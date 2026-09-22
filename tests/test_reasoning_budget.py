"""推理门禁与预算测试（离线）。

重点验证**诚实性**：能力不足的等级必须写 degraded，不得冒充成功。
"""

from __future__ import annotations

import json
import unittest

from tests._support import require_skill, temp_workspace

from icode.approvals import CliApprover, DenyAllApprover, ScriptedApprover
from icode.backends import Usage
from icode.budget import Budget, BudgetTracker
from icode.reasoning import TRACE_FILENAME, ReasoningGate, TraceRow, append_trace, read_trace


class TestReasoningGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()
        cls.gate = ReasoningGate.load(
            cls.settings.skill_root / "mcp" / "reasoning-gate" / "gates.json"
        )

    def test_真源可读且含等级表(self) -> None:
        self.assertTrue(self.gate.steps())
        self.assertEqual(self.gate.mechanisms_by_tier.get("L2"), "sequential-thinking")

    def test_plan_是_L2_且需要_trace(self) -> None:
        info = self.gate.for_step("plan")
        self.assertIsNotNone(info)
        self.assertEqual(info.default_tier, "L2")
        self.assertTrue(info.requires_trace)

    def test_能力不足的等级如实标_degraded(self) -> None:
        row = self.gate.build_row("T-1", "plan")
        self.assertIsNotNone(row)
        self.assertEqual(row.tier, "L2")
        self.assertEqual(row.mechanism, "sequential-thinking")
        self.assertFalse(row.attempted, "未接入 sequential-thinking 时不得声称 attempted")
        self.assertEqual(row.result, "degraded")
        self.assertTrue(row.degraded_reason)

    def test_不需要_trace_的步骤不写行(self) -> None:
        info = self.gate.for_step("status")
        if info is not None and not info.requires_trace:
            self.assertIsNone(self.gate.build_row("T-1", "status"))

    def test_不满足的步骤可枚举(self) -> None:
        """L2 已由本仓自实现提供；未实现的等级（如 L3）仍应被如实列出。"""
        unsatisfied = {s.step for s in self.gate.unsatisfied_steps()}
        self.assertNotIn("plan", unsatisfied, "plan 是 L2，已具备自实现能力")
        for step in unsatisfied:
            info = self.gate.for_step(step)
            assert info is not None
            self.assertNotIn(info.default_tier, ("L0", "L1", "L2"))

    def test_写读_trace_往返一致(self) -> None:
        with temp_workspace() as ws:
            path = ws / TRACE_FILENAME
            row = TraceRow(ticket_id="T-9", step="plan", tier="L2", default_tier="L2",
                           mechanism="sequential-thinking", attempted=False,
                           result="degraded", degraded_reason="未接入")
            append_trace(path, [row])
            append_trace(path, [row])
            rows = read_trace(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["ticket_id"], "T-9")
            # 字段严格对齐上游 schema
            expected = {"schema_version", "ticket_id", "step", "tier", "default_tier",
                        "triggers", "mechanism", "attempted", "result", "degraded_reason",
                        "over_invoked", "at",
                        # 额外字段：如实记录机制由谁提供（上游只检必需键）
                        "provider", "provider_kind", "deliberation_steps", "deliberation_digest"}
            self.assertEqual(set(rows[0]), expected)
            self.assertIn("at", json.dumps(rows[0]))
            # LF 结尾
            self.assertNotIn(b"\r\n", path.read_bytes())


