"""Task verification I/O failures remain private, incomplete and non-retryable."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from icode.backends import FakeBackend
from icode.isolation import NoIsolation
from icode.runner import prepare_workspace, run_task
from tests._support import REPO_ROOT, require_skill, temp_workspace


ERROR_TYPES = (OSError, PermissionError, FileNotFoundError)


def private_io_error(kind: type[OSError]) -> OSError:
    error = kind(5, "PRIVATE_MESSAGE", "PRIVATE_FILENAME", None, "PRIVATE_FILENAME2")
    error.add_note("PRIVATE_NOTE")
    return error


class TestTaskVerificationIo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def test_real_missing_interpreter_reports_failure_but_low_level_still_raises(self) -> None:
        from icode.runner import run_unittest

        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            with (
                patch("icode.runner.sys.executable", str(ws / "PRIVATE_MISSING_INTERPRETER")),
                patch("icode.runner._run_task_reviewer") as reviewer,
            ):
                with self.assertRaises(FileNotFoundError):
                    run_unittest(dst, sandbox=NoIsolation(), output_limit_bytes=1024)
                report = run_task(self.settings, backend=FakeBackend(["完成"]),
                                  workspace=dst, sandbox=NoIsolation())
            self.assertFalse(report.ok)
            self.assertIsNone(report.verification)
            self.assertEqual(report.exit_code, 2)
            self.assertNotIn("PRIVATE_", report.error + report.test_output + report.render())
            reviewer.assert_not_called()

    def test_program_errors_and_interruptions_are_not_silenced(self) -> None:
        for kind in (ValueError, TypeError, RuntimeError, KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), temp_workspace() as ws:
                dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
                with (
                    patch("icode.runner.run_unittest", side_effect=kind("sentinel")),
                    patch("icode.runner._run_task_reviewer") as reviewer,
                ):
                    with self.assertRaises(kind):
                        run_task(self.settings, backend=FakeBackend(["完成"]),
                                 workspace=dst, sandbox=NoIsolation())
                reviewer.assert_not_called()

    def test_initial_io_failure_returns_private_incomplete_report(self) -> None:
        for kind in ERROR_TYPES:
            with self.subTest(kind=kind.__name__), temp_workspace() as ws:
                dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
                backend = FakeBackend(["完成"])
                with (
                    patch("icode.runner.run_unittest", side_effect=private_io_error(kind)) as verify,
                    patch("icode.runner._run_task_reviewer") as reviewer,
                ):
                    try:
                        report = run_task(self.settings, backend=backend, workspace=dst,
                                          sandbox=NoIsolation())
                    except OSError:
                        self.fail("verification I/O failure escaped without a task report")
                self.assertFalse(report.ok)
                self.assertEqual(report.exit_code, 2)
                self.assertIsNone(report.verification)
                self.assertEqual(report.repair_attempts, [])
                self.assertEqual(report.repair_decisions, [])
                self.assertIn("独立验证未能完成文件操作", report.error)
                self.assertNotIn("PRIVATE_", report.error + report.test_output + report.render())
                self.assertEqual(len(backend.calls), 1)
                self.assertEqual(verify.call_count, 1)
                reviewer.assert_not_called()

    def test_repair_io_failure_preserves_prior_evidence_and_stops(self) -> None:
        for kind in ERROR_TYPES:
            with self.subTest(kind=kind.__name__), temp_workspace() as ws:
                dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
                backend = FakeBackend([
                    {"content": "", "tool_calls": [{
                        "id": "break", "name": "write_file",
                        "arguments": {"path": str(dst / "calc.py"),
                                      "content": "raise RuntimeError('boom')\n"},
                    }]}, "首次任务结束", "修复回合结束",
                ])
                with (
                    patch("icode.runner.run_unittest", side_effect=[
                        (1, "Traceback (most recent call last):\nAssertionError: boom\n"),
                        private_io_error(kind),
                    ]) as verify,
                    patch("icode.runner._run_task_reviewer") as reviewer,
                ):
                    try:
                        report = run_task(self.settings, backend=backend, workspace=dst,
                                          sandbox=NoIsolation(), max_repairs=2)
                    except OSError:
                        self.fail("repair I/O failure escaped without a task report")
                self.assertFalse(report.ok)
                self.assertEqual(report.exit_code, 2)
                self.assertIsNone(report.verification)
                self.assertEqual(len(report.repair_attempts), 1)
                self.assertEqual(report.repair_attempts[0].exit_code, 1)
                self.assertEqual(report.repair_decisions, ["allow"])
                self.assertIn("独立验证未能完成文件操作", report.error)
                self.assertNotIn("PRIVATE_", report.error + report.test_output + report.render())
                self.assertEqual(len(backend.calls), 3)
                self.assertEqual(verify.call_count, 2)
                reviewer.assert_not_called()

    def test_cli_io_failure_protects_private_error_and_receipt(self) -> None:
        from icode.cli import main

        for kind in ERROR_TYPES:
            for state in ("not_requested", "missing", "existing"):
                with self.subTest(kind=kind.__name__, state=state), temp_workspace() as ws:
                    dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
                    receipt = ws / "receipt.json"
                    if state == "existing":
                        receipt.write_bytes(b"keep prior complete receipt")
                    argv = ["task", "--workspace", str(dst)]
                    if state != "not_requested":
                        argv.extend(["--receipt-out", str(receipt)])
                    stdout, stderr = StringIO(), StringIO()
                    with (
                        patch("icode.cli.load_settings", return_value=self.settings),
                        patch("icode.cli._build_runner", return_value=(FakeBackend(["完成"]), None, None, None, NoIsolation())),
                        patch("icode.runner.run_unittest", side_effect=private_io_error(kind)),
                        patch("icode.runner._run_task_reviewer") as reviewer,
                        patch("icode.evidence.save_verification_receipt") as save_receipt,
                        redirect_stdout(stdout), redirect_stderr(stderr),
                    ):
                        result = main(argv)
                    self.assertEqual(result, 1 if state == "not_requested" else 2)
                    self.assertIn("独立验证未能完成文件操作", stdout.getvalue())
                    self.assertNotIn("PRIVATE_", stdout.getvalue() + stderr.getvalue())
                    save_receipt.assert_not_called()
                    reviewer.assert_not_called()
                    if state == "existing":
                        self.assertEqual(receipt.read_bytes(), b"keep prior complete receipt")
                    else:
                        self.assertFalse(receipt.exists())
