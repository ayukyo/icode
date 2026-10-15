# CI Reviewer stable ACL baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅为 CI 自有 Reviewer 临时树建立经过完整验证的 grant 前稳定基线，保持生产 ACL 恢复的严格等值比较。

**Architecture:** 在原 native fixture 的 snapshot seam 包装原 callable；普通 runtime/多根调用原样透传。选定 Reviewer 单根先执行原 snapshot 一次，必要时仅重设原 root DACL 一次，完整读取后树并验证唯一允许的一方向 0x400 变化，再构造全新 transaction。

**Tech Stack:** Python unittest、unittest.mock、现有 ctypes ACL API、Windows x64/ARM64 GitHub CI。

---

本文件是实施资产，不是已实施结果。基准 Agent HEAD `ca41c78d6f57938f8dd9aa1fb912dad7e44efe9c`；Skill pin `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。权威目录 `/home/orbbec/projects/icode`。用户 main-only/online-first 授权覆盖技能默认 worktree、分支与每步 commit 指引；本 PLAN 阶段不执行 Git、不落 SOURCE/TEST，不做本机 ACL 操作。先冻结 RED 测试，再由独立作者实施；根代理及两位独立审查者通过后才可启动实施。

参考规格：`docs/nbl/specs/2026-10-15-reviewer-acl-stable-baseline-design.md`。本方案仅借鉴已有 staged-runtime baseline 的原 DACL 设置机制；不调用其只检查 root 的归一化函数，不修改生产接口。微软 0x400/SetNamedSecurityInfoW 官方引用及采纳/暂缓/拒绝决策沿用规格的证据边界。三问：真实问题是双 Windows post-return root control XOR 1024；已有生产 snapshot/read/set/walk 可复用；调用链仅 fixture snapshot seam，生产 grant/restore 不变。

## 文件和冻结边界

| 文件 | 唯一责任 |
| --- | --- |
| `tests/test_windows_reviewer_acl_baseline.py`（新增） | 独立软件负控；仅 import 旧模块为 original，不直接导入旧 TestCase |
| `tests/test_windows_appcontainer.py` | 模块级 fixture baseline helper；native snapshot seam 集成；原 capture 消费 preflight；固定 ordinary log |

禁止修改 `src/icode/windows_appcontainer.py`、workflow、timeout、权限、依赖、pin、旧 restore 测试。原类 98 个 test 方法的名字集合和原 13 个 post-observation 方法均保持；新测试只在新类发现。软件 GREEN 不是 native/网络/R2/R3 验收。

### Task 1: 写入并冻结独立测试资产

**Dependencies:** None
**Parallelizable:** No (先建立同一测试资产的可信 RED)

- [x] Step 1: 新建下列完整文件；此时不要加入 Task 2 的 helper。

```python
"""Software contract for the CI-only Reviewer pre-grant ACL baseline."""
from __future__ import annotations

import ctypes
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import tests.test_windows_appcontainer as original

w = original.windows_appcontainer
ENV = {
    "GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows",
    "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
    "ICODE_DIAGNOSTIC_REVIEWER_SNAPSHOT": "true",
}


