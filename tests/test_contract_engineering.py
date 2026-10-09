"""Contract engineering gates; doubles only demonstrate orchestration boundaries."""

from dataclasses import replace
from pathlib import Path
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from icode import runner
from icode.autonomy import ExecutionContext, NativeChainExecutor
from icode.backends import FakeBackend
from icode.engineering_verification import VerificationCheck, VerificationPlan
from icode.control import ControlPlane, ControlResult, make_request
from icode.handshake import next_out_dir
from icode.self_verify import VerificationEvidence, evidence_fingerprint
from icode.isolation import NoIsolation
from icode.isolation import LandlockSandbox
from icode.execution_broker import ExecutionResult as BrokerResult
from icode.budget import BudgetTracker
from icode.operations import OperationRecorder
from icode.loop import LoopConfig
from icode.loop import LoopResult
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from tests._support import require_skill, temp_workspace
from tests.windows_snapshot_rejection_diagnostic import windows_snapshot_rejection_diagnostic


def policy_for(root, step="code"):
    root = root.resolve()
    return SandboxPolicy(1, "contract-run", "ENG-CONTRACT", step, root,
        (root,), (root,), (root / ".git", root / ".icode_output"),
        (root / ".git", root / ".icode_output"), NetworkMode.DENY, (),
        8, 30, 65536, (root / ".git",))


