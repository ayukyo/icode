"""Real installed-wheel dispatch evidence; unavailable native evidence never passes."""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from icode import execution_broker as broker
from icode.isolation import LandlockSandbox
from icode.linux_helper_object import LinuxHelperObject, open_linux_helper_object
from icode.linux_task_scope import LinuxTaskScope
from icode.native_helper import linux_arch_from_machine, linux_elf_architecture
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.tools.base import ToolContext
from icode.workspace import WorkspaceManager

@contextmanager
def temp_workspace():
    with tempfile.TemporaryDirectory(prefix="icode-installed-dispatch-") as raw:
        yield Path(raw)

def policy_for(root):
    return SandboxPolicy(1, "dispatch", "dispatch", "code", root, (root,),
                         (root,), (), (), NetworkMode.DENY, (), 8, 8, 2048, ())

def stat_identity(directory):
    descriptor = os.open("stat", os.O_RDONLY | os.O_CLOEXEC, dir_fd=directory)
    try:
        raw = os.read(descriptor, 8192)
    finally:
        os.close(descriptor)
    close = raw.rfind(b")")
    if close < 0: raise ValueError("proc stat unavailable")
    fields = raw[close + 2:].split()
    # fields[0] is field 3 (state); fields[19] is field 22 (starttime).
    if len(fields) < 20 or fields[0] in (b"Z", b"X", b"x"):
        raise ProcessLookupError("not live")
    return fields[19]

def running_identity(process, directory, expected, deadline):
    try:
        if time.monotonic() >= deadline or process.poll() is not None:
            return "inconclusive"
        before = stat_identity(directory)
        executable = os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=directory)
        try:
            current = os.fstat(executable)
        finally:
            os.close(executable)
        after = stat_identity(directory)
        if before != after or process.poll() is not None or time.monotonic() >= deadline:
            return "inconclusive"
        return "pass" if (current.st_dev, current.st_ino) == expected else "fail"
    except (OSError, ValueError):
        return "inconclusive"


def descriptor_closed(fd):
    """A detached socket is not evidence of a closed kernel descriptor."""
    try:
        os.fstat(fd)
    except OSError as error:
        return error.errno == errno.EBADF
    return False


def descriptor_identity(fd):
    status = os.fstat(fd)
    return status.st_dev, status.st_ino


def probe_workspace(root, stack, consumer):
    if consumer == "candidate":
        workspace = root / "workspace"
        workspace.mkdir()
        fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        stack.callback(os.close, fd)
        return workspace, fd, descriptor_identity(fd), None
    if consumer != "context":
        raise ValueError("unsupported probe consumer")
    source = root / "source"
    source.mkdir()
    (source / "source.txt").write_text("probe\n", encoding="ascii")
    for arguments in (["init", "-q"], ["add", "source.txt"],
                      ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(source), *arguments], check=True,
                       capture_output=True, timeout=15)
    session = stack.enter_context(WorkspaceManager(
        source, root / "data", "installed-public", isolate_git_metadata=True,
    ).open("public-ticket", "public-run"))
    fd, identity = session.workspace_fd, session.workspace_fd_identity
    if type(fd) is not int or identity is None or descriptor_identity(fd) != identity:
        raise RuntimeError("live session workspace identity unavailable")
    return session.workspace_root, fd, identity, session


def observed_entry(resource_mode, consumer):
    if consumer == "candidate":
        return broker._execute_linux_helper_observed_candidate, {"resource_mode": resource_mode}
    if consumer == "context":
        return (broker.execute_linux_resource_observed_command if resource_mode
                else broker.execute_linux_violation_observed_command), {}
    raise ValueError("unsupported probe consumer")


def cleanup_descriptor(fd, identity, real_close):
    """Clean a fixture residual only when it is still the captured object."""
    try:
        if descriptor_identity(fd) == identity:
            real_close(fd)
    except OSError:
        pass


def cleanup_process(process):
    """Last-resort fixture cleanup, after broker terminal evidence is read."""
    if process.returncode is None:
        broker._stop_group(process)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()


@contextmanager
def observe_channel_closes(endpoints):
    """Record EBADF at real close, before later scope opens reuse the number.

    The terminal socket must also be disarmed. Detachment alone never adds
    evidence, and fixture cleanup runs after the caller has taken its snapshot.
    """
    closed = set()
    real_close = socket.socket.close
    def close(endpoint):
        snapshot = next((item for item in endpoints if item[0] is endpoint), None)
        matches = snapshot is not None and endpoint.fileno() == snapshot[1]
        if matches:
            matches = descriptor_identity(snapshot[1]) == snapshot[2]
        result = real_close(endpoint)
        if matches and descriptor_closed(snapshot[1]):
            closed.add(id(endpoint))
        return result
    with mock.patch.object(socket.socket, 'close', new=close):
        yield closed