class TestDeliberationGate(unittest.TestCase):
    """L2 门禁的诚实性：**真跑过才给成功**。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()
        cls.gate = ReasoningGate.load(
            cls.settings.skill_root / "mcp" / "reasoning-gate" / "gates.json")

    def test_真跑推演才给成功(self) -> None:
        from icode.sequential import Deliberation

        d = Deliberation(tier="L2", steps=["第一步", "第二步", "第三步"], converged=True)
        row = self.gate.build_row("T-1", "plan", deliberation=d)
        assert row is not None
        self.assertTrue(row.attempted)
        self.assertEqual(row.result, "success")
        self.assertIsNone(row.degraded_reason)
        self.assertEqual(row.provider_kind, "in_repo")
        self.assertEqual(row.provider, "icode-in-repo-sequential-thinking")
        self.assertEqual(row.deliberation_steps, 3)
        self.assertTrue(row.deliberation_digest)

    def test_推演步数不足时如实降级(self) -> None:
        from icode.sequential import Deliberation

        d = Deliberation(tier="L2", steps=["只有一步"], converged=True)
        row = self.gate.build_row("T-1", "plan", deliberation=d)
        assert row is not None
        self.assertFalse(row.attempted)
        self.assertEqual(row.result, "degraded")
        self.assertIn("未取得有效推演", row.degraded_reason or "")

    def test_没给推演结果时不得报成功(self) -> None:
        row = self.gate.build_row("T-1", "plan")
        assert row is not None
        self.assertFalse(row.attempted)
        self.assertEqual(row.result, "degraded")

    def test_推演不落正文只记摘要(self) -> None:
        from icode.sequential import Deliberation

        d = Deliberation(tier="L2", steps=["敏感推演正文 A", "敏感推演正文 B", "敏感推演正文 C"])
        row = self.gate.build_row("T-1", "plan", deliberation=d)
        assert row is not None
        blob = json.dumps(row.as_dict(), ensure_ascii=False)
        self.assertNotIn("敏感推演正文", blob, "推演正文不得进入 trace")
        self.assertLess(len(blob), 4096, "trace 行必须在上游上限内")


class TestBudget(unittest.TestCase):
    def test_预算判定分级(self) -> None:
        b = Budget(expected_tokens=100, hard_ratio=3.0)
        self.assertEqual(b.verdict(Usage(total_tokens=50)), "within_budget")
        self.assertEqual(b.verdict(Usage(total_tokens=200)), "above_expected")
        self.assertEqual(b.verdict(Usage(total_tokens=500)), "over_budget")

    def test_无预算时只观测(self) -> None:
        b = Budget(expected_tokens=0)
        self.assertEqual(b.verdict(Usage(total_tokens=10_000)), "observe_only")

    def test_累计用量与报告(self) -> None:
        t = BudgetTracker(budget=Budget(expected_tokens=100))
        t.record(Usage(total_tokens=30, prompt_tokens=20, completion_tokens=10))
        t.record(Usage(total_tokens=40, prompt_tokens=25, completion_tokens=15))
        report = t.report()
        self.assertEqual(report["calls"], 2)
        self.assertEqual(report["total_tokens"], 70)
        self.assertEqual(report["verdict"], "within_budget")
        self.assertIn("tokens", t.render())


class TestApprovers(unittest.TestCase):
    def _req(self):
        from icode.approvals import ApprovalRequest

        return ApprovalRequest(tool="run_command", arguments={"argv": ["x"]},
                               reason="不在白名单", opclass="managed_write", workspace="/tmp")

    def test_默认审批者一律拒绝(self) -> None:
        self.assertFalse(DenyAllApprover().ask(self._req()))

    def test_脚本审批者按序作答(self) -> None:
        a = ScriptedApprover(answers=[True, False])
        self.assertTrue(a.ask(self._req()))
        self.assertFalse(a.ask(self._req()))
        self.assertFalse(a.ask(self._req()))  # 用完后走 default

    def test_CLI_审批者默认回车即拒绝(self) -> None:
        from unittest import mock

        with mock.patch("builtins.input", return_value=""):
            self.assertFalse(CliApprover(stream=open(__import__("os").devnull, "w")).ask(self._req()))
        with mock.patch("builtins.input", return_value="y"):
            self.assertTrue(CliApprover(stream=open(__import__("os").devnull, "w")).ask(self._req()))

    def test_CLI_审批者遇中断视为拒绝(self) -> None:
        from unittest import mock

        import os

        with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            self.assertFalse(CliApprover(stream=open(os.devnull, "w")).ask(self._req()))


if __name__ == "__main__":
    unittest.main()
