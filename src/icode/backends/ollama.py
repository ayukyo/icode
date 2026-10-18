"""Ollama 本地模型后端（`/api/chat` 原生协议，标准库实现）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .base import AssistantMessage, Backend, ToolCall, strip_think
from .openai_compatible import BackendError, Usage
from .transport import parse_tool_arguments, post_json, tool_specs_openai

DEFAULT_MODEL = "llama3.1"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"


def _convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """规范消息 → Ollama chat messages（保持角色，工具调用去掉 type 包装）。"""
    converted: list[dict[str, Any]] = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        role = raw.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            continue
        item: dict[str, Any] = {"role": role, "content": str(raw.get("content") or "")}
        if role == "assistant" and raw.get("tool_calls"):
            calls = []
            for index, call in enumerate(raw["tool_calls"]):
                if not isinstance(call, dict):
                    continue
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                calls.append({"function": {
                    "name": str(fn.get("name") or f"tool_{index}"),
                    "arguments": parse_tool_arguments(fn.get("arguments")),
                }})
            if calls:
                item["tool_calls"] = calls
        converted.append(item)
    return converted


@dataclass
class OllamaBackend:
    """本地模型后端；不强制密钥（仅当部署在需要鉴权的网关后才发送）。"""

    api_key: str = field(default="", repr=False)
    model: str = ""
    base_url: str = field(default="", repr=False)
    timeout: int = 300
    temperature: float | None = None
    proxy: str | None = field(default=None, repr=False)
    no_proxy: bool = False
    max_retries: int = 1
    retry_backoff: float = 1.0
    name: str = "ollama"
    usage: Usage = field(default_factory=lambda: Usage(calls=0))
    last_usage: Usage = field(default_factory=Usage, repr=False)

    def __post_init__(self) -> None:
        if not self.model:
            self.model = os.environ.get("ICODE_LLM_MODEL") or DEFAULT_MODEL
        if not self.base_url:
            self.base_url = (
                os.environ.get("ICODE_LLM_BASE_URL") or DEFAULT_BASE_URL
            ).rstrip("/")

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
        tool_choice: str = "auto",
    ) -> AssistantMessage:
        if not isinstance(tool_choice, str) or not tool_choice:
            raise ValueError("tool_choice 必须为非空模式或工具名")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _convert_messages(messages),
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if self.temperature is not None:
            payload["options"]["temperature"] = self.temperature
        specs = tool_specs_openai(tools)
        if specs:
            payload["tools"] = [
                {"type": "function", "function": {
                    "name": spec["name"],
                    "description": spec.get("description", ""),
                    "parameters": spec["parameters"],
                }}
                for spec in specs
            ]
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        result = post_json(
            url=f"{self.base_url}/api/chat",
            payload=payload,
            headers=headers,
            timeout=self.timeout,
            max_retries=self.max_retries,
            retry_backoff=self.retry_backoff,
            proxy=self.proxy,
            no_proxy=self.no_proxy,
            on_retry=lambda: setattr(self.usage, "retries", self.usage.retries + 1),
        )
        data = result.data

        prompt = int(data.get("prompt_eval_count") or 0)
        completion = int(data.get("eval_count") or 0)
        self.last_usage = Usage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            latency_ms=result.latency_ms,
        )
        self.usage = self.usage.merge(self.last_usage)
        try:
            message = data["message"]
            if not isinstance(message, dict):
                raise TypeError("message")
            calls: list[ToolCall] = []
            for index, raw in enumerate(message.get("tool_calls") or []):
                if not isinstance(raw, dict):
                    continue
                fn = raw.get("function") if isinstance(raw.get("function"), dict) else {}
                calls.append(ToolCall(
                    id=str(raw.get("id") or f"call_{index}"),
                    name=str(fn.get("name") or ""),
                    arguments=parse_tool_arguments(fn.get("arguments")),
                ))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise BackendError("响应结构异常（详情已隐藏）") from None

        return AssistantMessage(
            content=strip_think(message.get("content")),
            tool_calls=calls,
            raw={"model": data.get("model"), "done_reason": data.get("done_reason")},
        )


def _protocol_selfcheck() -> None:
    _: Backend = OllamaBackend()  # type: ignore[assignment]
