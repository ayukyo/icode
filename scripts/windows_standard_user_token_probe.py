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
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading

_SOURCE_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src"
if (_SOURCE_PACKAGE_ROOT / "icode").is_dir():
    # Running this file directly sets sys.path[0] to scripts/, not the
    # repository's src/ tree; Windows CI intentionally has no PYTHONPATH.
    sys.path.insert(0, str(_SOURCE_PACKAGE_ROOT))

import icode.windows_runner_pipe as _runner_pipe
from icode.windows_runner_pipe import (
    PIPE_CLIENT_ACCESS_MASK,
    create_runner_pipe_server,
    new_runner_pipe_name,
    open_runner_pipe_client,
    runner_process_logon_sid,
    runner_process_user_sid,
    validate_runner_pipe_name,
)


_USERNAME_RE = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
_SID_RE = re.compile(r"S-\d-(?:\d+-){1,14}\d+\Z", re.IGNORECASE)
_CREATE_NO_WINDOW = 0x08000000
_CREATE_SUSPENDED = 0x00000004
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x00000102
_INFINITE = 0xFFFFFFFF
_CHILD_REPORT_EXIT_GRACE_MS = 2_000
_ERROR_NO_SUCH_USER = 1317
_ERROR_LOGON_FAILURE = 1326
_ERROR_ACCESS_DENIED = 5
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PIPE_BUSY = 231
_ERROR_SEM_TIMEOUT = 121
_ERROR_NO_TOKEN = 1008
_SE_KERNEL_OBJECT = 6
_SE_DACL_PROTECTED = 0x1000
_ACCESS_ALLOWED_ACE_TYPE = 0x00
_ACCESS_DENIED_ACE_TYPE = 0x01
_SYSTEM_AUDIT_ACE_TYPE = 0x02
_SYSTEM_ALARM_ACE_TYPE = 0x03
_ACCESS_ALLOWED_OBJECT_ACE_TYPE = 0x05
_ACCESS_DENIED_OBJECT_ACE_TYPE = 0x06
_SYSTEM_AUDIT_OBJECT_ACE_TYPE = 0x07
_SYSTEM_ALARM_OBJECT_ACE_TYPE = 0x08
_ACCESS_ALLOWED_CALLBACK_ACE_TYPE = 0x09
_ACCESS_DENIED_CALLBACK_ACE_TYPE = 0x0A
_ACCESS_ALLOWED_CALLBACK_OBJECT_ACE_TYPE = 0x0B
_ACCESS_DENIED_CALLBACK_OBJECT_ACE_TYPE = 0x0C
_SYSTEM_RESOURCE_ATTRIBUTE_ACE_TYPE = 0x12
_SYSTEM_SCOPED_POLICY_ID_ACE_TYPE = 0x13
_SYSTEM_PROCESS_TRUST_LABEL_ACE_TYPE = 0x14
_SYSTEM_ACCESS_FILTER_ACE_TYPE = 0x15
_OWNER_SECURITY_INFORMATION = 0x00000001
_GROUP_SECURITY_INFORMATION = 0x00000002
_DACL_SECURITY_INFORMATION = 0x00000004
_LABEL_SECURITY_INFORMATION = 0x00000010  # Read mandatory label, not full SACL.
_PIPE_DIAGNOSTIC_SECURITY_INFORMATION = (
    _OWNER_SECURITY_INFORMATION
    | _GROUP_SECURITY_INFORMATION
    | _DACL_SECURITY_INFORMATION
    | _LABEL_SECURITY_INFORMATION
)
_SYSTEM_MANDATORY_LABEL_ACE_TYPE = 0x11
_SYSTEM_MANDATORY_LABEL_NO_WRITE_UP = 0x00000001
_ACE_TYPES_WITH_ACCESS_MASK = frozenset({
    _ACCESS_ALLOWED_ACE_TYPE,
    _ACCESS_DENIED_ACE_TYPE,
    _SYSTEM_AUDIT_ACE_TYPE,
    _SYSTEM_ALARM_ACE_TYPE,
    _ACCESS_ALLOWED_OBJECT_ACE_TYPE,
    _ACCESS_DENIED_OBJECT_ACE_TYPE,
    _SYSTEM_AUDIT_OBJECT_ACE_TYPE,
    _SYSTEM_ALARM_OBJECT_ACE_TYPE,
    _ACCESS_ALLOWED_CALLBACK_ACE_TYPE,
    _ACCESS_DENIED_CALLBACK_ACE_TYPE,
    _ACCESS_ALLOWED_CALLBACK_OBJECT_ACE_TYPE,
    _ACCESS_DENIED_CALLBACK_OBJECT_ACE_TYPE,
    _SYSTEM_MANDATORY_LABEL_ACE_TYPE,
    _SYSTEM_RESOURCE_ATTRIBUTE_ACE_TYPE,
    _SYSTEM_SCOPED_POLICY_ID_ACE_TYPE,
    _SYSTEM_PROCESS_TRUST_LABEL_ACE_TYPE,
    _SYSTEM_ACCESS_FILTER_ACE_TYPE,
})
_SE_GROUP_USE_FOR_DENY_ONLY = 0x00000010
_SE_GROUP_ENABLED = 0x00000004
_SE_GROUP_LOGON_ID = 0xC0000000
_SECURITY_IMPERSONATION_LEVEL = 2
_DIAGNOSTIC_MAX_ACE_COUNT = 256
_PIPE_DESCRIPTOR_MAX_ACE_REPORT = 8
_PIPE_SECURITY_DESCRIPTOR_SHAPE_RE = re.compile(
    r"sd_control=([0-9A-F]{4});sd_revision=[0-9]{1,3};"
    r"owner=(?:user|logon|other|absent|unavailable);"
    r"group=(?:user|logon|other|absent|unavailable);"
    r"dacl=(?:present|absent|null|unavailable);"
    r"acl_revision=(?:[0-9]{1,3}|x);ace_count=(?:[0-9]{1,3}|x);"
    r"aces=(?:-|(?:[0-9A-F]{2}\.[0-9A-F]{2}\.(?:[0-9A-F]{8}|--------))"
    r"(?:,(?:[0-9A-F]{2}\.[0-9A-F]{2}\.(?:[0-9A-F]{8}|--------)))*);"
    r"truncated=[01]\Z",
)
_DIAGNOSTIC_PRIVILEGE_BUFFER_BYTES = 4096
_MAXIMUM_ALLOWED_ACCESS = 0x02000000
_FILE_GENERIC_READ = 0x00120089
_FILE_GENERIC_WRITE = 0x00120116
_FILE_GENERIC_EXECUTE = 0x001200A0
_FILE_ALL_ACCESS = 0x001F01FF
_FILE_CREATE_PIPE_INSTANCE = 0x00000004
_PIPE_READ_DATA_ACCESS = 0x00000001
_PIPE_WRITE_DATA_ACCESS = 0x00000002
_PIPE_SYNCHRONIZE_ACCESS = 0x00100000
_GENERIC_READ = 0x80000000
_PIPE_ACCESS_MODE_MASK = 0x00000003
_PIPE_ACCESS_DUPLEX = 0x00000003
_PIPE_ACCESS_OUTBOUND = 0x00000002
_PIPE_DIRECTION_PROBE_TIMEOUT_MS = 2_000
_PIPE_DIRECTION_PROBE_STATES = frozenset({
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
    "server_close_failed",
    "client_close_failed",
    "security_descriptor_failed",
    "security_descriptor_free_failed",
    "invalid_logon_sid",
    "unsupported_platform",
    "probe_failed",
    "unavailable",
})
_RUNNER_PIPE_ACCESS_MATRIX = (
    ("z", 0),
    ("r", _PIPE_READ_DATA_ACCESS),
    ("w", _PIPE_WRITE_DATA_ACCESS),
    ("rw", _PIPE_READ_DATA_ACCESS | _PIPE_WRITE_DATA_ACCESS),
    ("s", _PIPE_SYNCHRONIZE_ACCESS),
    ("rs", _PIPE_READ_DATA_ACCESS | _PIPE_SYNCHRONIZE_ACCESS),
    ("ws", _PIPE_WRITE_DATA_ACCESS | _PIPE_SYNCHRONIZE_ACCESS),
    (
        "all",
        _PIPE_READ_DATA_ACCESS
        | _PIPE_WRITE_DATA_ACCESS
        | _PIPE_SYNCHRONIZE_ACCESS,
    ),
)
_RUNNER_PIPE_ACCESS_MATRIX_ALL_D5_RECEIPT = (
    "mask_z_d5+r_d5+w_d5+rw_d5+s_d5+rs_d5+ws_d5+all_d5"
)
_TOKEN_DUPLICATE = 0x0002
_TOKEN_QUERY = 0x0008
# TOKEN_INFORMATION_CLASS values: TokenIntegrityLevel=25, TokenMandatoryPolicy=27.
_TOKEN_INTEGRITY_LEVEL_CLASS = 25
_TOKEN_MANDATORY_POLICY_CLASS = 27
_TOKEN_MANDATORY_POLICY_NO_WRITE_UP = 0x00000001
_TOKEN_MANDATORY_POLICY_NEW_PROCESS_MIN = 0x00000002
_SECURITY_MANDATORY_LABEL_AUTHORITY = bytes((0, 0, 0, 0, 0, 16))
_SECURITY_MANDATORY_UNTRUSTED_RID = 0x0000
_SECURITY_MANDATORY_LOW_RID = 0x1000
_SECURITY_MANDATORY_MEDIUM_RID = 0x2000
_SECURITY_MANDATORY_MEDIUM_PLUS_RID = 0x2100
_SECURITY_MANDATORY_HIGH_RID = 0x3000
_SECURITY_MANDATORY_SYSTEM_RID = 0x4000
_SECURITY_MANDATORY_PROTECTED_PROCESS_RID = 0x5000
_TOKEN_ASSIGN_PRIMARY = 0x0001
_TOKEN_ADJUST_DEFAULT = 0x0080
_TOKEN_ADJUST_PRIVILEGES = 0x0020
_SECURITY_IMPERSONATION = 2
_DISABLE_MAX_PRIVILEGE = 0x0001
_LUA_TOKEN = 0x0004
_WRITE_RESTRICTED = 0x0008
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_RUNNER_SUCCESS_RESULT = (
    "runner_standard_user=PASS;server_pid_mismatch=PASS;"
    "child_restricted=PASS;child_non_admin=PASS;"
    "child_identity=PASS;job_assignment=PASS;exit=PASS"
)


def runner_probe_succeeded(result: str) -> bool:
    """Accept only the complete, versioned success record emitted by the probe."""
    return result == _RUNNER_SUCCESS_RESULT


def restricted_child_failure_detail(result: str) -> str:
    """Parse a bounded child failure record without accepting arbitrary output."""
    if not result.startswith("failed="):
        return "unclassified"
    candidate = result.removeprefix("failed=")
    stage, separator, detail = candidate.partition(";detail=")
    if not re.fullmatch(r"[a-z_]+:winerror=\d+|[a-z_]+", stage):
        return "unclassified"
    if not separator:
        return stage
    if not detail or len(detail) > 120 or not re.fullmatch(r"[A-Za-z0-9_+.-]+", detail):
        return "unclassified"
    return f"{stage}:{detail}"


def runner_report_failure_detail(result: str, exit_code: int) -> str | None:
    """Keep a child failure visible without trusting its report as free text."""
    if type(exit_code) is not int or not 0 <= exit_code <= 0xFFFFFFFF:
        return "unclassified"
    try:
        if len(result.encode("ascii")) > 512:
            return "unclassified"
    except (AttributeError, UnicodeError):
        return "unclassified"
    if exit_code == 0 and runner_probe_succeeded(result):
        return None
    detail = restricted_child_failure_detail(result)
    if detail != "unclassified":
        return detail
    # Older child builds wrote Python exception class names without normalizing
    # case; recognize only these fixed labels, never arbitrary report text.
    legacy_labels = {
        "TimeoutError": "timeout_error",
        "PermissionError": "permission_error",
        "RuntimeError": "runtime_error",
        "ValueError": "value_error",
        "OSError": "os_error",
    }
    if result.startswith("failed="):
        return legacy_labels.get(result.removeprefix("failed="), "unclassified")
    return "unclassified"


def _runner_child_failure_if_exited(
    *, kernel, process_handle: int, report_path: Path,
    server_pipe_handle: int | None = None,
    expected_logon_sid: str = "",
) -> str | None:
    """Read a child report after exit and diagnose pipe denial from its token."""
    if kernel.WaitForSingleObject(
        process_handle, _CHILD_REPORT_EXIT_GRACE_MS,
    ) != _WAIT_OBJECT_0:
        return None
    exit_code = wintypes.DWORD()
    if not kernel.GetExitCodeProcess(process_handle, ctypes.byref(exit_code)):
        return None
    try:
        with Path(report_path).open("rb") as report_file:
            raw_report = report_file.read(513)
    except OSError:
        return None
    if len(raw_report) > 512:
        return "unclassified"
    try:
        report = raw_report.decode("ascii")
    except UnicodeError:
        return "unclassified"
    detail = runner_report_failure_detail(report.strip(), int(exit_code.value))
    child_stage, separator, child_context = (detail or "").partition(":")
    if (
        child_stage == "client_open_access_denied"
        and server_pipe_handle
        and expected_logon_sid
    ):
        error_suffix = ""
        error_match = re.search(r"(?:^|\+)open_winerror_(\d+)\Z", child_context)
        if error_match:
            child_context = child_context[:error_match.start()].rstrip("+")
            error_suffix = f":winerror={error_match.group(1)}"
        access = _diagnose_runner_pipe_access(
            server_pipe_handle,
            expected_logon_sid,
            client_process_handle=process_handle,
        )
        context = f"+{child_context}" if separator and child_context else ""
        return f"{child_stage}{context}+{access}{error_suffix}"
    return detail


def logon_rejection_succeeded(
    *,
    expected_error_codes: tuple[int, ...],
    created: bool,
    error_code: int,
    process_started: bool,
    marker_exists: bool,
    process_residual: bool,
) -> bool:
    """Require bad credentials to fail before a child or target marker exists."""
    return (
        not created
        and error_code in expected_error_codes
        and not process_started
        and not marker_exists
        and not process_residual
    )


def unreadable_executable_rejection_succeeded(
    *,
    created: bool,
    error_code: int,
    process_started: bool,
    marker_exists: bool,
    process_residual: bool,
) -> bool:
    """Require executable access denial before process or command side effects."""
    return (
        not created
        and error_code == _ERROR_ACCESS_DENIED
        and not process_started
        and not marker_exists
        and not process_residual
    )


def unreadable_executable_cleanup_plan(
    *,
    create_succeeded: bool,
    process_handle: object,
    process_information_populated: bool,
) -> tuple[object | None, bool]:
    """Use only a process handle returned by a successful creation call.

    Win32 does not promise usable PROCESS_INFORMATION fields after a failed
    process-creation call. Treat any such output as ambiguous; never reopen a
    PID or close a handle whose ownership the API did not establish.
    """
    if not create_succeeded:
        return None, process_information_populated
    if process_handle:
        return process_handle, False
    return None, True


