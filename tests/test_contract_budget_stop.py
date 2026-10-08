"""Real control-plane regressions for an already-observed contract budget stop.

Explicit offline usage drives the real AgentLoop; these responses are not model
quality evidence. Failure receipts, artifacts and recovery come from the CP.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from icode import runner
from icode.backends import FakeBackend, Usage
from icode.budget import Budget
from icode.chain import assemble_review_manifest, run_chain
from icode.checkpoint import CHECKPOINT_NAME, Checkpointer
from icode.control import ControlPlane, ControlResult
from icode.handshake import next_out_dir
from icode.isolation import NoIsolation
from icode.loop import LoopConfig
from tests._support import require_skill, temp_workspace


PLAN = "# Actual offline plan\n\nPreserve existing behavior and test boundaries.\n"
REPLY = "Actual response text with enough content for the existing auto-persist path."


class _MeteredBackend(FakeBackend):
    def __init__(self, responses):
        super().__init__([response for response, _ in responses])
        self.charges = [charge for _, charge in responses]

    def complete(self, *args, **kwargs):
        charge = self.charges[min(self._index, len(self.charges) - 1)]
        response = super().complete(*args, **kwargs)
        self.last_usage = Usage(total_tokens=charge, calls=1)
        return response


def _write(out_dir: Path, call_id="write-plan"):
    return {"content": "", "tool_calls": [{
        "id": call_id, "name": "write_file",
        "arguments": {"path": str(out_dir / "01_plan.md"), "content": PLAN},
    }]}


def _events(out_dir: Path, kind: str):
    return [event for line in (out_dir / ".ico_events.jsonl").read_text(
        encoding="utf-8").splitlines()
        if (event := json.loads(line)).get("event_type") == kind]


class TestContractBudgetStop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = require_skill()

    def setUp(self):
        self.temporary = temp_workspace()
        self.workspace = self.temporary.__enter__().resolve()
        self.addCleanup(self.temporary.__exit__, None, None, None)
        self.out_dir = next_out_dir(self.workspace)
        self.ticket_id = "BUDGET-CONTRACT-1"
        self.cp = ControlPlane(self.settings)
        self.cp.create(self.out_dir, ticket_id=self.ticket_id,
                       requirement="actual offline budget boundary", birth="plan")

    def _run(self, backend, *, post=None, budget=None, config=None):
        return runner.run_contract_step(
            self.settings, backend=backend, workspace=self.workspace,
            step="plan", ticket_id=self.ticket_id, out_dir=self.out_dir,
            sandbox=NoIsolation(), post_write=post,
            budget=budget or Budget(expected_tokens=100), loop_config=config,
        )

    def _open_for_resume(self):
        attempt = self.cp.step_start(self.out_dir, "plan", ticket_id=self.ticket_id)
        self.cp.step_check(self.out_dir, "plan", attempt, "before_write",
                           ticket_id=self.ticket_id)
        checkpoint = Checkpointer(self.out_dir, ticket_id=self.ticket_id,
                                  step="plan", attempt=attempt)
        checkpoint.save(turn_index=1, tool_calls=0, history=[])
        return checkpoint

    def _assert_stopped(self, report, backend, calls, *, total_tokens=301):
        self.assertEqual(report.loop.stop_reason, "budget_exceeded")
        self.assertFalse(report.loop.ok)
        self.assertEqual(report.loop.usage.total_tokens, total_tokens)
        self.assertFalse(report.ok)
        self.assertIn("budget_exceeded", report.error)
        self.assertEqual(report.advance_status, "")
        self.assertEqual(report.reasoning_rows, [])
        self.assertEqual(len(backend.calls), calls)
        self.assertTrue((self.out_dir / CHECKPOINT_NAME).is_file())
        self.assertFalse((self.out_dir / ".thinking_gate_trace.jsonl").exists())

    def _assert_failure_receipt(self, report):
        self.assertEqual(report.finish_outcome, "failure")
        finished = _events(self.out_dir, "step_finished")
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["payload"]["outcome"], "failure")
        self.assertTrue(finished[0]["payload"]["evidence"])
        trace = self.cp.trace(self.out_dir).data
        self.assertEqual(trace["status"], "init_in_progress")
        self.assertFalse(trace["open_steps"])
        self.assertFalse(trace["open_operations"])

    def test_existing_actual_artifact_cannot_turn_301_into_success(self):
        backend = _MeteredBackend([(_write(self.out_dir), 100), (REPLY, 201)])
        post = mock.Mock()
        with mock.patch.object(runner, "_register_outputs", wraps=runner._register_outputs) as register, \
             mock.patch.object(runner, "_finalize", wraps=runner._finalize) as finalize:
            report = self._run(backend, post=post)
        self._assert_stopped(report, backend, 2)
        self._assert_failure_receipt(report)
        self.assertEqual((self.out_dir / "01_plan.md").read_text(encoding="utf-8"), PLAN)
        self.assertEqual(report.artifacts, [])
        self.assertEqual(_events(self.out_dir, "artifact_written"), [])
        operations = _events(self.out_dir, "operation_finished")
        self.assertEqual(len(operations), 1, "actual first-turn write receipt must remain")
        post.assert_not_called()
        register.assert_not_called()
        finalize.assert_not_called()

    def test_missing_artifact_over_budget_never_repairs_or_auto_persists(self):
        backend = _MeteredBackend([(REPLY, 301)])
        post = mock.Mock()
        with mock.patch.object(runner, "_persist_missing_from_response",
                               wraps=runner._persist_missing_from_response) as persist:
            report = self._run(backend, post=post)
        self._assert_stopped(report, backend, 1)
        self._assert_failure_receipt(report)
        self.assertFalse((self.out_dir / "01_plan.md").exists())
        self.assertEqual(_events(self.out_dir, "verification_recorded"), [])
        self.assertEqual(_events(self.out_dir, "artifact_written"), [])
        post.assert_not_called()
        persist.assert_not_called()

    def test_repair_budget_stop_preserves_prior_facts_without_post_stop_work(self):
        backend = _MeteredBackend([("initial reply", 1), (REPLY, 301)])
        post = mock.Mock()
        with mock.patch.object(runner, "_register_outputs", wraps=runner._register_outputs) as register, \
             mock.patch.object(runner, "_persist_missing_from_response",
                               wraps=runner._persist_missing_from_response) as persist:
            report = self._run(backend, post=post)
        self._assert_stopped(report, backend, 2, total_tokens=302)
        self._assert_failure_receipt(report)
        self.assertEqual(post.call_count, 1, "only the pre-budget initial callback happened")
        self.assertEqual(register.call_count, 1)
        self.assertEqual(len(_events(self.out_dir, "verification_recorded")), 1)
        self.assertFalse((self.out_dir / "01_plan.md").exists())
        persist.assert_not_called()

    def test_review_repair_keeps_real_pre_budget_artifact_receipts_and_bytes(self):
        # Reuse the existing real-CP legal review-entry fixture. Its offline
        # reasoning setup is fixture data, not a claim of model review quality.
        from tests.test_chain_offline import TestReviewInitialEntryOffline

        out_dir = TestReviewInitialEntryOffline._initial_ticket(self, self.workspace)
        round_body = json.dumps({"round": 1, "new_issues": [],
                                 "refuted_issues": [], "pending_verification": []})
        submit = {"content": "", "tool_calls": [{"id": "actual-round", "name": "submit_artifact",
                  "arguments": {"name": "review_round_1.json", "content": round_body}}]}
        backend = _MeteredBackend([(submit, 100), ("initial done", 1), (REPLY, 301)])
        assembled = {}
        def assemble(directory, step, attempt):
            ok, reason = assemble_review_manifest(directory, "REVIEW-HONESTY", attempt)
            self.assertTrue(ok, reason)
            for name in ("review_manifest.json", "review_round_1.json"):
                assembled[name] = (directory / name).read_bytes()
        post = mock.Mock(side_effect=assemble)
        with mock.patch.object(runner, "_register_outputs", wraps=runner._register_outputs) as register:
            report = runner.run_contract_step(
                self.settings, backend=backend, workspace=self.workspace,
                step="review", ticket_id="REVIEW-HONESTY", out_dir=out_dir,
                post_write=post, sandbox=NoIsolation(), budget=Budget(expected_tokens=100))
        self.assertFalse(report.ok)
        self.assertEqual(report.loop.stop_reason, "budget_exceeded")
        self.assertEqual(report.loop.usage.total_tokens, 402)  # Initial 100+1, repair 301.
        self.assertEqual(report.finish_outcome, "failure")
        self.assertEqual(len(backend.calls), 3)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(register.call_count, 1)
        self.assertEqual(report.artifacts, ["review_manifest.json", "review_round_1.json"])
        review_receipts = [event for event in _events(out_dir, "artifact_written")
                           if event["payload"].get("step") == "review"]
        self.assertEqual(len(review_receipts), 2)
        for name, body in assembled.items():
            self.assertEqual((out_dir / name).read_bytes(), body)
        self.assertFalse((out_dir / "02_review.md").exists())
        self.assertTrue((out_dir / CHECKPOINT_NAME).exists())

    def test_resume_budget_stop_preserves_checkpoint_and_never_registers(self):
        checkpoint = self._open_for_resume()
        (self.out_dir / "01_plan.md").write_bytes(PLAN.encode("utf-8"))
        backend = _MeteredBackend([(REPLY, 301)])
        with mock.patch.object(runner, "_register_outputs", wraps=runner._register_outputs) as register, \
             mock.patch.object(runner, "_finalize", wraps=runner._finalize) as finalize:
            report = runner.resume_contract_step(
                self.settings, backend=backend, out_dir=self.out_dir,
                budget=Budget(expected_tokens=100))
        self._assert_stopped(report, backend, 1)
        self._assert_failure_receipt(report)
        self.assertEqual(report.recovery_action, "resume")
        self.assertEqual(checkpoint.load().turn_index, 1)
        self.assertEqual(_events(self.out_dir, "artifact_written"), [])
        register.assert_not_called()
        finalize.assert_not_called()

    def test_later_resume_after_accepted_failure_uses_existing_recoverer(self):
        backend = _MeteredBackend([(REPLY, 301)])
        stopped = self._run(backend)
        self._assert_stopped(stopped, backend, 1)
        before = (self.out_dir / ".ico_events.jsonl").read_bytes()
        later = _MeteredBackend([("must not be called", 1)])
        report = runner.resume_contract_step(self.settings, backend=later, out_dir=self.out_dir,
                                              budget=Budget(expected_tokens=100))
        self.assertFalse(report.ok)
        self.assertEqual(report.recovery_action, "start_fresh")
        self.assertIn("attempt", report.error)
        self.assertEqual(later.calls, [])
        self.assertFalse((self.out_dir / CHECKPOINT_NAME).exists())
        self.assertEqual((self.out_dir / ".ico_events.jsonl").read_bytes(), before)

    def test_rejected_failure_keeps_open_attempt_and_checkpoint(self):
        backend = _MeteredBackend([(REPLY, 301)])
        rejected = ControlResult((), 2, {"ok": False, "outcome": "failure", "error": "PRIVATE_REJECT"})
        with mock.patch.object(runner, "ControlPlane", return_value=self.cp), \
             mock.patch.object(self.cp, "step_finish", return_value=rejected) as finish:
            report = self._run(backend)
        self._assert_stopped(report, backend, 1)
        self.assertEqual(report.finish_outcome, "")
        self.assertNotIn("PRIVATE_REJECT", report.render())
        self.assertEqual(finish.call_args.args[3], "failure")
        self.assertTrue(finish.call_args.kwargs["evidence"])
        self.assertEqual(_events(self.out_dir, "step_finished"), [])
        self.assertTrue(self.cp.trace(self.out_dir).data["open_steps"])

    def test_rejected_failure_does_not_claim_cross_process_budget_enforcement(self):
        backend = _MeteredBackend([(REPLY, 301)])
        rejected = ControlResult((), 2, {"ok": False})
        with mock.patch.object(runner, "ControlPlane", return_value=self.cp), \
             mock.patch.object(self.cp, "step_finish", return_value=rejected):
            stopped = self._run(backend)
        self._assert_stopped(stopped, backend, 1)
        later = _MeteredBackend([(_write(self.out_dir, "resume-write"), 100), ("done", 1)])
        resumed = runner.resume_contract_step(self.settings, backend=later, out_dir=self.out_dir,
                                               budget=Budget(expected_tokens=100))
        self.assertEqual(resumed.recovery_action, "resume")
        self.assertEqual(resumed.loop.stop_reason, "no_tool_calls")
        self.assertEqual(resumed.loop.usage.total_tokens, 101)
        # The old recovery path starts a new tracker, but the actual CP still
        # refuses success without its required boundary checks. Do not bypass it.
        self.assertEqual(resumed.finish_outcome, "")
        self.assertEqual(resumed.error, "")
        self.assertTrue(any("step finish" in name and not ok
                            for name, ok, _ in resumed.checkpoints))
        self.assertTrue((self.out_dir / CHECKPOINT_NAME).exists())
        self.assertGreaterEqual(len(later.calls), 2)

    def test_finish_and_trace_exceptions_cannot_replace_budget_reason(self):
        backend = _MeteredBackend([(REPLY, 301)])
        original_trace = self.cp.trace
        def trace(*args, **kwargs):
            if backend.calls:
                raise OSError("PRIVATE_TRACE")
            return original_trace(*args, **kwargs)
        with mock.patch.object(runner, "ControlPlane", return_value=self.cp), \
             mock.patch.object(self.cp, "step_finish", side_effect=RuntimeError("PRIVATE_FINISH")), \
             mock.patch.object(self.cp, "trace", side_effect=trace) as observe:
            report = self._run(backend)
        self._assert_stopped(report, backend, 1)
        self.assertEqual(report.finish_outcome, "")
        self.assertEqual(report.trace, {})
        self.assertEqual(observe.call_count, 2, "entry observation plus independent final observation")
        self.assertNotIn("PRIVATE", report.render())
        self.assertTrue(self.cp.trace(self.out_dir).data["open_steps"])

    def test_trace_exception_after_real_failure_retains_confirmed_outcome(self):
        backend = _MeteredBackend([(REPLY, 301)])
        original = self.cp.trace
        def trace(*args, **kwargs):
            if backend.calls:
                raise ValueError("PRIVATE_TRACE")
            return original(*args, **kwargs)
        with mock.patch.object(runner, "ControlPlane", return_value=self.cp), \
             mock.patch.object(self.cp, "trace", side_effect=trace):
            report = self._run(backend)
        self._assert_stopped(report, backend, 1)
        self.assertEqual(report.finish_outcome, "failure")
        self.assertEqual(report.trace, {})
        self.assertNotIn("PRIVATE", report.render())
        self.assertEqual(len(_events(self.out_dir, "step_finished")), 1)

    def test_unconfirmed_finish_and_trace_results_never_claim_closure(self):
        backend = _MeteredBackend([(REPLY, 301)])
        original = self.cp.trace
        def trace(*args, **kwargs):
            if backend.calls:
                return ControlResult((), 2, {"ok": False})
            return original(*args, **kwargs)
        with mock.patch.object(runner, "ControlPlane", return_value=self.cp), \
             mock.patch.object(self.cp, "step_finish", return_value=ControlResult((), 0, {"ok": True, "outcome": "success"})), \
             mock.patch.object(self.cp, "trace", side_effect=trace):
            report = self._run(backend)
        self._assert_stopped(report, backend, 1)
        self.assertEqual(report.finish_outcome, "")
        self.assertFalse(any(ok for name, ok, _ in report.checkpoints if "闭合" in name))

    def test_budget_receipt_interruptions_propagate_unchanged(self):
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__):
                backend = _MeteredBackend([(REPLY, 301)])
                error = kind("actual interruption")
                with mock.patch.object(runner, "ControlPlane", return_value=self.cp), \
                     mock.patch.object(self.cp, "step_finish", side_effect=error):
                    with self.assertRaises(kind) as caught:
                        self._run(backend)
                self.assertIs(caught.exception, error)
                self.assertEqual(len(backend.calls), 1)
                self.assertTrue((self.out_dir / CHECKPOINT_NAME).exists())

    def test_budget_trace_interruptions_propagate_after_actual_failure_receipt(self):
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__), temp_workspace() as temporary:
                workspace = temporary.resolve()
                out_dir = next_out_dir(workspace)
                cp = ControlPlane(self.settings)
                cp.create(out_dir, ticket_id=self.ticket_id, requirement="trace interruption", birth="plan")
                backend = _MeteredBackend([(REPLY, 301)])
                error = kind("actual trace interruption")
                original = cp.trace
                def trace(*args, **kwargs):
                    if backend.calls:
                        raise error
                    return original(*args, **kwargs)
                with mock.patch.object(runner, "ControlPlane", return_value=cp), \
                     mock.patch.object(cp, "trace", side_effect=trace):
                    with self.assertRaises(kind) as caught:
                        runner.run_contract_step(
                            self.settings, backend=backend, workspace=workspace,
                            ticket_id=self.ticket_id, out_dir=out_dir,
                            budget=Budget(expected_tokens=100), sandbox=NoIsolation())
                self.assertIs(caught.exception, error)
                self.assertEqual(len(backend.calls), 1)
                self.assertTrue((out_dir / CHECKPOINT_NAME).exists())
                self.assertEqual(_events(out_dir, "step_finished")[0]["payload"]["outcome"], "failure")

    def test_300_and_observation_only_keep_existing_artifact_success(self):
        for expected, charge in ((100, 200), (0, 10000)):
            with self.subTest(expected=expected), temp_workspace() as temporary:
                workspace = temporary.resolve()
                out_dir = next_out_dir(workspace)
                ControlPlane(self.settings).create(
                    out_dir, ticket_id="BUDGET-COMPAT-1", requirement="actual compatible plan", birth="plan")
                # Reasoning now shares the owner: explicitly zero-cost responses
                # keep this exact-boundary control from replaying the last charge.
                reasoning = json.dumps({"step": "Check the exact budget boundary", "next_thought_needed": False})
                backend = _MeteredBackend([(_write(out_dir), 100), ("done", charge)] + [(reasoning, 0)] * 3)
                report = runner.run_contract_step(
                    self.settings, backend=backend, workspace=workspace,
                    ticket_id="BUDGET-COMPAT-1", sandbox=NoIsolation(),
                    budget=Budget(expected_tokens=expected), out_dir=out_dir)
                self.assertEqual(report.loop.stop_reason, "no_tool_calls")
                self.assertEqual(report.loop.usage.total_tokens, 100 + charge)
                self.assertEqual(len(backend.calls), 5)
                self.assertEqual(report.finish_outcome, "success")
                self.assertEqual(report.error, "")
                self.assertEqual(report.artifacts, ["01_plan.md"])
                self.assertFalse((out_dir / CHECKPOINT_NAME).exists())

    def test_max_turns_with_actual_artifact_remains_existing_soft_stop(self):
        # A max-turn warning is soft; a separately failed reasoning gate is not.
        reasoning = json.dumps({"step": "Check the actual soft-stop artifact",
                                "next_thought_needed": False})
        backend = _MeteredBackend([(_write(self.out_dir), 100)] + [(reasoning, 0)] * 3)
        post = mock.Mock()
        report = self._run(backend, post=post, config=LoopConfig(max_turns=1))
        self.assertEqual(report.loop.stop_reason, "max_turns")
        self.assertFalse(report.loop.ok)
        self.assertEqual(report.finish_outcome, "success")
        self.assertEqual(report.error, "")
        self.assertEqual(report.artifacts, ["01_plan.md"])
        self.assertEqual(post.call_count, 1)
        self.assertFalse((self.out_dir / CHECKPOINT_NAME).exists())
        self.assertEqual(len(backend.calls), 4)
        self.assertEqual(report.reasoning_rows[0].result, "success")

    def test_non_budget_backend_error_keeps_existing_artifact_driven_behavior(self):
        class FailSecondResponse(_MeteredBackend):
            failed = False
            def complete(self, *args, **kwargs):
                if self._index == 1 and not self.failed:
                    self.failed = True
                    raise RuntimeError("actual offline backend failure")
                return super().complete(*args, **kwargs)
        backend = FailSecondResponse([(_write(self.out_dir), 100), ("done", 1)])
        report = self._run(backend)
        self.assertEqual(report.loop.stop_reason, "backend_error")
        self.assertFalse(report.loop.ok)
        self.assertEqual(report.finish_outcome, "success")
        self.assertEqual(report.error, "")
        self.assertEqual(report.artifacts, ["01_plan.md"])

    def test_real_chain_budget_failure_never_starts_next_step(self):
        backend = _MeteredBackend([(_write(self.out_dir), 100), (REPLY, 201)])
        report = run_chain(
            self.settings, backend=backend, workspace=self.workspace,
            requirement="actual chain stop", ticket_id=self.ticket_id,
            steps=("plan", "review"), out_dir=self.out_dir,
            sandbox=NoIsolation(), budget=Budget(expected_tokens=100))
        self.assertEqual([step.step for step in report.steps], ["plan"])
        self._assert_stopped(report.steps[0], backend, 2)
        self.assertFalse(report.ok)
        self.assertEqual([row["payload"]["step"] for row in _events(self.out_dir, "step_started")], ["plan"])


if __name__ == "__main__":
    unittest.main()
