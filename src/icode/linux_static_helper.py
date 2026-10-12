"""Private bounded static-load subcheck; never provenance or execution authority.

Borrow an existing owner without opening/closing descriptors or moving offsets.
The preparing creator remains the unique close owner, including on failure.
Trusted host callers must not close/dup2 or concurrently mutate the owner.
"""
from __future__ import annotations

import hashlib
import os
import stat
import struct
import sys

from .linux_helper_object import LinuxHelperObject, LinuxHelperObjectError
from .native_helper import linux_elf_architecture

_BINARY_LIMIT = 64 * 1024 * 1024
_READ_CHUNK = 64 * 1024
_HEADER_SIZE = 64
_PH_ENTRY_SIZE = 56
_PH_COUNT_LIMIT = 1024
_TABLE_READ_LIMIT = 64 * 1024
_FORBIDDEN_TYPES = (2, 3)  # PT_DYNAMIC, PT_INTERP; static PIE is outside this slice.


def _snapshot(status) -> tuple[int, int, int, int, int]:
    return (
        status.st_dev, status.st_ino, status.st_size,
        status.st_mtime_ns, status.st_ctime_ns,
    )


def _read_exact(fd: int, offset: int, length: int, size: int) -> bytes:
    # Validate before calling the OS; bool is not an integer contract input.
    if (type(offset) is not int or type(length) is not int or type(size) is not int
            or offset < 0 or length < 0 or length > _READ_CHUNK
            or offset > size or length > size - offset):
        raise LinuxHelperObjectError()
    data = os.pread(fd, length, offset)
    if type(data) is not bytes or len(data) != length:
        raise LinuxHelperObjectError()
    return data


def validate_static_linux_helper(owner: LinuxHelperObject) -> None:
    """Check finite ET_EXEC/no-loader shape and held digest; no factory attestation."""
    try:
        if (not sys.platform.startswith("linux")
                or not callable(getattr(os, "pread", None))
                or not isinstance(owner, LinuxHelperObject)):
            raise LinuxHelperObjectError()
        fd = owner.fileno()
        if type(fd) is not int or fd < 0:
            raise LinuxHelperObjectError()
        before = os.fstat(fd)
        size = before.st_size
        if (not stat.S_ISREG(before.st_mode) or type(size) is not int
                or size < _HEADER_SIZE or size > _BINARY_LIMIT):
            raise LinuxHelperObjectError()
        header = _read_exact(fd, 0, _HEADER_SIZE, size)
        architecture = owner.architecture
        if (type(architecture) is not str or architecture not in ("x86_64", "arm64")
                or linux_elf_architecture(header) != architecture
                or struct.unpack_from("<H", header, 16)[0] != 2):
            raise LinuxHelperObjectError()
        phoff = struct.unpack_from("<Q", header, 32)[0]
        entsize, count = struct.unpack_from("<HH", header, 54)
        table_size = entsize * count
        if (entsize != _PH_ENTRY_SIZE or not 1 <= count <= _PH_COUNT_LIMIT
                or phoff < _HEADER_SIZE or table_size > _TABLE_READ_LIMIT
                or phoff > size or table_size > size - phoff):
            raise LinuxHelperObjectError()
        table = _read_exact(fd, phoff, table_size, size)
        for offset in range(0, table_size, _PH_ENTRY_SIZE):
            if struct.unpack_from("<I", table, offset)[0] in _FORBIDDEN_TYPES:
                raise LinuxHelperObjectError()
        digest = hashlib.sha256()
        offset = 0
        while offset < size:
            count = min(_READ_CHUNK, size - offset)
            digest.update(_read_exact(fd, offset, count, size))
            offset += count
        # At most size+1 digest bytes; unexpected EOF growth is an independent refusal.
        eof = os.pread(fd, 1, size)
        if type(eof) is not bytes or eof != b"":
            raise LinuxHelperObjectError()
        if owner.fileno() != fd:
            raise LinuxHelperObjectError()
        after = os.fstat(fd)
        if (_snapshot(before) != _snapshot(after)
                or digest.hexdigest() != owner.sha256):
            raise LinuxHelperObjectError()
    except BaseException as error:
        # No parser-owned resources exist; the first signal is the original object.
        if not isinstance(error, Exception):
            raise
        raise LinuxHelperObjectError() from None