def stage_unreadable_executable_probe(
    scratch_path: Path,
    source_executable: Path,
    acl_tool: Path,
    user_sid: str,
    system_root: str,
) -> Path:
    """Copy a trusted executable into disposable scratch and deny one SID RX."""
    if not isinstance(user_sid, str) or _SID_RE.fullmatch(user_sid) is None:
        raise ValueError("unreadable_executable_probe_sid_invalid")
    scratch = Path(scratch_path)
    source = Path(source_executable)
    icacls = Path(acl_tool)
    if not scratch.is_dir() or not source.is_file() or not icacls.is_file():
        raise RuntimeError("unreadable_executable_probe_input_unavailable")

    target_directory = scratch / "no-rx"
    target = target_directory / "cmd.exe"
    try:
        target_directory.mkdir()
        shutil.copyfile(source, target)
    except OSError:
        raise RuntimeError("unreadable_executable_probe_staging_failed") from None
    if target.is_symlink() or not target.is_file():
        raise RuntimeError("unreadable_executable_probe_staging_failed")

    try:
        result = subprocess.run(
            [str(icacls), str(target), "/deny", f"*{user_sid}:(RX)"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=build_system_tool_environment(system_root),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("unreadable_executable_deny_acl_failed") from None
    if result.returncode != 0:
        raise RuntimeError("unreadable_executable_deny_acl_failed")
    return target


def attempt_unreadable_executable_launch(
    *,
    create_process: object,
    kernel: object,
    username: str,
    password_buffer: object,
    python_executable: str,
    executable_path: Path,
    marker_path: Path,
    scratch_path: Path,
    system_root: str,
    clear_last_error: object,
) -> tuple[bool, int, bool, bool, bool]:
    """Test a denied executable directly under the temporary account's token.

    This narrow native test runs before the separate runner-pipe handshake, so
    a pipe failure cannot conceal whether the same temporary user's ACL blocks
    execution of the disposable file copy.
    """
    if type(username) is not str or _USERNAME_RE.fullmatch(username) is None:
        raise ValueError("unreadable_executable_probe_username_invalid")
    if not callable(create_process) or not callable(clear_last_error):
        raise ValueError("unreadable_executable_probe_api_invalid")
    scratch = Path(scratch_path)
    executable = Path(executable_path)
    marker = Path(marker_path)
    if (
        not scratch.is_dir()
        or executable.is_symlink()
        or not executable.is_file()
        or not marker.parent.is_dir()
    ):
        raise RuntimeError("unreadable_executable_probe_input_unavailable")
    try:
        if marker.exists():
            raise RuntimeError("unreadable_executable_marker_preexists")
    except OSError:
        raise RuntimeError("unreadable_executable_marker_state_unavailable") from None

    command_line = subprocess.list2cmdline([
        str(executable), "/d", "/c", f"echo launched > {marker}",
    ])
    if len(command_line) >= 1024:
        raise RuntimeError("unreadable_executable_command_too_long")
    environment = build_runner_environment_block(
        python_executable=python_executable,
        scratch=str(scratch),
        system_root=system_root,
    )
    environment_buffer = _make_environment_buffer(environment)
    startup = _STARTUPINFO()
    startup.cb = ctypes.sizeof(startup)
    process = _PROCESS_INFORMATION()
    ctypes_last_error = getattr(ctypes, "get_last_error", None)
    if not callable(ctypes_last_error):
        raise RuntimeError("unreadable_executable_last_error_unavailable")

    try:
        clear_last_error()
        created = bool(create_process(
            username,
            ".",
            password_buffer,
            0,
            str(executable),
            ctypes.create_unicode_buffer(command_line),
            _CREATE_SUSPENDED | _CREATE_UNICODE_ENVIRONMENT | _CREATE_NO_WINDOW,
            ctypes.cast(environment_buffer, ctypes.c_void_p),
            str(scratch),
            ctypes.byref(startup),
            ctypes.byref(process),
        ))
        error_code = 0 if created else int(ctypes_last_error())
    except Exception:
        raise RuntimeError("unreadable_executable_process_creation_failed") from None

    process_information_populated = bool(
        process.hProcess or process.hThread
        or process.dwProcessId or process.dwThreadId
    )
    cleanup_handle, process_residual = unreadable_executable_cleanup_plan(
        create_succeeded=created,
        process_handle=process.hProcess,
        process_information_populated=process_information_populated,
    )
    try:
        if cleanup_handle:
            wait = kernel.WaitForSingleObject(cleanup_handle, 0)
            if wait != _WAIT_OBJECT_0:
                kernel.TerminateProcess(cleanup_handle, 1)
                wait = kernel.WaitForSingleObject(cleanup_handle, 5_000)
            process_residual = wait != _WAIT_OBJECT_0
    except Exception:
        process_residual = True
    finally:
        if created:
            for handle in (process.hThread, process.hProcess):
                if not handle:
                    continue
                try:
                    if not kernel.CloseHandle(handle):
                        process_residual = True
                except Exception:
                    # A thread-handle close failure must not skip the process
                    # handle, which is the only safe cleanup authority here.
                    process_residual = True

    try:
        marker_exists = marker.exists()
    except OSError:
        marker_exists = True
    process_started = created or process_information_populated
    return created, error_code, process_started, marker_exists, process_residual


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
    repository = Path(__file__).resolve().parents[1]
    package_source = repository / "src" / "icode"
    package_stage = scratch / "runner-lib" / "icode"
    package_stage.mkdir(parents=True, exist_ok=True)
    for name in (
        "__init__.py", "windows_runner_pipe.py", "windows_runner_protocol.py",
    ):
        source_module = package_source / name
        if not source_module.is_file():
            raise OSError("runner dependency is missing")
        shutil.copyfile(source_module, package_stage / name)
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
    sqos_diagnostic: bool = False,
) -> str:
    """Return an explicit environment block; ambient credentials are never copied."""
    if type(sqos_diagnostic) is not bool:
        raise ValueError("invalid_sqos_diagnostic_flag")
    python_path = _validate_windows_path("python_executable", python_executable)
    scratch_path = _validate_windows_path("scratch", scratch)
    windows_root = _validate_windows_path("system_root", system_root)
    python_dir = ntpath.dirname(python_path)
    system32 = ntpath.join(windows_root, "System32")
    runner_lib = ntpath.join(scratch_path, "runner-lib")
    if any(";" in entry for entry in (python_dir, system32, runner_lib)):
        raise ValueError("PATH entries must not contain semicolons")

    entries: dict[str, str] = {
        "SystemRoot": windows_root,
        "WINDIR": windows_root,
        "PATH": f"{python_dir};{system32}",
        "TEMP": scratch_path,
        "TMP": scratch_path,
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "PYTHONPATH": runner_lib,
        "ICODE_R2_PROBE_MODE": "runner",
    }
    if sqos_diagnostic:
        entries["ICODE_R2_SQOS_DIAGNOSTIC"] = "1"
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


def build_runner_pipe_command_line(
    python_executable: str,
    script_path: str,
    report_path: str,
    pipe_name: str,
    server_pid: int,
    request_id: str,
) -> str:
    """Build the fixed runner handshake invocation without credentials or policy."""
    python_path = _validate_windows_path("python_executable", python_executable)
    script = _validate_windows_path("script_path", script_path)
    report = _validate_windows_path("report_path", report_path)
    pipe = validate_runner_pipe_name(pipe_name)
    if type(server_pid) is not int or not 1 <= server_pid <= 0xFFFFFFFF:
        raise ValueError("invalid_runner_pipe_server_pid")
    if type(request_id) is not str or re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
        raise ValueError("invalid_runner_pipe_request_id")
    command = subprocess.list2cmdline([
        python_path, script, "--runner", report,
        "--pipe", pipe, "--server-pid", str(server_pid),
        "--request-id", request_id,
    ])
    if len(command) >= 1024:
        raise ValueError("runner command line exceeds the logon API limit")
    return command


def _safe_windows_error_code(exc: OSError) -> int:
    code = getattr(exc, "winerror", None)
    if type(code) is not int:
        code = exc.errno
    return code if type(code) is int and 0 <= code <= 0xFFFFFFFF else 0


def _safe_pipe_client_permission_stage(exc: PermissionError) -> str:
    if exc.args == ("runner_pipe_server_pid_mismatch",):
        return "server_pid_mismatch_rejected"
    stage = getattr(exc, "strerror", None)
    return {
        "runner_pipe_wait_access_denied": "client_wait_access_denied",
        "runner_pipe_open_access_denied": "client_open_access_denied",
        "runner_pipe_server_pid_query": "client_server_pid_query_access_denied",
    }.get(stage, "client_access_denied")


def _safe_standard_user_probe_error(exc: Exception) -> str:
    """Expose fixed probe labels while keeping arbitrary exception text private."""
    safe = str(exc)
    if safe in {
        "grant_probe_report_acl_failed",
        "standard_user_runner_timeout",
        "standard_user_runner_report_missing",
    }:
        return safe
    if re.fullmatch(r"[a-z_]+:winerror=\d+", safe):
        return safe
    if len(safe) <= 400 and re.fullmatch(
        r"standard_user_restricted_child_failed:[a-z0-9_+]+"
        r"(?::winerror=\d+)?(?::[A-Za-z0-9_+.-]{1,120})?",
        safe,
    ):
        return safe
    return type(exc).__name__


def _safe_runner_child_exception_detail(exc: Exception) -> str:
    """Return a bounded stage or exception-class label; never include raw text."""
    message = str(exc)
    if re.fullmatch(r"[a-z_]+:winerror=\d+", message):
        return message
    if re.fullmatch(r"[a-z_]+", message):
        return message
    if isinstance(exc, PermissionError):
        stage = _safe_pipe_client_permission_stage(exc)
        if stage != "client_access_denied":
            return stage
    label = re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).lower()
    return label if re.fullmatch(r"[a-z_]+", label) else "unclassified"


def _self_pipe_access_receipt_label(detail: object) -> str:
    """Reduce a self-pipe diagnostic to one fixed AccessCheck outcome tag."""
    labels = {
        "access_allow": "self_access_allow",
        "access_deny": "self_access_deny",
        "access_unavailable": "self_access_unavailable",
    }
    if isinstance(detail, str):
        for part in detail.split("+"):
            if part in labels:
                return labels[part]
    return "self_access_unavailable"


def _maximum_access_mask_receipt(
    call_succeeded: object,
    granted_access: object,
    access_status: object,
) -> str:
    """Render only a valid DWORD from a successful MAXIMUM_ALLOWED check."""
    if (
        type(call_succeeded) not in (bool, int)
        or call_succeeded == 0
        or type(access_status) not in (bool, int)
        or type(granted_access) is not int
        or not 0 <= granted_access <= 0xFFFFFFFF
        or (not access_status and granted_access != 0)
    ):
        return "unavailable"
    return f"{granted_access:08x}"


def _runner_pipe_accesscheck_observation(
    pipe_handle: int,
    expected_sid: str | None,
    expected_ace_mask: int = PIPE_CLIENT_ACCESS_MASK,
) -> tuple[str, str, str, str, str]:
    """Return fixed AccessCheck, token, DACL/ACE labels and maximum rights."""
    access_state = token_source = dacl_state = ace_state = "unavailable"
    max_access = "unavailable"
    try:
        diagnostic = _diagnose_runner_pipe_access(
            pipe_handle, expected_sid, expected_ace_mask=expected_ace_mask,
        )
    except Exception:
        return access_state, token_source, dacl_state, ace_state, max_access
    if isinstance(diagnostic, str):
        for part in diagnostic.split("+"):
            if part in {"access_allow", "access_deny", "access_unavailable"}:
                access_state = part.removeprefix("access_")
                break
    if isinstance(diagnostic, str):
        for part in diagnostic.split("+"):
            if part in {"token_process", "token_thread"}:
                token_source = part.removeprefix("token_")
                break
    if isinstance(diagnostic, str):
        for part in diagnostic.split("+"):
            if part in {
                "dacl_present", "dacl_absent", "dacl_null",
                "dacl_unavailable",
            }:
                dacl_state = part.removeprefix("dacl_")
                break
    if isinstance(diagnostic, str):
        for part in diagnostic.split("+"):
            if part in {
                "ace_match", "ace_missing", "ace_not_applicable",
                "ace_unavailable",
            }:
                ace_state = part.removeprefix("ace_")
                break
    if isinstance(diagnostic, str):
        for part in diagnostic.split("+"):
            if part.startswith("max_access_"):
                candidate = part.removeprefix("max_access_")
                if candidate == "unavailable" or re.fullmatch(
                    r"[0-9a-f]{8}", candidate,
                ):
                    max_access = candidate
                break
    return access_state, token_source, dacl_state, ace_state, max_access


def _runner_pipe_probe_detail_with_accesscheck(
    detail: str,
    observation: tuple[str, str, str, str, str],
) -> str:
    state, token_source, dacl_state, ace_state, max_access = observation
    if state not in {"allow", "deny", "unavailable"}:
        state = "unavailable"
    if token_source not in {"process", "thread", "unavailable"}:
        token_source = "unavailable"
    if dacl_state not in {"present", "absent", "null", "unavailable"}:
        dacl_state = "unavailable"
    if ace_state not in {"match", "missing", "not_applicable", "unavailable"}:
        ace_state = "unavailable"
    if (
        type(max_access) is not str
        or (
            max_access != "unavailable"
            and re.fullmatch(r"[0-9a-f]{8}", max_access) is None
        )
    ):
        max_access = "unavailable"
    result = (
        f"{detail}+access_{state}+token_{token_source}"
        f"+dacl_{dacl_state}+ace_{ace_state}"
    )
    if max_access != "unavailable":
        result += f"+max_access_{max_access}"
    return result


def _runner_pipe_probe_receipt_code(
    kind: str,
    opened: bool,
    detail: object,
) -> str:
    """Compactly encode open, AccessCheck, token, DACL, and ACE for A/Bs.

    The receipt order is default DACL, TokenUser DACL, TokenUser plus the
    create-instance bit. Each item is
    ``<kind><open><access><token><dacl><ace><maximum-access-mask>`` where
    open is ``o`` (opened), ``d`` (access denied), or ``f`` (other failure),
    access is ``a`` (allow), ``d`` (deny), or ``u`` (unavailable), and token
    is ``p`` (process), ``t`` (thread), or ``u`` (unavailable). DACL is
    ``p`` (present), ``a`` (absent), ``n`` (NULL), or ``u`` (unavailable);
    ACE is ``m`` (matching allow ACE), ``x`` (not found), ``n`` (not
    applicable), or ``u`` (unavailable). The final field is eight lowercase
    hex digits from AccessCheck(MAXIMUM_ALLOWED), or eight hyphens when
    unavailable. DACL and ACE ``n`` have distinct meanings by field position.
    These are independent observations; neither AccessCheck result replaces
    the actual open result.
    """
    if kind not in {"d", "u", "c"}:
        raise ValueError("invalid_temporary_pipe_probe_kind")
    if opened is True:
        open_state = "o"
    elif isinstance(detail, str) and (
        detail == "client_open_access_denied"
        or _runner_pipe_probe_open_denied(detail)
    ):
        open_state = "d"
    else:
        open_state = "f"
    access_state = "u"
    token_state = "u"
    dacl_state = ace_state = "u"
    max_access = "--------"
    if isinstance(detail, str):
        for part in detail.split("+"):
            if part in {"access_allow", "access_deny", "access_unavailable"}:
                access_state = {
                    "access_allow": "a",
                    "access_deny": "d",
                    "access_unavailable": "u",
                }[part]
            elif part in {"token_process", "token_thread"}:
                token_state = {"token_process": "p", "token_thread": "t"}[part]
            elif part in {
                "dacl_present", "dacl_absent", "dacl_null",
                "dacl_unavailable",
            }:
                dacl_state = {
                    "dacl_present": "p",
                    "dacl_absent": "a",
                    "dacl_null": "n",
                    "dacl_unavailable": "u",
                }[part]
            elif part in {
                "ace_match", "ace_missing", "ace_not_applicable",
                "ace_unavailable",
            }:
                ace_state = {
                    "ace_match": "m",
                    "ace_missing": "x",
                    "ace_not_applicable": "n",
                    "ace_unavailable": "u",
                }[part]
            elif part.startswith("max_access_"):
                candidate = part.removeprefix("max_access_")
                if re.fullmatch(r"[0-9a-f]{8}", candidate):
                    max_access = candidate
    return (
        f"{kind}{open_state}{access_state}{token_state}{dacl_state}{ace_state}"
        f"{max_access}"
    )


def _runner_pipe_probe_open_denied(detail: object) -> bool:
    return isinstance(detail, str) and (
        detail == "client_open_access_denied"
        or re.fullmatch(
            r"client_open_access_denied"
            r"(?:\+access_(?:allow|deny|unavailable))?"
            r"(?:\+token_(?:process|thread|child_process|unavailable))?"
            r"(?:\+dacl_(?:present|absent|null|unavailable))?"
            r"(?:\+ace_(?:match|missing|not_applicable|unavailable))?"
            r"(?:\+max_access_(?:unavailable|[0-9a-f]{8}))?",
            detail,
        )
    )


def runner_pipe_wrong_server_pid_probe() -> tuple[bool, str]:
    """Reject a false expected server PID and return only a safe stage code."""
    if sys.platform != "win32":
        return False, "unsupported_platform"
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetCurrentProcessId.argtypes = []
        kernel.GetCurrentProcessId.restype = wintypes.DWORD
        process_handle = kernel.GetCurrentProcess()
        current_pid = int(kernel.GetCurrentProcessId())
        wrong_pid = current_pid + 1 if current_pid < 0xFFFFFFFF else 1
        # Match the pipe factory contract and the production runner ACL: scope
        # the test pipe to this logon session, not the account across sessions.
        logon_sid = runner_process_logon_sid(process_handle)
        failures: list[str] = []
        with create_runner_pipe_server(logon_sid) as pipe:
            access_diagnostic = _diagnose_runner_pipe_access(
                getattr(pipe, "_handle", 0), logon_sid,
            )

            def accept_once() -> None:
                try:
                    pipe._connect(5_000)
                except TimeoutError:
                    failures.append("timeout")
                except OSError as exc:
                    failures.append(f"winerror_{_safe_windows_error_code(exc)}")
                except RuntimeError:
                    failures.append("invalid_state")

            worker = threading.Thread(target=accept_once, daemon=True)
            worker.start()
            # The server accepts ERROR_PIPE_CONNECTED when the client wins the
            # scheduling race, so a startup sleep is neither needed nor reliable.
            client_result = "client_not_started"
            try:
                client = open_runner_pipe_client(
                    pipe.name, wrong_pid, timeout_ms=2_000,
                )
            except PermissionError as exc:
                client_result = _safe_pipe_client_permission_stage(exc)
            except TimeoutError:
                client_result = "client_timeout"
            except OSError as exc:
                client_result = f"client_winerror_{_safe_windows_error_code(exc)}"
            else:
                client.close()
                client_result = "wrong_server_pid_accepted"
            worker.join(5)
            if worker.is_alive():
                pipe.close()
                worker.join(5)
            if worker.is_alive():
                return False, "server_thread_timeout"
            if failures:
                if client_result == "client_open_access_denied":
                    return False, f"{client_result}+{access_diagnostic}"
                return False, f"{client_result}+server_accept_{failures[0]}"
            if not pipe._connected:
                return False, f"{client_result}+server_not_connected"
            if client_result != "server_pid_mismatch_rejected":
                if client_result == "client_open_access_denied":
                    return False, f"{client_result}+{access_diagnostic}"
                return False, client_result
            return True, "server_pid_mismatch_rejected"
    except PermissionError:
        return False, "setup_access_denied"
    except TimeoutError:
        return False, "setup_timeout"
    except OSError as exc:
        return False, f"setup_winerror_{_safe_windows_error_code(exc)}"
    except (RuntimeError, ValueError):
        return False, "setup_invalid_state"


