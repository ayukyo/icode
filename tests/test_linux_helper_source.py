"""Source observations on real owners; fixtures are not installed-package proof."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from tests._support import temp_workspace
from tests.test_linux_static_helper import image
import icode.native_helper as locator
import icode.linux_helper_object as factory
import icode.linux_helper_source as subject
from icode.isolation import LandlockSandbox
from icode.sandbox_policy import SandboxPolicy, NetworkMode

REAL = {name: getattr(os, name, None) for name in ('open', 'close', 'fstat', 'stat', 'lstat', 'pread')}

def policy(root):
    return SandboxPolicy(1, 'run-source', 'ticket-source', 'code', root,
        (root,), (root,), (), (), NetworkMode.DENY, (), 16, 30, 4096, ())

@unittest.skipUnless(sys.platform.startswith('linux') and REAL['pread'], 'Linux source fixture; no installed credit')
class SourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = temp_workspace()
        self.root = self.directory.__enter__()
        self.addCleanup(self.directory.__exit__, None, None, None)
        self.prefix = self.root / 'user-pipx' / 'venvs' / 'icode-agent'
        self.package = self.prefix / 'lib' / 'python3.11' / 'site-packages' / 'icode'
        self.native = self.package / 'native'
        self.native.mkdir(parents=True)
        self.module = self.package / 'native_helper.py'
        self.module.write_text('# source fixture\n')
        self.binary = self.native / 'icode-landlock'
        self.manifest = self.native / 'icode-landlock.sha256'
        self.binary.write_bytes(image())
        self.binary.chmod(0o700)
        self.digest = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.manifest.write_text(self.digest + '\n', encoding='ascii')
        self.workspace = self.root / 'project'
        self.workspace.mkdir()
        self.policy = policy(self.workspace)
        self.sandbox = LandlockSandbox(str(self.binary), manifest=str(self.manifest))
        for target, name, value in ((locator, '__file__', str(self.module)),
                (sys, 'prefix', str(self.prefix)), (sys, 'base_prefix', '/usr')):
            mock = patch.object(target, name, value)
            mock.start()
            self.addCleanup(mock.stop)
        machine = patch.object(factory.platform, 'machine', return_value='x86_64')
        machine.start()
        self.addCleanup(machine.stop)
        self.owner = factory.open_linux_helper_object(self.binary, self.manifest)
        self.addCleanup(self.owner.close)
        self.fd = self.owner.fileno()

    def observe(self):
        return subject.observe_linux_helper_source(self.sandbox, policy=self.policy, owner=self.owner)

    def reject(self):
        with self.assertRaises(factory.LinuxHelperObjectError) as caught:
            self.observe()
        self.assertEqual(str(caught.exception), 'Linux helper object is unavailable')
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(self.owner.fileno(), self.fd)

    def test_runtime_resolutions_are_strict_in_source_observation(self):
        original = Path.resolve
        observed = []
        tracked = {Path.home(), Path(sys.prefix), Path(sys.base_prefix)}
        def resolving(path, *args, **kwargs):
            if path in tracked:
                observed.append((path, kwargs.get('strict')))
            return original(path, *args, **kwargs)
        with patch.object(Path, 'resolve', new=resolving):
            self.assertIsNotNone(self.observe())
        self.assertTrue(observed)
        self.assertEqual({path for path, _ in observed}, tracked)
        self.assertTrue(all(strict is True for _, strict in observed), observed)

    def test_default_checked_policy_keeps_zero_keyword_runtime_callback(self):
        roots = (self.prefix, Path('/usr'))
        with patch.object(self.sandbox, '_runtime_read_roots', side_effect=lambda: roots) as callback:
            self.assertEqual(self.sandbox._checked_policy_workspace(self.policy), self.workspace)
        callback.assert_called_once_with()

    def test_default_runtime_keeps_prefix_only_validation_callback(self):
        roots = (self.prefix, Path('/usr'))
        with patch.object(self.sandbox, '_validated_runtime_roots', side_effect=lambda prefixes: roots) as callback:
            self.assertEqual(self.sandbox._runtime_read_roots(), roots)
        callback.assert_called_once_with((Path(sys.prefix), Path(sys.base_prefix)))

    def test_workspace_install_is_target_rejection(self):
        # Other premises valid: same real package, owner, source and runtime prefix.
        self.policy = policy(self.prefix)
        self.reject()

    def test_external_user_writable_prefix_and_public_ancestors_pass(self):
        os.lseek(self.fd, 7, os.SEEK_SET)
        opened, closed = [], []
        def opening(path, flags, **kw):
            result = REAL['open'](path, flags, **kw)
            opened.append((path, flags, result))
            return result
        def closing(fd):
            closed.append(fd)
            return REAL['close'](fd)
        with patch.object(subject.os, 'open', side_effect=opening), patch.object(subject.os, 'close', side_effect=closing):
            result = self.observe()
        self.assertEqual(result.helper_path, self.binary)
        self.assertEqual(result.helper_snapshot[:2], (REAL['fstat'](self.fd).st_dev, REAL['fstat'](self.fd).st_ino))
        self.assertEqual(result.manifest_digest, self.digest)
        self.assertEqual(closed, [entry[2] for entry in reversed(opened)])
        self.assertNotIn(self.fd, closed)
        self.assertFalse(any(path == self.binary or path == self.binary.name for path, _, _ in opened))
        self.assertEqual(os.lseek(self.fd, 0, os.SEEK_CUR), 7)
        self.assertEqual(self.owner.fileno(), self.fd)

    def test_native_root_and_native_child_write_reject(self):
        child = self.native / 'project'
        child.mkdir()
        for workspace in (self.native, child):
            with self.subTest(workspace=workspace):
                self.policy = policy(workspace)
                self.reject()

    def test_alias_real_target_and_exact_package_match(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.native, target_is_directory=True)
        self.sandbox = LandlockSandbox(str(alias / self.binary.name), manifest=str(alias / self.manifest.name))
        self.assertEqual(self.observe().helper_path, self.binary)
        self.policy = policy(self.prefix)
        self.reject()
        self.policy = policy(self.workspace)
        other = self.root / 'other'
        other.mkdir()
        replacement = other / self.binary.name
        replacement.write_bytes(image())
        self.sandbox = LandlockSandbox(str(replacement), manifest=str(self.manifest))
        self.reject()

    def test_helper_unlink_replace_and_wrong_held_identity(self):
        old = self.binary.with_name('old-helper')
        self.binary.rename(old)
        self.reject()
        self.binary.write_bytes(image())
        self.binary.chmod(0o700)
        self.reject()
        self.assertEqual(self.owner.fileno(), self.fd)

    def test_ancestor_replacement_and_canonical_native_symlink_reject(self):
        actual_stat = REAL['stat']
        injected = False
        old = self.native.with_name('old-native')
        def changed(path, *args, **kw):
            nonlocal injected
            result = actual_stat(path, *args, **kw)
            if path == self.binary.name and kw.get('dir_fd') is not None and not injected:
                injected = True
                self.native.rename(old)
                self.native.mkdir()
                # Complete decoy keeps later path/manifest premises valid;
                # rejection must distinguish the original held directory.
                self.binary.write_bytes(image())
                self.binary.chmod(0o700)
                self.manifest.write_text(self.digest + '\n', encoding='ascii')
            return result
        with patch.object(subject.os, 'stat', side_effect=changed):
            self.reject()
        self.assertTrue(injected)
        self.binary.unlink()
        self.manifest.unlink()
        self.native.rmdir()
        self.native.symlink_to(old, target_is_directory=True)
        self.reject()

    def test_manifest_is_new_bound_observation_not_factory_identity(self):
        old = self.manifest.with_name('old-manifest')
        self.manifest.rename(old)
        self.manifest.write_text(self.digest + '\n')
        self.assertEqual(self.observe().manifest_digest, self.digest)
        for contents in ('0' * 64 + '\n', self.digest + '\nextra', self.digest.upper() + '\n'):
            with self.subTest(contents=contents[:1]):
                self.manifest.write_text(contents)
                self.reject()
        self.manifest.unlink()
        self.manifest.symlink_to(old)
        self.reject()

    def test_alias_drift_after_first_resolution_rejects(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.native, target_is_directory=True)
        other = self.root / 'decoy'
        other.mkdir()
        (other / self.binary.name).write_bytes(image())
        (other / self.manifest.name).write_text(self.digest + '\n')
        self.sandbox = LandlockSandbox(str(alias / self.binary.name), manifest=str(alias / self.manifest.name))
        original = REAL['pread']
        def changed(fd, length, offset):
            result = original(fd, length, offset)
            alias.unlink()
            alias.symlink_to(other, target_is_directory=True)
            return result
        with patch.object(subject.os, 'pread', side_effect=changed):
            self.reject()

    def test_finite_budgets_and_runtime_mapping(self):
        with patch.object(subject, '_PATH_BYTES', 1):
            self.reject()
        with patch.object(subject, '_DIRECTORY_LIMIT', 1):
            self.reject()
        with patch.object(sys, 'prefix', '/usr'):
            self.reject()

    def test_every_actual_os_position_fault_and_once_cleanup(self):
        # Discover calls on real successful fixture; then recreate for each target.
        counts = dict.fromkeys(REAL, 0)
        def counted(name):
            def call(*args, **kw):
                counts[name] += 1
                return REAL[name](*args, **kw)
            return call
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in REAL:
                stack.enter_context(patch.object(subject.os, name, side_effect=counted(name)))
            self.observe()
        for name, total in counts.items():
            for position in range(1, total + 1):
                for error_type in (OSError, KeyboardInterrupt, SystemExit):
                    with self.subTest(name=name, position=position, error_type=error_type):
                        error = error_type('private detail')
                        calls = 0
                        opened, closed = [], []
                        def opening(*args, **kw):
                            nonlocal calls
                            if name == 'open':
                                calls += 1
                                if calls == position:
                                    raise error
                            fd = REAL['open'](*args, **kw)
                            opened.append(fd)
                            return fd
                        def closing(fd):
                            nonlocal calls
                            closed.append(fd)
                            # Fault after actual close: unknown must not be retried.
                            REAL['close'](fd)
                            if name == 'close':
                                calls += 1
                                if calls == position:
                                    raise error
                        def target(*args, **kw):
                            nonlocal calls
                            calls += 1
                            if calls == position:
                                raise error
                            return REAL[name](*args, **kw)
                        with ExitStack() as stack:
                            stack.enter_context(patch.object(subject.os, 'open', side_effect=opening))
                            stack.enter_context(patch.object(subject.os, 'close', side_effect=closing))
                            if name not in ('open', 'close'):
                                stack.enter_context(patch.object(subject.os, name, side_effect=target))
                            with self.assertRaises(BaseException) as caught:
                                self.observe()
                        self.assertGreaterEqual(calls, position)
                        if error_type is OSError:
                            self.assertIsInstance(caught.exception, factory.LinuxHelperObjectError)
                        else:
                            self.assertIs(caught.exception, error)
                        self.assertEqual(closed, list(reversed(opened)))
                        self.assertNotIn(self.fd, closed)
                        self.assertEqual(self.owner.fileno(), self.fd)

    def test_first_signal_survives_later_cleanup_signal(self):
        first, following = KeyboardInterrupt('first'), SystemExit('later')
        opened, closed = [], []
        def opening(*args, **kw):
            fd = REAL['open'](*args, **kw)
            opened.append(fd)
            return fd
        def closing(fd):
            closed.append(fd)
            REAL['close'](fd)
            raise following
        with patch.object(subject.os, 'open', side_effect=opening), patch.object(subject.os, 'pread', side_effect=first), patch.object(subject.os, 'close', side_effect=closing):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.observe()
        self.assertIs(caught.exception, first)
        self.assertEqual(closed, list(reversed(opened)))
        self.assertEqual(self.owner.fileno(), self.fd)
