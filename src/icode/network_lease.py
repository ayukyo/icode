"""Temporary network authorization contracts; this module does not grant networking.

The host authority can obtain explicit approval and sign short-lived lease data.
Platform backends must still deny network access until they enforce proxy-only
routing in the operating system. A lease or its point-in-time verification is not
a connection permit or a security boundary by itself.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass
from enum import Enum

from .approvals import ApprovalRequest, Approver
from .sandbox_policy import (
    NetworkMode,
    PolicyValidationError,
    SandboxPolicy,
    is_exact_dns_hostname,
)


NETWORK_LEASE_SCHEMA_VERSION = 1
NANOSECONDS_PER_SECOND = 1_000_000_000
MAX_NETWORK_LEASE_TTL_SECONDS = 15 * 60
MAX_NETWORK_LEASE_TTL_NS = MAX_NETWORK_LEASE_TTL_SECONDS * NANOSECONDS_PER_SECOND
MAX_NETWORK_LEASE_DOMAINS = 32
HTTPS_PORT = 443

_LEASE_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
_POLICY_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class NetworkLeaseValidationError(ValueError):
    """Raised when a lease does not match its policy, target, or lifetime."""


class NetworkLeaseApprovalDenied(NetworkLeaseValidationError):
    """Raised when network approval is rejected, times out, or cannot be obtained."""


class NetworkPurpose(str, Enum):
    PACKAGE_INSTALL = "package_install"
    WEB_READ = "web_read"


@dataclass(frozen=True)
class NetworkLease:
    """An immutable, narrowly scoped authorization contract for a future broker."""

    schema_version: int
    lease_id: str
    approval_id: str
    run_id: str
    ticket_id: str
    step: str
    policy_hash: str
    purpose: NetworkPurpose
    allowed_domains: tuple[str, ...]
    port: int
    issued_at_monotonic_ns: int
    expires_at_monotonic_ns: int
    generation: int

    def __post_init__(self) -> None:
        self._validate_declared_types()
        object.__setattr__(
            self,
            "allowed_domains",
            tuple(sorted({domain.lower() for domain in self.allowed_domains})),
        )
        self.validate()

    def _validate_declared_types(self) -> None:
        if type(self.schema_version) is not int:
            raise NetworkLeaseValidationError("schema_version must be integer 1")
        if type(self.lease_id) is not str:
            raise NetworkLeaseValidationError("lease_id must be a string")
        if type(self.approval_id) is not str:
            raise NetworkLeaseValidationError("approval_id must be a string")
        for name in ("run_id", "ticket_id", "step", "policy_hash"):
            if type(getattr(self, name)) is not str:
                raise NetworkLeaseValidationError(f"{name} must be a string")
        if not isinstance(self.purpose, NetworkPurpose):
            raise NetworkLeaseValidationError("purpose must be a NetworkPurpose")
        if type(self.allowed_domains) is not tuple or any(
            type(domain) is not str for domain in self.allowed_domains
        ):
            raise NetworkLeaseValidationError("allowed_domains must be a tuple of strings")
        for name in (
            "port",
            "issued_at_monotonic_ns",
            "expires_at_monotonic_ns",
            "generation",
        ):
            if type(getattr(self, name)) is not int:
                raise NetworkLeaseValidationError(f"{name} must be an integer")

    def validate(self) -> None:
        self._validate_declared_types()
        if self.schema_version != NETWORK_LEASE_SCHEMA_VERSION:
            raise NetworkLeaseValidationError(
                f"unsupported network lease schema_version: {self.schema_version!r}"
            )
        if _LEASE_ID_PATTERN.fullmatch(self.lease_id) is None:
            raise NetworkLeaseValidationError("lease_id must be 32 lowercase hex characters")
        if not self.approval_id or len(self.approval_id) > 256:
            raise NetworkLeaseValidationError("approval_id must be non-blank and bounded")
        for name in ("approval_id", "run_id", "ticket_id", "step"):
            value = getattr(self, name)
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise NetworkLeaseValidationError(
                    f"{name} must contain UTF-8 encodable Unicode scalars"
                ) from error
            if not value.strip() or any(
                ord(character) < 32 or ord(character) == 127 for character in value
            ):
                raise NetworkLeaseValidationError(
                    f"{name} must be non-blank and contain no ASCII control characters"
                )
        if _POLICY_HASH_PATTERN.fullmatch(self.policy_hash) is None:
            raise NetworkLeaseValidationError("policy_hash must be a lowercase SHA-256 hex digest")
        if not self.allowed_domains or any(
            not is_exact_dns_hostname(domain) for domain in self.allowed_domains
        ):
            raise NetworkLeaseValidationError(
                "allowed_domains must contain exact ASCII DNS hostnames"
            )
        if len(self.allowed_domains) > MAX_NETWORK_LEASE_DOMAINS:
            raise NetworkLeaseValidationError(
                f"a network lease may contain at most {MAX_NETWORK_LEASE_DOMAINS} domains"
            )
        if self.port != HTTPS_PORT:
            raise NetworkLeaseValidationError(
                "temporary network leases currently require HTTPS port 443"
            )
        if self.issued_at_monotonic_ns <= 0:
            raise NetworkLeaseValidationError("issued_at_monotonic_ns must be positive")
        if self.expires_at_monotonic_ns <= self.issued_at_monotonic_ns:
            raise NetworkLeaseValidationError("lease expiry must follow its issue time")
        if (
            self.expires_at_monotonic_ns - self.issued_at_monotonic_ns
            > MAX_NETWORK_LEASE_TTL_NS
        ):
            raise NetworkLeaseValidationError("network lease lifetime exceeds 15 minutes")
        if self.generation <= 0:
            raise NetworkLeaseValidationError("generation must be a positive integer")

    def validate_request(
        self,
        policy: SandboxPolicy,
        *,
        purpose: NetworkPurpose,
        hostname: str,
        port: int,
        now_monotonic_ns: int,
        current_generation: int,
    ) -> None:
        """Validate one proposed proxy request without opening a connection."""

        self.validate()
        if not isinstance(policy, SandboxPolicy):
            raise NetworkLeaseValidationError("a valid SandboxPolicy is required")
        try:
            policy.validate()
        except PolicyValidationError as error:
            raise NetworkLeaseValidationError("sandbox policy is invalid") from error
        if policy.network_mode is not NetworkMode.PROXY_ALLOWLIST:
            raise NetworkLeaseValidationError("sandbox policy does not allow proxy routing")
        if (
            self.run_id != policy.run_id
            or self.ticket_id != policy.ticket_id
            or self.step != policy.step
            or self.policy_hash != policy.policy_hash
        ):
            raise NetworkLeaseValidationError("network lease is bound to a different policy")
        if not set(self.allowed_domains).issubset(policy.allowed_domains):
            raise NetworkLeaseValidationError("lease domains exceed the sandbox policy")
        if type(purpose) is not NetworkPurpose or purpose is not self.purpose:
            raise NetworkLeaseValidationError("request purpose differs from the lease")
        if (
            type(hostname) is not str
            or not is_exact_dns_hostname(hostname.lower())
        ):
            raise NetworkLeaseValidationError("request hostname must be an exact DNS hostname")
        if hostname.lower() not in self.allowed_domains:
            raise NetworkLeaseValidationError("request hostname is not authorized by the lease")
        if type(port) is not int or port != self.port:
            raise NetworkLeaseValidationError("request port is not authorized by the lease")
        if type(now_monotonic_ns) is not int or now_monotonic_ns < 0:
            raise NetworkLeaseValidationError("now_monotonic_ns must be a non-negative integer")
        if not self.issued_at_monotonic_ns <= now_monotonic_ns < self.expires_at_monotonic_ns:
            raise NetworkLeaseValidationError("network lease is not currently active")
        if type(current_generation) is not int or current_generation != self.generation:
            raise NetworkLeaseValidationError("network lease generation was revoked or replaced")

    def canonical_payload(self) -> bytes:
        """Return the deterministic bytes authenticated by the host-only HMAC key."""

        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "lease_id": self.lease_id,
            "approval_id": self.approval_id,
            "run_id": self.run_id,
            "ticket_id": self.ticket_id,
            "step": self.step,
            "policy_hash": self.policy_hash,
            "purpose": self.purpose.value,
            "allowed_domains": list(self.allowed_domains),
            "port": self.port,
            "issued_at_monotonic_ns": self.issued_at_monotonic_ns,
            "expires_at_monotonic_ns": self.expires_at_monotonic_ns,
            "generation": self.generation,
        }
        return json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True,
        ).encode("ascii")


@dataclass(frozen=True)
class IssuedNetworkLease:
    """A lease payload authenticated by one live NetworkLeaseAuthority instance."""

    lease: NetworkLease
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.lease, NetworkLease):
            raise NetworkLeaseValidationError("issued lease payload is invalid")
        if type(self.signature) is not str or _SIGNATURE_PATTERN.fullmatch(self.signature) is None:
            raise NetworkLeaseValidationError("lease signature must be a SHA-256 HMAC hex digest")


class NetworkLeaseAuthority:
    """Host-process signer, explicit-approval gate, and in-memory revocation epoch.

    The random HMAC key is never serialized. This authority does not open sockets or
    enforce OS routing; a future trusted proxy must consult it and independently
    close active connections on revoke/expiry.
    """

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)
        self._lock = threading.RLock()
        self._generations: dict[tuple[str, str, str, str], int] = {}

    @staticmethod
    def _policy_key(policy: SandboxPolicy) -> tuple[str, str, str, str]:
        if not isinstance(policy, SandboxPolicy):
            raise NetworkLeaseValidationError("a valid SandboxPolicy is required")
        try:
            policy.validate()
        except PolicyValidationError as error:
            raise NetworkLeaseValidationError("sandbox policy is invalid") from error
        if policy.network_mode is not NetworkMode.PROXY_ALLOWLIST:
            raise NetworkLeaseValidationError(
                "network leases require a proxy-allowlist policy"
            )
        return policy.run_id, policy.ticket_id, policy.step, policy.policy_hash

    def request_lease(
        self,
        policy: SandboxPolicy,
        *,
        approver: Approver,
        purpose: NetworkPurpose,
        allowed_domains: tuple[str, ...],
        ttl_seconds: int,
        now_monotonic_ns: int | None = None,
    ) -> IssuedNetworkLease:
        """Request explicit human approval, then issue a signed scoped lease.

        The host caller must keep the authority and HMAC key out of untrusted
        subprocesses. A missing/failed approver or revocation during the prompt
        produces no lease.
        """

        policy_key = self._policy_key(policy)
        if type(purpose) is not NetworkPurpose:
            raise NetworkLeaseValidationError("purpose must be a NetworkPurpose")
        if type(allowed_domains) is not tuple or any(
            type(domain) is not str for domain in allowed_domains
        ):
            raise NetworkLeaseValidationError("allowed_domains must be a tuple of strings")
        normalized_domains = tuple(sorted({domain.lower() for domain in allowed_domains}))
        if not normalized_domains or not set(normalized_domains).issubset(policy.allowed_domains):
            raise NetworkLeaseValidationError("requested domains exceed the sandbox policy")
        if len(normalized_domains) > MAX_NETWORK_LEASE_DOMAINS:
            raise NetworkLeaseValidationError(
                f"a network lease may contain at most {MAX_NETWORK_LEASE_DOMAINS} domains"
            )
        if (
            type(ttl_seconds) is not int
            or not 1 <= ttl_seconds <= MAX_NETWORK_LEASE_TTL_SECONDS
        ):
            raise NetworkLeaseValidationError(
                "ttl_seconds must be from 1 through "
                f"{MAX_NETWORK_LEASE_TTL_SECONDS}"
            )
        if not callable(getattr(approver, "ask", None)):
            raise NetworkLeaseApprovalDenied("network approval service is unavailable")

        with self._lock:
            generation = self._generations.get(policy_key, 1)
        approval_id = f"ap-net-{secrets.token_hex(12)}"
        request = ApprovalRequest(
            tool="temporary_network_access",
            arguments={
                "lease_request_id": approval_id,
                "run_id": policy.run_id,
                "ticket_id": policy.ticket_id,
                "step": policy.step,
                "purpose": purpose.value,
                "domains": list(normalized_domains),
                "port": HTTPS_PORT,
                "ttl_seconds": ttl_seconds,
            },
            reason=(
                "当前工单需要通过受控代理访问指定域名；"
                f"仅开放 HTTPS 443，期限 {ttl_seconds} 秒，到期或撤销后失效。"
            ),
            opclass="network_authorization",
            workspace=str(policy.workspace_root),
        )
        try:
            approved = approver.ask(request)
        except Exception as error:  # noqa: BLE001 - approval failure is deny.
            raise NetworkLeaseApprovalDenied("network approval failed closed") from error
        if approved is not True:
            raise NetworkLeaseApprovalDenied("network lease request was denied or timed out")

        with self._lock:
            if self._generations.get(policy_key, 1) != generation:
                raise NetworkLeaseValidationError(
                    "network scope was revoked while approval was pending"
                )
            issued_at = (
                time.monotonic_ns()
                if now_monotonic_ns is None
                else now_monotonic_ns
            )
            lease = NetworkLease(
                schema_version=NETWORK_LEASE_SCHEMA_VERSION,
                lease_id=secrets.token_hex(16),
                approval_id=approval_id,
                run_id=policy.run_id,
                ticket_id=policy.ticket_id,
                step=policy.step,
                policy_hash=policy.policy_hash,
                purpose=purpose,
                allowed_domains=normalized_domains,
                port=HTTPS_PORT,
                issued_at_monotonic_ns=issued_at,
                expires_at_monotonic_ns=(
                    issued_at + ttl_seconds * NANOSECONDS_PER_SECOND
                ),
                generation=generation,
            )
            signature = hmac.new(
                self._key, lease.canonical_payload(), hashlib.sha256,
            ).hexdigest()
            return IssuedNetworkLease(lease=lease, signature=signature)

    def verify_request(
        self,
        issued: IssuedNetworkLease,
        policy: SandboxPolicy,
        *,
        purpose: NetworkPurpose,
        hostname: str,
        port: int,
        now_monotonic_ns: int,
    ) -> None:
        """Authenticate and scope-check a request; this method does not connect."""

        if not isinstance(issued, IssuedNetworkLease):
            raise NetworkLeaseValidationError("issued network lease is required")
        policy_key = self._policy_key(policy)
        expected = hmac.new(
            self._key, issued.lease.canonical_payload(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, issued.signature):
            raise NetworkLeaseValidationError("network lease signature is invalid")
        with self._lock:
            generation = self._generations.get(policy_key, 1)
            issued.lease.validate_request(
                policy,
                purpose=purpose,
                hostname=hostname,
                port=port,
                now_monotonic_ns=now_monotonic_ns,
                current_generation=generation,
            )

    def revoke(self, policy: SandboxPolicy) -> int:
        """Invalidate every lease issued for this run/ticket/step/policy snapshot."""

        policy_key = self._policy_key(policy)
        with self._lock:
            generation = self._generations.get(policy_key, 1) + 1
            self._generations[policy_key] = generation
            return generation
