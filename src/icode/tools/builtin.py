"""内置工具集（最小集）。

- 读：`read_file` / `glob` / `grep`（grep 用纯 Python 实现，**不依赖 ripgrep**，跨平台一致）
- 写：`write_file` / `edit_file`（edit 要求 old 精确唯一匹配，避免误改）
- 执行：`run_command`（**无 shell**，参数列表；危险命令由 guard 拦截）

明确不含：任意 shell 拼接、网络访问、包安装。
"""

from __future__ import annotations

import fnmatch
import hashlib
import heapq
import json
import os
import re
import secrets
import stat
import sys
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from ..artifact_broker import ArtifactAccessError
from ..execution_broker import (
    execute_linux_violation_observed_command,
    execute_policy_command,
)
from ..git_broker import GitStatusUnavailable, execute_git_status
from ..isolation import LandlockSandbox
from ..sandbox_policy import NetworkMode, SandboxPolicy
from ..workspace import GitWorkspaceIdentity, WorkspaceSession
from ..workspace_snapshot import changed_files, snapshot_workspace
from .base import (
    OPCLASS_MANAGED_WRITE,
    OPCLASS_READ_ONLY,
    POLICY_DENIED_USER_MESSAGE,
    Tool,
    ToolContext,
    ToolRegistry,
    ToolResult,
    _params,
)

MAX_GLOB_HITS = 300
MAX_GREP_HITS = 120
# 扫描 grep 时跳过的目录（避免把依赖/缓存扫进来）
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", ".mypy_cache"}


# ---------------------------------------------------------------------------
# 读
# ---------------------------------------------------------------------------


def read_file(ctx: ToolContext, path: str, offset: int = 1, limit: int = 400) -> ToolResult:
    requested = ctx.resolve(path)
    try:
        target = requested.resolve(strict=True)
    except (OSError, RuntimeError):
        return ToolResult(False, f"文件不存在：{requested}", {"error": "not_found"})
    if not _policy_allows_read(ctx, target):
        return ToolResult(False, "策略禁止读取该文件", {"error": "read_denied"})
    if not target.is_file():
        return ToolResult(False, f"文件不存在：{requested}", {"error": "not_found"})

    try:
        anchor = _anchored_read_root(ctx, target)
        content = _read_anchored_text(
            anchor, target.relative_to(anchor), errors="replace",
            reject_hardlinks=ctx.read_only_workspace,
        )
    except (OSError, RuntimeError):
        content = None
    if content is None:
        return ToolResult(False, "文件读取失败或类型已变化", {"error": "read_unavailable"})
    lines = content.splitlines()
    start = max(1, int(offset))
    end = min(len(lines), start - 1 + max(1, int(limit)))
    body = "\n".join(f"{i:>5}| {lines[i - 1]}" for i in range(start, end + 1))
    header = f"{target}（共 {len(lines)} 行，显示 {start}-{end}）"
    return ToolResult(
        True,
        f"{header}\n{body}",
        {"path": str(target), "total_lines": len(lines), "start": start, "end": end},
    )


def glob_files(ctx: ToolContext, pattern: str) -> ToolResult:
    if not isinstance(pattern, str) or not pattern or Path(pattern).is_absolute():
        return ToolResult(False, "glob 模式必须是工作区内相对路径",
                          {"error": "invalid_pattern"})
    parts = Path(pattern).parts
    if not parts or ".." in parts:
        return ToolResult(False, "glob 模式不得离开工作区",
                          {"error": "invalid_pattern"})

    try:
        entries = _safe_workspace_entries(ctx)
        try:
            hits = heapq.nsmallest(
                MAX_GLOB_HITS,
                (relative.as_posix() for relative in entries
                 if _glob_matches(relative.parts, parts)),
            )
        finally:
            entries.close()
    except (OSError, RuntimeError):
        return ToolResult(False, "工作区枚举失败，已停止 glob 查询",
                          {"error": "glob_unavailable"})
    if not hits:
        return ToolResult(True, f"无匹配：{pattern}", {"hits": 0})
    return ToolResult(True, "\n".join(hits), {"hits": len(hits)})


def _glob_matches(path: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    @lru_cache(None)
    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern):
            return path_index == len(path)
        if pattern[pattern_index] == "**":
            return match(path_index, pattern_index + 1) or (
                path_index < len(path) and match(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path)
            and fnmatch.fnmatch(path[path_index], pattern[pattern_index])
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)


