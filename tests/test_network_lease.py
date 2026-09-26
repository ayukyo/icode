"""Bounded contract tests for temporary network authorization leases."""

from __future__ import annotations

import socket
import threading
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.approvals import DenyAllApprover, ScriptedApprover
from icode.network_lease import (
    MAX_NETWORK_LEASE_TTL_NS,
    NETWORK_LEASE_SCHEMA_VERSION,
    NetworkLease,
    NetworkLeaseApprovalDenied,
    NetworkLeaseAuthority,
    NetworkLeaseConnectionCloseError,
    NetworkLeaseValidationError,
    NetworkPurpose,
)
from icode.sandbox_policy import NetworkMode, SandboxPolicy


class NetworkLeaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.workspace = Path(self._temp_dir.name).resolve()

    def make_tcp_pair(self) -> tuple[socket.socket, socket.socket]:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.settimeout(1.0)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)

        peer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        peer.settimeout(1.0)
        self.addCleanup(peer.close)
        peer.connect(listener.getsockname())
        accepted, _ = listener.accept()
        accepted.settimeout(1.0)
        self.addCleanup(accepted.close)
        return peer, accepted

    @staticmethod
    def recv_exact(sock: socket.socket, size: int) -> bytes:
        received = bytearray()
        while len(received) < size:
            chunk = sock.recv(size - len(received))
            if not chunk:
                break
            received.extend(chunk)
        return bytes(received)

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
            "process_limit": 8,
            "wall_timeout_seconds": 600,
            "output_limit_bytes": 1024 * 1024,
            "protected_paths": (self.workspace / ".git",),
        }
        values.update(overrides)
        return SandboxPolicy(**values)

    def make_deny_policy(self, **overrides: object) -> SandboxPolicy:
        return self.make_policy(
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            **overrides,
        )

    def make_lease(self, policy: SandboxPolicy, **overrides: object) -> NetworkLease:
        values: dict[str, object] = {
            "schema_version": NETWORK_LEASE_SCHEMA_VERSION,
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

    def test_legacy_lease_semantics_are_rejected_by_schema_version(self) -> None:
        with self.assertRaises(NetworkLeaseValidationError):
            self.make_lease(
                self.make_deny_policy(),
                schema_version=1,
            )
        with self.assertRaises(NetworkLeaseValidationError):
            self.make_lease(
                self.make_deny_policy(),
                schema_version=True,
            )

    def test_lease_is_bound_to_policy_identity_and_hash(self) -> None:
        policy = self.make_policy()
        lease = self.make_lease(policy)
        mismatches = (
            (replace(policy, run_id="run-002"), "run-002"),
            (replace(policy, ticket_id="ICODE-25"), "ICODE-25"),
            (replace(policy, step="verify"), "verify"),
            (
                replace(policy, output_limit_bytes=policy.output_limit_bytes + 1),
                "same identity, new policy hash",
            ),
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
            (
                2_000_000_000,
                7,
                replace(
                    policy,
                    network_mode=NetworkMode.PROXY_ALLOWLIST,
                    allowed_domains=("pypi.org",),
                ),
            ),
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

    def test_authority_requires_explicit_approval_and_binds_the_request(self) -> None:
        policy = self.make_policy()
        approver = ScriptedApprover([True])
        authority = NetworkLeaseAuthority()

        grant = authority.request_lease(
            policy,
            approver=approver,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("PYPI.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )

        self.assertEqual(len(approver.seen), 1)
        request = approver.seen[0]
        self.assertEqual(request.tool, "temporary_network_access")
        self.assertEqual(request.opclass, "network_authorization")
        self.assertEqual(request.arguments["lease_request_id"], grant.lease.approval_id)
        self.assertEqual(request.arguments["domains"], ["pypi.org"])
        self.assertEqual(grant.lease.expires_at_monotonic_ns, 62_000_000_000)
        authority.verify_request(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=2_000_000_001,
        )

    def test_host_only_lease_overlay_binds_denied_base_policy(self) -> None:
        policy = self.make_deny_policy()
        approver = ScriptedApprover([True])
        authority = NetworkLeaseAuthority()

        grant = authority.request_lease(
            policy,
            approver=approver,
            purpose=NetworkPurpose.WEB_READ,
            allowed_domains=("docs.example",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )

        self.assertIs(policy.network_mode, NetworkMode.DENY)
        self.assertEqual(policy.allowed_domains, ())
        self.assertEqual(grant.lease.policy_hash, policy.policy_hash)
        authority.verify_request(
            grant,
            policy,
            purpose=NetworkPurpose.WEB_READ,
            hostname="docs.example",
            port=443,
            now_monotonic_ns=2_000_000_001,
        )
        with self.assertRaises(NetworkLeaseValidationError):
            authority.verify_request(
                grant,
                policy,
                purpose=NetworkPurpose.WEB_READ,
                hostname="sub.docs.example",
                port=443,
                now_monotonic_ns=2_000_000_001,
            )

    def test_host_only_lease_rejects_non_denied_policy_and_invalid_domains(self) -> None:
        authority = NetworkLeaseAuthority()
        denied_policy = self.make_deny_policy()
        invalid_domain_approver = ScriptedApprover([True])

        with self.assertRaises(NetworkLeaseValidationError):
            authority.request_lease(
                denied_policy,
                approver=invalid_domain_approver,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("127.0.0.1",),
                ttl_seconds=60,
                now_monotonic_ns=2_000_000_000,
            )
        self.assertEqual(invalid_domain_approver.seen, [])

        with self.assertRaises(NetworkLeaseValidationError):
            authority.request_lease(
                self.make_policy(
                    network_mode=NetworkMode.PROXY_ALLOWLIST,
                    allowed_domains=("pypi.org",),
                ),
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("pypi.org",),
                ttl_seconds=60,
                now_monotonic_ns=2_000_000_000,
            )

    def test_deny_all_approval_never_issues_a_lease(self) -> None:
        with self.assertRaises(NetworkLeaseApprovalDenied):
            NetworkLeaseAuthority().request_lease(
                self.make_policy(),
                approver=DenyAllApprover(),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("pypi.org",),
                ttl_seconds=60,
                now_monotonic_ns=2_000_000_000,
            )

    def test_approval_failure_and_invalid_domains_fail_closed(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()

        class BrokenApprover:
            def ask(inner_self: object, request: object) -> bool:
                raise RuntimeError("approval UI unavailable")

        with self.assertRaises(NetworkLeaseApprovalDenied):
            authority.request_lease(
                policy,
                approver=BrokenApprover(),  # type: ignore[arg-type]
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("pypi.org",),
                ttl_seconds=60,
                now_monotonic_ns=2_000_000_000,
            )

        approver = ScriptedApprover([True])
        with self.assertRaises(NetworkLeaseValidationError):
            authority.request_lease(
                policy,
                approver=approver,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("127.0.0.1",),
                ttl_seconds=60,
                now_monotonic_ns=2_000_000_000,
            )
        self.assertEqual(approver.seen, [])

    def test_authority_rejects_tampering_restart_replay_expiry_and_revocation(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )

        with self.assertRaises(NetworkLeaseValidationError):
            authority.verify_request(
                replace(grant, signature="0" * 64), policy,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                hostname="pypi.org", port=443, now_monotonic_ns=3_000_000_000,
            )
        changed_scope = replace(
            grant,
            lease=replace(grant.lease, allowed_domains=("files.pythonhosted.org",)),
        )
        with self.assertRaises(NetworkLeaseValidationError):
            authority.verify_request(
                changed_scope, policy, purpose=NetworkPurpose.PACKAGE_INSTALL,
                hostname="files.pythonhosted.org", port=443,
                now_monotonic_ns=3_000_000_000,
            )
        with self.assertRaises(NetworkLeaseValidationError):
            NetworkLeaseAuthority().verify_request(
                grant, policy, purpose=NetworkPurpose.PACKAGE_INSTALL,
                hostname="pypi.org", port=443, now_monotonic_ns=3_000_000_000,
            )
        with self.assertRaises(NetworkLeaseValidationError):
            authority.verify_request(
                grant, policy, purpose=NetworkPurpose.PACKAGE_INSTALL,
                hostname="pypi.org", port=443, now_monotonic_ns=62_000_000_000,
            )

        authority.revoke(policy)
        with self.assertRaises(NetworkLeaseValidationError):
            authority.verify_request(
                grant, policy, purpose=NetworkPurpose.PACKAGE_INSTALL,
                hostname="pypi.org", port=443, now_monotonic_ns=3_000_000_000,
            )

        renewed = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=3_000_000_000,
        )
        self.assertEqual(renewed.lease.generation, 2)
        authority.verify_request(
            renewed, policy, purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org", port=443, now_monotonic_ns=3_000_000_001,
        )

    def test_active_connection_is_closed_when_its_lease_is_revoked(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        closed: list[str] = []

        def close_tunnel() -> bool:
            closed.append("closed")
            return True

        handle = authority.register_active_connection(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            close=close_tunnel,
        )

        self.assertEqual(closed, [])
        self.assertEqual(authority.revoke(policy), 2)
        self.assertEqual(closed, ["closed"])
        self.assertFalse(authority.release_active_connection(handle))
        with self.assertRaises(NetworkLeaseValidationError):
            authority.verify_request(
                grant,
                policy,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                hostname="pypi.org",
                port=443,
                now_monotonic_ns=3_000_000_001,
            )

    def test_revoke_closes_real_tcp_tunnel_endpoints(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        client_peer, proxy_client = self.make_tcp_pair()
        proxy_upstream, upstream_peer = self.make_tcp_pair()

        register_sockets = getattr(authority, "register_active_sockets", None)
        self.assertTrue(callable(register_sockets), "authority lacks real-socket registration")
        handle = register_sockets(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            sockets=(proxy_client, proxy_upstream),
        )
        client_peer.sendall(b"client-alive")
        self.assertEqual(self.recv_exact(proxy_client, 12), b"client-alive")
        upstream_peer.sendall(b"upstream-alive")
        self.assertEqual(self.recv_exact(proxy_upstream, 14), b"upstream-alive")

        authority.revoke(policy)

        self.assertEqual(client_peer.recv(1), b"")
        self.assertEqual(upstream_peer.recv(1), b"")
        self.assertFalse(authority.release_active_connection(handle))

    def test_registration_rejects_distinct_socket_objects_sharing_one_fd(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        _, proxy_socket = self.make_tcp_pair()
        aliased_socket = socket.socket(fileno=proxy_socket.fileno())
        self.assertIsNot(aliased_socket, proxy_socket)
        self.assertEqual(aliased_socket.fileno(), proxy_socket.fileno())

        try:
            with self.assertRaisesRegex(NetworkLeaseValidationError, "duplicate"):
                authority.register_active_sockets(
                    grant,
                    policy,
                    purpose=NetworkPurpose.PACKAGE_INSTALL,
                    hostname="pypi.org",
                    port=443,
                    now_monotonic_ns=3_000_000_000,
                    sockets=(proxy_socket, aliased_socket),
                )
        finally:
            # Both wrappers refer to the same descriptor; leave its ownership
            # with proxy_socket so the test cleanup closes it exactly once.
            aliased_socket.detach()

    def test_revoke_closes_socket_after_original_wrapper_detaches(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        client_peer, proxy_socket = self.make_tcp_pair()
        handle = authority.register_active_sockets(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            sockets=(proxy_socket,),
        )

        detached_socket = socket.socket(fileno=proxy_socket.detach())
        self.addCleanup(detached_socket.close)
        detached_socket.sendall(b"still-active")
        self.assertEqual(self.recv_exact(client_peer, 12), b"still-active")

        authority.revoke(policy)

        client_peer.setblocking(False)
        try:
            observed = client_peer.recv(1)
        except BlockingIOError:
            observed = None
        self.assertEqual(observed, b"")
        self.assertFalse(authority.release_active_connection(handle))

    def test_registration_rejects_unconnected_or_non_tcp_sockets(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        unconnected_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(unconnected_tcp.close)
        unconnected_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(unconnected_udp.close)
        connected_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        connected_udp.connect(("127.0.0.1", 9))
        self.addCleanup(connected_udp.close)

        for candidate in (listener, unconnected_tcp, unconnected_udp, connected_udp):
            with self.subTest(socket_type=candidate.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)):
                with self.assertRaisesRegex(
                    NetworkLeaseValidationError, "connected IPv4/IPv6 TCP"
                ):
                    authority.register_active_sockets(
                        grant,
                        policy,
                        purpose=NetworkPurpose.PACKAGE_INSTALL,
                        hostname="pypi.org",
                        port=443,
                        now_monotonic_ns=3_000_000_000,
                        sockets=(candidate,),
                    )

    def test_expiry_sweep_closes_real_tcp_tunnel_endpoints(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=1,
            now_monotonic_ns=2_000_000_000,
        )
        client_peer, proxy_client = self.make_tcp_pair()
        proxy_upstream, upstream_peer = self.make_tcp_pair()

        register_sockets = getattr(authority, "register_active_sockets", None)
        self.assertTrue(callable(register_sockets), "authority lacks real-socket registration")
        handle = register_sockets(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=2_500_000_000,
            sockets=(proxy_client, proxy_upstream),
        )
        client_peer.sendall(b"before-expiry")
        self.assertEqual(self.recv_exact(proxy_client, 13), b"before-expiry")
        upstream_peer.sendall(b"before-expiry")
        self.assertEqual(self.recv_exact(proxy_upstream, 13), b"before-expiry")

        self.assertEqual(authority.close_expired_connections(3_000_000_000), 1)

        self.assertEqual(client_peer.recv(1), b"")
        self.assertEqual(upstream_peer.recv(1), b"")
        self.assertFalse(authority.release_active_connection(handle))

    def test_normal_connection_release_is_idempotent_and_does_not_close_twice(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        close_calls = 0

        def close_tunnel() -> bool:
            nonlocal close_calls
            close_calls += 1
            return True

        handle = authority.register_active_connection(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            close=close_tunnel,
        )

        self.assertTrue(authority.release_active_connection(handle))
        self.assertFalse(authority.release_active_connection(handle))
        self.assertEqual(close_calls, 0)
        self.assertEqual(authority.revoke(policy), 2)
        self.assertEqual(close_calls, 0)

        with self.assertRaises(NetworkLeaseValidationError):
            authority.release_active_connection(object())

    def test_expired_connections_are_closed_without_closing_live_leases(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        closed: list[str] = []

        def close_tunnel() -> bool:
            closed.append("expired")
            return True

        handle = authority.register_active_connection(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            close=close_tunnel,
        )

        self.assertEqual(authority.close_expired_connections(61_999_999_999), 0)
        self.assertEqual(closed, [])
        self.assertEqual(authority.close_expired_connections(62_000_000_000), 1)
        self.assertEqual(closed, ["expired"])
        self.assertFalse(authority.release_active_connection(handle))

    def test_new_connection_registration_sweeps_expired_tunnels_first(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        old_grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=1,
            now_monotonic_ns=1_000_000_000,
        )
        closed: list[str] = []

        def close_old_tunnel() -> bool:
            closed.append("old")
            return True

        old_handle = authority.register_active_connection(
            old_grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=1_500_000_000,
            close=close_old_tunnel,
        )
        new_grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=3_000_000_000,
        )

        new_handle = authority.register_active_connection(
            new_grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_001,
            close=lambda: True,
        )

        self.assertEqual(closed, ["old"])
        self.assertFalse(authority.release_active_connection(old_handle))
        self.assertTrue(authority.release_active_connection(new_handle))

    def test_revocation_blocks_new_approval_until_active_close_finishes(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        close_started = threading.Event()
        allow_close = threading.Event()
        revoke_finished = threading.Event()
        revoke_errors: list[Exception] = []

        def close_tunnel() -> bool:
            close_started.set()
            return allow_close.wait(timeout=3)

        authority.register_active_connection(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            close=close_tunnel,
        )

        def revoke() -> None:
            try:
                authority.revoke(policy)
            except Exception as error:  # noqa: BLE001 - captured for assertion.
                revoke_errors.append(error)
            finally:
                revoke_finished.set()

        revoke_thread = threading.Thread(target=revoke)
        revoke_thread.start()
        self.assertTrue(close_started.wait(timeout=1))
        try:
            request_finished = threading.Event()
            request_errors: list[Exception] = []

            def request_new_lease() -> None:
                try:
                    authority.request_lease(
                        policy,
                        approver=ScriptedApprover([True]),
                        purpose=NetworkPurpose.PACKAGE_INSTALL,
                        allowed_domains=("pypi.org",),
                        ttl_seconds=60,
                        now_monotonic_ns=4_000_000_000,
                    )
                except Exception as error:  # noqa: BLE001 - captured for assertion.
                    request_errors.append(error)
                finally:
                    request_finished.set()

            request_thread = threading.Thread(target=request_new_lease)
            request_thread.start()
            self.assertTrue(request_finished.wait(timeout=1))
            request_thread.join(timeout=1)
            self.assertFalse(request_thread.is_alive())
            self.assertEqual(len(request_errors), 1)
            self.assertIsInstance(request_errors[0], NetworkLeaseValidationError)
        finally:
            allow_close.set()
        revoke_thread.join(timeout=2)
        self.assertTrue(revoke_finished.is_set())
        self.assertFalse(revoke_thread.is_alive())
        self.assertEqual(revoke_errors, [])

    def test_close_failure_keeps_scope_revoked_and_can_be_retried(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True, True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        close_attempts = 0

        def close_tunnel() -> bool:
            nonlocal close_attempts
            close_attempts += 1
            if close_attempts == 1:
                raise OSError("raw socket detail must not escape")
            return True

        authority.register_active_connection(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            close=close_tunnel,
        )

        with self.assertRaises(NetworkLeaseConnectionCloseError) as raised:
            authority.revoke(policy)
        self.assertEqual(raised.exception.failure_count, 1)
        self.assertNotIn("raw socket detail", str(raised.exception))
        with self.assertRaises(NetworkLeaseValidationError):
            authority.request_lease(
                policy,
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("pypi.org",),
                ttl_seconds=60,
                now_monotonic_ns=4_000_000_000,
            )

        self.assertEqual(authority.close_expired_connections(4_000_000_000), 1)
        self.assertEqual(close_attempts, 2)
        authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=5_000_000_000,
        )

    def test_connection_close_callback_requires_literal_true_confirmation(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        close_attempts = 0

        def close_tunnel() -> bool:
            nonlocal close_attempts
            close_attempts += 1
            return 1 if close_attempts == 1 else True  # type: ignore[return-value]

        authority.register_active_connection(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            close=close_tunnel,
        )

        with self.assertRaises(NetworkLeaseConnectionCloseError):
            authority.revoke(policy)
        self.assertEqual(authority.close_expired_connections(4_000_000_000), 1)
        self.assertEqual(close_attempts, 2)

    def test_expiry_close_failure_blocks_scope_until_tunnel_cleanup_retries(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()
        grant = authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=2_000_000_000,
        )
        close_attempts = 0

        def close_tunnel() -> bool:
            nonlocal close_attempts
            close_attempts += 1
            return close_attempts > 1

        authority.register_active_connection(
            grant,
            policy,
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            hostname="pypi.org",
            port=443,
            now_monotonic_ns=3_000_000_000,
            close=close_tunnel,
        )

        with self.assertRaises(NetworkLeaseConnectionCloseError):
            authority.close_expired_connections(62_000_000_000)
        blocked_approver = ScriptedApprover([True])
        with self.assertRaises(NetworkLeaseValidationError):
            authority.request_lease(
                policy,
                approver=blocked_approver,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("pypi.org",),
                ttl_seconds=60,
                now_monotonic_ns=62_000_000_001,
            )
        self.assertEqual(blocked_approver.seen, [])
        with self.assertRaises(NetworkLeaseValidationError):
            authority.verify_request(
                grant,
                policy,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                hostname="pypi.org",
                port=443,
                now_monotonic_ns=62_000_000_001,
            )

        self.assertEqual(authority.close_expired_connections(62_000_000_001), 1)
        self.assertEqual(close_attempts, 2)
        authority.request_lease(
            policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("pypi.org",),
            ttl_seconds=60,
            now_monotonic_ns=63_000_000_000,
        )

    def test_revoke_during_pending_approval_prevents_lease_issue(self) -> None:
        policy = self.make_policy()
        authority = NetworkLeaseAuthority()

        class RevokeWhileWaiting:
            def ask(inner_self: object, request: object) -> bool:
                authority.revoke(policy)
                return True

        with self.assertRaises(NetworkLeaseValidationError):
            authority.request_lease(
                policy,
                approver=RevokeWhileWaiting(),  # type: ignore[arg-type]
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("pypi.org",),
                ttl_seconds=60,
                now_monotonic_ns=2_000_000_000,
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
