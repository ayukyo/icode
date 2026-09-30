"""Production Windows Git-tree parser contracts, portable unit coverage."""

from __future__ import annotations

import struct
import unittest
import hashlib
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from icode import windows_worktree, workspace_snapshot
from icode.workspace_snapshot import WorktreeTreeUnavailable


_SAFE_WINDOWS_SNAPSHOT_LOCATIONS = frozenset({
    "repo_root_git_child",
    "repo_root_target_dir_child",
    "git_metadata_descendant",
    "target_dir_descendant",
    "other_descendant",
    "unavailable",
})


def _safe_windows_snapshot_change_location(
    snapshot_parts: object,
    entry_name: object,
) -> str:
    """Collapse a native mismatch location to a fixed, non-path label."""
    if (
        type(snapshot_parts) is not tuple
        or any(type(part) is not str for part in snapshot_parts)
        or type(entry_name) is not str
    ):
        return "unavailable"
    if not snapshot_parts:
        if entry_name == ".git":
            return "repo_root_git_child"
        if entry_name == "target-dir":
            return "repo_root_target_dir_child"
        return "other_descendant"
    if snapshot_parts[0] == ".git":
        return "git_metadata_descendant"
    if snapshot_parts[0] == "target-dir":
        return "target_dir_descendant"
    return "other_descendant"


def _safe_windows_snapshot_change_receipt(observations: object) -> str:
    """Serialize only the two bounded retry labels, never path components."""
    if type(observations) is not dict:
        return "unavailable"
    if any(type(attempt) is not int or attempt not in (1, 2) for attempt in observations):
        return "unavailable"
    labels = {1: "unobserved", 2: "unobserved"}
    for attempt, location in observations.items():
        if type(location) is not str or location not in _SAFE_WINDOWS_SNAPSHOT_LOCATIONS:
            return "unavailable"
        labels[attempt] = location
    return f"try1_{labels[1]}+try2_{labels[2]}"


def _parse(buffer: bytes):
    parser = getattr(workspace_snapshot, "_parse_windows_directory_entries", None)
    if not callable(parser):
        raise AssertionError("production Windows directory parser is missing")
    return parser(buffer)


def _collect(read_page, *, buffer_bytes: int = 4096):
    collector = getattr(
        workspace_snapshot, "_collect_windows_directory_entries", None,
    )
    if not callable(collector):
        raise AssertionError("production Windows directory page collector is missing")
    return collector(read_page, buffer_bytes=buffer_bytes)


def _directory_record(
    name: str,
    *,
    file_id: bytes = bytes.fromhex("00112233445566778899aabbccddeeff"),
    attributes: int = 0x80,
    change_time: int = 0,
    end_of_file: int = 0,
    reparse_tag: int = 0,
    next_entry_offset: int = 0,
) -> bytes:
    encoded_name = name.encode("utf-16-le")
    if len(file_id) != 16:
        raise ValueError("file_id must contain exactly 16 bytes")
    record_size = 88 + len(encoded_name)
    record = bytearray(max(record_size, next_entry_offset))
    struct.pack_into("<I", record, 0, next_entry_offset)
    struct.pack_into("<Q", record, 32, change_time)
    struct.pack_into("<Q", record, 40, end_of_file)
    struct.pack_into("<I", record, 56, attributes)
    struct.pack_into("<I", record, 60, len(encoded_name))
    struct.pack_into("<I", record, 68, reparse_tag)
    record[72:88] = file_id
    record[88:record_size] = encoded_name
    return bytes(record)


def _symlink_reparse_buffer(target: str, *, flags: int = 1) -> bytes:
    encoded_target = target.encode("utf-16-le")
    path_buffer = encoded_target
    reparse_data_length = 12 + len(path_buffer)
    record = bytearray(8 + reparse_data_length)
    struct.pack_into("<IHH", record, 0, 0xA000000C, reparse_data_length, 0)
    struct.pack_into("<HHHHI", record, 8, 0, len(encoded_target), 0, 0, flags)
    record[20:] = path_buffer
    return bytes(record)


class TestWindowsSnapshotChangeDiagnostic(unittest.TestCase):
    def test_location_collapses_paths_to_fixed_categories(self) -> None:
        locate = globals().get("_safe_windows_snapshot_change_location")
        self.assertTrue(callable(locate), "safe_snapshot_location_helper_missing")

        self.assertEqual(locate((), ".git"), "repo_root_git_child")
        self.assertEqual(
            locate((), "target-dir"), "repo_root_target_dir_child",
        )
        self.assertEqual(
            locate((".git",), "objects"), "git_metadata_descendant",
        )
        self.assertEqual(
            locate(("target-dir",), "inside.txt"),
            "target_dir_descendant",
        )
        self.assertEqual(locate(("private",), "secret.txt"), "other_descendant")
        self.assertEqual(locate((object(),), "secret.txt"), "unavailable")

    def test_change_receipt_is_bounded_to_two_attempts_and_fixed_labels(self) -> None:
        format_receipt = globals().get("_safe_windows_snapshot_change_receipt")
        self.assertTrue(
            callable(format_receipt), "safe_snapshot_receipt_helper_missing",
        )

        self.assertEqual(
            format_receipt({1: "repo_root_git_child", 2: "other_descendant"}),
            "try1_repo_root_git_child+try2_other_descendant",
        )
        self.assertEqual(
            format_receipt({1: "repo_root_git_child"}),
            "try1_repo_root_git_child+try2_unobserved",
        )
        self.assertEqual(
            format_receipt({1: "private.txt", 2: "other_descendant"}),
            "unavailable",
        )
        self.assertEqual(
            format_receipt({
                1: "other_descendant",
                2: "other_descendant",
                3: "other_descendant",
            }),
            "unavailable",
        )


