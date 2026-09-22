"""推理门禁（reasoning gate）：读真源 + 写**真实**的 trace 行。

真源：`<skill_root>/mcp/reasoning-gate/gates.json`
痕迹：`{out_dir}/.thinking_gate_trace.jsonl`（每 step 一行，**不记录思维正文**）

诚实原则（重要）：
    上游词表规定 L2 必须 `mechanism=sequential-thinking` 且 `attempted=true`。
    上游用一个 npm MCP 服务器提供该机制；**本仓自实现了同一机制**
    （`sequential.py`：有界分步推演），因此 L2 现在可以真实满足。

    但**不声称**调用了上游的 MCP：trace 行里按词表填 `mechanism`（机制名，硬约束），
    并额外用 `provider` / `provider_kind` 字段如实写明实现来源。
    `REQUIRED_FIELDS` 只检缺失、不拒绝额外键，因此这是允许的。

    更关键的一条：**没有真跑推演就不许写成功行**。`build_row` 只有在拿到
    满足下限步数的推演结果时才给 `result=success`，否则一律 `degraded`。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

TRACE_FILENAME = ".thinking_gate_trace.jsonl"

VALID_TIERS = ("L0", "L1", "L2", "L3")
VALID_RESULTS = ("success", "degraded", "blocked")

# 本运行时**真正具备**的推理机制（按等级 → provider 标识）。未列出的等级一律走 degraded。
SUPPORTED_MECHANISMS: dict[str, str] = {
    "L0": "deterministic_checks",
    "L1": "decision_record",
    "L2": "icode-in-repo-sequential-thinking",
}
# noqa: L3 尚未实现（需独立对抗者），因此仍在 unsatisfied 列表里


class ReasoningGateError(RuntimeError):
    """推理门禁真源缺失或结构异常。"""


@dataclass(frozen=True)
class StepReasoning:
    step: str
    default_tier: str
    requires_trace: bool
    desc: str = ""


@dataclass
class TraceRow:
    """`.thinking_gate_trace.jsonl` 的一行（字段严格对齐上游 schema）。"""

    ticket_id: str
    step: str
    tier: str
    default_tier: str
    triggers: list[str] = field(default_factory=list)
    mechanism: str = "deterministic_checks"
    attempted: bool = False
    result: str = "degraded"
    degraded_reason: str | None = None
    over_invoked: bool = False
    at: str = ""
    schema_version: int = 1
    # --- 以下为额外字段：如实记录机制由谁提供（上游只检必需键，不拒绝额外键） ---
    provider: str = ""
    provider_kind: str = "in_repo"
    deliberation_steps: int = 0
    deliberation_digest: str = ""

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "ticket_id": self.ticket_id,
            "step": self.step,
            "tier": self.tier,
            "default_tier": self.default_tier,
            "triggers": self.triggers,
            "mechanism": self.mechanism,
            "attempted": self.attempted,
            "result": self.result,
            "degraded_reason": self.degraded_reason,
            "over_invoked": self.over_invoked,
            "at": self.at or _now_iso(),
            "provider": self.provider,
            "provider_kind": self.provider_kind,
            "deliberation_steps": self.deliberation_steps,
            "deliberation_digest": self.deliberation_digest,
        }


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ReasoningGate:
    """`mcp/reasoning-gate/gates.json` 的只读视图。"""

    def __init__(self, raw: dict) -> None:
        assets = raw.get("steps") or {}
        if not isinstance(assets, dict):
            raise ReasoningGateError("reasoning-gate gates.json 的 steps 结构异常")
        self.schema_version = raw.get("schema_version")
        self._steps = assets
        self.mechanisms_by_tier: dict[str, str] = dict(raw.get("mechanisms_by_tier") or {})
        self.constants: dict = dict(raw.get("constants") or {})
        self.escalation_triggers = raw.get("escalation_triggers") or {}

    @classmethod
    def load(cls, path: Path) -> ReasoningGate:
        p = Path(path)
        if not p.is_file():
            raise ReasoningGateError(f"推理门禁真源不存在：{p}")
        try:
            return cls(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ReasoningGateError(f"推理门禁真源不是合法 JSON：{exc}") from None

    def steps(self) -> tuple[str, ...]:
        return tuple(self._steps)

    def for_step(self, step: str) -> StepReasoning | None:
        raw = self._steps.get(step)
        if not isinstance(raw, dict):
            return None
        return StepReasoning(
            step=step,
            default_tier=str(raw.get("default_tier", "L0")),
            requires_trace=bool(raw.get("requires_trace", False)),
            desc=str(raw.get("desc", "")),
        )

    # ---- 计划 ----

    def capability_for(self, tier: str) -> tuple[str, bool]:
        """本运行时的真实能力：(mechanism, 是否真能执行)."""
        mech = self.mechanisms_by_tier.get(tier) or SUPPORTED_MECHANISMS.get(tier, "deterministic_checks")
        return mech, tier in SUPPORTED_MECHANISMS

    def unsatisfied_steps(self) -> tuple[StepReasoning, ...]:
        """需要 trace 但我们当前等级能力不满足的步骤（用于如实上报）。"""
        out: list[StepReasoning] = []
        for step in self.steps():
            info = self.for_step(step)
            if info and info.requires_trace and info.default_tier not in SUPPORTED_MECHANISMS:
                out.append(info)
        return tuple(out)

    def build_row(
        self, ticket_id: str, step: str, *, deliberation=None
    ) -> TraceRow | None:
        """为该步骤构造**如实**的 trace 行。

        不需要 trace 的步骤返回 None（不该写行）。
        `deliberation` 为本 attempt 真实跑出的推演结果（`sequential.Deliberation`）。

        **成功行的前提是真跑过**：步数达到该等级下限才算 success，
        否则一律 degraded 并给出原因 —— 不允许"没做却报成功"。
        """
        info = self.for_step(step)
        if info is None or not info.requires_trace:
            return None
        mechanism, capable = self.capability_for(info.default_tier)
        provider = SUPPORTED_MECHANISMS.get(info.default_tier, "")

        min_steps = 3 if info.default_tier in ("L2", "L3") else 0
        if capable:
            steps = int(getattr(deliberation, "step_count", 0) or 0)
            if deliberation is not None and steps >= min_steps:
                return TraceRow(
                    ticket_id=ticket_id, step=step, tier=info.default_tier,
                    default_tier=info.default_tier, mechanism=mechanism,
                    attempted=True, result="success", degraded_reason=None,
                    provider=provider, provider_kind="in_repo",
                    deliberation_steps=steps,
                    deliberation_digest=str(getattr(deliberation, "digest", "")),
                )
            return TraceRow(
                ticket_id=ticket_id, step=step, tier=info.default_tier,
                default_tier=info.default_tier, mechanism=mechanism,
                attempted=False, result="degraded",
                degraded_reason=(
                    f"具备 {mechanism} 能力但本 attempt 未取得有效推演"
                    f"（步数 {steps} < 下限 {min_steps}）；如实降级，不冒充成功"
                ),
                provider=provider, provider_kind="in_repo",
            )
        return TraceRow(
            ticket_id=ticket_id, step=step, tier=info.default_tier,
            default_tier=info.default_tier, mechanism=mechanism,
            attempted=False, result="degraded",
            degraded_reason=(
                f"本运行时尚未实现 {mechanism}（该等级需要独立对抗者）；"
                "不冒充该等级机制，因此不算满足推理门禁"
            ),
        )


def run_deliberation(gate: ReasoningGate, backend, *, step: str, question: str):
    """按该步骤的等级要求，真跑一次推演；不需要 trace 的步骤返回 None。"""
    info = gate.for_step(step)
    if info is None or not info.requires_trace:
        return None
    if info.default_tier not in SUPPORTED_MECHANISMS:
        return None
    from .sequential import SequentialThinking

    return SequentialThinking(backend).run(question, tier=info.default_tier)


def append_trace(path: Path, rows: Iterable[TraceRow]) -> int:
    """追加 trace 行（UTF-8 + LF，每行一个 JSON 对象）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r.as_dict(), ensure_ascii=False) + "\n" for r in rows)
    with p.open("ab") as fh:
        fh.write(payload.encode("utf-8"))
    return len(payload)


def read_trace(path: Path) -> tuple[dict, ...]:
    p = Path(path)
    if not p.is_file():
        return ()
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return tuple(out)
