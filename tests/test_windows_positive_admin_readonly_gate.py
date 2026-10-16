"""Actual readonly gate algorithms; modeled OS calls confer no native authority."""
from __future__ import annotations
import copy
import ctypes as c
from ctypes import wintypes as t
import hashlib
import importlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from tests.test_windows_positive_loopback_admin_native import NativeStore, snapshot, serialized, put
from tests import test_windows_positive_loopback_admin_native as native_tests

NAME = "scripts.windows_positive_admin_readonly_gate"
MODEL = Path(tempfile.gettempdir()).resolve() / "icode-readonly-model"
SETUP_PYTHON = MODEL / "setup/python.exe"
PRIVATE_ROOT = MODEL / "private"


def valid_environment(ctx):
    return dict(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted", RUNNER_OS="Windows",
        GITHUB_REPOSITORY=ctx["repository"], GITHUB_SHA=ctx["source_sha"], GITHUB_RUN_ID=ctx["run_id"],
        GITHUB_RUN_ATTEMPT=str(ctx["run_attempt"]), GITHUB_JOB=ctx["job"],
        RUNNER_ARCH="X64" if ctx["matrix"] == "x64" else "ARM64", GITHUB_REF="refs/heads/main",
        GITHUB_WORKFLOW_REF="ayukyo/icode/.github/workflows/ci.yml@refs/heads/main",
        GITHUB_WORKFLOW_SHA=ctx["source_sha"], ICODE_CI_POSITIVE_LOOPBACK_ADMIN="1",
        ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER="1")


try:
    gate = importlib.import_module(NAME)
except ModuleNotFoundError as error:
    if error.name != NAME:
        raise
    gate = None


class Function:
    def __init__(self, body): self.body = body
    def __call__(self, *args): return self.body(*args)


class AccountOS:
    def __init__(self):
        self.current = None
        self.sid = "S-1-5-21-1-2-3-1001"
        self.result = 0
        self.calls = []
        self.NetUserAdd = Function(self.add)
        self.NetUserDel = Function(self.delete)
    def add(self, server, level, value, parameter):
        self.calls.append(("add", server, level))
        if self.result == 0: self.current = self.sid
        return self.result
    def delete(self, server, name):
        self.calls.append(("delete", server, name))
        self.current = None
        return 0
    def account(self, w, name, *, absent=False, allow_absent=False):
        if absent:
            if self.current is not None: raise RuntimeError("modeled_account_exists")
            return None
        if self.current is None and not allow_absent: raise RuntimeError("modeled_sid_unknown")
        return self.current


class ParentOS:
    def __init__(self):
        self.system_directory = MODEL / "windows/System32"
        self.k = self.a = self
        self.events = []
        self.created = True
        self.outputs = (101, 102, 1234, 1235)
        self.alive = True
        self.user = "S-1-5-21-1-2-3-1001"
        self.creation = 5678
        self.admin = False
        self.fail = set()
        self.CreateProcessWithLogonW = Function(self.create)
    def create(self, user, domain, secret, logon, image, command, flags, env, cwd, startup, output):
        block = []
        address = env.value
        cursor = 0
        while True:
            value = c.wstring_at(address + cursor * c.sizeof(c.c_wchar))
            if not value: break
            block.append(value)
            cursor += len(value) + 1
        self.events.append(("create", image, command.value, flags, block, logon, cwd))
        record = output._obj
        record.process, record.thread, record.pid, record.tid = self.outputs
        return int(self.created)
    def WaitForSingleObject(self, handle, milliseconds):
        self.events.append(("wait", handle, milliseconds))
        if "wait" in self.fail: raise RuntimeError("modeled_wait")
        return 258 if self.alive else 0
    def TerminateProcess(self, handle, code):
        self.events.append(("terminate", handle))
        if "terminate" in self.fail: return 0
        self.alive = False
        return 1
    def process_user(self, handle): return self.user
    def process_created(self, handle): return self.creation
    def OpenProcessToken(self, handle, mask, output): put(output, t.HANDLE, 201); return 1
    def DuplicateToken(self, handle, level, output): put(output, t.HANDLE, 202); return 1
    def ConvertStringSidToSidW(self, value, output): put(output, c.c_void_p, 203); return 1
    def CheckTokenMembership(self, token, sid, output): put(output, t.BOOL, self.admin); return 1
    def LocalFree(self, pointer):
        self.events.append(("free", pointer.value))
        return pointer if "free" in self.fail else None
    def close(self, handle):
        value = handle.value if hasattr(handle, "value") else handle
        self.events.append(("close", value))
        if value in self.fail: raise RuntimeError("modeled_close_" + str(value))


