"""§13.12 五项原生创新端到端整合验证（收束工作包 W1）。

五项机制在同一工单生命周期内逐环咬合，证明它们是同一个不可绕过的控制平面：

  1. Contract-driven Agent        —— icode.control.ControlPlane + gates.json 状态机
  2. Gate-driven Context          —— icode.context_index（以当前未满足门禁的词项驱动选上下文）
  3. Least-capability Execution   —— icode.multi_agent/agent_scope（区域收敛 + 只读派生）
  4. Evidence-carrying Action     —— icode.extension_contract.attach_evidence + R3 验证回执
  5. Auditable Multi-Agent        —— icode.multi_agent（身份/边界/结论账本/step_gate）
  6. R7 收尾                      —— 证据包 + 签名 + 锚定（pack_verify/pack_signing/pack_anchor）

破坏性断言（G-A1）：缺结论 → 门禁 blocked；包内字节篡改 → 验签失败。
"""

import json
import stat
import tempfile
import unittest
from pathlib import Path

from tests._support import require_skill
from icode import pack_signing
from icode.agent_scope import converge_policy_to_region
from icode.context_index import build_index, select_context
from icode.control import ControlPlane
from icode.evidence import build_evidence_pack, collect_verifications
from icode.extension_contract import ExtensionManifest, SideEffect, attach_evidence
from icode.guard import Scope
from icode.multi_agent import AgentTeam
from icode.pack_anchor import build_git_tag_record, validate_records
from icode.pack_verify import verify_pack
from icode.sandbox_policy import NetworkMode, SandboxPolicy

TICKET_ID = "ICODE-142"


def _policy(workspace: Path) -> SandboxPolicy:
    return SandboxPolicy(
        schema_version=1, run_id="run-ni-001", ticket_id=TICKET_ID, step="code",
        workspace_root=workspace, read_roots=(workspace,), write_roots=(workspace,),
        deny_read_roots=(workspace / ".git",),
        deny_write_roots=(workspace / ".git",),
        network_mode=NetworkMode.DENY, allowed_domains=(),
        process_limit=32, wall_timeout_seconds=600, output_limit_bytes=4 * 1024 * 1024,
        protected_paths=(workspace / ".git",),
    )


def _scope(workspace: Path) -> Scope:
    return Scope(workspace_root=workspace, allowed_write_roots=(workspace,))


