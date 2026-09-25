"""Strict parser for Git porcelain-v2 NUL output; this module never runs Git.

Parsed paths remain bytes so unusual filesystem names are not lossy-decoded.
Parsing is not an execution or filesystem security boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


class GitStatusParseError(ValueError):
    """Raised when Git status output is truncated or outside porcelain-v2 grammar."""


@dataclass(frozen=True)
class GitStatusEntry:
    kind: Literal["tracked", "unmerged", "untracked", "ignored"]
    path: bytes
    index_status: str | None
    worktree_status: str | None
    original_path: bytes | None = None
    submodule_status: bytes = b"N..."


_MODES = frozenset({
    b"000000", b"040000", b"100644", b"100755", b"120000", b"160000",
})
_OBJECT_ID = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_RENAME_SCORE = re.compile(rb"([RC])([0-9]{1,3})\Z")
_ORDINARY_STATUS_CHARS = frozenset(".MTADRC")
_UNMERGED_STATUSES = frozenset({"DD", "AU", "UD", "UA", "DU", "AA", "UU"})


def parse_porcelain_v2(output: bytes) -> tuple[GitStatusEntry, ...]:
    """Parse complete `git status --porcelain=v2 -z` bytes or reject all output.

    The parser preserves path bytes, ignores extensible `#` headers as Git's
    format requires, and rejects unknown or malformed item records rather than
    returning a partial status list.
    """
    if not isinstance(output, bytes):
        raise TypeError("porcelain-v2 output must be bytes")
    if not output:
        return ()
    if not output.endswith(b"\0"):
        raise GitStatusParseError("porcelain-v2 stream is not NUL terminated")

    records = output.split(b"\0")[:-1]
    entries: list[GitStatusEntry] = []
    record_index = 0
    while record_index < len(records):
        record = records[record_index]
        record_index += 1
        if not record:
            raise GitStatusParseError("porcelain-v2 stream contains an empty record")
        if record.startswith(b"#"):
            if (
                not record.startswith(b"# ")
                or len(record) == 2
                or record[2:3] in (b" ", b"\t")
            ):
                raise GitStatusParseError("malformed porcelain-v2 header")
            continue

        if record.startswith(b"1 "):
            fields = record.split(b" ", 8)
            if len(fields) != 9:
                raise GitStatusParseError("malformed ordinary tracked record")
            status = _validate_tracked_fields(fields[1:8])
            path = fields[8]
            _require_path(path)
            entries.append(
                GitStatusEntry(
                    "tracked", path, status[0], status[1],
                    submodule_status=fields[2],
                )
            )
            continue

        if record.startswith(b"2 "):
            fields = record.split(b" ", 9)
            if len(fields) != 10:
                raise GitStatusParseError("malformed renamed/copied tracked record")
            status = _validate_tracked_fields(fields[1:8])
            score = _RENAME_SCORE.fullmatch(fields[8])
            if score is None or int(score.group(2)) > 100:
                raise GitStatusParseError("invalid rename/copy score")
            if score.group(1).decode("ascii") not in status:
                raise GitStatusParseError("rename/copy score does not match XY status")
            path = fields[9]
            _require_path(path)
            if record_index >= len(records):
                raise GitStatusParseError("renamed/copied record is missing original path")
            original_path = records[record_index]
            record_index += 1
            _require_path(original_path)
            entries.append(
                GitStatusEntry(
                    "tracked", path, status[0], status[1], original_path,
                    submodule_status=fields[2],
                ),
            )
            continue

        if record.startswith(b"u "):
            fields = record.split(b" ", 10)
            if len(fields) != 11:
                raise GitStatusParseError("malformed unmerged record")
            _validate_submodule(fields[2])
            for mode in fields[3:7]:
                _validate_mode(mode)
            for object_id in fields[7:10]:
                _validate_object_id(object_id)
            status = _status_pair(fields[1], frozenset(".MTADRCU"))
            if status not in _UNMERGED_STATUSES:
                raise GitStatusParseError("invalid unmerged XY status")
            path = fields[10]
            _require_path(path)
            entries.append(
                GitStatusEntry(
                    "unmerged", path, status[0], status[1],
                    submodule_status=fields[2],
                )
            )
            continue

        if record.startswith(b"? "):
            path = record[2:]
            _require_path(path)
            entries.append(GitStatusEntry("untracked", path, None, None))
            continue

        if record.startswith(b"! "):
            path = record[2:]
            _require_path(path)
            entries.append(GitStatusEntry("ignored", path, None, None))
            continue

        raise GitStatusParseError("unknown porcelain-v2 item record")

    return tuple(entries)


def _validate_tracked_fields(fields: list[bytes]) -> str:
    if len(fields) != 7:
        raise GitStatusParseError("malformed tracked metadata")
    status = _status_pair(fields[0], _ORDINARY_STATUS_CHARS)
    index_status, worktree_status = status
    if not (
        (index_status in "MTARC" and worktree_status in ".MTD")
        or (index_status == "D" and worktree_status == ".")
        or (index_status == "." and worktree_status in "MTDRCA")
    ):
        raise GitStatusParseError("invalid tracked XY status combination")
    _validate_submodule(fields[1])
    for mode in fields[2:5]:
        _validate_mode(mode)
    for object_id in fields[5:7]:
        _validate_object_id(object_id)
    return status


def _status_pair(value: bytes, allowed: frozenset[str]) -> str:
    try:
        status = value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise GitStatusParseError("status field is not ASCII") from exc
    if len(status) != 2 or any(character not in allowed for character in status):
        raise GitStatusParseError("invalid XY status field")
    if status == "..":
        raise GitStatusParseError("unchanged path must not appear as a status record")
    return status


def _validate_submodule(value: bytes) -> None:
    if value == b"N...":
        return
    if (
        len(value) == 4
        and value[:1] == b"S"
        and value[1:2] in (b".", b"C")
        and value[2:3] in (b".", b"M")
        and value[3:4] in (b".", b"U")
    ):
        return
    raise GitStatusParseError("invalid submodule state")


def _validate_mode(value: bytes) -> None:
    if value not in _MODES:
        raise GitStatusParseError("invalid file mode")


def _validate_object_id(value: bytes) -> None:
    if _OBJECT_ID.fullmatch(value) is None:
        raise GitStatusParseError("invalid object ID")


def _require_path(value: bytes) -> None:
    if not value:
        raise GitStatusParseError("empty path in porcelain-v2 record")
