"""Authenticated, bounded named-pipe transport primitives for Windows runners.

This module does not launch a helper, authorize a command, install policy, or
provide a provisioning/service endpoint. Callers must hold the process handle
returned by the trusted launch operation and supply the runner's logon SID.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import re
import secrets
import struct
import sys
import time
from typing import Any, Callable

from .windows_runner_protocol import (
    MAX_FRAME_BYTES,
    RunnerProtocolError,
    decode_frame,
    encode_frame,
    validate_correlation,
)


FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
FILE_FLAG_OVERLAPPED = 0x40000000
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
PIPE_CLIENT_ACCESS_MASK = 0x00100003  # FILE_READ_DATA | FILE_WRITE_DATA | SYNCHRONIZE
RUNNER_PIPE_OPEN_MODE = 0x00000003 | FILE_FLAG_FIRST_PIPE_INSTANCE | FILE_FLAG_OVERLAPPED
RUNNER_PIPE_MODE = PIPE_REJECT_REMOTE_CLIENTS  # byte type, byte read mode, PIPE_WAIT are zero
RUNNER_PIPE_MAX_INSTANCES = 1
RUNNER_PIPE_BUFFER_BYTES = MAX_FRAME_BYTES + 4

_SID_RE = re.compile(r"S-1-[0-9]+(?:-[0-9]+){1,15}\Z", re.IGNORECASE)
_PIPE_NAME_RE = re.compile(r"\\\\\.\\pipe\\icode-runner-[0-9a-f]{32}\Z")
_REQUEST_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_MAX_TIMEOUT_MS = 120_000

_ERROR_FILE_NOT_FOUND = 2
_ERROR_ACCESS_DENIED = 5
_ERROR_PIPE_BUSY = 231
_ERROR_PIPE_CONNECTED = 535
_ERROR_SEM_TIMEOUT = 121
_ERROR_IO_PENDING = 997
_ERROR_OPERATION_ABORTED = 995
_ERROR_NOT_FOUND = 1168
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x00000102
_WAIT_FAILED = 0xFFFFFFFF
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_PENDING_OVERLAPPED: list[tuple[object, ...]] = []
_CANCEL_DRAIN_TIMEOUT_MS = 5_000

_TOKEN_QUERY = 0x0008
_TOKEN_USER_CLASS = 1
_TOKEN_GROUPS_CLASS = 2
_TOKEN_SESSION_ID_CLASS = 12
_SE_GROUP_LOGON_ID = 0xC0000000

_PIPE_TYPE_BYTE = 0
_PIPE_READMODE_BYTE = 0
_PIPE_WAIT = 0
_OPEN_EXISTING = 3
_SECURITY_SQOS_PRESENT = 0x00100000
_SECURITY_IMPERSONATION = 0x00020000


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", ctypes.c_uint32),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", ctypes.c_int32),
    ]


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", ctypes.c_uint32),
        ("OffsetHigh", ctypes.c_uint32),
        ("hEvent", ctypes.c_void_p),
    ]


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_uint32)]


class _TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


class _TOKEN_GROUPS_HEADER(ctypes.Structure):
    _fields_ = [("GroupCount", ctypes.c_uint32)]


class _TOKEN_GROUP(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_uint32)]


@dataclass
class _Win32Api:
    kernel: Any
    advapi: Any


def _validate_sid(sid: str) -> str:
    if type(sid) is not str or _SID_RE.fullmatch(sid) is None:
        raise ValueError("invalid_runner_sid")
    return sid


def _validate_timeout(timeout_ms: int) -> int:
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= _MAX_TIMEOUT_MS:
        raise ValueError("invalid_pipe_timeout")
    return timeout_ms


def validate_runner_pipe_name(name: str) -> str:
    if type(name) is not str or _PIPE_NAME_RE.fullmatch(name) is None:
        raise ValueError("invalid_runner_pipe_name")
    return name


def new_runner_pipe_name() -> str:
    """Return an unpredictable local pipe name with 128 bits of entropy."""
    nonce = secrets.token_hex(16)
    if type(nonce) is not str or re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        raise RuntimeError("secure_pipe_nonce_unavailable")
    return rf"\\.\pipe\icode-runner-{nonce}"


def build_runner_pipe_sddl(runner_logon_sid: str) -> str:
    """Grant only read/write data and synchronization to this logon SID.

    In particular, do not use FILE_GENERIC_WRITE or GENERIC_ALL: the generic
    write mapping also grants FILE_CREATE_PIPE_INSTANCE for named pipes.
    """
    sid = _validate_sid(runner_logon_sid)
    return f"D:P(A;;0x{PIPE_CLIENT_ACCESS_MASK:08x};;;{sid})"


def _load_win32_api() -> _Win32Api:
    if sys.platform != "win32":
        raise OSError("unsupported_platform")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)

    kernel.CreateNamedPipeW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.POINTER(_SECURITY_ATTRIBUTES),
    ]
    kernel.CreateNamedPipeW.restype = ctypes.c_void_p
    kernel.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_wchar_p]
    kernel.CreateEventW.restype = ctypes.c_void_p
    kernel.ConnectNamedPipe.argtypes = [ctypes.c_void_p, ctypes.POINTER(_OVERLAPPED)]
    kernel.ConnectNamedPipe.restype = ctypes.c_int32
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.GetOverlappedResult.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_OVERLAPPED), ctypes.POINTER(ctypes.c_uint32), ctypes.c_int32,
    ]
    kernel.GetOverlappedResult.restype = ctypes.c_int32
    kernel.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.POINTER(_OVERLAPPED)]
    kernel.CancelIoEx.restype = ctypes.c_int32
    kernel.ReadFile.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(_OVERLAPPED),
    ]
    kernel.ReadFile.restype = ctypes.c_int32
    kernel.WriteFile.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(_OVERLAPPED),
    ]
    kernel.WriteFile.restype = ctypes.c_int32
    kernel.WaitNamedPipeW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.WaitNamedPipeW.restype = ctypes.c_int32
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    ]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.GetNamedPipeClientProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
    ]
    kernel.GetNamedPipeClientProcessId.restype = ctypes.c_int32
    kernel.GetNamedPipeClientSessionId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
    ]
    kernel.GetNamedPipeClientSessionId.restype = ctypes.c_int32
    kernel.GetNamedPipeServerProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
    ]
    kernel.GetNamedPipeServerProcessId.restype = ctypes.c_int32
    kernel.GetProcessId.argtypes = [ctypes.c_void_p]
    kernel.GetProcessId.restype = ctypes.c_uint32
    kernel.GetCurrentThread.argtypes = []
    kernel.GetCurrentThread.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int32
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p

    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = ctypes.c_int32
    advapi.ConvertStringSidToSidW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi.ConvertStringSidToSidW.restype = ctypes.c_int32
    advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi.EqualSid.restype = ctypes.c_int32
    advapi.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    advapi.OpenProcessToken.restype = ctypes.c_int32
    advapi.OpenThreadToken.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.OpenThreadToken.restype = ctypes.c_int32
    advapi.GetTokenInformation.argtypes = [
        ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    advapi.GetTokenInformation.restype = ctypes.c_int32
    advapi.ImpersonateNamedPipeClient.argtypes = [ctypes.c_void_p]
    advapi.ImpersonateNamedPipeClient.restype = ctypes.c_int32
    advapi.RevertToSelf.argtypes = []
    advapi.RevertToSelf.restype = ctypes.c_int32
    return _Win32Api(kernel, advapi)


def _winerror(stage: str) -> OSError:
    code = ctypes.get_last_error()
    return OSError(code, stage)


def _event_key(event: object) -> int | None:
    if isinstance(event, int):
        return event
    value = getattr(event, "value", None)
    return value if isinstance(value, int) else None


def _event_has_pending_storage(event: object) -> bool:
    key = _event_key(event)
    return key is not None and any(record[3] == key for record in _PENDING_OVERLAPPED)


def _cancel_and_drain(
    api: _Win32Api,
    handle: int,
    overlapped: _OVERLAPPED,
    event: object,
    buffer: object,
) -> tuple[bool, int, int, int, bool]:
    cancelled = api.kernel.CancelIoEx(handle, ctypes.byref(overlapped))
    cancel_error = 0 if cancelled else ctypes.get_last_error()
    wait = api.kernel.WaitForSingleObject(event, _CANCEL_DRAIN_TIMEOUT_MS)
    if wait != _WAIT_OBJECT_0:
        # Keep the OVERLAPPED, event and data buffer alive if Win32 cannot confirm
        # cancellation completion; freeing them while I/O is pending is unsafe.
        _PENDING_OVERLAPPED.append((api, handle, overlapped, _event_key(event), event, buffer))
        return False, 0, wait, cancel_error, True
    transferred = ctypes.c_uint32(0)
    completed = api.kernel.GetOverlappedResult(
        handle, ctypes.byref(overlapped), ctypes.byref(transferred), 0,
    )
    completion_error = 0 if completed else ctypes.get_last_error()
    return bool(completed), int(transferred.value), completion_error, cancel_error, False


def _handle_is_invalid(handle: int | None) -> bool:
    return handle is None or handle == 0 or handle == _INVALID_HANDLE_VALUE


def _overlapped_transfer(
    api: _Win32Api,
    handle: int,
    buffer: ctypes.Array,
    offset: int,
    length: int,
    *,
    writing: bool,
    deadline: float,
) -> int:
    event = api.kernel.CreateEventW(None, 1, 0, None)
    if _handle_is_invalid(event):
        raise _winerror("pipe_create_io_event")
    overlapped = _OVERLAPPED()
    overlapped.hEvent = event
    transferred = ctypes.c_uint32(0)
    pointer = ctypes.cast(ctypes.byref(buffer, offset), ctypes.c_void_p)
    operation = api.kernel.WriteFile if writing else api.kernel.ReadFile
    try:
        success = operation(
            handle, pointer, length, ctypes.byref(transferred), ctypes.byref(overlapped),
        )
        if success:
            if transferred.value == 0:
                raise OSError("pipe_zero_length_transfer")
            return int(transferred.value)
        error = ctypes.get_last_error()
        if error != _ERROR_IO_PENDING:
            raise OSError(error, "pipe_io")

        remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
        wait_result = api.kernel.WaitForSingleObject(event, remaining_ms)
        if wait_result == _WAIT_TIMEOUT:
            completed, count, error, cancel_error, retained = _cancel_and_drain(
                api, handle, overlapped, event, buffer,
            )
            if retained:
                raise OSError(error, "pipe_io_cancel_unconfirmed")
            if completed:
                return count
            if error == _ERROR_OPERATION_ABORTED:
                raise TimeoutError("pipe_io_timeout")
            if cancel_error not in (0, _ERROR_NOT_FOUND):
                raise OSError(cancel_error, "pipe_cancel_io")
            raise OSError(error, "pipe_io_completion")
        if wait_result != _WAIT_OBJECT_0:
            wait_error = ctypes.get_last_error() if wait_result == _WAIT_FAILED else wait_result
            _, _, _, _, retained = _cancel_and_drain(
                api, handle, overlapped, event, buffer,
            )
            if retained:
                raise OSError(wait_error, "pipe_io_cancel_unconfirmed")
            raise OSError(wait_error, "pipe_wait_io")
        if not api.kernel.GetOverlappedResult(
            handle, ctypes.byref(overlapped), ctypes.byref(transferred), 0,
        ):
            raise _winerror("pipe_io_completion")
        if transferred.value == 0:
            raise OSError("pipe_zero_length_transfer")
        return int(transferred.value)
    finally:
        if not _event_has_pending_storage(event):
            api.kernel.CloseHandle(event)


def _write_all(api: _Win32Api, handle: int, data: bytes, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    buffer = ctypes.create_string_buffer(data, len(data))
    offset = 0
    while offset < len(data):
        if time.monotonic() >= deadline:
            raise TimeoutError("pipe_write_timeout")
        offset += _overlapped_transfer(
            api, handle, buffer, offset, len(data) - offset,
            writing=True, deadline=deadline,
        )


def _read_exact(api: _Win32Api, handle: int, length: int, timeout_ms: int) -> bytes:
    deadline = time.monotonic() + timeout_ms / 1000
    buffer = ctypes.create_string_buffer(length)
    offset = 0
    while offset < length:
        if time.monotonic() >= deadline:
            raise TimeoutError("pipe_read_timeout")
        offset += _overlapped_transfer(
            api, handle, buffer, offset, length - offset,
            writing=False, deadline=deadline,
        )
    return buffer.raw[:length]


def _get_token_information(api: _Win32Api, token: int, info_class: int) -> ctypes.Array:
    required = ctypes.c_uint32(0)
    api.advapi.GetTokenInformation(token, info_class, None, 0, ctypes.byref(required))
    if not required.value or required.value > 1024 * 1024:
        raise _winerror("token_information_size")
    buffer = ctypes.create_string_buffer(required.value)
    if not api.advapi.GetTokenInformation(
        token, info_class, buffer, required.value, ctypes.byref(required),
    ):
        raise _winerror("token_information")
    return buffer


def _token_user_sid(api: _Win32Api, token: int) -> tuple[ctypes.Array, int]:
    buffer = _get_token_information(api, token, _TOKEN_USER_CLASS)
    user = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_USER)).contents
    if not user.User.Sid:
        raise OSError("token_user_sid_missing")
    return buffer, user.User.Sid


def _token_group_entries(
    buffer: ctypes.Array,
) -> tuple[ctypes.Array, list[tuple[int, int]]]:
    header = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_GROUPS_HEADER)).contents
    group_count = int(header.GroupCount)
    alignment = ctypes.alignment(_TOKEN_GROUP)
    group_offset = (ctypes.sizeof(_TOKEN_GROUPS_HEADER) + alignment - 1) & ~(alignment - 1)
    group_size = ctypes.sizeof(_TOKEN_GROUP)
    if (
        not 1 <= group_count <= 4096
        or group_offset + group_count * group_size > len(buffer)
    ):
        raise OSError("token_groups_shape_invalid")
    groups = ctypes.cast(ctypes.byref(buffer, group_offset), ctypes.POINTER(_TOKEN_GROUP))
    entries = [(int(groups[index].Sid), int(groups[index].Attributes)) for index in range(group_count)]
    return buffer, entries


def select_logon_sid(entries: object) -> int:
    """Select the unique, non-null SID carrying SE_GROUP_LOGON_ID."""
    if not isinstance(entries, (list, tuple)):
        raise ValueError("invalid_token_groups")
    matches: list[int] = []
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError("invalid_token_group")
        sid, attributes = entry
        if (
            type(sid) is not int or sid <= 0
            or type(attributes) is not int or not 0 <= attributes <= 0xFFFFFFFF
        ):
            raise ValueError("invalid_token_group")
        if attributes & _SE_GROUP_LOGON_ID == _SE_GROUP_LOGON_ID:
            matches.append(sid)
    if len(matches) != 1:
        raise ValueError("token_logon_sid_not_unique")
    return matches[0]


def _token_session_id(api: _Win32Api, token: int) -> int:
    session = ctypes.c_uint32(0)
    returned = ctypes.c_uint32(0)
    if not api.advapi.GetTokenInformation(
        token, _TOKEN_SESSION_ID_CLASS, ctypes.byref(session),
        ctypes.sizeof(session), ctypes.byref(returned),
    ):
        raise _winerror("token_session_id")
    if returned.value != ctypes.sizeof(session):
        raise OSError("token_session_id_size_mismatch")
    return int(session.value)


def runner_process_logon_sid(process_handle: int) -> str:
    """Return the enabled logon SID from a launched runner's primary token."""
    if sys.platform != "win32":
        raise OSError("unsupported_platform")
    if not process_handle:
        raise ValueError("invalid_runner_process_handle")
    api = _load_win32_api()
    token = ctypes.c_void_p()
    if not api.advapi.OpenProcessToken(process_handle, _TOKEN_QUERY, ctypes.byref(token)):
        raise _winerror("open_runner_process_token")
    sid_pointer = ctypes.c_void_p()
    try:
        groups_buffer, groups = _token_group_entries(
            _get_token_information(api, token, _TOKEN_GROUPS_CLASS),
        )
        try:
            logon_sid = select_logon_sid(groups)
        except ValueError as exc:
            raise OSError("token_logon_sid_invalid") from exc
        return _sid_to_string(api, logon_sid, sid_pointer, "convert_runner_logon_sid")
    finally:
        if sid_pointer:
            api.kernel.LocalFree(sid_pointer)
        api.kernel.CloseHandle(token)


