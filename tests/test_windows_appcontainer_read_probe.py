from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import scripts.run_windows_appcontainer_read_probe as probe_module
from scripts.run_windows_appcontainer_read_probe import (
    _DaclSnapshot,
    _dacl_state_equal,
    _format_network_error,
    _normalize_inherited_ace_flag,
    _normalize_disposable_workspace_dacl_baseline,
    _safe_diagnostics,
    _stat_is_reparse_point,
    _workspace_dacl_baseline_normalization_valid,
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
            acl_bytes=b"raw-before",
            acl_capacity_bytes=b"raw-before-capacity",
            normalized_acl_digest="normalized",
            control=0x8004,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
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

    def test_baseline_normalization_allows_only_inherited_marker_transition(self) -> None:
        original = _DaclSnapshot(
            descriptor_digest="before",
            acl_digest="raw-before",
            acl_bytes=b"ace-without-inherited-marker",
            acl_capacity_bytes=b"capacity-before-normalization",
            normalized_acl_digest="normalized",
            control=0x8004,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=0,
            acl_bytes_in_use=88,
        )
        normalized = replace(
            original,
            descriptor_digest="after",
            acl_digest="raw-after",
            acl_bytes=b"ace-with-inherited-marker",
            control=0x8404,
            inherited_ace_count=3,
        )

        self.assertTrue(
            _workspace_dacl_baseline_normalization_valid(original, normalized),
        )
        self.assertFalse(
            _workspace_dacl_baseline_normalization_valid(normalized, original),
        )
        self.assertFalse(
            _workspace_dacl_baseline_normalization_valid(
                original, replace(normalized, control=0x8804),
            ),
        )
        self.assertFalse(
            _workspace_dacl_baseline_normalization_valid(
                original, replace(normalized, file_identity=(1, 3)),
            ),
        )
        self.assertFalse(
            _workspace_dacl_baseline_normalization_valid(
                original, replace(normalized, explicit_aces=(b"changed",)),
            ),
        )

    def test_baseline_normalization_failure_codes_identify_only_mismatched_contracts(self) -> None:
        failure_codes = getattr(
            probe_module, "_workspace_dacl_baseline_normalization_failure_codes", None,
        )
        self.assertTrue(callable(failure_codes), "normalization failure classifier is missing")

        original = _DaclSnapshot(
            descriptor_digest="before",
            acl_digest="raw-before",
            acl_bytes=b"acl-before",
            acl_capacity_bytes=b"acl-capacity",
            normalized_acl_digest="normalized",
            control=0x8004,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=0,
            acl_bytes_in_use=88,
        )
        normalized = replace(original, control=0x8404)

        self.assertEqual(failure_codes(original, normalized), ())
        cases = (
            (replace(normalized, control=0x8804), ("control",)),
            (replace(normalized, control=0x9404), ("control", "protected")),
            (replace(normalized, explicit_aces=(b"changed",)), ("explicit_aces",)),
            (replace(normalized, revision=2), ("revision",)),
            (replace(normalized, present=False), ("dacl_presence",)),
            (replace(normalized, defaulted=True), ("dacl_defaulted",)),
            (replace(normalized, file_identity=(1, 3)), ("file_identity",)),
            (replace(normalized, ace_count=4), ("ace_count",)),
            (replace(normalized, acl_bytes_in_use=96), ("acl_length",)),
        )
        for changed, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(failure_codes(original, changed), expected)

    def test_baseline_normalization_allows_only_inherited_ace_additions(self) -> None:
        failure_codes = getattr(
            probe_module, "_workspace_dacl_baseline_normalization_failure_codes", None,
        )
        self.assertTrue(callable(failure_codes), "normalization failure classifier is missing")
        before = SimpleNamespace(
            control=0x8004,
            normalized_acl_digest="before-whole-dacl",
            explicit_aces=(b"explicit-a", b"explicit-b"),
            inherited_aces=(b"i" * 20,),
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            acl_bytes_in_use=88,
        )
        after = SimpleNamespace(
            control=0x8404,
            normalized_acl_digest="after-whole-dacl",
            explicit_aces=(b"explicit-a", b"explicit-b"),
            inherited_aces=(b"a" * 20, b"i" * 20, b"b" * 20),
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=5,
            acl_bytes_in_use=128,
        )

        self.assertEqual(failure_codes(before, after), ())
        self.assertEqual(
            failure_codes(
                before,
                SimpleNamespace(**{
                    **vars(after),
                    "explicit_aces": (b"changed-explicit", b"explicit-b"),
                }),
            ),
            ("explicit_aces",),
        )
        self.assertEqual(
            failure_codes(
                before,
                SimpleNamespace(**{
                    **vars(after),
                    "inherited_aces": (b"c" * 20, b"b" * 20),
                }),
            ),
            ("inherited_aces",),
        )
        reordered_before = SimpleNamespace(**{
            **vars(before),
            "inherited_aces": (b"i" * 20, b"j" * 20),
            "ace_count": 4,
            "acl_bytes_in_use": 128,
        })
        reordered_after = SimpleNamespace(**{
            **vars(after),
            "inherited_aces": (b"j" * 20, b"i" * 20, b"c" * 20),
            "ace_count": 5,
            "acl_bytes_in_use": 148,
        })
        self.assertEqual(
            failure_codes(reordered_before, reordered_after),
            ("inherited_aces",),
        )

    def test_baseline_normalization_compares_raw_ace_bytes_not_digest_surrogates(self) -> None:
        failure_codes = probe_module._workspace_dacl_baseline_normalization_failure_codes
        before = SimpleNamespace(
            control=0x8004,
            explicit_ace_digests=("same-explicit-digest",),
            inherited_ace_digests=(("same-inherited-digest", 20),),
            explicit_aces=(b"explicit-before",),
            inherited_aces=(b"inherited-before",),
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=2,
            acl_bytes_in_use=48,
        )
        after = SimpleNamespace(
            control=0x8404,
            explicit_ace_digests=("same-explicit-digest",),
            inherited_ace_digests=(("same-inherited-digest", 20),),
            explicit_aces=(b"explicit-after",),
            inherited_aces=(b"inherited-after",),
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=2,
            acl_bytes_in_use=48,
        )

        self.assertEqual(
            failure_codes(before, after),
            ("explicit_aces", "inherited_aces"),
        )

    def test_dacl_state_requires_exact_acl_bytes_and_security_control(self) -> None:
        before = _DaclSnapshot(
            descriptor_digest="layout-before",
            acl_digest="digest",
            acl_bytes=b"full-acl",
            acl_capacity_bytes=b"full-acl-capacity",
            normalized_acl_digest="normalized",
            control=0x8404,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=3,
            acl_bytes_in_use=88,
        )

        self.assertTrue(
            _dacl_state_equal(before, replace(before, descriptor_digest="new-layout")),
        )
        for changed in (
            replace(before, acl_bytes=b"changed-acl"),
            replace(before, control=0x8004),
            replace(before, file_identity=(1, 3)),
            replace(before, present=False),
        ):
            with self.subTest(changed=changed):
                self.assertFalse(_dacl_state_equal(before, changed))

    def test_baseline_normalization_rejects_reparse_disposable_root(self) -> None:
        snapshot = _DaclSnapshot(
            descriptor_digest="baseline",
            acl_digest="acl",
            acl_bytes=b"acl",
            acl_capacity_bytes=b"capacity",
            normalized_acl_digest="normalized",
            control=0x8404,
            revision=1,
            present=True,
            defaulted=False,
            file_identity=(1, 2),
            ace_count=3,
            inherited_ace_count=3,
            acl_bytes_in_use=88,
        )
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            actual_root = parent / "icode-appcontainer-read-handle-actual"
            actual_root.mkdir()
            (actual_root / "execution").mkdir()
            linked_root = parent / "icode-appcontainer-read-handle-linked"
            try:
                linked_root.symlink_to(actual_root, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"directory symlink is unavailable: {type(exc).__name__}")

            with patch(
                "scripts.run_windows_appcontainer_read_probe._dacl_snapshot",
                return_value=snapshot,
            ):
                with self.assertRaises(OSError):
                    _normalize_disposable_workspace_dacl_baseline(
                        linked_root / "execution",
                    )

    def test_baseline_normalization_reports_path_free_snapshot_failure_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "icode-appcontainer-read-handle-diagnostic"
            root.mkdir()
            workspace = root / "execution"
            workspace.mkdir()
            with patch(
                "scripts.run_windows_appcontainer_read_probe._dacl_snapshot",
                side_effect=OSError(5, "access denied", "sensitive-path"),
            ):
                with self.assertRaises(OSError) as raised:
                    _normalize_disposable_workspace_dacl_baseline(workspace)

        self.assertEqual(raised.exception.args, ("dacl_baseline_before_snapshot_errno_5",))

    def test_stat_reparse_detection_includes_windows_junction_attribute(self) -> None:
        regular_directory = SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o755,
            st_file_attributes=0,
        )
        junction = SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o755,
            st_file_attributes=0x0400,
        )
        symbolic_link = SimpleNamespace(
            st_mode=stat.S_IFLNK | 0o777,
            st_file_attributes=0,
        )

        self.assertFalse(_stat_is_reparse_point(regular_directory))
        self.assertTrue(_stat_is_reparse_point(junction))
        self.assertTrue(_stat_is_reparse_point(symbolic_link))


if __name__ == "__main__":
    unittest.main()
