from __future__ import annotations

import os
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
import sys

from icode.git_broker import (
    GitStatusUnavailable,
    execute_git_status,
    verify_git_workspace_identity,
)
from icode.isolation import LandlockSandbox
from icode.workspace import WorkspaceManager


def _git(repository: Path, *args: str) -> str:
    environment = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "ICODE test",
        "GIT_AUTHOR_EMAIL": "icode-test@example.invalid",
        "GIT_COMMITTER_NAME": "ICODE test",
        "GIT_COMMITTER_EMAIL": "icode-test@example.invalid",
    }
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result.stdout.strip()


@unittest.skipUnless(os.name == "posix", "R2.4 当前仅验证 POSIX 分层 worktree")
class TestGitWorkspaceIdentityVerification(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "source"
        self.repository.mkdir()
        _git(self.repository, "init", "--initial-branch=main")
        (self.repository / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        _git(self.repository, "add", "tracked.txt")
        _git(self.repository, "commit", "-m", "baseline")
        self.manager = WorkspaceManager(
            self.repository,
            self.root / "data",
            "git-broker-test",
            isolate_git_metadata=True,
        )
        self.session = self.manager.open("ticket-1", "run-1")
        self.addCleanup(self.session.lease.release)

    def test_accepts_intact_manager_identity_and_returns_only_git_roots(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)

        layout = verify_git_workspace_identity(identity)

        self.assertEqual(layout.worktree_root, identity.code_root)
        self.assertEqual(layout.git_dir, identity.git_dir)
        self.assertEqual(layout.common_dir, identity.common_dir)
        self.assertEqual(
            tuple(root.path for root in layout.metadata_roots),
            (identity.checkout_root / ".git", identity.git_dir, identity.common_dir),
        )
        snapshots = {item.path: item for item in identity.filesystem_identities}
        for claim in layout.metadata_roots:
            snapshot = snapshots[claim.path]
            self.assertEqual(
                (claim.device, claim.inode), (snapshot.device, snapshot.inode)
            )

    def test_rejects_changed_git_pointer(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        pointer = identity.checkout_root / ".git"
        pointer.write_text("gitdir: /tmp/not-this-worktree\n", encoding="ascii")

        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(identity)


    def test_rejects_changed_revision_or_ownership_marker(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        head_path = identity.git_dir / "HEAD"
        original_head = head_path.read_bytes()
        head_path.write_text("0" * 40 + "\n", encoding="ascii")
        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(identity)
        head_path.write_bytes(original_head)

        (identity.git_dir / "icode-workspace-identity").write_text(
            "replaced-token", encoding="ascii"
        )
        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(identity)

    def test_rejects_changed_common_directory_pointer(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        common_pointer = identity.git_dir / "commondir"
        original = common_pointer.read_bytes()
        common_pointer.write_text("../not-this-repository\n", encoding="ascii")
        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(identity)
        common_pointer.write_bytes(original)

    def test_rejects_path_escape_and_missing_identity(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        escaped = replace(identity, source_relative_path=Path("../../outside"))
        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(escaped)
        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(None)

    def test_rejects_symlinked_git_pointer(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        pointer = identity.checkout_root / ".git"
        pointer.unlink()
        pointer.symlink_to(identity.git_dir / "HEAD")

        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(identity)

    def test_rejects_symlinked_worktree_git_directory(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        original = identity.git_dir
        moved = original.with_name(original.name + "-real")
        original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)

        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(identity)

    def test_rejects_same_path_metadata_directory_replacement(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        original = identity.git_dir
        moved = original.with_name(original.name + "-old")
        original.rename(moved)
        original.mkdir()
        for name in ("commondir", "HEAD", "icode-workspace-identity"):
            (original / name).write_bytes((moved / name).read_bytes())

        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(identity)

    def test_rejects_same_content_metadata_file_replacement(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        head = identity.git_dir / "HEAD"
        backup = identity.git_dir / "HEAD-original"
        contents = head.read_bytes()
        head.rename(backup)
        head.write_bytes(contents)

        with self.assertRaises(GitStatusUnavailable):
            verify_git_workspace_identity(identity)


@unittest.skipUnless(
    sys.platform.startswith("linux")
    and shutil.which("cc")
    and Path("/usr/bin/git").is_file(),
    "需要 Linux Landlock、C 编译器和系统 Git",
)
class TestGitStatusBrokerExecution(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "source"
        self.repository.mkdir()
        _git(self.repository, "init", "--initial-branch=main")
        (self.repository / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        _git(self.repository, "add", "tracked.txt")
        _git(self.repository, "commit", "-m", "baseline")
        self.manager = WorkspaceManager(
            self.repository,
            self.root / "data",
            "git-status-broker-test",
            isolate_git_metadata=True,
        )
        self.session = self.manager.open("ticket-1", "run-1")
        self.addCleanup(self.session.lease.release)

        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        self.helper = self.root / "icode-landlock"
        build = subprocess.run(
            [
                shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                "-Werror", str(source), "-o", str(self.helper),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        self.manifest = self.root / "icode-landlock.sha256"
        self.manifest.write_text(
            hashlib.sha256(self.helper.read_bytes()).hexdigest() + "\n",
            encoding="ascii",
        )
        self.sandbox = LandlockSandbox(
            helper=str(self.helper), manifest=str(self.manifest)
        )

    def _status(self):
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        return execute_git_status(
            identity,
            sandbox=self.sandbox,
            policy=self.session.policy(
                "review", wall_timeout_seconds=10, output_limit_bytes=1024 * 1024
            ),
        )

    def test_status_reports_only_the_task_worktree_and_preserves_index(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        index = identity.git_dir / "index"
        index_before = index.read_bytes()
        (self.session.workspace_root / "tracked.txt").write_text(
            "modified\n", encoding="utf-8"
        )
        (self.session.workspace_root / "new file.txt").write_text(
            "new\n", encoding="utf-8"
        )

        entries = self._status()

        self.assertEqual(
            {entry.path for entry in entries},
            {b"tracked.txt", b"new file.txt"},
        )
        self.assertEqual(index.read_bytes(), index_before)
        self.assertEqual(
            (self.repository / "tracked.txt").read_text(encoding="utf-8"),
            "baseline\n",
        )

    def test_malicious_fsmonitor_and_external_diff_are_not_executed(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        marker = self.session.workspace_root / "helper-was-run"
        fsmonitor = self.session.workspace_root / "fake-fsmonitor"
        fsmonitor.write_text(
            f"#!/bin/sh\ntouch {marker}\nexit 0\n", encoding="utf-8"
        )
        fsmonitor.chmod(0o755)
        _git(self.repository, "config", "core.fsmonitor", str(fsmonitor))
        _git(self.repository, "config", "diff.external", str(fsmonitor))
        (self.session.workspace_root / "tracked.txt").write_text(
            "modified\n", encoding="utf-8"
        )

        entries = self._status()

        self.assertTrue(entries)
        self.assertFalse(marker.exists())

    def test_configured_clean_filter_is_rejected_without_execution(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        (self.session.workspace_root / ".gitattributes").write_text(
            "tracked.txt filter=hostile\n", encoding="ascii"
        )
        (self.session.workspace_root / "tracked.txt").write_text(
            "modified\n", encoding="utf-8"
        )
        index = identity.git_dir / "index"
        index_before = index.read_bytes()

        for scope, hook in (("--local", "clean"), ("--local", "process"),
                            ("--worktree", "clean")):
            with self.subTest(scope=scope, hook=hook):
                marker = self.session.workspace_root / f"{hook}-filter-was-run"
                filter_script = self.session.workspace_root / f"fake-{hook}-filter"
                filter_script.write_text(
                    f"#!/bin/sh\ntouch {marker}\nexec /bin/cat\n", encoding="utf-8"
                )
                filter_script.chmod(0o755)
                if scope == "--worktree":
                    _git(self.repository, "config", "extensions.worktreeConfig", "true")
                config_key = f"filter.hostile.{hook}"
                config = subprocess.run(
                    ["/usr/bin/git", "--git-dir", str(identity.git_dir),
                     "--work-tree", str(identity.workspace_root), "config", scope,
                     config_key, str(filter_script)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(config.returncode, 0, config.stderr)
                if scope == "--local" and hook == "clean":
                    raw_environment = {
                        "PATH": "/usr/bin:/bin",
                        "HOME": str(self.root),
                        "GIT_CONFIG_GLOBAL": os.devnull,
                        "GIT_CONFIG_SYSTEM": os.devnull,
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_OPTIONAL_LOCKS": "0",
                        "GIT_TERMINAL_PROMPT": "0",
                        "GIT_PAGER": "cat",
                    }
                    raw_status = subprocess.run(
                        [
                            "/usr/bin/git", "--git-dir", str(identity.git_dir),
                            "--work-tree", str(identity.workspace_root),
                            "-c", "core.fsmonitor=false", "--no-optional-locks",
                            "status", "--porcelain=v2", "-z", "--no-branch", "--",
                        ],
                        cwd=identity.workspace_root,
                        env=raw_environment,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(raw_status.returncode, 0, raw_status.stderr)
                    self.assertTrue(marker.exists(), "Git clean filter probe did not trigger")
                    marker.unlink()
                with self.assertRaises(GitStatusUnavailable):
                    self._status()
                self.assertFalse(marker.exists())
                unset = subprocess.run(
                    ["/usr/bin/git", "--git-dir", str(identity.git_dir),
                     "--work-tree", str(identity.workspace_root), "config", scope,
                     "--unset", config_key],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(unset.returncode, 0, unset.stderr)

        self.assertEqual(index.read_bytes(), index_before)

    def test_gitlink_is_rejected_without_entering_submodule(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        nested = self.session.workspace_root / "module"
        nested.mkdir()
        _git(nested, "init", "--initial-branch=main")
        (nested / "nested.txt").write_text("nested\n", encoding="utf-8")
        _git(nested, "add", "nested.txt")
        _git(nested, "commit", "-m", "nested baseline")
        marker = nested / "nested-fsmonitor-was-run"
        fsmonitor = nested / "nested-fsmonitor"
        fsmonitor.write_text(
            f"#!/bin/sh\ntouch {marker}\nexit 0\n", encoding="utf-8"
        )
        fsmonitor.chmod(0o755)
        _git(nested, "config", "core.fsmonitor", str(fsmonitor))
        nested_oid = _git(nested, "rev-parse", "HEAD")
        indexed_gitlink = subprocess.run(
            [
                "/usr/bin/git", "--git-dir", str(identity.git_dir),
                "--work-tree", str(identity.workspace_root), "update-index", "--add",
                "--cacheinfo", f"160000,{nested_oid},module",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(indexed_gitlink.returncode, 0, indexed_gitlink.stderr)

        with self.assertRaisesRegex(GitStatusUnavailable, "submodules_unsupported"):
            self._status()

        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