class TestReviewerAclBaseline(unittest.TestCase):
    def setUp(self):
        self.helper = getattr(original, "_prepare_reviewer_acl_baseline", None)
        self.assertTrue(callable(self.helper), "Reviewer stable baseline helper is missing")
        self.temp = tempfile.TemporaryDirectory(prefix="icode-reviewer-appcontainer-probe-")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve(strict=True)
        self.root = self.parent / ("icode-reviewer-snapshot-" + "a" * 32)
        self.root.mkdir()
        self.child = self.root / "reviewed.py"
        self.child.write_bytes(b"safe")
        self.workspace = self.parent / "task-scratch"
        self.workspace.mkdir()
        self.advapi, self.kernel = object(), object()
        self.entries = tuple(self.state(p) for p in (self.root, self.child))
        self.before = w._RuntimeAclTransaction(
            roots=(self.root,), entries=self.entries,
            advapi=self.advapi, kernel=self.kernel, snapshot_duration_ms=7,
        )
        self.report = {}
        self.delegate = mock.Mock(return_value=self.before)
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)

    def state(self, path, **changes):
        info = path.lstat()
        value = w._DaclSnapshot(
            path=path, dacl=b"original-acl", control=4, revision=1,
            present=True, defaulted=False,
            file_identity=(int(info.st_dev), int(info.st_ino)),
        )
        return replace(value, **changes)

    def call(self, roots=None, **changes):
        options = dict(snapshot=self.root, temp_parent=self.parent,
                       workspace=self.workspace, advapi=self.advapi,
                       kernel=self.kernel, report=self.report)
        options.update(changes)
        return self.helper(self.delegate, (self.root,) if roots is None else roots,
                           **options)

    def after(self, path, _advapi, _kernel):
        return replace(next(e for e in self.entries if e.path == path),
                       control=next(e for e in self.entries if e.path == path).control | 0x400)

    def test_permitted_change_returns_fresh_complete_transaction(self):
        written = []
        def capture_set(path, pointer, advapi):
            written.append((path, ctypes.string_at(pointer, len(self.entries[0].dacl)), advapi))
        with mock.patch.object(w, "_read_dacl_state", side_effect=self.after) as read, \
             mock.patch.object(w, "_set_dacl", side_effect=capture_set) as setter, \
             mock.patch.object(w, "_walk_workspace", wraps=w._walk_workspace) as walk:
            result = self.call()
        self.assertIsNot(result, self.before)
        self.assertIs(result.roots, self.before.roots)
        self.assertIs(result.advapi, self.advapi)
        self.assertIs(result.kernel, self.kernel)
        self.assertEqual(result.modified_roots, [])
        self.assertEqual(result.entries, tuple(self.after(e.path, None, None) for e in self.entries))
        self.assertGreaterEqual(result.snapshot_duration_ms, 0)
        self.delegate.assert_called_once_with((self.root,), workspace=self.workspace,
                                              advapi=self.advapi, kernel=self.kernel)
        setter.assert_called_once()
        self.assertEqual(setter.call_args.args[0], self.root)
        self.assertEqual(written, [(self.root, self.entries[0].dacl, self.advapi)])
        self.assertIs(setter.call_args.args[2], self.advapi)
        self.assertEqual(read.call_count, 2)
        self.assertEqual(walk.call_args.kwargs["max_entries"], 3)
        self.assertEqual(self.report, {"phase": "pre_grant_baseline", "state": "primed",
                                      "objects": 2, "changed": 2})
        self.assertEqual(self.before.entries, self.entries)

    def test_already_stable_returns_original_without_set_or_postread(self):
        self.before.entries = tuple(replace(e, control=e.control | 0x400) for e in self.entries)
        with mock.patch.object(w, "_set_dacl") as setter, \
             mock.patch.object(w, "_read_dacl_state") as read:
            self.assertIs(self.call(), self.before)
        setter.assert_not_called()
        read.assert_not_called()
        self.assertEqual(self.before.snapshot_duration_ms, 7)
        self.assertEqual(self.report["state"], "already_stable")

    def test_foreign_and_multi_root_pass_original_arguments_once(self):
        for roots in ([self.root], [self.child], [self.root, self.child], []):
            with self.subTest(roots=roots):
                self.delegate.reset_mock()
                with mock.patch.object(w, "_set_dacl") as setter:
                    self.assertIs(self.call(roots), self.before)
                self.delegate.assert_called_once_with(roots, workspace=self.workspace,
                                                      advapi=self.advapi, kernel=self.kernel)
                setter.assert_not_called()
                self.assertEqual(self.report, {})

    def test_each_optout_passes_through(self):
        for key in ENV:
            with self.subTest(key=key), mock.patch.dict(os.environ, {key: "false"}), \
                 mock.patch.object(w, "_set_dacl") as setter:
                self.delegate.reset_mock()
                self.assertIs(self.call(), self.before)
                self.delegate.assert_called_once()
                setter.assert_not_called()
                self.assertEqual(self.report, {})

    def test_bad_target_binding_fails_before_set(self):
        for parent, name in ((self.parent.parent, self.root),
                             (self.parent, self.parent / "icode-reviewer-snapshot-invalid")):
            with self.subTest(parent=parent, name=name), \
                 mock.patch.object(w, "_set_dacl") as setter:
                with self.assertRaises(w._AppContainerSetupError):
                    self.call((name,), snapshot=name, temp_parent=parent)
                setter.assert_not_called()
                self.assertEqual(self.report["state"], "failed")
                self.assertIsNone(self.report["changed"])

    def test_nested_probe_parent_is_rejected_before_delegate_or_set(self):
        nested_parent = self.parent / "icode-reviewer-appcontainer-probe-nested"
        nested_parent.mkdir()
        nested_root = nested_parent / ("icode-reviewer-snapshot-" + "b" * 32)
        nested_root.mkdir()
        with mock.patch.object(w, "_set_dacl") as setter:
            with self.assertRaises(w._AppContainerSetupError):
                self.call((nested_root,), snapshot=nested_root, temp_parent=nested_parent)
            setter.assert_not_called()
            self.delegate.assert_not_called()

    def test_invalid_before_metadata_and_transaction_shape_fail_before_set(self):
        bad_entries = [(), (self.entries[1],), (self.entries[0], self.entries[0])]
        for change in ({"control": 0x1004}, {"defaulted": True}, {"present": False},
                       {"file_identity": (1, 0)}, {"file_identity": (1, -1)},
                       {"file_identity": (True, 1)}, {"dacl": b""}, {"revision": 0}):
            bad_entries.append((replace(self.entries[0], **change), self.entries[1]))
        for entries in bad_entries:
            with self.subTest(entries=entries), mock.patch.object(w, "_set_dacl") as setter:
                self.before.entries = entries
                with self.assertRaises(w._AppContainerSetupError):
                    self.call()
                setter.assert_not_called()
        self.before.entries = self.entries
        self.before.modified_roots.append(self.root)
        with mock.patch.object(w, "_set_dacl") as setter:
            with self.assertRaises(w._AppContainerSetupError):
                self.call()
            setter.assert_not_called()

    def test_before_roots_and_api_identity_must_match(self):
        for changes in ({"roots": (self.child,)}, {"advapi": object()}, {"kernel": object()}):
            before = w._RuntimeAclTransaction(
                roots=self.before.roots, entries=self.entries, advapi=self.advapi,
                kernel=self.kernel, snapshot_duration_ms=7,
            )
            for key, value in changes.items():
                setattr(before, key, value)
            with self.subTest(changes=changes), mock.patch.object(w, "_set_dacl") as setter:
                self.delegate.return_value = before
                with self.assertRaises(w._AppContainerSetupError):
                    self.call()
                setter.assert_not_called()

    def test_every_unpermitted_after_field_is_rejected(self):
        for changes in ({"dacl": b"other"}, {"revision": 2}, {"present": False},
                        {"defaulted": True}, {"file_identity": (1, 99)},
                        {"control": 4}, {"control": 0xC04}, {"path": self.child}):
            with self.subTest(changes=changes), mock.patch.object(w, "_set_dacl"), \
                 mock.patch.object(w, "_read_dacl_state", side_effect=lambda p, a, k:
                                   replace(self.after(p, a, k), **changes)):
                with self.assertRaises(w._AppContainerSetupError):
                    self.call()
                self.assertEqual(self.report["state"], "failed")

    def test_reverse_marker_change_is_rejected(self):
        self.entries = (replace(self.entries[0], control=0x404), self.entries[1])
        self.before.entries = self.entries
        with mock.patch.object(w, "_set_dacl"), \
             mock.patch.object(w, "_read_dacl_state", side_effect=lambda p, a, k:
                               replace(self.after(p, a, k), control=4)):
            with self.assertRaises(w._AppContainerSetupError):
                self.call()

    def test_child_only_metadata_drift_is_rejected_after_valid_root(self):
        changes_to_reject = (
            {"dacl": b"child-drift"}, {"control": 0xC04}, {"revision": 2},
            {"present": False}, {"defaulted": True},
            {"file_identity": (1, 99)}, {"path": self.root},
        )
        for changes in changes_to_reject:
            read_paths = []
            def read(path, advapi, kernel):
                read_paths.append(path)
                legal = self.after(path, advapi, kernel)
                return replace(legal, **changes) if path == self.child else legal
            with self.subTest(changes=changes), mock.patch.object(w, "_set_dacl"), \
                 mock.patch.object(w, "_read_dacl_state", side_effect=read):
                with self.assertRaises(w._AppContainerSetupError):
                    self.call()
                self.assertEqual(read_paths, [self.root, self.child])
                self.assertEqual(self.report["state"], "failed")
                self.assertEqual(self.report["objects"], 2)
                self.assertIsNone(self.report["changed"])

    def test_tree_addition_and_removal_fail(self):
        for operation in ("add", "remove"):
            with self.subTest(operation=operation):
                def mutate(*_args):
                    if operation == "add":
                        (self.root / "added").write_bytes(b"extra")
                    else:
                        self.child.unlink()
                with mock.patch.object(w, "_set_dacl", side_effect=mutate), \
                     mock.patch.object(w, "_read_dacl_state", side_effect=self.after):
                    with self.assertRaises(w._AppContainerSetupError):
                        self.call()
                (self.root / "added").unlink(missing_ok=True)
                if not self.child.exists():
                    self.child.write_bytes(b"safe")

    def test_reparse_delegate_rejection_never_sets(self):
        self.delegate.side_effect = w._AppContainerSetupError("unsupported_runtime_root", "fixed")
        with mock.patch.object(w, "_set_dacl") as setter:
            with self.assertRaises(w._AppContainerSetupError):
                self.call()
            setter.assert_not_called()

    def test_setter_and_read_failure_prevent_return(self):
        for stage in ("set", "read"):
            with self.subTest(stage=stage), \
                 mock.patch.object(w, "_set_dacl", side_effect=RuntimeError("fixed") if stage == "set" else None), \
                 mock.patch.object(w, "_read_dacl_state", side_effect=RuntimeError("fixed")):
                with self.assertRaises(w._AppContainerSetupError):
                    self.call()
                self.assertEqual(self.report["state"], "failed")
                self.assertIsNone(self.report["changed"])

    def test_one_deadline_covers_delegate_set_walk_and_each_read(self):
        for stage in ("delegate", "set", "walk", "read"):
            clock = [0.0]
            def delegated(*args, **kwargs):
                if stage == "delegate": clock[0] = 31.0
                return self.before
            def setter(*args):
                if stage == "set": clock[0] = 31.0
            def walk(*args, **kwargs):
                self.assertEqual(kwargs["deadline"], 30.0)
                if stage == "walk": clock[0] = 31.0
                return [self.root, self.child]
            def read(p, a, k):
                if stage == "read": clock[0] = 31.0
                return self.after(p, a, k)
            with self.subTest(stage=stage), \
                 mock.patch.object(original.time, "monotonic", side_effect=lambda: clock[0]), \
                 mock.patch.object(w, "_set_dacl", side_effect=setter), \
                 mock.patch.object(w, "_walk_workspace", side_effect=walk), \
                 mock.patch.object(w, "_read_dacl_state", side_effect=read):
                self.delegate.side_effect = delegated
                with self.assertRaises(w._AppContainerSetupError):
                    self.call()
                self.assertEqual(self.report["state"], "failed")

    def test_duration_includes_delegate_and_postread(self):
        clock = [1.0]
        def delegated(*args, **kwargs):
            clock[0] = 3.0
            return self.before
        def read(p, a, k):
            clock[0] += 0.5
            return self.after(p, a, k)
        self.delegate.side_effect = delegated
        with mock.patch.object(original.time, "monotonic", side_effect=lambda: clock[0]), \
             mock.patch.object(w, "_set_dacl"), \
             mock.patch.object(w, "_read_dacl_state", side_effect=read):
            result = self.call()
        self.assertEqual(result.snapshot_duration_ms, 3000)

    def test_fixed_log_uses_ordinary_output_and_existing_size_gate(self):
        host = original.TestWindowsAppContainer()
        report = {"phase": "pre_grant_baseline", "state": "primed", "objects": 2, "changed": 2}
        stream = io.StringIO()
        with mock.patch("sys.stdout", stream), mock.patch.object(host, "_workflow_notice") as notice:
            host._workflow_json_notice("Windows Reviewer snapshot ACL pre-grant baseline", report)
        notice.assert_not_called()
        line = stream.getvalue().strip()
        self.assertTrue(line.startswith("reviewer_snapshot_acl_baseline="))
        self.assertEqual(json.loads(line.split("=", 1)[1]), report)
        with self.assertRaises(AssertionError):
            host._workflow_json_notice("Windows Reviewer snapshot ACL pre-grant baseline", {"state": "x" * 501})

    def test_native_capture_consumes_the_actual_baseline_wrapper(self):
        method = original.TestWindowsAppContainer.test_Reviewer快照原生探针脚本在非Windows主机可静态解析
        method(original.TestWindowsAppContainer(method.__name__))

    def test_native_log_failure_happens_after_wfp_cleanup(self):
        method = original.TestWindowsAppContainer.test_Reviewer快照原生探针脚本在非Windows主机可静态解析
        host_class = original.TestWindowsAppContainer
        real_notice = host_class._workflow_json_notice
        real_stop = original._stop_wfp_event_probe
        cleanup = []
        def stopped(*args, **kwargs):
            cleanup.append(True)
            return real_stop(*args, **kwargs)
        def notice(host, name, report):
            if name == "Windows Reviewer snapshot ACL pre-grant baseline":
                self.assertTrue(cleanup, "baseline logging preceded WFP cleanup")
                raise RuntimeError("synthetic baseline log failure")
            return real_notice(host, name, report)
        with mock.patch.object(original, "_stop_wfp_event_probe", side_effect=stopped), \
             mock.patch.object(host_class, "_workflow_json_notice", notice):
            with self.assertRaisesRegex(RuntimeError, "synthetic baseline log failure"):
                method(host_class(method.__name__))
        self.assertTrue(cleanup)


