"""角色上下文派生（R6/W3）：读写范围按角色收紧，不按自觉。

- executor：保留基座写范围（由编排器把写区域收敛到租约范围内）。
- planner / reviewer / verifier / auditor：``write_roots=()`` + deny 追加 +
  网络 DENY，并过既有 ``tighten_policy`` 只紧判定——与
  ``derive_read_only_reviewer_policy`` 同一纪律，但不绑定 review 步。
- ``scope_fingerprint`` 用作用域的**解析后绝对路径与白名单**计算上下文边界
  摘要：边界是算出来的，不是 agent 自报的。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .guard import Scope
from .roles import RoleError, role as _role
from .sandbox_policy import NetworkMode, SandboxPolicy, tighten_policy


def derive_agent_policy(
    base: SandboxPolicy,
    role_name: object,
    *,
    deny_read_roots: Iterable[object] = (),
) -> SandboxPolicy:
    """按角色派生沙箱策略；只读角色只紧不松，未知角色 fail-closed。"""
    if not isinstance(base, SandboxPolicy):
        raise RoleError("unknown_role", "base 策略非法")
    role_obj = _role(role_name)
    if role_obj.may_write:
        return base
    candidate = replace(
        base,
        write_roots=(),
        deny_read_roots=tuple((*base.deny_read_roots, *deny_read_roots)),
        network_mode=NetworkMode.DENY,
        allowed_domains=(),
    )
    return tighten_policy(base, candidate)


def derive_agent_guard_scope(base_scope: Scope, role_name: object) -> Scope:
    """按角色派生 Guard 作用域；只读角色不给任何写根。"""
    role_obj = _role(role_name)
    if role_obj.may_write:
        return base_scope
    return replace(base_scope, allowed_write_roots=())


def converge_policy_to_region(base: SandboxPolicy, region: object) -> SandboxPolicy:
    """把 executor 的写范围收敛到其申报区域（与基座写根的交集），只紧不松。

    区域必须是工作区相对路径且落在某个已授权写根之内；收敛后的策略即该次
    运行的真实上下文边界（结论的 context_digest 用收敛后的 policy_hash）。
    """
    from .write_lease import normalize_region  # noqa: PLC0415 - 避免环导入

    if not isinstance(base, SandboxPolicy):
        raise RoleError("unknown_role", "base 策略非法")
    parts = normalize_region(region)
    region_path = base.workspace_root.joinpath(*parts)
    narrowed = []
    for root in base.write_roots:
        root_path = Path(root)
        if region_path == root_path or root_path in region_path.parents:
            narrowed.append(region_path)
    if not narrowed:
        raise RoleError("region_outside_write_scope",
                        f"区域 {region!r} 不在任何已授权写根之内")
    candidate = replace(base, write_roots=tuple(narrowed))
    return tighten_policy(base, candidate)


def scope_fingerprint(scope: Scope) -> str:
    """上下文边界摘要：解析后路径与白名单的规范化 sha256。"""
    def _roots(value: object) -> list[str] | None:
        if value is None:
            return None
        return sorted(str(item) for item in value)

    payload = {
        "workspace_root": str(scope.workspace_root),
        "readable_roots": _roots(scope.readable_roots),
        "allowed_read_roots": _roots(scope.allowed_read_roots),
        "allowed_read_files": _roots(scope.allowed_read_files),
        "allowed_write_roots": _roots(scope.allowed_write_roots),
        "deny_read_roots": _roots(scope.deny_read_roots),
        "deny_write_roots": _roots(scope.deny_write_roots),
        "command_allowlist": sorted(scope.command_allowlist),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
