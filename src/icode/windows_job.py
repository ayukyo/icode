"""R2.3 开发期 Windows 工单级进程回收；尚不提供文件/网络隔离。"""

from __future__ import annotations

import ctypes
import ntpath
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


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


def _is_fixed_workspace_revocation_probe(
    argv: Sequence[str], cwd: str | os.PathLike[str],
    system_root: str | os.PathLike[str],
) -> bool:
    """Permit only the internal cmd.exe marker write used to verify ACL revocation."""
    if len(argv) != 4 or argv[1:3] != ["/d", "/c"]:
        return False
    try:
        executable = os.fspath(argv[0])
        workspace = os.fspath(cwd)
        root = os.fspath(system_root)
        if not all(isinstance(value, str) for value in (executable, workspace, root)):
            return False
        expected_executable = ntpath.join(root, "System32", "cmd.exe")
        if ntpath.normcase(ntpath.normpath(executable)) != ntpath.normcase(
            ntpath.normpath(expected_executable),
        ):
            return False
        command = argv[3]
        if not isinstance(command, str):
            return False
        prefix = 'echo denied> "'
        if not command.startswith(prefix) or not command.endswith('"'):
            return False
        marker = ntpath.normpath(command[len(prefix):-1])
        if ntpath.normcase(ntpath.dirname(marker)) != ntpath.normcase(
            ntpath.normpath(workspace),
        ):
            return False
        marker_name = ntpath.basename(marker)
        marker_prefix = ".icode-appcontainer-revocation-"
        suffix = marker_name.removeprefix(marker_prefix)
        return (
            marker_name.startswith(marker_prefix) and len(suffix) == 32
            and all(character in "0123456789abcdef" for character in suffix.casefold())
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
    _diagnostic_null_application_name: bool = False,
    _diagnostic_localappdata: str | None = None,
) -> WindowsJobResult:
    """挂起启动、入独立 Job、再恢复；所有失败都禁止当成沙箱成功。

    这是清理能力的局部试验，不接自动工单。主进程退出或超时后都终止
    Job 中剩余后代；最后一个 Job 句柄因宿主崩溃关闭时也由内核回收。
    私有诊断模式只允许 AppContainer 启动固定的无参数 whoami 探针。
    """
    if sys.platform != "win32":
        return WindowsJobResult(False, None, "unsupported_platform", False, "仅适用于 Windows")
    if not argv or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file():
        return WindowsJobResult(False, None, "invalid_command", False, "命令入口必须是存在的绝对路径")
    if not isinstance(_diagnostic_null_application_name, bool):
        return WindowsJobResult(False, None, "invalid_diagnostic_probe", False, "诊断启动模式无效")
    if _diagnostic_localappdata is not None and (
        not isinstance(_diagnostic_localappdata, str)
        or "\0" in _diagnostic_localappdata
        or not ntpath.isabs(_diagnostic_localappdata)
        or _appcontainer_sid is None
        or not (
            _is_fixed_system_whoami_probe(
                argv, os.environ.get("SystemRoot", r"C:\Windows"),
            )
            or _is_fixed_workspace_revocation_probe(
                argv, cwd, os.environ.get("SystemRoot", r"C:\Windows"),
            )
        )
        or _diagnostic_null_application_name
    ):
        return WindowsJobResult(
            False, None, "invalid_diagnostic_probe", False,
            "LOCALAPPDATA 差分仅允许固定 whoami 与内部 ACL 撤权探针",
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

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return WindowsJobResult(False, None, "job_creation_failed", False, str(ctypes.get_last_error()))
    process = PROCESS_INFORMATION()
    created = False
    assigned = False
    exit_code: int | None = None
    error: str | None = None
    detail = ""
    diagnostics: list[str] = []
    cleanup_ok = False
    attribute_storage: ctypes.Array | None = None
    attribute_list: ctypes.c_void_p | None = None
    attributes_initialized = False
    try:
        limits = EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x0008  # KILL_ON_JOB_CLOSE | ACTIVE_PROCESS
        limits.BasicLimitInformation.ActiveProcessLimit = process_limit
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")

        # 不继承宿主凭据或文件句柄；Job 自身也不会被子进程持有。
        environment_block = _build_windows_environment_block(argv[0], root, system_root)
        if _diagnostic_localappdata is not None:
            environment_block = _append_windows_environment_value(
                environment_block, "LOCALAPPDATA", _diagnostic_localappdata,
            )
        env_block = ctypes.create_unicode_buffer(environment_block)
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(argv)))
        if _appcontainer_sid is None:
            startup = STARTUPINFO()
            startup.cb = ctypes.sizeof(startup)
            startup_ptr = ctypes.cast(ctypes.byref(startup), ctypes.c_void_p)
            creation_flags = 0x00000004 | 0x00000400  # CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
        else:
            attribute_size = ctypes.c_size_t()
            ctypes.set_last_error(0)
            size_query_ok = bool(kernel.InitializeProcThreadAttributeList(
                None, 1, 0, ctypes.byref(attribute_size),
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
                attribute_list, 1, 0, ctypes.byref(attribute_size),
            ))
            attr_init_error = 0 if attr_init_ok else ctypes.get_last_error()
            diagnostics.append(
                f"attr_init_ok={attr_init_ok} attr_init_error={attr_init_error}"
            )
            if not attr_init_ok:
                raise OSError(attr_init_error, "InitializeProcThreadAttributeList")
            attributes_initialized = True
            security = SECURITY_CAPABILITIES(
                ctypes.c_void_p(_appcontainer_sid), None, 0, 0,
            )
            diagnostics.append(
                "security_attribute=0x00020009 "
                f"payload_bytes={ctypes.sizeof(security)} "
                f"sid_present={bool(security.AppContainerSid)} "
                f"capability_count={security.CapabilityCount} reserved={security.Reserved}"
            )
            # PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES; no network capabilities
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
            command, None, None, False, creation_flags,
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
        if created:
            kernel.CloseHandle(process.hThread)
            kernel.CloseHandle(process.hProcess)
        kernel.CloseHandle(job)
    if diagnostics:
        detail = "; ".join(part for part in (detail, *diagnostics) if part)
    return WindowsJobResult(created, exit_code, error, cleanup_ok, detail)
