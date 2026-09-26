"""跨进程工单租约与隔离工作区。"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal, Self, cast

from icode.sandbox_policy import (
    POLICY_SCHEMA_VERSION,
    NetworkMode,
    SandboxPolicy,
)

WORKSPACE_SCHEMA_VERSION = 1


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
_GIT_COMMAND_TIMEOUT_SECONDS = 60
_HASH_CHUNK_SIZE_BYTES = 1024 * 1024
_MAX_GIT_SYMLINK_TARGET_BYTES = 4096


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
    flags = (
        os.O_RDWR
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        _publish_initialized_lock_file(path)
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise WorkspaceError("工单锁文件不可信") from exc

    try:
        _validate_lock_file_identity(path, descriptor)
        stream = os.fdopen(descriptor, "r+b")
    except Exception:
        os.close(descriptor)
        raise
    stream.seek(0)
    return stream


def _validate_lock_file_identity(path: Path, descriptor: int) -> None:
    path_status = os.lstat(path)
    descriptor_status = os.fstat(descriptor)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    is_reparse = bool(
        reparse_flag and getattr(path_status, "st_file_attributes", 0) & reparse_flag
    )
    if (
        stat.S_ISLNK(path_status.st_mode)
        or is_reparse
        or not stat.S_ISREG(path_status.st_mode)
        or not stat.S_ISREG(descriptor_status.st_mode)
        or path_status.st_nlink != 1
        or descriptor_status.st_nlink != 1
        or (path_status.st_dev, path_status.st_ino)
        != (descriptor_status.st_dev, descriptor_status.st_ino)
    ):
        raise WorkspaceError("工单锁文件不可信")


def _prepare_lease_directory(data_root: Path) -> Path:
    lease_dir = Path(data_root) / "ticket-leases"
    try:
        lease_dir.mkdir(parents=True, exist_ok=True)
        before = os.lstat(lease_dir)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        is_reparse = bool(
            reparse_flag and getattr(before, "st_file_attributes", 0) & reparse_flag
        )
        if (
            stat.S_ISLNK(before.st_mode)
            or is_reparse
            or not stat.S_ISDIR(before.st_mode)
        ):
            raise WorkspaceError("工单租约目录不可信")
        if os.name == "posix":
            os.chmod(lease_dir, 0o700, follow_symlinks=False)
        after = os.lstat(lease_dir)
        if not stat.S_ISDIR(after.st_mode) or (before.st_dev, before.st_ino) != (
            after.st_dev,
            after.st_ino,
        ):
            raise WorkspaceError("工单租约目录不可信")
        return lease_dir
    except WorkspaceError:
        raise
    except OSError as exc:
        raise WorkspaceError("无法准备工单租约目录") from exc


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
            lease_dir = _prepare_lease_directory(data_root)
            path = lease_dir / digest
            stream = _open_lock_file(path)
            try:
                _acquire_file_lock(stream)
            except _LockUnavailable as exc:
                raise WorkspaceBusyError("工单已被其他进程占用") from exc
            _validate_lock_file_identity(path, stream.fileno())

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
        except Exception as exc:  # noqa: BLE001 - 即使 unlock 异常也必须继续 close
            error = exc
        try:
            stream.close()
        except Exception as exc:  # noqa: BLE001 - 自定义 BinaryIO 的 close 也需归一化
            if error is None:
                error = exc
        if error is not None:
            if isinstance(error, WorkspaceError):
                raise error
            raise WorkspaceError(f"无法释放工单租约：{error}") from error

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


def _normalize_path(path: Path) -> Path:
    try:
        return Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise WorkspaceError("无法规范化工作区路径") from exc


def default_data_root() -> Path:
    """返回当前平台的 ICODE 用户数据目录。"""

    configured = os.environ.get("ICODE_DATA_HOME")
    if configured:
        return _normalize_path(Path(configured))
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise WorkspaceError("Windows 环境缺少 LOCALAPPDATA")
        return _normalize_path(Path(local_app_data) / "ICODE Agent")
    if sys.platform == "darwin":
        return _normalize_path(
            Path.home() / "Library" / "Application Support" / "ICODE Agent"
        )
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return _normalize_path(Path(xdg_data_home) / "icode-agent")
    return _normalize_path(Path.home() / ".local" / "share" / "icode-agent")


@dataclass(frozen=True)
class GitPathIdentity:
    """A no-follow filesystem object identity captured by WorkspaceManager."""

    path: Path
    device: int
    inode: int
    kind: Literal["file", "directory"]


@dataclass(frozen=True)
class GitWorkspaceIdentity:
    """WorkspaceManager 已核验的分层 Git worktree 身份快照。"""

    checkout_root: Path
    code_root: Path
    workspace_root: Path
    top_level: Path
    common_dir: Path
    git_dir: Path
    revision: str
    identity_token: str
    source_relative_path: Path
    filesystem_identities: tuple[GitPathIdentity, ...] = ()


@dataclass
class WorkspaceSession:
    """持有工单租约的隔离工作区会话。"""

    project_id: str
    ticket_id: str
    run_id: str
    kind: Literal["git_worktree", "snapshot"]
    source_root: Path
    workspace_root: Path
    runtime_root: Path
    receipts_root: Path
    manifest_path: Path
    protected_paths: tuple[Path, ...]
    lease: TicketLease
    git_status_identity: GitWorkspaceIdentity | None = None

    def policy(
        self,
        step: str,
        process_limit: int = 64,
        wall_timeout_seconds: int = 1800,
        output_limit_bytes: int = 16 * 1024 * 1024,
    ) -> SandboxPolicy:
        return SandboxPolicy(
            schema_version=POLICY_SCHEMA_VERSION,
            run_id=self.run_id,
            ticket_id=self.ticket_id,
            step=step,
            workspace_root=self.workspace_root,
            read_roots=(self.workspace_root,),
            write_roots=(self.workspace_root,),
            deny_read_roots=(),
            deny_write_roots=self.protected_paths,
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            process_limit=process_limit,
            wall_timeout_seconds=wall_timeout_seconds,
            output_limit_bytes=output_limit_bytes,
            protected_paths=self.protected_paths,
        )

    def close(self) -> None:
        self.lease.release()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


@dataclass(frozen=True)
class _GitIdentity:
    top_level: Path
    common_dir: Path
    revision: str
    relative_source: Path


_SNAPSHOT_EXCLUDED_TOP_LEVEL = frozenset(
    (".icode_output", ".icode_runtime", "runtime", "receipts")
)
_COMMON_METADATA_FIELDS = frozenset(
    (
        "schema_version",
        "project_id",
        "ticket_id",
        "kind",
        "source_root",
        "checkout_root",
        "runtime_root",
        "receipts_root",
    )
)
_GIT_METADATA_FIELDS = _COMMON_METADATA_FIELDS | frozenset(
    (
        "git_top_level",
        "git_common_dir",
        "git_revision",
        "git_worktree_git_dir",
        "git_worktree_identity",
        "source_relative_path",
    )
)
_LAYERED_GIT_METADATA_FIELDS = _GIT_METADATA_FIELDS | frozenset(
    ("isolated_code_root",)
)
_SNAPSHOT_METADATA_FIELDS = _COMMON_METADATA_FIELDS | frozenset(
    ("snapshot_manifest_path", "snapshot_manifest_sha256")
)


def _identity_hash(value: str) -> str:
    return hashlib.sha256(_validated_bytes("identity", value)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_atomic(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _paths_overlap(left: Path, right: Path) -> bool:
    return _path_is_within(left, right) or _path_is_within(right, left)


@dataclass(frozen=True)
class _PathIdentity:
    device: int
    inode: int


def _capture_directory_identity(path: Path) -> _PathIdentity:
    try:
        status = os.lstat(path)
    except OSError as exc:
        raise WorkspaceError("无法确认新建工作区目录身份") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    is_reparse = bool(
        reparse_flag and getattr(status, "st_file_attributes", 0) & reparse_flag
    )
    if stat.S_ISLNK(status.st_mode) or is_reparse or not stat.S_ISDIR(status.st_mode):
        raise WorkspaceError("新建工作区目录身份无效")
    return _PathIdentity(status.st_dev, status.st_ino)


def _capture_git_path_identity(
    path: Path, kind: Literal["file", "directory"],
) -> GitPathIdentity:
    """Capture a trusted Git metadata object's no-follow device/inode pair."""
    try:
        status = os.lstat(path)
    except OSError as exc:
        raise WorkspaceError("无法捕获 Git 元数据对象身份") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    is_reparse = bool(
        reparse_flag and getattr(status, "st_file_attributes", 0) & reparse_flag
    )
    if stat.S_ISLNK(status.st_mode) or is_reparse:
        raise WorkspaceError("Git 元数据对象不得为符号链接")
    if kind == "file" and not stat.S_ISREG(status.st_mode):
        raise WorkspaceError("Git 元数据文件身份无效")
    if kind == "directory" and not stat.S_ISDIR(status.st_mode):
        raise WorkspaceError("Git 元数据目录身份无效")
    return GitPathIdentity(Path(path), status.st_dev, status.st_ino, kind)


