"""Host-only CONNECT scope lifecycle tests using loopback sockets only."""

from __future__ import annotations

import importlib
import importlib.util
import errno
import selectors
import socket
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode.approvals import ScriptedApprover
from icode.network_destination import ResolvedNetworkTarget
from icode.network_lease import NetworkLeaseAuthority, NetworkPurpose
from icode.sandbox_policy import NetworkMode, SandboxPolicy


class NetworkProxyScopeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.workspace = Path(self._temp_dir.name).resolve()
        self.policy = SandboxPolicy(
            schema_version=1,
            run_id="run-proxy-scope-test",
            ticket_id="ICODE-NET-SCOPE-1",
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
            ttl_seconds=60,
        )

    @staticmethod
    def request(hostname: str = "packages.example") -> bytes:
        return (
            f"CONNECT {hostname}:443 HTTP/1.1\r\n"
            f"Host: {hostname}\r\n\r\n"
        ).encode("ascii")

    def make_tcp_pair(self) -> tuple[socket.socket, socket.socket]:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.settimeout(1.0)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)

        peer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        peer.settimeout(2.0)
        self.addCleanup(peer.close)
        peer.connect(listener.getsockname())
        accepted, _ = listener.accept()
        accepted.settimeout(2.0)
        self.addCleanup(accepted.close)
        return peer, accepted

    def make_pending_loopback_listener(self) -> socket.socket:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        held_clients: list[socket.socket] = []
        self.addCleanup(lambda: [client.close() for client in held_clients])
        pending_codes = {
            errno.EINPROGRESS,
            errno.EWOULDBLOCK,
            errno.EALREADY,
            getattr(socket, "WSAEWOULDBLOCK", -1),
            getattr(socket, "WSAEINPROGRESS", -1),
            getattr(socket, "WSAEALREADY", -1),
        }

        for _attempt in range(32):
            candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            candidate.setblocking(False)
            error = candidate.connect_ex(listener.getsockname())
            if error not in (0, *pending_codes):
                candidate.close()
                break
            with selectors.DefaultSelector() as selector:
                selector.register(candidate, selectors.EVENT_WRITE)
                ready = bool(selector.select(timeout=0.03))
            socket_error = candidate.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if ready and socket_error == 0:
                held_clients.append(candidate)
                continue
            if not ready and error in pending_codes:
                candidate.close()
                return listener
            candidate.close()
            break

        self.skipTest("host TCP stack did not provide a pending loopback connect")

    @staticmethod
    def resolve_loopback_target(
        hostname: str,
        port: int,
        *,
        resolver,
    ) -> tuple[ResolvedNetworkTarget, ...]:
        answers = resolver(
            f"{hostname}.",
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        return tuple(
            ResolvedNetworkTarget(
                family=answer[0],
                socket_type=answer[1],
                protocol=answer[2],
                sockaddr=answer[4],
            )
            for answer in answers
        )

    @staticmethod
    def host_scope_types():
        if importlib.util.find_spec("icode.network_proxy_scope") is None:
            return None, None
        module = importlib.import_module("icode.network_proxy_scope")
        return (
            getattr(module, "HostConnectRuntime", None),
            getattr(module, "HostHttpsConnectScope", None),
        )

    def test_scope_close_during_dns_prevents_late_upstream_dial(self) -> None:
        runtime_type, scope_type = self.host_scope_types()
        self.assertTrue(callable(runtime_type), "host CONNECT runtime is missing")
        self.assertTrue(callable(scope_type), "host-owned CONNECT scope is missing")

        upstream_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream_listener.setblocking(False)
        upstream_listener.bind(("127.0.0.1", 0))
        upstream_listener.listen(1)
        self.addCleanup(upstream_listener.close)

        client_peer, proxy_client = self.make_tcp_pair()
        runtime = runtime_type(
            self.authority,
            sweep_interval_seconds=0.01,
        )
        runtime.start()
        self.addCleanup(runtime.close)
        scope = runtime.create_scope(
            self.issued,
            self.policy,
            NetworkPurpose.PACKAGE_INSTALL,
        )
        resolver_started = threading.Event()
        release_resolver = threading.Event()
        results: list[BaseException] = []

        def resolver(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
            resolver_started.set()
            if not release_resolver.wait(timeout=3):
                raise TimeoutError("test resolver release timed out")
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    upstream_listener.getsockname(),
                )
            ]

        def open_scope() -> None:
            try:
                scope.open_connect(proxy_client, self.request(), resolver=resolver)
            except BaseException as error:  # Capture the thread result for assertions.
                results.append(error)

        worker = threading.Thread(target=open_scope, daemon=True)
        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=self.resolve_loopback_target,
        ):
            worker.start()
            self.assertTrue(resolver_started.wait(timeout=2), "resolver was not reached")

            self.assertFalse(runtime.close())
            self.assertEqual(client_peer.recv(1), b"")
            release_resolver.set()
            worker.join(timeout=3)

            self.assertFalse(
                worker.is_alive(), "CONNECT open did not unwind after cancellation"
            )
            self.assertEqual(len(results), 1)
            self.assertTrue(runtime.close())
            with self.assertRaises(BlockingIOError):
                upstream_listener.accept()

    def test_policy_revoke_closes_client_and_connected_upstream_peers(self) -> None:
        runtime_type, scope_type = self.host_scope_types()
        self.assertTrue(callable(scope_type), "host-owned CONNECT scope is missing")
        runtime = runtime_type(
            self.authority,
            sweep_interval_seconds=0.01,
        )
        runtime.start()
        self.addCleanup(runtime.close)
        scope = runtime.create_scope(
            self.issued,
            self.policy,
            NetworkPurpose.PACKAGE_INSTALL,
        )

        upstream_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream_listener.settimeout(2.0)
        upstream_listener.bind(("127.0.0.1", 0))
        upstream_listener.listen(1)
        self.addCleanup(upstream_listener.close)
        client_peer, proxy_client = self.make_tcp_pair()

        def resolver(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    upstream_listener.getsockname(),
                )
            ]

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=self.resolve_loopback_target,
        ):
            tunnel = scope.open_connect(
                proxy_client,
                self.request(),
                resolver=resolver,
            )
        upstream_peer, _address = upstream_listener.accept()
        upstream_peer.settimeout(2.0)
        self.addCleanup(upstream_peer.close)

        client_peer.sendall(b"client-to-host")
        self.assertEqual(tunnel.client_socket.recv(14), b"client-to-host")
        tunnel.upstream_socket.sendall(b"client-to-upstream")
        self.assertEqual(upstream_peer.recv(19), b"client-to-upstream")
        upstream_peer.sendall(b"upstream-to-host")
        self.assertEqual(tunnel.upstream_socket.recv(16), b"upstream-to-host")
        tunnel.client_socket.sendall(b"host-to-client")
        self.assertEqual(client_peer.recv(14), b"host-to-client")

        self.authority.revoke(self.policy)

        self.assertEqual(client_peer.recv(1), b"")
        self.assertEqual(upstream_peer.recv(1), b"")
        later_peer, later_client = self.make_tcp_pair()
        late_dns_calls: list[bool] = []

        def forbidden_resolver(*_args: object, **_kwargs: object):
            late_dns_calls.append(True)
            return []

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=self.resolve_loopback_target,
        ):
            with self.assertRaises(ConnectionError):
                scope.open_connect(
                    later_client,
                    self.request(),
                    resolver=forbidden_resolver,
                )
        self.assertEqual(late_dns_calls, [])
        self.assertEqual(later_peer.recv(1), b"")
        self.assertTrue(runtime.close())

    def test_scope_close_cancels_pending_numeric_connect_on_its_owner(self) -> None:
        runtime_type, scope_type = self.host_scope_types()
        self.assertTrue(callable(runtime_type), "host CONNECT runtime is missing")
        self.assertTrue(callable(scope_type), "host-owned CONNECT scope is missing")
        runtime = runtime_type(self.authority, sweep_interval_seconds=0.01)
        runtime.start()
        self.addCleanup(runtime.close)
        scope = runtime.create_scope(
            self.issued,
            self.policy,
            NetworkPurpose.PACKAGE_INSTALL,
        )
        listener = self.make_pending_loopback_listener()
        client_peer, proxy_client = self.make_tcp_pair()
        candidate_sockets: list[socket.socket] = []
        connect_results: list[int] = []
        connect_started = threading.Event()
        release_connect_ex = threading.Event()
        self.addCleanup(release_connect_ex.set)
        outcomes: list[BaseException | object] = []
        original_connect_ex = socket.socket.connect_ex

        def observe_connect_ex(
            candidate: socket.socket,
            address: tuple[object, ...],
        ) -> int:
            result = original_connect_ex(candidate, address)
            if address == listener.getsockname():
                candidate_sockets.append(candidate)
                connect_results.append(result)
                connect_started.set()
                release_connect_ex.wait(timeout=2)
            return result

        target = ResolvedNetworkTarget(
            family=socket.AF_INET,
            socket_type=socket.SOCK_STREAM,
            protocol=socket.IPPROTO_TCP,
            sockaddr=listener.getsockname(),
        )

        def open_scope() -> None:
            try:
                scope.open_connect(
                    proxy_client,
                    self.request(),
                    resolver=lambda *_args, **_kwargs: [],
                )
            except BaseException as error:
                outcomes.append(error)

        worker = threading.Thread(target=open_scope, daemon=True)
        with (
            patch(
                "icode.network_connector.resolve_public_tcp_targets",
                return_value=(target,),
            ),
            patch.object(socket.socket, "connect_ex", observe_connect_ex),
        ):
            worker.start()
            self.assertTrue(connect_started.wait(timeout=2), "numeric dial did not start")
            from icode.network_connector import _CONNECT_IN_PROGRESS_CODES

            self.assertIn(connect_results[0], _CONNECT_IN_PROGRESS_CODES)
            self.assertFalse(runtime.close())
            self.assertEqual(client_peer.recv(1), b"")
        release_connect_ex.set()
        worker.join(timeout=2)

        self.assertFalse(worker.is_alive(), "cancelled numeric dial did not unwind")
        self.assertEqual(len(outcomes), 1)
        self.assertTrue(candidate_sockets)
        self.assertLess(candidate_sockets[0].fileno(), 0)
        self.assertTrue(runtime.close())

    def test_lease_expiry_closes_both_peers_and_blocks_later_dns(self) -> None:
        runtime_type, scope_type = self.host_scope_types()
        self.assertTrue(callable(runtime_type), "host CONNECT runtime is missing")
        self.assertTrue(callable(scope_type), "host-owned CONNECT scope is missing")
        authority = NetworkLeaseAuthority()
        issued = authority.request_lease(
            self.policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("packages.example",),
            ttl_seconds=1,
        )
        runtime = runtime_type(authority, sweep_interval_seconds=0.01)
        runtime.start()
        self.addCleanup(runtime.close)
        scope = runtime.create_scope(
            issued,
            self.policy,
            NetworkPurpose.PACKAGE_INSTALL,
        )

        upstream_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream_listener.settimeout(2.0)
        upstream_listener.bind(("127.0.0.1", 0))
        upstream_listener.listen(1)
        self.addCleanup(upstream_listener.close)
        client_peer, proxy_client = self.make_tcp_pair()
        resolver_calls = 0

        def resolver(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
            nonlocal resolver_calls
            resolver_calls += 1
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    upstream_listener.getsockname(),
                )
            ]

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=self.resolve_loopback_target,
        ):
            tunnel = scope.open_connect(
                proxy_client,
                self.request(),
                resolver=resolver,
            )
        upstream_peer, _address = upstream_listener.accept()
        upstream_peer.settimeout(2.0)
        self.addCleanup(upstream_peer.close)

        self.assertEqual(client_peer.recv(1), b"")
        self.assertEqual(upstream_peer.recv(1), b"")

        expired_peer, expired_client = self.make_tcp_pair()
        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=self.resolve_loopback_target,
        ):
            with self.assertRaises(ConnectionError):
                scope.open_connect(
                    expired_client,
                    self.request(),
                    resolver=resolver,
                )
        self.assertEqual(resolver_calls, 1)
        self.assertEqual(expired_peer.recv(1), b"")
        self.assertTrue(tunnel.close())
        self.assertTrue(runtime.close())

    def test_closing_one_scope_preserves_sibling_scope_under_same_policy(self) -> None:
        runtime_type, scope_type = self.host_scope_types()
        self.assertTrue(callable(runtime_type), "host CONNECT runtime is missing")
        self.assertTrue(callable(scope_type), "host-owned CONNECT scope is missing")
        authority = NetworkLeaseAuthority()
        issued = authority.request_lease(
            self.policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("packages.example", "mirror.example"),
            ttl_seconds=60,
        )
        runtime = runtime_type(authority, sweep_interval_seconds=0.01)
        runtime.start()
        self.addCleanup(runtime.close)
        first_scope = runtime.create_scope(
            issued,
            self.policy,
            NetworkPurpose.PACKAGE_INSTALL,
        )
        second_scope = runtime.create_scope(
            issued,
            self.policy,
            NetworkPurpose.PACKAGE_INSTALL,
        )

        first_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        second_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for listener in (first_listener, second_listener):
            listener.settimeout(2.0)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            self.addCleanup(listener.close)
        first_client_peer, first_proxy_client = self.make_tcp_pair()
        second_client_peer, second_proxy_client = self.make_tcp_pair()

        def open_scope(scope, client, hostname, listener):
            def resolver(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
                return [
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        socket.IPPROTO_TCP,
                        "",
                        listener.getsockname(),
                    )
                ]

            return scope.open_connect(
                client,
                self.request(hostname),
                resolver=resolver,
            )

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=self.resolve_loopback_target,
        ):
            first_tunnel = open_scope(
                first_scope,
                first_proxy_client,
                "packages.example",
                first_listener,
            )
            second_tunnel = open_scope(
                second_scope,
                second_proxy_client,
                "mirror.example",
                second_listener,
            )
        first_upstream_peer, _address = first_listener.accept()
        second_upstream_peer, _address = second_listener.accept()
        self.addCleanup(first_upstream_peer.close)
        self.addCleanup(second_upstream_peer.close)

        self.assertTrue(first_scope.close())
        self.assertEqual(first_client_peer.recv(1), b"")
        self.assertEqual(first_upstream_peer.recv(1), b"")

        second_client_peer.sendall(b"still-open")
        self.assertEqual(second_tunnel.client_socket.recv(10), b"still-open")
        second_tunnel.upstream_socket.sendall(b"still-open")
        self.assertEqual(second_upstream_peer.recv(10), b"still-open")
        self.assertEqual(second_tunnel.upstream_socket.getpeername(), second_listener.getsockname())

        self.assertTrue(runtime.close())
        self.assertEqual(second_client_peer.recv(1), b"")
        self.assertEqual(second_upstream_peer.recv(1), b"")
        self.assertTrue(first_tunnel.close())


if __name__ == "__main__":
    unittest.main()
