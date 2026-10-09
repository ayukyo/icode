# 可信会话 Git 状态与树投影 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实 manager 的分离 dot-root 会话获得同源、前后重核的 Git 状态与完整代码树投影，不改变无 session 行为或原生准入。

**Architecture:** runner 内部共用可信 session/layout 验证，复用现有 no-follow Git 身份验证及 bounded 纯文件 walker；state 与 tree 成对传入同一 session。先完成核心接口，再接全 contract/Reviewer/最后 CP 边界，最后加入精确 POSIX CI 选择并验收。

**Tech Stack:** Python 标准库 unittest、现有 WorkspaceManager/GitWorkspaceIdentity/ControlPlane、系统 Git；无新依赖或权限。

---

日期：2026-10-09。**状态：本片 Git 修复、本地软件验收及 main `923433b` 发布收尾完成；新 SHA 三条线上观察已终态 STOP，CI 仍四项 Windows 失败，不授 R2/R3 整体通过。** 获准设计 `docs/nbl/specs/2026-10-09-session-git-tree-design.md` SHA256 `cb50043d8314a8fd7793e3b4fae5d0f0171440390bc9f0866a43292911c2f679` 已由 fresh SPEC 与不同 QUALITY 分别 C0/I0/M0 审查（root 输入，不冒称计划作者审查）。基线 main `8d53670192e3e2cbfebaa0300d697fb3036308be`，vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`。下方代码保留获准计划示例；实际 fixture 返回形状及运行履历以后文为准。

用户明确要求连续实施、仅 main，不建分支/worktree；全片软件验收后才提交推送，覆盖技能的 routine 等待与每任务提交模板，但不覆盖 RED/GREEN、独立审查或安全门。本计划作者只写本文，交回 root 后 STOP，不自行调用执行技能或启动实现代理。

## 范围与文件职责

| 文件 | 本片职责 |
| --- | --- |
| `src/icode/runner.py` | 新增 session/layout 验证和成对 state/tree 路径；仅相关 caller 接线 |
| `tests/test_session_git_projection.py` | 一个真实 Git/manager 共享 fixture；状态、树、身份、布局、实际文件变化和兼容负控 |
| `tests/test_contract_engineering.py` | 复用现有工程 fixture，分离 session 接线正控、真实 Reviewer read/submit 控制 double、最后边界阻断 |
| `scripts/run_workspace_ci.py` | 新增精确 POSIX 方法 ID，保持现有 required-skip 门与 Windows 选择 |
| `tests/test_run_workspace_ci.py` | 精确加载一次、方法真实存在、平台选择、required skip 守卫 |
| 本文与 `docs/agent-landscape-live.md` | root 追加实际履历、相关上游采用/暂缓/不适配；不改冻结设计历史 |

不改 git_broker/workspace/workspace_snapshot/Native flag/vendor/measurement/result-commit/schema。无 session 的原接口调用必须保持精确参数形状；不宽化旧 doubles。split 子目录明确不支持。真实文件/Git/CP 与 model/transport double、软件与 OS/installed/模型信用分别记录。

## 统一执行环境

下列 shell 函数仅用于明确现存解释器、已有 PATH 和单并发资源上限，不安装工具、不读取 KEY、不修改全局配置：

```bash
session_git_python() {
  env PATH=/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin:/tmp/icode-sigstore-go-gwCdn3/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B "$@"
}
git branch --show-current
git rev-parse HEAD
git -C vendor/icode-skill rev-parse HEAD
git status --short
```

Expected：main/8d/vendor169；两处 root 既有 doc 元数据以及 root/其它作者拥有的设计/研究/evidence不回退、不覆盖。运行实际 command 前确认上述绝对解释器仍可用；失效则 root 选等价已存在环境并记录，不静默降级/安装。所有测试串行，编译 j1，长运行每 ≤60 秒更新。`scripts/run_workspace_ci.py` 没有 argparse/--help flag；它将位置 argv 当 unittest IDs，不能传猜测的 `--help` 或 `--only`。

## Task 1: 成对接口与真实 manager 身份/投影

**状态**

- [x] 任务完成（仅核心接口；不授 caller、全片或原生验收）

**Dependencies:** None

**Parallelizable:** No (唯一源 writer；核心接口与真实 fixture 同步，不能和测试/其它源码编辑并行)

- [x] **Step 1: 新增共享 fixture 与实际 RED 正控。**

创建 `tests/test_session_git_projection.py`，先放以下完整基础和首个正控。临时 source/data 不重叠；只操作 owned fixture，不改 main Git。`state`/`tree` 的 inspect 过渡只让旧接口得到真实基线调用，避免 unexpected keyword ERROR 冒充 RED；实现后同一 helper 自动使用新接口，最终还会强断言 signature 存在。

```python
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import tempfile
import textwrap
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from icode import runner
from icode.workspace import WorkspaceManager
from icode.workspace_snapshot import WorktreeTreeUnavailable


def git(root, *args, check=True):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                       GIT_AUTHOR_NAME="ICODE fixture", GIT_COMMITTER_NAME="ICODE fixture",
                       GIT_AUTHOR_EMAIL="fixture@example.invalid",
                       GIT_COMMITTER_EMAIL="fixture@example.invalid")
    return subprocess.run(["git", "-C", str(root), *args], check=check,
                          capture_output=True, text=True, encoding="utf-8",
                          env=environment, timeout=15)


class TestSessionGitProjection(unittest.TestCase):
    def fixture(self, *, object_format="sha1", split=True, extra_code_git=False,
                source_subdir=False, snapshot=False, extra_unrelated=False):
        if os.name != "posix":
            self.skipTest("manager split Git identity requires POSIX")
        temporary = tempfile.TemporaryDirectory(prefix="icode-session-git-")
        self.addCleanup(temporary.cleanup)
        owned = Path(temporary.name).resolve()
        source = owned / "source"
        source.mkdir()
        (source / "changed.py").write_text("value = 0\n", encoding="utf-8")
        if source_subdir:
            (source / "sub").mkdir()
            (source / "sub" / "part.py").write_text("part = 0\n", encoding="utf-8")
        revision = tree_oid = ""
        if not snapshot:
            result = git(source, "init", "-q", "--object-format=" + object_format, check=False)
            if result.returncode and object_format == "sha256":
                self.skipTest("installed Git lacks sha256 repository support")
            self.assertEqual(result.returncode, 0, result.stderr)
            git(source, "add", ".")
            git(source, "-c", "core.hooksPath=" + str(owned / "absent-hooks"),
                "commit", "-qm", "fixture baseline")
            revision = git(source, "rev-parse", "HEAD").stdout.strip()
            tree_oid = git(source, "rev-parse", "HEAD^{tree}").stdout.strip()
        manager = WorkspaceManager(source / "sub" if source_subdir else source,
                                   owned / "data", "session-git", isolate_git_metadata=split)
        session = manager.open("SESSION-GIT", "session-git-run")
        self.addCleanup(session.close)
        if extra_code_git or extra_unrelated:
            code_git = session.workspace_root / ".git"
            session.close()
            extra = (code_git,) if extra_code_git else (owned / "unrelated-protected",)
            manager = WorkspaceManager(source / "sub" if source_subdir else source,
                                       owned / "data", "session-git",
                                       isolate_git_metadata=split, extra_protected_paths=extra)
            session = manager.open("SESSION-GIT", "session-git-run")
            self.addCleanup(session.close)
        return owned, source, session, revision, tree_oid

    def state(self, workspace, session):
        kwargs = ({"workspace_session": session}
                  if "workspace_session" in inspect.signature(runner._read_task_git_state).parameters else {})
        return runner._read_task_git_state(workspace, **kwargs)

    def tree(self, workspace, revision, session, *, object_format=None):
        kwargs = ({"workspace_session": session}
                  if "workspace_session" in inspect.signature(runner._capture_task_git_tree_oid).parameters else {})
        return runner._capture_task_git_tree_oid(workspace, revision,
                                               object_format=object_format, **kwargs)

    def rejected(self, workspace, revision, session, *, tree_status="session_git_identity_unavailable"):
        with self.assertRaisesRegex(ValueError, "^workspace_git_identity_unavailable$"):
            self.state(workspace, session)
        self.assertEqual(self.tree(workspace, revision, session), ("", tree_status))

    def test_real_split_dot_matches_commit_tree(self):
        _, _, session, revision, expected = self.fixture()
        root = session.workspace_root
        self.assertEqual(self.state(root, session), ("sha1", revision))
        oid, status = self.tree(root, revision, session)
        self.assertEqual(status, "captured")
        self.assertEqual(oid, expected)
        for function in (runner._read_task_git_state, runner._capture_task_git_tree_oid):
            self.assertIn("workspace_session", inspect.signature(function).parameters)
