"""CI-only, bounded raw PE imports, delay imports and manifest policy.

Success describes only ``imports_delay_manifest``. It does not certify a whole
PE, loader compatibility, dependency origins, or trusted process execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import struct
import xml.etree.ElementTree as ET

from scripts.windows_pe_reader import PeImage

_READ_LIMIT = 16 * 1024 * 1024
_MODULE_LIMIT = 128
_SYMBOL_LIMIT = 4096
_STRING_LIMIT = 1024
_RESOURCE_LIMIT = 4096
_MANIFEST_LIMIT = 4096
_MANIFEST_TOTAL_LIMIT = 64 * 1024
_ORDINAL_FLAG = 1 << 63
_ASM_V1 = "urn:schemas-microsoft-com:asm.v1"
_ASM_V3 = "urn:schemas-microsoft-com:asm.v3"
_REASONS = frozenset({
    "directory_pair_invalid", "directory_not_declared", "budget_exceeded",
    "unterminated_table", "invalid_import", "unsupported_bound_import",
    "unsupported_delay_mode", "invalid_resource", "resource_cycle_or_alias",
    "invalid_manifest",
})


class PeDirectoryError(ValueError):
    """Closed reasons without attacker-controlled values in the message."""
    def __init__(self, reason: str):
        if type(reason) is not str or reason not in _REASONS:
            raise ValueError("directory_pair_invalid")
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ImportSymbol:
    name: str | None
    ordinal: int | None


@dataclass(frozen=True, slots=True)
class ImportModule:
    name: str
    symbols: tuple[ImportSymbol, ...]


@dataclass(frozen=True, slots=True)
class ResourceLeaf:
    path: tuple[int | str, int | str, int | str]
    rva: int
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ManifestLeaf:
    path: tuple[int | str, int | str, int | str]
    rva: int
    size: int
    sha256: str
    raw: bytes = field(repr=False)
    level: str
    ui_access: bool


@dataclass(frozen=True, slots=True)
class DirectoryInspection:
    architecture: str
    ordinary_imports: tuple[ImportModule, ...]
    delay_imports: tuple[ImportModule, ...]
    resources: tuple[ResourceLeaf, ...]
    manifests: tuple[ManifestLeaf, ...]
    scope: str = "imports_delay_manifest"


class _Inspection:
    """Private transactional context; no partial results escape on rejection."""
    def __init__(self, pe: PeImage):
        self.pe = pe
        self.read_left = _READ_LIMIT
        self.modules_left = _MODULE_LIMIT
        self.symbols_left = _SYMBOL_LIMIT
        self.resources_left = _RESOURCE_LIMIT
        self.manifests_left = _MANIFEST_TOTAL_LIMIT

    def consume(self, attr: str, size: int) -> None:
        remaining = getattr(self, attr)
        if size > remaining:
            raise PeDirectoryError("budget_exceeded")
        setattr(self, attr, remaining - size)

    def read(self, rva: int, size: int) -> bytes:
        # Charge repeated reads too, before read_rva performs any file slice.
        self.consume("read_left", size)
        return self.pe.read_rva(rva, size)

    def unpack(self, rva: int, fmt: str) -> tuple[int, ...]:
        return struct.unpack(fmt, self.read(rva, struct.calcsize(fmt)))

    def ascii(self, rva: int, *, dll: bool = False) -> str:
        raw = bytearray()
        for index in range(_STRING_LIMIT):
            byte = self.read(rva + index, 1)[0]
            if byte == 0:
                # Bytewise terminator search must not concatenate adjacent
                # backed regions into one supposedly complete string.
                self.pe.rva_to_offset(rva, index + 1)
                if not raw:
                    raise PeDirectoryError("invalid_import")
                name = raw.decode("ascii")
                if dll and (name in (".", "..") or any(c in name for c in "/\\:")):
                    raise PeDirectoryError("invalid_import")
                return name
            if byte > 127 or (dll and not 32 <= byte <= 126):
                raise PeDirectoryError("invalid_import")
            raw.append(byte)
        raise PeDirectoryError("budget_exceeded")

    def thunks(self, rva: int) -> tuple[tuple[int, ...], tuple[ImportSymbol, ...]]:
        if not rva:
            raise PeDirectoryError("invalid_import")
        values, symbols = [], []
        while True:
            value, = self.unpack(rva + len(values) * 8, "<Q")
            if value == 0:
                self.pe.rva_to_offset(rva, (len(values) + 1) * 8)
                return tuple(values), tuple(symbols)
            self.consume("symbols_left", 1)
            if value & _ORDINAL_FLAG:
                if value & ~(_ORDINAL_FLAG | 0xFFFF):
                    raise PeDirectoryError("invalid_import")
                symbol = ImportSymbol(None, value & 0xFFFF)
            else:
                if value > 0xFFFFFFFF:
                    raise PeDirectoryError("invalid_import")
                self.read(value, 2)  # Hint and name are independently file-backed.
                name = self.ascii(value + 2)
                self.pe.rva_to_offset(value, 2 + len(name) + 1)
                symbol = ImportSymbol(name, None)
            values.append(value)
            symbols.append(symbol)

    def address_table(self, rva: int, count: int, expected: tuple[int, ...] | None = None) -> None:
        if not rva:
            raise PeDirectoryError("invalid_import")
        # Require the complete equal-length table within one backed region.
        raw = self.read(rva, (count + 1) * 8)
        values = struct.unpack("<" + "Q" * (count + 1), raw)
        if values[-1] != 0 or any(value == 0 for value in values[:-1]):
            raise PeDirectoryError("invalid_import")
        if expected is not None and values[:-1] != expected:
            raise PeDirectoryError("invalid_import")

    def imports(self, pair: tuple[int, int], *, delay: bool) -> tuple[ImportModule, ...]:
        start, size = pair
        if not size:
            return ()
        stride = 32 if delay else 20
        modules = []
        offset = 0
        while offset + stride <= size:
            fields = self.unpack(start + offset, "<" + "I" * (stride // 4))
            offset += stride
            if not any(fields):
                return tuple(modules)
            self.consume("modules_left", 1)
            if delay:
                attrs, name, handle, iat, lookup, bound, unload, timestamp = fields
                if attrs != 1:
                    raise PeDirectoryError("unsupported_delay_mode")
                if bound or timestamp:
                    raise PeDirectoryError("unsupported_bound_import")
                if not handle:
                    raise PeDirectoryError("invalid_import")
                self.read(handle, 8)
            else:
                lookup, timestamp, _, name, iat = fields
                if timestamp:
                    raise PeDirectoryError("unsupported_bound_import")
                lookup = lookup or iat
            if not name:
                raise PeDirectoryError("invalid_import")
            dll = self.ascii(name, dll=True)
            values, symbols = self.thunks(lookup)
            # Delay IAT/unload values can be resolver addresses; never interpret
            # them as hint/name pointers. Ordinary unbound IAT must match lookup.
            self.address_table(iat, len(values), None if delay else values)
            if delay and unload:
                self.address_table(unload, len(values))
            modules.append(ImportModule(dll, symbols))
        raise PeDirectoryError("unterminated_table")

    def resources(self, pair: tuple[int, int]) -> tuple[tuple[ResourceLeaf, ...], tuple[ManifestLeaf, ...]]:
        base, size = pair
        leaves, manifests, visited = [], [], set()

        def metadata(offset: int, count: int) -> bytes:
            if offset < 0 or offset + count > size:
                raise PeDirectoryError("invalid_resource")
            return self.read(base + offset, count)

        def key(encoded: int) -> int | str:
            if not encoded & 0x80000000:
                if encoded > 0xFFFF:
                    raise PeDirectoryError("invalid_resource")
                return encoded
            offset = encoded & 0x7FFFFFFF
            length, = struct.unpack("<H", metadata(offset, 2))
            if not length:
                raise PeDirectoryError("invalid_resource")
            try:
                name = metadata(offset + 2, length * 2).decode("utf-16-le", errors="strict")
            except UnicodeDecodeError:
                raise PeDirectoryError("invalid_resource") from None
            if "\0" in name:
                raise PeDirectoryError("invalid_resource")
            return name

        def node(offset: int, path: tuple[int | str, ...]) -> None:
            if offset in visited:
                raise PeDirectoryError("resource_cycle_or_alias")
            visited.add(offset)
            characteristics, _, _, _, named, ids = struct.unpack("<IIHHHH", metadata(offset, 16))
            if characteristics:
                raise PeDirectoryError("invalid_resource")
            keys = set()
            for index in range(named + ids):
                self.consume("resources_left", 1)
                encoded, target = struct.unpack("<II", metadata(offset + 16 + index * 8, 8))
                if bool(encoded & 0x80000000) != (index < named):
                    raise PeDirectoryError("invalid_resource")
                name = key(encoded)
                if name in keys:
                    raise PeDirectoryError("invalid_resource")
                keys.add(name)
                leaf_path = path + (name,)
                directory = bool(target & 0x80000000)
                target &= 0x7FFFFFFF
                if len(leaf_path) < 3:
                    if not directory:
                        raise PeDirectoryError("invalid_resource")
                    node(target, leaf_path)
                    continue
                if directory:
                    raise PeDirectoryError("invalid_resource")
                self.consume("resources_left", 1)
                rva, length, _, reserved = struct.unpack("<IIII", metadata(target, 16))
                if reserved:
                    raise PeDirectoryError("invalid_resource")
                manifest = leaf_path[0] == 24
                if manifest:
                    if not length:
                        raise PeDirectoryError("invalid_manifest")
                    if length > _MANIFEST_LIMIT:
                        raise PeDirectoryError("budget_exceeded")
                    self.consume("manifests_left", length)
                if length:
                    raw = self.read(rva, length)
                else:
                    # Empty metadata carries no claim about backing, including
                    # an address at the image endpoint or in an unmapped gap.
                    if rva > self.pe._size_of_image:
                        raise PeDirectoryError("invalid_resource")
                    raw = b""
                if manifest:
                    _manifest_policy(raw)
                digest = hashlib.sha256(raw).hexdigest()
                leaves.append(ResourceLeaf(leaf_path, rva, length, digest))
                if manifest:
                    manifests.append(ManifestLeaf(leaf_path, rva, length, digest, raw, "asInvoker", False))

        if size:
            node(0, ())
        if not manifests:
            raise PeDirectoryError("invalid_manifest")
        return tuple(leaves), tuple(manifests)


def _manifest_policy(raw: bytes) -> None:
    try:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = raw.decode("utf-16", errors="strict")
        else:
            text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        raise PeDirectoryError("invalid_manifest") from None
    # Expat can auto-detect BOM-less UTF-16 even when ElementTree receives a
    # Python string containing NULs. Reject it before parsing the decoded text,
    # otherwise encoding auto-detection could bypass the DTD/entity check.
    if "\0" in text:
        raise PeDirectoryError("invalid_manifest")
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise PeDirectoryError("invalid_manifest")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise PeDirectoryError("invalid_manifest") from None
    if root.tag != f"{{{_ASM_V1}}}assembly" or root.get("manifestVersion") != "1.0":
        raise PeDirectoryError("invalid_manifest")
    # All security-chain local names must occur once in the whole document;
    # wrong namespaces, alternate placement and same-value duplicates fail.
    current = root
    for local in ("trustInfo", "security", "requestedPrivileges", "requestedExecutionLevel"):
        tag = f"{{{_ASM_V3}}}{local}"
        all_matches = [element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == local]
        direct = [child for child in current if child.tag == tag]
        if len(all_matches) != 1 or len(direct) != 1:
            raise PeDirectoryError("invalid_manifest")
        current = direct[0]
    if (current.attrib != {"level": "asInvoker", "uiAccess": "false"}
            or len(current) or (current.text is not None and current.text.strip())):
        raise PeDirectoryError("invalid_manifest")


def inspect_directories(image: bytes, *, expected_arch: str) -> DirectoryInspection:
    """Inspect the declared CI subset; base PeFormatError propagates unchanged."""
    pe = PeImage(image, expected_arch=expected_arch)
    if len(pe.data_directories) < 14:
        raise PeDirectoryError("directory_not_declared")
    for index in (1, 2, 11, 13):
        rva, size = pe.data_directories[index]
        if bool(rva) != bool(size):
            raise PeDirectoryError("directory_pair_invalid")
        if size:
            pe.rva_to_offset(rva, size)  # Validate complete declaration before use.
    if pe.data_directories[11] != (0, 0):
        raise PeDirectoryError("unsupported_bound_import")
    context = _Inspection(pe)
    ordinary = context.imports(pe.data_directories[1], delay=False)
    delay = context.imports(pe.data_directories[13], delay=True)
    resources, manifests = context.resources(pe.data_directories[2])
    return DirectoryInspection(pe.architecture, ordinary, delay, resources, manifests)