if __name__ == "__main__":
    unittest.main()
```

- [x] Step 2: 用下列命令核对现有 capture 方法唯一名称为 `test_Reviewer快照原生探针脚本在非Windows主机可静态解析`；与资产不一致时停止并修订 PLAN，不在冻结后变更测试。

```bash
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python - <<'PY'
import ast
from pathlib import Path
s=Path('tests/test_windows_appcontainer.py').read_text()
t=ast.parse(s)
for n in ast.walk(t):
    if isinstance(n, ast.FunctionDef) and n.name.startswith('test_') and '_CaptureAssertions' in ast.get_source_segment(s,n):
        print(n.name)
PY
```

- [x] Step 3: 在 WSL actual311 只运行新模块：`PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -m unittest tests.test_windows_reviewer_acl_baseline -v`。预期全部在 setUp 得到 AssertionError `Reviewer stable baseline helper is missing`，不是 ImportError/AttributeError。记录完整日志、退出码及测试文件 SHA256。由独立测试作者确认全部失败来自未实现特性后冻结测试。

### Task 2: 加入唯一 fixture helper 和原方法最小集成

**Dependencies:** Task 1
**Parallelizable:** No (必须在冻结 Assertion RED 后由另一作者实施)

- [x] Step 1: 在旧测试模块 `class TestWindowsAppContainer` 之前加入下列完整模块级 helper；不改 production。

```python
def _prepare_reviewer_acl_baseline(
    snapshot_call, roots, *, snapshot, temp_parent, workspace, advapi, kernel, report,
):
    """Prime only the selected CI-owned fixture before any Package SID grant."""
    opted_in = all(os.environ.get(key) == value for key, value in (
        ("GITHUB_ACTIONS", "true"), ("RUNNER_OS", "Windows"),
        ("ICODE_DIAGNOSTIC_RUNTIME_STAGING", "true"),
        ("ICODE_DIAGNOSTIC_REVIEWER_SNAPSHOT", "true"),
    ))
    if not opted_in or roots != (snapshot,):
        return snapshot_call(roots, workspace=workspace, advapi=advapi, kernel=kernel)
    started = time.monotonic()
    deadline = started + windows_appcontainer._MAX_RUNTIME_ACL_SNAPSHOT_SECONDS
    report.update(phase="pre_grant_baseline", state="failed", objects=None, changed=None)
    auto_inherited = windows_appcontainer._SE_DACL_AUTO_INHERITED

    def reject():
        raise _AppContainerSetupError(
            "reviewer_acl_baseline_failed", "Reviewer fixture baseline validation failed",
        )

    def checkpoint():
        if time.monotonic() > deadline:
            reject()

    try:
        checkpoint()
        name = snapshot.name
        prefix = "icode-reviewer-snapshot-"
        if (snapshot.parent != temp_parent or not temp_parent.is_absolute()
                or temp_parent.parent != Path(tempfile.gettempdir()).resolve(strict=True)
                or not temp_parent.name.startswith("icode-reviewer-appcontainer-probe-")
                or not name.startswith(prefix) or len(name) != len(prefix) + 32
                or any(c not in "0123456789abcdef" for c in name[len(prefix):])):
            reject()
        # The original validator inspects lexical ancestry for reparse points
        # before resolve; never replace it by a resolve-only containment test.
        before = snapshot_call(roots, workspace=workspace, advapi=advapi, kernel=kernel)
        checkpoint()
        if (snapshot.resolve(strict=True) != snapshot
                or temp_parent.resolve(strict=True) != temp_parent
                or before.roots != (snapshot,) or before.modified_roots
                or before.advapi is not advapi or before.kernel is not kernel):
            reject()
        entries = before.entries
        if not entries or len(entries) > windows_appcontainer._MAX_RUNTIME_ACL_OBJECTS:
            reject()
        paths = tuple(e.path for e in entries)
        if (paths[0] != snapshot or len(set(paths)) != len(paths)
                or any(p != snapshot and not p.is_relative_to(snapshot) for p in paths)):
            reject()
        for entry in entries:
            checkpoint()
            identity = entry.file_identity
            if (entry.protected or entry.defaulted or not entry.present
                    or not isinstance(entry.dacl, bytes) or not entry.dacl
                    or type(entry.revision) is not int or entry.revision < 1
                    or not isinstance(identity, tuple) or len(identity) != 2
                    or any(type(value) is not int for value in identity)
                    or identity[0] < 0 or identity[1] <= 0):
                reject()
        report["objects"] = len(entries)
        if all(entry.control & auto_inherited for entry in entries):
            checkpoint()
            report.update(state="already_stable", changed=0)
            return before
        original_acl = ctypes.create_string_buffer(entries[0].dacl)
        checkpoint()
        windows_appcontainer._set_dacl(
            snapshot, ctypes.cast(original_acl, ctypes.c_void_p), advapi,
        )
        checkpoint()
        actual_paths = windows_appcontainer._walk_workspace(
            snapshot, max_entries=len(entries) + 1, deadline=deadline,
        )
        checkpoint()
        if len(actual_paths) != len(paths) or set(actual_paths) != set(paths):
            reject()
        after = []
        changed = 0
        for old in entries:
            checkpoint()
            new = windows_appcontainer._read_dacl_state(old.path, advapi, kernel)
            checkpoint()
            if (new.path != old.path or new.dacl != old.dacl
                    or new.control != (old.control | auto_inherited)
                    or new.revision != old.revision or new.present != old.present
                    or new.defaulted != old.defaulted
                    or new.file_identity != old.file_identity):
                reject()
            changed += int(new.control != old.control)
            after.append(new)
        checkpoint()
        result = windows_appcontainer._RuntimeAclTransaction(
            roots=before.roots, entries=tuple(after), advapi=before.advapi,
            kernel=before.kernel,
            snapshot_duration_ms=int((time.monotonic() - started) * 1000),
        )
        checkpoint()
        report.update(state="primed", changed=changed)
        return result
    except _AppContainerSetupError:
        raise
    except Exception as exc:
        raise _AppContainerSetupError(
            "reviewer_acl_baseline_failed", "Reviewer fixture baseline preparation failed",
        ) from exc