def channels_confirmed_closed(endpoints, closed):
    return all(id(endpoint) in closed and endpoint.fileno() == -1 for endpoint, _, _ in endpoints)

@unittest.skipUnless(sys.platform.startswith("linux"), "Linux installed-package native gate")
class TestInstalledHelperDispatch(unittest.TestCase):
    def probe(self, resource_mode, mutation, consumer="candidate"):
        installed = LandlockSandbox.from_bundle()
        if installed is None:
            self.skipTest("inconclusive: real installed helper package unavailable; no native credit")
        source, manifest_source = Path(installed.helper), Path(installed.manifest)
        architecture = linux_arch_from_machine(platform.machine())
        self.assertEqual(linux_elf_architecture(source.read_bytes()[:64]), architecture)
        compiler = shutil.which("cc")
        if compiler is None:
            self.skipTest("inconclusive: native payload compiler unavailable; no native credit")
        if resource_mode and (os.getuid() == 0 or not Path(f"/run/user/{os.getuid()}/bus").exists()):
            self.skipTest("inconclusive: non-root user manager unavailable; no scope credit")
        with temp_workspace() as raw, ExitStack() as stack:
            root = raw.resolve()
            workspace, workspace_fd, workspace_identity, session = probe_workspace(root, stack, consumer)
            helper, manifest = root / "helper", root / "helper.sha256"
            shutil.copyfile(source, helper); helper.chmod(0o700)
            shutil.copyfile(manifest_source, manifest)
            payload = workspace / "fd-probe"
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                str(Path(__file__).resolve().parents[1] / "tests/native/linux_helper_fd_probe.c"), "-o", str(payload)],
                check=True, capture_output=True, timeout=30)
            sandbox = LandlockSandbox(str(helper), manifest=str(manifest))
            processes, procdirs, observations, owner_fds = [], [], [], []
            from icode import linux_seccomp_notify as notify
            from icode import linux_task_resource as resources
            monitors, receivers, scopes, endpoints, owners, close_calls = [], [], [], [], [], []
            real_close = os.close
            monitor_type = notify.LinuxSeccompViolationMonitor
            receiver_type = resources.LinuxTaskResourceReceiver
            scope_type = LinuxTaskScope
            real_owner_close = LinuxHelperObject.close
            def capture_component(constructor, values, *args, **kwargs):
                value = constructor(*args, **kwargs)
                values.append(value)
                stack.callback(value.close)
                return value
            def capture_channel(constructor):
                pair = constructor()
                endpoints.extend((endpoint, endpoint.fileno(), descriptor_identity(endpoint.fileno())) for endpoint in pair)
                for endpoint in pair:
                    fd, identity = endpoint.fileno(), descriptor_identity(endpoint.fileno())
                    stack.callback(cleanup_descriptor, fd, identity, real_close)
                    stack.callback(endpoint.close)
                return pair
            def owner_close(owner):
                close_calls.append(owner)
                return real_owner_close(owner)
            notify_channel = notify.create_seccomp_listener_handoff_channel
            resource_channel = resources.create_task_resource_channel
            expected = []
            native_policy = (session.policy("code", process_limit=1, wall_timeout_seconds=8, output_limit_bytes=2048)
                             if session else replace(policy_for(workspace), process_limit=1))
            ctx = ToolContext(workspace, sandbox=sandbox, policy=native_policy, workspace_session=session) if session else None
            context_calls = []
            real_popen = subprocess.Popen
            def launch(argv, **kwargs):
                process = real_popen(argv, **kwargs)
                # Manager version/show commands are not the dispatch process.
                if expected and (str(argv[0]).startswith("/proc/self/fd/")
                                 or (argv[0] == "/usr/bin/systemd-run" and "--scope" in argv)):
                    processes.append(process)
                    stack.callback(cleanup_process, process)
                    try:
                        directory = os.open(f"/proc/{process.pid}", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
                    except OSError:
                        directory = None
                    if directory is not None:
                        stack.callback(os.close, directory)
                    procdirs.append(directory)
                return process
            def factory(binary, digest):
                owner = open_linux_helper_object(binary, digest)
                fd = owner.fileno(); owner_fds.append(fd)
                owners.append(owner)
                current = os.fstat(fd); expected.append((current.st_dev, current.st_ino))
                stack.callback(cleanup_descriptor, fd, expected[-1], real_close)
                try:
                    if mutation == "rename": helper.rename(root / "held-renamed")
                    elif mutation == "unlink": helper.unlink()
                    elif mutation == "replace":
                        helper.rename(root / "held-replaced")
                        # A real ELF decoy. It prints a distinguishable marker if selected.
                        decoy = root / "decoy.c"
                        decoy.write_text('#include <stdio.h>\nint main(void){puts("DECOY-STARTED");return 0;}\n')
                        subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                        str(decoy), "-o", str(helper)], check=True,
                                       capture_output=True, timeout=30)
                except BaseException as error:
                    # Factory wrapper has not returned: broker owns nothing yet.
                    owner.__exit__(type(error), error, error.__traceback__)
                    raise
                return owner
            def wrap(argv, control, *resource_args, helper_object):
                status = os.fstat(helper_object.fileno())
                command = [str(payload), str(helper_object.fileno()), str(status.st_dev), str(status.st_ino),
                           str(workspace_fd), str(workspace_identity[0]), str(workspace_identity[1]),
                           "HELD-PAYLOAD-SCOPE" if resource_mode else "HELD-PAYLOAD"]
                if ctx is not None:
                    context_calls.append(helper_object)
                    prepared = (ctx.wrap_command_with_resource_receipt(
                        command, control, resource_args[0], resource_args[1], helper_object=helper_object)
                        if resource_args else ctx.wrap_command_with_violation_receipt(
                            command, control, helper_object=helper_object))
                    self.assertIs(prepared.helper_object, helper_object)
                    self.assertIn(workspace_fd, prepared.pass_fds)
                    return prepared
                if resource_args:
                    return sandbox.wrap_policy_with_resource_receipt(command, policy=native_policy,
                        control_socket=control, resource_socket=resource_args[0], unit=resource_args[1],
                        helper_object=helper_object, workspace_fd=workspace_fd, workspace_identity=workspace_identity)
                return sandbox.wrap_policy_with_violation_receipt(command, policy=native_policy,
                    control_socket=control, helper_object=helper_object,
                    workspace_fd=workspace_fd, workspace_identity=workspace_identity)
            real_configured = LinuxTaskScope.configured
            def configured(scope, deadline):
                real_configured(scope, deadline)
                self.assertEqual(scope._pid, processes[-1].pid)
                # Receiver._message authenticated SCM_CREDENTIALS against bind_process first.
                result = (running_identity(processes[-1], procdirs[-1], expected[0], deadline)
                          if procdirs[-1] is not None else "inconclusive")
                observations.append(("configured-before-ack", result))
                if result != "pass": raise RuntimeError("native identity gate unavailable")
            stack.enter_context(mock.patch.object(broker.subprocess, "Popen", side_effect=launch))
            stack.enter_context(mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory))
            stack.enter_context(mock.patch.object(LinuxTaskScope, "configured", new=configured))
            stack.enter_context(mock.patch.object(LinuxHelperObject, "close", new=owner_close))
            stack.enter_context(mock.patch.object(notify, "LinuxSeccompViolationMonitor",
                side_effect=lambda *args, **kwargs: capture_component(monitor_type, monitors, *args, **kwargs)))
            stack.enter_context(mock.patch.object(resources, "LinuxTaskResourceReceiver",
                side_effect=lambda *args, **kwargs: capture_component(receiver_type, receivers, *args, **kwargs)))
            stack.enter_context(mock.patch("icode.linux_task_scope.LinuxTaskScope",
                side_effect=lambda *args, **kwargs: capture_component(scope_type, scopes, *args, **kwargs)))
            stack.enter_context(mock.patch.object(notify, "create_seccomp_listener_handoff_channel",
                side_effect=lambda: capture_channel(notify_channel)))
            stack.enter_context(mock.patch.object(resources, "create_task_resource_channel",
                side_effect=lambda: capture_channel(resource_channel)))
            channel_close_evidence = stack.enter_context(observe_channel_closes(endpoints))
            for dispatch_number in range(2):
                shutil.copyfile(source, helper); helper.chmod(0o700)
                shutil.copyfile(manifest_source, manifest)
                for marker in (workspace / "ready", workspace / "release"):
                    marker.unlink(missing_ok=True)
                processes.clear(); procdirs.clear(); observations.clear(); owner_fds.clear(); expected.clear()
                monitors.clear(); receivers.clear(); scopes.clear(); endpoints.clear(); owners.clear(); close_calls.clear()
                channel_close_evidence.clear()
                context_calls.clear()
                entry, entry_options = observed_entry(resource_mode, consumer)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(entry,
                        [str(payload)], cwd=workspace, sandbox=sandbox, policy=native_policy,
                        timeout=6, command_wrapper=wrap, **entry_options)
                    try:
                        deadline = time.monotonic() + 3
                        while not (workspace / "ready").exists() and not future.done() and time.monotonic() < deadline:
                            time.sleep(0.01)
                        if (workspace / "ready").exists() and len(processes) == 1:
                            result = (running_identity(processes[0], procdirs[0], expected[0], deadline)
                                      if procdirs[0] is not None else "inconclusive")
                            observations.append(("payload-ready-before-release", result))
                        else:
                            observations.append(("payload-ready-before-release", "inconclusive"))
                    finally:
                        (workspace / "release").touch()
                    answer = future.result(timeout=8)
                live_workspace = os.fstat(workspace_fd)
                workspace_live = (live_workspace.st_dev, live_workspace.st_ino) == workspace_identity
                process_closed = all(p.returncode is not None and (p.stdout is None or p.stdout.closed)
                                     and (p.stderr is None or p.stderr.closed) for p in processes)
                channels_closed = channels_confirmed_closed(endpoints, channel_close_evidence)
                threads_stopped = all(value._thread is None or not value._thread.is_alive()
                                      for value in (*monitors, *receivers))
                record = dict(architecture=architecture, kernel=platform.release(), topology="scope" if resource_mode else "no-scope",
                              consumer=consumer, public_entry=("resource" if resource_mode else "violation") if ctx is not None else None,
                              context_borrowed=ctx is not None,
                              workspace_live=workspace_live,
                              package_helper_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                              manifest_sha256=hashlib.sha256(manifest_source.read_bytes()).hexdigest(),
                              mutation=mutation, dispatch_number=dispatch_number, observations=observations, error=answer.error,
                              cleanup_ok=answer.cleanup_ok, scope_cleanup_ok=answer.scope_cleanup_ok,
                              process_closed=process_closed, channels_closed=channels_closed,
                              threads_stopped=threads_stopped, owner_states=[owner._state for owner in owners],
                              scope_states=[scope.cleanup_state for scope in scopes],
                              pids=[p.pid for p in processes], systemd=subprocess.run(["/usr/bin/systemd-run", "--version"],
                                  capture_output=True, check=False, timeout=2).stdout.decode(errors="replace").splitlines()[:1])
                if ctx is not None:
                    self.assertEqual(context_calls, owners)
                    self.assertIs(ctx.workspace_session, session)
                    self.assertIs(ctx.policy, native_policy)
                    self.assertEqual(session.workspace_fd, workspace_fd)
                    self.assertEqual(session.workspace_fd_identity, workspace_identity)
                print(json.dumps(record, sort_keys=True), flush=True)
                self.assertNotIn("DECOY-STARTED", answer.output)
                self.assertEqual(len(processes), 1)
                self.assertEqual(len(owners), 1)
                self.assertEqual(close_calls, owners)
                self.assertTrue(process_closed)
                self.assertTrue(channels_closed)
                self.assertTrue(threads_stopped)
                self.assertTrue(all(p.returncode is not None for p in processes), "broker did not reap its own child")
                self.assertTrue(workspace_live)
                self.assertEqual((live_workspace.st_dev, live_workspace.st_ino), workspace_identity)
                self.assertTrue(answer.cleanup_ok)
                if resource_mode: self.assertIs(answer.scope_cleanup_ok, True)
                for fd in owner_fds:
                    with self.assertRaises(OSError) as caught: os.fstat(fd)
                    self.assertEqual(caught.exception.errno, errno.EBADF)
                if any(result == "fail" for _, result in observations):
                    self.fail("confirmed-negative: running helper is a different object")
                if any(result == "inconclusive" for _, result in observations):
                    # Real helper/payload/cleanup errors remain FAIL; observation
                    # unavailability alone can be inconclusive. CONFIGURED rejection
                    # specifically caused by an unavailable exe observation is unknown.
                    identity_blocked = resource_mode and observations[0] == ("configured-before-ack", "inconclusive")
                    if not identity_blocked:
                        self.assertIsNone(answer.error)
                        self.assertEqual(answer.exit_code, 0)
                        self.assertIn("HELD-PAYLOAD", answer.output)
                        self.assertTrue(answer.cleanup_ok)
                    self.skipTest("inconclusive: running identity/window unavailable; no native credit")
                self.assertIsNone(answer.error)
                self.assertEqual(answer.exit_code, 0)
                self.assertIn("HELD-PAYLOAD", answer.output)
                self.assertTrue(answer.cleanup_ok)
                self.assertEqual(answer.violation_observer_status, "complete")
                self.assertIsNotNone(answer.violation_receipt)
                self.assertEqual(answer.violation_receipt['source'], 'seccomp_user_notif')
                self.assertEqual(answer.violation_receipt['category'], 'network_socket')
                self.assertGreaterEqual(answer.violation_receipt['count'], 1)
                if resource_mode:
                    self.assertIs(answer.scope_cleanup_ok, True)
                    self.assertEqual(answer.resource_receipt["channel_status"], "complete")

    def test_no_scope_actual_package_identity_and_fd_boundary(self):
        for mutation in ("none", "rename", "unlink", "replace"):
            with self.subTest(mutation=mutation): self.probe(False, mutation)

    def test_scope_actual_package_second_hop_identity_and_fd_boundary(self):
        for mutation in ("none", "rename", "unlink", "replace"):
            with self.subTest(mutation=mutation): self.probe(True, mutation)

    def test_public_context_no_scope_actual_package_identity_and_fd_boundary(self):
        for mutation in ("none", "rename", "unlink", "replace"):
            with self.subTest(mutation=mutation): self.probe(False, mutation, "context")

    def test_public_context_scope_actual_package_identity_and_fd_boundary(self):
        for mutation in ("none", "rename", "unlink", "replace"):
            with self.subTest(mutation=mutation): self.probe(True, mutation, "context")


