"""Strict, side-effect-free parser for a future host-owned HTTPS CONNECT path."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .network_lease import HTTPS_PORT
from .sandbox_policy import is_exact_dns_hostname


MAX_CONNECT_REQUEST_HEAD_BYTES = 16 * 1024
MAX_CONNECT_REQUEST_HEADERS = 32
_HEADER_NAME_PATTERN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_HEADER_TERMINATOR = b"\r\n\r\n"
_INVALID_REQUEST = "invalid or unsupported CONNECT request"
_HTTPS_PORT_TEXT = str(HTTPS_PORT).encode("ascii")


class ConnectRequestError(ValueError):
    """Raised when a CONNECT request is outside the supported narrow contract."""


@dataclass(frozen=True, slots=True)
class HttpsConnectTarget:
    """The normalized DNS destination extracted from an accepted CONNECT head."""

    hostname: str
    port: int


def parse_https_connect_request_head(request_head: bytes) -> HttpsConnectTarget:
    """Parse a bounded CONNECT header block without performing network I/O.

    ICODE intentionally accepts only the authority-form HTTPS CONNECT shape
    ``CONNECT exact-ascii-host:443 HTTP/1.1`` and one matching ``Host`` field.
    It rejects all other fields, including request-body framing and proxy
    credentials, so no unparsed metadata can affect a future connector.
    """

    if type(request_head) is not bytes or not request_head:
        raise ConnectRequestError(_INVALID_REQUEST)
    if len(request_head) > MAX_CONNECT_REQUEST_HEAD_BYTES:
        raise ConnectRequestError(_INVALID_REQUEST)
    if (
        not request_head.endswith(_HEADER_TERMINATOR)
        or request_head.count(_HEADER_TERMINATOR) != 1
    ):
        raise ConnectRequestError(_INVALID_REQUEST)

    lines = request_head[:-len(_HEADER_TERMINATOR)].split(b"\r\n")
    if not lines or len(lines) - 1 > MAX_CONNECT_REQUEST_HEADERS:
        raise ConnectRequestError(_INVALID_REQUEST)
    request_line = lines[0]
    if any(byte < 0x20 or byte == 0x7F for byte in request_line):
        raise ConnectRequestError(_INVALID_REQUEST)
    try:
        method, authority, version = request_line.split(b" ")
    except ValueError:
        raise ConnectRequestError(_INVALID_REQUEST) from None
    if method != b"CONNECT" or version != b"HTTP/1.1":
        raise ConnectRequestError(_INVALID_REQUEST)

    hostname = _parse_authority(authority)
    host_fields = 0
    for line in lines[1:]:
        if not line or line.startswith((b" ", b"\t")):
            raise ConnectRequestError(_INVALID_REQUEST)
        separator = line.find(b":")
        if separator <= 0:
            raise ConnectRequestError(_INVALID_REQUEST)
        name = line[:separator]
        value = line[separator + 1:]
        if _HEADER_NAME_PATTERN.fullmatch(name) is None:
            raise ConnectRequestError(_INVALID_REQUEST)
        if any((byte < 0x20 and byte != 0x09) or byte == 0x7F for byte in value):
            raise ConnectRequestError(_INVALID_REQUEST)
        if name.lower() != b"host":
            raise ConnectRequestError(_INVALID_REQUEST)
        host_fields += 1
        if host_fields != 1 or _parse_host_field(value) != hostname:
            raise ConnectRequestError(_INVALID_REQUEST)

    if host_fields != 1:
        raise ConnectRequestError(_INVALID_REQUEST)
    return HttpsConnectTarget(hostname=hostname, port=HTTPS_PORT)


def _parse_authority(authority: bytes) -> str:
    """Return a canonical DNS hostname from an exact ``host:443`` target."""

    if authority.count(b":") != 1:
        raise ConnectRequestError(_INVALID_REQUEST)
    hostname_bytes, port_bytes = authority.split(b":", 1)
    if port_bytes != _HTTPS_PORT_TEXT:
        raise ConnectRequestError(_INVALID_REQUEST)
    try:
        hostname = hostname_bytes.decode("ascii")
    except UnicodeDecodeError:
        raise ConnectRequestError(_INVALID_REQUEST) from None
    if not is_exact_dns_hostname(hostname):
        raise ConnectRequestError(_INVALID_REQUEST)
    return hostname.lower()


def _parse_host_field(value: bytes) -> str | None:
    """Parse Host with only the implicit or explicit default HTTPS port."""

    normalized_value = value.strip(b" \t")
    if normalized_value.count(b":") > 1:
        return None
    if b":" in normalized_value:
        hostname_bytes, port_bytes = normalized_value.split(b":", 1)
        if port_bytes != _HTTPS_PORT_TEXT:
            return None
    else:
        hostname_bytes = normalized_value
    try:
        hostname = hostname_bytes.decode("ascii")
    except UnicodeDecodeError:
        return None
    if not is_exact_dns_hostname(hostname):
        return None
    return hostname.lower()
