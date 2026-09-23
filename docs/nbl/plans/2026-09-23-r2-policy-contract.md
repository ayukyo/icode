# R2.0 Sandbox Policy Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a versioned, fail-closed sandbox policy contract and one machine-readable ten-capability conformance contract that future Linux, macOS, and Windows helpers can consume without changing user-visible semantics.

**Architecture:** Add a standard-library-only `sandbox_policy` module as the single Python policy model, while publishing its wire shape as packaged JSON Schema. Add a separate `conformance` module and packaged JSON vector file for the ten cross-platform capabilities; expose only contract metadata through the existing capability report so R2.0 cannot be mistaken for an implemented native sandbox.

**Tech Stack:** Python 3.11+ standard library (`dataclasses`, `enum`, `hashlib`, `importlib.resources`, `json`, `pathlib`), JSON Schema documents, `unittest`, setuptools package data.

---

## File map

- `src/icode/sandbox_policy.py` — immutable policy model, canonical serialization, hash, validation, and monotonic tightening checks.
- `src/icode/schemas/sandbox-policy-v1.schema.json` — language-neutral wire contract for Python and future native helpers.
- `src/icode/conformance.py` — packaged contract loader, structural validation, and 90%/critical-capability scoring.
- `src/icode/conformance/sandbox-v1.json` — the ten user-visible capabilities and their negative-test identifiers.
- `src/icode/isolation.py` — adds policy/contract metadata to the existing honest capability report; does not change backend selection.
- `src/icode/cli.py` — prints R2 contract metadata in `icode doctor` without claiming native protection is ready.
- `pyproject.toml` — includes schema and conformance JSON files in built wheels.
- `tests/test_sandbox_policy.py` — policy construction, serialization, conflict, path, domain, and tightening tests.
- `tests/test_conformance.py` — vector loading, structural rejection, score thresholds, and critical-failure tests.
- `tests/test_isolation.py` — compatibility assertions for new report fields and unchanged backend truthfulness.
- `docs/roadmap.md` — records R2.0 as a contract milestone, while R2 native enforcement remains unaccepted.

### Task 1: Versioned immutable policy and JSON Schema

**状态**
- [x] 任务完成

**Dependencies:** None
**Parallelizable:** No (establishes the public types and wire contract used by every later task)

- [x] **Step 1: Write the failing construction and serialization tests**

Create `tests/test_sandbox_policy.py` with a temporary absolute workspace and this public API:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from icode.sandbox_policy import NetworkMode, SandboxPolicy


class SandboxPolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_policy(self, **overrides: object) -> SandboxPolicy:
        values: dict[str, object] = {
            "schema_version": 1,
            "run_id": "run-001",
            "ticket_id": "ICODE-24",
            "step": "code",
            "workspace_root": self.workspace,
            "read_roots": (self.workspace,),
            "write_roots": (self.workspace,),
            "deny_read_roots": (self.workspace / ".git",),
            "deny_write_roots": (self.workspace / ".git",),
            "network_mode": NetworkMode.DENY,
            "allowed_domains": (),
            "process_limit": 32,
            "wall_timeout_seconds": 600,
            "output_limit_bytes": 4 * 1024 * 1024,
            "protected_paths": (self.workspace / ".git",),
        }
        values.update(overrides)
        return SandboxPolicy(**values)

    def test_policy_is_immutable_and_normalizes_paths(self) -> None:
        policy = self.make_policy(read_roots=(self.workspace / ".", self.workspace))
        self.assertEqual(policy.read_roots, (self.workspace,))
        with self.assertRaisesRegex(Exception, "cannot assign"):
            policy.process_limit = 99  # type: ignore[misc]

    def test_canonical_json_and_hash_are_stable(self) -> None:
        first = self.make_policy()
        second = SandboxPolicy.from_dict(json.loads(first.canonical_json()))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.policy_hash, second.policy_hash)
        self.assertEqual(len(first.policy_hash), 64)

    def test_wire_shape_uses_strings_and_sorted_domains(self) -> None:
        policy = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("PYPI.org", "files.pythonhosted.org", "pypi.org"),
        )
        wire = policy.to_dict()
        self.assertEqual(wire["network_mode"], "proxy_allowlist")
        self.assertEqual(wire["allowed_domains"], ["files.pythonhosted.org", "pypi.org"])
        self.assertEqual(wire["workspace_root"], str(self.workspace))
