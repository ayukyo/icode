"""Test-only Win32 primitives for researching stable worktree traversal."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from pathlib import PureWindowsPath
from typing import Callable


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
_MAX_DIRECTORY_ENUMERATION_PAGES = 4_096
_MIN_DIRECTORY_ENUM_BUFFER_BYTES = _FILE_ID_EXTD_DIR_INFO_HEADER_BYTES + 2
_MAX_RELATIVE_FILE_READ_BYTES = 8 * 1024 * 1024
_RELATIVE_FILE_READ_CHUNK_BYTES = 64 * 1024
_STATUS_SUCCESS = 0
_STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034
_STATUS_REPARSE_POINT_ENCOUNTERED = 0xC000050B
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_FILE_ATTRIBUTE_DIRECTORY = 0x0010
_FILE_READ_DATA = 0x00000001
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
_FILE_ID_INFO_CLASS = 0x12
_FILE_ID_EXTD_DIRECTORY_INFO_CLASS = 0x13
_FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS = 0x14
_ERROR_NO_MORE_FILES = 18
_ERROR_MORE_DATA = 234


class WindowsDirectoryProbeError(RuntimeError):
    """A test-only Windows directory record could not be safely interpreted."""


def classify_namespace_operation_result(succeeded: object, winerror: object) -> str:
    """Map a native namespace operation to a bounded, non-sensitive label."""

    if type(succeeded) is not bool:
        return "receipt_incomplete"
    if succeeded:
        return "allowed"
    if type(winerror) is not int or not 1 <= winerror <= 0xFFFFFFFF:
        return "receipt_incomplete"
    if winerror == 32:  # ERROR_SHARING_VIOLATION
        return "blocked_sharing_violation"
    if winerror == 5:  # ERROR_ACCESS_DENIED
        return "blocked_access_denied"
    return "blocked_other"


def classify_directory_listing_drift(before: object, after: object) -> str:
    """Compare two bounded records from one held directory handle.

    This only detects differences between the supplied flat listings. It does
    not prove that either listing is complete or that the namespace was stable
    between calls; callers must establish those facts separately.
    """

    def signatures(entries: object) -> dict[str, tuple[int, int, bytes]] | None:
        if type(entries) is not tuple:
            return None
        result: dict[str, tuple[int, int, bytes]] = {}
        for entry in entries:
            if not isinstance(entry, ExtendedDirectoryInfoEntry):
                return None
            if (
                type(entry.attributes) is not int
                or not 0 <= entry.attributes <= 0xFFFFFFFF
                or type(entry.reparse_tag) is not int
                or not 0 <= entry.reparse_tag <= 0xFFFFFFFF
            ):
                return None
            try:
                require_enumerated_entry_name(entry, entry.name)
                file_id = _validate_file_id(entry.file_id)
            except (TypeError, ValueError, WindowsDirectoryProbeError):
                return None
            if entry.name in result:
                return None
            reparse_tag = (
                entry.reparse_tag
                if entry.attributes & _FILE_ATTRIBUTE_REPARSE_POINT
                else 0  # The API leaves this field undefined for ordinary entries.
            )
            result[entry.name] = (entry.attributes, reparse_tag, file_id)
        return result

    before_signatures = signatures(before)
    after_signatures = signatures(after)
    if before_signatures is None or after_signatures is None:
        return "receipt_incomplete"
    if before_signatures.keys() != after_signatures.keys():
        return "namespace_changed"
    if any(
        before_signatures[name] != after_signatures[name]
        for name in before_signatures
    ):
        return "entry_changed"
    return "same_observation"


def _validate_file_id(file_id: bytes) -> bytes:
    """Reject FILE_ID_128 sentinel values that do not identify an object."""

    if type(file_id) is not bytes or len(file_id) != 16:
        raise WindowsDirectoryProbeError("file_id_invalid")
    if file_id in (bytes(16), bytes([0xFF]) * 16):
        raise WindowsDirectoryProbeError("file_id_unavailable")
    return file_id


def require_enumerated_entry_name(
    entry: ExtendedDirectoryInfoEntry,
    relative_name: str,
) -> None:
    """Require a read name to be the exact single child enumerated by its parent."""

    if not isinstance(entry, ExtendedDirectoryInfoEntry):
        raise WindowsDirectoryProbeError("directory_entry_invalid")
    if not isinstance(relative_name, str) or "\x00" in relative_name:
        raise WindowsDirectoryProbeError("entry_name_changed")
    expected = PureWindowsPath(entry.name)
    requested = PureWindowsPath(relative_name)
    if (
        not entry.name
        or expected.is_absolute()
        or expected.drive
        or len(expected.parts) != 1
        or any(part in (".", "..") or ":" in part for part in expected.parts)
        or relative_name != entry.name
        or requested.is_absolute()
        or requested.drive
        or len(requested.parts) != 1
        or any(part in (".", "..") or ":" in part for part in requested.parts)
    ):
        raise WindowsDirectoryProbeError("entry_name_changed")


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
    file_contents: bytes | None = None


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


def require_enumerated_entry_identity(
    entry: ExtendedDirectoryInfoEntry,
    opened: NtRelativeOpenResult,
    expected_volume_serial_number: int,
) -> None:
    """Fail closed unless an opened child is the enumerated ordinary object.

    A caller must run this check before reading from the handle. Names are not
    compared because a controlled rename can change the current name while the
    expected record still identifies the object originally enumerated.
    """

    if not isinstance(entry, ExtendedDirectoryInfoEntry):
        raise WindowsDirectoryProbeError("directory_entry_invalid")
    if not isinstance(opened, NtRelativeOpenResult):
        raise WindowsDirectoryProbeError("entry_open_receipt_invalid")
    if (
        type(expected_volume_serial_number) is not int
        or not 0 <= expected_volume_serial_number <= 0xFFFFFFFFFFFFFFFF
    ):
        raise WindowsDirectoryProbeError("entry_volume_invalid")
    if type(entry.attributes) is not int or not 0 <= entry.attributes <= 0xFFFFFFFF:
        raise WindowsDirectoryProbeError("directory_entry_invalid")
    if type(entry.reparse_tag) is not int or not 0 <= entry.reparse_tag <= 0xFFFFFFFF:
        raise WindowsDirectoryProbeError("directory_entry_invalid")
    if (
        entry.attributes & _FILE_ATTRIBUTE_REPARSE_POINT
        or entry.reparse_tag != 0
    ):
        raise WindowsDirectoryProbeError("entry_reparse_point")

    receipt = classify_no_reparse_open_receipt(
        opened.status,
        opened.file_attributes,
    )
    if receipt == "reparse_rejected" or receipt == "reparse_opened":
        raise WindowsDirectoryProbeError("entry_reparse_point")
    if receipt == "native_open_failed":
        raise WindowsDirectoryProbeError("entry_open_failed")
    if receipt != "opened":
        raise WindowsDirectoryProbeError("entry_open_incomplete")

    enumerated_file_id = _validate_file_id(entry.file_id)
    opened_file_id = _validate_file_id(opened.file_id)
    if enumerated_file_id != opened_file_id:
        raise WindowsDirectoryProbeError("entry_identity_changed")
    if (
        type(opened.volume_serial_number) is not int
        or not 0 <= opened.volume_serial_number <= 0xFFFFFFFFFFFFFFFF
    ):
        raise WindowsDirectoryProbeError("entry_open_incomplete")
    if opened.volume_serial_number != expected_volume_serial_number:
        raise WindowsDirectoryProbeError("entry_volume_changed")
    if (
        type(opened.file_attributes) is not int
        or not 0 <= opened.file_attributes <= 0xFFFFFFFF
    ):
        raise WindowsDirectoryProbeError("entry_open_incomplete")
    if bool(entry.attributes & _FILE_ATTRIBUTE_DIRECTORY) != bool(
        opened.file_attributes & _FILE_ATTRIBUTE_DIRECTORY
    ):
        raise WindowsDirectoryProbeError("entry_type_changed")


def open_relative_without_reparse(
    directory_handle: int,
    relative_name: str,
    *,
    directory: bool,
) -> NtRelativeOpenResult:
    """Return metadata for a child opened relative to a held directory handle."""

    return _open_relative_without_reparse(
        directory_handle,
        relative_name,
        directory=directory,
        expected_entry=None,
        expected_volume_serial_number=None,
        max_file_bytes=None,
    )


def read_relative_file_if_identity_matches(
    directory_handle: int,
    relative_name: str,
    *,
    expected_entry: ExtendedDirectoryInfoEntry,
    expected_volume_serial_number: int,
    max_bytes: int,
) -> bytes:
    """Read one bounded file only after matching its enumerated handle identity.

    The open denies concurrent write/delete handles, rejects reparse objects,
    compares the full file ID plus volume serial before exposing bytes, and
    checks the same handle again afterward. This is test-only evidence, not an
    atomic namespace snapshot guarantee.
    """

    require_enumerated_entry_name(expected_entry, relative_name)
    result = _open_relative_without_reparse(
        directory_handle,
        relative_name,
        directory=False,
        expected_entry=expected_entry,
        expected_volume_serial_number=expected_volume_serial_number,
        max_file_bytes=max_bytes,
    )
    require_enumerated_entry_identity(
        expected_entry,
        result,
        expected_volume_serial_number,
    )
    if result.file_contents is None:
        raise WindowsDirectoryProbeError("relative_file_read_incomplete")
    return result.file_contents


def _read_open_file_contents(
    kernel: object,
    file_handle: ctypes.c_void_p,
    *,
    max_bytes: int,
) -> bytes:
    """Read at most max_bytes plus one sentinel byte from a native handle."""

    from ctypes import wintypes

    read_file = kernel.ReadFile  # type: ignore[attr-defined]
    read_file.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    read_file.restype = wintypes.BOOL
    output = bytearray()
    while True:
        request_size = min(
            _RELATIVE_FILE_READ_CHUNK_BYTES,
            max_bytes + 1 - len(output),
        )
        buffer = ctypes.create_string_buffer(request_size)
        bytes_read = wintypes.DWORD()
        if not read_file(
            file_handle,
            buffer,
            request_size,
            ctypes.byref(bytes_read),
            None,
        ):
            raise WindowsDirectoryProbeError("relative_file_read_failed")
        if bytes_read.value > request_size:
            raise WindowsDirectoryProbeError("relative_file_read_incomplete")
        if bytes_read.value == 0:
            return bytes(output)
        output.extend(buffer.raw[:bytes_read.value])
        if len(output) > max_bytes:
            raise WindowsDirectoryProbeError("relative_file_too_large")


def _open_relative_without_reparse(
    directory_handle: int,
    relative_name: str,
    *,
    directory: bool,
    expected_entry: ExtendedDirectoryInfoEntry | None,
    expected_volume_serial_number: int | None,
    max_file_bytes: int | None,
) -> NtRelativeOpenResult:
    """Open a disposable Windows probe entry relative to a held directory handle.

    The test-only helper combines OBJ_DONT_REPARSE with
    FILE_OPEN_REPARSE_POINT. It returns a fixed NTSTATUS, file attributes,
    volume serial number, and the full 128-bit file ID. Content reads are
    available only when an enumerated identity and byte limit are supplied.
    """

    if type(directory_handle) is not int or directory_handle <= 0:
        raise ValueError("directory_handle_invalid")
    if type(directory) is not bool:
        raise ValueError("directory_flag_invalid")
    if max_file_bytes is None:
        if expected_entry is not None or expected_volume_serial_number is not None:
            raise WindowsDirectoryProbeError("read_identity_required")
    else:
        if directory:
            raise WindowsDirectoryProbeError("relative_read_requires_file")
        if not isinstance(expected_entry, ExtendedDirectoryInfoEntry):
            raise WindowsDirectoryProbeError("directory_entry_invalid")
        if (
            type(expected_volume_serial_number) is not int
            or not 0 <= expected_volume_serial_number <= 0xFFFFFFFFFFFFFFFF
        ):
            raise WindowsDirectoryProbeError("entry_volume_invalid")
        if (
            type(max_file_bytes) is not int
            or not 1 <= max_file_bytes <= _MAX_RELATIVE_FILE_READ_BYTES
        ):
            raise WindowsDirectoryProbeError("relative_read_limit_invalid")
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
    if max_file_bytes is not None:
        access |= _FILE_READ_DATA
    share = (
        _FILE_SHARE_READ
        if max_file_bytes is not None
        else _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
    )  # Bounded reads deny concurrent write/delete handle opens.
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
        opened_result = NtRelativeOpenResult(
            status=status,
            file_attributes=int(tag_info.FileAttributes),
            file_id=file_id,
            volume_serial_number=int(file_id_info.volume_serial_number),
        )
        if max_file_bytes is not None:
            assert expected_entry is not None
            assert expected_volume_serial_number is not None
            require_enumerated_entry_identity(
                expected_entry,
                opened_result,
                expected_volume_serial_number,
            )
            file_contents = _read_open_file_contents(
                kernel,
                file_handle,
                max_bytes=max_file_bytes,
            )
            current_tag_info = FileAttributeTagInfo()
            if not kernel.GetFileInformationByHandleEx(
                file_handle,
                _FILE_ATTRIBUTE_TAG_INFO_CLASS,
                ctypes.byref(current_tag_info),
                ctypes.sizeof(current_tag_info),
            ):
                raise WindowsDirectoryProbeError("file_attribute_recheck_failed")
            current_file_id_info = _FileIdInfo()
            if not kernel.GetFileInformationByHandleEx(
                file_handle,
                _FILE_ID_INFO_CLASS,
                ctypes.byref(current_file_id_info),
                ctypes.sizeof(current_file_id_info),
            ):
                raise WindowsDirectoryProbeError("file_identity_recheck_failed")
            current_handle = NtRelativeOpenResult(
                status=status,
                file_attributes=int(current_tag_info.FileAttributes),
                file_id=_validate_file_id(bytes(current_file_id_info.file_id)),
                volume_serial_number=int(
                    current_file_id_info.volume_serial_number
                ),
            )
            require_enumerated_entry_identity(
                expected_entry,
                current_handle,
                expected_volume_serial_number,
            )
            return NtRelativeOpenResult(
                status=status,
                file_attributes=opened_result.file_attributes,
                file_id=opened_result.file_id,
                volume_serial_number=opened_result.volume_serial_number,
                file_contents=file_contents,
            )
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


def collect_extd_directory_entries(
    read_page: Callable[[int, int], tuple[bool, int, bytes]],
    *,
    buffer_bytes: int,
) -> tuple[ExtendedDirectoryInfoEntry, ...]:
    """Collect one held directory handle's bounded ExtdDirectoryInfo pages.

    The caller supplies a test-only Win32 page reader bound to one open handle.
    A fresh scan starts with the restart information class; subsequent calls
    continue with the ordinary information class. EOF candidates are limited
    to ERROR_NO_MORE_FILES or a strictly zero-filled successful response;
    one nonzero restart page with no usable entries may continue once. This
    does not lock the namespace or make the returned entries a point-in-time
    snapshot.
    """

    if not callable(read_page):
        raise WindowsDirectoryProbeError("directory_page_reader_invalid")
    if (
        type(buffer_bytes) is not int
        or not _MIN_DIRECTORY_ENUM_BUFFER_BYTES <= buffer_bytes
        <= _MAX_DIRECTORY_BUFFER_BYTES
    ):
        raise WindowsDirectoryProbeError("directory_buffer_size_invalid")

    entries: list[ExtendedDirectoryInfoEntry] = []
    names: set[str] = set()
    information_class = _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS
    api_calls = 0
    while True:
        if api_calls >= _MAX_DIRECTORY_ENUMERATION_PAGES:
            raise WindowsDirectoryProbeError("directory_page_limit")
        api_calls += 1
        try:
            response = read_page(information_class, buffer_bytes)
        except Exception:
            raise WindowsDirectoryProbeError("directory_enumeration_failed") from None
        if type(response) is not tuple or len(response) != 3:
            raise WindowsDirectoryProbeError("directory_page_response_invalid")

        succeeded, winerror, payload = response
        if (
            type(succeeded) is not bool
            or type(winerror) is not int
            or not 0 <= winerror <= 0xFFFFFFFF
            or type(payload) is not bytes
            or len(payload) > buffer_bytes
            or (succeeded and winerror != 0)
            or (not succeeded and winerror == 0)
        ):
            raise WindowsDirectoryProbeError("directory_page_response_invalid")
        if not succeeded:
            if winerror == _ERROR_NO_MORE_FILES:
                return tuple(entries)
            if winerror == _ERROR_MORE_DATA:
                raise WindowsDirectoryProbeError("directory_buffer_too_small")
            raise WindowsDirectoryProbeError("directory_enumeration_failed")

        page = parse_file_id_extd_directory_info(payload)
        if not page:
            if (
                information_class
                == _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS
                and api_calls == 1
                and not entries
                and any(payload)
            ):
                # The restart response can contain only dot entries, which
                # the parser intentionally filters. Continue once with the
                # ordinary class instead of treating it as EOF or looping.
                information_class = _FILE_ID_EXTD_DIRECTORY_INFO_CLASS
                continue
            if not any(payload):
                if api_calls == 1 and not entries:
                    return ()
                if entries:
                    # Keep this candidate narrow: some providers may signal EOF
                    # with a successful zero-filled buffer after useful entries.
                    # Native CI records the terminal response shape; nonzero
                    # filtered or malformed pages remain a no-progress failure.
                    return tuple(entries)
            raise WindowsDirectoryProbeError("directory_enumeration_no_progress")
        for entry in page:
            if entry.name in names:
                raise WindowsDirectoryProbeError("directory_duplicate_name")
            names.add(entry.name)
            if len(names) > _MAX_DIRECTORY_ENTRIES:
                raise WindowsDirectoryProbeError("directory_entry_limit")
            entries.append(entry)
        information_class = _FILE_ID_EXTD_DIRECTORY_INFO_CLASS
