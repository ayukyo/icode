"""Single-process budget ownership; offline usage is not model-quality evidence.

CP/AgentLoop/chain receipts are real. The policy adapter used by the native
executor test supplies no kernel isolation evidence and never launches commands.
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

from icode import autonomy, chain, runner
from icode.backends import FakeBackend, Usage
from icode.budget import Budget, BudgetTracker
from icode.checkpoint import CHECKPOINT_NAME, Checkpointer
from icode.control import ControlPlane
from icode.handshake import next_out_dir
from icode.isolation import NoIsolation
from icode.reasoning import ReasoningGate, read_trace, run_deliberation
from icode.sequential import Deliberation, SequentialThinking
from tests._support import require_skill, temp_workspace


PLAN = "# Actual plan\n\nKeep real control-plane checks and honest budget boundaries.\n"


def thought(more=False):
    return json.dumps({"step": "Check the actual boundary", "next_thought_needed": more})


class MeteredBackend(FakeBackend):
    def __init__(self, rows):
        super().__init__([response for response, _ in rows])
        self.charges = [charge for _, charge in rows]
        self.usage = Usage(total_tokens=99999, calls=999)

    def complete(self, *args, **kwargs):
        charge = self.charges[min(self._index, len(self.charges) - 1)]
        result = super().complete(*args, **kwargs)
        self.last_usage = None if charge is None else (
            charge if isinstance(charge, Usage) else Usage(total_tokens=charge, calls=1))
        return result


def write_plan(directory):
    return {"tool_calls": [{"id": "actual-plan", "name": "write_file",
            "arguments": {"path": str(directory / "01_plan.md"), "content": PLAN}}]}


def events(directory, kind):
    return [event for line in (directory / ".ico_events.jsonl").read_text(
        encoding="utf-8").splitlines()
        if (event := json.loads(line)).get("event_type") == kind]


class TestSharedRuntimeBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = require_skill()
        cls.gate = ReasoningGate.load(cls.settings.skill_root / "mcp/reasoning-gate/gates.json")

    def setUp(self):
        temporary = temp_workspace()
        self.workspace = temporary.__enter__().resolve()
        self.addCleanup(temporary.__exit__, None, None, None)
        self.directory = next_out_dir(self.workspace)
        self.ticket_id = "SHARED-BUDGET-1"
        self.cp = ControlPlane(self.settings)
        self.cp.create(self.directory, ticket_id=self.ticket_id,
                       requirement="actual shared runtime budget", birth="plan")

    def _run(self, backend, **kwargs):
        try:
            return runner.run_contract_step(self.settings, backend=backend,
                workspace=self.workspace, out_dir=self.directory, ticket_id=self.ticket_id,
                sandbox=NoIsolation(), budget=Budget(expected_tokens=100), **kwargs)
        except TypeError as error:
            self.fail(f"shared contract owner unsupported: {error!r}")

    def _failure(self, report, backend, calls, *, checkpoint_expected=True):
        self.assertFalse(report.ok)
        self.assertIn("budget_exceeded", report.error)
        self.assertEqual(len(backend.calls), calls)
        self.assertEqual((self.directory / CHECKPOINT_NAME).exists(), checkpoint_expected)
        self.assertEqual(report.finish_outcome, "failure")
        finished = events(self.directory, "step_finished")
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["payload"]["outcome"], "failure")
        self.assertTrue(finished[0]["payload"]["evidence"])
        self.assertEqual(self.cp.trace(self.directory).data["status"], "init_in_progress")
        self.assertFalse(events(self.directory, "state_changed"))
        self.assertFalse((self.directory / ".thinking_gate_trace.jsonl").exists())

    def test_real_initial_and_repair_100_plus_201_stops_before_persist(self):
        backend = MeteredBackend([("initial reply", 100), (PLAN, 201), (thought(), 0)])
        post = mock.Mock()
        report = self._run(backend, post_write=post)
        self._failure(report, backend, 2)
        self.assertEqual(report.loop.usage.total_tokens, 301)
        self.assertEqual(report.loop.stop_reason, "budget_exceeded")
        post.assert_called_once()
        self.assertFalse((self.directory / "01_plan.md").exists())
        self.assertEqual(events(self.directory, "artifact_written"), [])

    def test_real_deliberation_overrun_precedes_success_finish(self):
        backend = MeteredBackend([(write_plan(self.directory), 100), ("done", 0),
                                  (thought(), 201), (thought(), 0)])
        report = self._run(backend)
        self._failure(report, backend, 3)
        self.assertEqual(report.loop.usage.total_tokens, 100, "loop is a pre-deliberation snapshot")
        self.assertEqual((self.directory / "01_plan.md").read_bytes(), PLAN.encode())
        self.assertEqual(len(events(self.directory, "artifact_written")), 1)

    def test_fourth_deliberation_overrun_cannot_use_three_prior_steps_as_success(self):
        backend = MeteredBackend([(write_plan(self.directory), 100), ("done", 0),
                                  (thought(True), 40), (thought(True), 40),
                                  (thought(True), 40), (thought(), 81)])
        report = self._run(backend)
        self._failure(report, backend, 6)

    def test_real_chain_accumulates_plan_then_review_and_does_not_start_merge(self):
        backend = MeteredBackend([(write_plan(self.directory), 10), ("done", 0),
                                  (thought(), 90), (thought(), 90), (thought(), 90),
                                  ("review stop", 21), ("must not run", 0)])
        report = chain.run_chain(self.settings, backend=backend, workspace=self.workspace,
            requirement="actual shared chain", ticket_id=self.ticket_id, out_dir=self.directory,
            steps=("plan", "review", "merge"), budget=Budget(expected_tokens=100), sandbox=NoIsolation())
        self.assertEqual(report.stopped_at, "review", report.render())
        self.assertIn("budget_exceeded", report.steps[-1].error)
        self.assertEqual(len(backend.calls), 6)
        self.assertEqual(report.steps[0].finish_outcome, "success")
        self.assertEqual(report.steps[0].loop.usage.total_tokens, 10)
        self.assertEqual(report.steps[1].loop.usage.total_tokens, 301)
        self.assertEqual([event["payload"]["step"] for event in events(self.directory, "step_started")],
                         ["plan", "review"])
        self.assertEqual([event["payload"]["outcome"] for event in events(self.directory, "step_finished")],
                         ["success", "failure"])

    def test_build_row_never_promotes_observed_budget_stop(self):
        result = Deliberation(tier="L2", steps=["one", "two", "three"])
        result.budget_exceeded = True
        row = self.gate.build_row(self.ticket_id, "plan", deliberation=result)
        self.assertNotEqual(row.result, "success")

    def test_real_native_executor_accumulates_its_separate_chain_calls(self):
        from tests.test_autonomy import RecordingControl, _attach_verified_test_session
        context = autonomy.ExecutionContext(ticket_id=self.ticket_id, out_dir=self.directory,
            workspace=self.workspace, requirement="real native executor budget",
            status="init_in_progress", completed_steps=())
        control = RecordingControl()
        sandbox = _attach_verified_test_session(control, context)
        # This adapter is fixture authority only; forbid all command execution.
        sandbox.wrap_policy = mock.Mock(side_effect=AssertionError("no commands in budget fixture"))
        submit = {"tool_calls": [{"id": "actual-submit", "name": "submit_artifact",
                  "arguments": {"name": "01_plan.md", "content": PLAN}}]}
        backend = MeteredBackend([(submit, 10), ("done", 0), (thought(), 90),
                                  (thought(), 90), (thought(), 90), ("review stop", 21)])
        executor = autonomy.NativeChainExecutor(self.settings, backend=backend,
            budget=Budget(expected_tokens=100), sandbox=sandbox)
        actual_step = chain.run_contract_step
        reports = []
        def observe(*args, **kwargs):
            report = actual_step(*args, **kwargs)
            reports.append(report)
            return report
        with mock.patch.object(chain, "run_contract_step", side_effect=observe):
            result = executor.execute(context, control)
        self.assertEqual(result.last_step, "review", reports[0].render())
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[0].finish_outcome, "success")
        self.assertIn("budget_exceeded", reports[1].error)
        self.assertEqual(reports[1].loop.usage.total_tokens, 301)
        self.assertEqual(len(backend.calls), 6)
        sandbox.wrap_policy.assert_not_called()

    def test_conflicting_budget_rejected_before_any_cp_write_or_model(self):
        for entry in (runner.run_contract_step, runner.resume_contract_step, chain.run_chain):
            with self.subTest(entry=entry.__name__):
                before = (self.directory / ".ico_events.jsonl").read_bytes()
                backend = MeteredBackend([("must not run", 0)])
                kwargs = dict(backend=backend, out_dir=self.directory,
                    budget=Budget(expected_tokens=100), budget_tracker=BudgetTracker(Budget(expected_tokens=101)))
                if entry is not runner.resume_contract_step:
                    kwargs.update(workspace=self.workspace, ticket_id=self.ticket_id)
                if entry is chain.run_chain:
                    kwargs["requirement"] = "conflict"
                try:
                    entry(self.settings, **kwargs)
                except Exception as error:
                    observed = error
                else:
                    observed = None
                self.assertEqual(backend.calls, [])
                self.assertEqual((self.directory / ".ico_events.jsonl").read_bytes(), before)
                self.assertIsInstance(observed, ValueError, repr(observed))

    def test_resume_deliberation_reuses_owner_and_never_early_finishes(self):
        attempt = self.cp.step_start(self.directory, "plan", ticket_id=self.ticket_id)
        self.cp.step_check(self.directory, "plan", attempt, "before_write", ticket_id=self.ticket_id)
        (self.directory / "01_plan.md").write_bytes(PLAN.encode())
        self.cp.artifact(self.directory, "plan", attempt, "01_plan.md", ticket_id=self.ticket_id)
        self.cp.step_check(self.directory, "plan", attempt, "before_transition",
                           ticket_id=self.ticket_id, occurrence=2)
        checkpoint = Checkpointer(self.directory, ticket_id=self.ticket_id, step="plan", attempt=attempt)
        checkpoint.save(turn_index=1, tool_calls=0, history=[])
        backend = MeteredBackend([("done", 100), (thought(), 201)])
        owner = BudgetTracker(Budget(expected_tokens=100))
        try:
            report = runner.resume_contract_step(self.settings, backend=backend, out_dir=self.directory,
                budget_tracker=owner, sandbox=NoIsolation())
        except TypeError as error:
            self.fail(f"shared resume owner unsupported: {error!r}")
        self._failure(report, backend, 2)
        self.assertEqual(owner.usage.total_tokens, 301)
        self.assertEqual(report.loop.usage.total_tokens, 100)

    def test_compatible_budget_finalizes_once_with_immutable_loop_snapshot(self):
        owner = BudgetTracker(Budget(expected_tokens=100))
        backend = MeteredBackend([(write_plan(self.directory), 100), ("done", 0)] + [(thought(), 50)] * 3)
        with mock.patch.object(runner, "run_deliberation", wraps=runner.run_deliberation) as reasoning:
            report = self._run(backend, budget_tracker=owner)
        self.assertTrue(report.ok, report.render())
        self.assertEqual(report.finish_outcome, "success")
        self.assertEqual(len(backend.calls), 5)
        reasoning.assert_called_once()
        self.assertEqual(owner.usage.total_tokens, 250)
        self.assertEqual(report.loop.usage.total_tokens, 100)
        self.assertEqual(len(read_trace(self.directory / ".thinking_gate_trace.jsonl")), 1)
        self.assertFalse((self.directory / CHECKPOINT_NAME).exists())

    def test_existing_over_budget_owner_stops_before_first_model(self):
        owner = BudgetTracker(Budget(expected_tokens=100), Usage(total_tokens=301))
        backend = MeteredBackend([("must not run", 0)])
        report = self._run(backend, budget_tracker=owner)
        self._failure(report, backend, 0, checkpoint_expected=False)
        self.assertEqual(report.loop.stop_reason, "budget_exceeded")

    def test_independent_contract_calls_do_not_share_a_budget(self):
        backend = MeteredBackend([(write_plan(self.directory), 100), ("done", 0)] + [(thought(), 50)] * 3)
        first = self._run(backend)
        second_directory = next_out_dir(self.workspace)
        self.cp.create(second_directory, ticket_id="SHARED-BUDGET-2",
                       requirement="independent runtime budget", birth="plan")
        second_backend = MeteredBackend([(write_plan(second_directory), 100), ("done", 0)] + [(thought(), 50)] * 3)
        second = runner.run_contract_step(self.settings, backend=second_backend, workspace=self.workspace,
            out_dir=second_directory, ticket_id="SHARED-BUDGET-2", budget=Budget(expected_tokens=100),
            sandbox=NoIsolation())
        self.assertTrue(first.ok, first.render())
        self.assertTrue(second.ok, second.render())

    def test_native_execute_owner_is_local_and_separate_tickets_do_not_share(self):
        from tests.test_autonomy import RecordingControl, _attach_verified_test_session
        submit = {"tool_calls": [{"id": "actual-submit", "name": "submit_artifact",
                  "arguments": {"name": "01_plan.md", "content": PLAN}}]}
        script = [(submit, 10), ("done", 0)] + [(thought(), 90)] * 3 + [("review stop", 21)]
        backend = MeteredBackend(script * 2)
        first_context = autonomy.ExecutionContext(ticket_id=self.ticket_id, out_dir=self.directory,
            workspace=self.workspace, requirement="first execute", status="init_in_progress", completed_steps=())
        first_control = RecordingControl()
        sandbox = _attach_verified_test_session(first_control, first_context)
        sandbox.wrap_policy = mock.Mock(side_effect=AssertionError("no command execution"))
        executor = autonomy.NativeChainExecutor(self.settings, backend=backend,
            budget=Budget(expected_tokens=100), sandbox=sandbox)
        actual_step = chain.run_contract_step
        owners = []
        def observe(*args, **kwargs):
            owners.append(kwargs.get("budget_tracker"))
            return actual_step(*args, **kwargs)
        with mock.patch.object(chain, "run_contract_step", side_effect=observe):
            first = executor.execute(first_context, first_control)
            second_directory = next_out_dir(self.workspace)
            self.cp.create(second_directory, ticket_id="SHARED-BUDGET-2",
                           requirement="second execute", birth="plan")
            second_context = autonomy.ExecutionContext(ticket_id="SHARED-BUDGET-2", out_dir=second_directory,
                workspace=self.workspace, requirement="second execute", status="init_in_progress", completed_steps=())
            second_control = RecordingControl()
            _attach_verified_test_session(second_control, second_context)
            second = executor.execute(second_context, second_control)
        self.assertEqual(first.last_step, "review")
        self.assertEqual(second.last_step, "review")
        self.assertEqual(len(backend.calls), 12)
        self.assertEqual(len(owners), 4)
        self.assertIsInstance(owners[0], BudgetTracker)
        self.assertIs(owners[0], owners[1])
        self.assertIs(owners[2], owners[3])
        self.assertIsNot(owners[0], owners[2])
        self.assertEqual([owner.usage.total_tokens for owner in (owners[0], owners[2])], [301, 301])
        self.assertFalse(any(isinstance(value, BudgetTracker) for value in vars(executor).values()))

    def test_custom_runner_keeps_signature_and_typeerror_is_not_retried(self):
        from tests.test_autonomy import RecordingControl, _attach_verified_test_session
        context = autonomy.ExecutionContext(ticket_id=self.ticket_id, out_dir=self.directory,
            workspace=self.workspace, requirement="custom adapter compatibility",
            status="init_in_progress", completed_steps=())
        control = RecordingControl()
        sandbox = _attach_verified_test_session(control, context)
        calls = []
        def custom(settings, *, backend, workspace, requirement, ticket_id, steps,
                   out_dir, approver, loop_config, budget, on_event, sandbox, policy):
            calls.append(steps)
            raise TypeError("custom adapter failure after entry")
        executor = autonomy.NativeChainExecutor(self.settings, backend=FakeBackend(),
            step_runner=custom, budget=Budget(expected_tokens=100), sandbox=sandbox)
        result = executor.execute(context, control)
        self.assertEqual(calls, [("plan",)])
        self.assertEqual(result.error_code, "chain_error")


class TestBudgetedSequential(unittest.TestCase):
    def _run(self, backend, owner):
        try:
            result = SequentialThinking(backend).run("actual usage", budget_tracker=owner)
        except Exception as error:
            self.fail(f"shared owner unsupported: {error!r}")
        return result

    def test_response_usage_once_and_reasoning_not_double_counted(self):
        owner = BudgetTracker(Budget(expected_tokens=100))
        backend = MeteredBackend([(thought(), 10), (thought(), 20),
                                  (thought(), Usage(total_tokens=30, reasoning_tokens=20))])
        result = self._run(backend, owner)
        self.assertEqual(result.step_count, 3)
        self.assertEqual(owner.usage.total_tokens, 60)
        self.assertEqual(owner.usage.reasoning_tokens, 20)
        self.assertEqual(owner.usage.calls, 3)
        self.assertFalse(result.budget_exceeded)

    def test_charge_gate_precedes_parsing_over_budget_response(self):
        owner = BudgetTracker(Budget(expected_tokens=100))
        backend = MeteredBackend([(thought(), 301)])
        with mock.patch.object(SequentialThinking, "_parse", wraps=SequentialThinking._parse) as parse:
            result = self._run(backend, owner)
        self.assertTrue(result.budget_exceeded)
        self.assertEqual(result.steps, [])
        self.assertEqual(owner.usage.total_tokens, 301)
        self.assertEqual(len(backend.calls), 1)
        parse.assert_not_called()

    def test_existing_over_budget_owner_never_calls_backend(self):
        owner = BudgetTracker(Budget(expected_tokens=100), Usage(total_tokens=301))
        backend = MeteredBackend([(thought(), 0)])
        result = self._run(backend, owner)
        self.assertTrue(result.budget_exceeded)
        self.assertEqual(backend.calls, [])

    def test_300_observe_and_missing_usage_keep_existing_behavior(self):
        for budget, charge, expected in ((100, 100, 300), (0, 1000, 3000), (100, None, 0)):
            with self.subTest(budget=budget, charge=charge):
                owner = BudgetTracker(Budget(expected_tokens=budget))
                result = self._run(MeteredBackend([(thought(), charge)] * 3), owner)
                self.assertEqual(result.step_count, 3)
                self.assertFalse(result.budget_exceeded)
                self.assertEqual(owner.usage.total_tokens, expected)

    def test_backend_exception_is_not_charged_and_interrupts_propagate(self):
        for error in (RuntimeError("backend failure"), KeyboardInterrupt("stop"), SystemExit(17)):
            with self.subTest(kind=type(error).__name__):
                backend = MeteredBackend([(thought(), 301)])
                original = backend.complete
                def fail(*args, **kwargs):
                    original(*args, **kwargs)
                    raise error
                backend.complete = fail
                owner = BudgetTracker(Budget(expected_tokens=100))
                if isinstance(error, Exception):
                    result = self._run(backend, owner)
                    self.assertIn("RuntimeError", result.error)
                    self.assertFalse(result.budget_exceeded)
                else:
                    try:
                        SequentialThinking(backend).run("interrupt", budget_tracker=owner)
                    except BaseException as observed:
                        self.assertIs(observed, error)
                    else:
                        self.fail("interrupt was swallowed")
                self.assertEqual(owner.usage.total_tokens, 0)
                self.assertEqual(len(backend.calls), 1)

    def test_unrequired_and_unsupported_tiers_do_not_invoke_backend(self):
        gate = ReasoningGate({"steps": {"status": {"default_tier": "L0", "requires_trace": False},
                                      "audit": {"default_tier": "L3", "requires_trace": True}}})
        for step in ("status", "audit", "missing"):
            with self.subTest(step=step):
                backend = MeteredBackend([(thought(), 301)])
                owner = BudgetTracker(Budget(expected_tokens=100))
                try:
                    result = run_deliberation(gate, backend, step=step,
                        question="no supported reasoning", budget_tracker=owner)
                except TypeError as error:
                    self.fail(f"shared deliberation owner unsupported: {error!r}")
                self.assertIsNone(result)
                self.assertEqual(backend.calls, [])
                self.assertEqual(owner.usage.total_tokens, 0)


if __name__ == "__main__":
    unittest.main()
