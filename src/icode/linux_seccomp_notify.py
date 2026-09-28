"""Linux seccomp USER_NOTIF broker for native command denial receipts.

The module is intentionally Linux-only. It never continues a notified syscall:
every observed event is answered with EPERM, and observer failure terminates the
trusted helper so the payload cannot outlive an incomplete monitor.
"""

from __future__ import annotations

import array
import ctypes
import errno
import fcntl
import os
import platform
import select
import socket
import struct
import sys
import threading
import time

_HANDOFF_MESSAGE = b"ICODE_SECCOMP_LISTENER_V1"
_HANDOFF_ACK = b"ICODE_SECCOMP_LISTENER_ACK_V1"
_MAX_RECEIVED_FDS = 4
_EPERM = errno.EPERM
_AF_UNIX = 1
_AF_INET_FAMILIES = {2, 10}  # AF_INET, AF_INET6
_SECCOMP_GET_NOTIF_SIZES = 3
_SECCOMP_IOCTL_NOTIF_RECV = 0
_SECCOMP_IOCTL_NOTIF_SEND = 1
_SECCOMP_NR = {"x86_64": 317, "amd64": 317, "aarch64": 277, "arm64": 277}
_SYSCALLS = {
    "x86_64": {"socket": 41, "socketpair": 53, "io_uring_setup": 425},
    "amd64": {"socket": 41, "socketpair": 53, "io_uring_setup": 425},
    "aarch64": {"socket": 198, "socketpair": 199, "io_uring_setup": 425},
    "arm64": {"socket": 198, "socketpair": 199, "io_uring_setup": 425},
}


class LinuxSeccompNotificationError(ConnectionError):
    """A listener handoff or observer failure; execution must remain blocked."""


def create_seccomp_listener_handoff_channel() -> tuple[socket.socket, socket.socket]:
    """Return non-inheritable host/sender endpoints for one listener handoff."""

    if not sys.platform.startswith("linux"):
        raise LinuxSeccompNotificationError("Linux seccomp notifications unavailable")
    host_control: socket.socket | None = None
    sender_control: socket.socket | None = None
    try:
        host_control, sender_control = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_SEQPACKET,
        )
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
            raise LinuxSeccompNotificationError(
                "Linux seccomp notifications unavailable",
            ) from None
        raise


def _ioctl_iowr(number: int, size: int) -> int:
    # Linux asm-generic/ioctl.h _IOC encoding, also used by x86_64.
    return (3 << 30) | (size << 16) | (ord("!") << 8) | number


def _notification_sizes() -> tuple[int, int]:
    machine = platform.machine().lower()
    syscall_number = _SECCOMP_NR.get(machine)
    if syscall_number is None:
        raise LinuxSeccompNotificationError("unsupported seccomp architecture")

    class NotificationSizes(ctypes.Structure):
        _fields_ = [
            ("notification", ctypes.c_uint16),
            ("response", ctypes.c_uint16),
            ("data", ctypes.c_uint16),
        ]

    sizes = NotificationSizes()
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    result = libc.syscall(
        ctypes.c_long(syscall_number),
        ctypes.c_uint(_SECCOMP_GET_NOTIF_SIZES),
        ctypes.c_uint(0),
        ctypes.byref(sizes),
    )
    if result != 0 or sizes.notification < 80 or sizes.response < 24:
        error = ctypes.get_errno()
        raise LinuxSeccompNotificationError(
            "seccomp notification ABI unavailable",
        ) from OSError(error or errno.EPROTO, os.strerror(error or errno.EPROTO))
    return int(sizes.notification), int(sizes.response)


def _close_received_fds(descriptors: list[int]) -> None:
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except OSError:
            pass
    descriptors.clear()


