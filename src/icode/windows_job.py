"""R2.3 开发期 Windows 工单级进程回收；尚不提供文件/网络隔离。"""

from __future__ import annotations

import ctypes
import ntpath
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


_READ_HANDLE_PLACEHOLDER = "{ICODE_READ_HANDLE}"
_PRIVATE_NETWORK_CAPABILITY_SID = "S-1-15-3-3"
_SE_GROUP_ENABLED = 0x00000004
_TOKEN_GROUPS_CAPABILITY_PARSER_CODE = """\
class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [('Sid', ctypes.c_void_p), ('Attributes', wintypes.DWORD)]
class TOKEN_GROUPS(ctypes.Structure):
    _fields_ = [('GroupCount', wintypes.DWORD), ('Groups', SID_AND_ATTRIBUTES * 1)]
def _read_single_token_capability(buffer_address, buffer_capacity, returned_length):
    header_size = TOKEN_GROUPS.Groups.offset
    entry_size = ctypes.sizeof(SID_AND_ATTRIBUTES)
    if not buffer_address or buffer_capacity < header_size:
        raise ValueError('invalid token group buffer capacity')
    if returned_length < header_size:
        raise ValueError('invalid token group return length')
    if returned_length > buffer_capacity:
        raise ValueError('token group return length exceeds buffer capacity')
    group_count = ctypes.cast(
        buffer_address, ctypes.POINTER(TOKEN_GROUPS),
    ).contents.GroupCount
    if group_count != 1:
        raise ValueError('unexpected capability count')
    required_length = header_size + group_count * entry_size
    if returned_length < required_length:
        raise ValueError('truncated token group return length')
    capability = ctypes.cast(
        buffer_address + header_size, ctypes.POINTER(SID_AND_ATTRIBUTES),
    ).contents
    if not capability.Sid:
        raise ValueError('missing capability SID')
    return capability.Sid, int(capability.Attributes)
"""

_PRIVATE_NETWORK_CAPABILITY_PROBE_CODE = (
    """\
import sys
_failure_exit_code = 80
def _stage_failure_hook(exc_type, _exc_value, _traceback):
    if issubclass(exc_type, Exception):
        sys.exit(_failure_exit_code)
    sys.__excepthook__(exc_type, _exc_value, _traceback)
sys.excepthook = _stage_failure_hook
import ctypes, json, socket
from ctypes import wintypes
"""
    + _TOKEN_GROUPS_CAPABILITY_PARSER_CODE
    + """\
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
advapi = ctypes.WinDLL('advapi32', use_last_error=True)
SE_GROUP_ENABLED = 0x00000004
advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi.OpenProcessToken.restype = wintypes.BOOL
advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
advapi.GetTokenInformation.restype = wintypes.BOOL
advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.LocalFree.argtypes = [ctypes.c_void_p]
kernel.LocalFree.restype = ctypes.c_void_p
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.CloseHandle.restype = wintypes.BOOL
def sid_text(sid):
    text = wintypes.LPWSTR()
    if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return text.value
    finally:
        kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
_failure_exit_code = 81
token = wintypes.HANDLE()
if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
    raise ctypes.WinError(ctypes.get_last_error())
try:
    returned = wintypes.DWORD()
    appcontainer = wintypes.DWORD()
    _failure_exit_code = 82
    if not advapi.GetTokenInformation(token, 29, ctypes.byref(appcontainer), ctypes.sizeof(appcontainer), ctypes.byref(returned)):
        raise ctypes.WinError(ctypes.get_last_error())
    _failure_exit_code = 83
    package_size = wintypes.DWORD()
    ctypes.set_last_error(0)
    advapi.GetTokenInformation(token, 31, None, 0, ctypes.byref(package_size))
    if ctypes.get_last_error() != 122 or package_size.value < ctypes.sizeof(ctypes.c_void_p):
        raise ctypes.WinError(ctypes.get_last_error() or 87)
    package_buffer = ctypes.create_string_buffer(package_size.value)
    if not advapi.GetTokenInformation(token, 31, package_buffer, package_size.value, ctypes.byref(returned)):
        raise ctypes.WinError(ctypes.get_last_error())
    package_sid = ctypes.cast(package_buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
    _failure_exit_code = 84
    capability_buffer = ctypes.create_string_buffer(4096)
    if not advapi.GetTokenInformation(token, 30, capability_buffer, len(capability_buffer), ctypes.byref(returned)):
        raise ctypes.WinError(ctypes.get_last_error())
    capability_sid, capability_attributes = _read_single_token_capability(
        ctypes.addressof(capability_buffer), len(capability_buffer), returned.value,
    )
    _failure_exit_code = 85
    package_text = sid_text(package_sid)
    _failure_exit_code = 86
    capability_text = sid_text(capability_sid)
    _failure_exit_code = 87
    if not appcontainer.value:
        raise RuntimeError('unexpected AppContainer token flag')
    _failure_exit_code = 88
    if package_text != sys.argv[4]:
        raise RuntimeError('unexpected AppContainer package SID')
    _failure_exit_code = 89
    if capability_text != 'S-1-15-3-3':
        raise RuntimeError('unexpected AppContainer capability SID')
    if not (capability_attributes & SE_GROUP_ENABLED):
        # Keep the failed bit check, but distinguish an empty attribute word
        # from nonzero flags in the native CI receipt without changing policy.
        _failure_exit_code = 90 if capability_attributes == 0 else 95
        raise RuntimeError('unexpected AppContainer token capability')
    payload = json.dumps({
        'nonce': sys.argv[3], 'appcontainer': True,
        'package_sid': package_text, 'capability_count': 1,
        'capability_sid': capability_text,
    }, sort_keys=True, separators=(',', ':')).encode('ascii')
finally:
    kernel.CloseHandle(token)
for family, address, port in (
    (socket.AF_INET, '127.0.0.1', int(sys.argv[1]), 91, 92),
    (socket.AF_INET6, '::1', int(sys.argv[2]), 93, 94),
):
    _failure_exit_code = 91 if family == socket.AF_INET else 93
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect((address, port))
        _failure_exit_code = 92 if family == socket.AF_INET else 94
        connection.sendall(payload)
"""
)

_PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES = {
    0: "probe_completed",
    80: "probe_initialization",
    81: "token_open",
    82: "token_appcontainer",
    83: "token_package_sid",
    84: "token_capabilities",
    85: "token_package_sid_text",
    86: "token_capability_sid_text",
    87: "token_appcontainer_match",
    88: "token_package_sid_match",
    89: "token_capability_sid_match",
    90: "token_capability_enabled_missing_zero_attributes",
    91: "ipv4_connect",
    92: "ipv4_send",
    93: "ipv6_connect",
    94: "ipv6_send",
    95: "token_capability_enabled_missing_nonzero_attributes",
}


def _private_network_capability_exit_stage(exit_code: int | None) -> str:
    """Translate only fixed probe exits into bounded, non-sensitive stages."""
    if exit_code is None:
        return "no_exit_code"
    if type(exit_code) is not int:
        return "unclassified"
    return _PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES.get(
        exit_code, "unclassified",
    )


def _build_private_network_capability_probe_argv(
    python_executable: str | os.PathLike[str], ipv4_port: int, ipv6_port: int,
    nonce: str, package_sid: str,
) -> list[str]:
    """Construct the only Python payload accepted by the CI-only capability probe."""
    if (
        type(ipv4_port) is not int or not 1 <= ipv4_port <= 65535
        or type(ipv6_port) is not int or not 1 <= ipv6_port <= 65535
        or not isinstance(nonce, str) or len(nonce) != 32
        or any(character not in "0123456789abcdef" for character in nonce)
        or not isinstance(package_sid, str)
        or not package_sid.startswith("S-1-15-2-")
        or len(package_sid) > 256
        or "\0" in package_sid
    ):
        raise ValueError("invalid fixed private-network AppContainer probe parameters")
    return [
        os.fspath(python_executable), "-I", "-c",
        _PRIVATE_NETWORK_CAPABILITY_PROBE_CODE,
        str(ipv4_port), str(ipv6_port), nonce, package_sid,
    ]


