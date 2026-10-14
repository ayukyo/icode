import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unittest

CASES = (
    "cap1_fork", "control_fork", "seatbelt_positive", "profile_error",
    "release_eof", "exec_error", "receipt_loss",
)
NORMAL = ("cap1_fork", "control_fork", "seatbelt_positive", "receipt_loss")
FIELDS = frozenset("""
kind version candidate_sha variant case kernel os_build arch translated binary_sha256
profile_sha256 sandbox_exec_sha256 observer_pid observer_uid pid start_sec start_usec uid gid
saved_uid saved_gid credentials_valid configured sandboxed quota_enabled
profile_enabled cur hard uid_count_at_barrier registered released kernel_exec
payload_started exec_errno entered normal_exit payload_pid
payload_cur payload_hard fd3_errno fd4_errno recover_uid_errno recover_gid_errno
groups group fork_pid fork_errno child_byte gate_canary_errno gate_canary_allowed
payload_canary_errno payload_canary_allowed wait_status exit_code term_signal
remaining cleanup_scope retained
""".split())

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def started_state(kernel_exec, released, exec_errno):
    if kernel_exec == 1:
        return "true"
    if not released or exec_errno:
        return "false"
    return "unknown"

def delivered_state(confirmation):
    if confirmation is None:
        return "unknown"
    if confirmation not in ("false", "true", "unknown"):
        raise ValueError("invalid three-state value")
    return confirmation

def parse_delivery(raw):
    if len(raw) > 65536:
        raise ValueError("delivery size exceeded")
    launches, confirmations = {}, {}
    audit = None
    for line in raw.splitlines():
        row = json.loads(line, object_pairs_hook=unique_object)
        if audit is not None:
            raise ValueError("data after final audit manifest")
        kind = row.get("kind")
        if kind == "audit":
            if set(row) != {"kind", "version", "ledger_sha256", "root_directory", "retained"}:
                raise ValueError("audit schema mismatch")
            if row["version"] != 1 or row["retained"] is not True:
                raise ValueError("audit contract mismatch")
            if not re.fullmatch(r"[0-9a-f]{64}", row["ledger_sha256"]):
                raise ValueError("audit digest invalid")
            if not re.fullmatch(r"/private/var/icode-m0a1\.[A-Za-z0-9]+", row["root_directory"]):
                raise ValueError("root fixture target invalid")
            audit = row
            continue
        name = row.get("case")
        if name not in CASES or row.get("version") != 1:
            raise ValueError("delivery identity invalid")
        if kind == "launch":
            if set(row) != {"kind", "version", "case", "released"} or type(row["released"]) is not int:
                raise ValueError("launch schema invalid")
            if row["released"] not in (0, 1) or name in launches:
                raise ValueError("launch invalid or duplicated")
            if len(launches) >= len(CASES) or name != CASES[len(launches)]:
                raise ValueError("launch order invalid")
            launches[name] = row["released"]
        elif kind == "confirmation":
            if set(row) != {"kind", "version", "case", "payload_started"}:
                raise ValueError("confirmation schema invalid")
            if name not in launches or name in confirmations or name != next(reversed(launches)):
                raise ValueError("unsolicited or repeated confirmation")
            confirmations[name] = delivered_state(row["payload_started"])
        else:
            raise ValueError("unexpected delivery record")
    if tuple(launches) != CASES or audit is None:
        raise ValueError("delivery incomplete")
    views = {name: {"released": launches[name], "confirmation": confirmations.get(name),
                    "payload_started": delivered_state(confirmations.get(name))}
             for name in CASES}
    return views, audit

def bounded_json(path, bound):
    data = Path(path).read_bytes()
    if len(data) > bound:
        raise ValueError("evidence size exceeded")
    return json.loads(data, object_pairs_hook=unique_object)

