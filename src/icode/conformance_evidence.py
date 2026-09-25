"""把真实探针证据映射到十项一致性合同并评分（R2.2 评分闭环）。

设计契约（来自 docs/nbl/specs/2026-09-23-r2-cross-platform-isolation-design.md §12.1）：

- 本模块**只消费已提供的证据**，不执行自检、不生成 ready 回执；
- 每一项能力都必须有**直接**证据才能记 True；没有直接证据的一律记 False
  （保守，避免把「配置存在」当成「已强制」）；
- 能力证据来源逐项列出，便于审计方核对「这条结论来自哪条实测」。

典型用法：

    from icode.conformance_evidence import score_probe_evidence

    report = score_probe_evidence(
        checks={"workspace_write": True, "outside_write_denied": True, ...},
        platform="linux",
        process_tree_cleanup=True,
        resource_limits=True,
        uniform_violation=True,
    )
    # report["score"] = {"passed": ..., "total": 10, "critical_passed": ..., "ready": ...}
    # report["outcomes"]  # 十项逐项 bool
    # report["evidence"]  # 逐项证据来源
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .conformance import evaluate_platform_conformance, load_conformance_contract

# 探针检查键 → 能力 id 的直接证据映射。
# 只有**能被该检查直接证明**的能力才会被点亮；否则保守置 False。
_DIRECT_EVIDENCE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("workspace_write_boundary", ("workspace_write", "outside_write_denied")),
    ("protected_paths", ("protected_write_denied",)),
    ("sensitive_read_boundary", ("secret_read_denied",)),
    ("network_default_deny", ("network_denied",)),
    ("network_temporary_allowlist", ("network_allowlist_expiry",)),
    ("child_inheritance", ("child_inherits",)),
    ("process_tree_cleanup", ()),   # 来自独立回收探针，不来自原生最小探针
    ("resource_limits", ()),        # 来自独立资源限制探针
    ("uniform_violation", ()),      # 来自独立违规回执探针
    ("doctor_self_test", ()),       # 来自探针本身是否执行完成
)

_CAPABILITY_IDS = {
    "workspace_write_boundary",
    "protected_paths",
    "sensitive_read_boundary",
    "network_default_deny",
    "network_temporary_allowlist",
    "child_inheritance",
    "process_tree_cleanup",
    "resource_limits",
    "uniform_violation",
    "doctor_self_test",
}

# 需要**外部独立证据**（不在原生最小探针 checks 内）的能力 id
_EXTERNAL_EVIDENCE_IDS = {
    "process_tree_cleanup",
    "resource_limits",
    "uniform_violation",
}


class ConformanceEvidenceError(ValueError):
    """证据映射/评分输入非法。"""


def _require_string_keys(value: Mapping[Any, Any], location: str) -> None:
    invalid = [key for key in value if type(key) is not str]
    if invalid:
        raise ConformanceEvidenceError(f"{location} 的键必须是字符串：{invalid!r}")


def map_probe_checks(checks: Mapping[str, bool]) -> dict[str, bool]:
    """把一次原生探针的 checks 字典映射成十项能力的逐项结果（保守）。

    原生最小探针只直接证明其中一部分；没有直接证据的能力一律 False。
    """
    if not isinstance(checks, Mapping):
        raise ConformanceEvidenceError("checks 必须是映射")
    _require_string_keys(checks, "checks")
    for key, value in checks.items():
        if type(value) is not bool:
            raise ConformanceEvidenceError(f"checks[{key!r}] 必须是布尔值")

    outcomes: dict[str, bool] = {}
    evidence: dict[str, list[str]] = {}
    for capability_id, required_checks in _DIRECT_EVIDENCE:
        if not required_checks:
            evidence[capability_id] = []
            outcomes[capability_id] = False
            continue
        missing = [name for name in required_checks if name not in checks]
        passed = not missing and all(checks[name] for name in required_checks)
        evidence[capability_id] = [name for name in required_checks if checks.get(name)]
        outcomes[capability_id] = passed
    return outcomes


def apply_external_evidence(
    outcomes: Mapping[str, bool],
    *,
    process_tree_cleanup: bool | None = None,
    resource_limits: bool | None = None,
    uniform_violation: bool | None = None,
    doctor_self_test: bool | None = None,
) -> dict[str, bool]:
    """把独立探针（回收/资源/回执/自检）的结果合并进十项结果。

    传入 None 表示「没有该项独立证据」→ 保持 False（未验证）。
    """
    if not isinstance(outcomes, Mapping):
        raise ConformanceEvidenceError("outcomes 必须是映射")
    merged = dict(outcomes)
    for capability_id, value in (
        ("process_tree_cleanup", process_tree_cleanup),
        ("resource_limits", resource_limits),
        ("uniform_violation", uniform_violation),
        ("doctor_self_test", doctor_self_test),
    ):
        if value is not None:
            if type(value) is not bool:
                raise ConformanceEvidenceError(f"{capability_id} 必须是布尔值或 None")
            merged[capability_id] = value
    return merged


def score_probe_evidence(
    checks: Mapping[str, bool],
    *,
    platform: str,
    process_tree_cleanup: bool | None = None,
    resource_limits: bool | None = None,
    uniform_violation: bool | None = None,
    doctor_self_test: bool | None = None,
    process_group_cleanup: bool | None = None,
) -> dict[str, Any]:
    """把真实证据映射成十项结果并评分；返回含逐项证据来源的完整回执。

    参数语义（诚实边界）：
    - `checks`：原生探针的逐项布尔检查（如 `probe_native_sandbox(...).checks`）；
    - `process_tree_cleanup` / `resource_limits` / `uniform_violation`：
      各自独立探针的结果；None = 未验证 → False；
    - `doctor_self_test`：探针是否执行完成；None = 未验证 → False。
    """
    if type(platform) is not str or platform not in {"linux", "macos", "windows"}:
        raise ConformanceEvidenceError("platform 必须是 linux/macos/windows")

    outcomes = map_probe_checks(checks)
    outcomes = apply_external_evidence(
        outcomes,
        process_tree_cleanup=process_tree_cleanup,
        resource_limits=resource_limits,
        uniform_violation=uniform_violation,
        doctor_self_test=doctor_self_test,
    )
    if set(outcomes) != _CAPABILITY_IDS:
        missing = sorted(_CAPABILITY_IDS - set(outcomes))
        unknown = sorted(set(outcomes) - _CAPABILITY_IDS)
        raise ConformanceEvidenceError(
            f"十项结果不完整：missing={missing!r} unknown={unknown!r}"
        )

    score = evaluate_platform_conformance(
        outcomes,
        platform=platform,
        process_group_cleanup=process_group_cleanup,
    )
    contract = load_conformance_contract()

    direct_by_id = {capability_id: required for capability_id, required in _DIRECT_EVIDENCE}
    evidence: dict[str, list[str]] = {}
    for capability_id in _CAPABILITY_IDS:
        if capability_id in _EXTERNAL_EVIDENCE_IDS or capability_id == "doctor_self_test":
            source = (
                "independent_probe"
                if outcomes[capability_id]
                else "no_independent_evidence"
            )
        else:
            source = [
                name for name, passed in (checks or {}).items()
                if passed and name in direct_by_id[capability_id]
            ]
            if not source:
                source = ["no_direct_evidence"]
        evidence[capability_id] = source

    return {
        "platform": platform,
        "outcomes": outcomes,
        "evidence": evidence,
        "score": score,
        "contract": {
            "id": contract["contract_id"],
            "total": len(contract["capabilities"]),
            "critical": sum(item["critical"] for item in contract["capabilities"]),
            "minimum_passed": contract["minimum_passed"],
        },
        "honest_note": (
            "仅直接证据计为通过；未验证能力记为 False。"
            "评分不是自动模式放行的依据，也不能代替后端自检回执。"
        ),
    }
