"""Pure software loopback policy; no Windows APIs or mutation adapters."""
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
import importlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = "icode.windows_positive_loopback_policy"
try:
    core = importlib.import_module(MODULE)
except ModuleNotFoundError as exc:
    if exc.name != MODULE:
        raise
    core = None


def fields():
    return dict(admission=core.AdmissionFacts(True, True, True, True, True),
                repository="ayukyo/icode", source_sha="a" * 40, run_id="123",
                run_attempt=1, job="windows-reviewer-snapshot-probe", matrix="x64",
                account_sid="S-1-5-21-1-2-3-1001", pid=1234, process_created=5678,
                positive_profile="icode-" + "1" * 32,
                reviewer_profile="icode-" + "2" * 32,
                positive_sid="S-1-15-2-1-2-3-4-5-6-7",
                reviewer_sid="S-1-15-2-8-9-10-11-12-13-14",
                nonce="3" * 32, ipv4_port=12345, ipv6_port=23456,
                started_ms=1000, deadline_ms=61000)



def full_snapshot(entries, **options):
    # Explicit complete model facts; these are not OS observations.
    return core.Snapshot(entries, **{
        **dict(api_code=0, complete=True, released=True, reaped=True), **options})


class TestPositiveLoopbackPolicy(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(core, "new software policy core is absent; not an OS bug")
        self.m = core.Manifest(**fields())
        self.foreign = ("S-1-15-2-99", 0x80000004)
        self.b = full_snapshot((self.foreign,))
        self.a = full_snapshot((self.foreign, (self.m.positive_sid, 4)))
        self.ok = core.CommandResult(0, False, True)

    def begin(self):
        return core.begin(self.m, self.b, self.b, 1000)

    def intent(self):
        state = core.profile_created(self.begin(), self.m.positive_profile,
                                     self.m.positive_sid, 0, 1001)
        return core.add_intent(state, 1002)

    def added(self):
        return core.add_observed(self.intent(), self.a, self.ok, 1003)

    def successful(self):
        payload = json.dumps(dict(nonce=self.m.nonce, appcontainer=True,
            package_sid=self.m.positive_sid, capability_count=1,
            capability_sid="S-1-15-3-3"), sort_keys=True,
            separators=(",", ":")).encode("ascii")
        state = core.probe_observed(self.added(), (payload,), (payload,),
                                    True, True, 0, 1004)
        plan = core.cleanup_plan(state, self.a, True, 1005)
        self.assertEqual(plan.action, "delete")
        return core.cleanup_complete(plan, self.b, self.ok, 1006)

    def test_manifest_complete_binding_and_immutability(self):
        self.assertEqual(self.m.source_sha, "a" * 40)
        for index in range(5):
            for invalid in (False, 1, None):
                flags = [True] * 5
                flags[index] = invalid
                with self.subTest(index=index, value=invalid), self.assertRaises(core.PolicyError):
                    core.AdmissionFacts(*flags)
        with self.assertRaises(FrozenInstanceError):
            self.m.pid = 1
        for key in fields():
            changed = fields()
            changed[key] = None
            with self.subTest(key=key), self.assertRaises(core.PolicyError):
                core.Manifest(**changed)

    def test_manifest_rejects_cross_identity_and_invalid_scalars(self):
        cases = (("positive_sid", self.m.reviewer_sid),
                 ("positive_profile", self.m.reviewer_profile),
                 ("run_attempt", True), ("pid", False), ("process_created", -1),
                 ("ipv4_port", True), ("ipv6_port", 65536),
                 ("source_sha", "A" * 40), ("nonce", "x" * 32),
                 ("matrix", "arm"), ("deadline_ms", 61001),
                 ("started_ms", 61000), ("repository", "../other"))
        for key, value in cases:
            with self.subTest(key=key), self.assertRaises(core.PolicyError):
                core.Manifest(**dict(fields(), **{key: value}))

    def test_request_real_roundtrip_and_exact_correlation(self):
        wire = core.encode_request(self.m, "profile_created")
        self.assertLessEqual(len(wire), 4096)
        self.assertEqual(core.validate_request(wire, self.m, "profile_created", 1001),
                         "profile_created")
        body = json.loads(wire)
        for key in body:
            other = dict(body)
            other[key] = None
            with self.subTest(key=key), self.assertRaises(core.PolicyError):
                core.validate_request(json.dumps(other).encode(), self.m,
                                      "profile_created", 1001)
        for kind in ("probe_finished", "arbitrary_command"):
            with self.assertRaises(core.PolicyError):
                core.validate_request(wire, self.m, kind, 1001)

    def test_request_duplicates_limits_types_utf8_and_deadline(self):
        wire = core.encode_request(self.m, "probe_finished")
        for bad in (wire[:-1] + b',"version":1}', b"[]", b"\xff",
                    b" " * 4097, b'{"version":NaN}', wire + b"{}"):
            with self.subTest(bad=bad[:30]), self.assertRaises(core.PolicyError):
                core.validate_request(bad, self.m, "probe_finished", 1001)
        body = json.loads(wire)
        body["pid"] = True
        with self.assertRaises(core.PolicyError):
            core.validate_request(json.dumps(body).encode(), self.m,
                                  "probe_finished", 1001)
        for now in (True, 999, 61000, 61001):
            with self.assertRaises(core.PolicyError):
                core.validate_request(wire, self.m, "probe_finished", now)

    def test_snapshot_binary_identity_attributes_and_order(self):
        other = ("S-1-5-18", 0xFFFFFFFF)
        left = full_snapshot((self.foreign, other))
        right = full_snapshot((other, self.foreign))
        self.assertEqual(left, right)
        self.assertEqual(left.digest, right.digest)
        self.assertNotEqual(left, full_snapshot((other, (self.foreign[0], 0))))
        self.assertEqual(core.sid_bytes("S-1-5-18"),
                         b"\x01\x01\x00\x00\x00\x00\x00\x05\x12\x00\x00\x00")

    def test_snapshot_invalid_sids_duplicates_and_attribute_types(self):
        cases = ((("S-1-15-2-01", 0),), (("S-2-5-18", 0),),
                 (("S-1-281474976710656-1", 0),), (("S-1-5-4294967296", 0),),
                 (("S-1-5", 0),), ((self.foreign[0], True),),
                 ((self.foreign[0], -1),), ((self.foreign[0], 1 << 32),),
                 (self.foreign, self.foreign), [self.foreign],
                 ((self.foreign[0], 0, 1),))
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(core.PolicyError):
                full_snapshot(entries)

    def test_snapshot_complete_limit_and_api_release_reap_are_required(self):
        entries = tuple((f"S-1-15-2-{i}", i) for i in range(4096))
        self.assertEqual(len(full_snapshot(entries).entries), 4096)
        with self.assertRaises(core.PolicyError):
            full_snapshot(entries + (("S-1-15-2-5000", 0),))
        for options in (dict(api_code=5), dict(api_code=False),
                        dict(complete=False), dict(released=False),
                        dict(reaped=False), dict(complete=1)):
            with self.subTest(options=options), self.assertRaises(core.PolicyError):
                full_snapshot((self.foreign,), **options)

    def test_begin_requires_stable_absent_two_target_snapshot(self):
        self.assertEqual(self.begin().phase, "baseline")
        for other in (self.a, full_snapshot((self.foreign, (self.m.reviewer_sid, 0))),
                      full_snapshot(())):
            with self.subTest(other=other), self.assertRaises(core.PolicyError):
                core.begin(self.m, other, other if other == self.a else self.b, 1000)
        with self.assertRaises(core.PolicyError):
            core.begin(self.m, self.b, self.b, 61000)

    def test_profile_creation_requires_exact_owned_success(self):
        for args in ((self.m.reviewer_profile, self.m.positive_sid, 0),
                     (self.m.positive_profile, self.m.reviewer_sid, 0),
                     (self.m.positive_profile, self.m.positive_sid, 1),
                     (self.m.positive_profile, self.m.positive_sid, False)):
            with self.subTest(args=args), self.assertRaises(core.PolicyError):
                core.profile_created(self.begin(), *args, 1001)
        with self.assertRaises(core.PolicyError):
            core.add_intent(self.begin(), 1001)

    def test_intent_one_shot_and_deadline_cannot_be_replayed(self):
        intent = self.intent()
        self.assertEqual(intent.phase, "add_intent")
        with self.assertRaises(core.PolicyError):
            core.add_intent(intent, 1003)
        with self.assertRaises(core.PolicyError):
            core.profile_created(intent, self.m.positive_profile,
                                 self.m.positive_sid, 0, 1003)
        with self.assertRaises(core.PolicyError):
            core.add_intent(core.profile_created(self.begin(), self.m.positive_profile,
                            self.m.positive_sid, 0, 1001), 61000)
        with self.assertRaises(core.PolicyError):
            core.cleanup_plan(self.begin(), self.b, True, 1002)
        with self.assertRaises(core.PolicyError):
            core.cleanup_plan(core.fail(self.begin(), "observation_failed"),
                              self.a, True, 1003)

    def test_add_exact_delta_no_foreign_or_reviewer_change(self):
        state = self.added()
        self.assertEqual((state.phase, state.target_attributes), ("added", 4))
        for snapshot in (self.b, full_snapshot(((self.foreign[0], 0),
                             (self.m.positive_sid, 4))),
                         full_snapshot(self.a.entries + ((self.m.reviewer_sid, 0),))):
            result = core.add_observed(self.intent(), snapshot, self.ok, 1003)
            self.assertEqual(result.phase, "unknown")
            self.assertIsNotNone(result.first_error)

    def test_add_error_timeout_late_and_unreaped_do_not_grant_success(self):
        for command in (core.CommandResult(5, False, True),
                        core.CommandResult(None, True, True),
                        core.CommandResult(None, True, False)):
            state = core.add_observed(self.intent(), self.a, command, 1003)
            self.assertEqual(state.phase, "unknown")
            self.assertEqual(state.target_attributes, 4)
        late = core.add_observed(self.intent(), self.a, self.ok, 61000)
        self.assertEqual((late.phase, late.first_error), ("unknown", "deadline"))
        for args in ((False, False, True), (0, 0, True), (None, False, True)):
            with self.assertRaises(core.PolicyError):
                core.CommandResult(*args)

    def test_probe_requires_actual_complete_dual_payload_and_verified_token(self):
        payload = core.probe_payload(self.m)
        for args in (((payload,), (), True, True, 0),
                     ((payload, payload), (payload,), True, True, 0),
                     ((b"wrong",), (payload,), True, True, 0),
                     ((payload,), (payload,), False, True, 0),
                     ((payload,), (payload,), True, False, 0),
                     ((payload,), (payload,), True, True, 105)):
            state = core.probe_observed(self.added(), *args, 1004)
            self.assertEqual(state.phase, "unknown")
            self.assertFalse(state.both_nonce_received)
        self.assertEqual(self.successful().phase, "restored")
        late = core.probe_observed(self.added(), (payload,), (payload,),
                                   True, True, 0, 61000)
        self.assertEqual((late.phase, late.first_error), ("unknown", "deadline"))

    def test_cleanup_current_map_preserves_foreign_deltas_without_rollback(self):
        foreign_delta = ("S-1-5-19", 128)
        changed = full_snapshot(self.a.entries + (foreign_delta,))
        plan = core.cleanup_plan(self.added(), changed, True, 1005)
        self.assertEqual(plan.action, "delete")
        post = full_snapshot(self.b.entries + (foreign_delta,))
        result = core.cleanup_complete(plan, post, self.ok, 1006)
        self.assertTrue(result.modeled_restoration)
        self.assertEqual(result.first_error, "foreign_delta")
        receipt = json.loads(core.encode_receipt(result, 1007))
        self.assertEqual(receipt["status"], "unknown")

    def test_cleanup_absence_is_idempotent_and_ambiguous_owner_refuses(self):
        absent = core.cleanup_plan(self.added(), self.b, True, 1005)
        self.assertEqual(absent.action, "absent")
        done = core.cleanup_complete(absent, self.b, None, 1006)
        self.assertTrue(done.modeled_restoration)
        for current, reaped in ((full_snapshot((self.foreign,
                             (self.m.positive_sid, 8))), True), (self.a, False)):
            plan = core.cleanup_plan(self.added(), current, reaped, 1005)
            self.assertEqual(plan.action, "refuse")
            result = core.cleanup_complete(plan, self.b, self.ok, 1006)
            self.assertFalse(result.modeled_restoration)

    def test_cleanup_unknown_add_intent_and_error_keep_first_result(self):
        failed = core.fail(self.intent(), "add_failed")
        repeated = core.fail(failed, "cleanup_failed")
        self.assertEqual(repeated.first_error, "add_failed")
        plan = core.cleanup_plan(failed, self.a, True, 1005)
        self.assertEqual(plan.action, "delete")
        done = core.cleanup_complete(plan, self.b, self.ok, 1006)
        self.assertEqual(done.first_error, "add_failed")
        self.assertTrue(done.modeled_restoration)
        self.assertEqual(json.loads(core.encode_receipt(done, 1007))["status"], "unknown")
        with self.assertRaises(core.PolicyError):
            core.fail(self.intent(), "arbitrary stage/private contents")

    def test_cleanup_failure_or_bad_post_never_claims_restore(self):
        plan = core.cleanup_plan(self.added(), self.a, True, 1005)
        for post, command in ((self.a, self.ok),
                              (full_snapshot(()), self.ok),
                              (self.b, core.CommandResult(5, False, True)),
                              (self.b, core.CommandResult(None, True, False))):
            done = core.cleanup_complete(plan, post, command, 1006)
            self.assertFalse(done.modeled_restoration)
            self.assertEqual(json.loads(core.encode_receipt(done, 1007))["status"],
                             "unknown")
        late_plan = core.cleanup_plan(self.added(), self.a, True, 61000)
        late = core.cleanup_complete(late_plan, self.b, self.ok, 61001)
        self.assertTrue(late.modeled_restoration)
        self.assertEqual(late.first_error, "deadline")
        self.assertEqual(json.loads(core.encode_receipt(late, 61002))["status"], "unknown")
        with self.assertRaises(core.PolicyError):
            core.cleanup_plan(self.successful(), self.b, True, 1008)

    def test_receipt_budget_privacy_native_false_and_late_result(self):
        done = self.successful()
        for state, now, status in ((done, 1007, "modeled"),
                                  (done, 61000, "unknown"),
                                  (self.intent(), 1007, "unknown")):
            wire = core.encode_receipt(state, now)
            self.assertLessEqual(len(wire), 500)
            receipt = json.loads(wire)
            self.assertEqual(receipt["status"], status)
            self.assertIs(receipt["native_authorized"], False)
            self.assertIsNone(receipt["native_restoration_verified"])
            self.assertNotIn(self.m.positive_sid.encode(), wire)
            self.assertNotIn(self.foreign[0].encode(), wire)
            self.assertEqual(wire, json.dumps(receipt, sort_keys=True,
                separators=(",", ":"), ensure_ascii=True).encode("ascii"))

    def test_core_is_pure_and_canonical_types_are_not_duck_typed(self):
        tree = ast.parse(Path(core.__file__).read_text(encoding="utf-8"))
        forbidden = {"os", "sys", "ctypes", "subprocess", "socket", "pathlib", "time"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse({item.name.split(".")[0] for item in node.names}
                                 & forbidden)
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)
        class ForeignManifest:
            pass
        for bad in (ForeignManifest(), dict(fields())):
            with self.assertRaises(core.PolicyError):
                core.begin(bad, self.b, self.b, 1000)
        with self.assertRaises(core.PolicyError):
            core.begin(self.m, self.b.entries, self.b, 1000)
        self.assertEqual(replace(self.m, matrix="ARM64").matrix, "ARM64")


class TestPositiveLoopbackPolicyDiscovery(unittest.TestCase):
    def test_existing_default_discovery_without_native_activation(self):
        import fnmatch
        self.assertTrue(fnmatch.fnmatch(Path(__file__).name, "test*.py"))
        business = unittest.defaultTestLoader.loadTestsFromTestCase(TestPositiveLoopbackPolicy)
        own = unittest.defaultTestLoader.loadTestsFromTestCase(type(self))
        self.assertEqual((business.countTestCases(), own.countTestCases()), (19, 1))
        text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        test_job = text.split("\n  test:\n", 1)[1].split(
            "\n  packaged-skill-install:\n", 1)[0]
        self.assertEqual(test_job.count(
            "        run: python -u scripts/run_full_suite_ci.py\n"), 1)
        runner = (ROOT / "scripts/run_full_suite_ci.py").read_text(encoding="utf-8")
        tree = ast.parse(runner)
        argv = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Attribute) and target.attr == "argv"
                        for target in node.targets)
                and isinstance(node.value, ast.List)]
        self.assertEqual([ast.literal_eval(node.value) for node in argv], [["unittest", "-v"]])
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "run_module"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(ast.literal_eval(calls[0].args[0]), "unittest")
        self.assertNotIn("ICODE_DIAGNOSTIC_POSITIVE_LOOPBACK_EXEMPTION:", text)
        self.assertNotIn("CheckNetIsolation.exe LoopbackExempt -a", text)


if __name__ == "__main__":
    unittest.main()