def _directory_identity_matches(path: Path, identity: _PathIdentity) -> bool:
    try:
        status = os.lstat(path)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    is_reparse = bool(
        reparse_flag and getattr(status, "st_file_attributes", 0) & reparse_flag
    )
    return (
        not stat.S_ISLNK(status.st_mode)
        and not is_reparse
        and stat.S_ISDIR(status.st_mode)
        and (status.st_dev, status.st_ino) == (identity.device, identity.inode)
    )


def _quarantine_owned_tree(
    path: Path,
    identity: _PathIdentity | None,
    data_root: Path,
) -> Path | None:
    """原子移走仍匹配的目录；竞态替换也只会被保留而不会被删除。"""

    if identity is None or not _directory_identity_matches(path, identity):
        return None
    quarantine_root = data_root / "workspace-quarantine"
    _ensure_managed_directory(quarantine_root, parent=data_root)
    container = quarantine_root / uuid.uuid4().hex
    container.mkdir(mode=0o700)
    _ensure_managed_directory(container, parent=quarantine_root, create=False)
    destination = container / path.name
    try:
        os.rename(path, destination)
    except OSError as exc:
        raise WorkspaceError("无法隔离创建失败的工作区目录") from exc
    return destination


def _ensure_managed_directory(
    path: Path,
    *,
    parent: Path | None = None,
    create: bool = True,
) -> None:
    """创建固定布局目录，并拒绝 symlink/reparse 或规范路径重定向。"""

    if create:
        path.mkdir(parents=True, exist_ok=True)
    try:
        path_status = os.lstat(path)
    except OSError as exc:
        raise WorkspaceError("工作区布局目录不可信") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    is_reparse = bool(
        reparse_flag and getattr(path_status, "st_file_attributes", 0) & reparse_flag
    )
    if (
        stat.S_ISLNK(path_status.st_mode)
        or is_reparse
        or not stat.S_ISDIR(path_status.st_mode)
        or _normalize_path(path) != path
        or (parent is not None and path.parent != parent)
        or (parent is not None and not _path_is_within(path, parent))
    ):
        raise WorkspaceError("工作区布局目录不可信")


