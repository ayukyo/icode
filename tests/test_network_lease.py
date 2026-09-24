"""Bounded contract tests for temporary network authorization leases."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.network_lease import (
    MAX_NETWORK_LEASE_TTL_NS,
    NetworkLease,
    NetworkLeaseValidationError,
    NetworkPurpose,
)
from icode.sandbox_policy import NetworkMode, SandboxPolicy


class NetworkLeaseTestCase(unittest.TestCase):
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
            "network_mode": NetworkMode.PROXY_ALLOWLIST,
            "allowed_domains": ("pypi.org", "files.pythonhosted.org"),
            "process_limit": 8,
            "wall_timeout_seconds": 600,
            "output_limit_bytes": 1024 * 1024,
            "protected_paths": (self.workspace / ".git",),
        }
        values.update(overrides)
        return SandboxPolicy(**values)

    def make_lease(self, policy: SandboxPolicy, **overrides: object) -> NetworkLease:
        values: dict[str, object] = {
            "schema_version": 1,
            "lease_id": "a" * 32,
            "approval_id": "approval-001",
            "run_id": policy.run_id,
            "ticket_id": policy.ticket_id,
            "step": policy.step,
            "policy_hash": policy.policy_hash,
            "purpose": NetworkPurpose.PACKAGE_INSTALL,
            "allowed_domains": ("pypi.org",),
            "port": 443,
            "issued_at_monotonic_ns": 1_000_000_000,
            "expires_at_monotonic_ns": 31_000_000_000,
            "generation": 7,
        }
        values.update(overrides)
        return NetworkLease(**values)

    def test_matching_lease_authorizes_only_its_bound_https_destination(self) -> None:
        policy = self.make_policy()
        lease = self.make_lease(policy)

        lease.validate_request(
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="PYPI.ORG",
            port=443,
            now_monotonic_ns=2_000_000_000,
            current_generation=7,
        )

        with self.assertRaises(NetworkLeaseValidationError):
            lease.validate_request(
                policy,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                hostname="attacker.example",
                port=443,
                now_monotonic_ns=2_000_000_000,
                current_generation=7,
            )
        for denied_hostname in ("127.0.0.1", "pypi.org.", "sub.pypi.org"):
            with self.subTest(hostname=denied_hostname):
                with self.assertRaises(NetworkLeaseValidationError):
                    lease.validate_request(
                        policy,
                        purpose=NetworkPurpose.PACKAGE_INSTALL,
                        hostname=denied_hostname,
                        port=443,
                        now_monotonic_ns=2_000_000_000,
                        current_generation=7,
                    )

    def test_lease_is_bound_to_policy_identity_and_hash(self) -> None:
        policy = self.make_policy()
        lease = self.make_lease(policy)
        mismatches = (
            (replace(policy, run_id="run-002"), "run-002"),
            (replace(policy, ticket_id="ICODE-25"), "ICODE-25"),
            (replace(policy, step="verify"), "verify"),
            (replace(policy, allowed_domains=("pypi.org",)), "same identity, new policy hash"),
        )
        for altered_policy, label in mismatches:
            with self.subTest(mismatch=label):
                with self.assertRaises(NetworkLeaseValidationError):
                    lease.validate_request(
                        altered_policy,
                        purpose=NetworkPurpose.PACKAGE_INSTALL,
                        hostname="pypi.org",
                        port=443,
                        now_monotonic_ns=2_000_000_000,
                        current_generation=7,
                    )

    def test_expiry_generation_and_network_denial_fail_closed(self) -> None:
        policy = self.make_policy()
        lease = self.make_lease(policy)
        for now, generation, altered_policy in (
            (31_000_000_000, 7, policy),
            (2_000_000_000, 8, policy),
            (2_000_000_000, 7, replace(policy, network_mode=NetworkMode.DENY,
                                        allowed_domains=())),
        ):
            with self.subTest(now=now, generation=generation):
                with self.assertRaises(NetworkLeaseValidationError):
                    lease.validate_request(
                        altered_policy,
                        purpose=NetworkPurpose.PACKAGE_INSTALL,
                        hostname="pypi.org",
                        port=443,
                        now_monotonic_ns=now,
                        current_generation=generation,
                    )

    def test_lease_rejects_wrong_purpose_non_https_and_unlisted_domains(self) -> None:
        policy = self.make_policy()
        lease = self.make_lease(policy)
        for purpose, hostname, port in (
            (NetworkPurpose.PACKAGE_INSTALL, "pypi.org", 80),
            (NetworkPurpose.PACKAGE_INSTALL, "files.pythonhosted.org", 443),
            (NetworkPurpose.WEB_READ, "pypi.org", 443),
        ):
            with self.subTest(purpose=purpose, hostname=hostname, port=port):
                with self.assertRaises(NetworkLeaseValidationError):
                    lease.validate_request(
                        policy,
                        purpose=purpose,
                        hostname=hostname,
                        port=port,
                        now_monotonic_ns=2_000_000_000,
                        current_generation=7,
                    )

    def test_lease_rejects_invalid_clock_and_generation_types(self) -> None:
        policy = self.make_policy()
        lease = self.make_lease(policy)
        for now, generation in ((True, 7), (-1, 7), (2_000_000_000, True)):
            with self.subTest(now=now, generation=generation):
                with self.assertRaises(NetworkLeaseValidationError):
                    lease.validate_request(
                        policy,
                        purpose=NetworkPurpose.PACKAGE_INSTALL,
                        hostname="pypi.org",
                        port=443,
                        now_monotonic_ns=now,
                        current_generation=generation,
                    )

    def test_lease_is_immutable_and_caps_lifetime(self) -> None:
        policy = self.make_policy()
        lease = self.make_lease(policy)
        with self.assertRaises(FrozenInstanceError):
            lease.generation = 8  # type: ignore[misc]

        with self.assertRaises(NetworkLeaseValidationError):
            self.make_lease(
                policy,
                expires_at_monotonic_ns=(
                    1_000_000_000 + MAX_NETWORK_LEASE_TTL_NS + 1
                ),
            )

    def test_lease_rejects_invalid_scope_values(self) -> None:
        policy = self.make_policy()
        for field_name, value in (
            ("lease_id", "not-a-random-id"),
            ("purpose", "unrestricted"),
            ("allowed_domains", ("*.pypi.org",)),
            ("port", 80),
            ("generation", True),
            ("expires_at_monotonic_ns", 1_000_000_000),
        ):
            with self.subTest(field=field_name):
                with self.assertRaises(NetworkLeaseValidationError):
                    self.make_lease(policy, **{field_name: value})


if __name__ == "__main__":
    unittest.main()
