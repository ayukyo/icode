"""Test-only Windows file-ID directory enumeration probe."""

from __future__ import annotations

import ctypes
import importlib
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.windows_tree_snapshot_probe import (
    _FileIdBothDirectoryInfoHeader,
    _FileIdExtdDirectoryInfoHeader,
    _FileIdInfo,
)

_HEADER_SIZE = ctypes.sizeof(_FileIdBothDirectoryInfoHeader)
_EXTD_HEADER_SIZE = 88


def _entry_record(
    name: str,
    *,
    file_id: int,
    attributes: int = 0x80,
    next_entry_offset: int = 0,
) -> bytes:
    name_bytes = name.encode("utf-16-le")
    record = bytearray(max(_HEADER_SIZE + len(name_bytes), next_entry_offset))
    struct.pack_into(
        "<I", record, _FileIdBothDirectoryInfoHeader.next_entry_offset.offset,
        next_entry_offset,
    )
    struct.pack_into(
        "<I", record, _FileIdBothDirectoryInfoHeader.file_attributes.offset, attributes,
    )
    struct.pack_into(
        "<I", record, _FileIdBothDirectoryInfoHeader.file_name_length.offset,
        len(name_bytes),
    )
    struct.pack_into(
        "<Q", record, _FileIdBothDirectoryInfoHeader.file_id.offset, file_id,
    )
    record[_HEADER_SIZE:_HEADER_SIZE + len(name_bytes)] = name_bytes
    return bytes(record)


def _extd_entry_record(
    name: str,
    *,
    file_id: bytes,
    attributes: int = 0x80,
    reparse_tag: int = 0,
    next_entry_offset: int = 0,
) -> bytes:
    name_bytes = name.encode("utf-16-le")
    if len(file_id) != 16:
        raise ValueError("extended file identifier must be 16 bytes")
    record = bytearray(max(_EXTD_HEADER_SIZE + len(name_bytes), next_entry_offset))
    struct.pack_into("<I", record, 0, next_entry_offset)
    struct.pack_into("<I", record, 56, attributes)
    struct.pack_into("<I", record, 60, len(name_bytes))
    struct.pack_into("<I", record, 68, reparse_tag)
    record[72:88] = file_id
    record[_EXTD_HEADER_SIZE:_EXTD_HEADER_SIZE + len(name_bytes)] = name_bytes
    return bytes(record)


