"""Host-owned HTTPS CONNECT dialing, still separate from any worker network path.

This module validates the lease before DNS, dials only a validated numeric
sockaddr, registers a close callback before ``connect()``, and verifies the
lease again after the TCP handshake. It is not an HTTP listener or relay and
does not grant network access to an Agent or sandboxed process.
"""

from __future__ import annotations

import errno
import selectors
import socket
import threading
import time
from dataclasses import dataclass, field
from threading import Event, Lock

from .connect_request import HttpsConnectTarget, parse_https_connect_request_head
from .network_destination import (
    NetworkDestinationError,
    ResolvedNetworkTarget,
    Resolver,
    resolve_public_tcp_targets,
)
from .network_lease import (
    IssuedNetworkLease,
    NetworkLeaseAuthority,
    NetworkLeaseValidationError,
    NetworkPurpose,
)
from .sandbox_policy import SandboxPolicy


UPSTREAM_CONNECT_TIMEOUT_SECONDS = 10.0
PENDING_SOCKET_CLOSE_WAIT_SECONDS = 4.0
CONNECT_SELECTOR_POLL_INTERVAL_SECONDS = 0.1
_CONNECT_FAILED = "authorized HTTPS connection failed"
_CONNECT_IN_PROGRESS_CODES = frozenset(
    code
    for code in (
        errno.EINPROGRESS,
        errno.EWOULDBLOCK,
        errno.EALREADY,
        errno.EINTR,
        getattr(errno, "WSAEWOULDBLOCK", None),
        getattr(errno, "WSAEINPROGRESS", None),
        getattr(errno, "WSAEALREADY", None),
        getattr(socket, "WSAEWOULDBLOCK", None),
        getattr(socket, "WSAEINPROGRESS", None),
        getattr(socket, "WSAEALREADY", None),
    )
    if isinstance(code, int)
)
_CONNECT_ALREADY_CONNECTED = getattr(errno, "EISCONN", 0)


class NetworkConnectError(ConnectionError):
    """Raised when the host cannot complete an authorized HTTPS TCP dial."""


def _new_tcp_socket(
    family: int,
    socket_type: int,
    protocol: int,
) -> socket.socket:
    """Create a host-owned socket using the exact validated resolver family."""

    return socket.socket(family, socket_type, protocol)


def _close_socket(sock: socket.socket) -> bool:
    """Close one connector-owned socket and confirm the wrapper is detached."""

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        # An unconnected socket or a peer shutdown is still closed below.
        pass
    try:
        sock.close()
    except OSError:
        return False
    return sock.fileno() < 0


def _close_descriptor(sock: socket.socket) -> bool:
    """Close an owned wakeup descriptor without changing peer state."""

    try:
        sock.close()
    except OSError:
        return False
    return sock.fileno() < 0


class _PendingConnectCancelled(Exception):
    """Internal signal that the authority revoked a pending numeric dial."""