def runner_pipe_access_mask_matrix_probe() -> str:
    """Compare every subset of the runner client rights on disposable pipes.

    Each attempt keeps the logon-SID DACL and client-open flags unchanged and
    varies only ``dwDesiredAccess``. A successful open is immediately closed;
    this diagnostic does not connect the server endpoint or exchange data.
    """
    if sys.platform != "win32":
        return "unsupported_platform"
    try:
        api = _runner_pipe._load_win32_api()
        api.kernel.GetCurrentProcess.argtypes = []
        api.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process_handle = api.kernel.GetCurrentProcess()
        logon_sid = runner_process_logon_sid(process_handle)
    except Exception:
        return "matrix_setup_failed"

    outcomes: list[str] = []
    client_flags = (
        _runner_pipe.FILE_FLAG_OVERLAPPED
        | _runner_pipe._SECURITY_SQOS_PRESENT
        | _runner_pipe._SECURITY_IMPERSONATION
    )
    for case, requested_access in _RUNNER_PIPE_ACCESS_MATRIX:
        outcome = f"{case}_s"
        try:
            with create_runner_pipe_server(logon_sid) as pipe:
                if not api.kernel.WaitNamedPipeW(pipe.name, 2_000):
                    error = int(ctypes.get_last_error()) & 0xFFFFFFFF
                    outcome = f"{case}_w{error:08x}"
                else:
                    client_handle = api.kernel.CreateFileW(
                        pipe.name,
                        requested_access,
                        0,
                        None,
                        _runner_pipe._OPEN_EXISTING,
                        client_flags,
                        None,
                    )
                    if _runner_pipe._handle_is_invalid(client_handle):
                        error = int(ctypes.get_last_error()) & 0xFFFFFFFF
                        outcome = (
                            f"{case}_d5" if error == _ERROR_ACCESS_DENIED
                            else f"{case}_e{error:08x}"
                        )
                    else:
                        outcome = f"{case}_ok"
                        try:
                            if not api.kernel.CloseHandle(client_handle):
                                error = int(ctypes.get_last_error()) & 0xFFFFFFFF
                                outcome = f"{case}_c{error:08x}"
                        except OSError as exc:
                            error = _safe_windows_error_code(exc)
                            outcome = f"{case}_c{error:08x}"
                        except Exception:
                            outcome = f"{case}_c"
        except OSError as exc:
            error = _safe_windows_error_code(exc)
            outcome = f"{case}_s{error:08x}"
        except Exception:
            outcome = f"{case}_s"
        outcomes.append(outcome)

    receipt = "mask_" + "+".join(outcomes)
    return receipt if len(receipt) <= 110 else "matrix_unavailable"


def runner_pipe_open_without_synchronize_probe() -> tuple[bool, str]:
    """Test a narrower client mask against the unchanged per-logon pipe DACL.

    This is a diagnostic A/B only. It keeps the production pipe flags and the
    server ACL unchanged, and removes only SYNCHRONIZE from the client request.
    It does not change the production transport or its acceptance result.
    """
    if sys.platform != "win32":
        return False, "unsupported_platform"
    try:
        api = _runner_pipe._load_win32_api()
        api.kernel.GetCurrentProcess.argtypes = []
        api.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process_handle = api.kernel.GetCurrentProcess()
        logon_sid = runner_process_logon_sid(process_handle)
        with create_runner_pipe_server(logon_sid) as pipe:
            if not api.kernel.WaitNamedPipeW(pipe.name, 2_000):
                error = ctypes.get_last_error()
                if error == _ERROR_ACCESS_DENIED:
                    return False, "client_wait_access_denied"
                return False, "client_wait_failed"

            requested_access = PIPE_CLIENT_ACCESS_MASK & ~_PIPE_SYNCHRONIZE_ACCESS
            client = api.kernel.CreateFileW(
                pipe.name,
                requested_access,
                0,
                None,
                _runner_pipe._OPEN_EXISTING,
                _runner_pipe.FILE_FLAG_OVERLAPPED
                | _runner_pipe._SECURITY_SQOS_PRESENT
                | _runner_pipe._SECURITY_IMPERSONATION,
                None,
            )
            if _runner_pipe._handle_is_invalid(client):
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                    return False, "client_open_access_denied"
                return False, "client_open_failed"

            try:
                server_pid = wintypes.DWORD(0)
                if not api.kernel.GetNamedPipeServerProcessId(
                    client, ctypes.byref(server_pid),
                ) or server_pid.value == 0:
                    return False, "server_pid_unavailable"
                pipe._connect(2_000)
                if not pipe._connected:
                    return False, "server_connect_failed"
                return True, "client_opened_without_synchronize"
            except TimeoutError:
                return False, "server_connect_timeout"
            except OSError:
                return False, "server_connect_failed"
            finally:
                api.kernel.CloseHandle(client)
    except PermissionError:
        return False, "setup_access_denied"
    except TimeoutError:
        return False, "setup_timeout"
    except OSError:
        return False, "setup_failed"
    except (RuntimeError, ValueError):
        return False, "setup_invalid_state"


def runner_pipe_open_without_overlapped_probe() -> tuple[bool, str]:
    """Compare a synchronous client open against the unchanged per-logon pipe.

    This is a diagnostic A/B only. It keeps the production client access mask,
    server ACL, and SQOS unchanged, removing only FILE_FLAG_OVERLAPPED.
    """
    if sys.platform != "win32":
        return False, "unsupported_platform"
    try:
        api = _runner_pipe._load_win32_api()
        api.kernel.GetCurrentProcess.argtypes = []
        api.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process_handle = api.kernel.GetCurrentProcess()
        logon_sid = runner_process_logon_sid(process_handle)
        with create_runner_pipe_server(logon_sid) as pipe:
            if not api.kernel.WaitNamedPipeW(pipe.name, 2_000):
                error = ctypes.get_last_error()
                if error == _ERROR_ACCESS_DENIED:
                    return False, "client_wait_access_denied"
                return False, "client_wait_failed"

            client = api.kernel.CreateFileW(
                pipe.name,
                PIPE_CLIENT_ACCESS_MASK,
                0,
                None,
                _runner_pipe._OPEN_EXISTING,
                _runner_pipe._SECURITY_SQOS_PRESENT
                | _runner_pipe._SECURITY_IMPERSONATION,
                None,
            )
            if _runner_pipe._handle_is_invalid(client):
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                    return False, "client_open_access_denied"
                return False, "client_open_failed"

            try:
                server_pid = wintypes.DWORD(0)
                if not api.kernel.GetNamedPipeServerProcessId(
                    client, ctypes.byref(server_pid),
                ) or server_pid.value == 0:
                    return False, "server_pid_unavailable"
                pipe._connect(2_000)
                if not pipe._connected:
                    return False, "server_connect_failed"
                return True, "client_opened_without_overlapped"
            except TimeoutError:
                return False, "server_connect_timeout"
            except OSError:
                return False, "server_connect_failed"
            finally:
                api.kernel.CloseHandle(client)
    except PermissionError:
        return False, "setup_access_denied"
    except TimeoutError:
        return False, "setup_timeout"
    except OSError:
        return False, "setup_failed"
    except (RuntimeError, ValueError):
        return False, "setup_invalid_state"


def runner_pipe_open_without_sqos_probe(
    pipe_name: str,
    expected_server_pid: int,
) -> str:
    """Retry one denied parent-pipe open with only explicit SQOS bits removed.

    The probe uses the existing parent pipe name and expected server PID, the
    current child token, the production access/share/disposition values, and
    FILE_FLAG_OVERLAPPED. It closes any returned handle without sending data.
    """
    if sys.platform != "win32":
        return "unsupported_platform"
    try:
        pipe_name = validate_runner_pipe_name(pipe_name)
    except ValueError:
        return "invalid_pipe_name"
    if (
        type(expected_server_pid) is not int
        or not 1 <= expected_server_pid <= 0xFFFFFFFF
    ):
        return "invalid_server_pid"

    try:
        api = _runner_pipe._load_win32_api()
        if not api.kernel.WaitNamedPipeW(pipe_name, 1_000):
            error = int(ctypes.get_last_error()) & 0xFFFFFFFF
            if error == _ERROR_ACCESS_DENIED:
                return "wait_access_denied"
            if error == _ERROR_SEM_TIMEOUT:
                return "wait_timeout"
            if error == _ERROR_PIPE_BUSY:
                return "pipe_busy"
            if error == _ERROR_FILE_NOT_FOUND:
                return "pipe_not_found"
            return f"wait_winerror_{error}"

        set_last_error = getattr(ctypes, "set_last_error", None)
        if callable(set_last_error):
            set_last_error(0)
        handle = api.kernel.CreateFileW(
            pipe_name,
            PIPE_CLIENT_ACCESS_MASK,
            0,
            None,
            _runner_pipe._OPEN_EXISTING,
            _runner_pipe.FILE_FLAG_OVERLAPPED,
            None,
        )
        if _runner_pipe._handle_is_invalid(handle):
            error = int(ctypes.get_last_error()) & 0xFFFFFFFF
            if error == _ERROR_ACCESS_DENIED:
                return "access_denied"
            if error == _ERROR_PIPE_BUSY:
                return "pipe_busy"
            return f"open_winerror_{error}"

        result = "server_pid_unavailable"
        try:
            server_pid = wintypes.DWORD(0)
            if api.kernel.GetNamedPipeServerProcessId(
                handle, ctypes.byref(server_pid),
            ) and server_pid.value != 0:
                result = (
                    "opened" if server_pid.value == expected_server_pid
                    else "server_pid_mismatch"
                )
        except Exception:
            result = "server_pid_unavailable"

        try:
            if not api.kernel.CloseHandle(handle):
                return "handle_close_failed"
        except Exception:
            return "handle_close_failed"
        return result
    except (OSError, RuntimeError, ValueError):
        return "probe_failed"


def runner_pipe_open_with_default_dacl_probe() -> tuple[bool, str]:
    """Compare self-open with the token's default DACL on a disposable pipe.

    Only the pipe security descriptor differs from the existing self-pipe
    diagnostic. The random local pipe carries no data; it keeps the same
    first-instance, remote-client rejection, client access mask, SQOS, and
    overlapped flags as the runner transport. This is diagnostic-only and must
    never be used by the production pipe factory.
    """
    if sys.platform != "win32":
        return False, "unsupported_platform"
    try:
        api = _runner_pipe._load_win32_api()
        api.kernel.GetCurrentProcessId.argtypes = []
        api.kernel.GetCurrentProcessId.restype = wintypes.DWORD
        current_pid = int(api.kernel.GetCurrentProcessId())
        if current_pid <= 0:
            return False, "server_pid_unavailable"

        pipe_name = new_runner_pipe_name()
        server_handle = api.kernel.CreateNamedPipeW(
            pipe_name,
            _runner_pipe.RUNNER_PIPE_OPEN_MODE,
            _runner_pipe.RUNNER_PIPE_MODE,
            _runner_pipe.RUNNER_PIPE_MAX_INSTANCES,
            _runner_pipe.RUNNER_PIPE_BUFFER_BYTES,
            _runner_pipe.RUNNER_PIPE_BUFFER_BYTES,
            0,
            None,
        )
        if _runner_pipe._handle_is_invalid(server_handle):
            raise _runner_pipe._winerror("create_default_dacl_probe_pipe")

        with _runner_pipe.RunnerPipeServer(
            name=pipe_name, handle=server_handle, api=api,
        ) as pipe:
            if not api.kernel.WaitNamedPipeW(pipe.name, 2_000):
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                    return False, "client_wait_access_denied"
                return False, "client_wait_failed"

            # Compare the actual default descriptor with the same effective
            # token/mask immediately before the real disposable-pipe open.
            accesscheck_state = _runner_pipe_accesscheck_observation(
                pipe._handle, None,
            )
            client = api.kernel.CreateFileW(
                pipe.name,
                PIPE_CLIENT_ACCESS_MASK,
                0,
                None,
                _runner_pipe._OPEN_EXISTING,
                _runner_pipe.FILE_FLAG_OVERLAPPED
                | _runner_pipe._SECURITY_SQOS_PRESENT
                | _runner_pipe._SECURITY_IMPERSONATION,
                None,
            )
            if _runner_pipe._handle_is_invalid(client):
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_open_access_denied", accesscheck_state,
                    )
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "client_open_failed", accesscheck_state,
                )

            try:
                server_pid = wintypes.DWORD(0)
                if not api.kernel.GetNamedPipeServerProcessId(
                    client, ctypes.byref(server_pid),
                ) or server_pid.value == 0:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_pid_unavailable", accesscheck_state,
                    )
                if server_pid.value != current_pid:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_pid_mismatch", accesscheck_state,
                    )
                pipe._connect(2_000)
                if not pipe._connected:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_connect_failed", accesscheck_state,
                    )
                client_pid = wintypes.DWORD(0)
                if not api.kernel.GetNamedPipeClientProcessId(
                    pipe._handle, ctypes.byref(client_pid),
                ) or client_pid.value == 0:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_pid_unavailable", accesscheck_state,
                    )
                if client_pid.value != current_pid:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_pid_mismatch", accesscheck_state,
                    )
                return True, _runner_pipe_probe_detail_with_accesscheck(
                    "client_opened_with_default_dacl", accesscheck_state,
                )
            except TimeoutError:
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "server_connect_timeout", accesscheck_state,
                )
            except OSError:
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "server_connect_failed", accesscheck_state,
                )
            finally:
                if not api.kernel.CloseHandle(client):
                    raise _runner_pipe._winerror(
                        "close_default_dacl_probe_client",
                    )
    except PermissionError:
        return False, "setup_access_denied"
    except TimeoutError:
        return False, "setup_timeout"
    except OSError:
        return False, "setup_failed"
    except (RuntimeError, ValueError):
        return False, "setup_invalid_state"


def _pipe_descriptor_dacl_protected_state(descriptor_shape: object) -> str:
    """Read only the fixed DACL-protection bit from a safe descriptor shape."""
    if type(descriptor_shape) is not str or len(descriptor_shape) > 384:
        return "unavailable"
    match = _PIPE_SECURITY_DESCRIPTOR_SHAPE_RE.fullmatch(descriptor_shape)
    if match is None:
        return "unavailable"
    control = int(match.group(1), 16)
    return "on" if control & _SE_DACL_PROTECTED else "off"


def _format_pipe_default_dacl_copy_receipt(
    default_open_state: object,
    explicit_open_state: object,
    descriptor_state: object,
    default_protected_state: object = "unavailable",
    explicit_protected_state: object = "unavailable",
) -> str:
    """Keep the disposable descriptor-copy observation fixed and bounded."""
    open_states = {
        "opened", "access_denied", "failed", "not_run", "unsupported_platform",
    }
    descriptor_states = {
        "match", "mismatch", "unavailable", "setup_failed", "cleanup_failed",
    }
    protected_states = {"on", "off", "unavailable"}
    if not isinstance(default_open_state, str) or default_open_state not in open_states:
        default_open_state = "unavailable"
    if not isinstance(explicit_open_state, str) or explicit_open_state not in open_states:
        explicit_open_state = "unavailable"
    if not isinstance(descriptor_state, str) or descriptor_state not in descriptor_states:
        descriptor_state = "unavailable"
    if not isinstance(default_protected_state, str) or default_protected_state not in protected_states:
        default_protected_state = "unavailable"
    if not isinstance(explicit_protected_state, str) or explicit_protected_state not in protected_states:
        explicit_protected_state = "unavailable"
    receipt = (
        f"pipe_sd_copy=default_{default_open_state}_"
        f"explicit_{explicit_open_state}_shape_{descriptor_state}_"
        f"dacl_protected=d_{default_protected_state},e_{explicit_protected_state}"
    )
    return receipt if len(receipt) <= 128 else "pipe_sd_copy=unavailable"


def _runner_pipe_descriptor_copy_open_state(
    pipe_name: str,
    server_pid: int,
) -> str:
    """Open one diagnostic pipe with production client flags and no payload."""
    try:
        client = open_runner_pipe_client(
            pipe_name, server_pid, timeout_ms=2_000,
        )
    except PermissionError as exc:
        if (
            exc.errno == _ERROR_ACCESS_DENIED
            and exc.strerror == "runner_pipe_open_access_denied"
        ):
            return "access_denied"
        return "failed"
    except (OSError, RuntimeError, TimeoutError, ValueError):
        return "failed"
    except Exception:
        return "failed"
    try:
        client.close()
    except Exception:
        return "failed"
    return "opened"


