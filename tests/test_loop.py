"""Agent 回合循环 + 审批协议 + 副作用回执测试（全部离线）。

用 FakeBackend 回放工具调用，验证：
- 权限判定（拒绝 / 需审批）真的生效
- 审批默认拒绝、显式放行才继续
- 写动作会留下 operation 回执；副作用歧义时**拒绝执行**
- 有界：回合数上限、预算闸门
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from tests._support import temp_workspace

from icode.approvals import ApprovalRequest, DenyAllApprover, ScriptedApprover
from icode.artifact_broker import ArtifactBroker
from icode.backends import FakeBackend
from icode.budget import Budget, BudgetTracker
from icode.contracts import Port, StepContract
from icode.guard import Decision, Guard, Scope
from icode.loop import AgentLoop, LoopConfig
from icode.operations import StartedOperation
from icode.tools import ToolContext, default_registry


class _StubOps:
    """记录 start/finish 调用的假回执器（不依赖控制面）。"""

    def __init__(self, *, ambiguous: bool = False) -> None:
        self.started: list[dict] = []
        self.finished: list[dict] = []
        self.ambiguous = ambiguous

    def start(self, *, name: str, opclass: str, input_desc: str) -> StartedOperation:
        self.started.append({"name": name, "opclass": opclass,
                             "input_desc": input_desc})
        return StartedOperation(
            name=name, opclass=opclass,
            attempt=None if self.ambiguous else f"op-{len(self.started)}",
            ok=not self.ambiguous, ambiguous=self.ambiguous,
            detail="ambiguous_side_effect" if self.ambiguous else "",
        )

    def finish(self, attempt: str, *, outcome: str, evidence: str, check_ref: str,
               failure: str | None = None) -> bool:
        self.finished.append({"attempt": attempt, "outcome": outcome})
        return True


def _loop(script: list[Any], root: Path, *, approver=None, ops=None,
          config: LoopConfig | None = None, budget: BudgetTracker | None = None) -> AgentLoop:
    return AgentLoop(
        backend=FakeBackend(script),
        registry=default_registry(),
        guard=Guard(Scope(workspace_root=root)),
        ctx=ToolContext(root=root),
        approver=approver or DenyAllApprover(),
        operations=ops,  # type: ignore[arg-type]
        budget=budget or BudgetTracker(),
        config=config or LoopConfig(max_turns=4, max_tool_calls_per_turn=2),
    )


def _write_call(path: str, content: str = "x = 1\n", call_id: str = "c1") -> dict:
    return {"content": "", "tool_calls": [
        {"id": call_id, "name": "write_file", "arguments": {"path": path, "content": content}}
    ]}


class TestLoopGuards(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root: Path = self._ws.__enter__()

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_无工具调用即正常结束(self) -> None:
        loop = _loop(["任务完成"], self.root)
        r = loop.run([{"role": "user", "content": "hi"}])
        self.assertTrue(r.ok)
        self.assertEqual(r.stop_reason, "no_tool_calls")
        self.assertEqual(r.tool_calls, 0)

    def test_受控产物端口不依赖工作区读取授权(self) -> None:
        out_dir = self.root / "ticket"
        out_dir.mkdir()
        broker = ArtifactBroker(out_dir, StepContract(
            step="plan", outputs=(Port("plan", "ticket_file", "01_plan.md"),),
        ), max_bytes=1024)
        loop = _loop(["完成"], self.root)
        loop.ctx.artifact_broker = broker
        loop.guard = Guard(Scope(
            workspace_root=self.root, allowed_read_roots=(),
        ))
        self.assertEqual(loop._decide("submit_artifact", {"name": "01_plan.md"}).decision,
                         Decision.ALLOW)

    def test_工作区内写入被放行(self) -> None:
        loop = _loop([_write_call("a.py"), "完成"], self.root)
        r = loop.run([{"role": "user", "content": "写文件"}])
        self.assertTrue(r.ok)
        self.assertTrue((self.root / "a.py").is_file())
        self.assertEqual(r.turns[0].invocations[0].decision, "allow")

    def test_工作区外写入被拒绝且未落盘(self) -> None:
        outside = self.root.parent / "icode_escape_probe.py"
        loop = _loop([_write_call(str(outside)), "完成"], self.root)
        r = loop.run([{"role": "user", "content": "写外部文件"}])
        self.assertEqual(r.turns[0].invocations[0].decision, "deny")
        self.assertFalse(outside.exists())

    def test_危险命令被拒绝(self) -> None:
        script = [{"content": "", "tool_calls": [
            {"id": "c1", "name": "run_command", "arguments": {"argv": ["rm", "-rf", "/"]}}
        ]}, "完成"]
        loop = _loop(script, self.root)
        r = loop.run([{"role": "user", "content": "删除"}])
        inv = r.turns[0].invocations[0]
        self.assertEqual(inv.decision, "deny")
        self.assertIn("危险模式", inv.note)

    def test_需审批的动作默认被拒(self) -> None:
        script = [{"content": "", "tool_calls": [
            {"id": "c1", "name": "run_command", "arguments": {"argv": ["unknown-tool"]}}
        ]}, "完成"]
        loop = _loop(script, self.root)  # 默认 DenyAllApprover
        r = loop.run([{"role": "user", "content": "跑个未知命令"}])
        inv = r.turns[0].invocations[0]
        self.assertEqual(inv.decision, "require_approval")
        self.assertFalse(inv.approved)
        self.assertEqual(inv.result.meta["error"], "not_approved")

    def test_显式放行后才执行(self) -> None:
        script = [{"content": "", "tool_calls": [
            {"id": "c1", "name": "run_command", "arguments": {"argv": ["unknown-tool"]}}
        ]}, "完成"]
        approver = ScriptedApprover(answers=[True])
        loop = _loop(script, self.root, approver=approver)
        r = loop.run([{"role": "user", "content": "跑"}])
        self.assertTrue(r.turns[0].invocations[0].approved)
        self.assertEqual(len(approver.seen), 1)
        self.assertIsInstance(approver.seen[0], ApprovalRequest)

    def test_未知工具被如实报错(self) -> None:
        script = [{"content": "", "tool_calls": [
            {"id": "c1", "name": "no_such_tool", "arguments": {}}
        ]}, "完成"]
        r = _loop(script, self.root).run([{"role": "user", "content": "x"}])
        self.assertIn("工具不存在", r.turns[0].invocations[0].note)


class TestSideEffectReceipts(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root: Path = self._ws.__enter__()

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_写动作留下_start_finish_回执(self) -> None:
        ops = _StubOps()
        loop = _loop([_write_call("a.py"), "完成"], self.root, ops=ops)
        loop.run([{"role": "user", "content": "写"}])
        self.assertEqual(len(ops.started), 1)
        self.assertEqual(ops.started[0]["opclass"], "managed_write")
        self.assertEqual(len(ops.finished), 1)
        self.assertEqual(ops.finished[0]["outcome"], "success")

    def test_工具正文不进入操作回执或公开事件(self) -> None:
        secret = "private-content-never-in-receipt"
        ops = _StubOps()
        events: list[dict] = []
        loop = _loop([_write_call("a.py", secret), "完成"], self.root, ops=ops)
        loop.on_event = lambda kind, payload: events.append({"kind": kind, **payload})
        loop.run([{"role": "user", "content": "写"}])
        self.assertNotIn(secret, ops.started[0]["input_desc"])
        self.assertIn("args_sha256", ops.started[0]["input_desc"])
        self.assertNotIn(secret, str(events))

    def test_只读动作不产生回执(self) -> None:
        ops = _StubOps()
        script = [{"content": "", "tool_calls": [
            {"id": "c1", "name": "glob", "arguments": {"pattern": "*.py"}}
        ]}, "完成"]
        loop = _loop(script, self.root, ops=ops)
        loop.run([{"role": "user", "content": "列文件"}])
        self.assertEqual(ops.started, [])

    def test_副作用歧义时拒绝执行(self) -> None:
        ops = _StubOps(ambiguous=True)
        loop = _loop([_write_call("a.py"), "完成"], self.root, ops=ops)
        r = loop.run([{"role": "user", "content": "写"}])
        inv = r.turns[0].invocations[0]
        self.assertFalse(inv.approved)
        self.assertEqual(inv.result.meta["error"], "ambiguous_side_effect")
        self.assertFalse((self.root / "a.py").exists(), "歧义时必须停止执行，禁止盲目重放")


class TestToolCallPairing(unittest.TestCase):
    """协议不变量：assistant 里每个 tool_call 必须有配对的 tool 消息。

    回归背景：单回合工具调用数超上限时，我们曾把多余的调用**直接丢掉**，
    于是发给模型的 assistant 消息列着 5 个 tool_calls 却只有 4 条结果，
    OpenAI 兼容端点直接返回 HTTP 400 invalid params。真实链路跑出来的坑。
    """

    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root: Path = self._ws.__enter__()

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def _many(self, n: int) -> dict:
        return {"content": "", "tool_calls": [
            {"id": f"c{i}", "name": "write_file",
             "arguments": {"path": f"f{i}.py", "content": "x"}}
            for i in range(n)
        ]}

    def test_超上限的调用也有配对结果(self) -> None:
        loop = _loop([self._many(5), "完成"], self.root,
                     config=LoopConfig(max_turns=2, max_tool_calls_per_turn=2))
        r = loop.run([{"role": "user", "content": "写 5 个文件"}])

        assistant = next(m for m in r.messages if m.get("role") == "assistant")
        tool_ids = {m["tool_call_id"] for m in r.messages if m.get("role") == "tool"}
        declared = {c["id"] for c in assistant["tool_calls"]}
        self.assertEqual(declared, tool_ids, "每个 tool_call 必须有配对 tool 消息")
        self.assertEqual(len(declared), 5)

    def test_未执行的调用如实标注未执行(self) -> None:
        loop = _loop([self._many(3), "完成"], self.root,
                     config=LoopConfig(max_turns=2, max_tool_calls_per_turn=1))
        r = loop.run([{"role": "user", "content": "写 3 个文件"}])
        skipped = [i for i in r.turns[0].invocations if i.result and
                   i.result.meta.get("error") == "turn_tool_budget"]
        self.assertEqual(len(skipped), 2)
        for inv in skipped:
            self.assertIn("未执行", inv.result.content)
        # 未执行的不能落盘
        self.assertTrue((self.root / "f0.py").is_file())
        self.assertFalse((self.root / "f1.py").exists())


class TestLoopBounds(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root: Path = self._ws.__enter__()

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_到达回合上限即停止(self) -> None:
        script = [_write_call(f"f{i}.py", call_id=f"c{i}") for i in range(6)]
        loop = _loop(script, self.root, config=LoopConfig(max_turns=3, max_tool_calls_per_turn=1))
        r = loop.run([{"role": "user", "content": "一直写"}])
        self.assertFalse(r.ok)
        self.assertEqual(r.stop_reason, "max_turns")
        self.assertEqual(len(r.turns), 3)

    def test_单回合工具调用数受上限约束(self) -> None:
        many = {"content": "", "tool_calls": [
            {"id": f"c{i}", "name": "write_file", "arguments": {"path": f"g{i}.py", "content": "x"}}
            for i in range(5)
        ]}
        loop = _loop([many, "完成"], self.root, config=LoopConfig(max_turns=2, max_tool_calls_per_turn=2))
        r = loop.run([{"role": "user", "content": "写多个"}])
        executed = [i for i in r.turns[0].invocations if i.approved]
        self.assertEqual(len(executed), 2, "实际执行数受上限约束")
        self.assertEqual(len(r.turns[0].invocations), 5, "声明过的调用都要留痕（含未执行）")

    def test_预算超限即停止(self) -> None:
        from icode.backends import Usage

        tracker = BudgetTracker(budget=Budget(expected_tokens=10, hard_ratio=1.0))
        tracker.usage = Usage(total_tokens=99, calls=1)
        loop = _loop([_write_call("a.py"), "完成"], self.root, budget=tracker)
        r = loop.run([{"role": "user", "content": "写"}])
        self.assertEqual(r.stop_reason, "budget_exceeded")
        self.assertFalse((self.root / "a.py").exists())

    def test_后端异常被如实上报(self) -> None:
        class Boom:
            name = "boom"

            def complete(self, *a, **kw):
                raise RuntimeError("模型挂了")

        loop = AgentLoop(
            backend=Boom(),  # type: ignore[arg-type]
            registry=default_registry(),
            guard=Guard(Scope(workspace_root=self.root)),
            ctx=ToolContext(root=self.root),
        )
        r = loop.run([{"role": "user", "content": "x"}])
        self.assertFalse(r.ok)
        self.assertEqual(r.stop_reason, "backend_error")
        self.assertIn("模型挂了", r.error)


if __name__ == "__main__":
    unittest.main()
