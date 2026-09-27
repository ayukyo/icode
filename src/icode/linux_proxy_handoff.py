"""Fail-closed Linux receiver for a private loopback-listener FD handoff.

This module creates the private control channel, validates one received
listener and exposes an explicit host ACK. It does not start a proxy, relay
bytes, authorize destinations, or enable network access for an Agent or
sandboxed process.
"""

from __future__ import annotations

import array
import ipaddress
import math
import os
import selectors
import socket
import struct
import sys
import threading
import time
import weakref
from collections.abc import Callable

_HANDOFF_MESSAGE = b"ICODE_PROXY_LISTENER_V1"
_HANDOFF_ACK = b"ICODE_PROXY_LISTENER_ACK_V1"
_HANDOFF_NONCE_SIZE = 16
_MAX_RECEIVED_FDS = 4
_CREDENTIALS = struct.Struct("3i")
_HANDOFF_ERROR = "Linux proxy listener handoff is invalid"
_ACK_STATE_LOCK = threading.Lock()
_ACK_STATE: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


class ProxyHandoffError(ConnectionError):
    """Raised when the private channel or transferred listener is invalid."""


def _close_received_descriptors(descriptors) -> None:
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError:
            pass


def create_loopback_listener_handoff_channel() -> tuple[socket.socket, socket.socket]:
    """Create host/sender AF_UNIX seqpacket endpoints with peer credentials.

    The first returned endpoint stays with the trusted host receiver; the
    second may be inherited only by the trusted native helper. Both endpoints
    are non-inheritable unless an explicit subprocess ``pass_fds`` handoff is
    used.
    """

    if not sys.platform.startswith("linux"):
        raise ProxyHandoffError(_HANDOFF_ERROR)
    host_control: socket.socket | None = None
    sender_control: socket.socket | None = None
    try:
        host_control, sender_control = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_SEQPACKET,
        )
        host_control.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        os.set_inheritable(host_control.fileno(), False)
        os.set_inheritable(sender_control.fileno(), False)
        return host_control, sender_control
    except BaseException as exc:
        for endpoint in (sender_control, host_control):
            if endpoint is not None:
                try:
                    endpoint.close()
                except OSError:
                    pass
        if isinstance(exc, OSError):
            raise ProxyHandoffError(_HANDOFF_ERROR) from None
        raise


def _validate_control_socket(control: socket.socket) -> None:
    if (
        not isinstance(control, socket.socket)
        or control.fileno() < 0
        or control.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN)
        != socket.AF_UNIX
        or control.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
        != socket.SOCK_SEQPACKET
        or control.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1
    ):
        raise ProxyHandoffError(_HANDOFF_ERROR)


def _receive_message(
    control: socket.socket,
    *,
    timeout_seconds: float,
    descriptors: list[int],
    cancellation: threading.Event | None,
    accept_message: Callable[
        [bytes, list[tuple[int, int, int]], bool, int, object], None
    ],
) -> None:
    descriptor_bytes = array.array("i").itemsize * _MAX_RECEIVED_FDS
    ancillary_bytes = (
        socket.CMSG_SPACE(descriptor_bytes)
        + socket.CMSG_SPACE(_CREDENTIALS.size)
    )
    receive_flags = socket.MSG_CMSG_CLOEXEC | socket.MSG_DONTWAIT
    deadline = time.monotonic() + timeout_seconds
    with selectors.DefaultSelector() as selector:
        selector.register(control, selectors.EVENT_READ)
        while True:
            if cancellation is not None and cancellation.is_set():
                raise ProxyHandoffError(_HANDOFF_ERROR)
            remaining = max(0.0, deadline - time.monotonic())
            wait_seconds = (
                min(remaining, 0.05) if cancellation is not None else remaining
            )
            try:
                readable = selector.select(wait_seconds)
            except InterruptedError:
                continue
            if not readable:
                if cancellation is not None and cancellation.is_set():
                    raise ProxyHandoffError(_HANDOFF_ERROR)
                if remaining <= 0:
                    raise ProxyHandoffError(_HANDOFF_ERROR)
                continue
            try:
                payload, ancillary, flags, address = control.recvmsg(
                    len(_HANDOFF_MESSAGE) + _HANDOFF_NONCE_SIZE + 1,
                    ancillary_bytes,
                    receive_flags,
                )
            except (BlockingIOError, InterruptedError):
                continue

            # SCM_RIGHTS descriptors become this process's responsibility as
            # soon as recvmsg succeeds. This code runs off the main interpreter
            # thread, so Python signal exceptions cannot split FD registration.
            credentials, malformed = _parse_ancillary_data(
                ancillary,
                descriptors,
            )
            if cancellation is not None and cancellation.is_set():
                raise ProxyHandoffError(_HANDOFF_ERROR)
            accept_message(payload, credentials, malformed, flags, address)
            if cancellation is not None and cancellation.is_set():
                raise ProxyHandoffError(_HANDOFF_ERROR)
            return


