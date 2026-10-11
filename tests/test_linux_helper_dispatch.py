from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
import socket
import sys
import unittest
from unittest import mock

from tests._support import temp_workspace
from icode.isolation import LandlockSandbox, PreparedCommand
from icode.linux_helper_object import open_linux_helper_object
from icode.linux_task_scope import LinuxTaskScope
from icode.sandbox_policy import NetworkMode, SandboxPolicy

REAL_CLOSE = os.close


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
