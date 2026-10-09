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
from icode.loop import AgentLoop, LoopConfig, _review_round_alias_arguments
from icode.operations import StartedOperation
from icode.tools import Tool, ToolContext, ToolResult, default_registry


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

    def test_review_round_alias_requires_exact_structured_payload(self) -> None:
        translated = _review_round_alias_arguments({
            "name": "review_round_1.json",
            "content": '{"round":1,"new_issues":["n"],'
                       '"refuted_issues":[],"pending_verification":[]}',
        })
        self.assertEqual(translated, {
            "round": 1,
            "new_issues": ["n"],
            "refuted_issues": [],
            "pending_verification": [],
        })
        self.assertIsNone(_review_round_alias_arguments({
            "name": "review_round_1.json",
            "content": '{"round":1,"new_issues":[],"refuted_issues":[],'
                       '"pending_verification":[1]}',
        }))
        self.assertIsNone(_review_round_alias_arguments({
            "name": "02_review.md", "content": "not a round",
        }))

    def test_review_round_alias_runs_typed_handler(self) -> None:
        contract = StepContract(
            step="review",
            outputs=(Port("rounds", "ticket_glob", "review_round_*.json"),),
        )
        ticket = self.root / "ticket"
        ticket.mkdir()
        broker = ArtifactBroker(ticket, contract, max_bytes=1024)
        backend = FakeBackend([
            {"content": "", "tool_calls": [{
                "id": "generic-round", "name": "submit_artifact",
                "arguments": {
                    "name": "review_round_1.json",
                    "content": {
                        "round": 1, "new_issues": [], "refuted_issues": [],
                        "pending_verification": [],
                    },
                },
            }]},
            "完成",
        ])
        loop = AgentLoop(
            backend=backend,
            registry=default_registry(include_artifacts=True, include_review_round=True),
            guard=Guard(Scope(workspace_root=self.root)),
            ctx=ToolContext(root=self.root, artifact_broker=broker),
            config=LoopConfig(
                max_turns=2,
                force_tool_after_turns=1,
                force_tool_after_turns_tool="submit_review_round",
            ),
        )
        result = loop.run([{"role": "user", "content": "提交 round"}])
        self.assertTrue(result.ok, result.error)
        self.assertTrue((ticket / "review_round_1.json").is_file())
        self.assertEqual(result.turns[0].invocations[0].name, "submit_review_round")

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

    def test_结构化Reviewer提交仅在只读Reviewer上下文放行(self) -> None:
        loop = _loop(["done"], self.root)

        self.assertEqual(loop._decide("submit_review", {}).decision, Decision.DENY)

        loop.ctx.read_only_workspace = True
        loop.ctx.change_baseline = {}
        loop.ctx.review_submission_enabled = True
        self.assertEqual(loop._decide("submit_review", {}).decision, Decision.ALLOW)

        loop.ctx.review_submission_enabled = False
        self.assertEqual(loop._decide("submit_review", {}).decision, Decision.DENY)

    def test_required模式下自由文本只允许一次纠正后提交再结束(self) -> None:
        file_path = self.root / "reviewed.txt"
        file_path.write_text("reviewed content\n", encoding="utf-8")
        loop = _loop([
            {"content": "", "tool_calls": [{
                "id": "read", "name": "read_file",
                "arguments": {"path": str(file_path)},
            }]},
            "这是普通文本，不是结构化审查工具提交。",
            {"content": "", "tool_calls": [{
                "id": "submit", "name": "submit_review", "arguments": {},
            }]},
            "审查已提交。",
        ], self.root, config=LoopConfig(max_turns=6, tool_choice="required"))
        loop.ctx.read_only_workspace = True
        loop.ctx.change_baseline = {}
        loop.ctx.review_submission_enabled = True
        loop.registry.register(Tool(
            name="submit_review",
            description="test-only structured output",
            parameters={"type": "object", "properties": {}, "required": [],
                        "additionalProperties": False},
            handler=lambda _ctx: ToolResult(
                True, "valid", {"review_output": "schema_valid"},
            ),
        ))

        result = loop.run([{"role": "user", "content": "review"}])

        self.assertTrue(result.ok)
        self.assertEqual(result.stop_reason, "no_tool_calls")
        self.assertEqual(
            [call["tool_choice"] for call in loop.backend.calls],
            ["required", "required", "required", "auto"],
        )

    def test_required工具模式连续漏调后失败关闭且有界(self) -> None:
        loop = _loop(
            ["no tool one", "no tool two"], self.root,
            config=LoopConfig(max_turns=6, tool_choice="required"),
        )

        result = loop.run([{"role": "user", "content": "review"}])

        self.assertFalse(result.ok)
        self.assertEqual(result.stop_reason, "required_tool_not_called")
        self.assertEqual(len(loop.backend.calls), 2)

    def test_普通文本收尾后强制受控产物提交(self) -> None:
        out_dir = self.root / "ticket"
        out_dir.mkdir()
        broker = ArtifactBroker(out_dir, StepContract(
            step="review",
            outputs=(
                Port("review", "ticket_file", "02_review.md"),
                Port("rounds", "ticket_glob", "review_round_*.json"),
            ),
        ), max_bytes=4096)
        backend = FakeBackend([
            {"content": "已读取并形成审查结论，但尚未提交。"},
            {"content": "", "tool_calls": [{
                "id": "submit", "name": "submit_artifact",
                "arguments": {"name": "02_review.md", "content": "审查结论"},
            }]},
            {"content": "", "tool_calls": [{
                "id": "round", "name": "submit_artifact",
                "arguments": {
                    "name": "review_round_1.json",
                    "content": "{\"round\":1,\"new_issues\":[],"
                               "\"refuted_issues\":[],\"pending_verification\":[]}",
                },
            }]},
            "提交完成",
        ])
        registry = default_registry(include_artifacts=True)
        loop = AgentLoop(
            backend=backend,
            registry=registry,
            guard=Guard(Scope(workspace_root=self.root)),
            ctx=ToolContext(root=self.root, artifact_broker=broker),
            budget=BudgetTracker(),
            config=LoopConfig(max_turns=5, tool_choice_on_no_tool="submit_artifact"),
        )
        result = loop.run([{"role": "user", "content": "review"}])
        self.assertTrue(result.ok)
        self.assertTrue((out_dir / "02_review.md").is_file())
        self.assertEqual(
            [call["tool_choice"] for call in backend.calls],
            ["auto", "submit_artifact", "submit_artifact", "auto"],
        )

    def test_提供方忽略review_round工具选择时仍经产物校验提交(self) -> None:
        out_dir = self.root / "ticket-round-alias"
        out_dir.mkdir()
        broker = ArtifactBroker(out_dir, StepContract(
            step="review",
            outputs=(
                Port("review", "ticket_file", "02_review.md"),
                Port("rounds", "ticket_glob", "review_round_*.json"),
            ),
        ), max_bytes=4096)
        backend = FakeBackend([
            {"content": "", "tool_calls": [{
                "id": "review", "name": "submit_artifact",
                "arguments": {"name": "02_review.md", "content": "结论"},
            }]},
            {"content": "", "tool_calls": [{
                "id": "round", "name": "submit_artifact",
                "arguments": {"name": "review_round_1.json", "content": {
                    "round": 1, "new_issues": [], "refuted_issues": [],
                    "pending_verification": [],
                }},
            }]},
            "提交完成",
        ])
        loop = AgentLoop(
            backend=backend,
            registry=default_registry(include_artifacts=True, include_review_round=True),
            guard=Guard(Scope(workspace_root=self.root)),
            ctx=ToolContext(root=self.root, artifact_broker=broker),
            budget=BudgetTracker(),
            config=LoopConfig(max_turns=4),
        )
        result = loop.run([{"role": "user", "content": "review"}])
        self.assertTrue(result.ok, result.error)
        self.assertTrue((out_dir / "review_round_1.json").is_file())

    def test_同一回复的多次代码编辑在结果配对后才切换inspection(self) -> None:
        first = self.root / "first.py"
        second = self.root / "second.py"
        first.write_text("before = 1\n", encoding="utf-8")
        second.write_text("before = 2\n", encoding="utf-8")
        out_dir = self.root / "ticket"
        out_dir.mkdir()
        broker = ArtifactBroker(out_dir, StepContract(
            step="code",
            outputs=(Port("worklist", "ticket_file", "code_worklist.json"),),
        ), max_bytes=4096)

        def inspection_runner(**kwargs: Any) -> ToolResult:
            if kwargs.get("phase") == "prepare":
                (out_dir / "code_worklist.json").write_text(
                    '{"units":[{"files":[{"path":"first.py"},{"path":"second.py"}]}]}',
                    encoding="utf-8",
                )
            return ToolResult(True, "inspection-ok")

        backend = FakeBackend([
            {"content": "", "tool_calls": [
                {"id": "edit-1", "name": "edit_file",
                 "arguments": {"path": "first.py", "old": "before = 1", "new": "after = 1"}},
                {"id": "edit-2", "name": "edit_file",
                 "arguments": {"path": "second.py", "old": "before = 2", "new": "after = 2"}},
            ]},
            {"content": "", "tool_calls": [{
                "id": "inspect", "name": "inspection", "arguments": {"phase": "prepare"},
            }]},
            {"content": "", "tool_calls": [{
                "id": "read-1", "name": "inspection",
                "arguments": {"phase": "read", "read_phase": "code_review", "path": "first.py"},
            }]},
            {"content": "", "tool_calls": [{
                "id": "read-2", "name": "inspection",
                "arguments": {"phase": "read", "read_phase": "code_review", "path": "second.py"},
            }]},
            {"content": "", "tool_calls": [{
                "id": "check", "name": "inspection", "arguments": {"phase": "check"},
            }]},
            "完成",
        ])
        registry = default_registry(
            include_artifacts=True,
            inspection_runner=inspection_runner,
        )
        loop = AgentLoop(
            backend=backend,
            registry=registry,
            guard=Guard(Scope(workspace_root=self.root)),
            ctx=ToolContext(root=self.root, artifact_broker=broker),
            budget=BudgetTracker(),
            config=LoopConfig(
                max_turns=6,
                max_tool_calls_per_turn=2,
                force_tool_after_turns=1,
                force_tool_after_turns_tool="edit_file",
            ),
        )

        result = loop.run([{"role": "user", "content": "修改两个源码文件"}])

        self.assertTrue(result.ok)
        self.assertEqual(
            [call["tool_choice"] for call in backend.calls],
            ["edit_file", "inspection", "inspection", "inspection", "inspection", "auto"],
        )
        self.assertTrue(all(inv.result is not None and inv.result.ok for inv in result.turns[0].invocations))
        self.assertEqual([turn.invocations[0].name for turn in result.turns[1:5]], [
            "inspection", "inspection", "inspection", "inspection",
        ])
        self.assertTrue(all(turn.invocations[0].result is not None and turn.invocations[0].result.ok
                            for turn in result.turns[1:5]))
        self.assertEqual(first.read_text(encoding="utf-8"), "after = 1\n")
        self.assertEqual(second.read_text(encoding="utf-8"), "after = 2\n")

    def test_恢复时已有worklist先重新绑定再检查(self) -> None:
        source = self.root / "existing.py"
        source.write_text("value = 1\n", encoding="utf-8")
        out_dir = self.root / "ticket"
        out_dir.mkdir()
        (out_dir / "code_worklist.json").write_text(
            '{"units":[{"files":[{"path":"existing.py"}]}]}', encoding="utf-8",
        )
        broker = ArtifactBroker(out_dir, StepContract(
            step="code",
            outputs=(Port("worklist", "ticket_file", "code_worklist.json"),),
        ), max_bytes=4096)
        backend = FakeBackend([
            {"content": "", "tool_calls": [{
                "id": "prepare", "name": "inspection", "arguments": {"phase": "prepare"},
            }]},
            {"content": "", "tool_calls": [{
                "id": "read", "name": "inspection",
                "arguments": {"phase": "read", "read_phase": "code_review", "path": "existing.py"},
            }]},
            {"content": "", "tool_calls": [{
                "id": "check", "name": "inspection", "arguments": {"phase": "check"},
            }]},
            "恢复检查完成",
        ])

        def inspection_runner(**kwargs: Any) -> ToolResult:
            return ToolResult(True, "inspection-ok")

        loop = AgentLoop(
            backend=backend,
            registry=default_registry(
                include_artifacts=True, inspection_runner=inspection_runner,
            ),
            guard=Guard(Scope(workspace_root=self.root)),
            ctx=ToolContext(root=self.root, artifact_broker=broker),
            budget=BudgetTracker(),
            config=LoopConfig(max_turns=4),
        )

        result = loop.run([{"role": "user", "content": "恢复 code 检查"}])

        self.assertTrue(result.ok)
        self.assertEqual(
            [call["tool_choice"] for call in backend.calls],
            ["inspection", "inspection", "inspection", "auto"],
        )

    def test_精确Reviewer读完全部文件后强制结构化提交(self) -> None:
        first = self.root / "first.py"
        second = self.root / "second.py"
        first.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
        second.write_text("one line\n", encoding="utf-8")
        backend = FakeBackend([
            {"content": "", "tool_calls": [{
                "id": "read-first-1", "name": "read_file",
                "arguments": {"path": str(first), "offset": 1, "limit": 1},
            }]},
            {"content": "", "tool_calls": [
                {"id": "read-first-2", "name": "read_file",
                 "arguments": {"path": str(first), "offset": 2, "limit": 5}},
                {"id": "read-second", "name": "read_file",
                 "arguments": {"path": str(second)}},
            ]},
            {"content": "", "tool_calls": [{
                "id": "submit", "name": "submit_review", "arguments": {},
            }]},
            "review complete",
        ])
        registry = default_registry()
        registry.register(Tool(
            name="submit_review",
            description="test-only structured output",
            parameters={"type": "object", "properties": {}, "required": [],
                        "additionalProperties": False},
            handler=lambda _ctx: ToolResult(
                True, "valid", {"review_output": "schema_valid"},
            ),
        ))
        loop = AgentLoop(
            backend=backend,
            registry=registry,
            guard=Guard(Scope(
                workspace_root=self.root,
                allowed_read_files=(first, second),
            )),
            ctx=ToolContext(
                root=self.root, read_only_workspace=True,
                change_baseline={}, review_submission_enabled=True,
            ),
            config=LoopConfig(
                max_turns=6, max_tool_calls_per_turn=3,
                tool_choice="read_file", tool_choice_after_read="submit_review",
            ),
        )

        result = loop.run([{"role": "user", "content": "review"}])

        self.assertTrue(result.ok)
        self.assertEqual(
            [call["tool_choice"] for call in backend.calls],
            ["read_file", "read_file", "submit_review", "auto"],
        )

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
        self.assertEqual(inv.note, "此操作超出当前任务范围，已阻止。")
        self.assertEqual(inv.result.meta["error_code"], "policy_denied")
        self.assertEqual(
            inv.result.meta["violation_receipt"],
            {
                "schema_version": 1,
                "enforcement_layer": "application_policy",
                "os_enforced": False,
                "category": "guard_denied",
                "operation": "run_command",
            },
        )
        self.assertEqual(inv.result.content, "此操作超出当前任务范围，已阻止。")

    def test_权限拒绝事件带结构化回执且不携带自然语言原因(self) -> None:
        events: list[tuple[str, dict]] = []
        loop = _loop([{
            "content": "",
            "tool_calls": [{
                "id": "c1", "name": "run_command",
                "arguments": {"argv": ["rm", "-rf", "/"]},
            }],
        }, "完成"], self.root)
        loop.on_event = lambda kind, payload: events.append((kind, payload))

        result = loop.run([{"role": "user", "content": "删除"}])

        self.assertTrue(result.ok)
        denied = [payload for kind, payload in events if kind == "tool_denied"]
        self.assertEqual(len(denied), 1)
        self.assertNotIn("reason", denied[0])
        self.assertEqual(denied[0]["error_code"], "policy_denied")
        self.assertEqual(denied[0]["user_message"], "此操作超出当前任务范围，已阻止。")
        self.assertEqual(denied[0]["violation_receipt"]["os_enforced"], False)

    def test_应用策略拒绝结果事件携带安全提示(self) -> None:
        protected_file = self.root / "protected.txt"
        protected_file.write_text("private marker", encoding="utf-8")
        events: list[tuple[str, dict]] = []
        loop = _loop([{
            "content": "",
            "tool_calls": [{
                "id": "read-protected", "name": "read_file",
                "arguments": {"path": str(protected_file)},
            }],
        }, "完成"], self.root)
        loop.ctx.deny_read_roots = (protected_file,)
        loop.on_event = lambda kind, payload: events.append((kind, payload))

        result = loop.run([{"role": "user", "content": "读取文件"}])

        self.assertTrue(result.ok)
        tool_results = [payload for kind, payload in events if kind == "tool_result"]
        self.assertEqual(len(tool_results), 1)
        self.assertFalse(tool_results[0]["ok"])
        self.assertEqual(tool_results[0]["meta"]["error_code"], "policy_denied")
        self.assertEqual(tool_results[0]["user_message"], "此操作超出当前任务范围，已阻止。")

    def test_成功结果不会因机器码碰撞附加拒绝提示(self) -> None:
        events: list[tuple[str, dict]] = []
        loop = _loop([{
            "content": "",
            "tool_calls": [{
                "id": "success", "name": "success_probe", "arguments": {},
            }],
        }, "完成"], self.root)
        loop.registry.register(Tool(
            name="success_probe",
            description="test-only result metadata probe",
            parameters={
                "type": "object", "properties": {}, "required": [],
                "additionalProperties": False,
            },
            handler=lambda _ctx: ToolResult(
                True, "ok", {"error_code": "policy_denied"},
            ),
        ))
        loop.on_event = lambda kind, payload: events.append((kind, payload))

        result = loop.run([{"role": "user", "content": "探测成功结果"}])

        self.assertTrue(result.ok)
        tool_results = [payload for kind, payload in events if kind == "tool_result"]
        self.assertTrue(tool_results[0]["ok"])
        self.assertNotIn("user_message", tool_results[0])

    def test_拒绝报告不回显含敏感参数的Guard原因(self) -> None:
        marker = "PRIVATE_DENIAL_ARGUMENT_MARKER"
        loop = _loop([{
            "content": "",
            "tool_calls": [{
                "id": "malformed-shell", "name": "run_command",
                "arguments": {"argv": ["echo", f"$(cat {marker})"]},
            }],
        }, "完成"], self.root)

        result = loop.run([{"role": "user", "content": "运行命令"}])

        invocation = result.turns[0].invocations[0]
        self.assertEqual(invocation.note, "此操作超出当前任务范围，已阻止。")
        self.assertNotIn(marker, result.render())

    def test_畸形命令参数被拒且回合继续(self) -> None:
        for bad in ({"python": "-V"}, ["python", 1], 7):
            with self.subTest(argv=bad):
                script = [{"content": "", "tool_calls": [
                    {"id": "c1", "name": "run_command", "arguments": {"argv": bad}}
                ]}, "完成"]
                result = _loop(script, self.root).run([{"role": "user", "content": "测试"}])
                self.assertTrue(result.ok)
                invocation = result.turns[0].invocations[0]
                self.assertEqual(invocation.decision, "deny")
                self.assertFalse(invocation.approved)

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

    def test_必需工具回合预留必须绑定读取后工具且不可耗尽(self) -> None:
        with self.assertRaisesRegex(ValueError, "需要 tool_choice_after_read"):
            _loop(
                ["done"], self.root,
                config=LoopConfig(max_turns=5, required_tool_turn_reserve=1),
            )

        source = self.root / "reviewed.py"
        source.write_text("value = 1\n", encoding="utf-8")
        registry = default_registry()
        registry.register(Tool(
            name="submit_review",
            description="test-only structured output",
            parameters={"type": "object", "properties": {}, "required": [],
                        "additionalProperties": False},
            handler=lambda _ctx: ToolResult(True, "valid", {}),
        ))
        with self.assertRaisesRegex(ValueError, "必须小于 max_turns"):
            AgentLoop(
                backend=FakeBackend(["done"]),
                registry=registry,
                guard=Guard(Scope(
                    workspace_root=self.root, allowed_read_files=(source,),
                )),
                ctx=ToolContext(root=self.root),
                config=LoopConfig(
                    max_turns=1,
                    tool_choice="read_file",
                    tool_choice_after_read="submit_review",
                    required_tool_turn_reserve=1,
                ),
            )

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