def store_fixture():
    store = NativeStore()
    # Rebind every absolute role from the original POSIX-only software model.
    # No filesystem/parser method is mocked; these paths need not exist for
    # the actual ledger/admission shape parser, but must be host-absolute.
    old_root, old_system = store.root, store.w.system_directory
    store.root = MODEL / old_root.name
    store.w.system_directory = MODEL / "windows/System32"
    for collection in ("routes", "loader_images", "tool"):
        for row in store.data["readonly_prepare"][collection]:
            old = Path(row["path"])
            if old == old_root or old_root in old.parents:
                row["path"] = str(store.root / old.relative_to(old_root))
            elif old == old_system or old_system in old.parents:
                row["path"] = str(store.w.system_directory / old.relative_to(old_system))
            else:
                row["path"] = str(MODEL.anchor)
    boot = store.boot
    for index, kind in enumerate(("abi", "get", "get")):
        record = dict(kind=kind, job="Local\\ICODE.Positive." + boot["session"] + ".command." + str(index),
            output="command-" + str(index) + ".out", state="reaped", pid=9000 + index,
            process_created=10000 + index, resume_permitted=True, resume_attempted=True,
            resume_returned=1, exit_code=0, timed_out=False, reaped=True)
        store.data["commands"].append(record)
        if kind == "abi":
            observed = native_tests.TestAdminNative().abi_observation()
            store.files[record["output"]] = serialized(observed)
        else:
            raw = snapshot([["S-1-5-18", 7]])
            digest = hashlib.sha256(serialized(raw)).hexdigest()
            raw["process_reaped"] = None
            store.files[record["output"]] = serialized(raw)
            store.data["reads"].append(dict(started_ms=180000 + index, finished_ms=180001 + index,
                command_index=index, raw_sha256=digest,
                reader_sha256=store.data["frozen_files"][0]["sha256"]))
    store.files["cleanup.json"] = serialized(dict(schema=1,
        binding=hashlib.sha256(serialized(boot)).hexdigest(), domain="icode_positive_bootstrap_v1",
        stage="not_owned", delete_verified=None, native_restoration_verified=None))
    store.flush()
    return store


