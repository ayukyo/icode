"""Portable observation contracts; not Windows integration evidence."""
import importlib
import importlib.util
import sys
import unittest
from unittest.mock import patch
from pathlib import PureWindowsPath
import json
import io
import copy
import hashlib
from types import SimpleNamespace
from contextlib import redirect_stdout, redirect_stderr
from tests.test_windows_startup_security import descriptor, acl, ace, sid
from tests.test_windows_startup_pin import FakeBackend
from icode import windows_startup_pin as pin
from icode.windows_startup_security import parse_startup_security


SHA = "a" * 40
HOST = "S-1-5-21-7"


def module():
    return importlib.import_module("scripts.probe_windows_installed_chain")


class InstalledLocatorPolicyTests(unittest.TestCase):
    def test_unknown_policy_messages_and_composite_args_propagate(self):
        m = module()
        for args in (("PRIVATE",), ("untrusted ACE permits startup mutation", "PRIVATE")):
            original = m.StartupSecurityError(*args)
            with patch.object(m, "check_startup_security", side_effect=original):
                with self.assertRaises(m.StartupSecurityError) as raised:
                    m._policy_result(descriptor(), HOST, True)
                self.assertIs(raised.exception, original)

    def test_locator_rejects_unsupported_arch_and_bad_purelib_before_native(self):
        m = module()
        for platform, purelib in (("linux-x86_64", "C:\\site"), ("win32", "C:\\site"), ("win-amd64", "site"), ("win-amd64", "C:\\a\\..\\site")):
            with patch.object(m.icode, "__file__", "C:\\site\\icode\\__init__.py"), patch.object(m.sysconfig, "get_path", return_value=purelib), patch.object(m.sysconfig, "get_platform", return_value=platform), patch.object(m, "WindowsStartupPinBackend") as backend:
                with self.assertRaises(Exception):
                    m._installed_resources()
                backend.assert_not_called()

    def test_all_categories_and_source_owner_policy(self):
        m = module()
        categories = [(sid(), "admin"), (sid(5, (18,)), "system"), (sid(5, (21, 7)), "host"), (sid(1, (0,)), "everyone"), (sid(5, (11,)), "authenticated_users"), (sid(5, (32, 545)), "builtin_users"), (sid(3, (0,)), "creator_owner"), (sid(3, (4,)), "owner_rights"), (sid(5, (21, 8)), "other")]
        for raw_sid, category in categories:
            owner_text = "S-1-" + str(int.from_bytes(raw_sid[2:8], "big")) + "".join("-" + str(int.from_bytes(raw_sid[i:i + 4], "little")) for i in range(8, len(raw_sid), 4))
            self.assertEqual(m._trustee_category(owner_text, HOST), category)
        for owner in (sid(), sid(5, (18,)), sid(5, (21, 7))):
            self.assertEqual(m._policy_result(descriptor(owner=owner, dacl=acl((ace(mask=2, trustee=sid(3, (4,))),))), HOST, True), "pass")
        for allowed in (0, 1):
            raw = descriptor(dacl=acl((ace(allowed, 8, 2, sid(1, (0,))),)))
            self.assertEqual(m._policy_result(raw, HOST, True), "mutation_untrusted" if allowed == 0 else "pass")

    def test_installed_exact_lexical_paths_and_architectures(self):
        m = module()
        for platform, arch in (("win-amd64", "x64"), ("win-arm64", "arm64")):
            with patch.object(m.icode, "__file__", "C:\\目录\\site\\icode\\__init__.py"), patch.object(m.sysconfig, "get_path", return_value="C:\\目录\\site"), patch.object(m.sysconfig, "get_platform", return_value=platform):
                actual, resources = m._installed_resources()
                self.assertEqual(actual, arch)
                self.assertEqual(resources, tuple((r, PureWindowsPath(f"C:\\目录\\site\\icode\\native\\icode-{n}-windows-{arch}.exe")) for r, n in (("helper", "sandbox"), ("verifier", "provenance"))))

    def test_locator_refuses_relative_outside_dotdot_and_same_name(self):
        m = module()
        for bad in ("icode\\__init__.py", "D:\\site\\icode\\__init__.py", "C:\\site\\a\\..\\icode\\__init__.py", "C:\\site\\other\\__init__.py", "C:\\site\\icode\\same.py"):
            with patch.object(m.icode, "__file__", bad), patch.object(m.sysconfig, "get_path", return_value="C:\\site"), patch.object(m.sysconfig, "get_platform", return_value="win-amd64"):
                with self.assertRaises(Exception):
                    m._installed_resources()

    def test_policy_supported_descriptors_crosscheck(self):
        m = module()
        cases = [(descriptor(), True, "pass"), (descriptor(owner=sid(5, (21, 8))), True, "owner_untrusted"), (descriptor(dacl=acl()), True, "empty_dacl"), (descriptor(dacl=acl((ace(mask=2, trustee=sid(1, (0,))),))), True, "mutation_untrusted"), (descriptor(dacl=acl((ace(mask=0x40, trustee=sid(1, (0,))),))), False, "pass"), (descriptor(dacl=acl((ace(mask=0x40, trustee=sid(1, (0,))),))), True, "mutation_untrusted"), (descriptor(dacl=acl((ace(mask=2, trustee=sid(3, (4,))),))), True, "pass")]
        for raw, directory, result in cases:
            self.assertEqual(m._policy_result(raw, HOST, directory), result)

    def test_categories_priority(self):
        m = module()
        self.assertEqual(m._owner_category("S-1-5-32-544", "S-1-5-32-544"), "admin")
        self.assertEqual(m._owner_category("S-1-5-18", "S-1-5-18"), "system")
        self.assertEqual(m._trustee_category(HOST, HOST), "host")