def _parse_handoff(
    control: socket.socket,
    *,
    timeout_seconds: float,
) -> tuple[int, int, int]:
    """Receive exactly one seccomp FD and validate its notification ABI."""

    if timeout_seconds <= 0:
        raise LinuxSeccompNotificationError("seccomp listener handoff timed out")
    control.settimeout(min(timeout_seconds, 5.0))
    descriptor_size = array.array("i").itemsize
    ancillary_size = socket.CMSG_SPACE(descriptor_size * _MAX_RECEIVED_FDS)
    descriptors: list[int] = []
    adopted_descriptor: int | None = None
    try:
        payload, ancillary, flags, _address = control.recvmsg(
            len(_HANDOFF_MESSAGE) + 1,
            ancillary_size,
            socket.MSG_CMSG_CLOEXEC,
        )
        malformed = bool(flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC))
        for level, kind, raw in ancillary:
            if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
                malformed = True
                continue
            complete_size = len(raw) - (len(raw) % descriptor_size)
            if complete_size != len(raw):
                malformed = True
            values = array.array("i")
            values.frombytes(raw[:complete_size])
            descriptors.extend(values)
        if (
            malformed
            or payload != _HANDOFF_MESSAGE
            or len(descriptors) != 1
        ):
            raise LinuxSeccompNotificationError("invalid seccomp listener handoff")

        descriptor = descriptors.pop()
        adopted_descriptor = descriptor
        os.set_inheritable(descriptor, False)
        os.set_blocking(descriptor, False)
        notification_size, response_size = _notification_sizes()
        adopted_descriptor = None
        return descriptor, notification_size, response_size
    except (OSError, OverflowError, ValueError) as exc:
        raise LinuxSeccompNotificationError(
            "seccomp listener handoff failed",
        ) from exc
    finally:
        _close_received_fds(descriptors)
        if adopted_descriptor is not None:
            try:
                os.close(adopted_descriptor)
            except OSError:
                pass


