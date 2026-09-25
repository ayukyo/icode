"""Probe restricted-token child creation from a real standard Windows account.

This is a CI architecture gate, not a product sandbox or a fallback executor.
It starts only a fixed system command, and reports no username, password, SID,
or filesystem path.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import ntpath
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


_USERNAME_RE = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
_SID_RE = re.compile(r"S-\d-(?:\d+-){1,14}\d+\Z", re.IGNORECASE)
_CREATE_NO_WINDOW = 0x08000000
_CREATE_SUSPENDED = 0x00000004
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x00000102
_INFINITE = 0xFFFFFFFF
_TOKEN_DUPLICATE = 0x0002
_TOKEN_QUERY = 0x0008
_TOKEN_ASSIGN_PRIMARY = 0x0001
_TOKEN_ADJUST_DEFAULT = 0x0080
_TOKEN_ADJUST_PRIVILEGES = 0x0020
_DISABLE_MAX_PRIVILEGE = 0x0001
_LUA_TOKEN = 0x0004
_WRITE_RESTRICTED = 0x0008
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_RUNNER_SUCCESS_RESULT = (
    "runner_standard_user=PASS;child_restricted=PASS;child_non_admin=PASS;"
    "child_identity=PASS;"
    "job_assignment=PASS;exit=PASS"
)


def runner_probe_succeeded(result: str) -> bool:
    """Accept only the complete, versioned success record emitted by the probe."""
    return result == _RUNNER_SUCCESS_RESULT


def stage_runner_script(source_path: Path, scratch_path: Path) -> Path:
    """Copy this fixed probe into the directory explicitly granted to its runner."""
    source = Path(source_path).resolve(strict=True)
    scratch = Path(scratch_path).resolve(strict=True)
    if not source.is_file() or not scratch.is_dir():
        raise ValueError("runner script or scratch directory is unavailable")
    staged = scratch / "windows_standard_user_token_probe.py"
    if source == staged:
        raise ValueError("runner script must be staged into a separate directory")
    shutil.copyfile(source, staged)
    return staged


def _validate_windows_path(name: str, value: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError(f"{name} must be a non-empty Windows path")
    if not ntpath.isabs(value):
        raise ValueError(f"{name} must be absolute")
    drive, _ = ntpath.splitdrive(value)
    if len(drive) != 2 or drive[1] != ":":
        raise ValueError(f"{name} must use a local drive path")
    return ntpath.normpath(value)


def build_system_tool_environment(system_root: str) -> dict[str, str]:
    """Keep helper processes such as icacls free of ambient CI secrets."""
    windows_root = _validate_windows_path("system_root", system_root)
    return {
        "SystemRoot": windows_root,
        "WINDIR": windows_root,
        "PATH": ntpath.join(windows_root, "System32"),
    }


def build_runner_environment_block(
    *, python_executable: str, scratch: str, system_root: str,
) -> str:
    """Return an explicit environment block; ambient credentials are never copied."""
    python_path = _validate_windows_path("python_executable", python_executable)
    scratch_path = _validate_windows_path("scratch", scratch)
    windows_root = _validate_windows_path("system_root", system_root)
    python_dir = ntpath.dirname(python_path)
    system32 = ntpath.join(windows_root, "System32")
    if ";" in python_dir or ";" in system32:
        raise ValueError("PATH entries must not contain semicolons")

    entries: dict[str, str] = {
        "SystemRoot": windows_root,
        "WINDIR": windows_root,
        "PATH": f"{python_dir};{system32}",
        "TEMP": scratch_path,
        "TMP": scratch_path,
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "ICODE_R2_PROBE_MODE": "runner",
    }
    for path in (python_path, scratch_path, windows_root):
        drive = ntpath.splitdrive(path)[0].upper()
        entries[f"={drive}"] = scratch_path if drive.casefold() == ntpath.splitdrive(scratch_path)[0].casefold() else f"{drive}\\"

    serialized = sorted(entries.items(), key=lambda item: item[0].casefold())
    block = "\0".join(f"{name}={value}" for name, value in serialized) + "\0\0"
    if "\0\0\0" in block:
        raise ValueError("invalid environment block")
    return block


def _make_environment_buffer(block: str) -> ctypes.Array:
    if not isinstance(block, str) or not block.endswith("\0\0"):
        raise ValueError("environment block must end with two NUL characters")
    # create_unicode_buffer normally adds a third terminator when its input is
    # a string. Windows environment blocks must end at exactly the first pair.
    return ctypes.create_unicode_buffer(block, len(block))


def build_runner_command_line(
    python_executable: str, script_path: str, report_path: str,
) -> str:
    """Build the fixed two-argument runner invocation within LogonW's limit."""
    python_path = _validate_windows_path("python_executable", python_executable)
    script = _validate_windows_path("script_path", script_path)
    report = _validate_windows_path("report_path", report_path)
    command = subprocess.list2cmdline([python_path, script, "--runner", report])
    # CreateProcessWithLogonW documents a 1024-character command-line maximum.
    if len(command) >= 1024:
        raise ValueError("runner command line exceeds the logon API limit")
    return command


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _winerror(stage: str) -> RuntimeError:
    return RuntimeError(f"{stage}:winerror={ctypes.get_last_error()}")


