"""Real receiver cleanup facts; broker/process fixture gives no native/CP credit."""
from __future__ import annotations

import array
import errno
import os
import socket
import stat
import sys
import threading
import time
import unittest
from unittest.mock import patch

from tests import test_linux_prepared_broker as fixture
from tests import test_linux_helper_dispatch as dispatch
from icode import linux_prepared_step as prepared
from icode import linux_task_resource as resource

REAL_CLOSE = os.close


@unittest.skipUnless(sys.platform.startswith('linux') and callable(getattr(os, 'pread', None)),
    'Linux real-resource software fixture; skip is not acceptance')
class ResourceCleanupTests(unittest.TestCase):
    # Compose the fixture methods: inheriting its TestCase would rerun 26 tests.
    setUp = fixture.PreparedBrokerTests.setUp
    write_image = fixture.PreparedBrokerTests.write_image
    precheck_fixture = fixture.PreparedBrokerTests.precheck_fixture
    cleanup_scopes = fixture.PreparedBrokerTests.cleanup_scopes
    prepare = fixture.PreparedBrokerTests.prepare
    attach = fixture.PreparedBrokerTests.attach
    bind = fixture.PreparedBrokerTests.bind
    borrow = fixture.PreparedBrokerTests.borrow
    entry = fixture.PreparedBrokerTests.entry
    call = fixture.PreparedBrokerTests.call
    wrapper = fixture.PreparedBrokerTests.wrapper
    exercise = fixture.PreparedBrokerTests.exercise

    def receiver_pair(self):
        endpoints = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        endpoints[0].setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        receiver = resource.LinuxTaskResourceReceiver(endpoints[0],
            unit=dispatch.Scope.unit, limit=self.policy.process_limit)
        receiver.bind(expected_pid=os.getpid(), expected_uid=os.getuid(),
            expected_gid=os.getgid())
        self.addCleanup(endpoints[1].close)
        self.addCleanup(endpoints[0].close)
        self.addCleanup(receiver.close)
        return receiver, endpoints

    def worker(self, receiver, sender, descriptors=()):
        receiver.start(deadline_monotonic=time.monotonic() + 2)
        ancillary = ([(socket.SOL_SOCKET, socket.SCM_RIGHTS,
            array.array('i', descriptors))] if descriptors else [])
        self.assertEqual(sender.sendmsg([b'malformed'], ancillary), 9)
        self.assertTrue(receiver.wait(timeout_seconds=2))
        receiver._thread.join(timeout=2)
        self.assertIsNotNone(receiver._thread.ident)
        self.assertFalse(receiver._thread.is_alive())
        self.assertEqual(receiver.receipt()['channel_status'], 'incomplete')

    def broker_receiver(self, view, receiver, endpoints, descriptors=()):
        actual_pair = socket.socketpair
        actual_wait, actual_close = receiver.wait, receiver.close
        pairs = []
        def pair(*args, **kwargs):
            result = endpoints if not pairs else actual_pair(*args, **kwargs)
            pairs.append(result)
            return result
        def mutation(command):
            self.assertTrue(view._scope._inflight)
            self.worker(receiver, endpoints[1], descriptors)
        try:
            with patch.object(dispatch, 'Resource', return_value=receiver), \
                    patch.object(socket, 'socketpair', side_effect=pair):
                answer, error, events = self.exercise(True, view, mutation=mutation)
        finally:
            # exercise decorates methods to check active borrowing. Restore
            # them before testing repeated close after the borrow has returned.
            receiver.wait, receiver.close = actual_wait, actual_close
        self.assertIsNone(error)
        self.assertEqual(answer.resource_receipt['channel_status'], 'incomplete')
        self.assertIn('resource_close', events)
        self.assertEqual(len(pairs), 2)
        return answer

    def owned_facts(self, view):
        scope = view._scope
        self.assertFalse(scope._inflight)
        self.assertEqual(scope._owner_state, 'active')
        os.fstat(scope._owner.fileno())
        os.fstat(self.session.workspace_fd)
        self.session.lease._validate_active()

    def faulted(self, view):
        self.owned_facts(view)
        self.assertEqual(view._scope._consume_state, 'faulted')
        with self.assertRaises(prepared.LinuxPreparedStepError):
            with self.borrow(view):
                pass

    def rights_fault(self, receiver, attempts, retained, failure):
        def close(descriptor):
            if threading.current_thread() is receiver._thread:
                status = os.fstat(descriptor)
                self.assertTrue(stat.S_ISREG(status.st_mode))
                attempts.append(descriptor)
                if len(attempts) == 1:
                    retained.append(descriptor)
                    raise failure
            return REAL_CLOSE(descriptor)
        return close

    def assert_closed(self, descriptor):
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_rights_fault_continues_each_fd_once_and_close_stays_false(self):
        for failure in (OSError('private FD close'), KeyboardInterrupt(), SystemExit(17)):
            with self.subTest(kind=type(failure).__name__):
                receiver, endpoints = self.receiver_pair()
                attempts, retained = [], []
                with open(self.binary, 'rb') as first, open(self.manifest, 'rb') as second:
                    before = set()
                    for name in os.listdir('/proc/self/fd'):
                        descriptor = int(name)
                        try:
                            os.fstat(descriptor)
                        except OSError as error:
                            if error.errno == errno.EBADF:
                                continue
                            raise
                        before.add(descriptor)
                    identities = {(os.fstat(fd).st_dev, os.fstat(fd).st_ino)
                        for fd in (first.fileno(), second.fileno())}
                    try:
                        with patch.object(resource.os, 'close',
                                side_effect=self.rights_fault(receiver, attempts, retained, failure)):
                            self.worker(receiver, endpoints[1], (first.fileno(), second.fileno()))
                            self.assertEqual(len(attempts), 2)
                            self.assertEqual(len(set(attempts)), 2)
                            self.assertEqual(len(retained), 1)
                            self.assertTrue(stat.S_ISREG(os.fstat(retained[0]).st_mode))
                            self.assert_closed(attempts[1])
                            answers = (receiver.close(), receiver.close())
                            self.assertEqual(len(attempts), 2)
                            self.assertEqual(answers, (False, False))
                    finally:
                        # Saved real close is hygiene, never receiver cleanup credit.
                        # A baseline BaseException stops before unpacking the
                        # next delivered FD. Find only new FDs for these exact
                        # test-owned files, so even the RED has no fixture leak.
                        for name in os.listdir('/proc/self/fd'):
                            descriptor = int(name)
                            if descriptor in before:
                                continue
                            try:
                                status = os.fstat(descriptor)
                            except OSError as error:
                                if error.errno == errno.EBADF:
                                    continue
                                raise
                            if (status.st_dev, status.st_ino) in identities:
                                REAL_CLOSE(descriptor)

    def test_rights_unknown_faults_real_broker_attachment(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        receiver, endpoints = self.receiver_pair()
        attempts, retained = [], []
        with open(self.binary, 'rb') as source:
            try:
                with patch.object(resource.os, 'close', side_effect=self.rights_fault(
                        receiver, attempts, retained, OSError('private received close'))):
                    self.broker_receiver(view, receiver, endpoints, (source.fileno(),))
                self.assertEqual(attempts, retained)
                self.assertEqual(len(retained), 1)
                self.assertTrue(stat.S_ISREG(os.fstat(retained[0]).st_mode))
                self.owned_facts(view)
                self.faulted(view)
                self.assertIs(receiver.close(), False)
            finally:
                for descriptor in retained:
                    REAL_CLOSE(descriptor)

    def test_selector_close_unknown_retains_fd_and_faults_attachment(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        receiver, endpoints = self.receiver_pair()
        selector = resource.selectors.DefaultSelector()
        descriptor, actual_close = selector.fileno(), selector.close
        attempts = []
        def close():
            attempts.append(descriptor)
            raise OSError('private selector close')
        try:
            with patch.object(resource.selectors, 'DefaultSelector', return_value=selector), \
                    patch.object(selector, 'close', side_effect=close):
                self.broker_receiver(view, receiver, endpoints)
                self.assertEqual(attempts, [descriptor])
                os.fstat(descriptor)
                self.owned_facts(view)
                self.faulted(view)
                answers = (receiver.close(), receiver.close())
                self.assertEqual(attempts, [descriptor])
                self.assertEqual(answers, (False, False))
        finally:
            actual_close()  # Test-owned retained selector, no production credit.

    def test_unreturned_selector_is_conservatively_unknown(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        receiver, endpoints = self.receiver_pair()
        held = []
        actual_factory = resource.selectors.DefaultSelector
        def constructor():
            selector = actual_factory()
            held.append(selector)
            raise OSError('private unreturned selector')
        try:
            with patch.object(resource.selectors, 'DefaultSelector', side_effect=constructor):
                self.broker_receiver(view, receiver, endpoints)
            self.assertEqual(len(held), 1)
            os.fstat(held[0].fileno())
            self.owned_facts(view)
            self.faulted(view)
            self.assertIs(receiver.close(), False)
        finally:
            for selector in held:
                selector.close()  # Opaque-constructor debt remains unproved.

    def test_malformed_with_confirmed_cleanup_keeps_attachment_borrowable(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        receiver, endpoints = self.receiver_pair()
        answer = self.broker_receiver(view, receiver, endpoints)
        self.assertEqual(answer.error, 'resource_channel_failed')
        self.assertIs(receiver.close(), True)
        self.owned_facts(view)
        self.assertEqual(scope._consume_state, 'attached_bound')
        with self.borrow(view) as owner:
            self.assertIs(owner, scope._owner)

    def test_rights_confirmed_cleanup_closes_each_fd_once_and_keeps_borrowable(self):
        scope = self.prepare()
        view = self.bind(self.attach(scope))
        receiver, endpoints = self.receiver_pair()
        attempts = []
        def close(descriptor):
            if threading.current_thread() is receiver._thread:
                self.assertTrue(stat.S_ISREG(os.fstat(descriptor).st_mode))
                attempts.append(descriptor)
            return REAL_CLOSE(descriptor)
        with open(self.binary, 'rb') as first, open(self.manifest, 'rb') as second, \
                patch.object(resource.os, 'close', side_effect=close):
            self.broker_receiver(view, receiver, endpoints, (first.fileno(), second.fileno()))
            self.assertEqual(len(attempts), 2)
            self.assertEqual(len(set(attempts)), 2)
            for descriptor in attempts:
                self.assert_closed(descriptor)
            self.assertEqual((receiver.close(), receiver.close()), (True, True))
            self.assertEqual(len(attempts), 2)
        self.owned_facts(view)
        with self.borrow(view) as owner:
            self.assertIs(owner, scope._owner)

    def test_unstarted_close_is_true_and_preserves_caller_sockets(self):
        receiver, endpoints = self.receiver_pair()
        self.assertIsNone(receiver._thread)
        self.assertEqual((receiver.close(), receiver.close()), (True, True))
        for endpoint in endpoints:
            self.assertTrue(stat.S_ISSOCK(os.fstat(endpoint.fileno()).st_mode))
