"""有界 Agent 回合循环（Phase 2 核心）。

每个工具调用都必须依次通过：
    1) 工具存在性检查
    2) **权限判定**（guard，默认拒绝）
    3) **人工审批**（需要时暂停等待，默认拒绝）
    4) **副作用回执**（operation start/finish；歧义即停止，绝不重放）
    5) 执行 + 输出截断后回灌模型

循环是**有界**的：有最大回合数、单回合工具调用数上限与预算闸门。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .approvals import ApprovalRequest, Approver, DenyAllApprover
from .backends import AssistantMessage, Backend, Usage
from .budget import BudgetTracker
from .guard import Decision, Guard
from .operations import OperationRecorder
from .tools import OPCLASS_READ_ONLY, ToolContext, ToolRegistry, ToolResult


@dataclass
class LoopConfig:
    max_turns: int = 12
    max_tool_calls_per_turn: int = 4
    max_output_tokens: int = 2048


@dataclass
class ToolInvocation:
    name: str
    arguments: dict
    decision: str
    approved: bool
    result: ToolResult | None = None
    note: str = ""


@dataclass
class Turn:
    index: int
    assistant: AssistantMessage
    invocations: list[ToolInvocation] = field(default_factory=list)


@dataclass
class LoopResult:
    ok: bool
    stop_reason: str
    turns: list[Turn] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage, repr=False)
    error: str = ""

    @property
    def tool_calls(self) -> int:
        return sum(len(t.invocations) for t in self.turns)

    def render(self) -> str:
        lines = [f"回合循环：{len(self.turns)} 回合 / {self.tool_calls} 次工具调用；停止原因={self.stop_reason}"]
        for turn in self.turns:
            for inv in turn.invocations:
                mark = "OK " if inv.approved else "SKIP"
                lines.append(f"  {mark} {inv.name} [{inv.decision}] {inv.note}")
        if self.error:
            lines.append(f"  错误：{self.error}")
        return "\n".join(lines)


EventHook = Callable[[str, dict], None]
TurnHook = Callable[[int, int, list[dict]], None]  # (turn_index, tool_calls, history)


class AgentLoop:
    """有界的「模型 → 工具 → 模型」循环。"""

    def __init__(
        self,
        *,
        backend: Backend,
        registry: ToolRegistry,
        guard: Guard,
        ctx: ToolContext,
        approver: Approver | None = None,
        operations: OperationRecorder | None = None,
        budget: BudgetTracker | None = None,
        config: LoopConfig | None = None,
        on_event: EventHook | None = None,
        on_turn: TurnHook | None = None,
    ) -> None:
        self.backend = backend
        self.registry = registry
        self.guard = guard
        self.ctx = ctx
        self.approver: Approver = approver or DenyAllApprover()
        self.operations = operations
        self.budget = budget or BudgetTracker()
        self.config = config or LoopConfig()
        self.on_event = on_event or (lambda kind, payload: None)
        # 每个回合结束后回调（用于写检查点；不得在此抛错中断循环）
        self.on_turn = on_turn

    # ---- 权限判定 ----

    def _decide(self, name: str, args: dict[str, Any]):
        if name in ("read_file", "grep"):
            return self.guard.check_read(str(args.get("path") or "."))
        if name == "glob":
            return self.guard.check_read(str(self.ctx.root))
        if name in ("write_file", "edit_file"):
            return self.guard.check_write(str(args.get("path") or ""))
        if name == "run_command":
            return self.guard.check_command(args.get("argv") or [])
        return self.guard.check_read(str(self.ctx.root))

    # ---- 单次工具调用 ----

    def _invoke(self, call_name: str, args: dict[str, Any]) -> ToolInvocation:
        tool = self.registry.get(call_name)
        if tool is None:
            return ToolInvocation(call_name, args, Decision.DENY.value, False,
                                  ToolResult(False, f"未知工具：{call_name}", {"error": "unknown_tool"}),
                                  "工具不存在")

        verdict = self._decide(call_name, args)
        inv = ToolInvocation(call_name, args, verdict.decision.value, False, note=verdict.reason)

        if verdict.decision is Decision.DENY:
            inv.result = ToolResult(False, f"已被权限模型拒绝：{verdict.reason}",
                                    {"error": "denied"}, opclass=tool.opclass)
            self.on_event("tool_denied", {"tool": call_name, "reason": verdict.reason})
            return inv

        if verdict.decision is Decision.REQUIRE_APPROVAL:
            request = ApprovalRequest(
                tool=call_name, arguments=args, reason=verdict.reason,
                opclass=tool.opclass, workspace=str(self.ctx.root),
            )
            self.on_event("approval_requested", {"tool": call_name, "reason": verdict.reason})
            if not self.approver.ask(request):
                inv.result = ToolResult(False, "人工未放行，已跳过该动作", {"error": "not_approved"},
                                        opclass=tool.opclass)
                self.on_event("approval_denied", {"tool": call_name})
                return inv
            inv.note = f"{verdict.reason}｜已人工放行"

        # 副作用回执：写与执行类动作必须留 start/finish
        op_attempt: str | None = None
        if self.operations is not None and tool.opclass != OPCLASS_READ_ONLY:
            started = self.operations.start(
                name=f"tool:{call_name}",
                opclass=tool.opclass,
                input_desc=json.dumps(args, ensure_ascii=False)[:200],
            )
            if not started.can_execute:
                inv.result = ToolResult(
                    False,
                    "副作用回执不明确，已停止执行并等待人工核对（禁止盲目重放）："
                    + (started.detail or "ambiguous_side_effect"),
                    {"error": "ambiguous_side_effect"},
                    opclass=tool.opclass,
                )
                inv.note = "副作用歧义，拒绝重放"
                self.on_event("operation_ambiguous", {"tool": call_name, "detail": started.detail})
                return inv
            op_attempt = started.attempt

        inv.approved = True
        self.on_event("tool_start", {"tool": call_name, "arguments": args})
        result = self.registry.invoke(call_name, self.ctx, args)
        inv.result = result
        self.on_event("tool_result", {"tool": call_name, "ok": result.ok, "meta": result.meta})

        if op_attempt and self.operations is not None:
            self.operations.finish(
                op_attempt,
                outcome="success" if result.ok else "failure",
                evidence=f"tool={call_name}",
                check_ref=json.dumps(result.meta, ensure_ascii=False)[:200],
                failure=None if result.ok else "deterministic_failure",
            )
        return inv

    # ---- 主循环 ----

    def run(self, messages: list[dict]) -> LoopResult:
        history = list(messages)
        turns: list[Turn] = []
        stop_reason = "max_turns"
        error = ""
        total_tool_calls = 0

        for index in range(1, self.config.max_turns + 1):
            if self.budget.verdict == "over_budget":
                stop_reason = "budget_exceeded"
                break

            try:
                assistant = self.backend.complete(
                    history,
                    tools=self.registry.schemas(),
                    max_tokens=self.config.max_output_tokens,
                )
            except Exception as exc:  # noqa: BLE001 - 模型失败要如实上报，不吞掉
                return LoopResult(False, "backend_error", turns, history,
                                  getattr(self.backend, "usage", Usage()), f"{type(exc).__name__}: {exc}")

            last = getattr(self.backend, "last_usage", None)
            if last is not None:
                self.budget.record(last)

            turn = Turn(index=index, assistant=assistant)
            history.append(_assistant_message(assistant))
            self.on_event("assistant", {"index": index, "content": assistant.content,
                                        "tool_calls": [c.name for c in assistant.tool_calls]})

            if not assistant.has_tool_calls:
                turns.append(turn)
                stop_reason = "no_tool_calls"
                _notify_turn(self.on_turn, index, total_tool_calls, history)
                return LoopResult(True, stop_reason, turns, history, self.budget.usage)

            for call in assistant.tool_calls[: self.config.max_tool_calls_per_turn]:
                inv = self._invoke(call.name, dict(call.arguments or {}))
                turn.invocations.append(inv)
                history.append(_tool_message(call.id, inv))
            total_tool_calls += len(turn.invocations)
            turns.append(turn)
            _notify_turn(self.on_turn, index, total_tool_calls, history)

        return LoopResult(stop_reason == "no_tool_calls", stop_reason, turns, history,
                          self.budget.usage, error)


def _notify_turn(
    hook: TurnHook | None, turn_index: int, total_tool_calls: int, history: list[dict]
) -> None:
    """回合结束回调。**钩子异常不得中断循环**——检查点写失败不该毁掉整次运行。"""
    if hook is None:
        return
    try:
        hook(turn_index, total_tool_calls, history)
    except Exception:  # noqa: BLE001
        pass


def _assistant_message(msg: AssistantMessage) -> dict:
    payload: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        payload["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)},
            }
            for c in msg.tool_calls
        ]
    return payload


def _tool_message(call_id: str, inv: ToolInvocation) -> dict:
    if inv.result is None:
        body = inv.note or "动作未执行"
    else:
        body = inv.result.clipped()
        if not inv.result.ok:
            body = f"[失败] {body}"
    return {"role": "tool", "tool_call_id": call_id, "content": body}


def build_guard_and_ctx(workspace: Path, *, readable: tuple[Path, ...] = ()) -> tuple[Guard, ToolContext]:
    from .guard import Scope

    root = Path(workspace).resolve()
    return Guard(Scope(workspace_root=root, readable_roots=readable)), ToolContext(root=root)
