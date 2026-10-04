"""Test-only native probe for path-scoped macOS AF_UNIX policy."""

from __future__ import annotations

import errno
import os
import platform
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from typing import Callable
from unittest.mock import patch

from tests import _support  # noqa: F401  # Add the repository's src/ to sys.path.
from tests import macos_unix_socket_probe as probe
from icode.approvals import ScriptedApprover
from icode.isolation import MacSeatbeltSandbox
from icode.network_destination import ResolvedNetworkTarget
from icode.network_lease import NetworkLeaseAuthority, NetworkPurpose
from icode.network_proxy_scope import HostConnectRuntime, HostHttpsConnectScope
from icode.network_proxy_server import HostUnixSocks5ProxyServer
from icode.sandbox_policy import NetworkMode, SandboxPolicy


class TestUpstreamAcceptFixture(unittest.TestCase):
    def test_accept_fixture_keeps_waiting_after_poll_timeout(self) -> None:
        accept_connection = getattr(probe, "accept_connection_until_stopped", None)
        self.assertTrue(
            callable(accept_connection),
            "live-lease upstream fixture needs a stop-aware accept loop",
        )

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        stop_event = threading.Event()
        accepted_payloads: list[bytes] = []

        def accept_once() -> None:
            connection = accept_connection(listener, stop_event)
            if connection is None:
                return
            with connection:
                accepted_payloads.append(connection.recv(1))

        worker = threading.Thread(target=accept_once, daemon=True)
        worker.start()
        try:
            worker.join(timeout=0.35)
            self.assertTrue(
                worker.is_alive(),
                "one accept polling timeout must not end the upstream fixture",
            )
            with socket.create_connection(listener.getsockname(), timeout=1.0) as client:
                client.sendall(b"x")
            worker.join(timeout=1.0)
            self.assertFalse(worker.is_alive(), "upstream fixture did not accept the canary")
            self.assertEqual(accepted_payloads, [b"x"])
        finally:
            stop_event.set()
            worker.join(timeout=1.0)
            listener.close()


