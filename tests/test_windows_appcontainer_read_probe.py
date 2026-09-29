from __future__ import annotations

import unittest
from dataclasses import replace

from scripts.run_windows_appcontainer_read_probe import (
    _DaclSnapshot,
    _format_network_error,
    _normalize_inherited_ace_flag,
    _safe_diagnostics,
    _workspace_dacl_entries_equivalent,
)


class TestWindowsAppContainerReadProbe(unittest.TestCase):
    def test_network_error_diagnostic_accepts_only_bounded_integer_codes(self) -> None:
        self.assertEqual(_format_network_error(10013), "10013")
        self.assertEqual(_format_network_error(10051), "10051")

        for value in (None, "10013", True, -1, 65536):
            with self.subTest(value=value):
                self.assertEqual(_format_network_error(value), "unknown")

    def test_safe_diagnostics_rejects_sid_shaped_values(self) -> None:
        self.assertEqual(
            _safe_diagnostics("stage=5; package_sid=S-1-15-2-123"),
            "stage=5",
        )
        self.assertEqual(_safe_diagnostics("S-1-15-2-123"), "none")

    def test_inherited_ace_normalization_changes_only_the_inherited_marker(self) -> None:
        ace = b"\x00\x13\x08\x00ABCD"
        self.assertEqual(
            _normalize_inherited_ace_flag(ace),
            b"\x00\x03\x08\x00ABCD",
        )
        with self.assertRaises(ValueError):
            _normalize_inherited_ace_flag(b"\x00\x10\x08\x00")

    def test_dacl_equivalence_allows_only_auto_inheritance_metadata_delta(self) -> None:
        original = _DaclSnapshot(
            descriptor_digest="before",
            acl_digest="raw-before",
            normalized_acl_digest="normalized",
            control=0x8004,
            revision=1,
            present=True,
            defaulted=False,
            ace_count=3,
            inherited_ace_count=1,
            acl_bytes_in_use=88,
        )
        auto_inherited = replace(
            original,
            descriptor_digest="after",
            acl_digest="raw-after",
            control=0x8404,
        )

        self.assertTrue(
            _workspace_dacl_entries_equivalent(original, auto_inherited),
        )
        self.assertFalse(
            _workspace_dacl_entries_equivalent(
                original, replace(auto_inherited, control=0x8804),
            ),
        )
        self.assertFalse(
            _workspace_dacl_entries_equivalent(auto_inherited, original),
        )
        self.assertFalse(
            _workspace_dacl_entries_equivalent(
                original, replace(auto_inherited, normalized_acl_digest="different"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
