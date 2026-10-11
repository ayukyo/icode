"""Portable real-owner tests; no Windows native execution claim."""
import importlib
import importlib.util
import inspect
import hashlib
import copy
import pickle
from dataclasses import replace
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tests.test_windows_startup_pin import FakeBackend
from tests.test_windows_startup_security import descriptor, acl, ace, sid
from icode import windows_startup_pin as pin


HOST = 'S-1-5-21-100-200-300-1001'
HOST_BYTES = sid(5, (21, 100, 200, 300, 1001))


class SourceBackend(FakeBackend):
    def __init__(self, label, calls, nodes=4):
        super().__init__(pin)
        self.label, self.global_calls, self.nodes = label, calls, nodes
        self.security = descriptor(dacl=acl((ace(mask=0x2, trustee=HOST_BYTES),)))
        self.security_queries = {}
        self.security_values = {}
        self.close_faults = {}

    def call(self, label):
        self.global_calls.append((self.label, label))
        super().call(label)

    def query(self, handle):
        self.queries[handle] = self.queries.get(handle, 0) + 1
        self.call(f'query:{handle}:{self.queries[handle]}')
        directory = handle < self.nodes
        meta = pin.StartupFileMetadata(7, handle.to_bytes(16, 'little'), directory,
                                      False, False, 'disk', 1,
                                      0 if directory else len(self.data), 100)
        return replace(meta, **self.mutations.get((handle, self.queries[handle]), {}))

    def read(self, handle, offset, count):
        assert handle == self.nodes and handle in self.live
        self.call(f'read:{offset}')
        return self.data[offset:offset + count]

    def query_security(self, handle):
        assert handle in self.live
        count = self.security_queries.get(handle, 0) + 1
        self.security_queries[handle] = count
        self.call(f'security:{handle}:{count}')
        return self.security_values.get((handle, count), self.security)

    def close(self, handle):
        self.global_calls.append((self.label, f'close:{handle}'))
        self.closed.append(handle)
        if handle in self.close_faults:
            raise self.close_faults[handle]
        self.live.remove(handle)


class SourceOwnerTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('icode.windows_startup_source')
        self.calls = []
        self.backends = [SourceBackend(label, self.calls) for label in ('helper', 'verifier')]
        self.identity = SimpleNamespace(cleanup_unconfirmed=False, capture=lambda: HOST)

    def installed(self, nodes=4):
        parts = ['p'] * (nodes - 2) + ['image.exe']
        path = 'C:\\' + '\\'.join(parts)
        for backend in self.backends:
            backend.nodes = nodes
        return (('helper', path), ('verifier', path))

    def entry(self, nodes=4):
        with ExitStack() as stack:
            stack.enter_context(patch.object(self.m.os, 'name', 'nt'))
            stack.enter_context(patch.object(self.m, '_installed_resources', return_value=self.installed(nodes)))
            stack.enter_context(patch.object(self.m, 'WindowsStartupHostIdentity', return_value=self.identity))
            stack.enter_context(patch.object(self.m, 'WindowsStartupPinBackend', side_effect=self.backends))
            return self.m.pin_installed_startup_sources()

    def test_live_original_bytes_digest_order_and_revalidation(self):
        cls = getattr(self.m, 'PinnedStartupSources', None)
        self.assertTrue(callable(cls), 'composite owner missing')
        with self.entry() as owner:
            for resource in ('helper', 'verifier'):
                self.assertEqual(owner.content(resource), b'original bytes')
                self.assertEqual(owner.sha256(resource), hashlib.sha256(b'original bytes').hexdigest())
            self.assertIsNone(owner.revalidate())
            self.assertFalse(owner.closed)
        self.assertTrue(owner.close_confirmed)
        self.assertEqual(self.calls[-8:], [(r, f'close:{h}') for r in ('verifier', 'helper') for h in (4, 3, 2, 1)])
        for backend in self.backends:
            for handle in range(1, 5):
                self.assertEqual(backend.security_queries[handle], 4)

    def test_exact_resources_copy_pickle_and_unready_are_rejected(self):
        class Text(str):
            pass
        with self.entry() as owner:
            for resource in (Text('helper'), None, [], b'helper', 1, 'Helper', 'unknown'):
                for method in (owner.content, owner.sha256):
                    with self.subTest(resource=resource, method=method.__name__):
                        with self.assertRaises(pin.StartupPinError):
                            method(resource)
            for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                with self.assertRaises(pin.StartupPinError):
                    operation(owner)
            self.assertFalse(owner.closed)
        unready = self.m.PinnedStartupSources(HOST)
        for instance in (owner, unready):
            for operation in (lambda: instance.content('helper'), lambda: instance.sha256('verifier'),
                              instance.revalidate, instance.__enter__):
                with self.assertRaises(pin.StartupPinError):
                    operation()

    def test_identity_validation_before_any_open(self):
        for host, cleanup in (('S-1-05-18', False), (HOST, True), (HOST, None), (HOST, 0)):
            with self.subTest(host=host, cleanup=cleanup):
                self.setUp()
                self.identity.capture = lambda: host
                self.identity.cleanup_unconfirmed = cleanup
                with self.assertRaises(pin.StartupPinError):
                    self.entry()
                self.assertEqual(self.calls, [])

    def test_ace_budget_and_chain_limit(self):
        for extra in (False, True):
            with self.subTest(extra=extra):
                self.setUp()
                for backend in self.backends:
                    backend.security = descriptor(dacl=acl((ace(),) * 4))
                if extra:
                    data = descriptor(dacl=acl((ace(),) * 5))
                    self.backends[1].security_values.update({(32, 1): data, (32, 2): data})
                    with self.assertRaises(self.m.StartupSecurityError):
                        self.entry(32)
                    self.assertEqual([b.closed for b in self.backends], [list(range(32, 0, -1))] * 2)
                else:
                    with self.entry(32) as owner:
                        owner.revalidate()
                        owner.revalidate()

    def test_allowed_security_change_across_revalidation_rejected(self):
        owner = self.entry()
        self.backends[0].security = descriptor(owner=HOST_BYTES, dacl=acl((ace(trustee=HOST_BYTES),)))
        with self.assertRaises(self.m.StartupSecurityError):
            owner.revalidate()
        self.assertTrue(owner.close_confirmed)

    def test_global_metadata_chain_shape_not_truncated(self):
        owner = self.entry()
        owner._owners[0][1]._baseline.pop()
        with self.assertRaises(pin.StartupPinError):
            owner.revalidate()
        self.assertTrue(owner.close_confirmed)

    def test_close_all_interrupt_priority_and_unknown_never_retry(self):
        for exception_type in (RuntimeError, KeyboardInterrupt, SystemExit):
            with self.subTest(exception_type=exception_type):
                self.setUp()
                owner = self.entry()
                error = exception_type('private close value')
                self.backends[1].close_faults[4] = error
                self.backends[0].close_faults[2] = RuntimeError('another close')
                with self.assertRaises(BaseException) as caught:
                    owner.close()
                if exception_type is not RuntimeError:
                    self.assertIs(caught.exception, error)
                self.assertTrue(owner.closed)
                self.assertFalse(owner.close_confirmed)
                self.assertEqual(len(owner.close_errors), 2)
                self.assertEqual(self.calls[-8:], [(r, f'close:{h}') for r in ('verifier', 'helper') for h in (4, 3, 2, 1)])
                before = list(self.calls)
                owner.close()
                self.assertEqual(self.calls, before)

    def test_each_normal_close_fault_position(self):
        for index in (0, 1):
            for handle in range(1, 5):
                for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
                    with self.subTest(index=index, handle=handle, kind=kind):
                        self.setUp()
                        owner = self.entry()
                        error = kind('close unknown')
                        self.backends[index].close_faults[handle] = error
                        with self.assertRaises(BaseException) as caught:
                            owner.close()
                        if kind is RuntimeError:
                            self.assertIsInstance(caught.exception, pin.StartupPinCloseError)
                        else:
                            self.assertIs(caught.exception, error)
                        self.assertEqual([b.closed for b in self.backends], [[4, 3, 2, 1]] * 2)
                        self.assertFalse(owner.close_confirmed)
                        before = list(self.calls)
                        owner.close()
                        self.assertEqual(self.calls, before)

    def test_registration_unknown_close_not_retried_and_hostile_notes(self):
        original_class = self.m.PinnedStartupSources
        error = RuntimeError('registration body')
        error.__notes__ = 42
        class FaultList(list):
            def append(inner, item):
                super(FaultList, inner).append(item)
                raise error
        def factory(host):
            result = original_class(host)
            result._owners = FaultList()
            return result
        self.backends[0].close_faults[4] = KeyboardInterrupt('unknown')
        with patch.object(self.m, 'PinnedStartupSources', side_effect=factory):
            with self.assertRaises(BaseException) as caught:
                self.entry()
        self.assertIs(caught.exception, error)
        self.assertEqual(self.backends[0].closed, [4, 3, 2, 1])
        self.assertEqual(self.backends[1].closed, [])

    def test_entry_and_revalidation_faults_preserve_identity_and_global_cleanup(self):
        for resource_index in (0, 1):
            labels = [f'security:{h}:{n}' for h in range(1, 5) for n in (1, 2)]
            labels += [f'query:{h}:{n}' for h in range(1, 5) for n in (3, 4, 5, 6)]
            if resource_index == 1:
                labels += [f'open:{h}' for h in range(1, 5)]
                labels += [f'query:{h}:{n}' for h in range(1, 5) for n in (1, 2)] + ['read:0']
            for label in labels:
                for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
                    with self.subTest(resource=resource_index, label=label, kind=kind):
                        self.setUp()
                        error = kind('original secret')
                        backend = self.backends[resource_index]
                        backend.fail, backend.exception = label, error
                        with self.assertRaises(BaseException) as caught:
                            self.entry()
                        self.assertIs(caught.exception, error)
                        self.assertTrue(all(not b.live for b in self.backends))
                        closed_resources = [r for r, c in self.calls if c.startswith('close:')]
                        self.assertEqual(closed_resources, sorted(closed_resources, reverse=True))

    def test_metadata_before_security_must_fail_before_sd_query(self):
        self.backends[0].mutations[(1, 4)] = {'change_time': 101}
        with self.assertRaises(pin.StartupPinError):
            self.entry()
        self.assertEqual(self.backends[0].security_queries, {})

    def test_missing_installed_image_has_no_fallback(self):
        error = FileNotFoundError('fixed image missing')
        self.backends[1].fail, self.backends[1].exception = 'open:4', error
        with self.assertRaises(FileNotFoundError) as caught:
            self.entry()
        self.assertIs(caught.exception, error)
        self.assertTrue(all(not b.live for b in self.backends))
        self.assertEqual(sum(c == 'open:4' for _, c in self.calls), 2)

    def test_same_handle_security_order_with_two_live_resources(self):
        with self.entry():
            for label in ('helper', 'verifier'):
                for h in range(1, 5):
                    start = self.calls.index((label, f'query:{h}:4'))
                    self.assertEqual(self.calls[start:start + 4], [(label, value) for value in
                                     (f'query:{h}:4', f'security:{h}:1', f'security:{h}:2', f'query:{h}:5')])
            first_sd = next(i for i, (_, c) in enumerate(self.calls) if c.startswith('security:'))
            self.assertLess(self.calls.index(('verifier', 'query:4:2')), first_sd)

    def test_real_source_policy_and_parser_rejections(self):
        unknown = sid(5, (21, 999))
        bad = (descriptor(owner=unknown), descriptor(dacl=acl()),
               descriptor(dacl=acl((ace(mask=0x40000, trustee=unknown),))),
               descriptor(dacl=acl((ace(mask=0x40, trustee=unknown),))),
               descriptor(dacl=acl((ace(kind=2),))),
               descriptor(dacl=acl((ace(mask=0x200),))), b'bad', bytearray(descriptor()))
        for raw in bad:
            with self.subTest(raw=raw):
                self.setUp()
                self.backends[1].security = raw
                with self.assertRaises(self.m.StartupSecurityError):
                    self.entry()
                self.assertTrue(all(not b.live for b in self.backends))
        for trusted in (HOST_BYTES, sid(), sid(5, (18,))):
            self.setUp()
            for backend in self.backends:
                backend.security = descriptor(owner=trusted, dacl=acl((ace(mask=0x10000000, trustee=trusted),)))
            with self.entry():
                pass

    def test_second_sd_drift_and_every_metadata_field(self):
        changed = descriptor(dacl=acl((ace(mask=0x120089),)))
        for index in (0, 1):
            for h in range(1, 5):
                self.setUp()
                self.backends[index].security_values[(h, 2)] = changed
                with self.assertRaises(self.m.StartupSecurityError):
                    self.entry()
                self.assertTrue(all(not b.live for b in self.backends))
        changes = {'volume_serial': 8, 'file_id': b'x' * 16, 'directory': True,
                   'reparse': True, 'delete_pending': True, 'file_type': 'pipe',
                   'links': 2, 'size': 20, 'change_time': 101}
        for field, value in changes.items():
            for index in (0, 1):
                for count in (3, 4, 5, 6):
                    with self.subTest(field=field, index=index, count=count):
                        self.setUp()
                        self.backends[index].mutations[(4, count)] = {field: value}
                        with self.assertRaises(pin.StartupPinError):
                            self.entry()
                        self.assertTrue(all(not b.live for b in self.backends))

    def test_revalidation_each_boundary_fault_global_cleanup(self):
        for index in (0, 1):
            for h in range(1, 5):
                for label in (f'query:{h}:7', f'query:{h}:8', f'query:{h}:9', f'query:{h}:10',
                              f'security:{h}:3', f'security:{h}:4'):
                    for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
                        with self.subTest(index=index, label=label, kind=kind):
                            self.setUp()
                            owner = self.entry()
                            error = kind('original')
                            self.backends[index].fail, self.backends[index].exception = label, error
                            with self.assertRaises(BaseException) as caught:
                                owner.revalidate()
                            self.assertIs(caught.exception, error)
                            self.assertTrue(owner.close_confirmed)
                            self.assertEqual(self.calls[-8:], [(r, f'close:{n}') for r in ('verifier', 'helper') for n in (4, 3, 2, 1)])

    def test_pending_registration_before_and_after_append_failure(self):
        original_class = self.m.PinnedStartupSources
        for appended in (False, True):
            for index in (0, 1):
                for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
                    with self.subTest(appended=appended, index=index, kind=kind):
                        self.setUp()
                        error = kind('registration')
                        class FaultList(list):
                            def append(inner, value):
                                if len(inner) == index:
                                    if appended:
                                        super(FaultList, inner).append(value)
                                    raise error
                                super(FaultList, inner).append(value)
                        def factory(host):
                            result = original_class(host)
                            result._owners = FaultList()
                            return result
                        with patch.object(self.m, 'PinnedStartupSources', side_effect=factory):
                            with self.assertRaises(BaseException) as caught:
                                self.entry()
                        self.assertIs(caught.exception, error)
                        self.assertTrue(all(not b.live for b in self.backends))
                        for b in self.backends:
                            self.assertEqual(len(b.closed), len(set(b.closed)))

    def test_every_close_position_with_body_exception_and_hostile_notes(self):
        class Hostile(RuntimeError):
            def __getattribute__(self, name):
                if name == '__notes__':
                    raise SystemExit('hostile notes')
                return super().__getattribute__(name)
        for index in (0, 1):
            for h in range(1, 5):
                for kind in (RuntimeError, KeyboardInterrupt, SystemExit):
                    for body_type in (RuntimeError, KeyboardInterrupt, SystemExit, Hostile):
                        with self.subTest(index=index, handle=h, kind=kind, body=body_type):
                            self.setUp()
                            owner = self.entry()
                            self.backends[index].close_faults[h] = kind('secret close')
                            body = body_type('secret body')
                            with self.assertRaises(BaseException) as caught:
                                with owner:
                                    raise body
                            self.assertIs(caught.exception, body)
                            self.assertFalse(owner.close_confirmed)
                            self.assertTrue(owner.closed)
                            self.assertEqual([b.closed for b in self.backends], [[4, 3, 2, 1]] * 2)
                            if body_type is not Hostile:
                                self.assertEqual(body.__notes__, ['Startup source cleanup unconfirmed'])
                            before = list(self.calls)
                            owner.close()
                            self.assertEqual(self.calls, before)


