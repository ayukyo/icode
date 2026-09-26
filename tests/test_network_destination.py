"""Fail-closed DNS resolution tests for the future host-owned proxy."""

from __future__ import annotations

import socket
import unittest
from typing import Any
from unittest.mock import patch

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.
from icode.network_destination import (
    NetworkDestinationError,
    _supports_safe_ipaddress_classification,
    resolve_public_tcp_targets,
)


class NetworkDestinationTestCase(unittest.TestCase):
    def test_resolves_public_ipv4_and_ipv6_to_numeric_tcp_sockaddrs(self) -> None:
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),
            ),
        ]
        resolver_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            resolver_calls.append((args, kwargs))
            return answers

        targets = resolve_public_tcp_targets(
            "Docs.Example", 443, resolver=resolver,
        )

        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0].sockaddr, ("93.184.216.34", 443))
        self.assertEqual(
            targets[1].sockaddr,
            ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),
        )
        self.assertTrue(all(target.socket_type == socket.SOCK_STREAM for target in targets))
        self.assertTrue(all(target.protocol == socket.IPPROTO_TCP for target in targets))
        self.assertEqual(
            resolver_calls,
            [(("docs.example.", 443), {"type": socket.SOCK_STREAM, "proto": socket.IPPROTO_TCP})],
        )

    def test_default_resolver_uses_socket_getaddrinfo(self) -> None:
        answer = (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
        with patch(
            "icode.network_destination.socket.getaddrinfo",
            return_value=[answer],
        ) as getaddrinfo:
            targets = resolve_public_tcp_targets("Docs.Example", 443)

        self.assertEqual(len(targets), 1)
        getaddrinfo.assert_called_once_with(
            "docs.example.",
            443,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )

    def test_rejects_ip_literals_before_calling_resolver(self) -> None:
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return []

        for hostname in (
            "127.0.0.1",
            "::1",
            "0x7f000001",
            "localhost",
            "docs.example.",
            "文档.example",
            "Key.example",
        ):
            with self.subTest(hostname=hostname):
                with self.assertRaises(NetworkDestinationError):
                    resolve_public_tcp_targets(hostname, 443, resolver=resolver)

        self.assertEqual(resolver_calls, 0)

    def test_rejects_entire_dns_answer_when_any_address_is_not_global(self) -> None:
        private_answers = (
            (socket.AF_INET, ("10.0.0.5", 443)),
            (socket.AF_INET, ("127.0.0.1", 443)),
            (socket.AF_INET, ("169.254.1.1", 443)),
            (socket.AF_INET, ("100.64.0.1", 443)),
            (socket.AF_INET, ("192.0.2.1", 443)),
            (socket.AF_INET, ("224.0.0.1", 443)),
            (socket.AF_INET6, ("::1", 443, 0, 0)),
            (socket.AF_INET6, ("fc00::1", 443, 0, 0)),
            (socket.AF_INET6, ("fe80::1", 443, 0, 0)),
            (socket.AF_INET6, ("2001:db8::1", 443, 0, 0)),
            (socket.AF_INET6, ("ff02::1", 443, 0, 0)),
            (socket.AF_INET6, ("::ffff:93.184.216.34", 443, 0, 0)),
        )

        for family, sockaddr in private_answers:
            with self.subTest(sockaddr=sockaddr):
                answers = [
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        socket.IPPROTO_TCP,
                        "",
                        ("93.184.216.34", 443),
                    ),
                    (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr),
                ]
                with self.assertRaises(NetworkDestinationError):
                    resolve_public_tcp_targets(
                        "docs.example", 443, resolver=lambda *args, **kwargs: answers,
                    )

    def test_rejects_invalid_ports_before_calling_resolver(self) -> None:
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return []

        for port in (80, 444, True, 65536):
            with self.subTest(port=port):
                with self.assertRaises(NetworkDestinationError):
                    resolve_public_tcp_targets("docs.example", port, resolver=resolver)
        self.assertEqual(resolver_calls, 0)

    def test_rejects_scoped_ipv6_answers(self) -> None:
        answers = [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2606:2800::1", 443, 0, 2),
            ),
        ]

        with self.assertRaises(NetworkDestinationError):
            resolve_public_tcp_targets(
                "docs.example", 443, resolver=lambda *args, **kwargs: answers,
            )

        for sockaddr in (
            ("2606:2800::1", 443, 9, 0),
            ("2606:2800::1%eth0", 443, 0, 0),
        ):
            with self.subTest(sockaddr=sockaddr):
                with self.assertRaises(NetworkDestinationError):
                    resolve_public_tcp_targets(
                        "docs.example",
                        443,
                        resolver=lambda *args, **kwargs: [
                            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr),
                        ],
                    )

    def test_rejects_malformed_non_tcp_or_empty_dns_answers(self) -> None:
        invalid_answers = (
            [],
            [(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP, "", ("93.184.216.34", 443))],
            [(socket.AF_UNIX, socket.SOCK_STREAM, 0, "", "/tmp/socket")],
            [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("not-an-ip", 443))],
            [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 8443))],
        )

        for answers in invalid_answers:
            with self.subTest(answers=answers):
                with self.assertRaises(NetworkDestinationError):
                    resolve_public_tcp_targets(
                        "docs.example", 443, resolver=lambda *args, **kwargs: answers,
                    )

    def test_sanitizes_dns_os_errors(self) -> None:
        def failed_resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            raise socket.gaierror("private resolver details")

        with self.assertRaisesRegex(
            NetworkDestinationError, "DNS resolution failed",
        ) as caught:
            resolve_public_tcp_targets("docs.example", 443, resolver=failed_resolver)
        self.assertNotIn("private resolver details", str(caught.exception))

    def test_rejects_runtime_with_stale_ipaddress_special_range_tables(self) -> None:
        resolver_calls = 0

        def resolver(*args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 443),
                ),
            ]

        with patch(
            "icode.network_destination._supports_safe_ipaddress_classification",
            return_value=False,
            create=True,
        ):
            with self.assertRaisesRegex(
                NetworkDestinationError, "Python runtime is too old",
            ):
                resolve_public_tcp_targets("docs.example", 443, resolver=resolver)

        self.assertEqual(resolver_calls, 0)

    def test_ipaddress_special_range_classifier_has_explicit_patch_floor(self) -> None:
        cases = (
            ((3, 11, 9, "final"), False),
            ((3, 11, 10, "final"), True),
            ((3, 12, 3, "final"), False),
            ((3, 12, 4, "final"), True),
            ((3, 13, 0, "final"), True),
            ((3, 13, 0, "alpha"), False),
            ((3, 10, 20, "final"), False),
        )

        for version, expected in cases:
            with self.subTest(version=version):
                self.assertEqual(
                    _supports_safe_ipaddress_classification(version), expected,
                )

    def test_deduplicates_identical_numeric_targets(self) -> None:
        answer = (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
        targets = resolve_public_tcp_targets(
            "docs.example", 443, resolver=lambda *args, **kwargs: [answer, answer],
        )

        self.assertEqual(len(targets), 1)


if __name__ == "__main__":
    unittest.main()