def _safe_workspace_entries(ctx: ToolContext) -> Iterator[Path]:
    """从固定根枚举，不跟随目录链接；POSIX 使用目录 fd 锚定。"""
    root = ctx.root.resolve(strict=True)

    def fail_walk(error: OSError) -> None:
        raise error

    def allowed(relative: Path) -> bool:
        target = (root / relative).resolve(strict=False)
        if not target.is_relative_to(root):
            return False
        return _policy_allows_read(ctx, target)

    if os.name == "posix":
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with closing(os.fwalk(".", topdown=True, onerror=fail_walk,
                                  follow_symlinks=False, dir_fd=root_fd)) as walker:
                for directory, subdirs, files, directory_fd in walker:
                    parent = Path(directory)
                    candidates = sorted(set(subdirs) | set(files))
                    subdirs[:] = [
                        name for name in sorted(subdirs)
                        if name not in SKIP_DIRS
                        and allowed(parent / name)
                        and stat.S_ISDIR(os.stat(
                            name, dir_fd=directory_fd, follow_symlinks=False,
                        ).st_mode)
                    ]
                    for name in candidates:
                        if name not in SKIP_DIRS:
                            relative = parent / name
                            if allowed(relative):
                                yield relative
        finally:
            os.close(root_fd)
        return

    # Windows 自动策略模式仍阻断；普通会话也不跟随链接/接合点目录。
    for directory, subdirs, files in os.walk(root, topdown=True,
                                             onerror=fail_walk, followlinks=False):
        parent = Path(directory).relative_to(root)
        candidates = sorted(set(subdirs) | set(files))
        subdirs[:] = [
            name for name in sorted(subdirs)
            if name not in SKIP_DIRS
            and not (Path(directory) / name).is_symlink()
            and not getattr(Path(directory) / name, "is_junction", lambda: False)()
            and allowed(parent / name)
        ]
        for name in candidates:
            if name not in SKIP_DIRS:
                relative = parent / name
                if allowed(relative):
                    yield relative


def _policy_allows_read(ctx: ToolContext, target: Path) -> bool:
    try:
        target = Path(target).resolve(strict=False)
        denied_roots = tuple(
            Path(root).resolve(strict=False) for root in ctx.deny_read_roots
        )
    except (OSError, RuntimeError):
        return False
    if any(target.is_relative_to(root) for root in denied_roots):
        return False
    if (ctx.allowed_read_files is not None
            and target not in ctx.allowed_read_files):
        return False
    if ctx.policy is None:
        return True
    return (
        any(target.is_relative_to(root) for root in ctx.policy.read_roots)
        and not any(target.is_relative_to(root) for root in ctx.policy.deny_read_roots)
    )


def _anchored_read_root(ctx: ToolContext, target: Path) -> Path:
    if ctx.policy is not None:
        read_root = max(
            (root for root in ctx.policy.read_roots if target.is_relative_to(root)),
            key=lambda root: len(root.parts),
        )
        return read_root if read_root.is_dir() else read_root.parent
    workspace = ctx.root.resolve(strict=True)
    return workspace if target.is_relative_to(workspace) else target.parent


