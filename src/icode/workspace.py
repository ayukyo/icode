"""跨进程工单工作区租约。"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO


class WorkspaceError(RuntimeError):
    """工作区租约操作失败。"""


class WorkspaceBusyError(WorkspaceError):
    """目标工单已由其他进程持有。"""


class _LockUnavailable(Exception):
    """底层非阻塞锁未能取得。"""


_LOCK_BYTE = b"\0"
_POSIX_CONTENTION_ERRNOS = frozenset((errno.EACCES, errno.EAGAIN))
_WINDOWS_CONTENTION_ERRNOS = frozenset((errno.EACCES, errno.EAGAIN))
_WINDOWS_LOCK_VIOLATION = 33


def _validated_bytes(name: str, value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise WorkspaceError(f"{name} 必须是非空字符串")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise WorkspaceError(f"{name} 不得包含 ASCII 控制字符")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WorkspaceError(f"{name} 必须可编码为 UTF-8") from exc


def _publish_initialized_lock_file(path: Path) -> None:
    """在同目录准备完整 inode，再以硬链接原子发布且绝不覆盖目标。"""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".ticket-lease-",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    stream: BinaryIO | None = None
    try:
        stream = os.fdopen(descriptor, "r+b")
        descriptor = -1
        stream.write(_LOCK_BYTE)
        stream.flush()
        os.fsync(stream.fileno())
        stream.close()
        stream = None

        try:
            os.link(temporary_path, path)
        except FileExistsError:
            # 另一创建者已经发布了一个完整初始化的 inode。
            pass
        except OSError as exc:
            raise WorkspaceError("文件系统不支持安全发布工单锁文件") from exc
    finally:
        if stream is not None:
            _close_quietly(stream)
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # 目标 inode 已安全发布；临时硬链接清理失败不改变互斥语义。
            pass


def _open_lock_file(path: Path) -> BinaryIO:
    """打开已完整初始化的锁 inode；不存在时先原子发布。"""
    flags = os.O_RDWR | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        _publish_initialized_lock_file(path)
        descriptor = os.open(path, flags)

    try:
        stream = os.fdopen(descriptor, "r+b")
    except Exception:
        os.close(descriptor)
        raise
    stream.seek(0)
    return stream


def _is_lock_contention(exc: OSError) -> bool:
    if os.name == "posix":
        return exc.errno in _POSIX_CONTENTION_ERRNOS
    if os.name == "nt":  # pragma: no cover - 在 Windows CI 上执行
        return (
            exc.errno in _WINDOWS_CONTENTION_ERRNOS
            or getattr(exc, "winerror", None) == _WINDOWS_LOCK_VIOLATION
        )
    return False


def _raise_lock_error(exc: OSError) -> None:
    if _is_lock_contention(exc):
        raise _LockUnavailable from exc
    raise WorkspaceError(f"无法获取工单文件锁：{exc}") from exc


def _acquire_file_lock(stream: BinaryIO) -> None:
    if os.name == "posix":
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - 异常平台安装
            raise WorkspaceError("当前 POSIX 平台缺少 fcntl") from exc
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            _raise_lock_error(exc)
        return

    if os.name == "nt":  # pragma: no cover - 在 Windows CI 上执行
        try:
            import msvcrt
        except ImportError as exc:
            raise WorkspaceError("当前 Windows 平台缺少 msvcrt") from exc
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            _raise_lock_error(exc)
        return

    raise WorkspaceError(f"不支持的平台：{os.name}")


def _release_file_lock(stream: BinaryIO) -> None:
    if os.name == "posix":
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - 异常平台安装
            raise WorkspaceError("当前 POSIX 平台缺少 fcntl") from exc
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return

    if os.name == "nt":  # pragma: no cover - 在 Windows CI 上执行
        try:
            import msvcrt
        except ImportError as exc:
            raise WorkspaceError("当前 Windows 平台缺少 msvcrt") from exc
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return

    raise WorkspaceError(f"不支持的平台：{os.name}")


def _close_quietly(stream: BinaryIO | None) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except OSError:
        pass


@dataclass
class TicketLease:
    """同一 ``project_id`` 与 ``ticket_id`` 的跨进程排他租约。"""

    path: Path
    project_id: str
    ticket_id: str
    run_id: str
    _stream: BinaryIO | None = field(repr=False, compare=False)

    @classmethod
    def acquire(
        cls,
        data_root: Path,
        project_id: str,
        ticket_id: str,
        run_id: str,
    ) -> TicketLease:
        project_bytes = _validated_bytes("project_id", project_id)
        ticket_bytes = _validated_bytes("ticket_id", ticket_id)
        _validated_bytes("run_id", run_id)
        digest = hashlib.sha256(project_bytes + b"\0" + ticket_bytes).hexdigest()

        stream: BinaryIO | None = None
        try:
            lease_dir = Path(data_root) / "ticket-leases"
            lease_dir.mkdir(parents=True, exist_ok=True)
            path = lease_dir / digest
            stream = _open_lock_file(path)
            try:
                _acquire_file_lock(stream)
            except _LockUnavailable as exc:
                raise WorkspaceBusyError("工单已被其他进程占用") from exc

            if os.fstat(stream.fileno()).st_size == 0:
                # POSIX flock 与 Windows _locking 都允许锁定越过 EOF 的区间；
                # 因此遗留零长 inode 也必须先锁住，绝不能先写再锁。
                stream.seek(0)
                stream.write(_LOCK_BYTE)
                stream.flush()
                os.fsync(stream.fileno())

            metadata = {
                "pid": os.getpid(),
                "project_id": project_id,
                "run_id": run_id,
                "schema_version": 1,
                "ticket_id": ticket_id,
            }
            payload = (
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            stream.seek(0)
            stream.write(_LOCK_BYTE)
            stream.truncate(1)
            stream.seek(1)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            return cls(path, project_id, ticket_id, run_id, stream)
        except WorkspaceBusyError:
            _close_quietly(stream)
            raise
        except WorkspaceError:
            _close_quietly(stream)
            raise
        except Exception as exc:
            _close_quietly(stream)
            raise WorkspaceError(f"无法获取工单租约：{exc}") from exc

    def release(self) -> None:
        """释放租约；重复调用不产生副作用。"""
        stream = self._stream
        if stream is None:
            return
        self._stream = None

        error: Exception | None = None
        try:
            _release_file_lock(stream)
        except Exception as exc:
            error = exc
        try:
            stream.close()
        except Exception as exc:
            if error is None:
                error = exc
        if error is not None:
            if isinstance(error, WorkspaceError):
                raise error
            raise WorkspaceError(f"无法释放工单租约：{error}") from error

    def __enter__(self) -> TicketLease:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()
