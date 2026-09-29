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


@unittest.skipUnless(os.name == "nt", "requires native Windows handle semantics")
class TestNativeWindowsDirectoryHandleProbe(unittest.TestCase):
    def test_extd_directory_identity_matches_relative_open_and_detects_replacement(self) -> None:
        from ctypes import wintypes

        from tests.windows_tree_snapshot_probe import (
            _FILE_ID_EXTD_DIRECTORY_RESTART_INFO_CLASS,
            _FILE_ID_INFO_CLASS,
            _FileIdInfo,
            classify_no_reparse_open_receipt,
            open_relative_without_reparse,
            parse_file_id_extd_directory_info,
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
            stale_path = root / "stale.bin"
            replacement_source = root / "replacement-source.bin"
            payload.write_bytes(b"payload for identity probe")
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
                stale_entry = next(
                    (item for item in entries if item.name == "stale.bin"), None,
                )
                source_entry = next(
                    (item for item in entries if item.name == "replacement-source.bin"), None,
                )
                self.assertIsNotNone(payload_entry, "normal file was not enumerated")
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

                self.assertTrue(kernel.DeleteFileW(str(stale_path)), "stale child removal failed")
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
            finally:
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
