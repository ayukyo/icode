"""Private ownership of one delegated user scope; no global manager mutations."""
from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import sys
import threading
import time

from .linux_task_resource import _select_cleanup_error

_UNIT = re.compile(r"icode-task-[0-9a-f]{32}\.scope\Z")
_INVOCATION = re.compile(r"[0-9a-f]{32}\Z")
_PROPERTIES = ("Id", "LoadState", "ActiveState", "ControlGroup", "InvocationID", "Transient")
_CGROUP = Path("/sys/fs/cgroup")
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_QUERY_LIMIT_BYTES = 8192
_CGROUP_READ_LIMIT_BYTES = 4096
_BUS_CONNECT_TIMEOUT_SECONDS = 0.2
_VERSION_QUERY_TIMEOUT_SECONDS = 1
_GC_POLL_SECONDS = 0.02
_INT_MAX = 2147483647  # Native pids.max contract, never rounded or truncated.


class LinuxTaskScopeError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Linux task scope is unavailable")


def _open_directory(path: Path, *, uid: int, cgroup: bool = False) -> int:
    """Walk pinned non-link ancestors, accepting only root/current-UID owners."""
    if not path.is_absolute() or any(part in ("", ".", "..") for part in path.parts[1:]):
        raise LinuxTaskScopeError()
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        device = None
        for index, component in enumerate(path.parts[1:]):
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            previous = current
            current = following
            os.close(previous)
            status = os.fstat(current)
            if status.st_uid not in (0, uid) or status.st_mode & 0o022:
                raise LinuxTaskScopeError()
            if cgroup and index >= len(_CGROUP.parts) - 2:
                if device is not None and status.st_dev != device:
                    raise LinuxTaskScopeError()
                device = status.st_dev
        return current
    except BaseException as error:
        try:
            os.close(current)
        except BaseException as cleanup_error:
            selected = _select_cleanup_error(error, cleanup_error)
            if selected is not error:
                raise selected
        raise


def _trusted_tool(path: str, uid: int) -> None:
    parent = _open_directory(Path(path).parent, uid=0)
    descriptor = -1
    try:
        descriptor = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=parent)
        status = os.fstat(descriptor)
        if (not stat.S_ISREG(status.st_mode) or status.st_uid != 0
                or status.st_nlink != 1 or status.st_mode & 0o022
                or not status.st_mode & 0o111):
            raise LinuxTaskScopeError()
    finally:
        active_exception = sys.exc_info()[1]
        close_error = None
        for owned in (descriptor, parent):
            if owned < 0:
                continue
            try:
                os.close(owned)
            except BaseException as error:
                close_error = _select_cleanup_error(close_error, error)
        if close_error is not None:
            selected = _select_cleanup_error(active_exception, close_error)
            if selected is not active_exception:
                raise selected


def _read_at(directory: int, name: str, limit: int = _CGROUP_READ_LIMIT_BYTES) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    try:
        result = bytearray()
        while len(result) <= limit:
            chunk = os.read(descriptor, min(1024, limit + 1 - len(result)))
            if not chunk:
                return bytes(result)
            result.extend(chunk)
        raise LinuxTaskScopeError()
    finally:
        os.close(descriptor)