```

- [x] **Step 2: 确认真实失败。**

```bash
session_git_python -m unittest tests.test_session_git_projection.TestSessionGitProjection.test_real_split_dot_matches_commit_tree -v
```

Expected：实际 **FAIL**（`workspace_not_repository_root != captured`），而不是 TypeError/ERROR/fixture 初始化失败；记录 full assertion、total/F/E/skip。实际非该失败先修 fixture，不改生产来遮盖。

- [x] **Step 3: 完整加入其余核心测试。**

以下方法追加同一 `TestSessionGitProjection` 类，不复制 fixture。S-01～S-09 与部分 W/C 的具体对应在末尾矩阵；sha256为独立方法，只有该环境前提可 skip，required POSIX CI 将该 skip 明确失败而非伪 PASS。

```python
    def test_real_sha256_and_caller_format_base_rejection(self):
        _, _, session, revision, expected = self.fixture(object_format="sha256")
        self.assertEqual(self.state(session.workspace_root, session), ("sha256", revision))
        self.assertEqual(len(revision), 64)
        self.assertEqual(self.tree(session.workspace_root, revision, session), (expected, "captured"))
        for base, fmt in (("", None), ("0" * 64, "sha256"), (revision, "sha1")):
            with self.subTest(base=bool(base), fmt=fmt):
                self.assertEqual(self.tree(session.workspace_root, base, session, object_format=fmt),
                                 ("", "session_git_identity_unavailable"))

    def test_paths_subtrees_and_other_session_rejected(self):
        _, _, session, revision, _ = self.fixture()
        root = session.workspace_root
        identity = session.git_status_identity
        for wrong in (Path("relative"), root / ".." / "code", root.parent,
                      root / "sub", root.with_name("sibling")):
            with self.subTest(path=str(wrong)):
                self.rejected(wrong, revision, session)
        _, _, other, _, _ = self.fixture()
        self.rejected(root, revision, other)
        session.git_status_identity = replace(identity, source_relative_path=Path("sub"))
        self.rejected(root, revision, session, tree_status="workspace_shape_unsupported")
        _, _, subtree, revision, _ = self.fixture(source_subdir=True)
        self.rejected(subtree.workspace_root, revision, subtree,
                      tree_status="workspace_shape_unsupported")

    def test_identity_fields_missing_duplicate_device_inode_token_rejected(self):
        _, _, session, revision, _ = self.fixture()
        identity = session.git_status_identity
        claims = identity.filesystem_identities
        for supplied in (None, object(), replace(identity, filesystem_identities=()),
                         replace(identity, filesystem_identities=claims + claims[:1]),
                         replace(identity, identity_token="0" * 32),
                         replace(identity, filesystem_identities=(replace(claims[0], inode=claims[0].inode + 1), *claims[1:])),
                         replace(identity, filesystem_identities=(replace(claims[0], device=claims[0].device + 1), *claims[1:]))):
            with self.subTest(identity_type=type(supplied).__name__):
                session.git_status_identity = supplied
                self.rejected(session.workspace_root, revision, session)

    def test_metadata_real_rewrites_replacements_and_symlinks_rejected(self):
        for name, kind in (("pointer", "write"), ("commondir", "write"),
                           ("HEAD", "write"), ("icode-workspace-identity", "write"),
                           ("HEAD", "replace"), ("pointer", "symlink"), ("directory", "replace")):
            with self.subTest(name=name, kind=kind):
                _, _, session, revision, _ = self.fixture()
                identity = session.git_status_identity
                target = (identity.checkout_root / ".git" if name == "pointer" else
                          identity.git_dir if name == "directory" else identity.git_dir / name)
                if kind == "write":
                    target.write_bytes(b"not-the-original-metadata\n")
                elif kind == "symlink":
                    target.unlink()
                    target.symlink_to(identity.git_dir / "HEAD")
                elif name == "directory":
                    saved = target.with_name(target.name + "-saved")
                    target.rename(saved)
                    target.mkdir()
                    for field in ("commondir", "HEAD", "icode-workspace-identity"):
                        (target / field).write_bytes((saved / field).read_bytes())
                else:
                    contents = target.read_bytes()
                    target.rename(target.with_name(target.name + "-saved"))
                    target.write_bytes(contents)
                self.rejected(session.workspace_root, revision, session)

    def test_code_git_all_types_and_lstat_error_rejected_before_git_tree(self):
        for kind in ("file", "directory", "symlink", "dangling", "fifo", "ioerror"):
            with self.subTest(kind=kind):
                _, _, session, revision, _ = self.fixture()
                root_git = session.workspace_root / ".git"
                identity = session.git_status_identity
                if kind == "file":
                    root_git.write_text("gitdir: " + str(identity.git_dir) + "\n", encoding="ascii")
                elif kind == "directory":
                    root_git.mkdir()
                elif kind in ("symlink", "dangling"):
                    root_git.symlink_to(identity.git_dir if kind == "symlink" else root_git.with_name("absent"))
                elif kind == "fifo":
                    os.mkfifo(root_git)
                original_lstat = Path.lstat
                def checked_lstat(path, *args, **kwargs):
                    if kind == "ioerror" and path == root_git:
                        raise PermissionError("fixture lstat denied")
                    return original_lstat(path, *args, **kwargs)
                with patch.object(Path, "lstat", checked_lstat), \
                     patch("icode.workspace.read_git_repository_state") as state, \
                     patch.object(runner, "_worktree_git_tree_oid") as tree:
                    self.rejected(session.workspace_root, revision, session)
                state.assert_not_called()
                tree.assert_not_called()

    def test_missing_split_identity_same_head_injection_extra_protection_never_falls_back(self):
        for extra in (False, True):
            for inject in (False, True):
                with self.subTest(extra=extra, inject=inject):
                    _, _, session, revision, _ = self.fixture(extra_code_git=extra)
                    identity = session.git_status_identity
                    code_git = session.workspace_root / ".git"
                    self.assertEqual(code_git in session.protected_paths, extra)
                    if inject:
                        code_git.write_text("gitdir: " + str(identity.git_dir) + "\n", encoding="ascii")
                    session.git_status_identity = None
                    with patch("icode.workspace.read_git_repository_state") as state, \
                         patch.object(runner, "_worktree_git_tree_oid") as tree:
                        self.rejected(session.workspace_root, revision, session)
                    state.assert_not_called()
                    tree.assert_not_called()

    def test_session_field_layout_and_protection_validation(self):
        for field, value in (("kind", "unknown"), ("workspace_root", Path("relative")),
                             ("protected_paths", []), ("protected_paths", (Path("relative"),)),
                             ("manifest_path", Path("relative")), ("runtime_root", Path("/wrong-runtime")),
                             ("receipts_root", Path("/wrong-receipts")),
                             ("manifest_path", Path("/unknown/metadata.json")), ("protected_paths", ())):
            with self.subTest(field=field, value=repr(value)):
                _, _, session, revision, _ = self.fixture(split=False)
                root = session.workspace_root
                setattr(session, field, value)
                with patch("icode.workspace.read_git_repository_state") as state, \
                     patch.object(runner, "_worktree_git_tree_oid") as tree:
                    self.rejected(root, revision, session)
                state.assert_not_called()
                tree.assert_not_called()
        _, _, session, revision, _ = self.fixture()
        self.rejected(session.workspace_root, revision, object())
        session.kind = "snapshot"
        self.rejected(session.workspace_root, revision, session)

    def test_capture_window_observed_identity_head_format_and_fields_drift(self):
        for mutation in ("identity", "root", "kind", "HEAD", "pointer", "format", "rootgit"):
            with self.subTest(mutation=mutation):
                _, _, session, revision, _ = self.fixture()
                root, identity = session.workspace_root, session.git_status_identity
                original_tree = runner._worktree_git_tree_oid
                from icode.workspace import read_git_repository_state
                changed = False
                def walk(path, *, object_format):
                    nonlocal changed
                    result = original_tree(path, object_format=object_format)
                    if mutation == "identity":
                        session.git_status_identity = replace(identity)
                    elif mutation == "root":
                        session.workspace_root = root.parent
                    elif mutation == "kind":
                        session.kind = "snapshot"
                    elif mutation == "HEAD":
                        (identity.git_dir / "HEAD").write_text("0" * 40 + "\n", encoding="ascii")
                    elif mutation == "pointer":
                        (identity.checkout_root / ".git").write_text("gitdir: /not-this-session\n", encoding="ascii")
                    elif mutation == "rootgit":
                        (root / ".git").mkdir()
                    changed = True
                    return result
                def actual_state(path, *, require_root=False):
                    result = read_git_repository_state(path, require_root=require_root)
                    return ("sha256", result[1]) if mutation == "format" and changed else result
                with patch.object(runner, "_worktree_git_tree_oid", side_effect=walk), \
                     patch("icode.workspace.read_git_repository_state", side_effect=actual_state):
                    self.assertEqual(self.tree(root, revision, session), ("", "session_git_identity_unavailable"))
        for field in ("protected_paths", "manifest_path", "runtime_root", "receipts_root"):
            with self.subTest(fallback_field=field):
                _, _, session, revision, _ = self.fixture(split=False)
                root = session.workspace_root
                original_tree = runner._worktree_git_tree_oid
                def drift(path, *, object_format):
                    result = original_tree(path, object_format=object_format)
                    setattr(session, field, () if field == "protected_paths" else Path("/changed"))
                    return result
                with patch.object(runner, "_worktree_git_tree_oid", side_effect=drift):
                    self.assertEqual(self.tree(root, revision, session), ("", "session_git_identity_unavailable"))
        for mutation in ("HEAD", "identity", "protected_paths"):
            with self.subTest(state_window=mutation):
                _, _, session, revision, _ = self.fixture()
                root, identity = session.workspace_root, session.git_status_identity
                from icode.workspace import read_git_repository_state
                def state_drift(path, *, require_root=False):
                    result = read_git_repository_state(path, require_root=require_root)
                    if mutation == "HEAD":
                        (identity.git_dir / "HEAD").write_text("0" * 40 + "\n", encoding="ascii")
                    elif mutation == "identity":
                        session.git_status_identity = replace(identity)
                    else:
                        session.protected_paths = (*session.protected_paths, root / "new-protection")
                    return result
                with patch("icode.workspace.read_git_repository_state", side_effect=state_drift):
                    with self.assertRaisesRegex(ValueError, "^workspace_git_identity_unavailable$"):
                        self.state(root, session)

    def test_tree_semantics_stability_and_existing_failures_preserved(self):
        _, source, session, revision, _ = self.fixture()
        root = session.workspace_root
        initial = self.tree(root, revision, session)[0]
        (root / "changed.py").write_text("value = 1\n", encoding="utf-8")
        content_oid = self.tree(root, revision, session)[0]
        self.assertNotEqual(initial, content_oid)
        (root / "changed.py").chmod(0o755)
        mode_oid = self.tree(root, revision, session)[0]
        self.assertNotEqual(content_oid, mode_oid)
        (root / "link").symlink_to(source / "changed.py")
        link_oid = self.tree(root, revision, session)[0]
        (source / "changed.py").write_text("outside body not hashed\n", encoding="utf-8")
        self.assertEqual(self.tree(root, revision, session)[0], link_oid)
        (root / "link").unlink()
        (root / "link").symlink_to(source / "other.py")
        self.assertNotEqual(self.tree(root, revision, session)[0], link_oid)
        before = {"a": "1"}
        for after in ({"a": "2"}, {"a": "1", "b": "3"}):
            oid, status = runner._resolve_tested_git_tree(before, after, initial, "captured",
                                                        content_oid, "captured", "sha1", "sha1")
            self.assertEqual(oid, "")
            self.assertNotEqual(status, "stable")
        for failure in ("filesystem_changed", "unsupported_file_type", "worktree_too_large", "worktree_too_deep"):
            with self.subTest(failure=failure), patch.object(runner, "_worktree_git_tree_oid",
                    side_effect=WorktreeTreeUnavailable(failure)):
                self.assertEqual(self.tree(root, revision, session), ("", failure))
        nested = root / "nested"
        nested.mkdir()
        (nested / ".git").mkdir()
        self.assertEqual(self.tree(root, revision, session), ("", "nested_git_metadata"))
        (nested / ".git").rmdir()
        os.mkfifo(nested / "fifo")
        self.assertEqual(self.tree(root, revision, session)[0], "")
        (nested / "fifo").unlink()
        from icode import workspace_snapshot
        for name, limit, reason in (("_MAX_GIT_TREE_ENTRIES", 0, "worktree_too_large"),
                                    ("_MAX_GIT_TREE_BYTES", 0, "worktree_too_large"),
                                    ("_MAX_GIT_TREE_DEPTH", 0, "worktree_too_deep")):
            with self.subTest(bound=name), patch.object(workspace_snapshot, name, limit):
                self.assertEqual(self.tree(root, revision, session), ("", reason))

    def test_ordinary_snapshot_non_git_and_exact_legacy_call_shapes(self):
        for extra in (False, True):
            _, source, session, revision, expected = self.fixture(split=False, extra_unrelated=extra)
            self.assertIsNone(session.git_status_identity)
            self.assertEqual(self.state(session.workspace_root, session), ("sha1", revision))
            self.assertEqual(self.tree(session.workspace_root, revision, session), (expected, "captured"))
            self.assertEqual(runner._read_task_git_state(source), ("sha1", revision))
            self.assertEqual(runner._capture_task_git_tree_oid(source, revision), (expected, "captured"))
            (source / "sub").mkdir()
            self.assertEqual(runner._capture_task_git_tree_oid(source / "sub", revision),
                             ("", "workspace_not_repository_root"))
        _, _, session, _, _ = self.fixture(snapshot=True)
        self.assertEqual(self.state(session.workspace_root, session), ("", ""))
        self.assertEqual(self.tree(session.workspace_root, "", session), ("", "not_git_workspace"))
        from icode.workspace import WorkspaceError
        with patch("icode.workspace.read_git_repository_state", side_effect=WorkspaceError("unavailable")):
            self.assertEqual(self.state(session.workspace_root, session), ("", ""))
        with patch("icode.workspace.read_git_repository_state", side_effect=OSError("legacy io")):
            with self.assertRaisesRegex(OSError, "legacy io"):
                runner._read_task_git_state(session.workspace_root)
        with patch("icode.workspace.read_git_repository_state", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.state(session.workspace_root, session)
```

- [x] **Step 4: 写最小生产实现。**

在 runner 的 workspace import 增加 `GitWorkspaceIdentity`；在两个原函数前放以下私有验证函数。`binding` 只是本次栈内事实，不是持久授权、manifest反序列化或新模型。路径验证不 resolve。不吞 BaseException。identityNone 的 git_worktree 固定拓扑和原 protected root.git **同时**必要。

```python
def _task_git_session_layout(workspace: Path, session: WorkspaceSession):
    from .git_broker import GitStatusUnavailable, verify_git_workspace_identity

    def absolute(path):
        if (not isinstance(path, Path) or not path.is_absolute()
                or Path(os.path.abspath(os.fspath(path))) != path):
            raise ValueError("session_git_identity_unavailable")
        return path

    try:
        if not isinstance(session, WorkspaceSession):
            raise ValueError("session_git_identity_unavailable")
        root = absolute(workspace)
        if absolute(session.workspace_root) != root or session.kind not in ("snapshot", "git_worktree"):
            raise ValueError("session_git_identity_unavailable")
        protected = session.protected_paths
        if not isinstance(protected, tuple):
            raise ValueError("session_git_identity_unavailable")
        for path in protected:
            absolute(path)
        identity = session.git_status_identity
        binding = (session.kind, root, protected)
        if session.kind == "snapshot":
            if identity is not None:
                raise ValueError("session_git_identity_unavailable")
            return None, binding
        if identity is None:
            manifest = absolute(session.manifest_path)
            runtime = absolute(session.runtime_root)
            receipts = absolute(session.receipts_root)
            ticket_root = manifest.parent
            if (manifest != ticket_root / "workspace.json"
                    or runtime != ticket_root / "runtime"
                    or receipts != ticket_root / "receipts"
                    or root != ticket_root / "checkout"
                    or root / ".git" not in protected):
                raise ValueError("session_git_identity_unavailable")
            return None, (*binding, manifest, runtime, receipts)
        if not isinstance(identity, GitWorkspaceIdentity):
            raise ValueError("session_git_identity_unavailable")
        if not isinstance(identity.source_relative_path, Path):
            raise ValueError("session_git_identity_unavailable")
        if identity.source_relative_path != Path("."):
            raise ValueError("workspace_shape_unsupported")
        if (absolute(identity.workspace_root) != root
                or absolute(identity.code_root) != root
                or absolute(identity.checkout_root) / "code" != root):
            raise ValueError("session_git_identity_unavailable")
        layout = verify_git_workspace_identity(identity)
        if layout.worktree_root != root or layout.pathspec_root != root:
            raise ValueError("session_git_identity_unavailable")
        try:
            (root / ".git").lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError("session_git_identity_unavailable")
        fixed_identity = (identity.checkout_root, identity.code_root, identity.workspace_root,
                          identity.top_level, identity.common_dir, identity.git_dir,
                          identity.revision, identity.identity_token,
                          identity.source_relative_path, identity.filesystem_identities)
        return identity, (*binding, fixed_identity)
    except (GitStatusUnavailable, OSError, TypeError, AttributeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc) == "workspace_shape_unsupported":
            raise
        raise ValueError("session_git_identity_unavailable") from None


def _recheck_task_git_session(workspace, session, identity, binding):
    current_identity, current_binding = _task_git_session_layout(workspace, session)
    if current_identity is not identity or current_binding != binding:
        raise ValueError("session_git_identity_unavailable")
```

在 `_read_task_git_state` 增加 keyword并在原 body 最前增加下述 session分支；从原 `has_git_metadata = ...` 开始到返回原样保持，不重写legacy。对 snapshot/合格普通session递归调用 **无 session kwargs** 的原函数，legacy OSError分类保持；仅 layout验证与split Git接口的可预期身份错误归一化。

```python
def _read_task_git_state(workspace: Path, *, workspace_session: WorkspaceSession | None = None) -> tuple[str, str]:
    """读取真实 storage format/HEAD；可信分离会话只从其 checkout 查询。"""
    from .workspace import WorkspaceError, read_git_repository_state

    if workspace_session is not None:
        try:
            identity, binding = _task_git_session_layout(workspace, workspace_session)
        except ValueError:
            raise ValueError("workspace_git_identity_unavailable") from None
        if identity is None:
            result = _read_task_git_state(workspace)
            try:
                _recheck_task_git_session(workspace, workspace_session, identity, binding)
            except ValueError:
                raise ValueError("workspace_git_identity_unavailable") from None
            return result
        try:
            result = read_git_repository_state(identity.checkout_root, require_root=True)
            _recheck_task_git_session(workspace, workspace_session, identity, binding)
            object_format, revision = result
            length = {"sha1": 40, "sha256": 64}.get(object_format)
            if (length is None or not isinstance(revision, str)
                    or revision != identity.revision or len(revision) != length
                    or any(character not in "0123456789abcdef" for character in revision)):
                raise ValueError("session_git_identity_unavailable")
            return object_format, revision
        except (WorkspaceError, OSError, ValueError, TypeError, AttributeError):
            raise ValueError("workspace_git_identity_unavailable") from None

    has_git_metadata = any(
        (candidate / ".git").exists() or (candidate / ".git").is_symlink()
        for candidate in (workspace, *workspace.parents)
    )
    if shutil.which("git") is None:
        if has_git_metadata:
            raise ValueError("workspace_git_identity_unavailable")
        return "", ""
    try:
        object_format, revision = read_git_repository_state(workspace)
    except WorkspaceError:
        if has_git_metadata:
            raise ValueError("workspace_git_identity_unavailable") from None
        return "", ""
    if object_format not in ("sha1", "sha256"):
        raise ValueError("workspace_git_object_format_invalid")
    return object_format, revision
```

以上从has_git_metadata起是原真实body，不删除、重构或改变故障分类。`_capture_task_git_tree_oid` 同样只增加新 keyword和下述分支，从原 `if not base_commit_sha:` 起的全部 body保留。

```python
def _capture_task_git_tree_oid(
    workspace: Path, base_commit_sha: str, *, object_format: str | None = None,
    workspace_session: WorkspaceSession | None = None,
) -> tuple[str, str]:
    """只读捕获代码根原始 Git tree；session 来源前后真实重核。"""
    if workspace_session is not None:
        try:
            identity, binding = _task_git_session_layout(workspace, workspace_session)
        except ValueError as exc:
            return "", ("workspace_shape_unsupported" if str(exc) == "workspace_shape_unsupported"
                        else "session_git_identity_unavailable")
        if identity is None:
            result = _capture_task_git_tree_oid(workspace, base_commit_sha, object_format=object_format)
            try:
                _recheck_task_git_session(workspace, workspace_session, identity, binding)
            except ValueError:
                return "", "session_git_identity_unavailable"
            return result
        try:
            before_format, before_head = _read_task_git_state(workspace, workspace_session=workspace_session)
            if (not base_commit_sha or base_commit_sha != identity.revision
                    or before_head != base_commit_sha
                    or (object_format is not None and object_format != before_format)):
                return "", "session_git_identity_unavailable"
            oid = _worktree_git_tree_oid(workspace, object_format=before_format)
            after_format, after_head = _read_task_git_state(workspace, workspace_session=workspace_session)
            _recheck_task_git_session(workspace, workspace_session, identity, binding)
            if after_format != before_format or after_head != before_head:
                return "", "session_git_identity_unavailable"
            return oid, "captured"
        except WorktreeTreeUnavailable as exc:
            return "", exc.reason
        except ValueError:
            return "", "session_git_identity_unavailable"

    if not base_commit_sha:
        return "", "not_git_workspace"
    metadata = workspace / ".git"
    try:
        metadata_status = metadata.lstat()
    except OSError:
        return "", "workspace_not_repository_root"
    metadata_is_file_or_directory = (
        stat.S_ISDIR(metadata_status.st_mode)
        or stat.S_ISREG(metadata_status.st_mode)
    )
    if stat.S_ISLNK(metadata_status.st_mode) or not metadata_is_file_or_directory:
        return "", "git_metadata_unavailable"
    if object_format is None:
        try:
            object_format, _head_sha = _read_task_git_state(workspace)
        except ValueError:
            return "", "git_object_format_unavailable"
    if object_format not in ("sha1", "sha256"):
        return "", "unsupported_object_format"
    try:
        oid = _worktree_git_tree_oid(workspace, object_format=object_format)
    except WorktreeTreeUnavailable as exc:
        return "", exc.reason
    return oid, "captured"
```

- [x] **Step 5: 核心 GREEN、自 SPEC/QUALITY，不提交。**

```bash
session_git_python -m unittest tests.test_session_git_projection.TestSessionGitProjection -v
session_git_python -m unittest tests.test_git_broker.TestGitWorkspaceIdentityVerification tests.test_r3_regression.TestWorktreeGitTreeOID tests.test_verification_measurement -v
git diff --check
git diff -- src/icode/runner.py tests/test_session_git_projection.py
```

Expected：本机全部0F/E/skip；实际Git缺sha256只记录该前提skip并使required CI不能通过，不替换成SHA1。自SPEC核S矩阵、实际format/HEAD与splitdot范围，自QUALITY核最小修改/异常信用/旧body未改。fresh SPEC→不同 QUALITY 两者0阻塞后才 Task2；作者自审不能代替独立审查。

### Task 1 实际履历（2026-10-09，root 汇总）

作者 `/root/session_git_task1_implementation` 使用真实 Git/manager fixture，实际返回 `(session, source, revision, tree)`；不是上方计划示例的五项形状。初次正控 RED 为 1 方法、F1/E0/skip0、exit1，原树状态 `workspace_not_repository_root` 与 `captured` 不同。作者首轮 GREEN 为核心11方法/2.364s、原回归27方法/1.618s，均0F/E/skip、exit0；仅授本片软件接口，不授 caller、OS、installed、模型或完整步骤。

审查修订历史不得覆盖：fresh SPEC `/root/session_git_task1_spec` 首轮 C0/I0/M2，发现 source-relative 字段错类型分类与 core class 静态 skip；作者原自审零缺陷遗漏了这两项。修订实际 RED 分别为2方法/F2子场景和1方法/F1，均E0/skip0、exit1；修后11+27 GREEN、SPEC复审 C0/I0/M0。不同 QUALITY `/root/session_git_task1_quality` 随后给出 C0/I0/M1：普通 identityNone fallback 把真实 walker 的 ValueError 误归身份不可用。作者新增真实 manager/walker 中 `hashlib.new` 的故障注入负控，实际1方法/F2子场景/0.269s、E0/skip0、exit1，再将普通递归移出 split try，仅后核身份归一；作者修后11/2.387s+27/1.535s，全部通过。注入不是现场加密提供方故障。

最终同 SPEC 复审 C0/I0/M0：独立11/2.529s+27/1.629s；同不同 QUALITY 复审 C0/I0/M0：独立11/2.516s+27/1.581s。各次均0F/E/skip、exit0，sha256实际执行；重复审查不虚增不同方法数。两处 legacy body 与原 HEAD 逐字比较、diff检查均0。root 实读新增 helpers/state/tree、全新测试与后续改动，确认以上两次修正符合原合同；三复用模块、vendor169与Native gate False未改。

Task1最终冻结：runner SHA256 `3e5799fb2456f119b49b6e17a77134a827c9b45ce45ce1accc7567221796852f`；新测试 SHA256 `eb19c8322f6afaa4f5b80cbcbf6f7790eb08452d836130dc535465ee206c6fc8`。此为Task1阶段身份，Task2合法接线会产生新冻结，不把这些SHA冒称后续全片。作者与两位reviewer均STOP后，root于05:01 UTC后启动 fresh Task2唯一源码作者；main仍8d，尚未全片发布。

## Task 2: 全 caller 接线与工程/Reviewer/最后 CP 回归

**状态**

- [x] 任务完成

**Dependencies:** Task 1

**Parallelizable:** No (runner 同一文件唯一 writer，实际 CP/工程 tests 串行)

- [x] **Step 1: 先追加 caller guard 和真实 split 工程正控。**

在新模块的同一类追加下面方法。guard 是真实代码 AST 的参数来源检查与选定表达式观察，不报告为真实 contract admission/resume 往返；后面的 gate 测试才实际走 CP/operation/receipt/Reviewer。原 measurement/run_task 不得传 session。

```python
    def test_all_session_callers_pass_same_session_and_legacy_call_shapes_stay_exact(self):
        _, _, session, revision, _ = self.fixture()
        expected = ((runner.run_contract_step, 1, 0, "workspace_session"),
                    (runner.resume_contract_step, 1, 0, "workspace_session"),
                    (runner._contract_engineering_gate, 3, 3, "workspace_session"),
                    (runner._contract_engineering_binding_error, 1, 1, "session"),
                    (runner._run_task_reviewer, 0, 1, "workspace_session"))
        for function, states, trees, session_name in expected:
            source = ast.parse(textwrap.dedent(inspect.getsource(function)))
            calls = [node for node in ast.walk(source) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id in ("_read_task_git_state", "_capture_task_git_tree_oid")]
            self.assertEqual(sum(node.func.id == "_read_task_git_state" for node in calls), states)
            self.assertEqual(sum(node.func.id == "_capture_task_git_tree_oid" for node in calls), trees)
            assignments = [node for node in ast.walk(source) if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "git_session_kwargs"
                                   for target in node.targets)]
            self.assertEqual(len(assignments), 1, function.__name__)
            session_expr = assignments[0].value
            self.assertIn(session_name, {node.id for node in ast.walk(session_expr) if isinstance(node, ast.Name)})
            for supplied in (session, None):
                namespace = {session_name: supplied, "workspace": session.workspace_root,
                             "before_head": revision, "before_format": "sha1", "after_format": "sha1",
                             "current_format": "sha1", "object_format": "sha1",
                             "evidence": SimpleNamespace(base_commit_sha=revision, git_object_format="sha1")}
                exec(compile(ast.fix_missing_locations(ast.Module(body=[assignments[0]], type_ignores=[])),
                             "caller-session-binding", "exec"), namespace)
                self.assertEqual(namespace["git_session_kwargs"], {} if supplied is None else {"workspace_session": supplied})
                observed = []
                def capture(*args, **kwargs):
                    observed.append(kwargs)
                    return "sha1", revision
                namespace.update(_read_task_git_state=capture, _capture_task_git_tree_oid=capture)
                for call in calls:
                    self.assertTrue(any(keyword.arg is None and isinstance(keyword.value, ast.Name)
                                        and keyword.value.id == "git_session_kwargs" for keyword in call.keywords),
                                    function.__name__)
                    eval(compile(ast.fix_missing_locations(ast.Expression(body=call)), "caller-call", "eval"), namespace)
                for kwargs in observed:
                    self.assertEqual(kwargs.get("workspace_session"), supplied)
                    self.assertEqual("workspace_session" in kwargs, supplied is not None)
        for function in (runner._measure_task_verification, runner.run_task):
            source = ast.parse(textwrap.dedent(inspect.getsource(function)))
            for call in (node for node in ast.walk(source) if isinstance(node, ast.Call)
                         and isinstance(node.func, ast.Name)
                         and node.func.id in ("_read_task_git_state", "_capture_task_git_tree_oid")):
                self.assertFalse(any(keyword.arg == "workspace_session" or keyword.arg is None
                                     for keyword in call.keywords))
