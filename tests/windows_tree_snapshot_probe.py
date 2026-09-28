"""Test-only Win32 primitives for researching stable worktree traversal."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes


class _FileIdBothDirectoryInfoHeader(ctypes.LittleEndianStructure):
    """Fixed FILE_ID_BOTH_DIR_INFO fields; the variable name follows this header."""

    _fields_ = [
        ("next_entry_offset", ctypes.c_uint32),
        ("file_index", ctypes.c_uint32),
        ("creation_time", ctypes.c_int64),
        ("last_access_time", ctypes.c_int64),
        ("last_write_time", ctypes.c_int64),
        ("change_time", ctypes.c_int64),
        ("end_of_file", ctypes.c_int64),
        ("allocation_size", ctypes.c_int64),
        ("file_attributes", ctypes.c_uint32),
        ("file_name_length", ctypes.c_uint32),
        ("ea_size", ctypes.c_uint32),
        ("short_name_length", ctypes.c_int8),
        ("reserved", ctypes.c_uint8),
        ("short_name", ctypes.c_uint16 * 12),
        ("file_id", ctypes.c_uint64),
    ]


_FILE_ID_BOTH_DIR_INFO_HEADER_BYTES = ctypes.sizeof(_FileIdBothDirectoryInfoHeader)
_MAX_DIRECTORY_ENTRIES = 250_000
_MAX_DIRECTORY_BUFFER_BYTES = 16 * 1024 * 1024


class WindowsDirectoryProbeError(RuntimeError):
    """A test-only Windows directory record could not be safely interpreted."""


@dataclass(frozen=True)
class DirectoryInfoEntry:
    name: str
    attributes: int
    file_id: int


def parse_file_id_both_directory_info(buffer: bytes) -> tuple[DirectoryInfoEntry, ...]:
    """Parse bounded FILE_ID_BOTH_DIR_INFO records without trusting offsets."""

    if len(buffer) > _MAX_DIRECTORY_BUFFER_BYTES:
        raise WindowsDirectoryProbeError("directory_buffer_too_large")
    if not buffer:
        return ()

    entries: list[DirectoryInfoEntry] = []
    offset = 0
    while offset < len(buffer):
        if len(buffer) - offset < _FILE_ID_BOTH_DIR_INFO_HEADER_BYTES:
            raise WindowsDirectoryProbeError("directory_header_truncated")

        header = _FileIdBothDirectoryInfoHeader.from_buffer_copy(
            buffer[offset:offset + _FILE_ID_BOTH_DIR_INFO_HEADER_BYTES]
        )
        next_offset = int(header.next_entry_offset)
        attributes = int(header.file_attributes)
        name_length = int(header.file_name_length)
        file_id = int(header.file_id)
        if next_offset == 0 and name_length == 0 and attributes == 0 and file_id == 0:
            if not entries and not any(buffer[offset:]):
                return ()
            raise WindowsDirectoryProbeError("directory_record_empty")
        if name_length == 0 or name_length % 2:
            raise WindowsDirectoryProbeError("directory_name_length_invalid")

        record_end = offset + _FILE_ID_BOTH_DIR_INFO_HEADER_BYTES + name_length
        if record_end > len(buffer):
            raise WindowsDirectoryProbeError("directory_name_truncated")
        if next_offset:
            if (
                next_offset % 8
                or next_offset < _FILE_ID_BOTH_DIR_INFO_HEADER_BYTES + name_length
                or offset + next_offset > len(buffer)
            ):
                raise WindowsDirectoryProbeError("directory_next_offset_invalid")

        try:
            name = buffer[
                offset + _FILE_ID_BOTH_DIR_INFO_HEADER_BYTES:record_end
            ].decode("utf-16-le", errors="strict")
        except UnicodeDecodeError:
            raise WindowsDirectoryProbeError("directory_name_invalid") from None
        if not name or "\x00" in name or "/" in name or "\\" in name:
            raise WindowsDirectoryProbeError("directory_name_invalid")
        if name not in (".", ".."):
            entries.append(DirectoryInfoEntry(name, attributes, file_id))
            if len(entries) > _MAX_DIRECTORY_ENTRIES:
                raise WindowsDirectoryProbeError("directory_entry_limit")

        if next_offset == 0:
            break
        offset += next_offset

    return tuple(entries)
