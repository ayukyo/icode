"""Test-only Seatbelt profile composition for AF_UNIX policy probes.

This module is deliberately outside the production sandbox path. Its profile
grant is limited to connecting to AF_UNIX sockets below one approved root.
"""

from __future__ import annotations

import select
import stat
from pathlib import Path
import re
import socket
import threading
import time
from typing import Callable
from urllib.parse import quote

from icode.connect_request import ConnectRequestError, parse_https_connect_request_head
from icode.network_lease import NetworkLeaseValidationError


_CURL_VERSION_RE = re.compile(r"^curl\s+(\d+)\.(\d+)\.(\d+)(?:\s|$)")
_MACOS_SUN_PATH_BYTES = 103
_BRIDGE_CLIENT_TIMEOUT_SECONDS = 3.0
_BRIDGE_CONNECT_TIMEOUT_SECONDS = 3.0
_BRIDGE_ACCEPT_POLL_SECONDS = 0.1
_BRIDGE_RELAY_POLL_SECONDS = 0.1
_BRIDGE_RELAY_READ_CHUNK_BYTES = 64 * 1024
_BRIDGE_RELAY_BUFFER_LIMIT_BYTES = 256 * 1024
_BRIDGE_CONNECT_RESPONSE = b"HTTP/1.1 200 Connection Established\r\n\r\n"
_BRIDGE_CONNECT_RESPONSE_MAX_BYTES = 4096


def _close_bridge_socket(connection: socket.socket) -> bool:
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        connection.close()
    except OSError:
        return False
    return connection.fileno() < 0


def supports_curl_socks5_uds(version_output: str) -> bool:
    """Require curl 7.84.0+ and a UnixSockets-enabled build.

    The build feature alone is insufficient: curl added SOCKS proxy UDS
    support in 7.84.0, while UnixSockets predates that protocol support.
    """

    if not isinstance(version_output, str):
        return False
    lines = version_output.splitlines()
    if not lines:
        return False
    match = _CURL_VERSION_RE.match(lines[0].strip())
    if match is None:
        return False
    version = tuple(int(part) for part in match.groups())
    if version < (7, 84, 0):
        return False
    feature_lines = [line for line in lines[1:] if line.startswith("Features:")]
    return any("UnixSockets" in line.split() for line in feature_lines)


def curl_socks5_uds_proxy_url(socket_path: Path) -> str:
    """Build curl's SOCKS5h UDS proxy URL for one short absolute path."""

    path = Path(socket_path)
    raw_path = str(path)
    if not path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise ValueError("curl UDS proxy socket path must be absolute and normalized")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_path):
        raise ValueError("curl UDS proxy socket path contains a control character")
    if len(raw_path.encode("utf-8")) > _MACOS_SUN_PATH_BYTES:
        raise ValueError("curl UDS proxy socket path exceeds macOS sun_path")
    return "socks5h://localhost" + quote(raw_path, safe="/")


