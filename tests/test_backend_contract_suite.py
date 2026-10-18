"""同一离线契约套件：四个真实后端共用同一组断言（R4/G1）。

不触网：传输层用脚本化的假 opener 替换，请求构造与响应解析完整走真实代码。
"""

from __future__ import annotations

import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from icode.backends import (
    AnthropicBackend,
    GeminiBackend,
    OllamaBackend,
    OpenAICompatibleBackend,
)
from icode.backends.transport import _default_open

SECRET = "sk-contract-secret-marker"


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args) -> bool:
        return False


def _http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.test/x", status, f"error {SECRET}", None, None
    )


class _TransportScript:
    """脚本化 opener：按顺序返回响应或抛异常，并记录请求。"""

    def __init__(self, script) -> None:
        self.script = list(script)
        self.requests: list[urllib.request.Request] = []
        self.payloads: list[dict] = []

    def _next(self, request):
        self.requests.append(request)
        data = getattr(request, "data", None)
        if isinstance(data, bytes):
            self.payloads.append(json.loads(data.decode("utf-8")))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Response(item)

    # transport 后端：post_json 直接调用
    def open_transport(self, request, timeout, proxy, no_proxy):
        return self._next(request)

    # openai 兼容后端：通过 _opener().open(req, timeout=...)
    def open_opener(self, request, timeout=None):
        return self._next(request)


def _cases() -> dict[str, dict]:
    return {
        "anthropic": {
            "build": lambda: AnthropicBackend(
                api_key="k", model="claude-test", base_url="https://api.test"
            ),
            "url": "https://api.test/v1/messages",
            "patch": "transport",
            "auth": ("x-api-key",),
            "response": {
                "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "id": "tu_1", "name": "read_file",
                     "input": {"path": "a.py"}},
                ],
                "usage": {"input_tokens": 11, "output_tokens": 7},
                "model": "claude-test",
            },
            "assert_payload": lambda p: (
                p["model"] == "claude-test"
                and p["max_tokens"] == 64
                and p["system"] == "SYS"
                and p["messages"][-1]["role"] == "user"
                and p["tools"][0]["input_schema"]["type"] == "object"
            ),
        },
        "gemini": {
            "build": lambda: GeminiBackend(
                api_key="k", model="gemini-test", base_url="https://api.test"
            ),
            "url": "https://api.test/v1beta/models/gemini-test:generateContent",
            "patch": "transport",
            "auth": ("x-goog-api-key",),
            "response": {
                "candidates": [{
                    "content": {"parts": [
                        {"text": "ok"},
                        {"functionCall": {"name": "read_file", "args": {"path": "a.py"}}},
                    ]},
                    "finishReason": "STOP",
                }],
                "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7,
                                  "totalTokenCount": 18},
                "modelVersion": "gemini-test",
            },
            "assert_payload": lambda p: (
                p["systemInstruction"]["parts"][0]["text"] == "SYS"
                and p["contents"][-1]["role"] == "user"
                and p["generationConfig"]["maxOutputTokens"] == 64
                and p["tools"][0]["functionDeclarations"][0]["name"] == "read_file"
            ),
        },
        "ollama": {
            "build": lambda: OllamaBackend(
                model="llama-test", base_url="http://127.0.0.1:1"
            ),
            "url": "http://127.0.0.1:1/api/chat",
            "patch": "transport",
            "auth": (),
            "response": {
                "message": {"content": "ok", "tool_calls": [
                    {"function": {"name": "read_file", "arguments": {"path": "a.py"}}}
                ]},
                "prompt_eval_count": 11,
                "eval_count": 7,
            },
            "assert_payload": lambda p: (
                p["model"] == "llama-test"
                and p["stream"] is False
                and p["options"]["num_predict"] == 64
                and p["messages"][0]["role"] == "system"
                and p["tools"][0]["function"]["name"] == "read_file"
            ),
        },
        "openai-compatible": {
            "build": lambda: OpenAICompatibleBackend(
                api_key="k", model="oa-test", base_url="https://api.test"
            ),
            "url": "https://api.test/chat/completions",
            "patch": "opener",
            "auth": ("Authorization",),
            "response": {
                "choices": [{"message": {"content": "ok", "tool_calls": [
                    {"id": "c1", "function": {"name": "read_file",
                                              "arguments": "{\"path\": \"a.py\"}"}}
                ]}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7,
                          "total_tokens": 18},
            },
            "assert_payload": lambda p: (
                p["model"] == "oa-test"
                and p["max_tokens"] == 64
                and p["messages"][0]["role"] == "system"
                and p["tools"][0]["function"]["name"] == "read_file"
            ),
        },
    }


TOOLS = [{"type": "function", "function": {
    "name": "read_file", "description": "read",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
}}]
MESSAGES = [
    {"role": "system", "content": "SYS"},
    {"role": "user", "content": "read a.py"},
]


def _invoke(case: dict, script: list) -> tuple[object, _TransportScript]:
    backend = case["build"]()
    transport = _TransportScript(script)
    if case["patch"] == "transport":
        patcher = patch("icode.backends.transport._default_open",
                        transport.open_transport)
    else:
        patcher = patch.object(backend, "_opener",
                               lambda: type("O", (), {"open": transport.open_opener})())
    with patcher:
        message = backend.complete(MESSAGES, tools=TOOLS, max_tokens=64)
    return (backend, message, transport)