```

- [x] Step 2: 旧 `_workflow_json_notice` 中 `if name == "Windows Reviewer snapshot ACL post-restore observation":` 之前插入精确分支，保留已有 500 gate 和所有 annotation slots：

```python
        if name == "Windows Reviewer snapshot ACL pre-grant baseline":
            if (
                os.environ.get("GITHUB_ACTIONS") == "true"
                and os.environ.get("RUNNER_OS") == "Windows"
                and os.environ.get("ICODE_DIAGNOSTIC_RUNTIME_STAGING") == "true"
                and os.environ.get("ICODE_DIAGNOSTIC_REVIEWER_SNAPSHOT") == "true"
            ):
                print("reviewer_snapshot_acl_baseline=" + encoded, flush=True)
            return
```

- [x] Step 3: nativebody 中原 `original_restore = ...` 之前插入：

```python
                baseline_report: dict[str, object] = {
                    "phase": "pre_grant_baseline", "state": "failed", "objects": None, "changed": None,
                }
                original_snapshot = windows_appcontainer._snapshot_runtime_acl_roots
```

将原 restore patch 的结束 `):` 改为下列并列 patch；原 restore lambda 和候选调用全部原样保留：

```python
                    ), mock.patch.object(
                        windows_appcontainer, "_snapshot_runtime_acl_roots",
                        side_effect=lambda roots, **kwargs: _prepare_reviewer_acl_baseline(
                            original_snapshot, roots, snapshot=snapshot,
                            temp_parent=snapshot.parent, report=baseline_report, **kwargs,
                        ),
                    ):