```

在 `tests/test_contract_engineering.py` 现有 `TestContractEngineering` 类追加以下 helper 与两个 POSIX 方法（不新继承类，不重复收集旧 tests）。复用现有 CP fixture，其 out_dir 位于原 source，分离工作区只含真实已提交代码；真实修改发生在 CP 原 fixture 已打开 attempt 之后。此处是直接 gate 接线，不当普通 code/deepcheck全部门或第一三步真实模型。

```python
    def split_gate_fixture(self):
        from icode.workspace import WorkspaceManager
        from tests.test_shared_runtime_budget import MeteredBackend
        backend = MeteredBackend([(response, 1) for response in [
            {"tool_calls": [{"id": "read", "name": "read_file", "arguments": {"path": "changed.py"}}]},
            {"tool_calls": [{"id": "submit", "name": "submit_review", "arguments": {"summary": "Checked split change", "findings": []}}]},
            "done",
        ]])
        source, cp, directory, outcome, report, args = self.gate_fixture(reviewer=backend, git_workspace=True)
        data = self.enterContext(temp_workspace()).resolve()
        session = WorkspaceManager(source, data, "split-gate", isolate_git_metadata=True).open(
            "ENG-CONTRACT", "contract-run")
        self.addCleanup(session.close)
        root = session.workspace_root
        baseline = runner._snapshot(root)
        (root / "changed.py").write_text("value = 1\n", encoding="utf-8")
        args.update(workspace=root, workspace_session=session, baseline=baseline,
                    git_baseline=runner._read_task_git_state(root, workspace_session=session),
                    policy=session.policy("code", process_limit=8, wall_timeout_seconds=30, output_limit_bytes=65536),
                    plan=VerificationPlan(root, args["plan"].run_id, args["plan"].ticket_id,
                                          args["plan"].checks, args["plan"].steps, args["plan"].platforms))
        return root, cp, directory, outcome, report, args

    @unittest.skipUnless(os.name == "posix", "manager split Git identity is POSIX-only")
    def test_split_session_gate_real_tree_reviewer_and_final_binding(self):
        root, cp, directory, outcome, report, args = self.split_gate_fixture()
        state_function, tree_function = runner._read_task_git_state, runner._capture_task_git_tree_oid
        with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome) as dispatch, \
             patch.object(runner, "_read_task_git_state", wraps=state_function) as states, \
             patch.object(runner, "_capture_task_git_tree_oid", wraps=tree_function) as trees:
            self.assertTrue(runner._contract_engineering_gate(**args), report.error)
            self.assertEqual(runner._contract_engineering_binding_error(report, args["plan"], root,
                "code", "ENG-CONTRACT", args["policy"], args["sandbox"], args["workspace_session"]), "")
        dispatch.assert_called_once()
        self.assertTrue(states.call_args_list)
        self.assertTrue(trees.call_args_list)
        for call in states.call_args_list + trees.call_args_list:
            self.assertIs(call.kwargs["workspace_session"], args["workspace_session"])
        self.assertEqual(report.verification_evidence.tested_git_tree_status, "stable")
        self.assertEqual(report.verification_evidence.git_object_format, "sha1")
        self.assertFalse(cp.trace(directory).data["open_operations"])
        self.assertEqual(args["budget_tracker"].usage.calls, 3)
        self.assertEqual({tool["function"]["name"] for call in args["backend"].calls
                          for tool in call.get("tools", ())}, {"read_file", "submit_review"})

    @unittest.skipUnless(os.name == "posix", "manager split Git identity is POSIX-only")
    def test_split_session_reviewer_and_final_boundary_reject_real_drift(self):
        from icode.reviewer import ReviewReport
        for mutation in ("source_during_review", "identity_during_review", "source_after_review", "identity_after_review"):
            with self.subTest(mutation=mutation):
                root, cp, directory, outcome, report, args = self.split_gate_fixture()
                session = args["workspace_session"]
                def review(**kwargs):
                    if mutation == "source_during_review":
                        (root / "changed.py").write_text("value = 9\n", encoding="utf-8")
                    elif mutation == "identity_during_review":
                        (session.git_status_identity.git_dir / "HEAD").write_text("0" * 40 + "\n", encoding="ascii")
                    return ReviewReport(ok=True, model_reviewed=True, read_only_verified=True), None
                with patch("icode.tools.builtin._controlled_dispatch", return_value=outcome), \
                     patch.object(runner, "_run_task_reviewer", side_effect=review):
                    if mutation == "identity_during_review":
                        with self.assertRaisesRegex(ValueError, "workspace_git_identity_unavailable"):
                            runner._contract_engineering_gate(**args)
                        self.assertEqual(self.event_rows(directory, "step_finished"), [])
                        continue
                    passed = runner._contract_engineering_gate(**args)
                if mutation == "source_during_review":
                    self.assertFalse(passed)
                    self.assertEqual(report.error, "engineering_reviewer_failed")
                    self.assertEqual(self.event_rows(directory, "step_finished"), [])
                    continue
                self.assertTrue(passed, report.error)
                if mutation == "source_after_review":
                    (root / "changed.py").write_text("value = 9\n", encoding="utf-8")
                    self.assertEqual(runner._contract_engineering_binding_error(report, args["plan"], root,
                        "code", "ENG-CONTRACT", args["policy"], args["sandbox"], session), "engineering_final_binding_changed")
                else:
                    (session.git_status_identity.git_dir / "HEAD").write_text("0" * 40 + "\n", encoding="ascii")
                    with self.assertRaisesRegex(ValueError, "workspace_git_identity_unavailable"):
                        runner._contract_engineering_binding_error(report, args["plan"], root,
                            "code", "ENG-CONTRACT", args["policy"], args["sandbox"], session)
                self.assertEqual(self.event_rows(directory, "step_finished"), [])
