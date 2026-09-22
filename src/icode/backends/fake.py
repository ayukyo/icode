"""离线假后端：不联网、不花钱，用于契约测试与 Tool Loop 演练。

口径对齐上游：FakeBackend 的输出**不能作为任何真实验证证据**。
"""

from __future__ import annotations

import json
from typing import Any

from .base import AssistantMessage, Backend, ToolCall


class FakeBackend:
    """按脚本回放响应的后端（离线）。

    script 元素为字符串时返回纯文本；为 dict 时可带 tool_calls。
    """

    name = "fake"

    def __init__(self, script: list[Any] | None = None) -> None:
        self.script: list[Any] = list(script) if script else ["fake response"]
        self.calls: list[dict[str, Any]] = []
        self._index = 0

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self.script)

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
    ) -> AssistantMessage:
        self.calls.append({"messages": messages, "tools": tools, "max_tokens": max_tokens})
        item = self.script[min(self._index, len(self.script) - 1)]
        self._index += 1

        if isinstance(item, dict):
            content = str(item.get("content", ""))
            raw_calls = item.get("tool_calls") or []
        else:
            content, raw_calls = str(item), []

        calls: list[ToolCall] = []
        for idx, raw in enumerate(raw_calls):
            args = raw.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            calls.append(
                ToolCall(id=str(raw.get("id", f"call_{idx}")), name=str(raw["name"]), arguments=args or {})
            )
        return AssistantMessage(
            content=content,
            tool_calls=calls,
            raw={"backend": self.name, "script_index": self._index - 1},
        )


def _protocol_selfcheck() -> None:
    """静态自检：FakeBackend 满足 Backend 协议。"""
    _: Backend = FakeBackend()  # type: ignore[assignment]