class Socks5UdsCanary:
    """A test-only SOCKS5 server that never opens an outbound connection."""

    _CANARY_BODY = b"icode-socks5-uds-canary\n"
    _MAX_HTTP_HEADER = 4096

    def __init__(
        self,
        socket_path: Path,
        *,
        approved_target: tuple[str, int],
        blocked_target: tuple[str, int],
    ) -> None:
        self.socket_path = Path(socket_path)
        self.approved_target = approved_target
        self.blocked_target = blocked_target
        if not self.socket_path.is_absolute():
            raise ValueError("test canary socket path must be absolute")
        if approved_target == blocked_target:
            raise ValueError("test canary targets must differ")
        for hostname, port in (approved_target, blocked_target):
            if not hostname or not 1 <= port <= 65535:
                raise ValueError("test canary target is invalid")
        self.observed_targets: list[tuple[str, int]] = []
        self.failures: list[str] = []
        self._listener: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Socks5UdsCanary":
        if not hasattr(socket, "AF_UNIX"):
            raise OSError("AF_UNIX is unavailable")
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise FileExistsError("test canary socket path already exists")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.socket_path))
            listener.listen(4)
            listener.settimeout(0.2)
        except OSError:
            listener.close()
            raise
        self._listener = listener
        self._thread = threading.Thread(
            target=self._serve, name="icode-socks5-uds-canary", daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._stop.set()
        listener = self._listener
        if listener is not None:
            listener.close()
            self._listener = None
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3)
            if thread.is_alive():
                raise RuntimeError("test canary server did not stop within its deadline")
            self._thread = None
        if self.socket_path.is_socket():
            self.socket_path.unlink()

    @staticmethod
    def _recv_exact(connection: socket.socket, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            chunk = connection.recv(size - len(result))
            if not chunk:
                raise OSError("client closed during SOCKS5 request")
            result.extend(chunk)
        return bytes(result)

    def _serve(self) -> None:
        while not self._stop.is_set():
            listener = self._listener
            if listener is None:
                return
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                self.failures.append("accept_error")
                continue
            with connection:
                connection.settimeout(2)
                try:
                    self._handle_connection(connection)
                except (OSError, ValueError, UnicodeError):
                    self.failures.append("malformed_or_incomplete_request")

    def _handle_connection(self, connection: socket.socket) -> None:
        version, method_count = self._recv_exact(connection, 2)
        methods = self._recv_exact(connection, method_count)
        if version != 5 or 0 not in methods:
            connection.sendall(b"\x05\xff")
            return
        connection.sendall(b"\x05\x00")

        version, command, reserved, address_type = self._recv_exact(connection, 4)
        if version != 5 or command != 1 or reserved != 0:
            self._send_reply(connection, 1)
            return
        if address_type == 1:
            hostname = socket.inet_ntop(socket.AF_INET, self._recv_exact(connection, 4))
        elif address_type == 4:
            hostname = socket.inet_ntop(socket.AF_INET6, self._recv_exact(connection, 16))
        elif address_type == 3:
            name_length = self._recv_exact(connection, 1)[0]
            hostname = self._recv_exact(connection, name_length).decode("ascii")
        else:
            self._send_reply(connection, 8)
            return
        port = int.from_bytes(self._recv_exact(connection, 2), "big")
        target = (hostname, port)
        self.observed_targets.append(target)
        if target != self.approved_target:
            if target != self.blocked_target:
                self.failures.append("unexpected_target")
            self._send_reply(connection, 2)
            return

        self._send_reply(connection, 0)
        request = bytearray()
        while len(request) <= self._MAX_HTTP_HEADER:
            chunk = connection.recv(min(512, self._MAX_HTTP_HEADER + 1 - len(request)))
            if not chunk:
                return
            request.extend(chunk)
            if b"\r\n\r\n" in request:
                break
        if len(request) > self._MAX_HTTP_HEADER or not request.startswith(
            b"GET /canary HTTP/1.1\r\n",
        ):
            self.failures.append("unexpected_http_request")
            return
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
            + f"Content-Length: {len(self._CANARY_BODY)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + self._CANARY_BODY
        )
        connection.sendall(response)

    @staticmethod
    def _send_reply(connection: socket.socket, result: int) -> None:
        connection.sendall(b"\x05" + bytes((result,)) + b"\x00\x01\x00\x00\x00\x00\x00\x00")


