"""失败分类、机器策略决策与无进展检测（R3 退出条件）。

真源是 `vendor/icode-skill` 的 `execution_model.failure_policies`（六类）。
本模块不复制上游策略表，只做三件事：

1. 把 ICODE 的稳定 `error_code` 映射到六类之一（未知一律按
   `ambiguous_side_effect` 处理：可能已生效但回执未知，先核对真实状态）；
2. 把 `control.policy` 的返回严格解析为有界决策；缺字段、类型不符或未知
   action 一律 fail-closed 成人工介入，绝不自行重试；
3. 用失败指纹识别“证据没变的重复尝试”，阻止同一失败无限重试。

没有任何策略通道时，可重试类降级为人工介入——宁可停下，也不靠猜测重试。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

FAILURE_CLASSES = frozenset({
    "retryable_transport",
    "capability_unavailable",
    "deterministic_failure",
    "policy_schema_security",
    "ambiguous_side_effect",
    "destructive_risk",
})

# 对外只有四态：retry / fallback / manual / stop。
ACTIONS = frozenset({"retry", "fallback", "manual", "stop"})

# 上游 policy.action 的原始取值；不在表内的一律降级人工介入。
_RAW_ACTIONS = frozenset({
    "retry",
    "fallback",
    "repair_then_retry",
    "verify_receipt",
    "human_decision",
    "block",
})

_CLASS_BY_ERROR = {
    # 环境/能力缺失：走声明过的 fallback，并降低结论上限。
    "isolation_unavailable": "capability_unavailable",
    "execution_unavailable": "capability_unavailable",
    "verification_plan_provider_failed": "capability_unavailable",
    "backend_error": "capability_unavailable",
    "status_unavailable": "capability_unavailable",
    # 权限、策略、schema、身份：立即阻断。
    "invalid_ticket": "policy_schema_security",
    "invalid_status": "policy_schema_security",
    "verification_plan_invalid": "policy_schema_security",
    "verification_plan_identity_mismatch": "policy_schema_security",
    "verification_plan_required": "policy_schema_security",
    # 稳定复现的执行失败：先修复再重试。
    "chain_failed": "deterministic_failure",
    "step_blocked": "deterministic_failure",
    "gate_blocked": "deterministic_failure",
    "executor_failed": "deterministic_failure",
    # 可能已生效但回执未知：先核对真实状态，禁止盲目重放。
    "chain_error": "ambiguous_side_effect",
    "executor_error": "ambiguous_side_effect",
    "no_progress_stuck": "ambiguous_side_effect",
}

# 同一失败指纹重复到该次数即判定无进展；第二次相同失败就停，不再试运气。
STUCK_THRESHOLD = 2
# 历史只保留最近的有限条，避免运行元数据无界增长。
HISTORY_LIMIT = 8


@dataclass(frozen=True)
class FailureDecision:
    """一次失败后的有界决策；只含稳定字段，不含命令/路径/异常正文。"""

    failure_class: str
    action: str
    auto_retry: bool = False
    max_attempts: int = 0
    backoff_seconds: float = 0.0
    conclusion_ceiling: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if self.failure_class not in FAILURE_CLASSES:
            raise ValueError("unknown failure class")
        if self.action not in ACTIONS:
            raise ValueError("unknown failure action")

    def to_public(self) -> dict[str, object]:
        return {
            "class": self.failure_class,
            "action": self.action,
            "auto_retry": self.auto_retry,
            "max_attempts": self.max_attempts,
            "conclusion_ceiling": self.conclusion_ceiling,
            "reason": self.reason,
        }


def classify_failure(error_code: object) -> str:
    """把稳定错误码归入上游六类；未知或非字符串按 ambiguous_side_effect。"""
    if not isinstance(error_code, str) or not error_code:
        return "ambiguous_side_effect"
    return _CLASS_BY_ERROR.get(error_code, "ambiguous_side_effect")


def failure_fingerprint(error_code: object, step: object) -> str:
    """无进展判定的稳定指纹：步骤 + 错误码，不含输出正文。"""
    step_token = step if isinstance(step, str) and step else "-"
    code_token = error_code if isinstance(error_code, str) and error_code else "-"
    return f"{step_token}:{code_token}"


def is_stuck(history: list[str] | tuple[str, ...], fingerprint: str, *,
             threshold: int = STUCK_THRESHOLD) -> bool:
    """同一指纹在最近 threshold-1 次尝试中全部出现即为无进展。"""
    if threshold < 2 or not isinstance(fingerprint, str) or not fingerprint:
        return False
    recent = list(history)[-(threshold - 1):]
    return len(recent) == threshold - 1 and all(item == fingerprint for item in recent)


def record_failure(history: list[str] | tuple[str, ...], fingerprint: str, *,
                   limit: int = HISTORY_LIMIT) -> list[str]:
    """追加指纹并截断到最近 limit 条；非法历史项先丢弃。"""
    kept = [item for item in history if isinstance(item, str)][-limit:]
    kept.append(fingerprint)
    return kept[-limit:]


def _parse_policy(policy: object) -> dict[str, object] | None:
    """严格解析 policy 载荷；任何畸形都返回 None，由调用方 fail-closed。"""
    if not isinstance(policy, dict):
        return None
    action = policy.get("action")
    ceiling = policy.get("conclusion_ceiling")
    auto_retry = policy.get("auto_retry")
    max_attempts = policy.get("max_attempts")
    backoff = policy.get("backoff_seconds")
    if not isinstance(action, str) or action not in _RAW_ACTIONS:
        return None
    if not isinstance(ceiling, str) or not ceiling:
        return None
    if not isinstance(auto_retry, bool):
        return None
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 0:
        return None
    if backoff is None:
        backoff_value = 0.0
    elif isinstance(backoff, (int, float)) and not isinstance(backoff, bool) and backoff >= 0:
        backoff_value = float(backoff)
    else:
        return None
    return {
        "action": action,
        "conclusion_ceiling": ceiling,
        "auto_retry": auto_retry,
        "max_attempts": max_attempts,
        "backoff_seconds": backoff_value,
    }


def decide_failure(
    failure_class: str,
    *,
    attempts: int,
    policy: object = None,
    allow_retry: bool = True,
) -> FailureDecision:
    """把失败分类与机器策略收敛成四态决策；缺策略时一律不自行重试。"""
    cls = failure_class if failure_class in FAILURE_CLASSES else "ambiguous_side_effect"
    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0:
        attempts = 0
    if cls == "policy_schema_security":
        return FailureDecision(cls, "stop", reason="策略/schema/安全门禁：立即阻断")
    if cls == "destructive_risk":
        return FailureDecision(cls, "manual", reason="破坏型动作：交人工决定")
    parsed = _parse_policy(policy)
    if parsed is None:
        # 没有可信策略通道：不自行重试，交给人工或修复流程。
        return FailureDecision(
            cls, "manual",
            reason="缺少可信机器策略：不自行重试，交人工或修复流程",
        )
    raw_action = str(parsed["action"])
    max_attempts = int(parsed["max_attempts"])
    auto_retry = bool(parsed["auto_retry"])
    backoff = float(parsed["backoff_seconds"])
    ceiling = str(parsed["conclusion_ceiling"])
    if raw_action == "block":
        return FailureDecision(cls, "stop", max_attempts=max_attempts,
                               conclusion_ceiling=ceiling, reason="机器策略要求阻断")
    if raw_action == "fallback":
        if not allow_retry:
            return FailureDecision(cls, "manual", max_attempts=max_attempts,
                                   conclusion_ceiling=ceiling,
                                   reason="降级路径被禁用：交人工决定")
        return FailureDecision(cls, "fallback", max_attempts=max_attempts,
                               conclusion_ceiling=ceiling, reason="机器策略允许降级")
    if raw_action == "retry":
        permitted = auto_retry and allow_retry and attempts < max_attempts
        if not permitted:
            reason = ("重试预算已用尽" if attempts >= max_attempts
                      else "策略或调用方不允许自动重试")
            return FailureDecision(cls, "manual", auto_retry=auto_retry,
                                   max_attempts=max_attempts,
                                   conclusion_ceiling=ceiling, reason=reason)
        return FailureDecision(cls, "retry", auto_retry=True,
                               max_attempts=max_attempts,
                               backoff_seconds=backoff,
                               conclusion_ceiling=ceiling,
                               reason="机器策略允许有界重试")
    # repair_then_retry / verify_receipt / human_decision 都要求先产生新证据或人工决定。
    reason = {
        "repair_then_retry": "先修复并产生新证据，再决定是否重试",
        "verify_receipt": "先核对真实状态，禁止盲目重放",
        "human_decision": "交人工决定",
    }[raw_action]
    return FailureDecision(cls, "manual", max_attempts=max_attempts,
                           conclusion_ceiling=ceiling, reason=reason)


def stop_for_no_progress(decision: FailureDecision) -> FailureDecision:
    """无进展优先于策略：同一失败证据重复出现时直接停。"""
    if decision.action == "stop":
        return decision
    return replace(decision, action="stop", auto_retry=False,
                   reason="相同失败证据重复出现：无进展，停止并交人工")
