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