def _is_fixed_private_network_capability_probe(
    argv: Sequence[str], cwd: str | os.PathLike[str],
) -> bool:
    """Fail closed unless this is the fixed dual-loopback CI diagnostic command."""
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_OS") != "Windows"
        or os.environ.get("ICODE_DIAGNOSTIC_NETWORK_CAPABILITY") != "true"
        or isinstance(argv, (str, bytes))
        or not isinstance(argv, Sequence)
        or len(argv) != 8
        or any(not isinstance(argument, str) or "\0" in argument for argument in argv)
        or argv[1] != "-I"
        or argv[2] != "-c"
        or argv[3] != _PRIVATE_NETWORK_CAPABILITY_PROBE_CODE
        or ntpath.basename(argv[0]).casefold() != "python.exe"
    ):
        return False
    try:
        executable = ntpath.normcase(ntpath.normpath(argv[0]))
        workspace = ntpath.normcase(ntpath.normpath(os.fspath(cwd)))
        temp_root = ntpath.normcase(ntpath.normpath(tempfile.gettempdir()))
        runtime_dir = ntpath.basename(ntpath.dirname(executable)).casefold()
        workspace_name = ntpath.basename(workspace).casefold()
        probe_dir = ntpath.basename(ntpath.dirname(workspace)).casefold()
        if (
            not ntpath.isabs(executable) or not ntpath.isabs(workspace)
            or not ntpath.isabs(temp_root)
            or ntpath.commonpath((temp_root, executable)) != temp_root
            or ntpath.commonpath((temp_root, workspace)) != temp_root
            or not runtime_dir.startswith("icode-runtime-staging-reviewer-")
            or workspace_name != "task-scratch"
            or not probe_dir.startswith("icode-reviewer-appcontainer-probe-")
        ):
            return False
        if any(
            not value.isascii() or not value.isdecimal()
            or not 1 <= int(value) <= 65535
            for value in argv[4:6]
        ):
            return False
        if (
            len(argv[6]) != 32
            or any(character not in "0123456789abcdef" for character in argv[6])
            or not argv[7].startswith("S-1-15-2-")
            or len(argv[7]) > 256
        ):
            return False
    except (OSError, TypeError, ValueError):
        return False
    return True


@dataclass(frozen=True)
class WindowsJobResult:
    executed: bool
    exit_code: int | None
    error: str | None
    cleanup_ok: bool
    detail: str


@dataclass(frozen=True)
class WindowsJobProbeResult:
    executed: bool
    passed: bool
    checks: dict[str, bool]
    detail: str


class _FILE_STANDARD_INFO(ctypes.Structure):
    """Win32 FILE_STANDARD_INFO; BOOLEAN fields are one byte, not BOOL."""

    _fields_ = [
        ("AllocationSize", ctypes.c_longlong),
        ("EndOfFile", ctypes.c_longlong),
        ("NumberOfLinks", ctypes.c_uint32),
        ("DeletePending", ctypes.c_ubyte),
        ("Directory", ctypes.c_ubyte),
    ]


def _allocate_attribute_list_buffer(
    required_size: int,
) -> tuple[ctypes.Array, ctypes.c_void_p]:
    """Allocate enough pointer-aligned storage for a Win32 attribute list."""
    if required_size <= 0:
        raise ValueError("attribute-list size must be positive")
    pointer_size = ctypes.sizeof(ctypes.c_void_p)
    element_count = (required_size + pointer_size - 1) // pointer_size
    storage = (ctypes.c_size_t * element_count)()
    return storage, ctypes.cast(storage, ctypes.c_void_p)


def _bind_read_handle_placeholder(
    argv: Sequence[str], handle_value: int,
) -> list[str]:
    """Bind one explicit diagnostic token to the duplicated read-only handle."""
    if (
        isinstance(argv, (str, bytes))
        or not isinstance(argv, Sequence)
        or type(handle_value) is not int
        or handle_value <= 0
        or any(not isinstance(argument, str) for argument in argv)
    ):
        raise ValueError("invalid inherited read-handle binding")
    matches = [argument for argument in argv if argument == _READ_HANDLE_PLACEHOLDER]
    if len(matches) != 1 or any(
        _READ_HANDLE_PLACEHOLDER in argument
        and argument != _READ_HANDLE_PLACEHOLDER
        for argument in argv
    ):
        raise ValueError("read-handle placeholder must appear as one whole argument")
    return [
        str(handle_value) if argument == _READ_HANDLE_PLACEHOLDER else argument
        for argument in argv
    ]


def _is_fixed_read_handle_probe(
    argv: Sequence[str], cwd: str | os.PathLike[str], handle_value: int,
) -> bool:
    """Share the fail-closed runner, executable, workspace, and argument gate."""
    if (
        type(handle_value) is not int
        or handle_value <= 0
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_OS") != "Windows"
        or os.environ.get("ICODE_DIAGNOSTIC_READ_HANDLE") != "true"
        or isinstance(argv, (str, bytes))
        or not isinstance(argv, Sequence)
        or not argv
        or not isinstance(argv[0], str)
        or not os.path.isabs(argv[0])
        or ntpath.basename(argv[0]).casefold() != "icode-appcontainer-read-probe.exe"
    ):
        return False
    try:
        _bind_read_handle_placeholder(argv, handle_value)
        probe_path = os.path.normcase(os.path.realpath(argv[0]))
        workspace_path = os.path.normcase(
            os.path.realpath(os.path.abspath(os.fspath(cwd))),
        )
    except (OSError, TypeError, ValueError):
        return False
    return bool(probe_path) and os.path.dirname(probe_path) == workspace_path


