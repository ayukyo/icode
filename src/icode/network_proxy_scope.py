"""Host-owned HTTPS CONNECT connection lifetimes; no listener or worker API.

The host runtime owns one lease expiry monitor for its authority. Per-lease
scopes register accepted client sockets before DNS, reuse the existing numeric
upstream connector, and close only their own local socket handles on shutdown.
This module intentionally does not implement a listener, CONNECT response, or
byte relay and does not enable sandbox networking.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Event, Lock, RLock

from .connect_request import parse_https_connect_request_head
from .network_connector import (
    AuthorizedHttpsConnection,
    NetworkConnectError,
    open_authorized_https_connection,
)
from .network_lease import (
    IssuedNetworkLease,
    NetworkLeaseAuthority,
    NetworkLeaseExpiryMonitor,
    NetworkLeaseValidationError,
    NetworkPurpose,
)
from .network_destination import Resolver
from .sandbox_policy import SandboxPolicy


_SCOPE_ERROR = "host HTTPS CONNECT scope is unavailable"


class HostConnectScopeError(ConnectionError):
    """Raised when the trusted host cannot establish a leased CONNECT scope."""


def _close_socket(sock: socket.socket) -> bool:
    """Close one locally owned socket and confirm its wrapper is detached."""

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        return False
    return sock.fileno() < 0


@dataclass(slots=True)
class AuthorizedHttpsTunnel:
    """One host-owned pair of registered endpoints; never expose to a worker."""

    client_socket: socket.socket = field(repr=False)
    upstream: AuthorizedHttpsConnection = field(repr=False)
    _authority: NetworkLeaseAuthority = field(repr=False)
    _client_handle: object = field(repr=False)
    _on_close: object = field(repr=False)
    _close_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def upstream_socket(self) -> socket.socket:
        """Return the registered upstream socket to trusted host code."""

        return self.upstream.upstream_socket

    def close(self) -> bool:
        """Close this tunnel's own endpoints without revoking sibling scopes."""

        with self._close_lock:
            if self._closed:
                return True
            client_closed = _close_socket(self.client_socket)
            try:
                upstream_closed = self.upstream.close() is True
            except NetworkConnectError:
                upstream_closed = False
            # A concurrent authority revoke/expiry may already own this entry.
            self._authority.release_active_connection(self._client_handle)
            if not client_closed or not upstream_closed:
                return False
            self._closed = True
        callback = self._on_close
        if callable(callback):
            callback(self)
        return True


class HostConnectRuntime:
    """Trusted runtime owner for one authority-wide expiry monitor.

    Callers must start this runtime before accepting or handling any proxy
    client. It owns scopes but creates no listener and is not passed to workers.
    """

    def __init__(
        self,
        authority: NetworkLeaseAuthority,
        *,
        sweep_interval_seconds: float = 0.1,
    ) -> None:
        if not isinstance(authority, NetworkLeaseAuthority):
            raise HostConnectScopeError(_SCOPE_ERROR)
        try:
            monitor = NetworkLeaseExpiryMonitor(
                authority,
                sweep_interval_seconds=sweep_interval_seconds,
            )
        except Exception:
            raise HostConnectScopeError(_SCOPE_ERROR) from None
        self._authority = authority
        self._monitor = monitor
        self._lock = RLock()
        self._scopes: dict[int, HostHttpsConnectScope] = {}
        self._started = False
        self._closing = False
        self._closed = False

    def start(self) -> None:
        """Start the single monitor before a trusted listener accepts clients."""

        with self._lock:
            if self._started or self._closing or self._closed:
                raise HostConnectScopeError(_SCOPE_ERROR)
            try:
                self._monitor.start()
            except Exception:
                raise HostConnectScopeError(_SCOPE_ERROR) from None
            self._started = self._monitor.running
            if not self._started or self._monitor.failure_count:
                self._closing = True
                self._monitor.stop()
                raise HostConnectScopeError(_SCOPE_ERROR)

    def create_scope(
        self,
        issued: IssuedNetworkLease,
        policy: SandboxPolicy,
        purpose: NetworkPurpose,
    ) -> HostHttpsConnectScope:
        """Create one non-worker scope bound to the exact signed lease."""

        if (
            not isinstance(issued, IssuedNetworkLease)
            or not isinstance(policy, SandboxPolicy)
            or type(purpose) is not NetworkPurpose
        ):
            raise HostConnectScopeError(_SCOPE_ERROR)
        with self._lock:
            if (
                not self._started
                or self._closing
                or self._closed
                or not self._monitor.running
                or self._monitor.failure_count
            ):
                raise HostConnectScopeError(_SCOPE_ERROR)
            scope = HostHttpsConnectScope(
                self,
                issued,
                policy,
                purpose,
            )
            self._scopes[id(scope)] = scope
            return scope

    def close(self) -> bool:
        """Stop children and the monitor after all in-flight connects finish.

        A ``False`` result means cleanup is not confirmed. In particular, a
        synchronous DNS lookup cannot be interrupted; the caller must retry
        ``close()`` after the in-flight ``open_connect()`` returns. The monitor
        remains active until a retry confirms that every scope has closed.
        """

        with self._lock:
            self._closing = True
            scopes = tuple(self._scopes.values())
        close_results = tuple(scope.close() for scope in scopes)
        scopes_closed = all(close_results)
        if not scopes_closed:
            return False
        if not self._monitor.stop():
            return False
        with self._lock:
            if self._scopes:
                return False
            self._closed = True
        return True

    @property
    def _healthy(self) -> bool:
        with self._lock:
            return (
                self._started
                and not self._closing
                and not self._closed
                and self._monitor.running
                and self._monitor.failure_count == 0
            )

    @contextmanager
    def healthy_guard(self) -> Iterator[None]:
        """Keep runtime shutdown and expiry-monitor health stable briefly."""

        with self._lock:
            if (
                not self._started
                or self._closing
                or self._closed
            ):
                raise HostConnectScopeError(_SCOPE_ERROR)
            try:
                with self._monitor.healthy_guard():
                    yield
            except NetworkLeaseValidationError:
                raise HostConnectScopeError(_SCOPE_ERROR) from None

    def _forget_scope(self, scope: HostHttpsConnectScope) -> None:
        with self._lock:
            if self._scopes.get(id(scope)) is scope:
                del self._scopes[id(scope)]