class Socks5UdsLeaseConnectBridge:
    """Test-only SOCKS5/UDS adapter to the existing lease CONNECT listener.

    This deliberately does not enter production code. The loopback CONNECT
    listener has no client authentication, so the bridge is suitable only for
    controlled CI experiments and never grants production conformance credit.
    Socket-path identity is checked before cleanup, but compare-and-unlink is
    not atomic on portable POSIX; callers must use an owner-private test root.
    """

    _SOCKS_REPLY_SUCCESS = 0
    _SOCKS_REPLY_GENERAL_FAILURE = 1
    _SOCKS_REPLY_NOT_ALLOWED = 2
    _SOCKS_REPLY_COMMAND_UNSUPPORTED = 7
    _SOCKS_REPLY_ADDRESS_UNSUPPORTED = 8

    def __init__(
        self,
        socket_path: Path,
        connect_proxy_address: tuple[str, int],
        *,
        lease_check: Callable[[], None],
    ) -> None:
        path = Path(socket_path)
        raw_path = str(path)
        if not path.is_absolute() or any(part in {".", ".."} for part in path.parts):
            raise ValueError("test SOCKS bridge path must be absolute and normalized")
        if any(ord(char) < 32 or ord(char) == 127 for char in raw_path):
            raise ValueError("test SOCKS bridge path contains a control character")
        if len(raw_path.encode("utf-8")) > _MACOS_SUN_PATH_BYTES:
            raise ValueError("test SOCKS bridge path exceeds macOS sun_path")
        if type(connect_proxy_address) is not tuple or len(connect_proxy_address) != 2:
            raise ValueError("test CONNECT listener address is invalid")
        proxy_host, proxy_port = connect_proxy_address
        if (
            proxy_host != "127.0.0.1"
            or type(proxy_port) is not int
            or not 1 <= proxy_port <= 65535
        ):
            raise ValueError("test CONNECT listener must be IPv4 loopback")
        if not callable(lease_check):
            raise ValueError("test lease check must be callable")

        self.socket_path = path
        self.connect_proxy_address = connect_proxy_address
        self._lease_check = lease_check
        self.failures: list[str] = []
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._active_sockets: dict[int, socket.socket] = {}
        self._socket_identity: tuple[int, int] | None = None

    def __enter__(self) -> "Socks5UdsLeaseConnectBridge":
        if not hasattr(socket, "AF_UNIX"):
            raise OSError("AF_UNIX is unavailable")
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise FileExistsError("test SOCKS bridge socket path already exists")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.socket_path))
            file_info = self.socket_path.lstat()
            if not stat.S_ISSOCK(file_info.st_mode):
                raise OSError("test SOCKS bridge path is not a socket")
            self._socket_identity = (file_info.st_dev, file_info.st_ino)
            listener.listen(4)
            listener.settimeout(_BRIDGE_ACCEPT_POLL_SECONDS)
            self._listener = listener
            self._thread = threading.Thread(
                target=self._serve,
                name="icode-socks5-lease-bridge",
                daemon=True,
            )
            self._thread.start()
            return self
        except BaseException:
            listener.close()
            self._remove_owned_socket_path()
            raise

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self.close():
            raise RuntimeError("test SOCKS bridge did not close within its deadline")

    def close(self) -> bool:
        self._stop.set()
        with self._lock:
            listener = self._listener
            self._listener = None
            thread = self._thread
            active_sockets = tuple(self._active_sockets.values())
        listener_closed = True
        if listener is not None:
            try:
                listener.close()
            except OSError:
                listener_closed = False
        sockets_closed = True
        for connection in active_sockets:
            sockets_closed = _close_bridge_socket(connection) and sockets_closed
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        if thread is not None and thread.is_alive():
            return False
        path_removed = self._remove_owned_socket_path()
        with self._lock:
            no_active_sockets = not self._active_sockets
        return listener_closed and sockets_closed and path_removed and no_active_sockets

    def _remove_owned_socket_path(self) -> bool:
        try:
            file_info = self.socket_path.lstat()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if (
            not stat.S_ISSOCK(file_info.st_mode)
            or self._socket_identity != (file_info.st_dev, file_info.st_ino)
        ):
            return False
        try:
            self.socket_path.unlink()
        except OSError:
            return False
        return True

    def _track_socket(self, connection: socket.socket) -> bool:
        with self._lock:
            if self._stop.is_set():
                _close_bridge_socket(connection)
                return False
            self._active_sockets[id(connection)] = connection
            return True

    def _forget_socket(self, connection: socket.socket) -> None:
        with self._lock:
            if self._active_sockets.get(id(connection)) is connection:
                del self._active_sockets[id(connection)]

    def _serve(self) -> None:
        while not self._stop.is_set():
            listener = self._listener
            if listener is None:
                return
            try:
                client, _address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                self.failures.append("uds_accept_failed")
                self._stop.wait(_BRIDGE_ACCEPT_POLL_SECONDS)
                continue
            if not self._track_socket(client):
                return
            try:
                client.settimeout(_BRIDGE_CLIENT_TIMEOUT_SECONDS)
                self._handle_client(client)
            except NetworkLeaseValidationError:
                # Expiry/revocation is a normal denial, including mid-handshake.
                pass
            except (OSError, UnicodeError, ValueError, ConnectRequestError):
                if not self._stop.is_set():
                    self.failures.append("socks_client_failed")
            except Exception:
                if not self._stop.is_set():
                    self.failures.append("bridge_internal_failed")
            finally:
                _close_bridge_socket(client)
                self._forget_socket(client)

    @staticmethod
    def _recv_exact(
        connection: socket.socket,
        size: int,
        *,
        deadline: float | None = None,
        lease_check: Callable[[], None] | None = None,
    ) -> bytes:
        if type(size) is not int or size < 0:
            raise ValueError("SOCKS field length is invalid")
        result = bytearray()
        while len(result) < size:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("SOCKS handshake deadline expired")
                connection.settimeout(min(remaining, _BRIDGE_RELAY_POLL_SECONDS))
            try:
                chunk = connection.recv(size - len(result))
            except socket.timeout:
                if lease_check is not None:
                    lease_check()
                continue
            if not chunk:
                raise OSError("SOCKS client closed an incomplete request")
            result.extend(chunk)
            if lease_check is not None:
                lease_check()
        return bytes(result)

    @classmethod
    def _send_reply(cls, connection: socket.socket, result: int) -> None:
        connection.sendall(
            b"\x05" + bytes((result,)) + b"\x00\x01\x00\x00\x00\x00\x00\x00"
        )

    def _read_connect_target(
        self,
        connection: socket.socket,
        deadline: float,
    ) -> bytes | None:
        version, command, reserved, address_type = self._recv_exact(
            connection,
            4,
            deadline=deadline,
            lease_check=self._lease_check,
        )
        if version != 5 or reserved != 0:
            self._send_reply(connection, self._SOCKS_REPLY_GENERAL_FAILURE)
            return None
        if command != 1:
            self._send_reply(connection, self._SOCKS_REPLY_COMMAND_UNSUPPORTED)
            return None
        if address_type != 3:
            self._send_reply(connection, self._SOCKS_REPLY_ADDRESS_UNSUPPORTED)
            return None
        name_length = self._recv_exact(
            connection,
            1,
            deadline=deadline,
            lease_check=self._lease_check,
        )[0]
        if not 1 <= name_length <= 253:
            self._send_reply(connection, self._SOCKS_REPLY_NOT_ALLOWED)
            return None
        hostname_bytes = self._recv_exact(
            connection,
            name_length,
            deadline=deadline,
            lease_check=self._lease_check,
        )
        port = int.from_bytes(
            self._recv_exact(
                connection,
                2,
                deadline=deadline,
                lease_check=self._lease_check,
            ),
            "big",
        )
        try:
            hostname = hostname_bytes.decode("ascii")
            request_head = (
                b"CONNECT " + hostname.encode("ascii") + b":"
                + str(port).encode("ascii") + b" HTTP/1.1\r\nHost: "
                + hostname.encode("ascii") + b"\r\n\r\n"
            )
            target = parse_https_connect_request_head(request_head)
        except (UnicodeError, ConnectRequestError):
            self._send_reply(connection, self._SOCKS_REPLY_NOT_ALLOWED)
            return None
        if target.port != 443:
            self._send_reply(connection, self._SOCKS_REPLY_NOT_ALLOWED)
            return None
        return (
            b"CONNECT " + target.hostname.encode("ascii")
            + b":443 HTTP/1.1\r\nHost: "
            + target.hostname.encode("ascii") + b"\r\n\r\n"
        )

    @classmethod
    def _read_connect_response(
        cls,
        connection: socket.socket,
        *,
        deadline: float,
        lease_check: Callable[[], None],
    ) -> bytes | None:
        response = bytearray()
        while len(response) < _BRIDGE_CONNECT_RESPONSE_MAX_BYTES:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("CONNECT response deadline expired")
            connection.settimeout(min(remaining, _BRIDGE_RELAY_POLL_SECONDS))
            try:
                chunk = connection.recv(1)
            except socket.timeout:
                lease_check()
                continue
            if not chunk:
                lease_check()
                return None
            response.extend(chunk)
            lease_check()
            if response.endswith(b"\r\n\r\n"):
                return bytes(response)
        return None

    def _handle_client(self, client: socket.socket) -> None:
        deadline = time.monotonic() + _BRIDGE_CLIENT_TIMEOUT_SECONDS
        try:
            self._lease_check()
        except NetworkLeaseValidationError:
            return
        version, method_count = self._recv_exact(
            client,
            2,
            deadline=deadline,
            lease_check=self._lease_check,
        )
        if version != 5 or not 1 <= method_count <= 32:
            client.sendall(b"\x05\xff")
            return
        methods = self._recv_exact(
            client,
            method_count,
            deadline=deadline,
            lease_check=self._lease_check,
        )
        if 0 not in methods:
            client.sendall(b"\x05\xff")
            return
        client.sendall(b"\x05\x00")
        try:
            request_head = self._read_connect_target(client, deadline)
        except NetworkLeaseValidationError:
            self._send_reply(client, self._SOCKS_REPLY_NOT_ALLOWED)
            return
        if request_head is None:
            return

        try:
            self._lease_check()
        except NetworkLeaseValidationError:
            self._send_reply(client, self._SOCKS_REPLY_NOT_ALLOWED)
            return
        proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if not self._track_socket(proxy_socket):
            return
        connect_deadline = time.monotonic() + _BRIDGE_CONNECT_TIMEOUT_SECONDS
        try:
            try:
                proxy_socket.settimeout(_BRIDGE_CONNECT_TIMEOUT_SECONDS)
                proxy_socket.connect(self.connect_proxy_address)
                remaining = connect_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("CONNECT proxy deadline expired")
                proxy_socket.settimeout(remaining)
                proxy_socket.sendall(request_head)
                connect_response = self._read_connect_response(
                    proxy_socket,
                    deadline=connect_deadline,
                    lease_check=self._lease_check,
                )
            except NetworkLeaseValidationError:
                if not self._stop.is_set():
                    self._send_reply(client, self._SOCKS_REPLY_NOT_ALLOWED)
                return
            except OSError:
                if not self._stop.is_set():
                    self._send_reply(client, self._SOCKS_REPLY_GENERAL_FAILURE)
                return
            if connect_response != _BRIDGE_CONNECT_RESPONSE:
                self._send_reply(client, self._SOCKS_REPLY_GENERAL_FAILURE)
                return
            try:
                self._lease_check()
            except NetworkLeaseValidationError:
                self._send_reply(client, self._SOCKS_REPLY_NOT_ALLOWED)
                return
            client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            client.setblocking(False)
            proxy_socket.setblocking(False)
            self._relay(client, proxy_socket)
        finally:
            _close_bridge_socket(proxy_socket)
            self._forget_socket(proxy_socket)

    def _relay(self, client: socket.socket, proxy: socket.socket) -> None:
        peers = {client: proxy, proxy: client}
        outgoing = {client: bytearray(), proxy: bytearray()}
        read_open = {client: True, proxy: True}
        write_shutdown: set[socket.socket] = set()

        while not self._stop.is_set():
            try:
                self._lease_check()
            except NetworkLeaseValidationError:
                return
            for source, destination in peers.items():
                if (
                    not read_open[source]
                    and not outgoing[destination]
                    and destination not in write_shutdown
                ):
                    try:
                        destination.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    write_shutdown.add(destination)
            if not any(read_open.values()) and not any(outgoing.values()):
                return

            readable = [
                source for source in peers
                if read_open[source]
                and len(outgoing[peers[source]]) < _BRIDGE_RELAY_BUFFER_LIMIT_BYTES
            ]
            writable = [connection for connection, buffer in outgoing.items() if buffer]
            try:
                ready_to_read, ready_to_write, exceptional = select.select(
                    readable,
                    writable,
                    (client, proxy),
                    _BRIDGE_RELAY_POLL_SECONDS,
                )
            except (OSError, ValueError):
                return
            if exceptional:
                return
            for source in ready_to_read:
                destination = peers[source]
                available = _BRIDGE_RELAY_BUFFER_LIMIT_BYTES - len(outgoing[destination])
                try:
                    chunk = source.recv(min(_BRIDGE_RELAY_READ_CHUNK_BYTES, available))
                except BlockingIOError:
                    continue
                except OSError:
                    if self._stop.is_set():
                        return
                    try:
                        self._lease_check()
                    except NetworkLeaseValidationError:
                        return
                    raise
                if not chunk:
                    read_open[source] = False
                else:
                    outgoing[destination].extend(chunk)
            for destination in ready_to_write:
                buffer = outgoing[destination]
                try:
                    sent = destination.send(buffer)
                except BlockingIOError:
                    continue
                except OSError:
                    return
                if sent <= 0:
                    return
                del buffer[:sent]


def build_test_profile(base_profile: str, approved_socket_root: Path) -> str:
    """Append one path-scoped AF_UNIX connect grant to a deny-default profile."""

    if not isinstance(base_profile, str) or not base_profile:
        raise ValueError("base Seatbelt profile must be non-empty text")

    root = Path(approved_socket_root)
    raw_path = str(root)
    if not root.is_absolute():
        raise ValueError("approved AF_UNIX socket root must be absolute")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_path):
        raise ValueError("approved AF_UNIX socket root contains a control character")
    if any(part in {".", ".."} for part in root.parts):
        raise ValueError("approved AF_UNIX socket root must be normalized")

    quoted_path = raw_path.replace("\\", "\\\\").replace('"', '\\"')
    return (
        base_profile
        + '(allow file-read-metadata file-test-existence (subpath "'
        + quoted_path
        + '"))'
        + "(allow system-socket (socket-domain AF_UNIX))"
        + '(allow network-outbound (remote unix-socket (subpath "'
        + quoted_path
        + '")))'
    )
