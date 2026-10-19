"""R7/W3：独立第三方验证器扩展——tools 分发副本、签名/锚定校验接入。

集成部分（真实证据包）依赖 icode-skill 子模块，缺失时跳过（与既有证据包
测试同一纪律）；结构断言与 CLI 行为不依赖 skill。
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._support import REPO_ROOT, require_skill
from icode import pack_signing
from icode.evidence import build_evidence_pack
from icode.pack_anchor import build_git_tag_record, attach_anchor_records
from icode.pack_verify import (
    ANCHORS_NAME,
    SIGNATURE_NAME,
    verify_pack,
)
from icode.control import ControlPlane

MODULE_PATH = REPO_ROOT / "src" / "icode" / "pack_verify.py"
TOOLS_PATH = REPO_ROOT / "tools" / "verify_evidence_pack.py"


class ToolsCopyTests(unittest.TestCase):
    def test_tools_copy_is_byte_identical(self):
        self.assertTrue(TOOLS_PATH.is_file(), "缺少 tools/verify_evidence_pack.py")
        module_sha = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
        tools_sha = hashlib.sha256(TOOLS_PATH.read_bytes()).hexdigest()
        self.assertEqual(module_sha, tools_sha)

    def test_tools_copy_is_stdlib_only(self):
        source = TOOLS_PATH.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and not stripped.startswith("from __future__"):
                root_module = stripped.split()[1].split(".")[0].rstrip(",")
                self.assertNotEqual(root_module, "icode", stripped)
                self.assertNotIn("icode.", stripped, stripped)

    def test_usage_errors(self):
        proc = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", str(TOOLS_PATH)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("用法", proc.stdout + proc.stderr)
        proc = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", str(TOOLS_PATH),
             "--public-key", "not-hex", "/tmp"],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(proc.returncode, 2)


class SignedPackIntegrationTests(unittest.TestCase):
    """真实证据包上的签名/锚定全链路（需要 icode-skill）。"""

    def _build_pack(self, root: Path) -> tuple[Path, str]:
        settings = require_skill()
        cp = ControlPlane(settings)
        code = root / "code"
        code.mkdir()
        (root / "control").mkdir()
        ticket = root / "control/.icode_output/.icode_output_1"
        cp.create(ticket, ticket_id="r7-trust", requirement="trusted delivery")
        cp.bind_execution_root(ticket, ticket_id="r7-trust", execution_root=code)
        pack = root / "pack"
        commit = os.environ.get("ICODE_R7_TEST_COMMIT", "")
        report = build_evidence_pack(
            ticket, dest=pack, gates_json=settings.gates_json, clean=False,
            code_commit=commit or None,
        )
        self.assertTrue(report.ok, report.render())
        return pack, commit

    def test_unsigned_pack_reports_unsigned_and_require_signature_fails(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-unsigned-") as raw:
            root = Path(raw)
            pack, _ = self._build_pack(root)
            self.assertEqual(verify_pack(pack), [])
            self.assertEqual(
                verify_pack(pack, require_signature=True),
                ["缺少签名文件 signature.json（--require-signature 要求签名）"],
            )

    def test_provenance_section_present(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-prov-") as raw:
            root = Path(raw)
            pack, commit = self._build_pack(root)
            manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
            provenance = manifest.get("provenance")
            self.assertIsInstance(provenance, dict)
            self.assertIn("python_version", provenance)
            self.assertEqual(provenance["dependencies"], "core: none")
            if commit:
                self.assertEqual(provenance.get("code_commit"), commit)

    def test_sign_anchor_verify_full_chain_and_standalone(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-signed-") as raw:
            root = Path(raw)
            pack, _ = self._build_pack(root)
            manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
            digest = manifest["pack_digest"]

            # 锚定预声明（签名前）→ 签名 → 包内验证
            attach_anchor_records(pack, [
                build_git_tag_record(digest, "https://github.com/ayukyo/icode"),
            ])
            key_path = root / "signing.key"
            pack_signing.write_signing_key(pack_signing.generate_signing_key(), key_path)
            record = pack_signing.sign_pack(pack, key_path)
            public_key = record["public_key"]

            # 包内验证：提供公钥 → 通过；不提供 → 拒绝（有签名必须验）
            self.assertEqual(verify_pack(pack, public_key=public_key), [])
            self.assertTrue(verify_pack(pack))
            self.assertTrue(any("未提供" in p for p in verify_pack(pack)))

            # manifest 篡改（JSON 仍可解析的尾部空格）→ 验签失败
            manifest_path = pack / "manifest.json"
            original_bytes = manifest_path.read_bytes()
            manifest_path.write_bytes(original_bytes + b" ")
            problems = verify_pack(pack, public_key=public_key)
            self.assertTrue(any("签名验证失败" in p for p in problems), problems)
            manifest_path.write_bytes(original_bytes)

            # 清单外豁免封闭性：陌生文件仍被 ⑤ 拒绝
            (pack / "rogue.txt").write_text("smuggled", encoding="utf-8")
            problems = verify_pack(pack, public_key=public_key)
            self.assertTrue(any("未登记的额外文件" in p and "rogue.txt" in p
                                for p in problems), problems)
            (pack / "rogue.txt").unlink()

            # 第三方独立验证（无 ICODE 运行环境）：tools 副本 -I 隔离模式
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            proc = subprocess.run(
                [sys.executable, "-I", "-B", "-X", "utf8", str(TOOLS_PATH),
                 str(pack), "--public-key", public_key, "--require-signature"],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, (proc.stdout, proc.stderr))
            self.assertIn("证据包校验通过", proc.stdout)
            self.assertIn("Ed25519 签名", proc.stdout)

            # 包内 verify.py 副本同样通过（BOM 副本机制沿用）
            proc = subprocess.run(
                [sys.executable, "-I", "-B", "-X", "utf8", str(pack / "verify.py"),
                 str(pack), "--public-key", public_key],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, (proc.stdout, proc.stderr))


if __name__ == "__main__":
    unittest.main()
