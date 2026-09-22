"""渐进披露：把步骤文档拆成「强制注入」与「按需加载」两层。

为什么必须分两层（roadmap §3 Phase 1）：
- 上游步骤文档极大（01_plan.md 约 67KB、log.md 约 146KB），全量注入会直接烧穿预算；
- 但门禁规则若被懒加载掉，Agent 就会漏读约束 —— 所以**门禁不可懒**，只有背景知识可以懒。

本模块只读 `steps/*.md`，不修改上游。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .contracts import StepContract

# 强制注入的字符预算：门禁简报允许的上限（超出即截断并在报告中标明）
DEFAULT_MANDATORY_BUDGET = 4000

# 判定"门禁类"章节的关键词（命中即进入强制层）
_GATE_KEYWORDS = (
    "门禁", "强制", "必须", "禁止", "不得", "硬性", "前置", "校验",
    "reject", "fail-closed", "fail_closed", "required",
)

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")


@dataclass(frozen=True)
class Section:
    """文档章节（扁平切分：到下一个任意级别标题为止）。"""

    title: str
    level: int
    start: int  # 1-based 起始行
    end: int  # 1-based 结束行（含）
    chars: int

    @property
    def lines(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True)
class GuideStats:
    step: str
    path: str
    total_chars: int
    mandatory_chars: int
    section_count: int
    truncated: bool

    @property
    def ratio(self) -> float:
        """强制层占全文的比例。越小说明渐进披露收益越大。"""
        if self.total_chars <= 0:
            return 0.0
        return round(self.mandatory_chars / self.total_chars, 4)


class StepGuide:
    """单个步骤文档的渐进披露视图。"""

    def __init__(self, step: str, path: Path) -> None:
        self.step = step
        self.path = Path(path)
        self._text = self.path.read_text(encoding="utf-8", errors="replace")
        self._lines = self._text.splitlines()
        self._frontmatter, self._body_offset = self._split_frontmatter(self._lines)
        self._sections = self._parse_sections()

    # ---- 基础 ----

    @staticmethod
    def _split_frontmatter(lines: list[str]) -> tuple[str, int]:
        if not lines or lines[0].strip() != "---":
            return "", 0
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                return "\n".join(lines[1:idx]), idx + 1
        return "", 0

    def _parse_sections(self) -> tuple[Section, ...]:
        heads: list[tuple[int, str, int]] = []
        for i, line in enumerate(self._lines):
            if i < self._body_offset:
                continue
            m = _HEADING_RE.match(line)
            if m:
                heads.append((len(m.group(1)), m.group(2), i))
        out: list[Section] = []
        for n, (level, title, idx) in enumerate(heads):
            end = heads[n + 1][2] - 1 if n + 1 < len(heads) else len(self._lines) - 1
            chunk = "\n".join(self._lines[idx : end + 1])
            out.append(Section(title=title, level=level, start=idx + 1, end=end + 1, chars=len(chunk)))
        return tuple(out)

    # ---- 查询 ----

    @property
    def total_chars(self) -> int:
        return len(self._text)

    @property
    def frontmatter(self) -> str:
        return self._frontmatter

    def outline(self, *, max_items: int | None = None) -> tuple[Section, ...]:
        """章节索引（懒加载入口，不返回正文）。"""
        secs = self._sections
        return secs if max_items is None else secs[:max_items]

    def section_text(self, title: str, *, max_chars: int | None = None) -> str:
        """按需取某章节正文。"""
        for s in self._sections:
            if s.title == title:
                text = "\n".join(self._lines[s.start - 1 : s.end])
                return text if max_chars is None else text[:max_chars]
        raise KeyError(f"章节不存在：{title}")

    def gate_sections(self) -> tuple[Section, ...]:
        """门禁类章节（强制层候选）。"""
        out = []
        for s in self._sections:
            low = s.title.lower()
            if any(k in s.title or k in low for k in _GATE_KEYWORDS):
                out.append(s)
        return tuple(out)

    # ---- 强制层 ----

    def mandatory_brief(
        self,
        contract: StepContract | None = None,
        *,
        budget: int = DEFAULT_MANDATORY_BUDGET,
    ) -> tuple[str, bool]:
        """构造「必须注入」的门禁简报。

        返回 (文本, 是否因预算丢失内容)。
        - 机器契约（gates.json）优先级最高，永远完整给出；
        - 文档中的门禁段落按预算顺序追加，放不下就跳过并置 truncated=True；
        - 文本本身超预算时才做截断。
        """
        parts: list[str] = [f"# 门禁简报：{self.step}"]

        if contract is not None:
            parts.append("## 机器契约（gates.json，权威）")
            if contract.required_inputs:
                parts.append("必需输入：" + "、".join(p.value or p.id for p in contract.required_inputs))
            if contract.protected_inputs:
                parts.append(
                    "受保护输入（执行中漂移即 fail-closed）："
                    + "、".join(p.value or p.id for p in contract.protected_inputs)
                )
            if contract.outputs:
                # 产物端口全部列出（未标 required 的也是契约产物，落盘即需 artifact 登记）
                rendered = "、".join(
                    f"{p.value or p.id}{'（必需）' if p.required else ''}"
                    for p in contract.outputs
                )
                parts.append("产物端口：" + rendered)
            if contract.required_checks:
                parts.append("边界复检：" + "、".join(contract.required_checks))
            if contract.drift_routes:
                routes = "、".join(f"{k}->{v}" for k, v in contract.drift_routes.items())
                parts.append(f"漂移回流：{routes}")

        truncated = False
        for s in self.gate_sections():
            chunk = "\n".join(self._lines[s.start - 1 : s.end])  # 已含标题行，不再重复加
            if sum(len(p) for p in parts) + len(chunk) > budget:
                truncated = True
                continue
            parts.append(chunk)

        text = "\n\n".join(parts)
        if len(text) > budget:
            text = text[:budget] + "\n…（超出预算被截断）"
            truncated = True
        return text, truncated

    # ---- 报告 ----

    def stats(self, contract: StepContract | None = None, *, budget: int = DEFAULT_MANDATORY_BUDGET) -> GuideStats:
        brief, truncated = self.mandatory_brief(contract, budget=budget)
        return GuideStats(
            step=self.step,
            path=str(self.path),
            total_chars=self.total_chars,
            mandatory_chars=len(brief),
            section_count=len(self._sections),
            truncated=truncated,
        )


def resolve_step_doc(steps_dir: Path, step: str) -> Path | None:
    """按 `steps/` 实时清单解析步骤文档，不写死编号。"""
    steps_dir = Path(steps_dir)
    if not steps_dir.is_dir():
        return None
    for p in sorted(steps_dir.glob("*.md")):
        stem = p.stem
        if stem == step or stem.split("_", 1)[-1] == step:
            return p
    return None


def load_guide(steps_dir: Path, step: str) -> StepGuide | None:
    path = resolve_step_doc(steps_dir, step)
    return StepGuide(step, path) if path else None


def disclosure_report(
    steps_dir: Path,
    contract_steps: Iterable[str],
    contracts: dict[str, StepContract] | None = None,
    *,
    budget: int = DEFAULT_MANDATORY_BUDGET,
) -> tuple[GuideStats, ...]:
    """对全部步骤生成披露统计（供 `icode doctor` 使用）。"""
    out: list[GuideStats] = []
    for step in contract_steps:
        guide = load_guide(steps_dir, step)
        if guide is None:
            continue
        contract = (contracts or {}).get(step)
        out.append(guide.stats(contract, budget=budget))
    return tuple(out)


def summarize(stats: Sequence[GuideStats]) -> str:
    if not stats:
        return "无步骤文档统计"
    total = sum(s.total_chars for s in stats)
    forced = sum(s.mandatory_chars for s in stats)
    ratio = forced / total if total else 0.0
    return (
        f"{len(stats)} 个步骤：全文 {total:,} 字符，强制注入 {forced:,} 字符"
        f"（{ratio:.1%}），节省 {1 - ratio:.1%}"
    )