class TestBackendContractSuite(unittest.TestCase):
    """同一组断言跑四个真实后端：协议差异被隔离在各自的转换层。"""

    def test_请求形状与鉴权头一致(self) -> None:
        for name, case in _cases().items():
            with self.subTest(backend=name):
                payload = json.dumps(case["response"]).encode("utf-8")
                _, _, transport = _invoke(case, [payload])
                self.assertEqual(len(transport.requests), 1)
                request = transport.requests[0]
                self.assertEqual(request.full_url, case["url"])
                self.assertEqual(request.get_method(), "POST")
                headers = {k.lower(): v for k, v in request.header_items()}
                self.assertEqual(headers.get("content-type"), "application/json")
                for header in case["auth"]:
                    self.assertIn(header.lower(), headers)
                self.assertTrue(case["assert_payload"](transport.payloads[0]),
                                f"{name} payload={transport.payloads[0]}")

    def test_响应解析与用量记账一致(self) -> None:
        for name, case in _cases().items():
            with self.subTest(backend=name):
                payload = json.dumps(case["response"]).encode("utf-8")
                backend, message, _ = _invoke(case, [payload])
                self.assertEqual(message.content, "ok")
                self.assertEqual(len(message.tool_calls), 1)
                call = message.tool_calls[0]
                self.assertEqual(call.name, "read_file")
                self.assertEqual(call.arguments, {"path": "a.py"})
                self.assertEqual(backend.last_usage.prompt_tokens, 11)
                self.assertEqual(backend.last_usage.completion_tokens, 7)
                self.assertGreaterEqual(backend.last_usage.latency_ms, 0)
                self.assertEqual(backend.usage.calls, 1)
                self.assertIsInstance(backend.last_usage.as_metrics(), dict)

    def test_限流状态有界重试且成功(self) -> None:
        for name, case in _cases().items():
            with self.subTest(backend=name):
                payload = json.dumps(case["response"]).encode("utf-8")
                backend, message, transport = _invoke(
                    case, [_http_error(503), payload]
                )
                self.assertEqual(message.content, "ok")
                self.assertEqual(len(transport.requests), 2)
                # 重试计数累计在 usage 上；last_usage 只描述最后一次成功调用。
                self.assertEqual(backend.usage.retries, 1)
                self.assertEqual(backend.last_usage.retries, 0)

    def test_四xx不重试且错误不含响应正文(self) -> None:
        for name, case in _cases().items():
            with self.subTest(backend=name):
                backend = case["build"]()
                transport = _TransportScript([_http_error(401)])
                if case["patch"] == "transport":
                    patcher = patch("icode.backends.transport._default_open",
                                    transport.open_transport)
                else:
                    patcher = patch.object(
                        backend, "_opener",
                        lambda: type("O", (), {"open": transport.open_opener})(),
                    )
                with patcher:
                    with self.assertRaises(Exception) as caught:
                        backend.complete(MESSAGES, tools=TOOLS, max_tokens=64)
                self.assertEqual(len(transport.requests), 1)
                self.assertEqual(backend.usage.retries, 0)
                self.assertNotIn(SECRET, str(caught.exception))
                self.assertIn("HTTP 401", str(caught.exception))

    def test_结构异常统一为隐藏详情(self) -> None:
        for name, case in _cases().items():
            with self.subTest(backend=name):
                bogus = json.dumps({"unexpected": SECRET}).encode("utf-8")
                backend = case["build"]()
                transport = _TransportScript([bogus])
                if case["patch"] == "transport":
                    patcher = patch("icode.backends.transport._default_open",
                                    transport.open_transport)
                else:
                    patcher = patch.object(
                        backend, "_opener",
                        lambda: type("O", (), {"open": transport.open_opener})(),
                    )
                with patcher:
                    with self.assertRaises(Exception) as caught:
                        backend.complete(MESSAGES, tools=TOOLS, max_tokens=64)
                self.assertIn("响应结构异常（详情已隐藏）", str(caught.exception))
                self.assertNotIn(SECRET, str(caught.exception))

    def test_畸形JSON失败但不泄露正文(self) -> None:
        for name, case in _cases().items():
            with self.subTest(backend=name):
                backend = case["build"]()
                transport = _TransportScript([b"not-json " + SECRET.encode()])
                if case["patch"] == "transport":
                    patcher = patch("icode.backends.transport._default_open",
                                    transport.open_transport)
                else:
                    patcher = patch.object(
                        backend, "_opener",
                        lambda: type("O", (), {"open": transport.open_opener})(),
                    )
                with patcher:
                    with self.assertRaises(Exception) as caught:
                        backend.complete(MESSAGES, tools=TOOLS, max_tokens=64)
                self.assertNotIn(SECRET, str(caught.exception))


@unittest.skipUnless(
    os.environ.get("ICODE_RUN_REAL_MODEL_SMOKE") == "1"
    and os.environ.get("ICODE_LLM_API_KEY"),
    "需显式 ICODE_RUN_REAL_MODEL_SMOKE=1 与 ICODE_LLM_API_KEY 才跑真实模型冒烟",
)
class TestRealModelSmoke(unittest.TestCase):
    """真实调用只做冒烟：一条消息、一个回合，验证接线与用量记账。"""

    def test_真实模型单回合(self) -> None:
        from icode.backends import build_backend

        backend = build_backend(
            "openai-compatible",
            model=os.environ.get("ICODE_LLM_MODEL") or "",
            base_url=os.environ.get("ICODE_LLM_BASE_URL") or "",
        )
        message = backend.complete(
            [{"role": "user", "content": "只回复两个字：收到"}], max_tokens=32
        )
        self.assertIsInstance(message.content, str)
        self.assertGreater(backend.last_usage.total_tokens, 0)
        self.assertGreater(backend.last_usage.latency_ms, 0)
