"""证据包测试（Phase 3 核心验收）。

验收标准（roadmap Phase 3）：
    对一条完成的工单导出证据包，在**不依赖本工具**的前提下可独立校验通过；
    人为篡改一处即校验失败。

因此本文件同时做三件事：
    1. 用真控制面造一条真实工单 → 导出包 → 包内校验器通过
    2. 逐个篡改点（改正文 / 改事件 / 删文件 / 加文件 / 改清单）都必须被检出
    3. **把包内 verify.py 当独立程序跑**（清空 PYTHONPATH、cwd 在包外），
       并静态断言它不 import 本仓任何代码
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests._support import REPO_ROOT, make_finished_plan_ticket, require_skill, temp_workspace

from icode.evidence import build_evidence_pack, collect_verifications
from icode.pack_verify import verify_pack


class TestEvidencePack(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def _build(self, dest_parent: Path, *, workspace: Path, **kw):
        out_dir = make_finished_plan_ticket(self.settings, workspace)
        dest = dest_parent / "pack"
        report = build_evidence_pack(
            out_dir, dest=dest, gates_json=self.settings.gates_json, **kw
        )
        return out_dir, dest, report

    # ---- 正常路径 ----

    def test_导出证据包并通过包内校验(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertEqual(report.problems, [], "\n".join(report.problems))
            self.assertTrue(report.ok, report.render())
            self.assertTrue(report.selfcheck_ok)
            self.assertGreaterEqual(report.event_count, 5)
            self.assertEqual(report.artifact_count, 1)
            self.assertTrue(report.pack_digest)
            self.assertEqual(verify_pack(dest), [])

    def test_包内包含独立校验器与诚实边界声明(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            self.assertTrue((dest / "verify.py").is_file())
            readme = (dest / "README.md").read_text(encoding="utf-8")
            # 必须说明"不需要安装本工具"才能校验，以及四条诚实边界
            for token in (
                "不需要安装 icode-agent",
                "过程记录自洽且未被篡改",
                "不是",
                "应用层限制，不是内核级沙箱",
                "外部渠道锚定",
                "pack_digest",
            ):
                self.assertIn(token, readme, token)

    def test_VerificationEvidence序列化进证据包(self) -> None:
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            evidence = VerificationEvidence(
                step="code", attempt="1", kind="test",
                command=("python", "-m", "unittest"), exit_code=1,
                output="AssertionError: boom",
                environment_fingerprint="env-fp", category="code",
                artifact_hashes={"calc.py": "abc"},
            )
            _out, dest, report = self._build(
                ws, workspace=ws / "work", verifications=[evidence],
            )
            self.assertTrue(report.ok, report.render())
            verifications = json.loads(
                (dest / "verifications.json").read_text(encoding="utf-8")
            )
            receipts = verifications["receipts"]
            self.assertEqual(len(receipts), 1)
            self.assertEqual(receipts[0]["kind"], "verification")
            self.assertEqual(receipts[0]["step"], "code")
            self.assertEqual(receipts[0]["exit_code"], 1)
            self.assertEqual(receipts[0]["artifact_hashes"], {"calc.py": "abc"})
            self.assertTrue(receipts[0]["fingerprint"])
            self.assertNotIn("AssertionError: boom", json.dumps(receipts[0]))

    def test_清单列出所有文件且摘要自洽(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["pack_kind"], "icode-evidence-pack")
            self.assertEqual(manifest["pack_digest"], report.pack_digest)
            listed = {e["path"] for e in manifest["files"]}
            actual = {
                p.relative_to(dest).as_posix()
                for p in dest.rglob("*")
                if p.is_file() and p.name != "manifest.json"
            }
            self.assertEqual(listed, actual, "清单必须覆盖包内每个文件")

    def test_正文快照与链上哈希对应(self) -> None:
        """D11 的核心：链上只存摘要，包内必须给出正文并与之对应。"""
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            index = json.loads((dest / "artifacts.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["artifacts"]), 1)
            item = index["artifacts"][0]
            self.assertEqual(item["output"], "plan")
            self.assertTrue(item["matches_chain"])
            self.assertEqual(item["chain_sha256"], item["snapshot_sha256"])
            self.assertTrue((dest / item["snapshot"]).is_file())

    def test_包含外部验证回执(self) -> None:
        with temp_workspace() as ws:
            receipt = collect_verifications(0, [sys.executable, "-m", "unittest"], "Ran 12 tests\nOK\n")
            _out, dest, report = self._build(ws, workspace=ws / "work", verifications=[receipt])
            self.assertTrue(report.ok, report.render())
            data = json.loads((dest / "verifications.json").read_text(encoding="utf-8"))
            self.assertEqual(data["receipts"][0]["exit_code"], 0)
            self.assertIn("Ran 12 tests", data["receipts"][0]["output_tail"])

    def test_缺少回执时给出提示但不阻断(self) -> None:
        with temp_workspace() as ws:
            _out, _dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            self.assertTrue(any("回执" in w for w in report.warnings))

    # ---- 篡改检测 ----

    def test_篡改产物正文被检出(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            bodies = list((dest / "ticket" / "bodies").iterdir())
            bodies[0].write_text("# 被篡改的计划\n", encoding="utf-8")
            problems = verify_pack(dest)
            self.assertTrue(problems, "篡改正文必须被检出")
            self.assertTrue(any("正文快照" in p or "清单" in p for p in problems), problems)

    def test_篡改事件内容被检出(self) -> None:
        """改事件 payload 但不更新 event_hash → 哈希链必须报错。"""
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            events_path = dest / "ticket" / "events.jsonl"
            events = [json.loads(l) for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            target = next(e for e in events if e["event_type"] == "artifact_written")
            target["payload"]["sha256"] = "f" * 64  # 伪造链上摘要
            events_path.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in events) + "\n",
                encoding="utf-8",
            )
            problems = verify_pack(dest)
            self.assertTrue(problems, "篡改事件必须被检出")
            self.assertTrue(any("event_hash" in p for p in problems), problems)

    def test_删除链上事件被检出(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            events_path = dest / "ticket" / "events.jsonl"
            lines = [l for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            events_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
            problems = verify_pack(dest)
            self.assertTrue(problems)
            self.assertTrue(any("清单" in p or "断链" in p or "包摘要" in p for p in problems), problems)

    def test_删除已登记文件被检出(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            (dest / "artifacts.json").unlink()
            problems = verify_pack(dest)
            self.assertTrue(any("缺失" in p or "缺少" in p for p in problems), problems)

    def test_夹带未登记文件被检出(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            (dest / "extra_payload.txt").write_text("夹带内容\n", encoding="utf-8")
            problems = verify_pack(dest)
            self.assertTrue(any("未登记" in p for p in problems), problems)

    def test_篡改清单摘要被检出(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["pack_digest"] = "a" * 64
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            problems = verify_pack(dest)
            self.assertTrue(any("包摘要" in p for p in problems), problems)


class TestStandaloneVerifier(unittest.TestCase):
    """`verify.py` 必须能脱离本仓独立运行——否则"不依赖本工具"就是假的。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = require_skill()

    def test_校验器不导入本仓任何模块(self) -> None:
        source = (REPO_ROOT / "src" / "icode" / "pack_verify.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("icode", imported, "独立校验器不得依赖本仓")
        allowed = {"hashlib", "json", "sys", "pathlib", "__future__"}
        self.assertTrue(imported <= allowed, f"出现非标准库依赖：{imported - allowed}")

    def _run_verifier(self, pack: Path, *, cwd: Path, extra_env: dict | None = None):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)  # 刻意不带本仓路径
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(pack / "verify.py"), str(pack)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(cwd), env=env, shell=False,
        )

    def test_独立运行校验器通过(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            report = build_evidence_pack(out_dir, dest=dest, gates_json=self.settings.gates_json)
            self.assertTrue(report.ok, report.render())

            proc = self._run_verifier(dest, cwd=ws)  # cwd 在包外，模拟审计方
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("校验通过", proc.stdout)

    def test_独立运行校验器能发现篡改(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            build_evidence_pack(out_dir, dest=dest, gates_json=self.settings.gates_json)
            bodies = list((dest / "ticket" / "bodies").iterdir())
            bodies[0].write_text("偷偷改掉的内容\n", encoding="utf-8")

            proc = self._run_verifier(dest, cwd=ws)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("校验失败", proc.stdout)

    def test_校验器用法错误返回2(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            build_evidence_pack(out_dir, dest=dest, gates_json=self.settings.gates_json)
            proc = self._run_verifier(dest, cwd=ws, extra_env={})
            # 无参数调用应报用法错误
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            bad = subprocess.run(
                [sys.executable, str(dest / "verify.py")],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(ws), env=env, shell=False,
            )
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
