"""Native chain capability forwarding does not synthesize session authority."""

from __future__ import annotations

import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from icode.chain import run_chain
from icode.runner import StepReport
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