def runner_process_user_sid(process_handle: int) -> str:
    """Return the primary user SID of an already-open process handle."""
    if sys.platform != "win32":
        raise OSError("unsupported_platform")
    if not process_handle:
        raise ValueError("invalid_runner_process_handle")
    api = _load_win32_api()
    token = ctypes.c_void_p()
    if not api.advapi.OpenProcessToken(process_handle, _TOKEN_QUERY, ctypes.byref(token)):
        raise _winerror("open_runner_process_token")
    sid_pointer = ctypes.c_void_p()
    try:
        user_buffer, user_sid = _token_user_sid(api, token)
        _ = user_buffer
        return _sid_to_string(api, user_sid, sid_pointer, "convert_runner_user_sid")
    finally:
        if sid_pointer:
            api.kernel.LocalFree(sid_pointer)
        api.kernel.CloseHandle(token)


def _sid_to_string(api: _Win32Api, sid: int, output: ctypes.c_void_p, stage: str) -> str:
    convert = api.advapi.ConvertSidToStringSidW
    convert.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    convert.restype = ctypes.c_int32
    if not convert(sid, ctypes.byref(output)):
        raise _winerror(stage)
    return _validate_sid(ctypes.wstring_at(output))


class RunnerPipeClient:
    def __init__(self, *, name: str, handle: int, api: _Win32Api) -> None:
        self.name = name
        self._handle = handle
        self._api = api

    def send_message(self, message: dict[str, object], *, timeout_ms: int = 15_000) -> None:
        _validate_timeout(timeout_ms)
        frame = encode_frame(message)
        _write_all(self._api, self._handle, frame, timeout_ms)

    def receive_message(self, *, timeout_ms: int = 15_000) -> dict[str, object]:
        _validate_timeout(timeout_ms)
        header = _read_exact(self._api, self._handle, 4, timeout_ms)
        body_length = struct.unpack(">I", header)[0]
        if body_length == 0 or body_length > MAX_FRAME_BYTES:
            raise RunnerProtocolError("frame_too_large_or_empty")
        body = _read_exact(self._api, self._handle, body_length, timeout_ms)
        return decode_frame(header + body)

    def close(self) -> None:
        if self._handle:
            handle, self._handle = self._handle, 0
            if not self._api.kernel.CloseHandle(handle):
                raise _winerror("pipe_client_close")

    def __enter__(self) -> RunnerPipeClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            self.close()
        except OSError:
            if exc is None:
                raise


