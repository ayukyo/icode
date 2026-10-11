"""Bounded, immutable startup security snapshots; no access or launch authority.

Only the declared self-relative descriptor subset is accepted. This parser uses
owned bytes and does not query native pointers, HANDLEs, paths, or the OS.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from .windows_startup_pin import StartupPinError


_MAX_DESCRIPTOR_BYTES = 128 * 1024
_HEADER_SIZE = 20
_CONTROL_MASK = 0x950f
_REQUIRED_CONTROL = 0x8004
_ACE_FLAGS_MASK = 0x1f
_FILE_ACCESS_MASK = 0xf01f01ff


class StartupSecurityError(StartupPinError):
    """The bytes cannot satisfy the bounded security snapshot contract."""


@dataclass(frozen=True)
class StartupAccessEntry:
    allowed: bool
    flags: int
    mask: int
    sid: str


@dataclass(frozen=True)
class StartupSecurityDescriptor:
    raw: bytes
    owner_sid: str
    group_sid: str | None
    control: int
    entries: tuple[StartupAccessEntry, ...]


def _sid(data: bytes, start: int, limit: int) -> tuple[str, int]:
    if start + 8 > limit:
        raise StartupSecurityError("truncated SID header")
    revision, count = data[start:start + 2]
    end = start + 8 + 4 * count
    # Validate the entire SID before interpreting authority or subauthorities.
    if revision != 1 or count > 15 or end > limit:
        raise StartupSecurityError("invalid or truncated SID")
    authority = int.from_bytes(data[start + 2:start + 8], "big")
    subauthorities = struct.unpack_from(f"<{count}I", data, start + 8)
    return "S-1-" + str(authority) + "".join(f"-{value}" for value in subauthorities), end


def _acl(data: bytes, start: int) -> tuple[tuple[StartupAccessEntry, ...], int]:
    if start + 8 > len(data):
        raise StartupSecurityError("truncated ACL header")
    revision, reserved, size, count, reserved2 = struct.unpack_from("<BBHHH", data, start)
    end = start + size
    if (revision not in (2, 4) or reserved or reserved2 or size < 8
            or size % 4 or end > len(data)):
        raise StartupSecurityError("invalid ACL header or range")
    position = start + 8
    entries = []
    for _ in range(count):
        if position + 8 > end:
            raise StartupSecurityError("truncated ACE header")
        kind, flags, ace_size, mask = struct.unpack_from("<BBHI", data, position)
        ace_end = position + ace_size
        if (kind not in (0, 1) or flags & ~_ACE_FLAGS_MASK or mask & ~_FILE_ACCESS_MASK
                or ace_size < 16 or ace_size % 4 or ace_end > end):
            raise StartupSecurityError("unsupported or invalid ACE")
        trustee, sid_end = _sid(data, position + 8, ace_end)
        if sid_end != ace_end:
            raise StartupSecurityError("SID does not fill ACE")
        entries.append(StartupAccessEntry(kind == 0, flags, mask, trustee))
        position = ace_end
    if any(data[position:end]):
        raise StartupSecurityError("nonzero unused ACL bytes")
    return tuple(entries), end


def parse_startup_security(data: bytes) -> StartupSecurityDescriptor:
    """Parse the supported descriptor bytes, without deciding access policy."""
    if type(data) is not bytes or not _HEADER_SIZE <= len(data) <= _MAX_DESCRIPTOR_BYTES:
        raise StartupSecurityError("security descriptor must be bounded exact bytes")
    revision, reserved, control, owner, group, sacl, dacl = struct.unpack_from("<BBHIIII", data)
    if (revision != 1 or reserved or control & ~_CONTROL_MASK
            or control & _REQUIRED_CONTROL != _REQUIRED_CONTROL or sacl
            or not owner or not dacl):
        raise StartupSecurityError("unsupported security descriptor header")
    for offset in (owner, group, dacl):
        if offset and (offset < _HEADER_SIZE or offset % 4 or offset >= len(data)):
            raise StartupSecurityError("invalid security component offset")

    owner_sid, owner_end = _sid(data, owner, len(data))
    regions = [(owner, owner_end, "owner")]
    group_sid = None
    if group:
        group_sid, group_end = _sid(data, group, len(data))
        regions.append((group, group_end, "group"))
    entries, dacl_end = _acl(data, dacl)
    regions.append((dacl, dacl_end, "dacl"))

    # Owner/group may reference exactly one SID. Every other overlap fails,
    # including syntactically valid components embedded within another range.
    for index, (start, end, role) in enumerate(regions):
        for other_start, other_end, other_role in regions[index + 1:]:
            if start < other_end and other_start < end:
                if ({role, other_role} != {"owner", "group"}
                        or (start, end) != (other_start, other_end)):
                    raise StartupSecurityError("overlapping security components")
    position = _HEADER_SIZE
    for start, end in sorted({(start, end) for start, end, _ in regions}):
        if any(data[position:start]):
            raise StartupSecurityError("nonzero unreferenced descriptor bytes")
        position = end
    if any(data[position:]):
        raise StartupSecurityError("nonzero unreferenced descriptor bytes")
    return StartupSecurityDescriptor(data, owner_sid, group_sid, control, entries)


_ADMIN_SID = "S-1-5-32-544"
_SYSTEM_SID = "S-1-5-18"
_OWNER_RIGHTS_SID = "S-1-3-4"
_MAX_TEXT_SID_LENGTH = 184  # S-1-, 48-bit authority, and fifteen 32-bit subauthorities.
_MUTATION_ACCESS_MASK = (
    0x2 | 0x4 | 0x10 | 0x100  # write data, append, write EA, write attributes
    | 0x10000 | 0x40000 | 0x80000  # DELETE, WRITE_DAC, WRITE_OWNER
    | 0x40000000 | 0x10000000  # GENERIC_WRITE, GENERIC_ALL
)
_DELETE_CHILD = 0x40


def _validate_host_sid(value: str) -> None:
    """Require the same bounded decimal SID spelling produced by the parser."""
    if type(value) is not str or not 5 <= len(value) <= _MAX_TEXT_SID_LENGTH:
        raise StartupSecurityError("host SID must be bounded exact str")
    parts = value.split("-")
    if parts[:2] != ["S", "1"] or not 3 <= len(parts) <= 18:
        raise StartupSecurityError("host SID must have revision 1 and at most 15 subauthorities")
    for index, part in enumerate(parts[2:]):
        if (not part or any(character < "0" or character > "9" for character in part)
                or (len(part) > 1 and part[0] == "0")):
            raise StartupSecurityError("host SID must use canonical ASCII decimal")
        limit = (1 << 48) - 1 if index == 0 else (1 << 32) - 1
        if int(part) > limit:
            raise StartupSecurityError("host SID numeric component out of range")


def check_startup_security(data: bytes, *, role: str, host_sid: str,
                           directory: bool) -> StartupSecurityDescriptor:
    """Reject snapshots permitting untrusted mutation; never grant RX or launch.

    The internal consumer must capture host_sid from its actual host token.
    This byte-only policy does not simulate AccessCheck, group membership, or
    ACE ordering. Deny and inherit-only entries cannot erase mutation risk.
    """
    if type(role) is not str or role not in ("source", "protected"):
        raise StartupSecurityError("security role must be source or protected")
    if type(directory) is not bool:
        raise StartupSecurityError("directory must be exact bool")
    _validate_host_sid(host_sid)
    # Reparse owned bytes here: caller-constructed snapshots are not authority.
    snapshot = parse_startup_security(data)
    trusted = {_ADMIN_SID, _SYSTEM_SID}
    if role == "source":
        trusted.add(host_sid)
    if snapshot.owner_sid not in trusted:
        raise StartupSecurityError("startup security owner is not trusted for role")
    if not snapshot.entries:
        raise StartupSecurityError("empty DACL cannot establish usable startup security")
    mutation_mask = _MUTATION_ACCESS_MASK | (_DELETE_CHILD if directory else 0)
    for entry in snapshot.entries:
        # OWNER RIGHTS refers only to the actual owner, already checked above.
        trustee = snapshot.owner_sid if entry.sid == _OWNER_RIGHTS_SID else entry.sid
        if entry.allowed and trustee not in trusted and entry.mask & mutation_mask:
            raise StartupSecurityError("untrusted ACE permits startup mutation")
    return snapshot
