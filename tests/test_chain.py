"""Native chain capability forwarding does not synthesize session authority."""

from __future__ import annotations

import unittest
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from icode import runner
from icode.chain import run_chain
from icode.engineering_verification import VerificationCheck, VerificationPlan
from icode.isolation import LandlockSandbox
from icode.runner import StepReport
from icode.tools.base import ToolContext
from icode.tools.builtin import _git_status_available, default_registry, git_status
from icode.workspace import GitWorkspaceIdentity, WorkspaceSession
from tests._support import temp_workspace


class TestChainReviewArtifactHonesty(unittest.TestCase):
    """Exercise the real chain callback without inventing model artifacts."""

    def _post(self, out_dir: Path):
        def step_runner(*args, **kwargs):
            kwargs["post_write"](out_dir, "review", "review-attempt")
            return StepReport(step="review", ok=False, out_dir=str(out_dir), error="stop")

        with patch("icode.chain.ContractSet.load", return_value=object()), patch(
            "icode.chain._snapshot", return_value={},
        ), patch("icode.chain.run_contract_step", side_effect=step_runner):
            return run_chain(
                SimpleNamespace(gates_json=out_dir / "gates.json"),
                backend=object(), workspace=out_dir, ticket_id="ticket",
                requirement="review", steps=("review",),
            )

    def test_review_post_all_missing_keeps_artifacts_missing(self) -> None:
        with temp_workspace() as out_dir:
            report = self._post(out_dir)
            self.assertFalse((out_dir / "02_review.md").exists())
            self.assertEqual(list(out_dir.glob("review_round_*.json")), [])
            self.assertFalse((out_dir / "review_manifest.json").exists())
            self.assertTrue(any("装配：失败" in note for note in report.notes))

    def test_review_post_body_only_never_invents_clean_round(self) -> None:
        with temp_workspace() as out_dir:
            body = "# Actual model review\n\nTests need boundary coverage.\n"
            (out_dir / "02_review.md").write_text(body, encoding="utf-8")
            report = self._post(out_dir)
            self.assertEqual((out_dir / "02_review.md").read_text(encoding="utf-8"), body)
            self.assertEqual(list(out_dir.glob("review_round_*.json")), [])
            self.assertFalse((out_dir / "review_manifest.json").exists())
            self.assertTrue(any("装配：失败" in note for note in report.notes))

    def test_review_post_real_round_assembles_without_fabricating_body(self) -> None:
        with temp_workspace() as out_dir:
            detail = {"round": 1, "new_issues": ["Missing boundary test"],
                      "refuted_issues": [], "pending_verification": []}
            (out_dir / "review_round_1.json").write_text(json.dumps(detail), encoding="utf-8")
            self._post(out_dir)
            self.assertFalse((out_dir / "02_review.md").exists())
            manifest = json.loads((out_dir / "review_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["rounds"][0]["new_issues"], 1)
            self.assertEqual(manifest["rounds"][0]["origin_attempt"], "review-attempt")


class TestChainGitIdentityForwarding(unittest.TestCase):
    def test_forwards_host_identity_to_step_only_when_supplied(self) -> None:
        with temp_workspace() as root:
            identity = GitWorkspaceIdentity(
                checkout_root=root, code_root=root, workspace_root=root,
                top_level=root, common_dir=root / "common", git_dir=root / "git",
                revision="a" * 40, identity_token="secret",
                source_relative_path=Path("."),
            )
            session = WorkspaceSession(
                project_id="project", ticket_id="ticket", run_id="run-1",
                kind="git_worktree", source_root=root, workspace_root=root,
                runtime_root=root / "runtime", receipts_root=root / "receipts",
                manifest_path=root / "workspace.json",
                protected_paths=(root / ".git", identity.common_dir), lease=object(),
                git_status_identity=identity,
            )
            policy = session.policy("plan")
            calls: list[dict] = []

            def step_runner(*args, **kwargs):
                calls.append(kwargs)
                return StepReport(step="plan", ok=False, out_dir="", error="stop")

            with patch("icode.chain.ContractSet.load", return_value=object()), patch(
                "icode.chain._snapshot", return_value={},
            ), patch("icode.chain.run_contract_step", side_effect=step_runner):
                run_chain(SimpleNamespace(gates_json=root / "gates.json"), backend=object(), workspace=root,
                          ticket_id="ticket", requirement="status", steps=("plan",),
                          policy=policy, workspace_session=session)
                run_chain(SimpleNamespace(gates_json=root / "gates.json"), backend=object(), workspace=root,
                          ticket_id="ticket", requirement="status", steps=("plan",))
                session.run_id = "stale-run"
                run_chain(SimpleNamespace(gates_json=root / "gates.json"), backend=object(), workspace=root,
                          ticket_id="ticket", requirement="status", steps=("plan",),
                          policy=policy, workspace_session=session)

            self.assertIs(calls[0]["workspace_session"], session)
            self.assertIsNone(calls[1]["workspace_session"])
            self.assertIsNone(calls[2]["workspace_session"])
            with self.assertRaises(TypeError):
                run_chain(SimpleNamespace(gates_json=root / "gates.json"), backend=object(), workspace=root,
                          ticket_id="ticket", requirement="status", steps=("plan",),
                          git_status_identity=identity)


class TestChainPolicySessionForwarding(unittest.TestCase):
    POLICY_STEPS = ("plan", "audit", "merge", "review")

    def _session(self, root, *, kind="snapshot"):
        identity = None
        protected = ()
        if kind == "git_worktree":
            identity = GitWorkspaceIdentity(
                checkout_root=root, code_root=root, workspace_root=root,
                top_level=root, common_dir=root / "common", git_dir=root / "git",
                revision="a" * 40, identity_token="secret",
                source_relative_path=Path("."),
            )
            protected = (root / ".git", identity.common_dir)
        return WorkspaceSession(
            project_id="project", ticket_id="ticket", run_id="run-1",
            kind=kind, source_root=root, workspace_root=root,
            runtime_root=root / "runtime", receipts_root=root / "receipts",
            manifest_path=root / "workspace.json", protected_paths=protected,
            lease=Mock(), git_status_identity=identity,
        )

    def _invoke(self, root, step, policy, session, *, record=True, plan=None):
        calls = []

        def step_runner(*args, **kwargs):
            calls.append(kwargs)
            return StepReport(step=step, ok=False, out_dir="", error="stop")

        with patch("icode.chain.ControlPlane"), patch(
            "icode.chain.ContractSet.load", return_value=object(),
        ), patch("icode.chain._snapshot", return_value={}):
            kwargs = dict(
                backend=object(), workspace=root, ticket_id="ticket",
                requirement="policy session", steps=(step,), policy=policy,
                workspace_session=session, verification_plan=plan,
            )
            settings = SimpleNamespace(gates_json=root / "gates.json")
            if record:
                with patch("icode.chain.run_contract_step", side_effect=step_runner):
                    report = run_chain(settings, **kwargs)
            else:
                # Leave run_contract_step real: its early identity gate must fire.
                with patch.object(runner, "ControlPlane") as downstream_cp:
                    report = run_chain(settings, **kwargs)
                    downstream_cp.assert_not_called()
        return report, calls

    def test_snapshot_and_git_policy_steps_borrow_original_objects(self):
        with temp_workspace() as root:
            for kind in ("snapshot", "git_worktree"):
                session = self._session(root, kind=kind)
                for step in self.POLICY_STEPS:
                    with self.subTest(kind=kind, step=step), patch.object(
                        session, "close",
                    ) as close:
                        policy = session.policy(step)
                        report, calls = self._invoke(root, step, policy, session)
                        self.assertEqual(len(calls), 1)
                        self.assertIs(calls[0]["workspace_session"], session)
                        self.assertIs(calls[0]["policy"], policy)
                        self.assertEqual(report.reason, "stop")
                        close.assert_not_called()
                        session.lease.release.assert_not_called()

    def test_custom_resource_policy_is_not_replaced_or_git_filtered(self):
        with temp_workspace() as root:
            for kind in ("snapshot", "git_worktree"):
                session = self._session(root, kind=kind)
                for step in self.POLICY_STEPS:
                    with self.subTest(kind=kind, step=step):
                        policy = session.policy(
                            step, process_limit=8, wall_timeout_seconds=30,
                            output_limit_bytes=65536,
                        )
                        self.assertNotEqual(policy, session.policy(step))
                        _, calls = self._invoke(root, step, policy, session)
                        self.assertEqual(len(calls), 1)
                        self.assertIs(calls[0]["workspace_session"], session)
                        self.assertIs(calls[0]["policy"], policy)
                        session.lease.release.assert_not_called()

    def test_nonengineering_invalid_session_or_missing_policy_is_none(self):
        with temp_workspace() as root:
            for step in self.POLICY_STEPS:
                session = self._session(root)
                policy = session.policy(step)
                cases = [("absent", None), ("not-session", object())]
                for label, changes in (
                    ("stale-run", {"run_id": "stale"}),
                    ("wrong-ticket", {"ticket_id": "other"}),
                    ("wrong-root", {"workspace_root": root / "other"}),
                ):
                    cases.append((label, replace(session, **changes)))
                for label, candidate in cases:
                    with self.subTest(step=step, label=label):
                        _, calls = self._invoke(root, step, policy, candidate)
                        self.assertEqual(len(calls), 1)
                        self.assertIsNone(calls[0]["workspace_session"])
                _, calls = self._invoke(root, step, None, session)
                self.assertEqual(len(calls), 1)
                self.assertIsNone(calls[0]["workspace_session"])

    def test_engineering_preserves_matching_and_wrong_objects(self):
        with temp_workspace() as root:
            session = self._session(root)
            for step in ("code", "deepcheck"):
                policy = session.policy(step)
                for candidate in (
                    session, replace(session, run_id="wrong"),
                    replace(session, ticket_id="other"),
                    replace(session, workspace_root=root / "other"), object(),
                ):
                    with self.subTest(step=step, candidate=type(candidate).__name__):
                        _, calls = self._invoke(root, step, policy, candidate)
                        self.assertEqual(len(calls), 1)
                        self.assertIs(calls[0]["workspace_session"], candidate)
                        self.assertIs(calls[0]["policy"], policy)
                _, calls = self._invoke(root, step, None, session)
                self.assertIsNone(calls[0]["workspace_session"])

    def test_policy_wrong_step_ticket_or_root_keeps_chain_early_rejection(self):
        with temp_workspace() as root:
            session = self._session(root)
            policy = session.policy("plan")
            for changes in (
                {"step": "audit"}, {"ticket_id": "other"},
                {"workspace_root": root / "other", "read_roots": (root / "other",),
                 "write_roots": (root / "other",)},
            ):
                with self.subTest(changes=changes), patch(
                    "icode.chain.run_contract_step",
                ) as downstream:
                    with self.assertRaisesRegex(ValueError, "单步链路身份不匹配"):
                        self._invoke(root, "plan", replace(policy, **changes), session,
                                     record=False)
                    downstream.assert_not_called()

    def test_wrong_engineering_session_real_runner_refuses_before_cp(self):
        with temp_workspace() as root:
            session = self._session(root)
            check = VerificationCheck(
                "tests", "test", (sys.executable, "-B", "-m", "unittest"),
                "unittest_summary_v1",
            )
            plan = VerificationPlan(root, "run-1", "ticket", (check,))
            for step in ("code", "deepcheck"):
                for candidate in (replace(session, run_id="wrong"), object()):
                    with self.subTest(step=step, candidate=type(candidate).__name__):
                        report, calls = self._invoke(
                            root, step, session.policy(step), candidate,
                            record=False, plan=plan,
                        )
                        self.assertEqual(calls, [])
                        self.assertEqual(report.reason, "verification_session_identity_mismatch")
                        self.assertEqual(report.stopped_at, step)
                        self.assertFalse(report.delivered)

    def test_git_eligibility_remains_independent_of_session_forwarding(self):
        with temp_workspace() as root:
            session = self._session(root, kind="git_worktree")
            sandbox = LandlockSandbox("not-executed-helper")
            with patch("icode.tools.builtin.sys.platform", "linux"), patch(
                "icode.tools.builtin.execute_git_status",
            ) as broker:
                default = session.policy("plan")
                ctx = ToolContext(root=root, sandbox=sandbox, policy=default,
                                  workspace_session=session)
                self.assertTrue(_git_status_available(ctx))
                self.assertIn("git_status", default_registry(git_status_context=ctx).names())
                custom = session.policy("plan", process_limit=8,
                    wall_timeout_seconds=30, output_limit_bytes=65536)
                ctx.policy = custom
                self.assertFalse(_git_status_available(ctx))
                self.assertNotIn("git_status", default_registry(git_status_context=ctx).names())
                result = git_status(ctx)
                self.assertFalse(result.ok)
                self.assertEqual(result.meta["error"], "git_broker_unavailable")
                for step, read_only in (("review", False), ("plan", True), ("review", True)):
                    with self.subTest(step=step, read_only=read_only):
                        ctx.policy = session.policy(step)
                        ctx.read_only_workspace = read_only
                        self.assertFalse(_git_status_available(ctx))
                        self.assertNotIn("git_status", default_registry(git_status_context=ctx).names())
                        result = git_status(ctx)
                        self.assertFalse(result.ok)
                        self.assertEqual(result.meta["error"], "git_broker_unavailable")
                broker.assert_not_called()
