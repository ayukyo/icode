"""Real receiver/runtime facts; software launch seam, no native credit."""
from __future__ import annotations
from contextlib import ExitStack
from dataclasses import replace
import os
import selectors
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

LINUX = sys.platform.startswith("linux") and callable(getattr(os, "pread", None))
if LINUX:
    from tests import test_linux_prepared_step as fixture
    from tests import test_linux_prepared_broker as forwarding
    from tests import test_linux_helper_dispatch as dispatch
    from icode import execution_broker as broker
    from icode import linux_task_resource as resource
    from icode import linux_task_scope as scopes
    from icode import linux_seccomp_notify as seccomp
    from icode import linux_helper_object as factory

CHILD = r"""
import os, socket, struct, sys
sender = socket.socket(fileno=int(sys.argv[1]))
mode = sys.argv[2]
nonce = bytes.fromhex("0123456789abcdef0123456789abcdef")
limit = int(sys.argv[3])
frame = lambda phase: b"ICQR1" + bytes([phase]) + nonce + struct.pack("!I", limit)
sender.send(frame(1))
ack = sender.recv(64)
assert ack == b"ICQA1" + nonce + struct.pack("!I", limit)
if mode == "finished":
    sender.send(frame(3))
    sender.close()
elif mode == "preexec":
    sender.send(frame(2))
    sender.close()
elif mode == "cleanup":
    sender.send(frame(4))
    sender.close()
elif mode == "early":
    sender.close()
elif mode == "bad":
    sender.send(b"bad")
    sender.close()
else:
    os.close(1)
    os.close(2)
    sender.recv(1)
"""

