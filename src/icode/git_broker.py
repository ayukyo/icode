"""Fail-closed identity validation and Linux-only internal Git status query.

The fixed query accepts no model argv or repository path and is not exposed as
a tool. Metadata roots carry expected device/inode claims; the native Landlock
helper compares those claims on the same opened fd used to install each rule.
The prototype is not wired into user-facing execution or automatic mode.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import stat
from pathlib import Path
import sys

from .execution_broker import ExecutionResult, execute_policy_command
from .isolation import MetadataReadRoot
from .git_status import GitStatusParseError, GitStatusEntry, parse_porcelain_v2
from .sandbox_policy import NetworkMode, SandboxPolicy
from .workspace import GitPathIdentity, GitWorkspaceIdentity

_MAX_METADATA_FILE_BYTES = 4096
_GIT_STATUS_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_GIT_CONFIG_CHECK_MAX_OUTPUT_BYTES = 64 * 1024
_GIT_STATUS_TIMEOUT_SECONDS = 15
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
    metadata_roots: tuple[MetadataReadRoot, ...]


def execute_git_status(
    identity: GitWorkspaceIdentity | None,
    *,
    sandbox: object,
    policy: SandboxPolicy,
    timeout: int = _GIT_STATUS_TIMEOUT_SECONDS,
) -> tuple[GitStatusEntry, ...]:
    """Run one fixed, Linux-only, read-only status query for the trusted session.

    This remains an internal API: no tool or command route calls it. It accepts
    neither Git argv nor a repository path from the model. Any unsupported
    workspace shape, backend, metadata identity, helper, command result, or
    parser output fails closed with a path-free error.
    """
    from .isolation import LandlockSandbox

    if not sys.platform.startswith("linux") or not isinstance(sandbox, LandlockSandbox):
        raise GitStatusUnavailable("unsupported_backend")
    if not isinstance(policy, SandboxPolicy):
        raise GitStatusUnavailable("policy_missing")
    if (
        policy.network_mode is not NetworkMode.DENY
        or policy.allowed_domains
        or policy.read_roots != (policy.workspace_root,)
        or policy.write_roots != (policy.workspace_root,)
        or policy.wall_timeout_seconds < 1
        or policy.output_limit_bytes < 1
    ):
        raise GitStatusUnavailable("policy_not_read_only")
    if not isinstance(identity, GitWorkspaceIdentity):
        raise GitStatusUnavailable("identity_missing")

    try:
        workspace_root = _absolute_path(identity.workspace_root)
        if (
            identity.source_relative_path != Path(".")
            or policy.workspace_root != workspace_root
            or Path(policy.workspace_root).resolve(strict=True) != workspace_root
        ):
            raise GitStatusUnavailable("workspace_shape_unsupported")
        layout = verify_git_workspace_identity(identity)
        if (
            layout.worktree_root != workspace_root
            or layout.pathspec_root != workspace_root
        ):
            raise GitStatusUnavailable("worktree_policy_mismatch")
        required_deny_roots = {identity.checkout_root / ".git", identity.common_dir}
        if not required_deny_roots.issubset(set(policy.deny_write_roots)):
            raise GitStatusUnavailable("metadata_write_protection_missing")

        git_executable = _trusted_git_executable()
        git = str(git_executable)
        common = [
            git,
            "--no-pager",
            # Git <=2.35.1 treats the word "false" as a helper pathname.
            # An empty override safely clears any repository-selected helper.
            "-c", "core.fsmonitor=",
            "-c", "core.untrackedCache=false",
            "-c", "core.hooksPath=/dev/null",
            "-c", "core.excludesFile=/dev/null",
            "-c", "core.attributesFile=/dev/null",
            "-c", "status.renames=false",
            "--git-dir", str(layout.git_dir),
            "--work-tree", str(layout.worktree_root),
            "--no-optional-locks",
        ]
        wrap = getattr(sandbox, "_wrap_policy_with_metadata_roots", None)
        if not callable(wrap):
            raise GitStatusUnavailable("metadata_read_only_backend_missing")

        def run_query(arguments: list[str], output_limit: int) -> ExecutionResult:
            wrapped = wrap(
                [*common, *arguments],
                policy=policy,
                metadata_roots=layout.metadata_roots,
                network=False,
                workspace_read_only=True,
                execute_only=git_executable,
            )
            return execute_policy_command(
                wrapped,
                cwd=workspace_root,
                policy=policy,
                timeout=timeout,
                git_status=True,
                output_limit_bytes=output_limit,
            )

        # A configured clean/process filter can execute a shell command while
        # status inspects modified files. Do not try to sandbox arbitrary Git
        # helpers: conservatively refuse repositories that define either hook.
        filter_pattern = r"^filter\..*\.(clean|process)$"

        def has_filter_configuration(scope: str) -> bool:
            check = run_query(
                ["config", scope, "--null", "--get-regexp", filter_pattern],
                _GIT_CONFIG_CHECK_MAX_OUTPUT_BYTES,
            )
            if (
                check.error is not None
                or not check.cleanup_ok
                or check.output_truncated
                or check.exit_code not in (0, 1)
            ):
                raise GitStatusUnavailable("status_filter_configuration_unsupported")
            return bool(check.raw_output)

        if has_filter_configuration("--local"):
            raise GitStatusUnavailable("status_filter_configuration_unsupported")

        extension = run_query(
            ["config", "--local", "--bool", "--get", "extensions.worktreeConfig"],
            4096,
        )
        if (
            extension.error is not None
            or not extension.cleanup_ok
            or extension.output_truncated
            or extension.exit_code not in (0, 1)
            or extension.raw_output not in (b"", b"true\n", b"false\n")
        ):
            raise GitStatusUnavailable("status_worktree_config_unsupported")
        if extension.raw_output == b"true\n" and has_filter_configuration("--worktree"):
            raise GitStatusUnavailable("status_filter_configuration_unsupported")

        # Git may recursively inspect submodules. Refuse gitlinks before status
        # and then tell Git not to recurse, so nested repositories cannot supply
        # their own fsmonitor/filter configuration to this fixed query.
        index_entries = run_query(
            ["ls-files", "--stage", "-z"], _GIT_STATUS_MAX_OUTPUT_BYTES,
        )
        if (
            index_entries.error is not None
            or index_entries.exit_code != 0
            or not index_entries.cleanup_ok
            or index_entries.output_truncated
        ):
            raise GitStatusUnavailable("status_index_check_failed")
        for record in index_entries.raw_output.split(b"\0"):
            if not record:
                continue
            header, separator, path = record.partition(b"\t")
            fields = header.split(b" ")
            if not separator or not path or len(fields) != 3:
                raise GitStatusUnavailable("status_index_output_invalid")
            if fields[0] == b"160000":
                raise GitStatusUnavailable("submodules_unsupported")

        command = [
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=all",
            "--no-branch",
            "--",
        ]
        result = run_query(command, _GIT_STATUS_MAX_OUTPUT_BYTES)
        if (
            result.error is not None
            or result.exit_code != 0
            or not result.cleanup_ok
            or result.output_truncated
        ):
            raise GitStatusUnavailable("status_execution_failed")
        entries = parse_porcelain_v2(result.raw_output)
        if any(entry.submodule_status != b"N..." for entry in entries):
            raise GitStatusUnavailable("submodule_status_unsupported")
        return entries
    except GitStatusUnavailable:
        raise
    except GitStatusParseError:
        raise GitStatusUnavailable("status_output_invalid") from None
    except (OSError, RuntimeError, TypeError, ValueError, OverflowError):
        raise GitStatusUnavailable("status_execution_unavailable") from None


def _trusted_git_executable() -> Path:
    candidate = shutil.which("git", path="/usr/bin:/bin")
    if candidate is None:
        raise GitStatusUnavailable("git_executable_unavailable")
    try:
        executable = Path(candidate).resolve(strict=True)
        status = os.stat(executable, follow_symlinks=False)
    except (OSError, RuntimeError, ValueError):
        raise GitStatusUnavailable("git_executable_unavailable") from None
    if (
        not stat.S_ISREG(status.st_mode)
        or not os.access(executable, os.X_OK)
        or not (
            executable.is_relative_to(Path("/usr/bin"))
            or executable.is_relative_to(Path("/bin"))
        )
    ):
        raise GitStatusUnavailable("git_executable_untrusted")
    return executable


def verify_git_workspace_identity(
    identity: GitWorkspaceIdentity | None,
) -> VerifiedGitLayout:
    """Recheck manager-issued worktree metadata without invoking Git.

    Every path component is opened with ``O_NOFOLLOW`` and metadata files are
    read through already-open directory descriptors. This catches stale
    pointers, symlinks, changed/replaced HEAD files, and ownership-token drift.
    The returned roots preserve the session's expected device/inode values for
    the native helper to recheck while opening the exact Landlock rule objects.
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
        filesystem_identities = _verified_object_map(identity)

        if not isinstance(source_relative, Path):
            raise GitStatusUnavailable("source_path_invalid")
        if source_relative.is_absolute() or ".." in source_relative.parts:
            raise GitStatusUnavailable("source_path_invalid")
        if _lexical_absolute(code_root / source_relative) != workspace_root:
            raise GitStatusUnavailable("workspace_path_mismatch")
        if not git_dir.is_relative_to(common_dir) or git_dir == common_dir:
            raise GitStatusUnavailable("git_directory_relationship_invalid")

        directory_paths = {
            checkout_root, code_root, workspace_root, top_level, git_dir, common_dir,
        }
        file_paths = {
            checkout_root / ".git",
            git_dir / "commondir",
            git_dir / "HEAD",
            git_dir / "icode-workspace-identity",
        }
        if set(filesystem_identities) != directory_paths | file_paths:
            raise GitStatusUnavailable("filesystem_identity_set_mismatch")
        for directory in directory_paths:
            _verify_directory_identity(directory, filesystem_identities[directory])

        checkout_fd = _open_directory(checkout_root)
        try:
            git_pointer = _read_regular_file_at(
                checkout_fd, ".git", filesystem_identities[checkout_root / ".git"],
            )
        finally:
            os.close(checkout_fd)
        pointer_target = _parse_pointer(git_pointer, b"gitdir: ", checkout_root)
        if pointer_target != git_dir:
            raise GitStatusUnavailable("git_pointer_mismatch")

        git_fd = _open_directory(git_dir)
        try:
            common_pointer = _read_regular_file_at(
                git_fd, "commondir", filesystem_identities[git_dir / "commondir"],
            )
            head = _read_regular_file_at(
                git_fd, "HEAD", filesystem_identities[git_dir / "HEAD"],
            )
            ownership = _read_regular_file_at(
                git_fd,
                "icode-workspace-identity",
                filesystem_identities[git_dir / "icode-workspace-identity"],
            )
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
        metadata_roots=tuple(
            MetadataReadRoot(
                path,
                filesystem_identities[path].device,
                filesystem_identities[path].inode,
            )
            for path in (checkout_root / ".git", git_dir, common_dir)
        ),
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


