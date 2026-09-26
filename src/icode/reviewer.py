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

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .guard import Decision, Guard, Scope

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_BLOCKING = "blocking"

SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_BLOCKING)
MODEL_REVIEW_CATEGORIES = frozenset({
    "code", "compatibility", "contract", "correctness", "environment",
    "model_capability", "performance", "reliability", "security",
    "side_effect_unknown", "test", "other",
})


class ReviewError(RuntimeError):
    """审查上下文非法或无法安全产出结论。"""


@dataclass(frozen=True)
class ReviewFinding:
    severity: str
    category: str
    file: str
    message: str
    evidence_ref: str = ""
    line: int | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "line": self.line,
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
    model_reviewed: bool = False
    summary: str = ""

    def render(self) -> str:
        lines = ["独立 Reviewer", f"  只读上下文：{'通过' if self.read_only_verified else '未通过'}",
                 f"  审查文件：{'、'.join(self.reviewed_files) or '无'}",
                 f"  发现：{len(self.findings)} 条"]
        if self.model_reviewed and self.summary:
            lines.append(f"  模型审查摘要：{self.summary}")
        for finding in self.findings:
            location = f"{finding.file}:{finding.line}" if finding.line else finding.file
            lines.append(
                f"  [{finding.severity}/{finding.category}] {location}: "
                f"{finding.message}" + (f"（证据 {finding.evidence_ref[:8]}…）"
                                        if finding.evidence_ref else "")
            )
        if self.error:
            lines.append(f"  错误：{self.error}")
        lines.append("结果：" + ("通过" if self.ok else "未通过"))
        return "\n".join(lines)


def reviewer_guard(
    workspace: Path, *, allowed_read_files: tuple[Path, ...] | None = None,
) -> Guard:
    """构造只读审查上下文：工作区内可读，但**没有任何写授权**。

    `allowed_write_roots=()` 意味着 `check_write` 对任何路径都返回 DENY；
    可选的 `allowed_read_files` 使用精确路径相等，不把单个文件扩大成目录前缀。
    未指定时保留通用 Reviewer 的工作区只读范围。
    """
    root = Path(workspace).resolve()
    scope = Scope(
        workspace_root=root,
        allowed_read_roots=(root,) if allowed_read_files is None else (),
        allowed_read_files=(None if allowed_read_files is None else tuple(
            path if path.is_absolute() else root / path for path in allowed_read_files
        )),
        allowed_write_roots=(),
        deny_read_roots=(root / ".icode_output",),
        deny_write_roots=(root,),
    )
    return Guard(scope)


def is_review_read_only(
    guard: Guard, workspace: Path, *, readable_path: Path | None = None,
) -> bool:
    """用真实 Guard 判定锁死：任何写路径都必须被拒绝。

    被审对象（工作区内的文件）的 write_file / edit_file 都不得放行；
    读路径（read_file / grep）应放行。
    """
    root = Path(workspace).resolve()
    if guard.check_write(str(root / "probe.md")).decision is not Decision.DENY:
        return False
    read_target = readable_path or root / "readme.md"
    if not read_target.is_absolute():
        read_target = root / read_target
    read = guard.check_read(str(read_target))
    if read.decision not in (Decision.ALLOW, Decision.REQUIRE_APPROVAL):
        return False
    return True


def verify_read_only(
    guard: Guard, workspace: Path, *, readable_path: Path | None = None,
) -> bool:
    """审查前自检：工作区内写必须全部被拒；读必须放行。

    与 `is_review_read_only` 语义一致，显式区分「自检」用途，便于测试断言。
    """
    return is_review_read_only(guard, workspace, readable_path=readable_path)


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
        *,
        read_probe: Path | None = None,
    ) -> ReviewReport:
        """针对改动文件与验证证据产出结构化发现。

        只读自检失败时拒绝产出结论（fail-safe）。发现必须引用
        验证证据指纹（`evidence_ref`），没有证据引用不算自验证结论。
        """
        if not verify_read_only(
            self.guard, self.workspace, readable_path=read_probe,
        ):
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


