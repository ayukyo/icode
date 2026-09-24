"""内置工具集（最小集）。

- 读：`read_file` / `glob` / `grep`（grep 用纯 Python 实现，**不依赖 ripgrep**，跨平台一致）
- 写：`write_file` / `edit_file`（edit 要求 old 精确唯一匹配，避免误改）
- 执行：`run_command`（**无 shell**，参数列表；危险命令由 guard 拦截）

明确不含：任意 shell 拼接、网络访问、包安装。
"""

from __future__ import annotations

import hashlib
import json
import fnmatch
import heapq
import os
import re
import stat
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from ..artifact_broker import ArtifactAccessError
from ..execution_broker import execute_policy_command
from ..workspace_snapshot import changed_files, snapshot_workspace
from .base import (
    OPCLASS_MANAGED_WRITE,
    OPCLASS_READ_ONLY,
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
    target = ctx.resolve(path)
    if not target.is_file():
        return ToolResult(False, f"文件不存在：{target}", {"error": "not_found"})
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
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
        if ctx.policy is None:
            return True
        return (
            any(target.is_relative_to(read_root) for read_root in ctx.policy.read_roots)
            and not any(target.is_relative_to(denied) for denied in ctx.policy.deny_read_roots)
        )

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

    base = ctx.resolve(path)
    if base.is_file():
        targets = [base]
    else:
        targets = [p for p in sorted(base.rglob("*")) if p.is_file()
                   and not any(part in SKIP_DIRS for part in p.parts)]

    hits: list[str] = []
    for f in targets:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
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


def write_file(ctx: ToolContext, path: str, content: str) -> ToolResult:
    target = ctx.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.is_file()
    # 用 write_bytes 避免 Windows 下 os.linesep 把 LF 写成 CRLF（跨平台一致性）
    target.write_bytes(content.encode("utf-8"))
    return ToolResult(
        True,
        f"{'覆盖' if existed else '新建'} {target}（{len(content)} 字符）",
        {"path": str(target), "created": not existed, "bytes": len(content.encode('utf-8'))},
        opclass=OPCLASS_MANAGED_WRITE,
    )


def edit_file(ctx: ToolContext, path: str, old: str, new: str) -> ToolResult:
    target = ctx.resolve(path)
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

    if isinstance(argv, str):
        import shlex

        args = shlex.split(argv, posix=True)
    else:
        args = list(argv)
    if not args:
        return ToolResult(False, "空命令", {"error": "empty_argv"},
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
    try:
        exec_argv = ctx.wrap_command(args)
    except Exception as exc:  # noqa: BLE001 - 隔离不可用时拒绝执行，不降级
        return ToolResult(
            False,
            f"隔离不可用，已拒绝执行：{exc}",
            {"error": "isolation_unavailable", "sandbox": ctx.isolation_label()},
            opclass=OPCLASS_MANAGED_WRITE,
        )

    if ctx.policy is not None:
        outcome = execute_policy_command(
            exec_argv, cwd=workdir, policy=ctx.policy, timeout=timeout,
        )
        # 命令参数可能含密钥：事件与回执只保留摘要，不回显原文。
        argv_sha256 = hashlib.sha256(
            json.dumps(args, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        output = outcome.output.strip() or "<无输出>"
        return ToolResult(
            outcome.error is None and outcome.exit_code == 0,
            f"$ [受控命令]\nexit={outcome.exit_code}\n{output}",
            {
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
                **({"error": outcome.error} if outcome.error else {}),
            },
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


def default_registry(*, include_artifacts: bool = False,
                     include_changes: bool = False) -> ToolRegistry:
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
