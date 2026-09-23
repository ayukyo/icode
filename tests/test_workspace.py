"""跨进程工单租约测试。"""

from __future__ import annotations

import builtins
import errno
import hashlib
import json
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests._support import temp_workspace

from icode.workspace import TicketLease, WorkspaceBusyError, WorkspaceError


_CHILD_ACQUIRE = """
from pathlib import Path
import sys

from icode.workspace import TicketLease, WorkspaceBusyError, WorkspaceError

try:
    lease = TicketLease.acquire(
        Path(sys.argv[1]),
        project_id=sys.argv[2],
        ticket_id=sys.argv[3],
        run_id=sys.argv[4],
    )
except WorkspaceBusyError:
    print("busy")
except WorkspaceError:
    print("error")
else:
    print("acquired")
    lease.release()
"""


def _read_metadata(path: Path) -> dict:
    """跳过 Windows/POSIX 共用的 byte-0 锁区读取诊断元数据。"""
    with path.open("rb") as stream:
        stream.seek(1)
        return json.loads(stream.read().decode("utf-8"))


class _TrackingStream:
    """记录 truncate 后长度，并在零长度窗口模拟未加锁竞争者。"""

    def __init__(self, stream, observed_sizes: list[int]) -> None:
        self._stream = stream
        self._observed_sizes = observed_sizes

    def truncate(self, size: int | None = None) -> int:
        result = self._stream.truncate(size)
        actual_size = os.fstat(self._stream.fileno()).st_size
        self._observed_sizes.append(actual_size)
        if actual_size == 0:
            # POSIX advisory lock不会阻止未调用 flock 的竞争者写入；精确放大旧实现竞态。
            with builtins.open(self._stream.name, "r+b", buffering=0) as competitor:
                competitor.write(b"\0")
        return result

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


class _BlockingInitialWriteStream:
    """把首次锁字节写入暂停在精确可复现的初始化窗口。"""

    def __init__(
        self,
        stream,
        write_started: threading.Event,
        allow_write: threading.Event,
    ) -> None:
        self._stream = stream
        self._write_started = write_started
        self._allow_write = allow_write
        self._blocked = False

    def write(self, data: bytes) -> int:
        if not self._blocked and data == b"\0":
            self._blocked = True
            self._write_started.set()
            if not self._allow_write.wait(timeout=10):
                raise TimeoutError("test did not release initial write")
        return self._stream.write(data)

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