class TestReadonlyGate(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(gate, "readonly gate component absent; expected facility boundary")
        self.environment = valid_environment(store_fixture().data["context"])
        environment_patch = patch.dict(gate.os.environ, self.environment, clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
    def validate(self, store):
        return gate.validate_readonly_store(store, copy.deepcopy(store.data["context"]),
            store.data["account_name"], store.data["account_sid"], copy.deepcopy(store.data["parent"]))
    def account(self, model=None):
        model = model or AccountOS()
        account = gate.Account.__new__(gate.Account)
        account.w = N(system_directory=MODEL / "windows/System32")
        account.native = N(_account=model.account)
        account.net = model
        account.name, account.sid, account.owned = "icodeprobe_test", None, False
        account.password = c.create_unicode_buffer("aA1!sensitive")
        return account, model
    def parent(self, model=None, executable=None):
        model = model or ParentOS()
        value = gate.SuspendedParent(model, N(), MODEL / "checkout", executable or SETUP_PYTHON)
        account = N(name="icodeprobe_test", sid=model.user, password=c.create_unicode_buffer("aA1!"))
        return value, model, account
    def test_ready_exact_schema_and_wire_rejections(self):
        raw = gate.wire(gate.READY) + b"\n"
        self.assertEqual(gate.parse_receipt(raw, "readonly_ready"), gate.READY)
        values = [raw[:-1], raw + raw, raw + b"x", b"x" * 502, b"\xff\n",
            b'{"schema":1,"schema":1}\n', gate.wire(dict(gate.READY, extra=1)) + b"\n",
            gate.wire(dict(gate.READY, schema=True)) + b"\n",
            gate.wire(dict(gate.READY, sdk=1)) + b"\n",
            gate.wire(dict(gate.READY, stage="readonly_failed")) + b"\n"]
        for value in values:
            with self.subTest(raw=value), self.assertRaises(Exception): gate.parse_receipt(value, "readonly_ready")
    def test_frozen_root_is_existing_absolute_canonical_and_schema_exact(self):
        with tempfile.TemporaryDirectory(prefix="icode-positive-admin-") as name:
            root = str(Path(name).resolve(strict=True))
            good = dict(schema=1, stage="frozen", root=root)
            self.assertEqual(gate.parse_receipt(gate.wire(good) + b"\n", "frozen"), good)
            for changed in (dict(good, schema=True), dict(good, root="relative"),
                            dict(good, root=root + "/missing"), dict(good, extra=1)):
                with self.subTest(changed=changed), self.assertRaises(Exception):
                    gate.parse_receipt(gate.wire(changed) + b"\n", "frozen")
    def test_real_ledger_and_complete_original_gets_accept_without_restoration_claim(self):
        store = store_fixture()
        result = self.validate(store)
        self.assertEqual(result["stage"], "readonly_verified")
        self.assertFalse(store.data["exact_restoration"])
        self.assertEqual(gate.decode(store.files["cleanup.json"], 500)["stage"], "not_owned")
    def test_real_ledger_unknown_fields_and_readonly_state_mutations_reject(self):
        self.assertEqual(self.validate(store_fixture())["stage"], "readonly_verified")
        for key, value in (("extra", True), ("phase", "prepared"), ("owned_intent", True),
            ("first_error", "get_failed"), ("cleanup_error", "cleanup_failed"),
            ("readonly_prepare", None), ("target_attributes", 0), ("add_verified", True)):
            store = store_fixture(); store.data[key] = value
            with self.subTest(key=key), self.assertRaises(Exception): self.validate(store)
    def test_context_account_parent_binding_does_not_trust_ready_stdout(self):
        store = store_fixture()
        self.assertEqual(self.validate(store)["stage"], "readonly_verified")
        cases = [(dict(store.data["context"], source_sha="f" * 40), store.data["account_name"], store.data["account_sid"], store.data["parent"]),
            (store.data["context"], "icodeprobe_other", store.data["account_sid"], store.data["parent"]),
            (store.data["context"], store.data["account_name"], "S-1-5-21-9-9-9-1001", store.data["parent"]),
            (store.data["context"], store.data["account_name"], store.data["account_sid"], dict(store.data["parent"], process_created=1))]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(Exception): gate.validate_readonly_store(store, *args)
    def test_each_command_requires_complete_successful_reap(self):
        self.assertEqual(self.validate(store_fixture())["stage"], "readonly_verified")
        for index in range(3):
            for field, value in (("reaped", False), ("exit_code", 4), ("timed_out", True), ("state", "cleanup_unknown"), ("kind", "add")):
                store = store_fixture(); store.data["commands"][index][field] = value
                with self.subTest(index=index, field=field), self.assertRaises(Exception): self.validate(store)
    def test_get_output_hash_reader_index_and_worker_self_credit_reject(self):
        self.assertEqual(self.validate(store_fixture())["stage"], "readonly_verified")
        for mode in ("hash", "reader", "duplicate", "missing", "worker", "mapping", "invalid"):
            store = store_fixture()
            if mode == "hash": store.data["reads"][0]["raw_sha256"] = "0" * 64
            if mode == "reader": store.data["reads"][0]["reader_sha256"] = "0" * 64
            if mode == "duplicate": store.data["reads"][1] = copy.deepcopy(store.data["reads"][0])
            if mode == "missing": store.data["reads"].pop()
            if mode in ("worker", "mapping"):
                raw = gate.decode(store.files["command-2.out"], 1048576)
                raw["process_reaped"] = True if mode == "worker" else None
                if mode == "mapping":
                    raw["entries"][0][1] = 8
                    reaped = dict(raw, process_reaped=True)
                    store.data["reads"][1]["raw_sha256"] = hashlib.sha256(serialized(reaped)).hexdigest()
                store.files["command-2.out"] = serialized(raw)
            if mode == "invalid": store.files["command-2.out"] = b"not-json"
            with self.subTest(mode=mode), self.assertRaises(Exception): self.validate(store)
    def test_sdk_and_loader_admission_cannot_borrow_ready_stdout(self):
        self.assertEqual(self.validate(store_fixture())["stage"], "readonly_verified")
        for field in ("sdk_layout_verified", "python_binding_verified", "loader_verified", "canaries_verified"):
            store = store_fixture(); store.data["readonly_prepare"][field] = False
            with self.subTest(field=field), self.assertRaises(Exception): self.validate(store)
    def test_cleanup_original_must_be_exact_not_owned_bootstrap_binding(self):
        self.assertEqual(self.validate(store_fixture())["stage"], "readonly_verified")
        for key, value in (("binding", "0" * 64), ("stage", "cleaned"),
            ("delete_verified", True), ("native_restoration_verified", True), ("extra", False)):
            store = store_fixture(); raw = gate.decode(store.files["cleanup.json"], 500)
            raw[key] = value; store.files["cleanup.json"] = serialized(raw)
            with self.subTest(key=key), self.assertRaises(Exception): self.validate(store)
    def test_account_add_zero_is_only_ownership_and_delete_requires_same_sid(self):
        account, model = self.account(); sid = account.create()
        self.assertTrue(account.owned); self.assertEqual(sid, model.sid)
        model.current = "S-1-5-21-9-8-7-1001"
        with self.assertRaisesRegex(RuntimeError, "replaced"): account.delete()
        self.assertEqual([x[0] for x in model.calls], ["add"])
        model.current = sid; account.delete()
        self.assertFalse(account.owned); self.assertIsNone(model.current)
    def test_failed_add_and_existing_foreign_account_never_delete(self):
        for mode in ("exists", "failed"):
            account, model = self.account()
            if mode == "exists": model.current = model.sid
            else: model.result = 5
            with self.subTest(mode=mode), self.assertRaises(RuntimeError): account.create()
            account.delete()
            self.assertFalse(account.owned)
            self.assertNotIn("delete", [x[0] for x in model.calls])
    def test_successful_add_sid_unknown_fails_without_guess_delete_and_zeroes_secret(self):
        account, model = self.account()
        original = model.account
        def lookup(w, name, **options):
            if not options.get("absent") and not options.get("allow_absent"): raise RuntimeError("sid unavailable")
            return original(w, name, **options)
        account.native._account = lookup
        with self.assertRaisesRegex(RuntimeError, "sid unavailable"): account.create()
        self.assertTrue(account.owned)
        with self.assertRaisesRegex(RuntimeError, "identity_unknown"): account.delete()
        account.clear_secret()
        self.assertEqual(c.string_at(c.addressof(account.password), c.sizeof(account.password)), b"\0" * c.sizeof(account.password))
        self.assertNotIn("delete", [x[0] for x in model.calls])
    def test_constructor_layout_or_random_failure_never_leaves_mutable_secret(self):
        model = AccountOS(); buffers = []
        original = c.create_unicode_buffer
        def allocate(*args):
            value = original(*args); buffers.append(value); return value
        windows_layout = c.sizeof(t.DWORD) == 4 and c.sizeof(c.c_void_p) == 8
        with patch.object(gate.c, "WinDLL", lambda *args, **kwargs: model, create=True), \
             patch.object(gate.c, "create_unicode_buffer", allocate), \
             patch.object(gate.secrets, "token_bytes", side_effect=RuntimeError("random unavailable")):
            with self.assertRaisesRegex(RuntimeError, "random unavailable" if windows_layout else "account_layout"):
                gate.Account(N(system_directory=MODEL / "windows/System32"), N())
        for value in buffers:
            self.assertEqual(c.string_at(c.addressof(value), c.sizeof(value)), b"\0" * c.sizeof(value))
    def test_constructor_partial_password_fill_failure_zeroes_allocated_buffer(self):
        model = AccountOS(); original_sizeof, original_memset = c.sizeof, c.memset
        underlying = c.create_unicode_buffer(65)
        class Buffer:
            def __setitem__(self, index, value):
                if index == 3: raise RuntimeError("fill failed")
                underlying[index] = value
        buffer = Buffer()
        def size(value): return original_sizeof(underlying if value is buffer else value)
        def zero(value, byte, length): return original_memset(underlying if value is buffer else value, byte, length)
        windows_layout = c.sizeof(t.DWORD) == 4 and c.sizeof(c.c_void_p) == 8
        with patch.object(gate.c, "WinDLL", lambda *args, **kwargs: model, create=True), \
             patch.object(gate.c, "create_unicode_buffer", lambda count: buffer), \
             patch.object(gate.c, "sizeof", size), patch.object(gate.c, "memset", zero), \
             patch.object(gate.secrets, "token_bytes", return_value=b"x" * 60):
            with self.assertRaisesRegex(RuntimeError, "fill failed" if windows_layout else "account_layout"):
                gate.Account(N(system_directory=MODEL / "windows/System32"), N())
        self.assertEqual(c.string_at(c.addressof(underlying), original_sizeof(underlying)), b"\0" * original_sizeof(underlying))
    def test_parent_success_uses_fixed_real_test_suspended_no_credential_environment(self):
        parent, model, account = self.parent()
        identity = parent.create(account)
        self.assertEqual(identity, dict(pid=1234, process_created=5678))
        event = model.events[0]
        self.assertEqual(event[1], str(SETUP_PYTHON))
        self.assertEqual(event[2], subprocess.list2cmdline([event[1], "-m", "unittest", gate.METHOD, "-v"]))
        self.assertEqual(event[3], 0x4 | 0x400 | 0x08000000)
        self.assertEqual({x.split("=", 1)[0] for x in event[4]}, {"SystemRoot", "SystemDrive", "TEMP", "TMP"})
        parent.reap(); parent.close()
        self.assertFalse(model.alive)
        self.assertIn(("close", 101), model.events); self.assertIn(("close", 102), model.events)
        self.assertFalse(any(x[0] == "resume" for x in model.events))
    def test_failed_process_api_undefined_nonzero_outputs_are_never_owned(self):
        for values in ((0, 0, 0, 0), (901, 902, 903, 904)):
            parent, model, account = self.parent(); model.created = False; model.outputs = values
            with self.subTest(values=values), self.assertRaises(RuntimeError): parent.create(account)
            parent.reap(); parent.close()
            self.assertFalse(parent.created)
            self.assertEqual([x[0] for x in model.events], ["create"])
    def test_successful_original_creation_identity_rejection_still_reaps_owned_child(self):
        for mode in ("user", "creation", "admin"):
            parent, model, account = self.parent()
            if mode == "user": model.user = "S-1-5-21-9-9-9-1001"
            if mode == "creation": model.creation = 0
            if mode == "admin": model.admin = True
            with self.subTest(mode=mode), self.assertRaises(RuntimeError): parent.create(account)
            parent.reap(); parent.close()
            self.assertFalse(model.alive)
            self.assertIn(("terminate", 101), model.events)
    def test_gate_selects_setup_interpreter_for_standard_parent_before_account_creation(self):
        captured = []; store = store_fixture(); ctx = store.data["context"]
        environment = dict(valid_environment(ctx), GITHUB_WORKSPACE=str(gate.CHECKOUT))
        w = N(assert_admin=lambda: captured.append("admin"))
        def parent(w, native, checkout, executable):
            captured.append(("parent", checkout, executable)); return N()
        def account(w, native): captured.append("account"); return N()
        with patch.object(gate.sys, "platform", "win32"), patch.object(gate.sys, "version_info", (3, 12)), \
             patch.object(gate.sys, "flags", N(isolated=1, no_site=1, dont_write_bytecode=1)), \
             patch.object(gate, "Win32", lambda: w), patch.object(gate, "Native", lambda: N()), \
             patch.object(gate, "SuspendedParent", parent), patch.object(gate, "Account", account), \
             patch.dict(gate.os.environ, environment, clear=True):
            value = gate.Gate()
        self.assertEqual(captured, ["admin", ("parent", gate.CHECKOUT, Path(gate.sys.executable).absolute()), "account"])
        self.assertIsNone(value.root)
    def test_parent_command_utf16_limit_rejects_before_process_creation(self):
        parent, model, account = self.parent(executable=MODEL / ("x" * 1100 + ".exe"))
        with self.assertRaisesRegex(RuntimeError, "command_limit"): parent.create(account)
        self.assertEqual(model.events, [])
    def test_token_free_and_both_token_closes_are_independent(self):
        parent, model, account = self.parent(); model.admin = True; model.fail = {"free", 202, 201}
        with self.assertRaisesRegex(RuntimeError, "is_admin") as caught: parent.create(account)
        self.assertIn(("free", 203), model.events)
        self.assertIn(("close", 202), model.events); self.assertIn(("close", 201), model.events)
        self.assertTrue(any("cleanup_unknown" in x for x in caught.exception.__notes__))
        model.fail.clear(); parent.reap(); parent.close()
    def test_parent_terminate_failure_does_not_skip_wait_or_handle_releases(self):
        parent, model, account = self.parent(); parent.create(account); model.fail = {"terminate", 102}
        with self.assertRaises(Exception): parent.reap()
        with self.assertRaises(Exception): parent.close()
        self.assertIn(("wait", 101, 2000), model.events)
        self.assertIn(("close", 101), model.events); self.assertIn(("close", 102), model.events)
    def test_parent_already_exited_is_waited_not_killed(self):
        parent, model, account = self.parent(); parent.create(account); model.alive = False
        parent.reap(); parent.close()
        self.assertFalse(any(x[0] == "terminate" for x in model.events))
    def entry_fixture(self, *, exit_code=0, timeout=False, stderr=b"", stdout=None, close_fail=False):
        value = gate.Gate.__new__(gate.Gate)
        value.root, value.checkout = PRIVATE_ROOT, MODEL / "checkout"
        events, streams = [], []
        def temporary(**kwargs):
            stream = io.BytesIO(); streams.append(stream)
            original_close = stream.close
            def close():
                events.append(("stream_close", len(streams), id(stream)))
                original_close()
            stream.close = close
            return stream
        class Process:
            def __init__(self, argv, **options):
                events.append(("popen", argv, options))
                options["stdout"].write(gate.wire(gate.READY) + b"\n" if stdout is None else stdout)
                options["stderr"].write(stderr)
                self.alive = timeout; self.calls = 0
                def close():
                    events.append(("handle_close",))
                    if close_fail: raise RuntimeError("handle close failed")
                self._handle = N(Close=close)
            def wait(self, timeout):
                self.calls += 1; events.append(("process_wait", timeout))
                if self.calls == 1 and self.alive: raise subprocess.TimeoutExpired("fixed", timeout)
                return exit_code
            def poll(self): return None if self.alive else exit_code
            def kill(self): events.append(("kill",)); self.alive = False
        return value, events, streams, temporary, Process
    def test_entry_requires_complete_exit_and_clean_stderr_not_early_stdout(self):
        for result, error in ((4, b""), (0, b"warning")):
            value, events, streams, temporary, process = self.entry_fixture(exit_code=result, stderr=error)
            with patch.object(gate.tempfile, "TemporaryFile", temporary), patch.object(gate.subprocess, "Popen", process), \
                 patch.object(gate.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
                with self.subTest(result=result, error=error), self.assertRaises(RuntimeError): value._entry("readonly_ready", [], 180)
            self.assertTrue(all(x.closed for x in streams)); self.assertIn(("handle_close",), events)
    def test_entry_timeout_and_close_failure_preserve_timeout_and_attempt_all_cleanup(self):
        value, events, streams, temporary, process = self.entry_fixture(timeout=True, close_fail=True)
        with patch.object(gate.tempfile, "TemporaryFile", temporary), patch.object(gate.subprocess, "Popen", process), \
             patch.object(gate.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            with self.assertRaises(subprocess.TimeoutExpired) as caught: value._entry("readonly_ready", [], 180)
        self.assertIn(("kill",), events); self.assertIn(("process_wait", 4), events)
        self.assertTrue(all(x.closed for x in streams))
        self.assertTrue(any("cleanup_unknown" in x for x in caught.exception.__notes__))
    def test_entry_success_environment_excludes_control_files_and_credentials(self):
        value, events, streams, temporary, process = self.entry_fixture()
        with patch.object(gate.tempfile, "TemporaryFile", temporary), patch.object(gate.subprocess, "Popen", process), \
             patch.object(gate.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             patch.dict(gate.os.environ, {"GITHUB_ENV": "secret", "GITHUB_OUTPUT": "secret", "PASSWORD": "secret", "GITHUB_SHA": "a" * 40}, clear=True):
            self.assertEqual(value._entry("readonly_ready", [], 180), gate.READY)
        event = next(x for x in events if x[0] == "popen")
        self.assertEqual(event[2]["env"], {"GITHUB_SHA": "a" * 40})
        self.assertEqual(event[1][:4], [str(PRIVATE_ROOT / "runtime/python.exe"), "-I", "-S", "-B"])
        self.assertTrue(event[2]["close_fds"]); self.assertTrue(all(x.closed for x in streams))
    def test_entry_success_body_cannot_hide_owned_process_handle_close_failure(self):
        value, events, streams, temporary, process = self.entry_fixture(close_fail=True)
        with patch.object(gate.tempfile, "TemporaryFile", temporary), patch.object(gate.subprocess, "Popen", process), \
             patch.object(gate.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            with self.assertRaisesRegex(RuntimeError, "handle close failed"): value._entry("readonly_ready", [], 180)
        self.assertTrue(all(x.closed for x in streams))
        self.assertIn(("process_wait", 4), events)
    def test_entry_second_stream_allocation_failure_closes_first_without_launch(self):
        value, events, streams, temporary, process = self.entry_fixture()
        body = RuntimeError("second allocation failed")
        def allocate(**options):
            if streams: raise body
            return temporary(**options)
        with patch.object(gate.tempfile, "TemporaryFile", allocate), patch.object(gate.subprocess, "Popen", process):
            with self.assertRaises(RuntimeError) as caught: value._entry("readonly_ready", [], 180)
        self.assertIs(caught.exception, body)
        self.assertEqual(len(streams), 1); self.assertTrue(streams[0].closed)
        self.assertFalse(any(x[0] == "popen" for x in events))
    def test_gate_run_body_error_does_not_skip_any_independent_owned_cleanup(self):
        value = gate.Gate.__new__(gate.Gate)
        events = []; body = RuntimeError("freeze failed")
        def release(label):
            events.append(label)
            raise RuntimeError(label)
        value.parent = N(reap=lambda: release("reap"), close=lambda: release("parent_close"))
        value.account = N(name="icodeprobe_test", delete=lambda: release("delete"), clear_secret=lambda: release("clear"))
        # External fixed executable boundary fails before any account acquisition;
        # real Gate.run still owns attempt-all dispatch and primary-error policy.
        with patch.object(value, "_entry", side_effect=body):
            with self.assertRaises(RuntimeError) as caught: value.run()
        self.assertIs(caught.exception, body)
        self.assertEqual(events, ["reap", "parent_close", "delete", "clear"])
        self.assertTrue(any("cleanup_unknown" in x for x in body.__notes__))
    def test_gate_run_freezes_then_creates_then_validates_original_store_and_cleans(self):
        store = store_fixture(); value = gate.Gate.__new__(gate.Gate); events = []
        account, accounts = self.account(); accounts.sid = store.data["account_sid"]
        account.name = store.data["account_name"]
        parent, processes, unused = self.parent(); processes.user = accounts.sid
        parent_identity = store.data["parent"]
        processes.outputs = (101, 102, parent_identity["pid"], 1235)
        processes.creation = parent_identity["process_created"]
        value.parent, value.account, value.binding = parent, account, copy.deepcopy(store.data["context"])
        def reopen(root):
            self.assertEqual(root, store.root); events.append("reopen"); return store
        value.native = N(reopen=reopen)
        def entry(stage, arguments, timeout):
            events.append(stage)
            if stage == "frozen":
                self.assertEqual(accounts.calls, []); self.assertFalse(parent.created)
                return dict(schema=1, stage="frozen", root=str(store.root))
            self.assertTrue(account.owned); self.assertTrue(parent.created)
            self.assertEqual(c.string_at(c.addressof(account.password), c.sizeof(account.password)), b"\0" * c.sizeof(account.password))
            self.assertFalse(any(x[0] == "resume" for x in processes.events))
            return copy.deepcopy(gate.READY)
        # Only the external fixed entry executable is modeled here; _entry's
        # wire/exit behavior is independently exercised in the preceding tests.
        with patch.object(value, "_entry", entry), patch.object(value, "_probe", lambda: events.append("probe")):
            result = value.run()
        self.assertEqual(result["stage"], "readonly_verified")
        self.assertEqual(events, ["frozen", "probe", "readonly_ready", "reopen"])
        self.assertTrue(store.closed); self.assertFalse(account.owned); self.assertFalse(processes.alive)
        self.assertEqual([x[0] for x in accounts.calls], ["add", "delete"])
        self.assertFalse(store.data["exact_restoration"])
    def test_entry_child_failure_propagates_bounded_child_stage_and_exit(self):
        def receipt(code):
            return gate.wire(dict(schema=1, stage="failed", state="unknown", error=code)) + b"\n"
        cases = [("bounded_stage", receipt("create_directory"), ["child_stage: create_directory"]),
            ("unknown_stage", receipt("unknown"), ["child_stage: unknown"]),
            ("leaky_stage", receipt("C:\\Users\\runner\\secret"), ["child_stage: unknown"]),
            ("typed_receipt", gate.wire(dict(schema=1, stage="failed", state="unknown",
                error="unknown", type="OSError", winerror=5)) + b"\n",
             ["child_stage: unknown", "child_kind: OSError", "child_winerror: 5"]),
            ("bad_typed_receipt", gate.wire(dict(schema=1, stage="failed", state="unknown",
                error="unknown", type="C:\\evil", winerror="x")) + b"\n",
             ["child_stage: unknown"]),
            ("not_failed_stage", gate.wire(dict(schema=1, stage="frozen", root="C:\\x")) + b"\n", []),
            ("receipt_limit", b'{"schema":1,"stage":"failed","state":"unknown","error":"' + b"x" * 600 + b'"}\n', []),
            ("not_json", b"Traceback (most recent call last):\r\n", []),
            ("empty", b"", [])]
        for name, raw, expected in cases:
            with self.subTest(child=name):
                value, events, streams, temporary, process = self.entry_fixture(exit_code=4, stdout=raw)
                with patch.object(gate.tempfile, "TemporaryFile", temporary), \
                     patch.object(gate.subprocess, "Popen", process), \
                     patch.object(gate.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
                    with self.assertRaisesRegex(RuntimeError, "gate_entry_exit") as caught:
                        value._entry("readonly_ready", [], 180)
                notes = list(caught.exception.__notes__)
                self.assertIn("child_exit: 4", notes)
                self.assertIn("entry_stage: readonly_ready", notes)
                for item in expected:
                    self.assertIn(item, notes)
                for prefix in ("child_stage: ", "child_kind: ", "child_winerror: "):
                    self.assertEqual([x for x in notes if x.startswith(prefix)],
                                     [x for x in expected if x.startswith(prefix)])
                self.assertTrue(all(x.closed for x in streams))
    def test_entry_crashed_child_reports_bounded_exception_type_without_receipt(self):
        crash = (b"Traceback (most recent call last):\r\n  File \"D:\\a\\icode\\icode\\scripts\\"
                 b"windows_positive_loopback_admin_entry.py\", line 52\r\n"
                 b"ModuleNotFoundError: No module named 'scripts'\r\n")
        value, events, streams, temporary, process = self.entry_fixture(exit_code=1, stdout=b"", stderr=crash)
        with patch.object(gate.tempfile, "TemporaryFile", temporary), \
             patch.object(gate.subprocess, "Popen", process), \
             patch.object(gate.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            with self.assertRaisesRegex(RuntimeError, "gate_entry_exit") as caught:
                value._entry("readonly_ready", [], 180)
        self.assertIn("child_type: ModuleNotFoundError", caught.exception.__notes__)
        self.assertIn("child_exit: 1", caught.exception.__notes__)
        self.assertIn("entry_stage: readonly_ready", caught.exception.__notes__)
        self.assertFalse(any(x.startswith("child_stage: ") for x in caught.exception.__notes__))
    def test_failure_receipt_emits_bounded_stage_and_bounded_child(self):
        child = RuntimeError("gate_entry_exit")
        child.add_note("child_exit: 4"); child.add_note("child_stage: create_directory")
        self.assertEqual(gate.failure_receipt(child), dict(schema=1, stage="readonly_failed",
            state="unknown", error="gate_entry_exit", child="create_directory", child_exit=4))
        crashed = RuntimeError("gate_entry_exit")
        crashed.add_note("child_exit: 1"); crashed.add_note("child_type: ModuleNotFoundError")
        self.assertEqual(gate.failure_receipt(crashed), dict(schema=1, stage="readonly_failed",
            state="unknown", error="gate_entry_exit", child="ModuleNotFoundError", child_exit=1))
        typed = RuntimeError("gate_entry_exit")
        typed.add_note("child_exit: 4"); typed.add_note("child_stage: unknown")
        typed.add_note("child_kind: OSError"); typed.add_note("child_winerror: 5")
        typed.add_note("entry_stage: readonly_ready")
        self.assertEqual(gate.failure_receipt(typed), dict(schema=1, stage="readonly_failed",
            state="unknown", error="gate_entry_exit", child="unknown", child_exit=4,
            child_type="OSError", child_winerror=5, entry="readonly_ready"))
        foreign = RuntimeError("gate_entry_exit")
        foreign.add_note("entry_stage: serve")
        self.assertEqual(gate.failure_receipt(foreign), dict(schema=1, stage="readonly_failed",
            state="unknown", error="gate_entry_exit"))
        self.assertEqual(gate.failure_receipt(RuntimeError("context_fixed")), dict(schema=1,
            stage="readonly_failed", state="unknown", error="context_fixed"))
    def test_failure_receipt_never_admits_unbounded_child_detail(self):
        leaky = RuntimeError("gate_entry_exit")
        leaky.add_note("child_stage: C:\\Users\\runner\\secret"); leaky.add_note("child_type: D")
        leaky.add_note("child_exit: not-a-number")
        leaky.add_note("child_kind: C:\\evil"); leaky.add_note("child_winerror: -5")
        self.assertEqual(gate.failure_receipt(leaky), dict(schema=1, stage="readonly_failed",
            state="unknown", error="gate_entry_exit", child="unknown"))
        for error in (OSError(3, "C:\\Users\\runner\\secret"), RuntimeError("S-1-5-32-544"),
                      RuntimeError("aA1!"), RuntimeError(""),
                      RuntimeError("d6a7a3abbd2c2b29730d8ccc2d1a1c9f5a1c30fd")):
            with self.subTest(error=repr(error)):
                self.assertEqual(gate.failure_receipt(error), dict(schema=1,
                    stage="readonly_failed", state="unknown", error="unknown"))
    def test_probe_full_env_reports_bounded_socket_failure(self):
        value, events, streams, temporary, process = self.entry_fixture(exit_code=0)
        events.clear()
        def probe_result(argv, **options):
            events.append(("probe", argv, options))
            options["stdout"].write(b"probe_full_env_failed OSError 10106\n")
            return N(wait=lambda timeout: 1, poll=lambda: 1, kill=lambda: None,
                     _handle=N(Close=lambda: None))
        with patch.object(gate.tempfile, "TemporaryFile", temporary), \
             patch.object(gate.subprocess, "Popen", probe_result), \
             patch.object(gate.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            with self.assertRaisesRegex(RuntimeError, "gate_probe_full_env") as caught:
                value._probe()
        notes = list(caught.exception.__notes__)
        self.assertIn("child_type: OSError", notes)
        self.assertIn("child_winerror: 10106", notes)
        self.assertTrue(all(x.closed for x in streams))
    def test_probe_full_env_passes_silently_when_socket_works(self):
        value, events, streams, temporary, process = self.entry_fixture(exit_code=0)
        events.clear()
        def probe_process(argv, **options):
            events.append(("probe", argv, options))
            options["stdout"].write(b"probe_full_env_ok\n")
            return N(wait=lambda timeout: 0, poll=lambda: 0, kill=lambda: None,
                     _handle=N(Close=lambda: None))
        with patch.object(gate.tempfile, "TemporaryFile", temporary), \
             patch.object(gate.subprocess, "Popen", probe_process), \
             patch.object(gate.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            self.assertIsNone(value._probe())
        argv = events[0][1]
        self.assertTrue(any(part == "-c" for part in argv))
    def test_main_has_no_free_command_or_root_arguments(self):
        with patch.object(gate.sys, "argv", ["fixed", "--root", "/foreign"]), \
             patch.object(gate, "Gate", side_effect=AssertionError("must not construct")):
            with self.assertRaisesRegex(RuntimeError, "no_arguments"): gate.main()


if __name__ == "__main__":
    unittest.main()