def _parse_ancillary_data(
    ancillary: list[tuple[int, int, bytes]],
    descriptors: list[int],
) -> tuple[list[tuple[int, int, int]], bool]:
    credentials: list[tuple[int, int, int]] = []
    malformed = False
    descriptor_size = array.array("i").itemsize

    for level, kind, payload in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            complete_bytes = len(payload) - (len(payload) % descriptor_size)
            if complete_bytes != len(payload):
                malformed = True
            values = array.array("i")
            try:
                values.frombytes(payload[:complete_bytes])
                # The receiver allocates this cleanup list before recvmsg and
                # closes every copied descriptor in its finally block.
                descriptors.extend(values)
            except BaseException:
                # A runtime exception can occur after frombytes() makes the
                # descriptor numbers available but before list.extend().
                _close_received_descriptors(set(descriptors).union(values))
                descriptors.clear()
                raise
        elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
            if len(payload) != _CREDENTIALS.size:
                malformed = True
                continue
            credentials.append(_CREDENTIALS.unpack(payload))
        else:
            malformed = True

    return credentials, malformed


def _wrap_received_listener(descriptor: int) -> socket.socket:
    duplicate = os.dup(descriptor)
    try:
        listener = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
            fileno=duplicate,
        )
    except BaseException:
        os.close(duplicate)
        raise

    try:
        os.set_inheritable(listener.fileno(), False)
        domain = listener.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN)
        socket_type = listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
        accepting = listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
        address = listener.getsockname()
        if (
            domain != socket.AF_INET
            or socket_type != socket.SOCK_STREAM
            or accepting != 1
            or not isinstance(address, tuple)
            or len(address) != 2
            or not isinstance(address[1], int)
            or address[1] <= 0
            or address[1] > 65535
            or not ipaddress.IPv4Address(address[0]).is_loopback
        ):
            raise ProxyHandoffError(_HANDOFF_ERROR)
        return listener
    except BaseException:
        listener.close()
        raise


def _receive_loopback_listener_impl(
    control: socket.socket,
    *,
    expected_pid: int,
    timeout_seconds: float,
    cancellation: threading.Event | None,
) -> tuple[socket.socket, bytes]:
    if not sys.platform.startswith("linux"):
        raise ProxyHandoffError(_HANDOFF_ERROR)
    if (
        type(expected_pid) is not int
        or expected_pid <= 1
        or isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
    ):
        raise ProxyHandoffError(_HANDOFF_ERROR)
    if (
        timeout_seconds < 0
        or timeout_seconds > 30
        or not math.isfinite(timeout_seconds)
    ):
        raise ProxyHandoffError(_HANDOFF_ERROR)

    descriptors: list[int] = []
    listener_holder: list[socket.socket] = []
    nonce_holder: list[bytes] = []
    try:
        if cancellation is not None and cancellation.is_set():
            raise ProxyHandoffError(_HANDOFF_ERROR)
        _validate_control_socket(control)

        def validate_and_adopt(
            payload: bytes,
            credentials: list[tuple[int, int, int]],
            malformed: bool,
            flags: int,
            _address: object,
        ) -> None:
            if (
                flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC)
                or malformed
                or not payload.startswith(_HANDOFF_MESSAGE)
                or len(payload) != len(_HANDOFF_MESSAGE) + _HANDOFF_NONCE_SIZE
                or len(descriptors) != 1
                or len(credentials) != 1
                or credentials[0][0] != expected_pid
            ):
                raise ProxyHandoffError(_HANDOFF_ERROR)
            listener_holder.append(_wrap_received_listener(descriptors[0]))
            nonce_holder.append(payload[len(_HANDOFF_MESSAGE):])

        _receive_message(
            control,
            timeout_seconds=float(timeout_seconds),
            descriptors=descriptors,
            cancellation=cancellation,
            accept_message=validate_and_adopt,
        )
        return listener_holder.pop(), nonce_holder.pop()
    except ProxyHandoffError:
        raise
    except (OSError, OverflowError, TypeError, ValueError, struct.error):
        raise ProxyHandoffError(_HANDOFF_ERROR) from None
    finally:
        try:
            for listener in listener_holder:
                listener.close()
        finally:
            # Closing an adopted wrapper must not skip cleanup of the original
            # SCM_RIGHTS descriptors if that close itself raises.
            _close_received_descriptors(descriptors)


