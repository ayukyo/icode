"""Real resources/internal lifecycle; no CP, installed or runner credit."""
from __future__ import annotations
import copy
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import pickle
import stat
import struct
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from tests._support import temp_workspace
import icode.native_helper as locator
import icode.linux_helper_object as factory
import icode.linux_prepared_step as subject
from icode.isolation import LandlockSandbox
from icode.linux_static_helper import validate_static_linux_helper
from icode.linux_helper_source import observe_linux_helper_source
from icode.workspace import WorkspaceManager, _WorkspaceObject

REAL_CLOSE, REAL_FSTAT = os.close, os.fstat
ERROR = 'Linux prepared step is unavailable'

def image(types=(1,)):
    h = bytearray(64)
    h[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', h, 16, 2, 62, 1)
    struct.pack_into('<Q', h, 32, 64)
    struct.pack_into('<HHH', h, 52, 64, 56, len(types))
    return bytes(h) + b''.join(struct.pack('<IIQQQQQQ', t, 5, 0, 0, 0,
        64 + 56 * len(types), 64 + 56 * len(types), 4096) for t in types)

@unittest.skipUnless(sys.platform.startswith('linux') and callable(getattr(os, 'pread', None)),
    'Linux real resource fixture; skip is not acceptance')
class PreparedTests(unittest.TestCase):
    def setUp(self):
        d = temp_workspace()
        self.root = d.__enter__()
        self.addCleanup(d.__exit__, None, None, None)
        source = self.root / 'source'
        source.mkdir()
        (source / 'data.txt').write_text('real git fixture\n')
        for args in (('init', '-q'), ('add', 'data.txt'),
                ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.hooksPath=' + str(self.root / 'absent-hooks'),
                 'commit', '-qm', 'prepared fixture')):
            subprocess.run(['git', '-C', str(source), *args], check=True,
                capture_output=True, timeout=15)
        self.manager = WorkspaceManager(source, self.root / 'data',
            'prepared-project', isolate_git_metadata=True)
        self.session = self.manager.open('prepared-ticket', 'prepared-run')
        self.addCleanup(self.session.close)
        self.policy = self.session.policy('code', process_limit=16,
            wall_timeout_seconds=30, output_limit_bytes=4096)
        self.assertEqual(self.session.workspace_root, self.session.git_status_identity.code_root)
        self.assertFalse((self.session.workspace_root / '.git').exists())
        self.prefix = self.root / 'pipx' / 'venvs' / 'icode-agent'
        package = self.prefix / 'lib' / 'python3.11' / 'site-packages' / 'icode'
        native = package / 'native'
        native.mkdir(parents=True)
        module = package / 'native_helper.py'
        module.write_text('# actual locator mapping fixture\n')
        self.binary, self.manifest = native / 'icode-landlock', native / 'icode-landlock.sha256'
        self.write_image(image())
        for target, name, value in ((locator, '__file__', str(module)),
                (sys, 'prefix', str(self.prefix)), (sys, 'base_prefix', '/usr')):
            p = patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(factory.platform, 'machine', return_value='x86_64')
        p.start()
        self.addCleanup(p.stop)
        self.sandbox = LandlockSandbox(str(self.binary), manifest=str(self.manifest))
        self.scopes = []
        self.addCleanup(self.cleanup_scopes)
        self.precheck_fixture()

    def precheck_fixture(self):
        # Existing S0/S1a functions establish real fixture premises only.
        # This separate owner is closed here; it does not authorize the scaffold.
        self.policy.validate()
        self.sandbox.prepare_policy(self.policy)
        self.session.lease._validate_active()
        fd = self.session.workspace_fd
        self.assertIs(type(fd), int)
        self.assertGreaterEqual(fd, 3)
        held, path = REAL_FSTAT(fd), os.lstat(self.session.workspace_root)
        self.assertTrue(stat.S_ISDIR(held.st_mode))
        self.assertTrue(stat.S_ISDIR(path.st_mode))
        self.assertEqual((held.st_dev, held.st_ino), self.session.workspace_fd_identity)
        self.assertEqual((path.st_dev, path.st_ino), self.session.workspace_fd_identity)
        with factory.open_linux_helper_object(self.binary, self.manifest) as owner:
            validate_static_linux_helper(owner)
            observed = observe_linux_helper_source(self.sandbox, policy=self.policy, owner=owner)
            self.assertEqual(observed.helper_path, self.binary)
            self.assertEqual(observed.manifest_path, self.manifest)

    def write_image(self, data):
        self.binary.write_bytes(data)
        self.binary.chmod(0o700)
        self.manifest.write_text(hashlib.sha256(data).hexdigest() + '\n', encoding='ascii')

    def cleanup_scopes(self):
        for scope in self.scopes:
            if scope._owner_state == 'active':
                scope.close()

    def prepare(self):
        scope = subject.prepare_linux_step(self.sandbox,
            policy=self.policy, workspace_session=self.session)
        self.scopes.append(scope)
        return scope

    def attach(self, scope):
        return scope._attach(policy=self.policy, workspace_session=self.session)

    def bind(self, view):
        def validator(actual):
            if actual != 'software-attempt':
                raise RuntimeError('private attempt')
        view._bind_attempt('software-attempt', validate_attempt=validator)
        return view

    def borrow(self, view, **changes):
        args = dict(policy=self.policy, workspace_session=self.session, attempt='software-attempt')
        args.update(changes)
        return view.borrow(**args)

    def enter(self, context):
        with context:
            pass  # assertRaises outside must report the target "not raised".

    def reject(self, call):
        with self.assertRaises(subject.LinuxPreparedStepError) as caught:
            call()
        self.assertEqual(str(caught.exception), ERROR)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_wrong_session_reference_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        clone = replace(self.session)
        self.assertIs(clone.lease, self.session.lease)
        self.assertIs(clone._workspace_object, self.session._workspace_object)
        self.assertEqual(clone, self.session)
        self.reject(lambda: self.enter(self.borrow(view, workspace_session=clone)))
        with self.borrow(view) as owner:
            self.assertIs(owner, scope._owner)

    def test_equal_policy_reference_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        equal = replace(self.policy)
        self.assertEqual(equal.policy_hash, self.policy.policy_hash)
        self.reject(lambda: self.enter(self.borrow(view, policy=equal)))
        with self.borrow(view):
            pass

    def test_second_attach_active_owner_target(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        self.assertEqual(scope._owner_state, 'active')
        self.assertEqual(scope._consume_state, 'attached_bound')
        self.reject(lambda: self.attach(scope))
        self.assertIs(scope._attachment, view)

    def test_equal_policy_attach_target(self):
        scope = self.prepare()
        equal = replace(self.policy)
        self.assertEqual(equal.policy_hash, self.policy.policy_hash)
        self.reject(lambda: scope._attach(policy=equal, workspace_session=self.session))

    def test_same_owner_factory_once_and_borrowed_session_survives(self):
        original = subject.open_linux_helper_object
        opened = []
        def opening(*args):
            result = original(*args)
            opened.append(result)
            return result
        with patch.object(subject, 'open_linux_helper_object', side_effect=opening):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            fd = scope._owner.fileno()
            for _ in range(2):
                with self.borrow(view) as owner:
                    self.assertIs(owner, opened[0])
                    self.assertEqual(owner.fileno(), fd)
            self.assertEqual(len(opened), 1)
            self.assertEqual(scope._consume_state, 'attached_bound')
            view.finish()
            self.assertEqual(scope._consume_state, 'spent')
            self.assertEqual(scope._owner.fileno(), fd)
            scope.close()
            scope.close()
        self.assertEqual(scope._owner_state, 'closed')
        with self.assertRaises(OSError):
            REAL_FSTAT(fd)
        self.session.lease._validate_active()
        self.assertIsNotNone(self.session.workspace_fd_identity)

    def test_snapshot_nested_protection_is_not_removed(self):
        source = self.root / 'snapshot-source'
        source.mkdir()
        (source / 'data').write_text('snapshot')
        session = WorkspaceManager(source, self.root / 'snapshot-data', 'snapshot').open('ticket', 'run')
        try:
            policy = session.policy('code')
            self.assertIn(session.workspace_root / '.git', policy.protected_paths)
            self.reject(lambda: subject.prepare_linux_step(self.sandbox,
                policy=policy, workspace_session=session))
        finally:
            session.close()

    def test_bad_types_names_and_gates_before_factory(self):
        from types import SimpleNamespace
        from icode.sandbox_policy import NetworkMode
        root = self.session.workspace_root
        cases = ((SimpleNamespace(), self.policy, self.session),
            (self.sandbox, SimpleNamespace(), self.session),
            (self.sandbox, self.policy, SimpleNamespace()),
            (self.sandbox, replace(self.policy, run_id='other'), self.session),
            (self.sandbox, replace(self.policy, ticket_id='other'), self.session),
            (self.sandbox, replace(self.policy, write_roots=()), self.session),
            (self.sandbox, replace(self.policy, network_mode=NetworkMode.PROXY_ALLOWLIST,
                allowed_domains=('example.invalid',)), self.session),
            (self.sandbox, replace(self.policy, deny_write_roots=(*self.policy.deny_write_roots, root / 'nested'),
                protected_paths=(*self.policy.protected_paths, root / 'nested')), self.session))
        with patch.object(subject, 'open_linux_helper_object') as opening:
            for sandbox, policy, session in cases:
                self.reject(lambda: subject.prepare_linux_step(sandbox,
                    policy=policy, workspace_session=session))
            opening.assert_not_called()

    def test_lease_live_names_and_same_fields_new_lease_reference(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        original = self.session.lease
        clone = replace(original)
        self.assertIs(clone._stream, original._stream)
        self.session.lease = clone
        try:
            self.reject(lambda: self.enter(self.borrow(view)))
        finally:
            self.session.lease = original
        for target in (self.session, original):
            for field in ('project_id', 'ticket_id', 'run_id'):
                old = getattr(target, field)
                try:
                    setattr(target, field, old + '-drift')
                    self.reject(lambda: self.enter(self.borrow(view)))
                finally:
                    setattr(target, field, old)
        original.release()
        self.reject(lambda: self.enter(self.borrow(view)))
        self.reject(self.prepare)

    def test_workspace_same_fd_different_owner_reference(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        original = self.session._workspace_object
        self.session._workspace_object = _WorkspaceObject(original.descriptor, original.identity)
        try:
            self.reject(lambda: self.enter(self.borrow(view)))
        finally:
            self.session._workspace_object = original
        with self.borrow(view):
            pass

    def test_workspace_fd_values_identity_and_nofollow_path(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        obj, path = self.session._workspace_object, self.session.workspace_root
        original = obj.descriptor
        for value in (None, True, False, -1, 0, 1, 2):
            obj.descriptor = value
            try:
                self.reject(lambda: self.enter(self.borrow(view)))
            finally:
                obj.descriptor = original
        directory = self.root / 'wrong'
        directory.mkdir()
        for candidate in (directory, self.binary):
            fd = os.open(candidate, os.O_RDONLY)
            try:
                obj.descriptor = fd
                self.reject(lambda: self.enter(self.borrow(view)))
            finally:
                obj.descriptor = original
                REAL_CLOSE(fd)
        saved = path.with_name('saved-code')
        path.rename(saved)
        try:
            path.symlink_to(saved, target_is_directory=True)
            self.reject(lambda: self.enter(self.borrow(view)))
            path.unlink()
            path.mkdir()
            self.reject(lambda: self.enter(self.borrow(view)))
            path.rmdir()
        finally:
            saved.rename(path)
        with self.borrow(view):
            pass

    def test_closed_workspace_reused_fd_and_identity_drift(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        obj = self.session._workspace_object
        identity = obj.identity
        obj.identity = (identity[0], identity[1] + 1)
        try:
            self.reject(lambda: self.enter(self.borrow(view)))
        finally:
            obj.identity = identity
        other = self.root / 'different'
        other.mkdir()
        replacement = os.open(other, os.O_RDONLY | os.O_DIRECTORY)
        fd = obj.descriptor
        try:
            os.dup2(replacement, fd)
            self.reject(lambda: self.enter(self.borrow(view)))
        finally:
            REAL_CLOSE(fd)
            obj.descriptor = None
            REAL_CLOSE(replacement)
        self.reject(lambda: self.enter(self.borrow(view)))

    def test_policy_and_sandbox_drift(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        for field, value in (('step', 'deepcheck'), ('process_limit', 17),
                ('workspace_root', self.root)):
            old = getattr(self.policy, field)
            try:
                object.__setattr__(self.policy, field, value)
                self.reject(lambda: self.enter(self.borrow(view)))
            finally:
                object.__setattr__(self.policy, field, old)
        for field in ('helper', 'manifest'):
            old = getattr(self.sandbox, field)
            try:
                setattr(self.sandbox, field, old + '-other')
                self.reject(lambda: self.enter(self.borrow(view)))
            finally:
                setattr(self.sandbox, field, old)

    def test_static_recheck_source_replace_and_workspace_install(self):
        self.write_image(image((1, 3)))
        self.reject(self.prepare)
        self.write_image(image())
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        with self.binary.open('r+b') as stream:
            stream.seek(64)
            stream.write(struct.pack('<I', 2))
        self.reject(lambda: self.enter(self.borrow(view)))
        self.write_image(image())
        fresh = self.prepare()
        fresh_view = self.bind(self.attach(fresh))
        self.binary.rename(self.binary.with_name('original-helper'))
        self.write_image(image())
        self.reject(lambda: self.enter(self.borrow(fresh_view)))
        self.assertEqual(fresh._owner_state, 'active')
        # Real locator mapped into the policy RW root must be refused.
        package = self.session.workspace_root / 'installed-icode'
        native = package / 'native'
        native.mkdir(parents=True)
        module = package / 'native_helper.py'
        module.write_text('# writable source fixture\n')
        binary, manifest = native / 'icode-landlock', native / 'icode-landlock.sha256'
        binary.write_bytes(image())
        binary.chmod(0o700)
        manifest.write_text(hashlib.sha256(image()).hexdigest() + '\n')
        sandbox = LandlockSandbox(str(binary), manifest=str(manifest))
        with patch.object(locator, '__file__', str(module)):
            self.reject(lambda: subject.prepare_linux_step(sandbox,
                policy=self.policy, workspace_session=self.session))

    def test_pending_binding_bad_attempt_and_boolean_validator(self):
        scope = self.prepare()
        view = self.attach(scope)
        self.reject(lambda: self.enter(self.borrow(view)))
        for attempt in ('', ' ', True, None, 'bad\nvalue'):
            self.reject(lambda: view._bind_attempt(attempt, validate_attempt=lambda _: None))
        self.reject(lambda: view._bind_attempt('software-attempt', validate_attempt=lambda _: True))
        self.bind(view)
        self.reject(lambda: view._bind_attempt('software-attempt', validate_attempt=lambda _: None))
        self.reject(lambda: self.enter(self.borrow(view, attempt='other-attempt')))

    def test_validator_rechecks_each_borrow(self):
        scope = self.prepare()
        view = self.attach(scope)
        calls, active = [], True
        def validator(attempt):
            calls.append(attempt)
            if not active:
                raise RuntimeError('private CP model')
        view._bind_attempt('software-attempt', validate_attempt=validator)
        with self.borrow(view):
            pass
        active = False
        self.reject(lambda: self.enter(self.borrow(view)))
        self.assertEqual(calls, ['software-attempt'] * 3)

    def test_reentry_concurrent_and_close_active_borrow(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        outcomes = []
        def competing():
            try:
                with self.borrow(view):
                    outcomes.append('entered')
            except subject.LinuxPreparedStepError:
                outcomes.append('rejected')
        with self.borrow(view):
            self.reject(lambda: self.enter(self.borrow(view)))
            self.reject(scope.close)
            self.reject(view.finish)
            thread = threading.Thread(target=competing)
            thread.start()
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(outcomes, ['rejected'])
        with self.borrow(view):
            pass

    def test_pending_bound_spent_faulted(self):
        for bound in (False, True):
            scope = self.prepare()
            view = self.attach(scope)
            if bound:
                self.bind(view)
            view.finish()
            view.finish()
            self.assertEqual(scope._consume_state, 'spent')
            self.reject(lambda: self.enter(self.borrow(view)))
            self.reject(lambda: self.attach(scope))
            self.assertEqual(scope._owner_state, 'active')
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        with self.borrow(view):
            view._mark_faulted()
        self.assertFalse(scope._inflight)
        view.finish()
        self.assertEqual(scope._consume_state, 'faulted')
        self.reject(lambda: self.enter(self.borrow(view)))
        self.reject(lambda: self.attach(scope))
        scope.close()
        self.assertEqual(scope._owner_state, 'closed')

    def test_copy_pickle_handbuilt_cannot_inject_owner(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        for value in (scope, view):
            for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                self.reject(lambda: operation(value))
        self.reject(lambda: subject._LinuxStepAttachment())
        with patch.object(subject, 'open_linux_helper_object', side_effect=OSError('private')):
            self.reject(lambda: subject.LinuxPreparedStep(self.sandbox,
                policy=self.policy, workspace_session=self.session))

    def test_prepare_postfactory_failure_once_cleanup_and_signals(self):
        for body in (OSError('private'), KeyboardInterrupt('first'), SystemExit(7)):
            captured = []
            original = subject.open_linux_helper_object
            def opening(*args):
                owner = original(*args)
                captured.append(owner)
                return owner
            with patch.object(subject, 'open_linux_helper_object', side_effect=opening), \
                    patch.object(subject, 'validate_static_linux_helper', side_effect=body):
                if isinstance(body, Exception):
                    self.reject(self.prepare)
                else:
                    with self.assertRaises(type(body)) as caught:
                        self.prepare()
                    self.assertIs(caught.exception, body)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]._state, 'closed')
            self.session.lease._validate_active()

    def test_prepare_body_cleanup_combination(self):
        for body in (OSError('body'), KeyboardInterrupt('first'), SystemExit(3)):
            for cleanup in (OSError('cleanup'), KeyboardInterrupt('later'), SystemExit(8)):
                original, held, closed = subject.open_linux_helper_object, [], []
                def opening(*args):
                    owner = original(*args)
                    held.append(owner.fileno())
                    return owner
                def closing(fd):
                    closed.append(fd)
                    REAL_CLOSE(fd)
                    if fd in held:
                        raise cleanup
                with patch.object(subject, 'open_linux_helper_object', side_effect=opening), \
                        patch.object(subject, 'validate_static_linux_helper', side_effect=body), \
                        patch.object(subject.os, 'close', side_effect=closing):
                    with self.assertRaises(BaseException) as caught:
                        self.prepare()
                self.assertEqual(closed.count(held[0]), 1)
                expected = body if not isinstance(body, Exception) else cleanup
                if isinstance(expected, Exception):
                    self.assertIsInstance(caught.exception, subject.LinuxPreparedStepError)
                else:
                    self.assertIs(caught.exception, expected)

    def test_close_unknown_never_retry_body_cleanup_priority(self):
        for body in (None, RuntimeError('body'), KeyboardInterrupt('first'), SystemExit(5)):
            scope = self.prepare()
            fd, closed = scope._owner.fileno(), []
            def closing(actual):
                REAL_CLOSE(actual)
                if actual == fd:
                    closed.append(actual)
                    raise OSError('unknown close')
            with patch.object(subject.os, 'close', side_effect=closing):
                with self.assertRaises(BaseException) as caught:
                    with scope:
                        if body is not None:
                            raise body
                self.assertEqual(scope._owner_state, 'unknown')
                self.reject(scope.close)
            self.assertEqual(closed, [fd])
            if body is not None and not isinstance(body, Exception):
                self.assertIs(caught.exception, body)
            else:
                self.assertIsInstance(caught.exception, subject.LinuxPreparedStepError)

    def test_borrow_body_signal_releases_not_close(self):
        for body in (RuntimeError('body'), KeyboardInterrupt('first'), SystemExit(5)):
            scope = self.prepare()
            view = self.bind(self.attach(scope))
            with self.assertRaises(type(body)) as caught:
                with self.borrow(view):
                    raise body
            self.assertIs(caught.exception, body)
            self.assertFalse(scope._inflight)
            self.assertEqual(scope._owner_state, 'active')
            with self.borrow(view):
                pass

    def test_checks_faults_fixed_and_signals_original(self):
        for target in ('validate_static_linux_helper', 'observe_linux_helper_source'):
            for error in (OSError('private'), KeyboardInterrupt('first'), SystemExit(9)):
                scope = self.prepare()
                view = self.bind(self.attach(scope))
                with patch.object(subject, target, side_effect=error):
                    if isinstance(error, Exception):
                        self.reject(lambda: self.enter(self.borrow(view)))
                    else:
                        with self.assertRaises(type(error)) as caught:
                            with self.borrow(view):
                                self.fail('entered')
                        self.assertIs(caught.exception, error)
                self.assertFalse(scope._inflight)
                self.assertEqual(scope._owner_state, 'active')

    def test_source_cleanup_unknown_sticky_no_retry_helper_still_owned(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        helper_fd, workspace_fd = scope._owner.fileno(), self.session.workspace_fd
        closed = []
        def closing(fd):
            REAL_CLOSE(fd)
            closed.append(fd)
            if len(closed) == 1:
                raise OSError('source cleanup unknown')
        with patch.object(subject.os, 'close', side_effect=closing):
            self.reject(lambda: self.enter(self.borrow(view)))
        self.assertGreater(len(closed), 1)
        self.assertEqual(len(closed), len(set(closed)))
        self.assertNotIn(helper_fd, closed)
        self.assertNotIn(workspace_fd, closed)
        self.assertEqual(scope._consume_state, 'faulted')
        self.assertEqual(scope._owner_state, 'active')
        self.assertFalse(scope._inflight)
        with patch.object(subject, 'observe_linux_helper_source') as observe:
            self.reject(lambda: self.enter(self.borrow(view)))
            observe.assert_not_called()
        view.finish()
        self.assertEqual(scope._consume_state, 'faulted')
        scope.close()
        self.assertEqual(scope._owner_state, 'closed')
        self.session.lease._validate_active()

if __name__ == '__main__':
    unittest.main()
