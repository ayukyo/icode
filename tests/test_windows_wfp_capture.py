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
        candidate_wait = job.index("$process.WaitForExit(45000)")
        capture_stop = job.index("'capture', 'stop'")
        capture_parse = job.index("inspect_windows_wfp_capture.py")
        capture_cleanup = job.index("Remove-Item -LiteralPath $diagnosticPath")
        self.assertLess(candidate_start, capture_start)
        self.assertLess(capture_start, candidate_wait)
        self.assertLess(candidate_wait, capture_stop)
        self.assertLess(capture_stop, capture_parse)
        self.assertLess(capture_parse, capture_cleanup)
        self.assertIn("'capture', 'status'", job)
        self.assertIn("$wfpCaptureStarted", job)
        self.assertIn("Stop-Process -Id $process.Id -Force", job)
        self.assertIn("45000", job)
        self.assertIn("ICODE_DIAGNOSTIC_WFP_MATCH_FILE", job)
        self.assertIn("ICODE_DIAGNOSTIC_WFP_READY_FILE", job)
        self.assertIn("ICODE_DIAGNOSTIC_WFP_STARTED_FILE", job)
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
        self.assertEqual(job.count("-Path $netsh -Arguments"), 3)
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


if __name__ == "__main__":
    unittest.main()
