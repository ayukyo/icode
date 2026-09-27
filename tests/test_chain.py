"""Native chain capability forwarding does not synthesize session authority."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from icode.chain import run_chain
from icode.runner import StepReport
from icode.workspace import GitWorkspaceIdentity, WorkspaceSession
from tests._support import temp_workspace


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
