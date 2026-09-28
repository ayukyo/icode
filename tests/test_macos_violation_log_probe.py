"""Unit and native diagnostics for macOS Seatbelt violation logging."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import macos_violation_log_probe as probe
from icode.isolation import MacSeatbeltSandbox
from icode.sandbox_policy import NetworkMode, SandboxPolicy


class TestViolationEventParser(unittest.TestCase):
    def test_parser_accepts_kernel_sandbox_sender_with_matching_denial(self) -> None:
        record = {
            "processID": 0,
            "senderImagePath": "/System/Library/Sandbox",
            "eventMessage": "Sandbox: Python(4321) deny(1) file-read-data /private/tmp/secret.txt",
        }
        self.assertEqual(
            probe.parse_violation_record(json.dumps(record).encode("utf-8")),
            (4321, "file-read-data"),
        )

    def test_parser_rejects_untrusted_kernel_sender_even_with_denial_text(self) -> None:
        record = {
            "processID": 4321,
            "senderImagePath": "/System/Library/Other.framework",
            "eventMessage": "Sandbox: Python(4321) deny(1) file-read-data /private/tmp/secret.txt",
        }
        self.assertIsNone(
            probe.parse_violation_record(json.dumps(record).encode("utf-8")),
        )

    def test_log_stream_requests_debug_level_and_both_known_sources(self) -> None:
        builder = getattr(probe, "build_log_stream_command", None)
        self.assertTrue(callable(builder), "test-only log command builder is missing")

        command = builder(Path("/usr/bin/log"))
        self.assertEqual(command[:3], ["/usr/bin/log", "stream", "--style"])
        self.assertIn("--level", command)
        level_index = command.index("--level")
        self.assertEqual(command[level_index + 1], "debug")
        predicate_index = command.index("--predicate")
        predicate = command[predicate_index + 1]
        self.assertIn('subsystem == "com.apple.sandbox.reporting"', predicate)
        self.assertIn('senderImagePath CONTAINS "/Sandbox"', predicate)
        self.assertIn('eventMessage CONTAINS[c] "Sandbox"', predicate)

    def test_diagnostics_expose_only_fixed_record_categories(self) -> None:
        record = {
            "processID": 0,
            "senderImagePath": "/System/Library/Sandbox",
            "messageType": "error",
            "eventMessage": (
                "Sandbox: Python(4321) deny(1) file-read-data "
                "/private/tmp/secret-path"
            ),
        }
        classifier = getattr(probe, "diagnostic_record_categories", None)
        self.assertTrue(callable(classifier), "diagnostic record classifier is missing")
        categories = classifier(
            json.dumps(record).encode("utf-8"),
        )

        self.assertIn("json_object", categories)
        self.assertIn("source_kernel", categories)
        self.assertIn("message_type_error", categories)
        self.assertIn("deny_message", categories)
        self.assertIn("capability_file_read_data", categories)
        rendered = " ".join(categories)
        self.assertNotIn("4321", rendered)
        self.assertNotIn("secret-path", rendered)

    def test_summary_reports_counts_without_pid_or_path_values(self) -> None:
        formatter = getattr(probe, "format_sanitized_diagnostics", None)
        self.assertTrue(callable(formatter), "sanitized diagnostics formatter is missing")
        summary = formatter(
            {"stdout_lines": 2, "stderr_lines": 0, "json_object": 1},
            events={(4321, "file-read-data")},
            target_pid=4321,
            capability="file-read-data",
            logger_returncode=None,
        )

        self.assertIn("lines=out:2", summary)
        self.assertIn("target_match=yes", summary)
        self.assertIn("log_process=running", summary)
        self.assertNotIn("4321", summary)
        self.assertNotIn("/private", summary)

    def test_first_fixed_log_filter_banner_is_ignored_without_returning_contents(self) -> None:
        parser = getattr(probe, "parse_violation_stream_line", None)
        self.assertTrue(callable(parser), "test-only stream line parser is missing")

        line = b'Filtering the log data using "predicate /private/sensitive-path"\n'
        self.assertIsNone(parser(line, first_line=True))

    def test_unknown_non_json_stream_preamble_remains_inconclusive(self) -> None:
        parser = getattr(probe, "parse_violation_stream_line", None)
        self.assertTrue(callable(parser), "test-only stream line parser is missing")

        with self.assertRaises(probe.ViolationRecordError) as caught:
            parser(b"Unrecognized logger startup text\n", first_line=True)
        self.assertEqual(caught.exception.reason, "invalid_json")

    def test_known_filter_banner_after_first_line_remains_inconclusive(self) -> None:
        parser = getattr(probe, "parse_violation_stream_line", None)
        self.assertTrue(callable(parser), "test-only stream line parser is missing")

        with self.assertRaises(probe.ViolationRecordError) as caught:
            parser(b'Filtering the log data using "predicate"\n', first_line=False)
        self.assertEqual(caught.exception.reason, "invalid_json")

    def test_malformed_json_first_line_is_not_mistaken_for_a_banner(self) -> None:
        parser = getattr(probe, "parse_violation_stream_line", None)
        self.assertTrue(callable(parser), "test-only stream line parser is missing")

        with self.assertRaises(probe.ViolationRecordError) as caught:
            parser(b'{"subsystem":\n', first_line=True)
        self.assertEqual(caught.exception.reason, "invalid_json")

    def test_parser_returns_only_pid_and_capability_for_a_matching_event(self) -> None:
        parser = getattr(probe, "parse_violation_record", None)
        self.assertTrue(callable(parser), "test-only violation event parser is missing")

        record = {
            "subsystem": "com.apple.sandbox.reporting",
            "category": "violation",
            "eventMessage": "Sandbox: Python(4321) deny(1) file-read-data /private/tmp/secret.txt",
        }
        self.assertEqual(
            parser(json.dumps(record).encode("utf-8")),
            (4321, "file-read-data"),
        )

    def test_parser_ignores_records_outside_the_requested_source(self) -> None:
        record = {
            "subsystem": "com.example.other",
            "category": "violation",
            "eventMessage": "Sandbox: Python(4321) deny(1) file-read-data /private/secret",
        }
        self.assertIsNone(probe.parse_violation_record(json.dumps(record).encode("utf-8")))

    def test_parser_marks_matching_but_unparseable_records_inconclusive(self) -> None:
        with self.assertRaises(probe.ViolationRecordError) as caught:
            probe.parse_violation_record(b"not-json")
        self.assertEqual(caught.exception.reason, "invalid_json")

        record = {
            "subsystem": probe.SUBSYSTEM,
            "category": probe.CATEGORY,
            "eventMessage": "Sandbox denial message with changed format",
        }
        with self.assertRaises(probe.ViolationRecordError) as caught:
            probe.parse_violation_record(json.dumps(record).encode("utf-8"))
        self.assertEqual(caught.exception.reason, "unparsed_event_message")

    def test_parser_rejects_oversized_records_without_retaining_contents(self) -> None:
        with self.assertRaises(probe.ViolationRecordError) as caught:
            probe.parse_violation_record(b"x" * (probe.MAX_RECORD_BYTES + 1))
        self.assertEqual(caught.exception.reason, "record_too_large")


class TestObservationClassification(unittest.TestCase):
    def test_empty_or_unrelated_stream_is_never_reported_as_no_violation(self) -> None:
        empty = probe.classify_observation(
            (), target_pid=4321, capability="file-read-data",
        )
        unrelated = probe.classify_observation(
            ((4322, "file-read-data"),),
            target_pid=4321,
            capability="file-read-data",
        )
        self.assertEqual(empty.status, "inconclusive")
        self.assertEqual(empty.reason, "target_event_not_observed")
        self.assertEqual(unrelated.status, "inconclusive")

    def test_only_exact_target_pid_and_capability_is_positive_evidence(self) -> None:
        result = probe.classify_observation(
            ((4322, "file-read-data"), (4321, "file-read-data")),
            target_pid=4321,
            capability="file-read-data",
            incomplete_reason="stream_byte_limit",
        )
        self.assertEqual(result.status, "observed")
        self.assertEqual(result.reason, "matching_event")

    def test_observer_errors_remain_inconclusive(self) -> None:
        result = probe.classify_observation(
            (),
            target_pid=4321,
            capability="file-read-data",
            incomplete_reason="invalid_json",
        )
        self.assertEqual(result.status, "inconclusive")
        self.assertEqual(result.reason, "invalid_json")


@unittest.skipUnless(
    sys.platform == "darwin",
    "requires native macOS Unified Logging and Seatbelt",
)
class TestNativeViolationLogProbe(unittest.TestCase):
    def test_observes_one_controlled_seatbelt_file_read_denial(self) -> None:
        try:
            observer = probe.BoundedViolationLogObserver.start()
        except probe.ViolationObserverUnavailable as error:
            print(
                "::warning::macos-sandbox-violation-probe "
                f"status=inconclusive reason={error.reason} conformance_credit=none"
            )
            self.skipTest("native Unified Logging observer unavailable")

        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        child_stderr_nonempty = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="icode-seatbelt-log-probe-", dir="/private/tmp",
            ) as raw_root:
                root = Path(raw_root)
                workspace = (root / "workspace").resolve()
                workspace.mkdir()
                allowed_file = workspace / "allowed.txt"
                allowed_file.write_text("allowed", encoding="utf-8")
                secret_file = workspace / "secret.txt"
                secret_file.write_text("private", encoding="utf-8")
                policy = SandboxPolicy(
                    schema_version=1,
                    run_id="macos-violation-log-probe",
                    ticket_id="macos-violation-log-probe",
                    step="code",
                    workspace_root=workspace,
                    read_roots=(workspace,),
                    write_roots=(workspace,),
                    deny_read_roots=(secret_file,),
                    deny_write_roots=(),
                    network_mode=NetworkMode.DENY,
                    allowed_domains=(),
                    process_limit=8,
                    wall_timeout_seconds=10,
                    output_limit_bytes=1024,
                    protected_paths=(),
                )
                sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)
                profile = sandbox._policy_profile(policy)
                child_source = (
                    "import os, pathlib, sys\n"
                    "control = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')\n"
                    "if control != 'allowed': raise SystemExit(12)\n"
                    "print('TARGET_PID=' + str(os.getpid()), flush=True)\n"
                    "try:\n"
                    "    pathlib.Path(sys.argv[2]).read_bytes()\n"
                    "except PermissionError:\n"
                    "    print('READ_DENIED', flush=True)\n"
                    "else:\n"
                    "    print('READ_ALLOWED', flush=True)\n"
                )
                try:
                    child = subprocess.Popen(
                        [
                            sandbox_exec, "-p", profile, sys.executable, "-c",
                            child_source, str(allowed_file), str(secret_file),
                        ],
                        cwd=workspace,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                except OSError:
                    self.fail("controlled Seatbelt child could not start")

                try:
                    stdout, child_stderr = child.communicate(timeout=8)
                    child_stderr_nonempty = bool(child_stderr)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=2)
                    self.fail("controlled Seatbelt child exceeded its bounded timeout")

                self.assertEqual(child.returncode, 0, "controlled Seatbelt child failed")
                self.assertIn("READ_DENIED", stdout.splitlines())
                self.assertNotIn("READ_ALLOWED", stdout.splitlines())
                pid_line = next(
                    (line for line in stdout.splitlines() if line.startswith("TARGET_PID=")),
                    "",
                )
                match = re.fullmatch(r"TARGET_PID=([1-9][0-9]{0,9})", pid_line)
                self.assertIsNotNone(match, "controlled child did not report its PID marker")
                target_pid = int(match.group(1))
                observation = observer.observe(
                    target_pid=target_pid,
                    capability="file-read-data",
                )
        finally:
            observer.close()

        if observation.status != "observed":
            print(
                "::warning::macos-sandbox-violation-probe "
                f"status=inconclusive reason={observation.reason} "
                f"{observation.diagnostics} "
                f"child_stderr={'nonempty' if child_stderr_nonempty else 'empty'} "
                "conformance_credit=none"
            )
            self.skipTest("no exact native violation record was observed")

        print(
            "::notice::macos-sandbox-violation-probe "
            "status=observed capability=file-read-data conformance_credit=none"
        )


if __name__ == "__main__":
    unittest.main()
