"""Lease-gated HTTPS CONNECT target resolution tests.

These tests cover only host-side request authorization and DNS pinning. They do
not establish a socket, create a proxy listener, or grant worker networking.
"""

from __future__ import annotations

import importlib
import importlib.util
import socket
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.approvals import ScriptedApprover
from icode.connect_request import ConnectRequestError
from icode.network_destination import NetworkDestinationError
from icode.network_lease import (
    NetworkLeaseAuthority,
    NetworkLeaseValidationError,
    NetworkPurpose,
)
from icode.sandbox_policy import NetworkMode, SandboxPolicy


_VALID_ANSWERS = [
    (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        ("93.184.216.34", 443),
    ),
]
_CONNECT_REQUEST = (
    b"CONNECT packages.example:443 HTTP/1.1\r\n"
    b"Host: packages.example\r\n\r\n"
)


class LeasedConnectTargetTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.workspace = Path(self._temporary_directory.name).resolve()
        self.policy = SandboxPolicy(
            schema_version=1,
            run_id="run-connect-001",
            ticket_id="ICODE-42",
            step="implementation",
            workspace_root=self.workspace,
            read_roots=(self.workspace,),
            write_roots=(self.workspace,),
            deny_read_roots=(self.workspace / ".git",),
            deny_write_roots=(self.workspace / ".git",),
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            process_limit=8,
            wall_timeout_seconds=600,
            output_limit_bytes=1024 * 1024,
            protected_paths=(self.workspace / ".git",),
        )
        self.authority = NetworkLeaseAuthority()
        self.issued = self.authority.request_lease(
            self.policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("packages.example",),
            ttl_seconds=60,
        )

    def _resolve_targets(
        self,
        *,
        request_head: bytes = _CONNECT_REQUEST,
        issued: Any | None = None,
        policy: SandboxPolicy | None = None,
        purpose: NetworkPurpose = NetworkPurpose.PACKAGE_INSTALL,
        **kwargs: Any,
    ) -> Any:
        spec = importlib.util.find_spec("icode.leased_connect")
        self.assertIsNotNone(
            spec,
            "lease-gated CONNECT target resolution has not been implemented",
        )
        module = importlib.import_module("icode.leased_connect")
        resolver = getattr(module, "resolve_leased_https_connect_targets", None)
        self.assertTrue(
            callable(resolver),
            "lease-gated CONNECT target resolver is missing",
        )
        # Exercise lease-to-target behavior on every runner; the runtime patch
        # floor itself remains independently tested by test_network_destination.
        with patch(
            "icode.network_destination._supports_safe_ipaddress_classification",
            return_value=True,
        ):
            return resolver(
                request_head,
                self.authority,
                self.issued if issued is None else issued,
                self.policy if policy is None else policy,
                purpose,
                **kwargs,
            )

    def test_valid_lease_resolves_only_to_validated_numeric_targets(self) -> None:
        resolver_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            resolver_calls.append((args, kwargs))
            return _VALID_ANSWERS

        result = self._resolve_targets(resolver=resolver)

        self.assertEqual(result.hostname, "packages.example")
        self.assertEqual(result.port, 443)
        self.assertEqual(len(result.targets), 1)
        self.assertEqual(result.targets[0].sockaddr, ("93.184.216.34", 443))
        self.assertEqual(
            resolver_calls,
            [
                (
                    ("packages.example.", 443),
                    {"type": socket.SOCK_STREAM, "proto": socket.IPPROTO_TCP},
                ),
            ],
        )

    def test_revoked_lease_is_rejected_before_dns_resolution(self) -> None:
        self.authority.revoke(self.policy)
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return _VALID_ANSWERS

        with self.assertRaises(NetworkLeaseValidationError):
            self._resolve_targets(resolver=resolver)

        self.assertEqual(resolver_calls, 0)

    def test_invalid_signature_is_rejected_before_dns_resolution(self) -> None:
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return _VALID_ANSWERS

        bad_signature = (
            ("0" if self.issued.signature[0] != "0" else "1")
            + self.issued.signature[1:]
        )
        tampered_lease = replace(self.issued, signature=bad_signature)

        with self.assertRaises(NetworkLeaseValidationError):
            self._resolve_targets(issued=tampered_lease, resolver=resolver)

        self.assertEqual(resolver_calls, 0)

    def test_expired_lease_is_rejected_before_dns_resolution(self) -> None:
        expired_issued = self.authority.request_lease(
            self.policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("packages.example",),
            ttl_seconds=1,
        )
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return _VALID_ANSWERS

        module = importlib.import_module("icode.leased_connect")
        with patch.object(
            module.time,
            "monotonic_ns",
            return_value=expired_issued.lease.expires_at_monotonic_ns,
        ):
            with self.assertRaises(NetworkLeaseValidationError):
                self._resolve_targets(issued=expired_issued, resolver=resolver)

        self.assertEqual(resolver_calls, 0)

    def test_invalid_connect_request_is_rejected_before_dns_resolution(self) -> None:
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return _VALID_ANSWERS

        with self.assertRaises(ConnectRequestError):
            self._resolve_targets(
                request_head=b"CONNECT packages.example:444 HTTP/1.1\r\n\r\n",
                resolver=resolver,
            )

        self.assertEqual(resolver_calls, 0)

    def test_unlisted_hostname_is_rejected_before_dns_resolution(self) -> None:
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return _VALID_ANSWERS

        request_head = (
            b"CONNECT other.example:443 HTTP/1.1\r\n"
            b"Host: other.example\r\n\r\n"
        )
        with self.assertRaises(NetworkLeaseValidationError):
            self._resolve_targets(request_head=request_head, resolver=resolver)

        self.assertEqual(resolver_calls, 0)

    def test_wrong_purpose_is_rejected_before_dns_resolution(self) -> None:
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return _VALID_ANSWERS

        with self.assertRaises(NetworkLeaseValidationError):
            self._resolve_targets(
                purpose=NetworkPurpose.WEB_READ,
                resolver=resolver,
            )

        self.assertEqual(resolver_calls, 0)

    def test_policy_mismatch_is_rejected_before_dns_resolution(self) -> None:
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return _VALID_ANSWERS

        mismatched_policy = SandboxPolicy(
            schema_version=1,
            run_id="different-run",
            ticket_id=self.policy.ticket_id,
            step=self.policy.step,
            workspace_root=self.workspace,
            read_roots=(self.workspace,),
            write_roots=(self.workspace,),
            deny_read_roots=(self.workspace / ".git",),
            deny_write_roots=(self.workspace / ".git",),
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            process_limit=8,
            wall_timeout_seconds=600,
            output_limit_bytes=1024 * 1024,
            protected_paths=(self.workspace / ".git",),
        )
        with self.assertRaises(NetworkLeaseValidationError):
            self._resolve_targets(policy=mismatched_policy, resolver=resolver)

        self.assertEqual(resolver_calls, 0)

    def test_revocation_during_dns_discards_the_resolved_targets(self) -> None:
        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            self.authority.revoke(self.policy)
            return _VALID_ANSWERS

        with self.assertRaises(NetworkLeaseValidationError):
            self._resolve_targets(resolver=resolver)

    def test_expiry_during_dns_discards_the_resolved_targets(self) -> None:
        issued = self.authority.request_lease(
            self.policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("packages.example",),
            ttl_seconds=1,
        )

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            return _VALID_ANSWERS

        spec = importlib.util.find_spec("icode.leased_connect")
        self.assertIsNotNone(
            spec,
            "lease-gated CONNECT target resolution has not been implemented",
        )
        module = importlib.import_module("icode.leased_connect")
        resolve_targets = getattr(module, "resolve_leased_https_connect_targets", None)
        self.assertTrue(callable(resolve_targets))
        issued_at = issued.lease.issued_at_monotonic_ns
        with patch(
            "icode.network_destination._supports_safe_ipaddress_classification",
            return_value=True,
        ):
            with patch.object(
                module.time,
                "monotonic_ns",
                side_effect=(issued_at + 1, issued_at + 1_000_000_001),
            ):
                with self.assertRaises(NetworkLeaseValidationError):
                    resolve_targets(
                        _CONNECT_REQUEST,
                        self.authority,
                        issued,
                        self.policy,
                        NetworkPurpose.PACKAGE_INSTALL,
                        resolver=resolver,
                    )

    def test_private_dns_answer_is_rejected_without_returning_targets(self) -> None:
        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", 443),
                ),
            ]

        with self.assertRaises(NetworkDestinationError):
            self._resolve_targets(resolver=resolver)


if __name__ == "__main__":
    unittest.main()
