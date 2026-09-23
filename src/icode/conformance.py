"""Load and score the platform-neutral sandbox conformance contract.

This module evaluates supplied outcomes only. It does not probe a platform or
apply sandbox protections.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any


_TOP_LEVEL_FIELDS = {
    "schema_version",
    "contract_id",
    "minimum_passed",
    "capabilities",
}
_CAPABILITY_FIELDS = {"id", "critical", "description", "negative_test"}
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
_NON_CRITICAL_IDS = {"resource_limits", "uniform_violation"}


class ConformanceContractError(ValueError):
    """Raised when the conformance contract or supplied outcomes are invalid."""


def _require_exact_fields(
    value: Mapping[str, Any],
    expected: set[str],
    location: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ConformanceContractError(
            f"{location} fields do not match contract: "
            f"missing={missing!r}, unknown={unknown!r}"
        )


def _require_non_blank_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConformanceContractError(f"{location} must be non-blank text")
    return value


def _validate_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConformanceContractError("conformance contract must be an object")
    _require_exact_fields(value, _TOP_LEVEL_FIELDS, "contract")

    schema_version = value["schema_version"]
    if type(schema_version) is not int or schema_version != 1:
        raise ConformanceContractError("schema_version must be integer 1")
    if value["contract_id"] != "icode-sandbox-v1":
        raise ConformanceContractError("contract_id must be 'icode-sandbox-v1'")
    if (
        type(value["minimum_passed"]) is not int
        or value["minimum_passed"] != 9
    ):
        raise ConformanceContractError("minimum_passed must be integer 9")

    capabilities = value["capabilities"]
    if not isinstance(capabilities, list) or len(capabilities) != 10:
        raise ConformanceContractError("capabilities must contain exactly 10 items")

    capability_ids: list[str] = []
    negative_tests: list[str] = []
    critical_ids: set[str] = set()
    for index, capability in enumerate(capabilities):
        location = f"capabilities[{index}]"
        if not isinstance(capability, dict):
            raise ConformanceContractError(f"{location} must be an object")
        _require_exact_fields(capability, _CAPABILITY_FIELDS, location)

        capability_id = _require_non_blank_text(
            capability["id"], f"{location}.id"
        )
        negative_test = _require_non_blank_text(
            capability["negative_test"], f"{location}.negative_test"
        )
        _require_non_blank_text(
            capability["description"], f"{location}.description"
        )
        if type(capability["critical"]) is not bool:
            raise ConformanceContractError(f"{location}.critical must be a bool")

        capability_ids.append(capability_id)
        negative_tests.append(negative_test)
        if capability["critical"]:
            critical_ids.add(capability_id)

    if len(set(capability_ids)) != len(capability_ids):
        raise ConformanceContractError("capability ids must be unique")
    if len(set(negative_tests)) != len(negative_tests):
        raise ConformanceContractError("negative_test values must be unique")
    if set(capability_ids) != _CAPABILITY_IDS:
        raise ConformanceContractError("capability ids do not match sandbox-v1")
    if len(critical_ids) != 8:
        raise ConformanceContractError("exactly 8 capabilities must be critical")
    if critical_ids != _CAPABILITY_IDS - _NON_CRITICAL_IDS:
        raise ConformanceContractError(
            "only resource_limits and uniform_violation may be non-critical"
        )

    return value


def load_conformance_contract() -> dict[str, Any]:
    """Load and validate a fresh copy of the packaged sandbox-v1 contract."""

    resource = files("icode").joinpath("conformance/sandbox-v1.json")
    try:
        value = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConformanceContractError(
            "unable to load the packaged conformance contract"
        ) from error
    return _validate_contract(value)


def evaluate_conformance(outcomes: Mapping[str, bool]) -> dict[str, int | bool]:
    """Score exact capability outcomes against the packaged contract."""

    if not isinstance(outcomes, Mapping):
        raise ConformanceContractError("outcomes must be a mapping")

    contract = load_conformance_contract()
    capabilities = contract["capabilities"]
    capability_ids = {capability["id"] for capability in capabilities}
    outcome_ids = set(outcomes)
    if outcome_ids != capability_ids:
        missing = sorted(capability_ids - outcome_ids)
        unknown = sorted(outcome_ids - capability_ids)
        raise ConformanceContractError(
            "outcome ids do not match contract: "
            f"missing={missing!r}, unknown={unknown!r}"
        )

    for capability_id, value in outcomes.items():
        if type(value) is not bool:
            raise ConformanceContractError(
                f"outcome for {capability_id!r} must be a bool"
            )

    passed = sum(outcomes[capability_id] for capability_id in capability_ids)
    critical_passed = all(
        outcomes[capability["id"]]
        for capability in capabilities
        if capability["critical"]
    )
    ready = passed >= contract["minimum_passed"] and critical_passed
    return {
        "passed": passed,
        "total": len(capabilities),
        "critical_passed": critical_passed,
        "ready": ready,
    }
