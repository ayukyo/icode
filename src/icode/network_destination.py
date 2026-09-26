"""Resolve approved HTTPS hostnames to validated numeric TCP destinations.

This is a host-side input-validation primitive for a future trusted proxy. It
does not verify a network lease, open a destination TCP connection, grant worker
access, or enforce operating-system routing. Its default system resolver may
perform host DNS I/O, so the trusted caller must verify the lease first. It must
connect only to one of the returned numeric ``sockaddr`` values and never pass
the hostname to a second resolver during connection establishment.
"""

from __future__ import annotations

import ipaddress
import socket
import sys
from dataclasses import dataclass
from typing import Callable

from .network_lease import HTTPS_PORT
from .sandbox_policy import is_exact_dns_hostname


class NetworkDestinationError(ValueError):
    """Raised when an HTTPS hostname cannot be safely resolved and pinned."""


@dataclass(frozen=True, slots=True)
class ResolvedNetworkTarget:
    """One validated numeric TCP destination returned by the trusted resolver."""

    family: int
    socket_type: int
    protocol: int
    sockaddr: tuple[object, ...]


Resolver = Callable[..., list[tuple[int, int, int, str, tuple[object, ...]]]]


def _supports_safe_ipaddress_classification(
    version: tuple[int, int, int, str],
) -> bool:
    """Avoid prereleases and patch releases with stale IANA range tables."""

    if (
        type(version) is not tuple
        or len(version) != 4
        or any(type(part) is not int for part in version[:3])
        or type(version[3]) is not str
        or version[3] != "final"
    ):
        return False
    numeric_version = version[:3]
    return (
        numeric_version >= (3, 13, 0)
        or (numeric_version[:2] == (3, 12) and numeric_version >= (3, 12, 4))
        or (numeric_version[:2] == (3, 11) and numeric_version >= (3, 11, 10))
    )


def _is_global_unicast(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Conservatively reject special-purpose and non-globally-routable IPs."""

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return False
    return (
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def resolve_public_tcp_targets(
    hostname: str,
    port: int,
    *,
    resolver: Resolver | None = None,
) -> tuple[ResolvedNetworkTarget, ...]:
    """Resolve one exact DNS name to numeric, globally routable HTTPS targets.

    Every answer must be a public IPv4/IPv6 TCP stream address. If DNS returns
    a mix of public and non-public targets, the whole result is rejected rather
    than silently selecting only the public subset. The returned ``sockaddr``
    values contain numeric addresses and normalized scope/flow fields so a
    later connector can pin the exact address that was checked.
    """

    if type(hostname) is not str:
        raise NetworkDestinationError("hostname must be an exact ASCII DNS name")
    if not is_exact_dns_hostname(hostname):
        raise NetworkDestinationError("hostname must be an exact ASCII DNS name")
    normalized_hostname = hostname.lower()
    if type(port) is not int or port != HTTPS_PORT:
        raise NetworkDestinationError("network destinations currently require HTTPS port 443")
    runtime_version = sys.version_info
    if not _supports_safe_ipaddress_classification((
        runtime_version.major,
        runtime_version.minor,
        runtime_version.micro,
        runtime_version.releaselevel,
    )):
        raise NetworkDestinationError(
            "Python runtime is too old for safe IANA special-range classification"
        )

    resolve = socket.getaddrinfo if resolver is None else resolver
    if not callable(resolve):
        raise NetworkDestinationError("a trusted DNS resolver is required")
    try:
        # Make this an absolute DNS name so local search domains cannot rewrite it.
        answers = resolve(
            f"{normalized_hostname}.",
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except OSError:
        raise NetworkDestinationError("DNS resolution failed") from None

    if type(answers) not in (list, tuple) or not answers:
        raise NetworkDestinationError("DNS returned no usable TCP destinations")

    targets: list[ResolvedNetworkTarget] = []
    seen: set[tuple[int, tuple[object, ...]]] = set()
    for answer in answers:
        if type(answer) is not tuple or len(answer) != 5:
            raise NetworkDestinationError("DNS returned a malformed TCP destination")
        family, socket_type, protocol, _canonical_name, sockaddr = answer
        if (
            not isinstance(family, int)
            or isinstance(family, bool)
            or family not in (socket.AF_INET, socket.AF_INET6)
            or not isinstance(socket_type, int)
            or isinstance(socket_type, bool)
            or socket_type != socket.SOCK_STREAM
            or not isinstance(protocol, int)
            or isinstance(protocol, bool)
            or protocol not in (0, socket.IPPROTO_TCP)
            or type(sockaddr) is not tuple
        ):
            raise NetworkDestinationError("DNS returned a non-TCP or unsupported destination")

        family_value = int(family)
        expected_length = 2 if family_value == socket.AF_INET else 4
        if len(sockaddr) != expected_length:
            raise NetworkDestinationError("DNS returned an invalid IP socket address")
        address_text = sockaddr[0]
        address_port = sockaddr[1]
        if type(address_text) is not str or type(address_port) is not int:
            raise NetworkDestinationError("DNS returned an invalid IP socket address")
        if address_port != port or "%" in address_text:
            raise NetworkDestinationError("DNS returned an invalid or scoped IP address")

        try:
            address = ipaddress.ip_address(address_text)
        except ValueError:
            raise NetworkDestinationError("DNS returned a non-numeric IP address") from None
        expected_version = 4 if family_value == socket.AF_INET else 6
        if address.version != expected_version or not _is_global_unicast(address):
            raise NetworkDestinationError("DNS resolved to a non-public IP address")

        if family_value == socket.AF_INET:
            normalized_sockaddr: tuple[object, ...] = (str(address), port)
        else:
            flowinfo = sockaddr[2]
            scope_id = sockaddr[3]
            if (
                type(flowinfo) is not int
                or flowinfo != 0
                or type(scope_id) is not int
                or scope_id != 0
            ):
                raise NetworkDestinationError("DNS returned a scoped or altered IPv6 address")
            normalized_sockaddr = (str(address), port, 0, 0)

        key = (family_value, normalized_sockaddr)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            ResolvedNetworkTarget(
                family=family_value,
                socket_type=socket.SOCK_STREAM,
                protocol=socket.IPPROTO_TCP,
                sockaddr=normalized_sockaddr,
            )
        )

    if not targets:
        raise NetworkDestinationError("DNS returned no usable TCP destinations")
    return tuple(targets)
