"""CAB category observations exercise the real callback and JSON serializer only."""
from __future__ import annotations

import contextlib
import ctypes
import inspect
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import inspect_windows_cabinet_members as probe

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("target", "state", "etl", "other", "unknown")


class TestWfpCabObservation(unittest.TestCase):
    def receipt(self, names=(), *, error=None, default=False, member_error=0):
        class NativeFunction:
            def __call__(self, _path, _reserved, callback, context):
                if callback(context, 0x10, 0, 0) != 0:
                    raise AssertionError("CAB metadata must not extract")
                for name in names:
                    info = probe._FileInCabinetInfoW()
                    info.NameInCabinet = name
                    info.Win32Error = member_error
                    if callback(context, 0x11, ctypes.addressof(info), 0) != 2:
                        return False
                return True
        api = SimpleNamespace(SetupIterateCabinetW=NativeFunction())
        supports = "observe_categories" in inspect.signature(probe.inspect_cabinet_members).parameters
        arguments = []
        with tempfile.TemporaryDirectory(prefix="cab-observation-software-") as tmp:
            archive = Path(tmp) / "private-source-identity.cab"
            archive.write_bytes(b"MSCF synthetic API-boundary fixture")
            arguments = ["--archive", str(archive)]
            if not default and supports:
                arguments.append("--observe-categories")
            output = io.StringIO()
            with mock.patch.object(probe, "os", SimpleNamespace(name="nt")), \
                 mock.patch.object(probe.ctypes, "WinDLL", create=True,
                                   side_effect=error, return_value=api), \
                 mock.patch.object(probe.ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, create=True), \
                 contextlib.redirect_stdout(output):
                code = probe.main(arguments)
            wire = output.getvalue()
        self.assertLessEqual(len(wire.encode("utf-8")), 500)
        self.assertEqual(wire.count("\n"), 1)
        self.assertNotIn("private-source-identity", wire)
        return code, json.loads(wire), wire

    def categories(self, result):
        self.assertEqual(result.get("schema_version"), 4, "CAB_CATEGORY_SCHEMA_REQUIRED")
        value = result.get("member_categories")
        self.assertIsInstance(value, dict, "CAB_CATEGORY_OBSERVATION_REQUIRED")
        self.assertEqual(set(value), set(KEYS))
        return value

    def test_real_callback_and_cli_classify_fixed_members(self):
        code, result, wire = self.receipt(
            ("nested/WFPDIAG.XML", "wfpstate.xml", "nested/trace.etl", "notes.txt"))
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "listed")
        self.assertEqual(self.categories(result),
                         dict(target=1, state=1, etl=1, other=1, unknown=0))
        self.assertEqual(result["target_match_count"], 1)
        self.assertEqual(result["xml_member_count"], 2)
        for private in ("nested", "notes.txt", "trace.etl"):
            self.assertNotIn(private, wire)

    def test_unknown_and_noncanonical_names_are_counted_not_extracted(self):
        code, result, wire = self.receipt(
            ("secret/user.xml", "trace.\u03bc.xml", "bad\nname.etl", "", None))
        self.assertEqual(code, 0)
        self.assertEqual(result["target_match_count"], 0)
        self.assertEqual(self.categories(result),
                         dict(target=0, state=0, etl=0, other=1, unknown=4))
        self.assertEqual(sum(self.categories(result).values()), 5)
        self.assertNotIn("secret", wire)
        self.assertNotIn("user.xml", wire)

    def test_multiple_exact_targets_keep_original_ambiguity(self):
        _, result, _ = self.receipt(("wfpdiag.xml", "nested/wfpdiag.xml"))
        self.assertEqual(result["target_match_count"], 2)
        self.assertEqual(self.categories(result)["target"], 2)
        self.assertEqual(result["member_count"], 2)

    def test_api_permission_failure_is_unavailable_not_zero_categories(self):
        code, result, wire = self.receipt(error=PermissionError("private path token"))
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "api_unavailable")
        self.assertEqual(self.categories(result), dict.fromkeys(KEYS))
        self.assertNotIn("private path token", wire)

    def test_member_permission_error_never_becomes_a_complete_observation(self):
        code, result, wire = self.receipt(("wfpdiag.xml",), member_error=5)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "member_error")
        self.assertEqual(self.categories(result), dict.fromkeys(KEYS))
        self.assertIsNone(result["target_match_count"])
        self.assertNotIn("wfpdiag.xml", wire)

    def test_member_limit_failure_does_not_publish_partial_zero_counts(self):
        code, result, _ = self.receipt(("wfpstate.xml",) * 4097)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "member_limit_exceeded")
        self.assertEqual(result["member_count"], 4097)
        self.assertEqual(self.categories(result), dict.fromkeys(KEYS))

    def test_largest_success_counts_serialize_under_budget(self):
        code, result, _ = self.receipt(("capture.etl",) * 4096)
        self.assertEqual(code, 0)
        counts = self.categories(result)
        self.assertEqual(counts["etl"], 4096)
        self.assertEqual(sum(counts.values()), result["member_count"])

    def test_default_v3_receipt_and_exact_matcher_are_unchanged(self):
        code, result, _ = self.receipt(("wfpdiag_extra.xml",), default=True)
        self.assertEqual(code, 0)
        self.assertEqual(result["schema_version"], 3)
        self.assertNotIn("member_categories", result)
        self.assertEqual(result["target_match_count"], 0)
        self.assertTrue(probe.is_target_cabinet_member("nested/WFPDIAG.XML"))
        self.assertFalse(probe.is_target_cabinet_member("wfpdiag_extra.xml"))

    def test_workflow_observation_is_after_validation_and_does_not_expand_admission(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        start = workflow.index("  windows-reviewer-snapshot-probe:")
        end = workflow.index("  windows-appcontainer-read-handle-probe:", start)
        job = workflow[start:end]
        self.assertTrue("'--archive', $wfpCaptureArchive, '--observe-categories'" in job, "fixed workflow contract missing")
        self.assertTrue("$cabinetMemberSummary.schema_version -eq 4" in job, "fixed workflow contract missing")
        self.assertTrue("$categoryTotal -eq $cabinetMemberSummary.member_count" in job, "fixed workflow contract missing")
        self.assertTrue("$categoryNames -cnotcontains $key" in job, "nested category keys must be case-sensitive")
        self.assertTrue("$categories.target -eq $cabinetMemberSummary.target_match_count" in job, "fixed workflow contract missing")
        self.assertLess(job.index("$categoryTotal -eq"),
                        job.index("$wfpArchiveCategoryCounts = (\'target:"))
        self.assertTrue(
            "if ($cabinetSummaryValid -and $cabinetMemberSummary.status -ceq 'listed') {\n"
            + " " * 26 + "$wfpArchiveCategoryCounts =" in job,
            "category counts require an adjacent exact listed-status gate")
        self.assertTrue("cab_categories=$wfpArchiveCategoryCounts" in job, "fixed workflow contract missing")
        self.assertTrue("if ($matchDisposition -eq 'missing')" in job, "fixed workflow contract missing")
        self.assertTrue("$wfpCaptureStatus = 'archive_member_missing'" in job, "fixed workflow contract missing")
        self.assertTrue("@($wfpCaptureArchive, '-F:wfpdiag.xml', $wfpExtractExplicitFile)" in job, "fixed workflow contract missing")
        self.assertTrue("$wfpCaptureArchive, '-F:*'" not in job, "fixed workflow contract missing")
        self.assertTrue("Write-Output $memberListResult.Stdout" not in job, "fixed workflow contract missing")
        self.assertTrue("'set', 'options'" not in job, "fixed workflow contract missing")

    def test_strict_count_and_existing_actions_notice_are_preserved(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("pattern='test_windows_wfp_cab_observation.py'"), 2)
        for command in (line for line in workflow.splitlines()
                        if "pattern='test_windows_wfp_cab_observation.py'" in line):
            self.assertTrue("countTestCases()==10" in command, "fixed workflow contract missing")
            self.assertTrue("not r.wasSuccessful() or bool(r.skipped)" in command, "fixed workflow contract missing")
        notice = next(line for line in workflow.splitlines()
                      if '::notice title=Windows WFP capture and runner observer::' in line)
        self.assertTrue("cab_categories" not in notice, "fixed workflow contract missing")
        self.assertTrue("capture=$wfpCaptureStatus" in notice, "fixed workflow contract missing")


if __name__ == "__main__":
    unittest.main()
