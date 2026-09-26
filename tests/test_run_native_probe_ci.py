"""R2.2 native CI must score evidence actually collected on each platform."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest import mock

from tests import _support  # noqa: F401

from icode.isolation import MacSeatbeltSandbox, NativeProbeResult, ProcessGroupProbeResult
from scripts import run_native_probe_ci


class TestNativeProbeCi(unittest.TestCase):
    def test_conformance来源字符串不会被拆成单字符(self) -> None:
        report = {
            "score": {"passed": 0, "total": 10, "critical_passed": False, "ready": False},
            "outcomes": {"doctor_self_test": False},
            "evidence": {"doctor_self_test": "no_independent_evidence"},
        }
        output = StringIO()
        with mock.patch.object(run_native_probe_ci, "score_probe_evidence",
                               return_value=report), redirect_stdout(output):
            run_native_probe_ci._emit_conformance_score(
                {}, platform="linux", doctor_self_test=False,
            )

        self.assertIn(
            "conformance linux doctor_self_test: UNVERIFIED (no_independent_evidence)",
            output.getvalue(),
        )

    def test_macos评分前采集同组清理且失败时门禁关闭(self) -> None:
        sandbox = MacSeatbeltSandbox(sandbox_exec="/bin/true")
        native = NativeProbeResult(True, {"workspace_write": True}, "native ok")
        group = ProcessGroupProbeResult(
            executed=True,
            passed=False,
            checks={"normal_exit": True, "timeout": False},
            detail="timeout cleanup failed",
        )
        output = StringIO()

        with mock.patch.object(run_native_probe_ci.sys, "platform", "darwin"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox", return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_macos_process_group_cleanup",
                               return_value=group, create=True) as cleanup_probe, \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score, \
             redirect_stdout(output):
            result = run_native_probe_ci._check(sandbox, "/bin/true")

        cleanup_probe.assert_called_once_with(sandbox)
        self.assertIs(score.call_args.kwargs.get("process_group_cleanup"), False)
        self.assertIs(score.call_args.kwargs["doctor_self_test"], False)
        self.assertEqual(result, 1)
        self.assertIn("process_group_timeout: FAIL", output.getvalue())

    def test_macos同组清理通过后才允许原生探针作业通过(self) -> None:
        sandbox = MacSeatbeltSandbox(sandbox_exec="/bin/true")
        native = NativeProbeResult(True, {"workspace_write": True}, "native ok")
        group = ProcessGroupProbeResult(
            executed=True,
            passed=True,
            checks={"normal_exit": True, "timeout": True},
            detail="group cleanup ok",
        )

        with mock.patch.object(run_native_probe_ci.sys, "platform", "darwin"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox", return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_macos_process_group_cleanup",
                               return_value=group, create=True), \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score:
            result = run_native_probe_ci._check(sandbox, "/bin/true")

        self.assertIs(score.call_args.kwargs.get("process_group_cleanup"), True)
        self.assertIs(score.call_args.kwargs["doctor_self_test"], True)
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
