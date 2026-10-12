"""Real CP events and existing resources; no runner/installed/isolation credit."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests._support import REPO_ROOT
from icode.config import Settings
from icode.control import ControlError, ControlPlane, ControlResult, make_request
from icode.handshake import next_out_dir

MODULE = 'icode.linux_prepared_control'
if importlib.util.find_spec(MODULE) is None:
    binding = None
else:
    from icode.linux_prepared_control import _prepared_control_attempt_binding as binding

ERROR = 'Linux prepared control attempt is unavailable'
VENDOR = REPO_ROOT / 'vendor' / 'icode-skill'


class Guarded(unittest.TestCase):
    def require_binding(self):
        # A real assertion failure on the unchanged source, never ImportError RED.
        self.assertTrue(callable(binding), 'prepared binding callable is missing')
        return binding

    def raw(self, cp, out_dir, *, ticket='CP-PREPARED', step='plan', request='start-one'):
        target = getattr(cp, '_step_start_result', None)
        self.assertTrue(callable(target), 'raw step start callable is missing')
        return target(out_dir, step, ticket_id=ticket, request=request)

    def reject(self, call):
        with self.assertRaises(ControlError) as caught:
            call()
        error = caught.exception
        self.assertEqual(str(error), ERROR)
        self.assertIsNone(error.returncode)
        self.assertEqual(error.stderr, '')
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)


class RawCompatibilityTests(Guarded):
    def test_raw_keeps_result_identity_and_original_single_run_shape(self):
        cp = ControlPlane(Settings(VENDOR), check=False)
        target = getattr(cp, '_step_start_result', None)
        self.assertTrue(callable(target), 'raw step start callable is missing')
        for request in (None, '', 'explicit-request'):
            sentinel = object()
            result = ControlResult((), 7, {'attempt': sentinel})
            with patch.object(cp, 'run', return_value=result) as run:
                got = target(Path('/host/ticket'), 'plan', ticket_id='T', request=request)
            self.assertIs(got, result)
            self.assertIs(got.data['attempt'], sentinel)
            run.assert_called_once_with('step', '--dir', '/host/ticket', '--step',
                'plan', '--phase', 'start', '--request',
                request or make_request('T', 'step-plan-start'))

    def test_public_old_truthy_str_error_and_ok_semantics(self):
        cp = ControlPlane(Settings(VENDOR), check=False)
        self.assertTrue(ControlResult((), 0, {}).ok)
        self.assertTrue(ControlResult((), False, {'ok': 1}).ok)
        for value in ('attempt', ' ', 3, True, ['a'], {'a': 1}):
            result = ControlResult((), 0, {'attempt': value})
            with patch.object(cp, 'run', return_value=result) as run:
                self.assertEqual(cp.step_start('/host/ticket', 'plan', ticket_id='T'), str(value))
            run.assert_called_once_with('step', '--dir', '/host/ticket', '--step',
                'plan', '--phase', 'start', '--request', make_request('T', 'step-plan-start'))
        for value in (None, '', 0, False, [], {}):
            data = {'attempt': value}
            with patch.object(cp, 'run', return_value=ControlResult((), 0, data)):
                with self.assertRaises(ControlError) as caught:
                    cp.step_start('/host/ticket', 'plan', ticket_id='T')
            self.assertEqual(str(caught.exception), f'step start 未返回 attempt：{data}')
        for error in (ControlError('legacy body'), KeyboardInterrupt(), SystemExit(2)):
            with patch.object(cp, 'run', side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    cp.step_start('/host/ticket', 'plan', ticket_id='T')
            self.assertIs(caught.exception, error)


class RealCPTests(Guarded):
    def setUp(self):
        self.require_binding()
        self.assertTrue(Settings(VENDOR).exists(), 'fixed vendor fixture is unavailable')
        temporary = tempfile.TemporaryDirectory(prefix='icode_cp_prepared_')
        self.addCleanup(temporary.cleanup)
        self.cp_root = Path(temporary.name)
        self.out = next_out_dir(self.cp_root)
        self.ticket = 'CP-PREPARED'
        self.cp = ControlPlane(Settings(VENDOR))
        created = self.cp.create(self.out, ticket_id=self.ticket,
            requirement='isolated prepared control fixture', birth='plan')
        self.assertIs(created.data.get('ok'), True)
        self.start = self.raw(self.cp, self.out)
        self.attempt = self.start.data['attempt']

    def pair(self, result=None, **changes):
        args = dict(out_dir=self.out, ticket_id=self.ticket, step='plan',
            start_result=self.start if result is None else result)
        args.update(changes)
        return self.require_binding()(self.cp, **args)

    def stopped(self):
        finish = self.cp.step_finish(self.out, 'plan', self.attempt, 'blocked',
            ticket_id=self.ticket, request='finish-one', evidence=['software-fixture:closed'])
        self.assertIs(finish.data.get('ok'), True)

    def test_actual_start_replay_window_trace_and_new_attempt(self):
        self.assertNotIn('ticket_id', self.start.data)
        replay = self.raw(self.cp, self.out)
        self.assertNotIn('phase', replay.data)
        self.assertIs(replay.data.get('already_applied'), True)
        attempt, observer = self.pair(replay)
        self.assertEqual(attempt, self.attempt)
        # Append a real later event so limit=1 excludes the target start.
        updated = self.cp.step_check(self.out, 'plan', attempt, 'before_write',
            ticket_id=self.ticket, request='later-event')
        self.assertIs(updated.data.get('ok'), True)
        trace = self.cp.trace(self.out, limit=1)
        self.assertEqual(len(trace.data['events']), 1)
        self.assertNotEqual((trace.data['events'][0]).get('type'), 'step_started')
        self.assertIn(attempt, trace.data['open_steps'])
        self.assertNotIn('step', trace.data)
        with patch.object(self.cp, 'trace', wraps=self.cp.trace) as query:
            self.assertIsNone(observer(attempt))
            self.assertIsNone(observer(attempt))
            self.assertEqual(query.call_count, 2)
            query.assert_called_with(self.out, limit=1)
        self.stopped()
        self.reject(lambda: observer(attempt))
        newer = self.raw(self.cp, self.out, request='start-two')
        next_attempt, next_observer = self.pair(newer)
        self.assertNotEqual(next_attempt, attempt)
        self.assertIsNone(next_observer(next_attempt))
        self.reject(lambda: next_observer(attempt))
        self.reject(lambda: observer(next_attempt))
        self.reject(lambda: observer(attempt))

    def test_raw_bad_attempt_types_and_no_conversion(self):
        class NoString:
            def __str__(self):
                raise AssertionError('must never stringify an attempt')
        for value in (None, False, True, 0, 1, [], {}, NoString(), '', ' ', '\t', 'a\n', 'a\x7f'):
            with self.subTest(value_type=type(value).__name__):
                data = dict(self.start.data, attempt=value)
                self.reject(lambda: self.pair(ControlResult((), 0, data)))

    def test_start_receipt_type_returncode_ok_step_matrix(self):
        bad = [None, {}, object(), ControlResult((), 0, []),
            ControlResult((), False, self.start.data), ControlResult((), True, self.start.data),
            ControlResult((), 0.0, self.start.data), ControlResult((), 1, self.start.data)]
        for key, values in (('ok', (None, False, 1, 'true')),
                ('step', (None, True, 1, 'code', 'plan\n'))):
            missing = dict(self.start.data)
            missing.pop(key, None)
            bad.append(ControlResult((), 0, missing))
            bad.extend(ControlResult((), 0, dict(self.start.data, **{key: value})) for value in values)
        for result in bad:
            self.reject(lambda result=result: self.require_binding()(self.cp,
                out_dir=self.out, ticket_id=self.ticket, step='plan', start_result=result))

    def test_captured_coordinates_invalid_inputs_and_fresh_wrong_ticket_step(self):
        bind = self.require_binding()
        for key, values in (('ticket_id', (None, True, '', ' ', 'T\n')),
                ('step', (None, True, '', ' ', 'plan\n')),
                ('out_dir', (None, {}, '', ' ', '/host\n'))):
            for value in values:
                self.reject(lambda key=key, value=value: self.pair(**{key: value}))
        self.reject(lambda: bind({}, out_dir=self.out, ticket_id=self.ticket,
            step='plan', start_result=self.start))
        supplied = dict(out_dir=str(self.out), ticket_id=self.ticket, step='plan', start_result=self.start)
        attempt, observer = bind(self.cp, **supplied)
        supplied.update(out_dir=self.cp_root / 'other', ticket_id='OTHER', step='code')
        with patch.object(self.cp, 'trace', wraps=self.cp.trace) as query:
            self.assertIsNone(observer(attempt))
            query.assert_called_once_with(self.out, limit=1)
        _, wrong_ticket = self.pair(ticket_id='OTHER')
        self.reject(lambda: wrong_ticket(attempt))
        wrong_start = ControlResult((), 0, dict(self.start.data, step='code'))
        _, wrong_step = self.pair(wrong_start, step='code')
        self.reject(lambda: wrong_step(attempt))
        for actual in (None, True, 1, '', ' ', attempt + '-other'):
            with patch.object(self.cp, 'trace', wraps=self.cp.trace) as query:
                self.reject(lambda actual=actual: observer(actual))
                query.assert_not_called()

    def test_trace_strict_schema_negative_controls(self):
        attempt, observer = self.pair()
        original = self.cp.trace(self.out, limit=1)
        bad = [None, {}, object(), ControlResult((), 0, []),
            ControlResult((), False, original.data), ControlResult((), True, original.data),
            ControlResult((), 0.0, original.data),
            ControlResult((), 1, original.data)]
        for key, values in (('ok', (None, False, 1, 'true')),
                ('ticket_id', (None, True, 'OTHER')),
                ('open_steps', (None, [], {}, {attempt: None}, {attempt: []},
                    {attempt: {}}, {attempt: {'step': True}}, {attempt: {'step': 'code'}}))):
            missing = dict(original.data)
            missing.pop(key, None)
            bad.append(ControlResult((), 0, missing))
            bad.extend(ControlResult((), 0, dict(original.data, **{key: value})) for value in values)
        for result in bad:
            with patch.object(self.cp, 'trace', return_value=result) as query:
                self.reject(lambda: observer(attempt))
                query.assert_called_once_with(self.out, limit=1)
        # Recovery uses a fresh real query; a bad result never caches authority.
        self.assertIsNone(observer(attempt))

    def test_exact_dict_and_str_subclasses_rejected(self):
        class DictSubclass(dict):
            pass
        class StringSubclass(str):
            pass
        class IntSubclass(int):
            pass
        for result in (ControlResult((), 0, DictSubclass(self.start.data)),
                ControlResult((), IntSubclass(0), self.start.data),
                ControlResult((), 0, dict(self.start.data, step=StringSubclass('plan'))),
                ControlResult((), 0, dict(self.start.data, attempt=StringSubclass(self.attempt)))):
            self.reject(lambda result=result: self.pair(result))
        attempt, observer = self.pair()
        original = self.cp.trace(self.out, limit=1)
        for data in (DictSubclass(original.data), dict(original.data,
                ticket_id=StringSubclass(self.ticket)), dict(original.data,
                open_steps=DictSubclass(original.data['open_steps'])), dict(original.data,
                open_steps={attempt: DictSubclass(step='plan')}), dict(original.data,
                open_steps={attempt: {'step': StringSubclass('plan')}})):
            with patch.object(self.cp, 'trace', return_value=ControlResult((), 0, data)):
                self.reject(lambda: observer(attempt))

    def test_ordinary_fault_fixed_and_signals_original(self):
        attempt, observer = self.pair()
        for error in (ControlError('private path/body', stderr='private body'),
                OSError('private path/body'), ValueError('private receipt')):
            with patch.object(self.cp, 'trace', side_effect=error):
                self.reject(lambda: observer(attempt))
        for signal in (KeyboardInterrupt('private signal'), SystemExit(7)):
            with patch.object(self.cp, 'trace', side_effect=signal):
                with self.assertRaises(type(signal)) as caught:
                    observer(attempt)
            self.assertIs(caught.exception, signal)

    def test_actual_broken_event_chain_rejects_observer(self):
        attempt, observer = self.pair()
        self.assertIsNone(observer(attempt))
        events = self.out / '.ico_events.jsonl'
        # Deliberate fault injection in this newly owned temp ticket only.
        # This is not a product writer or an alternate observer/read path.
        with events.open('a', encoding='utf-8') as stream:
            stream.write('{invalid isolated event\n')
        self.reject(lambda: observer(attempt))


# Never import Linux-only fixture at module top on a non-Linux platform.
if sys.platform.startswith('linux'):
    from tests import test_linux_prepared_step as prepared_fixture

    class AttachmentCPTests(Guarded):
        def setUp(self):
            self.require_binding()
            self.resources = prepared_fixture.PreparedTests(methodName='runTest')
            self.addCleanup(self.resources.doCleanups)
            self.resources.setUp()
            self.resources.policy = self.resources.session.policy('plan', process_limit=16,
                wall_timeout_seconds=30, output_limit_bytes=4096)
            temporary = tempfile.TemporaryDirectory(prefix='icode_cp_attachment_')
            self.addCleanup(temporary.cleanup)
            self.out = next_out_dir(Path(temporary.name))
            self.ticket = self.resources.session.ticket_id
            self.cp = ControlPlane(Settings(VENDOR))
            self.cp.create(self.out, ticket_id=self.ticket,
                requirement='isolated actual attachment binding', birth='plan')
            self.start = self.raw(self.cp, self.out, ticket=self.ticket)
            self.attempt, self.observer = self.require_binding()(self.cp,
                out_dir=self.out, ticket_id=self.ticket, step='plan', start_result=self.start)
            self.scope = self.resources.prepare()
            self.assertEqual(self.resources.policy.step, self.start.data['step'])
            self.assertEqual(self.resources.policy.ticket_id, self.ticket)
            self.view = self.resources.attach(self.scope)
            self.helper_fd = self.scope._owner.fileno()

        def borrow(self, **changes):
            args = dict(policy=self.resources.policy,
                workspace_session=self.resources.session, attempt=self.attempt)
            args.update(changes)
            return self.view.borrow(**args)

        def owner_live(self):
            self.assertEqual(self.scope._owner_state, 'active')
            self.assertEqual(self.scope._owner.fileno(), self.helper_fd)
            prepared_fixture.REAL_FSTAT(self.helper_fd)
            self.resources.session.lease._validate_active()
            self.assertIsNotNone(self.resources.session.workspace_fd_identity)

        def finish_cp(self):
            self.cp.step_finish(self.out, 'plan', self.attempt, 'blocked',
                ticket_id=self.ticket, request='attachment-finish', evidence=['software-fixture:closed'])

        def test_real_bind_and_each_actual_borrow_requeries_then_external_close(self):
            with patch.object(self.cp, 'trace', wraps=self.cp.trace) as query:
                self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
                self.assertEqual(query.call_count, 1)
                for expected in (2, 3):
                    with self.borrow() as owner:
                        self.assertIs(owner, self.scope._owner)
                        self.assertEqual(query.call_count, expected)
                    self.owner_live()
                query.assert_called_with(self.out, limit=1)
            self.assertEqual(self.scope._consume_state, 'attached_bound')
            self.view.finish()
            self.owner_live()
            self.scope.close()
            with self.assertRaises(OSError):
                prepared_fixture.REAL_FSTAT(self.helper_fd)
            self.resources.session.lease._validate_active()

        def test_closed_or_broken_cp_before_wrapper_payload_owner_stays_external(self):
            self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            payload = []
            with self.borrow():
                payload.append('actual allowed borrow')
            self.finish_cp()
            with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                with self.borrow():
                    payload.append('wrapper/payload must not run')
            self.assertEqual(payload, ['actual allowed borrow'])
            self.owner_live()
            self.view.finish()
            self.owner_live()
            self.scope.close()
            with self.assertRaises(OSError):
                prepared_fixture.REAL_FSTAT(self.helper_fd)

        def test_chain_damage_after_bind_before_wrapper_payload(self):
            self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            events = self.out / '.ico_events.jsonl'
            # Intentional negative control, confined to this new temp ticket.
            with events.open('a', encoding='utf-8') as stream:
                stream.write('{invalid attachment fixture event\n')
            payload = []
            with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                with self.borrow():
                    payload.append('wrapper/payload must not run')
            self.assertEqual(payload, [])
            self.owner_live()
            self.view.finish()
            self.scope.close()

        def test_bind_fault_does_not_grant_bound_or_close_owner_and_signals_survive(self):
            for error in (OSError('private body'), KeyboardInterrupt(), SystemExit(3)):
                with patch.object(self.cp, 'trace', side_effect=error):
                    kind = prepared_fixture.subject.LinuxPreparedStepError if isinstance(error, Exception) else type(error)
                    with self.assertRaises(kind) as caught:
                        self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
                if not isinstance(error, Exception):
                    self.assertIs(caught.exception, error)
                self.assertEqual(self.scope._consume_state, 'attached_pending')
                self.assertIsNone(self.view._attempt)
                self.assertIsNone(self.view._validator)
                self.owner_live()
            self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            for signal in (KeyboardInterrupt(), SystemExit(4)):
                with patch.object(self.cp, 'trace', side_effect=signal):
                    with self.assertRaises(type(signal)) as caught:
                        with self.borrow():
                            self.fail('payload must not run')
                self.assertIs(caught.exception, signal)
                self.assertFalse(self.scope._inflight)
                self.owner_live()
            self.view.finish()
            self.scope.close()

        def test_actual_closed_cp_before_bind_remains_pending_external_owner_live(self):
            self.finish_cp()
            with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            self.assertEqual(self.scope._consume_state, 'attached_pending')
            self.assertIsNone(self.view._attempt)
            self.assertIsNone(self.view._validator)
            self.owner_live()
            self.view.finish()
            self.owner_live()
            self.scope.close()
            with self.assertRaises(OSError):
                prepared_fixture.REAL_FSTAT(self.helper_fd)

        def test_cp_success_does_not_replace_actual_session_policy_helper_gates(self):
            from dataclasses import replace
            self.view._bind_attempt(self.attempt, validate_attempt=self.observer)
            for changes in (dict(workspace_session=replace(self.resources.session)),
                    dict(policy=replace(self.resources.policy)), dict(attempt='other-attempt')):
                with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                    with self.borrow(**changes):
                        self.fail('payload must not run')
            self.owner_live()
            with self.borrow() as owner:
                self.assertIs(owner, self.scope._owner)
            # CP remains open, but actual held/source helper validation still wins.
            self.resources.write_image(prepared_fixture.image((1, 1)))
            self.assertIsNone(self.observer(self.attempt))
            with self.assertRaises(prepared_fixture.subject.LinuxPreparedStepError):
                with self.borrow():
                    self.fail('helper drift must block payload')
            self.view.finish()
            self.scope.close()


if __name__ == '__main__':
    unittest.main()