class _PendingDial:
    """Keep pending socket and selector ownership on the dialing thread.

    Revocation only sets a persistent flag and writes to a socketpair. The
    dialing owner unregisters from its selector by leaving the wait and closes
    the socket itself; cross-thread close is deliberately not used as a wakeup.
    """

    def __init__(
        self,
        sock: socket.socket,
        cancel_event: Event | None = None,
    ) -> None:
        self.socket = sock
        self._cancel_event = cancel_event
        self._owner_thread_id = threading.get_ident()
        self._state_lock = Lock()
        self._cancelled = False
        self._closed = Event()
        wakeup_reader, wakeup_writer = socket.socketpair()
        try:
            wakeup_reader.setblocking(False)
            wakeup_writer.setblocking(False)
        except BaseException:
            for wakeup_socket in (wakeup_reader, wakeup_writer):
                try:
                    _close_descriptor(wakeup_socket)
                except Exception:  # noqa: BLE001 - preserve the setup failure.
                    pass
            raise
        self._wakeup_reader = wakeup_reader
        self._wakeup_writer = wakeup_writer

    @property
    def wakeup_reader(self) -> socket.socket:
        return self._wakeup_reader

    @property
    def cancelled(self) -> bool:
        with self._state_lock:
            return self._cancelled or (
                self._cancel_event is not None and self._cancel_event.is_set()
            )

    def close_for_authority(self) -> bool:
        """Wake the owner and wait for confirmed socket closure."""

        if threading.get_ident() == self._owner_thread_id:
            with self._state_lock:
                self._cancelled = True
                return self._close_on_owner_locked()

        with self._state_lock:
            if self._closed.is_set():
                return self._all_descriptors_closed()
            self._cancelled = True
            try:
                self._wakeup_writer.send(b"x")
            except (BlockingIOError, OSError):
                # A full wakeup socket is already readable. The persistent flag
                # is also checked after every bounded selector wait.
                pass

        if not self._closed.wait(timeout=PENDING_SOCKET_CLOSE_WAIT_SECONDS):
            return False
        return self._all_descriptors_closed()

    def close_on_owner(self) -> bool:
        """Close a failed/cancelled attempt from its sole socket owner."""

        if threading.get_ident() != self._owner_thread_id:
            return False
        with self._state_lock:
            self._cancelled = True
            return self._close_on_owner_locked()

    def finish_connected(self) -> bool:
        """Drop only the temporary wakeup pair after successful promotion."""

        if threading.get_ident() != self._owner_thread_id:
            return False
        with self._state_lock:
            if (
                self._cancelled
                or (
                    self._cancel_event is not None
                    and self._cancel_event.is_set()
                )
                or self._closed.is_set()
            ):
                return False
            return self._close_wakeup_pair_locked()

    def close_wakeup_on_owner(self) -> bool:
        """Retry closing temporary wakeup descriptors during final cleanup."""

        if threading.get_ident() != self._owner_thread_id:
            return False
        with self._state_lock:
            return self._close_wakeup_pair_locked()

    def _close_on_owner_locked(self) -> bool:
        socket_closed = self._closed.is_set() or _close_socket(self.socket)
        wakeup_closed = self._close_wakeup_pair_locked()
        if socket_closed and wakeup_closed:
            self._closed.set()
            return True
        return False

    def _close_wakeup_pair_locked(self) -> bool:
        reader_closed = self._wakeup_reader.fileno() < 0 or _close_descriptor(
            self._wakeup_reader,
        )
        writer_closed = self._wakeup_writer.fileno() < 0 or _close_descriptor(
            self._wakeup_writer,
        )
        return reader_closed and writer_closed

    def _all_descriptors_closed(self) -> bool:
        return (
            self.socket.fileno() < 0
            and self._wakeup_reader.fileno() < 0
            and self._wakeup_writer.fileno() < 0
        )


def _connect_numeric(
    sock: socket.socket,
    sockaddr: tuple[object, ...],
    pending: _PendingDial,
) -> None:
    """Start a non-blocking numeric dial and wait for connect or cancellation."""

    if pending.cancelled:
        raise _PendingConnectCancelled

    sock.setblocking(False)
    if pending.cancelled:
        raise _PendingConnectCancelled
    result = sock.connect_ex(sockaddr)
    if result == 0 or result == _CONNECT_ALREADY_CONNECTED:
        if pending.cancelled:
            raise _PendingConnectCancelled
        return
    if result not in _CONNECT_IN_PROGRESS_CODES:
        raise OSError(result, "numeric connect failed")

    deadline = time.monotonic() + UPSTREAM_CONNECT_TIMEOUT_SECONDS
    with selectors.DefaultSelector() as selector:
        selector.register(sock, selectors.EVENT_WRITE, "socket")
        selector.register(pending.wakeup_reader, selectors.EVENT_READ, "cancel")
        while True:
            if pending.cancelled:
                raise _PendingConnectCancelled
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(_CONNECT_FAILED)

            events = selector.select(
                timeout=min(remaining, CONNECT_SELECTOR_POLL_INTERVAL_SECONDS),
            )
            if pending.cancelled:
                raise _PendingConnectCancelled
            if not events:
                continue

            if any(key.data == "cancel" for key, _mask in events):
                raise _PendingConnectCancelled
            if any(key.data == "socket" for key, _mask in events):
                # Write readiness means connect completion or failure; SO_ERROR
                # is the authoritative result on POSIX and Winsock selectors.
                socket_error = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if socket_error == 0:
                    if pending.cancelled:
                        raise _PendingConnectCancelled
                    return
                raise OSError(socket_error, "numeric connect failed")