class InstalledChainInterfaceTests(unittest.TestCase):
    def test_observation_interfaces_exist(self):
        self.assertIsNotNone(importlib.util.find_spec("scripts.probe_windows_installed_chain"))
        module = importlib.import_module("scripts.probe_windows_installed_chain")
        for name in ("_installed_resources", "_observe_resource", "probe", "validate_wire", "main"):
            self.assertTrue(callable(getattr(module, name, None)), name)


class ObservationBackend(FakeBackend):
    def __init__(self, count=4, security=None, failure=None, exception=None):
        super().__init__(pin)
        self.count = count
        self.security = security or descriptor()
        self.failure = failure
        self.error = exception or RuntimeError("PRIVATE")
        self.security_calls = []
        self.security_changes = {}
        self.metadata_changes = {}
        self.close_error = None

    def query(self, handle):
        from dataclasses import replace
        self.queries[handle] = self.queries.get(handle, 0) + 1
        position = (handle, self.queries[handle])
        if self.failure == ("query", *position):
            raise self.error
        value = pin.StartupFileMetadata(7, handle.to_bytes(16, "little"), handle < self.count, False, False, "disk", 1, 0 if handle < self.count else len(self.data), 100)
        return replace(value, **self.metadata_changes.get(position, {}))

    def read(self, handle, offset, count):
        self.assert_live(handle)
        return self.data[offset:offset + count]

    def assert_live(self, handle):
        assert handle in self.live

    def query_security(self, handle):
        self.assert_live(handle)
        index = self.security_calls.count(handle) + 1
        self.security_calls.append(handle)
        if self.failure == ("security", handle, index):
            raise self.error
        raw = self.security_changes.get((handle, index), self.security)
        # Model the real reader returning an owned copy only after parsing.
        raw = bytes(bytearray(raw))
        parse_startup_security(raw)
        return raw

    def close(self, handle):
        self.closed.append(handle)
        self.live.remove(handle)
        if self.close_error is not None:
            raise self.close_error


