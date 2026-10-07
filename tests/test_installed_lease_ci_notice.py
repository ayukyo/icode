"""Installed lease PASS/SKIP must be observable without forwarding raw output."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from scripts import run_native_wheel_ci as runner


class TestInstalledLeaseCiNotice(unittest.TestCase):
    def test_runner_returns_only_the_observed_pass_or_skip(self):
        for code, expected in ((0, "PASS"), (77, "SKIP")):
            with self.subTest(code=code):
                process = subprocess.CompletedProcess([], code, "PRIVATE_STDOUT", "PRIVATE_STDERR")
                output = StringIO()
                with mock.patch.object(runner.subprocess, "run", return_value=process), redirect_stdout(output):
                    self.assertEqual(runner._run("lease", ["probe"], cwd=Path("."), allow_environment_skip=True), expected)
                self.assertNotIn("PRIVATE_", output.getvalue())

    def test_main_publishes_one_fixed_notice_for_actual_lease_result(self):
        for status in ("PASS", "SKIP"):
            with self.subTest(status=status):
                def run(stage, *_args, **_kwargs):
                    return status if stage == "probe installed wheel network lease expiry" else "PASS"

                output = StringIO()
                with mock.patch.object(runner.sys, "platform", "linux"), \
                     mock.patch.object(runner.Path, "glob", return_value=[Path("test.whl")]), \
                     mock.patch.object(runner, "_run", side_effect=run) as execute, \
                     redirect_stdout(output):
                    self.assertEqual(runner.main(), 0)
                self.assertEqual(output.getvalue().count("::notice::"), 1)
                self.assertIn(f"::notice::installed-linux-network-lease result={status} conformance_credit=none", output.getvalue())
                lease = next(call for call in execute.call_args_list if call.args[0] == "probe installed wheel network lease expiry")
                self.assertTrue(lease.kwargs["allow_environment_skip"])
                self.assertIn("-I", lease.args[1])

    def test_lease_failure_still_blocks_main_without_pass_notice(self):
        def run(stage, *_args, **_kwargs):
            if stage == "probe installed wheel network lease expiry":
                raise RuntimeError("fixed_probe_failure")
            return "PASS"

        output = StringIO()
        with mock.patch.object(runner.sys, "platform", "linux"), \
             mock.patch.object(runner.Path, "glob", return_value=[Path("test.whl")]), \
             mock.patch.object(runner, "_run", side_effect=run), redirect_stdout(output):
            self.assertEqual(runner.main(), 1)
        self.assertNotIn("::notice::", output.getvalue())
        self.assertIn("::error::", output.getvalue())

    def test_unrequested_skip_still_fails_without_notice(self):
        process = subprocess.CompletedProcess([], 77, "", "fixed_probe_skip")
        output = StringIO()
        with mock.patch.object(runner.subprocess, "run", return_value=process), redirect_stdout(output):
            with self.assertRaises(RuntimeError):
                runner._run("another probe", ["probe"], cwd=Path("."))
        self.assertNotIn("::notice::", output.getvalue())

    def test_real_probe_failure_cannot_return_pass_or_skip(self):
        process = subprocess.CompletedProcess([], 1, "", "fixed_probe_failure")
        output = StringIO()
        with mock.patch.object(runner.subprocess, "run", return_value=process), redirect_stdout(output):
            with self.assertRaises(RuntimeError):
                runner._run("lease", ["probe"], cwd=Path("."), allow_environment_skip=True)
        self.assertNotIn("PASS", output.getvalue())
        self.assertNotIn("SKIP", output.getvalue())
        self.assertNotIn("::notice::", output.getvalue())