def runner_pipe_default_dacl_copy_probe() -> str:
    """Compare default DACL with an explicit copy on disposable local pipes.

    Both randomized, one-instance local pipes use the production open mode,
    mode, buffer sizes, timeout, exact client mask, and client flags. The first
    pipe uses its token default descriptor; the second receives only that
    descriptor's owner/group/DACL projection returned by GetSecurityInfo.
    Their read-back owner/group/DACL summaries must match before the second
    client-open observation is considered comparable. No payload is sent.
    """
    if sys.platform != "win32":
        return _format_pipe_default_dacl_copy_receipt(
            "unsupported_platform", "unsupported_platform", "unavailable",
        )

    api = None
    descriptor = ctypes.c_void_p()
    servers: list[_runner_pipe.RunnerPipeServer] = []
    default_state = "not_run"
    explicit_state = "not_run"
    descriptor_state = "unavailable"
    default_protected_state = "unavailable"
    explicit_protected_state = "unavailable"
    setup_failed = False
    cleanup_failed = False
    try:
        api = _runner_pipe._load_win32_api()
        api.kernel.GetCurrentProcess.argtypes = []
        api.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api.kernel.GetCurrentProcessId.argtypes = []
        api.kernel.GetCurrentProcessId.restype = wintypes.DWORD
        process_handle = api.kernel.GetCurrentProcess()
        server_pid = int(api.kernel.GetCurrentProcessId())
        if not process_handle or not 1 <= server_pid <= 0xFFFFFFFF:
            raise OSError("pipe_copy_probe_identity_unavailable")

        try:
            user_sid = runner_process_user_sid(process_handle)
            logon_sid = runner_process_logon_sid(process_handle)
        except Exception:
            user_sid = logon_sid = None

        def create_pipe(
            name: str,
            security_attributes: ctypes.POINTER(_runner_pipe._SECURITY_ATTRIBUTES)
            | None,
        ) -> _runner_pipe.RunnerPipeServer:
            handle = api.kernel.CreateNamedPipeW(
                name,
                _runner_pipe.RUNNER_PIPE_OPEN_MODE,
                _runner_pipe.RUNNER_PIPE_MODE,
                _runner_pipe.RUNNER_PIPE_MAX_INSTANCES,
                _runner_pipe.RUNNER_PIPE_BUFFER_BYTES,
                _runner_pipe.RUNNER_PIPE_BUFFER_BYTES,
                0,
                security_attributes,
            )
            if _runner_pipe._handle_is_invalid(handle):
                raise _runner_pipe._winerror("pipe_copy_probe_create")
            pipe = _runner_pipe.RunnerPipeServer(
                name=name, handle=handle, api=api,
            )
            servers.append(pipe)
            return pipe

        default_pipe = create_pipe(new_runner_pipe_name(), None)
        default_state = _runner_pipe_descriptor_copy_open_state(
            default_pipe.name, server_pid,
        )

        api.advapi.GetSecurityInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_int, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        api.advapi.GetSecurityInfo.restype = wintypes.DWORD
        status = api.advapi.GetSecurityInfo(
            default_pipe._handle,
            _SE_KERNEL_OBJECT,
            _OWNER_SECURITY_INFORMATION
            | _GROUP_SECURITY_INFORMATION
            | _DACL_SECURITY_INFORMATION,
            None, None, None, None, ctypes.byref(descriptor),
        )
        if status != 0 or not descriptor.value:
            raise OSError("pipe_copy_probe_descriptor_unavailable")

        attributes = _runner_pipe._SECURITY_ATTRIBUTES(
            ctypes.sizeof(_runner_pipe._SECURITY_ATTRIBUTES), descriptor, 0,
        )
        explicit_pipe = create_pipe(
            new_runner_pipe_name(), ctypes.byref(attributes),
        )
        default_shape = runner_pipe_security_descriptor_shape(
            default_pipe._handle, user_sid, logon_sid,
        )
        explicit_shape = runner_pipe_security_descriptor_shape(
            explicit_pipe._handle, user_sid, logon_sid,
        )
        default_protected_state = _pipe_descriptor_dacl_protected_state(
            default_shape,
        )
        explicit_protected_state = _pipe_descriptor_dacl_protected_state(
            explicit_shape,
        )
        if (
            default_shape == "sd=unavailable"
            or explicit_shape == "sd=unavailable"
        ):
            descriptor_state = "unavailable"
        elif default_shape != explicit_shape:
            descriptor_state = "mismatch"
        else:
            descriptor_state = "match"
            explicit_state = _runner_pipe_descriptor_copy_open_state(
                explicit_pipe.name, server_pid,
            )
    except Exception:
        setup_failed = True
    finally:
        for server in reversed(servers):
            try:
                server.close()
            except Exception:
                cleanup_failed = True
        if descriptor.value and api is not None:
            try:
                if api.kernel.LocalFree(descriptor):
                    cleanup_failed = True
            except Exception:
                cleanup_failed = True

    if cleanup_failed:
        descriptor_state = "cleanup_failed"
    elif setup_failed:
        descriptor_state = "setup_failed"
    return _format_pipe_default_dacl_copy_receipt(
        default_state, explicit_state, descriptor_state,
        default_protected_state, explicit_protected_state,
    )


def runner_pipe_open_with_user_sid_dacl_probe() -> tuple[bool, str]:
    """Compare a narrow explicit user-SID ACL on a disposable pipe.

    This diagnostic changes only the DACL principal from the runner's logon
    SID to its primary user SID. The production client mask and all pipe/open
    flags remain unchanged; the temporary pipe carries no data and is never
    used by the production factory.
    """
    if sys.platform != "win32":
        return False, "unsupported_platform"
    try:
        api = _runner_pipe._load_win32_api()
        api.kernel.GetCurrentProcess.argtypes = []
        api.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api.kernel.GetCurrentProcessId.argtypes = []
        api.kernel.GetCurrentProcessId.restype = wintypes.DWORD
        process_handle = api.kernel.GetCurrentProcess()
        current_pid = int(api.kernel.GetCurrentProcessId())
        if not process_handle or current_pid <= 0:
            return False, "server_pid_unavailable"

        user_sid = runner_process_user_sid(process_handle)
        with create_runner_pipe_server(user_sid) as pipe:
            if not api.kernel.WaitNamedPipeW(pipe.name, 2_000):
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                    return False, "client_wait_access_denied"
                return False, "client_wait_failed"

            accesscheck_state = _runner_pipe_accesscheck_observation(
                pipe._handle, user_sid,
            )
            client = api.kernel.CreateFileW(
                pipe.name,
                PIPE_CLIENT_ACCESS_MASK,
                0,
                None,
                _runner_pipe._OPEN_EXISTING,
                _runner_pipe.FILE_FLAG_OVERLAPPED
                | _runner_pipe._SECURITY_SQOS_PRESENT
                | _runner_pipe._SECURITY_IMPERSONATION,
                None,
            )
            if _runner_pipe._handle_is_invalid(client):
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_open_access_denied", accesscheck_state,
                    )
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "client_open_failed", accesscheck_state,
                )

            try:
                server_pid = wintypes.DWORD(0)
                if not api.kernel.GetNamedPipeServerProcessId(
                    client, ctypes.byref(server_pid),
                ) or server_pid.value == 0:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_pid_unavailable", accesscheck_state,
                    )
                if server_pid.value != current_pid:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_pid_mismatch", accesscheck_state,
                    )
                pipe._connect(2_000)
                if not pipe._connected:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_connect_failed", accesscheck_state,
                    )
                client_pid = wintypes.DWORD(0)
                if not api.kernel.GetNamedPipeClientProcessId(
                    pipe._handle, ctypes.byref(client_pid),
                ) or client_pid.value == 0:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_pid_unavailable", accesscheck_state,
                    )
                if client_pid.value != current_pid:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_pid_mismatch", accesscheck_state,
                    )
                return True, _runner_pipe_probe_detail_with_accesscheck(
                    "client_opened_with_user_sid_dacl", accesscheck_state,
                )
            except TimeoutError:
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "server_connect_timeout", accesscheck_state,
                )
            except OSError:
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "server_connect_failed", accesscheck_state,
                )
            finally:
                if not api.kernel.CloseHandle(client):
                    raise _runner_pipe._winerror(
                        "close_user_sid_dacl_probe_client",
                    )
    except PermissionError:
        return False, "setup_access_denied"
    except TimeoutError:
        return False, "setup_timeout"
    except OSError:
        return False, "setup_failed"
    except (RuntimeError, ValueError):
        return False, "setup_invalid_state"


def _create_user_sid_pipe_server_with_create_instance_access(
    user_sid: str,
    api: object,
) -> _runner_pipe.RunnerPipeServer:
    """Create a disposable test pipe with one extra named-pipe access bit.

    This deliberately does not change ``create_runner_pipe_server`` or the
    production runner ACL. The sole ACE grants the existing client mask plus
    FILE_CREATE_PIPE_INSTANCE to the temporary TokenUser SID.
    """
    sid = _runner_pipe._validate_sid(user_sid)
    pipe_name = new_runner_pipe_name()
    requested_mask = PIPE_CLIENT_ACCESS_MASK | _FILE_CREATE_PIPE_INSTANCE
    sddl = f"D:P(A;;0x{requested_mask:08x};;;{sid})"
    security_descriptor = ctypes.c_void_p()
    converted = bool(api.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(security_descriptor), None,
    ))
    if not converted:
        error = _runner_pipe._winerror(
            "create_instance_probe_security_descriptor",
        )
        if security_descriptor.value and api.kernel.LocalFree(security_descriptor):
            raise _runner_pipe._winerror(
                "free_create_instance_probe_security_descriptor",
            ) from error
        raise error
    if not security_descriptor.value:
        raise RuntimeError("create_instance_probe_security_descriptor_missing")

    attributes = _runner_pipe._SECURITY_ATTRIBUTES(
        ctypes.sizeof(_runner_pipe._SECURITY_ATTRIBUTES),
        security_descriptor,
        0,
    )
    handle = _runner_pipe._INVALID_HANDLE_VALUE
    try:
        handle = api.kernel.CreateNamedPipeW(
            pipe_name,
            _runner_pipe.RUNNER_PIPE_OPEN_MODE,
            _runner_pipe.RUNNER_PIPE_MODE,
            _runner_pipe.RUNNER_PIPE_MAX_INSTANCES,
            _runner_pipe.RUNNER_PIPE_BUFFER_BYTES,
            _runner_pipe.RUNNER_PIPE_BUFFER_BYTES,
            0,
            ctypes.byref(attributes),
        )
    finally:
        if (
            security_descriptor.value
            and api.kernel.LocalFree(security_descriptor)
        ):
            free_error = _runner_pipe._winerror(
                "free_create_instance_probe_security_descriptor",
            )
            if not _runner_pipe._handle_is_invalid(handle):
                if not api.kernel.CloseHandle(handle):
                    raise _runner_pipe._winerror(
                        "close_create_instance_probe_pipe_after_free_failure",
                    ) from free_error
            raise free_error

    if _runner_pipe._handle_is_invalid(handle):
        raise _runner_pipe._winerror("create_instance_probe_pipe")
    return _runner_pipe.RunnerPipeServer(
        name=pipe_name,
        handle=handle,
        api=api,
    )


def runner_pipe_open_with_user_sid_create_instance_access_probe() -> tuple[bool, str]:
    """Test one extra DACL bit on a random, local, zero-payload pipe only."""
    if sys.platform != "win32":
        return False, "unsupported_platform"
    try:
        api = _runner_pipe._load_win32_api()
        api.kernel.GetCurrentProcess.argtypes = []
        api.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api.kernel.GetCurrentProcessId.argtypes = []
        api.kernel.GetCurrentProcessId.restype = wintypes.DWORD
        process_handle = api.kernel.GetCurrentProcess()
        current_pid = int(api.kernel.GetCurrentProcessId())
        if not process_handle or current_pid <= 0:
            return False, "server_pid_unavailable"

        user_sid = runner_process_user_sid(process_handle)
        with _create_user_sid_pipe_server_with_create_instance_access(
            user_sid, api,
        ) as pipe:
            if not api.kernel.WaitNamedPipeW(pipe.name, 2_000):
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                    return False, "client_wait_access_denied"
                return False, "client_wait_failed"

            accesscheck_state = _runner_pipe_accesscheck_observation(
                pipe._handle, user_sid,
                PIPE_CLIENT_ACCESS_MASK | _FILE_CREATE_PIPE_INSTANCE,
            )
            client = api.kernel.CreateFileW(
                pipe.name,
                PIPE_CLIENT_ACCESS_MASK,
                0,
                None,
                _runner_pipe._OPEN_EXISTING,
                _runner_pipe.FILE_FLAG_OVERLAPPED
                | _runner_pipe._SECURITY_SQOS_PRESENT
                | _runner_pipe._SECURITY_IMPERSONATION,
                None,
            )
            if _runner_pipe._handle_is_invalid(client):
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_open_access_denied", accesscheck_state,
                    )
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "client_open_failed", accesscheck_state,
                )

            try:
                server_pid = wintypes.DWORD(0)
                if not api.kernel.GetNamedPipeServerProcessId(
                    client, ctypes.byref(server_pid),
                ) or server_pid.value == 0:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_pid_unavailable", accesscheck_state,
                    )
                if server_pid.value != current_pid:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_pid_mismatch", accesscheck_state,
                    )
                pipe._connect(2_000)
                if not pipe._connected:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "server_connect_failed", accesscheck_state,
                    )
                client_pid = wintypes.DWORD(0)
                if not api.kernel.GetNamedPipeClientProcessId(
                    pipe._handle, ctypes.byref(client_pid),
                ) or client_pid.value == 0:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_pid_unavailable", accesscheck_state,
                    )
                if client_pid.value != current_pid:
                    return False, _runner_pipe_probe_detail_with_accesscheck(
                        "client_pid_mismatch", accesscheck_state,
                    )
                return True, _runner_pipe_probe_detail_with_accesscheck(
                    "client_opened_with_user_sid_create_instance_access",
                    accesscheck_state,
                )
            except TimeoutError:
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "server_connect_timeout", accesscheck_state,
                )
            except OSError:
                return False, _runner_pipe_probe_detail_with_accesscheck(
                    "server_connect_failed", accesscheck_state,
                )
            finally:
                if not api.kernel.CloseHandle(client):
                    raise _runner_pipe._winerror(
                        "close_create_instance_probe_client",
                    )
    except PermissionError:
        return False, "setup_access_denied"
    except TimeoutError:
        return False, "setup_timeout"
    except OSError:
        return False, "setup_failed"
    except (RuntimeError, ValueError):
        return False, "setup_invalid_state"


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


class _SID_IDENTIFIER_AUTHORITY(ctypes.Structure):
    _fields_ = [("Value", ctypes.c_ubyte * 6)]


class _TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", _SID_AND_ATTRIBUTES)]


class _TOKEN_MANDATORY_POLICY(ctypes.Structure):
    _fields_ = [("Policy", wintypes.DWORD)]


class _ACL_HEADER(ctypes.Structure):
    _fields_ = [
        ("AclRevision", ctypes.c_ubyte),
        ("Sbz1", ctypes.c_ubyte),
        ("AclSize", ctypes.c_uint16),
        ("AceCount", ctypes.c_uint16),
        ("Sbz2", ctypes.c_uint16),
    ]


class _ACE_HEADER(ctypes.Structure):
    _fields_ = [
        ("AceType", ctypes.c_ubyte),
        ("AceFlags", ctypes.c_ubyte),
        ("AceSize", ctypes.c_uint16),
    ]


class _ACCESS_ALLOWED_ACE(ctypes.Structure):
    _fields_ = [
        ("Header", _ACE_HEADER),
        ("Mask", ctypes.c_uint32),
        ("SidStart", ctypes.c_uint32),
    ]


class _SYSTEM_MANDATORY_LABEL_ACE(ctypes.Structure):
    _fields_ = [
        ("Header", _ACE_HEADER),
        ("Mask", ctypes.c_uint32),
        ("SidStart", ctypes.c_uint32),
    ]


class _GENERIC_MAPPING(ctypes.Structure):
    _fields_ = [
        ("GenericRead", ctypes.c_uint32),
        ("GenericWrite", ctypes.c_uint32),
        ("GenericExecute", ctypes.c_uint32),
        ("GenericAll", ctypes.c_uint32),
    ]


