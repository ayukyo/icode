"""R2.3 AppContainer 文件/网络边界实验；不是生产后端 ready 证明。"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import http.client
import http.server
import inspect
import json
import ntpath
import os
from pathlib import Path
import socket
import socketserver
import stat
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import unittest
import uuid
from collections.abc import Callable
from unittest import mock
from urllib.parse import urlsplit

import icode.windows_appcontainer as windows_appcontainer
import icode.windows_job as windows_job_module
from icode.windows_appcontainer import (
    _AppContainerSetupError,
    _delete_appcontainer_profile,
    _get_appcontainer_localappdata_path,
)
from icode.windows_appcontainer import _walk_workspace, run_windows_appcontainer
from icode.windows_job import (
    _append_windows_environment_value,
    _build_windows_environment_block,
    WindowsJobResult,
    run_windows_job,
)

_WINDOWS_WSAEWOULDBLOCK = 10035
_WINDOWS_WSAETIMEDOUT = 10060


def _network_attempt_timed_out(
    attempted: object, connected: object, error_code: object,
    terminal_error: object,
) -> bool:
    """Classify only a timeout returned by the connect operation or SO_ERROR."""
    return (
        attempted is True
        and connected is False
        and terminal_error is True
        and type(error_code) is int
        and error_code == _WINDOWS_WSAETIMEDOUT
    )


def _query_administrators_group_membership_status(
    token: ctypes.c_void_p, admin_sid: ctypes.c_void_p, advapi: object, kernel: object,
) -> str:
    """Check Administrators membership using the impersonation-token API contract."""
    security_impersonation = 2
    impersonation_token = ctypes.c_void_p()
    advapi.DuplicateToken.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.DuplicateToken.restype = ctypes.c_int
    advapi.CheckTokenMembership.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
    ]
    advapi.CheckTokenMembership.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    if not advapi.DuplicateToken(
        token, security_impersonation, ctypes.byref(impersonation_token),
    ):
        return "administrators_token_duplicate_failed"
    try:
        admin_enabled = ctypes.c_int()
        if not advapi.CheckTokenMembership(
            impersonation_token, admin_sid, ctypes.byref(admin_enabled),
        ):
            return "administrators_membership_query_failed"
        return "member" if admin_enabled.value != 0 else "not_member"
    finally:
        if impersonation_token.value:
            kernel.CloseHandle(impersonation_token)


def _current_process_standard_user_status(expected_sid: str) -> str:
    """Return a fixed, non-sensitive reason if the host token is not expected."""
    if sys.platform != "win32":
        return "unsupported_platform"
    if not expected_sid.startswith("S-"):
        return "expected_sid_missing"

    class _SidAndAttributes(ctypes.Structure):
        _fields_ = [("sid", ctypes.c_void_p), ("attributes", ctypes.c_uint32)]

    class _TokenUser(ctypes.Structure):
        _fields_ = [("user", _SidAndAttributes)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    token_query_access = 0x0008
    token_duplicate_access = 0x0002
    advapi.OpenProcessToken.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.OpenProcessToken.restype = ctypes.c_int
    advapi.GetTokenInformation.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
    ]
    advapi.GetTokenInformation.restype = ctypes.c_int
    advapi.ConvertStringSidToSidW.argtypes = [
        ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.ConvertStringSidToSidW.restype = ctypes.c_int
    advapi.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.ConvertSidToStringSidW.restype = ctypes.c_int

    token = ctypes.c_void_p()
    actual_sid_string = ctypes.c_void_p()
    admin_sid = ctypes.c_void_p()
    try:
        if not advapi.OpenProcessToken(
            kernel.GetCurrentProcess(),
            token_query_access | token_duplicate_access,
            ctypes.byref(token),
        ):
            return "process_token_open_failed"
        required = ctypes.c_uint32()
        ctypes.set_last_error(0)
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        if ctypes.get_last_error() != 122 or required.value < ctypes.sizeof(_TokenUser):
            return "token_user_size_query_failed"
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi.GetTokenInformation(
            token, 1, buffer, required.value, ctypes.byref(required),
        ):
            return "token_user_query_failed"
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents
        if not token_user.user.sid or not advapi.ConvertSidToStringSidW(
            token_user.user.sid, ctypes.byref(actual_sid_string),
        ):
            return "token_user_sid_conversion_failed"
        actual_sid = ctypes.wstring_at(actual_sid_string.value)
        if actual_sid.casefold() != expected_sid.casefold():
            return "token_user_sid_mismatch"

        elevated = ctypes.c_uint32()
        if not advapi.GetTokenInformation(
            token, 20, ctypes.byref(elevated), ctypes.sizeof(elevated),
            ctypes.byref(required),
        ):
            return "token_elevation_query_failed"
        if elevated.value != 0:
            return "token_is_elevated"
        if not advapi.ConvertStringSidToSidW(
            "S-1-5-32-544", ctypes.byref(admin_sid),
        ):
            return "administrators_sid_conversion_failed"
        membership_status = _query_administrators_group_membership_status(
            token, admin_sid, advapi, kernel,
        )
        if membership_status == "administrators_token_duplicate_failed":
            return membership_status
        if membership_status == "administrators_membership_query_failed":
            return "administrators_membership_query_failed"
        if membership_status == "member":
            return "administrators_group_enabled"
        if membership_status != "not_member":
            return "administrators_membership_check_invalid_result"
        return "verified"
    except (OSError, ValueError, TypeError, ctypes.ArgumentError):
        return "token_api_error"
    finally:
        for pointer in (actual_sid_string, admin_sid):
            if pointer.value:
                kernel.LocalFree(pointer)
        if token.value:
            kernel.CloseHandle(token)


def _dacl_write_control_succeeds(path: Path) -> bool:
    """Prove this exact WRITE_DAC handle and SetSecurityInfo path can succeed."""
    if sys.platform != "win32":
        return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    ]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.GetSecurityInfo.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetSecurityInfo.restype = ctypes.c_uint32
    advapi.SetSecurityInfo.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
    ]
    advapi.SetSecurityInfo.restype = ctypes.c_uint32

    handle = kernel.CreateFileW(str(path), 0x00060000, 0x7, None, 3, 0x80, None)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        return False
    descriptor = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    try:
        status = advapi.GetSecurityInfo(
            handle, 1, 4, None, None, ctypes.byref(dacl), None,
            ctypes.byref(descriptor),
        )
        if status != 0 or not dacl.value:
            return False
        changed = advapi.SetSecurityInfo(
            handle, 1, 4, None, None, dacl, None,
        ) == 0
        closed = bool(kernel.CloseHandle(handle))
        handle = None
        return changed and closed
    finally:
        if descriptor.value:
            kernel.LocalFree(descriptor)
        if handle:
            kernel.CloseHandle(handle)

_RUNTIME_PROBE_FAILURE_STAGES = frozenset({
    "imports", "executable_absolute", "module_path", "prefix_absolute",
    "runtime_path", "runtime_write", "source_read", "environment", "network",
    "workspace_write", "child_launch",
})
_RUNTIME_PROBE_ERROR_TYPES = frozenset({
    "AttributeError", "ConnectionAbortedError", "ConnectionRefusedError",
    "ConnectionResetError", "FileExistsError", "FileNotFoundError",
    "ImportError", "IsADirectoryError", "ModuleNotFoundError", "NameError",
    "NotADirectoryError", "OSError", "PermissionError", "RuntimeError",
    "TimeoutError", "TimeoutExpired", "TypeError", "ValueError",
})
# Microsoft Winsock errors that indicate the attempted connection did not
# complete. They do not identify whether WFP, policy, routing, or another cause
# prevented it; the host-side positive control only validates the listener.
_APP_CONTAINER_CONNECT_FAILURE_WINERRORS = (
    10013, 10050, 10051, 10053, 10054, 10060, 10061, 10065,
)
_PATH_RESOLUTION_NOTICE_LABELS = (
    ("absolute", "abs"),
    ("stat", "stat"),
    ("read", "read"),
    ("resolve_strict", "strict"),
    ("resolve_nonstrict", "nonstrict"),
    ("getfinalpathname", "pyfinal"),
    ("native_createfile_zero", "createfile"),
    ("getfinal_nt", "nt"),
    ("getfinal_dos", "dos"),
)


def _classify_runtime_probe_failure(raw_failure: str) -> str:
    """Keep a known stage and safe class name; never forward exception text/paths."""
    if not raw_failure:
        return "not_observed"
    stage, separator, error_type = raw_failure.partition(":")
    if (
        stage not in _RUNTIME_PROBE_FAILURE_STAGES
        or not separator
        or not error_type.isascii()
        or not error_type.isidentifier()
    ):
        return "invalid_marker"
    if error_type in _RUNTIME_PROBE_ERROR_TYPES:
        return f"{stage}:{error_type}"
    return f"{stage}:other"


_STAGED_PYTHON_ENVIRONMENT_PROBE = """\
def _win32_environment_value(name):
    getter = ctypes.WinDLL('kernel32', use_last_error=True).GetEnvironmentVariableW
    getter.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_wchar), ctypes.c_uint32]
    getter.restype = ctypes.c_uint32
    ctypes.set_last_error(0)
    required = getter(name, None, 0)
    if required == 0:
        error = ctypes.get_last_error()
        if error == 203:
            return None
        if error == 0:
            return ''
        raise ctypes.WinError(error)
    buffer = ctypes.create_unicode_buffer(required)
    ctypes.set_last_error(0)
    copied = getter(name, buffer, required)
    if copied == 0:
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
    return buffer.value

def _environment_path_state(value):
    if value is None:
        return 'not_defined'
    try:
        metadata = os.stat(value)
    except PermissionError:
        return 'access_denied'
    except FileNotFoundError:
        return 'not_found'
    except OSError as exc:
        error = getattr(exc, 'winerror', None)
        if error == 3:
            return 'path_not_found'
        if error == 2:
            return 'not_found'
        if error == 5:
            return 'access_denied'
        return 'other_error'
    return 'directory' if stat.S_ISDIR(metadata.st_mode) else 'not_directory'

try:
    staged_environment = {}
    for _name in ('LOCALAPPDATA', 'TEMP', 'TMP'):
        _python_value = os.environ.get(_name)
        _win32_value = _win32_environment_value(_name)
        staged_environment[_name] = {
            'python_value': _python_value,
            'win32_value': _win32_value,
            'path_state': _environment_path_state(_python_value),
        }
except Exception as exc:
    Path('staging-python-failure-class').write_text(
        'environment:' + type(exc).__name__, encoding='ascii')
    raise
"""

_STAGED_PYTHON_PROFILE_API_PROBE = """\
def _localappdata_from_process_environment_block():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    getter = kernel.GetEnvironmentStringsW
    getter.argtypes = []
    getter.restype = ctypes.c_void_p
    freer = kernel.FreeEnvironmentStringsW
    freer.argtypes = [ctypes.c_void_p]
    freer.restype = ctypes.c_int
    block = getter()
    if not block:
        raise ctypes.WinError(ctypes.get_last_error())
    values = []
    try:
        base = int(block)
        offset = 0
        for _ in range(8192):
            entry = ctypes.wstring_at(base + offset)
            if not entry:
                return values
            separator = entry.find('=', 1) if entry.startswith('=') else entry.find('=')
            if separator >= 0 and entry[:separator].casefold() == 'localappdata':
                values.append(entry[separator + 1:])
            offset += (len(entry) + 1) * ctypes.sizeof(ctypes.c_wchar)
        raise RuntimeError('environment block exceeded diagnostic bound')
    finally:
        if not freer(block):
            raise ctypes.WinError(ctypes.get_last_error())

def _current_appcontainer_localappdata(observation):
    import ctypes.wintypes as wintypes
    class _AppContainerTokenInfo(ctypes.Structure):
        _fields_ = [('sid', ctypes.c_void_p)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    userenv = ctypes.WinDLL('userenv', use_last_error=True)
    ole32 = ctypes.WinDLL('ole32', use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    advapi.OpenProcessToken.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(ctypes.c_void_p)]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_void_p, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                              ctypes.POINTER(ctypes.c_void_p)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    userenv.GetAppContainerFolderPath.argtypes = [wintypes.LPCWSTR,
                                                   ctypes.POINTER(ctypes.c_void_p)]
    userenv.GetAppContainerFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

    token = ctypes.c_void_p()
    sid_string = ctypes.c_void_p()
    profile_path = ctypes.c_void_p()
    token_is_appcontainer = wintypes.DWORD()
    returned = wintypes.DWORD()
    opened = False
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008,
                                      ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        opened = True
        if not advapi.GetTokenInformation(token, 29, ctypes.byref(token_is_appcontainer),
                                           ctypes.sizeof(token_is_appcontainer),
                                           ctypes.byref(returned)):
            raise ctypes.WinError(ctypes.get_last_error())
        if token_is_appcontainer.value != 1:
            raise RuntimeError('current token is not an AppContainer')
        observation['token_is_appcontainer'] = True

        required = wintypes.DWORD()
        ctypes.set_last_error(0)
        advapi.GetTokenInformation(token, 31, None, 0, ctypes.byref(required))
        if ctypes.get_last_error() != 122 or required.value < ctypes.sizeof(_AppContainerTokenInfo):
            raise ctypes.WinError(ctypes.get_last_error() or 87)
        sid_storage = ctypes.create_string_buffer(required.value)
        if not advapi.GetTokenInformation(token, 31, sid_storage, required.value,
                                           ctypes.byref(returned)):
            raise ctypes.WinError(ctypes.get_last_error())
        token_info = ctypes.cast(sid_storage,
                                 ctypes.POINTER(_AppContainerTokenInfo)).contents
        if not token_info.sid:
            raise RuntimeError('AppContainer SID is missing')
        observation['token_sid_defined'] = True
        if not advapi.ConvertSidToStringSidW(token_info.sid, ctypes.byref(sid_string)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid_text = ctypes.wstring_at(sid_string)
        hr = int(userenv.GetAppContainerFolderPath(sid_text,
                                                   ctypes.byref(profile_path)))
        if hr != 0 or not profile_path.value:
            observation['profile_error_code'] = hr & 0xffff
            raise OSError(hr & 0xffff, 'GetAppContainerFolderPath failed')
        observation['profile_path'] = ctypes.wstring_at(profile_path)
    finally:
        cleanup_error = 0
        if profile_path.value:
            try:
                ole32.CoTaskMemFree(profile_path)
            except Exception:
                cleanup_error = 6
        if sid_string.value:
            if kernel.LocalFree(sid_string):
                cleanup_error = ctypes.get_last_error() or 6
        if opened:
            if not kernel.CloseHandle(token):
                cleanup_error = ctypes.get_last_error() or 6
        if cleanup_error:
            raise ctypes.WinError(cleanup_error)

_staged_profile_api = {
    'token_is_appcontainer': False,
    'token_sid_defined': False,
    'profile_path': None,
    'profile_error': None,
    'profile_error_code': None,
    'profile_path_state': 'not_defined',
    'environment_block_scan_complete': False,
    'environment_block_error': None,
    'environment_block_localappdata': [],
    'python_localappdata': staged_environment['LOCALAPPDATA']['python_value'],
    'win32_localappdata': staged_environment['LOCALAPPDATA']['win32_value'],
}
try:
    _staged_profile_api['environment_block_localappdata'] = \\
        _localappdata_from_process_environment_block()
    _staged_profile_api['environment_block_scan_complete'] = True
except Exception as exc:
    _staged_profile_api['environment_block_error'] = type(exc).__name__
try:
    _current_appcontainer_localappdata(_staged_profile_api)
    _staged_profile_api['profile_path_state'] = _environment_path_state(
        _staged_profile_api['profile_path'])
except Exception as exc:
    _staged_profile_api['profile_error'] = type(exc).__name__
    if _staged_profile_api['profile_error_code'] is None:
        _staged_profile_api['profile_error_code'] = getattr(exc, 'winerror', None)
"""

_STAGED_PYTHON_KNOWN_FOLDER_PROBE = """\
import uuid

_staged_profile_context = {
    'known_folder_path': None,
    'known_folder_error': None,
    'known_folder_error_code': None,
    'known_folder_path_state': 'not_defined',
    'package_identity': 'other_error',
    'package_identity_error_code': None,
}
try:
    import ctypes.wintypes as wintypes
    class _KnownFolderId(ctypes.Structure):
        _fields_ = [('data1', wintypes.DWORD), ('data2', wintypes.WORD),
                    ('data3', wintypes.WORD), ('data4', wintypes.BYTE * 8)]
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    ole32 = ctypes.WinDLL('ole32', use_last_error=True)
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_KnownFolderId), wintypes.DWORD, wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    _known_folder_id = _KnownFolderId.from_buffer_copy(
        uuid.UUID('F1B32785-6FBA-4FCF-9D55-7B8E7F157091').bytes_le)
    _known_folder_path = ctypes.c_void_p()
    try:
        _known_folder_hr = int(shell32.SHGetKnownFolderPath(
            ctypes.byref(_known_folder_id), 0x00004000, None,
            ctypes.byref(_known_folder_path)))
        if _known_folder_hr != 0 or not _known_folder_path.value:
            _staged_profile_context['known_folder_error_code'] = _known_folder_hr & 0xffff
            raise OSError(_known_folder_hr & 0xffff, 'SHGetKnownFolderPath failed')
        _staged_profile_context['known_folder_path'] = ctypes.wstring_at(
            _known_folder_path)
        _staged_profile_context['known_folder_path_state'] = _environment_path_state(
            _staged_profile_context['known_folder_path'])
    except Exception as exc:
        _staged_profile_context['known_folder_error'] = type(exc).__name__
        if _staged_profile_context['known_folder_error_code'] is None:
            _staged_profile_context['known_folder_error_code'] = getattr(exc, 'winerror', None)
    finally:
        if _known_folder_path.value:
            try:
                ole32.CoTaskMemFree(_known_folder_path)
            except Exception:
                _staged_profile_context['known_folder_error'] = 'cleanup_failed'
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentPackageFullName.argtypes = [
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR,
    ]
    kernel32.GetCurrentPackageFullName.restype = ctypes.c_long
    package_length = wintypes.DWORD(0)
    package_result = int(kernel32.GetCurrentPackageFullName(
        ctypes.byref(package_length), None))
    if package_result == 122 and package_length.value:
        package_name = ctypes.create_unicode_buffer(package_length.value)
        package_result = int(kernel32.GetCurrentPackageFullName(
            ctypes.byref(package_length), package_name))
    if package_result == 0:
        _staged_profile_context['package_identity'] = 'present'
    elif package_result == 15700:
        _staged_profile_context['package_identity'] = 'no_package'
        _staged_profile_context['package_identity_error_code'] = package_result
    else:
        _staged_profile_context['package_identity'] = 'other_error'
        _staged_profile_context['package_identity_error_code'] = package_result
except Exception as exc:
    if _staged_profile_context['known_folder_error'] is None:
        _staged_profile_context['known_folder_error'] = type(exc).__name__
    if _staged_profile_context['package_identity_error_code'] is None:
        _staged_profile_context['package_identity_error_code'] = getattr(exc, 'winerror', None)
"""

_STAGED_PYTHON_RUNTIME_IMAGE_PROBE = """\
_runtime_image_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_runtime_image_kernel32.CreateFileW.argtypes = [
    ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
]
_runtime_image_kernel32.CreateFileW.restype = ctypes.c_void_p
_runtime_image_kernel32.ReadFile.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p,
]
_runtime_image_kernel32.ReadFile.restype = ctypes.c_int
_runtime_image_kernel32.CreateFileMappingW.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
    ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p,
]
_runtime_image_kernel32.CreateFileMappingW.restype = ctypes.c_void_p
_runtime_image_kernel32.MapViewOfFile.argtypes = [
    ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
    ctypes.c_uint32, ctypes.c_size_t,
]
_runtime_image_kernel32.MapViewOfFile.restype = ctypes.c_void_p
_runtime_image_kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
_runtime_image_kernel32.UnmapViewOfFile.restype = ctypes.c_int
_runtime_image_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_runtime_image_kernel32.CloseHandle.restype = ctypes.c_int
_RUNTIME_GENERIC_READ = 0x80000000
_RUNTIME_SHARE_READ_WRITE_DELETE = 0x00000007
_RUNTIME_OPEN_EXISTING = 3
_RUNTIME_FILE_ATTRIBUTE_NORMAL = 0x00000080
_RUNTIME_PAGE_READONLY_SEC_IMAGE_NO_EXECUTE = 0x11000002
_RUNTIME_FILE_MAP_READ = 0x00000004

def _runtime_image_probe(path):
    result = {
        'opened': False,
        'read_ok': False,
        'section_created': False,
        'view_mapped': False,
        'cleanup_ok': True,
        'open_error': None,
        'read_error': None,
        'section_error': None,
        'view_error': None,
    }
    invalid_handle = ctypes.c_void_p(-1).value
    file_handle = None
    mapping_handle = None
    mapped_view = None
    try:
        file_handle = _runtime_image_kernel32.CreateFileW(
            path, _RUNTIME_GENERIC_READ, _RUNTIME_SHARE_READ_WRITE_DELETE,
            None, _RUNTIME_OPEN_EXISTING, _RUNTIME_FILE_ATTRIBUTE_NORMAL, None)
        if file_handle is None or file_handle == invalid_handle:
            result['open_error'] = ctypes.get_last_error()
        else:
            result['opened'] = True
            read_buffer = ctypes.create_string_buffer(1)
            bytes_read = ctypes.c_uint32()
            if _runtime_image_kernel32.ReadFile(
                file_handle, read_buffer, 1, ctypes.byref(bytes_read), None):
                if bytes_read.value == 1:
                    result['read_ok'] = True
                else:
                    result['read_error'] = 0
            else:
                result['read_error'] = ctypes.get_last_error()
            mapping_handle = _runtime_image_kernel32.CreateFileMappingW(
                file_handle, None, _RUNTIME_PAGE_READONLY_SEC_IMAGE_NO_EXECUTE,
                0, 0, None)
            if mapping_handle is None:
                result['section_error'] = ctypes.get_last_error()
            else:
                result['section_created'] = True
                mapped_view = _runtime_image_kernel32.MapViewOfFile(
                    mapping_handle, _RUNTIME_FILE_MAP_READ, 0, 0, 0)
                if mapped_view is None:
                    result['view_error'] = ctypes.get_last_error()
                else:
                    result['view_mapped'] = True
    except Exception:
        if not result['opened']:
            result['open_error'] = 0
        elif not result['read_ok'] and result['read_error'] is None:
            result['read_error'] = 0
        elif not result['section_created']:
            result['section_error'] = 0
        else:
            result['view_error'] = 0
    finally:
        if mapped_view is not None:
            try:
                if not _runtime_image_kernel32.UnmapViewOfFile(mapped_view):
                    result['cleanup_ok'] = False
            except Exception:
                result['cleanup_ok'] = False
        if mapping_handle is not None:
            try:
                if not _runtime_image_kernel32.CloseHandle(mapping_handle):
                    result['cleanup_ok'] = False
            except Exception:
                result['cleanup_ok'] = False
        if file_handle is not None and file_handle != invalid_handle:
            try:
                if not _runtime_image_kernel32.CloseHandle(file_handle):
                    result['cleanup_ok'] = False
            except Exception:
                result['cleanup_ok'] = False
    return result
"""

_STAGED_PYTHON_TEMPFILE_PROBE = """\
staged_tempfile = {
    'tempdir': None,
    'cwd': os.getcwd(),
    'created': False,
    'deleted': False,
    'error_type': None,
}
_tempfile_probe_path = None
try:
    staged_tempfile['tempdir'] = tempfile.gettempdir()
    with tempfile.NamedTemporaryFile(prefix='icode-temp-probe-', delete=True) as _probe:
        _tempfile_probe_path = _probe.name
        _probe.write(b'ICODE')
        _probe.flush()
        staged_tempfile['created'] = True
    staged_tempfile['deleted'] = not os.path.exists(_tempfile_probe_path)
except Exception as exc:
    staged_tempfile['error_type'] = type(exc).__name__
    if _tempfile_probe_path is not None:
        try:
            os.unlink(_tempfile_probe_path)
        except OSError:
            pass
