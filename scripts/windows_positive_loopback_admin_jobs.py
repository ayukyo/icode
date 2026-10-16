from __future__ import annotations

import ctypes as c
from ctypes import wintypes as t
from pathlib import Path
import subprocess
import time
import sys

from scripts.windows_positive_loopback_admin_store import PRIVATE, KERNEL_PRIVATE
from scripts.windows_positive_loopback_admin_win32 import (
    SA, STARTUP_EX, PROCESS, EXTENDED_LIMITS, Failure, checked, _release_owned,
)


def create_job(store, name):
    w = store.w
    descriptor = w.descriptor(KERNEL_PRIVATE)
    job = None
    transferred = False
    try:
        security = SA(c.sizeof(SA), descriptor, False)
        c.set_last_error(0)
        job = w.k.CreateJobObjectW(c.byref(security), name)
        checked(job, "job_create")
        if c.get_last_error() == 183:
            raise Failure("job_collision")
        limits = EXTENDED_LIMITS()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway flags.
        checked(w.k.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)), "job_limits")
        # Kernel objects ignore the owner carried by the creation descriptor:
        # the system assigns the token's default owner instead. Taking ownership
        # still requires WRITE_OWNER, and the private DACL grants it only to
        # Administrators and SYSTEM, so the owner is not asserted here.
        w.verify_security(job, KERNEL_PRIVATE, object_type=6, owner=False,
                          category="job_security_changed")
        allocation, descriptor = descriptor, None
        _release_owned(None, lambda: checked(not w.k.LocalFree(allocation), "free_descriptor"))
        transferred = True
        return job
    finally:
        _release_owned(sys.exception(),
            lambda: checked(not w.k.LocalFree(descriptor), "free_descriptor") if descriptor is not None else None,
            lambda: w.close(job) if job and not transferred else None,
        )


def wait_empty(store, job, milliseconds):
    deadline = time.monotonic() + milliseconds / 1000
    while True:
        if store.w.job_pids(job) == ():
            return
        if time.monotonic() >= deadline:
            raise Failure("job_not_empty")
        time.sleep(0.01)


def _argv(store, kind):
    root, data = store.root, store.data
    python = root / "runtime" / "python.exe"
    if kind == "get":
        return [str(python), "-I", "-S", "-B",
                str(root / "trusted" / "scripts" / "windows_positive_loopback_full_get.py"),
                "--full-get"]
    if kind == "abi":
        return [str(root / "icode-positive-loopback-admin-abi.exe")]
    if kind not in ("add", "delete"):
        raise Failure("command_kind")
    sid = data["bootstrap"]["positive_sid"]
    if sid == data["bootstrap"]["reviewer_sid"] or not sid.startswith("S-1-15-2-"):
        raise Failure("command_sid")
    if not data["owned_intent"] or data["operation_manifest"] is None:
        raise Failure("command_intent")
    if kind == "add":
        if data["phase"] != "add_intent" or any(item["kind"] == "add" for item in data["commands"]):
            raise Failure("command_replay")
        if int(time.monotonic() * 1000) >= data["operation_manifest"]["deadline_ms"]:
            raise Failure("command_deadline")
    elif data["phase"] != "cleanup_intent":
        raise Failure("command_phase")
    return [data["system_tool"]["path"], "LoopbackExempt",
            "-a" if kind == "add" else "-d", "-p=" + sid]