class NativeIntegrationTests(unittest.TestCase):
    """六环场景：同一工单、同一工作区、同一证据链。"""

    def test_five_mechanisms_bite_on_one_ticket(self):
        settings = require_skill()
        with tempfile.TemporaryDirectory(prefix="icode-native-integration-") as raw:
            root = Path(raw)

            # ── 环 1：Contract-driven Agent（控制面契约建单）────────────
            code = root / "code"
            code.mkdir()
            (root / "control").mkdir()
            (code / "calc.py").write_text(
                "def calc_gcd(a, b):\n    raise NotImplementedError\n",
                encoding="utf-8")
            (code / "test_calc.py").write_text(
                "import unittest\nimport calc\n\n"
                "class TestCalc(unittest.TestCase):\n"
                "    def test_placeholder(self):\n        self.assertTrue(True)\n",
                encoding="utf-8")
            (code / "部署说明.txt").write_text("与本次任务无关的运维文档", encoding="utf-8")
            ticket = root / "control/.icode_output/.icode_output_1"
            cp = ControlPlane(settings)
            cp.create(ticket, ticket_id=TICKET_ID, requirement="原生创新整合验证")
            cp.bind_execution_root(ticket, ticket_id=TICKET_ID, execution_root=code)

            # ── 环 2：Gate-driven Context（未满足门禁的词项驱动上下文）────
            # 当前门禁：calc_gcd/calc_lcm 实现与单测缺失——查询词项即来自该缺口。
            index = build_index(code, changed=["calc.py"])
            selection = select_context(index, query="calc gcd lcm unit test",
                                       budget_chars=2000)
            # 门禁缺口词项决定排序：缺口相关文件排前，无关文件垫底
            self.assertEqual(selection.files[0], "calc.py")
            self.assertEqual(selection.files[-1], "部署说明.txt")
            self.assertTrue(selection.text.strip())  # 有界大纲正文（只有大纲）

            # ── 环 3+5：Least-capability Execution + Auditable Multi-Agent ──
            team = AgentTeam(TICKET_ID, lease_dir=root / "leases",
                             policy=_policy(code), scope=_scope(code))
            executor = team.spawn("executor")
            reviewer = team.spawn("reviewer")

            # executor 写范围收敛到申报区域（单文件区域），越出即非本 run 边界
            region = "calc.py"  # write_lease 只接受工作区相对路径
            narrowed = converge_policy_to_region(executor.policy, region)
            self.assertEqual(len(narrowed.write_roots), 1)
            self.assertEqual(narrowed.write_roots[0].name, "calc.py")

            artifact_digest = {"value": ""}

            def executor_work(handle):
                target = code / region
                target.write_text(
                    "def calc_gcd(a, b):\n    return 6\n", encoding="utf-8")
                import hashlib
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                artifact_digest["value"] = digest
                return {"artifact_sha256": digest, "path": "calc.py"}

            executor_conclusion = team.run(
                executor, executor_work, step="code", write_region=region)
            self.assertEqual(executor_conclusion.outcome, "completed")
            self.assertEqual(executor_conclusion.evidence["agent_id"],
                             executor.agent_id)
            # executor 申报区域后，结论边界摘要 = 收敛后策略指纹（不是原全域摘要）
            self.assertEqual(executor_conclusion.evidence["context_digest"],
                             narrowed.policy_hash)
            self.assertNotEqual(executor_conclusion.evidence["context_digest"],
                                executor.context_digest)
            # 只读角色的上下文边界：write_roots 恒空（最小权限的结构保证）
            self.assertEqual(reviewer.policy.write_roots, ())
            self.assertEqual(reviewer.scope.allowed_write_roots, ())
            # 门禁按步骤核对：code 步的 executor 执行结论放行
            code_gate = team.step_gate("code", {"executor": "execution"})
            self.assertTrue(code_gate.ok, code_gate.missing)
            # 角色分离：review 步要求 reviewer 结论——executor 在 review 步
            # 从未运行，其 code 步结论不能顶替（blocked，无放宽路径）
            review_gate_before = team.step_gate("review", {"reviewer": "review"})
            self.assertFalse(review_gate_before.ok)

            def reviewer_work(handle):
                body = (code / "calc.py").read_text(encoding="utf-8")
                return {"reviewed": True, "ok": bool(body.strip())}

            reviewer_conclusion = team.run(reviewer, reviewer_work, step="review")
            self.assertEqual(reviewer_conclusion.outcome, "completed")
            self.assertNotEqual(executor_conclusion.evidence["context_digest"],
                                reviewer_conclusion.evidence["context_digest"])
            review_gate = team.step_gate("review", {"reviewer": "review"})
            self.assertTrue(review_gate.ok, review_gate.missing)
            # 破坏性断言：verifier 从未运行 → verify 步门禁 blocked
            blocked = team.step_gate("verify", {"verifier": "verification"})
            self.assertFalse(blocked.ok)
            self.assertIn("verifier:verification", blocked.missing)

            # ── 环 4：Evidence-carrying Action（R5 词表 + R3 回执通道）────
            manifest = ExtensionManifest(
                name="ni-executor", version="1.0.0", kind="tool",
                source="tests/test_native_integration.py",
                opclass="managed_write",
                description="整合验证：executor 产物登记",
                side_effects=(SideEffect(kind="file_write", target=region),),
                evidence=frozenset(
                    {"command_sha256", "exit_code", "execution_attempt"}),
            )
            binding = attach_evidence(manifest, {
                "command_sha256": "ab" * 32,
                "exit_code": 0,
                "execution_attempt": 1,
            })
            self.assertEqual(sorted(binding),
                             ["command_sha256", "execution_attempt", "exit_code"])
            with self.assertRaises(Exception):
                attach_evidence(manifest, {"command_sha256": "ab" * 32})
            # 控制面证据通道（R3）：独立验证回执随证据包序列化为 verifications.json
            verification = collect_verifications(
                exit_code=0, argv=["python", "-B", "-m", "unittest"],
                output="Ran 1 test in 0.001s\nOK\n",
            )

            # ── 环 6：R7 收尾（证据包 → 验证 → 签名 → 锚定）──────────────
            pack = root / "pack"
            report = build_evidence_pack(
                ticket, dest=pack, gates_json=settings.gates_json, clean=False,
                code_commit="f" * 40, verifications=[verification],
            )
            self.assertTrue(report.ok, report.render())
            self.assertEqual(verify_pack(pack), [])
            # 验证回执确实进入证据包并被清单覆盖
            self.assertTrue((pack / "verifications.json").is_file())

            key_path = root / "signing.key"
            pack_signing.write_signing_key(pack_signing.generate_signing_key(), key_path)
            seed = pack_signing.read_signing_key(key_path)
            record = pack_signing.sign_pack(pack, key_path)
            public_key = record["public_key"]
            self.assertEqual(verify_pack(pack, public_key=public_key), [])

            # 换包重贴/篡改：清单摘要与签名双重拦截
            from icode.pack_anchor import attach_anchor_records
            manifest_digest = json.loads(
                (pack / "manifest.json").read_text(encoding="utf-8"))["pack_digest"]
            attach_anchor_records(pack, [
                build_git_tag_record(manifest_digest, "https://github.com/ayukyo/icode"),
            ])
            # anchors.json 改动会使签名失效 → 必须重新签名后整体自洽
            record = pack_signing.sign_pack(pack, key_path)
            self.assertEqual(verify_pack(pack, public_key=record["public_key"]), [])
            problems = validate_records(
                [build_git_tag_record(manifest_digest, "https://example.com")],
                manifest_digest,
            )
            self.assertEqual(problems, [])
            wrong_pack_problems = validate_records(
                [build_git_tag_record("cd" * 32, "https://example.com")],
                manifest_digest,
            )
            self.assertTrue(any("换包重贴" in p for p in wrong_pack_problems))

            # 篡改 manifest（JSON 仍可解析的尾部空格）→ 验签失败（G-A1 破坏性断言）
            manifest_path = pack / "manifest.json"
            original_bytes = manifest_path.read_bytes()
            manifest_path.write_bytes(original_bytes + b" ")
            problems = verify_pack(pack, public_key=record["public_key"])
            self.assertTrue(any("签名验证失败" in p for p in problems), problems)
            manifest_path.write_bytes(original_bytes)
            self.assertEqual(verify_pack(pack, public_key=record["public_key"]), [])

            # 私钥材料绝不进入任何提交物
            seed_hex = seed.hex()
            for artifact in (pack / "signature.json",):
                self.assertNotIn(seed_hex, artifact.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
