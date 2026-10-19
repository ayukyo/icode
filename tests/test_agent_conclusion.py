"""代理结论账本：缺身份/边界/证据即拒、digest 稳定、账本有界（R6/W4）。"""

import unittest

from icode.agent_conclusion import (
    AgentConclusion,
    ConclusionError,
    ConclusionLedger,
)
from icode.roles import RoleError


def _conclusion(**overrides):
    base = {
        "agent_id": "reviewer#ICODE-31#1",
        "role": "reviewer",
        "ticket_id": "ICODE-31",
        "step": "review",
        "kind": "review",
        "context_digest": "a" * 64,
        "outcome": "completed",
        "evidence": {"reviewed_files": 3, "finding_count": 0},
    }
    base.update(overrides)
    return AgentConclusion(**base)


class TestConclusionValidation(unittest.TestCase):
    def test_完整结论可入账且digest稳定(self) -> None:
        first = _conclusion()
        again = _conclusion()
        self.assertEqual(first.digest, again.digest)
        self.assertEqual(len(first.digest), 64)
        projection = first.project()
        self.assertEqual(projection["outcome"], "completed")
        self.assertEqual(projection["evidence"]["reviewed_files"], 3)

    def test_身份字段不一致拒绝(self) -> None:
        for overrides in ({"agent_id": "executor#ICODE-31#1"},
                          {"agent_id": "reviewer#ICODE-32#1"},
                          {"role": "executor"}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ConclusionError) as caught:
                    _conclusion(**overrides)
                self.assertEqual(caught.exception.code, "agent_id_mismatch")

    def test_结论类型必须落在角色职责内(self) -> None:
        with self.assertRaises(ConclusionError) as caught:
            _conclusion(kind="execution")
        self.assertEqual(caught.exception.code, "conclusion_out_of_role")

    def test_上下文边界必须是sha256(self) -> None:
        with self.assertRaises(ConclusionError) as caught:
            _conclusion(context_digest="self-reported-boundary")
        self.assertEqual(caught.exception.code, "invalid_context_digest")

    def test_completed结论必须有非空证据且值受限(self) -> None:
        with self.assertRaises(ConclusionError) as caught:
            _conclusion(evidence={})
        self.assertEqual(caught.exception.code, "evidence_missing")
        with self.assertRaises(ConclusionError) as caught:
            _conclusion(evidence={"blob": ["nested"]})
        self.assertEqual(caught.exception.code, "evidence_invalid")

    def test_failed结论必须有稳定失败码而不伪造证据(self) -> None:
        with self.assertRaises(ConclusionError) as caught:
            _conclusion(outcome="failed", evidence={}, detail="")
        self.assertEqual(caught.exception.code, "detail_missing")
        failed = _conclusion(outcome="failed", evidence={},
                             detail="agent_work_failed")
        self.assertEqual(failed.project()["evidence"], {})
        self.assertEqual(failed.project()["detail"], "agent_work_failed")

    def test_未知结论状态拒绝(self) -> None:
        with self.assertRaises(ConclusionError) as caught:
            _conclusion(outcome="escaped")
        self.assertEqual(caught.exception.code, "invalid_outcome")

    def test_非法身份形态拒绝(self) -> None:
        with self.assertRaises(RoleError) as caught:
            _conclusion(agent_id="not-an-id")
        self.assertEqual(caught.exception.code, "invalid_agent_id")


class TestConclusionLedger(unittest.TestCase):
    def test_只增有界写满即拒(self) -> None:
        ledger = ConclusionLedger(limit=2)
        ledger.record(_conclusion())
        ledger.record(_conclusion(step="deepcheck"))
        with self.assertRaises(ConclusionError) as caught:
            ledger.record(_conclusion(step="audit"))
        self.assertEqual(caught.exception.code, "ledger_full")
        self.assertEqual(len(ledger.conclusions()), 2)

    def test_幂等重录同digest不重复占位(self) -> None:
        ledger = ConclusionLedger(limit=2)
        first = ledger.record(_conclusion())
        again = ledger.record(_conclusion())
        self.assertEqual(first, again)
        self.assertEqual(len(ledger.conclusions()), 1)

    def test_门禁查询按角色与步骤过滤(self) -> None:
        ledger = ConclusionLedger()
        ledger.record(_conclusion())
        self.assertTrue(ledger.has_completed("reviewer", "review", "review"))
        self.assertFalse(ledger.has_completed("reviewer", "review", "deepcheck"))
        self.assertFalse(ledger.has_completed("executor", "execution", "review"))

    def test_非结论对象拒绝(self) -> None:
        ledger = ConclusionLedger()
        with self.assertRaises(ConclusionError) as caught:
            ledger.record({"digest": "fake"})
        self.assertEqual(caught.exception.code, "invalid_conclusion")


if __name__ == "__main__":
    unittest.main()