def _runner_probe(report_path: Path) -> str:
    if sys.platform != "win32":
        return "unsupported_platform"

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.CheckTokenMembership.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
    ]
    advapi.CheckTokenMembership.restype = wintypes.BOOL
    advapi.CreateWellKnownSid.argtypes = [
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.CreateWellKnownSid.restype = wintypes.BOOL
    advapi.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi.GetLengthSid.restype = wintypes.DWORD
    advapi.CreateRestrictedToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_SID_AND_ATTRIBUTES),
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.CreateRestrictedToken.restype = wintypes.BOOL
    advapi.IsTokenRestricted.argtypes = [wintypes.HANDLE]
    advapi.IsTokenRestricted.restype = wintypes.BOOL
    advapi.CreateProcessAsUserW.argtypes = [
        wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD,
        ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(_STARTUPINFO),
        ctypes.POINTER(_PROCESS_INFORMATION),
    ]
    advapi.CreateProcessAsUserW.restype = wintypes.BOOL

    current_token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(
        kernel.GetCurrentProcess(),
        _TOKEN_DUPLICATE | _TOKEN_QUERY | _TOKEN_ASSIGN_PRIMARY
        | _TOKEN_ADJUST_DEFAULT | _TOKEN_ADJUST_PRIVILEGES,
        ctypes.byref(current_token),
    ):
        raise _winerror("open_current_token")

    restricted_token = wintypes.HANDLE()
    child_token = wintypes.HANDLE()
    job = wintypes.HANDLE()
    process = _PROCESS_INFORMATION()
    assigned_to_job = False
    try:
        required = wintypes.DWORD()
        advapi.GetTokenInformation(
            current_token, 1, None, 0, ctypes.byref(required),
        )
        if not required.value:
            raise _winerror("query_token_user_size")
        user_buffer = ctypes.create_string_buffer(required.value)
        if not advapi.GetTokenInformation(
            current_token, 1, user_buffer, required, ctypes.byref(required),
        ):
            raise _winerror("query_token_user")
        token_user = ctypes.cast(
            user_buffer, ctypes.POINTER(_TOKEN_USER),
        ).contents
        current_sid_size = advapi.GetLengthSid(token_user.User.Sid)
        if not current_sid_size:
            raise _winerror("get_runner_sid_length")
        current_sid = ctypes.string_at(token_user.User.Sid, current_sid_size)

        admin_sid_size = wintypes.DWORD()
        advapi.CreateWellKnownSid(
            26, None, None, ctypes.byref(admin_sid_size),
        )
        if not admin_sid_size.value:
            raise _winerror("query_admin_sid_size")
        admin_sid_buffer = ctypes.create_string_buffer(admin_sid_size.value)
        if not advapi.CreateWellKnownSid(
            26, None, admin_sid_buffer, ctypes.byref(admin_sid_size),
        ):
            raise _winerror("create_admin_sid")
        is_admin = wintypes.BOOL()
        if not advapi.CheckTokenMembership(
            None, admin_sid_buffer, ctypes.byref(is_admin),
        ):
            raise _winerror("check_runner_admin_membership")
        if is_admin.value:
            raise RuntimeError("runner_account_is_not_standard_user")

        restricting_sid = _SID_AND_ATTRIBUTES(token_user.User.Sid, 0)
        if not advapi.CreateRestrictedToken(
            current_token,
            _DISABLE_MAX_PRIVILEGE | _LUA_TOKEN | _WRITE_RESTRICTED,
            0, None, 0, None, 1, ctypes.byref(restricting_sid),
            ctypes.byref(restricted_token),
        ):
            raise _winerror("create_restricted_token")
        if not advapi.IsTokenRestricted(restricted_token):
            raise RuntimeError("restricted_token_check_failed")

        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise _winerror("create_job")
        limits = _EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(
            job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            raise _winerror("configure_job")

        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        system32 = ntpath.join(system_root, "System32")
        executable = ntpath.join(system32, "cmd.exe")
        command_line = ctypes.create_unicode_buffer(
            subprocess.list2cmdline([executable, "/d", "/c", "exit", "37"])
        )
        scratch = str(report_path.parent)
        environment = build_runner_environment_block(
            python_executable=sys.executable,
            scratch=scratch,
            system_root=system_root,
        )
        environment_buffer = _make_environment_buffer(environment)
        startup = _STARTUPINFO()
        startup.cb = ctypes.sizeof(startup)
        process = _PROCESS_INFORMATION()
        if not advapi.CreateProcessAsUserW(
            restricted_token, executable, command_line,
            None, None, False,
            _CREATE_SUSPENDED | _CREATE_NO_WINDOW | _CREATE_UNICODE_ENVIRONMENT,
            ctypes.cast(environment_buffer, ctypes.c_void_p),
            system32, ctypes.byref(startup), ctypes.byref(process),
        ):
            raise _winerror("create_process_as_user")

        if not kernel.AssignProcessToJobObject(job, process.hProcess):
            raise _winerror("assign_process_to_job")
        assigned_to_job = True
        if not advapi.OpenProcessToken(
            process.hProcess, _TOKEN_QUERY, ctypes.byref(child_token),
        ):
            raise _winerror("open_child_token")
        if not advapi.IsTokenRestricted(child_token):
            raise RuntimeError("child_token_not_restricted")
        child_is_admin = wintypes.BOOL()
        if not advapi.CheckTokenMembership(
            child_token, admin_sid_buffer, ctypes.byref(child_is_admin),
        ):
            raise _winerror("check_child_admin_membership")
        if child_is_admin.value:
            raise RuntimeError("child_token_is_admin")
        child_user_size = wintypes.DWORD()
        advapi.GetTokenInformation(
            child_token, 1, None, 0, ctypes.byref(child_user_size),
        )
        if not child_user_size.value:
            raise _winerror("query_child_token_user_size")
        child_user_buffer = ctypes.create_string_buffer(child_user_size.value)
        if not advapi.GetTokenInformation(
            child_token, 1, child_user_buffer, child_user_size,
            ctypes.byref(child_user_size),
        ):
            raise _winerror("query_child_token_user")
        child_user = ctypes.cast(
            child_user_buffer, ctypes.POINTER(_TOKEN_USER),
        ).contents
        child_sid_size = advapi.GetLengthSid(child_user.User.Sid)
        if not child_sid_size or ctypes.string_at(
            child_user.User.Sid, child_sid_size,
        ) != current_sid:
            raise RuntimeError("child_token_identity_mismatch")
        kernel.CloseHandle(child_token)
        child_token = wintypes.HANDLE()

        if kernel.ResumeThread(process.hThread) == 0xFFFFFFFF:
            raise _winerror("resume_restricted_child")
        wait = kernel.WaitForSingleObject(process.hProcess, 15_000)
        if wait == _WAIT_TIMEOUT:
            raise RuntimeError("restricted_child_timeout")
        if wait != _WAIT_OBJECT_0:
            raise _winerror("wait_restricted_child")
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(exit_code)):
            raise _winerror("get_restricted_child_exit")
        if exit_code.value != 37:
            raise RuntimeError(f"restricted_child_exit={exit_code.value}")
        return _RUNNER_SUCCESS_RESULT
    finally:
        if child_token:
            kernel.CloseHandle(child_token)
        if process.hProcess:
            if assigned_to_job and job:
                kernel.TerminateJobObject(job, 1)
                kernel.WaitForSingleObject(process.hProcess, 5000)
            elif not process.hThread or kernel.WaitForSingleObject(process.hProcess, 0) == _WAIT_TIMEOUT:
                kernel.TerminateProcess(process.hProcess, 1)
                kernel.WaitForSingleObject(process.hProcess, 5000)
        if process.hThread:
            kernel.CloseHandle(process.hThread)
        if process.hProcess:
            kernel.CloseHandle(process.hProcess)
        if job:
            kernel.CloseHandle(job)
        if restricted_token:
            kernel.CloseHandle(restricted_token)
        kernel.CloseHandle(current_token)


