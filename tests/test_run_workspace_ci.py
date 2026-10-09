"""跨平台 workspace workflow 的测试覆盖合同。"""

from __future__ import annotations

import io
import importlib
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from scripts import run_workspace_ci
from scripts.run_workspace_ci import CROSS_PLATFORM_R3_TESTS, DEFAULT_MODULES


class TestWorkspaceCiCoverage(unittest.TestCase):
    def test_operation_admission_methods_selected_once_required_and_never_static_skipped(self):
        definitions = (
            ("tests.test_operation_admission", "TestOperationAdmissionProtocol", 5),
            ("tests.test_operation_admission", "TestOperationAdmissionRealCP", 7),
        )
        expected = set()
        classes = {}
        for module_name, class_name, count in definitions:
            test_class = getattr(importlib.import_module(module_name), class_name)
            methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
            self.assertEqual(len(methods), count)
            self.assertFalse(getattr(test_class, "__unittest_skip__", False))
            for method in methods:
                test_id = module_name + "." + class_name + "." + method
                expected.add(test_id)
                classes[test_id] = test_class
                self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))
        for method in (
            "test_open_operation_replay_refuses_before_host_payload_without_closing",
            "test_early_admission_failure_and_exact_replay_keep_old_error_categories",
        ):
            test_id = "tests.test_contract_engineering.TestContractEngineering." + method
            expected.add(test_id)
            classes[test_id] = importlib.import_module("tests.test_contract_engineering").TestContractEngineering
        self.assertEqual(len(expected), 14)
        self.assertTrue(hasattr(run_workspace_ci, "OPERATION_ADMISSION_TESTS"))
        declared = run_workspace_ci.OPERATION_ADMISSION_TESTS
        self.assertEqual(set(declared), expected)
        self.assertEqual(len(declared), len(expected))

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        selected = [
            test for entry in run_workspace_ci.DEFAULT_MODULES
            for test in cases(unittest.defaultTestLoader.loadTestsFromName(entry))
            if test.id() in expected or test.id().startswith("tests.test_operation_admission.")
        ]
        self.assertEqual({test.id() for test in selected}, expected)
        self.assertEqual(len(selected), len(expected))
        for test_id in sorted(expected):
            with self.subTest(test_id=test_id):
                loaded = list(cases(unittest.defaultTestLoader.loadTestsFromName(test_id)))
                self.assertEqual(len(loaded), 1)
                self.assertIs(type(loaded[0]), classes[test_id])
                self.assertEqual(loaded[0].id(), test_id)
                self.assertFalse(getattr(getattr(loaded[0], loaded[0]._testMethodName), "__unittest_skip__", False))

                class SkippedRequiredTest(unittest.TestCase):
                    def id(self):
                        return test_id

                    def runTest(self):
                        self.skipTest("simulated missing admission dependency")

                with patch.object(
                    run_workspace_ci.unittest.defaultTestLoader,
                    "loadTestsFromNames",
                    return_value=unittest.TestSuite([SkippedRequiredTest()]),
                ), redirect_stderr(io.StringIO()):
                    self.assertEqual(run_workspace_ci.main((test_id,)), 1)

        # Run actual class setup lifecycle: required missing skill must be ERROR.
        actual = []

        class ObservingRunner:
            def run(self, suite):
                result = unittest.TestResult()
                suite.run(result)
                actual.append(result)
                return result

        selected_id = "tests.test_operation_admission.TestOperationAdmissionRealCP.test_actual_first_raw_open_replay_and_structured_next_occurrence"
        with patch(
            "tests.test_operation_admission.require_skill",
            side_effect=unittest.SkipTest("simulated required CP absent"),
        ), patch.object(run_workspace_ci.unittest, "TextTestRunner", return_value=ObservingRunner()):
            self.assertEqual(run_workspace_ci.main((selected_id,)), 1)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0].testsRun, 0)
        self.assertEqual(len(actual[0].errors), 1)
        self.assertEqual(actual[0].failures, [])
        self.assertEqual(actual[0].skipped, [])
        self.assertIn("Required admission CP fixture unavailable", actual[0].errors[0][1])

        # Existing engineering class remains optional; only selected new required methods promote holder skip.
        engineering_ids = (
            "tests.test_contract_engineering.TestContractEngineering.test_open_operation_replay_refuses_before_host_payload_without_closing",
            "tests.test_contract_engineering.TestContractEngineering.test_early_admission_failure_and_exact_replay_keep_old_error_categories",
        )
        holder_id = "setUpClass (tests.test_contract_engineering.TestContractEngineering)"
        for selected_id in engineering_ids:
            with self.subTest(required_engineering=selected_id):
                actual.clear()
                with patch(
                    "tests.test_contract_engineering.require_skill",
                    side_effect=unittest.SkipTest("simulated engineering CP absent"),
                ), patch.object(
                    run_workspace_ci.unittest, "TextTestRunner", return_value=ObservingRunner(),
                ), redirect_stderr(io.StringIO()):
                    self.assertEqual(run_workspace_ci.main((selected_id,)), 1)
                self.assertEqual(len(actual), 1)
                self.assertEqual(actual[0].testsRun, 0)
                self.assertEqual(actual[0].errors, [])
                self.assertEqual(actual[0].failures, [])
                self.assertEqual(len(actual[0].skipped), 1)
                self.assertEqual(actual[0].skipped[0][0].id(), holder_id)
                self.assertTrue(actual[0].wasSuccessful())

        # Same holder without selected new required method keeps optional semantics.
        actual.clear()
        optional_id = "tests.test_contract_engineering.TestContractEngineering.test_policy_code_missing_plan_refuses_before_control_write_and_model"
        self.assertNotIn(optional_id, run_workspace_ci.OPERATION_ADMISSION_TESTS)
        self.assertNotIn(optional_id, run_workspace_ci.POSIX_R3_TESTS)
        with patch(
            "tests.test_contract_engineering.require_skill",
            side_effect=unittest.SkipTest("simulated optional engineering CP absent"),
        ), patch.object(
            run_workspace_ci.unittest, "TextTestRunner", return_value=ObservingRunner(),
        ), redirect_stderr(io.StringIO()):
            self.assertEqual(run_workspace_ci.main((optional_id,)), 0)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0].testsRun, 0)
        self.assertEqual(actual[0].errors, [])
        self.assertEqual(actual[0].failures, [])
        self.assertEqual(len(actual[0].skipped), 1)
        self.assertEqual(actual[0].skipped[0][0].id(), holder_id)
        self.assertTrue(actual[0].wasSuccessful())

    def test_session_git_projection_methods_selected_once_and_required(self):
        module_name = "tests.test_session_git_projection"
        module = importlib.import_module(module_name)
        test_class = module.TestSessionGitProjection
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        expected = {module_name + ".TestSessionGitProjection." + method for method in methods}
        self.assertEqual(len(expected), 12)
        selected = [entry for entry in DEFAULT_MODULES if entry.startswith(module_name)]
        if os.name == "posix":
            self.assertEqual(set(selected), expected)
            self.assertEqual(len(selected), len(expected))
        else:
            self.assertEqual(selected, [])
        self.assertTrue(expected.issubset(run_workspace_ci.POSIX_R3_TESTS))
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        for test_id in sorted(expected):
            with self.subTest(test_id=test_id):
                loaded = list(cases(unittest.defaultTestLoader.loadTestsFromName(test_id)))
                self.assertEqual(len(loaded), 1)
                test = loaded[0]
                self.assertIs(type(test), test_class)
                self.assertEqual(test.id(), test_id)
                self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))

                class SkippedRequiredTest(unittest.TestCase):
                    def id(self) -> str:
                        return test_id

                    def runTest(self) -> None:
                        self.skipTest("simulated unavailable session Git support")

                suite = unittest.TestSuite([SkippedRequiredTest()])
                with patch.object(
                    run_workspace_ci.unittest.defaultTestLoader,
                    "loadTestsFromNames",
                    return_value=suite,
                ), redirect_stderr(io.StringIO()):
                    self.assertEqual(run_workspace_ci.main((test_id,)), 1)

        for method in (
            "test_split_session_gate_real_tree_reviewer_and_final_binding",
            "test_split_session_reviewer_and_final_boundary_reject_real_drift",
        ):
            test_id = "tests.test_contract_engineering.TestContractEngineering." + method
            self.assertIn(test_id, run_workspace_ci.POSIX_R3_TESTS)
            self.assertEqual(DEFAULT_MODULES.count(test_id), 1 if os.name == "posix" else 0)

    def test_python_preset_module_selected_once_completely_without_static_skips(self):
        name = "tests.test_verification_presets"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        module = importlib.import_module(name)
        test_class = getattr(module, "TestPythonUnittestPlanProvider", None)
        self.assertTrue(isinstance(test_class, type))
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        self.assertTrue(methods)
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))
        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test
        expected = {name + ".TestPythonUnittestPlanProvider." + method for method in methods}
        selected = [test for selection in DEFAULT_MODULES
                    if selection == name or selection.startswith(name + ".")
                    for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual({test.id() for test in selected}, expected)
        self.assertEqual(len(selected), len(expected))
        for test in selected:
            self.assertIs(type(test), test_class)
            self.assertFalse(getattr(type(test), "__unittest_skip__", False))
            self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))
        for old in ("tests.test_workbench", "tests.test_autonomy"):
            self.assertEqual(DEFAULT_MODULES.count(old), 1)

    def test_preset_cli_and_native_methods_are_selected_once_without_static_skips(self):
        from tests.test_workbench import TestWorkbenchCLI
        from tests.test_autonomy import TestNativePythonPreset
        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test
        for name, test_class in (("tests.test_workbench", TestWorkbenchCLI),
                                 ("tests.test_autonomy", TestNativePythonPreset)):
            self.assertEqual(DEFAULT_MODULES.count(name), 1)
            methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
            self.assertTrue(methods)
            expected = {name + "." + test_class.__name__ + "." + method for method in methods}
            selected = [test for selection in DEFAULT_MODULES
                        if selection == name or selection.startswith(name + ".")
                        for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))
                        if type(test) is test_class]
            self.assertEqual({test.id() for test in selected}, expected)
            self.assertEqual(len(selected), len(expected))
            self.assertFalse(getattr(test_class, "__unittest_skip__", False))
            for test in selected:
                self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))

    def test_backend_transport_privacy_selected_once_without_skips(self):
        name = "tests.test_backend_transport_privacy"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        module = importlib.import_module(name)
        test_class = getattr(module, "TestBackendTransportPrivacy", None)
        self.assertTrue(isinstance(test_class, type))
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        self.assertTrue(methods)
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        expected = {name + ".TestBackendTransportPrivacy." + method for method in methods}
        actual = [test for selection in DEFAULT_MODULES
                  if selection == name or selection.startswith(name + ".")
                  for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual({test.id() for test in actual}, expected)
        self.assertEqual(len(actual), len(expected))
        for test in actual:
            self.assertIs(type(test), test_class)
            self.assertFalse(getattr(type(test), "__unittest_skip__", False))
            self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))

    def test_pe_reader_portable_contract_is_selected_once_without_skips(self):
        module_name = "tests.test_windows_pe_reader"
        self.assertEqual(DEFAULT_MODULES.count(module_name), 1)
        module = importlib.import_module(module_name)
        test_class = getattr(module, "TestWindowsPeReader", None)
        self.assertTrue(isinstance(test_class, type))
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        self.assertTrue(methods)
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        expected = {module_name + ".TestWindowsPeReader." + method for method in methods}
        actual = [test for selection in DEFAULT_MODULES
                  if selection == module_name or selection.startswith(module_name + ".")
                  for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual({test.id() for test in actual}, expected)
        self.assertEqual(len(actual), len(expected))
        for test in actual:
            self.assertIs(type(test), test_class)

    def test_snapshot_rejection_diagnostic_selected_once_portably(self):
        name = "tests.test_windows_snapshot_rejection_diagnostic"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        module = importlib.import_module(name)
        test_class = getattr(module, "TestWindowsSnapshotRejectionDiagnostic", None)
        self.assertTrue(isinstance(test_class, type))
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        self.assertTrue(methods)
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))
        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test
        expected = {name + ".TestWindowsSnapshotRejectionDiagnostic." + method for method in methods}
        actual = [test.id() for selection in DEFAULT_MODULES
                  if selection == name or selection.startswith(name + ".")
                  for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(expected))

    def test_contract_git_baseline_only_uses_platform_gated_context_once(self):
        import ast
        import inspect
        import importlib.util
        import textwrap
        from contextlib import contextmanager
        from types import SimpleNamespace
        from icode import workspace_snapshot as ws, windows_worktree as ww
        from tests.test_contract_engineering import TestContractEngineering
        name = "tests.windows_snapshot_rejection_diagnostic"
        self.assertIsNotNone(importlib.util.find_spec(name), "diagnostic helper is not implemented")
        helper = importlib.import_module(name)
        context = getattr(helper, "windows_snapshot_rejection_diagnostic", None)
        self.assertTrue(callable(context), "diagnostic context is not implemented")
        source = textwrap.dedent(inspect.getsource(TestContractEngineering.gate_fixture))
        parsed = ast.parse(source)
        contexts = [node for node in ast.walk(parsed) if isinstance(node, ast.With)
                    and any(isinstance(child, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == "baseline" for target in child.targets)
                            for child in node.body)]
        self.assertEqual(len(contexts), 1, "only the initial fixture baseline must be wrapped")
        statement = contexts[0]
        self.assertEqual(len(statement.body), 1)
        self.assertEqual(len(statement.items), 1)
        self.assertIsInstance(statement.items[0].context_expr.func, ast.Name)
        self.assertEqual(statement.items[0].context_expr.func.id, "windows_snapshot_rejection_diagnostic")
        code = compile(ast.fix_missing_locations(ast.Module(body=[statement], type_ignores=[])),
                       "fixture-baseline-contract", "exec")
        originals = (ws._windows_directory_listing_signature, ws._windows_handle_signature,
                     ws._walk_windows_directory, ww._walk_windows_directory)
        for platform, git_workspace, expected in (("nt", True, True), ("nt", False, False),
                                                   ("posix", True, False), ("posix", False, False)):
            calls = []
            enabled_values = []
            root = object()
            result = {"private-name": "private-value"}
            def snapshot(received):
                calls.append(received)
                current = (ws._windows_directory_listing_signature, ws._windows_handle_signature,
                           ws._walk_windows_directory, ww._walk_windows_directory)
                self.assertEqual(current != originals, expected)
                return result
            @contextmanager
            def recording_context(*, enabled):
                enabled_values.append(enabled)
                with context(enabled=enabled, sink=lambda line: self.fail("stable fixture must not emit")):
                    yield
            namespace = dict(os=SimpleNamespace(name=platform), git_workspace=git_workspace,
                             root=root, runner=SimpleNamespace(_snapshot=snapshot),
                             windows_snapshot_rejection_diagnostic=recording_context)
            exec(code, namespace)
            self.assertIs(namespace["baseline"], result)
            self.assertEqual(calls, [root])
            self.assertEqual(enabled_values, [expected])
            self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                              ws._walk_windows_directory, ww._walk_windows_directory), originals)

    def test_pe_capture_portable_contract_is_selected_once(self) -> None:
        from tests.test_windows_pe_capture import TestWindowsPeCapture
        module = "tests.test_windows_pe_capture"
        name = module + ".TestWindowsPeCapture"
        host = module + ".TestWindowsPeCaptureHostCLI"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        self.assertNotIn(module, DEFAULT_MODULES)
        self.assertNotIn(host, DEFAULT_MODULES)

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        portable = list(cases(unittest.defaultTestLoader.loadTestsFromName(name)))
        methods = unittest.defaultTestLoader.getTestCaseNames(TestWindowsPeCapture)
        self.assertTrue(methods)
        expected = {name + "." + method for method in methods}
        self.assertEqual({test.id() for test in portable}, expected)
        selected = [test for selection in DEFAULT_MODULES if selection.startswith(module)
                    for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual(sorted(test.id() for test in selected), sorted(expected))
        for test in selected:
            self.assertIs(type(test), TestWindowsPeCapture)
            self.assertFalse(getattr(type(test), "__unittest_skip__", False))
            self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))
        host_ids = {test.id() for test in cases(unittest.defaultTestLoader.loadTestsFromName(host))}
        self.assertTrue(host_ids)
        self.assertTrue(host_ids.isdisjoint(test.id() for test in selected))

    def test_build_context_portable_contract_is_selected_once(self):
        from tests.test_windows_build_context import TestWindowsBuildContext
        name = "tests.test_windows_build_context.TestWindowsBuildContext"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        self.assertNotIn("tests.test_windows_build_context", DEFAULT_MODULES)
        self.assertNotIn(name + "HostCMake", DEFAULT_MODULES)
        methods = unittest.defaultTestLoader.getTestCaseNames(TestWindowsBuildContext)
        self.assertTrue(methods)
        self.assertFalse(getattr(TestWindowsBuildContext, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(TestWindowsBuildContext, method), "__unittest_skip__", False))

    def test_direct_volume_canary_portable_contract_is_selected_once(self):
        name = "tests.test_windows_direct_volume.TestWindowsDirectVolume"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        self.assertNotIn("tests.test_windows_direct_volume", DEFAULT_MODULES)

    def test_windows_build_binding_runs_portable_contract_once_without_host_compiler(self):
        from tests.test_windows_bootstrap_binding import TestWindowsBootstrapBinding
        name = "tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        self.assertNotIn("tests.test_windows_bootstrap_binding", DEFAULT_MODULES)
        self.assertNotIn(name + "HostCompiler", DEFAULT_MODULES)
        for method in unittest.defaultTestLoader.getTestCaseNames(TestWindowsBootstrapBinding):
            self.assertFalse(getattr(getattr(TestWindowsBootstrapBinding, method), "__unittest_skip__", False))

    def test_workspace_hook_evidence_contract_runs_on_every_platform(self) -> None:
        self.assertIn("tests.test_workspace_hook_contract", DEFAULT_MODULES)

    def test_cli_resume_sandbox_contract_runs_on_every_platform(self) -> None:
        self.assertIn("tests.test_cli_resume_sandbox", DEFAULT_MODULES)

    def test_shared_runtime_budget_contract_runs_on_every_platform(self) -> None:
        self.assertIn("tests.test_shared_runtime_budget", DEFAULT_MODULES)

    def test_rejected_post_transport_runs_on_every_platform(self) -> None:
        self.assertIn("tests.test_workbench_rejected_body", DEFAULT_MODULES)

    def test_contract_finalization_runs_once_on_every_platform(self) -> None:
        self.assertEqual(DEFAULT_MODULES.count("tests.test_contract_finalization"), 1)

    def test_host_engineering_contract_runs_once_without_optional_toolchain(self) -> None:
        for case in ("TestEngineeringVerification", "TestEngineeringAdapters", "TestEngineeringResourceDispatch"):
            self.assertEqual(DEFAULT_MODULES.count("tests.test_engineering_verification." + case), 1)
        self.assertNotIn("tests.test_engineering_verification.TestRealGoEngineeringVerification", DEFAULT_MODULES)

    def test_isolated_python_template_runs_once_without_optional_toolchain(self) -> None:
        name = "tests.test_engineering_verification.TestPythonIsolatedTemplate"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        from tests.test_engineering_verification import TestPythonIsolatedTemplate
        methods = unittest.defaultTestLoader.getTestCaseNames(TestPythonIsolatedTemplate)
        self.assertTrue(methods)
        for method in methods:
            self.assertTrue(callable(getattr(TestPythonIsolatedTemplate, method)))
            self.assertFalse(getattr(getattr(TestPythonIsolatedTemplate, method), "__unittest_skip__", False))
        self.assertNotIn("tests.test_engineering_verification", DEFAULT_MODULES)
        self.assertNotIn("tests.test_engineering_verification.TestRealGoEngineeringVerification", DEFAULT_MODULES)

    def test_engineering_evidence_contract_runs_once_on_every_platform(self) -> None:
        for case in ("TestEngineeringEvidence", "TestEngineeringReceiptValidation", "TestEngineeringEvidencePack"):
            self.assertEqual(DEFAULT_MODULES.count("tests.test_engineering_evidence." + case), 1)

    def test_contract_engineering_selection_exists_once_without_native_readiness_claim(self) -> None:
        from scripts.run_workspace_ci import CONTRACT_ENGINEERING_TESTS, POSIX_CONTRACT_ENGINEERING_TESTS
        from tests.test_contract_engineering import TestContractEngineering
        cases = unittest.defaultTestLoader.getTestCaseNames(TestContractEngineering)
        expected = {"tests.test_contract_engineering.TestContractEngineering." + name for name in cases}
        admission_engineering = {
            test_id for test_id in run_workspace_ci.OPERATION_ADMISSION_TESTS
            if test_id.startswith("tests.test_contract_engineering.TestContractEngineering.")
        }
        self.assertEqual(
            set(CONTRACT_ENGINEERING_TESTS) | set(POSIX_CONTRACT_ENGINEERING_TESTS) | admission_engineering,
            expected,
        )
        self.assertFalse(set(CONTRACT_ENGINEERING_TESTS) & set(POSIX_CONTRACT_ENGINEERING_TESTS))
        for test_id in CONTRACT_ENGINEERING_TESTS:
            self.assertEqual(DEFAULT_MODULES.count(test_id), 1)
        for test_id in POSIX_CONTRACT_ENGINEERING_TESTS:
            self.assertEqual(DEFAULT_MODULES.count(test_id), 1 if os.name == "posix" else 0)

    def test_cross_platform_matrix_selects_os_neutral_R3_regressions(self) -> None:
        self.assertEqual(len(CROSS_PLATFORM_R3_TESTS), 50)
        self.assertTrue(set(CROSS_PLATFORM_R3_TESTS).issubset(DEFAULT_MODULES))
        required_r3_evidence_tests = {
            "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_run_task证据锚定真实Git基线和含预存脏改动的快照",
            "tests.test_r3_regression.TestTaskReviewAndDiffBinding.test_SHA256基线自动选择对应tree对象格式",
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task显式参数自动绑定结果commit",
            "tests.test_r3_regression.TestResultCommitTreeBinding.test_run_task成功测试绑定受测tree和结果commit",
            "tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_cross_platform_matrix_only_names_existing_unittest_methods",
            "tests.test_evidence.TestEvidencePack.test真实task回执经CLI保存导入证据包并独立校验",
            "tests.test_evidence.TestEvidencePack.test_导出器保留JSON字符串中的Unicode行分隔符",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝非对象事件且在清理旧包前失败",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝任意事件类型的非对象payload并保留旧包",
            "tests.test_evidence.TestEvidencePack.test_非状态控制事件的空对象payload仍兼容导出和校验",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝不在SKILL枚举中的事件类型并保留旧包",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝不符合v1事件Schema的字段并保留旧包",
            "tests.test_evidence.TestEvidencePack.test_导出器拒绝缺失的工单身份且清理旧包前失败",
            "tests.test_evidence.TestEvidencePack.test_导出器不累计保留大量非产物事件payload",
            "tests.test_evidence.TestEvidencePack.test_evidence导入无效回执时返回用户错误且不触碰目标包",
            "tests.test_evidence.TestEvidencePack.test_evidence导入有限浮点回执后可生成并独立校验",
            "tests.test_evidence.TestEvidencePack.test_evidence导入最大嵌套深度回执可生成并独立校验",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器对畸形JSON结构返回失败而不抛异常",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝哈希自洽事件中的非对象payload",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝哈希自洽但未知的事件类型",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝哈希自洽但不符合v1事件Schema的包",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立Verifier接受Schema允许省略的request_id",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝证据包路径越界",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝固定成员符号链接",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器不跟随未登记的外部链接目录",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器拒绝证据包中的重复JSON成员名",
            "tests.test_evidence.TestStandaloneVerifier.test_文件摘要采用有界内存分块读取",
            "tests.test_evidence.TestStandaloneVerifier.test_event_chain校验不累计保留非产物事件payload",
            "tests.test_evidence.TestStandaloneVerifier.test_event_chain校验仍拒绝重复event_id",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝孤立代理项并接受合法代理对",
            "tests.test_evidence.TestStandaloneVerifier.test_所有Verifier拒绝非标准非有限数值",
            "tests.test_evidence.TestStandaloneVerifier.test_内置和独立校验器接受JSON字符串中的Unicode行段符号",
            "tests.test_runner.TestReviewStepReadOnlyContext.test_review阶段无隔离沙箱时命令在启动前拒绝且不产生标记",
        }
        self.assertTrue(required_r3_evidence_tests.issubset(
            CROSS_PLATFORM_R3_TESTS,
        ))
        self.assertNotIn("tests.test_r3_regression.TestResultCommitTreeBinding", DEFAULT_MODULES)

    def test_cross_platform_matrix_only_names_existing_unittest_methods(self) -> None:
        for test_id in CROSS_PLATFORM_R3_TESTS:
            module_name, class_name, method_name = test_id.rsplit(".", 2)
            test_case = getattr(importlib.import_module(module_name), class_name)
            with self.subTest(test_id=test_id):
                self.assertTrue(callable(getattr(test_case, method_name, None)))

    def test_posix_workspace_matrix_runs_native_tree_oid_git_differential(self) -> None:
        tree_differential = (
            "tests.test_r3_regression.TestWorktreeGitTreeOID."
            "test_tree_oid与Git写树一致并覆盖忽略项链接和模式"
        )
        if os.name == "posix":
            self.assertIn(tree_differential, DEFAULT_MODULES)
        else:
            self.assertNotIn(tree_differential, DEFAULT_MODULES)

    def test_required_posix_tree_oid_differential_cannot_skip(self) -> None:
        required_test_id = (
            "tests.test_r3_regression.TestWorktreeGitTreeOID."
            "test_tree_oid与Git写树一致并覆盖忽略项链接和模式"
        )

        class SkippedRequiredTest(unittest.TestCase):
            def id(self) -> str:
                return required_test_id

            def runTest(self) -> None:
                self.skipTest("simulated unavailable symlink support")

        suite = unittest.TestSuite([SkippedRequiredTest()])
        with patch.object(
            run_workspace_ci.unittest.defaultTestLoader,
            "loadTestsFromNames",
            return_value=suite,
        ):
            with redirect_stderr(io.StringIO()):
                exit_code = run_workspace_ci.main(
                    modules=(required_test_id,),
                )

        self.assertEqual(exit_code, 1)