def _run_git(
    working_directory: Path,
    arguments: Iterable[str],
    *,
    check: bool = True,
    input_data: bytes | None = None,
    text: bool = True,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    try:
        with tempfile.TemporaryDirectory(prefix="icode-empty-hooks-") as hooks_dir:
            completed = subprocess.run(
                [
                    "git",
                    "-c",
                    f"core.hooksPath={hooks_dir}",
                    "-c",
                    # Older Git releases execute the literal "false" as a
                    # helper path; an empty override disables helper selection.
                    "core.fsmonitor=",
                    "-C",
                    str(working_directory),
                    *arguments,
                ],
                shell=False,
                check=False,
                capture_output=True,
                text=text,
                input=None if text else input_data,
                env=environment,
                timeout=(
                    _GIT_COMMAND_TIMEOUT_SECONDS
                    if timeout_seconds is None
                    else min(_GIT_COMMAND_TIMEOUT_SECONDS, timeout_seconds)
                ),
            )
    except (OSError, subprocess.SubprocessError):
        # SubprocessError 会携带捕获的输出；异常边界不保留原异常链。
        raise WorkspaceError("Git 命令执行失败") from None
    if check and completed.returncode != 0:
        raise WorkspaceError("Git 命令执行失败")
    return completed


def _run_git_bytes(
    working_directory: Path,
    arguments: Iterable[str],
    *,
    input_data: bytes | None = None,
    check: bool = True,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return cast(
        subprocess.CompletedProcess[bytes],
        _run_git(
            working_directory,
            arguments,
            check=check,
            input_data=input_data,
            text=False,
            timeout_seconds=timeout_seconds,
        ),
    )


def _git_path(raw_path: str, working_directory: Path) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = working_directory / candidate
    return _normalize_path(candidate)


def _detect_git(source_root: Path) -> _GitIdentity | None:
    inside_result = _run_git(
        source_root, ("rev-parse", "--is-inside-work-tree"), check=False
    )
    bare_result = _run_git(
        source_root, ("rev-parse", "--is-bare-repository"), check=False
    )
    if bare_result.returncode == 0 and bare_result.stdout.strip() == "true":
        raise WorkspaceError("不支持 bare Git 仓库")
    if inside_result.returncode != 0:
        return None
    if inside_result.stdout.strip() != "true":
        raise WorkspaceError("Git 工作树身份无效")
    probe = _run_git(source_root, ("rev-parse", "--show-toplevel"))
    top_level_text = probe.stdout.strip()
    if not top_level_text:
        raise WorkspaceError("Git 仓库身份无效")
    top_level = _git_path(top_level_text, source_root)
    try:
        relative_source = source_root.relative_to(top_level)
    except ValueError as exc:
        raise WorkspaceError("源码目录不在 Git 顶层目录内") from exc

    common_result = _run_git(source_root, ("rev-parse", "--git-common-dir"))
    revision_result = _run_git(source_root, ("rev-parse", "HEAD"))
    common_text = common_result.stdout.strip()
    revision = revision_result.stdout.strip()
    if not common_text or not revision:
        raise WorkspaceError("Git 仓库身份无效")
    return _GitIdentity(
        top_level=top_level,
        common_dir=_git_path(common_text, source_root),
        revision=revision,
        relative_source=relative_source,
    )


@dataclass(frozen=True)
class _GitTreeEntry:
    mode: str
    object_type: str
    object_id: str
    size: int | None
    relative_path: PurePosixPath


def _safe_git_relative_path(raw_path: bytes) -> PurePosixPath:
    try:
        text = raw_path.decode("utf-8")
    except UnicodeDecodeError:
        raise WorkspaceError("Git 树包含不可安全物化的路径") from None
    parts = text.split("/")
    # Git 树路径规范使用“/”；拒绝反斜杠和冒号可避免同一清单在 Windows
    # 被解释成目录分隔符或盘符，而在 POSIX 被解释成普通文件名。
    if (
        not text
        or text.startswith("/")
        or "\\" in text
        or "\0" in text
        or ":" in text
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise WorkspaceError("Git 树包含不可安全物化的路径")
    return PurePosixPath(*parts)


def _safe_git_destination(checkout_root: Path, relative_path: PurePosixPath) -> Path:
    """将已验证的 Git 路径映射到 checkout 内，拒绝平台路径语义逃逸。"""

    validated_path = _safe_git_relative_path(relative_path.as_posix().encode("utf-8"))
    normalized_root = _normalize_path(checkout_root)
    destination = _normalize_path(normalized_root.joinpath(*validated_path.parts))
    if destination == normalized_root or not _path_is_within(
        destination, normalized_root
    ):
        raise WorkspaceError("Git 树路径逃出工作区")
    return destination


def _remaining_git_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WorkspaceError("Git 工作区物化超时")
    return remaining


def _git_tree_entries(
    identity: _GitIdentity, *, deadline: float
) -> list[_GitTreeEntry]:
    result = _run_git_bytes(
        identity.top_level,
        ("ls-tree", "-rz", "-l", "--full-tree", "-r", "-t", identity.revision),
        timeout_seconds=_remaining_git_time(deadline),
    )
    entries: list[_GitTreeEntry] = []
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        try:
            raw_metadata, raw_path = record.split(b"\t", 1)
            fields = raw_metadata.split()
            if len(fields) != 4:
                raise ValueError
            raw_mode, raw_type, raw_object_id, raw_size = fields
            mode = raw_mode.decode("ascii")
            object_type = raw_type.decode("ascii")
            object_id = raw_object_id.decode("ascii")
            size = None if raw_size == b"-" else int(raw_size)
        except (UnicodeDecodeError, ValueError):
            raise WorkspaceError("Git 树清单无效") from None
        if object_type not in {"blob", "tree", "commit"}:
            raise WorkspaceError("Git 树包含不支持的对象")
        entries.append(
            _GitTreeEntry(
                mode=mode,
                object_type=object_type,
                object_id=object_id,
                size=size,
                relative_path=_safe_git_relative_path(raw_path),
            )
        )
    return entries


def _start_git_blob_batch(
    identity: _GitIdentity,
    hooks_dir: str,
) -> subprocess.Popen[bytes]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    try:
        return subprocess.Popen(
            [
                "git",
                "-c",
                f"core.hooksPath={hooks_dir}",
                "-c",
                "core.fsmonitor=",
                "-C",
                str(identity.top_level),
                "cat-file",
                "--batch",
            ],
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            bufsize=0,
        )
    except OSError:
        raise WorkspaceError("Git blob 批处理启动失败") from None


def _regular_file_identity_matches(path: Path, identity: _PathIdentity | None) -> bool:
    if identity is None:
        return False
    try:
        status = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(status.st_mode) and (status.st_dev, status.st_ino) == (
        identity.device,
        identity.inode,
    )


def _quarantine_partial_file(path: Path, identity: _PathIdentity | None) -> None:
    """移走批处理中断的文件；竞态替换时也绝不做路径式删除。"""

    if identity is None or not _regular_file_identity_matches(path, identity):
        return
    container = path.parent / f".icode-partial-{uuid.uuid4().hex}"
    try:
        container.mkdir(mode=0o700)
        os.rename(path, container / "blob")
    except OSError:
        pass


def _git_blob_hasher(object_id: str, size: int):
    try:
        int(object_id, 16)
    except ValueError:
        raise WorkspaceError("Git blob 身份无效") from None
    if len(object_id) == 40:
        digest = hashlib.sha1(usedforsecurity=False)
    elif len(object_id) == 64:
        digest = hashlib.sha256()
    else:
        raise WorkspaceError("Git blob 身份无效")
    digest.update(f"blob {size}\0".encode("ascii"))
    return digest


def _finish_git_blob_batch(
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
) -> int:
    if process.stdin is not None and not process.stdin.closed:
        process.stdin.close()
    try:
        return process.wait(timeout=_remaining_git_time(deadline))
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        try:
            return process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            return -1


def _stop_git_blob_batch(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass
    for stream in (process.stdin, process.stdout):
        if stream is None:
            continue
        try:
            stream.close()
        except OSError:
            pass


def _materialize_git_blobs(
    checkout_root: Path,
    identity: _GitIdentity,
    entries: Iterable[_GitTreeEntry],
    *,
    symlink_enabled: bool,
    deadline: float,
) -> None:
    """通过单个长驻 batch 进程逐对象流式物化并校验 Git blob。"""

    blob_entries = tuple(entries)
    if not blob_entries:
        return
    for entry in blob_entries:
        if entry.size is None or entry.size < 0:
            raise WorkspaceError("Git blob 大小无效")
        if entry.mode not in {"100644", "100755", "120000"}:
            raise WorkspaceError("Git 树包含不支持的文件模式")

    process: subprocess.Popen[bytes] | None = None
    timer: threading.Timer | None = None
    timed_out = threading.Event()
    current_path: Path | None = None
    current_identity: _PathIdentity | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="icode-empty-hooks-") as hooks_dir:
            process = _start_git_blob_batch(identity, hooks_dir)
            if process.stdin is None or process.stdout is None:
                raise WorkspaceError("Git blob 批处理管道无效")

            def expire_process() -> None:
                timed_out.set()
                if process is not None and process.poll() is None:
                    try:
                        process.kill()
                    except OSError:
                        pass

            timer = threading.Timer(_remaining_git_time(deadline), expire_process)
            timer.daemon = True
            timer.start()

            for entry in blob_entries:
                current_path = _safe_git_destination(checkout_root, entry.relative_path)
                current_path.parent.mkdir(parents=True, exist_ok=True)
                current_identity = None
                try:
                    process.stdin.write(entry.object_id.encode("ascii") + b"\n")
                    process.stdin.flush()
                    header = process.stdout.readline()
                    if not header.endswith(b"\n"):
                        raise WorkspaceError("Git blob 批处理输出不完整")
                    fields = header[:-1].split()
                    if len(fields) != 3:
                        raise WorkspaceError("Git blob 批处理输出无效")
                    raw_object_id, object_type, raw_size = fields
                    actual_id = raw_object_id.decode("ascii")
                    actual_size = int(raw_size)
                    if (
                        actual_id != entry.object_id
                        or object_type != b"blob"
                        or actual_size != entry.size
                    ):
                        raise WorkspaceError("Git blob 身份不匹配")

                    digest = _git_blob_hasher(entry.object_id, actual_size)
                    with current_path.open("xb") as stream:
                        status = os.fstat(stream.fileno())
                        current_identity = _PathIdentity(status.st_dev, status.st_ino)
                        remaining = actual_size
                        while remaining:
                            chunk = process.stdout.read(
                                min(_HASH_CHUNK_SIZE_BYTES, remaining)
                            )
                            if not chunk:
                                raise WorkspaceError("Git blob 批处理输出不完整")
                            stream.write(chunk)
                            digest.update(chunk)
                            remaining -= len(chunk)
                    if process.stdout.read(1) != b"\n":
                        raise WorkspaceError("Git blob 批处理输出不完整")
                    if not _regular_file_identity_matches(
                        current_path, current_identity
                    ):
                        raise WorkspaceError("Git blob 目标身份发生变化")
                    if digest.hexdigest() != entry.object_id:
                        raise WorkspaceError("Git blob 身份不匹配")
                    if entry.mode == "120000":
                        _materialize_git_symlink(
                            current_path,
                            checkout_root,
                            symlink_enabled=symlink_enabled,
                        )
                    else:
                        current_path.chmod(0o755 if entry.mode == "100755" else 0o644)
                    current_path = None
                    current_identity = None
                except (OSError, UnicodeError, ValueError):
                    raise WorkspaceError("Git blob 批处理失败") from None

            return_code = _finish_git_blob_batch(process, deadline=deadline)
            if timed_out.is_set():
                raise WorkspaceError("Git 工作区物化超时")
            if return_code != 0:
                raise WorkspaceError("Git blob 批处理失败")
    except WorkspaceError:
        if current_path is not None:
            _quarantine_partial_file(current_path, current_identity)
        if timed_out.is_set():
            raise WorkspaceError("Git 工作区物化超时") from None
        raise
    except (OSError, subprocess.SubprocessError):
        if current_path is not None:
            _quarantine_partial_file(current_path, current_identity)
        raise WorkspaceError("Git blob 批处理失败") from None
    finally:
        if timer is not None:
            timer.cancel()
            timer.join(timeout=1)
        if process is not None:
            _stop_git_blob_batch(process)


def _git_symlinks_enabled(
    checkout_root: Path, *, deadline: float | None = None
) -> bool:
    result = _run_git(
        checkout_root,
        ("config", "--bool", "core.symlinks"),
        check=False,
        timeout_seconds=(None if deadline is None else _remaining_git_time(deadline)),
    )
    if result.returncode != 0:
        return os.name != "nt"
    value = result.stdout.strip().lower()
    if value in {"true", "yes", "on", "1"}:
        return True
    if value in {"false", "no", "off", "0"}:
        return False
    raise WorkspaceError("Git 符号链接配置无效")


def _materialize_git_symlink(
    destination: Path,
    checkout_root: Path,
    *,
    symlink_enabled: bool,
) -> None:
    """按显式能力选择真实 symlink 或 Git for Windows 的普通文件表示。"""

    if not symlink_enabled:
        destination.chmod(0o644)
        return
    try:
        status = os.lstat(destination)
        if not stat.S_ISREG(status.st_mode):
            raise WorkspaceError("Git 符号链接暂存文件身份无效")
        if status.st_size > _MAX_GIT_SYMLINK_TARGET_BYTES:
            raise WorkspaceError("Git 符号链接目标过长")
        with destination.open("rb") as stream:
            raw_target = stream.read(_MAX_GIT_SYMLINK_TARGET_BYTES + 1)
        if len(raw_target) > _MAX_GIT_SYMLINK_TARGET_BYTES:
            raise WorkspaceError("Git 符号链接目标过长")
        link_target = raw_target.decode("utf-8")
    except WorkspaceError:
        raise
    except (OSError, UnicodeDecodeError):
        raise WorkspaceError("Git 树包含无效符号链接") from None
    if (
        not link_target
        or "\0" in link_target
        or "\\" in link_target
        or ":" in link_target
    ):
        raise WorkspaceError("Git 树包含无效符号链接")
    target_path = Path(link_target)
    resolved_target = _normalize_path(destination.parent / target_path)
    normalized_root = _normalize_path(checkout_root)
    if target_path.is_absolute() or not _path_is_within(
        resolved_target, normalized_root
    ):
        raise WorkspaceError("Git 树符号链接逃出工作区")
    identity = _PathIdentity(status.st_dev, status.st_ino)
    if not _regular_file_identity_matches(destination, identity):
        raise WorkspaceError("Git 符号链接暂存文件身份发生变化")
    destination.unlink()
    try:
        destination.symlink_to(link_target)
    except OSError:
        raise WorkspaceError("无法创建 Git 符号链接") from None


def _materialize_git_tree(
    checkout_root: Path,
    identity: _GitIdentity,
    *,
    code_root: Path | None = None,
) -> None:
    destination_root = checkout_root if code_root is None else code_root
    deadline = time.monotonic() + _GIT_COMMAND_TIMEOUT_SECONDS
    entries = _git_tree_entries(identity, deadline=deadline)
    for entry in entries:
        destination = _safe_git_destination(destination_root, entry.relative_path)
        if entry.object_type in {"tree", "commit"}:
            destination.mkdir(parents=True, exist_ok=True)
    symlink_enabled = _git_symlinks_enabled(checkout_root, deadline=deadline)
    _materialize_git_blobs(
        destination_root,
        identity,
        (entry for entry in entries if entry.object_type == "blob"),
        symlink_enabled=symlink_enabled,
        deadline=deadline,
    )
    _run_git(
        checkout_root,
        ("read-tree", identity.revision),
        timeout_seconds=_remaining_git_time(deadline),
    )


def _registered_worktree_matches(
    identity: _GitIdentity,
    checkout_root: Path,
) -> bool:
    try:
        result = _run_git(
            identity.top_level,
            ("worktree", "list", "--porcelain"),
        )
    except WorkspaceError:
        return False
    records: list[dict[str, str]] = []
    for block in result.stdout.split("\n\n"):
        record: dict[str, str] = {}
        for line in block.splitlines():
            key, separator, value = line.partition(" ")
            record[key] = value if separator else ""
        if record:
            records.append(record)
    for candidate in records:
        try:
            candidate_path = _normalize_path(Path(candidate["worktree"]))
            candidate_head = candidate["HEAD"]
        except (KeyError, WorkspaceError):
            continue
        if candidate_path == checkout_root and candidate_head == identity.revision:
            return True
    return False


def _snapshot_entries(source_root: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    pending = [source_root]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            raise WorkspaceError("无法读取快照源码目录") from exc
        for child in children:
            relative = child.relative_to(source_root)
            if len(relative.parts) == 1 and child.name in _SNAPSHOT_EXCLUDED_TOP_LEVEL:
                continue
            try:
                mode = child.lstat().st_mode
            except OSError as exc:
                raise WorkspaceError("无法检查快照源码条目") from exc
            relative_text = relative.as_posix()
            if stat.S_ISLNK(mode):
                try:
                    target = os.readlink(child)
                    resolved_target = child.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise WorkspaceError("快照包含无效符号链接") from exc
                if not _path_is_within(resolved_target, source_root):
                    raise WorkspaceError("快照符号链接逃出源码目录")
                entries.append(
                    {"path": relative_text, "target": target, "type": "symlink"}
                )
            elif stat.S_ISDIR(mode):
                entries.append({"path": relative_text, "type": "directory"})
                pending.append(child)
            elif stat.S_ISREG(mode):
                try:
                    digest = hashlib.sha256()
                    size = 0
                    with child.open("rb") as stream:
                        while chunk := stream.read(_HASH_CHUNK_SIZE_BYTES):
                            digest.update(chunk)
                            size += len(chunk)
                except OSError as exc:
                    raise WorkspaceError("无法读取快照源码文件") from exc
                entries.append(
                    {
                        "path": relative_text,
                        "sha256": digest.hexdigest(),
                        "size": size,
                        "type": "file",
                    }
                )
            else:
                raise WorkspaceError("快照包含不支持的特殊文件")
    return sorted(entries, key=lambda entry: cast(str, entry["path"]))


def _snapshot_manifest(source_root: Path) -> tuple[bytes, str, list[dict[str, object]]]:
    entries = _snapshot_entries(source_root)
    payload = _canonical_json_bytes(
        {"entries": entries, "schema_version": WORKSPACE_SCHEMA_VERSION}
    )
    return payload, hashlib.sha256(payload).hexdigest(), entries


def _copy_snapshot(
    source_root: Path,
    destination: Path,
    entries: Iterable[Mapping[str, object]],
) -> None:
    for entry in entries:
        relative = Path(cast(str, entry["path"]))
        source = source_root / relative
        target = destination / relative
        entry_type = entry["type"]
        if entry_type == "directory":
            target.mkdir(parents=True, exist_ok=False)
        elif entry_type == "symlink":
            target.parent.mkdir(parents=True, exist_ok=True)
            if os.readlink(source) != entry["target"]:
                raise WorkspaceError("复制期间快照符号链接发生变化")
            target.symlink_to(cast(str, entry["target"]))
        elif entry_type == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                mode = source.lstat().st_mode
            except OSError as exc:
                raise WorkspaceError("复制期间快照文件不可用") from exc
            if not stat.S_ISREG(mode):
                raise WorkspaceError("复制期间快照文件类型发生变化")
            shutil.copy2(source, target, follow_symlinks=False)
        else:  # pragma: no cover - 仅内部清单可达
            raise WorkspaceError("快照清单条目类型无效")
    copied_payload, _, _ = _snapshot_manifest(destination)
    expected_payload = _canonical_json_bytes(
        {"entries": list(entries), "schema_version": WORKSPACE_SCHEMA_VERSION}
    )
    if copied_payload != expected_payload:
        raise WorkspaceError("复制期间快照内容发生变化")


def _read_strict_metadata(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file() or _normalize_path(path) != path:
        raise WorkspaceError("工作区元数据缺失或类型无效")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError("工作区元数据无效") from exc
    if type(value) is not dict:
        raise WorkspaceError("工作区元数据无效")
    return cast(dict[str, object], value)


class WorkspaceManager:
    """创建或严格复用按工程、工单隔离的工作区。"""

    def __init__(
        self,
        source_root: Path,
        data_root: Path,
        project_id: str,
        *,
        extra_protected_paths: Iterable[Path] = (),
        isolate_git_metadata: bool = False,
    ) -> None:
        _validated_bytes("project_id", project_id)
        self.source_root = _normalize_path(source_root)
        self.data_root = _normalize_path(data_root)
        if _paths_overlap(self.source_root, self.data_root):
            raise WorkspaceError("源码目录与数据目录不得重叠")
        self.project_id = project_id
        self.extra_protected_paths = tuple(
            _normalize_path(path) for path in extra_protected_paths
        )
        if isolate_git_metadata and os.name != "posix":
            raise WorkspaceError("当前平台不支持 Git 元数据分离")
        self.isolate_git_metadata = isolate_git_metadata

    def open(self, ticket_id: str, run_id: str) -> WorkspaceSession:
        lease = TicketLease.acquire(self.data_root, self.project_id, ticket_id, run_id)
        created_ticket_root: Path | None = None
        try:
            if self.source_root.is_symlink() or not self.source_root.is_dir():
                raise WorkspaceError("源码路径必须是已存在的目录")
            git_identity = _detect_git(self.source_root)
            kind: Literal["git_worktree", "snapshot"] = (
                "git_worktree" if git_identity is not None else "snapshot"
            )
            workspaces_root = self.data_root / "workspaces"
            _ensure_managed_directory(workspaces_root, parent=self.data_root)
            project_root = workspaces_root / _identity_hash(self.project_id)
            _ensure_managed_directory(project_root, parent=workspaces_root)
            ticket_root = project_root / _identity_hash(ticket_id)
            ticket_exists = ticket_root.exists() or ticket_root.is_symlink()
            if ticket_exists:
                _ensure_managed_directory(
                    ticket_root, parent=project_root, create=False
                )
            checkout_root = ticket_root / "checkout"
            runtime_root = ticket_root / "runtime"
            receipts_root = ticket_root / "receipts"
            manifest_path = ticket_root / "workspace.json"

            if ticket_exists:
                if not manifest_path.exists() and not manifest_path.is_symlink():
                    raise WorkspaceError("工单工作区已存在但缺少可信元数据")
                metadata = _read_strict_metadata(manifest_path)
                return self._reuse(
                    ticket_id,
                    run_id,
                    kind,
                    git_identity,
                    lease,
                    ticket_root,
                    checkout_root,
                    runtime_root,
                    receipts_root,
                    manifest_path,
                    metadata,
                )

            ticket_root.mkdir()
            created_ticket_root = ticket_root
            _ensure_managed_directory(ticket_root, parent=project_root)
            if git_identity is not None:
                metadata, owned_directories = self._create_git(
                    ticket_id,
                    ticket_root,
                    checkout_root,
                    runtime_root,
                    receipts_root,
                    git_identity,
                )
            else:
                metadata, owned_directories = self._create_snapshot(
                    ticket_id,
                    ticket_root,
                    checkout_root,
                    runtime_root,
                    receipts_root,
                )
            try:
                _write_atomic(manifest_path, _canonical_json_bytes(metadata))
            except Exception:
                self._cleanup_created_workspace(
                    kind,
                    git_identity,
                    ticket_root,
                    checkout_root,
                    runtime_root,
                    receipts_root,
                    owned_directories,
                )
                raise
            return self._session(
                ticket_id,
                run_id,
                kind,
                git_identity,
                lease,
                checkout_root,
                runtime_root,
                receipts_root,
                manifest_path,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001 - 公开边界统一清理并归一化异常
            if created_ticket_root is not None:
                try:
                    created_ticket_root.rmdir()
                except OSError:
                    # 仅删除确认为本次创建且已空的根；未知内容必须保留。
                    pass
            try:
                lease.release()
            except WorkspaceError:
                pass
            if isinstance(exc, WorkspaceError):
                raise WorkspaceError(str(exc)) from None
            raise WorkspaceError("无法打开隔离工作区") from None

    def _cleanup_created_workspace(
        self,
        kind: Literal["git_worktree", "snapshot"],
        git_identity: _GitIdentity | None,
        ticket_root: Path,
        checkout_root: Path,
        runtime_root: Path,
        receipts_root: Path,
        owned_directories: Mapping[Path, _PathIdentity],
    ) -> None:
        quarantined_checkout: Path | None = None
        for path in (checkout_root, runtime_root, receipts_root):
            try:
                quarantined = _quarantine_owned_tree(
                    path,
                    owned_directories.get(path),
                    self.data_root,
                )
                if path == checkout_root:
                    quarantined_checkout = quarantined
            except WorkspaceError:
                pass
        if (
            kind == "git_worktree"
            and git_identity is not None
            and quarantined_checkout is not None
        ):
            try:
                _run_git(
                    git_identity.top_level,
                    ("worktree", "remove", "--force", str(checkout_root)),
                )
            except WorkspaceError:
                pass

    def _common_metadata(
        self,
        ticket_id: str,
        kind: Literal["git_worktree", "snapshot"],
        checkout_root: Path,
        runtime_root: Path,
        receipts_root: Path,
    ) -> dict[str, object]:
        return {
            "checkout_root": str(checkout_root),
            "kind": kind,
            "project_id": self.project_id,
            "receipts_root": str(receipts_root),
            "runtime_root": str(runtime_root),
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "source_root": str(self.source_root),
            "ticket_id": ticket_id,
        }

    def _create_git(
        self,
        ticket_id: str,
        ticket_root: Path,
        checkout_root: Path,
        runtime_root: Path,
        receipts_root: Path,
        identity: _GitIdentity,
    ) -> tuple[dict[str, object], dict[Path, _PathIdentity]]:
        registered = False
        owned_directories: dict[Path, _PathIdentity] = {}
        try:
            if checkout_root.exists() or checkout_root.is_symlink():
                raise WorkspaceError("checkout 路径冲突")
            _run_git(
                identity.top_level,
                (
                    "worktree",
                    "add",
                    "--detach",
                    "--no-checkout",
                    str(checkout_root),
                    identity.revision,
                ),
            )
            registered = True
            owned_directories[checkout_root] = _capture_directory_identity(
                checkout_root
            )
            code_root = checkout_root / "code" if self.isolate_git_metadata else None
            if code_root is not None:
                code_root.mkdir()
                _materialize_git_tree(checkout_root, identity, code_root=code_root)
            else:
                _materialize_git_tree(checkout_root, identity)
            git_dir_result = _run_git(checkout_root, ("rev-parse", "--git-dir"))
            git_worktree_dir = _git_path(git_dir_result.stdout.strip(), checkout_root)
            git_worktree_identity = uuid.uuid4().hex
            _write_atomic(
                git_worktree_dir / "icode-workspace-identity",
                git_worktree_identity.encode("ascii"),
            )
            runtime_root.mkdir()
            owned_directories[runtime_root] = _capture_directory_identity(runtime_root)
            receipts_root.mkdir()
            owned_directories[receipts_root] = _capture_directory_identity(
                receipts_root
            )
            metadata = self._common_metadata(
                ticket_id,
                "git_worktree",
                checkout_root,
                runtime_root,
                receipts_root,
            )
            metadata.update(
                {
                    "git_common_dir": str(identity.common_dir),
                    "git_revision": identity.revision,
                    "git_top_level": str(identity.top_level),
                    "git_worktree_git_dir": str(git_worktree_dir),
                    "git_worktree_identity": git_worktree_identity,
                    "source_relative_path": identity.relative_source.as_posix(),
                }
            )
            if code_root is not None:
                metadata["isolated_code_root"] = str(code_root)
            return metadata, owned_directories
        except Exception:
            checkout_identity = owned_directories.get(checkout_root)
            quarantined_checkout: Path | None = None
            if registered:
                try:
                    quarantined_checkout = _quarantine_owned_tree(
                        checkout_root,
                        checkout_identity,
                        self.data_root,
                    )
                except WorkspaceError:
                    pass
            for path in (runtime_root, receipts_root):
                try:
                    _quarantine_owned_tree(
                        path,
                        owned_directories.get(path),
                        self.data_root,
                    )
                except WorkspaceError:
                    pass
            if registered and quarantined_checkout is not None:
                try:
                    _run_git(
                        identity.top_level,
                        ("worktree", "remove", "--force", str(checkout_root)),
                    )
                except WorkspaceError:
                    pass
            raise

    def _create_snapshot(
        self,
        ticket_id: str,
        ticket_root: Path,
        checkout_root: Path,
        runtime_root: Path,
        receipts_root: Path,
    ) -> tuple[dict[str, object], dict[Path, _PathIdentity]]:
        temporary_checkout = ticket_root / f".checkout-{uuid.uuid4().hex}.tmp"
        owned_directories: dict[Path, _PathIdentity] = {}
        try:
            if checkout_root.exists() or checkout_root.is_symlink():
                raise WorkspaceError("checkout 路径冲突")
            manifest_payload, manifest_hash, entries = _snapshot_manifest(
                self.source_root
            )
            temporary_checkout.mkdir()
            owned_directories[temporary_checkout] = _capture_directory_identity(
                temporary_checkout
            )
            _copy_snapshot(self.source_root, temporary_checkout, entries)
            if checkout_root.exists() or checkout_root.is_symlink():
                raise WorkspaceError("checkout 路径冲突")
            temporary_checkout.rename(checkout_root)
            owned_directories[checkout_root] = owned_directories.pop(temporary_checkout)
            runtime_root.mkdir()
            owned_directories[runtime_root] = _capture_directory_identity(runtime_root)
            receipts_root.mkdir()
            owned_directories[receipts_root] = _capture_directory_identity(
                receipts_root
            )
            snapshot_manifest_path = runtime_root / "snapshot-manifest.json"
            _write_atomic(snapshot_manifest_path, manifest_payload)
            metadata = self._common_metadata(
                ticket_id,
                "snapshot",
                checkout_root,
                runtime_root,
                receipts_root,
            )
            metadata.update(
                {
                    "snapshot_manifest_path": str(snapshot_manifest_path),
                    "snapshot_manifest_sha256": manifest_hash,
                }
            )
            return metadata, owned_directories
        except Exception:
            for path in (
                temporary_checkout,
                checkout_root,
                runtime_root,
                receipts_root,
            ):
                try:
                    _quarantine_owned_tree(
                        path,
                        owned_directories.get(path),
                        self.data_root,
                    )
                except WorkspaceError:
                    pass
            raise

    def _reuse(
        self,
        ticket_id: str,
        run_id: str,
        kind: Literal["git_worktree", "snapshot"],
        git_identity: _GitIdentity | None,
        lease: TicketLease,
        ticket_root: Path,
        checkout_root: Path,
        runtime_root: Path,
        receipts_root: Path,
        manifest_path: Path,
        metadata: dict[str, object],
    ) -> WorkspaceSession:
        for directory in (checkout_root, runtime_root, receipts_root):
            _ensure_managed_directory(directory, parent=ticket_root, create=False)
        layered_git = (
            kind == "git_worktree" and set(metadata) == _LAYERED_GIT_METADATA_FIELDS
        )
        if kind == "git_worktree" and layered_git != self.isolate_git_metadata:
            raise WorkspaceError("Git 元数据分离工作区格式不匹配")
        expected_fields = (
            (_LAYERED_GIT_METADATA_FIELDS if layered_git else _GIT_METADATA_FIELDS)
            if kind == "git_worktree" else _SNAPSHOT_METADATA_FIELDS
        )
        if set(metadata) != expected_fields:
            raise WorkspaceError("工作区元数据字段不匹配")
        if any(
            type(metadata[field]) is not str
            for field in expected_fields - {"schema_version"}
        ):
            raise WorkspaceError("工作区元数据字段类型无效")
        if type(metadata["schema_version"]) is not int:
            raise WorkspaceError("工作区元数据版本类型无效")
        expected = self._common_metadata(
            ticket_id, kind, checkout_root, runtime_root, receipts_root
        )
        if kind == "git_worktree":
            if git_identity is None:  # pragma: no cover - 由 kind 推导
                raise WorkspaceError("Git 工作区身份缺失")
            git_file = checkout_root / ".git"
            if (
                git_file.is_symlink()
                or not git_file.is_file()
                or _normalize_path(git_file) != git_file
            ):
                raise WorkspaceError("Git worktree 管理文件缺失")
            if layered_git:
                code_root = checkout_root / "code"
                try:
                    _ensure_managed_directory(
                        code_root, parent=checkout_root, create=False
                    )
                except WorkspaceError:
                    raise WorkspaceError("Git 分层代码目录无效") from None
                expected["isolated_code_root"] = str(code_root)
            checkout_common_result = _run_git(
                checkout_root, ("rev-parse", "--git-common-dir")
            )
            checkout_git_dir_result = _run_git(
                checkout_root, ("rev-parse", "--git-dir")
            )
            checkout_head_result = _run_git(checkout_root, ("rev-parse", "HEAD"))
            checkout_common = _git_path(
                checkout_common_result.stdout.strip(), checkout_root
            )
            checkout_git_dir = _git_path(
                checkout_git_dir_result.stdout.strip(), checkout_root
            )
            checkout_head = checkout_head_result.stdout.strip()
            identity_path = checkout_git_dir / "icode-workspace-identity"
            if identity_path.is_symlink() or not identity_path.is_file():
                raise WorkspaceError("Git worktree 所有权身份缺失")
            try:
                checkout_identity = identity_path.read_text(encoding="ascii")
            except (OSError, UnicodeError) as exc:
                raise WorkspaceError("Git worktree 所有权身份无效") from exc
            if (
                checkout_common != git_identity.common_dir
                or checkout_head != git_identity.revision
                or not _registered_worktree_matches(git_identity, checkout_root)
            ):
                raise WorkspaceError("Git worktree 注册身份漂移")
            expected.update(
                {
                    "git_common_dir": str(git_identity.common_dir),
                    "git_revision": git_identity.revision,
                    "git_top_level": str(git_identity.top_level),
                    "git_worktree_git_dir": str(checkout_git_dir),
                    "git_worktree_identity": checkout_identity,
                    "source_relative_path": git_identity.relative_source.as_posix(),
                }
            )
        else:
            snapshot_manifest_path = runtime_root / "snapshot-manifest.json"
            current_payload, current_hash, _ = _snapshot_manifest(self.source_root)
            expected.update(
                {
                    "snapshot_manifest_path": str(snapshot_manifest_path),
                    "snapshot_manifest_sha256": current_hash,
                }
            )
            if (
                snapshot_manifest_path.is_symlink()
                or not snapshot_manifest_path.is_file()
            ):
                raise WorkspaceError("快照基线清单缺失")
            try:
                stored_payload = snapshot_manifest_path.read_bytes()
            except OSError as exc:
                raise WorkspaceError("无法读取快照基线清单") from exc
            if (
                stored_payload != current_payload
                or hashlib.sha256(stored_payload).hexdigest() != current_hash
            ):
                raise WorkspaceError("快照基线清单身份不匹配")
        if metadata != expected:
            raise WorkspaceError("工作区身份与当前请求不匹配")
        if kind == "git_worktree":
            assert git_identity is not None
            code_root = checkout_root / "code" if layered_git else checkout_root
            workspace_root = code_root / git_identity.relative_source
            if not workspace_root.is_dir() or workspace_root.is_symlink():
                raise WorkspaceError("Git 工作区源码子目录缺失")
        return self._session(
            ticket_id,
            run_id,
            kind,
            git_identity,
            lease,
            checkout_root,
            runtime_root,
            receipts_root,
            manifest_path,
            metadata=metadata,
        )

    def _session(
        self,
        ticket_id: str,
        run_id: str,
        kind: Literal["git_worktree", "snapshot"],
        git_identity: _GitIdentity | None,
        lease: TicketLease,
        checkout_root: Path,
        runtime_root: Path,
        receipts_root: Path,
        manifest_path: Path,
        *,
        metadata: Mapping[str, object],
    ) -> WorkspaceSession:
        relative_source = git_identity.relative_source if git_identity else Path()
        code_root = (
            checkout_root / "code"
            if git_identity and self.isolate_git_metadata else checkout_root
        )
        workspace_root = _normalize_path(code_root / relative_source)
        protected = {
            self.source_root,
            _normalize_path(self.source_root / ".git"),
            _normalize_path(self.source_root / ".icode_output"),
            _normalize_path(checkout_root / ".git"),
            _normalize_path(runtime_root),
            _normalize_path(receipts_root),
            *self.extra_protected_paths,
        }
        if git_identity is not None:
            protected.update(
                {
                    git_identity.common_dir,
                    _normalize_path(git_identity.top_level / ".git"),
                }
            )
        git_status_identity = None
        if kind == "git_worktree" and self.isolate_git_metadata:
            if git_identity is None:
                raise WorkspaceError("Git 状态身份缺失")
            raw_git_dir = metadata.get("git_worktree_git_dir")
            raw_identity_token = metadata.get("git_worktree_identity")
            if not isinstance(raw_git_dir, str) or not isinstance(raw_identity_token, str):
                raise WorkspaceError("Git 状态身份元数据无效")
            code_root = _normalize_path(checkout_root / "code")
            normalized_checkout = _normalize_path(checkout_root)
            normalized_git_dir = _normalize_path(Path(raw_git_dir))
            normalized_common_dir = _normalize_path(git_identity.common_dir)
            filesystem_paths: dict[Path, Literal["file", "directory"]] = {}
            for path in (
                normalized_checkout,
                code_root,
                workspace_root,
                _normalize_path(git_identity.top_level),
                normalized_common_dir,
                normalized_git_dir,
            ):
                filesystem_paths[path] = "directory"
            for path in (
                normalized_checkout / ".git",
                normalized_git_dir / "commondir",
                normalized_git_dir / "HEAD",
                normalized_git_dir / "icode-workspace-identity",
            ):
                filesystem_paths[path] = "file"
            git_status_identity = GitWorkspaceIdentity(
                checkout_root=normalized_checkout,
                code_root=code_root,
                workspace_root=workspace_root,
                top_level=_normalize_path(git_identity.top_level),
                common_dir=normalized_common_dir,
                git_dir=normalized_git_dir,
                revision=git_identity.revision,
                identity_token=raw_identity_token,
                source_relative_path=git_identity.relative_source,
                filesystem_identities=tuple(
                    _capture_git_path_identity(path, kind)
                    for path, kind in sorted(
                        filesystem_paths.items(), key=lambda item: str(item[0])
                    )
                ),
            )
        return WorkspaceSession(
            project_id=self.project_id,
            ticket_id=ticket_id,
            run_id=run_id,
            kind=kind,
            source_root=self.source_root,
            workspace_root=workspace_root,
            runtime_root=_normalize_path(runtime_root),
            receipts_root=_normalize_path(receipts_root),
            manifest_path=_normalize_path(manifest_path),
            protected_paths=tuple(sorted(protected, key=str)),
            lease=lease,
            git_status_identity=git_status_identity,
        )
