"""Test-only Win32 primitives for researching stable worktree traversal."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from pathlib import PureWindowsPath


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


class _FileIdExtdDirectoryInfoHeader(ctypes.LittleEndianStructure):
    """Fixed FILE_ID_EXTD_DIR_INFO fields; the variable name follows this header."""

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
        ("reparse_point_tag", ctypes.c_uint32),
        ("file_id", ctypes.c_uint8 * 16),
    ]


class _FileIdInfo(ctypes.Structure):
    """FILE_ID_INFO with its volume serial and full 128-bit identifier."""

    _fields_ = [
        ("volume_serial_number", ctypes.c_uint64),
        ("file_id", ctypes.c_uint8 * 16),
    ]


_FILE_ID_BOTH_DIR_INFO_HEADER_BYTES = ctypes.sizeof(_FileIdBothDirectoryInfoHeader)
_FILE_ID_EXTD_DIR_INFO_HEADER_BYTES = ctypes.sizeof(_FileIdExtdDirectoryInfoHeader)
_MAX_DIRECTORY_ENTRIES = 250_000
_MAX_DIRECTORY_BUFFER_BYTES = 16 * 1024 * 1024
_STATUS_SUCCESS = 0
_STATUS_REPARSE_POINT_ENCOUNTERED = 0xC000050B
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
_FILE_ID_INFO_CLASS = 0x12
_FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS = 0x14


class WindowsDirectoryProbeError(RuntimeError):
    """A test-only Windows directory record could not be safely interpreted."""


def _validate_file_id(file_id: bytes) -> bytes:
    """Reject FILE_ID_128 sentinel values that do not identify an object."""

    if type(file_id) is not bytes or len(file_id) != 16:
        raise WindowsDirectoryProbeError("file_id_invalid")
    if file_id in (bytes(16), bytes([0xFF]) * 16):
        raise WindowsDirectoryProbeError("file_id_unavailable")
    return file_id


@dataclass(frozen=True)
class DirectoryInfoEntry:
    name: str
    attributes: int
    file_id: int


@dataclass(frozen=True)
class ExtendedDirectoryInfoEntry:
    name: str
    attributes: int
    reparse_tag: int
    file_id: bytes


@dataclass(frozen=True)
class NtRelativeOpenResult:
    status: int
    file_attributes: int | None
    file_id: bytes | None
    volume_serial_number: int | None


def classify_no_reparse_open_receipt(status: object, file_attributes: object) -> str:
    """Classify a native open without treating an error or reparse handle as safe."""

    if type(status) is not int or not 0 <= status <= 0xFFFFFFFF:
        return "receipt_incomplete"
    if status == _STATUS_REPARSE_POINT_ENCOUNTERED:
        return "reparse_rejected"
    if status != _STATUS_SUCCESS:
        return "native_open_failed"
    if type(file_attributes) is not int or not 0 <= file_attributes <= 0xFFFFFFFF:
        return "receipt_incomplete"
    if file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        return "reparse_opened"
    return "opened"


def open_relative_without_reparse(
    directory_handle: int,
    relative_name: str,
    *,
    directory: bool,
) -> NtRelativeOpenResult:
    """Open a disposable Windows probe entry relative to a held directory handle.

    The test-only helper combines OBJ_DONT_REPARSE with
    FILE_OPEN_REPARSE_POINT. It returns a fixed NTSTATUS, file attributes,
    volume serial number, and the full 128-bit file ID; it never reads entry
    contents or exposes the supplied name.
    """

    if type(directory_handle) is not int or directory_handle <= 0:
        raise ValueError("directory_handle_invalid")
    if type(directory) is not bool:
        raise ValueError("directory_flag_invalid")
    if not isinstance(relative_name, str) or "\x00" in relative_name:
        raise ValueError("relative_name_invalid")
    path = PureWindowsPath(relative_name)
    if (
        not relative_name
        or path.is_absolute()
        or path.drive
        or not path.parts
        or any(part in (".", "..") or ":" in part for part in path.parts)
    ):
        raise ValueError("relative_name_invalid")

    from ctypes import wintypes

    class UnicodeString(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", wintypes.LPWSTR),
        ]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.ULONG),
            ("RootDirectory", wintypes.HANDLE),
            ("ObjectName", ctypes.POINTER(UnicodeString)),
            ("Attributes", wintypes.ULONG),
            ("SecurityDescriptor", ctypes.c_void_p),
            ("SecurityQualityOfService", ctypes.c_void_p),
        ]

    class IoStatusUnion(ctypes.Union):
        _fields_ = [
            ("Status", wintypes.LONG),
            ("Pointer", ctypes.c_void_p),
        ]

    class IoStatusBlock(ctypes.Structure):
        _anonymous_ = ("Value",)
        _fields_ = [
            ("Value", IoStatusUnion),
            ("Information", ctypes.c_size_t),
        ]

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", wintypes.DWORD),
            ("ReparseTag", wintypes.DWORD),
        ]

    encoded_name = relative_name.encode("utf-16-le", errors="strict")
    if not encoded_name or len(encoded_name) + 2 > 0xFFFF:
        raise ValueError("relative_name_invalid")
    name_buffer = ctypes.create_unicode_buffer(relative_name)
    unicode_name = UnicodeString(
        len(encoded_name),
        len(encoded_name) + 2,
        ctypes.cast(name_buffer, wintypes.LPWSTR),
    )
    object_attributes = ObjectAttributes(
        ctypes.sizeof(ObjectAttributes),
        wintypes.HANDLE(directory_handle),
        ctypes.pointer(unicode_name),
        0x00000040 | 0x00001000,  # OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE
        None,
        None,
    )
    io_status = IoStatusBlock()
    file_handle = ctypes.c_void_p()

    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    nt_create_file = ntdll.NtCreateFile
    nt_create_file.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.ULONG,
        ctypes.POINTER(ObjectAttributes),
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
    ]
    nt_create_file.restype = wintypes.LONG
    access = 0x00000080 | 0x00100000  # FILE_READ_ATTRIBUTES | SYNCHRONIZE
    share = 0x00000001 | 0x00000002 | 0x00000004
    create_options = 0x00200000 | 0x00000020  # FILE_OPEN_REPARSE_POINT | synchronous
    create_options |= 0x00000001 if directory else 0x00000040
    raw_status = nt_create_file(
        ctypes.byref(file_handle),
        access,
        ctypes.byref(object_attributes),
        ctypes.byref(io_status),
        None,
        0x00000080,  # FILE_ATTRIBUTE_NORMAL
        share,
        1,  # FILE_OPEN
        create_options,
        None,
        0,
    )
    status = int(raw_status) & 0xFFFFFFFF
    if status != _STATUS_SUCCESS:
        if file_handle.value not in (None, ctypes.c_void_p(-1).value):
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle.restype = wintypes.BOOL
            if not kernel.CloseHandle(file_handle):
                raise OSError("failed_native_handle_cleanup")
        return NtRelativeOpenResult(status, None, None, None)
    if file_handle.value in (None, ctypes.c_void_p(-1).value):
        raise OSError("native_open_missing_handle")

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileInformationByHandleEx.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = wintypes.BOOL
    try:
        tag_info = FileAttributeTagInfo()
        if not kernel.GetFileInformationByHandleEx(
            file_handle,
            _FILE_ATTRIBUTE_TAG_INFO_CLASS,
            ctypes.byref(tag_info),
            ctypes.sizeof(tag_info),
        ):
            raise OSError("file_attribute_query_failed")
        file_id_info = _FileIdInfo()
        if not kernel.GetFileInformationByHandleEx(
            file_handle,
            _FILE_ID_INFO_CLASS,
            ctypes.byref(file_id_info),
            ctypes.sizeof(file_id_info),
        ):
            raise OSError("file_identity_query_failed")
        file_id = _validate_file_id(bytes(file_id_info.file_id))
        return NtRelativeOpenResult(
            status=status,
            file_attributes=int(tag_info.FileAttributes),
            file_id=file_id,
            volume_serial_number=int(file_id_info.volume_serial_number),
        )
    finally:
        if not kernel.CloseHandle(file_handle):
            raise OSError("failed_native_handle_cleanup")


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


def parse_file_id_extd_directory_info(
    buffer: bytes,
) -> tuple[ExtendedDirectoryInfoEntry, ...]:
    """Parse bounded FILE_ID_EXTD_DIR_INFO records without trusting offsets."""

    if not isinstance(buffer, bytes):
        raise WindowsDirectoryProbeError("directory_buffer_invalid")
    if len(buffer) > _MAX_DIRECTORY_BUFFER_BYTES:
        raise WindowsDirectoryProbeError("directory_buffer_too_large")
    if not buffer:
        return ()
    if _FILE_ID_EXTD_DIR_INFO_HEADER_BYTES != 88:
        raise WindowsDirectoryProbeError("directory_header_layout_invalid")

    entries: list[ExtendedDirectoryInfoEntry] = []
    record_count = 0
    offset = 0
    while offset < len(buffer):
        if len(buffer) - offset < _FILE_ID_EXTD_DIR_INFO_HEADER_BYTES:
            raise WindowsDirectoryProbeError("directory_header_truncated")

        header = _FileIdExtdDirectoryInfoHeader.from_buffer_copy(
            buffer[offset:offset + _FILE_ID_EXTD_DIR_INFO_HEADER_BYTES]
        )
        next_offset = int(header.next_entry_offset)
        attributes = int(header.file_attributes)
        name_length = int(header.file_name_length)
        reparse_tag = int(header.reparse_point_tag)
        file_id = bytes(header.file_id)
        if (
            next_offset == 0
            and name_length == 0
            and attributes == 0
            and reparse_tag == 0
            and file_id == bytes(16)
        ):
            if not entries and not any(buffer[offset:]):
                return ()
            raise WindowsDirectoryProbeError("directory_record_empty")
        file_id = _validate_file_id(file_id)
        if name_length == 0 or name_length % 2:
            raise WindowsDirectoryProbeError("directory_name_length_invalid")

        remaining = len(buffer) - offset
        record_end = offset + _FILE_ID_EXTD_DIR_INFO_HEADER_BYTES + name_length
        if record_end > len(buffer):
            raise WindowsDirectoryProbeError("directory_name_truncated")
        if next_offset and (
            next_offset % 8
            or next_offset < _FILE_ID_EXTD_DIR_INFO_HEADER_BYTES + name_length
            or next_offset >= remaining
        ):
            raise WindowsDirectoryProbeError("directory_next_offset_invalid")

        try:
            name = buffer[
                offset + _FILE_ID_EXTD_DIR_INFO_HEADER_BYTES:record_end
            ].decode("utf-16-le", errors="strict")
        except UnicodeDecodeError:
            raise WindowsDirectoryProbeError("directory_name_invalid") from None
        if (
            not name
            or "\x00" in name
            or "/" in name
            or "\\" in name
            or ":" in name
        ):
            raise WindowsDirectoryProbeError("directory_name_invalid")

        record_count += 1
        if record_count > _MAX_DIRECTORY_ENTRIES:
            raise WindowsDirectoryProbeError("directory_entry_limit")
        if name not in (".", ".."):
            entries.append(
                ExtendedDirectoryInfoEntry(name, attributes, reparse_tag, file_id)
            )

        if next_offset == 0:
            break
        offset += next_offset

    return tuple(entries)
