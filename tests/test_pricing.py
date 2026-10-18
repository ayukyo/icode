"""价格表与费用估算：只做运营指标，未知不等于免费（R4/W5）。"""

from __future__ import annotations

import unittest

from icode.backends.openai_compatible import Usage
from icode.backends.pricing import estimate_cost, price_for


class TestPricing(unittest.TestCase):
    def test_按模型前缀命中价格(self) -> None:
        self.assertEqual(price_for("claude-sonnet-4-5"), (3.0, 15.0))
        self.assertEqual(price_for("gemini-2.0-flash"), (0.10, 0.40))
        self.assertEqual(price_for("gpt-4o-mini"), (2.5, 10.0))
        self.assertEqual(price_for("MiniMax-M3"), (0.30, 1.20))

    def test_未知模型返回None且不冒充免费(self) -> None:
        for model in ("unknown-model", "", None, 7):
            with self.subTest(model=model):
                self.assertIsNone(price_for(model))
                usage = Usage(prompt_tokens=1000, completion_tokens=1000)
                self.assertIsNone(estimate_cost(model, usage))

    def test_本地模型计价为零(self) -> None:
        usage = Usage(prompt_tokens=5000, completion_tokens=5000)
        self.assertEqual(estimate_cost("llama3.1", usage), 0.0)

    def test_按输入输出分别计价(self) -> None:
        usage = Usage(prompt_tokens=2000, completion_tokens=500)
        # claude: 2000/1000*3 + 500/1000*15 = 6 + 7.5
        self.assertAlmostEqual(estimate_cost("claude-sonnet-4-5", usage), 13.5, places=6)
        usage = Usage(prompt_tokens=1000, completion_tokens=1000)
        # minimax: 1*0.3 + 1*1.2
        self.assertAlmostEqual(estimate_cost("MiniMax-M3", usage), 1.5, places=6)

    def test_异常token不产生费用(self) -> None:
        for usage in (
            Usage(prompt_tokens=-1, completion_tokens=10),
            Usage(prompt_tokens="10", completion_tokens=10),  # type: ignore[arg-type]
            Usage(prompt_tokens=True, completion_tokens=10),  # type: ignore[arg-type]
        ):
            with self.subTest(usage=usage):
                self.assertIsNone(estimate_cost("claude-x", usage))

    def test_费用合并与未知传播(self) -> None:
        known = Usage(cost_usd=1.5)
        known2 = Usage(cost_usd=2.0)
        self.assertEqual(known.merge(known2).cost_usd, 3.5)
        self.assertIsNone(known.merge(Usage(cost_usd=None)).cost_usd)
        self.assertEqual(Usage().as_metrics()["cost_usd"], None)


if __name__ == "__main__":
    unittest.main()
