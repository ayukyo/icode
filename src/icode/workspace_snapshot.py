"""宿主侧工作区改动快照；不能跟随不可信源码中的链接。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path


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
