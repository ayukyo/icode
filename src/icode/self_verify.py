"""R3 自验证与有界修复（产品架构 §13.7）。

从「能修改」升级到「能根据真实失败证据验证和修复」：

    修改 → 静态诊断 → 编译 → 单元测试 → 失败分类 → 有界修复 → 回归 → 独立 Reviewer

本模块只负责三个可独立测试的核心能力，不替代控制面门禁、不伪造证据：

1. **失败分类**（`classify_failure`）
   把一条命令 / 测试 / 契约回执的失败分成六类：
   `environment` / `code` / `test` / `contract` / `model_capability` / `side_effect_unknown`。
   分类依据是**可见证据**（退出码、输出模式、错误类型、是否产物缺失），
   不做没有依据的猜测；无法归类时如实归入 `side_effect_unknown`（fail-safe）。

2. **证据绑定**（`VerificationEvidence` / `evidence_fingerprint`）
   每次验证都绑定到 step、attempt、命令摘要、退出码、环境指纹、产物哈希、
   输出摘要与捕获时间。没有绑定的结果不能被当成「新证据」，
   也就不能支撑一次新的修复。

3. **有界修复决策**（`VerificationLedger` / `decide_repair`）
   只有当出现**新的失败证据**时才允许重试 / 修复；相同指纹的重复失败
   会被检测并在有界次数内终止，避免「没有新证据就反复碰运气」。
   副作用状态不明一律按 fail-safe 拒绝自动重试。
"""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

# 架构 §13.7 的六类失败
FAILURE_ENVIRONMENT = "environment"
FAILURE_CODE = "code"
FAILURE_TEST = "test"
FAILURE_CONTRACT = "contract"
FAILURE_MODEL_CAPABILITY = "model_capability"
FAILURE_SIDE_EFFECT_UNKNOWN = "side_effect_unknown"

FAILURE_CATEGORIES = (
    FAILURE_ENVIRONMENT,
    FAILURE_CODE,
    FAILURE_TEST,
    FAILURE_CONTRACT,
    FAILURE_MODEL_CAPABILITY,
    FAILURE_SIDE_EFFECT_UNKNOWN,
)

# 可自动重试 / 修复的类别；其余要求人工或停止（fail-safe）
AUTO_REPAIRABLE_CATEGORIES = {FAILURE_CODE, FAILURE_TEST, FAILURE_MODEL_CAPABILITY}

# 环境类：进程级 / 系统级信号（与具体代码改动无关）
_ENVIRONMENT_EXIT_CODES = {127, 126, 128, 137, 139, 134, 132, 2}

# 环境类错误形态（出现在输出里）
_ENVIRONMENT_PATTERNS = (
    "No such file or directory",
    "command not found",
    "ModuleNotFoundError",
    "ImportError: No module named",
    "Connection refused",
    "Connection timed out",
    "Name or service not known",
    "Cannot allocate memory",
    "Out of memory",
    "Killed",
    "Permission denied",
)

# 契约/门禁类：来自控制面回执，不是工程代码问题
_CONTRACT_PATTERNS = (
    "产物缺失",
    "产物登记",
    "边界复检",
    "门禁",
    "ambiguous_side_effect",
    "operation_ambiguous",
    "operation_finish_failed",
    "metadata",
    "状态前移",
    "review_manifest",
    "required_checks",
)

# 模型能力类：模型没有按契约产出 / 产出无法解析
_MODEL_CAPABILITY_PATTERNS = (
    "提取不到",
    "无法提取",
    "invalid JSON",
    "JSONDecodeError",
    "not_approved",
    "unknown_tool",
    "模型回复",
    "回合循环未自然结束",
    "max_turns",
)


@dataclass(frozen=True)
class VerificationEvidence:
    """一次验证结果及其绑定信息。

    语义：这条证据**只**对 `step` + `attempt` + `command`（摘要） +
    `exit_code` + `output_sha256` + `environment_fingerprint` +
    `artifact_hashes` 这些事实成立。任一事实变化都应产生新的证据，
    否则复用旧证据去推动状态前进会被视为「没有新证据」。
    """

    step: str
    attempt: str
    kind: str = "command"          # command / test / gate
    command: tuple[str, ...] = ()
    exit_code: int | None = None
    output: str = ""
    environment_fingerprint: str = ""
    artifact_hashes: Mapping[str, str] = field(default_factory=dict)
    category: str = FAILURE_SIDE_EFFECT_UNKNOWN
    captured_at: str = ""
    raw_error: str = ""

    @property
    def output_sha256(self) -> str:
        return _sha256(self.output.encode("utf-8"))

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and self.category not in (
            FAILURE_CONTRACT, FAILURE_SIDE_EFFECT_UNKNOWN,
        )


