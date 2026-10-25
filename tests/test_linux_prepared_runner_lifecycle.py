"""Runner lifecycle software evidence: actual CP/FD/borrow, synthetic ELF and transport."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import replace
import errno
import inspect
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests._support import REPO_ROOT
from icode import chain, runner
from icode.backends import FakeBackend
from icode.approvals import ScriptedApprover
from icode.budget import Budget, BudgetTracker
from icode.config import Settings
from icode.control import ControlPlane
from icode.engineering_verification import VerificationCheck, VerificationPlan, _execute_check
from icode.handshake import next_out_dir
from icode.loop import LoopConfig, LoopResult
from icode.tools import builtin
from icode.tools.base import ToolContext

LINUX = sys.platform.startswith("linux") and callable(getattr(os, "pread", None))
if LINUX:
    from tests import test_linux_prepared_step as fixture
    from tests import test_linux_helper_dispatch as dispatch
    from icode import execution_broker as broker
    from icode import linux_prepared_step as prepared

VENDOR = REPO_ROOT / "vendor" / "icode-skill"


@unittest.skipUnless(LINUX, "Linux software fixture; skip is not acceptance")
class PreparedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.resources = fixture.PreparedTests(methodName="runTest")
        self.addCleanup(self.resources.doCleanups)
        self.resources.setUp()
        self.root = self.resources.session.workspace_root
        self.session = self.resources.session
        self.sandbox = self.resources.sandbox
        self.settings = Settings(VENDOR)
        self.cp = ControlPlane(self.settings)
        self.opened, self.views, self.contexts, self.payloads, self.channels = [], [], [], [], []
        self.make_ticket("plan")

    def make_ticket(self, step):
        self.step = step
        self.policy = self.session.policy(step, process_limit=16,
            wall_timeout_seconds=30, output_limit_bytes=4096)
        self.resources.policy = self.policy
        self.ticket = self.session.ticket_id
        self.out = next_out_dir(self.resources.root / "control")
        if step == "code":
            self.out.mkdir(parents=True, exist_ok=True)
            legacy = dict(ticket_id=self.ticket, requirement="runner lifecycle",
                created_at="2026-10-12T00:00:00Z", status="code_in_progress",
                completed_steps=["1", "2", "3"], code_files=["data.txt"],
                workflow_gate_schema_version=1, thinking_gate_schema_version=1,
                mcp_gate_schema_version=2, semantic_decisions=[], requirement_deltas=[],
                project_path=str(self.resources.root / "control"))
            (self.out / ".ico_metadata.json").write_text(json.dumps(legacy), encoding="utf-8")
            self.assertIs(self.cp.run("migration", "--dir", str(self.out), "--apply").data.get("ok"), True)
            (self.out / "03_plan_final.md").write_text("# Accepted fixture plan\n", encoding="utf-8")
        else:
            created = self.cp.create(self.out, ticket_id=self.ticket,
                requirement="runner lifecycle", birth="plan")
            self.assertIs(created.data.get("ok"), True)
        self.assertIs(self.cp.bind_execution_root(self.out, ticket_id=self.ticket,
            execution_root=self.root).data.get("ok"), True)
        check = VerificationCheck("first", "test",
            (sys.executable, "-I", "-B", "-X", "utf8", "-m", "unittest",
             "discover", "-s", str(self.root), "-t", str(self.root)),
            "unittest_summary_v1", timeout_seconds=3, output_limit_bytes=4096)
        self.plan = VerificationPlan(self.root, self.session.run_id, self.ticket,
            (check, replace(check, check_id="second")), steps=(step,) if step == "code" else ("code",), platforms=("Linux",))

    def events(self, kind):
        return [row for line in (self.out / ".ico_events.jsonl").read_text(encoding="utf-8").splitlines()
            if (row := json.loads(line))["event_type"] == kind]

    def opened_attempt(self):
        opened = self.cp.trace(self.out).data["open_steps"]
        self.assertEqual(len(opened), 1)
        return next(iter(opened))

    def require_private(self):
        target = getattr(runner, "_make_prepared_ctx", None)
        self.assertTrue(callable(target), "runner prepared context factory missing")
        return target

    def args(self, backend=None, **changes):
        args = dict(backend=backend or FakeBackend([]), workspace=self.root, step=self.step,
            ticket_id=self.ticket, requirement="runner lifecycle", out_dir=self.out,
            sandbox=self.sandbox, policy=self.policy, workspace_session=self.session,
            approver=ScriptedApprover(default=True),
            loop_config=LoopConfig(max_turns=8))
        if self.step == "code":
            args["verification_plan"] = self.plan
        args.update(changes)
        return args

    def invoke(self, backend=None, **changes):
        # Missing API must be an intentional assertion RED, never TypeError.
        self.assertIn("prepared_scope", inspect.signature(runner.run_contract_step).parameters,
            "runner prepared lifecycle keyword missing")
        return runner.run_contract_step(self.settings, **self.args(backend, **changes))

    def script(self, *, commands=2, submit=True):
        rows = [{"tool_calls": [{"id": "command-" + str(n), "name": "run_command",
            "arguments": {"argv": ["/usr/bin/true"]}}]} for n in range(commands)]
        if submit:
            rows.append({"tool_calls": [{"id": "artifact", "name": "submit_artifact",
                "arguments": {"name": "04_code_review_fix.md" if self.step == "code" else "01_plan.md",
                              "content": "# Actual model-double artifact\n"}}]})
        rows.append("done")
        rows.extend(json.dumps({"step": "Check actual fixture", "next_thought_needed": False})
            for _ in range(6))
        return FakeBackend(rows)

    @contextmanager
    def transport(self, *, notify_unknown=False):
        """Reuse low transport seams only; real dispatch, borrow and wrappers remain."""
        original_factory = prepared.open_linux_helper_object
        original_attach = prepared.LinuxPreparedStep._attach
        original_ctx = getattr(runner, "_make_prepared_ctx", None)
        def opening(*args):
            owner = original_factory(*args)
            self.opened.append((owner, owner.fileno()))
            return owner
        def attaching(scope, **kwargs):
            view = original_attach(scope, **kwargs)
            self.views.append(view)
            return view
        def context(*args, **kwargs):
            ctx = original_ctx(*args, **kwargs)
            self.contexts.append(ctx)
            return ctx
        def channel():
            pair = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            self.channels.extend(pair)
            return pair
        def received(*args, **kwargs):
            receiver = dispatch.Resource()
            receiver.receipt = lambda: dict(schema_version=1, resource="linux_payload_tasks",
                limit=self.policy.process_limit, configured=True, payload_started=None,
                terminal="finished", channel_status="complete")
            return receiver
        def execute(argv, **kwargs):
            kwargs["before_spawn"]()
            command = argv
            self.assertIs(command.helper_object, self.views[-1]._scope._owner)
            self.payloads.append(command.helper_object)
            if notify_unknown:
                kwargs["on_cleanup_unknown"]()
            output = b"Ran 1 test in 0.01s\n\nOK\n"
            return broker.ExecutionResult(0, "", len(output), None, False, True, None,
                raw_output=output)
        with ExitStack() as stack:
            stack.enter_context(patch.object(prepared, "open_linux_helper_object", side_effect=opening))
            stack.enter_context(patch.object(prepared.LinuxPreparedStep, "_attach", new=attaching))
            if callable(original_ctx):
                stack.enter_context(patch.object(runner, "_make_prepared_ctx", side_effect=context))
            stack.enter_context(patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel",
                side_effect=channel))
            stack.enter_context(patch("icode.linux_task_resource.create_task_resource_channel",
                side_effect=channel))
            stack.enter_context(patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor",
                side_effect=dispatch.Monitor))
            stack.enter_context(patch("icode.linux_task_resource.LinuxTaskResourceReceiver",
                side_effect=received))
            stack.enter_context(patch("icode.linux_task_scope.LinuxTaskScope",
                side_effect=lambda **kwargs: dispatch.Scope()))
            stack.enter_context(patch.object(broker, "_execute_policy_command", side_effect=execute))
            yield
        self.assertTrue(all(endpoint.fileno() == -1 for endpoint in self.channels))

    def owner_closed(self):
        self.assertEqual(len(self.opened), 1)
        with self.assertRaises(OSError) as caught:
            os.fstat(self.opened[0][1])
        self.assertEqual(caught.exception.errno, errno.EBADF)
        self.session.lease._validate_active()
        os.fstat(self.session.workspace_fd)

    def no_terminal(self):
        trace = self.cp.trace(self.out)
        self.assertIs(trace.data.get("ok"), True)
        self.assertEqual(self.events("step_finished"), [])
        self.assertEqual(self.events("state_changed"), [])
        self.assertTrue(trace.data["open_steps"])

    def bound_context(self):
        self.require_private()
        scope = self.resources.prepare()
        view = self.resources.attach(scope)
        raw = self.cp._step_start_result(self.out, self.step, ticket_id=self.ticket,
            request="context-real-start")
        from icode.linux_prepared_control import _prepared_control_attempt_binding
        attempt, observer = _prepared_control_attempt_binding(self.cp, out_dir=self.out,
            ticket_id=self.ticket, step=self.step, start_result=raw)
        view._bind_attempt(attempt, validate_attempt=observer)
        ctx = self.require_private()(self.root, self.sandbox, self.policy,
            workspace_session=self.session, prepared_step=view, prepared_attempt=attempt)
        return scope, view, attempt, ctx

    def test_internal_prepare_attach_before_raw_start_and_backend_same_owner_twice(self):
        original = ControlPlane._step_start_result
        def start(control, *args, **kwargs):
            self.assertEqual(len(self.opened), 1)
            self.assertEqual(len(self.views), 1)
            self.assertEqual(self.views[0]._scope._consume_state, "attached_pending")
            self.assertEqual(self.payloads, [])
            return original(control, *args, **kwargs)
        backend = self.script()
        with self.transport(), patch.object(ControlPlane, "_step_start_result", new=start), \
                patch.object(ControlPlane, "step_start", side_effect=AssertionError("no public prepared start")):
            report = self.invoke(backend)
        self.assertEqual(len(self.payloads), 2, report.error)
        self.assertTrue(all(owner is self.opened[0][0] for owner in self.payloads))
        self.assertEqual(self.views[0]._scope._consume_state, "spent")
        self.assertTrue(backend.calls)
        self.owner_closed()
        # CP success/refusal keeps its original gate semantics; lifecycle is checked separately.
        self.assertEqual(len(self.events("step_started")), 1)
        for ctx in self.contexts:
            self.assertIs(ctx.prepared_step, self.views[0])
            self.assertEqual(ctx.prepared_attempt, self.views[0]._attempt)
            self.assertFalse(builtin.run_command(ctx, ["/usr/bin/true"]).ok)

    def test_production_repair_round_reuses_view_before_internal_close(self):
        backend = FakeBackend(["missing artifact", {"tool_calls": [
            {"id": "repair-command", "name": "run_command", "arguments": {"argv": ["/usr/bin/true"]}},
            {"id": "repair-artifact", "name": "submit_artifact",
             "arguments": {"name": "01_plan.md", "content": "# Repaired fixture\n"}}]},
            "done", *[json.dumps({"step": "fixture", "next_thought_needed": False}) for _ in range(6)]])
        with self.transport():
            report = self.invoke(backend)
        self.assertEqual(len(self.payloads), 1, report.error)
        self.assertGreaterEqual(len(self.contexts), 2)
        self.assertTrue(all(ctx.prepared_step is self.views[0] for ctx in self.contexts))
        self.assertTrue(any("补救" in warning for warning in report.warnings))
        self.owner_closed()

    def test_actual_engineering_gate_two_checks_and_readonly_reviewer_no_rw_view(self):
        self.make_ticket("code")
        backend = self.script(commands=2)
        original = runner._run_task_reviewer
        def review(**kwargs):
            self.assertEqual(kwargs["policy"].write_roots, ())
            self.assertNotIn("prepared_step", kwargs)
            self.assertNotIn("prepared_attempt", kwargs)
            self.assertEqual(self.views[0]._scope._consume_state, "attached_bound")
            return original(**kwargs)
        # Reviewer model responses follow the actual ordinary contract loop.
        backend = FakeBackend([
            {"tool_calls": [{"id": "ordinary", "name": "run_command",
                "arguments": {"argv": ["/usr/bin/true"]}},
                {"id": "report", "name": "submit_artifact", "arguments": {
                    "name": "04_code_review_fix.md", "content": "# Actual fixture report\n"}}]},
            "done", "repair completed",
            {"tool_calls": [{"id": "review-read", "name": "read_file",
                "arguments": {"path": "data.txt"}}]},
            {"tool_calls": [{"id": "review-submit", "name": "submit_review",
                "arguments": {"summary": "Read fixture", "findings": []}}]},
            "done", *[json.dumps({"step": "fixture", "next_thought_needed": False}) for _ in range(6)]])
        with self.transport(), patch.object(runner, "_run_task_reviewer", new=review) as reviewing:
            report = self.invoke(backend)
        self.assertIsNotNone(report.verification_evidence, report.error)
        self.assertEqual(len(report.verification_evidence.to_receipt()["run"]["checks"]), 2)
        self.assertGreaterEqual(len(self.payloads), 3)
        self.assertTrue(all(owner is self.opened[0][0] for owner in self.payloads))
        self.assertTrue(any(name == "宿主工程验收" and ok
            for name, ok, detail in report.checkpoints), report.error)
        self.assertEqual(self.views[0]._scope._consume_state, "spent")
        self.owner_closed()

    def test_external_owner_is_spent_but_active_second_runner_rejected_before_start(self):
        scope = self.resources.prepare()
        descriptor = scope._owner.fileno()
        with self.transport():
            report = self.invoke(self.script(commands=0), prepared_scope=scope)
        self.assertEqual(scope._consume_state, "spent", report.error)
        self.assertEqual(scope._owner_state, "active")
        os.fstat(descriptor)
        before = self.events("step_started")
        backend = self.script(commands=0)
        with patch.object(ControlPlane, "_step_start_result") as start:
            second = self.invoke(backend, prepared_scope=scope)
        self.assertFalse(second.ok)
        start.assert_not_called()
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.events("step_started"), before)
        self.assertEqual(scope._owner_state, "active")

    def test_real_tools_and_engineering_reject_all_public_binding_drifts(self):
        scope, view, attempt, original = self.bound_context()
        changes = [
            {"policy": None}, {"policy": replace(self.policy)},
            {"workspace_session": replace(self.session)}, {"workspace_session": None},
            {"sandbox": object()}, {"root": Path(str(self.root))},
            {"prepared_step": object()}, {"prepared_attempt": "wrong"},
            {"read_only_workspace": True},
            {"prepared_step": None, "prepared_attempt": None},
            {"policy": None, "prepared_step": None, "prepared_attempt": None}]
        for change in changes:
            for consume in ("tool", "engineering"):
                with self.subTest(change=tuple(change), consume=consume):
                    ctx = self.require_private()(self.root, self.sandbox, self.policy,
                        workspace_session=self.session, prepared_step=view, prepared_attempt=attempt)
                    for key, value in change.items():
                        setattr(ctx, key, value)
                    with patch.object(builtin, "execute_linux_resource_observed_command") as resource, \
                            patch.object(builtin, "execute_policy_command") as ordinary, \
                            patch.object(runner, "_run_unittest_with_bounded_output") as legacy, \
                            patch.object(self.sandbox, "wrap_policy") as wrapper, \
                            patch.object(prepared, "open_linux_helper_object") as factory:
                        answer = (builtin.run_command(ctx, ["/usr/bin/true"]) if consume == "tool"
                            else _execute_check(self.plan.checks[0], ctx, None))
                    if consume == "tool":
                        self.assertFalse(answer.ok)
                        self.assertIn(answer.meta.get("error"), ("isolation_unavailable", "invalid_cwd"))
                    else:
                        self.assertEqual(answer.status, "execution_unavailable")
                    for spy in (resource, ordinary, legacy, wrapper, factory):
                        spy.assert_not_called()
        self.assertEqual(scope._consume_state, "attached_bound")
        view.finish()
        self.assertFalse(builtin.run_command(original, ["/usr/bin/true"]).ok)

    def test_fresh_closed_cp_and_broken_chain_block_real_consumer_before_broker(self):
        scope, view, attempt, ctx = self.bound_context()
        self.assertIs(self.cp.step_finish(self.out, self.step, attempt, "blocked",
            ticket_id=self.ticket, request="close-control", evidence=["fixture:closed"]).data.get("ok"), True)
        with patch.object(builtin, "execute_linux_resource_observed_command") as resource:
            self.assertFalse(builtin.run_command(ctx, ["/usr/bin/true"]).ok)
            self.assertEqual(_execute_check(self.plan.checks[0], ctx, None).status, "execution_unavailable")
        resource.assert_not_called()
        self.make_ticket("plan")
        scope, view, attempt, ctx = self.bound_context()
        with (self.out / ".ico_events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("{isolated-invalid-event\n")
        with patch.object(builtin, "execute_linux_resource_observed_command") as resource:
            self.assertFalse(builtin.run_command(ctx, ["/usr/bin/true"]).ok)
        resource.assert_not_called()

    def test_raw_or_bind_failure_finishes_pending_and_closes_internal_owner_no_model(self):
        original = ControlPlane._step_start_result
        def bad_start(control, *args, **kwargs):
            result = original(control, *args, **kwargs)
            return replace(result, data=dict(result.data, attempt=True))
        backend = self.script()
        with self.transport(), patch.object(ControlPlane, "_step_start_result", new=bad_start):
            report = self.invoke(backend)
        self.assertFalse(report.ok)
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.views[0]._scope._consume_state, "spent")
        self.owner_closed()
        self.no_terminal()

    def terminal_case(self, branch, *, unknown=False, external_unknown=False):
        if branch in ("engineering_budget", "engineering_failure"):
            self.make_ticket("code")
        supplied = self.resources.prepare() if external_unknown else None
        descriptor = supplied._owner.fileno() if supplied is not None else None
        backend = self.script(commands=0)
        with ExitStack() as stack:
            if branch == "ordinary_budget":
                stack.enter_context(patch.object(runner, "_run_agent",
                    return_value=LoopResult(False, "budget_exceeded")))
            elif branch == "repair_budget":
                stack.enter_context(patch.object(runner, "_run_agent", side_effect=[
                    LoopResult(True, "done"),
                    LoopResult(False, "budget_exceeded")]))
            elif branch in ("engineering_budget", "engineering_failure"):
                def gate(**kwargs):
                    kwargs["report"].error = ("budget_exceeded" if branch == "engineering_budget"
                        else "engineering_verification_failed")
                    return False
                stack.enter_context(patch.object(runner, "_contract_engineering_gate", side_effect=gate))
            elif branch == "deliberation_budget":
                stack.enter_context(patch.object(runner, "_prepare_deliberation",
                    return_value=SimpleNamespace(budget_exceeded=True)))
            original_finish = prepared._LinuxStepAttachment.finish
            original_close = prepared.LinuxPreparedStep.close
            finish_calls, close_calls = [], []
            def finish(view):
                finish_calls.append(view)
                if unknown:
                    raise OSError("private finish body")
                if external_unknown:
                    # Caller-owned close races with its actual view finish; no field injection.
                    with self.assertRaises(prepared.LinuxPreparedStepError):
                        supplied.close()
                return original_finish(view)
            def close(scope):
                close_calls.append(scope)
                return original_close(scope)
            stack.enter_context(patch.object(prepared._LinuxStepAttachment, "finish", new=finish))
            stack.enter_context(patch.object(prepared.LinuxPreparedStep, "close", new=close))
            owner_closes = []
            if external_unknown:
                real_owner_close = fixture.factory.LinuxHelperObject.close
                def failed_owner_close(owner):
                    owner_closes.append(owner)
                    real_owner_close(owner)
                    raise OSError("external owner close confirmation failed")
                stack.enter_context(patch.object(fixture.factory.LinuxHelperObject, "close",
                    new=failed_owner_close))
            original_terminal = ControlPlane.step_finish
            terminal_calls = []
            def terminal(control, *args, **kwargs):
                caller = inspect.currentframe().f_back.f_code.co_name
                expected = ("_stop_contract_for_budget" if branch.endswith("budget")
                    else "_finish_step")
                self.assertEqual(caller, expected)
                if not external_unknown:
                    self.assertEqual(len(finish_calls), 1)
                    self.assertEqual(len(close_calls), 1)
                    self.assertEqual(self.views[0]._scope._consume_state, "spent")
                    self.owner_closed()
                # An external regression must reach actual CP; the spy never blocks it.
                result = original_terminal(control, *args, **kwargs)
                terminal_calls.append(result)
                return result
            stack.enter_context(patch.object(ControlPlane, "step_finish", new=terminal))
            selected_agent = runner._run_agent
            def checkpointed_agent(**kwargs):
                kwargs["ctx"].checkpointer.save(turn_index=0, tool_calls=0, history=[])
                return selected_agent(**kwargs)
            stack.enter_context(patch.object(runner, "_run_agent", side_effect=checkpointed_agent))
            original_clear = runner.Checkpointer.clear
            clearing = stack.enter_context(patch.object(runner.Checkpointer, "clear",
                autospec=True, side_effect=original_clear))
            with self.transport():
                report = self.invoke(backend, **({"prepared_scope": supplied}
                    if external_unknown else {}))
        self.assertEqual(len(finish_calls), 1)
        self.assertEqual(len(close_calls), 1)
        if external_unknown:
            self.assertEqual(close_calls, [supplied])
            self.assertEqual(owner_closes, [supplied._owner])
            self.assertEqual(supplied._owner_state, "unknown")
            self.assertEqual(supplied._consume_state, "spent")
            self.assertEqual(self.opened, [])
            with self.assertRaises(OSError) as caught:
                os.fstat(descriptor)
            self.assertEqual(caught.exception.errno, errno.EBADF)
            self.session.lease._validate_active()
            os.fstat(self.session.workspace_fd)
        else:
            self.owner_closed()
        if unknown or external_unknown:
            self.assertEqual(terminal_calls, [])
            self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
            self.no_terminal()
            clearing.assert_not_called()
            from icode.checkpoint import CHECKPOINT_NAME
            saved = json.loads((self.out / CHECKPOINT_NAME).read_text(encoding="utf-8"))
            self.assertEqual(saved["attempt"], self.opened_attempt())
            self.assertEqual(saved["step"], self.step)
        else:
            self.assertTrue(terminal_calls, (branch, report.error))
        print("software-terminal-fixture " + json.dumps(dict(branch=branch, unknown=unknown,
            external_unknown=external_unknown,
            terminal_calls=len(terminal_calls), actual_finish_events=len(self.events("step_finished")),
            status=self.cp.trace(self.out).data["status"],
            finish_attempts=len(finish_calls), close_attempts=len(close_calls)), sort_keys=True))
        return report

    def test_six_real_terminal_sites_cleanup_before_cp_and_unknown_never_finish(self):
        for branch in ("ordinary_budget", "repair_budget", "engineering_budget",
                "engineering_failure", "deliberation_budget", "normal"):
            for unknown in (False, True):
                with self.subTest(branch=branch, unknown=unknown):
                    # Fresh isolated fixture for each terminal; no reused attempt/owner.
                    case = type(self)(methodName="runTest")
                    case.setUp()
                    try:
                        case.terminal_case(branch, unknown=unknown)
                    finally:
                        case.doCleanups()

    def test_external_real_close_unknown_blocks_all_six_terminals_and_checkpoint_clear(self):
        for branch in ("ordinary_budget", "repair_budget", "engineering_budget",
                "engineering_failure", "deliberation_budget", "normal"):
            with self.subTest(branch=branch):
                case = type(self)(methodName="runTest")
                case.setUp()
                try:
                    case.terminal_case(branch, external_unknown=True)
                finally:
                    case.doCleanups()

    def test_external_real_close_unknown_overrides_ordinary_body_error_without_runner_retry(self):
        scope = self.resources.prepare()
        descriptor = scope._owner.fileno()
        owner_closes = []
        real_owner_close = fixture.factory.LinuxHelperObject.close
        def failed_owner_close(owner):
            owner_closes.append(owner)
            real_owner_close(owner)
            raise OSError("external owner close confirmation failed")
        def post(*args):
            with self.assertRaises(prepared.LinuxPreparedStepError):
                scope.close()
            raise OSError("ordinary post body")
        original_finish = prepared._LinuxStepAttachment.finish
        with self.transport(), patch.object(fixture.factory.LinuxHelperObject, "close",
                new=failed_owner_close), patch.object(scope, "close", wraps=scope.close) as closing, \
                patch.object(prepared._LinuxStepAttachment, "finish", autospec=True,
                    side_effect=original_finish) as finishing, \
                patch.object(ControlPlane, "step_finish", wraps=ControlPlane.step_finish) as terminal, \
                patch.object(runner.Checkpointer, "clear") as clearing:
            report = self.invoke(self.script(commands=0), prepared_scope=scope, post_write=post)
        self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
        closing.assert_called_once_with()
        finishing.assert_called_once_with(self.views[0])
        self.assertEqual(owner_closes, [scope._owner])
        self.assertEqual(scope._owner_state, "unknown")
        self.assertEqual(scope._consume_state, "spent")
        terminal.assert_not_called()
        clearing.assert_not_called()
        self.no_terminal()
        from icode.checkpoint import CHECKPOINT_NAME
        saved = json.loads((self.out / CHECKPOINT_NAME).read_text(encoding="utf-8"))
        self.assertEqual(saved["attempt"], self.opened_attempt())
        self.assertEqual(saved["step"], self.step)
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)
        self.session.lease._validate_active()
        os.fstat(self.session.workspace_fd)

    def test_faulted_finish_silent_does_not_grant_health_or_cp_terminal(self):
        def post(*args):
            self.views[0]._scope._consume_state = "faulted"
        with self.transport():
            report = self.invoke(self.script(commands=0), post_write=post)
        self.assertFalse(report.ok)
        self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
        self.assertEqual(self.views[0]._scope._consume_state, "faulted")
        self.owner_closed()
        self.no_terminal()

    def test_attach_failure_closes_owner_once_without_start_model_or_payload(self):
        backend = self.script()
        with self.transport(), patch.object(prepared.LinuxPreparedStep, "_attach",
                side_effect=OSError("private attach")) as attach, \
                patch.object(ControlPlane, "_step_start_result") as start:
            report = self.invoke(backend)
        self.assertFalse(report.ok)
        attach.assert_called_once()
        start.assert_not_called()
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.payloads, [])
        self.owner_closed()

    def test_body_cleanup_compound_errors_close_unknown_once_first_signal_identity(self):
        for body in (OSError("body"), KeyboardInterrupt("first-body"), SystemExit(7)):
            for finish_error in (OSError("finish"), KeyboardInterrupt("first-cleanup")):
                with self.subTest(body=type(body).__name__, finish=type(finish_error).__name__):
                    case = type(self)(methodName="runTest")
                    case.setUp()
                    attempts = []
                    real_owner_close = fixture.factory.LinuxHelperObject.close
                    def unknown(owner):
                        attempts.append(owner)
                        # Inject confirmed OS close followed by unknown report; never retry integer.
                        real_owner_close(owner)
                        raise SystemExit("later-close")
                    try:
                        with case.transport(), patch.object(runner, "_run_agent", side_effect=body), \
                                patch.object(prepared._LinuxStepAttachment, "finish", side_effect=finish_error), \
                                patch.object(fixture.factory.LinuxHelperObject, "close", new=unknown):
                            expected = body if not isinstance(body, Exception) else (
                                finish_error if not isinstance(finish_error, Exception) else None)
                            if expected is not None:
                                with case.assertRaises(type(expected)) as caught:
                                    case.invoke()
                                case.assertIs(caught.exception, expected)
                            else:
                                with case.assertRaises(SystemExit) as caught:
                                    case.invoke()
                                case.assertEqual(caught.exception.code, "later-close")
                        case.assertEqual(len(attempts), 1)
                        case.assertEqual(case.views[0]._scope._owner_state, "unknown")
                        case.no_terminal()
                    finally:
                        case.doCleanups()

    def test_ordinary_body_cannot_hide_cleanup_unknown_postwrite_and_no_retry(self):
        attempts = []
        original_close = fixture.factory.LinuxHelperObject.close
        def unknown(owner):
            attempts.append(owner)
            original_close(owner)
            raise OSError("private close")
        def post(*args):
            raise OSError("private post")
        with self.transport(), patch.object(fixture.factory.LinuxHelperObject, "close", new=unknown):
            report = self.invoke(self.script(commands=0), post_write=post)
        self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.views[0]._scope._owner_state, "unknown")
        self.no_terminal()

    def test_wrong_scope_refs_and_sources_reject_before_model_no_replacement_owner(self):
        scope = self.resources.prepare()
        for changes in ({"policy": replace(self.policy)}, {"workspace_session": replace(self.session)},
                {"sandbox": object()}, {"policy": None}, {"workspace_session": None}):
            with patch.object(ControlPlane, "_step_start_result") as start, \
                    patch.object(prepared, "open_linux_helper_object") as opening:
                backend = self.script()
                report = self.invoke(backend, prepared_scope=scope, **changes)
            self.assertFalse(report.ok)
            self.assertEqual(backend.calls, [])
            start.assert_not_called()
            opening.assert_not_called()
        self.assertEqual(scope._consume_state, "prepared")
        self.resources.write_image(fixture.image((1, 1)))
        with patch.object(ControlPlane, "_step_start_result") as start:
            report = self.invoke(self.script(), prepared_scope=scope)
        self.assertFalse(report.ok)
        start.assert_not_called()

    def test_chain_single_step_same_reference_none_callback_shape_and_bad_order(self):
        self.assertIn("prepared_scope", inspect.signature(chain.run_chain).parameters,
            "chain prepared lifecycle keyword missing")
        scope = self.resources.prepare()
        sentinel = runner.StepReport("plan", False, str(self.out), error="fixture-stop")
        original = chain.run_contract_step
        with patch.object(chain, "run_contract_step", return_value=sentinel) as callback:
            chain.run_chain(self.settings, backend=FakeBackend([]), workspace=self.root,
                requirement="fixture", ticket_id=self.ticket, out_dir=self.out, steps=("plan",),
                policy=self.policy, sandbox=self.sandbox, workspace_session=self.session,
                prepared_scope=scope, approver=ScriptedApprover(default=True))
        self.assertIs(callback.call_args.kwargs["prepared_scope"], scope)
        self.assertEqual(scope._consume_state, "prepared")
        with patch.object(chain, "run_contract_step", return_value=sentinel) as callback:
            chain.run_chain(self.settings, backend=FakeBackend([]), workspace=self.root,
                requirement="fixture", ticket_id=self.ticket, out_dir=self.out, steps=("plan",),
                policy=self.policy, sandbox=self.sandbox, workspace_session=self.session)
        self.assertNotIn("prepared_scope", callback.call_args.kwargs)
        with patch.object(chain, "run_contract_step") as callback:
            with self.assertRaises(ValueError):
                chain.run_chain(self.settings, backend=FakeBackend([]), workspace=self.root,
                    requirement="fixture", ticket_id=self.ticket, out_dir=self.out,
                    steps=("plan", "review"), policy=self.policy, sandbox=self.sandbox,
                    workspace_session=self.session, prepared_scope=scope)
        callback.assert_not_called()
        with self.transport(), patch.object(chain, "run_contract_step", wraps=original):
            report = chain.run_chain(self.settings, backend=self.script(), workspace=self.root,
                requirement="fixture", ticket_id=self.ticket, out_dir=self.out, steps=("plan",),
                policy=self.policy, sandbox=self.sandbox, workspace_session=self.session,
                prepared_scope=scope, approver=ScriptedApprover(default=True))
        self.assertEqual(scope._consume_state, "spent", report.reason)
        self.assertEqual(scope._owner_state, "active")
        self.assertEqual(len(self.payloads), 2)

    def test_none_no_session_explicit_nonpackage_legacy_and_original_make_ctx_shape(self):
        for session in (None, self.session):
            sandbox = self.sandbox if session is None else type(self.sandbox)(
                "/usr/bin/true", manifest="/usr/bin/true")
            with patch.object(prepared, "prepare_linux_step") as opening, \
                    patch.object(runner, "_run_agent", return_value=LoopResult(False, "budget_exceeded")) as run:
                report = self.invoke(workspace_session=session, sandbox=sandbox)
            opening.assert_not_called()
            self.assertNotIn("prepared_step", run.call_args.kwargs)
            self.assertNotIn("prepared_attempt", run.call_args.kwargs)
        old = dict(root=self.root, sandbox=self.sandbox, policy=self.policy,
            artifact_broker=None, change_baseline=None, read_only_workspace=False,
            review_submission_enabled=False, deny_read_roots=(), allowed_read_files=None,
            workspace_session=self.session)
        for view, attempt in ((None, None), (object(), "old-attempt"), (None, "")):
            with patch.object(runner, "ToolContext") as constructor:
                runner._make_ctx(self.root, self.sandbox, self.policy,
                    workspace_session=self.session, prepared_step=view, prepared_attempt=attempt)
            expected = dict(old)
            if view is not None or attempt is not None:
                expected.update(prepared_step=view, prepared_attempt=attempt)
            self.assertEqual(constructor.call_args.kwargs, expected)
        ctx = ToolContext(self.root, sandbox=None, policy=None)
        with patch.object(runner, "_run_unittest_with_bounded_output",
                return_value=(0, b"Ran 1 test in 0.01s\n\nOK\n", b"")):
            self.assertEqual(_execute_check(self.plan.checks[0], ctx, None).status, "passed")

    def test_silent_finish_external_bound_is_unknown_and_first_cleanup_signal_survives(self):
        scope = self.resources.prepare()
        with self.transport(), patch.object(prepared._LinuxStepAttachment, "finish", return_value=None):
            report = self.invoke(self.script(commands=0), prepared_scope=scope)
        self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
        self.assertEqual(scope._consume_state, "attached_bound")
        self.assertEqual(scope._owner_state, "active")
        self.no_terminal()
        for signal in (KeyboardInterrupt("cleanup-first"), SystemExit(4)):
            case = type(self)(methodName="runTest")
            case.setUp()
            try:
                with case.transport(), patch.object(prepared._LinuxStepAttachment, "finish",
                        side_effect=signal):
                    with case.assertRaises(type(signal)) as caught:
                        case.invoke(case.script(commands=0))
                case.assertIs(caught.exception, signal)
                case.owner_closed()
                case.no_terminal()
            finally:
                case.doCleanups()

    def test_actual_resume_reads_cp_checkpoint_without_prepared_restore_or_start(self):
        self.require_private()
        from icode.checkpoint import Checkpointer
        def post(*args):
            raise OSError("ordinary interrupted fixture")
        with self.transport():
            report = self.invoke(self.script(commands=0), post_write=post)
        attempt = self.opened_attempt()
        checkpoint = Checkpointer(self.out, ticket_id=self.ticket, step=self.step, attempt=attempt)
        self.assertTrue(checkpoint.exists())
        saved = json.loads(checkpoint.path.read_text(encoding="utf-8"))
        self.assertNotIn("prepared_scope", saved)
        self.assertNotIn("prepared_step", saved)
        self.assertNotIn("prepared_attempt", saved)
        self.assertEqual(self.views[0]._scope._consume_state, "spent")
        original = runner._run_agent
        with patch.object(prepared, "prepare_linux_step") as opening, \
                patch.object(ControlPlane, "_step_start_result") as start, \
                patch.object(runner, "_make_prepared_ctx") as prepared_ctx, \
                patch.object(runner, "_run_agent", wraps=original) as resumed:
            runner.resume_contract_step(self.settings, backend=self.script(commands=0),
                out_dir=self.out, step=self.step, ticket_id=self.ticket, workspace=self.root,
                sandbox=self.sandbox, policy=self.policy, workspace_session=self.session)
        opening.assert_not_called()
        start.assert_not_called()
        prepared_ctx.assert_not_called()
        self.assertTrue(resumed.call_args_list)
        self.assertNotIn("prepared_step", resumed.call_args.kwargs)
        self.assertNotIn("prepared_attempt", resumed.call_args.kwargs)
        self.assertEqual(len(self.events("step_started")), 1)

    def test_pure_admission_reviewer_resume_readyfalse_never_claim_rw_scope(self):
        self.make_ticket("code")
        scope = self.resources.prepare()
        with patch.object(prepared, "prepare_linux_step") as opening, \
                patch.object(scope, "_attach") as attaching:
            self.assertEqual(runner._contract_plan_error(self.plan, self.root, self.step,
                self.ticket, self.policy, self.sandbox, self.session), "")
        opening.assert_not_called()
        attaching.assert_not_called()
        self.assertEqual(scope._consume_state, "prepared")
        self.assertNotIn("prepared_scope", inspect.signature(runner.resume_contract_step).parameters)
        from icode.autonomy import ExecutionContext, NativeChainExecutor
        backend = FakeBackend(["must not run"])
        provider = Mock(return_value=self.plan)
        executor = NativeChainExecutor(self.settings, backend=backend, sandbox=self.sandbox,
            verification_plan_provider=provider)
        context = ExecutionContext(self.ticket, self.out, self.root, "fixture",
            self.cp.trace(self.out).data["status"], ())
        control = SimpleNamespace(session=self.session, ticket_id=self.ticket,
            run_id=self.session.run_id, safe_point=lambda step: None)
        with patch.object(executor, "_step_runner") as step_runner, \
                patch.object(ControlPlane, "_step_start_result") as start, \
                patch.object(prepared, "prepare_linux_step") as opening:
            result = executor.execute(context, control)
        self.assertFalse(self.sandbox.policy_contract_ready)
        self.assertEqual(result.state, "blocked")
        self.assertEqual(result.error_code, "isolation_unavailable")
        provider.assert_not_called()
        step_runner.assert_not_called()
        start.assert_not_called()
        opening.assert_not_called()
        self.assertEqual(backend.calls, [])

    def test_nonlinux_legacy_runner_callable_and_unresolved_candidate_never_fallback(self):
        for platform in ("darwin", "win32"):
            with self.subTest(platform=platform):
                self.make_ticket("plan")
                with patch.object(sys, "platform", platform), \
                        patch.object(prepared, "prepare_linux_step") as opening, \
                        patch.object(runner, "_run_agent", return_value=LoopResult(
                            False, "budget_exceeded")) as run:
                    report = self.invoke()
                self.assertEqual(report.finish_outcome, "failure", report.error)
                opening.assert_not_called()
                self.assertNotIn("prepared_step", run.call_args.kwargs)
                self.assertNotIn("prepared_attempt", run.call_args.kwargs)
        self.make_ticket("plan")
        missing = self.resources.binary.with_name("isolated-helper-moved")
        self.resources.binary.rename(missing)
        try:
            backend = self.script()
            with patch.object(ControlPlane, "_step_start_result") as raw, \
                    patch.object(ControlPlane, "step_start") as public, \
                    patch.object(prepared, "prepare_linux_step") as opening, \
                    patch.object(runner, "_run_agent") as run:
                report = self.invoke(backend)
            self.assertFalse(report.ok)
            self.assertIn("Linux prepared step is unavailable", report.error)
            for spy in (raw, public, opening, run):
                spy.assert_not_called()
            self.assertEqual(backend.calls, [])
        finally:
            missing.rename(self.resources.binary)

    def test_actual_candidate_factory_failure_no_start_model_legacy_or_replacement_owner(self):
        self.assertIn("prepared_scope", inspect.signature(runner.run_contract_step).parameters)
        backend = self.script()
        with patch.object(prepared, "open_linux_helper_object", side_effect=OSError("private factory")) as factory, \
                patch.object(ControlPlane, "_step_start_result") as raw, \
                patch.object(ControlPlane, "step_start") as public, \
                patch.object(runner, "_run_agent") as agent, \
                patch.object(builtin, "execute_policy_command") as ordinary:
            report = self.invoke(backend)
        self.assertFalse(report.ok)
        self.assertIn("Linux prepared step is unavailable", report.error)
        factory.assert_called_once()
        for spy in (raw, public, agent, ordinary):
            spy.assert_not_called()
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.events("step_started"), [])
        self.assertEqual(self.events("step_finished"), [])


if __name__ == "__main__":
    unittest.main()
