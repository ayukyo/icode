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
    def setUp(self) -> None:
        self.real_engineering_bridge_probe = run_native_probe_ci._probe_linux_engineering_bridge
        bridge_patch = mock.patch.object(
            run_native_probe_ci, "_probe_linux_engineering_bridge",
            return_value=run_native_probe_ci.ProbeExecution(
                "skipped", "portable_unit_test_no_native_credit",
            ),
        )
        self.bridge_probe_double = bridge_patch.start()
        self.addCleanup(bridge_patch.stop)

    def test_linux_engineering_bridge_skip_and_failure_keep_three_states(self) -> None:
        for status in ("passed", "skipped", "failed"):
            with self.subTest(status=status), \
                 mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
                 mock.patch.object(
                     run_native_probe_ci, "_run_unittest_probe",
                     return_value=run_native_probe_ci.ProbeExecution(status, "non-sensitive fixture"),
                 ) as execute:
                result = self.real_engineering_bridge_probe()
                self.assertEqual(result.status, status)
                execute.assert_called_once()
        with mock.patch.object(run_native_probe_ci.sys, "platform", "darwin"), \
             mock.patch.object(run_native_probe_ci, "_run_unittest_probe") as execute:
            result = self.real_engineering_bridge_probe()
            self.assertEqual(result.status, "skipped")
            execute.assert_not_called()

    def test_linux_engineering_bridge_diagnostic_selected_once_never_scored(self) -> None:
        for status in ("passed", "skipped", "failed", "unknown"):
            with self.subTest(status=status):
                self.bridge_probe_double.reset_mock()
                self.bridge_probe_double.return_value = SimpleNamespace(status=status, detail="fixture")
                result, _lease, score, output = self._run_linux_check_with_lease_expiry(
                    run_native_probe_ci.ProbeExecution("passed", "fixture"),
                )
                self.bridge_probe_double.assert_called_once_with()
                expected_status = "failed" if status == "unknown" else status
                self.assertEqual(result, 1 if expected_status == "failed" else 0)
                self.assertIn(
                    f"::notice::linux-engineering-bridge status={expected_status} "
                    "conformance_credit=none native_ready=false",
                    output,
                )
                self.assertNotIn("engineering_bridge", score.call_args.args[0])
                self.assertNotIn("engineering_bridge", score.call_args.kwargs)

    def test_linux_engineering_bridge_loader_selects_one_existing_case(self) -> None:
        probe = getattr(run_native_probe_ci, "_probe_linux_engineering_bridge", None)
        self.assertTrue(callable(probe), "engineering bridge case is not selected by native CI")
        from tests.test_linux_contract_engineering import TestLinuxContractEngineering

        with mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
             mock.patch.object(
                 run_native_probe_ci, "_run_unittest_probe",
                 return_value=run_native_probe_ci.ProbeExecution("passed", ""),
             ) as execute:
            result = self.real_engineering_bridge_probe()

        self.assertEqual(result.status, "passed")
        execute.assert_called_once()
        case = execute.call_args.args[0]
        self.assertIs(type(case), TestLinuxContractEngineering)
        self.assertEqual(case._testMethodName, "test_bridge_code_cp_receipt_and_pack")

    def test_linux_resource_loader_selects_real_quota_case_once(self) -> None:
        from tests.test_linux_product_task_quota import TestLinuxProductTaskQuota

        with mock.patch.object(run_native_probe_ci.sys, "platform", "linux"), \
             mock.patch.object(
                 run_native_probe_ci, "_run_unittest_probe",
                 return_value=run_native_probe_ci.ProbeExecution("passed", "fixture"),
             ) as execute:
            result = run_native_probe_ci._probe_linux_resource_limits()

        self.assertEqual(result.status, "passed")
        execute.assert_called_once()
        case = execute.call_args.args[0]
        self.assertIs(type(case), TestLinuxProductTaskQuota)
        self.assertEqual(case._testMethodName, "test_registry_cap_one_enforces_real_fork_quota")

    def test_unittest_probe_real_class_setup_skip_and_failure_lifecycle(self) -> None:
        events = []

        def make_case(mode):
            class LifecycleCase(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    events.append("setup")

                    def cleanup():
                        events.append("cleanup")
                        if mode in {
                            "cleanup_error", "setup_skip_cleanup_error",
                            "method_skip_cleanup_error",
                        }:
                            raise RuntimeError("fixture_cleanup_error")

                    cls.addClassCleanup(cleanup)
                    if mode in {"setup_skip", "setup_skip_cleanup_error"}:
                        raise unittest.SkipTest("fixture_setup_prerequisite_unavailable")
                    if mode == "setup_error":
                        raise RuntimeError("fixture_setup_error")

                @classmethod
                def tearDownClass(cls):
                    events.append("teardown")
                    if mode == "failure_with_teardown_skip":
                        raise unittest.SkipTest("fixture_teardown_skip")

                def runTest(self):
                    events.append("method")
                    if mode in {"method_skip", "method_skip_cleanup_error"}:
                        self.skipTest("fixture_method_skip")
                    if mode == "failure_with_teardown_skip":
                        self.fail("fixture_method_failure")

            return LifecycleCase()

        scenarios = (
            ("setup_skip", "skipped", 0, 1, 0, 0),
            ("setup_error", "failed", 0, 0, 0, 1),
            ("normal", "passed", 1, 0, 0, 0),
            ("method_skip", "skipped", 1, 1, 0, 0),
            ("cleanup_error", "failed", 1, 0, 0, 1),
            ("setup_skip_cleanup_error", "failed", 0, 1, 0, 1),
            ("method_skip_cleanup_error", "failed", 1, 1, 0, 1),
            ("failure_with_teardown_skip", "failed", 1, 1, 1, 0),
        )
        for mode, status, count, skips, failures, errors in scenarios:
            with self.subTest(mode=mode):
                events.clear()
                raw = unittest.TestResult()
                unittest.TestSuite((make_case(mode),)).run(raw)
                self.assertEqual(
                    (raw.testsRun, len(raw.skipped), len(raw.failures), len(raw.errors)),
                    (count, skips, failures, errors),
                )
                expected_events = (
                    ["setup", "cleanup"] if count == 0
                    else ["setup", "method", "teardown", "cleanup"]
                )
                self.assertEqual(events, expected_events)
                events.clear()
                execution = run_native_probe_ci._run_unittest_probe(make_case(mode))
                self.assertEqual(events, expected_events)
                self.assertEqual(execution.status, status, execution.detail)
                if mode == "setup_skip":
                    self.assertEqual(execution.detail, "fixture_setup_prerequisite_unavailable")
                elif mode == "method_skip":
                    self.assertEqual(execution.detail, "fixture_method_skip")

        raw = unittest.TestResult()
        unittest.TestSuite().run(raw)
        self.assertEqual((raw.testsRun, raw.skipped, raw.failures, raw.errors), (0, [], [], []))
        execution = run_native_probe_ci._run_unittest_probe(unittest.TestSuite())
        self.assertEqual(execution.status, "failed")
        self.assertEqual(execution.detail, "expected one test, ran 0")

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

    def _run_linux_check_with_lease_expiry(self, lease_result, *, resource_result=None):
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
            result = run_native_probe_ci._check(
                sandbox, "/tmp/icode-landlock", resource_result=resource_result,
            )
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

    def test_linux独立进程配额证据进入评分(self) -> None:
        result, _lease_probe, score, output = self._run_linux_check_with_lease_expiry(
            SimpleNamespace(status="passed", detail="lease ok"),
            resource_result=SimpleNamespace(
                status="passed", detail="real_process_quota_observed",
            ),
        )
        self.assertTrue(score.call_args.kwargs["resource_limits"])
        self.assertEqual(result, 0)
        self.assertIn("linux-resource-limits status=passed", output)

    def test_linux独立进程配额环境跳过不计分(self) -> None:
        result, _lease_probe, score, output = self._run_linux_check_with_lease_expiry(
            SimpleNamespace(status="passed", detail="lease ok"),
            resource_result=SimpleNamespace(
                status="skipped", detail="resource_quota_environment_unavailable",
            ),
        )
        self.assertNotIn("resource_limits", score.call_args.kwargs)
        self.assertEqual(result, 0)
        self.assertIn("linux-resource-limits status=skipped", output)

    def test_linux独立进程配额回归失败时native作业失败(self) -> None:
        result, _lease_probe, score, output = self._run_linux_check_with_lease_expiry(
            SimpleNamespace(status="passed", detail="lease ok"),
            resource_result=SimpleNamespace(
                status="failed", detail="native_process_quota_mismatch",
            ),
        )
        self.assertNotIn("resource_limits", score.call_args.kwargs)
        self.assertEqual(result, 1)
        self.assertIn("linux-resource-limits status=failed", output)
        self.assertIn("resource limits: native process quota mismatch", output)

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
