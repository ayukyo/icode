"""UI 设计包落地：状态展示契约与验收记录投影（§14.11 + R7）。

契约由后端版本化输出，前端只渲染不猜测；验收记录来自证据包事实
（存在才投影，不存在不伪造）。
"""

import json
import tempfile
import unittest
from pathlib import Path

from icode.tickets import (
    STATUS_DISPLAY_LOCALES,
    STATUS_STAGE_KEYS,
    STAGE_DISPLAY_LABELS,
    STATUS_DISPLAY_LABELS,
    acceptance_summary,
    status_display,
)


class StatusDisplayContractTests(unittest.TestCase):
    def test_stage_labels_cover_every_stage_key(self):
        stages = set(STATUS_STAGE_KEYS.values()) | {"unknown"}
        self.assertEqual(stages, set(STAGE_DISPLAY_LABELS))
        for stage, labels in STAGE_DISPLAY_LABELS.items():
            with self.subTest(stage=stage):
                self.assertEqual(set(labels), set(STATUS_DISPLAY_LOCALES))
                for locale, label in labels.items():
                    self.assertTrue(label, locale)

    def test_终态标签双语封闭(self):
        for status, labels in STATUS_DISPLAY_LABELS.items():
            self.assertEqual(set(labels), set(STATUS_DISPLAY_LOCALES))
            self.assertIn(status, ("completed", "blocked", "approval required",
                                   "failed", "unknown"))

    def test_three_part_model_known_status(self):
        display = status_display("review_in_progress", "reviewing_plan")
        self.assertEqual(display["status"], "review_in_progress")
        self.assertEqual(display["stage"], "reviewing_plan")
        self.assertEqual(display["stage_label"]["zh-CN"], "正在检查方案")
        self.assertEqual(display["stage_label"]["en-US"], "Reviewing plan")
        self.assertIsNotNone(display["status_label"])
        self.assertIsNone(display["auxiliary"])

    def test_auxiliary_for_confirmation_and_information(self):
        confirming = status_display("approval required", "reviewing_plan")
        self.assertEqual(confirming["auxiliary"]["key"], "awaiting_confirmation")
        self.assertEqual(confirming["status_label"]["zh-CN"], "需要你确认")
        blocked = status_display("blocked", "unknown")
        self.assertEqual(blocked["auxiliary"]["key"], "awaiting_information")
        self.assertEqual(blocked["status_label"]["en-US"], "Information needed")

    def test_unknown_status_falls_back(self):
        display = status_display("weird_future_status", "not_a_stage")
        self.assertEqual(display["stage"], "unknown")
        self.assertEqual(display["stage_label"]["zh-CN"], "状态未知")
        self.assertIsNone(display["auxiliary"])


class AcceptanceSummaryTests(unittest.TestCase):
    def _write_pack(self, pack_dir: Path, *, signed: bool, anchored: bool) -> None:
        pack_dir.mkdir(parents=True)
        (pack_dir / "manifest.json").write_text(json.dumps({
            "pack_digest": "ab" * 32,
            "generated_at": "2026-10-19T00:00:00+00:00",
        }), encoding="utf-8")
        if signed:
            (pack_dir / "signature.json").write_text(json.dumps({
                "algorithm": "ed25519",
                "signed_at": "2026-10-19T01:00:00+00:00",
                "key_fingerprint": "3ab1",
                "public_key": "cd" * 32,
            }), encoding="utf-8")
        if anchored:
            (pack_dir / "anchors.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "type": "git-tag",
                    "anchor_target": "ab" * 32,
                    "anchor_time": "2026-10-19T02:00:00+00:00",
                    "evidence": {"tag": "anchor/abababababababab",
                                 "repository": "https://github.com/ayukyo/icode"},
                }],
            }), encoding="utf-8")

    def test_absent_pack_returns_none(self):
        with tempfile.TemporaryDirectory(prefix="icode-ui-accept-") as raw:
            self.assertIsNone(acceptance_summary(Path(raw)))

    def test_signed_and_anchored_projection(self):
        with tempfile.TemporaryDirectory(prefix="icode-ui-accept-") as raw:
            self._write_pack(Path(raw) / "pack", signed=True, anchored=True)
            summary = acceptance_summary(Path(raw))
            self.assertIsNotNone(summary)
            self.assertEqual(summary["pack_digest"], "ab" * 32)
            self.assertEqual(summary["signature"]["state"], "signed")
            self.assertEqual(summary["signature"]["algorithm"], "ed25519")
            self.assertEqual(summary["anchors"][0]["type"], "git-tag")

    def test_unsigned_pack_states_it(self):
        with tempfile.TemporaryDirectory(prefix="icode-ui-accept-") as raw:
            self._write_pack(Path(raw) / "pack", signed=False, anchored=False)
            summary = acceptance_summary(Path(raw))
            self.assertIsNone(summary["signature"])
            self.assertEqual(summary["anchors"], [])

    def test_corrupt_manifest_returns_none(self):
        with tempfile.TemporaryDirectory(prefix="icode-ui-accept-") as raw:
            pack = Path(raw) / "pack"
            pack.mkdir()
            (pack / "manifest.json").write_text("not json", encoding="utf-8")
            self.assertIsNone(acceptance_summary(Path(raw)))


if __name__ == "__main__":
    unittest.main()