class RunnerPipeServer:
    def __init__(self, *, name: str, handle: int, api: _Win32Api) -> None:
        self.name = name
        self._handle = handle
        self._api = api
        self._connected = False

    def _connect(self, timeout_ms: int) -> None:
        _validate_timeout(timeout_ms)
        event = self._api.kernel.CreateEventW(None, 1, 0, None)
        if _handle_is_invalid(event):
            raise _winerror("pipe_connect_event")
        overlapped = _OVERLAPPED()
        overlapped.hEvent = event
        try:
            connected = self._api.kernel.ConnectNamedPipe(
                self._handle, ctypes.byref(overlapped),
            )
            if connected:
                self._connected = True
                return
            error = ctypes.get_last_error()
            if error == _ERROR_PIPE_CONNECTED:
                self._connected = True
                return
            if error != _ERROR_IO_PENDING:
                raise OSError(error, "pipe_connect")
            wait = self._api.kernel.WaitForSingleObject(event, timeout_ms)
            if wait == _WAIT_TIMEOUT:
                completed, _, completion_error, cancel_error, retained = _cancel_and_drain(
                    self._api, self._handle, overlapped, event, None,
                )
                if retained:
                    raise OSError(completion_error, "pipe_connect_cancel_unconfirmed")
                if completed:
                    self._connected = True
                    return
                if completion_error == _ERROR_OPERATION_ABORTED:
                    raise TimeoutError("runner_pipe_connect_timeout")
                if cancel_error not in (0, _ERROR_NOT_FOUND):
                    raise OSError(cancel_error, "pipe_cancel_connect")
                raise OSError(completion_error, "pipe_connect_completion")
            if wait != _WAIT_OBJECT_0:
                wait_error = ctypes.get_last_error() if wait == _WAIT_FAILED else wait
                _, _, _, _, retained = _cancel_and_drain(
                    self._api, self._handle, overlapped, event, None,
                )
                if retained:
                    raise OSError(wait_error, "pipe_connect_cancel_unconfirmed")
                raise OSError(wait_error, "pipe_connect_wait")
            transferred = ctypes.c_uint32(0)
            if not self._api.kernel.GetOverlappedResult(
                self._handle, ctypes.byref(overlapped), ctypes.byref(transferred), 0,
            ):
                raise _winerror("pipe_connect_completion")
            self._connected = True
        finally:
            if not _event_has_pending_storage(event):
                self._api.kernel.CloseHandle(event)

    def receive_message(self, *, timeout_ms: int = 15_000) -> dict[str, object]:
        if not self._connected:
            raise RuntimeError("runner_pipe_not_connected")
        _validate_timeout(timeout_ms)
        header = _read_exact(self._api, self._handle, 4, timeout_ms)
        body_length = struct.unpack(">I", header)[0]
        if body_length == 0 or body_length > MAX_FRAME_BYTES:
            raise RunnerProtocolError("frame_too_large_or_empty")
        body = _read_exact(self._api, self._handle, body_length, timeout_ms)
        return decode_frame(header + body)

    def wait_for_runner_ready(
        self,
        *,
        expected_process_handle: int,
        expected_user_sid: str,
        expected_logon_sid: str,
        request_id: str,
        timeout_ms: int = 15_000,
    ) -> None:
        _validate_sid(expected_user_sid)
        _validate_sid(expected_logon_sid)
        if type(request_id) is not str or _REQUEST_ID_RE.fullmatch(request_id) is None:
            raise ValueError("invalid_request_id")
        _validate_timeout(timeout_ms)
        self._connect(timeout_ms)
        message = self.receive_message(timeout_ms=timeout_ms)
        if message.get("type") != "spawn_ready":
            raise RunnerProtocolError("runner_ready_message_required")
        validate_correlation(message, request_id)
        _authenticate_client(
            self._api, self._handle, expected_process_handle,
            expected_user_sid, expected_logon_sid,
        )

    def close(self) -> None:
        if self._handle:
            handle, self._handle = self._handle, 0
            if not self._api.kernel.CloseHandle(handle):
                raise _winerror("pipe_server_close")

    def __enter__(self) -> RunnerPipeServer:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            self.close()
        except OSError:
            if exc is None:
                raise


