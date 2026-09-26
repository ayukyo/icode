"""Strict, side-effect-free parsing of the host-owned HTTPS CONNECT preface."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.
from icode.connect_request import (
    ConnectRequestError,
    parse_https_connect_request_head,
)


def _request(
    authority: str = "packages.example:443",
    host: str = "packages.example",
    extra_headers: tuple[bytes, ...] = (),
) -> bytes:
    return (
        f"CONNECT {authority} HTTP/1.1\r\nHost: {host}\r\n".encode("ascii")
        + b"".join(header + b"\r\n" for header in extra_headers)
        + b"\r\n"
    )


class ConnectRequestTestCase(unittest.TestCase):
    def test_parses_exact_https_connect_and_canonicalizes_ascii_host(self) -> None:
        request = _request(
            "Packages.Example:443",
            "PACKAGES.EXAMPLE",
        )

        target = parse_https_connect_request_head(request)

        self.assertEqual(target.hostname, "packages.example")
        self.assertEqual(target.port, 443)

    def test_host_header_may_omit_only_the_default_https_port(self) -> None:
        target = parse_https_connect_request_head(
            _request("packages.example:443", "PACKAGES.EXAMPLE:443")
        )

        self.assertEqual((target.hostname, target.port), ("packages.example", 443))

    def test_rejects_non_connect_or_ambiguous_authorities(self) -> None:
        invalid_requests = (
            _request("packages.example", "packages.example"),
            _request("packages.example:80", "packages.example:80"),
            _request("packages.example:0443", "packages.example:443"),
            _request("127.0.0.1:443", "127.0.0.1:443"),
            _request("[2001:4860::1]:443", "[2001:4860::1]:443"),
            _request("[fe80::1%25en0]:443", "[fe80::1%25en0]:443"),
            _request("user@packages.example:443", "user@packages.example:443"),
            _request("packages.example.:443", "packages.example.:443"),
            _request("packages.example/path:443", "packages.example/path:443"),
            _request("packages.example:443", "other.example"),
            _request("packages.example:443", "packages.example:444"),
            b"GET packages.example:443 HTTP/1.1\r\nHost: packages.example\r\n\r\n",
            b"connect packages.example:443 HTTP/1.1\r\nHost: packages.example\r\n\r\n",
            b"CONNECT  packages.example:443 HTTP/1.1\r\nHost: packages.example\r\n\r\n",
            b"CONNECT packages.example:443 HTTP/1.0\r\nHost: packages.example\r\n\r\n",
            b"CONNECT m\xc3\xbcnich.example:443 HTTP/1.1\r\nHost: m\xc3\xbcnich.example\r\n\r\n",
            (
                b"CONNECT \xe2\x84\xaakey.example:443 HTTP/1.1\r\n"
                b"Host: \xe2\x84\xaakey.example\r\n\r\n"
            ),
        )

        for request in invalid_requests:
            with self.subTest(request=request):
                with self.assertRaises(ConnectRequestError):
                    parse_https_connect_request_head(request)

    def test_requires_one_matching_host_and_rejects_request_framing(self) -> None:
        invalid_requests = (
            b"CONNECT packages.example:443 HTTP/1.1\r\n\r\n",
            _request(extra_headers=(b"Host: packages.example",)),
            _request(extra_headers=(b"Content-Length: 0",)),
            _request(extra_headers=(b"Transfer-Encoding: chunked",)),
            _request(extra_headers=(b"Trailer: X-Extra",)),
            _request(extra_headers=(b"Expect: 100-continue",)),
            _request(extra_headers=(b"Upgrade: websocket",)),
            _request(extra_headers=(b"User-Agent: test-client/1",)),
            _request(extra_headers=(b"Proxy-Connection: Keep-Alive",)),
            _request(extra_headers=(b"Authorization: secret",)),
            _request(extra_headers=(b"Proxy-Authorization: secret",)),
            _request(extra_headers=(b"X-Once: a", b"X-Once: b")),
            _request(extra_headers=(b" Host: packages.example",)),
            _request(extra_headers=(b"BrokenHeader",)),
            _request(extra_headers=(b"Bad\x01Header: value",)),
            _request(extra_headers=(b"X-Bad: \xff",)),
        )

        for request in invalid_requests:
            with self.subTest(request=request):
                with self.assertRaises(ConnectRequestError):
                    parse_https_connect_request_head(request)

    def test_rejects_malformed_line_endings_trailing_data_and_oversized_heads(self) -> None:
        valid = _request()
        malformed_requests = (
            valid.replace(b"\r\n", b"\n"),
            valid.replace(b"\r\n", b"\r"),
            valid + b"unexpected-body",
            valid + _request(),
            valid[:-2],
        )
        for request in malformed_requests:
            with self.subTest(request=request):
                with self.assertRaises(ConnectRequestError):
                    parse_https_connect_request_head(request)

        oversized = _request(extra_headers=(b"X-Large: " + b"a" * 17000,))
        with self.assertRaises(ConnectRequestError):
            parse_https_connect_request_head(oversized)

    def test_rejects_too_many_headers(self) -> None:
        headers = tuple(f"X-{index}: value".encode("ascii") for index in range(64))
        with self.assertRaises(ConnectRequestError):
            parse_https_connect_request_head(_request(extra_headers=headers))

    def test_rejection_message_does_not_echo_untrusted_request_data(self) -> None:
        request = _request(
            "secret.example:444",
            "secret.example:444",
        )

        with self.assertRaises(ConnectRequestError) as context:
            parse_https_connect_request_head(request)

        self.assertEqual(str(context.exception), "invalid or unsupported CONNECT request")

    def test_request_byte_and_header_limits_are_enforced_at_the_boundary(self) -> None:
        request = _request()
        with patch(
            "icode.connect_request.MAX_CONNECT_REQUEST_HEAD_BYTES",
            len(request),
        ):
            parse_https_connect_request_head(request)
        with patch(
            "icode.connect_request.MAX_CONNECT_REQUEST_HEAD_BYTES",
            len(request) - 1,
        ):
            with self.assertRaises(ConnectRequestError):
                parse_https_connect_request_head(request)

        with patch("icode.connect_request.MAX_CONNECT_REQUEST_HEADERS", 1):
            parse_https_connect_request_head(request)
        with patch("icode.connect_request.MAX_CONNECT_REQUEST_HEADERS", 0):
            with self.assertRaises(ConnectRequestError):
                parse_https_connect_request_head(request)


if __name__ == "__main__":
    unittest.main()