class LinuxSeccompViolationMonitor:
    """Own a transferred listener and answer DENY notifications with EPERM."""

    def __init__(self, control: socket.socket) -> None:
        self._control = control
        self._process: object | None = None
        self._listener_fd: int | None = None
        self._notification_size = 0
        self._response_size = 0
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._acknowledged = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._failed = False
        self._started = False

    def bind_process(self, process: object) -> None:
        if self._started or self._process is not None:
            raise LinuxSeccompNotificationError("seccomp monitor process already bound")
        self._process = process

    @property
    def failed(self) -> bool:
        with self._lock:
            return self._failed

    def _remaining_seconds(self, deadline_monotonic: float) -> float:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            self._fail()
            raise LinuxSeccompNotificationError("seccomp observer deadline expired")
        return remaining

    def start(self, *, deadline_monotonic: float) -> None:
        if self._started:
            raise LinuxSeccompNotificationError("seccomp monitor already started")
        remaining = self._remaining_seconds(deadline_monotonic)
        descriptor, notification_size, response_size = _parse_handoff(
            self._control,
            timeout_seconds=remaining,
        )
        self._listener_fd = descriptor
        self._notification_size = notification_size
        self._response_size = response_size
        self._remaining_seconds(deadline_monotonic)
        observer_thread = threading.Thread(
            target=self._observe,
            name="icode-seccomp-violation-monitor",
            daemon=True,
        )
        observer_thread.start()
        self._thread = observer_thread
        remaining = self._remaining_seconds(deadline_monotonic)
        if not self._ready.wait(timeout=remaining):
            self._fail()
            raise LinuxSeccompNotificationError("seccomp monitor did not become ready")
        self._acknowledge_if_healthy(deadline_monotonic)

    def _acknowledge_if_healthy(self, deadline_monotonic: float) -> None:
        failed = False
        with self._lock:
            thread = self._thread
            remaining = deadline_monotonic - time.monotonic()
            if (
                self._failed
                or thread is None
                or not thread.is_alive()
                or remaining <= 0
            ):
                failed = True
            else:
                self._control.settimeout(remaining)
                remaining = deadline_monotonic - time.monotonic()
                if remaining <= 0 or self._failed:
                    failed = True
                else:
                    # The observer thread waits on _acknowledged after poller
                    # registration, so it cannot fail its startup path between
                    # this health check and the helper's ACK barrier.
                    self._control.sendall(_HANDOFF_ACK)
                    self._started = True
                    self._acknowledged.set()
        if failed:
            self._fail()
            raise LinuxSeccompNotificationError(
                "seccomp observer failed before payload acknowledgement",
            )

    def _fail(self) -> None:
        notify = False
        with self._lock:
            if not self._failed:
                self._failed = True
                notify = True
        if notify:
            process_kill = getattr(self._process, "kill", None)
            if callable(process_kill):
                try:
                    process_kill()
                except OSError:
                    pass

    def abort(self) -> None:
        """Fail closed after setup cannot establish the observer barrier."""
        self._fail()

    def _record(self, category: str) -> None:
        with self._lock:
            if self._counts.get(category, 0) < 65535:
                self._counts[category] = self._counts.get(category, 0) + 1

    def _category(self, notification: bytes) -> str:
        machine = platform.machine().lower()
        syscall_numbers = _SYSCALLS.get(machine)
        if syscall_numbers is None:
            return "native_policy_violation"
        syscall_number = struct.unpack_from("=i", notification, 16)[0]
        if syscall_number == syscall_numbers["socket"]:
            family = struct.unpack_from("=Q", notification, 32)[0]
            return "network_socket" if family in _AF_INET_FAMILIES else "socket"
        if syscall_number == syscall_numbers["socketpair"]:
            return "socketpair"
        if syscall_number == syscall_numbers["io_uring_setup"]:
            return "async_io"
        return "native_policy_violation"

    def _observe(self) -> None:
        descriptor = self._listener_fd
        if descriptor is None:
            self._fail()
            self._ready.set()
            return
        try:
            receive_ioctl = _ioctl_iowr(
                _SECCOMP_IOCTL_NOTIF_RECV, self._notification_size,
            )
            send_ioctl = _ioctl_iowr(
                _SECCOMP_IOCTL_NOTIF_SEND, self._response_size,
            )
            poller = select.poll()
            poller.register(
                descriptor,
                select.POLLIN | select.POLLERR | select.POLLHUP | select.POLLNVAL,
            )
            self._ready.set()
            while not self._acknowledged.wait(timeout=0.05):
                if self._stop.is_set():
                    return
            if self._stop.is_set():
                return
            while not self._stop.is_set():
                events = poller.poll(100)
                if not events:
                    process_poll = getattr(self._process, "poll", None)
                    if callable(process_poll) and process_poll() is not None:
                        return
                    continue
                flags = events[0][1]
                if flags & (select.POLLERR | select.POLLNVAL):
                    if not self._stop.is_set():
                        raise OSError(errno.EIO, "seccomp listener closed")
                    return
                if not flags & select.POLLIN:
                    # HUP means no task remains attached to this filter, so no
                    # later sandboxed syscall can be lost.
                    if flags & select.POLLHUP:
                        return
                    continue
                notification = bytearray(self._notification_size)
                try:
                    fcntl.ioctl(descriptor, receive_ioctl, notification, True)
                except OSError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.ENOENT):
                        continue
                    raise
                notification_id = struct.unpack_from("=Q", notification, 0)[0]
                response = bytearray(self._response_size)
                struct.pack_into("=Q", response, 0, notification_id)
                struct.pack_into("=q", response, 8, 0)
                struct.pack_into("=i", response, 16, -_EPERM)
                struct.pack_into("=I", response, 20, 0)
                try:
                    fcntl.ioctl(descriptor, send_ioctl, response, True)
                except OSError as exc:
                    if exc.errno == errno.ENOENT:
                        continue
                    raise
                self._record(self._category(notification))
        except BaseException:  # noqa: BLE001 - any observer crash must fail closed.
            if not self._stop.is_set():
                self._fail()
        finally:
            self._ready.set()
            if self._listener_fd is not None:
                try:
                    os.close(self._listener_fd)
                except OSError:
                    self._fail()
                self._listener_fd = None

    def close(self) -> bool:
        self._stop.set()
        self._acknowledged.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            if thread.is_alive():
                self._fail()
                return False
        if self._listener_fd is not None:
            try:
                os.close(self._listener_fd)
            except OSError:
                self._fail()
            self._listener_fd = None
        return not self.failed

    def receipt(self) -> dict[str, object] | None:
        with self._lock:
            if not self._counts or self._failed:
                return None
            categories = sorted(self._counts)
            count = min(65535, sum(self._counts.values()))
        return {
            "schema_version": 1,
            "enforcement_layer": "os_seccomp_user_notif",
            "os_enforced": True,
            "category": categories[0] if len(categories) == 1 else "multiple",
            "source": "seccomp_user_notif",
            "count": count,
        }


__all__ = [
    "LinuxSeccompNotificationError",
    "LinuxSeccompViolationMonitor",
    "create_seccomp_listener_handoff_channel",
]
