"""宿主侧工作区改动快照；不能跟随不可信源码中的链接。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path


_MAX_GIT_TREE_ENTRIES = 250_000
_MAX_GIT_TREE_DEPTH = 128
_MAX_GIT_TREE_BYTES = 256 * 1024 * 1024
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = stat.FILE_ATTRIBUTE_REPARSE_POINT
_WINDOWS_EXTD_DIRECTORY_ENTRY_HEADER_SIZE = 88
_WINDOWS_FILE_NAME_MAX_UTF16_BYTES = 510
_WINDOWS_FILE_ID_EXTD_DIRECTORY_INFO_CLASS = 0x13
_WINDOWS_FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS = 0x14
_WINDOWS_ERROR_NO_MORE_FILES = 18
_WINDOWS_ERROR_MORE_DATA = 234
_MAX_WINDOWS_DIRECTORY_ENTRIES = _MAX_GIT_TREE_ENTRIES
_MAX_WINDOWS_DIRECTORY_ENUMERATION_PAGES = 4_096
_MAX_WINDOWS_DIRECTORY_BUFFER_BYTES = 16 * 1024 * 1024
_MIN_WINDOWS_DIRECTORY_BUFFER_BYTES = _WINDOWS_EXTD_DIRECTORY_ENTRY_HEADER_SIZE + 2
_WINDOWS_FILE_ATTRIBUTE_DIRECTORY = 0x10
_WINDOWS_FILE_ATTRIBUTE_DEVICE = 0x40
_WINDOWS_SYMLINK_REPARSE_TAG = 0xA000000C
_WINDOWS_SYMLINK_FLAG_RELATIVE = 0x00000001
_WINDOWS_MAX_REPARSE_BUFFER_BYTES = 16 * 1024
_WINDOWS_MAX_FILE_READ_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class _WindowsDirectoryEntry:
    """Git-relevant metadata from one FILE_ID_EXTD_DIR_INFO record."""

    name: str
    attributes: int
    reparse_tag: int
    file_id: bytes
    change_time: int
    end_of_file: int


@dataclass(frozen=True, slots=True)
class _WindowsHandleInfo:
    """Stable identity and type information queried from one open handle."""

    volume_serial_number: int
    file_id: bytes
    attributes: int
    reparse_tag: int
    change_time: int
    end_of_file: int
    is_directory: bool
    delete_pending: bool


class WorktreeTreeUnavailable(RuntimeError):
    """当前工作树不能安全、完整地表示为 Git tree。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _parse_windows_directory_entries(
    buffer: bytes | bytearray | memoryview,
) -> tuple[_WindowsDirectoryEntry, ...]:
    """Parse one bounded FileIdExtdDirectory* page; reject ambiguous records."""
    if not isinstance(buffer, (bytes, bytearray, memoryview)):
        raise WorktreeTreeUnavailable("windows_directory_buffer_invalid")
    try:
        view = memoryview(buffer)
        if not view.c_contiguous:
            raise ValueError("directory page buffer is not contiguous")
        view = view.cast("B")
    except (TypeError, ValueError):
        raise WorktreeTreeUnavailable("windows_directory_buffer_invalid") from None
    if len(view) > 1024 * 1024:
        raise WorktreeTreeUnavailable("windows_directory_buffer_too_large")
    if not view or not any(view):
        return ()

    entries: list[_WindowsDirectoryEntry] = []
    names: set[str] = set()
    offset = 0
    while offset < len(view):
        remaining = len(view) - offset
        if remaining < _WINDOWS_EXTD_DIRECTORY_ENTRY_HEADER_SIZE:
            if not any(view[offset:]):
                break
            raise WorktreeTreeUnavailable("windows_directory_record_truncated")

        next_entry_offset = int.from_bytes(view[offset:offset + 4], "little")
        change_time = int.from_bytes(view[offset + 32:offset + 40], "little", signed=True)
        end_of_file = int.from_bytes(view[offset + 40:offset + 48], "little", signed=True)
        attributes = int.from_bytes(view[offset + 56:offset + 60], "little")
        name_length = int.from_bytes(view[offset + 60:offset + 64], "little")
        reparse_tag = int.from_bytes(view[offset + 68:offset + 72], "little")
        if not attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT:
            # FILE_ID_EXTD_DIR_INFO defines this field only for reparse points.
            reparse_tag = 0
        file_id = bytes(view[offset + 72:offset + 88])

        if (
            name_length == 0
            or name_length > _WINDOWS_FILE_NAME_MAX_UTF16_BYTES
            or name_length % 2 != 0
            or name_length > remaining - _WINDOWS_EXTD_DIRECTORY_ENTRY_HEADER_SIZE
            or change_time < 0
            or end_of_file < 0
            or file_id in (bytes(16), bytes([0xFF]) * 16)
        ):
            raise WorktreeTreeUnavailable("windows_directory_record_invalid")

        name_start = offset + _WINDOWS_EXTD_DIRECTORY_ENTRY_HEADER_SIZE
        name_end = name_start + name_length
        try:
            name = bytes(view[name_start:name_end]).decode("utf-16-le", errors="strict")
        except UnicodeDecodeError:
            raise WorktreeTreeUnavailable("windows_directory_name_invalid") from None
        if (
            "\x00" in name
            or "/" in name
            or "\\" in name
            or ":" in name
            or name in ("", ".", "..")
        ):
            if name in (".", ".."):
                name = ""
            else:
                raise WorktreeTreeUnavailable("windows_directory_name_invalid")

        if name:
            if name in names:
                raise WorktreeTreeUnavailable("windows_directory_name_duplicate")
            names.add(name)
            entries.append(_WindowsDirectoryEntry(
                name=name,
                attributes=attributes,
                reparse_tag=reparse_tag,
                file_id=file_id,
                change_time=change_time,
                end_of_file=end_of_file,
            ))

        record_end = name_end
        if next_entry_offset == 0:
            if any(view[record_end:]):
                raise WorktreeTreeUnavailable("windows_directory_record_trailing_data")
            break
        if (
            next_entry_offset % 8 != 0
            or next_entry_offset < _WINDOWS_EXTD_DIRECTORY_ENTRY_HEADER_SIZE + name_length
            or next_entry_offset > remaining
        ):
            raise WorktreeTreeUnavailable("windows_directory_offset_invalid")
        offset += next_entry_offset

    return tuple(entries)