def _format_runner_pipe_access_diagnostic(
    *, dacl: str, ace: str, token: str, logon_sid: str,
    restricted: str, access: str,
    client_integrity: str = "unavailable",
    pipe_integrity: str = "unavailable",
    pipe_no_write_up: str = "unavailable",
    client_no_write_up: str = "unavailable",
    max_access: str = "unavailable",
) -> str:
    """Serialize only fixed diagnostic states, never SID or ACL contents."""
    choices = {
        "dacl": {"present", "absent", "null", "unavailable"},
        "ace": {"match", "missing", "not_applicable", "unavailable"},
        "token": {"thread", "process", "child_process", "unavailable"},
        "logon_sid": {"enabled", "disabled", "deny_only", "absent", "unavailable"},
        "restricted": {"yes", "no", "unavailable"},
        "access": {"allow", "deny", "unavailable"},
        "client_integrity": {
            "untrusted", "low", "medium", "medium_plus", "high", "system",
            "protected_process", "other", "unavailable",
        },
        "pipe_integrity": {
            "untrusted", "low", "medium", "medium_plus", "high", "system",
            "protected_process", "other", "absent", "unavailable",
        },
        "pipe_no_write_up": {"yes", "no", "unavailable"},
        "client_no_write_up": {"yes", "no", "unavailable"},
    }
    values = {
        "dacl": dacl,
        "ace": ace,
        "token": token,
        "logon_sid": logon_sid,
        "restricted": restricted,
        "access": access,
        "client_integrity": client_integrity,
        "pipe_integrity": pipe_integrity,
        "pipe_no_write_up": pipe_no_write_up,
        "client_no_write_up": client_no_write_up,
    }
    if any(value not in choices[key] for key, value in values.items()):
        raise ValueError("invalid_pipe_access_diagnostic")
    if (
        type(max_access) is not str
        or (
            max_access != "unavailable"
            and re.fullmatch(r"[0-9a-f]{8}", max_access) is None
        )
    ):
        raise ValueError("invalid_pipe_access_diagnostic")
    labels = {
        "logon_sid": "logon",
        "client_integrity": "client_il",
        "pipe_integrity": "pipe_il",
        "pipe_no_write_up": "pipe_nwu",
        "client_no_write_up": "token_nwu",
    }
    summary = "+".join(
        f"{labels.get(key, key)}_{value}" for key, value in values.items()
    )
    summary += f"+max_access_{max_access}"
    if len(summary) > 240:
        raise ValueError("pipe_access_diagnostic_too_long")
    return summary


def _integrity_level_from_rid(rid: int) -> str:
    """Map a mandatory-label RID to a fixed, non-sensitive diagnostic label."""
    return {
        _SECURITY_MANDATORY_UNTRUSTED_RID: "untrusted",
        _SECURITY_MANDATORY_LOW_RID: "low",
        _SECURITY_MANDATORY_MEDIUM_RID: "medium",
        _SECURITY_MANDATORY_MEDIUM_PLUS_RID: "medium_plus",
        _SECURITY_MANDATORY_HIGH_RID: "high",
        _SECURITY_MANDATORY_SYSTEM_RID: "system",
        _SECURITY_MANDATORY_PROTECTED_PROCESS_RID: "protected_process",
    }.get(rid, "other")


def _integrity_level_from_sid(
    advapi: object, sid: int | ctypes.c_void_p | None,
) -> str:
    """Normalize a mandatory-label SID without exposing its contents."""
    try:
        advapi.IsValidSid.argtypes = [ctypes.c_void_p]
        advapi.IsValidSid.restype = wintypes.BOOL
        advapi.GetSidIdentifierAuthority.argtypes = [ctypes.c_void_p]
        advapi.GetSidIdentifierAuthority.restype = ctypes.POINTER(
            _SID_IDENTIFIER_AUTHORITY,
        )
        advapi.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        advapi.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        advapi.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        advapi.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
        if not sid or not advapi.IsValidSid(sid):
            return "unavailable"
        authority = advapi.GetSidIdentifierAuthority(sid)
        subauthority_count = advapi.GetSidSubAuthorityCount(sid)
        if not authority or not subauthority_count:
            return "unavailable"
        if bytes(authority.contents.Value) != _SECURITY_MANDATORY_LABEL_AUTHORITY:
            return "other"
        count = int(subauthority_count.contents.value)
        if count < 1:
            return "unavailable"
        rid_pointer = advapi.GetSidSubAuthority(sid, count - 1)
        if not rid_pointer:
            return "unavailable"
        return _integrity_level_from_rid(int(rid_pointer.contents.value))
    except Exception:
        return "unavailable"


def _token_integrity_level(
    api: object, token: int | ctypes.c_void_p | None,
) -> str:
    """Observe token IL using the documented mandatory-label token class."""
    if not token:
        return "unavailable"
    try:
        buffer = _runner_pipe._get_token_information(
            api, token, _TOKEN_INTEGRITY_LEVEL_CLASS,
        )
        label = ctypes.cast(
            buffer, ctypes.POINTER(_TOKEN_MANDATORY_LABEL),
        ).contents
        return _integrity_level_from_sid(api.advapi, label.Label.Sid)
    except Exception:
        # Missing diagnostic APIs or token data never changes the probe result.
        return "unavailable"


def _token_mandatory_no_write_up(
    api: object, token: int | ctypes.c_void_p | None,
) -> str:
    """Report only the token's mandatory NO_WRITE_UP policy bit."""
    return _token_mandatory_policy_state(api, token)[0]


def _token_mandatory_policy_state(
    api: object, token: int | ctypes.c_void_p | None,
) -> tuple[str, str]:
    """Report the defined NO_WRITE_UP and NEW_PROCESS_MIN policy bits."""
    if not token:
        return "unavailable", "unavailable"
    try:
        buffer = _runner_pipe._get_token_information(
            api, token, _TOKEN_MANDATORY_POLICY_CLASS,
        )
        policy = ctypes.cast(
            buffer, ctypes.POINTER(_TOKEN_MANDATORY_POLICY),
        ).contents
        return (
            "yes" if policy.Policy & _TOKEN_MANDATORY_POLICY_NO_WRITE_UP else "no",
            "yes" if policy.Policy & _TOKEN_MANDATORY_POLICY_NEW_PROCESS_MIN else "no",
        )
    except Exception:
        return "unavailable", "unavailable"


def _pipe_integrity_details(
    api: object, security_descriptor: int | ctypes.c_void_p | None,
) -> tuple[str, str]:
    """Read only the pipe's mandatory-label ACE and its NO_WRITE_UP bit."""
    unavailable = ("unavailable", "unavailable")
    if not security_descriptor:
        return unavailable
    try:
        advapi = api.advapi
        advapi.GetSecurityDescriptorSacl.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL),
        ]
        advapi.GetSecurityDescriptorSacl.restype = wintypes.BOOL
        advapi.GetAce.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.GetAce.restype = wintypes.BOOL
        sacl_present = wintypes.BOOL()
        sacl = ctypes.c_void_p()
        sacl_defaulted = wintypes.BOOL()
        if not advapi.GetSecurityDescriptorSacl(
            security_descriptor, ctypes.byref(sacl_present),
            ctypes.byref(sacl), ctypes.byref(sacl_defaulted),
        ):
            return unavailable
        if not sacl_present.value or not sacl:
            return "absent", "unavailable"
        header = ctypes.cast(sacl, ctypes.POINTER(_ACL_HEADER)).contents
        if header.AceCount > _DIAGNOSTIC_MAX_ACE_COUNT:
            return unavailable
        labels: list[tuple[str, str]] = []
        for index in range(int(header.AceCount)):
            ace_pointer = ctypes.c_void_p()
            if not advapi.GetAce(sacl, index, ctypes.byref(ace_pointer)) or not ace_pointer:
                return unavailable
            ace_header = ctypes.cast(
                ace_pointer, ctypes.POINTER(_ACE_HEADER),
            ).contents
            if ace_header.AceType != _SYSTEM_MANDATORY_LABEL_ACE_TYPE:
                continue
            ace = ctypes.cast(
                ace_pointer, ctypes.POINTER(_SYSTEM_MANDATORY_LABEL_ACE),
            ).contents
            sid_offset = _SYSTEM_MANDATORY_LABEL_ACE.SidStart.offset
            sid = ctypes.c_void_p(ace_pointer.value + sid_offset)
            labels.append((
                _integrity_level_from_sid(advapi, sid),
                "yes" if ace.Mask & _SYSTEM_MANDATORY_LABEL_NO_WRITE_UP else "no",
            ))
        if not labels:
            return "absent", "unavailable"
        if len(labels) != 1:
            return unavailable
        return labels[0]
    except Exception:
        return unavailable


def _open_pipe_diagnostic_token(
    api: object,
    *,
    client_process_handle: int | None = None,
    token_access: int | None = None,
) -> tuple[ctypes.c_void_p | None, str]:
    """Open only the token whose access to the pipe is under investigation."""
    token = ctypes.c_void_p()
    if token_access is None:
        token_access = _TOKEN_QUERY | _TOKEN_DUPLICATE
    if type(token_access) is not int or token_access <= 0:
        raise ValueError("invalid_diagnostic_token_access")
    advapi = api.advapi
    if client_process_handle is not None:
        if advapi.OpenProcessToken(
            client_process_handle, token_access, ctypes.byref(token),
        ) and token:
            return token, "child_process"
        return None, "unavailable"

    if advapi.OpenThreadToken(
        api.kernel.GetCurrentThread(), token_access, 1, ctypes.byref(token),
    ) and token:
        return token, "thread"
    if ctypes.get_last_error() != _ERROR_NO_TOKEN:
        return None, "unavailable"
    if advapi.OpenProcessToken(
        api.kernel.GetCurrentProcess(), token_access, ctypes.byref(token),
    ) and token:
        return token, "process"
    return None, "unavailable"


def _format_runner_effective_token_diagnostic(
    *, token: str, logon_sid: str, restricted: str,
    integrity: str, no_write_up: str, new_process_min: str,
) -> str:
    """Serialize a compact effective-token snapshot using fixed labels only."""
    choices = {
        "token": {"thread", "process", "unavailable"},
        "logon_sid": {"enabled", "disabled", "deny_only", "absent", "unavailable"},
        "restricted": {"yes", "no", "unavailable"},
        "integrity": {
            "untrusted", "low", "medium", "medium_plus", "high", "system",
            "protected_process", "other", "unavailable",
        },
        "no_write_up": {"yes", "no", "unavailable"},
        "new_process_min": {"yes", "no", "unavailable"},
    }
    values = {
        "token": token,
        "logon_sid": logon_sid,
        "restricted": restricted,
        "integrity": integrity,
        "no_write_up": no_write_up,
        "new_process_min": new_process_min,
    }
    if any(value not in choices[key] for key, value in values.items()):
        raise ValueError("invalid_effective_token_diagnostic")
    summary = "+".join((
        f"token_{token}",
        f"il_{integrity}",
        f"restricted_{restricted}",
        f"logon_{logon_sid}",
        f"nwu_{no_write_up}",
        f"npm_{new_process_min}",
    ))
    if len(summary) > 120:
        raise ValueError("effective_token_diagnostic_too_long")
    return summary


def _compact_runner_effective_token_diagnostic(summary: str | None) -> str:
    """Keep only identity, integrity, restriction, and logon tags for a DACL A/B."""
    if not isinstance(summary, str):
        return "token_unavailable"
    allowed = {
        "token_thread", "token_process", "token_unavailable",
        "il_untrusted", "il_low", "il_medium", "il_medium_plus", "il_high",
        "il_system", "il_protected_process", "il_other", "il_unavailable",
        "restricted_yes", "restricted_no", "restricted_unavailable",
        "logon_enabled", "logon_disabled", "logon_deny_only", "logon_absent",
        "logon_unavailable",
    }
    selected: list[str] = []
    categories: set[str] = set()
    for part in summary.split("+"):
        if part not in allowed:
            continue
        category = part.split("_", 1)[0]
        if category not in categories:
            categories.add(category)
            selected.append(part)
    compact = "+".join(selected) or "token_unavailable"
    return compact if len(compact) <= 72 else "token_unavailable"


def _minimal_runner_effective_token_diagnostic(summary: str | None) -> str:
    """Keep the observed token source and logon-SID state in tight receipts."""
    choices = {
        "token": {"thread", "process", "unavailable"},
        "logon": {"enabled", "disabled", "deny_only", "absent", "unavailable"},
    }
    values = {"token": "unavailable", "logon": "unavailable"}
    observed: set[str] = set()
    if isinstance(summary, str):
        for part in summary.split("+"):
            category, separator, value = part.partition("_")
            if (
                separator
                and category in choices
                and value in choices[category]
                and category not in observed
            ):
                values[category] = value
                observed.add(category)
    return "+".join((
        f"token_{values['token']}",
        f"logon_{values['logon']}",
    ))


def _runner_effective_token_diagnostic() -> str:
    """Observe the current thread token immediately before the pipe open."""
    token_source = logon_state = restricted_state = "unavailable"
    integrity_state = no_write_up_state = new_process_min_state = "unavailable"
    api = None
    effective_token = None
    try:
        if sys.platform != "win32":
            return _format_runner_effective_token_diagnostic(
                token=token_source, logon_sid=logon_state,
                restricted=restricted_state, integrity=integrity_state,
                no_write_up=no_write_up_state,
                new_process_min=new_process_min_state,
            )
        api = _runner_pipe._load_win32_api()
        effective_token, token_source = _open_pipe_diagnostic_token(
            api, token_access=_TOKEN_QUERY,
        )
        if effective_token:
            integrity_state = _token_integrity_level(api, effective_token)
            no_write_up_state, new_process_min_state = _token_mandatory_policy_state(
                api, effective_token,
            )
            api.advapi.IsTokenRestricted.argtypes = [ctypes.c_void_p]
            api.advapi.IsTokenRestricted.restype = wintypes.BOOL
            restricted_state = (
                "yes" if api.advapi.IsTokenRestricted(effective_token) else "no"
            )
            groups_buffer, groups = _runner_pipe._token_group_entries(
                _runner_pipe._get_token_information(
                    api, effective_token, _runner_pipe._TOKEN_GROUPS_CLASS,
                ),
            )
            _ = groups_buffer
            logon_state = "absent"
            for _sid_pointer, attributes in groups:
                if attributes & _SE_GROUP_LOGON_ID != _SE_GROUP_LOGON_ID:
                    continue
                if attributes & _SE_GROUP_USE_FOR_DENY_ONLY:
                    logon_state = "deny_only"
                elif attributes & _SE_GROUP_ENABLED:
                    logon_state = "enabled"
                else:
                    logon_state = "disabled"
                break
    except Exception:
        # This observation is deliberately non-authoritative and best-effort.
        pass
    finally:
        if api is not None and effective_token:
            try:
                api.kernel.CloseHandle(effective_token)
            except Exception:
                pass
    return _format_runner_effective_token_diagnostic(
        token=token_source, logon_sid=logon_state,
        restricted=restricted_state, integrity=integrity_state,
        no_write_up=no_write_up_state,
        new_process_min=new_process_min_state,
    )


def _runner_pipe_dacl_observation(
    api: object,
    security_descriptor: ctypes.c_void_p,
    expected_sid: ctypes.c_void_p | None,
    *,
    expected_ace_mask: int,
) -> tuple[str, str]:
    """Observe DACL shape and an allow ACE without inferring access.

    ``expected_sid=None`` means this probe has no single principal whose ACE
    should be matched. A non-None but null pointer means that principal was
    requested but could not be resolved, so the ACE check is unavailable.
    """
    ace_unresolved = "not_applicable" if expected_sid is None else "unavailable"
    if (
        type(expected_ace_mask) is not int
        or not 0 < expected_ace_mask <= 0xFFFFFFFF
    ):
        return "unavailable", ace_unresolved

    advapi = api.advapi
    try:
        advapi.GetSecurityDescriptorDacl.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL),
        ]
        advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
        present = wintypes.BOOL()
        dacl_pointer = ctypes.c_void_p()
        defaulted = wintypes.BOOL()
        if not advapi.GetSecurityDescriptorDacl(
            security_descriptor, ctypes.byref(present),
            ctypes.byref(dacl_pointer), ctypes.byref(defaulted),
        ):
            return "unavailable", ace_unresolved
        if not present.value:
            # The API says the other outputs are invalid when no DACL exists.
            return "absent", "not_applicable"
        if not dacl_pointer.value:
            # A present bit plus a null ACL pointer is a NULL DACL, not an
            # allocated empty DACL; preserve that distinction in the receipt.
            return "null", "not_applicable"
        if expected_sid is None:
            return "present", "not_applicable"
        if not expected_sid.value:
            return "present", "unavailable"

        header = ctypes.cast(
            dacl_pointer, ctypes.POINTER(_ACL_HEADER),
        ).contents
        if header.AceCount > _DIAGNOSTIC_MAX_ACE_COUNT:
            return "present", "unavailable"

        advapi.GetAce.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.GetAce.restype = wintypes.BOOL
        ace_state = "missing"
        for index in range(int(header.AceCount)):
            ace_pointer = ctypes.c_void_p()
            if not advapi.GetAce(
                dacl_pointer, index, ctypes.byref(ace_pointer),
            ) or not ace_pointer.value:
                return "present", "unavailable"
            ace_header = ctypes.cast(
                ace_pointer, ctypes.POINTER(_ACE_HEADER),
            ).contents
            if ace_header.AceType != _ACCESS_ALLOWED_ACE_TYPE:
                continue
            allowed = ctypes.cast(
                ace_pointer, ctypes.POINTER(_ACCESS_ALLOWED_ACE),
            ).contents
            sid_offset = _ACCESS_ALLOWED_ACE.SidStart.offset
            ace_sid = ctypes.c_void_p(ace_pointer.value + sid_offset)
            if (
                (allowed.Mask & expected_ace_mask) == expected_ace_mask
                and advapi.EqualSid(ace_sid, expected_sid)
            ):
                ace_state = "match"
                break
        return "present", ace_state
    except Exception:
        return "unavailable", ace_unresolved


