"""Fixed CI readonly admission; never resumes its standard-user test parent."""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as t
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile

# -I intentionally omits the checkout from sys.path. Admit exactly the trusted
# candidate roots now, before any temporary account is created.
CHECKOUT = Path(__file__).resolve(strict=True).parents[1]
sys.path.insert(0, str(CHECKOUT))
sys.path.insert(0, str(CHECKOUT / "src"))

# These imports and native binding objects are resolved before a temporary user
# exists. Do not lazily import checkout code after creating that account.
from scripts.windows_positive_loopback_admin import _mapping
from scripts.windows_positive_loopback_admin_native import Native, context, ledger
from scripts.windows_positive_loopback_admin_store import PRIVATE, decode, wire
from scripts.windows_positive_loopback_admin_win32 import (
    Win32, STARTUP, PROCESS, checked, _release_owned,
)

METHOD = "tests.test_windows_appcontainer.TestWindowsAppContainer.test_Reviewer快照AppContainer只读边界与Job清理"
READY = dict(schema=1, stage="readonly_ready", sdk=True, loader=True,
             storage=True, standard_token=True, configuration_unchanged=True)
# PATH is required for winsock provider initialization on hosted runners:
# third-party catalog providers resolve their dependency DLLs through it.
ALLOWED_ENVIRONMENT = {"SystemRoot", "SystemDrive", "TEMP", "TMP", "PATH", "GITHUB_ACTIONS",
                       "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                       "GITHUB_JOB", "GITHUB_REF", "GITHUB_WORKFLOW_REF", "GITHUB_WORKFLOW_SHA",
                       "GITHUB_WORKSPACE", "RUNNER_OS", "RUNNER_ARCH", "RUNNER_ENVIRONMENT",
                       "ICODE_CI_POSITIVE_LOOPBACK_ADMIN", "ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER"}


def require(value, stage):
    if not value:
        raise RuntimeError(stage)


STAGE = re.compile(r"[a-z][a-z0-9_]{0,47}")
EXCEPTION = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,47}")


def bounded_stage(error):
    """Bounded failure category; never a secret, SID, path or command."""
    text = "" if error is None else str(error)
    if text != "unknown" and ("_" not in text or not STAGE.fullmatch(text)):
        return "unknown"
    return text


def child_receipt_stage(raw):
    """Bounded stage/type/winerror from the child's own failure receipt, if any."""
    try:
        value = json.loads(raw)
    except Exception:
        return None
    if type(value) is not dict or value.get("stage") != "failed":
        return None
    code = value.get("error")
    if type(code) is not str:
        return None
    detail = dict(stage=bounded_stage(code))
    kind = value.get("type")
    if type(kind) is str and EXCEPTION.fullmatch(kind):
        detail["kind"] = kind
    winerror = value.get("winerror")
    if type(winerror) is int and 0 < winerror < 65536:
        detail["winerror"] = winerror
    return detail


def bounded_child_type(raw):
    """Bounded exception class of a crashed child from its last stderr line."""
    try:
        lines = [item for item in raw.decode("utf-8", "replace").splitlines() if item.strip()]
        text = lines[-1].split(":", 1)[0].strip()
    except Exception:
        return None
    return text if EXCEPTION.fullmatch(text) else None


def entry_failure(stage, result, raw, stderr):
    """Bounded child failure detail on a nonzero entry exit; never raw output."""
    error = RuntimeError("gate_entry_exit")
    error.add_note("child_exit: %d" % result)
    error.add_note("entry_stage: %s" % stage if stage in ("frozen", "readonly_ready") else "entry_stage: unknown")
    detail = child_receipt_stage(raw)
    if detail is not None:
        error.add_note("child_stage: %s" % detail["stage"])
        if "kind" in detail:
            error.add_note("child_kind: %s" % detail["kind"])
        if "winerror" in detail:
            error.add_note("child_winerror: %d" % detail["winerror"])
        return error
    try:
        stderr.seek(0)
        crash = bounded_child_type(stderr.read(65536))
    except Exception:
        crash = None
    if crash is not None:
        error.add_note("child_type: %s" % crash)
    return error


