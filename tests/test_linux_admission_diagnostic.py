"""Independent format and current-host checks for the diagnostic-only codec."""

from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import icode.linux_admission_diagnostic as d


def report(reason="observation_incomplete", **changes):
    fields = dict(scope="linux_admission_diagnostic", schema_version=1,
                  platform="linux", os_build="release version", architecture="x86_64",
                  helper_sha256="a" * 64, policy_schema_version=1,
                  checked_at="2026-10-12T01:02:03Z", status="incomplete", reason=reason,
                  observations=d.LinuxDiagnosticObservations(True, False),
                  observation_coverage="legacy_probe_summary_only", cleanup_status="unknown")
    fields.update(changes)
    return d.LinuxAdmissionDiagnostic(**fields)


class CodecTests(unittest.TestCase):
    def test_five_combinations_and_immutable(self):
        cases = [report(), report("invalid_observation", observations=d.LinuxDiagnosticObservations(None, False)),
                 report("helper_unavailable", helper_sha256=None, observations=d.LinuxDiagnosticObservations(None, None)),
                 report("helper_changed", helper_sha256=None, observations=d.LinuxDiagnosticObservations(None, None)),
                 report("unsupported_environment", os_build=None, helper_sha256=None, observations=d.LinuxDiagnosticObservations(None, None))]
        for item in cases:
            restored = d.validate_linux_admission_diagnostic(d.serialize_linux_admission_diagnostic(item))
            self.assertEqual(item, restored)
            self.assertIs(type(restored), d.LinuxAdmissionDiagnostic)
            self.assertIs(type(restored.observations), d.LinuxDiagnosticObservations)
            with self.assertRaises(FrozenInstanceError):
                restored.observations.minimal_probe = False

    def test_canonical_and_duplicate_keys(self):
        wire = d.serialize_linux_admission_diagnostic(report())
        self.assertTrue(wire.endswith(b"\n"))
        for bad in [wire[:-1], wire + b"\n", b" " + wire,
                    wire.replace(b'"scope":', b'"scope":"linux_admission_diagnostic","scope":'),
                    wire.replace(b'"minimal_probe":true', b'"minimal_probe":true,"minimal_probe":true')]:
            with self.assertRaisesRegex(ValueError, "^invalid_linux_admission_diagnostic$"):
                d.validate_linux_admission_diagnostic(bad)

    def test_independent_oversize_canonical(self):
        item = report()
        wire = d.serialize_linux_admission_diagnostic(item)
        with patch.object(d, "MAX_DIAGNOSTIC_BYTES", len(wire) - 1):
            with self.assertRaisesRegex(ValueError, "^invalid_linux_admission_diagnostic$"):
                d.serialize_linux_admission_diagnostic(item)
            with self.assertRaisesRegex(ValueError, "^invalid_linux_admission_diagnostic$"):
                d.validate_linux_admission_diagnostic(wire)

    def test_types_enums_calendar_and_legacy_dict(self):
        class String(str):
            pass
        for key, value in [("schema_version", True), ("policy_schema_version", 0), ("policy_schema_version", True),
                           ("scope", String("linux_admission_diagnostic")), ("status", "ready"),
                           ("checked_at", "2026-02-30T01:02:03Z"), ("os_build", "\n"),
                           ("architecture", "aarch64"), ("helper_sha256", "A" * 64),
                           ("observations", {"minimal_probe": True, "protected_path_probe": False})]:
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "^invalid_linux_admission_diagnostic$"):
                d.serialize_linux_admission_diagnostic(replace(report(), **{key: value}))
        wire = d.serialize_linux_admission_diagnostic(report())
        for bad in [bytearray(wire), {}, wire.decode()]:
            with self.assertRaises(ValueError):
                d.validate_linux_admission_diagnostic(bad)

    def test_reason_requires_exact_partial_observations(self):
        for item in [report("invalid_observation"), report(observations=d.LinuxDiagnosticObservations(None, False)),
                     report("helper_changed"), report(observations=d.LinuxDiagnosticObservations(1, False))]:
            with self.assertRaises(ValueError):
                d.serialize_linux_admission_diagnostic(item)

    def test_extra_missing_keys_ascii_and_strict_subclasses(self):
        wire = d.serialize_linux_admission_diagnostic(report())
        for nested in (False, True):
            for extra in (False, True):
                altered = json.loads(wire)
                target = altered["observations"] if nested else altered
                if extra:
                    target["private_metadata"] = "private"
                else:
                    target.pop("minimal_probe" if nested else "scope")
                bad = (json.dumps(altered, sort_keys=True, separators=(",", ":")) + "\n").encode()
                with self.subTest(nested=nested, extra=extra), self.assertRaises(ValueError):
                    d.validate_linux_admission_diagnostic(bad)
        class Integer(int):
            pass
        class Bytes(bytes):
            pass
        for field in ("schema_version", "policy_schema_version"):
            with self.assertRaises(ValueError):
                d.serialize_linux_admission_diagnostic(replace(report(), **{field: Integer(1)}))
        for bad in (Bytes(wire), wire.replace(b"release version", b"\xff"), b""):
            with self.assertRaises(ValueError):
                d.validate_linux_admission_diagnostic(bad)


class HostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.helper = Path(self.tmp.name) / "icode-landlock"
        self.manifest = self.helper.parent / "icode-landlock.sha256"
        self.write_helper(b"actual-helper-A")
        for target, kwargs in [
            ("sys.platform", {"new": "linux"}),
            ("platform.release", {"return_value": "release"}),
            ("platform.version", {"return_value": "version"}),
            ("platform.machine", {"return_value": "x86_64"}),
            ("native_helper.bundled_linux_helper", {"return_value": self.helper}),
            ("isolation.probe_native_sandbox", {"return_value": SimpleNamespace(ready=True)}),
            ("isolation.probe_linux_protected_paths", {"return_value": SimpleNamespace(passed=False)}),
            ("sandbox_policy.POLICY_SCHEMA_VERSION", {"new": 1})]:
            mock = self.enterContext(patch("icode.linux_admission_diagnostic." + target, **kwargs))
            setattr(self, target.rsplit(".", 1)[-1], mock)

    def write_helper(self, body):
        self.helper.write_bytes(body)
        self.helper.chmod(0o755)
        self.manifest.write_text(hashlib.sha256(body).hexdigest() + "\n", encoding="ascii")

    def test_actual_digest_all_boolean_combinations_remain_incomplete(self):
        for first in (True, False):
            for second in (True, False):
                self.probe_native_sandbox.return_value = SimpleNamespace(ready=first)
                self.probe_linux_protected_paths.return_value = SimpleNamespace(passed=second)
                result = d.collect_linux_admission_diagnostic()
                self.assertEqual(result.helper_sha256, hashlib.sha256(self.helper.read_bytes()).hexdigest())
                self.assertEqual(result.observations, d.LinuxDiagnosticObservations(first, second))
                self.assertEqual((result.status, result.reason, result.cleanup_status), ("incomplete", "observation_incomplete", "unknown"))
                self.assertTrue(d.linux_diagnostic_binding_current(result))

    def test_nonlinux_unsupported_and_missing_never_probe(self):
        with patch.object(d.sys, "platform", "darwin"), self.assertRaisesRegex(ValueError, "^linux_admission_unavailable$"):
            d.collect_linux_admission_diagnostic()
        self.machine.return_value = "unknown"
        self.assertEqual(d.collect_linux_admission_diagnostic().reason, "unsupported_environment")
        self.machine.return_value = "x86_64"
        self.helper.unlink()
        self.assertEqual(d.collect_linux_admission_diagnostic().reason, "helper_unavailable")
        self.probe_native_sandbox.assert_not_called()
        self.probe_linux_protected_paths.assert_not_called()

    def test_helper_changed_or_disappeared_clears_summaries(self):
        for disappeared in (False, True):
            self.write_helper(b"actual-helper-A")
            def mutate(_sandbox):
                if disappeared:
                    self.helper.unlink()
                else:
                    self.write_helper(b"actual-helper-B")
                return SimpleNamespace(passed=True)
            self.probe_linux_protected_paths.side_effect = mutate
            result = d.collect_linux_admission_diagnostic()
            self.assertEqual(result.reason, "helper_changed")
            self.assertIsNone(result.helper_sha256)
            self.assertEqual(result.observations, d.LinuxDiagnosticObservations(None, None))
            self.assertFalse(d.linux_diagnostic_binding_current(result))

    def test_first_exception_stops_second_but_rehashes_sanitized(self):
        def fail(_sandbox):
            self.write_helper(b"actual-helper-B")
            raise RuntimeError("private-body")
        self.probe_native_sandbox.side_effect = fail
        result = d.collect_linux_admission_diagnostic()
        self.assertEqual(result.reason, "helper_changed")
        self.probe_linux_protected_paths.assert_not_called()
        self.assertNotIn(b"private-body", d.serialize_linux_admission_diagnostic(result))

    def test_invalid_summaries_and_second_exception_preserve_partial(self):
        for value in (1, "true", None):
            self.probe_native_sandbox.return_value = SimpleNamespace(ready=value)
            result = d.collect_linux_admission_diagnostic()
            self.assertEqual(result.reason, "invalid_observation")
            self.assertEqual(result.observations, d.LinuxDiagnosticObservations(None, False))
        self.probe_native_sandbox.return_value = SimpleNamespace(ready=True)
        self.probe_linux_protected_paths.side_effect = RuntimeError("private")
        self.assertEqual(d.collect_linux_admission_diagnostic().observations, d.LinuxDiagnosticObservations(True, None))

    def test_binding_platform_host_helper_policy_and_read_errors(self):
        result = d.collect_linux_admission_diagnostic()
        for target, kwargs in [("sys.platform", {"new": "darwin"}), ("platform.release", {"return_value": "changed"}),
                               ("platform.machine", {"return_value": "arm64"}), ("sandbox_policy.POLICY_SCHEMA_VERSION", {"new": 2}),
                               ("native_helper.bundled_linux_helper", {"side_effect": OSError("private")})]:
            with patch("icode.linux_admission_diagnostic." + target, **kwargs):
                self.assertFalse(d.linux_diagnostic_binding_current(result))
        self.write_helper(b"actual-helper-B")
        self.assertFalse(d.linux_diagnostic_binding_current(result))
        self.assertFalse(d.linux_diagnostic_binding_current({}))

    def test_host_drift_clears_identity(self):
        self.release.side_effect = ["release", "changed"]
        result = d.collect_linux_admission_diagnostic()
        self.assertEqual(result.reason, "unsupported_environment")
        self.assertIsNone(result.os_build)
        self.assertIsNone(result.helper_sha256)
        self.assertEqual(result.observations, d.LinuxDiagnosticObservations(None, None))

    def test_interrupt_objects_propagate_from_probe_and_binding(self):
        result = d.collect_linux_admission_diagnostic()
        for exception in (KeyboardInterrupt("same"), SystemExit("same")):
            self.probe_native_sandbox.side_effect = exception
            with self.assertRaises(type(exception)) as caught:
                d.collect_linux_admission_diagnostic()
            self.assertIs(caught.exception, exception)
            with patch.object(d.native_helper, "bundled_linux_helper", side_effect=exception):
                with self.assertRaises(type(exception)) as caught:
                    d.linux_diagnostic_binding_current(result)
                self.assertIs(caught.exception, exception)

    def test_arm_aliases_invalid_host_and_initial_policy(self):
        for alias in ("aarch64", "arm64", "ARM64"):
            self.machine.return_value = alias
            self.assertEqual(d.collect_linux_admission_diagnostic().architecture, "arm64")
        self.release.return_value = "\n"
        self.assertIsNone(d.collect_linux_admission_diagnostic().os_build)
        for value in (True, 0):
            with patch.object(d.sandbox_policy, "POLICY_SCHEMA_VERSION", value), self.assertRaisesRegex(ValueError, "^linux_admission_unavailable$"):
                d.collect_linux_admission_diagnostic()

    def test_policy_gate_precedes_all_eighteen_drift_combinations(self):
        for policy in (True, 2, 0):
            for helper in ("changed", "missing", "stable"):
                for host_changed in (False, True):
                    with self.subTest(policy=policy, helper=helper, host_changed=host_changed):
                        self.write_helper(b"actual-helper-A")
                        self.release.return_value = "release"
                        def mutate(_sandbox):
                            d.sandbox_policy.POLICY_SCHEMA_VERSION = policy
                            if helper == "changed":
                                self.write_helper(b"actual-helper-B")
                            elif helper == "missing":
                                self.helper.unlink()
                            if host_changed:
                                self.release.return_value = "changed"
                            return SimpleNamespace(passed=True)
                        self.probe_linux_protected_paths.side_effect = mutate
                        with patch.object(d.sandbox_policy, "POLICY_SCHEMA_VERSION", 1), self.assertRaisesRegex(ValueError, "^linux_admission_unavailable$"):
                            d.collect_linux_admission_diagnostic()

    def test_real_result_objects_only_export_summaries_and_use_fixed_sandbox(self):
        self.probe_native_sandbox.return_value = d.isolation.NativeProbeResult(True, {"private": False}, "private-detail")
        self.probe_linux_protected_paths.return_value = d.isolation.LinuxProtectedPathProbeResult(False, True, {"private": False}, "private-detail")
        result = d.collect_linux_admission_diagnostic()
        self.assertEqual(result.observations, d.LinuxDiagnosticObservations(True, True))
        sandbox = self.probe_native_sandbox.call_args.args[0]
        self.assertIs(type(sandbox), d.isolation.LandlockSandbox)
        self.assertEqual(sandbox.helper, str(self.helper))
        self.assertEqual(sandbox.manifest, str(self.manifest))
        self.assertIs(self.probe_linux_protected_paths.call_args.args[0], sandbox)
        self.assertNotIn(b"private", d.serialize_linux_admission_diagnostic(result))
        self.probe_native_sandbox.reset_mock()
        self.probe_linux_protected_paths.reset_mock()
        self.assertTrue(d.linux_diagnostic_binding_current(result))
        self.probe_native_sandbox.assert_not_called()
        self.probe_linux_protected_paths.assert_not_called()

    def test_old_dict_summary_and_first_error_stop_second_in_actual_collector(self):
        for response in ({"ready": True}, RuntimeError("private-error")):
            self.probe_linux_protected_paths.reset_mock()
            if isinstance(response, Exception):
                self.probe_native_sandbox.side_effect = response
            else:
                self.probe_native_sandbox.return_value = response
            result = d.collect_linux_admission_diagnostic()
            self.assertEqual(result.reason, "invalid_observation")
            self.assertEqual(result.observations, d.LinuxDiagnosticObservations(None, None))
            self.probe_linux_protected_paths.assert_not_called()
            self.assertNotIn(b"private", d.serialize_linux_admission_diagnostic(result))

    def test_real_helper_verification_rejects_bad_manifest_links_and_digest(self):
        for body in ("b" * 64 + "\n", "not-a-hash\n", "a" * 64 + "\n\n", "\u00ff"):
            self.manifest.write_text(body)
            self.assertEqual(d.collect_linux_admission_diagnostic().reason, "helper_unavailable")
        self.write_helper(b"actual-helper-A")
        original = self.helper.parent / "original"
        self.helper.rename(original)
        self.helper.symlink_to(original)
        self.assertEqual(d.collect_linux_admission_diagnostic().reason, "helper_unavailable")
        self.probe_native_sandbox.assert_not_called()
        self.probe_linux_protected_paths.assert_not_called()

    def test_ordinary_host_errors_and_aliases_are_sanitized(self):
        for alias in ("amd64", "AMD64", "x86_64"):
            self.machine.return_value = alias
            self.assertEqual(d.collect_linux_admission_diagnostic().architecture, "x86_64")
        for invalid in ("\n", "\u00ff", "a" * 256):
            self.release.return_value = invalid
            self.assertEqual(d.collect_linux_admission_diagnostic().reason, "unsupported_environment")
        self.release.side_effect = RuntimeError("private")
        result = d.collect_linux_admission_diagnostic()
        self.assertIsNone(result.os_build)
        self.assertNotIn(b"private", d.serialize_linux_admission_diagnostic(result))

    def test_interrupt_identity_from_host_helper_and_second_probe(self):
        for exception in (KeyboardInterrupt("same"), SystemExit("same")):
            for target in ("platform.release", "native_helper.verify_native_helper", "isolation.probe_linux_protected_paths"):
                with patch("icode.linux_admission_diagnostic." + target, side_effect=exception):
                    with self.assertRaises(type(exception)) as caught:
                        d.collect_linux_admission_diagnostic()
                    self.assertIs(caught.exception, exception)

    def test_binding_rejects_partial_malformed_and_policy_types(self):
        result = d.collect_linux_admission_diagnostic()
        for value in (True, 0):
            with patch.object(d.sandbox_policy, "POLICY_SCHEMA_VERSION", value):
                self.assertFalse(d.linux_diagnostic_binding_current(result))
        for value in (replace(result, status="ready"), replace(result, observations={}),
                      replace(result, reason="invalid_observation", observations=d.LinuxDiagnosticObservations(True, None))):
            self.assertFalse(d.linux_diagnostic_binding_current(value))

    def test_clock_failures_are_fixed_and_interrupt_identity_is_preserved(self):
        for stage in ("now", "strftime"):
            for exception in (RuntimeError("private-clock"), KeyboardInterrupt("same"), SystemExit("same")):
                with self.subTest(stage=stage, exception=type(exception).__name__):
                    with patch.object(d, "datetime") as clock, patch.object(d, "_host_identity") as host:
                        if stage == "now":
                            clock.now.side_effect = exception
                        else:
                            clock.now.return_value.strftime.side_effect = exception
                        if isinstance(exception, Exception):
                            # Capture the old RuntimeError too, so RED is an assertion failure.
                            with self.assertRaises(Exception) as caught:
                                d.collect_linux_admission_diagnostic()
                            self.assertIs(type(caught.exception), ValueError)
                            self.assertEqual(str(caught.exception), "linux_admission_unavailable")
                            self.assertIsNone(caught.exception.__cause__)
                            self.assertTrue(caught.exception.__suppress_context__)
                        else:
                            with self.assertRaises(type(exception)) as caught:
                                d.collect_linux_admission_diagnostic()
                            self.assertIs(caught.exception, exception)
                        host.assert_not_called()
                        self.bundled_linux_helper.assert_not_called()
                        self.probe_native_sandbox.assert_not_called()
                        self.probe_linux_protected_paths.assert_not_called()
