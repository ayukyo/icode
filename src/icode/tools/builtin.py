"""内置工具集（最小集）。

- 读：`read_file` / `glob` / `grep`（grep 用纯 Python 实现，**不依赖 ripgrep**，跨平台一致）
- 写：`write_file` / `edit_file`（edit 要求 old 精确唯一匹配，避免误改）
- 执行：`run_command`（**无 shell**，参数列表；危险命令由 guard 拦截）

明确不含：任意 shell 拼接、网络访问、包安装。
"""

from __future__ import annotations

import re
from pathlib import Path

from ..artifact_broker import ArtifactAccessError
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
    hits: list[str] = []
    for p in sorted(ctx.root.glob(pattern)):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        rel = p.relative_to(ctx.root).as_posix() if p.is_relative_to(ctx.root) else p.as_posix()
        hits.append(rel)
        if len(hits) >= MAX_GLOB_HITS:
            break
    if not hits:
        return ToolResult(True, f"无匹配：{pattern}", {"hits": 0})
    return ToolResult(True, "\n".join(hits), {"hits": len(hits)})


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


def read_artifact(ctx: ToolContext, name: str) -> ToolResult:
    if ctx.artifact_broker is None:
        return ToolResult(False, "当前步骤未开放受控产物端口",
                          {"error": "artifact_unavailable"})
    try:
        body = ctx.artifact_broker.read(name)
    except ArtifactAccessError as exc:
        return ToolResult(False, str(exc), {"error": "artifact_denied"})
    return ToolResult(True, body, {"name": name, "bytes": len(body.encode("utf-8"))})


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
    try:
        exec_argv = ctx.wrap_command(args)
    except Exception as exc:  # noqa: BLE001 - 隔离不可用时拒绝执行，不降级
        return ToolResult(
            False,
            f"隔离不可用，已拒绝执行：{exc}",
            {"error": "isolation_unavailable", "sandbox": ctx.isolation_label()},
            opclass=OPCLASS_MANAGED_WRITE,
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


def default_registry(*, include_artifacts: bool = False) -> ToolRegistry:
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
            }, ["name"]),
            handler=read_artifact,
        ))
    return reg
