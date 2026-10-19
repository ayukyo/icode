"""R7/W2：预声明锚定记录与 anchors.json 落盘。"""

import json
import tempfile
import unittest
from pathlib import Path

from icode.pack_anchor import (
    ANCHOR_TYPES,
    AnchorError,
    attach_anchor_records,
    build_ci_run_record,
    build_git_tag_record,
    build_rfc3161_record,
    build_transparency_log_record,
    validate_records,
)
from icode.pack_verify import validate_anchor_bundle

DIGEST = "ab" * 32


def _write_manifest(root: Path, pack_digest: str) -> Path:
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps({"pack_digest": pack_digest}), encoding="utf-8")
    return manifest_path


class BuilderTests(unittest.TestCase):
    def test_git_tag_record_defaults_and_prefix_rule(self):
        record = build_git_tag_record(DIGEST, "https://github.com/ayukyo/icode")
        self.assertEqual(record["type"], "git-tag")
        self.assertEqual(record["anchor_target"], DIGEST)
        self.assertEqual(record["evidence"]["tag"], f"anchor/{DIGEST[:16]}")
        with self.assertRaises(AnchorError):
            build_git_tag_record(DIGEST, "https://example.com", tag="release-1")

    def test_digest_must_be_hex64(self):
        for bad in ("", "XYZ", "ab" * 31, "AB" * 32, None, 123):
            with self.subTest(bad=bad):
                with self.assertRaises(AnchorError):
                    build_git_tag_record(bad, "https://example.com")

    def test_ci_run_requires_https(self):
        record = build_ci_run_record(DIGEST, "https://ci.example.com/run/1", "1", "success")
        self.assertEqual(record["evidence"]["conclusion"], "success")
        with self.assertRaises(AnchorError):
            build_ci_run_record(DIGEST, "http://ci.example.com/run/1", "1", "success")

    def test_rfc3161_fingerprint_must_be_hex(self):
        record = build_rfc3161_record(DIGEST, "cd" * 32)
        self.assertEqual(record["evidence"]["hash_algorithm"], "sha256")
        with self.assertRaises(AnchorError):
            build_rfc3161_record(DIGEST, "not-hex-at-all")
        with self.assertRaises(AnchorError):
            build_rfc3161_record(DIGEST, "ab")  # 太短

    def test_transparency_log_requires_https(self):
        record = build_transparency_log_record(DIGEST, "rekor", "https://rekor.example/entry/1")
        self.assertEqual(record["evidence"]["log_id"], "rekor")
        with self.assertRaises(AnchorError):
            build_transparency_log_record(DIGEST, "rekor", "http://rekor.example/entry/1")


class ValidationTests(unittest.TestCase):
    def test_type_vocabulary_is_closed(self):
        record = build_git_tag_record(DIGEST, "https://example.com")
        self.assertIn(record["type"], ANCHOR_TYPES)
        for bad in ("gossip", "handshake", "", None):
            mutated = dict(record, type=bad)
            problems = validate_anchor_bundle(
                {"schema_version": 1, "records": [mutated]}, DIGEST)
            self.assertTrue(any("封闭词表" in p for p in problems), problems)

    def test_digest_binding_rejects_re_paste(self):
        record = build_git_tag_record(DIGEST, "https://example.com")
        other_digest = "cd" * 32
        problems = validate_anchor_bundle(
            {"schema_version": 1, "records": [record]}, other_digest)
        self.assertTrue(any("换包重贴" in p for p in problems), problems)

    def test_missing_and_extra_fields_rejected(self):
        record = build_ci_run_record(DIGEST, "https://ci/1", "1", "success")
        broken = dict(record)
        del broken["evidence"]
        problems = validate_anchor_bundle({"schema_version": 1, "records": [broken]}, DIGEST)
        self.assertTrue(any("缺少字段" in p for p in problems), problems)
        extra = dict(record, note="hello")
        problems = validate_anchor_bundle({"schema_version": 1, "records": [extra]}, DIGEST)
        self.assertTrue(any("未知字段" in p for p in problems), problems)
        bad_evidence = dict(record, evidence={"run_url": "https://ci/1"})
        problems = validate_anchor_bundle({"schema_version": 1, "records": [bad_evidence]}, DIGEST)
        self.assertTrue(any("evidence 缺少字段" in p for p in problems), problems)

    def test_valid_bundle_passes(self):
        records = [
            build_git_tag_record(DIGEST, "https://github.com/ayukyo/icode"),
            build_ci_run_record(DIGEST, "https://ci.example.com/run/1", "1", "success"),
            build_rfc3161_record(DIGEST, "cd" * 32),
            build_transparency_log_record(DIGEST, "rekor", "https://rekor/entry/1"),
        ]
        self.assertEqual(validate_records(records, DIGEST), [])
        bundle = {"schema_version": 1, "records": records}
        self.assertEqual(validate_anchor_bundle(bundle, DIGEST), [])


class AttachTests(unittest.TestCase):
    def test_attach_writes_validated_bundle(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-anchor-") as raw:
            root = Path(raw)
            _write_manifest(root, DIGEST)
            path = attach_anchor_records(
                root, [build_git_tag_record(DIGEST, "https://example.com")])
            bundle = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(validate_anchor_bundle(bundle, DIGEST), [])

    def test_attach_refuses_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-anchor-") as raw:
            root = Path(raw)
            _write_manifest(root, DIGEST)
            attach_anchor_records(root, [])
            with self.assertRaises(AnchorError):
                attach_anchor_records(root, [])

    def test_attach_fail_closed_on_invalid_records(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-anchor-") as raw:
            root = Path(raw)
            _write_manifest(root, DIGEST)
            bad = [dict(build_git_tag_record(DIGEST, "https://example.com"),
                        type="unknown-type")]
            with self.assertRaises(AnchorError):
                attach_anchor_records(root, bad)
            self.assertFalse((root / "anchors.json").exists())


if __name__ == "__main__":
    unittest.main()
