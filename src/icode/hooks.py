"""生命周期 Hooks：只能收紧，不能放宽（R5/W2）。

与既有注入点对齐的三类事件（v1）：

- ``pre_tool``：工具调用前，可提出 Guard 收紧（deny 只加不减、白名单只减不加）；
- ``pre_step``：步骤开始前，可提出 SandboxPolicy 收紧（经既有
  ``sandbox_policy.tighten_policy`` 逐维判定）；
- ``observe``：只读观察，不可改任何策略。

规则：

1. **先判定后应用**：任何收紧候选都要通过只紧判定；放宽一律拒绝并留下审计
   记录（``applied=False`` + 稳定错误码），不影响其他 hook。
2. hook 本身必须是已注册扩展（manifest ``kind=hook``）；未注册即不可执行（G4）。
3. 收紧词表只有 Guard 作用域与沙箱策略两个通道——hook 无法触及
   gates.json / 控制面契约（注册时即拒绝未知事件）。
4. 本模块不提供任何文件写路径；审计记录由调用方决定是否进入事件链。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from .extension_contract import (
    ContractError,
    ExtensionRegistry,
    tighten_guard_scope,
)
from .sandbox_policy import PolicyValidationError, SandboxPolicy, tighten_policy

HOOK_PRE_TOOL = "pre_tool"
HOOK_PRE_STEP = "pre_step"
HOOK_OBSERVE = "observe"
HOOK_EVENTS = frozenset({HOOK_PRE_TOOL, HOOK_PRE_STEP, HOOK_OBSERVE})

# 观察事件载荷上限：hook 不得借观察通道搬运大段正文。
_MAX_OBSERVE_CHARS = 4000
_NAME_PREFIX = "hook_"


class HookError(RuntimeError):
    """hook 注册或执行非法；错误码稳定。"""


def _validate_hook_name(name: object) -> str:
    if not isinstance(name, str) or not name:
        raise HookError("hook_name: 必须为非空字符串")
    if len(name) > 64:
        raise HookError("hook_name: 超过 64 字符上限")
    return name


@dataclass(frozen=True)
class Hook:
    """一个声明式 hook：事件 + 收紧候选构造器（或观察回调）。"""

    name: str
    event: str
    description: str = ""
    tighten: Callable[..., object] | None = None
    observe: Callable[[str, Mapping[str, object]], None] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _validate_hook_name(self.name))
        if self.event not in HOOK_EVENTS:
            raise HookError(f"hook_event_unknown: {self.event!r}")
        if len(self.description) > 500:
            raise HookError("hook_description: 超过 500 字符上限")
        if self.event in (HOOK_PRE_TOOL, HOOK_PRE_STEP):
            if not callable(self.tighten):
                raise HookError("hook_tighten_missing: 收紧型 hook 必须提供候选构造器")
        if self.event == HOOK_OBSERVE and not callable(self.observe):
            raise HookError("hook_observe_missing: 观察型 hook 必须提供观察回调")


class HookRegistry:
    """注册表：hook 必须绑定已注册的 manifest（G4），且 manifest 类型为 hook。"""

    def __init__(self, manifests: ExtensionRegistry | None = None) -> None:
        self._manifests = manifests
        self._hooks: dict[str, Hook] = {}

    def register(self, hook: Hook) -> Hook:
        if not isinstance(hook, Hook):
            raise HookError("hook_type: 需要 Hook")
        if self._manifests is not None:
            manifest = self._manifests.get(hook.name)
            if manifest is None:
                raise HookError(f"hook_not_registered: {hook.name}")
            if manifest.kind != "hook":
                raise HookError(f"hook_manifest_kind_mismatch: {manifest.kind}")
        if hook.name in self._hooks:
            raise HookError(f"hook_duplicate: {hook.name}")
        self._hooks[hook.name] = hook
        return hook

    def hooks_for(self, event: str) -> list[Hook]:
        if event not in HOOK_EVENTS:
            raise HookError(f"hook_event_unknown: {event!r}")
        return [self._hooks[name] for name in sorted(self._hooks)
                if self._hooks[name].event == event]

    def names(self) -> list[str]:
        return sorted(self._hooks)


def _audit(hook: Hook, applied: bool, code: str = "") -> dict[str, object]:
    record: dict[str, object] = {"hook": hook.name, "event": hook.event, "applied": applied}
    if code:
        record["code"] = code
    return record


def apply_guard_tightenings(
    hooks: Iterable[Hook],
    deny: Iterable[str],
    allow: Iterable[str],
) -> tuple[set[str], set[str], list[dict[str, object]]]:
    """顺序应用 Guard 收紧；每个候选只与“当前已收紧状态”比较，单调只紧。"""
    current_deny, current_allow = set(deny), set(allow)
    audit: list[dict[str, object]] = []
    for hook in hooks:
        try:
            candidate = hook.tighten(current_deny, current_allow)  # type: ignore[misc]
            if not isinstance(candidate, tuple) or len(candidate) != 2:
                raise ContractError("hook_tighten_shape: 需要 (deny, allow) 二元组")
            next_deny, next_allow = tighten_guard_scope(
                current_deny, current_allow, candidate[0], candidate[1],
            )
        except (ContractError, PolicyValidationError, TypeError, ValueError) as error:
            audit.append(_audit(hook, False, str(error).split(":", 1)[0]))
            continue
        except Exception as error:  # noqa: BLE001 - 第三方 hook 异常不外泄、不中断
            audit.append(_audit(hook, False, f"hook_error:{type(error).__name__}"))
            continue
        current_deny, current_allow = set(next_deny), set(next_allow)
        audit.append(_audit(hook, True))
    return current_deny, current_allow, audit


def apply_policy_tightenings(
    hooks: Iterable[Hook],
    base: SandboxPolicy,
) -> tuple[SandboxPolicy, list[dict[str, object]]]:
    """顺序应用沙箱策略收紧；判定完全委托既有 ``tighten_policy``。"""
    if not isinstance(base, SandboxPolicy):
        raise HookError("hook_policy_type: 需要 SandboxPolicy")
    current = base
    audit: list[dict[str, object]] = []
    for hook in hooks:
        try:
            candidate = hook.tighten(current)  # type: ignore[misc]
            if not isinstance(candidate, SandboxPolicy):
                raise ContractError("hook_tighten_type: 需要 SandboxPolicy 候选")
            current = tighten_policy(current, candidate)
        except (ContractError, PolicyValidationError, TypeError, ValueError) as error:
            audit.append(_audit(hook, False, str(error).split(":", 1)[0]))
            continue
        except Exception as error:  # noqa: BLE001 - 同上
            audit.append(_audit(hook, False, f"hook_error:{type(error).__name__}"))
            continue
        audit.append(_audit(hook, True))
    return current, audit


def run_observers(
    hooks: Iterable[Hook],
    event_name: str,
    payload: Mapping[str, object],
) -> list[dict[str, object]]:
    """只读观察：异常不外泄；超限载荷拒绝（观察通道不搬运正文）。"""
    if not isinstance(payload, Mapping):
        raise HookError("hook_observe_payload: 必须是对象")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as error:
        raise HookError(f"hook_observe_payload: 不可序列化（{error}）") from error
    if len(encoded) > _MAX_OBSERVE_CHARS:
        raise HookError("hook_observe_payload: 超出观察载荷上限")
    audit: list[dict[str, object]] = []
    for hook in hooks:
        try:
            hook.observe(event_name, payload)  # type: ignore[misc]
        except Exception as error:  # noqa: BLE001 - 观察者失败不中断主流程
            audit.append(_audit(hook, False, f"hook_error:{type(error).__name__}"))
            continue
        audit.append(_audit(hook, True))
    return audit


def hook_manifest_name(hook_name: str) -> str:
    """hook 名 → 期望的 manifest 名（hook 与 manifest 同名绑定）。"""
    return _validate_hook_name(hook_name)


__all__ = [
    "HOOK_EVENTS",
    "HOOK_OBSERVE",
    "HOOK_PRE_STEP",
    "HOOK_PRE_TOOL",
    "Hook",
    "HookError",
    "HookRegistry",
    "apply_guard_tightenings",
    "apply_policy_tightenings",
    "hook_manifest_name",
    "run_observers",
]
