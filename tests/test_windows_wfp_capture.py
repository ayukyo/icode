"""Fail-closed parsing tests for the ephemeral Windows WFP capture diagnostic."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.inspect_windows_wfp_capture import (
    _inspect_wfpdiag_bytes,
    inspect_wfp_capture,
)


_PACKAGE_SID = "S-1-15-2-4163697451-3176919390-1155390458"
_CONTEXT = {
    "version": 1,
    "package_sid": _PACKAGE_SID,
    "targets": [
        {"ip_version": "FWP_IP_VERSION_V4", "remote_address": "127.0.0.1", "remote_port": 41001},
        {"ip_version": "FWP_IP_VERSION_V6", "remote_address": "::1", "remote_port": 41002},
    ],
}


def _event(
    *,
    sid: str = _PACKAGE_SID,
    ip_version: str = "FWP_IP_VERSION_V4",
    address: str = "127.0.0.1",
    port: int = 41001,
    protocol: int = 6,
    event_type: str = "FWPM_NET_EVENT_TYPE_CLASSIFY_DROP",
    direction: str = "MS_FWP_DIRECTION_OUT",
    flags: tuple[str, ...] = (
        "FWPM_NET_EVENT_FLAG_IP_VERSION_SET",
        "FWPM_NET_EVENT_FLAG_IP_PROTOCOL_SET",
        "FWPM_NET_EVENT_FLAG_REMOTE_ADDR_SET",
        "FWPM_NET_EVENT_FLAG_REMOTE_PORT_SET",
        "FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET",
    ),
) -> str:
    address_field = (
        "remoteAddrV4" if ip_version == "FWP_IP_VERSION_V4"
        else "remoteAddrV6.byteArray16"
    )
    flags_xml = "".join(f"<item>{flag}</item>" for flag in flags)
    return (
        "<netEvent><header>"
        f"<flags>{flags_xml}</flags><ipVersion>{ip_version}</ipVersion>"
        f"<ipProtocol>{protocol}</ipProtocol><{address_field}>{address}</{address_field}>"
        f"<remotePort>{port}</remotePort><packageSid>{sid}</packageSid>"
        f"</header><type>{event_type}</type>"
        f"<classifyDrop><msFwpDirection>{direction}</msFwpDirection></classifyDrop>"
        "</netEvent>"
    )


class TestWindowsWfpCapture(unittest.TestCase):
    def test_workflow_uses_bounded_setupapi_member_enumeration_before_extract(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("scripts/inspect_windows_cabinet_members.py", job)
        self.assertIn("'--archive', $wfpMemberSelfTestCab", job)
        self.assertIn("'--archive', $wfpCaptureArchive", job)
        self.assertIn("$cabinetMemberSummary = $memberListResult.Stdout | ConvertFrom-Json", job)
        self.assertIn("$wfpArchiveMemberMatchCount", job)
        self.assertNotIn("'-D', $wfpCaptureArchive", job)
        self.assertNotIn("$memberListResult.Stdout -split", job)

    def test_exact_appcontainer_sid_and_loopback_destination_drop_matches_for_both_families(self) -> None:
        document = (
            "<wfpdiag><netEvents><item>"
            + _event()
            + "</item><item>"
            + _event(
                ip_version="FWP_IP_VERSION_V6", address="::1", port=41002,
            )
            + "</item></netEvents></wfpdiag>"
        ).encode("utf-8")

        result = _inspect_wfpdiag_bytes(document, _CONTEXT)

        self.assertEqual(result, {"status": "matched", "exact_classify_drop_count": 2})

    def test_unrelated_or_non_drop_events_do_not_match(self) -> None:
        document = (
            "<wfpdiag><netEvents>"
            + _event(sid="S-1-15-2-999")
            + _event(port=41003)
            + _event(event_type="FWPM_NET_EVENT_TYPE_CLASSIFY_ALLOW")
            + _event(direction="MS_FWP_DIRECTION_IN")
            + _event(protocol=17)
            + "</netEvents></wfpdiag>"
        ).encode("utf-8")

        result = _inspect_wfpdiag_bytes(document, _CONTEXT)

        self.assertEqual(result, {"status": "no_match", "exact_classify_drop_count": 0})

    def test_missing_exact_tuple_fields_or_required_flag_is_inconclusive(self) -> None:
        event = _event(flags=(
            "FWPM_NET_EVENT_FLAG_IP_VERSION_SET",
            "FWPM_NET_EVENT_FLAG_IP_PROTOCOL_SET",
            "FWPM_NET_EVENT_FLAG_REMOTE_ADDR_SET",
            "FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET",
        ))
        document = f"<wfpdiag>{event}</wfpdiag>".encode("utf-8")

        result = _inspect_wfpdiag_bytes(document, _CONTEXT)

        self.assertEqual(result, {"status": "inconclusive", "exact_classify_drop_count": 0})

    def test_invalid_or_unbounded_inputs_fail_closed_without_echoing_private_values(self) -> None:
        invalid_context = {**_CONTEXT, "package_sid": "private-sid-value"}
        for xml_bytes, context in (
            (b"<!DOCTYPE wfpdiag [<!ENTITY x 'expanded'>]><wfpdiag/>", _CONTEXT),
            (b"<wfpdiag>", _CONTEXT),
            (b"x" * (8 * 1024 * 1024 + 1), _CONTEXT),
            (b"<wfpdiag/>", invalid_context),
        ):
            with self.subTest(size=len(xml_bytes)):
                result = _inspect_wfpdiag_bytes(xml_bytes, context)
                self.assertEqual(
                    result,
                    {"status": "inconclusive", "exact_classify_drop_count": 0},
                )
                self.assertNotIn("private-sid-value", json.dumps(result))

    def test_event_count_ceiling_returns_inconclusive_even_with_a_matching_drop(self) -> None:
        document = (
            "<wfpdiag>"
            + "<netEvent/>" * 8192
            + _event()
            + "</wfpdiag>"
        ).encode("utf-8")

        result = _inspect_wfpdiag_bytes(document, _CONTEXT)

        self.assertEqual(result, {"status": "inconclusive", "exact_classify_drop_count": 0})

    def test_file_wrapper_reports_only_fixed_status_and_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml_path = root / "wfpdiag.xml"
            context_path = root / "context.json"
            xml_path.write_text(f"<wfpdiag>{_event()}</wfpdiag>", encoding="utf-8")
            context_path.write_text(json.dumps(_CONTEXT), encoding="utf-8")

            result = inspect_wfp_capture(xml_path, context_path)

        self.assertEqual(result, {"status": "matched", "exact_classify_drop_count": 1})

    def test_workflow_capture_is_ephemeral_scoped_and_never_changes_wfp_policy(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]
        candidate_start = job.index("$process = Start-Process")
        capture_start = job.index("'capture', 'start'")
        candidate_wait = job.index("$process.WaitForExit(65000)")
        capture_stop = job.index("'capture', 'stop'")
        capture_parse = job.index("inspect_windows_wfp_capture.py")
        capture_cleanup = job.index("Remove-Item -LiteralPath $diagnosticPath")
        self.assertLess(capture_start, candidate_start)
        self.assertLess(candidate_start, candidate_wait)
        self.assertLess(candidate_wait, capture_stop)
        self.assertLess(capture_stop, capture_parse)
        self.assertLess(capture_parse, capture_cleanup)
        self.assertIn("'capture', 'status'", job)
        self.assertIn("$process.WaitForExit(65000)", job)
        self.assertNotIn("$process.WaitForExit(45000)", job)
        self.assertIn("$wfpCaptureStarted", job)
        self.assertIn("$wfpCapturePreflight", job)
        self.assertIn("Stop-Process -Id $process.Id -Force", job)
        self.assertIn("65000", job)
        self.assertIn("ICODE_DIAGNOSTIC_WFP_MATCH_FILE", job)
        self.assertNotIn("ICODE_DIAGNOSTIC_WFP_READY_FILE", job)
        self.assertNotIn("ICODE_DIAGNOSTIC_WFP_STARTED_FILE", job)
        self.assertIn("exact_classify_drop_count", job)
        self.assertNotIn("netsh wfp set", job)
        self.assertNotIn("actions/upload-artifact", job)

        appcontainer_test = (
            repository_root / "tests/test_windows_appcontainer.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ConvertSidToStringSidW", appcontainer_test)
        self.assertIn("ICODE_DIAGNOSTIC_WFP_CAPTURE", appcontainer_test)
        self.assertIn("wfp_context_path.parent.resolve() == runner_temp_path", appcontainer_test)
        self.assertIn("'package_sid_value':package_sid_value", appcontainer_test)
        self.assertNotIn('summary["package_sid_value"]', appcontainer_test)

    def test_workflow_only_starts_or_recovers_a_capture_from_bounded_status(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("function Get-WfpCaptureActivity", job)
        self.assertIn("return 'inactive'", job)
        self.assertIn("return 'active'", job)
        self.assertIn("return 'unknown'", job)
        self.assertIn("$wfpCapturePreflight -eq 'inactive'", job)
        self.assertIn("$wfpCaptureStatus = 'existing_session'", job)
        self.assertIn("$wfpCaptureStatus = 'status_unrecognized'", job)
        self.assertIn("$wfpCaptureStartAttempted -and -not $wfpCaptureStarted", job)
        self.assertIn("$wfpCaptureStatus -eq 'start_timeout'", job)
        self.assertIn("$wfpCaptureStatus -eq 'start_failed'", job)
        self.assertIn("$wfpCaptureStatus = 'start_state_unknown'", job)
        self.assertIn("$wfpCaptureStatus = 'start_state_unowned'", job)
        self.assertIn("[regex]::IsMatch(", job)
        self.assertIn("preflight=$wfpCapturePreflight", job)
        self.assertNotIn("$captureStatusResult.Stdout", "\n".join(
            line for line in job.splitlines() if "Write-Output" in line
        ))

    def test_workflow_bounds_each_external_capture_diagnostic_command(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("function Invoke-BoundedDiagnosticCommand", job)
        self.assertIn("$process.WaitForExit($TimeoutMilliseconds)", job)
        self.assertIn("$process.Kill($true)", job)
        self.assertIn("$profileBootstrap.WaitForExit(30000)", job)
        self.assertIn("$profileBootstrap.Kill($true)", job)
        self.assertNotIn("-Wait -PassThru", job)
        self.assertEqual(job.count("-Path $netsh -Arguments"), 4)
        self.assertIn("-Path $expand -Arguments", job)
        self.assertIn("-Path $python -Arguments", job)
        self.assertIn("-TimeoutMilliseconds 5000", job)
        self.assertIn("-TimeoutMilliseconds 10000", job)
        self.assertIn("-TimeoutMilliseconds 15000", job)
        self.assertIn("$stdoutTask.Wait(5000)", job)
        self.assertNotIn("GetAwaiter().GetResult()", job)
        self.assertIn("-CaptureStdout", job)
        self.assertNotIn("& $netsh wfp capture", job)
        self.assertNotIn("& $expand '-F:wfpdiag.xml'", job)

    def test_workflow_reports_bounded_wfp_extract_failure_category(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("$wfpExtractExitCode", job)
        self.assertIn("extract_exit_code=$wfpExtractExitCode", job)
        self.assertIn("extract_command_failed", job)
        self.assertIn("extract_xml_missing", job)
        self.assertIn("extract_xml_too_large", job)

    def test_workflow_uses_expand_cab_file_and_destination_argument_order(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]
        archive_branch = job.index("if (Test-Path -LiteralPath $wfpCaptureArchive -PathType Leaf)")
        member_list_call = job.index("$memberListResult = Invoke-BoundedDiagnosticCommand", archive_branch)
        member_list_result = job.index("'--archive', $wfpCaptureArchive", member_list_call)
        summary_parse = job.index(
            "$cabinetMemberSummary = $memberListResult.Stdout | ConvertFrom-Json",
            member_list_result,
        )
        member_count_zero = job.index("if ($matchCount -eq 0)", summary_parse)
        member_count_multiple = job.index("elseif ($matchCount -gt 1)", member_count_zero)
        extraction_mode = job.index("$expandArguments = if ($wfpMemberSelfTestExtractMode -eq 'file')", member_count_multiple)
        extraction_call = job.index("-Path $expand -Arguments $expandArguments", extraction_mode)
        self.assertLess(member_list_call, member_count_zero)
        self.assertLess(member_count_zero, member_count_multiple)
        self.assertLess(member_count_multiple, extraction_mode)
        self.assertLess(extraction_mode, extraction_call)
        self.assertIn("@($wfpCaptureArchive, '-F:wfpdiag.xml', $wfpExtractExplicitFile)", job)
        self.assertIn("@($wfpCaptureArchive, '-F:wfpdiag.xml', $wfpExtractRoot)", job)
        self.assertNotIn("$wfpCaptureArchive, '-F:*'", job)

    def test_workflow_checks_exact_cab_member_without_logging_archive_listing(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("$wfpArchiveMemberStatus = 'not_checked'", job)
        self.assertIn("scripts/inspect_windows_cabinet_members.py", job)
        self.assertIn("'--archive', $wfpCaptureArchive", job)
        self.assertIn("$cabinetMemberSummary.target_match_count", job)
        self.assertIn("$cabinetMemberSummary.status -cne 'listed'", job)
        self.assertIn("$wfpArchiveMemberStatus = 'multiple'", job)
        self.assertIn("archive_member_status=$wfpArchiveMemberStatus", job)
        self.assertNotIn("'-D', $wfpCaptureArchive", job)
        self.assertNotIn('Write-Output $memberListResult.Stdout', job)
        self.assertIn("archive_member_match_count=$wfpArchiveMemberMatchCount", job)

    def test_workflow_reports_only_the_validated_bounded_cabinet_member_count(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertTrue(
            "$wfpArchiveMemberCount = 'not_checked'" in job,
            "the CAB member count must default to a fixed not_checked category",
        )
        self.assertTrue(
            "$wfpArchiveMemberCount = [string]$cabinetMemberSummary.member_count" in job,
            "the notice may only publish the validated numeric member count",
        )
        self.assertTrue(
            "archive_member_count=$wfpArchiveMemberCount" in job,
            "the bounded count must be present in the fixed notice",
        )
        member_count_bound = job.index("$cabinetMemberSummary.member_count -le 4096")
        member_count_receipt = job.index(
            "$wfpArchiveMemberCount = [string]$cabinetMemberSummary.member_count"
        )
        self.assertLess(member_count_bound, member_count_receipt)
        self.assertLess(
            member_count_receipt,
            job.index("archive_member_count=$wfpArchiveMemberCount"),
        )
        self.assertTrue(
            "$wfpArchiveXmlMemberCount = 'not_checked'" in job,
            "the XML suffix count must default to a fixed not_checked category",
        )
        self.assertTrue(
            "$cabinetMemberSummary.schema_version -ne 2" in job,
            "the synthetic positive control must exercise the v2 receipt schema",
        )
        self.assertTrue(
            "$cabinetMemberSummary.xml_member_count -ne 1" in job,
            "the synthetic CAB must prove its single XML member is counted",
        )
        self.assertTrue(
            "$wfpArchiveXmlMemberCount = [string]$cabinetMemberSummary.xml_member_count" in job,
            "the notice may only publish the validated XML suffix count",
        )
        self.assertTrue(
            "archive_xml_member_count=$wfpArchiveXmlMemberCount" in job,
            "the bounded XML suffix count must be present in the fixed notice",
        )
        xml_count_bound = job.index("$cabinetMemberSummary.xml_member_count -le 4096")
        xml_count_consistency = job.index(
            "$cabinetMemberSummary.xml_member_count -le $cabinetMemberSummary.member_count"
        )
        xml_count_receipt = job.index(
            "$wfpArchiveXmlMemberCount = [string]$cabinetMemberSummary.xml_member_count"
        )
        self.assertLess(xml_count_bound, xml_count_receipt)
        self.assertLess(xml_count_consistency, xml_count_receipt)
        self.assertLess(
            xml_count_receipt,
            job.index("archive_xml_member_count=$wfpArchiveXmlMemberCount"),
        )
        self.assertIn("$cabinetMemberSummary.schema_version -eq 2", job)

    def test_workflow_rejects_malformed_or_unbounded_cabinet_probe_receipts(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("$expectedSummaryPropertyNames = @(", job)
        self.assertIn("$summaryPropertyNames.Count -eq $expectedSummaryPropertyNames.Count", job)
        self.assertIn("$cabinetMemberSummary.member_count -le 4096", job)
        self.assertIn("$cabinetMemberSummary.target_match_count -le $cabinetMemberSummary.member_count", job)
        self.assertIn("$cabinetMemberSummary.xml_member_count -le 4096", job)
        self.assertIn("$cabinetMemberSummary.xml_member_count -le $cabinetMemberSummary.member_count", job)
        self.assertIn("$cabinetMemberSummary.target_match_count -le $cabinetMemberSummary.xml_member_count", job)
        self.assertIn("'xml_member_count'", job)
        self.assertIn("$wfpArchiveMemberStatus = 'summary_invalid'", job)
        self.assertIn("$wfpArchiveMemberStatus = 'list_timeout'", job)
        logged_lines = [line for line in job.splitlines() if "Write-Output" in line]
        self.assertFalse(any("$memberListResult.Stdout" in line for line in logged_lines))

    def test_workflow_only_extracts_after_unique_native_member_match(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        member_probe = job.index("$cabinetMemberProbe, '--archive', $wfpCaptureArchive")
        summary_parse = job.index(
            "$cabinetMemberSummary = $memberListResult.Stdout | ConvertFrom-Json",
            member_probe,
        )
        unique_gate = job.index("if ($matchCount -eq 0)", summary_parse)
        extract_call = job.index("-Path $expand -Arguments $expandArguments", unique_gate)
        self.assertLess(member_probe, summary_parse)
        self.assertLess(summary_parse, unique_gate)
        self.assertLess(unique_gate, extract_call)
        self.assertIn("$wfpArchiveMemberMatchCount = if ($matchCount -eq 0)", job)
        self.assertIn("$matchCount -gt 1", job)
        self.assertNotIn("'-D', $wfpCaptureArchive", job)
        self.assertNotIn("$wfpCaptureArchive, '-F:*'", job)

    def test_workflow_verifies_cab_member_listing_with_a_synthetic_positive_control(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("System32/makecab.exe", job)
        self.assertIn("$wfpMemberSelfTestSource, $wfpMemberSelfTestCab", job)
        self.assertIn("$makecabResult.ExitCode -ne 0", job)
        self.assertIn("'--archive', $wfpMemberSelfTestCab", job)
        self.assertIn("$cabinetMemberSummary.status -ne 'listed'", job)
        self.assertIn("$cabinetMemberSummary.target_match_count -ne 1", job)
        self.assertNotIn("'-D', $wfpMemberSelfTestCab", job)
        self.assertIn("wfp_cab_member_parser_self_test_failed", job)
        self.assertIn("$wfpSyntheticExtract.ExitCode -ne 0", job)
        self.assertIn("Get-ChildItem -LiteralPath $wfpMemberSelfTestExtractRoot", job)
        self.assertIn("-Filter 'wfpdiag.xml' -File -Recurse -Force", job)
        self.assertIn("$syntheticXmlCandidates.Count -ne 1", job)
        self.assertIn("$extractTimedOut = if ($wfpSyntheticExtract.TimedOut)", job)
        self.assertIn("$extractExitCode = if ($null -eq $wfpSyntheticExtract.ExitCode)", job)
        self.assertIn("$syntheticXmlCandidateCount = if ($syntheticXmlCandidates.Count -eq 0)", job)
        self.assertIn(
            "wfp_cab_member_parser_self_test_extract=failed "
            "timed_out=$extractTimedOut exit_code=$extractExitCode "
            "xml_candidates=$syntheticXmlCandidateCount",
            job,
        )
        self.assertIn("$syntheticContentMatches", job)
        self.assertIn("wfp_cab_member_parser_self_test=passed", job)
        self.assertIn("$wfpMemberSelfTestStage = 'prepare'", job)
        self.assertIn("$wfpMemberSelfTestStage = 'makecab'", job)
        self.assertIn("$wfpMemberSelfTestStage = 'member_enumeration'", job)
        self.assertIn("$wfpMemberSelfTestStage = 'member_match'", job)
        self.assertIn("$wfpMemberSelfTestStage = 'extract'", job)
        self.assertIn("$wfpMemberSelfTestStage = 'content_check'", job)
        self.assertIn(
            'Write-Output "wfp_cab_member_parser_self_test=failed stage=$wfpMemberSelfTestStage"',
            job,
        )
        self.assertNotIn("Write-Output $memberListResult.Stdout", job)
        self.assertIn("throw 'wfp_cab_member_parser_self_test_cleanup_failed'", job)
        self.assertIn("Remove-Item -LiteralPath $wfpMemberSelfTestRoot -Recurse -Force", job)

    def test_workflow_diagnoses_synthetic_cab_extract_destination_and_filter_variants(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("$syntheticExactDirectoryResult = Invoke-BoundedDiagnosticCommand", job)
        self.assertIn("$syntheticExactFileResult = Invoke-BoundedDiagnosticCommand", job)
        self.assertIn("$syntheticWildcardDirectoryResult = Invoke-BoundedDiagnosticCommand", job)
        self.assertIn("-CaptureStdout -CaptureStderr", job)
        self.assertIn("synthetic_exact_directory_file=$syntheticExactDirectoryStatus", job)
        self.assertIn("synthetic_exact_file_file=$syntheticExactFileStatus", job)
        self.assertIn("synthetic_wildcard_directory_file=$syntheticWildcardDirectoryStatus", job)
        self.assertIn("synthetic_exact_stdout_member=$syntheticExactStdoutMember", job)
        self.assertIn("synthetic_exact_stderr_member=$syntheticExactStderrMember", job)
        logged_lines = [line for line in job.splitlines() if "Write-Output" in line]
        self.assertFalse(any("$syntheticExactDirectoryResult.Stdout" in line for line in logged_lines))
        self.assertFalse(any("$syntheticExactDirectoryResult.Stderr" in line for line in logged_lines))
        self.assertNotIn("$wfpCaptureArchive, '-F:*'", job)

    def test_workflow_accepts_one_nested_cab_xml_and_rejects_ambiguous_matches(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job_start = workflow.index("  windows-reviewer-snapshot-probe:")
        job_end = workflow.index("  windows-appcontainer-read-handle-probe:", job_start)
        job = workflow[job_start:job_end]

        self.assertIn("$wfpXmlCandidates = @(", job)
        self.assertIn("Get-ChildItem -LiteralPath $wfpExtractRoot", job)
        self.assertIn("-Filter 'wfpdiag.xml' -File -Recurse -Force -ErrorAction Stop", job)
        self.assertIn("$wfpXmlCandidates.Count -gt 1", job)
        self.assertIn("extract_xml_ambiguous", job)


if __name__ == "__main__":
    unittest.main()