def _authenticate_client(
    api: _Win32Api,
    pipe_handle: int,
    expected_process_handle: int,
    expected_user_sid: str,
    expected_logon_sid: str,
) -> None:
    if not expected_process_handle:
        raise ValueError("invalid_runner_process_handle")
    expected_sid_pointer = ctypes.c_void_p()
    if not api.advapi.ConvertStringSidToSidW(
        expected_user_sid, ctypes.byref(expected_sid_pointer),
    ):
        raise _winerror("convert_expected_user_sid")
    expected_logon_pointer = ctypes.c_void_p()
    if not api.advapi.ConvertStringSidToSidW(
        expected_logon_sid, ctypes.byref(expected_logon_pointer),
    ):
        api.kernel.LocalFree(expected_sid_pointer)
        raise _winerror("convert_expected_logon_sid")

    process_token = ctypes.c_void_p()
    client_token = ctypes.c_void_p()
    impersonating = False
    try:
        expected_pid = api.kernel.GetProcessId(expected_process_handle)
        if not expected_pid or api.kernel.WaitForSingleObject(expected_process_handle, 0) != _WAIT_TIMEOUT:
            raise PermissionError("runner_process_not_active")
        client_pid = ctypes.c_uint32(0)
        if not api.kernel.GetNamedPipeClientProcessId(pipe_handle, ctypes.byref(client_pid)):
            raise _winerror("pipe_client_pid")
        if client_pid.value != expected_pid:
            raise PermissionError("runner_pipe_client_pid_mismatch")
        pipe_session = ctypes.c_uint32(0)
        if not api.kernel.GetNamedPipeClientSessionId(pipe_handle, ctypes.byref(pipe_session)):
            raise _winerror("pipe_client_session")
        if not api.advapi.OpenProcessToken(
            expected_process_handle, _TOKEN_QUERY, ctypes.byref(process_token),
        ):
            raise _winerror("open_runner_process_token")
        process_user_buffer, process_user_sid = _token_user_sid(api, process_token)
        if not api.advapi.EqualSid(process_user_sid, expected_sid_pointer):
            raise PermissionError("runner_process_sid_mismatch")
        process_session = _token_session_id(api, process_token)

        if not api.advapi.ImpersonateNamedPipeClient(pipe_handle):
            raise _winerror("impersonate_pipe_client")
        impersonating = True
        if not api.advapi.OpenThreadToken(
            api.kernel.GetCurrentThread(), _TOKEN_QUERY, 1, ctypes.byref(client_token),
        ):
            raise _winerror("open_pipe_client_token")
        client_user_buffer, client_user_sid = _token_user_sid(api, client_token)
        if not api.advapi.EqualSid(client_user_sid, expected_sid_pointer):
            raise PermissionError("runner_pipe_client_sid_mismatch")
        client_session = _token_session_id(api, client_token)
        groups_buffer, groups = _token_group_entries(
            _get_token_information(api, client_token, _TOKEN_GROUPS_CLASS),
        )
        try:
            client_logon_sid = select_logon_sid(groups)
        except ValueError as exc:
            raise PermissionError("runner_pipe_logon_sid_invalid") from exc
        if not api.advapi.EqualSid(client_logon_sid, expected_logon_pointer):
            raise PermissionError("runner_pipe_logon_sid_mismatch")
        if process_session != client_session or pipe_session.value != client_session:
            raise PermissionError("runner_pipe_session_mismatch")
        if api.kernel.WaitForSingleObject(expected_process_handle, 0) != _WAIT_TIMEOUT:
            raise PermissionError("runner_process_exited_during_authentication")
        # Keep both buffers alive through every EqualSid call above.
        _ = process_user_buffer, client_user_buffer, groups_buffer
    finally:
        if impersonating and not api.advapi.RevertToSelf():
            if client_token:
                api.kernel.CloseHandle(client_token)
            if process_token:
                api.kernel.CloseHandle(process_token)
            api.kernel.LocalFree(expected_logon_pointer)
            api.kernel.LocalFree(expected_sid_pointer)
            raise _winerror("revert_pipe_client_impersonation")
        if client_token:
            api.kernel.CloseHandle(client_token)
        if process_token:
            api.kernel.CloseHandle(process_token)
        api.kernel.LocalFree(expected_logon_pointer)
        api.kernel.LocalFree(expected_sid_pointer)