def receive_loopback_listener(
    control: socket.socket,
    *,
    expected_pid: int,
    timeout_seconds: float,
) -> socket.socket:
    """Receive one credential-bound IPv4 loopback TCP listener descriptor.

    ``expected_pid`` must be the host-visible PID of the trusted direct child
    that owns the sender endpoint. The main interpreter thread delegates
    receiving, validation and descriptor adoption to a private worker so
    Python signal handlers are never replaced and cannot interrupt FD
    ownership transfer. If a caller signal interrupts the wait, cancellation
    is set and a worker whose thread identity is published is joined before
    the signal is re-raised. If interruption occurs inside ``Thread.start()``
    before that identity is published, a delayed worker observes cancellation
    before touching the control socket. Calls already made on a worker thread
    run directly because Python signal exceptions are dispatched on the main
    interpreter thread.
    """

    if threading.current_thread() is not threading.main_thread():
        listener, nonce = _receive_loopback_listener_impl(
            control,
            expected_pid=expected_pid,
            timeout_seconds=timeout_seconds,
            cancellation=None,
        )
        try:
            _register_ack_state(listener, control, nonce)
        except BaseException:
            try:
                listener.close()
            except BaseException:
                pass
            raise
        return listener

    cancellation = threading.Event()
    outcome: list[tuple[socket.socket, bytes] | BaseException] = []

    def receive_on_worker() -> None:
        try:
            outcome.append(
                _receive_loopback_listener_impl(
                    control,
                    expected_pid=expected_pid,
                    timeout_seconds=timeout_seconds,
                    cancellation=cancellation,
                )
            )
        except BaseException as exc:
            outcome.append(exc)

    worker = threading.Thread(
        target=receive_on_worker,
        name="icode-proxy-fd-receiver",
        daemon=True,
    )
    pending_interrupt: BaseException | None = None
    active_exception: BaseException | None = None
    try:
        worker.start()
        while True:
            try:
                if not worker.is_alive():
                    break
                worker.join(timeout=0.05)
            except BaseException as exc:
                if pending_interrupt is None:
                    pending_interrupt = exc
                while True:
                    try:
                        cancellation.set()
                        break
                    except BaseException as cancel_exc:
                        if pending_interrupt is None:
                            pending_interrupt = cancel_exc

        if pending_interrupt is not None:
            raise pending_interrupt
        if len(outcome) != 1:
            raise ProxyHandoffError(_HANDOFF_ERROR)
        if isinstance(outcome[0], BaseException):
            raise outcome.pop()
    except BaseException as exc:
        # sys.exc_info() here would also expose an exception handled by the
        # caller around this function, falsely marking a successful call as
        # interrupted. Track only exceptions raised by this receiver frame.
        active_exception = exc
        raise
    finally:
        cleanup_exception: BaseException | None = None
        while True:
            try:
                cancellation.set()
                if worker.ident is not None:
                    worker.join(timeout=0.05)
                    if worker.is_alive():
                        continue
                if active_exception is None and cleanup_exception is None:
                    # Deliver the socket only inside the retry-protected region.
                    # If a signal lands while evaluating this return, retain
                    # ownership here and close it on the next cleanup pass.
                    listener, nonce = outcome[0]
                    _register_ack_state(listener, control, nonce)
                    return listener
                for value in outcome:
                    if isinstance(value, tuple):
                        listener, _nonce = value
                        _forget_ack_state(listener)
                        listener.close()
                break
            except BaseException as exc:
                # Repeated caller signals must not strand worker-owned FDs;
                # retain the first cleanup interruption for normal returns.
                if cleanup_exception is None:
                    cleanup_exception = exc
        if active_exception is None and cleanup_exception is not None:
            raise cleanup_exception


def _register_ack_state(
    listener: socket.socket,
    control: socket.socket,
    nonce: bytes,
) -> None:
    if len(nonce) != _HANDOFF_NONCE_SIZE:
        raise ProxyHandoffError(_HANDOFF_ERROR)
    with _ACK_STATE_LOCK:
        if listener in _ACK_STATE:
            raise ProxyHandoffError(_HANDOFF_ERROR)
        _ACK_STATE[listener] = (control, nonce)


def _forget_ack_state(listener: socket.socket) -> None:
    with _ACK_STATE_LOCK:
        _ACK_STATE.pop(listener, None)


def acknowledge_loopback_listener_handoff(
    control: socket.socket,
    listener: socket.socket,
) -> None:
    """Release a trusted helper only after the host has prepared its bridge.

    The caller must first successfully receive and validate the listener, then
    establish whatever host-side accept/bridge ownership is required, and only
    then send an ACK bound to this exact listener and its unpredictable
    per-handoff nonce. The listener must be the object returned by the matching
    successful receive call. An ACK is a one-way release; callers must
    terminate the helper if their surrounding startup operation is
    interrupted or fails.
    """

    if not sys.platform.startswith("linux"):
        raise ProxyHandoffError(_HANDOFF_ERROR)
    try:
        _validate_control_socket(control)
        if not isinstance(listener, socket.socket) or listener.fileno() < 0:
            raise ProxyHandoffError(_HANDOFF_ERROR)
        with _ACK_STATE_LOCK:
            state = _ACK_STATE.get(listener)
            if state is None or state[0] is not control:
                raise ProxyHandoffError(_HANDOFF_ERROR)
            del _ACK_STATE[listener]
        payload = _HANDOFF_ACK + state[1]
        acknowledged = control.send(
            payload,
            socket.MSG_DONTWAIT | socket.MSG_NOSIGNAL,
        )
    except ProxyHandoffError:
        raise
    except (OSError, TypeError, ValueError):
        raise ProxyHandoffError(_HANDOFF_ERROR) from None
    if acknowledged != len(payload):
        raise ProxyHandoffError(_HANDOFF_ERROR)
