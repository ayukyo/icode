"""Test-only Seatbelt profile composition for AF_UNIX policy probes.

This module is deliberately outside the production sandbox path. Its profile
grant is limited to connecting to AF_UNIX sockets below one approved root.
"""

from __future__ import annotations

from pathlib import Path
import re
import socket
import threading
from urllib.parse import quote


_CURL_VERSION_RE = re.compile(r"^curl\s+(\d+)\.(\d+)\.(\d+)(?:\s|$)")
_MACOS_SUN_PATH_BYTES = 103


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
