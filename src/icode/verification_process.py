"""验证执行的平台进程管理（从 runner.py 下沉）。

这个模块只负责**如何把一个进程跑完并把输出安全取回来**：
有界输出读取、超时排空、进程组/作业树回收、平台差异分支。

它不负责：选哪个解释器、跑什么测试、如何解释退出码 —— 那是 `runner.run_unittest`
的策略职责，仍留在 `runner.py`。

依赖边界（SPEC v1.1 §5.2）：
  - 只依赖标准库 + `windows_process_tree`（单向）；
  - **不 import runner**（任何形式，含函数内延迟导入）；
  - `Sandbox` 仅用于 `if TYPE_CHECKING:` 下的类型标注。

公开名字由 `runner` 侧重导出：`from icode.runner import
_run_unittest_with_bounded_output` 与 `icode.runner._run_unittest_with_bounded_output`
必须是**同一个对象**（`is` 断言），否则既有 patch 目标会静默失效。
"""
from __future__ import annotations

import errno
import os
import re
import select
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:  # pragma: no cover - 仅供静态检查，运行时不导入
    from .isolation import Sandbox


_VERIFICATION_OUTPUT_READ_CHUNK_BYTES = 64 * 1024

_VERIFICATION_OUTPUT_DRAIN_TIMEOUT_SECONDS = 2.0

_VERIFICATION_PROCESS_CLEANUP_TIMEOUT_SECONDS = 2.0

_DARWIN_PROCESS_GROUP_AUDIT_LIMIT_BYTES = 64 * 1024

_DARWIN_PROCESS_GROUP_AUDIT_TIMEOUT_SECONDS = 1.0



class VerificationOutputError(RuntimeError):
    """The verifier did not produce a complete, safely captured output stream."""

    def __init__(
        self, message: str, *, return_code: int | None = None,
    ):
        self.return_code = return_code
        super().__init__(message)

class VerificationOutputLimitError(VerificationOutputError):
    """The independent verification output exceeded its evidence capture budget."""

    def __init__(self, limit_bytes: int, *, return_code: int | None = None):
        self.limit_bytes = limit_bytes
        super().__init__(
            f"独立验证输出超过安全上限（{limit_bytes:,} 字节），拒绝生成完整验证证据",
            return_code=return_code,
        )

class VerificationOutputCaptureError(VerificationOutputError):
    """The verifier exited but its output pipes could not be fully closed/drained."""

def _run_unittest_with_bounded_output(
    argv: list[str], *, workspace: Path, timeout: int, output_limit_bytes: int,
    environment: dict[str, str] | None = None,
) -> tuple[int, bytes, bytes]:
    """Drain both child pipes while retaining at most the combined byte budget.

    Once the budget is exceeded, continue draining so neither pipe can block the
    test process, but the caller must reject the result instead of issuing a
    receipt over partial output.
    """
    if type(output_limit_bytes) is not int or output_limit_bytes < 1:
        raise ValueError("output_limit_bytes must be a positive integer")

    launch_options = {"environment": environment} if environment is not None else {}
    if os.name == "posix":
        return _run_posix_bounded_output(
            argv, workspace=workspace, timeout=timeout,
            output_limit_bytes=output_limit_bytes,
            **launch_options,
        )
    return _run_threaded_bounded_output(
        argv, workspace=workspace, timeout=timeout,
        output_limit_bytes=output_limit_bytes,
        **launch_options,
    )

def _retain_verification_output(
    chunk: bytes, target: bytearray, *, output_limit_bytes: int,
    captured_bytes: int,
) -> tuple[int, bool]:
    available = max(0, output_limit_bytes - captured_bytes)
    keep = min(available, len(chunk))
    if keep:
        target.extend(chunk[:keep])
    return captured_bytes + keep, keep != len(chunk)

