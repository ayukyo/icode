"""预算与成本：**运营指标**（管预算），不作为质量指标（roadmap §5.2）。

用途只有一个：给出 P2 风险闸门的数据 —— "单工单成本超预算 3 倍即回退重设计上下文策略"。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .backends import Usage


@dataclass
class Budget:
    """一次运行的成本预算。`expected_tokens=0` 表示只观测、不设闸门。"""

    expected_tokens: int = 0
    hard_ratio: float = 3.0  # 超过 expected 的多少倍算"必须回退"

    def verdict(self, usage: Usage) -> str:
        if self.expected_tokens <= 0:
            return "observe_only"
        ratio = usage.total_tokens / self.expected_tokens
        if ratio > self.hard_ratio:
            return "over_budget"
        if ratio > 1.0:
            return "above_expected"
        return "within_budget"


@dataclass
class BudgetTracker:
    """累计用量并给出结论。"""

    budget: Budget = field(default_factory=Budget)
    usage: Usage = field(default_factory=lambda: Usage(calls=0))

    def record(self, usage: Usage) -> None:
        self.usage = self.usage.merge(usage)

    @property
    def verdict(self) -> str:
        return self.budget.verdict(self.usage)

    def report(self) -> dict:
        expected = self.budget.expected_tokens
        return {
            "calls": self.usage.calls,
            "total_tokens": self.usage.total_tokens,
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "cached_tokens": self.usage.cached_tokens,
            "reasoning_tokens": self.usage.reasoning_tokens,
            "expected_tokens": expected,
            "ratio": round(self.usage.total_tokens / expected, 3) if expected > 0 else None,
            "verdict": self.verdict,
        }

    def render(self) -> str:
        r = self.report()
        ratio = f"{r['ratio']}x" if r["ratio"] is not None else "n/a"
        return (
            f"成本（运营指标）：{r['calls']} 次调用 / {r['total_tokens']:,} tokens"
            f"（prompt {r['prompt_tokens']:,} / completion {r['completion_tokens']:,}"
            f" / cached {r['cached_tokens']:,}）；预算比 {ratio}；结论 {r['verdict']}"
        )
