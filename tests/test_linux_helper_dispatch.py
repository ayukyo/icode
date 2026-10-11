from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
import hashlib
import errno
import os
from pathlib import Path
import shutil
import socket
import sys
import unittest
from unittest import mock

from tests._support import temp_workspace
from icode.isolation import LandlockSandbox, PreparedCommand
from icode import execution_broker as broker
from icode.linux_helper_object import LinuxHelperObjectError, open_linux_helper_object
from icode.linux_task_scope import LinuxTaskScope
from icode.sandbox_policy import NetworkMode, SandboxPolicy

REAL_CLOSE = os.close


class TestInstalledProbeRecordPublishing(unittest.TestCase):
    def test_public_context_labels_are_bounded_and_survive_publication(self):
        import contextlib
        import importlib.util
        import io
        import json
        source = Path(__file__).resolve().parents[1] / 'scripts/run_native_wheel_ci.py'
        spec = importlib.util.spec_from_file_location('native_wheel_ci_context_labels_test', source)
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
        raw = {'architecture': 'x86_64', 'topology': 'scope', 'consumer': 'context',
               'public_entry': 'resource', 'context_borrowed': True}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            subject._publish_helper_dispatch_records(json.dumps(raw))
        prefix = 'helper-dispatch-record '
        self.assertTrue(output.getvalue().startswith(prefix))
        published = json.loads(output.getvalue()[len(prefix):])
        for name in ('consumer', 'public_entry', 'context_borrowed'):
            self.assertIn(name, published)
        self.assertEqual(published['consumer'], 'context')
        self.assertEqual(published['public_entry'], 'resource')
        self.assertIs(published['context_borrowed'], True)
        raw.update(consumer='PRIVATE-PATH', public_entry='PRIVATE-COMMAND', context_borrowed='true')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            subject._publish_helper_dispatch_records(json.dumps(raw))
        self.assertNotIn('PRIVATE', output.getvalue())
        published = json.loads(output.getvalue()[len(prefix):])
        for name in ('consumer', 'public_entry', 'context_borrowed'):
            self.assertNotIn(name, published)

    def test_new_stage_launch_error_has_fixed_diagnostic(self):
        import contextlib
        import importlib.util
        import io
        source = Path(__file__).resolve().parents[1] / 'scripts/run_native_wheel_ci.py'
        spec = importlib.util.spec_from_file_location('native_wheel_ci_dispatch_launch_test', source)
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
        output = io.StringIO()
        with mock.patch.object(subject.subprocess, 'run', side_effect=OSError('PRIVATE-ERROR')), contextlib.redirect_stdout(output):
            _, error = capture(lambda: subject._run('probe installed Linux helper same-object dispatch',
                ['/PRIVATE-COMMAND'], cwd=Path('/'), publish_output=True))
        self.assertIsInstance(error, RuntimeError)
        self.assertNotIn('PRIVATE', output.getvalue() + str(error))
        self.assertIn('helper_dispatch_probe_launch_failed', str(error))

    def test_new_stage_timeout_publishes_partial_records_without_raw_command(self):
        import contextlib
        import importlib.util
        import io
        import json
        import subprocess
        source = Path(__file__).resolve().parents[1] / 'scripts/run_native_wheel_ci.py'
        spec = importlib.util.spec_from_file_location('native_wheel_ci_dispatch_timeout_test', source)
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
        raw = json.dumps({'architecture': 'x86_64', 'topology': 'scope', 'error': 'timeout'})
        failure = subprocess.TimeoutExpired(['/PRIVATE-COMMAND'], 600,
            output=raw.encode(), stderr=b'PRIVATE-STDERR-SENTINEL')
        output = io.StringIO()
        with mock.patch.object(subject.subprocess, 'run', side_effect=failure), contextlib.redirect_stdout(output):
            _, error = capture(lambda: subject._run('probe installed Linux helper same-object dispatch',
                ['/PRIVATE-COMMAND'], cwd=Path('/'), publish_output=True, timeout_seconds=600))
        self.assertIsInstance(error, RuntimeError)
        self.assertIn('helper-dispatch-record', output.getvalue())
        self.assertNotIn('PRIVATE', output.getvalue() + str(error))
        self.assertIn('helper_dispatch_probe_timeout', str(error))

    def test_failed_new_stage_publishes_safe_json_before_fixed_failure(self):
        import contextlib
        import importlib.util
        import io
        import json
        import subprocess
        source = Path(__file__).resolve().parents[1] / 'scripts/run_native_wheel_ci.py'
        spec = importlib.util.spec_from_file_location('native_wheel_ci_dispatch_test', source)
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
        record = {'architecture': 'x86_64', 'topology': 'no-scope', 'mutation': 'none',
                  'observations': [['payload-ready-before-release', 'fail']], 'error': None,
                  'ignored_payload': 'PRIVATE-PAYLOAD-SENTINEL'}
        completed = subprocess.CompletedProcess([], 1, stdout=json.dumps(record) + '\nPRIVATE-PAYLOAD-SENTINEL\n',
                                                stderr='PRIVATE-STDERR-SENTINEL')
        output = io.StringIO()
        with mock.patch.object(subject.subprocess, 'run', return_value=completed), contextlib.redirect_stdout(output):
            result, error = capture(lambda: subject._run('probe installed Linux helper same-object dispatch',
                ['fixed-program'], cwd=Path('/'), publish_output=True))
        self.assertIsNone(result)
        self.assertIsInstance(error, RuntimeError)
        self.assertIn('helper-dispatch-record', output.getvalue())
        self.assertIn('"fail"', output.getvalue())
        self.assertNotIn('PRIVATE-PAYLOAD-SENTINEL', output.getvalue() + str(error))
        self.assertNotIn('PRIVATE-STDERR-SENTINEL', output.getvalue() + str(error))
        self.assertIn('helper_dispatch_probe_failed', str(error))


def policy_for(root):
    return SandboxPolicy(1, 'dispatch', 'dispatch', 'code', root, (root,), (root,), (), (), NetworkMode.DENY, (), 8, 8, 2048, ())


def pair(root):
    source = Path('/usr/bin/true').resolve(strict=True)
    binary = root / 'helper'
    shutil.copyfile(source, binary)
    binary.chmod(0o700)
    manifest = root / 'helper.sha256'
    manifest.write_text(hashlib.sha256(binary.read_bytes()).hexdigest() + '\n', encoding='ascii')
    return binary, manifest


def capture(call):
    try:
        return call(), None
    except BaseException as error:
        return None, error


