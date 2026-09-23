"""跨进程工单租约测试。"""

from __future__ import annotations

import builtins
import errno
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import icode.workspace as workspace_module
from icode.sandbox_policy import NetworkMode
from icode.workspace import (
    WORKSPACE_SCHEMA_VERSION,
    TicketLease,
    WorkspaceBusyError,
    WorkspaceError,
    WorkspaceManager,
    WorkspaceSession,
    default_data_root,
)
from tests._support import temp_workspace

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

    def _acquire_in_child(
        self, ticket_id: str, *, project_id: str = "project-1"
    ) -> str:
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
                return _BlockingInitialWriteStream(stream, write_started, allow_write)
            return stream

        def acquire_winner() -> None:
            try:
                winner["lease"] = TicketLease.acquire(
                    self.data_root, "project-1", "ticket-1", "winner-run"
                )
            except Exception as exc:  # noqa: BLE001 - 测试线程必须回传任意异常
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
        lease = TicketLease.acquire(
            self.data_root, "project-1", "ticket-1", "parent-run"
        )
        lease.release()

        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_重复_release_安全(self) -> None:
        lease = TicketLease.acquire(
            self.data_root, "project-1", "ticket-1", "parent-run"
        )
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
                with (
                    self.subTest(field=field_index, value=repr(invalid)),
                    self.assertRaises(WorkspaceError),
                ):
                    TicketLease.acquire(self.data_root, *values)

    def test_初始化_fsync_异常后关闭句柄且后续可获取(self) -> None:
        with (
            mock.patch("icode.workspace.os.fsync", side_effect=OSError("disk error")),
            self.assertRaises(WorkspaceError),
        ):
            TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run")

        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_第二次_metadata_fsync_异常后关闭句柄并释放锁(self) -> None:
        metadata_error = OSError("metadata fsync error")
        with (
            mock.patch(
                "icode.workspace.os.fsync",
                side_effect=(None, metadata_error),
            ) as fsync,
            self.assertRaises(WorkspaceError) as caught,
        ):
            TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run")

        self.assertEqual(fsync.call_count, 2)
        self.assertIs(caught.exception.__cause__, metadata_error)
        self.assertEqual(self._acquire_in_child("ticket-1"), "acquired")

    def test_遗留零长锁文件被占用时_busy_释放后安全恢复(self) -> None:
        lease = TicketLease.acquire(self.data_root, "project-1", "ticket-1", "seed-run")
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
        with (
            mock.patch("fcntl.flock", side_effect=lock_error),
            self.assertRaises(WorkspaceError) as caught,
        ):
            TicketLease.acquire(self.data_root, "project-1", "ticket-1", "parent-run")

        self.assertNotIsInstance(caught.exception, WorkspaceBusyError)
        self.assertIs(caught.exception.__cause__, lock_error)

    def test_目录创建失败统一为_workspace_error(self) -> None:
        not_a_directory = self.data_root / "file"
        not_a_directory.write_text("occupied", encoding="utf-8")

        with self.assertRaises(WorkspaceError):
            TicketLease.acquire(not_a_directory, "project-1", "ticket-1", "run-1")

    @unittest.skipUnless(os.name == "posix", "POSIX inode safety contract")
    def test_锁文件拒绝symlink和hardlink且不修改victim(self) -> None:
        for link_kind in ("symlink", "hardlink"):
            with self.subTest(link_kind=link_kind):
                data_root = self.data_root / link_kind
                lease_dir = data_root / "ticket-leases"
                lease_dir.mkdir(parents=True)
                victim = data_root / "victim.txt"
                original = b"victim must remain unchanged"
                victim.write_bytes(original)
                digest = hashlib.sha256(b"project-1\0ticket-1").hexdigest()
                lock_path = lease_dir / digest
                if link_kind == "symlink":
                    lock_path.symlink_to(victim)
                else:
                    os.link(victim, lock_path)

                with self.assertRaises(WorkspaceError):
                    TicketLease.acquire(data_root, "project-1", "ticket-1", "run-1")

                self.assertEqual(victim.read_bytes(), original)
                with victim.open("r+b") as stream:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def test_lease目录拒绝symlink重定向(self) -> None:
        data_root = self.data_root / "lease-dir-link"
        data_root.mkdir()
        outside = self.data_root / "outside-leases"
        outside.mkdir()
        (data_root / "ticket-leases").symlink_to(outside, target_is_directory=True)

        with self.assertRaises(WorkspaceError):
            TicketLease.acquire(data_root, "project-1", "ticket-1", "run-1")

        self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(os.name == "posix", "POSIX private directory mode")
    def test_lease目录权限为仅当前用户可访问(self) -> None:
        with TicketLease.acquire(
            self.data_root, "project-1", "private-ticket", "run-1"
        ) as lease:
            mode = lease.path.parent.stat().st_mode & 0o777

        self.assertEqual(mode, 0o700)


def _run_git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _create_git_repository(root: Path) -> Path:
    repository = root / "source-repository"
    repository.mkdir()
    _run_git(repository, "init", "-q")
    _run_git(repository, "config", "user.name", "ICODE Test")
    _run_git(repository, "config", "user.email", "icode@example.invalid")
    (repository / "nested").mkdir()
    (repository / "nested" / "tracked.txt").write_text("source\n", encoding="utf-8")
    _run_git(repository, "add", ".")
    _run_git(repository, "commit", "-qm", "initial")
    return repository