def _parse_windows_symlink_reparse_buffer(buffer: bytes) -> str:
    """Return the substitute name from one bounded symbolic-link reparse record."""
    if type(buffer) is not bytes or len(buffer) < 22:
        raise WorktreeTreeUnavailable("windows_symlink_buffer_invalid")
    if len(buffer) > _WINDOWS_MAX_REPARSE_BUFFER_BYTES:
        raise WorktreeTreeUnavailable("windows_symlink_buffer_too_large")

    tag = int.from_bytes(buffer[0:4], "little")
    data_length = int.from_bytes(buffer[4:6], "little")
    if tag != _WINDOWS_SYMLINK_REPARSE_TAG:
        raise WorktreeTreeUnavailable("windows_symlink_tag_unsupported")
    if data_length < 14 or data_length + 8 != len(buffer):
        raise WorktreeTreeUnavailable("windows_symlink_buffer_invalid")

    substitute_offset = int.from_bytes(buffer[8:10], "little")
    substitute_length = int.from_bytes(buffer[10:12], "little")
    print_offset = int.from_bytes(buffer[12:14], "little")
    print_length = int.from_bytes(buffer[14:16], "little")
    flags = int.from_bytes(buffer[16:20], "little")
    path_buffer = buffer[20:]
    if (
        flags & ~_WINDOWS_SYMLINK_FLAG_RELATIVE
        or substitute_length == 0
        or substitute_offset % 2 != 0
        or substitute_length % 2 != 0
        or print_offset % 2 != 0
        or print_length % 2 != 0
        or substitute_offset + substitute_length > len(path_buffer)
        or print_offset + print_length > len(path_buffer)
    ):
        raise WorktreeTreeUnavailable("windows_symlink_buffer_invalid")
    try:
        target = path_buffer[
            substitute_offset:substitute_offset + substitute_length
        ].decode("utf-16-le", errors="strict")
    except UnicodeDecodeError:
        raise WorktreeTreeUnavailable("windows_symlink_target_invalid") from None
    if not target or "\x00" in target:
        raise WorktreeTreeUnavailable("windows_symlink_target_invalid")
    return target


def _collect_windows_directory_entries(
    read_page,
    *,
    buffer_bytes: int,
) -> tuple[_WindowsDirectoryEntry, ...]:
    """Collect bounded directory pages from one held Windows directory handle.

    ``read_page`` is the native adapter for ``GetFileInformationByHandleEx``;
    this state machine validates each response and never treats an ambiguous
    successful empty page as EOF. A fresh scan restarts once, then continues.
    The result is an observed listing, not a point-in-time namespace snapshot.
    """
    if not callable(read_page):
        raise WorktreeTreeUnavailable("windows_directory_page_reader_invalid")
    if (
        type(buffer_bytes) is not int
        or not _MIN_WINDOWS_DIRECTORY_BUFFER_BYTES <= buffer_bytes
        <= _MAX_WINDOWS_DIRECTORY_BUFFER_BYTES
    ):
        raise WorktreeTreeUnavailable("windows_directory_buffer_size_invalid")

    entries: list[_WindowsDirectoryEntry] = []
    names: set[str] = set()
    information_class = _WINDOWS_FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS
    api_calls = 0
    while True:
        if api_calls >= _MAX_WINDOWS_DIRECTORY_ENUMERATION_PAGES:
            raise WorktreeTreeUnavailable("windows_directory_page_limit")
        api_calls += 1
        try:
            response = read_page(information_class, buffer_bytes)
        except Exception:
            raise WorktreeTreeUnavailable(
                "windows_directory_enumeration_failed",
            ) from None
        if type(response) is not tuple or len(response) != 3:
            raise WorktreeTreeUnavailable("windows_directory_page_response_invalid")

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
            raise WorktreeTreeUnavailable("windows_directory_page_response_invalid")
        if not succeeded:
            if winerror == _WINDOWS_ERROR_NO_MORE_FILES:
                return tuple(entries)
            if winerror == _WINDOWS_ERROR_MORE_DATA:
                raise WorktreeTreeUnavailable("windows_directory_buffer_too_small")
            raise WorktreeTreeUnavailable("windows_directory_enumeration_failed")

        page = _parse_windows_directory_entries(payload)
        if not page:
            if (
                information_class
                == _WINDOWS_FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS
                and api_calls == 1
                and not entries
                and any(payload)
            ):
                # A restart page containing only dot entries is not EOF.
                information_class = _WINDOWS_FILE_ID_EXTD_DIRECTORY_INFO_CLASS
                continue
            raise WorktreeTreeUnavailable("windows_directory_enumeration_no_progress")

        for entry in page:
            if entry.name in names:
                raise WorktreeTreeUnavailable("windows_directory_name_duplicate")
            names.add(entry.name)
            if len(names) > _MAX_WINDOWS_DIRECTORY_ENTRIES:
                raise WorktreeTreeUnavailable("windows_directory_entry_limit")
            entries.append(entry)
        information_class = _WINDOWS_FILE_ID_EXTD_DIRECTORY_INFO_CLASS


