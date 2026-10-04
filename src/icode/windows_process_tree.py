"""Bounded Windows Job Object lifecycle for independent verification."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes


CREATE_SUSPENDED = 0x00000004
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_THREAD_SUSPEND_RESUME = 0x00000002
_THREAD_QUERY_LIMITED_INFORMATION = 0x00000800
_THREAD_SNAPSHOT = 0x00000004
_WAIT_TIMEOUT = 0x00000102
_ERROR_NO_MORE_FILES = 18
_THREAD_DISCOVERY_TIMEOUT_SECONDS = 1.0
_THREAD_DISCOVERY_POLL_INTERVAL_SECONDS = 0.01


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BASIC_LIMITS(ctypes.Structure):
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


class _EXTENDED_LIMITS(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_LIMITS),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _BASIC_ACCOUNTING(ctypes.Structure):
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


class _THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", ctypes.c_long),
        ("tpDeltaPri", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
    ]


class WindowsProcessTree:
    """Assign a suspended process to a kill-on-close Job before it can run."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Windows Job Object is only available on Windows")

        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_api()
        self._job = self._kernel.CreateJobObjectW(None, None)
        if not self._job:
            self._raise_last_error("CreateJobObjectW")
        self._assigned = False
        limits = _EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._kernel.SetInformationJobObject(
            self._job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, "SetInformationJobObject failed")

    @property
    def assigned(self) -> bool:
        return self._assigned

    def _configure_api(self) -> None:
        kernel = self._kernel
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.GetProcessId.argtypes = [wintypes.HANDLE]
        kernel.GetProcessId.restype = wintypes.DWORD
        kernel.GetProcessIdOfThread.argtypes = [wintypes.HANDLE]
        kernel.GetProcessIdOfThread.restype = wintypes.DWORD
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_THREADENTRY32)]
        kernel.Thread32First.restype = wintypes.BOOL
        kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_THREADENTRY32)]
        kernel.Thread32Next.restype = wintypes.BOOL
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL

    @staticmethod
    def _raise_last_error(api: str) -> None:
        error = ctypes.get_last_error()
        raise OSError(error, f"{api} failed")

    def assign_and_resume(self, pid: int, process_handle: int) -> None:
        """Bind the only suspended primary thread's process, then resume it."""
        if (
            self._job is None or self._assigned
            or type(pid) is not int or pid < 1
            or type(process_handle) is not int or process_handle < 1
        ):
            raise RuntimeError("Windows verification Job is not assignable")

        # Use Popen's original process handle: reopening by PID could bind a
        # recycled PID if an external actor terminated the suspended child.
        process = wintypes.HANDLE(process_handle)
        if self._kernel.GetProcessId(process) != pid:
            raise OSError(0, "Popen process handle PID did not match the verifier")
        if self._kernel.WaitForSingleObject(process, 0) != _WAIT_TIMEOUT:
            raise OSError(0, "suspended verifier process exited before Job assignment")
        if not self._kernel.AssignProcessToJobObject(self._job, process):
            self._raise_last_error("AssignProcessToJobObject")
        self._assigned = True

        thread_id = self._suspended_primary_thread_id(pid, process)
        thread = self._kernel.OpenThread(
            _THREAD_SUSPEND_RESUME | _THREAD_QUERY_LIMITED_INFORMATION,
            False, thread_id,
        )
        if not thread:
            self._raise_last_error("OpenThread")
        try:
            if self._kernel.GetProcessIdOfThread(thread) != pid:
                raise OSError(0, "primary thread owner did not match the verifier PID")
            if self._kernel.WaitForSingleObject(process, 0) != _WAIT_TIMEOUT:
                raise OSError(0, "suspended verifier exited before its primary thread resumed")
            previous_suspend_count = self._kernel.ResumeThread(thread)
            if previous_suspend_count == 0xFFFFFFFF:
                self._raise_last_error("ResumeThread")
            if previous_suspend_count != 1:
                raise OSError(
                    0, "suspended verifier primary thread did not have suspend count 1",
                )
        finally:
            if not self._kernel.CloseHandle(thread):
                self._raise_last_error("CloseHandle(thread)")

    def _suspended_primary_thread_id(
        self, pid: int, process: wintypes.HANDLE,
    ) -> int:
        deadline = time.monotonic() + _THREAD_DISCOVERY_TIMEOUT_SECONDS
        while True:
            if self._kernel.WaitForSingleObject(process, 0) != _WAIT_TIMEOUT:
                raise OSError(0, "suspended verifier exited before its primary thread was found")
            snapshot = self._kernel.CreateToolhelp32Snapshot(_THREAD_SNAPSHOT, 0)
            invalid_handle = ctypes.c_void_p(-1).value
            if not snapshot or snapshot == invalid_handle:
                self._raise_last_error("CreateToolhelp32Snapshot")
            thread_ids: list[int] = []
            try:
                entry = _THREADENTRY32()
                entry.dwSize = ctypes.sizeof(entry)
                ctypes.set_last_error(0)
                found = bool(self._kernel.Thread32First(snapshot, ctypes.byref(entry)))
                if not found:
                    error = ctypes.get_last_error()
                    if error != _ERROR_NO_MORE_FILES:
                        raise OSError(error, "Thread32First failed")
                while found:
                    if entry.th32OwnerProcessID == pid:
                        thread_ids.append(int(entry.th32ThreadID))
                    ctypes.set_last_error(0)
                    found = bool(self._kernel.Thread32Next(snapshot, ctypes.byref(entry)))
                    if not found:
                        error = ctypes.get_last_error()
                        if error not in (0, _ERROR_NO_MORE_FILES):
                            raise OSError(error, "Thread32Next failed")
            finally:
                if not self._kernel.CloseHandle(snapshot):
                    self._raise_last_error("CloseHandle(thread snapshot)")

            if len(thread_ids) == 1:
                return thread_ids[0]
            if len(thread_ids) > 1:
                raise OSError(0, "suspended verifier process has unexpected extra threads")
            if time.monotonic() >= deadline:
                raise OSError(0, "could not locate suspended verifier primary thread")
            time.sleep(_THREAD_DISCOVERY_POLL_INTERVAL_SECONDS)

    def active_process_count(self) -> int:
        if self._job is None:
            raise RuntimeError("Windows verification Job is closed")
        accounting = _BASIC_ACCOUNTING()
        if not self._kernel.QueryInformationJobObject(
            self._job, _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting), ctypes.sizeof(accounting), None,
        ):
            self._raise_last_error("QueryInformationJobObject")
        return int(accounting.ActiveProcesses)

    def wait_until_empty(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            if self.active_process_count() == 0:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(min(0.01, deadline - time.monotonic()))

    def terminate_and_wait(self, timeout_seconds: float) -> bool:
        if self._job is None:
            return False
        try:
            if self.active_process_count() == 0:
                return True
            if not self._kernel.TerminateJobObject(self._job, 1):
                return self.wait_until_empty(timeout_seconds)
            return self.wait_until_empty(timeout_seconds)
        except OSError:
            return False

    def close(self) -> None:
        job = self._job
        if job and not self._kernel.CloseHandle(job):
            self._raise_last_error("CloseHandle(job)")
        self._job = None
