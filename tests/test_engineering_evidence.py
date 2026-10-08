"""Engineering receipt contracts; scope fixtures are not native acceptance."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from tests._support import make_finished_plan_ticket, require_skill, temp_workspace
from icode.engineering_verification import (
    EngineeringCheckResult, EngineeringVerificationRun, VerificationCheck,
    VerificationPlan, execute_verification_plan,
)
from icode.self_verify import VerificationEvidence, VerificationLedger, evidence_fingerprint
from icode.tools import ToolContext
from icode.isolation import NoIsolation


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class _Helpers:
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("icode.engineering_evidence"))
        return importlib.import_module("icode.engineering_evidence")

    def plan(self, root, *, two=False):
        checks = [VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"),
                                    "unittest_summary_v1", timeout_seconds=5, output_limit_bytes=65536)]
        if two:
            checks.insert(0, VerificationCheck("lint", "lint", (sys.executable, "-B", "-c", "pass"),
                                              "exit_status_v1", timeout_seconds=5, output_limit_bytes=65536))
        return VerificationPlan(root.resolve(), "eng-run", "EV-1", tuple(checks))

    def observed_run(self, plan, *, output=b"Ran 1 test in 0.001s\n\nOK\n", failed=False):
        # Closed transport observations only; these values do not demonstrate
        # that this fixture exercised a native task scope.
        checks = tuple(EngineeringCheckResult(
            c.check_id, "failed" if failed and c.kind == "test" else "passed",
            exit_code=1 if failed and c.kind == "test" else 0,
            tests_passed=0 if failed or c.kind != "test" else 1,
            output=output if c.kind == "test" else b"lint observation",
            cleanup_ok=True, cleanup_scope="linux_task_scope", cache_owner_cleanup_confirmed=True,
            scope_cleanup_ok=True, resource_channel_status="complete",
            violation_observer_status="complete", resource_receipt_sha256="a" * 64,
        ) for c in plan.checks)
        return EngineeringVerificationRun(plan.digest, "code", "1", "failed" if failed else "passed",
                                          checks, "b" * 64, "b" * 64, not failed)

    def binding(self, run, **kw):
        values = dict(step=run.step, attempt=run.attempt, kind="test", command=("private-argv",),
                      environment_fingerprint="host-env", tested_worktree_fingerprint=run.source_after,
                      initial_worktree_fingerprint="task-initial", base_commit_sha="c" * 40)
        values.update(kw)
        return VerificationEvidence(**values)

    def build(self, plan, run, **kw):
        return self.api().build_engineering_evidence(plan, run, binding=self.binding(run, **kw))


class TestEngineeringEvidence(_Helpers, unittest.TestCase):
    def test_entrypoint_is_present(self):
        self.assertTrue(callable(getattr(self.api(), "build_engineering_evidence", None)))

    def test_legacy_golden_receipt_and_fingerprint_remain_exact(self):
        self.api()
        legacy = VerificationEvidence(step="code", attempt="1", kind="test",
            command=("python", "-m", "unittest"), exit_code=1, output="AssertionError",
            environment_fingerprint="env-1", artifact_hashes={"calc.py": "abc"}, category="code",
            captured_at="2026-10-08T00:00:00+00:00")
        self.assertEqual(evidence_fingerprint(legacy), "c36a606190f236e92d3a586b92c78faf0e4df9e9eb575f438fe76181176a669c")
        self.assertEqual(hashlib.sha256(canonical(legacy.to_receipt())).hexdigest(),
                         "6fa92e309d7819b3056508149ad51ea7585b620a8e087d68be883f16b81a9a9d")
        self.assertIsNone(legacy.engineering_facts)

    def test_actual_python_pass_fail_and_zero_keep_host_observation_boundary(self):
        for body in ("self.assertEqual(1, 1)", "self.fail('actual failure')", None):
            with self.subTest(body=body), temp_workspace() as root:
                if body:
                    (root / "test_actual.py").write_text("import unittest\nclass T(unittest.TestCase):\n def test_one(self): " + body + "\n")
                plan = self.plan(root)
                run = execute_verification_plan(plan, ctx=ToolContext(root=root, sandbox=NoIsolation()),
                                                step="code", attempt="1")
                evidence = self.build(plan, run)
                row = evidence.to_receipt()
                self.assertEqual(row["kind"], "engineering_verification")
                self.assertEqual(row["run"]["checks"][0]["output_sha256"], run.checks[0].output_sha256)
                self.assertEqual(row["run"]["checks"][0]["tests_passed"], run.checks[0].tests_passed)
                if run.checks[0].cleanup_scope == "process_group":
                    self.assertFalse(evidence.passed)
                    self.assertEqual(evidence.category, "side_effect_unknown")
                    self.assertEqual(VerificationLedger().decide_repair(evidence).action, "human")
                else:
                    # A complete Windows Job receipt can close this host
                    # observation; it still authenticates no source or quality.
                    self.assertEqual(evidence.passed, run.passed)
                self.assertEqual(row["coverage"]["execution_source"], "not_authenticated")
                self.assertNotIn("actual failure", canonical(row).decode())
                self.assertNotIn(str(root), canonical(row).decode())
                self.assertNotIn("private-argv", canonical(row).decode())

    def test_deep_frozen_facts_and_ledger_preservation(self):
        with temp_workspace() as root:
            plan = self.plan(root, two=True)
            evidence = self.build(plan, self.observed_run(plan))
            def immutable(value):
                self.assertIn(type(value), (tuple, str, int, float, bool, type(None)))
                if type(value) is tuple:
                    for item in value:
                        immutable(item)
            immutable(evidence.engineering_facts)
            before = evidence.to_receipt()
            before["run"]["checks"][0]["status"] = "failed"
            self.assertTrue(evidence.passed)
            ledger = VerificationLedger()
            recorded = ledger.record(evidence)
            self.assertEqual(recorded.engineering_facts, evidence.engineering_facts)
            self.assertEqual(recorded.to_receipt()["run"], evidence.to_receipt()["run"])

    def test_audit_changes_but_repair_does_not_for_elapsed_output_or_labels(self):
        with temp_workspace() as root:
            plan = self.plan(root, two=True)
            first_run = self.observed_run(plan, failed=True, output=b"FAILED 0.001 seconds")
            other_run = dataclasses.replace(first_run, attempt="2", checks=(
                dataclasses.replace(first_run.checks[0], output=b"different passing output"),
                dataclasses.replace(first_run.checks[1], output=b"FAILED 9.9 seconds")))
            first = self.build(plan, first_run, captured_at="first")
            other = self.build(plan, other_run, captured_at="second")
            self.assertNotEqual(evidence_fingerprint(first), evidence_fingerprint(other))
            self.assertEqual(first.to_receipt()["repair_fingerprint"], other.to_receipt()["repair_fingerprint"])
            ledger = VerificationLedger(max_attempts=1)
            ledger.record(first)
            self.assertFalse(ledger.has_new_evidence(other))
            self.assertEqual(ledger.decide_repair(other, has_new_evidence=False).action, "too_many_attempts")
            changed = dataclasses.replace(first_run, source_before="d" * 64, source_after="d" * 64)
            self.assertTrue(ledger.has_new_evidence(self.build(plan, changed)))

    def test_exact_plan_check_order_and_binding_are_required(self):
        with temp_workspace() as root:
            plan = self.plan(root, two=True)
            run = self.observed_run(plan)
            for changed in (dataclasses.replace(run, plan_digest="e" * 64),
                            dataclasses.replace(run, checks=run.checks[::-1]),
                            dataclasses.replace(run, checks=run.checks[:1]),
                            dataclasses.replace(run, checks=run.checks + run.checks[:1]),
                            dataclasses.replace(run, checks=(run.checks[0], run.checks[0]))):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    self.build(plan, changed)
            for kw in ({"step": "task"}, {"attempt": "2"}, {"tested_worktree_fingerprint": ""},
                       {"tested_worktree_fingerprint": "wrong"}):
                with self.subTest(kw=kw), self.assertRaises(ValueError):
                    self.build(plan, run, **kw)

    def test_status_count_output_and_cleanup_contradictions_are_rejected(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            run = self.observed_run(plan)
            for kw in ({"tests_passed": 0}, {"tests_passed": True}, {"exit_code": 1},
                       {"output": None}, {"status": "not_run"}, {"status": "unknown"}):
                changed = dataclasses.replace(run, checks=(dataclasses.replace(run.checks[0], **kw),))
                with self.subTest(kw=kw), self.assertRaises(ValueError):
                    self.build(plan, changed)
            unknown = dataclasses.replace(run, checks=(dataclasses.replace(run.checks[0], scope_cleanup_ok=None),))
            evidence = self.build(plan, unknown)
            self.assertFalse(evidence.passed)
            self.assertEqual(evidence.category, "side_effect_unknown")
            self.assertEqual(VerificationLedger().decide_repair(evidence).action, "human")

    def test_unknown_resource_observer_and_tree_channels_never_allow_replay(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            run = self.observed_run(plan, failed=True)
            for kwargs in ({"resource_channel_status": "incomplete"}, {"violation_observer_status": "incomplete"},
                           {"resource_receipt_sha256": ""}, {"cache_owner_cleanup_confirmed": None},
                           {"cleanup_scope": "process_group"}, {"cleanup_scope": "job_tree", "resource_channel_status": "incomplete"}):
                changed = dataclasses.replace(run, checks=(dataclasses.replace(run.checks[0], **kwargs),))
                evidence = self.build(plan, changed)
                with self.subTest(kwargs=kwargs):
                    self.assertEqual(evidence.category, "side_effect_unknown")
                    self.assertEqual(VerificationLedger().decide_repair(evidence).action, "human")

    def test_unknown_source_window_is_not_invented(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            run = dataclasses.replace(self.observed_run(plan), status="source_unavailable", source_after="")
            evidence = self.build(plan, run)
            self.assertFalse(evidence.passed)
            self.assertEqual(evidence.category, "side_effect_unknown")
            with self.assertRaises(ValueError):
                self.build(plan, run, tested_worktree_fingerprint="invented")
            changed = dataclasses.replace(self.observed_run(plan), source_after="d" * 64)
            with self.assertRaises(ValueError):
                self.build(plan, changed)

    def test_default_and_explicit_true_cannot_bypass_stable_repair_key(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            evidence = self.build(plan, self.observed_run(plan, failed=True))
            for kwargs in ({}, {"has_new_evidence": True}):
                with self.subTest(kwargs=kwargs):
                    ledger = VerificationLedger()
                    self.assertEqual(ledger.decide_repair(evidence).action, "allow")
                    self.assertEqual(ledger.decide_repair(evidence, **kwargs).action, "no_new_evidence")

    def test_base_observation_labels_never_refresh_the_repair_key(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            evidence = self.build(plan, self.observed_run(plan, failed=True))
            labels = {
                "kind": "command", "command": ("another-old-command-label",),
                "result_commit_sha": "f" * 40, "result_commit_tree_oid": "e" * 40,
                "result_commit_tree_status": "matched", "result_commit_timing_status": "observed_after_test",
                "result_commit_checked_at": "later-capture", "test_head_before_sha": "e" * 40,
                "test_head_after_sha": "d" * 40, "test_head_status": "stable",
                "tested_git_tree_status": "available",
            }
            for field, value in labels.items():
                with self.subTest(field=field):
                    changed = dataclasses.replace(evidence, **{field: value})
                    if field != "result_commit_checked_at":
                        self.assertNotEqual(evidence_fingerprint(evidence), evidence_fingerprint(changed))
                    self.assertEqual(evidence.to_receipt()["repair_fingerprint"], changed.to_receipt()["repair_fingerprint"])
                    ledger = VerificationLedger()
                    ledger.record(evidence)
                    self.assertFalse(ledger.has_new_evidence(changed))
                    self.assertEqual(ledger.decide_repair(changed, has_new_evidence=True).action, "no_new_evidence")

    def test_real_source_environment_tools_parameters_and_failure_facts_refresh_key(self):
        import copy
        with temp_workspace() as root:
            plan = self.plan(root)
            run = self.observed_run(plan, failed=True)
            evidence = self.build(plan, run)
            for changes in ({"diff_fingerprint": "real-diff"}, {"base_commit_sha": "d" * 40},
                            {"initial_worktree_fingerprint": "new-initial-source"},
                            {"artifact_hashes": {"actual.py": "new-source-digest"}},
                            {"environment_fingerprint": "new-runtime-env"},
                            {"tested_git_tree_oid": "d" * 40}, {"git_object_format": "sha256"}):
                with self.subTest(changes=changes):
                    changed = dataclasses.replace(evidence, **changes)
                    self.assertNotEqual(evidence.to_receipt()["repair_fingerprint"], changed.to_receipt()["repair_fingerprint"])
                    ledger = VerificationLedger()
                    ledger.record(evidence)
                    self.assertTrue(ledger.has_new_evidence(changed))
            changed_source = dataclasses.replace(run, source_before="d" * 64, source_after="d" * 64)
            changed_exit = dataclasses.replace(run, checks=(dataclasses.replace(run.checks[0], exit_code=3),))
            tool = copy.copy(plan.checks[0])
            object.__setattr__(tool, "executable_identity", "f" * 64)
            tool_plan = dataclasses.replace(plan, checks=(tool,))
            parameter_plan = dataclasses.replace(plan, checks=(dataclasses.replace(plan.checks[0], cwd="sub"),))
            for changed in (self.build(plan, changed_source), self.build(plan, changed_exit),
                            self.build(tool_plan, self.observed_run(tool_plan, failed=True)),
                            self.build(parameter_plan, self.observed_run(parameter_plan, failed=True))):
                self.assertNotEqual(evidence.to_receipt()["repair_fingerprint"], changed.to_receipt()["repair_fingerprint"])
                ledger = VerificationLedger()
                ledger.record(evidence)
                self.assertTrue(ledger.has_new_evidence(changed))
            unknown_run = dataclasses.replace(run, checks=(dataclasses.replace(run.checks[0], scope_cleanup_ok=None),))
            unknown = self.build(plan, unknown_run, environment_fingerprint="new-runtime-env")
            self.assertEqual(VerificationLedger().decide_repair(unknown, has_new_evidence=True).action, "human")

    def test_exit_domain_keeps_signed_posix_and_unsigned_windows_endpoints(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            run = self.observed_run(plan, failed=True)
            for code in (-(2 ** 31), 2 ** 31 - 1, 3221225477, 2 ** 32 - 1):
                with self.subTest(code=code):
                    changed = dataclasses.replace(run, checks=(dataclasses.replace(run.checks[0], exit_code=code),))
                    try:
                        evidence = self.build(plan, changed)
                    except ValueError as error:
                        self.fail(f"valid host exit observation rejected: {error}")
                    self.assertEqual(evidence.exit_code, code)
                    self.assertFalse(evidence.passed)
            for code in (-(2 ** 31) - 1, 2 ** 32, True, 1.0):
                with self.subTest(code=code), self.assertRaises(ValueError):
                    self.build(plan, dataclasses.replace(run, checks=(dataclasses.replace(run.checks[0], exit_code=code),)))

    def test_host_attempt_survives_ledger_ordinal_and_base_binds_remain_live(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            run = dataclasses.replace(self.observed_run(plan), attempt="host-window-a")
            evidence = self.build(plan, run)
            recorded = VerificationLedger().record(evidence)
            self.assertEqual(recorded.attempt, "1")
            row = recorded.to_receipt()
            self.assertEqual(row["run"]["attempt"], "host-window-a")
            self.assertEqual(row["binding"]["execution_attempt"], "host-window-a")
            bound = dataclasses.replace(recorded, result_commit_sha="f" * 40,
                                        result_commit_tree_status="matched")
            self.assertNotEqual(evidence_fingerprint(recorded), evidence_fingerprint(bound))
            relabeled = dataclasses.replace(recorded, captured_at="later", result_commit_checked_at="later")
            self.assertEqual(evidence_fingerprint(recorded), evidence_fingerprint(relabeled))

    def test_first_failure_not_run_and_build_counts_cannot_forge_success(self):
        with temp_workspace() as root:
            plan = self.plan(root, two=True)
            good = self.observed_run(plan)
            failed = dataclasses.replace(good, status="failed", checks=(
                dataclasses.replace(good.checks[0], status="failed", exit_code=1),
                EngineeringCheckResult("tests", "not_run")))
            evidence = self.build(plan, failed)
            self.assertFalse(evidence.passed)
            for run in (dataclasses.replace(failed, status="passed"),
                        dataclasses.replace(failed, checks=(failed.checks[0], good.checks[1])),
                        dataclasses.replace(good, checks=(dataclasses.replace(good.checks[0], tests_passed=1), good.checks[1])),
                        dataclasses.replace(failed, checks=(failed.checks[0], dataclasses.replace(failed.checks[1], output=b"invented")))):
                with self.subTest(run=run), self.assertRaises(ValueError):
                    self.build(plan, run)

    def test_oversized_facts_and_fields_rejected_before_digest_and_entry_writes(self):
        from icode.evidence import EvidenceError, _verification_payload, save_verification_receipt
        with temp_workspace() as root:
            plan = self.plan(root)
            evidence = self.build(plan, self.observed_run(plan))
            for malformed in (dataclasses.replace(evidence, engineering_facts=("x" * (8 * 1024 * 1024),)),
                              dataclasses.replace(evidence, step="x" * (8 * 1024 * 1024)),
                              dataclasses.replace(evidence, engineering_facts={"mutable": []})):
                with self.subTest(field=type(malformed.engineering_facts)):
                    with patch("icode.engineering_evidence._engineering_digest") as digest:
                        with self.assertRaises(Exception) as caught:
                            evidence_fingerprint(malformed)
                        self.assertIsInstance(caught.exception, ValueError)
                        digest.assert_not_called()
                    target = root / "must-not-appear.json"
                    with self.assertRaises(EvidenceError):
                        save_verification_receipt(malformed, target)
                    with self.assertRaises(EvidenceError):
                        _verification_payload([malformed], [])
                    self.assertFalse(target.exists())

    def test_go_elapsed_changes_only_audit_not_repair_without_log_rewriting(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            run = self.observed_run(plan, failed=True, output=b'{"Action":"fail","Elapsed":0.1}\n')
            other = dataclasses.replace(run, checks=(dataclasses.replace(run.checks[0], output=b'{"Action":"fail","Elapsed":9.8}\n'),))
            first, second = self.build(plan, run), self.build(plan, other)
            self.assertNotEqual(first.to_receipt()["run"]["checks"][0]["output_sha256"], second.to_receipt()["run"]["checks"][0]["output_sha256"])
            self.assertEqual(first.to_receipt()["repair_fingerprint"], second.to_receipt()["repair_fingerprint"])

    def test_oversized_host_plan_is_rejected_before_its_digest(self):
        import copy
        from unittest.mock import PropertyMock
        with temp_workspace() as root:
            plan = self.plan(root)
            run = self.observed_run(plan)
            changed = copy.copy(plan)
            object.__setattr__(changed, "run_id", "x" * (8 * 1024 * 1024))
            with patch.object(VerificationPlan, "digest", new_callable=PropertyMock) as digest:
                with self.assertRaises(ValueError):
                    self.build(changed, run)
                digest.assert_not_called()

    def test_excessive_frozen_check_collection_fails_before_any_digest(self):
        with temp_workspace() as root:
            plan = self.plan(root)
            evidence = self.build(plan, self.observed_run(plan))
            api = self.api()
            facts = api._thaw(evidence.engineering_facts)
            facts["public_plan"]["checks"] *= 17
            facts["run"]["checks"] *= 17
            excessive = dataclasses.replace(evidence, engineering_facts=api._freeze(facts))
            with patch("icode.engineering_evidence._engineering_digest") as digest:
                with self.assertRaises(ValueError):
                    evidence_fingerprint(excessive)
                digest.assert_not_called()

    def test_malformed_frozen_run_and_attempt_have_bounded_public_errors(self):
        from icode.evidence import EvidenceError, _verification_payload, save_verification_receipt
        with temp_workspace() as root:
            plan = self.plan(root)
            evidence = self.build(plan, self.observed_run(plan))
            api = self.api()
            facts = api._thaw(evidence.engineering_facts)
            target = root / "existing-receipt.json"
            target.write_bytes(b"old-receipt")
            for bad_run in ({}, [], None, "not-an-object", {"attempt": True},
                            {"attempt": []}, {"attempt": ""}, {"attempt": "x" * 257}):
                malformed = dataclasses.replace(evidence, engineering_facts=api._freeze(
                    {"public_plan": facts["public_plan"], "run": bad_run}))
                operations = (
                    ("fingerprint", lambda: evidence_fingerprint(malformed), ValueError),
                    ("save", lambda: save_verification_receipt(malformed, target), EvidenceError),
                    ("direct_payload", lambda: _verification_payload([malformed], []), EvidenceError),
                )
                for name, operation, expected_error in operations:
                    with self.subTest(run=bad_run, operation=name), patch("icode.engineering_evidence._engineering_digest") as digest:
                        with self.assertRaises(Exception) as caught:
                            operation()
                        self.assertIsInstance(caught.exception, expected_error)
                        digest.assert_not_called()
                        self.assertEqual(target.read_bytes(), b"old-receipt")

    def test_actual_timeout_and_output_overflow_can_be_recorded_as_unknown(self):
        from icode.evidence import load_verification_receipts, save_verification_receipt
        for body, limit in (("print('x' * 20000)", 64), ("__import__('time').sleep(2)", 65536)):
            with self.subTest(body=body), temp_workspace() as root:
                (root / "test_actual.py").write_text("import unittest\nclass T(unittest.TestCase):\n def test_one(self): " + body + "\n")
                check = VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"),
                                          "unittest_summary_v1", timeout_seconds=1, output_limit_bytes=limit)
                plan = VerificationPlan(root.resolve(), "overflow-run", "EV-1", (check,))
                run = execute_verification_plan(plan, ctx=ToolContext(root=root, sandbox=NoIsolation()), step="code", attempt="1")
                self.assertEqual(run.checks[0].status, "output_incomplete")
                try:
                    evidence = self.build(plan, run)
                except ValueError as error:
                    self.fail(f"observed incomplete result could not be recorded: {error}")
                self.assertEqual(evidence.category, "side_effect_unknown")
                self.assertEqual(VerificationLedger().decide_repair(evidence).action, "human")
                receipt = root / "receipt.json"
                save_verification_receipt(evidence, receipt)
                self.assertEqual(load_verification_receipts([receipt])[0]["run"]["checks"][0]["output_sha256"], "")


class TestEngineeringReceiptValidation(_Helpers, unittest.TestCase):
    def test_timeout_numeric_domain_is_checked_before_float_conversion(self):
        from icode.evidence import EvidenceError, _verification_payload, load_verification_receipts, save_verification_receipt
        from icode.pack_verify import validate_engineering_receipt
        with temp_workspace() as root:
            plan = self.plan(root)
            evidence = self.build(plan, self.observed_run(plan))
            api = self.api()
            for timeout in (10 ** 400, -(10 ** 400), float("inf"), float("nan"), True):
                row = json.loads(canonical(evidence.to_receipt()))
                row["public_plan"]["checks"][0]["timeout_seconds"] = timeout
                facts = api._thaw(evidence.engineering_facts)
                facts["public_plan"]["checks"][0]["timeout_seconds"] = timeout
                malformed = dataclasses.replace(evidence, engineering_facts=api._freeze(facts))
                imported = root / "import.json"
                imported.write_bytes(canonical(row))
                target = root / "existing-receipt.json"
                target.write_bytes(b"old-receipt")
                operations = (
                    ("validator", lambda: validate_engineering_receipt(row), ValueError),
                    ("import", lambda: load_verification_receipts([imported]), EvidenceError),
                    ("fingerprint", lambda: evidence_fingerprint(malformed), ValueError),
                    ("save", lambda: save_verification_receipt(malformed, target), EvidenceError),
                    ("direct_payload", lambda: _verification_payload([malformed], []), EvidenceError),
                )
                for name, operation, expected_error in operations:
                    with self.subTest(timeout_type=type(timeout), sign=timeout > 0, operation=name):
                        with patch("icode.pack_verify._engineering_digest") as public_digest, patch("icode.engineering_evidence._engineering_digest") as host_digest:
                            with self.assertRaises(Exception) as caught:
                                operation()
                            self.assertIsInstance(caught.exception, expected_error)
                            public_digest.assert_not_called()
                            host_digest.assert_not_called()
                            self.assertEqual(target.read_bytes(), b"old-receipt")
                            if name == "import":
                                # Huge integers are legal JSON rejected by the
                                # engineering domain; NaN/Inf fail JSON parsing.
                                self.assertIn("工程验证" if type(timeout) in (int, bool) else "JSON", str(caught.exception))

    def test_valid_integer_and_finite_float_timeouts_remain_compatible(self):
        from icode.evidence import _verification_payload, load_verification_receipts, save_verification_receipt
        from icode.pack_verify import validate_engineering_receipt
        with temp_workspace() as root:
            original = self.plan(root)
            for timeout in (1, 1.25, 1800):
                with self.subTest(timeout=timeout):
                    plan = dataclasses.replace(original, checks=(dataclasses.replace(original.checks[0], timeout_seconds=timeout),))
                    evidence = self.build(plan, self.observed_run(plan))
                    row = evidence.to_receipt()
                    self.assertIsNotNone(validate_engineering_receipt(row))
                    self.assertEqual(evidence_fingerprint(evidence), row["fingerprint"])
                    path = root / f"receipt-{timeout}.json"
                    save_verification_receipt(evidence, path)
                    self.assertEqual(load_verification_receipts([path])[0]["public_plan"]["checks"][0]["timeout_seconds"], timeout)
                    self.assertEqual(_verification_payload([evidence], [])[1], 1)

    def test_closed_schema_versions_hashes_category_and_results(self):
        from icode.pack_verify import validate_engineering_receipt
        with temp_workspace() as root:
            plan = self.plan(root, two=True)
            original = self.build(plan, self.observed_run(plan)).to_receipt()
            self.assertIsNotNone(validate_engineering_receipt(original))
            mutations = [lambda r: r.pop("schema_version"),
                *[lambda r, v=v: r.update(schema_version=v) for v in (True, 1.0, 2)],
                lambda r: r.update(category="code"), lambda r: r.update(passed=False),
                lambda r: r.update(fingerprint="0" * 64),
                lambda r: r["public_plan"]["checks"].reverse(),
                lambda r: r["run"]["checks"].append(r["run"]["checks"][0]),
                lambda r: r["run"]["checks"][1].update(tests_passed=0),
                lambda r: r["binding"].update(tested_worktree_fingerprint=""),
                lambda r: r["run"].update(source_after="0" * 64),
                lambda r: r.update(extra="not allowed")]
            for mutation in mutations:
                row = json.loads(canonical(original))
                mutation(row)
                with self.subTest(row=row), self.assertRaises(ValueError):
                    validate_engineering_receipt(row)
            for old in ({"ratio": 1.25}, {"kind": "verification"}, {"kind": "unknown"}):
                self.assertIsNone(validate_engineering_receipt(old))

    def test_strict_wrapper_json_and_depth_budget_is_local(self):
        from icode.pack_verify import load_verifications_json, loads_json_value
        with temp_workspace() as root:
            path = root / "verifications.json"
            nested = b'{"value":' + b'[' * 127 + b'0' + b']' * 127 + b'}'
            path.write_bytes(b'{"schema_version":1,"receipts":[' + nested + b']}')
            self.assertEqual(load_verifications_json(path)["schema_version"], 1)
            with self.assertRaises(ValueError):
                loads_json_value(path.read_text())
            bad = [b'{"schema_version":1,"schema_versi\\u006fn":1,"receipts":[]}',
                   b'{"schema_version":1,"receipts":[{"x":"\\ud800"}]}',
                   b'{"schema_version":1,"receipts":[{"x":NaN}]}',
                   b'{"schema_version":1,"receipts":[{"x":1e999}]}',
                   b'{"schema_version":true,"receipts":[]}',
                   b'{"schema_version":1.0,"receipts":[]}',
                   b'{"schema_version":1,"receipts":[{"x":"\xff"}]}',
                   b'{"schema_version":1,"receipts":[{"kind":"engineering_verification"}]}',
                   b'{"schema_version":1,"receipts":[' + b'{"v":' + b'[' * 128 + b'0' + b']' * 128 + b'}]}']
            for payload in bad:
                path.write_bytes(payload)
                with self.subTest(payload=payload[:100]), self.assertRaises((ValueError, UnicodeError)):
                    load_verifications_json(path)

    def test_shared_mixed_row_count_and_output_budgets(self):
        from icode.evidence import EvidenceError, _verification_payload
        from icode.pack_verify import load_verifications_json
        self.assertEqual(_verification_payload([{}] * 9999, [{}])[1], 10000)
        with self.assertRaises(EvidenceError):
            _verification_payload([{}] * 10000, [{}])
        with self.assertRaises(EvidenceError):
            _verification_payload([{"v": "x" * (8 * 1024 * 1024)}], [])
        with temp_workspace() as root:
            path = root / "v.json"
            path.write_bytes(b'{"schema_version":1,"receipts":[' + b'{},' * 10000 + b'{}]}')
            with self.assertRaises(ValueError):
                load_verifications_json(path)
            path.write_bytes(b" " * (8 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                load_verifications_json(path)


class TestEngineeringEvidencePack(_Helpers, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = require_skill()

    def independent(self, pack, outside, *, encoding=None, args=None, newline=None):
        script = str(pack / "verify.py")
        arguments = [str(pack)] if args is None else args
        command = [sys.executable, "-I", "-B", script, *arguments]
        if encoding is not None:
            # Test fixture only: exercise the exported script with both actual
            # output streams strict, independent of the host console defaults.
            launcher = ("import runpy, sys; encoding, script, *args = sys.argv[1:]; "
                        f"sys.stdout.reconfigure(encoding=encoding, errors='strict', newline={newline!r}); "
                        f"sys.stderr.reconfigure(encoding=encoding, errors='strict', newline={newline!r}); "
                        "sys.argv = [script, *args]; runpy.run_path(script, run_name='__main__')")
            command = [sys.executable, "-I", "-B", "-c", launcher, encoding, script, *arguments]
        result = subprocess.run(command, cwd=outside, env=dict(os.environ, PYTHONPATH=""),
                                capture_output=True, timeout=30)
        # Decode captured bytes for host assertion diagnostics only. This does
        # not configure the child streams or hide a nonzero child exit status.
        result.stdout = result.stdout.decode(encoding or "utf-8", errors="replace")
        result.stderr = result.stderr.decode(encoding or "utf-8", errors="replace")
        return result

    def assert_independent_exit(self, pack, outside, expected=None, **kwargs):
        result = self.independent(pack, outside, **kwargs)
        diagnostics = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        if expected is None:
            self.assertNotEqual(result.returncode, 0, diagnostics)
        else:
            self.assertEqual(result.returncode, expected, diagnostics)
        return result

    def unicode_pack(self, root):
        from icode.evidence import build_evidence_pack
        from icode.pack_verify import verify_pack
        ticket = make_finished_plan_ticket(self.settings, root / "work")
        pack = root / "证据包-é-🚀"
        report = build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json)
        self.assertTrue(report.ok, report.render())
        self.assertEqual(verify_pack(pack), [])
        return pack

    def test_independent_success_keeps_exit_zero_with_strict_output_encodings(self):
        with temp_workspace() as root:
            pack = self.unicode_pack(root)
            for encoding in ("utf-8", "cp1252", "ascii"):
                with self.subTest(encoding=encoding):
                    result = self.assert_independent_exit(pack, root, 0, encoding=encoding)
                    expected = f"证据包校验通过：{pack}\n  工单：EV-1"
                    expected = expected.encode(encoding, errors="backslashreplace").decode(encoding)
                    self.assertIn(expected, result.stdout.replace("\r\n", "\n"))
                    self.assertEqual(result.stderr, "")
                    self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_independent_tampering_keeps_exit_one_with_strict_output_encodings(self):
        with temp_workspace() as root:
            pack = self.unicode_pack(root)
            (pack / "verifications.json").write_bytes(b"tampered")
            for encoding in ("utf-8", "cp1252", "ascii"):
                with self.subTest(encoding=encoding):
                    result = self.assert_independent_exit(pack, root, 1, encoding=encoding)
                    expected = f"证据包校验失败：{pack}\n  工单：EV-1"
                    expected = expected.encode(encoding, errors="backslashreplace").decode(encoding)
                    self.assertIn(expected, result.stdout.replace("\r\n", "\n"))
                    self.assertIn("verifications.json", result.stdout)
                    self.assertEqual(result.stderr, "")
                    self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_independent_crlf_diagnostics_preserve_strict_encoding_and_exits(self):
        with temp_workspace() as root:
            pack = self.unicode_pack(root)
            for expected_exit, message in ((0, "证据包校验通过"), (1, "证据包校验失败")):
                if expected_exit:
                    (pack / "verifications.json").write_bytes(b"tampered")
                for encoding in ("utf-8", "cp1252", "ascii"):
                    with self.subTest(exit=expected_exit, encoding=encoding):
                        result = self.assert_independent_exit(
                            pack, root, expected_exit, encoding=encoding, newline="\r\n")
                        expected = f"{message}：{pack}\n  工单：EV-1"
                        expected = expected.encode(encoding, errors="backslashreplace").decode(encoding)
                        self.assertIn("\r\n", result.stdout)
                        self.assertIn(expected, result.stdout.replace("\r\n", "\n"))
                        self.assertEqual(result.stderr, "")
                        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_independent_usage_keeps_exit_two_with_strict_output_encodings(self):
        with temp_workspace() as root:
            pack = self.unicode_pack(root)
            for encoding in ("utf-8", "cp1252", "ascii"):
                for args in ([], [str(root / "不存在-é-🚀")]):
                    with self.subTest(encoding=encoding, args=args):
                        result = self.assert_independent_exit(pack, root, 2, encoding=encoding, args=args)
                        expected = f"不是目录：{args[0]}" if args else "用法：python verify.py <证据包目录>"
                        expected = expected.encode(encoding, errors="backslashreplace").decode(encoding)
                        self.assertIn(expected, result.stderr)
                        if not args:
                            doc = "证据包独立校验器".encode(encoding, errors="backslashreplace").decode(encoding)
                            self.assertIn(doc, result.stdout)
                        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def rehash(self, pack):
        from icode.pack_verify import pack_digest
        manifest_path = pack / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        for entry in manifest["files"]:
            if entry["path"] == "verifications.json":
                body = (pack / entry["path"]).read_bytes()
                entry.update(size=len(body), sha256=hashlib.sha256(body).hexdigest())
        manifest["pack_digest"] = pack_digest(manifest["files"])
        manifest_path.write_bytes(canonical(manifest))

    def test_actual_save_cli_export_and_both_verifiers(self):
        from icode.evidence import save_verification_receipt
        from icode.cli import main
        from icode.pack_verify import verify_pack
        with temp_workspace() as root:
            (root / "test_actual.py").write_text("import unittest\nclass T(unittest.TestCase):\n def test_one(self): self.assertEqual(1, 1)\n")
            plan = self.plan(root)
            observed = execute_verification_plan(plan, ctx=ToolContext(root=root, sandbox=NoIsolation()),
                                                 step="code", attempt="host-window-a")
            evidence = VerificationLedger().record(self.build(plan, observed))
            receipt = root / "receipt.json"
            save_verification_receipt(evidence, receipt)
            ticket = make_finished_plan_ticket(self.settings, root / "work")
            pack = root / "pack"
            with patch("icode.cli.load_settings", return_value=self.settings), redirect_stdout(StringIO()):
                code = main(["evidence", "--ticket", str(ticket), "--dest", str(pack), "--receipt", str(receipt)])
            self.assertEqual(code, 0)
            self.assertEqual(verify_pack(pack), [])
            self.assert_independent_exit(pack, root, 0)
            body = json.loads((pack / "verifications.json").read_bytes())
            self.assertEqual(body["receipts"][0]["run"]["attempt"], "host-window-a")
            self.assertEqual(body["receipts"][0]["category"], evidence.category)
            body["receipts"][0]["run"]["checks"][0]["tests_passed"] = 0
            (pack / "verifications.json").write_bytes(canonical(body))
            self.rehash(pack)
            self.assertTrue(verify_pack(pack))
            self.assert_independent_exit(pack, root)

    def test_illegal_cli_receipt_preserves_old_pack(self):
        from icode.cli import main
        with temp_workspace() as root:
            ticket = make_finished_plan_ticket(self.settings, root / "work")
            pack = root / "pack"
            pack.mkdir()
            (pack / "sentinel").write_bytes(b"old")
            receipt = root / "bad.json"
            receipt.write_bytes(b'{"kind":"engineering_verification"}')
            with patch("icode.cli.load_settings", return_value=self.settings), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = main(["evidence", "--ticket", str(ticket), "--dest", str(pack), "--receipt", str(receipt)])
            self.assertEqual(code, 2)
            self.assertEqual((pack / "sentinel").read_bytes(), b"old")

    def test_self_consistent_other_ticket_receipt_cannot_move_between_packs(self):
        from icode.evidence import EvidenceError, build_evidence_pack
        from icode.pack_verify import engineering_receipt_values, verify_pack
        with temp_workspace() as root:
            plan = self.plan(root)
            row = self.build(plan, self.observed_run(plan)).to_receipt()
            ticket = make_finished_plan_ticket(self.settings, root / "work")
            pack = root / "pack"
            build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json, verifications=[row])
            before = (pack / "manifest.json").read_bytes()
            row["public_plan"]["ticket_id"] = "OTHER-TICKET"
            row.update({k: v for k, v in engineering_receipt_values(row).items() if k != "binding_exit_code"})
            with self.assertRaises(EvidenceError):
                build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json, verifications=[row])
            self.assertEqual((pack / "manifest.json").read_bytes(), before)
            (pack / "verifications.json").write_bytes(canonical({"schema_version": 1, "receipts": [row]}))
            self.rehash(pack)
            self.assertTrue(verify_pack(pack))
            self.assert_independent_exit(pack, root)

    def test_wrapper_negative_controls_remain_rejected_after_manifest_rehash(self):
        from icode.evidence import build_evidence_pack
        from icode.pack_verify import verify_pack
        with temp_workspace() as root:
            plan = self.plan(root)
            ticket = make_finished_plan_ticket(self.settings, root / "work")
            pack = root / "pack"
            row = self.build(plan, self.observed_run(plan)).to_receipt()
            build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json, verifications=[row])
            valid = {"schema_version": 1, "receipts": [row]}
            bad = [b'{"schema_version":1,"receipts":[],"recei\\u0070ts":[]}',
                   b'{"schema_version":1,"receipts":[{"x":"\xff"}]}',
                   b'{"schema_version":1,"receipts":[{"x":"\\udfff"}]}',
                   b'{"schema_version":1,"receipts":[{"x":Infinity}]}']
            for version in (True, 1.0, 9):
                changed = json.loads(canonical(valid))
                changed["receipts"][0]["schema_version"] = version
                bad.append(canonical(changed))
            for payload in bad:
                with self.subTest(payload=payload[:80]):
                    (pack / "verifications.json").write_bytes(payload)
                    self.rehash(pack)
                    self.assertTrue(verify_pack(pack))
                    self.assert_independent_exit(pack, root)
            # A fully rewritten legacy row has no engineering credit, but a
            # self-consistent unanchored pack cannot detect every downgrade.
            (pack / "verifications.json").write_bytes(canonical({"schema_version": 1, "receipts": [{"ratio": 1.25}]}))
            self.rehash(pack)
            self.assertEqual(verify_pack(pack), [])
            self.assert_independent_exit(pack, root, 0)

    def test_legacy_foreign_scalar_and_list_receipts_keep_export_semantics(self):
        from icode.evidence import EvidenceError, build_evidence_pack, load_verification_receipts
        from icode.pack_verify import verify_pack
        class Foreign:
            def __init__(self, value):
                self.value = value
            def to_receipt(self):
                return self.value
        with temp_workspace() as root:
            ticket = make_finished_plan_ticket(self.settings, root / "work")
            for value in (1.25, [1, "opaque"]):
                with self.subTest(value=value):
                    pack = root / "pack"
                    report = build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json,
                                                 verifications=[Foreign(value)])
                    self.assertTrue(report.ok, report.render())
                    self.assertEqual(verify_pack(pack), [])
                    self.assert_independent_exit(pack, root, 0)
                    path = root / "import.json"
                    path.write_bytes(canonical(value))
                    with self.assertRaises(EvidenceError):
                        load_verification_receipts([path])

    def test_unsigned_windows_failure_receipts_save_import_export_and_verify(self):
        from icode.evidence import build_evidence_pack, load_verification_receipts, save_verification_receipt
        from icode.pack_verify import verify_pack
        for code in (3221225477, 4294967295):
            with self.subTest(code=code), temp_workspace() as root:
                plan = self.plan(root)
                observed = self.observed_run(plan, failed=True)
                run = dataclasses.replace(observed, checks=(dataclasses.replace(observed.checks[0], exit_code=code),))
                try:
                    evidence = self.build(plan, run)
                except ValueError as error:
                    self.fail(f"unsigned Windows transport fixture rejected: {error}")
                receipt = root / "receipt.json"
                save_verification_receipt(evidence, receipt)
                rows = load_verification_receipts([receipt])
                self.assertEqual(rows[0]["run"]["checks"][0]["exit_code"], code)
                ticket = make_finished_plan_ticket(self.settings, root / "work")
                pack = root / "pack"
                report = build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json, verifications=rows)
                self.assertTrue(report.ok, report.render())
                self.assertEqual(verify_pack(pack), [])
                self.assert_independent_exit(pack, root, 0)
                for invalid in (-(2 ** 31) - 1, 2 ** 32, True, 1.0):
                    with self.subTest(invalid=invalid):
                        invalid_rows = json.loads(canonical(rows))
                        invalid_rows[0]["run"]["checks"][0]["exit_code"] = invalid
                        invalid_rows[0]["binding"]["exit_code"] = invalid
                        (pack / "verifications.json").write_bytes(canonical({"schema_version": 1, "receipts": invalid_rows}))
                        self.rehash(pack)
                        self.assertTrue(verify_pack(pack))
                        self.assert_independent_exit(pack, root)

    def test_malformed_frozen_run_preserves_actual_existing_pack(self):
        from icode.evidence import EvidenceError, build_evidence_pack
        with temp_workspace() as root:
            plan = self.plan(root)
            evidence = self.build(plan, self.observed_run(plan))
            ticket = make_finished_plan_ticket(self.settings, root / "work")
            pack = root / "pack"
            report = build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json, verifications=[evidence])
            self.assertTrue(report.ok, report.render())
            original_manifest = (pack / "manifest.json").read_bytes()
            api = self.api()
            facts = api._thaw(evidence.engineering_facts)
            for bad_run in ({}, [], None, "not-an-object"):
                malformed = dataclasses.replace(evidence, engineering_facts=api._freeze(
                    {"public_plan": facts["public_plan"], "run": bad_run}))
                with self.subTest(run=bad_run), patch("icode.engineering_evidence._engineering_digest") as digest:
                    with self.assertRaises(Exception) as caught:
                        build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json, verifications=[malformed])
                    self.assertIsInstance(caught.exception, EvidenceError)
                    digest.assert_not_called()
                    self.assertEqual((pack / "manifest.json").read_bytes(), original_manifest)

    def test_invalid_timeout_keeps_old_pack_and_rehashed_pack_fails_both_verifiers(self):
        from icode.evidence import EvidenceError, build_evidence_pack
        from icode.pack_verify import verify_pack
        with temp_workspace() as root:
            plan = self.plan(root)
            evidence = self.build(plan, self.observed_run(plan))
            ticket = make_finished_plan_ticket(self.settings, root / "work")
            pack = root / "pack"
            report = build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json, verifications=[evidence])
            self.assertTrue(report.ok, report.render())
            api = self.api()
            for timeout in (10 ** 400, -(10 ** 400), float("inf"), float("nan"), True):
                with self.subTest(timeout_type=type(timeout), sign=timeout > 0):
                    (pack / "verifications.json").write_bytes(canonical({"schema_version": 1, "receipts": [evidence.to_receipt()]}))
                    self.rehash(pack)
                    self.assertEqual(verify_pack(pack), [])
                    before = (pack / "manifest.json").read_bytes()
                    row = json.loads(canonical(evidence.to_receipt()))
                    row["public_plan"]["checks"][0]["timeout_seconds"] = timeout
                    facts = api._thaw(evidence.engineering_facts)
                    facts["public_plan"]["checks"][0]["timeout_seconds"] = timeout
                    malformed = dataclasses.replace(evidence, engineering_facts=api._freeze(facts))
                    for value in (row, malformed):
                        with patch("icode.pack_verify._engineering_digest") as public_digest, patch("icode.engineering_evidence._engineering_digest") as host_digest:
                            with self.assertRaises(Exception) as caught:
                                build_evidence_pack(ticket, dest=pack, gates_json=self.settings.gates_json, verifications=[value])
                            self.assertIsInstance(caught.exception, EvidenceError)
                            public_digest.assert_not_called()
                            host_digest.assert_not_called()
                            self.assertEqual((pack / "manifest.json").read_bytes(), before)
                    # These files deliberately include two kinds of invalid
                    # input: valid JSON integers outside the domain, and
                    # non-standard NaN/Infinity constants rejected by parsing.
                    (pack / "verifications.json").write_bytes(canonical({"schema_version": 1, "receipts": [row]}))
                    self.rehash(pack)
                    self.assertTrue(verify_pack(pack))
                    self.assert_independent_exit(pack, root)