def cleanup_test_channels(channels):
    for channel in channels:
        descriptor = getattr(channel, "original_fd", None)
        if descriptor is None:
            socket.socket.close(channel)
            continue
        # Fault fixtures retain the original FD even after broker detachment.
        socket.socket.detach(channel)
        try:
            REAL_CLOSE(descriptor)
        except OSError as error:
            if error.errno != errno.EBADF: raise


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux real-FD software contract')
class TestHeldWrappers(unittest.TestCase):
    def test_held_wrappers_preserve_workspace_resource_scope_after_unlink(self):
        with temp_workspace() as raw, ExitStack() as stack:
            root = raw.resolve()
            binary, manifest = pair(root)
            owner = stack.enter_context(open_linux_helper_object(binary, manifest))
            helper_fd = owner.fileno()
            workspace_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            stack.callback(REAL_CLOSE, workspace_fd)
            status = os.fstat(workspace_fd)
            identity = (status.st_dev, status.st_ino)
            endpoints = [socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET) for _ in range(2)]
            for endpoints_pair in endpoints:
                for endpoint in endpoints_pair:
                    stack.callback(endpoint.close)
            control, resource = endpoints[0][1], endpoints[1][1]
            binary.unlink()
            manifest.unlink()
            sandbox = LandlockSandbox(str(binary), manifest=str(manifest))
            with mock.patch('icode.native_helper.verify_native_helper', side_effect=AssertionError('path reopened')):
                wrapped, error = capture(lambda: sandbox.wrap_policy_with_resource_receipt(
                    ['/usr/bin/true', '--', 'literal'], policy=policy_for(root),
                    control_socket=control, resource_socket=resource,
                    unit='icode-task-0123456789abcdef0123456789abcdef.scope',
                    workspace_fd=workspace_fd, workspace_identity=identity, helper_object=owner))
            self.assertIsNone(error, 'held branch must work without pathname selection')
            self.assertIs(wrapped.helper_object, owner)
            self.assertEqual(wrapped[0], f'/proc/self/fd/{helper_fd}')
            self.assertEqual(wrapped.pass_fds, (helper_fd, workspace_fd))
            self.assertEqual(wrapped.cwd, '/')
            scope = object.__new__(LinuxTaskScope)
            scope.version, scope.unit = 254, 'icode-task-0123456789abcdef0123456789abcdef.scope'
            scoped = scope.wrap(wrapped)
            self.assertIs(scoped.helper_object, owner)
            self.assertEqual(scoped.pass_fds, wrapped.pass_fds)
            self.assertEqual(scoped.cwd, '/')
            self.assertEqual(scoped[scoped.index('--') + 1], wrapped[0])
            self.assertEqual(os.fstat(helper_fd).st_ino, owner._identity[1])
            self.assertTrue(os.fstat(workspace_fd))

    def test_held_policy_validation_still_rejects_unexpressible_policy(self):
        with temp_workspace() as raw:
            root = raw.resolve()
            binary, manifest = pair(root)
            with open_linux_helper_object(binary, manifest) as owner:
                host, control = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                try:
                    changed = replace(policy_for(root), write_roots=(root / 'nested',))
                    with self.assertRaises(ValueError):
                        LandlockSandbox(str(binary), manifest=str(manifest)).wrap_policy_with_violation_receipt(
                            ['true'], policy=changed, control_socket=control, helper_object=owner)
                finally:
                    host.close()
                    control.close()

    def test_old_prepared_command_defaults_to_no_helper_binding(self):
        self.assertIsNone(PreparedCommand(['true'], pass_fds=(), cwd='/').helper_object)

class Monitor:
    def __init__(self, host):
        self.host, self._started, self.failed = host, True, False
        self.closes = 0
    def close(self):
        self.closes += 1
        return True
    def receipt(self):
        return None
    def bind_process(self, process): pass
    def start(self, **kwargs): self._started = True
    def abort(self): self.failed = True