class TestContractEngineering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = require_skill()

    def gate_fixture(self, *, output=b"Ran 1 test in 0.01s\n\nOK\n", code=0,
                     changes=None, reviewer=None, git_workspace=False, interrupted_change=False):
        """Real CP and host verifier with a broker transport double, not native proof."""
        root = self.enterContext(temp_workspace()).resolve()
        self.assertEqual(root, root.resolve(strict=True))
        self.enterContext(patch("icode.tools.builtin._uses_resource_dispatch", return_value=True))
        if git_workspace:
            import subprocess
            (root / "changed.py").write_text("value = 0\n", encoding="utf-8")
            for command in (("init", "-q"), ("add", "changed.py"),
                ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "core.hooksPath=" + str(root / "absent-hooks"), "commit", "-qm", "fixture baseline")):
                initialized = subprocess.run(["git", "-C", str(root), *command],
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(initialized.returncode, 0, initialized.stderr)
        with windows_snapshot_rejection_diagnostic(enabled=os.name == "nt" and git_workspace):
            baseline = runner._snapshot(root)
        if not interrupted_change:
            (root / "changed.py").write_text("value = 1\n", encoding="utf-8")
        directory = next_out_dir(root).resolve()
        cp = ControlPlane(self.settings)
        cp.create(directory, ticket_id="ENG-CONTRACT", requirement="receipt", birth="plan")
        (directory / "03_plan_final.md").write_text("# Accepted plan\n", encoding="utf-8")
        attempt = cp.step_start(directory, "code", ticket_id="ENG-CONTRACT")
        if interrupted_change:
            # This is an actual change in the opened attempt, not a baseline
            # reconstructed after interruption or backdated fixture content.
            (root / "changed.py").write_text("value = 1\n", encoding="utf-8")
        check = VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"),
                                  "unittest_summary_v1", timeout_seconds=5, output_limit_bytes=65536)
        plan = VerificationPlan(root, "contract-run", "ENG-CONTRACT", (check,))
        resource = dict(schema_version=1, resource="linux_payload_tasks", limit=8, configured=True,
            payload_started=None, terminal="finished", channel_status="complete")
        outcome = BrokerResult(code, "", len(output), None, False, True, None,
            raw_output=output, resource_receipt=resource, scope_cleanup_ok=True,
            violation_observer_status="complete")
        if changes:
            outcome = replace(outcome, **changes)
        report = runner.StepReport("code", False, str(directory))
        arguments = dict(cp=cp, out_dir=directory, ticket_id="ENG-CONTRACT", step="code", attempt=attempt,
            report=report, plan=plan, policy=policy_for(root), sandbox=LandlockSandbox("transport-fixture"),
            workspace_session=None, workspace=root, baseline=baseline, git_baseline=runner._read_task_git_state(root),
            operations=OperationRecorder(cp, directory, "ENG-CONTRACT", scope="code"),
            backend=reviewer or FakeBackend([]), requirement="change", loop_config=LoopConfig(), budget_tracker=BudgetTracker())
        return root, cp, directory, outcome, report, arguments

    def event_rows(self, directory, kind):
        import json
        return [row for line in (directory / ".ico_events.jsonl").read_text(encoding="utf-8").splitlines()
                if (row := json.loads(line))["event_type"] == kind]

    def split_gate_fixture(self):
        """Real split session and Git projection; broker outcomes remain doubles."""
        from icode.workspace import WorkspaceManager
        from tests.test_shared_runtime_budget import MeteredBackend

        backend = MeteredBackend([
            ({"tool_calls": [{"id": "split-read", "name": "read_file",
                              "arguments": {"path": "changed.py"}}]}, 1),
            ({"tool_calls": [{"id": "split-review", "name": "submit_review",
                              "arguments": {"summary": "Checked split change", "findings": []}}]}, 1),
            ("done", 1),
        ])
        source, cp, directory, outcome, report, args = self.gate_fixture(
            reviewer=backend, git_workspace=True,
        )
        data = self.enterContext(temp_workspace()).resolve()
        session = WorkspaceManager(source, data, "split-gate", isolate_git_metadata=True).open(
            "ENG-CONTRACT", "contract-run",
        )
        self.addCleanup(session.close)
        root = session.workspace_root
        baseline = runner._snapshot(root)
        (root / "changed.py").write_text("value = 1\n", encoding="utf-8")
        old_plan = args["plan"]
        args.update(workspace=root, workspace_session=session, baseline=baseline,
            git_baseline=runner._read_task_git_state(root, workspace_session=session),
            policy=session.policy("code", process_limit=8, wall_timeout_seconds=30, output_limit_bytes=65536),
            plan=VerificationPlan(root, old_plan.run_id, old_plan.ticket_id, old_plan.checks,
                                  old_plan.steps, old_plan.platforms))
        return root, cp, directory, outcome, report, args

    @unittest.skipUnless(os.name == "posix", "manager split Git identity is POSIX-only")
    def test_split_session_gate_real_tree_reviewer_and_final_binding(self):
        root, cp, directory, outcome, report, args = self.split_gate_fixture()
        session = args["workspace_session"]
        with patch.object(runner, "_read_task_git_state", wraps=runner._read_task_git_state) as state, \
                patch.object(runner, "_capture_task_git_tree_oid", wraps=runner._capture_task_git_tree_oid) as tree, \
                patch("icode.tools.builtin._controlled_dispatch", return_value=outcome) as dispatch:
            self.assertTrue(runner._contract_engineering_gate(**args), report.error)
            # This isolated final-binding check does not claim the fixture meets every CP input gate.
            self.assertEqual(runner._contract_engineering_binding_error(
                report, args["plan"], root, "code", "ENG-CONTRACT", args["policy"],
                args["sandbox"], session,
            ), "")
        dispatch.assert_called_once()
        self.assertTrue(state.call_args_list)
        self.assertTrue(tree.call_args_list)
        for call in state.call_args_list + tree.call_args_list:
            self.assertIs(call.kwargs.get("workspace_session"), session)
        self.assertEqual(report.verification_evidence.tested_git_tree_status, "stable")
        self.assertEqual(report.verification_evidence.git_object_format, "sha1")
        self.assertFalse(cp.trace(directory).data["open_operations"])
        self.assertEqual(args["budget_tracker"].usage.calls, 3)
        tools = {tool["function"]["name"] for call in args["backend"].calls for tool in call["tools"]}
        self.assertEqual(tools, {"read_file", "submit_review"})

    @unittest.skipUnless(os.name == "posix", "manager split Git identity is POSIX-only")
    def test_split_session_reviewer_and_final_boundary_reject_real_drift(self):
        from icode.reviewer import ReviewReport

        for change in ("source_during_review", "identity_during_review",
                       "source_after_review", "identity_after_review"):
            with self.subTest(change=change):
                root, _cp, directory, outcome, report, args = self.split_gate_fixture()
                session = args["workspace_session"]

                def mutate():
                    if change.startswith("source"):
                        (root / "changed.py").write_text("value = 9\n", encoding="utf-8")
                    else:
                        (session.git_status_identity.git_dir / "HEAD").write_text("0" * 40 + "\n", encoding="ascii")

                def review(**kwargs):
                    if "during" in change:
                        mutate()
                    return ReviewReport(ok=True, model_reviewed=True, read_only_verified=True), None

                with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
                        patch.object(runner, "_run_task_reviewer", side_effect=review):
                    if change == "identity_during_review":
                        with self.assertRaisesRegex(ValueError, "^workspace_git_identity_unavailable$"):
                            runner._contract_engineering_gate(**args)
                    elif change == "source_during_review":
                        self.assertFalse(runner._contract_engineering_gate(**args))
                        self.assertEqual(report.error, "engineering_reviewer_failed")
                    else:
                        self.assertTrue(runner._contract_engineering_gate(**args), report.error)
                        mutate()
                        if change == "identity_after_review":
                            with self.assertRaisesRegex(ValueError, "^workspace_git_identity_unavailable$"):
                                runner._contract_engineering_binding_error(
                                    report, args["plan"], root, "code", "ENG-CONTRACT",
                                    args["policy"], args["sandbox"], session,
                                )
                        else:
                            self.assertEqual(runner._contract_engineering_binding_error(
                                report, args["plan"], root, "code", "ENG-CONTRACT",
                                args["policy"], args["sandbox"], session,
                            ), "engineering_final_binding_changed")
                self.assertFalse(self.event_rows(directory, "step_finished"))

    def test_policy_code_missing_plan_refuses_before_control_write_and_model(self):
        with temp_workspace() as root, patch.object(runner, "ControlPlane") as cp:
            backend = FakeBackend(["should not run"])
            report = runner.run_contract_step(self.settings, backend=backend,
                workspace=root, step="code", ticket_id="ENG-CONTRACT",
                policy=policy_for(root), sandbox=NoIsolation())
            self.assertFalse(report.ok)
            self.assertEqual(report.error, "verification_plan_required")
            cp.assert_not_called()

    def test_wrong_plan_binding_and_unavailable_resource_refuse_before_cp(self):
        with temp_workspace() as root:
            check = VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"),
                                      "unittest_summary_v1")
            plan = VerificationPlan(root, "contract-run", "ENG-CONTRACT", (check,))
            variants = ((object(), "verification_plan_invalid"),
                (replace(plan, run_id="other"), "verification_plan_identity_mismatch"),
                (replace(plan, ticket_id="other"), "verification_plan_identity_mismatch"),
                (replace(plan, steps=("task",)), "verification_plan_identity_mismatch"),
                (plan, "verification_resource_unavailable"))
            for supplied, expected in variants:
                with self.subTest(expected=expected), patch.object(runner, "ControlPlane") as cp:
                    report = runner.run_contract_step(self.settings, backend=FakeBackend([]),
                        workspace=root, step="code", ticket_id="ENG-CONTRACT", policy=policy_for(root),
                        verification_plan=supplied, sandbox=NoIsolation())
                    self.assertEqual(report.error, expected)
                    cp.assert_not_called()

    def test_plan_environment_platform_directory_and_tool_drift_refuse_before_cp(self):
        with temp_workspace() as root:
            check = VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"), "unittest_summary_v1")
            for field, value in (("environment", ()), ("workspace_identity", (-1, -1)), ("platforms", ())):
                plan = VerificationPlan(root, "contract-run", "ENG-CONTRACT", (check,))
                object.__setattr__(plan, field, value)
                with self.subTest(field=field), patch.object(runner, "ControlPlane") as cp:
                    report = runner.run_contract_step(self.settings, backend=FakeBackend([]), workspace=root,
                        step="code", ticket_id="ENG-CONTRACT", policy=policy_for(root), verification_plan=plan,
                        sandbox=LandlockSandbox("transport-fixture"))
                    self.assertEqual(report.error, "verification_plan_identity_mismatch")
                    cp.assert_not_called()
            plan = VerificationPlan(root, "contract-run", "ENG-CONTRACT", (check,))
            with patch.object(runner, "_executable_identity", return_value="changed"), \
                 patch.object(runner, "ControlPlane") as cp:
                report = runner.run_contract_step(self.settings, backend=FakeBackend([]), workspace=root,
                    step="code", ticket_id="ENG-CONTRACT", policy=policy_for(root), verification_plan=plan,
                    sandbox=LandlockSandbox("transport-fixture"))
                self.assertEqual(report.error, "verification_tool_changed")
                cp.assert_not_called()

    def test_session_identity_mismatch_refuses_before_cp(self):
        from icode.workspace import WorkspaceSession
        with temp_workspace() as root:
            check = VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"), "unittest_summary_v1")
            plan = VerificationPlan(root, "contract-run", "ENG-CONTRACT", (check,))
            session = Mock(spec=WorkspaceSession)
            session.run_id, session.ticket_id, session.workspace_root = "wrong", "ENG-CONTRACT", root
            with patch.object(runner, "ControlPlane") as cp:
                report = runner.run_contract_step(self.settings, backend=FakeBackend([]), workspace=root,
                    step="code", ticket_id="ENG-CONTRACT", policy=policy_for(root), verification_plan=plan,
                    sandbox=LandlockSandbox("transport-fixture"), workspace_session=session)
                self.assertEqual(report.error, "verification_session_identity_mismatch")
                cp.assert_not_called()

    def test_strict_record_accepts_actual_first_and_replay_responses(self):
        with temp_workspace() as root:
            cp = ControlPlane(self.settings)
            directory = next_out_dir(root)
            cp.create(directory, ticket_id="ENG-CONTRACT", requirement="receipt", birth="plan")
            evidence = VerificationEvidence(step="code", attempt="actual-attempt", kind="engineering_verification",
                command=("host-plan",), exit_code=1, diff_fingerprint="a" * 64, category="test")
            self.assertTrue(callable(getattr(runner, "_record_contract_engineering", None)))
            self.assertTrue(runner._record_contract_engineering(cp, directory, "ENG-CONTRACT", evidence))
            self.assertTrue(runner._record_contract_engineering(cp, directory, "ENG-CONTRACT", evidence))

    def test_strict_record_rejects_transport_payload_and_replay_mismatch(self):
        import uuid
        evidence = VerificationEvidence(step="code", attempt="actual", kind="engineering_verification",
            command=("host-plan",), exit_code=1, category="test", diff_fingerprint="a" * 64)
        payload = dict(kind="device_test", outcome="fail", evidence=evidence_fingerprint(evidence),
            baseline=evidence.diff_fingerprint, layer="unit", scenario="engineering_verification",
            note="step=code category=test")
        request = make_request("ENG-CONTRACT", "record-verification", attempt="verify",
            boundary="|".join((payload["kind"], payload["outcome"], payload["evidence"], payload["baseline"])))
        first = dict(ok=True, run=dict(run_id=str(uuid.uuid4()), at="2026-10-08T00:00:00Z", **payload), event_id=str(uuid.uuid4()))
        replay = dict(ok=True, already_applied=True, request_id=request, run_id=str(uuid.uuid4()), event_id=str(uuid.uuid4()))
        self.assertTrue(callable(getattr(runner, "_record_contract_engineering", None)))
        for rc, data in ((1, first), (0, dict(first, event_id="")),
            (0, dict(first, run=dict(first["run"], scenario="other"))),
            (0, dict(replay, request_id="wrong")), (0, dict(replay, run_id="not-uuid")),
            (0, dict(replay, already_applied=1)), (0, dict(first, event_id="evt-valid")),
            (0, dict(replay, event_id=1)), (0, dict(first, event_id="uuid-invalid"))):
            with self.subTest(data=data):
                cp = Mock()
                cp.record_verification.return_value = ControlResult((), rc, data)
                self.assertFalse(runner._record_contract_engineering(cp, Path("unused"), "ENG-CONTRACT", evidence))

    def test_native_provider_required_and_exception_are_stable_before_adapter(self):
        import inspect
        self.assertIn("verification_plan_provider", inspect.signature(NativeChainExecutor).parameters)
        with temp_workspace() as root:
            context = ExecutionContext("ENG-CONTRACT", root / "ticket", root, "change", "code_in_progress", ())
            control = SimpleNamespace(session=SimpleNamespace(policy=lambda step: policy_for(root)),
                                      safe_point=lambda step: None)
            sandbox = SimpleNamespace(is_real_isolation=True, policy_contract_ready=True,
                prepare_policy=lambda policy: None, wrap_policy=lambda *args, **kw: None)
            def broken(context, policy):
                raise ValueError("PRIVATE_SENTINEL")
            for provider, expected in ((None, "verification_plan_required"), (broken, "verification_plan_provider_failed"),
                                       (lambda ctx, policy: object(), "verification_plan_invalid")):
                with self.subTest(expected=expected), patch("icode.autonomy.chain_steps", return_value=("code",)), \
                    patch("icode.autonomy.ControlPlane.trace", return_value=ControlResult((), 0,
                        {"ticket_id": "ENG-CONTRACT", "status": "code_in_progress"})):
                    executor = NativeChainExecutor(self.settings, backend=FakeBackend([]), sandbox=sandbox,
                                                   verification_plan_provider=provider)
                    result = executor.execute(context, control)
                    self.assertEqual(result.error_code, expected)

    def test_host_gate_failure_saves_full_actual_attempt_and_records_failed_cp_run(self):
        self.assertTrue(callable(getattr(runner, "_contract_engineering_gate", None)))
        with temp_workspace() as root:
            baseline = runner._snapshot(root)
            (root / "changed.py").write_text("value = 1\n", encoding="utf-8")
            directory = next_out_dir(root)
            cp = ControlPlane(self.settings)
            cp.create(directory, ticket_id="ENG-CONTRACT", requirement="receipt", birth="plan")
            (directory / "03_plan_final.md").write_text("# Accepted plan\n", encoding="utf-8")
            attempt = cp.step_start(directory, "code", ticket_id="ENG-CONTRACT")
            check = VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"),
                                      "unittest_summary_v1")
            plan = VerificationPlan(root, "contract-run", "ENG-CONTRACT", (check,))
            output = b"Ran 1 test in 0.01s\n\nFAILED (failures=1)\n"
            resource = dict(schema_version=1, resource="linux_payload_tasks", limit=8, configured=True,
                payload_started=None, terminal="finished", channel_status="complete")
            outcome = BrokerResult(1, "", len(output), None, False, True, None,
                raw_output=output, resource_receipt=resource, scope_cleanup_ok=True,
                violation_observer_status="complete")
            report = runner.StepReport("code", False, str(directory))
            with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
                 patch("icode.tools.builtin._uses_resource_dispatch", return_value=True), \
                 patch.object(runner, "_run_task_reviewer") as reviewer:
                passed = runner._contract_engineering_gate(cp=cp, out_dir=directory,
                    ticket_id="ENG-CONTRACT", step="code", attempt=attempt, report=report,
                    plan=plan, policy=policy_for(root), sandbox=LandlockSandbox("transport-fixture"),
                    workspace_session=None, workspace=root, baseline=baseline, git_baseline=("", ""),
                    operations=OperationRecorder(cp, directory, "ENG-CONTRACT", scope="code"),
                    backend=FakeBackend([]), requirement="change", loop_config=LoopConfig(), budget_tracker=BudgetTracker())
            self.assertFalse(passed)
            reviewer.assert_not_called()
            from icode.evidence import load_verification_receipts
            row = load_verification_receipts([report.verification_receipt_path])[0]
            self.assertEqual(row["binding"]["attempt"], attempt)
            self.assertEqual(row["binding"]["execution_attempt"], attempt)
            self.assertEqual(row["run"]["attempt"], attempt)
            self.assertFalse(row["passed"])
            self.assertFalse(cp.trace(directory).data["open_operations"])

    def test_contract_consumes_gate_after_last_artifact_registration(self):
        with temp_workspace() as root:
            directory = next_out_dir(root)
            cp = Mock()
            cp.trace.return_value = ControlResult((), 0, {"ok": True, "status": "code_in_progress"})
            cp.run.return_value = ControlResult((), 0, {"ok": True, "ticket_id": "ENG-CONTRACT", "execution_root": str(root.resolve())})
            cp.step_start.return_value = "actual-cp-attempt"
            cp.step_check.return_value = ControlResult((), 0, {"result": "pass"})
            cp.artifact.return_value = ControlResult((), 0, {"ok": True})
            events = []
            def model(**kw):
                events.append("model")
                (root / "changed.py").write_text("value = 2\n", encoding="utf-8")
                return SimpleNamespace(ok=True, stop_reason="no_tool_calls", messages=[])
            def post(*args):
                events.append("post")
                for name in ("04_code_review_fix.md", "code_worklist.json"):
                    (directory / name).write_text("{}", encoding="utf-8")
            def gate(**kw):
                events.append("engineering")
                self.assertEqual(kw["attempt"], "actual-cp-attempt")
                self.assertEqual(kw["baseline"], {})
                kw["report"].error = "engineering_verification_failed"
                return False
            check = VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"), "unittest_summary_v1")
            plan = VerificationPlan(root, "contract-run", "ENG-CONTRACT", (check,))
            with patch.object(runner, "ControlPlane", return_value=cp), \
                patch.object(runner, "_contract_plan_error", return_value=""), \
                patch.object(runner, "_run_agent", side_effect=model), \
                patch.object(runner, "_contract_engineering_gate", side_effect=gate) as verify, \
                patch.object(runner, "_prepare_deliberation") as deliberate:
                report = runner.run_contract_step(self.settings, backend=FakeBackend([]), workspace=root,
                    out_dir=directory, step="code", ticket_id="ENG-CONTRACT", policy=policy_for(root),
                    verification_plan=plan, sandbox=NoIsolation(), post_write=post)
            self.assertFalse(report.ok)
            verify.assert_called_once()
            self.assertEqual(events, ["model", "post", "engineering"])
            deliberate.assert_not_called()
            self.assertTrue(Path(report.checkpoint_path).exists())
            cp.transition.assert_not_called()

    def test_reviewer_accepts_policy_and_session_as_explicit_optional_inputs(self):
        import inspect
        parameters = inspect.signature(runner._run_task_reviewer).parameters
        self.assertIn("policy", parameters)
        self.assertIn("workspace_session", parameters)

    def test_unknown_engineering_evidence_is_blocking_even_without_nonzero_exit(self):
        from tests.test_engineering_evidence import _Helpers
        from icode.reviewer import IndependentReviewer
        helper = _Helpers()
        with temp_workspace() as root:
            plan = helper.plan(root)
            observed = helper.observed_run(plan)
            unknown = replace(observed, status="source_unavailable", source_after="")
            evidence = runner.build_engineering_evidence(plan, unknown,
                binding=helper.binding(unknown))
            self.assertIsNone(evidence.exit_code)
            report = IndependentReviewer(workspace=root).review(["changed.py"], evidence)
            self.assertFalse(report.ok)

    def test_resume_engineering_requires_trusted_workspace_policy_plan_and_session(self):
        import inspect
        parameters = inspect.signature(runner.resume_contract_step).parameters
        for name in ("workspace", "policy", "workspace_session", "verification_plan"):
            self.assertIn(name, parameters)
        with temp_workspace() as root, patch.object(runner, "_run_agent") as model:
            report = runner.resume_contract_step(self.settings, backend=FakeBackend([]),
                out_dir=root, step="code", verification_plan=object())
            self.assertEqual(report.error, "engineering_recovery_identity_required")
            model.assert_not_called()

    def test_engineering_checkpoint_without_identity_cannot_fall_back_to_diagnostic(self):
        from icode.checkpoint import Checkpointer
        with temp_workspace() as root:
            directory = next_out_dir(root)
            cp = ControlPlane(self.settings)
            cp.create(directory, ticket_id="ENG-CONTRACT", requirement="resume", birth="plan")
            (directory / "03_plan_final.md").write_text("# Final plan\n", encoding="utf-8")
            attempt = cp.step_start(directory, "code", ticket_id="ENG-CONTRACT")
            checkpoint = Checkpointer(directory, ticket_id="ENG-CONTRACT", step="code", attempt=attempt)
            checkpoint.save(turn_index=1, tool_calls=0, history=[], stop_reason="engineering_verification_pending")
            with patch.object(runner, "_run_agent", return_value=SimpleNamespace(ok=True, stop_reason="no_tool_calls")) as model:
                report = runner.resume_contract_step(self.settings, backend=FakeBackend([]), out_dir=directory, step="code")
            self.assertEqual(report.error, "engineering_recovery_identity_required")
            model.assert_not_called()
            self.assertTrue(checkpoint.path.exists())

    def test_engineering_gate_is_selected_once_in_bounded_ci(self):
        from scripts.run_workspace_ci import DEFAULT_MODULES, CONTRACT_ENGINEERING_TESTS, POSIX_CONTRACT_ENGINEERING_TESTS
        for name in (*CONTRACT_ENGINEERING_TESTS, *(POSIX_CONTRACT_ENGINEERING_TESTS if os.name == "posix" else ())):
            self.assertEqual(DEFAULT_MODULES.count(name), 1)

    def test_passed_gate_consumes_real_reviewer_read_submit_and_shared_policy(self):
        from tests.test_shared_runtime_budget import MeteredBackend
        backend = MeteredBackend([(response, 1) for response in [
            {"tool_calls": [{"id": "read", "name": "read_file", "arguments": {"path": "changed.py"}}]},
            {"tool_calls": [{"id": "submit", "name": "submit_review", "arguments": {"summary": "Checked change", "findings": []}}]},
            "done",
        ]])
        root, cp, directory, outcome, report, args = self.gate_fixture(reviewer=backend)
        with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome) as dispatch, \
             patch.object(runner, "_make_ctx", wraps=runner._make_ctx) as contexts:
            passed = runner._contract_engineering_gate(**args)
        self.assertTrue(passed, report.error)
        dispatch.assert_called_once()
        reviewers = [c for c in contexts.call_args_list if c.kwargs.get("read_only_workspace")]
        self.assertEqual(len(reviewers), 1)
        review_policy = reviewers[0].args[2]
        self.assertEqual(review_policy.run_id, args["policy"].run_id)
        self.assertEqual(review_policy.step, "code")
        self.assertEqual(review_policy.write_roots, ())
        self.assertIn(directory, review_policy.deny_read_roots)
        self.assertFalse(cp.trace(directory).data["open_operations"])
        self.assertEqual(args["budget_tracker"].usage.calls, 3)

    def test_completed_operation_request_replay_cannot_rerun_engineering_payload(self):
        from icode.reviewer import ReviewReport
        root, cp, directory, outcome, report, args = self.gate_fixture()
        approved = ReviewReport(ok=True, read_only_verified=True, model_reviewed=True)
        with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome) as execute, \
             patch.object(runner, "_run_task_reviewer", return_value=(approved, None)):
            self.assertTrue(runner._contract_engineering_gate(**args))
            args["operations"] = OperationRecorder(cp, directory, "ENG-CONTRACT", scope="code")
            from icode.evidence import EvidenceError
            try:
                second = runner._contract_engineering_gate(**args)
            except EvidenceError:
                second = False
            self.assertFalse(second)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(report.error, "engineering_operation_replay_refused")

    def test_zero_skipped_nonzero_and_unknown_scope_never_receive_quality_credit(self):
        cases = (
            (b"Ran 0 tests in 0.01s\n\nOK\n", 0, {}, False),
            (b"Ran 1 test in 0.01s\n\nOK (skipped=1)\n", 0, {}, False),
            (b"Ran 1 test in 0.01s\n\nFAILED (failures=1)\n", 1, {}, False),
            (b"Ran 1 test in 0.01s\n\nOK\n", 0, {"scope_cleanup_ok": None}, True),
            (b"Ran 1 test in 0.01s\n\nOK\n", 0, {"output_truncated": True}, True),
            (b"Ran 1 test in 0.01s\n\nOK\n", 0, {"violation_observer_status": "incomplete"}, True),
        )
        for output, code, changes, open_expected in cases:
            with self.subTest(code=code, changes=changes):
                root, cp, directory, outcome, report, args = self.gate_fixture(output=output, code=code, changes=changes)
                with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
                     patch.object(runner, "_run_task_reviewer") as reviewer:
                    self.assertFalse(runner._contract_engineering_gate(**args))
                reviewer.assert_not_called()
                self.assertEqual(bool(cp.trace(directory).data["open_operations"]), open_expected)
                self.assertFalse(self.event_rows(directory, "verification_recorded")[0]["payload"]["outcome"] == "pass")

    def test_exception_after_confirmed_start_retains_unknown_action(self):
        root, cp, directory, outcome, report, args = self.gate_fixture()
        with patch.object(runner, "execute_verification_plan", side_effect=OSError("unknown launch")):
            with self.assertRaises(OSError):
                runner._contract_engineering_gate(**args)
        self.assertTrue(cp.trace(directory).data["open_operations"])
        self.assertEqual(self.event_rows(directory, "operation_finished"), [])

    def test_finalizer_context_keeps_policy_session_and_same_shared_budget(self):
        from tests.test_shared_runtime_budget import MeteredBackend
        import json
        backend = MeteredBackend([(response, 1) for response in [
            {"tool_calls": [{"id": "read", "name": "read_file", "arguments": {"path": "changed.py"}}]},
            "Read complete", "Read complete", "Read complete",
            {"tool_calls": [{"id": "submit", "name": "submit_review", "arguments": {"summary": "Checked change", "findings": []}}]},
            "done",
        ]])
        root, cp, directory, outcome, report, args = self.gate_fixture(reviewer=backend)
        from icode.workspace import WorkspaceSession
        session = WorkspaceSession("fixture", "ENG-CONTRACT", "contract-run", "snapshot",
            root, root, root, root, root / "manifest.json", (root / ".git", root / ".icode_output"),
            SimpleNamespace(release=lambda: None))
        args["workspace_session"] = session
        with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
             patch.object(runner, "_make_ctx", wraps=runner._make_ctx) as contexts:
            passed = runner._contract_engineering_gate(**args)
        self.assertTrue(passed, report.error)
        reviewers = [c for c in contexts.call_args_list if c.kwargs.get("read_only_workspace")]
        self.assertEqual(len(reviewers), 2)
        self.assertIs(reviewers[0].args[2], reviewers[1].args[2])
        self.assertIs(reviewers[0].kwargs["workspace_session"], reviewers[1].kwargs["workspace_session"])
        self.assertIs(reviewers[0].kwargs["workspace_session"], session)
        self.assertEqual(args["budget_tracker"].usage.calls, len(backend.calls))
        row = __import__("icode.evidence", fromlist=["load_verification_receipts"]).load_verification_receipts(
            [report.verification_receipt_path])[0]
        for call in backend.calls:
            user = json.loads(call["messages"][1]["content"])
            self.assertEqual(user["verification"]["engineering_verification"]["fingerprint"], row["fingerprint"])

    def test_reviewer_blocking_incomplete_read_nosubmit_budget_and_source_change_block(self):
        from tests.test_shared_runtime_budget import MeteredBackend
        from icode.budget import Budget
        read = {"tool_calls": [{"id": "read", "name": "read_file", "arguments": {"path": "changed.py"}}]}
        submit = {"tool_calls": [{"id": "submit", "name": "submit_review", "arguments": {"summary": "Checked", "findings": []}}]}
        blocking = {"tool_calls": [{"id": "submit", "name": "submit_review", "arguments": {"summary": "Found defect", "findings": [
            {"severity": "blocking", "category": "code", "file": "changed.py", "line": 1, "message": "Concrete introduced defect"}]}}]}
        variants = (
            ("blocking", [read, blocking, "done"], False),
            ("notallread", [submit, "done"], False),
            ("notsubmit", [read, "done", "done", "done", "done"], False),
            ("budget", [read, submit, "done"], True),
            ("source", [read, submit, "done"], False),
        )
        for mode, script, over_budget in variants:
            with self.subTest(mode=mode):
                backend = MeteredBackend([(r, 101 if over_budget else 1) for r in script])
                root, cp, directory, outcome, report, args = self.gate_fixture(reviewer=backend)
                if over_budget:
                    args["budget_tracker"] = BudgetTracker(Budget(expected_tokens=1))
                if mode == "source":
                    original = backend.complete
                    def complete(*a, **kw):
                        response = original(*a, **kw)
                        if backend._index == 3:
                            (root / "changed.py").write_text("value = 999\n", encoding="utf-8")
                        return response
                    backend.complete = complete
                with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome):
                    self.assertFalse(runner._contract_engineering_gate(**args))
                self.assertEqual(report.error, "budget_exceeded" if over_budget else "engineering_reviewer_failed")
                self.assertEqual(self.event_rows(directory, "step_finished"), [])
                if over_budget:
                    self.assertEqual(len(backend.calls), 1)

    def test_saved_complete_binding_is_rechecked_before_final_step_finish(self):
        self.assertTrue(callable(getattr(runner, "_contract_engineering_binding_error", None)))
        from icode.reviewer import ReviewReport
        root, cp, directory, outcome, report, args = self.gate_fixture()
        with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
             patch.object(runner, "_run_task_reviewer", return_value=(ReviewReport(ok=True,
                read_only_verified=True, model_reviewed=True), None)):
            self.assertTrue(runner._contract_engineering_gate(**args))
        self.assertEqual(runner._contract_engineering_binding_error(report, args["plan"], root,
            "code", "ENG-CONTRACT", args["policy"], args["sandbox"], None), "")
        (root / "changed.py").write_text("value = 9\n", encoding="utf-8")
        self.assertEqual(runner._contract_engineering_binding_error(report, args["plan"], root,
            "code", "ENG-CONTRACT", args["policy"], args["sandbox"], None), "engineering_final_binding_changed")

    @unittest.skipUnless(os.name == "posix", "POSIX captured-scope FD reader")
    def test_protected_deepcheck_scope_requires_unique_captured_current_cp_facts(self):
        self.assertTrue(callable(getattr(runner, "_contract_deepcheck_review_files", None)))
        root, cp, directory, outcome, report, args = self.gate_fixture()
        (directory / "04_code_review_fix.md").write_text("# Existing source\n", encoding="utf-8")
        cp.metadata_update(directory, ticket_id="ENG-CONTRACT", set_json={"code_files": ["changed.py"]})
        attempt = cp.step_start(directory, "deepcheck", ticket_id="ENG-CONTRACT")
        for occurrence, boundary in enumerate(("before_write", "after_wait", "before_transition"), 1):
            cp.step_check(directory, "deepcheck", attempt, boundary,
                ticket_id="ENG-CONTRACT", occurrence=occurrence)
        self.assertEqual(runner._contract_deepcheck_review_files(cp, directory, root,
            "ENG-CONTRACT", attempt), ["changed.py"])
        for mismatch in ("wrong-attempt", ""):
            self.assertIsNone(runner._contract_deepcheck_review_files(cp, directory, root,
                "ENG-CONTRACT", mismatch))
        (root / "changed.py").write_text("value = 9\n", encoding="utf-8")
        self.assertIsNone(runner._contract_deepcheck_review_files(cp, directory, root,
            "ENG-CONTRACT", attempt))

    def test_fixed_review_scope_is_only_available_to_policy_engineering_deepcheck(self):
        import inspect
        self.assertIn("review_files", inspect.signature(runner._run_task_reviewer).parameters)
        root, cp, directory, outcome, report, args = self.gate_fixture()
        evidence = VerificationEvidence(step="code", attempt="actual", exit_code=0)
        backend = FakeBackend([])
        for policy in (None, policy_for(root), policy_for(root, "deepcheck")):
            review, loop = runner._run_task_reviewer(backend=backend, workspace=root,
                task="inspect", changed_files=[], review_files=["changed.py"], evidence=evidence,
                baseline=runner._snapshot(root), sandbox=args["sandbox"], loop_config=LoopConfig(),
                budget_tracker=BudgetTracker(), policy=policy)
            self.assertFalse(review.ok)
        self.assertEqual(backend.calls, [])

    @unittest.skipUnless(os.name == "posix", "POSIX captured-scope FD reader")
    def test_deepcheck_scope_rejects_missing_gate_changed_list_other_root_and_link(self):
        for change in ("missing_gate", "empty", "extra", "other_root", "link", "bad_chain"):
            with self.subTest(change=change):
                root, cp, directory, outcome, report, args = self.gate_fixture()
                (directory / "04_code_review_fix.md").write_text("# Existing code\n", encoding="utf-8")
                cp.metadata_update(directory, ticket_id="ENG-CONTRACT", set_json={"code_files": ["changed.py"]})
                if change == "link":
                    (root / "real.py").write_bytes((root / "changed.py").read_bytes())
                    (root / "changed.py").unlink()
                    (root / "changed.py").symlink_to("real.py")
                attempt = cp.step_start(directory, "deepcheck", ticket_id="ENG-CONTRACT")
                for index, boundary in enumerate(("before_write", "after_wait", "before_transition"), 1):
                    if change != "missing_gate" or boundary != "after_wait":
                        cp.step_check(directory, "deepcheck", attempt, boundary,
                            ticket_id="ENG-CONTRACT", occurrence=index)
                if change in ("empty", "extra"):
                    (root / "extra.py").write_text("value = 2\n", encoding="utf-8")
                    updated = cp.metadata_update(directory, ticket_id="ENG-CONTRACT", request="scope-" + change,
                        set_json={"code_files": [] if change == "empty" else ["changed.py", "extra.py"]})
                    self.assertTrue(updated.data["ok"], updated.data)
                if change == "other_root":
                    other = self.enterContext(temp_workspace())
                    (other / "changed.py").write_bytes((root / "changed.py").read_bytes())
                    updated = cp.metadata_update(directory, ticket_id="ENG-CONTRACT", request="scope-other-root",
                        set_json={"project_path": str(other)})
                    self.assertFalse(updated.data["ok"])
                    self.assertEqual(updated.data["gate_id"], "metadata_update_protected")
                    root = other
                if change == "bad_chain":
                    events = directory / ".ico_events.jsonl"
                    events.write_bytes(events.read_bytes() + b"{\"tampered\": true}\n")
                self.assertIsNone(runner._contract_deepcheck_review_files(cp, directory, root,
                    "ENG-CONTRACT", attempt))

    def test_resume_checks_actual_attempt_unknown_and_completed_actions_before_model(self):
        from icode.checkpoint import Checkpointer
        from icode.workspace import WorkspaceSession
        from icode.reviewer import ReviewReport
        for state in ("unknown", "stale", "completed"):
            with self.subTest(state=state):
                root, cp, directory, outcome, report, args = self.gate_fixture()
                checkpoint = Checkpointer(directory, ticket_id="ENG-CONTRACT", step="code",
                    attempt="stale-attempt" if state == "stale" else args["attempt"])
                checkpoint.save(turn_index=1, tool_calls=1, history=[], stop_reason="engineering_verification_pending")
                if state == "unknown":
                    args["operations"].start(name="unknown-payload", opclass="managed_write", input_desc="fixture")
                if state == "completed":
                    with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
                         patch.object(runner, "_run_task_reviewer", return_value=(ReviewReport(ok=True,
                            read_only_verified=True, model_reviewed=True), None)):
                        self.assertTrue(runner._contract_engineering_gate(**args))
                session = WorkspaceSession("fixture", "ENG-CONTRACT", "contract-run", "snapshot",
                    root, root, root, root, root / "manifest.json", (root / ".git", root / ".icode_output"),
                    SimpleNamespace(release=lambda: None))
                with patch.object(runner, "_run_agent") as model, \
                     patch.object(runner, "execute_verification_plan") as commands:
                    resumed = runner.resume_contract_step(self.settings, backend=FakeBackend([]),
                        out_dir=directory, step="code", workspace=root, policy=args["policy"],
                        verification_plan=args["plan"], workspace_session=session, sandbox=args["sandbox"],
                        change_baseline=args["baseline"])
                model.assert_not_called()
                commands.assert_not_called()
                self.assertFalse(resumed.ok)
                self.assertTrue(checkpoint.exists())

    def test_resume_original_baseline_missing_invalid_or_alone_refuses_before_cp(self):
        import inspect
        from icode.workspace import WorkspaceSession
        self.assertIn("change_baseline", inspect.signature(runner.resume_contract_step).parameters)
        root, cp, directory, outcome, report, args = self.gate_fixture()
        session = WorkspaceSession("fixture", "ENG-CONTRACT", "contract-run", "snapshot",
            root, root, root, root, root / "manifest.json", (root / ".git", root / ".icode_output"),
            SimpleNamespace(release=lambda: None))
        variants = (None, [], {"changed.py": "bad"}, {"../escape": "a" * 64}, {".": "a" * 64},
            {"/absolute": "a" * 64}, {"a//b": "a" * 64}, {"nul\x00": "a" * 64},
            {"surrogate\ud800": "a" * 64}, {"changed.py": "A" * 64})
        for baseline in variants:
            with self.subTest(baseline=repr(baseline)), patch.object(runner, "ControlPlane") as control, \
                 patch.object(runner, "_run_agent") as model:
                resumed = runner.resume_contract_step(self.settings, backend=FakeBackend([]),
                    out_dir=directory, step="code", workspace=root, policy=args["policy"],
                    verification_plan=args["plan"], workspace_session=session, sandbox=args["sandbox"],
                    change_baseline=baseline)
                self.assertEqual(resumed.error, "engineering_recovery_baseline_required" if baseline is None
                                 else "engineering_recovery_baseline_invalid")
                control.assert_not_called()
                model.assert_not_called()
        with patch.object(runner, "ControlPlane") as control:
            resumed = runner.resume_contract_step(self.settings, backend=FakeBackend([]),
                out_dir=directory, step="code", change_baseline={})
            self.assertEqual(resumed.error, "engineering_recovery_identity_required")
            control.assert_not_called()
        # Scaled limits test both exact admission and over-budget rejection
        # without allocating a 256 MiB map or a quarter million test entries.
        for constant, limit, admitted, rejected in (
            ("_MAX_GIT_TREE_ENTRIES", 1, {"a": "a" * 64}, {"a": "a" * 64, "b": "b" * 64}),
            ("_MAX_GIT_TREE_DEPTH", 2, {"a/b": "a" * 64}, {"a/b/c": "a" * 64}),
            ("_MAX_GIT_TREE_BYTES", 65, {"a": "a" * 64}, {"ab": "a" * 64}),
        ):
            with self.subTest(constant=constant), patch.object(runner, constant, limit):
                self.assertEqual(dict(runner._freeze_contract_change_baseline(admitted)), admitted)
                self.assertIsNone(runner._freeze_contract_change_baseline(rejected))
        git_baseline = {".git/config": "a" * 64}
        frozen = runner._freeze_contract_change_baseline(git_baseline)
        self.assertEqual(dict(frozen), git_baseline)
        with self.assertRaises(TypeError):
            frozen[".git/config"] = "b" * 64

    def test_resume_original_attempt_reviews_pre_interrupt_and_resumed_changes(self):
        import inspect
        from icode.checkpoint import Checkpointer
        from icode.workspace import WorkspaceSession
        from tests.test_shared_runtime_budget import MeteredBackend
        self.assertIn("change_baseline", inspect.signature(runner.resume_contract_step).parameters)
        root, cp, directory, outcome, report, args = self.gate_fixture(interrupted_change=True)
        self.assertEqual(args["baseline"], {})  # Empty original workspace is valid.
        checkpoint = Checkpointer(directory, ticket_id="ENG-CONTRACT", step="code", attempt=args["attempt"])
        checkpoint.save(turn_index=1, tool_calls=1, history=[], stop_reason="engineering_verification_pending")
        session = WorkspaceSession("fixture", "ENG-CONTRACT", "contract-run", "snapshot",
            root, root, root, root, root / "manifest.json", (root / ".git", root / ".icode_output"),
            SimpleNamespace(release=lambda: None))
        backend = MeteredBackend([(response, 1) for response in [
            {"tool_calls": [{"id": "a", "name": "read_file", "arguments": {"path": "changed.py"}}]},
            {"tool_calls": [{"id": "b", "name": "read_file", "arguments": {"path": "later.py"}}]},
            {"tool_calls": [{"id": "submit", "name": "submit_review", "arguments": {"summary": "Read both changes", "findings": []}}]},
            "done",
        ]])
        def resumed_model(**kwargs):
            self.assertEqual(kwargs["checkpointer"].attempt, args["attempt"])
            self.assertEqual(dict(kwargs["change_baseline"]), {})
            args["baseline"]["changed.py"] = runner._snapshot(root)["changed.py"]
            # A caller's subsequent mutation cannot rewrite the admitted base.
            self.assertEqual(dict(kwargs["change_baseline"]), {})
            (root / "later.py").write_text("value = 2\n", encoding="utf-8")
            return LoopResult(True, "no_tool_calls")
        with patch.object(runner, "_run_agent", side_effect=resumed_model), \
             patch("icode.tools.builtin._controlled_dispatch", return_value=outcome) as commands, \
             patch.object(runner, "_run_task_reviewer", wraps=runner._run_task_reviewer) as reviewer, \
             patch.object(runner, "_prepare_deliberation", return_value=None):
            resumed = runner.resume_contract_step(self.settings, backend=backend, out_dir=directory,
                step="code", workspace=root, policy=args["policy"], verification_plan=args["plan"],
                workspace_session=session, sandbox=args["sandbox"], change_baseline=args["baseline"])
        commands.assert_called_once()
        reviewer.assert_called_once()
        self.assertEqual(set(reviewer.call_args.kwargs["changed_files"]), {"changed.py", "later.py"})
        self.assertEqual(dict(reviewer.call_args.kwargs["baseline"]), {})
        self.assertEqual(resumed.verification_evidence.diff_fingerprint,
                         runner._diff_fingerprint({}, runner._snapshot(root)))
        self.assertTrue(any(ok for name, ok, _ in resumed.checkpoints if "质量" in name))
        self.assertEqual(self.event_rows(directory, "verification_recorded")[0]["payload"]["outcome"], "pass")
        self.assertEqual(resumed.verification_evidence.attempt, args["attempt"])
        self.assertTrue(checkpoint.exists())  # Missing normal outputs still prevent success.

    @unittest.skipUnless(os.name == "posix", "POSIX captured-scope FD reader")
    def test_scope_source_reads_enforce_existing_host_budget_before_materialization(self):
        for sizes in ((runner.DEFAULT_REVIEW_ARTIFACT_LIMIT_BYTES,),
                      (runner.DEFAULT_REVIEW_ARTIFACT_LIMIT_BYTES + 1,),
                      (runner.DEFAULT_REVIEW_ARTIFACT_LIMIT_BYTES // 2 + 1,) * 2):
            with self.subTest(sizes=sizes):
                root, cp, directory, outcome, report, args = self.gate_fixture()
                names = []
                for index, size in enumerate(sizes):
                    name = "large-" + str(index) + ".py"
                    (root / name).write_bytes(b" " * size)
                    names.append(name)
                (directory / "04_code_review_fix.md").write_text("# Source\n", encoding="utf-8")
                cp.metadata_update(directory, ticket_id="ENG-CONTRACT", set_json={"code_files": names})
                attempt = cp.step_start(directory, "deepcheck", ticket_id="ENG-CONTRACT")
                for index, boundary in enumerate(("before_write", "after_wait", "before_transition"), 1):
                    cp.step_check(directory, "deepcheck", attempt, boundary,
                        ticket_id="ENG-CONTRACT", occurrence=index)
                actual = runner._contract_deepcheck_review_files(cp, directory, root, "ENG-CONTRACT", attempt)
                if sum(sizes) <= runner.DEFAULT_REVIEW_ARTIFACT_LIMIT_BYTES:
                    self.assertEqual(actual, names)
                else:
                    self.assertIsNone(actual)

    def test_each_turn_negative_marker_survives_restart_without_granting_authority(self):
        import subprocess
        from icode.checkpoint import Checkpointer
        from icode.contracts import ContractSet
        root, cp, directory, outcome, report, args = self.gate_fixture()
        checkpoint = Checkpointer(directory, ticket_id="ENG-CONTRACT", step="code", attempt=args["attempt"])
        checkpoint.save(turn_index=0, tool_calls=0, history=[], stop_reason="engineering_verification_pending")
        loop = runner._run_agent(backend=FakeBackend([
            {"tool_calls": [{"id": "read", "name": "read_file", "arguments": {"path": "changed.py"}}]}, "done"]),
            workspace=root, out_dir=directory, ticket_id="ENG-CONTRACT", step="code", brief="Read only fixture",
            contract=ContractSet.load(self.settings.gates_json).step("code"), requirement="Read",
            approver=None, loop_config=LoopConfig(), budget=None, on_event=None, sandbox=NoIsolation(),
            policy=args["policy"], checkpointer=checkpoint, operations=args["operations"])
        self.assertTrue(loop.ok)
        saved = checkpoint.load()
        self.assertGreater(saved.turn_index, 0)
        self.assertEqual(saved.stop_reason, "engineering_verification_pending")
        code = (
            "import sys\nfrom pathlib import Path\nfrom unittest.mock import patch\n"
            "from tests._support import require_skill\nfrom icode.runner import resume_contract_step\n"
            "from icode.backends import FakeBackend\n"
            "with patch('icode.runner.ControlPlane') as cp:\n"
            " report=resume_contract_step(require_skill(), backend=FakeBackend([]), out_dir=Path(sys.argv[1]), step='code')\n"
            " assert report.error=='engineering_recovery_identity_required', report.error\n"
            " cp.assert_not_called()\n"
        )
        restarted = subprocess.run([sys.executable, "-B", "-c", code, str(directory)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
        self.assertEqual(restarted.returncode, 0, restarted.stdout + restarted.stderr)
        self.assertTrue(checkpoint.exists())

    def test_final_boundary_rechecks_actual_cp_protected_input_after_reviewer(self):
        import inspect
        self.assertIn("cp", inspect.signature(runner._contract_engineering_binding_error).parameters)
        from icode.reviewer import ReviewReport
        root, cp, directory, outcome, report, args = self.gate_fixture()
        with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
             patch.object(runner, "_run_task_reviewer", return_value=(ReviewReport(ok=True,
                read_only_verified=True, model_reviewed=True), None)):
            self.assertTrue(runner._contract_engineering_gate(**args))
        (directory / "03_plan_final.md").write_text("# Drift after read-only reviewer\n", encoding="utf-8")
        error = runner._contract_engineering_binding_error(report, args["plan"], root,
            "code", "ENG-CONTRACT", args["policy"], args["sandbox"], None,
            cp=cp, out_dir=directory, attempt=args["attempt"])
        self.assertEqual(error, "engineering_final_control_binding_changed")
        self.assertEqual(self.event_rows(directory, "step_finished"), [])

    @unittest.skipUnless(os.name == "posix", "POSIX raw tree includes workspace control files")
    def test_workspace_control_receipts_are_real_git_tree_drift_not_source_credit(self):
        from icode.reviewer import ReviewReport
        import hashlib
        root, cp, directory, outcome, report, args = self.gate_fixture(git_workspace=True)
        control_changes = []
        started = args["operations"].start
        def observed_start(**kwargs):
            files = [directory / ".ico_events.jsonl", directory / ".ico_metadata.json"]
            before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
            result = started(**kwargs)
            control_changes.extend(path.name for path in files
                if hashlib.sha256(path.read_bytes()).hexdigest() != before[path.name])
            return result
        with patch.object(args["operations"], "start", side_effect=observed_start), \
             patch("icode.tools.builtin._controlled_dispatch", return_value=outcome) as dispatch, \
             patch.object(runner, "_run_task_reviewer", return_value=(ReviewReport(ok=True,
                read_only_verified=True, model_reviewed=True), None)):
            self.assertFalse(runner._contract_engineering_gate(**args))
        self.assertEqual(dispatch.call_count, 1)
        self.assertIn(".ico_events.jsonl", control_changes)
        self.assertTrue(report.verification_evidence.passed)
        self.assertEqual(report.verification_evidence.tested_git_tree_status, "stable")
        self.assertEqual(report.error, "engineering_reviewer_failed")
        self.assertEqual(self.event_rows(directory, "step_finished"), [])

    def test_incremental_cp_worklist_history_without_old_bodies_blocks_export(self):
        from icode.evidence import build_evidence_pack
        root, cp, directory, outcome, report, args = self.gate_fixture(git_workspace=True)
        cp.metadata_update(directory, ticket_id="ENG-CONTRACT", set_json={"code_files": ["changed.py"]})
        cp.step_check(directory, "code", args["attempt"], "before_write", ticket_id="ENG-CONTRACT")
        prepared = cp.run("inspection", "--dir", str(directory), "--step", "code",
            "--attempt", args["attempt"], "--phase", "prepare", "--scope", ".", "--allow-incomplete")
        self.assertTrue(prepared.data["ok"])
        import json
        worklist = json.loads((directory / "code_worklist.json").read_text(encoding="utf-8"))
        for phase in worklist["required_phases"]:
            (root / "changed.py").read_bytes()
            read = cp.run("inspection", "--dir", str(directory), "--step", "code",
                "--attempt", args["attempt"], "--phase", "read", "--read-phase", phase, "--path", "changed.py")
            self.assertTrue(read.data["ok"])
        exported = build_evidence_pack(directory, dest=root / "incremental-pack",
            gates_json=self.settings.gates_json)
        self.assertFalse(exported.ok)
        self.assertIn("正文快照", exported.render())
        self.assertNotEqual(prepared.data["sha256"], read.data["sha256"])

    def test_save_record_and_operation_ack_failures_retain_checkpoint_without_quality(self):
        from icode.checkpoint import Checkpointer
        for failure in ("save", "record", "operation"):
            with self.subTest(failure=failure):
                root, cp, directory, outcome, report, args = self.gate_fixture()
                checkpoint = Checkpointer(directory, ticket_id="ENG-CONTRACT", step="code", attempt=args["attempt"])
                checkpoint.save(turn_index=1, tool_calls=1, history=[], stop_reason="engineering_verification_pending")
                if failure == "save":
                    seam = patch("icode.evidence.save_verification_receipt", side_effect=ValueError("receipt conflict"))
                elif failure == "record":
                    seam = patch.object(cp, "record_verification", return_value=ControlResult((), 1, {"ok": True}))
                else:
                    seam = patch.object(cp, "operation_finish", return_value=ControlResult((), 1, {"ok": True}))
                with seam, patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
                     patch.object(runner, "_run_task_reviewer") as reviewer:
                    if failure == "save":
                        with self.assertRaises(ValueError):
                            runner._contract_engineering_gate(**args)
                    else:
                        self.assertFalse(runner._contract_engineering_gate(**args))
                reviewer.assert_not_called()
                self.assertTrue(checkpoint.exists())
                self.assertEqual(self.event_rows(directory, "step_finished"), [])
                if failure == "operation":
                    self.assertTrue(cp.trace(directory).data["open_operations"])

    def test_contract_and_resume_reject_same_bytes_other_cp_root_before_write_or_model(self):
        from icode.checkpoint import Checkpointer
        from icode.workspace import WorkspaceSession
        root, cp, directory, outcome, report, args = self.gate_fixture()
        other = self.enterContext(temp_workspace()).resolve()
        (other / "changed.py").write_bytes((root / "changed.py").read_bytes())
        plan = VerificationPlan(other, "contract-run", "ENG-CONTRACT", args["plan"].checks)
        checkpoint = Checkpointer(directory, ticket_id="ENG-CONTRACT", step="code", attempt=args["attempt"])
        checkpoint.save(turn_index=1, tool_calls=0, history=[], stop_reason="engineering_verification_pending")
        session = WorkspaceSession("fixture", "ENG-CONTRACT", "contract-run", "snapshot",
            other, other, other, other, other / "manifest.json", (other / ".git", other / ".icode_output"),
            SimpleNamespace(release=lambda: None))
        before = cp.trace(directory).data["event_count"]
        with patch.object(runner, "_run_agent") as model:
            started = runner.run_contract_step(self.settings, backend=FakeBackend([]), workspace=other,
                out_dir=directory, step="code", ticket_id="ENG-CONTRACT", policy=policy_for(other),
                verification_plan=plan, sandbox=args["sandbox"])
            resumed = runner.resume_contract_step(self.settings, backend=FakeBackend([]), workspace=other,
                out_dir=directory, step="code", ticket_id="ENG-CONTRACT", policy=policy_for(other),
                verification_plan=plan, sandbox=args["sandbox"], workspace_session=session,
                change_baseline=args["baseline"])
        model.assert_not_called()
        self.assertEqual(started.error, "engineering_control_workspace_mismatch")
        self.assertEqual(resumed.error, "engineering_control_workspace_mismatch")
        self.assertEqual(cp.trace(directory).data["event_count"], before)
        self.assertTrue(checkpoint.exists())

    def test_build_only_and_required_not_run_plan_never_gain_quality_credit(self):
        for kind in ("build_only", "not_run"):
            with self.subTest(kind=kind):
                root, cp, directory, outcome, report, args = self.gate_fixture()
                if kind == "build_only":
                    checks = (VerificationCheck("build", "build", (sys.executable, "-B", "-m", "unittest"), "exit_status_v1"),)
                    # The existing frozen plan constructor rejects this before
                    # it can become a formal execution input; do not forge it.
                    with self.assertRaisesRegex(ValueError, "insufficient verification plan"):
                        VerificationPlan(root, "contract-run", "ENG-CONTRACT", checks)
                    self.assertEqual(self.event_rows(directory, "verification_recorded"), [])
                    continue
                else:
                    checks = (*args["plan"].checks, VerificationCheck("later", "test",
                        (sys.executable, "-B", "-m", "unittest"), "unittest_summary_v1"))
                    output = b"Ran 1 test in 0.01s\n\nFAILED (failures=1)\n"
                    outcome = replace(outcome, exit_code=1, raw_output=output, output_bytes=len(output))
                args["plan"] = VerificationPlan(root, "contract-run", "ENG-CONTRACT", checks)
                with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome) as dispatch, \
                     patch.object(runner, "_run_task_reviewer") as reviewer:
                    self.assertFalse(runner._contract_engineering_gate(**args))
                self.assertEqual(dispatch.call_count, 1)
                reviewer.assert_not_called()
                row = report.verification_evidence.to_receipt()
                self.assertFalse(row["passed"])
                if kind == "not_run":
                    self.assertEqual(row["run"]["checks"][1]["status"], "not_run")

    def test_native_legacy_code_actual_cp_to_independent_pack(self):
        self._native_legacy_contract_to_pack(("code",))

    @unittest.skipUnless(os.name == "posix", "POSIX captured-scope FD reader")
    def test_native_legacy_deepcheck_actual_cp_to_independent_pack(self):
        self._native_legacy_contract_to_pack(("deepcheck",))

    def _native_legacy_contract_to_pack(self, steps):
        """Legacy entry; actual current CP boundaries, transport only, no native credit."""
        import json
        import subprocess
        from icode.evidence import build_evidence_pack, load_verification_receipts
        from icode.pack_verify import verify_pack
        class TransportSandbox(LandlockSandbox):
            @property
            def policy_contract_ready(self):
                return True
            def prepare_policy(self, policy):
                policy.validate()
        for step in steps:
            with self.subTest(step=step), temp_workspace() as root:
                root = root.resolve(strict=True)
                host_control = self.enterContext(temp_workspace())
                directory = next_out_dir(host_control).resolve()
                directory.mkdir(parents=True, exist_ok=True)
                (root / "changed.py").write_text("value = 0\n", encoding="utf-8")
                for command in (("init", "-q"), ("add", "changed.py"),
                    ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                     "-c", "core.hooksPath=" + str(root / "absent-hooks"), "commit", "-qm", "fixture baseline")):
                    initialized = subprocess.run(["git", "-C", str(root), *command],
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(initialized.returncode, 0, initialized.stderr)
                # Fixture seed is a preexisting legacy ticket, migrated through
                # the real CP. It does not claim the earlier model phases ran.
                legacy = dict(ticket_id="ENG-CONTRACT", requirement="change value", created_at="2026-10-08T00:00:00Z",
                    status=step + "_in_progress", completed_steps=["1", "2", "3"], code_files=["changed.py"],
                    workflow_gate_schema_version=1, thinking_gate_schema_version=1, mcp_gate_schema_version=2,
                    semantic_decisions=[], requirement_deltas=[], project_path=str(root))
                (directory / ".ico_metadata.json").write_text(json.dumps(legacy), encoding="utf-8")
                cp = ControlPlane(self.settings)
                migration = cp.run("migration", "--dir", str(directory), "--apply")
                self.assertTrue(migration.data["ok"])
                (directory / "03_plan_final.md").write_text("# Accepted legacy plan\n", encoding="utf-8")
                outputs = ("04_code_review_fix.md",) if step == "code" else ("05_deepcheck.md",)
                calls = ([{"id": "write", "name": "write_file", "arguments": {"path": "changed.py", "content": "value = 1\n"}}]
                         if step == "code" else [])
                calls += [{"id": "artifact-" + str(index), "name": "submit_artifact", "arguments": {
                    "name": name, "content": "{}" if name.endswith(".json") else "# Actual model fixture report\n"}}
                    for index, name in enumerate(outputs)]
                thought = json.dumps({"step": "Recheck actual current boundary", "next_thought_needed": False})
                backend = FakeBackend([
                    {"tool_calls": calls}, "done",
                    {"tool_calls": [{"id": "read", "name": "read_file", "arguments": {"path": "changed.py"}}]},
                    {"tool_calls": [{"id": "submit", "name": "submit_review", "arguments": {"summary": "Read changed value", "findings": []}}]},
                    "done", thought, thought, thought,
                ])
                sandbox = TransportSandbox("transport-fixture")
                policy = policy_for(root, step)
                control = SimpleNamespace(session=SimpleNamespace(policy=lambda name: policy), safe_point=lambda name: None)
                context = ExecutionContext("ENG-CONTRACT", directory, root, "change value", step + "_in_progress", ())
                check = VerificationCheck("tests", "test", (sys.executable, "-B", "-m", "unittest"), "unittest_summary_v1")
                provider = Mock(return_value=VerificationPlan(root, "contract-run", "ENG-CONTRACT", (check,)))
                output = b"Ran 1 test in 0.01s\n\nOK\n"
                outcome = BrokerResult(0, "", len(output), None, False, True, None, raw_output=output,
                    resource_receipt=dict(schema_version=1, resource="linux_payload_tasks", limit=8, configured=True,
                        payload_started=None, terminal="finished", channel_status="complete"),
                    scope_cleanup_ok=True, violation_observer_status="complete")
                observed = []
                finish_results = []
                fixture_errors = []
                def observed_step(*a, **kw):
                    original_post = kw["post_write"]
                    def fixture_inspection(path, current_step, attempt):
                        import hashlib
                        import importlib.util
                        from icode.artifact_broker import ArtifactBroker
                        from icode.contracts import ContractSet
                        original_post(path, current_step, attempt)
                        # Host fixture driver really reads the one declared
                        # source in every required phase. Declarations/hash
                        # checks prove no semantic judgment or native isolation.
                        spec = importlib.util.spec_from_file_location("contract_fixture_inspection",
                            self.settings.skill_root / "tools" / "inspection_worklist.py")
                        helper = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(helper)
                        metadata = json.loads((path / ".ico_metadata.json").read_text(encoding="utf-8"))
                        worklist = helper.build_worklist(root, metadata["code_files"], step=current_step,
                            ticket_id="ENG-CONTRACT", attempt=attempt, scopes=["."])
                        phases = worklist["required_phases"]
                        self.assertEqual(worklist["unobserved"], [], worklist)
                        digest = ""
                        for phase in phases:
                            for unit in worklist["units"]:
                                for file in unit["files"]:
                                    digest = hashlib.sha256((root / file["path"]).read_bytes()).hexdigest()
                                    self.assertEqual(digest, file["sha256"])
                                    file["reads"][phase] = digest
                        self.assertEqual(helper.validate_worklist(worklist, root, code_files=metadata["code_files"],
                            step=current_step, ticket_id="ENG-CONTRACT", attempt=attempt), [])
                        broker = ArtifactBroker(path, ContractSet.load(self.settings.gates_json).step(current_step), 65536)
                        broker.submit(current_step + "_worklist.json", json.dumps(worklist))
                        prepared = cp.run("inspection", "--dir", str(path), "--step", current_step,
                            "--attempt", attempt, "--phase", "prepare", "--scope", ".")
                        self.assertTrue(prepared.data["ok"], prepared.data)
                        self.assertTrue(prepared.data["resumed"])
                        if current_step == "code":
                            cp.artifact(path, current_step, attempt, "changed.py", ticket_id="ENG-CONTRACT", scope="workspace")
                        if current_step == "deepcheck":
                            coverage = dict(schema_version=1, ticket_id="ENG-CONTRACT", attempt=attempt,
                                review_scope=["changed.py"], coverage_status="complete_within_scope", unobserved=[],
                                dedup_status="not_eligible", dedup_reason="One declared source has no duplicate candidates",
                                dedup_unobserved=[], read_phases={phase: {"changed.py": digest} for phase in phases})
                            broker.submit("deepcheck_coverage.json", json.dumps(coverage))
                    def capture_fixture_error(*args):
                        from icode.control import ControlError
                        try:
                            fixture_inspection(*args)
                        except (AssertionError, ControlError, ValueError) as error:
                            fixture_errors.append(str(error))
                            raise
                    kw["post_write"] = capture_fixture_error
                    report = runner.run_contract_step(*a, **kw)
                    observed.append(report)
                    return report
                actual_finish = runner._finish_step
                def inspect_finish(control, *a, **kw):
                    method = control.step_finish
                    def capture(*args, **kwargs):
                        result = method(*args, **kwargs)
                        finish_results.append(result.data)
                        return result
                    control.step_finish = capture
                    actual_finish(control, *a, **kw)
                with patch("icode.autonomy.chain_steps", return_value=(step,)), \
                     patch("icode.chain.run_contract_step", side_effect=observed_step), \
                     patch.object(runner, "_finish_step", side_effect=inspect_finish), \
                     patch("icode.tools.builtin._uses_resource_dispatch", return_value=True), \
                     patch("icode.tools.builtin._controlled_dispatch", return_value=outcome) as dispatch:
                    result = NativeChainExecutor(self.settings, backend=backend, sandbox=sandbox,
                        verification_plan_provider=provider).execute(context, control)
                provider.assert_called_once_with(context, policy)
                self.assertEqual(dispatch.call_count, 1, str(fixture_errors) + observed[0].render())
                receipts = list(directory.glob(".engineering-*.json"))
                self.assertEqual(len(receipts), 1, result)
                row = load_verification_receipts(receipts)[0]
                self.assertTrue(row["passed"])
                starts = self.event_rows(directory, "step_started")
                finishes = self.event_rows(directory, "step_finished")
                self.assertEqual(len(finishes), 1, str(finish_results) + observed[0].render())
                self.assertEqual(finishes[0]["payload"]["outcome"], "success", str(row["binding"]) + observed[0].render())
                self.assertEqual(row["binding"]["attempt"], starts[0]["payload"]["attempt"])
                self.assertIn(row["fingerprint"], finishes[0]["payload"]["evidence"])
                self.assertFalse(cp.trace(directory).data["open_operations"])
                pack = root / "software-pack"
                exported = build_evidence_pack(directory, dest=pack, gates_json=self.settings.gates_json,
                    verifications=[row])
                self.assertTrue(exported.ok, exported.render())
                self.assertEqual(verify_pack(pack), [])
                outside = self.enterContext(temp_workspace())
                independent = subprocess.run([sys.executable, "-I", "-B", str(pack / "verify.py"), str(pack)],
                    cwd=outside, capture_output=True, text=True, timeout=15)
                self.assertEqual(independent.returncode, 0, independent.stdout + independent.stderr)
                # Existing transition/MCP gates remain independent of this
                # successful engineering/CP step receipt.
                if step == "deepcheck":
                    self.assertIn(result.state, ("blocked", "succeeded"))