def failure_receipt(error):
    """Bounded failure wire: this gate's category plus bounded child detail only."""
    value = dict(schema=1, stage="readonly_failed", state="unknown", error=bounded_stage(error))
    for note in getattr(error, "__notes__", ()):
        if note.startswith("child_stage: "):
            value["child"] = bounded_stage(note[len("child_stage: "):])
        elif note.startswith("child_type: "):
            name = note[len("child_type: "):]
            if EXCEPTION.fullmatch(name):
                value["child"] = name
        elif note.startswith("child_kind: "):
            name = note[len("child_kind: "):]
            if EXCEPTION.fullmatch(name):
                value["child_type"] = name
        elif note.startswith("child_winerror: "):
            digits = note[len("child_winerror: "):]
            if digits.isdigit():
                value["child_winerror"] = int(digits)
        elif note.startswith("entry_stage: "):
            name = note[len("entry_stage: "):]
            if name in ("frozen", "readonly_ready"):
                value["entry"] = name
        elif note.startswith("child_exit: "):
            digits = note[len("child_exit: "):]
            if digits.isdigit():
                value["child_exit"] = int(digits)
    return value


def parse_receipt(raw, stage):
    require(type(raw) is bytes and 1 < len(raw) <= 501
            and raw.endswith(b"\n") and raw.count(b"\n") == 1
            and all(value < 128 for value in raw), "gate_receipt_wire")
    value = decode(raw[:-1], 500)
    if stage == "frozen":
        require(type(value) is dict and set(value) == {"schema", "stage", "root"}
                and type(value["schema"]) is int and value["schema"] == 1
                and value["stage"] == stage and type(value["root"]) is str,
                "gate_frozen_schema")
        root = Path(value["root"])
        require(root.is_absolute() and root.resolve(strict=True) == root
                and root.name.startswith("icode-positive-admin-"), "gate_frozen_root")
    else:
        require(stage == "readonly_ready" and wire(value) == wire(READY),
                "gate_ready_schema")
    return value


def validate_readonly_store(store, expected_context, account_name, account_sid, parent_identity):
    data = ledger(store.data, private_root=store.root,
                  system_directory=store.w.system_directory)
    require(data["context"] == expected_context
            and data["account_name"] == account_name and data["account_sid"] == account_sid
            and data["parent"] == parent_identity, "gate_ledger_binding")
    require(data["phase"] == "bound" and data["owned_intent"] is False
            and data["operation_manifest"] is None and data["intent_ms"] is None
            and data["target_attributes"] is None
            and data["consumed"] == {"profile_created": False, "probe_finished": False}
            and data["first_error"] is None and data["cleanup_error"] is None
            and data["readonly_prepare"] is not None
            and not any(data[key] for key in ("add_verified", "delete_verified",
                        "others_preserved", "exact_restoration")), "gate_ledger_readonly")
    commands = data["commands"]
    require(commands and any(item["kind"] == "abi" for item in commands)
            and all(item["kind"] in ("abi", "get") and item["reaped"] is True
                    and item["exit_code"] == 0 and item["timed_out"] is False
                    and item["state"] == "reaped" for item in commands), "gate_commands")
    reads = data["reads"]
    require(len(reads) >= 2 and len(reads) == sum(item["kind"] == "get" for item in commands),
            "gate_reads_complete")
    maps, indexes = [], set()
    reader = [item for item in data["frozen_files"]
              if item["path"] == "trusted/scripts/windows_positive_loopback_full_get.py"]
    require(len(reader) == 1, "gate_reader_binding")
    for item in reads:
        index = item["command_index"]
        require(type(index) is int and 0 <= index < len(commands)
                and index not in indexes and commands[index]["kind"] == "get"
                and item["reader_sha256"] == reader[0]["sha256"], "gate_read_command")
        indexes.add(index)
        raw = decode(store.read(commands[index]["output"], PRIVATE, 1048576), 1048576)
        require(raw["process_reaped"] is None, "gate_worker_self_credit")
        raw["process_reaped"] = True
        require(hashlib.sha256(wire(raw)).hexdigest() == item["raw_sha256"], "gate_read_hash")
        maps.append(_mapping(raw))
    require(all(value == maps[0] for value in maps), "gate_configuration_changed")
    bootstrap = data["bootstrap"]
    cleanup = decode(store.read("cleanup.json", store.file_descriptor("public"), 500), 500)
    expected = dict(schema=1, binding=hashlib.sha256(wire(bootstrap)).hexdigest(),
                    domain="icode_positive_bootstrap_v1", stage="not_owned",
                    delete_verified=None, native_restoration_verified=None)
    require(wire(cleanup) == wire(expected), "gate_cleanup_original")
    return dict(schema=1, stage="readonly_verified", sdk=True, loader=True,
                storage=True, standard_token=True, configuration_unchanged=True)


