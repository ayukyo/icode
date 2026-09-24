"""Machine-readable sandbox conformance contract tests."""

from __future__ import annotations

import copy
import unittest

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.conformance import (
    ConformanceContractError,
    evaluate_conformance,
    evaluate_platform_conformance,
    load_conformance_contract,
    validate_conformance_contract,
)


CAPABILITY_IDS = {
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

NEGATIVE_TESTS = {
    "write_outside_workspace",
    "write_protected_path",
    "read_sensitive_path",
    "direct_network_access",
    "temporary_domain_expiry",
    "child_process_escape",
    "process_tree_residue",
    "resource_limit_overrun",
    "uniform_violation_receipt",
    "doctor_backend_self_test",
}


class ConformanceContractTestCase(unittest.TestCase):
    def make_outcomes(self) -> dict[str, bool]:
        return {capability_id: True for capability_id in CAPABILITY_IDS}

    def test_packaged_contract_has_exact_v1_capabilities(self) -> None:
        contract = load_conformance_contract()

        self.assertEqual(
            set(contract),
            {"schema_version", "contract_id", "minimum_passed", "capabilities"},
        )
        self.assertEqual(contract["schema_version"], 1)
        self.assertEqual(contract["contract_id"], "icode-sandbox-v1")
        self.assertEqual(contract["minimum_passed"], 9)
        capabilities = contract["capabilities"]
        self.assertEqual(len(capabilities), 10)
        self.assertEqual(
            {capability["id"] for capability in capabilities},
            CAPABILITY_IDS,
        )
        self.assertEqual(
            {capability["negative_test"] for capability in capabilities},
            NEGATIVE_TESTS,
        )
        self.assertEqual(
            sum(capability["critical"] for capability in capabilities),
            8,
        )
        self.assertEqual(
            {
                capability["id"]
                for capability in capabilities
                if not capability["critical"]
            },
            {"resource_limits", "uniform_violation"},
        )
        for capability in capabilities:
            self.assertEqual(
                set(capability),
                {"id", "critical", "description", "negative_test"},
            )
            self.assertTrue(capability["description"].strip())

    def test_loader_returns_fresh_data(self) -> None:
        first = load_conformance_contract()
        first["capabilities"][0]["description"] = "changed"

        second = load_conformance_contract()

        self.assertNotEqual(second["capabilities"][0]["description"], "changed")

    def test_capability_rejects_arbitrary_unique_negative_test(self) -> None:
        contract = copy.deepcopy(load_conformance_contract())
        contract["capabilities"][0]["negative_test"] = "arbitrary_unique_test"

        with self.assertRaises(ConformanceContractError):
            validate_conformance_contract(contract)

    def test_capability_rejects_swapped_negative_tests(self) -> None:
        contract = copy.deepcopy(load_conformance_contract())
        first = contract["capabilities"][0]
        second = contract["capabilities"][1]
        first["negative_test"], second["negative_test"] = (
            second["negative_test"],
            first["negative_test"],
        )

        with self.assertRaises(ConformanceContractError):
            validate_conformance_contract(contract)

    def test_contract_and_capability_keys_must_be_strings(self) -> None:
        malformed_contract = copy.deepcopy(load_conformance_contract())
        malformed_contract[1] = "integer key"
        malformed_contract[None] = "null key"

        malformed_capability = copy.deepcopy(load_conformance_contract())
        malformed_capability["capabilities"][0][1] = "integer key"
        malformed_capability["capabilities"][0][None] = "null key"

        for location, contract in (
            ("contract", malformed_contract),
            ("capability", malformed_capability),
        ):
            with self.subTest(location=location):
                with self.assertRaisesRegex(
                    ConformanceContractError,
                    r"keys must be strings",
                ):
                    validate_conformance_contract(contract)

    def test_optional_failure_still_meets_readiness_threshold(self) -> None:
        outcomes = self.make_outcomes()
        outcomes["resource_limits"] = False

        self.assertEqual(
            evaluate_conformance(outcomes),
            {
                "passed": 9,
                "total": 10,
                "critical_passed": True,
                "ready": True,
            },
        )

    def test_critical_failure_prevents_readiness(self) -> None:
        outcomes = self.make_outcomes()
        outcomes["network_default_deny"] = False

        self.assertEqual(
            evaluate_conformance(outcomes),
            {
                "passed": 9,
                "total": 10,
                "critical_passed": False,
                "ready": False,
            },
        )

    def test_macos_scoped_cleanup_exception_requires_real_group_evidence(self) -> None:
        outcomes = self.make_outcomes()
        outcomes["process_tree_cleanup"] = False

        strict = evaluate_conformance(outcomes)
        self.assertFalse(strict["ready"])
        self.assertFalse(strict["critical_passed"])
        report = evaluate_platform_conformance(
            outcomes, platform="macos", process_group_cleanup=True,
        )
        self.assertEqual(report["passed"], 9)
        self.assertFalse(report["critical_passed"])
        self.assertTrue(report["platform_critical_passed"])
        self.assertEqual(report["exception"], "macos_process_group_only")
        self.assertTrue(report["ready"])

        without_group = evaluate_platform_conformance(
            outcomes, platform="macos", process_group_cleanup=False,
        )
        self.assertFalse(without_group["platform_critical_passed"])
        self.assertFalse(without_group["ready"])

        outcomes["process_tree_cleanup"] = True
        contradictory = evaluate_platform_conformance(
            outcomes, platform="macos", process_group_cleanup=False,
        )
        self.assertFalse(contradictory["ready"])
        self.assertIsNone(contradictory["exception"])

    def test_macos_exception_does_not_waive_other_critical_or_90_percent(self) -> None:
        outcomes = self.make_outcomes()
        outcomes["process_tree_cleanup"] = False
        outcomes["network_default_deny"] = False
        self.assertFalse(evaluate_platform_conformance(
            outcomes, platform="macos", process_group_cleanup=True,
        )["ready"])
        outcomes["network_default_deny"] = True
        outcomes["resource_limits"] = False
        self.assertFalse(evaluate_platform_conformance(
            outcomes, platform="macos", process_group_cleanup=True,
        )["ready"])

    def test_other_platforms_retain_full_tree_requirement(self) -> None:
        outcomes = self.make_outcomes()
        outcomes["process_tree_cleanup"] = False
        for platform in ("linux", "windows"):
            with self.subTest(platform=platform):
                report = evaluate_platform_conformance(outcomes, platform=platform)
                self.assertFalse(report["ready"])
                self.assertIsNone(report["exception"])
        with self.assertRaises(ConformanceContractError):
            evaluate_platform_conformance(
                outcomes, platform="linux", process_group_cleanup=True,
            )

    def test_macos_group_evidence_must_be_explicit_boolean(self) -> None:
        outcomes = self.make_outcomes()
        for evidence in (None, 1, "true"):
            with self.subTest(evidence=evidence):
                with self.assertRaises(ConformanceContractError):
                    evaluate_platform_conformance(
                        outcomes, platform="macos", process_group_cleanup=evidence,
                    )
        with self.assertRaises(ConformanceContractError):
            evaluate_platform_conformance(outcomes, platform="unknown")

    def test_outcome_keys_must_match_capabilities_exactly(self) -> None:
        missing = self.make_outcomes()
        del missing["doctor_self_test"]
        extra = self.make_outcomes()
        extra["unknown_capability"] = True

        for outcomes in (missing, extra):
            with self.subTest(keys=set(outcomes)):
                with self.assertRaises(ConformanceContractError):
                    evaluate_conformance(outcomes)

    def test_outcome_values_must_be_real_booleans(self) -> None:
        for value in (1, 0, "true"):
            outcomes: dict[str, object] = self.make_outcomes()
            outcomes["resource_limits"] = value

            with self.subTest(value=value):
                with self.assertRaises(ConformanceContractError):
                    evaluate_conformance(outcomes)  # type: ignore[arg-type]

    def test_outcome_keys_must_be_strings(self) -> None:
        outcomes: dict[object, object] = self.make_outcomes()
        outcomes[1] = True
        outcomes[None] = False

        with self.assertRaisesRegex(
            ConformanceContractError,
            r"keys must be strings",
        ):
            evaluate_conformance(outcomes)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
