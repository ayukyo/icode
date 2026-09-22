"""步骤契约：从 gates.json 动态读取，**绝不写死步骤表**。

真源：`<skill_root>/mcp/workflow-gate/gates.json` 的 `execution_model`。
本模块只读，不修改上游任何文件。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# gates.json 中 execution_model 下的已知键（缺失时降级为空，不抛异常）
_EM_KEYS = (
    "boundaries",
    "input_kinds",
    "output_kinds",
    "step_outcomes",
    "step_contracts",
    "operation_classes",
    "failure_policies",
    "finish_gate_steps",
)


class ContractError(RuntimeError):
    """契约文件缺失或结构异常。"""


@dataclass(frozen=True)
class Port:
    """步骤的输入 / 输出端口。"""

    id: str
    kind: str
    value: str
    required: bool = False
    protected: bool = False


@dataclass(frozen=True)
class StepContract:
    step: str
    inputs: tuple[Port, ...] = ()
    outputs: tuple[Port, ...] = ()
    required_checks: tuple[str, ...] = ()
    drift_routes: dict[str, str] = field(default_factory=dict)

    @property
    def required_inputs(self) -> tuple[Port, ...]:
        return tuple(p for p in self.inputs if p.required)

    @property
    def required_outputs(self) -> tuple[Port, ...]:
        return tuple(p for p in self.outputs if p.required)

    @property
    def protected_inputs(self) -> tuple[Port, ...]:
        """受保护输入：执行中漂移即 fail-closed（Reactive 边界复检的对象）。"""
        return tuple(p for p in self.inputs if p.protected)

    def route_for(self, drift_input: str) -> str:
        return self.drift_routes.get(drift_input) or self.drift_routes.get("default") or self.step


def _to_port(item: object) -> Port:
    if isinstance(item, str):
        return Port(id=item, kind="unknown", value=item)
    if isinstance(item, dict):
        return Port(
            id=str(item.get("id", "")),
            kind=str(item.get("kind", "unknown")),
            value=str(item.get("value", "")),
            required=bool(item.get("required", False)),
            protected=bool(item.get("protected", False)),
        )
    raise ContractError(f"无法解析端口定义：{item!r}")


def _to_contract(step: str, raw: object) -> StepContract:
    if not isinstance(raw, dict):
        raise ContractError(f"步骤 {step} 的契约结构异常")
    checks = raw.get("required_checks") or ()
    routes = raw.get("drift_routes") or {}
    return StepContract(
        step=step,
        inputs=tuple(_to_port(i) for i in (raw.get("inputs") or ())),
        outputs=tuple(_to_port(o) for o in (raw.get("outputs") or ())),
        required_checks=tuple(str(c) for c in checks),
        drift_routes={str(k): str(v) for k, v in dict(routes).items()},
    )


class ContractSet:
    """gates.json 的只读视图。"""

    def __init__(self, raw: dict) -> None:
        em = raw.get("execution_model")
        if not isinstance(em, dict):
            raise ContractError("gates.json 缺少 execution_model")
        self._em = em
        self.schema_version = raw.get("schema_version")
        self._contracts: dict[str, StepContract] = {
            str(name): _to_contract(str(name), body)
            for name, body in dict(em.get("step_contracts") or {}).items()
        }

    # ---- 构造 ----

    @classmethod
    def load(cls, gates_json: Path) -> ContractSet:
        if not Path(gates_json).is_file():
            raise ContractError(f"契约文件不存在：{gates_json}")
        try:
            raw = json.loads(Path(gates_json).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ContractError(f"契约文件不是合法 JSON：{exc}") from None
        return cls(raw)

    # ---- 查询 ----

    def steps(self) -> tuple[str, ...]:
        """已登记步骤名（按 gates.json 中的顺序）。"""
        return tuple(self._contracts)

    def step(self, name: str) -> StepContract:
        try:
            return self._contracts[name]
        except KeyError:
            raise ContractError(
                f"未知步骤 {name!r}；已登记：{', '.join(self.steps())}"
            ) from None

    def has(self, name: str) -> bool:
        return name in self._contracts

    def boundaries(self) -> tuple[str, ...]:
        return tuple(str(b) for b in (self._em.get("boundaries") or ()))

    def operation_classes(self) -> tuple[str, ...]:
        raw = self._em.get("operation_classes") or {}
        return tuple(str(k) for k in dict(raw))

    def failure_policies(self) -> tuple[str, ...]:
        raw = self._em.get("failure_policies") or {}
        return tuple(str(k) for k in dict(raw))

    def step_outcomes(self) -> tuple[str, ...]:
        return tuple(str(o) for o in (self._em.get("step_outcomes") or ()))

    def finish_gate_steps(self) -> tuple[str, ...]:
        return tuple(str(s) for s in (self._em.get("finish_gate_steps") or ()))

    def raw(self) -> dict:
        return self._em


@dataclass(frozen=True)
class AlignmentIssue:
    kind: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - 展示用
        return f"[{self.kind}] {self.detail}"


def check_steps_alignment(contracts: ContractSet, steps_dir: Path) -> tuple[AlignmentIssue, ...]:
    """交叉校验 gates.json 的步骤与 `steps/*.md` 实时清单。

    上游 SKILL.md 明确规定：产物命名与 completed_steps 写号**以 steps/ 目录为准**，
    因此两者不一致时必须能被发现，而不是静默按某一方执行。
    """
    issues: list[AlignmentIssue] = []
    steps_dir = Path(steps_dir)
    if not steps_dir.is_dir():
        return (AlignmentIssue("missing_dir", f"steps 目录不存在：{steps_dir}"),)

    files = sorted(p.stem for p in steps_dir.glob("*.md"))
    # steps/ 的文件名形如 01_plan.md / fast.md，取末段作为步骤名
    doc_steps = {stem.split("_", 1)[1] if "_" in stem else stem for stem in files}

    for name in contracts.steps():
        if name not in doc_steps:
            issues.append(
                AlignmentIssue("contract_without_doc", f"gates.json 登记了 {name}，但 steps/ 无对应文档")
            )
    for name in sorted(doc_steps):
        if not contracts.has(name):
            issues.append(
                AlignmentIssue("doc_without_contract", f"steps/ 有 {name}.md，但 gates.json 未登记契约")
            )
    return tuple(issues)