class USER_INFO_1(c.Structure):
    _fields_ = [("name", t.LPWSTR), ("password", t.LPWSTR),
                ("password_age", t.DWORD), ("privilege", t.DWORD),
                ("home", t.LPWSTR), ("comment", t.LPWSTR),
                ("flags", t.DWORD), ("script", t.LPWSTR)]


class Account:
    def __init__(self, w, native):
        self.w, self.native = w, native
        require(c.sizeof(c.c_void_p) == 8 and c.sizeof(t.DWORD) == 4
                and c.sizeof(USER_INFO_1) == 56
                and [getattr(USER_INFO_1, name).offset for name, _kind in USER_INFO_1._fields_]
                    == [0, 8, 16, 20, 24, 32, 40, 48], "gate_account_layout")
        self.name = "icodeprobe_" + secrets.token_hex(4)
        self.sid, self.owned = None, False
        self.net = c.WinDLL(str(w.system_directory / "netapi32.dll"), use_last_error=True, winmode=0x800)
        self.net.NetUserAdd.restype = t.DWORD
        self.net.NetUserAdd.argtypes = [t.LPCWSTR, t.DWORD, c.c_void_p, c.POINTER(t.DWORD)]
        self.net.NetUserDel.restype = t.DWORD
        self.net.NetUserDel.argtypes = [t.LPCWSTR, t.LPCWSTR]
        self.password = c.create_unicode_buffer(65)
        # No Python str containing the full password, argv, environment or disk
        # credential is made. Mutable random material is overwritten immediately.
        material = bytearray()
        try:
            material.extend(secrets.token_bytes(60))
            alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            for index, byte in enumerate(material):
                self.password[index] = alphabet[byte % len(alphabet)]
            for index, character in enumerate("aA1!", 60):
                self.password[index] = character
        except BaseException:
            c.memset(self.password, 0, c.sizeof(self.password))
            raise
        finally:
            for index in range(len(material)):
                material[index] = 0

    def create(self):
        self.native._account(self.w, self.name, absent=True)
        value = USER_INFO_1(self.name, c.cast(self.password, t.LPWSTR), 0, 1,
                            None, "ICODE CI readonly admission", 0x0001 | 0x0200 | 0x10000, None)
        parameter = t.DWORD()
        result = int(self.net.NetUserAdd(None, 1, c.byref(value), c.byref(parameter)))
        require(result == 0, "gate_account_create")
        self.owned = True
        self.sid = self.native._account(self.w, self.name)
        return self.sid

    def delete(self):
        if not self.owned:
            return
        require(self.sid is not None, "gate_account_identity_unknown")
        current = self.native._account(self.w, self.name, allow_absent=True)
        require(current in (None, self.sid), "gate_account_replaced")
        if current is not None:
            require(int(self.net.NetUserDel(None, self.name)) == 0, "gate_account_delete")
        require(self.native._account(self.w, self.name, allow_absent=True) is None,
                "gate_account_delete_unconfirmed")
        self.owned = False

    def clear_secret(self):
        c.memset(self.password, 0, c.sizeof(self.password))


