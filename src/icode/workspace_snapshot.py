"""宿主侧工作区改动快照；不能跟随不可信源码中的链接。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path


_MAX_GIT_TREE_ENTRIES = 250_000
_MAX_GIT_TREE_DEPTH = 128
_MAX_GIT_TREE_BYTES = 256 * 1024 * 1024


class WorktreeTreeUnavailable(RuntimeError):
    """当前工作树不能安全、完整地表示为 Git tree。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def snapshot_workspace(root: Path) -> dict[str, str]:
    """散列工作区实体与 Git 相关类型/模式；绝不由宿主跟随读取链接。

    跳过 `.icode_output` 与 `__pycache__`：前者是工单账本，后者是宿主
    Python 编译产物——两者都不是模型改动，不能进入 diff 证据。
    """
    root = Path(root)
    out: dict[str, str] = {}
    if os.name == "posix":
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

        def scan(directory_fd: int, parts: tuple[str, ...]) -> None:
            # 所有子路径相对已经打开的目录 fd，防止检查后把祖先换成链接。
            with os.scandir(directory_fd) as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    if entry.name == ".icode_output" or entry.name == "__pycache__":
                        continue
                    child_parts = (*parts, entry.name)
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISDIR(mode):
                        child_fd = os.open(entry.name, directory_flags, dir_fd=directory_fd)
                        try:
                            scan(child_fd, child_parts)
                        finally:
                            os.close(child_fd)
                    elif stat.S_ISLNK(mode):
                        target = os.readlink(entry.name, dir_fd=directory_fd)
                        out[Path(*child_parts).as_posix()] = _entry_hash(
                            "symlink", "120000", os.fsencode(target),
                        )
                    elif stat.S_ISREG(mode):
                        file_fd = os.open(
                            entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                            dir_fd=directory_fd,
                        )
                        with os.fdopen(file_fd, "rb") as stream:
                            opened_mode = os.fstat(stream.fileno()).st_mode
                            if not stat.S_ISREG(opened_mode):
                                raise OSError("snapshot file type changed during scan")
                            executable = opened_mode & (
                                stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                            )
                            git_mode = "100755" if executable else "100644"
                            digest = hashlib.sha256(_entry_hash_prefix("file", git_mode))
                            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                                digest.update(chunk)
                            out[Path(*child_parts).as_posix()] = digest.hexdigest()

        root_fd = os.open(root, directory_flags)
        try:
            scan(root_fd, ())
        finally:
            os.close(root_fd)
        return out

    # Windows 暂无目录 fd + O_NOFOLLOW：不跟随链接/接合点，且自动模式
    # 仍保持阻断。路径离开根或类型在扫描中改变时按错误处理。
    if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
        raise OSError("snapshot root must be a real directory")
    anchor = root.resolve(strict=True)
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if ".icode_output" in rel_parts or "__pycache__" in rel_parts:
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            out[relative] = _entry_hash(
                "symlink", "120000", os.fsencode(os.readlink(path)),
            )
        elif getattr(path, "is_junction", lambda: False)():
            continue
        elif path.is_file():
            path.resolve(strict=True).relative_to(anchor)
            out[relative] = _entry_hash("file", "100644", path.read_bytes())
    return out


