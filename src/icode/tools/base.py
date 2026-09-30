"""工具基元：定义、注册表与调用契约。

设计约束：
- 工具**自身不做权限判定**——权限由 `guard.py` 统一裁决，避免规则散落。
- 每个工具声明自己的 `opclass`（read_only / managed_write / ...），供控制面 `operation` 回执使用。
- 输出一律**截断**后再回灌模型，保护上下文预算。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from ..artifact_broker import ArtifactBroker
from ..sandbox_policy import SandboxPolicy
from ..workspace import WorkspaceSession

# 工具输出回灌模型时的字符上限（渐进披露原则：不要把大段正文塞回上下文）
DEFAULT_OUTPUT_LIMIT = 8000

OPCLASS_READ_ONLY = "read_only"
OPCLASS_MANAGED_WRITE = "managed_write"
OPCLASS_EXTERNAL = "external_side_effect"
OPCLASS_DESTRUCTIVE = "destructive_hardware"

_POLICY_DENIAL_ERRORS = frozenset({"read_denied", "write_denied"})
_APPLICATION_POLICY_DENIAL_CATEGORIES = _POLICY_DENIAL_ERRORS | {"guard_denied"}
POLICY_DENIED_USER_MESSAGE = "此操作超出当前任务范围，已阻止。"


def application_policy_violation_receipt(
    operation: str, category: str,
) -> dict[str, object]:
    """Build a safe, explicitly application-layer denial receipt.

    This is not evidence of an operating-system sandbox denial and must never
    be used to satisfy the native ``uniform_violation`` conformance gate.
    """
    if (
        type(operation) is not str
        or not operation
        or len(operation) > 64
        or not operation[0].isascii()
        or not (operation[0].isalnum() or operation[0] == "_")
        or any(
            not char.isascii()
            or not (char.isalnum() or char in "_.-")
            for char in operation[1:]
        )
    ):
        # Tool names are extensible. Never leak malformed/custom labels into
        # receipts, but do not turn a denial into a secondary tool exception.
        operation = "other"
    if (
        type(category) is not str
        or category not in _APPLICATION_POLICY_DENIAL_CATEGORIES
    ):
        raise ValueError("unsupported application policy denial category")
    return {
        "schema_version": 1,
        "enforcement_layer": "application_policy",
        "os_enforced": False,
        "category": category,
        "operation": operation,
    }


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
    read_only_workspace: bool = False
    review_submission_enabled: bool = False
    deny_read_roots: tuple[Path, ...] = ()
    workspace_session: WorkspaceSession | None = None
    # Optional application-layer defense in depth for isolated Reviewers.
    # None preserves ordinary workspace/policy behavior; an empty tuple denies
    # every file read.
    allowed_read_files: tuple[Path, ...] | None = None
    _pinned_read_only_workspace: object | None = field(
        default=None, init=False, repr=False,
    )
    _read_only_workspace_pin_attempted: bool = field(
        default=False, init=False, repr=False,
    )

    def __post_init__(self) -> None:
        if self.allowed_read_files is None:
            return
        try:
            self.allowed_read_files = tuple(
                Path(path).resolve(strict=False)
                for path in self.allowed_read_files
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            # Malformed reviewer scope must never widen into an unrestricted read.
            self.allowed_read_files = ()

    def resolve(self, path: str) -> Path:
        p = Path(path)
        return p if p.is_absolute() else (self.root / p)

    # ---- 隔离 ----

    def needs_real_isolation(self) -> bool:
        return bool(getattr(self.sandbox, "is_real_isolation", False))

    @property
    def read_only_workspace_fd(self) -> int | None:
        """Return the pinned Reviewer root FD, if this backend uses one."""
        return getattr(self._pinned_read_only_workspace, "fd", None)

    def pin_read_only_workspace(self) -> None:
        """Capture the Reviewer root before model-controlled commands can run."""
        if not self.read_only_workspace:
            raise IsolationUnavailable("只有只读 Reviewer 上下文可以固定工作区句柄")
        pin = getattr(self.sandbox, "pin_read_only_workspace", None)
        if not callable(pin):
            return
        if self._pinned_read_only_workspace is not None:
            return
        if self._read_only_workspace_pin_attempted:
            raise IsolationUnavailable("Reviewer 工作区目录句柄已关闭或固定失败")
        self._read_only_workspace_pin_attempted = True
        try:
            self._pinned_read_only_workspace = pin(self.root)
        except Exception as exc:  # noqa: BLE001 - root capture failure is fail-closed
            raise IsolationUnavailable("Reviewer 工作区目录句柄固定失败") from exc

    def close(self) -> None:
        """Release any backend resources acquired for this tool context."""
        pinned = self._pinned_read_only_workspace
        self._pinned_read_only_workspace = None
        fd = getattr(pinned, "fd", None)
        if isinstance(fd, int):
            try:
                os.close(fd)
            except OSError:
                pass

    def isolation_label(self) -> str:
        if self.sandbox is None:
            return "应用层限制，非内核级沙箱"
        describe = getattr(self.sandbox, "describe", None)
        if callable(describe):
            return str(describe().get("claim") or describe().get("backend") or "未知")
        return "应用层限制，非内核级沙箱"

    def wrap_command(self, argv: list[str], *, network: bool = False) -> list[str]:
        """把命令包进沙箱（没有后端时原样返回）。"""
        if self.read_only_workspace:
            # Review 命令必须由操作系统强制只读；策略模式只能使用独立
            # Reviewer 策略编译接口，绝不回退到可写的普通策略 wrapper。
            if self.policy is not None:
                wrap_policy_read_only = getattr(
                    self.sandbox, "wrap_read_only_policy_excluding", None,
                )
                pinned = self._pinned_read_only_workspace
                pinned_fd = getattr(pinned, "fd", None)
                pinned_path = getattr(pinned, "path", None)
                if (
                    network
                    or not self.needs_real_isolation()
                    or not callable(wrap_policy_read_only)
                    or not isinstance(pinned_fd, int)
                    or not isinstance(pinned_path, Path)
                    or self.policy.workspace_root != pinned_path
                ):
                    raise IsolationUnavailable(
                        "当前后端不能验证策略与只读 Reviewer 边界的交集"
                    )
                try:
                    prepared = wrap_policy_read_only(
                        argv,
                        workspace=Path(pinned.path),
                        workspace_fd=pinned_fd,
                        policy=self.policy,
                    )
                    if getattr(prepared, "pass_fds", None) != (pinned_fd,):
                        raise IsolationUnavailable(
                            "策略化 Reviewer 未保留固定工作区 FD 启动合同"
                        )
                    return prepared
                except Exception:  # noqa: BLE001 - 策略/只读边界不能降级
                    raise IsolationUnavailable(
                        f"隔离后端 {getattr(self.sandbox, 'name', '?')} "
                        "无法绑定策略化只读 Reviewer；命令已拒绝"
                    ) from None
            if self.deny_read_roots:
                # 只有显式提供 OS 级排除目录能力的后端才可运行 Reviewer。
                # 普通只读挂载无法隐藏工作区内的工单账本，不能仅靠提示或 Guard。
                wrap_read_only = getattr(self.sandbox, "wrap_read_only_excluding", None)
            else:
                wrap_read_only = getattr(self.sandbox, "wrap_read_only", None)
            if not self.needs_real_isolation() or not callable(wrap_read_only):
                raise IsolationUnavailable(
                    "Reviewer 命令要求真实只读沙箱及可验证的排除目录能力，已拒绝执行"
                )
            try:
                pin = getattr(self.sandbox, "pin_read_only_workspace", None)
                workspace = self.root
                arguments: dict[str, object] = {
                    "workspace": workspace, "network": network,
                }
                if callable(pin):
                    if self._pinned_read_only_workspace is None:
                        raise IsolationUnavailable(
                            "Reviewer 工作区目录未在上下文建立阶段固定"
                        )
                    workspace = Path(self._pinned_read_only_workspace.path)
                    arguments["workspace"] = workspace
                    arguments["workspace_fd"] = self._pinned_read_only_workspace.fd
                if self.deny_read_roots:
                    arguments["deny_read_roots"] = self.deny_read_roots
                prepared = wrap_read_only(argv, **arguments)
                if callable(pin):
                    expected_fds = (self._pinned_read_only_workspace.fd,)
                    if getattr(prepared, "pass_fds", None) != expected_fds:
                        raise IsolationUnavailable(
                            "Reviewer 沙箱未保留工作区 FD 启动合同"
                        )
                    return prepared
                return list(prepared)
            except Exception:  # noqa: BLE001 - 只读边界失败时不允许降级执行
                raise IsolationUnavailable(
                    f"隔离后端 {getattr(self.sandbox, 'name', '?')} 无法绑定只读 Reviewer；"
                    "命令已拒绝"
                ) from None
        if self.policy is not None:
            wrap_policy = self._policy_command_wrapper()
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

    def _policy_command_wrapper(self):
        """Return the policy wrapper only after enforcing ToolContext binding."""
        if self.read_only_workspace:
            raise IsolationUnavailable("策略化 Reviewer 命令尚无可验证的只读策略绑定")
        wrap_policy = getattr(self.sandbox, "wrap_policy", None)
        if (
            self.policy is None
            or not self.needs_real_isolation()
            or not callable(wrap_policy)
            or self.policy.workspace_root != self.root.resolve()
        ):
            raise IsolationUnavailable("原生后端尚不能执行该工单的完整隔离策略")
        return wrap_policy

    def wrap_command_with_violation_receipt(
        self, argv: list[str], control_socket: object,
    ) -> list[str]:
        """Wrap a command for native receipts without bypassing context binding."""
        self._policy_command_wrapper()
        wrap_receipt = getattr(self.sandbox, "wrap_policy_with_violation_receipt", None)
        if not callable(wrap_receipt):
            raise IsolationUnavailable("原生违规回执通道不可用，命令已拒绝")
        try:
            return list(wrap_receipt(
                argv, policy=self.policy, control_socket=control_socket,
            ))
        except Exception:  # noqa: BLE001 - handoff 包装失败时拒绝执行
            raise IsolationUnavailable("工单隔离策略绑定失败，命令已拒绝") from None


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
            result = tool.run(ctx, arguments)
            if not result.ok and result.meta.get("error") in _POLICY_DENIAL_ERRORS:
                # 稳定的用户提示与机器码统一；保留 error 作为调用方兼容的细分原因。
                meta = dict(result.meta)
                meta["error_code"] = "policy_denied"
                meta["violation_receipt"] = application_policy_violation_receipt(
                    name, str(result.meta["error"]),
                )
                return ToolResult(
                    False, POLICY_DENIED_USER_MESSAGE, meta, opclass=result.opclass,
                )
            return result
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
