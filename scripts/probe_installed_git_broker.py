"""Verify the Git status broker from a cleanly installed Linux wheel."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile


class ProbeFailure(RuntimeError):
    """A path-free failure classification for CI output."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ProbeFailure(code)


def _run_git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        cwd=repository,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=15,
    )
    _require(result.returncode == 0, "git_fixture_setup_failed")
    return result


def _run_git_for_identity(
    identity: object, *arguments: str,
) -> subprocess.CompletedProcess[bytes]:
    git_dir = getattr(identity, "git_dir", None)
    worktree_root = getattr(identity, "workspace_root", None)
    _require(isinstance(git_dir, Path), "git_identity_invalid")
    _require(isinstance(worktree_root, Path), "git_identity_invalid")
    result = subprocess.run(
        [
            "/usr/bin/git", "--git-dir", str(git_dir), "--work-tree",
            str(worktree_root), *arguments,
        ],
        cwd=worktree_root,
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=15,
    )
    _require(result.returncode == 0, "git_fixture_setup_failed")
    return result


def _filesystem_snapshot(root: Path) -> tuple[tuple[str, int, bytes], ...]:
    records: list[tuple[str, int, bytes]] = []
    for directory_name, child_directories, child_files in os.walk(
        root, followlinks=False
    ):
        directory = Path(directory_name)
        for name in sorted((*child_directories, *child_files)):
            path = directory / name
            status = path.lstat()
            if stat.S_ISLNK(status.st_mode):
                content = os.fsencode(os.readlink(path))
            elif stat.S_ISREG(status.st_mode):
                content = hashlib.sha256(path.read_bytes()).digest()
            elif stat.S_ISDIR(status.st_mode):
                content = b""
            else:
                raise ProbeFailure("unexpected_git_filesystem_object")
            records.append(
                (path.relative_to(root).as_posix(), stat.S_IFMT(status.st_mode), content)
            )
        child_directories[:] = [
            name for name in child_directories if not (directory / name).is_symlink()
        ]
    return tuple(records)


def _git_tree_snapshot(identity: object) -> tuple[tuple[str, int, bytes], ...]:
    checkout_root = getattr(identity, "checkout_root", None)
    git_dir = getattr(identity, "git_dir", None)
    common_dir = getattr(identity, "common_dir", None)
    _require(
        all(isinstance(path, Path) for path in (checkout_root, git_dir, common_dir)),
        "git_identity_invalid",
    )
    records = []
    for label, root in (
        ("checkout", checkout_root), ("git", git_dir), ("common", common_dir),
    ):
        records.extend(
            (f"{label}/{name}", mode, content)
            for name, mode, content in _filesystem_snapshot(root)
        )
    return tuple(records)


def _configure_test_environment(root: Path) -> None:
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            os.environ.pop(name, None)
    os.environ.update(
        {
            "HOME": str(root),
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_AUTHOR_NAME": "ICODE wheel test",
            "GIT_AUTHOR_EMAIL": "icode-wheel@example.invalid",
            "GIT_COMMITTER_NAME": "ICODE wheel test",
            "GIT_COMMITTER_EMAIL": "icode-wheel@example.invalid",
        }
    )