```

- [x] **Step 2: 接线 RED。**

```bash
session_git_python -m unittest tests.test_session_git_projection.TestSessionGitProjection.test_all_session_callers_pass_same_session_and_legacy_call_shapes_stay_exact tests.test_contract_engineering.TestContractEngineering.test_split_session_gate_real_tree_reviewer_and_final_binding -v
```

Expected：guard 的实际 `len(assignments)==1` FAIL、工程 gate `engineering_verification_failed` FAIL；任何 fixture参数错误不是RED，先修真实API。不要添加stub、强制source_stable=True或mock treecaptured。

- [x] **Step 3: 完整 caller 接线。**

在 `run_contract_step` / `resume_contract_step` 工程baseline读取前分别增加：

```python
        git_session_kwargs = ({"workspace_session": workspace_session}
                              if workspace_session is not None else {})
        engineering_git_baseline = _read_task_git_state(workspace, **git_session_kwargs) if engineering else None
```

在 `_contract_engineering_gate` 的 `before = _snapshot(workspace)` 前增加局部kwargs，并只替换列出的六个state/tree调用；其它完整门、顺序和source_stable条件保持：

```python
    git_session_kwargs = ({"workspace_session": workspace_session}
                          if workspace_session is not None else {})
    before = _snapshot(workspace)
    before_format, before_head = _read_task_git_state(workspace, **git_session_kwargs)
    before_oid, before_status = _capture_task_git_tree_oid(workspace, before_head,
        object_format=before_format, **git_session_kwargs)
    run = execute_verification_plan(plan, ctx=ctx, step=step, attempt=attempt)
    after = _snapshot(workspace)
    after_format, after_head = _read_task_git_state(workspace, **git_session_kwargs)
    after_oid, after_status = _capture_task_git_tree_oid(workspace, before_head,
        object_format=after_format, **git_session_kwargs)
