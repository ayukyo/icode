from __future__ import annotations

import ctypes
import unittest
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

from scripts import windows_standard_user_token_probe as token_probe
from scripts.windows_standard_user_token_probe import (
    _run_child_mode,
    _make_environment_buffer,
    logon_rejection_succeeded,
    restricted_child_failure_detail,
    runner_probe_succeeded,
    stage_runner_script,
    build_system_tool_environment,
    build_runner_command_line,
    build_runner_pipe_command_line,
    build_runner_environment_block,
    runner_pipe_wrong_server_pid_probe,
)


class TestWindowsStandardUserTokenProbe(unittest.TestCase):
    def test_pipe_access_diagnostic_summary_is_redacted_and_bounded(self) -> None:
        summary = token_probe._format_runner_pipe_access_diagnostic(
            dacl="present",
            ace="match",
            token="thread",
            logon_sid="enabled",
            restricted="no",
            access="deny",
        )

        self.assertEqual(
            summary,
            "dacl_present+ace_match+token_thread+logon_enabled+restricted_no+access_deny",
        )
        self.assertLessEqual(len(summary), 120)
        self.assertNotIn("S-1-5-", summary)
        with self.assertRaises(ValueError):
            token_probe._format_runner_pipe_access_diagnostic(
                dacl="S-1-5-21-secret",
                ace="match",
                token="thread",
                logon_sid="enabled",
                restricted="no",
                access="deny",
            )

    def test_pipe_access_diagnostic_is_unavailable_off_windows(self) -> None:
        with mock.patch.object(
            token_probe._runner_pipe, "_load_win32_api",
            side_effect=AssertionError("native API must not load"),
        ):
            summary = token_probe._diagnose_runner_pipe_access(123, "not-logged")

        self.assertEqual(
            summary,
            "dacl_unavailable+ace_unavailable+token_unavailable+"
            "logon_unavailable+restricted_unavailable+access_unavailable",
        )
        self.assertNotIn("not-logged", summary)

    def test_pipe_access_diagnostic_structures_match_windows_layout(self) -> None:
        self.assertEqual(token_probe._ACL_HEADER.AceCount.offset, 4)
        self.assertEqual(token_probe._ACCESS_ALLOWED_ACE.SidStart.offset, 8)
        self.assertEqual(ctypes.sizeof(token_probe._ACCESS_ALLOWED_ACE), 12)

    def test_wrong_server_pid_probe_builds_acl_for_runner_logon_sid(self) -> None:
        class FakePipe:
            name = r"\\.\pipe\icode-runner-" + "d" * 32
            _connected = True

            def _connect(self, timeout_ms: int) -> None:
                self._connected = True

            def __enter__(self) -> "FakePipe":
                return self

            def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
                return None

            def close(self) -> None:
                return None

        kernel = mock.Mock()
        kernel.GetCurrentProcess.return_value = 123
        kernel.GetCurrentProcessId.return_value = 100
        pipe = FakePipe()
        with (
            mock.patch("scripts.windows_standard_user_token_probe.sys.platform", "win32"),
            mock.patch(
                "scripts.windows_standard_user_token_probe.ctypes.WinDLL",
                return_value=kernel,
                create=True,
            ),
            mock.patch(
                "scripts.windows_standard_user_token_probe.runner_process_logon_sid",
                return_value="S-1-5-5-123-456",
            ),
            mock.patch(
                "scripts.windows_standard_user_token_probe.create_runner_pipe_server",
                return_value=pipe,
            ) as create_server,
            mock.patch(
                "scripts.windows_standard_user_token_probe.open_runner_pipe_client",
                side_effect=PermissionError("runner_pipe_server_pid_mismatch"),
            ),
        ):
            result = runner_pipe_wrong_server_pid_probe()

        self.assertEqual(result, (True, "server_pid_mismatch_rejected"))
        create_server.assert_called_once_with("S-1-5-5-123-456")

    def test_wrong_server_pid_probe_confirms_only_the_expected_pid_mismatch(self) -> None:
        class FakePipe:
            name = r"\\.\pipe\icode-runner-" + "b" * 32

            def __init__(self) -> None:
                self._connected = False

            def _connect(self, timeout_ms: int) -> None:
                self._connected = True

            def __enter__(self) -> "FakePipe":
                return self

            def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
                return None

            def close(self) -> None:
                return None

        kernel = mock.Mock()
        kernel.GetCurrentProcess.return_value = 123
        kernel.GetCurrentProcessId.return_value = 100
        pipe = FakePipe()
        with (
            mock.patch("scripts.windows_standard_user_token_probe.sys.platform", "win32"),
            mock.patch(
                "scripts.windows_standard_user_token_probe.ctypes.WinDLL",
                return_value=kernel,
                create=True,
            ),
            mock.patch(
                "scripts.windows_standard_user_token_probe.runner_process_logon_sid",
                return_value="S-1-5-5-123-456",
            ),
            mock.patch(
                "scripts.windows_standard_user_token_probe.create_runner_pipe_server",
                return_value=pipe,
            ),
            mock.patch(
                "scripts.windows_standard_user_token_probe.open_runner_pipe_client",
                side_effect=PermissionError("runner_pipe_server_pid_mismatch"),
            ),
        ):
            result = runner_pipe_wrong_server_pid_probe()

        self.assertEqual(result, (True, "server_pid_mismatch_rejected"))

    def test_wrong_server_pid_probe_reports_only_sanitized_client_timeout(self) -> None:
        class FakePipe:
            name = r"\\.\pipe\icode-runner-" + "a" * 32

            def __init__(self) -> None:
                self._connected = False

            def _connect(self, timeout_ms: int) -> None:
                self._connected = True

            def __enter__(self) -> "FakePipe":
                return self

            def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
                return None

            def close(self) -> None:
                return None

        kernel = mock.Mock()
        kernel.GetCurrentProcess.return_value = 123
        kernel.GetCurrentProcessId.return_value = 100
        pipe = FakePipe()
        with (
            mock.patch("scripts.windows_standard_user_token_probe.sys.platform", "win32"),
            mock.patch(
                "scripts.windows_standard_user_token_probe.ctypes.WinDLL",
                return_value=kernel,
                create=True,
            ),
            mock.patch(
                "scripts.windows_standard_user_token_probe.runner_process_logon_sid",
                return_value="S-1-5-5-123-456",
            ),
            mock.patch(
                "scripts.windows_standard_user_token_probe.create_runner_pipe_server",
                return_value=pipe,
            ),
            mock.patch(
                "scripts.windows_standard_user_token_probe.open_runner_pipe_client",
                side_effect=TimeoutError("runner_pipe_wait_timeout"),
            ),
        ):
            result = runner_pipe_wrong_server_pid_probe()

        self.assertEqual(result, (False, "client_timeout"))

    def test_wrong_server_pid_probe_classifies_client_denial_stage_when_server_accept_times_out(self) -> None:
        class FakePipe:
            name = r"\\.\pipe\icode-runner-" + "c" * 32

            def __init__(self) -> None:
                self._connected = False

            def _connect(self, timeout_ms: int) -> None:
                raise TimeoutError("runner_pipe_connect_timeout")

            def __enter__(self) -> "FakePipe":
                return self

            def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
                return None

            def close(self) -> None:
                return None

        pipe = FakePipe()
        failures = (
            ("runner_pipe_wait_access_denied", "client_wait_access_denied"),
            ("runner_pipe_open_access_denied", "client_open_access_denied"),
            ("runner_pipe_server_pid_query", "client_server_pid_query_access_denied"),
        )
        for error_stage, expected_stage in failures:
            with self.subTest(error_stage=error_stage):
                kernel = mock.Mock()
                kernel.GetCurrentProcess.return_value = 123
                kernel.GetCurrentProcessId.return_value = 100
                with (
                    mock.patch("scripts.windows_standard_user_token_probe.sys.platform", "win32"),
                    mock.patch(
                        "scripts.windows_standard_user_token_probe.ctypes.WinDLL",
                        return_value=kernel,
                        create=True,
                    ),
                    mock.patch(
                        "scripts.windows_standard_user_token_probe.runner_process_logon_sid",
                        return_value="S-1-5-5-123-456",
                    ),
                    mock.patch(
                        "scripts.windows_standard_user_token_probe.create_runner_pipe_server",
                        return_value=pipe,
                    ),
                    mock.patch(
                        "scripts.windows_standard_user_token_probe.open_runner_pipe_client",
                        side_effect=PermissionError(5, error_stage),
                    ),
                    mock.patch(
                        "scripts.windows_standard_user_token_probe._diagnose_runner_pipe_access",
                        return_value=(
                            "dacl_present+ace_match+token_process+logon_enabled+"
                            "restricted_no+access_allow"
                        ),
                    ) as access_diagnostic,
                ):
                    result = runner_pipe_wrong_server_pid_probe()

                access_diagnostic.assert_called_once_with(
                    getattr(pipe, "_handle", 0), "S-1-5-5-123-456",
                )

                expected_result = (
                    (False,
                     "client_open_access_denied+dacl_present+ace_match+token_process+"
                     "logon_enabled+restricted_no+access_allow")
                    if expected_stage == "client_open_access_denied"
                    else (False, f"{expected_stage}+server_accept_timeout")
                )
                self.assertEqual(
                    result,
                    expected_result,
                )
                if expected_stage == "client_open_access_denied":
                    diagnostic_detail = expected_result[1].removeprefix(
                        "client_open_access_denied+",
                    )
                    self.assertNotEqual(
                        restricted_child_failure_detail(
                            "failed=runner_pipe_server_pid_mismatch;detail="
                            + diagnostic_detail
                        ),
                        "unclassified",
                    )

    def test_checkout_script_imports_package_without_pythonpath(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)

        result = subprocess.run(
            [
                sys.executable,
                "-S",
                str(repository / "scripts" / "windows_standard_user_token_probe.py"),
                "--invalid-test-argument",
            ],
            cwd=repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("restricted_token_probe_arguments_invalid", result.stdout)

    def test_staged_runner_imports_its_copied_package_from_pythonpath(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = ""

        with tempfile.TemporaryDirectory() as temporary_directory:
            scratch = Path(temporary_directory)
            staged = stage_runner_script(
                repository / "scripts" / "windows_standard_user_token_probe.py",
                scratch,
            )
            environment["PYTHONPATH"] = str(scratch / "runner-lib")
            result = subprocess.run(
                [
                    sys.executable, "-S", str(staged),
                    "--invalid-test-argument",
                ],
                cwd=scratch,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("restricted_token_probe_arguments_invalid", result.stdout)

    def test_runner_success_classifier_requires_all_gate_results(self) -> None:
        self.assertTrue(runner_probe_succeeded(
            "runner_standard_user=PASS;server_pid_mismatch=PASS;"
            "child_restricted=PASS;child_non_admin=PASS;"
            "child_identity=PASS;job_assignment=PASS;exit=PASS",
        ))
        self.assertFalse(runner_probe_succeeded(
            "runner_standard_user=PASS;server_pid_mismatch=PASS;"
            "child_restricted=PASS;child_non_admin=FAIL;"
            "child_identity=PASS;job_assignment=PASS;exit=PASS",
        ))
        self.assertFalse(runner_probe_succeeded(
            "runner_standard_user=PASS;server_pid_mismatch=FAIL;"
            "child_restricted=PASS;child_non_admin=PASS;child_identity=PASS;"
            "job_assignment=PASS;exit=PASS",
        ))
        self.assertFalse(runner_probe_succeeded("unsupported_platform"))

    def test_restricted_child_failure_detail_preserves_only_sanitized_diagnostics(self) -> None:
        self.assertEqual(
            restricted_child_failure_detail(
                "failed=runner_pipe_server_pid_mismatch;detail=client_open_access_denied"
            ),
            "runner_pipe_server_pid_mismatch:client_open_access_denied",
        )
        self.assertEqual(restricted_child_failure_detail("failed=old_failure"), "old_failure")
        self.assertEqual(
            restricted_child_failure_detail("failed=stage;detail=bad value"),
            "unclassified",
        )
        self.assertEqual(
            restricted_child_failure_detail("failed=stage;detail=" + "x" * 121),
            "unclassified",
        )

    def test_wrong_pid_probe_runs_in_standard_user_context_and_still_handshakes(self) -> None:
        class FakePipe:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            def __enter__(self) -> "FakePipe":
                return self

            def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
                return None

            def send_message(self, message: dict[str, object], *, timeout_ms: int) -> None:
                self.messages.append(message)

        with tempfile.TemporaryDirectory() as temporary_directory:
            report = Path(temporary_directory) / "result.txt"
            pipe = FakePipe()
            with (
                mock.patch("scripts.windows_standard_user_token_probe.sys.platform", "win32"),
                mock.patch.dict(os.environ, {
                    "TEMP": temporary_directory,
                    "ICODE_R2_PROBE_MODE": "runner",
                }),
                mock.patch(
                    "scripts.windows_standard_user_token_probe.runner_pipe_wrong_server_pid_probe",
                    return_value=(False, "client_open_access_denied"),
                ) as wrong_pid_probe,
                mock.patch(
                    "scripts.windows_standard_user_token_probe.open_runner_pipe_client",
                    return_value=pipe,
                ) as open_parent_pipe,
                mock.patch(
                    "scripts.windows_standard_user_token_probe._runner_probe",
                    return_value="unused",
                ) as runner_probe,
                mock.patch("scripts.windows_standard_user_token_probe._write_report") as write_report,
            ):
                result = _run_child_mode(
                    str(report), r"\\.\pipe\icode-runner-" + "a" * 32,
                    "1234", "b" * 32,
                )

        self.assertEqual(result, 1)
        wrong_pid_probe.assert_called_once_with()
        open_parent_pipe.assert_called_once()
        self.assertEqual(pipe.messages[0]["type"], "spawn_ready")
        runner_probe.assert_not_called()
        write_report.assert_called_once_with(
            report,
            "failed=runner_pipe_server_pid_mismatch;detail=client_open_access_denied",
        )

    def test_wrong_pid_success_is_required_before_standard_user_probe_passes(self) -> None:
        class FakePipe:
            def __enter__(self) -> "FakePipe":
                return self

            def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
                return None

            def send_message(self, _message: dict[str, object], *, timeout_ms: int) -> None:
                return None

        success = (
            "runner_standard_user=PASS;server_pid_mismatch=PASS;"
            "child_restricted=PASS;child_non_admin=PASS;child_identity=PASS;"
            "job_assignment=PASS;exit=PASS"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = Path(temporary_directory) / "result.txt"
            with (
                mock.patch("scripts.windows_standard_user_token_probe.sys.platform", "win32"),
                mock.patch.dict(os.environ, {
                    "TEMP": temporary_directory,
                    "ICODE_R2_PROBE_MODE": "runner",
                }),
                mock.patch(
                    "scripts.windows_standard_user_token_probe.runner_pipe_wrong_server_pid_probe",
                    return_value=(True, "server_pid_mismatch_rejected"),
                ),
                mock.patch(
                    "scripts.windows_standard_user_token_probe.open_runner_pipe_client",
                    return_value=FakePipe(),
                ),
                mock.patch(
                    "scripts.windows_standard_user_token_probe._runner_probe",
                    return_value=success,
                ) as runner_probe,
                mock.patch("scripts.windows_standard_user_token_probe._write_report") as write_report,
            ):
                result = _run_child_mode(
                    str(report), r"\\.\pipe\icode-runner-" + "c" * 32,
                    "1234", "d" * 32,
                )

        self.assertEqual(result, 0)
        runner_probe.assert_called_once_with(report)
        write_report.assert_called_once_with(report, success)

    def test_logon_rejection_requires_expected_error_and_no_side_effects(self) -> None:
        expected = {
            "expected_error_codes": (1326,),
            "created": False,
            "error_code": 1326,
            "process_started": False,
            "marker_exists": False,
            "process_residual": False,
        }
        self.assertTrue(logon_rejection_succeeded(**expected))

        failure_cases = (
            {"created": True},
            {"error_code": 5},
            {"process_started": True},
            {"marker_exists": True},
            {"process_residual": True},
        )
        for override in failure_cases:
            with self.subTest(override=override):
                self.assertFalse(
                    logon_rejection_succeeded(**{**expected, **override}),
                )

    def test_missing_account_accepts_only_documented_account_failure_codes(self) -> None:
        expected = {
            "expected_error_codes": (1317, 1326),
            "created": False,
            "error_code": 1317,
            "process_started": False,
            "marker_exists": False,
            "process_residual": False,
        }
        self.assertTrue(logon_rejection_succeeded(**expected))
        self.assertFalse(logon_rejection_succeeded(**{**expected, "error_code": 5}))

    def test_runner_environment_contains_only_explicit_non_secret_entries(self) -> None:
        block = build_runner_environment_block(
            python_executable=r"C:\Python\python.exe",
            scratch=r"C:\Users\Public\icode probe",
            system_root=r"C:\Windows",
        )
        entries = [item for item in block.split("\0") if item]
        names = {
            item[:item.index("=", 1)] if item.startswith("=")
            else item.split("=", 1)[0]
            for item in entries
        }
        self.assertEqual(
            names,
            {
                "=C:", "SystemRoot", "WINDIR", "PATH", "TEMP", "TMP",
                "PYTHONNOUSERSITE", "PYTHONUTF8", "PYTHONPATH", "ICODE_R2_PROBE_MODE",
            },
        )
        self.assertTrue(block.endswith("\0\0"))
        self.assertNotIn("ICODE_PROBE_PASSWORD", block)
        self.assertNotIn("GITHUB_TOKEN", block)
        self.assertIn("C:\\Users\\Public\\icode probe", block)
        self.assertIn(
            "PYTHONPATH=C:\\Users\\Public\\icode probe\\runner-lib",
            block,
        )

    def test_runner_command_line_quotes_paths_and_obeys_logon_api_limit(self) -> None:
        command = build_runner_command_line(
            r"C:\Python Dir\python.exe",
            r"D:\checkout dir\probe.py",
            r"C:\Users\Public\probe result.txt",
        )
        self.assertIn('"C:\\Python Dir\\python.exe"', command)
        self.assertIn('"D:\\checkout dir\\probe.py"', command)
        self.assertLess(len(command), 1024)

    def test_runner_pipe_command_line_binds_random_endpoint_parent_and_request(self) -> None:
        command = build_runner_pipe_command_line(
            r"C:\Python Dir\python.exe",
            r"D:\checkout dir\probe.py",
            r"C:\Users\Public\probe result.txt",
            r"\\.\pipe\icode-runner-" + "a1" * 16,
            4321,
            "0123456789abcdef0123456789abcdef",
        )
        self.assertIn(
            "--pipe " + r"\\.\pipe\icode-runner-" + "a1" * 16,
            command,
        )
        self.assertIn('--server-pid 4321', command)
        self.assertIn('--request-id 0123456789abcdef0123456789abcdef', command)
        self.assertLess(len(command), 1024)

        with self.assertRaises(ValueError):
            build_runner_pipe_command_line(
                r"C:\Python\python.exe", r"D:\probe.py", r"C:\Temp\result.txt",
                r"\\.\pipe\other", 4321, "0123456789abcdef0123456789abcdef",
            )

    def test_runner_environment_rejects_unsafe_path_serialization(self) -> None:
        cases = (
            {"python_executable": "python.exe"},
            {"scratch": r"C:\Temp" + "\0bad"},
            {"system_root": ""},
        )
        base = {
            "python_executable": r"C:\Python\python.exe",
            "scratch": r"C:\Temp",
            "system_root": r"C:\Windows",
        }
        for override in cases:
            with self.subTest(override=override):
                values = {**base, **override}
                with self.assertRaises(ValueError):
                    build_runner_environment_block(**values)

    def test_runner_command_line_rejects_overlong_or_relative_arguments(self) -> None:
        with self.assertRaises(ValueError):
            build_runner_command_line(
                r"C:\Python\python.exe",
                "D:\\" + "a" * 1100 + r"\probe.py",
                r"C:\Temp\result.txt",
            )
        with self.assertRaises(ValueError):
            build_runner_command_line(
                "python.exe", r"D:\probe.py", r"C:\Temp\result.txt",
            )

    def test_environment_buffer_preserves_exact_double_terminator(self) -> None:
        block = build_runner_environment_block(
            python_executable=r"C:\Python\python.exe",
            scratch=r"C:\Temp",
            system_root=r"C:\Windows",
        )
        buffer = _make_environment_buffer(block)
        self.assertEqual(len(buffer), len(block))
        self.assertEqual(buffer[-1], "\0")

    def test_system_acl_tool_gets_no_ambient_credentials_or_runner_variables(self) -> None:
        environment = build_system_tool_environment(r"C:\Windows")
        self.assertEqual(
            environment,
            {
                "SystemRoot": r"C:\Windows",
                "WINDIR": r"C:\Windows",
                "PATH": r"C:\Windows\System32",
            },
        )

    def test_runner_script_is_copied_into_the_acl_controlled_scratch_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            source = base / "checkout" / "probe.py"
            scratch = base / "public" / "scratch"
            source.parent.mkdir()
            scratch.mkdir(parents=True)
            source.write_text("fixed probe source\n", encoding="utf-8")

            staged = stage_runner_script(source, scratch)

            self.assertEqual(staged.parent, scratch)
            self.assertEqual(staged.read_text(encoding="utf-8"), "fixed probe source\n")
            self.assertEqual(staged.name, "windows_standard_user_token_probe.py")
            runner_lib = scratch / "runner-lib" / "icode"
            self.assertTrue((runner_lib / "__init__.py").is_file())
            self.assertTrue((runner_lib / "windows_runner_pipe.py").is_file())
            self.assertTrue((runner_lib / "windows_runner_protocol.py").is_file())


if __name__ == "__main__":
    unittest.main()
