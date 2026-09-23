"""自主运行意图、状态机与线程生命周期测试。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from icode.autonomy import (
    ACTIVE_STATES,
    AutonomyError,
    AutonomyManager,
    ExecutionContext,
    ExecutionResult,
    NativeChainExecutor,
    normalize_intent_payload,
)
from icode.backends import FakeBackend
from icode.chain import ChainReport, run_chain
from icode.runner import StepReport
from icode.tickets import TicketError, TicketService
from icode.workspace import (
    WorkspaceBusyError,
    WorkspaceError,
    WorkspaceManager,
)
from tests._support import require_skill, temp_workspace

ASYNC_TEST_TIMEOUT_SECONDS = 10.0


def _payload(project_id: str, request_id: str, *, mode: str = "autonomous") -> dict:
    return {
        "project_id": project_id,
        "title": "Autonomous runner",
        "description": "Run the existing ticket without browser authority.",
        "expected_result": "Persist an honest terminal state.",
        "priority": "normal",
        "locale": "en-US",
        "execution_mode": mode,
        "request_id": request_id,
    }


def _wait_state(
    service: TicketService,
    ticket_id: str,
    state: str,
    timeout: float = ASYNC_TEST_TIMEOUT_SECONDS,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ticket = service.ticket_detail(ticket_id)
        if ticket.get("autonomous_run", {}).get("state") == state:
            return ticket
        time.sleep(0.01)
    current = service.ticket_detail(ticket_id)
    raise AssertionError(f"expected {state}, got {current.get('autonomous_run')}")


def _wait_worker_release(
    manager: AutonomyManager,
    ticket_id: str,
    timeout: float = ASYNC_TEST_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout
    while ticket_id in manager._workers and time.monotonic() < deadline:
        time.sleep(0.01)
    if ticket_id in manager._workers:
        raise AssertionError(f"worker registry was not released for {ticket_id}")


def _acquire_lease_in_child(
    data_root: Path,
    project_id: str,
    ticket_id: str,
) -> str:
    source_root = Path(__file__).resolve().parents[1] / "src"
    environment = os.environ.copy()
    existing_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(source_root), existing_path) if part
    )
    program = "\n".join(
        (
            "from pathlib import Path",
            "import sys",
            "from icode.workspace import TicketLease, WorkspaceBusyError",
            "try:",
            '    lease = TicketLease.acquire(Path(sys.argv[1]), sys.argv[2], sys.argv[3], "child-run")',
            "except WorkspaceBusyError:",
            '    print("busy")',
            "else:",
            '    print("acquired")',
            "    lease.release()",
        )
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(data_root),
            project_id,
            ticket_id,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=10,
    )
    return completed.stdout.strip()


class BlockingExecutor:
    """由测试决定何时到达真实 safe point。"""

    def __init__(self, *, block_after_safe_point: bool = False) -> None:
        self.started = threading.Event()
        self.allow_safe_point = threading.Event()
        self.release = threading.Event()
        self.block_after_safe_point = block_after_safe_point
        self.calls = 0
        self.contexts = []

    def execute(self, context, control) -> ExecutionResult:
        self.calls += 1
        self.contexts.append(context)
        self.started.set()
        if not self.allow_safe_point.wait(3):
            raise RuntimeError("test safe-point timeout")
        control.safe_point("plan")
        if self.block_after_safe_point and not self.release.wait(3):
            raise RuntimeError("test release timeout")
        return ExecutionResult(state="succeeded", last_step="plan")


class ResumeExecutor:
    def __init__(self) -> None:
        self.first_started = threading.Event()
        self.first_safe_point = threading.Event()
        self.calls = 0

    def execute(self, context, control) -> ExecutionResult:
        self.calls += 1
        if self.calls == 1:
            self.first_started.set()
            if not self.first_safe_point.wait(3):
                raise RuntimeError("test resume timeout")
            control.safe_point("plan")
            raise AssertionError("paused safe point must stop the first run")
        control.safe_point("code")
        return ExecutionResult(state="succeeded", last_step="code")


class RaisingExecutor:
    def execute(self, context, control) -> ExecutionResult:
        raise RuntimeError(f"secret exception at {context.out_dir}")


class NeverSafePointExecutor:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(self, context, control) -> ExecutionResult:
        self.started.set()
        self.release.wait()
        return ExecutionResult(state="succeeded")


class BlockingLastStepRunner:
    """让停止意图确定性地落在最后一个 chain step 执行期间。"""

    def __init__(self, report: ChainReport) -> None:
        self.report = report
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def __call__(self, *args, **kwargs) -> ChainReport:
        self.calls += 1
        if kwargs.get("steps") != ("audit",):
            raise AssertionError("test must execute only the final audit step")
        self.started.set()
        if not self.release.wait(3):
            raise RuntimeError("test final-step timeout")
        return self.report


class ShutdownSafePointExecutor:
    """关服信号到达后才触达下一契约步骤边界。"""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.allow_safe_point = threading.Event()
        self.stopped = threading.Event()

    def execute(self, context, control) -> ExecutionResult:
        self.started.set()
        if not self.allow_safe_point.wait(3):
            raise RuntimeError("test shutdown safe-point timeout")
        try:
            control.safe_point("code")
        finally:
            self.stopped.set()
        raise AssertionError("shutdown safe point must stop the worker")


class FailOnceTicketService(TicketService):
    """只在明确武装后模拟一次控制面持久化失败。"""

    fail_next_update = False

    def update_agent_extension(self, ticket_id, patch, *, request_id):
        if self.fail_next_update:
            self.fail_next_update = False
            raise TicketError("simulated control-plane rejection")
        return super().update_agent_extension(
            ticket_id, patch, request_id=request_id)


class FailOneShutdownTicketService(TicketService):
    """关服阶段只让指定工单的控制面写入抛出非 TicketError。"""

    fail_ticket_id: str | None = None
    shutdown_update_calls: list[str]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.shutdown_update_calls = []

    def update_agent_extension(self, ticket_id, patch, *, request_id):
        if self.fail_ticket_id is not None and "-shutdown-" in request_id:
            self.shutdown_update_calls.append(ticket_id)
            if ticket_id == self.fail_ticket_id:
                raise RuntimeError("simulated shutdown persistence outage")
        return super().update_agent_extension(
            ticket_id, patch, request_id=request_id)


class MultiNeverSafePointExecutor:
    """并行启动多个 worker，直到测试统一放行。"""

    def __init__(self, expected: int) -> None:
        self.expected = expected
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self.calls = 0

    def execute(self, context, control) -> ExecutionResult:
        with self._lock:
            self.calls += 1
            if self.calls == self.expected:
                self.started.set()
        self.release.wait(3)
        return ExecutionResult(state="succeeded")


class RecordingControl:
    def __init__(self) -> None:
        self.steps: list[str] = []

    def safe_point(self, step: str) -> None:
        self.steps.append(step)


class RecordingWorkspaceSession:
    def __init__(self, workspace_root: Path, *, fail_close: bool = False) -> None:
        self.workspace_root = workspace_root
        self.fail_close = fail_close
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise WorkspaceError("private close failure")


class RecordingWorkspaceManager:
    def __init__(
        self,
        workspace_root: Path,
        *,
        open_error: WorkspaceError | None = None,
        fail_close: bool = False,
    ) -> None:
        self.workspace_root = workspace_root
        self.open_error = open_error
        self.fail_close = fail_close
        self.open_calls: list[tuple[str, str]] = []
        self.sessions: list[RecordingWorkspaceSession] = []

    def open(self, ticket_id: str, run_id: str) -> RecordingWorkspaceSession:
        self.open_calls.append((ticket_id, run_id))
        if self.open_error is not None:
            raise self.open_error
        session = RecordingWorkspaceSession(
            self.workspace_root,
            fail_close=self.fail_close,
        )
        self.sessions.append(session)
        return session


class TestNativeChainExecutor(unittest.TestCase):
    def test_从当前控制面状态续跑且每步先safe_point(self) -> None:
        settings = require_skill()
        calls: list[dict] = []

        def step_runner(*args, **kwargs):
            calls.append(kwargs)
            return ChainReport(
                delivered=True,
                out_dir=str(kwargs["out_dir"]),
                ticket_id=kwargs["ticket_id"],
            )

        executor = NativeChainExecutor(
            settings,
            backend=FakeBackend(["完成"]),
            step_runner=step_runner,
        )
        context = ExecutionContext(
            ticket_id="AUTO-RESUME-1",
            out_dir=Path("/tmp/ignored-ticket"),
            workspace=Path("/tmp/ignored-workspace"),
            requirement="resume from current status",
            status="init_in_progress",
            completed_steps=(),
        )
        control = RecordingControl()

        with patch(
            "icode.autonomy.ControlPlane.trace",
            return_value=SimpleNamespace(
                returncode=0,
                data={
                    "ok": True,
                    "ticket_id": context.ticket_id,
                    "status": "plan_done",
                },
            ),
        ):
            result = executor.execute(context, control)

        expected = ["review", "merge", "code", "deepcheck", "audit"]
        self.assertEqual(result, ExecutionResult(state="succeeded", last_step="audit"))
        self.assertEqual(
            control.steps,
            [boundary for step in expected for boundary in (step, step)],
        )
        self.assertEqual([call["steps"] for call in calls], [(step,) for step in expected])
        self.assertTrue(all(call["out_dir"] == context.out_dir.resolve() for call in calls))

    def test_completed工单没有待执行步骤(self) -> None:
        settings = require_skill()

        def unexpected_runner(*args, **kwargs):
            raise AssertionError("completed ticket must not reopen review automatically")

        executor = NativeChainExecutor(
            settings,
            backend=FakeBackend(["完成"]),
            step_runner=unexpected_runner,
        )
        context = ExecutionContext(
            ticket_id="AUTO-COMPLETED-1",
            out_dir=Path("/tmp/completed-ticket"),
            workspace=Path("/tmp/completed-workspace"),
            requirement="already completed",
            status="init_in_progress",
            completed_steps=(),
        )
        control = RecordingControl()

        with patch(
            "icode.autonomy.ControlPlane.trace",
            return_value=SimpleNamespace(
                returncode=0,
                data={
                    "ok": True,
                    "ticket_id": context.ticket_id,
                    "status": "completed",
                },
            ),
        ):
            result = executor.execute(context, control)

        self.assertEqual(result, ExecutionResult(state="succeeded"))
        self.assertEqual(control.steps, [])

    def test_runner明确失败映射为failed稳定码(self) -> None:
        settings = require_skill()

        def failed_runner(*args, **kwargs):
            return ChainReport(
                delivered=False,
                out_dir=str(kwargs["out_dir"]),
                ticket_id=kwargs["ticket_id"],
            )

        executor = NativeChainExecutor(
            settings,
            backend=FakeBackend(["完成"]),
            step_runner=failed_runner,
        )
        context = ExecutionContext(
            ticket_id="AUTO-FAILED-1",
            out_dir=Path("/tmp/failed-ticket"),
            workspace=Path("/tmp/failed-workspace"),
            requirement="deterministic failure",
            status="stale",
            completed_steps=(),
        )

        with patch(
            "icode.autonomy.ControlPlane.trace",
            return_value=SimpleNamespace(
                returncode=0,
                data={
                    "ok": True,
                    "ticket_id": context.ticket_id,
                    "status": "init_in_progress",
                },
            ),
        ):
            result = executor.execute(context, RecordingControl())

        self.assertEqual(
            result,
            ExecutionResult(
                state="failed",
                last_step="plan",
                error_code="chain_failed",
            ),
        )

    def test_控制面状态读取异常映射为稳定failed(self) -> None:
        settings = require_skill()
        executor = NativeChainExecutor(
            settings,
            backend=FakeBackend(["完成"]),
            step_runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("runner must not start")
            ),
        )
        context = ExecutionContext(
            ticket_id="AUTO-STATUS-FAIL-1",
            out_dir=Path("/tmp/private-ticket-path"),
            workspace=Path("/tmp/private-workspace-path"),
            requirement="status read failure",
            status="init_in_progress",
            completed_steps=(),
        )

        with patch(
            "icode.autonomy.ControlPlane.trace",
            side_effect=RuntimeError("secret failure at /tmp/private-ticket-path"),
        ):
            result = executor.execute(context, RecordingControl())

        self.assertEqual(
            result,
            ExecutionResult(state="failed", error_code="status_unavailable"),
        )
        self.assertNotIn("private-ticket-path", repr(result))

    def test_未知控制面状态不能误报成功(self) -> None:
        settings = require_skill()
        executor = NativeChainExecutor(
            settings,
            backend=FakeBackend(["完成"]),
            step_runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("runner must not start")
            ),
        )
        context = ExecutionContext(
            ticket_id="AUTO-UNKNOWN-STATUS-1",
            out_dir=Path("/tmp/unknown-status-ticket"),
            workspace=Path("/tmp/unknown-status-workspace"),
            requirement="unknown status",
            status="init_in_progress",
            completed_steps=(),
        )

        with patch(
            "icode.autonomy.ControlPlane.trace",
            return_value=SimpleNamespace(
                returncode=0,
                data={
                    "ok": True,
                    "ticket_id": context.ticket_id,
                    "status": "future_unknown_status",
                },
            ),
        ):
            result = executor.execute(context, RecordingControl())

        self.assertEqual(
            result,
            ExecutionResult(state="failed", error_code="invalid_status"),
        )

    def test_控制面工单身份不匹配时fail_closed(self) -> None:
        settings = require_skill()
        executor = NativeChainExecutor(
            settings,
            backend=FakeBackend(["完成"]),
            step_runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("runner must not start")
            ),
        )
        context = ExecutionContext(
            ticket_id="EXPECTED-TICKET",
            out_dir=Path("/tmp/mismatched-ticket"),
            workspace=Path("/tmp/mismatched-workspace"),
            requirement="mismatched identity",
            status="init_in_progress",
            completed_steps=(),
        )

        with patch(
            "icode.autonomy.ControlPlane.trace",
            return_value=SimpleNamespace(
                returncode=0,
                data={
                    "ok": True,
                    "ticket_id": "ACTUAL-TICKET",
                    "status": "completed",
                },
            ),
        ):
            result = executor.execute(context, RecordingControl())

        self.assertEqual(
            result,
            ExecutionResult(state="failed", error_code="invalid_ticket"),
        )

    def test_gate与step停止分别映射稳定blocked码(self) -> None:
        settings = require_skill()
        cases = (
            (
                ChainReport(
                    steps=[StepReport(
                        step="plan",
                        ok=True,
                        out_dir="/tmp/ticket",
                        advance_gates=["reasoning_gate"],
                    )],
                    stopped_at="plan",
                    reason="private gate detail at /tmp/ticket",
                ),
                "gate_blocked",
            ),
            (
                ChainReport(
                    steps=[StepReport(step="plan", ok=False, out_dir="/tmp/ticket")],
                    stopped_at="plan",
                    reason="private step failure at /tmp/ticket",
                ),
                "step_blocked",
            ),
        )
        context = ExecutionContext(
            ticket_id="AUTO-BLOCKED-1",
            out_dir=Path("/tmp/ticket"),
            workspace=Path("/tmp/workspace"),
            requirement="blocked mapping",
            status="stale",
            completed_steps=(),
        )

        for report, code in cases:
            with self.subTest(code=code), patch(
                "icode.autonomy.ControlPlane.trace",
                return_value=SimpleNamespace(
                    returncode=0,
                    data={
                        "ok": True,
                        "ticket_id": context.ticket_id,
                        "status": "init_in_progress",
                    },
                ),
            ):
                executor = NativeChainExecutor(
                    settings,
                    backend=FakeBackend(["完成"]),
                    step_runner=lambda *args, **kwargs: report,
                )
                result = executor.execute(context, RecordingControl())

            self.assertEqual(
                result,
                ExecutionResult(
                    state="blocked",
                    last_step="plan",
                    error_code=code,
                ),
            )
            self.assertNotIn("private", repr(result))
            self.assertNotIn("/tmp", repr(result))

    def test_真实控制面工单由native_executor原地续跑(self) -> None:
        settings = require_skill()
        with temp_workspace() as workspace:
            service = TicketService(
                settings,
                workspace=workspace,
                index_path=workspace / "index.json",
            )
            ticket_id = service.create_ticket(
                _payload(service.project_id, "native-integration-ticket")
            )["ticket"]["ticket_id"]
            record = service._resolve_ticket_record(ticket_id)
            before = sorted((workspace / ".icode_output").iterdir())
            plan_path = record.out_dir / "01_plan.md"
            backend = FakeBackend([
                {"content": "", "tool_calls": [{
                    "id": "write-plan",
                    "name": "write_file",
                    "arguments": {
                        "path": str(plan_path),
                        "content": "# Native plan\n\nContinue the existing ticket.\n",
                    },
                }]},
                "完成",
                '{"step":"check requirement","next_thought_needed":true}',
                '{"step":"check boundary","next_thought_needed":true}',
                '{"step":"confirm evidence","next_thought_needed":false}',
            ])
            native_calls = 0

            def real_first_step(*args, **kwargs):
                nonlocal native_calls
                native_calls += 1
                if native_calls == 1:
                    return run_chain(*args, **kwargs)
                step = kwargs["steps"][0]
                return ChainReport(
                    stopped_at=step,
                    reason="bounded integration stop",
                    out_dir=str(kwargs["out_dir"]),
                    ticket_id=kwargs["ticket_id"],
                )

            executor = NativeChainExecutor(
                settings,
                backend=backend,
                step_runner=real_first_step,
            )
            context = ExecutionContext(
                ticket_id=ticket_id,
                out_dir=record.out_dir,
                workspace=workspace,
                requirement=str(record.metadata.get("requirement") or ""),
                status="completed",  # 故意陈旧；executor 必须以真实 trace 为准。
                completed_steps=(),
            )
            control = RecordingControl()

            result = executor.execute(context, control)

            self.assertEqual(result.state, "blocked")
            self.assertGreaterEqual(native_calls, 1)
            self.assertEqual(control.steps[0], "plan")
            self.assertEqual(sorted((workspace / ".icode_output").iterdir()), before)
            self.assertTrue(plan_path.is_file())
            self.assertEqual(
                json.loads((record.out_dir / ".ico_metadata.json").read_text(
                    encoding="utf-8"
                ))["ticket_id"],
                ticket_id,
            )


class TestIntentPayload(unittest.TestCase):
    def test_只接受稳定动作与request_id(self) -> None:
        for intent in ("start", "pause", "resume", "cancel", "takeover"):
            self.assertEqual(
                normalize_intent_payload({"intent": intent, "request_id": f"ui-{intent}"}),
                {"intent": intent, "request_id": f"ui-{intent}"},
            )

    def test_拒绝未知字段缺失字段与非法枚举(self) -> None:
        for payload in (
            {"intent": "start", "request_id": "ui-1", "path": "/tmp/private"},
            {"intent": "start"},
            {"intent": "force", "request_id": "ui-2"},
            {"intent": "pause", "request_id": "bad request id"},
        ):
            with self.subTest(payload=payload), self.assertRaises(AutonomyError) as caught:
                normalize_intent_payload(payload)
            self.assertEqual(caught.exception.code, "invalid_intent")

    def test_ExecutionResult拒绝路径形态的last_step(self) -> None:
        with self.assertRaises(ValueError):
            ExecutionResult(state="succeeded", last_step="/tmp/private-step")


class TestAutonomyManager(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = require_skill()
        self.workspace_ctx = temp_workspace()
        self.workspace = self.workspace_ctx.__enter__()
        self.service = TicketService(
            self.settings,
            workspace=self.workspace,
            index_path=self.workspace / "index.json",
        )
        self.managers: list[AutonomyManager] = []

    def tearDown(self) -> None:
        for manager in reversed(self.managers):
            manager.shutdown(timeout=0.2)
        self.workspace_ctx.__exit__(None, None, None)

    def _ticket(self, request_id: str, *, mode: str = "autonomous") -> str:
        created = self.service.create_ticket(
            _payload(self.service.project_id, request_id, mode=mode))
        return created["ticket"]["ticket_id"]

    def _manager(
        self,
        executor=None,
        *,
        enabled: bool = True,
        workspace_manager=None,
    ) -> AutonomyManager:
        manager = AutonomyManager(
            self.service,
            executor=executor,
            enabled=enabled,
            workspace_manager=workspace_manager,
        )
        self.managers.append(manager)
        return manager

    def test_无workspace_manager保持原工作区兼容(self) -> None:
        ticket_id = self._ticket("legacy-workspace-ticket")
        executor = BlockingExecutor()
        executor.allow_safe_point.set()
        manager = self._manager(executor)

        manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": "legacy-workspace-start"}
        )
        _wait_state(self.service, ticket_id, "succeeded")

        self.assertEqual(executor.contexts[0].workspace, self.workspace)

    def test_executor使用隔离checkout且不修改source(self) -> None:
        ticket_id = self._ticket("isolated-checkout-ticket")
        source_file = self.workspace / "source.txt"
        source_file.write_text("source\n", encoding="utf-8")
        with tempfile.TemporaryDirectory(
            prefix="icode_autonomy_data_"
        ) as raw_data_root:
            workspace_manager = WorkspaceManager(
                self.workspace,
                Path(raw_data_root),
                self.service.project_id,
            )

            class EditingExecutor:
                def __init__(self) -> None:
                    self.workspace: Path | None = None

                def execute(inner_self, context, control) -> ExecutionResult:
                    inner_self.workspace = context.workspace
                    context.workspace.joinpath("source.txt").write_text(
                        "isolated\n", encoding="utf-8"
                    )
                    return ExecutionResult(state="succeeded")

            executor = EditingExecutor()
            manager = self._manager(executor, workspace_manager=workspace_manager)
            manager.handle_intent(
                ticket_id,
                {"intent": "start", "request_id": "isolated-checkout-start"},
            )
            _wait_state(self.service, ticket_id, "succeeded")
            _wait_worker_release(manager, ticket_id)

            self.assertIsNotNone(executor.workspace)
            self.assertNotEqual(executor.workspace, self.workspace)
            self.assertEqual(source_file.read_text(encoding="utf-8"), "source\n")
            with workspace_manager.open(ticket_id, "reacquired-run"):
                pass

    def test_workspace_busy在持久化和worker前稳定拒绝(self) -> None:
        ticket_id = self._ticket("workspace-busy-ticket")
        executor = BlockingExecutor()
        workspace_manager = RecordingWorkspaceManager(
            self.workspace / "isolated",
            open_error=WorkspaceBusyError(f"private busy path: {self.workspace}"),
        )
        manager = self._manager(executor, workspace_manager=workspace_manager)

        with self.assertRaises(AutonomyError) as caught:
            manager.handle_intent(
                ticket_id, {"intent": "start", "request_id": "workspace-busy-start"}
            )

        self.assertEqual(caught.exception.code, "workspace_busy")
        self.assertEqual(str(caught.exception), "该工单正在另一个进程中运行")
        self.assertEqual(executor.calls, 0)
        self.assertEqual(manager._workers, {})
        self.assertEqual(
            self.service.ticket_detail(ticket_id)["autonomous_run"],
            {"state": "pending", "revision": 0},
        )

    def test_workspace_setup失败稳定且零worker(self) -> None:
        ticket_id = self._ticket("workspace-setup-failure-ticket")
        executor = BlockingExecutor()
        workspace_manager = RecordingWorkspaceManager(
            self.workspace / "isolated",
            open_error=WorkspaceError(f"private setup path: {self.workspace}"),
        )
        manager = self._manager(executor, workspace_manager=workspace_manager)

        with self.assertRaises(AutonomyError) as caught:
            manager.handle_intent(
                ticket_id, {"intent": "start", "request_id": "workspace-setup-start"}
            )

        self.assertEqual(caught.exception.code, "workspace_setup_failed")
        self.assertEqual(str(caught.exception), "无法准备隔离工作区")
        self.assertEqual(executor.calls, 0)
        self.assertEqual(manager._workers, {})

    def test_starting持久化失败释放workspace_session(self) -> None:
        service = FailOnceTicketService(
            self.settings,
            workspace=self.workspace,
            index_path=self.workspace / "persist-start-index.json",
        )
        ticket_id = service.create_ticket(
            _payload(service.project_id, "persist-start-ticket")
        )["ticket"]["ticket_id"]
        executor = BlockingExecutor()
        workspace_manager = RecordingWorkspaceManager(self.workspace / "isolated")
        manager = AutonomyManager(
            service,
            executor=executor,
            enabled=True,
            workspace_manager=workspace_manager,
        )
        self.managers.append(manager)
        service.fail_next_update = True

        with self.assertRaises(AutonomyError) as caught:
            manager.handle_intent(
                ticket_id, {"intent": "start", "request_id": "persist-start"}
            )

        self.assertEqual(caught.exception.code, "state_persistence_failed")
        self.assertEqual(workspace_manager.sessions[0].close_calls, 1)
        self.assertEqual(manager._workers, {})
        self.assertEqual(executor.calls, 0)

    def test_thread_start失败释放workspace_session(self) -> None:
        ticket_id = self._ticket("workspace-thread-start-failure-ticket")
        workspace_manager = RecordingWorkspaceManager(self.workspace / "isolated")
        manager = self._manager(BlockingExecutor(), workspace_manager=workspace_manager)

        with (
            patch(
                "icode.autonomy.threading.Thread.start",
                side_effect=RuntimeError("private thread failure"),
            ),
            self.assertRaises(AutonomyError) as caught,
        ):
            manager.handle_intent(
                ticket_id, {"intent": "start", "request_id": "workspace-thread-start"}
            )

        self.assertEqual(caught.exception.code, "worker_start_failed")
        self.assertEqual(workspace_manager.sessions[0].close_calls, 1)

    def test_executor异常仍释放workspace_session且close异常不阻止registry释放(
        self,
    ) -> None:
        ticket_id = self._ticket("workspace-executor-failure-ticket")
        workspace_manager = RecordingWorkspaceManager(
            self.workspace / "isolated", fail_close=True
        )
        manager = self._manager(RaisingExecutor(), workspace_manager=workspace_manager)

        manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": "workspace-executor-failure"}
        )
        _wait_state(self.service, ticket_id, "failed")

        deadline = time.monotonic() + ASYNC_TEST_TIMEOUT_SECONDS
        while manager._workers and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(workspace_manager.sessions[0].close_calls, 1)
        self.assertEqual(manager._workers, {})
        self.assertEqual(manager._controls, {})

    def test_executor正常终态succeeded_failed_blocked均释放workspace_session(
        self,
    ) -> None:
        for index, state in enumerate(("succeeded", "failed", "blocked")):
            with self.subTest(state=state):
                ticket_id = self._ticket(f"workspace-{state}-terminal-{index}")
                workspace_manager = RecordingWorkspaceManager(
                    self.workspace / "isolated"
                )

                class TerminalExecutor:
                    def __init__(self, terminal_state: str) -> None:
                        self.terminal_state = terminal_state

                    def execute(inner_self, context, control) -> ExecutionResult:
                        error_code = (
                            None
                            if inner_self.terminal_state == "succeeded"
                            else f"stable_{inner_self.terminal_state}"
                        )
                        return ExecutionResult(
                            state=inner_self.terminal_state,
                            error_code=error_code,
                        )

                manager = self._manager(
                    TerminalExecutor(state), workspace_manager=workspace_manager
                )
                manager.handle_intent(
                    ticket_id,
                    {"intent": "start", "request_id": f"workspace-{state}-start"},
                )
                _wait_state(self.service, ticket_id, state)
                _wait_worker_release(manager, ticket_id)

                self.assertEqual(workspace_manager.sessions[0].close_calls, 1)

    def test_pause_cancel_takeover和shutdown完成后释放workspace_session(self) -> None:
        cases = (
            ("pause", "paused"),
            ("cancel", "cancelled"),
            ("takeover", "paused"),
        )
        for index, (intent, terminal) in enumerate(cases):
            with self.subTest(intent=intent):
                ticket_id = self._ticket(f"workspace-{intent}-ticket-{index}")
                executor = BlockingExecutor()
                workspace_manager = RecordingWorkspaceManager(
                    self.workspace / "isolated"
                )
                manager = self._manager(executor, workspace_manager=workspace_manager)
                manager.handle_intent(
                    ticket_id,
                    {"intent": "start", "request_id": f"workspace-{intent}-start"},
                )
                self.assertTrue(executor.started.wait(ASYNC_TEST_TIMEOUT_SECONDS))
                manager.handle_intent(
                    ticket_id,
                    {"intent": intent, "request_id": f"workspace-{intent}-stop"},
                )
                executor.allow_safe_point.set()
                _wait_state(self.service, ticket_id, terminal)
                _wait_worker_release(manager, ticket_id)
                self.assertEqual(workspace_manager.sessions[0].close_calls, 1)

        ticket_id = self._ticket("workspace-shutdown-ticket")
        executor = ShutdownSafePointExecutor()
        workspace_manager = RecordingWorkspaceManager(self.workspace / "isolated")
        manager = self._manager(executor, workspace_manager=workspace_manager)
        manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": "workspace-shutdown-start"}
        )
        self.assertTrue(executor.started.wait(ASYNC_TEST_TIMEOUT_SECONDS))
        shutdown_thread = threading.Thread(
            target=manager.shutdown,
            kwargs={"timeout": 2},
        )
        shutdown_thread.start()
        _wait_state(self.service, ticket_id, "interrupted")
        executor.allow_safe_point.set()
        shutdown_thread.join(ASYNC_TEST_TIMEOUT_SECONDS)
        self.assertFalse(shutdown_thread.is_alive())
        self.assertTrue(executor.stopped.wait(ASYNC_TEST_TIMEOUT_SECONDS))
        self.assertEqual(workspace_manager.sessions[0].close_calls, 1)

    def test_shutdown超时不提前释放真实ticket_lease(self) -> None:
        ticket_id = self._ticket("workspace-shutdown-timeout-ticket")
        executor = NeverSafePointExecutor()
        with tempfile.TemporaryDirectory(
            prefix="icode_shutdown_data_"
        ) as raw_data_root:
            data_root = Path(raw_data_root)
            workspace_manager = WorkspaceManager(
                self.workspace,
                data_root,
                self.service.project_id,
            )
            manager = self._manager(executor, workspace_manager=workspace_manager)
            manager.handle_intent(
                ticket_id,
                {"intent": "start", "request_id": "workspace-shutdown-timeout-start"},
            )
            self.assertTrue(executor.started.wait(ASYNC_TEST_TIMEOUT_SECONDS))
            second_workspace_manager = WorkspaceManager(
                self.workspace,
                data_root,
                self.service.project_id,
            )
            try:
                manager.shutdown(timeout=0.01)
                self.assertEqual(
                    _acquire_lease_in_child(
                        data_root,
                        self.service.project_id,
                        ticket_id,
                    ),
                    "busy",
                )
                with self.assertRaises(WorkspaceBusyError):
                    second_workspace_manager.open(ticket_id, "second-manager-run")
            finally:
                executor.release.set()

            deadline = time.monotonic() + ASYNC_TEST_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                try:
                    session = second_workspace_manager.open(ticket_id, "released-run")
                except WorkspaceBusyError:
                    time.sleep(0.01)
                    continue
                session.close()
                break
            else:
                self.fail("worker exited but the real ticket lease was not released")
            self.assertEqual(
                _acquire_lease_in_child(
                    data_root,
                    self.service.project_id,
                    ticket_id,
                ),
                "acquired",
            )

    def test_start能力关闭时fail_closed(self) -> None:
        ticket_id = self._ticket("disabled-ticket")
        manager = self._manager(BlockingExecutor(), enabled=False)

        with self.assertRaises(AutonomyError) as caught:
            manager.handle_intent(ticket_id, {"intent": "start", "request_id": "disabled-start"})

        self.assertEqual(caught.exception.code, "capability_disabled")
        self.assertEqual(
            self.service.ticket_detail(ticket_id)["autonomous_run"],
            {"state": "pending", "revision": 0},
        )

    def test_start拒绝未请求自动模式的工单(self) -> None:
        ticket_id = self._ticket("interactive-ticket", mode="interactive")
        manager = self._manager(BlockingExecutor())

        with self.assertRaises(AutonomyError) as caught:
            manager.handle_intent(ticket_id, {"intent": "start", "request_id": "bad-start"})

        self.assertEqual(caught.exception.code, "autonomous_not_requested")

    def test_重复intent和request_id幂等且同工单只有一个worker(self) -> None:
        ticket_id = self._ticket("one-worker-ticket")
        executor = BlockingExecutor(block_after_safe_point=True)
        manager = self._manager(executor)
        payload = {"intent": "start", "request_id": "same-start"}

        first = manager.handle_intent(ticket_id, payload)
        self.assertTrue(executor.started.wait(2))
        duplicate = manager.handle_intent(ticket_id, payload)
        with self.assertRaises(AutonomyError) as caught:
            manager.handle_intent(
                ticket_id, {"intent": "start", "request_id": "different-start"})

        self.assertEqual(caught.exception.code, "invalid_transition")
        self.assertEqual(executor.calls, 1)
        self.assertEqual(
            first["autonomous_run"]["run_id"],
            duplicate["autonomous_run"]["run_id"],
        )
        self.assertEqual(duplicate["autonomous_run"]["state"], "running")
        executor.allow_safe_point.set()
        executor.release.set()
        _wait_state(self.service, ticket_id, "succeeded")

    def test_worker线程启动失败收敛为可恢复的稳定中断态(self) -> None:
        ticket_id = self._ticket("worker-start-failure-ticket")
        executor = BlockingExecutor()
        manager = self._manager(executor)

        with patch(
            "icode.autonomy.threading.Thread.start",
            side_effect=RuntimeError(f"private start failure at {self.workspace}"),
        ), self.assertRaises(AutonomyError) as caught:
            manager.handle_intent(
                ticket_id,
                {"intent": "start", "request_id": "worker-start-failure"},
            )

        self.assertEqual(caught.exception.code, "worker_start_failed")
        interrupted = self.service.ticket_detail(ticket_id)
        self.assertEqual(interrupted["autonomous_run"]["state"], "interrupted")
        self.assertEqual(
            interrupted["autonomous_run"]["error_code"],
            "worker_start_failed",
        )
        self.assertEqual(interrupted["effective_execution_mode"], "interactive")
        self.assertEqual(interrupted["mode_status"], "pending_activation")
        raw = json.dumps(
            self.service._resolve_ticket_record(ticket_id).metadata["extensions"]
            ["icode_agent"]["autonomous_run"],
            ensure_ascii=False,
        )
        self.assertNotIn("private start failure", raw)
        self.assertNotIn(str(self.workspace), raw)

        manager.handle_intent(
            ticket_id,
            {"intent": "resume", "request_id": "worker-start-retry"},
        )
        self.assertTrue(executor.started.wait(2))
        executor.allow_safe_point.set()
        _wait_state(self.service, ticket_id, "succeeded")

    def test_重启后重复intent身份从raw扩展判重且不启动worker(self) -> None:
        ticket_id = self._ticket("restart-idempotency-ticket")
        first_executor = NeverSafePointExecutor()
        first_manager = self._manager(first_executor)
        payload = {"intent": "start", "request_id": "restart-same-start"}
        first_manager.handle_intent(ticket_id, payload)
        self.assertTrue(first_executor.started.wait(2))
        first_manager.shutdown(timeout=0.05)
        first_executor.release.set()
        time.sleep(0.05)

        record = self.service._resolve_ticket_record(ticket_id)
        raw_runtime = record.metadata["extensions"]["icode_agent"]["autonomous_run"]
        self.assertEqual(raw_runtime["last_intent"], "start")
        self.assertEqual(raw_runtime["last_intent_request_id"], "restart-same-start")
        public = self.service.ticket_detail(ticket_id)["autonomous_run"]
        self.assertNotIn("last_intent", public)
        self.assertNotIn("last_intent_request_id", public)

        replay_executor = BlockingExecutor()
        replay_manager = self._manager(replay_executor)
        replayed = replay_manager.handle_intent(ticket_id, payload)

        self.assertEqual(replayed["autonomous_run"]["state"], "interrupted")
        self.assertEqual(replay_executor.calls, 0)

    def test_较旧intent在后续动作和manager重建后重放仍幂等(self) -> None:
        ticket_id = self._ticket("older-intent-replay-ticket")
        first_executor = BlockingExecutor()
        first_manager = self._manager(first_executor)
        first_manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": "older-start"})
        self.assertTrue(first_executor.started.wait(2))
        first_manager.handle_intent(
            ticket_id, {"intent": "pause", "request_id": "older-pause"})
        first_executor.allow_safe_point.set()
        _wait_state(self.service, ticket_id, "paused")
        first_manager.shutdown(timeout=0.2)

        resumed_executor = BlockingExecutor()
        resumed_manager = self._manager(resumed_executor)
        resumed_manager.handle_intent(
            ticket_id, {"intent": "resume", "request_id": "newer-resume"})
        self.assertTrue(resumed_executor.started.wait(2))

        replayed = resumed_manager.handle_intent(
            ticket_id, {"intent": "pause", "request_id": "older-pause"})

        self.assertEqual(replayed["autonomous_run"]["state"], "running")
        resumed_executor.allow_safe_point.set()
        _wait_state(self.service, ticket_id, "succeeded")
        self.assertEqual(resumed_executor.calls, 1)
        raw_runtime = self.service._resolve_ticket_record(ticket_id).metadata[
            "extensions"]["icode_agent"]["autonomous_run"]
        self.assertLessEqual(len(raw_runtime["intent_receipts"]), 64)
        self.assertNotIn(
            "intent_receipts",
            self.service.ticket_detail(ticket_id)["autonomous_run"],
        )

    def test_intent_receipt历史有界并保留last_intent兼容字段(self) -> None:
        ticket_id = self._ticket("bounded-intent-receipts-ticket")
        seeded = [f"{index:064x}" for index in range(64)]
        self.service.update_agent_extension(
            ticket_id,
            {"autonomous_run": {
                "state": "pending",
                "revision": 0,
                "intent_receipts": seeded,
            }},
            request_id="seed-bounded-intent-receipts",
        )
        executor = BlockingExecutor()
        manager = self._manager(executor)

        manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": "bounded-start"})
        self.assertTrue(executor.started.wait(2))
        raw_runtime = self.service._resolve_ticket_record(ticket_id).metadata[
            "extensions"]["icode_agent"]["autonomous_run"]

        self.assertEqual(len(raw_runtime["intent_receipts"]), 64)
        self.assertNotIn(seeded[0], raw_runtime["intent_receipts"])
        self.assertEqual(raw_runtime["last_intent"], "start")
        self.assertEqual(raw_runtime["last_intent_request_id"], "bounded-start")
        executor.allow_safe_point.set()
        _wait_state(self.service, ticket_id, "succeeded")

    def test_pause只在safe_point变为paused(self) -> None:
        ticket_id = self._ticket("pause-ticket")
        executor = BlockingExecutor()
        manager = self._manager(executor)
        manager.handle_intent(ticket_id, {"intent": "start", "request_id": "pause-start"})
        self.assertTrue(executor.started.wait(2))

        requested = manager.handle_intent(
            ticket_id, {"intent": "pause", "request_id": "pause-request"})
        self.assertEqual(requested["autonomous_run"]["state"], "pause_requested")
        executor.allow_safe_point.set()

        paused = _wait_state(self.service, ticket_id, "paused")
        self.assertEqual(paused["effective_execution_mode"], "autonomous")
        self.assertEqual(paused["autonomous_run"]["last_step"], "plan")

    def test_最后一步运行中pause在runner返回边界优先于succeeded(self) -> None:
        ticket_id = self._ticket("pause-during-final-step-ticket")
        runner = BlockingLastStepRunner(ChainReport(
            delivered=True,
            out_dir="ignored",
            ticket_id=ticket_id,
        ))
        executor = NativeChainExecutor(
            self.settings,
            backend=FakeBackend(["完成"]),
            step_runner=runner,
        )
        manager = self._manager(executor)

        with patch("icode.autonomy.chain_steps", return_value=("audit",)), patch(
            "icode.autonomy.ControlPlane.trace",
            return_value=SimpleNamespace(
                returncode=0,
                data={
                    "ok": True,
                    "ticket_id": ticket_id,
                    "status": "deepcheck_done",
                },
            ),
        ):
            manager.handle_intent(
                ticket_id,
                {"intent": "start", "request_id": "final-step-pause-start"},
            )
            self.assertTrue(runner.started.wait(2))
            requested = manager.handle_intent(
                ticket_id,
                {"intent": "pause", "request_id": "final-step-pause"},
            )
            self.assertEqual(requested["autonomous_run"]["state"], "pause_requested")
            runner.release.set()
            paused = _wait_state(self.service, ticket_id, "paused")

        self.assertEqual(runner.calls, 1)
        self.assertEqual(paused["autonomous_run"]["last_step"], "audit")
        self.assertNotEqual(paused["autonomous_run"]["state"], "succeeded")

    def test_最后一步返回blocked时cancel意图仍在完成边界优先(self) -> None:
        ticket_id = self._ticket("cancel-during-blocked-final-step-ticket")
        runner = BlockingLastStepRunner(ChainReport(
            steps=[StepReport(
                step="audit",
                ok=False,
                out_dir="ignored",
            )],
            stopped_at="audit",
            reason="bounded blocked result",
            out_dir="ignored",
            ticket_id=ticket_id,
        ))
        executor = NativeChainExecutor(
            self.settings,
            backend=FakeBackend(["完成"]),
            step_runner=runner,
        )
        manager = self._manager(executor)

        with patch("icode.autonomy.chain_steps", return_value=("audit",)), patch(
            "icode.autonomy.ControlPlane.trace",
            return_value=SimpleNamespace(
                returncode=0,
                data={
                    "ok": True,
                    "ticket_id": ticket_id,
                    "status": "deepcheck_done",
                },
            ),
        ):
            manager.handle_intent(
                ticket_id,
                {"intent": "start", "request_id": "final-step-cancel-start"},
            )
            self.assertTrue(runner.started.wait(2))
            manager.handle_intent(
                ticket_id,
                {"intent": "cancel", "request_id": "final-step-cancel"},
            )
            runner.release.set()
            cancelled = _wait_state(self.service, ticket_id, "cancelled")

        self.assertEqual(runner.calls, 1)
        self.assertEqual(cancelled["autonomous_run"]["last_step"], "audit")
        self.assertNotEqual(cancelled["autonomous_run"]["state"], "blocked")

    def test_相同request_id用于不同intent不会发生控制面幂等冲突(self) -> None:
        ticket_id = self._ticket("shared-request-ticket")
        executor = BlockingExecutor()
        manager = self._manager(executor)
        shared_request = "shared-request-id"
        manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": shared_request})
        self.assertTrue(executor.started.wait(2))

        requested = manager.handle_intent(
            ticket_id, {"intent": "pause", "request_id": shared_request})

        self.assertEqual(requested["autonomous_run"]["state"], "pause_requested")
        executor.allow_safe_point.set()
        _wait_state(self.service, ticket_id, "paused")

    def test_intent持久化失败返回稳定错误且不激活停止意图(self) -> None:
        service = FailOnceTicketService(
            self.settings,
            workspace=self.workspace,
            index_path=self.workspace / "index.json",
        )
        ticket_id = service.create_ticket(
            _payload(service.project_id, "persistence-ticket"))["ticket"]["ticket_id"]
        executor = BlockingExecutor()
        manager = AutonomyManager(service, executor=executor, enabled=True)
        self.managers.append(manager)
        manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": "persistence-start"})
        self.assertTrue(executor.started.wait(2))
        service.fail_next_update = True

        with self.assertRaises(AutonomyError) as caught:
            manager.handle_intent(
                ticket_id, {"intent": "pause", "request_id": "persistence-pause"})

        self.assertEqual(caught.exception.code, "state_persistence_failed")
        executor.allow_safe_point.set()
        _wait_state(service, ticket_id, "succeeded")

    def test_resume创建新run并成功(self) -> None:
        ticket_id = self._ticket("resume-ticket")
        executor = ResumeExecutor()
        manager = self._manager(executor)
        started = manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": "resume-start"})
        first_run_id = started["autonomous_run"]["run_id"]
        self.assertTrue(executor.first_started.wait(2))
        manager.handle_intent(ticket_id, {"intent": "pause", "request_id": "resume-pause"})
        executor.first_safe_point.set()
        paused = _wait_state(self.service, ticket_id, "paused")
        _wait_worker_release(manager, ticket_id)

        manager.handle_intent(ticket_id, {"intent": "resume", "request_id": "resume-again"})
        succeeded = _wait_state(self.service, ticket_id, "succeeded")

        self.assertEqual(executor.calls, 2)
        self.assertNotEqual(succeeded["autonomous_run"]["run_id"], first_run_id)
        self.assertGreater(
            succeeded["autonomous_run"]["revision"],
            paused["autonomous_run"]["revision"],
        )

    def test_resume支持failed_blocked与interrupted终态(self) -> None:
        for index, state in enumerate(("failed", "blocked", "interrupted")):
            with self.subTest(state=state):
                ticket_id = self._ticket(f"resume-{state}-ticket")
                self.service.update_agent_extension(
                    ticket_id,
                    {"autonomous_run": {
                        "state": state,
                        "run_id": f"previous-{state}-run",
                        "revision": 3,
                        "updated_at": "2026-09-23T01:00:00Z",
                    }},
                    request_id=f"seed-resume-{state}-{index}",
                )
                executor = BlockingExecutor()
                executor.allow_safe_point.set()
                manager = self._manager(executor)

                manager.handle_intent(
                    ticket_id,
                    {"intent": "resume", "request_id": f"resume-{state}"},
                )
                succeeded = _wait_state(self.service, ticket_id, "succeeded")

                self.assertEqual(executor.calls, 1)
                self.assertNotEqual(
                    succeeded["autonomous_run"]["run_id"],
                    f"previous-{state}-run",
                )

    def test_cancel与takeover在safe_point生效(self) -> None:
        for intent, terminal in (("cancel", "cancelled"), ("takeover", "paused")):
            with self.subTest(intent=intent):
                ticket_id = self._ticket(f"{intent}-ticket")
                executor = BlockingExecutor()
                manager = self._manager(executor)
                manager.handle_intent(
                    ticket_id, {"intent": "start", "request_id": f"{intent}-start"})
                self.assertTrue(executor.started.wait(2))
                requested = manager.handle_intent(
                    ticket_id, {"intent": intent, "request_id": f"{intent}-request"})
                expected_requested = "cancel_requested" if intent == "cancel" else "pause_requested"
                self.assertEqual(requested["autonomous_run"]["state"], expected_requested)
                executor.allow_safe_point.set()
                stopped = _wait_state(self.service, ticket_id, terminal)
                self.assertEqual(stopped["effective_execution_mode"], "interactive")
                self.assertEqual(stopped["mode_status"], "pending_activation")

    def test_pause_requested可升级为cancel或takeover但不接受重复pause(self) -> None:
        for intent, requested_state, terminal in (
            ("cancel", "cancel_requested", "cancelled"),
            ("takeover", "pause_requested", "paused"),
        ):
            with self.subTest(intent=intent):
                ticket_id = self._ticket(f"pause-upgrade-{intent}-ticket")
                executor = BlockingExecutor()
                manager = self._manager(executor)
                manager.handle_intent(
                    ticket_id,
                    {"intent": "start", "request_id": f"pause-upgrade-{intent}-start"},
                )
                self.assertTrue(executor.started.wait(2))
                manager.handle_intent(
                    ticket_id,
                    {"intent": "pause", "request_id": f"pause-upgrade-{intent}-pause"},
                )
                with self.assertRaises(AutonomyError) as duplicate:
                    manager.handle_intent(
                        ticket_id,
                        {
                            "intent": "pause",
                            "request_id": f"pause-upgrade-{intent}-pause-again",
                        },
                    )
                self.assertEqual(duplicate.exception.code, "invalid_transition")

                upgraded = manager.handle_intent(
                    ticket_id,
                    {"intent": intent, "request_id": f"pause-upgrade-{intent}-apply"},
                )
                self.assertEqual(
                    upgraded["autonomous_run"]["state"],
                    requested_state,
                )
                executor.allow_safe_point.set()
                stopped = _wait_state(self.service, ticket_id, terminal)

                self.assertEqual(stopped["effective_execution_mode"], "interactive")
                self.assertEqual(stopped["mode_status"], "pending_activation")

    def test_executor异常只持久化稳定错误码(self) -> None:
        ticket_id = self._ticket("failure-ticket")
        manager = self._manager(RaisingExecutor())

        manager.handle_intent(ticket_id, {"intent": "start", "request_id": "failure-start"})
        failed = _wait_state(self.service, ticket_id, "failed")

        self.assertEqual(failed["autonomous_run"]["error_code"], "executor_error")
        record = self.service._resolve_ticket_record(ticket_id)
        persisted = record.metadata["extensions"]["icode_agent"]["autonomous_run"]
        raw = json.dumps(persisted, ensure_ascii=False)
        self.assertNotIn("secret exception", raw)
        self.assertNotIn(str(self.workspace), raw)
        self.assertNotIn("exception", persisted)

    def test_启动时active_stale状态统一降级interrupted(self) -> None:
        ticket_ids = []
        for index, state in enumerate((
            "starting", "running", "pause_requested", "cancel_requested"
        )):
            ticket_id = self._ticket(f"stale-{index}")
            ticket_ids.append(ticket_id)
            self.service.update_agent_extension(
                ticket_id,
                {"autonomous_run": {
                    "state": state,
                    "run_id": f"stale-run-{index}",
                    "revision": index + 1,
                    "updated_at": "2026-09-23T01:00:00Z",
                }},
                request_id=f"seed-stale-{index}",
            )

        self._manager(None, enabled=False)

        for ticket_id in ticket_ids:
            ticket = self.service.ticket_detail(ticket_id)
            recovered = ticket["autonomous_run"]
            self.assertEqual(recovered["state"], "interrupted")
            self.assertEqual(recovered["error_code"], "process_restarted")
            self.assertEqual(ticket["effective_execution_mode"], "interactive")
            self.assertEqual(ticket["mode_status"], "pending_activation")

    def test_stale恢复保留intent身份且重放不新建worker(self) -> None:
        ticket_id = self._ticket("stale-idempotency-ticket")
        self.service.update_agent_extension(
            ticket_id,
            {
                "effective_execution_mode": "autonomous",
                "mode_status": "active",
                "autonomous_run": {
                    "state": "running",
                    "run_id": "stale-identity-run",
                    "revision": 3,
                    "updated_at": "2026-09-23T01:00:00Z",
                    "last_intent": "start",
                    "last_intent_request_id": "stale-same-start",
                },
            },
            request_id="seed-stale-identity",
        )
        executor = BlockingExecutor()
        manager = self._manager(executor)

        replayed = manager.handle_intent(
            ticket_id, {"intent": "start", "request_id": "stale-same-start"})

        self.assertEqual(replayed["autonomous_run"]["state"], "interrupted")
        self.assertEqual(executor.calls, 0)
        record = self.service._resolve_ticket_record(ticket_id)
        raw_runtime = record.metadata["extensions"]["icode_agent"]["autonomous_run"]
        self.assertEqual(raw_runtime["last_intent"], "start")
        self.assertEqual(raw_runtime["last_intent_request_id"], "stale-same-start")

    def test_shutdown有界且未到safe_point时诚实降级(self) -> None:
        ticket_id = self._ticket("shutdown-ticket")
        executor = NeverSafePointExecutor()
        manager = self._manager(executor)
        manager.handle_intent(ticket_id, {"intent": "start", "request_id": "shutdown-start"})
        self.assertTrue(executor.started.wait(2))

        before = time.monotonic()
        manager.shutdown(timeout=0.05)
        elapsed = time.monotonic() - before

        self.assertLess(elapsed, 0.5)
        ticket = self.service.ticket_detail(ticket_id)
        interrupted = ticket["autonomous_run"]
        self.assertEqual(interrupted["state"], "interrupted")
        self.assertEqual(interrupted["error_code"], "shutdown")
        self.assertEqual(ticket["effective_execution_mode"], "interactive")
        self.assertEqual(ticket["mode_status"], "pending_activation")
        executor.release.set()
        time.sleep(0.05)
        self.assertEqual(
            self.service.ticket_detail(ticket_id)["autonomous_run"]["state"],
            "interrupted",
        )

    def test_shutdown后旧worker到达safe_point不能覆写中断终态(self) -> None:
        ticket_id = self._ticket("shutdown-safe-point-ticket")
        executor = ShutdownSafePointExecutor()
        manager = self._manager(executor)
        manager.handle_intent(
            ticket_id,
            {"intent": "start", "request_id": "shutdown-safe-point-start"},
        )
        self.assertTrue(executor.started.wait(2))

        manager.shutdown(timeout=0.01)
        during_shutdown = self.service.ticket_detail(ticket_id)
        self.assertEqual(during_shutdown["autonomous_run"]["state"], "interrupted")
        self.assertEqual(during_shutdown["autonomous_run"]["error_code"], "shutdown")

        executor.allow_safe_point.set()
        self.assertTrue(executor.stopped.wait(2))
        after_safe_point = self.service.ticket_detail(ticket_id)
        self.assertEqual(after_safe_point["autonomous_run"]["state"], "interrupted")
        self.assertEqual(after_safe_point["autonomous_run"]["error_code"], "shutdown")

    def test_shutdown超时时新manager不能启动第二个worker(self) -> None:
        ticket_id = self._ticket("shutdown-no-double-worker-ticket")
        old_executor = NeverSafePointExecutor()
        old_manager = self._manager(old_executor)
        old_manager.handle_intent(
            ticket_id,
            {"intent": "start", "request_id": "shutdown-old-start"},
        )
        self.assertTrue(old_executor.started.wait(2))
        old_manager.shutdown(timeout=0.01)
        self.assertEqual(
            self.service.ticket_detail(ticket_id)["autonomous_run"]["state"],
            "interrupted",
        )

        new_executor = BlockingExecutor()
        new_manager = self._manager(new_executor)
        with self.assertRaises(AutonomyError) as caught:
            new_manager.handle_intent(
                ticket_id,
                {"intent": "resume", "request_id": "shutdown-early-resume"},
            )

        self.assertEqual(caught.exception.code, "invalid_transition")
        self.assertEqual(new_executor.calls, 0)

        old_executor.release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                new_manager.handle_intent(
                    ticket_id,
                    {"intent": "resume", "request_id": "shutdown-safe-resume"},
                )
                break
            except AutonomyError as exc:
                if exc.code != "invalid_transition":
                    raise
                time.sleep(0.01)
        else:
            self.fail("old process worker lease was not released")

        self.assertTrue(new_executor.started.wait(2))
        new_executor.allow_safe_point.set()
        _wait_state(self.service, ticket_id, "succeeded")
        self.assertEqual(new_executor.calls, 1)

    def test_shutdown单工单持久化异常仍处理其余worker并有界join(self) -> None:
        service = FailOneShutdownTicketService(
            self.settings,
            workspace=self.workspace,
            index_path=self.workspace / "shutdown-index.json",
        )
        first_ticket = service.create_ticket(
            _payload(service.project_id, "shutdown-failing-ticket"))["ticket"]["ticket_id"]
        second_ticket = service.create_ticket(
            _payload(service.project_id, "shutdown-healthy-ticket"))["ticket"]["ticket_id"]
        executor = MultiNeverSafePointExecutor(expected=2)
        manager = AutonomyManager(service, executor=executor, enabled=True)
        self.managers.append(manager)
        manager.handle_intent(
            first_ticket, {"intent": "start", "request_id": "shutdown-failing-start"})
        manager.handle_intent(
            second_ticket, {"intent": "start", "request_id": "shutdown-healthy-start"})
        self.assertTrue(executor.started.wait(2))
        service.fail_ticket_id = first_ticket
        try:
            before = time.monotonic()
            manager.shutdown(timeout=0.05)
            elapsed = time.monotonic() - before

            self.assertLess(elapsed, 0.5)
            self.assertCountEqual(
                service.shutdown_update_calls, [first_ticket, second_ticket])
            self.assertIn(
                service.ticket_detail(first_ticket)["autonomous_run"]["state"],
                ACTIVE_STATES,
            )
            self.assertEqual(
                service.ticket_detail(second_ticket)["autonomous_run"]["state"],
                "interrupted",
            )
            self.assertTrue(any(worker.is_alive() for worker in manager._workers.values()))
        finally:
            executor.release.set()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
