"""Host-only HTTPS CONNECT authorization and numeric-dial tests."""

from __future__ import annotations

import errno
import select
import selectors
import socket
import threading
import unittest
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.approvals import ScriptedApprover
from icode.network_destination import ResolvedNetworkTarget
from icode.network_lease import NetworkLeaseAuthority, NetworkPurpose
from icode.sandbox_policy import NetworkMode, SandboxPolicy


class NetworkConnectorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.workspace = Path(self._temp_dir.name).resolve()
        self.policy = SandboxPolicy(
            schema_version=1,
            run_id="run-connect-test",
            ticket_id="ICODE-NET-1",
            step="code",
            workspace_root=self.workspace,
            read_roots=(self.workspace,),
            write_roots=(self.workspace,),
            deny_read_roots=(self.workspace / ".git",),
            deny_write_roots=(self.workspace / ".git",),
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            process_limit=8,
            wall_timeout_seconds=60,
            output_limit_bytes=4096,
            protected_paths=(self.workspace / ".git",),
        )
        self.authority = NetworkLeaseAuthority()
        self.issued = self.authority.request_lease(
            self.policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("packages.example",),
            ttl_seconds=30,
        )

    @staticmethod
    def request(hostname: str = "packages.example") -> bytes:
        return (
            f"CONNECT {hostname}:443 HTTP/1.1\r\n"
            f"Host: {hostname}\r\n\r\n"
        ).encode("ascii")

    @staticmethod
    def resolved_target(sockaddr: tuple[object, ...]) -> ResolvedNetworkTarget:
        return ResolvedNetworkTarget(
            family=socket.AF_INET,
            socket_type=socket.SOCK_STREAM,
            protocol=socket.IPPROTO_TCP,
            sockaddr=sockaddr,
        )

    def make_loopback_listener(self) -> socket.socket:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.settimeout(0.2)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        return listener

    def test_pending_dial_closes_wakeup_sockets_when_setup_fails(self) -> None:
        from icode.network_connector import _PendingDial

        class SetupSocket:
            def __init__(self, *, fail_on_nonblocking: bool = False) -> None:
                self.fail_on_nonblocking = fail_on_nonblocking
                self.closed = False

            def setblocking(self, _blocking: bool) -> None:
                if self.fail_on_nonblocking:
                    raise OSError("synthetic setup failure")

            def close(self) -> None:
                self.closed = True

            def fileno(self) -> int:
                return -1 if self.closed else 101

        primary = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(primary.close)
        reader = SetupSocket(fail_on_nonblocking=True)
        writer = SetupSocket()

        with patch("socket.socketpair", return_value=(reader, writer)):
            with self.assertRaises(OSError):
                _PendingDial(primary)  # type: ignore[arg-type]

        self.assertTrue(reader.closed)
        self.assertTrue(writer.closed)

    def test_cleanup_after_promotion_closes_temporary_wakeup_pair(self) -> None:
        from icode.network_connector import _PendingDial, _cleanup_attempt, _close_socket

        primary = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        pending = _PendingDial(primary)
        self.addCleanup(pending.close_on_owner)

        class PromotedConnection:
            def close(self) -> bool:
                return _close_socket(primary)

        cleaned = _cleanup_attempt(
            primary,
            pending,
            self.authority,
            handle=object(),
            active_connection=PromotedConnection(),  # type: ignore[arg-type]
        )

        self.assertTrue(cleaned)
        self.assertEqual(primary.fileno(), -1)
        self.assertEqual(pending.wakeup_reader.fileno(), -1)
        self.assertEqual(pending._wakeup_writer.fileno(), -1)

    def test_rejects_unleased_host_before_dns(self) -> None:
        from icode.network_connector import (
            NetworkConnectError,
            open_authorized_https_connection,
        )

        with patch("icode.network_connector.resolve_public_tcp_targets") as resolver:
            with self.assertRaises(NetworkConnectError):
                open_authorized_https_connection(
                    self.request("other.example"),
                    self.issued,
                    self.policy,
                    authority=self.authority,
                    purpose=NetworkPurpose.PACKAGE_INSTALL,
                )

        resolver.assert_not_called()

    def test_refuses_private_dns_answer_before_socket_creation(self) -> None:
        from icode.network_connector import (
            NetworkConnectError,
            open_authorized_https_connection,
        )

        resolver_calls = 0

        def private_resolver(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", 443),
                )
            ]

        with patch(
            "icode.network_destination._supports_safe_ipaddress_classification",
            return_value=True,
        ), patch("icode.network_connector._new_tcp_socket") as socket_factory:
            with self.assertRaises(NetworkConnectError):
                open_authorized_https_connection(
                    self.request(),
                    self.issued,
                    self.policy,
                    authority=self.authority,
                    purpose=NetworkPurpose.PACKAGE_INSTALL,
                    resolver=private_resolver,
                )

        self.assertEqual(resolver_calls, 1)
        socket_factory.assert_not_called()

    def test_rechecks_lease_after_dns_before_creating_socket(self) -> None:
        from icode.network_connector import (
            NetworkConnectError,
            open_authorized_https_connection,
        )

        target = self.resolved_target(("93.184.216.34", 443))

        def revoke_during_dns(*_args: object, **_kwargs: object) -> tuple[ResolvedNetworkTarget, ...]:
            self.authority.revoke(self.policy)
            return (target,)

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=revoke_during_dns,
        ), patch("icode.network_connector._new_tcp_socket") as socket_factory:
            with self.assertRaises(NetworkConnectError):
                open_authorized_https_connection(
                    self.request(),
                    self.issued,
                    self.policy,
                    authority=self.authority,
                    purpose=NetworkPurpose.PACKAGE_INSTALL,
                )

        socket_factory.assert_not_called()

    def test_connects_to_the_resolver_returned_numeric_sockaddr(self) -> None:
        from icode.network_connector import open_authorized_https_connection

        numeric_target = ("93.184.216.34", 443)
        target = self.resolved_target(numeric_target)

        class ConnectedSocket:
            family = socket.AF_INET

            def __init__(self) -> None:
                self.address: tuple[object, ...] | None = None
                self.closed = False
                self.connect_calls: list[tuple[object, ...]] = []

            def setblocking(self, _blocking: bool) -> None:
                pass

            def connect_ex(self, address: tuple[object, ...]) -> int:
                self.address = address
                self.connect_calls.append(address)
                return 0

            def shutdown(self, _how: int) -> None:
                pass

            def close(self) -> None:
                self.closed = True

            def fileno(self) -> int:
                return -1 if self.closed else 100

        sock = ConnectedSocket()
        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            return_value=(target,),
        ), patch("icode.network_connector._new_tcp_socket", return_value=sock):
            connection = open_authorized_https_connection(
                self.request(),
                self.issued,
                self.policy,
                authority=self.authority,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
            )

        self.assertEqual(sock.address, numeric_target)
        self.assertEqual(sock.connect_calls, [numeric_target])
        self.assertEqual(connection.sockaddr, numeric_target)
        self.assertTrue(connection.close())
        self.assertTrue(sock.closed)

    def test_pending_scope_precedes_connect_ex_and_is_promoted_before_publish(self) -> None:
        from icode.network_connector import open_authorized_https_connection

        listener = self.make_loopback_listener()
        numeric_target = listener.getsockname()
        target = self.resolved_target(numeric_target)
        events: list[tuple[str, object]] = []
        original_register = self.authority.register_active_connection
        original_promote = self.authority.promote_active_connection
        original_connect_ex = socket.socket.connect_ex

        def observe_register(*args: object, **kwargs: object) -> object:
            handle = original_register(*args, **kwargs)
            events.append(("register", kwargs.get("pending")))
            return handle

        def observe_promote(*args: object, **kwargs: object) -> bool:
            promoted = original_promote(*args, **kwargs)
            events.append(("promote", promoted))
            return promoted

        def observe_connect_ex(sock: socket.socket, address: tuple[object, ...]) -> int:
            events.append(("connect_ex", address))
            return original_connect_ex(sock, address)

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            return_value=(target,),
        ), patch.object(
            self.authority,
            "register_active_connection",
            side_effect=observe_register,
        ), patch.object(
            self.authority,
            "promote_active_connection",
            side_effect=observe_promote,
        ), patch.object(socket.socket, "connect_ex", observe_connect_ex):
            connection = open_authorized_https_connection(
                self.request(),
                self.issued,
                self.policy,
                authority=self.authority,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
            )

        peer, _ = listener.accept()
        self.addCleanup(peer.close)
        self.assertEqual(
            [event[0] for event in events],
            ["register", "connect_ex", "promote"],
        )
        self.assertIs(events[0][1], True)
        self.assertEqual(events[1][1], numeric_target)
        self.assertIs(events[2][1], True)
        self.assertTrue(connection.close())

    def test_selector_readiness_is_decided_by_socket_error(self) -> None:
        from icode.network_connector import (
            NetworkConnectError,
            open_authorized_https_connection,
        )

        numeric_target = ("127.0.0.1", 443)
        target = self.resolved_target(numeric_target)

        class ControlledSocket:
            def __init__(self, socket_error: int) -> None:
                self.socket_error = socket_error
                self.closed = False
                self.connect_address: tuple[object, ...] | None = None
                self.socket_error_reads = 0

            def setblocking(self, _blocking: bool) -> None:
                pass

            def connect_ex(self, address: tuple[object, ...]) -> int:
                self.connect_address = address
                return errno.EINPROGRESS

            def getsockopt(self, _level: int, _option: int) -> int:
                self.socket_error_reads += 1
                return self.socket_error

            def shutdown(self, _how: int) -> None:
                pass

            def close(self) -> None:
                self.closed = True

            def fileno(self) -> int:
                return -1 if self.closed else 102

        class WritableSelector:
            def __enter__(self) -> WritableSelector:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def register(self, _fileobj: object, _events: int, data: object = None) -> None:
                pass

            def select(self, timeout: float | None = None) -> list[tuple[object, int]]:
                return [(SimpleNamespace(data="socket"), selectors.EVENT_WRITE)]

            def close(self) -> None:
                return None

        for socket_error, should_connect in (
            (0, True),
            (errno.ECONNREFUSED, False),
        ):
            with self.subTest(socket_error=socket_error):
                sock = ControlledSocket(socket_error)
                promote = self.authority.promote_active_connection
                with patch(
                    "icode.network_connector.resolve_public_tcp_targets",
                    return_value=(target,),
                ), patch(
                    "icode.network_connector._new_tcp_socket",
                    return_value=sock,
                ), patch(
                    "selectors.DefaultSelector",
                    WritableSelector,
                ), patch.object(
                    self.authority,
                    "promote_active_connection",
                    wraps=promote,
                ) as promote_mock:
                    if should_connect:
                        connection = open_authorized_https_connection(
                            self.request(),
                            self.issued,
                            self.policy,
                            authority=self.authority,
                            purpose=NetworkPurpose.PACKAGE_INSTALL,
                        )
                        self.assertTrue(connection.close())
                        self.assertEqual(promote_mock.call_count, 1)
                    else:
                        with self.assertRaises(NetworkConnectError):
                            open_authorized_https_connection(
                                self.request(),
                                self.issued,
                                self.policy,
                                authority=self.authority,
                                purpose=NetworkPurpose.PACKAGE_INSTALL,
                            )
                        promote_mock.assert_not_called()

                self.assertEqual(sock.connect_address, numeric_target)
                self.assertEqual(sock.socket_error_reads, 1)
                self.assertTrue(sock.closed)

    def test_loopback_upstream_is_closed_when_lease_is_revoked(self) -> None:
        from icode.network_connector import open_authorized_https_connection

        listener = self.make_loopback_listener()
        numeric_target = listener.getsockname()
        target = self.resolved_target(numeric_target)
        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            return_value=(target,),
        ):
            connection = open_authorized_https_connection(
                self.request(),
                self.issued,
                self.policy,
                authority=self.authority,
                purpose=NetworkPurpose.PACKAGE_INSTALL,
            )

        peer, _ = listener.accept()
        peer.settimeout(1.0)
        self.addCleanup(peer.close)
        self.assertEqual(connection.upstream_socket.getpeername(), numeric_target)

        self.authority.revoke(self.policy)

        self.assertEqual(peer.recv(1), b"")
        self.assertTrue(connection.close())

    def test_revoke_wakes_selector_owner_and_closes_pending_socket(self) -> None:
        from icode.network_connector import (
            NetworkConnectError,
            open_authorized_https_connection,
        )

        numeric_target = ("127.0.0.1", 443)
        target = self.resolved_target(numeric_target)
        selector_waiting = threading.Event()
        outcomes: list[BaseException | object] = []
        connect_calls: list[tuple[object, ...]] = []
        created_sockets: list[object] = []

        class ControlledSocket:
            def __init__(self, family: int) -> None:
                self._socket = socket.socket(family, socket.SOCK_STREAM)
                self.closed = False

            def setblocking(self, _blocking: bool) -> None:
                pass

            def connect_ex(self, address: tuple[object, ...]) -> int:
                connect_calls.append(address)
                return errno.EINPROGRESS

            def shutdown(self, how: int) -> None:
                self._socket.shutdown(how)

            def close(self) -> None:
                self._socket.close()
                self.closed = True

            def fileno(self) -> int:
                return self._socket.fileno()

        class WakeSelector:
            def __init__(self) -> None:
                self._registrations: list[tuple[object, object]] = []

            def __enter__(self) -> WakeSelector:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def register(self, fileobj: object, _events: int, data: object = None) -> None:
                self._registrations.append((fileobj, data))

            def select(self, timeout: float | None = None) -> list[tuple[object, int]]:
                wake_reader = next(
                    fileobj
                    for fileobj, data in self._registrations
                    if data == "cancel"
                )
                selector_waiting.set()
                readable, _writable, _exceptional = select.select(
                    [wake_reader], [], [], timeout,
                )
                if not readable:
                    return []
                return [
                    (SimpleNamespace(data="cancel"), selectors.EVENT_READ)
                ]

            def close(self) -> None:
                return None

        def worker() -> None:
            try:
                outcomes.append(
                    open_authorized_https_connection(
                        self.request(),
                        self.issued,
                        self.policy,
                        authority=self.authority,
                        purpose=NetworkPurpose.PACKAGE_INSTALL,
                    )
                )
            except BaseException as error:  # captured for assertion in the test thread
                outcomes.append(error)

        def make_controlled_socket(
            family: int,
            _kind: int,
            _protocol: int,
        ) -> ControlledSocket:
            sock = ControlledSocket(family)
            created_sockets.append(sock)
            return sock

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            return_value=(target,),
        ), patch(
            "icode.network_connector._new_tcp_socket",
            side_effect=make_controlled_socket,
        ), patch(
            "selectors.DefaultSelector",
            WakeSelector,
        ):
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            self.assertTrue(selector_waiting.wait(timeout=2.0))
            self.authority.revoke(self.policy)
            thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive(), "connector did not leave the pending connect")
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], NetworkConnectError)
        self.assertEqual(connect_calls, [numeric_target])
        self.assertEqual(len(created_sockets), 1)
        self.assertTrue(created_sockets[0].closed)

    def test_connect_failure_closes_socket_and_releases_scope_entry(self) -> None:
        from icode.network_connector import (
            NetworkConnectError,
            open_authorized_https_connection,
        )

        target = self.resolved_target(("93.184.216.34", 443))
        created_sockets: list[socket.socket] = []
        real_socket_factory = socket.socket

        def make_socket(*args: object, **kwargs: object) -> socket.socket:
            sock = real_socket_factory(*args, **kwargs)
            created_sockets.append(sock)
            return sock

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            return_value=(target,),
        ), patch("icode.network_connector._new_tcp_socket", side_effect=make_socket), patch(
            "icode.network_connector._connect_numeric",
            side_effect=OSError("synthetic connection failure"),
        ):
            with self.assertRaises(NetworkConnectError):
                open_authorized_https_connection(
                    self.request(),
                    self.issued,
                    self.policy,
                    authority=self.authority,
                    purpose=NetworkPurpose.PACKAGE_INSTALL,
                )

        self.assertEqual(len(created_sockets), 1)
        self.assertEqual(created_sockets[0].fileno(), -1)
        self.assertEqual(self.authority.revoke(self.policy), self.issued.lease.generation + 1)

    def test_keyboard_interrupt_closes_pending_descriptors_before_propagating(self) -> None:
        from icode.network_connector import open_authorized_https_connection

        target = self.resolved_target(("93.184.216.34", 443))
        primary = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(primary.close)
        wakeup_sockets: list[socket.socket] = []
        real_socketpair = socket.socketpair

        def make_socketpair() -> tuple[socket.socket, socket.socket]:
            pair = real_socketpair()
            wakeup_sockets.extend(pair)
            return pair

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            return_value=(target,),
        ), patch(
            "icode.network_connector._new_tcp_socket",
            return_value=primary,
        ), patch(
            "icode.network_connector.socket.socketpair",
            side_effect=make_socketpair,
        ), patch(
            "icode.network_connector._connect_numeric",
            side_effect=KeyboardInterrupt,
        ):
            with self.assertRaises(KeyboardInterrupt):
                open_authorized_https_connection(
                    self.request(),
                    self.issued,
                    self.policy,
                    authority=self.authority,
                    purpose=NetworkPurpose.PACKAGE_INSTALL,
                )

        self.assertEqual(primary.fileno(), -1)
        self.assertEqual(len(wakeup_sockets), 2)
        self.assertTrue(all(sock.fileno() == -1 for sock in wakeup_sockets))


if __name__ == "__main__":
    unittest.main()
