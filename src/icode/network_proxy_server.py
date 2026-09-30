"""Host-owned CONNECT listener services for TCP and private Unix sockets.

This coordinator owns a trusted listener and every accepted client while it
reads one bounded CONNECT head, opens the existing lease-gated numeric
connection, and relays bytes. It is not exposed to Agent/ToolContext and does
not alter the deny-only worker sandbox policy. Calls to ``serve_once`` are
deliberately serialized; a caller that needs concurrency must provide a
separate, explicitly bounded owner rather than spawning unbounded handlers.
"""

from __future__ import annotations

import ipaddress
import math
import os
import select
import selectors
import socket
import stat
import sys
import threading
import time
from pathlib import Path
from threading import Lock, RLock

from .connect_request import MAX_CONNECT_REQUEST_HEAD_BYTES
from .network_destination import Resolver
from .network_lease import HTTPS_PORT, NetworkLeaseValidationError
from .network_proxy_scope import (
    AuthorizedHttpsTunnel,
    HostConnectScopeError,
    HostHttpsConnectScope,
)


_PROXY_ERROR = "host CONNECT proxy is unavailable"
_CONNECT_RESPONSE = b"HTTP/1.1 200 Connection Established\r\n\r\n"
_ACCEPT_POLL_SECONDS = 0.1
_CONNECT_HEAD_TIMEOUT_SECONDS = 5.0
_RELAY_POLL_SECONDS = 0.1
_RELAY_READ_CHUNK_BYTES = 64 * 1024
_RELAY_BUFFER_LIMIT_BYTES = 256 * 1024
_HEADER_TERMINATOR = b"\r\n\r\n"
_HANDOFF_READY_TIMEOUT_SECONDS = 2.0
_SESSION_JOIN_TIMEOUT_SECONDS = 4.0
_UNIX_SOCKET_PATH_MAX_BYTES = 103
_SOCKS5_VERSION = 5
_SOCKS5_METHOD_NO_AUTH = 0
_SOCKS5_COMMAND_CONNECT = 1
_SOCKS5_ADDRESS_DOMAIN = 3
_SOCKS5_REPLY_SUCCEEDED = 0
_SOCKS5_REP_GENERAL_FAILURE = 1
_SOCKS5_REP_NOT_ALLOWED = 2
_SOCKS5_REP_COMMAND_UNSUPPORTED = 7
_SOCKS5_REP_ADDRESS_UNSUPPORTED = 8
_SOCKS5_REP_NO_ACCEPTABLE_METHODS = 255


class HostConnectProxyError(ConnectionError):
    """Raised when the trusted host listener cannot complete a safe request."""


class _SocksRequestRejected(ValueError):
    """Internal bounded-protocol rejection with a SOCKS5 reply code."""

    def __init__(self, reply_code: int) -> None:
        super().__init__("SOCKS5 request is outside the supported contract")
        self.reply_code = reply_code


def _close_socket(sock: socket.socket) -> bool:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        return False
    return sock.fileno() < 0


def _relay_streams(
    scope: HostHttpsConnectScope,
    client_socket: socket.socket,
    upstream_socket: socket.socket,
) -> None:
    """Relay a lease tunnel with bounded buffers and bidirectional half-close."""

    peers = {
        client_socket: upstream_socket,
        upstream_socket: client_socket,
    }
    outgoing = {client_socket: bytearray(), upstream_socket: bytearray()}
    read_open = {client_socket: True, upstream_socket: True}
    write_shutdown: set[socket.socket] = set()
    next_lease_check = 0.0
    client_socket.setblocking(False)
    upstream_socket.setblocking(False)

    while True:
        now = time.monotonic()
        if now >= next_lease_check:
            scope.verify_lease()
            next_lease_check = now + _RELAY_POLL_SECONDS
        for source in (client_socket, upstream_socket):
            destination = peers[source]
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
            source
            for source in peers
            if read_open[source]
            and len(outgoing[peers[source]]) < _RELAY_BUFFER_LIMIT_BYTES
        ]
        writable = [sock for sock, buffer in outgoing.items() if buffer]
        try:
            ready_to_read, ready_to_write, exceptional = select.select(
                readable,
                writable,
                (client_socket, upstream_socket),
                max(0.0, next_lease_check - time.monotonic()),
            )
        except (OSError, ValueError):
            return
        if exceptional:
            return

        for source in ready_to_read:
            destination = peers[source]
            available = _RELAY_BUFFER_LIMIT_BYTES - len(outgoing[destination])
            try:
                chunk = source.recv(min(_RELAY_READ_CHUNK_BYTES, available))
            except BlockingIOError:
                continue
            if not chunk:
                read_open[source] = False
                continue
            outgoing[destination].extend(chunk)

        for destination in ready_to_write:
            buffer = outgoing[destination]
            try:
                sent = destination.send(buffer)
            except BlockingIOError:
                continue
            if sent <= 0:
                return
            del buffer[:sent]


