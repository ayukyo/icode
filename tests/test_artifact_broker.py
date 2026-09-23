"""策略会话的工单产物由宿主按步骤合同代读写。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests._support import temp_workspace

from icode.artifact_broker import ArtifactAccessError, ArtifactBroker
from icode.contracts import Port, StepContract
from icode.tools import ToolContext, default_registry


class TestArtifactBroker(unittest.TestCase):
    def setUp(self) -> None:
        self._root = temp_workspace()
        self.root = self._root.__enter__()
        self.out_dir = self.root / "ticket"
        self.out_dir.mkdir()
        self.contract = StepContract(
            step="review",
            inputs=(Port("plan", "ticket_file", "01_plan.md"),),
            outputs=(
                Port("review", "ticket_file", "02_review.md"),
                Port("manifest", "ticket_file", "review_manifest.json"),
                Port("rounds", "ticket_glob", "review_round_*.json"),
            ),
        )
        self.broker = ArtifactBroker(self.out_dir, self.contract, max_bytes=1024)

    def tearDown(self) -> None:
        self._root.__exit__(None, None, None)

    def test_仅合同产物可原子提交并读取声明输入(self) -> None:
        (self.out_dir / "01_plan.md").write_text("plan", encoding="utf-8")
        self.assertEqual(self.broker.read("01_plan.md"), "plan")
        self.assertEqual(self.broker.submit("02_review.md", "review"), 6)
        self.assertEqual((self.out_dir / "02_review.md").read_text(encoding="utf-8"),
                         "review")
        self.assertEqual(self.broker.submit("review_round_1.json", '{"round":1}'), 11)
        self.assertFalse(list(self.out_dir.glob(".icode-artifact-*")))

    def test_拒绝越界_隐藏文件_机器产物_未声明文件(self) -> None:
        for name in ("../escape.md", "/tmp/escape.md", ".ico_metadata.json",
                     "review_manifest.json", "unlisted.md", "folder/file.md"):
            with self.subTest(name=name), self.assertRaises(ArtifactAccessError):
                self.broker.submit(name, "untrusted")
        self.assertFalse((self.root / "escape.md").exists())

    def test_拒绝链接和无效JSON时保留原文件(self) -> None:
        outside = self.root / "outside.md"
        outside.write_text("untouched", encoding="utf-8")
        try:
            (self.out_dir / "02_review.md").symlink_to(outside)
        except OSError:
            pass  # Windows 受限账户可能不允许创建符号链接。
        else:
            with self.assertRaises(ArtifactAccessError):
                self.broker.submit("02_review.md", "overwrite")
            self.assertEqual(outside.read_text(encoding="utf-8"), "untouched")

        target = self.out_dir / "review_round_1.json"
        target.write_text('{"round":1}', encoding="utf-8")
        with self.assertRaises(ArtifactAccessError):
            self.broker.submit("review_round_1.json", "not json")
        self.assertEqual(target.read_text(encoding="utf-8"), '{"round":1}')

    def test_大小上限和输入边界(self) -> None:
        with self.assertRaises(ArtifactAccessError):
            self.broker.submit("02_review.md", "x" * 1025)
        with self.assertRaises(ArtifactAccessError):
            self.broker.read("02_review.md")
        with self.assertRaises(ArtifactAccessError):
            self.broker.read(".ico_metadata.json")

    def test_宿主替换失败按稳定错误返回且清理临时文件(self) -> None:
        with patch("icode.artifact_broker.os.replace", side_effect=OSError("private host path")):
            with self.assertRaises(ArtifactAccessError) as caught:
                self.broker.submit("02_review.md", "review")
        self.assertNotIn("private host path", str(caught.exception))
        self.assertFalse(list(self.out_dir.glob(".icode-artifact-*")))

    def test_模型只能通过启用的受控工具访问合同端口(self) -> None:
        registry = default_registry(include_artifacts=True)
        context = ToolContext(root=self.root, artifact_broker=self.broker)
        (self.out_dir / "01_plan.md").write_text("plan", encoding="utf-8")
        self.assertEqual(registry.invoke(
            "read_artifact", context, {"name": "01_plan.md"},
        ).content, "plan")
        self.assertTrue(registry.invoke(
            "submit_artifact", context,
            {"name": "02_review.md", "content": "review"},
        ).ok)
        self.assertEqual((self.out_dir / "02_review.md").read_text(encoding="utf-8"),
                         "review")
        blocked = registry.invoke(
            "submit_artifact", context,
            {"name": ".ico_metadata.json", "content": "spoof"},
        )
        self.assertFalse(blocked.ok)
        self.assertFalse((self.out_dir / ".ico_metadata.json").exists())
        self.assertNotIn("submit_artifact", default_registry().names())
