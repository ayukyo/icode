"""Sandbox policy wire contract tests."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.sandbox_policy import (
    NetworkMode,
    PolicyValidationError,
    SandboxPolicy,
    tighten_policy,
)


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

    def test_from_dict_rejects_unknown_fields(self) -> None:
        wire = self.make_policy().to_dict()
        wire["shell"] = True

        with self.assertRaisesRegex(PolicyValidationError, r"unknown=.*shell"):
            SandboxPolicy.from_dict(wire)

    def test_deny_network_mode_rejects_allowed_domains(self) -> None:
        with self.assertRaisesRegex(
            PolicyValidationError,
            r"(?i)(?=.*deny)(?=.*domains)",
        ):
            self.make_policy(allowed_domains=("pypi.org",))

    def test_proxy_allowlist_requires_a_domain(self) -> None:
        with self.assertRaisesRegex(
            PolicyValidationError,
            r"(?i)(?=.*allowlist)(?=.*domain)",
        ):
            self.make_policy(network_mode=NetworkMode.PROXY_ALLOWLIST)

    def test_domains_must_be_exact_dns_hostnames(self) -> None:
        invalid_domains = (
            "https://pypi.org",
            "*.pypi.org",
            "pypi.org/simple",
            "127.0.0.1",
        )

        for domain in invalid_domains:
            with self.subTest(domain=domain):
                with self.assertRaisesRegex(PolicyValidationError, r"(?i)domain"):
                    self.make_policy(
                        network_mode=NetworkMode.PROXY_ALLOWLIST,
                        allowed_domains=(domain,),
                    )

    def test_write_root_must_stay_within_workspace(self) -> None:
        with self.assertRaisesRegex(PolicyValidationError, r"(?i)write root"):
            self.make_policy(write_roots=(self.workspace.parent,))

    def test_resource_limits_must_be_strictly_positive_integers(self) -> None:
        for field_name in (
            "process_limit",
            "wall_timeout_seconds",
            "output_limit_bytes",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(PolicyValidationError, field_name):
                    self.make_policy(**{field_name: 0})

    def test_resource_limits_reject_bool_values(self) -> None:
        for field_name in (
            "process_limit",
            "wall_timeout_seconds",
            "output_limit_bytes",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(PolicyValidationError, field_name):
                    self.make_policy(**{field_name: True})

    def test_protected_path_must_be_covered_by_a_deny_root(self) -> None:
        with self.assertRaisesRegex(PolicyValidationError, r"(?i)protected path"):
            self.make_policy(protected_paths=(self.workspace / "secrets",))

    def test_identity_fields_reject_blank_and_control_characters(self) -> None:
        for field_name in ("run_id", "ticket_id", "step"):
            for value in ("   ", "valid\x00invalid", "line\nbreak"):
                with self.subTest(field_name=field_name, value=value):
                    with self.assertRaisesRegex(PolicyValidationError, field_name):
                        self.make_policy(**{field_name: value})

    def test_allow_root_fully_denied_is_rejected(self) -> None:
        source_root = self.workspace / "src"

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)write root"):
            self.make_policy(
                write_roots=(source_root,),
                deny_write_roots=(self.workspace,),
            )

    def test_read_root_fully_denied_is_rejected(self) -> None:
        source_root = self.workspace / "src"

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)read root"):
            self.make_policy(
                read_roots=(source_root,),
                deny_read_roots=(self.workspace,),
            )

    def test_deny_subpath_takes_precedence_without_invalidating_allow_root(
        self,
    ) -> None:
        policy = self.make_policy()

        self.assertEqual(policy.write_roots, (self.workspace,))
        self.assertEqual(policy.deny_write_roots, (self.workspace / ".git",))

    def test_tighten_policy_allows_narrower_write_root(self) -> None:
        base = self.make_policy()
        candidate = replace(base, write_roots=(self.workspace / "src",))

        self.assertIs(tighten_policy(base, candidate), candidate)

    def test_tighten_policy_allows_proxy_allowlist_to_become_deny(self) -> None:
        base = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("pypi.org",),
        )
        candidate = replace(
            base,
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
        )

        self.assertIs(tighten_policy(base, candidate), candidate)

    def test_tighten_policy_allows_lower_process_limit(self) -> None:
        base = self.make_policy(process_limit=32)
        candidate = replace(base, process_limit=8)

        self.assertIs(tighten_policy(base, candidate), candidate)

    def test_tighten_policy_rejects_wider_write_root(self) -> None:
        base = self.make_policy(write_roots=(self.workspace / "src",))
        candidate = replace(base, write_roots=(self.workspace,))

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_added_domain(self) -> None:
        base = self.make_policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("pypi.org",),
        )
        candidate = replace(
            base,
            allowed_domains=("files.pythonhosted.org", "pypi.org"),
        )

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_higher_limit(self) -> None:
        base = self.make_policy(process_limit=8)
        candidate = replace(base, process_limit=32)

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_removed_deny_rule(self) -> None:
        base = self.make_policy()
        candidate = replace(base, deny_write_roots=())

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_removed_protected_path(self) -> None:
        base = self.make_policy()
        candidate = replace(base, protected_paths=())

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)

    def test_tighten_policy_rejects_identity_change(self) -> None:
        base = self.make_policy()
        candidate = replace(base, run_id="run-002")

        with self.assertRaisesRegex(PolicyValidationError, r"(?i)broadens"):
            tighten_policy(base, candidate)


if __name__ == "__main__":
    unittest.main()