class Scope:
    version = 254
    unit = "icode-task-0123456789abcdef0123456789abcdef.scope"
    environment = {"XDG_RUNTIME_DIR": "/run/user/1000", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"}
    cleanup_state = "confirmed"
    def __init__(self): self.closed = 0
    def wrap(self, helper): return LinuxTaskScope.wrap(self, helper)
    def collected(self, deadline): return True
    def close(self): self.closed += 1
    def bind_process(self, pid): pass

class Resource:
    def __init__(self): self.closed = 0
    def wait(self, **kwargs): return True
    def close(self): self.closed += 1; return True
    def receipt(self):
        return {"channel_status": "complete", "payload_started": None, "terminal": "finished"}
    def bind_process(self, process, **kwargs): pass
    def start(self, **kwargs): pass

@unittest.skipUnless(sys.platform.startswith("linux"), "Linux real-FD broker software contract")
class TestDispatchOwner(unittest.TestCase):
    def exercise(self, root, *, mutate=None, fault=None, timeout=1, close_fault=None,
                 wrapper_fault=None, monitor_fault=None,
                 resource_mode=False, scope_fault=None, receiver_fault=None, mutate_roles=None,
                 cleanup_stage=None, cleanup_fault=None, output_limit_bytes=None, workspace_fd=None,
                 endpoint_fault=None, scope_state="confirmed", on_spawn=False,
                 scope_prefix_mutation=None, preparation_fault=None, public=False, legacy=False):
        binary, manifest = pair(root)
        owners, closes, launches, channels = [], [], [], []
        real_factory = open_linux_helper_object
        def factory(*args):
            owner = real_factory(*args)
            descriptor = owner.fileno()
            owners.append((owner, descriptor))
            real_close = owner.close
            def close():
                closes.append(descriptor)
                real_close()
                if close_fault is not None:
                    raise close_fault
            owner.close = close
            return owner
        def channel():
            if preparation_fault == "resource_channel" and not channels:
                raise RuntimeError("private preparation")
            if preparation_fault == "control_channel" and (not resource_mode or channels):
                raise RuntimeError("private preparation")
            host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            if endpoint_fault is not None and not channels:
                class UnknownHost(socket.socket):
                    attempts = 0
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.original_fd = self.fileno()
                    def close(self):
                        self.attempts += 1
                        raise endpoint_fault  # Before real close: socket stays live.
                if on_spawn:
                    sender = UnknownHost(fileno=sender.detach())
                else:
                    host = UnknownHost(fileno=host.detach())
            answer = (host, sender)
            channels.extend(answer)
            return answer
        task_scope, receiver = Scope(), Resource()
        task_scope.cleanup_state = scope_state
        if cleanup_stage in ("resource_close", "scope_close", "scope_collected"):
            target, attribute = ((receiver, "close") if cleanup_stage == "resource_close" else
                                 (task_scope, "close" if cleanup_stage == "scope_close" else "collected"))
            real_operation = getattr(target, attribute)
            def cleanup(*args, **kwargs):
                real_operation(*args, **kwargs)
                raise cleanup_fault
            setattr(target, attribute, cleanup)
        def monitor(host):
            if monitor_fault is not None: raise monitor_fault
            value = Monitor(host)
            if cleanup_stage == "monitor_close":
                original_close = value.close
                def close():
                    original_close(); raise cleanup_fault
                value.close = close
            return value
        def scoped(helper):
            if scope_fault is not None: raise scope_fault
            wrapped = Scope.wrap(task_scope, helper)
            if scope_prefix_mutation is not None: scope_prefix_mutation(wrapped)
            return wrapped
        task_scope.wrap = scoped
        def wrapper(argv, sender, *resource_args, helper_object=None):
            if wrapper_fault is not None:
                raise wrapper_fault
            if helper_object is None:
                return PreparedCommand(["/usr/bin/true"], pass_fds=(), cwd=str(root),
                                       helper_object=object())
            sandbox = LandlockSandbox(str(binary), manifest=str(manifest))
            workspace_identity = None
            if workspace_fd is not None:
                pinned = os.fstat(workspace_fd)
                workspace_identity = (pinned.st_dev, pinned.st_ino)
            workspace_binding = dict(workspace_fd=workspace_fd, workspace_identity=workspace_identity)
            if resource_args:
                # The fault override belongs to cleanup, after the real wrapper
                # has checked its ordinary socket type. Borrow the same live FD.
                resource_socket = resource_args[0]
                borrowed = None
                if on_spawn and type(resource_socket) is not socket.socket:
                    borrowed = socket.socket(fileno=resource_socket.fileno())
                    resource_socket = borrowed
                try:
                    prepared = sandbox.wrap_policy_with_resource_receipt(argv, policy=policy_for(root), control_socket=sender,
                        resource_socket=resource_socket, unit=resource_args[1], helper_object=helper_object, **workspace_binding)
                finally:
                    if borrowed is not None: borrowed.detach()
            else:
                prepared = sandbox.wrap_policy_with_violation_receipt(argv, policy=policy_for(root), control_socket=sender,
                    helper_object=helper_object, **workspace_binding)
            if mutate_roles is not None:
                mutate_roles(prepared, helper_object, sender, resource_args)
            if mutate is not None:
                mutate(prepared, helper_object)
            return prepared
        actual_core = broker._execute_policy_command
        def run(argv, **kwargs):
            if timeout != 1 or output_limit_bytes is not None:
                return actual_core(argv, **kwargs)
            hook = kwargs.get("before_spawn")
            if hook is not None:
                hook()
            launches.append((tuple(argv), kwargs["pass_fds"]))
            if on_spawn:
                try:
                    kwargs["on_spawn"](type("Process", (), {"pid": os.getpid()})(), 9999999999)
                except Exception:
                    return broker.ExecutionResult(None, "", 0, "proxy_setup_failed", False, True, None)
            if fault is not None:
                raise fault
            return broker.ExecutionResult(0, "software-contract", 17, None, False, True, None)
        with mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory), \
             mock.patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel", side_effect=channel), \
             mock.patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor",
                        side_effect=monitor), \
             mock.patch("icode.linux_task_scope.LinuxTaskScope",
                        **({"side_effect": RuntimeError("private constructor")} if preparation_fault == "scope_constructor"
                           else {"return_value": task_scope})), \
             mock.patch("icode.linux_task_resource.create_task_resource_channel", side_effect=channel), \
             mock.patch("icode.linux_task_resource.LinuxTaskResourceReceiver",
                        **({"side_effect": receiver_fault} if receiver_fault is not None else {"return_value": receiver})), \
             mock.patch.object(broker, "_execute_policy_command", side_effect=run):
            if legacy:
                entry = broker._execute_linux_observed_command
            elif public:
                entry = (broker.execute_linux_resource_observed_command if resource_mode
                         else broker.execute_linux_violation_observed_command)
            else:
                entry = broker._execute_linux_helper_observed_candidate
            arguments = dict(cwd=root, sandbox=LandlockSandbox(str(binary), manifest=str(manifest)),
                             policy=policy_for(root), timeout=timeout, command_wrapper=wrapper,
                             output_limit_bytes=output_limit_bytes)
            if legacy or not public:
                arguments["resource_mode"] = resource_mode
            result, error = capture(lambda: entry(["/usr/bin/true"], **arguments))
        self.last_scope, self.last_receiver = task_scope, receiver
        return result, error, owners, closes, launches, channels

    def assert_closed(self, fd):
        with self.assertRaises(OSError) as caught:
            os.fstat(fd)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_public_entries_own_and_launch_same_object(self):
        for resource_mode in (False, True):
            with self.subTest(resource_mode=resource_mode), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=resource_mode, public=True)
                self.assertIsNone(error)
                self.assertEqual(len(owners), 1)
                owner, fd = owners[0]
                self.assertIsNone(result.error)
                self.assertEqual(closes, [fd])
                self.assertEqual(len(launches), 1)
                self.assertIn(f"/proc/self/fd/{fd}", launches[0][0])
                self.assertIn(fd, launches[0][1])
                self.assertEqual(owner._state, "closed")
                self.assert_closed(fd)
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_public_first_signal_survives_owner_cleanup_fault(self):
        for resource_mode in (False, True):
            for first in (KeyboardInterrupt(), SystemExit(71)):
                with self.subTest(resource_mode=resource_mode, signal=type(first).__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), resource_mode=resource_mode, public=True,
                        fault=first, close_fault=LinuxHelperObjectError())
                    self.assertEqual(len(owners), 1)
                    self.assertIsNone(result)
                    self.assertIs(error, first)
                    self.assertEqual(closes, [owners[0][1]])
                    self.assertEqual(len(launches), 1)
                    self.assert_closed(owners[0][1])
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_public_faults_and_binding_rejection_keep_owner_cleanup(self):
        for resource_mode in (False, True):
            for stage in ("wrapper_fault", "monitor_fault", "fault"):
                for injected in (RuntimeError("fixed fault"), KeyboardInterrupt(), SystemExit(19)):
                    with self.subTest(resource_mode=resource_mode, stage=stage,
                                      fault=type(injected).__name__), temp_workspace() as raw:
                        result, error, owners, closes, launches, channels = self.exercise(
                            raw.resolve(), resource_mode=resource_mode, public=True, **{stage: injected})
                        self.assertEqual(len(owners), 1)
                        self.assertEqual(closes, [owners[0][1]])
                        self.assert_closed(owners[0][1])
                        self.assertEqual(len(launches), 1 if stage == "fault" else 0)
                        self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                        if not isinstance(injected, Exception) or stage == "fault":
                            self.assertIs(error, injected)
                        else:
                            self.assertIsNone(error)
                            self.assertEqual(result.error, "isolation_unavailable")
            def drop(prepared, owner): prepared.helper_object = None
            def swap(prepared, owner): prepared.helper_object = object()
            def duplicate(prepared, owner): prepared.pass_fds += prepared.pass_fds
            for mutation in (drop, swap, duplicate):
                with self.subTest(resource_mode=resource_mode, mutation=mutation.__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), resource_mode=resource_mode, public=True, mutate=mutation)
                    self.assertIsNone(error)
                    self.assertEqual(len(owners), 1)
                    self.assertEqual(result.error, "isolation_unavailable")
                    self.assertEqual(launches, [])
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_public_old_callback_never_retries_legacy_body(self):
        for resource_mode in (False, True):
            with self.subTest(resource_mode=resource_mode), temp_workspace() as raw:
                root = raw.resolve()
                binary, manifest = pair(root)
                body = []
                def old(argv, control, *resource_args):
                    body.append(True)
                    return argv
                entry = (broker.execute_linux_resource_observed_command if resource_mode
                         else broker.execute_linux_violation_observed_command)
                with mock.patch("icode.linux_helper_object.open_linux_helper_object",
                                wraps=open_linux_helper_object) as factory, \
                     mock.patch.object(broker.subprocess, "Popen") as started, \
                     mock.patch("icode.linux_task_scope.LinuxTaskScope", return_value=Scope()), \
                     mock.patch("icode.linux_task_resource.LinuxTaskResourceReceiver", return_value=Resource()):
                    result = entry(["/usr/bin/true"], cwd=root,
                        sandbox=LandlockSandbox(str(binary), manifest=str(manifest)),
                        policy=policy_for(root), timeout=1, command_wrapper=old)
                factory.assert_called_once()
                started.assert_not_called()
                self.assertEqual(body, [])
                self.assertEqual(result.error, "isolation_unavailable")
                self.assertIs(result.payload_started, False)

    def test_candidate_owns_once_and_launches_held_descriptor(self):
        with temp_workspace() as raw:
            result, error, owners, closes, launches, channels = self.exercise(raw.resolve())
            self.assertIsNone(error)
            self.assertIsNone(result.error, "candidate must dispatch rather than reject skeleton")
            self.assertEqual(len(owners), 1)
            owner, fd = owners[0]
            self.assertEqual(closes, [fd])
            self.assertEqual(launches[0][0][0], f"/proc/self/fd/{fd}")
            self.assertIn(fd, launches[0][1])
            self.assert_closed(fd)
            self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_preparation_constructor_and_channels_drain_the_acquired_owner(self):
        for stage in ("scope_constructor", "resource_channel", "control_channel"):
            with self.subTest(stage=stage), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=True, preparation_fault=stage)
                self.assertIsNone(error)
                self.assertEqual(result.error, "isolation_unavailable")
                self.assertIs(result.payload_started, False)
                self.assertEqual(launches, [])
                self.assertEqual(closes, [owners[0][1]])
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                if stage != "scope_constructor": self.assertEqual(self.last_scope.closed, 1)

    def test_candidate_rejects_changed_scope_prefix_before_monitor_or_launch(self):
        def missing_scope(wrapped): wrapped.remove("--scope")
        def changed_unit(wrapped):
            index = next(i for i, part in enumerate(wrapped) if part.startswith("--unit="))
            wrapped[index] = "--unit=foreign.scope"
        def changed_metadata(wrapped): wrapped.cwd = "/"
        for mutation in (missing_scope, changed_unit, changed_metadata):
            with self.subTest(mutation=mutation.__name__), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=True, scope_prefix_mutation=mutation)
                self.assertIsNone(error)
                self.assertEqual(result.error, "isolation_unavailable")
                self.assertIs(result.payload_started, False)
                self.assertEqual(launches, [])
                self.assertEqual(closes, [owners[0][1]])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_actual_candidate_invalid_handoff_remains_not_started(self):
        actual_check = broker._check_held_helper_launch
        for resource_mode in (False, True):
            with self.subTest(resource_mode=resource_mode), temp_workspace() as raw, \
                 mock.patch.object(broker.subprocess, "Popen") as popen, \
                 mock.patch.object(broker, "_check_held_helper_launch", wraps=actual_check) as check:
                def invalid_directory(prepared, owner):
                    prepared.cwd = str(raw / "absent")
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=resource_mode, timeout=2, mutate=invalid_directory)
                self.assertIsNone(error)
                self.assertEqual(result.error, "invalid_handoff")
                self.assertIs(result.payload_started, False)
                self.assertEqual(check.call_count, 1, "input validation must precede the final hook")
                popen.assert_not_called()
                self.assertEqual(closes, [owners[0][1]])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_endpoint_unknown_is_not_hidden_by_ordinary_process_core_error(self):
        with temp_workspace() as raw:
            channels = []
            try:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=True, fault=RuntimeError("ordinary core"),
                    endpoint_fault=OSError(errno.EIO, "before-close"))
                self.assertIsNone(result)
                self.assertIsInstance(error, LinuxHelperObjectError)
                self.assertEqual(channels[0].attempts, 1)
                self.assertTrue(os.fstat(channels[0].original_fd))
                self.assertTrue(all(channel.fileno() == -1 for channel in channels[1:]))
                self.assertEqual(closes, [owners[0][1]])
                self.assert_closed(owners[0][1])
            finally:
                cleanup_test_channels(channels)

    def test_on_spawn_unknown_sender_close_attempts_once_and_drains_other_components(self):
        for fault in (OSError(errno.EIO, "before-close"), KeyboardInterrupt(), SystemExit(61)):
            with self.subTest(fault=type(fault).__name__), temp_workspace() as raw:
                channels = []
                try:
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), resource_mode=True, endpoint_fault=fault, on_spawn=True)
                    self.assertIsNone(result)
                    if isinstance(fault, Exception):
                        self.assertIsInstance(error, LinuxHelperObjectError)
                    else:
                        self.assertIs(error, fault)
                    unknown = channels[1]
                    self.assertEqual(unknown.attempts, 1)
                    self.assertTrue(os.fstat(unknown.original_fd))
                    self.assertTrue(all(value.fileno() == -1 for value in channels if value is not unknown))
                    self.assertEqual(self.last_receiver.closed, 1)
                    self.assertEqual(self.last_scope.closed, 1)
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                finally:
                    cleanup_test_channels(channels)

    def test_ambiguous_endpoint_close_never_retries_through_garbage_collection(self):
        import gc
        import warnings
        for failure in (OSError(errno.EIO, "before-close"), KeyboardInterrupt(), SystemExit(73)):
            with self.subTest(failure=type(failure).__name__), temp_workspace() as raw:
                channels = []
                descriptor = -1
                try:
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), resource_mode=True, endpoint_fault=failure,
                        wrapper_fault=RuntimeError("ordinary wrapper"))
                    self.assertIsNone(result)
                    if isinstance(failure, Exception): self.assertIsInstance(error, LinuxHelperObjectError)
                    else: self.assertIs(error, failure)
                    unknown = channels[0]
                    descriptor = unknown.original_fd
                    self.assertEqual(unknown.attempts, 1)
                    self.assertTrue(os.fstat(descriptor))
                    # Clear exception chains holding close_endpoint frames and
                    # the owned socket, then drop the last fixture references.
                    pending = [error, failure]
                    seen = set()
                    while pending:
                        caught = pending.pop()
                        if caught is None or id(caught) in seen: continue
                        seen.add(id(caught))
                        pending.extend((caught.__context__, caught.__cause__))
                        caught.__traceback__ = None
                        caught.__context__ = caught.__cause__ = None
                    del caught, unknown, error
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", ResourceWarning)
                        channels.clear()
                        gc.collect()
                    _, descriptor_error = capture(lambda: os.fstat(descriptor))
                    self.assertIsNone(descriptor_error, "GC must not retry an ambiguous endpoint close")
                finally:
                    cleanup_test_channels(channels)
                    if descriptor >= 0:
                        try: REAL_CLOSE(descriptor)
                        except OSError: pass

    def test_dropped_swapped_alias_extra_and_payload_decoy_bindings_deny(self):
        def drop(prepared, owner): prepared.helper_object = None
        def swap(prepared, owner): prepared.helper_object = object()
        def duplicate(prepared, owner): prepared.pass_fds += prepared.pass_fds
        def extra(prepared, owner): prepared.pass_fds += (987654,)
        def payload_decoy(prepared, owner):
            prepared.extend([prepared[0]])
            prepared[0] = "/usr/bin/true"
        for mutate in (drop, swap, duplicate, extra, payload_decoy):
            with self.subTest(mutate=mutate.__name__), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(raw.resolve(), mutate=mutate)
                self.assertIsNone(error)
                self.assertEqual(result.error, "isolation_unavailable")
                self.assertEqual(launches, [])
                self.assertEqual(closes, [owners[0][1]])
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_private_legacy_observed_rejects_unexpected_binding_without_factory(self):
        with temp_workspace() as raw:
            result, error, owners, closes, launches, channels = self.exercise(raw.resolve(), legacy=True)
            self.assertIsNone(error)
            self.assertEqual(result.error, "isolation_unavailable")
            self.assertEqual((owners, closes, launches), ([], [], []))
            self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_owner_covers_wrapper_monitor_core_failure_and_signals(self):
        for key in ("wrapper_fault", "monitor_fault", "fault"):
            for injected in (RuntimeError("private detail"), KeyboardInterrupt(), SystemExit(19)):
                with self.subTest(stage=key, fault=type(injected).__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(raw.resolve(), **{key: injected})
                    self.assertEqual(len(owners), 1)
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                    if not isinstance(injected, Exception) or key == "fault":
                        self.assertIs(error, injected)
                    else:
                        self.assertIsNone(error)
                        self.assertEqual(result.error, "isolation_unavailable")

    def test_owner_close_unknown_never_returns_success_and_preserves_signal(self):
        for primary in (None, KeyboardInterrupt(), SystemExit(23)):
            with self.subTest(primary=type(primary).__name__), temp_workspace() as raw:
                failure = LinuxHelperObjectError()
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), fault=primary, close_fault=failure)
                self.assertIsNone(result)
                self.assertIs(error, primary if primary is not None else failure)
                self.assertEqual(closes, [owners[0][1]])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_unknown_owner_close_dominates_ordinary_core_failure_but_keeps_first_fixed_error(self):
        for primary in (RuntimeError("ordinary core"), LinuxHelperObjectError(), KeyboardInterrupt(), SystemExit(71)):
            with self.subTest(primary=type(primary).__name__), temp_workspace() as raw:
                cleanup = LinuxHelperObjectError()
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), fault=primary, close_fault=cleanup)
                self.assertIsNone(result)
                expected = cleanup if type(primary) is RuntimeError else primary
                self.assertIs(error, expected)
                self.assertEqual(closes, [owners[0][1]])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_final_live_channel_identity_denies_closed_detached_or_foreign_reuse(self):
        cases = ((resource_mode, mutation) for resource_mode in (False, True)
                 for mutation in ("closed", "detached", "raw-reused"))
        for resource_mode, mutation in cases:
            with self.subTest(resource_mode=resource_mode, mutation=mutation), temp_workspace() as raw:
                root = raw.resolve(); binary, manifest = pair(root)
                endpoints, owners, monitors, escaped = [], [], [], []
                real_environment = broker._policy_environment
                def factory(*args):
                    owner = open_linux_helper_object(*args)
                    owners.append((owner, owner.fileno()))
                    return owner
                def channel():
                    pair_value = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                    endpoints.extend(pair_value)
                    return pair_value
                def wrap(argv, control, *resource_args, helper_object):
                    sandbox = LandlockSandbox(str(binary), manifest=str(manifest))
                    if resource_args:
                        return sandbox.wrap_policy_with_resource_receipt(
                            argv, policy=policy_for(root), control_socket=control,
                            resource_socket=resource_args[0], unit=resource_args[1], helper_object=helper_object)
                    return sandbox.wrap_policy_with_violation_receipt(
                        argv, policy=policy_for(root), control_socket=control, helper_object=helper_object)
                def environment(*args, **kwargs):
                    result = real_environment(*args, **kwargs)
                    control = endpoints[1]
                    if mutation == "closed": control.close()
                    elif mutation == "detached": escaped.append(control.detach())
                    else:
                        descriptor = control.fileno()
                        REAL_CLOSE(descriptor)
                        foreign = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                        if foreign != descriptor:
                            os.dup2(foreign, descriptor); REAL_CLOSE(foreign)
                        escaped.append(descriptor)
                    return result
                def monitor(host):
                    value = Monitor(host); value._started = False
                    monitors.append(value)
                    return value
                try:
                    with mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory), \
                         mock.patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel", side_effect=channel), \
                         mock.patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor", side_effect=monitor), \
                         mock.patch("icode.linux_task_scope.LinuxTaskScope", return_value=Scope()), \
                         mock.patch("icode.linux_task_resource.create_task_resource_channel", side_effect=channel), \
                         mock.patch("icode.linux_task_resource.LinuxTaskResourceReceiver", return_value=Resource()), \
                         mock.patch.object(broker, "_policy_environment", side_effect=environment), \
                         mock.patch.object(broker.subprocess, "Popen", side_effect=RuntimeError("unexpected Popen")) as launched:
                        result, error = capture(lambda: broker._execute_linux_helper_observed_candidate(
                            ["true"], cwd=root, sandbox=LandlockSandbox(str(binary), manifest=str(manifest)),
                            policy=policy_for(root), timeout=1, resource_mode=resource_mode, command_wrapper=wrap))
                    self.assertEqual(launched.call_count, 0, "actual endpoint identity must be checked after environment")
                    if mutation == "closed":
                        self.assertIsNone(error)
                        self.assertEqual(result.error, "isolation_unavailable")
                        self.assertIs(result.payload_started, False)
                    else:
                        self.assertIsNone(result)
                        self.assertIsInstance(error, LinuxHelperObjectError)
                        self.assertTrue(os.fstat(escaped[0]), "broker must not close foreign or detached FD")
                        if mutation == "raw-reused":
                            import gc
                            self.assertEqual(endpoints[1].fileno(), -1, "stale socket must relinquish the foreign FD")
                            stale = endpoints.pop(1)
                            del stale
                            gc.collect()
                            self.assertTrue(os.fstat(escaped[0]), "GC must not close the reused foreign FD")
                    self.assertFalse(monitors[0]._started)
                    self.assertEqual(monitors[0].closes, 1)
                    self.assert_closed(owners[0][1])
                    self.assertEqual(endpoints[0].fileno(), -1)
                finally:
                    # Disarm the stale socket wrapper without closing a foreign FD.
                    if mutation == "raw-reused" and len(endpoints) == (4 if resource_mode else 2):
                        endpoints[1].detach()
                    for endpoint in endpoints: socket.socket.close(endpoint)
                    for descriptor in escaped:
                        try: REAL_CLOSE(descriptor)
                        except OSError: pass

    def test_unknown_live_close_does_not_retry_and_drains_all_other_resources(self):
        watched, attempts = [], []
        def remember(prepared, owner): watched.append(owner.fileno())
        def close(fd):
            if fd in watched:
                attempts.append(fd)
                raise OSError(errno.EIO, "before-close fault")
            return REAL_CLOSE(fd)
        with temp_workspace() as raw:
            try:
                with mock.patch("os.close", side_effect=close):
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), mutate=remember, resource_mode=True)
                self.assertIsNone(result)
                self.assertIsInstance(error, LinuxHelperObjectError)
                owner, fd = owners[0]
                self.assertEqual(owner._state, "unknown")
                self.assertTrue(os.fstat(fd), "fault occurred before actual close; FD must remain live")
                self.assertEqual(attempts, [fd])
                with self.assertRaises(LinuxHelperObjectError): owner.close()
                self.assertEqual(attempts, [fd])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                self.assertEqual(self.last_receiver.closed, 1)
                self.assertEqual(self.last_scope.closed, 1)
            finally:
                for fd in watched:
                    try: REAL_CLOSE(fd)
                    except OSError: pass

    def test_scope_and_receiver_construction_faults_drain_owner_and_channels(self):
        for stage in ("scope_fault", "receiver_fault", "monitor_fault"):
            for injected in (RuntimeError("private"), KeyboardInterrupt(), SystemExit(31)):
                with self.subTest(stage=stage, injected=type(injected).__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(
                        raw.resolve(), resource_mode=True, **{stage: injected})
                    self.assertEqual(launches, [])
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                    self.assertEqual(self.last_scope.closed, 1)
                    if stage == "monitor_fault": self.assertEqual(self.last_receiver.closed, 1)
                    if isinstance(injected, Exception):
                        self.assertIsNone(error); self.assertEqual(result.error, "isolation_unavailable")
                    else: self.assertIs(error, injected)

    def test_real_channel_aliases_and_scope_payload_decoy_never_launch(self):
        def alias_control(prepared, owner, control, args): prepared.pass_fds += (control.fileno(),)
        def alias_resource(prepared, owner, control, args): prepared.pass_fds += (args[0].fileno(),)
        def workspace_alias(prepared, owner, control, args):
            index = prepared.index("--")
            fd = control.fileno()
            prepared[index:index] = ["--workspace-object-fd", str(fd), "0", "1"]
            prepared.pass_fds += (fd,)
        def payload_decoy(prepared, owner, control, args):
            prepared.extend([prepared[0]]); prepared[0] = "/usr/bin/true"
        for mutate in (alias_control, alias_resource, workspace_alias, payload_decoy):
            with self.subTest(mutate=mutate.__name__), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=True, mutate_roles=mutate)
                self.assertIsNone(error); self.assertEqual(result.error, "isolation_unavailable")
                self.assertEqual(launches, [])
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_resource_cleanup_fault_attempts_remaining_resources_and_owner(self):
        for stage in ("resource_close", "monitor_close", "scope_collected", "scope_close"):
            for injected in (RuntimeError("private cleanup"), KeyboardInterrupt(), SystemExit(37)):
                with self.subTest(stage=stage, fault=type(injected).__name__), temp_workspace() as raw:
                    result, error, owners, closes, launches, channels = self.exercise(raw.resolve(),
                        resource_mode=True, cleanup_stage=stage, cleanup_fault=injected)
                    self.assertIsNone(result)
                    if stage == "scope_close" and isinstance(injected, Exception):
                        self.assertIsInstance(error, LinuxHelperObjectError)
                    else:
                        self.assertIs(error, injected)
                    self.assertEqual(closes, [owners[0][1]])
                    self.assert_closed(owners[0][1])
                    self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                    self.assertEqual(self.last_receiver.closed, 1)
                    self.assertEqual(self.last_scope.closed, 1)

    def test_live_endpoint_close_fault_is_not_hidden_by_ordinary_body_error(self):
        for body in (RuntimeError("private ordinary wrapper"), KeyboardInterrupt(), SystemExit(41)):
            for endpoint_error in (OSError(errno.EIO, "private before-close"), KeyboardInterrupt()):
                channels = []
                with self.subTest(body=type(body).__name__, cleanup=type(endpoint_error).__name__), temp_workspace() as raw:
                    try:
                        result, error, owners, closes, launches, channels = self.exercise(raw.resolve(),
                            resource_mode=True, wrapper_fault=body, endpoint_fault=endpoint_error)
                        self.assertIsNone(result)
                        if not isinstance(body, Exception):
                            self.assertIs(error, body)
                        elif not isinstance(endpoint_error, Exception):
                            self.assertIs(error, endpoint_error)
                        else:
                            self.assertIsInstance(error, LinuxHelperObjectError)
                            self.assertNotIn("private", str(error))
                        self.assertEqual(launches, [])
                        unknown = channels[0]
                        self.assertEqual(unknown.attempts, 1)
                        self.assertGreaterEqual(unknown.original_fd, 3)
                        self.assertEqual(unknown.fileno(), -1, "unknown is detached, not confirmed closed")
                        self.assertTrue(os.fstat(unknown.original_fd), "before-close socket must still be live")
                        self.assertTrue(all(channel.fileno() == -1 for channel in channels[1:]))
                        self.assertEqual(self.last_scope.closed, 1)
                        self.assertEqual(closes, [owners[0][1]])
                        self.assert_closed(owners[0][1])
                    finally:
                        # Bypass the faulting override; do not give cleanup credit.
                        cleanup_test_channels(channels)

    def test_owner_covers_actual_process_core_input_early_returns(self):
        for options, expected in (({"timeout": float("nan")}, "invalid_timeout"),
                                  ({"output_limit_bytes": 0}, "invalid_output_limit")):
            with self.subTest(expected=expected), temp_workspace() as raw, \
                 mock.patch.object(broker.subprocess, "Popen") as started:
                result, error, owners, closes, launches, channels = self.exercise(raw.resolve(), **options)
                self.assertIsNone(error); self.assertEqual(result.error, expected)
                started.assert_not_called()
                self.assertEqual(closes, [owners[0][1]])
                self.assert_closed(owners[0][1])
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))

    def test_each_dispatch_owner_closes_without_closing_session_workspace(self):
        with temp_workspace() as raw:
            root = raw.resolve()
            pinned = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                for number in range(2):
                    result, error, owners, closes, launches, channels = self.exercise(root, workspace_fd=pinned)
                    self.assertIsNone(error); self.assertIsNone(result.error)
                    self.assertEqual(len(owners), 1); self.assert_closed(owners[0][1])
                    self.assertIn(pinned, launches[0][1], "workspace must actually be borrowed by dispatch")
                    self.assertIn("--workspace-object-fd", launches[0][0])
                    self.assertTrue(os.fstat(pinned), f"dispatch {number} stole session workspace")
            finally:
                REAL_CLOSE(pinned)

    def test_candidate_rejects_unconfirmed_or_unknown_scope_after_all_attempts(self):
        for state in ("unconfirmed", "unknown"):
            with self.subTest(state=state), temp_workspace() as raw:
                result, error, owners, closes, launches, channels = self.exercise(
                    raw.resolve(), resource_mode=True, scope_state=state)
                self.assertIsNone(result); self.assertIsInstance(error, LinuxHelperObjectError)
                self.assertEqual(self.last_scope.closed, 1)
                self.assertEqual(self.last_receiver.closed, 1)
                self.assertTrue(all(channel.fileno() == -1 for channel in channels))
                self.assertEqual(closes, [owners[0][1]]); self.assert_closed(owners[0][1])

    def test_observed_final_hook_preserves_not_started_error_after_environment_mutation(self):
        for mutation in ("argv", "binding", "extra-fd", "cwd", "fd-type"):
            with self.subTest(mutation=mutation), temp_workspace() as raw:
                root = raw.resolve(); binary, manifest = pair(root)
                owners, prepared, endpoints = [], [], []
                real_factory = open_linux_helper_object
                real_environment = broker._policy_environment
                def factory(*args):
                    owner = real_factory(*args); owners.append((owner, owner.fileno())); return owner
                def channel():
                    pair_value = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                    endpoints.extend(pair_value); return pair_value
                def wrap(argv, control, *, helper_object):
                    value = LandlockSandbox(str(binary), manifest=str(manifest)).wrap_policy_with_violation_receipt(
                        argv, policy=policy_for(root), control_socket=control, helper_object=helper_object)
                    prepared.append(value); return value
                def environment(*args, **kwargs):
                    result = real_environment(*args, **kwargs)
                    if mutation == "argv": prepared[0][0] = "/usr/bin/true"
                    elif mutation == "binding": prepared[0].helper_object = None
                    elif mutation == "extra-fd": prepared[0].pass_fds += (987654,)
                    elif mutation == "cwd": prepared[0].cwd = "/"
                    else: prepared[0].pass_fds = tuple(float(fd) for fd in prepared[0].pass_fds)
                    return result
                def monitor(host):
                    value = Monitor(host); value._started = False; return value
                with mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory), \
                     mock.patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel", side_effect=channel), \
                     mock.patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor", side_effect=monitor), \
                     mock.patch.object(broker, "_policy_environment", side_effect=environment), \
                     mock.patch.object(broker.subprocess, "Popen", side_effect=RuntimeError("unexpected launch")) as start:
                    result, error = capture(lambda: broker._execute_linux_helper_observed_candidate(["true"], cwd=root,
                        sandbox=LandlockSandbox(str(binary), manifest=str(manifest)), policy=policy_for(root),
                        timeout=1, resource_mode=False, command_wrapper=wrap))
                self.assertIsNone(error, "final metadata change must deny before Popen")
                start.assert_not_called()
                self.assertEqual(result.error, "isolation_unavailable")
                self.assertIs(result.payload_started, False)
                self.assertEqual(result.violation_observer_status, "incomplete")
                self.assertEqual(len(owners), 1); self.assert_closed(owners[0][1])
                self.assertTrue(all(endpoint.fileno() == -1 for endpoint in endpoints))

