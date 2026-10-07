"""Task-boundary timeout handling must not sign incomplete or private output."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import subprocess
import unittest
from unittest.mock import patch

from icode.backends import FakeBackend
from icode.isolation import NoIsolation
from icode.runner import prepare_workspace, run_task
from tests._support import REPO_ROOT, require_skill, temp_workspace


def private_timeout() -> subprocess.TimeoutExpired:
    error = subprocess.TimeoutExpired(
        ["PRIVATE_COMMAND"], 5, output=b"PRIVATE_STDOUT", stderr=b"PRIVATE_STDERR",
    )
    error.add_note("PRIVATE_NOTE")
    return error


class TestTaskTimeout(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def test_initial_timeout_stops_without_complete_evidence_or_reviewer(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            backend = FakeBackend(["完成"])
            with (
                patch("icode.runner.run_unittest", side_effect=private_timeout()) as verify,
                patch("icode.runner._run_task_reviewer") as reviewer,
            ):
                try:
                    report = run_task(self.settings, backend=backend, workspace=dst,
                                      sandbox=NoIsolation())
                except subprocess.TimeoutExpired:
                    self.fail("task timeout escaped instead of returning a failure report")
            self.assertFalse(report.ok)
            self.assertEqual(report.exit_code, 2)
            self.assertIsNone(report.verification)
            self.assertEqual(report.repair_attempts, [])
            self.assertEqual(report.repair_decisions, [])
            self.assertIn("独立验证超过时间上限", report.error)
            self.assertNotIn("PRIVATE_", report.error + report.test_output + report.render())
            self.assertEqual(len(backend.calls), 1)
            self.assertEqual(verify.call_count, 1)
            reviewer.assert_not_called()

    def test_repair_timeout_preserves_prior_complete_evidence_and_stops(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            backend = FakeBackend([
                {"content": "", "tool_calls": [{
                    "id": "break", "name": "write_file",
                    "arguments": {"path": str(dst / "calc.py"),
                                  "content": "raise RuntimeError('boom')\n"},
                }]},
                "首次任务结束", "修复回合结束",
            ])
            with (
                patch("icode.runner.run_unittest", side_effect=[
                    (1, "Traceback (most recent call last):\nAssertionError: boom\n"),
                    private_timeout(),
                ]) as verify,
                patch("icode.runner._run_task_reviewer") as reviewer,
            ):
                try:
                    report = run_task(self.settings, backend=backend, workspace=dst,
                                      sandbox=NoIsolation(), max_repairs=2)
                except subprocess.TimeoutExpired:
                    self.fail("repair timeout escaped instead of returning a failure report")
            self.assertFalse(report.ok)
            self.assertEqual(report.exit_code, 2)
            self.assertIsNone(report.verification)
            self.assertEqual(len(report.repair_attempts), 1)
            self.assertEqual(report.repair_attempts[0].exit_code, 1)
            self.assertEqual(report.repair_decisions, ["allow"])
            self.assertIn("独立验证超过时间上限", report.error)
            self.assertNotIn("PRIVATE_", report.error + report.test_output + report.render())
            self.assertEqual(len(backend.calls), 3)
            self.assertEqual(verify.call_count, 2)
            reviewer.assert_not_called()

    def test_cli_timeout_is_private_and_does_not_create_or_replace_receipt(self) -> None:
        from icode.cli import _build_parser, cmd_task

        for receipt_state in ("not_requested", "missing", "existing"):
            with self.subTest(receipt_state=receipt_state), temp_workspace() as ws:
                dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
                receipt = ws / "receipt.json"
                if receipt_state == "existing":
                    receipt.write_bytes(b"keep prior complete receipt")
                argv = ["task", "--workspace", str(dst)]
                if receipt_state != "not_requested":
                    argv.extend(["--receipt-out", str(receipt)])
                args = _build_parser().parse_args(argv)
                backend = FakeBackend(["完成"])
                stdout, stderr = StringIO(), StringIO()
                with (
                    patch("icode.cli.load_settings", return_value=self.settings),
                    patch("icode.cli._build_runner", return_value=(backend, None, None, None, NoIsolation())),
                    patch("icode.runner.run_unittest", side_effect=private_timeout()),
                    patch("icode.runner._run_task_reviewer") as reviewer,
                    patch("icode.evidence.save_verification_receipt") as save_receipt,
                    redirect_stdout(stdout), redirect_stderr(stderr),
                ):
                    try:
                        result = cmd_task(args)
                    except subprocess.TimeoutExpired:
                        self.fail("CLI timeout escaped without a stable task failure")
                self.assertEqual(result, 1 if receipt_state == "not_requested" else 2)
                self.assertIn("独立验证超过时间上限", stdout.getvalue())
                self.assertNotIn("PRIVATE_", stdout.getvalue() + stderr.getvalue())
                save_receipt.assert_not_called()
                reviewer.assert_not_called()
                if receipt_state == "existing":
                    self.assertEqual(receipt.read_bytes(), b"keep prior complete receipt")
                else:
                    self.assertFalse(receipt.exists())