def _build_windows_worktree_tree(
    directory_handle,
    backend,
    *,
    object_format: str,
    is_root: bool = True,
    depth: int = 0,
    entry_counter: list[int] | None = None,
    byte_counter: list[int] | None = None,
    root_volume_serial_number: int | None = None,
) -> bytes | None:
    """Build a bounded Git tree using the shared identity-checked walker."""
    return _walk_windows_directory(
        directory_handle,
        backend,
        object_format=object_format,
        include_in_tree=True,
        snapshot_output=None,
        snapshot_parts=(),
        snapshot_enabled=False,
        is_root=is_root,
        depth=depth,
        entry_counter=entry_counter,
        byte_counter=byte_counter,
        root_volume_serial_number=root_volume_serial_number,
    )


def _walk_windows_directory(
    directory_handle,
    backend,
    *,
    object_format: str | None,
    include_in_tree: bool,
    snapshot_output: dict[str, str] | None,
    snapshot_parts: tuple[str, ...],
    snapshot_enabled: bool,
    is_root: bool,
    depth: int,
    entry_counter: list[int] | None = None,
    byte_counter: list[int] | None = None,
    root_volume_serial_number: int | None = None,
) -> bytes | None:
    """Walk one observed Windows directory for both R3 evidence projections.

    ``snapshot_output`` uses the same held handles, relative opens, identity
    checks, entry/depth/page bounds and before/after listings as the optional
    Git-tree output. It intentionally includes root ``.git`` metadata, matching
    the existing workspace diff projection; a Git tree projection excludes it.
    The 256 MiB aggregate content budget applies only to Git-tree construction.
    Workspace snapshots stream the existing full-content projection in bounded
    chunks so large root ``.git`` packs do not make ordinary snapshots fail.
    """
    if object_format is not None and object_format not in ("sha1", "sha256"):
        raise WorktreeTreeUnavailable("unsupported_object_format")
    if include_in_tree and object_format is None:
        raise WorktreeTreeUnavailable("unsupported_object_format")
    if snapshot_output is not None and type(snapshot_output) is not dict:
        raise WorktreeTreeUnavailable("windows_snapshot_output_invalid")
    if depth > _MAX_GIT_TREE_DEPTH:
        raise WorktreeTreeUnavailable("worktree_too_deep")
    if entry_counter is None:
        entry_counter = [0]
    if byte_counter is None:
        byte_counter = [0]

    try:
        initial_info = backend.query_info(directory_handle)
    except WorktreeTreeUnavailable:
        raise
    except Exception:
        raise WorktreeTreeUnavailable("windows_handle_query_failed") from None
    if not isinstance(initial_info, _WindowsHandleInfo):
        raise WorktreeTreeUnavailable("windows_handle_info_invalid")
    if root_volume_serial_number is None:
        root_volume_serial_number = initial_info.volume_serial_number
    _require_windows_directory_handle(
        initial_info, root_volume_serial_number,
    )

    try:
        entries_before = backend.enumerate_directory(directory_handle)
    except WorktreeTreeUnavailable:
        raise
    except Exception:
        raise WorktreeTreeUnavailable("windows_directory_enumeration_failed") from None
    _validate_windows_directory_listing(entries_before)
    tree_entries: list[tuple[bytes, bool, bytes, bytes]] = []
    for entry in entries_before:
        entry_in_tree = include_in_tree and not (is_root and entry.name == ".git")
        entry_in_snapshot = (
            snapshot_output is not None
            and snapshot_enabled
            and entry.name not in {".icode_output", "__pycache__"}
        )
        snapshot_path = (
            Path(*snapshot_parts, entry.name).as_posix()
            if entry_in_snapshot else None
        )
        if not entry_in_tree and not entry_in_snapshot:
            if snapshot_output is not None:
                _validate_windows_ignored_snapshot_entry(entry)
            continue
        if entry.name == ".git" and not is_root and entry_in_tree:
            raise WorktreeTreeUnavailable("nested_git_metadata")
        name = _windows_git_name_bytes(entry.name)
        if entry.attributes & _WINDOWS_FILE_ATTRIBUTE_DEVICE:
            raise WorktreeTreeUnavailable("unsupported_filesystem_entry")

        entry_counter[0] += 1
        if entry_counter[0] > _MAX_GIT_TREE_ENTRIES:
            raise WorktreeTreeUnavailable("worktree_too_large")
        is_directory = bool(entry.attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY)
        is_reparse_point = bool(
            entry.attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        )

        if is_reparse_point:
            if entry.reparse_tag != _WINDOWS_SYMLINK_REPARSE_TAG:
                raise WorktreeTreeUnavailable("windows_reparse_point_unsupported")
            try:
                link_handle = backend.open_child(
                    directory_handle,
                    entry,
                    directory=is_directory,
                    reparse=True,
                )
            except WorktreeTreeUnavailable:
                raise
            except Exception:
                raise WorktreeTreeUnavailable("windows_relative_open_failed") from None
            try:
                link_info = backend.query_info(link_handle)
                _require_windows_symlink_identity(
                    entry, link_info, root_volume_serial_number,
                )
                try:
                    target = backend.read_symlink_target(link_handle)
                except WorktreeTreeUnavailable:
                    raise
                except Exception:
                    raise WorktreeTreeUnavailable(
                        "windows_symlink_read_failed",
                    ) from None
                if not isinstance(target, str) or not target or "\x00" in target:
                    raise WorktreeTreeUnavailable("windows_symlink_target_invalid")
                try:
                    target_bytes = os.fsencode(target)
                except (UnicodeEncodeError, TypeError):
                    raise WorktreeTreeUnavailable(
                        "windows_symlink_target_invalid",
                    ) from None
                if entry_in_tree:
                    byte_counter[0] += len(target_bytes)
                    if byte_counter[0] > _MAX_GIT_TREE_BYTES:
                        raise WorktreeTreeUnavailable("worktree_too_large")
                final_link_info = backend.query_info(link_handle)
                _require_windows_symlink_identity(
                    entry, final_link_info, root_volume_serial_number,
                )
                if _windows_handle_signature(link_info) != _windows_handle_signature(
                    final_link_info,
                ):
                    raise WorktreeTreeUnavailable("windows_file_changed")
                if entry_in_tree:
                    assert object_format is not None
                    digest = _git_object_digest(
                        object_format, b"blob", len(target_bytes),
                    )
                    digest.update(target_bytes)
                    tree_entries.append((name, False, b"120000", digest.digest()))
                if snapshot_path is not None and snapshot_output is not None:
                    snapshot_output[snapshot_path] = _entry_hash(
                        "symlink", "120000", target_bytes,
                    )
            finally:
                _close_windows_backend_handle(backend, link_handle)
            continue

        try:
            child_handle = backend.open_child(
                directory_handle, entry, directory=is_directory,
            )
        except WorktreeTreeUnavailable:
            raise
        except Exception:
            raise WorktreeTreeUnavailable("windows_relative_open_failed") from None

        try:
            child_info = backend.query_info(child_handle)
            _require_windows_entry_identity(
                entry, child_info, root_volume_serial_number,
                is_directory=is_directory,
            )
            if is_directory:
                child_oid = _walk_windows_directory(
                    child_handle, backend, object_format=object_format,
                    include_in_tree=entry_in_tree,
                    snapshot_output=snapshot_output,
                    snapshot_parts=(*snapshot_parts, entry.name),
                    snapshot_enabled=entry_in_snapshot,
                    is_root=False, depth=depth + 1,
                    entry_counter=entry_counter, byte_counter=byte_counter,
                    root_volume_serial_number=root_volume_serial_number,
                )
                after_info = backend.query_info(child_handle)
                _require_windows_entry_identity(
                    entry, after_info, root_volume_serial_number,
                    is_directory=True,
                )
                if entry_in_tree and child_oid is not None:
                    tree_entries.append((name, True, b"40000", child_oid))
            else:
                child_oid = _hash_windows_worktree_blob(
                    child_handle, backend, entry, child_info,
                    object_format=object_format,
                    include_in_tree=entry_in_tree,
                    root_volume_serial_number=root_volume_serial_number,
                    byte_counter=byte_counter,
                    snapshot_output=(snapshot_output if snapshot_path is not None else None),
                    snapshot_path=snapshot_path,
                )
                if entry_in_tree:
                    assert child_oid is not None
                    tree_entries.append((name, False, b"100644", child_oid))
        finally:
            _close_windows_backend_handle(backend, child_handle)

    try:
        entries_after = backend.enumerate_directory(directory_handle)
    except WorktreeTreeUnavailable:
        raise
    except Exception:
        raise WorktreeTreeUnavailable("windows_directory_enumeration_failed") from None
    _validate_windows_directory_listing(entries_after)
    if snapshot_output is None and is_root:
        observed_entries = tuple(
            entry for entry in entries_before if entry.name != ".git"
        )
        observed_entries_after = tuple(
            entry for entry in entries_after if entry.name != ".git"
        )
    else:
        observed_entries = entries_before
        observed_entries_after = entries_after
    if _windows_directory_listing_signature(observed_entries) != (
        _windows_directory_listing_signature(observed_entries_after)
    ):
        raise WorktreeTreeUnavailable("windows_directory_changed")
    try:
        final_info = backend.query_info(directory_handle)
    except WorktreeTreeUnavailable:
        raise
    except Exception:
        raise WorktreeTreeUnavailable("windows_handle_query_failed") from None
    _require_windows_directory_handle(final_info, root_volume_serial_number)
    if _windows_handle_signature(initial_info) != _windows_handle_signature(final_info):
        raise WorktreeTreeUnavailable("windows_directory_changed")

    if not include_in_tree:
        return None
    tree_entries.sort(key=lambda item: item[0] + (b"/" if item[1] else b""))
    if not tree_entries and not is_root:
        return None
    tree_body = b"".join(
        mode + b" " + name + b"\0" + oid
        for name, _is_directory, mode, oid in tree_entries
    )
    return _hash_git_tree_body(object_format, tree_body)


