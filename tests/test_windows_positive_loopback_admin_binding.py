"""Dual-domain software protocol; no sender or OS authentication claim."""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import importlib
import json
import unittest
from icode import windows_positive_loopback_policy as policy

NAME = "scripts.windows_positive_loopback_admin"
try:
    admin = importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name != NAME: raise
    admin = None


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def identity():
    return dict(schema=1, domain="icode_positive_bootstrap_v1",
        repository="ayukyo/icode", source_sha="a" * 40, run_id="123",
        run_attempt=1, job="windows-reviewer-snapshot-probe", matrix="x64",
        session="4" * 32, account_sid="S-1-5-21-1-2-3-1001", pid=1234,
        process_created=5678, positive_profile="icode-" + "1" * 32,
        reviewer_profile="icode-" + "2" * 32,
        positive_sid="S-1-15-2-1-2-3-4-5-6-7",
        reviewer_sid="S-1-15-2-8-9-10-11-12-13-14", nonce="3" * 32,
        ipv4_port=12345, ipv6_port=23456, prepared_ms=1000,
        preparation_deadline_ms=181000)


def manifest(bootstrap, start=180999):
    fields = {key:value for key,value in bootstrap.items() if key not in
        {"schema", "domain", "session", "prepared_ms", "preparation_deadline_ms"}}
    return policy.Manifest(admission=policy.AdmissionFacts(True, True, True, True, True),
                           **fields, started_ms=start, deadline_ms=start + 60000)