def _build_windows_environment_block(
    executable: str | os.PathLike[str], cwd: str | os.PathLike[str],
    system_root: str | os.PathLike[str],
) -> str:
    """Build a minimal Unicode block, including drive-current-dir entries."""
    executable_path = os.fspath(executable)
    workspace_path = os.fspath(cwd)
    system_path = os.fspath(system_root)
    workspace_drive = ntpath.splitdrive(workspace_path)[0].upper()

    drive_directories: dict[str, str] = {}
    for path in (workspace_path, executable_path, system_path):
        drive = ntpath.splitdrive(path)[0].upper()
        if len(drive) == 2 and drive[1] == ":":
            # Relative paths on the task drive stay rooted in the task workspace.
            # Other drives start at their roots; AppContainer ACLs remain authoritative.
            drive_directories[drive] = (
                workspace_path if drive == workspace_drive else f"{drive}\\"
            )

    environment = {
        "SystemRoot": system_path,
        "WINDIR": system_path,
        "PATH": ";".join(
            (ntpath.dirname(executable_path), ntpath.join(system_path, "System32"))
        ),
        "TEMP": workspace_path,
        "TMP": workspace_path,
        "USERPROFILE": workspace_path,
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
    }
    entries = [(f"={drive}", directory) for drive, directory in drive_directories.items()]
    entries.extend(environment.items())
    entries.sort(key=lambda entry: entry[0].casefold())
    return "\0".join(f"{name}={value}" for name, value in entries) + "\0\0"


def _append_windows_environment_value(
    block: str, name: str, value: str,
) -> str:
    """Append one non-drive variable to a validated double-NUL environment block."""
    if (
        not isinstance(block, str) or not block.endswith("\0\0")
        or not isinstance(name, str) or not name
        or "=" in name or "\0" in name
        or not isinstance(value, str) or "\0" in value
    ):
        raise ValueError("invalid Unicode environment block entry")
    entries = [entry for entry in block.split("\0") if entry]
    existing_names = [
        entry[:entry.index("=", 1)] if entry.startswith("=")
        else entry.split("=", 1)[0]
        for entry in entries
    ]
    if any(existing.casefold() == name.casefold() for existing in existing_names):
        raise ValueError("environment variable already exists")
    entries.append(f"{name}={value}")
    entries.sort(key=lambda entry: (
        entry[:entry.index("=", 1)] if entry.startswith("=")
        else entry.split("=", 1)[0]
    ).casefold())
    return "\0".join(entries) + "\0\0"


def _is_fixed_system_whoami_probe(
    argv: Sequence[str], system_root: str | os.PathLike[str],
) -> bool:
    r"""Permit a launch-only diagnostic for exactly System32\whoami.exe."""
    if len(argv) != 1:
        return False
    try:
        executable = os.fspath(argv[0])
        root = os.fspath(system_root)
        if not isinstance(executable, str) or not isinstance(root, str):
            return False
        expected = ntpath.join(root, "System32", "whoami.exe")
        return (
            ntpath.isabs(executable)
            and ntpath.normcase(ntpath.normpath(executable))
            == ntpath.normcase(ntpath.normpath(expected))
        )
    except (TypeError, ValueError):
        return False


