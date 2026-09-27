"""Lease-gated DNS target preparation for a future trusted CONNECT broker.

This host-side primitive parses an HTTPS CONNECT request, checks the signed
host-only lease before DNS, resolves to public numeric TCP targets, and checks
the lease again before returning those targets. It does not open a socket,
create a listener, grant worker network access, or change the deny-only sandbox
policy. The default system resolver is blocking and cannot be cancelled here;
revocation or expiry during DNS is detected afterward and prevents targets
from being returned. A future connector must use a returned numeric sockaddr
as-is and independently register and revalidate its pending connection before
promotion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .connect_request import parse_https_connect_request_head
from .network_destination import (
    ResolvedNetworkTarget,
    Resolver,
    resolve_public_tcp_targets,
)
from .network_lease import (
    IssuedNetworkLease,
    NetworkLeaseAuthority,
    NetworkPurpose,
)
from .sandbox_policy import SandboxPolicy


@dataclass(frozen=True, slots=True)
class ValidatedConnectTargets:
    """Validated numeric destinations; not a connection or permission."""

    hostname: str
    port: int
    targets: tuple[ResolvedNetworkTarget, ...]


def resolve_leased_https_connect_targets(
    request_head: bytes,
    authority: NetworkLeaseAuthority,
    issued: IssuedNetworkLease,
    policy: SandboxPolicy,
    purpose: NetworkPurpose,
    *,
    resolver: Resolver | None = None,
) -> ValidatedConnectTargets:
    """Authorize a CONNECT target, resolve it, and recheck the lease.

    Request parsing and initial lease verification happen before any resolver
    call. A second verification after DNS prevents targets from being handed to
    a caller if the lease was revoked or expired while resolution was pending.
    Since system DNS is synchronous, this function cannot interrupt an
    in-progress resolver call. It never opens or configures a socket.
    """

    target = parse_https_connect_request_head(request_head)
    authority.verify_request(
        issued,
        policy,
        purpose=purpose,
        hostname=target.hostname,
        port=target.port,
        now_monotonic_ns=time.monotonic_ns(),
    )

    targets = resolve_public_tcp_targets(
        target.hostname,
        target.port,
        resolver=resolver,
    )

    authority.verify_request(
        issued,
        policy,
        purpose=purpose,
        hostname=target.hostname,
        port=target.port,
        now_monotonic_ns=time.monotonic_ns(),
    )
    return ValidatedConnectTargets(
        hostname=target.hostname,
        port=target.port,
        targets=targets,
    )