def _write_report(report_path: Path, result: str) -> None:
    report_path.write_text(result + "\n", encoding="ascii", newline="\n")


def _run_as_standard_user() -> int:
    if sys.platform != "win32":
        print("::error::restricted_token_probe_unsupported_platform")
        return 2
    # Remove credentials from this process environment before starting any
    # helper process. The runner itself receives a separately built allowlist.
    username = os.environ.pop("ICODE_R2_PROBE_USERNAME", "")
    password = os.environ.pop("ICODE_R2_PROBE_PASSWORD", "")
    sid = os.environ.pop("ICODE_R2_PROBE_SID", "")
    if not _USERNAME_RE.fullmatch(username) or not password or not _SID_RE.fullmatch(sid):
        print("::error::restricted_token_probe_credentials_invalid")
        return 2

    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    public_dir = Path(os.environ.get("PUBLIC", r"C:\Users\Public"))
    if not public_dir.is_dir():
        print("::error::restricted_token_probe_scratch_unavailable")
        return 2
    scratch: Path | None = None
    cleanup_failed = False
    result_code = 1
    try:
        scratch = Path(tempfile.mkdtemp(
            prefix="icode-r2-standard-user-", dir=public_dir,
        ))
        runner_script = stage_runner_script(Path(__file__), scratch)
        icacls = Path(system_root) / "System32" / "icacls.exe"
        acl = subprocess.run(
            [str(icacls), str(scratch), "/grant", f"*{sid}:(OI)(CI)M"],
            capture_output=True, text=True, timeout=15, check=False,
            env=build_system_tool_environment(system_root),
        )
        if acl.returncode != 0:
            raise RuntimeError("grant_probe_report_acl_failed")

        report = scratch / "result.txt"
        command = build_runner_command_line(
            sys.executable, str(runner_script), str(report),
        )
        environment = build_runner_environment_block(
            python_executable=sys.executable,
            scratch=str(scratch),
            system_root=system_root,
        )
        environment_buffer = _make_environment_buffer(environment)
        password_buffer = ctypes.create_unicode_buffer(password)
        password = ""
        startup = _STARTUPINFO()
        startup.cb = ctypes.sizeof(startup)
        process = _PROCESS_INFORMATION()
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi.CreateProcessWithLogonW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPWSTR,
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPWSTR,
            wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
            ctypes.POINTER(_STARTUPINFO), ctypes.POINTER(_PROCESS_INFORMATION),
        ]
        advapi.CreateProcessWithLogonW.restype = wintypes.BOOL
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        try:
            created = advapi.CreateProcessWithLogonW(
                username, ".", password_buffer, 0, sys.executable,
                ctypes.create_unicode_buffer(command),
                _CREATE_UNICODE_ENVIRONMENT | _CREATE_NO_WINDOW,
                ctypes.cast(environment_buffer, ctypes.c_void_p),
                str(scratch),
                ctypes.byref(startup), ctypes.byref(process),
            )
        finally:
            ctypes.memset(password_buffer, 0, ctypes.sizeof(password_buffer))
        if not created:
            raise _winerror("create_process_with_logon")
        try:
            wait = kernel.WaitForSingleObject(process.hProcess, 30_000)
            if wait == _WAIT_TIMEOUT:
                kernel.TerminateProcess(process.hProcess, 1)
                kernel.WaitForSingleObject(process.hProcess, 5000)
                raise RuntimeError("standard_user_runner_timeout")
            if wait != _WAIT_OBJECT_0:
                raise _winerror("wait_standard_user_runner")
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(exit_code)):
                raise _winerror("get_standard_user_runner_exit")
        finally:
            if kernel.WaitForSingleObject(process.hProcess, 0) == _WAIT_TIMEOUT:
                kernel.TerminateProcess(process.hProcess, 1)
                kernel.WaitForSingleObject(process.hProcess, 5000)
            kernel.CloseHandle(process.hThread)
            kernel.CloseHandle(process.hProcess)
        if not report.is_file():
            raise RuntimeError("standard_user_runner_report_missing")
        result = report.read_text(encoding="ascii").strip()
        if exit_code.value != 0 or not runner_probe_succeeded(result):
            detail = "unclassified"
            if result.startswith("failed="):
                candidate = result.removeprefix("failed=")
                if re.fullmatch(r"[a-z_]+:winerror=\d+|[a-z_]+", candidate):
                    detail = candidate
            raise RuntimeError(f"standard_user_restricted_child_failed:{detail}")
        print("standard_user_token_probe=PASS " + result)
        result_code = 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        safe = str(exc)
        if "winerror=" not in safe and safe not in {
            "grant_probe_report_acl_failed", "standard_user_runner_timeout",
            "standard_user_runner_report_missing",
        }:
            if not re.fullmatch(
                r"standard_user_restricted_child_failed:[a-z_]+", safe,
            ):
                safe = type(exc).__name__
        print(f"::error::standard_user_token_probe_failed {safe}")
    finally:
        if scratch is not None:
            try:
                shutil.rmtree(scratch)
            except OSError:
                cleanup_failed = True
                print("::error::standard_user_token_probe_scratch_cleanup_failed")
    if cleanup_failed:
        return 1
    return result_code


def _run_child_mode(report_path: str) -> int:
    if sys.platform != "win32":
        return 2
    try:
        report = Path(report_path)
        temp = os.environ.get("TEMP", "")
        if (
            os.environ.get("ICODE_R2_PROBE_MODE") != "runner"
            or not temp
            or ntpath.normcase(ntpath.dirname(ntpath.abspath(report_path)))
            != ntpath.normcase(ntpath.abspath(temp))
            or report.name != "result.txt"
        ):
            return 2
        result = _runner_probe(report)
        _write_report(report, result)
        return 0 if runner_probe_succeeded(result) else 1
    except (OSError, RuntimeError, ValueError) as exc:
        message = str(exc)
        if not re.fullmatch(r"[a-z_]+:winerror=\d+", message):
            message = type(exc).__name__
        try:
            _write_report(Path(report_path), "failed=" + message)
        except OSError:
            pass
        return 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "--runner":
        return _run_child_mode(args[1])
    if args:
        print("::error::restricted_token_probe_arguments_invalid")
        return 2
    return _run_as_standard_user()


if __name__ == "__main__":
    raise SystemExit(main())
