"""受控编排（R6/W5）：spawn → run（租约 + 结论）→ step_gate。

契约：

- ``spawn`` 按角色分配身份并派生上下文（只读角色自动只读）；
- ``run`` 在三段保护下执行注入的角色逻辑：身份核对 →（按需）区域写租约 →
  结论入账。**run 不抛执行异常**：工作失败/被拒都记为 ``failed`` /
  ``refused`` 结论（稳定码，异常正文不外泄），只有调用方编程错误（未知
  身份、只读角色申请写区域等）才抛 RoleError/LeaseError。
- ``step_gate`` 只认“所需角色都有 completed 结论”；没有任何放宽路径——
  任一代理失败即 blocked。
- 角色分离由词表保证：executor 的结论永远不能满足 reviewer 的门禁要求。
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .agent_conclusion import AgentConclusion, ConclusionError, ConclusionLedger
from .agent_scope import (
    converge_policy_to_region,
    derive_agent_guard_scope,
    derive_agent_policy,
    scope_fingerprint,
)
from .guard import Scope
from .roles import (
    AgentIdentity,
    RoleError,
    RoleRegistry,
    is_valid_ticket_id,
    role as _role,
)
from .sandbox_policy import SandboxPolicy
from .write_lease import LeaseBusy, LeaseError, WriteLeaseBoard

_MAX_PARALLEL = 4
_MAX_PARALLEL_CEILING = 8


@dataclass(frozen=True)
class AgentHandle:
    """一个已 spawn 的 Agent：身份 + 派生上下文 + 边界摘要。"""

    identity: AgentIdentity
    policy: SandboxPolicy | None
    scope: Scope | None
    context_digest: str

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    @property
    def role_name(self) -> str:
        return self.identity.role


@dataclass(frozen=True)
class GateReceipt:
    """步骤门禁回执：列出每个所需角色的满足情况；无放宽路径。"""

    ok: bool
    required: tuple[str, ...]
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass
class _Job:
    handle: AgentHandle
    work: Callable[[AgentHandle], Mapping[str, Any] | None]
    write_region: object
    evidence: Mapping[str, Any] | None


class AgentTeam:
    """一个工单内的受控多 Agent 编排（进程内并行 + 跨进程区域锁）。"""

    def __init__(
        self,
        ticket_id: object,
        *,
        lease_dir: object = None,
        policy: SandboxPolicy | None = None,
        scope: Scope | None = None,
        max_parallel: int = _MAX_PARALLEL,
        ledger_limit: int = 256,
    ) -> None:
        if not is_valid_ticket_id(ticket_id):
            raise RoleError("invalid_ticket", "ticket_id 形态非法")
        if type(max_parallel) is not int or not 1 <= max_parallel <= _MAX_PARALLEL_CEILING:
            raise RoleError("invalid_parallel", f"max_parallel 必须是 1..{8} 的整数")
        if policy is not None and not isinstance(policy, SandboxPolicy):
            raise RoleError("invalid_policy", "policy 需要 SandboxPolicy")
        if scope is not None and not isinstance(scope, Scope):
            raise RoleError("invalid_scope", "scope 需要 Scope")
        self._ticket_id = ticket_id
        self._policy = policy
        self._scope = scope
        self._max_parallel = max_parallel
        self._registry = RoleRegistry()
        self._ledger = ConclusionLedger(limit=ledger_limit)
        if lease_dir is not None:
            root = (policy.workspace_root if policy is not None
                    else scope.workspace_root if scope is not None else None)
            if root is not None:
                lease_path = Path(lease_dir).resolve()
                root_path = Path(root).resolve()
                if lease_path == root_path or root_path in lease_path.parents:
                    raise LeaseError("invalid_lease_dir",
                                     "租约目录不得位于工作区内（锁文件不是工作产物）")
        self._leases = WriteLeaseBoard(lease_dir) if lease_dir is not None else None
        self._handles: dict[str, AgentHandle] = {}
        self._record_lock = threading.Lock()

    # ---- spawn ----

    def spawn(self, role_name: object) -> AgentHandle:
        identity = self._registry.spawn(role_name, self._ticket_id)
        policy = (derive_agent_policy(self._policy, role_name)
                  if self._policy is not None else None)
        scope = (derive_agent_guard_scope(self._scope, role_name)
                 if self._scope is not None else None)
        if policy is not None and scope is not None:
            # 双源绑定：策略与 Guard 作用域同时进摘要，任一变化都改变边界。
            digest = hashlib.sha256(
                f"{policy.policy_hash}{scope_fingerprint(scope)}".encode("utf-8"),
            ).hexdigest()
        elif policy is not None:
            digest = policy.policy_hash
        elif scope is not None:
            digest = scope_fingerprint(scope)
        else:
            # 没有上下文边界就没有“独立上下文”可言：spawn 即拒，不等到 run。
            raise RoleError("context_boundary_missing",
                            "团队未配置策略或作用域，无法建立上下文边界")
        handle = AgentHandle(identity=identity, policy=policy,
                             scope=scope, context_digest=digest)
        self._handles[identity.agent_id] = handle
        return handle

    def handle(self, agent_id: object) -> AgentHandle:
        known = self._handles.get(agent_id) if isinstance(agent_id, str) else None
        if known is None:
            raise RoleError("unknown_agent", "agent 身份未在本团队发放")
        return known

    # ---- run ----

    def run(
        self,
        handle: AgentHandle,
        work: Callable[[AgentHandle], Mapping[str, Any] | None],
        *,
        step: object,
        write_region: object = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> AgentConclusion:
        identity = self._require_handle(handle)
        step_name = self._validate_step(step)
        kind = _role(identity.role).conclusions_kind
        self._registry.assert_conclusion_kind(identity, kind)
        lease = None
        try:
            if identity.may_write and write_region is None:
                # executor 必须申报写区域：不申报就没有可收敛的写边界，
                # “权限受限”不允许默认全工作区。
                raise RoleError("write_region_required",
                                "executor 运行必须申报 write_region")
            run_handle = handle
            if write_region is not None:
                if not identity.may_write:
                    # 只读角色申请写区域是调用方编程错误：fail-closed 直接拒。
                    self._registry.assert_may_write(identity)
                if self._leases is None:
                    raise LeaseError("lease_unavailable", "团队未配置租约目录")
                if handle.policy is not None and identity.may_write:
                    # 写范围收敛到申报区域：本次运行的真实边界即收敛后策略。
                    narrowed = converge_policy_to_region(handle.policy, write_region)
                    run_handle = AgentHandle(
                        identity=identity, policy=narrowed, scope=handle.scope,
                        context_digest=narrowed.policy_hash,
                    )
                try:
                    lease = self._leases.acquire(write_region, identity.agent_id)
                except LeaseBusy:
                    # 区域冲突是运行时事实：记 refused 结论，让门禁看见缺口，
                    # 而不是让一个代理的占用把整个编排炸掉。
                    return self._record(run_handle, step_name, kind, "refused", {},
                                        "lease_busy")
            if not run_handle.context_digest:
                return self._record(run_handle, step_name, kind, "refused", {},
                                    "context_boundary_missing")
            try:
                produced = work(run_handle)
            except Exception:  # noqa: BLE001 - 工作异常只留稳定码，正文不外泄
                return self._record(run_handle, step_name, kind, "failed", {},
                                    "agent_work_failed")
            try:
                if produced is None or (isinstance(produced, Mapping) and not produced):
                    return self._record(run_handle, step_name, kind, "refused", {},
                                        "evidence_missing")
                if not isinstance(produced, Mapping):
                    return self._record(run_handle, step_name, kind, "failed", {},
                                        "evidence_invalid")
                merged = dict(produced)
                # 身份与边界由编排器强制写入：工作返回值不能伪造或顶替。
                merged["agent_id"] = identity.agent_id
                merged["context_digest"] = run_handle.context_digest
                return self._record(run_handle, step_name, kind, "completed",
                                    merged, "")
            except ConclusionError:
                return self._record(run_handle, step_name, kind, "failed", {},
                                    "evidence_invalid")
        finally:
            if lease is not None:
                self._leases.release(lease)

    def run_parallel(self, jobs: Sequence[tuple[AgentHandle, Callable[[AgentHandle], Mapping[str, Any] | None], object, str]]) -> tuple[AgentConclusion, ...]:
        """并行执行；每个作业独立租约/结论，重叠区域由租约拒绝（不阻塞彼此）。

        作业元组：``(handle, work, write_region, step)``。
        """
        if not isinstance(jobs, Sequence) or isinstance(jobs, (str, bytes)):
            raise RoleError("invalid_jobs", "jobs 必须是序列")
        if len(jobs) > self._max_parallel:
            raise RoleError("too_many_jobs", f"并行上限 {self._max_parallel}")
        results: list[AgentConclusion | None] = [None] * len(jobs)
        errors: list[BaseException | None] = [None] * len(jobs)
        lock = threading.Lock()
        cursor = {"next": 0}

        def worker() -> None:
            while True:
                with lock:
                    index = cursor["next"]
                    cursor["next"] = index + 1
                if index >= len(jobs):
                    return
                handle, work, region, step = jobs[index]
                try:
                    results[index] = self.run(handle, work, step=step,
                                              write_region=region)
                except Exception as exc:  # noqa: BLE001 - 线程内异常必须浮出，不许静默丢结果
                    # 逃逸异常同样入账为 failed 结论：审计链完整，门禁必然 blocked。
                    try:
                        self._record(handle, self._validate_step(step),
                                     _role(handle.identity.role).conclusions_kind,
                                     "failed", {}, "agent_work_failed")
                    except Exception:  # noqa: BLE001 - 记账失败不得掩盖原始异常
                        pass
                    errors[index] = exc

        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(min(self._max_parallel, len(jobs)))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for error in errors:
            if error is not None:
                raise error
        return tuple(item for item in results if item is not None)

    # ---- gate ----

    def step_gate(self, step: object, required: Mapping[str, str]) -> GateReceipt:
        """门禁：本步骤内每个 (role, kind) 都必须有 completed 结论；无放宽路径。"""
        step_name = self._validate_step(step)
        if not isinstance(required, Mapping) or not required:
            raise RoleError("invalid_gate", "required 必须为非空映射")
        required_pairs: list[str] = []
        satisfied: list[str] = []
        missing: list[str] = []
        for role_name, kind in required.items():
            expected = _role(role_name).conclusions_kind
            if not isinstance(kind, str) or kind != expected:
                raise RoleError("conclusion_out_of_role",
                                f"角色 {role_name} 的门禁结论必须是 {expected}")
            pair = f"{role_name}:{kind}"
            required_pairs.append(pair)
            if self._ledger.has_completed(role_name, kind, step_name):
                satisfied.append(pair)
            else:
                missing.append(pair)
        return GateReceipt(ok=not missing, required=tuple(required_pairs),
                           satisfied=tuple(satisfied), missing=tuple(missing))

    # ---- 视图 ----

    def conclusions(self) -> list[dict[str, Any]]:
        return self._ledger.project()

    # ---- 内部 ----

    @staticmethod
    def _validate_step(step: object) -> str:
        if not isinstance(step, str) or not step.strip() or len(step) > 64:
            raise RoleError("invalid_step", "step 必须为 1..64 字符")
        return step.strip()

    def _require_handle(self, handle: object) -> AgentIdentity:
        if not isinstance(handle, AgentHandle):
            raise RoleError("invalid_handle", "需要 AgentHandle")
        return self._registry.require(handle.identity.agent_id)

    def _record(
        self,
        handle: AgentHandle,
        step: str,
        kind: str,
        outcome: str,
        evidence: Mapping[str, Any],
        detail: str,
    ) -> AgentConclusion:
        identity = handle.identity
        conclusion = AgentConclusion(
            agent_id=identity.agent_id, role=identity.role,
            ticket_id=identity.ticket_id, step=step,
            kind=kind, context_digest=handle.context_digest,
            outcome=outcome, evidence=dict(evidence), detail=detail,
        )
        self._ledger.record(conclusion)
        return conclusion
