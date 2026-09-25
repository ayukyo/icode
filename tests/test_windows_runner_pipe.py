from __future__ import annotations

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
    runner_process_user_sid,
    select_logon_sid,
    validate_runner_pipe_name,
)


class TestWindowsRunnerPipePolicy(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