class HostConnectProxyServer:
    """Own one validated non-blocking loopback listener and one scope.

    The listener socket is transferred to this object on successful
    construction. ``serve_once`` accepts a single loopback peer and remains
    occupied until that CONNECT tunnel closes. The caller controls which
    thread runs ``serve_once``/``serve_forever``; this class creates no worker
    threads and has no unbounded queue. The listener must be non-blocking
    before it is shared or handed off; this receiver never changes its shared
    open-file-description flags.
    """

    def __init__(
        self,
        listener_socket: socket.socket,
        scope: HostHttpsConnectScope,
    ) -> None:
        if type(listener_socket) is not socket.socket:
            raise HostConnectProxyError(_PROXY_ERROR)
        if not isinstance(scope, HostHttpsConnectScope):
            raise HostConnectProxyError(_PROXY_ERROR)
        try:
            address = listener_socket.getsockname()
            listening = listener_socket.getsockopt(
                socket.SOL_SOCKET,
                socket.SO_ACCEPTCONN,
            )
            socket_type = listener_socket.getsockopt(
                socket.SOL_SOCKET,
                socket.SO_TYPE,
            )
            loopback = ipaddress.ip_address(address[0]) == ipaddress.IPv4Address(
                "127.0.0.1",
            )
            # Python timeout mode also makes a POSIX FD O_NONBLOCK, but
            # accept() can still wait up to the wrapper timeout after stale
            # readiness. On POSIX, a received SCM_RIGHTS wrapper may report
            # None even though its shared FD is nonblocking; allow that safe
            # combination, but reject positive timeout mode. Windows cannot
            # query O_NONBLOCK for sockets, so require the wrapper's explicit
            # nonblocking mode there.
            listener_timeout = listener_socket.gettimeout()
            if os.name == "nt":
                listener_nonblocking = listener_timeout == 0.0
            else:
                listener_nonblocking = (
                    listener_timeout in (None, 0.0)
                    and not os.get_blocking(listener_socket.fileno())
                )
            valid_listener = (
                listener_socket.family == socket.AF_INET
                and socket_type == socket.SOCK_STREAM
                and listening == 1
                and loopback
                and listener_nonblocking
                and type(address[1]) is int
                and address[1] > 0
            )
            if not valid_listener:
                raise HostConnectProxyError(_PROXY_ERROR)
            listener_socket.set_inheritable(False)
            # SCM_RIGHTS shares open-file-description flags. Require the
            # creating/hand-off owner to set O_NONBLOCK before sharing, so a
            # readiness race cannot make accept() wait for a later client.
        except HostConnectProxyError:
            raise
        except (OSError, IndexError, TypeError, ValueError):
            raise HostConnectProxyError(_PROXY_ERROR) from None

        self._listener = listener_socket
        self._scope = scope
        self._lock = RLock()
        self._serve_lock = Lock()
        self._closed = False
        self._closed_event = threading.Event()
        self._serve_count = 0
        self._pending_clients: dict[int, socket.socket] = {}

    def serve_once(self, *, resolver: Resolver | None = None) -> bool:
        """Accept and relay one client; return false on poll timeout/shutdown.

        The request head is read byte-by-byte so bytes sent immediately after
        the terminator remain queued for the tunnel rather than being lost.
        Malformed, incomplete, expired, revoked, or unreachable requests are
        closed without returning a success response.
        """

        if not self._serve_lock.acquire(blocking=False):
            raise HostConnectProxyError(_PROXY_ERROR)
        with self._lock:
            if self._closed:
                self._serve_lock.release()
                return False
            self._serve_count += 1
            listener = self._listener

        client_socket: socket.socket | None = None
        tunnel: AuthorizedHttpsTunnel | None = None
        try:
            try:
                self._scope.verify_lease()
            except NetworkLeaseValidationError:
                self.close()
                return False
            try:
                readable, _writable, exceptional = select.select(
                    (listener,),
                    (),
                    (listener,),
                    _ACCEPT_POLL_SECONDS,
                )
                if exceptional:
                    raise OSError(_PROXY_ERROR)
                if not readable:
                    return False
                self._scope.verify_lease()
                with self._lock:
                    if self._closed:
                        return False
                client_socket, peer = listener.accept()
            except (BlockingIOError, ConnectionAbortedError):
                # Readiness may become stale if a peer resets before accept.
                # Because the listener is non-blocking, retry on the next poll.
                return False
            except (OSError, ValueError):
                with self._lock:
                    if self._closed:
                        return False
                # Persistent accept failures such as EMFILE can leave the
                # backlog readable. Back off without spinning, but let close()
                # wake this caller immediately.
                self._closed_event.wait(_ACCEPT_POLL_SECONDS)
                return False

            self._scope.register_accepted_client(client_socket)

            try:
                peer_is_loopback = (
                    ipaddress.ip_address(peer[0])
                    == ipaddress.IPv4Address("127.0.0.1")
                )
            except (IndexError, TypeError, ValueError):
                peer_is_loopback = False
            if not peer_is_loopback:
                _close_socket(client_socket)
                self._scope.release_accepted_client(client_socket)
                client_socket = None
                return True

            client_socket.settimeout(_CONNECT_HEAD_TIMEOUT_SECONDS)
            with self._lock:
                if self._closed:
                    _close_socket(client_socket)
                    self._scope.release_accepted_client(client_socket)
                    client_socket = None
                    return False
                self._pending_clients[id(client_socket)] = client_socket

            request_head = self._read_request_head(client_socket)
            tunnel = self._scope.open_connect(
                client_socket,
                request_head,
                resolver=resolver,
            )
            self._scope.verify_lease()
            if (
                tunnel.client_socket.fileno() < 0
                or tunnel.upstream_socket.fileno() < 0
            ):
                raise NetworkLeaseValidationError("host tunnel is no longer active")
            # The scope owns this client from this point, including the race
            # where close() runs between connect promotion and response send.
            with self._lock:
                self._pending_clients.pop(id(client_socket), None)
                if self._closed:
                    tunnel.close()
                    return True

            client_socket.sendall(_CONNECT_RESPONSE)
            self._relay(tunnel.client_socket, tunnel.upstream_socket)
            try:
                self._scope.verify_lease()
            except NetworkLeaseValidationError:
                self.close()
            return True
        except NetworkLeaseValidationError:
            self.close()
            if client_socket is not None:
                _close_socket(client_socket)
            return False
        except (HostConnectScopeError, OSError, ValueError):
            if client_socket is not None:
                _close_socket(client_socket)
            # Revocation closes relay sockets from another thread. That close
            # can surface as an I/O error before the normal post-relay lease
            # check, so revalidate before deciding the listener may survive.
            try:
                self._scope.verify_lease()
            except NetworkLeaseValidationError:
                self.close()
                return tunnel is not None
            # Once an authorized tunnel exists, this call already served its request.
            if tunnel is not None:
                return True
            # Shutdown before a request was authorized is the documented stop result.
            with self._lock:
                if self._closed:
                    return False
            return True
        except Exception:
            if client_socket is not None:
                _close_socket(client_socket)
            raise HostConnectProxyError(_PROXY_ERROR) from None
        finally:
            if tunnel is not None:
                tunnel.close()
            with self._lock:
                if client_socket is not None:
                    self._pending_clients.pop(id(client_socket), None)
                self._serve_count -= 1
            if client_socket is not None:
                self._scope.release_accepted_client(client_socket)
            self._serve_lock.release()

    def serve_forever(
        self,
        stop_event: threading.Event | None = None,
        *,
        resolver: Resolver | None = None,
        ready_event: threading.Event | None = None,
    ) -> None:
        """Run the serialized accept loop until stopped or this owner closes.

        ``ready_event`` is set only after the current lease/runtime has been
        verified. A host handoff owner can wait for it before acknowledging a
        sandbox payload; it does not grant the payload network access itself.
        """

        if stop_event is not None and type(stop_event) is not threading.Event:
            raise HostConnectProxyError(_PROXY_ERROR)
        if ready_event is not None and type(ready_event) is not threading.Event:
            raise HostConnectProxyError(_PROXY_ERROR)
        try:
            if ready_event is not None:
                self._scope.verify_lease()
                ready_event.set()
            while True:
                if stop_event is not None and stop_event.is_set():
                    return
                with self._lock:
                    if self._closed:
                        return
                self.serve_once(resolver=resolver)
        finally:
            self.close()

    def close(self) -> bool:
        """Close listener, pre-authorization clients, scope tunnels, and retry.

        A false return means an in-flight ``serve_once`` has not yet unwound;
        call again after its owner thread returns. This does not claim to join a
        caller-owned thread.
        """

        with self._lock:
            self._closed = True
            self._closed_event.set()
            listener = self._listener
            clients = tuple(self._pending_clients.values())

        listener_closed = listener.fileno() < 0 or _close_socket(listener)
        clients_closed = True
        for client in clients:
            clients_closed = _close_socket(client) and clients_closed
        scope_closed = self._scope.close()
        with self._lock:
            no_active_calls = self._serve_count == 0
        return listener_closed and clients_closed and scope_closed and no_active_calls

    def _read_request_head(self, client_socket: socket.socket) -> bytes:
        deadline = time.monotonic() + _CONNECT_HEAD_TIMEOUT_SECONDS
        next_lease_check = 0.0
        request_head = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(client_socket, selectors.EVENT_READ)
            while True:
                now = time.monotonic()
                if now >= next_lease_check:
                    self._scope.verify_lease()
                    now = time.monotonic()
                    next_lease_check = now + _RELAY_POLL_SECONDS
                with self._lock:
                    if self._closed:
                        raise HostConnectProxyError(_PROXY_ERROR)
                remaining = deadline - now
                if remaining <= 0:
                    raise TimeoutError(_PROXY_ERROR)
                events = selector.select(
                    timeout=min(
                        remaining,
                        max(0.0, next_lease_check - time.monotonic()),
                    ),
                )
                if not events:
                    continue
                chunk = client_socket.recv(1)
                if not chunk:
                    raise HostConnectProxyError(_PROXY_ERROR)
                request_head.extend(chunk)
                if len(request_head) > MAX_CONNECT_REQUEST_HEAD_BYTES:
                    raise HostConnectProxyError(_PROXY_ERROR)
                if request_head.endswith(_HEADER_TERMINATOR):
                    return bytes(request_head)

    def _relay(
        self,
        client_socket: socket.socket,
        upstream_socket: socket.socket,
    ) -> None:
        """Copy both directions through the shared bounded relay."""

        _relay_streams(self._scope, client_socket, upstream_socket)


