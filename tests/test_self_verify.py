"""R3 自验证与有界修复测试（离线、零依赖）。"""

from __future__ import annotations

import json
import unittest

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.self_verify import (
    AUTO_REPAIRABLE_CATEGORIES,
    FAILURE_CATEGORIES,
    FAILURE_CODE,
    FAILURE_CONTRACT,
    FAILURE_ENVIRONMENT,
    FAILURE_MODEL_CAPABILITY,
    FAILURE_SIDE_EFFECT_UNKNOWN,
    FAILURE_TEST,
    VerificationEvidence,
    VerificationLedger,
    classify_failure,
    environment_fingerprint,
    evidence_fingerprint,
)


class FailureClassificationTestCase(unittest.TestCase):
    def test_exit_127_is_environment(self) -> None:
        self.assertEqual(
            classify_failure(exit_code=127, output="sh: x: command not found"),
            FAILURE_ENVIRONMENT,
        )

    def test_module_not_found_is_environment(self) -> None:
        self.assertEqual(
            classify_failure(exit_code=1, output="ModuleNotFoundError: No module named 'x'"),
            FAILURE_ENVIRONMENT,
        )

    def test_test_assertion_failure_is_code(self) -> None:
        self.assertEqual(
            classify_failure(exit_code=1, kind="test",
                             output="FAIL: test_calc\nAssertionError: 0 != 1"),
            FAILURE_CODE,
        )

    def test_test_collection_error_is_test(self) -> None:
        self.assertEqual(
            classify_failure(exit_code=2, kind="test",
                             output="ERROR: failed to collect test_calc.py"),
            FAILURE_TEST,
        )

    def test_missing_artifact_is_contract(self) -> None:
        self.assertEqual(
            classify_failure(exit_code=1, output="产物缺失 01_plan.md",
                             missing_artifacts=("01_plan.md",)),
            FAILURE_CONTRACT,
        )

    def test_json_parse_failed_is_model_capability(self) -> None:
        self.assertEqual(
            classify_failure(exit_code=1, output="no json",
                             json_parse_failed=True),
            FAILURE_MODEL_CAPABILITY,
        )

    def test_ambiguous_side_effect_is_fail_safe(self) -> None:
        self.assertEqual(
            classify_failure(exit_code=1, output="anything",
                             ambiguous_side_effect=True),
            FAILURE_SIDE_EFFECT_UNKNOWN,
        )

    def test_unknown_command_failure_defaults_to_code(self) -> None:
        self.assertEqual(
            classify_failure(exit_code=1, kind="command", output="exit 1"),
            FAILURE_CODE,
        )

    def test_categories_are_exact_six(self) -> None:
        self.assertEqual(
            set(FAILURE_CATEGORIES),
            {
                FAILURE_ENVIRONMENT, FAILURE_CODE, FAILURE_TEST,
                FAILURE_CONTRACT, FAILURE_MODEL_CAPABILITY,
                FAILURE_SIDE_EFFECT_UNKNOWN,
            },
        )

    def test_auto_repairable_subset(self) -> None:
        self.assertTrue(FAILURE_CODE in AUTO_REPAIRABLE_CATEGORIES)
        self.assertTrue(FAILURE_TEST in AUTO_REPAIRABLE_CATEGORIES)
        self.assertTrue(FAILURE_SIDE_EFFECT_UNKNOWN not in AUTO_REPAIRABLE_CATEGORIES)


