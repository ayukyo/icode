"""Anthropic Messages API 后端（标准库实现，零第三方依赖）。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from .base import AssistantMessage, Backend, ToolCall, strip_think
from .openai_compatible import BackendError, Usage
from .transport import parse_tool_arguments, post_json, tool_specs_openai

DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    """规范消息（OpenAI 风格）→ Anthropic system + messages。"""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        role = raw.get("role")
        if role == "system":
            text = str(raw.get("content") or "")
            if text:
                system_parts.append(text)
            continue
        if role == "user":
            converted.append({
                "role": "user",
                "content": [{"type": "text", "text": str(raw.get("content") or "")}],
            })
            continue
        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            text = str(raw.get("content") or "")
            if text:
                blocks.append({"type": "text", "text": text})
            for index, call in enumerate(raw.get("tool_calls") or []):
                if not isinstance(call, dict):
                    continue
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                call_id = str(call.get("id") or f"call_{index}")
                name = str(fn.get("name") or "")
                blocks.append({
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": parse_tool_arguments(fn.get("arguments")),
                })
            if blocks:
                converted.append({"role": "assistant", "content": blocks})
            continue
        if role == "tool":
            converted.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": str(raw.get("tool_call_id") or ""),
                    "content": str(raw.get("content") or ""),
                }],
            })
    return system_parts, converted


@dataclass
class AnthropicBackend:
    api_key: str = field(repr=False)
    model: str = ""
    base_url: str = field(default="", repr=False)
    timeout: int = 180
    temperature: float | None = None
    proxy: str | None = field(default=None, repr=False)
    no_proxy: bool = False
    max_retries: int = 2
    retry_backoff: float = 1.5
    api_version: str = API_VERSION
    name: str = "anthropic"
    usage: Usage = field(default_factory=lambda: Usage(calls=0))
    last_usage: Usage = field(default_factory=Usage, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise BackendError("api_key 为空")
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
        system_parts, converted = _convert_messages(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": converted,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        specs = tool_specs_openai(tools)
        if specs:
            payload["tools"] = [
                {"name": spec["name"], "description": spec.get("description", ""),
                 "input_schema": spec["parameters"]}
                for spec in specs
            ]
            if tool_choice == "required":
                payload["tool_choice"] = {"type": "any"}
            elif tool_choice != "auto":
                payload["tool_choice"] = {"type": "tool", "name": tool_choice}
        result = post_json(
            url=f"{self.base_url}/v1/messages",
            payload=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
            },
            timeout=self.timeout,
            max_retries=self.max_retries,
            retry_backoff=self.retry_backoff,
            proxy=self.proxy,
            no_proxy=self.no_proxy,
            on_retry=lambda: setattr(self.usage, "retries", self.usage.retries + 1),
        )
        data = result.data

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        prompt = int(usage.get("input_tokens") or 0)
        completion = int(usage.get("output_tokens") or 0)
        self.last_usage = Usage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            latency_ms=result.latency_ms,
        )
        self.usage = self.usage.merge(self.last_usage)
        try:
            blocks = data["content"]
            if not isinstance(blocks, list):
                raise TypeError("content")
            texts: list[str] = []
            calls: list[ToolCall] = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    texts.append(str(block.get("text") or ""))
                elif block.get("type") == "tool_use":
                    calls.append(ToolCall(
                        id=str(block.get("id") or f"toolu_{len(calls)}"),
                        name=str(block.get("name") or ""),
                        arguments=parse_tool_arguments(block.get("input")),
                    ))
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            raise BackendError("响应结构异常（详情已隐藏）") from None

        return AssistantMessage(
            content=strip_think("".join(texts)),
            tool_calls=calls,
            raw={"model": data.get("model"), "stop_reason": data.get("stop_reason")},
        )


def _protocol_selfcheck() -> None:
    _: Backend = AnthropicBackend(api_key="x")  # type: ignore[assignment]
