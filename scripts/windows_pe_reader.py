"""CI-only bounded PE32+ headers and complete file-backed RVA reads.

Construction validates this narrow structural subset only. Directory pairs are
metadata; success does not certify directory contents or a loadable executable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct


_IMAGE_LIMIT = 8 * 1024 * 1024
_RVA_LIMIT = 1 << 32
_DOS_SIZE = 64
_COFF_SIZE = 20
_OPTIONAL_BASE_SIZE = 112
_SECTION_SIZE = 40
_SECTION_LIMIT = 96
_DIRECTORY_LIMIT = 16
_MACHINES = {0x8664: "x64", 0xAA64: "arm64"}
_REASONS = frozenset({
    "invalid_input", "image_limit", "truncated_headers", "invalid_signature",
    "architecture_mismatch", "unsupported_section_count",
    "unsupported_directory_count", "invalid_header_range",
    "invalid_section_range", "overlapping_sections", "invalid_rva_range",
    "rva_not_file_backed",
})


class PeFormatError(ValueError):
    """A closed, payload-free rejection reason."""

    def __init__(self, reason: str):
        if type(reason) is not str or reason not in _REASONS:
            raise ValueError("invalid_input")
        self.reason = reason
        super().__init__(reason)


def _require_range(image: bytes, start: int, size: int) -> None:
    if start < 0 or size < 0 or start + size > len(image):
        raise PeFormatError("truncated_headers")


def _unpack(image: bytes, start: int, fmt: str) -> tuple[int, ...]:
    # Every struct read has an explicit file-range check, even after a containing
    # header has already been checked. Defined truncations never leak struct.error.
    _require_range(image, start, struct.calcsize(fmt))
    return struct.unpack_from(fmt, image, start)


def _reject_overlaps(spans: list[tuple[int, int]]) -> None:
    previous_end = 0
    for start, end in sorted(spans):
        if start < previous_end:
            raise PeFormatError("overlapping_sections")
        previous_end = end


@dataclass(frozen=True, slots=True, init=False)
class PeImage:
    """Immutable original bytes plus bounded structural metadata."""

    _image: bytes = field(repr=False)
    architecture: str
    data_directories: tuple[tuple[int, int], ...]
    _size_of_image: int
    _sections: tuple[tuple[int, int, int, int], ...]
    _regions: tuple[tuple[int, int, int], ...]

    def __init__(self, image: bytes, *, expected_arch: str):
        if (type(image) is not bytes or type(expected_arch) is not str
                or expected_arch not in ("x64", "arm64")):
            raise PeFormatError("invalid_input")
        if not image or len(image) > _IMAGE_LIMIT:
            raise PeFormatError("image_limit")
        _require_range(image, 0, _DOS_SIZE)
        if image[:2] != b"MZ":
            raise PeFormatError("invalid_signature")
        pe_offset, = _unpack(image, 0x3C, "<I")
        if pe_offset < _DOS_SIZE:
            raise PeFormatError("invalid_header_range")
        _require_range(image, pe_offset, 4 + _COFF_SIZE)
        if image[pe_offset:pe_offset + 4] != b"PE\0\0":
            raise PeFormatError("invalid_signature")
        coff = pe_offset + 4
        machine, section_count = _unpack(image, coff, "<HH")
        architecture = _MACHINES.get(machine)
        if architecture != expected_arch:
            raise PeFormatError("architecture_mismatch")
        if not 1 <= section_count <= _SECTION_LIMIT:
            raise PeFormatError("unsupported_section_count")
        optional_size, = _unpack(image, coff + 16, "<H")
        optional = coff + _COFF_SIZE
        if optional_size < _OPTIONAL_BASE_SIZE:
            raise PeFormatError("truncated_headers")
        _require_range(image, optional, optional_size)
        magic, = _unpack(image, optional, "<H")
        if magic != 0x20B:
            raise PeFormatError("invalid_signature")
        directory_count, = _unpack(image, optional + 108, "<I")
        if directory_count > _DIRECTORY_LIMIT:
            raise PeFormatError("unsupported_directory_count")
        if _OPTIONAL_BASE_SIZE + 8 * directory_count > optional_size:
            raise PeFormatError("truncated_headers")
        table = optional + optional_size
        table_end = table + _SECTION_SIZE * section_count
        _require_range(image, table, _SECTION_SIZE * section_count)
        size_of_image, size_of_headers = _unpack(image, optional + 56, "<II")
        if (not size_of_image or not size_of_headers or size_of_headers < table_end
                or size_of_headers > len(image) or size_of_headers > size_of_image):
            raise PeFormatError("invalid_header_range")

        sections = []
        raw_spans = [(0, size_of_headers)]
        virtual_spans = [(0, size_of_headers)]
        regions = [(0, size_of_headers, 0)]
        for index in range(section_count):
            virtual_size, va, raw_size, raw_start = _unpack(
                image, table + index * _SECTION_SIZE + 8, "<IIII")
            extent = virtual_size if virtual_size else raw_size
            if raw_size and raw_start + raw_size > len(image):
                raise PeFormatError("invalid_section_range")
            if extent and (va + extent > size_of_image or va + extent > _RVA_LIMIT):
                raise PeFormatError("invalid_section_range")
            sections.append((va, virtual_size, raw_size, raw_start))
            if raw_size:
                raw_spans.append((raw_start, raw_start + raw_size))
            if extent:
                virtual_spans.append((va, va + extent))
            backed = min(raw_size, extent)
            if backed:
                regions.append((va, va + backed, raw_start))

        # Check all numeric ranges first, independent of table order. Compare
        # complete spans, including unmapped padding and virtual zero-fill tails.
        _reject_overlaps(raw_spans)
        _reject_overlaps(virtual_spans)
        directories = tuple(_unpack(image, optional + _OPTIONAL_BASE_SIZE + 8 * index, "<II")
                            for index in range(directory_count))
        # Publish no partially validated metadata. In particular, index 4 remains
        # raw file-offset metadata and is never prevalidated as an RVA.
        object.__setattr__(self, "_image", image)
        object.__setattr__(self, "architecture", architecture)
        object.__setattr__(self, "data_directories", directories)
        object.__setattr__(self, "_size_of_image", size_of_image)
        object.__setattr__(self, "_sections", tuple(sections))
        object.__setattr__(self, "_regions", tuple(regions))

    def rva_to_offset(self, rva: int, size: int) -> int:
        """Map one complete request inside one uniquely file-backed region."""
        if (type(rva) is not int or type(size) is not int
                or not 0 <= rva < _RVA_LIMIT or not 1 <= size <= _IMAGE_LIMIT
                or rva + size > _RVA_LIMIT or rva + size > self._size_of_image):
            raise PeFormatError("invalid_rva_range")
        for start, end, file_start in self._regions:
            if start <= rva and rva + size <= end:
                return file_start + rva - start
        raise PeFormatError("rva_not_file_backed")

    def read_rva(self, rva: int, size: int) -> bytes:
        """Return exact original bytes, without concatenation or zero filling."""
        offset = self.rva_to_offset(rva, size)
        return self._image[offset:offset + size]
