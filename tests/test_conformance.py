"""Machine-readable sandbox conformance contract tests."""

from __future__ import annotations

import copy
import unittest

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.conformance import (
    ConformanceContractError,
    evaluate_conformance,
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


if __name__ == "__main__":
    unittest.main()
