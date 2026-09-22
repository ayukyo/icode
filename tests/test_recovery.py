"""韧性测试（Phase 4 核心验收）。

两类崩溃演练（roadmap Phase 4 验收项）：
    ① **写到一半中断** —— 循环中途挂掉，进度留下；恢复后能继续完成，且不重复登记产物
    ② **副作用已发出但回执未知** —— 恢复必须**拒绝自动继续**，要求先核对真实状态

另有若干判定规则测试，重点是两条不可妥协的原则：
    - **真源是事件链，不是检查点**（冲突时事件链优先）
    - **检查点不保存模型正文**
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from tests._support import make_finished_plan_ticket, require_skill, temp_workspace

from icode.approvals import DenyAllApprover
from icode.backends import FakeBackend
from icode.checkpoint import CHECKPOINT_NAME, Checkpointer
from icode.control import ControlPlane
from icode.guard import Guard, Scope
from icode.loop import AgentLoop, LoopConfig
from icode.operations import OperationRecorder
from icode.recovery import (
    ACTION_BLOCKED,
    ACTION_RESUME,
    ACTION_START_FRESH,
    ACTION_VERIFY_SIDE_EFFECT,
    Recoverer,
)
from icode.tools import ToolContext, default_registry


def _open_plan_step(cp, workspace: Path, ticket_id: str = "RC-1") -> Path:
    """造一条"plan 已 start 但未 finish"的工单（步骤处于打开状态）。"""
    from icode.handshake import next_out_dir

    out_dir = next_out_dir(workspace)
    cp.create(out_dir, ticket_id=ticket_id, requirement="韧性测试", birth="plan")
    cp.step_start(out_dir, "plan", ticket_id=ticket_id)  # 故意不 finish
    return out_dir


def _count_events(out_dir: Path, event_type: str) -> int:
    path = out_dir / ".ico_events.jsonl"
    if not path.is_file():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and json.loads(line).get("event_type") == event_type:
            n += 1
    return n


class TestCheckpoint(unittest.TestCase):
    """检查点本体：原子写、不含正文、可清理。"""

    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.ws: Path = self._ws.__enter__()
        self.ck = Checkpointer(self.ws, ticket_id="T-1", step="plan", attempt="step-a")

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_保存后可读且无临时文件残留(self) -> None:
        self.ck.save(turn_index=3, tool_calls=7, history=[{"role": "user", "content": "x"}])
        self.assertTrue(self.ck.exists())
        state = self.ck.load()
        assert state is not None
        self.assertEqual(state.turn_index, 3)
        self.assertEqual(state.tool_calls, 7)
        self.assertEqual(state.attempt, "step-a")
        self.assertEqual(list(self.ws.glob("*.tmp")), [], "原子写不应留下 .tmp")

    def test_不保存模型正文(self) -> None:
        """安全底线：检查点只存进度，模型对话内容绝不落盘。"""
        secret_text = "这段是模型正文，绝不该出现在检查点里"
        self.ck.save(turn_index=1, tool_calls=1, history=[
            {"role": "assistant", "content": secret_text},
            {"role": "tool", "content": "tool output " + secret_text},
        ])
        raw = (self.ws / CHECKPOINT_NAME).read_text(encoding="utf-8")
        self.assertNotIn(secret_text, raw, "检查点泄漏了模型正文")
        data = json.loads(raw)
        self.assertIn("history_digest", data)
        self.assertNotIn("messages", json.dumps(data))
        self.assertNotIn("history", data)

    def test_同一历史得到同一摘要_不同历史不同摘要(self) -> None:
        h1 = [{"role": "user", "content": "a"}]
        h2 = [{"role": "user", "content": "b"}]
        s1 = self.ck.save(turn_index=1, tool_calls=0, history=h1)
        s2 = self.ck.save(turn_index=1, tool_calls=0, history=h2)
        self.assertNotEqual(s1.history_digest, s2.history_digest)
        s3 = self.ck.save(turn_index=1, tool_calls=0, history=h1)
        self.assertEqual(s1.history_digest, s3.history_digest)

    def test_清理(self) -> None:
        self.ck.save(turn_index=1, tool_calls=0, history=[])
        self.ck.clear()
        self.assertFalse(self.ck.exists())
        self.ck.clear()  # 幂等


class TestRecoveryDecision(unittest.TestCase):
    """恢复判定规则。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.ws: Path = self._ws.__enter__()
        self.cp = ControlPlane(self.settings)

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_干净工单判定为_start_fresh(self) -> None:
        out_dir = make_finished_plan_ticket(self.settings, self.ws)
        decision = Recoverer(self.cp, out_dir, "EV-1").analyze("plan")
        self.assertEqual(decision.action, ACTION_START_FRESH)
        self.assertTrue(decision.can_resume)
        self.assertFalse(decision.needs_human)

    def test_未闭合步骤判定为_resume(self) -> None:
        out_dir = _open_plan_step(self.cp, self.ws)
        decision = Recoverer(self.cp, out_dir, "RC-1").analyze("plan")
        self.assertEqual(decision.action, ACTION_RESUME)
        self.assertTrue(decision.open_steps)
        self.assertTrue(decision.can_resume)

    def test_未终结副作用判定为_verify_side_effect_first(self) -> None:
        out_dir = _open_plan_step(self.cp, self.ws, "RC-2")
        rec = OperationRecorder(self.cp, out_dir, "RC-2")
        started = rec.start(name="write-report", opclass="managed_write", input_desc="x")
        self.assertTrue(started.can_execute)
        # 故意不 finish —— 模拟"副作用已发出但回执未知"

        decision = Recoverer(self.cp, out_dir, "RC-2").analyze("plan")
        self.assertEqual(decision.action, ACTION_VERIFY_SIDE_EFFECT)
        self.assertTrue(decision.needs_human)
        self.assertFalse(decision.can_resume)
        self.assertEqual(len(decision.side_effect_operations), 1)
        self.assertIn("禁止直接重放", decision.reason)

    def test_只读未闭合动作不阻断恢复(self) -> None:
        out_dir = _open_plan_step(self.cp, self.ws, "RC-3")
        rec = OperationRecorder(self.cp, out_dir, "RC-3")
        rec.start(name="fetch-remote", opclass="read_only", input_desc="y")
        decision = Recoverer(self.cp, out_dir, "RC-3").analyze("plan")
        self.assertEqual(decision.action, ACTION_RESUME)
        self.assertFalse(decision.needs_human)

    def test_未知类别按副作用处理_fail_safe(self) -> None:
        """类别判不出来时必须走更严格的一侧——误判为只读会导致重放副作用。"""
        from icode.recovery import _classify_open_operations

        side, read_only = _classify_open_operations({"a1": {"name": "x"}})
        self.assertEqual(len(side), 1)
        self.assertEqual(read_only, [])
        side2, _ = _classify_open_operations({"a2": {"class": "weird_new_class"}})
        self.assertEqual(len(side2), 1)

    def test_事件链不可读时判定为_blocked(self) -> None:
        out_dir = self.ws / "not_a_ticket"
        out_dir.mkdir()
        decision = Recoverer(self.cp, out_dir, "NOPE").analyze("plan")
        self.assertEqual(decision.action, ACTION_BLOCKED)
        self.assertTrue(decision.needs_human)

    def test_检查点与事件链冲突时事件链优先(self) -> None:
        """检查点声称 attempt=X，但事件链上没有该未闭合步骤 → 丢弃检查点。"""
        out_dir = _open_plan_step(self.cp, self.ws, "RC-4")
        stale = Checkpointer(out_dir, ticket_id="RC-4", step="plan", attempt="step-不存在的attempt")
        stale.save(turn_index=9, tool_calls=9, history=[])
        decision = Recoverer(self.cp, out_dir, "RC-4").analyze("plan", checkpointer=stale)
        self.assertFalse(decision.checkpoint_valid)
        self.assertTrue(any("丢弃检查点" in w for w in decision.warnings), decision.warnings)
        self.assertFalse(stale.exists(), "失效检查点应被清除")

    def test_检查点归属其它工单时忽略(self) -> None:
        out_dir = _open_plan_step(self.cp, self.ws, "RC-5")
        foreign = Checkpointer(out_dir, ticket_id="OTHER", step="plan", attempt="x")
        foreign.save(turn_index=1, tool_calls=0, history=[])
        decision = Recoverer(self.cp, out_dir, "RC-5").analyze("plan", checkpointer=foreign)
        self.assertFalse(decision.checkpoint_valid)
        self.assertTrue(any("其它工单" in w for w in decision.warnings), decision.warnings)

    def test_未决审批在恢复提示中被明确要求重新确认(self) -> None:
        out_dir = _open_plan_step(self.cp, self.ws, "RC-6")
        ck = Checkpointer(out_dir, ticket_id="RC-6", step="plan", attempt="x")
        # 用真实 attempt 写检查点
        attempt = self.cp.step_start(out_dir, "plan", ticket_id="RC-6")
        ck2 = Checkpointer(out_dir, ticket_id="RC-6", step="plan", attempt=attempt)
        ck2.save(turn_index=2, tool_calls=3, history=[], pending_approvals=1)
        decision = Recoverer(self.cp, out_dir, "RC-6").analyze("plan", checkpointer=ck2)
        self.assertTrue(decision.checkpoint_valid)
        self.assertTrue(any("不自动放行" in w for w in decision.warnings), decision.warnings)
        self.assertIn("不会自动放行", decision.resume_brief())
        ck.clear()


