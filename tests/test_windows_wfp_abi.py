"""Test-only ABI gate before any Windows WFP event decoding is attempted."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import unittest


_EXPECTED_64BIT_WINDOWS_LAYOUT = {
    "subscription.size": 32,
    "subscription.enum_template": 0,
    "subscription.flags": 8,
    "subscription.session_key": 12,
    "header.size": 136,
    "header.flags": 8,
    "header.ip_version": 12,
    "header.ip_protocol": 16,
    "header.local_address": 20,
    "header.remote_address": 36,
    "header.local_port": 52,
    "header.remote_port": 54,
    "header.scope_id": 56,
    "header.app_id": 64,
    "header.user_id": 80,
    "header.address_family": 88,
    "header.package_sid": 96,
    "header.enterprise_id": 104,
    "header.policy_flags": 112,
    "header.effective_name": 120,
    "event.size": 152,
    "event.type": 136,
    "event.capability_drop": 144,
    "capability_drop.size": 24,
    "capability_drop.network_capability_id": 0,
    "capability_drop.filter_id": 8,
    "capability_drop.is_loopback": 16,
}


def _probe_module(test: unittest.TestCase):
    module_spec = importlib.util.find_spec("tests.windows_wfp_abi_probe")
    test.assertIsNotNone(
        module_spec,
        "Windows WFP ctypes layout probe is required before event decoding",
    )
    return importlib.import_module("tests.windows_wfp_abi_probe")


class TestWindowsWfpAbi(unittest.TestCase):
    def test_visual_studio_architecture_names_match_supported_target_and_host_values(self) -> None:
        probe = _probe_module(self)
        self.assertEqual(
            probe._visual_studio_architectures("x64", "AMD64"),
            ("amd64", "amd64"),
        )
        self.assertEqual(
            probe._visual_studio_architectures("ARM64", "ARM64"),
            ("arm64", "amd64"),
        )
        with self.assertRaisesRegex(RuntimeError, "unsupported_windows_runner_architecture"):
            probe._visual_studio_architectures("x86", "x86")

    def test_compiler_batch_stages_visual_studio_setup_and_compile_safely(self) -> None:
        probe = _probe_module(self)
        script = probe._build_visual_studio_batch_script(
            r"C:\Program Files\Microsoft Visual Studio\18\Enterprise\Common7\Tools\VsDevCmd.bat",
            "amd64",
            "amd64",
        )
        self.assertIn(
            'call "C:\\Program Files\\Microsoft Visual Studio\\18\\Enterprise\\Common7\\Tools\\VsDevCmd.bat" '
            "-arch=amd64 -host_arch=amd64 >NUL 2>NUL",
            script,
        )
        self.assertIn("if errorlevel 1 exit /b 91", script)
        self.assertIn("where.exe cl >NUL 2>NUL", script)
        self.assertIn("if errorlevel 1 exit /b 92", script)
        self.assertIn(
            "cl /nologo /W0 /Fewfp_sdk_layout_probe.exe wfp_sdk_layout_probe.c",
            script,
        )

    def test_ipv6_loopback_observer_uses_narrow_read_only_event_scope(self) -> None:
        repository_root = os.path.dirname(os.path.dirname(__file__))
        source_path = os.path.join(
            repository_root, "native", "windows", "icode_wfp_event_probe.c",
        )
        with open(source_path, encoding="utf-8") as source_file:
            source = source_file.read()

        for required_contract in (
            "--collect-ipv6-loopback",
            "FWPM_CONDITION_NET_EVENT_TYPE",
            "FWPM_NET_EVENT_TYPE_CAPABILITY_DROP",
            "FWP_V6_ADDR_MASK",
            "prefixLength = 128",
            "FWP_IP_VERSION_V6",
            "header->remoteAddrV6",
            "expected_loopback",
        ):
            with self.subTest(contract=required_contract):
                self.assertIn(required_contract, source)
        self.assertNotIn("FwpmEngineSetOption", source)

    def test_unsubscribe_failure_terminates_helper_before_releasing_callback_state(self) -> None:
        repository_root = os.path.dirname(os.path.dirname(__file__))
        source_path = os.path.join(
            repository_root, "native", "windows", "icode_wfp_event_probe.c",
        )
        with open(source_path, encoding="utf-8") as source_file:
            source = source_file.read()

        collector_start = source.index("static int run_collector(")
        collector_end = source.index("\nint wmain(", collector_start)
        collector = source[collector_start:collector_end]
        cleanup = collector.split("\ncleanup:\n", 1)[1]
        unsubscribe_call = cleanup.index("FwpmNetEventUnsubscribe0")
        unsubscribe_failure = cleanup.index(
            "if (api_result != ERROR_SUCCESS)", unsubscribe_call,
        )
        process_terminate = cleanup.index(
            "TerminateProcess(GetCurrentProcess(), ERROR_GEN_FAILURE);",
            unsubscribe_failure,
        )
        process_exit = cleanup.index(
            "ExitProcess(ERROR_GEN_FAILURE);", process_terminate,
        )
        engine_close = cleanup.index("FwpmEngineClose0", unsubscribe_failure)
        sid_free = cleanup.index("FreeSid(expected_sid)", unsubscribe_failure)

        self.assertLess(unsubscribe_call, unsubscribe_failure)
        self.assertLess(unsubscribe_failure, process_terminate)
        self.assertLess(process_terminate, process_exit)
        self.assertLess(process_exit, engine_close)
        self.assertLess(process_exit, sid_free)

    def test_subscription_return_code_is_preserved_in_bounded_native_receipt(self) -> None:
        repository_root = os.path.dirname(os.path.dirname(__file__))
        source_path = os.path.join(
            repository_root, "native", "windows", "icode_wfp_event_probe.c",
        )
        with open(source_path, encoding="utf-8") as source_file:
            source = source_file.read()

        call = source.index(
            "subscription_return_code = FwpmNetEventSubscribe2("
        )
        self.assertLess(
            source.index("subscription_attempted = TRUE;", call - 128), call,
        )
        self.assertIn(r'\"subscription_attempted\":%s', source)
        self.assertIn(r'\"subscription_return_code\":%s', source)
        self.assertIn(r'\"subscription_handle_present\":%s', source)
        self.assertIn(r'\"schema_version\":7', source)
        self.assertIn(r'\"schema_version\":6', source)

    def test_runner_permission_probe_creates_and_removes_only_its_profile(self) -> None:
        repository_root = os.path.dirname(os.path.dirname(__file__))
        source_path = os.path.join(
            repository_root, "native", "windows", "icode_wfp_event_probe.c",
        )
        with open(source_path, encoding="utf-8") as source_file:
            source = source_file.read()

        self.assertIn("--probe-runner-subscription", source)
        probe_start = source.index("static int run_runner_subscription_probe(")
        probe_end = source.index("\nint wmain(", probe_start)
        probe = source[probe_start:probe_end]
        create = probe.index("CreateAppContainerProfile(")
        success_guard = probe.index("if (create_result != S_OK", create)
        create_call = probe[create:success_guard]
        self.assertIn("NULL,\n        0,", create_call)
        create_failure_end = probe.index("if (created_sid == NULL", success_guard)
        collector = probe.index("probe_result = run_collector(", create_failure_end)
        free_sid = probe.index("FreeSid(created_sid)", collector)
        delete = probe.index("DeleteAppContainerProfile(", free_sid)

        self.assertLess(create, success_guard)
        self.assertLess(success_guard, collector)
        self.assertLess(collector, free_sid)
        self.assertLess(free_sid, delete)
        self.assertIn(
            "return RUNNER_PROBE_UNAVAILABLE;",
            probe[success_guard:create_failure_end],
        )
        self.assertNotIn("DeleteAppContainerProfile(", probe[success_guard:create_failure_end])
        self.assertIn("delete_result != S_OK", probe[delete:])
        self.assertIn("RUNNER_PROBE_PROFILE_CLEANUP_FAILED", probe[delete:])
        self.assertIn("return probe_result;", probe[delete:])

    def test_sdk_compile_failure_classification_does_not_return_raw_output(self) -> None:
        probe = _probe_module(self)
        classify = probe._classify_windows_sdk_compile_failure
        self.assertEqual(classify("", 91), "visual_studio_environment_setup_failed")
        self.assertEqual(classify("", 92), "compiler_unavailable_after_setup")
        self.assertEqual(
            classify("'cl' is not recognized as an internal or external command", 1),
            "compiler_unavailable",
        )
        self.assertEqual(
            classify("fatal error C1083: Cannot open include file: 'fwpmu.h'", 2),
            "windows_sdk_header_unavailable",
        )
        self.assertEqual(
            classify("wfp_sdk_layout_probe.c(12): error C2065: unknown identifier", 2),
            "sdk_declaration_compile_error",
        )
        self.assertEqual(
            classify("D:\\a\\icode\\private-runner-path\\failure", 2),
            "compiler_failed_without_diagnostic",
        )

    def test_ctypes_layout_matches_documented_64bit_windows_sdk_abi(self) -> None:
        if sys.maxsize <= 2**32:
            self.skipTest("the WFP diagnostic targets 64-bit Windows runners")
        probe = _probe_module(self)
        self.assertEqual(
            probe.ctypes_layout_snapshot(),
            _EXPECTED_64BIT_WINDOWS_LAYOUT,
        )

    @unittest.skipUnless(
        sys.platform == "win32" and os.environ.get("GITHUB_ACTIONS") == "true",
        "Windows SDK ABI cross-check runs on native GitHub Windows jobs",
    )
    def test_native_windows_sdk_layout_matches_ctypes_layout(self) -> None:
        probe = _probe_module(self)
        sdk_layout = probe.run_windows_sdk_layout_probe()
        self.assertEqual(sdk_layout, _EXPECTED_64BIT_WINDOWS_LAYOUT)
        self.assertEqual(sdk_layout, probe.ctypes_layout_snapshot())


if __name__ == "__main__":
    unittest.main()