```

Reviewer后的两个调用替换为：

```python
    current_format, current_head = _read_task_git_state(workspace, **git_session_kwargs)
    current_oid, current_status = _capture_task_git_tree_oid(workspace, before_head,
        object_format=current_format, **git_session_kwargs)
```

在 `_contract_engineering_binding_error` 的原state读取处加入局部kwargs，原tree调用同步：

```python
    git_session_kwargs = ({"workspace_session": session} if session is not None else {})
    object_format, head = _read_task_git_state(workspace, **git_session_kwargs)
```

```python
        oid, status = _capture_task_git_tree_oid(workspace, evidence.base_commit_sha,
            object_format=object_format, **git_session_kwargs)
```

在 `_run_task_reviewer` 的末尾 `if evidence.tested_git_tree_oid:` 中加入：

```python
        git_session_kwargs = ({"workspace_session": workspace_session}
                              if workspace_session is not None else {})
        current_tree_oid, current_tree_status = _capture_task_git_tree_oid(
            workspace, evidence.base_commit_sha,
            object_format=evidence.git_object_format, **git_session_kwargs,
        )
```

不得在 `_measure_task_verification`/run_task普通baseline增加keyword或kwargs，不改 `_read_task_base_commit_sha`、result-commit能力或其它caller。无session各处kwargs为空，旧精确tree wrapper/state double仍适用。

- [x] **Step 4: GREEN与原普通门回归，自审和独立双审查。**

```bash
session_git_python -m unittest tests.test_session_git_projection tests.test_contract_engineering -v
session_git_python -m unittest tests.test_verification_measurement tests.test_r3_regression -v
git diff --check
rg -n '_read_task_git_state|_capture_task_git_tree_oid|git_session_kwargs' src/icode/runner.py
```

Expected：实际0F/E，本片required0skip；原大型回归存在的环境skip按实际列表记录，不改为全平台通过。现有 deepcheck捕获范围/开始后源码与范围漂移、最后CP protectedinput、resume原baseline/attempt、旧精确签名与result-commit读只读回归都保持原断言。W-03的deepcheck信用来自这些原测试，不把新增直接 gate测试当完整deepcheck。作者自SPEC/QUALITY后 freshSPEC→不同QUALITY，未通过不进Task3、不提交。

### Task 2 实际履历（2026-10-09，root 汇总）

fresh 作者 `/root/session_git_task2_implementation` 先新增真实 caller AST/表达式 guard 与真实 split gate 正控，实际 RED 为2方法/F6子场景/E0/skip0、0.820s、exit1；五 caller 尚无局部 session 参数来源，真实 gate 返回 engineering_verification_failed。随后仅接线 admission、resume、gate、最后 binding、Reviewer 的六次 state 与五次 tree，同一对象输入；None 时局部 kwargs 为空，measurement/run_task 旧精准形状不改。测试使用 Task1 实际四项 fixture，不复制计划示例的五项形状。

作者首次 GREEN 为51/44.160s，0F/E/skip；此轮 PATH 中多了一次相同 /usr/local/bin，解释器未变，未隐去偏差。作者自行按原严格前缀重跑51/45.411s，0F/E/skip；回归90/18.681s，0F/E/skip1，各次exit0。自SPEC→自QUALITY均 C0/I0/M0。fresh SPEC `/root/session_git_task2_spec` 独立51/44.240s与90/18.786s，C0/I0/M0；不同 QUALITY `/root/session_git_task2_quality` 独立51/44.457s与90/18.580s，C0/I0/M1。两位审查均0F/E；51项skip0，90项唯一skip是 TestWindowsSnapshotReparseSafety.test_native_windows_junction_is_rejected_before_target_scan，原因 requires a native Windows junction；sha256实际执行，各次exit0。以上结果均绑定行为冻结 runner `a21a43ea3151e1bfe2e6f2839f14cf0c83f2fa5ae1ab135096b172fd7763d579`。

QUALITY Minor 为原树函数“不运行 Git helper”文案未限定树 walker本身；root接受后作者仅改一行 docstring，明确“宿主捕获原始 Git tree 投影；可信会话前后只读查询 Git 状态。”作者自双审、同SPEC与同不同QUALITY只读 delta 均 C0/I0/M0，原M1关闭。新 runner SHA256 `0bc0d5e0711e88e9aee35f3a693430eb529a6d597388a32c3ff0f2defe596a83`；只读管道还原文案精确得到上述旧SHA，确认其它字节不变。没有为文案重复141项，也不把旧运行结果冒称新SHA上的实际运行。全片最终软件验收另行执行。

Task2 core SHA256 `e87d0391ded46c25c61b3676938fa818a1e9fbcd1295b1a86adda91e71e36b94`（490行/12方法）；contract SHA256 `a807240ccfd6ad0d9a0add4104c312ce9c7a555596d8e5d3fcd00e9c24ef478d`（39方法，新2方法）。两处 legacy body 与原 HEAD 完全相同；去掉 Task2 kwargs 的只读管道恢复 Task1 runner SHA。依赖三模块、vendor169、Native False保持，diff检查0。新增正控授真实 manager/Git/CP/operation/受控 Reviewer read-submit/最后 source binding信用，但 transport/model double不是OS或真实模型，不是完整普通 code/deepcheck成功；deepcheck信用来自未改旧回归。作者、SPEC、QUALITY均STOP后才启动Task3唯一 writer；未提交推送。

## Task 3: 精确 POSIX CI 方法与 skip 失败门

**状态**

- [x] 任务完成

**Dependencies:** Task 2

**Parallelizable:** No (方法名与 GREEN 源冻结后同步选择，不和测试/源写并行)

- [x] **Step 1: 在现有 TestWorkspaceCiCoverage 加完整选择/动态 skip guard。**

```python
    def test_session_git_projection_methods_selected_once_and_required(self):
        module_name = "tests.test_session_git_projection"
        module = importlib.import_module(module_name)
        cls = module.TestSessionGitProjection
        prefix = module_name + ".TestSessionGitProjection."
        expected = {prefix + name for name in unittest.defaultTestLoader.getTestCaseNames(cls)}
        self.assertTrue(expected)
        selected = [name for name in DEFAULT_MODULES if name.startswith(module_name)]
        if os.name == "posix":
            self.assertEqual(set(selected), expected)
            self.assertEqual(len(selected), len(expected))
            self.assertTrue(expected.issubset(run_workspace_ci.POSIX_R3_TESTS))
            self.assertFalse(getattr(cls, "__unittest_skip__", False))
            for test_id in selected:
                cases = list(unittest.defaultTestLoader.loadTestsFromName(test_id))
                self.assertEqual(len(cases), 1)
                self.assertIs(type(cases[0]), cls)
                self.assertEqual(cases[0].id(), test_id)
                self.assertFalse(getattr(getattr(cls, cases[0]._testMethodName), "__unittest_skip__", False))
            for test_id in expected:
                class SkippedRequired(unittest.TestCase):
                    def id(self):
                        return test_id
                    def runTest(self):
                        self.skipTest("simulated required session Git prerequisite missing")
                with patch.object(run_workspace_ci.unittest.defaultTestLoader, "loadTestsFromNames",
                                  return_value=unittest.TestSuite([SkippedRequired()])), \
                     redirect_stderr(io.StringIO()):
                    self.assertEqual(run_workspace_ci.main((test_id,)), 1)
        else:
            self.assertEqual(selected, [])
        contract = "tests.test_contract_engineering.TestContractEngineering."
        additions = {contract + "test_split_session_gate_real_tree_reviewer_and_final_binding",
                     contract + "test_split_session_reviewer_and_final_boundary_reject_real_drift"}
        for test_id in additions:
            self.assertEqual(DEFAULT_MODULES.count(test_id), 1 if os.name == "posix" else 0)
            self.assertIn(test_id, run_workspace_ci.POSIX_R3_TESTS)
