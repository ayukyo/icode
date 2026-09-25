from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from dataclasses import replace

from icode.git_broker import GitStatusUnavailable, verify_git_workspace_identity
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


if __name__ == "__main__":
    unittest.main()
