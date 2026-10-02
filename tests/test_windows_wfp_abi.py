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