def worktree_git_tree_oid(root: Path, *, object_format: str) -> str:
    """只读计算工作树 Git 文件投影的 tree OID，不调用 Git 或写索引/对象库。

    该 OID 表示目录项、文件原始字节、POSIX 可执行位和符号链接目标；
    它不是 clean-filter 转换后的结果，也不包含 `.git` 元数据。为了不跟随
    源码中的链接或执行仓库配置中的 helper，本实现只接受 POSIX fd API，
    对嵌套 Git 元数据、特殊文件、扫描竞态和超限工作区均失败关闭。
    """
    if os.name != "posix":
        raise WorktreeTreeUnavailable("unsupported_platform")
    if object_format not in ("sha1", "sha256"):
        raise WorktreeTreeUnavailable("unsupported_object_format")

    root = Path(root)
    try:
        if root.is_symlink():
            raise WorktreeTreeUnavailable("workspace_root_is_link")
        root = Path(os.path.abspath(root))
        root_status = os.stat(root, follow_symlinks=False)
        if not stat.S_ISDIR(root_status.st_mode):
            raise WorktreeTreeUnavailable("workspace_root_not_directory")
        root_fd = os.open(
            root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
    except WorktreeTreeUnavailable:
        raise
    except OSError:
        raise WorktreeTreeUnavailable("workspace_unavailable") from None

    entry_counter = [0]
    byte_counter = [0]
    try:
        root_fd_status = os.fstat(root_fd)
        if not _same_filesystem_entry(root_status, root_fd_status):
            raise WorktreeTreeUnavailable("filesystem_changed")
        tree_digest = _hash_worktree_tree(
            root_fd, is_root=True, depth=0, algorithm=object_format,
            entry_counter=entry_counter, byte_counter=byte_counter,
        )
        if tree_digest is None:
            raise WorktreeTreeUnavailable("root_tree_unavailable")
        return tree_digest.hex()
    except WorktreeTreeUnavailable:
        raise
    except OSError:
        raise WorktreeTreeUnavailable("filesystem_unavailable") from None
    finally:
        os.close(root_fd)


def _increment_tree_entry_count(counter: list[int]) -> None:
    counter[0] += 1
    if counter[0] > _MAX_GIT_TREE_ENTRIES:
        raise WorktreeTreeUnavailable("worktree_too_large")


def _same_filesystem_entry(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_mode == after.st_mode
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
        and before.st_ctime_ns == after.st_ctime_ns
    )


def _git_object_digest(algorithm: str, kind: bytes, size: int):
    digest = hashlib.new(algorithm)
    digest.update(kind + b" " + str(size).encode("ascii") + b"\0")
    return digest


def _hash_worktree_blob_fd(
    descriptor: int,
    status: os.stat_result,
    algorithm: str,
    byte_counter: list[int],
) -> bytes:
    byte_counter[0] += status.st_size
    if status.st_size < 0 or byte_counter[0] > _MAX_GIT_TREE_BYTES:
        raise WorktreeTreeUnavailable("worktree_too_large")
    digest = _git_object_digest(algorithm, b"blob", status.st_size)
    bytes_read = 0
    with os.fdopen(os.dup(descriptor), "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            bytes_read += len(chunk)
            digest.update(chunk)
    after = os.fstat(descriptor)
    if bytes_read != status.st_size or not _same_filesystem_entry(status, after):
        raise WorktreeTreeUnavailable("filesystem_changed")
    return digest.digest()


def _hash_worktree_tree(
    directory_fd: int,
    *,
    is_root: bool,
    depth: int,
    algorithm: str,
    entry_counter: list[int],
    byte_counter: list[int],
) -> bytes | None:
    if depth > _MAX_GIT_TREE_DEPTH:
        raise WorktreeTreeUnavailable("worktree_too_deep")
    initial_status = os.fstat(directory_fd)
    entries: list[tuple[bytes, bool, bytes, bytes]] = []

    with os.scandir(directory_fd) as iterator:
        children = sorted(iterator, key=lambda child: os.fsencode(child.name))

    for child in children:
        name = os.fsencode(child.name)
        if is_root and name == b".git":
            # Repository metadata is not part of a Git tree. Never descend into it.
            continue
        if name == b".git":
            raise WorktreeTreeUnavailable("nested_git_metadata")
        if not name or b"/" in name or b"\0" in name:
            raise WorktreeTreeUnavailable("invalid_git_path")

        _increment_tree_entry_count(entry_counter)
        try:
            before = child.stat(follow_symlinks=False)
        except OSError:
            raise WorktreeTreeUnavailable("filesystem_changed") from None
        mode = before.st_mode

        if stat.S_ISDIR(mode):
            child_fd = os.open(
                child.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
            try:
                opened = os.fstat(child_fd)
                if not _same_filesystem_entry(before, opened):
                    raise WorktreeTreeUnavailable("filesystem_changed")
                oid = _hash_worktree_tree(
                    child_fd, is_root=False, depth=depth + 1,
                    algorithm=algorithm, entry_counter=entry_counter,
                    byte_counter=byte_counter,
                )
                if not _same_filesystem_entry(opened, os.fstat(child_fd)):
                    raise WorktreeTreeUnavailable("filesystem_changed")
            finally:
                os.close(child_fd)
            if oid is not None:
                entries.append((name, True, b"40000", oid))
        elif stat.S_ISREG(mode):
            descriptor = os.open(
                child.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or not _same_filesystem_entry(before, opened)
                ):
                    raise WorktreeTreeUnavailable("filesystem_changed")
                executable = opened.st_mode & (
                    stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
                git_mode = b"100755" if executable else b"100644"
                oid = _hash_worktree_blob_fd(
                    descriptor, opened, algorithm, byte_counter,
                )
            finally:
                os.close(descriptor)
            entries.append((name, False, git_mode, oid))
        elif stat.S_ISLNK(mode):
            target = os.readlink(child.name, dir_fd=directory_fd)
            try:
                after = os.stat(child.name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                raise WorktreeTreeUnavailable("filesystem_changed") from None
            if not _same_filesystem_entry(before, after):
                raise WorktreeTreeUnavailable("filesystem_changed")
            target_bytes = os.fsencode(target)
            oid = _git_object_digest(algorithm, b"blob", len(target_bytes))
            oid.update(target_bytes)
            entries.append((name, False, b"120000", oid.digest()))
        else:
            raise WorktreeTreeUnavailable("unsupported_filesystem_entry")

    if not _same_filesystem_entry(initial_status, os.fstat(directory_fd)):
        raise WorktreeTreeUnavailable("filesystem_changed")

    # Git compares a directory as if its name ended in '/', not as a NUL-terminated
    # non-directory entry. This matters for siblings such as `foo` and `foo.bar`.
    entries.sort(key=lambda entry: entry[0] + (b"/" if entry[1] else b""))
    if not entries and not is_root:
        # Git trees cannot preserve empty directories.
        return None
    tree_body = b"".join(
        mode + b" " + name + b"\0" + oid
        for name, _is_directory, mode, oid in entries
    )
    return _hash_git_tree_body(algorithm, tree_body)


def _hash_git_tree_body(algorithm: str, tree_body: bytes) -> bytes:
    digest = _git_object_digest(algorithm, b"tree", len(tree_body))
    digest.update(tree_body)
    return digest.digest()


def _entry_hash_prefix(entry_type: str, git_mode: str) -> bytes:
    """版本化地分隔文件类型/模式，避免相同字节产生不同 Git 项的碰撞。"""
    return f"icode-workspace-entry-v2\0{entry_type}\0{git_mode}\0".encode("ascii")


def _entry_hash(entry_type: str, git_mode: str, content: bytes) -> str:
    digest = hashlib.sha256(_entry_hash_prefix(entry_type, git_mode))
    digest.update(content)
    return digest.hexdigest()


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    names = set(before) | set(after)
    return sorted(name for name in names if before.get(name) != after.get(name))


def diff_fingerprint(before: dict[str, str], after: dict[str, str]) -> str:
    """把一次改动（相对基线）绑定成确定性指纹。

    只依赖改动前后每条路径的 sha256（不含正文），用于把验证证据
    绑定到「具体某次 diff」：同一结果文件在不同基线下的改动会得到
    不同指纹；新增/删除/修改三种状态由前后哈希的缺失/变化区分。
    未变化的路径不进入指纹（与 `changed_files` 的集合一致）。
    """
    entries: list[dict[str, str]] = []
    for name in sorted(set(before) | set(after)):
        old = before.get(name)
        new = after.get(name)
        if old == new:
            continue
        entries.append({
            "path": name,
            "status": "A" if old is None else "D" if new is None else "M",
            "before": old or "",
            "after": new or "",
        })
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_fingerprint(snapshot: dict[str, str]) -> str:
    """为完整工作区内容快照生成稳定指纹，不只覆盖相对基线的改动项。"""
    entries = [
        {"path": path, "sha256": digest}
        for path, digest in sorted(snapshot.items())
    ]
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
