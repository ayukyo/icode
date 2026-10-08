"""Credential-bound Linux task-resource facts, not an exec-success oracle.

The caller owns the socket. Start this receiver before waiting for a separate
USER_NOTIF handoff. CONFIGURED releases only the native preparation barrier;
neither a finished transcript nor EOF proves that exec succeeded.
"""
from __future__ import annotations

import array
import math
import os
import re
import selectors
import socket
import struct
import sys
import threading
import time

_FRAME = struct.Struct("!5sB16sI")
_ACK = struct.Struct("!5s16sI")
_CREDENTIALS = struct.Struct("3i")
_UNIT = re.compile(r"icode-task-([0-9a-f]{32})\.scope\Z")
_ERROR = "Linux task resource channel is invalid"
_TERMINALS = {2: "preexec_failed", 3: "finished", 4: "cleanup_failed"}


class LinuxTaskResourceError(ConnectionError):
    """A fixed, input-free error for an invalid private resource channel."""


def create_task_resource_channel() -> tuple[socket.socket, socket.socket]:
    if not sys.platform.startswith("linux"):
        raise LinuxTaskResourceError(_ERROR)
    host = sender = None
    try:
        host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        host.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        host.set_inheritable(False)
        sender.set_inheritable(False)
        return host, sender
    except BaseException as error:
        for endpoint in (sender, host):
            if endpoint is not None:
                endpoint.close()
        if isinstance(error, OSError):
            raise LinuxTaskResourceError(_ERROR) from None
        raise


