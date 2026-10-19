"""模型价格表与费用估算（R4/W5 运营指标）。

口径：
- 价格是**公开标价的静态估算**，不是账单；真实计费对账需要供应商账单接口，
  不在本阶段范围（决策日志已记录）。
- 未知模型返回 None（未知不等于免费）；本地模型计价为 0。
- 费用只进入 `Usage.cost_usd` 与 `as_metrics()`，**不参与任何质量门禁**。
"""

from __future__ import annotations

from typing import Any

# 每 1K tokens 的美元价：(输入, 输出)。按模型名前缀匹配，前缀最长者优先。
PRICES_USD_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "claude": (3.0, 15.0),
    "gemini": (0.10, 0.40),
    "gpt-4o": (2.5, 10.0),
    "gpt": (2.5, 10.0),
    # MiniMax 官方定价（≤512K 档、永久五折后）：$0.30/M 输入、$1.20/M 输出。
    # 表口径为 per-1K，故除 1000（旧值曾把 per-M 直接填进 per-1K 表，高估 1000 倍）。
    "minimax": (0.0003, 0.0012),
    "llama": (0.0, 0.0),
    "qwen": (0.0, 0.0),
}
_MAX_MATCH = max(len(prefix) for prefix in PRICES_USD_PER_1K_TOKENS)


def price_for(model: object) -> tuple[float, float] | None:
    """按前缀查价；未知模型返回 None。"""
    if not isinstance(model, str) or not model:
        return None
    lowered = model.lower()
    for size in range(min(_MAX_MATCH, len(lowered)), 0, -1):
        prefix = lowered[:size]
        if prefix in PRICES_USD_PER_1K_TOKENS:
            return PRICES_USD_PER_1K_TOKENS[prefix]
    return None


def estimate_cost(model: object, usage: Any) -> float | None:
    """按输入/输出 token 估算费用；缺价格或 token 异常时返回 None。"""
    price = price_for(model)
    if price is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if (not isinstance(prompt, int) or isinstance(prompt, bool) or prompt < 0
            or not isinstance(completion, int) or isinstance(completion, bool)
            or completion < 0):
        return None
    input_price, output_price = price
    total = (prompt / 1000.0) * input_price + (completion / 1000.0) * output_price
    return round(total, 8)
