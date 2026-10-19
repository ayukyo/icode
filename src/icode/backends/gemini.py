"""Google Gemini generateContent 后端（标准库实现，零第三方依赖）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .base import AssistantMessage, Backend, ToolCall, strip_think
from .openai_compatible import BackendError, Usage
from .pricing import estimate_cost
from .transport import parse_tool_arguments, post_json, tool_specs_openai

DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
API_VERSION = "v1beta"


def _convert_messages(
    messages: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """规范消息 → Gemini systemInstruction 文本 + contents。"""
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    names: dict[str, str] = {}
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
            contents.append({"role": "user",
                             "parts": [{"text": str(raw.get("content") or "")}]})
            continue
        if role == "assistant":
            parts: list[dict[str, Any]] = []
            text = str(raw.get("content") or "")
            if text:
                parts.append({"text": text})
            for index, call in enumerate(raw.get("tool_calls") or []):
                if not isinstance(call, dict):
                    continue
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                call_id = str(call.get("id") or f"call_{index}")
                name = str(fn.get("name") or "")
                names[call_id] = name
                parts.append({"functionCall": {
                    "name": name,
                    "args": parse_tool_arguments(fn.get("arguments")),
                }})
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue
        if role == "tool":
            call_id = str(raw.get("tool_call_id") or "")
            contents.append({"role": "user", "parts": [{"functionResponse": {
                "name": names.get(call_id, call_id or "tool"),
                "response": {"content": str(raw.get("content") or "")},
            }}]})
    return system_parts, contents


@dataclass
class GeminiBackend:
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
    name: str = "gemini"
    usage: Usage = field(default_factory=lambda: Usage(calls=0, cost_usd=0.0))  # 0.0 是费用求和的单位元：零观测不污染首次估算（W2 发现）
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
        system_parts, contents = _convert_messages(messages)
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        generation: dict[str, Any] = {"maxOutputTokens": max_tokens}
        if self.temperature is not None:
            generation["temperature"] = self.temperature
        payload["generationConfig"] = generation
        specs = tool_specs_openai(tools)
        if specs:
            declarations = [
                {"name": spec["name"], "description": spec.get("description", ""),
                 "parameters": spec["parameters"]}
                for spec in specs
            ]
            payload["tools"] = [{"functionDeclarations": declarations}]
            mode = "ANY" if tool_choice == "required" else "AUTO"
            payload["toolConfig"] = {"functionCallingConfig": {"mode": mode}}
        result = post_json(
            url=f"{self.base_url}/{self.api_version}/models/{self.model}:generateContent",
            payload=payload,
            headers={"x-goog-api-key": self.api_key},
            timeout=self.timeout,
            max_retries=self.max_retries,
            retry_backoff=self.retry_backoff,
            proxy=self.proxy,
            no_proxy=self.no_proxy,
            on_retry=lambda: setattr(self.usage, "retries", self.usage.retries + 1),
        )
        data = result.data

        meta = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
        prompt = int(meta.get("promptTokenCount") or 0)
        completion = int(meta.get("candidatesTokenCount") or 0)
        total = int(meta.get("totalTokenCount") or (prompt + completion))
        self.last_usage = Usage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            cached_tokens=int(meta.get("cachedContentTokenCount") or 0),
            latency_ms=result.latency_ms,
        )
        self.last_usage.cost_usd = estimate_cost(self.model, self.last_usage)
        self.usage = self.usage.merge(self.last_usage)
        try:
            candidates = data["candidates"]
            if not isinstance(candidates, list) or not candidates:
                raise TypeError("candidates")
            parts = candidates[0]["content"]["parts"]
            if not isinstance(parts, list):
                raise TypeError("parts")
            texts: list[str] = []
            calls: list[ToolCall] = []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if isinstance(part.get("text"), str):
                    texts.append(part["text"])
                call = part.get("functionCall")
                if isinstance(call, dict):
                    calls.append(ToolCall(
                        id=str(call.get("id") or f"call_{len(calls)}"),
                        name=str(call.get("name") or ""),
                        arguments=parse_tool_arguments(call.get("args")),
                    ))
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise BackendError("响应结构异常（详情已隐藏）") from None

        return AssistantMessage(
            content=strip_think("".join(texts)),
            tool_calls=calls,
            raw={"model": data.get("modelVersion"),
                 "finish_reason": candidates[0].get("finishReason")},
        )


def _protocol_selfcheck() -> None:
    _: Backend = GeminiBackend(api_key="x")  # type: ignore[assignment]
