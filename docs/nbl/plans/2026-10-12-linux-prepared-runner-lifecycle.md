# Linux prepared runner lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 Linux 内部生产 runner 单调用中于模型和真实 raw CP start 前准备并 claim 同一资源，将普通、补救、工程消费绑定到实际 attempt，并在六个 CP terminal 前确认一次收尾。

**Architecture:** 复用 S1 scope/attachment 状态机、S2a 精确薄适配、S2b1 raw start/fresh observer 及唯一资源 broker。runner 私有上下文捕获可信栈绑定，在实际 controlled resource dispatch 和 legacy wrap 两个消费入口防止公开字段漂移。局部一次收尾门覆盖六个 terminal，outer finally 兜底，不修改共享 finish/budget/finalize/resume 助手。

**Tech Stack:** Python 3.11、unittest、实际固定 vendor ControlPlane、Linux FD/lease/socketpair，合成 ELF 和底层传输 double；无新依赖。

---

初稿时仅文档资产（历史）。当前SOURCE/TEST已按批准资产正式实施；交付顺序按Task3及AGENTS的2026-10-13线上优先授权，不执行历史中的“仅文档/本机全量先于推送”。初稿观察main为 `667c92af7b338b9983c9829251a0f70128dd1d8e`，当时S2b1未发布，RAM测试因此等待。后续S2b1 main `1754ccafcd568f5771c342ec9223c307513cee2c` 的commit91aaca/push39f2c5均exit0，09:34:06 UTC核HEAD=remote/tracked clean，vendor固定21566a5；完整门74867于09:20:00 UTC exit0、09:20:20 UTC三门PASS，仅属于S2b1。该时期SOURCE/TEST未落盘、私人RAM不算正式TDD；后续正式证据另列。

批准 [DESIGN](../specs/2026-10-12-linux-prepared-runner-lifecycle-design.md) SHA-256 `ff78553d7fa5ce74fdb955464b253a0bb9567763f87e92ea8d0d04669d0410bf`；批准 DESIGN 的 fresh SPEC→不同 QUALITY 均 C0/I0/M0。历史 5ddc0aec 与 f08c75bf 两个 I 修正均保留：本计划完全保留原 `_make_ctx` 的 constructor kwargs/None/空串语义，且将 guard 放在实际普通工具与工程消费入口。母合同：[S1](../specs/2026-10-12-linux-prepared-step-scope-design.md)、[S2a](../specs/2026-10-12-linux-prepared-tool-context-design.md)、[S2b1](../specs/2026-10-12-linux-prepared-control-attempt-design.md)。

三问已确认：当前真实 runner 没有持有准备生命周期；scope/attachment/CP 机制已有；所有普通/补救/工程/终结调用链及独立 Reviewer、resume 分界已盘点。本片不实现新 owner、权限、用户参数、token、模型缓存、自动准入或 CP schema。

本次文档修订针对上一版 PLAN `75b1776e84e7726305171a400b39e1747bab3dd39909cc7a258a4824b3576643` 的独立 QUALITY C0/I1/M0：其局部收尾门仅核内部 owner closed，外部真实 close 失败后 unknown 可在 view.finish 已 spent 时漏过。采纳批准 DESIGN 的现有 owner 分账合同，终结必须内部 closed、外部 active；任何其他 owner 状态均固定 `prepared_cleanup_unconfirmed`，优先于 ordinary body 的 `prepared_execution_unconfirmed`。runner 只 finish 外部 view，不 close/retry 外部 owner；cleanup_attempted 先置、finish 与内部 close 独立尝试、first KI/SE 对象优先和旧共享函数保持原合同。不是新增机制或发布范围。

## 文件与所有权

原六功能范围为 `src/icode/runner.py`、`src/icode/chain.py`、新 `tests/test_linux_prepared_runner_lifecycle.py`、批准DESIGN、本PLAN、`docs/agent-landscape-live.md`。2026-10-13用户明确要求同步AGENTS.md及development-handoff.md两份流程文档，当前候选精确八路径，不扩功能源码。原PLAN作者仅写本文件；root维护流程文档/index，正式TEST与SOURCE仍不同作者。

原 runner SHA-256 `56abe98e31f02cc96327a364c52ace9aef5b7c60e6594025058e2de48f15a63d`；chain `28244144023c85548ca0e9bcb68235a935d648d53b8367ae80cde67f746508de`。S2b1 control `ffdaec53c10a23deed7b4383415fe48e1b54af706bee908a4f80fdece127c5ff`、新适配 `875635c99689a7e95c6c5d48670727f1453ef3fa05fa6ebf714440747d3596a0`、TEST `20868a62bff6138ce3f1ff8d25faf25ed14b57a69fb6f92c22503d5606d22f80` 已 frozen GREEN、独立 SOURCE 双审及实际发布。root 正式证据追加后的 S2b1 DESIGN SHA-256 `815fdb9c648ba22b79b55acaa8e9725396a26168da101d1ad63c4b1f84934342`、PLAN `5693c064cc8c44c8a32ece98566e2e1aaccdd087161b59384d58c54ae8d63f62`，未改变本片批准 DESIGN。实施前仍重核实际 main 与这些 bytes；发生漂移停止，不猜未来 SHA。

`tools/base.py`、`tools/builtin.py`、`engineering_verification.py`、scope/control/S2b1 module、native/vendor/autonomy/CI/所有旧 tests 均只读。实际资源消费沿原 `run_command→_controlled_dispatch→resource observed broker→view.borrow` 和 `_execute_check→_controlled_dispatch`；policy=None 时两实际入口均调用 `ctx.wrap_command`，其 `network` keyword shape 必须保留。工程 gate 的 ctx、本次补救 ctx 与普通 ctx 持同一 view/attempt；Reviewer 不接 RW view；纯 admission 不 claim；恢复不还原许可。

## 研究取舍