class TestProductionWindowsDirectoryEntryParser(unittest.TestCase):
    def test_parser_preserves_identity_type_size_and_change_metadata(self) -> None:
        expected_id = bytes.fromhex("00112233445566778899aabbccddeeff")
        entries = _parse(
            _directory_record(
                "café.bin",
                file_id=expected_id,
                attributes=0x80,
                change_time=123456,
                end_of_file=17,
            ),
        )

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.name, "café.bin")
        self.assertEqual(entry.file_id, expected_id)
        self.assertEqual(entry.attributes, 0x80)
        self.assertEqual(entry.change_time, 123456)
        self.assertEqual(entry.end_of_file, 17)

    def test_parser_ignores_undefined_reparse_tag_for_regular_entry(self) -> None:
        entry = _parse(
            _directory_record(
                "regular.bin",
                attributes=0x80,
                reparse_tag=0xA000000C,
            ),
        )[0]

        self.assertEqual(entry.reparse_tag, 0)

    def test_parser_bounds_aligned_pages_and_filters_dot_records(self) -> None:
        first_name = ".".encode("utf-16-le")
        first_offset = (88 + len(first_name) + 7) & ~7
        buffer = (
            _directory_record(
                ".", file_id=bytes.fromhex("11" * 16),
                next_entry_offset=first_offset,
            )
            + _directory_record(
                "child.txt", file_id=bytes.fromhex("22" * 16),
            )
        )

        entries = _parse(buffer)

        self.assertEqual([entry.name for entry in entries], ["child.txt"])

    def test_parser_rejects_invalid_identity_and_non_component_names(self) -> None:
        malformed = (
            _directory_record("file.bin", file_id=bytes(16)),
            _directory_record("../outside.txt", file_id=bytes.fromhex("33" * 16)),
            _directory_record("stream:name", file_id=bytes.fromhex("44" * 16)),
        )

        for buffer in malformed:
            with self.subTest(buffer=buffer[:16]):
                with self.assertRaises(WorktreeTreeUnavailable):
                    _parse(buffer)

    def test_parser_rejects_non_contiguous_memoryview(self) -> None:
        record = _directory_record("file.bin")
        interleaved = bytearray(len(record) * 2)
        interleaved[::2] = record
        non_contiguous = memoryview(interleaved)[::2]

        with self.assertRaises(WorktreeTreeUnavailable) as raised:
            _parse(non_contiguous)
        self.assertEqual(raised.exception.reason, "windows_directory_buffer_invalid")


class TestProductionWindowsSymlinkReparseParser(unittest.TestCase):
    def test_parser_uses_symlink_substitute_name_not_untrusted_print_name(self) -> None:
        parser = getattr(
            workspace_snapshot, "_parse_windows_symlink_reparse_buffer", None,
        )
        self.assertTrue(callable(parser), "production symlink reparse parser is missing")

        target = parser(_symlink_reparse_buffer("../real-target", flags=1))

        self.assertEqual(target, "../real-target")

    def test_parser_rejects_unknown_tags_offsets_and_flags(self) -> None:
        parser = getattr(
            workspace_snapshot, "_parse_windows_symlink_reparse_buffer", None,
        )
        self.assertTrue(callable(parser), "production symlink reparse parser is missing")
        valid = _symlink_reparse_buffer("\\??\\C:\\target", flags=0)
        unknown_tag = bytearray(valid)
        struct.pack_into("<I", unknown_tag, 0, 0xA0000003)
        invalid_offset = bytearray(valid)
        struct.pack_into("<H", invalid_offset, 8, 2)
        invalid_flags = _symlink_reparse_buffer("target", flags=2)

        for malformed in (bytes(unknown_tag), bytes(invalid_offset), invalid_flags):
            with self.subTest(malformed=malformed[:12]):
                with self.assertRaises(WorktreeTreeUnavailable):
                    parser(malformed)


class TestWindowsNativeStructureABI(unittest.TestCase):
    def test_fixed_width_windows_record_structures_match_native_layout(self) -> None:
        pointer_bytes = windows_worktree.ctypes.sizeof(windows_worktree.ctypes.c_void_p)

        self.assertEqual(windows_worktree.ctypes.sizeof(windows_worktree._FILE_BASIC_INFO), 40)
        self.assertEqual(windows_worktree.ctypes.sizeof(windows_worktree._FILE_STANDARD_INFO), 24)
        self.assertEqual(
            windows_worktree.ctypes.sizeof(windows_worktree._FILE_ATTRIBUTE_TAG_INFO), 8,
        )
        self.assertEqual(windows_worktree.ctypes.sizeof(windows_worktree._FILE_ID_INFO), 24)
        self.assertEqual(
            windows_worktree.ctypes.sizeof(windows_worktree._UNICODE_STRING),
            8 if pointer_bytes == 4 else 16,
        )
        self.assertEqual(
            windows_worktree.ctypes.sizeof(windows_worktree._OBJECT_ATTRIBUTES),
            24 if pointer_bytes == 4 else 48,
        )


class TestWindowsNativeOpenShareFlags(unittest.TestCase):
    def test_relative_file_directory_and_symlink_handles_allow_all_sharing(self) -> None:
        class FakeNtDll:
            def __init__(self):
                self.share_accesses = []

            def NtCreateFile(
                self, output_handle, _desired_access, _attributes, _io_status,
                _allocation_size, _file_attributes, share_access, *_remaining,
            ):
                self.share_accesses.append(int(share_access))
                handle_pointer = windows_worktree.ctypes.cast(
                    output_handle,
                    windows_worktree.ctypes.POINTER(windows_worktree.wintypes.HANDLE),
                )
                handle_pointer.contents.value = 0x1234 + len(self.share_accesses)
                return 0

        backend = object.__new__(windows_worktree._WindowsNativeWorktreeBackend)
        backend._ntdll = FakeNtDll()
        backend._kernel32 = SimpleNamespace()
        handles = (
            backend._open_relative(1, "file", directory=False),
            backend._open_relative(1, "directory", directory=True),
            backend._open_relative(1, "symlink", directory=False, reparse=True),
        )

        expected = (
            windows_worktree._FILE_SHARE_READ
            | windows_worktree._FILE_SHARE_WRITE
            | windows_worktree._FILE_SHARE_DELETE
        )
        self.assertEqual(backend._ntdll.share_accesses, [expected] * 3)
        self.assertEqual(len(handles), 3)