@dataclass(slots=True)
class AuthorizedHttpsConnection:
    """One registered host-side upstream socket; never serialize to a worker."""

    target: HttpsConnectTarget
    sockaddr: tuple[object, ...]
    _socket: socket.socket = field(repr=False)
    _authority: NetworkLeaseAuthority = field(repr=False)
    _handle: object = field(repr=False)
    _close_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def upstream_socket(self) -> socket.socket:
        """Return the live socket to trusted host relay code only."""

        with self._close_lock:
            if self._closed or self._socket.fileno() < 0:
                raise NetworkConnectError(_CONNECT_FAILED)
            return self._socket

    def close(self) -> bool:
        """Close normally and release the authority entry; safe to repeat."""

        with self._close_lock:
            if self._closed:
                return True
            if not _close_socket(self._socket):
                raise NetworkConnectError(_CONNECT_FAILED)
            self._closed = True
            # A concurrent revoke may already have closed and removed this handle.
            self._authority.release_active_connection(self._handle)
            return True

    def _close_from_authority(self) -> bool:
        """Serialize revoke/expiry teardown with normal host-side closure."""

        with self._close_lock:
            if self._closed:
                return self._socket.fileno() < 0
            if not _close_socket(self._socket):
                return False
            self._closed = True
            return True

    def __enter__(self) -> AuthorizedHttpsConnection:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def open_authorized_https_connection(
    request_head: bytes,
    issued: IssuedNetworkLease,
    policy: SandboxPolicy,
    *,
    authority: NetworkLeaseAuthority,
    purpose: NetworkPurpose,
    resolver: Resolver | None = None,
    cancel_event: Event | None = None,
) -> AuthorizedHttpsConnection:
    """Open one leased HTTPS target through a pinned numeric TCP address.

    The lease is checked before DNS and again after DNS. For each resolved
    numeric address, a pending cancellation callback is registered before
    non-blocking ``connect_ex``. Revocation wakes the selector; its owner closes
    the candidate socket before confirming cancellation. A successful handshake
    is revalidated and promoted before a connection object is returned. DNS uses
    the synchronous system resolver and cannot be interrupted by this function;
    the post-DNS check prevents use of a result after authorization changes.
    This function is synchronous: the caller thread owns the selector and waits
    for each candidate dial, while another thread may request cancellation via
    the authority callback and socketpair wakeup.

    The resolver override is passed through the same public-address validator;
    it is intended for trusted host configuration and tests, never worker input.
    """

    if not isinstance(authority, NetworkLeaseAuthority):
        raise NetworkConnectError(_CONNECT_FAILED)
    if cancel_event is not None and type(cancel_event) is not Event:
        raise NetworkConnectError(_CONNECT_FAILED)

    try:
        if cancel_event is not None and cancel_event.is_set():
            raise NetworkLeaseValidationError("host connection scope is closed")
        target = parse_https_connect_request_head(request_head)
        authority.verify_request(
            issued,
            policy,
            purpose=purpose,
            hostname=target.hostname,
            port=target.port,
            now_monotonic_ns=time.monotonic_ns(),
        )
        destinations = resolve_public_tcp_targets(
            target.hostname,
            target.port,
            resolver=resolver,
        )
        if cancel_event is not None and cancel_event.is_set():
            raise NetworkLeaseValidationError("host connection scope is closed")
        if type(destinations) is not tuple or not destinations or any(
            type(destination) is not ResolvedNetworkTarget
            for destination in destinations
        ):
            raise NetworkDestinationError("resolver returned an invalid result")
        # DNS can take time; never use its result if the lease changed meanwhile.
        authority.verify_request(
            issued,
            policy,
            purpose=purpose,
            hostname=target.hostname,
            port=target.port,
            now_monotonic_ns=time.monotonic_ns(),
        )
        if cancel_event is not None and cancel_event.is_set():
            raise NetworkLeaseValidationError("host connection scope is closed")
    except Exception as error:  # noqa: BLE001 - connector failures are fail-closed.
        raise NetworkConnectError(_CONNECT_FAILED) from None

    for destination in destinations:
        sock: socket.socket | None = None
        pending: _PendingDial | None = None
        handle: object | None = None
        active_connection: AuthorizedHttpsConnection | None = None
        try:
            # A previous numeric address may have failed. Reauthorize before each
            # new attempt; registration revalidates under the authority lock.
            authority.verify_request(
                issued,
                policy,
                purpose=purpose,
                hostname=target.hostname,
                port=target.port,
                now_monotonic_ns=time.monotonic_ns(),
            )
            if cancel_event is not None and cancel_event.is_set():
                raise NetworkLeaseValidationError("host connection scope is closed")
            sock = _new_tcp_socket(
                destination.family,
                destination.socket_type,
                destination.protocol,
            )
            pending = _PendingDial(sock, cancel_event=cancel_event)
            handle = authority.register_active_connection(
                issued,
                policy,
                purpose=purpose,
                hostname=target.hostname,
                port=target.port,
                now_monotonic_ns=time.monotonic_ns(),
                close=pending.close_for_authority,
                pending=True,
                clock=time.monotonic_ns,
            )
            _connect_numeric(sock, destination.sockaddr, pending)
            if pending.cancelled:
                raise _PendingConnectCancelled
            # The establishment phase is non-blocking; trusted relay code gets
            # a normal blocking socket after successful connection promotion.
            sock.setblocking(True)
            authority.verify_request(
                issued,
                policy,
                purpose=purpose,
                hostname=target.hostname,
                port=target.port,
                now_monotonic_ns=time.monotonic_ns(),
            )
            if pending.cancelled:
                raise _PendingConnectCancelled
            candidate_connection = AuthorizedHttpsConnection(
                target=target,
                sockaddr=destination.sockaddr,
                _socket=sock,
                _authority=authority,
                _handle=handle,
            )
            if not authority.promote_active_connection(
                handle,
                now_monotonic_ns=time.monotonic_ns(),
                close=candidate_connection._close_from_authority,
            ):
                raise NetworkLeaseValidationError(
                    "network connection could not be promoted"
                )
            active_connection = candidate_connection
            if not pending.finish_connected() or sock.fileno() < 0:
                raise NetworkConnectError(_CONNECT_FAILED)
            if pending.cancelled:
                raise _PendingConnectCancelled
            return candidate_connection
        except NetworkLeaseValidationError:
            _cleanup_attempt(
                sock, pending, authority, handle, active_connection,
            )
            raise NetworkConnectError(_CONNECT_FAILED) from None
        except _PendingConnectCancelled:
            _cleanup_attempt(
                sock, pending, authority, handle, active_connection,
            )
            raise NetworkConnectError(_CONNECT_FAILED) from None
        except NetworkConnectError:
            _cleanup_attempt(
                sock, pending, authority, handle, active_connection,
            )
            raise NetworkConnectError(_CONNECT_FAILED) from None
        except (OSError, NetworkDestinationError):
            if not _cleanup_attempt(
                sock, pending, authority, handle, active_connection,
            ):
                raise NetworkConnectError(_CONNECT_FAILED) from None
            continue
        except Exception as error:  # noqa: BLE001 - unexpected host failures deny.
            _cleanup_attempt(
                sock, pending, authority, handle, active_connection,
            )
            raise NetworkConnectError(_CONNECT_FAILED) from None
        except BaseException:
            # Preserve process-level interruptions, but do not leave a pending
            # authority entry or selector/socket resources behind if a caller
            # catches KeyboardInterrupt or another BaseException.
            _cleanup_attempt(
                sock, pending, authority, handle, active_connection,
            )
            raise

    raise NetworkConnectError(_CONNECT_FAILED) from None


def _cleanup_attempt(
    sock: socket.socket | None,
    pending: _PendingDial | None,
    authority: NetworkLeaseAuthority,
    handle: object | None,
    active_connection: AuthorizedHttpsConnection | None,
) -> bool:
    """Close an unpublished candidate before releasing its authority entry."""

    if active_connection is not None:
        try:
            connection_closed = active_connection.close()
        except NetworkConnectError:
            connection_closed = False
        wakeup_descriptors_closed = (
            pending is None or pending.close_wakeup_on_owner()
        )
        return connection_closed and wakeup_descriptors_closed
    if pending is not None:
        closed = pending.close_on_owner()
    elif sock is not None:
        closed = _close_socket(sock)
    else:
        closed = True
    if closed and handle is not None:
        authority.release_active_connection(handle)
    return closed
