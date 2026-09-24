"""R2.3 开发期 Windows 工单级进程回收；尚不提供文件/网络隔离。"""

from __future__ import annotations

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
) -> WindowsJobResult:
    """挂起启动、入独立 Job、再恢复；所有失败都禁止当成沙箱成功。

    这是清理能力的局部试验，不接自动工单。主进程退出或超时后都终止
    Job 中剩余后代；最后一个 Job 句柄因宿主崩溃关闭时也由内核回收。
    """
    if sys.platform != "win32":
        return WindowsJobResult(False, None, "unsupported_platform", False, "仅适用于 Windows")
    if not argv or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file():
        return WindowsJobResult(False, None, "invalid_command", False, "命令入口必须是存在的绝对路径")
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
        ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION),
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

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return WindowsJobResult(False, None, "job_creation_failed", False, str(ctypes.get_last_error()))
    process = PROCESS_INFORMATION()
    created = False
    assigned = False
    exit_code: int | None = None
    error: str | None = None
    detail = ""
    cleanup_ok = False
    try:
        limits = EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x0008  # KILL_ON_JOB_CLOSE | ACTIVE_PROCESS
        limits.BasicLimitInformation.ActiveProcessLimit = process_limit
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")

        # 不继承宿主凭据或文件句柄；Job 自身也不会被子进程持有。
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        environment = {
            "SystemRoot": system_root,
            "WINDIR": system_root,
            "PATH": os.pathsep.join((str(Path(argv[0]).parent), str(Path(system_root) / "System32"))),
            "TEMP": str(root), "TMP": str(root), "USERPROFILE": str(root),
            "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1",
        }
        env_block = ctypes.create_unicode_buffer(
            "\0".join(f"{key}={value}" for key, value in sorted(environment.items())) + "\0\0"
        )
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(argv)))
        startup = STARTUPINFO()
        startup.cb = ctypes.sizeof(startup)
        if not kernel.CreateProcessW(
            str(argv[0]), command, None, None, False, 0x00000004 | 0x00000400,
            env_block, str(root), ctypes.byref(startup), ctypes.byref(process),
        ):
            raise OSError(ctypes.get_last_error(), "CreateProcessW")
        created = True
        if not kernel.AssignProcessToJobObject(job, process.hProcess):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
        assigned = True
        if kernel.ResumeThread(process.hThread) == 0xFFFFFFFF:
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
        detail = f"{exc.strerror or type(exc).__name__} (err={exc.errno})"
    finally:
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
        if created:
            kernel.CloseHandle(process.hThread)
            kernel.CloseHandle(process.hProcess)
        kernel.CloseHandle(job)
    return WindowsJobResult(created, exit_code, error, cleanup_ok, detail)
