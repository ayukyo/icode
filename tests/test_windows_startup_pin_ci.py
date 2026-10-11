"""CI selection and skip enforcement; no simulated Windows OS credit."""

import importlib
import io
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from scripts import run_workspace_ci as ci


PORTABLE_CLASSES = (
    "tests.test_windows_startup_pin.StartupPinInterfaceTests",
    "tests.test_windows_startup_pin.StartupPinTests",
    "tests.test_windows_startup_native.NativeTransportTests",
    "tests.test_windows_startup_native.NativeModuleTests",
    "tests.test_windows_startup_security.StartupSecurityInterfaceTests",
    "tests.test_windows_startup_security.StartupSecurityParserTests",
    "tests.test_windows_startup_security.StartupSecurityPolicyTests",
    "tests.test_windows_startup_security_native.SecurityReaderConstructorTests",
    "tests.test_windows_startup_security_native.SecurityReaderInterfaceTests",
    "tests.test_windows_startup_security_native.SecurityReaderTransportTests",
    "tests.test_windows_startup_host_identity.HostIdentityInterfaceTests",
    "tests.test_windows_startup_host_identity.HostIdentityConstructorTests",
    "tests.test_windows_startup_host_identity.HostIdentityTransportTests",
    "tests.test_windows_installed_chain.InstalledLocatorPolicyTests",
    "tests.test_windows_installed_chain.InstalledChainInterfaceTests",
    "tests.test_windows_installed_chain.InstalledObservationTests",
    "tests.test_windows_installed_chain.InstalledProbeTests",
    "tests.test_windows_installed_chain.InstalledWireTests",
    "tests.test_windows_installed_chain.InstalledCliTests",
    "tests.test_windows_startup_source.SourceInterfaceTests",
    "tests.test_windows_startup_source.SourceLocatorTests",
    "tests.test_windows_startup_source.SourceOwnerTests",
    "tests.test_windows_installed_source.SourceProbeInterfaceTests",
    "tests.test_windows_installed_source.SourceReceiptTests",
    "tests.test_windows_installed_source.SourceConsumerObservationTests",
    "tests.test_windows_installed_source.SourceObservationLedgerTests",
    "tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests",
    "tests.test_windows_private_dacl_window.PrivateDaclTransportTests",
    "tests.test_windows_private_dacl_window.PrivateDaclNativeApiTests",
    "tests.test_windows_private_dacl_window.PrivateDaclWindowContractTests",
    "tests.test_windows_private_dacl_window.PrivateDaclLifecycleTests",
    "tests.test_windows_private_sibling_window.PrivateSiblingPortableTests",
)
NATIVE_CLASS = "tests.test_windows_startup_native.WindowsEnforcementTests"
NATIVE_SECURITY_CLASS = "tests.test_windows_startup_native.WindowsSecurityQueryTests"
NATIVE_IDENTITY_CLASS = "tests.test_windows_startup_host_identity.WindowsHostIdentityTests"
NATIVE_DACL_CLASS = "tests.test_windows_private_dacl_window.WindowsPrivateDaclWindowNativeTests"
NATIVE_SIBLING_CLASS = "tests.test_windows_private_sibling_window.WindowsPrivateSiblingWindowNativeTests"
NATIVE_CLASSES = (NATIVE_CLASS, NATIVE_SECURITY_CLASS, NATIVE_IDENTITY_CLASS, NATIVE_DACL_CLASS,
                  NATIVE_SIBLING_CLASS)
NATIVE_COUNTS = (6, 3, 2, 2, 2)
PORTABLE_COUNTS = (1, 32, 30, 3, 2, 24, 17, 2, 2, 16, 1, 4, 32, 7, 1, 16, 7, 11, 4, 3, 3, 18,
                   1, 6, 21, 5, 6, 5, 11, 3, 13, 18)
GUARD_MODULE = "tests.test_windows_startup_pin_ci"


def cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from cases(test)
        else:
            yield test


