"""S1c real-FD lifecycle software tests; no payload/CP/installed credit."""
from __future__ import annotations
from contextlib import ExitStack
from dataclasses import replace
import errno
import inspect
import os
import socket
import stat
import sys
import time
import unittest
from unittest.mock import patch
from tests import test_linux_prepared_step as fixture
from tests import test_linux_helper_dispatch as dispatch
from icode import execution_broker as broker
from icode import linux_helper_object as factory
from icode import linux_prepared_step as prepared
from icode import linux_seccomp_notify as seccomp
from icode import linux_task_scope as task_module


@unittest.skipUnless(sys.platform.startswith('linux') and callable(getattr(os, 'pread', None)),
    'Linux real-resource software fixture; skip is not acceptance')
class PreparedBrokerTests(unittest.TestCase):
    setUp = fixture.PreparedTests.setUp
    write_image = fixture.PreparedTests.write_image
    precheck_fixture = fixture.PreparedTests.precheck_fixture
    cleanup_scopes = fixture.PreparedTests.cleanup_scopes
    prepare = fixture.PreparedTests.prepare
    attach = fixture.PreparedTests.attach
    bind = fixture.PreparedTests.bind
    borrow = fixture.PreparedTests.borrow

    def entry(self, resource):
        return (broker.execute_linux_resource_observed_command if resource
                else broker.execute_linux_violation_observed_command)

    def call(self, resource, view, **changes):
        entry = self.entry(resource)
        arguments = dict(cwd=self.session.workspace_root, sandbox=self.sandbox,
            policy=self.policy, timeout=1, command_wrapper=self.wrapper,
            prepared_step=view, workspace_session=self.session,
            prepared_attempt='software-attempt')
        arguments.update(changes)
        # Baseline public exists. Missing new signature is exercised by calling
        # its actual old API, then asserting the requested forwarding below.
        # No missing-module/TypeError is counted as an effective RED.
        supported = inspect.signature(entry).parameters
        for name in ('prepared_step', 'workspace_session', 'prepared_attempt'):
            if name not in supported:
                arguments.pop(name)
        return entry(['/usr/bin/true'], **arguments)

    def wrapper(self, argv, sender, *resources, helper_object):
        self.owners.append(helper_object)
        binding = dict(policy=self.policy, control_socket=sender,
            helper_object=helper_object, workspace_fd=self.session.workspace_fd,
            workspace_identity=self.session.workspace_fd_identity)
        if resources:
            return self.sandbox.wrap_policy_with_resource_receipt(argv,
                resource_socket=resources[0], unit=resources[1], **binding)
        return self.sandbox.wrap_policy_with_violation_receipt(argv, **binding)

    def target_forwarding(self, resource):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.assertEqual(scope._consume_state, 'attached_bound')
        self.assertEqual(scope._owner_state, 'active')
        self.precheck_fixture()
        with patch.object(broker, '_execute_linux_observed_command',
                return_value=object()) as core:
            self.call(resource, view)
        self.assertEqual(core.call_count, 1)
        actual = core.call_args.kwargs
        self.assertIs(actual.get('prepared_step'), view)
        self.assertIs(actual.get('workspace_session'), self.session)
        self.assertEqual(actual.get('prepared_attempt'), 'software-attempt')

    def test_violation_public_forwarding_target(self):
        self.target_forwarding(False)

    def test_resource_public_forwarding_target(self):
        self.target_forwarding(True)

    def exercise(self, resource, view, *, body=None, fault=None, result=None,
            changes=None, notification=False, mutation=None, manager_stage=None,
            manager_answer=None, manager_body=None, manager_notification=False,
            construction=None, construction_body=None):
        self.owners, channels, events = [], [], []
        self.manager_keywords = []
        task, receiver = dispatch.Scope(), dispatch.Resource()
        monitor = dispatch.Monitor(None)
        def observe(label):
            self.assertTrue(view._scope._inflight)
            self.assertEqual(view._scope._owner_state, 'active')
            events.append(label)
        def channel():
            observe('channel')
            kind = 'resource_channel' if resource and not channels else 'seccomp_channel'
            if construction == kind:
                raise construction_body
            host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            if fault == 'endpoint_close' and not channels:
                class UnknownHost(socket.socket):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.original_fd = self.fileno()
                        self.attempts = 0
                    def close(self):
                        observe('endpoint_close')
                        self.attempts += 1
                        raise OSError('private endpoint detail')
                host = UnknownHost(fileno=host.detach())
            pair = host, sender
            channels.extend(pair)
            return pair
        def monitored(host):
            if construction == 'monitor':
                observe('monitor_constructor')
                raise construction_body
            monitor.host = host
            return monitor
        def received(*args, **kwargs):
            if construction == 'receiver':
                observe('receiver_constructor')
                raise construction_body
            return receiver
        for label, target, name in (('monitor_close', monitor, 'close'),
                ('resource_wait', receiver, 'wait'), ('resource_close', receiver, 'close'),
                ('scope_collected', task, 'collected'), ('scope_close', task, 'close')):
            original = getattr(target, name)
            def operation(*args, _label=label, _original=original, **kwargs):
                observe(_label)
                answer = _original(*args, **kwargs)
                if fault == _label:
                    raise OSError('private cleanup detail')
                if fault == _label + '_false':
                    return False
                return answer
            setattr(target, name, operation)
        if fault == 'scope_state':
            task.cleanup_state = 'unknown'
        if fault == 'resource_terminal':
            receiver.receipt = lambda: dict(channel_status='complete',
                payload_started=None, terminal='cleanup_failed')
        def run(argv, **kwargs):
            if argv == ['/usr/bin/systemctl', '--user', 'show']:
                observe('manager_process')
                self.manager_keywords.append(dict(kwargs))
                hook = kwargs.get('on_cleanup_unknown')
                if manager_notification and callable(hook):
                    hook()
                if manager_body is not None:
                    raise manager_body
                return manager_answer or broker.ExecutionResult(0, '', 0,
                    None, False, True, None, raw_output=b'fixture-manager')
            observe('launch')
            kwargs['before_spawn']()
            if notification:
                kwargs['on_cleanup_unknown']()
            if body is not None:
                raise body
            return result or broker.ExecutionResult(0, '', 0, None, False, True, None)
        def create_scope(*, limit, query):
            observe('scope_constructor')
            if construction == 'scope':
                raise construction_body
            def request():
                return query(['/usr/bin/systemctl', '--user', 'show'],
                    dict(task.environment), time.monotonic() + 2)
            if manager_stage == 'constructor':
                request()  # task_scope assignment has not completed yet.
            elif manager_stage == 'wrap':
                original_wrap = task.wrap
                def queried_wrap(helper):
                    request()
                    return original_wrap(helper)
                task.wrap = queried_wrap
            return task
        original_wrapper = self.wrapper
        def wrapped_wrapper(*args, **kwargs):
            self.assertEqual(set(kwargs), {'helper_object'})
            command = original_wrapper(*args, **kwargs)
            if mutation is not None:
                mutation(command)
            return command
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(self, 'wrapper', side_effect=wrapped_wrapper))
                opening = stack.enter_context(patch.object(factory,
                    'open_linux_helper_object', side_effect=AssertionError('borrow must not factory')))
                closing = stack.enter_context(patch.object(view._scope._owner,
                    'close', side_effect=AssertionError('broker must not close helper')))
                stack.enter_context(patch('icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel', side_effect=channel))
                stack.enter_context(patch('icode.linux_task_resource.create_task_resource_channel', side_effect=channel))
                stack.enter_context(patch('icode.linux_seccomp_notify.LinuxSeccompViolationMonitor', side_effect=monitored))
                stack.enter_context(patch('icode.linux_task_scope.LinuxTaskScope', side_effect=create_scope))
                stack.enter_context(patch('icode.linux_task_resource.LinuxTaskResourceReceiver', side_effect=received))
                stack.enter_context(patch.object(broker, '_execute_policy_command', side_effect=run))
                answer, error = dispatch.capture(lambda: self.call(resource, view, **(changes or {})))
                opening.assert_not_called()
                closing.assert_not_called()
            self.assertFalse(view._scope._inflight)
            self.assertEqual(view._scope._owner_state, 'active')
            os.fstat(view._scope._owner.fileno())
            os.fstat(self.session.workspace_fd)
            self.session.lease._validate_active()
            self.assertTrue(all(endpoint.fileno() == -1 for endpoint in channels))
            for endpoint in channels:
                if hasattr(endpoint, 'attempts'):
                    self.assertEqual(endpoint.attempts, 1)
            return answer, error, events
        finally:
            # Test-owned final fixture release is separate from broker credit;
            # this helper retains the original known-live FD for injected faults.
            dispatch.cleanup_test_channels(channels)

    def test_sequential_both_entries_same_owner_and_creator_closes_last(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        for resource in (False, True, False, True):
            answer, error, events = self.exercise(resource, view)
            self.assertIsNone(error)
            self.assertIsNone(answer.error)
            self.assertEqual(self.owners, [scope._owner])
            self.assertIn('monitor_close', events)
            self.assertEqual(scope._consume_state, 'attached_bound')
        descriptor = scope._owner.fileno()
        view.finish()
        scope.close()
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)
        os.fstat(self.session.workspace_fd)
        self.session.lease._validate_active()

    def test_reject_caller_facts_before_channels_and_no_fallback(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        wrong = ({'workspace_session': None}, {'workspace_session': replace(self.session)},
            {'policy': replace(self.policy)}, {'prepared_attempt': None},
            {'prepared_attempt': 'other-attempt'}, {'prepared_step': scope},
            {'prepared_step': object()}, {'sandbox': object()})
        for resource in (False, True):
            for change in wrong:
                with self.subTest(resource=resource, names=tuple(change)):
                    answer, error, events = self.exercise(resource, view, changes=change)
                    self.assertIsNone(error)
                    self.assertEqual(answer.error, 'isolation_unavailable')
                    self.assertIs(answer.payload_started, False)
                    self.assertEqual(events, [])
        self.assertEqual(scope._consume_state, 'attached_bound')

    def test_pending_spent_and_active_reentry_reject_before_channels(self):
        scope = self.prepare()
        view = self.attach(scope)
        answer, error, events = self.exercise(False, view)
        self.assertIsNone(error)
        self.assertEqual(answer.error, 'isolation_unavailable')
        self.assertEqual(events, [])
        self.bind(view)
        with self.borrow(view):
            with patch('icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel') as channels:
                answer = self.call(False, view)
            channels.assert_not_called()
            self.assertEqual(answer.error, 'isolation_unavailable')
        view.finish()
        answer, error, events = self.exercise(True, view)
        self.assertIsNone(error)
        self.assertEqual(answer.error, 'isolation_unavailable')
        self.assertEqual(events, [])

    def test_body_errors_and_signals_without_unknown_remain_borrowable(self):
        for body in (RuntimeError('private body'), KeyboardInterrupt(), SystemExit(19)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            answer, error, events = self.exercise(True, view, body=body)
            self.assertIsNone(answer)
            self.assertIs(error, body)
            self.assertEqual(scope._consume_state, 'attached_bound')
            self.assertIn('scope_close', events)
            with self.borrow(view) as owner:
                self.assertIs(owner, scope._owner)

    def test_borrowed_wrapper_binding_rejects_without_owner_replacement(self):
        def swapped(command):
            command.helper_object = object()
        def duplicated(command):
            command.pass_fds += command.pass_fds
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        for resource in (False, True):
            for mutation in (swapped, duplicated):
                with self.subTest(resource=resource, mutation=mutation.__name__):
                    answer, error, events = self.exercise(resource, view, mutation=mutation)
                    self.assertIsNone(error)
                    self.assertEqual(answer.error, 'isolation_unavailable')
                    self.assertIs(answer.payload_started, False)
                    self.assertNotIn('launch', events)
                    self.assertEqual(scope._consume_state, 'attached_bound')
        with self.borrow(view) as owner:
            self.assertIs(owner, scope._owner)

    def test_cleanup_unknown_matrix_blocks_next_command_but_keeps_owner(self):
        faults = ('monitor_close', 'monitor_close_false', 'resource_wait',
            'resource_close', 'resource_close_false', 'scope_collected',
            'scope_collected_false', 'scope_close', 'scope_state', 'resource_terminal',
            'endpoint_close')
        for fault in faults:
            with self.subTest(fault=fault):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                answer, error, events = self.exercise(True, view, fault=fault)
                self.assertEqual(scope._consume_state, 'faulted')
                self.assertIn('scope_close', events)
                self.assertIn('monitor_close', events)
                with self.assertRaises(prepared.LinuxPreparedStepError):
                    with self.borrow(view):
                        pass
                second, second_error, second_events = self.exercise(False, view)
                self.assertIsNone(second_error)
                self.assertEqual(second.error, 'isolation_unavailable')
                self.assertEqual(second_events, [])
                view.finish()
                self.assertEqual(scope._consume_state, 'faulted')
                scope.close()
                self.assertEqual(scope._owner_state, 'closed')

    def test_first_signal_and_unknown_keep_original_and_all_cleanup(self):
        for body in (KeyboardInterrupt(), SystemExit(71)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            answer, error, events = self.exercise(True, view,
                body=body, fault='resource_close')
            self.assertIsNone(answer)
            self.assertIs(error, body)
            self.assertEqual(scope._consume_state, 'faulted')
            self.assertIn('monitor_close', events)
            self.assertIn('scope_close', events)

    def test_ordinary_body_cannot_hide_cleanup_unknown(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        body = RuntimeError('private body')
        for fault in ('scope_close', 'scope_collected', 'resource_close', 'endpoint_close'):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            answer, error, events = self.exercise(True, view, body=body, fault=fault)
            self.assertIsNone(answer)
            self.assertIsInstance(error, factory.LinuxHelperObjectError)
            self.assertIsNot(error, body)
            self.assertEqual(scope._consume_state, 'faulted')
            self.assertNotIn('private', str(error))

    def test_process_unknown_result_and_signal_notification_fault_attachment(self):
        for body in (None, KeyboardInterrupt(), SystemExit(29)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            answer, error, events = self.exercise(False, view, body=body,
                notification=True, result=broker.ExecutionResult(0, '', 0,
                    'cleanup_failed', False, False, errno.EBUSY))
            self.assertEqual(scope._consume_state, 'faulted')
            if body is not None:
                self.assertIs(error, body)
            else:
                self.assertIsNone(error)
                self.assertIs(answer.cleanup_ok, False)

    def test_manager_constructor_unknown_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.precheck_fixture()
        answer, error, events = self.exercise(True, view, manager_stage='constructor',
            manager_answer=broker.ExecutionResult(None, '', 0,
                'cleanup_failed', False, False, errno.EBUSY))
        self.assertIsNone(error)
        self.assertEqual(answer.error, 'isolation_unavailable')
        self.assertEqual(events, ['scope_constructor', 'manager_process'])
        self.assertEqual(len(self.manager_keywords), 1)
        self.assertEqual(scope._owner_state, 'active')
        self.assertFalse(scope._inflight)
        # This is the effective target on the reachable Task2 intermediate.
        self.assertEqual(scope._consume_state, 'faulted')

    def test_manager_later_unknown_blocks_next_command(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        answer, error, events = self.exercise(True, view, manager_stage='wrap',
            manager_answer=broker.ExecutionResult(None, '', 0,
                'cleanup_failed', False, False, errno.EBUSY))
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertIn('scope_close', events)
        self.assertEqual(len(self.manager_keywords), 1)
        self.assertNotIn('launch', events)
        with self.assertRaises(prepared.LinuxPreparedStepError):
            with self.borrow(view):
                pass

    def test_manager_ordinary_body_with_unknown_notice_cannot_hide_cleanup(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        answer, error, events = self.exercise(True, view, manager_stage='constructor',
            manager_body=Exception('private manager body'), manager_notification=True)
        self.assertIsNone(answer)
        self.assertIsInstance(error, factory.LinuxHelperObjectError)
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertNotIn('private', str(error))

    def test_manager_signal_with_unknown_notice_keeps_original_and_faulted(self):
        for stage in ('constructor', 'wrap'):
            for first in (KeyboardInterrupt(), SystemExit(61)):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                answer, error, events = self.exercise(True, view,
                    manager_stage=stage, manager_body=first, manager_notification=True)
                self.assertIsNone(answer)
                self.assertIs(error, first)
                self.assertEqual(len(self.manager_keywords), 1)
                self.assertEqual(scope._consume_state, 'faulted')
                if stage == 'wrap':
                    self.assertIn('scope_close', events)

    def test_construction_manager_ordinary_failure_consumes_without_cleanup_claim(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        answer, error, events = self.exercise(True, view,
            manager_stage='constructor', manager_body=RuntimeError('private manager body'))
        self.assertIsNone(error)
        self.assertEqual(answer.error, 'isolation_unavailable')
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertEqual(events, ['scope_constructor', 'manager_process'])

    def test_construction_seccomp_real_unreturned_socket_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.precheck_fixture()
        held, attempts = [], []
        actual_pair = seccomp.socket.socketpair
        actual_set_inheritable = seccomp.os.set_inheritable
        class UnknownHost(seccomp.socket.socket):
            def close(self):
                attempts.append(self.fileno())
                raise OSError('private factory close')
        def pair(*args, **kwargs):
            host, sender = actual_pair(*args, **kwargs)
            host = UnknownHost(fileno=host.detach())
            held.extend((host, sender))
            return host, sender
        def inheritable(descriptor, value):
            if held and descriptor == held[0].fileno():
                raise OSError('private factory initialization')
            return actual_set_inheritable(descriptor, value)
        try:
            with patch.object(seccomp.socket, 'socketpair', side_effect=pair), \
                    patch.object(seccomp.os, 'set_inheritable', side_effect=inheritable), \
                    patch.object(factory, 'open_linux_helper_object') as opening, \
                    patch.object(scope._owner, 'close') as closing:
                answer, error = dispatch.capture(lambda: self.call(False, view))
            opening.assert_not_called()
            closing.assert_not_called()
            self.assertIsNone(error)
            self.assertEqual(answer.error, 'isolation_unavailable')
            self.assertEqual(len(held), 2)
            descriptor = held[0].fileno()
            self.assertEqual(attempts, [descriptor])
            self.assertTrue(stat.S_ISSOCK(os.fstat(descriptor).st_mode))
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, 'active')
            os.fstat(scope._owner.fileno())
            os.fstat(self.session.workspace_fd)
            self.assertEqual(scope._consume_state, 'faulted')
            with self.assertRaises(prepared.LinuxPreparedStepError):
                with self.borrow(view):
                    pass
        finally:
            # Test hygiene only; A does not recover this unreturned socket.
            for endpoint in held:
                seccomp.socket.socket.close(endpoint)

    def test_construction_scope_real_unreturned_tool_fd_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.precheck_fixture()
        held = []
        actual_close = task_module.os.close
        def closing(descriptor):
            if os.readlink('/proc/self/fd/' + str(descriptor)) == '/usr/bin/systemd-run':
                held.append(descriptor)
                raise OSError('private trusted-tool close')
            return actual_close(descriptor)
        try:
            with patch.object(task_module.os, 'close', side_effect=closing), \
                    patch.object(factory, 'open_linux_helper_object') as opening, \
                    patch.object(scope._owner, 'close') as helper_close:
                answer, error = dispatch.capture(lambda: self.call(True, view))
            opening.assert_not_called()
            helper_close.assert_not_called()
            self.assertIsNone(error)
            self.assertEqual(answer.error, 'isolation_unavailable')
            self.assertEqual(len(held), 1)
            self.assertTrue(stat.S_ISREG(os.fstat(held[0]).st_mode))
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, 'active')
            os.fstat(scope._owner.fileno())
            self.session.lease._validate_active()
            self.assertEqual(scope._consume_state, 'faulted')
            with self.assertRaises(prepared.LinuxPreparedStepError):
                with self.borrow(view):
                    pass
        finally:
            # Explicit saved test-owned FD release; not broker cleanup credit.
            for descriptor in held:
                actual_close(descriptor)

    def test_construction_five_failures_consume_and_keep_received_signals(self):
        for construction in ('scope', 'resource_channel', 'seccomp_channel', 'receiver', 'monitor'):
            for body in (RuntimeError('private constructor'), KeyboardInterrupt(), SystemExit(67)):
                with self.subTest(construction=construction, kind=type(body).__name__):
                    scope = self.prepare()
                    view = self.bind(self.attach(scope))
                    answer, error, events = self.exercise(True, view,
                        construction=construction, construction_body=body)
                    self.assertEqual(scope._consume_state, 'faulted')
                    if isinstance(body, Exception):
                        self.assertIsNone(error)
                        self.assertEqual(answer.error, 'isolation_unavailable')
                    else:
                        self.assertIsNone(answer)
                        self.assertIs(error, body)
                    if construction != 'scope':
                        self.assertIn('scope_close', events)
                    with self.assertRaises(prepared.LinuxPreparedStepError):
                        with self.borrow(view):
                            pass

    def test_construction_real_factory_received_signal_keeps_identity(self):
        for first in (KeyboardInterrupt(), SystemExit(71)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            actual_pair = seccomp.socket.socketpair
            actual_set = seccomp.os.set_inheritable
            held = []
            def pair(*args, **kwargs):
                endpoints = actual_pair(*args, **kwargs)
                held.extend(endpoints)
                return endpoints
            def inheritable(descriptor, value):
                if held and descriptor == held[0].fileno():
                    raise first
                return actual_set(descriptor, value)
            try:
                with patch.object(seccomp.socket, 'socketpair', side_effect=pair), \
                        patch.object(seccomp.os, 'set_inheritable', side_effect=inheritable):
                    answer, error = dispatch.capture(lambda: self.call(False, view))
                self.assertIsNone(answer)
                self.assertIs(error, first)
                self.assertTrue(all(endpoint.fileno() == -1 for endpoint in held))
                self.assertEqual(scope._consume_state, 'faulted')
                self.assertFalse(scope._inflight)
            finally:
                for endpoint in held:
                    seccomp.socket.socket.close(endpoint)

    def test_construction_old_none_keeps_original_factory_failure_contract(self):
        for first in (RuntimeError('old ctor'), KeyboardInterrupt(), SystemExit(73)):
            with patch.object(task_module, 'LinuxTaskScope', side_effect=first), \
                    patch('icode.linux_task_resource.create_task_resource_channel') as channels:
                answer, error = dispatch.capture(lambda: broker.execute_linux_resource_observed_command(
                    ['/usr/bin/true'], cwd=self.session.workspace_root, sandbox=self.sandbox,
                    policy=self.policy, timeout=1, command_wrapper=self.wrapper))
            channels.assert_not_called()
            if isinstance(first, Exception):
                self.assertIsNone(error)
                self.assertEqual(answer.error, 'isolation_unavailable')
            else:
                self.assertIsNone(answer)
                self.assertIs(error, first)
            os.fstat(self.session.workspace_fd)
            self.session.lease._validate_active()

    def test_old_none_manager_query_does_not_add_notification_keyword(self):
        held, keywords = [], []
        actual_factory = factory.open_linux_helper_object
        def opening(*args):
            owner = actual_factory(*args)
            held.append((owner, owner.fileno()))
            return owner
        def run(argv, **kwargs):
            keywords.append(dict(kwargs))
            return broker.ExecutionResult(0, '', 0, None, False, True, None,
                raw_output=b'fixture-manager')
        def create_scope(*, limit, query):
            query(['/usr/bin/systemctl', '--user', 'show'], {}, time.monotonic() + 2)
            raise RuntimeError('stop fixture before channels')
        with patch.object(factory, 'open_linux_helper_object', side_effect=opening), \
                patch('icode.linux_task_scope.LinuxTaskScope', side_effect=create_scope), \
                patch.object(broker, '_execute_policy_command', side_effect=run), \
                patch('icode.linux_task_resource.create_task_resource_channel') as channels:
            answer = broker.execute_linux_resource_observed_command(['/usr/bin/true'],
                cwd=self.session.workspace_root, sandbox=self.sandbox,
                policy=self.policy, timeout=1, command_wrapper=self.wrapper)
        self.assertEqual(answer.error, 'isolation_unavailable')
        channels.assert_not_called()
        self.assertEqual(len(keywords), 1)
        self.assertNotIn('on_cleanup_unknown', keywords[0])
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0][0]._state, 'closed')
        with self.assertRaises(OSError) as caught:
            os.fstat(held[0][1])
        self.assertEqual(caught.exception.errno, errno.EBADF)
        os.fstat(self.session.workspace_fd)

    def test_process_core_unknown_notifies_and_notification_fault_keeps_cleanup(self):
        actual_core = broker._execute_policy_command
        for body in (None, KeyboardInterrupt(), SystemExit(37)):
            for notice_error in (None, RuntimeError('private notification'),
                    KeyboardInterrupt(), SystemExit(41)):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                calls, processes = [], []
                actual_popen, actual_stop = broker.subprocess.Popen, broker._stop_group
                def popen(*args, **kwargs):
                    process = actual_popen(*args, **kwargs)
                    processes.append(process)
                    return process
                def stop(process):
                    actual_stop(process)
                    return False, errno.EBUSY
                def notice():
                    self.assertTrue(scope._inflight)
                    calls.append('unknown')
                    view._mark_faulted()
                    if notice_error is not None:
                        raise notice_error
                def spawned(process, deadline):
                    if body is not None:
                        raise body
                with self.borrow(view), patch.object(broker.subprocess, 'Popen', side_effect=popen), \
                        patch.object(broker, '_stop_group', side_effect=stop):
                    answer, error = dispatch.capture(lambda: actual_core(
                        [sys.executable, '-c', 'pass'], cwd=self.session.workspace_root,
                        policy=self.policy, timeout=1, on_spawn=spawned,
                        on_cleanup_unknown=notice))
                self.assertEqual(calls, ['unknown'])
                self.assertEqual(scope._consume_state, 'faulted')
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0].poll())
                self.assertTrue(processes[0].stdout.closed)
                if body is not None:
                    self.assertIs(error, body)
                elif notice_error is not None:
                    self.assertIs(error, notice_error)
                else:
                    self.assertIsNone(error)
                    self.assertIs(answer.cleanup_ok, False)

    def test_process_first_cleanup_signal_precedes_notification_signal(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        first, second = KeyboardInterrupt(), SystemExit(53)
        actual_stop, actual_popen = broker._stop_group, broker.subprocess.Popen
        processes = []
        def popen(*args, **kwargs):
            process = actual_popen(*args, **kwargs)
            processes.append(process)
            return process
        def stop(process):
            actual_stop(process)
            raise first
        def notice():
            self.assertTrue(scope._inflight)
            view._mark_faulted()
            raise second
        with self.borrow(view), patch.object(broker.subprocess, 'Popen', side_effect=popen), \
                patch.object(broker, '_stop_group', side_effect=stop):
            answer, error = dispatch.capture(lambda: broker._execute_policy_command(
                [sys.executable, '-c', 'pass'], cwd=self.session.workspace_root,
                policy=self.policy, timeout=1, on_cleanup_unknown=notice))
        self.assertIsNone(answer)
        self.assertIs(error, first)
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdout.closed)

    def test_process_selector_stop_and_pipe_unknown_each_notify(self):
        for stage in ('selector_close', 'stop_raise', 'pipe_close'):
            with self.subTest(stage=stage):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                fault = RuntimeError('private owned cleanup')
                calls, processes = [], []
                selector = broker.selectors.DefaultSelector()
                actual_selector_close = selector.close
                actual_stop, actual_popen = broker._stop_group, broker.subprocess.Popen
                class FaultPipe:
                    def __init__(self, stream):
                        self.stream = stream
                    def __getattr__(self, name):
                        return getattr(self.stream, name)
                    def close(self):
                        self.stream.close()
                        raise fault
                def popen(*args, **kwargs):
                    process = actual_popen(*args, **kwargs)
                    if stage == 'pipe_close':
                        process.stdout = FaultPipe(process.stdout)
                    processes.append(process)
                    return process
                def stop(process):
                    answer = actual_stop(process)
                    if stage == 'stop_raise':
                        raise fault
                    return answer
                def selector_close():
                    actual_selector_close()
                    if stage == 'selector_close':
                        raise fault
                def notice():
                    self.assertTrue(scope._inflight)
                    calls.append(stage)
                    view._mark_faulted()
                try:
                    with self.borrow(view), patch.object(broker.subprocess, 'Popen', side_effect=popen), \
                            patch.object(broker, '_stop_group', side_effect=stop), \
                            patch.object(broker.selectors, 'DefaultSelector', return_value=selector), \
                            patch.object(selector, 'close', side_effect=selector_close):
                        answer, error = dispatch.capture(lambda: broker._execute_policy_command(
                            [sys.executable, '-c', 'pass'], cwd=self.session.workspace_root,
                            policy=self.policy, timeout=1, on_cleanup_unknown=notice))
                    self.assertIsNone(answer)
                    self.assertIs(error, fault)
                    self.assertEqual(calls, [stage])
                    self.assertEqual(scope._consume_state, 'faulted')
                    self.assertIsNotNone(processes[0].returncode)
                    self.assertTrue(processes[0].stdout.closed)
                finally:
                    actual_selector_close()
                    for process in processes:
                        actual_stop(process)
                        stream = getattr(process.stdout, 'stream', process.stdout)
                        stream.close()

    def test_old_none_public_core_keyword_shape_remains_unchanged(self):
        for resource in (False, True):
            entry = self.entry(resource)
            with patch.object(broker, '_execute_linux_observed_command', return_value=object()) as core:
                entry(['/usr/bin/true'], cwd=self.session.workspace_root,
                    sandbox=self.sandbox, policy=self.policy, timeout=1,
                    command_wrapper=self.wrapper)
            for name in ('prepared_step', 'workspace_session', 'prepared_attempt'):
                self.assertNotIn(name, core.call_args.kwargs)
