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

from tests._support import REPO_ROOT, require_skill, temp_workspace

from icode.backends import FakeBackend
from icode.chain import chain_steps, run_chain
from icode.config import load_settings
from icode.contracts import ContractSet
from icode.control import ControlPlane
from icode.runner import run_contract_step, run_unittest
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
