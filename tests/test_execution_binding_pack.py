"""Portable binding contracts, including independently executed rehashed packs."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from tests._support import require_skill
from icode.control import ControlPlane
from icode.evidence import build_evidence_pack
from icode import pack_verify
from icode.pack_verify import canonical_event_hash, verify_pack


class BindingPackTests(unittest.TestCase):
    def test_real_bound_partial_pack_is_portable_after_code_disappears(self):
        settings = require_skill()
        cp = ControlPlane(settings)
        with tempfile.TemporaryDirectory(prefix="icode-binding-pack-") as raw:
            root = Path(raw).resolve()
            code = root / "code"
            code.mkdir()
            (root / "control").mkdir()
            ticket = root / "control/.icode_output/.icode_output_1"
            cp.create(ticket, ticket_id="pack-bind", requirement="binding pack")
            cp.bind_execution_root(ticket, ticket_id="pack-bind", execution_root=code)
            pack = root / "pack"
            report = build_evidence_pack(ticket, dest=pack, gates_json=settings.gates_json,
                                         clean=False)
            self.assertTrue(report.ok, report.render())
            self.assertEqual(verify_pack(pack), [])
            code.rmdir()
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            proc = subprocess.run([sys.executable, "-I", "-B", str(pack / "verify.py"), str(pack)],
                                  cwd=root, env=env, capture_output=True,
                                  text=True, encoding="utf-8", timeout=15)
            self.assertEqual(proc.returncode, 0, (proc.stdout, proc.stderr))

    def test_self_consistent_hash_does_not_replace_binding_semantics(self):
        mirror_type = getattr(pack_verify, "ExecutionBindingMirror", None)
        self.assertIsNotNone(mirror_type, "missing execution-binding mirror")
        binding = {"version": 1, "path": "/code", "ancestors": [
            {"path": "/", "device": 1, "inode": 1},
            {"path": "/code", "device": 1, "inode": 2}]}
        metadata = {"execution_binding": binding}
        digest = pack_verify._metadata_content_hash(metadata)
        good = {"event_type": "metadata_updated", "actor": "icode", "request_id": "binding",
                "payload": {"execution_root_binding": 1, "metadata_hash_after": digest,
                            "set": {"execution_binding": binding}, "append": {}}}

        def replay(sequence, meta=metadata):
            previous = "0" * 64
            mirror = mirror_type(meta)
            for item in sequence:
                event = dict(item, previous_event_hash=previous)
                event["event_hash"] = canonical_event_hash(event)
                previous = event["event_hash"]
                mirror.consume(event)
            return mirror.finish()

        self.assertEqual(replay([good]), [])
        # A later well-formed transaction must not mask a missing binding digest.
        later = {"event_type": "metadata_updated", "payload": {
            "set": {}, "append": {}, "metadata_hash_after": digest}}
        self.assertEqual(replay([good, later]), [])
        bad = [("missing-event", []), ("duplicate", [good, good])]
        missing_marker = copy.deepcopy(good)
        del missing_marker["payload"]["execution_root_binding"]
        bad.append(("missing-marker", [missing_marker]))
        boolean_marker = copy.deepcopy(good)
        boolean_marker["payload"]["execution_root_binding"] = True
        bad.append(("boolean-marker", [boolean_marker]))
        for name, value in (("missing", None), ("bool", True), ("invalid", "not-a-hash"),
                            ("uppercase", "A" * 64), ("short", "a" * 63)):
            event = copy.deepcopy(good)
            if value is None:
                del event["payload"]["metadata_hash_after"]
            else:
                event["payload"]["metadata_hash_after"] = value
            bad.append(("digest-" + name, [event, later]))
        for name, sequence in bad:
            with self.subTest(mutation=name):
                self.assertTrue(replay(sequence))
        self.assertTrue(replay([good], {}))
        self.assertEqual(replay([good], object()), [])  # Low-level no-metadata sentinel.

        # Guard depth before ancestor-list materialization, not merely after it.
        class TooManyParents:
            def __len__(self):
                return pack_verify.MAX_EXECUTION_BINDING_ANCESTORS

            def __iter__(self):
                raise AssertionError("overdeep ancestors must not be materialized")

            def __reversed__(self):
                raise AssertionError("overdeep ancestors must not be materialized")

        class DeepPath:
            parts = ("/", "code")
            parents = TooManyParents()

            def __init__(self, raw):
                self.raw = raw

            def is_absolute(self):
                return True

            def __str__(self):
                return self.raw

        with patch.object(pack_verify, "PurePosixPath", DeepPath):
            self.assertFalse(pack_verify.execution_binding_shape_ok(binding))
        deep = copy.deepcopy(binding)
        deep["path"] = "/" + "/".join(["x"] * 256)
        self.assertFalse(pack_verify.execution_binding_shape_ok(deep))

    def test_verify_pack_and_independent_process_reject_rehashed_binding_forgery(self):
        settings = require_skill()
        cp = ControlPlane(settings)
        for mutation in ("missing-marker", "duplicate", "missing-digest", "invalid-digest"):
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory(prefix="icode-binding-forgery-") as raw:
                    root = Path(raw).resolve()
                    (root / "code").mkdir()
                    (root / "control").mkdir()
                    ticket = root / "control/.icode_output/.icode_output_1"
                    cp.create(ticket, ticket_id="binding-forgery", requirement="binding pack")
                    cp.bind_execution_root(ticket, ticket_id="binding-forgery",
                                           execution_root=root / "code")
                    # Real later transaction supplies the final valid metadata digest.
                    cp.metadata_update(ticket, ticket_id="binding-forgery",
                                       set_json={"extensions": {"binding_test": True}},
                                       request="after-binding")
                    pack = root / "pack"
                    report = build_evidence_pack(ticket, dest=pack,
                                                 gates_json=settings.gates_json, clean=False)
                    self.assertTrue(report.ok, report.render())
                    self.assertEqual(verify_pack(pack), [])
                    path = pack / "ticket/events.jsonl"
                    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                    binding_event = next(event for event in events
                                         if "execution_root_binding" in event["payload"])
                    if mutation == "missing-marker":
                        del binding_event["payload"]["execution_root_binding"]
                    elif mutation == "duplicate":
                        extra = copy.deepcopy(binding_event)
                        extra["event_id"] = str(uuid.uuid4())
                        events.insert(events.index(binding_event) + 1, extra)
                    elif mutation == "missing-digest":
                        del binding_event["payload"]["metadata_hash_after"]
                    else:
                        binding_event["payload"]["metadata_hash_after"] = True
                    metadata = json.loads((pack / "ticket/metadata.json").read_text(encoding="utf-8"))
                    events[-1]["payload"]["metadata_hash_after"] = pack_verify._metadata_content_hash(metadata)
                    previous = "0" * 64
                    for event in events:
                        event["previous_event_hash"] = previous
                        event["event_hash"] = canonical_event_hash(event)
                        previous = event["event_hash"]
                    path.write_text("\n".join(json.dumps(event, ensure_ascii=False)
                                             for event in events) + "\n", encoding="utf-8")
                    manifest_path = pack / "manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for item in manifest["files"]:
                        member = pack / item["path"]
                        item["sha256"] = pack_verify.sha256_file(member)
                        item["size"] = member.stat().st_size
                    manifest["pack_digest"] = pack_verify.pack_digest(manifest["files"])
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
                    problems = verify_pack(pack)
                    environment = dict(os.environ)
                    environment.pop("PYTHONPATH", None)
                    result = subprocess.run([sys.executable, "-I", "-B", str(pack / "verify.py"), str(pack)],
                                            cwd=root, env=environment, capture_output=True, text=True,
                                            encoding="utf-8", timeout=15)
                    self.assertTrue(any("binding_" in item for item in problems),
                                    (problems, result.returncode, result.stdout, result.stderr))
                    self.assertFalse(any("断链" in item or "sha256" in item for item in problems), problems)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("binding_", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