class HostUnixSocks5ProxyServer:
    """Lease-bound SOCKS5 CONNECT service over one private AF_UNIX path.

    The caller creates a fresh mode-0700 directory owned by the effective UID
    and supplies a fresh socket path inside it. The sandbox profile should
    authorize only this exact path and must not grant the worker filesystem
    write access to the directory. The service itself accepts only SOCKS5
    no-auth CONNECT requests for a DNS hostname on TCP port 443. Each accepted
    stream is handed directly to the lease-bound scope, so no unauthenticated
    loopback TCP listener is exposed.

    Cleanup compares the endpoint's type, owner and inode before unlinking, but
    POSIX has no atomic "unlink this path only if it still names this inode"
    operation. A same-UID unsandboxed process can race that check; such
    processes are outside this API's trust boundary. The private directory and
    sandbox write denial protect against the worker and other UIDs, not against
    another process with the same UID.
    """

    def __init__(
        self,
        socket_path: str | os.PathLike[str],
        scope: HostHttpsConnectScope,
    ) -> None:
        if not isinstance(scope, HostHttpsConnectScope) or os.name != "posix":
            raise HostConnectProxyError(_PROXY_ERROR)
        if not hasattr(socket, "AF_UNIX"):
            raise HostConnectProxyError(_PROXY_ERROR)
        try:
            path = Path(socket_path)
            raw_path = os.fspath(path)
            encoded_path = os.fsencode(raw_path)
            parent_info = path.parent.lstat()
            valid_path = (
                path.is_absolute()
                and all(part not in {".", ".."} for part in path.parts)
                and not any(ord(char) < 32 or ord(char) == 127 for char in raw_path)
                and len(encoded_path) <= _UNIX_SOCKET_PATH_MAX_BYTES
                and path.parent.resolve(strict=True) == path.parent
                and stat.S_ISDIR(parent_info.st_mode)
                and not stat.S_ISLNK(parent_info.st_mode)
                and parent_info.st_uid == os.geteuid()
                and stat.S_IMODE(parent_info.st_mode) == 0o700
                and not os.path.lexists(path)
            )
            if not valid_path:
                raise HostConnectProxyError(_PROXY_ERROR)
            scope.verify_lease()
        except HostConnectProxyError:
            raise
        except (OSError, TypeError, ValueError):
            raise HostConnectProxyError(_PROXY_ERROR) from None

        self._socket_path = path
        self._socket_identity: tuple[int, int] | None = None
        self._listener: socket.socket | None = None
        self._scope = scope
        self._lock = RLock()
        self._serve_lock = Lock()
        self._closed_event = threading.Event()
        self._closed = False
        self._serve_count = 0
        self._pending_clients: dict[int, socket.socket] = {}

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(os.fspath(path))
            self._capture_socket_identity()
            os.chmod(path, 0o600, follow_symlinks=False)
            self._verify_owned_socket_path()
            listener.listen(4)
            listener.setblocking(False)
            listener.set_inheritable(False)
            scope.verify_lease()
            self._listener = listener
        except BaseException as error:
            try:
                listener.close()
            except OSError:
                pass
            self._remove_owned_socket_path()
            if isinstance(error, Exception):
                if isinstance(error, HostConnectProxyError):
                    raise
                raise HostConnectProxyError(_PROXY_ERROR) from None
            raise

    @property
    def socket_path(self) -> Path:
        """Return the exact filesystem endpoint for the sandbox profile."""

        return self._socket_path

    def serve_once(self, *, resolver: Resolver | None = None) -> bool:
        """Accept and process at most one bounded SOCKS5 client."""

        if not self._serve_lock.acquire(blocking=False):
            raise HostConnectProxyError(_PROXY_ERROR)
        with self._lock:
            if self._closed or self._listener is None:
                self._serve_lock.release()
                return False
            self._serve_count += 1
            listener = self._listener

        client_socket: socket.socket | None = None
        tunnel: AuthorizedHttpsTunnel | None = None
        try:
            try:
                self._scope.verify_lease()
                self._verify_owned_socket_path()
            except NetworkLeaseValidationError:
                self.close()
                return False
            except HostConnectProxyError:
                self.close()
                return False
            try:
                readable, _writable, exceptional = select.select(
                    (listener,),
                    (),
                    (listener,),
                    _ACCEPT_POLL_SECONDS,
                )
                if exceptional:
                    raise OSError(_PROXY_ERROR)
                if not readable:
                    return False
                self._scope.verify_lease()
                self._verify_owned_socket_path()
                with self._lock:
                    if self._closed:
                        return False
                client_socket, _address = listener.accept()
            except NetworkLeaseValidationError:
                self.close()
                return False
            except HostConnectProxyError:
                self.close()
                return False
            except (BlockingIOError, ConnectionAbortedError):
                return False
            except (OSError, ValueError):
                with self._lock:
                    if self._closed:
                        return False
                self._closed_event.wait(_ACCEPT_POLL_SECONDS)
                return False

            self._scope.register_accepted_client(client_socket)
            client_socket.setblocking(False)
            with self._lock:
                if self._closed:
                    _close_socket(client_socket)
                    self._scope.release_accepted_client(client_socket)
                    client_socket = None
                    return False
                self._pending_clients[id(client_socket)] = client_socket

            request_head = self._read_socks5_request(client_socket)
            if request_head is None:
                _close_socket(client_socket)
                return True
            tunnel = self._scope.open_unix_connect(
                client_socket,
                request_head,
                resolver=resolver,
            )
            self._scope.verify_lease()
            if (
                tunnel.client_socket.fileno() < 0
                or tunnel.upstream_socket.fileno() < 0
            ):
                raise NetworkLeaseValidationError("host tunnel is no longer active")
            with self._lock:
                self._pending_clients.pop(id(client_socket), None)
                if self._closed:
                    tunnel.close()
                    return True

            self._send_bytes(
                client_socket,
                b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00",
                deadline=time.monotonic() + _CONNECT_HEAD_TIMEOUT_SECONDS,
            )
            _relay_streams(
                self._scope,
                tunnel.client_socket,
                tunnel.upstream_socket,
            )
            return True
        except _SocksRequestRejected as error:
            if client_socket is not None:
                try:
                    self._send_socks_failure(client_socket, error.reply_code)
                except (HostConnectProxyError, OSError, NetworkLeaseValidationError):
                    pass
                _close_socket(client_socket)
            return True
        except NetworkLeaseValidationError:
            self.close()
            if client_socket is not None:
                _close_socket(client_socket)
            return False
        except (HostConnectScopeError, OSError, TimeoutError, ValueError):
            if client_socket is not None:
                _close_socket(client_socket)
            try:
                self._scope.verify_lease()
            except NetworkLeaseValidationError:
                self.close()
                return tunnel is not None
            with self._lock:
                if self._closed:
                    return False
            return tunnel is not None or client_socket is not None
        except Exception:
            if client_socket is not None:
                _close_socket(client_socket)
            raise HostConnectProxyError(_PROXY_ERROR) from None
        finally:
            if tunnel is not None:
                tunnel.close()
            with self._lock:
                if client_socket is not None:
                    self._pending_clients.pop(id(client_socket), None)
                self._serve_count -= 1
            if client_socket is not None:
                self._scope.release_accepted_client(client_socket)
            self._serve_lock.release()

    def serve_forever(
        self,
        stop_event: threading.Event | None = None,
        *,
        resolver: Resolver | None = None,
        ready_event: threading.Event | None = None,
    ) -> None:
        """Run the caller-owned serialized accept loop until stopped."""

        if stop_event is not None and type(stop_event) is not threading.Event:
            raise HostConnectProxyError(_PROXY_ERROR)
        if ready_event is not None and type(ready_event) is not threading.Event:
            raise HostConnectProxyError(_PROXY_ERROR)
        try:
            if ready_event is not None:
                self._scope.verify_lease()
                ready_event.set()
            while True:
                if stop_event is not None and stop_event.is_set():
                    return
                with self._lock:
                    if self._closed:
                        return
                self.serve_once(resolver=resolver)
        finally:
            self.close()

    def close(self) -> bool:
        """Close the endpoint, clients and lease scope; retry incomplete cleanup."""

        with self._lock:
            self._closed = True
            self._closed_event.set()
            listener = self._listener
            clients = tuple(self._pending_clients.values())

        listener_closed = listener is None or listener.fileno() < 0 or _close_socket(listener)
        clients_closed = True
        for client in clients:
            clients_closed = _close_socket(client) and clients_closed
        scope_closed = self._scope.close()
        path_removed = self._remove_owned_socket_path()
        with self._lock:
            no_active_calls = self._serve_count == 0
        return listener_closed and clients_closed and scope_closed and path_removed and no_active_calls

    def _capture_socket_identity(self) -> None:
        info = self._socket_path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            raise HostConnectProxyError(_PROXY_ERROR)
        self._socket_identity = (info.st_dev, info.st_ino)

    def _verify_owned_socket_path(self) -> None:
        try:
            info = self._socket_path.lstat()
            parent_info = self._socket_path.parent.lstat()
            parent_resolves_to_self = (
                self._socket_path.parent.resolve(strict=True)
                == self._socket_path.parent
            )
        except OSError:
            raise HostConnectProxyError(_PROXY_ERROR) from None
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or self._socket_identity != (info.st_dev, info.st_ino)
            or not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
            or stat.S_IMODE(parent_info.st_mode) != 0o700
            or not parent_resolves_to_self
        ):
            raise HostConnectProxyError(_PROXY_ERROR)

    def _remove_owned_socket_path(self) -> bool:
        if self._socket_identity is None:
            return True
        try:
            info = self._socket_path.lstat()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if (
            not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.geteuid()
            or self._socket_identity != (info.st_dev, info.st_ino)
        ):
            return False
        try:
            self._socket_path.unlink()
        except OSError:
            return False
        return True

    def _read_exact(
        self,
        client_socket: socket.socket,
        size: int,
        *,
        deadline: float,
    ) -> bytes:
        result = bytearray()
        while len(result) < size:
            self._scope.verify_lease()
            with self._lock:
                if self._closed:
                    raise HostConnectProxyError(_PROXY_ERROR)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(_PROXY_ERROR)
            try:
                readable, _writable, exceptional = select.select(
                    (client_socket,),
                    (),
                    (client_socket,),
                    min(_RELAY_POLL_SECONDS, remaining),
                )
            except (OSError, ValueError):
                raise HostConnectProxyError(_PROXY_ERROR) from None
            if exceptional:
                raise HostConnectProxyError(_PROXY_ERROR)
            if not readable:
                continue
            try:
                chunk = client_socket.recv(size - len(result))
            except BlockingIOError:
                continue
            if not chunk:
                raise HostConnectProxyError(_PROXY_ERROR)
            result.extend(chunk)
        return bytes(result)

    def _send_bytes(
        self,
        client_socket: socket.socket,
        payload: bytes,
        *,
        deadline: float,
    ) -> None:
        offset = 0
        while offset < len(payload):
            self._scope.verify_lease()
            with self._lock:
                if self._closed:
                    raise HostConnectProxyError(_PROXY_ERROR)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(_PROXY_ERROR)
            try:
                _readable, writable, exceptional = select.select(
                    (),
                    (client_socket,),
                    (client_socket,),
                    min(_RELAY_POLL_SECONDS, remaining),
                )
            except (OSError, ValueError):
                raise HostConnectProxyError(_PROXY_ERROR) from None
            if exceptional:
                raise HostConnectProxyError(_PROXY_ERROR)
            if not writable:
                continue
            try:
                sent = client_socket.send(payload[offset:])
            except BlockingIOError:
                continue
            if sent <= 0:
                raise HostConnectProxyError(_PROXY_ERROR)
            offset += sent

    def _send_socks_failure(
        self,
        client_socket: socket.socket,
        reply_code: int,
    ) -> None:
        self._send_bytes(
            client_socket,
            b"\x05" + bytes((reply_code,)) + b"\x00\x01\x00\x00\x00\x00\x00\x00",
            deadline=time.monotonic() + _RELAY_POLL_SECONDS,
        )

    def _read_socks5_request(
        self,
        client_socket: socket.socket,
    ) -> bytes | None:
        deadline = time.monotonic() + _CONNECT_HEAD_TIMEOUT_SECONDS
        version, method_count = self._read_exact(
            client_socket,
            2,
            deadline=deadline,
        )
        if version != _SOCKS5_VERSION or method_count == 0:
            raise _SocksRequestRejected(_SOCKS5_REP_NO_ACCEPTABLE_METHODS)
        methods = self._read_exact(
            client_socket,
            method_count,
            deadline=deadline,
        )
        if _SOCKS5_METHOD_NO_AUTH not in methods:
            self._send_bytes(
                client_socket,
                bytes((_SOCKS5_VERSION, _SOCKS5_REP_NO_ACCEPTABLE_METHODS)),
                deadline=deadline,
            )
            return None
        self._send_bytes(
            client_socket,
            bytes((_SOCKS5_VERSION, _SOCKS5_METHOD_NO_AUTH)),
            deadline=deadline,
        )

        version, command, reserved, address_type = self._read_exact(
            client_socket,
            4,
            deadline=deadline,
        )
        if version != _SOCKS5_VERSION or reserved != 0:
            raise _SocksRequestRejected(_SOCKS5_REP_GENERAL_FAILURE)
        if command != _SOCKS5_COMMAND_CONNECT:
            raise _SocksRequestRejected(_SOCKS5_REP_COMMAND_UNSUPPORTED)
        if address_type != _SOCKS5_ADDRESS_DOMAIN:
            raise _SocksRequestRejected(_SOCKS5_REP_ADDRESS_UNSUPPORTED)
        host_length = self._read_exact(
            client_socket,
            1,
            deadline=deadline,
        )[0]
        if host_length == 0:
            raise _SocksRequestRejected(_SOCKS5_REP_ADDRESS_UNSUPPORTED)
        hostname_bytes = self._read_exact(
            client_socket,
            host_length,
            deadline=deadline,
        )
        port = int.from_bytes(
            self._read_exact(client_socket, 2, deadline=deadline),
            "big",
        )
        if port != HTTPS_PORT:
            raise _SocksRequestRejected(_SOCKS5_REP_NOT_ALLOWED)
        try:
            hostname = hostname_bytes.decode("ascii")
            request_head = (
                f"CONNECT {hostname}:{HTTPS_PORT} HTTP/1.1\r\n"
                f"Host: {hostname}:{HTTPS_PORT}\r\n\r\n"
            ).encode("ascii")
        except UnicodeError:
            raise _SocksRequestRejected(_SOCKS5_REP_NOT_ALLOWED) from None
        return request_head


