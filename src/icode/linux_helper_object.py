"""Private Linux helper verification/FD ownership, never an execution grant.

Trusted callers must not externally close/dup2 the owned FD or concurrently
mutate owner state. Identity checks detect different-object reuse, not reuse of
the same object. No immutable-content, ancestor-trust or publisher claim.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import re
import stat
import sys

from .native_helper import linux_arch_from_machine, linux_elf_architecture

_ERROR = "Linux helper object is unavailable"
_MANIFEST_LIMIT = 66
_BINARY_LIMIT = 64 * 1024 * 1024
_READ_CHUNK = 64 * 1024
_HEADER_SIZE = 64
_MANIFEST = re.compile(rb"[0-9a-f]{64}\n?\Z")


class LinuxHelperObjectError(RuntimeError):
    """An input-free failure of the private helper-object contract."""

    def __init__(self) -> None:
        super().__init__(_ERROR)


def _select(first: BaseException | None, following: BaseException) -> BaseException:
    # Match existing cleanup priority without importing the supervision chain.
    if first is None or (isinstance(first, Exception) and not isinstance(following, Exception)):
        return following
    return first


def _raise_fixed_or_signal(error: BaseException) -> None:
    if not isinstance(error, Exception):
        raise error
    raise LinuxHelperObjectError() from None


def _identity(status) -> tuple[int, int]:
    return status.st_dev, status.st_ino


def _snapshot(status) -> tuple[int, int, int, int, int]:
    return (*_identity(status), status.st_size, status.st_mtime_ns, status.st_ctime_ns)


def _regular(status, *, executable: bool) -> None:
    if (not stat.S_ISREG(status.st_mode) or status.st_nlink != 1
            or (executable and not status.st_mode & 0o111)):
        raise LinuxHelperObjectError()


def _read_prefix(fd: int, limit: int) -> bytes:
    result = bytearray()
    while len(result) < limit:
        chunk = os.read(fd, limit - len(result))
        if not chunk:
            break
        result.extend(chunk)
    return bytes(result)


class LinuxHelperObject:
    """Explicit owner; factory verification, not constructor identity authentication."""

    def __init__(self, fd: int, identity: tuple[int, int], architecture: str, digest: str) -> None:
        self._fd = fd
        self._identity = identity
        self._architecture = architecture
        self._sha256 = digest
        self._state = "active"

    @property
    def architecture(self) -> str:
        return self._architecture

    @property
    def sha256(self) -> str:
        return self._sha256

    def fileno(self) -> int:
        try:
            if self._state != "active":
                raise LinuxHelperObjectError()
            status = os.fstat(self._fd)
            # After acquisition unlink/rename may change nlink/ctime, not identity.
            if not stat.S_ISREG(status.st_mode) or _identity(status) != self._identity:
                raise LinuxHelperObjectError()
            return self._fd
        except BaseException as error:
            _raise_fixed_or_signal(error)

    def close(self) -> None:
        if self._state == "closed":
            return
        if self._state != "active":
            raise LinuxHelperObjectError()
        try:
            fd = self.fileno()
            # An exception from close may mean the integer has already been reused.
            self._state = "unknown"
            os.close(fd)
        except BaseException as error:
            self._state = "unknown"
            _raise_fixed_or_signal(error)
        self._state = "closed"

    def __enter__(self) -> LinuxHelperObject:
        self.fileno()
        return self

    def __copy__(self):
        raise LinuxHelperObjectError()

    def __deepcopy__(self, memo):
        raise LinuxHelperObjectError()

    def __reduce_ex__(self, protocol):
        raise LinuxHelperObjectError()

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            self.close()
        except BaseException as cleanup_error:
            selected = _select(exc_value, cleanup_error)
            if selected is cleanup_error:
                raise
        return False


def open_linux_helper_object(binary: Path, manifest: Path) -> LinuxHelperObject:
    """Verify one opened binary and return its independent non-executing owner."""
    owned: list[int] = []
    try:
        # True host checks and required mechanisms precede all filesystem access.
        if not sys.platform.startswith("linux"):
            raise LinuxHelperObjectError()
        architecture = linux_arch_from_machine(platform.machine())
        flags = os.O_RDONLY
        for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
            value = getattr(os, name, None)
            if type(value) is not int or value <= 0:
                raise LinuxHelperObjectError()
            flags |= value

        binary_fd = os.open(binary, flags)
        owned.append(binary_fd)
        before = os.fstat(binary_fd)
        _regular(before, executable=True)
        if before.st_size < _HEADER_SIZE or before.st_size > _BINARY_LIMIT:
            raise LinuxHelperObjectError()

        manifest_fd = os.open(manifest, flags)
        owned.append(manifest_fd)
        _regular(os.fstat(manifest_fd), executable=False)
        expected = _read_prefix(manifest_fd, _MANIFEST_LIMIT)
        if _MANIFEST.fullmatch(expected) is None:
            raise LinuxHelperObjectError()
        # Relinquish retry responsibility before close, including close exceptions.
        owned.remove(manifest_fd)
        os.close(manifest_fd)

        os.lseek(binary_fd, 0, os.SEEK_SET)
        header = _read_prefix(binary_fd, _HEADER_SIZE)
        if linux_elf_architecture(header) != architecture:
            raise LinuxHelperObjectError()
        os.lseek(binary_fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        total = 0
        while total <= _BINARY_LIMIT:
            chunk = os.read(binary_fd, min(_READ_CHUNK, _BINARY_LIMIT + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > _BINARY_LIMIT:
                raise LinuxHelperObjectError()
            digest.update(chunk)
        after = os.fstat(binary_fd)
        _regular(after, executable=True)
        actual = digest.hexdigest()
        if (_snapshot(before) != _snapshot(after) or total != after.st_size
                or actual.encode("ascii") != expected.rstrip(b"\n")):
            raise LinuxHelperObjectError()
        owner = LinuxHelperObject(binary_fd, _identity(after), architecture, actual)
        owned.remove(binary_fd)
        return owner
    except BaseException as error:
        selected = error
        # Drain every still-owned entry once even if cleanup raises a signal.
        while owned:
            fd = owned.pop()
            try:
                os.close(fd)
            except BaseException as cleanup_error:
                selected = _select(selected, cleanup_error)
        _raise_fixed_or_signal(selected)
