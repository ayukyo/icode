"""Finite installed consumer observations; never compatibility or launch authority."""
import argparse
import ctypes
import json
import re
import sys
import sysconfig

from icode.native_helper import windows_arch_from_platform
from icode import windows_startup_source as source
from icode import windows_startup_security_native as security_native
from icode.windows_startup_security import StartupSecurityError


_WIRE_LIMIT = 32 * 1024
_MAX_NODES = 32
_MAX_ALLOCATIONS = 128
_REASONS = {
    'startup security owner is not trusted for role': 'owner_untrusted',
    'untrusted ACE permits startup mutation': 'mutation_untrusted',
    'empty DACL cannot establish usable startup security': 'empty_dacl',
}
_TOP_KEYS = {'schema_version', 'scope', 'source_sha', 'architecture', 'python', 'windows',
             'observation_complete', 'baseline', 'consumer', 'resources', 'policy_events',
             'security_reads', 'allocations', 'confirmed_frees', 'unconfirmed_frees',
             'close_order', 'reverse_close_confirmed', 'compatibility_accepted',
             'launch_authorized', 'protected_observed'}


def _require(condition):
    if not condition:
        raise ValueError('invalid_installed_source_receipt')


def _object(value, keys):
    _require(type(value) is dict and value.keys() == keys)


def _integer(value, low, high):
    _require(type(value) is int and low <= value <= high)


def _text(value, choices):
    _require(type(value) is str and value in choices)


def _versions(python, windows):
    _require(type(python) is list and len(python) == 2)
    _integer(python[0], 3, 3)
    _integer(python[1], 12, 12)
    _require(type(windows) is list and len(windows) == 3)
    for value in windows:
        _integer(value, 0, 2**32 - 1)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _reason(error):
    if (type(error) is StartupSecurityError and len(error.args) == 1
            and type(error.args[0]) is str):
        return _REASONS.get(error.args[0])
    return None


def _run_consumer(observation=None):
    try:
        owner = source.pin_installed_startup_sources()
    except StartupSecurityError as error:
        if observation is not None and observation.rejection is not error:
            raise
        reason = _reason(error)
        if reason is None:
            raise
        try:
            notes = BaseException.__getattribute__(error, '__notes__')
        except AttributeError:
            notes = []
        except BaseException:
            raise error
        # Pure policy refusals carry no notes. Absence is not cleanup proof,
        # but any visible or malformed note is already uncertainty, not an
        # ordinary unobserved refusal. Never inspect or print note contents.
        if type(notes) is not list or notes:
            raise
        return {'outcome': 'rejected', 'reason': reason}, None
    owner.close()
    if owner.close_confirmed is not True:
        raise ValueError('installed_source_observation_failed')
    return {'outcome': 'ready', 'reason': 'pass'}, True