def _darwin_process_group_has_live_members(pgid: int) -> bool | None:
    """Boundedly inspect a Darwin process group when killpg reports EPERM.

    XNU leaves an exited child in its process group until it is reaped, while
    killpg's signal walk skips zombies.  On that exact path EPERM can therefore
    mean either "only zombies remain" or "a live member could not be signalled".
    Treat it as clean only after `/bin/ps` confirms that no non-zombie member is
    present.  Any inspection error, timeout, or output overflow is inconclusive.
    """
    try:
        env = os.environ.copy()
        # macOS legacy command mode ignores `ps -g`'s PGID argument; pin the
        # selector semantics for this read-only audit without changing callers.
        env["COMMAND_MODE"] = "unix2003"
        # Do not add `-A`: macOS ps unions multiple selectors, so `-A -g PGID`
        # would expand this audit to all processes. `-x` includes no-tty members.
        proc = subprocess.Popen(
            ["/bin/ps", "-g", str(pgid), "-x", "-o", "stat="],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=False,
            bufsize=0,
            shell=False,
            start_new_session=True,
        )
    except (OSError, ValueError):
        return None

    output = bytearray()
    selector: selectors.BaseSelector | None = None
    deadline = time.monotonic() + _DARWIN_PROCESS_GROUP_AUDIT_TIMEOUT_SECONDS
    try:
        if proc.stdout is None:
            return None
        selector = selectors.DefaultSelector()
        os.set_blocking(proc.stdout.fileno(), False)
        selector.register(proc.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            for key, _ in selector.select(min(remaining, 0.05)):
                try:
                    chunk = os.read(key.fd, _VERIFICATION_OUTPUT_READ_CHUNK_BYTES)
                except BlockingIOError:
                    continue
                except OSError:
                    return None
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                if len(output) + len(chunk) > _DARWIN_PROCESS_GROUP_AUDIT_LIMIT_BYTES:
                    return None
                output.extend(chunk)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            return_code = proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            return None
        if return_code != 0:
            return None
        try:
            states = output.decode("ascii").splitlines()
        except UnicodeDecodeError:
            return None
        normalized_states = [state.strip() for state in states if state.strip()]
        # The unreaped leader must still be visible as a zombie.  Requiring it
        # prevents an empty/mis-scoped ps result from being treated as proof.
        if not normalized_states or not any(
            state.startswith("Z") for state in normalized_states
        ):
            return None
        return any(not state.startswith("Z") for state in normalized_states)
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    finally:
        if selector is not None:
            try:
                selector.close()
            except OSError:
                pass
        if proc.stdout is not None and not proc.stdout.closed:
            try:
                proc.stdout.close()
            except OSError:
                pass
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            except OSError:
                pass
            try:
                proc.wait(timeout=_VERIFICATION_PROCESS_CLEANUP_TIMEOUT_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                pass

def _terminate_posix_verification_group(
    proc: subprocess.Popen[bytes], *, process_exited: bool,
) -> tuple[bool, int | None]:
    """Stop the verifier's isolated session without reaping its numeric PGID first."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        if not process_exited:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            except OSError as exc:
                return False, exc.errno
        return True, None
    except OSError as exc:
        if (
            process_exited
            and sys.platform == "darwin"
            and exc.errno == errno.EPERM
            and _darwin_process_group_has_live_members(proc.pid) is False
        ):
            return True, None
        if not process_exited:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            except OSError:
                pass
        return False, exc.errno
    return True, None

class _PosixVerificationExitMonitor:
    """Observe child exit without reaping its session leader before group cleanup."""

    def __init__(self, proc: subprocess.Popen[bytes]):
        self._kqueue = None
        self._exited = False
        waitid_supported = all(hasattr(os, name) for name in (
            "waitid", "P_PID", "WEXITED", "WNOHANG", "WNOWAIT",
        ))
        self._use_waitid = bool(
            sys.platform.startswith("linux")
            and waitid_supported
        )
        if self._use_waitid:
            return
        if all(hasattr(select, name) for name in (
            "kqueue", "kevent", "KQ_FILTER_PROC", "KQ_EV_ADD", "KQ_EV_ENABLE",
            "KQ_EV_ONESHOT", "KQ_EV_ERROR", "KQ_NOTE_EXIT",
        )):
            kqueue = select.kqueue()
            try:
                event = select.kevent(
                    proc.pid,
                    filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE | select.KQ_EV_ONESHOT,
                    fflags=select.KQ_NOTE_EXIT,
                )
                self._exited = self._kqueue_reports_exit(
                    kqueue.control([event], 1, 0), allow_missing=True,
                )
            except BaseException:
                try:
                    kqueue.close()
                except OSError:
                    pass
                raise
            self._kqueue = kqueue
            return
        if waitid_supported:
            self._use_waitid = True
            return
        raise RuntimeError("平台没有可在 reap 前观测进程退出的 POSIX API")

    def exited(self, proc: subprocess.Popen[bytes]) -> bool:
        if proc.returncode is not None:
            return True
        if self._use_waitid:
            info = os.waitid(
                os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT,
            )
            return info is not None and info.si_pid == proc.pid
        if self._kqueue is not None and not self._exited:
            self._exited = self._kqueue_reports_exit(
                self._kqueue.control(None, 1, 0),
            )
        return self._exited

    @staticmethod
    def _kqueue_reports_exit(events, *, allow_missing: bool = False) -> bool:
        error_events = [
            item for item in events
            if getattr(item, "flags", 0) & select.KQ_EV_ERROR
        ]
        if error_events:
            if allow_missing and error_events[0].data == errno.ESRCH:
                # The verifier may exit before Darwin installs its EVFILT_PROC
                # watcher. It is still our unreaped child; the caller must
                # terminate its process group before waitpid() reaps it.
                return True
            raise OSError(
                error_events[0].data,
                "kqueue could not monitor the verifier process exit",
            )
        return any(
            getattr(item, "fflags", 0) & select.KQ_NOTE_EXIT
            for item in events
        )

    def close(self) -> None:
        if self._kqueue is not None:
            self._kqueue.close()
            self._kqueue = None

def _reap_posix_verification_process(proc: subprocess.Popen[bytes]) -> int:
    if proc.returncode is not None:
        return proc.returncode

    deadline = time.monotonic() + _VERIFICATION_PROCESS_CLEANUP_TIMEOUT_SECONDS
    while True:
        try:
            pid, status = os.waitpid(proc.pid, os.WNOHANG)
        except ChildProcessError as exc:
            raise VerificationOutputCaptureError(
                "独立验证子进程状态已被外部回收；拒绝生成完整验证证据",
            ) from exc
        if pid == proc.pid:
            proc.returncode = os.waitstatus_to_exitcode(status)
            return proc.returncode

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise VerificationOutputCaptureError(
                "独立验证进程在终止信号后仍未退出；拒绝生成完整验证证据",
            )
        time.sleep(min(0.01, remaining))

def _run_posix_bounded_output(
    argv: list[str], *, workspace: Path, timeout: int, output_limit_bytes: int,
    environment: dict[str, str] | None = None,
) -> tuple[int, bytes, bytes]:
    """Use nonblocking selectors so even setsid descendants cannot hang a reader."""
    proc = subprocess.Popen(  # noqa: S603 - host-selected argv, shell=False
        argv, cwd=str(workspace), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=False, bufsize=0, shell=False, start_new_session=True,
        **({"env": environment, "stdin": subprocess.DEVNULL} if environment is not None else {}),
    )
    process_deadline = time.monotonic() + timeout
    stdout_chunks = bytearray()
    stderr_chunks = bytearray()
    selector: selectors.BaseSelector | None = None
    captured_bytes = 0
    exceeded = False
    read_errors: list[OSError] = []
    return_code: int | None = None
    drain_deadline: float | None = None
    timed_out = False
    incomplete = False
    group_cleanup_ok = True
    group_cleanup_errno: int | None = None
    # A killpg attempt may take effect even if reaping later fails; never
    # retry a numeric PGID after status loss, where that ID could be reused.
    group_cleanup_attempted = False
    exit_monitor: _PosixVerificationExitMonitor | None = None

    try:
        assert proc.stdout is not None and proc.stderr is not None
        targets = {
            proc.stdout.fileno(): stdout_chunks,
            proc.stderr.fileno(): stderr_chunks,
        }
        try:
            selector = selectors.DefaultSelector()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise VerificationOutputCaptureError(
                "无法建立独立验证输出选择器；已拒绝不完整验证",
            ) from exc
        try:
            exit_monitor = _PosixVerificationExitMonitor(proc)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise VerificationOutputCaptureError(
                "无法建立安全的 POSIX 进程退出监视；拒绝运行独立验证",
            ) from exc
        for stream in (proc.stdout, proc.stderr):
            os.set_blocking(stream.fileno(), False)
            assert selector is not None
            selector.register(stream, selectors.EVENT_READ, targets[stream.fileno()])

        while True:
            now = time.monotonic()
            assert exit_monitor is not None
            assert selector is not None
            process_exited = exit_monitor.exited(proc)
            if process_exited and return_code is None:
                group_cleanup_attempted = True
                group_cleanup_ok, group_cleanup_errno = _terminate_posix_verification_group(
                    proc, process_exited=True,
                )
                return_code = _reap_posix_verification_process(proc)
                drain_deadline = now + _VERIFICATION_OUTPUT_DRAIN_TIMEOUT_SECONDS
            if return_code is not None and not selector.get_map():
                break
            if not process_exited and return_code is None and now >= process_deadline:
                timed_out = True
                group_cleanup_attempted = True
                cleanup_ok, cleanup_errno = _terminate_posix_verification_group(
                    proc, process_exited=False,
                )
                group_cleanup_ok = cleanup_ok and group_cleanup_ok
                group_cleanup_errno = cleanup_errno or group_cleanup_errno
                return_code = _reap_posix_verification_process(proc)
                drain_deadline = time.monotonic() + _VERIFICATION_OUTPUT_DRAIN_TIMEOUT_SECONDS

            if not selector.get_map():
                remaining = (
                    process_deadline - time.monotonic()
                    if drain_deadline is None
                    else drain_deadline - time.monotonic()
                )
                time.sleep(min(max(remaining, 0.0), 0.1))
                continue
            if drain_deadline is not None:
                remaining = drain_deadline - time.monotonic()
                if remaining <= 0:
                    incomplete = True
                    break
                wait_seconds = min(remaining, 0.1)
            else:
                remaining = process_deadline - time.monotonic()
                wait_seconds = min(max(remaining, 0.0), 0.1)

            for key, _ in selector.select(wait_seconds):
                try:
                    chunk = os.read(key.fd, _VERIFICATION_OUTPUT_READ_CHUNK_BYTES)
                except BlockingIOError:
                    continue
                except OSError as exc:
                    read_errors.append(exc)
                    selector.unregister(key.fileobj)
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                captured_bytes, over_limit = _retain_verification_output(
                    chunk, key.data, output_limit_bytes=output_limit_bytes,
                    captured_bytes=captured_bytes,
                )
                exceeded = exceeded or over_limit

        if return_code is None:
            group_cleanup_attempted = True
            cleanup_ok, cleanup_errno = _terminate_posix_verification_group(
                proc, process_exited=False,
            )
            group_cleanup_ok = cleanup_ok and group_cleanup_ok
            group_cleanup_errno = cleanup_errno or group_cleanup_errno
            return_code = _reap_posix_verification_process(proc)
        if timed_out:
            timeout_error = subprocess.TimeoutExpired(argv, timeout)
            timeout_error.output = bytes(stdout_chunks)
            timeout_error.stderr = bytes(stderr_chunks)
            raise timeout_error
        if incomplete:
            raise VerificationOutputCaptureError(
                "独立验证退出后，输出管道未在有界期限内关闭；拒绝使用不完整输出",
                return_code=return_code,
            )
        if not group_cleanup_ok:
            raise VerificationOutputCaptureError(
                "独立验证进程组清理未确认"
                + (f"（errno={group_cleanup_errno}）" if group_cleanup_errno is not None else "")
                + "；拒绝生成完整验证证据",
                return_code=return_code,
            )
        if read_errors:
            raise OSError("独立验证输出读取失败") from read_errors[0]
        if exceeded:
            raise VerificationOutputLimitError(
                output_limit_bytes, return_code=return_code,
            )
        assert return_code is not None
        return return_code, bytes(stdout_chunks), bytes(stderr_chunks)
    except BaseException:
        if proc.returncode is None and not group_cleanup_attempted:
            group_cleanup_attempted = True
            _terminate_posix_verification_group(proc, process_exited=False)
            try:
                _reap_posix_verification_process(proc)
            except VerificationOutputCaptureError:
                pass
        raise
    finally:
        try:
            if exit_monitor is not None:
                exit_monitor.close()
        finally:
            try:
                if selector is not None:
                    selector.close()
            finally:
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()

def _cancel_windows_pipe_readers(
    readers: list[threading.Thread], stop_readers: threading.Event,
) -> bool:
    """Cancel blocking Windows ReadFile calls so a daemon reader cannot linger."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    stop_readers.set()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenThread.restype = wintypes.HANDLE
    kernel.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
    kernel.CancelSynchronousIo.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    cleanup_ok = True
    cancel_deadline = time.monotonic() + 1.0
    while any(reader.is_alive() for reader in readers) and time.monotonic() < cancel_deadline:
        for reader in readers:
            if not reader.is_alive() or reader.native_id is None:
                continue
            handle = kernel.OpenThread(0x0001, False, reader.native_id)  # THREAD_TERMINATE
            if not handle:
                continue
            try:
                if not kernel.CancelSynchronousIo(handle):
                    error = ctypes.get_last_error()
                    # ERROR_NOT_FOUND means no read is pending at this instant;
                    # retry because the reader may have raced into the next read.
                    if error == 1168:
                        continue
                    # Any other failure is also retried to the bounded deadline;
                    # the final thread state determines whether cleanup succeeded.
            finally:
                if not kernel.CloseHandle(handle):
                    cleanup_ok = False
        for reader in readers:
            if reader.is_alive():
                reader.join(timeout=0.05)
    join_deadline = time.monotonic() + 1.0
    for reader in readers:
        reader.join(timeout=max(0.0, join_deadline - time.monotonic()))
    return cleanup_ok and not any(reader.is_alive() for reader in readers)

def _run_threaded_bounded_output(
    argv: list[str], *, workspace: Path, timeout: int, output_limit_bytes: int,
    environment: dict[str, str] | None = None,
) -> tuple[int, bytes, bytes]:
    job = None
    if sys.platform == "win32":
        from .windows_process_tree import WindowsProcessTree

        job = WindowsProcessTree()
    try:
        return _run_threaded_bounded_output_impl(
            argv, workspace=workspace, timeout=timeout,
            output_limit_bytes=output_limit_bytes, job=job,
            **({"environment": environment} if environment is not None else {}),
        )
    finally:
        if job is not None:
            job.close()

def _terminate_threaded_verification_tree(proc, job) -> bool:
    """Boundedly stop the Job (when present) and reap its verifier root."""
    if job is not None and job.assigned:
        try:
            job.terminate_and_wait(_VERIFICATION_PROCESS_CLEANUP_TIMEOUT_SECONDS)
        except OSError:
            pass

    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            if proc.poll() is None:
                return False
    try:
        proc.wait(timeout=_VERIFICATION_PROCESS_CLEANUP_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError):
        return False

    if job is not None and job.assigned:
        try:
            return job.wait_until_empty(_VERIFICATION_PROCESS_CLEANUP_TIMEOUT_SECONDS)
        except OSError:
            return False
    return True

def _join_or_cancel_threaded_readers(
    readers: list[threading.Thread], stop_readers: threading.Event,
) -> bool:
    drain_deadline = time.monotonic() + _VERIFICATION_OUTPUT_DRAIN_TIMEOUT_SECONDS
    for reader in readers:
        reader.join(timeout=max(0.0, drain_deadline - time.monotonic()))
    if any(reader.is_alive() for reader in readers):
        return _cancel_windows_pipe_readers(readers, stop_readers)
    return True

def _run_threaded_bounded_output_impl(
    argv: list[str], *, workspace: Path, timeout: int, output_limit_bytes: int,
    job=None, environment: dict[str, str] | None = None,
) -> tuple[int, bytes, bytes]:
    """Windows pipe reader threads with a bounded drain and explicit cancellation."""

    popen_options = {
        "cwd": str(workspace),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": False,
        "bufsize": 0,
        "shell": False,
    }
    if environment is not None:
        popen_options.update(env=environment, stdin=subprocess.DEVNULL)
    if job is not None:
        from .windows_process_tree import CREATE_SUSPENDED

        popen_options["creationflags"] = CREATE_SUSPENDED
    proc = subprocess.Popen(  # noqa: S603 - argv 是固定 unittest 启动参数，shell=False
        argv, **popen_options,
    )
    assert proc.stdout is not None and proc.stderr is not None
    stdout_chunks = bytearray()
    stderr_chunks = bytearray()
    captured_bytes = 0
    exceeded = False
    read_errors: list[Exception] = []
    capture_lock = threading.Lock()
    stop_readers = threading.Event()

    def drain(stream: BinaryIO, target: bytearray) -> None:
        nonlocal captured_bytes, exceeded
        try:
            while not stop_readers.is_set():
                try:
                    # Use unbuffered Popen pipes so each read drains currently
                    # available bytes instead of waiting to fill a 64 KiB buffer.
                    chunk = stream.read(_VERIFICATION_OUTPUT_READ_CHUNK_BYTES)
                except OSError:
                    if stop_readers.is_set():
                        break
                    raise
                if not chunk:
                    break
                with capture_lock:
                    captured_bytes, over_limit = _retain_verification_output(
                        chunk, target, output_limit_bytes=output_limit_bytes,
                        captured_bytes=captured_bytes,
                    )
                    exceeded = exceeded or over_limit
        except Exception as exc:  # noqa: BLE001 - a reader failure invalidates the evidence.
            if not stop_readers.is_set():
                with capture_lock:
                    read_errors.append(exc)
        finally:
            try:
                stream.close()
            except OSError as exc:
                if not stop_readers.is_set():
                    with capture_lock:
                        read_errors.append(exc)

    readers = (
        (threading.Thread(target=drain, args=(proc.stdout, stdout_chunks), daemon=True), proc.stdout),
        (threading.Thread(target=drain, args=(proc.stderr, stderr_chunks), daemon=True), proc.stderr),
    )
    started_readers: list[threading.Thread] = []
    started_streams: list[BinaryIO] = []
    try:
        for reader, stream in readers:
            reader.start()
            started_readers.append(reader)
            started_streams.append(stream)
    except BaseException:
        cleanup_ok = _terminate_threaded_verification_tree(proc, job)
        _cancel_windows_pipe_readers(started_readers, stop_readers)
        for _, stream in readers:
            if stream not in started_streams:
                stream.close()
        if not cleanup_ok:
            raise VerificationOutputCaptureError(
                "独立验证启动失败后，验证进程树清理未确认",
            )
        raise

    if job is not None:
        try:
            # CPython's Windows Popen retains the original process HANDLE;
            # using it avoids reopening a potentially recycled PID.
            process_handle = getattr(proc, "_handle", None)
            if (
                isinstance(process_handle, bool)
                or not isinstance(process_handle, int)
                or process_handle < 1
            ):
                raise RuntimeError("Windows Popen did not expose its native process handle")
            job.assign_and_resume(proc.pid, int(process_handle))
        except BaseException as exc:
            cleanup_ok = _terminate_threaded_verification_tree(proc, job)
            readers_ok = _join_or_cancel_threaded_readers(
                started_readers, stop_readers,
            )
            if not cleanup_ok or not readers_ok:
                raise VerificationOutputCaptureError(
                    "Windows Job 绑定失败后，未能确认验证进程树和管道均已清理",
                    return_code=proc.returncode,
                ) from exc
            raise VerificationOutputCaptureError(
                "Windows Job 绑定或主线程恢复失败；验证 payload 未获准运行",
                return_code=proc.returncode,
            ) from exc

    try:
        return_code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        cleanup_ok = _terminate_threaded_verification_tree(proc, job)
        readers_ok = _join_or_cancel_threaded_readers(
            started_readers, stop_readers,
        )
        if not cleanup_ok or not readers_ok:
            raise VerificationOutputCaptureError(
                "独立验证超时后，验证进程树或输出读取线程清理未确认",
                return_code=proc.returncode,
            ) from exc
        exc.output = bytes(stdout_chunks)
        exc.stderr = bytes(stderr_chunks)
        raise
    except BaseException as exc:
        cleanup_ok = _terminate_threaded_verification_tree(proc, job)
        _cancel_windows_pipe_readers(started_readers, stop_readers)
        if not cleanup_ok:
            raise VerificationOutputCaptureError(
                "独立验证异常后，验证进程树清理未确认",
                return_code=proc.returncode,
            ) from exc
        raise

    if job is not None:
        try:
            descendants_gone = job.wait_until_empty(0.05)
        except OSError:
            descendants_gone = False
        if not descendants_gone:
            cleanup_ok = _terminate_threaded_verification_tree(proc, job)
            readers_ok = _join_or_cancel_threaded_readers(
                started_readers, stop_readers,
            )
            if not cleanup_ok or not readers_ok:
                raise VerificationOutputCaptureError(
                    "验证器退出后仍有 Job 成员，且进程树/管道清理未确认",
                    return_code=return_code,
                )
            raise VerificationOutputCaptureError(
                "验证器退出后仍有 Job 后代；已终止进程树并拒绝生成验证证据",
                return_code=return_code,
            )

    drain_deadline = time.monotonic() + _VERIFICATION_OUTPUT_DRAIN_TIMEOUT_SECONDS
    for reader in started_readers:
        reader.join(timeout=max(0.0, drain_deadline - time.monotonic()))
    if any(reader.is_alive() for reader in started_readers):
        readers_stopped = _cancel_windows_pipe_readers(
            started_readers, stop_readers,
        )
        message = (
            "独立验证退出后，输出管道未在有界期限内关闭；拒绝使用不完整输出"
            if readers_stopped
            else "独立验证退出后，输出读取线程清理未确认；拒绝使用不完整输出"
        )
        raise VerificationOutputCaptureError(
            message,
            return_code=return_code,
        )
    if read_errors:
        raise OSError("独立验证输出读取失败") from read_errors[0]
    if exceeded:
        raise VerificationOutputLimitError(
            output_limit_bytes, return_code=return_code,
        )
    return return_code, bytes(stdout_chunks), bytes(stderr_chunks)

def _decode_verification_output(output: bytes) -> str:
    """Match subprocess text-mode UTF-8 replacement and universal newlines."""
    text = output.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")
