"""运行器测试（离线）：靶场隔离、快照比对、独立验证、真模型后端构造。"""

from __future__ import annotations

import json
import hashlib
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests._support import REPO_ROOT, require_skill, temp_workspace

from icode.backends import BackendError, OpenAICompatibleBackend, Usage, build_backend
from icode.runner import _changed, _snapshot, prepare_workspace, run_unittest


def _normalize_unittest_elapsed_time(output: str) -> str:
    return re.sub(
        r"(?m)^Ran ([0-9]+) tests? in [0-9]+(?:\.[0-9]+)?s$",
        r"Ran \1 tests in <elapsed>s",
        output,
    )


class _WindowsTestProcessHandle:
    """Keep one verified process handle across assertion and fallback cleanup."""

    def __init__(self, pid: int, expected_creation_filetime: int) -> None:
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.kernel = self.ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [
            self.wintypes.DWORD, self.wintypes.BOOL, self.wintypes.DWORD,
        ]
        self.kernel.OpenProcess.restype = self.wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [
            self.wintypes.HANDLE, self.wintypes.DWORD,
        ]
        self.kernel.WaitForSingleObject.restype = self.wintypes.DWORD
        self.kernel.GetProcessTimes.argtypes = [
            self.wintypes.HANDLE,
            ctypes.POINTER(self.wintypes.FILETIME),
            ctypes.POINTER(self.wintypes.FILETIME),
            ctypes.POINTER(self.wintypes.FILETIME),
            ctypes.POINTER(self.wintypes.FILETIME),
        ]
        self.kernel.GetProcessTimes.restype = self.wintypes.BOOL
        self.kernel.TerminateProcess.argtypes = [
            self.wintypes.HANDLE, self.wintypes.UINT,
        ]
        self.kernel.TerminateProcess.restype = self.wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [self.wintypes.HANDLE]
        self.kernel.CloseHandle.restype = self.wintypes.BOOL
        self.handle = self.kernel.OpenProcess(0x00101001, False, pid)
        if not self.handle:
            error = self.ctypes.get_last_error()
            raise OSError(error, "OpenProcess")

        creation_time = self.wintypes.FILETIME()
        other_times = [self.wintypes.FILETIME() for _ in range(3)]
        if not self.kernel.GetProcessTimes(
            self.handle,
            self.ctypes.byref(creation_time),
            self.ctypes.byref(other_times[0]),
            self.ctypes.byref(other_times[1]),
            self.ctypes.byref(other_times[2]),
        ):
            error = self.ctypes.get_last_error()
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise OSError(error, "GetProcessTimes")

        actual_creation_filetime = (
            (int(creation_time.dwHighDateTime) & 0xFFFFFFFF) << 32
        ) | (int(creation_time.dwLowDateTime) & 0xFFFFFFFF)
        self.identity_matches = (
            actual_creation_filetime == expected_creation_filetime
        )
        if not self.identity_matches:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise RuntimeError("Windows process PID was reused before handle capture")

    def exited_within(self, timeout_seconds: float) -> bool:
        if not self.handle or not self.identity_matches:
            raise RuntimeError("Windows process identity was not verified")
        status = self.kernel.WaitForSingleObject(
            self.handle, max(0, int(timeout_seconds * 1000)),
        )
        if status == 0:
            return True
        if status == 0x00000102:  # WAIT_TIMEOUT
            return False
        raise OSError(self.ctypes.get_last_error(), "WaitForSingleObject")

    def terminate_for_test_cleanup(self) -> None:
        """Terminate only the process whose creation identity was verified."""
        if not self.handle or not self.identity_matches:
            return
        status = self.kernel.WaitForSingleObject(self.handle, 0)
        if status == 0:  # WAIT_OBJECT_0: the verified target already exited.
            return
        if status != 0x00000102:  # WAIT_TIMEOUT; other failures are inconclusive.
            return
        if self.kernel.TerminateProcess(self.handle, 1):
            self.kernel.WaitForSingleObject(self.handle, 5000)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class TestWindowsTestProcessHandle(unittest.TestCase):
    def test_open_process_failure_is_not_treated_as_exited(self) -> None:
        import ctypes

        kernel = SimpleNamespace(
            OpenProcess=mock.Mock(return_value=0),
            WaitForSingleObject=mock.Mock(return_value=0),
            GetProcessTimes=mock.Mock(),
            CloseHandle=mock.Mock(),
            TerminateProcess=mock.Mock(),
        )
        with (
            mock.patch.object(ctypes, "WinDLL", return_value=kernel, create=True),
            mock.patch.object(ctypes, "get_last_error", return_value=5, create=True),
        ):
            with self.assertRaises(OSError) as caught:
                _WindowsTestProcessHandle(42, 99)

        self.assertEqual(caught.exception.args[:2], (5, "OpenProcess"))
        kernel.GetProcessTimes.assert_not_called()
        kernel.CloseHandle.assert_not_called()
        kernel.TerminateProcess.assert_not_called()

    def test_creation_time_query_failure_closes_handle_without_termination(self) -> None:
        import ctypes

        kernel = SimpleNamespace(
            OpenProcess=mock.Mock(return_value=123),
            WaitForSingleObject=mock.Mock(return_value=0),
            GetProcessTimes=mock.Mock(return_value=0),
            CloseHandle=mock.Mock(return_value=1),
            TerminateProcess=mock.Mock(),
        )
        with (
            mock.patch.object(ctypes, "WinDLL", return_value=kernel, create=True),
            mock.patch.object(ctypes, "get_last_error", return_value=5, create=True),
        ):
            with self.assertRaises(OSError) as caught:
                _WindowsTestProcessHandle(42, 99)

        self.assertEqual(caught.exception.args[:2], (5, "GetProcessTimes"))
        kernel.CloseHandle.assert_called_once_with(123)
        kernel.TerminateProcess.assert_not_called()

    def test_creation_time_mismatch_closes_handle_and_fails_closed(self) -> None:
        import ctypes
        from ctypes import wintypes

        def write_creation_time(_handle, creation_ptr, *_other_times) -> int:
            creation = ctypes.cast(
                creation_ptr, ctypes.POINTER(wintypes.FILETIME),
            ).contents
            creation.dwHighDateTime = 0
            creation.dwLowDateTime = 98
            return 1

        kernel = SimpleNamespace(
            OpenProcess=mock.Mock(return_value=123),
            WaitForSingleObject=mock.Mock(return_value=0),
            GetProcessTimes=mock.Mock(side_effect=write_creation_time),
            CloseHandle=mock.Mock(return_value=1),
            TerminateProcess=mock.Mock(),
        )
        with mock.patch.object(ctypes, "WinDLL", return_value=kernel, create=True):
            with self.assertRaisesRegex(RuntimeError, "PID was reused"):
                _WindowsTestProcessHandle(42, 99)

        kernel.CloseHandle.assert_called_once_with(123)
        kernel.TerminateProcess.assert_not_called()

    def test_cleanup_identity不匹配时不终止同PID的其他进程(self) -> None:
        process = object.__new__(_WindowsTestProcessHandle)
        process.handle = object()
        process.identity_matches = False
        process.kernel = SimpleNamespace(
            TerminateProcess=mock.Mock(return_value=1),
            WaitForSingleObject=mock.Mock(return_value=0),
        )

        process.terminate_for_test_cleanup()

        process.kernel.TerminateProcess.assert_not_called()
        process.kernel.WaitForSingleObject.assert_not_called()


class _WindowsTestProcessObserver:
    """Capture and retain the child's verified process handle before it exits."""

    def __init__(self, identity_path: Path, acknowledgement_path: Path) -> None:
        self.identity_path = identity_path
        self.acknowledgement_path = acknowledgement_path
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._process_lock = threading.Lock()
        self._closed = False
        self._process: _WindowsTestProcessHandle | None = None
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._observe, daemon=True)

    @property
    def process_handle(self) -> _WindowsTestProcessHandle | None:
        with self._process_lock:
            return self._process

    def start(self) -> None:
        self._thread.start()

    def _observe(self) -> None:
        deadline = time.monotonic() + 5.0
        while not self._stop.is_set() and time.monotonic() < deadline:
            if self.identity_path.is_file():
                try:
                    pid, creation_filetime = _read_windows_process_identity(
                        self.identity_path,
                    )
                    process = _WindowsTestProcessHandle(pid, creation_filetime)
                    with self._process_lock:
                        closed = self._closed
                        if not closed:
                            self._process = process
                    if closed:
                        try:
                            process.terminate_for_test_cleanup()
                        finally:
                            process.close()
                        return
                    self.acknowledgement_path.write_text("captured", encoding="ascii")
                except Exception as error:
                    self._error = error
                finally:
                    self._ready.set()
                return
            self._stop.wait(0.01)
        if not self._stop.is_set():
            self._error = TimeoutError("Windows test child identity was not observed")
            self._ready.set()

    def wait_for_process(self, timeout_seconds: float) -> _WindowsTestProcessHandle:
        if not self._ready.wait(timeout_seconds):
            raise TimeoutError("Windows test process handle was not captured")
        if self._error is not None:
            raise self._error
        if self._process is None:
            raise RuntimeError("Windows observer finished without a process handle")
        return self._process

    def close(self) -> None:
        with self._process_lock:
            self._closed = True
        self._stop.set()
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            raise RuntimeError("Windows test process observer did not stop")