@unittest.skipUnless(
    os.name == "posix" and hasattr(socket, "AF_UNIX"),
    "requires POSIX Unix-domain socket descriptors",
)
class TestInheritedUnixSocketFdRunner(unittest.TestCase):
    def test_preconnected_fd_probe_notice_has_only_bounded_status_fields(self) -> None:
        formatter = getattr(probe, "format_preconnected_fd_probe_notice", None)
        self.assertTrue(
            callable(formatter),
            "fixed-field native probe notice formatter is missing",
        )
        self.assertEqual(
            formatter(
                stage="observed",
                exit_code=0,
                marker_count=1,
                fd_status="roundtrip",
                tcp_socket_status="denied",
                unix_socket_status="denied",
            ),
            "::notice::macos-seatbelt-preconnected-uds-fd stage=observed "
            "exit_code=0 marker_count=1 preconnected_fd=roundtrip "
            "new_tcp_socket=denied new_unix_socket=denied "
            "conformance_credit=none",
        )
        with self.assertRaises(ValueError):
            formatter(
                stage="observed",
                exit_code=0,
                marker_count=1,
                fd_status="roundtrip ::error::forged",
                tcp_socket_status="denied",
                unix_socket_status="denied",
            )

    def test_child_can_roundtrip_over_an_explicitly_inherited_connected_fd(self) -> None:
        runner = getattr(probe, "run_with_inherited_fds", None)
        self.assertTrue(
            callable(runner),
            "bounded subprocess helper for explicitly inherited descriptors is missing",
        )

        host_connection, worker_connection = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_STREAM,
        )
        host_connection.settimeout(3.0)
        replies: list[bytes] = []
        failures: list[str] = []

        def respond_once() -> None:
            try:
                request = host_connection.recv(64)
                replies.append(request)
                if request == b"host-fd-request":
                    host_connection.sendall(b"host-fd-reply")
            except OSError as error:
                failures.append(type(error).__name__)

        responder = threading.Thread(target=respond_once, daemon=True)
        responder.start()
        source = (
            "import socket, sys\n"
            "connection = socket.socket(fileno=int(sys.argv[1]))\n"
            "connection.settimeout(2.0)\n"
            "try:\n"
            "    connection.sendall(b'host-fd-request')\n"
            "    reply = connection.recv(64)\n"
            "    print('probe:roundtrip' if reply == b'host-fd-reply' else 'probe:bad-reply')\n"
            "finally:\n"
            "    connection.close()\n"
        )
        try:
            result = runner(
                [sys.executable, "-S", "-c", source, str(worker_connection.fileno())],
                pass_fds=(worker_connection.fileno(),),
                cwd=Path.cwd(),
                timeout_seconds=5.0,
            )
        finally:
            worker_connection.close()
            responder.join(timeout=3.0)
            host_connection.close()

        self.assertFalse(responder.is_alive(), "host-side FD fixture did not finish")
        self.assertEqual(failures, [])
        self.assertEqual(replies, [b"host-fd-request"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "probe:roundtrip")


class TestUnixSocketPolicyBuilder(unittest.TestCase):
    def test_curl_socks5_uds_support_requires_version_and_build_feature(self) -> None:
        supports = getattr(probe, "supports_curl_socks5_uds", None)
        self.assertTrue(callable(supports), "curl SOCKS-over-UDS capability check is missing")

        self.assertTrue(supports(
            "curl 7.84.0 (x86_64-apple-darwin)\n"
            "Features: HTTPS-proxy UnixSockets\n",
        ))
        self.assertFalse(supports(
            "curl 7.83.1 (x86_64-apple-darwin)\n"
            "Features: HTTPS-proxy UnixSockets\n",
        ))
        self.assertFalse(supports(
            "curl 8.0.0 (x86_64-apple-darwin)\n"
            "Features: HTTPS-proxy\n",
        ))
        self.assertFalse(supports("not a curl version report\n"))

    def test_curl_socks5_uds_proxy_url_quotes_and_bounds_socket_path(self) -> None:
        build_url = getattr(probe, "curl_socks5_uds_proxy_url", None)
        self.assertTrue(callable(build_url), "curl SOCKS-over-UDS URL builder is missing")
        self.assertEqual(
            build_url(Path("/private/tmp/proxy root.sock")),
            "socks5h://localhost/private/tmp/proxy%20root.sock",
        )
        for invalid_path in (
            Path("relative/proxy.sock"),
            Path("/private/../tmp/proxy.sock"),
            Path("/private/tmp/proxy\n.sock"),
            Path("/" + "a" * 104),
        ):
            with self.subTest(path=str(invalid_path)):
                with self.assertRaises(ValueError):
                    build_url(invalid_path)

@unittest.skipUnless(hasattr(socket, "AF_UNIX"), "requires AF_UNIX sockets")
class TestSocks5LeaseConnectBridge(unittest.TestCase):
    @staticmethod
    def _recv_exact(connection: socket.socket, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            chunk = connection.recv(size - len(result))
            if not chunk:
                raise AssertionError("bridge closed a short SOCKS5 reply")
            result.extend(chunk)
        return bytes(result)

    def _request(
        self,
        socket_path: Path,
        request: bytes,
        *,
        client_payload: bytes = b"",
        fragmented: bool = False,
    ) -> tuple[int, bytes]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(str(socket_path))
            client.sendall(b"\x05\x01\x00")
            self.assertEqual(self._recv_exact(client, 2), b"\x05\x00")
            if fragmented:
                for byte in request:
                    client.sendall(bytes((byte,)))
                    time.sleep(0.001)
            else:
                client.sendall(request)
            reply = self._recv_exact(client, 10)
            self.assertEqual(reply[0], 5)
            self.assertEqual(reply[2], 0)
            self.assertEqual(reply[3], 1)
            result = reply[1]
            if result != 0:
                return result, b""
            if client_payload:
                client.sendall(client_payload)
                client.shutdown(socket.SHUT_WR)
            response = bytearray()
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
            return result, bytes(response)

    def test_invalid_socks_targets_do_not_open_internal_proxy_connection(self) -> None:
        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(
            callable(bridge_type),
            "a test-only lease CONNECT SOCKS5 UDS bridge is missing",
        )
        with tempfile.TemporaryDirectory(prefix="icode-socks5-lease-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            proxy_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_listener.bind(("127.0.0.1", 0))
            proxy_listener.listen(2)
            proxy_listener.settimeout(0.2)
            try:
                with bridge_type(
                    socket_path,
                    proxy_listener.getsockname(),
                    lease_check=lambda: None,
                ) as bridge:
                    raw_ip_request = (
                        b"\x05\x01\x00\x01\x7f\x00\x00\x01\x01\xbb"
                    )
                    non_https_request = (
                        b"\x05\x01\x00\x03\x10packages.example\x20\xfb"
                    )
                    unsupported_command = (
                        b"\x05\x02\x00\x03\x10packages.example\x01\xbb"
                    )
                    self.assertEqual(
                        self._request(socket_path, raw_ip_request)[0],
                        8,
                        "raw-IP SOCKS requests must be rejected",
                    )
                    self.assertEqual(
                        self._request(socket_path, non_https_request)[0],
                        2,
                        "non-443 SOCKS requests must be rejected",
                    )
                    self.assertEqual(
                        self._request(socket_path, unsupported_command)[0],
                        7,
                        "non-CONNECT SOCKS commands must be rejected",
                    )
                    self.assertEqual(bridge.failures, [])
                with self.assertRaises(socket.timeout):
                    proxy_listener.accept()
            finally:
                proxy_listener.close()

    def test_valid_domain_request_waits_for_connect_then_relays_full_duplex(self) -> None:
        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(
            callable(bridge_type),
            "a test-only lease CONNECT SOCKS5 UDS bridge is missing",
        )
        with tempfile.TemporaryDirectory(prefix="icode-socks5-lease-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            proxy_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_listener.bind(("127.0.0.1", 0))
            proxy_listener.listen(1)
            proxy_listener.settimeout(3)
            connect_heads: list[bytes] = []
            proxy_payloads: list[bytes] = []
            proxy_failures: list[str] = []

            def serve_proxy_once() -> None:
                try:
                    peer, _address = proxy_listener.accept()
                    with peer:
                        peer.settimeout(3)
                        request_head = bytearray()
                        while not request_head.endswith(b"\r\n\r\n"):
                            chunk = peer.recv(1)
                            if not chunk:
                                raise AssertionError("bridge sent a short CONNECT request")
                            request_head.extend(chunk)
                            if len(request_head) > 4096:
                                raise AssertionError("bridge CONNECT request was unbounded")
                        connect_heads.append(bytes(request_head))
                        peer.sendall(
                            b"HTTP/1.1 200 Connection Established\r\n\r\n"
                        )
                        incoming = bytearray()
                        while True:
                            chunk = peer.recv(4096)
                            if not chunk:
                                break
                            incoming.extend(chunk)
                        proxy_payloads.append(bytes(incoming))
                        peer.sendall(b"upstream-through-connect")
                        peer.shutdown(socket.SHUT_WR)
                except BaseException as error:
                    proxy_failures.append(type(error).__name__)

            proxy_worker = threading.Thread(
                target=serve_proxy_once,
                name="icode-socks5-test-proxy",
                daemon=True,
            )
            proxy_worker.start()
            try:
                with bridge_type(
                    socket_path,
                    proxy_listener.getsockname(),
                    lease_check=lambda: None,
                ) as bridge:
                    request = (
                        b"\x05\x01\x00\x03\x10packages.example\x01\xbb"
                    )
                    result, response = self._request(
                        socket_path,
                        request,
                        client_payload=b"client-through-socks-uds",
                        fragmented=True,
                    )
                    self.assertEqual(result, 0)
                    self.assertEqual(response, b"upstream-through-connect")
                    self.assertEqual(bridge.failures, [])
                self.assertFalse(socket_path.exists())
            finally:
                proxy_listener.close()
                proxy_worker.join(timeout=3)
            self.assertFalse(proxy_worker.is_alive())
            self.assertEqual(proxy_failures, [])
            self.assertEqual(
                connect_heads,
                [
                    b"CONNECT packages.example:443 HTTP/1.1\r\n"
                    b"Host: packages.example\r\n\r\n"
                ],
            )
            self.assertEqual(proxy_payloads, [b"client-through-socks-uds"])

    def test_expired_lease_is_rejected_before_internal_proxy_connect(self) -> None:
        from icode.network_lease import NetworkLeaseValidationError

        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        with tempfile.TemporaryDirectory(prefix="icode-socks5-expired-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            proxy_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_listener.bind(("127.0.0.1", 0))
            proxy_listener.listen(1)
            proxy_listener.settimeout(0.2)

            def reject_lease() -> None:
                raise NetworkLeaseValidationError("test lease expired")

            try:
                with bridge_type(
                    socket_path,
                    proxy_listener.getsockname(),
                    lease_check=reject_lease,
                ):
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.settimeout(1.0)
                        client.connect(str(socket_path))
                        self.assertEqual(
                            client.recv(1),
                            b"",
                            "an expired lease must close before SOCKS success",
                        )
                with self.assertRaises(socket.timeout):
                    proxy_listener.accept()
            finally:
                proxy_listener.close()

    def test_internal_connect_failure_returns_socks_failure_without_success(self) -> None:
        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        with tempfile.TemporaryDirectory(prefix="icode-socks5-refused-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            refused_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            refused_listener.bind(("127.0.0.1", 0))
            proxy_address = refused_listener.getsockname()
            refused_listener.close()

            with bridge_type(
                socket_path,
                proxy_address,
                lease_check=lambda: None,
            ):
                request = b"\x05\x01\x00\x03\x10packages.example\x01\xbb"
                result, _response = self._request(socket_path, request)
                self.assertEqual(result, 1, "connect failures use SOCKS general failure")

    def test_lease_revoke_during_connect_response_returns_policy_failure(self) -> None:
        from icode.network_lease import NetworkLeaseValidationError

        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        with tempfile.TemporaryDirectory(prefix="icode-socks5-response-revoke-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            proxy_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_listener.bind(("127.0.0.1", 0))
            proxy_listener.listen(1)
            response_started = threading.Event()
            proxy_closed = threading.Event()
            revoked = threading.Event()
            proxy_failures: list[str] = []
            client_results: list[tuple[int, bytes]] = []
            client_errors: list[BaseException] = []

            def lease_check() -> None:
                if revoked.is_set():
                    raise NetworkLeaseValidationError("test lease revoked")

            def serve_proxy_once() -> None:
                try:
                    peer, _address = proxy_listener.accept()
                    with peer:
                        peer.settimeout(2)
                        request_head = bytearray()
                        while not request_head.endswith(b"\r\n\r\n"):
                            chunk = peer.recv(1)
                            if not chunk:
                                raise AssertionError("bridge sent a short CONNECT request")
                            request_head.extend(chunk)
                        peer.sendall(b"H")
                        response_started.set()
                        while peer.recv(4096):
                            pass
                        proxy_closed.set()
                except BaseException as error:
                    proxy_failures.append(type(error).__name__)

            proxy_worker = threading.Thread(
                target=serve_proxy_once,
                name="icode-socks5-revoke-response-proxy",
                daemon=True,
            )
            proxy_worker.start()

            def request_from_client() -> None:
                try:
                    client_results.append(self._request(
                        socket_path,
                        b"\x05\x01\x00\x03\x10packages.example\x01\xbb",
                    ))
                except BaseException as error:
                    client_errors.append(error)

            client_worker = threading.Thread(
                target=request_from_client,
                name="icode-socks5-revoke-response-client",
                daemon=True,
            )
            try:
                with patch.object(probe, "_BRIDGE_CONNECT_TIMEOUT_SECONDS", 0.7):
                    with bridge_type(
                        socket_path,
                        proxy_listener.getsockname(),
                        lease_check=lease_check,
                    ) as bridge:
                        client_worker.start()
                        self.assertTrue(response_started.wait(2))
                        revoke_started = time.monotonic()
                        revoked.set()
                        client_worker.join(timeout=0.5)
                        self.assertFalse(
                            client_worker.is_alive(),
                            "lease revocation must interrupt a partial CONNECT response",
                        )
                        self.assertEqual(client_errors, [])
                        self.assertEqual(client_results, [(2, b"")])
                        self.assertLess(time.monotonic() - revoke_started, 0.5)
                    self.assertEqual(bridge.failures, [])
                self.assertTrue(proxy_closed.wait(1))
            finally:
                revoked.set()
                proxy_listener.close()
                if client_worker.ident is not None:
                    client_worker.join(timeout=2)
                proxy_worker.join(timeout=2)
            self.assertFalse(client_worker.is_alive())
            self.assertFalse(proxy_worker.is_alive())
            self.assertEqual(proxy_failures, [])

    def test_slow_connect_response_uses_one_absolute_deadline(self) -> None:
        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        with tempfile.TemporaryDirectory(prefix="icode-socks5-response-deadline-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            proxy_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_listener.bind(("127.0.0.1", 0))
            proxy_listener.listen(1)
            second_fragment_sent = threading.Event()
            proxy_closed = threading.Event()
            proxy_failures: list[str] = []
            client_results: list[tuple[int, bytes]] = []
            client_errors: list[BaseException] = []

            def serve_proxy_once() -> None:
                try:
                    peer, _address = proxy_listener.accept()
                    with peer:
                        peer.settimeout(2)
                        request_head = bytearray()
                        while not request_head.endswith(b"\r\n\r\n"):
                            chunk = peer.recv(1)
                            if not chunk:
                                raise AssertionError("bridge sent a short CONNECT request")
                            request_head.extend(chunk)
                        peer.sendall(b"H")
                        time.sleep(0.45)
                        peer.sendall(b"T")
                        second_fragment_sent.set()
                        while peer.recv(4096):
                            pass
                        proxy_closed.set()
                except BaseException as error:
                    proxy_failures.append(type(error).__name__)

            proxy_worker = threading.Thread(
                target=serve_proxy_once,
                name="icode-socks5-slow-response-proxy",
                daemon=True,
            )
            proxy_worker.start()

            def request_from_client() -> None:
                try:
                    client_results.append(self._request(
                        socket_path,
                        b"\x05\x01\x00\x03\x10packages.example\x01\xbb",
                    ))
                except BaseException as error:
                    client_errors.append(error)

            client_worker = threading.Thread(
                target=request_from_client,
                name="icode-socks5-slow-response-client",
                daemon=True,
            )
            try:
                with patch.object(probe, "_BRIDGE_CONNECT_TIMEOUT_SECONDS", 0.75):
                    with bridge_type(
                        socket_path,
                        proxy_listener.getsockname(),
                        lease_check=lambda: None,
                    ) as bridge:
                        client_worker.start()
                        self.assertTrue(second_fragment_sent.wait(2))
                        deadline_remaining_started = time.monotonic()
                        client_worker.join(timeout=0.5)
                        self.assertFalse(
                            client_worker.is_alive(),
                            "a later response byte must not reset the CONNECT deadline",
                        )
                        self.assertEqual(client_errors, [])
                        self.assertEqual(client_results, [(1, b"")])
                        self.assertLess(
                            time.monotonic() - deadline_remaining_started,
                            0.5,
                        )
                    self.assertEqual(bridge.failures, [])
                self.assertTrue(proxy_closed.wait(1))
            finally:
                proxy_listener.close()
                if client_worker.ident is not None:
                    client_worker.join(timeout=2)
                proxy_worker.join(timeout=2)
            self.assertFalse(client_worker.is_alive())
            self.assertFalse(proxy_worker.is_alive())
            self.assertEqual(proxy_failures, [])

    def test_revoked_lease_is_checked_when_connect_response_eof_arrives(self) -> None:
        from icode.network_lease import NetworkLeaseValidationError

        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        reader, writer = socket.socketpair()
        writer.close()

        def reject_lease() -> None:
            raise NetworkLeaseValidationError("test lease revoked before EOF")

        try:
            with self.assertRaises(NetworkLeaseValidationError):
                bridge_type._read_connect_response(
                    reader,
                    deadline=time.monotonic() + 1.0,
                    lease_check=reject_lease,
                )
        finally:
            reader.close()

    def test_lease_revoke_during_partial_request_closes_without_proxy_connect(self) -> None:
        from icode.network_lease import NetworkLeaseValidationError

        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        with tempfile.TemporaryDirectory(prefix="icode-socks5-partial-revoke-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            proxy_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_listener.bind(("127.0.0.1", 0))
            proxy_listener.listen(1)
            proxy_listener.settimeout(0.25)
            revoked = threading.Event()

            def lease_check() -> None:
                if revoked.is_set():
                    raise NetworkLeaseValidationError("test lease revoked")

            try:
                with bridge_type(
                    socket_path,
                    proxy_listener.getsockname(),
                    lease_check=lease_check,
                ) as bridge:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.settimeout(1.0)
                        client.connect(str(socket_path))
                        client.sendall(b"\x05\x01\x00")
                        self.assertEqual(self._recv_exact(client, 2), b"\x05\x00")
                        client.sendall(b"\x05")
                        revoked.set()
                        self.assertEqual(
                            self._recv_exact(client, 10)[1],
                            2,
                            "revocation must reject a partial SOCKS request",
                        )
                        self.assertEqual(client.recv(1), b"")
                    self.assertEqual(bridge.failures, [])
                with self.assertRaises(socket.timeout):
                    proxy_listener.accept()
            finally:
                proxy_listener.close()

    def test_slow_partial_request_is_bound_by_an_absolute_handshake_deadline(self) -> None:
        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        with tempfile.TemporaryDirectory(prefix="icode-socks5-deadline-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            deadline_seconds = 0.6
            with patch.object(
                probe, "_BRIDGE_CLIENT_TIMEOUT_SECONDS", deadline_seconds,
            ):
                with bridge_type(
                    socket_path,
                    ("127.0.0.1", 9),
                    lease_check=lambda: None,
                ):
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.settimeout(1.0)
                        request_started_at = time.monotonic()
                        client.connect(str(socket_path))
                        client.sendall(b"\x05\x01\x00")
                        self.assertEqual(self._recv_exact(client, 2), b"\x05\x00")
                        client.sendall(b"\x05")
                        time.sleep(0.45)
                        second_byte_sent = probe.send_if_peer_open(client, b"\x01")
                        if second_byte_sent:
                            partial_elapsed = time.monotonic()
                            try:
                                response = client.recv(1)
                            except (
                                BrokenPipeError,
                                ConnectionResetError,
                                ConnectionAbortedError,
                            ):
                                response = b""
                            self.assertEqual(response, b"")
                            self.assertLess(
                                time.monotonic() - partial_elapsed,
                                0.4,
                                "each received byte must not reset the handshake deadline",
                            )
                        self.assertGreaterEqual(
                            time.monotonic() - request_started_at,
                            deadline_seconds,
                            "the bridge must not close before its absolute deadline",
                        )

    def test_delayed_probe_write_recognizes_only_peer_closed_errors(self) -> None:
        send_if_peer_open = getattr(probe, "send_if_peer_open", None)
        self.assertTrue(callable(send_if_peer_open), "peer-close probe helper is missing")

        class FakeConnection:
            def __init__(self, error: OSError | None) -> None:
                self.error = error

            def sendall(self, _payload: bytes) -> None:
                if self.error is not None:
                    raise self.error

        for error in (
            BrokenPipeError(errno.EPIPE, "closed peer"),
            ConnectionResetError(errno.ECONNRESET, "reset peer"),
            ConnectionAbortedError(errno.ECONNABORTED, "aborted peer"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertFalse(send_if_peer_open(FakeConnection(error), b"x"))

        with self.assertRaisesRegex(OSError, "unrelated send failure"):
            send_if_peer_open(
                FakeConnection(OSError(errno.EIO, "unrelated send failure")),
                b"x",
            )

    def test_close_cancels_partial_handshake_and_removes_owned_socket(self) -> None:
        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        with tempfile.TemporaryDirectory(prefix="icode-socks5-close-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            bridge = bridge_type(
                socket_path,
                ("127.0.0.1", 9),
                lease_check=lambda: None,
            )
            bridge.__enter__()
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(2)
            try:
                client.connect(str(socket_path))
                client.sendall(b"\x05\x01")
                self.assertTrue(bridge.close())
                try:
                    self.assertEqual(client.recv(1), b"")
                except OSError:
                    pass
                self.assertFalse(socket_path.exists())
            finally:
                client.close()
                bridge.close()

    def test_close_does_not_unlink_a_replaced_socket_path(self) -> None:
        bridge_type = getattr(probe, "Socks5UdsLeaseConnectBridge", None)
        self.assertTrue(callable(bridge_type), "the test-only bridge is missing")
        with tempfile.TemporaryDirectory(prefix="icode-socks5-replace-") as raw_root:
            socket_path = Path(raw_root) / "bridge.sock"
            bridge = bridge_type(
                socket_path,
                ("127.0.0.1", 9),
                lease_check=lambda: None,
            )
            bridge.__enter__()
            socket_path.unlink()
            socket_path.write_text("replacement belongs to the test", encoding="utf-8")
            self.assertFalse(bridge.close())
            self.assertEqual(
                socket_path.read_text(encoding="utf-8"),
                "replacement belongs to the test",
            )


class TestUnixSocketCanaryAndProfile(unittest.TestCase):
    @staticmethod
    def _recv_exact(client: socket.socket, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            chunk = client.recv(size - len(result))
            if not chunk:
                raise AssertionError("test canary closed a short SOCKS5 reply")
            result.extend(chunk)
        return bytes(result)

    @staticmethod
    def _socks5_canary_request(
        socket_path: Path, hostname: str, port: int,
    ) -> tuple[int, bytes]:
        domain = hostname.encode("ascii")
        request = (
            b"\x05\x01\x00\x03" + bytes((len(domain),)) + domain
            + port.to_bytes(2, "big")
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(socket_path))
            client.sendall(b"\x05\x01\x00")
            if TestUnixSocketCanaryAndProfile._recv_exact(client, 2) != b"\x05\x00":
                raise AssertionError("test canary rejected no-auth SOCKS5 negotiation")
            client.sendall(request)
            reply_head = TestUnixSocketCanaryAndProfile._recv_exact(client, 4)
            if reply_head[0] != 5 or reply_head[2] != 0:
                raise AssertionError("test canary returned a malformed SOCKS5 reply")
            address_length = {1: 4, 4: 16}.get(reply_head[3])
            if reply_head[3] == 3:
                address_length_byte = TestUnixSocketCanaryAndProfile._recv_exact(client, 1)
                address_length = address_length_byte[0]
            if address_length is None:
                raise AssertionError("test canary returned an unknown SOCKS5 address type")
            remaining = address_length + 2
            TestUnixSocketCanaryAndProfile._recv_exact(client, remaining)
            if reply_head[1] != 0:
                return reply_head[1], b""

            client.sendall(
                b"GET /canary HTTP/1.1\r\nHost: approved.example\r\n"
                b"Connection: close\r\n\r\n"
            )
            response = bytearray()
            while len(response) <= 4096:
                chunk = client.recv(min(512, 4097 - len(response)))
                if not chunk:
                    break
                response.extend(chunk)
            return reply_head[1], bytes(response)

    def test_test_only_socks5_uds_canary_allows_only_approved_domain(self) -> None:
        canary_type = getattr(probe, "Socks5UdsCanary", None)
        self.assertTrue(callable(canary_type), "test-only SOCKS5 UDS canary is missing")

        with tempfile.TemporaryDirectory(prefix="icode-socks5-uds-") as raw_root:
            socket_path = Path(raw_root) / "proxy.sock"
            with canary_type(
                socket_path,
                approved_target=("approved.example", 45678),
                blocked_target=("blocked.example", 45678),
            ) as canary:
                approved_reply = self._socks5_canary_request(
                    socket_path, "approved.example", 45678,
                )
                blocked_reply = self._socks5_canary_request(
                    socket_path, "blocked.example", 45678,
                )

            self.assertEqual(approved_reply[0], 0)
            self.assertIn(b"icode-socks5-uds-canary", approved_reply[1])
            self.assertEqual(blocked_reply[0], 2)
            self.assertEqual(blocked_reply[1], b"")
            self.assertEqual(
                canary.observed_targets,
                [("approved.example", 45678), ("blocked.example", 45678)],
            )

    def test_policy_grants_only_outbound_unix_socket_beneath_approved_root(self) -> None:
        builder = getattr(probe, "build_test_profile", None)
        self.assertTrue(callable(builder), "test-only Seatbelt profile builder is missing")

        base = "(version 1)(deny default)"
        approved = Path("/private/tmp/approved sockets")
        profile = builder(base, approved)

        self.assertTrue(profile.startswith(base))
        self.assertIn(
            '(allow file-read-metadata file-test-existence '
            '(subpath "/private/tmp/approved sockets"))',
            profile,
        )
        self.assertIn("(allow system-socket (socket-domain AF_UNIX))", profile)
        self.assertIn(
            '(allow network-outbound (remote unix-socket '
            '(subpath "/private/tmp/approved sockets")))',
            profile,
        )
        self.assertNotIn("network-bind", profile)
        self.assertNotIn('(allow network*)', profile)
        self.assertNotIn('(allow network-outbound (remote ip', profile)

    def test_policy_builder_rejects_relative_and_control_character_paths(self) -> None:
        builder = getattr(probe, "build_test_profile", None)
        self.assertTrue(callable(builder), "test-only Seatbelt profile builder is missing")

        with self.assertRaises(ValueError):
            builder("(version 1)(deny default)", Path("relative/socket-root"))
        with self.assertRaises(ValueError):
            builder("(version 1)(deny default)", Path("/private/tmp/bad\nroot"))

    def test_policy_builder_quotes_sbpl_path_literals(self) -> None:
        builder = getattr(probe, "build_test_profile", None)
        self.assertTrue(callable(builder), "test-only Seatbelt profile builder is missing")

        profile = builder(
            "(version 1)(deny default)",
            Path('/private/tmp/a "quoted" root'),
        )
        self.assertIn('/private/tmp/a \\"quoted\\" root', profile)


class TestLiveLeaseTestProxyFactory(unittest.TestCase):
    def test_factory_creates_the_listener_it_hands_to_the_proxy_server(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-live-proxy-factory-") as raw:
            workspace = Path(raw) / "workspace"
            workspace.mkdir()
            policy = SandboxPolicy(
                schema_version=1,
                run_id="run-live-proxy-factory-test",
                ticket_id="ICODE-LIVE-PROXY-FACTORY-TEST",
                step="code",
                workspace_root=workspace,
                read_roots=(workspace,),
                write_roots=(workspace,),
                deny_read_roots=(workspace / ".git",),
                deny_write_roots=(workspace / ".git",),
                network_mode=NetworkMode.DENY,
                allowed_domains=(),
                process_limit=2,
                wall_timeout_seconds=10,
                output_limit_bytes=1024,
                protected_paths=(workspace / ".git",),
            )
            authority = NetworkLeaseAuthority()
            issued = authority.request_lease(
                policy,
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("packages.example",),
                ttl_seconds=30,
            )
            runtime = HostConnectRuntime(authority, sweep_interval_seconds=0.01)
            runtime.start()
            try:
                scope = runtime.create_scope(
                    issued,
                    policy,
                    NetworkPurpose.PACKAGE_INSTALL,
                )
                factory = getattr(probe, "create_test_lease_proxy_server", None)
                self.assertTrue(
                    callable(factory),
                    "test-only owned listener factory is missing",
                )
                listener, server = factory(scope)
                try:
                    self.assertIs(type(listener), socket.socket)
                    self.assertIs(server._listener, listener)
                    self.assertEqual(listener.getsockname()[0], "127.0.0.1")
                    self.assertGreater(listener.getsockname()[1], 0)
                    self.assertEqual(listener.gettimeout(), 0.0)
                    self.assertFalse(listener.get_inheritable())
                    try:
                        listening = listener.getsockopt(
                            socket.SOL_SOCKET,
                            socket.SO_ACCEPTCONN,
                        )
                    except OSError as error:
                        self.assertEqual(error.errno, errno.ENOPROTOOPT)
                    else:
                        self.assertEqual(listening, 1)
                finally:
                    self.assertTrue(server.close())
            finally:
                self.assertTrue(runtime.close())


@unittest.skipUnless(sys.platform == "darwin", "requires native macOS Seatbelt")
class TestNativeUnixSocketPolicy(unittest.TestCase):
    @staticmethod
    def _run_probe(
        sandbox_exec: str, profile: str, cwd: Path, source: str,
        *arguments: str,
    ) -> str:
        try:
            result = subprocess.run(
                [sandbox_exec, "-p", profile, sys.executable, "-S", "-c", source,
                 *arguments],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("sandboxed socket probe exceeded its deadline") from None
        except OSError:
            raise AssertionError("could not start sandboxed socket probe") from None
        if result.returncode != 0:
            raise AssertionError("sandboxed socket probe did not exit cleanly")
        markers = [line for line in result.stdout.splitlines() if line.startswith("probe:")]
        if len(markers) != 1:
            raise AssertionError("sandboxed socket probe returned an invalid marker")
        return markers[0]

    def test_preconnected_unix_fd_without_worker_socket_grants(self) -> None:
        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        if not Path(sandbox_exec).is_file():
            self.skipTest("sandbox-exec is unavailable; no conformance credit")

        with tempfile.TemporaryDirectory(
            prefix="icode-seatbelt-preconnected-fd-", dir="/private/tmp",
        ) as raw_root:
            root = Path(raw_root).resolve()
            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            policy = SandboxPolicy(
                schema_version=1,
                run_id="run-macos-preconnected-fd-test",
                ticket_id="ICODE-MACOS-PRECONNECTED-FD-1",
                step="code",
                workspace_root=workspace,
                read_roots=(workspace,),
                write_roots=(workspace,),
                deny_read_roots=(),
                deny_write_roots=(),
                network_mode=NetworkMode.DENY,
                allowed_domains=(),
                process_limit=8,
                wall_timeout_seconds=10,
                output_limit_bytes=4096,
                protected_paths=(),
            )
            sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)
            profile = sandbox._policy_profile(policy)
            host_connection, worker_connection = socket.socketpair(
                socket.AF_UNIX, socket.SOCK_STREAM,
            )
            host_connection.sendall(b"seatbelt-fd-reply")
            host_connection.settimeout(0.5)
            source = (
                "import errno, socket, sys\n"
                "denied = (errno.EPERM, errno.EACCES)\n"
                "connection = None\n"
                "try:\n"
                "    connection = socket.socket(fileno=int(sys.argv[1]))\n"
                "    connection.settimeout(1.0)\n"
                "    if connection.recv(64) != b'seatbelt-fd-reply':\n"
                "        fd_status = 'error'\n"
                "    else:\n"
                "        connection.sendall(b'seatbelt-fd-request')\n"
                "        fd_status = 'roundtrip'\n"
                "except OSError as error:\n"
                "    fd_status = 'denied' if error.errno in denied else 'error'\n"
                "finally:\n"
                "    if connection is not None: connection.close()\n"
                "socket_status = {}\n"
                "for name, family in (('tcp', socket.AF_INET), ('unix', socket.AF_UNIX)):\n"
                "    try:\n"
                "        candidate = socket.socket(family, socket.SOCK_STREAM)\n"
                "    except OSError as error:\n"
                "        socket_status[name] = 'denied' if error.errno in denied else 'error'\n"
                "    else:\n"
                "        candidate.close()\n"
                "        socket_status[name] = 'created'\n"
                "print('probe:' + ','.join((fd_status, socket_status['tcp'], "
                "socket_status['unix'])))\n"
            )
            print(
                probe.format_preconnected_fd_probe_notice(
                    stage="started",
                    exit_code=None,
                    marker_count=0,
                    fd_status="not_run",
                    tcp_socket_status="not_run",
                    unix_socket_status="not_run",
                ),
                flush=True,
            )
            try:
                result = probe.run_with_inherited_fds(
                    [
                        sandbox_exec, "-p", profile, sys.executable, "-S", "-c",
                        source, str(worker_connection.fileno()),
                    ],
                    pass_fds=(worker_connection.fileno(),),
                    cwd=workspace,
                    timeout_seconds=7.0,
                )
                try:
                    host_request = host_connection.recv(64)
                except TimeoutError:
                    host_request = b""
            finally:
                worker_connection.close()
                host_connection.close()

            markers = [
                line for line in result.stdout.splitlines()
                if line.startswith("probe:")
            ]
            fields = markers[0][len("probe:"):].split(",") if len(markers) == 1 else []
            if len(fields) == 3:
                fd_status, tcp_socket_status, unix_socket_status = fields
            else:
                fd_status = tcp_socket_status = unix_socket_status = "unparsed"
            print(
                probe.format_preconnected_fd_probe_notice(
                    stage="observed",
                    exit_code=result.returncode,
                    marker_count=len(markers),
                    fd_status=(
                        fd_status
                        if fd_status in {"roundtrip", "denied", "error", "unparsed"}
                        else "unparsed"
                    ),
                    tcp_socket_status=(
                        tcp_socket_status
                        if tcp_socket_status in {"denied", "created", "error", "unparsed"}
                        else "unparsed"
                    ),
                    unix_socket_status=(
                        unix_socket_status
                        if unix_socket_status in {"denied", "created", "error", "unparsed"}
                        else "unparsed"
                    ),
                ),
                flush=True,
            )

            self.assertIn(host_request, (b"", b"seatbelt-fd-request"))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(len(markers), 1)
            self.assertEqual(len(fields), 3)
            self.assertIn(fd_status, {"roundtrip", "denied", "error"})
            self.assertIn(tcp_socket_status, {"denied", "created"})
            self.assertIn(unix_socket_status, {"denied", "created"})
            self.assertEqual(tcp_socket_status, "denied")
            self.assertEqual(unix_socket_status, "denied")
            if fd_status == "roundtrip":
                self.assertEqual(host_request, b"seatbelt-fd-request")
            else:
                self.assertEqual(host_request, b"")

    @staticmethod
    def _run_sandboxed_curl(
        sandbox_exec: str,
        profile: str,
        curl_path: str,
        cwd: Path,
        environment: dict[str, str],
        url: str,
    ) -> tuple[int, bytes]:
        try:
            result = subprocess.run(
                [
                    sandbox_exec, "-p", profile, curl_path, "-q", "--fail",
                    "--silent", "--show-error", "--max-time", "4",
                    "--noproxy", "", "--output", "-", url,
                ],
                cwd=cwd,
                env=environment,
                capture_output=True,
                timeout=8,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("sandboxed curl canary exceeded its deadline") from None
        except OSError:
            raise AssertionError("could not start sandboxed curl canary") from None
        return result.returncode, result.stdout

    def test_path_scoped_unix_proxy_works_while_other_sockets_remain_denied(self) -> None:
        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        if not Path(sandbox_exec).is_file():
            self.skipTest("sandbox-exec is unavailable")

        with tempfile.TemporaryDirectory(
            prefix="icode-seatbelt-unix-probe-", dir="/private/tmp",
        ) as raw_root:
            root = Path(raw_root)
            workspace = root / "workspace"
            approved_root = root / "proxy"
            other_root = workspace / "other"
            workspace.mkdir()
            approved_root.mkdir(parents=True)
            other_root.mkdir()
            allowed_path = approved_root / "proxy.sock"
            denied_path = other_root / "other.sock"

            sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)
            base_profile = sandbox._profile(workspace, False)
            profile = probe.build_test_profile(base_profile, approved_root)
            allowed_source = (
                "import errno, socket, sys\n"
                "client = None\n"
                "try:\n"
                "    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "    client.settimeout(2)\n"
                "    client.connect(sys.argv[1])\n"
                "    client.sendall(b'icode-unix-probe')\n"
                "    print('probe:connected')\n"
                "except OSError as exc:\n"
                "    print('probe:denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "finally:\n"
                "    if client is not None: client.close()\n"
            )
            unlink_source = (
                "import errno, os, sys\n"
                "try:\n"
                "    os.unlink(sys.argv[1])\n"
                "except OSError as exc:\n"
                "    print('probe:denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "else:\n"
                "    print('probe:unlinked')\n"
            )
            tcp_source = (
                "import errno, socket, sys\n"
                "client = None\n"
                "try:\n"
                "    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "    client.settimeout(2)\n"
                "    client.connect(('127.0.0.1', int(sys.argv[1])))\n"
                "    print('probe:connected')\n"
                "except OSError as exc:\n"
                "    print('probe:denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "finally:\n"
                "    if client is not None: client.close()\n"
            )

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as allowed_listener:
                allowed_listener.bind(str(allowed_path))
                allowed_listener.listen(1)
                allowed_listener.settimeout(2)
                allowed_result = self._run_probe(
                    sandbox_exec, profile, workspace, allowed_source,
                    str(allowed_path),
                )
                self.assertEqual(allowed_result, "probe:connected")
                connection, _ = allowed_listener.accept()
                with connection:
                    connection.settimeout(1)
                    received = bytearray()
                    while len(received) < len(b"icode-unix-probe"):
                        chunk = connection.recv(len(b"icode-unix-probe") - len(received))
                        if not chunk:
                            break
                        received.extend(chunk)
                    self.assertEqual(bytes(received), b"icode-unix-probe")
                unlink_result = self._run_probe(
                    sandbox_exec, profile, workspace, unlink_source,
                    str(allowed_path),
                )
                self.assertEqual(unlink_result, "probe:denied")
                self.assertTrue(allowed_path.exists())

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as denied_listener:
                denied_listener.bind(str(denied_path))
                denied_listener.listen(1)
                denied_listener.settimeout(0.25)
                denied_result = self._run_probe(
                    sandbox_exec, profile, workspace, allowed_source,
                    str(denied_path),
                )
                self.assertEqual(denied_result, "probe:denied")
                with self.assertRaises(socket.timeout):
                    denied_listener.accept()

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_listener:
                tcp_listener.bind(("127.0.0.1", 0))
                tcp_listener.listen(1)
                tcp_listener.settimeout(0.25)
                tcp_result = self._run_probe(
                    sandbox_exec, profile, workspace, tcp_source,
                    str(tcp_listener.getsockname()[1]),
                )
                self.assertEqual(tcp_result, "probe:denied")
                with self.assertRaises(socket.timeout):
                    tcp_listener.accept()

        print(
            "::notice::macos-seatbelt-unix-socket "
            "approved_unix=connected_payload_verified=yes "
            "other_unix=denied tcp_loopback=denied conformance_credit=none",
            flush=True,
        )

    def test_sandboxed_curl_uses_all_proxy_with_path_scoped_socks5_uds(self) -> None:
        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        curl_path = shutil.which("curl")
        if not Path(sandbox_exec).is_file() or curl_path is None:
            print(
                "::warning::macos-seatbelt-curl-socks-uds "
                "supported=no reason=client_or_sandbox_exec_missing conformance_credit=none",
                flush=True,
            )
            self.skipTest("curl or sandbox-exec is unavailable; no conformance credit")
        try:
            version_result = subprocess.run(
                [curl_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            print(
                "::warning::macos-seatbelt-curl-socks-uds "
                "supported=no reason=version_probe_failed conformance_credit=none",
                flush=True,
            )
            self.skipTest("curl version probe failed; no conformance credit")
        if version_result.returncode != 0 or not probe.supports_curl_socks5_uds(
            version_result.stdout,
        ):
            print(
                "::warning::macos-seatbelt-curl-socks-uds "
                "supported=no reason=version_or_unix_sockets_feature_missing "
                "conformance_credit=none",
                flush=True,
            )
            self.skipTest("curl lacks SOCKS5 UDS support; no conformance credit")

        sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)
        with tempfile.TemporaryDirectory(
            prefix="icode-seatbelt-curl-socks-", dir="/private/tmp",
        ) as raw_root:
            root = Path(raw_root)
            workspace = root / "workspace"
            approved_root = root / "proxy"
            workspace.mkdir()
            approved_root.mkdir()
            socket_path = approved_root / "socks.sock"
            proxy_url = probe.curl_socks5_uds_proxy_url(socket_path)
            profile = probe.build_test_profile(
                sandbox._profile(workspace, False), approved_root,
            )
            environment = {
                "PATH": "/usr/bin:/bin",
                "HOME": str(workspace),
                "LC_ALL": "C",
                "ALL_PROXY": proxy_url,
                "NO_PROXY": "",
                "no_proxy": "",
            }
            allowed_url = "http://approved.example:45678/canary"
            blocked_url = "http://blocked.example:45678/canary"
            with probe.Socks5UdsCanary(
                socket_path,
                approved_target=("approved.example", 45678),
                blocked_target=("blocked.example", 45678),
            ) as canary:
                allowed_status, allowed_body = self._run_sandboxed_curl(
                    sandbox_exec, profile, curl_path, workspace,
                    environment, allowed_url,
                )
                blocked_status, blocked_body = self._run_sandboxed_curl(
                    sandbox_exec, profile, curl_path, workspace,
                    environment, blocked_url,
                )

            self.assertEqual(allowed_status, 0)
            self.assertEqual(allowed_body, probe.Socks5UdsCanary._CANARY_BODY)
            self.assertNotEqual(blocked_status, 0)
            self.assertEqual(blocked_body, b"")
            self.assertEqual(
                canary.observed_targets,
                [("approved.example", 45678), ("blocked.example", 45678)],
            )
            self.assertEqual(canary.failures, [])

        print(
            "::notice::macos-seatbelt-curl-socks-uds "
            "curl_supported=yes socks5h_domain_preserved=yes "
            "approved_canary=yes blocked_target=denied conformance_credit=none",
            flush=True,
        )

    def test_sandboxed_curl_uses_test_bridge_and_live_lease_scope(self) -> None:
        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        curl_path = shutil.which("curl")
        if not Path(sandbox_exec).is_file() or curl_path is None:
            self.skipTest("curl or sandbox-exec is unavailable; no conformance credit")
        try:
            version_result = subprocess.run(
                [curl_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            self.skipTest("curl version probe failed; no conformance credit")
        if version_result.returncode != 0 or not probe.supports_curl_socks5_uds(
            version_result.stdout,
        ):
            self.skipTest("curl lacks SOCKS5 UDS support; no conformance credit")

        with tempfile.TemporaryDirectory(
            prefix="icode-seatbelt-live-lease-", dir="/private/tmp",
        ) as raw_root:
            root = Path(raw_root)
            workspace = root / "workspace"
            approved_root = root / "proxy"
            workspace.mkdir()
            approved_root.mkdir()
            socket_path = approved_root / "socks.sock"
            sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)
            profile = probe.build_test_profile(
                sandbox._profile(workspace, False), approved_root,
            )
            environment = {
                "PATH": "/usr/bin:/bin",
                "HOME": str(workspace),
                "LC_ALL": "C",
                "ALL_PROXY": probe.curl_socks5_uds_proxy_url(socket_path),
                "NO_PROXY": "",
                "no_proxy": "",
            }

            policy = SandboxPolicy(
                schema_version=1,
                run_id="run-macos-socks-lease-test",
                ticket_id="ICODE-MACOS-SOCKS-LEASE-1",
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
            authority = NetworkLeaseAuthority()
            issued = authority.request_lease(
                policy,
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("packages.example",),
                ttl_seconds=60,
            )
            runtime = HostConnectRuntime(authority, sweep_interval_seconds=0.01)
            runtime.start()
            scope = runtime.create_scope(
                issued,
                policy,
                NetworkPurpose.PACKAGE_INSTALL,
            )

            listener_facts: list[str] = []

            def record_listener_fact(
                name: str,
                probe_fact: Callable[[], object],
            ) -> None:
                try:
                    fact_value = probe_fact()
                except OSError as error:
                    error_number = error.errno
                    safe_error_number = (
                        error_number if type(error_number) is int else "unknown"
                    )
                    error_name = (
                        errno.errorcode.get(error_number, "UNKNOWN")
                        if type(error_number) is int
                        else "UNKNOWN"
                    )
                    fact_value = (
                        f"error:OSError:errno={safe_error_number},name={error_name}"
                    )
                except Exception as error:
                    fact_value = f"error:{type(error).__name__}"
                listener_facts.append(f"{name}={fact_value}")

            def inspect_owned_listener(listener: socket.socket) -> None:
                def listening_buffer_fact() -> str:
                    option_value = listener.getsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_ACCEPTCONN,
                        4,
                    )
                    if type(option_value) is not bytes or len(option_value) != 4:
                        return "unexpected_buffer_shape"
                    return (
                        "matches_one"
                        if option_value == struct.pack("@i", 1)
                        else "differs_from_one"
                    )

                def stream_socket_buffer_fact() -> str:
                    option_value = listener.getsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_TYPE,
                        4,
                    )
                    if type(option_value) is not bytes or len(option_value) != 4:
                        return "unexpected_buffer_shape"
                    return (
                        "matches_stream"
                        if option_value == struct.pack("@i", socket.SOCK_STREAM)
                        else "differs_from_stream"
                    )

                record_listener_fact(
                    "exact_socket_type",
                    lambda: type(listener) is socket.socket,
                )
                record_listener_fact(
                    "ipv4_family",
                    lambda: listener.family == socket.AF_INET,
                )
                record_listener_fact(
                    "stream_socket",
                    lambda: listener.getsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_TYPE,
                    ) == socket.SOCK_STREAM,
                )
                record_listener_fact("acceptconn_level", lambda: socket.SOL_SOCKET)
                record_listener_fact("acceptconn_option", lambda: socket.SO_ACCEPTCONN)
                record_listener_fact(
                    "stream_socket_buffer_form",
                    stream_socket_buffer_fact,
                )
                record_listener_fact(
                    "listening",
                    lambda: listener.getsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_ACCEPTCONN,
                    ) == 1,
                )
                record_listener_fact("listening_buffer_form", listening_buffer_fact)
                record_listener_fact(
                    "ipv4_loopback",
                    lambda: listener.getsockname()[0] == "127.0.0.1",
                )
                record_listener_fact(
                    "positive_port",
                    lambda: type(listener.getsockname()[1]) is int
                    and listener.getsockname()[1] > 0,
                )
                record_listener_fact(
                    "wrapper_nonblocking",
                    lambda: listener.gettimeout() == 0.0,
                )
                record_listener_fact(
                    "fd_nonblocking",
                    lambda: not os.get_blocking(listener.fileno()),
                )
                record_listener_fact(
                    "scope_type",
                    lambda: isinstance(scope, HostHttpsConnectScope),
                )
                record_listener_fact(
                    "noninheritable_after_validation",
                    lambda: not listener.get_inheritable(),
                )

            proxy_listener, proxy_server = probe.create_test_lease_proxy_server(scope)
            inspect_owned_listener(proxy_listener)
            print(
                "::notice::macos-live-lease-listener-contract "
                f"python={platform.python_version()} "
                f"macos={platform.mac_ver()[0] or 'unknown'} "
                f"arch={platform.machine()} "
                + " ".join(listener_facts),
                flush=True,
            )
            upstream_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            upstream_listener.bind(("127.0.0.1", 0))
            upstream_listener.listen(2)
            upstream_address = upstream_listener.getsockname()
            upstream_body = b"live-test-lease-bridge\n"
            upstream_requests: list[bytes] = []
            upstream_failures: list[str] = []
            resolved_hosts: list[str] = []
            ready = threading.Event()
            stop = threading.Event()

            def serve_upstream_once() -> None:
                try:
                    connection = probe.accept_connection_until_stopped(
                        upstream_listener,
                        stop,
                    )
                    if connection is None:
                        return
                    with connection:
                        connection.settimeout(3.0)
                        request_head = bytearray()
                        while not request_head.endswith(b"\r\n\r\n"):
                            chunk = connection.recv(1)
                            if not chunk:
                                raise AssertionError("curl request ended before HTTP headers")
                            request_head.extend(chunk)
                            if len(request_head) > 8192:
                                raise AssertionError("curl HTTP request exceeded test bound")
                        upstream_requests.append(bytes(request_head))
                        connection.sendall(
                            b"HTTP/1.1 200 OK\r\nContent-Length: "
                            + str(len(upstream_body)).encode("ascii")
                            + b"\r\nConnection: close\r\n\r\n"
                            + upstream_body
                        )
                        connection.shutdown(socket.SHUT_WR)
                except BaseException as error:
                    upstream_failures.append(type(error).__name__)

            def resolve_to_test_upstream(
                hostname: str,
                port: int,
                *,
                resolver: object = None,
            ) -> tuple[ResolvedNetworkTarget, ...]:
                del resolver
                resolved_hosts.append(hostname)
                self.assertEqual(port, 443)
                return (
                    ResolvedNetworkTarget(
                        family=socket.AF_INET,
                        socket_type=socket.SOCK_STREAM,
                        protocol=socket.IPPROTO_TCP,
                        sockaddr=upstream_address,
                    ),
                )

            proxy_failures: list[str] = []

            def serve_proxy() -> None:
                try:
                    proxy_server.serve_forever(stop, ready_event=ready)
                except BaseException as error:
                    proxy_failures.append(type(error).__name__)

            upstream_worker = threading.Thread(
                target=serve_upstream_once,
                name="icode-macos-live-lease-upstream",
                daemon=True,
            )
            proxy_worker = threading.Thread(
                target=serve_proxy,
                name="icode-macos-live-lease-proxy",
                daemon=True,
            )
            resolver_patch = patch(
                "icode.network_connector.resolve_public_tcp_targets",
                side_effect=resolve_to_test_upstream,
            )
            resolver_patch.start()
            self.addCleanup(resolver_patch.stop)
            upstream_worker.start()
            proxy_worker.start()
            try:
                self.assertTrue(ready.wait(1.0), "live lease CONNECT server did not start")
                with probe.Socks5UdsLeaseConnectBridge(
                    socket_path,
                    proxy_listener.getsockname(),
                    lease_check=scope.verify_lease,
                ) as bridge:
                    allowed_status, allowed_body = self._run_sandboxed_curl(
                        sandbox_exec,
                        profile,
                        curl_path,
                        workspace,
                        environment,
                        "http://packages.example:443/canary",
                    )
                    blocked_status, blocked_body = self._run_sandboxed_curl(
                        sandbox_exec,
                        profile,
                        curl_path,
                        workspace,
                        environment,
                        "http://blocked.example:443/canary",
                    )
                    self.assertEqual(bridge.failures, [])
                self.assertEqual(allowed_status, 0)
                self.assertEqual(allowed_body, upstream_body)
                self.assertNotEqual(blocked_status, 0)
                self.assertEqual(blocked_body, b"")
                upstream_worker.join(timeout=2.0)
                self.assertFalse(upstream_worker.is_alive())
                self.assertEqual(len(upstream_requests), 1)
                self.assertIn(b"GET /canary ", upstream_requests[0])
                self.assertEqual(resolved_hosts, ["packages.example"])
                self.assertEqual(upstream_failures, [])
            finally:
                stop.set()
                proxy_server.close()
                proxy_worker.join(timeout=2.0)
                upstream_listener.close()
                upstream_worker.join(timeout=2.0)
                self.assertTrue(proxy_server.close())
                self.assertTrue(runtime.close())
            self.assertFalse(proxy_worker.is_alive())
            self.assertEqual(proxy_failures, [])

        print(
            "::notice::macos-seatbelt-live-lease-uds-test "
            "approved_domain=http_test_tunnel=passed blocked_domain=failed_closed "
            "direct_worker_tcp=covered_by_socket_probe conformance_credit=none",
            flush=True,
        )

    def test_sandboxed_curl_uses_production_unix_lease_proxy(self) -> None:
        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        curl_path = shutil.which("curl")
        if not Path(sandbox_exec).is_file() or curl_path is None:
            self.skipTest("curl or sandbox-exec is unavailable; no conformance credit")
        try:
            version_result = subprocess.run(
                [curl_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            self.skipTest("curl version probe failed; no conformance credit")
        if version_result.returncode != 0 or not probe.supports_curl_socks5_uds(
            version_result.stdout,
        ):
            self.skipTest("curl lacks SOCKS5 UDS support; no conformance credit")

        with tempfile.TemporaryDirectory(
            prefix="icode-seatbelt-production-uds-", dir="/private/tmp",
        ) as raw_root:
            root = Path(raw_root).resolve()
            workspace = root / "workspace"
            socket_root = root / "proxy"
            workspace.mkdir(mode=0o700)
            socket_root.mkdir(mode=0o700)
            socket_path = socket_root / "lease.sock"
            sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)

            policy = SandboxPolicy(
                schema_version=1,
                run_id="run-macos-production-uds-test",
                ticket_id="ICODE-MACOS-PRODUCTION-UDS-1",
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
            authority = NetworkLeaseAuthority()
            issued = authority.request_lease(
                policy,
                approver=ScriptedApprover([True]),
                purpose=NetworkPurpose.PACKAGE_INSTALL,
                allowed_domains=("packages.example",),
                ttl_seconds=60,
            )
            runtime = HostConnectRuntime(authority, sweep_interval_seconds=0.01)
            runtime.start()
            scope = runtime.create_scope(
                issued,
                policy,
                NetworkPurpose.PACKAGE_INSTALL,
            )
            proxy_server = HostUnixSocks5ProxyServer(socket_path, scope)
            wrapped = sandbox.experimental_wrap_leased_unix_connect_candidate(
                [curl_path, "--silent"],
                policy=policy,
                socket_path=socket_path,
            )
            profile = wrapped[wrapped.index("-p") + 1]
            environment = {
                "PATH": "/usr/bin:/bin",
                "HOME": str(workspace),
                "LC_ALL": "C",
                "ALL_PROXY": probe.curl_socks5_uds_proxy_url(socket_path),
                "NO_PROXY": "",
                "no_proxy": "",
            }
            upstream_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            upstream_listener.bind(("127.0.0.1", 0))
            upstream_listener.listen(2)
            upstream_listener.settimeout(3.0)
            upstream_address = upstream_listener.getsockname()
            upstream_body = b"production-uds-lease\n"
            upstream_requests: list[bytes] = []
            upstream_failures: list[str] = []
            resolved_hosts: list[str] = []
            ready = threading.Event()
            stop = threading.Event()
            proxy_failures: list[str] = []

            def serve_upstream_once() -> None:
                try:
                    connection, _address = upstream_listener.accept()
                    with connection:
                        connection.settimeout(3.0)
                        request_head = bytearray()
                        while not request_head.endswith(b"\r\n\r\n"):
                            chunk = connection.recv(1)
                            if not chunk:
                                raise AssertionError("canary request ended before headers")
                            request_head.extend(chunk)
                            if len(request_head) > 8192:
                                raise AssertionError("canary request exceeded test bound")
                        upstream_requests.append(bytes(request_head))
                        connection.sendall(
                            b"HTTP/1.1 200 OK\r\nContent-Length: "
                            + str(len(upstream_body)).encode("ascii")
                            + b"\r\nConnection: close\r\n\r\n"
                            + upstream_body
                        )
                        connection.shutdown(socket.SHUT_WR)
                except BaseException as error:
                    upstream_failures.append(type(error).__name__)

            def resolve_to_test_upstream(
                hostname: str,
                port: int,
                *,
                resolver: object = None,
            ) -> tuple[ResolvedNetworkTarget, ...]:
                del resolver
                resolved_hosts.append(hostname)
                self.assertEqual(port, 443)
                return (
                    ResolvedNetworkTarget(
                        family=socket.AF_INET,
                        socket_type=socket.SOCK_STREAM,
                        protocol=socket.IPPROTO_TCP,
                        sockaddr=upstream_address,
                    ),
                )

            def serve_proxy() -> None:
                try:
                    proxy_server.serve_forever(stop, ready_event=ready)
                except BaseException as error:
                    proxy_failures.append(type(error).__name__)

            direct_network_source = (
                "import errno, socket, sys\n"
                "sock = None\n"
                "family = int(sys.argv[1])\n"
                "port = int(sys.argv[2])\n"
                "target = ('127.0.0.1', port) if family == socket.AF_INET else ('::1', port, 0, 0)\n"
                "try:\n"
                "    sock = socket.socket(family, socket.SOCK_STREAM)\n"
                "except OSError as exc:\n"
                "    print('probe:socket-denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "else:\n"
                "    try:\n"
                "        sock.settimeout(1.0)\n"
                "        sock.connect(target)\n"
                "    except OSError as exc:\n"
                "        print('probe:connect-denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "    else:\n"
                "        print('probe:connected')\n"
                "finally:\n"
                "    if sock is not None: sock.close()\n"
            )
            worker_created_socket_path = socket_root / "worker-created.sock"
            worker_bind_source = (
                "import errno, socket, sys\n"
                "sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "try:\n"
                "    sock.bind(sys.argv[1])\n"
                "except OSError as exc:\n"
                "    print('probe:create-denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "else:\n"
                "    print('probe:created')\n"
                "finally:\n"
                "    sock.close()\n"
            )

            outside_socket_path = root / "outside.sock"
            outside_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(outside_listener.close)
            outside_listener.bind(str(outside_socket_path))
            os.chmod(outside_socket_path, 0o600)
            outside_listener.listen(1)
            outside_listener.settimeout(0.2)
            outside_network_source = (
                "import errno, socket, sys\n"
                "sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "try:\n"
                "    sock.connect(sys.argv[1])\n"
                "except OSError as exc:\n"
                "    print('probe:connect-denied' if exc.errno in (errno.EPERM, errno.EACCES) "
                "else 'probe:unexpected')\n"
                "else:\n"
                "    print('probe:connected')\n"
                "finally:\n"
                "    sock.close()\n"
            )

            upstream_worker = threading.Thread(
                target=serve_upstream_once,
                name="icode-macos-production-uds-upstream",
                daemon=True,
            )
            proxy_worker = threading.Thread(
                target=serve_proxy,
                name="icode-macos-production-uds-proxy",
                daemon=True,
            )
            direct_listeners: dict[int, tuple[socket.socket, int]] = {}
            for family, bind_address in (
                (socket.AF_INET, ("127.0.0.1", 0)),
                (socket.AF_INET6, ("::1", 0, 0, 0)),
            ):
                listener = socket.socket(family, socket.SOCK_STREAM)
                self.addCleanup(listener.close)
                listener.settimeout(2.0)
                listener.bind(bind_address)
                listener.listen(1)
                endpoint = listener.getsockname()
                with socket.socket(family, socket.SOCK_STREAM) as host_control:
                    host_control.settimeout(2.0)
                    host_control.connect(endpoint)
                    accepted_control, _address = listener.accept()
                    accepted_control.close()
                listener.settimeout(0.2)
                direct_listeners[family] = (listener, int(endpoint[1]))

            resolver_patch = patch(
                "icode.network_connector.resolve_public_tcp_targets",
                side_effect=resolve_to_test_upstream,
            )
            resolver_patch.start()
            self.addCleanup(resolver_patch.stop)
            upstream_worker.start()
            proxy_worker.start()

            try:
                self.assertTrue(ready.wait(1.0), "lease UDS proxy did not become ready")
                self.assertEqual(socket_path.stat().st_mode & 0o777, 0o600)
                worker_bind_result = self._run_probe(
                    sandbox_exec,
                    profile,
                    workspace,
                    worker_bind_source,
                    str(worker_created_socket_path),
                )
                self.assertEqual(
                    worker_bind_result,
                    "probe:create-denied",
                    "Seatbelt profile allowed a worker-created socket in the proxy directory",
                )
                self.assertFalse(worker_created_socket_path.exists())
                outside_result = self._run_probe(
                    sandbox_exec,
                    profile,
                    workspace,
                    outside_network_source,
                    str(outside_socket_path),
                )
                self.assertEqual(
                    outside_result,
                    "probe:connect-denied",
                    "Seatbelt profile allowed a Unix-domain socket outside its private directory",
                )
                try:
                    outside_peer, _address = outside_listener.accept()
                except TimeoutError:
                    pass
                else:
                    outside_peer.close()
                    self.fail("outside Unix-domain listener accepted a connection")
                direct_results: dict[int, str] = {}
                for family in (socket.AF_INET, socket.AF_INET6):
                    listener, direct_port = direct_listeners[family]
                    direct_result = self._run_probe(
                        sandbox_exec,
                        profile,
                        workspace,
                        direct_network_source,
                        str(family),
                        str(direct_port),
                    )
                    direct_results[family] = direct_result
                    self.assertIn(
                        direct_result,
                        ("probe:socket-denied", "probe:connect-denied"),
                        f"Seatbelt profile allowed direct outbound TCP family {family}",
                    )
                    try:
                        unexpected_peer, _address = listener.accept()
                    except TimeoutError:
                        pass
                    else:
                        unexpected_peer.close()
                        self.fail(
                            f"Seatbelt listener accepted direct TCP family {family}"
                        )
                allowed_status, allowed_body = self._run_sandboxed_curl(
                    sandbox_exec,
                    profile,
                    curl_path,
                    workspace,
                    environment,
                    "http://packages.example:443/canary",
                )
                blocked_status, blocked_body = self._run_sandboxed_curl(
                    sandbox_exec,
                    profile,
                    curl_path,
                    workspace,
                    environment,
                    "http://blocked.example:443/canary",
                )
                self.assertEqual(allowed_status, 0)
                self.assertEqual(allowed_body, upstream_body)
                self.assertNotEqual(blocked_status, 0)
                self.assertEqual(blocked_body, b"")
                upstream_worker.join(timeout=2.0)
                self.assertFalse(upstream_worker.is_alive())
                self.assertEqual(len(upstream_requests), 1)
                self.assertIn(b"GET /canary ", upstream_requests[0])
                self.assertEqual(resolved_hosts, ["packages.example"])
                self.assertEqual(upstream_failures, [])
            finally:
                stop.set()
                proxy_server.close()
                proxy_worker.join(timeout=2.0)
                outside_listener.close()
                upstream_listener.close()
                upstream_worker.join(timeout=2.0)
                self.assertTrue(proxy_server.close())
                self.assertFalse(socket_path.exists())
                self.assertTrue(runtime.close())
            self.assertFalse(proxy_worker.is_alive())
            self.assertEqual(proxy_failures, [])

        print(
            "::notice::macos-seatbelt-production-uds-lease-test "
            "approved_domain=passed blocked_domain=failed_closed "
            "worker_proxy_dir_bind=denied outside_uds=denied "
            f"ipv4_tcp={direct_results[socket.AF_INET]} "
            f"ipv6_tcp={direct_results[socket.AF_INET6]} "
            "profile_scope=private_socket_dir_subpath conformance_credit=none",
            flush=True,
        )


if __name__ == "__main__":
    unittest.main()
