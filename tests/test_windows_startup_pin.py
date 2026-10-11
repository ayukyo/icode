"""Portable tests of HANDLE ownership, not Windows integration evidence."""
import importlib.util
import hashlib
import copy
from dataclasses import replace
import unittest


class StartupPinInterfaceTests(unittest.TestCase):
    def test_internal_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("icode.windows_startup_pin"))


class FakeBackend:
    """Models acquisition/query/read/close boundaries with explicit faults."""

    def __init__(self, module, *, fail=None, exception=None, mutations=None):
        self.module = module
        self.fail = fail
        self.exception = exception or RuntimeError("backend fault")
        self.mutations = mutations or {}
        self.calls = []
        self.live = set()
        self.closed = []
        self.queries = {}
        self.data = b"original bytes"
        self.read_result = None
        self.close_failures = set()
        self.reuse = False

    def call(self, label):
        self.calls.append(label)
        if label == self.fail:
            raise self.exception

    def acquire(self, label):
        self.call(label)
        handle = 1 if self.reuse else len(self.live) + len(self.closed) + 1
        self.live.add(handle)
        return handle

    def open_root(self, drive):
        assert drive == "C:"
        return self.acquire("open:1")

    def open_child(self, parent, name, *, directory):
        assert parent in self.live
        assert "\\" not in name
        return self.acquire(f"open:{parent + 1}")

    def query(self, handle):
        self.queries[handle] = self.queries.get(handle, 0) + 1
        self.call(f"query:{handle}:{self.queries[handle]}")
        meta = self.module.StartupFileMetadata(
            volume_serial=7, file_id=handle.to_bytes(16, "little"),
            directory=handle < 4, reparse=False, delete_pending=False,
            file_type="disk", links=1, size=0 if handle < 4 else len(self.data),
            change_time=100,
        )
        return replace(meta, **self.mutations.get((handle, self.queries[handle]), {}))

    def read(self, handle, offset, count):
        assert handle == 4 and handle in self.live
        self.call(f"read:{offset}")
        return self.data[offset:offset + count] if self.read_result is None else self.read_result

    def close(self, handle):
        self.closed.append(handle)
        if handle in self.close_failures:
            raise RuntimeError(f"close:{handle}")
        self.live.remove(handle)


class StartupPinTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("icode.windows_startup_pin")
        self.assertIsNotNone(spec)
        from icode import windows_startup_pin
        self.m = windows_startup_pin
        self.backend = FakeBackend(self.m)

    def pin(self, **kwargs):
        return self.m.pin_startup_file("C:\\a\\b\\start.exe", _backend=self.backend, **kwargs)

    def test_original_bytes_digest_context_and_closed_access(self):
        with self.pin() as owner:
            self.assertEqual(owner.content, b"original bytes")
            self.assertEqual(owner.sha256, hashlib.sha256(owner.content).hexdigest())
            self.assertIsNone(owner.revalidate())
            self.backend.data = b"different data"
            self.assertEqual(owner.content, b"original bytes")
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])
        self.assertTrue(owner.closed)
        self.assertTrue(owner.close_confirmed)
        owner.close()
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])
        for operation in (lambda: owner.content, lambda: owner.sha256, owner.revalidate):
            with self.assertRaises(self.m.StartupPinError):
                operation()

    def test_all_acquisition_query_and_read_failure_points_cleanup(self):
        labels = [f"open:{h}" for h in range(1, 5)]
        labels += [f"query:{h}:1" for h in range(1, 5)]
        labels += [f"query:{h}:2" for h in range(1, 5)] + ["read:0"]
        for label in labels:
            for exc in (RuntimeError(label), KeyboardInterrupt(label), SystemExit(label)):
                with self.subTest(label=label, exception=type(exc)):
                    self.backend = FakeBackend(self.m, fail=label, exception=exc)
                    with self.assertRaises(type(exc)) as raised:
                        self.pin()
                    self.assertIs(raised.exception, exc)
                    self.assertFalse(self.backend.live)
                    self.assertEqual(self.backend.closed, sorted(self.backend.closed, reverse=True))

    def test_live_owner_rejects_copy_without_changing_ownership(self):
        for copier in (copy.copy, copy.deepcopy):
            with self.subTest(copier=copier.__name__):
                self.backend = FakeBackend(self.m)
                owner = self.pin()
                duplicate = None
                error = None
                try:
                    duplicate = copier(owner)
                except Exception as exc:
                    error = exc
                self.assertFalse(owner.closed)
                self.assertEqual(owner.content, b"original bytes")
                self.assertEqual(owner.sha256, hashlib.sha256(owner.content).hexdigest())
                self.assertEqual(self.backend.live, {1, 2, 3, 4})
                self.assertEqual(self.backend.closed, [])
                owner.revalidate()
                owner.close()
                self.assertTrue(owner.close_confirmed)
                self.assertEqual(self.backend.closed, [4, 3, 2, 1])
                self.assertFalse(self.backend.live)
                # Numeric HANDLEs now represent unrelated newly opened objects.
                self.backend.live.update({1, 2, 3, 4})
                owner.close()
                if duplicate is not None:
                    duplicate.close()
                self.assertEqual(self.backend.closed, [4, 3, 2, 1])
                self.assertEqual(self.backend.live, {1, 2, 3, 4})
                self.assertIsInstance(error, self.m.StartupPinError)
                self.assertEqual(str(error), "startup HANDLE owner cannot be copied")
                self.assertIsNone(duplicate)

    def test_uninitialized_and_closed_owners_reject_copy_explicitly(self):
        for state in ("uninitialized", "closed"):
            for copier in (copy.copy, copy.deepcopy):
                with self.subTest(state=state, copier=copier.__name__):
                    self.backend = FakeBackend(self.m)
                    owner = (self.m.PinnedStartupFile(self.backend, 10)
                             if state == "uninitialized" else self.pin())
                    if state == "closed":
                        owner.close()
                    calls = list(self.backend.calls)
                    closed = list(self.backend.closed)
                    error = None
                    duplicate = None
                    try:
                        duplicate = copier(owner)
                    except Exception as exc:
                        error = exc
                    self.assertEqual(self.backend.calls, calls)
                    self.assertEqual(self.backend.closed, closed)
                    self.assertFalse(self.backend.live)
                    self.assertEqual(owner.closed, state == "closed")
                    owner.close()
                    self.assertTrue(owner.close_confirmed)
                    self.assertEqual(self.backend.closed, closed)
                    self.assertIsInstance(error, self.m.StartupPinError)
                    self.assertEqual(str(error), "startup HANDLE owner cannot be copied")
                    self.assertIsNone(duplicate)

    def test_path_lexical_rejections_before_backend(self):
        paths = ["a.exe", "C:a.exe", "\\\\server\\share\\a", "\\\\?\\C:\\a",
                 "C:/a", "C:\\a:stream", "C:\\a\\..\\x", "C:\\a\\.\\x",
                 "C:\\\\x", "C:\\a\\", "C:\\CON", "C:\\con.txt", "C:\\LPT1.exe",
                 "C:\\a.\\x", "C:\\a \\x", "C:\\a\x00", "C:\\a\ud800", "C:\\a?", "C:\\a|x", "C:\\"]
        for path in paths:
            with self.subTest(path=repr(path)), self.assertRaises(self.m.StartupPinError):
                self.m.pin_startup_file(path, _backend=self.backend)
        self.assertEqual(self.backend.calls, [])

    def test_strict_budget_rejects_before_backend(self):
        for size in (True, False, 0, -1, 1.5, None, 64 * 1024 * 1024 + 1):
            with self.subTest(size=size), self.assertRaises(self.m.StartupPinError):
                self.pin(max_bytes=size)
        self.assertEqual(self.backend.calls, [])

    def test_metadata_invalid_types_and_values(self):
        fields = {"volume_serial": [True, -1, 2**64], "file_id": [b"short", bytearray(16)],
                  "directory": [1], "reparse": [0, True], "delete_pending": [0, True],
                  "file_type": ["pipe", 1], "links": [True, 0, 2],
                  "size": [True, -1, 0, 64 * 1024 * 1024 + 1], "change_time": [True, 2**63]}
        for field, values in fields.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.backend = FakeBackend(self.m, mutations={(4, 1): {field: value}})
                    with self.assertRaises(self.m.StartupPinError):
                        self.pin()
                    self.assertFalse(self.backend.live)

    def test_ancestors_and_identity_drift_rejected(self):
        cases = [(h, 1, {"reparse": True}) for h in range(1, 4)]
        cases += [(h, 1, {"directory": False}) for h in range(1, 4)]
        cases += [(h, 1, {"volume_serial": 8}) for h in range(2, 5)]
        cases += [(h, 2, {"file_id": b"x" * 16}) for h in range(1, 5)]
        cases += [(4, 2, {"size": 15}), (4, 2, {"change_time": 101}),
                  (4, 1, {"directory": True}), (2, 1, {"file_id": (1).to_bytes(16, "little")})]
        for handle, query, mutation in cases:
            with self.subTest(handle=handle, query=query, mutation=mutation):
                self.backend = FakeBackend(self.m, mutations={(handle, query): mutation})
                with self.assertRaises(self.m.StartupPinError):
                    self.pin()
                self.assertFalse(self.backend.live)

    def test_read_eof_excess_wrong_type_and_budget(self):
        for value in (b"", b"x" * 30, "not bytes", bytearray(b"data"), None):
            with self.subTest(value=value):
                self.backend = FakeBackend(self.m)
                if value is None:
                    self.backend.data = b"x" * 20
                    with self.assertRaises(self.m.StartupPinError):
                        self.pin(max_bytes=10)
                else:
                    self.backend.read_result = value
                    with self.assertRaises(self.m.StartupPinError):
                        self.pin()
                self.assertFalse(self.backend.live)

    def test_reused_handle_rejected_without_duplicate_close(self):
        self.backend.reuse = True
        with self.assertRaises(self.m.StartupPinError):
            self.pin()
        self.assertEqual(self.backend.closed, [1])

    def test_multiple_close_failures_preserve_uncertainty_no_retry(self):
        owner = self.pin()
        self.backend.close_failures = {4, 2}
        with self.assertRaises(self.m.StartupPinCloseError) as raised:
            owner.close()
        self.assertEqual(len(raised.exception.errors), 2)
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])
        self.assertEqual(self.backend.live, {4, 2})
        self.assertFalse(owner.close_confirmed)
        owner.close()
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])

    def test_each_close_fault_and_base_exception_still_attempts_all(self):
        for handle in range(1, 5):
            for exception in (RuntimeError("close"), KeyboardInterrupt("close"), SystemExit("close")):
                with self.subTest(handle=handle, exception=type(exception)):
                    self.backend = FakeBackend(self.m)
                    owner = self.pin()
                    close = self.backend.close

                    def failing_close(current):
                        if current == handle:
                            self.backend.closed.append(current)
                            raise exception
                        close(current)

                    self.backend.close = failing_close
                    expected = self.m.StartupPinCloseError if isinstance(exception, Exception) else type(exception)
                    with self.assertRaises(expected) as raised:
                        owner.close()
                    if isinstance(exception, Exception):
                        self.assertEqual(raised.exception.errors, (exception,))
                    else:
                        self.assertIs(raised.exception, exception)
                    self.assertEqual(owner.close_errors, (exception,))
                    self.assertEqual(self.backend.closed, [4, 3, 2, 1])
                    self.assertEqual(self.backend.live, {handle})

    def test_close_first_interrupt_beats_ordinary_failures(self):
        owner = self.pin()
        faults = {4: RuntimeError("ordinary"), 3: KeyboardInterrupt("first interrupt"),
                  2: SystemExit("later interrupt")}
        original = self.backend.close

        def close(handle):
            if handle in faults:
                self.backend.closed.append(handle)
                raise faults[handle]
            original(handle)

        self.backend.close = close
        with self.assertRaises(KeyboardInterrupt) as raised:
            owner.close()
        self.assertIs(raised.exception, faults[3])
        self.assertEqual(owner.close_errors, tuple(faults.values()))
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])

    def test_normal_context_close_failure_is_reported(self):
        with self.assertRaises(self.m.StartupPinCloseError):
            with self.pin() as owner:
                self.backend.close_failures = {1}
        self.assertTrue(owner.closed)
        self.assertFalse(owner.close_confirmed)
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])

    def test_body_exception_wins_over_close_failures(self):
        for exc in (ValueError("body"), KeyboardInterrupt("body"), SystemExit("body")):
            self.backend = FakeBackend(self.m)
            with self.assertRaises(type(exc)) as raised:
                with self.pin():
                    self.backend.close_failures = {1, 4}
                    raise exc
            self.assertIs(raised.exception, exc)
            self.assertEqual(self.backend.closed, [4, 3, 2, 1])

    def test_constructor_exception_wins_over_close_failures(self):
        exc = KeyboardInterrupt("read")
        self.backend = FakeBackend(self.m, fail="read:0", exception=exc)
        self.backend.close_failures = {4, 2}
        with self.assertRaises(KeyboardInterrupt) as raised:
            self.pin()
        self.assertIs(raised.exception, exc)
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])

    def test_construction_failure_notes_unconfirmed_close_without_sensitive_details(self):
        exception = RuntimeError("sensitive original")
        self.backend = FakeBackend(self.m, fail="read:0", exception=exception)
        self.backend.close_failures = {4, 2}
        with self.assertRaises(RuntimeError) as raised:
            self.pin()
        self.assertIs(raised.exception, exception)
        self.assertEqual(getattr(exception, "__notes__", []), ["Startup HANDLE cleanup unconfirmed: 2"])

    def test_body_interrupt_notes_mixed_close_faults_and_retains_object(self):
        exception = KeyboardInterrupt("body")
        faults = {4: SystemExit("sensitive close"), 2: RuntimeError("sensitive close")}
        original = self.backend.close

        def close(handle):
            if handle in faults:
                self.backend.closed.append(handle)
                raise faults[handle]
            original(handle)

        with self.assertRaises(KeyboardInterrupt) as raised:
            with self.pin() as owner:
                self.backend.close = close
                raise exception
        self.assertIs(raised.exception, exception)
        self.assertEqual(getattr(exception, "__notes__", []), ["Startup HANDLE cleanup unconfirmed: 2"])
        self.assertEqual(owner.close_errors, tuple(faults.values()))
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])

    def test_note_override_cannot_mask_body_exception(self):
        class CustomError(RuntimeError):
            def add_note(self, note):
                raise SystemExit("override must not run")

        exception = CustomError("body")
        with self.assertRaises(CustomError) as raised:
            with self.pin():
                self.backend.close_failures = {1}
                raise exception
        self.assertIs(raised.exception, exception)
        self.assertEqual(getattr(exception, "__notes__", []), ["Startup HANDLE cleanup unconfirmed: 1"])

    def test_nested_validation_cleanup_does_not_duplicate_note(self):
        exception = RuntimeError("query")
        self.backend = FakeBackend(self.m, fail="query:4:2", exception=exception)
        self.backend.close_failures = {1}
        with self.assertRaises(RuntimeError) as raised:
            self.pin()
        self.assertIs(raised.exception, exception)
        self.assertEqual(exception.__notes__, ["Startup HANDLE cleanup unconfirmed: 1"])

    def test_note_attribute_failure_never_masks_primary_exception(self):
        class CustomError(RuntimeError):
            @property
            def __notes__(self):
                raise SystemExit("note attribute fault")

        exception = CustomError("body")
        with self.assertRaises(CustomError) as raised:
            with self.pin():
                self.backend.close_failures = {1}
                raise exception
        self.assertIs(raised.exception, exception)
        self.assertEqual(self.backend.closed, [4, 3, 2, 1])

    def test_revalidate_failure_closes_owner(self):
        owner = self.pin()
        self.backend.mutations[(4, 3)] = {"change_time": 101}
        with self.assertRaises(self.m.StartupPinError):
            owner.revalidate()
        self.assertTrue(owner.closed)
        self.assertFalse(self.backend.live)

    def test_revalidate_each_query_exception_preserves_object_and_cleanup(self):
        for handle in range(1, 5):
            self.backend = FakeBackend(self.m)
            owner = self.pin()
            exception = KeyboardInterrupt("revalidate")
            self.backend.fail = f"query:{handle}:3"
            self.backend.exception = exception
            with self.assertRaises(KeyboardInterrupt) as raised:
                owner.revalidate()
            self.assertIs(raised.exception, exception)
            self.assertFalse(self.backend.live)

    def test_bounded_multichunk_and_short_read_are_complete(self):
        for step in (65536, 7):
            self.backend = FakeBackend(self.m)
            self.backend.data = b"z" * (65536 + 13)
            original_read = self.backend.read

            def short_read(handle, offset, count):
                return original_read(handle, offset, min(step, count))

            self.backend.read = short_read
            with self.pin() as owner:
                self.assertEqual(owner.content, self.backend.data)
                self.assertEqual(owner.sha256, hashlib.sha256(self.backend.data).hexdigest())

    def test_multichunk_second_read_interrupt_and_eof_cleanup(self):
        for exception in (RuntimeError("read"), KeyboardInterrupt("read"), SystemExit("read")):
            self.backend = FakeBackend(self.m, fail="read:65536", exception=exception)
            self.backend.data = b"z" * (65536 + 13)
            with self.assertRaises(type(exception)) as raised:
                self.pin()
            self.assertIs(raised.exception, exception)
            self.assertFalse(self.backend.live)
        self.backend = FakeBackend(self.m)
        self.backend.data = b"z" * (65536 + 13)
        original_read = self.backend.read
        self.backend.read = lambda handle, offset, count: original_read(handle, offset, count) if offset == 0 else b""
        with self.assertRaises(self.m.StartupPinError):
            self.pin()
        self.assertFalse(self.backend.live)

    def test_revalidate_metadata_structure_and_all_field_drift(self):
        fields = {"volume_serial": 8, "file_id": b"y" * 16, "directory": True,
                  "reparse": True, "delete_pending": True, "file_type": "pipe",
                  "links": 2, "size": 1, "change_time": 101}
        for field, value in fields.items():
            self.backend = FakeBackend(self.m, mutations={(4, 2): {field: value}})
            with self.subTest(field=field), self.assertRaises(self.m.StartupPinError):
                self.pin()
            self.assertFalse(self.backend.live)
        self.backend = FakeBackend(self.m)
        self.backend.query = lambda handle: {"directory": True}
        with self.assertRaises(self.m.StartupPinError):
            self.pin()
        self.assertEqual(self.backend.closed, [1])

    def test_metadata_ancestor_pending_and_strict_types(self):
        for handle in range(1, 4):
            for mutation in ({"delete_pending": True}, {"links": False}, {"size": False},
                             {"file_type": "char"}, {"directory": 1}, {"change_time": -(2**63)-1}):
                self.backend = FakeBackend(self.m, mutations={(handle, 1): mutation})
                with self.subTest(handle=handle, mutation=mutation), self.assertRaises(self.m.StartupPinError):
                    self.pin()
                self.assertFalse(self.backend.live)

    def test_invalid_handle_and_nonstring_path_rejected(self):
        for handle in (0, -1, True, None, "1", 2**64 - 1):
            self.backend = FakeBackend(self.m)
            self.backend.open_root = lambda drive: handle
            with self.subTest(handle=handle), self.assertRaises(self.m.StartupPinError):
                self.pin()
        for path in (None, b"C:\\a", 1):
            with self.subTest(path=path), self.assertRaises(self.m.StartupPinError):
                self.m.pin_startup_file(path, _backend=self.backend)

    def test_reserved_alias_before_extension_with_space_rejected(self):
        for path in ("C:\\CON .txt", "C:\\NUL .exe", "C:\\CLOCK$"):
            self.backend = FakeBackend(self.m)
            with self.subTest(path=path), self.assertRaises(self.m.StartupPinError):
                self.m.pin_startup_file(path, _backend=self.backend)
            self.assertEqual(self.backend.calls, [])

    def test_uninitialized_owner_rejects_access_enter_and_revalidation(self):
        owner = self.m.PinnedStartupFile(self.backend, 10)
        for operation in (lambda: owner.content, lambda: owner.sha256, owner.__enter__, owner.revalidate):
            with self.assertRaises(self.m.StartupPinError):
                operation()
        owner.close()
        self.assertTrue(owner.close_confirmed)

    def test_native_backend_module_name_matches_task2(self):
        from unittest.mock import patch
        import sys
        import types
        module = types.ModuleType("icode.windows_startup_native")
        module.WindowsStartupPinBackend = lambda: self.backend
        with patch.object(self.m.os, "name", "nt"), patch.dict(sys.modules, {module.__name__: module}):
            with self.m.pin_startup_file("C:\\a\\b\\start.exe") as owner:
                self.assertEqual(owner.content, self.backend.data)

    def test_portable_default_refuses_native_claim(self):
        import os
        if os.name != "nt":
            with self.assertRaises(self.m.StartupPinError):
                self.m.pin_startup_file("C:\\a.exe")


if __name__ == "__main__":
    unittest.main()