```

- [x] **Step 2: CI选择 RED。**

```bash
session_git_python -m unittest tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_session_git_projection_methods_selected_once_and_required -v
```

Expected：actual assertion FAIL，selected空但expected非空；不是import/loaderERROR。新的module用现有默认 unittest discovery在原full中自动一次加载，无需改变preflight。

- [x] **Step 3: 加精确方法 ID，不改 main/required-skip逻辑。**

在现有 `POSIX_CONTRACT_ENGINEERING_TESTS` 名称列表尾部加入：

```python
    "test_split_session_gate_real_tree_reviewer_and_final_binding",
    "test_split_session_reviewer_and_final_boundary_reject_real_drift",
```

在 `POSIX_R3_TESTS` 上方定义明确tuple，随后展开进原POSIX_R3_TESTS；不能用module/classentry代替方法ID：

```python
SESSION_GIT_PROJECTION_TESTS = tuple(
    "tests.test_session_git_projection.TestSessionGitProjection." + name for name in (
        "test_real_split_dot_matches_commit_tree",
        "test_real_sha256_and_caller_format_base_rejection",
        "test_paths_subtrees_and_other_session_rejected",
        "test_identity_fields_missing_duplicate_device_inode_token_rejected",
        "test_metadata_real_rewrites_replacements_and_symlinks_rejected",
        "test_code_git_all_types_and_lstat_error_rejected_before_git_tree",
        "test_missing_split_identity_same_head_injection_extra_protection_never_falls_back",
        "test_session_field_layout_and_protection_validation",
        "test_capture_window_observed_identity_head_format_and_fields_drift",
        "test_tree_semantics_stability_and_existing_failures_preserved",
        "test_ordinary_snapshot_non_git_and_exact_legacy_call_shapes",
        "test_all_session_callers_pass_same_session_and_legacy_call_shapes_stay_exact",
    )
)

POSIX_R3_TESTS = (
    "tests.test_r3_regression.TestWorktreeGitTreeOID.test_tree_oid与Git写树一致并覆盖忽略项链接和模式",
    *POSIX_CONTRACT_ENGINEERING_TESTS,
    *SESSION_GIT_PROJECTION_TESTS,
)
```

无全局静态skip。full在非POSIX上无法构造splitmanager，因此新module的fixture可在最开始使用实际平台前提 `if os.name != "posix": self.skipTest("manager split Git identity requires POSIX")`；DEFAULT根本不选该module/方法到Windows，故Windowsbounded矩阵不新增skip。这是实际环境限制，不是隐藏实现失败；root本机POSIXrequired不得skip。`tests/test_run_workspace_ci` guard本身是portable，可在所有平台完整执行。

- [x] **Step 4: GREEN、20轮方法集准备、双审查，不提交。**

```bash
session_git_python -m unittest tests.test_run_workspace_ci -v
session_git_python scripts/run_workspace_ci.py tests.test_session_git_projection.TestSessionGitProjection.test_real_split_dot_matches_commit_tree tests.test_contract_engineering.TestContractEngineering.test_split_session_gate_real_tree_reviewer_and_final_binding
git diff --check
```

Expected：0F/E/skip，实际两个method加载且执行，不把模拟skipguard的受测结果计入原生信用。作者自SPEC/QUALITY后 freshSPEC→不同QUALITY；root全局 freshSPEC→不同QUALITY完成后才冻结源Task4。

### Task 3 实际履历（2026-10-09，root 汇总）

fresh 作者 `/root/session_git_task3_implementation` 仅改 CI loader 与其 guard；真实 RED 为新 guard 1方法/F1/E0/skip0、0.065s、exit1，selected为空而真实 loader 得到12项 expected。随后原 POSIX contract 集合加2方法，新增精确12项 SESSION_GIT_PROJECTION_TESTS 并展开 required 集合；唯一 guard 验完整选择、准确 case/type/id、无静态 skip，逐12个 synthetic required skip 实际返回1。原 main/ARGV/required-intersection/平台判断/50个跨平台 ID 保持。POSIX required 当前20项（原 oracle1+contract7+core12），非POSIX DEFAULT 不选新增POSIX方法；guard本身portable，Windows仅静态核。

作者 strictprefix 串行 GREEN：guard module24/0.154s、脚本指定两真实方法2/1.008s；自SPEC→自QUALITY C0/I0/M0。fresh SPEC `/root/session_git_task3_spec` 独立24/0.176s与2/1.021s，C0/I0/M0；不同 QUALITY `/root/session_git_task3_quality` 独立24/0.160s与2/1.090s，C0/I0/M0。各次0F/E/skip、exit0，diff检查0。synthetic skip只授拒绝机制，不计作原生执行；实际2方法仍分别授真实 Git/session和真实CP/operation/受控Reviewer/final source binding，broker/model是double。

Task3冻结 loader SHA256 `6e46fb09bae2673a583da0f41e9abe0b4fe638b0f5f0f08f35d6da75e339a4c7`；guard SHA256 `4ce8d7eb98c6db73ea559e0d979bf1ac9b9948459266d7d8d43e1a3f6d055f58`。前片 runner/core/contract 三SHA保持Task2文案后的冻结；main8d、vendor169 clean、Native False未变。作者和两审查均STOP，20轮、DEFAULT、原full、额外compile与发布尚未执行，交 root 全局双审后Task4。

## Task 4: 冻结源总体软件验收、文档与精确 main 发布

**状态**

- [x] 任务完成（本片软件/发布与终态观察收尾；非整体 CI/Native 通过）

**Dependencies:** Task 3

**Parallelizable:** No (root唯一测试/发布执行器；源码冻结不和测试/编辑并行，发布后只读观察可并行下一设计)

- [x] **Step 1: root全局审查后冻结 five source/test/loader 文件。**

```bash
git diff -- src/icode/runner.py tests/test_session_git_projection.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
sha256sum src/icode/runner.py tests/test_session_git_projection.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
sha256sum src/icode/git_broker.py src/icode/workspace.py src/icode/workspace_snapshot.py
git -C vendor/icode-skill status --porcelain
git diff --check
```

Expected：五源冻结SHA记录在实际履历；三个不改源仍等于末尾基线，vendor无dirty。完整代码diff人工核查无measurement/resultcommit/Native/schema/权限变更。新module未跟踪时root使用只读 `git diff --no-index /dev/null tests/test_session_git_projection.py` 读新内容（该命令差异exit1不是测试失败），不忽略新文件。

- [x] **Step 2: 点测与20轮核心/接线/selection回归。**

```bash
session_git_python -m unittest tests.test_session_git_projection tests.test_contract_engineering tests.test_run_workspace_ci tests.test_verification_measurement tests.test_r3_regression.TestWorktreeGitTreeOID tests.test_git_broker.TestGitWorkspaceIdentityVerification -v
session_git_round=1
while [ "$session_git_round" -le 20 ]; do
  session_git_python -m unittest tests.test_session_git_projection tests.test_contract_engineering.TestContractEngineering.test_split_session_gate_real_tree_reviewer_and_final_binding tests.test_contract_engineering.TestContractEngineering.test_split_session_reviewer_and_final_boundary_reject_real_drift tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_session_git_projection_methods_selected_once_and_required -v || break
  session_git_round=$((session_git_round + 1))
done
test "$session_git_round" -eq 21
```

Expected：实际20轮逐轮记录total/F/E/skip与exit；本片required0skip，非绿色停止修复、重新审查/freeze，不靠重跑择绿。原环境skip分别列明，不从“0F/E”推“所有真实OS通过”。20是用户自检轮数，不是13向量需要13methods。

- [x] **Step 3: DEFAULT与原full恰好一次。**

```bash
session_git_python scripts/run_workspace_ci.py
session_git_python -c 'import re, sys, time
from scripts import preflight
original = preflight.subprocess.run
seen = []
def observe(*args, **kwargs):
    selected = bool(args) and args[0] == [sys.executable, "-m", "unittest"]
    if selected:
        assert len(args) == 1
        assert kwargs == dict(cwd=str(preflight.REPO), capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)
        assert not seen
        started = time.monotonic()
        result = original(*args, **kwargs)
        seen.append(result)
        print("original full child wall", time.monotonic() - started, "returncode", result.returncode, flush=True)
        for stream in (result.stdout or "", result.stderr or ""):
            for line in stream.splitlines():
                if re.search(r"^Ran [0-9]+ tests? in |^OK(?:$| \()|^FAILED|bootstrap.*binding|verifier.*binding", line, re.I):
                    print(line, flush=True)
        return result
    return original(*args, **kwargs)
preflight.subprocess.run = observe
started = time.monotonic()
try:
    code = preflight.main([])
finally:
    preflight.subprocess.run = original
assert len(seen) == 1
print("original preflight wall", time.monotonic() - started, flush=True)
sys.exit(code)'
```

Expected：DEFAULT actual成功、required0skip；原secret/submodule/tests三道成功且原child一次、argv/kwargs/结果对象不改。这是**新五源freeze**的原full，不重复8d历史full。保存actualtotal/P/F/E/skip和每个既有skip分类，不改module过滤或环境择绿。若source修改则前freeze的full不能授新freeze；先审查/freeze后新一轮唯一full，不把已失败full伪称未跑。

- [x] **Step 4: compile-j1、非测试守卫、七维实际报告。**

```bash
session_git_pyc_dir=$(mktemp -d /tmp/icode-session-git-pyc-XXXXXX)
PYTHONPYCACHEPREFIX="$session_git_pyc_dir" session_git_python -m compileall -q -j 1 src scripts tests
session_git_python scripts/check_governance.py
session_git_python scripts/check_site.py
session_git_python scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
sha256sum src/icode/runner.py tests/test_session_git_projection.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：exit0/fivefreeze相同、缓存仅仓外mktemp，不递归删除。记录源码真实tree绑定与metadata分离、错误归一化、原caller签名与CP/Reviewer等门。对照脚本只核名单/日期，不冒称20上游源码重新审查。root输出完整七维实际报告；不能用“100%”遮盖未验OS/installed/模型。

