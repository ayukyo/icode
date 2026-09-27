"""Host-side CONNECT listener lifecycle tests using loopback sockets only."""

from __future__ import annotations

import array
import errno
import os
import socket
import sys
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.

from icode import linux_proxy_handoff, network_proxy_server
from icode.approvals import ScriptedApprover
from icode.network_destination import ResolvedNetworkTarget
from icode.network_lease import NetworkLeaseAuthority, NetworkPurpose
from icode.network_proxy_scope import HostConnectRuntime
from icode.network_proxy_server import HostConnectProxyError, HostConnectProxyServer
from icode.sandbox_policy import NetworkMode, SandboxPolicy


class NetworkProxyServerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        workspace = Path(self.temp_dir.name).resolve()
        self.policy = SandboxPolicy(
            schema_version=1,
            run_id="run-proxy-server-test",
            ticket_id="ICODE-NET-SERVER-1",
            step="code",
            workspace_root=workspace,
            read_roots=(workspace,),
            write_roots=(workspace,),
            deny_read_roots=(workspace / ".git",),
            deny_write_roots=(workspace / ".git",),
            network_mode=NetworkMode.DENY,
            allowed_domains=(),
            process_limit=8,
            wall_timeout_seconds=60,
            output_limit_bytes=4096,
            protected_paths=(workspace / ".git",),
        )
        self.authority = NetworkLeaseAuthority()
        self.issued = self.authority.request_lease(
            self.policy,
            approver=ScriptedApprover([True]),
            purpose=NetworkPurpose.PACKAGE_INSTALL,
            allowed_domains=("packages.example",),
            ttl_seconds=60,
        )
        self.runtime = HostConnectRuntime(self.authority, sweep_interval_seconds=0.01)
        self.runtime.start()
        self.addCleanup(self.runtime.close)
        self.scope = self.runtime.create_scope(
            self.issued,
            self.policy,
            NetworkPurpose.PACKAGE_INSTALL,
        )

    @staticmethod
    def request() -> bytes:
        return b"CONNECT packages.example:443 HTTP/1.1\r\nHost: packages.example\r\n\r\n"

    @staticmethod
    def local_resolver(hostname: str, port: int, address: tuple[str, int]):
        def resolve(*_args: object, **_kwargs: object) -> tuple[ResolvedNetworkTarget, ...]:
            return (
                ResolvedNetworkTarget(
                    family=socket.AF_INET,
                    socket_type=socket.SOCK_STREAM,
                    protocol=socket.IPPROTO_TCP,
                    sockaddr=address,
                ),
            )

        return resolve

    def make_listener(self) -> socket.socket:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        listener.setblocking(False)
        self.addCleanup(listener.close)
        return listener

    def make_server(self, listener: socket.socket) -> HostConnectProxyServer:
        server = HostConnectProxyServer(listener, self.scope)
        self.addCleanup(server.close)
        return server

    def assert_peer_closed(self, client: socket.socket) -> None:
        try:
            self.assertEqual(client.recv(1), b"")
        except ConnectionResetError:
            # Closing with an unread partial CONNECT head may be reported as RST.
            pass

    def test_listener_connects_before_200_and_relays_both_directions(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        upstream_listener = self.make_listener()
        upstream_listener.settimeout(2.0)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        served: list[bool] = []

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=lambda hostname, port, resolver=None: self.local_resolver(
                hostname,
                port,
                upstream_listener.getsockname(),
            )(hostname, port),
        ):
            worker = threading.Thread(
                target=lambda: served.append(server.serve_once()),
                daemon=True,
            )
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(self.request())
            response = bytearray()
            while not response.endswith(b"\r\n\r\n"):
                response.extend(client.recv(1))
            self.assertEqual(
                bytes(response),
                b"HTTP/1.1 200 Connection Established\r\n\r\n",
            )

            upstream, _address = upstream_listener.accept()
            upstream.settimeout(2.0)
            self.addCleanup(upstream.close)
            client.sendall(b"client payload")
            self.assertEqual(upstream.recv(14), b"client payload")
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(upstream.recv(1), b"")
            upstream.sendall(b"upstream payload")
            self.assertEqual(client.recv(16), b"upstream payload")
            upstream.shutdown(socket.SHUT_WR)
            self.assertEqual(client.recv(1), b"")
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(served, [True])
        self.assertTrue(server.close())

    def test_serve_forever_can_signal_readiness_before_payload_ack(self) -> None:
        server = self.make_server(self.make_listener())
        ready = threading.Event()
        stop = threading.Event()
        failures: list[BaseException] = []

        def serve() -> None:
            try:
                server.serve_forever(stop, ready_event=ready)
            except BaseException as exc:
                failures.append(exc)

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            self.assertTrue(
                ready.wait(1.0),
                "listener loop must be healthy before the sandbox is released",
            )
            self.assertTrue(worker.is_alive())
            self.assertEqual(failures, [])
        finally:
            stop.set()
            server.close()
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux SCM_RIGHTS")
    def test_handoff_session_starts_ready_proxy_before_ack_and_relays(self) -> None:
        session_type = getattr(
            network_proxy_server, "LinuxHostConnectProxySession", None,
        )
        self.assertTrue(
            callable(session_type),
            "Linux handoff must have a host-owned CONNECT session coordinator",
        )
        listener = self.make_listener()
        upstream_listener = self.make_listener()
        upstream_listener.settimeout(2.0)
        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        self.addCleanup(host_control.close)
        self.addCleanup(sender_control.close)
        nonce = bytes.fromhex("102132435465768798a9bacbdcedfe0f")
        payload = b"ICODE_PROXY_LISTENER_V1" + nonce
        rights = array.array("i", [listener.fileno()])
        self.assertEqual(
            sender_control.sendmsg(
                [payload], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)],
            ),
            len(payload),
        )
        session = session_type(
            host_control,
            expected_pid=os.getpid(),
            scope=self.scope,
            handoff_timeout_seconds=1.0,
            ready_timeout_seconds=1.0,
        )
        self.addCleanup(session.close)
        acknowledge = linux_proxy_handoff.acknowledge_loopback_listener_handoff

        def acknowledge_only_after_ready(control: socket.socket, received: socket.socket) -> None:
            self.assertTrue(session.ready)
            self.assertFalse(session.acknowledged)
            acknowledge(control, received)

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        with (
            patch(
                "icode.linux_proxy_handoff.acknowledge_loopback_listener_handoff",
                side_effect=acknowledge_only_after_ready,
            ),
            patch(
                "icode.network_connector.resolve_public_tcp_targets",
                side_effect=lambda hostname, port, resolver=None: self.local_resolver(
                    hostname, port, upstream_listener.getsockname(),
                )(hostname, port),
            ),
        ):
            session.start()
            sender_control.settimeout(1.0)
            self.assertEqual(
                sender_control.recv(64),
                b"ICODE_PROXY_LISTENER_ACK_V1" + nonce,
            )
            client.connect(listener.getsockname())
            client.sendall(self.request())
            response = bytearray()
            while not response.endswith(b"\r\n\r\n"):
                response.extend(client.recv(1))
            self.assertEqual(
                bytes(response),
                b"HTTP/1.1 200 Connection Established\r\n\r\n",
            )
            upstream, _address = upstream_listener.accept()
            upstream.settimeout(2.0)
            self.addCleanup(upstream.close)
            client.sendall(b"handoff request")
            self.assertEqual(upstream.recv(16), b"handoff request")
            upstream.sendall(b"handoff response")
            self.assertEqual(client.recv(16), b"handoff response")
            self.assertTrue(session.close())
            self.assert_peer_closed(client)

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux SCM_RIGHTS")
    def test_revoked_lease_does_not_ack_payload_and_closes_handoff(self) -> None:
        session_type = getattr(
            network_proxy_server, "LinuxHostConnectProxySession", None,
        )
        self.assertTrue(
            callable(session_type),
            "Linux handoff must have a host-owned CONNECT session coordinator",
        )
        listener = self.make_listener()
        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        self.addCleanup(host_control.close)
        self.addCleanup(sender_control.close)
        nonce = bytes.fromhex("ffeeddccbbaa99887766554433221100")
        payload = b"ICODE_PROXY_LISTENER_V1" + nonce
        rights = array.array("i", [listener.fileno()])
        sender_control.sendmsg(
            [payload], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)],
        )
        session = session_type(
            host_control,
            expected_pid=os.getpid(),
            scope=self.scope,
            handoff_timeout_seconds=1.0,
            ready_timeout_seconds=1.0,
        )
        self.addCleanup(session.close)
        self.authority.revoke(self.policy)

        with self.assertRaises(HostConnectProxyError):
            session.start()

        sender_control.settimeout(1.0)
        self.assertEqual(sender_control.recv(64), b"")
        self.assertFalse(session.acknowledged)

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux SCM_RIGHTS")
    def test_revoked_lease_is_rechecked_at_the_ack_boundary(self) -> None:
        session_type = getattr(
            network_proxy_server, "LinuxHostConnectProxySession", None,
        )
        self.assertTrue(callable(session_type), "Linux handoff session is required")
        listener = self.make_listener()
        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        self.addCleanup(host_control.close)
        self.addCleanup(sender_control.close)
        nonce = bytes.fromhex("1234567890abcdef1234567890abcdef")
        payload = b"ICODE_PROXY_LISTENER_V1" + nonce
        rights = array.array("i", [listener.fileno()])
        sender_control.sendmsg(
            [payload], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)],
        )
        session = session_type(
            host_control,
            expected_pid=os.getpid(),
            scope=self.scope,
            handoff_timeout_seconds=1.0,
            ready_timeout_seconds=1.0,
        )
        self.addCleanup(session.close)
        original_verify = self.scope.verify_lease
        original_guard = self.scope.live_lease_guard

        def keep_ready_thread_alive(
            server: HostConnectProxyServer,
            _stop_event: threading.Event,
            *,
            ready_event: threading.Event,
        ) -> None:
            original_verify()
            ready_event.set()
            server._closed_event.wait(2.0)

        @contextmanager
        def revoke_before_ack_guard():
            self.authority.revoke(self.policy)
            with original_guard():
                yield

        with (
            patch.object(
                HostConnectProxyServer,
                "serve_forever",
                new=keep_ready_thread_alive,
            ),
            patch.object(self.scope, "live_lease_guard", new=revoke_before_ack_guard),
        ):
            with self.assertRaises(HostConnectProxyError):
                session.start()

        self.assertTrue(session._ready_event.is_set())
        sender_control.settimeout(1.0)
        self.assertEqual(sender_control.recv(64), b"")
        self.assertFalse(session.acknowledged)

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux SCM_RIGHTS")
    def test_close_during_handoff_reports_incomplete_then_retries(self) -> None:
        session_type = getattr(
            network_proxy_server, "LinuxHostConnectProxySession", None,
        )
        self.assertTrue(callable(session_type), "Linux handoff session is required")
        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        self.addCleanup(host_control.close)
        self.addCleanup(sender_control.close)
        session = session_type(
            host_control,
            expected_pid=os.getpid(),
            scope=self.scope,
            handoff_timeout_seconds=0.1,
            ready_timeout_seconds=1.0,
        )
        self.addCleanup(session.close)
        errors: list[BaseException] = []

        def start() -> None:
            try:
                session.start()
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=start, daemon=True)
        worker.start()
        deadline = time.monotonic() + 1.0
        while not session._start_attempted and time.monotonic() < deadline:
            time.sleep(0.001)
        self.assertTrue(session._start_attempted)
        self.assertFalse(
            session.close(),
            "shutdown must report that the in-progress receiver has not unwound",
        )
        worker.join(timeout=1.0)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], HostConnectProxyError)
        self.assertTrue(session.close())
        sender_control.settimeout(1.0)
        self.assertEqual(sender_control.recv(64), b"")

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux SCM_RIGHTS")
    def test_session_close_preserves_interrupt_after_closing_control_fd(self) -> None:
        session_type = getattr(
            network_proxy_server, "LinuxHostConnectProxySession", None,
        )
        self.assertTrue(callable(session_type), "Linux handoff session is required")
        listener = self.make_listener()
        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        self.addCleanup(host_control.close)
        self.addCleanup(sender_control.close)
        nonce = bytes.fromhex("0011aa22bb33cc44dd55ee66ff778899")
        payload = b"ICODE_PROXY_LISTENER_V1" + nonce
        rights = array.array("i", [listener.fileno()])
        sender_control.sendmsg(
            [payload], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)],
        )
        session = session_type(
            host_control,
            expected_pid=os.getpid(),
            scope=self.scope,
            handoff_timeout_seconds=1.0,
            ready_timeout_seconds=1.0,
        )
        self.addCleanup(session.close)
        session.start()
        thread = session._thread
        self.assertIsNotNone(thread)
        assert thread is not None
        join = thread.join
        interrupts = 0

        def interrupt_once(*, timeout: float | None = None) -> None:
            nonlocal interrupts
            if interrupts == 0:
                interrupts += 1
                raise KeyboardInterrupt
            join(timeout=timeout)

        with patch.object(thread, "join", side_effect=interrupt_once):
            with self.assertRaises(KeyboardInterrupt):
                session.close()

        self.assertEqual(interrupts, 1)
        self.assertLess(host_control.fileno(), 0)
        self.assertTrue(session.close())

    @unittest.skipUnless(sys.platform.startswith("linux"), "requires Linux SCM_RIGHTS")
    def test_handoff_session_normalizes_unrepresentably_large_timeout(self) -> None:
        session_type = getattr(
            network_proxy_server, "LinuxHostConnectProxySession", None,
        )
        self.assertTrue(callable(session_type), "Linux handoff session is required")
        host_control, sender_control = (
            linux_proxy_handoff.create_loopback_listener_handoff_channel()
        )
        self.addCleanup(host_control.close)
        self.addCleanup(sender_control.close)

        try:
            session_type(
                host_control,
                expected_pid=os.getpid(),
                scope=self.scope,
                handoff_timeout_seconds=10**1000,
            )
        except HostConnectProxyError:
            return
        except OverflowError:
            self.fail("timeout validation must not leak numeric conversion errors")
        self.fail("unrepresentably large timeout was accepted")

    def test_upstream_failure_closes_without_sending_success_response(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        closed_listener = self.make_listener()
        closed_address = closed_listener.getsockname()
        closed_listener.close()
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        served: list[bool] = []

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=lambda hostname, port, resolver=None: self.local_resolver(
                hostname,
                port,
                closed_address,
            )(hostname, port),
        ):
            worker = threading.Thread(
                target=lambda: served.append(server.serve_once()),
                daemon=True,
            )
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(self.request())
            self.assertEqual(client.recv(1), b"")
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(served, [True])
        self.assertTrue(server.close())

    def test_malformed_connect_is_closed_without_resolving_or_sending_200(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        resolver_calls: list[bool] = []
        worker = threading.Thread(
            target=lambda: server.serve_once(
                resolver=lambda *_args, **_kwargs: resolver_calls.append(True),
            ),
            daemon=True,
        )
        worker.start()
        client.connect(listener.getsockname())
        client.sendall(
            b"CONNECT packages.example:80 HTTP/1.1\r\n"
            b"Host: packages.example\r\n\r\n"
        )
        self.assert_peer_closed(client)
        worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(resolver_calls, [])
        self.assertTrue(server.close())

    def test_incomplete_head_times_out_without_resolving(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(1.0)
        self.addCleanup(client.close)
        resolver_calls: list[bool] = []
        worker = threading.Thread(
            target=lambda: server.serve_once(
                resolver=lambda *_args, **_kwargs: resolver_calls.append(True),
            ),
            daemon=True,
        )
        with patch("icode.network_proxy_server._CONNECT_HEAD_TIMEOUT_SECONDS", 0.05):
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(b"CONNECT packages.")
            self.assert_peer_closed(client)
            worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(resolver_calls, [])
        self.assertTrue(server.close())

    def test_oversized_head_is_closed_without_resolving(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(1.0)
        self.addCleanup(client.close)
        resolver_calls: list[bool] = []
        worker = threading.Thread(
            target=lambda: server.serve_once(
                resolver=lambda *_args, **_kwargs: resolver_calls.append(True),
            ),
            daemon=True,
        )
        with patch("icode.network_proxy_server.MAX_CONNECT_REQUEST_HEAD_BYTES", 32):
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(b"A" * 33)
            self.assert_peer_closed(client)
            worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(resolver_calls, [])
        self.assertTrue(server.close())

    def test_listener_must_be_bound_to_ipv4_loopback(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("0.0.0.0", 0))
        listener.listen(1)
        try:
            with self.assertRaises(HostConnectProxyError):
                HostConnectProxyServer(listener, self.scope)
            self.assertGreaterEqual(listener.fileno(), 0)
        finally:
            listener.close()

    def test_server_rejects_blocking_listener_without_mutating_shared_flags(self) -> None:
        listener = self.make_listener()
        listener.settimeout(None)
        self.assertTrue(listener.getblocking())

        with self.assertRaises(HostConnectProxyError):
            HostConnectProxyServer(listener, self.scope)

        self.assertTrue(listener.getblocking())
        self.assertGreaterEqual(listener.fileno(), 0)

    def test_server_rejects_timeout_mode_listener_without_mutating_timeout(self) -> None:
        listener = self.make_listener()
        listener.settimeout(0.2)
        self.assertEqual(listener.gettimeout(), 0.2)

        with self.assertRaises(HostConnectProxyError):
            HostConnectProxyServer(listener, self.scope)

        self.assertEqual(listener.gettimeout(), 0.2)

    @unittest.skipIf(os.name == "nt", "SCM_RIGHTS/POSIX fd wrapper semantics")
    def test_server_accepts_received_nonblocking_fd_with_default_wrapper_mode(self) -> None:
        original_listener = self.make_listener()
        received_listener = socket.socket(fileno=os.dup(original_listener.fileno()))
        self.addCleanup(received_listener.close)
        original_listener.close()
        self.assertIsNone(received_listener.gettimeout())

        server = HostConnectProxyServer(received_listener, self.scope)
        self.addCleanup(server.close)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        client.connect(received_listener.getsockname())
        client.sendall(b"not a CONNECT request\r\n\r\n")

        self.assertTrue(server.serve_once())
        self.assert_peer_closed(client)
        self.assertTrue(server.close())

    def test_transient_accept_race_does_not_close_listener(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)

        with (
            patch(
                "icode.network_proxy_server.select.select",
                return_value=([listener], [], []),
            ),
            patch("socket.socket.accept", side_effect=BlockingIOError),
        ):
            self.assertFalse(server.serve_once())

        self.assertGreaterEqual(listener.fileno(), 0)
        self.assertTrue(server.close())

    def test_persistent_accept_resource_error_is_backed_off_and_close_wakes(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        accept_calls = 0

        def fail_accept(*_args: object, **_kwargs: object):
            nonlocal accept_calls
            accept_calls += 1
            raise OSError(errno.EMFILE, "too many open files")

        with (
            patch(
                "icode.network_proxy_server.select.select",
                return_value=([listener], [], []),
            ),
            patch("socket.socket.accept", side_effect=fail_accept),
        ):
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            time.sleep(0.35)
            server.close()
            worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertLessEqual(accept_calls, 6)
        self.assertTrue(server.close())

    def test_server_close_cancels_a_client_still_sending_its_header(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        served: list[bool] = []
        resolver_calls: list[bool] = []
        read_started = threading.Event()
        original_read = server._read_request_head

        def observe_read(client_socket: socket.socket) -> bytes:
            read_started.set()
            return original_read(client_socket)

        worker = threading.Thread(
            target=lambda: served.append(
                server.serve_once(
                    resolver=lambda *_args, **_kwargs: resolver_calls.append(True),
                )
            ),
            daemon=True,
        )
        with patch.object(server, "_read_request_head", side_effect=observe_read):
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(b"CONNECT packages.")
            self.assertTrue(read_started.wait(timeout=1.0))
            self.assertTrue(self.scope._accepted_clients)
            server.close()
            self.assert_peer_closed(client)
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(served, [True])
        self.assertEqual(resolver_calls, [])
        self.assertTrue(server.close())

    def test_revocation_closes_a_client_still_sending_its_header(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(0.5)
        self.addCleanup(client.close)
        served: list[bool] = []
        resolver_calls: list[bool] = []
        read_started = threading.Event()
        original_read = server._read_request_head

        def observe_read(client_socket: socket.socket) -> bytes:
            read_started.set()
            return original_read(client_socket)

        worker = threading.Thread(
            target=lambda: served.append(
                server.serve_once(
                    resolver=lambda *_args, **_kwargs: resolver_calls.append(True),
                )
            ),
            daemon=True,
        )
        with (
            patch.object(server, "_read_request_head", side_effect=observe_read),
            patch(
                "icode.network_proxy_server._CONNECT_HEAD_TIMEOUT_SECONDS",
                1.5,
            ),
        ):
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(b"CONNECT packages.")
            self.assertTrue(read_started.wait(timeout=1.0))
            self.authority.revoke(self.policy)
            self.assert_peer_closed(client)
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(served, [False])
        self.assertEqual(resolver_calls, [])
        self.assertTrue(server.close())

    def test_expiry_closes_a_client_still_sending_its_header(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(0.5)
        self.addCleanup(client.close)
        read_started = threading.Event()
        original_read = server._read_request_head
        fake_now = [self.issued.lease.issued_at_monotonic_ns + 1]

        def observe_read(client_socket: socket.socket) -> bytes:
            read_started.set()
            return original_read(client_socket)

        worker = threading.Thread(target=server.serve_once, daemon=True)
        with (
            patch.object(server, "_read_request_head", side_effect=observe_read),
            patch(
                "icode.network_proxy_scope.time.monotonic_ns",
                side_effect=lambda: fake_now[0],
            ),
        ):
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(b"CONNECT packages.")
            self.assertTrue(read_started.wait(timeout=1.0))
            self.assertTrue(self.scope._accepted_clients)
            fake_now[0] = self.issued.lease.expires_at_monotonic_ns
            self.assert_peer_closed(client)
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertLess(listener.fileno(), 0)
        self.assertTrue(server.close())

    def test_scope_close_closes_a_client_before_header_authorization(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(0.5)
        self.addCleanup(client.close)
        read_started = threading.Event()
        original_read = server._read_request_head

        def observe_read(client_socket: socket.socket) -> bytes:
            read_started.set()
            return original_read(client_socket)

        worker = threading.Thread(target=server.serve_once, daemon=True)
        with patch.object(server, "_read_request_head", side_effect=observe_read):
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(b"CONNECT packages.")
            self.assertTrue(read_started.wait(timeout=1.0))
            self.assertTrue(self.scope._accepted_clients)
            self.scope.close()
            self.assert_peer_closed(client)
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertTrue(self.scope.close())
        self.assertTrue(server.close())

    def test_revoked_idle_scope_closes_its_listener(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        self.authority.revoke(self.policy)

        self.assertFalse(server.serve_once())
        self.assertLess(listener.fileno(), 0)
        self.assertTrue(server.close())

    def test_revoke_after_upstream_connect_closes_before_200_and_listener(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        upstream_listener = self.make_listener()
        upstream_listener.settimeout(2.0)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        served: list[bool] = []
        original_open = self.scope.open_connect

        def open_then_revoke(*args: object, **kwargs: object):
            tunnel = original_open(*args, **kwargs)
            self.authority.revoke(self.policy)
            return tunnel

        with (
            patch.object(self.scope, "open_connect", side_effect=open_then_revoke),
            patch(
                "icode.network_connector.resolve_public_tcp_targets",
                side_effect=lambda hostname, port, resolver=None: self.local_resolver(
                    hostname,
                    port,
                    upstream_listener.getsockname(),
                )(hostname, port),
            ),
        ):
            worker = threading.Thread(
                target=lambda: served.append(server.serve_once()),
                daemon=True,
            )
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(self.request())
            self.assert_peer_closed(client)
            upstream_peer, _address = upstream_listener.accept()
            upstream_peer.settimeout(2.0)
            self.addCleanup(upstream_peer.close)
            self.assertEqual(upstream_peer.recv(1), b"")
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(served, [False])
        self.assertLess(listener.fileno(), 0)
        self.assertTrue(server.close())

    def test_active_revoke_closes_relay_peers_and_listener(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        upstream_listener = self.make_listener()
        upstream_listener.settimeout(2.0)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        served: list[bool] = []

        with patch(
            "icode.network_connector.resolve_public_tcp_targets",
            side_effect=lambda hostname, port, resolver=None: self.local_resolver(
                hostname,
                port,
                upstream_listener.getsockname(),
            )(hostname, port),
        ):
            worker = threading.Thread(
                target=lambda: served.append(server.serve_once()),
                daemon=True,
            )
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(self.request())
            response = bytearray()
            while not response.endswith(b"\r\n\r\n"):
                response.extend(client.recv(1))
            self.assertEqual(
                bytes(response),
                b"HTTP/1.1 200 Connection Established\r\n\r\n",
            )
            upstream_peer, _address = upstream_listener.accept()
            upstream_peer.settimeout(2.0)
            self.addCleanup(upstream_peer.close)
            client.sendall(b"before-revoke")
            self.assertEqual(upstream_peer.recv(13), b"before-revoke")
            upstream_peer.sendall(b"still-authorized")
            self.assertEqual(client.recv(16), b"still-authorized")

            self.authority.revoke(self.policy)
            self.assert_peer_closed(client)
            self.assert_peer_closed(upstream_peer)
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(served, [True])
        self.assertLess(listener.fileno(), 0)
        self.assertTrue(server.close())

    def test_expiry_monitor_failure_closes_an_active_relay(self) -> None:
        listener = self.make_listener()
        server = self.make_server(listener)
        upstream_listener = self.make_listener()
        upstream_listener.settimeout(2.0)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2.0)
        self.addCleanup(client.close)
        served: list[bool] = []
        fail_sweeps = threading.Event()
        original_close_expired = self.authority.close_expired_connections

        def close_expired(now_monotonic_ns: int) -> int:
            if fail_sweeps.is_set():
                raise RuntimeError("injected monitor failure")
            return original_close_expired(now_monotonic_ns)

        with (
            patch.object(
                self.authority,
                "close_expired_connections",
                side_effect=close_expired,
            ),
            patch(
                "icode.network_connector.resolve_public_tcp_targets",
                side_effect=lambda hostname, port, resolver=None: self.local_resolver(
                    hostname,
                    port,
                    upstream_listener.getsockname(),
                )(hostname, port),
            ),
        ):
            worker = threading.Thread(
                target=lambda: served.append(server.serve_once()),
                daemon=True,
            )
            worker.start()
            client.connect(listener.getsockname())
            client.sendall(self.request())
            response = bytearray()
            while not response.endswith(b"\r\n\r\n"):
                response.extend(client.recv(1))
            upstream_peer, _address = upstream_listener.accept()
            upstream_peer.settimeout(2.0)
            self.addCleanup(upstream_peer.close)
            fail_sweeps.set()

            deadline = time.monotonic() + 1.0
            while self.runtime._monitor.failure_count == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreater(self.runtime._monitor.failure_count, 0)
            self.assert_peer_closed(client)
            self.assert_peer_closed(upstream_peer)
            worker.join(timeout=2.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(served, [False])
        self.assertLess(listener.fileno(), 0)
        self.assertTrue(server.close())


if __name__ == "__main__":
    unittest.main()
