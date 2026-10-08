"""Actual-byte contracts for the CI-only PE header and RVA foundation."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
import hashlib
import importlib
import importlib.util
import io
import struct
import unittest


LIMIT = 8 * 1024 * 1024
DEFAULT = object()


def pe_bytes(*, arch="x64", sections=None, directories=(), pe_offset=0x80,
             size_of_image=0x4000, size_of_headers=None, file_size=None):
    """Build real DOS/COFF/PE32+ headers and a complete section table."""
    count = 1 if sections is None else len(sections)
    optional_size = 112 + 8 * len(directories)
    optional = pe_offset + 24
    table = optional + optional_size
    headers = ((table + 40 * count + 0xFF) // 0x100) * 0x100
    if size_of_headers is not None:
        headers = size_of_headers
    if sections is None:
        sections = ((0x1000, 0x100, 0x100, headers),)
    required = max(table + 40 * count, headers,
                   *(start + raw for _, _, raw, start in sections if raw))
    body = bytearray(required if file_size is None else file_size)
    body[:2] = b"MZ"
    struct.pack_into("<I", body, 0x3C, pe_offset)
    body[pe_offset:pe_offset + 4] = b"PE\0\0"
    struct.pack_into("<HH", body, pe_offset + 4,
                     {"x64": 0x8664, "arm64": 0xAA64}[arch], count)
    struct.pack_into("<H", body, pe_offset + 20, optional_size)
    struct.pack_into("<H", body, optional, 0x20B)
    struct.pack_into("<II", body, optional + 56, size_of_image, headers)
    struct.pack_into("<I", body, optional + 108, len(directories))
    for index, pair in enumerate(directories):
        struct.pack_into("<II", body, optional + 112 + index * 8, *pair)
    for index, (va, virtual, raw, start) in enumerate(sections):
        struct.pack_into("<IIII", body, table + index * 40 + 8,
                         virtual, va, raw, start)
    return bytes(body)


def changed(image, offset, fmt, *values):
    body = bytearray(image)
    struct.pack_into(fmt, body, offset, *values)
    return bytes(body)


class TestWindowsPeReader(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("scripts.windows_pe_reader")
        self.assertIsNotNone(spec, "CI-only PE reader interface is missing")
        module = importlib.import_module("scripts.windows_pe_reader")
        self.PeImage = getattr(module, "PeImage", None)
        self.PeFormatError = getattr(module, "PeFormatError", None)
        self.assertTrue(callable(self.PeImage), "PeImage interface is missing")
        self.assertTrue(isinstance(self.PeFormatError, type))
        self.assertTrue(issubclass(self.PeFormatError, ValueError))

    def reject(self, reason, image=DEFAULT, *, arch="x64"):
        if image is DEFAULT:
            image = pe_bytes()
        with self.assertRaises(self.PeFormatError) as caught:
            self.PeImage(image, expected_arch=arch)
        self.assertIs(type(caught.exception), self.PeFormatError)
        self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(str(caught.exception), reason)

    def read_reject(self, reader, reason, rva, size):
        for method in (reader.rva_to_offset, reader.read_rva):
            with self.subTest(method=method.__name__, rva=rva, size=size):
                with self.assertRaises(self.PeFormatError) as caught:
                    method(rva, size)
                self.assertIs(type(caught.exception), self.PeFormatError)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(str(caught.exception), reason)

    def test_minimal_both_architectures_and_empty_directories(self):
        for arch in ("x64", "arm64"):
            with self.subTest(arch=arch):
                image = pe_bytes(arch=arch)
                reader = self.PeImage(image, expected_arch=arch)
                self.assertEqual(reader.architecture, arch)
                self.assertEqual(reader.data_directories, ())
                self.assertIs(reader._image, image)

    def test_bad_arch_precedes_empty_budget(self):
        self.reject("invalid_input", b"", arch="amd64")

    def test_directory_limit_precedes_array_truncation(self):
        self.reject("unsupported_directory_count", changed(pe_bytes(), 0x98 + 108, "<I", 17))

    def test_exact_input_types_and_arch_values(self):
        class BytesSubclass(bytes):
            pass

        class StrSubclass(str):
            pass

        image = pe_bytes()
        for value in (None, True, object(), bytearray(image), memoryview(image),
                      BytesSubclass(image), "MZ", 7):
            with self.subTest(image_type=type(value)):
                self.reject("invalid_input", value)
        for value in (True, 7, None, "X64", "amd64", "", StrSubclass("x64")):
            with self.subTest(arch=value):
                self.reject("invalid_input", arch=value)

    def test_empty_and_image_budget_exact_boundary(self):
        self.reject("image_limit", b"")
        image = pe_bytes(file_size=LIMIT)
        self.assertIs(self.PeImage(image, expected_arch="x64")._image, image)
        self.reject("image_limit", image + b"\0")

    def test_dos_signature_and_truncation(self):
        self.reject("truncated_headers", b"MZ" + bytes(61))
        self.reject("invalid_signature", changed(pe_bytes(), 0, "<H", 0))

    def test_pe_offset_bounds_and_complete_coff(self):
        self.assertEqual(self.PeImage(pe_bytes(pe_offset=64), expected_arch="x64").architecture, "x64")
        image = pe_bytes()
        self.reject("invalid_header_range", changed(image, 0x3C, "<I", 63))
        for offset in (len(image), len(image) - 23, 0xFFFFFFFF):
            with self.subTest(offset=offset):
                self.reject("truncated_headers", changed(image, 0x3C, "<I", offset))

    def test_pe_signature(self):
        self.reject("invalid_signature", changed(pe_bytes(), 0x80, "<I", 0))

    def test_machine_unsupported_and_expected_mismatch(self):
        self.reject("architecture_mismatch", changed(pe_bytes(), 0x84, "<H", 0x14C))
        self.reject("architecture_mismatch", pe_bytes(arch="arm64"))
        self.reject("architecture_mismatch", arch="arm64")

    def test_section_count_policy(self):
        for count in (0, 97):
            with self.subTest(count=count):
                self.reject("unsupported_section_count", changed(pe_bytes(), 0x86, "<H", count))

    def test_optional_header_length_and_magic(self):
        for length in (111, 0xFFFF):
            with self.subTest(length=length):
                self.reject("truncated_headers", changed(pe_bytes(), 0x94, "<H", length))
        self.reject("invalid_signature", changed(pe_bytes(), 0x98, "<H", 0x10B))

    def test_directory_array_must_fit_declared_optional_header(self):
        self.reject("truncated_headers", changed(pe_bytes(), 0x98 + 108, "<I", 1))

    def test_all_declared_directory_pairs_preserved_only_as_metadata(self):
        pairs = ((0, 0), (0xFFFFFFFF, 9), (0, 8), (9, 0)) + tuple((0x9000 + n, n) for n in range(12))
        reader = self.PeImage(pe_bytes(directories=pairs), expected_arch="x64")
        self.assertIs(type(reader.data_directories), tuple)
        self.assertEqual(reader.data_directories, pairs)
        one = self.PeImage(pe_bytes(directories=((0x9000, 0),)), expected_arch="x64")
        self.assertEqual(one.data_directories, ((0x9000, 0),))
        self.assertFalse(hasattr(reader, "parse_complete"))

    def test_certificate_directory_file_offset_is_not_validated_as_rva(self):
        pairs = ((0, 0),) * 4 + ((0x800, 16),)
        image = pe_bytes(directories=pairs, file_size=0x810)
        reader = self.PeImage(image, expected_arch="x64")
        self.assertEqual(reader.data_directories[4], (0x800, 16))
        self.read_reject(reader, "rva_not_file_backed", 0x800, 16)

    def test_section_table_truncation(self):
        table_end = 0x98 + 112 + 40
        self.reject("truncated_headers", pe_bytes()[:table_end - 1])

    def test_header_ranges_and_zero_image_size(self):
        image = pe_bytes()
        table_end = 0x98 + 112 + 40
        for headers in (0, table_end - 1, len(image) + 1, 0x4001):
            with self.subTest(headers=headers):
                self.reject("invalid_header_range", changed(image, 0x98 + 60, "<I", headers))
        for size in (0, 0x1FF):
            with self.subTest(size=size):
                self.reject("invalid_header_range", changed(image, 0x98 + 56, "<I", size))
        # Isolate the SizeOfImage bound from the file-size bound.
        self.reject("invalid_header_range", pe_bytes(file_size=0x5000, size_of_headers=0x4001))

    def test_header_and_section_reads_at_exact_ends(self):
        image = pe_bytes(size_of_image=0x1100)
        reader = self.PeImage(image, expected_arch="x64")
        for rva, size, offset in ((0, 0x200, 0), (0x1000, 0x100, 0x200),
                                  (0x1FF, 1, 0x1FF), (0x10FF, 1, 0x2FF)):
            with self.subTest(rva=rva, size=size):
                self.assertEqual(reader.rva_to_offset(rva, size), offset)
                self.assertEqual(reader.read_rva(rva, size), image[offset:offset + size])

    def test_unordered_adjacent_sections_and_independent_reads(self):
        sections = ((0x1100, 0x100, 0x100, 0x300), (0x1000, 0x100, 0x100, 0x200))
        body = bytearray(pe_bytes(sections=sections))
        body[0x300:0x400] = b"B" * 0x100
        body[0x200:0x300] = b"A" * 0x100
        reader = self.PeImage(bytes(body), expected_arch="x64")
        for rva, offset, marker in ((0x1100, 0x300, b"B"), (0x1000, 0x200, b"A")):
            with self.subTest(rva=rva):
                self.assertEqual(reader.rva_to_offset(rva, 0x100), offset)
                self.assertEqual(reader.read_rva(rva, 0x100), marker * 0x100)
        self.read_reject(reader, "rva_not_file_backed", 0x10FF, 2)

    def test_section_count_96_and_search_bound(self):
        sections = tuple((0x1000 + n * 0x100, 0x100, 0x100, 0x2000 + n * 0x100) for n in range(96))
        # A 96-entry table fits below RVA 0x1000 only with the legal DOS-end PE
        # offset here; the default 0x80 would round headers up to 0x1100.
        image = pe_bytes(sections=sections, size_of_image=0x7000, pe_offset=64)
        reader = self.PeImage(image, expected_arch="x64")
        self.assertEqual(len(reader._sections), 96)
        self.assertLessEqual(len(reader._regions), 97)
        self.assertEqual(reader.rva_to_offset(0x6FFF, 1), 0x7FFF)
        self.assertEqual(reader.read_rva(0x6FFF, 1), image[0x7FFF:0x8000])

    def test_zero_virtual_size_uses_raw_extent(self):
        image = pe_bytes(sections=((0x1000, 0, 0x100, 0x200),))
        reader = self.PeImage(image, expected_arch="x64")
        self.assertEqual(reader.read_rva(0x1000, 0x100), image[0x200:0x300])
        self.read_reject(reader, "rva_not_file_backed", 0x1100, 1)

    def test_zero_raw_size_ignores_pointer_and_never_zero_fills(self):
        reader = self.PeImage(pe_bytes(sections=((0x1000, 0x100, 0, 0xFFFFFFFF),)), expected_arch="x64")
        self.read_reject(reader, "rva_not_file_backed", 0x1000, 1)

    def test_both_section_sizes_zero_provide_no_mapping(self):
        sections = ((0xFFFFFFFF, 0, 0, 0xFFFFFFFF),)
        reader = self.PeImage(pe_bytes(sections=sections), expected_arch="x64")
        self.assertEqual(reader._sections, sections)
        self.assertEqual(reader._regions, ((0, 0x200, 0),))
        self.read_reject(reader, "invalid_rva_range", 0xFFFFFFFF, 1)

    def test_zero_fill_and_raw_padding_not_file_backed(self):
        for virtual, backed in ((0x200, 0x100), (0x80, 0x80)):
            with self.subTest(virtual=virtual):
                image = pe_bytes(sections=((0x1000, virtual, 0x100, 0x200),))
                reader = self.PeImage(image, expected_arch="x64")
                self.assertEqual(reader.read_rva(0x1000, backed), image[0x200:0x200 + backed])
                self.read_reject(reader, "rva_not_file_backed", 0x1000 + backed, 1)

    def test_raw_and_virtual_section_ranges(self):
        image = pe_bytes()
        section = 0x98 + 112 + 8
        for offset, value in ((12, len(image)), (12, 0xFFFFFFFF), (8, 0xFFFFFFFF),
                              (4, 0x4000), (4, 0xFFFFFFF0), (0, 0xFFFFFFFF)):
            with self.subTest(offset=offset, value=value):
                self.reject("invalid_section_range", changed(image, section + offset, "<I", value))

    def test_header_raw_and_virtual_overlaps(self):
        for sections in (((0x1000, 0x100, 0x100, 0x100),),
                         ((0x100, 0x100, 0x100, 0x200),)):
            with self.subTest(sections=sections):
                self.reject("overlapping_sections", pe_bytes(sections=sections))

    def test_full_raw_padding_and_virtual_zero_fill_overlap(self):
        for sections in (((0x1000, 0x80, 0x200, 0x200), (0x2000, 0x100, 0x100, 0x300)),
                         ((0x1000, 0x200, 0x80, 0x200), (0x1100, 0x100, 0x100, 0x300))):
            with self.subTest(sections=sections):
                self.reject("overlapping_sections", pe_bytes(sections=sections))

    def test_section_ranges_precede_overlap_independent_of_order(self):
        overlap = ((0x1000, 0x100, 0x100, 0x200), (0x1080, 0x100, 0x100, 0x300))
        invalid = (0x2000, 0x100, 0x100, 0x400)
        # The fixture has complete headers/table; only the chosen raw pointer is invalid.
        for sections, index in ((overlap + (invalid,), 2), ((invalid,) + overlap, 0)):
            with self.subTest(index=index):
                image = pe_bytes(sections=sections)
                table = 0x98 + 112
                image = changed(image, table + index * 40 + 20, "<I", len(image))
                self.reject("invalid_section_range", image)

    def test_read_argument_types_sign_and_budget(self):
        class IntSubclass(int):
            pass

        reader = self.PeImage(pe_bytes(), expected_arch="x64")
        for rva, size in ((True, 1), (0, True), (IntSubclass(0), 1), (0, IntSubclass(1)),
                          (0.0, 1), (0, 1.0), (-1, 1), (0, 0), (0, -1),
                          (0x100000000, 1), (0xFFFFFFFF, 2), (0, LIMIT + 1), (0x4000, 1)):
            with self.subTest(rva=rva, size=size):
                self.read_reject(reader, "invalid_rva_range", rva, size)

    def test_exact_read_budget_supported_when_single_header_region(self):
        image = pe_bytes(sections=((0, 0, 0, 0),), size_of_headers=LIMIT,
                         size_of_image=LIMIT, file_size=LIMIT)
        reader = self.PeImage(image, expected_arch="x64")
        self.assertEqual(reader.rva_to_offset(0, LIMIT), 0)
        self.assertEqual(reader.read_rva(0, LIMIT), image)

    def test_gap_overlay_and_header_crossing_are_not_fallbacks(self):
        reader = self.PeImage(pe_bytes(file_size=0x2000), expected_arch="x64")
        for rva, size in ((0x300, 1), (0x1800, 1), (0x1FF, 2), (0x10FF, 2)):
            with self.subTest(rva=rva):
                self.read_reject(reader, "rva_not_file_backed", rva, size)
        adjacent = self.PeImage(pe_bytes(sections=((0x200, 0x100, 0x100, 0x200),)), expected_arch="x64")
        self.assertEqual(adjacent.rva_to_offset(0x1FF, 1), 0x1FF)
        self.assertEqual(adjacent.rva_to_offset(0x200, 1), 0x200)
        self.assertEqual(len(adjacent.read_rva(0x1FF, 1)), 1)
        self.assertEqual(len(adjacent.read_rva(0x200, 1)), 1)
        self.read_reject(adjacent, "rva_not_file_backed", 0x1FF, 2)

    def test_read_methods_have_identical_rejections(self):
        reader = self.PeImage(pe_bytes(), expected_arch="x64")
        self.read_reject(reader, "invalid_rva_range", -1, 1)
        self.read_reject(reader, "rva_not_file_backed", 0x300, 1)

    def test_immutable_metadata_original_bytes_and_quiet_repr(self):
        marker = b"PRIVATE_PE_BODY_MARKER"
        body = bytearray(pe_bytes(directories=((0x9000, 0),)))
        body[0x200:0x200 + len(marker)] = marker
        image = bytes(body)
        digest = hashlib.sha256(image).digest()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            reader = self.PeImage(image, expected_arch="x64")
            self.assertEqual(reader.read_rva(0x1000, len(marker)), marker)
            representation = repr(reader)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn(marker.decode(), representation)
        self.assertIs(reader._image, image)
        self.assertEqual(hashlib.sha256(image).digest(), digest)
        for value in (reader._sections, reader._regions, reader.data_directories):
            self.assertIs(type(value), tuple)
            self.assertTrue(all(type(item) is tuple for item in value))
        for name in ("_image", "architecture", "data_directories", "_size_of_image", "_regions", "_sections"):
            with self.subTest(field=name):
                with self.assertRaises(FrozenInstanceError):
                    setattr(reader, name, None)
        for name in ("parse_complete", "runtime_load_verified", "source_launch_verified"):
            self.assertFalse(hasattr(reader, name))

    def test_old_minimal_machine_contract_remains_distinct(self):
        from icode.native_helper import windows_pe_architecture

        body = bytearray(70)
        body[:2] = b"MZ"
        struct.pack_into("<I", body, 0x3C, 64)
        body[64:68] = b"PE\0\0"
        struct.pack_into("<H", body, 68, 0x8664)
        image = bytes(body)
        self.assertEqual(windows_pe_architecture(image), "x64")
        self.reject("truncated_headers", image)
        self.assertEqual(windows_pe_architecture(image), "x64")
