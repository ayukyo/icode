"""Real socket ownership boundaries; Linux software only, no native/CP credit."""
from __future__ import annotations

import os
import socket
import stat
import sys
import types
import unittest
from unittest.mock import patch

REAL_SOCKET = socket.socket
REAL_PAIR = socket.socketpair
REAL_DETACH = REAL_SOCKET.detach
if sys.platform.startswith('linux'):
    from icode import linux_seccomp_notify as seccomp
    from icode import linux_task_resource as resource
    FACTORIES = ((resource, resource.create_task_resource_channel,
                  resource.LinuxTaskResourceError, 'Linux task resource channel is invalid'),
                 (seccomp, seccomp.create_seccomp_listener_handoff_channel,
                  seccomp.LinuxSeccompNotificationError, 'Linux seccomp notifications unavailable'))
else:
    FACTORIES = ()


@unittest.skipUnless(sys.platform.startswith('linux'),
    'Linux real-socket fixture; skip is not acceptance')
class ChannelFactoryCleanupTests(unittest.TestCase):
    def exercise(self, module, factory, body, failures, *, detach_error=None):
        held, descriptors, attempts, replacements = [], [], [], []
        test = self

        class Endpoint(REAL_SOCKET):
            def setsockopt(self, *args):
                if self is held[0]:
                    raise body
                return super().setsockopt(*args)

            def detach(self):
                raise AssertionError('factory used overridable detach')

            def close(self):
                index = held.index(self)
                attempts.append(index)
                failure = failures.get(index)
                if failure is None:
                    return REAL_SOCKET.close(self)
                mode, error = failure
                if mode == 'after':
                    descriptor = self.fileno()
                    REAL_SOCKET.close(self)
                    replacement = os.open('/dev/null', os.O_RDONLY)
                    if replacement != descriptor:
                        os.dup2(replacement, descriptor)
                        os.close(replacement)
                    replacements.append(descriptor)
                raise error

        def pair(*args, **kwargs):
            test.assertEqual(args, (socket.AF_UNIX, socket.SOCK_SEQPACKET))
            test.assertEqual(kwargs, {})
            for endpoint in REAL_PAIR(*args, **kwargs):
                wrapped = Endpoint(fileno=REAL_DETACH(endpoint))
                held.append(wrapped)
                descriptors.append(wrapped.fileno())
            return tuple(held)

        def inheritable(descriptor, value):
            test.assertEqual(value, False)
            raise body

        class DetachBoundary:
            @staticmethod
            def detach(endpoint):
                if endpoint is held[1] and detach_error is not None:
                    raise detach_error
                return REAL_DETACH(endpoint)

        boundary = types.SimpleNamespace(socketpair=pair,
            socket=REAL_SOCKET if detach_error is None else DetachBoundary,
            AF_UNIX=socket.AF_UNIX, SOCK_SEQPACKET=socket.SOCK_SEQPACKET,
            SOL_SOCKET=socket.SOL_SOCKET, SO_PASSCRED=socket.SO_PASSCRED)
        captured = None
        try:
            with patch.object(module, 'socket', boundary), \
                    patch.object(module.os, 'set_inheritable', side_effect=inheritable):
                try:
                    factory()
                except BaseException as error:
                    captured = error
            return captured, held, descriptors, attempts, replacements
        except BaseException:
            self.hygiene(held, descriptors, failures, replacements)
            raise

    def hygiene(self, held, descriptors, failures, replacements):
        # Only the controlled before-close injection guarantees saved FD live.
        for index, endpoint in enumerate(held):
            descriptor = REAL_DETACH(endpoint)
            if descriptor >= 0:
                os.close(descriptor)
            elif failures.get(index, ('', None))[0] == 'before':
                os.close(descriptors[index])
        for descriptor in replacements:
            os.close(descriptor)

    def test_seccomp_original_signal_and_independent_host_close(self):
        for signal in (KeyboardInterrupt('body'), SystemExit(29)):
            with self.subTest(signal=type(signal).__name__):
                failures = {1: ('before', RuntimeError('sender close'))}
                answer = self.exercise(seccomp,
                    seccomp.create_seccomp_listener_handoff_channel, signal, failures)
                error, held, fds, attempts, replacements = answer
                try:
                    self.assertTrue(stat.S_ISSOCK(os.fstat(fds[1]).st_mode))
                    self.assertIs(error, signal)
                    self.assertEqual(attempts, [1, 0])
                    self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                finally:
                    self.hygiene(held, fds, failures, replacements)

    def test_both_factories_disarm_before_close_without_release_credit(self):
        for module, factory, kind, message in FACTORIES:
            with self.subTest(factory=factory.__name__):
                failures = {0: ('before', OSError('host close')),
                            1: ('before', RuntimeError('sender close'))}
                answer = self.exercise(module, factory, OSError('init'), failures)
                error, held, fds, attempts, replacements = answer
                try:
                    self.assertTrue(all(stat.S_ISSOCK(os.fstat(fd).st_mode) for fd in fds))
                    self.assertIs(type(error), kind)
                    self.assertEqual(str(error), message)
                    self.assertEqual(attempts, [1, 0])
                    self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                finally:
                    self.hygiene(held, fds, failures, replacements)

    def test_cleanup_signal_selected_and_original_signal_retained(self):
        for module, factory, _kind, _message in FACTORIES:
            for received in (RuntimeError('body'), KeyboardInterrupt('body'), SystemExit(31)):
                for cleanup in (KeyboardInterrupt('close'), SystemExit(32)):
                    with self.subTest(factory=factory.__name__, body=type(received).__name__,
                                      cleanup=type(cleanup).__name__):
                        failures = {1: ('before', cleanup), 0: ('before', SystemExit(33))}
                        answer = self.exercise(module, factory, received, failures)
                        error, held, fds, attempts, replacements = answer
                        try:
                            self.assertIs(error, cleanup if isinstance(received, Exception) else received)
                            self.assertEqual(attempts, [1, 0])
                            self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                        finally:
                            self.hygiene(held, fds, failures, replacements)

    def test_after_close_reused_integer_is_not_retried(self):
        for module, factory, _kind, _message in FACTORIES:
            with self.subTest(factory=factory.__name__):
                body = RuntimeError('body')
                failures = {1: ('after', OSError('close after release'))}
                answer = self.exercise(module, factory, body, failures)
                error, held, fds, attempts, replacements = answer
                try:
                    self.assertEqual(replacements, [fds[1]])
                    self.assertTrue(stat.S_ISCHR(os.fstat(fds[1]).st_mode))
                    self.assertIs(error, body)
                    self.assertEqual(attempts, [1, 0])
                    self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                finally:
                    self.hygiene(held, fds, failures, replacements)

    def test_detach_failure_still_attempts_host_and_keeps_first_signal(self):
        for module, factory, _kind, _message in FACTORIES:
            for body in (RuntimeError('body'), KeyboardInterrupt('body'), SystemExit(34)):
                with self.subTest(factory=factory.__name__, body=type(body).__name__):
                    detached = KeyboardInterrupt('detach')
                    failures = {1: ('before', OSError('sender close'))}
                    answer = self.exercise(module, factory, body, failures, detach_error=detached)
                    error, held, fds, attempts, replacements = answer
                    try:
                        self.assertTrue(stat.S_ISSOCK(os.fstat(fds[1]).st_mode))
                        self.assertIs(error, detached if isinstance(body, Exception) else body)
                        self.assertEqual(attempts, [1, 0])
                        self.assertEqual(held[0].fileno(), -1)
                        self.assertEqual(held[1].fileno(), fds[1])
                    finally:
                        self.hygiene(held, fds, failures, replacements)

    def test_ordinary_initialization_contract(self):
        for module, factory, kind, message in FACTORIES:
            for body in (OSError('init'), RuntimeError('init')):
                with self.subTest(factory=factory.__name__, body=type(body).__name__):
                    answer = self.exercise(module, factory, body, {})
                    error, held, fds, attempts, replacements = answer
                    try:
                        if isinstance(body, OSError):
                            self.assertIs(type(error), kind)
                            self.assertEqual(str(error), message)
                        else:
                            self.assertIs(error, body)
                        self.assertEqual(attempts, [1, 0])
                        self.assertEqual([endpoint.fileno() for endpoint in held], [-1, -1])
                    finally:
                        self.hygiene(held, fds, {}, replacements)

    def test_success_tuple_flags_and_caller_ownership(self):
        for module, factory, _kind, _message in FACTORIES:
            with self.subTest(factory=factory.__name__):
                endpoints = factory()
                try:
                    self.assertIs(type(endpoints), tuple)
                    self.assertEqual(len(endpoints), 2)
                    for endpoint in endpoints:
                        self.assertIs(type(endpoint), REAL_SOCKET)
                        self.assertTrue(stat.S_ISSOCK(os.fstat(endpoint.fileno()).st_mode))
                        self.assertFalse(endpoint.get_inheritable())
                        self.assertEqual(endpoint.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE),
                                         socket.SOCK_SEQPACKET)
                    if module is resource:
                        self.assertEqual(endpoints[0].getsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED), 1)
                finally:
                    for endpoint in endpoints:
                        endpoint.close()

    def test_nonlinux_fixed_refusal_before_pair(self):
        for module, factory, kind, message in FACTORIES:
            with self.subTest(factory=factory.__name__):
                with patch.object(module.sys, 'platform', 'win32'), \
                        patch.object(module.socket, 'socketpair') as pair:
                    with self.assertRaises(kind) as raised:
                        factory()
                self.assertEqual(str(raised.exception), message)
                pair.assert_not_called()


if __name__ == '__main__':
    unittest.main()