class TestAdminBindings(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(admin, "new admin binding component absent; facility RED")
        self.b = identity()
        self.m = manifest(self.b)
        self.session = self.b["session"]

    def test_bootstrap_real_producer_parser_digest_and_exact_fields(self):
        produced = admin.encode_bootstrap_request(self.b)
        body = json.loads(produced)
        self.assertEqual(body["binding"], hashlib.sha256(wire(self.b)).hexdigest())
        self.assertEqual(set(body), {"schema", "domain", "kind", "binding", "session",
            "pid", "process_created", "positive_profile", "positive_sid", "reviewer_sid",
            "nonce", "ipv4_port", "ipv6_port"})
        self.assertEqual(admin.validate_bootstrap_request(produced, self.b, 180999),
                         "profile_created")
        self.assertNotIn("binding", self.b)
        self.assertLessEqual(len(produced), 4096)

    def test_bootstrap_identity_each_field_digest_binds_and_bad_shapes_reject(self):
        original = admin.encode_bootstrap_request(self.b)
        for key in self.b:
            changed = dict(self.b)
            changed[key] = None
            with self.subTest(key=key), self.assertRaises((admin.AdminError, policy.PolicyError)):
                admin.encode_bootstrap_request(changed)
        for key in ("source_sha", "run_id", "session", "nonce", "positive_profile"):
            changed = dict(self.b)
            changed[key] = changed[key].replace("1", "5").replace("a", "b").replace("3", "6").replace("4", "7")
            with self.subTest(key=key), self.assertRaises((admin.AdminError, policy.PolicyError)):
                admin.validate_bootstrap_request(original, changed, 1001)
        for key in ("schema", "pid", "process_created", "run_attempt", "ipv4_port",
                    "ipv6_port", "prepared_ms", "preparation_deadline_ms"):
            changed = dict(self.b, **{key:True})
            with self.subTest(key=key), self.assertRaises((admin.AdminError, policy.PolicyError)):
                admin.encode_bootstrap_request(changed)

    def test_dual_clocks_near_preparation_expiry_gets_new_immutable_operation_window(self):
        created = admin.encode_bootstrap_request(self.b)
        self.assertEqual(admin.validate_bootstrap_request(created, self.b, 180999), "profile_created")
        operation = admin.encode_operation_request(self.m, self.session)
        self.assertEqual(admin.validate_operation_request(operation, self.m, self.session, 240998),
                         "probe_finished")
        self.assertEqual((self.m.started_ms, self.m.deadline_ms), (180999, 240999))
        for now in (999, 181000, 181001, True):
            with self.subTest(now=now), self.assertRaises(admin.AdminError):
                admin.validate_bootstrap_request(created, self.b, now)
        for now in (180998, 240999, 241000, True):
            with self.subTest(now=now), self.assertRaises(policy.PolicyError):
                admin.validate_operation_request(operation, self.m, self.session, now)

    def test_domain_and_core_requests_cannot_cross_admission(self):
        created = admin.encode_bootstrap_request(self.b)
        operation = admin.encode_operation_request(self.m, self.session)
        naked = policy.encode_request(self.m, "profile_created")
        with self.assertRaises(admin.AdminError):
            admin.validate_operation_request(created, self.m, self.session, 181000)
        for value in (operation, naked):
            with self.subTest(value=value), self.assertRaises(admin.AdminError):
                admin.validate_bootstrap_request(value, self.b, 1001)
        self.assertEqual(json.loads(operation)["request"],
                         json.loads(policy.encode_request(self.m, "probe_finished")))

    def test_request_each_field_missing_extra_or_wrong_type_rejects(self):
        for mode in ("bootstrap", "operation"):
            original = json.loads(admin.encode_bootstrap_request(self.b) if mode == "bootstrap"
                                  else admin.encode_operation_request(self.m, self.session))
            def validate(value):
                if mode == "bootstrap":
                    return admin.validate_bootstrap_request(value, self.b, 1001)
                return admin.validate_operation_request(value, self.m, self.session, 181000)
            for key in original:
                missing = dict(original); del missing[key]
                wrong = dict(original, **{key:None})
                for changed in (missing, wrong):
                    with self.subTest(mode=mode, key=key), self.assertRaises(
                            (admin.AdminError, policy.PolicyError)):
                        validate(wire(changed))
            with self.assertRaises((admin.AdminError, policy.PolicyError)):
                validate(wire(dict(original, extra=1)))

    def test_parser_duplicate_keys_utf8_nan_size_and_bool_int_reject(self):
        created = admin.encode_bootstrap_request(self.b)
        operation = admin.encode_operation_request(self.m, self.session)
        for good, validate in (
            (created, lambda data: admin.validate_bootstrap_request(data, self.b, 1001)),
            (operation, lambda data: admin.validate_operation_request(data, self.m, self.session, 181000))):
            for bad in (b"", b"x" * 4097, b"\xff", b"[]", b'{"x":NaN}',
                        good[:-1] + b',"schema":1}', good.replace(b'"schema":1', b'"schema":true')):
                with self.subTest(bad=bad), self.assertRaises((admin.AdminError, policy.PolicyError)):
                    validate(bad)
        outer = json.loads(operation)
        for key in outer["request"]:
            changed = json.loads(operation)
            changed["request"][key] = None
            with self.subTest(key=key), self.assertRaises((admin.AdminError, policy.PolicyError)):
                admin.validate_operation_request(wire(changed), self.m, self.session, 181000)
        changed = json.loads(operation); changed["request"]["ipv4_port"] = True
        with self.assertRaises(policy.PolicyError):
            admin.validate_operation_request(wire(changed), self.m, self.session, 181000)

    def test_operation_binding_session_candidate_and_window_are_immutable(self):
        from dataclasses import replace
        operation = admin.encode_operation_request(self.m, self.session)
        for changed in (replace(self.m, source_sha="b" * 40),
                        replace(self.m, started_ms=181000, deadline_ms=241000),
                        replace(self.m, ipv6_port=23457)):
            with self.subTest(changed=changed), self.assertRaises(policy.PolicyError):
                admin.validate_operation_request(operation, changed, self.session, 181001)
        with self.assertRaises(admin.AdminError):
            admin.validate_operation_request(operation, self.m, "5" * 32, 181001)


if __name__ == "__main__":
    unittest.main()
