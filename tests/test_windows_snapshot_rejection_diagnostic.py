"""Portable controls for the test-only snapshot observer; no native credit."""

from contextlib import nullcontext
from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from icode import workspace_snapshot as ws
from icode import windows_worktree as ww


def info(**changes):
    return replace(ws._WindowsHandleInfo(7, bytes([17]) * 16, 16, 0, 1, 0, True, False),
                   **changes)


def entry(name, **changes):
    return replace(ws._WindowsDirectoryEntry(name, 16, 0, bytes([17]) * 16, 1, 0),
                   **changes)


class Backend:
    def __init__(self, *, listings=None, infos=None, open_error=None, close_error=None,
                 data=b"payload", query_error=None):
        self.listings = listings or {(): ((), ())}
        self.infos = infos or {(): (info(), info())}
        self.open_error = open_error
        self.close_error = close_error
        self.query_error = query_error
        self.data = data
        self.q = {}
        self.e = {}
        self.offset = {}
        self.trace = []

    def open_root(self, root):
        self.trace.append(("open_root",))
        if self.open_error is not None:
            raise self.open_error
        return ()

    def query_info(self, handle):
        self.trace.append(("query", handle))
        if self.query_error is not None:
            raise self.query_error
        count = self.q.get(handle, 0)
        self.q[handle] = count + 1
        values = self.infos[handle]
        return values[min(count, len(values) - 1)]

    def enumerate_directory(self, handle):
        self.trace.append(("enumerate", handle))
        count = self.e.get(handle, 0)
        self.e[handle] = count + 1
        return self.listings[handle][min(count, 1)]

    def open_child(self, handle, child, *, directory, reparse=False):
        self.trace.append(("open_child", handle, child.name, directory, reparse))
        return (*handle, child.name)

    def read_file(self, handle, size):
        self.trace.append(("read", handle, size))
        offset = self.offset.get(handle, 0)
        self.offset[handle] = offset + size
        return self.data[offset:offset + size]

    def read_symlink_target(self, handle):
        self.trace.append(("symlink", handle))
        return "private-target"

    def close_handle(self, handle):
        self.trace.append(("close", handle))

    def close_root(self, handle):
        self.trace.append(("close_root",))
        if self.close_error is not None:
            raise self.close_error


def tree(parts=(), *, drift=True):
    listings = {}
    infos = {}
    for depth in range(len(parts) + 1):
        path = parts[:depth]
        infos[path] = (info(),) * 4
        if depth < len(parts):
            before = after = (entry(parts[depth]),)
        else:
            before = (entry(".icode_output"),)
            after = () if drift else before
        listings[path] = before, after
    return Backend(listings=listings, infos=infos)


def file_tree(*, held_change=False, directory_symlink=False):
    payload = b"payload"
    normal = entry("private-file", attributes=0x80, end_of_file=len(payload))
    attributes = 0x490 if directory_symlink else 0x480
    link = entry("private-link", attributes=attributes, reparse_tag=0xA000000C)
    file_info = info(attributes=0x80, is_directory=False, end_of_file=len(payload))
    link_info = info(attributes=attributes, reparse_tag=0xA000000C,
                     is_directory=directory_symlink)
    return Backend(listings={(): ((normal, link), (normal, link))},
                   infos={(): (info(), info(change_time=2 if held_change else 1)),
                          (normal.name,): (file_info, file_info),
                          (link.name,): (link_info, link_info)})