def create_runner_pipe_server(
    runner_logon_sid: str, *, name: str | None = None,
) -> RunnerPipeServer:
    """Create a one-client local runner pipe with an explicit per-logon DACL."""
    sddl = build_runner_pipe_sddl(runner_logon_sid)
    pipe_name = new_runner_pipe_name() if name is None else validate_runner_pipe_name(name)
    api = _load_win32_api()
    security_descriptor = ctypes.c_void_p()
    if not api.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(security_descriptor), None,
    ):
        raise _winerror("pipe_security_descriptor")
    attributes = _SECURITY_ATTRIBUTES(
        ctypes.sizeof(_SECURITY_ATTRIBUTES), security_descriptor, 0,
    )
    try:
        handle = api.kernel.CreateNamedPipeW(
            pipe_name, RUNNER_PIPE_OPEN_MODE, RUNNER_PIPE_MODE,
            RUNNER_PIPE_MAX_INSTANCES, RUNNER_PIPE_BUFFER_BYTES,
            RUNNER_PIPE_BUFFER_BYTES, 0, ctypes.byref(attributes),
        )
    finally:
        api.kernel.LocalFree(security_descriptor)
    if _handle_is_invalid(handle):
        raise _winerror("create_runner_pipe")
    return RunnerPipeServer(name=pipe_name, handle=handle, api=api)