沿用 S2b1 2026-10-12 08:18–08:19 UTC 的实际 GET 固定观察，无新 GET/HEAD 刷新：[OpenHands state](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/conversation/state.py#L526-L561)、[workspace 分账](https://github.com/OpenHands/software-agent-sdk/blob/3934349da2db0433238621542173a00a8af7439c/openhands-sdk/openhands/sdk/workspace/models.py#L20-L42)、[Codex 原身份](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/sdk/typescript/src/thread.ts#L77-L141)。前者 MIT，后者 Apache-2.0。采纳结果、身份、生命周期分账及每次消费重核；ICODE 已有 view/state/CP，收益为退出完整收尾与早终结阻断，成本为 runner 局部接线和真实 CP/FD 软件负控，无源码复制/依赖/权限变化。暂缓恢复、缓存、installed/原生合流和自动 ready；不适配 typed 对象或 finally 存在即授权。

root 的独立只读研究已另在 [live](../../agent-landscape-live.md) 记录 09:37:01–09:37:33 UTC 两固定 project/LICENSE 实际 GET200（不刷新 HEAD）。Codex exec 1027–1082/1126–1164、bwrap 66–100 支持退出/结果/cleanup 与同 owner 分账，采纳局部终结顺序机制；OpenHands LocalWorkspace 36–45 先 callback 再 super，而 base 88–169 是 best-effort/默认无清理，不适配 ICODE 的 CP 终结门。无新增范围、源码复制或许可依赖；不把旧查询伪装成本次观察。

## Task 1: 固定发布基线与正式 TEST ONLY RED

**状态**
- [x] 任务完成（正式作者/root RED及冻结，证据见文末2026-10-13执行记录）

**Dependencies:** None
**Parallelizable:** No (必须先有 S2b1 实际发布及本 PLAN 独立双审)

- [ ] **Step 1:** root 用 `git rev-parse HEAD`、`git -C vendor/icode-skill rev-parse HEAD` 和上述 `sha256sum` 核实际已发布 S2b1。记录实际 SHA、DESIGN/PLAN fresh SPEC→不同 QUALITY 零遗留、停止条件，不填推测 SHA。
- [ ] **Step 2:** 不同 TEST 作者完整回读批准 DESIGN、三母合同、原调用链及旧 S2a TEST，使用下面完整 Python 资产仅以 apply_patch 创建新 TEST。禁止改旧 tests、SOURCE、scope、vendor；测试缺 API 用 callable/signature assertion，不能以 ImportError/constructor TypeError 算 RED。
- [ ] **Step 3:** 正式作者执行 `.venv/bin/python -m unittest tests.test_linux_prepared_runner_lifecycle -v`，root 独立重复同命令。预期特征缺失 assertion FAIL、exit1、0 ERROR；按测试名/子用例记录有效 assert FAIL，不要求兼容正例也必须红。若 fixture/API 错误，修 TEST 并再次从 unchanged SOURCE 取有效 RED。
- [ ] **Step 4:** 作者完成 SPEC 自审→QUALITY 自审，root 确认 TEST sha 与独立 RED 后冻结新 TEST，才放行不同 SOURCE 作者。文档 RAM compile/诊断完全不代替这两次实际 RED。

### 完整新 TEST 字节资产

以下 fence 完整内容对应 `tests/test_linux_prepared_runner_lifecycle.py`，末尾保留换行。临时工单只能在 fixture 自建隔离目录，用固定 `next_out_dir`、真实 `create/bind_execution_root/raw start/trace/step_finish(evidence)` 与 code fixture migration API；不写本仓或 vendor。合成 ELF、manager/monitor/payload transport seam 不授 native/installed、真实模型或隔离信用。真实 CP 事件、scope/session/lease/held FD 和生产调用链单列软件信用。

```python
"""Runner lifecycle software evidence: actual CP/FD/borrow, synthetic ELF and transport."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import replace
import errno
import inspect
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests._support import REPO_ROOT
from icode import chain, runner
from icode.backends import FakeBackend
from icode.approvals import ScriptedApprover
from icode.budget import Budget, BudgetTracker
from icode.config import Settings
from icode.control import ControlPlane
from icode.engineering_verification import VerificationCheck, VerificationPlan, _execute_check
from icode.handshake import next_out_dir
from icode.loop import LoopConfig, LoopResult
from icode.tools import builtin
from icode.tools.base import ToolContext

LINUX = sys.platform.startswith("linux") and callable(getattr(os, "pread", None))
if LINUX:
    from tests import test_linux_prepared_step as fixture
    from tests import test_linux_helper_dispatch as dispatch
    from icode import execution_broker as broker
    from icode import linux_prepared_step as prepared

VENDOR = REPO_ROOT / "vendor" / "icode-skill"


@unittest.skipUnless(LINUX, "Linux software fixture; skip is not acceptance")
class PreparedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.resources = fixture.PreparedTests(methodName="runTest")
        self.addCleanup(self.resources.doCleanups)
        self.resources.setUp()
        self.root = self.resources.session.workspace_root
        self.session = self.resources.session
        self.sandbox = self.resources.sandbox
        self.settings = Settings(VENDOR)
        self.cp = ControlPlane(self.settings)
        self.opened, self.views, self.contexts, self.payloads, self.channels = [], [], [], [], []
        self.make_ticket("plan")

    def make_ticket(self, step):
        self.step = step
        self.policy = self.session.policy(step, process_limit=16,
            wall_timeout_seconds=30, output_limit_bytes=4096)
        self.resources.policy = self.policy
        self.ticket = self.session.ticket_id
        self.out = next_out_dir(self.resources.root / "control")
        if step == "code":
            self.out.mkdir(parents=True, exist_ok=True)
            legacy = dict(ticket_id=self.ticket, requirement="runner lifecycle",
                created_at="2026-10-12T00:00:00Z", status="code_in_progress",
                completed_steps=["1", "2", "3"], code_files=["data.txt"],
                workflow_gate_schema_version=1, thinking_gate_schema_version=1,
                mcp_gate_schema_version=2, semantic_decisions=[], requirement_deltas=[],
                project_path=str(self.resources.root / "control"))
            (self.out / ".ico_metadata.json").write_text(json.dumps(legacy), encoding="utf-8")
            self.assertIs(self.cp.run("migration", "--dir", str(self.out), "--apply").data.get("ok"), True)
            (self.out / "03_plan_final.md").write_text("# Accepted fixture plan\n", encoding="utf-8")
        else:
            created = self.cp.create(self.out, ticket_id=self.ticket,
                requirement="runner lifecycle", birth="plan")
            self.assertIs(created.data.get("ok"), True)
        self.assertIs(self.cp.bind_execution_root(self.out, ticket_id=self.ticket,
            execution_root=self.root).data.get("ok"), True)
        check = VerificationCheck("first", "test",
            (sys.executable, "-I", "-B", "-X", "utf8", "-m", "unittest",
             "discover", "-s", str(self.root), "-t", str(self.root)),
            "unittest_summary_v1", timeout_seconds=3, output_limit_bytes=4096)
        self.plan = VerificationPlan(self.root, self.session.run_id, self.ticket,
            (check, replace(check, check_id="second")), steps=(step,) if step == "code" else ("code",), platforms=("Linux",))

    def events(self, kind):
        return [row for line in (self.out / ".ico_events.jsonl").read_text(encoding="utf-8").splitlines()
            if (row := json.loads(line))["event_type"] == kind]

    def opened_attempt(self):
        opened = self.cp.trace(self.out).data["open_steps"]
        self.assertEqual(len(opened), 1)
        return next(iter(opened))

    def require_private(self):
        target = getattr(runner, "_make_prepared_ctx", None)
        self.assertTrue(callable(target), "runner prepared context factory missing")
        return target

    def args(self, backend=None, **changes):
        args = dict(backend=backend or FakeBackend([]), workspace=self.root, step=self.step,
            ticket_id=self.ticket, requirement="runner lifecycle", out_dir=self.out,
            sandbox=self.sandbox, policy=self.policy, workspace_session=self.session,
            approver=ScriptedApprover(default=True),
            loop_config=LoopConfig(max_turns=8))
        if self.step == "code":
            args["verification_plan"] = self.plan
        args.update(changes)
        return args

    def invoke(self, backend=None, **changes):
        # Missing API must be an intentional assertion RED, never TypeError.
        self.assertIn("prepared_scope", inspect.signature(runner.run_contract_step).parameters,
            "runner prepared lifecycle keyword missing")
        return runner.run_contract_step(self.settings, **self.args(backend, **changes))

    def script(self, *, commands=2, submit=True):
        rows = [{"tool_calls": [{"id": "command-" + str(n), "name": "run_command",
            "arguments": {"argv": ["/usr/bin/true"]}}]} for n in range(commands)]
        if submit:
            rows.append({"tool_calls": [{"id": "artifact", "name": "submit_artifact",
                "arguments": {"name": "04_code_review_fix.md" if self.step == "code" else "01_plan.md",
                              "content": "# Actual model-double artifact\n"}}]})
        rows.append("done")
        rows.extend(json.dumps({"step": "Check actual fixture", "next_thought_needed": False})
            for _ in range(6))
        return FakeBackend(rows)

    @contextmanager
    def transport(self, *, notify_unknown=False):
        """Reuse low transport seams only; real dispatch, borrow and wrappers remain."""
        original_factory = prepared.open_linux_helper_object
        original_attach = prepared.LinuxPreparedStep._attach
        original_ctx = getattr(runner, "_make_prepared_ctx", None)
        def opening(*args):
            owner = original_factory(*args)
            self.opened.append((owner, owner.fileno()))
            return owner
        def attaching(scope, **kwargs):
            view = original_attach(scope, **kwargs)
            self.views.append(view)
            return view
        def context(*args, **kwargs):
            ctx = original_ctx(*args, **kwargs)
            self.contexts.append(ctx)
            return ctx
        def channel():
            pair = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            self.channels.extend(pair)
            return pair
        def received(*args, **kwargs):
            receiver = dispatch.Resource()
            receiver.receipt = lambda: dict(schema_version=1, resource="linux_payload_tasks",
                limit=self.policy.process_limit, configured=True, payload_started=None,
                terminal="finished", channel_status="complete")
            return receiver
        def execute(argv, **kwargs):
            kwargs["before_spawn"]()
            command = argv
            self.assertIs(command.helper_object, self.views[-1]._scope._owner)
            self.payloads.append(command.helper_object)
            if notify_unknown:
                kwargs["on_cleanup_unknown"]()
            output = b"Ran 1 test in 0.01s\n\nOK\n"
            return broker.ExecutionResult(0, "", len(output), None, False, True, None,
                raw_output=output)
        with ExitStack() as stack:
            stack.enter_context(patch.object(prepared, "open_linux_helper_object", side_effect=opening))
            stack.enter_context(patch.object(prepared.LinuxPreparedStep, "_attach", new=attaching))
            if callable(original_ctx):
                stack.enter_context(patch.object(runner, "_make_prepared_ctx", side_effect=context))
            stack.enter_context(patch("icode.linux_seccomp_notify.create_seccomp_listener_handoff_channel",
                side_effect=channel))
            stack.enter_context(patch("icode.linux_task_resource.create_task_resource_channel",
                side_effect=channel))
            stack.enter_context(patch("icode.linux_seccomp_notify.LinuxSeccompViolationMonitor",
                side_effect=dispatch.Monitor))
            stack.enter_context(patch("icode.linux_task_resource.LinuxTaskResourceReceiver",
                side_effect=received))
            stack.enter_context(patch("icode.linux_task_scope.LinuxTaskScope",
                side_effect=lambda **kwargs: dispatch.Scope()))
            stack.enter_context(patch.object(broker, "_execute_policy_command", side_effect=execute))
            yield
        self.assertTrue(all(endpoint.fileno() == -1 for endpoint in self.channels))

    def owner_closed(self):
        self.assertEqual(len(self.opened), 1)
        with self.assertRaises(OSError) as caught:
            os.fstat(self.opened[0][1])
        self.assertEqual(caught.exception.errno, errno.EBADF)
        self.session.lease._validate_active()
        os.fstat(self.session.workspace_fd)

    def no_terminal(self):
        trace = self.cp.trace(self.out)
        self.assertIs(trace.data.get("ok"), True)
        self.assertEqual(self.events("step_finished"), [])
        self.assertEqual(self.events("state_changed"), [])
        self.assertTrue(trace.data["open_steps"])

    def bound_context(self):
        self.require_private()
        scope = self.resources.prepare()
        view = self.resources.attach(scope)
        raw = self.cp._step_start_result(self.out, self.step, ticket_id=self.ticket,
            request="context-real-start")
        from icode.linux_prepared_control import _prepared_control_attempt_binding
        attempt, observer = _prepared_control_attempt_binding(self.cp, out_dir=self.out,
            ticket_id=self.ticket, step=self.step, start_result=raw)
        view._bind_attempt(attempt, validate_attempt=observer)
        ctx = self.require_private()(self.root, self.sandbox, self.policy,
            workspace_session=self.session, prepared_step=view, prepared_attempt=attempt)
        return scope, view, attempt, ctx

    def test_internal_prepare_attach_before_raw_start_and_backend_same_owner_twice(self):
        original = ControlPlane._step_start_result
        def start(control, *args, **kwargs):
            self.assertEqual(len(self.opened), 1)
            self.assertEqual(len(self.views), 1)
            self.assertEqual(self.views[0]._scope._consume_state, "attached_pending")
            self.assertEqual(self.payloads, [])
            return original(control, *args, **kwargs)
        backend = self.script()
        with self.transport(), patch.object(ControlPlane, "_step_start_result", new=start), \
                patch.object(ControlPlane, "step_start", side_effect=AssertionError("no public prepared start")):
            report = self.invoke(backend)
        self.assertEqual(len(self.payloads), 2, report.error)
        self.assertTrue(all(owner is self.opened[0][0] for owner in self.payloads))
        self.assertEqual(self.views[0]._scope._consume_state, "spent")
        self.assertTrue(backend.calls)
        self.owner_closed()
        # CP success/refusal keeps its original gate semantics; lifecycle is checked separately.
        self.assertEqual(len(self.events("step_started")), 1)
        for ctx in self.contexts:
            self.assertIs(ctx.prepared_step, self.views[0])
            self.assertEqual(ctx.prepared_attempt, self.views[0]._attempt)
            self.assertFalse(builtin.run_command(ctx, ["/usr/bin/true"]).ok)

    def test_production_repair_round_reuses_view_before_internal_close(self):
        backend = FakeBackend(["missing artifact", {"tool_calls": [
            {"id": "repair-command", "name": "run_command", "arguments": {"argv": ["/usr/bin/true"]}},
            {"id": "repair-artifact", "name": "submit_artifact",
             "arguments": {"name": "01_plan.md", "content": "# Repaired fixture\n"}}]},
            "done", *[json.dumps({"step": "fixture", "next_thought_needed": False}) for _ in range(6)]])
        with self.transport():
            report = self.invoke(backend)
        self.assertEqual(len(self.payloads), 1, report.error)
        self.assertGreaterEqual(len(self.contexts), 2)
        self.assertTrue(all(ctx.prepared_step is self.views[0] for ctx in self.contexts))
        self.assertTrue(any("补救" in warning for warning in report.warnings))
        self.owner_closed()

    def test_actual_engineering_gate_two_checks_and_readonly_reviewer_no_rw_view(self):
        self.make_ticket("code")
        backend = self.script(commands=2)
        original = runner._run_task_reviewer
        def review(**kwargs):
            self.assertEqual(kwargs["policy"].write_roots, ())
            self.assertNotIn("prepared_step", kwargs)
            self.assertNotIn("prepared_attempt", kwargs)
            self.assertEqual(self.views[0]._scope._consume_state, "attached_bound")
            return original(**kwargs)
        # Reviewer model responses follow the actual ordinary contract loop.
        backend = FakeBackend([
            {"tool_calls": [{"id": "ordinary", "name": "run_command",
                "arguments": {"argv": ["/usr/bin/true"]}},
                {"id": "report", "name": "submit_artifact", "arguments": {
                    "name": "04_code_review_fix.md", "content": "# Actual fixture report\n"}}]},
            "done", "repair completed",
            {"tool_calls": [{"id": "review-read", "name": "read_file",
                "arguments": {"path": "data.txt"}}]},
            {"tool_calls": [{"id": "review-submit", "name": "submit_review",
                "arguments": {"summary": "Read fixture", "findings": []}}]},
            "done", *[json.dumps({"step": "fixture", "next_thought_needed": False}) for _ in range(6)]])
        with self.transport(), patch.object(runner, "_run_task_reviewer", new=review) as reviewing:
            report = self.invoke(backend)
        self.assertIsNotNone(report.verification_evidence, report.error)
        self.assertEqual(len(report.verification_evidence.to_receipt()["run"]["checks"]), 2)
        self.assertGreaterEqual(len(self.payloads), 3)
        self.assertTrue(all(owner is self.opened[0][0] for owner in self.payloads))
        self.assertTrue(any(name == "宿主工程验收" and ok
            for name, ok, detail in report.checkpoints), report.error)
        self.assertEqual(self.views[0]._scope._consume_state, "spent")
        self.owner_closed()

    def test_external_owner_is_spent_but_active_second_runner_rejected_before_start(self):
        scope = self.resources.prepare()
        descriptor = scope._owner.fileno()
        with self.transport():
            report = self.invoke(self.script(commands=0), prepared_scope=scope)
        self.assertEqual(scope._consume_state, "spent", report.error)
        self.assertEqual(scope._owner_state, "active")
        os.fstat(descriptor)
        before = self.events("step_started")
        backend = self.script(commands=0)
        with patch.object(ControlPlane, "_step_start_result") as start:
            second = self.invoke(backend, prepared_scope=scope)
        self.assertFalse(second.ok)
        start.assert_not_called()
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.events("step_started"), before)
        self.assertEqual(scope._owner_state, "active")

    def test_real_tools_and_engineering_reject_all_public_binding_drifts(self):
        scope, view, attempt, original = self.bound_context()
        changes = [
            {"policy": None}, {"policy": replace(self.policy)},
            {"workspace_session": replace(self.session)}, {"workspace_session": None},
            {"sandbox": object()}, {"root": Path(str(self.root))},
            {"prepared_step": object()}, {"prepared_attempt": "wrong"},
            {"read_only_workspace": True},
            {"prepared_step": None, "prepared_attempt": None},
            {"policy": None, "prepared_step": None, "prepared_attempt": None}]
        for change in changes:
            for consume in ("tool", "engineering"):
                with self.subTest(change=tuple(change), consume=consume):
                    ctx = self.require_private()(self.root, self.sandbox, self.policy,
                        workspace_session=self.session, prepared_step=view, prepared_attempt=attempt)
                    for key, value in change.items():
                        setattr(ctx, key, value)
                    with patch.object(builtin, "execute_linux_resource_observed_command") as resource, \
                            patch.object(builtin, "execute_policy_command") as ordinary, \
                            patch.object(runner, "_run_unittest_with_bounded_output") as legacy, \
                            patch.object(self.sandbox, "wrap_policy") as wrapper, \
                            patch.object(prepared, "open_linux_helper_object") as factory:
                        answer = (builtin.run_command(ctx, ["/usr/bin/true"]) if consume == "tool"
                            else _execute_check(self.plan.checks[0], ctx, None))
                    if consume == "tool":
                        self.assertFalse(answer.ok)
                        self.assertIn(answer.meta.get("error"), ("isolation_unavailable", "invalid_cwd"))
                    else:
                        self.assertEqual(answer.status, "execution_unavailable")
                    for spy in (resource, ordinary, legacy, wrapper, factory):
                        spy.assert_not_called()
        self.assertEqual(scope._consume_state, "attached_bound")
        view.finish()
        self.assertFalse(builtin.run_command(original, ["/usr/bin/true"]).ok)

    def test_fresh_closed_cp_and_broken_chain_block_real_consumer_before_broker(self):
        scope, view, attempt, ctx = self.bound_context()
        self.assertIs(self.cp.step_finish(self.out, self.step, attempt, "blocked",
            ticket_id=self.ticket, request="close-control", evidence=["fixture:closed"]).data.get("ok"), True)
        with patch.object(builtin, "execute_linux_resource_observed_command") as resource:
            self.assertFalse(builtin.run_command(ctx, ["/usr/bin/true"]).ok)
            self.assertEqual(_execute_check(self.plan.checks[0], ctx, None).status, "execution_unavailable")
        resource.assert_not_called()
        self.make_ticket("plan")
        scope, view, attempt, ctx = self.bound_context()
        with (self.out / ".ico_events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("{isolated-invalid-event\n")
        with patch.object(builtin, "execute_linux_resource_observed_command") as resource:
            self.assertFalse(builtin.run_command(ctx, ["/usr/bin/true"]).ok)
        resource.assert_not_called()

    def test_raw_or_bind_failure_finishes_pending_and_closes_internal_owner_no_model(self):
        original = ControlPlane._step_start_result
        def bad_start(control, *args, **kwargs):
            result = original(control, *args, **kwargs)
            return replace(result, data=dict(result.data, attempt=True))
        backend = self.script()
        with self.transport(), patch.object(ControlPlane, "_step_start_result", new=bad_start):
            report = self.invoke(backend)
        self.assertFalse(report.ok)
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.views[0]._scope._consume_state, "spent")
        self.owner_closed()
        self.no_terminal()

    def terminal_case(self, branch, *, unknown=False, external_unknown=False):
        if branch in ("engineering_budget", "engineering_failure"):
            self.make_ticket("code")
        supplied = self.resources.prepare() if external_unknown else None
        descriptor = supplied._owner.fileno() if supplied is not None else None
        backend = self.script(commands=0)
        with ExitStack() as stack:
            if branch == "ordinary_budget":
                stack.enter_context(patch.object(runner, "_run_agent",
                    return_value=LoopResult(False, "budget_exceeded")))
            elif branch == "repair_budget":
                stack.enter_context(patch.object(runner, "_run_agent", side_effect=[
                    LoopResult(True, "done"),
                    LoopResult(False, "budget_exceeded")]))
            elif branch in ("engineering_budget", "engineering_failure"):
                def gate(**kwargs):
                    kwargs["report"].error = ("budget_exceeded" if branch == "engineering_budget"
                        else "engineering_verification_failed")
                    return False
                stack.enter_context(patch.object(runner, "_contract_engineering_gate", side_effect=gate))
            elif branch == "deliberation_budget":
                stack.enter_context(patch.object(runner, "_prepare_deliberation",
                    return_value=SimpleNamespace(budget_exceeded=True)))
            original_finish = prepared._LinuxStepAttachment.finish
            original_close = prepared.LinuxPreparedStep.close
            finish_calls, close_calls = [], []
            def finish(view):
                finish_calls.append(view)
                if unknown:
                    raise OSError("private finish body")
                if external_unknown:
                    # Caller-owned close races with its actual view finish; no field injection.
                    with self.assertRaises(prepared.LinuxPreparedStepError):
                        supplied.close()
                return original_finish(view)
            def close(scope):
                close_calls.append(scope)
                return original_close(scope)
            stack.enter_context(patch.object(prepared._LinuxStepAttachment, "finish", new=finish))
            stack.enter_context(patch.object(prepared.LinuxPreparedStep, "close", new=close))
            owner_closes = []
            if external_unknown:
                real_owner_close = fixture.factory.LinuxHelperObject.close
                def failed_owner_close(owner):
                    owner_closes.append(owner)
                    real_owner_close(owner)
                    raise OSError("external owner close confirmation failed")
                stack.enter_context(patch.object(fixture.factory.LinuxHelperObject, "close",
                    new=failed_owner_close))
            original_terminal = ControlPlane.step_finish
            terminal_calls = []
            def terminal(control, *args, **kwargs):
                caller = inspect.currentframe().f_back.f_code.co_name
                expected = ("_stop_contract_for_budget" if branch.endswith("budget")
                    else "_finish_step")
                self.assertEqual(caller, expected)
                if not external_unknown:
                    self.assertEqual(len(finish_calls), 1)
                    self.assertEqual(len(close_calls), 1)
                    self.assertEqual(self.views[0]._scope._consume_state, "spent")
                    self.owner_closed()
                # An external regression must reach actual CP; the spy never blocks it.
                result = original_terminal(control, *args, **kwargs)
                terminal_calls.append(result)
                return result
            stack.enter_context(patch.object(ControlPlane, "step_finish", new=terminal))
            selected_agent = runner._run_agent
            def checkpointed_agent(**kwargs):
                kwargs["checkpointer"].save(turn_index=0, tool_calls=0, history=[])
                return selected_agent(**kwargs)
            stack.enter_context(patch.object(runner, "_run_agent", side_effect=checkpointed_agent))
            original_clear = runner.Checkpointer.clear
            clearing = stack.enter_context(patch.object(runner.Checkpointer, "clear",
                autospec=True, side_effect=original_clear))
            with self.transport():
                report = self.invoke(backend, **({"prepared_scope": supplied}
                    if external_unknown else {}))
        self.assertEqual(len(finish_calls), 1)
        self.assertEqual(len(close_calls), 1)
        if external_unknown:
            self.assertEqual(close_calls, [supplied])
            self.assertEqual(owner_closes, [supplied._owner])
            self.assertEqual(supplied._owner_state, "unknown")
            self.assertEqual(supplied._consume_state, "spent")
            self.assertEqual(self.opened, [])
            with self.assertRaises(OSError) as caught:
                os.fstat(descriptor)
            self.assertEqual(caught.exception.errno, errno.EBADF)
            self.session.lease._validate_active()
            os.fstat(self.session.workspace_fd)
        else:
            self.owner_closed()
        if unknown or external_unknown:
            self.assertEqual(terminal_calls, [])
            self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
            self.no_terminal()
            clearing.assert_not_called()
            from icode.checkpoint import CHECKPOINT_NAME
            saved = json.loads((self.out / CHECKPOINT_NAME).read_text(encoding="utf-8"))
            self.assertEqual(saved["attempt"], self.opened_attempt())
            self.assertEqual(saved["step"], self.step)
        else:
            self.assertTrue(terminal_calls, (branch, report.error))
        print("software-terminal-fixture " + json.dumps(dict(branch=branch, unknown=unknown,
            external_unknown=external_unknown,
            terminal_calls=len(terminal_calls), actual_finish_events=len(self.events("step_finished")),
            status=self.cp.trace(self.out).data["status"],
            finish_attempts=len(finish_calls), close_attempts=len(close_calls)), sort_keys=True))
        return report

    def test_six_real_terminal_sites_cleanup_before_cp_and_unknown_never_finish(self):
        for branch in ("ordinary_budget", "repair_budget", "engineering_budget",
                "engineering_failure", "deliberation_budget", "normal"):
            for unknown in (False, True):
                with self.subTest(branch=branch, unknown=unknown):
                    # Fresh isolated fixture for each terminal; no reused attempt/owner.
                    case = type(self)(methodName="runTest")
                    case.setUp()
                    try:
                        case.terminal_case(branch, unknown=unknown)
                    finally:
                        case.doCleanups()

    def test_external_real_close_unknown_blocks_all_six_terminals_and_checkpoint_clear(self):
        for branch in ("ordinary_budget", "repair_budget", "engineering_budget",
                "engineering_failure", "deliberation_budget", "normal"):
            with self.subTest(branch=branch):
                case = type(self)(methodName="runTest")
                case.setUp()
                try:
                    case.terminal_case(branch, external_unknown=True)
                finally:
                    case.doCleanups()

    def test_external_real_close_unknown_overrides_ordinary_body_error_without_runner_retry(self):
        scope = self.resources.prepare()
        descriptor = scope._owner.fileno()
        owner_closes = []
        real_owner_close = fixture.factory.LinuxHelperObject.close
        def failed_owner_close(owner):
            owner_closes.append(owner)
            real_owner_close(owner)
            raise OSError("external owner close confirmation failed")
        def post(*args):
            with self.assertRaises(prepared.LinuxPreparedStepError):
                scope.close()
            raise OSError("ordinary post body")
        original_finish = prepared._LinuxStepAttachment.finish
        with self.transport(), patch.object(fixture.factory.LinuxHelperObject, "close",
                new=failed_owner_close), patch.object(scope, "close", wraps=scope.close) as closing, \
                patch.object(prepared._LinuxStepAttachment, "finish", autospec=True,
                    side_effect=original_finish) as finishing, \
                patch.object(ControlPlane, "step_finish", wraps=ControlPlane.step_finish) as terminal, \
                patch.object(runner.Checkpointer, "clear") as clearing:
            report = self.invoke(self.script(commands=0), prepared_scope=scope, post_write=post)
        self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
        closing.assert_called_once_with()
        finishing.assert_called_once_with(self.views[0])
        self.assertEqual(owner_closes, [scope._owner])
        self.assertEqual(scope._owner_state, "unknown")
        self.assertEqual(scope._consume_state, "spent")
        terminal.assert_not_called()
        clearing.assert_not_called()
        self.no_terminal()
        from icode.checkpoint import CHECKPOINT_NAME
        saved = json.loads((self.out / CHECKPOINT_NAME).read_text(encoding="utf-8"))
        self.assertEqual(saved["attempt"], self.opened_attempt())
        self.assertEqual(saved["step"], self.step)
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptor)
        self.assertEqual(caught.exception.errno, errno.EBADF)
        self.session.lease._validate_active()
        os.fstat(self.session.workspace_fd)

    def test_faulted_finish_silent_does_not_grant_health_or_cp_terminal(self):
        def post(*args):
            self.views[0]._scope._consume_state = "faulted"
        with self.transport():
            report = self.invoke(self.script(commands=0), post_write=post)
        self.assertFalse(report.ok)
        self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
        self.assertEqual(self.views[0]._scope._consume_state, "faulted")
        self.owner_closed()
        self.no_terminal()

    def test_attach_failure_closes_owner_once_without_start_model_or_payload(self):
        backend = self.script()
        with self.transport(), patch.object(prepared.LinuxPreparedStep, "_attach",
                side_effect=OSError("private attach")) as attach, \
                patch.object(ControlPlane, "_step_start_result") as start:
            report = self.invoke(backend)
        self.assertFalse(report.ok)
        attach.assert_called_once()
        start.assert_not_called()
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.payloads, [])
        self.owner_closed()

    def test_body_cleanup_compound_errors_close_unknown_once_first_signal_identity(self):
        for body in (OSError("body"), KeyboardInterrupt("first-body"), SystemExit(7)):
            for finish_error in (OSError("finish"), KeyboardInterrupt("first-cleanup")):
                with self.subTest(body=type(body).__name__, finish=type(finish_error).__name__):
                    case = type(self)(methodName="runTest")
                    case.setUp()
                    attempts = []
                    real_owner_close = fixture.factory.LinuxHelperObject.close
                    def unknown(owner):
                        attempts.append(owner)
                        # Inject confirmed OS close followed by unknown report; never retry integer.
                        real_owner_close(owner)
                        raise SystemExit("later-close")
                    try:
                        with case.transport(), patch.object(runner, "_run_agent", side_effect=body), \
                                patch.object(prepared._LinuxStepAttachment, "finish", side_effect=finish_error), \
                                patch.object(fixture.factory.LinuxHelperObject, "close", new=unknown):
                            expected = body if not isinstance(body, Exception) else (
                                finish_error if not isinstance(finish_error, Exception) else None)
                            if expected is not None:
                                with case.assertRaises(type(expected)) as caught:
                                    case.invoke()
                                case.assertIs(caught.exception, expected)
                            else:
                                with case.assertRaises(SystemExit) as caught:
                                    case.invoke()
                                case.assertEqual(caught.exception.code, "later-close")
                        case.assertEqual(len(attempts), 1)
                        case.assertEqual(case.views[0]._scope._owner_state, "unknown")
                        case.no_terminal()
                    finally:
                        case.doCleanups()

    def test_ordinary_body_cannot_hide_cleanup_unknown_postwrite_and_no_retry(self):
        attempts = []
        original_close = fixture.factory.LinuxHelperObject.close
        def unknown(owner):
            attempts.append(owner)
            original_close(owner)
            raise OSError("private close")
        def post(*args):
            raise OSError("private post")
        with self.transport(), patch.object(fixture.factory.LinuxHelperObject, "close", new=unknown):
            report = self.invoke(self.script(commands=0), post_write=post)
        self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.views[0]._scope._owner_state, "unknown")
        self.no_terminal()

    def test_wrong_scope_refs_and_sources_reject_before_model_no_replacement_owner(self):
        scope = self.resources.prepare()
        for changes in ({"policy": replace(self.policy)}, {"workspace_session": replace(self.session)},
                {"sandbox": object()}, {"policy": None}, {"workspace_session": None}):
            with patch.object(ControlPlane, "_step_start_result") as start, \
                    patch.object(prepared, "open_linux_helper_object") as opening:
                backend = self.script()
                report = self.invoke(backend, prepared_scope=scope, **changes)
            self.assertFalse(report.ok)
            self.assertEqual(backend.calls, [])
            start.assert_not_called()
            opening.assert_not_called()
        self.assertEqual(scope._consume_state, "prepared")
        self.resources.write_image(fixture.image((1, 1)))
        with patch.object(ControlPlane, "_step_start_result") as start:
            report = self.invoke(self.script(), prepared_scope=scope)
        self.assertFalse(report.ok)
        start.assert_not_called()

    def test_chain_single_step_same_reference_none_callback_shape_and_bad_order(self):
        self.assertIn("prepared_scope", inspect.signature(chain.run_chain).parameters,
            "chain prepared lifecycle keyword missing")
        scope = self.resources.prepare()
        sentinel = runner.StepReport("plan", False, str(self.out), error="fixture-stop")
        original = chain.run_contract_step
        with patch.object(chain, "run_contract_step", return_value=sentinel) as callback:
            chain.run_chain(self.settings, backend=FakeBackend([]), workspace=self.root,
                requirement="fixture", ticket_id=self.ticket, out_dir=self.out, steps=("plan",),
                policy=self.policy, sandbox=self.sandbox, workspace_session=self.session,
                prepared_scope=scope, approver=ScriptedApprover(default=True))
        self.assertIs(callback.call_args.kwargs["prepared_scope"], scope)
        self.assertEqual(scope._consume_state, "prepared")
        with patch.object(chain, "run_contract_step", return_value=sentinel) as callback:
            chain.run_chain(self.settings, backend=FakeBackend([]), workspace=self.root,
                requirement="fixture", ticket_id=self.ticket, out_dir=self.out, steps=("plan",),
                policy=self.policy, sandbox=self.sandbox, workspace_session=self.session)
        self.assertNotIn("prepared_scope", callback.call_args.kwargs)
        with patch.object(chain, "run_contract_step") as callback:
            with self.assertRaises(ValueError):
                chain.run_chain(self.settings, backend=FakeBackend([]), workspace=self.root,
                    requirement="fixture", ticket_id=self.ticket, out_dir=self.out,
                    steps=("plan", "review"), policy=self.policy, sandbox=self.sandbox,
                    workspace_session=self.session, prepared_scope=scope)
        callback.assert_not_called()
        with self.transport(), patch.object(chain, "run_contract_step", wraps=original):
            report = chain.run_chain(self.settings, backend=self.script(), workspace=self.root,
                requirement="fixture", ticket_id=self.ticket, out_dir=self.out, steps=("plan",),
                policy=self.policy, sandbox=self.sandbox, workspace_session=self.session,
                prepared_scope=scope, approver=ScriptedApprover(default=True))
        self.assertEqual(scope._consume_state, "spent", report.reason)
        self.assertEqual(scope._owner_state, "active")
        self.assertEqual(len(self.payloads), 2)

    def test_none_no_session_explicit_nonpackage_legacy_and_original_make_ctx_shape(self):
        for session in (None, self.session):
            sandbox = self.sandbox if session is None else type(self.sandbox)(
                "/usr/bin/true", manifest="/usr/bin/true")
            with patch.object(prepared, "prepare_linux_step") as opening, \
                    patch.object(runner, "_run_agent", return_value=LoopResult(False, "budget_exceeded")) as run:
                report = self.invoke(workspace_session=session, sandbox=sandbox)
            opening.assert_not_called()
            self.assertNotIn("prepared_step", run.call_args.kwargs)
            self.assertNotIn("prepared_attempt", run.call_args.kwargs)
        old = dict(root=self.root, sandbox=self.sandbox, policy=self.policy,
            artifact_broker=None, change_baseline=None, read_only_workspace=False,
            review_submission_enabled=False, deny_read_roots=(), allowed_read_files=None,
            workspace_session=self.session)
        for view, attempt in ((None, None), (object(), "old-attempt"), (None, "")):
            with patch.object(runner, "ToolContext") as constructor:
                runner._make_ctx(self.root, self.sandbox, self.policy,
                    workspace_session=self.session, prepared_step=view, prepared_attempt=attempt)
            expected = dict(old)
            if view is not None or attempt is not None:
                expected.update(prepared_step=view, prepared_attempt=attempt)
            self.assertEqual(constructor.call_args.kwargs, expected)
        ctx = ToolContext(self.root, sandbox=None, policy=None)
        with patch.object(runner, "_run_unittest_with_bounded_output",
                return_value=(0, b"Ran 1 test in 0.01s\n\nOK\n", b"")):
            self.assertEqual(_execute_check(self.plan.checks[0], ctx, None).status, "passed")

    def test_silent_finish_external_bound_is_unknown_and_first_cleanup_signal_survives(self):
        scope = self.resources.prepare()
        with self.transport(), patch.object(prepared._LinuxStepAttachment, "finish", return_value=None):
            report = self.invoke(self.script(commands=0), prepared_scope=scope)
        self.assertEqual(report.error, "prepared_cleanup_unconfirmed")
        self.assertEqual(scope._consume_state, "attached_bound")
        self.assertEqual(scope._owner_state, "active")
        self.no_terminal()
        for signal in (KeyboardInterrupt("cleanup-first"), SystemExit(4)):
            case = type(self)(methodName="runTest")
            case.setUp()
            try:
                with case.transport(), patch.object(prepared._LinuxStepAttachment, "finish",
                        side_effect=signal):
                    with case.assertRaises(type(signal)) as caught:
                        case.invoke(case.script(commands=0))
                case.assertIs(caught.exception, signal)
                case.owner_closed()
                case.no_terminal()
            finally:
                case.doCleanups()

    def test_actual_resume_reads_cp_checkpoint_without_prepared_restore_or_start(self):
        self.require_private()
        from icode.checkpoint import Checkpointer
        def post(*args):
            raise OSError("ordinary interrupted fixture")
        with self.transport():
            report = self.invoke(self.script(commands=0), post_write=post)
        attempt = self.opened_attempt()
        checkpoint = Checkpointer(self.out, ticket_id=self.ticket, step=self.step, attempt=attempt)
        self.assertTrue(checkpoint.exists())
        saved = json.loads(checkpoint.path.read_text(encoding="utf-8"))
        self.assertNotIn("prepared_scope", saved)
        self.assertNotIn("prepared_step", saved)
        self.assertNotIn("prepared_attempt", saved)
        self.assertEqual(self.views[0]._scope._consume_state, "spent")
        original = runner._run_agent
        with patch.object(prepared, "prepare_linux_step") as opening, \
                patch.object(ControlPlane, "_step_start_result") as start, \
                patch.object(runner, "_make_prepared_ctx") as prepared_ctx, \
                patch.object(runner, "_run_agent", wraps=original) as resumed:
            runner.resume_contract_step(self.settings, backend=self.script(commands=0),
                out_dir=self.out, step=self.step, ticket_id=self.ticket, workspace=self.root,
                sandbox=self.sandbox, policy=self.policy, workspace_session=self.session)
        opening.assert_not_called()
        start.assert_not_called()
        prepared_ctx.assert_not_called()
        self.assertTrue(resumed.call_args_list)
        self.assertNotIn("prepared_step", resumed.call_args.kwargs)
        self.assertNotIn("prepared_attempt", resumed.call_args.kwargs)
        self.assertEqual(len(self.events("step_started")), 1)

    def test_pure_admission_reviewer_resume_readyfalse_never_claim_rw_scope(self):
        self.make_ticket("code")
        scope = self.resources.prepare()
        with patch.object(prepared, "prepare_linux_step") as opening, \
                patch.object(scope, "_attach") as attaching:
            self.assertEqual(runner._contract_plan_error(self.plan, self.root, self.step,
                self.ticket, self.policy, self.sandbox, self.session), "")
        opening.assert_not_called()
        attaching.assert_not_called()
        self.assertEqual(scope._consume_state, "prepared")
        self.assertNotIn("prepared_scope", inspect.signature(runner.resume_contract_step).parameters)
        from icode.autonomy import ExecutionContext, NativeChainExecutor
        backend = FakeBackend(["must not run"])
        provider = Mock(return_value=self.plan)
        executor = NativeChainExecutor(self.settings, backend=backend, sandbox=self.sandbox,
            verification_plan_provider=provider)
        context = ExecutionContext(self.ticket, self.out, self.root, "fixture",
            self.cp.trace(self.out).data["status"], ())
        control = SimpleNamespace(session=self.session, ticket_id=self.ticket,
            run_id=self.session.run_id, safe_point=lambda step: None)
        with patch.object(executor, "_step_runner") as step_runner, \
                patch.object(ControlPlane, "_step_start_result") as start, \
                patch.object(prepared, "prepare_linux_step") as opening:
            result = executor.execute(context, control)
        self.assertFalse(self.sandbox.policy_contract_ready)
        self.assertEqual(result.state, "blocked")
        self.assertEqual(result.error_code, "isolation_unavailable")
        provider.assert_not_called()
        step_runner.assert_not_called()
        start.assert_not_called()
        opening.assert_not_called()
        self.assertEqual(backend.calls, [])

    def test_nonlinux_legacy_runner_callable_and_unresolved_candidate_never_fallback(self):
        for platform in ("darwin", "win32"):
            with self.subTest(platform=platform):
                self.make_ticket("plan")
                with patch.object(sys, "platform", platform), \
                        patch.object(prepared, "prepare_linux_step") as opening, \
                        patch.object(runner, "_run_agent", return_value=LoopResult(
                            False, "budget_exceeded")) as run:
                    report = self.invoke()
                self.assertEqual(report.finish_outcome, "failure", report.error)
                opening.assert_not_called()
                self.assertNotIn("prepared_step", run.call_args.kwargs)
                self.assertNotIn("prepared_attempt", run.call_args.kwargs)
        self.make_ticket("plan")
        missing = self.resources.binary.with_name("isolated-helper-moved")
        self.resources.binary.rename(missing)
        try:
            backend = self.script()
            with patch.object(ControlPlane, "_step_start_result") as raw, \
                    patch.object(ControlPlane, "step_start") as public, \
                    patch.object(prepared, "prepare_linux_step") as opening, \
                    patch.object(runner, "_run_agent") as run:
                report = self.invoke(backend)
            self.assertFalse(report.ok)
            self.assertIn("Linux prepared step is unavailable", report.error)
            for spy in (raw, public, opening, run):
                spy.assert_not_called()
            self.assertEqual(backend.calls, [])
        finally:
            missing.rename(self.resources.binary)

    def test_actual_candidate_factory_failure_no_start_model_legacy_or_replacement_owner(self):
        self.assertIn("prepared_scope", inspect.signature(runner.run_contract_step).parameters)
        backend = self.script()
        with patch.object(prepared, "open_linux_helper_object", side_effect=OSError("private factory")) as factory, \
                patch.object(ControlPlane, "_step_start_result") as raw, \
                patch.object(ControlPlane, "step_start") as public, \
                patch.object(runner, "_run_agent") as agent, \
                patch.object(builtin, "execute_policy_command") as ordinary:
            report = self.invoke(backend)
        self.assertFalse(report.ok)
        self.assertIn("Linux prepared step is unavailable", report.error)
        factory.assert_called_once()
        for spy in (raw, public, agent, ordinary):
            spy.assert_not_called()
        self.assertEqual(backend.calls, [])
        self.assertEqual(self.events("step_started"), [])
        self.assertEqual(self.events("step_finished"), [])


if __name__ == "__main__":
    unittest.main()
```

## Task 2: 仅两 SOURCE 差分及作者/root GREEN

**状态**
- [x] 任务完成（两 SOURCE、双方GREEN/限定回归、fresh双审；发布门另列Task3）

**Dependencies:** Task 1
**Parallelizable:** No (正式有效 RED 后由不同 SOURCE 作者执行)

- [ ] **Step 1:** SOURCE 作者核 Task 1 原始作者/root RED、frozen TEST SHA、实际 runner/chain 原 hash 完全相等，以 apply_patch 应用下面两个完整 unified diff。不能修改 `_make_ctx`、共享 budget/finish/finalize/resume、旧 tests、tools/工程/scope 实现。
- [ ] **Step 2:** `.venv/bin/python -m unittest tests.test_linux_prepared_runner_lifecycle -v` 得到 GREEN、exit0、0 ERROR；root 独立重复新 TEST。新 TEST 同时覆盖真实普通/补救、工程两 check/Reviewer、真实 CP 六出口与 compound cleanup。若失败，保持测试断言，修两 SOURCE；六范围无法满足时报告真实 gap，重新设计独立审查。
- [ ] **Step 3:** 作者/root 执行限定回归：

```bash
.venv/bin/python -m unittest tests.test_linux_prepared_runner_lifecycle tests.test_linux_prepared_tool_context tests.test_linux_prepared_control_attempt tests.test_linux_prepared_step tests.test_linux_prepared_broker tests.test_contract_engineering tests.test_chain tests.test_shared_runtime_budget tests.test_control tests.test_runner -v
```

预期 exit0、0 FAIL/ERROR；非 Linux skip 不授能力。此回归只软件层，不自行启动 native/installed/CI/KEY/model 或完整 guard。root 根据现有必要回归契约补齐普通工具、工程/workspace-FD、S1/B2相关门，不能用 broad test 重复替代具体缺口。
- [ ] **Step 4:** SOURCE 作者 built-in SPEC 自审（逐条核 DESIGN）→QUALITY 自审（签名、一次回收、固定错误、旧 callbacks 形状）。两阶段无问题才回报，并给 root 源码/TEST SHA、用例数/skip/耗时/原日志/footer。root fresh SOURCE SPEC→不同 QUALITY 均 C0/I0/M0 后冻结。

### 完整两 SOURCE unified diff 资产

```diff
--- a/src/icode/runner.py
+++ b/src/icode/runner.py
@@ -1217,6 +1217,7 @@
     out_dir: Path | None = None,
     extra_instructions: str = "",
     post_write: "Callable[[Path, str, str], None] | None" = None,
+    prepared_scope: object | None = None,
 ) -> StepReport:
     """按契约执行一个步骤，模型通过工具循环完成该步骤的产物。
-
+
@@ -1238,8 +1239,48 @@
         if error:
             return StepReport(step=step, ok=False, out_dir=str(out_dir or ""), error=error)
     engineering = policy is not None and step in ("code", "deepcheck")
+    owned_scope, view, prepared_options = None, None, {}
+    internally_owned, cleanup_attempted, cleanup_error, body_signal = False, False, None, None
     cp = ControlPlane(settings)
     report = StepReport(step=step, ok=False, out_dir="")
+
+    def finish_prepared():
+        nonlocal cleanup_attempted, cleanup_error
+        if owned_scope is None:
+            return True
+        if not cleanup_attempted:
+            cleanup_attempted = True
+            errors = []
+            if owned_scope._consume_state == "faulted":
+                errors.append(RuntimeError("prepared_cleanup_unconfirmed"))
+            if view is not None:
+                try:
+                    view.finish()
+                    if owned_scope._consume_state != "spent":
+                        errors.append(RuntimeError("prepared_cleanup_unconfirmed"))
+                except BaseException as error:
+                    errors.append(error)
+            if internally_owned:
+                try:
+                    owned_scope.close()
+                except BaseException as error:
+                    errors.append(error)
+            if (owned_scope._consume_state == "faulted"
+                    or owned_scope._owner_state != ("closed" if internally_owned else "active")):
+                errors.append(RuntimeError("prepared_cleanup_unconfirmed"))
+            # Preserve the first KI/SE; ordinary failures cannot hide unknown cleanup.
+            cleanup_error = next((error for error in errors
+                                  if not isinstance(error, Exception)), errors[0] if errors else None)
+        if body_signal is not None:
+            return False
+        if cleanup_error is not None:
+            if not isinstance(cleanup_error, Exception):
+                raise cleanup_error
+            report.ok = False
+            report.error = "prepared_cleanup_unconfirmed"
+            report.add("准备资源收尾确认", False, report.error)
+            return False
+        return True
-
+
     # `step-run --step review` does not go through chain.py's post hook.  Keep
     # the same machine-owned manifest contract for that public entry point:
@@ -1316,13 +1357,21 @@
                     report.error = "中间状态流转未通过，未启动步骤"
                     return report
-
+
-        attempt = cp.step_start(
-            out_dir, step, ticket_id=ticket_id,
-            request=_step_start_request(
-                cp, out_dir, step, ticket_id,
-                trace_result=(state if in_prog else None),
-            ),
-        )
+        owned_scope, internally_owned = _prepared_scope_for_call(
+            workspace, step, ticket_id, sandbox, policy, workspace_session, prepared_scope)
+        request = _step_start_request(cp, out_dir, step, ticket_id,
+                                      trace_result=(state if in_prog else None))
+        if owned_scope is None:
+            attempt = cp.step_start(out_dir, step, ticket_id=ticket_id, request=request)
+        else:
+            from .linux_prepared_control import _prepared_control_attempt_binding
+
+            view = owned_scope._attach(policy=policy, workspace_session=workspace_session)
+            raw = cp._step_start_result(out_dir, step, ticket_id=ticket_id, request=request)
+            attempt, observer = _prepared_control_attempt_binding(
+                cp, out_dir=out_dir, ticket_id=ticket_id, step=step, start_result=raw)
+            view._bind_attempt(attempt, validate_attempt=observer)
+            prepared_options = {"prepared_step": view, "prepared_attempt": attempt}
         report.add("step start", bool(attempt), f"attempt={attempt}")
-
+
         # 检查点：让中断后可恢复（不保存模型正文）
@@ -1366,9 +1415,12 @@
                     change_baseline=change_baseline,
                     inspection_runner=_bound_inspection_runner(
                         cp, out_dir, ticket_id, step, attempt),
+                    **prepared_options,
                 )
                 report.loop = loop
                 if loop.stop_reason == "budget_exceeded":
+                    if not finish_prepared():
+                        return report
                     return _stop_contract_for_budget(cp, out_dir, step, attempt, ticket_id, report)
                 if not loop.ok:
                     # 由**证据**判定成败，而不是由循环的停止原因判定：
@@ -1450,9 +1502,12 @@
                             cp, out_dir, ticket_id, step, attempt),
                         extra_instructions=repair_instructions,
                         operations=step_ops,
+                        **prepared_options,
                     )
                     report.loop = repair
                     if repair.stop_reason == "budget_exceeded":
+                        if not finish_prepared():
+                            return report
                         return _stop_contract_for_budget(cp, out_dir, step, attempt, ticket_id, report)
                     if post_write is not None:
                         post_write(out_dir, step, attempt)
@@ -1494,15 +1549,22 @@
                     workspace=workspace, baseline=engineering_baseline,
                     git_baseline=engineering_git_baseline, operations=step_ops,
                     backend=backend, requirement=requirement or DEFAULT_TASK,
-                    loop_config=loop_config, budget_tracker=budget_tracker):
+                    loop_config=loop_config, budget_tracker=budget_tracker,
+                    **prepared_options):
                 if report.error == "budget_exceeded":
+                    if not finish_prepared():
+                        return report
                     return _stop_contract_for_budget(cp, out_dir, step, attempt, ticket_id, report)
+                if not finish_prepared():
+                    return report
                 _finish_step(cp, out_dir, step, attempt, ticket_id, report, missing)
                 return report
-
+
         deliberation = _prepare_deliberation(settings, backend, step, report,
                                              requirement or DEFAULT_TASK, budget_tracker)
         if getattr(deliberation, "budget_exceeded", False):
+            if not finish_prepared():
+                return report
             return _stop_contract_for_budget(cp, out_dir, step, attempt, ticket_id, report)
         _record_deliberation(settings, out_dir, step, ticket_id, report, deliberation)
         if engineering:
@@ -1512,6 +1574,11 @@
             if error:
                 report.error = error
                 report.add("终结前工程绑定重核", False, error)
+        if view is not None:
+            _make_prepared_ctx(workspace, sandbox, policy, workspace_session=workspace_session,
+                               **prepared_options)
+        if not finish_prepared():
+            return report
         _finish_step(cp, out_dir, step, attempt, ticket_id, report, missing)
         if report.finish_outcome == "success":
             ckpt.clear()  # 步骤已干净终结，检查点不再需要
@@ -1520,8 +1587,15 @@
         return report
-
+
     except Exception as exc:  # noqa: BLE001
-        report.error = "engineering_execution_unconfirmed" if engineering else f"{type(exc).__name__}: {exc}"
+        report.error = ("prepared_execution_unconfirmed" if owned_scope is not None or prepared_scope is not None
+                        else "engineering_execution_unconfirmed" if engineering else f"{type(exc).__name__}: {exc}")
         return report
+
+    except BaseException as signal_error:
+        body_signal = signal_error
+        raise
+    finally:
+        finish_prepared()
-
+
-
+
 def _contract_plan_error(plan, workspace, step, ticket_id, policy, sandbox, session) -> str:
@@ -1792,6 +1866,7 @@
     *, cp, out_dir, ticket_id, step, attempt, report, plan, policy, sandbox,
     workspace_session, workspace, baseline, git_baseline, operations, backend,
     requirement, loop_config, budget_tracker,
+    prepared_step=None, prepared_attempt=None,
 ) -> bool:
     """One final host window after all writes, followed by a separate code Reviewer."""
     from .evidence import save_verification_receipt
@@ -1806,7 +1881,10 @@
         report.error = "budget_exceeded"
         return False
     plan_digest = plan.digest
-    ctx = _make_ctx(workspace, sandbox, policy, workspace_session=workspace_session)
+    ctx = (_make_ctx(workspace, sandbox, policy, workspace_session=workspace_session)
+           if prepared_step is None else _make_prepared_ctx(
+               workspace, sandbox, policy, workspace_session=workspace_session,
+               prepared_step=prepared_step, prepared_attempt=prepared_attempt))
     # An operation attempt is distinct from the CP step attempt. Its name binds
     # the latter so a later CP attempt cannot replay an earlier managed action.
     operation_name = "engineering-" + _sha256_text(step + "|" + attempt)
@@ -2169,6 +2247,95 @@
         report.add("step finish（被门禁拒绝，如实上报）", False, detail[:160])
-
+
-
+
+def _prepared_scope_for_call(workspace, step, ticket_id, sandbox, policy, session, supplied):
+    """Classify source before prepare; failed candidates never become legacy."""
+    from .isolation import LandlockSandbox
+    from .linux_prepared_step import LinuxPreparedStep, LinuxPreparedStepError, prepare_linux_step
+    from .linux_helper_source import _source_paths
+    from . import native_helper
+
+    if supplied is not None:
+        if (not isinstance(supplied, LinuxPreparedStep) or step == "review"
+                or supplied._sandbox is not sandbox or supplied._policy is not policy
+                or supplied._session is not session or policy is None
+                or policy.workspace_root != workspace or policy.step != step
+                or policy.ticket_id != ticket_id or supplied._consume_state != "prepared"):
+            raise LinuxPreparedStepError()
+        supplied._check(policy=policy, workspace_session=session)
+        return supplied, False
+    if (not sys.platform.startswith("linux") or not isinstance(sandbox, LandlockSandbox)
+            or session is None or policy is None or step == "review"):
+        return None, False
+    try:
+        # Resolve failures are unknown candidates, never evidence of legacy source.
+        module = Path(native_helper.__file__).resolve(strict=True)
+        native = module.parent / "native"
+        helper = Path(sandbox.helper).resolve(strict=True)
+        manifest = (Path(sandbox.manifest).resolve(strict=True)
+                    if sandbox.manifest is not None else None)
+        if helper != native / "icode-landlock" and manifest != native / "icode-landlock.sha256":
+            return None, False
+        _source_paths(sandbox)
+        scope = prepare_linux_step(sandbox, policy=policy, workspace_session=session)
+        return scope, True
+    except Exception:
+        raise LinuxPreparedStepError() from None
+
+
+class _PreparedToolContext(ToolContext):
+    """Trusted runner stack binding survives mutations of public context fields."""
+
+    def __init__(self, *args, **kwargs):
+        super().__init__(*args, **kwargs)
+        self._prepared_binding = (self.prepared_step, self.prepared_attempt, self.policy,
+                                  self.workspace_session, self.sandbox, self.root)
+        self._check_prepared_binding()
+
+    def _check_prepared_binding(self):
+        from .linux_prepared_step import _LinuxStepAttachment
+        from .tools.base import IsolationUnavailable
+
+        try:
+            view, attempt, policy, session, sandbox, root = self._prepared_binding
+            if (not isinstance(view, _LinuxStepAttachment)
+                    or self.prepared_step is not view or self.prepared_attempt != attempt
+                    or type(self.prepared_attempt) is not str or self.policy is not policy
+                    or self.workspace_session is not session or self.sandbox is not sandbox
+                    or self.root is not root or self.read_only_workspace):
+                raise ValueError("binding")
+            scope = view._current()
+            if (scope._consume_state != "attached_bound" or scope._sandbox is not sandbox
+                    or policy is None or policy.workspace_root != root):
+                raise ValueError("binding")
+            scope._check(policy=policy, workspace_session=session)
+            view._validate_attempt(attempt)
+        except Exception:
+            raise IsolationUnavailable("准备对象工具上下文不可用") from None
+
+    def _policy_command_wrapper(self):
+        self._check_prepared_binding()
+        return super()._policy_command_wrapper()
+
+    def wrap_command(self, argv, *, network=False):
+        from .tools.base import IsolationUnavailable
+
+        # Policy=None legacy consumption cannot erase the captured prepared binding.
+        raise IsolationUnavailable("准备对象工具上下文不可用") from None
+
+
+def _make_prepared_ctx(
+    workspace, sandbox, policy, artifact_broker=None, change_baseline=None,
+    *, workspace_session, prepared_step, prepared_attempt, read_only_workspace=False,
+    deny_read_roots=(),
+):
+    return _PreparedToolContext(
+        root=workspace, sandbox=sandbox, policy=policy, artifact_broker=artifact_broker,
+        change_baseline=change_baseline, workspace_session=workspace_session,
+        prepared_step=prepared_step, prepared_attempt=prepared_attempt,
+        read_only_workspace=read_only_workspace, deny_read_roots=deny_read_roots,
+    )
+
+
 def _make_ctx(
     workspace: Path, sandbox: Sandbox | None, policy: SandboxPolicy | None = None,
     artifact_broker: ArtifactBroker | None = None,
@@ -2408,6 +2575,7 @@
     budget_tracker: BudgetTracker | None = None,
     workspace_session: WorkspaceSession | None = None,
     inspection_runner=None,
+    prepared_step=None, prepared_attempt=None,
 ) -> LoopResult:
     read_only_workspace = step == "review"
     deny_read_roots = list(policy.deny_read_roots if policy is not None else ())
@@ -2442,11 +2610,15 @@
         deny_write_roots=policy.deny_write_roots if policy is not None else (),
     )
     guard = Guard(scope)
-    ctx = _make_ctx(
+    context_factory = _make_ctx if prepared_step is None else _make_prepared_ctx
+    context_options = {} if prepared_step is None else {
+        "prepared_step": prepared_step, "prepared_attempt": prepared_attempt}
+    ctx = context_factory(
         workspace, sandbox, policy, artifact_broker, change_baseline,
         read_only_workspace=read_only_workspace,
         deny_read_roots=tuple(deny_read_roots),
         workspace_session=workspace_session,
+        **context_options,
     )
     registry = default_registry(
         include_artifacts=artifact_broker is not None,
--- a/src/icode/chain.py
+++ b/src/icode/chain.py
@@ -304,6 +304,7 @@
     workspace_session: WorkspaceSession | None = None,
     on_step=None,
     out_dir: Path | None = None,
+    prepared_scope: object | None = None,
 ) -> ChainReport:
     """串起完整链路。**任一步骤被门禁拒绝即停步**，并如实报告。"""
     budget_tracker = _runtime_budget(budget, budget_tracker)
@@ -330,6 +331,15 @@
         or policy.workspace_root != workspace or policy.ticket_id != ticket_id
     ):
         raise ValueError("隔离策略与当前单步链路身份不匹配")
+    prepared_options = {}
+    if prepared_scope is not None:
+        from .runner import _prepared_scope_for_call
+
+        if len(order) != 1 or policy is None:
+            raise ValueError("准备对象与当前单步链路身份不匹配")
+        _prepared_scope_for_call(workspace, order[0], ticket_id, sandbox, policy,
+                                 workspace_session, prepared_scope)
+        prepared_options = {"prepared_scope": prepared_scope}
     report.notes.append("链路顺序（由状态机派生）：" + " → ".join(order))
-
+
     before = _snapshot(workspace)
@@ -390,6 +400,7 @@
                                else policy_session),
             change_baseline=before if policy is not None else None,
             extra_instructions=instructions, post_write=post,
+            **prepared_options,
         )
         report.steps.append(step_report)
         out_dir = Path(step_report.out_dir) if step_report.out_dir else out_dir
```

## Task 3: 线上优先验收、文档与候选交付

**状态**
- [ ] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (frozen SOURCE/TEST 与独立双审之后)

- [x] **Step 1:** 按2026-10-13用户明确确认的线上优先顺序，本机只运行原secret/submodule单门和必要针对性回归，不再默认全量。SOURCE/TEST冻结、编译默认j1；原全量失败历史保留，不因环境准备或局部正控通过改写。21项Probe（skip2）及18项包测试均实际exit0，两单门PASS；线上全量仍待。
- [ ] **Step 2:** root 在 DESIGN/live 只追加实际软件证据、实际 SHA/各层信用/未授边界；本 PLAN 写实际证据足迹。观察名单沿固定上游；不增加远端刷新，不宣称模型六步/90%、自动ready、R2/R3或 installed 完成。
- [ ] **Step 3:** 使用原 scanner，不改脚本、不忽略诊断，分别两轮：

```bash
.venv/bin/python /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/specs/2026-10-12-linux-prepared-runner-lifecycle-design.md docs/nbl/plans/2026-10-12-linux-prepared-runner-lifecycle.md docs/agent-landscape-live.md
```

两轮原 stdout 必须共0条疑似项；同期纳入AGENTS.md与development-handoff.md两流程文档。计数/状态/字段/标题人工核：原六功能范围加两文档共八候选路径、六terminal、prepared→pending→bound→spent及sticky faulted、公开字段/私有绑定、Task依赖和资产一致；历史结果不洗白。
- [ ] **Step 4:** root fresh secret/submodule、精确八路径index与diff核验，确认TEST/SOURCE未漂移后推送main待验收候选，记录真实SHA；不创建分支/版本标签。GitHub同SHA的全量单测、secret/submodule及本片必要门真实通过后才勾Task3完成，继续下一阶段；其它R2/R3未通过项单列，不能外推整体完成。作者不commit/push，root不取消或反复重跑掩盖失败。

## 测试覆盖与验收边界

新 TEST 的正例使用生产 `run_contract_step`、生产 `run_chain`、实际 `_run_agent` 普通/补救、实际 `_contract_engineering_gate`/工程 checks、实际 CP 创建/raw start/observer/终结和真实资源 fixture。普通两次与工程两次消费共享 owner/view，factory 仅一次；模型与 manager/payload transport double 独立标注，绝不授实际模型/隔离。六 terminal matrix 的 branch budget/gate seam 仅选择真实 runner 分支，CP 没被替换，实际事件负控确认收尾失败时未写 step_finished、未 state_changed、attempt仍 open；其健康侧通过真实原终结回执，不伪造 accepted success。

异常分账覆盖 pending start坏值、attach失败、postwrite ordinary异常、first KI/SE body与cleanup组合、finish失败仍独立close、helper close unknown不重试及 silent faulted/silent bound finish。外部 owner 只结束消费资格保持active，内部闭合 FD实际 EBADF、session FD/lease活。公开字段同时抹除、policy=None/换等值引用、session/sandbox/root/view/attempt/readonly漂移逐一命中实际 run_command 与 _execute_check，不仅构造/dispatch。

本次新增外部 owner 负控使用真实 `scope.close()`：底层 helper 原 close 成功后抛出确认错误，scope 真实先置 unknown 且不恢复 active；不直接赋 `_owner_state`。六 terminal 子分支及 ordinary postwrite body 分别断言真实 finish 一次、外部创建者 close 一次且底层 close 一次、runner 无重试、owner unknown/consume spent、实际 CP 无 step_finished/state_changed、attempt 仍 open、真实 checkpoint attempt/step 保留且 clear 未调用。OS descriptor 实际 EBADF，session FD/lease仍活；每个独立 fixture 单独回收自己的资源，unknown FD 不重试。旧内部矩阵仍为12子分支，本次外部矩阵新增6子分支，方法总数22，不混算 assertion 数。

None/no-session/明确非包内来源保留旧shape/旧报告，无prepared kwargs、额外factory或新模型设置；_make_ctx None/空attempt精确kwargs不变。模拟 darwin/win32 分类执行真实 runner legacy 入口（并非只 skip TEST），确认无 prepared kwargs/factory。包内来源 strict resolve 未知与实际 prepare 工厂失败均真实 runner 负控：未 public/raw start、未 backend/ordinary legacy 消费、未 fallback/replacement owner；采纳为 DESIGN 来源分类的必需证据，而不是新增机制。pureadmission无claim；实际resume读取真实CP/checkpoint旧路径、不start或还原attachment；实际automatic policy_contract_ready=False 阻断 provider/model/start/payload；Reviewer派生只读策略不接RW view/attempt。旧tests保持原字节；发现兼容冲突不得降低旧负控。

六 terminal matrix 各已建立实际 CP attempt 与 Checkpointer；fixture 明示保存一个真实初始 checkpoint，unknown 后逐支断言文件仍在、attempt/step 对应、clear 未调用，并核真实终结调用的 caller 是原 `_stop_contract_for_budget` 或 `_finish_step`。健康侧每支实际 step_finished=1、finish/close 各尝试1；unknown 每支 step_finished=0、terminal调用0、finish/close 各尝试1。普通/补救/工程 budget、工程 failure、deliberation budget 的正常预算停止不会等同健康业务成功；仅 normal 的健康侧实际 status=plan_done，其他 init_in_progress/code_in_progress，符合原 CP 状态转换。attachfailed 无 established checkpoint，故不泛化强加 checkpoint 断言。

## 两阶段内置自审记录

以下原20方法/37 BASE assertion 和09:44自审、scanner结果均为上一版历史证据；本次修订的新资产和实测另记，旧 C0/I0/M0 自审不能覆盖随后独立 QUALITY 发现的外部 owner I1。

SPEC 自审先逐节比 DESIGN 三问/来源分类/CP绑定/上下文/六terminal/异常/旧shape/信用边界，再另一次 QUALITY 核代码资产与真实符号。私人 RAM 诊断不替代正式作者/root RED/GREEN、独立审查或完整门；不能把 AST parse 当 GREEN。

完整诊断历史（不删失败、不转授正式 TDD）：最初 RAM 构建命令超过 argv 限额而未执行；第二次 shell quoting 导致 SyntaxError；第三次 stdin 未提供导致 JSONDecodeError；node_repl 超过 64000-byte strict auto-review limit 被拒；早期文本变换给出错误缩进、重建后才 compile；JS String.raw 内 literal backtick 引起 Invalid unexpected token，改 chr(96) 后成功。都是编写工具失败，不是产品 RED。最初代码围栏结束有一个 leading space，已修为原 ^```，未修改 scanner。

实际 S2b1 发布后初 TEST hash `ca56cc0c4ef7922d1fd6a2811e7216364dec407094ca54a1f3d5f3a8572508fe`：BASE session77919，18 方法、33 assertion FAIL、0 ERROR、0 skip，10.222s，exit1。首次投影 session13569，18 方法、4 FAIL、0 ERROR、0 skip，47.423s，exit1：`test_actual_engineering_gate_two_checks_and_readonly_reviewer_no_rw_view` 期望 payload>=3 得1；`test_chain_single_step_same_reference_none_callback_shape_and_bad_order` 期望2得0；`test_internal_prepare_attach_before_raw_start_and_backend_same_owner_twice` 期望2得0；`test_production_repair_round_reuses_view_before_internal_close` 期望1得0。根因是 fixture 未显式 ScriptedApprover、资源 receipt 不完整而在到达消费断言前正确 fail-closed。仅修 TEST 夹具为真实 approver 与 schema1 的完整7字段资源回执；没有弱化消费计数/CP/scope/旧None断言，没有改 SRC。

夹具修正后 TEST hash `f12efae95e114d5ba32699ea613c3d78244a0a18e8bf1642e461e92e762d64ed`：投影 session89136，18 方法、0 FAIL/ERROR/skip，46.588s，exit0。随后追加包内 resolve/工厂与非 Linux 真实入口负控、六 terminal caller/checkpoint 明示证据，TEST hash `ee14a0ec7265715a715a2d5ec4d6c662136e30b0091ead56764778bca34436a2`：投影 session32622 footer32aded，20 方法、0 FAIL/ERROR/skip，50.198s，exit0；逐支输出12条 fixture证据。对应 BASE session54722 footerf2415c（原签名 repr 输出过长截断）及只缩短 stdout repr 的重复 session11041 footerceda1f：20 方法、37 assertion FAIL、0 ERROR/skip，exit1；33项 signature missing、其余3项 private factory missing、1项 chain signature missing 的失败都是 API feature assertion，不是 ImportError/TypeError。方法数与37子用例失败、12terminal子分支分别计数，不混用。

静态自审已修：guard wrap_command 保留 `network` keyword 避免工程 legacy TypeError；LoopResult 使用真实 stop_reason 第二参数；VerificationPlan 不使用未支持plan step；finish不抛还需close前确认spent，防 silent faulted/bound健康洗白。最终格式修正将 TEST 输出改为中性 software-terminal-fixture，避免将未来正式 TEST 误标 RAM；diff 的空白 context 行等价改成删除/增加空行对，old/new hunk 各计数不变、投影 SOURCE bytes 不变。未用 git diff --check 冒充 ignored PLAN 的行尾检查。正式 TDD/回归/完整guard与 PLAN fresh独立审查仍待。

最终相同 TEST 字节资产 SHA-256 `772188d5fae95b2dcd3415fe97ef62a4659edc5f7552f58ef9424ded8534a334`。RAM 投影 session77009 footer7c24c1：20 方法、0 FAIL、0 ERROR、0 skip，51.053s，exit0，12条中性 software-terminal-fixture 实际 CP 证据；BASE session77134 footer739c4c：20 方法、37 assertion FAIL、0 ERROR、0 skip，exit1，原 stdout 完整列37失败名/子用例，未授未到达的生命周期分支信用。最后 BASE 仅缩短签名 mappingproxy 的 stdout 展示，不改变 assert 或 source。实际最终 BASE 与投影都来自上述完全相同 fence，均是私人 RAM 诊断而非正式 TDD。

完整 diff fence 分离后的 runner diff SHA-256 `6b96fd4f6fbe9efce088f4249ec40ff726490fc7dbb35c33e158af6d455a9599`、chain diff `4c221ca86df3ec3b46eacca4810892535f91e261fc3a8e47d9573c83e6a84197`（各含末尾换行）；严格 old/new 上下文重放后候选 runner `a0f3342473edc1c222188bf47a2aed7903b33783d6d6871a5848451262fb9d2f`、chain `16c23c505724cb9a23f25eb27d77e21919146dd0dbc3adde752de2c863f10acd`，与格式修正前相等。AST 核原 `_make_ctx`、`_stop_contract_for_budget`、`_finish_step`、`_finalize`、`resume_contract_step` 五函数全文完全未改，真实 terminal 六处。09:44:12 UTC 再只读核 main 仍1754ccaf、实际 runner/chain 与批准 DESIGN 仍等于开头基线（工具31ece5/518c15）。行尾 rstrip 逐行比对工具fd896b stdout `PLAN trailing-whitespace []`、exit0，完整文件而非 Git 忽略视角。

内置 SPEC 自审（09:44 UTC，C0/I0/M0）：逐条对应批准 DESIGN 的真实自动候选分类/unknown拒绝、外部引用校验、单调用内部所有权、start前claim、raw一次与实际attempt/freshCP、三个执行阶段同view、真实两消费门、六terminal/outerfinally、spent/faulted/close分账、第一signal、旧None与resume/Reviewer/ready分界；20方法与12terminal子分支证据无缺口。6发布范围可实现，无需扩共享工具/工程/scope/CP/native/vendor。

随后内置 QUALITY 自审（09:44 UTC，C0/I0/M0）：以原源码/真实API重核精确ctor shape、network签名、正式RED防误信用、strict diff与AST、真实CP事件/terminal caller/checkpoint、fixture transport和模型信用拆分、异常对象identity、旧shared函数不变、统计与历史日期、所有文件相对链接和行尾格式。无占位、未将测试double当真实模型、未预写未来SHA；本作者自审不替代 root 后续 fresh SPEC→不同 QUALITY 的独立批准。

原始 doc-contract-consistency scanner 未修改、不忽略项：初 PLAN 两轮44cd4d/ed30c1均 raw0；最终 DESIGN/PLAN/live 原命令两轮71f671/f59f3b，均 stdout `检查 3 个文件`、`共 0 条疑似项`，exit0。人工计数/状态/字段/段名四核通过：六发布路径与六真实terminal独立计数；20测试方法不是37 assertion子用例或12terminal子分支；prepared→pending→bound→spent/closed 与sticky faulted没有靠mark修健康；公开两字段/私有实refs、Task依赖/文件名、历史片发布与本片待实施边界一致。该脚本只审文档结构，不授实际执行能力。

【架构级自检报告】（上一版历史，仅 PLAN 与 RAM 资产）

- 语法/编译：通过 RAM 两 SOURCE/新 TEST AST parse、严格 old/new diff 重放；实际 SOURCE/TEST 未实施。
- 依赖/调用链：通过生产普通/补救/工程/链/六terminal、真实 CP API 与旧 _make_ctx shape 的 RAM 软件验证。
- 逻辑/边界：通过外部/内部owner、scope状态、真实消费漂移及准入/恢复/Reviewer/ready 分界软件断言。
- 异常处理：通过一次finish与独立close、silent faulted/bound拒绝、unknown不重试、第一KI/SE对象优先及checkpoint保留软件断言。
- 关联模块：通过限定落盘核；仅本 PLAN 写入，拟发布六路径，共享工具/工程/scope/vendor/native/CI/旧tests只读。
- 兼容安全：通过None/custom旧keyword shape、非Linux legacy调用、scope创建者责任；无用户参数/权限/token/缓存扩展。
- 可运行性：通过私人 RAM 软件诊断；正式 TDD/回归/完整guard尚未实施，native/installed/真实模型未验证，不宣称100%。

### 外部 owner I1 修订的当前资产与实测

runner 完整 diff 仍13 hunks，chain 仍3 hunks；runner 仅局部收尾 owner 条件改为内部 closed/外部 active，hunk old/new 行数及后续起点不变。严格重放逐hunk核 old/new counts、完整原上下文和 new 起点，全部通过；候选 compile/AST 通过，五个旧共享函数全文未改，chain diff/候选字节完全未变。当前 runner diff SHA-256 `20d0cffed984daddf5fce4253577f03157fa662dc83835f756e0a29b68f3229c`，候选 runner `91e5e6cc6fb0c1c12f9c769bd30aea5b9e95d7dcd3dc01bea6027d6d6074869b`；chain diff `4c221ca86df3ec3b46eacca4810892535f91e261fc3a8e47d9573c83e6a84197`，候选 chain `16c23c505724cb9a23f25eb27d77e21919146dd0dbc3adde752de2c863f10acd`。完整新 TEST 为47065 UTF-8 bytes、22方法，SHA-256 `20a1339e369c56617738e8938e4965ec68efebf44dea7e160c3f717121191b73`；这是文档候选资产 hash，不是未来正式落盘或发布 SHA。

本次历史继续保留：一次说明文字 apply_patch 因末段上下文不匹配拒绝，未改变文件；初 TEST `4d786ba27d681fe18d814f45b90e6c7eca675c8e8f5a2ca83c7089826d95ae2d`（46963 bytes）D/9p RAM BASE cell8为22方法/44 assertion FAIL/0 ERROR/0 skip、45.730s、exit1。初投影跨REPL调用采集只取得前6方法和进程exit0而无原footer，不授PASS。随后修正 external terminal spy，使旧门漏过时仍调用真实 CP而非被内部owner断言挡住；TEST `5f2be01b0b81fec4091ea3cbbe7900e721d92a2999812c79f59fa339f538c689`（47108 bytes）D/9p投影 cell20完整22方法/0 FAIL/0 ERROR/0 skip、194.916s、exit0，18条实际事件输出。此版在agent返回时关闭外部owner，旧门mutation首轮2方法/7 FAIL/0 ERROR/0 skip、11.955s，其中engineering/normal先在上下文重核被挡，因此不能单独证明六terminal漏门；保留历史但不授完整六出口定位信用。

最终 TEST 把外部创建者真实 close 失败定位到原 `view.finish()` 前，再调用原 finish；无直接赋owner状态，ordinary body独立负控仍在真实postwrite。冻结原生FS副本 `/home/orbbec/icode-linux-validation.UV7vPA/repo` 仅为root建立的只读软件诊断基线，原SOURCE与vendor已核相等；不是worktree或新branch，不能用副本clean代D工作区完整性。解释器 `/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python`，`env PYTHONPATH=src ... -B -`；从D本 PLAN读取当前fence、SOURCE和真实vendor CP从副本加载，SOURCE/TEST只在RAM compile/import，不写入任何文件。fixtures只在自身隔离临时目录创建资源和CP工单，未知FD不重试，各自回收；不启动native/fullguard/install/KEY/model。

最终旧门mutation只在RAM将单一owner条件还原上一版，新 TEST断言不改。首轮2方法/7 assertion FAIL/0 ERROR/0 skip、14.124s、exit1；随后加诊断print重核实际CP事件，14.030s、同统计、原footer `RAM_FOOTER OLD_PROJECTED methods 2 FAIL 7 ERROR 0 skip 0 exit 1`。六分支逐支真实 terminal_calls=1、原CP回执ok=True、实际step_finished=1/state_changed=0；“1”是调用/回执数量，不是returncode。ordinary body则错误保留prepared_execution_unconfirmed，负控要求prepared_cleanup_unconfirmed而FAIL。实际事件证明spy未通过AssertionError伪挡旧漏门；没有强改CP门或将原回执伪造成成功。

最终相同20a TEST fence两次严格13+3重放后的完整RAM诊断 cell25：BASE22方法、44 assertion FAIL、0 ERROR、0 skip、20.717s，原footer `RAM_FOOTER BASE methods 22 FAIL 44 ERROR 0 skip 0 exit 1`；投影22方法、0 FAIL、0 ERROR、0 skip、94.814s，原footer `RAM_FOOTER PROJECTED methods 22 FAIL 0 ERROR 0 skip 0 exit 0`。原日志保留在诊断进程REPL内存；44条失败均为API feature assertion（40 signature、3 private factory、1 chain signature），不是ImportError/TypeError。投影原stdout18条matrix：旧内部健康6条实际step_finished=1、内部unknown6条=0，新增外部unknown6条terminal_calls=0/step_finished=0；其state_changed=0、open attempt、checkpoint attempt/step原值和clear零调用逐支真实断言通过。ordinary body固定错误优先级、finish一次、caller close一次、底层close一次、无runner重试、EBADF和live session/lease均通过。以上均是私人RAM软件诊断，不是正式作者/root RED/GREEN，不授原生副本或新解释器native/installed/R2R3整体信用。

本次内置 SPEC 自审（先逐条核批准DESIGN，C0/I0/M0）：三问/六范围、候选分类与原身份、raw start/claim/freshCP、普通补救工程同view及真实消费guard、六terminal/finally、内closed/外active与unknown拒绝、sticky faulted、第一KI/SE、ordinary错误优先、None/Reviewer/resume/ready分界均保留。新增6外部terminal及ordinarybody真实失败补全I1，无需修改scope/CP/工具或扩大发布范围。

随后本次内置 QUALITY 自审（独立再核完整候选资产，C0/I0/M0）：cleanup_attempted先置，view.finish失败仍独立尝试内部close，外部由创建者关闭且runner不close/retry；真实state机unknown没有用字段写入或重试修健康。strict13+3 hunks/源码compile、旧5函数全文、network签名、None构造kwargs、chain资产不变、fixture资源回收、mutation真实事件与最终同fenceBASE/投影、历史证据分账均已核。作者自审不代root fresh SPEC→不同QUALITY批准；正式TDD/独立SOURCE双审/完整门仍待，不自动handoff。

【架构级自检报告】（本次仅 PLAN 与 RAM 资产）

- 语法/编译：通过当前两SOURCE/TEST RAM compile/AST及严格13+3 hunks old/new完整重放；未落盘实施。
- 依赖/调用链：通过22方法软件诊断，真实普通/补救/工程/chain及CP六terminal；旧共享5函数全文不变。
- 逻辑/边界：通过内部closed/外部active分账、外部unknown六出口和ordinarybody负控；旧None/恢复/Reviewer/ready合同保持。
- 异常处理：通过先置cleanup_attempted、独立finish/内部close、unknown不重试、first KI/SE对象及固定错误优先级。
- 关联模块：仅本PLAN落盘，SOURCE/TEST均RAM；DESIGN/live/handoff/vendor/index及既有修改保留，六发布范围不变。
- 兼容安全：通过当前全部既有候选资产软件断言，chain不变；无新依赖/机制/权限/token/缓存或用户参数。
- 可运行性：当前22方法RAM投影exit0且0 FAIL/ERROR/skip；正式TDD/回归/完整guard、native/installed/真实模型尚未授信，不宣称100%。

## 2026-10-13 正式执行与原生工作区接力

本节保留线上优先获授权前的本机守护/迁移历史。“本机完整门通过才提交”的原要求已由Task3新顺序替换；所有原失败仍真实保留，不执行过时的停止/交付条件。

本节为执行证据，不改批准DESIGN或任何Python/diff围栏资产。原批准PLAN SHA256 `836b276a167d17d29b57a3ac30a89ec76325d13d62876e085eec983dd80be174`，fresh PLAN SPEC→不同QUALITY均C0/I0/M0；上文Step复选框保留原操作模板，Task1/Task2实际各Step已满足如下证据。Task3发布未完成。

- 正式新TEST实际47065bytes/22方法/SHA256 `20a1339e369c56617738e8938e4965ec68efebf44dea7e160c3f717121191b73`。原SOURCE作者RED22/44有效AssertionError/0ERROR、skip/45.119s/exit1；root独立RED22/44/0ERROR、skip/45.750s/exit1，完整日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-formal-red.log`，SHA256 `9fc96fb312a0db93878ad2dbc262bccdce1ad52fe4dce07539fb22fe351669e7`。缺API用assert而非收集失败，TEST作者内置双审完成后停止，root核摘要并冻结，才放行不同SOURCE作者。
- 两SOURCE实际严格批准13+3 hunks：runner `91e5e6cc6fb0c1c12f9c769bd30aea5b9e95d7dcd3dc01bea6027d6d6074869b`，chain `16c23c505724cb9a23f25eb27d77e21919146dd0dbc3adde752de2c863f10acd`；五共享函数全文不变。作者GREEN22/188.874s/0FAIL、ERROR、skip/exit0，日志 `/home/orbbec/icode-s2b2-source-green-20261013-1910.log`，SHA256 `b1688bfb4e24e3034510f67e18ec7c534eb4f4c31d13f7e15234685661618fb8`；rootGREEN22/183.293s/0FAIL、ERROR、skip/exit0，日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-formal-green.log`，SHA256 `adfd03c75d2ae9bb67c98dc7e8727ec2faa07a5734b94a17c55c6eb99f7867aa`。
- 指定10模块作者254/403.696s、root254/394.392s，均0FAIL、ERROR/skip6/exit0；原日志分别 `/home/orbbec/icode-s2b2-source-regression-20261013-1915.log`（`f0fe39bcccdf66d0d36ef144e693e6bc5989499ff7a362e132719c6ba23df525`）、`/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-regression.log`（`ef5b2fc7c15bbd0d7167bc9934fec62c938df1a905fd44a6a44594a0d01e1cf2`）。6项既有平台skip不授原生信用。root补8模块工具/工程/目录对象/预算回归200/93.289s/0FAIL、ERROR/skip3/exit0，日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-callchain-regression.log`（`e4427635c77e26d98e8b171186575e8bb782c58887309f70af714acc5e2e89b4`）；缺Go及两用户总线条件不授通过。
- 作者内置SPEC→QUALITY完成；fresh实际SOURCE SPEC→不同QUALITY均C0/I0/M0。各自实际核当前字节/调用链，未把作者日志复核称为独立执行；root已核全部上述原footer与摘要。SOURCE/TEST继续冻结。
- root原D完整守护按原脚本j1实际结束：2026-10-13 11:22:41–11:45:07 UTC，日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-full-preflight.log`，SHA256 `2091db207939670b0690d39a3013ec8918871d96a76ed59200f7a39d115ca66f`。3216/1323.887s/FAIL2、ERROR1/skip165/exit1；密钥PASS、子仓与测试FAIL，禁止发布。原脚本只保留失败尾15行，已见子仓污染与Landlock策略绑定拒绝，ERROR1具体栈未被该脚本保留，不猜测。
- 用户明确授权保留Windows67个Junction、迁WSL原生工作区验收发布。新 `/home/orbbec/projects/icode` 从同本机main HEAD7aad及固定vendor21566a5本地Git对象克隆，初始两仓clean、仅main；不是历史诊断副本/worktree，不清原D改动，不新增线上分支或改子仓固定版本。迁移先逐字节核当前候选，重新捕获原生完整测试输出及原完整守护，未通过前不提交推送。迁移前实际sequentialthinking3步骤已完成（a10f77），不以配置存在代替调用成功。

Windows另片诊断保持独立：旧/新34项同2FAIL2ERROR，root自有空目录实测`..`零ID被原parser先拒绝；只读RAM移动真实子项身份校验后三个快照相关用例通过，仍有Path期待格式FAIL。无物理SOURCE/TEST修改，不授正式修复或Windows整体验收；完整证据及信用边界见 [接力记录](../../development-handoff.md)。

---
**Execution Mode:** serial

原文档作者交付时仅停在文档、未落盘SOURCE/TEST（历史），覆盖当时writing-plans自动handoff/worktree/commit建议。当前SOURCE/TEST已正式实施并冻结，root按用户main-only、线上优先的Task3推进候选与验收，不再停在文档交付。