class _Observation:
    """One synchronous production call's finite private native-return ledger."""

    def __init__(self):
        self.nodes = [[], []]
        self.backends = 0
        self.handles = {}
        self.closed = []
        self.allocations = []
        self.active_allocations = {}
        self.reads = []
        self.pending = []
        self.events = []
        self.current = None
        self.fault = False
        self.rejection = None

    def opened(self, resource, handle):
        if (resource not in (0, 1) or len(self.nodes[resource]) >= _MAX_NODES
                or type(handle) is not int or handle in self.handles):
            self.fault = True
            return
        node = (resource, len(self.nodes[resource]))
        self.nodes[resource].append(node)
        self.handles[handle] = node

    def close(self, handle, result):
        node = self.handles.get(handle)
        if (node is None or node in self.closed or type(result) is not int or result == 0):
            self.fault = True
            return
        self.closed.append(node)

    def allocated(self, pointer):
        if not pointer:
            return
        if (self.current is None or pointer in self.active_allocations
                or len(self.allocations) >= _MAX_ALLOCATIONS):
            self.fault = True
            return
        allocation = {'node': self.current, 'attempted': False, 'confirmed': False}
        self.allocations.append(allocation)
        self.active_allocations[pointer] = allocation

    def freeing(self, pointer):
        allocation = self.active_allocations.get(pointer)
        if allocation is None or allocation['attempted']:
            self.fault = True
            return None
        allocation['attempted'] = True
        return allocation

    def freed(self, pointer, allocation, result):
        if allocation is None or result is not None:
            self.fault = True
            return
        allocation['confirmed'] = True
        del self.active_allocations[pointer]

    def policy(self, raw, result):
        acquired = self.nodes[0] + self.nodes[1]
        ordinal = len(self.events)
        if (len(self.pending) != 2 or ordinal >= len(acquired)
                or any(node != acquired[ordinal] or value != raw for node, value in self.pending)
                or (self.events and self.events[-1]['result'] != 'pass')):
            self.fault = True
            return
        resource, index = acquired[ordinal]
        self.events.append({'resource': ('helper', 'verifier')[resource], 'index': index,
                            'result': result, 'security_reads': 2, 'confirmed_frees': 2})
        self.pending.clear()

    def receipt(self):
        acquired = self.nodes[0] + self.nodes[1]
        expected_reads = [node for node in acquired[:len(self.events)] for _ in range(2)]
        if (self.fault or self.backends != 2 or any(not 2 <= len(nodes) <= _MAX_NODES for nodes in self.nodes)
                or self.closed != list(reversed(acquired)) or self.active_allocations or self.pending
                or len(self.reads) != len(self.allocations) or len(self.reads) != 2 * len(self.events)
                or self.reads != expected_reads
                or [allocation['node'] for allocation in self.allocations] != expected_reads
                or any(not allocation['confirmed'] for allocation in self.allocations)):
            raise ValueError('installed_source_observation_failed')
        return {'resources': [{'resource': name, 'nodes': len(nodes), 'opened': len(nodes),
                               'confirmed_closes': len(nodes), 'unconfirmed_closes': 0}
                              for name, nodes in zip(('helper', 'verifier'), self.nodes)],
                'policy_events': self.events, 'security_reads': len(self.reads),
                'allocations': len(self.allocations), 'confirmed_frees': len(self.allocations),
                'unconfirmed_frees': 0,
                'close_order': [{'resource': ('helper', 'verifier')[resource], 'index': index}
                                for resource, index in self.closed], 'reverse_close_confirmed': True}


