"""Native, no-reparse Windows adapter for the bounded worktree tree walker."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import ntpath
import os
from pathlib import Path, PureWindowsPath

from .workspace_snapshot import (
    WorktreeTreeUnavailable,
    _WINDOWS_FILE_ATTRIBUTE_DIRECTORY,
    _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT,
    _WindowsHandleInfo,
    _build_windows_worktree_tree,
    _collect_windows_directory_entries,
    _parse_windows_symlink_reparse_buffer,
    _walk_windows_directory,
    _require_windows_directory_handle,
)


_FILE_READ_DATA = 0x0001
_FILE_LIST_DIRECTORY = 0x0001
_FILE_READ_ATTRIBUTES = 0x0080
_SYNCHRONIZE = 0x00100000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_OPEN_EXISTING = 3
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_OPEN = 1
_FILE_DIRECTORY_FILE = 0x00000001
_FILE_NON_DIRECTORY_FILE = 0x00000040
_FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
_FILE_OPEN_REPARSE_POINT = 0x00200000
_OBJ_DONT_REPARSE = 0x00001000
_FILE_BASIC_INFO_CLASS = 0
_FILE_STANDARD_INFO_CLASS = 1
_FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
_FILE_ID_INFO_CLASS = 0x12
_NATIVE_DIRECTORY_PAGE_BYTES = 1024 * 1024
_WINDOWS_WORKSPACE_SNAPSHOT_ATTEMPTS = 2
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_FSCTL_GET_REPARSE_POINT = 0x000900A8


class _FILE_BASIC_INFO(ctypes.Structure):
    _fields_ = [
        ("CreationTime", ctypes.c_int64),
        ("LastAccessTime", ctypes.c_int64),
        ("LastWriteTime", ctypes.c_int64),
        ("ChangeTime", ctypes.c_int64),
        ("FileAttributes", ctypes.c_uint32),
    ]


class _FILE_STANDARD_INFO(ctypes.Structure):
    _fields_ = [
        ("AllocationSize", ctypes.c_int64),
        ("EndOfFile", ctypes.c_int64),
        ("NumberOfLinks", ctypes.c_uint32),
        ("DeletePending", wintypes.BOOLEAN),
        ("Directory", wintypes.BOOLEAN),
    ]


class _FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", ctypes.c_uint32),
        ("ReparseTag", ctypes.c_uint32),
    ]


class _FILE_ID_INFO(ctypes.Structure):
    _fields_ = [
        ("VolumeSerialNumber", ctypes.c_uint64),
        ("FileId", ctypes.c_ubyte * 16),
    ]


class _UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", ctypes.c_void_p),
    ]


class _OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.ULONG),
        ("RootDirectory", wintypes.HANDLE),
        ("ObjectName", ctypes.POINTER(_UNICODE_STRING)),
        ("Attributes", wintypes.ULONG),
        ("SecurityDescriptor", ctypes.c_void_p),
        ("SecurityQualityOfService", ctypes.c_void_p),
    ]


class _IO_STATUS_BLOCK_UNION(ctypes.Union):
    _fields_ = [
        ("Status", ctypes.c_long),
        ("Pointer", ctypes.c_void_p),
    ]


class _IO_STATUS_BLOCK(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("u", _IO_STATUS_BLOCK_UNION),
        ("Information", ctypes.c_size_t),
    ]


class _WindowsNativeWorktreeBackend:
    """Use held directory handles and identity-checked relative child opens."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise WorktreeTreeUnavailable("unsupported_platform")
        try:
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._ntdll = ctypes.WinDLL("ntdll")
        except (AttributeError, OSError):
            raise WorktreeTreeUnavailable("windows_native_api_unavailable") from None
        self._root_handles: list[int] = []
        self._configure_apis()

    def _configure_apis(self) -> None:
        self._kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        self._kernel32.CreateFileW.restype = wintypes.HANDLE
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32.GetFileInformationByHandleEx.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        self._kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
        self._kernel32.ReadFile.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]
        self._kernel32.ReadFile.restype = wintypes.BOOL
        self._kernel32.DeviceIoControl.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        self._kernel32.DeviceIoControl.restype = wintypes.BOOL
        self._ntdll.NtCreateFile.argtypes = [
            ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
            ctypes.POINTER(_OBJECT_ATTRIBUTES), ctypes.POINTER(_IO_STATUS_BLOCK),
            ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
            wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG,
        ]
        self._ntdll.NtCreateFile.restype = ctypes.c_long

    @staticmethod
    def _handle_value(handle: object) -> int:
        value = getattr(handle, "value", handle)
        if type(value) is not int or value in (0, _INVALID_HANDLE_VALUE):
            raise WorktreeTreeUnavailable("windows_handle_invalid")
        return value

    def _native_handle(self, handle: object) -> wintypes.HANDLE:
        return wintypes.HANDLE(self._handle_value(handle))

    def open_root(self, root: Path) -> int:
        absolute_path = ntpath.abspath(str(root))
        full_path = PureWindowsPath(_normalize_extended_unc_prefix(absolute_path))
        anchor, relative_parts = self._volume_anchor_and_parts(full_path)
        anchor_handle = self._kernel32.CreateFileW(
            anchor,
            _FILE_LIST_DIRECTORY | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        try:
            current = self._handle_value(anchor_handle)
        except WorktreeTreeUnavailable:
            raise WorktreeTreeUnavailable("windows_volume_root_open_failed") from None
        self._root_handles.append(current)
        try:
            root_info = self.query_info(current)
            volume_serial_number = root_info.volume_serial_number
            _require_windows_directory_handle(root_info, volume_serial_number)
            for part in relative_parts:
                child = self._open_relative(current, part, directory=True)
                self._root_handles.append(child)
                child_info = self.query_info(child)
                _require_windows_directory_handle(child_info, volume_serial_number)
                current = child
            return current
        except Exception as exc:
            self.close_root(current)
            if isinstance(exc, WorktreeTreeUnavailable):
                raise
            raise WorktreeTreeUnavailable("windows_root_open_failed") from None

    @staticmethod
    def _volume_anchor_and_parts(path: PureWindowsPath) -> tuple[str, tuple[str, ...]]:
        if not path.is_absolute() or not path.drive:
            raise WorktreeTreeUnavailable("windows_workspace_path_invalid")
        drive = path.drive
        if len(drive) == 2 and drive[1] == ":" and drive[0].isalpha():
            anchor = "\\\\?\\" + drive + "\\"
        elif (
            drive.startswith("\\\\?\\")
            and len(drive) == 6
            and drive[-1] == ":"
            and drive[-2].isalpha()
        ):
            anchor = drive + "\\"
        elif drive.casefold().startswith("\\\\?\\unc\\"):
            components = drive[8:].split("\\")
            if len(components) != 2 or not all(components):
                raise WorktreeTreeUnavailable("windows_workspace_path_unsupported")
            anchor = "\\\\?\\UNC\\" + components[0] + "\\" + components[1] + "\\"
        elif drive.startswith("\\\\?\\Volume{") and drive.endswith("}"):
            anchor = drive + "\\"
        elif drive.startswith("\\\\"):
            components = drive.lstrip("\\").split("\\")
            if len(components) != 2 or not all(components):
                raise WorktreeTreeUnavailable("windows_workspace_path_unsupported")
            anchor = "\\\\?\\UNC\\" + components[0] + "\\" + components[1] + "\\"
        else:
            raise WorktreeTreeUnavailable("windows_workspace_path_unsupported")
        return anchor, tuple(part for part in path.parts[1:] if part not in ("", "."))

    def _open_relative(
        self,
        parent_handle: object,
        name: str,
        *,
        directory: bool,
        reparse: bool = False,
    ) -> int:
        try:
            encoded_name = name.encode("utf-16-le", errors="strict")
        except UnicodeEncodeError:
            raise WorktreeTreeUnavailable("windows_directory_name_invalid") from None
        if (
            not encoded_name
            or len(encoded_name) > 510
            or any(char in name for char in ("\x00", "/", "\\", ":"))
        ):
            raise WorktreeTreeUnavailable("windows_directory_name_invalid")
        name_storage = ctypes.create_string_buffer(encoded_name + b"\x00\x00")
        unicode_name = _UNICODE_STRING(
            len(encoded_name), len(encoded_name) + 2,
            ctypes.cast(name_storage, ctypes.c_void_p),
        )
        attributes = _OBJECT_ATTRIBUTES(
            ctypes.sizeof(_OBJECT_ATTRIBUTES),
            self._native_handle(parent_handle),
            ctypes.pointer(unicode_name),
            0 if reparse else _OBJ_DONT_REPARSE,
            None,
            None,
        )
        io_status = _IO_STATUS_BLOCK()
        opened = wintypes.HANDLE()
        desired_access = _FILE_READ_ATTRIBUTES | _SYNCHRONIZE
        share_access = _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
        create_options = _FILE_SYNCHRONOUS_IO_NONALERT | _FILE_OPEN_REPARSE_POINT
        if directory:
            desired_access |= _FILE_LIST_DIRECTORY
            create_options |= _FILE_DIRECTORY_FILE
        else:
            desired_access |= _FILE_READ_DATA
            create_options |= _FILE_NON_DIRECTORY_FILE
        status = self._ntdll.NtCreateFile(
            ctypes.byref(opened),
            desired_access,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            None,
            0,
            share_access,
            _FILE_OPEN,
            create_options,
            None,
            0,
        )
        if int(status) & 0x80000000:
            if opened.value not in (None, _INVALID_HANDLE_VALUE):
                self._kernel32.CloseHandle(opened)
            raise WorktreeTreeUnavailable("windows_relative_open_failed")
        try:
            return self._handle_value(opened)
        except WorktreeTreeUnavailable:
            raise WorktreeTreeUnavailable("windows_relative_open_failed") from None

    def query_info(self, handle: object) -> _WindowsHandleInfo:
        native = self._native_handle(handle)
        basic = _FILE_BASIC_INFO()
        standard = _FILE_STANDARD_INFO()
        attributes = _FILE_ATTRIBUTE_TAG_INFO()
        file_id = _FILE_ID_INFO()
        queries = (
            (_FILE_BASIC_INFO_CLASS, basic),
            (_FILE_STANDARD_INFO_CLASS, standard),
            (_FILE_ATTRIBUTE_TAG_INFO_CLASS, attributes),
            (_FILE_ID_INFO_CLASS, file_id),
        )
        for information_class, record in queries:
            ctypes.set_last_error(0)
            if not self._kernel32.GetFileInformationByHandleEx(
                native,
                information_class,
                ctypes.byref(record),
                ctypes.sizeof(record),
            ):
                raise WorktreeTreeUnavailable("windows_handle_query_failed")
        if int(basic.FileAttributes) != int(attributes.FileAttributes):
            raise WorktreeTreeUnavailable("windows_handle_info_inconsistent")
        reparse_tag = (
            int(attributes.ReparseTag)
            if attributes.FileAttributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT else 0
        )
        return _WindowsHandleInfo(
            volume_serial_number=int(file_id.VolumeSerialNumber),
            file_id=bytes(file_id.FileId),
            attributes=int(attributes.FileAttributes),
            reparse_tag=reparse_tag,
            change_time=int(basic.ChangeTime),
            end_of_file=int(standard.EndOfFile),
            is_directory=bool(standard.Directory),
            delete_pending=bool(standard.DeletePending),
        )

    def enumerate_directory(self, handle: object):
        native = self._native_handle(handle)

        def read_page(information_class: int, buffer_bytes: int):
            buffer = ctypes.create_string_buffer(buffer_bytes)
            ctypes.set_last_error(0)
            succeeded = bool(self._kernel32.GetFileInformationByHandleEx(
                native,
                information_class,
                ctypes.byref(buffer),
                buffer_bytes,
            ))
            winerror = 0 if succeeded else int(ctypes.get_last_error())
            return succeeded, winerror, bytes(buffer.raw)

        return _collect_windows_directory_entries(
            read_page,
            buffer_bytes=_NATIVE_DIRECTORY_PAGE_BYTES,
        )

    def open_child(
        self,
        parent_handle: object,
        entry,
        *,
        directory: bool,
        reparse: bool = False,
    ) -> int:
        return self._open_relative(
            parent_handle,
            entry.name,
            directory=directory,
            reparse=reparse,
        )

    def read_symlink_target(self, handle: object) -> str:
        buffer = ctypes.create_string_buffer(16 * 1024)
        bytes_returned = wintypes.DWORD()
        ctypes.set_last_error(0)
        if not self._kernel32.DeviceIoControl(
            self._native_handle(handle),
            _FSCTL_GET_REPARSE_POINT,
            None,
            0,
            ctypes.byref(buffer),
            len(buffer),
            ctypes.byref(bytes_returned),
            None,
        ):
            raise WorktreeTreeUnavailable("windows_symlink_read_failed")
        if bytes_returned.value > len(buffer):
            raise WorktreeTreeUnavailable("windows_symlink_buffer_invalid")
        return _parse_windows_symlink_reparse_buffer(
            bytes(buffer.raw[:bytes_returned.value]),
        )

    def read_file(self, handle: object, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        bytes_read = wintypes.DWORD()
        ctypes.set_last_error(0)
        if not self._kernel32.ReadFile(
            self._native_handle(handle),
            ctypes.byref(buffer),
            size,
            ctypes.byref(bytes_read),
            None,
        ):
            raise WorktreeTreeUnavailable("windows_file_read_failed")
        if bytes_read.value > size:
            raise WorktreeTreeUnavailable("windows_file_read_invalid")
        return bytes(buffer.raw[:bytes_read.value])

    def close_handle(self, handle: object) -> None:
        native = self._native_handle(handle)
        ctypes.set_last_error(0)
        if not self._kernel32.CloseHandle(native):
            raise WorktreeTreeUnavailable("windows_handle_close_failed")

    def close_root(self, _root_handle: object) -> None:
        handles, self._root_handles = self._root_handles, []
        first_error = False
        for handle in reversed(handles):
            try:
                self.close_handle(handle)
            except WorktreeTreeUnavailable:
                first_error = True
        if first_error:
            raise WorktreeTreeUnavailable("windows_handle_close_failed")


def _normalize_extended_unc_prefix(path: str) -> str:
    """Canonicalize the case-insensitive UNC device prefix before pathlib parsing."""
    prefix = "\\\\?\\UNC\\"
    if path[:len(prefix)].casefold() == prefix.casefold():
        return prefix + path[len(prefix):]
    return path


def worktree_git_tree_oid_windows(root: Path, *, object_format: str) -> str:
    """Hash one bounded observation of a no-reparse Windows working tree."""
    if object_format not in ("sha1", "sha256"):
        raise WorktreeTreeUnavailable("unsupported_object_format")
    backend = _WindowsNativeWorktreeBackend()
    root_handle = backend.open_root(Path(root))
    tree_digest = None
    try:
        tree_digest = _build_windows_worktree_tree(
            root_handle,
            backend,
            object_format=object_format,
        )
    except WorktreeTreeUnavailable:
        raise
    except Exception:
        raise WorktreeTreeUnavailable("windows_worktree_unavailable") from None
    finally:
        backend.close_root(root_handle)
    if tree_digest is None:
        raise WorktreeTreeUnavailable("windows_root_tree_unavailable")
    return tree_digest.hex()


def snapshot_windows_workspace_windows(root: Path) -> dict[str, str]:
    """Return a bounded, handle-relative Windows workspace observation."""
    for attempt in range(_WINDOWS_WORKSPACE_SNAPSHOT_ATTEMPTS):
        backend = _WindowsNativeWorktreeBackend()
        root_handle = backend.open_root(Path(root))
        snapshot: dict[str, str] = {}
        retry_after_close = False
        try:
            _walk_windows_directory(
                root_handle,
                backend,
                object_format=None,
                include_in_tree=False,
                snapshot_output=snapshot,
                snapshot_parts=(),
                snapshot_enabled=True,
                is_root=True,
                depth=0,
            )
        except WorktreeTreeUnavailable as exc:
            if (
                exc.reason != "windows_directory_changed"
                or attempt + 1 >= _WINDOWS_WORKSPACE_SNAPSHOT_ATTEMPTS
            ):
                raise
            # No partial hashes escape: close every handle before reopening
            # the root and rebuilding a fresh snapshot on the one retry.
            retry_after_close = True
        except Exception:
            raise WorktreeTreeUnavailable(
                "windows_workspace_snapshot_unavailable",
            ) from None
        finally:
            backend.close_root(root_handle)
        if not retry_after_close:
            return snapshot
    raise WorktreeTreeUnavailable("windows_workspace_snapshot_unavailable")
