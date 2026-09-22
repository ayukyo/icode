"""崩溃恢复：从**事件链**重新水合上下文（Phase 4）。

恢复决策由两类真源共同决定，且**冲突时事件链优先**：
    - 控制面 `trace` 的投影：`open_steps` / `open_operations` / `open_agents`
    - 工单目录内的检查点：`.agent_checkpoint.json`（仅进度标记，不含模型正文）

四类结果：
    `start_fresh`              没有未闭合项 → 正常开始
    `resume`                   有未闭合 step / 只读动作 → 可继续（从事件链水合上下文）
    `verify_side_effect_first` 有未终结的**副作用**动作 → 必须先核对真实状态，禁止重放
    `blocked`                  事件链不可读或自相矛盾 → 停下，绝不猜

副作用那一类是本地最关键的规则：上游明确「先核对真实状态，再补 finish；禁止直接重放」，
因此本模块只负责**识别与阻止**，核对后的收尾由 `resolve_open_operation()` 显式完成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .checkpoint import Checkpointer, LoopCheckpoint
from .control import ControlError, ControlPlane

# 需要"先核对真实状态"的动作类别
SIDE_EFFECT_CLASSES = frozenset({"managed_write", "external_side_effect", "destructive_hardware"})
READ_ONLY_CLASS = "read_only"

ACTION_START_FRESH = "start_fresh"
ACTION_RESUME = "resume"
ACTION_VERIFY_SIDE_EFFECT = "verify_side_effect_first"
ACTION_BLOCKED = "blocked"


@dataclass
class RecoveryDecision:
    action: str
    reason: str
    step: str = ""
    open_steps: dict = field(default_factory=dict)
    open_operations: dict = field(default_factory=dict)
    open_agents: dict = field(default_factory=dict)
    checkpoint: LoopCheckpoint | None = None
    checkpoint_valid: bool = False
    registered_outputs: list[str] = field(default_factory=list)
    side_effect_operations: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def can_resume(self) -> bool:
        return self.action in (ACTION_RESUME, ACTION_START_FRESH)

    @property
    def needs_human(self) -> bool:
        return self.action in (ACTION_VERIFY_SIDE_EFFECT, ACTION_BLOCKED)

    def render(self) -> str:
        lines = [
            "崩溃恢复分析",
            f"  步骤：{self.step or '（未指定）'}",
            f"  决策：{self.action}",
            f"  理由：{self.reason}",
        ]
        if self.registered_outputs:
            lines.append("  已登记产物：" + "、".join(self.registered_outputs))
        if self.open_steps:
            lines.append(f"  未闭合步骤：{list(self.open_steps)}")
        if self.open_operations:
            lines.append(f"  未闭合动作：{list(self.open_operations)}")
        if self.side_effect_operations:
            lines.append("  ⚠ 未终结的副作用动作（必须先核对真实状态，禁止重放）：")
            for op in self.side_effect_operations:
                lines.append(f"      - attempt={op.get('attempt')} class={op.get('class')} name={op.get('name')}")
        if self.checkpoint is not None:
            cp = self.checkpoint
            lines.append(
                f"  检查点：{'有效' if self.checkpoint_valid else '无效'} "
                f"（回合 {cp.turn_index} / 工具调用 {cp.tool_calls} / attempt={cp.attempt}）"
            )
        else:
            lines.append("  检查点：无")
        if self.warnings:
            lines += ["  提示："] + [f"    - {w}" for w in self.warnings]
        return "\n".join(lines)

    def resume_brief(self) -> str:
        """注入新回合的恢复上下文（来自事件链，不是回放聊天记录）。"""
        if self.action == ACTION_BLOCKED:
            return "**恢复被阻断**：事件链不可读或自相矛盾，请人工核对后再继续。"
        lines = [
            "【恢复上下文（来自事件链，非聊天记录回放）】",
            f"  - 步骤：{self.step}",
        ]
        if self.checkpoint is not None and self.checkpoint_valid:
            lines.append(
                f"  - 上次运行进度：{self.checkpoint.turn_index} 个回合 / "
                f"{self.checkpoint.tool_calls} 次工具调用（attempt={self.checkpoint.attempt}）"
            )
            if self.checkpoint.pending_approvals:
                lines.append(
                    f"  - ⚠ 有 {self.checkpoint.pending_approvals} 项审批在中断时未决："
                    "**不会自动放行**，需要重新经人工确认"
                )
        if self.registered_outputs:
            lines.append("  - 已登记产物（不要重复劳动）：" + "、".join(self.registered_outputs))
        if self.side_effect_operations:
            lines.append("  - ⚠ 存在未终结的副作用动作：**禁止重放**，先核对真实状态")
        lines.append(
            "  要求：不要重放已完成的动作；直接从未完成处继续产出；"
            "若无法确认某动作是否已生效，停下来报告而不是再执行一次。"
        )
        return "\n".join(lines)


def _classify_open_operations(open_operations: dict) -> tuple[list[dict], list[dict]]:
    """把未闭合动作分成 (副作用类, 只读类)。

    防御性设计：**类别无法判定时按副作用处理**（更严格的一侧），
    因为误判为只读会导致重放副作用。
    """
    side_effects: list[dict] = []
    read_only: list[dict] = []
    for attempt, info in (open_operations or {}).items():
        data = info if isinstance(info, dict) else {}
        opclass = str(data.get("class") or data.get("opclass") or "")
        entry = {
            "attempt": attempt,
            "class": opclass or "unknown",
            "name": data.get("name") or data.get("action") or "",
        }
        if opclass == READ_ONLY_CLASS:
            read_only.append(entry)
        else:
            side_effects.append(entry)
    return side_effects, read_only


def _collect_attempts(open_steps: dict) -> set[str]:
    """从 trace 的 open_steps 投影里收集 attempt 标识。

    投影结构可能随上游演化，因此同时看键名与值里的 attempt 字段（防御性）。
    """
    found: set[str] = set()
    for key, value in (open_steps or {}).items():
        found.add(str(key))
        if isinstance(value, dict):
            inner = value.get("attempt")
            if inner:
                found.add(str(inner))
    return found


def _registered_outputs(out_dir: Path) -> list[str]:
    """从事件链里取已登记的产物（事件链是唯一真源）。"""
    import json

    path = Path(out_dir) / ".ico_events.jsonl"
    if not path.is_file():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") != "artifact_written":
            continue
        payload = event.get("payload") or {}
        # 优先显示人能一眼认出的文件名；退化为端口 id
        raw_path = str(payload.get("path") or "")
        name = Path(raw_path).name if raw_path else str(payload.get("output") or "")
        if name and name not in out:
            out.append(name)
    return out


class Recoverer:
    """按事件链判定"该怎么继续"。"""

    def __init__(self, control: ControlPlane, out_dir: Path | str, ticket_id: str) -> None:
        self.control = control
        self.out_dir = Path(out_dir)
        self.ticket_id = ticket_id

    def analyze(
        self, step: str, *, attempt: str | None = None, checkpointer: Checkpointer | None = None
    ) -> RecoveryDecision:
        try:
            trace = self.control.trace(self.out_dir)
        except ControlError as exc:
            return RecoveryDecision(
                action=ACTION_BLOCKED,
                reason=f"事件链不可读（trace 失败），无法安全判定恢复点：{exc}",
                step=step,
            )
        if trace.returncode != 0 or trace.data.get("ok") is not True:
            return RecoveryDecision(
                action=ACTION_BLOCKED,
                reason="事件链不可读（trace 返回非成功），无法安全判定恢复点",
                step=step,
            )

        open_steps = dict(trace.data.get("open_steps") or {})
        open_operations = dict(trace.data.get("open_operations") or {})
        open_agents = dict(trace.data.get("open_agents") or {})
        side_effects, read_only = _classify_open_operations(open_operations)

        decision = RecoveryDecision(
            action=ACTION_START_FRESH,
            reason="无未闭合项",
            step=step,
            open_steps=open_steps,
            open_operations=open_operations,
            open_agents=open_agents,
            registered_outputs=_registered_outputs(self.out_dir),
            side_effect_operations=side_effects,
        )

        # 检查点校验：与事件链冲突时**事件链优先**
        if checkpointer is not None and checkpointer.exists():
            cp = checkpointer.load()
            decision.checkpoint = cp
            if cp is not None:
                open_attempts = _collect_attempts(open_steps)
                if cp.ticket_id != self.ticket_id:
                    decision.warnings.append("检查点属于其它工单，已忽略")
                elif open_attempts and cp.attempt not in open_attempts:
                    decision.warnings.append(
                        "检查点指向的 attempt 在事件链上没有未闭合步骤（该步骤可能已终结）；"
                        "按事件链为准，丢弃检查点"
                    )
                    checkpointer.clear()
                elif not open_attempts:
                    decision.warnings.append(
                        "事件链无未闭合步骤，检查点已失效；按事件链为准，丢弃检查点"
                    )
                    checkpointer.clear()
                else:
                    decision.checkpoint_valid = True
            if decision.checkpoint is not None and decision.checkpoint.pending_approvals:
                decision.warnings.append(
                    f"中断时存在 {decision.checkpoint.pending_approvals} 项未决审批 —— 恢复后必须重新确认，不自动放行"
                )

        # 决策优先级：副作用 > 未闭合步骤 > 干净
        if side_effects:
            decision.action = ACTION_VERIFY_SIDE_EFFECT
            names = "、".join(f"{o['name']}({o['class']})" for o in side_effects)
            decision.reason = (
                f"存在 {len(side_effects)} 个未终结的副作用动作：{names}。"
                "必须先核对真实状态，再用 resolve_open_operation() 补 finish；禁止直接重放。"
            )
            return decision

        if open_steps:
            decision.action = ACTION_RESUME
            decision.reason = (
                f"存在未闭合步骤 {list(open_steps)}；从事件链重新水合上下文后继续（不重放已完成动作）"
            )
            return decision

        if read_only:
            decision.action = ACTION_RESUME
            decision.reason = (
                f"仅有未闭合的**只读**动作 {[o['attempt'] for o in read_only]}，"
                "按 policy 可重新执行；继续即可"
            )
            return decision

        if decision.checkpoint is not None and not decision.checkpoint_valid:
            decision.reason = "事件链无未闭合项，检查点已失效并丢弃"
        return decision

    # ---- 核对后收尾（人工确认路径） ----

    def resolve_open_operation(
        self,
        attempt: str,
        *,
        outcome: str,
        evidence: str,
        check_ref: str,
        failure: str | None = None,
    ) -> bool:
        """人工核对真实状态后补 `operation finish`（上游规定的正确收尾方式）。"""
        result = self.control.operation_finish(
            self.out_dir,
            attempt=attempt,
            outcome=outcome,
            evidence=evidence,
            check_ref=check_ref,
            failure=failure,
        )
        return result.returncode == 0 and result.data.get("ok") is True