class InstalledObservationTests(unittest.TestCase):
    def test_structural_roles_control_and_actual_child_edges(self):
        for count in (2, 4, 32):
            backend = ObservationBackend(count=count)
            leaf = descriptor(control=0x9004)
            backend.security_changes.update({(count, read): leaf for read in (1, 2)})
            result = self.observe(backend)
            for index, node in enumerate(result["chain"]):
                self.assertIn("structural_roles", node)
                self.assertIn("dacl_protected", node)
                self.assertIn("inheritance_to_next", node)
                expected = []
                if index < count - 1:
                    expected.append("route_ancestor")
                if index == 0:
                    expected.append("volume_root")
                if index == count - 2:
                    expected.append("image_parent")
                if index == count - 1:
                    expected.append("image_leaf")
                self.assertEqual(node["structural_roles"], expected)
                self.assertIs(node["dacl_protected"], index == count - 1)
                edge = node["inheritance_to_next"]
                if index == count - 1:
                    self.assertIsNone(edge)
                else:
                    self.assertEqual(edge["next_index"], index + 1)
                    self.assertIs(edge["child_dacl_protected"], index == count - 2)
                    self.assertEqual(edge["target_kind"], "file" if index == count - 2 else "directory")
                    self.assertEqual(edge["flag_candidate_indices"], [])
                    self.assertEqual(edge["state"], "no_flag_candidates")
            self.assertFalse(backend.live)
            self.assertEqual(backend.closed, list(range(count, 0, -1)))

    def test_direct_candidates_separate_directory_leaf_and_keep_io_policy(self):
        mask = 2 | 4 | 0x40 | 0x10 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x40000000 | 0x10000000
        raw = descriptor(dacl=acl((ace(0, 0, mask, sid(1, (0,))),
                                   ace(1, 0, mask, sid(1, (0,))),
                                   ace(0, 8, mask, sid(1, (0,))))))
        result = self.observe(ObservationBackend(security=raw))
        common = ["write_ea", "write_attributes", "delete_object", "write_dacl",
                  "write_owner", "generic_write", "generic_all"]
        for node in result["chain"]:
            entries = node["entries"]
            self.assertIn("direct_operation_candidates", entries[0])
            expected = (["add_file", "add_subdirectory", "delete_child"] if node["directory"]
                        else ["write_data", "append_data"]) + common
            self.assertEqual(entries[0]["direct_operation_candidates"], expected)
            self.assertEqual(entries[1]["direct_operation_candidates"], [])
            self.assertEqual(entries[2]["direct_operation_candidates"], [])
            self.assertEqual(node["policy_result"], "mutation_untrusted")
            self.assertEqual(entries[2]["mutation"], mask if node["directory"] else mask & ~0x40)

    def test_single_edge_flags_include_deny_io_np_and_use_child_control(self):
        flags = (0, 1, 2, 4, 8, 16, 1 | 4, 2 | 8, 1 | 2 | 4 | 8 | 16)
        entries = tuple(ace(index % 2, value, 2) for index, value in enumerate(flags))
        for protected in (False, True):
            backend = ObservationBackend(security=descriptor(dacl=acl(entries)))
            parent = descriptor(dacl=acl(entries), control=0x8004 if protected else 0x9004)
            child = descriptor(dacl=acl(entries), control=0x9004 if protected else 0x8004)
            backend.security_changes.update({(handle, read): raw
                                             for handle, raw in ((3, parent), (4, child))
                                             for read in (1, 2)})
            result = self.observe(backend)
            for index, bit, target in ((0, 2, "directory"), (2, 1, "file")):
                self.assertIn("inheritance_to_next", result["chain"][index])
                edge = result["chain"][index]["inheritance_to_next"]
                self.assertEqual(edge["next_index"], index + 1)
                self.assertEqual(edge["target_kind"], target)
                self.assertEqual(edge["flag_candidate_indices"],
                                 [i for i, value in enumerate(flags) if value & bit])
            edge = result["chain"][2]["inheritance_to_next"]
            self.assertIs(edge["child_dacl_protected"], protected)
            self.assertEqual(edge["state"], "flag_candidates_child_protected" if protected
                             else "flag_candidates_child_unprotected")

    def test_chain33_and_constructor_failure_zero_opens(self):
        m = module()
        with patch.object(m, "WindowsStartupPinBackend") as constructor:
            with self.assertRaises(ValueError):
                m._observe_resource("helper", PureWindowsPath("C:\\" + "\\".join(["a"] * 32)), HOST, [0])
            constructor.assert_not_called()
        original = RuntimeError("PRIVATE constructor")
        with patch.object(m, "WindowsStartupPinBackend", side_effect=original), patch.object(m, "pin_startup_file") as opened:
            with self.assertRaises(RuntimeError) as raised:
                m._observe_resource("helper", PureWindowsPath("C:\\a\\file.exe"), HOST, [0])
            self.assertIs(raised.exception, original)
            opened.assert_not_called()

    def test_pin_failure_never_returned_as_unobserved(self):
        backend = ObservationBackend()
        backend.fail = "open:4"
        with self.assertRaises(RuntimeError):
            self.observe(backend)
        self.assertEqual(backend.closed, [3, 2, 1])

    def test_hostile_body_and_close_exception_preserve_identity(self):
        class HostileInterrupt(KeyboardInterrupt):
            def __getattribute__(self, name):
                if name in ("__notes__", "add_note", "__str__"):
                    raise RuntimeError("PRIVATE hook")
                return super().__getattribute__(name)
        original = HostileInterrupt("PRIVATE body")
        backend = ObservationBackend(failure=("security", 3, 2), exception=original)
        backend.close_error = HostileInterrupt("PRIVATE close")
        with self.assertRaises(HostileInterrupt) as raised:
            self.observe(backend)
        self.assertIs(raised.exception, original)
        self.assertEqual(backend.closed, [4, 3, 2, 1])

    def test_invalid_budget_and_exact_descriptor_types_cleanup(self):
        for budget in ([], [True], [-1], [513], (0,), [0, 1]):
            backend = ObservationBackend()
            with self.assertRaises(Exception):
                self.observe(backend, budget)
            self.assertFalse(backend.live)
        backend = ObservationBackend()
        real = backend.query_security
        def aliased(handle):
            return bytearray(real(handle))
        backend.query_security = aliased
        with self.assertRaises(Exception):
            self.observe(backend)
        self.assertFalse(backend.live)

    def test_unknown_returned_policy_is_failure(self):
        backend = ObservationBackend()
        with patch.object(module(), "_policy_result", return_value="PRIVATE UNKNOWN"):
            with self.assertRaises(Exception):
                self.observe(backend)
        self.assertFalse(backend.live)

    def observe(self, backend, budget=None):
        m = module()
        path = "C:\\" + "\\".join(["a"] * (backend.count - 2) + ["start.exe"])
        with patch.object(m, "WindowsStartupPinBackend", return_value=backend):
            return m._observe_resource("helper", PureWindowsPath(path), HOST, [0] if budget is None else budget)

    def test_success_owns_real_pin_bytes_and_closes_once(self):
        backend = ObservationBackend()
        result = self.observe(backend)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["owned_handles"], 4)
        self.assertEqual(result["confirmed_closes"], 4)
        self.assertEqual(result["image_sha256"], hashlib.sha256(backend.data).hexdigest())
        self.assertEqual(backend.closed, [4, 3, 2, 1])
        self.assertEqual(backend.security_calls, [1, 1, 2, 2, 3, 3, 4, 4])
        self.assertFalse(backend.live)

    def test_every_security_position_fails_and_preserves_original(self):
        for handle in range(1, 5):
            for read in (1, 2):
                for exc in (RuntimeError("PRIVATE"), KeyboardInterrupt("PRIVATE"), SystemExit("PRIVATE"), module().StartupSecurityError("empty DACL cannot establish usable startup security")):
                    backend = ObservationBackend(failure=("security", handle, read), exception=exc)
                    with self.assertRaises(type(exc)) as raised:
                        self.observe(backend)
                    self.assertIs(raised.exception, exc)
                    self.assertEqual(backend.closed, [4, 3, 2, 1])

    def test_every_metadata_position_fails_and_closes(self):
        for handle in range(1, 5):
            for query in range(1, 7):
                backend = ObservationBackend(failure=("query", handle, query))
                with self.assertRaises(RuntimeError) as raised:
                    self.observe(backend)
                self.assertIs(raised.exception, backend.error)
                self.assertFalse(backend.live)
                self.assertEqual(len(backend.closed), len(set(backend.closed)))

    def test_supported_rejection_continues_entire_chain(self):
        backend = ObservationBackend(security=descriptor(dacl=acl()))
        result = self.observe(backend)
        self.assertIsInstance(result, dict)
        self.assertEqual([n["policy_result"] for n in result["chain"]], ["empty_dacl"] * 4)
        self.assertEqual(len(backend.security_calls), 8)

    def test_metadata_and_descriptor_drift_fail(self):
        for handle in range(1, 5):
            for kind in ("metadata_before", "metadata_after", "descriptor", "unsupported_before", "unsupported_after"):
                backend = ObservationBackend()
                if kind.startswith("metadata"):
                    backend.metadata_changes[(handle, 4 if kind.endswith("before") else 5)] = {"change_time": 101}
                else:
                    backend.security_changes[(handle, 1 if kind.endswith("before") else 2)] = descriptor(owner=sid(5, (18,))) if kind == "descriptor" else b"bad"
                with self.assertRaises(Exception):
                    self.observe(backend)
                self.assertFalse(backend.live)

    def test_unknown_policy_and_extra_parse_fail_preserve_identity(self):
        m = module()
        for name in ("check_startup_security", "parse_startup_security"):
            for handle in range(1, 9 if name == "parse_startup_security" else 5):
                original = m.StartupSecurityError("UNKNOWN PRIVATE")
                real = getattr(m, name)
                calls = [0]
                def fail(*args, **kwargs):
                    calls[0] += 1
                    if calls[0] == handle:
                        raise original
                    return real(*args, **kwargs)
                backend = ObservationBackend()
                with patch.object(m, name, side_effect=fail):
                    with self.assertRaises(m.StartupSecurityError) as raised:
                        self.observe(backend)
                self.assertIs(raised.exception, original)
                self.assertFalse(backend.live)

    def test_close_failure_interrupt_and_body_priority_no_retry(self):
        for close in (RuntimeError("CLOSE PRIVATE"), KeyboardInterrupt("CLOSE PRIVATE"), SystemExit("CLOSE PRIVATE")):
            for body in (None, KeyboardInterrupt("BODY PRIVATE"), SystemExit("BODY PRIVATE")):
                backend = ObservationBackend(failure=("security", 1, 1) if body is not None else None, exception=body)
                backend.close_error = close
                expected = type(body) if body is not None else type(close) if not isinstance(close, Exception) else pin.StartupPinCloseError
                with self.assertRaises(expected) as raised:
                    self.observe(backend)
                if body is not None:
                    self.assertIs(raised.exception, body)
                self.assertEqual(backend.closed, [4, 3, 2, 1])

    def test_chain_and_cumulative_ace_budget_boundaries(self):
        self.assertIsInstance(self.observe(ObservationBackend(count=32)), dict)
        with self.assertRaises(Exception):
            self.observe(ObservationBackend(count=33))
        budget = [504]
        self.assertIsInstance(self.observe(ObservationBackend(), budget), dict)
        self.assertEqual(budget, [512])
        with self.assertRaises(Exception):
            self.observe(ObservationBackend(), [506])