class TestWindowsTestProcessObserver(unittest.TestCase):
    def test_close_during_handle_capture_closes_late_handle(self) -> None:
        with temp_workspace() as ws:
            identity_path = ws / "identity"
            identity_path.write_text("42 99", encoding="ascii")
            entered_capture = threading.Event()
            release_capture = threading.Event()
            process = SimpleNamespace(
                terminate_for_test_cleanup=mock.Mock(),
                close=mock.Mock(),
            )

            def delayed_process_capture(pid: int, creation_filetime: int):
                self.assertEqual((pid, creation_filetime), (42, 99))
                entered_capture.set()
                if not release_capture.wait(2.0):
                    raise TimeoutError("test did not release process capture")
                return process

            observer = _WindowsTestProcessObserver(
                identity_path, ws / "acknowledged",
            )
            observer_globals = _WindowsTestProcessObserver._observe.__globals__
            with mock.patch.dict(
                observer_globals,
                {"_WindowsTestProcessHandle": delayed_process_capture},
            ):
                observer.start()
                # Full-suite discovery may have other bounded subprocess tests
                # completing immediately before this case.  Keep the test
                # deterministic under that scheduler load while retaining a
                # finite wait and the same close-during-capture assertion.
                self.assertTrue(entered_capture.wait(5.0))
                try:
                    with self.assertRaisesRegex(
                        RuntimeError, "observer did not stop",
                    ):
                        observer.close()
                finally:
                    release_capture.set()
                observer._thread.join(timeout=1.0)

            self.assertFalse(observer._thread.is_alive())
            process.terminate_for_test_cleanup.assert_called_once_with()
            process.close.assert_called_once_with()
            self.assertIsNone(observer.process_handle)
            self.assertFalse((ws / "acknowledged").exists())


def _read_windows_process_identity(path: Path) -> tuple[int, int]:
    fields = path.read_text(encoding="ascii").split()
    if len(fields) != 2:
        raise ValueError("Windows child identity must contain PID and creation FILETIME")
    pid, creation_filetime = (int(field, 10) for field in fields)
    if pid <= 0 or creation_filetime <= 0:
        raise ValueError("Windows child identity values must be positive")
    return pid, creation_filetime


def _windows_child_identity_writer(identity_path: Path, after_write: str) -> str:
    """Return a Windows-only child prelude recording its PID and creation time."""
    return (
        "import ctypes, os\n"
        "from ctypes import wintypes\n"
        "from pathlib import Path\n"
        "kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)\n"
        "kernel32.GetCurrentProcess.restype = wintypes.HANDLE\n"
        "kernel32.GetProcessTimes.argtypes = [\n"
        "    wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),\n"
        "    ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),\n"
        "    ctypes.POINTER(wintypes.FILETIME),\n"
        "]\n"
        "kernel32.GetProcessTimes.restype = wintypes.BOOL\n"
        "creation = wintypes.FILETIME()\n"
        "others = [wintypes.FILETIME() for _ in range(3)]\n"
        "if not kernel32.GetProcessTimes(\n"
        "    kernel32.GetCurrentProcess(), ctypes.byref(creation),\n"
        "    ctypes.byref(others[0]), ctypes.byref(others[1]), ctypes.byref(others[2]),\n"
        "):\n"
        "    raise OSError(ctypes.get_last_error(), 'GetProcessTimes')\n"
        "creation_filetime = ((creation.dwHighDateTime & 0xFFFFFFFF) << 32) | (creation.dwLowDateTime & 0xFFFFFFFF)\n"
        f"identity_path = Path({str(identity_path)!r})\n"
        "identity_temp = identity_path.with_suffix(identity_path.suffix + '.tmp')\n"
        "identity_temp.write_text(f'{os.getpid()} {creation_filetime}', encoding='ascii')\n"
        "identity_temp.replace(identity_path)\n"
        + after_write
    )