class TestIdentityEvidence(unittest.TestCase):
    def test_channel_close_requires_observed_close_and_tolerates_later_fd_reuse(self):
        first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        endpoints = [(item, item.fileno(), descriptor_identity(item.fileno())) for item in (first, second)]
        first_fd = first.fileno()
        detached_fd = foreign = None
        real_close = socket.socket.close
        try:
            with observe_channel_closes(endpoints) as closed:
                first.close()
                self.assertIn(id(first), closed)
                self.assertTrue(descriptor_closed(first_fd))
                # Reuse the released numeric descriptor with a different real
                # object. This cannot erase the previously measured close.
                foreign = os.open('/usr/bin/true', os.O_RDONLY | os.O_CLOEXEC)
                if foreign != first_fd:
                    os.dup2(foreign, first_fd)
                    os.close(foreign)
                    foreign = first_fd
                self.assertTrue(channels_confirmed_closed(endpoints[:1], closed))
                detached_fd = second.detach()
                self.assertTrue(os.fstat(detached_fd))
                self.assertFalse(channels_confirmed_closed(endpoints, closed))
                self.assertNotIn(id(second), closed)
        finally:
            real_close(first)
            real_close(second)
            if detached_fd is not None:
                os.close(detached_fd)
            if foreign is not None:
                os.close(foreign)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux procfs identity")
    def test_real_wrong_object_is_negative_and_elapsed_window_is_unknown(self):
        class Current:
            pid = os.getpid()
            def poll(self): return None
        directory = os.open(f"/proc/{os.getpid()}", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        foreign = os.open("/usr/bin/true", os.O_RDONLY | os.O_CLOEXEC)
        try:
            status = os.fstat(foreign)
            expected = (status.st_dev, status.st_ino)
            self.assertEqual(running_identity(Current(), directory, expected, time.monotonic() + 1), "fail")
            self.assertEqual(running_identity(Current(), directory, expected, time.monotonic() - 1), "inconclusive")
        finally:
            os.close(foreign); os.close(directory)

class TestInstalledCandidateFaults(unittest.TestCase):
    def run_fault(self, resource_mode, scenario, consumer="candidate"):
        from icode import linux_seccomp_notify as notify
        from icode import linux_task_resource as resources
        import socket
        sandbox = LandlockSandbox.from_bundle()
        if sandbox is None: self.skipTest("inconclusive: installed native package unavailable")
        self.assertEqual(linux_elf_architecture(Path(sandbox.helper).read_bytes()[:64]),
                         linux_arch_from_machine(platform.machine()))
        if resource_mode and (os.getuid() == 0 or not Path(f"/run/user/{os.getuid()}/bus").exists()):
            self.skipTest("inconclusive: non-root user manager unavailable")
        compiler = shutil.which("cc")
        if compiler is None: self.skipTest("inconclusive: C compiler unavailable")
        source, manifest_source = Path(sandbox.helper), Path(sandbox.manifest)
        package_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest_hash = hashlib.sha256(manifest_source.read_bytes()).hexdigest()
        systemd = subprocess.run(['/usr/bin/systemd-run', '--version'], capture_output=True,
                                 check=False, timeout=2).stdout.decode(errors='replace').splitlines()[:1]
        real_popen, real_stop, real_close = subprocess.Popen, broker._stop_group, os.close
        monitor_start = notify.LinuxSeccompViolationMonitor.start
        monitor_close = notify.LinuxSeccompViolationMonitor.close
        record_original = notify.LinuxSeccompViolationMonitor._record
        acknowledge_original = notify.LinuxSeccompViolationMonitor._acknowledge_if_healthy
        resource_close = resources.LinuxTaskResourceReceiver.close
        scope_configured = LinuxTaskScope.configured
        owner_factory = open_linux_helper_object
        owner_close = LinuxHelperObject.close
        owner_close_calls = []
        monitors, receivers, scopes, processes, endpoints, owners, leaked = [], [], [], [], [], [], []
        hits, directory_fds = [], set()
        endpoint_snapshots = []
        injected = KeyboardInterrupt() if scenario == "keyboardinterrupt" else SystemExit(47)
        with temp_workspace() as raw, ExitStack() as stack:
            root = raw.resolve()
            workspace, workspace_fd, identity, session = probe_workspace(root, stack, consumer)
            payload = workspace / "fault-payload"
            subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                str(Path(__file__).resolve().parents[1] / "tests/native/linux_helper_fd_probe.c"), "-o", str(payload)],
                check=True, capture_output=True, timeout=30)
            policy = (session.policy("code", process_limit=1, wall_timeout_seconds=6, output_limit_bytes=256)
                      if session else replace(policy_for(workspace), process_limit=1, wall_timeout_seconds=6, output_limit_bytes=256))
            ctx = ToolContext(workspace, sandbox=sandbox, policy=policy, workspace_session=session) if session else None
            context_calls = []
            def factory(*args):
                owner = owner_factory(*args); owners.append((owner, owner.fileno())); return owner
            def close_owner(owner):
                owner_close_calls.append(owner)
                return owner_close(owner)
            notify_channel = notify.create_seccomp_listener_handoff_channel
            resource_channel = resources.create_task_resource_channel
            def channel(factory):
                answer = factory()
                endpoints.extend(answer)
                endpoint_snapshots.extend((endpoint, endpoint.fileno(), descriptor_identity(endpoint.fileno())) for endpoint in answer)
                return answer
            def monitor_factory(*args):
                value = original_monitor(*args); monitors.append(value); return value
            def receiver_factory(*args, **kwargs):
                value = original_receiver(*args, **kwargs); receivers.append(value); return value
            def scope_factory(*args, **kwargs):
                value = original_scope(*args, **kwargs); scopes.append(value); return value
            original_monitor = notify.LinuxSeccompViolationMonitor
            original_receiver = resources.LinuxTaskResourceReceiver
            original_scope = LinuxTaskScope
            def launch(argv, **kwargs):
                dispatch = str(argv[0]).startswith("/proc/self/fd/") or (argv[0] == "/usr/bin/systemd-run" and "--scope" in argv)
                if dispatch and scenario == "launch_failed":
                    hits.append(scenario); raise OSError(errno.ENOEXEC, "fixed launch fault")
                process = real_popen(argv, **kwargs)
                if dispatch: processes.append(process)
                return process
            def wrap(argv, control, *resource_args, helper_object):
                status = os.fstat(helper_object.fileno())
                marker = "OUTPUT" if scenario == "output_limit" else "HELD-PAYLOAD"
                if resource_mode: marker += "-SCOPE"
                command = [str(payload), str(helper_object.fileno()), str(status.st_dev), str(status.st_ino),
                           str(workspace_fd), str(identity[0]), str(identity[1]), marker]
                if ctx is not None:
                    context_calls.append(helper_object)
                    prepared = (ctx.wrap_command_with_resource_receipt(
                        command, control, resource_args[0], resource_args[1], helper_object=helper_object)
                        if resource_args else ctx.wrap_command_with_violation_receipt(
                            command, control, helper_object=helper_object))
                    self.assertIs(prepared.helper_object, helper_object)
                    return prepared
                options = dict(policy=policy, control_socket=control, helper_object=helper_object,
                               workspace_fd=workspace_fd, workspace_identity=identity)
                if resource_args:
                    return sandbox.wrap_policy_with_resource_receipt(command, resource_socket=resource_args[0],
                        unit=resource_args[1], **options)
                return sandbox.wrap_policy_with_violation_receipt(command, **options)
            def start(monitor, *, deadline_monotonic):
                if scenario == "observer_start":
                    hits.append(scenario); raise RuntimeError("fixed observer start fault")
                monitor_start(monitor, deadline_monotonic=deadline_monotonic)
                if scenario in ("keyboardinterrupt", "systemexit"):
                    hits.append(scenario); raise injected
            def record(monitor, category):
                record_original(monitor, category)
                if scenario == "observer_runtime":
                    hits.append(scenario); monitor._fail()
            def configured(scope, deadline):
                scope_configured(scope, deadline)
                if scenario == "resource_configured":
                    hits.append(scenario); raise RuntimeError("fixed CONFIGURED failure")
            def close(fd):
                if scenario == "helper_close_unknown" and any(fd == owned_fd for _, owned_fd in owners):
                    hits.append(scenario); leaked.append(fd); raise OSError(errno.EIO, "before helper close")
                if scenario == "scope_close_unknown" and fd in directory_fds:
                    hits.append(scenario); leaked.append(fd); raise OSError(errno.EIO, "before scope directory close")
                return real_close(fd)
            def close_resource(receiver):
                result = resource_close(receiver)
                if scenario == "resource_close": hits.append(scenario)
                return False if scenario == "resource_close" else result
            def close_monitor(monitor):
                result = monitor_close(monitor)
                if scenario == "observer_close": hits.append(scenario)
                return False if scenario == "observer_close" else result
            def acknowledge(monitor, deadline):
                if scenario == "missing_ack":
                    self.assertTrue(monitor._ready.is_set())
                    self.assertFalse(monitor.failed)
                    self.assertTrue(monitor._thread.is_alive())
                    hits.append(scenario); return
                acknowledge_original(monitor, deadline)
                if scenario == "bad_ack":
                    self.assertTrue(monitor._started); hits.append(scenario)
            def start_resource(receiver, *, deadline_monotonic, configured_deadline_monotonic=None):
                hits.append(scenario); raise RuntimeError("fixed resource start fault")
            stack.enter_context(mock.patch.object(broker.subprocess, "Popen", side_effect=launch))
            stack.enter_context(mock.patch("icode.linux_helper_object.open_linux_helper_object", side_effect=factory))
            stack.enter_context(mock.patch.object(LinuxHelperObject, 'close', new=close_owner))
            stack.enter_context(mock.patch.object(notify, "create_seccomp_listener_handoff_channel", side_effect=lambda: channel(notify_channel)))
            stack.enter_context(mock.patch.object(resources, "create_task_resource_channel", side_effect=lambda: channel(resource_channel)))
            stack.enter_context(mock.patch.object(notify, "LinuxSeccompViolationMonitor", side_effect=monitor_factory))
            stack.enter_context(mock.patch.object(resources, "LinuxTaskResourceReceiver", side_effect=receiver_factory))
            stack.enter_context(mock.patch("icode.linux_task_scope.LinuxTaskScope", side_effect=scope_factory))
            stack.enter_context(mock.patch.object(original_monitor, "start", new=start))
            stack.enter_context(mock.patch.object(original_monitor, "_record", new=record))
            stack.enter_context(mock.patch.object(original_monitor, "close", new=close_monitor))
            stack.enter_context(mock.patch.object(original_receiver, "close", new=close_resource))
            stack.enter_context(mock.patch.object(original_scope, "configured", new=configured))
            stack.enter_context(mock.patch("os.close", side_effect=close))
            channel_close_evidence = stack.enter_context(observe_channel_closes(endpoint_snapshots))
            if scenario == "bad_ack": stack.enter_context(mock.patch.object(notify, "_HANDOFF_ACK", b"INVALID_ACK"))
            if scenario in ("bad_ack", "missing_ack"):
                stack.enter_context(mock.patch.object(original_monitor, "_acknowledge_if_healthy", new=acknowledge))
            if scenario == "resource_start":
                stack.enter_context(mock.patch.object(original_receiver, "start", new=start_resource))
            if scenario == "scope_close_unknown":
                # _close_pins pops before close, so target exact acquired identities.
                def configured_capture(scope, deadline):
                    configured(scope, deadline); directory_fds.update(scope._fds)
                stack.enter_context(mock.patch.object(original_scope, "configured", new=configured_capture))
                # Only os.close is faulted: production _close_owned_descriptor
                # must set sticky unknown itself, with no manual state or retry.
            if scenario not in ("timeout", "bad_ack", "missing_ack", "observer_start", "resource_start", "resource_configured"):
                (workspace / "release").touch()
            result, error = None, None
            entry, entry_options = observed_entry(resource_mode, consumer)
            try:
                try:
                    result = entry([str(payload)], cwd=workspace,
                        sandbox=sandbox, policy=policy, timeout=3 if scenario == "timeout" else 4,
                        command_wrapper=wrap, **entry_options)
                except BaseException as exception:
                    error = exception
                # Snapshot broker terminal evidence before any fixture self-cleanup.
                process_closed = all(process.returncode is not None and
                    (process.stdout is None or process.stdout.closed) and
                    (process.stderr is None or process.stderr.closed) for process in processes)
                channels_closed = channels_confirmed_closed(endpoint_snapshots, channel_close_evidence)
                threads_stopped = all(monitor._thread is None or not monitor._thread.is_alive() for monitor in monitors)
                threads_stopped = threads_stopped and all(receiver._thread is None or not receiver._thread.is_alive() for receiver in receivers)
                owner_states = [owner._state for owner, _ in owners]
                live_workspace = os.fstat(workspace_fd)
                workspace_live = (live_workspace.st_dev, live_workspace.st_ino) == identity
                scope_states = [scope.cleanup_state for scope in scopes]
                owned_scopes = [scope for scope in scopes if scope._path is not None]
                scope_gc = all(not scope._path.exists() for scope in owned_scopes) if owned_scopes else None
                print(json.dumps(dict(scenario=scenario, topology="scope" if resource_mode else "no-scope",
                    consumer=consumer, public_entry=("resource" if resource_mode else "violation") if ctx is not None else None,
                    context_borrowed=ctx is not None,
                    architecture=linux_arch_from_machine(platform.machine()), process_closed=process_closed,
                    channels_closed=channels_closed, threads_stopped=threads_stopped,
                    owner_states=owner_states, scope_states=scope_states, scope_cleanup_ok=scope_gc,
                    workspace_live=workspace_live, pids=[process.pid for process in processes],
                    kernel=platform.release(), systemd=systemd,
                    package_helper_sha256=package_hash, manifest_sha256=manifest_hash,
                    error=result.error if result is not None else "raised", exception=type(error).__name__ if error is not None else None), sort_keys=True), flush=True)
                self.assertEqual(len(owners), 1); self.assertTrue(process_closed)
                if ctx is not None:
                    self.assertEqual(context_calls, [owner for owner, _ in owners])
                self.assertEqual(owner_close_calls, [owner for owner, _ in owners])
                self.assertTrue(channels_closed); self.assertTrue(threads_stopped)
                if scenario not in ("timeout", "output_limit"):
                    self.assertIn(scenario, hits, "requested native fault site was never reached")
                self.assertEqual(len(processes), 0 if scenario == "launch_failed" else 1)
                self.assertTrue(workspace_live)
                if owned_scopes: self.assertIs(scope_gc, True, "owned scope cgroup remains")
                if scenario in ("keyboardinterrupt", "systemexit"):
                    self.assertIs(error, injected); self.assertIsNone(result)
                elif scenario in ("helper_close_unknown", "scope_close_unknown"):
                    self.assertIsNone(result); self.assertEqual(type(error).__name__, "LinuxHelperObjectError")
                    self.assertTrue(leaked); self.assertEqual(len(leaked), len(set(leaked)))
                    for fd in leaked: self.assertTrue(os.fstat(fd))
                else:
                    self.assertIsNone(error); self.assertIsNotNone(result)
                    self.assertTrue(result.error is not None or result.exit_code != 0)
                    if scenario in ("timeout", "output_limit", "launch_failed"):
                        self.assertEqual(result.error, scenario)
                    if scenario == "launch_failed": self.assertIs(result.payload_started, False)
                    if scenario == "timeout": self.assertTrue((workspace / "ready").exists())
                    if scenario in ("timeout", "output_limit"): hits.append(scenario)
                    if scenario in ("bad_ack", "missing_ack", "observer_start", "resource_start", "resource_configured"):
                        self.assertFalse((workspace / "ready").exists())
                    self.assertTrue(result.cleanup_ok)
                self.assertIn(scenario, hits)
                if scenario in ("observer_close", "resource_close", "helper_close_unknown", "scope_close_unknown"):
                    self.assertTrue((workspace / "ready").exists(), "cleanup fault cannot substitute an earlier startup failure")
                    self.assertEqual(processes[0].returncode, 0)
                for owner, fd in owners:
                    if scenario != "helper_close_unknown":
                        with self.assertRaises(OSError) as caught: os.fstat(fd)
                        self.assertEqual(caught.exception.errno, errno.EBADF)
                    else: self.assertEqual(owner._state, "unknown")
                if scenario == "scope_close_unknown": self.assertIn("unknown", scope_states)
                else: self.assertTrue(all(state == "confirmed" for state in scope_states))
            finally:
                # RED/fault leftovers are cleaned with saved real methods only
                # after the terminal snapshot; these attempts confer no credit.
                for process in processes:
                    if process.returncode is None: real_stop(process)
                    for stream in (process.stdout, process.stderr):
                        if stream is not None: stream.close()
                for monitor in monitors: monitor_close(monitor)
                for receiver in receivers: resource_close(receiver)
                for endpoint in endpoints: socket.socket.close(endpoint)
                for _, fd, identity in endpoint_snapshots:
                    cleanup_descriptor(fd, identity, real_close)
                for fd in set(leaked):
                    try: real_close(fd)
                    except OSError: pass

    def test_real_candidate_faults_no_scope(self):
        for scenario in ("bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                         "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"):
            with self.subTest(scenario=scenario): self.run_fault(False, scenario)

    def test_real_candidate_faults_scope(self):
        for scenario in ("bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                         "resource_start", "resource_configured", "resource_close", "scope_close_unknown",
                         "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"):
            with self.subTest(scenario=scenario): self.run_fault(True, scenario)

    def test_real_public_context_faults_no_scope(self):
        for scenario in ("bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                         "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"):
            with self.subTest(scenario=scenario): self.run_fault(False, scenario, "context")

    def test_real_public_context_faults_scope(self):
        for scenario in ("bad_ack", "missing_ack", "observer_start", "observer_runtime", "observer_close",
                         "resource_start", "resource_configured", "resource_close", "scope_close_unknown",
                         "timeout", "output_limit", "launch_failed", "keyboardinterrupt", "systemexit", "helper_close_unknown"):
            with self.subTest(scenario=scenario): self.run_fault(True, scenario, "context")

def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): return 1
    if result.skipped: return 77
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