class TestWindowsPathNormalization(unittest.TestCase):
    def test_extended_unc_prefix_is_normalized_case_insensitively(self) -> None:
        from pathlib import PureWindowsPath

        path = windows_worktree._normalize_extended_unc_prefix(
            "\\\\?\\unc\\server\\share\\repo",
        )

        self.assertEqual(
            windows_worktree._WindowsNativeWorktreeBackend._volume_anchor_and_parts(
                PureWindowsPath(path),
            ),
            ("\\\\?\\UNC\\server\\share\\", ("repo",)),
        )


class TestWindowsWorkspaceSnapshotDispatch(unittest.TestCase):
    def test_workspace_snapshot_routes_windows_to_handle_relative_walker(self) -> None:
        workspace = Path("C:/source")
        fake_os = type(
            "FakeOS", (), {"name": "nt", "fsencode": staticmethod(os.fsencode)},
        )()

        with patch.object(workspace_snapshot, "os", fake_os), patch(
            "icode.windows_worktree.snapshot_windows_workspace_windows",
            return_value={"safe.py": "digest"},
            create=True,
        ) as native_snapshot, patch.object(
            workspace_snapshot,
            "_snapshot_windows_workspace",
            side_effect=AssertionError("path-based Windows snapshot was used"),
            create=True,
        ):
            actual = workspace_snapshot.snapshot_workspace(workspace)

        self.assertEqual(actual, {"safe.py": "digest"})
        native_snapshot.assert_called_once_with(workspace)

    def test_shared_snapshot_walker_keeps_workspace_hash_contract_and_ignores_outputs(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("71" * 16))
        root.children["safe.py"] = _FakeWindowsNode(
            "safe.py", bytes.fromhex("72" * 16), content=b"code",
        )
        root.children[".git"] = _FakeWindowsNode(
            ".git", bytes.fromhex("73" * 16), content=b"git metadata",
        )
        output = _FakeWindowsNode(".icode_output", bytes.fromhex("74" * 16))
        output.children["report.md"] = _FakeWindowsNode(
            "report.md", bytes.fromhex("75" * 16), content=b"ignored output",
        )
        root.children[".icode_output"] = output
        pycache = _FakeWindowsNode("__pycache__", bytes.fromhex("76" * 16))
        pycache.children["module.pyc"] = _FakeWindowsNode(
            "module.pyc", bytes.fromhex("77" * 16), content=b"ignored bytecode",
        )
        root.children["__pycache__"] = pycache
        backend = _FakeWindowsTreeBackend(root)
        fake_os = type(
            "FakeOS", (), {"name": "nt", "fsencode": staticmethod(os.fsencode)},
        )()

        with patch.object(workspace_snapshot, "os", fake_os), patch.object(
            windows_worktree, "_WindowsNativeWorktreeBackend", return_value=backend,
        ):
            actual = workspace_snapshot.snapshot_workspace(Path("C:/source"))

        self.assertEqual(actual, {
            "safe.py": workspace_snapshot._entry_hash("file", "100644", b"code"),
            ".git": workspace_snapshot._entry_hash(
                "file", "100644", b"git metadata",
            ),
        })
        self.assertEqual(backend.read_calls, 2)
        self.assertTrue(all(handle.closed for handle in backend.opened))

    def test_directory_entry_and_handle_eof_may_differ(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("6a" * 16))
        source_directory = _FakeWindowsNode("src", bytes.fromhex("6b" * 16))
        source_directory.handle_end_of_file = 4096
        source_directory.children["main.py"] = _FakeWindowsNode(
            "main.py", bytes.fromhex("6c" * 16), content=b"print('ok')\n",
        )
        root.children["src"] = source_directory
        backend = _FakeWindowsTreeBackend(root)
        fake_os = type(
            "FakeOS", (), {"name": "nt", "fsencode": staticmethod(os.fsencode)},
        )()

        with patch.object(workspace_snapshot, "os", fake_os), patch.object(
            windows_worktree, "_WindowsNativeWorktreeBackend", return_value=backend,
        ):
            actual = workspace_snapshot.snapshot_workspace(Path("C:/source"))

        self.assertEqual(actual, {
            "src/main.py": workspace_snapshot._entry_hash(
                "file", "100644", b"print('ok')\n",
            ),
        })
        self.assertEqual(backend.read_calls, 1)
        self.assertTrue(all(handle.closed for handle in backend.opened))

    def test_snapshot_retries_once_after_directory_change_time_race(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("7a" * 16))
        directory = _FakeWindowsNode("changing", bytes.fromhex("7b" * 16))
        directory.children["safe.py"] = _FakeWindowsNode(
            "safe.py", bytes.fromhex("7c" * 16), content=b"stable\n",
        )
        root.children["changing"] = directory
        backends: list[_FakeWindowsTreeBackend] = []

        class ChangeOnceBackend(_FakeWindowsTreeBackend):
            def open_child(self, parent, entry, *, directory, reparse=False):
                handle = super().open_child(
                    parent, entry, directory=directory, reparse=reparse,
                )
                if not backends[:-1]:
                    handle.node.change_time += 1
                return handle

        def create_backend():
            backend = ChangeOnceBackend(root)
            backends.append(backend)
            return backend

        with patch.object(
            windows_worktree, "_WindowsNativeWorktreeBackend",
            side_effect=create_backend,
        ):
            actual = windows_worktree.snapshot_windows_workspace_windows(
                Path("C:/source"),
            )

        self.assertEqual(actual, {
            "changing/safe.py": workspace_snapshot._entry_hash(
                "file", "100644", b"stable\n",
            ),
        })
        self.assertEqual(len(backends), 2)
        self.assertTrue(all(
            handle.closed
            for backend in backends
            for handle in (*backend.opened, *backend.root_handles)
        ))

    def test_snapshot_still_fails_closed_after_second_directory_change_time_race(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("7d" * 16))
        directory = _FakeWindowsNode("changing", bytes.fromhex("7e" * 16))
        directory.children["safe.py"] = _FakeWindowsNode(
            "safe.py", bytes.fromhex("7f" * 16), content=b"stable\n",
        )
        root.children["changing"] = directory
        backends: list[_FakeWindowsTreeBackend] = []

        class AlwaysChangingBackend(_FakeWindowsTreeBackend):
            def open_child(self, parent, entry, *, directory, reparse=False):
                handle = super().open_child(
                    parent, entry, directory=directory, reparse=reparse,
                )
                handle.node.change_time += 1
                return handle

        def create_backend():
            backend = AlwaysChangingBackend(root)
            backends.append(backend)
            return backend

        with patch.object(
            windows_worktree, "_WindowsNativeWorktreeBackend",
            side_effect=create_backend,
        ), self.assertRaises(WorktreeTreeUnavailable) as raised:
            windows_worktree.snapshot_windows_workspace_windows(
                Path("C:/source"),
            )

        self.assertEqual(
            raised.exception.reason,
            "windows_directory_entry_change_time_changed",
        )
        self.assertEqual(len(backends), 2)
        self.assertTrue(all(
            handle.closed
            for backend in backends
            for handle in (*backend.opened, *backend.root_handles)
        ))

    def test_snapshot_does_not_retry_file_identity_change(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("80" * 16))
        root.children["unsafe.py"] = _FakeWindowsNode(
            "unsafe.py", bytes.fromhex("81" * 16), content=b"unstable\n",
        )
        backends: list[_FakeWindowsTreeBackend] = []

        class FileIdentityChangeBackend(_FakeWindowsTreeBackend):
            def open_child(self, parent, entry, *, directory, reparse=False):
                handle = super().open_child(
                    parent, entry, directory=directory, reparse=reparse,
                )
                handle.node.file_id = bytes.fromhex("82" * 16)
                return handle

        def create_backend():
            backend = FileIdentityChangeBackend(root)
            backends.append(backend)
            return backend

        with patch.object(
            windows_worktree, "_WindowsNativeWorktreeBackend",
            side_effect=create_backend,
        ), self.assertRaises(WorktreeTreeUnavailable) as raised:
            windows_worktree.snapshot_windows_workspace_windows(
                Path("C:/source"),
            )

        self.assertEqual(raised.exception.reason, "windows_entry_identity_changed")
        self.assertEqual(len(backends), 1)
        self.assertTrue(all(
            handle.closed
            for backend in backends
            for handle in (*backend.opened, *backend.root_handles)
        ))

    def test_workspace_snapshot_is_not_limited_by_git_tree_oid_byte_budget(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("78" * 16))
        root.children[".git"] = _FakeWindowsNode(
            ".git", bytes.fromhex("79" * 16), content=b"large packed objects",
        )
        backend = _FakeWindowsTreeBackend(root)
        fake_os = type(
            "FakeOS", (), {"name": "nt", "fsencode": staticmethod(os.fsencode)},
        )()

        with patch.object(workspace_snapshot, "os", fake_os), patch.object(
            workspace_snapshot, "_MAX_GIT_TREE_BYTES", 1,
        ), patch.object(
            windows_worktree, "_WindowsNativeWorktreeBackend", return_value=backend,
        ):
            actual = workspace_snapshot.snapshot_workspace(Path("C:/source"))

        self.assertEqual(actual, {
            ".git": workspace_snapshot._entry_hash(
                "file", "100644", b"large packed objects",
            ),
        })

    def test_shared_snapshot_walker_hashes_symlink_text_without_reading_target(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("81" * 16))
        link = _FakeWindowsNode(
            "alias", bytes.fromhex("82" * 16), content=b"must not be read",
        )
        link.reparse_target = "../outside.txt"
        root.children["alias"] = link
        backend = _FakeWindowsTreeBackend(root)
        fake_os = type(
            "FakeOS", (), {"name": "nt", "fsencode": staticmethod(os.fsencode)},
        )()

        with patch.object(workspace_snapshot, "os", fake_os), patch.object(
            windows_worktree, "_WindowsNativeWorktreeBackend", return_value=backend,
        ):
            actual = workspace_snapshot.snapshot_workspace(Path("C:/source"))

        self.assertEqual(actual, {
            "alias": workspace_snapshot._entry_hash(
                "symlink", "120000", b"../outside.txt",
            ),
        })
        self.assertEqual(backend.read_calls, 0)


