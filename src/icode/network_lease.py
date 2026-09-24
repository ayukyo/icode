"""Temporary network-lease scope contract; this module does not grant networking.

Platform backends must continue to deny network access until they validate a lease
and enforce proxy-only routing in the operating system. The lease is immutable
scope data, not proof of user approval or a security boundary by itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .sandbox_policy import (
    NetworkMode,
    PolicyValidationError,
    SandboxPolicy,
    is_exact_dns_hostname,
)


NETWORK_LEASE_SCHEMA_VERSION = 1
MAX_NETWORK_LEASE_TTL_NS = 15 * 60 * 1_000_000_000
HTTPS_PORT = 443

_LEASE_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
_POLICY_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class NetworkLeaseValidationError(ValueError):
    """Raised when a lease does not match its policy, target, or lifetime."""


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
