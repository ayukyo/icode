# Windows positive admin readonly gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This document is a review candidate, not implementation authorization; separate TEST and SOURCE authors are required.

**Goal:** In the existing dual Windows Reviewer job, prove the actual SDK/Python ABI and protected readonly admission against a never-resumed real standard-user test parent, without adding or deleting an exemption.

**Architecture:** Add one fixed CI orchestrator before the existing Reviewer step. Freeze privileged inputs before creating its dedicated temporary account, retain original suspended process/thread handles, invoke only the frozen readonly entry, and independently verify durable originals after complete process exit. The old Reviewer network/ACL/profile checks remain untouched and may still fail.

**Tech Stack:** Python 3.12, ctypes, Windows SDK/CMake, existing protected Admin/Native/Store, GitHub-hosted x64 and ARM64 runners.

---

## Scope, authority and alternatives

Parent specifications are `docs/nbl/specs/2026-10-15-windows-ci-positive-loopback-exemption-design.md` (SHA256 `62f1ffa91d51ea837371a392f807d7bd325cf64c0e7cb1fc277030413324606c`) and `docs/nbl/specs/2026-10-15-windows-ci-positive-loopback-admin-binding-design.md` (`8d3f0a749962f8f25b6cc3ee1aab42e613f1d7d27d4851613aa345e4e74726ae`). This is main plan Task 3 only, not Task 4. Root accepted approach A: dedicated Python orchestrator in the existing job. PowerShell embedded ctypes/Add-Type duplicates ownership and is not adopted; adding a mode to the old already-resuming runner couples unrelated pipe/network logic and is not adopted.

No native execution, compilation, account creation, actual SOURCE/TEST/CI edits, Git mutation or ICODE-SKILL change is performed by writing this document. Main-only overrides skill worktree defaults. Existing source candidate is `39030d24df39d9bb33dc6f2b5e7957939ac859f1`; workflow source hash is `b4e10208ee1c28ddc45d9bc81365791ec58af5ada34aba220182700fdd01cb18`. Final asset after hashes below bind literal reviewed bytes, not a claim of native success.