def load_evidence(directory):
    directory = Path(directory)
    meta = bounded_json(directory / "metadata.json", 16384)
    delivery_raw = (directory / "native.stdout.jsonl").read_bytes()
    views, audit = parse_delivery(delivery_raw)
    if bounded_json(directory / "delivery-view.json", 4096) != views:
        raise ValueError("frozen delivery view differs from actual received bytes")
    if hashlib.sha256(delivery_raw).hexdigest() != meta["native_stdout_sha256"]:
        raise ValueError("delivery raw changed")
    raw = (directory / "native.audit.jsonl").read_bytes()
    if len(raw) > 65536:
        raise ValueError("native output size exceeded")
    if meta.get("truncated") or hashlib.sha256(raw).hexdigest() != meta["native_audit_sha256"]:
        raise ValueError("native audit export truncated or changed")
    lines = raw.splitlines(keepends=True)
    if len(lines) != len(CASES):
        raise ValueError("native evidence incomplete")
    objects = [json.loads(line, object_pairs_hook=unique_object) for line in lines]
    if hashlib.sha256(raw).hexdigest() != audit["ledger_sha256"]:
        raise ValueError("root ledger export hash mismatch")
    records = {}
    for name, row in zip(CASES, objects):
        if set(row) != FIELDS or row["case"] != name or row["kind"] != "case" or row["version"] != 1:
            raise ValueError("native case schema/order mismatch")
        if row["candidate_sha"] != meta["candidate_sha"] or row["arch"] != meta["arch"]:
            raise ValueError("native candidate/platform mismatch")
        if row["binary_sha256"] != meta["binary_sha256"] or row["variant"] != meta["variant"]:
            raise ValueError("native binary identity mismatch")
        if row["kernel"] != meta["kernel"] or row["os_build"] != meta["os_build"]:
            raise ValueError("native OS identity mismatch")
        for key in ("binary_sha256", "profile_sha256", "sandbox_exec_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", row[key]):
                raise ValueError("native digest invalid")
        state = started_state(row["kernel_exec"], row["released"], row["exec_errno"])
        if row["payload_started"] != state:
            raise ValueError("native exec fact contradicted")
        if views[name]["released"] != row["released"]:
            raise ValueError("launch fact differs from root audit")
        if views[name]["confirmation"] is not None and views[name]["confirmation"] != state:
            raise ValueError("received confirmation differs from root audit")
        records[name] = row
    return meta, records, audit, views

class TestM0a1Protocol(unittest.TestCase):
    def test_no_release_is_false(self):
        self.assertEqual(started_state(0, 0, 0), "false")

    def test_exec_failure_is_false(self):
        self.assertEqual(started_state(0, 1, errno.ENOENT), "false")

    def test_eof_without_exec_evidence_is_unknown(self):
        self.assertEqual(started_state(0, 1, 0), "unknown")

    def test_native_exec_survives_receipt_loss(self):
        self.assertEqual(started_state(1, 1, 0), "true")
        wire = []
        for name in CASES:
            wire.append({"kind": "launch", "version": 1, "case": name, "released": 1})
            if name != "receipt_loss":
                wire.append({"kind": "confirmation", "version": 1, "case": name,
                             "payload_started": "true"})
        wire.append({"kind": "audit", "version": 1, "ledger_sha256": "0" * 64,
                     "root_directory": "/private/var/icode-m0a1.Protocol", "retained": True})
        views, _ = parse_delivery(("\n".join(json.dumps(row) for row in wire) + "\n").encode())
        self.assertIsNone(views["receipt_loss"]["confirmation"])
        self.assertEqual(views["receipt_loss"]["payload_started"], "unknown")
        self.assertEqual(views["cap1_fork"]["payload_started"], "true")

    def test_forged_or_invalid_receipt_rejected(self):
        with self.assertRaises(ValueError):
            delivered_state("SANDBOXED EXEC_OK")
        with self.assertRaises(ValueError):
            json.loads('{"version":1,"version":1}', object_pairs_hook=unique_object)