def _diagnose_runner_pipe_access(
    pipe_handle: int,
    logon_sid: str | None,
    *,
    client_process_handle: int | None = None,
    expected_ace_mask: int = PIPE_CLIENT_ACCESS_MASK,
) -> str:
    """Read the pipe DACL and the actual client token without changing either."""
    dacl_state = token_source = logon_state = "unavailable"
    ace_state = "not_applicable" if logon_sid is None else "unavailable"
    restricted_state = access_state = "unavailable"
    max_access = "unavailable"
    api = None
    security_descriptor = ctypes.c_void_p()
    expected_sid: ctypes.c_void_p | None = None
    effective_token = ctypes.c_void_p()
    impersonation_token = ctypes.c_void_p()
    client_integrity_state = client_no_write_up_state = "unavailable"
    pipe_integrity_state = pipe_no_write_up_state = "unavailable"
    try:
        if sys.platform != "win32" or not pipe_handle:
            return _format_runner_pipe_access_diagnostic(
                dacl=dacl_state, ace=ace_state, token=token_source,
                logon_sid=logon_state, restricted=restricted_state,
                access=access_state, max_access=max_access,
            )
        api = _runner_pipe._load_win32_api()
        advapi = api.advapi
        advapi.GetSecurityInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_int, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.GetSecurityInfo.restype = wintypes.DWORD
        advapi.GetSecurityDescriptorDacl.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL),
        ]
        advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
        advapi.GetAce.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.GetAce.restype = wintypes.BOOL
        advapi.DuplicateToken.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.DuplicateToken.restype = wintypes.BOOL
        advapi.IsTokenRestricted.argtypes = [ctypes.c_void_p]
        advapi.IsTokenRestricted.restype = wintypes.BOOL
        advapi.AccessCheck.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(_GENERIC_MAPPING), ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.BOOL),
        ]
        advapi.AccessCheck.restype = wintypes.BOOL
        advapi.ConvertStringSidToSidW.argtypes = [
            wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.ConvertStringSidToSidW.restype = wintypes.BOOL

        if isinstance(logon_sid, str):
            expected_sid = ctypes.c_void_p()
            if not advapi.ConvertStringSidToSidW(
                logon_sid, ctypes.byref(expected_sid),
            ):
                expected_sid = ctypes.c_void_p()

        # AccessCheck rejects a descriptor without owner and group SIDs.
        status = advapi.GetSecurityInfo(
            pipe_handle, _SE_KERNEL_OBJECT, _PIPE_DIAGNOSTIC_SECURITY_INFORMATION,
            None, None, None, None, ctypes.byref(security_descriptor),
        )
        if status == 0 and security_descriptor:
            dacl_state, ace_state = _runner_pipe_dacl_observation(
                api, security_descriptor, expected_sid,
                expected_ace_mask=expected_ace_mask,
            )
        elif status != 0 or not security_descriptor:
            dacl_state = "unavailable"

        effective_token, token_source = _open_pipe_diagnostic_token(
            api, client_process_handle=client_process_handle,
        )
        pipe_integrity_state, pipe_no_write_up_state = _pipe_integrity_details(
            api, security_descriptor,
        )
        if effective_token:
            client_integrity_state = _token_integrity_level(api, effective_token)
            client_no_write_up_state = _token_mandatory_no_write_up(
                api, effective_token,
            )
            groups_buffer, groups = _runner_pipe._token_group_entries(
                _runner_pipe._get_token_information(
                    api, effective_token, _runner_pipe._TOKEN_GROUPS_CLASS,
                ),
            )
            _ = groups_buffer
            restricted_state = (
                "yes" if advapi.IsTokenRestricted(effective_token) else "no"
            )
            logon_state = "absent"
            if expected_sid:
                for sid_pointer, attributes in groups:
                    if not advapi.EqualSid(sid_pointer, expected_sid):
                        continue
                    if attributes & _SE_GROUP_USE_FOR_DENY_ONLY:
                        logon_state = "deny_only"
                    elif attributes & _SE_GROUP_ENABLED:
                        logon_state = "enabled"
                    else:
                        logon_state = "disabled"
                    break
            if advapi.DuplicateToken(
                effective_token, _SECURITY_IMPERSONATION_LEVEL,
                ctypes.byref(impersonation_token),
            ):
                if security_descriptor:
                    mapping = _GENERIC_MAPPING(
                        _FILE_GENERIC_READ, _FILE_GENERIC_WRITE,
                        _FILE_GENERIC_EXECUTE, _FILE_ALL_ACCESS,
                    )
                    for desired_access in (
                        PIPE_CLIENT_ACCESS_MASK, _MAXIMUM_ALLOWED_ACCESS,
                    ):
                        privileges = ctypes.create_string_buffer(
                            _DIAGNOSTIC_PRIVILEGE_BUFFER_BYTES,
                        )
                        privilege_length = wintypes.DWORD(
                            ctypes.sizeof(privileges),
                        )
                        granted_access = wintypes.DWORD()
                        access_granted = wintypes.BOOL()
                        accesscheck_succeeded = advapi.AccessCheck(
                            security_descriptor, impersonation_token,
                            desired_access, ctypes.byref(mapping),
                            privileges, ctypes.byref(privilege_length),
                            ctypes.byref(granted_access),
                            ctypes.byref(access_granted),
                        )
                        if desired_access == PIPE_CLIENT_ACCESS_MASK:
                            if accesscheck_succeeded:
                                access_state = (
                                    "allow" if access_granted.value else "deny"
                                )
                        else:
                            max_access = _maximum_access_mask_receipt(
                                accesscheck_succeeded,
                                int(granted_access.value),
                                int(access_granted.value),
                            )
    except Exception:
        # This is an observational probe. A diagnostic error must not change
        # whether the original CreateFileW negative test is attempted.
        pass
    finally:
        if api is not None:
            if impersonation_token:
                api.kernel.CloseHandle(impersonation_token)
            if effective_token:
                api.kernel.CloseHandle(effective_token)
            if expected_sid:
                api.kernel.LocalFree(expected_sid)
            if security_descriptor:
                api.kernel.LocalFree(security_descriptor)
    return _format_runner_pipe_access_diagnostic(
        dacl=dacl_state, ace=ace_state, token=token_source,
        logon_sid=logon_state, restricted=restricted_state,
        access=access_state, client_integrity=client_integrity_state,
        pipe_integrity=pipe_integrity_state,
        pipe_no_write_up=pipe_no_write_up_state,
        client_no_write_up=client_no_write_up_state,
        max_access=max_access,
    )


def _format_pipe_security_descriptor_shape(
    *,
    control: int,
    revision: int,
    owner_relation: str,
    group_relation: str,
    dacl_state: str,
    acl_revision: int | None,
    ace_count: int | None,
    ace_records: tuple[tuple[int, int, int | None], ...],
) -> str:
    """Encode bounded descriptor metadata without serializing any SID."""
    relations = {"user", "logon", "other", "absent", "unavailable"}
    dacl_states = {"present", "absent", "null", "unavailable"}
    if (
        type(control) is not int or not 0 <= control <= 0xFFFF
        or type(revision) is not int or not 0 <= revision <= 0xFF
        or type(owner_relation) is not str
        or owner_relation not in relations
        or type(group_relation) is not str
        or group_relation not in relations
        or type(dacl_state) is not str
        or dacl_state not in dacl_states
        or not isinstance(ace_records, tuple)
    ):
        return "sd=unavailable"
    encoded_records: list[str] = []
    truncated = False

    if dacl_state == "present":
        if (
            type(acl_revision) is not int or not 0 <= acl_revision <= 0xFF
            or type(ace_count) is not int
            or not 0 <= ace_count <= _DIAGNOSTIC_MAX_ACE_COUNT
            or len(ace_records) > ace_count
        ):
            return "sd=unavailable"
        truncated = (
            ace_count > len(ace_records)
            or len(ace_records) > _PIPE_DESCRIPTOR_MAX_ACE_REPORT
        )
        for record in ace_records[:_PIPE_DESCRIPTOR_MAX_ACE_REPORT]:
            if not isinstance(record, tuple) or len(record) != 3:
                return "sd=unavailable"
            ace_type, ace_flags, ace_mask = record
            if (
                type(ace_type) is not int or not 0 <= ace_type <= 0xFF
                or type(ace_flags) is not int or not 0 <= ace_flags <= 0xFF
                or (
                    ace_mask is not None
                    and (
                        type(ace_mask) is not int
                        or not 0 <= ace_mask <= 0xFFFFFFFF
                    )
                )
            ):
                return "sd=unavailable"
            mask_text = "--------" if ace_mask is None else f"{ace_mask:08X}"
            encoded_records.append(
                f"{ace_type:02X}.{ace_flags:02X}.{mask_text}"
            )
    elif acl_revision is not None or ace_count is not None or ace_records:
        return "sd=unavailable"

    items = ",".join(encoded_records) or "-"
    receipt = (
        f"sd_control={control:04X};sd_revision={revision};"
        f"owner={owner_relation};group={group_relation};dacl={dacl_state};"
        f"acl_revision={acl_revision if acl_revision is not None else 'x'};"
        f"ace_count={ace_count if ace_count is not None else 'x'};"
        f"aces={items};truncated={int(truncated)}"
    )
    return receipt if len(receipt) <= 384 else "sd=unavailable"


def _runner_pipe_direction_probe_sddl(logon_sid: str) -> str:
    """Return the same narrowly scoped read-only DACL for both test arms."""
    sid = _runner_pipe._validate_sid(logon_sid)
    return f"D:P(A;;GR;;;{sid})"


def _format_runner_pipe_direction_receipt(
    duplex_state: object,
    outbound_state: object,
) -> str:
    """Format fixed states only; never place SID or native error text in CI."""
    if (
        not isinstance(duplex_state, str)
        or duplex_state not in _PIPE_DIRECTION_PROBE_STATES
    ):
        duplex_state = "unavailable"
    if (
        not isinstance(outbound_state, str)
        or outbound_state not in _PIPE_DIRECTION_PROBE_STATES
    ):
        outbound_state = "unavailable"
    return (
        f"pipe_direction=duplex_{duplex_state}_outbound_{outbound_state}"
    )


def _runner_pipe_direction_probe_arm(
    api: object,
    security_descriptor: ctypes.c_void_p,
    access_mode: int,
) -> str:
    """Open one disposable pipe and make no connection or data API calls."""
    pipe_name = new_runner_pipe_name()
    open_mode = (
        _runner_pipe.RUNNER_PIPE_OPEN_MODE & ~_PIPE_ACCESS_MODE_MASK
    ) | access_mode
    attributes = _runner_pipe._SECURITY_ATTRIBUTES(
        ctypes.sizeof(_runner_pipe._SECURITY_ATTRIBUTES),
        security_descriptor,
        0,
    )
    server = _runner_pipe._INVALID_HANDLE_VALUE
    client = _runner_pipe._INVALID_HANDLE_VALUE
    state = "probe_failed"
    try:
        server = api.kernel.CreateNamedPipeW(
            pipe_name,
            open_mode,
            _runner_pipe.RUNNER_PIPE_MODE,
            _runner_pipe.RUNNER_PIPE_MAX_INSTANCES,
            _runner_pipe.RUNNER_PIPE_BUFFER_BYTES,
            _runner_pipe.RUNNER_PIPE_BUFFER_BYTES,
            0,
            ctypes.byref(attributes),
        )
        if _runner_pipe._handle_is_invalid(server):
            state = (
                "server_create_access_denied"
                if ctypes.get_last_error() == _ERROR_ACCESS_DENIED
                else "server_create_failed"
            )
        elif not api.kernel.WaitNamedPipeW(
            pipe_name, _PIPE_DIRECTION_PROBE_TIMEOUT_MS,
        ):
            error = ctypes.get_last_error()
            if error == _ERROR_ACCESS_DENIED:
                state = "wait_access_denied"
            elif error == _ERROR_SEM_TIMEOUT:
                state = "wait_timeout"
            else:
                state = "wait_failed"
        else:
            client = api.kernel.CreateFileW(
                pipe_name,
                _GENERIC_READ,
                0,
                None,
                _runner_pipe._OPEN_EXISTING,
                _runner_pipe.FILE_FLAG_OVERLAPPED
                | _runner_pipe._SECURITY_SQOS_PRESENT
                | _runner_pipe._SECURITY_IMPERSONATION,
                None,
            )
            if _runner_pipe._handle_is_invalid(client):
                error = ctypes.get_last_error()
                if error == _ERROR_ACCESS_DENIED:
                    state = "open_access_denied"
                elif error == _ERROR_PIPE_BUSY:
                    state = "open_pipe_busy"
                elif error == _ERROR_FILE_NOT_FOUND:
                    state = "open_pipe_not_found"
                else:
                    state = "open_failed"
            else:
                state = "opened"
    except Exception:
        state = "probe_failed"
    finally:
        if not _runner_pipe._handle_is_invalid(client):
            try:
                if not api.kernel.CloseHandle(client):
                    state = "client_close_failed"
            except Exception:
                state = "client_close_failed"
        if not _runner_pipe._handle_is_invalid(server):
            try:
                if not api.kernel.CloseHandle(server):
                    state = "server_close_failed"
            except Exception:
                state = "server_close_failed"
    return state


def runner_pipe_server_direction_probe() -> str:
    """Compare duplex/outbound client-open behavior without production impact.

    Both random temporary pipes use the same per-logon SID DACL, server flags,
    modes, buffers, and client GENERIC_READ open. Only the server direction
    differs. The probe does not connect through ConnectNamedPipe, inspect PIDs,
    or read/write pipe data; it records only the client CreateFileW result.
    """
    unavailable = _format_runner_pipe_direction_receipt(
        "unavailable", "unavailable",
    )
    if sys.platform != "win32":
        return _format_runner_pipe_direction_receipt(
            "unsupported_platform", "unsupported_platform",
        )

    security_descriptor = ctypes.c_void_p()
    try:
        api = _runner_pipe._load_win32_api()
        api.kernel.GetCurrentProcess.argtypes = []
        api.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process_handle = api.kernel.GetCurrentProcess()
        if not process_handle:
            return _format_runner_pipe_direction_receipt(
                "probe_failed", "probe_failed",
            )
        try:
            logon_sid = _runner_pipe._validate_sid(
                runner_process_logon_sid(process_handle),
            )
        except ValueError:
            return _format_runner_pipe_direction_receipt(
                "invalid_logon_sid", "invalid_logon_sid",
            )

        sddl = _runner_pipe_direction_probe_sddl(logon_sid)
        if not api.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(security_descriptor), None,
        ) or not security_descriptor.value:
            if security_descriptor.value:
                free_result = api.kernel.LocalFree(security_descriptor)
                security_descriptor = ctypes.c_void_p()
                if free_result:
                    return _format_runner_pipe_direction_receipt(
                        "security_descriptor_free_failed",
                        "security_descriptor_free_failed",
                    )
            return _format_runner_pipe_direction_receipt(
                "security_descriptor_failed", "security_descriptor_failed",
            )

        duplex_state = _runner_pipe_direction_probe_arm(
            api, security_descriptor, _PIPE_ACCESS_DUPLEX,
        )
        outbound_state = _runner_pipe_direction_probe_arm(
            api, security_descriptor, _PIPE_ACCESS_OUTBOUND,
        )
        free_result = api.kernel.LocalFree(security_descriptor)
        security_descriptor = ctypes.c_void_p()
        if free_result:
            return _format_runner_pipe_direction_receipt(
                "security_descriptor_free_failed",
                "security_descriptor_free_failed",
            )
        return _format_runner_pipe_direction_receipt(
            duplex_state, outbound_state,
        )
    except Exception:
        if security_descriptor.value:
            try:
                api.kernel.LocalFree(security_descriptor)
            except Exception:
                pass
        return unavailable