def _observe_consumer():
    observation = _Observation()
    backend_base = source.WindowsStartupPinBackend
    reader_base = security_native.WindowsStartupSecurityReader
    policy_base = source.check_startup_security

    class Backend(backend_base):
        def __init__(self):
            self._observation_resource = observation.backends
            observation.backends += 1
            super().__init__()

        def _open(self, *arguments, **keywords):
            try:
                handle = super()._open(*arguments, **keywords)
            except BaseException:
                observation.fault = True
                raise
            try:
                observation.opened(self._observation_resource, handle)
            except BaseException:
                observation.fault = True
                # Until return, the caller has not registered this acquisition.
                # Retire it once, without letting cleanup replace the body.
                try:
                    super().close(handle)
                except BaseException:
                    pass
                raise
            return handle

        def _call(self, function, *arguments):
            try:
                result = super()._call(function, *arguments)
            except BaseException:
                observation.fault = True
                raise
            if function is self._kernel32.CloseHandle:
                observation.close(arguments[0], result)
            return result

        def query_security(self, handle):
            observation.current = observation.handles.get(handle)
            try:
                return super().query_security(handle)
            finally:
                observation.current = None

    class Reader(reader_base):
        def _call(self, function, *arguments):
            allocation = None
            recording_error = None
            is_query = function is self._advapi32.GetSecurityInfo
            is_free = function is self._kernel32.LocalFree
            if is_free:
                try:
                    allocation = observation.freeing(arguments[0])
                except BaseException as error:
                    observation.fault = True
                    recording_error = error
            try:
                result = super()._call(function, *arguments)
            except BaseException:
                observation.fault = True
                # Recording is ancillary to the native body error. In
                # particular, a second interrupt must not replace its identity.
                if is_query:
                    try:
                        pointer = ctypes.cast(arguments[-1], ctypes.POINTER(ctypes.c_void_p))[0]
                        observation.allocated(pointer)
                    except BaseException:
                        observation.fault = True
                raise
            # Even failed status receipts with nonNULL outputs own a new
            # generation; the production reader validates status and releases.
            if is_query:
                pointer = ctypes.cast(arguments[-1], ctypes.POINTER(ctypes.c_void_p))[0]
                observation.allocated(pointer)
            if is_free:
                if recording_error is not None:
                    # Observation must never prevent the real cleanup call.
                    # Its receipt is unknown, and its original recording error
                    # propagates only after that one actual release attempt.
                    raise recording_error
                observation.freed(arguments[0], allocation, result)
            return result

        def read(self, handle):
            before = len(observation.allocations)
            try:
                raw = super().read(handle)
            except BaseException:
                observation.fault = True
                raise
            new = observation.allocations[before:]
            if (len(new) != 1 or new[0]['node'] != observation.current
                    or not new[0]['confirmed'] or type(raw) is not bytes):
                observation.fault = True
            observation.reads.append(observation.current)
            observation.pending.append((observation.current, raw))
            return raw

    def policy(*arguments, **keywords):
        try:
            result = policy_base(*arguments, **keywords)
        except BaseException as error:
            reason = _reason(error)
            if reason is None:
                observation.fault = True
            else:
                try:
                    observation.policy(arguments[0], reason)
                    observation.rejection = error
                except BaseException:
                    observation.fault = True
            raise
        observation.policy(arguments[0], 'pass')
        return result

    try:
        source.WindowsStartupPinBackend = Backend
        source.check_startup_security = policy
        security_native.WindowsStartupSecurityReader = Reader
        result, closed = _run_consumer(observation)
    finally:
        source.WindowsStartupPinBackend = backend_base
        source.check_startup_security = policy_base
        security_native.WindowsStartupSecurityReader = reader_base
    return result, observation.receipt()


def probe(source_sha):
    if (sys.platform != 'win32' or type(source_sha) is not str
            or re.fullmatch('[0-9a-f]{40}', source_sha) is None):
        raise ValueError('invalid_installed_source_observation_input')
    python = [sys.version_info.major, sys.version_info.minor]
    version = sys.getwindowsversion()
    windows = [version.major, version.minor, version.build]
    _versions(python, windows)
    arch = windows_arch_from_platform(sysconfig.get_platform())
    baseline, baseline_closed = _run_consumer()
    consumer, observation = _observe_consumer()
    if consumer != baseline:
        raise ValueError('installed_source_observation_failed')
    return {'schema_version': 1, 'scope': 'installed_source_consumer_observation',
            'source_sha': source_sha, 'architecture': arch, 'python': python, 'windows': windows,
            'observation_complete': True,
            'baseline': {'outcome': baseline['outcome'], 'close_confirmed': baseline_closed},
            'consumer': consumer, **observation, 'compatibility_accepted': False,
            'launch_authorized': False, 'protected_observed': False}