def _read_anchored_text(
    root: Path,
    relative: Path,
    *,
    errors: str = "ignore",
    reject_hardlinks: bool = False,
) -> str | None:
    """从可信目录读取真实普通文件；祖先与终点均不跟随链接。"""
    if not relative.parts:
        return None
    if os.name == "posix":
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            directory_fd = os.open(root, directory_flags)
        except OSError:
            return None
        try:
            for component in relative.parts[:-1]:
                next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            file_fd = os.open(
                relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory_fd,
            )
            with os.fdopen(file_fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                # 路径白名单无法区分硬链接的另一个目录项；Reviewer 只读白名单
                # 因此只接受单链接 inode，避免外部内容通过别名进入模型上下文。
                if not stat.S_ISREG(info.st_mode) or (
                    reject_hardlinks and info.st_nlink != 1
                ):
                    return None
                return stream.read().decode("utf-8", errors=errors)
        except OSError:
            return None
        finally:
            os.close(directory_fd)

    # Windows 自动模式仍阻断；会话扫描至少拒绝链接/接合点和越界解析。
    target = root
    for component in relative.parts:
        target = target / component
        if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
            return None
    try:
        if target.resolve(strict=True).is_relative_to(root) and target.is_file():
            file_fd = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            with os.fdopen(file_fd, "r", encoding="utf-8", errors=errors) as stream:
                info = os.fstat(stream.fileno())
                # Windows 也必须在已打开的文件句柄上检查链接数，避免仅按名称授权。
                if not stat.S_ISREG(info.st_mode) or (
                    reject_hardlinks and info.st_nlink != 1
                ):
                    return None
                return stream.read()
    except (OSError, RuntimeError):
        pass
    return None


def grep_files(
    ctx: ToolContext,
    pattern: str,
    path: str = ".",
    max_hits: int = MAX_GREP_HITS,
) -> ToolResult:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return ToolResult(False, f"正则非法：{exc}", {"error": "bad_regex"})

    hits: list[str] = []
    base = ctx.resolve(path)
    if base.is_file():
        try:
            target = base.resolve(strict=True)
        except (OSError, RuntimeError):
            target = None
        if target is None:
            targets = []
        elif not _policy_allows_read(ctx, target):
            return ToolResult(False, "策略禁止读取该文件", {"error": "read_denied"})
        else:
            try:
                anchor = _anchored_read_root(ctx, target)
                text = _read_anchored_text(
                    anchor, target.relative_to(anchor),
                    reject_hardlinks=ctx.read_only_workspace,
                )
            except (OSError, RuntimeError):
                text = None
            targets = [(base, text)]
    elif base.is_dir():
        root = base.resolve(strict=True)
        if not _policy_allows_read(ctx, root):
            return ToolResult(False, "策略禁止读取该目录", {"error": "read_denied"})
        scan_ctx = ToolContext(
            root=root, policy=ctx.policy, deny_read_roots=ctx.deny_read_roots,
            read_only_workspace=ctx.read_only_workspace,
            allowed_read_files=ctx.allowed_read_files,
        )
        try:
            entries = _safe_workspace_entries(scan_ctx)
            try:
                relatives = sorted(entries)
            finally:
                entries.close()
        except (OSError, RuntimeError):
            return ToolResult(False, "目录扫描失败，已停止 grep 查询",
                              {"error": "grep_unavailable"})
        targets = ((root / relative, _read_anchored_text(
            root, relative, reject_hardlinks=ctx.read_only_workspace,
        ))
                   for relative in relatives)
    else:
        targets = []

    for f, text in targets:
        if text is None:
            continue
        for no, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                rel = f.relative_to(ctx.root).as_posix() if f.is_relative_to(ctx.root) else f.as_posix()
                hits.append(f"{rel}:{no}: {line.strip()[:200]}")
                if len(hits) >= max_hits:
                    break
        if len(hits) >= max_hits:
            break

    if not hits:
        return ToolResult(True, f"无匹配：{pattern}", {"hits": 0})
    return ToolResult(True, "\n".join(hits), {"hits": len(hits)})


# ---------------------------------------------------------------------------
# 写
# ---------------------------------------------------------------------------


def _write_target(ctx: ToolContext, path: str) -> tuple[Path, Path, Path]:
    workspace = ctx.root.resolve(strict=True)
    target = ctx.resolve(path).resolve(strict=False)
    if not target.is_relative_to(workspace):
        raise PermissionError("写入目标不在工作区")
    if ctx.policy is not None:
        if any(target.is_relative_to(root) for root in ctx.policy.deny_write_roots):
            raise PermissionError("写入目标受策略保护")
        roots = [root for root in ctx.policy.write_roots if target.is_relative_to(root)]
        if not roots:
            raise PermissionError("写入目标不在策略写根")
        anchor = max(roots, key=lambda root: len(root.parts))
    else:
        anchor = workspace
    relative = target.relative_to(anchor)
    if not relative.parts:
        raise PermissionError("不能将写根本身当作文件")
    return target, anchor, relative


def _open_parent_at(anchor: Path, relative: Path, *, create: bool) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_fd = os.open(anchor, flags)
    try:
        for component in relative.parts[:-1]:
            try:
                child_fd = os.open(component, flags, dir_fd=parent_fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                child_fd = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
        return parent_fd
    except BaseException:
        os.close(parent_fd)
        raise


def _regular_at(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(current.st_mode):
        raise PermissionError("写入目标不是普通文件")
    return current


def _atomic_write_at(parent_fd: int, name: str, body: bytes,
                     prior: os.stat_result | None) -> None:
    temporary = f".icode-write-{secrets.token_hex(12)}"
    temporary_fd = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o666, dir_fd=parent_fd,
    )
    try:
        with os.fdopen(temporary_fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            if prior is not None:
                # 保留可执行位，但不把旧文件的 setuid/setgid 权限带到新内容。
                mode = stat.S_IMODE(prior.st_mode) & ~(stat.S_ISUID | stat.S_ISGID)
                os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        current = _regular_at(parent_fd, name)
        if (prior is None) != (current is None):
            raise OSError("写入目标在操作中发生变化")
        if prior is not None and current is not None and (
            prior.st_dev, prior.st_ino, prior.st_mtime_ns, prior.st_size
        ) != (
            current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size
        ):
            raise OSError("写入目标在操作中发生变化")
        os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


def write_file(ctx: ToolContext, path: str, content: str) -> ToolResult:
    try:
        target, anchor, relative = _write_target(ctx, path)
        body = content.encode("utf-8")
        if os.name == "posix":
            parent_fd = _open_parent_at(anchor, relative, create=True)
            try:
                prior = _regular_at(parent_fd, relative.name)
                _atomic_write_at(parent_fd, relative.name, body, prior)
                existed = prior is not None
            finally:
                os.close(parent_fd)
        else:
            if ctx.policy is not None:
                raise PermissionError("Windows 策略写入尚未验证")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise PermissionError("写入目标不是普通文件")
            existed = target.is_file()
            target.write_bytes(body)
    except PermissionError:
        return ToolResult(False, "写入路径未获授权", {"error": "write_denied"},
                          opclass=OPCLASS_MANAGED_WRITE)
    except (OSError, RuntimeError, UnicodeError):
        return ToolResult(False, "写入失败或目标在操作中变化", {"error": "write_unavailable"},
                          opclass=OPCLASS_MANAGED_WRITE)
    return ToolResult(
        True,
        f"{'覆盖' if existed else '新建'} {target}（{len(content)} 字符）",
        {"path": str(target), "created": not existed, "bytes": len(body)},
        opclass=OPCLASS_MANAGED_WRITE,
    )


def edit_file(ctx: ToolContext, path: str, old: str, new: str) -> ToolResult:
    try:
        target, anchor, relative = _write_target(ctx, path)
        if not _policy_allows_read(ctx, target):
            return ToolResult(False, "策略禁止读取编辑目标", {"error": "read_denied"},
                              opclass=OPCLASS_MANAGED_WRITE)
        if os.name == "posix":
            parent_fd = _open_parent_at(anchor, relative, create=False)
            try:
                prior = _regular_at(parent_fd, relative.name)
                if prior is None:
                    return ToolResult(False, f"文件不存在：{target}", {"error": "not_found"},
                                      opclass=OPCLASS_MANAGED_WRITE)
                file_fd = os.open(
                    relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=parent_fd,
                )
                with os.fdopen(file_fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise PermissionError("编辑目标不是普通文件")
                    text = stream.read().decode("utf-8")
                count = text.count(old)
                if count == 0:
                    return ToolResult(False, "未找到待替换内容（old 必须逐字匹配，含缩进）",
                                      {"error": "no_match"}, opclass=OPCLASS_MANAGED_WRITE)
                if count > 1:
                    return ToolResult(False, f"待替换内容出现 {count} 次，不唯一；请提供更长上下文",
                                      {"error": "not_unique", "count": count},
                                      opclass=OPCLASS_MANAGED_WRITE)
                _atomic_write_at(parent_fd, relative.name,
                                 text.replace(old, new, 1).encode("utf-8"), prior)
            finally:
                os.close(parent_fd)
        else:
            if ctx.policy is not None:
                raise PermissionError("Windows 策略写入尚未验证")
            if not target.is_file():
                return ToolResult(False, f"文件不存在：{target}", {"error": "not_found"},
                                  opclass=OPCLASS_MANAGED_WRITE)
            text = target.read_text(encoding="utf-8")
            count = text.count(old)
            if count == 0:
                return ToolResult(False, "未找到待替换内容（old 必须逐字匹配，含缩进）",
                                  {"error": "no_match"}, opclass=OPCLASS_MANAGED_WRITE)
            if count > 1:
                return ToolResult(False, f"待替换内容出现 {count} 次，不唯一；请提供更长上下文",
                                  {"error": "not_unique", "count": count},
                                  opclass=OPCLASS_MANAGED_WRITE)
            target.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    except FileNotFoundError:
        return ToolResult(False, f"文件不存在：{path}", {"error": "not_found"},
                          opclass=OPCLASS_MANAGED_WRITE)
    except PermissionError:
        return ToolResult(False, "编辑路径未获授权", {"error": "write_denied"},
                          opclass=OPCLASS_MANAGED_WRITE)
    except (OSError, RuntimeError, UnicodeError):
        return ToolResult(False, "编辑失败或目标在操作中变化", {"error": "write_unavailable"},
                          opclass=OPCLASS_MANAGED_WRITE)
    return ToolResult(True, f"已编辑 {target}（替换 {len(old)} -> {len(new)} 字符）",
                      {"path": str(target)}, opclass=OPCLASS_MANAGED_WRITE)


def submit_artifact(ctx: ToolContext, name: str, content: str) -> ToolResult:
    """仅在策略会话中由宿主代写当前步骤声明的产物。"""
    if ctx.artifact_broker is None:
        return ToolResult(False, "当前步骤未开放受控产物端口",
                          {"error": "artifact_unavailable"}, opclass=OPCLASS_MANAGED_WRITE)
    try:
        size = ctx.artifact_broker.submit(name, content)
    except ArtifactAccessError as exc:
        return ToolResult(False, str(exc), {"error": "artifact_denied"},
                          opclass=OPCLASS_MANAGED_WRITE)
    return ToolResult(True, f"已提交步骤产物 {name}（{size} 字节）",
                      {"name": name, "bytes": size}, opclass=OPCLASS_MANAGED_WRITE)


def read_artifact(
    ctx: ToolContext, name: str, offset: int = 1, limit: int = 400,
) -> ToolResult:
    if ctx.artifact_broker is None:
        return ToolResult(False, "当前步骤未开放受控产物端口",
                          {"error": "artifact_unavailable"})
    try:
        body = ctx.artifact_broker.read(name)
    except ArtifactAccessError as exc:
        return ToolResult(False, str(exc), {"error": "artifact_denied"})
    try:
        first = max(1, int(offset))
        count = min(1000, max(1, int(limit)))
    except (TypeError, ValueError):
        return ToolResult(False, "读取范围非法", {"error": "bad_range"})
    lines = body.splitlines()
    end = min(len(lines), first - 1 + count)
    excerpt = "\n".join(f"{index:>5}| {lines[index - 1]}" for index in range(first, end + 1))
    return ToolResult(
        True, f"{name}（共 {len(lines)} 行，显示 {first}-{end}）\n{excerpt}",
        {"name": name, "total_lines": len(lines), "start": first, "end": end},
    )


def workspace_changes(ctx: ToolContext) -> ToolResult:
    """不调用 Git，只报告相对本链路初始快照的文件增删改。"""
    if ctx.change_baseline is None:
        return ToolResult(False, "当前会话没有改动基线", {"error": "changes_unavailable"})
    try:
        current = snapshot_workspace(ctx.root)
    except OSError:
        return ToolResult(False, "工作区快照失败，已停止改动查询",
                          {"error": "snapshot_unavailable"})
    names = changed_files(ctx.change_baseline, current)
    names = [
        name for name in names
        if _policy_allows_read(ctx, ctx.root / Path(name))
    ]
    lines = [
        f"{'A' if name not in ctx.change_baseline else 'D' if name not in current else 'M'} {name}"
        for name in names[:300]
    ]
    if len(names) > 300:
        lines.append(f"…另外 {len(names) - 300} 项未展示")
    return ToolResult(
        True,
        "相对本次任务开始时的文件改动（不是 Git 暂存/提交状态）：\n"
        + ("\n".join(lines) if lines else "无改动"),
        {"changed": len(names), "shown": min(len(names), 300)},
    )


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def run_command(
    ctx: ToolContext,
    argv: list[str] | str,
    timeout: int = 180,
    cwd: str = "",
) -> ToolResult:
    """执行一条命令（**无 shell**）。

    权限判定由 guard 在调用前完成；本函数负责**按当前隔离能力**执行，
    并在 meta 里如实标注用的是哪种隔离（或没有）。
    """
    import subprocess

    if not isinstance(argv, (str, list, tuple)) or (
        not isinstance(argv, str)
        and any(not isinstance(part, str) for part in argv)
    ):
        return ToolResult(False, "命令参数必须是字符串或字符串列表",
                          {"error": "invalid_argv"}, opclass=OPCLASS_MANAGED_WRITE)
    if isinstance(argv, str):
        import shlex

        try:
            args = shlex.split(argv, posix=True)
        except ValueError:
            return ToolResult(False, "命令参数解析失败",
                              {"error": "invalid_argv"}, opclass=OPCLASS_MANAGED_WRITE)
    else:
        args = list(argv)
    if not args:
        return ToolResult(False, "空命令", {"error": "empty_argv"},
                          opclass=OPCLASS_MANAGED_WRITE)
    if not args[0].strip() or any("\x00" in part for part in args):
        return ToolResult(False, "命令参数非法", {"error": "invalid_argv"},
                          opclass=OPCLASS_MANAGED_WRITE)

    workdir = ctx.resolve(cwd) if cwd else ctx.root
    try:
        workdir = workdir.resolve(strict=True)
        workdir.relative_to(ctx.root.resolve(strict=True))
        if not workdir.is_dir():
            raise ValueError("not a directory")
    except (OSError, ValueError):
        return ToolResult(
            False, "执行目录必须位于工作区内且为已有目录",
            {"error": "invalid_cwd"}, opclass=OPCLASS_MANAGED_WRITE,
        )
    if (
        ctx.policy is not None
        and Path(args[0]).name.lower().removesuffix(".exe") == "git"
        and any(
            protected.name == ".git"
            and ctx.root.resolve().is_relative_to(protected.parent / "code")
            for protected in ctx.policy.protected_paths
        )
    ):
        return ToolResult(
            False,
            "分层工作区不能直接运行 Git 命令；请用 workspace_changes 查看本次改动",
            {"error": "git_broker_unavailable"},
            opclass=OPCLASS_READ_ONLY if _looks_read_only(args) else OPCLASS_MANAGED_WRITE,
        )
    use_linux_violation_receipts = (
        ctx.policy is not None
        and sys.platform.startswith("linux")
        and isinstance(ctx.sandbox, LandlockSandbox)
        and ctx.policy.network_mode is NetworkMode.DENY
        and not ctx.policy.allowed_domains
    )
    try:
        exec_argv = (
            args if use_linux_violation_receipts else ctx.wrap_command(args)
        )
    except Exception as exc:  # noqa: BLE001 - 隔离不可用时拒绝执行，不降级
        return ToolResult(
            False,
            f"隔离不可用，已拒绝执行：{exc}",
            {"error": "isolation_unavailable", "sandbox": ctx.isolation_label()},
            opclass=OPCLASS_MANAGED_WRITE,
        )

    if ctx.policy is not None:
        if use_linux_violation_receipts:
            outcome = execute_linux_violation_observed_command(
                args,
                cwd=workdir,
                sandbox=ctx.sandbox,
                policy=ctx.policy,
                timeout=timeout,
                command_wrapper=ctx.wrap_command_with_violation_receipt,
            )
        else:
            outcome = execute_policy_command(
                exec_argv, cwd=workdir, policy=ctx.policy, timeout=timeout,
            )
        # 命令参数可能含密钥：事件与回执只保留摘要，不回显原文。
        argv_sha256 = hashlib.sha256(
            json.dumps(args, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if outcome.error == "isolation_unavailable":
            return ToolResult(
                False,
                "隔离不可用，已拒绝执行：工单隔离策略绑定失败，命令已拒绝",
                {"error": "isolation_unavailable", "sandbox": ctx.isolation_label()},
                opclass=OPCLASS_MANAGED_WRITE,
            )
        result_meta = {
            "argv_sha256": argv_sha256,
            "exit_code": outcome.exit_code,
            "cwd": workdir.relative_to(ctx.root.resolve()).as_posix(),
            "isolation": ctx.isolation_label(),
            "real_isolation": ctx.needs_real_isolation(),
            "policy_hash": ctx.policy.policy_hash,
            "output_bytes": outcome.output_bytes,
            "output_truncated": outcome.output_truncated,
            "cleanup_ok": outcome.cleanup_ok,
            "cleanup_errno": outcome.cleanup_errno,
            # cleanup_ok 只表示 broker 的进程组收束调用成功，不是整树证明。
            "cleanup_scope": (
                "not_started" if outcome.error in ("launch_failed", "unsupported_platform")
                else "process_group"
            ),
        }
        if outcome.violation_observer_status is not None:
            result_meta["violation_observer_status"] = outcome.violation_observer_status
        if outcome.violation_receipt is not None:
            result_meta.update({
                "error": "policy_denied",
                "error_code": "policy_denied",
                "violation_receipt": outcome.violation_receipt,
            })
            return ToolResult(
                False,
                POLICY_DENIED_USER_MESSAGE,
                result_meta,
                opclass=OPCLASS_READ_ONLY if _looks_read_only(args) else OPCLASS_MANAGED_WRITE,
            )
        if outcome.error == "unsupported_platform":
            result_meta["error"] = "unsupported_platform"
            result_meta["error_code"] = "unsupported_platform"
            result_meta["payload_started"] = False
            return ToolResult(
                False,
                "当前平台暂未开放受控命令执行，命令未启动。",
                result_meta,
                opclass=OPCLASS_READ_ONLY if _looks_read_only(args) else OPCLASS_MANAGED_WRITE,
            )
        if outcome.error:
            result_meta["error"] = outcome.error
        output = outcome.output.strip() or "<无输出>"
        return ToolResult(
            outcome.error is None and outcome.exit_code == 0,
            f"$ [受控命令]\nexit={outcome.exit_code}\n{output}",
            result_meta,
            opclass=OPCLASS_READ_ONLY if _looks_read_only(args) else OPCLASS_MANAGED_WRITE,
        )

    proc = subprocess.run(  # noqa: S603 - 参数列表 + shell=False
        exec_argv,
        cwd=str(workdir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(1, int(timeout)),
        shell=False,
    )
    body = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    return ToolResult(
        proc.returncode == 0,
        f"$ {' '.join(args)}\nexit={proc.returncode}\n{body.strip() or '<无输出>'}",
        {
            "argv": args,
            "exit_code": proc.returncode,
            "cwd": str(workdir),
            "isolation": ctx.isolation_label(),
            "real_isolation": ctx.needs_real_isolation(),
        },
        opclass=OPCLASS_READ_ONLY if _looks_read_only(args) else OPCLASS_MANAGED_WRITE,
    )


_READ_ONLY_HEADS = {
    "git", "ls", "dir", "cat", "type", "echo", "pwd", "grep", "rg",
    "find", "which", "where", "diff", "head", "tail", "wc", "sort", "uniq",
}
_GIT_MUTATING = {"add", "commit", "push", "pull", "merge", "reset", "checkout", "clean", "rebase"}


def _looks_read_only(args: list[str]) -> bool:
    head = Path(args[0]).name.lower().removesuffix(".exe")
    if head not in _READ_ONLY_HEADS:
        return False
    if head == "git" and len(args) > 1 and args[1].lower() in _GIT_MUTATING:
        return False
    return True


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------


def _git_status_available(ctx: ToolContext) -> bool:
    session = ctx.workspace_session
    policy = ctx.policy
    if not isinstance(session, WorkspaceSession) or not isinstance(policy, SandboxPolicy):
        return False
    identity = session.git_status_identity
    if not isinstance(identity, GitWorkspaceIdentity):
        return False
    try:
        session_policy = session.policy(policy.step)
    except Exception:  # noqa: BLE001 - stale or malformed session disables the tool.
        return False
    return (
        sys.platform.startswith("linux")
        and isinstance(ctx.sandbox, LandlockSandbox)
        and not ctx.read_only_workspace
        and policy.step != "review"
        and session.kind == "git_worktree"
        and session.ticket_id == policy.ticket_id
        and session.run_id == policy.run_id
        and policy == session_policy
        and session.workspace_root == ctx.root
        and ctx.root == identity.workspace_root == identity.code_root == policy.workspace_root
        and identity.source_relative_path == Path(".")
        and policy.network_mode is NetworkMode.DENY
        and not policy.allowed_domains
        and policy.read_roots == (ctx.root,)
        and policy.write_roots == (ctx.root,)
        and {identity.checkout_root / ".git", identity.common_dir}.issubset(
            set(policy.deny_write_roots)
        )
    )


def git_status(ctx: ToolContext) -> ToolResult:
    """Return one complete, path-safe status from the manager-issued worktree."""
    if (
        not _git_status_available(ctx)
        or not isinstance(ctx.workspace_session, WorkspaceSession)
        or not isinstance(ctx.workspace_session.git_status_identity, GitWorkspaceIdentity)
        or ctx.policy is None
    ):
        return ToolResult(False, "Git 状态不可用", {"error": "git_broker_unavailable"})
    try:
        entries = execute_git_status(
            ctx.workspace_session.git_status_identity,
            sandbox=ctx.sandbox, policy=ctx.policy,
        )
        for item in entries:
            for path in (item.path, item.original_path):
                if path is None:
                    continue
                if (not isinstance(path, bytes) or not path or path.startswith(b"/")
                        or b"\0" in path or b".." in path.split(b"/")):
                    raise ValueError("invalid relative status path")
        payload = {
            "clean": not entries,
            "entries": [
                {
                    "kind": item.kind,
                    "path": os.fsdecode(item.path),
                    "index_status": item.index_status,
                    "worktree_status": item.worktree_status,
                    **({"original_path": os.fsdecode(item.original_path)}
                       if item.original_path is not None else {}),
                }
                for item in entries
            ],
        }
        content = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        if len(content) > ctx.output_limit:
            return ToolResult(False, "Git 状态超出输出限额", {"error": "git_broker_unavailable"})
        return ToolResult(True, content, {"entry_count": len(entries)})
    except (GitStatusUnavailable, UnicodeError, ValueError, TypeError):
        return ToolResult(False, "Git 状态不可用", {"error": "git_broker_unavailable"})


def default_registry(*, include_artifacts: bool = False,
                     include_changes: bool = False,
                     git_status_context: ToolContext | None = None) -> ToolRegistry:
    """Phase 2 最小工具集。

    **不含任意 shell 执行**：`run_command` 需经 guard 白名单放行，
    而 `bash` 类无限制执行在 Phase 5（沙箱）之前不开放。
    """
    reg = ToolRegistry()
    reg.register(Tool(
        name="read_file",
        description="读取工程内文件内容，带行号。大文件用 offset/limit 分段读。",
        parameters=_params({
            "path": {"type": "string", "description": "文件路径（相对工程根或绝对）"},
            "offset": {"type": "integer", "description": "起始行，默认 1"},
            "limit": {"type": "integer", "description": "读取行数，默认 400"},
        }, ["path"]),
        handler=read_file,
    ))
    reg.register(Tool(
        name="glob",
        description="按 glob 模式列出工程内文件，如 '**/*.py'。",
        parameters=_params({
            "pattern": {"type": "string", "description": "glob 模式"},
        }, ["pattern"]),
        handler=glob_files,
    ))
    reg.register(Tool(
        name="grep",
        description="按正则搜索文件内容，返回 file:line: 内容。",
        parameters=_params({
            "pattern": {"type": "string", "description": "正则表达式"},
            "path": {"type": "string", "description": "搜索起点，默认工程根"},
            "max_hits": {"type": "integer", "description": "最大命中数，默认 120"},
        }, ["pattern"]),
        handler=grep_files,
    ))
    reg.register(Tool(
        name="write_file",
        description="新建或覆盖文件（UTF-8，LF）。新建类改动优先用 edit_file。",
        parameters=_params({
            "path": {"type": "string"},
            "content": {"type": "string"},
        }, ["path", "content"]),
        handler=write_file,
        opclass=OPCLASS_MANAGED_WRITE,
    ))
    reg.register(Tool(
        name="edit_file",
        description="精确替换文件中的一段内容（old 必须唯一匹配）。",
        parameters=_params({
            "path": {"type": "string"},
            "old": {"type": "string", "description": "被替换的原文（逐字匹配）"},
            "new": {"type": "string", "description": "替换后的内容"},
        }, ["path", "old", "new"]),
        handler=edit_file,
        opclass=OPCLASS_MANAGED_WRITE,
    ))
    reg.register(Tool(
        name="run_command",
        description=(
            "执行一条命令。**不经过 shell**：argv 必须是参数列表，"
            "如 [\"ls\",\"-la\"]、[\"python\",\"-m\",\"unittest\"]。"
            "禁止使用 && || | ; > 等 shell 语法（会被直接拒绝）；"
            "需要串联多条命令时请分多次调用。"
            "仅白名单命令放行，危险命令（递归删除/强制推送/管道执行远端脚本等）会被拒绝。"
        ),
        parameters=_params({
            "argv": {
                "type": "array", "items": {"type": "string"},
                "description": "命令与参数数组，如 ['python','-m','unittest']",
            },
            "timeout": {"type": "integer", "description": "超时秒数，默认 180"},
            "cwd": {"type": "string", "description": "工作目录，默认工程根"},
        }, ["argv"]),
        handler=run_command,
        opclass=OPCLASS_MANAGED_WRITE,
    ))
    if include_changes:
        reg.register(Tool(
            name="workspace_changes",
            description="列出相对本次任务开始时的文件增删改；不是 Git 暂存或提交状态。",
            parameters=_params({}, []),
            handler=workspace_changes,
        ))
    if git_status_context is not None and _git_status_available(git_status_context):
        reg.register(Tool(
            name="git_status",
            description="查询当前工单工作区的 Git 暂存、工作区、未跟踪和冲突状态。",
            parameters={**_params({}, []), "additionalProperties": False},
            handler=git_status,
        ))
    if include_artifacts:
        reg.register(Tool(
            name="submit_artifact",
            description="按当前步骤合同提交工单产物正文；只传文件名，不传路径。",
            parameters=_params({
                "name": {"type": "string", "description": "当前步骤产物文件名"},
                "content": {"type": "string", "description": "UTF-8 产物正文"},
            }, ["name", "content"]),
            handler=submit_artifact,
            opclass=OPCLASS_MANAGED_WRITE,
        ))
        reg.register(Tool(
            name="read_artifact",
            description="读取当前步骤合同声明的旧工单输入；只传文件名。",
            parameters=_params({
                "name": {"type": "string", "description": "当前步骤输入文件名"},
                "offset": {"type": "integer", "description": "起始行，默认 1"},
                "limit": {"type": "integer", "description": "读取行数，默认 400，最多 1000"},
            }, ["name"]),
            handler=read_artifact,
        ))
    return reg