@dataclass(frozen=True)
class RepairDecision:
    action: str            # allow / no_new_evidence / too_many_attempts / human
    attempt: int
    reason: str
    previous_fingerprint: str = ""
    current_fingerprint: str = ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def environment_fingerprint() -> str:
    """返回运行环境的轻量指纹（不含密钥、不含完整路径清单）。

    只取解释器版本、平台名、架构与平台版本；不读环境变量正文，
    避免把宿主凭据带进证据。
    """
    payload = json.dumps(
        {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "machine": platform.machine(),
            "release": platform.release(),
        },
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return _sha256(payload.encode("utf-8"))


def evidence_fingerprint(evidence: VerificationEvidence) -> str:
    """把一次验证绑定成确定性指纹；任何绑定事实变化都会改变指纹。

    指纹只依赖**去重、确定性**的事实；输出正文不直接进指纹，
    只用其 sha256，避免把大输出或敏感内容写进指纹。
    """
    artifacts = {
        str(key): str(value)
        for key, value in sorted(evidence.artifact_hashes.items())
    }
    payload = json.dumps(
        {
            "step": evidence.step,
            "attempt": evidence.attempt,
            "kind": evidence.kind,
            "command": list(evidence.command),
            "exit_code": evidence.exit_code,
            "output_sha256": evidence.output_sha256,
            "environment_fingerprint": evidence.environment_fingerprint,
            "artifact_hashes": artifacts,
            "category": evidence.category,
        },
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return _sha256(payload.encode("utf-8"))


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = _normalize_text(text)
    return any(p.lower() in lowered for p in patterns)


def classify_failure(
    *,
    exit_code: int | None,
    output: str = "",
    error: str = "",
    kind: str = "command",
    missing_artifacts: tuple[str, ...] = (),
    json_parse_failed: bool = False,
    ambiguous_side_effect: bool = False,
    tool_denied: bool = False,
) -> str:
    """把一次失败证据分类到六类之一；无法归类时按 fail-safe 归为 side_effect_unknown。

    分类是**证据驱动**的：先看最具体、最可靠的信号，逐级收窄；
    不会因为输出里同时出现多种模式就丢弃证据去猜。
    """
    if ambiguous_side_effect:
        return FAILURE_SIDE_EFFECT_UNKNOWN
    if tool_denied:
        return FAILURE_CONTRACT
    if json_parse_failed:
        return FAILURE_MODEL_CAPABILITY
    if missing_artifacts:
        return FAILURE_CONTRACT
    if kind == "gate":
        return FAILURE_CONTRACT

    if kind == "test":
        # 测试运行本身失败（收集/加载错误）与断言失败（代码问题）区分开。
        # 收集/加载错误在退出码 2（pytest 的 error/interrupted）和未收集到用例
        # 时出现，先于环境类退出码判断，因为这是「测试架子」而非系统问题。
        lowered = _normalize_text(output + "\n" + error)
        if any(pat in lowered for pat in (
            "failed to collect", "could not collect", "import error while loading",
            "fixture", "no tests ran", "error collecting", "collector failed",
        )):
            return FAILURE_TEST
        if exit_code == 2 and "no tests ran" in lowered:
            return FAILURE_TEST
        # 环境形态（缺依赖/缺命令）仍优先于通用代码回归
        if _contains_any(output + "\n" + error, _ENVIRONMENT_PATTERNS):
            return FAILURE_ENVIRONMENT
        # 默认：测试退出非零 → 代码改动导致断言失败
        return FAILURE_CODE

    if exit_code is not None and exit_code in _ENVIRONMENT_EXIT_CODES:
        # 126/127 是系统找不到命令；128+ 是信号类终止 —— 与具体代码改动无关。
        return FAILURE_ENVIRONMENT
    if _contains_any(output + "\n" + error, _ENVIRONMENT_PATTERNS):
        return FAILURE_ENVIRONMENT
    if _contains_any(output + "\n" + error, _CONTRACT_PATTERNS):
        return FAILURE_CONTRACT
    if _contains_any(output + "\n" + error, _MODEL_CAPABILITY_PATTERNS):
        return FAILURE_MODEL_CAPABILITY

    if kind == "command":
        # 通用命令失败：默认归为代码（改动引入的回归），但保留可纠正性。
        return FAILURE_CODE

    return FAILURE_SIDE_EFFECT_UNKNOWN


class VerificationLedger:
    """记录每次验证的证据，检测「无新证据的重复尝试」，决定有界修复。"""

    def __init__(self, *, max_attempts: int = 3, env: str = "") -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        self.environment_fingerprint = env or environment_fingerprint()
        self._entries: list[VerificationEvidence] = []
        self._seen_fingerprints: set[str] = set()

    @property
    def attempts(self) -> int:
        return len(self._entries)

    def record(self, evidence: VerificationEvidence) -> VerificationEvidence:
        """登记一次验证证据；同一步内重复指纹被记忆，用于阻止无进展重试。"""
        bound = VerificationEvidence(
            step=evidence.step,
            attempt=str(len(self._entries) + 1),
            kind=evidence.kind,
            command=tuple(evidence.command),
            exit_code=evidence.exit_code,
            output=evidence.output,
            environment_fingerprint=evidence.environment_fingerprint
            or self.environment_fingerprint,
            artifact_hashes=dict(evidence.artifact_hashes),
            category=evidence.category,
            captured_at=evidence.captured_at or _now(),
            raw_error=evidence.raw_error,
        )
        self._seen_fingerprints.add(evidence_fingerprint(bound))
        self._entries.append(bound)
        return bound

    def last(self) -> VerificationEvidence | None:
        return self._entries[-1] if self._entries else None

    def decide_repair(
        self,
        evidence: VerificationEvidence,
        *,
        has_new_evidence: bool = True,
    ) -> RepairDecision:
        """根据最新证据决定是否允许修复 / 重试。

        规则（fail-safe）：
        - 副作用不明 → human（绝不自动重放）；
        - 超过有界次数 → too_many_attempts（停止）；
        - 没有新证据（指纹未变）→ no_new_evidence（停止碰运气）；
        - 新证据且类别可自动修复 → allow；
        - 环境 / 契约类失败默认也允许修复（环境类通常修复环境，契约类补产物），
          但每次都必须有新证据。
        """
        current = self.record(evidence)
        attempt = len(self._entries)

        if current.category == FAILURE_SIDE_EFFECT_UNKNOWN:
            return RepairDecision(
                "human", attempt,
                "副作用状态不明，禁止自动重放；请先核对真实状态再继续",
                previous_fingerprint="", current_fingerprint=evidence_fingerprint(current),
            )
        if attempt > self.max_attempts:
            return RepairDecision(
                "too_many_attempts", attempt,
                f"已超过有界修复次数上限（{self.max_attempts}）",
                current_fingerprint=evidence_fingerprint(current),
            )
        if not has_new_evidence:
            return RepairDecision(
                "no_new_evidence", attempt,
                "没有新的失败证据（指纹与上次相同），不允许重复相同尝试",
                current_fingerprint=evidence_fingerprint(current),
            )
        return RepairDecision(
            "allow", attempt,
            f"出现新的失败证据（{current.category}），允许有界修复",
            previous_fingerprint=self._previous_fingerprint(),
            current_fingerprint=evidence_fingerprint(current),
        )

    def _previous_fingerprint(self) -> str:
        if len(self._entries) < 2:
            return ""
        return evidence_fingerprint(self._entries[-2])

    def has_new_evidence(self, evidence: VerificationEvidence) -> bool:
        """判断这条证据相对已登记证据是否构成「新证据」。

        新证据 = 绑定事实（命令/退出码/输出摘要/环境/产物哈希）发生了变化，
        而不是输出长度或文本细节变化。
        """
        fingerprint = evidence_fingerprint(evidence)
        return fingerprint not in self._seen_fingerprints
