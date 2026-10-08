"""Real CLI/CP recovery boundaries with an offline backend, never KEY/model access.

NoIsolation proves object forwarding only, not kernel isolation or model quality.
Control-plane checks, receipts, checkpoint recovery and AgentLoop remain real.
"""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
import unittest
from unittest import mock

from icode import cli, runner
from icode.backends import FakeBackend, Usage
from icode.checkpoint import Checkpointer
from icode.control import ControlPlane
from icode.handshake import next_out_dir
from icode.isolation import NoIsolation
from icode.operations import OperationRecorder
from tests._support import require_skill, temp_workspace


PLAN = "# Offline recovery plan\n\nKeep the actual CP boundary checks unchanged.\n"
THINKING = "1. Preserve the artifact.\n2. Check actual receipts.\n3. Report the outcome."


class _ChargedBackend(FakeBackend):
    def complete(self, *args, **kwargs):
        result = super().complete(*args, **kwargs)
        self.last_usage = Usage(total_tokens=301, calls=1)
        return result


class _InterruptedBackend(FakeBackend):
    def __init__(self, error):
        super().__init__(["unused"])
        self.error = error

    def complete(self, *args, **kwargs):
        super().complete(*args, **kwargs)
        raise self.error


class TestCLIResumeSandbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = require_skill()

    def setUp(self):
        temporary = temp_workspace()
        self.workspace = temporary.__enter__().resolve()
        self.addCleanup(temporary.__exit__, None, None, None)
        self.cp = ControlPlane(self.settings)
        self.contexts = []
        self.closed = []

    def _ticket(self, *, complete_checks=False):
        directory = next_out_dir(self.workspace)
        ticket_id = f"CLI-RESUME-{directory.name.rsplit('_', 1)[-1]}"
        created = self.cp.create(directory, ticket_id=ticket_id,
                                 requirement="actual CLI recovery boundary", birth="plan")
        self.assertIs(created.data.get("ok"), True)
        attempt = self.cp.step_start(directory, "plan", ticket_id=ticket_id)
        self.cp.step_check(directory, "plan", attempt, "before_write", ticket_id=ticket_id)
        if complete_checks:
            (directory / "01_plan.md").write_bytes(PLAN.encode("utf-8"))
            self.cp.artifact(directory, "plan", attempt, "01_plan.md", ticket_id=ticket_id)
            self.cp.step_check(directory, "plan", attempt, "before_transition",
                               ticket_id=ticket_id, occurrence=2)
        checkpoint = Checkpointer(directory, ticket_id=ticket_id, step="plan", attempt=attempt)
        checkpoint.save(turn_index=1, tool_calls=0, history=[])
        return directory, ticket_id, checkpoint

    def _observe_context(self, original, *args, **kwargs):
        context = original(*args, **kwargs)
        self.contexts.append(context)
        close = context.close
        def close_observed():
            self.closed.append(context)
            return close()
        context.close = close_observed
        return context

    def _capture(self, callback):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            try:
                return callback(), None, output.getvalue()
            except BaseException as error:
                # Old TypeError must be a causal assertion RED, not a test error.
                return None, error, output.getvalue()

    def _cli(self, directory, backend, selected, *, budget=0, resume=True, explicit_skill=False):
        arguments = ["recover", "--ticket", str(directory), "--quiet",
                     "--backend", "fake", "--isolation", "none",
                     "--budget-tokens", str(budget)]
        if resume:
            arguments.append("--resume")
        if explicit_skill:
            arguments.extend(["--skill-root", str(self.settings.skill_root)])
        original = runner._make_ctx
        with ExitStack() as stack:
            factory = stack.enter_context(mock.patch("icode.backends.build_backend", return_value=backend))
            selector = stack.enter_context(mock.patch("icode.isolation.select_sandbox", return_value=selected))
            fallback = stack.enter_context(mock.patch.object(
                runner, "select_sandbox", side_effect=AssertionError("explicit sandbox lost")))
            stack.enter_context(mock.patch.object(runner, "_make_ctx", side_effect=lambda *a, **k:
                self._observe_context(original, *a, **k)))
            result, error, output = self._capture(lambda: cli.main(arguments))
        if factory.called:
            self.assertEqual(factory.call_args.args, ("fake",))
            self.assertIsNone(factory.call_args.kwargs["key_file"])
        fallback.assert_not_called()
        return result, error, output, factory, selector

    def _events(self, directory, kind):
        return [event for line in (directory / ".ico_events.jsonl").read_text(
            encoding="utf-8").splitlines()
            if (event := json.loads(line)).get("event_type") == kind]

    def _assert_forwarded(self, selected):
        self.assertEqual(len(self.contexts), 1)
        self.assertIs(self.contexts[0].sandbox, selected)
        self.assertEqual(self.closed, self.contexts)

    def test_real_cli_success_with_actual_required_checks_and_same_sandbox(self):
        directory, _, checkpoint = self._ticket(complete_checks=True)
        original_plan = (directory / "01_plan.md").read_bytes()
        selected = NoIsolation()
        backend = FakeBackend(["done", THINKING, THINKING, THINKING])
        result, error, _, factory, selector = self._cli(directory, backend, selected)
        self.assertIsNone(error, repr(error))
        self.assertEqual(result, 0)
        factory.assert_called_once()
        selector.assert_called_once_with("none")
        self._assert_forwarded(selected)
        self.assertEqual((directory / "01_plan.md").read_bytes(), original_plan)
        self.assertFalse(checkpoint.path.exists())
        finished = self._events(directory, "step_finished")
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["payload"]["outcome"], "success")
        self.assertFalse(self.cp.trace(directory).data["open_steps"])

    def test_real_cli_missing_boundary_check_remains_failure(self):
        directory, _, checkpoint = self._ticket()
        backend = FakeBackend([{"tool_calls": [{"id": "actual-write", "name": "write_file",
            "arguments": {"path": str(directory / "01_plan.md"), "content": PLAN}}]},
            "done", THINKING, THINKING, THINKING])
        selected = NoIsolation()
        result, error, output, _, _ = self._cli(directory, backend, selected)
        self.assertIsNone(error, repr(error))
        self.assertEqual(result, 1)
        self._assert_forwarded(selected)
        self.assertIn("边界检查", output)
        self.assertTrue(checkpoint.path.exists())
        self.assertTrue(self.cp.trace(directory).data["open_steps"])
        self.assertEqual(self._events(directory, "step_finished"), [])

    def test_direct_omitted_and_none_keep_existing_fallback(self):
        for kwargs in ({}, {"sandbox": None}):
            with self.subTest(kwargs=kwargs):
                directory, _, _ = self._ticket(complete_checks=True)
                self.contexts.clear()
                self.closed.clear()
                selected = NoIsolation()
                original = runner._make_ctx
                with mock.patch.object(runner, "select_sandbox", return_value=selected) as fallback, \
                     mock.patch.object(runner, "_make_ctx", side_effect=lambda *a, **k:
                         self._observe_context(original, *a, **k)):
                    report, error, _ = self._capture(lambda: runner.resume_contract_step(
                        self.settings, backend=FakeBackend(["done", THINKING, THINKING, THINKING]),
                        out_dir=directory, **kwargs))
                self.assertIsNone(error, repr(error))
                self.assertTrue(report.ok, report.render())
                fallback.assert_called_once_with()
                self._assert_forwarded(selected)

    def test_direct_explicit_sandbox_is_not_reselected(self):
        directory, _, _ = self._ticket(complete_checks=True)
        selected = NoIsolation()
        original = runner._make_ctx
        with mock.patch.object(runner, "select_sandbox", side_effect=AssertionError("lost sandbox")) as fallback, \
             mock.patch.object(runner, "_make_ctx", side_effect=lambda *a, **k:
                 self._observe_context(original, *a, **k)):
            report, error, _ = self._capture(lambda: runner.resume_contract_step(
                self.settings, backend=FakeBackend(["done", THINKING, THINKING, THINKING]),
                out_dir=directory, sandbox=selected))
        self.assertIsNone(error, repr(error))
        self.assertTrue(report.ok, report.render())
        fallback.assert_not_called()
        self._assert_forwarded(selected)

    def test_real_cli_301_keeps_budget_failure_and_checkpoint(self):
        directory, _, checkpoint = self._ticket()
        selected = NoIsolation()
        backend = _ChargedBackend(["actual charged response"])
        result, error, output, _, _ = self._cli(directory, backend, selected, budget=100)
        self.assertIsNone(error, repr(error))
        self.assertEqual(result, 1)
        self._assert_forwarded(selected)
        self.assertEqual(len(backend.calls), 1)
        self.assertIn("budget_exceeded", output)
        self.assertTrue(checkpoint.path.exists())
        self.assertEqual(self._events(directory, "artifact_written"), [])
        finished = self._events(directory, "step_finished")
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["payload"]["outcome"], "failure")
        self.assertTrue(finished[0]["payload"]["evidence"])
        self.assertFalse(self.cp.trace(directory).data["open_steps"])
        self.assertFalse((directory / ".thinking_gate_trace.jsonl").exists())

    def test_unknown_side_effect_outcome_blocks_before_backend_construction(self):
        for opclass in ("managed_write", "external_side_effect"):
            with self.subTest(opclass=opclass):
                directory, ticket_id, checkpoint = self._ticket()
                started = OperationRecorder(self.cp, directory, ticket_id).start(
                    name="unfinished", opclass=opclass, input_desc="fixture only; no action executed")
                self.assertTrue(started.can_execute)
                events = (directory / ".ico_events.jsonl").read_bytes()
                checkpoint_bytes = checkpoint.path.read_bytes()
                backend = FakeBackend(["must not run"])
                result, error, _, factory, selector = self._cli(directory, backend, NoIsolation())
                self.assertIsNone(error, repr(error))
                self.assertEqual(result, 1)
                factory.assert_not_called()
                selector.assert_not_called()
                self.assertEqual(backend.calls, [])
                self.assertEqual(self.contexts, [])
                self.assertEqual((directory / ".ico_events.jsonl").read_bytes(), events)
                self.assertEqual(checkpoint.path.read_bytes(), checkpoint_bytes)

    def test_real_cli_interrupts_propagate_same_object_without_false_finish(self):
        for interrupted in (KeyboardInterrupt("stop"), SystemExit(17)):
            with self.subTest(kind=type(interrupted).__name__):
                directory, _, checkpoint = self._ticket()
                self.contexts.clear()
                self.closed.clear()
                selected = NoIsolation()
                backend = _InterruptedBackend(interrupted)
                result, error, _, _, _ = self._cli(directory, backend, selected)
                self.assertIsNone(result)
                self.assertIs(error, interrupted)
                self._assert_forwarded(selected)
                self.assertEqual(len(backend.calls), 1)
                self.assertTrue(checkpoint.path.exists())
                self.assertTrue(self.cp.trace(directory).data["open_steps"])
                self.assertEqual(self._events(directory, "step_finished"), [])

    def test_analysis_only_keeps_checkpoint_without_building_backend(self):
        directory, _, checkpoint = self._ticket()
        events = (directory / ".ico_events.jsonl").read_bytes()
        checkpoint_bytes = checkpoint.path.read_bytes()
        backend = FakeBackend(["must not run"])
        result, error, _, factory, selector = self._cli(directory, backend, NoIsolation(), resume=False)
        self.assertIsNone(error, repr(error))
        self.assertEqual(result, 0)
        factory.assert_not_called()
        selector.assert_not_called()
        self.assertEqual(backend.calls, [])
        self.assertEqual((directory / ".ico_events.jsonl").read_bytes(), events)
        self.assertEqual(checkpoint.path.read_bytes(), checkpoint_bytes)

    def test_explicit_settings_uses_same_control_plane_without_rediscovery(self):
        for entry in ("omitted_sandbox_api", "explicit_sandbox_api", "explicit_skill_cli"):
            with self.subTest(entry=entry):
                directory, ticket_id, checkpoint = self._ticket(complete_checks=True)
                self.contexts.clear()
                self.closed.clear()
                selected = NoIsolation()
                backend = FakeBackend(["done", THINKING, THINKING, THINKING])
                controls, loops = [], []
                events_before = (directory / ".ico_events.jsonl").read_bytes()
                checkpoint_before = checkpoint.path.read_bytes()
                def control_observed(settings):
                    control = ControlPlane(settings)
                    controls.append(control)
                    return control
                original_loop = runner.AgentLoop
                def loop_observed(**kwargs):
                    loop = original_loop(**kwargs)
                    loops.append(loop)
                    return loop
                original_context = runner._make_ctx
                with mock.patch.object(runner, "ControlPlane", side_effect=control_observed), \
                     mock.patch.object(runner, "AgentLoop", side_effect=loop_observed), \
                     mock.patch.object(runner, "load_settings_for", side_effect=AssertionError(
                         "explicit settings must not be rediscovered")) as rediscovery:
                    if entry == "explicit_skill_cli":
                        result, error, output, _, _ = self._cli(
                            directory, backend, selected, explicit_skill=True)
                        success = result == 0
                    else:
                        kwargs = {} if entry == "omitted_sandbox_api" else {"sandbox": selected}
                        with mock.patch.object(runner, "select_sandbox", return_value=selected), \
                             mock.patch.object(runner, "_make_ctx", side_effect=lambda *a, **k:
                                 self._observe_context(original_context, *a, **k)):
                            report, error, output = self._capture(lambda: runner.resume_contract_step(
                                self.settings, backend=backend, out_dir=directory, **kwargs))
                        success = report is not None and report.ok
                        output = report.render() if report is not None else output
                if rediscovery.called:
                    self.assertEqual(backend.calls, [])
                    self.assertEqual((directory / ".ico_events.jsonl").read_bytes(), events_before)
                    self.assertEqual(checkpoint.path.read_bytes(), checkpoint_before)
                self.assertFalse(rediscovery.called, output)
                self.assertIsNone(error, repr(error))
                self.assertTrue(success, output)
                self.assertEqual(len(controls), 1)
                self.assertEqual(controls[0].settings.skill_root, self.settings.skill_root)
                self.assertEqual(len(loops), 1)
                recorder = loops[0].operations
                self.assertIsInstance(recorder, OperationRecorder)
                self.assertIs(recorder.control, controls[0])
                self.assertEqual(recorder.out_dir, directory)
                self.assertEqual(recorder.ticket_id, ticket_id)
                self.assertEqual(recorder.scope, "", "keep legacy operation request-key scope")
                self._assert_forwarded(selected)
                self.assertFalse(checkpoint.path.exists())
                self.assertEqual(self._events(directory, "step_finished")[0]["payload"]["outcome"], "success")


if __name__ == "__main__":
    unittest.main()