class TestProductionWindowsDirectoryPageCollector(unittest.TestCase):
    def test_collector_restarts_once_after_dot_only_page_then_continues(self) -> None:
        dot_page = _directory_record(
            ".", file_id=bytes.fromhex("11" * 16),
        )
        child_page = _directory_record(
            "child.txt", file_id=bytes.fromhex("22" * 16),
        )
        responses = iter([
            (True, 0, dot_page),
            (True, 0, child_page),
            (False, 18, b""),
        ])
        information_classes = []

        def read_page(information_class: int, _size: int):
            information_classes.append(information_class)
            return next(responses)

        entries = _collect(read_page)

        self.assertEqual([entry.name for entry in entries], ["child.txt"])
        self.assertEqual(
            information_classes,
            [
                workspace_snapshot._WINDOWS_FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
                workspace_snapshot._WINDOWS_FILE_ID_EXTD_DIRECTORY_INFO_CLASS,
                workspace_snapshot._WINDOWS_FILE_ID_EXTD_DIRECTORY_INFO_CLASS,
            ],
        )

    def test_collector_preserves_specific_malformed_page_error(self) -> None:
        malformed = bytearray(_directory_record("bad.txt"))
        struct.pack_into("<I", malformed, 60, 3)

        with self.assertRaises(WorktreeTreeUnavailable) as raised:
            _collect(lambda _info_class, _size: (True, 0, bytes(malformed)))

        self.assertEqual(raised.exception.reason, "windows_directory_record_invalid")

    def test_collector_rejects_zero_success_page_as_ambiguous_no_progress(self) -> None:
        with self.assertRaises(WorktreeTreeUnavailable) as raised:
            _collect(lambda _info_class, size: (True, 0, bytes(size)))

        self.assertEqual(
            raised.exception.reason, "windows_directory_enumeration_no_progress",
        )

    def test_collector_rejects_duplicate_names_across_pages(self) -> None:
        responses = iter([
            (True, 0, _directory_record("same.txt", file_id=bytes.fromhex("33" * 16))),
            (True, 0, _directory_record("same.txt", file_id=bytes.fromhex("44" * 16))),
        ])

        with self.assertRaises(WorktreeTreeUnavailable) as raised:
            _collect(lambda _info_class, _size: next(responses))

        self.assertEqual(
            raised.exception.reason, "windows_directory_name_duplicate",
        )

    def test_collector_maps_unknown_native_error_to_fixed_reason(self) -> None:
        with self.assertRaises(WorktreeTreeUnavailable) as raised:
            _collect(lambda _info_class, _size: (False, 5, b""))

        self.assertEqual(
            raised.exception.reason, "windows_directory_enumeration_failed",
        )