class HostHttpsConnectScope:
    """One lease-bound host scope managing its accepted and upstream sockets.

    ``open_connect`` takes ownership of the accepted client socket. The client
    is registered before DNS, and the existing connector owns upstream
    registration/promotion. Scope close signals in-flight work and closes only
    this scope's endpoints; explicit ``authority.revoke(policy)`` remains a
    separate, policy-wide operation.
    """

    def __init__(
        self,
        runtime: HostConnectRuntime,
        issued: IssuedNetworkLease,
        policy: SandboxPolicy,
        purpose: NetworkPurpose,
    ) -> None:
        self._runtime = runtime
        self._authority = runtime._authority
        self._issued = issued
        self._policy = policy
        self._purpose = purpose
        self._lock = RLock()
        self._cancel_event = Event()
        self._closed = False
        self._open_count = 0
        self._accepted_clients: dict[int, socket.socket] = {}
        self._pending_clients: dict[int, tuple[socket.socket, object]] = {}
        self._tunnels: dict[int, AuthorizedHttpsTunnel] = {}

    def register_accepted_client(self, client_socket: socket.socket) -> None:
        """Track an accepted proxy peer before reading any untrusted bytes."""

        if type(client_socket) is not socket.socket:
            raise HostConnectScopeError(_SCOPE_ERROR)
        with self._lock:
            if (
                self._closed
                or not self._runtime._healthy
                or id(client_socket) in self._accepted_clients
            ):
                _close_socket(client_socket)
                raise HostConnectScopeError(_SCOPE_ERROR)
            self._accepted_clients[id(client_socket)] = client_socket

    def release_accepted_client(self, client_socket: socket.socket) -> None:
        """Release a header-reading peer after ownership moves or it closes."""

        with self._lock:
            if self._accepted_clients.get(id(client_socket)) is client_socket:
                del self._accepted_clients[id(client_socket)]

    def verify_lease(self) -> None:
        """Recheck live scope authority while waiting for a CONNECT head."""

        with self._lock:
            if self._closed or not self._runtime._healthy:
                raise NetworkLeaseValidationError("host connection scope is closed")
        self._authority.verify_scope(
            self._issued,
            self._policy,
            purpose=self._purpose,
            now_monotonic_ns=time.monotonic_ns(),
        )

    @contextmanager
    def live_lease_guard(self) -> Iterator[None]:
        """Hold scope/runtime/authority state stable for a short release action.

        This is reserved for irreversible host-side publication such as the
        nonce ACK which releases a sandbox payload. The guarded body must be
        non-blocking; normal CONNECT processing continues to use
        ``verify_lease`` and its existing bounded cancellation paths.
        """

        with self._lock:
            if self._closed or self._cancel_event.is_set():
                raise NetworkLeaseValidationError(
                    "host connection scope is closed"
                )
            with self._runtime.healthy_guard():
                with self._authority.scope_guard(
                    self._issued,
                    self._policy,
                    purpose=self._purpose,
                    clock=time.monotonic_ns,
                ):
                    yield

    def open_connect(
        self,
        client_socket: socket.socket,
        request_head: bytes,
        *,
        resolver: Resolver | None = None,
    ) -> AuthorizedHttpsTunnel:
        """Authorize and connect one accepted client without exposing a listener."""

        if type(client_socket) is not socket.socket:
            raise HostConnectScopeError(_SCOPE_ERROR)
        with self._lock:
            if self._closed or not self._runtime._healthy:
                _close_socket(client_socket)
                raise HostConnectScopeError(_SCOPE_ERROR)
            self._open_count += 1

        client_handle: object | None = None
        upstream: AuthorizedHttpsConnection | None = None
        published = False
        try:
            if self._cancel_event.is_set():
                raise NetworkLeaseValidationError("host connection scope is closed")
            target = parse_https_connect_request_head(request_head)
            self._authority.verify_request(
                self._issued,
                self._policy,
                purpose=self._purpose,
                hostname=target.hostname,
                port=target.port,
                now_monotonic_ns=time.monotonic_ns(),
            )
            client_handle = self._authority.register_active_sockets(
                self._issued,
                self._policy,
                purpose=self._purpose,
                hostname=target.hostname,
                port=target.port,
                now_monotonic_ns=time.monotonic_ns(),
                sockets=(client_socket,),
                clock=time.monotonic_ns,
            )
            with self._lock:
                if self._closed or self._cancel_event.is_set():
                    raise NetworkLeaseValidationError(
                        "host connection scope is closed"
                    )
                self._accepted_clients.pop(id(client_socket), None)
                self._pending_clients[id(client_socket)] = (
                    client_socket,
                    client_handle,
                )

            upstream = open_authorized_https_connection(
                request_head,
                self._issued,
                self._policy,
                authority=self._authority,
                purpose=self._purpose,
                resolver=resolver,
                cancel_event=self._cancel_event,
            )
            if self._cancel_event.is_set() or not self._runtime._healthy:
                raise NetworkLeaseValidationError("host connection scope is closed")
            self._authority.verify_request(
                self._issued,
                self._policy,
                purpose=self._purpose,
                hostname=target.hostname,
                port=target.port,
                now_monotonic_ns=time.monotonic_ns(),
            )

            tunnel = AuthorizedHttpsTunnel(
                client_socket=client_socket,
                upstream=upstream,
                _authority=self._authority,
                _client_handle=client_handle,
                _on_close=self._forget_tunnel,
            )
            with self._lock:
                if self._closed or self._cancel_event.is_set():
                    raise NetworkLeaseValidationError(
                        "host connection scope is closed"
                    )
                self._pending_clients.pop(id(client_socket), None)
                self._tunnels[id(tunnel)] = tunnel
                published = True
            return tunnel
        except Exception:
            if upstream is not None:
                try:
                    upstream.close()
                except Exception:  # noqa: BLE001 - scope cleanup stays fail-closed.
                    pass
            if not published:
                _close_socket(client_socket)
                if client_handle is not None:
                    self._authority.release_active_connection(client_handle)
            raise HostConnectScopeError(_SCOPE_ERROR) from None
        except BaseException:
            if upstream is not None:
                try:
                    upstream.close()
                except Exception:  # noqa: BLE001 - preserve the original interruption.
                    pass
            if not published:
                _close_socket(client_socket)
                if client_handle is not None:
                    self._authority.release_active_connection(client_handle)
            raise
        finally:
            with self._lock:
                self._pending_clients.pop(id(client_socket), None)
                self._open_count -= 1

    def close(self) -> bool:
        """Close only this scope; never revoke siblings under the policy key.

        Return ``False`` while an in-flight DNS/connect operation or any socket
        close is unresolved. The trusted owner must retry after that operation
        returns; runtime shutdown stays fail-closed in the meantime.
        """

        with self._lock:
            self._closed = True
            self._cancel_event.set()
            accepted_clients = tuple(self._accepted_clients.values())
            pending_clients = tuple(self._pending_clients.values())
            tunnels = tuple(self._tunnels.values())
            self._pending_clients.clear()

        cleanup_ok = True
        for client_socket in accepted_clients:
            cleanup_ok = _close_socket(client_socket) and cleanup_ok
        for client_socket, handle in pending_clients:
            cleanup_ok = _close_socket(client_socket) and cleanup_ok
            self._authority.release_active_connection(handle)
        for tunnel in tunnels:
            cleanup_ok = tunnel.close() and cleanup_ok
        with self._lock:
            no_open_operations = self._open_count == 0
            no_accepted_clients = not self._accepted_clients
            no_tunnels = not self._tunnels
        if cleanup_ok and no_open_operations and no_accepted_clients and no_tunnels:
            self._runtime._forget_scope(self)
            return True
        return False

    def _forget_tunnel(self, tunnel: AuthorizedHttpsTunnel) -> None:
        with self._lock:
            if self._tunnels.get(id(tunnel)) is tunnel:
                del self._tunnels[id(tunnel)]
