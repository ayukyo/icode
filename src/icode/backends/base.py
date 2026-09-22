"""模型后端抽象：最小契约 —— 一个回合产出一条助手消息（可含 tool_calls）。

Phase 1 只实现 FakeBackend（离线、零成本、可进 CI）。
真模型后端（OpenAI 兼容 / Anthropic）属 Phase 2。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str | None) -> str:
    """剥离推理模型的思考标签（如 MiniMax-M3 的 <think>...</think>）。"""
    if not text:
        return ""
    return _THINK_RE.sub("", text).strip()


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantMessage:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


@runtime_checkable
class Backend(Protocol):
    name: str

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
    ) -> AssistantMessage:
        """执行一个模型回合。"""
        ...