class _FakeWindowsNode:
    def __init__(self, name: str, file_id: bytes, *, content: bytes | None = None):
        self.name = name
        self.file_id = file_id
        self.content = content
        self.handle_end_of_file: int | None = None
        self.children: dict[str, _FakeWindowsNode] = {}
        self.change_time = 1
        self.reparse = False
        self.reparse_tag = 0xA000000C
        self.reparse_target: str | None = None

    @property
    def is_directory(self) -> bool:
        return self.content is None

    @property
    def is_reparse_point(self) -> bool:
        return self.reparse or self.reparse_target is not None


class _FakeWindowsHandle:
    def __init__(self, node: _FakeWindowsNode):
        self.node = node
        self.position = 0
        self.closed = False


class _FakeWindowsTreeBackend:
    def __init__(self, root: _FakeWindowsNode):
        self.root = root
        self.opened: list[_FakeWindowsHandle] = []
        self.root_handles: list[_FakeWindowsHandle] = []
        self.read_calls = 0

    def open_root(self, _root: Path):
        handle = _FakeWindowsHandle(self.root)
        self.root_handles.append(handle)
        return handle

    def close_root(self, _root_handle) -> None:
        for handle in self.root_handles:
            self.close_handle(handle)

    def enumerate_directory(self, handle: _FakeWindowsHandle):
        result = []
        for node in handle.node.children.values():
            is_directory = node.is_directory
            attributes = (
                (0x10 if is_directory else 0x80)
                | (0x400 if node.is_reparse_point else 0)
            )
            result.append(workspace_snapshot._WindowsDirectoryEntry(
                name=node.name,
                attributes=attributes,
                reparse_tag=node.reparse_tag if node.is_reparse_point else 0,
                file_id=node.file_id,
                change_time=node.change_time,
                end_of_file=0 if is_directory else len(node.content or b""),
            ))
        return tuple(result)

    def open_child(
        self,
        parent: _FakeWindowsHandle,
        entry,
        *,
        directory: bool,
        reparse: bool = False,
    ):
        node = parent.node.children[entry.name]
        if node.is_directory != directory:
            raise WorktreeTreeUnavailable("windows_entry_type_changed")
        if reparse != node.is_reparse_point:
            raise WorktreeTreeUnavailable("windows_entry_type_changed")
        handle = _FakeWindowsHandle(node)
        self.opened.append(handle)
        return handle

    def query_info(self, handle: _FakeWindowsHandle):
        node = handle.node
        is_directory = node.is_directory
        attributes = (
            (0x10 if is_directory else 0x80)
            | (0x400 if node.is_reparse_point else 0)
        )
        return workspace_snapshot._WindowsHandleInfo(
            volume_serial_number=7,
            file_id=node.file_id,
            attributes=attributes,
            reparse_tag=node.reparse_tag if node.is_reparse_point else 0,
            change_time=node.change_time,
            end_of_file=(
                node.handle_end_of_file
                if node.handle_end_of_file is not None
                else 0 if is_directory else len(node.content or b"")
            ),
            is_directory=is_directory,
            delete_pending=False,
        )

    def read_file(self, handle: _FakeWindowsHandle, size: int) -> bytes:
        self.read_calls += 1
        content = handle.node.content or b""
        chunk = content[handle.position:handle.position + size]
        handle.position += len(chunk)
        return chunk

    def close_handle(self, handle: _FakeWindowsHandle) -> None:
        handle.closed = True

    def read_symlink_target(self, handle: _FakeWindowsHandle) -> str:
        if not handle.node.is_reparse_point or handle.node.reparse_target is None:
            raise WorktreeTreeUnavailable("windows_symlink_read_failed")
        return handle.node.reparse_target