def probe_windows_job_cleanup() -> WindowsJobProbeResult:
    """真实测试正常退出/超时后的 Job 后代回收，绝不计作文件或网络隔离。"""
    if sys.platform != "win32":
        return WindowsJobProbeResult(False, False, {}, "当前平台不适用")
    checks = {"normal_exit": False, "timeout": False}
    try:
        with tempfile.TemporaryDirectory(prefix="icode-windows-job-probe-") as raw:
            root = Path(raw).resolve()
            for mode, child_delay, timeout in (
                ("normal_exit", 1.5, 5), ("timeout", 3.0, 1),
            ):
                started = root / f"{mode}-started"
                residue = root / f"{mode}-residue"
                child_code = (
                    "import time\nfrom pathlib import Path\n"
                    f"Path({str(started)!r}).write_text('ready')\n"
                    f"time.sleep({child_delay!r})\n"
                    f"Path({str(residue)!r}).write_text('late')\n"
                )
                parent_code = (
                    "import subprocess, sys, time\nfrom pathlib import Path\n"
                    f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                    "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
                    f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                    "    time.sleep(0.01)\n"
                    "else: raise RuntimeError('child did not start')\n"
                    + ("time.sleep(8)\n" if mode == "timeout" else "")
                )
                result = run_windows_job(
                    [sys.executable, "-c", parent_code],
                    cwd=root, timeout_seconds=timeout,
                )
                if started.is_file():
                    time.sleep(child_delay + 0.2)
                checks[mode] = (
                    result.executed and result.cleanup_ok
                    and started.is_file() and not residue.exists()
                    and (result.error == "timeout" if mode == "timeout"
                         else result.error is None and result.exit_code == 0)
                )
    except Exception:  # noqa: BLE001 - 自检异常只可降为未通过
        return WindowsJobProbeResult(True, False, checks, "Windows Job 局部探测异常")
    failed = [name for name, passed in checks.items() if not passed]
    return WindowsJobProbeResult(
        True, not failed, checks,
        "Job 后代清理局部探测通过；不含文件/网络隔离" if not failed
        else "Job 后代清理未通过：" + ", ".join(failed),
    )


