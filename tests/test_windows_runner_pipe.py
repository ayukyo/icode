from __future__ import annotations

import ctypes
import os
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from icode import windows_runner_pipe
from icode.windows_runner_pipe import (
    FILE_FLAG_FIRST_PIPE_INSTANCE,
    FILE_FLAG_OVERLAPPED,
    PIPE_CLIENT_ACCESS_MASK,
    PIPE_REJECT_REMOTE_CLIENTS,
    build_runner_pipe_sddl,
    create_runner_pipe_server,
    new_runner_pipe_name,
    open_runner_pipe_client,
    runner_process_logon_sid,
    runner_process_user_sid,
    RunnerPipeServer,
    select_logon_sid,
    validate_runner_pipe_name,
)
from icode.windows_runner_protocol import RunnerProtocolError


REQUEST_ID = "0123456789abcdef0123456789abcdef"


def _spawn_request(request_id: str = REQUEST_ID) -> dict[str, object]:
    return {
        "version": 1,
        "type": "spawn_request",
        "request_id": request_id,
        "argv": ["python", "-c", "print('ready')"],
        "cwd_rel": ".",
        "timeout_ms": 1_000,
        "output_limit_bytes": 1_024,
    }


def _authenticated_server() -> RunnerPipeServer:
    api = windows_runner_pipe._Win32Api(
        kernel=SimpleNamespace(),
        advapi=SimpleNamespace(),
    )
    server = RunnerPipeServer(
        name=r"\\.\pipe\icode-runner-" + "a" * 32,
        handle=0x5678,
        api=api,
    )
    def mark_connected(_timeout_ms: int) -> None:
        server._connected = True

    server._connect = mock.Mock(side_effect=mark_connected)
    server._receive_wire_message = mock.Mock(return_value={
        "version": 1,
        "type": "spawn_ready",
        "request_id": REQUEST_ID,
    })
    with mock.patch("icode.windows_runner_pipe._authenticate_client"):
        server.wait_for_runner_ready(
            expected_process_handle=123,
            expected_user_sid="S-1-5-21-1-2-3-1001",
            expected_logon_sid="S-1-5-5-100-200",
            request_id=REQUEST_ID,
        )
    return server


def _native_pipe_access_control_receipt() -> str:
    """Run existing no-payload ACL controls and return only fixed labels."""
    try:
        from scripts.windows_standard_user_token_probe import (
            _runner_pipe_probe_receipt_code,
            _self_pipe_access_receipt_label,
            runner_pipe_open_with_default_dacl_probe,
            runner_pipe_open_with_user_sid_dacl_probe,
            runner_pipe_wrong_server_pid_probe,
        )

        self_opened, self_detail = runner_pipe_wrong_server_pid_probe()
        if self_opened is True:
            self_state = "self_pipe_ok"
        elif (
            type(self_detail) is str
            and self_detail.startswith("client_open_access_denied")
        ):
            self_state = "self_pipe_denied"
        else:
            self_state = "self_pipe_other"
        self_access = _self_pipe_access_receipt_label(self_detail)

        default_opened, default_detail = runner_pipe_open_with_default_dacl_probe()
        user_opened, user_detail = runner_pipe_open_with_user_sid_dacl_probe()
        default_receipt = _runner_pipe_probe_receipt_code(
            "d", default_opened, default_detail,
        )
        user_receipt = _runner_pipe_probe_receipt_code(
            "u", user_opened, user_detail,
        )
        return (
            f"self_pipe={self_state}:{self_access};"
            f"temporary_dacl={default_receipt}_{user_receipt}"
        )
    except Exception:
        return "self_pipe=unavailable;temporary_dacl=unavailable"