class TestWorkspaceManager(unittest.TestCase):
    def setUp(self) -> None:
        self._workspace = temp_workspace()
        self.root = self._workspace.__enter__()
        self.data_root = self.root / "data"

    def tearDown(self) -> None:
        self._workspace.__exit__(None, None, None)

    def _snapshot_source(self, name: str = "source") -> Path:
        source = self.root / name
        source.mkdir()
        (source / "file.txt").write_text("snapshot\n", encoding="utf-8")
        (source / "directory").mkdir()
        (source / "directory" / "nested.bin").write_bytes(b"\x00\x01")
        return source

    def _ticket_root(self, project_id: str, ticket_id: str) -> Path:
        project_hash = hashlib.sha256(project_id.encode("utf-8")).hexdigest()
        ticket_hash = hashlib.sha256(ticket_id.encode("utf-8")).hexdigest()
        return self.data_root / "workspaces" / project_hash / ticket_hash

    def assert_lease_released(self, project_id: str, ticket_id: str) -> None:
        lease = TicketLease.acquire(
            self.data_root, project_id, ticket_id, "recovery-run"
        )
        lease.release()

    def test_git子目录创建detached工作树且不修改原工作树(self) -> None:
        repository = _create_git_repository(self.root)
        source = repository / "nested"
        (repository / "dirty.txt").write_text("untracked\n", encoding="utf-8")
        status_before = _run_git(repository, "status", "--porcelain=v1", "-uall")

        manager = WorkspaceManager(source, self.data_root, "../../project-secret")
        with manager.open("../ticket-secret", "run-1") as session:
            self.assertIsInstance(session, WorkspaceSession)
            self.assertEqual(session.kind, "git_worktree")
            self.assertEqual(
                _run_git(session.workspace_root, "rev-parse", "--abbrev-ref", "HEAD"),
                "HEAD",
            )
            self.assertEqual(
                _run_git(session.workspace_root, "rev-parse", "HEAD"),
                _run_git(repository, "rev-parse", "HEAD"),
            )
            self.assertEqual(
                _run_git(session.workspace_root, "status", "--porcelain=v1"), ""
            )
            checkout_file = session.workspace_root / "tracked.txt"
            checkout_file.write_text("changed in checkout\n", encoding="utf-8")
            self.assertEqual(
                (source / "tracked.txt").read_text(encoding="utf-8"), "source\n"
            )
            relative_ticket_root = str(
                session.manifest_path.parent.relative_to(self.data_root)
            )
            self.assertNotIn("project-secret", relative_ticket_root)
            self.assertNotIn("ticket-secret", relative_ticket_root)

        self.assertEqual(
            _run_git(repository, "status", "--porcelain=v1", "-uall"), status_before
        )
        with manager.open("../ticket-secret", "run-2") as reused:
            self.assertEqual(
                reused.workspace_root.joinpath("tracked.txt").read_text(
                    encoding="utf-8"
                ),
                "changed in checkout\n",
            )

    def test_git创建不执行post_checkout_hook且不等待sleep(self) -> None:
        repository = _create_git_repository(self.root)
        hooks = repository / ".githooks"
        hooks.mkdir()
        marker = repository / "hook-ran"
        hook = hooks / "post-checkout"
        hook.write_text(
            f"#!/bin/sh\nprintf ran > {marker}\nsleep 2\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        _run_git(repository, "config", "core.hooksPath", str(hooks))

        started = time.monotonic()
        with WorkspaceManager(repository, self.data_root, "project-1").open(
            "hook-ticket", "run-1"
        ):
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.5)
        self.assertFalse(marker.exists())

    def test_git安全物化不执行smudge_filter(self) -> None:
        repository = _create_git_repository(self.root)
        marker = repository / "filter-ran"
        filter_script = self.root / "evil-filter.sh"
        filter_script.write_text(
            f"#!/bin/sh\nprintf ran > {marker}\ntr 'a-z' 'A-Z'\n",
            encoding="utf-8",
        )
        filter_script.chmod(0o755)
        (repository / ".gitattributes").write_text(
            "filtered.txt filter=evil\n", encoding="utf-8"
        )
        (repository / "filtered.txt").write_text("lowercase\n", encoding="utf-8")
        _run_git(repository, "config", "filter.evil.smudge", str(filter_script))
        _run_git(repository, "config", "filter.evil.clean", "cat")
        _run_git(repository, "add", ".gitattributes", "filtered.txt")
        _run_git(repository, "commit", "-qm", "add filtered file")

        with WorkspaceManager(repository, self.data_root, "project-1").open(
            "filter-ticket", "run-1"
        ) as session:
            materialized = session.workspace_root.joinpath("filtered.txt").read_text(
                encoding="utf-8"
            )

        self.assertEqual(materialized, "lowercase\n")
        self.assertFalse(marker.exists())

    def test_git路径拒绝windows逃逸形态并安全映射到checkout(self) -> None:
        invalid_paths = (
            b"C:\\outside\\file.txt",
            b"..\\..\\outside.txt",
            b"directory\\file.txt",
            b"drive:C/file.txt",
            b"nul\x00file.txt",
            b"/absolute.txt",
            b"directory//file.txt",
            b"directory/./file.txt",
            b"directory/../file.txt",
        )
        for raw_path in invalid_paths:
            with (
                self.subTest(raw_path=raw_path),
                self.assertRaises(WorkspaceError),
            ):
                workspace_module._safe_git_relative_path(raw_path)

        checkout = self.root / "checkout"
        checkout.mkdir()
        relative = workspace_module._safe_git_relative_path(b"directory/file.txt")
        destination = workspace_module._safe_git_destination(checkout, relative)

        self.assertEqual(destination, checkout / "directory" / "file.txt")

    def test_git多个大blob使用单一batch流式物化(self) -> None:
        repository = _create_git_repository(self.root)
        expected: dict[str, bytes] = {}
        for index, byte in enumerate((b"a", b"b", b"c")):
            name = f"large-{index}.bin"
            content = byte * (2 * 1024 * 1024)
            repository.joinpath(name).write_bytes(content)
            expected[name] = content
        executable = repository / "executable.sh"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        _run_git(repository, "add", ".")
        _run_git(repository, "commit", "-qm", "add large blobs")

        original_popen = subprocess.Popen
        process_calls: list[tuple[tuple[str, ...], bool, bool, bool, bool]] = []

        def recording_popen(*args, **kwargs):
            command = tuple(args[0])
            environment = kwargs.get("env")
            process_calls.append(
                (
                    command,
                    kwargs.get("stdin") is subprocess.PIPE,
                    kwargs.get("stdout") is subprocess.PIPE,
                    kwargs.get("stderr") is subprocess.DEVNULL,
                    isinstance(environment, dict)
                    and not any(key.upper().startswith("GIT_") for key in environment),
                )
            )
            return original_popen(*args, **kwargs)

        with (
            mock.patch("icode.workspace.subprocess.Popen", side_effect=recording_popen),
            WorkspaceManager(repository, self.data_root, "project-1").open(
                "streamed-git-ticket", "run-1"
            ) as session,
        ):
            for name, content in expected.items():
                self.assertEqual(
                    session.workspace_root.joinpath(name).read_bytes(), content
                )
            self.assertTrue(
                session.workspace_root.joinpath("executable.sh").stat().st_mode & 0o111
            )
            self.assertEqual(
                _run_git(session.workspace_root, "write-tree"),
                _run_git(repository, "rev-parse", "HEAD^{tree}"),
            )

        cat_file_calls = [call for call in process_calls if "cat-file" in call[0]]
        self.assertEqual(len(cat_file_calls), 1, cat_file_calls)
        (
            command,
            stdin_is_pipe,
            stdout_is_pipe,
            stderr_discarded,
            git_environment_clean,
        ) = cat_file_calls[0]
        self.assertIn("--batch", command)
        self.assertTrue(stdin_is_pipe)
        self.assertTrue(stdout_is_pipe)
        self.assertTrue(stderr_discarded)
        self.assertTrue(git_environment_clean)
        self.assertFalse(any("hash-object" in call[0] for call in process_calls))

    def test_git三百小文件物化使用常数个子进程(self) -> None:
        repository = _create_git_repository(self.root)
        small_files = repository / "small-files"
        small_files.mkdir()
        for index in range(300):
            small_files.joinpath(f"file-{index:03d}.txt").write_text(
                f"content-{index}\n", encoding="utf-8"
            )
        _run_git(repository, "add", ".")
        _run_git(repository, "commit", "-qm", "add many small files")

        original_popen = subprocess.Popen
        process_commands: list[tuple[str, ...]] = []

        def recording_popen(*args, **kwargs):
            process_commands.append(tuple(args[0]))
            return original_popen(*args, **kwargs)

        with (
            mock.patch("icode.workspace.subprocess.Popen", side_effect=recording_popen),
            WorkspaceManager(repository, self.data_root, "project-1").open(
                "many-small-files-ticket", "run-1"
            ),
        ):
            pass

        self.assertLessEqual(len(process_commands), 16, process_commands)
        self.assertEqual(
            sum("cat-file" in command for command in process_commands),
            1,
            process_commands,
        )
        self.assertFalse(
            any("hash-object" in command for command in process_commands),
            process_commands,
        )

    def test_git_batch中途EOF和timeout清理partial并结束进程(self) -> None:
        class BatchOutput:
            def __init__(self, header: bytes, *, block: bool) -> None:
                self._header = header
                self._block = block
                self._read_count = 0
                self.released = threading.Event()

            def readline(self) -> bytes:
                header, self._header = self._header, b""
                return header

            def read(self, size: int) -> bytes:
                self._read_count += 1
                if self._read_count == 1:
                    return b"x" * min(10, size)
                if self._block:
                    self.released.wait(timeout=2)
                return b""

            def close(self) -> None:
                self.released.set()

        class FakeBatchProcess:
            def __init__(self, header: bytes, *, block: bool) -> None:
                self.stdin = io.BytesIO()
                self.stdout = BatchOutput(header, block=block)
                self.returncode: int | None = None
                self.killed = False
                self.terminated = False
                self.waited = False

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                self.waited = True
                if self.returncode is None:
                    self.returncode = 1
                return self.returncode

            def terminate(self) -> None:
                self.terminated = True
                self.returncode = -15
                self.stdout.released.set()

            def kill(self) -> None:
                self.killed = True
                self.returncode = -9
                self.stdout.released.set()

        content = b"x" * 100
        digest = hashlib.sha1(b"blob 100\0" + content).hexdigest()
        entry = workspace_module._GitTreeEntry(
            mode="100644",
            object_type="blob",
            object_id=digest,
            size=len(content),
            relative_path=workspace_module.PurePosixPath("partial.bin"),
        )
        identity = workspace_module._GitIdentity(
            top_level=self.root,
            common_dir=self.root,
            revision="0" * 40,
            relative_source=Path(),
        )

        for name, block, timeout_seconds in (
            ("eof", False, 5.0),
            ("timeout", True, 0.05),
        ):
            with self.subTest(name=name):
                checkout = self.root / f"batch-{name}"
                checkout.mkdir()
                process = FakeBatchProcess(
                    f"{digest} blob {len(content)}\n".encode("ascii"),
                    block=block,
                )
                with (
                    mock.patch(
                        "icode.workspace._start_git_blob_batch",
                        return_value=process,
                    ),
                    self.assertRaises(WorkspaceError),
                ):
                    workspace_module._materialize_git_blobs(
                        checkout,
                        identity,
                        (entry,),
                        symlink_enabled=True,
                        deadline=time.monotonic() + timeout_seconds,
                    )

                self.assertFalse(checkout.joinpath("partial.bin").exists())
                self.assertTrue(process.waited)
                self.assertIsNotNone(process.poll())
                if block:
                    self.assertTrue(process.killed)

    def test_git_symlink能力关闭写普通文件且开启时创建内部链接(self) -> None:
        checkout = self.root / "symlink-checkout"
        checkout.mkdir()
        (checkout / "target.txt").write_text("target", encoding="utf-8")

        fallback = checkout / "fallback-link"
        fallback.write_bytes(b"target.txt")
        workspace_module._materialize_git_symlink(
            fallback,
            checkout,
            symlink_enabled=False,
        )
        self.assertFalse(fallback.is_symlink())
        self.assertEqual(fallback.read_bytes(), b"target.txt")

        native = checkout / "native-link"
        native.write_bytes(b"target.txt")
        workspace_module._materialize_git_symlink(
            native,
            checkout,
            symlink_enabled=True,
        )
        self.assertTrue(native.is_symlink())
        self.assertEqual(os.readlink(native), "target.txt")

        unsupported = checkout / "unsupported-link"
        unsupported.write_bytes(b"target.txt")
        with (
            mock.patch.object(
                Path,
                "symlink_to",
                side_effect=PermissionError("symlink unavailable"),
            ),
            self.assertRaises(WorkspaceError),
        ):
            workspace_module._materialize_git_symlink(
                unsupported,
                checkout,
                symlink_enabled=True,
            )
        self.assertFalse(unsupported.exists())

    def test_git物化按显式symlink能力降级为普通文件(self) -> None:
        repository = _create_git_repository(self.root)
        repository.joinpath("tracked-link").symlink_to("nested/tracked.txt")
        _run_git(repository, "add", "tracked-link")
        _run_git(repository, "commit", "-qm", "add symlink")

        with (
            mock.patch(
                "icode.workspace._git_symlinks_enabled",
                return_value=False,
            ),
            WorkspaceManager(repository, self.data_root, "project-1").open(
                "symlink-fallback-ticket", "run-1"
            ) as session,
        ):
            materialized = session.workspace_root / "tracked-link"
            self.assertFalse(materialized.is_symlink())
            self.assertEqual(materialized.read_bytes(), b"nested/tracked.txt")

    def test_git命令清除继承重定向环境并设置timeout(self) -> None:
        source = self._snapshot_source()
        redirect_repository = _create_git_repository(self.root)
        inherited = {
            "GIT_DIR": str(redirect_repository / ".git"),
            "GIT_WORK_TREE": str(redirect_repository),
            "GIT_INDEX_FILE": str(redirect_repository / ".git" / "index"),
            "GIT_CONFIG_COUNT": "0",
        }
        original_run = subprocess.run
        observed: list[dict[str, object]] = []

        def recording_run(*args, **kwargs):
            observed.append(kwargs)
            return original_run(*args, **kwargs)

        with (
            mock.patch.dict(os.environ, inherited, clear=False),
            mock.patch("icode.workspace.subprocess.run", side_effect=recording_run),
            WorkspaceManager(source, self.data_root, "project-1").open(
                "environment-ticket", "run-1"
            ) as session,
        ):
            self.assertEqual(session.kind, "snapshot")

        self.assertTrue(observed)
        for call in observed:
            environment = call.get("env")
            self.assertIsInstance(environment, dict)
            self.assertFalse(
                any(key.startswith("GIT_") for key in environment), environment
            )
            self.assertIsInstance(call.get("timeout"), (int, float))
            self.assertGreater(call["timeout"], 0)

    def test_非git目录生成带清单的原子快照并排除运行时目录(self) -> None:
        source = self._snapshot_source()
        (source / ".icode_output").mkdir()
        (source / ".icode_output" / "ignored.txt").write_text(
            "ignored", encoding="utf-8"
        )
        (source / ".icode_runtime").mkdir()
        (source / ".icode_runtime" / "ignored.txt").write_text(
            "ignored", encoding="utf-8"
        )
        (source / "internal-link").symlink_to("file.txt")

        with WorkspaceManager(source, self.data_root, "project-1").open(
            "ticket-1", "run-1"
        ) as session:
            self.assertEqual(session.kind, "snapshot")
            self.assertEqual(
                (session.workspace_root / "file.txt").read_text(encoding="utf-8"),
                "snapshot\n",
            )
            self.assertTrue((session.workspace_root / "internal-link").is_symlink())
            self.assertFalse((session.workspace_root / ".icode_output").exists())
            self.assertFalse((session.workspace_root / ".icode_runtime").exists())
            metadata = json.loads(session.manifest_path.read_text(encoding="utf-8"))
            baseline_path = session.runtime_root / "snapshot-manifest.json"
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            self.assertEqual(
                metadata["snapshot_manifest_sha256"],
                hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
            )
            entries = {item["path"]: item for item in baseline["entries"]}
            self.assertEqual(entries["file.txt"]["type"], "file")
            self.assertEqual(entries["file.txt"]["size"], len(b"snapshot\n"))
            self.assertEqual(entries["internal-link"]["type"], "symlink")
            self.assertEqual(entries["internal-link"]["target"], "file.txt")
            self.assertIn("sha256", entries["directory/nested.bin"])

    def test_同一工单复用已存在快照并保留代理修改(self) -> None:
        source = self._snapshot_source()
        manager = WorkspaceManager(source, self.data_root, "project-1")
        first = manager.open("ticket-1", "run-1")
        first.workspace_root.joinpath("file.txt").write_text(
            "agent change\n", encoding="utf-8"
        )
        original_checkout = first.workspace_root
        first.close()

        with manager.open("ticket-1", "run-2") as reused:
            self.assertEqual(reused.workspace_root, original_checkout)
            self.assertEqual(
                reused.workspace_root.joinpath("file.txt").read_text(encoding="utf-8"),
                "agent change\n",
            )

    def test_workspace元数据严格拒绝缺失未知字段及身份漂移(self) -> None:
        source = self._snapshot_source()
        manager = WorkspaceManager(source, self.data_root, "project-1")

        mutations = {
            "missing": lambda value: value.pop("kind"),
            "unknown": lambda value: value.__setitem__("unexpected", True),
            "schema": lambda value: value.__setitem__("schema_version", 999),
            "source": lambda value: value.__setitem__("source_root", str(self.root)),
        }
        for index, (name, mutate) in enumerate(mutations.items()):
            ticket_id = f"ticket-{index}"
            session = manager.open(ticket_id, "run-create")
            manifest_path = session.manifest_path
            session.close()
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
            mutate(metadata)
            manifest_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.subTest(mutation=name):
                with self.assertRaises(WorkspaceError):
                    manager.open(ticket_id, "run-reopen")
                self.assert_lease_released("project-1", ticket_id)

    def test_git_revision漂移被拒绝且不覆盖旧checkout(self) -> None:
        repository = _create_git_repository(self.root)
        manager = WorkspaceManager(repository, self.data_root, "project-1")
        first = manager.open("ticket-1", "run-1")
        old_revision = _run_git(first.workspace_root, "rev-parse", "HEAD")
        first.close()
        (repository / "second.txt").write_text("second\n", encoding="utf-8")
        _run_git(repository, "add", ".")
        _run_git(repository, "commit", "-qm", "second")

        with self.assertRaises(WorkspaceError):
            manager.open("ticket-1", "run-2")

        checkout = self._ticket_root("project-1", "ticket-1") / "checkout"
        self.assertEqual(_run_git(checkout, "rev-parse", "HEAD"), old_revision)
        self.assert_lease_released("project-1", "ticket-1")

    def test_snapshot基线清单漂移及checkout缺失被拒绝(self) -> None:
        source = self._snapshot_source()
        manager = WorkspaceManager(source, self.data_root, "project-1")

        session = manager.open("manifest-ticket", "run-1")
        session.runtime_root.joinpath("snapshot-manifest.json").write_text(
            "{}", encoding="utf-8"
        )
        session.close()
        with self.assertRaises(WorkspaceError):
            manager.open("manifest-ticket", "run-2")

        session = manager.open("checkout-ticket", "run-1")
        checkout = session.workspace_root
        session.close()
        checkout.rename(checkout.with_name("checkout-moved"))
        with self.assertRaises(WorkspaceError):
            manager.open("checkout-ticket", "run-2")

    def test_reuse拒绝ticket根symlink逃逸data_root(self) -> None:
        source = self._snapshot_source()
        manager = WorkspaceManager(source, self.data_root, "project-1")
        session = manager.open("ticket-1", "run-1")
        ticket_root = session.manifest_path.parent
        session.close()
        outside = self.root / "escaped-ticket-root"
        ticket_root.rename(outside)
        ticket_root.symlink_to(outside, target_is_directory=True)

        with self.assertRaises(WorkspaceError):
            manager.open("ticket-1", "run-2")

        self.assert_lease_released("project-1", "ticket-1")

    def test_manifest发布失败删除空ticket根且可立即重试(self) -> None:
        source = self._snapshot_source()
        manager = WorkspaceManager(source, self.data_root, "project-1")
        ticket_root = self._ticket_root("project-1", "retry-ticket")
        original_write_atomic = workspace_module._write_atomic
        failed_once = False

        def fail_workspace_metadata_once(path: Path, payload: bytes) -> None:
            nonlocal failed_once
            if path.name == "workspace.json" and not failed_once:
                failed_once = True
                raise OSError("simulated metadata failure")
            original_write_atomic(path, payload)

        with (
            mock.patch(
                "icode.workspace._write_atomic",
                side_effect=fail_workspace_metadata_once,
            ),
            self.assertRaises(WorkspaceError),
        ):
            manager.open("retry-ticket", "run-1")

        self.assertFalse(ticket_root.exists())
        with manager.open("retry-ticket", "run-2") as retried:
            self.assertEqual(retried.kind, "snapshot")

    def test_git_add失败不删除未注册竞争者目录(self) -> None:
        repository = _create_git_repository(self.root)
        original_run_git = workspace_module._run_git
        marker_holder: list[Path] = []

        def fail_after_competitor_created(working_directory, arguments, **kwargs):
            arguments = tuple(arguments)
            if arguments[:2] == ("worktree", "add"):
                checkout = Path(arguments[arguments.index("--no-checkout") + 1])
                checkout.mkdir()
                marker = checkout / "competitor-marker"
                marker.write_text("keep", encoding="utf-8")
                marker_holder.append(marker)
                raise WorkspaceError("simulated add failure")
            return original_run_git(working_directory, arguments, **kwargs)

        with (
            mock.patch(
                "icode.workspace._run_git", side_effect=fail_after_competitor_created
            ),
            self.assertRaises(WorkspaceError),
        ):
            WorkspaceManager(repository, self.data_root, "project-1").open(
                "competitor-ticket", "run-1"
            )

        self.assertEqual(len(marker_holder), 1)
        self.assertEqual(marker_holder[0].read_text(encoding="utf-8"), "keep")
        self.assert_lease_released("project-1", "competitor-ticket")

    def test_workspace元数据发布失败清理由本次创建的资源(self) -> None:
        source = self._snapshot_source()
        ticket_root = self._ticket_root("project-1", "ticket-1")
        original_write_atomic = workspace_module._write_atomic

        def fail_workspace_metadata(path: Path, payload: bytes) -> None:
            if path.name == "workspace.json":
                raise OSError("simulated metadata failure")
            original_write_atomic(path, payload)

        with (
            mock.patch(
                "icode.workspace._write_atomic", side_effect=fail_workspace_metadata
            ),
            self.assertRaises(WorkspaceError),
        ):
            WorkspaceManager(source, self.data_root, "project-1").open(
                "ticket-1", "run-1"
            )

        self.assertFalse(ticket_root.joinpath("checkout").exists())
        self.assertFalse(ticket_root.joinpath("runtime").exists())
        self.assertFalse(ticket_root.joinpath("receipts").exists())
        self.assert_lease_released("project-1", "ticket-1")

    def test_工作区布局父目录被symlink替换时拒绝越界写入(self) -> None:
        source = self._snapshot_source()
        project_hash = hashlib.sha256(b"project-1").hexdigest()
        workspaces_root = self.data_root / "workspaces"
        workspaces_root.mkdir(parents=True)
        outside = self.root / "outside-workspaces"
        outside.mkdir()
        workspaces_root.joinpath(project_hash).symlink_to(
            outside, target_is_directory=True
        )

        with self.assertRaises(WorkspaceError):
            WorkspaceManager(source, self.data_root, "project-1").open(
                "ticket-1", "run-1"
            )

        self.assertEqual(list(outside.iterdir()), [])
        self.assert_lease_released("project-1", "ticket-1")

    def test_不存在或非目录source被拒绝并释放租约(self) -> None:
        sources = (self.root / "missing", self.root / "plain-file")
        sources[1].write_text("not a directory", encoding="utf-8")
        for index, source in enumerate(sources):
            ticket_id = f"ticket-{index}"
            with self.subTest(source=source.name):
                with self.assertRaises(WorkspaceError):
                    WorkspaceManager(source, self.data_root, "project-1").open(
                        ticket_id, "run-1"
                    )
                self.assert_lease_released("project-1", ticket_id)

    def test_source与data_root任一方向重叠时在lease前拒绝(self) -> None:
        source = self._snapshot_source()
        nested_data = source / ".local-data"
        with self.assertRaises(WorkspaceError):
            WorkspaceManager(source, nested_data, "project-1")
        self.assertFalse(nested_data.exists())

        outer_data = self.root / "outer-data"
        nested_source = outer_data / "source"
        nested_source.mkdir(parents=True)
        with self.assertRaises(WorkspaceError):
            WorkspaceManager(nested_source, outer_data, "project-1")
        self.assertFalse((outer_data / "ticket-leases").exists())

    def test_未知checkout冲突时失败且不删除内容(self) -> None:
        source = self._snapshot_source()
        ticket_root = self._ticket_root("project-1", "ticket-1")
        checkout = ticket_root / "checkout"
        checkout.mkdir(parents=True)
        marker = checkout / "keep.txt"
        marker.write_text("do not remove", encoding="utf-8")

        with self.assertRaises(WorkspaceError):
            WorkspaceManager(source, self.data_root, "project-1").open(
                "ticket-1", "run-1"
            )

        self.assertEqual(marker.read_text(encoding="utf-8"), "do not remove")
        self.assert_lease_released("project-1", "ticket-1")

    def test_git失败清理不删除被替换checkout也不调用worktree_remove(self) -> None:
        repository = _create_git_repository(self.root)
        checkout_marker: Path | None = None
        git_calls: list[tuple[str, ...]] = []
        original_run_git = workspace_module._run_git

        def recording_run_git(working_directory, arguments, **kwargs):
            git_calls.append(tuple(arguments))
            return original_run_git(working_directory, arguments, **kwargs)

        def replace_checkout(checkout_root, identity):
            nonlocal checkout_marker
            checkout_root.rename(checkout_root.with_name("owned-checkout"))
            checkout_root.mkdir()
            checkout_marker = checkout_root / "foreign-marker.txt"
            checkout_marker.write_text("foreign", encoding="utf-8")
            raise WorkspaceError("injected materialization failure")

        with (
            mock.patch("icode.workspace._run_git", side_effect=recording_run_git),
            mock.patch(
                "icode.workspace._materialize_git_tree",
                side_effect=replace_checkout,
            ),
            self.assertRaises(WorkspaceError),
        ):
            WorkspaceManager(repository, self.data_root, "project-1").open(
                "git-cleanup-ticket", "run-1"
            )

        self.assertIsNotNone(checkout_marker)
        self.assertEqual(checkout_marker.read_text(encoding="utf-8"), "foreign")
        self.assertFalse(
            any(call[:2] == ("worktree", "remove") for call in git_calls),
            git_calls,
        )
        self.assert_lease_released("project-1", "git-cleanup-ticket")

    def test_git_worktree_add异常后不追认并清理匹配注册目录(self) -> None:
        repository = _create_git_repository(self.root)
        foreign_marker: Path | None = None
        git_calls: list[tuple[str, ...]] = []
        original_run_git = workspace_module._run_git
        original_rename = os.rename

        def fail_after_registration(working_directory, arguments, **kwargs):
            nonlocal foreign_marker
            command = tuple(arguments)
            git_calls.append(command)
            if command[:2] != ("worktree", "add"):
                return original_run_git(working_directory, arguments, **kwargs)
            original_run_git(working_directory, arguments, **kwargs)
            checkout = Path(command[-2])
            original_rename(checkout, checkout.with_name("unreturned-add-checkout"))
            checkout.mkdir()
            foreign_marker = checkout / "foreign-marker.txt"
            foreign_marker.write_text("foreign", encoding="utf-8")
            raise WorkspaceError("injected worktree add transport failure")

        with (
            mock.patch(
                "icode.workspace._run_git",
                side_effect=fail_after_registration,
            ),
            self.assertRaises(WorkspaceError),
        ):
            WorkspaceManager(repository, self.data_root, "project-1").open(
                "unreturned-add-ticket", "run-1"
            )

        self.assertIsNotNone(foreign_marker)
        self.assertEqual(foreign_marker.read_text(encoding="utf-8"), "foreign")
        self.assertFalse(
            any(call[:2] == ("worktree", "remove") for call in git_calls),
            git_calls,
        )

    def test_创建失败将owned目录移入quarantine且允许retry(self) -> None:
        repository = _create_git_repository(self.root)
        manager = WorkspaceManager(repository, self.data_root, "project-1")
        original_write_atomic = workspace_module._write_atomic

        def fail_workspace_manifest(path: Path, payload: bytes) -> None:
            if path.name == "workspace.json":
                raise OSError("injected metadata publish failure")
            original_write_atomic(path, payload)

        with (
            mock.patch(
                "icode.workspace._write_atomic",
                side_effect=fail_workspace_manifest,
            ),
            self.assertRaises(WorkspaceError),
        ):
            manager.open("quarantine-ticket", "run-1")

        ticket_root = self._ticket_root("project-1", "quarantine-ticket")
        self.assertFalse(ticket_root.exists())
        quarantine = self.data_root / "workspace-quarantine"
        quarantined_names = {
            path.name
            for container in quarantine.iterdir()
            for path in container.iterdir()
        }
        self.assertEqual(quarantined_names, {"checkout", "runtime", "receipts"})
        self.assertTrue(any(quarantine.rglob("tracked.txt")))

        with manager.open("quarantine-ticket", "run-2") as retried:
            self.assertEqual(
                retried.workspace_root.joinpath("nested", "tracked.txt").read_text(
                    encoding="utf-8"
                ),
                "source\n",
            )

    def test_git失败清理不prune用户其它离线worktree登记(self) -> None:
        repository = _create_git_repository(self.root)
        unrelated = self.root / "unrelated-worktree"
        _run_git(
            repository,
            "worktree",
            "add",
            "--detach",
            "--no-checkout",
            str(unrelated),
            "HEAD",
        )
        unrelated_quarantine = self.root / "unrelated-offline"
        unrelated.rename(unrelated_quarantine)
        manager = WorkspaceManager(repository, self.data_root, "project-1")
        original_write_atomic = workspace_module._write_atomic

        def fail_workspace_manifest(path: Path, payload: bytes) -> None:
            if path.name == "workspace.json":
                raise OSError("simulated workspace manifest failure")
            original_write_atomic(path, payload)

        with (
            mock.patch(
                "icode.workspace._write_atomic",
                side_effect=fail_workspace_manifest,
            ),
            self.assertRaises(WorkspaceError),
        ):
            manager.open("targeted-cleanup-ticket", "run-1")

        registrations = _run_git(repository, "worktree", "list", "--porcelain")
        self.assertIn(str(unrelated), registrations)

    def test_quarantine_rename窗口替换的foreign目录仍保留(self) -> None:
        source = self._snapshot_source()
        original_write_atomic = workspace_module._write_atomic
        original_rename = os.rename
        injected = False

        def fail_workspace_manifest(path: Path, payload: bytes) -> None:
            if path.name == "workspace.json":
                raise OSError("injected metadata publish failure")
            original_write_atomic(path, payload)

        def replace_at_rename(source_path, destination_path, *args, **kwargs):
            nonlocal injected
            source_path = Path(source_path)
            if source_path.name == "runtime" and not injected:
                injected = True
                original_rename(
                    source_path,
                    source_path.with_name("owned-runtime-before-race"),
                )
                source_path.mkdir()
                source_path.joinpath("foreign-marker.txt").write_text(
                    "foreign", encoding="utf-8"
                )
            return original_rename(source_path, destination_path, *args, **kwargs)

        with (
            mock.patch(
                "icode.workspace._write_atomic",
                side_effect=fail_workspace_manifest,
            ),
            mock.patch("icode.workspace.os.rename", side_effect=replace_at_rename),
            self.assertRaises(WorkspaceError),
        ):
            WorkspaceManager(source, self.data_root, "project-1").open(
                "rename-race-ticket", "run-1"
            )

        self.assertTrue(injected)
        markers = list(self.data_root.rglob("foreign-marker.txt"))
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0].read_text(encoding="utf-8"), "foreign")

    def test_snapshot失败清理只删除创建时同inode目录(self) -> None:
        source = self._snapshot_source()
        foreign_markers: list[Path] = []
        original_write_atomic = workspace_module._write_atomic

        def replace_workspace_directories(path: Path, payload: bytes) -> None:
            if path.name != "workspace.json":
                original_write_atomic(path, payload)
                return
            ticket_root = path.parent
            for name in ("checkout", "runtime", "receipts"):
                directory = ticket_root / name
                directory.rename(ticket_root / f"owned-{name}")
                directory.mkdir()
                marker = directory / "foreign-marker.txt"
                marker.write_text("foreign", encoding="utf-8")
                foreign_markers.append(marker)
            raise OSError("injected metadata publish failure")

        with (
            mock.patch(
                "icode.workspace._write_atomic",
                side_effect=replace_workspace_directories,
            ),
            self.assertRaises(WorkspaceError),
        ):
            WorkspaceManager(source, self.data_root, "project-1").open(
                "snapshot-cleanup-ticket", "run-1"
            )

        self.assertEqual(len(foreign_markers), 3)
        for marker in foreign_markers:
            self.assertEqual(marker.read_text(encoding="utf-8"), "foreign")
        self.assert_lease_released("project-1", "snapshot-cleanup-ticket")

    def test_拒绝逃出source的symlink并释放租约(self) -> None:
        source = self._snapshot_source()
        outside = self.root / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        (source / "escape").symlink_to(outside)

        with self.assertRaises(WorkspaceError):
            WorkspaceManager(source, self.data_root, "project-1").open(
                "ticket-1", "run-1"
            )

        self.assertFalse(
            self._ticket_root("project-1", "ticket-1").joinpath("checkout").exists()
        )
        self.assert_lease_released("project-1", "ticket-1")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFO support")
    def test_拒绝特殊文件且不留下checkout(self) -> None:
        source = self._snapshot_source()
        os.mkfifo(source / "named-pipe")

        with self.assertRaises(WorkspaceError):
            WorkspaceManager(source, self.data_root, "project-1").open(
                "ticket-1", "run-1"
            )

        self.assertFalse(
            self._ticket_root("project-1", "ticket-1").joinpath("checkout").exists()
        )
        self.assert_lease_released("project-1", "ticket-1")

    def test_git命令失败统一异常且释放租约不泄露命令输出(self) -> None:
        source = self._snapshot_source()
        git_error = subprocess.CalledProcessError(
            128, ["git"], output="sensitive stdout", stderr="sensitive stderr"
        )
        with (
            mock.patch("icode.workspace.subprocess.run", side_effect=git_error),
            self.assertRaises(WorkspaceError) as caught,
        ):
            WorkspaceManager(source, self.data_root, "project-1").open(
                "ticket-1", "run-1"
            )

        self.assertNotIn("sensitive", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assert_lease_released("project-1", "ticket-1")

    def test_bare和unborn_git仓库稳定拒绝而非snapshot(self) -> None:
        bare = self.root / "bare.git"
        bare.mkdir()
        _run_git(bare, "init", "--bare", "-q")
        unborn = self.root / "unborn"
        unborn.mkdir()
        _run_git(unborn, "init", "-q")

        for index, source in enumerate((bare, unborn)):
            ticket_id = f"git-invalid-{index}"
            with self.subTest(source=source.name):
                with self.assertRaises(WorkspaceError):
                    WorkspaceManager(source, self.data_root, "project-1").open(
                        ticket_id, "run-1"
                    )
                self.assertFalse(
                    self._ticket_root("project-1", ticket_id)
                    .joinpath("checkout")
                    .exists()
                )
                self.assert_lease_released("project-1", ticket_id)

    def test_reuse_git拒绝HEAD漂移和同common_dir替换worktree(self) -> None:
        repository = _create_git_repository(self.root)
        manager = WorkspaceManager(repository, self.data_root, "project-1")

        changed = manager.open("head-ticket", "run-1")
        changed_root = changed.workspace_root
        changed.close()
        changed_root.joinpath("tracked.txt").write_text(
            "new commit\n", encoding="utf-8"
        )
        _run_git(changed_root, "add", "tracked.txt")
        _run_git(changed_root, "commit", "-qm", "workspace commit")
        with self.assertRaises(WorkspaceError):
            manager.open("head-ticket", "run-2")

        replaced = manager.open("replace-ticket", "run-1")
        replaced_root = replaced.workspace_root
        revision = _run_git(replaced_root, "rev-parse", "HEAD")
        replaced.close()
        _run_git(repository, "worktree", "remove", "--force", str(replaced_root))
        _run_git(
            repository,
            "worktree",
            "add",
            "--detach",
            str(replaced_root),
            revision,
        )
        with self.assertRaises(WorkspaceError):
            manager.open("replace-ticket", "run-2")

    def test_snapshot哈希流式读取而不调用Path_read_bytes(self) -> None:
        source = self._snapshot_source()
        source.joinpath("large.bin").write_bytes(b"x" * (1024 * 1024))

        with (
            mock.patch(
                "icode.workspace.Path.read_bytes",
                side_effect=AssertionError("snapshot hashing must stream"),
            ),
            WorkspaceManager(source, self.data_root, "project-1").open(
                "stream-ticket", "run-1"
            ) as session,
        ):
            self.assertTrue(session.workspace_root.joinpath("large.bin").is_file())

    def test_session保护路径和deny网络策略完整且close幂等(self) -> None:
        repository = _create_git_repository(self.root)
        extra = self.root / "extra-protected"
        manager = WorkspaceManager(
            repository, self.data_root, "project-1", extra_protected_paths=(extra,)
        )
        session = manager.open("ticket-1", "run-1")

        expected = {
            repository.resolve(),
            repository.joinpath(".git").resolve(),
            repository.joinpath(".icode_output").resolve(),
            session.workspace_root.joinpath(".git").resolve(),
            session.runtime_root.resolve(),
            session.receipts_root.resolve(),
            extra.resolve(),
        }
        self.assertTrue(expected.issubset(set(session.protected_paths)))
        self.assertEqual(
            session.protected_paths,
            tuple(sorted(set(session.protected_paths), key=str)),
        )
        policy = session.policy(
            "implement", process_limit=7, wall_timeout_seconds=11, output_limit_bytes=13
        )
        self.assertEqual(policy.workspace_root, session.workspace_root)
        self.assertEqual(policy.read_roots, (session.workspace_root,))
        self.assertEqual(policy.write_roots, (session.workspace_root,))
        self.assertEqual(policy.network_mode, NetworkMode.DENY)
        self.assertEqual(policy.allowed_domains, ())
        self.assertEqual(policy.deny_write_roots, session.protected_paths)
        self.assertEqual(policy.protected_paths, session.protected_paths)
        self.assertEqual(
            (
                policy.process_limit,
                policy.wall_timeout_seconds,
                policy.output_limit_bytes,
            ),
            (7, 11, 13),
        )
        session.close()
        session.close()
        self.assert_lease_released("project-1", "ticket-1")


class TestDefaultDataRoot(unittest.TestCase):
    def test_icode_data_home优先且返回绝对规范路径(self) -> None:
        self.assertEqual(WORKSPACE_SCHEMA_VERSION, 1)
        with mock.patch.dict(
            os.environ,
            {"ICODE_DATA_HOME": "relative-data", "XDG_DATA_HOME": "/ignored"},
            clear=True,
        ):
            self.assertEqual(default_data_root(), Path("relative-data").resolve())

    def test_windows_macos及xdg默认路径(self) -> None:
        cases = (
            (
                "win32",
                {"LOCALAPPDATA": "/local-app-data"},
                Path("/local-app-data/ICODE Agent"),
            ),
            ("darwin", {}, Path.home() / "Library/Application Support/ICODE Agent"),
            ("linux", {"XDG_DATA_HOME": "/xdg"}, Path("/xdg/icode-agent")),
            ("linux", {}, Path.home() / ".local/share/icode-agent"),
        )
        for platform, environment, expected in cases:
            with (
                self.subTest(platform=platform, environment=environment),
                mock.patch("icode.workspace.sys.platform", platform),
                mock.patch.dict(os.environ, environment, clear=True),
            ):
                self.assertEqual(default_data_root(), expected.resolve())

    def test_windows缺少localappdata时失败(self) -> None:
        with (
            mock.patch("icode.workspace.sys.platform", "win32"),
            mock.patch.dict(os.environ, {}, clear=True),
            self.assertRaises(WorkspaceError),
        ):
            default_data_root()


class TestWorkspaceRoadmapContract(unittest.TestCase):
    def test_r21明确工作区能力和隔离边界(self) -> None:
        roadmap = (
            Path(__file__).resolve().parents[1] / "docs" / "roadmap.md"
        ).read_text(encoding="utf-8")
        self.assertIn("R2.1", roadmap)
        self.assertIn("跨进程租约", roadmap)
        self.assertIn("不等于操作系统强制隔离", roadmap)


if __name__ == "__main__":
    unittest.main()
