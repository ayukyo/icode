"""仓库结构/符号/变更索引与 token 预算感知的有界选取（R4/G3）。

设计约束：
- **只出大纲不出正文**：索引保存路径、指纹、大小与符号行，选取结果只渲染
  路径/指纹/符号，从不注入源码正文——大仓库任务不需要全量源码。
- 纯函数：索引与选取不写工作区、不发网络请求；变更集由调用方提供
  （git 边界留给调用方，便于离线测试与复用）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "node_modules", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode", "build", "dist", ".egg-info",
})
_SYMBOL_RE = re.compile(r"^(?P<indent>\s*)(?P<kind>class|def|async def)\s+(?P<name>[A-Za-z_]\w*)")
MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class SymbolEntry:
    path: str
    kind: str
    name: str
    line: int


@dataclass
class RepoIndex:
    root: Path
    files: list[FileEntry] = field(default_factory=list)
    symbols: list[SymbolEntry] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass(frozen=True)
class ContextSelection:
    """有界上下文：只含大纲文本与计数，不含任何源码正文。"""

    text: str
    files: tuple[str, ...]
    symbols: tuple[str, ...]
    dropped_files: int

    @property
    def chars(self) -> int:
        return len(self.text)


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
    except OSError:
        return "unreadable"
    return hasher.hexdigest()


def _outline(path: Path, relative: str, limit: int = 64) -> list[SymbolEntry]:
    """Python 文件的一级符号大纲（缩进为 0 的 class/def）。"""
    if path.suffix != ".py":
        return []
    symbols: list[SymbolEntry] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, start=1):
                match = _SYMBOL_RE.match(line)
                if match is None or match.group("indent"):
                    continue
                symbols.append(SymbolEntry(
                    path=relative,
                    kind="class" if match.group("kind") == "class" else "function",
                    name=match.group("name"),
                    line=number,
                ))
                if len(symbols) >= limit:
                    break
    except OSError:
        return []
    return symbols


def build_index(
    root: str | Path,
    *,
    changed: list[str] | tuple[str, ...] = (),
    max_files: int = 4000,
) -> RepoIndex:
    """构建结构/符号/变更索引；超过上限时截断并标记。"""
    base = Path(root).resolve()
    index = RepoIndex(root=base)
    for path in sorted(base.rglob("*")):
        try:
            relative_parts = path.relative_to(base).parts
        except ValueError:
            continue
        if any(part in _SKIP_DIRS for part in relative_parts):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            continue
        relative = "/".join(relative_parts)
        if len(index.files) >= max_files:
            index.truncated = True
            break
        index.files.append(FileEntry(path=relative, size=size, sha256=_digest(path)))
        index.symbols.extend(_outline(path, relative))
    index.changed = [item for item in changed if isinstance(item, str)][:max_files]
    return index


def _score(entry: FileEntry, terms: list[str], changed: set[str]) -> int:
    lowered = entry.path.lower()
    score = 0
    for term in terms:
        if term in lowered:
            score += 3
    if entry.path in changed:
        score += 5
    return score


def select_context(
    index: RepoIndex,
    *,
    query: str,
    budget_chars: int = 4000,
    limit_files: int = 12,
) -> ContextSelection:
    """按关键词与变更集选文件，渲染**只有大纲**的有界上下文。"""
    if not isinstance(budget_chars, int) or budget_chars <= 0:
        raise ValueError("budget_chars 必须为正整数")
    if not isinstance(limit_files, int) or limit_files <= 0:
        raise ValueError("limit_files 必须为正整数")
    terms = [term for term in re.split(r"[^0-9A-Za-z_\u4e00-\u9fff]+", query.lower()) if term]
    changed = set(index.changed)
    ranked = sorted(
        index.files,
        key=lambda entry: (-_score(entry, terms, changed), entry.path),
    )
    selected: list[FileEntry] = []
    lines: list[str] = []
    used = 0
    for entry in ranked:
        if len(selected) >= limit_files:
            break
        symbols = [s for s in index.symbols if s.path == entry.path]
        row = f"- {entry.path} ({entry.size}B sha256:{entry.sha256[:12]})"
        if entry.path in changed:
            row += " [changed]"
        for symbol in symbols[:8]:
            row += f"\n    {symbol.kind} {symbol.name} L{symbol.line}"
        if used + len(row) + 1 > budget_chars:
            continue
        selected.append(entry)
        lines.append(row)
        used += len(row) + 1
        if used >= budget_chars * 0.95:
            break
    text = "\n".join(lines)
    return ContextSelection(
        text=text,
        files=tuple(entry.path for entry in selected),
        symbols=tuple(symbol.name for symbol in index.symbols
                      if symbol.path in {entry.path for entry in selected}),
        dropped_files=max(0, len(index.files) - len(selected)),
    )
