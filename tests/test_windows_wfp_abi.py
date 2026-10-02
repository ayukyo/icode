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

    def test_sdk_compile_failure_classification_does_not_return_raw_output(self) -> None:
        probe = _probe_module(self)
        classify = probe._classify_windows_sdk_compile_failure
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
