"""自主工单运行时的意图验证、状态机与 worker 生命周期。

本模块只编排可信的服务端 executor。所有持久化统一委托 ``TicketService``，
浏览器字段、异常正文、凭据和路径都不会进入运行时公开事实。
"""

from __future__ import annotations

import copy
import hashlib
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .approvals import Approver
from .backends import Backend
from .budget import Budget
from .chain import ChainReport, chain_steps, run_chain
from .config import Settings
from .contracts import ContractSet
from .control import ControlPlane
from .loop import LoopConfig
from .tickets import TicketError, TicketService

INTENTS = frozenset({"start", "pause", "resume", "cancel", "takeover"})
ACTIVE_STATES = frozenset({
    "starting", "running", "pause_requested", "cancel_requested",
})
TERMINAL_RESULT_STATES = frozenset({"succeeded", "failed", "blocked"})
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,140}$")
_STABLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_STEP_RE = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
_INTENT_RECEIPT_RE = re.compile(r"^[0-9a-f]{64}$")
# 只保留最近 64 个已接受 intent 的稳定摘要，避免运行时 metadata 无界增长。
# 超出窗口的更早请求不再承诺跨重启幂等，控制面仍会 fail-closed 拒绝冲突重放。
_INTENT_RECEIPT_LIMIT = 64

# 同一进程内可能先关旧 Workbench、再建新 Workbench。若旧 worker 因正在模型
# 调用而未在 join 时限内退出，新 manager 也必须看见这份租约，避免两个执行器
# 同时操作同一工单。进程重启后注册表自然清空，持久化恢复仍由控制面状态负责。
_PROCESS_WORKERS_LOCK = threading.RLock()
_PROCESS_WORKERS: dict[str, threading.Thread] = {}