def _hash_windows_worktree_blob(
    file_handle,
    backend,
    entry: _WindowsDirectoryEntry,
    initial_info: _WindowsHandleInfo,
    *,
    object_format: str | None,
    include_in_tree: bool,
    root_volume_serial_number: int,
    byte_counter: list[int],
    snapshot_output: dict[str, str] | None,
    snapshot_path: str | None,
) -> bytes | None:
    size = entry.end_of_file
    if size < 0:
        raise WorktreeTreeUnavailable("worktree_too_large")
    if include_in_tree:
        byte_counter[0] += size
        if byte_counter[0] > _MAX_GIT_TREE_BYTES:
            raise WorktreeTreeUnavailable("worktree_too_large")
    git_digest = (
        _git_object_digest(object_format, b"blob", size)
        if include_in_tree and object_format is not None else None
    )
    snapshot_digest = (
        hashlib.sha256(_entry_hash_prefix("file", "100644"))
        if snapshot_output is not None and snapshot_path is not None else None
    )
    if git_digest is None and snapshot_digest is None:
        raise WorktreeTreeUnavailable("windows_snapshot_projection_missing")
    bytes_read = 0
    while bytes_read < size:
        request_size = min(_WINDOWS_MAX_FILE_READ_CHUNK_BYTES, size - bytes_read)
        try:
            chunk = backend.read_file(file_handle, request_size)
        except WorktreeTreeUnavailable:
            raise
        except Exception:
            raise WorktreeTreeUnavailable("windows_file_read_failed") from None
        if type(chunk) is not bytes or not chunk or len(chunk) > request_size:
            raise WorktreeTreeUnavailable("windows_file_size_changed")
        bytes_read += len(chunk)
        if git_digest is not None:
            git_digest.update(chunk)
        if snapshot_digest is not None:
            snapshot_digest.update(chunk)
    if bytes_read != size:
        raise WorktreeTreeUnavailable("windows_file_size_changed")
    try:
        final_info = backend.query_info(file_handle)
    except WorktreeTreeUnavailable:
        raise
    except Exception:
        raise WorktreeTreeUnavailable("windows_handle_query_failed") from None
    _require_windows_entry_identity(
        entry, final_info, root_volume_serial_number, is_directory=False,
    )
    if _windows_handle_signature(initial_info) != _windows_handle_signature(final_info):
        raise WorktreeTreeUnavailable("windows_file_changed")
    if snapshot_digest is not None and snapshot_output is not None and snapshot_path:
        snapshot_output[snapshot_path] = snapshot_digest.hexdigest()
    return git_digest.digest() if git_digest is not None else None