class LinuxTaskResourceReceiver:
    """Receive at most CONFIGURED plus one terminal, bound to a host writer.

    ``bind_process`` additionally arranges fail-closed child termination on a
    malformed transcript. ``bind`` supports callers owning termination outside
    this component. All recvmsg/FD cleanup runs on the worker, away from Python
    main-thread signal callbacks. ``close`` stops that worker, not the caller's
    socket and not a cgroup/scope.
    """

    def __init__(self, control: socket.socket, *, unit: str, limit: int) -> None:
        match = _UNIT.fullmatch(unit) if type(unit) is str else None
        if (
            not sys.platform.startswith("linux") or not match
            or type(limit) is not int or not 1 <= limit <= 2147483647
            or type(control) is not socket.socket or control.fileno() < 0
            or control.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN) != socket.AF_UNIX
            or control.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET
            or control.getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED) != 1
        ):
            raise LinuxTaskResourceError(_ERROR)
        self._control = control
        self._nonce = bytes.fromhex(match.group(1))
        self._limit = limit
        self._expected: tuple[int, int, int] | None = None
        self._process: object | None = None
        self._stop = threading.Event()
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._configured = False
        self._terminal: int | None = None
        self._complete = False

    def bind(self, *, expected_pid: int, expected_uid: int, expected_gid: int) -> None:
        values = (expected_pid, expected_uid, expected_gid)
        if (
            self._expected is not None or self._thread is not None
            or any(type(value) is not int for value in values)
            or expected_pid <= 1 or expected_uid < 0 or expected_gid < 0
        ):
            raise LinuxTaskResourceError(_ERROR)
        self._expected = values

    def bind_process(self, process: object, *, expected_uid: int,
                     expected_gid: int) -> None:
        if not callable(getattr(process, "kill", None)):
            raise LinuxTaskResourceError(_ERROR)
        self.bind(expected_pid=getattr(process, "pid", None),
                  expected_uid=expected_uid, expected_gid=expected_gid)
        self._process = process

    def start(self, *, deadline_monotonic: float) -> None:
        if (
            self._expected is None or self._thread is not None or self._stop.is_set()
            or isinstance(deadline_monotonic, bool)
            or not isinstance(deadline_monotonic, (int, float))
            or not math.isfinite(deadline_monotonic)
            or deadline_monotonic <= time.monotonic()
        ):
            raise LinuxTaskResourceError(_ERROR)
        worker = threading.Thread(target=self._receive, args=(deadline_monotonic,),
                                  name="icode-task-resource", daemon=True)
        self._thread = worker
        try:
            worker.start()
        except BaseException:
            self._stop.set()
            self._fail()
            raise

    def _fail(self) -> None:
        with self._lock:
            self._terminal = None
            self._complete = False
        if self._process is not None:
            try:
                self._process.kill()
            except OSError:
                pass

    def _message(self) -> bytes:
        ancillary: list[tuple[int, int, bytes]] = []
        credentials: list[tuple[int, int, int]] = []
        malformed = False
        try:
            payload, ancillary, flags, _address = self._control.recvmsg(
                _FRAME.size + 1,
                socket.CMSG_SPACE(array.array("i").itemsize * 32)
                + socket.CMSG_SPACE(_CREDENTIALS.size),
                socket.MSG_CMSG_CLOEXEC | socket.MSG_DONTWAIT,
            )
            for level, kind, raw in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    malformed = True  # This protocol never accepts an FD.
                elif level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS:
                    if len(raw) != _CREDENTIALS.size:
                        malformed = True
                    else:
                        credentials.append(_CREDENTIALS.unpack(raw))
                else:
                    malformed = True
            if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or malformed:
                raise LinuxTaskResourceError(_ERROR)
            # Linux seqpacket permits zero-byte messages: with SO_PASSCRED
            # those carry ancillary credentials, unlike actual peer EOF.
            if not payload and ancillary:
                raise LinuxTaskResourceError(_ERROR)
            if payload and credentials != [self._expected]:
                raise LinuxTaskResourceError(_ERROR)
            return payload
        finally:
            # Scan the original delivery, not a partially populated adoption
            # list: parsing an earlier credential must not strand later FDs.
            for level, kind, raw in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    width = struct.calcsize("=i")
                    for offset in range(0, len(raw) - len(raw) % width, width):
                        descriptor = struct.unpack_from("=i", raw, offset)[0]
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass

    def _receive(self, deadline: float) -> None:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self._control, selectors.EVENT_READ)
                count = 0
                while not self._stop.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise LinuxTaskResourceError(_ERROR)
                    if not selector.select(min(remaining, 0.05)):
                        continue
                    try:
                        payload = self._message()
                    except (BlockingIOError, InterruptedError):
                        continue
                    if not payload:
                        with self._lock:
                            if self._terminal is None:
                                raise LinuxTaskResourceError(_ERROR)
                            self._complete = True
                        return
                    if len(payload) != _FRAME.size:
                        raise LinuxTaskResourceError(_ERROR)
                    magic, phase, nonce, limit = _FRAME.unpack(payload)
                    if magic != b"ICQR1" or nonce != self._nonce or limit != self._limit:
                        raise LinuxTaskResourceError(_ERROR)
                    if count >= 2 or self._terminal is not None:
                        raise LinuxTaskResourceError(_ERROR)
                    if phase == 1 and count == 0:
                        ack = _ACK.pack(b"ICQA1", self._nonce, self._limit)
                        if self._control.send(ack, socket.MSG_NOSIGNAL | socket.MSG_DONTWAIT) != len(ack):
                            raise LinuxTaskResourceError(_ERROR)
                        with self._lock:
                            self._configured = True
                    elif phase in _TERMINALS and (count == 1 or phase in (2, 4)):
                        with self._lock:
                            self._terminal = phase
                    else:
                        raise LinuxTaskResourceError(_ERROR)
                    count += 1
                raise LinuxTaskResourceError(_ERROR)
        except BaseException:
            self._fail()
        finally:
            self._done.set()

    def wait(self, *, timeout_seconds: float) -> bool:
        if (
            isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or timeout_seconds < 0
        ):
            raise LinuxTaskResourceError(_ERROR)
        return self._done.wait(timeout_seconds)

    def close(self) -> bool:
        self._stop.set()
        worker = self._thread
        if worker is not None and worker.ident is not None:
            worker.join(timeout=2)
            return self._done.is_set()
        return True

    def receipt(self) -> dict[str, object]:
        with self._lock:
            return {
                "schema_version": 1,
                "resource": "linux_payload_tasks",
                "limit": self._limit,
                "configured": self._configured,
                "payload_started": False if self._complete and self._terminal == 2 else None,
                "terminal": _TERMINALS.get(self._terminal) if self._complete else None,
                "channel_status": "complete" if self._complete else "incomplete",
            }
