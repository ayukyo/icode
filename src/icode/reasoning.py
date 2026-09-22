"""推理门禁（reasoning gate）：读真源 + 写**真实**的 trace 行。

真源：`<skill_root>/mcp/reasoning-gate/gates.json`
痕迹：`{out_dir}/.thinking_gate_trace.jsonl`（每 step 一行，**不记录思维正文**）

诚实原则（重要）：
    上游词表规定 L2 必须 `mechanism=sequential-thinking` 且 `attempted=true`。
    本运行时**尚未接入**该 MCP，因此对 L2/L3 步骤我们**不允许**写成功行——
    宁可如实写 `attempted=false` + `result=degraded` + 明确原因，让门禁拦下，
    也不伪造一行"看起来做过 L2"的 trace。
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

# 本运行时**真正具备**的推理机制（按等级）。未列出的等级一律走 degraded。
SUPPORTED_MECHANISMS: dict[str, str] = {
    "L0": "deterministic_checks",
}


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

    def build_row(self, ticket_id: str, step: str) -> TraceRow | None:
        """为该步骤构造**如实**的 trace 行。

        不需要 trace 的步骤返回 None（不该写行）。
        """
        info = self.for_step(step)
        if info is None or not info.requires_trace:
            return None
        mechanism, capable = self.capability_for(info.default_tier)
        if capable:
            return TraceRow(
                ticket_id=ticket_id, step=step, tier=info.default_tier,
                default_tier=info.default_tier, mechanism=mechanism,
                attempted=True, result="success", degraded_reason=None,
            )
        return TraceRow(
            ticket_id=ticket_id, step=step, tier=info.default_tier,
            default_tier=info.default_tier, mechanism=mechanism,
            attempted=False, result="degraded",
            degraded_reason=(
                f"本运行时尚未接入 {mechanism}（Phase 2 剩余项）；"
                "以有界回合循环替代，但**不冒充该等级机制**，因此不算满足推理门禁"
            ),
        )


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