def _validate_windows_ignored_snapshot_entry(entry: _WindowsDirectoryEntry) -> None:
    if entry.attributes & _WINDOWS_FILE_ATTRIBUTE_DEVICE:
        raise WorktreeTreeUnavailable("unsupported_filesystem_entry")
    if entry.attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY:
        return
    if entry.attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT:
        return
    if entry.attributes:
        return
    raise WorktreeTreeUnavailable("unsupported_filesystem_entry")


def _validate_windows_directory_listing(entries: object) -> None:
    if type(entries) is not tuple:
        raise WorktreeTreeUnavailable("windows_directory_listing_invalid")
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, _WindowsDirectoryEntry):
            raise WorktreeTreeUnavailable("windows_directory_entry_invalid")
        _windows_git_name_bytes(entry.name)
        if entry.name in names:
            raise WorktreeTreeUnavailable("windows_directory_name_duplicate")
        names.add(entry.name)
        if (
            type(entry.attributes) is not int
            or not 0 <= entry.attributes <= 0xFFFFFFFF
            or type(entry.reparse_tag) is not int
            or not 0 <= entry.reparse_tag <= 0xFFFFFFFF
            or type(entry.file_id) is not bytes
            or len(entry.file_id) != 16
            or entry.file_id in (bytes(16), bytes([0xFF]) * 16)
            or type(entry.change_time) is not int
            or entry.change_time < 0
            or type(entry.end_of_file) is not int
            or entry.end_of_file < 0
        ):
            raise WorktreeTreeUnavailable("windows_directory_entry_invalid")


def _windows_git_name_bytes(name: object) -> bytes:
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or any(char in name for char in ("\x00", "/", "\\", ":"))
    ):
        raise WorktreeTreeUnavailable("invalid_git_path")
    try:
        return name.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise WorktreeTreeUnavailable("windows_directory_name_invalid") from None


def _require_windows_directory_handle(
    info: object,
    root_volume_serial_number: int,
) -> None:
    if (
        not isinstance(info, _WindowsHandleInfo)
        or type(root_volume_serial_number) is not int
        or root_volume_serial_number <= 0
        or type(info.volume_serial_number) is not int
        or info.volume_serial_number != root_volume_serial_number
        or type(info.file_id) is not bytes
        or len(info.file_id) != 16
        or info.file_id in (bytes(16), bytes([0xFF]) * 16)
        or type(info.attributes) is not int
        or not 0 <= info.attributes <= 0xFFFFFFFF
        or not info.attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY
        or info.attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        or info.attributes & _WINDOWS_FILE_ATTRIBUTE_DEVICE
        or type(info.is_directory) is not bool
        or info.is_directory is not True
        or type(info.delete_pending) is not bool
        or info.delete_pending is not False
        or type(info.reparse_tag) is not int
        or not 0 <= info.reparse_tag <= 0xFFFFFFFF
        or type(info.change_time) is not int
        or info.change_time < 0
        or type(info.end_of_file) is not int
        or info.end_of_file < 0
    ):
        raise WorktreeTreeUnavailable("windows_directory_identity_invalid")