- [x] **Step 5: root追加实际履历和只读并行研究的采用决定，文档连续两轮clean。**

root只用 apply_patch更新本文状态/履历及landscape；带入此前已由root拥有的两处doc元数据和批准的新设计/研究/evidence，冻结设计不篡改历史“未实现/待复审”的交付时点。root实际 G1/G2 只读/owned-fixture 诊断记录 linux-bridge-blockers 也带入；并行 bridge 实施计划须完成其独立 SPEC→不同 QUALITY 复审后才带入，不把计划批准当实施。记录每个审查的身份、范围、结果与freezeSHA，13向量实际方法/子用例mapping、真实Git/manager/CP与double信用、剩余native/installed/model门。上游固定Codex/Aider证据与许可已经设计/landscape记录，不为此片增加框架或复制代码。

```bash
session_git_python /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-session-git-tree.md docs/nbl/specs/2026-10-09-session-git-tree-design.md docs/agent-landscape-live.md docs/nbl/specs/2026-10-09-linux-engineering-bridge-design.md docs/nbl/specs/2026-10-09-linux-engineering-bridge-upstream-research.md docs/nbl/specs/2026-10-09-linux-bridge-command-evidence.md docs/nbl/specs/2026-10-09-linux-bridge-blockers.md docs/nbl/plans/2026-10-09-linux-engineering-bridge.md docs/nbl/plans/2026-10-09-r3-workbench-python-preset.md
session_git_python /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-session-git-tree.md docs/nbl/specs/2026-10-09-session-git-tree-design.md docs/agent-landscape-live.md docs/nbl/specs/2026-10-09-linux-engineering-bridge-design.md docs/nbl/specs/2026-10-09-linux-engineering-bridge-upstream-research.md docs/nbl/specs/2026-10-09-linux-bridge-command-evidence.md docs/nbl/specs/2026-10-09-linux-bridge-blockers.md docs/nbl/plans/2026-10-09-linux-engineering-bridge.md docs/nbl/plans/2026-10-09-r3-workbench-python-preset.md
```

Expected：两轮各0疑似项，人工核计数/枚举/字段/标题/历史与当前观测。文档改动后再两轮；仅docmetadata变化不重跑同freezefull。

- [x] **Step 6: 非测试守卫、exact main索引提交推送。**

```bash
session_git_python scripts/preflight.py --only secrets
session_git_python scripts/preflight.py --only submodule
session_git_python scripts/check_governance.py
session_git_python scripts/check_site.py
session_git_python scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
git branch --show-current
git status --short
git add src/icode/runner.py tests/test_session_git_projection.py tests/test_contract_engineering.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py docs/agent-landscape-live.md docs/nbl/plans/2026-10-09-r3-workbench-python-preset.md
git add -f docs/nbl/plans/2026-10-09-session-git-tree.md docs/nbl/specs/2026-10-09-session-git-tree-design.md docs/nbl/specs/2026-10-09-linux-engineering-bridge-design.md docs/nbl/specs/2026-10-09-linux-engineering-bridge-upstream-research.md docs/nbl/specs/2026-10-09-linux-bridge-command-evidence.md docs/nbl/specs/2026-10-09-linux-bridge-blockers.md docs/nbl/plans/2026-10-09-linux-engineering-bridge.md
git diff --cached --stat
git diff --cached --check
git diff --cached --name-only
git write-tree
```

Expected：实际14路径（五源/九文档）精确索引、无vendor/gitlink/native/其它用户changes混入；新增两文档为真实阻塞诊断与已独立双审的后续 bridge 计划，后者未通过则不授索引许可。如本片实际必要路径数不同，root先核实际必要scope与新freeze，不靠硬配计数。ignoreddocs只有获准七路径exactforce-add，无`git add .`。每个indexblob须与freeze软件源/最终doc字节一致，若不一致停止查明。

```bash
git commit -m "fix: bind task Git projection to trusted workspace sessions"
git push origin main
git rev-parse HEAD
git ls-remote --heads origin
git status --short
```

Expected：commit/push实际0、remote仅main且HEAD一致，记录actualparent/tree/pathcount/SHAs。用户既有主仓本阶段授权覆盖上述操作；不创建release/分支/权限，不把push成功当CI通过。

- [x] **Step 7: root绑定新SHA持续只读观察并自动继续后续bridge。**

使用现有GitHub connector读取 **本次实际新SHA** 的CI/Pages/Windows provenance runs/jobs；记录run/job/headSHA/结论及有界一次日志获取，所有终态STOP，不再轮询8d旧run。源码scope/native/installed/模型各层分开，Windows已知10093/10038与Reviewer10035/WFP、macquota等仍单列，不能把main绿或本片Linuxhost软件绿称R2/R3总体完成。

随后按已批准 Linux engineering bridge设计制定/双审实施计划，继续真实资源→CP→operation→receipt→完整树→Reviewer→pack→独立验证与普通code/deepcheck、installed/模型门。未获得KEY真实endpoint、额外vendor Gitpipe授权等不擅自扩大；不等待用户例行“继续”，可安全推进的工作持续做。

### Task 4 root 实际履历（2026-10-09 06:11 UTC）

fresh 全局 SPEC `/root/session_git_global_spec` 与不同 QUALITY `/root/session_git_global_quality` 均 C0/I0/M0、只读、STOP；实读边界与任务审查独立，不冒称运行测试。root 核五源实际 diff、核心 fixture、相关 caller/contract/CI 与复用身份/walker路径，不冒称全文巨型 runner。最终源码冻结如下，所有下列 root 软件门之后摘要不变：

| 文件 | SHA256 |
| --- | --- |
| src/icode/runner.py | 0bc0d5e0711e88e9aee35f3a693430eb529a6d597388a32c3ff0f2defe596a83 |
| tests/test_session_git_projection.py | e87d0391ded46c25c61b3676938fa818a1e9fbcd1295b1a86adda91e71e36b94 |
| tests/test_contract_engineering.py | a807240ccfd6ad0d9a0add4104c312ce9c7a555596d8e5d3fcd00e9c24ef478d |
| scripts/run_workspace_ci.py | 6e46fb09bae2673a583da0f41e9abe0b4fe638b0f5f0f08f35d6da75e339a4c7 |
| tests/test_run_workspace_ci.py | 4ce8d7eb98c6db73ea559e0d979bf1ac9b9948459266d7d8d43e1a3f6d055f58 |

root 所有测试串行、使用本文严格既存解释器/PATH/环境，未以改平台/过滤/静态 skip 择绿：

| 实际门 | 结果 | 时间/信用 |
| --- | --- | --- |
| 定点 core12+contract39+selection24+measurement12+legacy tree6+Git identity9 | 102P、0F/E/skip、exit0 | 45.888s，逐条实际 ok 与摘要已读 |
| 20轮，每轮 core12+新增contract2+新增selection1 | 300次、15 distinct methods、每轮0F/E/skip/exit0 | 单轮6.321–7.971s，总wall135.37235273979604s；首失败停止，非并发/伪计数 |
| DEFAULT workspace | 595P、0F/E/skip、exit0；bootstrap byte-binding PASS | 171.330s；新增CI guard不是整个module入DEFAULT，故不是596 |
| 原始 full，经未改child参数/环境/result对象的preflight observer一次 | 2454total/2395P/59环境skip/0F/E、child exit0；三道及bootstrap byte-binding PASS | unittest484.469s、childwall484.8119901290629s、parent486.1531917571556s、childcount1；本freeze仅此一次 |
| compileall -q -j1 src scripts tests | exit0 | .637054715s；仓外owned cache `/tmp/icode-session-git-pyc-a8HYzt`，未删除 |
| secrets/submodule/governance/site/landscape排期/diff | 全部exit0 | governance四工作流/双README契约；site静态2HTML/6Markdown/3上游asset/2social；排期核20名单，不是20源码刷新 |

原full verbosity1只输出59skip总数，没有逐ID运行清单；不捏造其名称/类别。此前90项回归的Windows junction单skip仅属于该次回归，不能冒充本full清单。sha256 Git正控实际执行，定点/DEFAULT无skip。此前旧8d full没有重跑；后续仅文档元数据变化不重跑同源full。复用 git_broker/workspace/workspace_snapshot SHA分别仍 `e174d3fa75abb19b2c82aff835a638ac29df82665029c7be47b8063dc3a2c14e` / `4fe2dd726ef75f53175bd8e69408855174f5b84ce5fcebf76c7ed98bdf1c7753` / `56cdd4442a91c081e8cf1b86963f9894a1a55b458ff57584340229f4895d3eaf`；vendor1693651清洁、Native ready仍False。

【架构级自检报告】（仅此冻结源码的本地主机软件验收）

- ✅ 语法/编译：j1编译、原full/DEFAULT与文档结构已核；未授其它OS编译信用。
- ✅ 依赖/调用链：成对state/tree、五caller同一session、CI精确选择及现有身份/walker接口完整。
- ✅ 逻辑/边界：布局、来源/实际format/base、前后身份、真实漂移、注入拒绝与20轮通过；不承诺ABA原子快照。
- ✅ 异常处理：既有IO分类、失败归一与BaseException传播/部分tree拒绝有对应负控；非任意环境全覆盖。
- ✅ 关联模块：真实CP/operation/receipt/Reviewer协议与最后binding回归通过；model/transport double信用单列。
- ✅ 兼容安全：legacy精准参数/树语义、snapshot与普通root、旧resultcommit/平台required门保留，无vendor/native/权限变化。
- ✅ 可运行性：所列Linuxhost软件命令实际通过；Windows/macOS Native、installed桥接与真实模型未验，不能写生产100%。

已批准的后续bridge计划仅静态双审通过，未实施。G1重入设计已另独立双审，未修源码；G2 vendor身份范围修复授权未得。Windows Git pipe/Reviewer/WFP与PE来源执行、macOS quota、Linux完整Native/installed及真实模型endpoint/1→6/≥90%仍未关闭。发布与新SHA CI是下一项实际门，不将本地软件成功等同R2/R3整体完成。

### main 实际发布记录（2026-10-09 06:14 UTC）

两轮文档检查各9文件/0疑似项，人工核计数/字段/向量/平台与历史时点；最终非测试守卫全exit0。最初普通add因docs ignore返回1，已停止该链，未因此冒称索引完整；随后只对获准七个新文档exact force-add，不改ignore规则。新文档no-index检查只因新增差异返回1且空错误输出，不把tracked空diff代替检查。最终index实际14路径，逐blob SHA与五软件冻结及九最终文档文件字节全相同、cached check0，vendor/gitlink/native与下一G1 ignored设计未入索引。

