"""Internal startup bytes/HANDLE owner; neither publisher nor launch authority.

The backend must open a directly bound local volume root, then open each single
component relative to the preceding HANDLE without following reparse points.
Every acquired HANDLE is owned here; query/read must use that same HANDLE.
There is deliberately no POSIX emulation and no path-based read fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ntpath
import os
import re
from typing import Protocol


MAX_STARTUP_BYTES = 64 * 1024 * 1024
_READ_CHUNK = 64 * 1024


class StartupPinError(RuntimeError):
    """The source or owner cannot safely satisfy the pin contract."""


class StartupPinCloseError(StartupPinError):
    def __init__(self, errors: tuple[BaseException, ...]):
        self.errors = errors
        super().__init__(f"{len(errors)} startup HANDLE close(s) unconfirmed")


@dataclass(frozen=True)
class StartupFileMetadata:
    volume_serial: int
    file_id: bytes
    directory: bool
    reparse: bool
    delete_pending: bool
    file_type: str
    links: int
    size: int
    change_time: int


class _StartupPinBackend(Protocol):
    def open_root(self, drive: str) -> int: ...
    def open_child(self, parent: int, name: str, *, directory: bool) -> int: ...
    def query(self, handle: int) -> StartupFileMetadata: ...
    def read(self, handle: int, offset: int, count: int) -> bytes: ...
    def close(self, handle: int) -> None: ...


def _local_components(path: str) -> tuple[str, list[str]]:
    if type(path) is not str:
        raise StartupPinError("startup path must be a string")
    try:
        path.encode("utf-16-le", "strict")
    except UnicodeError as exc:
        raise StartupPinError("invalid Unicode startup path") from exc
    if not re.match(r"^[A-Za-z]:\\", path) or "/" in path:
        raise StartupPinError("startup path must be an absolute local drive path")
    drive, tail = ntpath.splitdrive(path)
    components = tail[1:].split("\\")
    for component in components:
        if (not component or component in (".", "..") or component.endswith((" ", "."))
                or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in component)):
            raise StartupPinError("unsafe startup path component")
        stem = component.split(".", 1)[0].rstrip(" ").upper()
        if stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem):
            raise StartupPinError("device alias is not a startup file")
    return drive.upper(), components


def _metadata(value: StartupFileMetadata, *, directory: bool, max_bytes: int) -> StartupFileMetadata:
    if type(value) is not StartupFileMetadata:
        raise StartupPinError("invalid HANDLE metadata structure")
    for field, minimum, maximum in (("volume_serial", 0, 2**64 - 1),
                                    ("links", 0, 2**32 - 1),
                                    ("size", 0, 2**64 - 1),
                                    ("change_time", -(2**63), 2**63 - 1)):
        item = getattr(value, field)
        if type(item) is not int or not minimum <= item <= maximum:
            raise StartupPinError(f"invalid HANDLE {field}")
    if type(value.file_id) is not bytes or len(value.file_id) != 16:
        raise StartupPinError("invalid 128-bit file identity")
    if any(type(getattr(value, field)) is not bool for field in ("directory", "reparse", "delete_pending")):
        raise StartupPinError("invalid HANDLE boolean metadata")
    if type(value.file_type) is not str or value.file_type != "disk":
        raise StartupPinError("HANDLE is not a disk object")
    if value.reparse or value.delete_pending or value.directory != directory:
        raise StartupPinError("unsafe HANDLE role or state")
    if not directory and (value.links != 1 or not 0 < value.size <= max_bytes):
        raise StartupPinError("startup file must be nonempty, single-link, and bounded")
    return value


class PinnedStartupFile:
    """Own volume, ancestor and final file HANDLEs and immutable source bytes.

    close() tries every registered HANDLE once, in reverse order. Failed closes
    remain explicitly unconfirmed; they are never retried because a numeric
    HANDLE might have been recycled after an ambiguous backend failure.
    """

    def __init__(self, backend: _StartupPinBackend, max_bytes: int):
        self._backend = backend
        self._max_bytes = max_bytes
        self._handles: list[int] = []
        self._baseline: list[StartupFileMetadata] = []
        self._unconfirmed: list[int] = []
        self._close_errors: tuple[BaseException, ...] = ()
        self._closed = False
        self._ready = False
        self._content = b""
        self._sha256 = ""

    def __copy__(self):
        # Independent close state must never share ownership of numeric HANDLEs.
        raise StartupPinError("startup HANDLE owner cannot be copied")

    def __deepcopy__(self, memo):
        raise StartupPinError("startup HANDLE owner cannot be copied")

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def close_confirmed(self) -> bool:
        return self._closed and not self._unconfirmed

    @property
    def close_errors(self) -> tuple[BaseException, ...]:
        return self._close_errors

    def _require_open(self) -> None:
        if self._closed or not self._ready:
            raise StartupPinError("startup owner is closed or uninitialized")

    @property
    def content(self) -> bytes:
        self._require_open()
        return self._content

    @property
    def sha256(self) -> str:
        self._require_open()
        return self._sha256

    def _register(self, handle: int) -> int:
        if type(handle) is not int or not 0 < handle < 2**64 - 1:
            raise StartupPinError("invalid acquired HANDLE")
        if handle in self._handles:
            raise StartupPinError("backend reused an owned HANDLE")
        self._handles.append(handle)
        return handle

    def _query_new(self, handle: int, *, directory: bool) -> None:
        meta = _metadata(self._backend.query(handle), directory=directory, max_bytes=self._max_bytes)
        if self._baseline and meta.volume_serial != self._baseline[0].volume_serial:
            raise StartupPinError("startup chain crosses volumes")
        if any((old.volume_serial, old.file_id) == (meta.volume_serial, meta.file_id)
               for old in self._baseline):
            raise StartupPinError("startup chain reuses an object identity")
        self._baseline.append(meta)

    def revalidate(self) -> None:
        self._require_open()
        self._validate_chain()

    def _validate_chain(self) -> None:
        try:
            for handle, previous in zip(self._handles, self._baseline):
                current = _metadata(self._backend.query(handle), directory=previous.directory,
                                    max_bytes=self._max_bytes)
                if current != previous:
                    raise StartupPinError("pinned HANDLE metadata changed")
        except BaseException as exc:
            self._close_preserving_exception(exc)
            raise

    def _close_preserving_exception(self, original: BaseException) -> None:
        already_closed = self._closed
        try:
            self.close()
        except BaseException:
            # The originating exception, including KI/SystemExit, has priority.
            pass
        if self._unconfirmed and not already_closed:
            try:
                BaseException.add_note(original, f"Startup HANDLE cleanup unconfirmed: {len(self._unconfirmed)}")
            except BaseException:
                # Even a hostile exception object's attribute hooks cannot
                # replace the originating failure while recording cleanup.
                pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        errors = []
        for handle in reversed(self._handles):
            try:
                self._backend.close(handle)
            except BaseException as exc:
                self._unconfirmed.append(handle)
                errors.append(exc)
        self._close_errors = tuple(errors)
        if errors:
            for error in errors:
                if not isinstance(error, Exception):
                    raise error
            raise StartupPinCloseError(self._close_errors)

    def __enter__(self) -> PinnedStartupFile:
        self._require_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is not None:
            self._close_preserving_exception(exc)
        else:
            self.close()
        return False


def pin_startup_file(absolute_local_path: str, max_bytes: int = MAX_STARTUP_BYTES,
                     *, _backend: _StartupPinBackend | None = None) -> PinnedStartupFile:
    """Pin original file bytes through HANDLEs; does not authorize path launch."""
    drive, components = _local_components(absolute_local_path)
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_STARTUP_BYTES:
        raise StartupPinError("invalid startup byte budget")
    if _backend is None:
        if os.name != "nt":
            raise StartupPinError("native Windows startup pin backend unavailable")
        try:
            from .windows_startup_native import WindowsStartupPinBackend
        except ImportError as exc:
            raise StartupPinError("native Windows startup pin backend unavailable") from exc
        _backend = WindowsStartupPinBackend()
    owner = PinnedStartupFile(_backend, max_bytes)
    try:
        handle = owner._register(_backend.open_root(drive))
        owner._query_new(handle, directory=True)
        for index, component in enumerate(components):
            directory = index < len(components) - 1
            handle = owner._register(_backend.open_child(handle, component, directory=directory))
            owner._query_new(handle, directory=directory)
        expected_size = owner._baseline[-1].size
        content = bytearray()
        while len(content) < expected_size:
            count = min(_READ_CHUNK, expected_size - len(content))
            chunk = _backend.read(handle, len(content), count)
            if type(chunk) is not bytes or not 0 < len(chunk) <= count:
                raise StartupPinError("invalid or unexpected EOF in startup HANDLE read")
            content.extend(chunk)
        owner._validate_chain()
        owner._content = bytes(content)
        owner._sha256 = hashlib.sha256(owner._content).hexdigest()
        owner._ready = True
        return owner
    except BaseException as exc:
        owner._close_preserving_exception(exc)
        raise
