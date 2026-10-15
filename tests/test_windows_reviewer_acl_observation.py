"""Software-only checks for the real Reviewer post-restore observation seam."""
from __future__ import annotations

import contextlib
import ctypes
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests import test_windows_appcontainer as original


OPT_IN = {
    "GITHUB_ACTIONS": "true", "RUNNER_OS": "Windows",
    "ICODE_DIAGNOSTIC_RUNTIME_STAGING": "true",
    "ICODE_DIAGNOSTIC_REVIEWER_SNAPSHOT": "true",
}
LABEL = "Windows Reviewer snapshot ACL post-restore observation"
PREFIX = "reviewer_snapshot_acl_observation="


class TestReviewerAclObservation(unittest.TestCase):
    def setUp(self):
        self.case = original.TestWindowsAppContainer()
        self.api = original.windows_appcontainer
        self.temporary = tempfile.TemporaryDirectory(prefix="icode-acl-observation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "snapshot"
        self.root.mkdir()
        self.child = self.root / "reviewed.py"
        self.child.write_bytes(b"fixture")
        self.entries = tuple(self.snapshot(path) for path in (self.root, self.child))
        self.transaction = self.api._RuntimeAclTransaction(
            (self.root,), self.entries, object(), object(), 0,
        )
        self.sid = ctypes.c_void_p(123)
        self.report = {}

    def snapshot(self, path):
        info = path.lstat()
        return self.api._DaclSnapshot(
            path, b"original", 0, 1, True, False,
            (int(info.st_dev), int(info.st_ino)),
        )

    def observe(self, restore, transaction=None):
        method = getattr(self.case, "_observe_reviewer_acl_restore", None)
        self.assertTrue(callable(method), "Reviewer restore observation is not connected")
        return method(
            restore, self.transaction if transaction is None else transaction,
            self.sid, self.root, self.report,
        )

    def test_success_calls_original_once_with_original_objects_and_does_not_scan(self):
        calls = []
        def restore(transaction, sid):
            calls.append((transaction, sid))
            return True
        with mock.patch.dict(os.environ, OPT_IN), mock.patch.object(
            self.api, "_walk_workspace", side_effect=AssertionError("unexpected scan"),
        ):
            self.assertIs(self.observe(restore), True)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], self.transaction)
        self.assertIs(calls[0][1], self.sid)
        self.assertEqual(self.report, {
            "state": "restored", "phase": "post_restore_observation",
            "restore_returned": True,
        })

    def test_foreign_and_multi_root_transactions_are_untouched(self):
        for roots in ((self.root.parent,), (self.root, self.root.parent),
                      (self.root.parent / "snapshot" / ".." / "snapshot",)):
            with self.subTest(roots=roots), mock.patch.dict(os.environ, OPT_IN):
                foreign = replace(self.transaction, roots=roots)
                calls = []
                def restore(transaction, sid):
                    calls.append((transaction, sid))
                    return False
                self.assertIs(self.observe(restore, foreign), False)
                self.assertEqual(calls, [(foreign, self.sid)])
                self.assertEqual(self.report, {})

    def test_each_missing_opt_in_disables_observation_not_restore(self):
        for key in OPT_IN:
            with self.subTest(key=key), mock.patch.dict(os.environ, {**OPT_IN, key: "false"}):
                calls = []
                def restore(transaction, sid):
                    calls.append((transaction, sid))
                    return False
                self.assertIs(self.observe(restore), False)
                self.assertEqual(calls, [(self.transaction, self.sid)])
                self.assertEqual(self.report, {})

    def test_original_exception_is_rethrown_once_without_text(self):
        error = RuntimeError("secret-path-S-1-15-2-private")
        calls = []
        def restore(transaction, sid):
            calls.append((transaction, sid))
            raise error
        with mock.patch.dict(os.environ, OPT_IN), self.assertRaises(RuntimeError) as caught:
            self.observe(restore)
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [(self.transaction, self.sid)])
        self.assertEqual(self.report, {
            "state": "restore_exception", "phase": "post_restore_observation",
            "restore_returned": None,
        })

    def test_false_stays_false_when_later_snapshot_matches(self):
        with mock.patch.dict(os.environ, OPT_IN), mock.patch.object(
            self.api, "_read_dacl_state", side_effect=lambda path, *_: self.snapshot(path),
        ), mock.patch.object(self.api, "_contains_sid", return_value=False):
            self.assertIs(self.observe(lambda *_: False), False)
        self.assertEqual(self.report, {
            "state": "snapshot_match_after_failure", "objects": 2,
            "phase": "post_restore_observation", "restore_returned": False,
        })

    def test_observer_exception_does_not_change_false_or_block_foreign_restore(self):
        with mock.patch.dict(os.environ, OPT_IN), mock.patch.object(
            self.api, "_walk_workspace", side_effect=TypeError("private filename"),
        ):
            self.assertIs(self.observe(lambda *_: False), False)
            foreign = replace(self.transaction, roots=(self.root.parent,))
            calls = []
            def restore(transaction, sid):
                calls.append((transaction, sid))
                return True
            self.assertIs(self.observe(restore, foreign), True)
        self.assertEqual(calls, [(foreign, self.sid)])
        self.assertEqual(self.report["state"], "inspection_failed")
        self.assertNotIn("private", repr(self.report))
        self.assertIs(self.report["restore_returned"], False)

    def test_walk_is_bounded_by_snapshot_plus_one_and_existing_deadline(self):
        real_walk = self.api._walk_workspace
        with mock.patch.dict(os.environ, OPT_IN), mock.patch.object(
            original.time, "monotonic", return_value=100.0,
        ), mock.patch.object(self.api, "_walk_workspace", wraps=real_walk) as walk, \
             mock.patch.object(self.api, "_read_dacl_state", side_effect=lambda path, *_: self.snapshot(path)), \
             mock.patch.object(self.api, "_contains_sid", return_value=False):
            self.assertIs(self.observe(lambda *_: False), False)
        walk.assert_called_once_with(
            self.root, max_entries=len(self.entries) + 1,
            deadline=100.0 + self.api._MAX_RUNTIME_ACL_SNAPSHOT_SECONDS,
        )

    def test_actual_walk_overflow_is_unknown_not_success(self):
        for name in ("extra-a", "extra-b"):
            (self.root / name).write_bytes(b"extra")
        with mock.patch.dict(os.environ, OPT_IN):
            self.assertIs(self.observe(lambda *_: False), False)
        self.assertEqual(self.report["state"], "inspection_failed")
        self.assertNotIn(str(self.root), repr(self.report))

    def test_deadline_expired_after_read_cannot_report_matching_snapshot(self):
        self.assertTrue(callable(getattr(self.case, "_observe_reviewer_acl_restore", None)),
                        "Reviewer restore observation is not connected")
        for boundary in ("before_read", "after_read", "after_contains"):
            ticks = {"now": 0.0}
            def read(*_):
                if boundary == "after_read":
                    ticks["now"] = 31.0
                return self.entries[0]
            def contains(*_):
                ticks["now"] = 31.0
                return False
            def walk(*_, **__):
                if boundary == "before_read":
                    ticks["now"] = 31.0
                return [self.root]
            with self.subTest(boundary=boundary), mock.patch.dict(os.environ, OPT_IN), \
                 mock.patch.object(original.time, "monotonic", side_effect=lambda: ticks["now"]), \
                 mock.patch.object(self.api, "_walk_workspace", side_effect=walk), \
                 mock.patch.object(self.api, "_read_dacl_state", side_effect=read) as read_call, \
                 mock.patch.object(self.api, "_contains_sid", side_effect=contains) as sid_call:
                transaction = replace(self.transaction, entries=(self.entries[0],))
                self.assertIs(self.observe(lambda *_: False, transaction), False)
            self.assertEqual(self.report["state"], "inspection_failed")
            self.assertEqual(read_call.call_count, 0 if boundary == "before_read" else 1)
            self.assertEqual(sid_call.call_count, 1 if boundary == "after_contains" else 0)

    def test_each_snapshot_field_and_sid_are_projected_without_private_values(self):
        changes = {
            "dacl": (b"private-acl", "dacl_changed"),
            "control": (0x0400, "control_changed"),
            "revision": (2, "revision_changed"),
            "present": (False, "present_changed"),
            "defaulted": (True, "defaulted_changed"),
            "file_identity": ((999, 888), "file_identity_changed"),
        }
        for field, (value, flag) in changes.items():
            with self.subTest(field=field), mock.patch.dict(os.environ, OPT_IN), \
                 mock.patch.object(self.api, "_read_dacl_state", return_value=replace(self.entries[0], **{field: value})), \
                 mock.patch.object(self.api, "_contains_sid", return_value=False):
                self.report.clear()
                self.assertIs(self.observe(lambda *_: False), False)
                self.assertEqual(self.report["state"], "object_mismatch")
                self.assertEqual(self.report["object"], "root")
                self.assertIs(self.report[flag], True)
                self.assertEqual(self.report["control_delta"], 0x0400 if field == "control" else 0)
                self.assertNotIn(str(self.root), repr(self.report))
                self.assertNotIn("private-acl", repr(self.report))
                self.assertNotIn("999", repr(self.report))
        with mock.patch.dict(os.environ, OPT_IN), mock.patch.object(
            self.api, "_read_dacl_state", return_value=self.entries[0],
        ), mock.patch.object(self.api, "_contains_sid", return_value=True):
            self.assertIs(self.observe(lambda *_: False), False)
        self.assertIs(self.report["sid_residual"], True)

    def test_path_set_counts_and_setup_errors_are_bounded_and_private(self):
        with mock.patch.dict(os.environ, OPT_IN), mock.patch.object(
            self.api, "_walk_workspace", return_value=[self.root],
        ):
            self.assertIs(self.observe(lambda *_: False), False)
        self.assertEqual(self.report["expected_only"], 1)
        self.assertEqual(self.report["actual_only"], 0)
        with mock.patch.dict(os.environ, OPT_IN), mock.patch.object(
            self.api, "_walk_workspace",
            side_effect=self.api._AppContainerSetupError("secret-path-SID", "private detail"),
        ):
            self.assertIs(self.observe(lambda *_: False), False)
        self.assertNotIn("secret", repr(self.report))
        self.assertNotIn("private", repr(self.report))

    def test_real_serializer_routes_only_fixed_opted_in_plain_log_and_keeps_budget(self):
        payload = {"phase": "post_restore_observation", "restore_returned": False,
                   "state": "inspection_failed", "category": "filesystem_error"}
        for key in (None, *OPT_IN):
            environment = OPT_IN if key is None else {**OPT_IN, key: "false"}
            output = io.StringIO()
            with mock.patch.dict(os.environ, environment), contextlib.redirect_stdout(output):
                self.case._workflow_json_notice(LABEL, payload)
            if key is None:
                self.assertTrue(output.getvalue().startswith(PREFIX))
                self.assertEqual(json.loads(output.getvalue()[len(PREFIX):]), payload)
                self.assertNotIn("::notice", output.getvalue())
            else:
                self.assertEqual(output.getvalue(), "")
        with self.assertRaises(AssertionError):
            self.case._workflow_json_notice(LABEL, {"payload": "x" * 500})
        maximum = {
            "state": "object_mismatch", "object": "descendant",
            "dacl_changed": False, "metadata_changed": False,
            "control_changed": False, "revision_changed": False,
            "present_changed": False, "defaulted_changed": False,
            "file_identity_changed": False, "control_delta": 0xFFFF,
            "sid_residual": False, "phase": "post_restore_observation",
            "restore_returned": False,
        }
        with mock.patch.dict(os.environ, OPT_IN), contextlib.redirect_stdout(io.StringIO()) as out:
            self.case._workflow_json_notice(LABEL, maximum)
        encoded = out.getvalue()[len(PREFIX):].strip()
        self.assertLessEqual(len(encoded), 500)
        self.assertEqual(json.loads(encoded), maximum)
        with mock.patch.dict(os.environ, OPT_IN), contextlib.redirect_stdout(io.StringIO()) as out:
            self.case._workflow_json_notice("old notice", {"text": "%\r\n"})
        self.assertIn("::notice title=R2.3 old notice::", out.getvalue())
        self.assertIn("%25", out.getvalue())

    def test_actual_native_body_static_capture_consumes_observer(self):
        source = original.inspect.getsource(
            original.TestWindowsAppContainer.test_Reviewer快照AppContainer只读边界与Job清理,
        )
        self.assertTrue("self._observe_reviewer_acl_restore(" in source,
                        "actual Reviewer launch must consume the observer")
        self.case.test_Reviewer快照原生探针脚本在非Windows主机可静态解析()


if __name__ == "__main__":
    unittest.main()