class TestWindowsRunnerPipePolicy(unittest.TestCase):
    def test_server_refuses_to_send_or_receive_before_runner_authentication(self) -> None:
        api = windows_runner_pipe._Win32Api(
            kernel=SimpleNamespace(),
            advapi=SimpleNamespace(),
        )
        server = RunnerPipeServer(
            name=r"\\.\pipe\icode-runner-" + "b" * 32,
            handle=0x5678,
            api=api,
        )

        with self.assertRaisesRegex(RuntimeError, "runner_pipe_not_authenticated"):
            server.send_message(_spawn_request())
        with self.assertRaisesRegex(RuntimeError, "runner_pipe_not_authenticated"):
            server.receive_message()

    def test_ready_handshake_is_correlated_and_cannot_be_replayed(self) -> None:
        api = windows_runner_pipe._Win32Api(
            kernel=SimpleNamespace(),
            advapi=SimpleNamespace(),
        )
        server = RunnerPipeServer(
            name=r"\\.\pipe\icode-runner-" + "c" * 32,
            handle=0x5678,
            api=api,
        )
        server._connect = mock.Mock(side_effect=lambda _timeout_ms: setattr(server, "_connected", True))
        server._receive_wire_message = mock.Mock(return_value={
            "version": 1,
            "type": "spawn_ready",
            "request_id": "f" * 32,
        })
        with mock.patch("icode.windows_runner_pipe._authenticate_client") as authenticate:
            with self.assertRaisesRegex(RunnerProtocolError, "request_id_mismatch"):
                server.wait_for_runner_ready(
                    expected_process_handle=123,
                    expected_user_sid="S-1-5-21-1-2-3-1001",
                    expected_logon_sid="S-1-5-5-100-200",
                    request_id=REQUEST_ID,
                )
            authenticate.assert_not_called()

        with self.assertRaisesRegex(RuntimeError, "runner_ready_already_attempted"):
            server.wait_for_runner_ready(
                expected_process_handle=123,
                expected_user_sid="S-1-5-21-1-2-3-1001",
                expected_logon_sid="S-1-5-5-100-200",
                request_id=REQUEST_ID,
            )

    def test_authenticated_server_sends_one_correlated_spawn_request(self) -> None:
        server = _authenticated_server()
        message = _spawn_request()

        with mock.patch("icode.windows_runner_pipe._write_all") as write_all:
            server.send_message(message, timeout_ms=1_000)

            write_all.assert_called_once_with(
                server._api,
                server._handle,
                windows_runner_pipe.encode_frame(message),
                1_000,
            )
            with self.assertRaisesRegex(RunnerProtocolError, "spawn_request_already_sent"):
                server.send_message(message, timeout_ms=1_000)

    def test_server_rejects_wrong_request_id_and_runner_to_host_message_types(self) -> None:
        server = _authenticated_server()
        wrong_request = _spawn_request("f" * 32)
        runner_message = {
            "version": 1,
            "type": "spawn_ready",
            "request_id": REQUEST_ID,
        }

        with mock.patch("icode.windows_runner_pipe._write_all") as write_all:
            with self.assertRaisesRegex(RunnerProtocolError, "request_id_mismatch"):
                server.send_message(wrong_request)
            with self.assertRaisesRegex(
                RunnerProtocolError,
                "unsupported_server_message_type",
            ):
                server.send_message(runner_message)

        write_all.assert_not_called()

    def test_cancel_before_spawn_prevents_later_spawn(self) -> None:
        server = _authenticated_server()
        cancel = {
            "version": 1,
            "type": "cancel_request",
            "request_id": REQUEST_ID,
        }

        with mock.patch("icode.windows_runner_pipe._write_all") as write_all:
            server.send_message(cancel)
            with self.assertRaisesRegex(RunnerProtocolError, "runner_request_cancelled"):
                server.send_message(_spawn_request())

        self.assertEqual(write_all.call_count, 1)

    def test_output_sequence_correlation_and_terminal_state_are_enforced(self) -> None:
        server = _authenticated_server()
        with mock.patch("icode.windows_runner_pipe._write_all"):
            server.send_message(_spawn_request())
        messages = iter((
            {
                "version": 1,
                "type": "output",
                "request_id": REQUEST_ID,
                "sequence": 1,
                "data_b64": "aGVsbG8=",
            },
            {
                "version": 1,
                "type": "output",
                "request_id": REQUEST_ID,
                "sequence": 2,
                "data_b64": "d29ybGQ=",
            },
        ))
        server._receive_wire_message = mock.Mock(
            side_effect=lambda **_kwargs: next(messages),
        )
        self.assertEqual(server.receive_message()["sequence"], 1)
        self.assertEqual(server.receive_message()["sequence"], 2)

        server._receive_wire_message = mock.Mock(return_value={
            "version": 1,
            "type": "output",
            "request_id": "f" * 32,
            "sequence": 3,
            "data_b64": "d29ybGQ=",
        })
        with self.assertRaisesRegex(RunnerProtocolError, "request_id_mismatch"):
            server.receive_message()

    def test_server_requires_contiguous_output_and_one_terminal_response(self) -> None:
        server = _authenticated_server()
        with mock.patch("icode.windows_runner_pipe._write_all"):
            server.send_message(_spawn_request())

        server._receive_wire_message = mock.Mock(return_value={
            "version": 1,
            "type": "output",
            "request_id": REQUEST_ID,
            "sequence": 2,
            "data_b64": "d29ybGQ=",
        })
        with self.assertRaisesRegex(RunnerProtocolError, "output_sequence_mismatch"):
            server.receive_message()

        terminal_server = _authenticated_server()
        with mock.patch("icode.windows_runner_pipe._write_all"):
            terminal_server.send_message(_spawn_request())
        exit_message = {
            "version": 1,
            "type": "exit",
            "request_id": REQUEST_ID,
            "exit_code": 0,
            "timed_out": False,
            "output_truncated": False,
            "cleanup_ok": True,
        }
        terminal_server._receive_wire_message = mock.Mock(return_value=exit_message)
        self.assertEqual(terminal_server.receive_message(), exit_message)
        with self.assertRaisesRegex(
            RunnerProtocolError,
            "runner_pipe_session_failed|runner_pipe_terminal_message_received",
        ):
            terminal_server.receive_message()

    def test_cancel_ack_requires_a_cancel_and_cannot_be_repeated(self) -> None:
        cancel_ack = {
            "version": 1,
            "type": "cancel_ack",
            "request_id": REQUEST_ID,
            "cancelled": True,
        }
        server = _authenticated_server()
        server._receive_wire_message = mock.Mock(return_value=cancel_ack)
        with self.assertRaisesRegex(RunnerProtocolError, "unsolicited_cancel_ack"):
            server.receive_message()

        cancelled_server = _authenticated_server()
        with mock.patch("icode.windows_runner_pipe._write_all"):
            cancelled_server.send_message({
                "version": 1,
                "type": "cancel_request",
                "request_id": REQUEST_ID,
            })
        cancelled_server._receive_wire_message = mock.Mock(return_value=cancel_ack)
        self.assertEqual(cancelled_server.receive_message(), cancel_ack)
        with self.assertRaisesRegex(RunnerProtocolError, "duplicate_cancel_ack"):
            cancelled_server.receive_message()

    def test_failed_partial_send_poisons_server_transport(self) -> None:
        server = _authenticated_server()

        with mock.patch(
            "icode.windows_runner_pipe._write_all",
            side_effect=OSError("partial write"),
        ):
            with self.assertRaisesRegex(OSError, "partial write"):
                server.send_message(_spawn_request())

        with mock.patch("icode.windows_runner_pipe._write_all") as write_all:
            with self.assertRaisesRegex(RunnerProtocolError, "runner_pipe_session_failed"):
                server.send_message(_spawn_request())

        write_all.assert_not_called()

    @unittest.skipIf(
        sys.platform == "win32",
        "Linux only: fixed unavailable-host receipt",
    )
    def test_native_pipe_diagnostic_receipt_is_fixed_when_unavailable(self) -> None:
        self.assertEqual(
            _native_pipe_access_control_receipt(),
            "self_pipe=self_pipe_other:self_access_unavailable;"
            "temporary_dacl=dfuuuu_ufuuuu",
        )

    def test_pipe_security_descriptor_shape_receipt_is_bounded_and_sid_free(self) -> None:
        from scripts import windows_standard_user_token_probe as probe

        formatter = getattr(probe, "_format_pipe_security_descriptor_shape", None)
        self.assertTrue(callable(formatter), "descriptor_shape_formatter_missing")
        receipt = formatter(
            control=0x8004,
            revision=1,
            owner_relation="user",
            group_relation="other",
            dacl_state="present",
            acl_revision=2,
            ace_count=1,
            ace_records=((0, 0, PIPE_CLIENT_ACCESS_MASK),),
        )
        self.assertEqual(
            receipt,
            "sd_control=8004;sd_revision=1;owner=user;group=other;"
            "dacl=present;acl_revision=2;ace_count=1;"
            "aces=00.00.00100003;truncated=0",
        )
        self.assertLessEqual(len(receipt), 384)
        self.assertNotIn("S-1-5-", receipt)

    def test_pipe_security_descriptor_shape_receipt_rejects_unbounded_fields(self) -> None:
        from scripts import windows_standard_user_token_probe as probe

        formatter = getattr(probe, "_format_pipe_security_descriptor_shape", None)
        self.assertTrue(callable(formatter), "descriptor_shape_formatter_missing")
        receipt = formatter(
            control=0x8004,
            revision=1,
            owner_relation="S-1-5-21-1001",
            group_relation="other",
            dacl_state="present",
            acl_revision=2,
            ace_count=257,
            ace_records=((0, 0, PIPE_CLIENT_ACCESS_MASK),),
        )
        self.assertEqual(receipt, "sd=unavailable")

        many_aces = tuple(
            (index, index, PIPE_CLIENT_ACCESS_MASK)
            for index in range(9)
        )
        bounded = formatter(
            control=0x8004,
            revision=1,
            owner_relation="user",
            group_relation="logon",
            dacl_state="present",
            acl_revision=2,
            ace_count=len(many_aces),
            ace_records=many_aces,
        )
        self.assertIn("ace_count=9", bounded)
        self.assertIn("truncated=1", bounded)
        self.assertLessEqual(len(bounded), 384)

    @unittest.skipIf(sys.platform == "win32", "非 Windows 固定降级回执")
    def test_pipe_security_descriptor_probe_is_unavailable_off_windows(self) -> None:
        from scripts.windows_standard_user_token_probe import (
            runner_pipe_security_descriptor_shape,
        )

        self.assertEqual(
            runner_pipe_security_descriptor_shape(0, None, None),
            "sd=unavailable",
        )

    def test_pipe_direction_receipt_is_fixed_and_bounded(self) -> None:
        from scripts import windows_standard_user_token_probe as probe

        formatter = getattr(
            probe, "_format_runner_pipe_direction_receipt", None,
        )
        self.assertTrue(callable(formatter), "direction_receipt_formatter_missing")
        self.assertEqual(
            formatter("opened", "open_access_denied"),
            "pipe_direction=duplex_opened_outbound_open_access_denied",
        )
        self.assertEqual(
            formatter("S-1-5-21-secret", "open_access_denied"),
            "pipe_direction=duplex_unavailable_outbound_open_access_denied",
        )
        bounded = formatter("x" * 10_000, "open_failed")
        self.assertEqual(
            bounded,
            "pipe_direction=duplex_unavailable_outbound_open_failed",
        )
        self.assertEqual(
            formatter([], "open_failed"),
            "pipe_direction=duplex_unavailable_outbound_open_failed",
        )
        self.assertLessEqual(len(bounded), 128)

    def test_pipe_direction_probe_dacl_is_sid_bound_and_read_only(self) -> None:
        from scripts import windows_standard_user_token_probe as probe

        builder = getattr(
            probe, "_runner_pipe_direction_probe_sddl", None,
        )
        self.assertTrue(callable(builder), "direction_probe_sddl_builder_missing")
        logon_sid = "S-1-5-5-100-200"
        self.assertEqual(
            builder(logon_sid),
            f"D:P(A;;GR;;;{logon_sid})",
        )
        with self.assertRaisesRegex(ValueError, "invalid_runner_sid"):
            builder("S-1-5-21-secret")

    def test_pipe_direction_probe_changes_only_server_direction(self) -> None:
        from scripts import windows_standard_user_token_probe as probe

        descriptor_conversion = mock.Mock(
            side_effect=lambda _sddl, _revision, output, _size: (
                setattr(output._obj, "value", 0x7777) or 1
            ),
        )
        created_pipes: list[tuple[object, ...]] = []
        opened_clients: list[tuple[object, ...]] = []
        kernel = SimpleNamespace(
            GetCurrentProcess=mock.Mock(return_value=0x1111),
            CreateNamedPipeW=mock.Mock(
                side_effect=lambda *args: (
                    created_pipes.append(args) or (0x2000 + len(created_pipes))
                ),
            ),
            WaitNamedPipeW=mock.Mock(return_value=1),
            CreateFileW=mock.Mock(
                side_effect=lambda *args: (
                    opened_clients.append(args) or (0x3000 + len(opened_clients))
                ),
            ),
            CloseHandle=mock.Mock(return_value=1),
            LocalFree=mock.Mock(return_value=0),
        )
        api = SimpleNamespace(
            kernel=kernel,
            advapi=SimpleNamespace(
                ConvertStringSecurityDescriptorToSecurityDescriptorW=(
                    descriptor_conversion
                ),
            ),
        )

        with (
            mock.patch.object(probe, "sys", SimpleNamespace(platform="win32")),
            mock.patch(
                "icode.windows_runner_pipe._load_win32_api",
                return_value=api,
            ),
            mock.patch.object(
                probe, "runner_process_logon_sid", return_value="S-1-5-5-100-200",
            ),
        ):
            receipt = probe.runner_pipe_server_direction_probe()

        self.assertEqual(
            receipt,
            "pipe_direction=duplex_opened_outbound_opened",
        )
        self.assertEqual(len(created_pipes), 2)
        server_open_modes = [arguments[1] for arguments in created_pipes]
        self.assertEqual(
            [mode & 0x3 for mode in server_open_modes],
            [0x3, 0x2],
        )
        self.assertEqual(
            server_open_modes[0] & ~0x3,
            server_open_modes[1] & ~0x3,
        )
        self.assertEqual(created_pipes[0][2:7], created_pipes[1][2:7])
        descriptor_conversion.assert_called_once()
        self.assertEqual(
            descriptor_conversion.call_args.args[:2],
            ("D:P(A;;GR;;;S-1-5-5-100-200)", 1),
        )
        self.assertEqual(
            opened_clients[0][1:],
            (
                0x80000000,
                0,
                None,
                windows_runner_pipe._OPEN_EXISTING,
                FILE_FLAG_OVERLAPPED
                | windows_runner_pipe._SECURITY_SQOS_PRESENT
                | windows_runner_pipe._SECURITY_IMPERSONATION,
                None,
            ),
        )
        self.assertEqual(
            opened_clients[0][1:],
            opened_clients[1][1:],
        )
        self.assertEqual(kernel.WaitNamedPipeW.call_count, 2)
        self.assertEqual(kernel.CloseHandle.call_count, 4)

    def test_pipe_direction_probe_is_fixed_unavailable_off_windows(self) -> None:
        from scripts import windows_standard_user_token_probe as probe

        with mock.patch.object(probe, "sys", SimpleNamespace(platform="linux")):
            self.assertEqual(
                probe.runner_pipe_server_direction_probe(),
                "pipe_direction=duplex_unsupported_platform_"
                "outbound_unsupported_platform",
            )

    def test_server_accepts_client_that_connected_before_connect_named_pipe(self) -> None:
        kernel = SimpleNamespace(
            CreateEventW=mock.Mock(return_value=0x1234),
            ConnectNamedPipe=mock.Mock(return_value=0),
            CloseHandle=mock.Mock(return_value=1),
        )
        api = windows_runner_pipe._Win32Api(kernel=kernel, advapi=None)
        server = RunnerPipeServer(name=r"\\.\pipe\icode-runner-" + "f" * 32,
                                  handle=0x5678, api=api)

        with mock.patch.object(
            windows_runner_pipe.ctypes,
            "get_last_error",
            return_value=windows_runner_pipe._ERROR_PIPE_CONNECTED,
            create=True,
        ) as get_last_error:
            server._connect(1_000)

        self.assertTrue(server._connected)
        kernel.ConnectNamedPipe.assert_called_once()
        get_last_error.assert_called_once_with()
        kernel.CloseHandle.assert_called_once_with(0x1234)

    def test_unconfirmed_cancel_drain_has_a_finite_wait_and_pins_storage(self) -> None:
        kernel = SimpleNamespace(
            CancelIoEx=mock.Mock(return_value=1),
            WaitForSingleObject=mock.Mock(
                return_value=windows_runner_pipe._WAIT_TIMEOUT,
            ),
        )
        api = windows_runner_pipe._Win32Api(kernel=kernel, advapi=None)
        event = windows_runner_pipe.ctypes.c_void_p(0x1234)
        overlapped = windows_runner_pipe._OVERLAPPED()
        buffer = windows_runner_pipe.ctypes.create_string_buffer(b"x", 1)
        pending_count = len(windows_runner_pipe._PENDING_OVERLAPPED)

        try:
            result = windows_runner_pipe._cancel_and_drain(
                api, 1, overlapped, event, buffer,
            )

            self.assertEqual(
                result,
                (False, 0, windows_runner_pipe._WAIT_TIMEOUT, 0, True),
            )
            kernel.WaitForSingleObject.assert_called_once_with(event, 5_000)
            retained = windows_runner_pipe._PENDING_OVERLAPPED[pending_count]
            self.assertIs(retained[2], overlapped)
            self.assertIs(retained[4], event)
            self.assertIs(retained[5], buffer)
        finally:
            del windows_runner_pipe._PENDING_OVERLAPPED[pending_count:]

    def test_pipe_name_uses_128_bit_random_nonce_and_local_namespace(self) -> None:
        with mock.patch("icode.windows_runner_pipe.secrets.token_hex", return_value="a1" * 16):
            name = new_runner_pipe_name()

        self.assertEqual(name, r"\\.\pipe\icode-runner-" + "a1" * 16)
        self.assertRegex(name.rsplit("-", 1)[-1], r"[0-9a-f]{32}\Z")
        self.assertEqual(validate_runner_pipe_name(name), name)
        with self.assertRaises(ValueError):
            validate_runner_pipe_name(name + "\\child")

    def test_pipe_acl_only_grants_exact_runner_sid_and_no_instance_creation(self) -> None:
        sid = "S-1-5-21-111-222-333-1001"

        sddl = build_runner_pipe_sddl(sid)

        self.assertEqual(sddl, f"D:P(A;;0x{PIPE_CLIENT_ACCESS_MASK:08x};;;{sid})")
        self.assertNotIn("GA", sddl)
        self.assertNotIn("GW", sddl)
        self.assertEqual(PIPE_CLIENT_ACCESS_MASK & 0x00000004, 0)

    def test_invalid_sid_and_injected_sddl_text_are_rejected(self) -> None:
        for sid in (
            "",
            "S-1-5-21-1-2-3-x",
            "S-1-5-21-1-2-3-4);D:(A;;GA;;;WD",
            "S-1-5-21-1-2-3-4\x00",
        ):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                build_runner_pipe_sddl(sid)

    def test_native_endpoint_requires_exclusive_overlapped_local_pipe(self) -> None:
        self.assertTrue(windows_runner_pipe.RUNNER_PIPE_OPEN_MODE & FILE_FLAG_FIRST_PIPE_INSTANCE)
        self.assertTrue(windows_runner_pipe.RUNNER_PIPE_OPEN_MODE & FILE_FLAG_OVERLAPPED)
        self.assertTrue(windows_runner_pipe.RUNNER_PIPE_MODE & PIPE_REJECT_REMOTE_CLIENTS)
        self.assertEqual(windows_runner_pipe.RUNNER_PIPE_MAX_INSTANCES, 1)

    def test_server_rejects_non_windows_before_loading_native_apis(self) -> None:
        with mock.patch.object(windows_runner_pipe.sys, "platform", "linux"), \
             mock.patch.object(windows_runner_pipe.ctypes, "WinDLL", create=True) as load_api:
            with self.assertRaisesRegex(OSError, "unsupported_platform"):
                create_runner_pipe_server("S-1-5-21-1-2-3-1001")

        load_api.assert_not_called()

    def test_process_user_sid_rejects_non_windows_before_loading_native_apis(self) -> None:
        with mock.patch.object(windows_runner_pipe.sys, "platform", "linux"), \
             mock.patch.object(windows_runner_pipe.ctypes, "WinDLL", create=True) as load_api:
            with self.assertRaisesRegex(OSError, "unsupported_platform"):
                runner_process_user_sid(123)

        load_api.assert_not_called()

    def test_token_identity_requires_exactly_one_logon_sid_group(self) -> None:
        self.assertEqual(
            select_logon_sid([(0x1000, 0x4), (0x2000, 0xC0000000)]),
            0x2000,
        )
        for groups in (
            [],
            [(0x1000, 0x4)],
            [(0, 0xC0000000)],
            [(0x1000, 0xC0000000), (0x2000, 0xC0000000)],
            [(0x1000, "0xC0000000")],
        ):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                select_logon_sid(groups)

    def test_client_rejects_untrusted_pipe_names_and_invalid_pid_before_win32(self) -> None:
        with mock.patch.object(windows_runner_pipe.sys, "platform", "win32"), \
             mock.patch.object(windows_runner_pipe.ctypes, "WinDLL", create=True) as load_api:
            with self.assertRaises(ValueError):
                open_runner_pipe_client(r"\\.\pipe\other-service", 1234)
            with self.assertRaises(ValueError):
                open_runner_pipe_client(r"\\.\pipe\icode-runner-" + "a" * 32, 0)

        load_api.assert_not_called()

    def test_client_open_observer_runs_immediately_before_create_file(self) -> None:
        events: list[str] = []
        create_file_arguments: list[tuple[object, ...]] = []

        class FakeKernel:
            def WaitNamedPipeW(self, *_args) -> int:
                events.append("wait")
                return 1

            def CreateFileW(self, *_args) -> int:
                events.append("create_file")
                create_file_arguments.append(_args)
                return windows_runner_pipe._INVALID_HANDLE_VALUE

        api = windows_runner_pipe._Win32Api(kernel=FakeKernel(), advapi=None)

        def observe_open_attempt() -> None:
            events.append("observe")
            raise RuntimeError("private diagnostic failure")

        with (
            mock.patch.object(windows_runner_pipe.sys, "platform", "win32"),
            mock.patch.object(windows_runner_pipe, "_load_win32_api", return_value=api),
            mock.patch.object(
                windows_runner_pipe.ctypes,
                "get_last_error",
                return_value=5,
                create=True,
            ),
        ):
            with self.assertRaises(PermissionError) as raised:
                windows_runner_pipe._open_runner_pipe_client_with_observer(
                    r"\\.\pipe\icode-runner-" + "a" * 32,
                    1234,
                    timeout_ms=100,
                    observer=observe_open_attempt,
                )

        self.assertEqual(events, ["wait", "observe", "create_file"])
        self.assertEqual(raised.exception.errno, 5)
        self.assertEqual(raised.exception.strerror, "runner_pipe_open_access_denied")
        self.assertEqual(len(create_file_arguments), 1)
        _name, desired_access, share_mode, security, disposition, flags, template = (
            create_file_arguments[0]
        )
        self.assertEqual(desired_access, PIPE_CLIENT_ACCESS_MASK)
        self.assertEqual(share_mode, 0)
        self.assertIsNone(security)
        self.assertEqual(disposition, windows_runner_pipe._OPEN_EXISTING)
        self.assertEqual(
            flags,
            FILE_FLAG_OVERLAPPED
            | windows_runner_pipe._SECURITY_SQOS_PRESENT
            | windows_runner_pipe._SECURITY_IMPERSONATION,
        )
        self.assertIsNone(template)