```

namespace invariant：选定 `snapshot` 已在原 fixture 中 resolve 为 canonical；传入其 `snapshot.parent`，避免 Windows TemporaryDirectory raw 8.3 spelling 与 canonical root 混用造成误拒。其余 temp_root 使用不变，foreign pass-through 不增 I/O。此集成代码资产相对前版唯一一行变化为 `temp_parent=temp_root` → `temp_parent=snapshot.parent`；逆向替换该行即可恢复前版代码资产（本说明文字除外）。

在现有 `finally:` 原 runner relay 与 `_stop_wfp_event_probe` 清理全部完成之后、与原 postrestore notice 同层且位于该 notice 之前插入。不得放入 finally 开头；日志失败不能阻断原清理：

```python
                self._workflow_json_notice(
                    "Windows Reviewer snapshot ACL pre-grant baseline", baseline_report,
                )
```

- [x] Step 4: 最小适配现有 static capture，让 fake runner 真调用新增 snapshot wrapper。旧 `transaction = SimpleNamespace(roots=...)` 块替换为：

```python
                selected_root = tuple(_kwargs["_diagnostic_reviewer_snapshot_roots"])[0]
                transaction = windows_appcontainer._snapshot_runtime_acl_roots(
                    (selected_root,), workspace=_kwargs["cwd"],
                    advapi=capture_advapi, kernel=capture_kernel,
                )
                self.assertEqual(transaction.roots, (selected_root,))
                self.assertTrue(all(e.control & 0x400 for e in transaction.entries))
