"""Temporary network authorization contracts; this module does not grant networking.

The host authority can obtain explicit approval and sign short-lived lease data.
Platform backends must still deny network access until they enforce proxy-only
routing in the operating system. The authority can atomically register trusted
proxy close callbacks, but it does not create sockets or enforce routing; a lease
or point-in-time verification is not a network permission or security boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .approvals import ApprovalRequest, Approver
from .sandbox_policy import (
    NetworkMode,
    PolicyValidationError,
    SandboxPolicy,
    is_exact_dns_hostname,
)


NETWORK_LEASE_SCHEMA_VERSION = 2
NANOSECONDS_PER_SECOND = 1_000_000_000
MAX_NETWORK_LEASE_TTL_SECONDS = 15 * 60
MAX_NETWORK_LEASE_TTL_NS = MAX_NETWORK_LEASE_TTL_SECONDS * NANOSECONDS_PER_SECOND
MAX_NETWORK_LEASE_DOMAINS = 32
HTTPS_PORT = 443
_NETWORK_CONNECTION_CLOSE_WAIT_SECONDS = 5.0
DEFAULT_NETWORK_LEASE_SWEEP_INTERVAL_SECONDS = 0.1
MIN_NETWORK_LEASE_SWEEP_INTERVAL_SECONDS = 0.01
MAX_NETWORK_LEASE_SWEEP_INTERVAL_SECONDS = 1.0
NETWORK_LEASE_MONITOR_STOP_TIMEOUT_SECONDS = 5.0

_LEASE_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
_POLICY_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class NetworkLeaseValidationError(ValueError):
    """Raised when a lease does not match its policy, target, or lifetime."""


class NetworkLeaseApprovalDenied(NetworkLeaseValidationError):
    """Raised when network approval is rejected, times out, or cannot be obtained."""


class NetworkLeaseConnectionCloseError(NetworkLeaseValidationError):
    """Raised when active connection closure cannot be confirmed."""

    def __init__(self, failure_count: int) -> None:
        self.failure_count = failure_count
        super().__init__(
            "one or more active network connections could not be confirmed closed"
        )


class NetworkPurpose(str, Enum):
    PACKAGE_INSTALL = "package_install"
    WEB_READ = "web_read"


@dataclass(frozen=True)
class NetworkLease:
    """A signed host-only authorization overlay for a future trusted broker.

    ``policy_hash`` binds the unchanged, deny-only SandboxPolicy. The lease is
    not a SandboxPolicy permission and must never be passed to an untrusted
    worker as evidence that operating-system network access is available.
    """

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
            tuple(sorted({
                domain.lower() if is_exact_dns_hostname(domain) else domain
                for domain in self.allowed_domains
            })),
        )
        self.validate()

    def _validate_declared_types(self) -> None:
        if type(self.schema_version) is not int:
            raise NetworkLeaseValidationError("schema_version must be an integer")
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

    def validate_scope(
        self,
        policy: SandboxPolicy,
        *,
        purpose: NetworkPurpose,
        now_monotonic_ns: int,
        current_generation: int,
    ) -> None:
        """Validate the live lease and deny-only policy without a target."""

        self.validate()
        if not isinstance(policy, SandboxPolicy):
            raise NetworkLeaseValidationError("a valid SandboxPolicy is required")
        try:
            policy.validate()
        except PolicyValidationError as error:
            raise NetworkLeaseValidationError("sandbox policy is invalid") from error
        if (
            policy.network_mode is not NetworkMode.DENY
            or policy.allowed_domains
        ):
            raise NetworkLeaseValidationError(
                "network lease must overlay a deny-only sandbox policy"
            )
        if (
            self.run_id != policy.run_id
            or self.ticket_id != policy.ticket_id
            or self.step != policy.step
            or self.policy_hash != policy.policy_hash
        ):
            raise NetworkLeaseValidationError("network lease is bound to a different policy")
        if type(purpose) is not NetworkPurpose or purpose is not self.purpose:
            raise NetworkLeaseValidationError("request purpose differs from the lease")
        if type(now_monotonic_ns) is not int or now_monotonic_ns < 0:
            raise NetworkLeaseValidationError("now_monotonic_ns must be a non-negative integer")
        if not self.issued_at_monotonic_ns <= now_monotonic_ns < self.expires_at_monotonic_ns:
            raise NetworkLeaseValidationError("network lease is not currently active")
        if type(current_generation) is not int or current_generation != self.generation:
            raise NetworkLeaseValidationError("network lease generation was revoked or replaced")

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
        """Validate a host-proxy request over an unchanged deny-only base policy.

        The lease is a host-side authorization overlay. It does not alter the
        candidate ``SandboxPolicy`` or grant a worker network permission.
        """

        self.validate_scope(
            policy,
            purpose=purpose,
            now_monotonic_ns=now_monotonic_ns,
            current_generation=current_generation,
        )
        if type(hostname) is not str or not is_exact_dns_hostname(hostname):
            raise NetworkLeaseValidationError("request hostname must be an exact DNS hostname")
        if hostname.lower() not in self.allowed_domains:
            raise NetworkLeaseValidationError("request hostname is not authorized by the lease")
        if type(port) is not int or port != self.port:
            raise NetworkLeaseValidationError("request port is not authorized by the lease")

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


@dataclass(frozen=True, slots=True, repr=False)
class _NetworkConnectionHandle:
    """Opaque in-process identity; never serialize or pass it to a worker."""

    connection_id: str


@dataclass
class _ActiveNetworkConnection:
    handle: _NetworkConnectionHandle
    policy_key: tuple[str, str, str, str]
    lease: NetworkLease
    close_callback: Callable[[], bool]
    release_callback: Callable[[], bool] | None = None
    pending: bool = False
    closing: bool = False
    close_complete: threading.Event = field(
        default_factory=threading.Event, repr=False, compare=False,
    )


class NetworkLeaseAuthority:
    """Host-process signer, explicit-approval gate, and in-memory revocation epoch.

    The random HMAC key is never serialized. This authority does not open sockets or
    enforce OS routing; a future trusted proxy must register its own socket-close
    callbacks and periodically call ``close_expired_connections``.
    """

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)
        self._lock = threading.RLock()
        self._generations: dict[tuple[str, str, str, str], int] = {}
        self._revoking_policy_keys: set[tuple[str, str, str, str]] = set()
        self._active_connections: dict[str, _ActiveNetworkConnection] = {}

    @staticmethod
    def _policy_key(policy: SandboxPolicy) -> tuple[str, str, str, str]:
        if not isinstance(policy, SandboxPolicy):
            raise NetworkLeaseValidationError("a valid SandboxPolicy is required")
        try:
            policy.validate()
        except PolicyValidationError as error:
            raise NetworkLeaseValidationError("sandbox policy is invalid") from error
        if (
            policy.network_mode is not NetworkMode.DENY
            or policy.allowed_domains
        ):
            raise NetworkLeaseValidationError(
                "network leases require a deny-only sandbox policy"
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
        produces no lease. Lease domains form a host-only overlay over the
        deny-only base policy; they never broaden the policy passed to a worker.
        """

        policy_key = self._policy_key(policy)
        if type(purpose) is not NetworkPurpose:
            raise NetworkLeaseValidationError("purpose must be a NetworkPurpose")
        if type(allowed_domains) is not tuple or any(
            type(domain) is not str for domain in allowed_domains
        ):
            raise NetworkLeaseValidationError("allowed_domains must be a tuple of strings")
        if not allowed_domains or any(
            not is_exact_dns_hostname(domain) for domain in allowed_domains
        ):
            raise NetworkLeaseValidationError(
                "requested domains must be exact ASCII DNS hostnames"
            )
        normalized_domains = tuple(sorted({domain.lower() for domain in allowed_domains}))
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
            if policy_key in self._revoking_policy_keys:
                raise NetworkLeaseValidationError(
                    "network scope revocation cleanup is incomplete"
                )
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
            if (
                policy_key in self._revoking_policy_keys
                or self._generations.get(policy_key, 1) != generation
            ):
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
        with self._lock:
            self._verify_request_locked(
                issued,
                policy,
                policy_key=policy_key,
                purpose=purpose,
                hostname=hostname,
                port=port,
                now_monotonic_ns=now_monotonic_ns,
            )

    def verify_scope(
        self,
        issued: IssuedNetworkLease,
        policy: SandboxPolicy,
        *,
        purpose: NetworkPurpose,
        now_monotonic_ns: int,
    ) -> None:
        """Authenticate lease liveness before a proxy knows its request target."""

        if not isinstance(issued, IssuedNetworkLease):
            raise NetworkLeaseValidationError("issued network lease is required")
        policy_key = self._policy_key(policy)
        with self._lock:
            self._verify_scope_locked(
                policy,
                policy_key=policy_key,
                issued=issued,
                purpose=purpose,
                now_monotonic_ns=now_monotonic_ns,
            )

    @contextmanager
    def scope_guard(
        self,
        issued: IssuedNetworkLease,
        policy: SandboxPolicy,
        *,
        purpose: NetworkPurpose,
        clock: Callable[[], int],
    ) -> Iterator[None]:
        """Hold the lease-generation lock across one short publication action.

        Trusted host code may use this for a non-blocking, irreversible action
        such as releasing a sandbox only after its lease has been revalidated.
        The clock is sampled after acquiring the lock; keep the body short and
        do not perform DNS, socket connection, or waits.
        """

        if not isinstance(issued, IssuedNetworkLease):
            raise NetworkLeaseValidationError("issued network lease is required")
        if not callable(clock):
            raise NetworkLeaseValidationError("monotonic clock callback is invalid")
        policy_key = self._policy_key(policy)
        with self._lock:
            try:
                now_monotonic_ns = clock()
            except Exception:  # noqa: BLE001 - lease publication fails closed.
                raise NetworkLeaseValidationError(
                    "monotonic clock callback failed"
                ) from None
            if type(now_monotonic_ns) is not int or now_monotonic_ns < 0:
                raise NetworkLeaseValidationError(
                    "monotonic clock callback returned an invalid value"
                )
            self._verify_scope_locked(
                policy,
                policy_key=policy_key,
                issued=issued,
                purpose=purpose,
                now_monotonic_ns=now_monotonic_ns,
            )
            yield

    def _verify_scope_locked(
        self,
        policy: SandboxPolicy,
        *,
        policy_key: tuple[str, str, str, str],
        issued: IssuedNetworkLease,
        purpose: NetworkPurpose,
        now_monotonic_ns: int,
    ) -> None:
        if policy_key in self._revoking_policy_keys:
            raise NetworkLeaseValidationError(
                "network scope revocation cleanup is incomplete"
            )
        expected = hmac.new(
            self._key,
            issued.lease.canonical_payload(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, issued.signature):
            raise NetworkLeaseValidationError("network lease signature is invalid")
        issued.lease.validate_scope(
            policy,
            purpose=purpose,
            now_monotonic_ns=now_monotonic_ns,
            current_generation=self._generations.get(policy_key, 1),
        )

    def _verify_request_locked(
        self,
        issued: IssuedNetworkLease,
        policy: SandboxPolicy,
        *,
        policy_key: tuple[str, str, str, str],
        purpose: NetworkPurpose,
        hostname: str,
        port: int,
        now_monotonic_ns: int,
    ) -> None:
        if policy_key in self._revoking_policy_keys:
            raise NetworkLeaseValidationError(
                "network scope revocation cleanup is incomplete"
            )
        expected = hmac.new(
            self._key, issued.lease.canonical_payload(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, issued.signature):
            raise NetworkLeaseValidationError("network lease signature is invalid")
        generation = self._generations.get(policy_key, 1)
        issued.lease.validate_request(
            policy,
            purpose=purpose,
            hostname=hostname,
            port=port,
            now_monotonic_ns=now_monotonic_ns,
            current_generation=generation,
        )

    def register_active_connection(
        self,
        issued: IssuedNetworkLease,
        policy: SandboxPolicy,
        *,
        purpose: NetworkPurpose,
        hostname: str,
        port: int,
        now_monotonic_ns: int,
        close: Callable[[], bool],
        pending: bool = False,
        clock: Callable[[], int] | None = None,
        release: Callable[[], bool] | None = None,
    ) -> _NetworkConnectionHandle:
        """Atomically validate and register one trusted proxy-owned connection.

        A pending connect attempt must pass ``pending=True`` and register its
        cancellation/wakeup callback before starting a non-blocking connect.
        The callback must return strict boolean ``True`` only after its owner
        confirms closure. Already-connected sockets remain non-pending and
        cannot be promoted again. Release the returned handle only after normal
        closure. This does not create, route, or monitor a socket and is not a
        network permission by itself. Pending registrations require ``clock``;
        it is sampled under the authority lock after synchronous expiry cleanup,
        so a pending dial cannot rely on a timestamp made stale by a close
        callback.
        """

        if not callable(close):
            raise NetworkLeaseValidationError("connection close callback is required")
        if release is not None and not callable(release):
            raise NetworkLeaseValidationError("connection release callback is invalid")
        if type(pending) is not bool:
            raise NetworkLeaseValidationError("pending must be a boolean")
        if pending and clock is None:
            raise NetworkLeaseValidationError(
                "pending connection requires a monotonic clock callback"
            )
        if clock is not None and not callable(clock):
            raise NetworkLeaseValidationError("monotonic clock callback is invalid")
        self.close_expired_connections(now_monotonic_ns)
        policy_key = self._policy_key(policy)
        with self._lock:
            registration_time = now_monotonic_ns
            if clock is not None:
                try:
                    registration_time = clock()
                except Exception:  # noqa: BLE001 - registration fails closed.
                    raise NetworkLeaseValidationError(
                        "monotonic clock callback failed"
                    ) from None
                if type(registration_time) is not int or registration_time < 0:
                    raise NetworkLeaseValidationError(
                        "monotonic clock callback returned an invalid value"
                    )
            self._verify_request_locked(
                issued,
                policy,
                policy_key=policy_key,
                purpose=purpose,
                hostname=hostname,
                port=port,
                now_monotonic_ns=registration_time,
            )
            handle = _NetworkConnectionHandle(secrets.token_hex(32))
            self._active_connections[handle.connection_id] = _ActiveNetworkConnection(
                handle=handle,
                policy_key=policy_key,
                lease=issued.lease,
                close_callback=close,
                release_callback=release,
                pending=pending,
            )
            return handle

    def register_active_sockets(
        self,
        issued: IssuedNetworkLease,
        policy: SandboxPolicy,
        *,
        purpose: NetworkPurpose,
        hostname: str,
        port: int,
        now_monotonic_ns: int,
        sockets: tuple[socket.socket, ...],
        clock: Callable[[], int] | None = None,
    ) -> _NetworkConnectionHandle:
        """Register real proxy-owned sockets for authority-controlled closure.

        This method duplicates descriptors supplied by trusted host-side code
        and owns those duplicates for shutdown. It does not create a proxy,
        connect a socket, or permit worker network access. The caller retains
        ownership of its originals and must not mutate them concurrently with
        registration or share them with an untrusted worker.
        """

        if type(sockets) is not tuple or not sockets:
            raise NetworkLeaseValidationError(
                "active proxy sockets must be a non-empty tuple"
            )
        if any(type(sock) is not socket.socket for sock in sockets):
            raise NetworkLeaseValidationError(
                "active proxy sockets must be standard socket objects"
            )
        file_descriptors = tuple(sock.fileno() for sock in sockets)
        if any(file_descriptor < 0 for file_descriptor in file_descriptors):
            raise NetworkLeaseValidationError(
                "active proxy sockets must all be open"
            )
        if len(set(file_descriptors)) != len(file_descriptors):
            raise NetworkLeaseValidationError(
                "active proxy socket tuple contains duplicate file descriptors"
            )
        try:
            for sock in sockets:
                if (
                    sock.family not in (socket.AF_INET, socket.AF_INET6)
                    or sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
                    != socket.SOCK_STREAM
                ):
                    raise NetworkLeaseValidationError(
                        "active proxy sockets must be connected IPv4/IPv6 TCP streams"
                    )
                sock.getpeername()
        except OSError:
            raise NetworkLeaseValidationError(
                "active proxy sockets must be connected IPv4/IPv6 TCP streams"
            ) from None

        owned_sockets: list[socket.socket] = []

        def discard_owned_sockets() -> None:
            for sock in owned_sockets:
                try:
                    sock.close()
                except OSError:
                    pass

        try:
            for sock in sockets:
                owned_sockets.append(sock.dup())
        except BaseException:
            discard_owned_sockets()
            raise

        owned_socket_tuple = tuple(owned_sockets)

        def close_sockets() -> bool:
            for sock in owned_socket_tuple:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    # A peer may already have shut down one direction;
                    # still close each authority-owned descriptor.
                    pass
                try:
                    sock.close()
                except OSError:
                    # Continue closing the rest; final descriptor checks
                    # keep an incomplete close fail-closed in the authority.
                    pass
            return all(sock.fileno() < 0 for sock in owned_socket_tuple)

        def release_sockets() -> bool:
            """Dispose authority-owned duplicates after local normal shutdown."""

            for sock in owned_socket_tuple:
                try:
                    sock.close()
                except OSError:
                    pass
            return all(sock.fileno() < 0 for sock in owned_socket_tuple)

        try:
            return self.register_active_connection(
                issued,
                policy,
                purpose=purpose,
                hostname=hostname,
                port=port,
                now_monotonic_ns=now_monotonic_ns,
                close=close_sockets,
                clock=clock,
                release=release_sockets,
            )
        except Exception:
            discard_owned_sockets()
            raise

    def release_active_connection(self, handle: object) -> bool:
        """Forget a proxy connection after its owner has closed it normally."""

        if not isinstance(handle, _NetworkConnectionHandle):
            raise NetworkLeaseValidationError("active network connection handle is invalid")
        with self._lock:
            entry = self._active_connections.get(handle.connection_id)
            if entry is None or entry.handle is not handle:
                return False
            # A revocation marker blocks new authorization/registrations, but it
            # must not block an owner from releasing its own already-closed
            # handle. An expired sibling lease can mark the shared policy key
            # while another still-live lease is closing normally.
            if entry.closing:
                return False
            release_callback = entry.release_callback
            if release_callback is None:
                del self._active_connections[handle.connection_id]
                entry.close_complete.set()
                return True
            entry.closing = True
            entry.close_complete.clear()

        try:
            released = release_callback() is True
        except Exception:  # noqa: BLE001 - callback details can contain socket data.
            released = False

        with self._lock:
            current = self._active_connections.get(handle.connection_id)
            if current is not entry:
                entry.close_complete.set()
                return released
            if released:
                del self._active_connections[handle.connection_id]
            entry.closing = False
            entry.close_complete.set()
            return released

    def promote_active_connection(
        self,
        handle: object,
        *,
        now_monotonic_ns: int,
        close: Callable[[], bool],
    ) -> bool:
        """Atomically transfer a registered pending attempt to a connected socket.

        A trusted connector registers its cancellation/wakeup callback before
        starting a non-blocking connect. Once the socket is connected, it calls
        this method to replace that callback with one which owns the connected
        socket. Promotion and revoke/expiry state checks share the authority
        lock, so a failed promotion must close the candidate locally and must
        never publish it to the caller. This is lifecycle bookkeeping only; it
        does not perform or route a connection.
        """

        if not isinstance(handle, _NetworkConnectionHandle):
            raise NetworkLeaseValidationError(
                "active network connection handle is invalid"
            )
        if type(now_monotonic_ns) is not int or now_monotonic_ns < 0:
            raise NetworkLeaseValidationError(
                "now_monotonic_ns must be a non-negative integer"
            )
        if not callable(close):
            raise NetworkLeaseValidationError(
                "connected socket close callback is required"
            )
        with self._lock:
            entry = self._active_connections.get(handle.connection_id)
            if entry is None or entry.handle is not handle:
                return False
            if (
                entry.closing
                or not entry.pending
                or entry.policy_key in self._revoking_policy_keys
                or now_monotonic_ns < entry.lease.issued_at_monotonic_ns
                or entry.lease.expires_at_monotonic_ns <= now_monotonic_ns
                or entry.lease.generation
                != self._generations.get(entry.policy_key, 1)
            ):
                return False
            entry.close_callback = close
            entry.pending = False
            return True

    def _close_active_connections(
        self,
        entries: tuple[_ActiveNetworkConnection, ...],
    ) -> int:
        closed_count = 0
        failure_count = 0
        for entry in entries:
            with self._lock:
                if self._active_connections.get(entry.handle.connection_id) is not entry:
                    continue
                if entry.closing:
                    wait_for_close = entry.close_complete
                else:
                    entry.closing = True
                    entry.close_complete.clear()
                    wait_for_close = None

            if wait_for_close is not None:
                if not wait_for_close.wait(
                    timeout=_NETWORK_CONNECTION_CLOSE_WAIT_SECONDS,
                ):
                    failure_count += 1
                    continue
                with self._lock:
                    if self._active_connections.get(entry.handle.connection_id) is entry:
                        failure_count += 1
                continue

            try:
                close_confirmed = entry.close_callback() is True
            except Exception:  # noqa: BLE001 - callback details may contain secrets.
                close_confirmed = False

            if not close_confirmed:
                with self._lock:
                    if self._active_connections.get(entry.handle.connection_id) is entry:
                        entry.closing = False
                    entry.close_complete.set()
                failure_count += 1
            else:
                with self._lock:
                    if self._active_connections.get(entry.handle.connection_id) is entry:
                        del self._active_connections[entry.handle.connection_id]
                    entry.closing = False
                    entry.close_complete.set()
                closed_count += 1

        if failure_count:
            raise NetworkLeaseConnectionCloseError(failure_count) from None
        return closed_count

    def close_expired_connections(self, now_monotonic_ns: int) -> int:
        """Close expired, revoked-generation, and unfinished-revocation connections.

        The trusted proxy event loop must call this periodically; the authority
        deliberately creates no background threads on its own.
        """

        if type(now_monotonic_ns) is not int or now_monotonic_ns < 0:
            raise NetworkLeaseValidationError(
                "now_monotonic_ns must be a non-negative integer"
            )
        with self._lock:
            expired_policy_keys = {
                entry.policy_key
                for entry in self._active_connections.values()
                if entry.lease.expires_at_monotonic_ns <= now_monotonic_ns
            }
            # Block new approvals/registrations until every tunnel in this scope
            # is confirmed closed; otherwise a failed close could overlap a new lease.
            self._revoking_policy_keys.update(expired_policy_keys)
            entries = tuple(
                entry
                for entry in self._active_connections.values()
                if (
                    entry.lease.expires_at_monotonic_ns <= now_monotonic_ns
                    or entry.lease.generation
                    != self._generations.get(entry.policy_key, 1)
                )
            )
            revoking_keys = tuple(self._revoking_policy_keys)
        closed_count = self._close_active_connections(entries)
        with self._lock:
            for policy_key in revoking_keys:
                if not any(
                    entry.policy_key == policy_key
                    and (
                        entry.lease.expires_at_monotonic_ns <= now_monotonic_ns
                        or entry.lease.generation
                        != self._generations.get(entry.policy_key, 1)
                    )
                    for entry in self._active_connections.values()
                ):
                    self._revoking_policy_keys.discard(policy_key)
        return closed_count

    def revoke(self, policy: SandboxPolicy) -> int:
        """Invalidate every lease issued for this run/ticket/step/policy snapshot."""

        policy_key = self._policy_key(policy)
        with self._lock:
            generation = self._generations.get(policy_key, 1) + 1
            self._generations[policy_key] = generation
            self._revoking_policy_keys.add(policy_key)
            entries = tuple(
                entry
                for entry in self._active_connections.values()
                if entry.policy_key == policy_key
            )
        self._close_active_connections(entries)
        with self._lock:
            if not any(
                entry.policy_key == policy_key
                for entry in self._active_connections.values()
            ):
                self._revoking_policy_keys.discard(policy_key)
        return generation


class NetworkLeaseExpiryMonitor:
    """Periodically sweep expired host-owned connections on a trusted thread.

    The monitor is opt-in and single-use: the host lifecycle owner must start it
    while its proxy scope is active and stop it during shutdown. It does not
    open listeners, grant worker networking, or replace OS-level proxy routing.
    Failed closes remain fail-closed in the authority and are retried on the
    next sweep; the monitor records only a safe failure category, not exception
    text that could contain socket or destination details.
    """

    def __init__(
        self,
        authority: NetworkLeaseAuthority,
        *,
        sweep_interval_seconds: float = DEFAULT_NETWORK_LEASE_SWEEP_INTERVAL_SECONDS,
    ) -> None:
        if not isinstance(authority, NetworkLeaseAuthority):
            raise NetworkLeaseValidationError(
                "a host NetworkLeaseAuthority is required"
            )
        try:
            interval = float(sweep_interval_seconds)
        except (OverflowError, TypeError, ValueError):
            interval = math.nan
        if (
            type(sweep_interval_seconds) not in (int, float)
            or not math.isfinite(interval)
            or not MIN_NETWORK_LEASE_SWEEP_INTERVAL_SECONDS
            <= interval
            <= MAX_NETWORK_LEASE_SWEEP_INTERVAL_SECONDS
        ):
            raise NetworkLeaseValidationError(
                "sweep interval must be between 0.01 and 1.0 seconds"
            )

        self._authority = authority
        self._sweep_interval_seconds = interval
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._started = False
        self._stopped = False
        self._failure_count = 0
        self._last_error: str | None = None

    @property
    def running(self) -> bool:
        """Whether the owned sweep thread is currently alive."""

        with self._state_lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def failure_count(self) -> int:
        """Number of sweep attempts whose cleanup did not complete."""

        with self._state_lock:
            return self._failure_count

    @property
    def last_error(self) -> str | None:
        """A fixed, non-sensitive health category for the most recent sweep."""

        with self._state_lock:
            return self._last_error

    @contextmanager
    def healthy_guard(self) -> Iterator[None]:
        """Keep monitor health stable across a short host publication action."""

        with self._state_lock:
            thread = self._thread
            if (
                not self._started
                or self._stopped
                or thread is None
                or not thread.is_alive()
                or self._failure_count != 0
            ):
                raise NetworkLeaseValidationError(
                    "network lease expiry monitor is unhealthy"
                )
            yield

    def start(self) -> None:
        """Start exactly one daemon sweep thread for this monitor instance."""

        with self._state_lock:
            if self._started or self._stopped:
                raise RuntimeError("network lease expiry monitor is single-use")
            thread = threading.Thread(
                target=self._run,
                name="icode-network-lease-expiry",
                daemon=True,
            )
            self._thread = thread
            self._started = True
            try:
                thread.start()
            except BaseException:
                self._thread = None
                self._started = False
                raise

    def stop(self) -> bool:
        """Request shutdown and wait up to the fixed bounded join interval."""

        with self._state_lock:
            self._stopped = True
            thread = self._thread
            self._stop_event.set()
        if thread is None:
            return True
        if thread is threading.current_thread():
            return False
        thread.join(timeout=NETWORK_LEASE_MONITOR_STOP_TIMEOUT_SECONDS)
        return not thread.is_alive()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._authority.close_expired_connections(time.monotonic_ns())
            except Exception:  # noqa: BLE001 - keep retrying without exposing details.
                with self._state_lock:
                    self._failure_count += 1
                    self._last_error = "connection_cleanup_failed"
            else:
                with self._state_lock:
                    self._last_error = None
            if self._stop_event.wait(self._sweep_interval_seconds):
                return