@unittest.skipUnless(os.name == "posix", "POSIX process core launch contract")
class TestFinalLaunchContract(unittest.TestCase):
    def test_final_check_follows_environment_and_denies_before_popen(self):
        with temp_workspace() as raw:
            root = raw.resolve()
            events = []
            def environment(*args, **kwargs):
                events.append("environment"); return {}
            def check():
                events.append("check"); raise ValueError("private final detail")
            with mock.patch.object(broker, "_policy_environment", side_effect=environment), \
                 mock.patch.object(broker.subprocess, "Popen") as launched:
                answer = broker._execute_policy_command(["/usr/bin/true"], cwd=root,
                    policy=policy_for(root), timeout=1, before_spawn=check)
            self.assertEqual(events, ["environment", "check"])
            self.assertEqual(answer.error, "isolation_unavailable")
            self.assertIs(answer.payload_started, False)
            launched.assert_not_called()

    def test_input_early_returns_are_real_and_never_call_final_hook(self):
        with temp_workspace() as raw:
            root = raw.resolve()
            for override, expected in (({"timeout": float("nan")}, "invalid_timeout"),
                                       ({"output_limit_bytes": 0}, "invalid_output_limit"),
                                       ({"pass_fds": (True,)}, "invalid_handoff")):
                with self.subTest(expected=expected), mock.patch.object(broker.subprocess, "Popen") as launch:
                    hook = mock.Mock()
                    options = dict(cwd=root, policy=policy_for(root), timeout=1, before_spawn=hook)
                    options.update(override)
                    result = broker._execute_policy_command(["/usr/bin/true"], **options)
                    self.assertEqual(result.error, expected)
                    hook.assert_not_called(); launch.assert_not_called()

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux real FD reuse")
    def test_dead_or_reused_owner_never_closes_foreign_descriptor(self):
        for reuse in (False, True):
            with self.subTest(reuse=reuse), temp_workspace() as raw:
                root = raw.resolve(); binary, manifest = pair(root)
                owner = open_linux_helper_object(binary, manifest)
                fd = owner.fileno(); REAL_CLOSE(fd)
                foreign = -1
                try:
                    if reuse:
                        foreign = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                        if foreign != fd:
                            os.dup2(foreign, fd); REAL_CLOSE(foreign); foreign = fd
                    with self.assertRaises(LinuxHelperObjectError): owner.fileno()
                    with self.assertRaises(LinuxHelperObjectError): owner.close()
                    with self.assertRaises(LinuxHelperObjectError): owner.close()
                    if reuse: self.assertTrue(os.fstat(fd))
                finally:
                    if foreign >= 0: REAL_CLOSE(foreign)

