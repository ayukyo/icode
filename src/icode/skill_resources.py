"""Pinned, stdlib-only SKILL resource integrity and build staging.

The manifest is part of the installed TCB, not a signature or launch grant.
Resources are consumed without writes; this is not an OS read-only guarantee.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_COMMIT = "1693651c1bd7daad3272eb054f0f81d6f254d08d"
MANIFEST_SHA256 = "1afcdfa48214a5a0c16f14c9bf25617bb1015e8fbda7e3de3a613d8dc2b6986c"
MAX_MANIFEST_BYTES = 32768
MAX_MEMBER_BYTES = 1048576
MEMBER_COUNT = 72
TOTAL_BYTES = 1928781


class SkillResourceError(ValueError):
    """Missing, unsafe or altered fixed resources; never silently degrade."""


def _fail():
    raise SkillResourceError("Fixed SKILL resource integrity check failed")


def _plain(path: Path, *, directory: bool) -> None:
    info = path.lstat()
    # Windows directory junctions are reparse points, not always is_symlink().
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        _fail()


def _read_file(path: Path, limit: int) -> bytes:
    _plain(path, directory=False)
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        _fail()
    return raw


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def read_manifest(path: Path | None = None) -> dict:
    """Validate bounded JSON and its fixed byte identity before using paths."""
    try:
        raw = _read_file(path or PACKAGE_DIR / "skill_runtime_manifest.json", MAX_MANIFEST_BYTES)
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if not isinstance(data, dict) or set(data) != {"schema_version", "source", "members"}:
            _fail()
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            _fail()
        if data["source"] != {"repository": "https://github.com/ayukyo/icode-skill",
                              "commit": SOURCE_COMMIT, "license": "MIT"}:
            _fail()
        members = data["members"]
        if not isinstance(members, list) or len(members) != MEMBER_COUNT:
            _fail()
        paths = []
        for member in members:
            if not isinstance(member, dict) or set(member) != {"path", "size", "sha256"}:
                _fail()
            name, size, digest = member["path"], member["size"], member["sha256"]
            if (not isinstance(name, str)
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", name)
                    or any(part in {".", ".."} for part in name.split("/"))
                    or PurePosixPath(name).as_posix() != name
                    or type(size) is not int or not 0 < size <= MAX_MEMBER_BYTES
                    or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                _fail()
            paths.append(name)
        if paths != sorted(set(paths)) or sum(m["size"] for m in members) != TOTAL_BYTES:
            _fail()
        if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
            _fail()
        return data
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SkillResourceError("Fixed SKILL manifest is missing or invalid") from exc


def _member(root: Path, name: str) -> Path:
    path = root
    parts = PurePosixPath(name).parts
    for component in parts[:-1]:
        path /= component
        _plain(path, directory=True)
    path /= parts[-1]
    if root.resolve() not in path.resolve().parents:
        _fail()
    return path


def verify_resources(root: Path) -> Path:
    """Check all fixed members before any CP invocation or build copy."""
    try:
        root = Path(root).absolute()
        _plain(root, directory=True)
        for member in read_manifest()["members"]:
            raw = _read_file(_member(root, member["path"]), member["size"])
            if len(raw) != member["size"] or hashlib.sha256(raw).hexdigest() != member["sha256"]:
                _fail()
        return root
    except OSError as exc:
        raise SkillResourceError("Fixed SKILL resources are missing or inaccessible") from exc


def bundled_skill_root() -> Path:
    # pip/pipx install a stable unpacked directory. No temporary as_file context.
    return verify_resources(PACKAGE_DIR / "skill_runtime")


def stage_resources(source: Path, destination: Path) -> None:
    """Copy only the pinned closure; reject stale extras and unsafe build paths."""
    source = verify_resources(source)
    members = read_manifest()["members"]
    allowed = {m["path"] for m in members}
    destination = Path(destination).absolute()
    try:
        for parent in (destination, *destination.parents):
            if parent.exists() or parent.is_symlink():
                _plain(parent, directory=True)
        if destination.exists():
            for path in destination.rglob("*"):
                _plain(path, directory=path.is_dir())
                if path.is_file() and path.relative_to(destination).as_posix() not in allowed:
                    _fail()
        # Verify the full source and destination boundary before the first write.
        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            target = destination / member["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = _read_file(_member(source, member["path"]), member["size"])
            if hashlib.sha256(raw).hexdigest() != member["sha256"]:
                _fail()
            if target.exists() and _read_file(target, member["size"]) == raw:
                continue
            # sdist may hardlink release-tree files. Replacing a staged inode
            # avoids rewriting source files or a foreign hardlink's contents.
            fd, temporary = tempfile.mkstemp(prefix=".skill-stage-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        verify_resources(destination)
    except OSError as exc:
        raise SkillResourceError("Cannot stage fixed SKILL resources") from exc