def _require_windows_entry_identity(
    entry: _WindowsDirectoryEntry,
    info: object,
    root_volume_serial_number: int,
    *,
    is_directory: bool,
) -> None:
    if not isinstance(info, _WindowsHandleInfo):
        raise WorktreeTreeUnavailable("windows_handle_info_invalid")
    _validate_windows_directory_listing((entry,))
    if (
        type(root_volume_serial_number) is not int
        or root_volume_serial_number <= 0
        or type(info.volume_serial_number) is not int
        or info.volume_serial_number <= 0
        or info.volume_serial_number != root_volume_serial_number
        or type(info.file_id) is not bytes
        or info.file_id != entry.file_id
        or type(info.change_time) is not int
        or type(info.end_of_file) is not int
        or info.end_of_file < 0
        # Directory enumeration and an opened directory handle can report
        # different EndOfFile values; directory contents are guarded by the
        # before/after listing signatures and stable handle metadata instead.
        or (not is_directory and info.end_of_file != entry.end_of_file)
        or type(info.is_directory) is not bool
        or info.is_directory is not is_directory
        or type(info.delete_pending) is not bool
        or info.delete_pending is not False
        or type(info.attributes) is not int
        or not 0 <= info.attributes <= 0xFFFFFFFF
        or bool(info.attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY) != is_directory
        or info.attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        or info.attributes & _WINDOWS_FILE_ATTRIBUTE_DEVICE
        or type(info.reparse_tag) is not int
        or info.reparse_tag != entry.reparse_tag
    ):
        raise WorktreeTreeUnavailable("windows_entry_identity_changed")
    if info.change_time != entry.change_time:
        # Keep the strict version check, but distinguish the one directory
        # race for which the outer snapshot may discard all partial output and
        # retry from a newly opened root. File and reparse identity changes
        # remain non-retryable.
        reason = (
            "windows_directory_entry_change_time_changed"
            if is_directory else "windows_entry_identity_changed"
        )
        raise WorktreeTreeUnavailable(reason)


def _require_windows_symlink_identity(
    entry: _WindowsDirectoryEntry,
    info: object,
    root_volume_serial_number: int,
) -> None:
    if not isinstance(info, _WindowsHandleInfo):
        raise WorktreeTreeUnavailable("windows_handle_info_invalid")
    _validate_windows_directory_listing((entry,))
    is_directory = bool(entry.attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY)
    if (
        type(root_volume_serial_number) is not int
        or root_volume_serial_number <= 0
        or type(info.volume_serial_number) is not int
        or info.volume_serial_number != root_volume_serial_number
        or type(info.file_id) is not bytes
        or info.file_id != entry.file_id
        or type(info.change_time) is not int
        or info.change_time != entry.change_time
        or type(info.end_of_file) is not int
        or info.end_of_file != entry.end_of_file
        or type(info.is_directory) is not bool
        or info.is_directory is not is_directory
        or type(info.delete_pending) is not bool
        or info.delete_pending is not False
        or type(info.attributes) is not int
        or not info.attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        or info.attributes & _WINDOWS_FILE_ATTRIBUTE_DEVICE
        or bool(info.attributes & _WINDOWS_FILE_ATTRIBUTE_DIRECTORY) != is_directory
        or type(info.reparse_tag) is not int
        or info.reparse_tag != _WINDOWS_SYMLINK_REPARSE_TAG
        or entry.reparse_tag != _WINDOWS_SYMLINK_REPARSE_TAG
    ):
        raise WorktreeTreeUnavailable("windows_entry_identity_changed")


def _windows_directory_listing_signature(
    entries: tuple[_WindowsDirectoryEntry, ...],
) -> tuple[tuple[str, int, int, bytes, int, int], ...]:
    return tuple(sorted(
        (
            entry.name, entry.attributes,
            entry.reparse_tag
            if entry.attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT else 0,
            entry.file_id, entry.change_time, entry.end_of_file,
        )
        for entry in entries
    ))


def _windows_handle_signature(
    info: _WindowsHandleInfo,
) -> tuple[int, bytes, int, int, int, int, bool, bool]:
    return (
        info.volume_serial_number, info.file_id,
        info.attributes & (
            _WINDOWS_FILE_ATTRIBUTE_DIRECTORY
            | _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
            | _WINDOWS_FILE_ATTRIBUTE_DEVICE
        ),
        info.reparse_tag
        if info.attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT else 0,
        info.change_time, info.end_of_file, info.is_directory, info.delete_pending,
    )


def _close_windows_backend_handle(backend, handle) -> None:
    try:
        backend.close_handle(handle)
    except WorktreeTreeUnavailable:
        raise
    except Exception:
        raise WorktreeTreeUnavailable("windows_handle_close_failed") from None