class StartupPinCiTests(unittest.TestCase):
    def test_native_host_identity_methods_exist(self):
        module = importlib.import_module("tests.test_windows_startup_host_identity")
        test_class = getattr(module, "WindowsHostIdentityTests", None)
        self.assertTrue(isinstance(test_class, type), "missing native host identity class")
        self.assertEqual(unittest.defaultTestLoader.getTestCaseNames(test_class), [
            "test_capture_repeated_matches_independent_os_sid_and_closes",
            "test_token_user_abi_matches_native_64_bit_layout",
        ])

    def run_ci(self, selections):
        results = []

        class ObservingRunner:
            def run(self, suite):
                result = unittest.TestResult()
                suite.run(result)
                results.append(result)
                return result

        with patch.object(ci.unittest, "TextTestRunner", return_value=ObservingRunner()), redirect_stderr(io.StringIO()):
            code = ci.main(tuple(selections))
        self.assertEqual(len(results), 1)
        return code, results[0]

    def test_default_selects_complete_pin_contract_once(self):
        expected = []
        self.assertEqual(len(PORTABLE_CLASSES), len(PORTABLE_COUNTS))
        for class_id, count in zip(PORTABLE_CLASSES, PORTABLE_COUNTS):
            loaded = list(cases(unittest.defaultTestLoader.loadTestsFromName(class_id)))
            self.assertEqual(len(loaded), count)
            for test in loaded:
                self.assertFalse(getattr(type(test), "__unittest_skip__", False))
                self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))
            expected.extend(test.id() for test in loaded)
        self.assertEqual(len(NATIVE_CLASSES), len(NATIVE_COUNTS))
        for class_id, count in zip(NATIVE_CLASSES, NATIVE_COUNTS):
            native = list(cases(unittest.defaultTestLoader.loadTestsFromName(class_id)))
            self.assertEqual(len(native), count)
            if os.name == "nt":
                expected.extend(test.id() for test in native)
        selected = [test.id() for entry in ci.DEFAULT_MODULES
                    if entry.startswith(("tests.test_windows_startup_pin.", "tests.test_windows_startup_native.",
                                         "tests.test_windows_startup_security.", "tests.test_windows_startup_security_native.",
                                         "tests.test_windows_startup_host_identity.", "tests.test_windows_installed_chain",
                                         "tests.test_windows_startup_source",
                                         "tests.test_windows_installed_source",
                                         "tests.test_windows_private_dacl_window.",
                                         "tests.test_windows_private_sibling_window.",
                                         "tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests"))
                    for test in cases(unittest.defaultTestLoader.loadTestsFromName(entry))]
        self.assertCountEqual(selected, expected)
        self.assertEqual(ci.DEFAULT_MODULES.count(GUARD_MODULE), 1)
        self.assertEqual(ci.DEFAULT_MODULES.count("tests.test_windows_installed_chain"), 1)
        self.assertEqual(ci.DEFAULT_MODULES.count("tests.test_windows_startup_source"), 1)
        self.assertEqual(ci.DEFAULT_MODULES.count("tests.test_windows_installed_source"), 1)
        self.assertEqual(ci.DEFAULT_MODULES.count("tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests"), 1)
        guard_ids = [test.id() for entry in ci.DEFAULT_MODULES
                     if entry == GUARD_MODULE or entry.startswith(GUARD_MODULE + ".")
                     for test in cases(unittest.defaultTestLoader.loadTestsFromName(entry))]
        self.assertCountEqual(guard_ids, [test.id() for test in cases(
            unittest.defaultTestLoader.loadTestsFromName(GUARD_MODULE))])

    def test_platform_selection_loads_portable_and_windows_leaves_exactly_once(self):
        select = getattr(ci, "startup_pin_tests", None)
        self.assertTrue(callable(select), "missing platform startup pin selector")
        portable = [test.id() for name in PORTABLE_CLASSES
                    for test in cases(unittest.defaultTestLoader.loadTestsFromName(name))]
        native = [test.id() for name in NATIVE_CLASSES
                  for test in cases(unittest.defaultTestLoader.loadTestsFromName(name))]
        for platform in ("posix", "nt"):
            selected = [test.id() for name in select(platform)
                        for test in cases(unittest.defaultTestLoader.loadTestsFromName(name))]
            self.assertCountEqual(selected, portable + (native if platform == "nt" else []))
            self.assertEqual(len(selected), len(set(selected)))

    def test_every_pin_method_body_skip_is_required(self):
        for class_id in (*PORTABLE_CLASSES, *NATIVE_CLASSES, GUARD_MODULE + ".StartupPinCiTests"):
            module_id, class_name = class_id.rsplit(".", 1)
            test_class = getattr(importlib.import_module(module_id), class_name)
            for method in unittest.defaultTestLoader.getTestCaseNames(test_class):
                def skip_body(_case):
                    raise unittest.SkipTest("required pin body unavailable")
                with self.subTest(method=class_id + "." + method), patch.object(
                    test_class, "__unittest_skip__", False, create=True
                ), patch.object(test_class, "setUp", lambda _case: None), patch.object(test_class, method, skip_body):
                    for selection in (class_id + "." + method, class_id, module_id):
                        suite = unittest.defaultTestLoader.loadTestsFromName(class_id + "." + method)
                        with patch.object(ci.unittest.defaultTestLoader, "loadTestsFromNames", return_value=suite):
                            code, result = self.run_ci((selection,))
                        self.assertEqual(code, 1)
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [])
                        self.assertEqual(result.failures, [])
                        self.assertEqual(len(result.skipped), 1)

    def test_pin_fixture_skips_fail_for_method_class_and_module_selections(self):
        for class_id in (*PORTABLE_CLASSES, *NATIVE_CLASSES, GUARD_MODULE + ".StartupPinCiTests"):
            module_id, class_name = class_id.rsplit(".", 1)
            module = importlib.import_module(module_id)
            test_class = getattr(module, class_name)
            method = unittest.defaultTestLoader.getTestCaseNames(test_class)[0]
            for selection in (class_id + "." + method, class_id, module_id):
                for fixture in ("setUp", "tearDown", "setUpClass", "tearDownClass", "setUpModule", "tearDownModule"):
                    def skip_fixture(*_args):
                        raise unittest.SkipTest("required pin fixture unavailable")
                    target = module if fixture.endswith("Module") else test_class
                    replacement = classmethod(skip_fixture) if fixture.endswith("Class") else skip_fixture
                    # Only fixture classification is under test; suppress bodies
                    # and Windows setup so no Windows call is faked as native.
                    with self.subTest(selection=selection, fixture=fixture), patch.object(
                        test_class, "__unittest_skip__", False, create=True
                    ), patch.object(test_class, "setUp", lambda _case: None), patch.object(
                        target, fixture, replacement, create=True
                    ):
                        # Narrow the loaded suite to real class/method leaves;
                        # retain the caller's class/module selector for required detection.
                        suite = unittest.defaultTestLoader.loadTestsFromName(class_id + "." + method)
                        with patch.object(test_class, method, lambda _case: None), patch.object(
                            ci.unittest.defaultTestLoader, "loadTestsFromNames", return_value=suite
                        ):
                            code, result = self.run_ci((selection,))
                        self.assertEqual(code, 1)
                        self.assertEqual(result.errors, [])
                        self.assertEqual(result.failures, [])
                        self.assertEqual(len(result.skipped), 1)

    def test_real_class_and_module_loader_cannot_hide_required_skip(self):
        for class_id, count in ((PORTABLE_CLASSES[0], 1),
                                ("tests.test_windows_installed_chain.InstalledProbeTests", 7),
                                ("tests.test_windows_startup_source.SourceOwnerTests", 18),
                                ("tests.test_windows_installed_source.SourceConsumerObservationTests", 21),
                                ("tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests", 6),
                                *zip(PORTABLE_CLASSES[-5:-1], PORTABLE_COUNTS[-5:-1]),
                                (PORTABLE_CLASSES[-1], 18),
                                (NATIVE_DACL_CLASS, 2), (NATIVE_SIBLING_CLASS, 2)):
            module_id, class_name = class_id.rsplit(".", 1)
            module = importlib.import_module(module_id)
            test_class = getattr(module, class_name)
            with self.subTest(class_id=class_id), patch.object(test_class, "__unittest_skip__", True, create=True):
                code, result = self.run_ci((class_id,))
            self.assertEqual(code, 1)
            self.assertEqual(result.testsRun, count)
            self.assertEqual(len(result.skipped), count)

        def skip_fixture():
            raise unittest.SkipTest("required module unavailable")

        for module_id in ("tests.test_windows_startup_pin", "tests.test_windows_startup_native",
                          "tests.test_windows_startup_security", "tests.test_windows_startup_security_native",
                          "tests.test_windows_startup_host_identity", "tests.test_windows_installed_chain",
                          "tests.test_windows_startup_source", "tests.test_windows_installed_source",
                          "tests.test_windows_private_dacl_window",
                          "tests.test_windows_private_sibling_window"):
            module = importlib.import_module(module_id)
            with patch.object(module, "setUpModule", skip_fixture, create=True):
                code, result = self.run_ci((module_id,))
            self.assertEqual(code, 1)
            self.assertEqual(result.testsRun, 0)
            self.assertEqual(len(result.skipped), 1)
            self.assertEqual(result.errors, [])

    def test_real_portable_class_and_module_selections_run_without_skip(self):
        for selection, count in (*zip(PORTABLE_CLASSES, PORTABLE_COUNTS),
                                 ("tests.test_windows_startup_pin", 33),
                                 ("tests.test_windows_startup_security", 43),
                                 ("tests.test_windows_startup_security_native", 20),
                                 ("tests.test_windows_installed_chain", 46),
                                 ("tests.test_windows_startup_source", 24),
                                 ("tests.test_windows_installed_source", 33)):
            with self.subTest(selection=selection):
                code, result = self.run_ci((selection,))
                self.assertEqual(code, 0)
                self.assertEqual(result.testsRun, count)
                self.assertEqual(result.skipped, [])
                self.assertEqual(result.errors, [])
                self.assertEqual(result.failures, [])

    def test_missing_method_load_error_cannot_succeed(self):
        code, result = self.run_ci((PORTABLE_CLASSES[0] + ".test_missing_required_pin",))
        self.assertEqual(code, 1)
        self.assertEqual(len(result.errors), 1)

    def test_private_dacl_module_platform_skip_never_receives_native_credit(self):
        module_id = "tests.test_windows_private_dacl_window"
        module = importlib.import_module(module_id)
        native = module.WindowsPrivateDaclWindowNativeTests
        # skipUnless returns the undecorated class on Windows: no skip attribute.
        missing = object()
        original = native.__dict__.get("__unittest_skip__", missing)
        try:
            if original is not missing:
                del native.__unittest_skip__
            with patch.object(native, "__unittest_skip__", True, create=True):
                code, result = self.run_ci((module_id,))
        finally:
            if original is not missing:
                native.__unittest_skip__ = original
            elif "__unittest_skip__" in native.__dict__:
                del native.__unittest_skip__
        self.assertIs(native.__dict__.get("__unittest_skip__", missing), original)
        self.assertEqual(result.testsRun, 34)
        self.assertEqual(len(result.skipped), 2)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
        self.assertEqual(code, 1)

    def test_private_sibling_module_platform_skip_never_receives_native_credit(self):
        module_id = "tests.test_windows_private_sibling_window"
        module = importlib.import_module(module_id)
        native = module.WindowsPrivateSiblingWindowNativeTests
        missing = object()
        original = native.__dict__.get("__unittest_skip__", missing)
        try:
            if original is not missing:
                del native.__unittest_skip__
            with patch.object(native, "__unittest_skip__", True, create=True):
                code, result = self.run_ci((module_id,))
        finally:
            if original is not missing:
                native.__unittest_skip__ = original
            elif "__unittest_skip__" in native.__dict__:
                del native.__unittest_skip__
        self.assertIs(native.__dict__.get("__unittest_skip__", missing), original)
        self.assertEqual(result.testsRun, 20)
        self.assertEqual(len(result.skipped), 2)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
        self.assertEqual(code, 1)

    def test_required_subtest_and_nested_subtest_skips_fail(self):
        for class_id in (*PORTABLE_CLASSES, *NATIVE_CLASSES, GUARD_MODULE + ".StartupPinCiTests"):
            module_id, class_name = class_id.rsplit(".", 1)
            test_class = getattr(importlib.import_module(module_id), class_name)
            method = unittest.defaultTestLoader.getTestCaseNames(test_class)[0]
            parent_id = class_id + "." + method
            for nested in (False, True):
                def skip_subtest(case):
                    with case.subTest(required_case="unavailable (x=y)", values=("a", "b")):
                        if nested:
                            with case.subTest(inner="(nested), key=value"):
                                case.skipTest("required nested pin subtest unavailable")
                        else:
                            case.skipTest("required pin subtest unavailable")
                with self.subTest(parent_id=parent_id, nested=nested), patch.object(
                    test_class, "__unittest_skip__", False, create=True
                ), patch.object(test_class, "setUp", lambda _case: None), patch.object(test_class, method, skip_subtest):
                    for selection in (parent_id, class_id, module_id):
                        suite = unittest.defaultTestLoader.loadTestsFromName(parent_id)
                        with patch.object(ci.unittest.defaultTestLoader, "loadTestsFromNames", return_value=suite):
                            code, result = self.run_ci((selection,))
                        self.assertEqual(result.testsRun, 1)
                        self.assertEqual(result.errors, [])
                        self.assertEqual(result.failures, [])
                        self.assertEqual(len(result.skipped), 1)
                        skipped = result.skipped[0][0]
                        self.assertNotEqual(skipped.id(), parent_id)
                        self.assertIsInstance(skipped.test_case, unittest.TestCase)
                        self.assertEqual(skipped.test_case.id(), parent_id)
                        self.assertEqual(code, 1)

    def test_optional_nested_subtest_skip_remains_successful(self):
        module = importlib.import_module("tests.test_contract_engineering")
        test_class = module.TestContractEngineering
        method = "test_policy_code_missing_plan_refuses_before_control_write_and_model"
        def skip_subtest(case):
            with case.subTest(optional="(outer), x=y"):
                with case.subTest(inner="unavailable", values=(1, 2)):
                    case.skipTest("optional nested subtest unavailable")
        with patch.object(test_class, "setUp", lambda _case: None), patch.object(test_class, method, skip_subtest):
            code, result = self.run_ci(("tests.test_contract_engineering.TestContractEngineering." + method,))
        self.assertEqual(code, 0)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])

    def test_existing_optional_body_and_fixture_skip_remain_successful(self):
        module = importlib.import_module("tests.test_contract_engineering")
        test_class = module.TestContractEngineering
        method = "test_policy_code_missing_plan_refuses_before_control_write_and_model"
        selected = "tests.test_contract_engineering.TestContractEngineering." + method
        def skip(*_args):
            raise unittest.SkipTest("optional dependency unavailable")
        for fixture in (None, "setUpClass", "tearDownClass", "setUpModule", "tearDownModule"):
            with self.subTest(fixture=fixture), patch.object(test_class, "setUp", lambda _case: None), patch.object(
                test_class, method, skip if fixture is None else lambda _case: None
            ):
                if fixture is None:
                    code, result = self.run_ci((selected,))
                else:
                    target = test_class if fixture.endswith("Class") else module
                    replacement = classmethod(skip) if fixture.endswith("Class") else skip
                    with patch.object(target, fixture, replacement, create=True):
                        code, result = self.run_ci((selected,))
                self.assertEqual(code, 0)
                self.assertEqual(len(result.skipped), 1)
                self.assertEqual(result.errors, [])

    def test_old_binding_class_and_host_compiler_remain_optional(self):
        module = importlib.import_module("tests.test_windows_bootstrap_binding")
        for class_name in ("TestWindowsBootstrapBinding", "TestWindowsBootstrapBindingHostCompiler"):
            test_class = getattr(module, class_name)
            method = unittest.defaultTestLoader.getTestCaseNames(test_class)[0]
            selected = "tests.test_windows_bootstrap_binding." + class_name + "." + method
            def skip(*_args):
                raise unittest.SkipTest("old optional binding unavailable")
            for fixture in (None, "setUpClass", "tearDownClass", "setUpModule", "tearDownModule"):
                with self.subTest(class_name=class_name, fixture=fixture), patch.object(
                    test_class, "__unittest_skip__", False, create=True
                ), patch.object(test_class, "setUp", lambda _case: None), patch.object(
                    test_class, method, skip if fixture is None else lambda _case: None
                ):
                    if fixture is None:
                        code, result = self.run_ci((selected,))
                    else:
                        target = test_class if fixture.endswith("Class") else module
                        replacement = classmethod(skip) if fixture.endswith("Class") else skip
                        with patch.object(target, fixture, replacement, create=True):
                            code, result = self.run_ci((selected,))
                    self.assertEqual(code, 0)
                    self.assertEqual(len(result.skipped), 1)
                    self.assertEqual(result.errors, [])
                    self.assertEqual(result.failures, [])
