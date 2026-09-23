"""Sandbox policy wire contract tests."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.sandbox_policy import NetworkMode, SandboxPolicy


class SandboxPolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.workspace = Path(self._temp_dir.name).resolve()

    def make_policy(self, **overrides: object) -> SandboxPolicy:
        values: dict[str, object] = {
            "schema_version": 1,
            "run_id": "run-001",
            "ticket_id": "ICODE-24",
            "step": "code",
            "workspace_root": self.workspace,
            "read_roots": (self.workspace,),
            "write_roots": (self.workspace,),
            "deny_read_roots": (self.workspace / ".git",),
            "deny_write_roots": (self.workspace / ".git",),
            "network_mode": NetworkMode.DENY,
            "allowed_domains": (),
            "process_limit": 32,
            "wall_timeout_seconds": 600,
            "output_limit_bytes": 4 * 1024 * 1024,
            "protected_paths": (self.workspace / ".git",),
        }
        values.update(overrides)
        return SandboxPolicy(**values)

    def test_policy_is_frozen_and_normalizes_duplicate_paths(self) -> None:
        policy = self.make_policy(
            read_roots=(self.workspace / ".", self.workspace, self.workspace)
        )

        with self.assertRaises(FrozenInstanceError):
            policy.run_id = "run-002"  # type: ignore[misc]
        self.assertEqual(policy.read_roots, (self.workspace,))

    def test_canonical_json_round_trip_and_hash_are_stable(self) -> None:
        policy = self.make_policy()
        canonical_json = policy.canonical_json()
        restored = SandboxPolicy.from_dict(json.loads(canonical_json))

        self.assertEqual(restored, policy)
        self.assertEqual(restored.canonical_json(), canonical_json)
        self.assertEqual(policy.canonical_json(), canonical_json)
        self.assertEqual(restored.policy_hash, policy.policy_hash)
        self.assertEqual(policy.policy_hash, policy.policy_hash)
        self.assertEqual(len(policy.policy_hash), 64)

    def test_proxy_allowlist_wire_format_normalizes_domains(self) -> None:
        policy = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("PYPI.org", "files.pythonhosted.org", "pypi.org"),
        )

        wire = policy.to_dict()
        self.assertEqual(wire["network_mode"], "proxy_allowlist")
        self.assertEqual(
            wire["allowed_domains"],
            ["files.pythonhosted.org", "pypi.org"],
        )
        self.assertIsInstance(wire["workspace_root"], str)


if __name__ == "__main__":
    unittest.main()