def runner_pipe_security_descriptor_shape(
    pipe_handle: int,
    user_sid: str | None,
    logon_sid: str | None,
) -> str:
    """Read a pipe handle's descriptor into a fixed, bounded test receipt.

    This diagnostic only queries the actual object descriptor. It does not
    mutate its ACL, inspect arbitrary SID text, or participate in production
    runner-pipe creation/open decisions.
    """
    if sys.platform != "win32" or not pipe_handle:
        return "sd=unavailable"

    api = None
    descriptor = ctypes.c_void_p()
    expected_sids: list[ctypes.c_void_p] = []
    try:
        api = _runner_pipe._load_win32_api()
        advapi = api.advapi
        advapi.GetSecurityInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_int, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.GetSecurityInfo.restype = wintypes.DWORD
        advapi.GetSecurityDescriptorControl.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.WORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL
        advapi.GetSecurityDescriptorOwner.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.BOOL),
        ]
        advapi.GetSecurityDescriptorOwner.restype = wintypes.BOOL
        advapi.GetSecurityDescriptorGroup.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.BOOL),
        ]
        advapi.GetSecurityDescriptorGroup.restype = wintypes.BOOL
        advapi.GetSecurityDescriptorDacl.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL),
        ]
        advapi.GetSecurityDescriptorDacl.restype = wintypes.BOOL
        advapi.GetAce.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.GetAce.restype = wintypes.BOOL
        advapi.ConvertStringSidToSidW.argtypes = [
            wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi.ConvertStringSidToSidW.restype = wintypes.BOOL
        advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        advapi.EqualSid.restype = wintypes.BOOL
        api.kernel.LocalFree.argtypes = [ctypes.c_void_p]
        api.kernel.LocalFree.restype = ctypes.c_void_p

        status = advapi.GetSecurityInfo(
            pipe_handle,
            _SE_KERNEL_OBJECT,
            _OWNER_SECURITY_INFORMATION
            | _GROUP_SECURITY_INFORMATION
            | _DACL_SECURITY_INFORMATION,
            None, None, None, None, ctypes.byref(descriptor),
        )
        if status != 0 or not descriptor.value:
            return "sd=unavailable"

        user_pointer = logon_pointer = None
        for sid_text in (user_sid, logon_sid):
            allocated_sid = ctypes.c_void_p()
            if (
                not isinstance(sid_text, str)
                or not advapi.ConvertStringSidToSidW(
                    sid_text, ctypes.byref(allocated_sid),
                )
                or not allocated_sid.value
            ):
                if allocated_sid.value:
                    api.kernel.LocalFree(allocated_sid)
                return "sd=unavailable"
            expected_sids.append(allocated_sid)
        user_pointer, logon_pointer = expected_sids

        control = wintypes.WORD()
        revision = wintypes.DWORD()
        if not advapi.GetSecurityDescriptorControl(
            descriptor, ctypes.byref(control), ctypes.byref(revision),
        ):
            return "sd=unavailable"

        def sid_relation(pointer: ctypes.c_void_p) -> str:
            if not pointer.value:
                return "absent"
            if advapi.EqualSid(pointer, user_pointer):
                return "user"
            if advapi.EqualSid(pointer, logon_pointer):
                return "logon"
            return "other"

        owner_pointer = ctypes.c_void_p()
        owner_defaulted = wintypes.BOOL()
        group_pointer = ctypes.c_void_p()
        group_defaulted = wintypes.BOOL()
        if not advapi.GetSecurityDescriptorOwner(
            descriptor, ctypes.byref(owner_pointer), ctypes.byref(owner_defaulted),
        ) or not advapi.GetSecurityDescriptorGroup(
            descriptor, ctypes.byref(group_pointer), ctypes.byref(group_defaulted),
        ):
            return "sd=unavailable"

        present = wintypes.BOOL()
        dacl_pointer = ctypes.c_void_p()
        dacl_defaulted = wintypes.BOOL()
        if not advapi.GetSecurityDescriptorDacl(
            descriptor, ctypes.byref(present), ctypes.byref(dacl_pointer),
            ctypes.byref(dacl_defaulted),
        ):
            return "sd=unavailable"
        if not present.value:
            dacl_state = "absent"
            acl_revision = ace_count = None
            ace_records: tuple[tuple[int, int, int | None], ...] = ()
        elif not dacl_pointer.value:
            dacl_state = "null"
            acl_revision = ace_count = None
            ace_records = ()
        else:
            dacl_state = "present"
            acl = ctypes.cast(
                dacl_pointer, ctypes.POINTER(_ACL_HEADER),
            ).contents
            acl_revision = int(acl.AclRevision)
            ace_count = int(acl.AceCount)
            if (
                int(acl.AclSize) < ctypes.sizeof(_ACL_HEADER)
                or ace_count > _DIAGNOSTIC_MAX_ACE_COUNT
            ):
                return "sd=unavailable"
            records: list[tuple[int, int, int | None]] = []
            acl_base = int(dacl_pointer.value)
            for index in range(min(ace_count, _PIPE_DESCRIPTOR_MAX_ACE_REPORT)):
                ace_pointer = ctypes.c_void_p()
                if not advapi.GetAce(
                    dacl_pointer, index, ctypes.byref(ace_pointer),
                ) or not ace_pointer.value:
                    return "sd=unavailable"
                ace = ctypes.cast(
                    ace_pointer, ctypes.POINTER(_ACE_HEADER),
                ).contents
                ace_size = int(ace.AceSize)
                ace_offset = int(ace_pointer.value) - acl_base
                if (
                    ace_size < ctypes.sizeof(_ACE_HEADER)
                    or ace_offset < ctypes.sizeof(_ACL_HEADER)
                    or ace_offset + ace_size > int(acl.AclSize)
                ):
                    return "sd=unavailable"
                ace_mask = None
                if (
                    ace.AceType in _ACE_TYPES_WITH_ACCESS_MASK
                    and ace_size >= (
                        ctypes.sizeof(_ACE_HEADER)
                        + ctypes.sizeof(wintypes.DWORD)
                    )
                ):
                    ace_mask = int.from_bytes(
                        ctypes.string_at(
                            int(ace_pointer.value) + ctypes.sizeof(_ACE_HEADER),
                            ctypes.sizeof(wintypes.DWORD),
                        ),
                        byteorder="little",
                        signed=False,
                    )
                records.append((int(ace.AceType), int(ace.AceFlags), ace_mask))
            ace_records = tuple(records)

        return _format_pipe_security_descriptor_shape(
            control=int(control.value),
            revision=int(revision.value),
            owner_relation=sid_relation(owner_pointer),
            group_relation=sid_relation(group_pointer),
            dacl_state=dacl_state,
            acl_revision=acl_revision,
            ace_count=ace_count,
            ace_records=ace_records,
        )
    except Exception:
        return "sd=unavailable"
    finally:
        if api is not None:
            for expected_sid in expected_sids:
                if expected_sid.value:
                    try:
                        api.kernel.LocalFree(expected_sid)
                    except Exception:
                        # Descriptor cleanup must not obscure the pipe-open
                        # result; this helper is confined to a short-lived test.
                        pass
            if descriptor.value:
                try:
                    api.kernel.LocalFree(descriptor)
                except Exception:
                    # Keep diagnostic cleanup failures out of the test receipt.
                    pass


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
    advapi.DuplicateToken.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.DuplicateToken.restype = wintypes.BOOL
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
    membership_token = wintypes.HANDLE()
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
            process.hProcess, _TOKEN_QUERY | _TOKEN_DUPLICATE,
            ctypes.byref(child_token),
        ):
            raise _winerror("open_child_token")
        if not advapi.IsTokenRestricted(child_token):
            raise RuntimeError("child_token_not_restricted")
        # CheckTokenMembership requires an impersonation token when a handle
        # is supplied; the process token above is primary, so duplicate it.
        if not advapi.DuplicateToken(
            child_token, _SECURITY_IMPERSONATION,
            ctypes.byref(membership_token),
        ):
            raise _winerror("duplicate_child_token_for_membership")
        child_is_admin = wintypes.BOOL()
        if not advapi.CheckTokenMembership(
            membership_token, admin_sid_buffer, ctypes.byref(child_is_admin),
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
        if membership_token:
            kernel.CloseHandle(membership_token)
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


def _attempt_rejected_logon(
    *,
    advapi: object,
    kernel: object,
    username: str,
    password: str,
    python_executable: str,
    runner_script: Path,
    report_path: Path,
    system_root: str,
) -> tuple[bool, int, bool, bool, bool]:
    """Try one invalid local logon and clean up any unexpected child immediately."""
    if os.path.lexists(report_path):
        raise RuntimeError("negative_logon_report_preexists")
    command = build_runner_command_line(
        python_executable, str(runner_script), str(report_path),
    )
    environment = build_runner_environment_block(
        python_executable=python_executable,
        scratch=str(report_path.parent),
        system_root=system_root,
    )
    environment_buffer = _make_environment_buffer(environment)
    password_buffer = ctypes.create_unicode_buffer(password)
    password = ""
    startup = _STARTUPINFO()
    startup.cb = ctypes.sizeof(startup)
    process = _PROCESS_INFORMATION()
    created = False
    error_code = 0
    process_started = False
    process_residual = False
    try:
        try:
            created = bool(advapi.CreateProcessWithLogonW(
                username,
                ".",
                password_buffer,
                0,
                python_executable,
                ctypes.create_unicode_buffer(command),
                _CREATE_UNICODE_ENVIRONMENT | _CREATE_NO_WINDOW,
                ctypes.cast(environment_buffer, ctypes.c_void_p),
                str(report_path.parent),
                ctypes.byref(startup),
                ctypes.byref(process),
            ))
            error_code = 0 if created else ctypes.get_last_error()
        finally:
            ctypes.memset(password_buffer, 0, ctypes.sizeof(password_buffer))

        process_started = bool(
            process.hProcess or process.hThread
            or process.dwProcessId or process.dwThreadId
        )
        if process.hProcess:
            wait = kernel.WaitForSingleObject(
                process.hProcess, 30_000 if created else 0,
            )
            if wait != _WAIT_OBJECT_0:
                # Any unexpected child is killed before the result is classified.
                kernel.TerminateProcess(process.hProcess, 1)
                wait = kernel.WaitForSingleObject(process.hProcess, 5_000)
            process_residual = wait != _WAIT_OBJECT_0
        elif process.dwProcessId or process.dwThreadId:
            # Without a process handle we cannot prove cleanup of a reported child.
            process_residual = True
    finally:
        try:
            if process.hProcess and kernel.WaitForSingleObject(
                process.hProcess, 0,
            ) != _WAIT_OBJECT_0:
                kernel.TerminateProcess(process.hProcess, 1)
                process_residual = (
                    kernel.WaitForSingleObject(process.hProcess, 5_000)
                    != _WAIT_OBJECT_0
                )
        finally:
            if process.hThread:
                kernel.CloseHandle(process.hThread)
            if process.hProcess:
                kernel.CloseHandle(process.hProcess)
            ctypes.memset(password_buffer, 0, ctypes.sizeof(password_buffer))

    return (
        created,
        error_code,
        process_started,
        os.path.lexists(report_path),
        process_residual,
    )


def _run_as_standard_user() -> int:
    if sys.platform != "win32":
        print("::error::restricted_token_probe_unsupported_platform")
        return 2
    # Remove credentials from this process environment before starting any
    # helper process. The runner itself receives a separately built allowlist.
    username = os.environ.pop("ICODE_R2_PROBE_USERNAME", "")
    password = os.environ.pop("ICODE_R2_PROBE_PASSWORD", "")
    sid = os.environ.pop("ICODE_R2_PROBE_SID", "")
    missing_username = os.environ.pop("ICODE_R2_PROBE_MISSING_USERNAME", "")
    if (
        not _USERNAME_RE.fullmatch(username)
        or not password
        or not _SID_RE.fullmatch(sid)
        or not _USERNAME_RE.fullmatch(missing_username)
        or missing_username == username
    ):
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
        stage_unreadable_executable_probe(
            scratch,
            Path(system_root) / "System32" / "cmd.exe",
            icacls,
            sid,
            system_root,
        )

        report = scratch / "result.txt"
        pipe_name = new_runner_pipe_name()
        request_id = secrets.token_hex(16)
        parent_pid = os.getpid()
        command = build_runner_pipe_command_line(
            sys.executable, str(runner_script), str(report),
            pipe_name, parent_pid, request_id,
        )
        environment = build_runner_environment_block(
            python_executable=sys.executable,
            scratch=str(scratch),
            system_root=system_root,
            sqos_diagnostic=(
                os.environ.get("ICODE_R2_SQOS_DIAGNOSTIC") == "true"
            ),
        )
        environment_buffer = _make_environment_buffer(environment)
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
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        kernel.GetCurrentProcessId.restype = wintypes.DWORD

        unreadable_password_buffer = ctypes.create_unicode_buffer(password)
        try:
            unreadable_observation = attempt_unreadable_executable_launch(
                create_process=advapi.CreateProcessWithLogonW,
                kernel=kernel,
                username=username,
                password_buffer=unreadable_password_buffer,
                python_executable=sys.executable,
                executable_path=scratch / "no-rx" / "cmd.exe",
                marker_path=scratch / "unreadable-executable-marker.txt",
                scratch_path=scratch,
                system_root=system_root,
                clear_last_error=lambda: ctypes.set_last_error(0),
            )
        finally:
            ctypes.memset(
                unreadable_password_buffer, 0,
                ctypes.sizeof(unreadable_password_buffer),
            )
        if not unreadable_executable_rejection_succeeded(
            created=unreadable_observation[0],
            error_code=unreadable_observation[1],
            process_started=unreadable_observation[2],
            marker_exists=unreadable_observation[3],
            process_residual=unreadable_observation[4],
        ):
            password = ""
            if unreadable_observation[4]:
                raise RuntimeError("unreadable_executable_process_residual")
            if unreadable_observation[3]:
                raise RuntimeError("unreadable_executable_marker_created")
            if unreadable_observation[0] or unreadable_observation[2]:
                raise RuntimeError("unreadable_executable_started")
            raise RuntimeError(
                "unreadable_executable_error:winerror="
                f"{unreadable_observation[1]}"
            )
        print(
            "::notice::unreadable_executable=DENIED;"
            "target=temporary_standard_user;marker=ABSENT;residual=ABSENT"
        )

        password_buffer = ctypes.create_unicode_buffer(password)
        password = ""
        startup = _STARTUPINFO()
        startup.cb = ctypes.sizeof(startup)
        process = _PROCESS_INFORMATION()
        try:
            created = advapi.CreateProcessWithLogonW(
                username, ".", password_buffer, 0, sys.executable,
                ctypes.create_unicode_buffer(command),
                _CREATE_SUSPENDED | _CREATE_UNICODE_ENVIRONMENT | _CREATE_NO_WINDOW,
                ctypes.cast(environment_buffer, ctypes.c_void_p),
                str(scratch),
                ctypes.byref(startup), ctypes.byref(process),
            )
        finally:
            ctypes.memset(password_buffer, 0, ctypes.sizeof(password_buffer))
        if not created:
            raise _winerror("create_process_with_logon")
        try:
            logon_sid = runner_process_logon_sid(process.hProcess)
            with create_runner_pipe_server(logon_sid) as timeout_pipe:
                try:
                    timeout_pipe._connect(250)
                except TimeoutError as exc:
                    if str(exc) != "runner_pipe_connect_timeout":
                        raise
                else:
                    raise RuntimeError("runner_pipe_timeout_probe_unexpected_connection")
            if timeout_pipe._handle:
                raise RuntimeError("runner_pipe_timeout_handle_leaked")

            with create_runner_pipe_server(logon_sid, name=pipe_name) as pipe:
                try:
                    unauthorized = open_runner_pipe_client(
                        pipe.name, parent_pid, timeout_ms=1_000,
                    )
                except PermissionError as exc:
                    if exc.errno != _ERROR_ACCESS_DENIED:
                        raise RuntimeError("runner_pipe_other_sid_rejection_unverified") from exc
                else:
                    unauthorized.close()
                    raise RuntimeError("runner_pipe_other_sid_was_allowed")

                resumed = kernel.ResumeThread(process.hThread)
                if resumed != 1:
                    raise RuntimeError("runner_resume_thread_failed")
                try:
                    pipe.wait_for_runner_ready(
                        expected_process_handle=process.hProcess,
                        expected_user_sid=sid,
                        expected_logon_sid=logon_sid,
                        request_id=request_id,
                        timeout_ms=15_000,
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    detail = _runner_child_failure_if_exited(
                        kernel=kernel,
                        process_handle=process.hProcess,
                        report_path=report,
                        server_pipe_handle=pipe._handle,
                        expected_logon_sid=logon_sid,
                    )
                    if detail is not None:
                        raise RuntimeError(
                            f"standard_user_restricted_child_failed:{detail}"
                        ) from exc
                    raise
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
            detail = restricted_child_failure_detail(result)
            raise RuntimeError(f"standard_user_restricted_child_failed:{detail}")

        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        invalid_password = password + "_invalid"
        missing_root = scratch / "missing_account"
        missing_root.mkdir()
        missing_report = missing_root / "result.txt"
        missing_observation = _attempt_rejected_logon(
            advapi=advapi,
            kernel=kernel,
            username=missing_username,
            password=password,
            python_executable=sys.executable,
            runner_script=runner_script,
            report_path=missing_report,
            system_root=system_root,
        )
        password = ""
        if not logon_rejection_succeeded(
            expected_error_codes=(_ERROR_NO_SUCH_USER, _ERROR_LOGON_FAILURE),
            created=missing_observation[0],
            error_code=missing_observation[1],
            process_started=missing_observation[2],
            marker_exists=missing_observation[3],
            process_residual=missing_observation[4],
        ):
            raise RuntimeError(
                f"missing_account_rejection_failed:winerror={missing_observation[1]};"
                f"created={int(missing_observation[0])};"
                f"child={int(missing_observation[2])};"
                f"report={int(missing_observation[3])};"
                f"residual={int(missing_observation[4])}"
            )

        bad_password_root = scratch / "bad_password"
        bad_password_root.mkdir()
        bad_password_report = bad_password_root / "result.txt"
        bad_password_observation = _attempt_rejected_logon(
            advapi=advapi,
            kernel=kernel,
            username=username,
            password=invalid_password,
            python_executable=sys.executable,
            runner_script=runner_script,
            report_path=bad_password_report,
            system_root=system_root,
        )
        invalid_password = ""
        if not logon_rejection_succeeded(
            expected_error_codes=(_ERROR_LOGON_FAILURE,),
            created=bad_password_observation[0],
            error_code=bad_password_observation[1],
            process_started=bad_password_observation[2],
            marker_exists=bad_password_observation[3],
            process_residual=bad_password_observation[4],
        ):
            raise RuntimeError(
                f"bad_password_rejection_failed:winerror={bad_password_observation[1]};"
                f"created={int(bad_password_observation[0])};"
                f"child={int(bad_password_observation[2])};"
                f"report={int(bad_password_observation[3])};"
                f"residual={int(bad_password_observation[4])}"
            )

        print(
            "standard_user_token_probe=PASS " + result
            + " runner_pipe_probe=PASS;logon_sid_dacl=PASS;other_sid=ACCESS_DENIED;"
            "server_pid_mismatch=DENIED;client_pid=PASS;token_sid_session=PASS;"
            "timeout_cancel=PASS "
            + " negative_logon_probes=PASS;missing_account=FAIL_CLOSED;"
            "bad_password=FAIL_CLOSED;unreadable_executable=FAIL_CLOSED;"
            "runner_report=ABSENT;child=ABSENT;marker=ABSENT;residual=ABSENT"
        )
        result_code = 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        print(
            "::error::standard_user_token_probe_failed "
            + _safe_standard_user_probe_error(exc)
        )
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


def _run_child_mode(
    report_path: str,
    pipe_name: str,
    server_pid_text: str,
    request_id: str,
) -> int:
    if sys.platform != "win32":
        return 2
    validated_report: Path | None = None
    effective_token_diagnostic: str | None = None
    wrong_pid_probe_state: str | None = None
    no_sync_probe_state: str | None = None
    no_overlapped_probe_state: str | None = None
    default_dacl_probe_state: str | None = None
    user_sid_dacl_probe_state: str | None = None
    user_sid_create_instance_probe_state: str | None = None
    temporary_acl_probe_receipt: str | None = None
    self_pipe_access_probe_state: str | None = None
    access_mask_matrix_state: str | None = None
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
        validated_report = report
        if not server_pid_text.isascii() or not server_pid_text.isdecimal():
            return 2
        server_pid = int(server_pid_text)
        if not 1 <= server_pid <= 0xFFFFFFFF:
            return 2
        if re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
            return 2
        # Exercise PID mismatch from the temporary standard-user logon itself.
        # If its exact DACL self-open is denied, run diagnostic A/Bs one at a
        # time, changing only one client open option per probe. None changes
        # production permissions or replaces the parent handshake.
        pipe_rejected, _pipe_detail = runner_pipe_wrong_server_pid_probe()
        if pipe_rejected is True:
            wrong_pid_probe_state = "self_pipe_ok"
        elif (
            type(_pipe_detail) is str
            and _pipe_detail.startswith("client_open_access_denied")
        ):
            wrong_pid_probe_state = "self_pipe_denied"
            # Keep only the fixed AccessCheck result. The same temporary
            # self-pipe CreateFileW attempt has just returned access denied.
            self_pipe_access_probe_state = _self_pipe_access_receipt_label(
                _pipe_detail,
            )
            no_sync_opened, no_sync_detail = (
                runner_pipe_open_without_synchronize_probe()
            )
            if no_sync_opened is True:
                no_sync_probe_state = "nosync_ok"
            elif (
                type(no_sync_detail) is str
                and no_sync_detail == "client_open_access_denied"
            ):
                no_sync_probe_state = "nosync_denied"
                no_overlapped_opened, no_overlapped_detail = (
                    runner_pipe_open_without_overlapped_probe()
                )
                if no_overlapped_opened is True:
                    no_overlapped_probe_state = "noovl_ok"
                elif (
                    type(no_overlapped_detail) is str
                    and no_overlapped_detail == "client_open_access_denied"
                ):
                    no_overlapped_probe_state = "noovl_denied"
                    default_dacl_opened, default_dacl_detail = (
                        runner_pipe_open_with_default_dacl_probe()
                    )
                    temporary_acl_probe_receipt = "tmp_" + (
                        _runner_pipe_probe_receipt_code(
                            "d", default_dacl_opened, default_dacl_detail,
                        )
                    )
                    if default_dacl_opened is True:
                        default_dacl_probe_state = "default_dacl_ok"
                    elif _runner_pipe_probe_open_denied(default_dacl_detail):
                        default_dacl_probe_state = "default_dacl_denied"
                    else:
                        default_dacl_probe_state = "default_dacl_failed"
                    user_sid_dacl_opened, user_sid_dacl_detail = (
                        runner_pipe_open_with_user_sid_dacl_probe()
                    )
                    temporary_acl_probe_receipt += "_" + (
                        _runner_pipe_probe_receipt_code(
                            "u", user_sid_dacl_opened, user_sid_dacl_detail,
                        )
                    )
                    if user_sid_dacl_opened is True:
                        user_sid_dacl_probe_state = "user_sid_dacl_ok"
                    elif _runner_pipe_probe_open_denied(user_sid_dacl_detail):
                        user_sid_dacl_probe_state = "user_sid_dacl_denied"
                        create_instance_opened, create_instance_detail = (
                            runner_pipe_open_with_user_sid_create_instance_access_probe()
                        )
                        temporary_acl_probe_receipt += "_" + (
                            _runner_pipe_probe_receipt_code(
                                "c", create_instance_opened,
                                create_instance_detail,
                            )
                        )
                        if create_instance_opened is True:
                            user_sid_create_instance_probe_state = (
                                "user_sid_create_instance_ok"
                            )
                        elif _runner_pipe_probe_open_denied(create_instance_detail):
                            user_sid_create_instance_probe_state = (
                                "user_sid_create_instance_denied"
                            )
                        else:
                            user_sid_create_instance_probe_state = (
                                "user_sid_create_instance_failed"
                            )
                    else:
                        user_sid_dacl_probe_state = "user_sid_dacl_failed"
                else:
                    no_overlapped_probe_state = "noovl_failed"
            else:
                no_sync_probe_state = "nosync_failed"
            # Keep the explicit logon-SID DACL and client flags fixed while
            # exhaustively varying only the three client access bits.
            access_mask_matrix_state = runner_pipe_access_mask_matrix_probe()
        else:
            wrong_pid_probe_state = "self_pipe_failed"

        def capture_effective_token() -> None:
            nonlocal effective_token_diagnostic
            effective_token_diagnostic = _runner_effective_token_diagnostic()

        with _runner_pipe._open_runner_pipe_client_with_observer(
            pipe_name, server_pid, timeout_ms=15_000,
            observer=capture_effective_token,
        ) as pipe:
            pipe.send_message({
                "version": 1,
                "type": "spawn_ready",
                "request_id": request_id,
            }, timeout_ms=15_000)
        safe_pipe_detail = re.sub(
            r"[^A-Za-z0-9_+.-]", "_", str(_pipe_detail),
        )[:120] or "unknown"
        result = (
            _runner_probe(report) if pipe_rejected else
            "failed=runner_pipe_server_pid_mismatch;detail=" + safe_pipe_detail
        )
        _write_report(report, result)
        return 0 if runner_probe_succeeded(result) else 1
    except Exception as exc:  # noqa: BLE001 - child reports only a fixed safe label
        if validated_report is not None:
            try:
                failure_detail = _safe_runner_child_exception_detail(exc)
                sqos_probe_receipt: str | None = None
                if (
                    failure_detail == "client_open_access_denied"
                    and os.environ.get("ICODE_R2_SQOS_DIAGNOSTIC") == "1"
                ):
                    try:
                        sqos_probe_result = runner_pipe_open_without_sqos_probe(
                            pipe_name, server_pid,
                        )
                    except Exception:
                        sqos_probe_result = "probe_failed"
                    sqos_probe_receipt = {
                        "opened": "sqos_default_opened",
                        "access_denied": "sqos_default_access_denied",
                        "pipe_busy": "sqos_default_pipe_busy",
                        "wait_timeout": "sqos_default_wait_timeout",
                        "wait_access_denied": "sqos_default_wait_access_denied",
                        "pipe_not_found": "sqos_default_pipe_not_found",
                        "server_pid_unavailable": "sqos_default_server_pid_unavailable",
                        "server_pid_mismatch": "sqos_default_server_pid_mismatch",
                        "probe_failed": "sqos_default_probe_failed",
                        "unsupported_platform": "sqos_default_unavailable",
                        "invalid_pipe_name": "sqos_default_invalid_pipe",
                        "invalid_server_pid": "sqos_default_invalid_pid",
                    }.get(sqos_probe_result, "sqos_default_unavailable")
                if failure_detail == "client_open_access_denied":
                    diagnostic = effective_token_diagnostic or "token_unavailable"
                    minimal_diagnostic = _minimal_runner_effective_token_diagnostic(
                        effective_token_diagnostic,
                    )
                    minimal_token = minimal_diagnostic.partition("+")[0]
                    context_parts = [diagnostic]
                    if user_sid_create_instance_probe_state is not None:
                        # The compact receipt retains each disposable DACL's
                        # CreateFileW and same-handle AccessCheck outcome.
                        context_parts = [
                            _compact_runner_effective_token_diagnostic(
                                effective_token_diagnostic,
                            ),
                            temporary_acl_probe_receipt or "tmp_unavailable",
                        ]
                    elif user_sid_dacl_probe_state is not None:
                        context_parts = [
                            _compact_runner_effective_token_diagnostic(
                                effective_token_diagnostic,
                            ),
                            temporary_acl_probe_receipt or "tmp_unavailable",
                        ]
                    elif wrong_pid_probe_state is not None:
                        context_parts.append(wrong_pid_probe_state)
                    if self_pipe_access_probe_state is not None:
                        context_parts.append(self_pipe_access_probe_state)
                    if sqos_probe_receipt is not None:
                        context_parts.append(sqos_probe_receipt)
                    if (
                        default_dacl_probe_state is not None
                        and user_sid_dacl_probe_state is None
                    ):
                        # This final A/B only runs after the self, no-SYNCHRONIZE,
                        # and no-OVERLAPPED probes all returned access denied.
                        # Keep the bounded receipt focused on the changed DACL.
                        context_parts.append(
                            temporary_acl_probe_receipt or default_dacl_probe_state,
                        )
                    elif (
                        user_sid_dacl_probe_state is None
                        and no_overlapped_probe_state is not None
                    ):
                        combined_probe_state = {
                            "noovl_ok": "nosync_noovl_ok",
                            "noovl_denied": "nosync_noovl_denied",
                        }.get(no_overlapped_probe_state, "nosync_noovl_failed")
                        context_parts.append(combined_probe_state)
                    elif (
                        user_sid_dacl_probe_state is None
                        and default_dacl_probe_state is None
                        and no_sync_probe_state is not None
                    ):
                        context_parts.append(no_sync_probe_state)
                    error_code = _safe_windows_error_code(exc)
                    context_parts.append(f"open_winerror_{error_code}")
                    context = "+".join(context_parts)
                    if (
                        len(context) > 120
                        and self_pipe_access_probe_state is not None
                    ):
                        compact_parts = [minimal_diagnostic]
                        if temporary_acl_probe_receipt is not None:
                            compact_parts.extend((
                                temporary_acl_probe_receipt,
                                self_pipe_access_probe_state,
                            ))
                        elif default_dacl_probe_state is not None:
                            compact_parts.extend((
                                default_dacl_probe_state,
                                self_pipe_access_probe_state,
                            ))
                        elif no_overlapped_probe_state is not None:
                            combined_probe_state = {
                                "noovl_ok": "nosync_noovl_ok",
                                "noovl_denied": "nosync_noovl_denied",
                            }.get(no_overlapped_probe_state, "nosync_noovl_failed")
                            compact_parts.extend((
                                "self_pipe_denied",
                                self_pipe_access_probe_state,
                                combined_probe_state,
                            ))
                        elif no_sync_probe_state is not None:
                            compact_parts.extend((
                                "self_pipe_denied",
                                self_pipe_access_probe_state,
                                no_sync_probe_state,
                            ))
                        else:
                            compact_parts.extend((
                                "self_pipe_denied",
                                self_pipe_access_probe_state,
                            ))
                        compact_parts.append(f"open_winerror_{error_code}")
                        context = "+".join(compact_parts)
                        if len(context) > 120:
                            context = "+".join((
                                minimal_diagnostic,
                                "self_pipe_denied",
                                self_pipe_access_probe_state,
                                f"open_winerror_{error_code}",
                            ))
                    elif (
                        len(context) > 120
                        and user_sid_create_instance_probe_state is not None
                    ):
                        context = "+".join((
                            minimal_diagnostic,
                            temporary_acl_probe_receipt or "tmp_unavailable",
                            f"open_winerror_{error_code}",
                        ))
                    elif (
                        len(context) > 120
                        and user_sid_dacl_probe_state is not None
                    ):
                        context = "+".join((
                            minimal_diagnostic,
                            temporary_acl_probe_receipt or "tmp_unavailable",
                            f"open_winerror_{error_code}",
                        ))
                    if (
                        len(context) > 120
                        or re.fullmatch(r"[A-Za-z0-9_+.-]+", context) is None
                    ):
                        if self_pipe_access_probe_state is not None:
                            context = "+".join((
                                minimal_diagnostic,
                                "self_pipe_denied",
                                self_pipe_access_probe_state,
                                f"open_winerror_{error_code}",
                            ))
                        else:
                            context = f"{minimal_token}+open_winerror_{error_code}"
                    if access_mask_matrix_state is not None:
                        # The full rights matrix is the highest-value bounded
                        # evidence for this failure; retain it over earlier
                        # ACL A/B labels unless it repeats the same denial for
                        # all eight rights. In that case a fixed summary leaves
                        # room for the ACL controls already run in this child.
                        matrix_state = access_mask_matrix_state
                        if (
                            not isinstance(matrix_state, str)
                            or len(matrix_state) > 110
                            or re.fullmatch(
                                r"(?:mask_[A-Za-z0-9_+.-]+|matrix_[a-z_]+)",
                                matrix_state,
                            ) is None
                        ):
                            matrix_state = "matrix_unavailable"
                        if (
                            matrix_state == _RUNNER_PIPE_ACCESS_MATRIX_ALL_D5_RECEIPT
                            and default_dacl_probe_state is not None
                            and user_sid_dacl_probe_state is not None
                        ):
                            context_parts = [
                                minimal_diagnostic,
                                temporary_acl_probe_receipt or "tmp_unavailable",
                            ]
                            context_parts.extend((
                                "mask_all_d5",
                                f"winerror_{error_code}",
                            ))
                            context = "+".join(context_parts)
                            if len(context) > 120:
                                # Preserve the DACL comparisons and the actual
                                # client-open error over a repeated matrix.
                                context_parts.remove("mask_all_d5")
                                context = "+".join(context_parts)
                            if len(context) > 120:
                                # The parent independently records the child
                                # token; keep the exact ACL outcomes first.
                                context_parts = [
                                    temporary_acl_probe_receipt or "tmp_unavailable",
                                ]
                                context_parts.append(f"winerror_{error_code}")
                                context = "+".join(context_parts)
                        else:
                            matrix_context = "+".join((
                                minimal_diagnostic,
                                self_pipe_access_probe_state or "self_access_unavailable",
                                matrix_state,
                                f"open_winerror_{error_code}",
                            ))
                            if len(matrix_context) > 120:
                                matrix_context = "+".join((
                                    matrix_state,
                                    f"open_winerror_{error_code}",
                                ))
                            if len(matrix_context) > 120:
                                matrix_context = matrix_state
                            context = matrix_context
                    if sqos_probe_receipt is not None:
                        sqos_context = [minimal_diagnostic]
                        if temporary_acl_probe_receipt is not None:
                            sqos_context.append(temporary_acl_probe_receipt)
                        if access_mask_matrix_state == _RUNNER_PIPE_ACCESS_MATRIX_ALL_D5_RECEIPT:
                            sqos_context.append("mask_all_d5")
                        sqos_context.extend((
                            sqos_probe_receipt,
                            f"open_winerror_{error_code}",
                        ))
                        context = "+".join(sqos_context)
                        if len(context) > 120:
                            context = "+".join((
                                minimal_diagnostic,
                                sqos_probe_receipt,
                                f"open_winerror_{error_code}",
                            ))
                    failure_detail += ";detail=" + context
                _write_report(
                    validated_report,
                    "failed=" + failure_detail,
                )
            except OSError:
                pass
        return 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if (
        len(args) == 8
        and args[0] == "--runner"
        and args[2] == "--pipe"
        and args[4] == "--server-pid"
        and args[6] == "--request-id"
    ):
        return _run_child_mode(args[1], args[3], args[5], args[7])
    if args:
        print("::error::restricted_token_probe_arguments_invalid")
        return 2
    return _run_as_standard_user()


if __name__ == "__main__":
    raise SystemExit(main())
