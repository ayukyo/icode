"""B2 actual FD/software ownership; no native manager or installed credit."""
from __future__ import annotations
from contextlib import ExitStack, contextmanager
import errno
import inspect
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading
import time
import unittest
from unittest.mock import patch
from tests._support import temp_workspace

LINUX = sys.platform.startswith("linux")
if LINUX:
    from icode import linux_task_scope as subject
    from icode import linux_prepared_step as prepared
    from icode import execution_broker as broker
    from tests import test_linux_prepared_broker as previous
    from tests import test_linux_prepared_step as fixture
    from tests import test_linux_helper_dispatch as dispatch

REAL_OPEN, REAL_CLOSE, REAL_FSTAT = os.open, os.close, os.fstat
BASE_SOCKET = socket.socket
BASE_DETACH, BASE_CLOSE = BASE_SOCKET.detach, BASE_SOCKET.close


def capture(operation):
    try:
        return operation(), None
    except BaseException as error:
        return None, error


def release_live(descriptors):
    # Only test-owned, known-live before-close faults; never production credit.
    for descriptor in set(descriptors):
        try:
            REAL_FSTAT(descriptor)
        except OSError:
            continue
        REAL_CLOSE(descriptor)


@unittest.skipUnless(LINUX, "Linux actual FD software; skip is not acceptance")
class TemporaryScopeTests(unittest.TestCase):
    @contextmanager
    def tree(self, kind=None, failure=None, reuse=False):
        with temp_workspace() as root:
            group = root / "group"
            group.mkdir(mode=0o700)
            (group / "supervisor").mkdir(mode=0o700)
            (group / "payload").mkdir(mode=0o700)
            pid = os.getpid()
            for parent, name, data in (
                (group, "cgroup.procs", ""),
                (group / "supervisor", "cgroup.procs", str(pid)),
                (group / "payload", "cgroup.procs", ""),
                (group / "payload", "pids.current", "0"),
                (group / "payload", "pids.max", "16"),
            ):
                (parent / name).write_text(data, encoding="ascii")
            task = object.__new__(subject.LinuxTaskScope)
            task.uid, task.limit, task._pid = os.getuid(), 16, pid
            task.unit = "icode-task-" + "a" * 32 + ".scope"
            task.version = 249
            task.environment = dict(dispatch.Scope.environment)
            task._fds, task._identities = [], []
            task._cleanup_unknown = False
            task._path, task._invocation, task._owned = None, None, False
            task._lifecycle, task._close_requested = threading.Lock(), threading.Event()
            task._membership = lambda: "/group/supervisor"
            task._show = lambda deadline: dict(LoadState="loaded", ActiveState="active",
                Transient="yes", InvocationID="b" * 32, ControlGroup="/group")
            trace = dict(opened=[], attempts=[], watched=None, foreign=None, roots=0,
                         read_names=[], fault_hits=0, watched_before=0)
            def opening(path, flags, *args, **kwargs):
                actual = root if path == "/" else path
                descriptor = REAL_OPEN(actual, flags, *args, **kwargs)
                trace["opened"].append(descriptor)
                if path == "/":
                    trace["roots"] += 1
                    selected = ((kind == "initialwalk" and trace["roots"] == 1)
                        or (kind == "revalidationwalk" and trace["roots"] == 4)
                        or kind == "collectwalk")
                    if selected and trace["watched"] is None:
                        trace["watched"] = descriptor
                        trace["watched_before"] = trace["attempts"].count(descriptor)
                elif stat.S_ISREG(REAL_FSTAT(descriptor).st_mode):
                    trace["read_names"].append(str(path))
                    if (kind in ("read", "read2", "read3", "read4", "read5")
                            and len(trace["read_names"]) == (1 if kind == "read" else int(kind[-1]))
                            and trace["watched"] is None):
                        trace["watched"] = descriptor
                        trace["watched_before"] = trace["attempts"].count(descriptor)
                return descriptor
            def closing(descriptor):
                trace["attempts"].append(descriptor)
                if descriptor == trace["watched"] and trace["fault_hits"] == 0:
                    trace["fault_hits"] += 1
                    if reuse:
                        REAL_CLOSE(descriptor)
                        foreign = REAL_OPEN("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                        if foreign != descriptor:
                            os.dup2(foreign, descriptor)
                            REAL_CLOSE(foreign)
                        trace["foreign"] = descriptor
                    raise failure
                REAL_CLOSE(descriptor)
            trace["opening"], trace["closing"] = opening, closing
            try:
                with patch.object(subject, "_CGROUP", Path("/")), \
                     patch.object(subject.os, "open", side_effect=opening), \
                     patch.object(subject.os, "close", side_effect=closing):
                    yield task, trace
            finally:
                # Release the actual pins before taking test-owned residuals.
                with patch.object(subject.os, "close", side_effect=REAL_CLOSE):
                    task.close()
                release_live(trace["opened"])

    def test_configure_read_initial_walk_and_revalidation_unknown_targets(self):
        for kind in ("read", "read2", "read3", "read4", "read5", "initialwalk", "revalidationwalk"):
            with self.subTest(kind=kind), self.tree(kind, OSError(errno.EIO, "before close")) as (task, trace):
                _, error = capture(lambda: task.configured(time.monotonic() + 1))
                self.assertIsInstance(error, OSError)
                descriptor = trace["watched"]
                self.assertIsNotNone(descriptor)
                self.assertTrue(REAL_FSTAT(descriptor))
                self.assertEqual(trace["fault_hits"], 1)
                self.assertEqual(trace["attempts"].count(descriptor) - trace["watched_before"], 1)
                self.assertEqual(task._fds, [])
                self.assertFalse(task._lifecycle.locked())
                for other in set(trace["opened"]) - {descriptor}:
                    with self.assertRaises(OSError):
                        REAL_FSTAT(other)
                self.assertEqual(task.cleanup_state, "unknown")
                task.close()
                self.assertTrue(REAL_FSTAT(descriptor))
                self.assertEqual(task.cleanup_state, "unknown")

    def test_collected_walk_unknown_target_and_lock_release(self):
        with self.tree("collectwalk", OSError(errno.EIO, "before close")) as (task, trace):
            task._owned, task._path, task._invocation = True, Path("/group"), "b" * 32
            self.assertIsNone(task.collected(time.monotonic() + 1))
            self.assertTrue(REAL_FSTAT(trace["watched"]))
            self.assertEqual(trace["fault_hits"], 1)
            self.assertEqual(trace["attempts"].count(trace["watched"]) - trace["watched_before"], 1)
            self.assertFalse(task._lifecycle.locked())
            self.assertEqual(task.cleanup_state, "unknown")

    def test_after_close_reuse_is_not_retried_and_remains_unknown_target(self):
        with self.tree("read", OSError(errno.EIO, "after close"), reuse=True) as (task, trace):
            _, error = capture(lambda: task.configured(time.monotonic() + 1))
            self.assertIsInstance(error, OSError)
            self.assertTrue(stat.S_ISCHR(REAL_FSTAT(trace["foreign"]).st_mode))
            self.assertEqual(trace["attempts"].count(trace["watched"]) - trace["watched_before"], 1)
            task.close()
            self.assertTrue(REAL_FSTAT(trace["foreign"]))
            self.assertEqual(task.cleanup_state, "unknown")

    def test_success_configure_all_reads_revalidation_and_default_none_helpers(self):
        with self.tree() as (task, trace):
            task.configured(time.monotonic() + 1)
            self.assertTrue(task._owned)
            self.assertEqual(trace["roots"], 6)
            self.assertEqual(trace["read_names"], ["cgroup.procs", "cgroup.procs",
                "cgroup.procs", "pids.current", "pids.max"])
            descriptor = subject._open_directory(Path("/group/payload"), uid=task.uid)
            try:
                self.assertEqual(subject._read_at(descriptor, "pids.max"), b"16")
                with self.assertRaises(subject.LinuxTaskScopeError):
                    subject._read_at(descriptor, "pids.max", limit=0)
            finally:
                REAL_CLOSE(descriptor)
            task.close()
            self.assertEqual(task.cleanup_state, "confirmed")

    def test_collected_real_missing_directory_success(self):
        with self.tree() as (task, trace):
            task._owned, task._path = True, Path("/absent")
            task._show = lambda deadline: dict(LoadState="not-found", ControlGroup="")
            self.assertIs(task.collected(time.monotonic() + 1), True)
            self.assertFalse(task._lifecycle.locked())
            self.assertEqual(task.cleanup_state, "confirmed")

    def test_read_first_signal_identity_target_and_cleanup_signal_control(self):
        for body in (KeyboardInterrupt(), SystemExit(81), RuntimeError("body")):
            for cleanup in (OSError(errno.EIO, "close"), KeyboardInterrupt(), SystemExit(82)):
                with self.subTest(body=type(body).__name__, cleanup=type(cleanup).__name__), temp_workspace() as root:
                    (root / "data").write_bytes(b"data")
                    directory = REAL_OPEN(root, os.O_RDONLY | os.O_DIRECTORY)
                    opened, attempts = [], []
                    def opening(*args, **kwargs):
                        fd = REAL_OPEN(*args, **kwargs)
                        opened.append(fd)
                        return fd
                    def closing(fd):
                        attempts.append(fd)
                        REAL_CLOSE(fd)
                        raise cleanup
                    try:
                        with patch.object(subject.os, "open", side_effect=opening), \
                             patch.object(subject.os, "read", side_effect=body), \
                             patch.object(subject.os, "close", side_effect=closing):
                            _, error = capture(lambda: subject._read_at(directory, "data"))
                        expected = body if not isinstance(body, Exception) or isinstance(cleanup, Exception) else cleanup
                        self.assertEqual(attempts, opened)
                        for fd in opened:
                            with self.assertRaises(OSError):
                                REAL_FSTAT(fd)
                        self.assertIs(error, expected)
                    finally:
                        REAL_CLOSE(directory)


@unittest.skipUnless(LINUX, "Linux constructor actual directory/socket FD")
class RuntimeProbeTests(unittest.TestCase):
    @contextmanager
    def construction(self, body=None, probe_error=None, parent_error=None,
                     detached_error=None, unavailable=False, reuse=False):
        with temp_workspace() as root:
            parent = REAL_OPEN(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            original = REAL_FSTAT(parent)
            uid = 1001
            status = type("Status", (), dict(st_uid=uid, st_mode=stat.S_IFDIR | 0o700))()
            bus = type("Bus", (), dict(st_uid=uid, st_mode=stat.S_IFSOCK | 0o600))()
            trace = dict(parent=[], probe=[], detach=[], foreign=None, queries=[])
            class Probe(BASE_SOCKET):
                def settimeout(self, seconds):
                    trace["timeout"] = seconds
                def connect(self, path):
                    trace["connect"] = path
                    if body is not None:
                        raise body
                def getsockopt(self, *args):
                    return struct.pack("3i", os.getpid(), uid, os.getgid())
                def close(self):
                    trace["probe"].append(self.fileno())
                    if probe_error is not None:
                        if reuse:
                            fd = self.fileno()
                            BASE_CLOSE(self)
                            foreign = REAL_OPEN("/dev/null", os.O_RDONLY)
                            if foreign != fd:
                                os.dup2(foreign, fd)
                                REAL_CLOSE(foreign)
                            trace["foreign"] = fd
                        raise probe_error
                    BASE_CLOSE(self)
                def detach(self):
                    raise AssertionError("must not use overridden detach")
            probe = Probe(socket.AF_UNIX, socket.SOCK_STREAM)
            probe_fd = probe.fileno()
            def factory(*args):
                if unavailable:
                    raise body
                return probe
            def detach(endpoint):
                trace["detach"].append(endpoint)
                if detached_error is not None:
                    raise detached_error
                return BASE_DETACH(endpoint)
            class SocketShim:
                pass
            SocketShim.detach = staticmethod(detach)
            SocketShim.__new__ = staticmethod(lambda cls, *args: factory(*args))
            def closing(fd):
                trace["parent"].append(fd)
                if parent_error is not None:
                    raise parent_error
                REAL_CLOSE(fd)
            def fstat(fd):
                return status if fd == parent else REAL_FSTAT(fd)
            def query(argv, environment, deadline):
                trace["queries"].append((argv, environment, deadline))
                return b"systemd 249\n"
            try:
                with ExitStack() as stack:
                    stack.enter_context(patch.object(subject.os, "getuid", return_value=uid))
                    stack.enter_context(patch.object(subject, "_trusted_tool"))
                    stack.enter_context(patch.object(subject, "_open_directory", return_value=parent))
                    stack.enter_context(patch.object(subject.os, "fstat", side_effect=fstat))
                    stack.enter_context(patch.object(subject.os, "stat", return_value=bus))
                    stack.enter_context(patch.object(subject.os, "close", side_effect=closing))
                    stack.enter_context(patch.object(subject.socket, "socket", SocketShim))
                    value, error = capture(lambda: subject.LinuxTaskScope(limit=16, query=query))
                yield value, error, probe, probe_fd, parent, trace
            finally:
                # Base detach prevents fixture finalization from retrying any reused number.
                BASE_DETACH(probe)
                release_live([parent, probe_fd, trace["foreign"]] if trace["foreign"] is not None
                             else [parent, probe_fd])

    def test_runtime_body_first_signal_probe_and_parent_failures_target(self):
        for first in (KeyboardInterrupt(), SystemExit(83)):
            with self.subTest(first=type(first).__name__), self.construction(
                    first, RuntimeError("probe close"), RuntimeError("parent close")) as (value, error, probe, probe_fd, parent, trace):
                self.assertTrue(REAL_FSTAT(probe_fd))
                self.assertTrue(REAL_FSTAT(parent))
                self.assertEqual(trace["probe"], [probe_fd])
                self.assertEqual(trace["parent"], [parent])
                self.assertIs(error, first)
                self.assertEqual(probe.fileno(), -1)

    def test_unavailable_probe_still_closes_parent_and_preserves_first_signal_target(self):
        for first in (KeyboardInterrupt(), SystemExit(84)):
            with self.subTest(first=type(first).__name__), self.construction(
                    first, parent_error=RuntimeError("parent close"), unavailable=True) as (value, error, probe, probe_fd, parent, trace):
                self.assertEqual(trace["probe"], [])
                self.assertEqual(trace["parent"], [parent])
                self.assertTrue(REAL_FSTAT(parent))
                self.assertIs(error, first)

    def test_detach_fault_keeps_first_signal_and_still_drains_parent(self):
        first = KeyboardInterrupt()
        with self.construction(first, RuntimeError("probe close"), None,
                SystemExit(85)) as (value, error, probe, probe_fd, parent, trace):
            self.assertIs(error, first)
            self.assertEqual(trace["detach"], [probe])
            self.assertEqual(trace["parent"], [parent])
            with self.assertRaises(OSError):
                REAL_FSTAT(parent)
            self.assertTrue(REAL_FSTAT(probe_fd))

    def test_probe_after_close_reuse_survives_parent_drain(self):
        first = RuntimeError("probe close")
        with self.construction(probe_error=first, reuse=True) as (value, error, probe, probe_fd, parent, trace):
            self.assertIs(error, first)
            self.assertEqual(trace["probe"], [probe_fd])
            self.assertEqual(probe.fileno(), -1)
            self.assertTrue(stat.S_ISCHR(REAL_FSTAT(trace["foreign"]).st_mode))
            self.assertEqual(trace["parent"], [parent])

    def test_runtime_ordinary_body_cleanup_signal_priority_and_remaining_parent(self):
        body = RuntimeError("connect")
        for cleanup in (OSError(errno.EIO, "probe close"), KeyboardInterrupt(), SystemExit(86)):
            with self.subTest(cleanup=type(cleanup).__name__), self.construction(
                    body, cleanup, RuntimeError("parent close")) as (value, error, probe, probe_fd, parent, trace):
                self.assertEqual(trace["probe"], [probe_fd])
                self.assertEqual(trace["parent"], [parent])
                self.assertEqual(probe.fileno(), -1)
                self.assertTrue(REAL_FSTAT(probe_fd))
                self.assertTrue(REAL_FSTAT(parent))
                self.assertIs(error, body if isinstance(cleanup, Exception) else cleanup)

    def test_success_constructor_contract(self):
        with self.construction() as (value, error, probe, probe_fd, parent, trace):
            self.assertIsNone(error)
            self.assertEqual(value.version, 249)
            self.assertEqual(trace["timeout"], subject._BUS_CONNECT_TIMEOUT_SECONDS)
            self.assertEqual(trace["connect"], "/run/user/1001/bus")
            self.assertEqual(trace["probe"], [probe_fd])
            self.assertEqual(trace["parent"], [parent])
            self.assertEqual(len(trace["queries"]), 1)
            self.assertEqual(value.cleanup_state, "confirmed")


@unittest.skipUnless(LINUX, "Linux prepared borrow with actual scope state")
class BrokerScopeTests(unittest.TestCase):
    if LINUX:
        setUp = fixture.PreparedTests.setUp
        write_image = fixture.PreparedTests.write_image
        precheck_fixture = fixture.PreparedTests.precheck_fixture
        cleanup_scopes = fixture.PreparedTests.cleanup_scopes
        prepare = fixture.PreparedTests.prepare
        attach = fixture.PreparedTests.attach
        bind = fixture.PreparedTests.bind
        borrow = fixture.PreparedTests.borrow
        call = previous.PreparedBrokerTests.call
        entry = previous.PreparedBrokerTests.entry
        wrapper = previous.PreparedBrokerTests.wrapper

    def test_actual_returned_scope_unknown_faults_attachment_before_next_borrow(self):
        for kind in ("read", "initialwalk"):
            with self.subTest(kind=kind):
                owner = self.prepare()
                view = self.bind(self.attach(owner))
                self.owners = []
                helper = TemporaryScopeTests()
                with helper.tree(kind, OSError(errno.EIO, "before close")) as (task, trace):
                    task.limit = self.policy.process_limit
                    # Real returned scope, real configured and close methods.
                    # Manager/payload/receiver are software seams, not native proof.
                    task.collected = lambda deadline: True
                    def run(argv, **kwargs):
                        kwargs["before_spawn"]()
                        with patch.object(subject.os, "open", side_effect=trace["opening"]), \
                             patch.object(subject.os, "close", side_effect=trace["closing"]):
                            _, configured_error = capture(lambda: task.configured(time.monotonic() + 1))
                        self.assertIsInstance(configured_error, OSError)
                        return broker.ExecutionResult(0, "", 0, None, False, True, None)
                    with patch.object(subject.os, "open", side_effect=REAL_OPEN), \
                         patch.object(subject.os, "close", side_effect=REAL_CLOSE), \
                         patch.object(subject, "LinuxTaskScope", return_value=task), \
                         patch("icode.linux_task_resource.LinuxTaskResourceReceiver", return_value=dispatch.Resource()), \
                         patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor", side_effect=dispatch.Monitor), \
                         patch.object(broker, "_execute_policy_command", side_effect=run):
                        _, error = capture(lambda: self.call(True, view))
                    self.assertTrue(REAL_FSTAT(trace["watched"]))
                    self.assertEqual(trace["attempts"].count(trace["watched"]) - trace["watched_before"], 1)
                    self.assertFalse(task._lifecycle.locked())
                    self.assertFalse(owner._inflight)
                    self.assertEqual(owner._owner_state, "active")
                    REAL_FSTAT(owner._owner.fileno())
                    REAL_FSTAT(self.session.workspace_fd)
                    self.assertEqual(owner._consume_state, "faulted")
                    self.assertEqual(task.cleanup_state, "unknown")
                    self.assertIsInstance(error, RuntimeError)
                    with self.assertRaises(prepared.LinuxPreparedStepError):
                        with self.borrow(view):
                            self.fail("faulted borrow re-entered")


if __name__ == "__main__":
    unittest.main()