class TestWindowsSnapshotRejectionDiagnostic(unittest.TestCase):
    def diagnostic(self):
        name = "tests.windows_snapshot_rejection_diagnostic"
        self.assertIsNotNone(importlib.util.find_spec(name), "diagnostic helper is not implemented")
        module = importlib.import_module(name)
        for symbol in ("windows_snapshot_rejection_diagnostic", "_listing_difference",
                       "_handle_difference", "_Observer", "_scope"):
            self.assertTrue(callable(getattr(module, symbol, None)), symbol + " is not implemented")
        return module

    def call(self, backends, *, observed=True):
        module = self.diagnostic()
        lines = []
        pending = iter(backends)
        created = []
        def factory():
            backend = next(pending)
            created.append(backend)
            return backend
        context = module.windows_snapshot_rejection_diagnostic(sink=lines.append) if observed else nullcontext()
        result = error = None
        try:
            with patch.object(ww, "_WindowsNativeWorktreeBackend", new=factory), context:
                result = ww.snapshot_windows_workspace_windows(Path("private-workspace"))
        except Exception as caught:
            error = caught
        return result, error, lines, created

    def receipt(self, lines):
        module = self.diagnostic()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(module.PREFIX))
        self.assertTrue(lines[0].isascii())
        receipt = json.loads(lines[0][len(module.PREFIX):])
        self.assertEqual(set(receipt), {"schema_version", "call_outcome", "attempts"})
        self.assertIs(type(receipt["schema_version"]), int)
        self.assertEqual(receipt["schema_version"], 1)
        self.assertIn(receipt["call_outcome"], ("returned", "raised"))
        self.assertEqual(len(receipt["attempts"]), 2)
        keys = {"attempt", "status", "scope", "reject_stage", "changed_entry_class",
                "listing_difference_mask", "handle_observation", "handle_difference_mask"}
        for ordinal, record in enumerate(receipt["attempts"], 1):
            self.assertEqual(set(record), keys)
            self.assertIs(type(record["attempt"]), int)
            self.assertEqual(record["attempt"], ordinal)
            self.assertIn(record["status"], ("directory_rejected", "completed", "other_error",
                                           "not_observed", "diagnostic_unavailable"))
            self.assertIn(record["scope"], ("root", "git_metadata", "other_descendant", "unavailable"))
            self.assertIn(record["reject_stage"], ("listing", "held_handle", "none", "not_observed", "unavailable"))
            self.assertIn(record["changed_entry_class"], ("git_metadata", "ignored_control", "other",
                                                        "mixed", "not_observed", "unavailable"))
            self.assertIn(record["handle_observation"], ("not_observed", "same", "different", "unavailable"))
            if record["status"] == "directory_rejected":
                if record["reject_stage"] == "listing":
                    self.assertIn(record["listing_difference_mask"], range(1, 64))
                    self.assertEqual(record["handle_observation"], "not_observed")
                    self.assertIsNone(record["handle_difference_mask"])
                else:
                    self.assertEqual(record["reject_stage"], "held_handle")
                    self.assertEqual(record["listing_difference_mask"], 0)
                    self.assertEqual(record["changed_entry_class"], "not_observed")
                    self.assertEqual(record["handle_observation"], "different")
                    self.assertIn(record["handle_difference_mask"], range(1, 256))
            elif record["status"] == "diagnostic_unavailable":
                self.assertEqual([record[key] for key in ("scope", "reject_stage", "changed_entry_class",
                                                         "handle_observation")], ["unavailable"] * 4)
                self.assertIsNone(record["listing_difference_mask"])
                self.assertIsNone(record["handle_difference_mask"])
            else:
                self.assertEqual(record["scope"], "unavailable")
                self.assertEqual(record["changed_entry_class"], "not_observed")
                self.assertEqual(record["handle_observation"], "not_observed")
                self.assertIsNone(record["listing_difference_mask"])
                self.assertIsNone(record["handle_difference_mask"])
                self.assertEqual(record["reject_stage"], "not_observed" if record["status"] == "not_observed" else "none")
        return receipt

    def test_stable_result_identity_and_no_output(self):
        module = self.diagnostic()
        value = object()
        calls = []
        def original(*args, **kwargs):
            calls.append((args, kwargs))
            return value
        lines = []
        with patch.object(ws, "_walk_windows_directory", new=original), module.windows_snapshot_rejection_diagnostic(sink=lines.append):
            returned = ws._walk_windows_directory("sentinel", snapshot_parts=(), is_root=True, depth=0)
        self.assertIs(returned, value)
        self.assertEqual(calls, [(("sentinel",), dict(snapshot_parts=(), is_root=True, depth=0))])
        self.assertEqual(lines, [])
        result, error, lines, created = self.call([Backend()])
        self.assertEqual(result, {})
        self.assertIsNone(error)
        self.assertEqual(lines, [])
        self.assertEqual(len(created), 1)

    def test_listing_classifier_all_fields_membership_and_categories(self):
        module = self.diagnostic()
        base = entry("secret-name", attributes=0x80)
        before = ws._windows_directory_listing_signature((base,))
        vectors = (("attributes", 0x81, 2), ("reparse_tag", 0xA000000C, 4),
                   ("file_id", bytes([34]) * 16, 8), ("change_time", 2, 16), ("end_of_file", 9, 32))
        for field, value, bit in vectors:
            with self.subTest(field=field):
                initial = replace(base, attributes=0x480) if field == "reparse_tag" else base
                a = ws._windows_directory_listing_signature((initial,))
                b = ws._windows_directory_listing_signature((replace(initial, **{field: value}),))
                self.assertEqual(module._listing_difference(a, b, "root"), (bit, "other"))
        self.assertEqual(module._listing_difference(before, (), "root"), (1, "other"))
        self.assertEqual(module._listing_difference((), before, "root"), (1, "other"))
        self.assertEqual(module._listing_difference(before, before, "root"), (0, "not_observed"))
        for scope, names, expected in (("root", (".git",), "git_metadata"),
                                       ("root", (".icode_output", "__pycache__"), "ignored_control"),
                                       ("other_descendant", (".git",), "other"),
                                       ("git_metadata", (".icode_output", "secret"), "git_metadata"),
                                       ("root", (".git", ".icode_output", "secret"), "mixed")):
            signatures = ws._windows_directory_listing_signature(tuple(entry(name) for name in names))
            self.assertEqual(module._listing_difference((), signatures, scope), (1, expected))
        mixed = ws._windows_directory_listing_signature((entry(".git"), entry(".icode_output"), base))
        changed = ws._windows_directory_listing_signature((entry(".git", change_time=2), replace(base, end_of_file=8)))
        self.assertEqual(module._listing_difference(mixed, changed, "root"), (1 | 16 | 32, "mixed"))

    def test_handle_classifier_eight_bits_is_not_walker_credit(self):
        module = self.diagnostic()
        before = ws._windows_handle_signature(info())
        for index, value in enumerate((8, bytes([34]) * 16, 0x50, 0xA000000C, 2, 9, False, True)):
            after = list(before)
            after[index] = value
            self.assertEqual(module._handle_difference(before, tuple(after)), 1 << index)
        self.assertEqual(module._handle_difference(before, before), 0)
        self.assertEqual(module._handle_difference(before, (8, bytes([34]) * 16, 0x50, 1, 2, 9, False, True)), 255)

    def test_actual_listing_rejection_and_retry_do_not_query_final_handle(self):
        first = tree()
        second = Backend()
        result, error, lines, created = self.call([first, second])
        self.assertIsNone(error)
        self.assertEqual(result, {})
        self.assertEqual(len(created), 2)
        self.assertEqual(first.q[()], 1)
        receipt = self.receipt(lines)
        self.assertEqual(receipt["call_outcome"], "returned")
        a, b = receipt["attempts"]
        self.assertEqual((a["status"], a["scope"], a["reject_stage"], a["changed_entry_class"],
                          a["listing_difference_mask"]), ("directory_rejected", "root", "listing", "ignored_control", 1))
        self.assertEqual(b["status"], "completed")

    def test_actual_listing_each_field_and_root_classes(self):
        # Ignored entries are listed/validated but never opened, so every legal
        # listing field reaches the actual listing rejection without bypasses.
        vectors = (("attributes", 0x11, 2), ("file_id", bytes([34]) * 16, 8),
                   ("change_time", 2, 16), ("end_of_file", 8, 32),
                   ("reparse_tag", 0xA000000C, 4))
        for field, value, bit in vectors:
            with self.subTest(field=field):
                base = entry(".icode_output", attributes=0x410 if field == "reparse_tag" else 16)
                backend = Backend(listings={(): ((base,), (replace(base, **{field: value}),))})
                _, error, lines, _ = self.call([backend, Backend()])
                self.assertIsNone(error)
                self.assertEqual(self.receipt(lines)["attempts"][0]["listing_difference_mask"], bit)
                self.assertEqual(backend.q[()], 1)
        for additions, expected in (((entry(".git"),), "git_metadata"),
                                     ((entry("private-name"),), "other"),
                                     ((entry(".git"), entry("__pycache__"), entry("private-name")), "mixed")):
            backend = Backend(listings={(): ((), additions)})
            _, error, lines, _ = self.call([backend, Backend()])
            self.assertIsNone(error)
            self.assertEqual(self.receipt(lines)["attempts"][0]["changed_entry_class"], expected)

    def test_actual_held_handle_reachable_fields_and_two_rejections(self):
        original = ww._walk_windows_directory
        for field, value, bit in (("file_id", bytes([34]) * 16, 2), ("change_time", 2, 16), ("end_of_file", 8, 32)):
            with self.subTest(field=field):
                captured = []
                def capture(*args, **kwargs):
                    try:
                        return original(*args, **kwargs)
                    except Exception as error:
                        captured.append(error)
                        raise
                backends = [Backend(infos={(): (info(), info(**{field: value}))}) for _ in range(2)]
                with patch.object(ww, "_walk_windows_directory", new=capture):
                    _, error, lines, created = self.call(backends)
                self.assertIsInstance(error, ws.WorktreeTreeUnavailable)
                self.assertIs(error, captured[-1])
                self.assertEqual(error.args, ("windows_directory_changed",))
                self.assertEqual(error.reason, "windows_directory_changed")
                self.assertEqual(len(created), 2)
                receipt = self.receipt(lines)
                self.assertEqual(receipt["call_outcome"], "raised")
                for record in receipt["attempts"]:
                    self.assertEqual((record["status"], record["reject_stage"], record["listing_difference_mask"],
                                      record["handle_difference_mask"]), ("directory_rejected", "held_handle", 0, bit))

    def test_actual_validator_errors_keep_original_object_and_no_receipt(self):
        module = self.diagnostic()
        cases = (dict(volume_serial_number=8), dict(attributes=0), dict(attributes=0x50),
                 dict(is_directory=False), dict(delete_pending=True), dict(reparse_tag=-1),
                 dict(reparse_tag=0x100000000), dict(attributes=0x410, reparse_tag=0xA000000C))
        original = ws._walk_windows_directory
        for changes in cases:
            captured = []
            def capture(*args, **kwargs):
                try:
                    return original(*args, **kwargs)
                except Exception as error:
                    captured.append(error)
                    raise
            backend = Backend(infos={(): (info(), info(**changes))})
            with self.subTest(changes=changes), patch.object(ww, "_walk_windows_directory", new=capture):
                _, error, lines, created = self.call([backend])
                self.assertIs(error, captured[0])
                self.assertEqual(error.reason, "windows_directory_identity_invalid")
                self.assertEqual(lines, [])
                self.assertEqual(len(created), 1)
        for raw in (1, 0xA000000C, 0xFFFFFFFF):
            _, error, lines, _ = self.call([Backend(infos={(): (info(), info(reparse_tag=raw))})])
            self.assertIsNone(error)
            self.assertEqual(lines, [])
        self.assertEqual(module._scope((".git", "hooks")), "git_metadata")
        self.assertEqual(module._scope(("subdir", ".git")), "other_descendant")
        for bad in (None, [], ("..",), ("a/b",), ("",), (3,)):
            self.assertEqual(module._scope(bad), "unavailable")

    def test_deepest_git_and_nested_git_scopes_parent_does_not_overwrite(self):
        for parts, scope, changed in (((".git", "hooks"), "git_metadata", "git_metadata"),
                                       (("subdir", ".git"), "other_descendant", "ignored_control")):
            first = tree(parts)
            _, error, lines, _ = self.call([first, Backend()])
            self.assertIsNone(error)
            record = self.receipt(lines)["attempts"][0]
            self.assertEqual((record["scope"], record["changed_entry_class"]), (scope, changed))
            self.assertEqual(record["reject_stage"], "listing")
            self.assertEqual(first.e[parts], 2)
            self.assertEqual(first.e[()], 1)
            self.assertFalse(any(call[0] == "open_child" and call[2] == ".icode_output" for call in first.trace))

    def test_open_close_boundaries_slots_and_original_other_errors(self):
        for second, expected in ((Backend(open_error=ws.WorktreeTreeUnavailable("open-private")), "not_observed"),
                                 (Backend(close_error=ws.WorktreeTreeUnavailable("close-private")), "completed"),
                                 (Backend(query_error=ws.WorktreeTreeUnavailable("query-private")), "other_error")):
            _, error, lines, _ = self.call([tree(), second])
            self.assertIs(error, second.open_error or second.close_error or second.query_error)
            receipt = self.receipt(lines)
            self.assertEqual(receipt["call_outcome"], "raised")
            self.assertEqual(receipt["attempts"][1]["status"], expected)
        for backend in (Backend(open_error=ws.WorktreeTreeUnavailable("open-private")),
                        Backend(query_error=ws.WorktreeTreeUnavailable("query-private"))):
            _, error, lines, created = self.call([backend])
            self.assertIs(error, backend.open_error or backend.query_error)
            self.assertEqual(len(created), 1)
            self.assertEqual(lines, [])

    def test_file_and_symlink_signatures_are_not_directory_handle_pair(self):
        for directory_symlink in (False, True):
            backend = file_tree(held_change=True, directory_symlink=directory_symlink)
            _, error, lines, _ = self.call([backend, Backend()])
            self.assertIsNone(error)
            record = self.receipt(lines)["attempts"][0]
            self.assertEqual((record["reject_stage"], record["handle_difference_mask"]), ("held_handle", 16))
            self.assertTrue(any(item[0] == "read" for item in backend.trace))
            self.assertTrue(any(item[0] == "symlink" for item in backend.trace))
        payload = b"payload"
        normal = entry("private-file", attributes=0x80, end_of_file=len(payload))
        file_info = info(attributes=0x80, is_directory=False, end_of_file=len(payload))
        bad_file = Backend(listings={(): ((normal,), (normal,))},
                           infos={(): (info(), info()), (normal.name,): (file_info, replace(file_info, change_time=2))})
        _, error, lines, created = self.call([bad_file])
        self.assertEqual(error.reason, "windows_entry_identity_changed")
        self.assertEqual(lines, [])
        self.assertEqual(len(created), 1)

    def test_backend_sequences_identical_with_and_without_hooks(self):
        for maker in (Backend, tree, file_tree,
                      lambda: file_tree(held_change=True, directory_symlink=True),
                      lambda: tree((".git", "hooks")),
                      lambda: Backend(infos={(): (info(), info(change_time=2))}),
                      lambda: Backend(infos={(): (info(), info(delete_pending=True))})):
            plain = [maker(), Backend()]
            observed = [maker(), Backend()]
            a, ae, _, ac = self.call(plain, observed=False)
            b, be, lines, bc = self.call(observed)
            self.assertEqual(a, b)
            self.assertEqual(getattr(ae, "reason", None), getattr(be, "reason", None))
            self.assertEqual([backend.trace for backend in ac], [backend.trace for backend in bc])
            if lines:
                self.receipt(lines)

    def test_hook_aliases_restore_and_signature_result_identity(self):
        module = self.diagnostic()
        references = ((ws, "_windows_directory_listing_signature"), (ws, "_windows_handle_signature"),
                      (ws, "_walk_windows_directory"), (ww, "_walk_windows_directory"))
        original = [getattr(owner, name) for owner, name in references]
        lines = []
        with module.windows_snapshot_rejection_diagnostic(sink=lines.append):
            for (owner, name), value in zip(references, original):
                self.assertIsNot(getattr(owner, name), value)
                self.assertFalse(hasattr(getattr(owner, name), "mock_calls"))
            backend = tree((".git",))
            with self.assertRaises(ws.WorktreeTreeUnavailable):
                ws._walk_windows_directory((), backend, object_format=None, include_in_tree=False,
                    snapshot_output={}, snapshot_parts=(), snapshot_enabled=True, is_root=True, depth=0)
        self.assertEqual(self.receipt(lines)["attempts"][0]["scope"], "git_metadata")
        for (owner, name), value in zip(references, original):
            self.assertIs(getattr(owner, name), value)
        returned = (entry("private"),)
        calls = []
        def signature(*args, **kwargs):
            calls.append((args, kwargs))
            return returned
        observer = module._Observer()
        wrapped = observer.signature(signature, observer._listing)
        self.assertIs(wrapped("value", flag=1), returned)
        self.assertEqual(calls, [(("value",), {"flag": 1})])
        failure = ws.WorktreeTreeUnavailable("unchanged-private")
        def failing(*args, **kwargs):
            calls.append((args, kwargs))
            raise failure
        wrapped = observer.signature(failing, observer._listing)
        with self.assertRaises(ws.WorktreeTreeUnavailable) as raised:
            wrapped("error", flag=2)
        self.assertIs(raised.exception, failure)
        self.assertEqual(failure.reason, "unchanged-private")
        self.assertEqual(failure.args, ("unchanged-private",))
        self.assertEqual(calls[-1], (("error",), {"flag": 2}))
        self.assertEqual(len(calls), 2)

    def test_owner_nested_and_other_thread_contexts_are_nonblocking_transparent(self):
        module = self.diagnostic()
        outer = []
        nested = []
        other = []
        done = threading.Event()
        errors = []
        references = []
        def worker():
            try:
                before = ws._walk_windows_directory
                with module.windows_snapshot_rejection_diagnostic(sink=other.append):
                    references.append(ws._walk_windows_directory is before)
                    with self.assertRaises(ws.WorktreeTreeUnavailable):
                        ww._walk_windows_directory((), tree(), object_format=None, include_in_tree=False,
                            snapshot_output={}, snapshot_parts=(), snapshot_enabled=True, is_root=True, depth=0)
                references.append(ws._walk_windows_directory is before)
            except Exception as error:
                errors.append(error)
            finally:
                done.set()
        with module.windows_snapshot_rejection_diagnostic(sink=outer.append):
            installed = ws._walk_windows_directory
            with module.windows_snapshot_rejection_diagnostic(sink=nested.append):
                self.assertIs(ws._walk_windows_directory, installed)
                self.assertIsNone(ww._walk_windows_directory((), Backend(), object_format=None,
                    include_in_tree=False, snapshot_output={}, snapshot_parts=(),
                    snapshot_enabled=True, is_root=True, depth=0))
            thread = threading.Thread(target=worker)
            thread.start()
            self.assertTrue(done.wait(2), "non-owner context must not wait for owner")
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertIs(ws._walk_windows_directory, installed)
            with self.assertRaises(ws.WorktreeTreeUnavailable):
                ww._walk_windows_directory((), tree(), object_format=None, include_in_tree=False,
                    snapshot_output={}, snapshot_parts=(), snapshot_enabled=True, is_root=True, depth=0)
        self.assertEqual(errors, [])
        self.assertEqual(references, [True, True])
        self.assertEqual(nested, [])
        self.assertEqual(other, [])
        self.assertEqual([record["status"] for record in self.receipt(outer)["attempts"]],
                         ["completed", "directory_rejected"])

    def test_active_references_released_and_actual_frame_count_bounded(self):
        module = self.diagnostic()
        observer = module._Observer()
        frame = observer._make_frame(0, ())
        observer.frames.append(frame)
        listing = observer.signature(ws._windows_directory_listing_signature, observer._listing)
        before = listing((entry("private-name"),))
        self.assertIs(frame.listing_before, before)
        listing((entry("private-name"),))
        self.assertIsNone(frame.listing_before)
        handle = observer.signature(ws._windows_handle_signature, observer._handle)
        before = handle(info())
        self.assertIs(frame.handle_before, before)
        handle(info())
        self.assertIsNone(frame.handle_before)
        self.assertNotIn("snapshot_parts", module._Frame.__slots__)
        self.assertEqual(len(observer.records), 2)
        observer.frames.clear()
        actual_observers = []
        peaks = []
        original_class = module._Observer
        original_make_frame = module._Observer._make_frame
        def factory():
            created = original_class()
            actual_observers.append(created)
            return created
        def make_frame(self, slot_index, parts):
            peaks.append(len(self.frames) + 1)
            return original_make_frame(self, slot_index, parts)
        with patch.object(original_class, "_make_frame", new=make_frame), patch.object(module, "_Observer", new=factory):
            _, error, lines, _ = self.call([tree(("d",) * 128), Backend()])
        self.assertIsNone(error)
        self.assertEqual(max(peaks), 129)
        self.assertEqual(len(actual_observers), 1)
        self.assertEqual(actual_observers[0].frames, [])
        self.assertEqual(len(actual_observers[0].records), 2)
        self.receipt(lines)

    def test_real_depth_129_and_synthetic_130_frames_do_not_borrow_parent(self):
        module = self.diagnostic()
        _, error, lines, _ = self.call([tree(("d",) * 128), Backend()])
        self.assertIsNone(error)
        self.assertEqual(self.receipt(lines)["attempts"][0]["status"], "directory_rejected")
        _, error, lines, _ = self.call([tree(("d",) * 129)])
        self.assertEqual(error.reason, "worktree_too_deep")
        self.assertEqual(lines, [])
        failure = ws.WorktreeTreeUnavailable("windows_directory_changed")
        peak = []
        def synthetic(*args, **kwargs):
            peak.append(kwargs["depth"])
            if kwargs["depth"] == 129:
                raise failure
            return ws._walk_windows_directory(snapshot_parts=(*kwargs["snapshot_parts"], "d"),
                    is_root=False, depth=kwargs["depth"] + 1)
        lines = []
        with patch.object(ws, "_walk_windows_directory", new=synthetic), module.windows_snapshot_rejection_diagnostic(sink=lines.append):
            with self.assertRaises(ws.WorktreeTreeUnavailable) as raised:
                ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0)
        self.assertIs(raised.exception, failure)
        self.assertEqual(max(peak), 129)
        self.assertEqual(self.receipt(lines)["attempts"][0]["status"], "diagnostic_unavailable")

    def test_observer_bookkeeping_comparison_slot_and_sink_failures_preserve_original(self):
        module = self.diagnostic()
        def broken(*args, **kwargs):
            raise ValueError("private observer error")
        for owner, symbol in ((module._Observer, "_make_frame"), (module._Observer, "_listing"),
                              (module, "_scope"), (module, "_entry_class"),
                              (module, "_listing_difference"), (module._Observer, "_handle"),
                              (module, "_handle_difference"), (module._Observer, "_rejected")):
            maker = (lambda: Backend(infos={(): (info(), info(change_time=2))})) if "handle" in symbol else tree
            with self.subTest(symbol=symbol), patch.object(owner, symbol, new=broken):
                _, error, lines, _ = self.call([maker(), maker()])
            self.assertEqual(error.reason, "windows_directory_changed")
            self.assertEqual([slot["status"] for slot in self.receipt(lines)["attempts"]],
                             ["diagnostic_unavailable", "diagnostic_unavailable"])
        for owner, symbol in ((module.json, "dumps"),):
            with patch.object(owner, symbol, new=broken):
                result, error, lines, _ = self.call([tree(), Backend()])
            self.assertEqual(result, {})
            self.assertIsNone(error)
            self.assertEqual(lines, [])
        value = object()
        for failure in (None, ws.WorktreeTreeUnavailable("original-private")):
            def original(*args, **kwargs):
                raise ws.WorktreeTreeUnavailable("windows_directory_changed")
            returned = None
            try:
                with patch.object(ws, "_walk_windows_directory", new=original), module.windows_snapshot_rejection_diagnostic(sink=broken):
                    try:
                        ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0)
                    except ws.WorktreeTreeUnavailable:
                        pass
                    if failure is not None:
                        raise failure
                    returned = value
            except ws.WorktreeTreeUnavailable as raised:
                self.assertIs(raised, failure)
            else:
                self.assertIsNone(failure)
                self.assertIs(returned, value)
        for original_error in (KeyboardInterrupt(), SystemExit(7)):
            with self.assertRaises(type(original_error)) as raised:
                with module.windows_snapshot_rejection_diagnostic(sink=broken):
                    raise original_error
            self.assertIs(raised.exception, original_error)

    def test_restore_slot_failure_and_overflow_exit_preserve_original(self):
        module = self.diagnostic()
        def broken(*args, **kwargs):
            raise ValueError("private bookkeeping")
        for symbol in ("_restore",):
            with patch.object(module._Observer, symbol, new=broken):
                result, error, lines, _ = self.call([Backend()])
                self.assertEqual(result, {})
                self.assertIsNone(error)
                self.assertEqual(lines, [])
                _, error, lines, _ = self.call([tree(), tree()])
                self.assertEqual(error.reason, "windows_directory_changed")
                self.assertEqual(lines, [])
        with patch.object(module, "_unavailable", new=broken), patch.object(module._Observer, "_make_frame", new=broken):
            _, error, lines, _ = self.call([tree(), tree()])
        self.assertEqual(error.reason, "windows_directory_changed")
        self.assertEqual(lines, [])
        # Keep a parent active, overfill only its subtree, then return from the
        # subtree and feed the parent real production signatures again.
        observer = module._Observer()
        parent = observer._make_frame(0, ())
        observer.frames = [parent] * module.MAX_FRAMES
        value = object()
        wrapped = observer.walker(lambda **kwargs: value)
        self.assertIs(wrapped(snapshot_parts=("private",), is_root=False, depth=129), value)
        self.assertEqual(len(observer.frames), module.MAX_FRAMES)
        self.assertEqual(observer.suspended, 0)
        self.assertIs(observer._active(), parent)
        before = ws._windows_directory_listing_signature(())
        after = ws._windows_directory_listing_signature((entry(".icode_output"),))
        observer._listing(before)
        observer._listing(after)
        self.assertEqual((parent.listing_mask, parent.entry_class), (1, "ignored_control"))
        observer.frames.clear()

    def test_partial_install_rolls_back_before_body_and_releases_owner(self):
        module = self.diagnostic()
        actual = module.patch.object
        originals = (ws._windows_directory_listing_signature, ws._windows_handle_signature,
                     ws._walk_windows_directory, ww._walk_windows_directory)
        for fail_at in range(1, 5):
            calls = []
            def installing(*args, **kwargs):
                calls.append(1)
                if len(calls) == fail_at:
                    raise ValueError("partial install")
                return actual(*args, **kwargs)
            lines = []
            with patch.object(module.patch, "object", new=installing):
                with module.windows_snapshot_rejection_diagnostic(sink=lines.append):
                    self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                                      ws._walk_windows_directory, ww._walk_windows_directory), originals)
                    self.assertTrue(module._OWNER.acquire(blocking=False))
                    module._OWNER.release()
            self.assertEqual(lines, [])
        for interruption in (KeyboardInterrupt(), SystemExit(7)):
            calls = []
            def interrupted_install(*args, **kwargs):
                calls.append(1)
                if len(calls) == 4:
                    raise interruption
                return actual(*args, **kwargs)
            with patch.object(module.patch, "object", new=interrupted_install):
                with self.assertRaises(type(interruption)) as raised:
                    with module.windows_snapshot_rejection_diagnostic(sink=lambda line: self.fail("interrupted install must not emit")):
                        self.fail("interrupted installation must propagate")
            self.assertIs(raised.exception, interruption)
            self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                              ws._walk_windows_directory, ww._walk_windows_directory), originals)
            self.assertTrue(module._OWNER.acquire(blocking=False))
            module._OWNER.release()
        result, error, lines, _ = self.call([tree(), Backend()])
        self.assertEqual(result, {})
        self.assertIsNone(error)
        self.receipt(lines)

        def broken_stack():
            raise ValueError("private stack construction failure")
        with patch.object(module, "ExitStack", new=broken_stack):
            result, error, lines, _ = self.call([Backend()])
        self.assertEqual(result, {})
        self.assertIsNone(error)
        self.assertEqual(lines, [])
        self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                          ws._walk_windows_directory, ww._walk_windows_directory), originals)
        self.assertTrue(module._OWNER.acquire(blocking=False))
        module._OWNER.release()

        def pending_close(stack):
            raise ValueError("private pending rollback failure")
        calls = []
        def installing(*args, **kwargs):
            calls.append(1)
            if len(calls) == 4:
                raise ValueError("private installation failure")
            return actual(*args, **kwargs)
        with patch.object(module.ExitStack, "close", new=pending_close), \
                patch.object(module.patch, "object", new=installing):
            with module.windows_snapshot_rejection_diagnostic(sink=lambda line: self.fail("failed install must not emit")):
                self.assertEqual((ws._windows_directory_listing_signature, ws._windows_handle_signature,
                                  ws._walk_windows_directory, ww._walk_windows_directory), originals)
                self.assertTrue(module._OWNER.acquire(blocking=False))
                module._OWNER.release()

    def test_context_cleanup_and_emit_failures_keep_original_results(self):
        module = self.diagnostic()
        actual_close = module.ExitStack.close
        references = ((ws, "_windows_directory_listing_signature"),
                      (ws, "_windows_handle_signature"),
                      (ws, "_walk_windows_directory"), (ww, "_walk_windows_directory"))
        def failed_close(stack):
            actual_close(stack)
            raise ValueError("private cleanup failure")
        def failed_before_close(stack):
            raise ValueError("private pending cleanup failure")
        def failed_emit(*args, **kwargs):
            raise ValueError("private observer failure")
        for owner, symbol, replacement in ((module.ExitStack, "close", failed_close),
                                            (module.ExitStack, "close", failed_before_close),
                                            (module._Observer, "emit", failed_emit)):
            for failure in (None, ws.WorktreeTreeUnavailable("original-private")):
                with self.subTest(symbol=symbol, raised=failure is not None):
                    value = object()
                    calls = []
                    def original(*args, **kwargs):
                        calls.append((args, kwargs))
                        if failure is not None:
                            raise failure
                        return value
                    lines = []
                    with patch.object(ws, "_walk_windows_directory", new=original):
                        originals = [getattr(owner, name) for owner, name in references]
                        with patch.object(owner, symbol, new=replacement):
                            try:
                                with module.windows_snapshot_rejection_diagnostic(sink=lines.append):
                                    result = ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0)
                            except Exception as error:
                                self.assertIs(error, failure)
                            else:
                                self.assertIsNone(failure)
                                self.assertIs(result, value)
                        self.assertEqual([getattr(owner, name) for owner, name in references], originals)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(lines, [])
                    self.assertTrue(module._OWNER.acquire(blocking=False))
                    module._OWNER.release()

        for owner, symbol in ((module.ExitStack, "close"), (module._Observer, "emit")):
            for interruption in (KeyboardInterrupt(), SystemExit(7)):
                def interrupted(*args, **kwargs):
                    raise interruption
                originals = [getattr(owner, name) for owner, name in references]
                with patch.object(owner, symbol, new=interrupted):
                    with self.assertRaises(type(interruption)) as raised:
                        with module.windows_snapshot_rejection_diagnostic(sink=lambda line: self.fail("interruption must not emit")):
                            pass
                self.assertIs(raised.exception, interruption)
                self.assertEqual([getattr(owner, name) for owner, name in references], originals)
                self.assertTrue(module._OWNER.acquire(blocking=False))
                module._OWNER.release()

    def test_failed_fallback_restoration_leaves_only_transparent_wrappers(self):
        module = self.diagnostic()
        references = ((ws, "_windows_directory_listing_signature"),
                      (ws, "_windows_handle_signature"),
                      (ws, "_walk_windows_directory"), (ww, "_walk_windows_directory"))
        observers = []
        actual_observer = module._Observer
        def factory():
            observer = actual_observer()
            observers.append(observer)
            return observer
        def broken(*args, **kwargs):
            raise ValueError("private unrecoverable cleanup")
        value = object()
        calls = []
        failure = ws.WorktreeTreeUnavailable("private-original-failure")
        def original(*args, **kwargs):
            calls.append((args, kwargs))
            if kwargs.get("fail"):
                raise failure
            return value
        with patch.object(ws, "_walk_windows_directory", new=original):
            originals = [getattr(owner, name) for owner, name in references]
            try:
                lines = []
                with patch.object(module, "_Observer", new=factory), \
                        patch.object(module.ExitStack, "close", new=broken), \
                        patch.object(module, "setattr", new=broken, create=True):
                    try:
                        with module.windows_snapshot_rejection_diagnostic(sink=lines.append):
                            result = ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0)
                    except Exception as error:
                        self.fail("cleanup replaced the original result: " + type(error).__name__)
                self.assertIs(result, value)
                self.assertTrue(all(getattr(owner, name) is not old for (owner, name), old in zip(references, originals)))
                self.assertIs(ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0), value)
                with self.assertRaises(ws.WorktreeTreeUnavailable) as raised:
                    ws._walk_windows_directory(snapshot_parts=(), is_root=True, depth=0, fail=True)
                self.assertIs(raised.exception, failure)
                self.assertEqual(observers[0].root_count, 1)
                self.assertEqual(len(calls), 3)
                self.assertEqual(lines, [])
                self.assertTrue(module._OWNER.acquire(blocking=False))
                module._OWNER.release()
            finally:
                # The fault intentionally prevented restoration; the test
                # restores its own injected references after the assertions.
                for (owner, name), old in zip(references, originals):
                    setattr(owner, name, old)

    def test_extra_root_returns_and_errors_suppress_output_keep_slots_and_identity(self):
        module = self.diagnostic()
        failure = ws.WorktreeTreeUnavailable("windows_directory_changed")
        value = object()
        actual_walker = ws._walk_windows_directory
        for third_error in (None, failure):
            calls = []
            observer = module._Observer()
            def original(*args, **kwargs):
                calls.append(kwargs)
                if len(calls) < 3:
                    return actual_walker(*args, **kwargs)
                if third_error is not None:
                    raise failure
                return value
            wrapped = observer.walker(original)
            listing = observer.signature(ws._windows_directory_listing_signature, observer._listing)
            handle = observer.signature(ws._windows_handle_signature, observer._handle)
            arguments = dict(object_format=None, include_in_tree=False, snapshot_output={},
                             snapshot_parts=(), snapshot_enabled=True, is_root=True, depth=0)
            with patch.object(ws, "_windows_directory_listing_signature", new=listing), patch.object(ws, "_windows_handle_signature", new=handle):
                for _ in range(2):
                    with self.assertRaises(ws.WorktreeTreeUnavailable):
                        wrapped((), tree(), **arguments)
                before_lines = []
                observer.emit(before_lines.append, "raised")
                self.assertEqual([record["status"] for record in self.receipt(before_lines)["attempts"]],
                                 ["directory_rejected", "directory_rejected"])
                previous = [dict(record) for record in observer.records]
                if third_error is None:
                    self.assertIs(wrapped((), Backend(), **arguments), value)
                else:
                    with self.assertRaises(ws.WorktreeTreeUnavailable) as raised:
                        wrapped((), Backend(), **arguments)
                    self.assertIs(raised.exception, failure)
            self.assertEqual(len(calls), 3)
            self.assertEqual(observer.records, previous)
            self.assertEqual(len(observer.records), 2)
            self.assertTrue(observer.invalid_context)
            lines = []
            observer.emit(lines.append, "raised" if third_error else "returned")
            self.assertEqual(lines, [])

    def test_redacted_closed_output(self):
        _, _, lines, _ = self.call([tree((".git", "private-directory")), Backend()])
        self.receipt(lines)
        for forbidden in ("private", ".git", ".icode_output", "__pycache__", "file_id", "volume",
                          "change_time", "end_of_file", "traceback", "reason", "signature"):
            self.assertNotIn(forbidden, lines[0])


if __name__ == "__main__":
    unittest.main()
