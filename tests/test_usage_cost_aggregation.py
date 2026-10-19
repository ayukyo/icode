"""多次调用的费用聚合不被零观测污染（收束工作包 W2 回归测试）。

背景：四个真实后端的聚合器曾以 `Usage(calls=0)`（cost=None）起步，
`Usage.merge` 的"任一未知即未知"语义把估算费用永久污染为 None。
修复后：聚合器初始 `cost_usd=0.0`——0.0 是费用求和的加法单位元，
零观测（零成本）不污染首次估算；真实观测的未知仍正确传播为未知。
"""

import json
import unittest
from unittest.mock import patch

from tests.test_backend_contract_suite import MESSAGES, TOOLS, _TransportScript
from icode.backends.anthropic import AnthropicBackend
from icode.backends.gemini import GeminiBackend
from icode.backends.ollama import OllamaBackend
from icode.backends.openai_compatible import OpenAICompatibleBackend
from icode.backends.pricing import price_for

OA_RESPONSE = {
    "choices": [{"message": {"content": "ok"}}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 500,
              "total_tokens": 1500},
}
ANTHROPIC_RESPONSE = {
    "content": [{"type": "text", "text": "ok"}],
    "usage": {"input_tokens": 1000, "output_tokens": 500},
    "model": "minimax-m3",
}
GEMINI_RESPONSE = {
    "candidates": [{"content": {"parts": [{"text": "ok"}]},
                    "finishReason": "STOP"}],
    "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 500,
                      "totalTokenCount": 1500},
    "modelVersion": "minimax-m3",
}
OLLAMA_RESPONSE = {
    "message": {"content": "ok"},
    "prompt_eval_count": 1000,
    "eval_count": 500,
}


def _expected_cost(prompt: int, completion: int) -> float:
    price = price_for("minimax-m3")
    assert price is not None, "pricing 表应含 minimax 前缀（静态估算价）"
    assert price == (0.0003, 0.0012), (
        "MiniMax M3 per-1K 价锁定为 (0.0003, 0.0012)= $0.30/$1.20 per M；"
        "per-M 数字进 per-1K 表曾造成 1000 倍失真"
    )
    return (prompt / 1000) * price[0] + (completion / 1000) * price[1]


class _TwoCallCostCase(unittest.TestCase):
    """同一断言跑四个真实后端：两次调用后聚合费用 = 两次估算之和。"""

    def _drive(self, backend, payload: bytes, *, opener_mode: bool):
        transport = _TransportScript([payload, payload])
        if opener_mode:
            patcher = patch.object(
                backend, "_opener",
                lambda: type("O", (), {"open": transport.open_opener})())
        else:
            patcher = patch("icode.backends.transport._default_open",
                            transport.open_transport)
        with patcher:
            backend.complete(MESSAGES, tools=TOOLS, max_tokens=64)
            backend.complete(MESSAGES, tools=TOOLS, max_tokens=64)
        return backend


class TestOpenAICompatibleCost(_TwoCallCostCase):
    def test_两次调用费用聚合(self):
        backend = self._drive(
            OpenAICompatibleBackend(api_key="k", model="minimax-m3",
                                    base_url="https://api.test"),
            json.dumps(OA_RESPONSE).encode("utf-8"), opener_mode=True,
        )
        self.assertEqual(backend.usage.calls, 2)
        self.assertAlmostEqual(backend.usage.cost_usd,
                               _expected_cost(1000, 500) * 2, places=6)
        self.assertAlmostEqual(backend.last_usage.cost_usd,
                               _expected_cost(1000, 500), places=6)

    def test_零观测时单调用费用可见(self):
        backend = OpenAICompatibleBackend(api_key="k", model="minimax-m3",
                                          base_url="https://api.test")
        payload = json.dumps(OA_RESPONSE).encode("utf-8")
        transport = _TransportScript([payload])
        with patch.object(backend, "_opener",
                          lambda: type("O", (), {"open": transport.open_opener})()):
            backend.complete(MESSAGES, tools=TOOLS, max_tokens=64)
        self.assertEqual(backend.usage.calls, 1)
        self.assertAlmostEqual(backend.usage.cost_usd,
                               _expected_cost(1000, 500), places=6)


class TestAnthropicCost(_TwoCallCostCase):
    def test_两次调用费用聚合(self):
        backend = self._drive(
            AnthropicBackend(api_key="k", model="minimax-m3",
                             base_url="https://api.test"),
            json.dumps(ANTHROPIC_RESPONSE).encode("utf-8"), opener_mode=False,
        )
        self.assertEqual(backend.usage.calls, 2)
        self.assertAlmostEqual(backend.usage.cost_usd,
                               _expected_cost(1000, 500) * 2, places=6)


class TestGeminiCost(_TwoCallCostCase):
    def test_两次调用费用聚合(self):
        backend = self._drive(
            GeminiBackend(api_key="k", model="minimax-m3",
                          base_url="https://api.test"),
            json.dumps(GEMINI_RESPONSE).encode("utf-8"), opener_mode=False,
        )
        self.assertEqual(backend.usage.calls, 2)
        self.assertAlmostEqual(backend.usage.cost_usd,
                               _expected_cost(1000, 500) * 2, places=6)


class TestOllamaCost(_TwoCallCostCase):
    def test_两次调用费用聚合_本地计价为零(self):
        # ollama 模型名 llama-test 命中 "llama": (0.0, 0.0) —— 本地模型计价为 0
        backend = self._drive(
            OllamaBackend(model="llama-test", base_url="http://127.0.0.1:1"),
            json.dumps(OLLAMA_RESPONSE).encode("utf-8"), opener_mode=False,
        )
        self.assertEqual(backend.usage.calls, 2)
        self.assertEqual(backend.usage.cost_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
