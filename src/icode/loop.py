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

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .approvals import ApprovalRequest, Approver, DenyAllApprover
from .backends import AssistantMessage, Backend, Usage
from .budget import BudgetTracker
from .guard import Decision, Guard, Verdict
from .operations import OperationRecorder
from .tools import OPCLASS_READ_ONLY, ToolContext, ToolRegistry, ToolResult


@dataclass
class LoopConfig:
    max_turns: int = 12
    max_tool_calls_per_turn: int = 8
    max_output_tokens: int = 2048
    tool_choice: str = "auto"
    tool_choice_after_read: str | None = None


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
        if (self.config.tool_choice not in ("auto", "required")
                and self.registry.get(self.config.tool_choice) is None):
            raise ValueError("tool_choice 必须是 auto、required 或已注册工具名")
        if self.config.tool_choice_after_read is not None:
            if self.config.tool_choice != "read_file":
                raise ValueError("tool_choice_after_read 需要初始 tool_choice=read_file")
            if self.registry.get(self.config.tool_choice_after_read) is None:
                raise ValueError("tool_choice_after_read 必须是已注册工具名")
            if not self.guard.scope.allowed_read_files:
                raise ValueError("tool_choice_after_read 需要精确文件读取白名单")
        self.on_event = on_event or (lambda kind, payload: None)
        # 每个回合结束后回调（用于写检查点；不得在此抛错中断循环）
        self.on_turn = on_turn

    # ---- 权限判定 ----

    def _decide(self, name: str, args: dict[str, Any]):
        if name == "submit_review":
            if (self.ctx.review_submission_enabled
                    and self.ctx.read_only_workspace
                    and self.ctx.change_baseline is not None):
                return Verdict(Decision.ALLOW, "只读 Reviewer 的结构化输出端口")
            return Verdict(Decision.DENY, "结构化审查提交仅在独立只读 Reviewer 中开放")
        if name in ("submit_artifact", "read_artifact"):
            if self.ctx.artifact_broker is None:
                return Verdict(Decision.DENY, "当前步骤未开放受控产物端口")
            return Verdict(Decision.ALLOW, "受控产物端口按步骤合同校验")
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
        # 回执和公开事件只保留参数摘要；正文、命令参数及私有路径不外泄。
        safe_args = {
            "arg_keys": sorted(args),
            "args_sha256": hashlib.sha256(
                json.dumps(args, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
        }
        op_attempt: str | None = None
        if self.operations is not None and tool.opclass != OPCLASS_READ_ONLY:
            started = self.operations.start(
                name=f"tool:{call_name}",
                opclass=tool.opclass,
                input_desc=json.dumps(safe_args, ensure_ascii=False),
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
        self.on_event("tool_start", {"tool": call_name, "arguments": safe_args})
        result = self.registry.invoke(call_name, self.ctx, args)
        inv.result = result
        self.on_event("tool_result", {"tool": call_name, "ok": result.ok, "meta": result.meta})

        if op_attempt and self.operations is not None:
            finished = self.operations.finish(
                op_attempt,
                outcome="success" if result.ok else "failure",
                evidence=f"tool={call_name}",
                check_ref=json.dumps(result.meta, ensure_ascii=False)[:200],
                failure=None if result.ok else "deterministic_failure",
            )
            if not finished:
                # 终结回执失败必须**可见**：它会在控制面留下未闭合动作，
                # 导致同名副作用再次 start 时被判 ambiguous_side_effect 而拒绝执行。
                # 以前这里静默失败，排查时只看到一串"副作用歧义，拒绝重放"。
                inv.note = (inv.note + "｜" if inv.note else "") + "副作用回执终结失败"
                if inv.result is not None:
                    inv.result.meta["operation_finish_failed"] = True
                self.on_event("operation_finish_failed",
                              {"tool": call_name, "attempt": op_attempt})
        return inv

    # ---- 主循环 ----

    def run(self, messages: list[dict]) -> LoopResult:
        history = list(messages)
        turns: list[Turn] = []
        stop_reason = "max_turns"
        error = ""
        total_tool_calls = 0
        tool_choice = self.config.tool_choice
        required_tool_retry_remaining = 1 if tool_choice != "auto" else 0
        expected_read_files = set(self.guard.scope.allowed_read_files or ())
        read_spans: dict[Path, list[tuple[int, int]]] = {}
        read_totals: dict[Path, int] = {}
        completed_read_files: set[Path] = set()

        for index in range(1, self.config.max_turns + 1):
            if self.budget.verdict == "over_budget":
                stop_reason = "budget_exceeded"
                break

            try:
                assistant = self.backend.complete(
                    history,
                    tools=self.registry.schemas(),
                    max_tokens=self.config.max_output_tokens,
                    tool_choice=tool_choice,
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
                if tool_choice != "auto":
                    _notify_turn(self.on_turn, index, total_tool_calls, history)
                    if required_tool_retry_remaining > 0:
                        required_tool_retry_remaining -= 1
                        history.append({
                            "role": "user",
                            "content": (
                                "本步骤要求通过已提供的工具完成操作；上一条普通文本不会被采纳。"
                                "请按当前 system 指令调用所需工具，不要用自由文本代替。"
                            ),
                        })
                        continue
                    stop_reason = "required_tool_not_called"
                    error = "必需工具模式下模型连续未调用工具，已失败关闭"
                    return LoopResult(False, stop_reason, turns, history,
                                      self.budget.usage, error)
                stop_reason = "no_tool_calls"
                _notify_turn(self.on_turn, index, total_tool_calls, history)
                return LoopResult(True, stop_reason, turns, history, self.budget.usage)

            allowed = assistant.tool_calls[: self.config.max_tool_calls_per_turn]
            skipped = assistant.tool_calls[len(allowed) :]

            for call in allowed:
                inv = self._invoke(call.name, dict(call.arguments or {}))
                turn.invocations.append(inv)
                history.append(_tool_message(call.id, inv))
                completed_path = _record_complete_read_file(
                        inv,
                        expected_files=expected_read_files,
                        spans=read_spans,
                        totals=read_totals,
                        output_limit=self.ctx.output_limit,
                    )
                if completed_path is not None:
                    completed_read_files.add(completed_path)
                if (
                    self.config.tool_choice_after_read is not None
                    and tool_choice == self.config.tool_choice
                    and expected_read_files.issubset(completed_read_files)
                ):
                    # 只有所有精确白名单文件均被无截断、完整读取后，才强制最终提交工具。
                    tool_choice = self.config.tool_choice_after_read
                if (
                    tool_choice != "auto"
                    and call.name == "submit_review"
                    and inv.result is not None
                    and inv.result.ok
                    and inv.result.meta.get("review_output") == "schema_valid"
                ):
                    # Reviewer 结构化提交通过本地校验后，允许模型自然结束；
                    # 提交前强制使用工具，避免只返回自由文本绕过合同。
                    tool_choice = "auto"

            # 超出单回合上限的调用**也要回一条配对结果**：
            # OpenAI 兼容协议要求 assistant 消息里每个 tool_call 都有对应的 tool 消息，
            # 否则下一次请求会因参数不合法被拒（实测 HTTP 400）。
            # 而且这里如实说明"未执行"，而不是假装执行过。
            for call in skipped:
                inv = ToolInvocation(
                    name=call.name,
                    arguments=dict(call.arguments or {}),
                    decision=Decision.DENY.value,
                    approved=False,
                    result=ToolResult(
                        ok=False,
                        content=(
                            f"未执行：本回合工具调用数超过上限"
                            f"（{self.config.max_tool_calls_per_turn}）。"
                            "请缩小批次，在下一回合重发这条调用。"
                        ),
                        meta={"error": "turn_tool_budget"},
                    ),
                    note="超出单回合工具调用上限，未执行",
                )
                turn.invocations.append(inv)
                history.append(_tool_message(call.id, inv))
                self.on_event("tool_skipped_budget", {"tool": call.name})

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


def _record_complete_read_file(
    invocation: ToolInvocation,
    *,
    expected_files: set[Path],
    spans: dict[Path, list[tuple[int, int]]],
    totals: dict[Path, int],
    output_limit: int,
) -> Path | None:
    """Record a successful, untruncated read span and report if this span closes the file."""
    if invocation.name != "read_file" or invocation.result is None or not invocation.result.ok:
        return None
    if invocation.result.clipped(output_limit) != invocation.result.content:
        return None
    try:
        meta = invocation.result.meta
        path = Path(meta["path"]).resolve(strict=True)
        start, end, total = meta["start"], meta["end"], meta["total_lines"]
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        return None
    if (path not in expected_files or type(start) is not int or type(end) is not int
            or type(total) is not int or total < 0):
        return None
    previous_total = totals.setdefault(path, total)
    if previous_total != total:
        totals.pop(path, None)
        spans.pop(path, None)
        return None
    file_spans = spans.setdefault(path, [])
    file_spans.append((start, end))
    if total == 0:
        return path if start == 1 and end == 0 else None
    next_line = 1
    for span_start, span_end in sorted(file_spans):
        if span_end < next_line:
            continue
        if span_start > next_line:
            return None
        next_line = max(next_line, span_end + 1)
    return path if next_line > total else None


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
