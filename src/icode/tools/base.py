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

from ..artifact_broker import ArtifactBroker
from ..sandbox_policy import SandboxPolicy

# 工具输出回灌模型时的字符上限（渐进披露原则：不要把大段正文塞回上下文）
DEFAULT_OUTPUT_LIMIT = 8000

OPCLASS_READ_ONLY = "read_only"
OPCLASS_MANAGED_WRITE = "managed_write"
OPCLASS_EXTERNAL = "external_side_effect"
OPCLASS_DESTRUCTIVE = "destructive_hardware"


@dataclass
class ToolContext:
    """工具运行上下文。

    `sandbox` 为可选的隔离后端（见 `isolation.py`）。**没有可用后端时它是 None**，
    此时执行类工具走的是"应用层限制"，元数据里会如实标注，不得宣称沙箱。
    """

    root: Path
    output_limit: int = DEFAULT_OUTPUT_LIMIT
    sandbox: object | None = None
    policy: SandboxPolicy | None = None
    artifact_broker: ArtifactBroker | None = None
    change_baseline: dict[str, str] | None = None

    def resolve(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else (self.root / p)

    # ---- 隔离 ----

    def needs_real_isolation(self) -> bool:
        return bool(getattr(self.sandbox, "is_real_isolation", False))

    def isolation_label(self) -> str:
        if self.sandbox is None:
            return "应用层限制，非内核级沙箱"
        describe = getattr(self.sandbox, "describe", None)
        if callable(describe):
            return str(describe().get("claim") or describe().get("backend") or "未知")
        return "应用层限制，非内核级沙箱"

    def wrap_command(self, argv: list[str], *, network: bool = False) -> list[str]:
        """把命令包进沙箱（没有后端时原样返回）。"""
        if self.policy is not None:
            # 自主会话的策略必须由后端完整绑定；普通 wrap 只证明最小探针，
            # 无法保护可写工作区内的 .git 等例外路径。
            wrap_policy = getattr(self.sandbox, "wrap_policy", None)
            if (not self.needs_real_isolation() or not callable(wrap_policy)
                    or self.policy.workspace_root != self.root.resolve()):
                raise IsolationUnavailable("原生后端尚不能执行该工单的完整隔离策略")
            try:
                return list(wrap_policy(argv, policy=self.policy, network=network))
            except Exception:  # noqa: BLE001 - 策略绑定失败不允许退回普通 wrap
                raise IsolationUnavailable("工单隔离策略绑定失败，命令已拒绝") from None
        wrap = getattr(self.sandbox, "wrap", None)
        if not callable(wrap):
            return list(argv)
        try:
            return list(wrap(argv, workspace=self.root, network=network))
        except Exception:  # noqa: BLE001 - 隔离失败时必须退回安全侧：不执行
            raise IsolationUnavailable(
                f"隔离后端 {getattr(self.sandbox, 'name', '?')} 包装命令失败；"
                "为避免在无隔离状态下执行，已拒绝该命令"
            ) from None


class IsolationUnavailable(RuntimeError):
    """隔离后端不可用/包装失败。**此时拒绝执行，而不是降级执行。**"""


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