@unittest.skipUnless(LINUX, "Linux real-resource software tests; skip is not acceptance")
class RuntimeDeadlineTests(unittest.TestCase):
    if LINUX:
        setUp = fixture.PreparedTests.setUp
        write_image = fixture.PreparedTests.write_image
        precheck_fixture = fixture.PreparedTests.precheck_fixture
        cleanup_scopes = fixture.PreparedTests.cleanup_scopes
        prepare = fixture.PreparedTests.prepare
        attach = fixture.PreparedTests.attach
        bind = fixture.PreparedTests.bind
        borrow = fixture.PreparedTests.borrow
        wrapper = forwarding.PreparedBrokerTests.wrapper

    def run_chain(self, mode="timeout", *, core_error=None, observer_failed=False,
                  resource_close_unknown=False, close_wins=False, external_kill=False,
                  configured_failure=False, configured_expiration=False, fake_fact=None,
                  initial_empty_readiness=False, core_empty_readiness=False):
        self.owners = []
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        task = dispatch.Scope()
        task.configured = lambda deadline: None
        if configured_failure:
            def configured(deadline):
                raise RuntimeError("fixed callback fixture")
            task.configured = configured
        if configured_expiration:
            def configured(deadline):
                threading.Event().wait(max(0, deadline - time.monotonic()) + 0.001)
            task.configured = configured
        monitor = dispatch.Monitor(None)
        monitor.failed = observer_failed
        originals = dict(selector=selectors.DefaultSelector,
                         core=broker._execute_policy_command,
                         receiver=resource.LinuxTaskResourceReceiver)
        eof = threading.Event()
        killed = threading.Event()
        release = threading.Event()
        worker_blocked = threading.Event()
        state = dict(receivers=[], processes=[], before_kill=[], core=[], selectors=[], close_threads=[])
        timeout = 0.3 if mode == "timeout" else 3.0

        def complete_eof_barrier():
            eof.set()
            if external_kill:
                state["processes"][0].kill()
            elif close_wins:
                self.assertTrue(worker_blocked.wait(5))
                receiver = state["receivers"][0]
                closer = threading.Thread(target=receiver.close, name="deadline-test-close")
                state["close_threads"].append(closer)
                closer.start()
                self.assertTrue(receiver._stop.wait(5))
                threading.Event().wait(max(0, state["deadline"] - time.monotonic()) + 0.001)
                release.set()
            self.assertTrue(killed.wait(5))

        class RoutedSelector:
            def __init__(inner):
                inner.actual = originals["selector"]()
                inner.worker = threading.current_thread().name == "icode-task-resource"
                inner.calls = 0
                inner.polls = 0
                state["selectors"].append(inner)
            def register(inner, *args, **kwargs):
                return inner.actual.register(*args, **kwargs)
            def unregister(inner, *args, **kwargs):
                return inner.actual.unregister(*args, **kwargs)
            def get_map(inner):
                return inner.actual.get_map()
            def select(inner, timeout=None):
                inner.calls += 1
                if inner.worker and inner.calls == 1 and initial_empty_readiness:
                    return []  # A legal empty poll must not imply CONFIGURED.
                if (inner.worker and mode == "timeout"
                        and state["receivers"][0].receipt()["configured"] is True):
                    worker_blocked.set()
                    self.assertTrue(eof.wait(5))
                    if close_wins:
                        self.assertTrue(release.wait(5))
                    elif external_kill:
                        return inner.actual.select(timeout)
                    else:
                        threading.Event().wait(max(0, state["deadline"] - time.monotonic()) + 0.001)
                    return []
                if not inner.worker and mode == "timeout":
                    process = state["processes"][0]
                    expected = {process.stdout.fileno(), process.stderr.fileno()}
                    self.assertEqual(set(inner.actual.get_map()), expected)
                    ready = {}
                    hygiene_deadline = time.monotonic() + 5
                    while set(ready) != expected:
                        remaining = hygiene_deadline - time.monotonic()
                        self.assertGreater(remaining, 0, "real pipe EOF barrier expired")
                        inner.polls += 1
                        if core_empty_readiness and inner.polls == 1:
                            # Diagnostic empty poll arriving after the actual
                            # deadline; never hand-set a receiver expiry fact.
                            threading.Event().wait(max(0, state["deadline"] - time.monotonic()) + 0.001)
                            events = []
                        else:
                            events = inner.actual.select(min(remaining, 0.05))
                        for key, mask in events:
                            self.assertIn(key.fd, expected)
                            self.assertEqual(os.read(key.fd, 1), b"")
                            ready[key.fd] = (key, mask)
                    # Keep both genuine EOF keys in this core iteration until
                    # the real worker has killed/reaped the real child.
                    complete_eof_barrier()
                    return list(ready.values())
                return inner.actual.select(timeout)
            def close(inner):
                inner.actual.close()

        def received(*args, **kwargs):
            receiver = (originals["receiver"])(*args, **kwargs)
            state["receivers"].append(receiver)
            original_start = receiver.start
            def start(**keywords):
                state["deadline"] = keywords["deadline_monotonic"]
                original_start(**keywords)
            receiver.start = start
            if resource_close_unknown:
                original_close = receiver.close
                def close():
                    original_close()
                    return False
                receiver.close = close
            return receiver

        def core(argv, **keywords):
            # Authenticate the real held wrapper before a software-only argv
            # substitution. No native helper/scope/payload success is claimed.
            keywords.pop("before_spawn")()
            original_spawn = keywords["on_spawn"]
            def spawn(process, deadline):
                state["processes"].append(process)
                original_kill = process.kill
                def kill():
                    receiver = state["receivers"][0]
                    state["before_kill"].append(
                        getattr(receiver, "_runtime_deadline_expired", None))
                    original_kill()
                    process.wait(timeout=5)
                    killed.set()
                process.kill = kill
                original_spawn(process, deadline)
            keywords["on_spawn"] = spawn
            actual = [sys.executable, "-I", "-c", CHILD,
                      str(keywords["pass_fds"][-1]), mode, str(self.policy.process_limit)]
            answer = (originals["core"])(actual, **keywords)
            state["core"].append(answer)
            if core_error is not None:
                answer = replace(answer, error=core_error,
                                 cleanup_ok=core_error != "cleanup_failed")
            return answer

        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(scopes, "LinuxTaskScope", return_value=task))
                stack.enter_context(patch.object(seccomp, "LinuxSeccompViolationMonitor", return_value=monitor))
                stack.enter_context(patch.object(resource, "LinuxTaskResourceReceiver", side_effect=received))
                stack.enter_context(patch.object(broker, "_execute_policy_command", side_effect=core))
                stack.enter_context(patch.object(selectors, "DefaultSelector", side_effect=RoutedSelector))
                if fake_fact is not None:
                    # Only the classification strict-bool negative uses a
                    # receipt double; real worker positives never set the fact.
                    stack.enter_context(patch.object(originals["receiver"],
                        "_runtime_deadline_expired", property(lambda instance: fake_fact),
                        create=True))
                answer = broker.execute_linux_resource_observed_command(
                    ["/usr/bin/true"], cwd=self.session.workspace_root,
                    sandbox=self.sandbox, policy=self.policy, timeout=timeout,
                    command_wrapper=self.wrapper, prepared_step=view,
                    workspace_session=self.session, prepared_attempt="software-attempt")
            self.assertEqual(len(state["receivers"]), 1)
            self.assertEqual(len(state["processes"]), 1)
            self.assertEqual(len(state["core"]), 1)
            self.assertTrue(any(selector.worker for selector in state["selectors"]))
            self.assertTrue(any(not selector.worker for selector in state["selectors"]))
            self.assertTrue(state["receivers"][0]._done.is_set())
            self.assertIsNotNone(state["processes"][0].poll())
            self.assertTrue(state["processes"][0].stdout.closed)
            self.assertTrue(state["processes"][0].stderr.closed)
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, "active")
            self.session.lease._validate_active()
            self.assertTrue(os.fstat(self.session.workspace_fd))
            return answer, state, scope, view
        finally:
            release.set()
            eof.set()
            for process in state["processes"]:
                if process.poll() is None:
                    subprocess.Popen.kill(process)
                process.wait(timeout=5)
            for receiver in state["receivers"]:
                receiver.close()
            for closer in state["close_threads"]:
                closer.join(timeout=5)
                self.assertFalse(closer.is_alive())

    def fact(self, state):
        value = getattr(state["receivers"][0], "_runtime_deadline_expired", None)
        self.assertIs(type(value), bool)
        return value

    def test_real_runtime_expiry_precedes_kill_and_repairs_eof_core_race(self):
        answer, state, scope, view = self.run_chain()
        self.assertIsNone(state["core"][0].error)
        self.assertEqual(state["core"][0].exit_code, -9)
        self.assertIs(state["core"][0].cleanup_ok, True)
        self.assertEqual(state["before_kill"], [True])
        self.assertIs(self.fact(state), True)
        self.assertEqual(answer.error, "timeout")
        self.assertEqual(answer.resource_receipt["channel_status"], "incomplete")
        self.assertIs(answer.scope_cleanup_ok, True)
        self.assertEqual(scope._consume_state, "attached_bound")
        self.assertNotIn("runtime_deadline_expired", answer.resource_receipt)
        view.finish()
        self.assertIs(self.fact(state), True)

    def test_timeout_survives_failed_observer_without_new_preserved_errors(self):
        answer, state, scope, view = self.run_chain(observer_failed=True)
        self.assertIsNone(state["core"][0].error)
        self.assertIs(self.fact(state), True)
        self.assertEqual(answer.error, "timeout")
        self.assertEqual(answer.violation_observer_status, "incomplete")

    def test_initial_empty_readiness_waits_for_real_configured_before_barrier(self):
        answer, state, scope, view = self.run_chain(initial_empty_readiness=True)
        self.assertIsNone(state["core"][0].error)
        self.assertEqual(state["core"][0].exit_code, -9)
        self.assertEqual(state["before_kill"], [True])
        self.assertIs(self.fact(state), True)
        self.assertIs(answer.resource_receipt["configured"], True)
        self.assertEqual(answer.error, "timeout")
        self.assertIs(answer.scope_cleanup_ok, True)

    def test_core_empty_readiness_cannot_escape_same_iteration_eof_barrier(self):
        answer, state, scope, view = self.run_chain(core_empty_readiness=True)
        self.assertIsNone(state["core"][0].error)
        self.assertEqual(state["core"][0].exit_code, -9)
        self.assertEqual(state["before_kill"], [True])
        self.assertIs(self.fact(state), True)
        self.assertEqual(answer.error, "timeout")
        self.assertIs(answer.scope_cleanup_ok, True)

    def test_existing_core_errors_are_not_replaced_by_runtime_fact(self):
        for error in ("output_limit", "cleanup_failed", "read_failed",
                      "manager_output_limit", "proxy_setup_failed"):
            for failed in (False, True):
                with self.subTest(error=error, failed=failed):
                    answer, state, scope, view = self.run_chain(
                        core_error=error, observer_failed=failed)
                    self.assertIs(self.fact(state), True)
                    expected = ("violation_observer_failed" if failed and error in
                        ("read_failed", "manager_output_limit", "proxy_setup_failed") else error)
                    self.assertEqual(answer.error, expected)
                    if error == "cleanup_failed":
                        self.assertEqual(scope._consume_state, "faulted")

    def test_complete_and_early_protocol_outcomes_do_not_invent_expiry(self):
        for mode, expected in (("finished", None), ("preexec", "resource_setup_failed"),
                               ("cleanup", "resource_cleanup_failed"),
                               ("early", "resource_channel_failed"), ("bad", "resource_channel_failed")):
            with self.subTest(mode=mode):
                answer, state, scope, view = self.run_chain(mode)
                self.assertIs(self.fact(state), False)
                self.assertEqual(answer.error, expected)
                if mode in ("finished", "preexec", "cleanup"):
                    self.assertEqual(answer.resource_receipt["channel_status"], "complete")
                else:
                    self.assertEqual(answer.resource_receipt["channel_status"], "incomplete")
                if mode == "cleanup":
                    self.assertEqual(scope._consume_state, "faulted")

    def test_external_kill_is_not_runtime_expiry(self):
        answer, state, scope, view = self.run_chain(external_kill=True)
        self.assertIs(self.fact(state), False)
        self.assertEqual(answer.exit_code, -9)
        self.assertEqual(answer.error, "resource_channel_failed")

    def test_configuration_failure_and_cutoff_do_not_invent_expiry(self):
        for cutoff in (False, True):
            with self.subTest(cutoff=cutoff):
                answer, state, scope, view = self.run_chain("finished",
                    configured_failure=not cutoff, configured_expiration=cutoff)
                self.assertIs(self.fact(state), False)
                self.assertEqual(answer.error, "resource_channel_failed")
                self.assertIs(answer.resource_receipt["configured"], False)

    def test_close_linearized_before_runtime_cutoff_does_not_invent_expiry(self):
        answer, state, scope, view = self.run_chain(close_wins=True)
        self.assertTrue(state["receivers"][0]._stop.is_set())
        self.assertGreaterEqual(time.monotonic(), state["deadline"])
        self.assertIs(self.fact(state), False)
        self.assertEqual(answer.error, "resource_channel_failed")

    def test_complete_transcript_cleanup_unknown_remains_faulted_not_timeout(self):
        answer, state, scope, view = self.run_chain("finished", resource_close_unknown=True)
        self.assertIs(self.fact(state), False)
        self.assertEqual(answer.resource_receipt["channel_status"], "incomplete")
        self.assertEqual(answer.error, "resource_channel_failed")
        self.assertEqual(scope._consume_state, "faulted")
        with self.assertRaises(Exception):
            with self.borrow(view):
                pass

    def test_truthy_non_bool_observation_cannot_grant_timeout(self):
        for value in (1, "true", object()):
            with self.subTest(type=type(value).__name__):
                answer, state, scope, view = self.run_chain("early", fake_fact=value)
                self.assertEqual(answer.error, "resource_channel_failed")

    def test_existing_eof_alive_core_path_still_times_out(self):
        with fixture.temp_workspace() as root:
            result = broker._execute_policy_command(
                [sys.executable, "-I", "-c",
                 "import os,time;os.close(1);os.close(2);time.sleep(5)"],
                cwd=root, policy=dispatch.policy_for(root), timeout=0.1,
                manager_stderr=True)
        self.assertEqual(result.error, "timeout")
        self.assertEqual(result.exit_code, -9)
        self.assertIs(result.cleanup_ok, True)

    def test_all_stop_writes_share_receiver_lock(self):
        host, sender = resource.create_task_resource_channel()
        receiver = resource.LinuxTaskResourceReceiver(host,
            unit=dispatch.Scope.unit, limit=2)
        receiver.bind(expected_pid=os.getpid(), expected_uid=os.getuid(),
                      expected_gid=os.getgid())
        actual = receiver._stop
        writes = []
        class Stop:
            def set(inner):
                writes.append(receiver._lock.locked())
                return actual.set()
            def is_set(inner):
                return actual.is_set()
        receiver._stop = Stop()
        try:
            with patch.object(threading.Thread, "start", side_effect=RuntimeError("thread fixture")):
                with self.assertRaises(RuntimeError):
                    receiver.start(deadline_monotonic=time.monotonic() + 1)
            self.assertEqual(writes, [True])
            writes.clear()
            receiver.close()
            self.assertEqual(writes, [True])
        finally:
            host.close()
            sender.close()