def open_runner_pipe_client(
    name: str,
    expected_server_pid: int,
    *,
    timeout_ms: int = 15_000,
) -> RunnerPipeClient:
    """Open a local runner pipe and reject a server other than the expected parent."""
    return _open_runner_pipe_client_impl(
        name, expected_server_pid, timeout_ms=timeout_ms,
    )


def _open_runner_pipe_client_with_observer(
    name: str,
    expected_server_pid: int,
    *,
    timeout_ms: int = 15_000,
    observer: Callable[[], None],
) -> RunnerPipeClient:
    """Open a pipe with an internal, read-only CI diagnostic observer.

    The observer runs after a pipe instance is available and immediately before
    each ``CreateFileW`` attempt. It must not mutate the current thread token;
    observer failures do not change connection behavior. This private entry
    point is reserved for the standard-user Windows probe.
    """
    return _open_runner_pipe_client_impl(
        name,
        expected_server_pid,
        timeout_ms=timeout_ms,
        before_create_file=observer,
    )


def _open_runner_pipe_client_impl(
    name: str,
    expected_server_pid: int,
    *,
    timeout_ms: int = 15_000,
    before_create_file: Callable[[], None] | None = None,
) -> RunnerPipeClient:
    """Shared client implementation; the observer is reserved for CI diagnostics."""
    pipe_name = validate_runner_pipe_name(name)
    timeout = _validate_timeout(timeout_ms)
    if type(expected_server_pid) is not int or not 1 <= expected_server_pid <= 0xFFFFFFFF:
        raise ValueError("invalid_expected_server_pid")
    api = _load_win32_api()
    deadline = time.monotonic() + timeout / 1000
    while True:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        available = api.kernel.WaitNamedPipeW(pipe_name, remaining_ms)
        if not available:
            error = ctypes.get_last_error()
            if error == _ERROR_SEM_TIMEOUT or time.monotonic() >= deadline:
                raise TimeoutError("runner_pipe_wait_timeout")
            if error in (_ERROR_FILE_NOT_FOUND, _ERROR_PIPE_BUSY):
                time.sleep(min(0.025, max(0.0, deadline - time.monotonic())))
                if time.monotonic() >= deadline:
                    raise TimeoutError("runner_pipe_wait_timeout")
                continue
            if error == _ERROR_ACCESS_DENIED:
                raise PermissionError(error, "runner_pipe_wait_access_denied")
            raise OSError(error, "runner_pipe_wait")
        if before_create_file is not None:
            try:
                before_create_file()
            except Exception:
                # Diagnostics must never suppress or replace the pipe open.
                pass
        handle = api.kernel.CreateFileW(
            pipe_name, PIPE_CLIENT_ACCESS_MASK, 0, None, _OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED | _SECURITY_SQOS_PRESENT | _SECURITY_IMPERSONATION,
            None,
        )
        if _handle_is_invalid(handle):
            error = ctypes.get_last_error()
            if error == _ERROR_PIPE_BUSY and time.monotonic() < deadline:
                continue
            if error == _ERROR_ACCESS_DENIED:
                raise PermissionError(error, "runner_pipe_open_access_denied")
            raise OSError(error, "runner_pipe_open")
        try:
            server_pid = ctypes.c_uint32(0)
            if not api.kernel.GetNamedPipeServerProcessId(handle, ctypes.byref(server_pid)):
                raise _winerror("runner_pipe_server_pid_query")
            if server_pid.value != expected_server_pid:
                raise PermissionError("runner_pipe_server_pid_mismatch")
            return RunnerPipeClient(name=pipe_name, handle=handle, api=api)
        except BaseException:
            api.kernel.CloseHandle(handle)
            raise
