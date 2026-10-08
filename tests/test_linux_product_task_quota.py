"""Actual Linux registry task quotas; no overall conformance credit."""
from __future__ import annotations

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import functools
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import textwrap
import unittest
import contextlib

from tests._support import temp_workspace
from tests import test_linux_violation_receipt as _violation_fixture
from icode.tools import default_registry
from unittest import mock


def require_user_manager(test):
    """Skip only a missing host prerequisite, never an observed quota failure."""
    @functools.wraps(test)
    def run(self, *args, **kwargs):
        import stat
        bus = Path(f"/run/user/{os.getuid()}/bus")
        if os.getuid() == 0 or not bus.exists() or not stat.S_ISSOCK(bus.lstat().st_mode):
            self.skipTest("non-root user manager bus required; conformance_credit=none")
        return test(self, *args, **kwargs)
    return run


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux-only seqpacket")
class TestConfiguredCallback(unittest.TestCase):
    def check_callback(self, callback, *, seconds: float = 1, cancelled: bool = False,
                       configured_seconds: float | None = None):
        from icode.linux_task_resource import LinuxTaskResourceReceiver, create_task_resource_channel
        from tests.test_linux_task_resource import UNIT, frame
        host, sender = create_task_resource_channel()
        receiver = LinuxTaskResourceReceiver(host, unit=UNIT, limit=2, on_configured=callback)
        try:
            receiver.bind(expected_pid=os.getpid(), expected_uid=os.getuid(), expected_gid=os.getgid())
            options = {"configured_deadline_monotonic": time.monotonic() + configured_seconds} if configured_seconds else {}
            receiver.start(deadline_monotonic=time.monotonic() + seconds, **options)
            sender.send(frame(1))
            sender.settimeout(0.3)
            if cancelled:
                self.assertTrue(self.entered.wait(timeout=0.3), "callback was not invoked")
                receiver.close()
            return sender.recv(64)
        finally:
            receiver.close()
            sender.close()
            host.close()

    def test_callback_runs_before_ack(self):
        calls = []
        ack = self.check_callback(lambda deadline: calls.append(deadline))
        self.assertEqual(ack[:5], b"ICQA1")
        self.assertEqual(len(calls), 1, "ACK bypassed configured identity callback")

    def test_callback_exception_never_acks(self):
        def failure(deadline):
            raise RuntimeError("injected callback failure")
        with self.assertRaises(TimeoutError):
            self.check_callback(failure)

    def test_callback_elapsed_deadline_never_acks(self):
        with self.assertRaises(TimeoutError):
            self.check_callback(lambda deadline: time.sleep(0.15), seconds=0.05)

    def test_callback_cancelled_receiver_never_acks(self):
        self.entered = threading.Event()
        def callback(deadline):
            self.entered.set()
            time.sleep(0.1)
        with self.assertRaises(TimeoutError):
            self.check_callback(callback, cancelled=True)

    def test_callback_configuration_budget_never_acks_late(self):
        with self.assertRaises(TimeoutError):
            self.check_callback(lambda deadline: time.sleep(0.15), configured_seconds=0.05)

    def test_terminal_can_arrive_after_configuration_budget(self):
        from icode.linux_task_resource import LinuxTaskResourceReceiver, create_task_resource_channel
        from tests.test_linux_task_resource import UNIT, frame
        host, sender = create_task_resource_channel()
        receiver = LinuxTaskResourceReceiver(host, unit=UNIT, limit=2)
        try:
            receiver.bind(expected_pid=os.getpid(), expected_uid=os.getuid(), expected_gid=os.getgid())
            receiver.start(deadline_monotonic=time.monotonic() + 1,
                           configured_deadline_monotonic=time.monotonic() + 0.1)
            sender.send(frame(1))
            sender.settimeout(0.3)
            self.assertEqual(sender.recv(64)[:5], b"ICQA1")
            time.sleep(0.15)
            sender.send(frame(3))
            sender.close()
            self.assertTrue(receiver.wait(timeout_seconds=0.5))
            self.assertEqual(receiver.receipt()["channel_status"], "complete")
        finally:
            receiver.close(); sender.close(); host.close()

    def test_configuration_deadline_strict_parameter_validation(self):
        from icode.linux_task_resource import LinuxTaskResourceReceiver, LinuxTaskResourceError, create_task_resource_channel
        from tests.test_linux_task_resource import UNIT
        for value in (True, "tomorrow", float("nan"), float("inf"), time.monotonic() - 1):
            with self.subTest(value=repr(value)):
                host, sender = create_task_resource_channel()
                receiver = LinuxTaskResourceReceiver(host, unit=UNIT, limit=2)
                try:
                    receiver.bind(expected_pid=os.getpid(), expected_uid=os.getuid(), expected_gid=os.getgid())
                    with self.assertRaises(LinuxTaskResourceError):
                        receiver.start(deadline_monotonic=time.monotonic() + 1,
                                       configured_deadline_monotonic=value)
                    self.assertIsNone(receiver._thread)
                finally:
                    receiver.close(); sender.close(); host.close()


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux-only ownership")
class TestScopeDescriptorOwnership(unittest.TestCase):
    def test_directory_close_fault_priority_preserves_interrupt(self):
        from icode import linux_task_scope
        import errno
        actual_open, actual_close = os.open, os.close
        for first, second, expected in ((KeyboardInterrupt(), RuntimeError("secondary close"), KeyboardInterrupt),
                                        (OSError(errno.EIO, "first close"), KeyboardInterrupt(), KeyboardInterrupt)):
            with self.subTest(first=type(first).__name__):
                owned, attempted = [], []
                def tracked_open(*args, **kwargs):
                    descriptor = actual_open(*args, **kwargs); owned.append(descriptor); return descriptor
                def fault_close(descriptor):
                    attempted.append(descriptor); actual_close(descriptor)
                    raise first if len(attempted) == 1 else second
                try:
                    with mock.patch.object(linux_task_scope.os, "open", side_effect=tracked_open), \
                         mock.patch.object(linux_task_scope.os, "close", side_effect=fault_close):
                        try: linux_task_scope._open_directory(Path("/run"), uid=os.getuid())
                        except BaseException as error:
                            self.assertIsInstance(error, expected, "secondary ordinary close error hid interruption")
                        else: self.fail("injected interruption was suppressed")
                    self.assertEqual(len(attempted), 2)
                    for descriptor in owned:
                        with self.assertRaises(OSError): os.fstat(descriptor)
                finally:
                    for descriptor in owned:
                        try: actual_close(descriptor)
                        except OSError: pass

    def test_resource_factory_cleanup_interrupt_closes_both_real_endpoints(self):
        from icode.linux_task_resource import create_task_resource_channel
        baseline = len(os.listdir("/proc/self/fd"))
        for error in (KeyboardInterrupt(), SystemExit(19)):
            with self.subTest(error=type(error).__name__):
                host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                class BadHost(socket.socket):
                    def setsockopt(self, *args): raise OSError("injected SO_PASSCRED failure")
                class InterruptedSender(socket.socket):
                    def close(self):
                        super().close()
                        raise error
                host, sender = BadHost(fileno=host.detach()), InterruptedSender(fileno=sender.detach())
                try:
                    with mock.patch("icode.linux_task_resource.socket.socketpair", return_value=(host, sender)):
                        with self.assertRaises(type(error)): create_task_resource_channel()
                    self.assertEqual(host.fileno(), -1, "factory interruption skipped host endpoint cleanup")
                    self.assertEqual(sender.fileno(), -1)
                finally:
                    socket.socket.close(sender); socket.socket.close(host)
        self.assertEqual(len(os.listdir("/proc/self/fd")), baseline)

    def test_broker_setup_cleanup_interrupt_closes_all_owned_resources(self):
        from icode import execution_broker
        from icode.isolation import LandlockSandbox
        from icode.linux_task_resource import create_task_resource_channel
        from icode.sandbox_policy import SandboxPolicy, NetworkMode
        baseline = len(os.listdir("/proc/self/fd"))
        for error in (KeyboardInterrupt(), SystemExit(23)):
            with self.subTest(error=type(error).__name__), temp_workspace() as root:
                host, sender = create_task_resource_channel()
                class InterruptedSender(socket.socket):
                    def close(self):
                        super().close()
                        raise error
                sender = InterruptedSender(fileno=sender.detach())
                pin, scope_closed = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC), []
                class OwnedScope:
                    environment = {}
                    def close(self):
                        scope_closed.append(True)
                        os.close(pin)
                policy = SandboxPolicy(1,"test","test","code",root,(root,),(root,),(),(),NetworkMode.DENY,(),1,8,1024,())
                try:
                    with mock.patch("icode.linux_task_scope.LinuxTaskScope", return_value=OwnedScope()), \
                         mock.patch("icode.linux_task_resource.create_task_resource_channel", return_value=(host, sender)), \
                         mock.patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel", side_effect=RuntimeError("injected second channel failure")):
                        with self.assertRaises(type(error)):
                            execution_broker.execute_linux_resource_observed_command(
                                [sys.executable], cwd=root, policy=policy, timeout=2,
                                sandbox=LandlockSandbox(helper="/not-executed-owned-fixture"), command_wrapper=lambda argv,*args:argv)
                    self.assertEqual(host.fileno(), -1, "broker interruption skipped resource host endpoint")
                    self.assertEqual(scope_closed, [True], "broker interruption skipped owned scope pin")
                    with self.assertRaises(OSError): os.fstat(pin)
                finally:
                    socket.socket.close(sender); socket.socket.close(host)
                    try: os.close(pin)
                    except OSError: pass
        self.assertEqual(len(os.listdir("/proc/self/fd")), baseline)

    def test_tool_cleanup_interrupt_overrides_ordinary_setup_failure(self):
        from icode import linux_task_scope
        actual_open, actual_close, opened, cleanup_calls = os.open, os.close, [], []
        def owned_open(*args, **kwargs):
            descriptor = actual_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor
        def interrupted_close(descriptor):
            actual_close(descriptor)
            if len(opened) >= 3:
                cleanup_calls.append(descriptor)
                if len(cleanup_calls) == 1: raise KeyboardInterrupt()
        with mock.patch.object(linux_task_scope.os, "open", side_effect=owned_open), \
             mock.patch.object(linux_task_scope.os, "close", side_effect=interrupted_close):
            try: linux_task_scope._trusted_tool("/dev/null", os.getuid())
            except BaseException as error:
                self.assertIsInstance(error, KeyboardInterrupt, "ordinary setup error swallowed cleanup interruption")
            else: self.fail("invalid tool was accepted")
        self.assertEqual(len(cleanup_calls), 2)
        for descriptor in set(opened):
            with self.assertRaises(OSError): os.fstat(descriptor)

    def test_pin_close_interrupt_attempts_all_fds_then_propagates(self):
        from icode.linux_task_scope import LinuxTaskScope
        actual_close = os.close
        for error in (KeyboardInterrupt(), RuntimeError("first close error")):
            with self.subTest(error=type(error).__name__):
                scope = object.__new__(LinuxTaskScope)
                scope._fds = [os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC) for _ in range(3)]
                scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
                owned, attempted = list(scope._fds), []
                def fault_close(descriptor):
                    attempted.append(descriptor)
                    actual_close(descriptor)
                    if len(attempted) == 1: raise error
                try:
                    with mock.patch("icode.linux_task_scope.os.close", side_effect=fault_close):
                        with self.assertRaises(type(error)): scope.close()
                    self.assertEqual(len(attempted), 3, "interrupted first close skipped remaining owned pins")
                    self.assertFalse(scope._fds)
                    self.assertFalse(scope._lifecycle.locked())
                    for descriptor in owned:
                        with self.assertRaises(OSError): os.fstat(descriptor)
                finally:
                    for descriptor in owned:
                        try: actual_close(descriptor)
                        except OSError: pass

    def test_deferred_callback_pin_cleanup_interrupt_reclaims_all_fds(self):
        from icode.linux_task_scope import LinuxTaskScope
        from icode.linux_task_resource import LinuxTaskResourceReceiver, create_task_resource_channel
        from tests.test_linux_task_resource import UNIT, frame
        scope = object.__new__(LinuxTaskScope)
        scope._fds = [os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC) for _ in range(3)]
        scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
        scope._owned = False
        entered, release = threading.Event(), threading.Event()
        owned, attempted, actual_close = list(scope._fds), [], os.close
        def configure(deadline):
            entered.set()
            if not release.wait(timeout=1): raise RuntimeError("bounded callback wait expired")
            scope._owned = True
        scope._configure_locked = configure
        def fault_close(descriptor):
            actual_close(descriptor)
            if descriptor in owned:
                attempted.append(descriptor)
                if len(attempted) == 1: raise KeyboardInterrupt()
        host, sender = create_task_resource_channel()
        receiver = LinuxTaskResourceReceiver(host, unit=UNIT, limit=2, on_configured=scope.configured)
        try:
            receiver.bind(expected_pid=os.getpid(), expected_uid=os.getuid(), expected_gid=os.getgid())
            with mock.patch("icode.linux_task_scope.os.close", side_effect=fault_close):
                receiver.start(deadline_monotonic=time.monotonic() + 2)
                sender.send(frame(1))
                self.assertTrue(entered.wait(timeout=.3))
                scope.close()
                self.assertEqual(attempted, [])
                release.set()
                self.assertTrue(receiver.wait(timeout_seconds=.5))
            self.assertEqual(len(attempted), 3, "deferred callback close leaked owned pins")
            self.assertFalse(scope._owned)
            self.assertFalse(scope._lifecycle.locked())
            self.assertFalse(scope._fds)
            self.assertEqual(receiver.receipt()["channel_status"], "incomplete")
            sender.settimeout(.1)
            with self.assertRaises(TimeoutError): sender.recv(64)
        finally:
            release.set(); receiver.close(); sender.close(); host.close()
            for descriptor in owned:
                try: actual_close(descriptor)
                except OSError: pass

    def test_tool_double_close_fault_preserves_first_error(self):
        from icode import linux_task_scope
        import errno
        opened, leaf_closed = [], []
        actual_open, actual_close = os.open, os.close
        def owned_open(*args, **kwargs):
            descriptor = actual_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor
        def fault_close(descriptor):
            actual_close(descriptor)
            if descriptor == opened[-1]:
                leaf_closed.append(True)
                raise OSError(errno.EIO, "first tool close error")
            if leaf_closed:
                raise OSError(errno.EPERM, "second parent close error")
        with mock.patch.object(linux_task_scope.os, "open", side_effect=owned_open), \
             mock.patch.object(linux_task_scope.os, "close", side_effect=fault_close):
            with self.assertRaises(OSError) as captured:
                linux_task_scope._trusted_tool("/usr/bin/systemctl", os.getuid())
        self.assertEqual(captured.exception.errno, errno.EIO, "later cleanup hid the original exception")
        for descriptor in set(opened):
            with self.assertRaises(OSError): os.fstat(descriptor)

    def test_tool_close_failure_still_reclaims_parent(self):
        from icode import linux_task_scope
        import errno
        opened, attempted = [], []
        actual_open, actual_close = os.open, os.close
        def owned_open(*args, **kwargs):
            descriptor = actual_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor
        def fault_close(descriptor):
            attempted.append(descriptor)
            actual_close(descriptor)
            if descriptor == opened[-1]:
                raise OSError(errno.EIO, "injected tool close failure")
        try:
            with mock.patch.object(linux_task_scope.os, "open", side_effect=owned_open), \
                 mock.patch.object(linux_task_scope.os, "close", side_effect=fault_close):
                with self.assertRaises(OSError) as captured:
                    linux_task_scope._trusted_tool("/usr/bin/systemctl", os.getuid())
            self.assertEqual(captured.exception.errno, errno.EIO)
            self.assertIn(opened[-2], attempted, "pinned tool parent survived close failure")
            with self.assertRaises(OSError): os.fstat(opened[-2])
        finally:
            for descriptor in set(opened):
                try: os.fstat(descriptor)
                except OSError: continue
                actual_close(descriptor)

    def test_scope_argv_has_explicit_helper_separator(self):
        from icode.linux_task_scope import LinuxTaskScope
        scope = object.__new__(LinuxTaskScope)
        scope.unit = "icode-task-" + "a" * 32 + ".scope"
        for version in (249, 254):
            scope.version = version
            argv = scope.wrap(["/trusted/helper", "--", "$X", "", "-dash"])
            self.assertEqual(argv[argv.index("/trusted/helper") - 1], "--")
            self.assertEqual(argv[-3:], ["$X", "", "-dash"])

    def test_parent_close_failure_reclaims_following_fd_and_preserves_error(self):
        from icode import linux_task_scope
        import errno
        opened, attempted = [], []
        actual_open, actual_close = os.open, os.close
        def open_owned(*args, **kwargs):
            descriptor = actual_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor
        def fail_parent_close(descriptor):
            attempted.append(descriptor)
            actual_close(descriptor)
            if descriptor == opened[0]:
                raise OSError(errno.EIO, "injected parent close failure")
        try:
            with mock.patch.object(linux_task_scope.os, "open", side_effect=open_owned), \
                 mock.patch.object(linux_task_scope.os, "close", side_effect=fail_parent_close):
                with self.assertRaises(OSError) as captured:
                    linux_task_scope._open_directory(Path("/run"), uid=os.getuid())
            self.assertEqual(captured.exception.errno, errno.EIO)
            self.assertEqual(attempted.count(opened[0]), 1, "old FD was closed twice")
            with self.assertRaises(OSError):
                os.fstat(opened[1])
        finally:
            for descriptor in opened:
                try:
                    os.fstat(descriptor)
                except OSError:
                    continue
                actual_close(descriptor)


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                     "Linux/compiler required; conformance_credit=none")
class TestLinuxProductTaskQuota(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory(prefix="icode-product-quota-")
        cls.addClassCleanup(cls._directory.cleanup)
        directory = Path(cls._directory.name)
        cls._helper = directory / "icode-landlock"
        source = Path(__file__).resolve().parents[1] / "native/linux/icode_landlock.c"
        result = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                 str(source), "-o", str(cls._helper)],
                                capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError("actual native helper compile failed")
        cls._manifest = directory / "icode-landlock.sha256"
        cls._manifest.write_text(hashlib.sha256(cls._helper.read_bytes()).hexdigest() + "\n",
                                 encoding="ascii")

    def context(self, root: Path, *, limit: int = 1):
        context = _violation_fixture.TestLinuxViolationReceipt._context(self, root)
        context.policy = replace(context.policy, process_limit=limit)
        return context

    def run_python(self, root: Path, code: str, *, limit: int = 1, timeout: float = 8):
        return default_registry().invoke("run_command", self.context(root, limit=limit),
                                         {"argv": [sys.executable, "-I", "-c", code], "timeout": timeout})

    @contextlib.contextmanager
    def capture_scopes(self):
        from icode.linux_task_scope import LinuxTaskScope
        scopes = []
        original = LinuxTaskScope.configured
        def configured(scope, deadline):
            original(scope, deadline)
            scopes.append(scope)
        with mock.patch.object(LinuxTaskScope, "configured", new=configured):
            yield scopes

    def assert_collected(self, scopes):
        self.assertTrue(scopes)
        for scope in scopes:
            self.assertTrue(scope._owned)
            self.assertFalse(scope._path.exists(), "own pinned cgroup path remains")
            fields = scope._show(time.monotonic() + 0.5)
            self.assertEqual(fields["LoadState"], "not-found")
            self.assertEqual(fields["ControlGroup"], "")
            self.assertFalse(Path(f"/proc/{scope._pid}").exists(), "own launcher was not reaped")

    @require_user_manager
    def test_thread_is_charged_and_supervisor_is_outside_payload(self):
        with temp_workspace() as root, self.capture_scopes() as scopes, ThreadPoolExecutor(max_workers=1) as pool:
            code = ("import ctypes,errno,os,time\n"
                    "libc=ctypes.CDLL(None); thread=ctypes.c_ulong()\n"
                    "callback=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p)(lambda _:None)\n"
                    "assert libc.pthread_create(ctypes.byref(thread),None,callback,None)==errno.EAGAIN\n"
                    "open('ready','w').write('ready')\n"
                    "deadline=time.monotonic()+4\n"
                    "while not os.path.exists('release'):\n"
                    " assert time.monotonic()<deadline; time.sleep(.01)\n"
                    "print('thread charged')\n")
            future = pool.submit(self.run_python, root, code)
            try:
                deadline = time.monotonic() + 2
                while not (root / "ready").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((root / "ready").exists())
                scope = scopes[0]
                self.assertEqual((scope._path / "payload/pids.current").read_text().strip(), "1")
                self.assertGreaterEqual(int((scope._path / "payload/pids.events").read_text().split()[1]), 1)
                supervisors = (scope._path / "supervisor/cgroup.procs").read_text().split()
                payload_pids = (scope._path / "payload/cgroup.procs").read_text().split()
                self.assertIn(str(scope._pid), supervisors)
                self.assertTrue(set(supervisors).isdisjoint(payload_pids))
                self.assertNotIn(str(os.getpid()), (scope._path / "payload/cgroup.procs").read_text().split())
            finally:
                (root / "release").touch()
            result = future.result(timeout=4)
            self.assertTrue(result.ok, result.content)
            self.assertTrue(result.meta["scope_cleanup_ok"])
            self.assert_collected(scopes)

    @require_user_manager
    def test_cap_two_sets_id_child_cannot_create_third_task(self):
        code = ("import errno,os,signal\n"
                "child=os.fork()\n"
                "if child==0:\n"
                " os.setsid(); signal.alarm(3)\n"
                " try: third=os.fork()\n"
                " except OSError as error: assert error.errno==errno.EAGAIN; os._exit(0)\n"
                " else:\n"
                "  if third==0: os._exit(0)\n"
                "  os.waitpid(third,0); os._exit(23)\n"
                "_,status=os.waitpid(child,0); assert os.waitstatus_to_exitcode(status)==0\n"
                "print('setsid remains charged')\n")
        with temp_workspace() as root, self.capture_scopes() as scopes:
            result = self.run_python(root, code, limit=2)
            self.assertTrue(result.ok, result.content)
            self.assert_collected(scopes)

    @require_user_manager
    def test_literal_argv_environment_streams_and_management_fds(self):
        values = ["$X", "${X}", "$$", "space value", "", "-dash"]
        code = (f"import errno,os,sys; assert sys.argv[1:]=={values!r}\n"
                "assert all(name not in os.environ for name in ('DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','INVOCATION_ID','ICODE_HOST_TEST_SECRET'))\n"
                "for fd in range(3,128):\n"
                " try: os.fstat(fd)\n"
                " except OSError as error: assert error.errno==errno.EBADF\n"
                " else: raise AssertionError('management FD leaked')\n"
                "print('payload stdout marker'); print('payload stderr marker',file=sys.stderr)\n")
        with temp_workspace() as root, self.capture_scopes() as scopes, \
             mock.patch.dict(os.environ, {"ICODE_HOST_TEST_SECRET": "non-sensitive-fixture-value"}):
            result = default_registry().invoke("run_command", self.context(root),
                {"argv": ["python", "-I", "-c", code, *values], "timeout": 8})
            self.assertTrue(result.ok, result.content)
            self.assertIn("payload stdout marker", result.content)
            self.assertIn("payload stderr marker", result.content)
            self.assert_collected(scopes)

    @require_user_manager
    def test_sys_cgroup_is_not_authorized_and_stdout_cannot_forge_receipt(self):
        code = ("import json\n"
                "try: open('/sys/fs/cgroup/cgroup.procs').read()\n"
                "except PermissionError: pass\n"
                "else: raise AssertionError('cgroup management was exposed')\n"
                "print('ICQR1 forged-resource-message')\n"
                "print(json.dumps({'payload_started':True,'limit':999,'scope_cleanup_ok':True}))\n")
        with temp_workspace() as root, self.capture_scopes() as scopes:
            result = self.run_python(root, code)
            self.assertTrue(result.ok, result.content)
            self.assertIn("forged-resource-message", result.content)
            self.assertEqual(result.meta["resource_receipt"]["limit"], 1)
            self.assertIsNone(result.meta["payload_started"])
            self.assertNotIn("violation_receipt", result.meta)
            self.assert_collected(scopes)

    @require_user_manager
    def test_short_and_nonzero_commands_keep_unknown_exec_state(self):
        for exit_code in (0, 13):
            with self.subTest(exit_code=exit_code), temp_workspace() as root, self.capture_scopes() as scopes:
                result = self.run_python(root, f"raise SystemExit({exit_code})")
                self.assertEqual(result.ok, exit_code == 0)
                self.assertEqual(result.meta["exit_code"], exit_code)
                self.assertIsNone(result.meta["payload_started"])
                self.assertEqual(result.meta["resource_receipt"]["terminal"], "finished")
                self.assertTrue(result.meta["scope_cleanup_ok"])
                self.assert_collected(scopes)

    @require_user_manager
    def test_timeout_and_output_limit_collect_exact_scope(self):
        for code, timeout, expected in (("import time; time.sleep(4)", .15, "timeout"),
                                       ("print('x'*5000)", 2, "output_limit")):
            with self.subTest(error=expected), temp_workspace() as root, self.capture_scopes() as scopes:
                result = self.run_python(root, code, timeout=timeout)
                self.assertFalse(result.ok)
                self.assertEqual(result.meta["error"], expected)
                self.assertIsNone(result.meta["payload_started"])
                self.assertTrue(result.meta["scope_cleanup_ok"])
                self.assert_collected(scopes)

    @require_user_manager
    def test_two_concurrent_scopes_are_independent(self):
        with temp_workspace() as first, temp_workspace() as second, self.capture_scopes() as scopes, \
             ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.run_python, root, "import time; time.sleep(.1); print('independent')", limit=cap)
                       for root, cap in ((first, 1), (second, 2))]
            results = [future.result(timeout=4) for future in futures]
            self.assertTrue(all(result.ok for result in results), [result.content for result in results])
            self.assertEqual({result.meta["resource_receipt"]["limit"] for result in results}, {1, 2})
            self.assertEqual(len({scope.unit for scope in scopes}), 2)
            self.assertEqual(len({scope._identities[0] for scope in scopes}), 2)
            self.assert_collected(scopes)

    @require_user_manager
    def test_ack_wrong_fields_timeout_and_callback_exception_never_release_payload(self):
        from icode.linux_task_scope import LinuxTaskScope
        original_show, original_configured = LinuxTaskScope._show, LinuxTaskScope.configured
        for failure in ("wrong_group", "duplicate", "query_timeout", "callback_exception"):
            with self.subTest(failure=failure), temp_workspace() as root:
                observed = []
                def show(scope, deadline):
                    if not observed:
                        observed.append((scope, Path("/sys/fs/cgroup") / scope._membership()[1:].removesuffix("/supervisor")))
                        if failure == "query_timeout":
                            scope._query_adapter([sys.executable, "-I", "-c", "import time;time.sleep(2)"],
                                                 scope.environment, deadline)
                        if failure == "duplicate":
                            actual_query = scope._query_adapter
                            def duplicate_query(argv, environment, query_deadline):
                                raw = actual_query(argv, environment, query_deadline)
                                return raw + ("Id=" + scope.unit + "\n").encode("ascii")
                            scope._query_adapter = duplicate_query
                            try: return original_show(scope, deadline)
                            finally: scope._query_adapter = actual_query
                    fields = original_show(scope, deadline)
                    if failure == "wrong_group": fields["ControlGroup"] += "/wrong"
                    return fields
                def configured(scope, deadline):
                    original_configured(scope, deadline)
                    if failure == "callback_exception": raise RuntimeError("injected callback failure")
                with mock.patch.object(LinuxTaskScope, "_show", new=show), \
                     mock.patch.object(LinuxTaskScope, "configured", new=configured):
                    result = self.run_python(root, "open('forbidden-marker','w').write('bad')")
                self.assertFalse(result.ok)
                self.assertIsNone(result.meta["payload_started"])
                self.assertFalse((root / "forbidden-marker").exists())
                self.assertEqual(len(observed), 1)
                scope, path = observed[0]
                deadline = time.monotonic() + 1
                while path.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertFalse(path.exists())
                self.assertEqual(original_show(scope, time.monotonic() + .5)["LoadState"], "not-found")
                self.assertFalse(Path(f"/proc/{scope._pid}").exists())

    def test_no_bus_wrong_tool_and_out_of_range_cap_fail_before_launch(self):
        from icode import linux_task_scope, execution_broker
        actual_directory, actual_tool = linux_task_scope._open_directory, linux_task_scope._trusted_tool
        for failure in ("no_bus", "wrong_tool", "cap_range"):
            with self.subTest(failure=failure), temp_workspace() as root:
                context = self.context(root, limit=2147483648 if failure == "cap_range" else 1)
                wrong_tool = root / "not-a-trusted-tool"
                wrong_tool.write_text("test-only-untrusted-tool", encoding="ascii")
                def directory(path, **kwargs):
                    if failure == "no_bus" and path == Path(f"/run/user/{os.getuid()}"):
                        raise FileNotFoundError("injected missing current user bus")
                    return actual_directory(path, **kwargs)
                def tool(path, uid):
                    return actual_tool(str(wrong_tool) if failure == "wrong_tool" else path, uid)
                with mock.patch.object(linux_task_scope, "_open_directory", new=directory), \
                     mock.patch.object(linux_task_scope, "_trusted_tool", new=tool), \
                     mock.patch.object(execution_broker.subprocess, "Popen", wraps=subprocess.Popen) as launch:
                    result = default_registry().invoke("run_command", context,
                        {"argv": [sys.executable, "-I", "-c", "open('bad-marker','w').close()"], "timeout": 8})
                    self.assertFalse(launch.called, "invalid setup started an actual process")
                self.assertFalse(result.ok)
                self.assertEqual(result.meta["error"], "resource_setup_failed")
                self.assertIs(result.meta["payload_started"], False)
                self.assertFalse((root / "bad-marker").exists())

    def test_manager_stderr_has_independent_discard_budget(self):
        from icode.execution_broker import _execute_policy_command
        with temp_workspace() as root:
            result = _execute_policy_command(
                [sys.executable, "-I", "-c", "import os;os.write(2,b'manager-private-'+b'x'*65537)"],
                cwd=root, policy=self.context(root).policy, timeout=2, manager_stderr=True)
        self.assertEqual(result.error, "manager_output_limit")
        self.assertEqual(result.raw_output, b"")
        self.assertEqual(result.output_bytes, 0)
        self.assertFalse(result.output_truncated)

    @require_user_manager
    def test_selector_read_thread_start_and_interrupt_clean_owned_launch(self):
        from icode import execution_broker
        from icode.linux_task_scope import LinuxTaskScope
        from icode.linux_task_resource import LinuxTaskResourceReceiver
        original_core, original_wrap = execution_broker._execute_policy_command, LinuxTaskScope.wrap
        for failure in ("selector", "read", "thread_start", "interrupt"):
            with self.subTest(failure=failure), temp_workspace() as root:
                scopes = []
                def wrap(scope, helper):
                    scopes.append(scope)
                    return original_wrap(scope, helper)
                def core(argv, **kwargs):
                    if "--scope" not in argv:
                        return original_core(argv, **kwargs)
                    if failure == "selector":
                        with mock.patch.object(execution_broker.selectors, "DefaultSelector",
                                               side_effect=OSError("injected selector allocation failure")):
                            return original_core(argv, **kwargs)
                    if failure == "thread_start":
                        actual_start = threading.Thread.start
                        def start(worker):
                            if worker.name == "icode-task-resource": raise RuntimeError("injected worker creation failure")
                            return actual_start(worker)
                        with mock.patch.object(threading.Thread, "start", new=start):
                            return original_core(argv, **kwargs)
                    actual_spawn, actual_read = kwargs["on_spawn"], os.read
                    fault_fd = []
                    def spawn(process, deadline):
                        actual_spawn(process, deadline)
                        fault_fd.append(process.stdout.fileno())
                    kwargs["on_spawn"] = spawn
                    def read(descriptor, size):
                        if fault_fd and descriptor == fault_fd[0]:
                            fault_fd.clear()
                            if failure == "interrupt": raise KeyboardInterrupt()
                            raise OSError("injected actual payload read failure")
                        return actual_read(descriptor, size)
                    with mock.patch.object(execution_broker.os, "read", new=read):
                        return original_core(argv, **kwargs)
                with mock.patch.object(LinuxTaskScope, "wrap", new=wrap), \
                     mock.patch.object(execution_broker, "_execute_policy_command", new=core):
                    if failure == "interrupt":
                        with self.assertRaises(KeyboardInterrupt): self.run_python(root, "print('ready')")
                    else:
                        result = self.run_python(root, "print('ready')")
                        self.assertFalse(result.ok)
                        self.assertIsNone(result.meta["payload_started"])
                self.assertEqual(len(scopes), 1)
                scope = scopes[0]
                deadline = time.monotonic() + 1
                while scope._show(deadline)["LoadState"] != "not-found" and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(scope._show(time.monotonic() + .5)["LoadState"], "not-found")
                if scope._pid is not None: self.assertFalse(Path(f"/proc/{scope._pid}").exists())

    @require_user_manager
    def test_existing_scope_collision_preserves_old_member_directory_and_limit(self):
        from icode.linux_task_scope import LinuxTaskScope
        nonce = os.urandom(16).hex()
        unit = "icode-task-" + nonce + ".scope"
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C",
                       "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
                       "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{os.getuid()}/bus"}
        with temp_workspace() as root:
            ready = root / "old-ready.json"
            code = ("import json,os,pathlib,signal,time;signal.alarm(6)\n"
                    "group=pathlib.Path('/sys/fs/cgroup')/pathlib.Path('/proc/self/cgroup').read_text().split('0::',1)[1].strip().lstrip('/')\n"
                    "payload=group/'payload';payload.mkdir();(group/'cgroup.subtree_control').write_text('+pids');(payload/'pids.max').write_text('3')\n"
                    f"pathlib.Path({str(ready)!r}).write_text(json.dumps({{'path':str(group),'inode':group.stat().st_ino,'payload_inode':payload.stat().st_ino,'pid':os.getpid()}}))\n"
                    "time.sleep(5)\n")
            child = subprocess.Popen(["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect",
                                      "--no-ask-password", "--description=ICODE task command", "--unit=" + unit,
                                      "--property=Delegate=pids", "--", sys.executable, "-I", "-c", code],
                                     env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline = time.monotonic() + 2
                while not ready.exists() and time.monotonic() < deadline: time.sleep(.01)
                self.assertTrue(ready.exists(), "bounded old-scope fixture did not start")
                facts = json.loads(ready.read_text())
                group = Path(facts["path"])
                members = (group / "cgroup.procs").read_text().split()
                self.assertIn(str(child.pid), members)
                with mock.patch("icode.linux_task_scope.secrets.token_hex", return_value=nonce):
                    result = self.run_python(root, "open('collision-marker','w').close()")
                self.assertFalse(result.ok)
                self.assertFalse((root / "collision-marker").exists())
                self.assertIsNone(child.poll(), "collision cleanup signalled the old owner")
                self.assertEqual(group.stat().st_ino, facts["inode"])
                self.assertEqual((group / "payload").stat().st_ino, facts["payload_inode"])
                self.assertEqual((group / "cgroup.procs").read_text().split(), members)
                self.assertEqual((group / "payload/pids.max").read_text().strip(), "3")
            finally:
                if child.poll() is None: os.killpg(child.pid, signal.SIGKILL)
                child.communicate(timeout=2)
                if ready.exists():
                    group = Path(json.loads(ready.read_text())["path"])
                    deadline = time.monotonic() + 1
                    while group.exists() and time.monotonic() < deadline: time.sleep(.01)
                    self.assertFalse(group.exists(), "bounded old own scope did not GC")

    @require_user_manager
    def test_host_sigkill_removes_charged_setsid_descendants_without_python_finally(self):
        repository = Path(__file__).resolve().parents[1]
        with temp_workspace() as root:
            metadata = root / "host-scope.json"
            payload = ("import os,signal,time;signal.alarm(5)\n"
                       "child=os.fork()\n"
                       "if child==0:\n"
                       " os.setsid();signal.alarm(4);time.sleep(2);open('late-marker','w').close();os._exit(0)\n"
                       "open('payload-ready','w').write('ready')\n"
                       "time.sleep(4)\n")
            driver = textwrap.dedent(f"""\
                import sys,json,os,pathlib
                sys.path.insert(0,{str(repository / 'src')!r})
                from icode.isolation import LandlockSandbox
                from icode.sandbox_policy import SandboxPolicy,NetworkMode
                from icode.tools import ToolContext,default_registry
                from icode.linux_task_scope import LinuxTaskScope
                root=pathlib.Path({str(root)!r})
                original=LinuxTaskScope.configured
                def configured(scope,deadline):
                    original(scope,deadline)
                    pathlib.Path({str(metadata)!r}).write_text(json.dumps({{'unit':scope.unit,'path':str(scope._path),'pid':scope._pid,'identity':scope._identities[0]}}))
                LinuxTaskScope.configured=configured
                policy=SandboxPolicy(1,'host-crash','host-crash','code',root,(root,),(root,),(),(),NetworkMode.DENY,(),2,8,2048,())
                context=ToolContext(root=root,policy=policy,sandbox=LandlockSandbox(helper={str(self._helper)!r},manifest={str(self._manifest)!r}))
                result=default_registry().invoke('run_command',context,{{'argv':[sys.executable,'-I','-c',{payload!r}],'timeout':8}})
                raise SystemExit(0 if result.ok else 1)
                """)
            host = subprocess.Popen([sys.executable, "-I", "-c", driver], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, start_new_session=True)
            facts, pids = None, []
            try:
                deadline = time.monotonic() + 2
                while not (root / "payload-ready").exists() and time.monotonic() < deadline: time.sleep(.01)
                self.assertTrue((root / "payload-ready").exists(), "actual registry payload did not reach barrier")
                facts = json.loads(metadata.read_text())
                group = Path(facts["path"])
                self.assertEqual((group.stat().st_dev, group.stat().st_ino), tuple(facts["identity"]))
                pids = [int(pid) for pid in (group / "payload/cgroup.procs").read_text().split()]
                self.assertEqual(len(pids), 2)
                self.assertEqual((group / "payload/pids.current").read_text().strip(), "2")
                host.kill()
                host.communicate(timeout=2)
                self.assertEqual(host.returncode, -signal.SIGKILL)
                deadline = time.monotonic() + 2
                while group.exists() and time.monotonic() < deadline: time.sleep(.01)
                self.assertFalse(group.exists(), "host death left its exact cgroup")
                for pid in [facts["pid"], *pids]:
                    status = Path(f"/proc/{pid}/status")
                    if status.exists():
                        self.assertIn("\nState:\tZ", status.read_text(), "host death left a live charged process")
                time.sleep(2.1)
                self.assertFalse((root / "late-marker").exists())
                answer = subprocess.run(["/usr/bin/systemctl", "--user", "show", facts["unit"], "--property=LoadState,ControlGroup"],
                                        env={"PATH":"/usr/bin:/bin", "XDG_RUNTIME_DIR":f"/run/user/{os.getuid()}",
                                             "DBUS_SESSION_BUS_ADDRESS":f"unix:path=/run/user/{os.getuid()}/bus"},
                                        capture_output=True, timeout=1)
                self.assertIn(b"LoadState=not-found", answer.stdout)
                self.assertIn(b"ControlGroup=\n", answer.stdout)
            finally:
                if host.poll() is None: host.kill()
                host.communicate(timeout=2)
                # Native children are alarm-bounded even if the assertion fails;
                # never signal a PID discovered outside this owned scope.
                if facts:
                    deadline = time.monotonic() + 6
                    while Path(facts["path"]).exists() and time.monotonic() < deadline: time.sleep(.02)
                    self.assertFalse(Path(facts["path"]).exists())

    @require_user_manager
    def test_registry_cap_one_enforces_real_fork_quota(self) -> None:
        with temp_workspace() as root:
            result = self.run_python(root,
                "import errno,os\n"
                "try: child=os.fork()\n"
                "except OSError as error: assert error.errno==errno.EAGAIN\n"
                "else:\n"
                "    if child==0: os._exit(0)\n"
                "    os.waitpid(child,0); raise AssertionError('quota absent')\n"
                "print('quota enforced')\n")
        self.assertTrue(result.ok, result.content)
        self.assertEqual(result.meta["resource_receipt"]["limit"], 1)
        self.assertTrue(result.meta["resource_receipt"]["configured"])
        self.assertIsNone(result.meta["payload_started"])
        self.assertTrue(result.meta["scope_cleanup_ok"])

    @require_user_manager
    def test_relative_python_keeps_current_venv(self) -> None:
        with temp_workspace() as root:
            result = default_registry().invoke("run_command", self.context(root),
                {"argv": ["python", "-I", "-c",
                          f"import sys; assert sys.prefix=={sys.prefix!r}; print('current interpreter')"],
                 "timeout": 8})
        self.assertTrue(result.ok, result.content)
        self.assertIn("current interpreter", result.content)

    def test_core_stdout_close_failure_still_closes_manager_stderr(self) -> None:
        from icode import execution_broker
        original = subprocess.Popen
        children = []
        class FaultClose:
            def __init__(self, stream):
                self.stream = stream
            def fileno(self):
                return self.stream.fileno()
            def close(self):
                self.stream.close()
                raise RuntimeError("injected close failure")
        def launch(*args, **kwargs):
            child = original(*args, **kwargs)
            child.stdout = FaultClose(child.stdout)
            children.append(child)
            return child
        with temp_workspace() as root:
            try:
                with mock.patch.object(execution_broker.subprocess, "Popen", side_effect=launch):
                    with self.assertRaisesRegex(RuntimeError, "injected close failure"):
                        execution_broker._execute_policy_command(
                            [sys.executable, "-I", "-c", "print('ok')"], cwd=root,
                            policy=self.context(root).policy, timeout=2, manager_stderr=True)
                self.assertEqual(len(children), 1)
                self.assertTrue(children[0].stderr.closed, "manager stderr survived stdout-close failure")
                self.assertIsNotNone(children[0].poll())
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=2)
                    child.stderr.close()

    def test_core_pipe_close_priority_keeps_interrupt_and_first_peer_error(self):
        from icode import execution_broker
        actual_launch = subprocess.Popen
        for first, second, expected in ((KeyboardInterrupt(), RuntimeError("second"), KeyboardInterrupt),
                                        (RuntimeError("first"), KeyboardInterrupt(), KeyboardInterrupt),
                                        (RuntimeError("first"), RuntimeError("second"), RuntimeError)):
            with self.subTest(first=type(first).__name__, second=type(second).__name__), temp_workspace() as root:
                children = []
                class FaultStream:
                    def __init__(self, stream, error): self.stream, self.error = stream, error
                    def fileno(self): return self.stream.fileno()
                    def close(self): self.stream.close(); raise self.error
                def launch(*args, **kwargs):
                    child = actual_launch(*args, **kwargs); children.append(child)
                    child.stdout = FaultStream(child.stdout, first)
                    child.stderr = FaultStream(child.stderr, second)
                    return child
                try:
                    with mock.patch.object(execution_broker.subprocess, "Popen", side_effect=launch):
                        try:
                            execution_broker._execute_policy_command([sys.executable, "-I", "-c", "print('bounded')"],
                                cwd=root, policy=self.context(root).policy, timeout=1, manager_stderr=True)
                        except BaseException as error:
                            self.assertIsInstance(error, expected, "later ordinary pipe error hid interruption")
                            if expected is RuntimeError: self.assertIs(error, first)
                        else: self.fail("injected close error was suppressed")
                    self.assertIsNotNone(children[0].poll())
                    self.assertTrue(children[0].stdout.stream.closed)
                    self.assertTrue(children[0].stderr.stream.closed)
                finally:
                    for child in children:
                        if child.poll() is None: child.kill()
                        child.wait(timeout=2)
                        child.stdout.stream.close(); child.stderr.stream.close()

    def test_dual_endpoint_wrapper_rejects_invalid_trusted_inputs(self):
        from icode.linux_task_resource import create_task_resource_channel
        from icode.linux_seccomp_notify import create_seccomp_listener_handoff_channel
        control_host, control_sender = create_seccomp_listener_handoff_channel()
        resource_host, resource_sender = create_task_resource_channel()
        try:
            with temp_workspace() as root:
                context = self.context(root)
                valid = {"policy": context.policy, "control_socket": control_sender,
                         "resource_socket": resource_sender, "unit": "icode-task-" + "a" * 32 + ".scope"}
                for key, value in (("policy", object()), ("control_socket", None),
                                   ("resource_socket", control_sender), ("unit", "icode-task-bad.scope")):
                    with self.subTest(key=key):
                        try:
                            context.sandbox.wrap_policy_with_resource_receipt([sys.executable],
                                                                             **dict(valid, **{key: value}))
                        except Exception as error:
                            self.assertIsInstance(error, ValueError, "trusted input was dereferenced before validation")
                        else:
                            self.fail("invalid private wrapper input was accepted")
        finally:
            for endpoint in (resource_sender, resource_host, control_sender, control_host): endpoint.close()

    @require_user_manager
    def test_missing_exec_is_fixed_preexec_failure(self) -> None:
        with temp_workspace() as root:
            result = default_registry().invoke("run_command", self.context(root),
                {"argv": ["/missing-product-quota-executable"], "timeout": 8})
        self.assertIs(result.meta["payload_started"], False)
        self.assertEqual(result.meta.get("error"), "resource_setup_failed")
        self.assertNotIn("execvp", result.content)

    def test_policy_binding_failure_projects_not_started(self) -> None:
        with temp_workspace() as root:
            context = self.context(root)
            context.read_only_workspace = True
            result = default_registry().invoke("run_command", context,
                {"argv": [sys.executable, "-I", "-c", "raise AssertionError('must not run')"], "timeout": 8})
        self.assertEqual(result.meta.get("error"), "isolation_unavailable")
        self.assertIs(result.meta.get("payload_started"), False)

    def test_binding_rejects_before_manager_query_when_runtime_is_missing(self):
        from icode import execution_broker, linux_task_scope
        original = linux_task_scope._open_directory
        def no_runtime(path, **kwargs):
            if path == Path(f"/run/user/{os.getuid()}"): raise FileNotFoundError()
            return original(path, **kwargs)
        for failure in ("readonly", "root_mismatch"):
            with self.subTest(failure=failure), temp_workspace() as root:
                context = self.context(root)
                if failure == "readonly": context.read_only_workspace = True
                else: context.policy = replace(context.policy, workspace_root=root.parent,
                                               read_roots=(root.parent,), write_roots=(root.parent,))
                with mock.patch.object(linux_task_scope, "_open_directory", new=no_runtime), \
                     mock.patch.object(execution_broker.subprocess, "Popen", wraps=subprocess.Popen) as launch:
                    result = default_registry().invoke("run_command", context,
                        {"argv": [sys.executable, "-I", "-c", "open('must-not-run','w').close()"], "timeout": 8})
                    self.assertFalse(launch.called)
                self.assertFalse(result.ok)
                self.assertEqual(result.meta["error"], "isolation_unavailable")
                self.assertIs(result.meta["payload_started"], False)
                self.assertFalse((root / "must-not-run").exists())

    @require_user_manager
    def test_resource_wait_failure_still_closes_actual_receiver(self):
        from icode.linux_task_resource import LinuxTaskResourceReceiver
        actual_start, actual_close = LinuxTaskResourceReceiver.start, LinuxTaskResourceReceiver.close
        for error in (RuntimeError("injected resource wait failure"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), temp_workspace() as root:
                started, closed = [], []
                def start(receiver, **kwargs):
                    started.append(receiver)
                    return actual_start(receiver, **kwargs)
                def close(receiver):
                    closed.append(receiver)
                    return actual_close(receiver)
                try:
                    with mock.patch.object(LinuxTaskResourceReceiver, "start", new=start), \
                         mock.patch.object(LinuxTaskResourceReceiver, "close", new=close), \
                         mock.patch.object(LinuxTaskResourceReceiver, "wait", side_effect=error):
                        if isinstance(error, KeyboardInterrupt):
                            with self.assertRaises(KeyboardInterrupt):
                                self.run_python(root, "print('short')")
                        else:
                            result = self.run_python(root, "print('short')")
                            self.assertFalse(result.ok)
                    self.assertEqual(len(started), 1)
                    self.assertIn(started[0], closed, "wait failure skipped actual receiver close")
                    self.assertFalse(started[0]._thread.is_alive())
                finally:
                    for receiver in started:
                        actual_close(receiver)

    @require_user_manager
    def test_unconfirmed_receiver_close_is_not_success(self):
        from icode.linux_task_resource import LinuxTaskResourceReceiver
        actual_close = LinuxTaskResourceReceiver.close
        def unconfirmed(receiver):
            actual_close(receiver)
            return False
        with temp_workspace() as root, mock.patch.object(LinuxTaskResourceReceiver, "close", new=unconfirmed):
            result = self.run_python(root, "print('short')")
        self.assertFalse(result.ok, "unconfirmed worker cleanup was reported successful")
        self.assertEqual(result.meta["resource_receipt"]["channel_status"], "incomplete")

    @require_user_manager
    def test_active_callback_keeps_owned_pins_until_worker_returns(self):
        from icode.linux_task_scope import LinuxTaskScope
        from icode.linux_task_resource import LinuxTaskResourceReceiver
        entered, release = threading.Event(), threading.Event()
        pins, receivers = [], []
        actual_show, actual_start = LinuxTaskScope._show, LinuxTaskResourceReceiver.start
        def held_show(scope, deadline):
            if scope._fds and not entered.is_set():
                pins.extend(scope._fds)
                entered.set()
                if not release.wait(timeout=6):
                    raise RuntimeError("bounded callback release expired")
            return actual_show(scope, deadline)
        def start(receiver, **kwargs):
            receivers.append(receiver)
            return actual_start(receiver, **kwargs)
        with temp_workspace() as root, ThreadPoolExecutor(max_workers=1) as pool:
            try:
                with mock.patch.object(LinuxTaskScope, "_show", new=held_show), \
                     mock.patch.object(LinuxTaskResourceReceiver, "start", new=start):
                    future = pool.submit(self.run_python, root, "print('must not execute')", timeout=0.2)
                    self.assertTrue(entered.wait(timeout=1))
                    result = future.result(timeout=4)
                    self.assertFalse(result.ok)
                    self.assertIsNone(result.meta["payload_started"])
                    self.assertTrue(receivers[0]._thread.is_alive())
                    self.assertEqual(len(pins), 3)
                    for descriptor in pins:
                        try:
                            os.fstat(descriptor)
                        except OSError:
                            self.fail("scope pin was closed while callback still owned it")
            finally:
                release.set()
                for receiver in receivers:
                    self.assertTrue(receiver.close())
                for descriptor in pins:
                    with self.assertRaises(OSError): os.fstat(descriptor)

    @require_user_manager
    def test_phase_four_is_fixed_failure_and_discards_payload_output(self) -> None:
        from icode.isolation import LandlockSandbox
        with tempfile.TemporaryDirectory(prefix="icode-product-finish-fault-") as temporary:
            directory = Path(temporary)
            repository = Path(__file__).resolve().parents[1]
            source = directory / "fault.c"
            source.write_text('#define _GNU_SOURCE\n' +
                f'#include "{repository / "native/linux/icode_task_quota.h"}"\n' +
                'static int fault_finish(struct icode_task_quota *state){\n'
                'icode_task_quota_finish(state);errno=EBUSY;return -1;}\n'
                '#define icode_task_quota_finish fault_finish\n' +
                f'#include "{repository / "native/linux/icode_landlock.c"}"\n', encoding="ascii")
            helper = directory / "helper"
            build = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                                    str(source), "-o", str(helper)], capture_output=True, timeout=30)
            self.assertEqual(build.returncode, 0)
            manifest = directory / "helper.sha256"
            manifest.write_text(hashlib.sha256(helper.read_bytes()).hexdigest() + "\n", encoding="ascii")
            with temp_workspace() as root:
                context = self.context(root)
                context.sandbox = LandlockSandbox(helper=str(helper), manifest=str(manifest))
                result = default_registry().invoke("run_command", context,
                    {"argv": [sys.executable, "-I", "-c", "print('discard-failed-cleanup-output')"], "timeout": 8})
            self.assertFalse(result.ok)
            self.assertNotIn("discard-failed-cleanup-output", result.content)
            self.assertEqual(result.meta.get("error"), "resource_cleanup_failed")
            self.assertEqual(result.meta["resource_receipt"]["terminal"], "cleanup_failed")
            self.assertIsNone(result.meta["payload_started"])