class TestCrashDrills(unittest.TestCase):
    """两类崩溃演练。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.ws: Path = self._ws.__enter__()
        self.cp = ControlPlane(self.settings)

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def _open_step(self, ticket_id: str) -> tuple[Path, str]:
        from icode.handshake import next_out_dir

        out_dir = next_out_dir(self.ws)
        self.cp.create(out_dir, ticket_id=ticket_id, requirement="演练", birth="plan")
        attempt = self.cp.step_start(out_dir, "plan", ticket_id=ticket_id)
        return out_dir, attempt

    def _loop(self, out_dir: Path, ticket_id: str, script: list[Any], ck: Checkpointer | None):
        return AgentLoop(
            backend=FakeBackend(script),
            registry=default_registry(),
            guard=Guard(Scope(workspace_root=self.ws)),
            ctx=ToolContext(root=self.ws),
            approver=DenyAllApprover(),
            operations=OperationRecorder(self.cp, out_dir, ticket_id),
            config=LoopConfig(max_turns=6, max_tool_calls_per_turn=1),
            on_turn=(None if ck is None else (
                lambda t, c, h: ck.save(turn_index=t, tool_calls=c, history=h)
            )),
        )

    # ---- 演练①：写到一半中断 ----

    def test_演练1_写到一半中断后能恢复且不重复登记产物(self) -> None:
        ticket_id = "DRILL-1"
        out_dir, attempt = self._open_step(ticket_id)
        ck = Checkpointer(out_dir, ticket_id=ticket_id, step="plan", attempt=attempt)

        # 第一回合写产物；第二回合后端"崩溃"
        # 产物必须落在工单目录内（真实运行时提示词给的就是绝对路径）
        deliverable = str(out_dir / "01_plan.md")
        write_call = {"content": "", "tool_calls": [
            {"id": "c1", "name": "write_file",
             "arguments": {"path": deliverable, "content": "# 半成品计划\n"}}
        ]}

        class _Boom:
            name = "boom"

            def __init__(self) -> None:
                self.n = 0

            def complete(self, *a, **kw):
                self.n += 1
                if self.n == 1:
                    return FakeBackend([write_call]).complete(*a, **kw)
                raise RuntimeError("进程模拟中断")

        loop = AgentLoop(
            backend=_Boom(),  # type: ignore[arg-type]
            registry=default_registry(),
            guard=Guard(Scope(workspace_root=self.ws)),
            ctx=ToolContext(root=self.ws),
            config=LoopConfig(max_turns=6, max_tool_calls_per_turn=1),
            on_turn=lambda t, c, h: ck.save(turn_index=t, tool_calls=c, history=h),
        )
        result = loop.run([{"role": "user", "content": "写计划"}])
        self.assertFalse(result.ok)
        self.assertEqual(result.stop_reason, "backend_error")

        # 中断后：工单侧步骤仍未闭合，检查点留下进度
        self.assertTrue(ck.exists(), "中断后应留下检查点")
        state = ck.load()
        assert state is not None
        self.assertGreaterEqual(state.turn_index, 1)
        self.assertEqual(_count_events(out_dir, "step_finished"), 0, "步骤不应已终结")
        self.assertEqual(_count_events(out_dir, "artifact_written"), 0, "中断前未登记产物")

        # 恢复分析：应判定可继续
        decision = Recoverer(self.cp, out_dir, ticket_id).analyze("plan", checkpointer=ck)
        self.assertEqual(decision.action, ACTION_RESUME)
        self.assertTrue(decision.checkpoint_valid)
        self.assertIn(attempt, decision.resume_brief())

        # 继续跑（模拟恢复后的新进程）：补齐产物并终结
        resumed = self._loop(out_dir, ticket_id, [write_call, "完成"], ck)
        resumed_result = resumed.run([
            {"role": "system", "content": decision.resume_brief()},
            {"role": "user", "content": "继续"},
        ])
        self.assertTrue(resumed_result.ok, resumed_result.render())

        # 恢复后的收尾：按契约顺序复检 → 登记产物 → 复检 → 终结
        self.cp.step_check(out_dir, "plan", attempt, "before_write",
                           ticket_id=ticket_id, occurrence=1)
        art = self.cp.artifact(out_dir, "plan", attempt, "01_plan.md", ticket_id=ticket_id)
        self.assertTrue(art.data.get("ok") is True)
        self.cp.step_check(out_dir, "plan", attempt, "before_transition",
                           ticket_id=ticket_id, occurrence=2)
        fin = self.cp.step_finish(out_dir, "plan", attempt, "success",
                                  ticket_id=ticket_id, evidence=["drill"], check=False)
        self.assertEqual(fin.data.get("outcome"), "success",
                         f"终结回执失败：{fin.data.get('error') or fin.data}")
        ck.clear()

        # 关键不变量：产物**只登记一次**
        self.assertEqual(_count_events(out_dir, "artifact_written"), 1)
        self.assertEqual(_count_events(out_dir, "step_finished"), 1)
        self.assertFalse(ck.exists())

    # ---- 演练②：副作用已发出但回执未知 ----

    def test_演练2_副作用回执未知时拒绝自动恢复_核对后放行(self) -> None:
        ticket_id = "DRILL-2"
        out_dir, _attempt = self._open_step(ticket_id)

        rec = OperationRecorder(self.cp, out_dir, ticket_id)
        started = rec.start(name="publish", opclass="external_side_effect", input_desc="payload")
        self.assertTrue(started.can_execute)
        # 进程在此"死亡"——没有 finish

        recoverer = Recoverer(self.cp, out_dir, ticket_id)
        decision = recoverer.analyze("plan")
        self.assertEqual(decision.action, ACTION_VERIFY_SIDE_EFFECT)
        self.assertTrue(decision.needs_human)
        self.assertIn("禁止直接重放", decision.reason)
        self.assertIn("禁止重放", decision.resume_brief())

        # 人工核对真实状态后，用原 attempt 补 finish（这是上游规定的正确收尾）
        ok = recoverer.resolve_open_operation(
            started.attempt or "",
            outcome="success",
            evidence="drill:verified-external",
            check_ref="人工核对：远端已收到该次发布",
        )
        self.assertTrue(ok, "核对后补 finish 应成功")

        # 再分析：副作用已闭合 → 不再阻断
        after = recoverer.analyze("plan")
        self.assertNotEqual(after.action, ACTION_VERIFY_SIDE_EFFECT)
        self.assertTrue(after.can_resume)

    def test_不同步骤的回执键不得冲突(self) -> None:
        """回归：request 键若不含步骤，plan 与 review 的第 1 次同名工具调用
        会生成同一个幂等键，而 payload（input_desc）不同 → 上游判冲突。
        实测整条链路因此走不动（第二个步骤的所有命令被误拒）。
        """
        from icode.control import make_request
        from icode.operations import OperationRecorder

        # 键必须按 scope 区分
        k1 = make_request("T-1", "op-plan-tool:write_file-start", occurrence=1)
        k2 = make_request("T-1", "op-review-tool:write_file-start", occurrence=1)
        self.assertNotEqual(k1, k2)

        # 不同 scope 的同名工具调用， occurrence 相同 → request 键必须不同
        out_dir = _open_plan_step(self.cp, self.ws, "T-1")
        r1 = OperationRecorder(self.cp, out_dir, "T-1", scope="plan")
        r2 = OperationRecorder(self.cp, out_dir, "T-1", scope="review")
        a1 = r1.start(name="tool:write_file", opclass="managed_write", input_desc="plan 写")
        self.assertTrue(a1.ok, a1.detail)
        self.assertTrue(r1.finish(a1.attempt or "", outcome="success",
                                  evidence="t", check_ref="ok"),
                        "第一个动作应能正常终结")
        # 注意：必须先终结第一个（上游按 name 拒绝同名未终结动作，这是正确行为）
        a2 = r2.start(name="tool:write_file", opclass="managed_write", input_desc="review 写")
        self.assertTrue(a2.ok, f"第二个步骤的副作用被误拒：{a2.detail}")
        self.assertNotEqual(a1.attempt, a2.attempt)

    def test_演练2b_未核对时再次尝试同名副作用会被控制面拦下(self) -> None:
        """禁止盲重放的机制验证：同名副作用只有 start 无 finish，再 start 必须报歧义。"""
        ticket_id = "DRILL-3"
        out_dir, _attempt = self._open_step(ticket_id)
        rec = OperationRecorder(self.cp, out_dir, ticket_id)
        first = rec.start(name="do-once", opclass="managed_write", input_desc="v1")
        self.assertTrue(first.can_execute)

        second = rec.start(name="do-once", opclass="managed_write", input_desc="v1-again")
        self.assertFalse(second.can_execute, "未终结的副作用不得再次执行")
        self.assertTrue(second.ambiguous or not second.ok)


if __name__ == "__main__":
    unittest.main()
