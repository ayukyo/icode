"""Portable tests for the Windows-only CAB member probe's name contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from scripts import inspect_windows_cabinet_members as cabinet_probe
    from scripts.inspect_windows_cabinet_members import (
        inspect_cabinet_members,
        is_target_cabinet_member,
    )
except ModuleNotFoundError as error:
    if error.name != "scripts.inspect_windows_cabinet_members":
        raise
    inspect_cabinet_members = None
    is_target_cabinet_member = None
    cabinet_probe = None


class TestWindowsCabinetMemberName(unittest.TestCase):
    def _require_classifier(self):
        if is_target_cabinet_member is None:
            self.fail("the bounded Windows CAB member classifier is not implemented")
        return is_target_cabinet_member

    def test_cabinet_info_notification_is_accepted_without_extracting_members(self) -> None:
        if cabinet_probe is None:
            self.fail("the bounded Windows CAB inspector is not implemented")
        handle_notification = getattr(cabinet_probe, "_handle_setupapi_notification", None)
        self.assertIsNotNone(
            handle_notification,
            "SetupAPI cabinet metadata notifications must be handled explicitly",
        )

        state = {"member_count": 0, "target_match_count": 0}
        callback_result = handle_notification(0x10, 0, state)

        self.assertEqual(callback_result, 0)
        self.assertEqual(state, {"member_count": 0, "target_match_count": 0})

    def test_exact_basename_matches_at_root_or_under_a_cabinet_directory(self) -> None:
        is_member = self._require_classifier()

        for name in (
            "wfpdiag.xml",
            "WFPDIAG.XML",
            "diagnostics/wfpdiag.xml",
            r"diagnostics\WFPDIAG.XML",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_member(name))

    def test_substrings_suffixes_and_empty_names_do_not_match(self) -> None:
        is_member = self._require_classifier()

        for name in (
            "prefix-wfpdiag.xml",
            "wfpdiag.xml.backup",
            "diagnostics/other.xml",
            "diagnostics/",
            "",
            None,
            "diagnostics/wfpdİag.xml",
        ):
            with self.subTest(name=name):
                self.assertFalse(is_member(name))

    def test_missing_archive_returns_a_fixed_receipt_without_echoing_path(self) -> None:
        if inspect_cabinet_members is None:
            self.fail("the bounded Windows CAB inspector is not implemented")

        with tempfile.TemporaryDirectory() as directory:
            private_path = Path(directory) / "private-cabinet-name.cab"
            receipt = inspect_cabinet_members(private_path)

        self.assertEqual(
            receipt,
            {
                "schema_version": 1,
                "status": "invalid_archive",
                "member_count": 0,
                "target_match_count": None,
            },
        )
        self.assertNotIn(str(private_path), json.dumps(receipt))


if __name__ == "__main__":
    unittest.main()
