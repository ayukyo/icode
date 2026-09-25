"""Fail-closed validation primitives for the internal Git status broker.

This module does not launch Git or expose a tool. It verifies the immutable
workspace-manager identity immediately before a future fixed-argument query.
The returned metadata roots are candidates only; callers still need the OS
read-only/network-isolation contract before they may execute Git.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import stat
from pathlib import Path

from .workspace import GitWorkspaceIdentity

_MAX_METADATA_FILE_BYTES = 4096
_NOFOLLOW_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


class GitStatusUnavailable(RuntimeError):
    """The trusted worktree identity is absent, stale, or not safely verifiable."""


@dataclass(frozen=True)
class VerifiedGitLayout:
    """Validated roots for one internal status query; not an execution grant."""

    worktree_root: Path
    git_dir: Path
    common_dir: Path
    pathspec_root: Path
    metadata_roots: tuple[Path, ...]


def verify_git_workspace_identity(
    identity: GitWorkspaceIdentity | None,
) -> VerifiedGitLayout:
    """Recheck manager-issued worktree metadata without invoking Git.

    Every path component is opened with ``O_NOFOLLOW`` and metadata files are
    read through already-open directory descriptors. This catches stale
    pointers, symlinks, changed HEAD contents, and ownership-token drift. It
    does not bind directory device/inode values across a later helper launch,
    so the result must not be treated as a complete TOCTOU-proof execution grant.
    """
    if (
        os.name != "posix"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
    ):
        raise GitStatusUnavailable("unsupported_platform")
    if not isinstance(identity, GitWorkspaceIdentity):
        raise GitStatusUnavailable("identity_missing")

    try:
        checkout_root = _absolute_path(identity.checkout_root)
        code_root = _absolute_path(identity.code_root)
        workspace_root = _absolute_path(identity.workspace_root)
        top_level = _absolute_path(identity.top_level)
        git_dir = _absolute_path(identity.git_dir)
        common_dir = _absolute_path(identity.common_dir)
        source_relative = identity.source_relative_path

        if not isinstance(source_relative, Path):
            raise GitStatusUnavailable("source_path_invalid")
        if source_relative.is_absolute() or ".." in source_relative.parts:
            raise GitStatusUnavailable("source_path_invalid")
        if _lexical_absolute(code_root / source_relative) != workspace_root:
            raise GitStatusUnavailable("workspace_path_mismatch")
        if not git_dir.is_relative_to(common_dir) or git_dir == common_dir:
            raise GitStatusUnavailable("git_directory_relationship_invalid")

        for directory in (checkout_root, code_root, workspace_root, top_level,
                          git_dir, common_dir):
            descriptor = _open_directory(directory)
            os.close(descriptor)

        checkout_fd = _open_directory(checkout_root)
        try:
            git_pointer = _read_regular_file_at(checkout_fd, ".git")
        finally:
            os.close(checkout_fd)
        pointer_target = _parse_pointer(git_pointer, b"gitdir: ", checkout_root)
        if pointer_target != git_dir:
            raise GitStatusUnavailable("git_pointer_mismatch")

        git_fd = _open_directory(git_dir)
        try:
            common_pointer = _read_regular_file_at(git_fd, "commondir")
            head = _read_regular_file_at(git_fd, "HEAD")
            ownership = _read_regular_file_at(git_fd, "icode-workspace-identity")
        finally:
            os.close(git_fd)
        common_target = _parse_pointer(common_pointer, b"", git_dir)
        if common_target != common_dir:
            raise GitStatusUnavailable("common_directory_mismatch")
        if not identity.revision or any(
            character not in "0123456789abcdef" for character in identity.revision
        ) or len(identity.revision) not in (40, 64):
            raise GitStatusUnavailable("revision_invalid")
        if head != identity.revision.encode("ascii") + b"\n":
            raise GitStatusUnavailable("revision_mismatch")
        if (
            len(identity.identity_token) != 32
            or any(
                character not in "0123456789abcdef"
                for character in identity.identity_token
            )
            or ownership != identity.identity_token.encode("ascii")
        ):
            raise GitStatusUnavailable("ownership_mismatch")
    except GitStatusUnavailable:
        raise
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        OverflowError,
        AttributeError,
    ):
        raise GitStatusUnavailable("identity_unverifiable") from None

    return VerifiedGitLayout(
        worktree_root=code_root,
        git_dir=git_dir,
        common_dir=common_dir,
        pathspec_root=workspace_root,
        metadata_roots=(checkout_root / ".git", git_dir, common_dir),
    )


def _absolute_path(path: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise GitStatusUnavailable("path_not_absolute")
    normalized = _lexical_absolute(candidate)
    if normalized != candidate:
        raise GitStatusUnavailable("path_not_normalized")
    return candidate


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _open_directory(path: Path) -> int:
    """Open an absolute directory by walking from `/` without following links."""
    parts = path.parts
    if not parts or parts[0] != path.anchor:
        raise GitStatusUnavailable("directory_path_invalid")
    current = os.open(path.anchor, _NOFOLLOW_FLAGS | os.O_DIRECTORY)
    try:
        for part in parts[1:]:
            if not part or part in (".", ".."):
                raise GitStatusUnavailable("directory_component_invalid")
            next_fd = os.open(
                part,
                _NOFOLLOW_FLAGS | os.O_DIRECTORY,
                dir_fd=current,
            )
            os.close(current)
            current = next_fd
        if not stat.S_ISDIR(os.fstat(current).st_mode):
            raise GitStatusUnavailable("not_a_directory")
        return current
    except BaseException:
        os.close(current)
        raise


def _read_regular_file_at(directory_fd: int, name: str) -> bytes:
    if not name or "/" in name or name in (".", ".."):
        raise GitStatusUnavailable("metadata_name_invalid")
    descriptor = os.open(name, _NOFOLLOW_FLAGS, dir_fd=directory_fd)
    try:
        status = os.fstat(descriptor)
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_size > _MAX_METADATA_FILE_BYTES
        ):
            raise GitStatusUnavailable("metadata_file_invalid")
        chunks: list[bytes] = []
        remaining = _MAX_METADATA_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > _MAX_METADATA_FILE_BYTES:
            raise GitStatusUnavailable("metadata_file_too_large")
        return data
    finally:
        os.close(descriptor)


def _parse_pointer(content: bytes, prefix: bytes, relative_to: Path) -> Path:
    value = content
    if prefix:
        if not value.startswith(prefix):
            raise GitStatusUnavailable("metadata_pointer_invalid")
        value = value[len(prefix):]
    if value.endswith(b"\n"):
        value = value[:-1]
    if not value or b"\0" in value or b"\n" in value or b"\r" in value:
        raise GitStatusUnavailable("metadata_pointer_invalid")
    target = Path(os.fsdecode(value))
    if not target.is_absolute():
        target = relative_to / target
    return _lexical_absolute(target)