def run_fixed(store, kind, *, budget_ms=5000):
    if type(budget_ms) is not int or not 0 < budget_ms <= 5000:
        raise Failure("command_budget")
    work_deadline = time.monotonic() + budget_ms / 1000
    argv = _argv(store, kind)
    if len(store.data["commands"]) >= 32:
        raise Failure("command_count")
    number = len(store.data["commands"])
    output = "command-" + str(number) + ".out"
    name = "Local\\ICODE.Positive." + store.data["session"] + ".command." + str(number)
    record = dict(kind=kind, job=name, output=output, state="allocated", pid=None,
                  process_created=None, resume_permitted=False, resume_attempted=False,
                  resume_returned=None, exit_code=None, timed_out=False, reaped=False)
    store.write(output, b"", create=True)
    store.data["commands"].append(record)
    store.flush()
    w = store.w
    job = thread = process_handle = out = null = None
    attribute_list = None
    attributes_initialized = False
    successful_return = False
    try:
        job = create_job(store, name)
        out, _ = w.open_file(store.root / output, PRIVATE, write=True, inherit=True)
        security = SA(c.sizeof(SA), None, True)
        null = w.k.CreateFileW("\\\\.\\NUL", 0x80000000, 3, c.byref(security), 3, 0, None)
        if null in (None, c.c_void_p(-1).value):
            raise Failure("null_handle")
        size = c.c_size_t()
        w.k.InitializeProcThreadAttributeList(None, 2, 0, c.byref(size))
        if not 1 <= size.value <= 1048576:
            raise Failure("attribute_size")
        # c_size_t array supplies pointer alignment on x64 and ARM64.
        storage = (c.c_size_t * ((size.value + c.sizeof(c.c_size_t) - 1) // c.sizeof(c.c_size_t)))()
        attribute_list = c.cast(storage, c.c_void_p)
        checked(w.k.InitializeProcThreadAttributeList(attribute_list, 2, 0, c.byref(size)), "attribute_init")
        attributes_initialized = True
        jobs, handles = (t.HANDLE * 1)(job), (t.HANDLE * 2)(out, null)
        checked(w.k.UpdateProcThreadAttribute(attribute_list, 0, 0x0002000D,
            c.cast(jobs, c.c_void_p), c.sizeof(jobs), None, None), "job_attribute")
        checked(w.k.UpdateProcThreadAttribute(attribute_list, 0, 0x00020002,
            c.cast(handles, c.c_void_p), c.sizeof(handles), None, None), "handle_attribute")
        startup, process = STARTUP_EX(), PROCESS()
        startup.startup.cb = c.sizeof(startup)
        startup.startup.flags = 0x100
        startup.startup.stdin = null
        startup.startup.stdout = out
        startup.startup.stderr = out
        startup.attributes = attribute_list
        command = c.create_unicode_buffer(subprocess.list2cmdline(argv))
        # Environment contains only trusted Windows/frozen runtime locations;
        # no PATH, Python, GITHUB_ENV/OUTPUT or user-controlled loading hints.
        windows = str(w.system_directory.parent)
        environment = c.create_unicode_buffer(
            "SystemRoot=" + windows + "\0TEMP=" + str(store.root)
            + "\0TMP=" + str(store.root) + "\0\0")
        checked(w.k.CreateProcessW(argv[0], command, None, None, True,
            0x00000004 | 0x00000400 | 0x00080000 | 0x08000000,
            environment, str(store.root / "runtime"), c.byref(startup), c.byref(process)), "command_create")
        process_handle, thread = process.process, process.thread
        if not process.pid or set(w.job_pids(job)) != {int(process.pid)}:
            raise Failure("command_job_admission")
        creation = w.process_created(process_handle)
        if not creation:
            raise Failure("command_identity")
        record.update(state="ready", pid=int(process.pid), process_created=creation,
                      resume_permitted=True, resume_attempted=None)
        # The only path to Resume comes after this actual FlushFileBuffers.
        store.flush()
        if time.monotonic() >= work_deadline:
            raise Failure("command_work_deadline")
        if kind == "add" and int(time.monotonic() * 1000) >= store.data["operation_manifest"]["deadline_ms"]:
            raise Failure("command_deadline")
        record["resume_attempted"] = True
        previous = int(w.k.ResumeThread(thread))
        record["resume_returned"] = previous
        if previous != 1:
            raise Failure("command_resume")
        remaining = max(0, min(budget_ms, int((work_deadline - time.monotonic()) * 1000)))
        waited = int(w.k.WaitForSingleObject(process_handle, remaining))
        record["timed_out"] = waited == 258
        if waited not in (0, 258):
            raise Failure("command_wait")
        if waited == 258 or w.job_pids(job):
            _release_owned(None,
                lambda: checked(w.k.TerminateJobObject(job, 1), "command_terminate"),
                lambda: checked(w.k.WaitForSingleObject(process_handle, 2000) == 0, "command_reap"),
                lambda: wait_empty(store, job, 2000),
            )
        else:
            wait_empty(store, job, 2000)
        code = t.DWORD()
        checked(w.k.GetExitCodeProcess(process_handle, c.byref(code)), "command_exit")
        record.update(exit_code=int(code.value), reaped=True, state="reaped")
        store.flush()
        successful_return = True
        return dict(record)
    finally:
        primary = sys.exception()
        errors = []
        if process_handle and not record["reaped"]:
            try:
                _release_owned(None,
                    lambda: checked(w.k.TerminateJobObject(job, 1), "command_terminate") if job
                            else checked(w.k.TerminateProcess(process_handle, 1), "command_terminate"),
                    lambda: checked(w.k.WaitForSingleObject(process_handle, 2000) == 0, "command_reap"),
                    lambda: wait_empty(store, job, 2000) if job else None,
                )
                record.update(reaped=True, state="reaped_after_failure")
            except BaseException as error:
                errors.append(error)
        if attributes_initialized:
            try:
                w.k.DeleteProcThreadAttributeList(attribute_list)
            except BaseException as error:
                errors.append(error)
        for handle in (thread, process_handle, null, out, job):
            if handle:
                try:
                    w.close(handle)
                except BaseException as error:
                    errors.append(error)
        if not successful_return:
            if record["resume_attempted"] is None:
                # This live instance knows it never reached Resume. A crash
                # leaves durable ready/attempted=None, not this in-memory fact.
                record["resume_attempted"] = False
            try:
                store.flush()
            except BaseException as error:
                errors.append(error)
        if errors:
            record["reaped"] = False
            record["state"] = "cleanup_unknown"
            try:
                store.flush()
            except BaseException as error:
                errors.append(error)
            failure = primary if primary is not None else errors[0]
            for error in errors:
                failure.add_note(f"cleanup_unknown: {error!r}")
            if primary is None:
                raise failure