@unittest.skipUnless(os.environ.get("ICODE_M0A1_EVIDENCE"), "native evidence was not requested")
class TestNativeM0a1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "darwin":
            raise RuntimeError("macOS native evidence cannot be verified on another OS")
        cls.meta, cls.rows, cls.audit, cls.views = load_evidence(os.environ["ICODE_M0A1_EVIDENCE"])
        if cls.meta["native_exit"] != 0:
            raise RuntimeError("native driver failed, not semantic RED")

    def test_complete_native_identity_and_protocol(self):
        self.assertEqual(tuple(self.rows), CASES)
        self.assertEqual(len({r["uid"] for r in self.rows.values()}), len(CASES))
        for r in self.rows.values():
            with self.subTest(case=r["case"]):
                self.assertEqual(r["observer_uid"], 0)
                self.assertEqual(r["translated"], 0)
                self.assertGreater(r["observer_pid"], 0)
                self.assertGreater(r["pid"], 0)
                self.assertGreater(r["start_sec"], 0)
                self.assertGreaterEqual(r["uid"], 60000)
                self.assertLess(r["uid"], 61024)
                self.assertEqual(r["gid"], r["uid"])
                self.assertEqual(r["remaining"], 0)
                self.assertIs(r["retained"], True)
                self.assertEqual(r["cleanup_scope"], "owned_root_only")
        for name in NORMAL:
            r = self.rows[name]
            with self.subTest(case=name):
                for key in ("configured", "sandboxed", "credentials_valid", "registered",
                            "released", "kernel_exec", "entered", "normal_exit"):
                    self.assertEqual(r[key], 1, key)
                self.assertEqual(r["uid_count_at_barrier"], 1)
                self.assertEqual(r["payload_pid"], r["pid"])
                self.assertEqual(r["saved_uid"], r["uid"])
                self.assertEqual(r["saved_gid"], r["gid"])
                self.assertEqual(r["groups"], 1)
                self.assertEqual(r["group"], r["gid"])
                self.assertEqual(r["fd3_errno"], errno.EBADF)
                self.assertEqual(r["fd4_errno"], errno.EBADF)
                self.assertEqual(r["recover_uid_errno"], errno.EPERM)
                self.assertEqual(r["recover_gid_errno"], errno.EPERM)
                self.assertEqual(r["gate_canary_allowed"], 1)
                self.assertEqual(r["payload_canary_allowed"], 1)
                if r["profile_enabled"]:
                    self.assertIn(r["gate_canary_errno"], (errno.EPERM, errno.EACCES))
                    self.assertIn(r["payload_canary_errno"], (errno.EPERM, errno.EACCES))
                else:
                    self.assertEqual(r["gate_canary_errno"], 0)
                    self.assertEqual(r["payload_canary_errno"], 0)

    def test_positive_controls_really_execute(self):
        for name in ("control_fork", "seatbelt_positive"):
            r = self.rows[name]
            self.assertEqual(r["quota_enabled"], 0)
            self.assertGreater(r["fork_pid"], 0)
            self.assertEqual(r["fork_errno"], 0)
            self.assertEqual(r["child_byte"], 1)
            self.assertGreaterEqual(r["payload_cur"], 2)
        self.assertEqual(self.rows["control_fork"]["profile_enabled"], 1)
        self.assertEqual(self.rows["seatbelt_positive"]["profile_enabled"], 0)

    def test_cap1_quota_semantic(self):
        for name in ("cap1_fork", "receipt_loss"):
            r = self.rows[name]
            self.assertEqual(r["fork_errno"], errno.EAGAIN, "M0A1_QUOTA_REJECTION")
            self.assertEqual(r["fork_pid"], -1)
            self.assertEqual(r["child_byte"], 0)
            self.assertEqual(r["quota_enabled"], 1)
            self.assertEqual((r["cur"], r["hard"]), (1, 1))
            self.assertEqual((r["payload_cur"], r["payload_hard"]), (1, 1))

    def test_no_payload_before_release(self):
        for name in ("profile_error", "release_eof"):
            r = self.rows[name]
            self.assertEqual(r["configured"], 1)
            self.assertEqual(r["released"], 0)
            self.assertEqual(r["kernel_exec"], 0)
            self.assertEqual(r["entered"], 0)
            self.assertEqual(r["payload_started"], "false")
        self.assertEqual(self.rows["profile_error"]["sandboxed"], 0)
        self.assertEqual(self.rows["release_eof"]["sandboxed"], 1)
        self.assertEqual(self.rows["release_eof"]["exec_errno"], errno.ECANCELED)

    def test_exec_failure_and_lost_delivery_distinct(self):
        failed = self.rows["exec_error"]
        self.assertEqual(failed["released"], 1)
        self.assertEqual(failed["kernel_exec"], 0)
        self.assertEqual(failed["exec_errno"], errno.ENOENT)
        self.assertEqual(failed["entered"], 0)
        self.assertEqual(failed["payload_started"], "false")
        lost = self.rows["receipt_loss"]
        self.assertEqual(lost["kernel_exec"], 1)
        self.assertEqual(lost["entered"], 1)
        self.assertEqual(lost["payload_started"], "true")
        self.assertIsNone(self.views["receipt_loss"]["confirmation"])
        self.assertEqual(self.views["receipt_loss"]["payload_started"], "unknown")
        for name in CASES:
            if name != "receipt_loss":
                self.assertEqual(self.views[name]["confirmation"], self.rows[name]["payload_started"])
