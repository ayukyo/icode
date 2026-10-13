"""Exact Windows dot exclusion retains record and child identity checks."""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import unittest
from pathlib import Path

from icode import workspace_snapshot as ws
from icode.workspace_snapshot import WorktreeTreeUnavailable
from tests.test_windows_worktree_tree_oid import _directory_record


_VALID_ID = bytes.fromhex("00112233445566778899aabbccddeeff")
_SENTINELS = (bytes(16), bytes([0xFF]) * 16)


def _observe_parse(payload: bytes):
    # A baseline rejection is an assertion difference, never a test ERROR.
    try:
        return ws._parse_windows_directory_entries(payload)
    except WorktreeTreeUnavailable as exc:
        return ("rejected", exc.reason)


def _observe_collect(responses):
    remaining = iter(responses)
    calls = []

    def read_page(information_class: int, buffer_bytes: int):
        calls.append((information_class, buffer_bytes))
        return next(remaining)

    try:
        result = ws._collect_windows_directory_entries(read_page, buffer_bytes=4096)
    except WorktreeTreeUnavailable as exc:
        result = ("rejected", exc.reason)
    return result, calls


def _dot_page(file_id: bytes = bytes(16)) -> bytes:
    return (
        _directory_record(".", file_id=file_id, attributes=0x10, next_entry_offset=96)
        + _directory_record("..", file_id=file_id, attributes=0x10)
    )


def _git_sha1(kind: bytes, content: bytes) -> bytes:
    return hashlib.sha1(kind + b" " + str(len(content)).encode("ascii") + b"\0" + content).digest()


def _observe_native(operation):
    try:
        return operation()
    except (OSError, WorktreeTreeUnavailable):
        # Native production refusal remains an assertion failure, never skip.
        return ("rejected", "native_workspace_rejection")