def snapshot_workspace(root: Path) -> dict[str, str]:
    """散列工作区实体与 Git 相关类型/模式；绝不由宿主跟随读取链接。

    跳过 `.icode_output` 与 `__pycache__`：前者是工单账本，后者是宿主
    Python 编译产物——两者都不是模型改动，不能进入 diff 证据。
    """
    root = Path(root)
    out: dict[str, str] = {}
    if os.name == "posix":
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

        def scan(directory_fd: int, parts: tuple[str, ...]) -> None:
            # 所有子路径相对已经打开的目录 fd，防止检查后把祖先换成链接。
            with os.scandir(directory_fd) as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if entry.name in {".icode_output", "__pycache__"}:
                        if not (
                            stat.S_ISDIR(mode) or stat.S_ISLNK(mode) or stat.S_ISREG(mode)
                        ):
                            raise OSError("snapshot contains unsupported file type")
                        continue
                    child_parts = (*parts, entry.name)
                    if stat.S_ISDIR(mode):
                        child_fd = os.open(entry.name, directory_flags, dir_fd=directory_fd)
                        try:
                            scan(child_fd, child_parts)
                        finally:
                            os.close(child_fd)
                    elif stat.S_ISLNK(mode):
                        target = os.readlink(entry.name, dir_fd=directory_fd)
                        out[Path(*child_parts).as_posix()] = _entry_hash(
                            "symlink", "120000", os.fsencode(target),
                        )
                    elif stat.S_ISREG(mode):
                        file_fd = os.open(
                            entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                            dir_fd=directory_fd,
                        )
                        with os.fdopen(file_fd, "rb") as stream:
                            opened_mode = os.fstat(stream.fileno()).st_mode
                            if not stat.S_ISREG(opened_mode):
                                raise OSError("snapshot file type changed during scan")
                            executable = opened_mode & (
                                stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                            )
                            git_mode = "100755" if executable else "100644"
                            digest = hashlib.sha256(_entry_hash_prefix("file", git_mode))
                            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                                digest.update(chunk)
                            out[Path(*child_parts).as_posix()] = digest.hexdigest()
                    else:
                        raise OSError("snapshot contains unsupported file type")

        root_fd = os.open(root, directory_flags)
        try:
            scan(root_fd, ())
        finally:
            os.close(root_fd)
        return out

    from .windows_worktree import snapshot_windows_workspace_windows

    try:
        return snapshot_windows_workspace_windows(root)
    except WorktreeTreeUnavailable as exc:
        if exc.reason == "windows_reparse_point_unsupported":
            message = "snapshot contains an unsupported reparse point"
        elif exc.reason == "unsupported_filesystem_entry":
            message = "snapshot contains unsupported file type"
        else:
            message = f"snapshot unavailable ({exc.reason})"
        raise OSError(message) from None