class InstalledProbeTests(unittest.TestCase):
    def test_probe_fresh_native_backends_accept_recycled_retired_numbers(self):
        # Controlled DLL outputs exercise the production transport and owner;
        # these are portable ABI fixtures, not native Windows evidence.
        from tests import test_windows_startup_native as native_tests
        fixtures = [native_tests.NativeTransportTests() for _ in range(2)]
        raw = descriptor()
        for fixture in fixtures:
            fixture.setUp()
            fixture.b._security_reader = SimpleNamespace(read=lambda handle: bytes(bytearray(raw)))
        data = self.run_probe([fixture.b for fixture in fixtures])
        self.assertIsInstance(data, dict)
        self.assertEqual(self.backend_factory.call_count, 2)
        for fixture in fixtures:
            self.assertEqual(fixture.b._retired, {10, 11, 12, 13})
            self.assertEqual(fixture.b._active, {})
            self.assertEqual([args[0] for args in fixture.k.CloseHandle.calls], [13, 12, 11, 10])
        # The old backend rejects even a successful new native acquisition of
        # its retired number; the second fresh backend already accepted it.
        first = fixtures[0]
        first.next_handle = 10
        with self.assertRaises(pin.StartupPinError):
            first.b.open_root("C:")
        self.assertEqual(first.b._active, {})
        self.assertEqual(fixtures[1].next_handle, 14)

    def test_actual_two_resource_ace512_accepts_514_refuses(self):
        raw = descriptor(dacl=acl(tuple(ace() for _ in range(32))))
        data = self.run_probe([ObservationBackend(security=raw), ObservationBackend(security=raw)])
        self.assertIsInstance(data, dict)
        self.assertEqual(sum(len(n["entries"]) * 2 for r in data["resources"] for n in r["chain"]), 512)
        extra = descriptor(dacl=acl(tuple(ace() for _ in range(33))))
        backends = [ObservationBackend(security=raw), ObservationBackend(security=raw)]
        backends[1].security_changes.update({(4, 1): extra, (4, 2): extra})
        with self.assertRaises(Exception):
            self.run_probe(backends)
        self.assertTrue(all(not b.live for b in backends))

    def run_probe(self, backends, identity=None, source=SHA):
        m = module()
        identity = identity or SimpleNamespace(capture=lambda: HOST, cleanup_unconfirmed=False)
        with patch.object(m.sys, "platform", "win32"), patch.object(m.sys, "version_info", SimpleNamespace(major=3, minor=12)), patch.object(m.sys, "getwindowsversion", return_value=SimpleNamespace(major=10, minor=0, build=123), create=True), patch.object(m, "_installed_resources", return_value=("x64", (("helper", PureWindowsPath("C:\\a\\b\\start.exe")), ("verifier", PureWindowsPath("C:\\a\\b\\start.exe"))))), patch.object(m, "WindowsStartupHostIdentity", return_value=identity), patch.object(m, "WindowsStartupPinBackend", side_effect=backends) as factory:
            self.backend_factory = factory
            return m.probe(source)

    def test_two_resources_independent_backends_same_numeric_handles(self):
        backends = [ObservationBackend(security=descriptor(dacl=acl())), ObservationBackend()]
        result = self.run_probe(backends)
        self.assertIsInstance(result, dict)
        self.assertFalse(result["source_policy_all_passed"])
        self.assertTrue(result["observation_complete"])
        self.assertEqual([r["resource"] for r in result["resources"]], ["helper", "verifier"])
        for backend in backends:
            self.assertEqual(backend.closed, [4, 3, 2, 1])

    def test_platform_and_bad_sha_zero_api(self):
        m = module()
        for platform, source in (("linux", SHA), ("win32", SHA.upper()), ("win32", True), ("win32", "a" * 39), ("win32", "a" * 41), ("win32", "PRIVATE")):
            with patch.object(m.sys, "platform", platform), patch.object(m, "_installed_resources") as locator, patch.object(m, "WindowsStartupHostIdentity") as identity, patch.object(m, "WindowsStartupPinBackend") as backend:
                with self.assertRaises(Exception):
                    m.probe(source)
                locator.assert_not_called()
                identity.assert_not_called()
                backend.assert_not_called()

    def test_only_python312_producer_can_reach_native_apis(self):
        m = module()
        for minor in (10, 11, 13):
            with self.subTest(minor=minor), patch.object(m.sys, "platform", "win32"), \
                 patch.object(m.sys, "version_info", SimpleNamespace(major=3, minor=minor)), \
                 patch.object(m, "_installed_resources") as locator, \
                 patch.object(m, "WindowsStartupHostIdentity") as identity:
                with self.assertRaises(ValueError):
                    m.probe(SHA)
                locator.assert_not_called()
                identity.assert_not_called()

    def test_identity_refusal_or_unconfirmed_prevents_opens(self):
        for unconfirmed in (False, True):
            capture = unittest.mock.Mock(side_effect=RuntimeError("PRIVATE")) if not unconfirmed else unittest.mock.Mock(return_value=HOST)
            identity = SimpleNamespace(capture=capture, cleanup_unconfirmed=unconfirmed)
            with self.assertRaises(Exception):
                self.run_probe([], identity=identity)
            self.assertEqual(capture.call_count, 1)
            self.backend_factory.assert_not_called()

    def test_real_observation_receipt_is_finite_and_private_free(self):
        raw = descriptor(owner=sid(5, (21, 7)), group=sid(5, (21, 987654321)), dacl=acl((ace(mask=2, trustee=sid(5, (21, 987654321))),)))
        data = self.run_probe([ObservationBackend(security=raw), ObservationBackend(security=raw)])
        encoded = wire(data)
        self.assertEqual(module().validate_wire(encoded, SHA, "x64",
                                              expected_python=[3, 12],
                                              expected_windows=[10, 0, 123]), data)
        for private in (HOST.encode(), b"987654321", b"start.exe", b"file_id", b"HANDLE", b"PRIVATE"):
            self.assertNotIn(private, encoded)

    def test_second_resource_failure_first_already_closed(self):
        backends = [ObservationBackend(), ObservationBackend(failure=("security", 1, 1))]
        with self.assertRaises(RuntimeError):
            self.run_probe(backends)
        for backend in backends:
            self.assertEqual(backend.closed, [4, 3, 2, 1])