class TestWindowsDotEntryIdentity(unittest.TestCase):
    def test_exact_dot_sentinel_ids_are_excluded(self) -> None:
        for name in (".", ".."):
            for file_id in (*_SENTINELS, _VALID_ID):
                with self.subTest(name=name, identity=file_id):
                    self.assertEqual(
                        _observe_parse(_directory_record(name, file_id=file_id, attributes=0x10)),
                        (),
                    )

    def test_mixed_page_keeps_every_real_child_field(self) -> None:
        child = _directory_record(
            "café.bin", file_id=_VALID_ID, attributes=0x400,
            reparse_tag=0xA000000C, change_time=123456, end_of_file=17,
        )
        payload = (
            _directory_record(".", file_id=bytes(16), attributes=0x10, next_entry_offset=96)
            + _directory_record("..", file_id=bytes(16), attributes=0x10, next_entry_offset=96)
            + child
        )
        self.assertEqual(_observe_parse(payload), (
            ws._WindowsDirectoryEntry("café.bin", 0x400, 0xA000000C, _VALID_ID, 123456, 17),
        ))

    def test_real_and_near_dot_children_reject_sentinel_ids(self) -> None:
        for name in ("child.txt", ". ", ".. ", "..."):
            for file_id in _SENTINELS:
                with self.subTest(name=name, identity=file_id):
                    self.assertEqual(
                        _observe_parse(_directory_record(name, file_id=file_id)),
                        ("rejected", "windows_directory_record_invalid"),
                    )

    def test_dot_records_keep_structure_and_name_rejections(self) -> None:
        cases = []
        for name in (".", ".."):
            for file_id in (*_SENTINELS, _VALID_ID):
                for name_length in (0, 1, 512, 510):
                    invalid = bytearray(_directory_record(name, file_id=file_id))
                    struct.pack_into("<I", invalid, 60, name_length)
                    cases.append((bytes(invalid), "windows_directory_record_invalid"))
                for position in (32, 40):
                    invalid = bytearray(_directory_record(name, file_id=file_id))
                    struct.pack_into("<q", invalid, position, -1)
                    cases.append((bytes(invalid), "windows_directory_record_invalid"))
                invalid = bytearray(_directory_record(name, file_id=file_id))
                invalid[88:90] = b"\x00\xd8"
                cases.append((bytes(invalid), "windows_directory_name_invalid"))
        for name in ("\0", "./", ".\\", ".:"):
            cases.append((
                _directory_record(name, file_id=bytes(16)),
                "windows_directory_name_invalid",
            ))
        for payload, reason in cases:
            with self.subTest(reason=reason, header=payload[:88]):
                self.assertEqual(_observe_parse(payload), ("rejected", reason))

    def test_dot_records_keep_offset_trailing_and_header_rejections(self) -> None:
        for name in (".", ".."):
            for file_id in (*_SENTINELS, _VALID_ID):
                base = _directory_record(name, file_id=file_id)
                for next_offset in (1, 88, 4096):
                    invalid = bytearray(base)
                    struct.pack_into("<I", invalid, 0, next_offset)
                    with self.subTest(name=name, identity=file_id, offset=next_offset):
                        self.assertEqual(
                            _observe_parse(bytes(invalid)),
                            ("rejected", "windows_directory_offset_invalid"),
                        )
                self.assertEqual(
                    _observe_parse(base + b"\x01"),
                    ("rejected", "windows_directory_record_trailing_data"),
                )
        self.assertEqual(
            _observe_parse(b"\x01" + bytes(86)),
            ("rejected", "windows_directory_record_truncated"),
        )

    def test_first_dot_only_page_continues_then_keeps_child(self) -> None:
        child = _directory_record("child.txt", file_id=_VALID_ID)
        result, calls = _observe_collect([
            (True, 0, _dot_page()), (True, 0, child), (False, 18, b""),
        ])
        self.assertEqual(result, (ws._WindowsDirectoryEntry("child.txt", 0x80, 0, _VALID_ID, 0, 0),))
        self.assertEqual(calls, [(20, 4096), (19, 4096), (19, 4096)])

    def test_first_dot_only_page_requires_native_eof(self) -> None:
        result, calls = _observe_collect([(True, 0, _dot_page()), (False, 18, b"")])
        self.assertEqual(result, ())
        self.assertEqual(calls, [(20, 4096), (19, 4096)])

    def test_second_dot_only_page_is_no_progress(self) -> None:
        result, calls = _observe_collect([(True, 0, _dot_page()), (True, 0, _dot_page())])
        self.assertEqual(result, ("rejected", "windows_directory_enumeration_no_progress"))
        self.assertEqual(calls, [(20, 4096), (19, 4096)])


@unittest.skipUnless(os.name == "nt", "requires actual Windows native directory APIs")
class TestWindowsDotEntryIdentityNative(unittest.TestCase):
    def test_native_empty_directory_snapshot_and_oid(self) -> None:
        with tempfile.TemporaryDirectory(prefix="icode-dot-empty-") as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(_observe_native(lambda: ws.snapshot_workspace(root)), {})
            self.assertEqual(
                _observe_native(lambda: ws.worktree_git_tree_oid(root, object_format="sha1")),
                _git_sha1(b"tree", b"").hex(),
            )
        self.assertFalse(root.exists())

    def test_native_file_and_nested_empty_directories(self) -> None:
        content = b"dot identity\n"
        with tempfile.TemporaryDirectory(prefix="icode-dot-child-") as temporary:
            root = Path(temporary).resolve()
            (root / "empty" / "nested").mkdir(parents=True)
            (root / "child.txt").write_bytes(content)
            # Literal pieces avoid Python octal escape ambiguity in the oracle.
            expected_snapshot = hashlib.sha256(
                b"icode-workspace-entry-v2\0" + b"file\0" + b"100644\0" + content,
            ).hexdigest()
            self.assertEqual(
                _observe_native(lambda: ws.snapshot_workspace(root)),
                {"child.txt": expected_snapshot},
            )
            tree_body = b"100644 child.txt\0" + _git_sha1(b"blob", content)
            self.assertEqual(
                _observe_native(lambda: ws.worktree_git_tree_oid(root, object_format="sha1")),
                _git_sha1(b"tree", tree_body).hex(),
            )
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