def merge_model_review(
    base_report: ReviewReport,
    response: str,
    *,
    changed_files: list[str],
    evidence: Any,
) -> ReviewReport:
    """Validate an independent model review and bind every finding to current evidence.

    The response is deliberately a small, strict JSON contract. Invalid or
    unbound output is a failed review, never an implicit approval.
    """
    def failed(reason: str) -> ReviewReport:
        return ReviewReport(
            ok=False,
            findings=list(base_report.findings),
            reviewed_files=list(changed_files),
            read_only_verified=base_report.read_only_verified,
            error=reason,
            model_reviewed=False,
        )

    if not base_report.read_only_verified:
        return failed("只读上下文未通过自检")
    if evidence is None:
        return failed("缺少可绑定的独立验证证据")
    if not isinstance(response, str):
        return failed("模型审查响应类型非法")
    try:
        response_size = len(response.encode("utf-8"))
    except UnicodeError:
        return failed("模型审查响应包含非法 Unicode")
    if response_size > 32 * 1024:
        return failed("模型审查响应超过 32 KiB 上限")

    body = response.strip()
    if body.startswith("```json") and body.endswith("```"):
        body = body[len("```json"): -len("```")].strip()
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return failed("模型审查响应不是有效 JSON")
    if not isinstance(payload, dict) or set(payload) != {"summary", "findings"}:
        return failed("模型审查响应字段不符合合同")

    summary = payload.get("summary")
    raw_findings = payload.get("findings")
    if (not isinstance(summary, str) or not summary.strip() or len(summary) > 2000
            or not isinstance(raw_findings, list) or len(raw_findings) > 100):
        return failed("模型审查摘要或发现列表不符合合同")

    try:
        from .self_verify import evidence_fingerprint

        evidence_ref = evidence_fingerprint(evidence)
    except Exception:  # noqa: BLE001 - malformed evidence cannot authorize a review
        return failed("验证证据指纹不可用")
    changed = set(changed_files)
    model_findings: list[ReviewFinding] = []
    required_fields = {"severity", "category", "file", "line", "message"}
    for item in raw_findings:
        if not isinstance(item, dict) or set(item) != required_fields:
            return failed("模型审查发现字段不符合合同")
        severity = item.get("severity")
        category = item.get("category")
        file_name = item.get("file")
        line = item.get("line")
        message = item.get("message")
        if not isinstance(severity, str) or severity not in SEVERITIES:
            return failed("模型审查发现包含未知严重级别")
        if not isinstance(category, str) or category not in MODEL_REVIEW_CATEGORIES:
            return failed("模型审查发现包含未知类别")
        if (not isinstance(file_name, str) or not file_name or "\\" in file_name
                or PurePosixPath(file_name).is_absolute()
                or PurePosixPath(file_name).as_posix() != file_name
                or ".." in PurePosixPath(file_name).parts
                or file_name not in changed):
            return failed("模型审查发现未绑定到本次变更文件")
        if line is not None and (type(line) is not int or line < 1):
            return failed("模型审查发现行号非法")
        if not isinstance(message, str) or not message.strip() or len(message) > 2000:
            return failed("模型审查发现说明为空或过长")
        model_findings.append(ReviewFinding(
            severity=severity,
            category=category,
            file=file_name,
            message=message.strip(),
            evidence_ref=evidence_ref,
            line=line,
        ))

    findings = [*base_report.findings, *model_findings]
    return ReviewReport(
        ok=base_report.ok and not any(
            finding.severity == SEVERITY_BLOCKING for finding in model_findings
        ),
        findings=findings,
        reviewed_files=list(changed_files),
        read_only_verified=True,
        model_reviewed=True,
        summary=summary.strip(),
    )