class TestFileIdDirectoryInfoParser(unittest.TestCase):
    def _parser_module(self):
        try:
            return importlib.import_module("tests.windows_tree_snapshot_probe")
        except ImportError:
            return None

    def test_ctypes_header_matches_documented_fixed_header_size(self) -> None:
        self.assertEqual(_HEADER_SIZE, 104)
        self.assertEqual(
            _FileIdBothDirectoryInfoHeader.file_id.offset % 8,
            0,
            "64-bit file identifier must retain native alignment",
        )

    def test_parser_returns_name_attributes_and_full_file_id(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_both_directory_info", None)
        self.assertTrue(callable(parser), "Windows directory-info parser is missing")

        entries = parser(_entry_record("源 file.txt", file_id=0xFEDCBA9876543210))

        self.assertEqual(
            [(entry.name, entry.attributes, entry.file_id) for entry in entries],
            [("源 file.txt", 0x80, 0xFEDCBA9876543210)],
        )

    def test_parser_walks_multiple_aligned_records_and_preserves_reparse_flag(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_both_directory_info", None)
        self.assertTrue(callable(parser), "Windows directory-info parser is missing")
        first_size = _HEADER_SIZE + len("first.txt".encode("utf-16-le"))
        first_offset = (first_size + 7) & ~7
        buffer = (
            _entry_record(
                "first.txt", file_id=7, next_entry_offset=first_offset,
            )
            + _entry_record(
                "link", file_id=9, attributes=0x400, next_entry_offset=0,
            )
        )

        entries = parser(buffer)

        self.assertEqual(
            [(entry.name, entry.file_id, entry.attributes) for entry in entries],
            [("first.txt", 7, 0x80), ("link", 9, 0x400)],
        )

    def test_parser_rejects_odd_utf16_name_length(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_both_directory_info", None)
        error_type = getattr(module, "WindowsDirectoryProbeError", RuntimeError)
        self.assertTrue(callable(parser), "Windows directory-info parser is missing")
        buffer = bytearray(_entry_record("name", file_id=1))
        struct.pack_into(
            "<I", buffer, _FileIdBothDirectoryInfoHeader.file_name_length.offset, 3,
        )

        with self.assertRaises(error_type):
            parser(bytes(buffer))

    def test_parser_rejects_unaligned_or_out_of_bounds_next_offset(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_both_directory_info", None)
        error_type = getattr(module, "WindowsDirectoryProbeError", RuntimeError)
        self.assertTrue(callable(parser), "Windows directory-info parser is missing")
        record = _entry_record("name", file_id=1)

        for next_offset in (1, len(record) + 8):
            malformed = bytearray(record)
            struct.pack_into("<I", malformed, 0, next_offset)
            with self.subTest(next_offset=next_offset):
                with self.assertRaises(error_type):
                    parser(bytes(malformed))


class TestFileIdExtdDirectoryInfoParser(unittest.TestCase):
    def test_ctypes_header_matches_documented_extd_layout(self) -> None:
        self.assertEqual(ctypes.sizeof(_FileIdExtdDirectoryInfoHeader), _EXTD_HEADER_SIZE)
        self.assertEqual(_FileIdExtdDirectoryInfoHeader.reparse_point_tag.offset, 68)
        self.assertEqual(_FileIdExtdDirectoryInfoHeader.file_id.offset, 72)
        self.assertEqual(ctypes.sizeof(_FileIdInfo), 24)
        self.assertEqual(_FileIdInfo.volume_serial_number.offset, 0)
        self.assertEqual(_FileIdInfo.file_id.offset, 8)

    def _parser_module(self):
        try:
            return importlib.import_module("tests.windows_tree_snapshot_probe")
        except ImportError:
            return None

    def test_parser_accepts_empty_directory_records_and_zero_filled_api_buffer(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_extd_directory_info", None)
        self.assertTrue(callable(parser), "extended Windows directory-info parser is missing")

        self.assertEqual(parser(bytes(_EXTD_HEADER_SIZE)), ())
        self.assertEqual(parser(bytes(1024)), ())

    def test_parser_preserves_name_attributes_reparse_tag_and_128_bit_id(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_extd_directory_info", None)
        self.assertTrue(callable(parser), "extended Windows directory-info parser is missing")
        file_id = bytes.fromhex("00112233445566778899aabbccddeeff")

        entries = parser(
            _extd_entry_record(
                "链接.bin", file_id=file_id,
                attributes=0x400, reparse_tag=0xA000000C,
            )
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "链接.bin")
        self.assertEqual(entries[0].attributes, 0x400)
        self.assertEqual(entries[0].reparse_tag, 0xA000000C)
        self.assertEqual(entries[0].file_id, file_id)

    def test_parser_rejects_unusable_128_bit_file_id_sentinels(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_extd_directory_info", None)
        error_type = getattr(module, "WindowsDirectoryProbeError", RuntimeError)
        self.assertTrue(callable(parser), "extended Windows directory-info parser is missing")

        for file_id in (bytes(16), bytes([0xFF]) * 16):
            with self.subTest(file_id=file_id.hex()):
                with self.assertRaises(error_type):
                    parser(_extd_entry_record("ordinary.bin", file_id=file_id))

    def test_parser_walks_aligned_records_and_ignores_fixed_buffer_padding(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_extd_directory_info", None)
        self.assertTrue(callable(parser), "extended Windows directory-info parser is missing")
        first_size = _EXTD_HEADER_SIZE + len("first.txt".encode("utf-16-le"))
        first_offset = (first_size + 7) & ~7
        buffer = (
            _extd_entry_record(
                "first.txt", file_id=bytes.fromhex("00000000000000000000000000000001"),
                next_entry_offset=first_offset,
            )
            + _extd_entry_record(
                "second.txt", file_id=bytes.fromhex("00000000000000000000000000000002"),
            )
        )

        entries = parser(buffer + bytes(1024 - len(buffer)))

        self.assertEqual(
            [(entry.name, entry.file_id) for entry in entries],
            [
                ("first.txt", bytes.fromhex("00000000000000000000000000000001")),
                ("second.txt", bytes.fromhex("00000000000000000000000000000002")),
            ],
        )

    def test_parser_rejects_truncated_header_and_invalid_name_bounds(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_extd_directory_info", None)
        error_type = getattr(module, "WindowsDirectoryProbeError", RuntimeError)
        self.assertTrue(callable(parser), "extended Windows directory-info parser is missing")

        malformed_buffers = [
            bytes(_EXTD_HEADER_SIZE - 1),
            "not a byte buffer",
            _extd_entry_record("name", file_id=bytes(16))[:_EXTD_HEADER_SIZE - 1],
            _extd_entry_record("", file_id=bytes(16)),
        ]
        odd_length = bytearray(_extd_entry_record("name", file_id=bytes(16)))
        struct.pack_into("<I", odd_length, 60, 3)
        malformed_buffers.append(bytes(odd_length))
        truncated_name = bytearray(_extd_entry_record("name", file_id=bytes(16)))
        struct.pack_into("<I", truncated_name, 60, len(truncated_name))
        malformed_buffers.append(bytes(truncated_name))
        invalid_utf16 = bytearray(_extd_entry_record("x", file_id=bytes(16)))
        invalid_utf16[_EXTD_HEADER_SIZE:_EXTD_HEADER_SIZE + 2] = b"\x00\xd8"
        malformed_buffers.append(bytes(invalid_utf16))

        for malformed in malformed_buffers:
            with self.subTest(length=len(malformed)):
                with self.assertRaises(error_type):
                    parser(malformed)

    def test_parser_rejects_malformed_offsets_and_non_component_names(self) -> None:
        module = self._parser_module()
        parser = getattr(module, "parse_file_id_extd_directory_info", None)
        error_type = getattr(module, "WindowsDirectoryProbeError", RuntimeError)
        self.assertTrue(callable(parser), "extended Windows directory-info parser is missing")

        record = _extd_entry_record("name", file_id=bytes(16))
        malformed_records = []
        for next_offset in (1, _EXTD_HEADER_SIZE, len(record), len(record) + 8):
            malformed = bytearray(record)
            struct.pack_into("<I", malformed, 0, next_offset)
            malformed_records.append(bytes(malformed))
        for name in ("folder/child", "folder\\child", "stream:name", "bad\x00name"):
            malformed_records.append(_extd_entry_record(name, file_id=bytes(16)))

        for malformed in malformed_records:
            with self.subTest():
                with self.assertRaises(error_type):
                    parser(malformed)

    def test_parser_enforces_buffer_and_entry_limits(self) -> None:
        from unittest.mock import patch

        module = self._parser_module()
        parser = getattr(module, "parse_file_id_extd_directory_info", None)
        error_type = getattr(module, "WindowsDirectoryProbeError", RuntimeError)
        self.assertTrue(callable(parser), "extended Windows directory-info parser is missing")

        with patch.object(module, "_MAX_DIRECTORY_BUFFER_BYTES", 8):
            with self.assertRaises(error_type):
                parser(bytes(9))

        pair = (
            _extd_entry_record(
                "one", file_id=bytes.fromhex("00000000000000000000000000000001"),
                next_entry_offset=(
                    _EXTD_HEADER_SIZE + len("one".encode("utf-16-le")) + 7
                ) & ~7,
            )
            + _extd_entry_record(
                "two", file_id=bytes.fromhex("00000000000000000000000000000002"),
            )
        )
        with patch.object(module, "_MAX_DIRECTORY_ENTRIES", 1):
            with self.assertRaises(error_type):
                parser(pair)


class TestFileIdExtdDirectoryPagination(unittest.TestCase):
    def test_collector_uses_restart_then_continuation_and_requires_explicit_eof(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        collect = getattr(module, "collect_extd_directory_entries", None)
        self.assertTrue(callable(collect), "bounded directory page collector is missing")

        def record(name: str, file_id: int) -> bytes:
            return _extd_entry_record(
                name, file_id=file_id.to_bytes(16, "little"),
            )

        pages = [
            (True, 0, record("one.txt", 1)),
            (True, 0, record("two.txt", 2)),
            (False, 18, b""),  # ERROR_NO_MORE_FILES
        ]
        information_classes = []

        def read_page(information_class: int, buffer_bytes: int):
            information_classes.append((information_class, buffer_bytes))
            return pages.pop(0)

        entries = collect(read_page, buffer_bytes=512)

        self.assertEqual([entry.name for entry in entries], ["one.txt", "two.txt"])
        self.assertEqual(
            information_classes,
            [
                (module._FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS, 512),
                (module._FILE_ID_EXTD_DIRECTORY_INFO_CLASS, 512),
                (module._FILE_ID_EXTD_DIRECTORY_INFO_CLASS, 512),
            ],
        )
        self.assertEqual(pages, [])

    def test_collector_accepts_only_empty_first_page_or_explicit_empty_eof(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        collect = getattr(module, "collect_extd_directory_entries", None)
        self.assertTrue(callable(collect), "bounded directory page collector is missing")

        self.assertEqual(
            collect(lambda _info_class, _size: (False, 18, b""), buffer_bytes=512),
            (),
        )
        self.assertEqual(
            collect(
                lambda _info_class, size: (True, 0, bytes(size)),
                buffer_bytes=512,
            ),
            (),
        )

    def test_collector_accepts_zero_filled_success_as_eof_after_entries(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        collect = getattr(module, "collect_extd_directory_entries", None)
        self.assertTrue(callable(collect), "bounded directory page collector is missing")
        first = _extd_entry_record(
            "one.txt", file_id=bytes.fromhex("00000000000000000000000000000001"),
        )
        pages = [(True, 0, first), (True, 0, bytes(512))]

        entries = collect(
            lambda _info_class, _size: pages.pop(0), buffer_bytes=512,
        )

        self.assertEqual([entry.name for entry in entries], ["one.txt"])
        self.assertEqual(pages, [])

    def test_collector_accepts_zero_filled_continuation_after_filtered_restart(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        collect = getattr(module, "collect_extd_directory_entries", None)
        self.assertTrue(callable(collect), "bounded directory page collector is missing")
        dot_page = _extd_entry_record(
            ".", file_id=bytes.fromhex("00000000000000000000000000000004"),
        )
        pages = [(True, 0, dot_page), (True, 0, bytes(512))]
        information_classes = []

        def read_page(information_class: int, _size: int):
            information_classes.append(information_class)
            return pages.pop(0)

        entries = collect(read_page, buffer_bytes=512)

        self.assertEqual(entries, ())
        self.assertEqual(
            information_classes,
            [
                module._FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
                module._FILE_ID_EXTD_DIRECTORY_INFO_CLASS,
            ],
        )
        self.assertEqual(pages, [])

    def test_collector_continues_after_filtered_restart_page(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        collect = getattr(module, "collect_extd_directory_entries", None)
        self.assertTrue(callable(collect), "bounded directory page collector is missing")
        dot_page = _extd_entry_record(
            ".", file_id=bytes.fromhex("00000000000000000000000000000002"),
        )
        file_page = _extd_entry_record(
            "one.txt", file_id=bytes.fromhex("00000000000000000000000000000003"),
        )
        pages = [(True, 0, dot_page), (True, 0, file_page), (False, 18, b"")]
        information_classes = []

        def read_page(information_class: int, _size: int):
            information_classes.append(information_class)
            return pages.pop(0)

        entries = collect(read_page, buffer_bytes=512)

        self.assertEqual([entry.name for entry in entries], ["one.txt"])
        self.assertEqual(
            information_classes,
            [
                module._FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
                module._FILE_ID_EXTD_DIRECTORY_INFO_CLASS,
                module._FILE_ID_EXTD_DIRECTORY_INFO_CLASS,
            ],
        )
        self.assertEqual(pages, [])

    def test_collector_rejects_unknown_errors_duplicate_names_and_empty_continuation(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        collect = getattr(module, "collect_extd_directory_entries", None)
        self.assertTrue(callable(collect), "bounded directory page collector is missing")
        error_type = getattr(module, "WindowsDirectoryProbeError")
        first = _extd_entry_record(
            "same.txt", file_id=bytes.fromhex("00000000000000000000000000000001"),
        )

        scenarios = [
            (
                [(True, 0, first), (False, 5, b"")],
                "directory_enumeration_failed",
            ),
            (
                [(False, 234, b"")],
                "directory_buffer_too_small",
            ),
            (
                [
                    (True, 0, first),
                    (
                        True,
                        0,
                        _extd_entry_record(
                            ".",
                            file_id=bytes.fromhex(
                                "00000000000000000000000000000003",
                            ),
                        ),
                    ),
                ],
                "directory_enumeration_no_progress",
            ),
            (
                [
                    (
                        True,
                        0,
                        _extd_entry_record(
                            ".",
                            file_id=bytes.fromhex(
                                "00000000000000000000000000000002",
                            ),
                        ),
                    ),
                    (
                        True,
                        0,
                        _extd_entry_record(
                            "..",
                            file_id=bytes.fromhex(
                                "00000000000000000000000000000003",
                            ),
                        ),
                    ),
                ],
                "directory_enumeration_no_progress",
            ),
            (
                [(True, 0, first), (True, 0, first)],
                "directory_duplicate_name",
            ),
        ]
        for pages, expected_reason in scenarios:
            with self.subTest(expected_reason=expected_reason):
                responses = list(pages)

                def read_page(_info_class: int, _size: int):
                    return responses.pop(0)

                with self.assertRaisesRegex(error_type, expected_reason):
                    collect(read_page, buffer_bytes=512)

    def test_collector_validates_buffer_page_and_response_limits_before_success(self) -> None:
        from unittest.mock import patch

        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        collect = getattr(module, "collect_extd_directory_entries", None)
        self.assertTrue(callable(collect), "bounded directory page collector is missing")
        error_type = getattr(module, "WindowsDirectoryProbeError")

        for response in (
            (True, 0, bytearray(512)),
            (True, 0, bytes(513)),
            (1, 0, bytes(512)),
            (False, -1, b""),
            [False, 18, b""],
        ):
            with self.subTest(response=type(response).__name__):
                with self.assertRaises(error_type):
                    collect(lambda _info_class, _size: response, buffer_bytes=512)

        callback_calls = []
        with self.assertRaisesRegex(error_type, "directory_buffer_size_invalid"):
            collect(
                lambda *args: callback_calls.append(args),
                buffer_bytes=64,
            )
        self.assertEqual(callback_calls, [])

        with patch.object(module, "_MAX_DIRECTORY_ENUMERATION_PAGES", 1):
            responses = [
                (
                    True,
                    0,
                    _extd_entry_record(
                        "one.txt",
                        file_id=bytes.fromhex("00000000000000000000000000000001"),
                    ),
                ),
                (False, 18, b""),
            ]

            def read_page(_info_class: int, _size: int):
                return responses.pop(0)

            with self.assertRaisesRegex(error_type, "directory_page_limit"):
                collect(read_page, buffer_bytes=512)


class TestNoReparseOpenReceipt(unittest.TestCase):
    def test_open_receipt_requires_success_without_a_reparse_attribute(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        classify = getattr(module, "classify_no_reparse_open_receipt", None)
        self.assertTrue(callable(classify), "no-reparse receipt classifier is missing")

        status_success = getattr(module, "_STATUS_SUCCESS", 0)
        status_reparse = getattr(module, "_STATUS_REPARSE_POINT_ENCOUNTERED", 0xC000050B)
        reparse_attribute = getattr(module, "_FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        self.assertEqual(classify(status_success, 0x80), "opened")
        self.assertEqual(
            classify(status_success, reparse_attribute), "reparse_opened",
        )
        self.assertEqual(classify(status_reparse, None), "reparse_rejected")
        self.assertEqual(classify(status_success, None), "receipt_incomplete")
        self.assertEqual(classify(0xC0000022, None), "native_open_failed")
        self.assertEqual(classify(True, 0x80), "receipt_incomplete")

    def test_relative_open_rejects_non_child_names_before_native_calls(self) -> None:
        from tests.windows_tree_snapshot_probe import open_relative_without_reparse

        for name in (
            "",
            ".",
            "..",
            "C:\\outside",
            "\\\\server\\share",
            "folder\\..\\outside.txt",
            "file:stream",
            "embedded\x00nul",
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "relative_name_invalid"):
                    open_relative_without_reparse(1, name, directory=False)
        with self.assertRaisesRegex(ValueError, "directory_flag_invalid"):
            open_relative_without_reparse(1, "child", directory=1)  # type: ignore[arg-type]


class TestNamespaceOperationReceipt(unittest.TestCase):
    def test_classifier_only_emits_bounded_success_and_error_categories(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        classify = getattr(module, "classify_namespace_operation_result", None)
        self.assertTrue(
            callable(classify),
            "namespace operation receipt classifier is missing",
        )

        self.assertEqual(classify(True, 0), "allowed")
        self.assertEqual(classify(False, 32), "blocked_sharing_violation")
        self.assertEqual(classify(False, 5), "blocked_access_denied")
        self.assertEqual(classify(False, 2), "blocked_other")
        self.assertEqual(classify(False, 0), "receipt_incomplete")
        self.assertEqual(classify(1, 32), "receipt_incomplete")
        self.assertEqual(classify(False, -1), "receipt_incomplete")


class TestDirectoryListingDrift(unittest.TestCase):
    def test_comparison_fails_closed_on_namespace_or_identity_drift(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        classify = getattr(module, "classify_directory_listing_drift", None)
        self.assertTrue(
            callable(classify),
            "held-directory listing drift classifier is missing",
        )
        entry_type = getattr(module, "ExtendedDirectoryInfoEntry")

        def entry(
            name: str,
            file_id: str,
            *,
            attributes: int = 0x80,
            reparse_tag: int = 0,
        ):
            return entry_type(
                name=name,
                attributes=attributes,
                reparse_tag=reparse_tag,
                file_id=bytes.fromhex(file_id),
            )

        first = entry("first.txt", "00112233445566778899aabbccddeeff")
        second = entry("second.txt", "10112233445566778899aabbccddeeff")
        self.assertEqual(
            classify((first, second), (first, second)), "same_observation",
        )
        undefined_tag = entry(
            "first.txt", "00112233445566778899aabbccddeeff",
            reparse_tag=0xA000000C,
        )
        self.assertEqual(classify((first,), (undefined_tag,)), "same_observation")
        self.assertEqual(
            classify((first,), (first, second)), "namespace_changed",
        )
        self.assertEqual(
            classify((first, second), (second,)), "namespace_changed",
        )
        replaced = entry("first.txt", "20112233445566778899aabbccddeeff")
        self.assertEqual(classify((first,), (replaced,)), "entry_changed")
        changed_attributes = entry(
            "first.txt", "00112233445566778899aabbccddeeff", attributes=0x400,
        )
        self.assertEqual(classify((first,), (changed_attributes,)), "entry_changed")
        changed_tag = entry(
            "first.txt", "00112233445566778899aabbccddeeff",
            attributes=0x400, reparse_tag=0xA000000C,
        )
        self.assertEqual(
            classify((changed_attributes,), (changed_tag,)), "entry_changed",
        )
        self.assertEqual(classify((first, first), (first,)), "receipt_incomplete")
        self.assertEqual(classify((object(),), (object(),)), "receipt_incomplete")
        invalid_id = entry("bad.txt", "00000000000000000000000000000000")
        self.assertEqual(classify((invalid_id,), (invalid_id,)), "receipt_incomplete")
        self.assertEqual(classify(None, (first,)), "receipt_incomplete")


class TestEnumeratedEntryIdentityGate(unittest.TestCase):
    def test_checked_reader_uses_the_exact_enumerated_child_name(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        require_name = getattr(module, "require_enumerated_entry_name", None)
        self.assertTrue(
            callable(require_name),
            "identity-bound read must not substitute another name for the enumerated child",
        )
        entry_type = getattr(module, "ExtendedDirectoryInfoEntry")
        error_type = getattr(module, "WindowsDirectoryProbeError")
        entry = entry_type(
            name="payload.bin", attributes=0x80, reparse_tag=0,
            file_id=bytes.fromhex("00112233445566778899aabbccddeeff"),
        )

        self.assertIsNone(require_name(entry, "payload.bin"))
        for alias in ("Payload.bin", "other.bin", "subdir/payload.bin", "payload.bin:stream"):
            with self.subTest(alias=alias):
                with self.assertRaisesRegex(error_type, "entry_name_changed"):
                    require_name(entry, alias)

    def test_content_read_requires_the_enumerated_object_identity(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        require_identity = getattr(module, "require_enumerated_entry_identity", None)
        self.assertTrue(
            callable(require_identity),
            "an opened child must be checked against its enumerated identity before reading",
        )
        entry_type = getattr(module, "ExtendedDirectoryInfoEntry")
        open_result_type = getattr(module, "NtRelativeOpenResult")
        error_type = getattr(module, "WindowsDirectoryProbeError")
        file_id_a = bytes.fromhex("00112233445566778899aabbccddeeff")
        file_id_b = bytes.fromhex("ffeeddccbbaa99887766554433221100")
        enumerated = entry_type(
            name="stale.bin", attributes=0x80, reparse_tag=0, file_id=file_id_a,
        )
        opened = open_result_type(
            status=0, file_attributes=0x80,
            file_id=file_id_a, volume_serial_number=42,
        )

        self.assertIsNone(require_identity(enumerated, opened, 42))
        with self.assertRaisesRegex(error_type, "entry_identity_changed"):
            require_identity(
                enumerated,
                open_result_type(
                    status=0, file_attributes=0x80,
                    file_id=file_id_b, volume_serial_number=42,
                ),
                42,
            )
        with self.assertRaisesRegex(error_type, "entry_volume_changed"):
            require_identity(
                enumerated,
                open_result_type(
                    status=0, file_attributes=0x80,
                    file_id=file_id_a, volume_serial_number=43,
                ),
                42,
            )
        with self.assertRaisesRegex(error_type, "entry_reparse_point"):
            require_identity(
                entry_type(
                    name="stale.bin", attributes=0x400,
                    reparse_tag=0xA000000C, file_id=file_id_a,
                ),
                opened,
                42,
            )
        with self.assertRaisesRegex(error_type, "entry_type_changed"):
            require_identity(
                enumerated,
                open_result_type(
                    status=0, file_attributes=0x10,
                    file_id=file_id_a, volume_serial_number=42,
                ),
                42,
            )
        with self.assertRaisesRegex(error_type, "entry_open_failed"):
            require_identity(
                enumerated,
                open_result_type(
                    status=0xC0000022, file_attributes=None,
                    file_id=None, volume_serial_number=None,
                ),
                42,
            )

    def test_content_reader_validates_identity_inputs_before_native_calls(self) -> None:
        module = importlib.import_module("tests.windows_tree_snapshot_probe")
        read_checked = getattr(
            module, "read_relative_file_if_identity_matches", None,
        )
        self.assertTrue(
            callable(read_checked),
            "Windows file content must have an identity-bound relative reader",
        )
        error_type = getattr(module, "WindowsDirectoryProbeError")
        entry_type = getattr(module, "ExtendedDirectoryInfoEntry")
        valid_entry = entry_type(
            name="payload.bin", attributes=0x80, reparse_tag=0,
            file_id=bytes.fromhex("00112233445566778899aabbccddeeff"),
        )

        invalid_arguments = (
            {"expected_entry": None, "expected_volume_serial_number": 42,
             "max_bytes": 1},
            {"expected_entry": valid_entry, "expected_volume_serial_number": None,
             "max_bytes": 1},
            {"expected_entry": valid_entry, "expected_volume_serial_number": 42,
             "max_bytes": True},
            {"expected_entry": valid_entry, "expected_volume_serial_number": 42,
             "max_bytes": 0},
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(error_type):
                    read_checked(1, "payload.bin", **arguments)

@unittest.skipUnless(os.name == "nt", "requires native Windows handle semantics")
class TestNativeWindowsDirectoryHandleProbe(unittest.TestCase):
    def test_extd_directory_enumeration_paginates_and_restarts_on_same_handle(self) -> None:
        from ctypes import wintypes

        from tests.windows_tree_snapshot_probe import (
            _FILE_ID_EXTD_DIRECTORY_INFO_CLASS,
            _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
            collect_extd_directory_entries,
            classify_directory_listing_drift,
        )

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        ]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.GetFileInformationByHandleEx.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = wintypes.BOOL

        invalid_handle = ctypes.c_void_p(-1).value
        file_list_directory = 0x00000001
        file_read_attributes = 0x00000080
        file_share_all = 0x00000007
        file_open_existing = 3
        file_flag_backup_semantics = 0x02000000
        file_flag_open_reparse_point = 0x00200000
        buffer_bytes = 512

        with tempfile.TemporaryDirectory(prefix="icode-r3-dir-pages-") as raw:
            root = Path(raw) / "many"
            root.mkdir()
            expected_names = {f"item-{index:03d}.txt" for index in range(96)}
            for name in expected_names:
                (root / name).write_bytes(b"page probe")

            def open_directory(path: Path) -> int:
                handle = kernel.CreateFileW(
                    str(path), file_list_directory | file_read_attributes,
                    file_share_all, None, file_open_existing,
                    file_flag_backup_semantics | file_flag_open_reparse_point, None,
                )
                self.assertNotIn(handle, (None, invalid_handle), "directory open failed")
                return int(handle)

            def collect(handle: int):
                information_classes = []
                page_signals = []

                def read_page(information_class: int, requested_bytes: int):
                    information_classes.append(information_class)
                    buffer = ctypes.create_string_buffer(requested_bytes)
                    ctypes.set_last_error(0)
                    succeeded = bool(
                        kernel.GetFileInformationByHandleEx(
                            handle, information_class, buffer, requested_bytes,
                        )
                    )
                    error = 0 if succeeded else int(ctypes.get_last_error())
                    page_signals.append((information_class, succeeded, error, any(buffer.raw)))
                    return succeeded, error, buffer.raw

                try:
                    entries = collect_extd_directory_entries(
                        read_page, buffer_bytes=buffer_bytes,
                    )
                except Exception as exc:
                    raise AssertionError(
                        f"bounded enumeration failed: {exc}; page_signals={page_signals}"
                    ) from exc
                return entries, information_classes, page_signals

            def assert_known_eof(page_signals) -> None:
                self.assertTrue(page_signals, "enumeration issued no native query")
                _info_class, succeeded, error, has_nonzero_data = page_signals[-1]
                self.assertTrue(
                    (succeeded and error == 0 and not has_nonzero_data)
                    or (not succeeded and error == 18),
                    f"unexpected native enumeration terminal response: {page_signals[-1]}",
                )

            handle = open_directory(root)
            try:
                first_pass, first_classes, first_signals = collect(handle)
                self.assertEqual({entry.name for entry in first_pass}, expected_names)
                assert_known_eof(first_signals)
                self.assertEqual(first_classes[0], _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS)
                self.assertGreater(len(first_classes), 2, "fixture did not cross buffer pages")
                self.assertTrue(
                    all(
                        info_class == _FILE_ID_EXTD_DIRECTORY_INFO_CLASS
                        for info_class in first_classes[1:]
                    ),
                    "continuation pages did not use FileIdExtdDirectoryInfo",
                )

                second_pass, second_classes, second_signals = collect(handle)
                self.assertEqual(second_classes[0], _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS)
                assert_known_eof(second_signals)
                self.assertEqual(
                    classify_directory_listing_drift(first_pass, second_pass),
                    "same_observation",
                )
            finally:
                if not kernel.CloseHandle(handle):
                    raise OSError("failed_native_handle_cleanup")

            empty = root / "empty"
            empty.mkdir()
            empty_handle = open_directory(empty)
            try:
                empty_entries, empty_classes, empty_signals = collect(empty_handle)
                self.assertEqual(empty_entries, ())
                assert_known_eof(empty_signals)
                self.assertEqual(empty_classes[0], _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS)
                self.assertLessEqual(len(empty_classes), 2)
                self.assertTrue(
                    all(
                        info_class == _FILE_ID_EXTD_DIRECTORY_INFO_CLASS
                        for info_class in empty_classes[1:]
                    ),
                    "empty-directory continuation used the wrong information class",
                )
            finally:
                if not kernel.CloseHandle(empty_handle):
                    raise OSError("failed_native_handle_cleanup")

    def test_held_directory_restart_list_detects_add_remove_and_same_name_replacement(self) -> None:
        from ctypes import wintypes

        from tests.windows_tree_snapshot_probe import (
            _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
            classify_directory_listing_drift,
            parse_file_id_extd_directory_info,
        )

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        ]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.GetFileInformationByHandleEx.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = wintypes.BOOL

        invalid_handle = ctypes.c_void_p(-1).value
        file_list_directory = 0x00000001
        file_read_attributes = 0x00000080
        file_share_all = 0x00000007
        file_open_existing = 3
        file_flag_backup_semantics = 0x02000000
        file_flag_open_reparse_point = 0x00200000

        with tempfile.TemporaryDirectory(prefix="icode-r3-dir-drift-") as raw:
            root = Path(raw)
            first = root / "first.txt"
            second = root / "second.txt"
            displaced = root / "displaced.txt"
            first.write_bytes(b"object A")
            second.write_bytes(b"object B")
            handle = kernel.CreateFileW(
                str(root), file_list_directory | file_read_attributes,
                file_share_all, None, file_open_existing,
                file_flag_backup_semantics | file_flag_open_reparse_point, None,
            )
            self.assertNotIn(handle, (None, invalid_handle), "held directory open failed")

            def list_entries():
                buffer = ctypes.create_string_buffer(64 * 1024)
                self.assertTrue(
                    kernel.GetFileInformationByHandleEx(
                        handle,
                        _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
                        buffer,
                        len(buffer),
                    ),
                    "held-directory restart enumeration failed",
                )
                return parse_file_id_extd_directory_info(buffer.raw)

            try:
                baseline = list_entries()
                self.assertEqual(
                    {entry.name for entry in baseline}, {"first.txt", "second.txt"},
                    "the bounded disposable baseline listing was incomplete",
                )
                self.assertEqual(
                    classify_directory_listing_drift(baseline, list_entries()),
                    "same_observation",
                )

                extra = root / "extra.txt"
                extra.write_bytes(b"added")
                added = list_entries()
                self.assertEqual(
                    {entry.name for entry in added},
                    {"first.txt", "second.txt", "extra.txt"},
                )
                self.assertEqual(
                    classify_directory_listing_drift(baseline, added),
                    "namespace_changed",
                )
                extra.unlink()
                removed = list_entries()
                self.assertEqual(
                    classify_directory_listing_drift(baseline, removed),
                    "same_observation",
                )

                # Swap two ordinary objects while preserving the exact names.
                first.rename(displaced)
                second.rename(first)
                displaced.rename(second)
                replaced = list_entries()
                self.assertEqual(
                    {entry.name for entry in replaced}, {"first.txt", "second.txt"},
                )
                self.assertEqual(
                    classify_directory_listing_drift(baseline, replaced),
                    "entry_changed",
                )
            finally:
                if not kernel.CloseHandle(handle):
                    raise OSError("failed_native_handle_cleanup")

    def test_extd_directory_identity_matches_relative_open_and_detects_aba_replacement(self) -> None:
        from ctypes import wintypes

        from tests.windows_tree_snapshot_probe import (
            _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
            _FILE_ID_INFO_CLASS,
            _STATUS_OBJECT_NAME_NOT_FOUND,
            _FileIdInfo,
            WindowsDirectoryProbeError,
            classify_no_reparse_open_receipt,
            open_relative_without_reparse,
            parse_file_id_extd_directory_info,
            read_relative_file_if_identity_matches,
        )

        probe_module = importlib.import_module("tests.windows_tree_snapshot_probe")

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.GetFileInformationByHandleEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
        kernel.DeleteFileW.argtypes = [wintypes.LPCWSTR]
        kernel.DeleteFileW.restype = wintypes.BOOL
        kernel.MoveFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        kernel.MoveFileW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = wintypes.BOOL

        invalid_handle = ctypes.c_void_p(-1).value
        open_existing = 3
        file_list_directory = 0x00000001
        file_read_attributes = 0x00000080
        file_share_all = 0x00000007
        file_flag_backup_semantics = 0x02000000
        file_flag_open_reparse_point = 0x00200000
        file_attribute_reparse_point = 0x00000400

        with tempfile.TemporaryDirectory(prefix="icode-r3-fileid128-") as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            payload = root / "payload.bin"
            empty_payload = root / "empty.bin"
            exact_limit_payload = root / "exact-limit.bin"
            multi_chunk_payload = root / "multi-chunk.bin"
            share_probe_payload = root / "active-reader-share.bin"
            stale_path = root / "stale.bin"
            replacement_source = root / "replacement-source.bin"
            displaced_path = root / "displaced-stale.bin"
            replacement_away_path = root / "replacement-away.bin"
            payload.write_bytes(b"payload for identity probe")
            empty_payload.write_bytes(b"")
            exact_limit_bytes = b"exact-limit-probe"
            exact_limit_payload.write_bytes(exact_limit_bytes)
            multi_chunk_bytes = b"m" * (64 * 1024 + 17)
            multi_chunk_payload.write_bytes(multi_chunk_bytes)
            share_probe_bytes = b"active reader share probe"
            share_probe_payload.write_bytes(share_probe_bytes)
            stale_path.write_bytes(b"stale identity probe")
            replacement_source.write_bytes(b"replacement identity probe")

            root_handle = kernel.CreateFileW(
                str(root),
                file_list_directory | file_read_attributes,
                file_share_all,
                None,
                open_existing,
                file_flag_backup_semantics | file_flag_open_reparse_point,
                None,
            )
            self.assertNotIn(root_handle, (None, invalid_handle), "directory open failed")
            writer_handle = None
            try:
                parent_identity = _FileIdInfo()
                self.assertTrue(
                    kernel.GetFileInformationByHandleEx(
                        root_handle,
                        _FILE_ID_INFO_CLASS,
                        ctypes.byref(parent_identity),
                        ctypes.sizeof(parent_identity),
                    ),
                    "parent identity query failed",
                )
                directory_buffer = ctypes.create_string_buffer(64 * 1024)
                self.assertTrue(
                    kernel.GetFileInformationByHandleEx(
                        root_handle,
                        _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
                        directory_buffer,
                        len(directory_buffer),
                    ),
                    "extended directory enumeration failed",
                )
                entries = parse_file_id_extd_directory_info(directory_buffer.raw)
                payload_entry = next(
                    (item for item in entries if item.name == "payload.bin"), None,
                )
                empty_entry = next(
                    (item for item in entries if item.name == "empty.bin"), None,
                )
                exact_limit_entry = next(
                    (item for item in entries if item.name == "exact-limit.bin"), None,
                )
                multi_chunk_entry = next(
                    (item for item in entries if item.name == "multi-chunk.bin"), None,
                )
                share_probe_entry = next(
                    (item for item in entries if item.name == "active-reader-share.bin"),
                    None,
                )
                stale_entry = next(
                    (item for item in entries if item.name == "stale.bin"), None,
                )
                source_entry = next(
                    (item for item in entries if item.name == "replacement-source.bin"), None,
                )
                self.assertIsNotNone(payload_entry, "normal file was not enumerated")
                self.assertIsNotNone(empty_entry, "empty file was not enumerated")
                self.assertIsNotNone(exact_limit_entry, "boundary file was not enumerated")
                self.assertIsNotNone(multi_chunk_entry, "multi-chunk file was not enumerated")
                self.assertIsNotNone(share_probe_entry, "share probe file was not enumerated")
                self.assertIsNotNone(stale_entry, "stale child was not enumerated")
                self.assertIsNotNone(source_entry, "replacement file was not enumerated")
                self.assertFalse(
                    payload_entry.attributes & file_attribute_reparse_point,
                    "payload was not an ordinary file",
                )
                self.assertFalse(
                    stale_entry.attributes & file_attribute_reparse_point,
                    "stale child was not an ordinary file",
                )
                self.assertFalse(
                    source_entry.attributes & file_attribute_reparse_point,
                    "replacement source was not an ordinary file",
                )
                self.assertEqual(
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "empty.bin",
                        expected_entry=empty_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=1,
                    ),
                    b"",
                    "an empty synchronous file read should terminate at EOF",
                )
                self.assertEqual(
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "exact-limit.bin",
                        expected_entry=exact_limit_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=len(exact_limit_bytes),
                    ),
                    exact_limit_bytes,
                    "a file exactly at its byte limit should succeed",
                )
                with self.assertRaisesRegex(
                    WindowsDirectoryProbeError,
                    "relative_file_too_large",
                ):
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "exact-limit.bin",
                        expected_entry=exact_limit_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=len(exact_limit_bytes) - 1,
                    )
                self.assertEqual(
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "multi-chunk.bin",
                        expected_entry=multi_chunk_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=len(multi_chunk_bytes),
                    ),
                    multi_chunk_bytes,
                    "bounded reading should preserve content across chunk boundaries",
                )

                opened_payload = open_relative_without_reparse(
                    int(root_handle), "payload.bin", directory=False,
                )
                self.assertEqual(
                    classify_no_reparse_open_receipt(
                        opened_payload.status, opened_payload.file_attributes,
                    ),
                    "opened",
                )
                self.assertTrue(
                    opened_payload.volume_serial_number
                    == int(parent_identity.volume_serial_number),
                    "payload volume serial did not match parent",
                )
                self.assertTrue(
                    opened_payload.file_id == payload_entry.file_id,
                    "enumerated and opened payload identities differed",
                )
                self.assertEqual(
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "payload.bin",
                        expected_entry=payload_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=1024,
                    ),
                    b"payload for identity probe",
                    "the bounded reader did not return the enumerated file content",
                )

                original_read = probe_module._read_open_file_contents
                generic_write = 0x40000000
                delete_access = 0x00010000
                error_sharing_violation = 32

                def assert_conflicting_access_is_denied(
                    desired_access: int,
                    operation: str,
                ) -> None:
                    ctypes.set_last_error(0)
                    conflicting_handle = kernel.CreateFileW(
                        str(share_probe_payload),
                        desired_access,
                        file_share_all,
                        None,
                        open_existing,
                        0x00000080,
                        None,
                    )
                    error = ctypes.get_last_error()
                    if conflicting_handle not in (None, invalid_handle):
                        self.assertTrue(
                            kernel.CloseHandle(conflicting_handle),
                            f"unexpected {operation} handle cleanup failed",
                        )
                    self.assertEqual(
                        conflicting_handle,
                        invalid_handle,
                        f"{operation} access succeeded while the reader was active",
                    )
                    self.assertEqual(
                        error,
                        error_sharing_violation,
                        f"{operation} access was not rejected as a sharing violation",
                    )

                def assert_live_reader_blocks_write_and_delete(
                    kernel_api: object,
                    live_handle: ctypes.c_void_p,
                    *,
                    max_bytes: int,
                ) -> bytes:
                    assert_conflicting_access_is_denied(generic_write, "write")
                    assert_conflicting_access_is_denied(delete_access, "DELETE")
                    return original_read(
                        kernel_api,
                        live_handle,
                        max_bytes=max_bytes,
                    )

                with mock.patch.object(
                    probe_module,
                    "_read_open_file_contents",
                    side_effect=assert_live_reader_blocks_write_and_delete,
                ):
                    self.assertEqual(
                        read_relative_file_if_identity_matches(
                            int(root_handle),
                            "active-reader-share.bin",
                            expected_entry=share_probe_entry,
                            expected_volume_serial_number=int(
                                parent_identity.volume_serial_number
                            ),
                            max_bytes=len(share_probe_bytes),
                        ),
                        share_probe_bytes,
                        "the reader should finish after conflicting opens are rejected",
                    )
                writer_handle = kernel.CreateFileW(
                    str(payload),
                    0x40000000,  # GENERIC_WRITE
                    file_share_all,
                    None,
                    open_existing,
                    0x00000080,  # FILE_ATTRIBUTE_NORMAL
                    None,
                )
                self.assertNotIn(
                    writer_handle,
                    (None, invalid_handle),
                    "existing-writer sharing fixture could not be opened",
                )
                with self.assertRaisesRegex(
                    WindowsDirectoryProbeError,
                    "entry_open_failed",
                ):
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "payload.bin",
                        expected_entry=payload_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=1024,
                    )
                self.assertTrue(
                    kernel.CloseHandle(writer_handle),
                    "existing-writer fixture cleanup failed",
                )
                writer_handle = None
                self.assertEqual(
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "payload.bin",
                        expected_entry=payload_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=1024,
                    ),
                    b"payload for identity probe",
                    "closing the conflicting writer did not restore the bounded read",
                )
                with self.assertRaisesRegex(
                    WindowsDirectoryProbeError,
                    "relative_file_too_large",
                ):
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "payload.bin",
                        expected_entry=payload_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=1,
                    )
                self.assertTrue(
                    kernel.MoveFileW(
                        str(payload), str(root / "payload-after-read-error.bin"),
                    ),
                    "oversize read failure left the source handle open",
                )
                self.assertTrue(
                    kernel.MoveFileW(
                        str(root / "payload-after-read-error.bin"), str(payload),
                    ),
                    "oversize read failure cleanup could not restore the fixture",
                )

                self.assertTrue(
                    kernel.MoveFileW(str(stale_path), str(displaced_path)),
                    "stale child displacement failed",
                )
                missing_after_displacement = open_relative_without_reparse(
                    int(root_handle), "stale.bin", directory=False,
                )
                self.assertEqual(
                    classify_no_reparse_open_receipt(
                        missing_after_displacement.status,
                        missing_after_displacement.file_attributes,
                    ),
                    "native_open_failed",
                    "a missing name must not reuse the old enumerated identity",
                )
                self.assertEqual(
                    missing_after_displacement.status,
                    _STATUS_OBJECT_NAME_NOT_FOUND,
                    "the displaced child should fail specifically as a missing name",
                )
                with self.assertRaisesRegex(
                    WindowsDirectoryProbeError,
                    "entry_open_failed",
                ):
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "stale.bin",
                        expected_entry=stale_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=1024,
                    )
                self.assertTrue(
                    kernel.MoveFileW(str(replacement_source), str(stale_path)),
                    "replacement child move failed",
                )
                reopened_replacement = open_relative_without_reparse(
                    int(root_handle), "stale.bin", directory=False,
                )
                self.assertEqual(
                    classify_no_reparse_open_receipt(
                        reopened_replacement.status,
                        reopened_replacement.file_attributes,
                    ),
                    "opened",
                )
                self.assertTrue(
                    reopened_replacement.volume_serial_number
                    == int(parent_identity.volume_serial_number),
                    "replacement volume serial did not match parent",
                )
                self.assertEqual(
                    reopened_replacement.file_id,
                    source_entry.file_id,
                    "reopened path did not resolve to the previously enumerated replacement",
                )
                self.assertTrue(
                    reopened_replacement.file_id != stale_entry.file_id,
                    "reopened replacement retained stale enumerated identity",
                )
                refreshed_directory_buffer = ctypes.create_string_buffer(64 * 1024)
                self.assertTrue(
                    kernel.GetFileInformationByHandleEx(
                        root_handle,
                        _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
                        refreshed_directory_buffer,
                        len(refreshed_directory_buffer),
                    ),
                    "replacement identity re-enumeration failed",
                )
                refreshed_entries = parse_file_id_extd_directory_info(
                    refreshed_directory_buffer.raw,
                )
                replacement_at_stale = next(
                    (item for item in refreshed_entries if item.name == "stale.bin"),
                    None,
                )
                self.assertIsNotNone(
                    replacement_at_stale,
                    "replacement path was not visible after re-enumeration",
                )
                self.assertEqual(
                    replacement_at_stale.file_id,
                    source_entry.file_id,
                    "re-enumerated path identity did not match moved replacement",
                )
                with mock.patch.object(
                    probe_module,
                    "_read_open_file_contents",
                    wraps=probe_module._read_open_file_contents,
                ) as low_level_reader:
                    with self.assertRaisesRegex(
                        WindowsDirectoryProbeError,
                        "entry_identity_changed",
                    ):
                        read_relative_file_if_identity_matches(
                            int(root_handle),
                            "stale.bin",
                            expected_entry=stale_entry,
                            expected_volume_serial_number=int(
                                parent_identity.volume_serial_number
                            ),
                            max_bytes=1024,
                        )
                    low_level_reader.assert_not_called()
                self.assertEqual(
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "stale.bin",
                        expected_entry=replacement_at_stale,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=1024,
                    ),
                    b"replacement identity probe",
                    "the replacement must be readable only under its enumerated identity",
                )

                self.assertTrue(
                    kernel.MoveFileW(str(stale_path), str(replacement_away_path)),
                    "replacement child displacement failed",
                )
                self.assertTrue(
                    kernel.MoveFileW(str(displaced_path), str(stale_path)),
                    "original child restoration failed",
                )
                reopened_original = open_relative_without_reparse(
                    int(root_handle), "stale.bin", directory=False,
                )
                self.assertEqual(
                    classify_no_reparse_open_receipt(
                        reopened_original.status, reopened_original.file_attributes,
                    ),
                    "opened",
                )
                self.assertEqual(
                    reopened_original.file_id,
                    stale_entry.file_id,
                    "restored name did not resolve to the original enumerated object",
                )
                self.assertNotEqual(
                    reopened_original.file_id,
                    reopened_replacement.file_id,
                    "A-to-B-to-A name cycle did not expose distinct file identities",
                )
                self.assertEqual(
                    read_relative_file_if_identity_matches(
                        int(root_handle),
                        "stale.bin",
                        expected_entry=stale_entry,
                        expected_volume_serial_number=int(
                            parent_identity.volume_serial_number
                        ),
                        max_bytes=1024,
                    ),
                    b"stale identity probe",
                    "the original object should be readable again after restoration",
                )
            finally:
                if writer_handle not in (None, invalid_handle):
                    if not kernel.CloseHandle(writer_handle):
                        raise OSError("failed_writer_handle_cleanup")
                if not kernel.CloseHandle(root_handle):
                    raise OSError("failed_native_handle_cleanup")

    def test_directory_file_ids_and_file_handle_share_semantics(self) -> None:
        import ctypes
        from ctypes import wintypes

        from tests.windows_tree_snapshot_probe import parse_file_id_both_directory_info

        class FileTime(ctypes.Structure):
            _fields_ = [
                ("low", wintypes.DWORD),
                ("high", wintypes.DWORD),
            ]

        class ByHandleFileInformation(ctypes.Structure):
            _fields_ = [
                ("attributes", wintypes.DWORD),
                ("creation_time", FileTime),
                ("access_time", FileTime),
                ("write_time", FileTime),
                ("volume_serial", wintypes.DWORD),
                ("size_high", wintypes.DWORD),
                ("size_low", wintypes.DWORD),
                ("links", wintypes.DWORD),
                ("index_high", wintypes.DWORD),
                ("index_low", wintypes.DWORD),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.GetFileInformationByHandleEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
        kernel.GetFileInformationByHandle.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ByHandleFileInformation),
        ]
        kernel.GetFileInformationByHandle.restype = wintypes.BOOL
        kernel.DeleteFileW.argtypes = [wintypes.LPCWSTR]
        kernel.DeleteFileW.restype = wintypes.BOOL
        kernel.MoveFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        kernel.MoveFileW.restype = wintypes.BOOL
        kernel.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        kernel.GetVolumeInformationW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = wintypes.BOOL

        invalid_handle = ctypes.c_void_p(-1).value
        open_existing = 3
        file_share_read = 0x00000001
        file_share_all = 0x00000007
        file_list_directory = 0x00000001
        generic_read = 0x80000000
        generic_write = 0x40000000
        delete_access = 0x00010000
        file_read_attributes = 0x00000080
        file_flag_backup_semantics = 0x02000000
        file_flag_open_reparse_point = 0x00200000
        file_attribute_normal = 0x00000080
        create_new = 1
        file_id_both_directory_restart_info = 0x0B
        error_sharing_violation = 32
        error_access_denied = 5

        with tempfile.TemporaryDirectory(prefix="icode-r3-win-handle-") as temporary:
            root = Path(temporary)
            filesystem_name = ctypes.create_unicode_buffer(64)
            volume_serial = wintypes.DWORD()
            max_component_length = wintypes.DWORD()
            filesystem_flags = wintypes.DWORD()
            self.assertTrue(
                kernel.GetVolumeInformationW(
                    str(root.anchor), None, 0,
                    ctypes.byref(volume_serial),
                    ctypes.byref(max_component_length),
                    ctypes.byref(filesystem_flags),
                    filesystem_name, len(filesystem_name),
                ),
                "filesystem query failed",
            )
            payload = root / "payload.bin"
            added_by_probe = root / "added-by-probe.bin"
            rename_source = root / "rename-source.bin"
            rename_target = root / "rename-target.bin"
            delete_by_probe = root / "delete-by-probe.bin"
            payload.write_bytes(b"bounded file-id probe")
            rename_source.write_bytes(b"rename probe")
            delete_by_probe.write_bytes(b"delete probe")
            (root / "child").mkdir()

            root_handle = kernel.CreateFileW(
                str(root), file_list_directory | file_read_attributes,
                file_share_read, None, open_existing,
                file_flag_backup_semantics | file_flag_open_reparse_point, None,
            )
            self.assertNotIn(root_handle, (None, invalid_handle), "directory open failed")
            payload_handle = None
            unexpected_handle = None
            try:
                directory_buffer = ctypes.create_string_buffer(64 * 1024)
                self.assertTrue(
                    kernel.GetFileInformationByHandleEx(
                        root_handle, file_id_both_directory_restart_info,
                        directory_buffer, len(directory_buffer),
                    ),
                    "directory enumeration failed",
                )
                entries = parse_file_id_both_directory_info(directory_buffer.raw)
                entry = next((item for item in entries if item.name == "payload.bin"), None)
                self.assertIsNotNone(entry, "expected file entry was not enumerated")

                payload_handle = kernel.CreateFileW(
                    str(payload), generic_read | file_read_attributes,
                    file_share_read, None, open_existing, file_flag_open_reparse_point, None,
                )
                self.assertNotIn(payload_handle, (None, invalid_handle), "file open failed")
                file_information = ByHandleFileInformation()
                self.assertTrue(
                    kernel.GetFileInformationByHandle(payload_handle, ctypes.byref(file_information)),
                    "file identity query failed",
                )
                opened_file_id = (
                    (int(file_information.index_high) << 32)
                    | int(file_information.index_low)
                )
                self.assertEqual(entry.file_id, opened_file_id, "directory and handle IDs differ")

                def classify_namespace_result(succeeded: bool) -> str:
                    if succeeded:
                        return "allowed"
                    error = ctypes.get_last_error()
                    if error == error_sharing_violation:
                        return "blocked_sharing_violation"
                    if error == error_access_denied:
                        return "blocked_access_denied"
                    return f"blocked_other_{error}"

                ctypes.set_last_error(0)
                unexpected_handle = kernel.CreateFileW(
                    str(added_by_probe), generic_write, file_share_all, None, create_new,
                    file_attribute_normal, None,
                )
                if unexpected_handle in (None, invalid_handle):
                    directory_create_error = ctypes.get_last_error()
                    if directory_create_error == error_sharing_violation:
                        directory_create_result = "blocked_sharing_violation"
                    elif directory_create_error == error_access_denied:
                        directory_create_result = "blocked_access_denied"
                    else:
                        directory_create_result = f"blocked_other_{directory_create_error}"
                else:
                    directory_create_result = "allowed"
                    kernel.CloseHandle(unexpected_handle)
                    unexpected_handle = None
                    self.assertTrue(
                        kernel.DeleteFileW(str(added_by_probe)),
                        "probe-created child cleanup failed",
                    )

                ctypes.set_last_error(0)
                directory_rename_result = classify_namespace_result(
                    bool(kernel.MoveFileW(str(rename_source), str(rename_target)))
                )
                if directory_rename_result == "allowed":
                    self.assertTrue(
                        kernel.DeleteFileW(str(rename_target)),
                        "renamed probe child cleanup failed",
                    )

                ctypes.set_last_error(0)
                directory_delete_result = classify_namespace_result(
                    bool(kernel.DeleteFileW(str(delete_by_probe)))
                )

                ctypes.set_last_error(0)
                unexpected_handle = kernel.CreateFileW(
                    str(root), delete_access, file_share_all, None, open_existing,
                    file_flag_backup_semantics | file_flag_open_reparse_point, None,
                )
                self.assertEqual(
                    unexpected_handle, invalid_handle,
                    "read-only directory handle unexpectedly allowed DELETE access",
                )
                self.assertEqual(ctypes.get_last_error(), error_sharing_violation)
                unexpected_handle = None

                ctypes.set_last_error(0)
                unexpected_handle = kernel.CreateFileW(
                    str(payload), generic_write, file_share_all, None, open_existing,
                    file_flag_open_reparse_point | file_attribute_normal, None,
                )
                self.assertEqual(
                    unexpected_handle, invalid_handle,
                    "read-only file handle unexpectedly allowed a writer",
                )
                self.assertEqual(ctypes.get_last_error(), error_sharing_violation)
                unexpected_handle = None

                ctypes.set_last_error(0)
                unexpected_handle = kernel.CreateFileW(
                    str(payload), delete_access, file_share_all, None, open_existing,
                    file_flag_open_reparse_point, None,
                )
                self.assertEqual(
                    unexpected_handle, invalid_handle,
                    "read-only file handle unexpectedly allowed DELETE access",
                )
                self.assertEqual(ctypes.get_last_error(), error_sharing_violation)
                unexpected_handle = None
                filesystem_label = filesystem_name.value
                if (
                    not 1 <= len(filesystem_label) <= 16
                    or not filesystem_label.isascii()
                    or not all(char.isalnum() or char in "_-" for char in filesystem_label)
                ):
                    filesystem_label = "other"
                probe_result = (
                    "windows-tree-snapshot-probe "
                    f"filesystem={filesystem_label} "
                    f"directory_create={directory_create_result} "
                    f"directory_rename={directory_rename_result} "
                    f"directory_delete={directory_delete_result} "
                    "file_write=blocked_sharing_violation "
                    "file_delete=blocked_sharing_violation"
                )
                print(probe_result)
                if os.environ.get("GITHUB_ACTIONS") == "true":
                    print(
                        "::notice title=R3 Windows tree snapshot probe::"
                        f"{probe_result}"
                    )
            finally:
                for handle in (unexpected_handle, payload_handle, root_handle):
                    if handle not in (None, invalid_handle):
                        kernel.CloseHandle(handle)

    def test_parent_directory_share_mode_namespace_mutation_matrix(self) -> None:
        from ctypes import wintypes

        from tests.windows_tree_snapshot_probe import (
            classify_namespace_operation_result,
        )

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        kernel.CreateFileW.restype = ctypes.c_void_p
        for name in ("DeleteFileW", "RemoveDirectoryW"):
            function = getattr(kernel, name)
            function.argtypes = [wintypes.LPCWSTR]
            function.restype = wintypes.BOOL
        kernel.MoveFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        kernel.MoveFileW.restype = wintypes.BOOL
        kernel.MoveFileExW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
        ]
        kernel.MoveFileExW.restype = wintypes.BOOL
        kernel.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        kernel.GetVolumeInformationW.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = wintypes.BOOL

        invalid_handle = ctypes.c_void_p(-1).value
        file_list_directory = 0x00000001
        file_read_attributes = 0x00000080
        file_share_read = 0x00000001
        file_share_write = 0x00000002
        file_share_delete = 0x00000004
        file_share_all = file_share_read | file_share_write | file_share_delete
        file_flag_backup_semantics = 0x02000000
        file_flag_open_reparse_point = 0x00200000
        create_new = 1
        open_existing = 3
        file_attribute_normal = 0x00000080
        movefile_replace_existing = 0x00000001

        with tempfile.TemporaryDirectory(prefix="icode-r3-win-share-matrix-") as raw:
            temporary_root = Path(raw)
            filesystem_name = ctypes.create_unicode_buffer(64)
            volume_serial = wintypes.DWORD()
            max_component_length = wintypes.DWORD()
            filesystem_flags = wintypes.DWORD()
            self.assertTrue(
                kernel.GetVolumeInformationW(
                    str(temporary_root.anchor),
                    None,
                    0,
                    ctypes.byref(volume_serial),
                    ctypes.byref(max_component_length),
                    ctypes.byref(filesystem_flags),
                    filesystem_name,
                    len(filesystem_name),
                ),
                "filesystem query failed",
            )
            filesystem_label = filesystem_name.value
            if (
                not 1 <= len(filesystem_label) <= 16
                or not filesystem_label.isascii()
                or not all(char.isalnum() or char in "_-" for char in filesystem_label)
            ):
                filesystem_label = "other"

            observations: list[str] = []
            share_modes = (
                ("baseline", None),
                ("read", file_share_read),
                ("read_write", file_share_read | file_share_write),
                ("all", file_share_all),
            )
            for mode_name, share_mode in share_modes:
                root = temporary_root / mode_name
                root.mkdir()
                outside = temporary_root / f"{mode_name}-outside"
                outside.mkdir()
                delete_path = root / "delete.bin"
                rename_source = root / "rename-source.bin"
                replace_source = root / "replace-source.bin"
                replace_target = root / "replace-target.bin"
                reparse_slot = root / "reparse-slot"
                delete_path.write_bytes(b"delete")
                rename_source.write_bytes(b"rename")
                replace_source.write_bytes(b"new")
                replace_target.write_bytes(b"old")
                reparse_slot.mkdir()

                parent_handle = None
                junction_created = False
                reparse_create_attempted = False
                try:
                    if share_mode is not None:
                        parent_handle = kernel.CreateFileW(
                            str(root),
                            file_list_directory | file_read_attributes,
                            share_mode,
                            None,
                            open_existing,
                            file_flag_backup_semantics | file_flag_open_reparse_point,
                            None,
                        )
                        self.assertNotIn(
                            parent_handle,
                            (None, invalid_handle),
                            f"could not hold the {mode_name} parent-directory handle",
                        )

                    def label_boolean_result(succeeded: bool) -> str:
                        winerror = 0 if succeeded else ctypes.get_last_error()
                        return classify_namespace_operation_result(succeeded, winerror)

                    ctypes.set_last_error(0)
                    create_handle = kernel.CreateFileW(
                        str(root / "create.bin"),
                        0x40000000,
                        file_share_all,
                        None,
                        create_new,
                        file_attribute_normal,
                        None,
                    )
                    create_succeeded = create_handle not in (None, invalid_handle)
                    create_winerror = 0 if create_succeeded else ctypes.get_last_error()
                    create_result = classify_namespace_operation_result(
                        create_succeeded,
                        create_winerror,
                    )
                    if create_succeeded:
                        self.assertTrue(kernel.CloseHandle(create_handle))

                    ctypes.set_last_error(0)
                    delete_result = label_boolean_result(
                        bool(kernel.DeleteFileW(str(delete_path))),
                    )

                    ctypes.set_last_error(0)
                    rename_result = label_boolean_result(
                        bool(kernel.MoveFileW(
                            str(rename_source),
                            str(root / "rename-target.bin"),
                        )),
                    )

                    ctypes.set_last_error(0)
                    replace_result = label_boolean_result(
                        bool(kernel.MoveFileExW(
                            str(replace_source),
                            str(replace_target),
                            movefile_replace_existing,
                        )),
                    )
                    if replace_result == "allowed":
                        self.assertEqual(replace_target.read_bytes(), b"new")

                    ctypes.set_last_error(0)
                    reparse_remove_result = label_boolean_result(
                        bool(kernel.RemoveDirectoryW(str(reparse_slot))),
                    )
                    reparse_create_result = "not_attempted"
                    if reparse_remove_result == "allowed":
                        reparse_create_attempted = True
                        junction = subprocess.run(
                            [
                                "cmd.exe",
                                "/d",
                                "/c",
                                "mklink",
                                "/J",
                                str(reparse_slot),
                                str(outside),
                            ],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        junction_created = junction.returncode == 0
                        reparse_create_result = (
                            "allowed" if junction_created else "blocked_or_failed"
                        )

                    results = (
                        create_result,
                        delete_result,
                        rename_result,
                        replace_result,
                        reparse_remove_result,
                        reparse_create_result,
                    )
                    self.assertNotIn("receipt_incomplete", results)
                    if mode_name == "baseline":
                        self.assertEqual(
                            results,
                            ("allowed",) * len(results),
                            "uncontended namespace mutation baseline failed",
                        )
                    observations.append(
                        f"mode={mode_name} "
                        f"create={create_result} "
                        f"delete={delete_result} "
                        f"rename={rename_result} "
                        f"replace={replace_result} "
                        f"reparse_remove={reparse_remove_result} "
                        f"reparse_create={reparse_create_result}"
                    )
                finally:
                    try:
                        if parent_handle not in (None, invalid_handle):
                            self.assertTrue(
                                kernel.CloseHandle(parent_handle),
                                "parent-directory handle cleanup failed",
                            )
                    finally:
                        if reparse_create_attempted:
                            ctypes.set_last_error(0)
                            cleanup_succeeded = bool(
                                kernel.RemoveDirectoryW(str(reparse_slot)),
                            )
                            cleanup_error = ctypes.get_last_error()
                            if junction_created:
                                self.assertTrue(
                                    cleanup_succeeded,
                                    "junction cleanup failed",
                                )
                            elif not cleanup_succeeded:
                                self.assertIn(
                                    cleanup_error,
                                    (2, 3),  # ERROR_FILE_NOT_FOUND / ERROR_PATH_NOT_FOUND
                                    "failed reparse create left an unexpected filesystem object",
                                )

            probe_result = (
                "windows-tree-share-matrix "
                f"filesystem={filesystem_label} "
                + " ".join(observations)
            )
            print(probe_result)
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(
                    "::notice title=R3 Windows namespace share-mode matrix::"
                    f"{probe_result}"
                )

    def test_relative_native_open_rejects_reparse_and_replaced_child(self) -> None:
        from ctypes import wintypes

        from tests.windows_tree_snapshot_probe import (
            classify_no_reparse_open_receipt,
            open_relative_without_reparse,
        )

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = wintypes.BOOL

        invalid_handle = ctypes.c_void_p(-1).value
        file_list_directory = 0x00000001
        file_read_attributes = 0x00000080
        file_share_all = 0x00000007
        open_existing = 3
        file_flag_backup_semantics = 0x02000000
        file_flag_open_reparse_point = 0x00200000
        reparse_attribute = 0x00000400

        with tempfile.TemporaryDirectory(prefix="icode-r3-relative-open-") as temporary:
            root = Path(temporary) / "workspace"
            outside = Path(temporary) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "plain.txt").write_text("disposable probe", encoding="utf-8")
            (root / "child").mkdir()
            (outside / "outside.txt").write_text("not opened", encoding="utf-8")
            (root / "replace-me").mkdir()

            def create_junction(junction: Path, target: Path) -> None:
                result = subprocess.run(
                    ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    "could not create native test junction",
                )

            root_handle = kernel.CreateFileW(
                str(root),
                file_list_directory | file_read_attributes,
                file_share_all,
                None,
                open_existing,
                file_flag_backup_semantics | file_flag_open_reparse_point,
                None,
            )
            self.assertNotIn(root_handle, (None, invalid_handle), "directory open failed")
            try:
                normal_file = open_relative_without_reparse(
                    int(root_handle), "plain.txt", directory=False,
                )
                self.assertEqual(
                    classify_no_reparse_open_receipt(
                        normal_file.status, normal_file.file_attributes,
                    ),
                    "opened",
                )
                self.assertIsNotNone(normal_file.file_id)

                normal_directory = open_relative_without_reparse(
                    int(root_handle), "child", directory=True,
                )
                self.assertEqual(
                    classify_no_reparse_open_receipt(
                        normal_directory.status, normal_directory.file_attributes,
                    ),
                    "opened",
                )
                self.assertIsNotNone(normal_directory.file_id)

                original_child = open_relative_without_reparse(
                    int(root_handle), "replace-me", directory=True,
                )
                self.assertEqual(
                    classify_no_reparse_open_receipt(
                        original_child.status, original_child.file_attributes,
                    ),
                    "opened",
                )
                self.assertIsNotNone(original_child.file_id)
                (root / "replace-me").rmdir()
                create_junction(root / "replace-me", outside)

                replaced_child = open_relative_without_reparse(
                    int(root_handle), "replace-me", directory=True,
                )
                replaced_classification = classify_no_reparse_open_receipt(
                    replaced_child.status, replaced_child.file_attributes,
                )
                self.assertIn(
                    replaced_classification,
                    ("reparse_rejected", "reparse_opened"),
                    "a child replaced by a junction must not be treated as a normal directory",
                )
                if replaced_classification == "reparse_opened":
                    self.assertTrue(replaced_child.file_attributes & reparse_attribute)
                    self.assertNotEqual(replaced_child.file_id, original_child.file_id)

                create_junction(root / "junction", outside)
                traversed_junction = open_relative_without_reparse(
                    int(root_handle), "junction\\outside.txt", directory=False,
                )
                self.assertEqual(
                    classify_no_reparse_open_receipt(
                        traversed_junction.status,
                        traversed_junction.file_attributes,
                    ),
                    "reparse_rejected",
                    (
                        "an ancestor junction must be rejected before opening its target; "
                        f"status=0x{traversed_junction.status:08x}"
                    ),
                )
            finally:
                if not kernel.CloseHandle(root_handle):
                    raise OSError("failed_native_handle_cleanup")


if __name__ == "__main__":
    unittest.main()
