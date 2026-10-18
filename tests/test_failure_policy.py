"""失败分类、机器策略决策与无进展检测的纯函数测试（R3 退出条件）。"""

from __future__ import annotations

import unittest

from icode.failure_policy import (
    ACTIONS,
    FAILURE_CLASSES,
    STUCK_THRESHOLD,
    FailureDecision,
    classify_failure,
    decide_failure,
    failure_fingerprint,
    is_stuck,
    record_failure,
    stop_for_no_progress,
)


def _policy(**overrides):
    base = {
        "action": "retry",
        "max_attempts": 3,
        "backoff_seconds": 1,
        "conclusion_ceiling": "degraded",
        "auto_retry": True,
    }
    base.update(overrides)
    return base


class TestFailureClassification(unittest.TestCase):
    def test_稳定错误码映射到上游六类(self) -> None:
        expected = {
            "isolation_unavailable": "capability_unavailable",
            "execution_unavailable": "capability_unavailable",
            "verification_plan_provider_failed": "capability_unavailable",
            "backend_error": "capability_unavailable",
            "status_unavailable": "capability_unavailable",
            "invalid_ticket": "policy_schema_security",
            "invalid_status": "policy_schema_security",
            "verification_plan_invalid": "policy_schema_security",
            "verification_plan_identity_mismatch": "policy_schema_security",
            "verification_plan_required": "policy_schema_security",
            "chain_failed": "deterministic_failure",
            "step_blocked": "deterministic_failure",
            "gate_blocked": "deterministic_failure",
            "executor_failed": "deterministic_failure",
            "chain_error": "ambiguous_side_effect",
            "executor_error": "ambiguous_side_effect",
        }
        for code, failure_class in expected.items():
            with self.subTest(code=code):
                self.assertEqual(classify_failure(code), failure_class)

    def test_未知或非字符串一律按回执未知处理(self) -> None:
        for value in ("", None, 7, "some_new_code"):
            with self.subTest(value=value):
                self.assertEqual(classify_failure(value), "ambiguous_side_effect")

    def test_指纹只含步骤与稳定错误码(self) -> None:
        self.assertEqual(failure_fingerprint("chain_failed", "deepcheck"),
                         "deepcheck:chain_failed")
        self.assertEqual(failure_fingerprint("chain_failed", None), "-:chain_failed")
        self.assertEqual(failure_fingerprint(None, "code"), "code:-")


class TestFailureDecision(unittest.TestCase):
    def test_没有策略通道时不自行重试(self) -> None:
        for failure_class in ("retryable_transport", "capability_unavailable",
                              "deterministic_failure", "ambiguous_side_effect"):
            with self.subTest(failure_class=failure_class):
                decision = decide_failure(failure_class, attempts=1, policy=None)
                self.assertEqual(decision.action, "manual")
                self.assertFalse(decision.auto_retry)

    def test_安全与破坏类不依赖策略(self) -> None:
        security = decide_failure("policy_schema_security", attempts=0, policy=_policy())
        self.assertEqual(security.action, "stop")
        destructive = decide_failure("destructive_risk", attempts=0, policy=_policy())
        self.assertEqual(destructive.action, "manual")

    def test_策略允许且在预算内才重试(self) -> None:
        allowed = decide_failure("retryable_transport", attempts=1, policy=_policy())
        self.assertEqual(allowed.action, "retry")
        self.assertTrue(allowed.auto_retry)
        self.assertEqual(allowed.backoff_seconds, 1.0)
        exhausted = decide_failure("retryable_transport", attempts=3, policy=_policy())
        self.assertEqual(exhausted.action, "manual")
        no_auto = decide_failure("retryable_transport", attempts=1,
                                 policy=_policy(auto_retry=False))
        self.assertEqual(no_auto.action, "manual")
        caller_denied = decide_failure("retryable_transport", attempts=1,
                                       policy=_policy(), allow_retry=False)
        self.assertEqual(caller_denied.action, "manual")

    def test_其余上游动作收敛为有界决策(self) -> None:
        cases = {
            "fallback": "fallback",
            "block": "stop",
            "repair_then_retry": "manual",
            "verify_receipt": "manual",
            "human_decision": "manual",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                decision = decide_failure("deterministic_failure", attempts=0,
                                          policy=_policy(action=raw))
                self.assertEqual(decision.action, expected)

    def test_畸形策略一律降级人工介入(self) -> None:
        broken = [
            None, {}, {"action": "retry"},
            _policy(action="arbitrary"),
            _policy(auto_retry="yes"),
            _policy(max_attempts=-1),
            _policy(max_attempts=True),
            _policy(backoff_seconds="soon"),
            _policy(conclusion_ceiling=""),
        ]
        for payload in broken:
            with self.subTest(payload=payload):
                decision = decide_failure("retryable_transport", attempts=0, policy=payload)
                self.assertEqual(decision.action, "manual")
                self.assertFalse(decision.auto_retry)

    def test_决策只允许四态与六类(self) -> None:
        self.assertEqual(ACTIONS, frozenset({"retry", "fallback", "manual", "stop"}))
        self.assertEqual(len(FAILURE_CLASSES), 6)
        with self.assertRaises(ValueError):
            FailureDecision("unknown_class", "manual")
        with self.assertRaises(ValueError):
            FailureDecision("deterministic_failure", "proceed")

    def test_公开投影只含稳定字段(self) -> None:
        decision = decide_failure("retryable_transport", attempts=1, policy=_policy())
        public = decision.to_public()
        self.assertEqual(set(public), {
            "class", "action", "auto_retry", "max_attempts",
            "conclusion_ceiling", "reason",
        })
        self.assertNotIn("command", public)
        self.assertNotIn("output", public)


class TestNoProgress(unittest.TestCase):
    def test_相同指纹第二次即判无进展(self) -> None:
        # history 只含既往尝试；最近一次与本次相同即第二次重复。
        self.assertEqual(STUCK_THRESHOLD, 2)
        self.assertFalse(is_stuck([], "plan:chain_failed"))
        self.assertTrue(is_stuck(["plan:chain_failed"], "plan:chain_failed"))
        self.assertTrue(is_stuck(["plan:chain_failed", "plan:chain_failed"],
                                 "plan:chain_failed"))

    def test_不同证据不算无进展(self) -> None:
        self.assertFalse(is_stuck(["plan:chain_failed"], "code:chain_failed"))
        self.assertTrue(is_stuck(["plan:chain_failed", "code:chain_failed"],
                                 "code:chain_failed"))

    def test_历史有界且丢弃非法项(self) -> None:
        history = ["a:1"] * 20 + [7, None]  # type: ignore[list-item]
        recorded = record_failure(history, "b:2", limit=8)
        self.assertEqual(len(recorded), 8)
        self.assertEqual(recorded[-1], "b:2")
        self.assertTrue(all(isinstance(item, str) for item in recorded))

    def test_无进展优先于策略动作(self) -> None:
        retry = decide_failure("retryable_transport", attempts=1, policy=_policy())
        self.assertEqual(retry.action, "retry")
        stopped = stop_for_no_progress(retry)
        self.assertEqual(stopped.action, "stop")
        self.assertFalse(stopped.auto_retry)
        self.assertIn("无进展", stopped.reason)
        self.assertEqual(stop_for_no_progress(stopped), stopped)


if __name__ == "__main__":
    unittest.main()
