"""S2a thin adapter software contract; no CP/native/installed credit."""
from __future__ import annotations

from dataclasses import fields, replace
import inspect
import os
import sys
import unittest
from unittest.mock import patch

from icode import runner
from icode.tools import builtin
from icode.tools.base import IsolationUnavailable, ToolContext

LINUX = sys.platform.startswith('linux') and callable(getattr(os, 'pread', None))
if LINUX:
    from tests import test_linux_prepared_step as fixture
    from tests import test_linux_prepared_broker as broker_fixture
    from icode import execution_broker as broker
    from icode import linux_helper_object as factory
    from icode import linux_prepared_step as prepared


@unittest.skipUnless(LINUX, 'Linux software fixture; skip is not acceptance')
class PreparedToolContextTests(unittest.TestCase):
    if LINUX:
        setUp = fixture.PreparedTests.setUp
        write_image = fixture.PreparedTests.write_image
        precheck_fixture = fixture.PreparedTests.precheck_fixture
        cleanup_scopes = fixture.PreparedTests.cleanup_scopes
        prepare = fixture.PreparedTests.prepare
        attach = fixture.PreparedTests.attach
        bind = fixture.PreparedTests.bind
        borrow = fixture.PreparedTests.borrow
        exercise = broker_fixture.PreparedBrokerTests.exercise
        wrapper = broker_fixture.PreparedBrokerTests.wrapper

    def context(self, view=None, attempt=None, **changes):
        ctx = ToolContext(root=self.session.workspace_root, sandbox=self.sandbox,
            policy=self.policy, workspace_session=self.session)
        # Actual baseline dispatch is exercised without constructor TypeError.
        ctx.prepared_step, ctx.prepared_attempt = view, attempt
        for name, value in changes.items():
            setattr(ctx, name, value)
        return ctx

    def dispatch(self, ctx, **options):
        return builtin._controlled_dispatch(ctx, ['/usr/bin/true'],
            cwd=self.session.workspace_root, timeout=1, **options)

    def call(self, resource, view, **changes):
        self.assertIs(resource, True)
        ctx = getattr(self, 'closed_context', None)
        if ctx is None:
            ctx = self.context(view, 'software-attempt', **changes)
        ctx.wrap_command_with_resource_receipt = self.wrapper
        return self.dispatch(ctx)

    def test_old_eleven_positional_mapping_and_new_field_contract(self):
        values = (self.session.workspace_root, 77, self.sandbox, self.policy,
            object(), {'a': 'b'}, False, True, (), self.session, None)
        ctx = ToolContext(*values)
        names = ('root', 'output_limit', 'sandbox', 'policy', 'artifact_broker',
            'change_baseline', 'read_only_workspace', 'review_submission_enabled',
            'deny_read_roots', 'workspace_session', 'allowed_read_files')
        for name, value in zip(names, values):
            self.assertIs(getattr(ctx, name), value)
        by_name = {item.name: item for item in fields(ToolContext)}
        self.assertIn('prepared_step', by_name)
        self.assertIn('prepared_attempt', by_name)
        for name in ('prepared_step', 'prepared_attempt'):
            self.assertTrue(by_name[name].kw_only)
            self.assertFalse(by_name[name].repr)
            self.assertIsNone(by_name[name].default)
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        ctx = ToolContext(*values, prepared_step=view, prepared_attempt='software-attempt')
        self.assertIs(ctx.prepared_step, view)
        self.assertNotIn('prepared_step=', repr(ctx))
        self.assertNotIn('prepared_attempt=', repr(ctx))
        with self.assertRaises(TypeError):
            ToolContext(*values, view, 'software-attempt')

    def test_make_ctx_same_references_no_lifecycle_and_none_old_kwargs(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        old = dict(root=self.session.workspace_root, sandbox=self.sandbox,
            policy=self.policy, artifact_broker=None, change_baseline=None,
            read_only_workspace=False, review_submission_enabled=False,
            deny_read_roots=(), allowed_read_files=None, workspace_session=self.session)
        supported = inspect.signature(runner._make_ctx).parameters
        for step, attempt in ((None, None), (view, 'software-attempt'), (None, '')):
            passed = {'prepared_step': step, 'prepared_attempt': attempt}
            passed = {name: value for name, value in passed.items() if name in supported}
            with patch.object(runner, 'ToolContext', return_value=object()) as constructor, \
                    patch.object(prepared, 'open_linux_helper_object') as opening, \
                    patch.object(scope, '_attach') as attaching, \
                    patch.object(view, '_bind_attempt') as binding:
                runner._make_ctx(self.session.workspace_root, self.sandbox,
                    policy=self.policy, workspace_session=self.session, **passed)
            expected = dict(old)
            if step is not None or attempt is not None:
                expected.update(prepared_step=step, prepared_attempt=attempt)
            self.assertEqual(constructor.call_args.kwargs, expected)
            opening.assert_not_called()
            attaching.assert_not_called()
            binding.assert_not_called()
        kwargs = dict(policy=self.policy, workspace_session=self.session)
        kwargs.update({name: value for name, value in
            (('prepared_step', view), ('prepared_attempt', 'software-attempt'))
            if name in supported})
        actual = runner._make_ctx(self.session.workspace_root, self.sandbox, **kwargs)
        self.assertIs(getattr(actual, 'prepared_step', None), view)
        self.assertEqual(getattr(actual, 'prepared_attempt', None), 'software-attempt')

    def test_none_exact_resource_kwargs_with_output_and_cache(self):
        ctx = self.context()
        cache = self.session.workspace_root / 'cache'
        for output in (None, 900):
            for directory in (None, cache):
                with self.subTest(output=output, cache=directory):
                    with patch.object(builtin, 'execute_linux_resource_observed_command') as entry:
                        self.dispatch(ctx, output_limit_bytes=output,
                            verification_cache_root=directory)
                    expected = dict(cwd=self.session.workspace_root, sandbox=self.sandbox,
                        policy=self.policy, timeout=1,
                        command_wrapper=ctx.wrap_command_with_resource_receipt)
                    if output is not None:
                        expected['output_limit_bytes'] = output
                    if directory is not None:
                        expected['verification_cache_root'] = directory
                    self.assertEqual(entry.call_args.kwargs, expected)

    def test_none_exact_ordinary_kwargs_and_cache_refusal(self):
        ctx = self.context(sandbox=object())
        for output in (None, 900):
            with patch.object(ctx, 'wrap_command', return_value=['wrapped']) as wrapper, \
                    patch.object(builtin, 'execute_policy_command') as entry, \
                    patch.object(builtin, 'execute_linux_resource_observed_command') as resource:
                self.dispatch(ctx, output_limit_bytes=output)
            expected = dict(cwd=self.session.workspace_root, policy=self.policy, timeout=1)
            if output is not None:
                expected['output_limit_bytes'] = output
            self.assertEqual(entry.call_args.kwargs, expected)
            self.assertEqual(entry.call_args.args, (['wrapped'],))
            wrapper.assert_called_once()
            resource.assert_not_called()
        with patch.object(ctx, 'wrap_command') as wrapper, \
                patch.object(builtin, 'execute_policy_command') as entry:
            with self.assertRaises(IsolationUnavailable):
                self.dispatch(ctx, verification_cache_root=self.session.workspace_root / 'cache')
        wrapper.assert_not_called()
        entry.assert_not_called()

    def test_valid_dispatch_forwards_three_keywords_once_no_ordinary(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        ctx = self.context(view, 'software-attempt')
        with patch.object(builtin, 'execute_linux_resource_observed_command') as entry, \
                patch.object(builtin, 'execute_policy_command') as ordinary, \
                patch.object(view, 'borrow') as borrowing:
            self.dispatch(ctx)
        expected = dict(cwd=self.session.workspace_root, sandbox=self.sandbox,
            policy=self.policy, timeout=1, command_wrapper=ctx.wrap_command_with_resource_receipt,
            prepared_step=view, workspace_session=self.session,
            prepared_attempt='software-attempt')
        self.assertEqual(entry.call_args.kwargs, expected)
        entry.assert_called_once()
        ordinary.assert_not_called()
        borrowing.assert_not_called()

    def test_shape_and_mutated_context_reject_before_all_dispatch_calls(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        cases = [dict(prepared_step=None, prepared_attempt='software-attempt'),
            dict(prepared_step=None, prepared_attempt=''),
            dict(prepared_step=scope), dict(prepared_step=object()),
            dict(workspace_session=None), dict(workspace_session=object()),
            dict(read_only_workspace=True), dict(sandbox=object())]
        cases.extend(dict(prepared_attempt=value) for value in
            (None, '', ' ', True, 1, 'bad\nvalue', 'bad\x7fvalue'))
        for change in cases:
            with self.subTest(change=tuple(change)):
                ctx = self.context(view, 'software-attempt')
                for name, value in change.items():
                    setattr(ctx, name, value)
                with patch.object(ctx, '_policy_command_wrapper') as binding, \
                        patch.object(ctx, 'wrap_command') as wrapper, \
                        patch.object(builtin, 'execute_linux_resource_observed_command') as resource, \
                        patch.object(builtin, 'execute_policy_command') as ordinary, \
                        patch.object(factory, 'open_linux_helper_object') as opening, \
                        patch.object(broker, '_execute_policy_command') as payload:
                    with self.assertRaises(IsolationUnavailable) as caught:
                        self.dispatch(ctx)
                self.assertEqual(str(caught.exception), '准备对象工具上下文不可用')
                self.assertIsNone(caught.exception.__cause__)
                for spy in (binding, wrapper, resource, ordinary, opening, payload):
                    spy.assert_not_called()

    def test_wrong_identity_view_and_attempt_reach_unique_borrow_gate(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        other_scope = self.prepare()
        other_view = self.bind(self.attach(other_scope))
        # Well-shaped but genuinely stale view; helper/session remain active.
        other_view.finish()
        clone = replace(self.session)
        self.assertEqual(clone, self.session)
        self.assertIsNot(clone, self.session)
        self.assertIs(clone.lease, self.session.lease)
        self.assertIs(clone._workspace_object, self.session._workspace_object)
        cases = ((view, {'workspace_session': clone}),
            (other_view, {}), (view, {'prepared_attempt': 'other-attempt'}))
        for target, changes in cases:
            with self.subTest(changes=tuple(changes), stale=target is other_view):
                original = target.borrow
                with patch.object(target, 'borrow', wraps=original) as borrowing, \
                        patch.object(builtin, 'execute_policy_command') as ordinary, \
                        patch.object(builtin, 'execute_linux_resource_observed_command',
                            wraps=broker.execute_linux_resource_observed_command) as entry:
                    answer, error, events = self.exercise(True, target, changes=changes)
                entry.assert_called_once()
                borrowing.assert_called_once()
                ordinary.assert_not_called()
                self.assertIsNone(error)
                self.assertEqual(answer.error, 'isolation_unavailable')
                self.assertIs(answer.payload_started, False)
                self.assertEqual(events, [])
        self.assertEqual(scope._consume_state, 'attached_bound')
        self.session.lease._validate_active()

    def test_ctx_close_then_two_actual_dispatch_consumptions_owner_lives(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        ctx = self.context(view, 'software-attempt')
        helper_fd = scope._owner.fileno()
        with patch.object(view, 'finish') as finish, patch.object(scope, 'close') as close:
            ctx.close()
        finish.assert_not_called()
        close.assert_not_called()
        self.closed_context = ctx
        original = view.borrow
        for _ in range(2):
            with patch.object(view, 'borrow', wraps=original) as borrowing, \
                    patch.object(builtin, 'execute_policy_command') as ordinary, \
                    patch.object(builtin, 'execute_linux_resource_observed_command',
                        wraps=broker.execute_linux_resource_observed_command) as entry:
                answer, error, events = self.exercise(True, view)
            entry.assert_called_once()
            borrowing.assert_called_once()
            ordinary.assert_not_called()
            self.assertIsNone(error)
            self.assertIsNone(answer.error)
            self.assertEqual(self.owners, [scope._owner])
            self.assertIn('launch', events)
            self.assertIn('scope_close', events)
            self.assertEqual(scope._consume_state, 'attached_bound')
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, 'active')
            os.fstat(helper_fd)
            os.fstat(self.session.workspace_fd)
            self.session.lease._validate_active()
        # External fixture creator alone ends eligibility and owns final close.
        view.finish()
        self.assertEqual(scope._consume_state, 'spent')
        os.fstat(helper_fd)
        scope.close()
        self.assertEqual(scope._owner_state, 'closed')
        with self.assertRaises(OSError):
            os.fstat(helper_fd)
        os.fstat(self.session.workspace_fd)
        self.session.lease._validate_active()


if __name__ == '__main__':
    unittest.main()