class LinuxTaskScope:
    """Pin only a CONFIGURED task, then observe its exact unit/directory GC.

    The query adapter reuses the existing execution broker; this class never
    starts, signals, stops, enumerates or deletes another manager unit.
    """

    def __init__(self, *, limit: int, query: Callable[[list[str], dict[str, str], float], bytes]) -> None:
        self.uid = os.getuid()
        if self.uid == 0 or type(limit) is not int or not 1 <= limit <= _INT_MAX:
            raise LinuxTaskScopeError()
        self.limit = limit
        self.unit = f"icode-task-{secrets.token_hex(16)}.scope"
        if not _UNIT.fullmatch(self.unit):
            raise LinuxTaskScopeError()
        self._query_adapter = query
        self._fds: list[int] = []
        self._path: Path | None = None
        self._pid: int | None = None
        self._identities: list[tuple[int, int]] = []
        self._invocation: str | None = None
        self._owned = False
        self._lifecycle = threading.Lock()
        self._close_requested = threading.Event()
        for path in ("/usr/bin/systemd-run", "/usr/bin/systemctl"):
            _trusted_tool(path, self.uid)
        runtime = Path(f"/run/user/{self.uid}")
        parent = _open_directory(runtime, uid=self.uid)
        try:
            status = os.fstat(parent)
            bus = os.stat("bus", dir_fd=parent, follow_symlinks=False)
            if (status.st_uid != self.uid or stat.S_IMODE(status.st_mode) != 0o700
                    or not stat.S_ISSOCK(bus.st_mode) or bus.st_uid != self.uid):
                raise LinuxTaskScopeError()
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(_BUS_CONNECT_TIMEOUT_SECONDS)
                probe.connect(str(runtime / "bus"))
                _pid, peer_uid, _gid = struct.unpack("3i", probe.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if peer_uid != self.uid:
                    raise LinuxTaskScopeError()
        finally:
            os.close(parent)
        self.environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
                            "XDG_RUNTIME_DIR": str(runtime),
                            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime / 'bus'}"}
        version = self._query(["/usr/bin/systemd-run", "--version"], time.monotonic() + _VERSION_QUERY_TIMEOUT_SECONDS)
        match = re.match(rb"systemd ([0-9]+)(?:\s|\Z)", version)
        if not match:
            raise LinuxTaskScopeError()
        self.version = int(match.group(1))

    def _query(self, argv: list[str], deadline: float) -> bytes:
        if time.monotonic() >= deadline:
            raise LinuxTaskScopeError()
        result = self._query_adapter(argv, self.environment, deadline)
        if type(result) is not bytes or len(result) > _QUERY_LIMIT_BYTES or time.monotonic() >= deadline:
            raise LinuxTaskScopeError()
        return result

    def _show(self, deadline: float) -> dict[str, str]:
        argv = ["/usr/bin/systemctl", "--user", "show", self.unit,
                "--property=" + ",".join(_PROPERTIES)]
        raw = self._query(argv, deadline)
        try:
            fields: dict[str, str] = {}
            for line in raw.decode("utf-8", errors="strict").splitlines():
                name, value = line.split("=", 1)
                if name not in _PROPERTIES or name in fields or "\x00" in value:
                    raise LinuxTaskScopeError()
                fields[name] = value
            if set(fields) != set(_PROPERTIES) or fields["Id"] != self.unit:
                raise LinuxTaskScopeError()
            return fields
        except (UnicodeError, ValueError):
            raise LinuxTaskScopeError() from None

    def wrap(self, helper: list[str]) -> list[str]:
        flags = ["--expand-environment=no"] if self.version >= 254 else []
        return ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect",
                "--no-ask-password", "--description=ICODE task command", f"--unit={self.unit}",
                "--property=Delegate=pids", *flags, "--", *helper]

    def bind_process(self, pid: int) -> None:
        if self._pid is not None or type(pid) is not int or pid <= 1:
            raise LinuxTaskScopeError()
        self._pid = pid

    def _membership(self) -> str:
        if self._pid is None:
            raise LinuxTaskScopeError()
        with open(f"/proc/{self._pid}/cgroup", "rb") as stream:
            raw = stream.read(_CGROUP_READ_LIMIT_BYTES + 1)
        lines = raw.splitlines()
        if len(raw) > _CGROUP_READ_LIMIT_BYTES or len(lines) != 1 or not lines[0].startswith(b"0::/"):
            raise LinuxTaskScopeError()
        value = lines[0][3:].decode("utf-8", errors="strict")
        if ("\x00" in value or "//" in value or any(part in (".", "..") for part in value.split("/"))
                or not value.endswith(f"/{self.unit}/supervisor")):
            raise LinuxTaskScopeError()
        return value

    def configured(self, deadline: float) -> None:
        try:
            with self._lifecycle:
                if self._close_requested.is_set():
                    raise LinuxTaskScopeError()
                self._configure_locked(deadline)
                if self._close_requested.is_set():
                    self._owned = False
                    raise LinuxTaskScopeError()
        finally:
            # Also covers exceptional callbacks and requests arriving at the
            # lock-release boundary; no descriptor can be recycled mid-use.
            if self._close_requested.is_set():
                self.close()

    def _configure_locked(self, deadline: float) -> None:
        membership = self._membership()
        group = membership.removesuffix("/supervisor")
        path = _CGROUP / group.lstrip("/")
        try:
            for candidate in (path, path / "supervisor", path / "payload"):
                descriptor = _open_directory(candidate, uid=self.uid, cgroup=True)
                self._fds.append(descriptor)
                status = os.fstat(descriptor)
                if status.st_uid != self.uid:
                    raise LinuxTaskScopeError()
                self._identities.append((status.st_dev, status.st_ino))
            fields = self._show(deadline)
            if (fields["LoadState"] != "loaded" or fields["ActiveState"] != "active"
                    or fields["Transient"] != "yes" or not _INVOCATION.fullmatch(fields["InvocationID"])
                    or fields["ControlGroup"] != group):
                raise LinuxTaskScopeError()
            if (_read_at(self._fds[0], "cgroup.procs").strip()
                    or _read_at(self._fds[1], "cgroup.procs").strip() != str(self._pid).encode("ascii")
                    or _read_at(self._fds[2], "cgroup.procs").strip()
                    or _read_at(self._fds[2], "pids.current").strip() != b"0"
                    or _read_at(self._fds[2], "pids.max").strip() != str(self.limit).encode("ascii")):
                raise LinuxTaskScopeError()
            if self._membership() != membership:
                raise LinuxTaskScopeError()
            for candidate, identity in zip((path, path / "supervisor", path / "payload"), self._identities, strict=True):
                descriptor = _open_directory(candidate, uid=self.uid, cgroup=True)
                try:
                    status = os.fstat(descriptor)
                    if (status.st_dev, status.st_ino) != identity:
                        raise LinuxTaskScopeError()
                finally:
                    os.close(descriptor)
            if time.monotonic() >= deadline:
                raise LinuxTaskScopeError()
            self._path = path
            self._invocation = fields["InvocationID"]
            self._owned = True
        except BaseException:
            self._close_pins()
            raise

    def collected(self, deadline: float) -> bool | None:
        if not self._lifecycle.acquire(blocking=False):
            return None
        try:
            return self._collect_locked(deadline)
        finally:
            self._lifecycle.release()
            if self._close_requested.is_set():
                self.close()

    def _collect_locked(self, deadline: float) -> bool | None:
        if not self._owned or self._path is None:
            return None
        while time.monotonic() < deadline:
            try:
                fields = self._show(deadline)
                try:
                    descriptor = _open_directory(self._path, uid=self.uid, cgroup=True)
                except FileNotFoundError:
                    return fields["LoadState"] == "not-found" and not fields["ControlGroup"]
                else:
                    os.close(descriptor)
                if fields["LoadState"] == "loaded" and fields["InvocationID"] != self._invocation:
                    return False
                time.sleep(min(_GC_POLL_SECONDS, max(0, deadline - time.monotonic())))
            except (OSError, ValueError, LinuxTaskScopeError):
                return None
        return False

    def close(self) -> None:
        self._close_requested.set()
        if not self._lifecycle.acquire(blocking=False):
            return
        try:
            self._close_pins()
        finally:
            self._lifecycle.release()

    def _close_pins(self) -> None:
        close_error = None
        while self._fds:
            descriptor = self._fds.pop()
            try:
                os.close(descriptor)
            except OSError:
                pass
            except BaseException as error:
                close_error = _select_cleanup_error(close_error, error)
        if close_error is not None:
            raise close_error