def _expected_git_blob(algorithm: str, content: bytes) -> bytes:
    digest = hashlib.new(algorithm)
    digest.update(b"blob " + str(len(content)).encode("ascii") + b"\0")
    digest.update(content)
    return digest.digest()


def _expected_git_tree(algorithm: str, entries) -> bytes:
    ordered = sorted(entries, key=lambda item: item[0] + (b"/" if item[1] else b""))
    body = b"".join(
        mode + b" " + name + b"\0" + oid
        for name, is_directory, mode, oid in ordered
    )
    digest = hashlib.new(algorithm)
    digest.update(b"tree " + str(len(body)).encode("ascii") + b"\0")
    digest.update(body)
    return digest.digest()


class TestProductionWindowsWorktreeTreeBuilder(unittest.TestCase):
    def _builder(self):
        builder = getattr(workspace_snapshot, "_build_windows_worktree_tree", None)
        if not callable(builder):
            raise AssertionError("production Windows recursive Git-tree builder is missing")
        return builder

    def test_builder_matches_git_object_serialization_for_sha1_and_sha256(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("01" * 16))
        root.children["a.txt"] = _FakeWindowsNode(
            "a.txt", bytes.fromhex("02" * 16), content=b"abc",
        )
        child_directory = _FakeWindowsNode("dir", bytes.fromhex("03" * 16))
        child_directory.children["nested.bin"] = _FakeWindowsNode(
            "nested.bin", bytes.fromhex("04" * 16), content=b"xy",
        )
        child_directory.children["empty"] = _FakeWindowsNode(
            "empty", bytes.fromhex("05" * 16),
        )
        root.children["dir"] = child_directory
        root.children["empty-root"] = _FakeWindowsNode(
            "empty-root", bytes.fromhex("06" * 16),
        )
        for algorithm in ("sha1", "sha256"):
            with self.subTest(algorithm=algorithm):
                backend = _FakeWindowsTreeBackend(root)
                child_oid = _expected_git_tree(algorithm, [
                    (
                        b"nested.bin", False, b"100644",
                        _expected_git_blob(algorithm, b"xy"),
                    ),
                ])
                expected = _expected_git_tree(algorithm, [
                    (b"a.txt", False, b"100644", _expected_git_blob(algorithm, b"abc")),
                    (b"dir", True, b"40000", child_oid),
                ])
                actual = self._builder()(
                    _FakeWindowsHandle(root), backend, object_format=algorithm,
                )

                self.assertEqual(actual, expected)
                self.assertTrue(all(handle.closed for handle in backend.opened))

    def test_builder_rejects_identity_mismatch_before_reading_file(self) -> None:
        class MismatchedBackend(_FakeWindowsTreeBackend):
            def open_child(self, parent, entry, *, directory):
                handle = super().open_child(parent, entry, directory=directory)
                handle.node.file_id = bytes.fromhex("ff" * 16)
                return handle

        root = _FakeWindowsNode("", bytes.fromhex("11" * 16))
        root.children["file.txt"] = _FakeWindowsNode(
            "file.txt", bytes.fromhex("22" * 16), content=b"do not read",
        )
        backend = MismatchedBackend(root)

        with self.assertRaises(WorktreeTreeUnavailable) as raised:
            self._builder()(
                _FakeWindowsHandle(root), backend, object_format="sha1",
            )

        self.assertEqual(raised.exception.reason, "windows_entry_identity_changed")
        self.assertEqual(backend.read_calls, 0)
        self.assertTrue(all(handle.closed for handle in backend.opened))

    def test_builder_rejects_regular_file_handle_eof_mismatch(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("16" * 16))
        source = _FakeWindowsNode(
            "source.py", bytes.fromhex("17" * 16), content=b"must not read",
        )
        source.handle_end_of_file = len(source.content or b"") + 1
        root.children["source.py"] = source
        backend = _FakeWindowsTreeBackend(root)

        with self.assertRaises(WorktreeTreeUnavailable) as raised:
            self._builder()(
                _FakeWindowsHandle(root), backend, object_format="sha1",
            )

        self.assertEqual(raised.exception.reason, "windows_entry_identity_changed")
        self.assertEqual(backend.read_calls, 0)
        self.assertTrue(all(handle.closed for handle in backend.opened))

    def test_builder_excludes_root_git_metadata_from_tree_and_drift_receipt(self) -> None:
        class GitMetadataChangingBackend(_FakeWindowsTreeBackend):
            def __init__(self, root):
                super().__init__(root)
                self.root_enumerations = 0

            def enumerate_directory(self, handle):
                if handle.node is self.root:
                    self.root_enumerations += 1
                    if self.root_enumerations == 2:
                        self.root.children[".git"].change_time += 1
                return super().enumerate_directory(handle)

        root = _FakeWindowsNode("", bytes.fromhex("51" * 16))
        root.children[".git"] = _FakeWindowsNode(
            ".git", bytes.fromhex("52" * 16),
        )
        backend = GitMetadataChangingBackend(root)

        actual = self._builder()(
            _FakeWindowsHandle(root), backend, object_format="sha1",
        )

        self.assertEqual(actual, _expected_git_tree("sha1", []))

    def test_builder_matches_git_symlink_entry_without_reading_target(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("91" * 16))
        link = _FakeWindowsNode(
            "alias", bytes.fromhex("92" * 16), content=b"target file bytes",
        )
        link.reparse_target = "../external.txt"
        root.children["alias"] = link
        backend = _FakeWindowsTreeBackend(root)

        actual = self._builder()(
            _FakeWindowsHandle(root), backend, object_format="sha1",
        )

        self.assertEqual(actual, _expected_git_tree("sha1", [
            (
                b"alias", False, b"120000",
                _expected_git_blob("sha1", b"../external.txt"),
            ),
        ]))
        self.assertEqual(backend.read_calls, 0)
        self.assertTrue(all(handle.closed for handle in backend.opened))

    def test_builder_matches_git_directory_symlink_entry_without_traversing_target(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("93" * 16))
        directory_link = _FakeWindowsNode(
            "alias-dir", bytes.fromhex("94" * 16),
        )
        directory_link.reparse_target = "../target-dir"
        root.children["alias-dir"] = directory_link
        backend = _FakeWindowsTreeBackend(root)

        actual = self._builder()(
            _FakeWindowsHandle(root), backend, object_format="sha1",
        )

        self.assertEqual(actual, _expected_git_tree("sha1", [
            (
                b"alias-dir", False, b"120000",
                _expected_git_blob("sha1", b"../target-dir"),
            ),
        ]))
        self.assertEqual(backend.read_calls, 0)
        self.assertTrue(all(handle.closed for handle in backend.opened))

    def test_builder_rejects_junction_before_opening_or_enumerating_target(self) -> None:
        root = _FakeWindowsNode("", bytes.fromhex("a1" * 16))
        junction = _FakeWindowsNode("junction", bytes.fromhex("a2" * 16))
        junction.reparse = True
        junction.reparse_tag = 0xA0000003
        root.children["junction"] = junction
        backend = _FakeWindowsTreeBackend(root)

        with self.assertRaisesRegex(
            WorktreeTreeUnavailable, "windows_reparse_point_unsupported",
        ):
            self._builder()(
                _FakeWindowsHandle(root), backend, object_format="sha1",
            )

        self.assertEqual(backend.opened, [])
        self.assertEqual(backend.read_calls, 0)