"""


def _is_observed_appcontainer_connect_failure(error: OSError) -> bool:
    """Classify a failed connect attempt without attributing its cause."""
    return (
        isinstance(error, (PermissionError, TimeoutError))
        or getattr(error, "winerror", None) in _APP_CONTAINER_CONNECT_FAILURE_WINERRORS
    )


def _compact_path_resolution_probe_notice(
    probe: dict[str, dict[str, object]], *, complete: bool,
) -> dict[str, object]:
    """Keep the public Actions notice below its 500-character transport limit."""
    operations: dict[str, list[object]] = {}
    for operation, label in _PATH_RESOLUTION_NOTICE_LABELS:
        outcome = probe.get(operation)
        if not isinstance(outcome, dict):
            continue
        error = outcome.get("error")
        operations[label] = [
            outcome.get("ok") is True,
            error if error in _RUNTIME_PROBE_ERROR_TYPES | {"none"} else "other",
            outcome.get("winerror") if isinstance(outcome.get("winerror"), int) else None,
        ]
    # Tuple fields are [ok, safe error class, WinError]; operation aliases are
    # fixed above so even nine verbose Windows errors fit one Actions notice.
    return {"complete": complete, "operations": operations}


class TestWindowsAppContainer(unittest.TestCase):
    def test_reviewer_snapshot_root_requires_named_temp_directory_outside_scratch(self) -> None:
        validator = getattr(
            windows_appcontainer,
            "_validate_diagnostic_reviewer_snapshot_roots",
            None,
        )
        self.assertTrue(
            callable(validator),
            "reviewer snapshot diagnostic root validator is missing",
        )
        with tempfile.TemporaryDirectory(prefix="icode-reviewer-snapshot-validation-") as raw:
            base = Path(raw)
            scratch = base / "scratch"
            snapshot = base / "icode-reviewer-snapshot-validation"
            scratch.mkdir()
            snapshot.mkdir()
            (snapshot / "allowed.py").write_text("value = 1\n", encoding="utf-8")

            self.assertEqual(
                validator((snapshot,), workspace=scratch),
                (snapshot.resolve(),),
            )
            with self.assertRaises(_AppContainerSetupError) as overlap:
                validator((scratch,), workspace=scratch)
            self.assertEqual(overlap.exception.error, "unsupported_runtime_root")

            not_named = base / "snapshot"
            not_named.mkdir()
            with self.assertRaises(_AppContainerSetupError) as bad_name:
                validator((not_named,), workspace=scratch)
            self.assertEqual(bad_name.exception.error, "invalid_diagnostic_probe")

            with self.assertRaises(_AppContainerSetupError) as bad_shape:
                validator(str(snapshot), workspace=scratch)
            self.assertEqual(bad_shape.exception.error, "invalid_diagnostic_probe")

            runner_temp = base / "runner-temp"
            runner_temp.mkdir()
            outside_temp = base / "outside-temp" / "icode-reviewer-snapshot-outside"
            outside_temp.mkdir(parents=True)
            with mock.patch(
                "icode.windows_appcontainer.tempfile.gettempdir",
                return_value=str(runner_temp),
            ), self.assertRaises(_AppContainerSetupError) as outside:
                validator((outside_temp,), workspace=scratch)
            self.assertEqual(outside.exception.error, "invalid_diagnostic_probe")

    def test_reviewer_snapshot_appcontainer_probe_requires_explicit_ci_optin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-reviewer-snapshot-gate-") as raw:
            root = Path(raw)
            scratch = root / "scratch"
            runtime = root / "icode-runtime-staging-gate"
            snapshot = root / "icode-reviewer-snapshot-gate"
            scratch.mkdir()
            runtime.mkdir()
            snapshot.mkdir()
            probe = runtime / "python.exe"
            probe.write_bytes(b"test-only placeholder")
            with mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
                 mock.patch.dict(
                     os.environ,
                     {
                         "GITHUB_ACTIONS": "true",
                         "RUNNER_OS": "Windows",
                         "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
                     },
                     clear=True,
                 ), mock.patch("ctypes.WinDLL", create=True) as load_api:
                result = run_windows_appcontainer(
                    [str(probe), "-I", "-c", "pass"],
                    cwd=scratch,
                    timeout_seconds=2,
                    _diagnostic_runtime_acl=True,
                    _diagnostic_runtime_roots=(runtime,),
                    _diagnostic_reviewer_snapshot_roots=(snapshot,),
                )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        self.assertFalse(result.cleanup_ok)
        load_api.assert_not_called()

    def test_reviewer_snapshot_probe拒绝与runtime重叠且不改ACL(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-reviewer-snapshot-overlap-") as raw:
            root = Path(raw)
            scratch = root / "scratch"
            runtime = root / "icode-runtime-staging-overlap"
            snapshot = runtime / "icode-reviewer-snapshot-overlap"
            scratch.mkdir()
            snapshot.mkdir(parents=True)
            probe = runtime / "python.exe"
            probe.write_bytes(b"test-only placeholder")
            with mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
                 mock.patch.dict(
                     os.environ,
                     {
                         "GITHUB_ACTIONS": "true",
                         "RUNNER_OS": "Windows",
                         "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
                         "ICODE_DIAGNOSTIC_REVIEWER_SNAPSHOT": "true",
                     },
                     clear=True,
                 ), mock.patch("ctypes.WinDLL", create=True) as load_api:
                result = run_windows_appcontainer(
                    [str(probe), "-I", "-c", "pass"],
                    cwd=scratch,
                    timeout_seconds=2,
                    _diagnostic_runtime_acl=True,
                    _diagnostic_runtime_roots=(runtime,),
                    _diagnostic_reviewer_snapshot_roots=(snapshot,),
                )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "unsupported_runtime_root")
        self.assertFalse(result.cleanup_ok)
        load_api.assert_not_called()

    def test_diagnostic_profile_name_accepts_only_generated_shape(self) -> None:
        validator = getattr(
            windows_appcontainer, "_is_diagnostic_profile_name", None,
        )
        self.assertTrue(callable(validator), "diagnostic profile-name validator is missing")
        self.assertTrue(validator("icode-0123456789abcdef0123456789abcdef"))
        for invalid in (
            None,
            "other-0123456789abcdef0123456789abcdef",
            "icode-0123456789abcdef0123456789abcdeg",
            "icode-0123456789abcdef0123456789abcde",
            "icode-0123456789ABCDEF0123456789ABCDEF",
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(validator(invalid))

    def test_只读句柄POC缺少显式optin时默认拒绝(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-read-handle-gate-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {"GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows"},
                 clear=True,
             ), mock.patch("ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [sys.executable], cwd=raw, timeout_seconds=2,
                _diagnostic_read_handle=123,
                _diagnostic_profile_name="icode-0123456789abcdef0123456789abcdef",
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        self.assertFalse(result.cleanup_ok)
        load_api.assert_not_called()

    def test_诊断profile名称不能脱离只读句柄探针单独指定(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-profile-name-gate-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [sys.executable], cwd=raw, timeout_seconds=2,
                _diagnostic_profile_name="icode-0123456789abcdef0123456789abcdef",
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_只读句柄POC即使有optin也拒绝非GitHubWindowsrunner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-read-handle-runner-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {"ICODE_DIAGNOSTIC_READ_HANDLE": "true"},
                 clear=True,
             ), mock.patch("ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [sys.executable], cwd=raw, timeout_seconds=2,
                _diagnostic_read_handle=123,
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_只读句柄POC拒绝工作区外的同名可执行文件(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-read-handle-path-") as raw:
            root = Path(raw)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            probe = external / "icode-appcontainer-read-probe.exe"
            probe.write_bytes(b"test-only placeholder")
            with mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
                 mock.patch.dict(
                     os.environ,
                     {
                         "GITHUB_ACTIONS": "true",
                         "RUNNER_OS": "Windows",
                         "ICODE_DIAGNOSTIC_READ_HANDLE": "true",
                     },
                     clear=True,
                 ), mock.patch("ctypes.WinDLL", create=True) as load_api:
                result = run_windows_appcontainer(
                    [str(probe), "--input-handle", windows_job_module._READ_HANDLE_PLACEHOLDER],
                    cwd=workspace, timeout_seconds=2, _diagnostic_read_handle=123,
                )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_只读句柄POC固定可执行文件在工作区内才进入原生设置(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-read-handle-allow-") as raw:
            workspace = Path(raw)
            probe = workspace / "icode-appcontainer-read-probe.exe"
            probe.write_bytes(b"test-only placeholder")
            with mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
                 mock.patch.dict(
                     os.environ,
                     {
                         "GITHUB_ACTIONS": "true",
                         "RUNNER_OS": "Windows",
                         "ICODE_DIAGNOSTIC_READ_HANDLE": "true",
                     },
                     clear=True,
                 ), mock.patch(
                     "ctypes.WinDLL", side_effect=OSError(5, "expected test stop"), create=True,
                 ) as load_api:
                result = run_windows_appcontainer(
                    [str(probe), "--input-handle", windows_job_module._READ_HANDLE_PLACEHOLDER],
                    cwd=workspace, timeout_seconds=2, _diagnostic_read_handle=123,
                )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "appcontainer_api_unavailable")
        load_api.assert_called_once_with("userenv", use_last_error=True)

    def test_failure_marker分类保留安全阶段但不输出任意异常内容(self) -> None:
        self.assertEqual(_classify_runtime_probe_failure(""), "not_observed")
        self.assertEqual(
            _classify_runtime_probe_failure("network:ConnectionRefusedError"),
            "network:ConnectionRefusedError",
        )
        self.assertEqual(
            _classify_runtime_probe_failure("workspace_write:UnknownSystemError"),
            "workspace_write:other",
        )
        self.assertEqual(
            _classify_runtime_probe_failure("network:C:\\private\\secret"),
            "invalid_marker",
        )
        self.assertEqual(
            _classify_runtime_probe_failure("unknown:/private/secret"),
            "invalid_marker",
        )
        self.assertTrue(_is_observed_appcontainer_connect_failure(PermissionError()))
        self.assertTrue(_is_observed_appcontainer_connect_failure(TimeoutError()))
        refused = ConnectionRefusedError()
        refused.winerror = 10061
        self.assertTrue(_is_observed_appcontainer_connect_failure(refused))
        reset = ConnectionResetError()
        reset.winerror = 10054
        self.assertTrue(_is_observed_appcontainer_connect_failure(reset))
        unexpected = OSError()
        unexpected.winerror = 10014
        self.assertFalse(_is_observed_appcontainer_connect_failure(unexpected))
        self.assertFalse(_is_observed_appcontainer_connect_failure(OSError()))

    def test_path_resolution诊断回执在Actions长度上限内(self) -> None:
        probe = {
            operation: {"ok": False, "error": "ConnectionAbortedError", "winerror": 10053}
            for operation, _label in _PATH_RESOLUTION_NOTICE_LABELS
        }
        notice = _compact_path_resolution_probe_notice(probe, complete=True)
        encoded = json.dumps(notice, ensure_ascii=True, separators=(",", ":"))
        self.assertLessEqual(len(encoded), 500)
        self.assertEqual(
            notice["operations"]["strict"],
            [False, "ConnectionAbortedError", 10053],
        )

    def test_staging诊断只物化根内链接且保留源运行时不变(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-test-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            real = source / "python-real.exe"
            real.write_bytes(b"known interpreter bytes")
            link = source / "python.exe"
            try:
                link.symlink_to(real.name)
            except OSError as exc:
                self.skipTest(f"当前文件系统不支持符号链接测试：{exc}")

            destination = root / "icode-runtime-staging-copy"
            summary = stage_runtime(source, destination)

            self.assertEqual(summary["materialized_links"], 1)
            self.assertEqual((destination / "python.exe").read_bytes(), real.read_bytes())
            self.assertFalse((destination / "python.exe").is_symlink())
            self.assertTrue(link.is_symlink())
            self.assertEqual(windows_appcontainer._runtime_reparse_inventory(destination)["symbolic_link"], 0)

    def test_runtime重解析清点保留root词法拼写避免链接目标别名误判(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-reparse-lexical-") as raw:
            runtime = Path(raw) / "runtime"
            runtime.mkdir()
            target = runtime / "python-real.exe"
            target.write_bytes(b"inside")
            (runtime / "python.exe").symlink_to(target.name)

            # Windows may resolve an 8.3 root spelling to its long form while
            # os.readlink retains the link's original spelling. Inventory is
            # lexical by contract; the later disposable-copy step separately
            # resolves and validates the final file object before following it.
            with mock.patch.object(
                Path, "resolve", side_effect=AssertionError("root spelling was rewritten"),
            ):
                summary = windows_appcontainer._runtime_reparse_inventory(runtime)

        self.assertEqual(summary["link_target_inside_root"], 1)
        self.assertEqual(summary["link_target_outside_root"], 0)

    def test_stagingACL诊断只接受runner临时目录中的专用根(self) -> None:
        validate_roots = getattr(
            windows_appcontainer, "_validate_diagnostic_runtime_roots", None,
        )
        self.assertTrue(callable(validate_roots), "缺少 staging ACL 诊断根验证器")
        if not callable(validate_roots):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-staging-test-") as raw:
            parent = Path(raw)
            workspace = parent / "task"
            workspace.mkdir()
            staging = parent / "icode-runtime-staging-copy"
            staging.mkdir()
            executable = staging / "python.exe"
            executable.write_bytes(b"native executable placeholder")
            self.assertEqual(
                validate_roots(
                    (staging,), executable=executable, workspace=workspace,
                ),
                (staging.resolve(),),
            )

            ordinary = parent / "runtime"
            ordinary.mkdir()
            with self.assertRaises(_AppContainerSetupError):
                validate_roots(
                    (ordinary,), executable=ordinary / "python.exe", workspace=workspace,
                )
            with self.assertRaises(_AppContainerSetupError):
                validate_roots(
                    (staging,), executable=ordinary / "python.exe", workspace=workspace,
                )

    def test显式staging根不能绕过ACL诊断门(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-staging-gate-") as raw:
            result = run_windows_appcontainer(
                [sys.executable], cwd=raw, timeout_seconds=1,
                _diagnostic_runtime_roots=(Path(raw),),
            )
        self.assertEqual(result.error, "invalid_diagnostic_probe")

    def test_staging诊断拒绝根外链接且不创建副本(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-outside-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            outside = root / "outside.bin"
            outside.write_bytes(b"private")
            link = source / "python.exe"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"当前文件系统不支持符号链接测试：{exc}")
            destination = root / "icode-runtime-staging-copy"

            with self.assertRaises(_AppContainerSetupError) as raised:
                stage_runtime(source, destination)

            self.assertEqual(raised.exception.error, "runtime_staging_unsafe_reparse")
            self.assertFalse(destination.exists())
            self.assertEqual(outside.read_bytes(), b"private")

    def test_staging诊断拒绝非专用或临时目录外目标(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-target-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            (source / "python.exe").write_bytes(b"runtime")
            destinations = (
                root / "ordinary-directory-name",
                Path(tempfile.gettempdir()).resolve().parent
                / f"icode-runtime-staging-outside-{os.getpid()}",
            )
            for destination in destinations:
                with self.subTest(destination_kind="named" if destination.parent == root else "outside"):
                    with self.assertRaises(_AppContainerSetupError) as raised:
                        stage_runtime(source, destination)
                    self.assertEqual(raised.exception.error, "runtime_staging_copy_failed")
                    self.assertFalse(destination.exists())

    def test_staging诊断拒绝目录链接避免递归复制(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-dirlink-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            target = source / "target"
            target.mkdir()
            (target / "sentinel.bin").write_bytes(b"inside")
            alias = source / "target-alias"
            try:
                alias.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"当前文件系统不支持目录符号链接测试：{exc}")
            destination = root / "icode-runtime-staging-copy"

            with self.assertRaises(_AppContainerSetupError) as raised:
                stage_runtime(source, destination)

            self.assertEqual(raised.exception.error, "runtime_staging_unsafe_reparse")
            self.assertFalse(destination.exists())
            self.assertEqual((target / "sentinel.bin").read_bytes(), b"inside")

    def test_staging诊断拒绝词法根内的链接循环(self) -> None:
        stage_runtime = getattr(
            windows_appcontainer, "_copy_runtime_tree_for_diagnostic", None,
        )
        self.assertTrue(callable(stage_runtime), "缺少 runtime staging 诊断入口")
        if not callable(stage_runtime):
            return
        with tempfile.TemporaryDirectory(prefix="icode-runtime-stage-link-chain-") as raw:
            root = Path(raw)
            source = root / "runtime"
            source.mkdir()
            first_link = source / "first-link.bin"
            second_link = source / "second-link.bin"
            try:
                first_link.symlink_to(second_link.name)
                second_link.symlink_to(first_link.name)
            except OSError as exc:
                self.skipTest(f"当前文件系统不支持符号链接测试：{exc}")
            destination = root / "icode-runtime-staging-copy"

            with self.assertRaises(_AppContainerSetupError) as raised:
                stage_runtime(source, destination)

            self.assertEqual(raised.exception.error, "runtime_staging_unsafe_reparse")
            self.assertFalse(destination.exists())

    def test_reparse点原因映射为固定脱敏类别(self) -> None:
        symlink_mode = mock.Mock(st_mode=stat.S_IFLNK, st_reparse_tag=0)
        junction_tag = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
        symlink_tag = getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C)
        junction = mock.Mock(st_mode=stat.S_IFDIR, st_reparse_tag=junction_tag)
        symlink = mock.Mock(st_mode=stat.S_IFREG, st_reparse_tag=symlink_tag)
        unknown = mock.Mock(st_mode=stat.S_IFDIR, st_reparse_tag=0x12345678)

        self.assertEqual(windows_appcontainer._reparse_kind(symlink_mode), "symbolic_link")
        self.assertEqual(windows_appcontainer._reparse_kind(junction), "mount_point")
        self.assertEqual(windows_appcontainer._reparse_kind(symlink), "symbolic_link")
        self.assertEqual(windows_appcontainer._reparse_kind(unknown), "other_reparse")

    def test_reparse目标关系诊断只返回固定路径关系类别(self) -> None:
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                "python311.exe", r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "inside_root",
        )
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                r"..\outside\python311.exe",
                r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "outside_root",
        )
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                r"\\build-share\python\python.exe",
                r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "outside_root",
        )
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                r"\??\Volume{1234}\python.exe",
                r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "unknown",
        )
        self.assertEqual(
            windows_appcontainer._classify_runtime_link_target(
                r"\\?\C:\hostedtoolcache\windows\Python\3.11\x64\python311.exe",
                r"C:\hostedtoolcache\windows\Python\3.11\x64",
                r"C:\hostedtoolcache\windows\Python\3.11\x64", windows=True,
            ),
            "inside_root",
        )

    def test_runtime重解析清点不跟随链接且不输出目标(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-reparse-inventory-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            workspace = parent / "task"
            workspace.mkdir()
            internal_target = runtime / "python-real.exe"
            internal_target.write_bytes(b"inside")
            external_target = parent / "outside.exe"
            external_target.write_bytes(b"outside")
            external_directory = parent / "outside-runtime"
            external_directory.mkdir()
            (external_directory / "sentinel.exe").write_bytes(b"outside")
            links = (
                runtime / "python.exe", runtime / "helper.exe",
                runtime / "vendor",
            )
            try:
                links[0].symlink_to(internal_target)
                links[1].symlink_to(external_target)
                links[2].symlink_to(external_directory, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"文件系统不支持符号链接清点测试：{exc}")

            summary = windows_appcontainer._runtime_reparse_inventory(runtime)

        self.assertEqual(summary["entries"], 4)
        self.assertEqual(summary["symbolic_link"], 3)
        self.assertEqual(summary["link_target_inside_root"], 1)
        self.assertEqual(summary["link_target_outside_root"], 2)
        self.assertEqual(summary["link_target_unknown"], 0)
        self.assertNotIn(str(parent), repr(summary))

        with tempfile.TemporaryDirectory(prefix="icode-runtime-reparse-inventory-limit-") as raw:
            root = Path(raw)
            (root / "first").write_text("1", encoding="utf-8")
            (root / "second").write_text("2", encoding="utf-8")
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._runtime_reparse_inventory(root, max_entries=1)
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._runtime_reparse_inventory(
                    root, deadline=time.monotonic() - 1,
                )

    @unittest.skipUnless(
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
        and os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_REPARSE_INVENTORY") == "true",
        "运行时 reparse 清点只在单独启用的 Windows Actions 诊断步骤执行",
    )
    def test_诊断Python运行时重解析目标关系(self) -> None:
        roots = tuple(dict.fromkeys((Path(sys.prefix), Path(sys.base_prefix))))
        summary = {
            "root_count": len(roots),
            "entries": 0,
            "symbolic_link": 0,
            "mount_point": 0,
            "other_reparse": 0,
            "link_target_inside_root": 0,
            "link_target_outside_root": 0,
            "link_target_unknown": 0,
        }
        for root in roots:
            observed = windows_appcontainer._runtime_reparse_inventory(root)
            for name, count in observed.items():
                summary[name] += count
        self._workflow_notice(
            "Python runtime reparse inventory (path-free lexical relation)",
            json.dumps(summary, ensure_ascii=True, separators=(",", ":")),
        )

    def test_runtime根在触碰文件系统前识别UNC路径(self) -> None:
        self.assertTrue(
            windows_appcontainer._is_unc_runtime_root(
                r"\\build-share\python\3.12", windows=True,
            ),
        )
        self.assertTrue(
            windows_appcontainer._is_unc_runtime_root(
                "//build-share/python/3.12", windows=True,
            ),
        )
        self.assertFalse(
            windows_appcontainer._is_unc_runtime_root(
                r"C:\hostedtoolcache\Python\3.12", windows=True,
            ),
        )
        self.assertFalse(
            windows_appcontainer._is_unc_runtime_root(
                r"\\build-share\python\3.12", windows=False,
            ),
        )

    def test_workspace_DACL读取不要求运行时快照对象标识(self) -> None:
        snapshot = windows_appcontainer._DaclSnapshot(
            path=Path("runtime"), dacl=b"dacl", control=0, revision=1,
            present=True, defaulted=False, file_identity=(1, 0),
        )
        with mock.patch.object(
            windows_appcontainer, "_read_dacl_state", return_value=snapshot,
        ) as read_state:
            dacl, protected = windows_appcontainer._read_dacl(
                Path("runtime"), object(), object(),
            )
        self.assertEqual(dacl, b"dacl")
        self.assertFalse(protected)
        self.assertEqual(read_state.call_args.args[0], Path("runtime"))

    def _workflow_notice(self, name: str, detail: str) -> None:
        """Expose only bounded probe outcomes in public Actions annotations."""
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return
        safe_detail = detail[:500].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title=R2.3 {name}::{safe_detail}", flush=True)

    def _workflow_json_notice(self, name: str, detail: dict[str, object]) -> None:
        encoded = json.dumps(detail, ensure_ascii=True, separators=(",", ":"))
        self.assertLessEqual(
            len(encoded), 500,
            f"R2.3 JSON notice {name!r} would be silently truncated",
        )
        self._workflow_notice(name, encoded)

    def test_Reviewer宿主普通用户校验在非Windows上返回固定原因码(self) -> None:
        status = _current_process_standard_user_status("S-1-5-21-test")
        self.assertEqual(status, "unsupported_platform")

    def test_CheckTokenMembership使用主令牌的模拟副本且关闭句柄(self) -> None:
        token = ctypes.c_void_p(0x1234)
        admin_sid = ctypes.c_void_p(0x5678)
        advapi = mock.Mock()
        kernel = mock.Mock()

        def duplicate_primary_token(
            source: ctypes.c_void_p, level: int, target: ctypes.c_void_p,
        ) -> int:
            self.assertEqual(source.value, token.value)
            self.assertEqual(level, 2)
            ctypes.cast(target, ctypes.POINTER(ctypes.c_void_p)).contents.value = 0x9ABC
            return 1

        advapi.DuplicateToken.side_effect = duplicate_primary_token
        advapi.CheckTokenMembership.return_value = 1

        status = _query_administrators_group_membership_status(
            token, admin_sid, advapi, kernel,
        )

        self.assertEqual(status, "not_member")
        checked_token = advapi.CheckTokenMembership.call_args.args[0]
        self.assertEqual(checked_token.value, 0x9ABC)
        self.assertEqual(advapi.CheckTokenMembership.call_args.args[1].value, admin_sid.value)
        kernel.CloseHandle.assert_called_once_with(checked_token)

    def test_管理员组查询的令牌复制失败时不调用成员检查(self) -> None:
        advapi = mock.Mock()
        kernel = mock.Mock()
        advapi.DuplicateToken.return_value = 0

        status = _query_administrators_group_membership_status(
            ctypes.c_void_p(1), ctypes.c_void_p(2), advapi, kernel,
        )

        self.assertEqual(status, "administrators_token_duplicate_failed")
        advapi.CheckTokenMembership.assert_not_called()
        kernel.CloseHandle.assert_not_called()

    def test_CheckTokenMembership发现管理员组启用时返回成员状态(self) -> None:
        advapi = mock.Mock()
        kernel = mock.Mock()
        impersonation_token = 0x9ABC

        def duplicate_token(
            _source: ctypes.c_void_p, _level: int, target: ctypes.c_void_p,
        ) -> int:
            ctypes.cast(target, ctypes.POINTER(ctypes.c_void_p)).contents.value = impersonation_token
            return 1

        def check_membership(
            checked_token: ctypes.c_void_p, _sid: ctypes.c_void_p, member: ctypes.c_void_p,
        ) -> int:
            self.assertEqual(checked_token.value, impersonation_token)
            ctypes.cast(member, ctypes.POINTER(ctypes.c_int)).contents.value = 1
            return 1

        advapi.DuplicateToken.side_effect = duplicate_token
        advapi.CheckTokenMembership.side_effect = check_membership

        status = _query_administrators_group_membership_status(
            ctypes.c_void_p(0x1234), ctypes.c_void_p(0x5678), advapi, kernel,
        )

        self.assertEqual(status, "member")
        kernel.CloseHandle.assert_called_once()

    def test_Reviewer网络超时回执必须绑定尝试未连接和精确超时代码(self) -> None:
        self.assertIs(_network_attempt_timed_out(True, False, 10060, True), True)
        for attempted, connected, error_code, terminal_error in (
            (False, False, 10060, True),
            (True, True, 10060, True),
            (True, False, 10060, False),
            (True, False, 10035, False),
            (True, False, 10013, True),
            (True, False, 10061, True),
            (True, False, -1, True),
            (True, None, 10035, False),
            (True, False, True, True),
        ):
            with self.subTest(
                attempted=attempted, connected=connected, error_code=error_code,
                terminal_error=terminal_error,
            ):
                self.assertIs(
                    _network_attempt_timed_out(
                        attempted, connected, error_code, terminal_error,
                    ),
                    False,
                )

    def test_Reviewer快照原生探针脚本在非Windows主机可静态解析(self) -> None:
        captured_scripts: list[str] = []
        captured_notices: list[tuple[str, str]] = []

        class _CaptureAssertions:
            def assertTrue(self, *_args: object, **_kwargs: object) -> None:
                return None

            def assertEqual(self, *_args: object, **_kwargs: object) -> None:
                return None

            def assertIs(self, *_args: object, **_kwargs: object) -> None:
                return None

            def _workflow_json_notice(
                self, name: str, detail: dict[str, object],
            ) -> None:
                encoded = json.dumps(detail, ensure_ascii=True, separators=(",", ":"))
                if len(encoded) > 500:
                    raise AssertionError("native Reviewer probe notice exceeds GitHub limit")
                captured_notices.append((name, encoded))

        with tempfile.TemporaryDirectory(prefix="icode-reviewer-probe-script-") as raw:
            source_root = Path(raw) / "source-python"
            source_root.mkdir()
            source_executable = source_root / Path(sys.executable).name
            source_executable.write_bytes(b"synthetic Python executable")

            def stage_runtime(_source: Path, destination: Path) -> dict[str, int]:
                destination.mkdir()
                (destination / Path(sys.executable).name).write_bytes(b"synthetic staged Python")
                return {"staged_entries": 1}

            def capture_runner(argv: list[str], **_kwargs: object) -> WindowsJobResult:
                script = argv[-1]
                compile(script, "<reviewer-snapshot-probe-captured>", "exec")
                captured_scripts.append(script)
                return WindowsJobResult(
                    True, 0, None, True,
                    "reviewer_snapshot_acl_restore_verified=true;runtime_acl_restore_verified=true",
                )

            with mock.patch.object(sys, "prefix", str(source_root)), \
                 mock.patch.object(sys, "base_prefix", str(source_root)), \
                 mock.patch(
                     "icode.windows_appcontainer._copy_runtime_tree_for_diagnostic",
                     side_effect=stage_runtime,
                 ), mock.patch(
                     "tests.test_windows_appcontainer.subprocess.run",
                     return_value=mock.Mock(returncode=0),
                 ), mock.patch(
                     "tests.test_windows_appcontainer._current_process_standard_user_status",
                     return_value="verified",
                 ), mock.patch(
                     "tests.test_windows_appcontainer._dacl_write_control_succeeds",
                     return_value=True,
                 ), mock.patch.dict(
                     os.environ,
                     {"ICODE_DIAGNOSTIC_STANDARD_USER_SID": "S-1-5-21-1-2-3-1001"},
                 ), mock.patch(
                     "tests.test_windows_appcontainer.run_windows_appcontainer",
                     side_effect=capture_runner,
                 ):
                TestWindowsAppContainer.test_Reviewer快照AppContainer只读边界与Job清理.__wrapped__(
                    _CaptureAssertions(),
                )

        notice_names = {name for name, _encoded in captured_notices}
        self.assertIn("Windows Reviewer snapshot access", notice_names)
        self.assertIn("Windows Reviewer snapshot writes and cleanup", notice_names)
        self.assertIn("Windows Reviewer access diagnostics", notice_names)
        self.assertIn("Windows Reviewer handle cleanup diagnostics", notice_names)
        self.assertIn("Windows Reviewer WriteFile diagnostics", notice_names)
        self.assertIn("Windows Reviewer loopback network denial", notice_names)
        self.assertIn("Windows Reviewer write canary fingerprints", notice_names)
        self.assertTrue(all(len(encoded) <= 500 for _name, encoded in captured_notices))
        network_notice = json.loads(next(
            encoded
            for name, encoded in captured_notices
            if name == "Windows Reviewer loopback network denial"
        ))
        self.assertIs(network_notice["ipv4_network_wait_expired"], False)
        self.assertIs(network_notice["ipv4_network_timed_out"], False)
        self.assertIs(network_notice["ipv6_network_wait_expired"], False)
        self.assertIs(network_notice["ipv6_network_timed_out"], False)
        writes_notice = json.loads(next(
            encoded
            for name, encoded in captured_notices
            if name == "Windows Reviewer snapshot writes and cleanup"
        ))
        self.assertIs(writes_notice["write_canary_before_unchanged"], True)
        self.assertIs(writes_notice["write_canary_unchanged"], True)
        self.assertIs(writes_notice["write_canary_matches_expected_result"], False)
        max_error_notice = {
            key: {"winerror": 0xFFFFFFFF, "errno": 0xFFFFFFFF}
            for key in (
                "outside_snapshot", "workspace", "home", "ledger", "write",
                "delete", "rename", "create", "dacl_write_dac",
            )
        }
        self.assertLessEqual(
            len(json.dumps(max_error_notice, separators=(",", ":"))), 500,
        )
        max_close_errors = {
            key: 0xFFFFFFFF
            for key in (
                "approved_read", "outside_snapshot", "workspace", "home", "ledger",
                "write", "create",
            )
        }
        self.assertLessEqual(
            len(json.dumps(max_close_errors, separators=(",", ":"))), 500,
        )
        max_write_diagnostics = {
            "stage": "writefile",
            "io_succeeded": False,
            "requested_bytes": 7,
            "bytes_transferred": 0xFFFFFFFF,
        }
        self.assertLessEqual(
            len(json.dumps(max_write_diagnostics, separators=(",", ":"))), 500,
        )
        max_canary_fingerprints = {
            "before_length": 0x7FFFFFFFFFFFFFFF,
            "before_sha256": "f" * 64,
            "after_length": 0x7FFFFFFFFFFFFFFF,
            "after_sha256": "f" * 64,
        }
        self.assertLessEqual(
            len(json.dumps(max_canary_fingerprints, separators=(",", ":"))), 500,
        )
        max_network_notice = {
            "ipv4_host_control": True,
            "ipv4_network_attempted": True,
            "ipv4_network_connected": False,
            "ipv4_network_connect_denied": True,
            "ipv4_network_error": 0xFFFFFFFF,
            "ipv4_canary_received": False,
            "ipv6_host_control": True,
            "ipv6_network_attempted": True,
            "ipv6_network_connected": False,
            "ipv6_network_connect_denied": True,
            "ipv6_network_error": 0xFFFFFFFF,
            "ipv6_canary_received": False,
        }
        self.assertLessEqual(
            len(json.dumps(max_network_notice, separators=(",", ":"))), 500,
        )
        self.assertEqual(len(captured_scripts), 1)
        self.assertEqual(
            captured_scripts[0].count(
                "requested_bytes=len(write_payload) if io_kind=='write' else 0",
            ),
            1,
        )
        for required_probe in (
            "outside_snapshot_denied", "workspace_denied", "home_denied",
            "ledger_denied", "write_denied", "delete_denied", "rename_denied",
            "create_denied", "dacl_write_dac_denied",
            "0x00060000", "capability_count",
            "advapi.DuplicateToken.argtypes",
            "OpenProcessToken(kernel.GetCurrentProcess(),0x000a,",
            "DuplicateToken(token,2,ctypes.byref(admin_token))",
            "kernel.CheckTokenMembershipEx.argtypes",
            "CheckTokenMembershipEx(admin_token,admin_sid,0x00000001,",
            "kernel.CloseHandle(admin_token)",
            "access_errors={}",
            "close_errors={}",
            "write_diagnostics={}",
            "def access_denied(key,call):",
            "if code==5: return True",
            "def bounded_error_code(value):",
            "access_errors[key]={'winerror':bounded_error_code(code),'errno':bounded_error_code(getattr(exc,'errno',None))}",
            "facts['access_errors']=access_errors",
            "if error_code==5: return True",
            "access_errors['dacl_write_dac']={'winerror':bounded_error_code(error_code),'errno':-1}",
            "native_kernel=ctypes.WinDLL('kernel32',use_last_error=True)",
            "native_kernel.CreateFileW.argtypes=",
            "native_kernel.ReadFile.argtypes=",
            "native_kernel.WriteFile.argtypes=",
            "INVALID_HANDLE_VALUE=ctypes.c_void_p(-1).value",
            "def native_file_access(key,path,desired_access,disposition,io_kind=None):",
            "handle=native_kernel.CreateFileW(",
            "code=ctypes.get_last_error()",
            "native_kernel.ReadFile(",
            "native_kernel.WriteFile(",
            "native_kernel.CloseHandle(handle)",
            "def native_access_denied(key,path,desired_access,io_kind=None,disposition=3):",
            "close_errors[key]=bounded_error_code(close_error)",
            "denied=cleanup_ok and code==5",
            "if key=='write' and bytes_transferred!=0: denied=False",
            "return denied",
            "facts['close_errors']=close_errors",
            "write_diagnostics['write']={'stage':stage,'io_succeeded':io_succeeded,"
            "'requested_bytes':requested_bytes,'bytes_transferred':"
            "bounded_error_code(bytes_transferred)}",
            "facts['write_diagnostics']=write_diagnostics",
            "native_access_denied('outside_snapshot',outside,0x80000000,'read')",
            "if key not in {'child_pid','access_errors','close_errors','write_diagnostics',"
            "'ipv4_network_connected','ipv4_network_error','ipv4_network_wait_expired',"
            "'ipv4_network_terminal_error','ipv6_network_connected','ipv6_network_error',"
            "'ipv6_network_wait_expired','ipv6_network_terminal_error'}",
            "import ctypes,hashlib,json,os,pathlib,select,socket,subprocess,sys,time",
            "def network_connect_denied(family,address,port):",
            "connection.setblocking(False)",
            "code=bounded_error_code(connection.connect_ex((address,port)))",
            "if code in (WSAEWOULDBLOCK,WSAEINPROGRESS):",
            "select.select([], [connection], [connection], 3)",
            "connection.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR)",
            "return True,False,False,code,True",
            "terminal_error=True",
            "else: terminal_error=(code!=0)",
            "network_connect_denied(socket.AF_INET,'127.0.0.1',ipv4_loopback_port)",
            "network_connect_denied(socket.AF_INET6,'::1',ipv6_loopback_port)",
            "facts['ipv4_network_attempted']=ipv4_network_attempted",
            "facts['ipv4_network_connect_denied']",
            "facts['ipv4_network_wait_expired']=ipv4_network_wait_expired",
            "facts['ipv6_network_attempted']=ipv6_network_attempted",
            "facts['ipv6_network_connect_denied']",
            "facts['ipv6_network_wait_expired']=ipv6_network_wait_expired",
        ):
            with self.subTest(required_probe=required_probe):
                self.assertIn(required_probe, captured_scripts[0])

        probe_script = captured_scripts[0]
        helper_start = probe_script.index("network_canary=")
        helper_end = probe_script.index("ipv4_network_attempted,", helper_start)
        network_helper = probe_script[helper_start:helper_end]

        class _ConnectExSocket:
            def __init__(
                self, result: int = 0, error: OSError | None = None,
                completion: str = "write", completion_error: int = 0,
            ) -> None:
                self.result = result
                self.error = error
                self.completion = completion
                self.completion_error = completion_error
                self.closed = False
                self.sent: bytes | None = None
                self.blocking: bool | None = None
                self.wait_timeout: float | None = None
                self.timeout: float | None = None

            def setblocking(self, blocking: bool) -> None:
                self.blocking = blocking

            def settimeout(self, timeout: float) -> None:
                self.timeout = timeout
                self.blocking = False

            def connect_ex(self, _address: tuple[str, int]) -> int:
                if self.error is not None:
                    raise self.error
                return self.result

            def getsockopt(self, _level: int, _option: int) -> int:
                if self.completion == "socket_error":
                    error = OSError("getsockopt failed")
                    error.winerror = self.completion_error
                    raise error
                return self.completion_error

            def sendall(self, payload: bytes) -> None:
                self.sent = payload

            def close(self) -> None:
                self.closed = True

        def run_network_probe(connection: _ConnectExSocket) -> tuple[
            tuple[bool, bool, bool, int, bool, bool], dict[str, object],
        ]:
            socket_module = type("SocketModule", (), {
                "AF_INET": socket.AF_INET,
                "AF_INET6": socket.AF_INET6,
                "SOCK_STREAM": socket.SOCK_STREAM,
                "SOL_SOCKET": socket.SOL_SOCKET,
                "SO_ERROR": socket.SO_ERROR,
                "socket": staticmethod(lambda *_args: connection),
            })()

            def select_sockets(
                _readable: list[object], writable: list[object],
                exceptional: list[object], timeout: float,
            ) -> tuple[list[object], list[object], list[object]]:
                connection.wait_timeout = timeout
                if connection.completion == "timeout":
                    return [], [], []
                if connection.completion == "select_error":
                    error = OSError("select failed")
                    error.winerror = connection.completion_error
                    raise error
                if connection.completion == "exception":
                    return [], [], exceptional
                return [], writable, []

            select_module = type("SelectModule", (), {
                "select": staticmethod(select_sockets),
            })()
            namespace: dict[str, object] = {
                "socket": socket_module,
                "select": select_module,
            }
            exec(network_helper, namespace)
            probe = namespace["network_connect_denied"]
            return probe(socket.AF_INET, "127.0.0.1", 32123), namespace

        for code, completion, completion_error, expected in (
            (10013, "write", 0, (True, False, True, 10013, False, True)),
            (10035, "exception", 10013, (True, False, True, 10013, False, True)),
            (10035, "exception", 10061, (True, False, False, 10061, False, True)),
            (10035, "exception", 10060, (True, False, False, 10060, False, True)),
            (10035, "select_error", 10013, (True, False, False, 10013, False, False)),
            (10035, "socket_error", 10013, (True, False, False, 10013, False, False)),
            (10036, "exception", 10013, (True, False, True, 10013, False, True)),
            (10035, "write", 0, (True, True, False, 0, False, False)),
            (10035, "timeout", 0, (True, False, False, 10035, True, False)),
            (10061, "write", 0, (True, False, False, 10061, False, True)),
            (0, "write", 0, (True, True, False, 0, False, False)),
        ):
            with self.subTest(
                connect_ex_code=code,
                completion=completion,
                completion_error=completion_error,
            ):
                connection = _ConnectExSocket(
                    result=code,
                    completion=completion,
                    completion_error=completion_error,
                )
                outcome, namespace = run_network_probe(connection)

                self.assertEqual(outcome, expected)
                self.assertIs(
                    _network_attempt_timed_out(
                        outcome[0], outcome[1], outcome[3], outcome[5],
                    ),
                    outcome[3] == 10060 and outcome[5] is True,
                )
                self.assertTrue(connection.closed)
                self.assertIs(connection.blocking, False)
                if code in (10035, 10036):
                    self.assertEqual(connection.wait_timeout, 3)
                if expected[1]:
                    self.assertEqual(connection.sent, namespace["network_canary"])
                else:
                    self.assertIsNone(connection.sent)

        access_denied = OSError("access denied")
        access_denied.winerror = 10013
        socket_timeout = OSError("connect timed out")
        socket_timeout.winerror = 10060
        for error, expected in (
            (access_denied, (True, False, True, 10013, False, True)),
            (socket_timeout, (True, False, False, 10060, False, True)),
            (OSError("error code unavailable"), (True, False, False, -1, False, True)),
        ):
            with self.subTest(connect_ex_exception=expected[3]):
                connection = _ConnectExSocket(error=error)
                outcome, _namespace = run_network_probe(connection)

                self.assertEqual(outcome, expected)
                self.assertTrue(connection.closed)
        self.assertNotIn("advapi.CheckTokenMembership", captured_scripts[0])

        reviewer_source = inspect.getsource(
            TestWindowsAppContainer.test_Reviewer快照AppContainer只读边界与Job清理,
        )
        self.assertIn('"Windows Reviewer loopback network denial"', reviewer_source)
        acceptance_start = reviewer_source.index(
            "self.assertTrue(all(summary[key] is True for key in (",
        )
        acceptance_end = reviewer_source.index(")), summary)", acceptance_start)
        acceptance_contract = reviewer_source[acceptance_start:acceptance_end]
        self.assertIn('"write_canary_unchanged"', acceptance_contract)
        self.assertNotIn("network_timed_out", acceptance_contract)
        self.assertNotIn("write_canary_before_unchanged", acceptance_contract)
        self.assertNotIn("write_canary_matches_expected_result", acceptance_contract)
        self.assertNotIn("write_canary_matches_payload", acceptance_contract)
        summary_start = reviewer_source.index("summary = {")
        summary_end = reviewer_source.index(
            'self._workflow_json_notice(\n                    "Windows Reviewer probe preflight"',
            summary_start,
        )
        summary_contract = reviewer_source[summary_start:summary_end]
        facts_projection_start = summary_contract.index("for key in (")
        facts_projection_end = summary_contract.index(")\n                    },", facts_projection_start)
        facts_projection = summary_contract[facts_projection_start:facts_projection_end]
        self.assertNotIn('"write_canary_unchanged"', facts_projection)
        self.assertNotIn('"write_canary_matches_expected_result"', facts_projection)
        self.assertIn(
            '"write_canary_unchanged": write_canary_unchanged',
            summary_contract,
        )
        self.assertRegex(
            summary_contract,
            r'"write_canary_matches_expected_result":\s*\(\s*'
            r'write_canary_matches_expected_result\s*\)',
        )
        self.assertIn("expected_write_result = (", reviewer_source)
        self.assertIn(
            "write_payload + write_canary_original[len(write_payload):]",
            reviewer_source,
        )
        self.assertIn("write_canary_before_length", reviewer_source)
        self.assertIn("write_canary_before_sha256", reviewer_source)
        self.assertIn("write_canary_after_length", reviewer_source)
        self.assertIn("write_canary_after_sha256", reviewer_source)
        before_canary_read = reviewer_source.index(
            "write_canary_before = mutable_file.read_bytes()",
        )
        candidate_launch = reviewer_source.index(
            "candidate = run_windows_appcontainer(", before_canary_read,
        )
        after_canary_hash = reviewer_source.index(
            "write_canary_after_sha256 = hashlib.sha256(", candidate_launch,
        )
        self.assertLess(before_canary_read, candidate_launch)
        self.assertLess(candidate_launch, after_canary_hash)
        self.assertEqual(b"changed" + b"original\n"[len(b"changed"):], b"changedl\n")

        helper_start = captured_scripts[0].index("access_errors={}\n")
        network_helper_start = captured_scripts[0].index(
            "def network_connect_denied(family,address,port):", helper_start,
        )
        access_helper_start = captured_scripts[0].index(
            "def access_denied(key,call):", network_helper_start,
        )
        helper_end = captured_scripts[0].index(
            "def dacl_write_dac_denied(path):", access_helper_start,
        )
        helper_source = (
            captured_scripts[0][helper_start:network_helper_start]
            + captured_scripts[0][access_helper_start:helper_end]
        )
        error_helpers: dict[str, object] = {}
        exec("import errno\n" + helper_source, error_helpers)

        def raising(error: OSError) -> Callable[[], None]:
            def operation() -> None:
                raise error

            return operation

        class WindowsAccessDenied(PermissionError):
            @property
            def winerror(self) -> int:
                return 5

        class WindowsSharingViolation(PermissionError):
            @property
            def winerror(self) -> int:
                return 32

        access_denied = error_helpers["access_denied"]
        self.assertTrue(
            access_denied(
                "winerror_5",
                raising(WindowsAccessDenied(errno.EACCES, "access denied")),
            ),
        )
        self.assertEqual(
            error_helpers["access_errors"]["winerror_5"],
            {"winerror": 5, "errno": errno.EACCES},
        )
        self.assertFalse(
            access_denied(
                "errno_access_denied_without_winerror",
                raising(PermissionError(errno.EACCES, "access denied")),
            ),
        )
        self.assertEqual(
            error_helpers["access_errors"]["errno_access_denied_without_winerror"],
            {"winerror": -1, "errno": errno.EACCES},
        )
        self.assertFalse(
            access_denied(
                "sharing_violation",
                raising(WindowsSharingViolation(errno.EACCES, "sharing violation")),
            ),
        )
        self.assertEqual(
            error_helpers["access_errors"]["sharing_violation"],
            {"winerror": 32, "errno": errno.EACCES},
        )
        self.assertFalse(
            access_denied(
                "path_missing",
                raising(FileNotFoundError(errno.ENOENT, "missing path")),
            ),
        )
        self.assertEqual(
            error_helpers["access_errors"]["path_missing"],
            {"winerror": -1, "errno": errno.ENOENT},
        )
        self.assertFalse(
            access_denied("other_error", raising(OSError(errno.EIO, "I/O error"))),
        )
        self.assertEqual(
            error_helpers["access_errors"]["other_error"],
            {"winerror": -1, "errno": errno.EIO},
        )

        native_start = captured_scripts[0].index("def native_file_access(key,path,")
        native_end = captured_scripts[0].index("token=query_token()", native_start)
        native_source = captured_scripts[0][native_start:native_end]
        for immediate_error_check in (
            "handle=native_kernel.CreateFileW(str(path),desired_access,0x7,None,"
            "disposition,0x80,None)\n"
            "    if handle==INVALID_HANDLE_VALUE:\n"
            "        return data,ctypes.get_last_error(),True",
            "if not native_kernel.ReadFile(handle,buffer,len(buffer),"
            "ctypes.byref(transferred),None):\n"
            "                io_succeeded=False\n"
            "                error_code=ctypes.get_last_error()",
            "if not native_kernel.WriteFile(handle,payload,requested_bytes,"
            "ctypes.byref(transferred),None):\n"
            "                io_succeeded=False\n"
            "                error_code=ctypes.get_last_error()",
        ):
            self.assertIn(immediate_error_check, native_source)

        class FakeDWORD:
            def __init__(self) -> None:
                self.value = 0

        class FakeWintypes:
            DWORD = FakeDWORD

        class FakeCtypes:
            def __init__(self, last_error: dict[str, int]) -> None:
                self._last_error = last_error

            def set_last_error(self, value: int) -> None:
                self._last_error["value"] = value

            def get_last_error(self) -> int:
                return self._last_error["value"]

            create_string_buffer = staticmethod(ctypes.create_string_buffer)
            byref = staticmethod(lambda value: value)

        class FakeKernel:
            def __init__(
                self,
                last_error: dict[str, int],
                close_ok: bool,
                create_handle: int = 7,
                create_error: int = 0,
                write_ok: bool = False,
                write_transferred: int = 0,
            ) -> None:
                self._last_error = last_error
                self._close_ok = close_ok
                self._create_handle = create_handle
                self._create_error = create_error
                self._write_ok = write_ok
                self._write_transferred = write_transferred
                self.close_calls = 0

            def CreateFileW(self, *_args: object) -> int:
                self._last_error["value"] = self._create_error
                return self._create_handle

            def ReadFile(self, *_args: object) -> bool:
                self._last_error["value"] = 5
                return False

            def WriteFile(self, *_args: object) -> bool:
                transferred = _args[3]
                transferred.value = self._write_transferred
                self._last_error["value"] = 0 if self._write_ok else 5
                return self._write_ok

            def CloseHandle(self, _handle: int) -> bool:
                self.close_calls += 1
                self._last_error["value"] = 6
                return self._close_ok

        def run_native_access(
            *,
            close_ok: bool = True,
            create_handle: int = 7,
            create_error: int = 0,
            io_kind: str = "read",
            write_ok: bool = False,
            write_transferred: int = 0,
        ) -> tuple[
            bool,
            dict[str, object],
            dict[str, object],
            dict[str, object],
            FakeKernel,
        ]:
            last_error = {"value": 0}
            kernel = FakeKernel(
                last_error, close_ok, create_handle, create_error,
                write_ok, write_transferred,
            )
            namespace: dict[str, object] = {
                "ctypes": FakeCtypes(last_error),
                "wintypes": FakeWintypes,
                "native_kernel": kernel,
                "INVALID_HANDLE_VALUE": -1,
                "access_errors": {},
                "close_errors": {},
                "write_diagnostics": {},
                "write_payload": b"changed",
                "bounded_error_code": lambda value: (
                    value if type(value) is int and -0x80000000 <= value <= 0xFFFFFFFF else -1
                ),
            }
            exec(native_source, namespace)
            try:
                denied = namespace["native_access_denied"](
                    "write" if io_kind == "write" else "read",
                    Path("canary.txt"),
                    0x40000000 if io_kind == "write" else 0x80000000,
                    io_kind,
                )
            except RuntimeError as exc:
                self.fail(f"CloseHandle failure discarded the captured I/O error: {exc}")
            self.assertIs(type(denied), bool)
            return (
                denied,
                namespace["access_errors"],
                namespace["close_errors"],
                namespace["write_diagnostics"],
                kernel,
            )

        denied, native_errors, close_errors, _write_diagnostics, kernel = run_native_access(
            close_ok=False,
        )
        self.assertFalse(denied, "failed handle cleanup must not count as access denial")
        self.assertEqual(native_errors["read"], {"winerror": 5, "errno": -1})
        self.assertEqual(close_errors["read"], 6)
        self.assertEqual(kernel.close_calls, 1)

        denied, native_errors, close_errors, write_diagnostics, kernel = run_native_access(
            close_ok=False,
            io_kind="write",
            write_ok=False,
            write_transferred=0,
        )
        self.assertFalse(denied, "failed handle cleanup must not count as a write denial")
        self.assertEqual(native_errors["write"], {"winerror": 5, "errno": -1})
        self.assertEqual(close_errors["write"], 6)
        self.assertEqual(
            write_diagnostics["write"],
            {
                "stage": "writefile",
                "io_succeeded": False,
                "requested_bytes": 7,
                "bytes_transferred": 0,
            },
        )
        self.assertEqual(kernel.close_calls, 1)

        denied, native_errors, close_errors, _write_diagnostics, kernel = run_native_access()
        self.assertTrue(denied, "WinError 5 with successful cleanup is a denial")
        self.assertEqual(native_errors["read"], {"winerror": 5, "errno": -1})
        self.assertEqual(close_errors, {})
        self.assertEqual(kernel.close_calls, 1)

        denied, native_errors, close_errors, _write_diagnostics, kernel = run_native_access(
            create_handle=-1, create_error=32,
        )
        self.assertFalse(denied, "WinError 32 is not an access-denied result")
        self.assertEqual(native_errors["read"], {"winerror": 32, "errno": -1})
        self.assertEqual(close_errors, {})
        self.assertEqual(kernel.close_calls, 0)

        denied, native_errors, close_errors, write_diagnostics, kernel = run_native_access(
            io_kind="write", write_ok=False, write_transferred=0,
        )
        self.assertTrue(denied)
        self.assertEqual(native_errors["write"], {"winerror": 5, "errno": -1})
        self.assertEqual(close_errors, {})
        self.assertEqual(
            write_diagnostics["write"],
            {
                "stage": "writefile",
                "io_succeeded": False,
                "requested_bytes": 7,
                "bytes_transferred": 0,
            },
        )
        self.assertEqual(kernel.close_calls, 1)

        denied, native_errors, close_errors, write_diagnostics, kernel = run_native_access(
            io_kind="write", write_ok=False, write_transferred=3,
        )
        self.assertFalse(denied, "partial WriteFile failure must not count as a denied write")
        self.assertEqual(native_errors["write"], {"winerror": 5, "errno": -1})
        self.assertEqual(close_errors, {})
        self.assertEqual(
            write_diagnostics["write"],
            {
                "stage": "writefile",
                "io_succeeded": False,
                "requested_bytes": 7,
                "bytes_transferred": 3,
            },
        )
        self.assertEqual(kernel.close_calls, 1)

        denied, _native_errors, close_errors, write_diagnostics, kernel = run_native_access(
            io_kind="write", write_ok=True, write_transferred=3,
        )
        self.assertFalse(denied, "short successful WriteFile must not count as a denied write")
        self.assertEqual(close_errors, {})
        self.assertEqual(
            write_diagnostics["write"],
            {
                "stage": "writefile",
                "io_succeeded": True,
                "requested_bytes": 7,
                "bytes_transferred": 3,
            },
        )
        self.assertEqual(kernel.close_calls, 1)

        denied, _native_errors, close_errors, write_diagnostics, kernel = run_native_access(
            io_kind="write", write_ok=True, write_transferred=7,
        )
        self.assertFalse(denied)
        self.assertEqual(close_errors, {})
        self.assertEqual(
            write_diagnostics["write"],
            {
                "stage": "writefile",
                "io_succeeded": True,
                "requested_bytes": 7,
                "bytes_transferred": 7,
            },
        )
        self.assertEqual(kernel.close_calls, 1)

    def test_JSON工作流回执超限时必须显式失败(self) -> None:
        with self.assertRaises(AssertionError):
            self._workflow_json_notice("test", {"payload": "x" * 500})

    def test_staging基线规范化仅接受自动继承控制位变化(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-staging-acl-baseline-") as raw:
            root = Path(raw) / "icode-runtime-staging-test"
            root.mkdir()
            root_resolved = root.resolve(strict=True)
            before = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"original-dacl", control=0x0004, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            after = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"original-dacl", control=0x0404, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            with mock.patch.dict(os.environ, {
                "GITHUB_ACTIONS": "true",
                "RUNNER_OS": "Windows",
                "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
            }), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=(before, after),
            ), mock.patch.object(windows_appcontainer, "_set_dacl") as set_dacl:
                delta = windows_appcontainer._normalize_staged_runtime_acl_baseline(
                    root, object(), object(),
                )

        self.assertEqual(delta, 0x0400)
        set_dacl.assert_called_once()
        # The normalization helper deliberately passes its verified canonical
        # temp-root spelling to Win32, which may differ from an 8.3 alias.
        self.assertEqual(set_dacl.call_args.args[0], root_resolved)

    def test_staging基线已规范化时不再写入ACL(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-staging-acl-baseline-") as raw:
            root = Path(raw) / "icode-runtime-staging-test"
            root.mkdir()
            snapshot = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"original-dacl", control=0x0404, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            with mock.patch.dict(os.environ, {
                "GITHUB_ACTIONS": "true",
                "RUNNER_OS": "Windows",
                "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
            }), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", return_value=snapshot,
            ), mock.patch.object(windows_appcontainer, "_set_dacl") as set_dacl:
                delta = windows_appcontainer._normalize_staged_runtime_acl_baseline(
                    root, object(), object(),
                )

        self.assertEqual(delta, 0)
        set_dacl.assert_not_called()

    def test_staging基线规范化发现DACL变化时失败关闭(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-staging-acl-baseline-") as raw:
            root = Path(raw) / "icode-runtime-staging-test"
            root.mkdir()
            before = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"original-dacl", control=0x0004, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            after = windows_appcontainer._DaclSnapshot(
                path=root, dacl=b"changed-dacl", control=0x0404, revision=1,
                present=True, defaulted=False, file_identity=(1, 2),
            )
            with mock.patch.dict(os.environ, {
                "GITHUB_ACTIONS": "true",
                "RUNNER_OS": "Windows",
                "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
            }), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=(before, after),
            ), mock.patch.object(windows_appcontainer, "_set_dacl"):
                with self.assertRaises(_AppContainerSetupError) as raised:
                    windows_appcontainer._normalize_staged_runtime_acl_baseline(
                        root, object(), object(),
                    )

        self.assertEqual(raised.exception.error, "runtime_acl_normalization_failed")

    @staticmethod
    def _runtime_acl_restore_categories(
        transaction: windows_appcontainer._RuntimeAclTransaction,
        sid: ctypes.c_void_p,
    ) -> dict[str, object]:
        """Classify the first restore mismatch without exposing object paths."""
        try:
            root = transaction.roots[0]
            actual_paths = windows_appcontainer._walk_workspace(root)
            expected = {
                item.path: item for item in transaction.entries
                if item.path == root or item.path.is_relative_to(root)
            }
            actual_set = set(actual_paths)
            expected_set = set(expected)
            actual_only = len(actual_set - expected_set)
            expected_only = len(expected_set - actual_set)
            if actual_only or expected_only:
                return {
                    "state": "path_set_mismatch",
                    "actual_only": actual_only,
                    "expected_only": expected_only,
                }

            for path in actual_paths:
                current = windows_appcontainer._read_dacl_state(
                    path, transaction.advapi, transaction.kernel,
                )
                before = expected[path]
                dacl_changed = current.dacl != before.dacl
                metadata_changes = {
                    "control_changed": current.control != before.control,
                    "revision_changed": current.revision != before.revision,
                    "present_changed": current.present != before.present,
                    "defaulted_changed": current.defaulted != before.defaulted,
                    "file_identity_changed": current.file_identity != before.file_identity,
                }
                metadata_changed = any(metadata_changes.values())
                sid_residual = windows_appcontainer._contains_sid(
                    current.dacl, sid, transaction.advapi,
                )
                if dacl_changed or metadata_changed or sid_residual:
                    return {
                        "state": "object_mismatch",
                        "object": "root" if path == root else "descendant",
                        "dacl_changed": dacl_changed,
                        "metadata_changed": metadata_changed,
                        **metadata_changes,
                        "control_delta": before.control ^ current.control,
                        "sid_residual": sid_residual,
                    }
            return {"state": "snapshot_match_after_failure", "objects": len(actual_paths)}
        except _AppContainerSetupError as exc:
            return {"state": "inspection_failed", "category": exc.error}
        except (OSError, RuntimeError, ValueError):
            return {"state": "inspection_failed", "category": "filesystem_error"}

    def _observe_runtime_acl_restore(
        self,
        restore: Callable[[windows_appcontainer._RuntimeAclTransaction, ctypes.c_void_p], bool],
        transaction: windows_appcontainer._RuntimeAclTransaction,
        sid: ctypes.c_void_p,
        report: dict[str, object],
    ) -> bool:
        try:
            restored = restore(transaction, sid)
        except Exception:
            report.update({"state": "restore_exception"})
            raise
        report.update(
            {"state": "restored"}
            if restored
            else self._runtime_acl_restore_categories(transaction, sid)
        )
        return restored

    def test_runtime_ACL恢复诊断只报告脱敏的不匹配类别(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-diagnostic-") as raw:
            root = Path(raw) / "runtime"
            root.mkdir()
            child = root / "python.dll"
            child.write_bytes(b"runtime")

            def snapshot(path: Path, dacl: bytes, *, control: int = 0):
                info = path.lstat()
                return windows_appcontainer._DaclSnapshot(
                    path=path, dacl=dacl, control=control, revision=1,
                    present=True, defaulted=False,
                    file_identity=(int(info.st_dev), int(info.st_ino)),
                )

            transaction = windows_appcontainer._RuntimeAclTransaction(
                roots=(root,),
                entries=(snapshot(root, b"original-root"), snapshot(child, b"original-child")),
                advapi=object(), kernel=object(), snapshot_duration_ms=1,
            )
            child_after = snapshot(child, b"changed-child")
            root_after = snapshot(root, b"original-root", control=0x0400)
            child_original = snapshot(child, b"original-child")

            def read_state(path: Path, _advapi: object, _kernel: object):
                return snapshot(path, b"original-root") if path == root else child_after

            with mock.patch.object(
                windows_appcontainer, "_walk_workspace", return_value=[root, child],
            ), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ), mock.patch.object(
                windows_appcontainer, "_contains_sid", return_value=False,
            ):
                report = self._runtime_acl_restore_categories(
                    transaction, ctypes.c_void_p(123),
                )

        self.assertEqual(report["state"], "object_mismatch")
        self.assertEqual(report["object"], "descendant")
        self.assertTrue(report["dacl_changed"])
        self.assertFalse(report["metadata_changed"])
        self.assertFalse(report["control_changed"])
        self.assertFalse(report["revision_changed"])
        self.assertFalse(report["present_changed"])
        self.assertFalse(report["defaulted_changed"])
        self.assertFalse(report["file_identity_changed"])
        self.assertEqual(report["control_delta"], 0)
        self.assertNotIn(str(root), repr(report))

        with mock.patch.object(
            windows_appcontainer, "_walk_workspace", return_value=[root, child],
        ), mock.patch.object(
            windows_appcontainer, "_read_dacl_state",
            side_effect=lambda path, _advapi, _kernel: (
                root_after if path == root else child_original
            ),
        ), mock.patch.object(
            windows_appcontainer, "_contains_sid", return_value=False,
        ):
            root_report = self._runtime_acl_restore_categories(
                transaction, ctypes.c_void_p(123),
            )

        self.assertEqual(root_report["state"], "object_mismatch")
        self.assertEqual(root_report["object"], "root")
        self.assertFalse(root_report["dacl_changed"])
        self.assertTrue(root_report["metadata_changed"])
        self.assertTrue(root_report["control_changed"])
        self.assertFalse(root_report["revision_changed"])
        self.assertFalse(root_report["present_changed"])
        self.assertFalse(root_report["defaulted_changed"])
        self.assertFalse(root_report["file_identity_changed"])
        self.assertEqual(root_report["control_delta"], 0x0400)
        self.assertNotIn(str(root), repr(root_report))

    @staticmethod
    def _read_cmd_exit_status(path: Path) -> int | None:
        try:
            label, value = path.read_text(encoding="ascii").strip().split("=", 1)
            return int(value) if label == "exit_code" else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _profile_env_values(env_lines: list[str]) -> list[str]:
        return [
            line.split("=", 1)[1]
            for line in env_lines
            if line.partition("=")[0].casefold() == "localappdata" and "=" in line
        ]

    @classmethod
    def _profile_env_matches_api(cls, env_lines: list[str], profile_paths: list[str]) -> bool:
        values = cls._profile_env_values(env_lines)
        if len(profile_paths) != 1 or len(values) != 1:
            return False
        actual = values[0].rstrip("\\/").casefold()
        expected = profile_paths[0].rstrip("\\/").casefold()
        return bool(actual) and actual == expected

    @staticmethod
    def _profile_path_relation(actual: str, expected: str) -> str:
        actual_path = ntpath.normcase(ntpath.normpath(actual))
        expected_path = ntpath.normcase(ntpath.normpath(expected))
        if not ntpath.isabs(actual_path) or not ntpath.isabs(expected_path):
            return "invalid"
        if actual_path == expected_path:
            return "exact"
        try:
            common_path = ntpath.commonpath([actual_path, expected_path])
        except ValueError:
            return "other"
        if common_path == expected_path:
            relative_path = ntpath.relpath(actual_path, expected_path)
            components = relative_path.split(ntpath.sep)
            first_component = components[0].casefold()
            category = {
                "temp": "api_child_temp",
                "local": "api_child_local",
                "localstate": "api_child_local_state",
            }.get(first_component, "api_child_other")
            return category if len(components) == 1 else f"{category}_nested"
        if common_path == actual_path:
            return "api_parent"
        if ntpath.dirname(actual_path) == ntpath.dirname(expected_path):
            return "sibling"
        return "other"

    @staticmethod
    def _profile_path_stat_class(path: str) -> str:
        try:
            metadata = os.stat(path)
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if isinstance(exc, FileNotFoundError) or winerror in {2, 3}:
                return "not_found"
            if isinstance(exc, PermissionError) or winerror == 5:
                return "access_denied"
            return "other_error"
        return "directory" if stat.S_ISDIR(metadata.st_mode) else "not_directory"

    @staticmethod
    def _summarize_staged_environment(
        observation: object, api_profile: str | None,
    ) -> dict[str, object]:
        """Keep raw child environment paths local; publish only comparisons and classes."""
        names = {
            "LOCALAPPDATA": "localappdata",
            "TEMP": "temp",
            "TMP": "tmp",
        }
        if (
            not isinstance(observation, dict)
            or set(observation) != set(names)
            or not isinstance(api_profile, str)
            or not api_profile
        ):
            return {"complete": False}
        summary: dict[str, object] = {"complete": True}
        for source_name, output_name in names.items():
            item = observation.get(source_name)
            if not isinstance(item, dict):
                return {"complete": False}
            python_value = item.get("python_value")
            win32_value = item.get("win32_value")
            python_defined = isinstance(python_value, str) and bool(python_value)
            win32_defined = isinstance(win32_value, str) and bool(win32_value)
            matches = False
            if python_defined and win32_defined:
                matches = (
                    ntpath.normcase(ntpath.normpath(python_value))
                    == ntpath.normcase(ntpath.normpath(win32_value))
                )
            path_state = item.get("path_state")
            if path_state not in {
                "not_defined", "directory", "not_directory", "not_found",
                "path_not_found", "access_denied", "other_error",
            }:
                path_state = "invalid"
            result: dict[str, object] = {
                "python_defined": python_defined,
                "win32_defined": win32_defined,
                "python_win32_match": matches,
                "path_state": path_state,
            }
            if source_name == "LOCALAPPDATA":
                api_match = False
                if python_defined and isinstance(api_profile, str) and api_profile:
                    api_match = (
                        ntpath.normcase(ntpath.normpath(python_value))
                        == ntpath.normcase(ntpath.normpath(api_profile))
                    )
                result["api_match"] = api_match
            summary[output_name] = result
        return summary

    @staticmethod
    def _summarize_staged_profile_api(
        observation: object, host_api_profile: str | None,
    ) -> dict[str, object]:
        """Publish container identity and profile-path relations, never paths or SID."""
        required = {
            "token_is_appcontainer", "token_sid_defined", "profile_path",
            "profile_error", "profile_error_code", "profile_path_state",
            "environment_block_scan_complete", "environment_block_localappdata",
            "environment_block_error", "python_localappdata", "win32_localappdata",
        }
        if not isinstance(observation, dict) or not required.issubset(observation):
            return {"complete": False}
        if (
            not isinstance(observation["token_is_appcontainer"], bool)
            or not isinstance(observation["token_sid_defined"], bool)
            or not isinstance(observation["environment_block_scan_complete"], bool)
            or observation["environment_block_error"] is not None
            and not isinstance(observation["environment_block_error"], str)
            or not isinstance(observation["environment_block_localappdata"], list)
            or not all(
                isinstance(value, str) and value
                for value in observation["environment_block_localappdata"]
            )
            or observation["profile_path"] is not None
            and (not isinstance(observation["profile_path"], str) or not observation["profile_path"])
            or observation["profile_error"] is not None
            and not isinstance(observation["profile_error"], str)
            or observation["profile_error_code"] is not None
            and (not isinstance(observation["profile_error_code"], int)
                 or observation["profile_error_code"] < 0)
            or observation["profile_path_state"] not in {
                "not_defined", "directory", "not_directory", "not_found",
                "path_not_found", "access_denied", "other_error",
            }
            or any(
                observation[name] is not None and not isinstance(observation[name], str)
                for name in ("python_localappdata", "win32_localappdata")
            )
            or host_api_profile is not None
            and (not isinstance(host_api_profile, str) or not host_api_profile)
        ):
            return {"complete": False}

        profile_path = observation["profile_path"]
        python_value = observation["python_localappdata"]
        win32_value = observation["win32_localappdata"]
        environment_values = observation["environment_block_localappdata"]

        def same_path(left: object, right: object) -> bool:
            return (
                isinstance(left, str) and bool(left)
                and isinstance(right, str) and bool(right)
                and ntpath.normcase(ntpath.normpath(left))
                == ntpath.normcase(ntpath.normpath(right))
            )

        profile_error = observation["profile_error"]
        if profile_error is None:
            error = "none"
        elif profile_error in _RUNTIME_PROBE_ERROR_TYPES:
            error = profile_error
        else:
            error = "other"
        error_code = observation["profile_error_code"]
        if error_code is not None and error_code > 65535:
            error_code = None
        environment_block_error = observation["environment_block_error"]
        if environment_block_error is None:
            environment_error = "none"
        elif environment_block_error in _RUNTIME_PROBE_ERROR_TYPES:
            environment_error = environment_block_error
        else:
            environment_error = "other"
        if isinstance(profile_path, str):
            profile_relation = TestWindowsAppContainer._profile_path_relation(
                profile_path, host_api_profile or "",
            ) if host_api_profile else "unavailable"
        else:
            profile_relation = "unavailable"
        if isinstance(python_value, str) and isinstance(profile_path, str):
            environment_relation = TestWindowsAppContainer._profile_path_relation(
                python_value, profile_path,
            )
        else:
            environment_relation = "unavailable"
        return {
            "complete": True,
            "token_is_appcontainer": observation["token_is_appcontainer"],
            "token_sid_defined": observation["token_sid_defined"],
            "profile_api_ok": isinstance(profile_path, str) and error == "none",
            "profile_api_matches_host": same_path(profile_path, host_api_profile),
            "profile_api_relation": profile_relation,
            "profile_path_state": observation["profile_path_state"],
            "environment_block_scan_complete": observation["environment_block_scan_complete"],
            "environment_block_error": environment_error,
            "environment_entry_count": len(environment_values),
            "environment_block_matches_api": (
                len(environment_values) == 1
                and same_path(environment_values[0], profile_path)
            ),
            "python_win32_match": same_path(python_value, win32_value),
            "environment_matches_api": same_path(python_value, profile_path),
            "environment_relation": environment_relation,
            "error": error,
            "error_code": error_code,
        }

    @staticmethod
    def _summarize_localappdata_environment_ab(
        host_observation: object,
        appcontainer_observation: object,
        supplied_profile: str,
    ) -> dict[str, object]:
        """Compare explicit environment values while discarding both raw paths."""
        expected = {
            "launch_ok", "exit_code", "localappdata", "expected_localappdata",
        }
        app_expected = expected | {"cleanup_ok"}
        if (
            not isinstance(host_observation, dict)
            or not isinstance(appcontainer_observation, dict)
            or not expected.issubset(host_observation)
            or not app_expected.issubset(appcontainer_observation)
            or not isinstance(supplied_profile, str)
            or not supplied_profile
            or not ntpath.isabs(supplied_profile)
        ):
            return {"complete": False}

        for observation in (host_observation, appcontainer_observation):
            if (
                type(observation["launch_ok"]) is not bool
                or observation["exit_code"] is not None
                and type(observation["exit_code"]) is not int
                or observation["localappdata"] is not None
                and (not isinstance(observation["localappdata"], str)
                     or not observation["localappdata"])
                or observation["expected_localappdata"] is not None
                and (not isinstance(observation["expected_localappdata"], str)
                     or not observation["expected_localappdata"])
            ):
                return {"complete": False}
        if type(appcontainer_observation["cleanup_ok"]) is not bool:
            return {"complete": False}

        def same_path(left: object, right: str) -> bool:
            return (
                isinstance(left, str) and bool(left)
                and ntpath.normcase(ntpath.normpath(left))
                == ntpath.normcase(ntpath.normpath(right))
            )

        host_value = host_observation["localappdata"]
        host_sentinel = host_observation["expected_localappdata"]
        app_value = appcontainer_observation["localappdata"]
        app_sentinel = appcontainer_observation["expected_localappdata"]
        return {
            "complete": True,
            "host_launch_ok": host_observation["launch_ok"],
            "host_exit_ok": host_observation["exit_code"] == 0,
            "host_matches_supplied": same_path(host_value, supplied_profile),
            "host_sentinel_matches_supplied": same_path(host_sentinel, supplied_profile),
            "appcontainer_launch_ok": appcontainer_observation["launch_ok"],
            "appcontainer_exit_ok": appcontainer_observation["exit_code"] == 0,
            "appcontainer_cleanup_ok": appcontainer_observation["cleanup_ok"],
            "appcontainer_matches_supplied": same_path(app_value, supplied_profile),
            "appcontainer_sentinel_matches_supplied": same_path(
                app_sentinel, supplied_profile,
            ),
            "appcontainer_profile_relation": (
                TestWindowsAppContainer._profile_path_relation(
                    app_value, supplied_profile,
                )
                if isinstance(app_value, str) and app_value else "unavailable"
            ),
        }

    @staticmethod
    def _summarize_known_folder_observation(
        observation: object, profile_api_path: str,
    ) -> dict[str, object]:
        required = {
            "known_folder_path", "known_folder_error", "known_folder_error_code",
            "known_folder_path_state", "package_identity",
            "package_identity_error_code",
        }
        if (
            not isinstance(observation, dict)
            or not required.issubset(observation)
            or not isinstance(profile_api_path, str)
            or not profile_api_path
            or not ntpath.isabs(profile_api_path)
        ):
            return {"complete": False}
        path = observation["known_folder_path"]
        error = observation["known_folder_error"]
        error_code = observation["known_folder_error_code"]
        path_state = observation["known_folder_path_state"]
        package_state = observation["package_identity"]
        package_error_code = observation["package_identity_error_code"]
        if (
            path is not None and (not isinstance(path, str) or not path)
            or error is not None and not isinstance(error, str)
            or error_code is not None
            and (type(error_code) is not int or error_code < 0)
            or not isinstance(path_state, str)
            or path_state not in {
                "not_defined", "directory", "not_directory", "not_found",
                "path_not_found", "access_denied", "other_error",
            }
            or not isinstance(package_state, str)
            or package_state not in {"not_checked", "present", "no_package", "other_error"}
            or package_error_code is not None
            and (type(package_error_code) is not int or package_error_code < 0)
        ):
            return {"complete": False}
        if error is None:
            safe_error = "none"
        elif error in _RUNTIME_PROBE_ERROR_TYPES:
            safe_error = error
        else:
            safe_error = "other"
        if error_code is not None and error_code > 65535:
            error_code = None
        if package_error_code is not None and package_error_code > 65535:
            package_error_code = None
        return {
            "complete": True,
            "query_ok": isinstance(path, str) and safe_error == "none",
            "matches_profile_api": (
                isinstance(path, str)
                and ntpath.normcase(ntpath.normpath(path))
                == ntpath.normcase(ntpath.normpath(profile_api_path))
            ),
            "relation": (
                TestWindowsAppContainer._profile_path_relation(path, profile_api_path)
                if isinstance(path, str) else "unavailable"
            ),
            "path_state": path_state,
            "error": safe_error,
            "error_code": error_code,
            "package_identity": package_state,
            "package_error_code": package_error_code,
        }

    @staticmethod
    def _summarize_runtime_image_probe(
        host_observation: object, container_observation: object,
    ) -> dict[str, object]:
        """Return path-free read|image states using fixed labels and DWORD errors."""
        labels = (
            "source_python", "source_core", "staged_python", "staged_core",
        )
        expected_fields = {
            "opened", "read_ok", "section_created", "view_mapped", "cleanup_ok",
            "open_error", "read_error", "section_error", "view_error",
        }
        if (
            not isinstance(host_observation, dict)
            or not isinstance(container_observation, dict)
            or set(host_observation) != set(labels)
            or set(container_observation) != set(labels)
        ):
            return {"complete": False}

        def classify(value: object) -> tuple[str, bool] | None:
            if not isinstance(value, dict) or set(value) != expected_fields:
                return None
            for name in (
                "opened", "read_ok", "section_created", "view_mapped", "cleanup_ok",
            ):
                if type(value[name]) is not bool:
                    return None
            for name in ("open_error", "read_error", "section_error", "view_error"):
                code = value[name]
                if code is not None and (type(code) is not int or not 0 <= code <= 0xFFFFFFFF):
                    return None
            if value["opened"] != (value["open_error"] is None):
                return None
            if not value["opened"]:
                if any(value[name] for name in (
                    "read_ok", "section_created", "view_mapped",
                )):
                    return None
                if any(value[name] is not None for name in (
                    "read_error", "section_error", "view_error",
                )):
                    return None
            elif value["read_ok"] != (value["read_error"] is None):
                return None
            elif value["section_created"] != (value["section_error"] is None):
                return None
            elif not value["section_created"]:
                if value["view_mapped"] or value["view_error"] is not None:
                    return None
            elif value["view_mapped"] != (value["view_error"] is None):
                return None
            if value["view_mapped"]:
                image_state = "ok"
            elif not value["opened"]:
                image_state = f"open{value['open_error']}"
            elif not value["section_created"]:
                image_state = f"section{value['section_error']}"
            else:
                image_state = f"view{value['view_error']}"
            if value["read_ok"]:
                read_state = "ok"
            elif not value["opened"]:
                read_state = "na"
            else:
                read_state = f"e{value['read_error']}"
            return f"{read_state}|{image_state}", value["cleanup_ok"]

        summary: dict[str, object] = {"complete": True}
        cleanup_results: list[bool] = []
        for prefix, observation in (
            ("host", host_observation), ("container", container_observation),
        ):
            for label in labels:
                classified = classify(observation[label])
                if classified is None:
                    return {"complete": False}
                state, cleanup_ok = classified
                summary[f"{prefix}_{label}"] = state
                cleanup_results.append(cleanup_ok)
        summary["cleanup_ok"] = all(cleanup_results)
        return summary

    @staticmethod
    def _summarize_staged_tempfile(
        observation: object, environment: object,
    ) -> dict[str, object]:
        """Publish tempfile behavior without disclosing any observed path."""
        if (
            not isinstance(observation, dict)
            or not isinstance(environment, dict)
            or not all(name in environment for name in ("LOCALAPPDATA", "TEMP", "TMP"))
            or not isinstance(observation.get("cwd"), str)
            or not observation["cwd"]
        ):
            return {"complete": False}

        tempdir = observation.get("tempdir")
        if tempdir is not None and (not isinstance(tempdir, str) or not tempdir):
            return {"complete": False}

        def environment_value(name: str) -> str | None:
            item = environment.get(name)
            if not isinstance(item, dict):
                return None
            value = item.get("python_value")
            return value if isinstance(value, str) and value else None

        def same_path(left: str | None, right: str | None) -> bool:
            return bool(left and right) and (
                ntpath.normcase(ntpath.normpath(left))
                == ntpath.normcase(ntpath.normpath(right))
            )

        def within_path(path: str | None, parent: str) -> bool:
            if not path:
                return False
            try:
                return ntpath.normcase(ntpath.commonpath([path, parent])) == (
                    ntpath.normcase(ntpath.normpath(parent))
                )
            except ValueError:
                return False

        temp_value = environment_value("TEMP")
        tmp_value = environment_value("TMP")
        matches_temp = same_path(tempdir, temp_value)
        matches_tmp = same_path(tempdir, tmp_value)
        within_workspace = within_path(tempdir, observation["cwd"])
        if tempdir is None:
            source = "unavailable"
        elif matches_temp:
            source = "temp"
        elif matches_tmp:
            source = "tmp"
        elif within_workspace:
            source = "workspace"
        else:
            source = "other"

        error_type = observation.get("error_type")
        if error_type is None:
            error = "none"
        elif isinstance(error_type, str) and error_type in _RUNTIME_PROBE_ERROR_TYPES:
            error = error_type
        else:
            error = "other"
        return {
            "complete": True,
            "source": source,
            "matches_temp": matches_temp,
            "matches_tmp": matches_tmp,
            "within_workspace": within_workspace,
            "created": observation.get("created") is True,
            "deleted": observation.get("deleted") is True,
            "error": error,
        }

    @staticmethod
    def _decode_cmd_unicode_output(contents: bytes) -> str:
        if contents.startswith(b"\xff\xfe"):
            contents = contents[2:]
        return contents.decode("utf-16-le")

    @staticmethod
    def _append_expected_profile_path(block: str, name: str, value: str) -> str:
        updated = _append_windows_environment_value(block, name, value)
        if name.casefold() == "localappdata":
            # Test-only alias enables an in-process comparison without logging either path.
            updated = _append_windows_environment_value(
                updated, "ICODE_EXPECTED_LOCALAPPDATA", value,
            )
        return updated

    def test_CMD退出码探针要求命名字段避免数字被解析成重定向(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-cmd-status-") as raw:
            status = Path(raw) / "status.txt"
            status.write_text("exit_code=7", encoding="ascii")
            self.assertEqual(self._read_cmd_exit_status(status), 7)
            status.write_text("7", encoding="ascii")
            self.assertIsNone(self._read_cmd_exit_status(status))

    def test_CMDUnicode输出解析支持有无BOM且拒绝损坏文本(self) -> None:
        expected = "LOCALAPPDATA=C:\\Users\\runner\\AppData\\Local\\Packages\\icode\\AC\r\n"
        encoded = expected.encode("utf-16-le")
        self.assertEqual(self._decode_cmd_unicode_output(encoded), expected)
        self.assertEqual(
            self._decode_cmd_unicode_output(b"\xff\xfe" + encoded), expected,
        )
        with self.assertRaises(UnicodeDecodeError):
            self._decode_cmd_unicode_output(b"\x00")

    def test_profile环境路径诊断要求唯一键值并与API路径匹配(self) -> None:
        profile_line = r"LOCALAPPDATA=C:\Users\runner\AppData\Local\Packages\icode\AC"
        self.assertEqual(self._profile_env_values([profile_line]), [
            r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        ])
        self.assertTrue(self._profile_env_matches_api(
            [profile_line],
            ["c:\\users\\RUNNER\\AppData\\Local\\Packages\\icode\\AC\\"],
        ))
        self.assertFalse(self._profile_env_matches_api(
            [r"LOCALAPPDATA=C:\Users\runner\AppData\Local\Packages\other\AC"],
            [r"C:\Users\runner\AppData\Local\Packages\icode\AC"],
        ))
        self.assertFalse(self._profile_env_matches_api(
            [r"LOCALAPPDATA=C:\one", r"LOCALAPPDATA=C:\two"], [r"C:\one"],
        ))
        self.assertTrue(self._profile_env_matches_api(
            [r"LOCALAPPDATA=C:\profile\AC\Temp"], ["C:\\profile\\AC\\Temp\\"],
        ))

    def test_profile路径关系只返回脱敏子目录类别(self) -> None:
        expected = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        self.assertEqual(self._profile_path_relation(expected + "\\", expected), "exact")
        self.assertEqual(
            self._profile_path_relation(expected + r"\Temp", expected), "api_child_temp",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Local", expected), "api_child_local",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\LocalState", expected),
            "api_child_local_state",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Private", expected), "api_child_other",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Temp\Nested", expected),
            "api_child_temp_nested",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Local\Nested", expected),
            "api_child_local_nested",
        )
        self.assertEqual(
            self._profile_path_relation(expected + r"\Private\Nested", expected),
            "api_child_other_nested",
        )
        self.assertEqual(
            self._profile_path_relation(ntpath.dirname(expected), expected), "api_parent",
        )
        self.assertEqual(
            self._profile_path_relation(ntpath.dirname(expected) + r"\AC2", expected),
            "sibling",
        )
        self.assertEqual(self._profile_path_relation(r"D:\Other", expected), "other")
        self.assertEqual(self._profile_path_relation("relative", expected), "invalid")

    def test_staged_Python_profileAPI摘要只发布身份与路径关系(self) -> None:
        summarize = getattr(self, "_summarize_staged_profile_api", None)
        self.assertTrue(
            callable(summarize),
            "profile API probe needs a dedicated path-free summary",
        )
        api_profile = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        actual_environment = api_profile + r"\Unknown\Nested"
        summary = summarize(
            {
                "token_is_appcontainer": True,
                "token_sid_defined": True,
                "profile_path": api_profile,
                "profile_error": None,
                "profile_error_code": None,
                "profile_path_state": "directory",
                "environment_block_scan_complete": True,
                "environment_block_error": None,
                "environment_block_localappdata": [actual_environment],
                "python_localappdata": actual_environment,
                "win32_localappdata": actual_environment,
            },
            api_profile,
        )

        self.assertEqual(
            summary,
            {
                "complete": True,
                "token_is_appcontainer": True,
                "token_sid_defined": True,
                "profile_api_ok": True,
                "profile_api_matches_host": True,
                "profile_api_relation": "exact",
                "profile_path_state": "directory",
                "environment_block_scan_complete": True,
                "environment_block_error": "none",
                "environment_entry_count": 1,
                "environment_block_matches_api": False,
                "python_win32_match": True,
                "environment_matches_api": False,
                "environment_relation": "api_child_other_nested",
                "error": "none",
                "error_code": None,
            },
        )
        serialized = json.dumps(summary, ensure_ascii=True)
        self.assertNotIn("C:\\Users\\runner", serialized)
        self.assertNotIn("S-1-15-2", serialized)
        self.assertLessEqual(
            len(json.dumps(summary, ensure_ascii=True, separators=(",", ":"))), 500,
        )
        self.assertEqual(summarize({}, api_profile), {"complete": False})

    def test_AppContainer_known_folder摘要只返回关系状态和错误码(self) -> None:
        summarize = getattr(self, "_summarize_known_folder_observation", None)
        self.assertTrue(callable(summarize), "known-folder probe needs a safe summary")
        api_profile = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        summary = summarize(
            {
                "known_folder_path": api_profile,
                "known_folder_error": None,
                "known_folder_error_code": None,
                "known_folder_path_state": "directory",
                "package_identity": "no_package",
                "package_identity_error_code": 15700,
            },
            api_profile,
        )

        self.assertEqual(
            summary,
            {
                "complete": True,
                "query_ok": True,
                "matches_profile_api": True,
                "relation": "exact",
                "path_state": "directory",
                "error": "none",
                "error_code": None,
                "package_identity": "no_package",
                "package_error_code": 15700,
            },
        )
        serialized = json.dumps(summary, ensure_ascii=True, separators=(",", ":"))
        self.assertNotIn("C:\\Users\\runner", serialized)
        self.assertNotIn("S-1-15-2", serialized)
        self.assertLessEqual(len(serialized), 500)
        invalid_context = {
            "known_folder_path": api_profile,
            "known_folder_error": None,
            "known_folder_error_code": None,
            "known_folder_path_state": [],
            "package_identity": [],
            "package_identity_error_code": None,
        }
        self.assertEqual(summarize(invalid_context, api_profile), {"complete": False})
        self.assertEqual(summarize({}, api_profile), {"complete": False})

    def test_LOCALAPPDATA环境A_B摘要只输出脱敏比较(self) -> None:
        summarize = getattr(self, "_summarize_localappdata_environment_ab", None)
        self.assertTrue(callable(summarize), "profile env A/B needs a safe summary")
        api_profile = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        summary = summarize(
            {
                "launch_ok": True,
                "exit_code": 0,
                "localappdata": api_profile,
                "expected_localappdata": api_profile,
            },
            {
                "launch_ok": True,
                "exit_code": 0,
                "cleanup_ok": True,
                "localappdata": api_profile + r"\Unknown\Nested",
                "expected_localappdata": api_profile,
            },
            api_profile,
        )

        self.assertEqual(
            summary,
            {
                "complete": True,
                "host_launch_ok": True,
                "host_exit_ok": True,
                "host_matches_supplied": True,
                "host_sentinel_matches_supplied": True,
                "appcontainer_launch_ok": True,
                "appcontainer_exit_ok": True,
                "appcontainer_cleanup_ok": True,
                "appcontainer_matches_supplied": False,
                "appcontainer_sentinel_matches_supplied": True,
                "appcontainer_profile_relation": "api_child_other_nested",
            },
        )
        serialized = json.dumps(summary, ensure_ascii=True)
        self.assertNotIn("C:\\Users\\runner", serialized)
        self.assertLessEqual(
            len(json.dumps(summary, ensure_ascii=True, separators=(",", ":"))), 500,
        )
        self.assertEqual(
            summarize({}, {}, api_profile), {"complete": False},
        )

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_宿主与AppContainer接收相同显式LOCALAPPDATA(self) -> None:
        """Observe explicit profile input in both launch contexts without logging paths."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        command = system_root / "System32" / "cmd.exe"
        profile_paths: list[str] = []

        def record_profile_path(
            sid: ctypes.c_void_p,
            userenv: ctypes.WinDLL,
            advapi: ctypes.WinDLL,
            kernel: ctypes.WinDLL,
            ole32: ctypes.WinDLL,
        ) -> str:
            path = _get_appcontainer_localappdata_path(
                sid, userenv, advapi, kernel, ole32,
            )
            profile_paths.append(path)
            return path

        def read_environment(path: Path) -> dict[str, str | None]:
            lines = self._decode_cmd_unicode_output(path.read_bytes()).splitlines()
            parsed: dict[str, str | None] = {}
            for name in ("LOCALAPPDATA", "ICODE_EXPECTED_LOCALAPPDATA"):
                prefix = name.casefold() + "="
                values = [
                    line.split("=", 1)[1] for line in lines
                    if line.casefold().startswith(prefix)
                ]
                parsed[name.casefold()] = values[0] if len(values) == 1 else None
            return parsed

        with tempfile.TemporaryDirectory(prefix="icode-localappdata-ab-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            script = workspace / "environment.cmd"
            app_output = workspace / "appcontainer-environment.txt"
            host_output = workspace / "host-environment.txt"
            script.write_text(
                "@echo off\r\n"
                'set LOCALAPPDATA > "appcontainer-environment.txt"\r\n'
                'set ICODE_EXPECTED_LOCALAPPDATA >> "appcontainer-environment.txt"\r\n',
                encoding="ascii",
            )
            with mock.patch(
                "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                side_effect=record_profile_path,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=self._append_expected_profile_path,
            ):
                app_result = run_windows_appcontainer(
                    [str(command), "/u", "/d", "/c", f".\\{script.name}"],
                    cwd=workspace, timeout_seconds=10, process_limit=2,
                )

            self.assertEqual(len(profile_paths), 1, "one API profile path should be captured")
            supplied_profile = profile_paths[0]
            host_environment_block = _build_windows_environment_block(
                command, workspace, system_root,
            )
            host_environment = {
                entry.split("=", 1)[0]: entry.split("=", 1)[1]
                for entry in host_environment_block.split("\0") if entry
                and not entry.startswith("=") and "=" in entry
            }
            host_environment["LOCALAPPDATA"] = supplied_profile
            host_environment["ICODE_EXPECTED_LOCALAPPDATA"] = supplied_profile
            host_script = workspace / "host-environment.cmd"
            host_script.write_text(
                "@echo off\r\n"
                'set LOCALAPPDATA > "host-environment.txt"\r\n'
                'set ICODE_EXPECTED_LOCALAPPDATA >> "host-environment.txt"\r\n',
                encoding="ascii",
            )
            host_launch_ok = True
            try:
                host_result = subprocess.run(
                    [str(command), "/u", "/d", "/c", f".\\{host_script.name}"],
                    cwd=workspace, env=host_environment, capture_output=True,
                    timeout=10, check=False, shell=False,
                )
                host_exit_code = host_result.returncode
            except subprocess.TimeoutExpired:
                host_launch_ok = False
                host_exit_code = None
            except OSError:
                host_launch_ok = False
                host_exit_code = None
            try:
                app_values = read_environment(app_output)
            except (OSError, UnicodeDecodeError):
                app_values = {"localappdata": None, "icode_expected_localappdata": None}
            try:
                host_values = read_environment(host_output)
            except (OSError, UnicodeDecodeError):
                host_values = {"localappdata": None, "icode_expected_localappdata": None}

        summary = self._summarize_localappdata_environment_ab(
            {
                "launch_ok": host_launch_ok,
                "exit_code": host_exit_code,
                "localappdata": host_values["localappdata"],
                "expected_localappdata": host_values["icode_expected_localappdata"],
            },
            {
                "launch_ok": app_result.executed,
                "exit_code": app_result.exit_code,
                "cleanup_ok": app_result.cleanup_ok,
                "localappdata": app_values["localappdata"],
                "expected_localappdata": app_values["icode_expected_localappdata"],
            },
            supplied_profile,
        )
        self._workflow_json_notice("explicit LOCALAPPDATA host/AppContainer A/B", summary)
        self.assertTrue(summary.get("complete"), "A/B environment summary is incomplete")
        self.assertTrue(summary["host_launch_ok"], "host explicit-environment control did not launch")
        self.assertTrue(summary["host_exit_ok"], "host explicit-environment positive control failed")
        self.assertTrue(summary["host_matches_supplied"], "host changed explicit LOCALAPPDATA")
        self.assertTrue(
            summary["host_sentinel_matches_supplied"],
            "host control did not receive the matching sentinel",
        )
        self.assertTrue(summary["appcontainer_launch_ok"], "AppContainer command did not launch")
        self.assertTrue(summary["appcontainer_exit_ok"], "AppContainer environment script failed")
        self.assertTrue(summary["appcontainer_cleanup_ok"], "AppContainer job cleanup failed")
        self.assertLessEqual(
            len(json.dumps(summary, separators=(",", ":"))), 500,
            "A/B workflow notice exceeds the compact notice limit",
        )

    def test_staged_Python环境观测摘要脱敏并区分API路径(self) -> None:
        api_profile = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        workspace = r"D:\a\_temp\task"
        summary = self._summarize_staged_environment(
            {
                "LOCALAPPDATA": {
                    "python_value": api_profile + r"\Unknown\Nested",
                    "win32_value": api_profile + r"\Unknown\Nested",
                    "path_state": "path_not_found",
                },
                "TEMP": {
                    "python_value": workspace,
                    "win32_value": workspace,
                    "path_state": "directory",
                },
                "TMP": {
                    "python_value": workspace,
                    "win32_value": workspace,
                    "path_state": "directory",
                },
            },
            api_profile,
        )

        self.assertEqual(
            summary,
            {
                "complete": True,
                "localappdata": {
                    "python_defined": True,
                    "win32_defined": True,
                    "python_win32_match": True,
                    "api_match": False,
                    "path_state": "path_not_found",
                },
                "temp": {
                    "python_defined": True,
                    "win32_defined": True,
                    "python_win32_match": True,
                    "path_state": "directory",
                },
                "tmp": {
                    "python_defined": True,
                    "win32_defined": True,
                    "python_win32_match": True,
                    "path_state": "directory",
                },
            },
        )
        serialized = json.dumps(summary, ensure_ascii=True)
        self.assertNotIn("C:\\Users\\runner", serialized)
        self.assertNotIn("D:\\a\\_temp", serialized)
        compact_notice = json.dumps(summary, ensure_ascii=True, separators=(",", ":"))
        self.assertLessEqual(len(compact_notice), 500)
        self.assertEqual(self._summarize_staged_environment({"TEMP": {}}, api_profile), {
            "complete": False,
        })
        self.assertEqual(self._summarize_staged_environment(
            {
                "LOCALAPPDATA": {},
                "TEMP": {},
                "TMP": {},
            },
            None,
        ), {"complete": False})

    def test_staged_Python_tempfile观测摘要脱敏并区分目录来源(self) -> None:
        workspace = r"D:\a\_temp\task"
        temp_dir = workspace + r"\nested-temp"
        environment = {
            "LOCALAPPDATA": {
                "python_value": r"C:\Users\runner\AppData\Local\Packages\icode\AC",
                "win32_value": r"C:\Users\runner\AppData\Local\Packages\icode\AC",
                "path_state": "not_found",
            },
            "TEMP": {
                "python_value": r"C:\Users\runner\AppData\Local\Temp",
                "win32_value": r"C:\Users\runner\AppData\Local\Temp",
                "path_state": "not_found",
            },
            "TMP": {
                "python_value": r"C:\Users\runner\AppData\Local\Temp",
                "win32_value": r"C:\Users\runner\AppData\Local\Temp",
                "path_state": "not_found",
            },
        }

        summary = self._summarize_staged_tempfile(
            {
                "tempdir": temp_dir,
                "cwd": workspace,
                "created": True,
                "deleted": True,
                "error_type": None,
                "error_text": r"D:\private\must-not-escape",
            },
            environment,
        )

        self.assertEqual(
            summary,
            {
                "complete": True,
                "source": "workspace",
                "matches_temp": False,
                "matches_tmp": False,
                "within_workspace": True,
                "created": True,
                "deleted": True,
                "error": "none",
            },
        )
        serialized = json.dumps(summary, ensure_ascii=True, separators=(",", ":"))
        self.assertNotIn("D:\\a\\_temp", serialized)
        self.assertNotIn("D:\\private", serialized)
        self.assertLessEqual(len(serialized), 500)

        failed = self._summarize_staged_tempfile(
            {
                "tempdir": None,
                "cwd": workspace,
                "created": False,
                "deleted": False,
                "error_type": "PermissionError",
            },
            environment,
        )
        self.assertEqual(failed["source"], "unavailable")
        self.assertEqual(failed["error"], "PermissionError")
        self.assertFalse(failed["created"])
        profile_temp = self._summarize_staged_tempfile(
            {
                "tempdir": r"C:\Users\runner\AppData\Local\Packages\icode\AC\Temp",
                "cwd": workspace,
                "created": True,
                "deleted": True,
                "error_type": None,
            },
            environment,
        )
        self.assertEqual(profile_temp["source"], "other")
        self.assertFalse(profile_temp["within_workspace"])
        self.assertEqual(
            self._summarize_staged_tempfile({}, environment),
            {"complete": False},
        )

    def test_profile_api_token_calls_bind_Advapi32(self) -> None:
        self.assertIn("advapi.OpenProcessToken.argtypes", _STAGED_PYTHON_PROFILE_API_PROBE)
        self.assertIn("advapi.GetTokenInformation.argtypes", _STAGED_PYTHON_PROFILE_API_PROBE)
        self.assertNotIn("kernel.OpenProcessToken", _STAGED_PYTHON_PROFILE_API_PROBE)
        self.assertNotIn("kernel.GetTokenInformation", _STAGED_PYTHON_PROFILE_API_PROBE)

    def test_known_folder_and_package_identity_APIs_have_explicit_signatures(self) -> None:
        self.assertIn("shell32.SHGetKnownFolderPath.argtypes", _STAGED_PYTHON_KNOWN_FOLDER_PROBE)
        self.assertIn("shell32.SHGetKnownFolderPath.restype", _STAGED_PYTHON_KNOWN_FOLDER_PROBE)
        self.assertIn("kernel32.GetCurrentPackageFullName.argtypes", _STAGED_PYTHON_KNOWN_FOLDER_PROBE)
        self.assertIn("kernel32.GetCurrentPackageFullName.restype", _STAGED_PYTHON_KNOWN_FOLDER_PROBE)
        self.assertIn("0x00004000", _STAGED_PYTHON_KNOWN_FOLDER_PROBE)

    def test_runtime映像探针Win32签名固定且只读不执行(self) -> None:
        probe = globals().get("_STAGED_PYTHON_RUNTIME_IMAGE_PROBE")
        self.assertIsInstance(probe, str, "runtime image probe is missing")
        self.assertIn("CreateFileW.argtypes", probe)
        self.assertIn("ReadFile.argtypes", probe)
        self.assertIn("CreateFileMappingW.argtypes", probe)
        self.assertIn("MapViewOfFile.argtypes", probe)
        self.assertIn("UnmapViewOfFile.argtypes", probe)
        self.assertIn("0x11000002", probe)
        self.assertIn("0x00000004", probe)
        self.assertNotIn("LoadLibrary", probe)
        self.assertNotIn("FILE_MAP_EXECUTE", probe)

    def test_runtime映像探针摘要只公开固定阶段和错误码(self) -> None:
        summarize = getattr(self, "_summarize_runtime_image_probe", None)
        self.assertTrue(callable(summarize), "runtime image probe needs a safe summary")

        def result(
            *, opened: bool = True, section: bool = True, view: bool = True,
            cleanup: bool = True, open_error: int | None = None,
            read: bool | None = None, read_error: int | None = None,
            section_error: int | None = None, view_error: int | None = None,
        ) -> dict[str, object]:
            if read is None:
                read = opened
            return {
                "opened": opened,
                "read_ok": read,
                "section_created": section,
                "view_mapped": view,
                "cleanup_ok": cleanup,
                "open_error": open_error,
                "read_error": read_error,
                "section_error": section_error,
                "view_error": view_error,
            }

        host = {
            key: result() for key in (
                "source_python", "source_core", "staged_python", "staged_core",
            )
        }
        container = dict(host)
        container["source_core"] = result(
            opened=False, section=False, view=False, open_error=5, read=False,
        )
        container["staged_core"] = result(read=False, read_error=5)
        summary = summarize(host, container)
        self.assertEqual(
            summary,
            {
                "complete": True,
                "host_source_python": "ok|ok",
                "host_source_core": "ok|ok",
                "host_staged_python": "ok|ok",
                "host_staged_core": "ok|ok",
                "container_source_python": "ok|ok",
                "container_source_core": "na|open5",
                "container_staged_python": "ok|ok",
                "container_staged_core": "e5|ok",
                "cleanup_ok": True,
            },
        )
        serialized = json.dumps(summary, ensure_ascii=True, separators=(",", ":"))
        self.assertNotIn("C:\\Users\\runner", serialized)
        self.assertLessEqual(len(serialized), 500)
        notice = {
            "host_exit": 0,
            "host_error": "none",
            "observation": summary,
        }
        self.assertLessEqual(
            len(json.dumps(notice, ensure_ascii=True, separators=(",", ":"))),
            500,
        )
        max_failure = result(
            opened=False, read=False, section=False, view=False,
            open_error=0xFFFFFFFF,
        )
        worst_case = summarize(
            {label: max_failure for label in (
                "source_python", "source_core", "staged_python", "staged_core",
            )},
            {label: max_failure for label in (
                "source_python", "source_core", "staged_python", "staged_core",
            )},
        )
        self.assertLessEqual(
            len(json.dumps(
                {"host_exit": 0, "host_error": "none", "observation": worst_case},
                ensure_ascii=True, separators=(",", ":"),
            )),
            500,
        )
        malformed = dict(container)
        malformed["source_core"] = result(opened=False, section=True, view=False)
        self.assertEqual(summarize(host, malformed), {"complete": False})
        oversized = dict(container)
        oversized["source_core"] = result(
            opened=False, section=False, view=False, open_error=0x100000000,
            read=False,
        )
        self.assertEqual(summarize(host, oversized), {"complete": False})

    def test_staged_Python环境探针片段可独立解析(self) -> None:
        compile(
            _STAGED_PYTHON_ENVIRONMENT_PROBE,
            "<staged-python-environment-probe>",
            "exec",
        )
        compile(
            _STAGED_PYTHON_PROFILE_API_PROBE,
            "<staged-python-profile-api-probe>",
            "exec",
        )
        compile(
            _STAGED_PYTHON_KNOWN_FOLDER_PROBE,
            "<staged-python-known-folder-probe>",
            "exec",
        )
        image_probe = globals().get("_STAGED_PYTHON_RUNTIME_IMAGE_PROBE")
        self.assertIsInstance(image_probe, str, "runtime image probe is missing")
        compile(image_probe, "<staged-python-runtime-image-probe>", "exec")
        compile(
            _STAGED_PYTHON_TEMPFILE_PROBE,
            "<staged-python-tempfile-probe>",
            "exec",
        )
        compile(
            "import ctypes, os, stat\n"
            + _STAGED_PYTHON_ENVIRONMENT_PROBE
            + _STAGED_PYTHON_PROFILE_API_PROBE
            + _STAGED_PYTHON_KNOWN_FOLDER_PROBE
            + image_probe
            + _STAGED_PYTHON_TEMPFILE_PROBE,
            "<staged-python-profile-environment-combined-probe>",
            "exec",
        )

    def test_profile环境诊断alias只复制API路径且不输出路径(self) -> None:
        expected = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        block = self._append_expected_profile_path("\0\0", "LOCALAPPDATA", expected)
        values = {
            entry.split("=", 1)[0].casefold(): entry.split("=", 1)[1]
            for entry in block.split("\0") if entry and "=" in entry
        }
        self.assertEqual(values.get("localappdata"), expected)
        self.assertEqual(values.get("icode_expected_localappdata"), expected)
        self.assertEqual(len(values), 2)

    def _mock_profile_apis(self) -> dict[str, mock.Mock]:
        import ctypes

        apis = {name: mock.Mock() for name in ("userenv", "kernel32", "advapi32", "ole32")}

        def create_profile(*args: object) -> int:
            sid_output = args[-1]
            ctypes.cast(sid_output, ctypes.POINTER(ctypes.c_void_p)).contents.value = 123
            return 0

        apis["userenv"].CreateAppContainerProfile.side_effect = create_profile
        apis["userenv"].DeleteAppContainerProfile.return_value = 0
        apis["advapi32"].IsValidSid.return_value = True
        apis["advapi32"].GetLengthSid.return_value = 12
        return apis

    def test_workspace目录拒绝链接与硬链接(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-paths-") as raw:
            root = Path(raw)
            target = root / "outside.txt"
            target.write_text("outside", encoding="utf-8")
            workspace = root / "task"
            workspace.mkdir()
            try:
                (workspace / "link.txt").symlink_to(target)
            except OSError:
                pass  # Windows without developer mode may deny symlink creation.
            else:
                with self.assertRaises(_AppContainerSetupError) as caught:
                    _walk_workspace(workspace)
                self.assertIn("类别=symbolic_link", caught.exception.detail)

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-hardlinks-") as raw:
            root = Path(raw)
            source = root / "outside.txt"
            source.write_text("outside", encoding="utf-8")
            workspace = root / "task"
            workspace.mkdir()
            try:
                os.link(source, workspace / "linked.txt")
            except OSError as exc:
                self.skipTest(f"文件系统不支持硬链接测试：{exc}")
            with self.assertRaises(_AppContainerSetupError):
                _walk_workspace(workspace)

    def test_runtime_ACL目录扫描支持对象数和时限上限(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-tree-limit-") as raw:
            root = Path(raw)
            (root / "python.dll").write_bytes(b"runtime")
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._walk_workspace(root, max_entries=1)
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._walk_workspace(
                    root, deadline=time.monotonic() - 1,
                )

    def test_runtime根校验去重并拒绝覆盖工作区的目录(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-roots-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            workspace = parent / "task"
            workspace.mkdir()

            roots = windows_appcontainer._validate_runtime_roots(
                (runtime, runtime.resolve()), workspace=workspace,
            )

            self.assertEqual(roots, (runtime.resolve(),))
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._validate_runtime_roots(
                    (parent,), workspace=workspace,
                )

    def test_runtime根校验拒绝嵌套授权根和用户目录根(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-roots-overlap-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            nested = runtime / "Lib"
            nested.mkdir(parents=True)
            workspace = parent / "task"
            workspace.mkdir()

            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._validate_runtime_roots(
                    (runtime, nested), workspace=workspace,
                )
            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._validate_runtime_roots(
                    (Path.home(),), workspace=workspace,
                )

    def test_runtime根校验拒绝指向外部目录的符号链接(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-root-link-") as raw:
            parent = Path(raw)
            actual = parent / "python"
            actual.mkdir()
            workspace = parent / "task"
            workspace.mkdir()
            link = parent / "python-alias"
            try:
                link.symlink_to(actual, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"文件系统不支持符号链接测试：{exc}")

            with self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._validate_runtime_roots(
                    (link,), workspace=workspace,
                )

    def test_runtime树ACL快照以脱敏类别拒绝符号链接(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-tree-link-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            workspace = parent / "task"
            workspace.mkdir()
            outside = parent / "outside.dll"
            outside.write_bytes(b"outside")
            try:
                (runtime / "python.dll").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"文件系统不支持符号链接测试：{exc}")

            with self.assertRaises(_AppContainerSetupError) as caught:
                windows_appcontainer._snapshot_runtime_acl_roots(
                    (runtime,), workspace=workspace, advapi=object(), kernel=object(),
                )

        self.assertEqual(caught.exception.error, "unsupported_runtime_root")
        self.assertIn("symbolic_link", caught.exception.detail)
        self.assertNotIn(str(parent), caught.exception.detail)

    def test_runtime_ACL快照枚举完整树并拒绝受保护DACL(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-snapshot-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            sample = runtime / "python.dll"
            sample.write_bytes(b"runtime")
            workspace = parent / "task"
            workspace.mkdir()

            def read_state(path: Path, _advapi: object, _kernel: object):
                info = path.lstat()
                return windows_appcontainer._DaclSnapshot(
                    path=path, dacl=b"original-dacl", control=0, revision=1,
                    present=True, defaulted=False,
                    file_identity=(int(info.st_dev), int(info.st_ino)),
                )

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ):
                snapshot = windows_appcontainer._snapshot_runtime_acl_roots(
                    (runtime,), workspace=workspace, advapi=object(), kernel=object(),
                )
            self.assertEqual(
                {item.path for item in snapshot.entries},
                {runtime.resolve(strict=True), sample.resolve(strict=True)},
            )

            def read_protected_state(path: Path, _advapi: object, _kernel: object):
                state = read_state(path, _advapi, _kernel)
                if path.resolve(strict=True) == sample.resolve(strict=True):
                    return windows_appcontainer._DaclSnapshot(
                        path=path, dacl=state.dacl,
                        control=windows_appcontainer._SE_DACL_PROTECTED, revision=1,
                        present=True, defaulted=False,
                        file_identity=state.file_identity,
                    )
                return state

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_protected_state,
            ), self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._snapshot_runtime_acl_roots(
                    (runtime,), workspace=workspace, advapi=object(), kernel=object(),
                )

    def test_runtime_ACL预检失败回执保留脱敏拒绝原因(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-reason-") as raw:
            parent = Path(raw)
            runtime = parent / "python"
            runtime.mkdir()
            workspace = parent / "task"
            workspace.mkdir()
            with mock.patch.object(
                windows_appcontainer, "_walk_workspace",
                side_effect=_AppContainerSetupError(
                    "unsupported_workspace_entry", "任务目录含硬链接，AppContainer 拒绝启动",
                ),
            ), self.assertRaises(_AppContainerSetupError) as caught:
                windows_appcontainer._snapshot_runtime_acl_roots(
                    (runtime,), workspace=workspace, advapi=object(), kernel=object(),
                )

        self.assertEqual(caught.exception.error, "unsupported_runtime_root")
        self.assertIn("unsupported_workspace_entry", caught.exception.detail)
        self.assertIn("硬链接", caught.exception.detail)
        self.assertNotIn(str(runtime), caught.exception.detail)

    def test_runtime_ACL逐根只授读取执行且先记录待恢复根(self) -> None:
        import ctypes

        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-apply-") as raw:
            parent = Path(raw)
            first = parent / "python-a"
            second = parent / "python-b"
            first.mkdir()
            second.mkdir()
            workspace = parent / "task"
            workspace.mkdir()

            def read_state(path: Path, _advapi: object, _kernel: object):
                info = path.lstat()
                return windows_appcontainer._DaclSnapshot(
                    path=path, dacl=b"original-dacl", control=0, revision=1,
                    present=True, defaulted=False,
                    file_identity=(int(info.st_dev), int(info.st_ino)),
                )

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ):
                transaction = windows_appcontainer._snapshot_runtime_acl_roots(
                    (first, second), workspace=workspace,
                    advapi=object(), kernel=object(),
                )

            calls: list[tuple[Path, int]] = []

            def apply(root: Path, _sid: object, access: int, *_apis: object) -> None:
                calls.append((root, access))
                if root == transaction.roots[1]:
                    raise _AppContainerSetupError("runtime_acl_failed", "injected failure")

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ), mock.patch.object(
                windows_appcontainer, "_contains_sid", return_value=False,
            ), mock.patch.object(
                windows_appcontainer, "_add_runtime_acl", side_effect=apply,
            ), self.assertRaises(_AppContainerSetupError):
                windows_appcontainer._grant_runtime_acl_roots(
                    transaction, ctypes.c_void_p(123),
                )

            expected_access = (
                windows_appcontainer._FILE_GENERIC_READ
                | windows_appcontainer._FILE_GENERIC_EXECUTE
            )
            self.assertEqual(
                calls,
                [(transaction.roots[0], expected_access), (transaction.roots[1], expected_access)],
            )
            self.assertEqual(transaction.modified_roots, list(transaction.roots))

    def test_runtime_ACL恢复按逆序执行并要求全树状态精确匹配(self) -> None:
        import ctypes

        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-restore-") as raw:
            parent = Path(raw)
            first = parent / "python-a"
            second = parent / "python-b"
            first.mkdir()
            second.mkdir()
            workspace = parent / "task"
            workspace.mkdir()

            def read_state(path: Path, _advapi: object, _kernel: object):
                info = path.lstat()
                return windows_appcontainer._DaclSnapshot(
                    path=path, dacl=b"original-dacl", control=0, revision=1,
                    present=True, defaulted=False,
                    file_identity=(int(info.st_dev), int(info.st_ino)),
                )

            with mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ):
                transaction = windows_appcontainer._snapshot_runtime_acl_roots(
                    (first, second), workspace=workspace,
                    advapi=object(), kernel=object(),
                )
            transaction.modified_roots[:] = list(transaction.roots)
            restored: list[Path] = []

            with mock.patch.object(
                windows_appcontainer, "_set_dacl",
                side_effect=lambda path, *_args: restored.append(path),
            ), mock.patch.object(
                windows_appcontainer, "_read_dacl_state", side_effect=read_state,
            ), mock.patch.object(
                windows_appcontainer, "_contains_sid", return_value=False,
            ):
                result = windows_appcontainer._restore_runtime_acl_roots(
                    transaction, ctypes.c_void_p(123),
                )

            self.assertTrue(result)
            self.assertEqual(restored, list(reversed(transaction.roots)))
            self.assertEqual(transaction.modified_roots, [])

    def test_非_windows平台明确拒绝(self) -> None:
        if sys.platform == "win32":
            self.skipTest("仅用于验证非 Windows 拒绝路径")
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-unsupported-") as raw:
            result = run_windows_appcontainer(
                [sys.executable, "-V"], cwd=raw, timeout_seconds=2,
            )
        self.assertFalse(result.executed)
        self.assertFalse(result.cleanup_ok)
        self.assertEqual(result.error, "unsupported_platform")

    def test_lpApplicationName诊断在AppContainer外层拒绝其它命令(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-invalid-diagnostic-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable), "/all"], cwd=raw, timeout_seconds=2,
                _diagnostic_null_application_name=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_runtime_ACL诊断在GitHubActions以外被拒绝(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-gate-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {
                     "GITHUB_ACTIONS": "false", "RUNNER_OS": "Windows",
                     "ICODE_DIAGNOSTIC_RUNTIME_ACL": "true",
                 },
             ):
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
                _diagnostic_runtime_acl=True,
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        self.assertFalse(result.cleanup_ok)

    def test_runtime_ACL差分缺少专用环境开关时拒绝(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-opt-in-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {"GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows"},
                 clear=True,
             ):
            host_runtime = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
                _diagnostic_runtime_acl=True,
            )
            staged_runtime = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
                _diagnostic_runtime_acl=True,
                _diagnostic_runtime_roots=(Path(raw),),
            )

        self.assertEqual(host_runtime.error, "invalid_diagnostic_probe")
        self.assertEqual(staged_runtime.error, "invalid_diagnostic_probe")
        self.assertFalse(host_runtime.executed)
        self.assertFalse(staged_runtime.executed)
        self.assertFalse(host_runtime.cleanup_ok)
        self.assertFalse(staged_runtime.cleanup_ok)

    def test_runtime_ACL诊断在主进程前授权并在退出后恢复(self) -> None:
        apis = self._mock_profile_apis()
        transaction = windows_appcontainer._RuntimeAclTransaction(
            roots=(Path("C:/runtime"),), entries=(),
            advapi=apis["advapi32"], kernel=apis["kernel32"],
            snapshot_duration_ms=1,
        )
        job_result = WindowsJobResult(True, 0, None, True, "")
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-flow-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch.dict(
                 os.environ,
                 {
                     "GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows",
                     "ICODE_DIAGNOSTIC_RUNTIME_ACL": "true",
                 },
             ), \
             mock.patch(
                 "icode.windows_appcontainer.ctypes.WinDLL",
                 create=True,
                 side_effect=lambda name, **_kwargs: apis[name],
             ), \
             mock.patch(
                 "icode.windows_appcontainer._grant_workspace_acl",
                 return_value=(b"workspace-dacl", apis["advapi32"], apis["kernel32"]),
             ), \
             mock.patch(
                 "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                 return_value=r"C:\runner\profile\AC",
             ), \
             mock.patch(
                 "icode.windows_appcontainer._snapshot_runtime_acl_roots",
                 return_value=transaction,
             ) as snapshot, \
             mock.patch("icode.windows_appcontainer._grant_runtime_acl_roots") as grant, \
             mock.patch(
                 "icode.windows_appcontainer._restore_runtime_acl_roots", return_value=True,
             ) as restore_runtime, \
             mock.patch(
                 "icode.windows_appcontainer._restore_workspace_acl", return_value=True,
             ), mock.patch(
                 "icode.windows_appcontainer.run_windows_job", return_value=job_result,
             ) as run_job:
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
                _diagnostic_runtime_acl=True,
            )

        self.assertTrue(result.executed, result)
        self.assertTrue(result.cleanup_ok, result)
        snapshot.assert_called_once()
        self.assertEqual(
            snapshot.call_args.args[0], (Path(sys.prefix), Path(sys.base_prefix)),
        )
        grant.assert_called_once_with(transaction, apis["advapi32"].FreeSid.call_args.args[0])
        restore_runtime.assert_called_once()
        self.assertGreaterEqual(run_job.call_count, 1)

    def test_容器LOCALAPPDATA通过SID字符串查询并释放Win32内存(self) -> None:
        import ctypes

        sid_text = ctypes.create_unicode_buffer("S-1-15-2-123")
        profile_path = ctypes.create_unicode_buffer(
            r"C:\Users\runner\AppData\Local\Packages\icode\AC",
        )
        advapi = mock.Mock()
        userenv = mock.Mock()
        kernel = mock.Mock()
        ole32 = mock.Mock()

        def convert_sid(sid: object, output: object) -> int:
            self.assertEqual(getattr(sid, "value", sid), 123)
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(sid_text)
            )
            return 1

        def get_appcontainer_path(sid_string: str, output: object) -> int:
            self.assertEqual(sid_string, "S-1-15-2-123")
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(profile_path)
            )
            return 0

        advapi.ConvertSidToStringSidW.side_effect = convert_sid
        userenv.GetAppContainerFolderPath.side_effect = get_appcontainer_path
        kernel.LocalFree.return_value = None
        with mock.patch("icode.windows_appcontainer.sys.platform", "win32"):
            path = _get_appcontainer_localappdata_path(
                ctypes.c_void_p(123), userenv, advapi, kernel, ole32,
            )

        self.assertEqual(path, r"C:\Users\runner\AppData\Local\Packages\icode\AC")
        kernel.LocalFree.assert_called_once()
        ole32.CoTaskMemFree.assert_called_once()

    def test_容器LOCALAPPDATA查询失败时释放SID且不猜路径(self) -> None:
        import ctypes

        sid_text = ctypes.create_unicode_buffer("S-1-15-2-123")
        advapi = mock.Mock()
        userenv = mock.Mock()
        kernel = mock.Mock()
        ole32 = mock.Mock()

        def convert_sid(sid: object, output: object) -> int:
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(sid_text)
            )
            return 1

        advapi.ConvertSidToStringSidW.side_effect = convert_sid
        userenv.GetAppContainerFolderPath.return_value = 0x80004005
        kernel.LocalFree.return_value = None
        with self.assertRaises(_AppContainerSetupError), \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"):
            _get_appcontainer_localappdata_path(
                ctypes.c_void_p(123), userenv, advapi, kernel, ole32,
            )
        kernel.LocalFree.assert_called_once()
        ole32.CoTaskMemFree.assert_not_called()

    def test_profile删除按官方约定重试并确认profile数据目录消失(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-delete-") as raw:
            profile_path = Path(raw) / "AC"
            profile_path.mkdir()
            userenv = mock.Mock()

            def delete_profile(_profile: str) -> int:
                if userenv.DeleteAppContainerProfile.call_count == 2:
                    profile_path.rmdir()
                return 0

            userenv.DeleteAppContainerProfile.side_effect = delete_profile
            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(profile_path),
            )

        self.assertTrue(deleted, detail)
        self.assertEqual(detail, "")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_profile数据目录残留时删除验证失败(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-residue-") as raw:
            profile_path = Path(raw) / "AC"
            profile_path.mkdir()
            userenv = mock.Mock()
            userenv.DeleteAppContainerProfile.return_value = 0

            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(profile_path),
            )

        self.assertFalse(deleted)
        self.assertEqual(detail, "profile_storage_residual")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_profile删除API连续失败时即使数据目录缺失也不报成功(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-profile-delete-error-") as raw:
            absent_path = Path(raw) / "already-missing"
            userenv = mock.Mock()
            userenv.DeleteAppContainerProfile.return_value = 0x80004005

            deleted, detail = _delete_appcontainer_profile(
                "icode-test", userenv, str(absent_path),
            )

        self.assertFalse(deleted)
        self.assertEqual(detail, "profile_delete_failed:0x80004005")
        self.assertEqual(userenv.DeleteAppContainerProfile.call_count, 2)

    def test_容器路径查询失败时不启动命令且保留准确清理结果(self) -> None:
        apis = self._mock_profile_apis()
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-path-failure-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch(
                 "icode.windows_appcontainer.ctypes.WinDLL",
                 create=True,
                 side_effect=lambda name, **_kwargs: apis[name],
             ), \
             mock.patch(
                 "icode.windows_appcontainer._grant_workspace_acl",
                 return_value=(b"original-dacl", apis["advapi32"], apis["kernel32"]),
             ), \
             mock.patch(
                 "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                 side_effect=_AppContainerSetupError(
                     "appcontainer_profile_path_failed", "profile path unavailable",
                 ),
             ), \
             mock.patch("icode.windows_appcontainer._restore_workspace_acl", return_value=True), \
             mock.patch("icode.windows_appcontainer.run_windows_job") as run_job:
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
            )

        self.assertFalse(result.executed)
        self.assertEqual(result.error, "appcontainer_profile_path_failed")
        self.assertTrue(result.cleanup_ok)
        run_job.assert_not_called()
        apis["userenv"].DeleteAppContainerProfile.assert_called_once()
        apis["advapi32"].FreeSid.assert_called_once()

    def test_容器正常启动和撤权探针都只收到当前profile路径(self) -> None:
        profile_path = r"C:\Users\runner\AppData\Local\Packages\icode\AC"
        apis = self._mock_profile_apis()
        job_result = WindowsJobResult(True, 0, None, True, "")
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-profile-path-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch(
                 "icode.windows_appcontainer.ctypes.WinDLL",
                 create=True,
                 side_effect=lambda name, **_kwargs: apis[name],
             ), \
             mock.patch(
                 "icode.windows_appcontainer._grant_workspace_acl",
                 return_value=(b"original-dacl", apis["advapi32"], apis["kernel32"]),
             ), \
             mock.patch(
                 "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                 return_value=profile_path,
             ), \
             mock.patch("icode.windows_appcontainer._restore_workspace_acl", return_value=True), \
             mock.patch(
                 "icode.windows_appcontainer.run_windows_job", return_value=job_result,
             ) as run_job:
            result = run_windows_appcontainer(
                [sys.executable, "-c", "pass"], cwd=raw, timeout_seconds=2,
            )

        self.assertTrue(result.executed)
        self.assertTrue(result.cleanup_ok)
        self.assertEqual(run_job.call_count, 2, "主命令和 ACL 撤权探针都应在同一容器中运行")
        for call in run_job.call_args_list:
            self.assertEqual(call.kwargs["_appcontainer_sid"], 123)
            self.assertEqual(call.kwargs["_appcontainer_localappdata"], profile_path)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_profile专属目录可写且进程退出后删除(self) -> None:
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        command = system_root / "System32" / "cmd.exe"
        profile_paths: list[str] = []
        profile_directory_exists_before_launch: list[bool] = []
        marker_present_before_delete: list[bool] = []
        profile_actual_stat_before_delete: list[str] = []
        profile_actual_relation_before_delete: list[str] = []
        profile_actual_samefile_as_api_before_delete: list[bool] = []
        marker_name = "icode-profile-lifecycle-probe.txt"
        delete_profile = _delete_appcontainer_profile

        def get_profile_path(
            sid: ctypes.c_void_p,
            userenv: ctypes.WinDLL,
            advapi: ctypes.WinDLL,
            kernel: ctypes.WinDLL,
            ole32: ctypes.WinDLL,
        ) -> str:
            path = _get_appcontainer_localappdata_path(
                sid, userenv, advapi, kernel, ole32,
            )
            profile_paths.append(path)
            profile_directory_exists_before_launch.append(Path(path).is_dir())
            return path

        def observe_profile_delete(
            profile: str, userenv: ctypes.WinDLL, localappdata: str | None,
        ) -> tuple[bool, str]:
            marker_path = Path(localappdata or "") / marker_name
            marker_present_before_delete.append(marker_path.is_file())
            actual_stat_class = "unavailable"
            actual_path_relation = "unavailable"
            actual_samefile_as_api = False
            try:
                unicode_status = self._read_cmd_exit_status(profile_env_unicode_status)
                unicode_output = self._decode_cmd_unicode_output(
                    profile_env_unicode_value.read_bytes(),
                ).splitlines()
                actual_paths = self._profile_env_values(unicode_output)
                if unicode_status == 0 and len(actual_paths) == 1:
                    actual_stat_class = self._profile_path_stat_class(actual_paths[0])
                    if localappdata:
                        actual_path_relation = self._profile_path_relation(
                            actual_paths[0], localappdata,
                        )
                        if actual_stat_class == "directory":
                            actual_samefile_as_api = Path(actual_paths[0]).samefile(localappdata)
            except (OSError, UnicodeDecodeError, ValueError):
                pass  # Diagnostic failure must not prevent the real profile cleanup.
            profile_actual_stat_before_delete.append(actual_stat_class)
            profile_actual_relation_before_delete.append(actual_path_relation)
            profile_actual_samefile_as_api_before_delete.append(actual_samefile_as_api)
            return delete_profile(profile, userenv, localappdata)

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-profile-lifecycle-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            script = workspace / "profile-write.cmd"
            profile_env_state = workspace / "profile-env-state.txt"
            profile_env_value = workspace / "profile-env-value.txt"
            profile_env_unicode_value = workspace / "profile-env-unicode-value.txt"
            profile_env_unicode_status = workspace / "profile-env-unicode-status.txt"
            profile_env_compare = workspace / "profile-env-compare.txt"
            profile_expected_env_state = workspace / "profile-expected-env-state.txt"
            profile_directory_state = workspace / "profile-directory-state.txt"
            profile_write_status = workspace / "profile-write-status.txt"
            profile_write_stderr = workspace / "profile-write-stderr.txt"
            # The space before `>` prevents a trailing status digit being parsed as a file descriptor.
            script.write_text(
                "@echo off\r\n"
                f'if defined LOCALAPPDATA (echo defined> "{profile_env_state.name}") '
                f'else (echo missing> "{profile_env_state.name}")\r\n'
                f'set LOCALAPPDATA > "{profile_env_value.name}"\r\n'
                f'if defined ICODE_EXPECTED_LOCALAPPDATA '
                f'(echo defined> "{profile_expected_env_state.name}") '
                f'else (echo missing> "{profile_expected_env_state.name}")\r\n'
                f'cmd.exe /u /d /c "set LOCALAPPDATA" '
                f'> "{profile_env_unicode_value.name}"\r\n'
                f'echo exit_code=%errorlevel% > "{profile_env_unicode_status.name}"\r\n'
                f'if /i "%LOCALAPPDATA%"=="%ICODE_EXPECTED_LOCALAPPDATA%" '
                f'(echo match> "{profile_env_compare.name}") '
                f'else (echo mismatch> "{profile_env_compare.name}")\r\n'
                f'if exist "%LOCALAPPDATA%\\." (echo exists> "{profile_directory_state.name}") '
                f'else (echo missing> "{profile_directory_state.name}")\r\n'
                f'(echo profile-write-ok> "%LOCALAPPDATA%\\{marker_name}") '
                f'2> "{profile_write_stderr.name}"\r\n'
                f'echo exit_code=%errorlevel% > "{profile_write_status.name}"\r\n',
                encoding="utf-8",
            )
            with mock.patch(
                "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                side_effect=get_profile_path,
            ), mock.patch(
                "icode.windows_appcontainer._delete_appcontainer_profile",
                side_effect=observe_profile_delete,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=self._append_expected_profile_path,
            ):
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{script.name}"],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )
            try:
                profile_write_error = profile_write_stderr.read_text(
                    encoding="utf-8", errors="replace",
                ).casefold()
            except OSError:
                profile_write_error = ""
            if "access is denied" in profile_write_error or "access denied" in profile_write_error:
                profile_write_error_class = "access_denied"
            elif "path not found" in profile_write_error or "cannot find the path" in profile_write_error:
                profile_write_error_class = "path_not_found"
            elif "file not found" in profile_write_error or "cannot find the file" in profile_write_error:
                profile_write_error_class = "file_not_found"
            elif profile_write_error:
                profile_write_error_class = "other_write_error"
            else:
                profile_write_error_class = "no_stderr"
            profile_write_status_value = self._read_cmd_exit_status(profile_write_status)
            try:
                profile_env_defined = (
                    profile_env_state.read_text(encoding="utf-8").strip() == "defined"
                )
            except OSError:
                profile_env_defined = False
            try:
                profile_expected_env_defined = (
                    profile_expected_env_state.read_text(encoding="ascii").strip() == "defined"
                )
            except OSError:
                profile_expected_env_defined = False
            profile_env_matches_api = False
            try:
                profile_env_lines = profile_env_value.read_text(
                    encoding="utf-8", errors="replace",
                ).splitlines()
                profile_env_matches_api = self._profile_env_matches_api(
                    profile_env_lines, profile_paths,
                )
            except OSError:
                profile_env_matches_api = False
            profile_unicode_env_matches_api = False
            profile_unicode_env_matches_host = False
            profile_unicode_env_lines: list[str] = []
            profile_unicode_output_present = False
            try:
                profile_unicode_set_status = self._read_cmd_exit_status(
                    profile_env_unicode_status,
                )
            except OSError:
                profile_unicode_set_status = None
            try:
                profile_unicode_output = profile_env_unicode_value.read_bytes()
                profile_unicode_output_present = bool(profile_unicode_output)
                profile_unicode_env_lines = self._decode_cmd_unicode_output(
                    profile_unicode_output,
                ).splitlines()
                if profile_unicode_set_status == 0 and profile_unicode_env_lines:
                    profile_unicode_env_matches_api = self._profile_env_matches_api(
                        profile_unicode_env_lines, profile_paths,
                    )
            except (OSError, UnicodeDecodeError):
                profile_unicode_env_matches_api = False
            host_localappdata = os.environ.get("LOCALAPPDATA")
            host_localappdata_defined = bool(host_localappdata)
            actual_profile_paths = self._profile_env_values(profile_unicode_env_lines)
            profile_unicode_actual_value_defined = len(actual_profile_paths) == 1
            if profile_unicode_set_status == 0 and profile_unicode_env_lines and host_localappdata:
                profile_unicode_env_matches_host = self._profile_env_matches_api(
                    profile_unicode_env_lines, [host_localappdata],
                )
            try:
                profile_env_equals_api = (
                    profile_env_compare.read_text(encoding="ascii").strip() == "match"
                )
            except OSError:
                profile_env_equals_api = False
            try:
                profile_directory_visible = (
                    profile_directory_state.read_text(encoding="utf-8").strip() == "exists"
                )
            except OSError:
                profile_directory_visible = False

        self._workflow_notice(
            "profile storage lifecycle",
            f"executed={result.executed} exit={result.exit_code} cleanup={result.cleanup_ok} "
            f"env={profile_env_defined}/{profile_expected_env_defined}/{host_localappdata_defined} "
            f"unicode={profile_unicode_set_status}/{profile_unicode_output_present} "
            f"equals_api={profile_env_matches_api}/{profile_unicode_env_matches_api} "
            f"equals_host={profile_unicode_env_matches_host} alias_match={profile_env_equals_api} "
            f"actual={profile_unicode_actual_value_defined} "
            f"stat={profile_actual_stat_before_delete} relation={profile_actual_relation_before_delete} "
            f"same_api={profile_actual_samefile_as_api_before_delete} "
            f"dir_before={profile_directory_exists_before_launch} visible={profile_directory_visible} "
            f"write={profile_write_status_value}/{profile_write_error_class} "
            f"marker={marker_present_before_delete}",
        )
        self.assertTrue(result.executed, result)
        self.assertEqual(result.exit_code, 0, result)
        self.assertTrue(result.cleanup_ok, result)
        self.assertEqual(len(profile_paths), 1)
        self.assertEqual(marker_present_before_delete, [True])
        self.assertFalse(
            Path(profile_paths[0]).exists(),
            "profile storage must be removed when the AppContainer job ends",
        )

    def test_LOCALAPPDATA诊断在AppContainer外层拒绝用户命令(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-invalid-localappdata-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable), "/all"], cwd=raw, timeout_seconds=2,
                _diagnostic_omit_localappdata=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    def test_省略LOCALAPPDATA差分不能与app_name差分叠加(self) -> None:
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-overlapping-diagnostics-") as raw, \
             mock.patch("icode.windows_appcontainer.sys.platform", "win32"), \
             mock.patch("icode.windows_appcontainer.Path.is_absolute", return_value=True), \
             mock.patch("icode.windows_appcontainer.Path.is_file", return_value=True), \
             mock.patch("icode.windows_appcontainer.ctypes.WinDLL", create=True) as load_api:
            result = run_windows_appcontainer(
                [str(executable)], cwd=raw, timeout_seconds=2,
                _diagnostic_omit_localappdata=True,
                _diagnostic_null_application_name=True,
            )
        self.assertFalse(result.executed)
        self.assertEqual(result.error, "invalid_diagnostic_probe")
        load_api.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断仅LOCALAPPDATA最小环境块下的系统程序启动(self) -> None:
        """The wrapper adds only its profile path to this intentionally empty base block."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-empty-env-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            safe_environment = _build_windows_environment_block(
                executable, workspace, system_root,
            )
            # The base block is intentionally empty; the wrapper adds only its profile path.
            # Never pass lpEnvironment=None, which would copy arbitrary runner variables.
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=("\0\0", safe_environment),
            ):
                result = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10, process_limit=2,
                )
            self._workflow_notice(
                "minimal base environment plus profile LOCALAPPDATA",
                f"executed={result.executed} exit={result.exit_code} error={result.error} "
                f"cleanup={result.cleanup_ok} detail={result.detail}",
            )
            self.assertTrue(result.executed, result)
            self.assertEqual(result.exit_code, 0, result)
            self.assertTrue(result.cleanup_ok, result)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_AppContainer环境块仅比普通Job多容器LOCALAPPDATA(self) -> None:
        """AppContainer receives its own profile path, never the host profile variable."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value
        observed_metadata: list[str] = []

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
                entries = [entry for entry in block.split("\0") if entry]
                names = [
                    entry[:entry.index("=", 1)] if entry.startswith("=")
                    else entry.split("=", 1)[0]
                    for entry in entries
                ]
                observed_metadata.append(
                    f"chars={len(block)} utf16_bytes={len(block.encode('utf-16-le'))} "
                    f"nul_chars={block.count(chr(0))} names={names} "
                    f"sha256={hashlib.sha256(block.encode('utf-16-le')).hexdigest()}"
                )
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-matched-env-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                ordinary = run_windows_job(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                )
                appcontainer = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2,
                )

        self._workflow_notice(
            "AppContainer profile LOCALAPPDATA environment control",
            f"ordinary=executed:{ordinary.executed},exit:{ordinary.exit_code},"
            f"error:{ordinary.error},cleanup:{ordinary.cleanup_ok}; "
            f"appcontainer=executed:{appcontainer.executed},exit:{appcontainer.exit_code},"
            f"error:{appcontainer.error},cleanup:{appcontainer.cleanup_ok},"
            f"detail:{appcontainer.detail}; captured_blocks={len(observed_blocks)} "
            f"metadata={observed_metadata[:2]}",
        )

        self.assertTrue(ordinary.executed, ordinary)
        self.assertEqual(ordinary.exit_code, 0, ordinary)
        self.assertTrue(ordinary.cleanup_ok, ordinary)
        self.assertGreaterEqual(len(observed_blocks), 2, "both primary launches must build an environment")
        def parse(block: str) -> dict[str, str]:
            entries: dict[str, str] = {}
            for entry in block.split("\0"):
                if not entry:
                    continue
                separator = entry.index("=", 1) if entry.startswith("=") else entry.index("=")
                entries[entry[:separator]] = entry[separator + 1:]
            return entries

        ordinary_entries, appcontainer_base_entries = map(parse, observed_blocks[:2])
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(appcontainer_base_entries, ordinary_entries)
        self.assertEqual(
            len(appcontainer_blocks), 2,
            "the AppContainer main command and ACL-revocation probe both use its profile variable",
        )
        appcontainer_entries = parse(appcontainer_blocks[0])
        self.assertNotIn("LOCALAPPDATA", ordinary_entries)
        self.assertIn("LOCALAPPDATA", appcontainer_entries)
        self.assertTrue(Path(appcontainer_entries["LOCALAPPDATA"]).is_absolute())
        self.assertEqual(
            [parse(block)["LOCALAPPDATA"] for block in appcontainer_blocks],
            [appcontainer_entries["LOCALAPPDATA"]] * len(appcontainer_blocks),
        )
        self.assertEqual(
            {key: value for key, value in appcontainer_entries.items() if key != "LOCALAPPDATA"},
            ordinary_entries,
        )
        self.assertTrue(appcontainer.executed, appcontainer)
        self.assertEqual(appcontainer.exit_code, 0, appcontainer)
        self.assertTrue(appcontainer.cleanup_ok, appcontainer)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断lpApplicationName显式路径与NULL差分(self) -> None:
        """Compare only lpApplicationName while keeping the suspended Job path intact."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-lpappname-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                null_application_name = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2, _diagnostic_null_application_name=True,
                )

        env_equal = len(observed_blocks) == 2 and observed_blocks[0] == observed_blocks[1]
        self._workflow_notice(
            "lpApplicationName A/B diagnostic",
            f"candidate=executed:{null_application_name.executed},"
            f"exit:{null_application_name.exit_code},error:{null_application_name.error},"
            f"cleanup:{null_application_name.cleanup_ok}; environment_blocks="
            f"{len(observed_blocks)},equal:{env_equal}; "
            f"ab:{null_application_name.detail.partition('application_name_ab=')[2]}",
        )
        self.assertGreaterEqual(len(observed_blocks), 2, "both launches must reach environment setup")
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(
            len(appcontainer_blocks), 3,
            "the A/B launches and ACL-revocation probe each use the same profile variable",
        )
        self.assertEqual(appcontainer_blocks[0], appcontainer_blocks[1])

        def profile_localappdata_value(block: str) -> str:
            entries = [
                entry for entry in block.split("\0") if entry
                and entry[:entry.index("=", 1)].casefold() == "localappdata"
            ]
            self.assertEqual(len(entries), 1, "final AppContainer block must contain one profile path")
            return entries[0].split("=", 1)[1]

        localappdata_values = [
            profile_localappdata_value(block) for block in appcontainer_blocks
        ]
        self.assertEqual(localappdata_values[1:], [localappdata_values[0]] * 2)
        self.assertTrue(null_application_name.executed, null_application_name)
        self.assertEqual(null_application_name.exit_code, 0, null_application_name)
        self.assertTrue(null_application_name.cleanup_ok, null_application_name)
        app_name_ab = null_application_name.detail.partition("application_name_ab=")[2]
        self.assertIn("baseline:executed:True,exit:0", app_name_ab)
        self.assertIn("candidate:executed:True,exit:0", app_name_ab)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断同一profile仅追加LOCALAPPDATA差分(self) -> None:
        """Keep profile SID and launch inputs fixed while adding its official local-data path."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        executable = system_root / "System32" / "whoami.exe"
        target_executable = os.path.normcase(str(executable))
        observed_blocks: list[str] = []
        appcontainer_blocks: list[str] = []
        append_environment_value = _append_windows_environment_value

        def build_and_observe(
            executable_path: str | os.PathLike[str],
            cwd: str | os.PathLike[str],
            system_root_path: str | os.PathLike[str],
        ) -> str:
            block = _build_windows_environment_block(
                executable_path, cwd, system_root_path,
            )
            if os.path.normcase(os.fspath(executable_path)) == target_executable:
                observed_blocks.append(block)
            return block

        def append_and_observe(block: str, name: str, value: str) -> str:
            result = append_environment_value(block, name, value)
            if name.casefold() == "localappdata":
                appcontainer_blocks.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-localappdata-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            with mock.patch(
                "icode.windows_job._build_windows_environment_block",
                side_effect=build_and_observe,
            ), mock.patch(
                "icode.windows_job._append_windows_environment_value",
                side_effect=append_and_observe,
            ):
                candidate = run_windows_appcontainer(
                    [str(executable)], cwd=workspace, timeout_seconds=10,
                    process_limit=2, _diagnostic_omit_localappdata=True,
                )

        ab_summary = candidate.detail.partition("localappdata_ab=")[2]
        self._workflow_notice(
            "same-profile LOCALAPPDATA A/B diagnostic",
            f"candidate=executed:{candidate.executed},exit:{candidate.exit_code},"
            f"error:{candidate.error},cleanup:{candidate.cleanup_ok}; "
            f"ab={ab_summary}; captured_blocks={len(observed_blocks)}",
        )
        self.assertEqual(len(observed_blocks), 2, "baseline and candidate must both launch")
        self.assertIn("baseline:executed:False", ab_summary)
        self.assertIn("baseline_win32_error:203", ab_summary)
        self.assertIn("candidate:executed:True,exit:0", ab_summary)

        def parse(block: str) -> dict[str, str]:
            entries: dict[str, str] = {}
            for entry in block.split("\0"):
                if not entry:
                    continue
                separator = entry.index("=", 1) if entry.startswith("=") else entry.index("=")
                entries[entry[:separator]] = entry[separator + 1:]
            return entries

        baseline_entries, candidate_base_entries = map(parse, observed_blocks)
        self.assertEqual(observed_blocks[0], observed_blocks[1])
        self.assertEqual(candidate_base_entries, baseline_entries)
        self.assertEqual(
            len(appcontainer_blocks), 2,
            "the A/B candidate and ACL-revocation probe use the profile variable",
        )
        candidate_entries = parse(appcontainer_blocks[0])
        self.assertNotIn("LOCALAPPDATA", baseline_entries)
        self.assertIn("LOCALAPPDATA", candidate_entries)
        self.assertEqual(
            parse(appcontainer_blocks[1])["LOCALAPPDATA"],
            candidate_entries["LOCALAPPDATA"],
        )
        self.assertEqual(
            {key: value for key, value in candidate_entries.items() if key != "LOCALAPPDATA"},
            baseline_entries,
        )
        self.assertTrue(candidate.executed, candidate)
        self.assertEqual(candidate.exit_code, 0, candidate)
        self.assertTrue(candidate.cleanup_ok, candidate)

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_诊断容器对宿主Python运行时文件的直接读取(self) -> None:
        """Distinguish runtime DACL access from a missing or misplaced dependency."""
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        command = system_root / "System32" / "cmd.exe"
        executable = Path(sys.executable)
        stdlib = Path(sysconfig.get_path("stdlib"))
        version = f"{sys.version_info.major}{sys.version_info.minor}"
        dll_name = sysconfig.get_config_var("DLLLIBRARY") or f"python{version}.dll"
        candidates = [
            ("system32_control", system_root / "System32" / "whoami.exe"),
            ("python_executable", executable),
            ("python_shared_library", executable.parent / dll_name),
            ("stdlib_pathlib", stdlib / "pathlib.py"),
            ("stdlib_encodings", stdlib / "encodings" / "__init__.py"),
            ("stdlib_archive", executable.parent / f"python{version}.zip"),
        ]
        runtime_files = [(label, path) for label, path in candidates if path.is_file()]
        self._workflow_notice(
            "Python runtime direct-read inventory",
            json.dumps(
                {
                    "candidate_count": len(candidates),
                    "available_count": len(runtime_files),
                    "available_labels": [label for label, _ in runtime_files],
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        )
        self.assertGreaterEqual(
            len(runtime_files), 4,
            "Windows CI runtime layout changed; direct-read diagnostic lacks enough samples",
        )
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-runtime-access-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            copy_script = workspace / "copy-runtime.cmd"
            copy_started = workspace / "copy-runtime-started.txt"
            for index, (label, source) in enumerate(runtime_files):
                destination_name = f"runtime-copy-{index}.bin"
                destination = workspace / destination_name
                copy_message = workspace / f"runtime-copy-{index}.message.txt"
                copy_started.unlink(missing_ok=True)
                copy_message.unlink(missing_ok=True)
                copy_script.write_text(
                    f'@echo off\r\necho started> "{copy_started.name}"\r\n'
                    f'copy /b "{source}" "{destination_name}" '
                    f'> "{copy_message.name}" 2>&1\r\n',
                    encoding="utf-8",
                )
                # The Package SID is granted the task directory, not its temp parents.
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{copy_script.name}"],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )
                copy_script_started = copy_started.is_file()
                source_size = source.stat().st_size
                copied_size = destination.stat().st_size if destination.is_file() else None
                try:
                    copy_output = copy_message.read_text(
                        encoding="utf-8", errors="replace",
                    ).casefold()
                except OSError:
                    copy_output = ""
                if copied_size == source_size:
                    copy_error_class = "read_ok"
                elif "access is denied" in copy_output or "access denied" in copy_output:
                    copy_error_class = "access_denied"
                elif "cannot find the path" in copy_output or "path not found" in copy_output:
                    copy_error_class = "path_not_found"
                elif "cannot find the file" in copy_output or "file not found" in copy_output:
                    copy_error_class = "file_not_found"
                elif copy_output:
                    copy_error_class = "other_copy_error"
                else:
                    copy_error_class = "no_copy_diagnostic"
                error_class = "none"
                if result.error is not None:
                    error_class = (
                        result.error
                        if result.error in {
                            "timeout", "native_api_failed", "cleanup_failed", "job_creation_failed",
                        }
                        else "other_error"
                    )
                result_summary: dict[str, object] = {
                    "label": label,
                    "copy_script_started": copy_script_started,
                    "source_size": source_size,
                    "source_read_match": copied_size == source_size,
                    "copy_error_class": copy_error_class,
                    "executed": result.executed,
                    "exit_code": result.exit_code,
                    "error_class": error_class,
                    "cleanup_ok": result.cleanup_ok,
                    "copied_size": copied_size,
                }
                # Emit each bounded, path-free observation before assertions so an
                # early runtime/ACL failure cannot hide earlier file results.
                self._workflow_notice(
                    "Python runtime direct-read diagnostic",
                    json.dumps(result_summary, ensure_ascii=True, separators=(",", ":")),
                )
                self.assertTrue(result.executed, result)
                self.assertIsNone(result.error, result)
                self.assertTrue(result.cleanup_ok, result)
            self.assertTrue(
                result_summary["copy_script_started"],
                "AppContainer did not start the workspace-relative copy script",
            )

    @unittest.skipUnless(
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
        and os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_ACL") == "true",
        "host runtime ACL A/B 仅在显式启用的隔离诊断环境执行",
    )
    def test_诊断Python运行时只读ACL启动写入拒绝与精确恢复(self) -> None:
        """Mutate only hosted toolcache ACLs, then require byte-exact restoration."""
        with tempfile.TemporaryDirectory(prefix="icode-runtime-acl-native-") as raw:
            workspace = Path(raw) / "task"
            workspace.mkdir()
            marker = workspace / "python-runtime-started.txt"
            write_denied = workspace / "runtime-write-denied.txt"
            network_connect_failed = workspace / "runtime-network-connect-failed.txt"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(1)
                port = listener.getsockname()[1]
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    accepted, _address = listener.accept()
                    accepted.close()
                host_loopback_positive_control = True
                script = (
                    "import os,pathlib,socket,sys,sysconfig,encodings\n"
                    "marker=pathlib.Path('python-runtime-started.txt')\n"
                    "stdlib=pathlib.Path(sysconfig.get_path('stdlib'))\n"
                    "files=[pathlib.Path(sys.executable),pathlib.Path(pathlib.__file__),"
                    "pathlib.Path(encodings.__file__)]\n"
                    "dll=sysconfig.get_config_var('DLLLIBRARY')\n"
                    "if dll: files.extend([pathlib.Path(sys.executable).parent/dll,"
                    "pathlib.Path(sys.base_prefix)/dll])\n"
                    "for item in files:\n"
                    "    if item.is_file(): item.read_bytes()\n"
                    "try:\n"
                    "    fd=os.open(pathlib.__file__,os.O_WRONLY|os.O_APPEND)\n"
                    "except OSError:\n"
                    "    pathlib.Path('runtime-write-denied.txt').write_text('true')\n"
                    "else:\n"
                    "    os.close(fd); raise SystemExit(73)\n"
                    "try:\n"
                    f"    with socket.create_connection(('127.0.0.1',{port}),timeout=1):\n"
                    "        pass\n"
                    "except PermissionError:\n"
                    "    pathlib.Path('runtime-network-connect-failed.txt').write_text('true')\n"
                    "except TimeoutError:\n"
                    "    pathlib.Path('runtime-network-connect-failed.txt').write_text('true')\n"
                    "except OSError as exc:\n"
                    "    if getattr(exc,'winerror',None) in "
                    f"{_APP_CONTAINER_CONNECT_FAILURE_WINERRORS!r}:\n"
                    "        pathlib.Path('runtime-network-connect-failed.txt').write_text('true')\n"
                    "    else:\n"
                    "        raise\n"
                    "else:\n"
                    "    raise SystemExit(74)\n"
                    "marker.write_text('started')\n"
                )
                argv = [sys.executable, "-I", "-c", script]
                baseline = run_windows_appcontainer(
                    argv, cwd=workspace, timeout_seconds=10, process_limit=4,
                )
                marker.unlink(missing_ok=True)
                write_denied.unlink(missing_ok=True)
                network_connect_failed.unlink(missing_ok=True)
                candidate = run_windows_appcontainer(
                    argv, cwd=workspace, timeout_seconds=10, process_limit=4,
                    _diagnostic_runtime_acl=True,
                )

            summary = {
                "baseline_executed": baseline.executed,
                "baseline_exit": baseline.exit_code,
                "baseline_cleanup": baseline.cleanup_ok,
                "candidate_executed": candidate.executed,
                "candidate_exit": candidate.exit_code,
                "candidate_cleanup": candidate.cleanup_ok,
                "runtime_marker": marker.is_file(),
                "runtime_write_denied": write_denied.is_file(),
                "host_loopback_positive_control": host_loopback_positive_control,
                "network_connect_failed": network_connect_failed.is_file(),
                "runtime_acl_restore_verified": "runtime_acl_restore_verified=true" in candidate.detail,
                "detail": candidate.detail,
            }
            self._workflow_notice(
                "Python runtime read-only ACL A/B",
                json.dumps(summary, ensure_ascii=True, separators=(",", ":")),
            )
            self.assertTrue(baseline.cleanup_ok, baseline)
            self.assertTrue(candidate.executed, candidate)
            self.assertEqual(candidate.exit_code, 0, candidate)
            self.assertTrue(marker.is_file(), "Python did not write its workspace marker")
            self.assertTrue(write_denied.is_file(), "runtime files unexpectedly accepted write-open")
            self.assertTrue(
                host_loopback_positive_control,
                "host-side loopback positive-control listener did not accept a connection",
            )
            self.assertTrue(
                network_connect_failed.is_file(),
                "AppContainer unexpectedly connected to the host-side positive-control listener",
            )
            self.assertTrue(candidate.cleanup_ok, candidate)
            self.assertIn("runtime_acl_restore_verified=true", candidate.detail)

    @unittest.skipUnless(
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
        and os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_STAGING") == "true",
        "disposable staged Python runtime 只在独立 Windows Actions 诊断步骤执行",
    )
    def test_诊断stagedPython运行时可读执行不可写且恢复清理(self) -> None:
        if Path(sys.prefix).resolve() != Path(sys.base_prefix).resolve():
            self.skipTest("CI 当前 Python 是 venv；该诊断要求固定 base runtime root")
        source_root = Path(sys.base_prefix).resolve(strict=True)
        source_executable = source_root / Path(sys.executable).name
        source_stdlib = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
        source_probe = source_stdlib / "pathlib.py"
        self.assertTrue(source_executable.is_file(), "host Python executable is missing")
        self.assertTrue(source_probe.is_file(), "host Python stdlib sample is missing")

        temporary = tempfile.TemporaryDirectory(prefix="icode-runtime-stage-run-")
        temp_root = Path(temporary.name)
        workspace = temp_root / "task"
        workspace.mkdir()
        staged_root = temp_root / "icode-runtime-staging-copy"
        stage_summary: dict[str, int] = {}
        dacl_targets: list[Path] = []
        original_set_dacl = windows_appcontainer._set_dacl
        runtime_acl_snapshot = mock.Mock()
        runtime_acl_restore_report: dict[str, object] = {}
        original_restore_runtime_acl = windows_appcontainer._restore_runtime_acl_roots
        candidate_profile_paths: list[str] = []

        def record_dacl_target(
            path: Path, dacl: ctypes.c_void_p, advapi: ctypes.WinDLL,
        ) -> None:
            dacl_targets.append(Path(path).resolve(strict=True))
            original_set_dacl(path, dacl, advapi)

        def record_candidate_profile_path(
            sid: ctypes.c_void_p,
            userenv: ctypes.WinDLL,
            advapi: ctypes.WinDLL,
            kernel: ctypes.WinDLL,
            ole32: ctypes.WinDLL,
        ) -> str:
            path = _get_appcontainer_localappdata_path(
                sid, userenv, advapi, kernel, ole32,
            )
            candidate_profile_paths.append(path)
            return path

        try:
            try:
                stage_summary = windows_appcontainer._copy_runtime_tree_for_diagnostic(
                    source_root, staged_root,
                )
            except _AppContainerSetupError as exc:
                self._workflow_notice(
                    "Python runtime staging copy",
                    json.dumps({"copy_error": exc.error}, separators=(",", ":")),
                )
                self.fail(f"runtime staging failed closed: {exc.error}")

            staged_executable = staged_root / source_executable.name
            self.assertTrue(staged_executable.is_file(), "staged Python executable is missing")
            runtime_core_name = (
                f"python{sys.version_info.major}{sys.version_info.minor}.dll"
            )
            source_core = source_root / runtime_core_name
            staged_core = staged_root / runtime_core_name
            self.assertTrue(source_core.is_file(), "host Python core DLL is missing")
            self.assertTrue(staged_core.is_file(), "staged Python core DLL is missing")
            try:
                host_stage_probe = subprocess.run(
                    [
                        str(staged_executable), "-I", "-c",
                        "import _ctypes,_sqlite3,_ssl,ctypes,encodings,json,pathlib,platform,sqlite3,ssl; "
                        "print(json.dumps({'version':platform.python_version()}))",
                    ],
                    cwd=workspace, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=10,
                    shell=False, check=False,
                )
                host_stage_probe_exit = host_stage_probe.returncode
                host_stage_probe_error = "none"
                try:
                    host_stage_version = json.loads(host_stage_probe.stdout).get("version")
                except (AttributeError, json.JSONDecodeError):
                    host_stage_version = None
            except subprocess.TimeoutExpired:
                host_stage_probe_exit = None
                host_stage_probe_error = "timeout"
                host_stage_version = None
            except OSError:
                host_stage_probe_exit = None
                host_stage_probe_error = "launch_failed"
                host_stage_version = None
            self._workflow_json_notice(
                "Python runtime staging host positive control",
                {
                    "executed": host_stage_probe_exit is not None,
                    "exit": host_stage_probe_exit,
                    "error": host_stage_probe_error,
                    "version": host_stage_version,
                },
            )
            self.assertEqual(
                host_stage_probe_exit, 0,
                f"staged Python did not pass its host positive control ({host_stage_probe_error})",
            )
            host_image_probe_script = (
                "import ctypes,json\n"
                + _STAGED_PYTHON_RUNTIME_IMAGE_PROBE
                + "\n_runtime_image_mapping={"
                + f"'source_python':_runtime_image_probe({str(source_executable)!r}),"
                + f"'source_core':_runtime_image_probe({str(source_core)!r}),"
                + f"'staged_python':_runtime_image_probe({str(staged_executable)!r}),"
                + f"'staged_core':_runtime_image_probe({str(staged_core)!r})"
                + "}\nprint(json.dumps(_runtime_image_mapping,separators=(',',':')))\n"
            )
            try:
                host_image_process = subprocess.run(
                    [str(staged_executable), "-I", "-c", host_image_probe_script],
                    cwd=workspace, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=10,
                    shell=False, check=False,
                )
                host_image_probe_exit = host_image_process.returncode
                host_image_probe_error = "none"
                try:
                    host_image_observation = json.loads(host_image_process.stdout)
                except (TypeError, json.JSONDecodeError):
                    host_image_observation = {}
                    host_image_probe_error = "invalid_result"
            except subprocess.TimeoutExpired:
                host_image_probe_exit = None
                host_image_probe_error = "timeout"
                host_image_observation = {}
            except OSError:
                host_image_probe_exit = None
                host_image_probe_error = "launch_failed"
                host_image_observation = {}
            baseline_marker = workspace / "staging-baseline-started"
            baseline = run_windows_appcontainer(
                [
                    str(staged_executable), "-I", "-c",
                    "from pathlib import Path; Path('staging-baseline-started').write_text('started')",
                ],
                cwd=workspace, timeout_seconds=10, process_limit=4,
            )

            workspace_marker = workspace / "staging-workspace-write"
            script_started_marker = workspace / "staging-python-script-started"
            imports_completed_marker = workspace / "staging-python-imports-completed"
            paths_completed_marker = workspace / "staging-python-paths-completed"
            path_resolution_probe_marker = workspace / "staging-python-path-resolution.json"
            runtime_write_completed_marker = workspace / "staging-runtime-write-completed"
            source_read_completed_marker = workspace / "staging-source-read-completed"
            network_completed_marker = workspace / "staging-network-completed"
            python_failure_marker = workspace / "staging-python-failure-class"
            runtime_write_probe = staged_root / "staging-runtime-write-probe"
            runtime_write_marker = workspace / "staging-runtime-write-denied"
            child_marker = workspace / "staging-child-started"
            result_marker = workspace / "staging-result.json"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(1)
                port = listener.getsockname()[1]
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    accepted, _address = listener.accept()
                    accepted.close()
                host_loopback_positive_control = True

                child_script = (
                    "import _ctypes,_sqlite3,_ssl; from pathlib import Path; "
                    f"Path({str(child_marker)!r}).write_text('child-ok')"
                )
                script = (
                    "open('staging-python-script-started','w',encoding='ascii').write('1')\n"
                    "try:\n"
                    "    import _ctypes,_sqlite3,_ssl,ctypes,encodings,json,pathlib,"
                    "os,platform,socket,sqlite3,ssl,stat,subprocess,sys,sysconfig,tempfile; from pathlib import Path\n"
                    "except Exception as exc:\n"
                    "    open('staging-python-failure-class','w',encoding='ascii').write("
                    "'imports:'+type(exc).__name__)\n"
                    "    raise\n"
                    + _STAGED_PYTHON_ENVIRONMENT_PROBE
                    + _STAGED_PYTHON_PROFILE_API_PROBE
                    + _STAGED_PYTHON_KNOWN_FOLDER_PROBE
                    + _STAGED_PYTHON_RUNTIME_IMAGE_PROBE
                    + _STAGED_PYTHON_TEMPFILE_PROBE
                    + "\n"
                    + "runtime_image_mapping={"
                    + f"'source_python':_runtime_image_probe({str(source_executable)!r}),"
                    + f"'source_core':_runtime_image_probe({str(source_core)!r}),"
                    + f"'staged_python':_runtime_image_probe({str(staged_executable)!r}),"
                    + f"'staged_core':_runtime_image_probe({str(staged_core)!r})"
                    + "}\n"
                    "def checkpoint(name): Path(name).write_text('1',encoding='ascii')\n"
                    "def failed(stage,exc): Path('staging-python-failure-class').write_text("
                    "stage+':'+type(exc).__name__,encoding='ascii')\n"
                    "def path_probe(call):\n"
                    "    try:\n"
                    "        call()\n"
                    "    except Exception as exc:\n"
                    "        return {'ok':False,'error':type(exc).__name__,"
                    "'winerror':getattr(exc,'winerror',None)}\n"
                    "    return {'ok':True,'error':'none','winerror':None}\n"
                    "def read_executable_byte():\n"
                    "    with open(sys.executable,'rb') as stream:\n"
                    "        return stream.read(1)\n"
                    "native_kernel32=ctypes.WinDLL('kernel32',use_last_error=True)\n"
                    "native_create_file=native_kernel32.CreateFileW\n"
                    "native_create_file.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,"
                    "ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,"
                    "ctypes.c_void_p]\n"
                    "native_create_file.restype=ctypes.c_void_p\n"
                    "native_get_final_path=native_kernel32.GetFinalPathNameByHandleW\n"
                    "native_get_final_path.argtypes=[ctypes.c_void_p,"
                    "ctypes.POINTER(ctypes.c_wchar),ctypes.c_uint32,ctypes.c_uint32]\n"
                    "native_get_final_path.restype=ctypes.c_uint32\n"
                    "native_close_handle=native_kernel32.CloseHandle\n"
                    "native_close_handle.argtypes=[ctypes.c_void_p]\n"
                    "native_close_handle.restype=ctypes.c_int\n"
                    "def open_executable_handle():\n"
                    "    handle=native_create_file(sys.executable,0,0,None,3,"
                    "0x02000000,None)\n"
                    "    if handle is None or handle==ctypes.c_void_p(-1).value:\n"
                    "        raise ctypes.WinError(ctypes.get_last_error())\n"
                    "    return handle\n"
                    "def createfile_zero_probe():\n"
                    "    handle=open_executable_handle()\n"
                    "    native_close_handle(handle)\n"
                    "def native_final_path(volume_flag):\n"
                    "    handle=open_executable_handle()\n"
                    "    try:\n"
                    "        buffer=ctypes.create_unicode_buffer(32768)\n"
                    "        length=native_get_final_path(handle,buffer,len(buffer),volume_flag)\n"
                    "        if length==0:\n"
                    "            raise ctypes.WinError(ctypes.get_last_error())\n"
                    "        if length>=len(buffer):\n"
                    "            raise OSError(122,'diagnostic path buffer too small')\n"
                    "        return buffer.value\n"
                    "    finally:\n"
                    "        native_close_handle(handle)\n"
                    "checkpoint('staging-python-imports-completed')\n"
                    "import nt\n"
                    "path_probes={\n"
                    "    'absolute':path_probe(lambda:Path(sys.executable).absolute()),\n"
                    "    'stat':path_probe(lambda:__import__('os').stat(sys.executable)),\n"
                    "    'read':path_probe(read_executable_byte),\n"
                    "    'resolve_strict':path_probe("
                    "lambda:Path(sys.executable).resolve(strict=True)),\n"
                    "    'resolve_nonstrict':path_probe("
                    "lambda:Path(sys.executable).resolve(strict=False)),\n"
                    "    'getfinalpathname':path_probe("
                    "lambda:nt._getfinalpathname(sys.executable)),\n"
                    "    'native_createfile_zero':path_probe(createfile_zero_probe),\n"
                    "    'getfinal_nt':path_probe(lambda:native_final_path(2)),\n"
                    "    'getfinal_dos':path_probe(lambda:native_final_path(0)),\n"
                    "}\n"
                    f"Path({str(path_resolution_probe_marker)!r}).write_text("
                    "json.dumps(path_probes),encoding='ascii')\n"
                    "try:\n"
                    "    executable_path=Path(sys.executable).absolute()\n"
                    "except Exception as exc:\n"
                    "    failed('executable_absolute',exc)\n"
                    "    raise\n"
                    "root=executable_path.parent\n"
                    "modules=[pathlib,encodings,json,platform,ssl,sqlite3,_ctypes,_sqlite3,_ssl]\n"
                    "try:\n"
                    "    module_paths=[Path(m.__file__).absolute() for m in modules]\n"
                    "except Exception as exc:\n"
                    "    failed('module_path',exc)\n"
                    "    raise\n"
                    "module_roots=all(path.is_relative_to(root) for path in module_paths)\n"
                    "try:\n"
                    "    prefix=Path(sys.prefix).absolute()\n"
                    "except Exception as exc:\n"
                    "    failed('prefix_absolute',exc)\n"
                    "    raise\n"
                    "prefix_ok=prefix==root\n"
                    "checkpoint('staging-python-paths-completed')\n"
                    "try:\n"
                    f"    Path({str(runtime_write_probe)!r}).write_bytes(b'x')\n"
                    "except PermissionError:\n"
                    "    runtime_write_denied=True\n"
                    "except OSError as exc:\n"
                    "    failed('runtime_write',exc)\n"
                    "    raise\n"
                    "else:\n"
                    "    runtime_write_denied=False\n"
                    "if runtime_write_denied:\n"
                    f"    Path({str(runtime_write_marker)!r}).write_text('denied')\n"
                    "checkpoint('staging-runtime-write-completed')\n"
                    "try:\n"
                    f"    Path({str(source_probe)!r}).read_bytes()\n"
                    "except PermissionError:\n"
                    "    source_runtime_denied=True\n"
                    "except OSError as exc:\n"
                    "    failed('source_read',exc)\n"
                    "    raise\n"
                    "else:\n"
                    "    source_runtime_denied=False\n"
                    "checkpoint('staging-source-read-completed')\n"
                    "network_connect_failed=False\n"
                    "network_connect_error=None\n"
                    "try:\n"
                    f"    with socket.create_connection(('127.0.0.1',{port}),timeout=1):\n"
                    "        pass\n"
                    "except PermissionError as exc:\n"
                    "    network_connect_failed=True\n"
                    "    network_connect_error=type(exc).__name__\n"
                    "except TimeoutError as exc:\n"
                    "    network_connect_failed=True\n"
                    "    network_connect_error=type(exc).__name__\n"
                    "except OSError as exc:\n"
                    "    if getattr(exc,'winerror',None) in "
                    f"{_APP_CONTAINER_CONNECT_FAILURE_WINERRORS!r}:\n"
                    "        network_connect_failed=True\n"
                    "        network_connect_error=type(exc).__name__\n"
                    "    else:\n"
                    "        failed('network',exc)\n"
                    "        raise\n"
                    "checkpoint('staging-network-completed')\n"
                    "try:\n"
                    "    workspace=Path.cwd()\n"
                    f"    Path({str(workspace_marker)!r}).write_text('write-ok')\n"
                    "except Exception as exc:\n"
                    "    failed('workspace_write',exc)\n"
                    "    raise\n"
                    f"child_code={child_script!r}\n"
                    "try:\n"
                    "    child=subprocess.run([sys.executable,'-I','-c',child_code],"
                    "timeout=5,check=False)\n"
                    "except Exception as exc:\n"
                    "    failed('child_launch',exc)\n"
                    "    raise\n"
                    "result={'prefix_ok':prefix_ok,'module_roots':module_roots,"
                    "'python_version':platform.python_version(),"
                    "'environment':staged_environment,"
                    "'profile_api':_staged_profile_api,"
                    "'profile_context':_staged_profile_context,"
                    "'tempfile':staged_tempfile,"
                    "'runtime_image_mapping':runtime_image_mapping,"
                    "'runtime_write_denied':runtime_write_denied,"
                    "'source_runtime_denied':source_runtime_denied,"
                    "'network_connect_failed':network_connect_failed,"
                    "'network_connect_error':network_connect_error,"
                    "'child_exit':child.returncode}\n"
                    f"Path({str(result_marker)!r}).write_text(json.dumps(result))\n"
                    "if not all((prefix_ok,module_roots,runtime_write_denied,"
                    "source_runtime_denied,network_connect_failed,child.returncode==0)):\n"
                    "    raise SystemExit(78)\n"
                )
                try:
                    compile(script, "<staged-runtime-probe>", "exec")
                except SyntaxError:
                    self.fail("staged runtime probe script is syntactically invalid")
                with mock.patch(
                    "icode.windows_appcontainer._snapshot_runtime_acl_roots",
                    wraps=windows_appcontainer._snapshot_runtime_acl_roots,
                ) as runtime_acl_snapshot, mock.patch(
                    "icode.windows_appcontainer._set_dacl",
                    side_effect=record_dacl_target,
                ), mock.patch(
                    "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                    side_effect=record_candidate_profile_path,
                ), mock.patch(
                    "icode.windows_appcontainer._restore_runtime_acl_roots",
                    side_effect=lambda transaction, sid: self._observe_runtime_acl_restore(
                        original_restore_runtime_acl,
                        transaction, sid, runtime_acl_restore_report,
                    ),
                ):
                    candidate = run_windows_appcontainer(
                        [str(staged_executable), "-I", "-c", script],
                        cwd=workspace, timeout_seconds=20, process_limit=4,
                        _diagnostic_runtime_acl=True,
                        _diagnostic_runtime_roots=(staged_root,),
                    )

            try:
                staged_result = json.loads(result_marker.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                staged_result = {}
            profile_environment = self._summarize_staged_environment(
                staged_result.get("environment"),
                candidate_profile_paths[0] if len(candidate_profile_paths) == 1 else None,
            )
            profile_api = self._summarize_staged_profile_api(
                staged_result.get("profile_api"),
                candidate_profile_paths[0] if len(candidate_profile_paths) == 1 else None,
            )
            profile_context = self._summarize_known_folder_observation(
                staged_result.get("profile_context"),
                candidate_profile_paths[0] if len(candidate_profile_paths) == 1 else None,
            )
            tempfile_probe = self._summarize_staged_tempfile(
                staged_result.get("tempfile"), staged_result.get("environment"),
            )
            runtime_image_mapping = self._summarize_runtime_image_probe(
                host_image_observation, staged_result.get("runtime_image_mapping"),
            )
            python_failure = "not_observed"
            try:
                raw_failure = python_failure_marker.read_text(encoding="ascii").strip()
            except OSError:
                raw_failure = ""
            try:
                raw_path_resolution_probe = json.loads(
                    path_resolution_probe_marker.read_text(encoding="ascii"),
                )
            except (OSError, ValueError):
                raw_path_resolution_probe = {}
            path_resolution_probe = {
                operation: {
                    "ok": outcome.get("ok") is True,
                    "error": outcome.get("error")
                    if outcome.get("error") in {
                        "none", "AttributeError", "FileNotFoundError", "OSError",
                        "PermissionError", "TypeError", "ValueError",
                    } else "other",
                    "winerror": outcome.get("winerror")
                    if isinstance(outcome.get("winerror"), int) else None,
                }
                for operation, outcome in raw_path_resolution_probe.items()
                if operation in {
                    "absolute", "stat", "read", "resolve_strict",
                    "resolve_nonstrict", "getfinalpathname", "native_createfile_zero",
                    "getfinal_nt", "getfinal_dos",
                } and isinstance(outcome, dict)
            }
            python_failure = _classify_runtime_probe_failure(raw_failure)
            raw_network_connect_error = staged_result.get("network_connect_error")
            if raw_network_connect_error in _RUNTIME_PROBE_ERROR_TYPES:
                network_connect_error = raw_network_connect_error
            elif raw_network_connect_error is None:
                network_connect_error = "not_observed"
            else:
                network_connect_error = "other"
            runtime_write_probe.unlink(missing_ok=True)
            summary = {
                **stage_summary,
                "baseline_executed": baseline.executed,
                "baseline_exit": baseline.exit_code,
                "baseline_cleanup": baseline.cleanup_ok,
                "baseline_started": baseline_marker.is_file(),
                "candidate_executed": candidate.executed,
                "candidate_exit": candidate.exit_code,
                "candidate_error": candidate.error,
                "candidate_cleanup": candidate.cleanup_ok,
                "staged_python_version": staged_result.get("python_version"),
                "acl_baseline_normalization": (
                    candidate.detail.split(
                        "runtime_acl_baseline_normalized=true control_delta=", 1,
                    )[1].split(";", 1)[0]
                    if "runtime_acl_baseline_normalized=true control_delta=" in candidate.detail
                    else "not_observed"
                ),
                "python_script_started": script_started_marker.is_file(),
                "python_imports_completed": imports_completed_marker.is_file(),
                "python_paths_completed": paths_completed_marker.is_file(),
                "runtime_write_check_completed": runtime_write_completed_marker.is_file(),
                "source_read_check_completed": source_read_completed_marker.is_file(),
                "network_check_completed": network_completed_marker.is_file(),
                "python_failure": python_failure,
                "python_path_resolution": path_resolution_probe,
                "profile_environment": profile_environment,
                "profile_api": profile_api,
                "profile_context": profile_context,
                "tempfile_probe": tempfile_probe,
                "runtime_image_mapping": runtime_image_mapping,
                "host_image_probe_exit": host_image_probe_exit,
                "host_image_probe_error": host_image_probe_error,
                "python_path_resolution_probe_complete": set(path_resolution_probe) == {
                    "absolute", "stat", "read", "resolve_strict",
                    "resolve_nonstrict", "getfinalpathname", "native_createfile_zero",
                    "getfinal_nt", "getfinal_dos",
                },
                "runtime_marker": candidate.executed and candidate.exit_code == 0,
                "workspace_write": workspace_marker.is_file(),
                "runtime_write_denied": runtime_write_marker.is_file()
                or staged_result.get("runtime_write_denied") is True,
                "source_runtime_denied": staged_result.get("source_runtime_denied") is True,
                "network_connect_failed": staged_result.get("network_connect_failed") is True,
                "network_connect_error": network_connect_error,
                "module_roots": staged_result.get("module_roots") is True,
                "prefix_ok": staged_result.get("prefix_ok") is True,
                "child_started": child_marker.is_file(),
                "acl_restore_verified": "runtime_acl_restore_verified=true" in candidate.detail,
                "acl_roots_are_staged": runtime_acl_snapshot.call_args is not None
                and runtime_acl_snapshot.call_args.args[0] == (staged_root.resolve(),),
                "source_acl_untouched": not any(
                    path == source_root
                    or path.is_relative_to(source_root)
                    or source_root.is_relative_to(path)
                    for path in dacl_targets
                ),
                "candidate_detail_flags": [
                    label for label, marker in (
                        ("runtime_acl_snapshot", "runtime_acl_snapshot="),
                        ("runtime_acl_baseline_normalized", "runtime_acl_baseline_normalized=true"),
                        ("runtime_acl_access_granted", "runtime_acl_access=read_execute"),
                        ("runtime_acl_restore_verified", "runtime_acl_restore_verified=true"),
                        ("runtime_acl_restore_failed", "runtime_acl_restore_failed"),
                        ("workspace_acl_restore_failed", "workspace_acl_restore_failed"),
                        ("workspace_acl_revocation_unverified", "workspace_acl_revocation_unverified"),
                        ("profile_storage_residual", "profile_storage_residual"),
                        ("profile_storage_unverified", "profile_storage_unverified"),
                        ("profile_delete_failed", "profile_delete_failed"),
                        ("sid_release_failed", "sid_release_failed"),
                        ("job_terminate_failed", "TerminateJobObject err="),
                        ("job_query_failed", "QueryInformationJobObject err="),
                    ) if marker in candidate.detail
                ],
                "runtime_acl_restore_report": runtime_acl_restore_report or {"state": "not_observed"},
            }
            self._workflow_json_notice(
                "Python disposable staging inventory",
                {
                    "source_entries": summary.get("source_entries"),
                    "materialized_links": summary.get("materialized_links"),
                    "staged_entries": summary.get("staged_entries"),
                    "host_python_version": host_stage_version,
                },
            )
            self._workflow_json_notice(
                "Python disposable staging lifecycle",
                {
                    "baseline_executed": summary["baseline_executed"],
                    "baseline_exit": summary["baseline_exit"],
                    "baseline_cleanup": summary["baseline_cleanup"],
                    "baseline_started": summary["baseline_started"],
                    "candidate_executed": summary["candidate_executed"],
                    "candidate_exit": summary["candidate_exit"],
                    "candidate_error": summary["candidate_error"],
                    "candidate_cleanup": summary["candidate_cleanup"],
                    "staged_python_version": summary["staged_python_version"],
                },
            )
            self._workflow_json_notice(
                "Python disposable staging cleanup diagnostics",
                {"detail_flags": summary["candidate_detail_flags"]},
            )
            self._workflow_json_notice(
                "Python disposable staging ACL mismatch classification",
                summary["runtime_acl_restore_report"],
            )
            self._workflow_json_notice(
                "Python disposable staging script checkpoints",
                {
                    "script_started": summary["python_script_started"],
                    "imports_completed": summary["python_imports_completed"],
                    "paths_completed": summary["python_paths_completed"],
                    "runtime_write_check_completed": summary["runtime_write_check_completed"],
                    "source_read_check_completed": summary["source_read_check_completed"],
                    "network_check_completed": summary["network_check_completed"],
                    "python_failure": summary["python_failure"],
                },
            )
            self._workflow_json_notice(
                "Python disposable staging path-resolution probes",
                _compact_path_resolution_probe_notice(
                    summary["python_path_resolution"],
                    complete=summary["python_path_resolution_probe_complete"],
                ),
            )
            self._workflow_json_notice(
                "Python staged environment flags", profile_environment,
            )
            self._workflow_json_notice(
                "Python staged profile API diagnostics", summary["profile_api"],
            )
            self._workflow_json_notice(
                "Python staged known-folder context", summary["profile_context"],
            )
            self._workflow_json_notice(
                "Python staged tempfile consumer", tempfile_probe,
            )
            self._workflow_json_notice(
                "Python staged runtime image mapping (read-only)",
                {
                    "host_exit": host_image_probe_exit,
                    "host_error": host_image_probe_error,
                    "observation": runtime_image_mapping,
                },
            )
            self._workflow_json_notice(
                "Python disposable staging boundary assertions",
                {
                    "acl_restore_verified": summary["acl_restore_verified"],
                    "acl_baseline_normalization_delta": summary["acl_baseline_normalization"],
                    "acl_roots_are_staged": summary["acl_roots_are_staged"],
                    "source_acl_untouched": summary["source_acl_untouched"],
                    "runtime_marker": summary["runtime_marker"],
                    "workspace_write": summary["workspace_write"],
                    "runtime_write_denied": summary["runtime_write_denied"],
                    "source_runtime_denied": summary["source_runtime_denied"],
                    "host_loopback_positive_control": host_loopback_positive_control,
                    "network_connect_failed": summary["network_connect_failed"],
                    "network_connect_error": summary["network_connect_error"],
                    "module_roots": summary["module_roots"],
                    "prefix_ok": summary["prefix_ok"],
                    "child_started": summary["child_started"],
                },
            )
        finally:
            temporary.cleanup()

        stage_deleted = not temp_root.exists()
        self._workflow_json_notice(
            "Python disposable staging deletion",
            {"staging_removed": stage_deleted},
        )
        self.assertTrue(baseline.cleanup_ok, "baseline AppContainer cleanup failed")
        self.assertFalse(summary["baseline_started"], "AppContainer read staged runtime before grant")
        self.assertTrue(candidate.executed, "staged AppContainer process did not start")
        self.assertEqual(candidate.exit_code, 0, "staged runtime probe did not complete")
        self.assertTrue(candidate.cleanup_ok, "staged AppContainer cleanup failed")
        self.assertTrue(summary["python_script_started"], "staged Python never entered its command script")
        self.assertTrue(
            summary["python_path_resolution_probe_complete"],
            "staged Python path-resolution probes did not all report",
        )
        profile_environment = summary["profile_environment"]
        self.assertIsInstance(profile_environment, dict)
        self.assertTrue(
            profile_environment.get("complete"),
            "staged Python environment probe is incomplete",
        )
        for name in ("localappdata", "temp", "tmp"):
            self.assertTrue(
                profile_environment[name]["python_win32_match"],
                f"staged Python and Win32 disagree on {name}",
            )
        profile_api = summary["profile_api"]
        self.assertTrue(profile_api.get("complete"), "staged profile API probe is incomplete")
        self.assertTrue(
            profile_api["environment_block_scan_complete"],
            "staged profile environment block could not be inspected",
        )
        self.assertEqual(profile_api["environment_entry_count"], 1)
        self.assertTrue(profile_api["token_is_appcontainer"], "staged process token is not AppContainer")
        self.assertTrue(profile_api["token_sid_defined"], "staged AppContainer token has no SID")
        self.assertTrue(profile_api["profile_api_ok"], "container profile API lookup failed")
        self.assertTrue(
            profile_api["profile_api_matches_host"],
            "container and host resolved different profile API paths",
        )
        profile_context = summary["profile_context"]
        self.assertTrue(
            profile_context.get("complete"),
            "staged known-folder/package context probe is incomplete",
        )
        tempfile_probe = summary["tempfile_probe"]
        self.assertTrue(
            tempfile_probe.get("complete"),
            "staged Python tempfile probe did not produce a sanitized result",
        )
        self.assertTrue(
            tempfile_probe["created"],
            f"staged Python tempfile could not create a file ({tempfile_probe['error']})",
        )
        self.assertTrue(
            tempfile_probe["deleted"],
            "staged Python tempfile did not remove its temporary file",
        )
        runtime_image_mapping = summary["runtime_image_mapping"]
        self.assertEqual(
            summary["host_image_probe_exit"], 0,
            f"runtime image host positive control failed ({summary['host_image_probe_error']})",
        )
        self.assertTrue(
            runtime_image_mapping.get("complete") is True,
            "runtime image mapping probe did not produce a safe complete observation",
        )
        self.assertTrue(
            runtime_image_mapping.get("cleanup_ok") is True,
            "runtime image mapping probe did not release all handles/views",
        )
        self.assertTrue(
            all(
                runtime_image_mapping.get(f"host_{label}") == "ok|ok"
                for label in (
                    "source_python", "source_core", "staged_python", "staged_core",
                )
            ),
            "host positive control could not image-map every runtime file",
        )
        self.assertEqual(
            runtime_image_mapping.get("container_staged_python"), "ok|ok",
            "AppContainer could not image-map the staged Python executable",
        )
        self.assertEqual(
            runtime_image_mapping.get("container_staged_core"), "ok|ok",
            "AppContainer could not image-map the staged Python core DLL",
        )
        self.assertIn(
            summary["acl_baseline_normalization"], {"0", "1024"},
            "staging ACL baseline normalization was not verified",
        )
        self.assertTrue(summary["acl_restore_verified"], "staged runtime DACL was not exactly restored")
        self.assertTrue(summary["acl_roots_are_staged"], "runtime ACL transaction escaped the staging root")
        self.assertTrue(summary["source_acl_untouched"], "source runtime ACL was modified")
        self.assertTrue(summary["workspace_write"], "AppContainer could not write its task workspace")
        self.assertTrue(summary["runtime_write_denied"], "staged runtime accepted a write")
        self.assertTrue(summary["source_runtime_denied"], "AppContainer read the original runtime")
        self.assertTrue(
            host_loopback_positive_control,
            "host-side loopback positive-control listener did not accept a connection",
        )
        self.assertTrue(
            summary["network_connect_failed"],
            "AppContainer unexpectedly connected to the host-side positive-control listener",
        )
        self.assertTrue(summary["module_roots"], "Python imported a module outside the staged runtime")
        self.assertTrue(summary["prefix_ok"], "staged Python resolved its prefix outside the staging root")
        self.assertTrue(summary["child_started"], "staged Python child process did not start")
        self.assertTrue(stage_deleted, "staged runtime directory remains after cleanup")

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_在AppContainer中运行Python并解析工作路径(self) -> None:
        """Verify the host Python runtime and path behavior, not only System32 tools."""
        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-python-") as raw:
            root = Path(raw).resolve()
            workspace = root / "task"
            workspace.mkdir()
            marker = workspace / "python-probe.json"
            profile_paths: list[str] = []

            def get_profile_path(
                sid: ctypes.c_void_p,
                userenv: ctypes.WinDLL,
                advapi: ctypes.WinDLL,
                kernel: ctypes.WinDLL,
                ole32: ctypes.WinDLL,
            ) -> str:
                path = _get_appcontainer_localappdata_path(
                    sid, userenv, advapi, kernel, ole32,
                )
                profile_paths.append(path)
                return path

            probe = (
                "import json\n"
                "from pathlib import Path\n"
                "import sys\n"
                "import os\n"
                "result = {}\n"
                "for label, value in [('cwd', Path.cwd()), ('executable', Path(sys.executable))]:\n"
                "    try:\n"
                "        result[label] = str(value.resolve(strict=True))\n"
                "    except Exception as exc:\n"
                "        result[label] = f'{type(exc).__name__}: {exc}'\n"
                "profile_marker = Path(os.environ['LOCALAPPDATA']) / 'icode-profile-lifecycle-probe'\n"
                "profile_marker.write_text('temporary', encoding='utf-8')\n"
                f"Path({str(marker)!r}).write_text(json.dumps(result), encoding='utf-8')\n"
            )
            with mock.patch(
                "icode.windows_appcontainer._get_appcontainer_localappdata_path",
                side_effect=get_profile_path,
            ):
                result = run_windows_appcontainer(
                    [sys.executable, "-S", "-c", probe],
                    cwd=workspace, timeout_seconds=15, process_limit=4,
                )
            self._workflow_notice(
                "Python runtime",
                f"executed={result.executed} exit={result.exit_code} error={result.error} "
                f"cleanup={result.cleanup_ok} detail={result.detail}",
            )
            self.assertTrue(result.executed, result)
            self.assertEqual(result.exit_code, 0, result)
            self.assertTrue(result.cleanup_ok, result)
            self.assertTrue(marker.is_file(), "AppContainer Python did not write its workspace marker")
            path_result = marker.read_text(encoding="utf-8")
            self._workflow_notice("Python path resolution", path_result)
            resolved = json.loads(path_result)
            self.assertEqual(set(resolved), {"cwd", "executable"})
            self.assertEqual(len(profile_paths), 1)
            self.assertFalse(
                Path(profile_paths[0]).exists(),
                "容器退出后 profile 私有数据目录必须已删除",
            )
            for label, value in resolved.items():
                self.assertTrue(
                    Path(value).is_absolute(),
                    f"AppContainer could not resolve {label}: {value}",
                )

    @unittest.skipUnless(sys.platform == "win32", "需 Windows AppContainer 原生实测")
    def test_工作区ACL与容器profile隔离且默认拒绝网络(self) -> None:
        requests: list[str] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - 标准库接口名
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"host-positive-control")

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

        with tempfile.TemporaryDirectory(prefix="icode-appcontainer-test-") as raw:
            root = Path(raw).resolve()
            workspace = root / "task"
            workspace.mkdir()
            nested = workspace / "existing" / "nested"
            nested.mkdir(parents=True)
            (nested / "input.txt").write_text("existing-workspace-file", encoding="utf-8")
            outside_secret = root / "outside-secret.txt"
            outside_secret.write_text("must-not-enter-appcontainer", encoding="utf-8")
            outside_write = root / "outside-write.txt"

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/probe"
            try:
                # 宿主正向对照：listener 确实可达，沙箱负例才有解释力。
                parsed = urlsplit(url)
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
                connection.request("GET", parsed.path)
                response = connection.getresponse()
                self.assertEqual(response.read(), b"host-positive-control")
                connection.close()
                self.assertEqual(requests, ["/probe"])
                requests.clear()
                self._workflow_notice("host loopback positive control", "listener reachable")

                system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
                curl = system_root / "System32" / "curl.exe"
                command = system_root / "System32" / "cmd.exe"
                self.assertTrue(curl.is_file(), "Windows 目标环境需提供系统 curl.exe")
                inline_marker = workspace / "inline-write.txt"
                inline_write = run_windows_appcontainer(
                    [
                        str(command), "/d", "/c",
                        "echo inline-write-ok> inline-write.txt",
                    ],
                    cwd=workspace, timeout_seconds=8, process_limit=2,
                )
                self._workflow_notice(
                    "AppContainer relative cwd write control",
                    f"executed={inline_write.executed} exit={inline_write.exit_code} "
                    f"error={inline_write.error} cleanup={inline_write.cleanup_ok} "
                    f"marker={inline_marker.is_file()}",
                )
                self.assertTrue(inline_write.executed, inline_write)
                self.assertEqual(inline_write.exit_code, 0, inline_write)
                self.assertTrue(inline_write.cleanup_ok, inline_write)
                self.assertEqual(inline_marker.read_text(encoding="utf-8").strip(), "inline-write-ok")

                allowed_write = workspace / "new-output.txt"
                copied_secret = workspace / "outside-copy.txt"
                copied_nested = workspace / "nested-copy.txt"
                child_started = workspace / "child-started.txt"
                child_late = workspace / "child-late.txt"
                child_release = workspace / "child-release.txt"
                child_launch_log = workspace / "child-launch.log"
                script_complete = workspace / "probe-script-complete.txt"
                child_script = workspace / "child.cmd"
                child_script.write_text(
                    "@echo off\r\n"
                    f'echo started> "{child_started.name}"\r\n'
                    ":wait_for_release\r\n"
                    f'if not exist "{child_release.name}" goto wait_for_release\r\n'
                    f'echo late> "{child_late.name}"\r\n',
                    encoding="utf-8",
                )
                # Prove the exact child payload can observe release and write its
                # late marker when it is not under the AppContainer Job.
                host_control = subprocess.Popen(
                    [str(command), "/d", "/c", f".\\{child_script.name}"],
                    cwd=workspace,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                try:
                    deadline = time.monotonic() + 10
                    while (
                        not child_started.is_file()
                        and host_control.poll() is None
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.05)
                    self.assertTrue(
                        child_started.is_file(),
                        "host positive control did not start the descendant",
                    )
                    child_release.write_text("release", encoding="utf-8")
                    deadline = time.monotonic() + 5
                    while not child_late.is_file() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(
                        child_late.is_file(),
                        "host positive control did not write the late marker",
                    )
                    host_control.wait(timeout=5)
                    self.assertEqual(host_control.returncode, 0)
                finally:
                    if not child_release.exists():
                        child_release.write_text("release", encoding="utf-8")
                    try:
                        host_control.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        host_control.kill()
                        host_control.wait(timeout=5)
                self._workflow_notice(
                    "descendant payload positive control",
                    f"started={child_started.is_file()} late_marker={child_late.is_file()} "
                    f"exit={host_control.returncode}",
                )
                child_started.unlink(missing_ok=True)
                child_late.unlink(missing_ok=True)
                child_release.unlink(missing_ok=True)
                script = workspace / "probe.cmd"
                script.write_text(
                    "@echo off\r\n"
                    f'echo workspace-write-ok> "{allowed_write.name}"\r\n'
                    f'type "{os.path.relpath(nested / "input.txt", workspace)}" '
                    f'> "{copied_nested.name}"\r\n'
                    f'type "{os.path.relpath(outside_secret, workspace)}" '
                    f'> "{copied_secret.name}"\r\n'
                    f'echo escape> "{os.path.relpath(outside_write, workspace)}"\r\n'
                    f'"{curl}" --noproxy "*" --connect-timeout 1 --max-time 2 '
                    f'"{url}" > "network.txt" 2>&1\r\n'
                    f'start "" /b cmd.exe /d /c .\\{child_script.name} '
                    f'> "{child_launch_log.name}" 2>&1\r\n'
                    ":wait_for_child\r\n"
                    f'if not exist "{child_started.name}" goto wait_for_child\r\n'
                    f'echo reached-end> "{script_complete.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                # Use a cwd-relative entry point so access stays within the task ACL.
                result = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{script.name}"],
                    cwd=workspace, timeout_seconds=12, process_limit=8,
                )
                try:
                    child_launch_output = child_launch_log.read_text(
                        encoding="utf-8", errors="replace",
                    ).casefold()
                except OSError:
                    child_launch_output = ""
                if "access is denied" in child_launch_output or "access denied" in child_launch_output:
                    child_launch_error_class = "access_denied"
                elif "not recognized" in child_launch_output or "cannot find" in child_launch_output:
                    child_launch_error_class = "command_or_script_not_found"
                elif child_launch_output:
                    child_launch_error_class = "other_output"
                else:
                    child_launch_error_class = "no_output"
                self._workflow_notice(
                    "workspace and network probe",
                    f"executed={result.executed} exit={result.exit_code} error={result.error} "
                    f"cleanup={result.cleanup_ok} script_complete={script_complete.is_file()} "
                    f"workspace_write={allowed_write.is_file()} nested_copy={copied_nested.is_file()} "
                    f"outside_write={outside_write.exists()} child_started={child_started.is_file()} "
                    f"child_launch_log={child_launch_log.is_file()} "
                    f"child_launch_error_class={child_launch_error_class} detail={result.detail}",
                )

                self.assertTrue(result.executed, result)
                self.assertIsNone(result.error, result)
                self.assertTrue(result.cleanup_ok, result)
                self.assertTrue(
                    script_complete.is_file(),
                    "AppContainer workspace probe did not reach its completion marker",
                )
                self.assertEqual(result.exit_code, 0, result)
                self.assertEqual(allowed_write.read_text(encoding="utf-8").strip(), "workspace-write-ok")
                self.assertEqual(
                    (nested / "input.txt").read_text(encoding="utf-8"),
                    "existing-workspace-file",
                )
                self.assertEqual(
                    copied_nested.read_text(encoding="utf-8").strip(),
                    "existing-workspace-file",
                )
                self.assertNotIn("must-not-enter-appcontainer", copied_secret.read_text(encoding="utf-8"))
                self.assertFalse(outside_write.exists())
                self.assertEqual(requests, [], "AppContainer unexpectedly reached localhost")
                self.assertTrue(
                    child_started.is_file(),
                    "AppContainer descendant did not start; check the bounded launch diagnostic",
                )
                child_release.write_text("release", encoding="utf-8")
                deadline = time.monotonic() + 5
                while not child_late.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(child_late.exists(), "AppContainer Job left a descendant alive")

                child_started.unlink()
                child_late.unlink(missing_ok=True)
                child_release.unlink(missing_ok=True)
                timeout_script = workspace / "timeout-parent.cmd"
                timeout_script.write_text(
                    "@echo off\r\n"
                    f'start "" /b cmd.exe /d /c .\\{child_script.name}\r\n'
                    ":hold\r\n"
                    "goto hold\r\n",
                    encoding="utf-8",
                )
                timed_out = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{timeout_script.name}"],
                    cwd=workspace, timeout_seconds=2, process_limit=8,
                )
                self._workflow_notice(
                    "timeout cleanup probe",
                    f"executed={timed_out.executed} error={timed_out.error} "
                    f"cleanup={timed_out.cleanup_ok} detail={timed_out.detail}",
                )
                self.assertTrue(timed_out.executed, timed_out)
                self.assertEqual(timed_out.error, "timeout", timed_out)
                self.assertTrue(timed_out.cleanup_ok, timed_out)
                self.assertTrue(child_started.is_file(), "timeout descendant did not start")
                child_release.write_text("release", encoding="utf-8")
                deadline = time.monotonic() + 5
                while not child_late.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(child_late.exists(), "timeout left an AppContainer descendant alive")

                limited_marker = workspace / "process-limit-child.txt"
                limited_parent_attempted = workspace / "process-limit-parent-attempted.txt"
                limited_status = workspace / "process-limit-launch-status.txt"
                limited_child = workspace / "process-limit-child.cmd"
                limited_child.write_text(
                    "@echo off\r\n"
                    f'echo escaped> "{limited_marker.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                limited_parent = workspace / "process-limit-parent.cmd"
                # Keep whitespace before `>` so CMD does not treat a status digit as an FD.
                limited_parent.write_text(
                    "@echo off\r\n"
                    f'echo attempted> "{limited_parent_attempted.name}"\r\n'
                    f'cmd.exe /d /c .\\{limited_child.name}\r\n'
                    f'echo exit_code=%errorlevel% > "{limited_status.name}"\r\n'
                    "exit /b 0\r\n",
                    encoding="utf-8",
                )
                limit_control = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{limited_parent.name}"],
                    cwd=workspace, timeout_seconds=5, process_limit=2,
                )
                positive_launch_status = self._read_cmd_exit_status(limited_status)
                self._workflow_notice(
                    "process limit positive control",
                    f"executed={limit_control.executed} exit={limit_control.exit_code} "
                    f"cleanup={limit_control.cleanup_ok} "
                    f"parent_attempted={limited_parent_attempted.is_file()} "
                    f"child_marker={limited_marker.is_file()} "
                    f"launch_status={positive_launch_status}",
                )
                self.assertTrue(limit_control.executed, limit_control)
                self.assertEqual(limit_control.exit_code, 0, limit_control)
                self.assertTrue(limit_control.cleanup_ok, limit_control)
                self.assertTrue(limited_parent_attempted.is_file(), "parent spawn attempt was not recorded")
                self.assertTrue(
                    limited_marker.is_file(),
                    "the process-limit payload must start without the one-process cap",
                )
                self.assertEqual(positive_launch_status, 0, "positive child launch must succeed")
                limited_marker.unlink()
                limited_parent_attempted.unlink()
                limited_status.unlink(missing_ok=True)
                limited = run_windows_appcontainer(
                    [str(command), "/d", "/c", f".\\{limited_parent.name}"],
                    cwd=workspace, timeout_seconds=5, process_limit=1,
                )
                negative_launch_status = self._read_cmd_exit_status(limited_status)
                self._workflow_notice(
                    "process limit probe",
                    f"executed={limited.executed} exit={limited.exit_code} error={limited.error} "
                    f"cleanup={limited.cleanup_ok} "
                    f"parent_attempted={limited_parent_attempted.is_file()} "
                    f"child_marker={limited_marker.is_file()} "
                    f"launch_status={negative_launch_status} detail={limited.detail}",
                )
                self.assertTrue(limited.executed, limited)
                self.assertEqual(limited.exit_code, 0, limited)
                self.assertTrue(limited.cleanup_ok, limited)
                self.assertTrue(limited_parent_attempted.is_file(), "parent did not reach child creation")
                self.assertFalse(limited_marker.exists(), "Job active-process limit was not enforced")
                self.assertIsNotNone(negative_launch_status, "child launch result was not recorded")
                self.assertNotEqual(negative_launch_status, 0, "one-process cap must reject child creation")
            finally:
                server.shutdown()
                server.server_close()

    @unittest.skipUnless(
        sys.platform == "win32"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
        and os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_STAGING") == "true"
        and os.environ.get("ICODE_DIAGNOSTIC_REVIEWER_SNAPSHOT") == "true",
        "Windows AppContainer Reviewer snapshot probe runs only in its required native CI job",
    )
    def test_Reviewer快照AppContainer只读边界与Job清理(self) -> None:
        if Path(sys.prefix).resolve() != Path(sys.base_prefix).resolve():
            self.fail("CI Python must be a base interpreter for disposable runtime staging")

        expected_standard_user_sid = os.environ.get(
            "ICODE_DIAGNOSTIC_STANDARD_USER_SID", "",
        )
        parent_standard_user_status = _current_process_standard_user_status(
            expected_standard_user_sid,
        )
        parent_standard_user_verified = parent_standard_user_status == "verified"
        self.assertTrue(
            parent_standard_user_verified,
            "native Reviewer probe host token check failed: "
            f"{parent_standard_user_status}",
        )

        source_root = Path(sys.base_prefix).resolve(strict=True)
        source_executable = source_root / Path(sys.executable).name
        self.assertTrue(source_executable.is_file(), "host Python executable is missing")

        with tempfile.TemporaryDirectory(prefix="icode-reviewer-appcontainer-probe-") as raw:
            temp_root = Path(raw)
            scratch = temp_root / "task-scratch"
            scratch.mkdir()
            staged_runtime = temp_root / f"icode-runtime-staging-reviewer-{uuid.uuid4().hex}"
            snapshot = temp_root / f"icode-reviewer-snapshot-{uuid.uuid4().hex}"
            outside_root = temp_root / "outside-snapshot"
            original_workspace = temp_root / "original-workspace-canary"
            ledger_root = temp_root / "ledger-canary"
            for directory in (snapshot, outside_root, original_workspace, ledger_root):
                directory.mkdir()

            allowed_content = b"def reviewed_value():\n    return 'safe-snapshot'\n"
            approved_file = snapshot / "reviewed.py"
            approved_file.write_bytes(allowed_content)
            new_file = snapshot / "new.py"
            mutable_file = snapshot / "mutable.py"
            write_canary_original = b"original\n"
            write_payload = b"changed"
            mutable_file.write_bytes(write_canary_original)
            deletable_file = snapshot / "delete.py"
            deletable_file.write_bytes(b"delete sentinel\n")
            rename_file = snapshot / "rename.py"
            rename_file.write_bytes(b"rename sentinel\n")
            dacl_file = snapshot / "dacl.py"
            dacl_file.write_bytes(b"dacl sentinel\n")
            outside_file = outside_root / "sentinel.txt"
            outside_file.write_text("outside snapshot", encoding="ascii")
            dacl_control_verified = _dacl_write_control_succeeds(outside_file)
            self.assertTrue(
                dacl_control_verified,
                "WRITE_DAC positive control must open and perform SetSecurityInfo",
            )
            workspace_file = original_workspace / "sentinel.txt"
            workspace_file.write_text("original workspace", encoding="ascii")
            ledger_file = ledger_root / "verification-ledger.json"
            ledger_file.write_text('{"private":"synthetic canary"}', encoding="ascii")

            home_temp = tempfile.TemporaryDirectory(
                prefix="icode-reviewer-home-canary-", dir=Path.home(),
            )
            network_servers: list[socketserver.ThreadingTCPServer] = []
            network_threads: list[threading.Thread] = []
            network_host_controls = {"ipv4": False, "ipv6": False}
            try:
                home_file = Path(home_temp.name) / "sentinel.txt"
                home_file.write_text("user home canary", encoding="ascii")
                class _CanaryHandler(socketserver.BaseRequestHandler):
                    def handle(self) -> None:
                        self.request.settimeout(2)
                        chunks: list[bytes] = []
                        received = 0
                        while received < 256:
                            try:
                                chunk = self.request.recv(256 - received)
                            except OSError:
                                break
                            if not chunk:
                                break
                            chunks.append(chunk)
                            received += len(chunk)
                        payload = b"".join(chunks)
                        self.server.received_canaries.append(payload)

                class _CanaryServer(socketserver.ThreadingTCPServer):
                    allow_reuse_address = True
                    daemon_threads = True

                    def __init__(
                        self, address: tuple[str, int] | tuple[str, int, int, int],
                        family: int,
                    ) -> None:
                        self.address_family = family
                        self.received_canaries: list[bytes] = []
                        super().__init__(address, _CanaryHandler)

                host_positive_canary = b"icode-reviewer-host-positive-control-v1"
                for label, family, address in (
                    ("ipv4", socket.AF_INET, "127.0.0.1"),
                    ("ipv6", socket.AF_INET6, "::1"),
                ):
                    listener = _CanaryServer((address, 0), family)
                    network_servers.append(listener)
                    listener_thread = threading.Thread(
                        target=listener.serve_forever, daemon=True,
                    )
                    network_threads.append(listener_thread)
                    listener_thread.start()
                    with socket.socket(family, socket.SOCK_STREAM) as control:
                        control.settimeout(3)
                        control.connect(listener.server_address)
                        control.sendall(host_positive_canary)
                    deadline = time.monotonic() + 3
                    while (
                        host_positive_canary not in listener.received_canaries
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    network_host_controls[label] = (
                        listener.received_canaries == [host_positive_canary]
                    )
                    self.assertTrue(
                        network_host_controls[label],
                        f"{label} host listener positive control failed",
                    )
                    listener.received_canaries.clear()

                network_canary = b"icode-reviewer-appcontainer-network-canary-v1"
                ipv4_loopback_port = network_servers[0].server_address[1]
                ipv6_loopback_port = network_servers[1].server_address[1]
                original_snapshot_hash = hashlib.sha256(approved_file.read_bytes()).hexdigest()
                stage_summary = windows_appcontainer._copy_runtime_tree_for_diagnostic(
                    source_root, staged_runtime,
                )
                staged_executable = staged_runtime / source_executable.name
                self.assertTrue(staged_executable.is_file(), "staged Python executable is missing")
                positive_control = subprocess.run(
                    [
                        str(staged_executable), "-I", "-c",
                        "import ctypes,hashlib,json,pathlib,subprocess; "
                        "print(json.dumps({'runtime_ready':True}))",
                    ],
                    cwd=scratch, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=15, shell=False, check=False,
                )
                self.assertEqual(
                    positive_control.returncode, 0,
                    "staged Python host positive control failed",
                )

                result_file = scratch / "reviewer-probe-result.json"
                child_ready_file = scratch / "reviewer-child-ready"
                child_code = (
                    "from pathlib import Path; import time; "
                    f"Path({str(child_ready_file)!r}).write_text('ready'); time.sleep(30)"
                )
                script = (
                    "import ctypes,hashlib,json,os,pathlib,select,socket,subprocess,sys,time\n"
                    "import ctypes.wintypes as wintypes\n"
                    "def query_token():\n"
                    "    import ctypes.wintypes as wintypes\n"
                    "    kernel=ctypes.WinDLL('kernel32',use_last_error=True)\n"
                    "    advapi=ctypes.WinDLL('advapi32',use_last_error=True)\n"
                    "    kernel.GetCurrentProcess.argtypes=[]\n"
                    "    kernel.GetCurrentProcess.restype=ctypes.c_void_p\n"
                    "    kernel.CloseHandle.argtypes=[ctypes.c_void_p]\n"
                    "    kernel.CloseHandle.restype=wintypes.BOOL\n"
                    "    kernel.CheckTokenMembershipEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,"
                    "wintypes.DWORD,ctypes.POINTER(wintypes.BOOL)]\n"
                    "    kernel.CheckTokenMembershipEx.restype=wintypes.BOOL\n"
                    "    kernel.LocalFree.argtypes=[ctypes.c_void_p]\n"
                    "    kernel.LocalFree.restype=ctypes.c_void_p\n"
                    "    advapi.OpenProcessToken.argtypes=[ctypes.c_void_p,wintypes.DWORD,"
                    "ctypes.POINTER(ctypes.c_void_p)]\n"
                    "    advapi.OpenProcessToken.restype=wintypes.BOOL\n"
                    "    advapi.DuplicateToken.argtypes=[ctypes.c_void_p,ctypes.c_int,"
                    "ctypes.POINTER(ctypes.c_void_p)]\n"
                    "    advapi.DuplicateToken.restype=wintypes.BOOL\n"
                    "    advapi.GetTokenInformation.argtypes=[ctypes.c_void_p,ctypes.c_int,"
                    "ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]\n"
                    "    advapi.GetTokenInformation.restype=wintypes.BOOL\n"
                    "    advapi.ConvertStringSidToSidW.argtypes=[wintypes.LPCWSTR,"
                    "ctypes.POINTER(ctypes.c_void_p)]\n"
                    "    advapi.ConvertStringSidToSidW.restype=wintypes.BOOL\n"
                    "    token=ctypes.c_void_p(); admin_token=ctypes.c_void_p(); returned=wintypes.DWORD()\n"
                    "    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(),0x000a,"
                    "ctypes.byref(token)): raise ctypes.WinError(ctypes.get_last_error())\n"
                    "    try:\n"
                    "        app=wintypes.DWORD(); elevated=wintypes.DWORD()\n"
                    "        if not advapi.GetTokenInformation(token,29,ctypes.byref(app),"
                    "ctypes.sizeof(app),ctypes.byref(returned)): raise ctypes.WinError(ctypes.get_last_error())\n"
                    "        if not advapi.GetTokenInformation(token,20,ctypes.byref(elevated),"
                    "ctypes.sizeof(elevated),ctypes.byref(returned)): raise ctypes.WinError(ctypes.get_last_error())\n"
                    "        sid_size=wintypes.DWORD(); ctypes.set_last_error(0)\n"
                    "        advapi.GetTokenInformation(token,31,None,0,ctypes.byref(sid_size))\n"
                    "        if ctypes.get_last_error()!=122 or sid_size.value<ctypes.sizeof(ctypes.c_void_p):\n"
                    "            raise ctypes.WinError(ctypes.get_last_error() or 87)\n"
                    "        sid_buffer=ctypes.create_string_buffer(sid_size.value)\n"
                    "        if not advapi.GetTokenInformation(token,31,sid_buffer,sid_size.value,"
                    "ctypes.byref(returned)): raise ctypes.WinError(ctypes.get_last_error())\n"
                    "        sid=ctypes.cast(sid_buffer,ctypes.POINTER(ctypes.c_void_p)).contents.value\n"
                    "        if not sid: raise RuntimeError('missing package SID')\n"
                    "        capability_buffer=ctypes.create_string_buffer(4096)\n"
                    "        if not advapi.GetTokenInformation(token,30,capability_buffer,"
                    "len(capability_buffer),ctypes.byref(returned)): raise ctypes.WinError(ctypes.get_last_error())\n"
                    "        capability_count=ctypes.cast(capability_buffer,"
                    "ctypes.POINTER(wintypes.DWORD)).contents.value\n"
                    "        admin_sid=ctypes.c_void_p(); admin_enabled=wintypes.BOOL()\n"
                    "        if not advapi.ConvertStringSidToSidW('S-1-5-32-544',ctypes.byref(admin_sid)):\n"
                    "            raise ctypes.WinError(ctypes.get_last_error())\n"
                    "        try:\n"
                    "            if not advapi.DuplicateToken(token,2,ctypes.byref(admin_token)):\n"
                    "                raise ctypes.WinError(ctypes.get_last_error())\n"
                    "            if not kernel.CheckTokenMembershipEx(admin_token,admin_sid,"
                    "0x00000001,ctypes.byref(admin_enabled)):\n"
                    "                raise ctypes.WinError(ctypes.get_last_error())\n"
                    "        finally:\n"
                    "            if admin_token.value: kernel.CloseHandle(admin_token)\n"
                    "            kernel.LocalFree(admin_sid)\n"
                    "        return {'appcontainer':app.value==1,'package_sid':True,"
                    "'capability_count':capability_count,'elevated':elevated.value!=0,"
                    "'admin_group_enabled':admin_enabled.value!=0}\n"
                    "    finally:\n"
                    "        kernel.CloseHandle(token)\n"
                    "access_errors={}\n"
                    "close_errors={}\n"
                    "write_diagnostics={}\n"
                    f"write_payload={write_payload!r}\n"
                    f"network_canary={network_canary!r}\n"
                    f"ipv4_loopback_port={ipv4_loopback_port!r}\n"
                    f"ipv6_loopback_port={ipv6_loopback_port!r}\n"
                    "WSAEACCES=10013; WSAEWOULDBLOCK=10035; WSAEINPROGRESS=10036\n"
                    "def bounded_error_code(value):\n"
                    "    return value if type(value) is int and -0x80000000<=value<=0xffffffff else -1\n"
                    "def network_connect_denied(family,address,port):\n"
                    "    try: connection=socket.socket(family,socket.SOCK_STREAM)\n"
                    "    except OSError as exc:\n"
                    "        code=bounded_error_code(getattr(exc,'winerror',None))\n"
                    "        return False,False,False,code,False,False\n"
                    "    try:\n"
                    "        try:\n"
                    "            connection.setblocking(False)\n"
                    "        except OSError as exc:\n"
                    "            code=bounded_error_code(getattr(exc,'winerror',None))\n"
                    "            return False,False,False,code,False,False\n"
                    "        try:\n"
                    "            code=bounded_error_code(connection.connect_ex((address,port)))\n"
                    "        except OSError as exc:\n"
                    "            code=bounded_error_code(getattr(exc,'winerror',None))\n"
                    "            return True,False,code==WSAEACCES,code,False,True\n"
                    "        if code in (WSAEWOULDBLOCK,WSAEINPROGRESS):\n"
                    "            # WSAEWOULDBLOCK is pending; wait for completion before classifying.\n"
                    "            try:\n"
                    "                _readable,writable,exceptional=select.select([], [connection], [connection], 3)\n"
                    "            except OSError as exc:\n"
                    "                code=bounded_error_code(getattr(exc,'winerror',None))\n"
                    "                return True,False,False,code,False,False\n"
                    "            if not writable and not exceptional: return True,False,False,code,True,False\n"
                    "            try:\n"
                    "                code=bounded_error_code(connection.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR))\n"
                    "            except OSError as exc:\n"
                    "                code=bounded_error_code(getattr(exc,'winerror',None))\n"
                    "                return True,False,False,code,False,False\n"
                    "            terminal_error=True\n"
                    "        else: terminal_error=(code!=0)\n"
                    "        if code!=0: return True,False,code==WSAEACCES,code,False,terminal_error\n"
                    "        try: connection.sendall(network_canary)\n"
                    "        except OSError: pass\n"
                    "        return True,True,False,0,False,False\n"
                    "    finally: connection.close()\n"
                    "ipv4_network_attempted,ipv4_network_connected,"
                    "ipv4_network_connect_denied,ipv4_network_error,"
                    "ipv4_network_wait_expired,ipv4_network_terminal_error="
                    "network_connect_denied(socket.AF_INET,'127.0.0.1',ipv4_loopback_port)\n"
                    "ipv6_network_attempted,ipv6_network_connected,"
                    "ipv6_network_connect_denied,ipv6_network_error,"
                    "ipv6_network_wait_expired,ipv6_network_terminal_error="
                    "network_connect_denied(socket.AF_INET6,'::1',ipv6_loopback_port)\n"
                    "def access_denied(key,call):\n"
                    "    try: call()\n"
                    "    except OSError as exc:\n"
                    "        code=getattr(exc,'winerror',None)\n"
                    "        access_errors[key]={'winerror':bounded_error_code(code),"
                    "'errno':bounded_error_code(getattr(exc,'errno',None))}\n"
                    "        if code==5: return True\n"
                    "    return False\n"
                    "def dacl_write_dac_denied(path):\n"
                    "    import ctypes.wintypes as wintypes\n"
                    "    kernel=ctypes.WinDLL('kernel32',use_last_error=True)\n"
                    "    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,"
                    "wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]\n"
                    "    kernel.CreateFileW.restype=ctypes.c_void_p\n"
                    "    kernel.CloseHandle.argtypes=[ctypes.c_void_p]; kernel.CloseHandle.restype=wintypes.BOOL\n"
                    "    ctypes.set_last_error(0)\n"
                    "    handle=kernel.CreateFileW(str(path),0x00060000,0x7,None,3,0x80,None)\n"
                    "    if handle==ctypes.c_void_p(-1).value:\n"
                    "        error_code=ctypes.get_last_error()\n"
                    "        if error_code==5: return True\n"
                    "        access_errors['dacl_write_dac']={'winerror':bounded_error_code(error_code),'errno':-1}\n"
                    "        return False\n"
                    "    kernel.CloseHandle(handle)\n"
                    "    return False\n"
                    "native_kernel=ctypes.WinDLL('kernel32',use_last_error=True)\n"
                    "native_kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,"
                    "wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]\n"
                    "native_kernel.CreateFileW.restype=ctypes.c_void_p\n"
                    "native_kernel.ReadFile.argtypes=[ctypes.c_void_p,ctypes.c_void_p,"
                    "wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]\n"
                    "native_kernel.ReadFile.restype=wintypes.BOOL\n"
                    "native_kernel.WriteFile.argtypes=[ctypes.c_void_p,ctypes.c_void_p,"
                    "wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p]\n"
                    "native_kernel.WriteFile.restype=wintypes.BOOL\n"
                    "native_kernel.CloseHandle.argtypes=[ctypes.c_void_p]\n"
                    "native_kernel.CloseHandle.restype=wintypes.BOOL\n"
                    "INVALID_HANDLE_VALUE=ctypes.c_void_p(-1).value\n"
                    "def native_file_access(key,path,desired_access,disposition,io_kind=None):\n"
                    "    data=b''; error_code=None; cleanup_ok=True; stage='createfilew'\n"
                    f"    requested_bytes={len(write_payload)} if io_kind=='write' else 0\n"
                    "    transferred=wintypes.DWORD(); io_succeeded=None\n"
                    "    ctypes.set_last_error(0)\n"
                    "    handle=native_kernel.CreateFileW(str(path),desired_access,0x7,None,"
                    "disposition,0x80,None)\n"
                    "    if handle==INVALID_HANDLE_VALUE:\n"
                    "        return data,ctypes.get_last_error(),True,stage,transferred.value,io_succeeded\n"
                    "    if handle is None: return data,0,True,stage,transferred.value,io_succeeded\n"
                    "    try:\n"
                    "        if io_kind=='read':\n"
                    "            stage='readfile'; buffer=ctypes.create_string_buffer(4096)\n"
                    "            ctypes.set_last_error(0)\n"
                    "            if not native_kernel.ReadFile(handle,buffer,len(buffer),"
                    "ctypes.byref(transferred),None):\n"
                    "                io_succeeded=False\n"
                    "                error_code=ctypes.get_last_error()\n"
                    "            else: io_succeeded=True; data=buffer.raw[:transferred.value]\n"
                    "        elif io_kind=='write':\n"
                    "            stage='writefile'; payload=ctypes.create_string_buffer(write_payload)\n"
                    "            ctypes.set_last_error(0)\n"
                    "            if not native_kernel.WriteFile(handle,payload,requested_bytes,"
                    "ctypes.byref(transferred),None):\n"
                    "                io_succeeded=False\n"
                    "                error_code=ctypes.get_last_error()\n"
                    "            else:\n"
                    "                io_succeeded=True\n"
                    "                if transferred.value!=requested_bytes: error_code=0\n"
                    "    finally:\n"
                    "        try:\n"
                    "            ctypes.set_last_error(0)\n"
                    "            if not native_kernel.CloseHandle(handle):\n"
                    "                close_error=ctypes.get_last_error()\n"
                    "                close_errors[key]=bounded_error_code(close_error)\n"
                    "                cleanup_ok=False\n"
                    "        except Exception:\n"
                    "            close_errors[key]=-1; cleanup_ok=False\n"
                    "    return data,error_code,cleanup_ok,stage,transferred.value,io_succeeded\n"
                    "def native_access_denied(key,path,desired_access,io_kind=None,disposition=3):\n"
                    "    _data,code,cleanup_ok,stage,bytes_transferred,io_succeeded=native_file_access("
                    "key,path,desired_access,disposition,io_kind)\n"
                    "    requested_bytes=len(write_payload) if io_kind=='write' else 0\n"
                    "    if key=='write': write_diagnostics['write']={'stage':stage,"
                    "'io_succeeded':io_succeeded,'requested_bytes':requested_bytes,"
                    "'bytes_transferred':bounded_error_code(bytes_transferred)}\n"
                    "    access_errors[key]={'winerror':bounded_error_code(code),'errno':-1}\n"
                    "    denied=cleanup_ok and code==5\n"
                    "    if key=='write' and bytes_transferred!=0: denied=False\n"
                    "    return denied\n"
                    "token=query_token()\n"
                    f"approved=pathlib.Path({str(approved_file)!r})\n"
                    f"expected={original_snapshot_hash!r}\n"
                    f"outside=pathlib.Path({str(outside_file)!r})\n"
                    f"workspace=pathlib.Path({str(workspace_file)!r})\n"
                    f"home=pathlib.Path({str(home_file)!r})\n"
                    f"ledger=pathlib.Path({str(ledger_file)!r})\n"
                    f"mutable=pathlib.Path({str(mutable_file)!r})\n"
                    f"deletable=pathlib.Path({str(deletable_file)!r})\n"
                    f"rename_source=pathlib.Path({str(rename_file)!r})\n"
                    f"rename_target=pathlib.Path({str(snapshot / 'renamed.py')!r})\n"
                    f"dacl_file=pathlib.Path({str(dacl_file)!r})\n"
                    f"new_file=pathlib.Path({str(new_file)!r})\n"
                    "approved_content,approved_error,approved_cleanup,approved_stage,"
                    "approved_bytes,approved_io=native_file_access("
                    "'approved_read',approved,0x80000000,3,'read')\n"
                    "facts={'approved_read':approved_error is None and approved_cleanup and "
                    "hashlib.sha256(approved_content).hexdigest()==expected,"
                    "'outside_snapshot_denied':native_access_denied('outside_snapshot',outside,0x80000000,'read'),"
                    "'workspace_denied':native_access_denied('workspace',workspace,0x80000000,'read'),"
                    "'home_denied':native_access_denied('home',home,0x80000000,'read'),"
                    "'ledger_denied':native_access_denied('ledger',ledger,0x80000000,'read'),"
                    "'write_denied':native_access_denied('write',mutable,0x40000000,'write'),"
                    "'delete_denied':access_denied('delete',lambda:deletable.unlink()),"
                    "'rename_denied':access_denied('rename',lambda:rename_source.rename(rename_target)),"
                    "'create_denied':native_access_denied('create',new_file,0x40000000,None,1),"
                    "'dacl_write_dac_denied':dacl_write_dac_denied(dacl_file)}\n"
                    "facts['ipv4_network_attempted']=ipv4_network_attempted\n"
                    "facts['ipv4_network_connected']=ipv4_network_connected\n"
                    "facts['ipv4_network_connect_denied']=ipv4_network_connect_denied\n"
                    "facts['ipv4_network_error']=bounded_error_code(ipv4_network_error)\n"
                    "facts['ipv4_network_wait_expired']=ipv4_network_wait_expired\n"
                    "facts['ipv4_network_terminal_error']=ipv4_network_terminal_error\n"
                    "facts['ipv6_network_attempted']=ipv6_network_attempted\n"
                    "facts['ipv6_network_connected']=ipv6_network_connected\n"
                    "facts['ipv6_network_connect_denied']=ipv6_network_connect_denied\n"
                    "facts['ipv6_network_error']=bounded_error_code(ipv6_network_error)\n"
                    "facts['ipv6_network_wait_expired']=ipv6_network_wait_expired\n"
                    "facts['ipv6_network_terminal_error']=ipv6_network_terminal_error\n"
                    "facts['access_errors']=access_errors\n"
                    "facts['close_errors']=close_errors\n"
                    "facts['write_diagnostics']=write_diagnostics\n"
                    f"child=subprocess.Popen([sys.executable,'-I','-c',{child_code!r}])\n"
                    f"deadline=time.monotonic()+5\n"
                    f"while not pathlib.Path({str(child_ready_file)!r}).is_file() and time.monotonic()<deadline: time.sleep(.05)\n"
                    "facts['child_started']=pathlib.Path(" + repr(str(child_ready_file)) + ").is_file()\n"
                    "facts['child_pid']=child.pid\n"
                    "pathlib.Path(" + repr(str(result_file)) + ").write_text("
                    "json.dumps({'token':token,'facts':facts}),encoding='ascii')\n"
                    "if not (token['appcontainer'] and token['package_sid'] and token['capability_count']==0 "
                    "and not token['elevated'] and not token['admin_group_enabled'] "
                    "and all(value for key,value in facts.items() "
                    "if key not in {'child_pid','access_errors','close_errors','write_diagnostics',"
                    "'ipv4_network_connected','ipv4_network_error','ipv4_network_wait_expired',"
                    "'ipv4_network_terminal_error','ipv6_network_connected','ipv6_network_error',"
                    "'ipv6_network_wait_expired','ipv6_network_terminal_error'})): raise SystemExit(78)\n"
                )
                compile(script, "<reviewer-snapshot-probe>", "exec")
                try:
                    write_canary_before = mutable_file.read_bytes()
                    write_canary_before_length = len(write_canary_before)
                    write_canary_before_sha256 = hashlib.sha256(
                        write_canary_before,
                    ).hexdigest()
                    write_canary_before_unchanged = (
                        write_canary_before == write_canary_original
                    )
                except OSError:
                    write_canary_before_length = -1
                    write_canary_before_sha256 = "unavailable"
                    write_canary_before_unchanged = False
                candidate = run_windows_appcontainer(
                    [str(staged_executable), "-I", "-c", script],
                    cwd=scratch, timeout_seconds=20, process_limit=8,
                    _diagnostic_runtime_acl=True,
                    _diagnostic_runtime_roots=(staged_runtime,),
                    _diagnostic_reviewer_snapshot_roots=(snapshot,),
                )

                try:
                    result = json.loads(result_file.read_text(encoding="ascii"))
                except (OSError, ValueError):
                    result = {}
                facts = result.get("facts") if isinstance(result, dict) else {}
                token = result.get("token") if isinstance(result, dict) else {}
                facts = facts if isinstance(facts, dict) else {}
                token = token if isinstance(token, dict) else {}
                raw_access_errors = facts.get("access_errors")
                if not isinstance(raw_access_errors, dict):
                    raw_access_errors = {}
                access_error_keys = {
                    "outside_snapshot", "workspace", "home", "ledger",
                    "write", "delete", "rename", "create", "dacl_write_dac",
                }
                access_errors: dict[str, dict[str, int]] = {}
                for key, details in raw_access_errors.items():
                    if key not in access_error_keys or not isinstance(details, dict):
                        continue
                    winerror = details.get("winerror")
                    error_number = details.get("errno")
                    if (
                        type(winerror) is int
                        and -1 <= winerror <= 0xFFFFFFFF
                        and type(error_number) is int
                        and -1 <= error_number <= 0xFFFFFFFF
                    ):
                        access_errors[key] = {
                            "winerror": winerror,
                            "errno": error_number,
                        }

                raw_close_errors = facts.get("close_errors")
                if not isinstance(raw_close_errors, dict):
                    raw_close_errors = {}
                close_error_keys = {
                    "approved_read", "outside_snapshot", "workspace", "home",
                    "ledger", "write", "create",
                }
                close_errors: dict[str, int] = {}
                for key, error_number in raw_close_errors.items():
                    if (
                        key in close_error_keys
                        and type(error_number) is int
                        and -1 <= error_number <= 0xFFFFFFFF
                    ):
                        close_errors[key] = error_number

                raw_write_diagnostics = facts.get("write_diagnostics")
                write_details = (
                    raw_write_diagnostics.get("write")
                    if isinstance(raw_write_diagnostics, dict)
                    else None
                )
                if not isinstance(write_details, dict):
                    write_details = {}
                raw_stage = write_details.get("stage")
                stage = (
                    raw_stage
                    if isinstance(raw_stage, str) and raw_stage in {"createfilew", "writefile"}
                    else "missing"
                )
                raw_io_succeeded = write_details.get("io_succeeded")
                io_succeeded = (
                    raw_io_succeeded
                    if type(raw_io_succeeded) is bool or raw_io_succeeded is None
                    else None
                )
                raw_requested_bytes = write_details.get("requested_bytes")
                requested_bytes = (
                    raw_requested_bytes
                    if type(raw_requested_bytes) is int
                    and raw_requested_bytes == len(write_payload)
                    else -1
                )
                raw_bytes_transferred = write_details.get("bytes_transferred")
                bytes_transferred = (
                    raw_bytes_transferred
                    if type(raw_bytes_transferred) is int
                    and 0 <= raw_bytes_transferred <= len(write_payload)
                    else -1
                )
                write_diagnostics = {
                    "stage": stage,
                    "io_succeeded": io_succeeded,
                    "requested_bytes": requested_bytes,
                    "bytes_transferred": bytes_transferred,
                }

                def network_error_code(key: str) -> int:
                    value = facts.get(key)
                    return (
                        value
                        if type(value) is int and -1 <= value <= 0xFFFFFFFF
                        else -1
                    )

                # Give accepted loopback connections time to reach the handler before
                # interpreting a missing canary as evidence of denial.
                network_deadline = time.monotonic() + 0.25
                while (
                    time.monotonic() < network_deadline
                    and not any(
                        network_canary in listener.received_canaries
                        for listener in network_servers
                    )
                ):
                    time.sleep(0.01)

                try:
                    new_file.unlink(missing_ok=True)
                    create_cleanup_ok = not new_file.exists() and not new_file.is_symlink()
                except OSError:
                    create_cleanup_ok = False
                try:
                    write_canary_content = mutable_file.read_bytes()
                    write_canary_after_length = len(write_canary_content)
                    write_canary_after_sha256 = hashlib.sha256(
                        write_canary_content,
                    ).hexdigest()
                    expected_write_result = (
                        write_payload + write_canary_original[len(write_payload):]
                    )
                    write_canary_unchanged = write_canary_content == write_canary_original
                    write_canary_matches_expected_result = (
                        write_canary_content == expected_write_result
                    )
                except OSError:
                    write_canary_unchanged = False
                    write_canary_matches_expected_result = False
                    write_canary_after_length = -1
                    write_canary_after_sha256 = "unavailable"

                child_pid = facts.get("child_pid")
                child_exited = False
                if type(child_pid) is int and child_pid > 0:
                    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
                    kernel.OpenProcess.restype = ctypes.c_void_p
                    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                    kernel.WaitForSingleObject.restype = ctypes.c_uint32
                    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                    kernel.CloseHandle.restype = ctypes.c_int
                    child_handle = kernel.OpenProcess(0x00100000, 0, child_pid)
                    if child_handle:
                        try:
                            child_exited = kernel.WaitForSingleObject(child_handle, 0) == 0
                        finally:
                            kernel.CloseHandle(child_handle)
                    else:
                        child_exited = ctypes.get_last_error() == 87

                summary = {
                    "executed": candidate.executed,
                    "exit": candidate.exit_code,
                    "cleanup": candidate.cleanup_ok,
                    "appcontainer": token.get("appcontainer") is True,
                    "package_sid": token.get("package_sid") is True,
                    "capabilities": token.get("capability_count"),
                    "elevated": token.get("elevated"),
                    "admin_group_enabled": token.get("admin_group_enabled"),
                    "write_canary_before_unchanged": write_canary_before_unchanged,
                    "ipv4_host_control": network_host_controls["ipv4"] is True,
                    "ipv4_network_attempted": facts.get("ipv4_network_attempted") is True,
                    "ipv4_network_connected": facts.get("ipv4_network_connected") is True,
                    "ipv4_network_connect_denied": (
                        facts.get("ipv4_network_connect_denied") is True
                    ),
                    "ipv4_network_error": network_error_code("ipv4_network_error"),
                    "ipv4_network_wait_expired": (
                        facts.get("ipv4_network_wait_expired") is True
                    ),
                    "ipv4_network_timed_out": _network_attempt_timed_out(
                        facts.get("ipv4_network_attempted"),
                        facts.get("ipv4_network_connected"),
                        network_error_code("ipv4_network_error"),
                        facts.get("ipv4_network_terminal_error"),
                    ),
                    "ipv4_canary_received": (
                        network_canary in network_servers[0].received_canaries
                    ),
                    "ipv6_host_control": network_host_controls["ipv6"] is True,
                    "ipv6_network_attempted": facts.get("ipv6_network_attempted") is True,
                    "ipv6_network_connected": facts.get("ipv6_network_connected") is True,
                    "ipv6_network_connect_denied": (
                        facts.get("ipv6_network_connect_denied") is True
                    ),
                    "ipv6_network_error": network_error_code("ipv6_network_error"),
                    "ipv6_network_wait_expired": (
                        facts.get("ipv6_network_wait_expired") is True
                    ),
                    "ipv6_network_timed_out": _network_attempt_timed_out(
                        facts.get("ipv6_network_attempted"),
                        facts.get("ipv6_network_connected"),
                        network_error_code("ipv6_network_error"),
                        facts.get("ipv6_network_terminal_error"),
                    ),
                    "ipv6_canary_received": (
                        network_canary in network_servers[1].received_canaries
                    ),
                    **{
                        key: facts.get(key) is True
                        for key in (
                            "approved_read", "outside_snapshot_denied", "workspace_denied",
                            "home_denied", "ledger_denied", "write_denied", "delete_denied",
                            "rename_denied", "create_denied", "dacl_write_dac_denied", "child_started",
                        )
                    },
                    "write_canary_unchanged": write_canary_unchanged,
                    "write_canary_matches_expected_result": (
                        write_canary_matches_expected_result
                    ),
                    "create_cleanup_ok": create_cleanup_ok,
                    "child_exited": child_exited,
                    "snapshot_acl_restored": (
                        "reviewer_snapshot_acl_restore_verified=true" in candidate.detail
                    ),
                    "runtime_acl_restored": "runtime_acl_restore_verified=true" in candidate.detail,
                    "staged_files": stage_summary.get("staged_entries"),
                    "access_errors": access_errors,
                    "close_errors": close_errors,
                    "write_diagnostics": write_diagnostics,
                    "write_canary_fingerprints": {
                        "before_length": write_canary_before_length,
                        "before_sha256": write_canary_before_sha256,
                        "after_length": write_canary_after_length,
                        "after_sha256": write_canary_after_sha256,
                    },
                }
                self._workflow_json_notice(
                    "Windows Reviewer probe preflight",
                    {
                        "parent_standard_user": parent_standard_user_verified,
                        "parent_standard_user_status": parent_standard_user_status,
                        "dacl_control_verified": dacl_control_verified,
                    },
                )
                self._workflow_json_notice(
                    "Windows Reviewer snapshot access",
                    {
                        key: summary[key]
                        for key in (
                            "executed", "exit", "cleanup", "appcontainer", "package_sid",
                            "capabilities", "elevated", "admin_group_enabled", "approved_read",
                            "outside_snapshot_denied", "workspace_denied", "home_denied",
                            "ledger_denied",
                        )
                    },
                )
                self._workflow_json_notice(
                    "Windows Reviewer snapshot writes and cleanup",
                    {
                        key: summary[key]
                        for key in (
                            "write_denied", "delete_denied", "rename_denied", "create_denied",
                            "dacl_write_dac_denied", "child_started", "child_exited",
                            "snapshot_acl_restored", "runtime_acl_restored", "staged_files",
                            "write_canary_unchanged", "write_canary_matches_expected_result",
                            "write_canary_before_unchanged",
                            "create_cleanup_ok",
                        )
                    },
                )
                self._workflow_json_notice(
                    "Windows Reviewer access diagnostics",
                    summary["access_errors"],
                )
                self._workflow_json_notice(
                    "Windows Reviewer handle cleanup diagnostics",
                    summary["close_errors"],
                )
                self._workflow_json_notice(
                    "Windows Reviewer WriteFile diagnostics",
                    summary["write_diagnostics"],
                )
                self._workflow_json_notice(
                    "Windows Reviewer loopback network denial",
                    {
                        key: summary[key]
                        for key in (
                            "ipv4_host_control", "ipv4_network_attempted",
                            "ipv4_network_connected", "ipv4_network_connect_denied",
                            "ipv4_network_error", "ipv4_network_wait_expired",
                            "ipv4_network_timed_out",
                            "ipv4_canary_received",
                            "ipv6_host_control", "ipv6_network_attempted",
                            "ipv6_network_connected", "ipv6_network_connect_denied",
                            "ipv6_network_error", "ipv6_network_wait_expired",
                            "ipv6_network_timed_out",
                            "ipv6_canary_received",
                        )
                    },
                )
                self._workflow_json_notice(
                    "Windows Reviewer write canary fingerprints",
                    summary["write_canary_fingerprints"],
                )
                self.assertTrue(candidate.executed, candidate)
                self.assertEqual(candidate.exit_code, 0, candidate)
                self.assertTrue(candidate.cleanup_ok, candidate)
                self.assertTrue(parent_standard_user_verified, summary)
                self.assertTrue(dacl_control_verified, summary)
                self.assertTrue(all(summary[key] is True for key in (
                    "appcontainer", "package_sid", "approved_read", "outside_snapshot_denied",
                    "workspace_denied", "home_denied", "ledger_denied", "write_denied",
                    "delete_denied", "rename_denied", "create_denied", "dacl_write_dac_denied",
                    "child_started", "child_exited", "snapshot_acl_restored", "runtime_acl_restored",
                    "write_canary_unchanged", "create_cleanup_ok",
                    "ipv4_host_control", "ipv4_network_attempted",
                    "ipv4_network_connect_denied", "ipv6_host_control",
                    "ipv6_network_attempted", "ipv6_network_connect_denied",
                )), summary)
                self.assertIs(summary["ipv4_network_connected"], False, summary)
                self.assertEqual(summary["ipv4_network_error"], 10013, summary)
                self.assertIs(summary["ipv4_canary_received"], False, summary)
                self.assertIs(summary["ipv6_network_connected"], False, summary)
                self.assertEqual(summary["ipv6_network_error"], 10013, summary)
                self.assertIs(summary["ipv6_canary_received"], False, summary)
                self.assertEqual(summary["capabilities"], 0, summary)
                self.assertIs(summary["elevated"], False, summary)
                self.assertIs(summary["admin_group_enabled"], False, summary)
                self.assertEqual(hashlib.sha256(approved_file.read_bytes()).hexdigest(), original_snapshot_hash)
                self.assertEqual(outside_file.read_text(encoding="ascii"), "outside snapshot")
                self.assertEqual(workspace_file.read_text(encoding="ascii"), "original workspace")
                self.assertEqual(ledger_file.read_text(encoding="ascii"), '{"private":"synthetic canary"}')
                self.assertEqual(home_file.read_text(encoding="ascii"), "user home canary")
            finally:
                for listener, listener_thread in zip(network_servers, network_threads):
                    if listener_thread.is_alive():
                        listener.shutdown()
                        listener_thread.join(timeout=3)
                    listener.server_close()
                home_temp.cleanup()


if __name__ == "__main__":
    unittest.main()