commit与push均实际exit0：`923433b5d6be5e3bda05684ef4ed98daa69eb9e7`，parent `8d53670192e3e2cbfebaa0300d697fb3036308be`，tree `82bb2b07667ab1f122795b0be48b970ccc1c72c1`，14paths/4199insertions/17deletions。远程heads只有main并指同SHA，tracked工作区当次清洁。此记录是发布后的下一阶段元数据，不回写已发布tree或重跑同冻结full。

只读观察者 `/root/923433b_ci_observer` 绑定新SHA：CI `37892478455`、Pages `37892478447`、Windows provenance `37892478524`，首次06:15UTC分别queued/queued/in_progress；非终态不授通过，所有终态后停止轮询。G0本地主机源码修复/软件/发布前置已关闭，CI/目标平台信用另列；自动开始G1实施计划，不据此授bridge/Native/installed/模型完成。

### 新 SHA 终态观察收尾（2026-10-09 06:31–06:33 UTC）

独立只读 `/root/923433b_ci_observer` 按实际 `923433b5d6be5e3bda05684ef4ed98daa69eb9e7`、attempt1核下表。wrapper首30 jobs、REST仅page2补14；CI选定14日志与provenance5日志各取一次，未重取/重试/下载或运行binary，所有终态STOP。root据该独立报告登记，不冒称自身重抓19日志。

| run | 实际结论 | 关键 job / 结果 |
| --- | --- | --- |
| [CI37892478455](https://github.com/ayukyo/icode/actions/runs/37892478455) | 44jobs：37success/4failure/3retired skip | Python311 `113696266005` /312 `113696265811` 各2454total/2383P/71环境skip/0F/E，426.537/552.495s；Ubuntu `113696266115` /macOS `113696266040` 各DEFAULT595P/0skip，164.853/304.040s；bootstrap均PASS |
| [Pages37892478447](https://github.com/ayukyo/icode/actions/runs/37892478447) | success2/2 | validate `113696265446`、deploy `113696300128` |
| [Windows provenance37892478524](https://github.com/ayukyo/icode/actions/runs/37892478524) | success5/5 | validate `113696265861` 9unitP；四安装job各9unitP/0skip、19安装验签P+1buildcontextP |

Windows workspace x64 `113696266060` /ARM `113696266130` 各575total/553P/1F/1E/20skip，331.973/336.944s；实际 incremental CP inspection prepare报10093、legacy code CP baseline报10038。当前失败摘要无新Git投影失败，不等于全部Windows软件通过。两个full的71skip无逐ID清单，不补造或合并本地59。

Native：Ubuntu22 x64 `113696266425` /ARM `113696266142` 8/10、criticalTrue/readyFalse；Ubuntu latest x64 `113696266205` /24 ARM `113696266154` 7/10、criticalFalse/readyFalse；macIntel `113696266165` /ARM `113696266363` 6/10、criticalFalse/同组清理True/readyFalse。全部quota/uniform UNVERIFIED；这些是新运行观测，不覆盖旧8d的不同计数，也不将mac同组清理改回整树零残留承诺。

Reviewer x64 `113696266014` /ARM `113696266308` 均exit78/cleanupTrue/tokenNone；IPv4/6 error10035、connectedFalse/deniedFalse/waitExpiredTrue/canaryFalse。**本次target_context=valid**，observer ready/collection enabled但no_matching_event、cap_drop0、CAB archive_member_missing；不沿用旧wait_timeout、不当DENY。标准用户/部分禁写与ACL恢复的局部正证据不替代整体Reviewer失败。

四安装job/官方artifact：ARM311 `113699204976`/`11599517779`、x64312 `113699204997`/`11599298211`、x64311 `113699205004`/`11599476612`、ARM312 `113699205024`/`11599697121`；实际创建日志helper SHA与对应 [54216154](https://github.com/ayukyo/icode/attestations/54216154)、[54215663](https://github.com/ayukyo/icode/attestations/54215663)、[54215624](https://github.com/ayukyo/icode/attestations/54215624)、[54215892](https://github.com/ayukyo/icode/attestations/54215892) subject匹配，官方artifact run/head/ZIPdigest与上传日志匹配、未过期。未独立解析statement或下载运行PE；四capture parse_complete/runtime_load_verified/source_launch_verified仍全False，production_authority=none。签名安装成功不是生产Windows或R2/R3通过。

G0 Git软件/发布前置关闭；自动推进G1最小准入修复计划。G1当前仅设计双审通过/计划初审，未改源码；G2 vendor范围和Windows Gitpipe授权、Linux完整bridge/installed、各OS Native/资源与真实模型endpoint/1→6/≥90%仍分别未通过，不重试旧923工作流或改源码skip取绿。

## 验收向量映射与信用

| 向量 | 具体代码/回归 | 可授信用/限制 |
| --- | --- | --- |
| S-01 | real_split_dot_matches_commit_tree | 真实host manager/Git/rawroot投影；不是Native |
| S-02 | real_sha256_and_caller_format_base_rejection；sha1正控 | 实际格式/基线；sha256前提skip不通过required门 |
| S-03 | paths_subtrees_and_other_session_rejected | 绝对词法路径/同一根/dot范围，子树明确未支持 |
| S-04 | identity_fields_missing_duplicate_device_inode_token_rejected、session_field_layout_and_protection_validation、capture_window… | 真实verifier与固定布局；任何Git/walker前reject资格失效 |
| S-05 | metadata_real_rewrites_replacements_and_symlinks_rejected | 实际pointer/common/HEAD/ownership字节/inode/symlink变化 |
| S-06 | code_git_all_types…、missing_split_identity_same_head_injection_extra_protection_never_falls_back | 真实manager extra构造，身份None+注入有/无保护全拒绝，无Git/walker |
| S-07 | capture_window_observed_identity_head_format_and_fields_drift | 实际HEAD/pointer/rootgit及host对象/actualformat时刻double；未授原子ABA保证 |
| S-08 | tree_semantics_stability_and_existing_failures_preserved + 原 TestWorktreeGitTreeOID 回归 | 字节/mode/linktarget/nested/special/原限制语义；故障注入与真实文件分列 |
| S-09 | ordinary_snapshot_non_git_and_exact_legacy_call_shapes | 真非分层固定布局/unrelatedextra、snapshot、普通root/nonGit/子目录原边界 |
| W-01 | all_session_callers… AST/选定表达式观察 + split_gate… runtime包裹观察 | admission/resume为代码来源/表达式层；gate/Reviewer/finalbinding为真实调用层，不授wholechain |
| W-02 | split_session_gate_real_tree_reviewer_and_final_binding | 真实manager/state/tree/CP/operation/receipt/read/submit；transport/model double，不授OS模型语义 |
| W-03 | split_session_reviewer_and_final_boundary_reject_real_drift + 现有 deepcheck/resume/最后CP回归 | 真实源码/身份变化拒绝；既有开始后范围/源码不可重捕获取绿 |
| C-01 | verification_measurement、r3_regression、Gitbroker/tree/原精确double与resultcommit回归 | 旧IO/timeout/signature与根范围保持；split result-commit仍未支持 |

13向量不是任意13个方法；本计划新core类12方法（多subTest）+contract2方法+loader1方法。实施如拆分/补强必须同步精准selection/guard与mapping，不静态skip、少选、重复收集或任意扩scope。源码窗口unstable与有界walker等保证仍来自原实现，不把结束时双端核验说成点时原子快照。

## 作者自审、阅读来源与七维设计报告

sequential-thinking 三步已实际调用并记录本任务context：需求分解、串行复用方案、身份/范围/平台/证据信用风险。已完整读取 writing-plans与doc-contract-consistency-audit技能及后者检查脚本；设计179行完整读。实际源码阅读：runner原双接口与imports、contract gate/最后binding完整段、admission/resumebaseline与Reviewer末尾；workspaceSession/Identity、readGitRepositoryState及manager固定布局/_session完整相关段；git_broker verifier完整282–410及路径/identity辅助相关段；POSIX walker根与关键错误分支；工程VerificationPlan/Check真实API；CI脚本实际159–结尾入口/常量选择与loaderguard相关段。大型测试仅相关fixture/method与符号范围，不声称全文产品审查；一次组合output截断的段不计全文，后续重核具体使用API。

自SPEC：C0/I0/M0，获准设计每条scope/route/base/format/beforeafter/caller/compat与13向量已映射；不改冻结设计、不授split resultcommit/子树/native。自QUALITY：C0/I0/M0，最小runner helpers与共享真实fixture、串行TDD/双审/freezefullonce、精确methodsrequiredskip与用户main-only一致。自审不是独立批准；等待freshSPEC与不同QUALITY验本计划后交执行。

作者实际确认下列生产SHA未变；这里只是计划交付范围核对，不授软件验收：

| 文件 | 基线 SHA256 |
| --- | --- |
| runner.py | 2b145db41b3ebbd0f90f3e9d8b19e73b9ca6a08c97e1ba5fbe59d6d777ea671b |
| git_broker.py | e174d3fa75abb19b2c82aff835a638ac29df82665029c7be47b8063dc3a2c14e |
| workspace.py | 4fe2dd726ef75f53175bd8e69408855174f5b84ce5fcebf76c7ed98bdf1c7753 |
| workspace_snapshot.py | 56cdd4442a91c081e8cf1b86963f9894a1a55b458ff57584340229f4895d3eaf |

【架构级自检报告】（仅计划层）

- ✅ 语法/结构：完整Markdown与代码围栏、完整代码/命令和现有API字段人工核对；不声明已编译。
- ✅ 依赖/调用链：Task1→2→3→4；所有state/tree caller/Reviewer/最后CP/恢复与legacy独立列明。
- ✅ 逻辑/边界：严格dot/fixedlayout+protected/.git注入/实际format/同对象与固定事实前后重核。
- ✅ 异常处理：路径无关身份失败；无sessionIO分类保留；不吞BaseException/不授partialtree。
- ✅ 关联模块：CP/Plan/operation/receipt/Reviewer/source-stability门原样，不改Native/vendor/schema。
- ✅ 兼容安全：无session精准shape、合法snapshot/非分层root/unrelatedextra、旧resultcommit与平台required门保持。
- ⚠️ 可运行性：未实施、未运行任何测试/import/compile/install/model；必须由实际RED/GREEN/整体软件与目标平台证据验收，不声明100%。

---

**Execution Mode:** serial

独立计划作者只将本文交root；root在freshSPEC→不同QUALITY批准后使用 `nbl.subagent-driven-development`，每task fresh writer与审查，root最终全局review/测试/发布。并行上游研究已由独立只读代理完成并录入获准设计/landscape，不再让研究替代实际软件与Linux bridge验收。