def validate_wire(wire, source_sha, arch, *, expected_python, expected_windows):
    """Validate the finite wire contract, not independent native evidence."""
    try:
        _require(type(source_sha) is str and re.fullmatch('[0-9a-f]{40}', source_sha) is not None)
        _text(arch, {'x64', 'arm64'})
        _versions(expected_python, expected_windows)
        _require(type(wire) is bytes and 1 <= len(wire) <= _WIRE_LIMIT)
        ending = b'\r\n' if wire.endswith(b'\r\n') else b'\n'
        _require(wire.endswith(ending))
        data = json.loads(wire.decode('ascii', 'strict'), object_pairs_hook=_unique_object)
        _require(json.dumps(data, separators=(',', ':')).encode('ascii') + ending == wire)
        _object(data, _TOP_KEYS)
        _integer(data['schema_version'], 1, 1)
        _text(data['scope'], {'installed_source_consumer_observation'})
        _text(data['source_sha'], {source_sha})
        _text(data['architecture'], {arch})
        _versions(data['python'], data['windows'])
        _require(data['python'] == expected_python and data['windows'] == expected_windows)
        for key, value in (('observation_complete', True), ('reverse_close_confirmed', True),
                           ('compatibility_accepted', False), ('launch_authorized', False),
                           ('protected_observed', False)):
            _require(data[key] is value)
        _object(data['baseline'], {'outcome', 'close_confirmed'})
        _object(data['consumer'], {'outcome', 'reason'})
        outcome = data['consumer']['outcome']
        _text(outcome, {'ready', 'rejected'})
        _text(data['baseline']['outcome'], {outcome})
        _require(data['baseline']['close_confirmed'] is (True if outcome == 'ready' else None))
        _text(data['consumer']['reason'], {'pass'} if outcome == 'ready' else set(_REASONS.values()))
        resources = data['resources']
        _require(type(resources) is list and len(resources) == 2)
        acquired = []
        for resource, name in zip(resources, ('helper', 'verifier')):
            _object(resource, {'resource', 'nodes', 'opened', 'confirmed_closes', 'unconfirmed_closes'})
            _text(resource['resource'], {name})
            count = resource['nodes']
            _integer(count, 2, _MAX_NODES)
            for key in ('opened', 'confirmed_closes'):
                _integer(resource[key], count, count)
            _integer(resource['unconfirmed_closes'], 0, 0)
            acquired.extend((name, index) for index in range(count))
        events = data['policy_events']
        _require(type(events) is list and 1 <= len(events) <= len(acquired))
        if outcome == 'ready':
            _require(len(events) == len(acquired))
        for ordinal, event in enumerate(events):
            _object(event, {'resource', 'index', 'result', 'security_reads', 'confirmed_frees'})
            name, index = acquired[ordinal]
            _text(event['resource'], {name})
            _integer(event['index'], index, index)
            result = data['consumer']['reason'] if ordinal == len(events) - 1 else 'pass'
            _text(event['result'], {result})
            _integer(event['security_reads'], 2, 2)
            _integer(event['confirmed_frees'], 2, 2)
        expected = 2 * len(events)
        _require(expected <= _MAX_ALLOCATIONS)
        for key in ('security_reads', 'allocations', 'confirmed_frees'):
            _integer(data[key], expected, expected)
        _integer(data['unconfirmed_frees'], 0, 0)
        order = data['close_order']
        _require(type(order) is list and len(order) == len(acquired))
        for item, (name, index) in zip(order, reversed(acquired)):
            _object(item, {'resource', 'index'})
            _text(item['resource'], {name})
            _integer(item['index'], index, index)
        return data
    except Exception:
        raise ValueError('invalid_installed_source_receipt') from None


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError('invalid_installed_source_observation_input')

    try:
        parser = Parser(description=__doc__, add_help=False)
        parser.add_argument('--source-sha', required=True)
        args = parser.parse_args(argv)
        data = probe(args.source_sha)
        wire = json.dumps(data, separators=(',', ':')).encode('ascii') + b'\n'
        validate_wire(wire, args.source_sha, data['architecture'],
                      expected_python=data['python'], expected_windows=data['windows'])
        sys.stdout.write(wire.decode('ascii'))
        return 0
    except KeyboardInterrupt:
        code = 130
    except (Exception, SystemExit):
        code = 1
    sys.stderr.write('windows_installed_source_observation_failed\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
