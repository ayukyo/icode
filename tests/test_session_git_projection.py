from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from icode import runner, workspace_snapshot
from icode.workspace import WorkspaceError, WorkspaceManager


class TestSessionGitProjection(unittest.TestCase):
    def fixture(
        self, *, object_format="sha1", split=True, extra_code_git=False,
        source_subdir=False, snapshot=False, extra_unrelated=False,
    ):
        if os.name != "posix":
            self.skipTest("requires real POSIX split Git sessions")
        temporary = tempfile.TemporaryDirectory(prefix="icode-session-git-")
        self.addCleanup(temporary.cleanup)
        owned = Path(temporary.name).resolve()
        source = owned / "source"
        source.mkdir()
        (source / "changed.py").write_text("value = 0\n", encoding="utf-8")
        (source / "sub").mkdir()
        (source / "sub" / "part.py").write_text("part = 1\n", encoding="utf-8")
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("GIT_")}
        environment.update({
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "ICODE fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "ICODE fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        })

        def git(*arguments):
            return subprocess.run(
                ["git", "-C", str(source), *arguments], check=True,
                capture_output=True, text=True, encoding="utf-8",
                timeout=15, env=environment,
            ).stdout.strip()

        revision = tree = ""
        if not snapshot:
            try:
                git("init", "-q", f"--object-format={object_format}")
            except subprocess.CalledProcessError as exc:
                if object_format == "sha256" and (
                    "unknown option" in exc.stderr
                    or "unknown hash algorithm" in exc.stderr
                    or "unsupported hash algorithm" in exc.stderr
                ):
                    self.skipTest("installed Git does not support sha256")
                raise
            git("add", ".")
            git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "baseline")
            revision, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        manager_source = source / "sub" if source_subdir else source
        manager = WorkspaceManager(
            manager_source, owned / "data", "session-git", isolate_git_metadata=split,
        )
        session = manager.open("SESSION-GIT", "session-git-run")
        self.addCleanup(session.close)
        if extra_code_git or extra_unrelated:
            extra = []
            if extra_code_git:
                extra.append(session.workspace_root / ".git")
            if extra_unrelated:
                extra.append(owned / "unrelated-protected")
            session.close()
            manager = WorkspaceManager(
                manager_source, owned / "data", "session-git",
                isolate_git_metadata=split, extra_protected_paths=tuple(extra),
            )
            session = manager.open("SESSION-GIT", "session-git-run")
            self.addCleanup(session.close)
        return session, source, revision, tree

    def state(self, session, workspace=None):
        root = session.workspace_root if workspace is None else workspace
        kwargs = ({"workspace_session": session}
                  if "workspace_session" in inspect.signature(runner._read_task_git_state).parameters
                  else {})
        return runner._read_task_git_state(root, **kwargs)

    def tree(self, session, revision, workspace=None, object_format=None):
        root = session.workspace_root if workspace is None else workspace
        kwargs = {"object_format": object_format}
        if "workspace_session" in inspect.signature(runner._capture_task_git_tree_oid).parameters:
            kwargs["workspace_session"] = session
        return runner._capture_task_git_tree_oid(root, revision, **kwargs)

    def rejected(self, session, revision, workspace=None,
                 status="session_git_identity_unavailable"):
        with self.assertRaisesRegex(ValueError, "^workspace_git_identity_unavailable$"):
            self.state(session, workspace)
        self.assertEqual(self.tree(session, revision, workspace), ("", status))

    def test_real_split_dot_matches_commit_tree(self):
        self.assertTrue(inspect.getsource(type(self)).lstrip().startswith(
            "class TestSessionGitProjection("
        ))
        session, _source, revision, tree = self.fixture()
        self.assertEqual(self.state(session), ("sha1", revision))
        oid, status = self.tree(session, revision)
        self.assertEqual(status, "captured")
        self.assertEqual(oid, tree)
        self.assertIn("workspace_session", inspect.signature(runner._read_task_git_state).parameters)
        self.assertIn("workspace_session", inspect.signature(runner._capture_task_git_tree_oid).parameters)

    def test_real_sha256_and_caller_format_base_rejection(self):
        session, _source, revision, tree = self.fixture(object_format="sha256")
        self.assertEqual(self.state(session), ("sha256", revision))
        self.assertEqual(len(revision), 64)
        self.assertEqual(self.tree(session, revision), (tree, "captured"))
        self.assertEqual(len(tree), 64)
        for base, fmt in (("", None), ("0" * 64, None), (revision, "sha1")):
            with self.subTest(base=base, object_format=fmt):
                self.assertEqual(self.tree(session, base, object_format=fmt),
                                 ("", "session_git_identity_unavailable"))

    def test_paths_subtrees_and_other_session_rejected(self):
        session, _source, revision, _tree = self.fixture()
        root = session.workspace_root
        other, _source2, _revision2, _tree2 = self.fixture()
        for path in (Path("relative"), Path(root.anchor), root / ".." / "code",
                     root.parent, root / "sub", root.parent / "sibling",
                     other.workspace_root):
            with self.subTest(path=path):
                self.rejected(session, revision, path)
        session.git_status_identity = replace(
            session.git_status_identity, source_relative_path=Path("sub"),
        )
        self.rejected(session, revision, status="workspace_shape_unsupported")
        sub_session, _source, revision, _tree = self.fixture(source_subdir=True)
        self.rejected(sub_session, revision, status="workspace_shape_unsupported")

    def test_identity_fields_missing_duplicate_device_inode_token_rejected(self):
        session, _source, revision, _tree = self.fixture()
        identity = session.git_status_identity
        claims = identity.filesystem_identities
        cases = (
            None, object(), replace(identity, filesystem_identities=()),
            replace(identity, source_relative_path="."),
            replace(identity, source_relative_path=None),
            replace(identity, filesystem_identities=claims + (claims[0],)),
            replace(identity, identity_token="0" * 32),
            replace(identity, filesystem_identities=(replace(claims[0], inode=claims[0].inode + 1), *claims[1:])),
            replace(identity, filesystem_identities=(replace(claims[0], device=claims[0].device + 1), *claims[1:])),
        )
        for index, invalid in enumerate(cases):
            with self.subTest(case=index):
                session.git_status_identity = invalid
                self.rejected(session, revision)

    def test_metadata_real_rewrites_replacements_and_symlinks_rejected(self):
        for change in ("pointer", "commondir", "HEAD", "ownership", "head-replace",
                       "pointer-symlink", "directory-replace"):
            with self.subTest(change=change):
                session, _source, revision, _tree = self.fixture()
                identity = session.git_status_identity
                pointer = identity.checkout_root / ".git"
                if change == "pointer":
                    pointer.write_text("gitdir: /untrusted\n", encoding="ascii")
                elif change in ("commondir", "HEAD", "ownership"):
                    name = "icode-workspace-identity" if change == "ownership" else change
                    (identity.git_dir / name).write_text("0" * 40 + "\n", encoding="ascii")
                elif change == "head-replace":
                    head = identity.git_dir / "HEAD"
                    contents = head.read_bytes()
                    head.rename(head.with_name("HEAD-old"))
                    head.write_bytes(contents)
                elif change == "pointer-symlink":
                    pointer.unlink()
                    pointer.symlink_to(identity.git_dir / "HEAD")
                else:
                    old = identity.git_dir.with_name(identity.git_dir.name + "-old")
                    identity.git_dir.rename(old)
                    identity.git_dir.mkdir()
                    for name in ("commondir", "HEAD", "icode-workspace-identity"):
                        (identity.git_dir / name).write_bytes((old / name).read_bytes())
                self.rejected(session, revision)

    def test_code_git_all_types_and_lstat_error_rejected_before_git_tree(self):
        for kind in ("file", "directory", "symlink", "dangling", "fifo", "lstat-error"):
            with self.subTest(kind=kind):
                session, _source, revision, _tree = self.fixture()
                code_git = session.workspace_root / ".git"
                identity = session.git_status_identity
                if kind == "file":
                    code_git.write_text(f"gitdir: {identity.git_dir}\n", encoding="utf-8")
                elif kind == "directory":
                    code_git.mkdir()
                elif kind in ("symlink", "dangling"):
                    code_git.symlink_to(identity.git_dir if kind == "symlink" else code_git.parent / "missing")
                elif kind == "fifo":
                    os.mkfifo(code_git)
                real_lstat = Path.lstat

                def lstat(path, *args, **kwargs):
                    if kind == "lstat-error" and path == code_git:
                        raise PermissionError("fixture denied lstat")
                    return real_lstat(path, *args, **kwargs)

                with patch("pathlib.Path.lstat", lstat), \
                        patch("icode.workspace.read_git_repository_state") as git_state, \
                        patch("icode.runner._worktree_git_tree_oid") as walker:
                    self.rejected(session, revision)
                    git_state.assert_not_called()
                    walker.assert_not_called()

    def test_missing_split_identity_same_head_injection_extra_protection_never_falls_back(self):
        for extra in (False, True):
            for inject in (False, True):
                with self.subTest(extra=extra, inject=inject):
                    session, _source, revision, _tree = self.fixture(extra_code_git=extra)
                    code_git = session.workspace_root / ".git"
                    self.assertEqual(code_git in session.protected_paths, extra)
                    if inject:
                        code_git.write_text(f"gitdir: {session.git_status_identity.git_dir}\n", encoding="utf-8")
                    session.git_status_identity = None
                    with patch("icode.workspace.read_git_repository_state") as git_state, \
                            patch("icode.runner._worktree_git_tree_oid") as walker:
                        self.rejected(session, revision)
                        git_state.assert_not_called()
                        walker.assert_not_called()

    def test_session_field_layout_and_protection_validation(self):
        session, _source, revision, _tree = self.fixture(split=False)
        cases = (
            replace(session, kind="unknown"), replace(session, workspace_root=Path("relative")),
            replace(session, protected_paths=list(session.protected_paths)),
            replace(session, protected_paths=(Path("relative"),)),
            replace(session, manifest_path=Path("relative")),
            replace(session, manifest_path=session.manifest_path.with_name("metadata.json")),
            replace(session, runtime_root=session.runtime_root.with_name("wrong-runtime")),
            replace(session, receipts_root=session.receipts_root.with_name("wrong-receipts")),
            replace(session, protected_paths=()), object(),
        )
        snapshot, _source, _rev, _tree = self.fixture(snapshot=True)
        split, _source, _rev, _tree = self.fixture()
        cases += (replace(snapshot, git_status_identity=split.git_status_identity),)
        for index, invalid in enumerate(cases):
            with self.subTest(case=index), \
                    patch("icode.workspace.read_git_repository_state") as git_state, \
                    patch("icode.runner._worktree_git_tree_oid") as walker:
                root = invalid.workspace_root if hasattr(invalid, "workspace_root") else session.workspace_root
                self.rejected(invalid, revision, root)
                git_state.assert_not_called()
                walker.assert_not_called()

    def test_capture_window_observed_identity_head_format_and_fields_drift(self):
        real_walker = runner._worktree_git_tree_oid
        for change in ("identity", "root", "kind", "HEAD", "pointer", "root-git", "format",
                       "protected", "manifest", "runtime", "receipts"):
            with self.subTest(window="tree", change=change):
                fallback = change in ("protected", "manifest", "runtime", "receipts")
                session, _source, revision, _tree = self.fixture(split=not fallback)
                root, identity = session.workspace_root, session.git_status_identity
                walked = False

                def walker(*args, **kwargs):
                    nonlocal walked
                    oid = real_walker(*args, **kwargs)
                    walked = True
                    if change == "identity":
                        session.git_status_identity = replace(identity)
                    elif change == "root":
                        session.workspace_root = root.parent
                    elif change == "kind":
                        session.kind = "snapshot"
                    elif change == "HEAD":
                        (identity.git_dir / "HEAD").write_text("0" * 40 + "\n", encoding="ascii")
                    elif change == "pointer":
                        (identity.checkout_root / ".git").write_text("gitdir: /changed\n", encoding="ascii")
                    elif change == "root-git":
                        (root / ".git").mkdir()
                    elif change == "protected":
                        session.protected_paths += (root.parent / "extra",)
                    elif change == "manifest":
                        session.manifest_path = session.manifest_path.with_name("metadata.json")
                    elif change == "runtime":
                        session.runtime_root = session.runtime_root.with_name("other")
                    elif change == "receipts":
                        session.receipts_root = session.receipts_root.with_name("other")
                    return oid

                from icode.workspace import read_git_repository_state

                def actual_state(*args, **kwargs):
                    result = read_git_repository_state(*args, **kwargs)
                    return ("sha256", result[1]) if walked and change == "format" else result

                with patch("icode.runner._worktree_git_tree_oid", walker), \
                        patch("icode.workspace.read_git_repository_state", actual_state):
                    self.assertEqual(self.tree(session, revision, root),
                                     ("", "session_git_identity_unavailable"))
                self.assertTrue(walked)
        for change in ("HEAD", "identity", "protected"):
            with self.subTest(window="state", change=change):
                session, _source, revision, _tree = self.fixture()
                identity = session.git_status_identity
                from icode.workspace import read_git_repository_state

                def state_then_change(*args, **kwargs):
                    result = read_git_repository_state(*args, **kwargs)
                    if change == "HEAD":
                        (identity.git_dir / "HEAD").write_text("0" * 40 + "\n", encoding="ascii")
                    elif change == "identity":
                        session.git_status_identity = replace(identity)
                    else:
                        session.protected_paths += (session.workspace_root.parent / "extra",)
                    return result

                with patch("icode.workspace.read_git_repository_state", state_then_change):
                    with self.assertRaisesRegex(ValueError, "^workspace_git_identity_unavailable$"):
                        self.state(session)

    def test_tree_semantics_stability_and_existing_failures_preserved(self):
        session, source, revision, _tree = self.fixture()
        root = session.workspace_root
        baseline, status = self.tree(session, revision)
        self.assertEqual(status, "captured")
        (root / "changed.py").write_bytes(b"value = 2\n")
        content_oid, status = self.tree(session, revision)
        self.assertEqual(status, "captured")
        self.assertNotEqual(content_oid, baseline)
        (root / "changed.py").chmod(0o755)
        mode_oid, status = self.tree(session, revision)
        self.assertEqual(status, "captured")
        self.assertNotEqual(mode_oid, content_oid)
        target = source.parent / "outside"
        target.write_bytes(b"outside-v1")
        link = root / "link"
        link.symlink_to(target)
        link_oid, status = self.tree(session, revision)
        self.assertEqual(status, "captured")
        target.write_bytes(b"outside-v2")
        self.assertEqual(self.tree(session, revision), (link_oid, "captured"))
        link.unlink()
        link.symlink_to(source.parent / "other-target")
        self.assertNotEqual(self.tree(session, revision)[0], link_oid)
        for before, after, oid1, oid2 in (({"a": "1"}, {"a": "2"}, baseline, baseline),
                                          ({"a": "1"}, {"a": "1"}, baseline, mode_oid)):
            self.assertEqual(runner._resolve_tested_git_tree(
                before, after, oid1, "captured", oid2, "captured", "sha1", "sha1",
            ), ("", "unstable_during_test"))
        for reason in ("filesystem_changed", "workspace_unavailable", "root_tree_unavailable"):
            with self.subTest(fault_reason=reason), patch(
                "icode.runner._worktree_git_tree_oid", side_effect=runner.WorktreeTreeUnavailable(reason),
            ):
                self.assertEqual(self.tree(session, revision), ("", reason))
        nested = root / "sub" / ".git"
        nested.mkdir()
        self.assertEqual(self.tree(session, revision), ("", "nested_git_metadata"))
        nested.rmdir()
        fifo = root / "fifo"
        os.mkfifo(fifo)
        self.assertEqual(self.tree(session, revision), ("", "unsupported_filesystem_entry"))
        fifo.unlink()
        for limit, reason in (("_MAX_GIT_TREE_ENTRIES", "worktree_too_large"),
                              ("_MAX_GIT_TREE_BYTES", "worktree_too_large"),
                              ("_MAX_GIT_TREE_DEPTH", "worktree_too_deep")):
            with self.subTest(limit=limit), patch.object(workspace_snapshot, limit, 0):
                self.assertEqual(self.tree(session, revision), ("", reason))

    def test_ordinary_snapshot_non_git_and_exact_legacy_call_shapes(self):
        for extra in (False, True):
            with self.subTest(ordinary_extra=extra):
                session, source, revision, tree = self.fixture(split=False, extra_unrelated=extra)
                self.assertIsNone(session.git_status_identity)
                self.assertIn(session.workspace_root / ".git", session.protected_paths)
                self.assertEqual(self.state(session), ("sha1", revision))
                self.assertEqual(self.tree(session, revision), (tree, "captured"))
                self.assertEqual(runner._read_task_git_state(source), ("sha1", revision))
                self.assertEqual(runner._capture_task_git_tree_oid(source, revision), (tree, "captured"))
                self.assertEqual(runner._capture_task_git_tree_oid(source / "sub", revision),
                                 ("", "workspace_not_repository_root"))
                original_state, original_tree = runner._read_task_git_state, runner._capture_task_git_tree_oid
                with patch("icode.runner._read_task_git_state", wraps=original_state) as state_calls:
                    self.assertEqual(original_state(session.workspace_root, workspace_session=session), ("sha1", revision))
                    self.assertEqual(state_calls.call_args.args, (session.workspace_root,))
                    self.assertEqual(state_calls.call_args.kwargs, {})
                with patch("icode.runner._capture_task_git_tree_oid", wraps=original_tree) as tree_calls:
                    self.assertEqual(original_tree(session.workspace_root, revision, object_format="sha1",
                                                   workspace_session=session), (tree, "captured"))
                    self.assertEqual(tree_calls.call_args.args, (session.workspace_root, revision))
                    self.assertEqual(tree_calls.call_args.kwargs, {"object_format": "sha1"})
                with patch("icode.workspace_snapshot.hashlib.new",
                           side_effect=ValueError("walker digest unavailable")):
                    with self.assertRaisesRegex(ValueError, "^walker digest unavailable$"):
                        runner._capture_task_git_tree_oid(
                            session.workspace_root, revision, object_format="sha1",
                        )
                    with self.assertRaisesRegex(ValueError, "^walker digest unavailable$"):
                        self.tree(session, revision, object_format="sha1")
        snapshot, source, _revision, _tree = self.fixture(snapshot=True)
        self.assertEqual(self.state(snapshot), ("", ""))
        self.assertEqual(self.tree(snapshot, ""), ("", "not_git_workspace"))
        with patch("icode.workspace.read_git_repository_state", side_effect=WorkspaceError("not git")):
            self.assertEqual(runner._read_task_git_state(source), ("", ""))
        with patch("icode.workspace.read_git_repository_state", side_effect=OSError("legacy error")):
            with self.assertRaisesRegex(OSError, "legacy error"):
                runner._read_task_git_state(source)
        with patch("icode.workspace.read_git_repository_state", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.state(snapshot)

    def test_all_session_callers_pass_same_session_and_legacy_call_shapes_stay_exact(self):
        session, _source, revision, _tree = self.fixture()
        callers = (
            (runner.run_contract_step, 1, 0, "workspace_session"),
            (runner.resume_contract_step, 1, 0, "workspace_session"),
            (runner._contract_engineering_gate, 3, 3, "workspace_session"),
            (runner._contract_engineering_binding_error, 1, 1, "session"),
            (runner._run_task_reviewer, 0, 1, "workspace_session"),
        )
        symbols = {"_read_task_git_state", "_capture_task_git_tree_oid"}
        for function, state_count, tree_count, session_name in callers:
            with self.subTest(caller=function.__name__):
                body = ast.parse(textwrap.dedent(inspect.getsource(function)))
                calls = [node for node in ast.walk(body) if isinstance(node, ast.Call)
                         and isinstance(node.func, ast.Name) and node.func.id in symbols]
                self.assertEqual(sum(call.func.id == "_read_task_git_state" for call in calls), state_count)
                self.assertEqual(sum(call.func.id == "_capture_task_git_tree_oid" for call in calls), tree_count)
                assignments = [node for node in ast.walk(body) if isinstance(node, ast.Assign)
                               and any(isinstance(target, ast.Name) and target.id == "git_session_kwargs"
                                       for target in node.targets)]
                self.assertEqual(len(assignments), 1)
                assignment = assignments[0]
                self.assertIn(session_name, {node.id for node in ast.walk(assignment.value)
                                            if isinstance(node, ast.Name)})
                for supplied_session in (session, None):
                    recorded = []

                    def capture(*args, **kwargs):
                        recorded.append((args, kwargs))
                        return "sha1", revision

                    namespace = {
                        session_name: supplied_session, "workspace": session.workspace_root,
                        "before_head": revision, "before_format": "sha1", "after_format": "sha1",
                        "current_format": "sha1", "object_format": "sha1",
                        "evidence": SimpleNamespace(base_commit_sha=revision, git_object_format="sha1"),
                        "_read_task_git_state": capture, "_capture_task_git_tree_oid": capture,
                    }
                    # Observe only the assignment/call expressions, not admission or recovery.
                    module = ast.fix_missing_locations(ast.Module(body=[assignment], type_ignores=[]))
                    exec(compile(module, "<session-caller-assignment>", "exec"), namespace)
                    expected = {} if supplied_session is None else {"workspace_session": session}
                    self.assertEqual(namespace["git_session_kwargs"], expected)
                    for call in calls:
                        expansions = [keyword for keyword in call.keywords if keyword.arg is None]
                        self.assertEqual(len(expansions), 1)
                        self.assertIsInstance(expansions[0].value, ast.Name)
                        self.assertEqual(expansions[0].value.id, "git_session_kwargs")
                        expression = ast.fix_missing_locations(ast.Expression(body=call))
                        eval(compile(expression, "<session-caller-call>", "eval"), namespace)
                        args, kwargs = recorded[-1]
                        tree_call = call.func.id == "_capture_task_git_tree_oid"
                        self.assertEqual(args, (session.workspace_root, revision) if tree_call
                                         else (session.workspace_root,))
                        self.assertEqual(kwargs, dict(expected, object_format="sha1") if tree_call else expected)
                        self.assertEqual("workspace_session" in kwargs, supplied_session is not None)
                        if supplied_session is not None:
                            self.assertIs(kwargs["workspace_session"], session)
        for function, state_count, tree_count in (
            (runner._measure_task_verification, 2, 2), (runner.run_task, 1, 0),
        ):
            with self.subTest(legacy_caller=function.__name__):
                body = ast.parse(textwrap.dedent(inspect.getsource(function)))
                calls = [node for node in ast.walk(body) if isinstance(node, ast.Call)
                         and isinstance(node.func, ast.Name) and node.func.id in symbols]
                self.assertEqual(sum(call.func.id == "_read_task_git_state" for call in calls), state_count)
                self.assertEqual(sum(call.func.id == "_capture_task_git_tree_oid" for call in calls), tree_count)
                for call in calls:
                    tree_call = call.func.id == "_capture_task_git_tree_oid"
                    self.assertEqual(len(call.args), 2 if tree_call else 1)
                    self.assertIsInstance(call.args[0], ast.Name)
                    self.assertEqual(call.args[0].id, "workspace")
                    self.assertEqual([keyword.arg for keyword in call.keywords],
                                     ["object_format"] if tree_call else [])