class LinuxHostConnectProxySession:
    """Own one Linux listener handoff and its lease-bound host proxy loop.

    The caller starts the trusted sandbox helper and retains responsibility
    for stopping that process. This owner receives its authenticated listener,
    starts a healthy accept loop, and only then sends the nonce-bound ACK that
    releases the helper payload. The session consumes the host control socket
    and scope once ``start()`` begins; failures close both without ACK.
    """

    def __init__(
        self,
        control_socket: socket.socket,
        *,
        expected_pid: int,
        scope: HostHttpsConnectScope,
        handoff_timeout_seconds: float = 5.0,
        ready_timeout_seconds: float = _HANDOFF_READY_TIMEOUT_SECONDS,
    ) -> None:
        if (
            type(control_socket) is not socket.socket
            or control_socket.fileno() < 0
            or type(expected_pid) is not int
            or expected_pid <= 1
            or not isinstance(scope, HostHttpsConnectScope)
            or isinstance(handoff_timeout_seconds, bool)
            or not isinstance(handoff_timeout_seconds, (int, float))
            or not 0 <= handoff_timeout_seconds <= 30
            or not math.isfinite(handoff_timeout_seconds)
            or isinstance(ready_timeout_seconds, bool)
            or not isinstance(ready_timeout_seconds, (int, float))
            or not 0 < ready_timeout_seconds <= 10
            or not math.isfinite(ready_timeout_seconds)
        ):
            raise HostConnectProxyError(_PROXY_ERROR)

        self._control = control_socket
        self._expected_pid = expected_pid
        self._scope = scope
        self._handoff_timeout_seconds = float(handoff_timeout_seconds)
        self._ready_timeout_seconds = float(ready_timeout_seconds)
        self._lock = RLock()
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._server: HostConnectProxyServer | None = None
        self._thread: threading.Thread | None = None
        self._serve_failure: BaseException | None = None
        self._start_attempted = False
        self._starting = False
        self._closing = False
        self._closed = False
        self._acknowledged = False

    @property
    def ready(self) -> bool:
        """Whether a live accept loop has verified the lease/runtime."""

        with self._lock:
            return (
                self._ready_event.is_set()
                and self._thread is not None
                and self._thread.is_alive()
                and self._serve_failure is None
                and not self._closing
                and not self._closed
            )

    @property
    def acknowledged(self) -> bool:
        """Whether the receiver successfully sent the helper's release ACK."""

        with self._lock:
            return self._acknowledged

    def start(self) -> None:
        """Receive, prepare and acknowledge exactly one helper listener."""

        if not sys.platform.startswith("linux"):
            raise HostConnectProxyError(_PROXY_ERROR)
        with self._lock:
            if self._start_attempted or self._closing or self._closed:
                raise HostConnectProxyError(_PROXY_ERROR)
            self._start_attempted = True
            self._starting = True

        listener: socket.socket | None = None
        try:
            from .linux_proxy_handoff import (
                acknowledge_loopback_listener_handoff,
                receive_loopback_listener,
            )

            listener = receive_loopback_listener(
                self._control,
                expected_pid=self._expected_pid,
                timeout_seconds=self._handoff_timeout_seconds,
            )
            server = HostConnectProxyServer(listener, self._scope)
            with self._lock:
                if self._closing:
                    raise HostConnectProxyError(_PROXY_ERROR)
                self._server = server
                listener = None  # Ownership transferred to the server.

            def serve() -> None:
                try:
                    server.serve_forever(
                        self._stop_event,
                        ready_event=self._ready_event,
                    )
                except BaseException as exc:
                    with self._lock:
                        self._serve_failure = exc

            thread = threading.Thread(
                target=serve,
                name="icode-host-connect-proxy",
                daemon=True,
            )
            with self._lock:
                self._thread = thread
            thread.start()

            deadline = time.monotonic() + self._ready_timeout_seconds
            while not self._ready_event.is_set():
                if not thread.is_alive():
                    raise HostConnectProxyError(_PROXY_ERROR)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HostConnectProxyError(_PROXY_ERROR)
                self._ready_event.wait(min(0.05, remaining))
            if not thread.is_alive():
                raise HostConnectProxyError(_PROXY_ERROR)
            with self._scope.live_lease_guard():
                with self._lock:
                    if self._closing or self._closed or not self.ready:
                        raise HostConnectProxyError(_PROXY_ERROR)
                    acknowledge_loopback_listener_handoff(
                        self._control, server._listener,
                    )
                    self._acknowledged = True
                    self._starting = False
        except BaseException as exc:
            if listener is not None:
                try:
                    listener.close()
                except BaseException:
                    pass
            with self._lock:
                self._starting = False
            try:
                self.close()
            except BaseException:
                # The startup failure remains primary. ``close`` retries its
                # own interrupted operations; callers may retry if it returns
                # incomplete on the next explicit cleanup attempt.
                pass
            if isinstance(exc, Exception):
                raise HostConnectProxyError(_PROXY_ERROR) from None
            raise

    def close(self) -> bool:
        """Stop the accept loop, close its scope and release the control FD.

        The helper process is caller-owned and must be stopped by its launcher.
        A false result means the serving thread or scope still has in-flight
        work; retry after its owner returns (for example after synchronous DNS
        resolution finishes).
        """

        with self._lock:
            self._closing = True
            self._stop_event.set()
            if self._starting:
                return False
            server = self._server
            thread = self._thread

        pending_interrupt: BaseException | None = None

        def remember_interrupt(exc: BaseException) -> None:
            nonlocal pending_interrupt
            if pending_interrupt is None:
                pending_interrupt = exc

        server_closed = True
        if server is not None:
            try:
                server_closed = server.close()
            except BaseException as exc:
                remember_interrupt(exc)
                server_closed = False
        if thread is not None and thread is not threading.current_thread():
            deadline = time.monotonic() + _SESSION_JOIN_TIMEOUT_SECONDS
            while thread.is_alive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    thread.join(timeout=min(0.05, remaining))
                except BaseException as exc:
                    # Preserve caller interruption but keep retrying the
                    # bounded join so it cannot strand the listener owner.
                    remember_interrupt(exc)
        thread_stopped = thread is None or not thread.is_alive()
        if server is not None:
            try:
                server_closed = server.close()
            except BaseException as exc:
                remember_interrupt(exc)
                server_closed = False
        try:
            scope_closed = self._scope.close()
        except BaseException as exc:
            remember_interrupt(exc)
            scope_closed = False

        control_closed = self._control.fileno() < 0
        for _attempt in range(3):
            if control_closed:
                break
            try:
                self._control.close()
                control_closed = self._control.fileno() < 0
            except BaseException as exc:
                remember_interrupt(exc)
                control_closed = self._control.fileno() < 0

        closed = server_closed and scope_closed and thread_stopped and control_closed
        with self._lock:
            self._closed = closed
        if pending_interrupt is not None:
            raise pending_interrupt
        return closed