class SuspendedParent:
    def __init__(self, w, native, checkout, executable):
        self.w, self.native = w, native
        self.checkout, self.executable = checkout, executable
        self.process, self.identity, self.created = PROCESS(), None, False
        function = w.a.CreateProcessWithLogonW
        function.restype = t.BOOL
        function.argtypes = [t.LPCWSTR, t.LPCWSTR, t.LPCWSTR, t.DWORD,
                            t.LPCWSTR, t.LPWSTR, t.DWORD, c.c_void_p,
                            t.LPCWSTR, c.POINTER(STARTUP), c.POINTER(PROCESS)]

    def create(self, account):
        system = self.w.system_directory.parent
        # An explicit environment block, never inherited workflow control files.
        environment = dict(SystemRoot=str(system), SystemDrive=system.drive,
                           TEMP=str(system / "Temp"), TMP=str(system / "Temp"))
        block = c.create_unicode_buffer("\0".join(key + "=" + value
                    for key, value in sorted(environment.items(), key=lambda pair: pair[0].upper())) + "\0\0")
        text = subprocess.list2cmdline([str(self.executable), "-m", "unittest", METHOD, "-v"])
        require("\0" not in text and len(text.encode("utf-16-le")) // 2 + 1 <= 1024,
                "gate_parent_command_limit")
        command = c.create_unicode_buffer(text)
        startup = STARTUP()
        startup.cb = c.sizeof(startup)
        created = self.w.a.CreateProcessWithLogonW(account.name, ".", account.password,
                0, str(self.executable), command, 0x4 | 0x400 | 0x08000000,
                c.cast(block, c.c_void_p), str(self.checkout), c.byref(startup),
                c.byref(self.process))
        if not created:
            # Failed API output is not owned-handle or termination authority.
            # Do not dereference/close/kill a possibly foreign garbage value.
            unknown = any((self.process.process, self.process.thread,
                           self.process.pid, self.process.tid))
            self.process = PROCESS()
            raise RuntimeError("gate_parent_create_unknown_output" if unknown else "gate_parent_create")
        self.created = True
        require(bool(self.process.process) and bool(self.process.thread)
                and self.process.pid > 0 and self.process.tid > 0, "gate_parent_handles")
        require(self.w.k.WaitForSingleObject(self.process.process, 0) == 258
                and self.w.process_user(self.process.process) == account.sid,
                "gate_parent_identity")
        created = self.w.process_created(self.process.process)
        require(type(created) is int and created > 0, "gate_parent_creation")
        self.identity = dict(pid=int(self.process.pid), process_created=created)
        token, duplicate, admin_sid = t.HANDLE(), t.HANDLE(), c.c_void_p()
        try:
            checked(self.w.a.OpenProcessToken(self.process.process, 10, c.byref(token)), "gate_parent_token")
            checked(self.w.a.DuplicateToken(token, 2, c.byref(duplicate)), "gate_parent_duplicate")
            checked(self.w.a.ConvertStringSidToSidW("S-1-5-32-544", c.byref(admin_sid)), "gate_admin_sid")
            member = t.BOOL()
            checked(self.w.a.CheckTokenMembership(duplicate, admin_sid, c.byref(member)), "gate_parent_membership")
            require(not member.value, "gate_parent_is_admin")
        finally:
            _release_owned(sys.exception(),
                lambda: checked(not self.w.k.LocalFree(admin_sid), "gate_admin_sid_free") if admin_sid else None,
                lambda: self.w.close(duplicate), lambda: self.w.close(token))
        return self.identity

    def reap(self):
        if not self.created or not self.process.process:
            return
        state = int(self.w.k.WaitForSingleObject(self.process.process, 0))
        actions = []
        actions.append(lambda: require(state in (0, 258), "gate_parent_wait_unknown"))
        if state == 258:
            actions.append(lambda: checked(self.w.k.TerminateProcess(self.process.process, 1),
                                           "gate_parent_terminate"))
        actions.append(lambda: checked(self.w.k.WaitForSingleObject(self.process.process, 2000) == 0,
                                       "gate_parent_reap"))
        _release_owned(None, *actions)

    def close(self):
        if not self.created:
            return
        _release_owned(None,
            lambda: self.w.close(self.process.thread) if self.process.thread else None,
            lambda: self.w.close(self.process.process) if self.process.process else None)


