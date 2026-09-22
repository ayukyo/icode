"""契约握手测试（Phase 1 核心验收）。

全程离线：不调用模型、不联网，产物落在临时目录。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests._support import require_skill, temp_workspace

from icode.control import ControlPlane, make_request
from icode.handshake import PROBE_BANNER, request_preview, run_handshake


class TestDeterministicRequestKeys(unittest.TestCase):
    def test_同逻辑动作派生同键(self) -> None:
        a = make_request("T-1", "step-plan-check", boundary="before_write", occurrence=1)
        b = make_request("T-1", "step-plan-check", boundary="before_write", occurrence=1)
        self.assertEqual(a, b)

    def test_不同发生次数派生不同键(self) -> None:
        a = make_request("T-1", "step-plan-check", boundary="before_write", occurrence=1)
        b = make_request("T-1", "step-plan-check", boundary="before_write", occurrence=2)
        self.assertNotEqual(a, b)

    def test_不同工单不冲突(self) -> None:
        self.assertNotEqual(make_request("T-1", "create"), make_request("T-2", "create"))

    def test_预览包含四个关键键(self) -> None:
        self.assertEqual(len(request_preview("HANDSHAKE-1", "plan")), 4)


class TestHandshake(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def test_plan_步骤端到端握手通过(self) -> None:
        with temp_workspace() as ws:
            report = run_handshake(self.settings, workspace=ws, step="plan")

            self.assertEqual(report.error, "", f"握手异常：{report.error}")
            self.assertTrue(report.ok, "握手未通过：\n" + report.render())

            # 契约的复检点必须全部被执行
            names = [c.name for c in report.checkpoints]
            self.assertTrue(any("before_write" in n for n in names))
            self.assertTrue(any("before_transition" in n for n in names))
            self.assertTrue(any("finish success" in n for n in names))

            # 事件链完整且无未闭合项
            self.assertGreaterEqual(report.trace.get("event_count", 0), 5)
            self.assertEqual(report.trace.get("open_steps"), {})
            self.assertEqual(report.trace.get("open_operations"), {})
            self.assertEqual(report.trace.get("open_agents"), {})

    def test_状态前移被门禁正确拦截_且不伪造证据(self) -> None:
        """门禁要求真实证据（思考 trace / 语义决策），探测件应被拦下。

        这条测试是**门禁有效性的回归信号**：
        若某天门禁放行了没有真实证据的探测件，说明门禁被削弱了，必须立刻知道。
        """
        with temp_workspace() as ws:
            report = run_handshake(self.settings, workspace=ws, step="plan")
            self.assertTrue(report.ok, report.render())
            self.assertIsNotNone(report.advance)
            self.assertEqual(report.advance.status, "blocked",
                             f"期望被门禁拦截，实际={report.advance.status}；{report.render()}")
            gates = {g["gate_id"] for g in report.advance.failed_gates}
            self.assertIn("thinking_gate", gates)
            self.assertIn("workflow_contract", gates)
            # 状态确实没有前移
            self.assertEqual(report.trace.get("status"), "init_in_progress")
            # 不得出现由我们有产出的思考 trace（因为我们没做真实推理）
            self.assertFalse((Path(report.out_dir) / ".thinking_gate_trace.jsonl").exists(),
                             "不得伪造思考 trace 去凑状态前移")

    def test_产物落盘且标注为探测(self) -> None:
        with temp_workspace() as ws:
            report = run_handshake(self.settings, workspace=ws, step="plan")
            self.assertTrue(report.ok, report.render())
            plan = Path(report.out_dir) / "01_plan.md"
            self.assertTrue(plan.is_file(), "契约声明的产物必须落盘")
            text = plan.read_text(encoding="utf-8")
            self.assertTrue(text.startswith(PROBE_BANNER))
            self.assertIn("不得作为证据引用", text)

    def test_产物有_artifact_登记与哈希(self) -> None:
        with temp_workspace() as ws:
            report = run_handshake(self.settings, workspace=ws, step="plan")
            self.assertTrue(report.ok, report.render())
            events = Path(report.out_dir) / ".ico_events.jsonl"
            self.assertTrue(events.is_file())
            types = [json.loads(line)["event_type"] for line in
                     events.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertIn("ticket_created", types)
            self.assertIn("step_started", types)
            self.assertIn("artifact_written", types)
            self.assertIn("step_finished", types)

    def test_未知步骤给出明确失败而非异常(self) -> None:
        with temp_workspace() as ws:
            report = run_handshake(self.settings, workspace=ws, step="no_such_step")
            self.assertFalse(report.ok)
            self.assertFalse(report.error)

    def test_握手不触碰子模块工作树(self) -> None:
        """两仓独立：握手不得在 vendor/icode-skill 内留下任何改动。"""
        cp = ControlPlane(self.settings)
        dirty = cp.run(
            "-h", check=False
        )  # 触发一次子进程调用，确认控制面可执行
        self.assertIn(dirty.returncode, (0, 2))
        sub = self.settings.skill_root
        if (sub / ".." / ".." / ".gitmodules").exists():
            import subprocess

            out = subprocess.run(
                ["git", "-C", str(sub), "status", "--porcelain"],
                capture_output=True, text=True, encoding="utf-8", shell=False,
            )
            self.assertEqual(out.stdout.strip(), "", "子模块工作树被污染（两仓必须独立）")


if __name__ == "__main__":
    unittest.main()