class TestScopeCleanupEvidence(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "real collected recheck directory FD")
    def test_collected_temporary_before_close_failure_remains_unknown(self):
        import threading
        import time
        with temp_workspace() as raw:
            scope = object.__new__(LinuxTaskScope)
            scope._fds = []
            scope.uid = os.getuid()
            scope._owned, scope._path = True, raw
            scope._invocation = "0123456789abcdef0123456789abcdef"
            scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
            scope._show = lambda deadline: {"LoadState": "loaded", "InvocationID": scope._invocation}
            fd = os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            attempts = []
            def close(descriptor):
                attempts.append(descriptor)
                raise OSError(errno.EIO, "before-close")
            try:
                with mock.patch("icode.linux_task_scope._open_directory", return_value=fd), \
                     mock.patch("icode.linux_task_scope.os.close", side_effect=close):
                    self.assertIsNone(scope.collected(time.monotonic() + 1))
                self.assertEqual(attempts, [fd])
                self.assertTrue(os.fstat(fd))
                self.assertEqual(scope.cleanup_state, "unknown")
                scope.close()
                self.assertTrue(os.fstat(fd))
                self.assertEqual(scope.cleanup_state, "unknown")
            finally:
                REAL_CLOSE(fd)

    @unittest.skipUnless(sys.platform.startswith("linux"), "real FD cleanup signal priority")
    def test_scope_keeps_first_signal_while_draining_every_owned_fd(self):
        import threading
        for stage in ("configure_locked", "configured", "collected"):
            for first in (KeyboardInterrupt(), SystemExit(51)):
                with self.subTest(stage=stage, first=type(first).__name__), temp_workspace() as raw:
                    scope = object.__new__(LinuxTaskScope)
                    scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
                    scope._fds, scope._identities = [], []
                    scope.uid = os.getuid()
                    fd = os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                    attempts = []
                    following = SystemExit(52) if isinstance(first, KeyboardInterrupt) else KeyboardInterrupt()
                    def close(descriptor):
                        attempts.append(descriptor)
                        REAL_CLOSE(descriptor)
                        raise following
                    def fail(deadline):
                        scope._close_requested.set()
                        raise first
                    try:
                        with mock.patch("icode.linux_task_scope.os.close", side_effect=close):
                            if stage == "configure_locked":
                                scope._membership = lambda: "/icode-task/supervisor"
                                with mock.patch("icode.linux_task_scope._open_directory", return_value=fd), \
                                     mock.patch("icode.linux_task_scope.os.fstat", side_effect=first):
                                    _, error = capture(lambda: scope.configured(0))
                            else:
                                scope._fds = [fd]
                                setattr(scope, "_configure_locked" if stage == "configured" else "_collect_locked", fail)
                                _, error = capture(lambda: (scope.configured if stage == "configured" else scope.collected)(0))
                        self.assertIs(error, first)
                        self.assertEqual(attempts, [fd])
                        self.assertEqual(scope.cleanup_state, "unknown")
                        with self.assertRaises(OSError): os.fstat(fd)
                    finally:
                        try: REAL_CLOSE(fd)
                        except OSError: pass

    @unittest.skipUnless(sys.platform.startswith("linux"), "real Linux directory descriptors")
    def test_partial_before_close_failure_stays_unknown_and_never_retries(self):
        import threading
        with temp_workspace() as raw:
            scope = object.__new__(LinuxTaskScope)
            scope._fds = [os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC) for _ in range(3)]
            scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
            descriptors = list(scope._fds); watched = descriptors[-1]; attempted = []
            def close(fd):
                attempted.append(fd)
                if fd == watched: raise OSError(errno.EIO, "before-close")
                REAL_CLOSE(fd)
            try:
                with mock.patch("icode.linux_task_scope.os.close", side_effect=close): scope.close()
                self.assertEqual(set(attempted), set(descriptors))
                self.assertTrue(os.fstat(watched)); self.assertEqual(scope.cleanup_state, "unknown")
                for fd in descriptors[:-1]:
                    with self.assertRaises(OSError): os.fstat(fd)
                scope.close(); self.assertEqual(len(attempted), 3)
                self.assertEqual(scope.cleanup_state, "unknown")
            finally:
                for fd in descriptors:
                    try: REAL_CLOSE(fd)
                    except OSError: pass

    @unittest.skipUnless(sys.platform.startswith("linux"), "real Linux deferred directory close")
    def test_active_callback_close_is_unconfirmed_then_confirmed_or_sticky_unknown(self):
        import threading
        for fault in (None, KeyboardInterrupt(), SystemExit(43)):
            with self.subTest(fault=type(fault).__name__), temp_workspace() as raw:
                scope = object.__new__(LinuxTaskScope)
                scope._fds = [os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)]
                scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
                scope._owned = False
                descriptor = scope._fds[0]; entered, release = threading.Event(), threading.Event()
                caught = []
                def callback(deadline):
                    entered.set()
                    if not release.wait(1): raise RuntimeError("bounded callback expired")
                    scope._owned = True
                scope._configure_locked = callback
                def close(fd):
                    REAL_CLOSE(fd)
                    if fd == descriptor and fault is not None: raise fault
                def run():
                    try: scope.configured(0)
                    except BaseException as error: caught.append(error)
                try:
                    with mock.patch("icode.linux_task_scope.os.close", side_effect=close):
                        worker = threading.Thread(target=run); worker.start()
                        self.assertTrue(entered.wait(1)); scope.close()
                        self.assertEqual(scope.cleanup_state, "unconfirmed")
                        self.assertTrue(os.fstat(descriptor)); release.set(); worker.join(2)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(scope.cleanup_state, "confirmed" if fault is None else "unknown")
                    if fault is not None: self.assertIs(caught[0], fault)
                    with self.assertRaises(OSError): os.fstat(descriptor)
                finally:
                    release.set()
                    try: REAL_CLOSE(descriptor)
                    except OSError: pass

    @unittest.skipUnless(sys.platform.startswith("linux"), "configured failure owns a real directory FD")
    def test_configured_failure_drain_keeps_unknown_evidence(self):
        import threading
        from icode.linux_task_scope import LinuxTaskScopeError
        with temp_workspace() as raw:
            scope = object.__new__(LinuxTaskScope)
            scope._fds, scope._identities = [], []
            scope.uid = os.getuid()
            scope._lifecycle, scope._close_requested = threading.Lock(), threading.Event()
            scope._membership = lambda: "/icode-task/supervisor"
            fd = os.open(raw, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                with mock.patch("icode.linux_task_scope._open_directory", return_value=fd), \
                     mock.patch("icode.linux_task_scope.os.fstat", side_effect=LinuxTaskScopeError()), \
                     mock.patch("icode.linux_task_scope.os.close", side_effect=OSError(errno.EIO, "before-close")):
                    with self.assertRaises(LinuxTaskScopeError): scope.configured(0)
                self.assertTrue(os.fstat(fd)); self.assertEqual(scope._fds, [])
                self.assertEqual(scope.cleanup_state, "unknown")
                scope.close(); self.assertTrue(os.fstat(fd))
            finally: REAL_CLOSE(fd)
