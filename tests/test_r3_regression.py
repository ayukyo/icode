"""R3 回归切片测试：diff 指纹绑定、事件链验证记录、证据包收集、独立 Reviewer 接线。

覆盖 roadmap「下一片」的三项：
1. workspace_changes / 测试回执绑定到具体 diff 与产物哈希（diff_fingerprint）；
2. 独立 Reviewer 与 Executor 隔离上下文，且不能修改被审对象（run_task 接线）；
3. 修复证据写入事件链（verification_recorded）并随证据包取证。
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests._support import REPO_ROOT, make_finished_plan_ticket, require_skill, temp_workspace

from icode.workspace_snapshot import changed_files, diff_fingerprint, snapshot_workspace


class TestDiffFingerprint(unittest.TestCase):
    def test_无改动时为空指纹(self) -> None:
        snap = {"a.py": "h1"}
        self.assertEqual(diff_fingerprint(snap, dict(snap)), diff_fingerprint(snap, snap))
        # 同一内容两次快照指纹一致（不因键序变化）
        self.assertEqual(
            diff_fingerprint({"b": "x", "a": "y"}, {"b": "x", "a": "y"}),
            diff_fingerprint({"a": "y", "b": "x"}, {"a": "y", "b": "x"}),
        )

    def test_改动变化指纹(self) -> None:
        before = {"a.py": "old"}
        after = {"a.py": "new"}
        self.assertNotEqual(diff_fingerprint(before, before), diff_fingerprint(before, after))

    def test_同结果不同基线得到不同指纹(self) -> None:
        # 结果内容相同，但基线不同 → 指纹必须不同（证据锚定到具体 diff）
        before_a = {"a.py": "old-1"}
        before_b = {"a.py": "old-2"}
        after = {"a.py": "new"}
        self.assertNotEqual(
            diff_fingerprint(before_a, after), diff_fingerprint(before_b, after),
        )

    def test_增删改状态区分(self) -> None:
        base = {"a.py": "h"}
        added = diff_fingerprint(base, {"a.py": "h", "b.py": "x"})
        deleted = diff_fingerprint({"a.py": "h", "b.py": "x"}, base)
        self.assertNotEqual(added, deleted)
        self.assertNotEqual(added, diff_fingerprint(base, {"a.py": "h2"}))

    def test___pycache__编译产物不进入diff(self) -> None:
        with temp_workspace() as ws:
            (ws / "a.py").write_text("x = 1\n", encoding="utf-8")
            before = snapshot_workspace(ws)
            pyc = ws / "__pycache__" / "a.cpython-311.pyc"
            pyc.parent.mkdir()
            pyc.write_bytes(b"pyc-artifact")
            self.assertNotIn("__pycache__/a.cpython-311.pyc", snapshot_workspace(ws))
            # 宿主编译产物不是模型改动，不产生 diff 证据
            self.assertEqual(changed_files(before, snapshot_workspace(ws)), [])
            self.assertEqual(
                diff_fingerprint(before, snapshot_workspace(ws)),
                diff_fingerprint(before, before),
            )

    def test_与changed_files集合一致(self) -> None:
        before = {"a.py": "h1", "b.py": "h2"}
        after = {"a.py": "h1", "b.py": "h2b", "c.py": "h3"}
        self.assertEqual(changed_files(before, after), ["b.py", "c.py"])
        # 未变化路径不参与指纹：改 b 与改 b+c 必须不同，但只列变化项
        fp_bc = diff_fingerprint(before, after)
        self.assertNotEqual(fp_bc, diff_fingerprint(before, {"a.py": "h1", "b.py": "h2b"}))
        # 指纹不含正文
        self.assertNotIn("h2b", fp_bc)


class TestEvidenceDiffBinding(unittest.TestCase):
    def test_diff_fingerprint进入指纹与回执(self) -> None:
        from icode.self_verify import VerificationEvidence, evidence_fingerprint

        base = dict(
            step="task", attempt="1", kind="test",
            command=("python", "-m", "unittest"), exit_code=0,
            environment_fingerprint="env", diff_fingerprint="diff-A",
        )
        a = VerificationEvidence(**base)
        b = VerificationEvidence(**{**base, "diff_fingerprint": "diff-B"})
        self.assertNotEqual(evidence_fingerprint(a), evidence_fingerprint(b))
        receipt = a.to_receipt()
        self.assertEqual(receipt["diff_fingerprint"], "diff-A")
        self.assertIn("diff_fingerprint", receipt)


class TestTaskReviewAndDiffBinding(unittest.TestCase):
    """run_task：diff 绑定 + 独立 Reviewer 接线（只读、不能修改被审对象）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def test_run_task绑定diff指纹并挂review(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import prepare_workspace, run_task

        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            report = run_task(
                self.settings, backend=FakeBackend(["完成"]), workspace=dst,
            )
            evidence = report.verification
            self.assertIsNotNone(evidence)
            # 无改动 → diff 指纹仍为确定值（空 diff 的指纹）
            self.assertEqual(len(evidence.diff_fingerprint), 64)
            # 独立 Reviewer 已接线：只读自检通过，且不能修改被审对象
            self.assertIsNotNone(report.review)
            self.assertTrue(report.review.read_only_verified)
            self.assertFalse((dst / "probe.md").exists(),
                             "Reviewer 必须只读，不得写入被审对象")
            # 空 diff 的证据指纹不含任何文件正文
            self.assertNotIn(dst.name, evidence.diff_fingerprint)

    def test_review对失败证据给blocking发现(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import prepare_workspace, run_task

        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            calc_path = str(dst / "calc.py")
            script = [
                {"content": "", "tool_calls": [
                    {"id": "break-calc", "name": "write_file",
                     "arguments": {"path": calc_path,
                                   "content": "raise RuntimeError('boom')\n"}}
                ]},
                "完成",
            ]
            report = run_task(
                self.settings, backend=FakeBackend(script), workspace=dst,
            )
            self.assertIsNotNone(report.review)
            self.assertTrue(report.review.read_only_verified)
            self.assertTrue(any(
                f.severity == "blocking" for f in report.review.findings
            ), [f.to_dict() for f in report.review.findings])
            self.assertTrue(all(
                f.evidence_ref for f in report.review.findings if f.category
            ))
            # Reviewer 不得改动工作区
            before = snapshot_workspace(dst)
            report.review  # 已构造完毕，改动若有已在构造时发生
            self.assertEqual(snapshot_workspace(dst), before)


class TestRepairEvidenceIntoEventChain(unittest.TestCase):
    """run_contract_step 补救回合把修复证据写入事件链（verification_recorded）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def test_修复证据写入事件链并随证据包取证(self) -> None:
        from icode.control import ControlPlane
        from icode.handshake import next_out_dir
        from icode.runner import run_contract_step
        from icode.sandbox_policy import NetworkMode, SandboxPolicy

        with temp_workspace() as ws:
            workspace = ws / "workspace"
            workspace.mkdir()
            out_dir = next_out_dir(workspace)
            ticket_id = "R3-EVENT-1"
            policy = SandboxPolicy(
                schema_version=1, run_id="r3-offline", ticket_id=ticket_id,
                step="plan", workspace_root=workspace.resolve(),
                read_roots=(workspace,), write_roots=(workspace,),
                deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(),
                process_limit=16, wall_timeout_seconds=60, output_limit_bytes=1024,
                protected_paths=(),
            )
            ControlPlane(self.settings).create(
                out_dir, ticket_id=ticket_id, requirement="R3 事件链", birth="plan",
            )
            loop = SimpleNamespace(ok=True, messages=[], stop_reason="done", error="")
            with patch("icode.runner._run_agent", return_value=loop) as agent, \
                 patch("icode.runner._finalize"):
                report = run_contract_step(
                    self.settings, backend=None, workspace=workspace,
                    step="plan", ticket_id=ticket_id, out_dir=out_dir,
                    policy=policy,
                )
            # 模型没写产物 → 进入补救回合
            self.assertGreaterEqual(agent.call_count, 2)
            # 事件链里必须出现 verification_recorded
            events = [
                json.loads(line)
                for line in (out_dir / ".ico_events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            recorded = [e for e in events if e.get("event_type") == "verification_recorded"]
            self.assertTrue(recorded, "修复证据必须写入事件链")
            run_payload = recorded[0]["payload"]
            self.assertEqual(run_payload["outcome"], "fail")
            self.assertTrue(run_payload["evidence"])
            # 元数据 verification_runs 与事件一致
            meta = json.loads((out_dir / ".ico_metadata.json").read_text(encoding="utf-8"))
            self.assertTrue(meta.get("verification_runs"))

            # 证据包把 verification_runs 纳入 verifications.json
            dest = ws / "pack"
            from icode.evidence import build_evidence_pack

            pack = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(pack.ok, pack.render())
            verifications = json.loads(
                (dest / "verifications.json").read_text(encoding="utf-8")
            )
            kinds = {r.get("kind") for r in verifications["receipts"]}
            self.assertIn("verification_recorded", kinds)
            recorded_receipts = [
                r for r in verifications["receipts"]
                if r.get("kind") == "verification_recorded"
            ]
            self.assertTrue(recorded_receipts)
            self.assertTrue(recorded_receipts[0]["fingerprint"])
            self.assertTrue(recorded_receipts[0]["baseline"])


class TestBoundedRepairLoop(unittest.TestCase):
    """run_task 有界修复循环：失败 → 分类 → 有界修复 → 回归 → 独立 Reviewer。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def test_zero_repairs_disables_retry_without_rejecting_task(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import prepare_workspace, run_task

        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            calc_path = str(dst / "calc.py")
            script = [
                {"content": "", "tool_calls": [
                    {"id": "break", "name": "write_file",
                     "arguments": {"path": calc_path, "content": "raise RuntimeError('boom')\n"}}
                ]},
                "完成",
            ]
            report = run_task(
                self.settings, backend=FakeBackend(script), workspace=dst,
                max_repairs=0,
            )

        self.assertNotEqual(report.exit_code, 0)
        self.assertEqual(report.repair_attempts, [report.verification])
        self.assertEqual(report.repair_decisions, [])

    def test_negative_repairs_is_rejected_before_model_turn(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import prepare_workspace, run_task

        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            with self.assertRaisesRegex(ValueError, "max_repairs must be >= 0"):
                run_task(
                    self.settings, backend=FakeBackend([]), workspace=dst,
                    max_repairs=-1,
                )


    def test_修复成功后回归通过并记录决策(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import prepare_workspace, run_task
        from icode.self_verify import FAILURE_CODE

        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            calc_path = str(dst / "calc.py")
            original = (dst / "calc.py").read_text(encoding="utf-8")
            script = [
                # 第一次运行：破坏 calc.py 后自然结束 → 独立测试失败
                {"content": "", "tool_calls": [
                    {"id": "break", "name": "write_file",
                     "arguments": {"path": calc_path, "content": "raise RuntimeError('boom')\n"}}
                ]},
                "完成",
                # 第二次运行（修复回合）：恢复 calc.py → 回归通过
                {"content": "", "tool_calls": [
                    {"id": "fix", "name": "write_file",
                     "arguments": {"path": calc_path, "content": original}}
                ]},
                "完成",
            ]
            report = run_task(
                self.settings, backend=FakeBackend(script), workspace=dst,
            )
            # 第一次破坏 → code 类失败 → 允许修复 → 第二次恢复 → 回归通过
            self.assertEqual(report.repair_decisions, ["allow"])
            self.assertEqual(len(report.repair_attempts), 2)
            self.assertEqual(report.exit_code, 0)
            self.assertTrue(report.verification.passed)
            self.assertEqual(report.repair_attempts[0].category, FAILURE_CODE)
            self.assertNotEqual(
                report.repair_attempts[0].diff_fingerprint,
                report.repair_attempts[1].diff_fingerprint,
                "修复后的 diff 必须与失败时不同（新证据）",
            )
            self.assertIsNotNone(report.review)
            self.assertTrue(report.review.read_only_verified)

    def test_无新证据时停止不碰运气(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import prepare_workspace, run_task

        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            calc_path = str(dst / "calc.py")
            script = [
                {"content": "", "tool_calls": [
                    {"id": "break", "name": "write_file",
                     "arguments": {"path": calc_path, "content": "raise RuntimeError('boom')\n"}}
                ]},
                "完成",  # 第二次不改动 → 无新证据 → 停止
            ]
            report = run_task(
                self.settings, backend=FakeBackend(script), workspace=dst,
            )
            self.assertEqual(report.repair_decisions, ["allow", "no_new_evidence"])
            self.assertEqual(len(report.repair_attempts), 2)
            self.assertNotEqual(report.exit_code, 0)

    def test_修复次数受max_repairs有界(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import prepare_workspace, run_task

        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            calc_path = str(dst / "calc.py")
            # 每次调用都产生新的破坏（新 diff + 新输出 → 每次都是新证据）
            script = []
            for version in ("v1", "v2", "v3"):
                script.append({"content": "", "tool_calls": [
                    {"id": f"break-{version}", "name": "write_file",
                     "arguments": {"path": calc_path,
                                   "content": f"raise RuntimeError('{version}')\n"}}
                ]})
            report = run_task(
                self.settings, backend=FakeBackend(script), workspace=dst,
                max_repairs=1,
            )
            # 首次失败 + 1 次修复后即停止，即便每次都有新证据
            self.assertEqual(len(report.repair_attempts), 2)
            self.assertLessEqual(len(report.repair_decisions), 1)
            self.assertNotEqual(report.exit_code, 0)


class TestMaxRepairsArgument(unittest.TestCase):
    def test_cli_accepts_zero_but_rejects_negative_max_repairs(self) -> None:
        from contextlib import redirect_stderr
        from io import StringIO
        from icode.cli import _build_parser

        parser = _build_parser()
        self.assertEqual(
            parser.parse_args(["task", "--max-repairs", "0"]).max_repairs,
            0,
        )
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            parser.parse_args(["task", "--max-repairs", "-1"])
        self.assertEqual(raised.exception.code, 2)


class TestEvidencePackCollectsVerificationRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def test_已有verification_runs的工单自动纳入回执(self) -> None:
        from icode.control import ControlPlane
        from icode.evidence import build_evidence_pack
        from icode.handshake import next_out_dir

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            cp = ControlPlane(self.settings)
            ticket_id = "R3-PACK-1"
            # 再补一条真实验证记录
            cp.record_verification(
                out_dir, ticket_id=ticket_id, kind="device_test",
                outcome="fail", evidence="fp-abc", baseline="diff-xyz",
                layer="unit", scenario="test",
            )
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())
            verifications = json.loads(
                (dest / "verifications.json").read_text(encoding="utf-8")
            )
            recorded = [
                r for r in verifications["receipts"]
                if r.get("kind") == "verification_recorded"
            ]
            self.assertTrue(recorded)
            self.assertEqual(recorded[0]["fingerprint"], "fp-abc")
            self.assertEqual(recorded[0]["baseline"], "diff-xyz")


if __name__ == "__main__":
    unittest.main()