def enrich_receipt(data):
    # Independent fixture formulas: never reuse production derivation helpers.
    for resource in data["resources"]:
        chain = resource["chain"]
        for i, node in enumerate(chain):
            roles = []
            if i < len(chain) - 1:
                roles.append("route_ancestor")
            if i == 0:
                roles.append("volume_root")
            if i == len(chain) - 2:
                roles.append("image_parent")
            if i == len(chain) - 1:
                roles.append("image_leaf")
            node["structural_roles"] = roles
            node["dacl_protected"] = False
            choices = ([(2, "add_file"), (4, "add_subdirectory"), (0x40, "delete_child")]
                       if node["directory"] else [(2, "write_data"), (4, "append_data")])
            choices += [(0x10, "write_ea"), (0x100, "write_attributes"),
                        (0x10000, "delete_object"), (0x40000, "write_dacl"),
                        (0x80000, "write_owner"), (0x40000000, "generic_write"),
                        (0x10000000, "generic_all")]
            for entry in node["entries"]:
                entry["direct_operation_candidates"] = (
                    [name for bit, name in choices if entry["mutation"] & bit]
                    if entry["allowed"] and not entry["flags"] & 8 else [])
        for i, node in enumerate(chain):
            if i == len(chain) - 1:
                node["inheritance_to_next"] = None
                continue
            child = chain[i + 1]
            bit = 2 if child["directory"] else 1
            indices = [j for j, entry in enumerate(node["entries"]) if entry["flags"] & bit]
            node["inheritance_to_next"] = {
                "next_index": i + 1, "target_kind": "directory" if child["directory"] else "file",
                "child_dacl_protected": False, "flag_candidate_indices": indices,
                "state": "flag_candidates_child_unprotected" if indices else "no_flag_candidates"}
    return data