@unittest.skipUnless(os.name == "nt", "requires native Windows file handles and Git")
class TestNativeWindowsWorktreeTreeOID(unittest.TestCase):
    def _git(self, root: Path, *arguments: str) -> str:
        import subprocess

        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True, capture_output=True, text=True,
        )
        return result.stdout.strip()

    def _object_directory_state(self, objects: Path):
        return tuple(
            (
                path.relative_to(objects).as_posix(),
                path.stat().st_size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in sorted(objects.rglob("*"))
            if path.is_file()
        )

    def test_native_worktree_oid_matches_git_without_index_or_odb_writes(self) -> None:
        from icode.workspace_snapshot import worktree_git_tree_oid

        import subprocess

        with tempfile.TemporaryDirectory(prefix="icode-r3-tree-") as temporary:
            repo = Path(temporary) / "repo café"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            self._git(repo, "config", "user.name", "ICODE tests")
            self._git(repo, "config", "user.email", "icode-tests@example.invalid")
            (repo / "simple.txt").write_bytes(b"alpha\n")
            (repo / "name with 空格.txt").write_bytes(b"unicode\n")
            (repo / "nested").mkdir()
            (repo / "nested" / "child.bin").write_bytes(bytes(range(64)))
            self._git(repo, "add", "-A")
            expected = self._git(repo, "write-tree")

            index = repo / ".git" / "index"
            index_before = (index.read_bytes(), index.stat().st_mtime_ns)
            object_dir = repo / ".git" / "objects"
            objects_before = self._object_directory_state(object_dir)

            actual = worktree_git_tree_oid(repo, object_format="sha1")

            self.assertEqual(actual, expected)
            self.assertEqual(
                (index.read_bytes(), index.stat().st_mtime_ns), index_before,
            )
            self.assertEqual(self._object_directory_state(object_dir), objects_before)

    def test_native_worktree_sha256_oid_matches_git(self) -> None:
        from icode.workspace_snapshot import worktree_git_tree_oid

        import subprocess

        with tempfile.TemporaryDirectory(prefix="icode-r3-tree-sha256-") as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            subprocess.run(
                ["git", "init", "-q", "--object-format=sha256", str(repo)],
                check=True, capture_output=True,
            )
            (repo / "sha256.txt").write_bytes(b"sha256\n")
            self._git(repo, "add", "sha256.txt")
            expected = self._git(repo, "write-tree")

            self.assertEqual(
                worktree_git_tree_oid(repo, object_format="sha256"), expected,
            )

    def test_native_workspace_snapshot_uses_handles_and_keeps_ignored_outputs_out(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-r3-snapshot-") as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            (workspace / "safe.py").write_bytes(b"source\n")
            (workspace / ".icode_output").mkdir()
            (workspace / ".icode_output" / "receipt.md").write_text(
                "ignored", encoding="utf-8",
            )
            (workspace / "__pycache__").mkdir()
            (workspace / "__pycache__" / "generated.pyc").write_bytes(b"ignored")

            actual = workspace_snapshot.snapshot_workspace(workspace)

        self.assertEqual(actual, {
            "safe.py": workspace_snapshot._entry_hash(
                "file", "100644", b"source\n",
            ),
        })

    def test_native_worktree_oid_matches_git_symlink_entry(self) -> None:
        from icode.workspace_snapshot import worktree_git_tree_oid

        import subprocess

        with tempfile.TemporaryDirectory(prefix="icode-r3-tree-symlink-") as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            self._git(repo, "config", "core.symlinks", "true")
            (repo / "safe.txt").write_bytes(b"target\n")
            target_directory = repo / "target-dir"
            target_directory.mkdir()
            (target_directory / "inside.txt").write_bytes(b"directory target\n")
            alias = repo / "alias"
            directory_alias = repo / "alias-dir"
            try:
                os.symlink("safe.txt", alias)
                os.symlink(
                    "target-dir", directory_alias, target_is_directory=True,
                )
            except (NotImplementedError, OSError) as exc:
                if os.environ.get("ICODE_REQUIRE_WINDOWS_NATIVE_SYMLINKS") == "1":
                    self.fail(f"required Windows symlink creation unavailable: {exc}")
                self.skipTest(f"Windows symlink creation unavailable: {exc}")
            self._git(repo, "add", "-A")
            for name in ("alias", "alias-dir"):
                mode = self._git(repo, "ls-files", "-s", name).split()[0]
                self.assertEqual(mode, "120000")
            expected = self._git(repo, "write-tree")

            self.assertEqual(
                worktree_git_tree_oid(repo, object_format="sha1"), expected,
            )

            # Keep production checks unchanged while making native mismatches
            # actionable in CI logs instead of reporting only a generic reason.
            check_entry_identity = workspace_snapshot._require_windows_entry_identity
            check_symlink_identity = workspace_snapshot._require_windows_symlink_identity
            walk_windows_directory = windows_worktree._walk_windows_directory
            native_backend_type = windows_worktree._WindowsNativeWorktreeBackend
            snapshot_diagnostic = {"attempt": 0, "parts": ()}
            change_time_locations: dict[int, str] = {}

            def observe_snapshot_backend(*args, **kwargs):
                snapshot_diagnostic["attempt"] += 1
                return native_backend_type(*args, **kwargs)

            def observe_snapshot_walk(*args, **kwargs):
                parts = kwargs.get("snapshot_parts", ())
                previous_parts = snapshot_diagnostic["parts"]
                snapshot_diagnostic["parts"] = parts
                try:
                    return walk_windows_directory(*args, **kwargs)
                finally:
                    snapshot_diagnostic["parts"] = previous_parts

            def report_identity_mismatch(check, entry, info, *args, **kwargs):
                try:
                    check(entry, info, *args, **kwargs)
                except WorktreeTreeUnavailable as exc:
                    if exc.reason not in {
                        "windows_entry_identity_changed",
                        "windows_directory_entry_change_time_changed",
                    }:
                        raise
                    attempt = snapshot_diagnostic["attempt"]
                    if (
                        exc.reason == "windows_directory_entry_change_time_changed"
                        and attempt in (1, 2)
                    ):
                        change_time_locations.setdefault(
                            attempt,
                            _safe_windows_snapshot_change_location(
                                snapshot_diagnostic["parts"], entry.name,
                            ),
                        )
                    expected_volume = args[0] if args else None
                    expected_directory = kwargs.get("is_directory")
                    raise WorktreeTreeUnavailable(
                        f"{exc.reason}:name={entry.name!r} "
                        f"volume={expected_volume!r}/{info.volume_serial_number!r} "
                        f"entry_id={entry.file_id.hex()} handle_id={info.file_id.hex()} "
                        f"entry_change={entry.change_time} handle_change={info.change_time} "
                        f"entry_size={entry.end_of_file} handle_size={info.end_of_file} "
                        f"directory={expected_directory!r}/{info.is_directory!r} "
                        f"delete_pending={info.delete_pending!r} "
                        f"entry_attributes={entry.attributes:#x} "
                        f"handle_attributes={info.attributes:#x} "
                        f"entry_tag={entry.reparse_tag:#x} handle_tag={info.reparse_tag:#x}"
                    ) from None

            with (
                patch.object(
                    workspace_snapshot,
                    "_require_windows_entry_identity",
                    side_effect=lambda *args, **kwargs: report_identity_mismatch(
                        check_entry_identity, *args, **kwargs,
                    ),
                ),
                patch.object(
                    workspace_snapshot,
                    "_require_windows_symlink_identity",
                    side_effect=lambda *args, **kwargs: report_identity_mismatch(
                        check_symlink_identity, *args, **kwargs,
                    ),
                ),
                patch.object(
                    workspace_snapshot,
                    "_walk_windows_directory",
                    side_effect=observe_snapshot_walk,
                ),
                patch.object(
                    windows_worktree,
                    "_walk_windows_directory",
                    side_effect=observe_snapshot_walk,
                ),
                patch.object(
                    windows_worktree,
                    "_WindowsNativeWorktreeBackend",
                    side_effect=observe_snapshot_backend,
                ),
            ):
                try:
                    snapshot = workspace_snapshot.snapshot_workspace(repo)
                except OSError as exc:
                    if change_time_locations:
                        receipt = _safe_windows_snapshot_change_receipt(
                            change_time_locations,
                        )
                        raise OSError(f"{exc};safe_diag={receipt}") from None
                    raise

            self.assertEqual(
                snapshot["alias"],
                workspace_snapshot._entry_hash(
                    "symlink", "120000", os.fsencode(os.readlink(alias)),
                ),
            )
            self.assertEqual(
                snapshot["alias-dir"],
                workspace_snapshot._entry_hash(
                    "symlink", "120000", os.fsencode(os.readlink(directory_alias)),
                ),
            )

    def test_native_snapshot_file_handles_allow_concurrent_write_and_rename(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-r3-sharing-") as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            file_path = root / "content.txt"
            file_path.write_bytes(b"stable content\n")
            moved_path = root / "moved.txt"
            backend = windows_worktree._WindowsNativeWorktreeBackend()
            root_handle = backend.open_root(root)
            file_handle = None
            try:
                entry = next(
                    item for item in backend.enumerate_directory(root_handle)
                    if item.name == file_path.name
                )
                file_handle = backend.open_child(
                    root_handle, entry, directory=False,
                )
                with file_path.open("r+b"):
                    pass
                os.replace(file_path, moved_path)
                os.replace(moved_path, file_path)
            finally:
                if file_handle is not None:
                    backend.close_handle(file_handle)
                backend.close_root(root_handle)

            self.assertEqual(file_path.read_bytes(), b"stable content\n")


if __name__ == "__main__":
    unittest.main()