class SourceInterfaceTests(unittest.TestCase):
    def test_named_internal_budgets(self):
        m = importlib.import_module('icode.windows_startup_source')
        self.assertEqual(getattr(m, '_MAX_CHAIN_NODES', None), 32)
        self.assertEqual(getattr(m, '_MAX_SNAPSHOT_ACES', None), 512)

    def test_fixed_no_arguments_interface(self):
        spec = importlib.util.find_spec('icode.windows_startup_source')
        self.assertIsNotNone(spec, 'internal source consumer is missing')
        module = importlib.import_module('icode.windows_startup_source')
        entry = getattr(module, 'pin_installed_startup_sources', None)
        self.assertTrue(callable(entry), 'fixed source entry is missing')
        self.assertEqual(len(inspect.signature(entry).parameters), 0)

    def test_non_windows_and_injected_arguments_do_not_touch_native(self):
        m = importlib.import_module('icode.windows_startup_source')
        with patch.object(m.os, 'name', 'posix'), \
                patch.object(m, 'WindowsStartupHostIdentity') as identity, \
                patch.object(m, 'WindowsStartupPinBackend') as backend:
            with self.assertRaisesRegex(pin.StartupPinError, 'unavailable'):
                m.pin_installed_startup_sources()
            for kwargs in ({'path': 'C:\\x.exe'}, {'host_sid': HOST}, {'json': {}}, {'role': 'source'}):
                with self.assertRaises(TypeError):
                    m.pin_installed_startup_sources(**kwargs)
            with self.assertRaises(TypeError):
                m.pin_installed_startup_sources('C:\\x.exe')
            identity.assert_not_called()
            backend.assert_not_called()


class SourceLocatorTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('icode.windows_startup_source')

    def test_user_site_fixed_resources_without_purelib(self):
        locator = getattr(self.m, '_installed_resources', None)
        self.assertTrue(callable(locator), 'installed locator missing')
        with patch.object(self.m, '__file__', 'C:\\用户 site\\icode\\windows_startup_source.py'), \
                patch.object(self.m.sysconfig, 'get_platform', return_value='win-amd64'), \
                patch.object(self.m.sysconfig, 'get_path', side_effect=AssertionError('purelib forbidden')):
            self.assertEqual(locator(), (
                ('helper', 'C:\\用户 site\\icode\\native\\icode-sandbox-windows-x64.exe'),
                ('verifier', 'C:\\用户 site\\icode\\native\\icode-provenance-windows-x64.exe')))

    def test_lexical_shape_architecture_and_33_nodes_before_identity(self):
        paths = ('relative\\icode\\windows_startup_source.py',
                 '\\\\server\\share\\icode\\windows_startup_source.py',
                 'C:\\unsafe.\\icode\\windows_startup_source.py',
                 'C:\\CON\\icode\\windows_startup_source.py',
                 'C:\\x\\other\\windows_startup_source.py',
                 'C:\\x\\icode\\wrong.py',
                 'C:\\' + '\\'.join(['p'] * 29 + ['icode', 'windows_startup_source.py']))
        for path in paths:
            with self.subTest(path=path), patch.object(self.m.os, 'name', 'nt'), \
                    patch.object(self.m, '__file__', path), \
                    patch.object(self.m.sysconfig, 'get_platform', return_value='win-amd64'), \
                    patch.object(self.m, 'WindowsStartupHostIdentity') as identity, \
                    patch.object(self.m, 'WindowsStartupPinBackend') as backend:
                with self.assertRaises(pin.StartupPinError):
                    self.m.pin_installed_startup_sources()
                identity.assert_not_called()
                backend.assert_not_called()
        with patch.object(self.m, '__file__', 'C:\\x\\icode\\windows_startup_source.py'), \
                patch.object(self.m.sysconfig, 'get_platform', return_value='win32'), \
                patch.object(self.m.os, 'name', 'nt'), \
                patch.object(self.m, 'WindowsStartupHostIdentity') as identity:
            with self.assertRaises(ValueError):
                self.m.pin_installed_startup_sources()
            identity.assert_not_called()

    def test_32_nodes_and_arm64_are_fixed_without_resolve(self):
        path = 'C:\\' + '\\'.join(['p'] * 28 + ['icode', 'windows_startup_source.py'])
        with patch.object(self.m, '__file__', path), \
                patch.object(self.m.sysconfig, 'get_platform', return_value='win-arm64'):
            for _, resource in self.m._installed_resources():
                self.assertEqual(len(pin._local_components(resource)[1]) + 1, 32)
                self.assertTrue(resource.endswith('windows-arm64.exe'))
