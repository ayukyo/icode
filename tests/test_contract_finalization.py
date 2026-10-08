"""Actual CP finalization ordering; offline models do not prove isolation quality."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from icode import runner
from icode.backends import FakeBackend
from icode.checkpoint import Checkpointer
from icode.chain import run_chain
from icode.control import ControlPlane, ControlResult
from icode.contracts import ContractSet
from icode.handshake import next_out_dir
from icode.isolation import NoIsolation
from icode.loop import LoopConfig
from icode.reasoning import ReasoningGate
from tests._support import require_skill, temp_workspace

PLAN = "# Plan\n\nPreserve failed receipts and checkpoints.\n"
THINKING = json.dumps({"step": "Check the actual artifact and receipt.",
                       "next_thought_needed": False})


class TestContractFinalization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = require_skill()

    def _events(self, directory, kind):
        events = [json.loads(line) for line in (directory / ".ico_events.jsonl").read_text(
            encoding="utf-8").splitlines()]
        return [event for event in events if event["event_type"] == kind]

    def _script(self, directory, *, reasoning=True):
        return [{"tool_calls": [{"id": "write-plan", "name": "write_file",
            "arguments": {"path": str(directory / "01_plan.md"), "content": PLAN}}]},
            "done", *([THINKING] * 3 if reasoning else [""])]

    def _resume_ticket(self, workspace, *, complete_checks):
        directory = next_out_dir(workspace)
        ticket_id = "FINAL-RESUME"
        cp = ControlPlane(self.settings)
        cp.create(directory, ticket_id=ticket_id, requirement="finalization", birth="plan")
        attempt = cp.step_start(directory, "plan", ticket_id=ticket_id)
        cp.step_check(directory, "plan", attempt, "before_write", ticket_id=ticket_id)
        (directory / "01_plan.md").write_text(PLAN, encoding="utf-8")
        cp.artifact(directory, "plan", attempt, "01_plan.md", ticket_id=ticket_id)
        if complete_checks:
            cp.step_check(directory, "plan", attempt, "before_transition",
                          ticket_id=ticket_id, occurrence=2)
        checkpoint = Checkpointer(directory, ticket_id=ticket_id, step="plan", attempt=attempt)
        checkpoint.save(turn_index=1, tool_calls=0, history=[])
        return directory, checkpoint, cp

    def test_actual_empty_reasoning_cannot_finish_success_or_clear_checkpoint(self):
        with temp_workspace() as workspace:
            directory = next_out_dir(workspace)
            cp = ControlPlane(self.settings)
            cp.create(directory, ticket_id="FINAL-EMPTY", requirement="finalization", birth="plan")
            original_transition = ControlPlane.transition
            with patch.object(ControlPlane, "transition", autospec=True,
                              side_effect=original_transition) as transition:
                report = runner.run_contract_step(self.settings,
                    backend=FakeBackend(self._script(directory, reasoning=False)),
                    workspace=workspace, out_dir=directory, ticket_id="FINAL-EMPTY",
                    sandbox=NoIsolation())
            self.assertFalse(report.ok, report.render())
            self.assertEqual(report.finish_outcome, "failure", report.render())
            self.assertTrue(Path(report.checkpoint_path).exists())
            self.assertEqual([e["payload"]["outcome"] for e in self._events(
                directory, "step_finished")], ["failure"])
            transition.assert_not_called()
            self.assertFalse(cp.trace(directory).data["open_steps"])
            rows = (directory / ".thinking_gate_trace.jsonl").read_text(
                encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0])["result"], "degraded")

    def test_actual_resume_rejected_finish_never_attempts_transition(self):
        with temp_workspace() as workspace:
            directory, checkpoint, cp = self._resume_ticket(workspace, complete_checks=False)
            original_transition = ControlPlane.transition
            with patch.object(ControlPlane, "transition", autospec=True,
                              side_effect=original_transition) as transition:
                report = runner.resume_contract_step(self.settings,
                    backend=FakeBackend(["done", THINKING, THINKING, THINKING]),
                    out_dir=directory, sandbox=NoIsolation())
            self.assertFalse(report.ok, report.render())
            self.assertEqual(report.finish_outcome, "")
            self.assertTrue(checkpoint.path.exists())
            self.assertTrue(cp.trace(directory).data["open_steps"])
            self.assertEqual(self._events(directory, "step_finished"), [])
            transition.assert_not_called()

    def test_actual_resume_empty_reasoning_preserves_checkpoint(self):
        with temp_workspace() as workspace:
            directory, checkpoint, cp = self._resume_ticket(workspace, complete_checks=True)
            original_transition = ControlPlane.transition
            with patch.object(ControlPlane, "transition", autospec=True,
                              side_effect=original_transition) as transition:
                report = runner.resume_contract_step(self.settings,
                    backend=FakeBackend(["done", ""]), out_dir=directory,
                    sandbox=NoIsolation())
            self.assertFalse(report.ok, report.render())
            self.assertEqual(report.finish_outcome, "failure")
            self.assertTrue(checkpoint.path.exists())
            self.assertEqual([e["payload"]["outcome"] for e in self._events(
                directory, "step_finished")], ["failure"])
            transition.assert_not_called()
            self.assertFalse(cp.trace(directory).data["open_steps"])

    def test_actual_success_records_reasoning_before_finish_once(self):
        with temp_workspace() as workspace:
            directory = next_out_dir(workspace)
            cp = ControlPlane(self.settings)
            cp.create(directory, ticket_id="FINAL-SUCCESS", requirement="finalization", birth="plan")
            observed = []
            original_finish = ControlPlane.step_finish

            def finish(control, *args, **kwargs):
                path = directory / ".thinking_gate_trace.jsonl"
                observed.append(path.read_text(encoding="utf-8").splitlines()
                                if path.is_file() else [])
                return original_finish(control, *args, **kwargs)

            with patch.object(ControlPlane, "step_finish", autospec=True, side_effect=finish):
                report = runner.run_contract_step(self.settings,
                    backend=FakeBackend(self._script(directory)), workspace=workspace,
                    out_dir=directory, ticket_id="FINAL-SUCCESS", sandbox=NoIsolation())
            self.assertTrue(report.ok, report.render())
            self.assertEqual(report.finish_outcome, "success")
            self.assertFalse(Path(report.checkpoint_path).exists())
            self.assertEqual(len(observed), 1)
            self.assertEqual(len(observed[0]), 1)
            self.assertEqual(json.loads(observed[0][0])["result"], "success")
            self.assertEqual(len(report.reasoning_rows), 1)
            self.assertEqual(len((directory / ".thinking_gate_trace.jsonl").read_text(
                encoding="utf-8").splitlines()), 1)

    def test_transport_refusal_or_wrong_outcome_never_confirms_finish(self):
        for rc, ok, outcome in ((1, True, "success"), (0, False, "success"),
                                (0, True, "failure"), (0, True, "")):
            with self.subTest(rc=rc, ok=ok, outcome=outcome):
                cp = Mock()
                cp.step_finish.return_value = ControlResult((), rc, {
                    "ok": ok, "outcome": outcome, "step": "plan", "attempt": "attempt"})
                report = runner.StepReport(step="plan", ok=False, out_dir="unused")
                runner._finish_step(cp, Path("unused"), "plan", "attempt", "ticket", report, [])
                self.assertEqual(report.finish_outcome, "")
                self.assertTrue(any(not passed for _, passed, _ in report.checkpoints))

    def test_existing_failed_checkpoint_or_error_requests_failure(self):
        for error in (False, True):
            with self.subTest(error=error):
                cp = Mock()
                def finish(*args, **kwargs):
                    return ControlResult((), 0, {"ok": True, "outcome": args[3],
                                                "step": args[1], "attempt": args[2]})
                cp.step_finish.side_effect = finish
                report = runner.StepReport(step="plan", ok=False, out_dir="unused")
                if error:
                    report.error = "actual earlier error"
                else:
                    report.add("actual earlier check", False)
                runner._finish_step(cp, Path("unused"), "plan", "attempt", "ticket", report, [])
                self.assertEqual(cp.step_finish.call_args.args[3], "failure")
                self.assertEqual(report.finish_outcome, "failure")

    def test_transport_foreign_or_missing_identity_never_confirms_finish(self):
        for identity in ({"step": "review", "attempt": "attempt"},
                         {"step": "plan", "attempt": "foreign"},
                         {"step": "plan"}, {"attempt": "attempt"}):
            with self.subTest(identity=identity):
                cp = Mock()
                cp.step_finish.return_value = ControlResult((), 0, {
                    "ok": True, "outcome": "success", **identity})
                report = runner.StepReport(step="plan", ok=False, out_dir="unused")
                runner._finish_step(cp, Path("unused"), "plan", "attempt", "ticket", report, [])
                self.assertEqual(report.finish_outcome, "")
                self.assertTrue(any(not passed for _, passed, _ in report.checkpoints))

    def test_metadata_failure_prevents_transition_but_trace_is_still_observed(self):
        cp = Mock()
        cp.transition.return_value = ControlResult((), 0, {"ok": True})
        cp.trace.return_value = ControlResult((), 0, {"ok": True, "open_steps": {},
                                                    "open_operations": {}})
        report = runner.StepReport(step="plan", ok=False, out_dir="unused",
                                   finish_outcome="success")
        def metadata(*args):
            args[-1].add("actual metadata refusal", False)
        with patch.object(runner, "_ensure_gate_metadata", side_effect=metadata):
            runner._finalize(self.settings, cp, Path("unused"), "plan", "ticket",
                             ContractSet.load(self.settings.gates_json), report)
        self.assertFalse(report.ok)
        cp.transition.assert_not_called()
        cp.trace.assert_called_once()

    def test_finish_exception_does_not_hide_trace_or_replace_existing_failure(self):
        cp = Mock()
        cp.step_finish.side_effect = OSError("PRIVATE_FINISH")
        cp.trace.return_value = ControlResult((), 0, {"ok": True, "open_steps": {"attempt": {}},
                                                    "open_operations": {}})
        report = runner.StepReport(step="plan", ok=False, out_dir="unused")
        report.error = "original failed check"
        runner._finish_step(cp, Path("unused"), "plan", "attempt", "ticket", report, [])
        runner._finalize(self.settings, cp, Path("unused"), "plan", "ticket",
                         ContractSet.load(self.settings.gates_json), report)
        self.assertFalse(report.ok)
        self.assertEqual(report.finish_outcome, "")
        self.assertEqual(report.error, "original failed check")
        self.assertNotIn("PRIVATE", report.render())
        cp.transition.assert_not_called()
        cp.trace.assert_called_once()

    def test_finish_interruptions_keep_the_same_object(self):
        for error in (KeyboardInterrupt("stop"), SystemExit(17)):
            with self.subTest(error=type(error).__name__):
                cp = Mock()
                cp.step_finish.side_effect = error
                report = runner.StepReport(step="plan", ok=False, out_dir="unused")
                with self.assertRaises(type(error)) as caught:
                    runner._finish_step(cp, Path("unused"), "plan", "attempt", "ticket", report, [])
                self.assertIs(caught.exception, error)
                self.assertEqual(report.finish_outcome, "")

    def test_actual_idempotent_finish_without_phase_keeps_identity_compatibility(self):
        with temp_workspace() as workspace:
            directory, checkpoint, cp = self._resume_ticket(workspace, complete_checks=True)
            first = cp.step_finish(directory, "plan", checkpoint.attempt, "success",
                ticket_id="FINAL-RESUME", evidence=["e2e:model-run"], check=False)
            self.assertIs(first.data.get("ok"), True)
            before = (directory / ".ico_events.jsonl").read_bytes()
            report = runner.StepReport(step="plan", ok=False, out_dir=str(directory))
            runner._finish_step(cp, directory, "plan", checkpoint.attempt,
                                "FINAL-RESUME", report, [])
            self.assertEqual(report.finish_outcome, "success", report.render())
            self.assertEqual((directory / ".ico_events.jsonl").read_bytes(), before)

    def test_no_trace_step_does_not_create_a_row_or_failed_checkpoint(self):
        gate = ReasoningGate({"steps": {"install": {
            "default_tier": "L0", "requires_trace": False}}})
        with temp_workspace() as directory, patch.object(
                ReasoningGate, "load", return_value=gate):
            report = runner.StepReport(step="install", ok=False, out_dir=str(directory))
            runner._record_deliberation(self.settings, directory, "install", "ticket", report, None)
            self.assertEqual(report.checkpoints, [])
            self.assertEqual(report.reasoning_rows, [])
            self.assertFalse((directory / ".thinking_gate_trace.jsonl").exists())

    def test_unconfirmed_trace_cannot_claim_clean_closure(self):
        for rc, data in ((2, {"ok": True}), (0, {"ok": False}), (0, {})):
            with self.subTest(rc=rc, data=data):
                cp = Mock()
                cp.trace.return_value = ControlResult((), rc, data)
                report = runner.StepReport(step="plan", ok=False, out_dir="unused",
                                           finish_outcome="failure")
                runner._finalize(self.settings, cp, Path("unused"), "plan", "ticket",
                                 ContractSet.load(self.settings.gates_json), report)
                self.assertFalse(report.ok)
                self.assertFalse(any(passed for name, passed, _ in report.checkpoints if "闭合" in name))
                cp.transition.assert_not_called()

    def test_actual_max_turn_warning_cannot_soften_empty_reasoning(self):
        with temp_workspace() as workspace:
            directory = next_out_dir(workspace)
            ControlPlane(self.settings).create(directory, ticket_id="FINAL-MAX",
                                               requirement="soft stop", birth="plan")
            backend = FakeBackend([self._script(directory)[0], ""])
            report = runner.run_contract_step(self.settings, backend=backend,
                workspace=workspace, out_dir=directory, ticket_id="FINAL-MAX",
                sandbox=NoIsolation(), loop_config=LoopConfig(max_turns=1))
            self.assertEqual(report.loop.stop_reason, "max_turns")
            self.assertEqual(report.finish_outcome, "failure")
            self.assertFalse(report.ok)
            self.assertTrue(Path(report.checkpoint_path).exists())

    def test_actual_chain_failed_reasoning_never_starts_review(self):
        with temp_workspace() as workspace:
            directory = next_out_dir(workspace)
            ControlPlane(self.settings).create(directory, ticket_id="FINAL-CHAIN",
                                               requirement="chain stop", birth="plan")
            report = run_chain(self.settings,
                backend=FakeBackend(self._script(directory, reasoning=False)), workspace=workspace,
                out_dir=directory, ticket_id="FINAL-CHAIN", steps=("plan", "review"),
                requirement="actual failed reasoning chain", sandbox=NoIsolation())
            self.assertFalse(report.ok)
            self.assertEqual(report.stopped_at, "plan")
            self.assertEqual([event["payload"]["step"] for event in self._events(
                directory, "step_started")], ["plan"])
            self.assertEqual(report.steps[0].finish_outcome, "failure")


if __name__ == "__main__":
    unittest.main()
