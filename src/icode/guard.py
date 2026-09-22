"""应用层权限模型（**不是沙箱**）。

重要声明（roadmap §3 Phase 1 / C2）：
    这是**应用层限制**，不是内核级隔离。模型若绕过本模块直接执行 shell，
    这些规则不构成保障。真正的隔离在 Phase 5 落地前，对外**不得宣称"安全沙箱"**。

设计目标：把"默认拒绝"变成可测试的判定函数，而不是散落在各处的 if。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePath


class Decision(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


# 明显危险的命令片段：命中即拒（不依赖 shell 解析，做保守子串匹配）
_DANGEROUS_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r", "递归强制删除"),
    (r"\brm\s+-rf\b", "递归强制删除"),
    (r"\bmkfs\b|\bformat\b|\bfdisk\b", "磁盘格式化"),
    (r"\bdd\s+if=", "裸设备写入"),
    (r":\(\)\s*\{.*\}\s*;", "fork 炸弹"),
    (r"\bshutdown\b|\breboot\b|\bhalt\b", "电源操作"),
    (r"\bgit\s+push\b.*--force|\bgit\s+push\b.*-f\b", "强制推送"),
    (r"\bgit\s+reset\s+--hard\b", "丢弃本地改动"),
    (r"\bchmod\s+-R\s+777\b", "危险权限变更"),
    (r"\b(curl|wget)\b[^|]*\|\s*(sh|bash|zsh)\b", "管道执行远端脚本"),
    (r"\breg\s+delete\b|\bregedit\b", "注册表删除"),
    (r"\bRemove-Item\b.*-Recurse", "递归删除"),
    (r"\bdel\s+/[sq]\b", "递归删除"),
)

# 默认允许的命令首词（Phase 2 的白名单起点：只读或与验收直接相关）
_DEFAULT_COMMAND_ALLOWLIST: tuple[str, ...] = (
    "python", "python3", "py",
    "git", "ls", "dir", "cat", "type", "echo", "pwd", "cd",
    "grep", "rg", "find", "which", "where",
    "make", "gcc", "cc", "clang",
    "diff", "head", "tail", "wc", "sort", "uniq",
)


@dataclass(frozen=True)
class Scope:
    """可信执行根。

    workspace_root: 允许写入的工程根（唯一可写区域）
    readable_roots: 额外允许读取的目录（默认只读）
    """

    workspace_root: Path
    readable_roots: tuple[Path, ...] = ()
    command_allowlist: tuple[str, ...] = _DEFAULT_COMMAND_ALLOWLIST

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_root", Path(self.workspace_root).resolve())
        object.__setattr__(
            self, "readable_roots", tuple(Path(p).resolve() for p in self.readable_roots)
        )


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass
class Guard:
    """应用层判定器。所有工具调用前必须过这里。"""

    scope: Scope
    approvals: list[str] = field(default_factory=list)

    # ---- 读 ----

    def check_read(self, path: PurePath | str) -> Verdict:
        target = self._resolve(path)
        if _is_within(target, self.scope.workspace_root):
            return Verdict(Decision.ALLOW, "工作区内读取")
        for root in self.scope.readable_roots:
            if _is_within(target, root):
                return Verdict(Decision.ALLOW, f"只读根内读取：{root}")
        return Verdict(Decision.REQUIRE_APPROVAL, "工作区外读取，需人工确认")

    # ---- 写 ----

    def check_write(self, path: PurePath | str) -> Verdict:
        target = self._resolve(path)
        if _is_within(target, self.scope.workspace_root):
            return Verdict(Decision.ALLOW, "工作区内写入")
        return Verdict(Decision.DENY, "工作区外写入：默认拒绝")

    # ---- 命令 ----

    def check_command(self, argv: list[str] | tuple[str, ...] | str) -> Verdict:
        text = argv if isinstance(argv, str) else " ".join(argv)
        stripped = text.strip()
        if not stripped:
            return Verdict(Decision.DENY, "空命令")

        for pattern, label in _DANGEROUS_PATTERNS:
            if re.search(pattern, stripped, flags=re.IGNORECASE):
                return Verdict(Decision.DENY, f"命中危险模式：{label}")

        head = (argv.split()[0] if isinstance(argv, str) else argv[0]).strip()
        head = Path(head).name  # 归一化路径形式
        head = head[:-4] if head.lower().endswith(".exe") else head
        if head in self.scope.command_allowlist:
            return Verdict(Decision.ALLOW, f"命令白名单：{head}")
        return Verdict(Decision.REQUIRE_APPROVAL, f"不在白名单：{head}")

    # ---- 内部 ----

    def _resolve(self, path: PurePath | str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.scope.workspace_root / p
        # 不要求路径已存在，因此用 os.path.normpath 语义化处理 .. 与符号链接文本形态
        return Path(_normalize(p))

    def summary(self) -> dict[str, object]:
        return {
            "workspace_root": str(self.scope.workspace_root),
            "readable_roots": [str(p) for p in self.scope.readable_roots],
            "allowlist": list(self.scope.command_allowlist),
            "is_sandbox": False,
            "note": "应用层限制，非内核级沙箱；不得对外宣称安全沙箱",
        }


def _normalize(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:  # pragma: no cover - 平台差异兜底
        return path
