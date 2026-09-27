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
from unittest.mock import patch

from icode.execution_broker import ExecutionResult
from icode.git_broker import (
    GitStatusUnavailable,
    execute_policy_command,
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

    def test_status_command_does_not_install_empty_external_diff_override(self) -> None:
        commands: list[list[str]] = []

        def successful_or_absent(*args, **kwargs) -> ExecutionResult:
            command = args[0]
            commands.append(command)
            exit_code = 1 if len(commands) <= 2 else 0
            return ExecutionResult(
                exit_code=exit_code,
                output="",
                output_bytes=0,
                error=None,
                output_truncated=False,
                cleanup_ok=True,
                cleanup_errno=None,
                raw_output=b"",
            )

        with patch(
            "icode.git_broker.execute_policy_command",
            side_effect=successful_or_absent,
        ):
            entries = self._status()

        self.assertEqual(entries, ())
        self.assertEqual(len(commands), 4)
        self.assertFalse(
            any("diff.external=" in argument for command in commands for argument in command)
        )
        arguments = [argument for command in commands for argument in command]
        self.assertIn("core.fsmonitor=", arguments)
        self.assertNotIn("core.fsmonitor=false", arguments)

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

    def test_helper_rejects_metadata_inode_replaced_after_python_recheck(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        pointer = identity.checkout_root / ".git"
        displaced_pointer = identity.checkout_root / ".git.identity-race-backup"
        original_bytes = pointer.read_bytes()
        original_execute = execute_policy_command
        helper_results: list[ExecutionResult] = []
        replaced = False

        def replace_pointer_before_status(argv: list[str], **kwargs) -> ExecutionResult:
            nonlocal replaced
            if "--porcelain=v2" not in argv:
                return original_execute(argv, **kwargs)

            # execute_git_status has already verified the manager-issued
            # identity and LandlockSandbox has serialized its original inode
            # claim into argv. Replace that path immediately before the native
            # helper opens it, then restore it even if launch or cleanup fails.
            pointer.rename(displaced_pointer)
            pointer.write_bytes(original_bytes)
            replaced = True
            try:
                result = original_execute(argv, **kwargs)
                helper_results.append(result)
                return result
            finally:
                pointer.unlink(missing_ok=True)
                displaced_pointer.rename(pointer)

        with patch(
            "icode.git_broker.execute_policy_command",
            side_effect=replace_pointer_before_status,
        ):
            with self.assertRaisesRegex(
                GitStatusUnavailable, "status_execution_failed"
            ):
                self._status()

        self.assertTrue(replaced, "the replacement must occur after Python recheck")
        self.assertEqual(len(helper_results), 1)
        self.assertEqual(helper_results[0].exit_code, 1)
        self.assertIn(
            "metadata root identity changed", helper_results[0].output
        )
        self.assertTrue(helper_results[0].cleanup_ok)
        self.assertTrue(
            verify_git_workspace_identity(identity).metadata_roots,
            "the original metadata identity must be restored after the probe",
        )

    def test_head_content_drift_during_status_discards_the_result(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        head = identity.git_dir / "HEAD"
        original_head = head.read_bytes()
        original_execute = execute_policy_command
        changed = False

        def change_head_after_status(argv: list[str], **kwargs) -> ExecutionResult:
            nonlocal changed
            result = original_execute(argv, **kwargs)
            if "--porcelain=v2" in argv:
                head.write_bytes(b"0" * len(identity.revision) + b"\n")
                changed = True
            return result

        try:
            with patch(
                "icode.git_broker.execute_policy_command",
                side_effect=change_head_after_status,
            ):
                with self.assertRaisesRegex(
                    GitStatusUnavailable, "revision_mismatch"
                ):
                    self._status()
        finally:
            head.write_bytes(original_head)

        self.assertTrue(changed, "the HEAD rewrite must happen during status")
        self.assertTrue(
            verify_git_workspace_identity(identity).metadata_roots,
            "the manager-owned HEAD content must be restored after the probe",
        )

    def test_all_status_subcommands_share_one_wall_clock_deadline(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        elapsed = [0.0]
        calls: list[tuple[list[str], float]] = []

        def simulated_monotonic() -> float:
            return elapsed[0]

        def simulated_query(argv: list[str], **kwargs) -> ExecutionResult:
            calls.append((argv, kwargs["timeout"]))
            if "--get-regexp" in argv or "--get" in argv:
                exit_code = 1
            elif "ls-files" in argv:
                exit_code = 0
            else:
                exit_code = 0
            elapsed[0] += 0.4
            return ExecutionResult(
                exit_code=exit_code,
                output="",
                output_bytes=0,
                error=None,
                output_truncated=False,
                cleanup_ok=True,
                cleanup_errno=None,
                raw_output=b"",
            )

        with patch("icode.git_broker.monotonic", side_effect=simulated_monotonic):
            with patch(
                "icode.git_broker.execute_policy_command",
                side_effect=simulated_query,
            ):
                with self.assertRaisesRegex(
                    GitStatusUnavailable, "status_timeout"
                ):
                    execute_git_status(
                        identity,
                        sandbox=self.sandbox,
                        policy=self.session.policy(
                            "review", wall_timeout_seconds=10,
                            output_limit_bytes=1024 * 1024,
                        ),
                        timeout=1,
                    )

        self.assertEqual(len(calls), 3)
        self.assertAlmostEqual(calls[0][1], 1.0)
        self.assertAlmostEqual(calls[1][1], 0.6)
        self.assertAlmostEqual(calls[2][1], 0.2)

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
                            "-c", "core.fsmonitor=", "--no-optional-locks",
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

    def test_config_added_after_preflight_cannot_launch_a_filter_helper(self) -> None:
        identity = self.session.git_status_identity
        self.assertIsNotNone(identity)
        (self.session.workspace_root / ".gitattributes").write_text(
            "tracked.txt filter=late\n", encoding="ascii"
        )
        (self.session.workspace_root / "tracked.txt").write_text(
            "modified\n", encoding="utf-8"
        )
        filter_command = (
            "/usr/bin/python3 -c \"import sys;"
            "sys.stderr.write('ICODE_LATE_FILTER_EXECUTED\\\\n');"
            "sys.stdout.write(sys.stdin.read())\""
        )
        _git(self.repository, "config", "filter.late.clean", filter_command)
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
                "--no-optional-locks", "status", "--porcelain=v2", "-z",
                "--no-branch", "--",
            ],
            cwd=identity.workspace_root,
            env=raw_environment,
            capture_output=True,
            check=False,
        )
        self.assertEqual(raw_status.returncode, 0, raw_status.stderr)
        self.assertIn(b"ICODE_LATE_FILTER_EXECUTED", raw_status.stderr)
        _git(self.repository, "config", "--unset", "filter.late.clean")

        injected = False
        results: list[ExecutionResult] = []

        def inject_configuration_before_status(argv: list[str], **kwargs) -> ExecutionResult:
            nonlocal injected
            if not injected and "--porcelain=v2" in argv:
                configured = subprocess.run(
                    [
                        "/usr/bin/git", "--git-dir", str(identity.git_dir),
                        "--work-tree", str(identity.workspace_root), "config", "--local",
                        "filter.late.clean", filter_command,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if configured.returncode != 0:
                    raise AssertionError(configured.stderr)
                injected = True
            result = execute_policy_command(argv, **kwargs)
            results.append(result)
            return result

        with patch(
            "icode.git_broker.execute_policy_command",
            side_effect=inject_configuration_before_status,
        ):
            with self.assertRaises(GitStatusUnavailable):
                self._status()

        self.assertTrue(injected, "the hostile config must arrive after preflight")
        self.assertTrue(results, "Git subprocess results should be captured")
        self.assertNotIn(
            b"ICODE_LATE_FILTER_EXECUTED\n",
            b"".join(result.raw_output for result in results),
            "the fixed status query must not launch a late-configured helper",
        )

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