class _MeteredBackend(FakeBackend):
    """Report one explicit charge for each real FakeBackend response."""

    def __init__(self, responses: list[tuple[Any, int]]) -> None:
        super().__init__([response for response, _ in responses])
        self.charges = [charge for _, charge in responses]

    def complete(self, *args, **kwargs):
        from icode.backends import Usage

        charge = self.charges[min(self._index, len(self.charges) - 1)]
        response = super().complete(*args, **kwargs)
        self.last_usage = Usage(total_tokens=charge, calls=1)
        return response


class TestPostResponseBudgetGate(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.root = self._ws.__enter__()

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def _metered_loop(self, responses, *, expected=100, hard_ratio=3.0, **kwargs):
        tracker = BudgetTracker(Budget(expected_tokens=expected, hard_ratio=hard_ratio))
        loop = _loop([response for response, _ in responses], self.root,
                     budget=tracker, **kwargs)
        loop.backend = _MeteredBackend(responses)
        return loop, tracker

    def test_last_text_response_over_budget_cannot_succeed(self) -> None:
        loop, tracker = self._metered_loop([("actual final reply", 301)],
                                          config=LoopConfig(max_turns=1))
        hooks = []
        loop.on_turn = lambda index, calls, history: hooks.append((index, calls, list(history)))
        report = loop.run([{"role": "user", "content": "finish"}])
        self.assertFalse(report.ok)
        self.assertEqual(report.stop_reason, "budget_exceeded")
        self.assertEqual(report.usage.total_tokens, 301)
        self.assertEqual(report.usage.calls, 1)
        self.assertEqual(tracker.verdict, "over_budget")
        self.assertEqual(len(report.turns), 1)
        self.assertEqual(report.messages[-1]["content"], "actual final reply")
        self.assertEqual(hooks, [(1, 0, report.messages)])

    def test_over_budget_tool_response_never_starts_side_effects(self) -> None:
        from unittest.mock import patch

        operations = _StubOps()
        loop, tracker = self._metered_loop([(_write_call("budget-marker"), 301)],
                                          ops=operations, config=LoopConfig(max_turns=1))
        with patch.object(loop, "_invoke", wraps=loop._invoke) as invoke, patch.object(
            loop.registry, "invoke", wraps=loop.registry.invoke,
        ) as registry, patch.object(loop.approver, "ask", wraps=loop.approver.ask) as ask:
            report = loop.run([{"role": "user", "content": "write"}])
        self.assertFalse(report.ok)
        self.assertEqual(report.stop_reason, "budget_exceeded")
        self.assertFalse((self.root / "budget-marker").exists())
        invoke.assert_not_called()
        registry.assert_not_called()
        ask.assert_not_called()
        self.assertEqual(operations.started, [])
        self.assertEqual(operations.finished, [])
        self.assertIs(report.usage, tracker.usage)
        self.assertEqual(report.usage.total_tokens, 301)

    def test_every_skipped_call_has_truthful_paired_result_and_checkpoint(self) -> None:
        calls = {"content": "requested writes", "tool_calls": [
            {"id": f"b{i}", "name": "write_file",
             "arguments": {"path": f"budget-{i}", "content": "not written"}}
            for i in range(3)
        ]}
        loop, _ = self._metered_loop([(calls, 301)],
                                    config=LoopConfig(max_turns=1, max_tool_calls_per_turn=1))
        events, hooks = [], []
        loop.on_event = lambda kind, payload: events.append((kind, payload))
        loop.on_turn = lambda index, count, history: hooks.append((index, count, list(history)))
        report = loop.run([{"role": "user", "content": "batch"}])
        self.assertEqual(report.stop_reason, "budget_exceeded")
        self.assertFalse(report.ok)
        declared = {call["id"] for call in report.messages[1]["tool_calls"]}
        replies = [message for message in report.messages if message["role"] == "tool"]
        self.assertEqual({message["tool_call_id"] for message in replies}, declared)
        self.assertEqual(len(replies), 3)
        self.assertEqual(len(report.turns[0].invocations), 3)
        for invocation in report.turns[0].invocations:
            self.assertFalse(invocation.approved)
            self.assertFalse(invocation.result.ok)
            self.assertEqual(invocation.result.meta["error"], "budget_exceeded")
            self.assertIn("未执行", invocation.result.content)
        self.assertFalse(any((self.root / f"budget-{i}").exists() for i in range(3)))
        self.assertEqual(hooks, [(1, 3, report.messages)])
        self.assertEqual([kind for kind, _ in events],
                         ["assistant"] + ["tool_skipped_budget"] * 3)

    def test_exact_threshold_and_custom_ratio_keep_strict_greater_than(self) -> None:
        for expected, ratio, charge, allowed in ((100, 3.0, 300, True), (100, 3.0, 301, False),
                                                (100, 1.0, 100, True), (100, 1.0, 101, False)):
            with self.subTest(expected=expected, ratio=ratio, charge=charge):
                loop, _ = self._metered_loop([("complete", charge)], expected=expected,
                                            hard_ratio=ratio, config=LoopConfig(max_turns=1))
                report = loop.run([{"role": "user", "content": "threshold"}])
                self.assertIs(report.ok, allowed)
                self.assertEqual(report.stop_reason, "no_tool_calls" if allowed else "budget_exceeded")
                self.assertEqual(report.usage.total_tokens, charge)

    def test_rejected_nonobject_json_arguments_keep_budget_failure_and_pairing(self) -> None:
        import json

        for raw, expected in ((7, 7), ('"scalar"', "scalar"), ([1], [1])):
            with self.subTest(raw=raw):
                response = {"content": "invalid arguments", "tool_calls": [
                    {"id": "invalid-json-args", "name": "write_file", "arguments": raw},
                ]}
                operations, hooks = _StubOps(), []
                loop, tracker = self._metered_loop([(response, 301)], ops=operations)
                loop.on_turn = lambda index, count, history: hooks.append((index, count))
                report = loop.run([{"role": "user", "content": "reject without parsing"}])
                self.assertFalse(report.ok)
                self.assertEqual(report.stop_reason, "budget_exceeded")
                self.assertEqual(report.usage.total_tokens, 301)
                self.assertIs(report.usage, tracker.usage)
                self.assertEqual(operations.started, [])
                self.assertEqual(hooks, [(1, 1)])
                invocation = report.turns[0].invocations[0]
                self.assertFalse(invocation.approved)
                self.assertEqual(invocation.arguments, {})
                self.assertEqual(invocation.result.meta["error"], "budget_exceeded")
                assistant = report.messages[1]["tool_calls"][0]
                self.assertEqual(json.loads(assistant["function"]["arguments"]), expected)
                self.assertEqual(report.messages[-1]["tool_call_id"], "invalid-json-args")
                self.assertIn("未执行", report.messages[-1]["content"])

    def test_observe_only_and_missing_usage_keep_existing_behavior(self) -> None:
        for expected in (0, -1):
            with self.subTest(expected=expected):
                loop, tracker = self._metered_loop([("complete", 301)], expected=expected)
                report = loop.run([{"role": "user", "content": "observe"}])
                self.assertTrue(report.ok)
                self.assertEqual(tracker.verdict, "observe_only")
                self.assertEqual(report.usage.total_tokens, 301)
        loop = _loop(["unmetered complete"], self.root,
                     budget=BudgetTracker(Budget(expected_tokens=100)))
        report = loop.run([{"role": "user", "content": "missing usage"}])
        self.assertTrue(report.ok)
        self.assertEqual(report.usage.total_tokens, 0)

    def test_cumulative_charge_preserves_first_write_but_blocks_second(self) -> None:
        operations = _StubOps()
        loop, tracker = self._metered_loop(
            [(_write_call("first-marker", call_id="first"), 100),
             (_write_call("second-marker", call_id="second"), 201)],
            ops=operations, config=LoopConfig(max_turns=2),
        )
        report = loop.run([{"role": "user", "content": "two turns"}])
        self.assertFalse(report.ok)
        self.assertEqual(report.stop_reason, "budget_exceeded")
        self.assertTrue((self.root / "first-marker").is_file())
        self.assertFalse((self.root / "second-marker").exists())
        self.assertEqual(len(operations.started), 1)
        self.assertEqual(len(operations.finished), 1)
        self.assertEqual(len(loop.backend.calls), 2)
        self.assertIs(report.usage, tracker.usage)
        self.assertEqual(report.usage.total_tokens, 301)
        self.assertEqual(report.usage.calls, 2)
        self.assertEqual(len(report.turns), 2)

    def test_required_tool_mode_never_retries_after_charge_exceeds_budget(self) -> None:
        loop, _ = self._metered_loop([("no tool", 301)],
                                    config=LoopConfig(max_turns=3, tool_choice="required"))
        report = loop.run([{"role": "user", "content": "required"}])
        self.assertFalse(report.ok)
        self.assertEqual(report.stop_reason, "budget_exceeded")
        self.assertEqual(len(loop.backend.calls), 1)
        self.assertEqual(report.usage.calls, 1)
        self.assertEqual(len(report.messages), 2)

    def test_failed_checkpoint_hook_cannot_turn_budget_failure_into_success(self) -> None:
        loop, _ = self._metered_loop([("actual reply", 301)])
        hooks = []

        def broken_hook(index, count, history):
            hooks.append((index, count))
            raise RuntimeError("test-only checkpoint failure")

        loop.on_turn = broken_hook
        report = loop.run([{"role": "user", "content": "checkpoint"}])
        self.assertFalse(report.ok)
        self.assertEqual(report.stop_reason, "budget_exceeded")
        self.assertEqual(hooks, [(1, 0)])
        self.assertEqual(report.usage.total_tokens, 301)


if __name__ == "__main__":
    unittest.main()
