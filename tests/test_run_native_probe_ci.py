"""R2.2 native CI must score evidence actually collected on each platform."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import _support  # noqa: F401

from icode.isolation import (
    LandlockSandbox,
    LinuxProtectedPathProbeResult,
    LinuxProcessTreeCleanupProbeResult,
    MacProtectedPathProbeResult,
    MacSeatbeltSandbox,
    NativeProbeResult,
    ProcessGroupProbeResult,
)
from scripts import run_native_probe_ci


class TestNativeProbeCi(unittest.TestCase):
    def test_unittest探针结果区分通过跳过和失败(self) -> None:
        class PassingCase(unittest.TestCase):
            def runTest(self) -> None:
                pass

        class SkippedCase(unittest.TestCase):
            def runTest(self) -> None:
                self.skipTest("namespace capability unavailable")

        class FailingCase(unittest.TestCase):
            def runTest(self) -> None:
                self.fail("lease expiry was not enforced")

        run_probe = getattr(run_native_probe_ci, "_run_unittest_probe", None)
        self.assertTrue(callable(run_probe), "native runner must classify unittest outcomes")
        self.assertEqual(run_probe(PassingCase()).status, "passed")
        skipped = run_probe(SkippedCase())
        self.assertEqual(skipped.status, "skipped")
        self.assertIn("namespace capability unavailable", skipped.detail)
        failed = run_probe(FailingCase())
        self.assertEqual(failed.status, "failed")
        self.assertIn("lease expiry was not enforced", failed.detail)

    def test_unittest探针执行测试类级资源生命周期(self) -> None:
        class FixtureCase(unittest.TestCase):
            class_resource_ready = False

            @classmethod
            def setUpClass(cls) -> None:
                cls.class_resource_ready = True

            @classmethod
            def tearDownClass(cls) -> None:
                cls.class_resource_ready = False

            def runTest(self) -> None:
                self.assertTrue(type(self).class_resource_ready)

        result = run_native_probe_ci._run_unittest_probe(FixtureCase())

        self.assertEqual(result.status, "passed", result.detail)
        self.assertFalse(FixtureCase.class_resource_ready)

    def _run_linux_check_with_lease_expiry(self, lease_result):
        sandbox = LandlockSandbox(helper="/tmp/icode-landlock")
        native = NativeProbeResult(True, {"workspace_write": True}, "native ok")
        protected = LinuxProtectedPathProbeResult(
            executed=True, passed=True,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
            detail="protected paths ok",
        )
        cleanup = LinuxProcessTreeCleanupProbeResult(
            executed=True, passed=True,
            checks={
                "descendant_started": True,
                "descendant_detached": True,
                "descendant_exited": True,
                "no_delayed_write": True,
            },
            detail="tree cleanup ok",
        )
        output = StringIO()
        with mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox",
                               return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_linux_protected_paths",
                               return_value=protected), \
             mock.patch.object(run_native_probe_ci, "probe_linux_process_tree_cleanup",
                               return_value=cleanup), \
             mock.patch.object(run_native_probe_ci, "_probe_linux_network_lease_expiry",
                               return_value=lease_result, create=True) as lease_probe, \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_seccomp_receipt",
                 return_value=SimpleNamespace(status="passed", detail="receipt ok"),
             ) as receipt_probe, \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_observed_command_bounds",
                 return_value=SimpleNamespace(status="passed", detail="bounds ok"),
             ) as bounds_probe, \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score, \
             redirect_stdout(output):
            result = run_native_probe_ci._check(sandbox, "/tmp/icode-landlock")
        receipt_probe.assert_called_once_with()
        bounds_probe.assert_called_once_with()
        return result, lease_probe, score, output.getvalue()

    def test_linux租约到期正向证据进入评分(self) -> None:
        result, lease_probe, score, output = self._run_linux_check_with_lease_expiry(
            SimpleNamespace(status="passed", detail="both peers observed EOF"),
        )
        lease_probe.assert_called_once_with()
        self.assertTrue(score.call_args.args[0]["network_allowlist_expiry"])
        self.assertEqual(result, 0)
        self.assertIn("linux-network-allowlist-expiry status=passed", output)

    def test_linux环境跳过不计租约到期正向证据(self) -> None:
        result, lease_probe, score, output = self._run_linux_check_with_lease_expiry(
            SimpleNamespace(status="skipped", detail="namespace capability unavailable"),
        )
        lease_probe.assert_called_once_with()
        self.assertFalse(score.call_args.args[0]["network_allowlist_expiry"])
        self.assertEqual(result, 0)
        self.assertIn("linux-network-allowlist-expiry status=skipped", output)

    def test_linux租约到期回归失败时原生作业失败(self) -> None:
        result, lease_probe, score, output = self._run_linux_check_with_lease_expiry(
            SimpleNamespace(status="failed", detail="lease expiry was not enforced"),
        )
        lease_probe.assert_called_once_with()
        self.assertFalse(score.call_args.args[0]["network_allowlist_expiry"])
        self.assertEqual(result, 1)
        self.assertIn("linux-network-allowlist-expiry status=failed", output)
        self.assertIn("network allowlist expiry", output)

    def _run_linux_check_with_seccomp_receipt(
        self,
        violation_result,
        bounds_result=SimpleNamespace(status="passed", detail="bounded commands observed"),
    ):
        sandbox = LandlockSandbox(helper="/tmp/icode-landlock")
        native = NativeProbeResult(True, {"workspace_write": True}, "native ok")
        protected = LinuxProtectedPathProbeResult(
            executed=True, passed=True,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
            detail="protected paths ok",
        )
        cleanup = LinuxProcessTreeCleanupProbeResult(
            executed=True, passed=True,
            checks={
                "descendant_started": True,
                "descendant_detached": True,
                "descendant_exited": True,
                "no_delayed_write": True,
            },
            detail="tree cleanup ok",
        )
        output = StringIO()
        with mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox",
                               return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_linux_protected_paths",
                               return_value=protected), \
             mock.patch.object(run_native_probe_ci, "probe_linux_process_tree_cleanup",
                               return_value=cleanup), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_seccomp_receipt",
                 return_value=violation_result, create=True,
             ) as violation_probe, \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_observed_command_bounds",
                 return_value=bounds_result, create=True,
             ) as bounds_probe, \
             mock.patch.object(run_native_probe_ci, "_probe_linux_network_lease_expiry",
                               return_value=SimpleNamespace(status="passed", detail="ok"),
                               create=True), \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score, \
             redirect_stdout(output):
            result = run_native_probe_ci._check(sandbox, "/tmp/icode-landlock")
        return result, violation_probe, bounds_probe, score, output.getvalue()

    def test_linux多类别原生回执运行但不冒充统一违规评分(self) -> None:
        result, violation_probe, _bounds_probe, score, output = self._run_linux_check_with_seccomp_receipt(
            SimpleNamespace(status="passed", detail="two denied syscall categories"),
        )

        violation_probe.assert_called_once_with()
        self.assertNotIn("uniform_violation", score.call_args.kwargs)
        self.assertEqual(result, 0)
        self.assertIn("linux-seccomp-receipt-probe status=passed", output)

    def test_linux原生回执探针跳过时保持未验证(self) -> None:
        result, violation_probe, _bounds_probe, score, output = self._run_linux_check_with_seccomp_receipt(
            SimpleNamespace(status="skipped", detail="user notification unavailable"),
        )

        violation_probe.assert_called_once_with()
        self.assertNotIn("uniform_violation", score.call_args.kwargs)
        self.assertEqual(result, 0)
        self.assertIn("linux-seccomp-receipt-probe status=skipped", output)

    def test_linux原生回执回归失败时原生作业失败(self) -> None:
        result, violation_probe, _bounds_probe, score, output = self._run_linux_check_with_seccomp_receipt(
            SimpleNamespace(status="failed", detail="uniform receipt mismatch"),
        )

        violation_probe.assert_called_once_with()
        self.assertNotIn("uniform_violation", score.call_args.kwargs)
        self.assertEqual(result, 1)
        self.assertIn("linux-seccomp-receipt-probe status=failed", output)
        self.assertIn("native seccomp receipt probe", output)

    def test_linux实命令资源界限探针进入native作业但不冒充评分(self) -> None:
        bounds = SimpleNamespace(status="passed", detail="bounded commands observed")
        result, violation_probe, bounds_probe, score, output = (
            self._run_linux_check_with_seccomp_receipt(
                SimpleNamespace(status="passed", detail="receipt observed"),
                bounds_result=bounds,
            )
        )

        violation_probe.assert_called_once_with()
        bounds_probe.assert_called_once_with()
        self.assertNotIn("resource_limits", score.call_args.kwargs)
        self.assertEqual(result, 0)
        self.assertIn("linux-observed-command-bounds status=passed", output)

    def test_linux实命令资源界限环境跳过时不计分(self) -> None:
        bounds = SimpleNamespace(status="skipped", detail="namespace unavailable")
        result, _violation_probe, bounds_probe, score, output = (
            self._run_linux_check_with_seccomp_receipt(
                SimpleNamespace(status="passed", detail="receipt observed"),
                bounds_result=bounds,
            )
        )

        bounds_probe.assert_called_once_with()
        self.assertNotIn("resource_limits", score.call_args.kwargs)
        self.assertEqual(result, 0)
        self.assertIn("linux-observed-command-bounds status=skipped", output)

    def test_linux实命令资源界限探针回归失败时native作业失败(self) -> None:
        bounds = SimpleNamespace(status="failed", detail="bounded command mismatch")
        result, _violation_probe, bounds_probe, score, output = (
            self._run_linux_check_with_seccomp_receipt(
                SimpleNamespace(status="passed", detail="receipt observed"),
                bounds_result=bounds,
            )
        )

        bounds_probe.assert_called_once_with()
        self.assertNotIn("resource_limits", score.call_args.kwargs)
        self.assertEqual(result, 1)
        self.assertIn("linux-observed-command-bounds status=failed", output)
        self.assertIn("native observed command bounds probe", output)

    def test_conformance来源字符串不会被拆成单字符(self) -> None:
        report = {
            "score": {
                "passed": 0,
                "total": 10,
                "critical_passed": False,
                "platform_critical_passed": False,
                "process_group_cleanup": None,
                "ready": False,
            },
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
        self.assertIn("platform_critical_passed=false", output.getvalue())
        self.assertIn("process_group_cleanup=not_applicable", output.getvalue())

    def test_linux保护路径证据进入评分且随包探针门禁失败关闭(self) -> None:
        sandbox = LandlockSandbox(helper="/tmp/icode-landlock")
        native = NativeProbeResult(
            True, {"workspace_write": True}, "native ok",
        )
        protected = LinuxProtectedPathProbeResult(
            executed=True,
            passed=True,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
            detail="protected paths ok",
        )
        cleanup = LinuxProcessTreeCleanupProbeResult(
            executed=True, passed=True,
            checks={
                "descendant_started": True,
                "descendant_detached": True,
                "descendant_exited": True,
                "no_delayed_write": True,
            },
            detail="tree cleanup ok",
        )
        success_output = StringIO()

        with mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox",
                               return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_linux_protected_paths",
                               return_value=protected), \
             mock.patch.object(run_native_probe_ci, "probe_linux_process_tree_cleanup",
                               return_value=cleanup), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_network_lease_expiry",
                 return_value=SimpleNamespace(status="passed", detail="lease ok"),
             ), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_seccomp_receipt",
                 return_value=SimpleNamespace(status="passed", detail="receipt ok"),
             ), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_observed_command_bounds",
                 return_value=SimpleNamespace(status="passed", detail="ok"),
                 create=True,
             ), \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score, \
             redirect_stdout(success_output):
            result = run_native_probe_ci._check(sandbox, "/tmp/icode-landlock")

        self.assertTrue(score.call_args.args[0]["protected_write_denied"])
        self.assertIs(score.call_args.kwargs["process_tree_cleanup"], True)
        self.assertTrue(score.call_args.kwargs["doctor_self_test"])
        self.assertEqual(result, 0)

        failed = LinuxProtectedPathProbeResult(
            executed=True,
            passed=False,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": False,
                "protected_rename_denied": True,
            },
            detail="protected paths failed",
        )
        failure_output = StringIO()
        with mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox",
                               return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_linux_protected_paths",
                               return_value=failed), \
             mock.patch.object(run_native_probe_ci, "probe_linux_process_tree_cleanup",
                               return_value=cleanup), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_network_lease_expiry",
                 return_value=SimpleNamespace(status="passed", detail="lease ok"),
             ), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_seccomp_receipt",
                 return_value=SimpleNamespace(status="passed", detail="receipt ok"),
             ), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_observed_command_bounds",
                 return_value=SimpleNamespace(status="passed", detail="ok"),
                 create=True,
             ), \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score, \
             redirect_stdout(failure_output):
            result = run_native_probe_ci._check(sandbox, "/tmp/icode-landlock")

        self.assertFalse(score.call_args.args[0]["protected_write_denied"])
        self.assertFalse(score.call_args.kwargs["doctor_self_test"])
        self.assertEqual(result, 1)
        self.assertIn("::error::landlock native probe failed: protected paths:",
                      failure_output.getvalue())

    def test_linux脱组后代未回收时证据为负且原生作业失败(self) -> None:
        sandbox = LandlockSandbox(helper="/tmp/icode-landlock")
        native = NativeProbeResult(True, {"workspace_write": True}, "native ok")
        protected = LinuxProtectedPathProbeResult(
            executed=True, passed=True,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
            detail="protected paths ok",
        )
        cleanup = LinuxProcessTreeCleanupProbeResult(
            executed=True, passed=False,
            checks={
                "descendant_started": True,
                "descendant_detached": True,
                "descendant_exited": False,
                "no_delayed_write": False,
            },
            detail="detached_descendant_still_running",
        )
        failure_output = StringIO()

        with mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox",
                               return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_linux_protected_paths",
                               return_value=protected), \
             mock.patch.object(run_native_probe_ci, "probe_linux_process_tree_cleanup",
                               return_value=cleanup), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_network_lease_expiry",
                 return_value=SimpleNamespace(status="passed", detail="lease ok"),
             ), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_seccomp_receipt",
                 return_value=SimpleNamespace(status="passed", detail="receipt ok"),
             ), \
             mock.patch.object(
                 run_native_probe_ci, "_probe_linux_observed_command_bounds",
                 return_value=SimpleNamespace(status="passed", detail="ok"),
                 create=True,
             ), \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score, \
             redirect_stdout(failure_output):
            result = run_native_probe_ci._check(sandbox, "/tmp/icode-landlock")

        self.assertIs(score.call_args.kwargs["process_tree_cleanup"], False)
        self.assertFalse(score.call_args.kwargs["doctor_self_test"])
        self.assertEqual(result, 1)
        self.assertIn(
            "::error::landlock native probe failed: process-tree cleanup:",
            failure_output.getvalue(),
        )

    def test_macos评分回执区分严格树清理与平台同组清理(self) -> None:
        output = StringIO()
        checks = {
            "workspace_write": True,
            "outside_write_denied": True,
            "protected_write_denied": True,
            "secret_read_denied": True,
            "network_denied": True,
            "network_allowlist_expiry": True,
            "child_inherits": True,
        }

        with redirect_stdout(output):
            run_native_probe_ci._emit_conformance_score(
                checks,
                platform="macos",
                doctor_self_test=True,
                process_tree_cleanup=False,
                process_group_cleanup=True,
            )

        notice = next(
            line for line in output.getvalue().splitlines()
            if line.startswith("::notice::conformance macos ")
        )
        self.assertIn("critical_passed=false", notice)
        self.assertIn("platform_critical_passed=true", notice)
        self.assertIn("process_group_cleanup=true", notice)
        self.assertIn("ready=false", notice)
        self.assertIn(
            "conformance macos process_tree_cleanup: UNVERIFIED "
            "(no_independent_evidence)",
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
        protected = MacProtectedPathProbeResult(
            executed=True, passed=True,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
            detail="protected paths ok",
        )
        output = StringIO()

        with mock.patch.object(run_native_probe_ci.sys, "platform", "darwin"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox", return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_macos_protected_paths",
                               return_value=protected), \
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
        protected = MacProtectedPathProbeResult(
            executed=True, passed=True,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
            detail="protected paths ok",
        )
        output = StringIO()

        with mock.patch.object(run_native_probe_ci.sys, "platform", "darwin"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox", return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_macos_protected_paths",
                               return_value=protected), \
             mock.patch.object(run_native_probe_ci, "probe_macos_process_group_cleanup",
                               return_value=group, create=True), \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score, \
             redirect_stdout(output):
            result = run_native_probe_ci._check(sandbox, "/bin/true")

        self.assertIs(score.call_args.kwargs.get("process_group_cleanup"), True)
        self.assertIs(score.call_args.kwargs["doctor_self_test"], True)
        self.assertTrue(score.call_args.args[0]["protected_write_denied"])
        self.assertEqual(result, 0)

    def test_macos保护路径探针失败时原生作业失败且评分保留负证据(self) -> None:
        sandbox = MacSeatbeltSandbox(sandbox_exec="/bin/true")
        native = NativeProbeResult(True, {"workspace_write": True}, "native ok")
        protected = MacProtectedPathProbeResult(
            executed=True, passed=False,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": False,
                "protected_rename_denied": True,
                "\n::error::injected=true": True,
            },
            detail="protected paths failed",
        )
        group = ProcessGroupProbeResult(
            executed=True, passed=True,
            checks={"normal_exit": True, "timeout": True}, detail="group cleanup ok",
        )
        output = StringIO()

        with mock.patch.object(run_native_probe_ci.sys, "platform", "darwin"), \
             mock.patch.object(run_native_probe_ci, "probe_native_sandbox", return_value=native), \
             mock.patch.object(run_native_probe_ci, "probe_macos_protected_paths",
                               return_value=protected), \
             mock.patch.object(run_native_probe_ci, "probe_macos_process_group_cleanup",
                               return_value=group), redirect_stdout(output), \
             mock.patch.object(run_native_probe_ci, "_emit_conformance_score") as score:
            result = run_native_probe_ci._check(sandbox, "/bin/true")

        checks = score.call_args.args[0]
        self.assertFalse(checks["protected_write_denied"])
        self.assertFalse(score.call_args.kwargs["doctor_self_test"])
        self.assertEqual(result, 1)
        self.assertIn(
            "::notice::macos-protected-path protected_write_denied=false",
            output.getvalue(),
        )
        self.assertNotIn("::error::injected=true", output.getvalue())


if __name__ == "__main__":
    unittest.main()