@unittest.skipUnless(sys.platform == "win32", "需要 Windows 原生 named-pipe 双向验证")
class TestWindowsRunnerPipeNative(unittest.TestCase):
    def test_temporary_server_direction_ab_emits_fixed_receipt(self) -> None:
        from scripts.windows_standard_user_token_probe import (
            runner_pipe_server_direction_probe,
        )

        receipt = runner_pipe_server_direction_probe()
        print(f"::notice::{receipt}")
        prefix, _, states = receipt.partition("pipe_direction=")
        self.assertEqual(prefix, "")
        duplex_state, separator, outbound_state = states.partition(
            "_outbound_",
        )
        allowed_states = {
            "opened",
            "open_access_denied",
            "open_pipe_busy",
            "open_pipe_not_found",
            "open_failed",
            "wait_access_denied",
            "wait_timeout",
            "wait_failed",
            "server_create_access_denied",
            "server_create_failed",
            "security_descriptor_failed",
            "server_close_failed",
            "client_close_failed",
            "invalid_logon_sid",
            "security_descriptor_free_failed",
            "unsupported_platform",
            "probe_failed",
            "unavailable",
        }
        self.assertEqual(separator, "_outbound_")
        self.assertIn(duplex_state, allowed_states)
        self.assertIn(outbound_state, allowed_states)
        self.assertLessEqual(len(receipt), 128)

    def test_authenticated_pipe_round_trip_carries_one_bounded_request(self) -> None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        process_handle = kernel.GetCurrentProcess()
        process_id = os.getpid()
        user_sid = runner_process_user_sid(process_handle)
        logon_sid = runner_process_logon_sid(process_handle)
        server = create_runner_pipe_server(logon_sid)
        request_id = os.urandom(16).hex()
        ready = {
            "version": 1,
            "type": "spawn_ready",
            "request_id": request_id,
        }
        spawn = _spawn_request(request_id)
        output = {
            "version": 1,
            "type": "output",
            "request_id": request_id,
            "sequence": 1,
            "data_b64": "aGVsbG8=",
        }
        exit_message = {
            "version": 1,
            "type": "exit",
            "request_id": request_id,
            "exit_code": 0,
            "timed_out": False,
            "output_truncated": False,
            "cleanup_ok": True,
        }
        client_results: list[dict[str, object]] = []
        client_errors: list[BaseException] = []
        server_descriptor_shape = "sd=unavailable"

        def run_client() -> None:
            try:
                with open_runner_pipe_client(
                    server.name,
                    process_id,
                    timeout_ms=5_000,
                ) as client:
                    client.send_message(ready, timeout_ms=5_000)
                    client_results.append(client.receive_message(timeout_ms=5_000))
                    client.send_message(output, timeout_ms=5_000)
                    client.send_message(exit_message, timeout_ms=5_000)
            except BaseException as exc:  # relay thread failures to the test thread
                client_errors.append(exc)

        client_thread = threading.Thread(target=run_client, daemon=True)
        server_error: BaseException | None = None
        try:
            client_thread.start()
            server.wait_for_runner_ready(
                expected_process_handle=process_handle,
                expected_user_sid=user_sid,
                expected_logon_sid=logon_sid,
                request_id=request_id,
                timeout_ms=5_000,
            )
            server.send_message(spawn, timeout_ms=5_000)
            self.assertEqual(server.receive_message(timeout_ms=5_000), output)
            self.assertEqual(server.receive_message(timeout_ms=5_000), exit_message)
        except BaseException as exc:
            server_error = exc
        finally:
            from scripts.windows_standard_user_token_probe import (
                runner_pipe_security_descriptor_shape,
            )

            server_descriptor_shape = runner_pipe_security_descriptor_shape(
                server._handle, user_sid, logon_sid,
            )
            server.close()
            client_thread.join(timeout=6)

        self.assertFalse(client_thread.is_alive(), "named-pipe client thread leaked")
        if client_errors:
            client_error = client_errors[0]
            if isinstance(client_error, OSError):
                raw_stage = client_error.strerror or ""
                safe_stage = (
                    raw_stage
                    if len(raw_stage) <= 64
                    and raw_stage.isascii()
                    and all(
                        character.islower()
                        or character.isdigit()
                        or character == "_"
                        for character in raw_stage
                    )
                    else "unavailable"
                )
                details = (
                    f"errno={client_error.errno}:stage={safe_stage}"
                )
            else:
                details = f"type={type(client_error).__name__}"
            controls = (
                f";{_native_pipe_access_control_receipt()}"
                if isinstance(client_error, PermissionError)
                else ""
            )
            descriptor = (
                f";server_descriptor={server_descriptor_shape}"
                if isinstance(client_error, PermissionError)
                else ""
            )
            self.fail(
                f"native_pipe_client_failed:{details}{controls}{descriptor}"
            )
        if server_error is not None:
            raise server_error
        self.assertEqual(client_errors, [])
        self.assertEqual(client_results, [spawn])


if __name__ == "__main__":
    unittest.main()
