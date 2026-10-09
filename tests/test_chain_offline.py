"""完整链路离线测试：用 FakeBackend 走通 plan → review → merge（零 token）。

这是 Phase 6 的核心验收：在接入真模型之前，先证明编排器与控制面
对每一步的契约都能正确走通（含产物登记、状态前移、事件链完整）。
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from tests._support import REPO_ROOT, make_finished_plan_ticket, require_skill, temp_workspace

from icode.backends import FakeBackend
from icode.chain import assemble_review_manifest, chain_steps, run_chain
from icode.config import load_settings
from icode.contracts import ContractSet
from icode.control import ControlPlane
from icode.runner import AUTOPERSIST_HEADER, run_contract_step, run_unittest
from icode.runner import StepReport
from icode.isolation import NoIsolation
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.tools import default_registry
from icode.workspace_snapshot import snapshot_workspace

# 各步骤的模拟产物内容（模型"应该"写的内容）
PLAN_TEXT = "# 实施计划\n\n## 需求理解\n为 calc.py 新增 gcd/lcm。\n"
REVIEW_TEXT = "# 审查报告\n\n计划合理，建议补充边界测试。\n"
REVIEW_JSON = {"round": 1, "new_issues": [], "refuted_issues": [], "pending_verification": []}
MERGED_TEXT = "# 定稿计划\n\n合并审查意见后的最终实施计划。\n"


def _policy(workspace: Path, step: str, ticket_id: str) -> SandboxPolicy:
    return SandboxPolicy(
        schema_version=1, run_id="offline-run", ticket_id=ticket_id,
        step=step, workspace_root=workspace, read_roots=(workspace,),
        write_roots=(workspace,), deny_read_roots=(),
        deny_write_roots=(workspace / ".git",), network_mode=NetworkMode.DENY,
        allowed_domains=(), process_limit=16, wall_timeout_seconds=60,
        output_limit_bytes=1024, protected_paths=(workspace / ".git",),
    )


def _script_for_step(step: str, out_dir: Path) -> list[dict[str, Any]]:
    """构造 FakeBackend 脚本：模拟模型调用 write_file 写产物，然后结束。"""
    targets: dict[str, str] = {
        "plan": "01_plan.md",
        "review": "02_review.md",
        "merge": "03_plan_final.md",
    }
    contents: dict[str, str] = {
        "plan": PLAN_TEXT,
        "review": REVIEW_TEXT,
        "merge": MERGED_TEXT,
    }
    filename = targets.get(step)
    content = contents.get(step, f"# {step} 产物\n")
    if not filename:
        return ["完成"]

    abs_path = str(Path(out_dir) / filename)
    write_call = {"content": "", "tool_calls": [
        {"id": f"w-{step}", "name": "write_file",
         "arguments": {"path": abs_path, "content": content}}
    ]}
    extra: list[dict[str, Any]] = []
    if step == "review":
        json_path = str(Path(out_dir) / "review_round_1.json")
        extra.append({"content": "", "tool_calls": [
            {"id": f"j-{step}", "name": "write_file",
             "arguments": {"path": json_path, "content": json.dumps(REVIEW_JSON)}}
        ]})
    return [write_call, *extra, "完成"]


class TestChainOffline(unittest.TestCase):
    """完整链路离线测试（FakeBackend，零 token）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()
        cls.contracts = ContractSet.load(cls.settings.gates_json)

    def test_链路顺序从状态机派生(self) -> None:
        order = chain_steps(self.contracts)
        self.assertEqual(order, ("plan", "review", "merge", "code", "deepcheck", "audit"))

    def test_run_chain复用可信已有工单目录(self) -> None:
        with temp_workspace() as workspace:
            from icode.handshake import next_out_dir

            (workspace / "code.py").write_text("before = True\n", encoding="utf-8")
            expected_code_snapshot = snapshot_workspace(workspace)["code.py"]
            existing_ticket = next_out_dir(workspace)
            ticket_id = "OFFLINE-EXISTING-1"
            ControlPlane(self.settings).create(
                existing_ticket,
                ticket_id=ticket_id,
                requirement="续跑已有工单",
                birth="plan",
            )
            before = sorted((workspace / ".icode_output").iterdir())
            step_report = StepReport(
                step="plan",
                ok=True,
                out_dir=str(existing_ticket.resolve()),
                finish_outcome="success",
            )
            policy = _policy(workspace.resolve(), "plan", ticket_id)

            with patch("icode.chain.run_contract_step", return_value=step_report) as invoked:
                report = run_chain(
                    self.settings,
                    backend=FakeBackend(["完成"]),
                    workspace=workspace,
                    requirement="续跑已有工单",
                    ticket_id=ticket_id,
                    steps=("plan",),
                    out_dir=existing_ticket,
                    policy=policy,
                )

            self.assertTrue(report.ok)
            self.assertEqual(sorted((workspace / ".icode_output").iterdir()), before)
            self.assertEqual(invoked.call_args.kwargs["ticket_id"], ticket_id)
            self.assertEqual(invoked.call_args.kwargs["out_dir"], existing_ticket.resolve())
            self.assertIs(invoked.call_args.kwargs["policy"], policy)
            self.assertEqual(
                invoked.call_args.kwargs["change_baseline"]["code.py"],
                expected_code_snapshot,
            )

    def test_run_chain拒绝非工单目录与身份不匹配目录(self) -> None:
        with temp_workspace() as workspace:
            not_a_ticket = workspace / "not-a-ticket"
            not_a_ticket.mkdir()
            with self.assertRaisesRegex(ValueError, r"\.ico_metadata\.json"):
                run_chain(
                    self.settings,
                    backend=FakeBackend(["完成"]),
                    workspace=workspace,
                    requirement="invalid existing ticket",
                    ticket_id="EXPECTED-1",
                    steps=("plan",),
                    out_dir=not_a_ticket,
                )

            from icode.handshake import next_out_dir

            mismatched = next_out_dir(workspace)
            ControlPlane(self.settings).create(
                mismatched,
                ticket_id="ACTUAL-1",
                requirement="mismatched ticket",
                birth="plan",
            )
            with self.assertRaisesRegex(ValueError, "ticket_id"):
                run_chain(
                    self.settings,
                    backend=FakeBackend(["完成"]),
                    workspace=workspace,
                    requirement="mismatched ticket",
                    ticket_id="EXPECTED-1",
                    steps=("plan",),
                    out_dir=mismatched,
                )

    def test_run_chain拒绝非UTF8_metadata(self) -> None:
        with temp_workspace() as workspace:
            invalid = workspace / "invalid-ticket"
            invalid.mkdir()
            (invalid / ".ico_metadata.json").write_bytes(b"\xff\xfe")

            with self.assertRaisesRegex(ValueError, "metadata"):
                run_chain(
                    self.settings,
                    backend=FakeBackend(["完成"]),
                    workspace=workspace,
                    requirement="invalid metadata encoding",
                    ticket_id="INVALID-UTF8-1",
                    steps=("plan",),
                    out_dir=invalid,
                )

    def test_contract_step的模型与补救回合继承隔离后端(self) -> None:
        with temp_workspace() as workspace:
            from icode.handshake import next_out_dir

            out_dir = next_out_dir(workspace)
            ticket_id = "OFFLINE-SANDBOX-1"
            ControlPlane(self.settings).create(
                out_dir, ticket_id=ticket_id, requirement="隔离透传", birth="plan",
            )
            sandbox = object()
            policy = _policy(workspace.resolve(), "plan", ticket_id)
            loop = SimpleNamespace(ok=True, messages=[], stop_reason="done", error="")
            with patch("icode.runner._run_agent", return_value=loop) as agent, patch(
                "icode.runner._finalize"
            ):
                run_contract_step(
                    self.settings, backend=FakeBackend(["完成"]), workspace=workspace,
                    step="plan", ticket_id=ticket_id, out_dir=out_dir,
                    sandbox=sandbox, policy=policy,
                )

            self.assertGreaterEqual(agent.call_count, 2, "必须覆盖首次与补救回合")
            self.assertTrue(all(
                call.kwargs.get("sandbox") is sandbox
                and call.kwargs.get("policy") is policy
                for call in agent.call_args_list
            ))
            self.assertIn("submit_artifact",
                          agent.call_args_list[1].kwargs["extra_instructions"])
            self.assertNotIn("write_file",
                             agent.call_args_list[1].kwargs["extra_instructions"].split(
                                 "不要用 write_file", 1
                             )[0])

    def test_策略会话只通过受控工具提交宿主工单产物(self) -> None:
        with temp_workspace() as project:
            checkout = project / "checkout"
            checkout.mkdir()
            from icode.handshake import next_out_dir as allocate_ticket_dir

            out_dir = allocate_ticket_dir(project)
            ticket_id = "OFFLINE-BROKER-1"
            ControlPlane(self.settings).create(
                out_dir, ticket_id=ticket_id, requirement="受控产物", birth="plan",
            )
            policy = _policy(checkout.resolve(), "plan", ticket_id)
            backend = FakeBackend([{
                "content": "", "tool_calls": [
                    {"id": "spoof-ledger", "name": "write_file",
                     "arguments": {"path": str(out_dir / ".ico_metadata.json"),
                                   "content": "spoof"}},
                    {"id": "submit-plan", "name": "submit_artifact",
                     "arguments": {"name": "01_plan.md", "content": PLAN_TEXT}},
                    {"id": "changes", "name": "workspace_changes", "arguments": {}},
                ],
            }, "完成"])
            with patch("icode.runner._finalize"):
                report = run_contract_step(
                    self.settings, backend=backend, workspace=checkout,
                    step="plan", ticket_id=ticket_id, out_dir=out_dir,
                    sandbox=NoIsolation(), policy=policy,
                )
            self.assertEqual((out_dir / "01_plan.md").read_text(encoding="utf-8"),
                             PLAN_TEXT)
            self.assertEqual(report.loop.turns[0].invocations[0].decision, "deny")
            self.assertTrue(report.loop.turns[0].invocations[1].result.ok)
            self.assertTrue(report.loop.turns[0].invocations[2].result.ok)
            self.assertIn("无改动", report.loop.turns[0].invocations[2].result.content)
            self.assertEqual(json.loads((out_dir / ".ico_metadata.json").read_text(
                encoding="utf-8"))["ticket_id"], ticket_id)
            prompt = backend.calls[0]["messages"][0]["content"]
            self.assertIn("submit_artifact", prompt)
            self.assertIn("workspace_changes", prompt)
            self.assertNotIn("这些路径位于工单目录内（属于工作区）", prompt)
            self.assertIn("submit_artifact", backend.calls[0]["messages"][1]["content"])
            self.assertNotIn("submit_artifact", default_registry().names())

    def test_plan_review_merge_三步走通(self) -> None:
        """离线验证：plan → review → merge 三步全部通过，事件链完整。"""
        with temp_workspace() as ws:
            # 准备一个隔离的靶场副本
            from icode.runner import prepare_workspace

            work = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)

            # 逐步骤跑（不用 run_chain，因为 FakeBackend 需要针对每步骤定制脚本）
            cp = ControlPlane(self.settings)
            from icode.handshake import next_out_dir

            out_dir = next_out_dir(work)
            ticket_id = "OFFLINE-1"

            cp.create(out_dir, ticket_id=ticket_id,
                      requirement="离线链路测试", birth="plan")

            delivered_steps: list[str] = []
            for step in ("plan", "review", "merge"):
                attempt = cp.step_start(out_dir, step, ticket_id=ticket_id)
                self.assertTrue(attempt, f"{step} start 失败")

                # before_write
                res = cp.step_check(out_dir, step, attempt, "before_write",
                                    ticket_id=ticket_id, occurrence=1)
                self.assertEqual(res.data.get("result"), "pass", f"{step} before_write")

                # 模拟模型写产物
                contract = self.contracts.step(step)
                for port in contract.outputs:
                    if port.kind != "ticket_file" or not port.value:
                        continue
                    target = out_dir / port.value
                    if target.is_file():
                        continue
                    content = {
                        "01_plan.md": PLAN_TEXT,
                        "02_review.md": REVIEW_TEXT,
                        "03_plan_final.md": MERGED_TEXT,
                    }.get(port.value)
                    if content is None and port.value == "review_round_1.json":
                        content = json.dumps(REVIEW_JSON)
                    if content is None:
                        # glob 或未知产物：生成最小占位
                        content = f"# {port.value}\n"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")

                # review_manifest 装配（结构合同：rounds 用 int 计数 + detail 文件引用）
                if step == "review":
                    round_data = {"round": 1, "new_issues": [], "refuted_issues": [],
                                  "pending_verification": []}
                    (out_dir / "review_round_1.json").write_text(
                        json.dumps(round_data, ensure_ascii=False) + "\n", encoding="utf-8")
                    sha = hashlib.sha256(
                        (out_dir / "review_round_1.json").read_bytes()).hexdigest()
                    manifest = {
                        "schema_version": 1, "ticket_id": ticket_id,
                        "review_run": attempt,
                        "rounds": [{
                            "round": 1, "origin_attempt": attempt,
                            "new_issues": 0, "refuted_issues": 0,
                            "pending_verification": 0,
                            "detail_path": "review_round_1.json",
                            "detail_sha256": sha,
                        }],
                    }
                    (out_dir / "review_manifest.json").write_text(
                        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

                # 登记产物
                for port in contract.outputs:
                    if port.kind == "ticket_file" and port.value:
                        art = cp.artifact(out_dir, step, attempt, port.value, ticket_id=ticket_id)
                        self.assertTrue(art.data.get("ok") is True,
                                        f"{step} artifact {port.value}: {art.data}")
                # review 的 round 文件**也必须登记**（origin_receipt 链要求）
                if step == "review":
                    for rf in sorted(out_dir.glob("review_round_*.json")):
                        art = cp.artifact(out_dir, step, attempt, rf.name, ticket_id=ticket_id)
                        self.assertTrue(art.data.get("ok") is True,
                                        f"review round artifact {rf.name}: {art.data}")

                # after_wait（review 有）
                if "after_wait" in contract.required_checks:
                    res = cp.step_check(out_dir, step, attempt, "after_wait",
                                        ticket_id=ticket_id, occurrence=2)
                    self.assertEqual(res.data.get("result"), "pass", f"{step} after_wait")

                # before_transition
                occ = 3 if "after_wait" in contract.required_checks else 2
                res = cp.step_check(out_dir, step, attempt, "before_transition",
                                    ticket_id=ticket_id, occurrence=occ)
                self.assertEqual(res.data.get("result"), "pass", f"{step} before_transition")

                # finish
                fin = cp.step_finish(out_dir, step, attempt, "success",
                                     ticket_id=ticket_id, evidence=["offline"], check=False)
                self.assertEqual(fin.data.get("outcome"), "success", f"{step} finish: {fin.data}")

                # 推理 trace
                from icode.reasoning import ReasoningGate
                from icode.sequential import Deliberation

                gate = ReasoningGate.load(self.settings.skill_root / "mcp" / "reasoning-gate" / "gates.json")
                delib = Deliberation(tier="L2", steps=["s1", "s2", "s3"], converged=True)
                row = gate.build_row(ticket_id, step, deliberation=delib)
                if row is not None:
                    from icode.reasoning import append_trace
                    append_trace(out_dir / ".thinking_gate_trace.jsonl", [row])

                # 门禁 metadata
                self.cp = cp
                _ensure_gate_meta(cp, out_dir, ticket_id)

                # 状态前移
                target_status = self.contracts.status_for_step(step)
                if target_status:
                    verdict = "verification_pending" if target_status == "completed" else None
                    tr = cp.transition(out_dir, target_status, ticket_id=ticket_id,
                                       delivery_verdict=verdict)
                    # 门禁可能拦截，如实记录
                    if tr.data.get("ok") is not True:
                        gates = [str(g.get("gate_id")) for g in (tr.data.get("failed_gates") or [])]
                        print(f"    [{step}] 状态前移被门禁拦截：{gates}（离线测试预期）")

                delivered_steps.append(step)

            # 验证
            self.assertEqual(delivered_steps, ["plan", "review", "merge"])
            trace = cp.trace(out_dir)
            self.assertTrue(trace.data.get("ok"))
            self.assertEqual(trace.data.get("open_steps"), {})
            self.assertEqual(trace.data.get("open_operations"), {})

            # 状态应已推进
            status = trace.data.get("status")
            self.assertIn(status, ("plan_finalized", "plan_done", "review_done"))

            # 产物文件存在
            for f in ("01_plan.md", "02_review.md", "review_manifest.json", "03_plan_final.md"):
                self.assertTrue((out_dir / f).is_file(), f"产物缺失：{f}")

            # 事件链无未闭合
            events_path = out_dir / ".ico_events.jsonl"
            events = [json.loads(l) for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            started = [e for e in events if e["event_type"] == "step_started"]
            finished = [e for e in events if e["event_type"] == "step_finished"]
            self.assertEqual(len(started), len(finished), "step start/finish 不配对")


class TestReviewArtifactHonestyOffline(unittest.TestCase):
    """Real controller, model tool loop and artifact broker; no gate mocks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def _ticket(self, workspace: Path) -> Path:
        from icode.reasoning import ReasoningGate, append_trace
        from icode.sequential import Deliberation

        out_dir = make_finished_plan_ticket(self.settings, workspace, ticket_id="REVIEW-HONESTY")
        cp = ControlPlane(self.settings)
        gate = ReasoningGate.load(self.settings.skill_root / "mcp/reasoning-gate/gates.json")
        row = gate.build_row("REVIEW-HONESTY", "plan", deliberation=Deliberation(
            tier="L2", steps=["Read plan", "Check scope", "Check test contract"], converged=True,
        ))
        if row is not None:
            append_trace(out_dir / ".thinking_gate_trace.jsonl", [row])
        _ensure_gate_meta(cp, out_dir, "REVIEW-HONESTY")
        transition = cp.transition(out_dir, "plan_done", ticket_id="REVIEW-HONESTY")
        self.assertTrue(transition.data.get("ok"), transition.data)
        # Start in a genuine review entry: the upstream review_run receipt must
        # follow that entry. Initial-entry ordering is a separate runner issue.
        transition = cp.transition(out_dir, "review_in_progress", ticket_id="REVIEW-HONESTY")
        self.assertTrue(transition.data.get("ok"), transition.data)
        return out_dir

    def _backend(self, submissions: dict[str, str], reply: str) -> FakeBackend:
        script = []
        if submissions:
            script.append({"content": "", "tool_calls": [
                {"id": f"submit-{index}", "name": "submit_artifact",
                 "arguments": {"name": name, "content": body}}
                for index, (name, body) in enumerate(submissions.items())
            ]})
        # The existing bounded repair may ask once; it receives no new artifacts.
        return FakeBackend([*script, reply, "完成", *["完成"] * 5])

    def _chain(self, workspace: Path, submissions: dict[str, str], reply: str):
        out_dir = self._ticket(workspace)
        backend = self._backend(submissions, reply)
        report = run_chain(
            self.settings, backend=backend, workspace=workspace,
            requirement="Independent plan review", ticket_id="REVIEW-HONESTY",
            steps=("review",), out_dir=out_dir, sandbox=NoIsolation(),
        )
        return out_dir, backend, report

    def _assert_failure(self, out_dir: Path, report) -> None:
        self.assertFalse(report.ok)
        self.assertEqual(report.stopped_at, "review")
        self.assertNotEqual(report.steps[0].finish_outcome, "success")
        trace = ControlPlane(self.settings).trace(out_dir)
        self.assertNotEqual(trace.data.get("status"), "review_done")

    def test_all_missing_keeps_review_and_round_missing(self) -> None:
        with temp_workspace() as workspace:
            out_dir, _backend, report = self._chain(workspace, {}, "完成")
            self.assertFalse((out_dir / "02_review.md").exists())
            self.assertEqual(list(out_dir.glob("review_round_*.json")), [])
            self._assert_failure(out_dir, report)

    def test_body_only_fails_without_clean_round(self) -> None:
        with temp_workspace() as workspace:
            out_dir, _backend, report = self._chain(workspace, {"02_review.md": REVIEW_TEXT}, "完成")
            self.assertEqual((out_dir / "02_review.md").read_text(encoding="utf-8"), REVIEW_TEXT)
            self.assertEqual(list(out_dir.glob("review_round_*.json")), [])
            self._assert_failure(out_dir, report)

    def test_round_only_short_reply_does_not_invent_body(self) -> None:
        with temp_workspace() as workspace:
            out_dir, _backend, report = self._chain(
                workspace, {"review_round_1.json": json.dumps(REVIEW_JSON)}, "完成",
            )
            self.assertFalse((out_dir / "02_review.md").exists())
            self.assertTrue((out_dir / "review_manifest.json").is_file())
            self._assert_failure(out_dir, report)

    def test_real_round_and_reply_persist_traceable_body(self) -> None:
        with temp_workspace() as workspace:
            out_dir, _backend, report = self._chain(
                workspace, {"review_round_1.json": json.dumps(REVIEW_JSON)}, REVIEW_TEXT,
            )
            self.assertEqual((out_dir / "02_review.md").read_text(encoding="utf-8"),
                             AUTOPERSIST_HEADER + REVIEW_TEXT.strip())
            self.assertEqual(report.steps[0].finish_outcome, "success", report.render())
            self.assertIn("review_round_1.json", report.steps[0].artifacts)
            events = (out_dir / ".ico_events.jsonl").read_text(encoding="utf-8")
            self.assertIn(hashlib.sha256((out_dir / "02_review.md").read_bytes()).hexdigest(), events)

    def test_free_json_reply_never_becomes_submitted_round(self) -> None:
        with temp_workspace() as workspace:
            out_dir, _backend, report = self._chain(
                workspace, {}, REVIEW_TEXT + "\n```json\n" + json.dumps(REVIEW_JSON) + "\n```",
            )
            self.assertEqual(list(out_dir.glob("review_round_*.json")), [])
            self.assertFalse((out_dir / "review_manifest.json").exists())
            self._assert_failure(out_dir, report)

    def test_complete_submission_preserves_real_body(self) -> None:
        with temp_workspace() as workspace:
            out_dir, _backend, report = self._chain(workspace, {
                "02_review.md": REVIEW_TEXT, "review_round_1.json": json.dumps(REVIEW_JSON),
            }, "完成")
            self.assertEqual((out_dir / "02_review.md").read_text(encoding="utf-8"), REVIEW_TEXT)
            self.assertEqual(report.steps[0].finish_outcome, "success", report.render())
            self.assertTrue(report.steps[0].ok, report.steps[0].render())
            self.assertEqual(report.steps[0].trace.get("open_steps"), {})

    def test_existing_body_is_not_overwritten_by_long_reply(self) -> None:
        with temp_workspace() as workspace:
            out_dir, _backend, report = self._chain(workspace, {
                "02_review.md": REVIEW_TEXT, "review_round_1.json": json.dumps(REVIEW_JSON),
            }, "# A different substantive reply\n\nMust not replace submitted text.")
            self.assertEqual((out_dir / "02_review.md").read_text(encoding="utf-8"), REVIEW_TEXT)
            self.assertEqual(report.steps[0].finish_outcome, "success", report.render())

    def test_contract_step_reposts_after_real_body_persistence(self) -> None:
        with temp_workspace() as workspace:
            out_dir = self._ticket(workspace)
            backend = self._backend({"review_round_1.json": json.dumps(REVIEW_JSON)}, REVIEW_TEXT)
            posts: list[tuple[str, str, bool]] = []

            def post(directory: Path, step: str, attempt: str) -> None:
                posts.append((step, attempt, (directory / "02_review.md").is_file()))
                assemble_review_manifest(directory, "REVIEW-HONESTY", attempt)

            report = run_contract_step(
                self.settings, backend=backend, workspace=workspace, step="review",
                ticket_id="REVIEW-HONESTY", out_dir=out_dir, sandbox=NoIsolation(), post_write=post,
            )
            self.assertEqual(len(posts), 3, posts)
            self.assertEqual([exists for _step, _attempt, exists in posts], [False, False, True])
            self.assertEqual(len({attempt for _step, attempt, _exists in posts}), 1)
            self.assertEqual(report.finish_outcome, "success", report.render())

    def test_contract_step_reassembles_machine_manifest_when_only_it_is_missing(self) -> None:
        with temp_workspace() as workspace:
            out_dir = self._ticket(workspace)
            backend = self._backend({
                "02_review.md": REVIEW_TEXT,
                "review_round_1.json": json.dumps(REVIEW_JSON),
            }, "完成")
            posts: list[int] = []

            def post(directory: Path, step: str, attempt: str) -> None:
                posts.append(len(posts) + 1)
                # The first assembly may run before the final round is visible;
                # final registration must retry the idempotent machine assembly.
                if len(posts) >= 2:
                    ok, reason = assemble_review_manifest(directory, "REVIEW-HONESTY", attempt)
                    self.assertTrue(ok, reason)

            report = run_contract_step(
                self.settings, backend=backend, workspace=workspace, step="review",
                ticket_id="REVIEW-HONESTY", out_dir=out_dir, sandbox=NoIsolation(), post_write=post,
            )
            self.assertTrue(report.ok, report.render())
            self.assertGreaterEqual(len(posts), 2)
            self.assertTrue((out_dir / "review_manifest.json").is_file())

    def test_contract_step_post_persistence_exception_fails_before_finish(self) -> None:
        with temp_workspace() as workspace:
            out_dir = self._ticket(workspace)
            backend = self._backend({"review_round_1.json": json.dumps(REVIEW_JSON)}, REVIEW_TEXT)

            def post(directory: Path, step: str, attempt: str) -> None:
                if (directory / "02_review.md").is_file():
                    raise RuntimeError("post-persistence-failed")
                assemble_review_manifest(directory, "REVIEW-HONESTY", attempt)

            report = run_contract_step(
                self.settings, backend=backend, workspace=workspace, step="review",
                ticket_id="REVIEW-HONESTY", out_dir=out_dir, sandbox=NoIsolation(), post_write=post,
            )
            self.assertIn("post-persistence-failed", report.error)
            self.assertFalse(report.ok)
            self.assertEqual(report.finish_outcome, "")
            self.assertTrue(Path(report.checkpoint_path).is_file())


class TestReviewInitialEntryOffline(unittest.TestCase):
    """First review entry must precede its genuine attempt/origin receipt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    _backend = TestReviewArtifactHonestyOffline._backend

    def _initial_ticket(self, workspace: Path) -> Path:
        from icode.reasoning import ReasoningGate, append_trace
        from icode.sequential import Deliberation

        out_dir = make_finished_plan_ticket(self.settings, workspace, ticket_id="REVIEW-HONESTY")
        cp = ControlPlane(self.settings)
        gate = ReasoningGate.load(self.settings.skill_root / "mcp/reasoning-gate/gates.json")
        row = gate.build_row("REVIEW-HONESTY", "plan", deliberation=Deliberation(
            tier="L2", steps=["Read plan", "Check scope", "Check test contract"], converged=True,
        ))
        if row is not None:
            append_trace(out_dir / ".thinking_gate_trace.jsonl", [row])
        _ensure_gate_meta(cp, out_dir, "REVIEW-HONESTY")
        result = cp.transition(out_dir, "plan_done", ticket_id="REVIEW-HONESTY")
        self.assertTrue(result.data.get("ok"), result.data)
        self.assertEqual(cp.trace(out_dir).data.get("status"), "plan_done")
        return out_dir

    def _assert_initial_receipts(self, out_dir: Path, report) -> None:
        events = [json.loads(row) for row in (out_dir / ".ico_events.jsonl").read_text(
            encoding="utf-8").splitlines() if row.strip()]
        entries = [index for index, event in enumerate(events)
                   if event["event_type"] == "state_changed"
                   and event["payload"].get("to") == "review_in_progress"]
        starts = [index for index, event in enumerate(events)
                  if event["event_type"] == "step_started"
                  and event["payload"].get("step") == "review"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(starts), 1)
        self.assertLess(entries[0], starts[0], "review entry must precede its attempt")
        self.assertEqual(report.steps[0].finish_outcome, "success", report.steps[0].render())
        manifest = json.loads((out_dir / "review_manifest.json").read_text(encoding="utf-8"))
        attempt = events[starts[0]]["payload"]["attempt"]
        self.assertEqual(manifest["review_run"], attempt)
        self.assertEqual(manifest["rounds"][0]["origin_attempt"], attempt)
        digest = hashlib.sha256((out_dir / "review_round_1.json").read_bytes()).hexdigest()
        self.assertEqual(manifest["rounds"][0]["detail_sha256"], digest)
        self.assertTrue(any(event["event_type"] == "artifact_written"
                            and event["payload"].get("attempt") == attempt
                            and event["payload"].get("sha256") == digest
                            for event in events[starts[0] + 1:]))
        self.assertEqual(report.steps[0].trace.get("open_steps"), {})

    def test_initial_review_full_submission_has_entry_before_start(self) -> None:
        with temp_workspace() as workspace:
            out_dir = self._initial_ticket(workspace)
            report = run_chain(
                self.settings, backend=self._backend({
                    "02_review.md": REVIEW_TEXT, "review_round_1.json": json.dumps(REVIEW_JSON),
                }, "完成"), workspace=workspace, requirement="First review",
                ticket_id="REVIEW-HONESTY", steps=("review",),
                out_dir=out_dir, sandbox=NoIsolation(),
            )
            self._assert_initial_receipts(out_dir, report)

    def test_initial_review_real_round_and_reply_have_original_receipts(self) -> None:
        with temp_workspace() as workspace:
            out_dir = self._initial_ticket(workspace)
            backend = self._backend({"review_round_1.json": json.dumps(REVIEW_JSON)}, REVIEW_TEXT)
            report = run_chain(
                self.settings, backend=backend, workspace=workspace, requirement="First review",
                ticket_id="REVIEW-HONESTY", steps=("review",),
                out_dir=out_dir, sandbox=NoIsolation(),
            )
            self._assert_initial_receipts(out_dir, report)
            self.assertEqual((out_dir / "02_review.md").read_text(encoding="utf-8"),
                             AUTOPERSIST_HEADER + REVIEW_TEXT.strip())
            self.assertEqual(sum(call["tools"] is not None for call in backend.calls), 3)

    def test_plan_birth_and_reuse_do_not_repeat_existing_entry(self) -> None:
        original_transition = ControlPlane.transition
        for reuse in (False, True):
            with self.subTest(reuse=reuse), temp_workspace() as workspace:
                out_dir = None
                if reuse:
                    from icode.handshake import next_out_dir

                    out_dir = next_out_dir(workspace)
                    created = ControlPlane(self.settings).create(
                        out_dir, ticket_id="PLAN-ENTRY", requirement="Plan entry", birth="plan",
                    )
                    self.assertIs(created.data.get("ok"), True)
                backend = self._backend({}, PLAN_TEXT)
                with patch.object(ControlPlane, "transition", autospec=True,
                                  side_effect=original_transition) as transitions:
                    report = run_contract_step(
                        self.settings, backend=backend, workspace=workspace,
                        step="plan", ticket_id="PLAN-ENTRY", requirement="Plan entry",
                        out_dir=out_dir, sandbox=NoIsolation(),
                    )
                self.assertEqual(report.finish_outcome, "success", report.render())
                self.assertFalse(any(call.args[2] == "init_in_progress"
                                     for call in transitions.call_args_list))
                self.assertEqual((Path(report.out_dir) / "01_plan.md").read_text(encoding="utf-8"),
                                 AUTOPERSIST_HEADER + PLAN_TEXT.strip())

    def test_rejected_entry_never_starts_attempt_checkpoint_or_model(self) -> None:
        original_start = ControlPlane.step_start
        for failure in (SimpleNamespace(data={"ok": False}, returncode=1),
                        RuntimeError("transition-failed")):
            with self.subTest(failure=type(failure).__name__), temp_workspace() as workspace:
                out_dir = self._initial_ticket(workspace)
                backend = FakeBackend([REVIEW_TEXT])
                with patch.object(ControlPlane, "step_start", autospec=True,
                                  side_effect=original_start) as start, patch.object(
                    ControlPlane, "transition",
                    **({"side_effect": failure} if isinstance(failure, Exception)
                       else {"return_value": failure}),
                ), patch("icode.runner.Checkpointer") as checkpoint, patch(
                    "icode.runner.OperationRecorder",
                ) as operations:
                    report = run_contract_step(
                        self.settings, backend=backend, workspace=workspace, step="review",
                        ticket_id="REVIEW-HONESTY", out_dir=out_dir, sandbox=NoIsolation(),
                    )
                start.assert_not_called()
                checkpoint.assert_not_called()
                operations.assert_not_called()
                self.assertEqual(backend.calls, [])
                self.assertFalse(report.ok)
                self.assertTrue(report.error)
                self.assertEqual(report.checkpoint_path, "")
                self.assertFalse((out_dir / ".agent_checkpoint.json").exists())
                events = [json.loads(row) for row in (out_dir / ".ico_events.jsonl").read_text(
                    encoding="utf-8").splitlines() if row.strip()]
                self.assertFalse(any(event["event_type"] == "step_started"
                                     and event["payload"].get("step") == "review" for event in events))

    def test_untrusted_reuse_trace_never_starts_step(self) -> None:
        for failure in (SimpleNamespace(data={"ok": False, "status": "review_in_progress"}),
                        RuntimeError("trace-failed")):
            with self.subTest(failure=type(failure).__name__), temp_workspace() as workspace:
                out_dir = self._initial_ticket(workspace)
                backend = FakeBackend([REVIEW_TEXT])
                with patch.object(ControlPlane, "trace",
                                  **({"side_effect": failure} if isinstance(failure, Exception)
                                     else {"return_value": failure})), patch.object(
                    ControlPlane, "step_start",
                ) as start, patch.object(ControlPlane, "transition") as transition, patch(
                    "icode.runner.Checkpointer",
                ) as checkpoint, patch("icode.runner.OperationRecorder") as operations:
                    report = run_contract_step(
                        self.settings, backend=backend, workspace=workspace, step="review",
                        ticket_id="REVIEW-HONESTY", out_dir=out_dir, sandbox=NoIsolation(),
                    )
                start.assert_not_called()
                transition.assert_not_called()
                checkpoint.assert_not_called()
                operations.assert_not_called()
                self.assertEqual(backend.calls, [])
                self.assertFalse(report.ok)
                self.assertTrue(report.error)
                self.assertEqual(report.checkpoint_path, "")

    def test_contract_entry_order_preserves_nonprogress_and_other_steps(self) -> None:
        for step, target in (("plan", "init_in_progress"), ("merge", None), ("audit", None),
                             ("code", "code_in_progress"), ("deepcheck", "deepcheck_in_progress")):
            with self.subTest(step=step), temp_workspace() as workspace:
                calls: list[str] = []

                def transition(*args, **kwargs):
                    calls.append(args[1])
                    return SimpleNamespace(data={"ok": True}, returncode=0)

                def start(*args, **kwargs):
                    calls.append("start")
                    raise RuntimeError("stop-after-start")

                with patch.object(ControlPlane, "transition", side_effect=transition), patch.object(
                    ControlPlane, "step_start", side_effect=start,
                ), patch.object(ControlPlane, "trace", return_value=SimpleNamespace(
                    data={"ok": True, "status": "previous"}, returncode=0,
                )):
                    report = run_contract_step(
                        self.settings, backend=FakeBackend(["完成"]), workspace=workspace,
                        step=step, ticket_id="ENTRY-ORDER", out_dir=workspace, sandbox=NoIsolation(),
                    )
                self.assertEqual(calls, [target, "start"] if target else ["start"])
                self.assertIn("stop-after-start", report.error)

        # 没有中间状态映射时直接 start；不为步骤名硬编码额外流转。
        for step in ("plan", "merge", "audit"):
            with self.subTest(no_progress=step), temp_workspace() as workspace:
                with patch.object(ContractSet, "in_progress_status_for", return_value=None), patch.object(
                    ControlPlane, "transition",
                ) as transition, patch.object(ControlPlane, "step_start",
                                               side_effect=RuntimeError("stop-after-start")) as start:
                    report = run_contract_step(
                        self.settings, backend=FakeBackend(["完成"]), workspace=workspace,
                        step=step, ticket_id="ENTRY-ORDER", out_dir=workspace, sandbox=NoIsolation(),
                    )
                transition.assert_not_called()
                start.assert_called_once()
                self.assertIn("stop-after-start", report.error)


def _ensure_gate_meta(cp, out_dir: Path, ticket_id: str) -> None:
    """补齐 strict 门禁要求的 metadata 键。"""
    path = out_dir / ".ico_metadata.json"
    if not path.is_file():
        return
    meta = json.loads(path.read_text(encoding="utf-8"))
    missing = {k: [] for k in ("semantic_decisions", "requirement_deltas") if k not in meta}
    if missing:
        cp.metadata_update(out_dir, ticket_id=ticket_id, set_json=missing)


if __name__ == "__main__":
    unittest.main()