def run_windows_job(
    argv: Sequence[str], *, cwd: str | Path, timeout_seconds: int,
    process_limit: int = 8,
    _appcontainer_sid: int | None = None,
    _diagnostic_read_handle: int | None = None,
    _diagnostic_null_application_name: bool = False,
    _appcontainer_localappdata: str | None = None,
    _diagnostic_private_network_capability: bool = False,
) -> WindowsJobResult:
    """挂起启动、入独立 Job、再恢复；所有失败都禁止当成沙箱成功。

    这是清理能力的局部试验，不接自动工单。主进程退出或超时后都终止
    Job 中剩余后代；最后一个 Job 句柄因宿主崩溃关闭时也由内核回收。
    仅开发期 AppContainer POC 可选择继承一个降权后的普通只读文件句柄；
    常规调用仍不继承任何宿主凭据或文件句柄。
    私有 app-name 诊断只允许 AppContainer 启动固定的无参数 whoami 探针；容器 profile
    路径只由上层 AppContainer 包装器通过 Win32 API 获取并传入。
    私有网络 capability 只允许固定双栈 loopback 正控；该权限实际覆盖私有网络，
    不得传入工单命令，也不计入零 capability 隔离验收。
    """
    if not isinstance(_diagnostic_private_network_capability, bool):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", False,
            "私有网络 capability 诊断标记无效",
        )
    if _diagnostic_private_network_capability and (
        _appcontainer_sid is None
        or _diagnostic_read_handle is not None
        or _diagnostic_null_application_name
        or not _is_fixed_private_network_capability_probe(argv, cwd)
    ):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", False,
            "私有网络 capability 仅允许固定的 GitHub Windows 双栈回环探针",
        )
    if _diagnostic_read_handle is not None:
        if (
            _appcontainer_sid is None
            or _diagnostic_null_application_name
            or not _is_fixed_read_handle_probe(argv, cwd, _diagnostic_read_handle)
        ):
            return WindowsJobResult(
                False, None, "invalid_diagnostic_probe", False,
                "只读句柄仅允许受控 runner 上工作区内的固定 AppContainer 探针",
            )
    elif any(
        isinstance(argument, str) and _READ_HANDLE_PLACEHOLDER in argument
        for argument in argv
    ):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", False,
            "命令包含未绑定的只读句柄占位符",
        )
    if sys.platform != "win32":
        return WindowsJobResult(False, None, "unsupported_platform", False, "仅适用于 Windows")
    if not argv or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file():
        return WindowsJobResult(False, None, "invalid_command", False, "命令入口必须是存在的绝对路径")
    if not isinstance(_diagnostic_null_application_name, bool):
        return WindowsJobResult(False, None, "invalid_diagnostic_probe", False, "诊断启动模式无效")
    if _appcontainer_localappdata is not None and (
        not isinstance(_appcontainer_localappdata, str)
        or "\0" in _appcontainer_localappdata
        or not ntpath.isabs(_appcontainer_localappdata)
        or _appcontainer_sid is None
    ):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", False,
            "LOCALAPPDATA 只允许与 AppContainer SID 一起使用且必须是绝对路径",
        )
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    if _diagnostic_null_application_name and (
        _appcontainer_sid is None
        or not _is_fixed_system_whoami_probe(argv, system_root)
    ):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", False,
            "NULL lpApplicationName 仅允许 AppContainer 固定 whoami 探针",
        )
    if not 1 <= timeout_seconds <= 86400 or not 1 <= process_limit <= 1024:
        return WindowsJobResult(False, None, "invalid_limit", False, "超时或进程上限无效")
    root = Path(cwd).resolve()
    if not root.is_dir():
        return WindowsJobResult(False, None, "invalid_workspace", False, "工作目录不存在")

    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class BASIC_LIMITS(ctypes.Structure):
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

    class EXTENDED_LIMITS(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMITS),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class BASIC_ACCOUNTING(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
            ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class STARTUPINFOEX(ctypes.Structure):
        _fields_ = [
            ("StartupInfo", STARTUPINFO),
            ("lpAttributeList", ctypes.c_void_p),
        ]

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    class SECURITY_CAPABILITIES(ctypes.Structure):
        _fields_ = [
            ("AppContainerSid", ctypes.c_void_p),
            ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
            ("CapabilityCount", wintypes.DWORD),
            ("Reserved", wintypes.DWORD),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD),
        ]

    class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", wintypes.DWORD), ("ReparseTag", wintypes.DWORD),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.c_void_p, ctypes.POINTER(PROCESS_INFORMATION),
    ]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel.DeleteProcThreadAttributeList.restype = None
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    kernel.GetFileType.restype = wintypes.DWORD
    kernel.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.DuplicateHandle.argtypes = [
        wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel.DuplicateHandle.restype = wintypes.BOOL

    duplicate_read_handle = wintypes.HANDLE()
    private_network_capability_sid = ctypes.c_void_p()
    private_network_capability_attributes = None
    bound_argv = list(argv)
    if _diagnostic_read_handle is not None:
        source_handle = wintypes.HANDLE(_diagnostic_read_handle)
        standard_info = _FILE_STANDARD_INFO()
        attribute_info = FILE_ATTRIBUTE_TAG_INFO()
        valid_source = (
            kernel.GetFileType(source_handle) == 1
            and bool(kernel.GetFileInformationByHandleEx(
                source_handle, 1, ctypes.byref(standard_info),
                ctypes.sizeof(standard_info),
            ))
            and bool(kernel.GetFileInformationByHandleEx(
                source_handle, 9, ctypes.byref(attribute_info),
                ctypes.sizeof(attribute_info),
            ))
            and not standard_info.Directory
            and standard_info.NumberOfLinks == 1
            and not (attribute_info.FileAttributes & 0x400)
        )
        if not valid_source:
            return WindowsJobResult(
                False, None, "invalid_diagnostic_probe", False,
                "只读句柄必须指向普通、非重解析、单链接磁盘文件",
            )
        current_process = kernel.GetCurrentProcess()
        if not kernel.DuplicateHandle(
            current_process, source_handle, current_process,
            ctypes.byref(duplicate_read_handle), 0x00120089, True, 0,
        ):
            return WindowsJobResult(
                False, None, "invalid_diagnostic_probe", False,
                "只读文件句柄复制失败",
            )
        try:
            bound_argv = _bind_read_handle_placeholder(
                argv, int(duplicate_read_handle.value),
            )
        except (TypeError, ValueError):
            kernel.CloseHandle(duplicate_read_handle)
            return WindowsJobResult(
                False, None, "invalid_diagnostic_probe", False,
                "只读句柄命令占位符不符合诊断合同",
            )

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        if duplicate_read_handle.value:
            kernel.CloseHandle(duplicate_read_handle)
        return WindowsJobResult(False, None, "job_creation_failed", False, str(ctypes.get_last_error()))
    process = PROCESS_INFORMATION()
    created = False
    assigned = False
    exit_code: int | None = None
    error: str | None = None
    detail = ""
    diagnostics: list[str] = []
    cleanup_ok = False
    capability_sid_cleanup_ok = True
    attribute_storage: ctypes.Array | None = None
    attribute_list: ctypes.c_void_p | None = None
    attributes_initialized = False
    try:
        limits = EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x0008  # KILL_ON_JOB_CLOSE | ACTIVE_PROCESS
        limits.BasicLimitInformation.ActiveProcessLimit = process_limit
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")

        # 默认不继承宿主句柄；诊断例外仅传一个降权为只读的普通文件句柄。
        environment_block = _build_windows_environment_block(argv[0], root, system_root)
        if _appcontainer_localappdata is not None:
            environment_block = _append_windows_environment_value(
                environment_block, "LOCALAPPDATA", _appcontainer_localappdata,
            )
        env_block = ctypes.create_unicode_buffer(environment_block)
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(bound_argv))
        if _appcontainer_sid is None:
            startup = STARTUPINFO()
            startup.cb = ctypes.sizeof(startup)
            startup_ptr = ctypes.cast(ctypes.byref(startup), ctypes.c_void_p)
            creation_flags = 0x00000004 | 0x00000400  # CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
        else:
            attribute_count = 2 if duplicate_read_handle.value else 1
            if _diagnostic_private_network_capability:
                advapi = ctypes.WinDLL("advapi32", use_last_error=True)
                advapi.ConvertStringSidToSidW.argtypes = [
                    wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                ]
                advapi.ConvertStringSidToSidW.restype = wintypes.BOOL
                kernel.LocalFree.argtypes = [ctypes.c_void_p]
                kernel.LocalFree.restype = ctypes.c_void_p
                if not advapi.ConvertStringSidToSidW(
                    _PRIVATE_NETWORK_CAPABILITY_SID,
                    ctypes.byref(private_network_capability_sid),
                ) or not private_network_capability_sid.value:
                    raise OSError(
                        ctypes.get_last_error(), "ConvertStringSidToSidW(capability)",
                    )
                private_network_capability_attributes = (SID_AND_ATTRIBUTES * 1)(
                    SID_AND_ATTRIBUTES(
                        private_network_capability_sid, _SE_GROUP_ENABLED,
                    ),
                )
            attribute_size = ctypes.c_size_t()
            ctypes.set_last_error(0)
            size_query_ok = bool(kernel.InitializeProcThreadAttributeList(
                None, attribute_count, 0, ctypes.byref(attribute_size),
            ))
            size_error = 0 if size_query_ok else ctypes.get_last_error()
            size_query_expected = (
                not size_query_ok and size_error == 122 and attribute_size.value > 0
            )
            diagnostics.append(
                f"attr_size_query_expected={size_query_expected} "
                f"attr_size_query_ok={size_query_ok} attr_size_query_error={size_error} "
                f"attr_bytes={attribute_size.value}"
            )
            if not size_query_expected:
                raise OSError(size_error, "InitializeProcThreadAttributeList(size)")
            attribute_storage, attribute_list = _allocate_attribute_list_buffer(
                attribute_size.value,
            )
            attr_init_ok = bool(kernel.InitializeProcThreadAttributeList(
                attribute_list, attribute_count, 0, ctypes.byref(attribute_size),
            ))
            attr_init_error = 0 if attr_init_ok else ctypes.get_last_error()
            diagnostics.append(
                f"attr_init_ok={attr_init_ok} attr_init_error={attr_init_error}"
            )
            if not attr_init_ok:
                raise OSError(attr_init_error, "InitializeProcThreadAttributeList")
            attributes_initialized = True
            if private_network_capability_attributes is None:
                security = SECURITY_CAPABILITIES(
                    ctypes.c_void_p(_appcontainer_sid), None, 0, 0,
                )
            else:
                security = SECURITY_CAPABILITIES(
                    ctypes.c_void_p(_appcontainer_sid),
                    ctypes.cast(private_network_capability_attributes,
                                ctypes.POINTER(SID_AND_ATTRIBUTES)),
                    1, 0,
                )
            diagnostics.append(
                "security_attribute=0x00020009 "
                f"payload_bytes={ctypes.sizeof(security)} "
                f"sid_present={bool(security.AppContainerSid)} "
                f"capability_count={security.CapabilityCount} reserved={security.Reserved} "
                f"private_network_control={_diagnostic_private_network_capability}"
            )
            # Only the isolated diagnostic branch may supply one private-network SID.
            attr_update_ok = bool(kernel.UpdateProcThreadAttribute(
                attribute_list, 0, 0x00020009, ctypes.byref(security),
                ctypes.sizeof(security), None, None,
            ))
            attr_update_error = 0 if attr_update_ok else ctypes.get_last_error()
            diagnostics.append(
                f"attr_update_ok={attr_update_ok} attr_update_error={attr_update_error}"
            )
            if not attr_update_ok:
                raise OSError(attr_update_error, "UpdateProcThreadAttribute(security)")
            if duplicate_read_handle.value:
                inherited_handles = (wintypes.HANDLE * 1)(duplicate_read_handle.value)
                handle_list_ok = bool(kernel.UpdateProcThreadAttribute(
                    attribute_list, 0, 0x00020002,
                    ctypes.cast(inherited_handles, ctypes.c_void_p),
                    ctypes.sizeof(inherited_handles), None, None,
                ))
                handle_list_error = 0 if handle_list_ok else ctypes.get_last_error()
                diagnostics.append(
                    f"read_handle_list_ok={handle_list_ok} "
                    f"read_handle_list_error={handle_list_error} count=1 access=read_only"
                )
                if not handle_list_ok:
                    raise OSError(handle_list_error, "UpdateProcThreadAttribute(handle_list)")
            startup_ex = STARTUPINFOEX()
            startup_ex.StartupInfo.cb = ctypes.sizeof(startup_ex)
            startup_ex.lpAttributeList = attribute_list
            startup_ptr = ctypes.cast(ctypes.byref(startup_ex), ctypes.c_void_p)
            creation_flags = (
                0x00000004 | 0x00000400 | 0x00080000
            )  # SUSPENDED | UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT
            diagnostics.append(
                f"flags=0x{creation_flags:08x} unicode_environment=1 "
                "extended_startup_info=1 suspended=1"
            )
            if _diagnostic_null_application_name:
                diagnostics.append("application_name_mode=null_cmdline_fixed_whoami")
        if not kernel.CreateProcessW(
            None if _diagnostic_null_application_name else str(argv[0]),
            command, None, None, bool(duplicate_read_handle.value), creation_flags,
            env_block, str(root), startup_ptr, ctypes.byref(process),
        ):
            raise OSError(ctypes.get_last_error(), "CreateProcessW")
        created = True
        if not kernel.AssignProcessToJobObject(job, process.hProcess):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
        assigned = True
        resume_count = kernel.ResumeThread(process.hThread)
        if resume_count in (0, 0xFFFFFFFF):
            raise OSError(ctypes.get_last_error(), "ResumeThread")
        wait = kernel.WaitForSingleObject(process.hProcess, timeout_seconds * 1000)
        if wait == 0x00000102:
            error = "timeout"
        elif wait != 0:
            raise OSError(ctypes.get_last_error(), "WaitForSingleObject")
        else:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(code)):
                raise OSError(ctypes.get_last_error(), "GetExitCodeProcess")
            exit_code = int(code.value)
    except OSError as exc:
        error = "native_api_failed"
        system_detail = ctypes.FormatError(exc.errno).strip() if exc.errno else ""
        detail = f"{exc.strerror or type(exc).__name__}: {system_detail} (err={exc.errno})"
    finally:
        if duplicate_read_handle.value:
            kernel.CloseHandle(duplicate_read_handle)
        if private_network_capability_sid.value:
            if kernel.LocalFree(private_network_capability_sid):
                capability_sid_cleanup_ok = False
                error = "cleanup_failed"
                detail = "LocalFree(private network capability SID) failed"
        if attributes_initialized and attribute_list is not None:
            kernel.DeleteProcThreadAttributeList(attribute_list)
        if assigned:
            if not kernel.TerminateJobObject(job, 1):
                error = "cleanup_failed"
                detail = f"TerminateJobObject err={ctypes.get_last_error()}"
            else:
                until = time.monotonic() + 5
                while time.monotonic() < until:
                    counts = BASIC_ACCOUNTING()
                    if not kernel.QueryInformationJobObject(
                        job, 1, ctypes.byref(counts), ctypes.sizeof(counts), None,
                    ):
                        detail = f"QueryInformationJobObject err={ctypes.get_last_error()}"
                        break
                    if counts.ActiveProcesses == 0:
                        cleanup_ok = True
                        break
                    time.sleep(0.02)
                if not cleanup_ok:
                    error = "cleanup_failed"
        elif created:
            kernel.TerminateProcess(process.hProcess, 1)
        else:
            # No child was created, so there is no process or descendant to reap.
            # Preserve the original launch error instead of relabeling it as cleanup.
            cleanup_ok = True
        cleanup_ok = cleanup_ok and capability_sid_cleanup_ok
        if created:
            kernel.CloseHandle(process.hThread)
            kernel.CloseHandle(process.hProcess)
        kernel.CloseHandle(job)
    if diagnostics:
        detail = "; ".join(part for part in (detail, *diagnostics) if part)
    return WindowsJobResult(created, exit_code, error, cleanup_ok, detail)