class EvidenceFingerprintTestCase(unittest.TestCase):
    def make(self, **overrides) -> VerificationEvidence:
        base: dict = dict(
            step="code", attempt="1", kind="test",
            command=("python", "-m", "unittest"), exit_code=1,
            output="AssertionError", environment_fingerprint="env-1",
            artifact_hashes={"calc.py": "abc"},
        )
        base.update(overrides)
        return VerificationEvidence(**base)

    def test_same_facts_same_fingerprint(self) -> None:
        self.assertEqual(
            evidence_fingerprint(self.make()),
            evidence_fingerprint(self.make()),
        )

    def test_output_change_changes_fingerprint(self) -> None:
        self.assertNotEqual(
            evidence_fingerprint(self.make(output="AssertionError A")),
            evidence_fingerprint(self.make(output="AssertionError B")),
        )

    def test_exit_code_change_changes_fingerprint(self) -> None:
        self.assertNotEqual(
            evidence_fingerprint(self.make(exit_code=1)),
            evidence_fingerprint(self.make(exit_code=2)),
        )

    def test_artifact_hash_change_changes_fingerprint(self) -> None:
        self.assertNotEqual(
            evidence_fingerprint(self.make(artifact_hashes={"calc.py": "abc"})),
            evidence_fingerprint(self.make(artifact_hashes={"calc.py": "def"})),
        )

    def test_fingerprint_does_not_contain_secret_or_full_output(self) -> None:
        fp = evidence_fingerprint(self.make(output="secret-token-should-not-leak"))
        self.assertNotIn("secret-token-should-not-leak", fp)
        self.assertNotIn("secret-token-should-not-leak", self.make(output="x").output_sha256)

    def test_receipt_binds_facts_without_full_output(self) -> None:
        evidence = self.make(
            output="traceback secret-token-should-not-leak",
            artifact_hashes={"calc.py": "abc"},
            environment_fingerprint="env-1",
        )
        receipt = evidence.to_receipt()
        self.assertEqual(receipt["kind"], "verification")
        self.assertEqual(receipt["step"], "code")
        self.assertEqual(receipt["exit_code"], 1)
        self.assertEqual(receipt["command"], ["python", "-m", "unittest"])
        self.assertEqual(receipt["environment_fingerprint"], "env-1")
        self.assertEqual(receipt["artifact_hashes"], {"calc.py": "abc"})
        self.assertTrue(receipt["output_sha256"])
        self.assertEqual(receipt["fingerprint"], evidence_fingerprint(evidence))
        # 回执不得包含输出正文或敏感内容
        self.assertNotIn("secret-token-should-not-leak", json.dumps(receipt))
        self.assertNotIn("traceback", receipt["command"])


class VerificationLedgerTestCase(unittest.TestCase):
    def make(self, **overrides) -> VerificationEvidence:
        base: dict = dict(
            step="code", attempt="1", kind="test",
            command=("python", "-m", "unittest"), exit_code=1,
            output="AssertionError", environment_fingerprint="env-1",
            category=FAILURE_CODE,
        )
        base.update(overrides)
        return VerificationEvidence(**base)

    def test_first_repair_with_new_evidence_is_allowed(self) -> None:
        ledger = VerificationLedger()
        decision = ledger.decide_repair(self.make(), has_new_evidence=True)
        self.assertEqual(decision.action, "allow")
        self.assertEqual(ledger.attempts, 1)

    def test_identical_repeat_is_no_new_evidence(self) -> None:
        ledger = VerificationLedger()
        first = ledger.decide_repair(self.make(), has_new_evidence=True)
        self.assertEqual(first.action, "allow")
        second = ledger.decide_repair(self.make(), has_new_evidence=False)
        self.assertEqual(second.action, "no_new_evidence")

    def test_changed_output_is_new_evidence(self) -> None:
        ledger = VerificationLedger()
        ledger.decide_repair(self.make(output="AssertionError A"), has_new_evidence=True)
        decision = ledger.decide_repair(
            self.make(output="AssertionError B"), has_new_evidence=True)
        self.assertEqual(decision.action, "allow")

    def test_side_effect_unknown_is_human_even_first(self) -> None:
        ledger = VerificationLedger()
        decision = ledger.decide_repair(
            self.make(category=FAILURE_SIDE_EFFECT_UNKNOWN), has_new_evidence=True)
        self.assertEqual(decision.action, "human")

    def test_max_attempts_is_bounded(self) -> None:
        ledger = VerificationLedger(max_attempts=2)
        ledger.decide_repair(self.make(output="A"), has_new_evidence=True)
        ledger.decide_repair(self.make(output="B"), has_new_evidence=True)
        decision = ledger.decide_repair(self.make(output="C"), has_new_evidence=True)
        self.assertEqual(decision.action, "too_many_attempts")

    def test_has_new_evidence_detects_change(self) -> None:
        ledger = VerificationLedger()
        self.assertTrue(ledger.has_new_evidence(self.make(output="A")))
        ledger.record(self.make(output="A"))
        self.assertFalse(ledger.has_new_evidence(self.make(output="A")))
        self.assertTrue(ledger.has_new_evidence(self.make(output="B")))

    def test_record_assigns_increasing_attempt(self) -> None:
        ledger = VerificationLedger()
        ledger.record(self.make())
        ledger.record(self.make(output="B"))
        self.assertEqual([e.attempt for e in ledger._entries], ["1", "2"])

    def test_invalid_max_attempts_rejected(self) -> None:
        with self.assertRaises(ValueError):
            VerificationLedger(max_attempts=0)

    def test_environment_fingerprint_is_stable(self) -> None:
        self.assertTrue(environment_fingerprint())
        self.assertEqual(environment_fingerprint(), environment_fingerprint())


if __name__ == "__main__":
    unittest.main()
