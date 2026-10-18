"""压缩与再水合：不丢失硬门禁、用户约束与未闭合副作用（R4/G2）。"""

from __future__ import annotations

import unittest

from icode.compaction import (
    COMPACT_MARKER,
    UNCLOSED_MARKER,
    compact_history,
    history_chars,
    rehydrate,
)

SYSTEM = {"role": "system", "content": "【门禁要求（必须遵守）】review 步骤只读；禁止越界写。"}
REQUIREMENT = {"role": "user", "content": "用户约束：不得修改 src/core.py，只允许改 tests/。"}


def _history(turns: int = 30) -> list[dict]:
    messages = [dict(SYSTEM), dict(REQUIREMENT)]
    for index in range(turns):
        messages.append({"role": "assistant", "content": f"第 {index} 轮分析" + "细节" * 80,
                         "tool_calls": [{"id": f"c{index}", "type": "function",
                                         "function": {"name": "read_file",
                                                      "arguments": "{\"path\": \"a.py\"}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"c{index}",
                         "content": "工具输出" + "正文" * 200})
    messages.append({"role": "assistant", "content": "最终结论：通过。"})
    return messages


class TestCompaction(unittest.TestCase):
    def test_超预算时压缩且受保护项逐字保留(self) -> None:
        messages = _history()
        before = history_chars(messages)
        result = compact_history(
            messages, budget_chars=2000, open_operations=["write_file:attempt-7"],
        )
        self.assertTrue(result.compacted)
        self.assertLess(result.chars_after, before)
        self.assertGreater(result.dropped, 0)
        # 门禁 system 与用户约束逐字保留
        self.assertEqual(result.messages[0], SYSTEM)
        self.assertEqual(result.messages[1], REQUIREMENT)
        self.assertIn(COMPACT_MARKER, result.messages[2]["content"])
        # 未闭合副作用以回执注入，且不被当成已处理
        self.assertTrue(any(UNCLOSED_MARKER in item.get("content", "")
                            for item in result.messages))
        self.assertTrue(any("write_file:attempt-7" in item.get("content", "")
                            for item in result.messages))
        # 尾部保留最近回合
        self.assertEqual(result.messages[-1], messages[-1])

    def test_未超预算不改动(self) -> None:
        messages = [dict(SYSTEM), dict(REQUIREMENT), {"role": "assistant", "content": "短"}]
        before = history_chars(messages)
        result = compact_history(messages, budget_chars=100000)
        self.assertFalse(result.compacted)
        self.assertEqual(result.messages, messages)
        self.assertEqual(result.chars_after, before)
        self.assertEqual(result.digest["dropped"], 0)

    def test_再水合保持不变式且可重复(self) -> None:
        messages = _history()
        first = compact_history(messages, budget_chars=1500,
                                open_operations=["write_file:attempt-7"])
        restored = rehydrate(first)
        self.assertEqual(restored[0], SYSTEM)
        self.assertEqual(restored[1], REQUIREMENT)
        self.assertTrue(any(UNCLOSED_MARKER in item.get("content", "") for item in restored))
        second = compact_history(restored, budget_chars=1500,
                                 open_operations=["write_file:attempt-7"])
        self.assertEqual(second.dropped, 0, "已压缩历史不应再次丢弃受保护项")
        self.assertEqual(second.messages[0], SYSTEM)
        self.assertEqual(second.messages[1], REQUIREMENT)

    def test_入参不被修改(self) -> None:
        messages = _history(4)
        snapshot = [dict(item) for item in messages]
        compact_history(messages, budget_chars=1000, open_operations=["x"])
        self.assertEqual(messages, snapshot)

    def test_非法预算拒绝(self) -> None:
        for budget in (0, -1, "1000", None):
            with self.subTest(budget=budget):
                with self.assertRaises(ValueError):
                    compact_history([dict(SYSTEM)], budget_chars=budget)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