```

在 `capture_runner` 定义之前加入以下完整 fake native snapshot；它只模拟已稳定对象，不模拟 baseline wrapper：

```python
            capture_advapi, capture_kernel = object(), object()

            def capture_snapshot(roots, *, workspace, advapi, kernel):
                paths = windows_appcontainer._walk_workspace(roots[0])
                entries = []
                for path in paths:
                    info = path.lstat()
                    entries.append(windows_appcontainer._DaclSnapshot(
                        path=path, dacl=b"synthetic-stable-acl", control=0x404,
                        revision=1, present=True, defaulted=False,
                        file_identity=(int(info.st_dev), int(info.st_ino)),
                    ))
                return windows_appcontainer._RuntimeAclTransaction(
                    roots=tuple(roots), entries=tuple(entries), advapi=advapi,
                    kernel=kernel, snapshot_duration_ms=0,
                )
```

在 static capture 将下列原片段：

```python
                ), mock.patch.object(
                    windows_appcontainer, "_restore_runtime_acl_roots",
```

精确替换为：

```python
                ), mock.patch.object(
                    windows_appcontainer, "_snapshot_runtime_acl_roots",
                    side_effect=capture_snapshot,
                ), mock.patch.object(
                    windows_appcontainer, "_restore_runtime_acl_roots",
```

不得删除 restore patch 的其余参数。无需为 `_CaptureAssertions` 添加 helper method，因为新增 helper 位于模块层；其现有 `_workflow_json_notice`、`assertLessEqual` 已满足日志路径。在 capture 现有 `self.assertEqual(len(captured_acl_restores), 1)` 后加入：

```python
        baseline_lines = [line for line in wfp_output.getvalue().splitlines()
                          if line.startswith("reviewer_snapshot_acl_baseline=")]
        self.assertEqual(len(baseline_lines), 1)
        baseline_receipt = json.loads(baseline_lines[0].split("=", 1)[1])
        self.assertEqual(baseline_receipt["phase"], "pre_grant_baseline")
        self.assertEqual(baseline_receipt["state"], "already_stable")
        self.assertGreater(baseline_receipt["objects"], 1)
        self.assertEqual(baseline_receipt["changed"], 0)
```

- [x] Step 5: 在任何落 SOURCE 前，独立审查者把以上代码仅投影到内存 AST、compile 和针对性 replay。相同冻结测试先对原代码 Assertion RED、再对投影代码 GREEN，记录测试 SHA 不变；投影验证不替代正式实施后的实际文件测试。

### Task 3: 软件验收与独立双审

**Dependencies:** Task 2
**Parallelizable:** No (集成和冻结测试必须完成)

- [x] Step 1: 运行同一新模块和实际 capture 方法，预期 exit 0；只运行针对性回归，不做本机 full/native。命令：

```bash
PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -m unittest tests.test_windows_reviewer_acl_baseline -v
```

- [x] Step 2: 用 AST 对实施前后旧类 `test_` 名集合严格比较应仍为 98 个，原 13 项 post-observation 集合与其方法内容逐项保持；production/workflow/pin hash 不变。新模块不得因 import TestCase 别名发现旧测试。执行 `python -m compileall -q tests/test_windows_appcontainer.py tests/test_windows_reviewer_acl_baseline.py`，只作为语法软件检查。

- [x] Step 3: 两位独立审查分别核对 SPEC/QUALITY 与 frozen TEST/source 投影。审查必须检查所有 after 字段、N+1 上界、一次 delegate/一次 Set、no-op identity、30 秒聚合 budget、失败不 launch、日志无路径/SID/ACL/异常文本、原 postrestore wrapper 并列保留。任何发现先修 PLAN，再重新审，不先落 SOURCE。

### Task 4: 候选与原生证据交接

**Dependencies:** Task 3
**Parallelizable:** No (既有所有 Agent run terminal 且独立审通过才可候选推送)

- [ ] Step 1: 根代理遵循既有 main-only/online-first 授权，先确认当前所有 Agent runs terminal、必要本机密钥扫描和固定子仓完整性通过，再将候选推送 main 触发既有 CI。不得更改 workflow、取消旧失败或反复重跑隐藏失败；本 PLAN 作者不执行 Git。
- [ ] Step 2: 对 candidate SHA 绑定 dual Windows x64/ARM64 原日志/job/exit。要求 baseline `primed` 或 `already_stable` 后 unchanged strict restore 通过；report 不能代替 restore assertion。30 秒只是同步 native call 前后软件 checkpoint，不是可中断硬 timeout。
- [ ] Step 3: 网络 DENY、WP0b、macOS、Linux/R3 和整体 R2/R3 独立保留原门。仅两个 Windows baseline/restore 通过仍不可宣称产品 ready、原因唯一或全阶段完成。

## 自 SPEC / QUALITY 检查

Task 1 覆盖独立测试发现、Assertion RED、pass-through、全部 opt-in、目标绑定、before 元数据、modified roots、no-op、单向变化、after 每字段、reverse、增删、identity、更换/异常、reparse delegate、budget、duration、固定日志和实际 native capture；Task 2 覆盖一次 delegate/Set、原 API 注入、完整 after transaction 和并列 postrestore；Task 3 覆盖 frozen tests 与旧方法不变；Task 4 覆盖线上证据及未通过门保留。

2026-10-15 最新修订内存验证记录（actual311 软件层）：同一 TEST 资产原 SOURCE 19/19 Assertion RED，0 errors，所有失败均包含缺失 helper 的固定断言；投影 SOURCE 19/19 GREEN，0 failures、0 errors，耗时约 5.21 秒。最新增加 root 合法而仅 child 的 DACL/control 其它位/revision/present/defaulted/identity/path 各字段漂移拒绝，确认两次读取与 failed/objects=2/changed=None。helper/native 初始 objects、changed 均 None；完整 before 验证后 objects=N，already_stable 明确 changed=0，primed 完整验证后才记录真实 changed count，失败从不伪称 changed=0。helper 复用现有 `_SE_DACL_AUTO_INHERITED` 常量并给预期 OR 加括号，测试保留独立 literal。此前增加的嵌套伪 probe-parent、实际 capture 日志异常清理顺序、单元素 list 透传负控均继续通过。前版投影 AST 原/后旧类均 98 个 test 方法，本次只增模块 helper、既有方法内插入，不增加旧方法。此前原 SOURCE 的 `test_JSON工作流回执超限时必须显式失败` 与 `test_runtime_ACL恢复诊断只报告脱敏的不匹配类别` 定向 2/2 通过，不声称全部原 post-observation 已重跑。inspect.getsource 的 linecache 使用投影全文与 None mtime；finally 恢复 linecache、sys.modules 和 tests package attribute。实际 TEST/SOURCE 文件未落地，未执行本机全量或 native。

TEST fenced asset SHA256 `4594d0f48b384bdece7829108812916aadf339acd52976bf6b19793fdbea3d02`；helper fenced asset SHA256 `42f28e567482b046f29d293a046a326cd02dfd746fad6aef679e156250f10322`（均按代码块 UTF-8 字节含末尾换行）。当前 PLAN 尚须全文与独立双审；内存软件 GREEN 不代表正式实施或 native 成功。实现时如发现代码资产不匹配实际源码，应停止该任务修 PLAN 并重新审查，不能把测试自身错误登记为产品 RED。

【架构级自检报告】
- 语法/编译：TEST 与投影 SOURCE 内存 compile 通过。
- 依赖/调用链：真实 snapshot seam/read/set/walk 字段已核对，最终需独立审查。
- 逻辑/边界：19 个测试同资产原 RED / 投影 GREEN；原生边界未验证。
- 异常处理：软件负控通过；candidate fail-closed 原生验收仍待 CI。
- 关联模块：仅测试层两文件；production/workflow/pin 禁改。
- 兼容安全：旧 98 方法与原 13 post-observation 保持为验收门。
- 可运行性：仅内存投影软件通过，尚未实施；dual-native 验收未建立。

---
**Execution Mode:** serial

历史冻结门：原 PLAN SHA `6fa7b56ba4b4e42e0837a5bc062db3ef5f37d82c03515e7cd8523205f08d20b6` 已经 root 全文及独立 SPEC/QUALITY 双审后进入实施。以上勾选仅记录软件步骤，不修改代码资产。独立 TEST/root 正式 19 Assertion RED 后，不同 SOURCE 作者实现；root 新19＋旧13合32软件通过、0跳过，原98方法与保护文件逐字节核验通过。实际 SOURCE SHA `3fcb8ab511c99ad76e7e39bd17a0ce3acb1dae7a97d07300e485e58a52e3419e`。全片质量审查、候选推送及双原生结果仍待，不授 R2/R3 完成。

后续全片审结：fresh GLOBAL SPEC 与不同 GLOBAL QUALITY 均 C0/I0/M0；QUALITY 亲核当前执行 ledger、冻结资产及实际32项软件GREEN。仅候选推送与双Windows原生结果待办，不授原生恢复、网络或R2/R3通过。