def worktree_git_tree_oid(root: Path, *, object_format: str) -> str:
    """只读计算工作树 Git 文件投影的 tree OID，不调用 Git 或写索引/对象库。

    该 OID 表示目录项、文件原始字节、POSIX 可执行位和符号链接目标；
    它不是 clean-filter 转换后的结果，也不包含根 `.git` 元数据。Windows
    Windows 路径使用 parent-relative no-follow handles，仅读取符号链接本身
    的 substitute target text；junction/未知 reparse、特殊文件、不稳定目录
    观察或超限工作区均失败关闭。两平台都不声称点时原子快照。
    """
    if object_format not in ("sha1", "sha256"):
        raise WorktreeTreeUnavailable("unsupported_object_format")
    if os.name == "nt":
        from .windows_worktree import worktree_git_tree_oid_windows

        return worktree_git_tree_oid_windows(root, object_format=object_format)
    if os.name != "posix":
        raise WorktreeTreeUnavailable("unsupported_platform")

    root = Path(root)
    try:
        if root.is_symlink():
            raise WorktreeTreeUnavailable("workspace_root_is_link")
        root = Path(os.path.abspath(root))
        root_status = os.stat(root, follow_symlinks=False)
        if not stat.S_ISDIR(root_status.st_mode):
            raise WorktreeTreeUnavailable("workspace_root_not_directory")
        root_fd = os.open(
            root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
    except WorktreeTreeUnavailable:
        raise
    except OSError:
        raise WorktreeTreeUnavailable("workspace_unavailable") from None

    entry_counter = [0]
    byte_counter = [0]
    try:
        root_fd_status = os.fstat(root_fd)
        if not _same_filesystem_entry(root_status, root_fd_status):
            raise WorktreeTreeUnavailable("filesystem_changed")
        tree_digest = _hash_worktree_tree(
            root_fd, is_root=True, depth=0, algorithm=object_format,
            entry_counter=entry_counter, byte_counter=byte_counter,
        )
        if tree_digest is None:
            raise WorktreeTreeUnavailable("root_tree_unavailable")
        return tree_digest.hex()
    except WorktreeTreeUnavailable:
        raise
    except OSError:
        raise WorktreeTreeUnavailable("filesystem_unavailable") from None
    finally:
        os.close(root_fd)


def _increment_tree_entry_count(counter: list[int]) -> None:
    counter[0] += 1
    if counter[0] > _MAX_GIT_TREE_ENTRIES:
        raise WorktreeTreeUnavailable("worktree_too_large")


def _same_filesystem_entry(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_mode == after.st_mode
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
        and before.st_ctime_ns == after.st_ctime_ns
    )


def _git_object_digest(algorithm: str, kind: bytes, size: int):
    digest = hashlib.new(algorithm)
    digest.update(kind + b" " + str(size).encode("ascii") + b"\0")
    return digest


def _hash_worktree_blob_fd(
    descriptor: int,
    status: os.stat_result,
    algorithm: str,
    byte_counter: list[int],
) -> bytes:
    byte_counter[0] += status.st_size
    if status.st_size < 0 or byte_counter[0] > _MAX_GIT_TREE_BYTES:
        raise WorktreeTreeUnavailable("worktree_too_large")
    digest = _git_object_digest(algorithm, b"blob", status.st_size)
    bytes_read = 0
    with os.fdopen(os.dup(descriptor), "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            bytes_read += len(chunk)
            digest.update(chunk)
    after = os.fstat(descriptor)
    if bytes_read != status.st_size or not _same_filesystem_entry(status, after):
        raise WorktreeTreeUnavailable("filesystem_changed")
    return digest.digest()


def _hash_worktree_tree(
    directory_fd: int,
    *,
    is_root: bool,
    depth: int,
    algorithm: str,
    entry_counter: list[int],
    byte_counter: list[int],
) -> bytes | None:
    if depth > _MAX_GIT_TREE_DEPTH:
        raise WorktreeTreeUnavailable("worktree_too_deep")
    initial_status = os.fstat(directory_fd)
    entries: list[tuple[bytes, bool, bytes, bytes]] = []

    with os.scandir(directory_fd) as iterator:
        children = sorted(iterator, key=lambda child: os.fsencode(child.name))

    for child in children:
        name = os.fsencode(child.name)
        if is_root and name == b".git":
            # Repository metadata is not part of a Git tree. Never descend into it.
            continue
        if name == b".git":
            raise WorktreeTreeUnavailable("nested_git_metadata")
        if not name or b"/" in name or b"\0" in name:
            raise WorktreeTreeUnavailable("invalid_git_path")

        _increment_tree_entry_count(entry_counter)
        try:
            before = child.stat(follow_symlinks=False)
        except OSError:
            raise WorktreeTreeUnavailable("filesystem_changed") from None
        mode = before.st_mode

        if stat.S_ISDIR(mode):
            child_fd = os.open(
                child.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
            try:
                opened = os.fstat(child_fd)
                if not _same_filesystem_entry(before, opened):
                    raise WorktreeTreeUnavailable("filesystem_changed")
                oid = _hash_worktree_tree(
                    child_fd, is_root=False, depth=depth + 1,
                    algorithm=algorithm, entry_counter=entry_counter,
                    byte_counter=byte_counter,
                )
                if not _same_filesystem_entry(opened, os.fstat(child_fd)):
                    raise WorktreeTreeUnavailable("filesystem_changed")
            finally:
                os.close(child_fd)
            if oid is not None:
                entries.append((name, True, b"40000", oid))
        elif stat.S_ISREG(mode):
            descriptor = os.open(
                child.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or not _same_filesystem_entry(before, opened)
                ):
                    raise WorktreeTreeUnavailable("filesystem_changed")
                executable = opened.st_mode & (
                    stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )
                git_mode = b"100755" if executable else b"100644"
                oid = _hash_worktree_blob_fd(
                    descriptor, opened, algorithm, byte_counter,
                )
            finally:
                os.close(descriptor)
            entries.append((name, False, git_mode, oid))
        elif stat.S_ISLNK(mode):
            target = os.readlink(child.name, dir_fd=directory_fd)
            try:
                after = os.stat(child.name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                raise WorktreeTreeUnavailable("filesystem_changed") from None
            if not _same_filesystem_entry(before, after):
                raise WorktreeTreeUnavailable("filesystem_changed")
            target_bytes = os.fsencode(target)
            oid = _git_object_digest(algorithm, b"blob", len(target_bytes))
            oid.update(target_bytes)
            entries.append((name, False, b"120000", oid.digest()))
        else:
            raise WorktreeTreeUnavailable("unsupported_filesystem_entry")

    if not _same_filesystem_entry(initial_status, os.fstat(directory_fd)):
        raise WorktreeTreeUnavailable("filesystem_changed")

    # Git compares a directory as if its name ended in '/', not as a NUL-terminated
    # non-directory entry. This matters for siblings such as `foo` and `foo.bar`.
    entries.sort(key=lambda entry: entry[0] + (b"/" if entry[1] else b""))
    if not entries and not is_root:
        # Git trees cannot preserve empty directories.
        return None
    tree_body = b"".join(
        mode + b" " + name + b"\0" + oid
        for name, _is_directory, mode, oid in entries
    )
    return _hash_git_tree_body(algorithm, tree_body)


def _hash_git_tree_body(algorithm: str, tree_body: bytes) -> bytes:
    digest = _git_object_digest(algorithm, b"tree", len(tree_body))
    digest.update(tree_body)
    return digest.digest()


def _entry_hash_prefix(entry_type: str, git_mode: str) -> bytes:
    """版本化地分隔文件类型/模式，避免相同字节产生不同 Git 项的碰撞。"""
    return f"icode-workspace-entry-v2\0{entry_type}\0{git_mode}\0".encode("ascii")


def _entry_hash(entry_type: str, git_mode: str, content: bytes) -> str:
    digest = hashlib.sha256(_entry_hash_prefix(entry_type, git_mode))
    digest.update(content)
    return digest.hexdigest()


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    names = set(before) | set(after)
    return sorted(name for name in names if before.get(name) != after.get(name))


def diff_fingerprint(before: dict[str, str], after: dict[str, str]) -> str:
    """把一次改动（相对基线）绑定成确定性指纹。

    只依赖改动前后每条路径的 sha256（不含正文），用于把验证证据
    绑定到「具体某次 diff」：同一结果文件在不同基线下的改动会得到
    不同指纹；新增/删除/修改三种状态由前后哈希的缺失/变化区分。
    未变化的路径不进入指纹（与 `changed_files` 的集合一致）。
    """
    entries: list[dict[str, str]] = []
    for name in sorted(set(before) | set(after)):
        old = before.get(name)
        new = after.get(name)
        if old == new:
            continue
        entries.append({
            "path": name,
            "status": "A" if old is None else "D" if new is None else "M",
            "before": old or "",
            "after": new or "",
        })
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_fingerprint(snapshot: dict[str, str]) -> str:
    """为完整工作区内容快照生成稳定指纹，不只覆盖相对基线的改动项。"""
    entries = [
        {"path": path, "sha256": digest}
        for path, digest in sorted(snapshot.items())
    ]
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