def _verified_object_map(
    identity: GitWorkspaceIdentity,
) -> dict[Path, GitPathIdentity]:
    objects = identity.filesystem_identities
    if not objects or any(not isinstance(item, GitPathIdentity) for item in objects):
        raise GitStatusUnavailable("filesystem_identity_missing")
    mapped = {item.path: item for item in objects}
    if len(mapped) != len(objects):
        raise GitStatusUnavailable("filesystem_identity_duplicate")
    for path, item in mapped.items():
        if (
            not isinstance(path, Path)
            or type(item.device) is not int
            or type(item.inode) is not int
            or item.device < 0
            or item.inode < 0
            or item.kind not in ("file", "directory")
        ):
            raise GitStatusUnavailable("filesystem_identity_invalid")
    return mapped


def _verify_directory_identity(path: Path, expected: GitPathIdentity) -> None:
    if expected.path != path or expected.kind != "directory":
        raise GitStatusUnavailable("directory_identity_invalid")
    descriptor = _open_directory(path)
    try:
        status = os.fstat(descriptor)
        if (status.st_dev, status.st_ino) != (expected.device, expected.inode):
            raise GitStatusUnavailable("directory_identity_changed")
    finally:
        os.close(descriptor)


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


def _read_regular_file_at(
    directory_fd: int, name: str, expected: GitPathIdentity,
) -> bytes:
    if not name or "/" in name or name in (".", ".."):
        raise GitStatusUnavailable("metadata_name_invalid")
    if expected.kind != "file":
        raise GitStatusUnavailable("file_identity_invalid")
    descriptor = os.open(name, _NOFOLLOW_FLAGS, dir_fd=directory_fd)
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode) or (
            (status.st_dev, status.st_ino) != (expected.device, expected.inode)
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