class Gate:
    def __init__(self):
        require(sys.platform == "win32" and sys.version_info[:2] == (3, 12), "gate_windows312")
        require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
                "gate_python_flags")
        self.w, self.native = Win32(), Native()
        self.w.assert_admin()
        self.checkout = Path(__file__).resolve(strict=True).parents[1]
        require(Path(os.environ.get("GITHUB_WORKSPACE", "")).resolve(strict=True) == self.checkout,
                "gate_checkout")
        self.binding = context(dict(repository=os.environ.get("GITHUB_REPOSITORY"),
            source_sha=os.environ.get("GITHUB_SHA"), run_id=os.environ.get("GITHUB_RUN_ID"),
            run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
            job=os.environ.get("GITHUB_JOB"),
            matrix={"X64": "x64", "ARM64": "ARM64"}.get(os.environ.get("RUNNER_ARCH"))))
        self.parent = SuspendedParent(self.w, self.native, self.checkout, Path(sys.executable).absolute())
        self.account = Account(self.w, self.native)
        self.root = None

    def _entry(self, stage, arguments, timeout):
        executable = Path(sys.executable).absolute() if stage == "frozen" else self.root / "runtime/python.exe"
        entry = self.checkout / "scripts/windows_positive_loopback_admin_entry.py" if stage == "frozen" else self.root / "trusted/scripts/windows_positive_loopback_admin_entry.py"
        # The trusted admin needs original binding fields, not workflow output
        # file capabilities. Its fixed context() independently checks them.
        # Windows normalizes some inherited key spellings (SystemRoot can be
        # read back as SYSTEMROOT); matching is therefore case-insensitive.
        lowered = {key.casefold() for key in ALLOWED_ENVIRONMENT}
        environment = {key: value for key, value in os.environ.items()
                       if key.casefold() in lowered}
        stdout, stderr = None, None
        try:
            # Before freeze the account does not exist. Afterwards inherit the
            # protected root's BA/SY-only file ACL, not user probeRoot storage.
            stdout = tempfile.TemporaryFile(dir=self.root)
            stderr = tempfile.TemporaryFile(dir=self.root)
            process = subprocess.Popen([str(executable), "-I", "-S", "-B", str(entry), *arguments],
                cwd=self.checkout, env=environment, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                result = process.wait(timeout=timeout)
            finally:
                def stop():
                    if process.poll() is None:
                        process.kill()
                # Popen's Windows process handle has no public close method;
                # the fixed host adapter explicitly releases this owned handle
                # after the independent actual wait. No child/client handle is
                # accepted here. Tests exercise Close failure independently.
                _release_owned(sys.exception(), stop, lambda: process.wait(timeout=4),
                    lambda: process._handle.Close())
            stdout.seek(0)
            raw = stdout.read(502)
            if result != 0:
                raise entry_failure(stage, result, raw, stderr)
            stderr.seek(0)
            require(stderr.read(1) == b"", "gate_entry_stderr")
            return parse_receipt(raw, stage)
        finally:
            _release_owned(sys.exception(),
                lambda: stderr.close() if stderr is not None else None,
                lambda: stdout.close() if stdout is not None else None)

    def _probe(self):
        """Distinguish a frozen-runtime socket failure from the filtered env.

        The readonly child runs the frozen interpreter with the filtered
        environment. This probe runs the same frozen interpreter with the full
        environment once; a bounded socket failure category is reported for it
        and the filtered-environment comparison lives in the workflow probe.
        """
        code = ("import socket, time\n"
                "error = None\n"
                "for attempt in range(3):\n"
                "    try:\n"
                "        socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()\n"
                "    except OSError as caught:\n"
                "        error = caught\n"
                "        time.sleep(0.2 * (attempt + 1))\n"
                "if error is not None:\n"
                "    print('probe_full_env_failed', type(error).__name__, getattr(error, 'winerror', None), 3)\n"
                "    raise SystemExit(1)\n"
                "print('probe_full_env_ok')\n")
        stdout, stderr = None, None
        try:
            stdout = tempfile.TemporaryFile(dir=self.root)
            stderr = tempfile.TemporaryFile(dir=self.root)
            process = subprocess.Popen([str(self.root / "runtime/python.exe"), "-I", "-S", "-B",
                                        "-c", code],
                cwd=self.checkout, env=dict(os.environ), stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            result = process.wait(timeout=30)
            stdout.seek(0)
            raw = stdout.read(201)
            if result != 0:
                error = RuntimeError("gate_probe_full_env")
                fields = raw.decode("ascii", "replace").strip().split(" ")
                if len(fields) == 4 and fields[0] == "probe_full_env_failed" \
                        and EXCEPTION.fullmatch(fields[1]) and fields[2].isdigit() \
                        and fields[3].isdigit():
                    error.add_note("child_type: %s" % fields[1])
                    error.add_note("child_winerror: %s" % fields[2])
                raise error
            require(raw == b"probe_full_env_ok\n", "gate_probe_output")
        finally:
            _release_owned(sys.exception(),
                lambda: stderr.close() if stderr is not None else None,
                lambda: stdout.close() if stdout is not None else None)

    def run(self):
        result = None
        try:
            frozen = self._entry("frozen", ["freeze", "--account", self.account.name], 180)
            self.root = Path(frozen["root"])
            self._probe()
            sid = self.account.create()
            identity = self.parent.create(self.account)
            self.account.clear_secret()
            self._entry("readonly_ready", ["readonly", "--root", str(self.root),
                "--account-sid", sid, "--parent", str(identity["pid"])], 180)
            store = self.native.reopen(self.root)
            try:
                result = validate_readonly_store(store, self.binding, self.account.name, sid, identity)
            finally:
                _release_owned(sys.exception(), store.close)
        finally:
            _release_owned(sys.exception(), self.parent.reap, self.parent.close,
                           self.account.delete, self.account.clear_secret)
        return result


def main():
    require(len(sys.argv) == 1, "gate_no_arguments")
    result = Gate().run()
    sys.stdout.buffer.write(wire(result) + b"\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        sys.stdout.buffer.write(wire(failure_receipt(error)) + b"\n")
        sys.stdout.flush()
        raise SystemExit(4)
