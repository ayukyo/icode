"""R3 独立 Reviewer：与 Executor 隔离上下文，且不能修改被审对象。

产品架构 §13.7 要求：

    Reviewer 与 Executor 使用隔离上下文，且 Reviewer 不能修改被审对象。

本模块实现一个可独立测试的最小切片：

1. **只读审查上下文**（`reviewer_guard` / `is_review_read_only`）
   构造一个 Guard，`allowed_write_roots=()` 表示「没有任何可写授权」；
   对工作区内的读放行、对任何写（write_file / edit_file）一律拒绝。
   用真实 Guard 判定锁死，不靠约定。

2. **结构化发现**（`ReviewFinding` / `IndependentReviewer.review`）
   针对 Executor 的改动文件与验证证据，产出带严重级别、失败分类、
   文件、消息与证据引用的发现；发现必须引用具体验证证据指纹
   （没有证据引用就不是「自验证」结论）。

3. **只读自检**（`verify_read_only`）
   显式断言审查上下文不能修改被审对象；验证失败即拒绝产出审查结论，
   避免 Reviewer 意外获得写能力后污染被审对象。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .guard import Decision, Guard, Scope

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_BLOCKING = "blocking"

SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_BLOCKING)


class ReviewError(RuntimeError):
    """审查上下文非法或无法安全产出结论。"""


@dataclass(frozen=True)
class ReviewFinding:
    severity: str
    category: str
    file: str
    message: str
    evidence_ref: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "message": self.message,
            "evidence_ref": self.evidence_ref,
        }


@dataclass
class ReviewReport:
    ok: bool
    findings: list[ReviewFinding] = field(default_factory=list)
    reviewed_files: list[str] = field(default_factory=list)
    read_only_verified: bool = False
    error: str = ""

    def render(self) -> str:
        lines = ["独立 Reviewer", f"  只读上下文：{'通过' if self.read_only_verified else '未通过'}",
                 f"  审查文件：{'、'.join(self.reviewed_files) or '无'}",
                 f"  发现：{len(self.findings)} 条"]
        for finding in self.findings:
            lines.append(
                f"  [{finding.severity}/{finding.category}] {finding.file}: "
                f"{finding.message}" + (f"（证据 {finding.evidence_ref[:8]}…）"
                                        if finding.evidence_ref else "")
            )
        if self.error:
            lines.append(f"  错误：{self.error}")
        lines.append("结果：" + ("通过" if self.ok else "未通过"))
        return "\n".join(lines)


def reviewer_guard(workspace: Path) -> Guard:
    """构造只读审查上下文：工作区内可读，但**没有任何写授权**。

    `allowed_write_roots=()` 意味着 `check_write` 对任何路径都返回 DENY
    （策略未授权写入），`deny_write_roots` 兜底工作区外。读路径仍放行。
    """
    root = Path(workspace).resolve()
    scope = Scope(
        workspace_root=root,
        allowed_read_roots=(root,),
        allowed_write_roots=(),
        deny_write_roots=(root,),
    )
    return Guard(scope)


def is_review_read_only(guard: Guard, workspace: Path) -> bool:
    """用真实 Guard 判定锁死：任何写路径都必须被拒绝。

    被审对象（工作区内的文件）的 write_file / edit_file 都不得放行；
    读路径（read_file / grep）应放行。
    """
    root = Path(workspace).resolve()
    if guard.check_write(str(root / "probe.md")).decision is not Decision.DENY:
        return False
    read = guard.check_read(str(root / "readme.md"))
    if read.decision not in (Decision.ALLOW, Decision.REQUIRE_APPROVAL):
        return False
    return True


def verify_read_only(guard: Guard, workspace: Path) -> bool:
    """审查前自检：工作区内写必须全部被拒；读必须放行。

    与 `is_review_read_only` 语义一致，显式区分「自检」用途，便于测试断言。
    """
    return is_review_read_only(guard, workspace)


class IndependentReviewer:
    """基于验证证据的只读 Reviewer。

    不直接读取文件内容做语义判断——那是模型的能力；这里聚焦
    「证据引用的结构化审查」：把 Executor 的验证证据翻译成
    Reviewer 可复核的发现，并保证上下文只读。
    """

    def __init__(self, *, workspace: Path, guard: Guard | None = None) -> None:
        self.workspace = Path(workspace).resolve()
        self.guard = guard or reviewer_guard(self.workspace)

    def review(
        self,
        changed_files: list[str],
        evidence: Any | None = None,
    ) -> ReviewReport:
        """针对改动文件与验证证据产出结构化发现。

        只读自检失败时拒绝产出结论（fail-safe）。发现必须引用
        验证证据指纹（`evidence_ref`），没有证据引用不算自验证结论。
        """
        if not verify_read_only(self.guard, self.workspace):
            return ReviewReport(
                ok=False, reviewed_files=list(changed_files),
                read_only_verified=False,
                error="只读审查上下文自检未通过，拒绝产出结论",
            )

        evidence_ref = ""
        category = ""
        exit_code = None
        if evidence is not None:
            from .self_verify import evidence_fingerprint

            evidence_ref = evidence_fingerprint(evidence)
            category = getattr(evidence, "category", "") or ""
            exit_code = getattr(evidence, "exit_code", None)

        findings: list[ReviewFinding] = []
        if exit_code is not None and exit_code != 0:
            findings.append(ReviewFinding(
                severity=SEVERITY_BLOCKING,
                category=category or "side_effect_unknown",
                file=",".join(changed_files) or "<task>",
                message="独立验证未通过，修复必须引用本条失败证据的新变化",
                evidence_ref=evidence_ref,
            ))
        elif exit_code == 0 and changed_files:
            findings.append(ReviewFinding(
                severity=SEVERITY_INFO,
                category=category or "code",
                file=",".join(changed_files),
                message="独立验证通过，改动与证据一致",
                evidence_ref=evidence_ref,
            ))
        for rel in changed_files:
            if (self.workspace / rel).is_symlink():
                findings.append(ReviewFinding(
                    severity=SEVERITY_BLOCKING,
                    category="side_effect_unknown",
                    file=rel,
                    message="被审对象是符号链接，拒绝在只读上下文中展开",
                    evidence_ref=evidence_ref,
                ))

        return ReviewReport(
            ok=not any(f.severity == SEVERITY_BLOCKING for f in findings),
            findings=findings,
            reviewed_files=list(changed_files),
            read_only_verified=True,
        )