```

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 -m unittest tests.test_sandbox_policy -v
```

Expected: import failure for `icode.sandbox_policy`, proving the tests cover a missing feature.

- [x] **Step 3: Implement the immutable model and canonical wire format**

Create `src/icode/sandbox_policy.py` with:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

POLICY_SCHEMA_VERSION = 1


class PolicyValidationError(ValueError):
    """The trusted runtime produced a sandbox policy that cannot be enforced safely."""


class NetworkMode(str, Enum):
    DENY = "deny"
    PROXY_ALLOWLIST = "proxy_allowlist"


def _normalize_paths(values: tuple[Path, ...]) -> tuple[Path, ...]:
    return tuple(sorted({Path(value).expanduser().resolve(strict=False) for value in values}, key=str))


@dataclass(frozen=True)
class SandboxPolicy:
    schema_version: int
    run_id: str
    ticket_id: str
    step: str
    workspace_root: Path
    read_roots: tuple[Path, ...]
    write_roots: tuple[Path, ...]
    deny_read_roots: tuple[Path, ...]
    deny_write_roots: tuple[Path, ...]
    network_mode: NetworkMode
    allowed_domains: tuple[str, ...]
    process_limit: int
    wall_timeout_seconds: int
    output_limit_bytes: int
    protected_paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_root", Path(self.workspace_root).expanduser().resolve(strict=False))
        for field_name in (
            "read_roots", "write_roots", "deny_read_roots",
            "deny_write_roots", "protected_paths",
        ):
            object.__setattr__(self, field_name, _normalize_paths(tuple(getattr(self, field_name))))
        # Public direct construction first requires the declared dataclass types;
        # from_dict performs validated wire conversions before reaching here.
        domains = tuple(sorted({item.lower() for item in self.allowed_domains}))
        object.__setattr__(self, "allowed_domains", domains)
        self.validate()

    def validate(self) -> None:
        # Task 2 replaces this minimal gate with the complete conflict checks.
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise PolicyValidationError(f"unsupported policy schema version: {self.schema_version}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "step": self.step,
            "workspace_root": str(self.workspace_root),
            "read_roots": [str(path) for path in self.read_roots],
            "write_roots": [str(path) for path in self.write_roots],
            "deny_read_roots": [str(path) for path in self.deny_read_roots],
            "deny_write_roots": [str(path) for path in self.deny_write_roots],
            "network_mode": self.network_mode.value,
            "allowed_domains": list(self.allowed_domains),
            "process_limit": self.process_limit,
            "wall_timeout_seconds": self.wall_timeout_seconds,
            "output_limit_bytes": self.output_limit_bytes,
            "protected_paths": [str(path) for path in self.protected_paths],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SandboxPolicy":
        expected = set(cls.__dataclass_fields__)
        unknown = set(value) - expected
        missing = expected - set(value)
        if unknown or missing:
            raise PolicyValidationError(
                f"policy fields mismatch: missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        path_lists = {
            name: tuple(Path(item) for item in value[name])
            for name in (
                "read_roots", "write_roots", "deny_read_roots",
                "deny_write_roots", "protected_paths",
            )
        }
        return cls(
            schema_version=value["schema_version"],
            run_id=value["run_id"],
            ticket_id=value["ticket_id"],
            step=value["step"],
            workspace_root=Path(value["workspace_root"]),
            network_mode=NetworkMode(value["network_mode"]),
            allowed_domains=tuple(value["allowed_domains"]),
            process_limit=value["process_limit"],
            wall_timeout_seconds=value["wall_timeout_seconds"],
            output_limit_bytes=value["output_limit_bytes"],
            **path_lists,
        )

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @property
    def policy_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
```

Create `src/icode/schemas/sandbox-policy-v1.schema.json` as a Draft 2020-12 object schema. It must set `additionalProperties` to `false`, require all fifteen dataclass fields, use integer `const: 1` for `schema_version`, constrain `network_mode` to `deny` or `proxy_allowlist`, require absolute non-empty path strings, require positive integer limits, and define domain items as external ASCII DNS hostnames without surrounding whitespace, a trailing dot, scheme, path, port, wildcard, localhost, IP literal, or 1-4-part legacy numeric IPv4 text. Public direct construction requires the declared dataclass types (`int` but not `bool`, `Path`, path tuples, `NetworkMode`, and domain string tuples); `from_dict` performs strict wire-shape checks and validated conversion before construction. Mixed-case DNS wire values are valid and the decoder canonicalizes them with `lower()` only; it never repairs untrusted input with `strip()` or `rstrip()`. The schema covers wire shape and constraints expressible in Draft 2020-12 only. The Python/native strict decoder is the authoritative complete semantic validator: it rejects non-`int` runtime values such as `True` and `1.0`, rejects strings that are not UTF-8-encodable Unicode scalar text, applies current-platform absolute-path semantics, and enforces cross-array containment, deny, and protected-path relationships. JSON Schema engines cannot consistently express the Unicode scalar boundary, so schema validation alone must never be described as complete policy acceptance.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the same focused command. Expected: 3 tests pass.

- [x] **Step 5: Commit the public policy contract**

```bash
git add src/icode/sandbox_policy.py src/icode/schemas/sandbox-policy-v1.schema.json tests/test_sandbox_policy.py
git commit -m "feat: add versioned sandbox policy contract"
```

### Task 2: Fail-closed conflicts and monotonic tightening

**状态**
- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (extends Task 1's validator and public policy API)

- [x] **Step 1: Add failing validation and tightening tests**

Extend `tests/test_sandbox_policy.py` with individual tests that assert:

```python
from dataclasses import replace

from icode.sandbox_policy import PolicyValidationError, tighten_policy


def test_unknown_fields_are_rejected(self) -> None:
    value = self.make_policy().to_dict()
    value["shell"] = True
    with self.assertRaisesRegex(PolicyValidationError, "unknown=.*shell"):
        SandboxPolicy.from_dict(value)

def test_deny_network_rejects_domains(self) -> None:
    with self.assertRaisesRegex(PolicyValidationError, "deny.*domains"):
        self.make_policy(allowed_domains=("pypi.org",))

def test_allowlist_requires_at_least_one_domain(self) -> None:
    with self.assertRaisesRegex(PolicyValidationError, "allowlist.*domain"):
        self.make_policy(network_mode=NetworkMode.PROXY_ALLOWLIST)

def test_url_and_wildcard_are_not_domains(self) -> None:
    for invalid in ("https://pypi.org", "*.pypi.org", "pypi.org/simple", "127.0.0.1"):
        with self.subTest(invalid=invalid):
            with self.assertRaises(PolicyValidationError):
                self.make_policy(
                    network_mode=NetworkMode.PROXY_ALLOWLIST,
                    allowed_domains=(invalid,),
                )

def test_write_root_must_stay_inside_workspace(self) -> None:
    with self.assertRaisesRegex(PolicyValidationError, "write root"):
        self.make_policy(write_roots=(self.workspace.parent,))

def test_limits_must_be_positive(self) -> None:
    for field in ("process_limit", "wall_timeout_seconds", "output_limit_bytes"):
        with self.subTest(field=field):
            with self.assertRaisesRegex(PolicyValidationError, field):
                self.make_policy(**{field: 0})

def test_protected_path_requires_a_deny_write_rule(self) -> None:
    with self.assertRaisesRegex(PolicyValidationError, "protected path"):
        self.make_policy(deny_read_roots=(self.workspace / ".git",), deny_write_roots=())

def test_tightening_can_reduce_paths_network_and_limits(self) -> None:
    base = self.make_policy(
        network_mode=NetworkMode.PROXY_ALLOWLIST,
        allowed_domains=("pypi.org", "files.pythonhosted.org"),
    )
    candidate = replace(
        base,
        write_roots=(self.workspace / "src",),
        network_mode=NetworkMode.DENY,
        allowed_domains=(),
        process_limit=8,
    )
    self.assertEqual(tighten_policy(base, candidate), candidate)

def test_tightening_rejects_added_write_root_domain_or_limit(self) -> None:
    base = self.make_policy(
        write_roots=(self.workspace / "src",),
        network_mode=NetworkMode.PROXY_ALLOWLIST,
        allowed_domains=("pypi.org",),
    )
    invalid = (
        replace(base, write_roots=(self.workspace,)),
        replace(base, allowed_domains=("pypi.org", "example.com")),
        replace(base, process_limit=base.process_limit + 1),
    )
    for candidate in invalid:
        with self.subTest(candidate=candidate):
            with self.assertRaisesRegex(PolicyValidationError, "broadens"):
                tighten_policy(base, candidate)
```

Also add tests for blank/control-character identifiers, a write root wholly inside a denied root, removing a base deny rule, and removing a protected path.

- [x] **Step 2: Run the focused tests and verify RED**

Run the Task 1 focused command. Expected: the new cases fail because the checks and `tighten_policy` do not exist.

- [x] **Step 3: Implement complete validation and tightening**

In `src/icode/sandbox_policy.py`:

- validate non-empty `run_id`, `ticket_id`, and `step`, rejecting ASCII control characters;
- validate positive limits;
- accept only exact DNS hostnames matching lowercase labels, reject IP literals, schemes, paths, ports, and wildcards;
- require all write roots to be at or below `workspace_root`;
- allow a deny path below an allow path because `.git` protection relies on deny precedence;
- reject an allow root that is itself at or below a deny root because it would be wholly unusable;
- require every protected path to be covered by a deny-write root; a deny-read root may additionally cover the same path but is never sufficient by itself;
- require `deny` to have no domains and `proxy_allowlist` to have at least one domain.

Add these helpers and API:

```python
def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _roots_are_no_broader(candidate: tuple[Path, ...], base: tuple[Path, ...]) -> bool:
    return all(any(_is_within(path, root) for root in base) for path in candidate)


def _denies_preserved(candidate: tuple[Path, ...], base: tuple[Path, ...]) -> bool:
    return all(any(_is_within(denied, candidate_root) for candidate_root in candidate) for denied in base)


def tighten_policy(base: SandboxPolicy, candidate: SandboxPolicy) -> SandboxPolicy:
    """Return candidate only when it cannot grant more authority than base."""
```

`tighten_policy` must require identical schema/run/ticket/step/workspace identity, no broader read or write roots, preservation or enlargement of deny roots and protected paths, equal-or-lower numeric limits, and no broader network access. Every rejection must raise `PolicyValidationError` with the word `broadens` so callers can classify it as `POLICY_INVALID` rather than asking users for more authority.

- [x] **Step 4: Run focused and isolation regression tests**

```bash
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 -m unittest tests.test_sandbox_policy tests.test_isolation -v
```

Expected: all policy and existing isolation tests pass.

- [x] **Step 5: Commit validation behavior**

```bash
git add src/icode/sandbox_policy.py tests/test_sandbox_policy.py
git commit -m "feat: enforce sandbox policy conflicts"
```

### Task 3: Machine-readable conformance vectors and scoring

**状态**
- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (the conformance contract must use the finalized R2.0 policy semantics)

- [x] **Step 1: Write failing contract and score tests**

Create `tests/test_conformance.py`:

```python
from __future__ import annotations

import unittest

from icode.conformance import (
    ConformanceContractError,
    evaluate_conformance,
    load_conformance_contract,
)


class TestConformanceContract(unittest.TestCase):
    def test_packaged_contract_has_ten_capabilities_and_eight_critical(self) -> None:
        contract = load_conformance_contract()
        self.assertEqual(contract["schema_version"], 1)
        self.assertEqual(contract["contract_id"], "icode-sandbox-v1")
        self.assertEqual(len(contract["capabilities"]), 10)
        self.assertEqual(sum(item["critical"] for item in contract["capabilities"]), 8)
        self.assertEqual(
            {item["id"] for item in contract["capabilities"]},
            {
                "workspace_write_boundary", "protected_paths", "sensitive_read_boundary",
                "network_default_deny", "network_temporary_allowlist", "child_inheritance",
                "process_tree_cleanup", "resource_limits", "uniform_violation", "doctor_self_test",
            },
        )

    def test_nine_of_ten_with_all_critical_is_ready(self) -> None:
        contract = load_conformance_contract()
        outcomes = {item["id"]: True for item in contract["capabilities"]}
        outcomes["resource_limits"] = False
        score = evaluate_conformance(outcomes)
        self.assertEqual(score["passed"], 9)
        self.assertEqual(score["total"], 10)
        self.assertTrue(score["critical_passed"])
        self.assertTrue(score["ready"])

    def test_critical_failure_is_never_ready(self) -> None:
        contract = load_conformance_contract()
        outcomes = {item["id"]: True for item in contract["capabilities"]}
        outcomes["network_default_deny"] = False
        score = evaluate_conformance(outcomes)
        self.assertEqual(score["passed"], 9)
        self.assertFalse(score["critical_passed"])
        self.assertFalse(score["ready"])

    def test_missing_or_unknown_result_is_rejected(self) -> None:
        with self.assertRaises(ConformanceContractError):
            evaluate_conformance({})
        contract = load_conformance_contract()
        outcomes = {item["id"]: True for item in contract["capabilities"]}
        outcomes["unknown"] = True
        with self.assertRaises(ConformanceContractError):
            evaluate_conformance(outcomes)
```

- [x] **Step 2: Run the focused tests and verify RED**

```bash
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 -m unittest tests.test_conformance -v
```

Expected: import failure for `icode.conformance`.

- [x] **Step 3: Add the packaged vectors and strict loader**

Create `src/icode/conformance/sandbox-v1.json` with `schema_version: 1`, `contract_id: "icode-sandbox-v1"`, `minimum_passed: 9`, and exactly the ten IDs from the test. Each capability object must contain only:

```json
{
  "id": "workspace_write_boundary",
  "critical": true,
  "description": "Writing outside the task workspace is blocked by the operating system",
  "negative_test": "write_outside_workspace"
}
```

Use the eight critical flags from section 14.1 of the approved R2 specification: every capability is critical except `resource_limits` and `uniform_violation`. Give every item a unique `negative_test` identifier matching section 14.2.

Create `src/icode/conformance.py` using `importlib.resources.files("icode").joinpath("conformance/sandbox-v1.json")`. `load_conformance_contract()` must return a fresh dictionary, reject unknown top-level or capability fields, reject duplicate IDs/test IDs, require exactly ten entries/eight critical entries/minimum nine, and raise `ConformanceContractError`. `evaluate_conformance()` must require an exact result-key match and actual `bool` values, then return:

```python
{
    "passed": passed,
    "total": 10,
    "critical_passed": critical_passed,
    "ready": passed >= 9 and critical_passed,
}
```

- [x] **Step 4: Package JSON resources and verify GREEN**

Change `pyproject.toml` package data to:

```toml
icode = ["web_assets/*", "workbench_assets/*", "schemas/*.json", "conformance/*.json"]
```

Run the focused tests. Expected: 4 tests pass.

- [x] **Step 5: Commit conformance contract**

```bash
git add pyproject.toml src/icode/conformance.py src/icode/conformance/sandbox-v1.json tests/test_conformance.py
git commit -m "feat: add sandbox conformance contract"
```

### Task 4: Honest capability-report integration, package verification, and stage record

**状态**
- [x] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (integrates and verifies all preceding artifacts)

- [x] **Step 1: Add failing compatibility assertions**

Extend `tests/test_isolation.py::TestHonesty.test_能力报告口径与所选后端一致`:

```python
self.assertEqual(report["policy_schema_version"], 1)
self.assertEqual(report["conformance_contract"]["id"], "icode-sandbox-v1")
self.assertEqual(report["conformance_contract"]["total"], 10)
self.assertEqual(report["conformance_contract"]["critical"], 8)
self.assertEqual(report["conformance_contract"]["minimum_passed"], 9)
self.assertFalse(report["conformance_contract"]["executed"])
```

Add a CLI test in `tests/test_offline.py` that invokes `cmd_doctor` with a temporary workspace and captured stdout, then asserts the output contains `R2 策略合同：v1` and `一致性测试：尚未执行`, while the existing sandbox label remains present.

- [x] **Step 2: Run the two focused suites and verify RED**

```bash
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 -m unittest tests.test_isolation tests.test_offline -v
```

Expected: report keys and doctor lines are missing.

- [x] **Step 3: Integrate metadata without changing backend selection**

Update `capability_report()` in `src/icode/isolation.py` to load the conformance contract and append:

```python
"policy_schema_version": POLICY_SCHEMA_VERSION,
"conformance_contract": {
    "id": contract["contract_id"],
    "total": len(contract["capabilities"]),
    "critical": sum(item["critical"] for item in contract["capabilities"]),
    "minimum_passed": contract["minimum_passed"],
    "executed": False,
},
```

Do not alter `select_sandbox()`, `honest_label`, or any backend `is_real_isolation` value. Update `cmd_doctor()` in `src/icode/cli.py` to print the contract version and explicitly state that native conformance has not run; this is informational and must not turn a WARN backend into OK.

- [x] **Step 4: Record the stage boundary in the roadmap**

Add an R2 section to `docs/roadmap.md` stating that R2.0 publishes policy/contract definitions only, native enforcement begins in R2.1–R2.4, and full R2 acceptance still requires all three platform matrices. Link the approved design and this implementation plan.

- [x] **Step 5: Run full verification and inspect the wheel**

```bash
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 -m compileall -q src tests
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 -m unittest
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 scripts/preflight.py
python3 scripts/check_site.py
python3 scripts/check_governance.py
git diff --check
```

Build a wheel outside the repository and inspect it without extracting:

```bash
wheel_dir=$(mktemp -d)
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 -m pip wheel . --no-deps --no-build-isolation --wheel-dir "$wheel_dir"
/home/orbbec/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 -c 'import sys, zipfile; p=sys.argv[1]; names=set(zipfile.ZipFile(p).namelist()); required={"icode/schemas/sandbox-policy-v1.schema.json", "icode/conformance/sandbox-v1.json"}; missing=required-names; assert not missing, missing; print("wheel resources present")' "$(find "$wheel_dir" -maxdepth 1 -name '*.whl' -print -quit)"
```

Expected: 3.11 tests and all repository checks pass; wheel inspection prints `wheel resources present`. If Python 3.12 is locally available, repeat the full unittest command with 3.12; otherwise rely on the pinned CI matrix after push and report that boundary.

- [x] **Step 6: Commit the completed R2.0 stage**

```bash
git add src/icode/isolation.py src/icode/cli.py tests/test_isolation.py tests/test_offline.py docs/roadmap.md docs/nbl/plans/2026-09-23-r2-policy-contract.md
git commit -m "feat: expose R2 policy contract status"
```

---
**Execution Mode:** serial