class AutonomyError(RuntimeError):
    """对调用方稳定的自主运行错误；``code`` 不含环境细节。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_intent_payload(payload: object) -> dict[str, str]:
    """严格收敛不可信 intent JSON，拒绝多余能力参数。"""
    if not isinstance(payload, dict) or set(payload) != {"intent", "request_id"}:
        raise AutonomyError("invalid_intent", "意图请求必须只含 intent 和 request_id")
    intent = payload.get("intent")
    request_id = payload.get("request_id")
    if intent not in INTENTS:
        raise AutonomyError("invalid_intent", "intent 不是受支持的稳定动作")
    if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise AutonomyError("invalid_intent", "request_id 格式非法")
    return {"intent": intent, "request_id": request_id}


@dataclass(frozen=True)
class ExecutionContext:
    """只交给可信 executor 的内部上下文；不得序列化进公共响应。"""

    ticket_id: str
    out_dir: Path
    workspace: Path
    requirement: str
    status: str
    completed_steps: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionResult:
    """executor 返回的稳定终态，不携带模型输出或异常正文。"""

    state: str
    last_step: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in TERMINAL_RESULT_STATES:
            raise ValueError("executor result state must be succeeded/failed/blocked")
        if self.last_step is not None and (
            not isinstance(self.last_step, str)
            or _STEP_RE.fullmatch(self.last_step) is None
        ):
            raise ValueError("last_step must be a stable step token")
        if self.error_code is not None and (
            not isinstance(self.error_code, str)
            or _STABLE_CODE_RE.fullmatch(self.error_code) is None
        ):
            raise ValueError("error_code must be a stable code")


class Executor(Protocol):
    """Task 2 可注入 native chain adapter 的最小协议。"""

    def execute(self, context: ExecutionContext, control: "RunControl") -> ExecutionResult:
        ...


class NativeChainExecutor:
    """把原生 ICODE chain 收敛为可在安全点停止的 executor。"""

    def __init__(
        self,
        settings: Settings,
        *,
        backend: Backend,
        step_runner: Callable[..., ChainReport] = run_chain,
        approver: Approver | None = None,
        loop_config: LoopConfig | None = None,
        budget: Budget | None = None,
        on_event: Callable[[str, dict], None] | None = None,
        sandbox: Any = None,
    ) -> None:
        self.settings = settings
        self.backend = backend
        self._step_runner = step_runner
        self.approver = approver
        self.loop_config = loop_config
        self.budget = budget
        self.on_event = on_event
        self.sandbox = sandbox

    def execute(self, context: ExecutionContext, control: "RunControl") -> ExecutionResult:
        out_dir = context.out_dir.resolve()
        try:
            contracts = ContractSet.load(self.settings.gates_json)
        except Exception:  # noqa: BLE001 - 公开结果只保留稳定码。
            return ExecutionResult(state="failed", error_code="chain_error")
        try:
            trace = ControlPlane(self.settings).trace(out_dir)
        except Exception:  # noqa: BLE001 - 禁止持久化控制面异常正文。
            return ExecutionResult(state="failed", error_code="status_unavailable")
        status = trace.data.get("status") if trace.returncode == 0 else None
        if not isinstance(status, str) or not status:
            return ExecutionResult(state="failed", error_code="status_unavailable")
        if trace.data.get("ticket_id") != context.ticket_id:
            return ExecutionResult(state="failed", error_code="invalid_ticket")
        known_statuses = {
            str(value)
            for value in (contracts.state_machine().get("states") or ())
        }
        if status not in known_statuses:
            return ExecutionResult(state="failed", error_code="invalid_status")

        pending = chain_steps(contracts, from_status=status)
        last_step: str | None = None
        for step in pending:
            control.safe_point(step)
            try:
                report = self._step_runner(
                    self.settings,
                    backend=self.backend,
                    workspace=context.workspace,
                    requirement=context.requirement,
                    ticket_id=context.ticket_id,
                    steps=(step,),
                    out_dir=out_dir,
                    approver=self.approver,
                    loop_config=self.loop_config,
                    budget=self.budget,
                    on_event=self.on_event,
                    sandbox=self.sandbox,
                )
            except Exception:  # noqa: BLE001 - 只返回稳定码，不泄露异常正文。
                return ExecutionResult(
                    state="failed", last_step=step, error_code="chain_error")
            # runner 正常返回才构成真实的步骤完成边界。停止意图可能在本步
            # 模型/工具执行期间到达，必须先于 succeeded/blocked 结果收敛；
            # runner 抛异常时不会走到这里，因此不会伪造已完成边界。
            control.safe_point(step)
            last_step = step
            if not report.delivered:
                if report.stopped_at:
                    code = "gate_blocked" if any(
                        item.advance_gates for item in report.steps
                    ) else "step_blocked"
                    return ExecutionResult(
                        state="blocked", last_step=step, error_code=code)
                return ExecutionResult(
                    state="failed", last_step=step, error_code="chain_failed")
        return ExecutionResult(state="succeeded", last_step=last_step)


class _RunStopped(RuntimeError):
    """safe point 已完成受控停止；仅在线程内部传播。"""


class RunControl:
    """executor 在契约步骤边界调用的停止控制器。"""

    def __init__(self, ticket_id: str, run_id: str, manager: "AutonomyManager") -> None:
        self.ticket_id = ticket_id
        self.run_id = run_id
        self._manager = manager
        self._stop_intent: str | None = None

    def safe_point(self, step: str) -> None:
        if not isinstance(step, str) or _STEP_RE.fullmatch(step) is None:
            raise ValueError("safe point step must be a stable step token")
        self._manager._safe_point(self, step)


class AutonomyManager:
    """线程安全的自主 intent 状态机；同一进程内一个工单至多一个 worker。"""

    def __init__(
        self,
        tickets: TicketService,
        *,
        executor: Executor | None,
        enabled: bool = False,
    ) -> None:
        self.tickets = tickets
        self.executor = executor
        self.enabled = bool(enabled and executor is not None)
        self._lock = threading.RLock()
        self._workers: dict[str, threading.Thread] = {}
        self._controls: dict[str, RunControl] = {}
        self._receipts: dict[tuple[str, str, str], dict] = {}
        self._shutting_down = False
        self._recover_stale_runs()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _revision(runtime: object) -> int:
        if not isinstance(runtime, dict):
            return 0
        value = runtime.get("revision")
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    @staticmethod
    def _internal_request(ticket_id: str, suffix: str) -> str:
        digest = hashlib.sha256(f"{ticket_id}|{suffix}".encode("utf-8")).hexdigest()[:20]
        return f"autonomy-{suffix[:80]}-{digest}"

    @staticmethod
    def _intent_receipt_token(ticket_id: str, intent: str, request_id: str) -> str:
        return hashlib.sha256(
            f"{ticket_id}|{intent}|{request_id}".encode("utf-8")
        ).hexdigest()

    def _intent_receipts(self, ticket_id: str, runtime: object) -> list[str]:
        """读取有界 receipt，并把旧版 last_intent 身份纳入兼容窗口。"""
        if not isinstance(runtime, dict):
            return []
        raw = runtime.get("intent_receipts")
        receipts = [
            value for value in raw
            if isinstance(value, str) and _INTENT_RECEIPT_RE.fullmatch(value)
        ] if isinstance(raw, list) else []
        last_intent = runtime.get("last_intent")
        last_request = runtime.get("last_intent_request_id")
        if last_intent in INTENTS and (
            isinstance(last_request, str)
            and _REQUEST_ID_RE.fullmatch(last_request) is not None
        ):
            legacy = self._intent_receipt_token(
                ticket_id, last_intent, last_request)
            if legacy not in receipts:
                receipts.append(legacy)
        return receipts[-_INTENT_RECEIPT_LIMIT:]

    def _append_intent_receipt(
        self,
        ticket_id: str,
        runtime: object,
        intent: str,
        request_id: str,
    ) -> list[str]:
        receipts = self._intent_receipts(ticket_id, runtime)
        token = self._intent_receipt_token(ticket_id, intent, request_id)
        if token not in receipts:
            receipts.append(token)
        return receipts[-_INTENT_RECEIPT_LIMIT:]

    def _ticket(self, ticket_id: str) -> dict:
        try:
            return self.tickets.ticket_detail(ticket_id)
        except TicketError as exc:
            raise AutonomyError("ticket_not_found", "工单不存在或身份不唯一") from exc

    def _execution_context(self, ticket_id: str) -> ExecutionContext:
        try:
            record = self.tickets._resolve_ticket_record(ticket_id)
        except TicketError as exc:
            raise AutonomyError("ticket_not_found", "工单不存在或身份不唯一") from exc
        metadata = record.metadata
        requirement = metadata.get("requirement")
        status = metadata.get("status")
        completed = metadata.get("completed_steps")
        return ExecutionContext(
            ticket_id=ticket_id,
            out_dir=record.out_dir,
            workspace=self.tickets.workspace,
            requirement=requirement if isinstance(requirement, str) else "",
            status=status if isinstance(status, str) else "unknown",
            completed_steps=tuple(str(item) for item in completed)
            if isinstance(completed, list) else (),
        )

    def _raw_runtime(self, ticket_id: str) -> dict:
        """读取仅供状态机使用的原始运行时字段，包括非公开幂等身份。"""
        try:
            record = self.tickets._resolve_ticket_record(ticket_id)
        except TicketError as exc:
            raise AutonomyError("ticket_not_found", "工单不存在或身份不唯一") from exc
        agent = self.tickets._agent_extension(record.metadata)
        runtime = agent.get("autonomous_run")
        return dict(runtime) if isinstance(runtime, dict) else {}

    def _process_worker_key(self, ticket_id: str) -> str:
        try:
            record = self.tickets._resolve_ticket_record(ticket_id)
        except TicketError as exc:
            raise AutonomyError("ticket_not_found", "工单不存在或身份不唯一") from exc
        return str(record.out_dir.resolve())

    @staticmethod
    def _reserve_process_worker(key: str, worker: threading.Thread) -> bool:
        with _PROCESS_WORKERS_LOCK:
            existing = _PROCESS_WORKERS.get(key)
            if existing is not None:
                # ident=None 既可能尚未 start，也可能从未成功 start；注册与 start
                # 紧邻执行，保守视为已占用，直到持有者显式释放。
                if existing.ident is None or existing.is_alive():
                    return False
                _PROCESS_WORKERS.pop(key, None)
            _PROCESS_WORKERS[key] = worker
            return True

    @staticmethod
    def _release_process_worker(key: str, worker: threading.Thread) -> None:
        with _PROCESS_WORKERS_LOCK:
            if _PROCESS_WORKERS.get(key) is worker:
                _PROCESS_WORKERS.pop(key, None)

    def _has_live_process_worker(self, ticket_id: str) -> bool:
        key = self._process_worker_key(ticket_id)
        with _PROCESS_WORKERS_LOCK:
            worker = _PROCESS_WORKERS.get(key)
            if worker is None:
                return False
            if worker.ident is None or worker.is_alive():
                return True
            _PROCESS_WORKERS.pop(key, None)
            return False

    def _recover_stale_runs(self) -> None:
        """进程启动不冒充旧 worker 仍存活，active 状态一律中断。"""
        snapshot = self.tickets.snapshot()
        for ticket in snapshot.get("tickets", []):
            try:
                runtime = self._raw_runtime(ticket["ticket_id"])
            except AutonomyError:
                continue
            if runtime.get("state") not in ACTIVE_STATES:
                continue
            # 这是同一进程内仍在退出的真实 worker，不是重启残留。让旧 manager
            # 在 safe point/返回处完成中断，不能抢先宣布其已消失。
            try:
                if self._has_live_process_worker(ticket["ticket_id"]):
                    continue
            except AutonomyError:
                continue
            recovered = dict(runtime)
            recovered.update({
                "state": "interrupted",
                "revision": self._revision(runtime) + 1,
                "updated_at": self._now(),
                "finished_at": self._now(),
                "error_code": "process_restarted",
            })
            request_id = self._internal_request(
                ticket["ticket_id"], f"recover-{recovered['revision']}")
            try:
                self.tickets.update_agent_extension(
                    ticket["ticket_id"],
                    {
                        "effective_execution_mode": "interactive",
                        "mode_status": "pending_activation",
                        "autonomous_run": recovered,
                    },
                    request_id=request_id,
                )
            except TicketError:
                # 某一损坏/并发关闭工单不能阻止其余工单安全恢复。
                continue

    def handle_intent(self, ticket_id: str, payload: object) -> dict:
        """验证并应用一个幂等 intent，返回不含可信路径的工单投影。"""
        clean = normalize_intent_payload(payload)
        key = (ticket_id, clean["intent"], clean["request_id"])
        with self._lock:
            prior = self._receipts.get(key)
            if prior is not None:
                return self._ticket(ticket_id)
            if self._shutting_down:
                raise AutonomyError("manager_shutdown", "自主运行管理器正在关闭")

            ticket = self._ticket(ticket_id)
            intent = clean["intent"]
            raw_runtime = self._raw_runtime(ticket_id)
            receipt = self._intent_receipt_token(
                ticket_id, intent, clean["request_id"])
            if receipt in self._intent_receipts(ticket_id, raw_runtime):
                self._receipts[key] = copy.deepcopy(ticket)
                return ticket
            if (
                raw_runtime.get("last_intent") == intent
                and raw_runtime.get("last_intent_request_id") == clean["request_id"]
            ):
                self._receipts[key] = copy.deepcopy(ticket)
                return ticket
            if intent in {"start", "resume"}:
                result = self._start_or_resume_locked(ticket, intent, clean["request_id"])
            elif intent in {"pause", "cancel", "takeover"}:
                result = self._request_stop_locked(ticket, intent, clean["request_id"])
            else:  # pragma: no cover - normalize_intent_payload 已穷尽
                raise AutonomyError("invalid_intent", "不支持的 intent")
            self._receipts[key] = copy.deepcopy(result)
            return result

    def _require_capability(self, ticket: dict) -> None:
        if not self.enabled:
            raise AutonomyError("capability_disabled", "自主执行能力未启用")
        if ticket.get("requested_execution_mode") != "autonomous":
            raise AutonomyError("autonomous_not_requested", "工单未请求自动模式")

    def _persist_intent(self, ticket_id: str, patch: dict, request_id: str) -> dict:
        """把控制面拒绝收敛为不含环境细节的稳定 API 错误。"""
        try:
            return self.tickets.update_agent_extension(
                ticket_id, patch, request_id=request_id)
        except TicketError as exc:
            raise AutonomyError(
                "state_persistence_failed", "自主运行状态未被控制面接受") from exc

    def _release_worker_locked(self, ticket_id: str, control: RunControl) -> None:
        """在终态可见前后使用同一把锁原子释放当前 run 的注册。"""
        if self._controls.get(ticket_id) is control:
            worker = self._workers.get(ticket_id)
            self._controls.pop(ticket_id, None)
            self._workers.pop(ticket_id, None)
            if worker is not None:
                self._release_process_worker(
                    self._process_worker_key(ticket_id), worker)

    def _start_or_resume_locked(self, ticket: dict, intent: str, request_id: str) -> dict:
        self._require_capability(ticket)
        ticket_id = ticket["ticket_id"]
        worker = self._workers.get(ticket_id)
        if worker is not None and worker.is_alive():
            raise AutonomyError("invalid_transition", "该工单已有运行中的 worker")
        runtime = self._raw_runtime(ticket_id)
        state = runtime.get("state")
        if intent == "start":
            allowed = {
                None, "pending", "cancelled", "succeeded", "failed", "blocked", "interrupted",
            }
        else:
            allowed = {"paused", "failed", "blocked", "interrupted"}
        if state not in allowed:
            raise AutonomyError("invalid_transition", f"当前状态不能 {intent}")

        now = self._now()
        run_id = f"run-{uuid.uuid4().hex}"
        starting = {
            "state": "starting",
            "run_id": run_id,
            "revision": self._revision(runtime) + 1,
            "requested_at": now,
            "updated_at": now,
            "last_intent": intent,
            "last_intent_request_id": request_id,
            "intent_receipts": self._append_intent_receipt(
                ticket_id, runtime, intent, request_id),
        }
        control = RunControl(ticket_id, run_id, self)
        thread = threading.Thread(
            target=self._worker_main,
            args=(ticket_id, control),
            name=f"icode-autonomy-{ticket_id}",
            daemon=True,
        )
        worker_key = self._process_worker_key(ticket_id)
        if not self._reserve_process_worker(worker_key, thread):
            raise AutonomyError("invalid_transition", "该工单已有运行中的 worker")
        try:
            public = self._persist_intent(
                ticket_id,
                {
                    "effective_execution_mode": "autonomous",
                    "mode_status": "active",
                    "autonomous_run": starting,
                },
                self._internal_request(ticket_id, f"intent-{intent}-{request_id}"),
            )
        except Exception:
            self._release_process_worker(worker_key, thread)
            raise
        self._controls[ticket_id] = control
        self._workers[ticket_id] = thread
        try:
            thread.start()
        except RuntimeError:
            self._release_worker_locked(ticket_id, control)
            interrupted = dict(starting)
            interrupted.update({
                "state": "interrupted",
                "revision": self._revision(starting) + 1,
                "updated_at": self._now(),
                "finished_at": self._now(),
                "error_code": "worker_start_failed",
            })
            self._persist_intent(
                ticket_id,
                {
                    "effective_execution_mode": "interactive",
                    "mode_status": "pending_activation",
                    "autonomous_run": interrupted,
                },
                self._internal_request(
                    ticket_id,
                    f"run-{control.run_id}-{interrupted['revision']}-start-failed",
                ),
            )
            raise AutonomyError("worker_start_failed", "自主 worker 启动失败") from None
        return public

    def _request_stop_locked(self, ticket: dict, intent: str, request_id: str) -> dict:
        ticket_id = ticket["ticket_id"]
        runtime = self._raw_runtime(ticket_id)
        state = runtime.get("state")
        control = self._controls.get(ticket_id)
        worker = self._workers.get(ticket_id)
        if (
            control is None
            or worker is None
            or not worker.is_alive()
            or state not in {"starting", "running", "pause_requested"}
        ):
            raise AutonomyError("invalid_transition", "该工单没有可停止的 worker")
        if state == "pause_requested" and intent == "pause":
            raise AutonomyError("invalid_transition", "暂停已在等待 safe point")

        requested_state = "cancel_requested" if intent == "cancel" else "pause_requested"
        requested = dict(runtime)
        requested.update({
            "state": requested_state,
            "revision": self._revision(runtime) + 1,
            "updated_at": self._now(),
            "last_intent": intent,
            "last_intent_request_id": request_id,
            "intent_receipts": self._append_intent_receipt(
                ticket_id, runtime, intent, request_id),
        })
        public = self._persist_intent(
            ticket_id,
            {"autonomous_run": requested},
            self._internal_request(ticket_id, f"intent-{intent}-{request_id}"),
        )
        # 只有控制面已接受请求，executor 才能在下一个 safe point 应用它。
        control._stop_intent = intent
        return public

    def _worker_main(self, ticket_id: str, control: RunControl) -> None:
        try:
            with self._lock:
                runtime = self._raw_runtime(ticket_id)
                if self._shutting_down or runtime.get("run_id") != control.run_id:
                    return
                if runtime.get("state") == "starting":
                    running = dict(runtime)
                    running.update({
                        "state": "running",
                        "revision": self._revision(runtime) + 1,
                        "started_at": self._now(),
                        "updated_at": self._now(),
                    })
                    self.tickets.update_agent_extension(
                        ticket_id,
                        {"autonomous_run": running},
                        request_id=self._internal_request(
                            ticket_id, f"run-{control.run_id}-{running['revision']}-running"),
                    )
            context = self._execution_context(ticket_id)
            executor = self.executor
            if executor is None:  # 构造时已 fail-closed；防止未来热替换竞态。
                raise RuntimeError("executor unavailable")
            result = executor.execute(context, control)
            with self._lock:
                if self._shutting_down or self._controls.get(ticket_id) is not control:
                    return
                runtime = self._raw_runtime(ticket_id)
                if runtime.get("run_id") != control.run_id:
                    return
                terminal = dict(runtime)
                terminal.update({
                    "state": result.state,
                    "revision": self._revision(runtime) + 1,
                    "updated_at": self._now(),
                    "finished_at": self._now(),
                })
                if result.last_step is not None:
                    terminal["last_step"] = result.last_step
                error_code = result.error_code
                if error_code is None and result.state == "failed":
                    error_code = "executor_failed"
                if error_code is None and result.state == "blocked":
                    error_code = "execution_blocked"
                if error_code is not None:
                    terminal["error_code"] = error_code
                else:
                    terminal.pop("error_code", None)
                self.tickets.update_agent_extension(
                    ticket_id,
                    {"autonomous_run": terminal},
                    request_id=self._internal_request(
                        ticket_id, f"run-{control.run_id}-{terminal['revision']}-{result.state}"),
                )
                self._release_worker_locked(ticket_id, control)
        except _RunStopped:
            pass
        except Exception:
            self._record_executor_failure(ticket_id, control)
        finally:
            with self._lock:
                self._release_worker_locked(ticket_id, control)

    def _record_executor_failure(self, ticket_id: str, control: RunControl) -> None:
        """异常正文绝不进入 metadata，仅记录稳定错误码。"""
        with self._lock:
            if self._shutting_down or self._controls.get(ticket_id) is not control:
                return
            try:
                runtime = self._raw_runtime(ticket_id)
                if runtime.get("run_id") != control.run_id:
                    return
                failed = dict(runtime)
                failed.update({
                    "state": "failed",
                    "revision": self._revision(runtime) + 1,
                    "updated_at": self._now(),
                    "finished_at": self._now(),
                    "error_code": "executor_error",
                })
                self.tickets.update_agent_extension(
                    ticket_id,
                    {"autonomous_run": failed},
                    request_id=self._internal_request(
                        ticket_id, f"run-{control.run_id}-{failed['revision']}-failed"),
                )
                self._release_worker_locked(ticket_id, control)
            except (AutonomyError, TicketError):
                return

    def _safe_point(self, control: RunControl, step: str) -> None:
        with self._lock:
            if self._controls.get(control.ticket_id) is not control:
                raise _RunStopped()
            runtime = self._raw_runtime(control.ticket_id)
            if runtime.get("run_id") != control.run_id:
                raise _RunStopped()
            stop_intent = "interrupted" if self._shutting_down else control._stop_intent
            next_runtime = dict(runtime)
            next_runtime.update({
                "revision": self._revision(runtime) + 1,
                "updated_at": self._now(),
                "last_step": step,
            })
            patch: dict = {"autonomous_run": next_runtime}
            if stop_intent is None:
                next_runtime["state"] = "running"
            else:
                if stop_intent == "cancel":
                    next_runtime["state"] = "cancelled"
                    patch["effective_execution_mode"] = "interactive"
                elif stop_intent in {"pause", "takeover"}:
                    next_runtime["state"] = "paused"
                    if stop_intent == "takeover":
                        patch["effective_execution_mode"] = "interactive"
                else:
                    next_runtime["state"] = "interrupted"
                    next_runtime["error_code"] = "shutdown"
                    patch["effective_execution_mode"] = "interactive"
                next_runtime["finished_at"] = self._now()
                if patch.get("effective_execution_mode") == "interactive":
                    patch["mode_status"] = "pending_activation"
            self.tickets.update_agent_extension(
                control.ticket_id,
                patch,
                request_id=self._internal_request(
                    control.ticket_id,
                    f"run-{control.run_id}-{next_runtime['revision']}-safe-point"),
            )
            if stop_intent is not None:
                self._release_worker_locked(control.ticket_id, control)
                raise _RunStopped()

    def shutdown(self, *, timeout: float = 2.0) -> None:
        """请求中断并限时 join；控制面失效时不伪造已落盘的中断态。"""
        timeout = max(0.0, float(timeout))
        workers: list[threading.Thread] = []
        try:
            with self._lock:
                if self._shutting_down:
                    workers = list(self._workers.values())
                else:
                    self._shutting_down = True
                    workers = list(self._workers.values())
                    for ticket_id, control in list(self._controls.items()):
                        # 内存停止意图不依赖持久化成功；旧 worker 到达 safe point
                        # 后仍会停止。某个工单写失败也不能阻断其余 worker 的关服。
                        control._stop_intent = "interrupted"
                        try:
                            runtime = self._raw_runtime(ticket_id)
                            if runtime.get("state") not in ACTIVE_STATES:
                                continue
                            interrupted = dict(runtime)
                            interrupted.update({
                                "state": "interrupted",
                                "revision": self._revision(runtime) + 1,
                                "updated_at": self._now(),
                                "finished_at": self._now(),
                                "error_code": "shutdown",
                            })
                            self.tickets.update_agent_extension(
                                ticket_id,
                                {
                                    "effective_execution_mode": "interactive",
                                    "mode_status": "pending_activation",
                                    "autonomous_run": interrupted,
                                },
                                request_id=self._internal_request(
                                    ticket_id,
                                    f"run-{control.run_id}-{interrupted['revision']}-shutdown"),
                            )
                        except Exception:  # noqa: BLE001 - 关服必须继续处理其余 worker。
                            continue
        finally:
            deadline = time.monotonic() + timeout
            for worker in workers:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                worker.join(remaining)


__all__ = [
    "ACTIVE_STATES",
    "AutonomyError",
    "AutonomyManager",
    "ExecutionContext",
    "ExecutionResult",
    "Executor",
    "INTENTS",
    "NativeChainExecutor",
    "RunControl",
    "normalize_intent_payload",
]
