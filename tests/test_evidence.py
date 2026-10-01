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

    def test_导出器保留JSON字符串中的Unicode行分隔符(self) -> None:
        from icode.pack_verify import GENESIS_HASH, canonical_event_hash

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            events[0]["payload"]["unicode_separators"] = "NEL:\u0085 LS:\u2028 PS:\u2029"
            previous_hash = GENESIS_HASH
            for event in events:
                event["previous_event_hash"] = previous_hash
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )
            original_bytes = events_path.read_bytes()

            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )

            self.assertTrue(report.ok, report.render())
            self.assertEqual((dest / "ticket" / "events.jsonl").read_bytes(), original_bytes)
            self.assertEqual(verify_pack(dest), [])

    def test_导出器拒绝非对象事件且在清理旧包前失败(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            (out_dir / ".ico_events.jsonl").write_text("null\n", encoding="utf-8")
            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_text("keep existing evidence pack\n", encoding="utf-8")

            with self.assertRaises(EvidenceError):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep existing evidence pack\n")

    def test_导出器拒绝任意事件类型的非对象payload并保留旧包(self) -> None:
        from icode.evidence import EvidenceError
        from icode.pack_verify import GENESIS_HASH, canonical_event_hash

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(events[0]["event_type"], "ticket_created")
            events[0]["payload"] = None
            previous_hash = GENESIS_HASH
            for event in events:
                event["previous_event_hash"] = previous_hash
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )

            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_text("keep existing evidence pack\n", encoding="utf-8")

            with self.assertRaisesRegex(EvidenceError, "payload"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep existing evidence pack\n")

    def test_任意事件类型的空对象payload仍兼容导出和校验(self) -> None:
        from icode.pack_verify import GENESIS_HASH, canonical_event_hash

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(events[0]["event_type"], "ticket_created")
            events[0]["payload"] = {}
            previous_hash = GENESIS_HASH
            for event in events:
                event["previous_event_hash"] = previous_hash
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )

            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())
            self.assertEqual(verify_pack(dest), [])
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            standalone = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws),
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                shell=False,
            )
            self.assertEqual(standalone.returncode, 0, standalone.stdout + standalone.stderr)

    def test_导出器不累计保留大量非产物事件payload(self) -> None:
        import tracemalloc

        from icode.pack_verify import canonical_event_hash

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            previous_hash = events[-1]["event_hash"]
            ticket_id = events[0]["ticket_id"]
            padding = "x" * (16 * 1024)
            for index in range(256):
                event = {
                    "schema_version": 1,
                    "event_id": f"synthetic-event-{index}",
                    "ticket_id": ticket_id,
                    "timestamp": "2026-10-01T00:00:00+00:00",
                    "actor": "system",
                    "event_type": "external_note",
                    "payload": {"note": padding},
                    "previous_event_hash": previous_hash,
                }
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
                events.append(event)
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )

            dest = ws / "pack"
            tracemalloc.start()
            try:
                report = build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )
                _, peak_bytes = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()

            self.assertTrue(report.ok, report.render())
            self.assertEqual(report.event_count, len(events))
            self.assertLess(
                peak_bytes,
                3 * 1024 * 1024,
                "导出器不应累计保留所有非产物事件 payload："
                f"峰值分配 {peak_bytes} 字节",
            )

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
                base_commit_sha="a" * 40,
                initial_worktree_fingerprint="initial-tree",
                tested_worktree_fingerprint="tested-tree",
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
            self.assertEqual(receipts[0]["base_commit_sha"], "a" * 40)
            self.assertEqual(receipts[0]["initial_worktree_fingerprint"], "initial-tree")
            self.assertEqual(receipts[0]["tested_worktree_fingerprint"], "tested-tree")
            self.assertEqual(receipts[0]["artifact_hashes"], {"calc.py": "abc"})
            self.assertTrue(receipts[0]["fingerprint"])
            self.assertNotIn("AssertionError: boom", json.dumps(receipts[0]))

    def test_独立task回执写为JSON且不覆盖已有文件(self) -> None:
        from icode.evidence import EvidenceError, save_verification_receipt
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            destination = ws / "receipts" / "task.json"
            destination.parent.mkdir()
            evidence = VerificationEvidence(
                step="task", attempt="1", kind="test", exit_code=0,
                output="private test output", raw_error="private detail",
                result_commit_sha="a" * 40,
                result_commit_tree_oid="b" * 40,
                result_commit_tree_status="matched",
            )

            written = save_verification_receipt(evidence, destination)

            self.assertEqual(written, destination)
            payload = destination.read_bytes()
            receipt = json.loads(payload)
            self.assertEqual(receipt, evidence.to_receipt())
            self.assertNotIn("private test output", payload.decode("utf-8"))
            self.assertNotIn("private detail", payload.decode("utf-8"))
            with self.assertRaises(EvidenceError):
                save_verification_receipt(evidence, destination)
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual([path.name for path in destination.parent.iterdir()], ["task.json"])

    def test_task回执输出不自动创建父目录(self) -> None:
        from icode.evidence import EvidenceError, save_verification_receipt
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            parent = ws / "not-created"
            destination = parent / "task.json"
            evidence = VerificationEvidence(step="task", attempt="1", exit_code=1)

            with self.assertRaises(EvidenceError):
                save_verification_receipt(evidence, destination)

            self.assertFalse(parent.exists())

    def test_task回执拒绝包含NUL的目标路径(self) -> None:
        from icode.evidence import EvidenceError, save_verification_receipt
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            destination = ws / "bad\x00name.json"
            evidence = VerificationEvidence(step="task", attempt="1", exit_code=0)

            with self.assertRaisesRegex(EvidenceError, "目标文件名无效"):
                save_verification_receipt(evidence, destination)

            self.assertEqual(list(ws.iterdir()), [])

    def test_task回执拒绝非验证证据类型(self) -> None:
        from icode.evidence import EvidenceError, save_verification_receipt

        class ForeignReceipt:
            def to_receipt(self) -> dict[str, str]:
                return {"kind": "verification", "arbitrary": "value"}

        with temp_workspace() as ws:
            destination = ws / "receipt.json"
            with self.assertRaises(EvidenceError):
                save_verification_receipt(ForeignReceipt(), destination)

            self.assertFalse(destination.exists())
            self.assertEqual(list(ws.iterdir()), [])

    def test_task回执发布失败清理临时文件(self) -> None:
        from unittest.mock import patch

        from icode.evidence import EvidenceError, save_verification_receipt
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            destination = ws / "receipt.json"
            evidence = VerificationEvidence(step="task", attempt="1", exit_code=0)
            with patch("icode.evidence.os.link", side_effect=OSError("private path")):
                with self.assertRaisesRegex(EvidenceError, "无法安全写入或发布"):
                    save_verification_receipt(evidence, destination)

            self.assertFalse(destination.exists())
            self.assertEqual(list(ws.iterdir()), [])

    def test_task回执内容类型损坏时返回安全错误(self) -> None:
        from icode.evidence import EvidenceError, save_verification_receipt
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            destination = ws / "receipt.json"
            malformed = VerificationEvidence(
                step="task", attempt="1", output=object(),  # type: ignore[arg-type]
            )

            with self.assertRaisesRegex(EvidenceError, "无法编码为 JSON"):
                save_verification_receipt(malformed, destination)

            self.assertFalse(destination.exists())
            self.assertEqual(list(ws.iterdir()), [])

    def test_task回执可直接导入证据包CLI(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.cli import _build_parser, cmd_evidence
        from icode.evidence import save_verification_receipt
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            receipt_path = ws / "task-verification.json"
            evidence = VerificationEvidence(
                step="task", attempt="1", kind="test", exit_code=0,
                result_commit_sha="a" * 40,
                result_commit_tree_oid="b" * 40,
                result_commit_tree_status="matched",
            )
            save_verification_receipt(evidence, receipt_path)
            pack_path = ws / "pack"
            args = _build_parser().parse_args([
                "evidence", "--ticket", str(ticket), "--dest", str(pack_path),
                "--receipt", str(receipt_path),
            ])

            with patch("icode.cli.load_settings", return_value=self.settings):
                with redirect_stdout(StringIO()):
                    exit_code = cmd_evidence(args)

            self.assertEqual(exit_code, 0)
            packed = json.loads(
                (pack_path / "verifications.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                packed["receipts"][0]["result_commit_tree_status"], "matched",
            )
            self.assertEqual(verify_pack(pack_path), [])

    def test_evidence导入无效回执时返回用户错误且不触碰目标包(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.cli import main

        cases = (
            ("invalid-json", b"{\"receipt\":", "JSON 格式无效", False),
            ("invalid-utf8", b"\xff", "不是有效 UTF-8", True),
            ("non-object", b"null", "回执文件结构无效", False),
            ("non-object-item", b"[{\"kind\":\"command\"}, null]", "回执文件结构无效", True),
            ("nan", b"{\"value\":NaN}", "JSON 格式无效", True),
            ("positive-infinity", b"{\"value\":Infinity}", "JSON 格式无效", True),
            ("negative-infinity", b"{\"value\":-Infinity}", "JSON 格式无效", True),
            ("overflow", b"{\"value\":1e400}", "JSON 格式无效", True),
            ("duplicate-member", b"{\"value\":1,\"value\":2}", "JSON 格式无效", True),
            ("lone-surrogate", b"{\"value\":\"\\ud800\"}", "JSON 格式无效", True),
            (
                "over-nesting-limit",
                b'{"value":' + b"[" * 128 + b"0" + b"]" * 128 + b"}",
                "JSON 格式无效",
                True,
            ),
            (
                "deeply-nested",
                b'{"value":' * 1200 + b"0" + b"}" * 1200,
                "JSON 格式无效",
                True,
            ),
        )
        for name, contents, expected_error, existing_pack in cases:
            with self.subTest(receipt=name), temp_workspace() as ws:
                ticket = make_finished_plan_ticket(self.settings, ws / "work")
                receipt_path = ws / f"{name}.json"
                receipt_path.write_bytes(contents)
                pack_path = ws / "pack"
                marker = pack_path / "keep.txt"
                if existing_pack:
                    pack_path.mkdir()
                    marker.write_bytes(b"keep existing evidence pack")

                stdout = StringIO()
                stderr = StringIO()
                with (
                    patch("icode.cli.load_settings", return_value=self.settings),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    exit_code = main([
                        "evidence",
                        "--ticket", str(ticket),
                        "--dest", str(pack_path),
                        "--receipt", str(receipt_path),
                    ])

                if exit_code != 2:
                    self.fail(
                        f"{name}: expected invalid receipt to return 2, got {exit_code}; "
                        f"stdout={stdout.getvalue()!r}, stderr={stderr.getvalue()!r}"
                    )
                self.assertIn(expected_error, stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())
                if existing_pack:
                    self.assertEqual(marker.read_bytes(), b"keep existing evidence pack")
                    self.assertEqual(list(pack_path.iterdir()), [marker])
                else:
                    self.assertFalse(pack_path.exists())

    def test_evidence导入有限浮点回执后可生成并独立校验(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.cli import main

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            receipt_path = ws / "finite.json"
            receipt_path.write_bytes(b'{"ratio":1.25}')
            pack_path = ws / "pack"
            stdout = StringIO()
            stderr = StringIO()
            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main([
                    "evidence",
                    "--ticket", str(ticket),
                    "--dest", str(pack_path),
                    "--receipt", str(receipt_path),
                ])

            self.assertEqual(exit_code, 0, stdout.getvalue() + stderr.getvalue())
            verifications = json.loads(
                (pack_path / "verifications.json").read_text(encoding="utf-8")
            )
            self.assertEqual(verifications["receipts"], [{"ratio": 1.25}])
            self.assertEqual(verify_pack(pack_path), [])

    def test_evidence导入最大嵌套深度回执可生成并独立校验(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.cli import main

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            receipt_path = ws / "max-depth.json"
            # Root object plus 127 nested arrays is exactly 128 containers deep.
            receipt_path.write_bytes(
                b'{"value":' + b"[" * 127 + b"0" + b"]" * 127 + b"}"
            )
            pack_path = ws / "pack"
            stdout = StringIO()
            stderr = StringIO()
            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main([
                    "evidence",
                    "--ticket", str(ticket),
                    "--dest", str(pack_path),
                    "--receipt", str(receipt_path),
                ])

            self.assertEqual(exit_code, 0, stdout.getvalue() + stderr.getvalue())
            self.assertEqual(verify_pack(pack_path), [])

    def test真实task回执经CLI保存导入证据包并独立校验(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.approvals import DenyAllApprover
        from icode.backends import FakeBackend
        from icode.budget import Budget
        from icode.cli import main
        from icode.isolation import NoIsolation

        with temp_workspace() as ws:
            repo = ws / "repo"
            repo.mkdir()
            source = repo / "calc.py"
            test_file = repo / "test_calc.py"
            source.write_bytes(b"def add(a, b): return a + b")
            test_file.write_bytes(
                b"import unittest\n"
                b"from calc import add\n\n"
                b"class TestCalc(unittest.TestCase):\n"
                b"    def test_add(self):\n"
                b"        self.assertEqual(add(2, 3), 5)\n"
            )

            def git(*arguments: str) -> str:
                result = subprocess.run(
                    ["git", "-C", str(repo), *arguments],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                    shell=False,
                )
                return result.stdout.strip()

            git("init", "-q")
            git("config", "user.name", "ICODE tests")
            git("config", "user.email", "icode-tests@example.invalid")
            git("config", "core.autocrlf", "false")
            git("add", "calc.py", "test_calc.py")
            git("commit", "-q", "-m", "baseline")
            base_commit = git("rev-parse", "HEAD")

            result_source = "def add(a, b): return a + b # task result"
            source.write_bytes(result_source.encode("utf-8"))
            git("add", "calc.py")
            git("commit", "-q", "-m", "expected task result")
            result_commit = git("rev-parse", "HEAD")
            result_tree = git("rev-parse", "HEAD^{tree}")
            git("reset", "--hard", base_commit)

            backend = FakeBackend([
                {"content": "", "tool_calls": [{
                    "id": "executor-edit",
                    "name": "write_file",
                    "arguments": {
                        "path": str(source),
                        "content": result_source,
                    },
                }]},
                "executor finished",
                {"content": "", "tool_calls": [{
                    "id": "review-read",
                    "name": "read_file",
                    "arguments": {"path": "calc.py"},
                }]},
                {"content": "", "tool_calls": [{
                    "id": "review-submit",
                    "name": "submit_review",
                    "arguments": {
                        "summary": "Reviewed the changed source.",
                        "findings": [],
                    },
                }]},
                "review submitted",
            ])
            receipt_path = ws / "task-verification.json"
            task_stdout = StringIO()
            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                patch(
                    "icode.cli._build_runner",
                    return_value=(
                        backend,
                        DenyAllApprover(),
                        Budget(),
                        None,
                        NoIsolation(),
                    ),
                ),
                redirect_stdout(task_stdout),
            ):
                task_exit = main([
                    "task",
                    "--workspace", str(repo),
                    "--task", "Keep add behavior unchanged and apply the requested edit.",
                    "--max-repairs", "0",
                    "--result-commit", result_commit,
                    "--receipt-out", str(receipt_path),
                ])

            self.assertEqual(task_exit, 0, task_stdout.getvalue())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual(receipt["test_head_status"], "stable")
            self.assertEqual(receipt["test_head_before_sha"], base_commit)
            self.assertEqual(receipt["test_head_after_sha"], base_commit)
            self.assertEqual(receipt["tested_git_tree_status"], "stable")
            self.assertEqual(receipt["tested_git_tree_oid"], result_tree)
            self.assertEqual(receipt["result_commit_sha"], result_commit)
            self.assertEqual(receipt["result_commit_tree_oid"], result_tree)
            self.assertEqual(receipt["result_commit_tree_status"], "matched")
            self.assertTrue(receipt["fingerprint"])
            self.assertNotIn("output", receipt)
            self.assertEqual(git("rev-parse", "HEAD"), base_commit)

            ticket = make_finished_plan_ticket(self.settings, ws / "ticket-work")
            pack_path = ws / "pack"
            evidence_stdout = StringIO()
            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                redirect_stdout(evidence_stdout),
            ):
                evidence_exit = main([
                    "evidence",
                    "--ticket", str(ticket),
                    "--dest", str(pack_path),
                    "--receipt", str(receipt_path),
                ])

            self.assertEqual(evidence_exit, 0, evidence_stdout.getvalue())
            packed = json.loads(
                (pack_path / "verifications.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(packed["receipts"], [receipt])
            self.assertEqual(verify_pack(pack_path), [])

            verify_stdout = StringIO()
            with redirect_stdout(verify_stdout):
                verify_exit = main(["verify-pack", str(pack_path)])
            self.assertEqual(verify_exit, 0, verify_stdout.getvalue())
            self.assertIn("证据包校验通过", verify_stdout.getvalue())

            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(pack_path / "verify.py"), str(pack_path)],
                cwd=str(ws),
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                shell=False,
            )
            self.assertEqual(
                independent.returncode,
                0,
                independent.stdout + independent.stderr,
            )
            self.assertIn("校验通过", independent.stdout)

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
        allowed = {"hashlib", "json", "math", "os", "pathlib", "stat", "sys", "__future__"}
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

    def test_内置和独立校验器对畸形JSON结构返回失败而不抛异常(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main

        def write_json(path: Path, value: object) -> None:
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

        def replace_event(pack: Path, field: str, value: object, *, artifact: bool = False) -> None:
            events_path = pack / "ticket" / "events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            target = next(
                event for event in events
                if event.get("event_type") == ("artifact_written" if artifact else "ticket_created")
            )
            target[field] = value
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )

        def invalid_event_root(pack: Path) -> None:
            (pack / "ticket" / "events.jsonl").write_text("null\n", encoding="utf-8")

        def invalid_manifest_root(pack: Path) -> None:
            write_json(pack / "manifest.json", [])

        def over_nested_manifest(pack: Path) -> None:
            manifest_path = pack / "manifest.json"
            text = manifest_path.read_text(encoding="utf-8").rstrip()
            self.assertTrue(text.endswith("}"), text[-32:])
            manifest_path.write_text(
                text[:-1] + ',"audit_note":' + "[" * 128 + "0" + "]" * 128 + "}\n",
                encoding="utf-8",
            )

        def invalid_manifest_item(pack: Path) -> None:
            manifest_path = pack / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"] = [None]
            write_json(manifest_path, manifest)

        def missing_manifest_digest(pack: Path) -> None:
            manifest_path = pack / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"] = [{"path": "ticket/events.jsonl"}]
            write_json(manifest_path, manifest)

        def invalid_artifact_root(pack: Path) -> None:
            write_json(pack / "artifacts.json", [])

        def invalid_artifact_item(pack: Path) -> None:
            write_json(pack / "artifacts.json", {"artifacts": [None]})

        cases = (
            ("manifest-root", invalid_manifest_root, "清单文件不可解析"),
            ("manifest-over-nested", over_nested_manifest, "嵌套深度"),
            ("manifest-item", invalid_manifest_item, "清单 files 第 1 项结构无效"),
            ("manifest-missing-hash", missing_manifest_digest, "缺少有效 path 或 sha256"),
            ("event-root", invalid_event_root, "事件链第 1 行结构无效"),
            ("event-id-type", lambda pack: replace_event(
                pack, "event_id", [],
            ), "event_id 结构无效"),
            ("event-type", lambda pack: replace_event(
                pack, "event_type", [],
            ), "首条事件类型"),
            ("artifact-payload", lambda pack: replace_event(
                pack, "payload", ["malformed"], artifact=True,
            ), "artifact_written 事件 payload 结构无效"),
            ("artifact-index-root", invalid_artifact_root, "artifacts.json 不可解析"),
            ("artifact-index-item", invalid_artifact_item, "artifacts.json 第 1 项结构无效"),
        )
        for name, mutate, expected_problem in cases:
            with self.subTest(structure=name), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                dest = ws / "pack"
                report = build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())
                mutate(dest)

                problems = verify_pack(dest)
                self.assertTrue(problems, name)
                self.assertTrue(
                    any(expected_problem in problem for problem in problems),
                    f"{name}: {problems}",
                )

                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["verify-pack", str(dest)])
                self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
                self.assertIn("证据包校验失败", stdout.getvalue())
                self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())

                standalone = self._run_verifier(dest, cwd=ws)
                self.assertEqual(
                    standalone.returncode, 1, standalone.stdout + standalone.stderr,
                )
                self.assertIn("校验失败", standalone.stdout)
                self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

    def test_所有Verifier拒绝哈希自洽事件中的非对象payload(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main
        from icode.pack_verify import GENESIS_HASH, canonical_event_hash, pack_digest, sha256_file

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            events_path = dest / "ticket" / "events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(events[0]["event_type"], "ticket_created")
            events[0]["payload"] = None
            previous_hash = GENESIS_HASH
            for event in events:
                event["previous_event_hash"] = previous_hash
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )

            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            event_entry = next(
                item for item in manifest["files"]
                if item["path"] == "ticket/events.jsonl"
            )
            event_entry["sha256"] = sha256_file(events_path)
            event_entry["size"] = events_path.stat().st_size
            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            problems = verify_pack(dest)
            self.assertTrue(
                any("事件 payload 结构无效" in problem for problem in problems),
                problems,
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["verify-pack", str(dest)])
            self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
            self.assertIn("事件 payload 结构无效", stdout.getvalue())
            self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())

            standalone = self._run_verifier(dest, cwd=ws)
            self.assertEqual(standalone.returncode, 1, standalone.stdout + standalone.stderr)
            self.assertIn("事件 payload 结构无效", standalone.stdout)
            self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

    def test_内置和独立校验器拒绝证据包中的重复JSON成员名(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main
        from icode.pack_verify import pack_digest, sha256_file

        def replace_member(pack: Path, member: str) -> None:
            if member == "manifest.json":
                path = pack / member
                text = path.read_text(encoding="utf-8")
                unique_member = '"path": "ticket/metadata.json"'
                self.assertIn(unique_member, text)
                path.write_text(
                    text.replace(
                        unique_member,
                        '"p\\u0061th": "ignored-shadow.txt", ' + unique_member,
                        1,
                    ),
                    encoding="utf-8",
                )
                return

            path = pack / member
            text = path.read_text(encoding="utf-8")
            if member == "ticket/events.jsonl":
                unique_member = '"event_type": "ticket_created"'
                duplicate = '"event_type": "ignored-shadow", ' + unique_member
            else:
                unique_member = '"artifacts": ['
                duplicate = '"artifacts": [], ' + unique_member
            self.assertIn(unique_member, text)
            path.write_text(text.replace(unique_member, duplicate, 1), encoding="utf-8")

            manifest_path = pack / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = next(item for item in manifest["files"] if item["path"] == member)
            entry["sha256"] = sha256_file(path)
            entry["size"] = path.stat().st_size
            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        for member in ("manifest.json", "ticket/events.jsonl", "artifacts.json"):
            with self.subTest(member=member), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                dest = ws / "pack"
                report = build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())
                replace_member(dest, member)

                problems = verify_pack(dest)
                self.assertTrue(problems)
                self.assertTrue(
                    any("重复 JSON 成员名" in problem for problem in problems), problems,
                )

                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["verify-pack", str(dest)])
                self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
                self.assertIn("重复 JSON 成员名", stdout.getvalue())
                self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())

                standalone = self._run_verifier(dest, cwd=ws)
                self.assertEqual(
                    standalone.returncode, 1, standalone.stdout + standalone.stderr,
                )
                self.assertIn("重复 JSON 成员名", standalone.stdout)
                self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

    def test_文件摘要采用有界内存分块读取(self) -> None:
        import hashlib
        import tracemalloc

        from icode.pack_verify import sha256_file

        with temp_workspace() as ws:
            artifact = ws / "large-artifact.bin"
            artifact_size = 8 * 1024 * 1024
            with artifact.open("wb") as stream:
                stream.truncate(artifact_size)

            with artifact.open("rb") as stream:
                expected = hashlib.file_digest(stream, "sha256").hexdigest()

            tracemalloc.start()
            try:
                actual = sha256_file(artifact)
                _, peak_bytes = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()

            self.assertEqual(actual, expected)
            self.assertLess(
                peak_bytes,
                4 * 1024 * 1024,
                f"哈希单个 {artifact_size} 字节文件时 Python 峰值分配 {peak_bytes} 字节",
            )

    def test_event_chain校验不累计保留非产物事件payload(self) -> None:
        import tracemalloc

        from icode.pack_verify import _verify_event_chain, canonical_event_hash

        with temp_workspace() as ws:
            events_path = ws / "events.jsonl"
            previous_hash = "0" * 64
            padding = "x" * (16 * 1024)
            with events_path.open("w", encoding="utf-8") as stream:
                for index in range(256):
                    event = {
                        "event_id": f"large-event-{index}",
                        "event_type": "ticket_created" if index == 0 else "command_output",
                        "payload": {"padding": padding},
                        "previous_event_hash": previous_hash,
                    }
                    event["event_hash"] = canonical_event_hash(event)
                    previous_hash = event["event_hash"]
                    stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
                    stream.write("\n")

            tracemalloc.start()
            try:
                _artifact_facts, problems = _verify_event_chain(events_path)
                _, peak_bytes = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()

            self.assertEqual(problems, [])
            self.assertLess(
                peak_bytes,
                2 * 1024 * 1024,
                "逐行验证不应按全部非产物 payload 累积 Python 对象："
                f"峰值分配 {peak_bytes} 字节",
            )

    def test_event_chain校验仍拒绝重复event_id(self) -> None:
        from icode.pack_verify import _verify_event_chain, canonical_event_hash

        with temp_workspace() as ws:
            events_path = ws / "duplicate-ids.jsonl"
            previous_hash = "0" * 64
            lines: list[str] = []
            for index, event_type in enumerate(("ticket_created", "command_output")):
                event = {
                    "event_id": "reused-event-id",
                    "event_type": event_type,
                    "payload": {"sequence": index},
                    "previous_event_hash": previous_hash,
                }
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
                lines.append(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            _artifact_facts, problems = _verify_event_chain(events_path)

            self.assertTrue(any("event_id 重复" in problem for problem in problems), problems)

    def test_所有Verifier拒绝孤立代理项并接受合法代理对(self) -> None:
        invalid_scalar = chr(0xD800)
        cases = (
            ("manifest object key", "manifest_key", 1),
            ("manifest.files.path", "path", 1),
            ("manifest.pack_digest", "digest", 1),
            ("manifest.files.sha256", "file_hash", 1),
            ("manifest.ticket.ticket_id", "ticket_id", 1),
            ("artifacts.json", "artifact_index", 1),
            ("event.payload", "event_payload", 1),
            ("valid surrogate pair", "paired_ticket", 0),
        )
        cli_code = "from icode.cli import main; raise SystemExit(main())"

        for name, mutation, expected_exit in cases:
            with self.subTest(field=name), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                dest = ws / "pack"
                report = build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())

                manifest_path = dest / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if mutation == "manifest_key":
                    manifest[invalid_scalar] = "invalid member name"
                elif mutation == "path":
                    manifest["files"].append({
                        "path": invalid_scalar, "sha256": "0" * 64, "size": 0,
                    })
                elif mutation == "digest":
                    manifest["pack_digest"] = invalid_scalar
                elif mutation == "file_hash":
                    manifest["files"][0]["sha256"] = invalid_scalar
                elif mutation == "ticket_id":
                    manifest["ticket"]["ticket_id"] = invalid_scalar
                elif mutation == "artifact_index":
                    index_path = dest / "artifacts.json"
                    index = json.loads(index_path.read_text(encoding="utf-8"))
                    index["audit_note"] = invalid_scalar
                    index_path.write_text(
                        json.dumps(index, ensure_ascii=True, indent=2) + "\n",
                        encoding="utf-8",
                    )
                elif mutation == "event_payload":
                    events_path = dest / "ticket" / "events.jsonl"
                    events = [
                        json.loads(line)
                        for line in events_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    events[0]["payload"]["audit_note"] = invalid_scalar
                    events_path.write_text(
                        "\n".join(
                            json.dumps(event, ensure_ascii=True) for event in events
                        ) + "\n",
                        encoding="utf-8",
                    )
                else:
                    manifest["ticket"]["ticket_id"] = chr(0xD83D) + chr(0xDE00)
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )

                problems = verify_pack(dest)
                rendered = "\n".join(problems)
                self.assertEqual(bool(problems), expected_exit == 1, rendered)
                self.assertNotIn(invalid_scalar, rendered)
                if expected_exit:
                    self.assertTrue(
                        any("孤立 UTF-16 代理项" in problem for problem in problems),
                        rendered,
                    )

                env = dict(os.environ)
                env["PYTHONPATH"] = str(REPO_ROOT / "src")
                env["PYTHONIOENCODING"] = "utf-8:strict"
                cli = subprocess.run(
                    [sys.executable, "-c", cli_code, "verify-pack", str(dest)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    cwd=str(ws), env=env, shell=False,
                )
                self.assertEqual(
                    cli.returncode, expected_exit, cli.stdout + cli.stderr,
                )
                self.assertNotIn("Traceback", cli.stdout + cli.stderr)
                self.assertNotIn(invalid_scalar, cli.stdout + cli.stderr)

                standalone = self._run_verifier(
                    dest, cwd=ws, extra_env={"PYTHONIOENCODING": "utf-8:strict"},
                )
                self.assertEqual(
                    standalone.returncode, expected_exit,
                    standalone.stdout + standalone.stderr,
                )
                self.assertNotIn(
                    "Traceback", standalone.stdout + standalone.stderr,
                )
                self.assertNotIn(invalid_scalar, standalone.stdout + standalone.stderr)

    def test_所有Verifier拒绝非标准非有限数值(self) -> None:
        from icode.pack_verify import canonical_event_hash, pack_digest, sha256_file

        numeric_cases = (
            ("event NaN", "event", float("nan"), "NaN", "NaN", True),
            ("manifest Infinity", "manifest", float("inf"), "Infinity", "Infinity", True),
            ("artifact -Infinity", "artifact", float("-inf"), "-Infinity", "-Infinity", True),
            ("event positive exponent overflow", "event", float("inf"), "Infinity", "1e400", True),
            ("event negative exponent overflow", "event", float("-inf"), "-Infinity", "-1e400", True),
            ("event finite number", "event", 1.25, "1.25", "1.25", False),
        )
        cli_code = "from icode.cli import main; raise SystemExit(main())"

        for name, surface, number, serialized_value, wire_value, should_reject in numeric_cases:
            with self.subTest(value=name), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                dest = ws / "pack"
                report = build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())

                manifest_path = dest / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

                if surface == "event":
                    events_path = dest / "ticket" / "events.jsonl"
                    events = [
                        json.loads(line)
                        for line in events_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    events[0]["payload"]["audit_number"] = number
                    previous_hash = "0" * 64
                    for event in events:
                        event["previous_event_hash"] = previous_hash
                        event["event_hash"] = canonical_event_hash(event)
                        previous_hash = event["event_hash"]
                    event_lines = [
                        json.dumps(event, ensure_ascii=False) for event in events
                    ]
                    if wire_value != serialized_value:
                        marker = f'"audit_number": {serialized_value}'
                        self.assertIn(marker, event_lines[0])
                        event_lines[0] = event_lines[0].replace(
                            marker, f'"audit_number": {wire_value}', 1,
                        )
                    events_path.write_text(
                        "\n".join(event_lines) + "\n", encoding="utf-8",
                    )
                    event_entry = next(
                        entry for entry in manifest["files"]
                        if entry["path"] == "ticket/events.jsonl"
                    )
                    event_entry["sha256"] = sha256_file(events_path)
                    event_entry["size"] = events_path.stat().st_size
                    manifest["pack_digest"] = pack_digest(manifest["files"])
                elif surface == "manifest":
                    manifest["audit_number"] = number
                else:
                    index_path = dest / "artifacts.json"
                    index = json.loads(index_path.read_text(encoding="utf-8"))
                    index["audit_number"] = number
                    index_path.write_text(
                        json.dumps(index, ensure_ascii=True, indent=2) + "\n",
                        encoding="utf-8",
                    )

                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )

                problems = verify_pack(dest)
                if should_reject:
                    self.assertTrue(
                        any("非有限" in problem or "非标准 JSON 数值" in problem for problem in problems),
                        problems,
                    )
                else:
                    self.assertEqual(problems, [])

                env = dict(os.environ)
                env["PYTHONPATH"] = str(REPO_ROOT / "src")
                env["PYTHONIOENCODING"] = "utf-8:strict"
                cli = subprocess.run(
                    [sys.executable, "-c", cli_code, "verify-pack", str(dest)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    cwd=str(ws), env=env, shell=False,
                )
                expected_exit = 1 if should_reject else 0
                self.assertEqual(cli.returncode, expected_exit, cli.stdout + cli.stderr)
                self.assertNotIn("Traceback", cli.stdout + cli.stderr)

                standalone = self._run_verifier(
                    dest, cwd=ws, extra_env={"PYTHONIOENCODING": "utf-8:strict"},
                )
                self.assertEqual(
                    standalone.returncode, expected_exit,
                    standalone.stdout + standalone.stderr,
                )
                self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

    def test_内置和独立校验器接受JSON字符串中的Unicode行段符号(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main
        from icode.pack_verify import canonical_event_hash, pack_digest, sha256_file

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            events_path = dest / "ticket" / "events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertIsInstance(events[0].get("payload"), dict)
            events[0]["payload"]["audit_note"] = (
                "第一段\u0085第二段\u2028第三段\u2029第四段"
            )
            previous_hash = "0" * 64
            for event in events:
                event["previous_event_hash"] = previous_hash
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )

            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            event_entry = next(
                entry for entry in manifest["files"]
                if entry["path"] == "ticket/events.jsonl"
            )
            event_entry["sha256"] = sha256_file(events_path)
            event_entry["size"] = events_path.stat().st_size
            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            self.assertEqual(verify_pack(dest), [])

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["verify-pack", str(dest)])
            self.assertEqual(exit_code, 0, stdout.getvalue() + stderr.getvalue())
            self.assertIn("证据包校验通过", stdout.getvalue())

            standalone = self._run_verifier(dest, cwd=ws)
            self.assertEqual(
                standalone.returncode, 0, standalone.stdout + standalone.stderr,
            )
            self.assertIn("校验通过", standalone.stdout)

    def test_内置和独立校验器拒绝证据包路径越界(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from hashlib import sha256
        from io import StringIO

        from icode.cli import main
        from icode.pack_verify import pack_digest, sha256_file

        outside_marker = "external evidence must not be read"

        def read_json(path: Path) -> dict:
            return json.loads(path.read_text(encoding="utf-8"))

        def write_json(path: Path, value: object) -> None:
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        def refresh_manifest(pack: Path, changed_member: str) -> None:
            manifest_path = pack / "manifest.json"
            manifest = read_json(manifest_path)
            member = pack / changed_member
            entry = next(item for item in manifest["files"] if item["path"] == changed_member)
            entry["sha256"] = sha256_file(member)
            entry["size"] = member.stat().st_size
            manifest["pack_digest"] = pack_digest(manifest["files"])
            write_json(manifest_path, manifest)

        def add_manifest_traversal(pack: Path, outside: Path) -> None:
            outside.write_text(outside_marker, encoding="utf-8")
            manifest = read_json(pack / "manifest.json")
            manifest["files"].append({
                "path": "../outside.txt",
                "sha256": sha256(outside.read_bytes()).hexdigest(),
                "size": outside.stat().st_size,
            })
            manifest["pack_digest"] = pack_digest(manifest["files"])
            write_json(pack / "manifest.json", manifest)

        def add_windows_separator_traversal(pack: Path, outside: Path) -> None:
            outside.write_text(outside_marker, encoding="utf-8")
            manifest = read_json(pack / "manifest.json")
            manifest["files"].append({
                "path": r"..\outside.txt",
                "sha256": sha256(outside.read_bytes()).hexdigest(),
                "size": outside.stat().st_size,
            })
            manifest["pack_digest"] = pack_digest(manifest["files"])
            write_json(pack / "manifest.json", manifest)

        def add_absolute_manifest_path(pack: Path, outside: Path, relative: str) -> None:
            manifest = read_json(pack / "manifest.json")
            manifest["files"].append({"path": relative, "sha256": "0" * 64, "size": 0})
            manifest["pack_digest"] = pack_digest(manifest["files"])
            write_json(pack / "manifest.json", manifest)

        def move_artifact_snapshot_outside(pack: Path, outside: Path) -> None:
            index_path = pack / "artifacts.json"
            index = read_json(index_path)
            item = index["artifacts"][0]
            snapshot = pack / item["snapshot"]
            outside.write_bytes(snapshot.read_bytes())
            item["snapshot"] = "../outside.txt"
            write_json(index_path, index)
            refresh_manifest(pack, "artifacts.json")

        cases = (
            ("manifest traversal", add_manifest_traversal),
            ("Windows separator traversal", add_windows_separator_traversal),
            ("POSIX absolute", lambda pack, outside: add_absolute_manifest_path(
                pack, outside, "/outside.txt",
            )),
            ("Windows drive absolute", lambda pack, outside: add_absolute_manifest_path(
                pack, outside, "C:/outside.txt",
            )),
            ("UNC absolute", lambda pack, outside: add_absolute_manifest_path(
                pack, outside, "//server/share/outside.txt",
            )),
            ("artifact snapshot traversal", move_artifact_snapshot_outside),
        )
        for name, mutate in cases:
            with self.subTest(path=name), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                pack = ws / "pack"
                report = build_evidence_pack(
                    out_dir, dest=pack, gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())
                outside = ws / "outside.txt"
                mutate(pack, outside)

                problems = verify_pack(pack)
                rendered = "\n".join(problems)
                self.assertTrue(any("包内路径无效" in problem for problem in problems), problems)
                self.assertNotIn(outside_marker, rendered)

                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["verify-pack", str(pack)])
                self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
                self.assertIn("证据包校验失败", stdout.getvalue())
                self.assertIn("包内路径无效", stdout.getvalue())
                self.assertNotIn(outside_marker, stdout.getvalue() + stderr.getvalue())
                self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())

                standalone = self._run_verifier(pack, cwd=ws)
                self.assertEqual(
                    standalone.returncode, 1, standalone.stdout + standalone.stderr,
                )
                self.assertIn("包内路径无效", standalone.stdout)
                self.assertNotIn(outside_marker, standalone.stdout + standalone.stderr)
                self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

    def test_内置和独立校验器不跟随未登记的外部链接目录(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            pack = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=pack, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())
            outside = ws / "outside"
            outside.mkdir()
            (outside / "private-marker.txt").write_text(
                "external directory marker", encoding="utf-8",
            )
            link = pack / "unlisted-link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"当前平台不能创建目录符号链接：{type(exc).__name__}")

            problems = verify_pack(pack)
            rendered = "\n".join(problems)
            self.assertTrue(any("不允许的链接" in problem for problem in problems), problems)
            self.assertNotIn("external directory marker", rendered)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["verify-pack", str(pack)])
            self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
            self.assertIn("不允许的链接", stdout.getvalue())
            self.assertNotIn("external directory marker", stdout.getvalue() + stderr.getvalue())
            self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())

            standalone = self._run_verifier(pack, cwd=ws)
            self.assertEqual(
                standalone.returncode, 1, standalone.stdout + standalone.stderr,
            )
            self.assertIn("不允许的链接", standalone.stdout)
            self.assertNotIn("external directory marker", standalone.stdout + standalone.stderr)
            self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

    def test_内置和独立校验器拒绝固定成员符号链接(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main

        for relative in ("manifest.json", "ticket/events.jsonl", "artifacts.json"):
            with self.subTest(member=relative), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                pack = ws / "pack"
                report = build_evidence_pack(
                    out_dir, dest=pack, gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())

                member = pack / relative
                outside = ws / "outside-member"
                outside.write_bytes(member.read_bytes())
                member.unlink()
                try:
                    member.symlink_to(outside)
                except (NotImplementedError, OSError) as exc:
                    self.skipTest(f"当前平台不能创建符号链接：{type(exc).__name__}")

                problems = verify_pack(pack)
                self.assertTrue(any("包内路径无效" in problem for problem in problems), problems)

                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main(["verify-pack", str(pack)])
                self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
                self.assertIn("包内路径无效", stdout.getvalue())
                self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())

                standalone = self._run_verifier(pack, cwd=ws)
                self.assertEqual(
                    standalone.returncode, 1, standalone.stdout + standalone.stderr,
                )
                self.assertIn("包内路径无效", standalone.stdout)
                self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

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