def _probe() -> None:
    if not sys.platform.startswith("linux"):
        raise ProbeFailure("unsupported_platform")
    if not Path("/usr/bin/git").is_file():
        raise ProbeFailure("git_executable_unavailable")

    from icode.git_broker import GitStatusUnavailable, execute_git_status
    from icode.isolation import LandlockSandbox
    from icode.sandbox_policy import NetworkMode
    from icode.workspace import WorkspaceManager

    with tempfile.TemporaryDirectory(prefix="icode-installed-git-") as raw:
        root = Path(raw).resolve()
        _configure_test_environment(root)

        source = root / "source"
        source.mkdir()
        _run_git(source, "init", "--initial-branch=main")
        (source / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        _run_git(source, "add", "tracked.txt")
        _run_git(source, "commit", "-m", "baseline")

        manager = WorkspaceManager(
            source,
            root / "workspace-data",
            "installed-git-broker-probe",
            isolate_git_metadata=True,
        )
        session = manager.open("ticket", "run")
        try:
            identity = session.git_status_identity
            _require(identity is not None, "git_identity_missing")
            sandbox = LandlockSandbox.from_bundle()
            _require(sandbox is not None, "installed_landlock_helper_missing")

            workspace = session.workspace_root
            index_path = identity.git_dir / "index"
            index_before = index_path.read_bytes()
            source_before = (source / "tracked.txt").read_bytes()
            (workspace / "tracked.txt").write_text("modified\n", encoding="utf-8")
            (workspace / "new file.txt").write_text("new\n", encoding="utf-8")

            helper_marker = root / "external-helper-ran"
            helper = root / "hostile-helper"
            helper.write_text(
                "#!/bin/sh\n"
                f"/usr/bin/touch {shlex.quote(str(helper_marker))}\n"
                "exec /bin/cat\n",
                encoding="utf-8",
            )
            helper.chmod(0o755)
            _run_git_for_identity(identity, "config", "core.fsmonitor", str(helper))
            _run_git_for_identity(identity, "config", "diff.external", str(helper))

            policy = session.policy(
                "review", wall_timeout_seconds=10, output_limit_bytes=1024 * 1024
            )
            _require(policy.network_mode is NetworkMode.DENY, "git_policy_not_offline")
            metadata_before = _git_tree_snapshot(identity)
            entries = execute_git_status(identity, sandbox=sandbox, policy=policy)
            entry_paths = {entry.path for entry in entries}
            if entry_paths != {b"tracked.txt", b"new file.txt"}:
                raise ProbeFailure(
                    "git_status_result_mismatch "
                    f"tracked={b'tracked.txt' in entry_paths} "
                    f"new_file={b'new file.txt' in entry_paths} "
                    f"count={len(entry_paths)}"
                )
            _require(not helper_marker.exists(), "external_git_helper_ran")
            _require(
                _git_tree_snapshot(identity) == metadata_before,
                "git_metadata_changed",
            )
            _require(index_path.read_bytes() == index_before, "git_index_changed")
            _require(
                (source / "tracked.txt").read_bytes() == source_before,
                "original_repository_changed",
            )

            attributes = workspace / ".gitattributes"
            attributes.write_text("tracked.txt filter=hostile\n", encoding="ascii")
            filter_marker = root / "clean-filter-ran"
            clean_filter = root / "hostile-clean-filter"
            clean_filter.write_text(
                "#!/bin/sh\n"
                f"/usr/bin/touch {shlex.quote(str(filter_marker))}\n"
                "exec /bin/cat\n",
                encoding="utf-8",
            )
            clean_filter.chmod(0o755)
            _run_git_for_identity(
                identity, "config", "filter.hostile.clean", str(clean_filter)
            )

            control = subprocess.run(
                [
                    "/usr/bin/git", "--git-dir", str(identity.git_dir),
                    "--work-tree", str(identity.workspace_root),
                    "-c", "core.fsmonitor=false", "--no-optional-locks",
                    "status", "--porcelain=v2", "-z", "--no-branch", "--",
                ],
                cwd=workspace,
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=15,
            )
            _require(control.returncode == 0, "git_filter_control_failed")
            _require(filter_marker.is_file(), "git_filter_control_not_triggered")
            filter_marker.unlink()

            metadata_before = _git_tree_snapshot(identity)
            try:
                execute_git_status(identity, sandbox=sandbox, policy=policy)
            except GitStatusUnavailable as exc:
                _require(
                    str(exc) == "status_filter_configuration_unsupported",
                    "git_filter_rejected_for_unexpected_reason",
                )
            else:
                raise ProbeFailure("configured_clean_filter_not_rejected")

            _require(not filter_marker.exists(), "git_clean_filter_ran_in_broker")
            _require(
                _git_tree_snapshot(identity) == metadata_before,
                "git_metadata_changed",
            )
            _require(index_path.read_bytes() == index_before, "git_index_changed")
            _require(
                (source / "tracked.txt").read_bytes() == source_before,
                "original_repository_changed",
            )
        finally:
            session.lease.release()


def main() -> int:
    try:
        _probe()
    except ProbeFailure as exc:
        print(f"::error::{exc}")
        return 1
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"::error::git_broker_wheel_probe_failed ({type(exc).__name__})")
        return 1
    print("installed Git status broker: read-only query and hostile-filter rejection PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
