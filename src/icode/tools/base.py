"""工具基元：定义、注册表与调用契约。

设计约束：
- 工具**自身不做权限判定**——权限由 `guard.py` 统一裁决，避免规则散落。
- 每个工具声明自己的 `opclass`（read_only / managed_write / ...），供控制面 `operation` 回执使用。
- 输出一律**截断**后再回灌模型，保护上下文预算。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

# 工具输出回灌模型时的字符上限（渐进披露原则：不要把大段正文塞回上下文）
DEFAULT_OUTPUT_LIMIT = 8000

OPCLASS_READ_ONLY = "read_only"
OPCLASS_MANAGED_WRITE = "managed_write"
OPCLASS_EXTERNAL = "external_side_effect"
OPCLASS_DESTRUCTIVE = "destructive_hardware"


@dataclass
class ToolContext:
    """工具运行上下文。"""

    root: Path
    output_limit: int = DEFAULT_OUTPUT_LIMIT

    def resolve(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else (self.root / p)


@dataclass
class ToolResult:
    ok: bool
    content: str
    meta: dict[str, Any] = field(default_factory=dict)
    opclass: str = OPCLASS_READ_ONLY

    def clipped(self, limit: int = DEFAULT_OUTPUT_LIMIT) -> str:
        if len(self.content) <= limit:
            return self.content
        head = self.content[: limit // 2]
        tail = self.content[-limit // 2 :]
        return f"{head}\n…（输出过长已截断 {len(self.content) - limit} 字符）…\n{tail}"


@runtime_checkable
class ToolHandler(Protocol):
    def __call__(self, ctx: ToolContext, **kwargs: Any) -> ToolResult: ...


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., ToolResult]
    opclass: str = OPCLASS_READ_ONLY

    def schema(self) -> dict[str, Any]:
        """OpenAI function calling 形态的 schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        return self.handler(ctx, **arguments)


def _params(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


class ToolRegistry:
    """工具注册表：统一暴露 schema 与调用入口。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"工具重名：{tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def schemas(self, allow: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        names = allow if allow is not None else self.names()
        return [self._tools[n].schema() for n in names if n in self._tools]

    def invoke(self, name: str, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                ok=False,
                content=f"未知工具：{name}。可用：{', '.join(self.names())}",
                meta={"error": "unknown_tool"},
            )
        try:
            return tool.run(ctx, arguments)
        except TypeError as exc:
            return ToolResult(
                ok=False,
                content=f"工具参数不合法：{exc}",
                meta={"error": "bad_arguments"},
                opclass=tool.opclass,
            )
        except Exception as exc:  # noqa: BLE001 - 工具失败要回灌模型而不是中断循环
            return ToolResult(
                ok=False,
                content=f"{type(exc).__name__}: {exc}",
                meta={"error": "tool_exception"},
                opclass=tool.opclass,
            )


def schemas_json(registry: ToolRegistry) -> str:
    return json.dumps(registry.schemas(), ensure_ascii=False)