class TestTicketLease(unittest.TestCase):
    def setUp(self) -> None:
        self._workspace = temp_workspace()
        self.data_root = self._workspace.__enter__()

    def tearDown(self) -> None:
        self._workspace.__exit__(None, None, None)

    def _acquire_in_child(self, ticket_id: str, *, project_id: str = "project-1") -> str:
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[1] / "src")
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (source_root, existing) if part
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                _CHILD_ACQUIRE,
                str(self.data_root),
                project_id,
                ticket_id,
                "child-run",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        return completed.stdout.strip()

    def test_同一工程同一工单被第二进程拒绝(self) -> None:
        with TicketLease.acquire(
            self.data_root, "project-1", "ticket-1", "parent-run"
        ) as lease:
            expected = {
                "pid": os.getpid(),
                "project_id": "project-1",
                "run_id": "parent-run",
                "schema_version": 1,
                "ticket_id": "ticket-1",
            }
            self.assertEqual(_read_metadata(lease.path), expected)
            self.assertEqual(self._acquire_in_child("ticket-1"), "busy")
            self.assertEqual(_read_metadata(lease.path), expected)

    def test_不同工单可由两个进程同时持有(self) -> None:
        with TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run"):
            self.assertEqual(self._acquire_in_child("ticket-2"), "acquired")

    def test_首次并发初始化不会向竞争者暴露零长目标文件(self) -> None:
        write_started = threading.Event()
        allow_write = threading.Event()
        original_fdopen = os.fdopen
        first_open = True
        winner: dict[str, object] = {}

        def blocking_fdopen(*args, **kwargs):
            nonlocal first_open
            stream = original_fdopen(*args, **kwargs)
            if first_open:
                first_open = False
                return _BlockingInitialWriteStream(
                    stream, write_started, allow_write
                )
            return stream

        def acquire_winner() -> None:
            try:
                winner["lease"] = TicketLease.acquire(
                    self.data_root, "project-1", "ticket-1", "winner-run"
                )
            except Exception as exc:  # 测试线程必须把异常带回主线程
                winner["error"] = exc

        with mock.patch("icode.workspace.os.fdopen", side_effect=blocking_fdopen):
            thread = threading.Thread(target=acquire_winner)
            thread.start()
            self.assertTrue(write_started.wait(timeout=10))
            try:
                loser_result = self._acquire_in_child("ticket-1")
            finally:
                allow_write.set()
                thread.join(timeout=10)

        lease = winner.get("lease")
        if isinstance(lease, TicketLease):
            lease.release()
        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", winner)
        self.assertIn(loser_result, {"busy", "acquired"})
        self.assertIsInstance(lease, TicketLease)

    def test_release_后另一进程可重新获取(self) -> None:
        lease = TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run")
        lease.release()

        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_重复_release_安全(self) -> None:
        lease = TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run")
        lease.release()
        lease.release()

        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_锁路径只含工程与工单身份摘要(self) -> None:
        project_id = "../../untrusted-project"
        ticket_id = "nested/untrusted-ticket"
        expected_name = hashlib.sha256(
            project_id.encode("utf-8") + b"\0" + ticket_id.encode("utf-8")
        ).hexdigest()

        with TicketLease.acquire(
            self.data_root, project_id, ticket_id, "run-1"
        ) as lease:
            self.assertEqual(lease.path.name, expected_name)
            self.assertTrue(lease.path.is_relative_to(self.data_root))
            relative = str(lease.path.relative_to(self.data_root))
            self.assertNotIn(project_id, relative)
            self.assertNotIn(ticket_id, relative)

    def test_锁成功后写入稳定诊断元数据(self) -> None:
        with TicketLease.acquire(
            self.data_root, "project-1", "ticket-1", "run-1"
        ) as lease:
            metadata = _read_metadata(lease.path)

        self.assertEqual(
            metadata,
            {
                "pid": os.getpid(),
                "project_id": "project-1",
                "run_id": "run-1",
                "schema_version": 1,
                "ticket_id": "ticket-1",
            },
        )

    def test_元数据更新期间锁文件永不变为零长度(self) -> None:
        observed_sizes: list[int] = []
        original_path_open = Path.open
        original_fdopen = os.fdopen

        def tracked_path_open(path: Path, *args, **kwargs):
            return _TrackingStream(
                original_path_open(path, *args, **kwargs), observed_sizes
            )

        def tracked_fdopen(*args, **kwargs):
            return _TrackingStream(original_fdopen(*args, **kwargs), observed_sizes)

        with (
            mock.patch(
                "icode.workspace.Path.open",
                autospec=True,
                side_effect=tracked_path_open,
            ),
            mock.patch("icode.workspace.os.fdopen", side_effect=tracked_fdopen),
        ):
            lease = TicketLease.acquire(
                self.data_root, "project-1", "ticket-1", "parent-run"
            )
            lease.release()

        self.assertEqual(observed_sizes, [1])
        self.assertEqual(lease.path.read_bytes()[:1], b"\0")
        self.assertEqual(
            _read_metadata(lease.path),
            {
                "pid": os.getpid(),
                "project_id": "project-1",
                "run_id": "parent-run",
                "schema_version": 1,
                "ticket_id": "ticket-1",
            },
        )

    def test_拒绝空值_控制字符及不可编码字符串(self) -> None:
        invalid_values = ("", "line\nbreak", "delete\x7f", "surrogate\ud800")
        for field_index in range(3):
            for invalid in invalid_values:
                values = ["project-1", "ticket-1", "run-1"]
                values[field_index] = invalid
                with self.subTest(field=field_index, value=repr(invalid)):
                    with self.assertRaises(WorkspaceError):
                        TicketLease.acquire(self.data_root, *values)

    def test_初始化_fsync_异常后关闭句柄且后续可获取(self) -> None:
        with mock.patch("icode.workspace.os.fsync", side_effect=OSError("disk error")):
            with self.assertRaises(WorkspaceError):
                TicketLease.acquire(
                    self.data_root, "project-1", "ticket-1", "parent-run"
                )

        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_第二次_metadata_fsync_异常后关闭句柄并释放锁(self) -> None:
        metadata_error = OSError("metadata fsync error")
        with mock.patch(
            "icode.workspace.os.fsync",
            side_effect=(None, metadata_error),
        ) as fsync:
            with self.assertRaises(WorkspaceError) as caught:
                TicketLease.acquire(
                    self.data_root, "project-1", "ticket-1", "parent-run"
                )

        self.assertEqual(fsync.call_count, 2)
        self.assertIs(caught.exception.__cause__, metadata_error)
        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_遗留零长锁文件被占用时_busy_释放后安全恢复(self) -> None:
        lease = TicketLease.acquire(
            self.data_root, "project-1", "ticket-1", "seed-run"
        )
        path = lease.path
        lease.release()
        path.write_bytes(b"")

        with path.open("r+b") as legacy_stream:
            if os.name == "posix":
                import fcntl

                fcntl.flock(legacy_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif os.name == "nt":  # pragma: no cover - Windows CI
                import msvcrt

                legacy_stream.seek(0)
                msvcrt.locking(legacy_stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - 公开接口只支持 POSIX/Windows
                self.skipTest(f"unsupported platform: {os.name}")
            try:
                self.assertEqual(self._acquire_in_child("ticket-1"), "busy")
            finally:
                if os.name == "posix":
                    fcntl.flock(legacy_stream.fileno(), fcntl.LOCK_UN)
                else:  # pragma: no cover - Windows CI
                    legacy_stream.seek(0)
                    msvcrt.locking(legacy_stream.fileno(), msvcrt.LK_UNLCK, 1)

        with TicketLease.acquire(
            self.data_root, "project-1", "ticket-1", "recovery-run"
        ) as recovered:
            self.assertEqual(
                _read_metadata(recovered.path),
                {
                    "pid": os.getpid(),
                    "project_id": "project-1",
                    "run_id": "recovery-run",
                    "schema_version": 1,
                    "ticket_id": "ticket-1",
                },
            )

    @unittest.skipUnless(os.name == "posix", "POSIX flock errno contract")
    def test_flock_eio_统一为_workspace_error_而非_busy(self) -> None:
        lock_error = OSError(errno.EIO, "simulated lock I/O failure")
        with mock.patch("fcntl.flock", side_effect=lock_error):
            with self.assertRaises(WorkspaceError) as caught:
                TicketLease.acquire(
                    self.data_root, "project-1", "ticket-1", "parent-run"
                )

        self.assertNotIsInstance(caught.exception, WorkspaceBusyError)
        self.assertIs(caught.exception.__cause__, lock_error)

    def test_目录创建失败统一为_workspace_error(self) -> None:
        not_a_directory = self.data_root / "file"
        not_a_directory.write_text("occupied", encoding="utf-8")

        with self.assertRaises(WorkspaceError):
            TicketLease.acquire(not_a_directory, "project-1", "ticket-1", "run-1")


if __name__ == "__main__":
    unittest.main()