def validate(value, source, arch):
    return module().validate_wire(value, source, arch,
                                  expected_python=[3, 12], expected_windows=[10, 0, 123])


def receipt():
    node = {"index": 0, "kind": "root", "directory": True, "metadata_observed_equal": True, "descriptor_observed_equal": True, "parser_result": "supported", "policy_result": "pass", "owner": "admin", "entries": [{"allowed": True, "flags": 0, "mutation": 2, "trustee": "admin"}]}
    last = dict(copy.deepcopy(node), index=1, kind="file", directory=False)
    resources = [{"resource": r, "role": "source", "image_sha256": "b" * 64, "chain": copy.deepcopy([node, last]), "owned_handles": 2, "confirmed_closes": 2, "unconfirmed_closes": 0} for r in ("helper", "verifier")]
    data = {"schema_version": 2, "scope": "installed_source_chain_observation", "source_sha": SHA, "architecture": "x64", "python": [3, 12], "windows": [10, 0, 123], "observation_complete": True, "source_policy_all_passed": True, "protected_observed": False, "compatibility_accepted": False, "launch_authorized": False, "resources": resources}
    return enrich_receipt(data)


def wire(data, ending=b"\n"):
    return json.dumps(data, separators=(",", ":")).encode("ascii") + ending


class InstalledWireTests(unittest.TestCase):
    def test_v2_derived_fields_and_edge_exact_types_are_recomputed(self):
        original = receipt()
        try:
            accepted = validate(wire(original), SHA, "x64")
        except ValueError:
            self.fail("validator must accept the complete valid v2 role/control/edge receipt")
        self.assertEqual(accepted, original)
        node_path = ("resources", 0, "chain", 0)
        edge_path = node_path + ("inheritance_to_next",)
        entry_path = node_path + ("entries", 0)
        changes = [(node_path, "structural_roles", value) for value in
                   ([], ["image_leaf"], ["route_ancestor", "volume_root", "image_parent", "image_parent"])]
        changes += [(node_path, "dacl_protected", 0), (node_path, "inheritance_to_next", None)]
        changes += [(edge_path, key, value) for key, value in (
            ("next_index", True), ("next_index", 0), ("target_kind", "directory"),
            ("child_dacl_protected", True), ("child_dacl_protected", 0),
            ("flag_candidate_indices", [True]), ("flag_candidate_indices", [0, 0]),
            ("flag_candidate_indices", [0]), ("state", "flag_candidates_child_protected"))]
        changes += [(entry_path, "direct_operation_candidates", value) for value in
                    ([], ["write_data"], ["add_file", "add_file"], [True])]
        changes.append((edge_path, "PRIVATE", "PRIVATE"))
        for path, key, value in changes:
            data = copy.deepcopy(original)
            obj = data
            for part in path:
                obj = obj[part]
            obj[key] = value
            with self.subTest(path=path, key=key, value=value), self.assertRaises(ValueError):
                validate(wire(data), SHA, "x64")
        for path, key in [(node_path, field) for field in
                          ("structural_roles", "dacl_protected", "inheritance_to_next")] + [(edge_path, "state")]:
            data = copy.deepcopy(original)
            obj = data
            for part in path:
                obj = obj[part]
            del obj[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                validate(wire(data), SHA, "x64")
        self.assertEqual(set(original["resources"][0]["chain"][0]["inheritance_to_next"]),
                         {"next_index", "target_kind", "child_dacl_protected", "flag_candidate_indices", "state"})

    def test_v2_required_runtime_arguments_old_versions_and_wrong_supported_runtime(self):
        original = receipt()
        try:
            accepted = validate(wire(original), SHA, "x64")
        except ValueError:
            self.fail("runtime contract requires an accepted complete v2 positive control first")
        self.assertEqual(accepted, original)
        with self.assertRaises(TypeError):
            module().validate_wire(wire(original), SHA, "x64")
        for python, windows in (([3, 13], [10, 0, 123]), ([3, 12], [10, 0, 124]),
                                ([3, True], [10, 0, 123]), ((3, 12), [10, 0, 123]),
                                ([3, 12], [10, 0, True]), ([3, 12], [10, 0, -1])):
            with self.subTest(python=python, windows=windows), self.assertRaises(ValueError):
                module().validate_wire(wire(original), SHA, "x64",
                                       expected_python=python, expected_windows=windows)
        for version in (0, 1, 3, True, 2.0):
            data = copy.deepcopy(original)
            data["schema_version"] = version
            with self.subTest(version=version), self.assertRaises(ValueError):
                validate(wire(data), SHA, "x64")
        old = copy.deepcopy(original)
        old["schema_version"] = 1
        for resource in old["resources"]:
            for node in resource["chain"]:
                for key in ("structural_roles", "dacl_protected", "inheritance_to_next"):
                    del node[key]
                for entry in node["entries"]:
                    del entry["direct_operation_candidates"]
        with self.assertRaises(ValueError):
            validate(wire(old), SHA, "x64")

    def test_matching_unsupported_python_receipts_are_rejected(self):
        self.assertEqual(validate(wire(receipt()), SHA, "x64"), receipt())
        for minor in (10, 11, 13):
            data = receipt()
            data["python"] = [3, minor]
            with self.subTest(minor=minor), self.assertRaises(ValueError):
                module().validate_wire(wire(data), SHA, "x64",
                                       expected_python=[3, minor], expected_windows=[10, 0, 123])

    def test_byte_limit_inclusive_and_actual_large_wire_refused(self):
        m = module()
        valid = wire(receipt())
        with patch.object(m, "_WIRE_LIMIT", len(valid)):
            self.assertEqual(validate(valid, SHA, "x64"), receipt())
        with patch.object(m, "_WIRE_LIMIT", len(valid) - 1):
            with self.assertRaises(ValueError):
                validate(valid, SHA, "x64")
        self.assertEqual(m._WIRE_LIMIT, 256 * 1024)
        for count in (256 * 1024, 256 * 1024 + 1):
            with self.assertRaises(ValueError):
                validate(b" " * (count - 1) + b"\n", SHA, "x64")

    def test_chain32_33_and_ace512_514_wire_budgets(self):
        for count in (32, 33):
            data = receipt()
            resource = data["resources"][0]
            template = resource["chain"][0]
            resource["chain"] = [dict(copy.deepcopy(template), index=i, kind="root" if i == 0 else "file" if i == count - 1 else "ancestor", directory=i != count - 1) for i in range(count)]
            resource.update(owned_handles=count, confirmed_closes=count)
            enrich_receipt(data)
            if count == 32:
                self.assertEqual(validate(wire(data), SHA, "x64"), data)
            else:
                with self.assertRaises(ValueError):
                    validate(wire(data), SHA, "x64")
        data = receipt()
        entry = data["resources"][0]["chain"][0]["entries"][0]
        for r in data["resources"]:
            for n in r["chain"]:
                n["entries"] = [dict(entry) for _ in range(64)]
        enrich_receipt(data)
        self.assertEqual(validate(wire(data), SHA, "x64"), data)
        data["resources"][1]["chain"][1]["entries"].append(dict(entry))
        with self.assertRaises(ValueError):
            validate(wire(data), SHA, "x64")

    def test_each_boolean_integer_field_rejects_aliases_and_floats(self):
        for path in [("schema_version",), ("source_policy_all_passed",), ("observation_complete",), ("protected_observed",), ("compatibility_accepted",), ("launch_authorized",), ("python", 0), ("python", 1), ("windows", 0), ("windows", 1), ("windows", 2), ("resources", 0, "owned_handles"), ("resources", 0, "confirmed_closes"), ("resources", 0, "unconfirmed_closes"), ("resources", 0, "chain", 0, "index"), ("resources", 0, "chain", 0, "directory"), ("resources", 0, "chain", 0, "metadata_observed_equal"), ("resources", 0, "chain", 0, "descriptor_observed_equal"), ("resources", 0, "chain", 0, "entries", 0, "allowed"), ("resources", 0, "chain", 0, "entries", 0, "flags"), ("resources", 0, "chain", 0, "entries", 0, "mutation")]:
            for value in (True, 1.0, "1", None):
                data = receipt()
                obj = data
                for key in path[:-1]:
                    obj = obj[key]
                if type(obj[path[-1]]) is bool and value is True:
                    value = 1
                obj[path[-1]] = value
                with self.subTest(path=path, value=value):
                    with self.assertRaises(ValueError):
                        validate(wire(data), SHA, "x64")

    def test_nested_duplicates_private_strings_and_nonfinite(self):
        valid = wire(receipt())
        for needle in (b'"role":"source"', b'"index":0', b'"allowed":true'):
            value = valid.replace(needle, needle + b"," + needle, 1)
            with self.assertRaises(ValueError) as raised:
                validate(value, SHA, "x64")
            self.assertEqual(str(raised.exception), "invalid_installed_chain_receipt")
            self.assertTrue(raised.exception.__suppress_context__)
        for value in (b"Infinity", b"-Infinity", b"NaN"):
            with self.assertRaises(ValueError):
                validate(valid.replace(b'"schema_version":2', b'"schema_version":' + value), SHA, "x64")

    def test_canonical_lf_and_crlf_receipts(self):
        for ending in (b"\n", b"\r\n"):
            self.assertEqual(validate(wire(receipt(), ending), SHA, "x64"), receipt())

    def test_invalid_encoding_duplicate_and_noncanonical(self):
        valid = wire(receipt())
        for value in (b"", b"\xff\n", valid + b"\n", valid[:-1], b" " + valid, valid.replace(b'"schema_version":2', b'"schema_version":2,"schema_version":2'), valid.replace(b'"schema_version":2', b'"schema_version":NaN'), valid.replace(b'"schema_version":2', b'"schema_version":2.0'), bytearray(valid)):
            with self.assertRaisesRegex(ValueError, "^invalid_installed_chain_receipt$"):
                validate(value, SHA, "x64")

    def test_every_level_exact_fields_and_types(self):
        original = receipt()
        for target in ((), ("resources", 0), ("resources", 0, "chain", 0), ("resources", 0, "chain", 0, "entries", 0)):
            for change in ("extra", "missing", "wrong_type"):
                data = copy.deepcopy(original)
                obj = data
                for key in target:
                    obj = obj[key]
                if change == "extra":
                    obj["PRIVATE SID"] = "PRIVATE PATH"
                elif change == "missing":
                    obj.pop(next(iter(obj)))
                else:
                    key = next(iter(obj))
                    obj[key] = True if type(obj[key]) is int else 1
                with self.assertRaisesRegex(ValueError, "^invalid_installed_chain_receipt$"):
                    validate(wire(data), SHA, "x64")

    def test_semantic_negative_matrix_and_expected_arguments(self):
        for path, value in [(("schema_version",), 3), (("launch_authorized",), True), (("windows",), [10, 0, -1]), (("python",), [3, 10]), (("resources", 0, "resource"), "verifier"), (("resources", 0, "role"), "protected"), (("resources", 0, "image_sha256"), "A" * 64), (("resources", 0, "confirmed_closes"), 1), (("resources", 0, "chain", 0, "index"), 1), (("resources", 0, "chain", 0, "kind"), "file"), (("resources", 0, "chain", 0, "owner"), HOST), (("resources", 0, "chain", 0, "entries", 0, "flags"), 32), (("resources", 0, "chain", 0, "entries", 0, "mutation"), 8), (("resources", 0, "chain", 1, "directory"), True)]:
            data = receipt()
            obj = data
            for key in path[:-1]:
                obj = obj[key]
            obj[path[-1]] = value
            with self.assertRaises(ValueError):
                validate(wire(data), SHA, "x64")
        for source, arch in (("b" * 40, "x64"), (SHA, "arm64"), (SHA.upper(), "x64"), (SHA, "PRIVATE"), (True, "x64")):
            with self.assertRaises(ValueError):
                validate(wire(receipt()), source, arch)

    def test_policy_and_all_passed_are_recomputed(self):
        for owner, entries, result in (("other", [], "owner_untrusted"), ("admin", [], "empty_dacl"), ("host", [{"allowed": True, "flags": 8, "mutation": 2, "trustee": "everyone"}], "mutation_untrusted")):
            data = receipt()
            node = data["resources"][0]["chain"][0]
            node.update(owner=owner, entries=entries)
            enrich_receipt(data)
            with self.assertRaises(ValueError):
                validate(wire(data), SHA, "x64")
            node["policy_result"] = result
            data["source_policy_all_passed"] = False
            self.assertEqual(validate(wire(data), SHA, "x64"), data)


class InstalledCliTests(unittest.TestCase):
    def test_normal_help_and_parse_error_stay_outside_runtime_handler(self):
        for args, code in ((["--help"], 0), ([], 2), (["--path", "PRIVATE"], 2)):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err), patch.object(module(), "probe") as probe:
                with self.assertRaises(SystemExit) as raised:
                    module().main(args)
                self.assertEqual(raised.exception.code, code)
                probe.assert_not_called()

    def test_validation_and_output_budget_fail_without_success_output(self):
        for change in ("invalid", "budget"):
            data = receipt()
            if change == "invalid":
                data["launch_authorized"] = True
            else:
                data["PRIVATE"] = "x" * (256 * 1024)
            out, err = io.StringIO(), io.StringIO()
            with patch.object(module(), "probe", return_value=data), redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(module().main(["--source-sha", SHA]), 1)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(err.getvalue(), "windows_installed_chain_observation_failed\n")

    def test_one_safe_json_success_after_validation(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(module(), "probe", return_value=receipt()), \
             patch.object(module().sys, "version_info", SimpleNamespace(major=3, minor=12)), \
             redirect_stdout(out), redirect_stderr(err):
            code = module().main(["--source-sha", SHA])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().encode(), wire(receipt()))
        self.assertEqual(err.getvalue(), "")

    def test_private_hostile_exception_and_cause_never_printed(self):
        class Hostile(RuntimeError):
            def __str__(self):
                raise AssertionError("PRIVATE str")
        for exc, expected in ((Hostile("PRIVATE"), 1), (KeyboardInterrupt("PRIVATE"), 130), (SystemExit("PRIVATE"), 1)):
            exc.__cause__ = RuntimeError("PRIVATE cause")
            out, err = io.StringIO(), io.StringIO()
            with patch.object(module(), "probe", side_effect=exc), redirect_stdout(out), redirect_stderr(err):
                code = module().main(["--source-sha", SHA])
            self.assertEqual(code, expected)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(err.getvalue(), "windows_installed_chain_observation_failed\n")