Microsoft contracts observed 2026-10-15: [NetUserAdd](https://learn.microsoft.com/en-us/windows/win32/api/lmaccess/nf-lmaccess-netuseradd), [USER_INFO_1](https://learn.microsoft.com/en-us/windows/win32/api/lmaccess/ns-lmaccess-user_info_1), [NetUserDel](https://learn.microsoft.com/en-us/windows/win32/api/lmaccess/nf-lmaccess-netuserdel), [CreateProcessWithLogonW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw). Use local-server NULL, level 1, USER_PRIV_USER and fixed flags. Only NetUserAdd return 0 creates cleanup ownership. A failed call, including user-exists, never authorizes deletion of an observed account. No logon-profile load is requested: this parent never executes, so no user-profile bootstrap process or disk profile is needed here. OS calls themselves are not promised preemptible hard deadlines.

## File responsibility and interface freeze

| File | Change | Responsibility |
| --- | --- | --- |
| `scripts/windows_positive_admin_readonly_gate.py` | New, complete source below | Fixed orchestrator and strict evidence validation; no free command/path CLI |
| `.github/workflows/ci.yml` | Exact insertion below | Existing x64/ARM64 job builds existing ABI target, calls readonly gate, then keeps original steps |
| `tests/test_windows_positive_admin_readonly_gate.py` | Independent TEST author | Real parsers/lifecycle with fake OS boundary, ordering and all-owner fault matrix |
| Existing seven admin modules, SDK C and CMake | Unchanged | Reuse actual readonly, ABI, loading/storage/Job proofs |
| Product AppContainer/Job and vendor pin | Unchanged | No consumer, exemption or platform-readiness opening |

The frozen public test interfaces are `parse_receipt(raw, stage)`, `validate_readonly_store(store, expected_context, account_name, account_sid, parent_identity)`, `Account(w, native)`, `SuspendedParent(w, native, checkout, executable)`, and `Gate.run()`. Constructors inject only owned OS boundaries; no user CLI accepts a command, executable, account SID or root. `main()` accepts no arguments. Tests must call these real implementations; no stand-in gate granting native success.

### Ownership invariant

| Owner | Acquired before/after account | Transfer and release |
| --- | --- | --- |
| Orchestrator Python and imports | Before | Load existing modules and DLL binding objects before account creation; process-lifetime DLL references are not blind-FreeLibrary'd |
| Frozen runtime/scripts/SDK/ledger | Before | `freeze` returns exact root only after full exit0; never scan temp roots or put it under user probeRoot; retain failed evidence |
| Account and secret buffer | After freeze | Own only return-0 NetUserAdd; SID exact recheck before NetUserDel; unknown SID prevents guessed deletion and fails candidate; zero mutable password regardless of body/cleanup failure |
| Standard parent original process/thread | After account | Only successful CreateProcessWithLogonW transfers ownership; failed API nonzero output is unknown, never guessed handles. CREATE_SUSPENDED, never Resume; before handing PID to admin validate held token+creation; owned original finally independently wait/terminate/reap and close both handles |
| Frozen readonly admin process | After parent | Complete wait/exit; on timeout kill exact process and wait; known durable command cleanup checked independently; no first-line success |
| Reopened Store, command/Job evidence | After entry exits | Reopen actual protected root, verify native security/identity and durable exact fields, read original command outputs; independent Store.close |

The selected setup Python and fixed original unittest argv are used for the suspended standard parent, not the admin-only frozen interpreter and not a successful stand-in command. Since its initial thread is never resumed, this proves identity/Job/admission only, not test execution or Task 4 payload.

## Task 1: Independently authored failing tests

**Dependencies:** Approved design and frozen interface above.
**Parallelizable:** No (SOURCE must wait for TEST-only semantic RED and review).

- [ ] Independent TEST author writes the test file first, covering the following exact entry points and assertions. A missing module/import-loader error is recorded separately and does not count as semantic RED.
- [ ] Parser checks: exact frozen/ready schemas; duplicate/unknown keys; bool masquerading as int; extra line; no trailing LF; >501 bytes; Unicode; failed-stage; a correct first line followed by failure cannot pass `Gate._entry`.
- [ ] Account lifecycle: freeze precedes add; return-0 is sole ownership; exists/failure never deletes foreign; fresh SID mismatch refuses delete; zero password on every exit; standard token check fails closed.
- [ ] Parent lifecycle: fixed actual unittest argv and 1024 UTF-16-unit bound including terminator; flags include suspended/Unicode/no-window but no breakaway; no ResumeThread call on success or failure; failed API zero or nonzero undefined output never authorizes handle use/termination/close; token/creation mismatch never transfers identity; successful original owned creation still reaps on later validation failure; failed wait/terminate/first close does not skip independent releases; exited process is not blindly killed.
- [ ] Evidence checks: exact context/account/parent; real ledger validation; bound/no intent/no operation/no consumption; readonly admission object required; first/cleanup error fail; only ABI/Get commands, complete reaped exit0; each read rebinds exact original output and SHA, full maps match; cleanup original is exact not_owned/bootstrap binding; no add/delete invocation.
- [ ] Body plus cleanup failure preserves body and adds cleanup_unknown; body success plus cleanup failure fails; readonly stdout before nonzero exit fails; no inherited GITHUB_ENV/GITHUB_OUTPUT/password; no account/profile/probeRoot cleanup hides unknown command/Job recovery.
- [ ] Run targeted unittest on TEST-only state, retain complete exit code and counters. SOURCE author differs from TEST author; fresh SPEC then different QUALITY before actual SOURCE, then exact targeted GREEN and existing admin/policy regressions. Software fakes do not prove Windows ABI, native ACLs or account/system restoration.

## Task 2: Complete SOURCE candidate

**Dependencies:** Task 1 semantic RED, reviewed TEST-only artifact.
**Parallelizable:** No (single implementation writer).

- [ ] Add exactly `scripts/windows_positive_admin_readonly_gate.py` with this content. It is literal reviewed source, not executed by this DOC.

```python
"""Fixed CI readonly admission; never resumes its standard-user test parent."""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as t
import hashlib
import json
import os
from pathlib import Path
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


def require(value, stage):
    if not value:
        raise RuntimeError(stage)


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
        allowed = {"SystemRoot", "SystemDrive", "TEMP", "TMP", "GITHUB_ACTIONS",
                   "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                   "GITHUB_JOB", "GITHUB_REF", "GITHUB_WORKFLOW_REF", "GITHUB_WORKFLOW_SHA",
                   "GITHUB_WORKSPACE", "RUNNER_OS", "RUNNER_ARCH", "RUNNER_ENVIRONMENT",
                   "ICODE_CI_POSITIVE_LOOPBACK_ADMIN", "ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER"}
        environment = {key: value for key, value in os.environ.items() if key in allowed}
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
            require(result == 0, "gate_entry_exit")
            stdout.seek(0)
            raw = stdout.read(502)
            stderr.seek(0)
            require(stderr.read(1) == b"", "gate_entry_stderr")
            return parse_receipt(raw, stage)
        finally:
            _release_owned(sys.exception(),
                lambda: stderr.close() if stderr is not None else None,
                lambda: stdout.close() if stdout is not None else None)

    def run(self):
        result = None
        try:
            frozen = self._entry("frozen", ["freeze", "--account", self.account.name], 180)
            self.root = Path(frozen["root"])
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
    except Exception:
        sys.stdout.buffer.write(b'{"schema":1,"stage":"readonly_failed","state":"unknown"}\n')
        sys.stdout.buffer.flush()
        raise SystemExit(4)
```

## Task 3: Exact existing-workflow insertion

**Dependencies:** Task 2 targeted software GREEN and independent SOURCE reviews; all preceding candidate workflows terminal before a new push.
**Parallelizable:** x64/ARM64 independently in the existing matrix, not concurrent instances on one runner.

- [ ] Insert the following steps immediately before existing `Build and self-test IPv6 loopback WFP observer` in `windows-reviewer-snapshot-probe`; no other job or line is replaced. Before anchor is exact original `      - name: Build and self-test IPv6 loopback WFP observer`. After anchor retains that same line after this block.

```yaml
      - name: Test positive admin software on native Python 3.12
        shell: pwsh
        run: |
          $ErrorActionPreference = 'Stop'
          python -m unittest tests.test_windows_positive_loopback_admin_binding tests.test_windows_positive_loopback_admin tests.test_windows_positive_loopback_admin_get tests.test_windows_positive_loopback_admin_win32 tests.test_windows_positive_loopback_admin_store tests.test_windows_positive_loopback_admin_jobs tests.test_windows_positive_loopback_admin_native tests.test_windows_positive_loopback_admin_entry tests.test_windows_positive_admin_readonly_gate tests.test_windows_positive_loopback_policy -v
          if ($LASTEXITCODE -ne 0) { throw 'positive_admin_software_failed' }
      - name: Build positive admin readonly SDK oracle
        shell: pwsh
        run: |
          $ErrorActionPreference = 'Stop'
          cmake -S native/windows -B build/positive-admin-abi -A '${{ matrix.cmake-architecture }}' -DICODE_BUILD_WINDOWS_BOOTSTRAP=OFF
          if ($LASTEXITCODE -ne 0) { throw 'positive_admin_abi_configure_failed' }
          cmake --build build/positive-admin-abi --config Release --target icode_positive_loopback_admin_abi --parallel 1
          if ($LASTEXITCODE -ne 0) { throw 'positive_admin_abi_build_failed' }
      - name: Prove positive admin readonly admission without exemption
        shell: pwsh
        env:
          ICODE_CI_POSITIVE_LOOPBACK_ADMIN: '1'
          ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER: '1'
        run: |
          $ErrorActionPreference = 'Stop'
          python -I -S -B scripts/windows_positive_admin_readonly_gate.py
          if ($LASTEXITCODE -ne 0) { throw 'positive_admin_readonly_failed' }
```

The original Reviewer steps, conditions, bodies and errors are retained. A failed readonly prerequisite fails the job and later default-dependent steps are explicitly unobserved/skipped, never passed or claimed repaired. Preserve the historical actual Reviewer failures; this candidate cannot replace them with skip credit. Actual native runs must bind exact candidate SHA, job ID, architecture, full output and final exit; successful C process alone is not SDK/Python comparison. Native._abi compares all 77 layout fields and exercises actual process-times/LocalFree/FreeSid calls. No `GITHUB_JOB` or matrix forging is permitted. No `continue-on-error` is added.

## Task 4: Acceptance and handoff, not consumer activation

**Dependencies:** Same candidate dual Windows Task 3 complete native results.
**Parallelizable:** No (proof must be reconciled before next slice).

- [ ] Run `python -m unittest tests.test_windows_positive_admin_readonly_gate -v` and the existing 152 admin/binding/Store/Win32/Job tests plus 20 policy tests on targeted software scope; keep exact counts, no inferred totals.
- [ ] Verify no actual source change to existing seven modules, C/CMake, product launch guards or vendor pin; `git diff --check`; secret/local-path scan of this batch; main-only review/commit/push per standing authorization.
- [ ] Online x64 and ARM64 both must build SDK target and complete actual readonly gate exit0, protected original ledger/cleanup, no exemption commands and confirmed account/process/handle cleanup. Unknown, timeout, skip or runner disappearance fails this slice.
- [ ] Record that no Resume occurred, no test payload ran and no add/delete happened. Task 4 original consumer remains disabled, old Reviewer timeout remains inconclusive absent its required evidence; no R2/R3 or automatic-mode completion claim.

Exact targeted commands for the future implementing author (not executed by this DOC author):

```bash
python -m unittest tests.test_windows_positive_admin_readonly_gate -v
python -m unittest tests.test_windows_positive_loopback_admin_binding tests.test_windows_positive_loopback_admin tests.test_windows_positive_loopback_admin_get tests.test_windows_positive_loopback_admin_win32 tests.test_windows_positive_loopback_admin_store tests.test_windows_positive_loopback_admin_jobs tests.test_windows_positive_loopback_admin_native tests.test_windows_positive_loopback_admin_entry tests.test_windows_positive_loopback_policy -v
git diff --check
```

Expected first TEST-only observation is a specifically documented absent-component boundary until real parsers/lifecycle become importable; this is not semantic RED. Independent TEST author must select behavioral tests that run against the candidate in RAM for review, then actual implementation TDD must retain the proper actual TEST-only failure separately. Expected post-implementation command exits are zero with zero failure/error/skip for this new software scope. Existing 152 and 20 counters are historical references, not newly observed values. Full online workflow remains the authority for native/Python 3.12 proof.

### Frozen asset manifest

The Python fence is the exact complete new file (LF, final newline). The YAML fence is the exact insertion, not an entire replacement workflow. Applying it once to the sole anchor in the observed current workflow produces the after hash below; any drift blocks mechanical application and requires a fresh review.

| Asset | Before SHA256 | Reviewed after SHA256 | Bytes / lines |
| --- | --- | --- | --- |
| `scripts/windows_positive_admin_readonly_gate.py` | absent | `b53bff1d7991693dabb3cc6b23dc0014c0af5d5dcbf2fcc5c17eebab631187ce` | 18383 / 350 |
| YAML insertion literal | absent | `2b3ff952377fb8bfcae05dfef95afa61606689e2ddb96d64f38132e271204d35` | 1703 / 23 |
| `.github/workflows/ci.yml` | `b4e10208ee1c28ddc45d9bc81365791ec58af5ada34aba220182700fdd01cb18` | `d48966cac7c5cb40e219e458dd981ebe0902e030d6552b53ee5db5f385b2da8c` | 138621 / 2564 |

Existing entry raw SHA `667cde741a5e135121b5894b598c4d55c6ecbb7d5da9365f6d1cb8141443bf7e` and Native raw SHA `d4761232e46876996d077bcab796e96935bcb40395618c19bb171c9e30e81012` remain unchanged. SDK oracle continues its original 77-field comparison; the new USER_INFO_1 uses the official fixed Win64 layout with explicit runtime size/offset checks, not an assertion that those added account calls were independently exercised by the old C oracle.

### Time-budget and failure accounting

Freeze entry: 180-second caller wait, then exact process kill if live and independent 4-second wait. Readonly entry: independent at-most-180-second caller wait; existing native preparation retains its own original deadline rather than extending it. ABI/Get command bodies still use existing 5-second work plus original bounded reap, and operation/cleanup domains remain original 60/30 seconds, unused as authorization for this readonly run. Original held standard parent gets 2-second actual reap after conditional termination; no Resume/Assign-failure fallback. NetUser calls and OS file I/O are not claimed hard-preemptible. Job total remains 25 minutes, CMake uses parallel 1.

If the readonly admin must be killed, no ready credit is granted; its process exit closes its private command Job handles, but that fact alone is not a confirmed command-process recovery receipt. Preserve the root and classify missing durable/native recovery evidence as unknown. Original held standard parent/account/secret/handle cleanup is still independently attempted; account deletion never supplies command/Job recovery proof. A runner lost before finally similarly remains failed/unknown, not an inferred restoration success.

## Candidate self-review and evidence limits

This candidate is intentionally not marked complete. Static observation `24ee65` parsed the one Python fence with AST, derived all asset hashes, checked that the SOURCE target remains absent and `git diff --check` exits zero. PyYAML is absent in the existing diagnostic environment, so YAML semantic parse is explicitly unobserved and no dependency was installed. One earlier diagnostic command used an incorrectly quoted fence regex and was not accepted as AST evidence; `27dc90` and `24ee65` correctly used a literal stdin script. The full source must receive independent review of its actual ownership, pre-account loading boundary, subprocess supervision, ledger-output completeness and native API contracts before any execution. No local native proof was performed. Readonly native failure must be diagnosed from original CI logs, not replaced with a fake adapter, weaker ACL, owner allowlist, environment spoof or alternate success path.

【架构级自检报告】
语法/编译：DOC 候选待静态与独立审查，无 Windows 编译结果。依赖/调用链：限定现有 job/SDK/Admin/Native/Store，未接 Task 4。逻辑/边界：已显式区分 never-resumed parent 与实际测试执行。异常处理：列明原始句柄、账号、凭据、Store 与首错义务，待逐项审查。关联模块：现生产源码未修改。兼容安全：Reviewer、产品 guard、vendor pin 不变。可运行性：未运行，不报告 100%。

---
**Execution Mode:** serial

DOC-only delegation overrides automatic execution. Root must obtain independent TEST/SPEC/QUALITY gates before dispatching actual implementation.