class TestFixtureIsolation(unittest.TestCase):
    def test_靶场复制到隔离目录(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            self.assertTrue((dst / "calc.py").is_file())
            self.assertTrue((dst / "test_calc.py").is_file())
            # 是副本，不是软链/原目录
            self.assertNotEqual(dst.resolve(), (REPO_ROOT / "tests" / "fixtures" / "pycalc").resolve())

    def test_改副本不影响仓库基线(self) -> None:
        origin = REPO_ROOT / "tests" / "fixtures" / "pycalc" / "calc.py"
        before = origin.read_text(encoding="utf-8")
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            (dst / "calc.py").write_text("# 被污染的副本\n", encoding="utf-8")
        self.assertEqual(origin.read_text(encoding="utf-8"), before,
                         "靶场基线被污染：E2E 必须在副本上跑")

    def test_未知靶场报错(self) -> None:
        with temp_workspace() as ws:
            with self.assertRaises(FileNotFoundError):
                prepare_workspace("no_such_fixture", ws / "work", repo_root=REPO_ROOT)

    def test_重复准备会重建(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            (dst / "junk.tmp").write_text("x", encoding="utf-8")
            dst2 = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            self.assertFalse((dst2 / "junk.tmp").exists())


class TestSnapshot(unittest.TestCase):
    def test_改动检测(self) -> None:
        with temp_workspace() as ws:
            (ws / "a.py").write_text("1\n", encoding="utf-8")
            before = _snapshot(ws)
            (ws / "a.py").write_text("2\n", encoding="utf-8")
            (ws / "b.py").write_text("3\n", encoding="utf-8")
            after = _snapshot(ws)
            self.assertEqual(_changed(before, after), ["a.py", "b.py"])

    def test_快照忽略工单产物(self) -> None:
        with temp_workspace() as ws:
            (ws / ".icode_output").mkdir()
            (ws / ".icode_output" / "x.md").write_text("x", encoding="utf-8")
            (ws / "a.py").write_text("1\n", encoding="utf-8")
            self.assertEqual(list(_snapshot(ws)), ["a.py"])

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_快照只记录链接文本不读取外部目标(self) -> None:
        with temp_workspace() as parent:
            workspace = parent / "workspace"
            workspace.mkdir()
            secret = parent / "secret"
            secret.write_text("outside-secret", encoding="utf-8")
            link = workspace / "alias"
            link.symlink_to(secret)
            expected = hashlib.sha256(os.fsencode(str(secret))).hexdigest()

            before = _snapshot(workspace)
            self.assertIn("alias", before)
            self.assertNotEqual(before["alias"], expected)
            secret.write_text("changed-outside-secret", encoding="utf-8")
            self.assertEqual(_snapshot(workspace), before)

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_快照不递归外部目录且拒绝链接根(self) -> None:
        with temp_workspace() as parent:
            workspace = parent / "workspace"
            workspace.mkdir()
            outside = parent / "outside"
            outside.mkdir()
            (outside / "secret").write_text("outside-secret", encoding="utf-8")
            (workspace / "directory-link").symlink_to(outside, target_is_directory=True)
            self.assertEqual(list(_snapshot(workspace)), ["directory-link"])
            root_alias = parent / "root-alias"
            root_alias.symlink_to(workspace, target_is_directory=True)
            with self.assertRaises(OSError):
                _snapshot(root_alias)


class TestIndependentVerification(unittest.TestCase):
    def test_unittest摘要归一化忽略非确定耗时(self) -> None:
        self.assertEqual(
            _normalize_unittest_elapsed_time("Ran 1 test in 0.000s\nOK\n"),
            _normalize_unittest_elapsed_time("Ran 1 test in 0.001s\nOK\n"),
        )

    @staticmethod
    def _raw_unittest_output(workspace):
        result = subprocess.run(
            [sys.executable, "-B", "-m", "unittest"],
            cwd=str(workspace), capture_output=True, text=False,
            timeout=180, shell=False,
        )
        return result.returncode, result.stdout, result.stderr

    def test_任务证据对大型改动文件使用有界分块哈希(self) -> None:
        from pathlib import Path

        from icode.runner import _bind_task_evidence

        content = b"large evidence artifact\n" * 90_000
        expected_digest = hashlib.sha256(content).hexdigest()
        chunk_limit = 1024 * 1024
        with temp_workspace() as workspace:
            artifact = workspace / "large.bin"
            artifact.write_bytes(content)
            original_open = Path.open
            original_read_bytes = Path.read_bytes
            read_bytes_paths: list[Path] = []
            read_sizes: list[int] = []

            class _ReadSizeTracker:
                def __init__(self, stream):
                    self.stream = stream

                def __enter__(self):
                    return self

                def __exit__(self, _exc_type, _exc, _traceback):
                    self.stream.close()
                    return False

                def read(self, size=-1):
                    read_sizes.append(size)
                    return self.stream.read(size)

            def tracked_open(path, *args, **kwargs):
                stream = original_open(path, *args, **kwargs)
                if path == artifact:
                    return _ReadSizeTracker(stream)
                return stream

            def tracked_read_bytes(path):
                read_bytes_paths.append(path)
                return original_read_bytes(path)

            with (
                mock.patch.object(Path, "open", new=tracked_open),
                mock.patch.object(Path, "read_bytes", new=tracked_read_bytes),
            ):
                changed, evidence = _bind_task_evidence(
                    {"large.bin": "before"}, {"large.bin": "after"},
                    0, "", workspace,
                )

            self.assertEqual(changed, ["large.bin"])
            self.assertEqual(evidence.artifact_hashes["large.bin"], expected_digest)
            self.assertEqual(read_bytes_paths, [], "不得整文件载入到内存")
            self.assertTrue(read_sizes, "改动文件必须确实经过分块读取")
            self.assertTrue(
                all(0 < size <= chunk_limit for size in read_sizes),
                f"文件读取块必须不超过 {chunk_limit} 字节：{read_sizes!r}",
            )

    def test_有界输出解码保持universal_newlines和非法UTF8兼容(self) -> None:
        from icode import runner

        self.assertEqual(
            runner._decode_verification_output(b"a\r\nb\rc\n\xff"),
            "a\nb\nc\n�",
        )

    @unittest.skipUnless(os.name == "posix", "POSIX killpg cleanup semantics")
    def test_macos进程组EPERM仅在独立确认无存活成员后视为已清理(self) -> None:
        from icode import runner

        process = SimpleNamespace(pid=4321, returncode=0)
        with (
            mock.patch.object(runner, "sys", SimpleNamespace(platform="darwin")),
            mock.patch.object(runner.os, "killpg", side_effect=PermissionError(1, "denied")),
            mock.patch.object(runner, "_darwin_process_group_has_live_members", return_value=False),
        ):
            self.assertEqual(
                runner._terminate_posix_verification_group(process, process_exited=True),
                (True, None),
            )

    @unittest.skipUnless(os.name == "posix", "POSIX killpg cleanup semantics")
    def test_macos进程组EPERM且仍有存活成员时保持失败(self) -> None:
        from icode import runner

        process = SimpleNamespace(pid=4321, returncode=0)
        with (
            mock.patch.object(runner, "sys", SimpleNamespace(platform="darwin")),
            mock.patch.object(runner.os, "killpg", side_effect=PermissionError(1, "denied")),
            mock.patch.object(runner, "_darwin_process_group_has_live_members", return_value=True),
        ):
            self.assertEqual(
                runner._terminate_posix_verification_group(process, process_exited=True),
                (False, 1),
            )

    @unittest.skipUnless(os.name == "posix", "Darwin ps 审计使用 POSIX 管道")
    def test_macos进程组审计要求看见zombie锚点并拒绝存活成员(self) -> None:
        from icode import runner

        def inspect(states: bytes) -> bool | None:
            read_fd, write_fd = os.pipe()
            try:
                os.write(write_fd, states)
            finally:
                os.close(write_fd)
            process = SimpleNamespace(
                stdout=os.fdopen(read_fd, "rb", buffering=0),
                returncode=0,
                wait=mock.Mock(return_value=0),
                kill=mock.Mock(),
            )
            with mock.patch.dict(os.environ, {"COMMAND_MODE": "legacy"}):
                with mock.patch.object(
                    runner.subprocess, "Popen", return_value=process,
                ) as popen:
                    result = runner._darwin_process_group_has_live_members(1234)
            self.assertEqual(
                popen.call_args.args[0],
                ["/bin/ps", "-g", "1234", "-x", "-o", "stat="],
            )
            self.assertEqual(
                popen.call_args.kwargs["env"]["COMMAND_MODE"], "unix2003",
                "审计必须覆盖继承的 legacy 模式，确保 -g 参数按 PGID 解释",
            )
            return result

        self.assertIs(inspect(b"Z+\n"), False)
        self.assertIs(inspect(b"Z+\nS\n"), True)
        self.assertIsNone(inspect(b""), "没有 zombie 锚点时不能确认审计范围")

    @unittest.skipUnless(sys.platform == "darwin", "需要 macOS 原生 zombie/ps 语义")
    def test_macos进程组审计能识别未回收的退出leader(self) -> None:
        import selectors

        from icode import runner

        process = subprocess.Popen(
            [sys.executable, "-B", "-c", "pass"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
        )
        monitor = None
        selector = None
        try:
            self.assertIsNotNone(process.stdout)
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(
                selector.select(timeout=2.0),
                "短命 leader 必须在期限内关闭 stdout",
            )
            self.assertEqual(os.read(process.stdout.fileno(), 1), b"")
            self.assertIsNone(process.returncode, "不能在测试退出监视前 reap leader")

            monitor = runner._PosixVerificationExitMonitor(process)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not monitor.exited(process):
                time.sleep(0.01)

            self.assertTrue(monitor.exited(process), "测试 leader 应在期限内退出")
            self.assertIs(
                runner._darwin_process_group_has_live_members(process.pid),
                False,
                "ps 必须只查询目标进程组，并确认未回收 zombie leader 无存活同组后代",
            )
        finally:
            if monitor is not None:
                monitor.close()
            if selector is not None:
                selector.close()
            if process.stdout is not None:
                process.stdout.close()
            process.wait(timeout=2.0)

    @unittest.skipUnless(os.name == "posix", "POSIX bounded runner 清理路径")
    def test_selector初始化失败仍终止并回收已启动的验证进程(self) -> None:
        from icode import runner
        from icode.runner import VerificationOutputCaptureError

        class FakeProcess:
            pid = 987654321
            returncode = None

            def __init__(self) -> None:
                self.stdout = open(os.devnull, "rb")
                self.stderr = open(os.devnull, "rb")

        process = FakeProcess()
        with (
            mock.patch.object(runner.subprocess, "Popen", return_value=process),
            mock.patch.object(
                runner.selectors, "DefaultSelector",
                side_effect=OSError("too many open files"),
            ),
            mock.patch.object(
                runner, "_terminate_posix_verification_group", return_value=(True, None),
            ) as terminate,
            mock.patch.object(
                runner.os, "waitpid", return_value=(process.pid, 0),
            ) as waitpid,
        ):
            with self.assertRaises(VerificationOutputCaptureError):
                runner._run_posix_bounded_output(
                    ["python", "-m", "unittest"],
                    workspace=REPO_ROOT,
                    timeout=10,
                    output_limit_bytes=1024,
                )

        terminate.assert_called_once_with(process, process_exited=False)
        waitpid.assert_called_once_with(process.pid, os.WNOHANG)
        self.assertEqual(process.returncode, 0)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.stderr.closed)

    @unittest.skipUnless(os.name == "posix", "POSIX waitpid reaping")
    def test_POSIX回收保留真实子进程退出码(self) -> None:
        from icode import runner

        process = subprocess.Popen(
            [sys.executable, "-B", "-c", "raise SystemExit(7)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
        )

        self.assertEqual(runner._reap_posix_verification_process(process), 7)
        self.assertEqual(process.returncode, 7)

    @unittest.skipUnless(os.name == "posix", "POSIX ECHILD handling")
    def test_POSIX失去子进程状态时拒绝继续(self) -> None:
        from icode import runner
        from icode.runner import VerificationOutputCaptureError

        process = SimpleNamespace(
            pid=4321,
            returncode=None,
            wait=mock.Mock(return_value=0),
        )
        with mock.patch.object(
            runner.os, "waitpid", side_effect=ChildProcessError(),
        ):
            with self.assertRaises(VerificationOutputCaptureError):
                runner._reap_posix_verification_process(process)

        process.wait.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "POSIX group cleanup ordering")
    def test_退出状态丢失后不重复按旧PGID清理(self) -> None:
        from icode import runner
        from icode.runner import VerificationOutputCaptureError

        class FakeSelector:
            def register(self, *_args, **_kwargs) -> None:
                pass

            def get_map(self):
                return {}

            def close(self) -> None:
                pass

        class FakeMonitor:
            def exited(self, _process) -> bool:
                return True

            def close(self) -> None:
                pass

        class FakeProcess:
            pid = 1234
            returncode = None

            def __init__(self) -> None:
                self.stdout = open(os.devnull, "rb")
                self.stderr = open(os.devnull, "rb")

        process = FakeProcess()
        cleanup = mock.Mock(return_value=(True, None))
        reap = mock.Mock(
            side_effect=VerificationOutputCaptureError(
                "独立验证子进程状态已被外部回收",
            ),
        )
        try:
            with (
                mock.patch.object(runner.subprocess, "Popen", return_value=process),
                mock.patch.object(runner.selectors, "DefaultSelector", FakeSelector),
                mock.patch.object(
                    runner, "_PosixVerificationExitMonitor", return_value=FakeMonitor(),
                ),
                mock.patch.object(runner, "_terminate_posix_verification_group", cleanup),
                mock.patch.object(runner, "_reap_posix_verification_process", reap),
            ):
                with self.assertRaises(VerificationOutputCaptureError):
                    runner._run_posix_bounded_output(
                        ["python", "-m", "unittest"],
                        workspace=REPO_ROOT,
                        timeout=10,
                        output_limit_bytes=1024,
                    )

            cleanup.assert_called_once_with(process, process_exited=True)
            reap.assert_called_once_with(process)
        finally:
            process.stdout.close()
            process.stderr.close()

    @unittest.skipUnless(os.name == "posix", "POSIX kqueue/waitid 分派")
    def test_macos退出监视使用kqueue且不调用waitid(self) -> None:
        from icode import runner

        class FakeKqueue:
            def __init__(self) -> None:
                self.poll_count = 0
                self.closed = False

            def control(self, changes, max_events, timeout):
                if changes is not None:
                    return []
                self.poll_count += 1
                return [SimpleNamespace(flags=0, fflags=16, data=0)]

            def close(self) -> None:
                self.closed = True

        queue = FakeKqueue()
        fake_select = SimpleNamespace(
            kqueue=lambda: queue,
            kevent=lambda *args, **kwargs: object(),
            KQ_FILTER_PROC=1,
            KQ_EV_ADD=2,
            KQ_EV_ENABLE=4,
            KQ_EV_ONESHOT=8,
            KQ_EV_ERROR=32,
            KQ_NOTE_EXIT=16,
        )
        process = SimpleNamespace(pid=1234, returncode=None)
        with (
            mock.patch.object(runner, "select", fake_select),
            mock.patch.object(runner, "sys", SimpleNamespace(platform="darwin")),
            mock.patch.object(
                runner.os, "waitid", create=True,
                side_effect=AssertionError("waitid must not be used"),
            ),
        ):
            monitor = runner._PosixVerificationExitMonitor(process)
            self.assertTrue(monitor.exited(process))
            monitor.close()

        self.assertTrue(queue.closed)

    @unittest.skipUnless(os.name == "posix", "POSIX kqueue 注册结果")
    def test_kqueue注册目标已消失时按已退出处理并关闭队列(self) -> None:
        import errno

        from icode import runner

        class ErrorEvent:
            flags = 32
            data = errno.ESRCH

        class FakeKqueue:
            closed = False

            def control(self, changes, max_events, timeout):
                return [ErrorEvent()]

            def close(self) -> None:
                self.closed = True

        queue = FakeKqueue()
        fake_select = SimpleNamespace(
            kqueue=lambda: queue,
            kevent=lambda *args, **kwargs: object(),
            KQ_FILTER_PROC=1,
            KQ_EV_ADD=2,
            KQ_EV_ENABLE=4,
            KQ_EV_ONESHOT=8,
            KQ_EV_ERROR=32,
            KQ_NOTE_EXIT=16,
        )
        process = SimpleNamespace(pid=1234, returncode=None)
        with (
            mock.patch.object(runner, "select", fake_select),
            mock.patch.object(runner, "sys", SimpleNamespace(platform="darwin")),
        ):
            monitor = runner._PosixVerificationExitMonitor(process)
            try:
                self.assertTrue(monitor.exited(process))
            finally:
                monitor.close()

        self.assertTrue(queue.closed)

    @unittest.skipUnless(os.name == "posix", "POSIX kqueue 轮询错误")
    def test_kqueue轮询阶段的ESRCH仍然失败关闭(self) -> None:
        import errno

        from icode import runner

        class ErrorEvent:
            flags = 32
            data = errno.ESRCH

        class FakeKqueue:
            closed = False

            def control(self, changes, max_events, timeout):
                return [] if changes is not None else [ErrorEvent()]

            def close(self) -> None:
                self.closed = True

        queue = FakeKqueue()
        fake_select = SimpleNamespace(
            kqueue=lambda: queue,
            kevent=lambda *args, **kwargs: object(),
            KQ_FILTER_PROC=1,
            KQ_EV_ADD=2,
            KQ_EV_ENABLE=4,
            KQ_EV_ONESHOT=8,
            KQ_EV_ERROR=32,
            KQ_NOTE_EXIT=16,
        )
        process = SimpleNamespace(pid=1234, returncode=None)
        with (
            mock.patch.object(runner, "select", fake_select),
            mock.patch.object(runner, "sys", SimpleNamespace(platform="darwin")),
        ):
            monitor = runner._PosixVerificationExitMonitor(process)
            try:
                with self.assertRaises(ProcessLookupError):
                    monitor.exited(process)
            finally:
                monitor.close()

        self.assertTrue(queue.closed)

    @unittest.skipUnless(os.name == "posix", "POSIX kqueue 错误事件清理")
    def test_kqueue注册错误会关闭监视器并拒绝继续(self) -> None:
        from icode import runner

        class ErrorEvent:
            flags = 32
            data = 1

        class FakeKqueue:
            closed = False

            def control(self, changes, max_events, timeout):
                return [ErrorEvent()]

            def close(self) -> None:
                self.closed = True

        queue = FakeKqueue()
        fake_select = SimpleNamespace(
            kqueue=lambda: queue,
            kevent=lambda *args, **kwargs: object(),
            KQ_FILTER_PROC=1,
            KQ_EV_ADD=2,
            KQ_EV_ENABLE=4,
            KQ_EV_ONESHOT=8,
            KQ_EV_ERROR=32,
            KQ_NOTE_EXIT=16,
        )
        with (
            mock.patch.object(runner, "select", fake_select),
            mock.patch.object(runner, "sys", SimpleNamespace(platform="darwin")),
        ):
            with self.assertRaises(OSError):
                runner._PosixVerificationExitMonitor(SimpleNamespace(pid=1234))

        self.assertTrue(queue.closed)

    def test_靶场基线独立跑测试通过(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            code, output = run_unittest(dst)
            self.assertEqual(code, 0, output[-800:])
            self.assertIn("OK", output)

    def test_没有发现测试不能被当成通过(self) -> None:
        with temp_workspace() as ws:
            code, output = run_unittest(ws)

        self.assertNotEqual(code, 0, "空测试集不构成验证证据")
        self.assertIn("Ran 0 tests", output)

    def test_改动导致失败时退出码非零(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            (dst / "calc.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
            code, _ = run_unittest(dst)
            self.assertNotEqual(code, 0, "独立验证必须能识别破坏性改动")

    def test_有界输出在预算内保留完整UTF8输出和原摘要输入(self) -> None:
        from icode.runner import VerificationOutputLimitError

        with temp_workspace() as ws:
            (ws / "test_output.py").write_text(
                "import sys, unittest\n"
                "class OutputTest(unittest.TestCase):\n"
                "    def test_output(self):\n"
                "        sys.stdout.write('stdout-雪\\n')\n"
                "        sys.stderr.write('stderr-🧪\\n')\n",
                encoding="utf-8",
            )
            code, baseline = run_unittest(ws)
            self.assertEqual(code, 0, baseline[-800:])
            raw_code, raw_stdout, raw_stderr = self._raw_unittest_output(ws)
            self.assertEqual(raw_code, code)
            cap_bytes = len(raw_stdout) + len(raw_stderr)

            bounded_code, bounded = run_unittest(
                ws, output_limit_bytes=cap_bytes,
            )

            self.assertEqual(bounded_code, code)
            self.assertEqual(
                _normalize_unittest_elapsed_time(bounded),
                _normalize_unittest_elapsed_time(baseline),
            )
            self.assertIn("stdout-雪", bounded)
            self.assertIn("stderr-🧪", bounded)
            with self.assertRaises(VerificationOutputLimitError) as raised:
                run_unittest(ws, output_limit_bytes=cap_bytes - 1)
            self.assertEqual(raised.exception.return_code, 0)

    def test_有界捕获超限时保留非零子进程退出码(self) -> None:
        from icode.runner import VerificationOutputLimitError

        with temp_workspace() as ws:
            (ws / "test_output.py").write_text(
                "import sys, unittest\n"
                "class OutputTest(unittest.TestCase):\n"
                "    def test_output(self):\n"
                "        sys.stdout.write('x' * 4096)\n"
                "        self.fail('verification failed after output')\n",
                encoding="utf-8",
            )
            with self.assertRaises(VerificationOutputLimitError) as raised:
                run_unittest(ws, output_limit_bytes=128)

        self.assertEqual(raised.exception.return_code, 1)

    def test_有界捕获保持非法UTF8替换语义(self) -> None:
        with temp_workspace() as ws:
            (ws / "test_output.py").write_text(
                "import sys, unittest\n"
                "class OutputTest(unittest.TestCase):\n"
                "    def test_output(self):\n"
                "        sys.stdout.buffer.write(b'bad-\\xff\\n')\n"
                "        sys.stderr.buffer.write(b'bad-\\xfe\\n')\n",
                encoding="utf-8",
            )
            code, baseline = run_unittest(ws)
            raw_code, raw_stdout, raw_stderr = self._raw_unittest_output(ws)
            self.assertEqual(raw_code, code)
            bounded_code, bounded = run_unittest(
                ws, output_limit_bytes=len(raw_stdout) + len(raw_stderr),
            )

            self.assertEqual(bounded_code, code)
            self.assertEqual(
                _normalize_unittest_elapsed_time(bounded),
                _normalize_unittest_elapsed_time(baseline),
            )
            self.assertIn("bad-�", bounded)

    def test_有界捕获超时仍终止直接验证进程(self) -> None:
        from subprocess import TimeoutExpired

        with temp_workspace() as ws:
            (ws / "test_slow.py").write_text(
                "import time, unittest\n"
                "class SlowTest(unittest.TestCase):\n"
                "    def test_slow(self):\n"
                "        time.sleep(10)\n",
                encoding="utf-8",
            )

            with self.assertRaises(TimeoutExpired):
                run_unittest(ws, timeout=1, output_limit_bytes=1024)

    @unittest.skipUnless(os.name == "posix", "进程组回收只在 POSIX 上验证")
    def test_父进程退出后回收同组持管道后代(self) -> None:
        with temp_workspace() as ws:
            pid_file = ws / "child.pid"
            late_marker = ws / "late-marker"
            child_code = (
                "import time\nfrom pathlib import Path\n"
                f"time.sleep(2.0)\nPath({str(late_marker)!r}).write_text('late')\n"
            )
            (ws / "test_child.py").write_text(
                "import subprocess, sys, unittest\n"
                "from pathlib import Path\n"
                "class ChildTest(unittest.TestCase):\n"
                "    def test_background_child(self):\n"
                f"        child = subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                "stdout=sys.stdout, stderr=sys.stderr)\n"
                f"        Path({str(pid_file)!r}).write_text(str(child.pid))\n",
                encoding="utf-8",
            )

            started = time.monotonic()
            code, _ = run_unittest(ws, timeout=5, output_limit_bytes=1024)
            elapsed = time.monotonic() - started

            self.assertEqual(code, 0)
            self.assertLess(elapsed, 1.5, "同组后代不应让排空等待其自然退出")
            self.assertFalse(late_marker.exists(), "父进程退出后同组后代应被回收")

    @unittest.skipUnless(os.name == "posix", "POSIX setsid 后代边界")
    def test_主动脱组持有管道时有界失败且不返回部分输出(self) -> None:
        with temp_workspace() as ws:
            pid_file = ws / "detached-child.pid"
            child_code = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
                "time.sleep(3.0)\n"
            )
            (ws / "test_detached_child.py").write_text(
                "import subprocess, sys, time, unittest\n"
                "from pathlib import Path\n"
                "class DetachedChildTest(unittest.TestCase):\n"
                "    def test_detached_child(self):\n"
                f"        subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                "stdout=sys.stdout, stderr=sys.stderr)\n"
                f"        for _ in range(200):\n            if Path({str(pid_file)!r}).exists(): break\n"
                "            time.sleep(0.01)\n",
                encoding="utf-8",
            )

            started = time.monotonic()
            try:
                with self.assertRaisesRegex(RuntimeError, "输出管道未在"):
                    run_unittest(ws, timeout=5, output_limit_bytes=1024)
                self.assertLess(
                    time.monotonic() - started, 4.0,
                    "主动脱组后代不能令独立验证无限等待",
                )
            finally:
                if pid_file.is_file():
                    try:
                        os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    @unittest.skipUnless(os.name == "posix", "进程组回收只在 POSIX 上验证")
    def test_验证进程超时会回收仍持有输出管道的同组后代(self) -> None:
        from subprocess import TimeoutExpired

        with temp_workspace() as ws:
            late_marker = ws / "timeout-child-late-marker"
            child_code = (
                "import time\nfrom pathlib import Path\n"
                f"time.sleep(2.0)\nPath({str(late_marker)!r}).write_text('late')\n"
            )
            (ws / "test_timeout_child.py").write_text(
                "import subprocess, sys, time, unittest\n"
                "class TimeoutChildTest(unittest.TestCase):\n"
                "    def test_background_child(self):\n"
                f"        subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                "stdout=sys.stdout, stderr=sys.stderr)\n"
                "        time.sleep(10)\n",
                encoding="utf-8",
            )

            started = time.monotonic()
            with self.assertRaises(TimeoutExpired):
                run_unittest(ws, timeout=1, output_limit_bytes=1024)

            self.assertLess(time.monotonic() - started, 3.0)
            self.assertFalse(late_marker.exists(), "超时清理必须覆盖仍持有管道的同组后代")

    @unittest.skipUnless(os.name == "nt", "Windows 同步 pipe read 取消")
    def test_windows_后代持有管道时有界失败且清理读取线程(self) -> None:
        from icode.runner import VerificationOutputCaptureError

        with temp_workspace() as ws:
            pid_file = ws / "windows-child.pid"
            acknowledged_file = ws / "windows-child-handle-captured"
            child_code = _windows_child_identity_writer(
                pid_file, "import time\ntime.sleep(30.0)\n",
            )
            (ws / "test_windows_child.py").write_text(
                "import subprocess, sys, time, unittest\n"
                "from pathlib import Path\n"
                "class WindowsChildTest(unittest.TestCase):\n"
                "    def test_background_child(self):\n"
                f"        subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                "stdout=sys.stdout, stderr=sys.stderr)\n"
                f"        for _ in range(200):\n            if Path({str(acknowledged_file)!r}).is_file(): break\n"
                "            time.sleep(0.01)\n"
                "        else:\n            raise AssertionError('child handle was not captured')\n",
                encoding="utf-8",
            )

            started = time.monotonic()
            observer = _WindowsTestProcessObserver(pid_file, acknowledged_file)
            observer.start()
            child_process: _WindowsTestProcessHandle | None = None
            try:
                with self.assertRaises(VerificationOutputCaptureError):
                    run_unittest(ws, timeout=5, output_limit_bytes=1024)
                self.assertLess(time.monotonic() - started, 4.0)
                self.assertTrue(pid_file.is_file(), "子进程必须已报告测试 PID")
                child_process = observer.wait_for_process(0.5)
                self.assertTrue(
                    child_process.exited_within(0.5),
                    "验证器退出后仍持有输出管道的后代必须被回收",
                )
            finally:
                try:
                    observer.close()
                finally:
                    if child_process is None:
                        child_process = observer.process_handle
                    if child_process is not None:
                        try:
                            child_process.terminate_for_test_cleanup()
                        finally:
                            child_process.close()

    @unittest.skipUnless(os.name == "nt", "Windows 超时后的同步 pipe read 取消")
    def test_windows_验证超时且后代持管道时有界终止(self) -> None:
        from subprocess import TimeoutExpired

        from icode.runner import VerificationOutputCaptureError

        with temp_workspace() as ws:
            pid_file = ws / "windows-timeout-child.pid"
            acknowledged_file = ws / "windows-timeout-child-handle-captured"
            child_code = _windows_child_identity_writer(
                pid_file, "import time\ntime.sleep(30.0)\n",
            )
            (ws / "test_windows_timeout_child.py").write_text(
                "import subprocess, sys, time, unittest\n"
                "class WindowsTimeoutChildTest(unittest.TestCase):\n"
                "    def test_background_child(self):\n"
                f"        subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                "stdout=sys.stdout, stderr=sys.stderr)\n"
                f"        for _ in range(200):\n            if __import__('pathlib').Path({str(acknowledged_file)!r}).is_file(): break\n"
                "            time.sleep(0.01)\n"
                "        else:\n            raise AssertionError('child handle was not captured')\n"
                "        time.sleep(10)\n",
                encoding="utf-8",
            )

            started = time.monotonic()
            observer = _WindowsTestProcessObserver(pid_file, acknowledged_file)
            observer.start()
            child_process: _WindowsTestProcessHandle | None = None
            try:
                with self.assertRaises((TimeoutExpired, VerificationOutputCaptureError)):
                    run_unittest(ws, timeout=5, output_limit_bytes=1024)
                self.assertLess(time.monotonic() - started, 7.0)
                self.assertTrue(pid_file.is_file(), "子进程必须已报告测试 PID")
                child_process = observer.wait_for_process(0.5)
                self.assertTrue(
                    child_process.exited_within(0.5),
                    "验证器超时必须通过 Job 回收仍持有输出管道的后代",
                )
            finally:
                try:
                    observer.close()
                finally:
                    if child_process is None:
                        child_process = observer.process_handle
                    if child_process is not None:
                        try:
                            child_process.terminate_for_test_cleanup()
                        finally:
                            child_process.close()

    @unittest.skipUnless(os.name == "nt", "Windows CREATE_SUSPENDED/Job Object 启动顺序")
    def test_windows_Job分配失败时payload不会启动(self) -> None:
        from icode.runner import VerificationOutputCaptureError
        from icode.windows_process_tree import WindowsProcessTree

        with temp_workspace() as ws:
            marker = ws / "payload-started"
            (ws / "test_payload_start.py").write_text(
                "import unittest\n"
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('started')\n"
                "class PayloadStartTest(unittest.TestCase):\n"
                "    def test_payload_loaded(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )

            with mock.patch.object(
                WindowsProcessTree, "assign_and_resume",
                side_effect=OSError("injected Job assignment failure"),
            ):
                with self.assertRaises(VerificationOutputCaptureError):
                    run_unittest(ws, timeout=5, output_limit_bytes=1024)

            self.assertFalse(marker.exists(), "Job 分配失败时 Python payload 不得执行")

    def test_双流持续输出超过预算时持续排空且显式拒绝(self) -> None:
        from icode.runner import VerificationOutputLimitError

        with temp_workspace() as ws:
            (ws / "test_output.py").write_text(
                "import sys, unittest\n"
                "class OutputTest(unittest.TestCase):\n"
                "    def test_output(self):\n"
                "        for _ in range(256):\n"
                "            sys.stdout.write('O' * 4096)\n"
                "            sys.stderr.write('E' * 4096)\n"
                "            sys.stdout.flush()\n"
                "            sys.stderr.flush()\n"
                "        sys.stdout.write('\\n')\n"
                "        sys.stderr.write('\\n')\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(VerificationOutputLimitError, "超过安全上限"):
                run_unittest(ws, timeout=15, output_limit_bytes=1024)

    def test_指定沙箱会包裹独立测试命令(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        class _RecordingSandbox:
            name = "recording"
            is_real_isolation = True

            def __init__(self):
                self.calls = []

            def wrap(self, argv, *, workspace, network=False):
                self.calls.append((list(argv), workspace, network))
                return ["sandbox-wrapper", *argv]

        sandbox = _RecordingSandbox()
        with temp_workspace() as ws:
            with mock.patch(
                "icode.runner.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="OK", stderr=""),
            ) as run:
                code, output = run_unittest(ws, sandbox=sandbox)

        self.assertEqual((code, output), (0, "OK"))
        self.assertEqual(len(sandbox.calls), 1)
        argv, workspace, network = sandbox.calls[0]
        self.assertEqual(argv, [sys.executable, "-B", "-m", "unittest"])
        self.assertEqual(workspace, ws)
        self.assertFalse(network)
        self.assertEqual(run.call_args.args[0], ["sandbox-wrapper", *argv])

    @unittest.skipUnless(
        sys.platform.startswith("linux") and shutil.which("bwrap"),
        "需要 Linux bubblewrap 原生隔离",
    )
    def test_bwrap验证器不能读取工作区外文件(self) -> None:
        from icode.isolation import BubblewrapSandbox

        with temp_workspace() as parent:
            workspace = parent / "workspace"
            workspace.mkdir()
            private_file = parent / "private.txt"
            private_file.write_text("outside-workspace-sentinel", encoding="utf-8")
            (workspace / "test_boundary.py").write_text(
                "import unittest\n"
                "class BoundaryTest(unittest.TestCase):\n"
                "    def test_private_file_is_unavailable(self):\n"
                f"        with self.assertRaises(OSError): open({str(private_file)!r}, 'rb')\n",
                encoding="utf-8",
            )

            code, output = run_unittest(workspace, sandbox=BubblewrapSandbox())

        self.assertEqual(code, 0, output[-800:])
        self.assertIn("OK", output)
        self.assertNotIn("outside-workspace-sentinel", output)


class TestAutoPersist(unittest.TestCase):
    """"模型文本产出 → 运行时落盘"通道：内容必须来自模型，且诚实标注来源。"""

    def test_提取JSON并落盘(self) -> None:
        from icode.runner import _extract_json, _persist_missing_from_response

        text = (
            "审查结论如下：\n"
            '```json\n{"round": 1, "new_issues": ["计划缺测试计划"],'
            ' "refuted_issues": [], "pending_verification": []}\n```\n'
        )
        data = _extract_json(text)
        self.assertEqual(data["round"], 1)
        self.assertEqual(data["new_issues"], ["计划缺测试计划"])

        with temp_workspace() as ws:
            out = ws / "t"
            out.mkdir()
            report = _FakeReport()
            from icode.contracts import _to_contract

            contract = _to_contract("review", {"outputs": [
                {"id": "review", "kind": "ticket_file", "value": "review_round_1.json",
                 "required": True}]})
            persisted = _persist_missing_from_response(out, contract, report, text)
            self.assertEqual(len(persisted), 1)
            self.assertIn("JSON 提取", persisted[0])
            got = json.loads((out / "review_round_1.json").read_text(encoding="utf-8"))
            self.assertEqual(got["round"], 1)

    def test_Markdown产物带来源标注(self) -> None:
        from icode.runner import AUTOPERSIST_HEADER, _persist_missing_from_response
        from icode.contracts import _to_contract

        with temp_workspace() as ws:
            out = ws / "t"
            out.mkdir()
            report = _FakeReport()
            contract = _to_contract("plan", {"outputs": [
                {"id": "plan", "kind": "ticket_file", "value": "01_plan.md",
                 "required": True}]})
            text = "# 计划\n\n内容足够长。" * 10
            persisted = _persist_missing_from_response(out, contract, report, text)
            self.assertEqual(len(persisted), 1)
            body = (out / "01_plan.md").read_text(encoding="utf-8")
            self.assertTrue(body.startswith(AUTOPERSIST_HEADER.split("\n")[0][:20]))
            self.assertIn("# 计划", body)

    def test_策略会话的文本补落盘也经过合同端口(self) -> None:
        from icode.artifact_broker import ArtifactBroker
        from icode.contracts import _to_contract
        from icode.runner import _persist_missing_from_response

        with temp_workspace() as ws:
            out = ws / "ticket"
            out.mkdir()
            contract = _to_contract("plan", {"outputs": [
                {"id": "plan", "kind": "ticket_file", "value": "01_plan.md",
                 "required": True},
            ]})
            broker = ArtifactBroker(out, contract, max_bytes=1024)
            persisted = _persist_missing_from_response(
                out, contract, _FakeReport(), "# 计划\n" * 4,
                artifact_broker=broker,
            )
            self.assertEqual(len(persisted), 1)
            self.assertTrue((out / "01_plan.md").is_file())

    def test_符号链接不能冒充已登记的工单产物(self) -> None:
        from icode.contracts import _to_contract
        from icode.runner import StepReport, _register_outputs

        class RejectArtifactCall:
            def artifact(self, *args, **kwargs):
                raise AssertionError("符号链接不可登记")

        with temp_workspace() as ws:
            out = ws / "ticket"
            out.mkdir()
            outside = ws / "outside.md"
            outside.write_text("untrusted", encoding="utf-8")
            try:
                (out / "01_plan.md").symlink_to(outside)
            except OSError:
                self.skipTest("当前账户无法创建符号链接")
            contract = _to_contract("plan", {"outputs": [
                {"id": "plan", "kind": "ticket_file", "value": "01_plan.md",
                 "required": True},
            ]})
            report = StepReport(step="plan", ok=False, out_dir=str(out))
            missing = _register_outputs(
                RejectArtifactCall(), out, "plan", "attempt", "ticket", contract, report,
            )
            self.assertEqual(missing, ["01_plan.md"])

    def test_提取不到JSON时诚实保持缺失(self) -> None:
        from icode.runner import _persist_missing_from_response
        from icode.contracts import _to_contract

        with temp_workspace() as ws:
            out = ws / "t"
            out.mkdir()
            report = _FakeReport()
            contract = _to_contract("review", {"outputs": [
                {"id": "r", "kind": "ticket_file", "value": "review_round_1.json",
                 "required": True}]})
            persisted = _persist_missing_from_response(
                out, contract, report, "没有 JSON 对象的纯文本回复，" + "这段回复足够长以通过最短长度检查。" * 6)
            self.assertEqual(persisted, [], "提取不到 JSON 不得伪造")
            self.assertTrue(any("未提取到" in w for w in report.warnings))

    def test_已有产物不覆盖(self) -> None:
        from icode.runner import _persist_missing_from_response
        from icode.contracts import _to_contract

        with temp_workspace() as ws:
            out = ws / "t"
            out.mkdir()
            (out / "01_plan.md").write_text("模型自己写的", encoding="utf-8")
            report = _FakeReport()
            contract = _to_contract("plan", {"outputs": [
                {"id": "plan", "kind": "ticket_file", "value": "01_plan.md",
                 "required": True}]})
            persisted = _persist_missing_from_response(out, contract, report, "长文本" * 100)
            self.assertEqual(persisted, [], "已有产物不得覆盖")
            self.assertEqual((out / "01_plan.md").read_text(encoding="utf-8"), "模型自己写的")


class _FakeReport:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def warn(self, text: str) -> None:
        self.warnings.append(text)


class TestBackendFactory(unittest.TestCase):
    def test_fake_后端无需密钥(self) -> None:
        b = build_backend("fake")
        self.assertEqual(getattr(b, "name", ""), "fake")
        msg = b.complete([{"role": "user", "content": "hi"}])
        self.assertTrue(msg.content)

    def test_真模型后端缺密钥时报可读错误(self) -> None:
        import os
        from unittest import mock

        from icode import config as cfg
        from icode.config import ConfigError

        saved = {k: os.environ.pop(k, None) for k in ("ICODE_LLM_API_KEY", "ICODE_LLM_KEY_FILE")}
        try:
            # 同时屏蔽本地 icode.local.toml，确保"无任何密钥来源"这一前提成立
            with mock.patch.object(cfg, "_load_local_config", return_value={}):
                with self.assertRaises(ConfigError):
                    build_backend("openai-compatible")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_未知后端名报错(self) -> None:
        with self.assertRaises(BackendError):
            build_backend("gpt-from-mars")

    def test_剥离思考标签(self) -> None:
        from icode.backends import strip_think

        self.assertEqual(strip_think("<think>内部推理</think>\n结果"), "结果")

    def test_usage_合并(self) -> None:
        a = Usage(total_tokens=10, prompt_tokens=6, completion_tokens=4)
        b = Usage(total_tokens=5, prompt_tokens=3, completion_tokens=2, calls=2)
        m = a.merge(b)
        self.assertEqual(m.total_tokens, 15)
        self.assertEqual(m.calls, 3)

    def test_空密钥直接拒绝(self) -> None:
        with self.assertRaises(BackendError):
            OpenAICompatibleBackend(api_key="")


class TestProxyStrategy(unittest.TestCase):
    """代理策略：默认跟随环境，但必须能显式绕过（托管环境的隧道代理会 502）。"""

    def test_默认跟随环境(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        self.assertFalse(b.no_proxy)
        self.assertIsNone(b.proxy)
        with mock.patch("urllib.request.getproxies", return_value={}):
            self.assertEqual(b.active_proxy(), "无")
        with mock.patch("urllib.request.getproxies", return_value={"https": "http://env.invalid:1"}):
            self.assertEqual(b.active_proxy(), "已配置（环境代理）")

    def test_强制直连时描述明确(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", no_proxy=True)
        self.assertEqual(b.active_proxy(), "禁用（强制直连）")

    def test_显式代理优先于环境(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", proxy="http://127.0.0.1:1")
        with mock.patch("urllib.request.getproxies", return_value={"https": "http://env.invalid:1"}):
            self.assertEqual(b.active_proxy(), "已配置（显式代理）")

    def test_直连时代理映射为空(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", no_proxy=True)
        self.assertEqual(b._proxy_mapping(), {}, "强制直连必须得到空代理映射")

    def test_显式代理映射只含该代理(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", proxy="http://127.0.0.1:1")
        self.assertEqual(b._proxy_mapping(),
                         {"http": "http://127.0.0.1:1", "https": "http://127.0.0.1:1"})

    def test_默认跟随环境代理(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        import urllib.request

        mapping = {"https": "http://env.invalid:1"}
        with mock.patch.object(urllib.request, "getproxies", return_value=mapping):
            self.assertEqual(b._proxy_mapping(), mapping)

    def test_opener_可构造且不改状态(self) -> None:
        with mock.patch("urllib.request.getproxies", return_value={}):
            for kwargs in ({}, {"no_proxy": True}, {"proxy": "http://127.0.0.1:1"}):
                backend = OpenAICompatibleBackend(api_key="k", **kwargs)  # type: ignore[arg-type]
                before = (backend.proxy, backend.no_proxy)
                opener = backend._opener()
                self.assertTrue(hasattr(opener, "open"))
                self.assertEqual((backend.proxy, backend.no_proxy), before)

    def test_代理失败时给出可执行提示(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        with mock.patch("urllib.request.getproxies", return_value={"https": "http://env.invalid:1"}):
            hint = b._proxy_hint(RuntimeError())
        self.assertIn("--no-proxy", hint)
        self.assertIn("ICODE_LLM_NO_PROXY=1", hint)

    def test_已显式配置时不再提示(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", no_proxy=True)
        self.assertEqual(b._proxy_hint(RuntimeError("502 Bad Gateway")), "")

    def test_环境变量可强制直连(self) -> None:
        import os

        from icode.config import llm_no_proxy

        saved = os.environ.get("ICODE_LLM_NO_PROXY")
        try:
            os.environ["ICODE_LLM_NO_PROXY"] = "1"
            self.assertTrue(llm_no_proxy())
            os.environ["ICODE_LLM_NO_PROXY"] = "0"
            self.assertFalse(llm_no_proxy())
        finally:
            if saved is None:
                os.environ.pop("ICODE_LLM_NO_PROXY", None)
            else:
                os.environ["ICODE_LLM_NO_PROXY"] = saved


class TestBackendRetry(unittest.TestCase):
    """模型调用是只读动作：传输类失败可自动重试；4xx 属确定性失败，绝不重试。"""

    def test_可重试状态码(self) -> None:
        for code in (408, 425, 429, 500, 502, 503, 504):
            self.assertTrue(OpenAICompatibleBackend._retryable_http(code), code)
        for code in (400, 401, 403, 404, 422):
            self.assertFalse(OpenAICompatibleBackend._retryable_http(code), code)

    def test_超时与连接错误可重试(self) -> None:
        self.assertTrue(OpenAICompatibleBackend._retryable_exc(TimeoutError("read timed out")))
        self.assertTrue(OpenAICompatibleBackend._retryable_exc(
            __import__("urllib.error", fromlist=["URLError"]).URLError("boom")))
        self.assertFalse(OpenAICompatibleBackend._retryable_exc(ValueError("逻辑错误")))

    def _ok_response(self):
        import json as _json

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return _json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        return _Resp()

    def test_required_tool_choice透传到兼容API(self) -> None:
        import json as _json
        from unittest import mock

        captured: list[dict] = []

        class _Opener:
            def open(self, req, timeout=None):
                captured.append(_json.loads(req.data.decode("utf-8")))
                return TestBackendRetry._ok_response(self)

        b = OpenAICompatibleBackend(api_key="k", max_retries=0)
        with mock.patch.object(b, "_opener", return_value=_Opener()):
            b.complete(
                [{"role": "user", "content": "review"}],
                tools=[{"type": "function", "function": {"name": "submit_review"}}],
                tool_choice="required",
            )

        self.assertEqual(captured[0]["tool_choice"], "required")

    def test_named_tool_choice转换为函数选择对象(self) -> None:
        import json as _json
        from unittest import mock

        captured: list[dict] = []

        class _Opener:
            def open(self, req, timeout=None):
                captured.append(_json.loads(req.data.decode("utf-8")))
                return TestBackendRetry._ok_response(self)

        b = OpenAICompatibleBackend(api_key="k", max_retries=0)
        with mock.patch.object(b, "_opener", return_value=_Opener()):
            b.complete(
                [{"role": "user", "content": "review"}],
                tools=[{"type": "function", "function": {"name": "submit_review"}}],
                tool_choice="submit_review",
            )

        self.assertEqual(captured[0]["tool_choice"], {
            "type": "function", "function": {"name": "submit_review"},
        })

    def test_首次超时后重试成功(self) -> None:
        from unittest import mock

        calls: list[int] = []

        class _Opener:
            def open(self, req, timeout=None):
                calls.append(1)
                if len(calls) == 1:
                    raise TimeoutError("The read operation timed out")
                return NONE_RESP

        NONE_RESP = self._ok_response()
        b = OpenAICompatibleBackend(api_key="k", max_retries=2, retry_backoff=0)
        with mock.patch.object(b, "_opener", return_value=_Opener()):
            msg = b.complete([{"role": "user", "content": "x"}])
        self.assertEqual(msg.content, "ok")
        self.assertEqual(b.usage.retries, 1)
        self.assertEqual(len(calls), 2, "应当重试一次")

    def test_重试耗尽报可读错误(self) -> None:
        from unittest import mock

        class _Opener:
            def open(self, req, timeout=None):
                raise TimeoutError("The read operation timed out")

        b = OpenAICompatibleBackend(api_key="k", max_retries=1, retry_backoff=0)
        with mock.patch.object(b, "_opener", return_value=_Opener()):
            with self.assertRaises(BackendError) as ctx:
                b.complete([{"role": "user", "content": "x"}])
        self.assertIn("TimeoutError", str(ctx.exception))
        self.assertEqual(b.usage.retries, 1)

    def test_401_不重试(self) -> None:
        import urllib.error
        from unittest import mock

        calls: list[int] = []

        class _Opener:
            def open(self, req, timeout=None):
                calls.append(1)
                raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

        b = OpenAICompatibleBackend(api_key="k", max_retries=3, retry_backoff=0)
        with mock.patch.object(b, "_opener", return_value=_Opener()):
            with self.assertRaises(BackendError) as ctx:
                b.complete([{"role": "user", "content": "x"}])
        self.assertIn("401", str(ctx.exception))
        self.assertEqual(len(calls), 1, "401 是确定性失败，不得重试")
        self.assertEqual(b.usage.retries, 0)


class TestTaskVerificationEvidence(unittest.TestCase):
    """R3：run_task 的独立测试回执必须绑定到证据，模型自述不算。"""

    def test缺少验证证据时其他所有阶段通过也不能报告任务成功(self) -> None:
        from types import SimpleNamespace

        from icode.runner import TaskReport
        from icode.self_verify import VerificationEvidence

        report_without_evidence = TaskReport(
            task="missing evidence", workspace="/unused", exit_code=0,
            test_output="", loop=SimpleNamespace(ok=True),
            reviewer_loop=SimpleNamespace(ok=True), changed_files=["source.py"],
            review=SimpleNamespace(ok=True, model_reviewed=True),
        )
        report_with_failed_evidence = TaskReport(
            task="mismatched evidence", workspace="/unused", exit_code=0,
            test_output="", loop=SimpleNamespace(ok=True),
            reviewer_loop=SimpleNamespace(ok=True), changed_files=["source.py"],
            review=SimpleNamespace(ok=True, model_reviewed=True),
            verification=VerificationEvidence(
                step="task", attempt="1", exit_code=1,
            ),
        )
        report_with_unpassed_evidence = TaskReport(
            task="unpassed evidence", workspace="/unused", exit_code=0,
            test_output="", loop=SimpleNamespace(ok=True),
            reviewer_loop=SimpleNamespace(ok=True), changed_files=["source.py"],
            review=SimpleNamespace(ok=True, model_reviewed=True),
                verification=VerificationEvidence(
                step="task", attempt="1", exit_code=0,
                category="side_effect_unknown",
            ),
        )

        self.assertFalse(report_without_evidence.ok)
        self.assertFalse(report_with_failed_evidence.ok)
        self.assertFalse(report_with_unpassed_evidence.ok)

    def test_独立测试回执绑定到证据(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import run_task

        settings = require_skill()
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            # 不改动文件：基线测试通过 → exit_code=0
            report = run_task(
                settings, backend=FakeBackend(["完成"]), workspace=dst,
            )
            self.assertIsNotNone(report.verification)
            evidence = report.verification
            self.assertEqual(evidence.step, "task")
            self.assertEqual(evidence.kind, "test")
            self.assertEqual(evidence.command, ("python", "-B", "-m", "unittest"))
            self.assertEqual(evidence.exit_code, 0)
            self.assertTrue(evidence.passed)
            self.assertTrue(evidence.environment_fingerprint)
            self.assertTrue(evidence.output_sha256)
            # 改动为空 → 无产物哈希，但仍绑定环境指纹
            self.assertEqual(dict(evidence.artifact_hashes), {})

    def test_run_task把同一沙箱交给独立验证器(self) -> None:
        from unittest import mock

        from icode.backends import FakeBackend
        from icode.isolation import NoIsolation
        from icode.runner import run_task

        settings = require_skill()
        sandbox = NoIsolation(reason="测试显式沙箱传递")
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            with mock.patch("icode.runner.run_unittest", return_value=(0, "OK")) as verify:
                run_task(
                    settings, backend=FakeBackend(["完成"]), workspace=dst,
                    sandbox=sandbox,
                )

        self.assertIs(verify.call_args.kwargs["sandbox"], sandbox)

    def test_破坏性改动产生带哈希与分类的证据(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import run_task

        settings = require_skill()
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            # 模拟模型在工作区内把 calc.py 改坏（通过工具，而非直接改文件）
            calc_path = str(dst / "calc.py")
            script = [
                {"content": "", "tool_calls": [
                    {"id": "break-calc", "name": "write_file",
                     "arguments": {"path": calc_path,
                                   "content": "raise RuntimeError('boom')\n"}}
                ]},
                "完成",
            ]
            report = run_task(
                settings, backend=FakeBackend(script), workspace=dst,
            )
            evidence = report.verification
            self.assertIsNotNone(evidence)
            self.assertNotEqual(evidence.exit_code, 0)
            self.assertFalse(evidence.passed)
            from icode.self_verify import FAILURE_CODE

            self.assertEqual(evidence.category, FAILURE_CODE)
            self.assertIn("calc.py", evidence.artifact_hashes)
            self.assertEqual(len(evidence.artifact_hashes["calc.py"]), 64)
            self.assertTrue(evidence.environment_fingerprint)


class TestReviewStepReadOnlyContext(unittest.TestCase):
    """R3 Reviewer 在独立上下文中只能读源码、提交审查产物。"""

    def test_review阶段无隔离沙箱时命令在启动前拒绝且不产生标记(self) -> None:
        import subprocess
        from types import SimpleNamespace
        from unittest.mock import patch

        from icode.backends import FakeBackend
        from icode.contracts import ContractSet
        from icode.handshake import next_out_dir
        from icode.isolation import NoIsolation
        from icode.runner import _run_agent

        settings = require_skill()
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            workspace_marker = workspace / "review-command-started.txt"
            outside_marker = root / "outside-review-command-started.txt"
            out_dir = next_out_dir(workspace)
            command_code = (
                "("
                f"__import__('pathlib').Path({str(workspace_marker)!r})"
                ".write_text('started'),"
                f"__import__('pathlib').Path({str(outside_marker)!r})"
                ".write_text('started')"
                ")"
            )
            contract = ContractSet.load(settings.gates_json).step("review")
            backend = FakeBackend([
                {"content": "", "tool_calls": [
                    {"id": "review-command", "name": "run_command", "arguments": {
                        "argv": ["python", "-c", command_code],
                    }},
                    {"id": "submit-review", "name": "submit_artifact", "arguments": {
                        "name": "02_review.md", "content": "# Review\n\nNo findings.\n",
                    }},
                ]},
                "审查产物已提交",
            ])

            class _Operations:
                def start(self, **_kwargs):
                    return SimpleNamespace(can_execute=True, attempt="attempt-1", detail="")

                def finish(self, *_args, **_kwargs):
                    return True

            with patch("subprocess.run", wraps=subprocess.run) as process_run:
                report = _run_agent(
                    backend=backend,
                    workspace=workspace,
                    out_dir=out_dir,
                    ticket_id="REVIEW-NO-ISOLATION",
                    step="review",
                    brief="Review without changing source or running unisolated commands.",
                    contract=contract,
                    requirement="Do not start a Reviewer command without OS isolation.",
                    approver=None,
                    loop_config=None,
                    budget=None,
                    on_event=None,
                    sandbox=NoIsolation(reason="Windows Reviewer boundary integration test"),
                    operations=_Operations(),
                )

        command_call, submit_call = report.turns[0].invocations
        self.assertEqual(command_call.name, "run_command")
        self.assertEqual(command_call.decision, "allow")
        self.assertFalse(command_call.result.ok)
        self.assertEqual(command_call.result.meta.get("error"), "isolation_unavailable")
        self.assertIs(command_call.result.meta.get("payload_started"), False)
        self.assertEqual(process_run.call_count, 0, "未通过 OS 隔离时不得启动命令")
        self.assertFalse(workspace_marker.exists())
        self.assertFalse(outside_marker.exists())
        self.assertTrue(submit_call.result.ok, submit_call.result.content)

    def test_review阶段源码写入被拒绝且审查产物仍可提交(self) -> None:
        from types import SimpleNamespace

        from icode.backends import FakeBackend
        from icode.contracts import ContractSet
        from icode.handshake import next_out_dir
        from icode.isolation import NoIsolation
        from icode.runner import _run_agent

        settings = require_skill()
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            source = workspace / "calc.py"
            source.write_text("ORIGINAL = True\n", encoding="utf-8")
            out_dir = next_out_dir(workspace)
            (out_dir / "01_plan.md").write_text("Plan input\n", encoding="utf-8")
            private_ledger = out_dir / ".ico_metadata.json"
            private_ledger.write_text("REVIEW_LEDGER_SECRET\n", encoding="utf-8")
            contract = ContractSet.load(settings.gates_json).step("review")
            backend = FakeBackend([
                {"content": "", "tool_calls": [
                    {"id": "modify-source", "name": "write_file",
                     "arguments": {"path": str(source), "content": "ORIGINAL = False\n"}},
                    {"id": "read-ledger", "name": "read_file",
                     "arguments": {"path": str(private_ledger)}},
                    {"id": "read-approved-plan", "name": "read_artifact",
                     "arguments": {"name": "01_plan.md"}},
                    {"id": "glob-ledger", "name": "glob",
                     "arguments": {"pattern": ".icode_output/**/*"}},
                    {"id": "grep-ledger", "name": "grep",
                     "arguments": {"pattern": "REVIEW_LEDGER_SECRET", "path": "."}},
                    {"id": "submit-review", "name": "submit_artifact",
                     "arguments": {"name": "02_review.md", "content": "# Review\n\nNo findings.\n"}},
                ]},
                "审查产物已提交",
            ])

            class _Operations:
                def start(self, **_kwargs):
                    return SimpleNamespace(can_execute=True, attempt="attempt-1", detail="")

                def finish(self, *_args, **_kwargs):
                    return True

            report = _run_agent(
                backend=backend, workspace=workspace, out_dir=out_dir,
                ticket_id="REVIEW-READONLY-1", step="review", brief="Review the plan.",
                contract=contract, requirement="Review without modifying source.",
                approver=None, loop_config=None, budget=None, on_event=None,
                sandbox=NoIsolation(), operations=_Operations(),
            )
            self.assertEqual(source.read_text(encoding="utf-8"), "ORIGINAL = True\n")
            self.assertEqual((out_dir / "02_review.md").read_text(encoding="utf-8"),
                             "# Review\n\nNo findings.\n")

        invocations = report.turns[0].invocations
        self.assertEqual(invocations[0].decision, "deny")
        self.assertEqual(invocations[0].result.meta.get("error"), "denied")
        self.assertEqual(invocations[1].decision, "deny")
        self.assertNotIn("REVIEW_LEDGER_SECRET", invocations[1].result.content)
        self.assertTrue(invocations[2].result.ok, invocations[2].result.content)
        self.assertIn("Plan input", invocations[2].result.content)
        self.assertTrue(invocations[3].result.ok)
        self.assertNotIn(".ico_metadata.json", invocations[3].result.content)
        self.assertTrue(invocations[4].result.ok)
        self.assertEqual(invocations[4].result.meta.get("hits"), 0)
        self.assertNotIn(":1: REVIEW_LEDGER_SECRET", invocations[4].result.content)
        self.assertTrue(invocations[5].result.ok, invocations[5].result.content)
        system_prompt = backend.calls[0]["messages"][0]["content"]
        self.assertIn("只读独立审查", system_prompt)
        self.assertIn("run_command", system_prompt)

    def test_策略化review也拒绝源码写入(self) -> None:
        from types import SimpleNamespace

        from icode.backends import FakeBackend
        from icode.contracts import ContractSet
        from icode.isolation import NoIsolation
        from icode.runner import _run_agent
        from icode.sandbox_policy import NetworkMode, SandboxPolicy

        settings = require_skill()
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            source = workspace / "calc.py"
            source.write_text("ORIGINAL = True\n", encoding="utf-8")
            out_dir = workspace / "alternate-tickets" / "REVIEW-READONLY-2"
            out_dir.mkdir(parents=True)
            private_ledger = out_dir / ".ico_metadata.json"
            private_ledger.write_text("REVIEW_POLICY_LEDGER_SECRET\n", encoding="utf-8")
            contract = ContractSet.load(settings.gates_json).step("review")
            policy = SandboxPolicy(
                schema_version=1, run_id="review-policy", ticket_id="REVIEW-READONLY-2",
                step="review", workspace_root=workspace,
                read_roots=(workspace,), write_roots=(workspace,),
                deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=4096, protected_paths=(),
            )
            backend = FakeBackend([
                {"content": "", "tool_calls": [
                    {"id": "modify-source", "name": "write_file",
                     "arguments": {"path": str(source), "content": "ORIGINAL = False\n"}},
                    {"id": "read-ledger", "name": "read_file",
                     "arguments": {"path": str(private_ledger)}},
                    {"id": "submit-review", "name": "submit_artifact",
                     "arguments": {"name": "02_review.md", "content": "# Review\n\nNo findings.\n"}},
                ]},
                "审查产物已提交",
            ])

            class _Operations:
                def start(self, **_kwargs):
                    return SimpleNamespace(can_execute=True, attempt="attempt-1", detail="")

                def finish(self, *_args, **_kwargs):
                    return True

            report = _run_agent(
                backend=backend, workspace=workspace, out_dir=out_dir,
                ticket_id="REVIEW-READONLY-2", step="review", brief="Review the plan.",
                contract=contract, requirement="Review without modifying source.",
                approver=None, loop_config=None, budget=None, on_event=None,
                sandbox=NoIsolation(), operations=_Operations(), policy=policy,
            )
            self.assertEqual(source.read_text(encoding="utf-8"), "ORIGINAL = True\n")
            self.assertTrue((out_dir / "02_review.md").is_file())

        self.assertEqual(report.turns[0].invocations[0].decision, "deny")
        self.assertEqual(report.turns[0].invocations[1].decision, "deny")
        self.assertNotIn("REVIEW_POLICY_LEDGER_SECRET",
                         report.turns[0].invocations[1].result.content)
        self.assertTrue(report.turns[0].invocations[2].result.ok)

    @unittest.skipUnless(
        sys.platform.startswith("linux")
        and os.environ.get("ICODE_RUN_POLICY_REVIEWER_PROBE") == "1",
        "策略化 Reviewer runner 原生链路由 Linux CI 显式启用",
    )
    def test_bwrap策略化reviewer由runner派生策略并隐藏宿主账本(self) -> None:
        from types import SimpleNamespace

        from icode.backends import FakeBackend
        from icode.contracts import ContractSet
        from icode.handshake import next_out_dir
        from icode.isolation import BubblewrapSandbox
        from icode.runner import _run_agent
        from icode.sandbox_policy import (
            NetworkMode,
            SandboxPolicy,
            derive_read_only_reviewer_policy,
        )

        settings = require_skill()
        if not shutil.which("bwrap"):
            self.fail("策略化 Reviewer runner 探针要求 Bubblewrap 已安装")
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            source = workspace / "calc.py"
            source.write_text("ORIGINAL = True\n", encoding="utf-8")
            out_dir = next_out_dir(workspace)
            private_ledger = out_dir / ".ico_metadata.json"
            private_ledger.write_text("RUNNER_POLICY_LEDGER_SECRET\n", encoding="utf-8")
            contract = ContractSet.load(settings.gates_json).step("review")
            base_policy = SandboxPolicy(
                schema_version=1,
                run_id="review-runner-policy",
                ticket_id="REVIEW-RUNNER-POLICY",
                step="review",
                workspace_root=workspace,
                read_roots=(workspace,),
                write_roots=(workspace,),
                deny_read_roots=(),
                deny_write_roots=(),
                network_mode=NetworkMode.PROXY_ALLOWLIST,
                allowed_domains=("example.org",),
                process_limit=8,
                wall_timeout_seconds=20,
                output_limit_bytes=4096,
                protected_paths=(),
            )
            effective_policy = derive_read_only_reviewer_policy(
                base_policy,
                workspace_root=workspace,
                deny_read_roots=(workspace / ".icode_output", out_dir),
            )
            hidden_relative = private_ledger.relative_to(workspace).as_posix()
            probe_code = (
                "print('ledger-hidden' if not "
                f"__import__('pathlib').Path({hidden_relative!r}).exists() "
                "else 'ledger-visible')"
            )
            backend = FakeBackend([
                {"content": "", "tool_calls": [
                    {"id": "policy-probe", "name": "run_command", "arguments": {
                        "argv": ["python3", "-c", probe_code],
                    }},
                    {"id": "submit-review", "name": "submit_artifact", "arguments": {
                        "name": "02_review.md", "content": "# Review\n\nNo findings.\n",
                    }},
                ]},
                "策略化审查已完成",
            ])

            class _Operations:
                def start(self, **_kwargs):
                    return SimpleNamespace(can_execute=True, attempt="attempt-1", detail="")

                def finish(self, *_args, **_kwargs):
                    return True

            report = _run_agent(
                backend=backend,
                workspace=workspace,
                out_dir=out_dir,
                ticket_id="REVIEW-RUNNER-POLICY",
                step="review",
                brief="Review the current changes.",
                contract=contract,
                requirement="Keep the Reviewer read-only.",
                approver=None,
                loop_config=None,
                budget=None,
                on_event=None,
                sandbox=BubblewrapSandbox(),
                operations=_Operations(),
                policy=base_policy,
            )

            self.assertEqual(source.read_text(encoding="utf-8"), "ORIGINAL = True\n")
            self.assertEqual(
                private_ledger.read_text(encoding="utf-8"),
                "RUNNER_POLICY_LEDGER_SECRET\n",
            )
            self.assertEqual(
                (out_dir / "02_review.md").read_text(encoding="utf-8"),
                "# Review\n\nNo findings.\n",
            )

        invocations = report.turns[0].invocations
        command_result = invocations[0].result
        self.assertTrue(
            command_result.ok,
            f"decision={invocations[0].decision} note={invocations[0].note} "
            f"meta={command_result.meta} content={command_result.content}",
        )
        self.assertIn("ledger-hidden", command_result.content)
        self.assertNotIn("RUNNER_POLICY_LEDGER_SECRET", command_result.content)
        self.assertEqual(command_result.meta.get("policy_hash"), effective_policy.policy_hash)
        self.assertTrue(invocations[1].result.ok, invocations[1].result.content)


if __name__ == "__main__":
    unittest.main()
