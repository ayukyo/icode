"""Characterize task verification, then require one private measurement window.

Offline model responses drive the real loop and file tools. They are not model
quality evidence; only the actual unittest subprocess supplies test outcomes.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from icode import runner
from icode.backends import FakeBackend
from icode.isolation import NoIsolation
from icode.self_verify import classify_failure
from tests._support import require_skill, temp_workspace


class _RecordingSandbox(NoIsolation):
    def __init__(self):
        super().__init__(reason="measurement characterization, not isolation proof")
        self.commands = []

    def wrap(self, argv, *, workspace, network=False):
        self.commands.append((list(argv), workspace, network))
        return super().wrap(argv, workspace=workspace, network=network)


def _write_response(value: int, call_id: str):
    return {"content": "", "tool_calls": [{
        "id": call_id, "name": "write_file",
        "arguments": {"path": "subject.py", "content": f"VALUE = {value}\n"},
    }]}


def _git(root: Path, *args: str):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, timeout=10)


def _workspace(root: Path):
    root = root.resolve()
    (root / "subject.py").write_bytes(b"VALUE = 0\n")
    (root / "test_subject.py").write_bytes(
        b"import unittest\nimport subject\n"
        b"class TestSubject(unittest.TestCase):\n"
        b" def test_value(self): self.assertEqual(subject.VALUE, 1)\n")
    _git(root, "init", "--quiet", "--object-format=sha1")
    _git(root, "add", "subject.py", "test_subject.py")
    _git(root, "-c", "user.name=ICODE Test", "-c", "user.email=test@example.invalid",
         "commit", "--quiet", "-m", "measurement baseline")
    return root


@unittest.skipUnless(os.name in ("posix", "nt") and shutil.which("git"),
                     "native Git/snapshot platform required; conformance_credit=none")
class TestTaskMeasurementCharacterization(unittest.TestCase):
    """These assertions must pass before and after the extraction."""

    @classmethod
    def setUpClass(cls):
        cls.settings = require_skill()

    def test_initial_real_test_keeps_stable_binding_and_original_command(self):
        with temp_workspace() as temporary:
            root = _workspace(temporary)
            sandbox = _RecordingSandbox()
            baseline = runner._snapshot(root)
            with mock.patch.object(runner, "_run_task_reviewer", return_value=(None, None)), \
                 mock.patch.object(runner, "run_unittest", wraps=runner.run_unittest) as verify:
                report = runner.run_task(self.settings, backend=FakeBackend([
                    _write_response(1, "initial"), "done"]), workspace=root,
                    sandbox=sandbox, max_repairs=0)
            evidence = report.verification
            self.assertEqual(report.exit_code, 0)
            self.assertEqual(report.changed_files, ["subject.py"])
            self.assertEqual(evidence.attempt, "1")
            self.assertEqual(evidence.command, ("python", "-B", "-m", "unittest"))
            self.assertEqual(evidence.tested_git_tree_status, "stable")
            self.assertEqual(evidence.test_head_status, "stable")
            self.assertEqual(evidence.initial_worktree_fingerprint, runner._snapshot_fingerprint(baseline))
            self.assertEqual(evidence.artifact_hashes["subject.py"],
                             hashlib.sha256((root / "subject.py").read_bytes()).hexdigest())
            self.assertEqual(verify.call_count, 1)
            self.assertIs(verify.call_args.kwargs["sandbox"], sandbox)
            self.assertEqual(verify.call_args.kwargs["output_limit_bytes"], runner._MAX_VERIFICATION_OUTPUT_BYTES)
            self.assertEqual(sandbox.commands, [([sys.executable, "-B", "-m", "unittest"], root, False)])

    def test_repair_real_tests_preserve_attempts_and_failure_classification(self):
        with temp_workspace() as temporary:
            root = _workspace(temporary)
            backend = FakeBackend([_write_response(2, "break"), "first done",
                                   _write_response(1, "repair"), "repair done"])
            with mock.patch.object(runner, "_run_task_reviewer", return_value=(None, None)):
                report = runner.run_task(self.settings, backend=backend, workspace=root,
                                         sandbox=NoIsolation(), max_repairs=1)
            first, second = report.repair_attempts
            self.assertEqual([first.attempt, second.attempt], ["1", "2"])
            self.assertEqual([first.exit_code, second.exit_code], [1, 0])
            self.assertEqual(first.category, classify_failure(exit_code=1, output=first.output, kind="test"))
            self.assertEqual(second.category, "")
            self.assertNotEqual(first.diff_fingerprint, second.diff_fingerprint)
            self.assertEqual(first.initial_worktree_fingerprint, second.initial_worktree_fingerprint)
            self.assertEqual(first.base_commit_sha, second.base_commit_sha)
            self.assertEqual(report.repair_decisions, ["allow"])
            self.assertIs(report.verification, second)
            self.assertEqual(report.exit_code, 0)
            self.assertEqual(len(backend.calls), 4)

    def test_git_and_binder_oserrors_are_not_incomplete_output_reports(self):
        for phase in ("before_git", "after_git", "binder"):
            with self.subTest(phase=phase), temp_workspace() as temporary:
                root = _workspace(temporary)
                error = OSError("observation failure, not verifier output")
                original = runner._read_task_git_state
                calls = 0
                def state(workspace):
                    nonlocal calls
                    calls += 1
                    if calls == (2 if phase == "before_git" else 3):
                        raise error
                    return original(workspace)
                target = "_bind_task_evidence" if phase == "binder" else "_read_task_git_state"
                effect = error if phase == "binder" else state
                with mock.patch.object(runner, target, side_effect=effect), \
                     mock.patch.object(runner, "_run_task_reviewer") as reviewer:
                    with self.assertRaises(OSError) as caught:
                        runner.run_task(self.settings, backend=FakeBackend(["done"]),
                                        workspace=root, sandbox=NoIsolation(), max_repairs=0)
                self.assertIs(caught.exception, error)
                reviewer.assert_not_called()


class TestSharedMeasurementStructure(unittest.TestCase):
    """A missing private entry is structural RED, not an old behavioral bug."""

    def test_task_initial_and_repair_share_measurement_without_duplicate_window(self):
        helper = getattr(runner, "_measure_task_verification", None)
        self.assertTrue(callable(helper), "single private measurement entry is absent")
        tree = ast.parse(inspect.getsource(runner.run_task))
        names = [node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertEqual(names.count("_measure_task_verification"), 2)
        for duplicated in ("run_unittest", "_capture_task_git_tree_oid", "_resolve_tested_git_tree",
                           "_resolve_test_head_status", "_bind_task_evidence"):
            self.assertNotIn(duplicated, names)


@unittest.skipUnless(os.name in ("posix", "nt") and shutil.which("git"),
                     "native Git/snapshot platform required; conformance_credit=none")
class TestVerificationMeasurement(unittest.TestCase):
    def _entry(self):
        helper = getattr(runner, "_measure_task_verification", None)
        self.assertTrue(callable(helper), "private measurement entry is absent (structural RED)")
        return helper

    def _inputs(self, root, *, sandbox=None, attempt="measurement-attempt"):
        before = runner._snapshot(root)
        object_format, revision = runner._read_task_git_state(root)
        (root / "subject.py").write_bytes(b"VALUE = 1\n")
        after = runner._snapshot(root)
        return dict(workspace=root, before=before, after=after, attempt=attempt,
                    base_commit_sha=revision, git_object_format=object_format,
                    initial_worktree_fingerprint=runner._snapshot_fingerprint(before),
                    sandbox=sandbox or NoIsolation())

    def test_stable_measurement_reuses_binding_and_bounded_actual_command(self):
        measure = self._entry()
        with temp_workspace() as temporary:
            root = _workspace(temporary)
            sandbox = _RecordingSandbox()
            inputs = self._inputs(root, sandbox=sandbox)
            with mock.patch.object(runner, "run_unittest", wraps=runner.run_unittest) as verify:
                changed, evidence = measure(**inputs)
            self.assertEqual(changed, ["subject.py"])
            self.assertEqual(evidence.attempt, inputs["attempt"])
            self.assertEqual(evidence.tested_git_tree_status, "stable")
            self.assertEqual(evidence.test_head_status, "stable")
            expected = runner._bind_task_evidence(
                inputs["before"], inputs["after"], evidence.exit_code, evidence.output, root,
                attempt=inputs["attempt"], base_commit_sha=inputs["base_commit_sha"],
                initial_worktree_fingerprint=inputs["initial_worktree_fingerprint"],
                git_object_format=inputs["git_object_format"],
                test_head_before_sha=evidence.test_head_before_sha,
                test_head_after_sha=evidence.test_head_after_sha,
                test_head_status=evidence.test_head_status,
                tested_git_tree_oid=evidence.tested_git_tree_oid,
                tested_git_tree_status=evidence.tested_git_tree_status)
            self.assertEqual((changed, evidence), expected)
            self.assertIs(verify.call_args.kwargs["sandbox"], sandbox)
            self.assertEqual(verify.call_args.kwargs["output_limit_bytes"], runner._MAX_VERIFICATION_OUTPUT_BYTES)
            self.assertEqual(sandbox.commands, [([sys.executable, "-B", "-m", "unittest"], root, False)])

    def test_actual_test_write_keeps_pretest_fingerprint_and_invalidates_tree(self):
        measure = self._entry()
        with temp_workspace() as temporary:
            root = _workspace(temporary)
            with (root / "test_subject.py").open("ab") as test_file:
                test_file.write(b"from pathlib import Path\nPath('test-created.txt').write_text('observed')\n")
            inputs = self._inputs(root)
            changed, evidence = measure(**inputs)
            self.assertEqual(evidence.exit_code, 0)
            self.assertTrue((root / "test-created.txt").exists())
            self.assertEqual(changed, ["subject.py"])
            self.assertEqual(evidence.tested_git_tree_oid, "")
            self.assertEqual(evidence.tested_git_tree_status, "unstable_during_test")
            self.assertEqual(evidence.tested_worktree_fingerprint, runner._snapshot_fingerprint(inputs["after"]))
            self.assertNotEqual(evidence.tested_worktree_fingerprint,
                                runner._snapshot_fingerprint(runner._snapshot(root)))

    def test_actual_test_head_change_preserves_existing_unstable_window(self):
        measure = self._entry()
        with temp_workspace() as temporary:
            root = _workspace(temporary)
            with (root / "test_subject.py").open("ab") as test_file:
                test_file.write(
                    b"import subprocess\nsubprocess.run(['git','-c','user.name=ICODE Test',"
                    b"'-c','user.email=test@example.invalid','commit','--allow-empty','--quiet',"
                    b"'-m','observed during test'],check=True,timeout=5)\n")
            inputs = self._inputs(root)
            _, evidence = measure(**inputs)
            self.assertEqual(evidence.exit_code, 0)
            self.assertNotEqual(evidence.test_head_before_sha, evidence.test_head_after_sha)
            self.assertEqual(evidence.test_head_status, "changed_during_test")
            # Existing full snapshots include .git: an empty commit changes
            # the observation window even if the source-only tree is equal.
            self.assertEqual(evidence.tested_git_tree_status, "unstable_during_test")
            self.assertEqual(evidence.tested_git_tree_oid, "")

    def test_object_format_change_never_signs_a_tree(self):
        measure = self._entry()
        with temp_workspace() as temporary:
            root = _workspace(temporary)
            inputs = self._inputs(root)
            revision = inputs["base_commit_sha"]
            with mock.patch.object(runner, "_read_task_git_state",
                                   side_effect=[("sha1", revision), ("sha256", "a" * 64)]):
                _, evidence = measure(**inputs)
            self.assertEqual(evidence.tested_git_tree_oid, "")
            self.assertEqual(evidence.tested_git_tree_status, "object_format_changed_during_test")
            self.assertEqual(evidence.test_head_status, "object_format_changed_during_test")
            self.assertEqual(evidence.git_object_format, "sha1")

    def test_unavailable_projection_preserves_reason_and_no_invented_oid(self):
        measure = self._entry()
        with temp_workspace() as temporary:
            root = _workspace(temporary)
            inputs = self._inputs(root)
            with mock.patch.object(runner, "_capture_task_git_tree_oid",
                                   return_value=("", "unsupported_entry")):
                _, evidence = measure(**inputs)
            self.assertEqual(evidence.exit_code, 0)
            self.assertEqual(evidence.tested_git_tree_oid, "")
            self.assertEqual(evidence.tested_git_tree_status, "unsupported_entry")

    def test_output_failures_wrap_only_original_verifier_error(self):
        measure = self._entry()
        errors = (runner.VerificationOutputCaptureError("PRIVATE_CAPTURE", return_code=2),
                  subprocess.TimeoutExpired(["PRIVATE_COMMAND"], 1, output=b"PRIVATE_OUTPUT"),
                  OSError("PRIVATE_IO"))
        for error in errors:
            with self.subTest(kind=type(error).__name__), temp_workspace() as temporary:
                root = _workspace(temporary)
                inputs = self._inputs(root)
                failure_type = getattr(runner, "_TaskVerificationOutputFailure", None)
                self.assertIsNotNone(failure_type, "private output failure boundary is absent")
                with mock.patch.object(runner, "run_unittest", side_effect=error), \
                     mock.patch.object(runner, "_bind_task_evidence") as bind:
                    with self.assertRaises(failure_type) as caught:
                        measure(**inputs)
                self.assertIs(caught.exception.error, error)
                self.assertNotIn("PRIVATE", str(caught.exception))
                bind.assert_not_called()

    def test_observation_binding_program_errors_and_interrupts_propagate(self):
        measure = self._entry()
        faults = [(name, OSError("observation failure")) for name in (
            "_read_task_git_state", "_capture_task_git_tree_oid", "_snapshot", "_bind_task_evidence")]
        faults += [("run_unittest", kind("program or interruption"))
                   for kind in (ValueError, TypeError, RuntimeError, KeyboardInterrupt, SystemExit)]
        for name, error in faults:
            with self.subTest(name=name, kind=type(error).__name__), temp_workspace() as temporary:
                root = _workspace(temporary)
                inputs = self._inputs(root)
                with mock.patch.object(runner, name, side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        measure(**inputs)
                self.assertIs(caught.exception, error)

    def test_both_actual_task_attempts_call_same_measurement_entry(self):
        measure = self._entry()
        with temp_workspace() as temporary:
            root = _workspace(temporary)
            sandbox = NoIsolation()
            backend = FakeBackend([_write_response(2, "first"), "first done",
                                   _write_response(1, "second"), "second done"])
            with mock.patch.object(runner, "_measure_task_verification", wraps=measure) as measured, \
                 mock.patch.object(runner, "_run_task_reviewer", return_value=(None, None)):
                report = runner.run_task(require_skill(), backend=backend, workspace=root,
                                         sandbox=sandbox, max_repairs=1)
            self.assertEqual(measured.call_count, 2)
            first, second = [call.kwargs for call in measured.call_args_list]
            self.assertEqual([first["attempt"], second["attempt"]], ["1", "2"])
            self.assertEqual(first["before"], second["before"])
            self.assertEqual(first["base_commit_sha"], second["base_commit_sha"])
            self.assertIs(first["sandbox"], sandbox)
            self.assertIs(second["sandbox"], sandbox)
            self.assertEqual(report.exit_code, 0)
            self.assertEqual(len(report.repair_attempts), 2)


if __name__ == "__main__":
    unittest.main()
