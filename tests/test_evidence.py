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

    def _record_claim(self, out_dir: Path, *, ticket_id: str, statement: str) -> dict:
        from icode.control import ControlPlane

        result = ControlPlane(self.settings).run(
            "record-claim", "--dir", str(out_dir), "--kind", "fact",
            "--statement", statement, "--source", "evidence-pack regression",
            "--boundary", "claim/event mirror contract",
            "--evidence", "fp-claim-evidence-pack",
            "--request-id", f"evidence-pack-claim-{ticket_id}-{statement}",
            check=False,
        )
        self.assertTrue(result.ok, result.data)
        claim = result.data.get("claim")
        self.assertIsInstance(claim, dict)
        return claim

    def _record_skill_run(
        self, out_dir: Path, *, ticket_id: str, skill: str = "evidence-check",
        trigger: str = "evidence-pack mirror regression", occurrence: int = 1,
    ) -> dict:
        from icode.control import ControlPlane

        result = ControlPlane(self.settings).run(
            "record-skill-run", "--dir", str(out_dir),
            "--skill", skill, "--trigger", trigger,
            "--result", "success", "--adopted", "true",
            "--evidence-ref", f"fp-skill-run-{ticket_id}-{occurrence}",
            "--elapsed-ms", "12", "--estimated-tokens", "34",
            "--unique-finding", f"finding-{occurrence}",
            "--request-id", f"evidence-pack-skill-run-{ticket_id}-{occurrence}",
            check=False,
        )
        self.assertTrue(result.ok, result.data)
        run = result.data.get("run")
        self.assertIsInstance(run, dict)
        return run

    def _record_agent_spawn(
        self, out_dir: Path, *, ticket_id: str, scope: str = "evidence review",
        occurrence: int = 1,
    ) -> dict:
        from icode.control import ControlPlane

        result = ControlPlane(self.settings).run(
            "record-agent-spawn", "--dir", str(out_dir),
            "--task-scope", scope,
            "--expected-artifact", f"bounded finding {occurrence}",
            "--evidence-boundary", "ticket evidence only",
            "--join-condition", "one documented finding",
            "--backend", "test-backend", "--model", "test-model",
            "--capability", "text", "--capability", "reasoning",
            "--request-id", f"evidence-pack-agent-spawn-{ticket_id}-{occurrence}",
            check=False,
        )
        self.assertTrue(result.ok, result.data)
        spawn = result.data.get("spawn")
        self.assertIsInstance(spawn, dict)
        return spawn

    def _record_agent_result(
        self, out_dir: Path, *, ticket_id: str, spawn_id: str,
        occurrence: int = 1, result_name: str = "joined",
        adopted: str = "yes", error_class: str | None = None,
    ) -> dict:
        from icode.control import ControlPlane

        args = [
            "record-agent-result", "--dir", str(out_dir),
            "--spawn-id", spawn_id, "--result", result_name, "--adopted", adopted,
            "--adoption-reason", "bounded result accepted",
            "--evidence-ref", f"fp-agent-result-{ticket_id}-{occurrence}",
            "--summary", f"result summary {occurrence}",
        ]
        if error_class is not None:
            args.extend(["--error-class", error_class])
        args.extend([
            "--request-id", f"evidence-pack-agent-result-{ticket_id}-{occurrence}",
        ])
        result = ControlPlane(self.settings).run(*args, check=False)
        self.assertTrue(result.ok, result.data)
        spawn = result.data.get("spawn")
        self.assertIsInstance(spawn, dict)
        return spawn

    def _rewrite_event_chain(self, events_path: Path, events: list[dict]) -> None:
        from icode.pack_verify import GENESIS_HASH, canonical_event_hash

        previous_hash = GENESIS_HASH
        for event in events:
            event["previous_event_hash"] = previous_hash
            event["event_hash"] = canonical_event_hash(event)
            previous_hash = event["event_hash"]
        events_path.write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
            encoding="utf-8",
        )

    def _drop_metadata_hash_markers(self, events_path: Path) -> None:
        """把手改metadata的旧格式测试夹具明确建成 marker-free 事件链。"""
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for event in events:
            payload = event.get("payload")
            if isinstance(payload, dict):
                payload.pop("metadata_hash_after", None)
        self._rewrite_event_chain(events_path, events)

    def _append_rehashed_event(
        self, metadata_path: Path, events_path: Path, event_type: str,
        payload: dict, metadata_updates: dict,
    ) -> None:
        """Append a schema-valid synthetic event and bind its resulting metadata."""
        import uuid

        from icode.pack_verify import _metadata_content_hash, canonical_event_hash

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.update(metadata_updates)
        event_payload = dict(payload)
        event_payload["metadata_hash_after"] = _metadata_content_hash(metadata)
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        event = {
            "schema_version": 1,
            "event_id": str(uuid.uuid4()),
            "ticket_id": metadata["ticket_id"],
            "timestamp": "2026-10-05T00:00:00+00:00",
            "actor": "system",
            "event_type": event_type,
            "payload": event_payload,
            "previous_event_hash": events[-1]["event_hash"],
        }
        event["event_hash"] = canonical_event_hash(event)
        events.append(event)
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8",
        )
        events_path.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
            encoding="utf-8",
        )

    def _refresh_pack_member_hash(self, pack_dir: Path, relative_path: str) -> None:
        from icode.pack_verify import pack_digest, sha256_file

        member = pack_dir / relative_path
        manifest_path = pack_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = next(item for item in manifest["files"] if item["path"] == relative_path)
        entry["sha256"] = sha256_file(member)
        entry["size"] = member.stat().st_size
        manifest["pack_digest"] = pack_digest(manifest["files"])
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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

    def test_导出器接受交错Agent生命周期及合法未终结spawn(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            first = self._record_agent_spawn(
                out_dir, ticket_id=metadata["ticket_id"], occurrence=1,
            )
            second = self._record_agent_spawn(
                out_dir, ticket_id=metadata["ticket_id"], scope="independent check",
                occurrence=2,
            )
            completed_second = self._record_agent_result(
                out_dir, ticket_id=metadata["ticket_id"],
                spawn_id=second["spawn_id"], occurrence=2,
            )

            report = build_evidence_pack(
                out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())
            self.assertEqual(verify_pack(ws / "pack"), [])
            packed = json.loads(
                (ws / "pack" / "ticket" / "metadata.json").read_text(encoding="utf-8"),
            )
            spawns = packed["extensions"]["agent"]["spawns"]
            self.assertEqual([item["spawn_id"] for item in spawns], [
                first["spawn_id"], completed_second["spawn_id"],
            ])
            self.assertNotIn("result", spawns[0])
            self.assertEqual(spawns[1]["result"], "joined")

    def test_导出器接受Agent全部合法终态与采纳组合(self) -> None:
        valid_outcomes = (
            ("joined", "yes"), ("joined", "partial"), ("joined", "no"),
            ("timed_out", "no"), ("stopped", "no"), ("failed", "no"),
        )
        for index, (result_name, adopted) in enumerate(valid_outcomes, start=1):
            with self.subTest(result=result_name, adopted=adopted), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                metadata = json.loads(
                    (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
                )
                spawn = self._record_agent_spawn(
                    out_dir, ticket_id=metadata["ticket_id"], occurrence=index,
                )
                self._record_agent_result(
                    out_dir, ticket_id=metadata["ticket_id"],
                    spawn_id=spawn["spawn_id"], occurrence=index,
                    result_name=result_name, adopted=adopted,
                    error_class="backend_error" if result_name != "joined" else None,
                )
                report = build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())
                self.assertEqual(verify_pack(ws / "pack"), [])

    def test_导出器拒绝metadata_agent_lifecycle与事件分叉且保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self._record_agent_spawn(out_dir, ticket_id=metadata["ticket_id"])

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["extensions"]["agent"]["spawns"][0]["task_scope"] = "metadata-only"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8",
            )

            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_bytes(b"preserve previous evidence pack\n")
            with self.assertRaisesRegex(
                EvidenceError, "agent_spawned/agent_result",
            ):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                    clean=True,
                )
            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器拒绝agent事件改写缺失或倒序(self) -> None:
        from icode.evidence import EvidenceError

        for mode in ("event-only", "missing-result", "missing-spawn", "spawn-order"):
            with self.subTest(mode=mode), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                metadata = json.loads(
                    (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
                )
                first = self._record_agent_spawn(
                    out_dir, ticket_id=metadata["ticket_id"], occurrence=1,
                )
                if mode == "spawn-order":
                    self._record_agent_spawn(
                        out_dir, ticket_id=metadata["ticket_id"], scope="second",
                        occurrence=2,
                    )
                else:
                    self._record_agent_result(
                        out_dir, ticket_id=metadata["ticket_id"],
                        spawn_id=first["spawn_id"],
                    )

                events_path = out_dir / ".ico_events.jsonl"
                events = [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                spawn_indexes = [
                    index for index, event in enumerate(events)
                    if event.get("event_type") == "agent_spawned"
                ]
                result_indexes = [
                    index for index, event in enumerate(events)
                    if event.get("event_type") == "agent_result"
                ]
                if mode == "event-only":
                    events[spawn_indexes[0]]["payload"]["task_scope"] = "event-only"
                elif mode == "missing-result":
                    self.assertEqual(len(result_indexes), 1)
                    events.pop(result_indexes[0])
                elif mode == "missing-spawn":
                    events.pop(spawn_indexes[0])
                else:
                    self.assertEqual(len(spawn_indexes), 2)
                    left, right = spawn_indexes
                    events[left], events[right] = events[right], events[left]
                self._rewrite_event_chain(events_path, events)

                with self.assertRaisesRegex(
                    EvidenceError, "agent_spawned/agent_result",
                ):
                    build_evidence_pack(
                        out_dir, dest=ws / "pack",
                        gates_json=self.settings.gates_json,
                    )

    def test_导出器拒绝result早于spawn的非法Agent生命周期(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            spawn = self._record_agent_spawn(out_dir, ticket_id=metadata["ticket_id"])
            self._record_agent_result(
                out_dir, ticket_id=metadata["ticket_id"], spawn_id=spawn["spawn_id"],
            )
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            spawn_index = next(
                index for index, event in enumerate(events)
                if event.get("event_type") == "agent_spawned"
            )
            result_index = next(
                index for index, event in enumerate(events)
                if event.get("event_type") == "agent_result"
            )
            events[spawn_index], events[result_index] = events[result_index], events[spawn_index]
            self._rewrite_event_chain(events_path, events)

            with self.assertRaisesRegex(
                EvidenceError, "agent_spawned/agent_result",
            ):
                build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )

    def test_导出器拒绝重复终结Agent生命周期(self) -> None:
        import uuid

        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            spawn = self._record_agent_spawn(out_dir, ticket_id=metadata["ticket_id"])
            self._record_agent_result(
                out_dir, ticket_id=metadata["ticket_id"], spawn_id=spawn["spawn_id"],
            )
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            result_event = next(
                event for event in events
                if event.get("event_type") == "agent_result"
            )
            duplicate = json.loads(json.dumps(result_event))
            duplicate["event_id"] = str(uuid.uuid4())
            duplicate["request_id"] = "evidence-pack-agent-result-duplicate"
            events.append(duplicate)
            self._rewrite_event_chain(events_path, events)

            with self.assertRaisesRegex(
                EvidenceError, "agent_spawned/agent_result",
            ):
                build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )

    def test_Agent生命周期归约器遵守三个开放spawn边界(self) -> None:
        from icode.pack_verify import _AgentLifecycleMirror

        def spawn_record(index: int) -> dict:
            return {
                "spawn_id": f"spawn-{index}", "at": "2026-10-05T00:00:00Z",
                "task_scope": f"scope-{index}",
                "expected_artifact": f"artifact-{index}",
                "evidence_boundary": "ticket-only",
                "join_condition": "one finding", "backend": "test",
                "model": "test-model", "capabilities": ["text"],
            }

        three_records = [spawn_record(index) for index in range(3)]
        accepted = _AgentLifecycleMirror(three_records)
        for record in three_records:
            accepted.consume("agent_spawned", dict(record))
        self.assertTrue(accepted.finish())

        four_records = [spawn_record(index) for index in range(4)]
        rejected = _AgentLifecycleMirror(four_records)
        for record in four_records:
            rejected.consume("agent_spawned", dict(record))
        self.assertFalse(rejected.finish())

        duplicate_records = [spawn_record(1), spawn_record(1)]
        duplicate = _AgentLifecycleMirror(duplicate_records)
        for record in duplicate_records:
            duplicate.consume("agent_spawned", dict(record))
        self.assertFalse(duplicate.finish())

    def test_导出器拒绝畸形agent_spawns并兼容缺省或null路径(self) -> None:
        from icode.evidence import EvidenceError

        malformed_extensions = (
            "invalid", False, 0, {"agent": "invalid"}, {"agent": False},
            {"agent": 0}, {"agent": {"spawns": "invalid"}},
            {"agent": {"spawns": False}}, {"agent": {"spawns": 0}},
            {"agent": {"spawns": [None]}},
        )
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            self._drop_metadata_hash_markers(out_dir / ".ico_events.jsonl")
            original = json.loads(metadata_path.read_text(encoding="utf-8"))
            for index, extensions in enumerate(malformed_extensions):
                with self.subTest(extensions=extensions):
                    metadata = dict(original)
                    metadata["extensions"] = extensions
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    with self.assertRaises(EvidenceError):
                        build_evidence_pack(
                            out_dir, dest=ws / f"bad-pack-{index}",
                            gates_json=self.settings.gates_json,
                        )

            compatible_extensions = (
                "missing", None, {"agent": None}, {"agent": {}},
                {"agent": {"spawns": None}},
            )
            for index, extensions in enumerate(compatible_extensions):
                with self.subTest(extensions=extensions):
                    metadata = dict(original)
                    if extensions == "missing":
                        metadata.pop("extensions", None)
                    else:
                        metadata["extensions"] = extensions
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    report = build_evidence_pack(
                        out_dir, dest=ws / f"compatible-pack-{index}",
                        gates_json=self.settings.gates_json,
                    )
                    self.assertTrue(report.ok, report.render())

    def test_独立校验器拒绝重签包中Agent生命周期metadata分叉(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            self._record_agent_spawn(out_dir, ticket_id=metadata["ticket_id"])
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["extensions"]["agent"]["spawns"][0]["task_scope"] = (
                "resigned metadata-only mutation"
            )
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._refresh_pack_member_hash(dest, "ticket/metadata.json")

            problems = verify_pack(dest)
            self.assertTrue(
                any("agent_spawned/agent_result" in problem for problem in problems),
                problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn(
                "agent_spawned/agent_result", independent.stdout + independent.stderr,
            )

    def test_独立校验器拒绝畸形agent_spawns(self) -> None:
        with temp_workspace() as ws:
            _out_dir, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["extensions"] = {"agent": {"spawns": [None]}}
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._refresh_pack_member_hash(dest, "ticket/metadata.json")

            problems = verify_pack(dest)
            self.assertTrue(
                any("metadata.extensions.agent.spawns" in problem for problem in problems),
                problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn(
                "metadata.extensions.agent.spawns",
                independent.stdout + independent.stderr,
            )

    def test_导出器拒绝未镜像metadata直写且保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["requirement"] = "unrecorded metadata-only change"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8",
            )

            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_bytes(b"preserve previous evidence pack\n")
            with self.assertRaisesRegex(EvidenceError, "metadata_hash_after"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                    clean=True,
                )
            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器拒绝重算事件链后的metadata_hash_after分叉(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            hashed_events = [
                event for event in events
                if event.get("payload", {}).get("metadata_hash_after")
            ]
            self.assertTrue(hashed_events)
            hashed_events[-1]["payload"]["metadata_hash_after"] = "0" * 64
            self._rewrite_event_chain(events_path, events)

            with self.assertRaisesRegex(EvidenceError, "metadata_hash_after"):
                build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )

    def test_导出器兼容没有metadata_hash_after的旧事件链(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            for event in events:
                event.get("payload", {}).pop("metadata_hash_after", None)
            self._rewrite_event_chain(events_path, events)

            report = build_evidence_pack(
                out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())
            self.assertEqual(verify_pack(ws / "pack"), [])

    def test_独立校验器拒绝重签包中未镜像metadata直写(self) -> None:
        with temp_workspace() as ws:
            out_dir, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())

            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["requirement"] = "resigned metadata-only change"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._refresh_pack_member_hash(dest, "ticket/metadata.json")

            problems = verify_pack(dest)
            self.assertTrue(
                any("metadata_hash_after" in problem for problem in problems), problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn("metadata_hash_after", independent.stdout + independent.stderr)

    def test_导出器拒绝重签事件链中的非法状态迁移(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                "state_changed",
                {"from": "init_in_progress", "to": "completed",
                 "delivery_verdict": "verified"},
                {"status": "completed", "delivery_verdict": "verified"},
            )
            with self.assertRaisesRegex(EvidenceError, "state_changed"):
                build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )

    def test_导出器拒绝关闭阶段跳跃并保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                "close_phase", {"from": None, "to": "archived"},
                {"close_state": "archived"},
            )
            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_bytes(b"preserve previous evidence pack\n")
            with self.assertRaisesRegex(EvidenceError, "close_phase"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                    clean=True,
                )
            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器拒绝畸形状态机契约并保留旧包(self) -> None:
        from icode.contracts import ContractError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            gates = json.loads(self.settings.gates_json.read_text(encoding="utf-8"))
            gates["state_machine"]["close_phases"] = ["not-closed"]
            gates_json = ws / "gates.json"
            gates_json.write_text(json.dumps(gates), encoding="utf-8")
            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_bytes(b"preserve previous evidence pack\n")

            with self.assertRaisesRegex(ContractError, "state_machine"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=gates_json, clean=True,
                )

            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_独立校验器拒绝重签包中的畸形状态机快照(self) -> None:
        with temp_workspace() as ws:
            _out, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            contracts_path = dest / "contracts.json"
            contracts = json.loads(contracts_path.read_text(encoding="utf-8"))
            contracts["state_machine"]["close_phases"] = ["not-closed"]
            contracts_path.write_text(
                json.dumps(contracts, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._refresh_pack_member_hash(dest, "contracts.json")

            problems = verify_pack(dest)
            self.assertTrue(
                any("contracts.json state_machine" in item for item in problems),
                problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn("contracts.json state_machine", independent.stdout + independent.stderr)

    def test_导出器拒绝最终状态与metadata分叉(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                "state_changed",
                {"from": "init_in_progress", "to": "plan_done",
                 "delivery_verdict": None},
                {"requirement": "metadata.status intentionally not updated"},
            )
            with self.assertRaisesRegex(EvidenceError, "metadata.status"):
                build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )

    def test_无状态机契约快照时旧包兼容且明确降级(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                "state_changed",
                {"from": "init_in_progress", "to": "completed",
                 "delivery_verdict": "verified"},
                {"status": "completed", "delivery_verdict": "verified"},
            )
            report = build_evidence_pack(out_dir, dest=ws / "pack")

            self.assertTrue(report.ok, report.render())
            self.assertTrue(
                any("不声明已验证工单状态/关闭阶段语义" in item for item in report.warnings),
                report.warnings,
            )
            self.assertEqual(verify_pack(ws / "pack"), [])

    def test_导出器拒绝未完成关闭时重开(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                "ticket_reopened", {"from": "closed", "to": None},
                {"close_state": None},
            )
            with self.assertRaisesRegex(EvidenceError, "ticket_reopened"):
                build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )

    def test_状态镜像接受合法状态迁移和完整关闭后重开(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                "state_changed",
                {"from": "init_in_progress", "to": "plan_done",
                 "delivery_verdict": None},
                {"status": "plan_done"},
            )
            phases = [
                "close_planned", "archived", "roots_verified", "checkouts_removed",
                "branches_removed", "closed",
            ]
            previous = None
            for phase in phases:
                self._append_rehashed_event(
                    out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                    "close_phase", {"from": previous, "to": phase},
                    {"close_state": phase},
                )
                previous = phase
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                "ticket_reopened", {"from": "closed", "to": None},
                {"close_state": None},
            )
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", out_dir / ".ico_events.jsonl",
                "close_phase", {"from": None, "to": "close_planned"},
                {"close_state": "close_planned"},
            )
            report = build_evidence_pack(
                out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())
            self.assertEqual(verify_pack(ws / "pack"), [])

    def test_独立校验器拒绝重签包中的非法状态迁移(self) -> None:
        with temp_workspace() as ws:
            out_dir, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            self._append_rehashed_event(
                dest / "ticket" / "metadata.json",
                dest / "ticket" / "events.jsonl",
                "state_changed",
                {"from": "init_in_progress", "to": "completed",
                 "delivery_verdict": "verified"},
                {"status": "completed", "delivery_verdict": "verified"},
            )
            self._refresh_pack_member_hash(dest, "ticket/metadata.json")
            self._refresh_pack_member_hash(dest, "ticket/events.jsonl")

            problems = verify_pack(dest)
            self.assertTrue(any("state_changed" in item for item in problems), problems)
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn("state_changed", independent.stdout + independent.stderr)

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

    def test_导出器拒绝畸形verification_runs且保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for index, malformed_runs in enumerate(([None], "", False, 0)):
                with self.subTest(verification_runs=malformed_runs):
                    metadata["verification_runs"] = malformed_runs
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )

                    for clean in (True, False):
                        with self.subTest(clean=clean):
                            dest = ws / f"existing-pack-{index}-{clean}"
                            dest.mkdir()
                            marker = dest / "keep.txt"
                            marker.write_bytes(b"preserve previous evidence pack\n")

                            with self.assertRaises(EvidenceError):
                                build_evidence_pack(
                                    out_dir, dest=dest,
                                    gates_json=self.settings.gates_json,
                                    clean=clean,
                                )

                            self.assertEqual(
                                marker.read_bytes(),
                                b"preserve previous evidence pack\n",
                            )

    def test_导出器拒绝metadata_skill_run与事件分叉且保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self._record_skill_run(
                out_dir, ticket_id=metadata["ticket_id"],
            )

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["extensions"]["skills"]["runs"][0]["skill"] = "metadata-only"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8",
            )

            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_bytes(b"preserve previous evidence pack\n")
            with self.assertRaisesRegex(EvidenceError, "skill_run_recorded"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                    clean=True,
                )
            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器拒绝重算哈希后的skill_run事件分叉(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            self._record_skill_run(out_dir, ticket_id=metadata["ticket_id"])

            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            skill_events = [
                event for event in events
                if event.get("event_type") == "skill_run_recorded"
            ]
            self.assertEqual(len(skill_events), 1)
            skill_events[0]["payload"]["trigger"] = "event-only mutation"
            self._rewrite_event_chain(events_path, events)

            with self.assertRaisesRegex(EvidenceError, "skill_run_recorded"):
                build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )

    def test_导出器拒绝skill_run事件缺失或倒序(self) -> None:
        from icode.evidence import EvidenceError

        for mode in ("missing", "reordered"):
            with self.subTest(mode=mode), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                metadata = json.loads(
                    (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
                )
                for occurrence in (1, 2):
                    self._record_skill_run(
                        out_dir, ticket_id=metadata["ticket_id"],
                        skill=f"evidence-check-{occurrence}", occurrence=occurrence,
                    )

                events_path = out_dir / ".ico_events.jsonl"
                events = [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                skill_run_indexes = [
                    index for index, event in enumerate(events)
                    if event.get("event_type") == "skill_run_recorded"
                ]
                self.assertEqual(len(skill_run_indexes), 2)
                if mode == "missing":
                    events.pop(skill_run_indexes[0])
                else:
                    first, second = skill_run_indexes
                    events[first], events[second] = events[second], events[first]
                self._rewrite_event_chain(events_path, events)

                dest = ws / "existing-pack"
                dest.mkdir()
                marker = dest / "keep.txt"
                marker.write_bytes(b"preserve previous evidence pack\n")
                with self.assertRaisesRegex(EvidenceError, "skill_run_recorded"):
                    build_evidence_pack(
                        out_dir, dest=dest, gates_json=self.settings.gates_json,
                        clean=True,
                    )
                self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器拒绝畸形嵌套skill_runs且保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        malformed_extensions = (
            "invalid",
            False,
            0,
            {"skills": "invalid"},
            {"skills": False},
            {"skills": 0},
            {"skills": {"runs": "invalid"}},
            {"skills": {"runs": False}},
            {"skills": {"runs": 0}},
            {"skills": {"runs": [None]}},
        )
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for index, malformed in enumerate(malformed_extensions):
                with self.subTest(extensions=malformed):
                    metadata["extensions"] = malformed
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    dest = ws / f"existing-pack-{index}"
                    dest.mkdir()
                    marker = dest / "keep.txt"
                    marker.write_bytes(b"preserve previous evidence pack\n")
                    with self.assertRaises(EvidenceError):
                        build_evidence_pack(
                            out_dir, dest=dest,
                            gates_json=self.settings.gates_json, clean=True,
                        )
                    self.assertEqual(
                        marker.read_bytes(), b"preserve previous evidence pack\n",
                    )

    def test_导出器兼容缺省与null的skill_run扩展(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            self._drop_metadata_hash_markers(out_dir / ".ico_events.jsonl")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            compatible_extensions = (
                "missing", None, {"skills": None}, {"skills": {}},
                {"skills": {"runs": None}},
            )
            for index, extensions in enumerate(compatible_extensions):
                with self.subTest(extensions=extensions):
                    if extensions == "missing":
                        metadata.pop("extensions", None)
                    else:
                        metadata["extensions"] = extensions
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    report = build_evidence_pack(
                        out_dir, dest=ws / f"pack-{index}",
                        gates_json=self.settings.gates_json,
                    )
                    self.assertTrue(report.ok, report.render())

    def test_独立校验器拒绝重签包中skill_runs与事件不一致(self) -> None:
        from icode.pack_verify import pack_digest, sha256_file

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            self._record_skill_run(out_dir, ticket_id=metadata["ticket_id"])
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["extensions"]["skills"]["runs"][0]["trigger"] = (
                "resigned metadata-only mutation"
            )
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._refresh_pack_member_hash(dest, "ticket/metadata.json")

            problems = verify_pack(dest)
            self.assertTrue(
                any("skill_run_recorded" in problem for problem in problems), problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn("skill_run_recorded", independent.stdout + independent.stderr)

    def test_独立校验器拒绝畸形嵌套skill_runs(self) -> None:
        with temp_workspace() as ws:
            _out_dir, dest, report = self._build(ws, workspace=ws / "work")
            self.assertTrue(report.ok, report.render())
            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["extensions"] = {"skills": {"runs": [None]}}
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._refresh_pack_member_hash(dest, "ticket/metadata.json")

            problems = verify_pack(dest)
            self.assertTrue(
                any("metadata.extensions.skills.runs" in problem for problem in problems),
                problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn(
                "metadata.extensions.skills.runs",
                independent.stdout + independent.stderr,
            )

    def test_导出器拒绝metadata与verification事件不一致且保留旧包(self) -> None:
        from icode.control import ControlPlane
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            recorded = ControlPlane(self.settings).record_verification(
                out_dir, ticket_id=metadata["ticket_id"], kind="device_test",
                outcome="pass", evidence="fp-verification-run-1",
                baseline="diff-verification-run-1", layer="unit",
                scenario="evidence-pack-consistency",
            )
            self.assertTrue(recorded.ok, recorded.data)

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["verification_runs"][0]["evidence"] = "metadata-only-change"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8",
            )

            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_bytes(b"preserve previous evidence pack\n")
            with self.assertRaisesRegex(EvidenceError, "verification_recorded"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json, clean=True,
                )
            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器拒绝已重算哈希的verification事件分叉(self) -> None:
        from icode.control import ControlPlane
        from icode.evidence import EvidenceError
        from icode.pack_verify import GENESIS_HASH, canonical_event_hash

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            recorded = ControlPlane(self.settings).record_verification(
                out_dir, ticket_id=metadata["ticket_id"], kind="device_test",
                outcome="pass", evidence="fp-verification-run-2",
                baseline="diff-verification-run-2", layer="unit",
                scenario="evidence-pack-consistency",
            )
            self.assertTrue(recorded.ok, recorded.data)

            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            verification_events = [
                event for event in events
                if event.get("event_type") == "verification_recorded"
            ]
            self.assertEqual(len(verification_events), 1)
            verification_events[0]["payload"]["evidence"] = "event-only-change"
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
            marker.write_bytes(b"preserve previous evidence pack\n")
            with self.assertRaisesRegex(EvidenceError, "verification_recorded"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json, clean=True,
                )
            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器区分verification值的JSON类型(self) -> None:
        from icode.control import ControlPlane
        from icode.evidence import EvidenceError
        from icode.pack_verify import GENESIS_HASH, canonical_event_hash

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            recorded = ControlPlane(self.settings).record_verification(
                out_dir, ticket_id=metadata["ticket_id"], kind="device_test",
                outcome="pass", evidence="fp-verification-run-json-type",
                baseline="diff-verification-run-json-type", layer="unit",
                scenario="evidence-pack-consistency",
            )
            self.assertTrue(recorded.ok, recorded.data)

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["verification_runs"][0]["outcome"] = 1
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8",
            )
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            verification_events = [
                event for event in events
                if event.get("event_type") == "verification_recorded"
            ]
            self.assertEqual(len(verification_events), 1)
            verification_events[0]["payload"]["outcome"] = True
            previous_hash = GENESIS_HASH
            for event in events:
                event["previous_event_hash"] = previous_hash
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(EvidenceError, "verification_recorded"):
                build_evidence_pack(
                    out_dir, dest=ws / "pack", gates_json=self.settings.gates_json,
                )

    def test_导出器拒绝verification事件缺失或顺序不一致(self) -> None:
        from icode.control import ControlPlane
        from icode.evidence import EvidenceError
        from icode.pack_verify import GENESIS_HASH, canonical_event_hash

        for mode in ("missing", "reordered"):
            with self.subTest(mode=mode), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                metadata = json.loads(
                    (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
                )
                control = ControlPlane(self.settings)
                for index in (1, 2):
                    recorded = control.record_verification(
                        out_dir, ticket_id=metadata["ticket_id"], kind="device_test",
                        outcome="pass", evidence=f"fp-verification-run-{mode}-{index}",
                        baseline=f"diff-verification-run-{mode}-{index}", layer="unit",
                        scenario="evidence-pack-consistency",
                    )
                    self.assertTrue(recorded.ok, recorded.data)

                events_path = out_dir / ".ico_events.jsonl"
                events = [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                verification_indexes = [
                    index for index, event in enumerate(events)
                    if event.get("event_type") == "verification_recorded"
                ]
                self.assertEqual(len(verification_indexes), 2)
                if mode == "missing":
                    events.pop(verification_indexes[0])
                else:
                    first, second = verification_indexes
                    events[first], events[second] = events[second], events[first]
                previous_hash = GENESIS_HASH
                for event in events:
                    event["previous_event_hash"] = previous_hash
                    event["event_hash"] = canonical_event_hash(event)
                    previous_hash = event["event_hash"]
                events_path.write_text(
                    "\n".join(
                        json.dumps(event, ensure_ascii=False) for event in events
                    ) + "\n",
                    encoding="utf-8",
                )

                dest = ws / "existing-pack"
                dest.mkdir()
                marker = dest / "keep.txt"
                marker.write_bytes(b"preserve previous evidence pack\n")
                with self.assertRaisesRegex(EvidenceError, "verification_recorded"):
                    build_evidence_pack(
                        out_dir, dest=dest, gates_json=self.settings.gates_json,
                        clean=True,
                    )
                self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_独立校验器拒绝摘要自洽但metadata与事件不一致(self) -> None:
        from icode.control import ControlPlane
        from icode.pack_verify import pack_digest, sha256_file

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            recorded = ControlPlane(self.settings).record_verification(
                out_dir, ticket_id=metadata["ticket_id"], kind="device_test",
                outcome="pass", evidence="fp-verification-run-3",
                baseline="diff-verification-run-3", layer="unit",
                scenario="evidence-pack-consistency",
            )
            self.assertTrue(recorded.ok, recorded.data)
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["verification_runs"][0]["evidence"] = "metadata-only-change"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            metadata_entry = next(
                item for item in manifest["files"]
                if item["path"] == "ticket/metadata.json"
            )
            metadata_entry["sha256"] = sha256_file(metadata_path)
            metadata_entry["size"] = metadata_path.stat().st_size
            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            problems = verify_pack(dest)
            self.assertTrue(
                any("verification_recorded" in problem for problem in problems),
                problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn(
                "verification_recorded", independent.stdout + independent.stderr,
            )

    def test_导出器拒绝metadata_claim与事件不一致且保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self._record_claim(
                out_dir, ticket_id=metadata["ticket_id"], statement="claim mirror original",
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["claims"][0]["statement"] = "metadata-only claim mutation"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8",
            )

            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_bytes(b"preserve previous evidence pack\n")
            with self.assertRaisesRegex(EvidenceError, "claim_recorded"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json, clean=True,
                )
            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器拒绝畸形claims且保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for index, malformed_claims in enumerate(([None], "", False, 0)):
                with self.subTest(claims=malformed_claims):
                    metadata["claims"] = malformed_claims
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    dest = ws / f"existing-pack-{index}"
                    dest.mkdir()
                    marker = dest / "keep.txt"
                    marker.write_bytes(b"preserve previous evidence pack\n")
                    with self.assertRaises(EvidenceError):
                        build_evidence_pack(
                            out_dir, dest=dest,
                            gates_json=self.settings.gates_json, clean=True,
                        )
                    self.assertEqual(
                        marker.read_bytes(), b"preserve previous evidence pack\n",
                    )

    def test_导出器拒绝重算哈希后的claim事件分叉(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            self._record_claim(
                out_dir, ticket_id=metadata["ticket_id"], statement="claim event original",
            )
            events_path = out_dir / ".ico_events.jsonl"
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            claim_events = [
                event for event in events if event.get("event_type") == "claim_recorded"
            ]
            self.assertEqual(len(claim_events), 1)
            claim_events[0]["payload"]["statement"] = "event-only claim mutation"
            self._rewrite_event_chain(events_path, events)

            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_bytes(b"preserve previous evidence pack\n")
            with self.assertRaisesRegex(EvidenceError, "claim_recorded"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json, clean=True,
                )
            self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_导出器拒绝claim事件缺失或顺序不一致(self) -> None:
        from icode.evidence import EvidenceError

        for mode in ("missing", "reordered"):
            with self.subTest(mode=mode), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                metadata = json.loads(
                    (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
                )
                for index in (1, 2):
                    self._record_claim(
                        out_dir,
                        ticket_id=metadata["ticket_id"],
                        statement=f"claim mirror {mode} {index}",
                    )
                events_path = out_dir / ".ico_events.jsonl"
                events = [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                claim_indexes = [
                    index for index, event in enumerate(events)
                    if event.get("event_type") == "claim_recorded"
                ]
                self.assertEqual(len(claim_indexes), 2)
                if mode == "missing":
                    events.pop(claim_indexes[0])
                else:
                    first, second = claim_indexes
                    events[first], events[second] = events[second], events[first]
                self._rewrite_event_chain(events_path, events)

                dest = ws / "existing-pack"
                dest.mkdir()
                marker = dest / "keep.txt"
                marker.write_bytes(b"preserve previous evidence pack\n")
                with self.assertRaisesRegex(EvidenceError, "claim_recorded"):
                    build_evidence_pack(
                        out_dir, dest=dest, gates_json=self.settings.gates_json,
                        clean=True,
                    )
                self.assertEqual(marker.read_bytes(), b"preserve previous evidence pack\n")

    def test_独立校验器拒绝摘要自洽但claims与事件不一致(self) -> None:
        from icode.pack_verify import pack_digest, sha256_file

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            metadata = json.loads(
                (out_dir / ".ico_metadata.json").read_text(encoding="utf-8"),
            )
            self._record_claim(
                out_dir, ticket_id=metadata["ticket_id"], statement="claim for verifier",
            )
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["claims"][0]["statement"] = "metadata-only signed claim mutation"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            metadata_entry = next(
                item for item in manifest["files"]
                if item["path"] == "ticket/metadata.json"
            )
            metadata_entry["sha256"] = sha256_file(metadata_path)
            metadata_entry["size"] = metadata_path.stat().st_size
            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            problems = verify_pack(dest)
            self.assertTrue(
                any("claim_recorded" in problem for problem in problems), problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn("claim_recorded", independent.stdout + independent.stderr)

    def test_独立校验器拒绝metadata中的畸形claims(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["claims"] = [None]
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._refresh_pack_member_hash(dest, "ticket/metadata.json")

            problems = verify_pack(dest)
            self.assertTrue(
                any("metadata.claims" in problem for problem in problems), problems,
            )
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            independent = subprocess.run(
                [sys.executable, str(dest / "verify.py"), str(dest)],
                cwd=str(ws), env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30, shell=False,
            )
            self.assertNotEqual(
                independent.returncode, 0, independent.stdout + independent.stderr,
            )
            self.assertIn("metadata.claims", independent.stdout + independent.stderr)

    def test_导出器遇到无效契约文件时保留旧包(self) -> None:
        from icode.contracts import ContractError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            gates_json = ws / "gates.json"
            gates_json.write_text("{", encoding="utf-8")
            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_text("preserve previous evidence pack\n", encoding="utf-8")

            with self.assertRaises(ContractError):
                build_evidence_pack(out_dir, dest=dest, gates_json=gates_json)

            self.assertTrue(marker.is_file(), "无效契约不得先删除旧证据包")
            self.assertEqual(
                marker.read_text(encoding="utf-8"), "preserve previous evidence pack\n",
            )

    def test_evidence畸形gates_json返回用户错误且保留旧包(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import patch

        from icode.cli import main

        deep_json = (
            b'{"execution_model":{"step_contracts":{"plan":{"required_checks":'
            + b"[" * 1200 + b"0" + b"]" * 1200 + b"}}}}"
        )
        oversized_integer = (
            b'{"schema_version":' + b"9" * 5000 + b',"execution_model":{}}'
        )
        cases = (
            ("invalid-utf8", b"\xff", "不是有效 UTF-8"),
            ("invalid-json", b"{", "不是合法 JSON"),
            ("non-object-root", b"[]", "结构无效"),
            (
                "invalid-step-contracts",
                b'{"execution_model":{"step_contracts":7}}',
                "结构无效",
            ),
            (
                "invalid-inputs",
                b'{"execution_model":{"step_contracts":{"plan":{"inputs":7}}}}',
                "结构无效",
            ),
            ("deeply-nested", deep_json, "嵌套深度超过安全上限"),
            ("oversized-integer", oversized_integer, "超出解析限制"),
        )

        for name, contents, expected_error in cases:
            with self.subTest(gates_json=name), temp_workspace() as ws:
                ticket = make_finished_plan_ticket(self.settings, ws / "work")
                gates_json = ws / "gates.json"
                gates_json.write_bytes(contents)
                pack_path = ws / "pack"
                pack_path.mkdir()
                marker = pack_path / "keep.txt"
                marker.write_bytes(b"keep existing evidence pack")
                stdout = StringIO()
                stderr = StringIO()

                with (
                    patch(
                        "icode.cli.load_settings",
                        return_value=SimpleNamespace(gates_json=gates_json),
                    ),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    try:
                        exit_code = main([
                            "evidence", "--ticket", str(ticket), "--dest", str(pack_path),
                        ])
                    except Exception as exc:  # noqa: BLE001 - assert CLI contains input failures
                        self.fail(
                            f"{name}: CLI leaked {type(exc).__name__}: {exc}; "
                            f"stderr={stderr.getvalue()!r}"
                        )

                self.assertEqual(
                    exit_code, 2,
                    f"{name}: stdout={stdout.getvalue()!r}, stderr={stderr.getvalue()!r}",
                )
                self.assertIn(expected_error, stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())
                self.assertEqual(marker.read_bytes(), b"keep existing evidence pack")
                self.assertEqual(list(pack_path.iterdir()), [marker])

    def test_evidence契约JSON在解析前强制结构标点预算(self) -> None:
        from unittest.mock import patch

        import json

        from icode.contracts import ContractError
        from icode.evidence import _contract_snapshot

        with temp_workspace() as ws:
            gates_json = ws / "gates.json"
            gates_json.write_text(
                '{"execution_model":{"step_contracts":{"plan":'
                '{"required_checks":["{}[],:\\\"quoted"]}}}}',
                encoding="utf-8",
            )

            # The JSON has 14 structural punctuation characters; punctuation in
            # the escaped string value must not consume the budget.
            with patch("icode.pack_verify._MAX_JSON_STRUCTURAL_TOKENS", 14):
                self.assertEqual(
                    _contract_snapshot(gates_json, {"plan"})["steps"]["plan"]
                    ["required_checks"],
                    ["{}[],:\"quoted"],
                )

            with (
                patch("icode.pack_verify._MAX_JSON_STRUCTURAL_TOKENS", 13),
                patch("icode.evidence.json.loads", wraps=json.loads) as json_loads,
            ):
                with self.assertRaisesRegex(ContractError, "结构标点超过安全上限"):
                    _contract_snapshot(gates_json, {"plan"})
                json_loads.assert_not_called()

    def test_evidence契约JSON嵌套深度边界在解析前执行(self) -> None:
        from unittest.mock import patch

        import json

        from icode.contracts import ContractError
        from icode.evidence import _contract_snapshot

        with temp_workspace() as ws:
            gates_json = ws / "gates.json"
            for depth, allowed in ((127, True), (128, False)):
                with self.subTest(total_depth=depth + 1):
                    extension = b"[" * depth + b"0" + b"]" * depth
                    gates_json.write_bytes(
                        b'{"execution_model":{"step_contracts":{"plan":{}}},'
                        b'"extension":' + extension + b"}"
                    )
                    if allowed:
                        snapshot = _contract_snapshot(gates_json, {"plan"})
                        self.assertIn("plan", snapshot["steps"])
                        continue

                    with patch(
                        "icode.evidence.json.loads", wraps=json.loads,
                    ) as json_loads:
                        with self.assertRaisesRegex(ContractError, "嵌套深度超过安全上限"):
                            _contract_snapshot(gates_json, {"plan"})
                        json_loads.assert_not_called()

    def test_evidence拒绝超结构预算gates_json且保留旧包(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import patch

        from icode.cli import main

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            gates_json = ws / "gates.json"
            gates_json.write_bytes(
                b'{"execution_model":{"step_contracts":{"plan":{}}},'
                b'"extension":[' + b"0," * 500_000 + b"0]}"
            )
            pack_path = ws / "pack"
            pack_path.mkdir()
            marker = pack_path / "keep.txt"
            marker.write_bytes(b"keep existing evidence pack")
            stdout = StringIO()
            stderr = StringIO()

            with (
                patch(
                    "icode.cli.load_settings",
                    return_value=SimpleNamespace(gates_json=gates_json),
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main([
                    "evidence", "--ticket", str(ticket), "--dest", str(pack_path),
                ])

            self.assertEqual(
                exit_code, 2,
                f"stdout={stdout.getvalue()!r}, stderr={stderr.getvalue()!r}",
            )
            self.assertIn("结构标点超过安全上限", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertEqual(marker.read_bytes(), b"keep existing evidence pack")
            self.assertEqual(list(pack_path.iterdir()), [marker])

    def test_导出器限制contracts快照UTF8输出字节并保留旧包(self) -> None:
        from unittest.mock import patch

        from icode.evidence import EvidenceError, _contract_snapshot

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            gates_json = ws / "gates.json"
            gates_json.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "execution_model": {
                            "step_contracts": {
                                "plan": {
                                    "required_checks": ["确认多语言契约"] * 64,
                                    "extension_number": float("nan"),
                                },
                                "unselected": {"extension_text": "未选步骤"},
                            },
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            expected_text = json.dumps(
                _contract_snapshot(gates_json, {"plan"}),
                ensure_ascii=False,
                indent=2,
            ) + "\n"
            output_bytes = len(expected_text.encode("utf-8"))
            self.assertGreater(output_bytes, gates_json.stat().st_size)

            for clean in (True, False):
                with self.subTest(clean=clean):
                    dest = ws / f"existing-{clean}"
                    dest.mkdir()
                    marker = dest / "keep.txt"
                    marker.write_bytes(b"preserve old output\n")

                    with patch(
                        "icode.evidence._MAX_EVIDENCE_CONTRACTS_JSON_BYTES",
                        output_bytes - 1,
                    ):
                        with self.assertRaisesRegex(EvidenceError, "契约快照输出超过安全上限"):
                            build_evidence_pack(
                                out_dir,
                                dest=dest,
                                gates_json=gates_json,
                                clean=clean,
                            )

                    self.assertEqual(marker.read_bytes(), b"preserve old output\n")
                    self.assertEqual([path.name for path in dest.iterdir()], ["keep.txt"])

    def test_导出器contracts快照恰好达到输出上限仍保持JSON兼容(self) -> None:
        from unittest.mock import patch

        from icode.evidence import _contract_snapshot

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            gates_json = ws / "gates.json"
            gates_json.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "execution_model": {
                            "step_contracts": {
                                "plan": {
                                    "required_checks": ["确认多语言契约"] * 64,
                                    "extension_number": float("nan"),
                                },
                                "unselected": {"extension_text": "未选步骤"},
                            },
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            expected_text = json.dumps(
                _contract_snapshot(gates_json, {"plan"}),
                ensure_ascii=False,
                indent=2,
            ) + "\n"
            output_bytes = len(expected_text.encode("utf-8"))
            dest = ws / "pack"

            with patch(
                "icode.evidence._MAX_EVIDENCE_CONTRACTS_JSON_BYTES",
                output_bytes,
            ):
                report = build_evidence_pack(out_dir, dest=dest, gates_json=gates_json)

            self.assertTrue(report.ok, report.render())
            self.assertEqual((dest / "contracts.json").read_text(encoding="utf-8"), expected_text)
            self.assertIn("NaN", expected_text)
            self.assertNotIn("unselected", expected_text)
            self.assertEqual(verify_pack(dest), [])

    def test_导出器拒绝与工单源目录重叠的目标且不改动源(self) -> None:
        from icode.evidence import EvidenceError

        cases = ("same", "ancestor", "descendant", "dotdot")
        for case in cases:
            for clean in (True, False):
                with self.subTest(destination=case, clean=clean), temp_workspace() as ws:
                    out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                    before_entries = sorted(
                        path.relative_to(out_dir).as_posix()
                        for path in out_dir.rglob("*")
                    )
                    before_files = {
                        path.relative_to(out_dir).as_posix(): path.read_bytes()
                        for path in out_dir.rglob("*") if path.is_file()
                    }

                    if case == "same":
                        dest = out_dir
                    elif case == "ancestor":
                        dest = ws
                    elif case == "descendant":
                        dest = out_dir / "nested-pack"
                    else:
                        dest = out_dir / ".." / out_dir.name

                    with self.assertRaisesRegex(EvidenceError, "目录不得与工单源目录重叠"):
                        build_evidence_pack(
                            out_dir,
                            dest=dest,
                            gates_json=self.settings.gates_json,
                            clean=clean,
                        )

                    self.assertTrue(out_dir.is_dir(), "拒绝重叠目标后工单源目录必须保留")
                    self.assertEqual(
                        sorted(path.relative_to(out_dir).as_posix() for path in out_dir.rglob("*")),
                        before_entries,
                        "拒绝重叠目标后源目录中不得新增证据包文件",
                    )
                    self.assertEqual(
                        {
                            path.relative_to(out_dir).as_posix(): path.read_bytes()
                            for path in out_dir.rglob("*") if path.is_file()
                        },
                        before_files,
                        "拒绝重叠目标后工单文件字节必须保持不变",
                    )

    def test_导出器拒绝符号链接别名目标且不改动工单源(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            before_events = (out_dir / ".ico_events.jsonl").read_bytes()
            before_metadata = (out_dir / ".ico_metadata.json").read_bytes()
            alias = ws / "ticket-alias"
            try:
                alias.symlink_to(out_dir, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"当前平台不允许创建目录符号链接：{type(exc).__name__}")

            with self.assertRaisesRegex(EvidenceError, "目录不得与工单源目录重叠"):
                build_evidence_pack(
                    out_dir, dest=alias, gates_json=self.settings.gates_json,
                )

            self.assertEqual((out_dir / ".ico_events.jsonl").read_bytes(), before_events)
            self.assertEqual((out_dir / ".ico_metadata.json").read_bytes(), before_metadata)

    def test_导出器拒绝覆盖契约输入目录且保留全部输入(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            input_dir = ws / "contract-input"
            input_dir.mkdir()
            gates_json = input_dir / "gates.json"
            gates_bytes = self.settings.gates_json.read_bytes()
            gates_json.write_bytes(gates_bytes)
            marker = input_dir / "keep.txt"
            marker.write_bytes(b"unrelated input must remain\n")

            with self.assertRaisesRegex(EvidenceError, "目录不得覆盖契约输入"):
                build_evidence_pack(out_dir, dest=input_dir, gates_json=gates_json)

            self.assertEqual(gates_json.read_bytes(), gates_bytes)
            self.assertEqual(marker.read_bytes(), b"unrelated input must remain\n")

    def test_导出器对gates_json按字节上限有界读取并在超限时保留旧包(self) -> None:
        from unittest.mock import patch

        from icode.contracts import ContractError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            gates_json = ws / "gates.json"
            gates_bytes = self.settings.gates_json.read_bytes()
            gates_json.write_bytes(gates_bytes)
            dest = ws / "pack"
            limit = len(gates_bytes)

            # Exactly-at-limit input remains compatible with the current contract.
            with patch("icode.evidence._MAX_EVIDENCE_GATES_JSON_BYTES", limit):
                report = build_evidence_pack(
                    out_dir, dest=dest, gates_json=gates_json,
                )
            self.assertTrue(report.ok, report.render())
            contracts_before = (dest / "contracts.json").read_bytes()

            gates_json.write_bytes(gates_bytes + b" ")
            for clean in (True, False):
                with self.subTest(clean=clean):
                    marker = dest / "keep-existing-pack.txt"
                    marker.write_text("preserve existing package\n", encoding="utf-8")
                    with patch(
                        "icode.evidence._MAX_EVIDENCE_GATES_JSON_BYTES",
                        limit,
                    ):
                        with self.assertRaisesRegex(ContractError, "安全输入上限"):
                            build_evidence_pack(
                                out_dir,
                                dest=dest,
                                gates_json=gates_json,
                                clean=clean,
                            )
                    self.assertEqual(
                        marker.read_text(encoding="utf-8"),
                        "preserve existing package\n",
                    )
                    self.assertEqual(
                        (dest / "contracts.json").read_bytes(), contracts_before,
                    )

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

    def test_导出器超限事件链在清理旧包前失败(self) -> None:
        from unittest.mock import patch

        import icode.evidence as evidence
        from icode.evidence import EvidenceError

        limits = (
            ("_MAX_EVENT_CHAIN_LINE_BYTES", 64, "单条物理行"),
            ("_MAX_EVENT_CHAIN_TOTAL_BYTES", 1, "总输入字节数"),
            ("_MAX_EVENT_CHAIN_EVENT_COUNT", 0, "事件条数"),
        )
        for constant, limit, message in limits:
            with self.subTest(limit=constant), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                dest = ws / "existing-pack"
                dest.mkdir()
                marker = dest / "keep.txt"
                marker.write_text("preserve this pack\n", encoding="utf-8")

                with patch.object(evidence, constant, limit, create=True):
                    with self.assertRaisesRegex(EvidenceError, message):
                        build_evidence_pack(
                            out_dir, dest=dest, gates_json=self.settings.gates_json,
                        )

                self.assertEqual(marker.read_text(encoding="utf-8"), "preserve this pack\n")

    def test_非状态控制事件的空对象payload仍兼容导出和校验(self) -> None:
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
            events[0]["payload"] = {"birth_kind": "plan"}
            previous_hash = GENESIS_HASH
            for event in events:
                event["previous_event_hash"] = previous_hash
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )
            self._append_rehashed_event(
                out_dir / ".ico_metadata.json", events_path,
                "external_note", {}, {},
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

    def test_导出器拒绝不在SKILL枚举中的事件类型并保留旧包(self) -> None:
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
            self.assertGreater(len(events), 1)
            self.assertEqual(events[0]["event_type"], "ticket_created")
            events[1]["event_type"] = "command_output"
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

            with self.assertRaisesRegex(EvidenceError, "event_type"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep existing evidence pack\n")

    def test_导出器拒绝不符合v1事件Schema的字段并保留旧包(self) -> None:
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
            events[1]["ticket_id"] = "different-source-ticket"
            events[1]["actor"] = "unregistered-actor"
            events[1]["unexpected_field"] = "still hash-consistent"
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

            with self.assertRaises(EvidenceError) as raised:
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )
            for field in ("actor", "additionalProperties", "ticket_id"):
                self.assertIn(field, str(raised.exception))

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep existing evidence pack\n")

    def test_导出器拒绝缺失的工单身份且清理旧包前失败(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            meta_path = out_dir / ".ico_metadata.json"
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            metadata.pop("ticket_id")
            meta_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_text("keep existing evidence pack\n", encoding="utf-8")

            with self.assertRaisesRegex(EvidenceError, "ticket_id"):
                build_evidence_pack(
                    out_dir, dest=dest, gates_json=self.settings.gates_json,
                )

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep existing evidence pack\n")

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
                    "event_id": f"00000000-0000-4000-8000-{index:012x}",
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
                "当前过程记录、metadata 与包内成员相互自洽",
                "不是",
                "应用层限制，不是内核级沙箱",
                "task 回执仅记录验证结果快照",
                "不包含完整会话事件回放",
                "不证明过程中不存在未记录副作用",
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
            self.assertEqual(receipts[0]["coverage"], {
                "record_scope": "verification_result_snapshot",
                "session_replay": "not_included",
                "unrecorded_side_effects": "not_proven",
            })
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
            self.assertEqual(
                packed["receipts"][0]["coverage"]["session_replay"],
                "not_included",
            )
            self.assertEqual(
                packed["receipts"][0]["coverage"]["unrecorded_side_effects"],
                "not_proven",
            )
            self.assertEqual(verify_pack(pack_path), [])

    def test_receipt_from输出超限时保留既有证据包(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.cli import _build_parser, cmd_evidence
        from icode.runner import VerificationOutputLimitError, _MAX_VERIFICATION_OUTPUT_BYTES

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            receipt_from = ws / "external-tests"
            receipt_from.mkdir()
            pack_path = ws / "existing-pack"
            pack_path.mkdir()
            marker = pack_path / "keep.txt"
            marker.write_text("preserve old pack\n", encoding="utf-8")
            args = _build_parser().parse_args([
                "evidence", "--ticket", str(ticket), "--dest", str(pack_path),
                "--receipt-from", str(receipt_from),
            ])
            stderr = StringIO()

            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                patch(
                    "icode.runner.run_unittest",
                    side_effect=VerificationOutputLimitError(1024),
                ) as run_unittest,
                patch("icode.evidence.build_evidence_pack") as build,
                redirect_stdout(StringIO()),
                redirect_stderr(stderr),
            ):
                exit_code = cmd_evidence(args)

            self.assertEqual(exit_code, 2)
            self.assertIn("未生成或覆盖", stderr.getvalue())
            run_unittest.assert_called_once_with(
                receipt_from.resolve(),
                output_limit_bytes=_MAX_VERIFICATION_OUTPUT_BYTES,
            )
            build.assert_not_called()
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve old pack\n")

    def test_receipt_from小输出生成完整回执并通过独立校验(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.cli import _build_parser, cmd_evidence

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            receipt_from = ws / "external-tests"
            receipt_from.mkdir()
            (receipt_from / "test_external.py").write_text(
                "import sys, unittest\n"
                "class ExternalTest(unittest.TestCase):\n"
                "    def test_output(self):\n"
                "        sys.stdout.write('external-stdout-marker\\n')\n"
                "        sys.stderr.write('external-stderr-marker\\n')\n",
                encoding="utf-8",
            )
            pack_path = ws / "pack"
            args = _build_parser().parse_args([
                "evidence", "--ticket", str(ticket), "--dest", str(pack_path),
                "--receipt-from", str(receipt_from),
            ])

            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                redirect_stdout(StringIO()),
            ):
                exit_code = cmd_evidence(args)

            self.assertEqual(exit_code, 0)
            receipts = json.loads(
                (pack_path / "verifications.json").read_text(encoding="utf-8"),
            )["receipts"]
            self.assertEqual(len(receipts), 1)
            receipt = receipts[0]
            self.assertEqual(receipt["exit_code"], 0)
            self.assertRegex(receipt["output_sha256"], r"^[0-9a-f]{64}$")
            self.assertIn("external-stdout-marker", receipt["output_tail"])
            self.assertIn("external-stderr-marker", receipt["output_tail"])
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

    def test_evidence拒绝超大回执文件且保留旧包(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.cli import main

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            receipt_path = ws / "oversized.json"
            receipt_path.write_bytes(
                b'{"value":"' + b"x" * (8 * 1024 * 1024) + b'"}'
            )
            pack_path = ws / "pack"
            pack_path.mkdir()
            marker = pack_path / "keep.txt"
            marker.write_bytes(b"keep existing evidence pack")
            stdout = StringIO()
            stderr = StringIO()

            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main([
                    "evidence", "--ticket", str(ticket), "--dest", str(pack_path),
                    "--receipt", str(receipt_path),
                ])

            self.assertEqual(exit_code, 2, stdout.getvalue() + stderr.getvalue())
            self.assertIn("回执文件超过单文件安全上限", stderr.getvalue())
            self.assertEqual(marker.read_bytes(), b"keep existing evidence pack")
            self.assertEqual(list(pack_path.iterdir()), [marker])

    def test_evidence拒绝累计回执输入超限且保留旧包(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        import icode.evidence as evidence_module
        from icode.cli import main

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            receipt_paths = []
            for index in range(3):
                path = ws / f"receipt-{index}.json"
                path.write_bytes(
                    b'{"value":"' + b"x" * (6 * 1024 * 1024) + b'"}'
                )
                receipt_paths.append(path)
            pack_path = ws / "pack"
            pack_path.mkdir()
            marker = pack_path / "keep.txt"
            marker.write_bytes(b"keep existing evidence pack")
            stdout = StringIO()
            stderr = StringIO()
            argv = ["evidence", "--ticket", str(ticket), "--dest", str(pack_path)]
            for path in receipt_paths:
                argv.extend(("--receipt", str(path)))
            read_limits = []
            original_reader = evidence_module.read_bounded_bytes

            def tracking_reader(path, *, max_bytes):
                read_limits.append(max_bytes)
                return original_reader(path, max_bytes=max_bytes)

            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                patch(
                    "icode.evidence.read_bounded_bytes",
                    side_effect=tracking_reader,
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(argv)

            self.assertEqual(exit_code, 2, stdout.getvalue() + stderr.getvalue())
            self.assertIn("回执文件累计输入超过安全上限", stderr.getvalue())
            self.assertEqual(
                read_limits,
                [
                    8 * 1024 * 1024,
                    8 * 1024 * 1024,
                    16 * 1024 * 1024
                    - sum(path.stat().st_size for path in receipt_paths[:2]),
                ],
            )
            self.assertEqual(marker.read_bytes(), b"keep existing evidence pack")
            self.assertEqual(list(pack_path.iterdir()), [marker])

    def test_evidence拒绝回执条数超限且保留旧包(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from icode.cli import main

        with temp_workspace() as ws:
            ticket = make_finished_plan_ticket(self.settings, ws / "work")
            receipt_path = ws / "too-many.json"
            receipt_path.write_text(json.dumps([{}] * 10_001), encoding="utf-8")
            pack_path = ws / "pack"
            pack_path.mkdir()
            marker = pack_path / "keep.txt"
            marker.write_bytes(b"keep existing evidence pack")
            stdout = StringIO()
            stderr = StringIO()

            with (
                patch("icode.cli.load_settings", return_value=self.settings),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main([
                    "evidence", "--ticket", str(ticket), "--dest", str(pack_path),
                    "--receipt", str(receipt_path),
                ])

            self.assertEqual(exit_code, 2, stdout.getvalue() + stderr.getvalue())
            self.assertIn("验证回执条数超过安全上限", stderr.getvalue())
            self.assertEqual(marker.read_bytes(), b"keep existing evidence pack")
            self.assertEqual(list(pack_path.iterdir()), [marker])

    def test_evidence拒绝生成超大verifications_json且保留旧包(self) -> None:
        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            pack_path = ws / "pack"
            pack_path.mkdir()
            marker = pack_path / "keep.txt"
            marker.write_bytes(b"keep existing evidence pack")

            with self.assertRaisesRegex(EvidenceError, "验证回执输出超过安全上限"):
                build_evidence_pack(
                    out_dir,
                    dest=pack_path,
                    gates_json=self.settings.gates_json,
                    verifications=[{"value": "x" * (8 * 1024 * 1024)}],
                )

            self.assertEqual(marker.read_bytes(), b"keep existing evidence pack")
            self.assertEqual(list(pack_path.iterdir()), [marker])

    def test_独立task回执序列化超限时不发布(self) -> None:
        from icode.evidence import EvidenceError, save_verification_receipt
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            destination = ws / "receipt.json"
            evidence = VerificationEvidence(
                step="x" * (8 * 1024 * 1024), attempt="1", exit_code=0,
            )

            with self.assertRaisesRegex(EvidenceError, "验证回执输出超过安全上限"):
                save_verification_receipt(evidence, destination)

            self.assertFalse(destination.exists())
            self.assertEqual(list(ws.iterdir()), [])

    def test_独立task回执在生成fingerprint前拒绝超大字段(self) -> None:
        from unittest.mock import patch

        from icode.evidence import EvidenceError, save_verification_receipt
        from icode.self_verify import VerificationEvidence

        with temp_workspace() as ws:
            destination = ws / "receipt.json"
            evidence = VerificationEvidence(
                step="x" * (8 * 1024 * 1024), attempt="1", exit_code=0,
            )

            with patch.object(
                VerificationEvidence,
                "to_receipt",
                wraps=evidence.to_receipt,
            ) as to_receipt:
                with self.assertRaisesRegex(EvidenceError, "验证回执输出超过安全上限"):
                    save_verification_receipt(evidence, destination)
                to_receipt.assert_not_called()

            self.assertFalse(destination.exists())
            self.assertEqual(list(ws.iterdir()), [])

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
        allowed = {
            "hashlib", "json", "math", "os", "pathlib", "re", "stat", "sys",
            "__future__",
        }
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

    def test_包级问题诊断限制样本但仍完整扫描(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main
        from icode.pack_verify import pack_digest

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            long_missing_path = "/".join(("p" * 180,) * 5)
            manifest["files"].append({
                "path": long_missing_path,
                "sha256": "0" * 64,
            })
            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            for index in range(80):
                (dest / f"unexpected-{index:03}.txt").write_text(
                    "unregistered\n", encoding="utf-8",
                )

            problems = verify_pack(dest)
            joined = "\n".join(problems)
            self.assertEqual(getattr(problems, "total_count", None), 81)
            self.assertEqual(getattr(problems, "sample_count", None), 32)
            self.assertEqual(len(problems), 33)
            self.assertIn("省略 49 条", joined)
            self.assertNotIn(long_missing_path, joined)
            self.assertLessEqual(max(map(len, problems)), 512)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["verify-pack", str(dest)])
            self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
            self.assertIn("问题 81 处", stdout.getvalue())
            self.assertIn("省略 49 条", stdout.getvalue())
            self.assertLess(len(stdout.getvalue()), 16 * 1024)

            standalone = self._run_verifier(dest, cwd=ws)
            self.assertEqual(
                standalone.returncode, 1, standalone.stdout + standalone.stderr,
            )
            self.assertIn("问题 81 处", standalone.stdout)
            self.assertIn("省略 49 条", standalone.stdout)

    def test_事件链坏记录洪泛时仍完整验证且诊断有界(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main
        from icode.pack_verify import pack_digest, sha256_file

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            events_path = dest / "ticket" / "events.jsonl"
            events = []
            repeated_id = "00000000-0000-4000-8000-000000000001"
            ticket_id = json.loads(
                events_path.read_text(encoding="utf-8").splitlines()[0]
            )["ticket_id"]
            for index in range(257):
                events.append({
                    "schema_version": 1,
                    "event_id": repeated_id if index < 256 else "x" * 4096,
                    "ticket_id": ticket_id,
                    "timestamp": "2026-10-01T00:00:00+00:00",
                    "actor": "system",
                    "event_type": "ticket_created" if index == 0 else "step_finished",
                    "payload": {},
                    "previous_event_hash": "e" * 64,
                    "event_hash": "f" * 64,
                })
            events_path.write_text(
                "\n".join(json.dumps(event, separators=(",", ":")) for event in events)
                + "\n",
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
            joined_problems = "\n".join(problems)
            self.assertLessEqual(len(problems), 34, joined_problems)
            self.assertIn("769 个链问题", joined_problems)
            self.assertIn("省略 737 条", joined_problems)
            self.assertIn("event_id_duplicate=255", joined_problems)
            self.assertIn("event_hash=257", joined_problems)
            self.assertIn("previous_event_hash=257", joined_problems)
            self.assertNotIn("x" * 4096, joined_problems)
            self.assertLess(max(map(len, problems)), 512)

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["verify-pack", str(dest)])
            self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
            self.assertIn("省略 737 条", stdout.getvalue())
            self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())
            self.assertLess(len(stdout.getvalue()), 16 * 1024)

            standalone = self._run_verifier(dest, cwd=ws)
            self.assertEqual(
                standalone.returncode, 1, standalone.stdout + standalone.stderr,
            )
            self.assertIn("省略 737 条", standalone.stdout)
            self.assertNotIn("x" * 4096, standalone.stdout + standalone.stderr)
            self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)
            self.assertLess(len(standalone.stdout), 16 * 1024)

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

    def test_所有Verifier拒绝哈希自洽但未知的事件类型(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main
        from icode.pack_verify import (
            ALLOWED_EVENT_TYPES,
            ALLOWED_EVENT_ACTORS,
            EVENT_HASH_PATTERN,
            EVENT_ID_PATTERN,
            EVENT_REQUIRED_FIELDS,
            EVENT_SCHEMA_FIELDS,
            EVENT_SCHEMA_VERSION,
            EVENT_TIMESTAMP_PATTERN,
            GENESIS_HASH,
            canonical_event_hash,
            pack_digest,
            sha256_file,
        )
        from icode.pack_verify import event_schema_issues

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
            self.assertGreater(len(events), 1)
            self.assertEqual(events[0]["event_type"], "ticket_created")
            non_ascii_timestamp = dict(events[0])
            non_ascii_timestamp["timestamp"] = "٢٠٢٦-١٠-٠١T٠٠:٠٠:٠٠"
            self.assertIn(
                "timestamp",
                event_schema_issues(
                    non_ascii_timestamp,
                    expected_ticket_id=events[0]["ticket_id"],
                ),
            )
            events[1]["event_type"] = "command_output"
            schema_path = REPO_ROOT / "vendor" / "icode-skill" / "schemas" / "ticket-event.schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ALLOWED_EVENT_TYPES,
                frozenset(schema["properties"]["event_type"]["enum"]),
            )
            self.assertEqual(
                ALLOWED_EVENT_ACTORS,
                frozenset(schema["properties"]["actor"]["enum"]),
            )
            self.assertEqual(
                EVENT_REQUIRED_FIELDS,
                frozenset(schema["required"]),
            )
            self.assertEqual(
                EVENT_SCHEMA_FIELDS,
                frozenset(schema["properties"]),
            )
            properties = schema["properties"]
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(EVENT_SCHEMA_VERSION, properties["schema_version"]["const"])
            self.assertEqual("string", properties["event_id"]["type"])
            self.assertEqual(EVENT_ID_PATTERN, properties["event_id"]["pattern"])
            self.assertEqual("string", properties["ticket_id"]["type"])
            self.assertEqual(1, properties["ticket_id"]["minLength"])
            self.assertEqual("string", properties["timestamp"]["type"])
            self.assertEqual(EVENT_TIMESTAMP_PATTERN, properties["timestamp"]["pattern"])
            self.assertEqual(
                EVENT_HASH_PATTERN,
                properties["previous_event_hash"]["pattern"],
            )
            self.assertEqual(
                EVENT_HASH_PATTERN,
                properties["event_hash"]["pattern"],
            )
            self.assertEqual("object", properties["payload"]["type"])
            self.assertEqual("string", properties["previous_event_hash"]["type"])
            self.assertEqual("string", properties["event_hash"]["type"])
            self.assertNotIn("request_id", schema["required"])
            self.assertEqual(
                ["string", "null"], properties["request_id"]["type"],
            )
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
                any("event_type" in problem for problem in problems),
                problems,
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["verify-pack", str(dest)])
            self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
            self.assertIn("event_type", stdout.getvalue())
            self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())

            standalone = self._run_verifier(dest, cwd=ws)
            self.assertEqual(standalone.returncode, 1, standalone.stdout + standalone.stderr)
            self.assertIn("event_type", standalone.stdout)
            self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

    def test_所有Verifier拒绝哈希自洽但不符合v1事件Schema的包(self) -> None:
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO

        from icode.cli import main
        from icode.pack_verify import (
            GENESIS_HASH,
            canonical_event_hash,
            pack_digest,
            sha256_file,
        )

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
            malformed = events[1]
            malformed["schema_version"] = 2
            malformed["event_id"] = "not-a-uuid-v4"
            malformed["ticket_id"] = "different-ticket"
            malformed["timestamp"] = "not-a-timestamp"
            malformed.pop("actor")
            malformed["request_id"] = []
            malformed["unexpected_field"] = "still hash-consistent"
            previous_hash = GENESIS_HASH
            for event in events:
                event["previous_event_hash"] = previous_hash
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
            events_path.write_text(
                "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )

            metadata_path = dest / "ticket" / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["ticket_id"] = "different-metadata-ticket"
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest["files"]:
                file_path = dest / entry["path"]
                entry["sha256"] = sha256_file(file_path)
                entry["size"] = file_path.stat().st_size
            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            problems = verify_pack(dest)
            self.assertTrue(problems, "schema-invalid but rehashed ticket event must be rejected")
            schema_problem = next(
                problem for problem in problems if "ticket-event schema" in problem
            )
            for field in (
                "actor", "additionalProperties", "event_id", "request_id",
                "schema_version", "ticket_id", "timestamp",
            ):
                self.assertIn(field, schema_problem)
            self.assertTrue(
                any("清单与工单 metadata 的 ticket_id 不一致" in problem for problem in problems),
                problems,
            )

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["verify-pack", str(dest)])
            self.assertEqual(exit_code, 1, stdout.getvalue() + stderr.getvalue())
            self.assertIn("ticket-event schema", stdout.getvalue())
            self.assertNotIn("Traceback", stdout.getvalue() + stderr.getvalue())

            standalone = self._run_verifier(dest, cwd=ws)
            self.assertEqual(standalone.returncode, 1, standalone.stdout + standalone.stderr)
            self.assertIn("ticket-event schema", standalone.stdout)
            self.assertNotIn("Traceback", standalone.stdout + standalone.stderr)

    def test_内置和独立Verifier接受Schema允许省略的request_id(self) -> None:
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
            events[1].pop("request_id")
            events[2]["request_id"] = "replay-request-id"
            events[2]["payload"]["future_payload_extension"] = {"accepted": True}
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

            self.assertEqual(verify_pack(dest), [])
            standalone = self._run_verifier(dest, cwd=ws)
            self.assertEqual(standalone.returncode, 0, standalone.stdout + standalone.stderr)

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
                        "schema_version": 1,
                        "event_id": f"00000000-0000-4000-8000-{index:012x}",
                        "ticket_id": "bounded-memory-ticket",
                        "timestamp": "2026-10-01T00:00:00+00:00",
                        "actor": "system",
                        "event_type": "ticket_created" if index == 0 else "step_finished",
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

    def test_event_chain对单条UTF8物理行字节数设置硬上限(self) -> None:
        from unittest.mock import patch

        from icode.pack_verify import _verify_event_chain, canonical_event_hash

        with temp_workspace() as ws:
            events_path = ws / "oversized-line.jsonl"
            event = {
                "schema_version": 1,
                "event_id": "00000000-0000-4000-8000-000000000001",
                "ticket_id": "bounded-line-ticket",
                "timestamp": "2026-10-01T00:00:00+00:00",
                "actor": "system",
                "event_type": "ticket_created",
                # ASCII 字符数低于阈值，但 UTF-8 字节数会超过阈值。
                "payload": {"padding": "界" * 160, "secret": "must-not-echo"},
                "previous_event_hash": "0" * 64,
            }
            event["event_hash"] = canonical_event_hash(event)
            events_path.write_text(
                json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )

            with patch(
                "icode.pack_verify._MAX_EVENT_CHAIN_LINE_BYTES", 700, create=True,
            ):
                artifact_facts, problems = _verify_event_chain(events_path)

            self.assertEqual(artifact_facts, {})
            self.assertEqual(len(problems), 1, problems)
            self.assertIn("单条物理行", problems[0])
            self.assertNotIn("must-not-echo", "\n".join(problems))

    def test_event_chain对总输入字节数设置硬上限(self) -> None:
        from unittest.mock import patch

        from icode.pack_verify import _verify_event_chain, canonical_event_hash

        with temp_workspace() as ws:
            events_path = ws / "oversized-total.jsonl"
            event = {
                "schema_version": 1,
                "event_id": "00000000-0000-4000-8000-000000000001",
                "ticket_id": "bounded-total-ticket",
                "timestamp": "2026-10-01T00:00:00+00:00",
                "actor": "system",
                "event_type": "ticket_created",
                "payload": {},
                "previous_event_hash": "0" * 64,
            }
            event["event_hash"] = canonical_event_hash(event)
            events_path.write_text(
                json.dumps(event, separators=(",", ":")) + "\n", encoding="utf-8",
            )

            with patch(
                "icode.pack_verify._MAX_EVENT_CHAIN_TOTAL_BYTES", 1, create=True,
            ):
                artifact_facts, problems = _verify_event_chain(events_path)

            self.assertEqual(artifact_facts, {})
            self.assertEqual(len(problems), 1, problems)
            self.assertIn("总输入字节数", problems[0])

    def test_event_chain对记录数设置硬上限并兼容CR物理分帧(self) -> None:
        from unittest.mock import patch

        from icode.pack_verify import _verify_event_chain, canonical_event_hash

        with temp_workspace() as ws:
            events_path = ws / "too-many-events.jsonl"
            previous_hash = "0" * 64
            lines = []
            for index, event_type in enumerate(("ticket_created", "step_finished")):
                event = {
                    "schema_version": 1,
                    "event_id": f"00000000-0000-4000-8000-{index + 1:012x}",
                    "ticket_id": "bounded-count-ticket",
                    "timestamp": "2026-10-01T00:00:00+00:00",
                    "actor": "system",
                    "event_type": event_type,
                    "payload": {"sequence": index},
                    "previous_event_hash": previous_hash,
                }
                event["event_hash"] = canonical_event_hash(event)
                previous_hash = event["event_hash"]
                lines.append(json.dumps(event, separators=(",", ":")))
            # RFC-compatible CR-only framing 也应继续按物理行处理。
            events_path.write_text("\r".join(lines) + "\r", encoding="utf-8")

            with patch(
                "icode.pack_verify._MAX_EVENT_CHAIN_EVENT_COUNT", 1, create=True,
            ):
                artifact_facts, problems = _verify_event_chain(events_path)

            self.assertEqual(artifact_facts, {})
            self.assertEqual(len(problems), 1, problems)
            self.assertIn("事件条数", problems[0])

    def test_verify_pack在哈希整个超限事件文件前拒绝(self) -> None:
        from unittest.mock import patch

        import icode.pack_verify as pack_verify

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())
            events_path = dest / "ticket" / "events.jsonl"

            with (
                patch.object(pack_verify, "_MAX_EVENT_CHAIN_TOTAL_BYTES", 1, create=True),
                patch.object(pack_verify, "sha256_file", wraps=pack_verify.sha256_file) as hasher,
            ):
                problems = verify_pack(dest)

            self.assertTrue(any("总输入字节数" in problem for problem in problems), problems)
            self.assertFalse(
                any(call.args and Path(call.args[0]) == events_path for call in hasher.call_args_list),
                "verify_pack 不应先对超限事件文件做完整 SHA-256 扫描",
            )

    def test_verify_pack拒绝重复登记事件路径(self) -> None:
        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=dest, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())

            manifest_path = dest / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            event_entry = next(
                item for item in manifest["files"]
                if item["path"] == "ticket/events.jsonl"
            )
            manifest["files"].append(dict(event_entry))
            from icode.pack_verify import pack_digest

            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            problems = verify_pack(dest)

            self.assertTrue(any("path 重复" in problem for problem in problems), problems)

    def test_event_chain校验仍拒绝重复event_id(self) -> None:
        from icode.pack_verify import _verify_event_chain, canonical_event_hash

        with temp_workspace() as ws:
            events_path = ws / "duplicate-ids.jsonl"
            previous_hash = "0" * 64
            lines: list[str] = []
            for index, event_type in enumerate(("ticket_created", "step_finished")):
                event = {
                    "schema_version": 1,
                    "event_id": "00000000-0000-4000-8000-000000000001",
                    "ticket_id": "duplicate-event-ticket",
                    "timestamp": "2026-10-01T00:00:00+00:00",
                    "actor": "system",
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
        from icode.pack_verify import (
            GENESIS_HASH,
            _metadata_content_hash,
            canonical_event_hash,
            pack_digest,
            sha256_file,
        )

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
                    ticket_id = chr(0x1F600)
                    manifest["ticket"]["ticket_id"] = ticket_id

                    metadata_path = dest / "ticket" / "metadata.json"
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    metadata["ticket_id"] = ticket_id
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=True, indent=2) + "\n",
                        encoding="utf-8",
                    )

                    events_path = dest / "ticket" / "events.jsonl"
                    events = [
                        json.loads(line)
                        for line in events_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    hashed_events = [
                        event for event in events
                        if isinstance(event.get("payload"), dict)
                        and event["payload"].get("metadata_hash_after")
                    ]
                    self.assertTrue(hashed_events)
                    hashed_events[-1]["payload"]["metadata_hash_after"] = (
                        _metadata_content_hash(metadata)
                    )
                    previous_hash = GENESIS_HASH
                    for event in events:
                        event["ticket_id"] = ticket_id
                        event["previous_event_hash"] = previous_hash
                        event["event_hash"] = canonical_event_hash(event)
                        previous_hash = event["event_hash"]
                    events_path.write_text(
                        "\n".join(
                            json.dumps(event, ensure_ascii=True) for event in events
                        ) + "\n",
                        encoding="utf-8",
                    )

                    for entry in manifest["files"]:
                        file_path = dest / entry["path"]
                        entry["sha256"] = sha256_file(file_path)
                        entry["size"] = file_path.stat().st_size
                    manifest["pack_digest"] = pack_digest(manifest["files"])
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

    def test_JSON结构预算只统计字符串外的JSON标点(self) -> None:
        from unittest.mock import patch

        from icode.pack_verify import loads_json_value

        text = '{"note":"{}[],:","items":[1]}'
        # 字符串中的括号/逗号/冒号不是结构标点；JSON 本身共有 7 个。
        with patch("icode.pack_verify._MAX_JSON_STRUCTURAL_TOKENS", 7):
            self.assertEqual(loads_json_value(text), {"note": "{}[],:", "items": [1]})
        with patch("icode.pack_verify._MAX_JSON_STRUCTURAL_TOKENS", 6):
            with self.assertRaisesRegex(ValueError, "JSON结构标点超过安全上限"):
                loads_json_value(text)

    def test_包内控制JSON超出字节预算时拒绝(self) -> None:
        from unittest.mock import patch

        limits = (
            ("manifest.json", "_MAX_MANIFEST_JSON_BYTES"),
            ("ticket/metadata.json", "_MAX_METADATA_JSON_BYTES"),
            ("artifacts.json", "_MAX_ARTIFACT_INDEX_JSON_BYTES"),
        )
        for relative, constant in limits:
            with self.subTest(member=relative), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                pack = ws / "pack"
                report = build_evidence_pack(
                    out_dir, dest=pack, gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())
                exact_limit = (pack / relative).stat().st_size
                with patch(f"icode.pack_verify.{constant}", exact_limit):
                    self.assertEqual(verify_pack(pack), [])
                with patch(f"icode.pack_verify.{constant}", exact_limit - 1):
                    problems = verify_pack(pack)
                self.assertTrue(
                    any("控制JSON超过输入字节上限" in problem for problem in problems),
                    problems,
                )

    def test_普通清单文件受单文件摘要上限约束(self) -> None:
        from unittest.mock import patch

        from icode.pack_verify import pack_digest, sha256_file

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            pack = ws / "pack"
            report = build_evidence_pack(out_dir, dest=pack, gates_json=None)
            self.assertTrue(report.ok, report.render())
            manifest_path = pack / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = manifest["files"]
            largest_existing = max((pack / entry["path"]).stat().st_size for entry in entries)
            target = next(entry for entry in entries if entry["path"] == "verifications.json")
            payload = b"x" * (largest_existing + 1)
            (pack / target["path"]).write_bytes(payload)
            target["size"] = len(payload)
            target["sha256"] = sha256_file(pack / target["path"])
            manifest["pack_digest"] = pack_digest(entries)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with patch(
                "icode.pack_verify._MAX_PACKAGE_FILE_BYTES", largest_existing, create=True,
            ):
                problems = verify_pack(pack)

            self.assertTrue(
                any("单文件安全上限" in problem for problem in problems), problems,
            )

            # Tighten only the copied independent verifier's test fixture limit;
            # its result must match the in-process verifier without PYTHONPATH.
            verifier_path = pack / "verify.py"
            verifier_source = verifier_path.read_bytes()
            limit_declaration = b"_MAX_PACKAGE_FILE_BYTES = 256 * 1024 * 1024"
            self.assertIn(limit_declaration, verifier_source)
            verifier_path.write_bytes(
                verifier_source.replace(
                    limit_declaration,
                    f"_MAX_PACKAGE_FILE_BYTES = {largest_existing}".encode("ascii"),
                ),
            )
            verifier_entry = next(entry for entry in entries if entry["path"] == "verify.py")
            verifier_entry["size"] = verifier_path.stat().st_size
            verifier_entry["sha256"] = sha256_file(verifier_path)
            manifest["pack_digest"] = pack_digest(entries)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            standalone = self._run_verifier(pack, cwd=ws)
            self.assertEqual(standalone.returncode, 1, standalone.stdout + standalone.stderr)
            self.assertIn("单文件安全上限", standalone.stdout)

    def test_包摘要累计读取预算包含正文二次哈希(self) -> None:
        from unittest.mock import patch

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            pack = ws / "pack"
            report = build_evidence_pack(out_dir, dest=pack, gates_json=None)
            self.assertTrue(report.ok, report.render())
            manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
            package_file_bytes = sum(
                (pack / entry["path"]).stat().st_size for entry in manifest["files"]
            )
            artifacts = json.loads((pack / "artifacts.json").read_text(encoding="utf-8"))
            body_bytes = sum(
                (pack / item["snapshot"]).stat().st_size
                for item in artifacts["artifacts"] if item["snapshot"]
            )

            # 文件清单哈希恰好耗尽限额后，正文绑定的第二次哈希必须被计入。
            with patch(
                "icode.pack_verify._MAX_PACKAGE_HASH_READ_BYTES",
                package_file_bytes,
                create=True,
            ):
                problems = verify_pack(pack)
            self.assertTrue(
                any("累计摘要读取超过安全上限" in problem for problem in problems),
                problems,
            )
            self.assertFalse(any("缺少正文快照" in problem for problem in problems), problems)

            with patch(
                "icode.pack_verify._MAX_PACKAGE_HASH_READ_BYTES",
                package_file_bytes + body_bytes,
                create=True,
            ):
                self.assertEqual(verify_pack(pack), [])

    def test_校验器拒绝累计正文快照超限(self) -> None:
        from unittest.mock import patch

        from icode.pack_verify import pack_digest, sha256_file

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            pack = ws / "pack"
            report = build_evidence_pack(out_dir, dest=pack, gates_json=None)
            self.assertTrue(report.ok, report.render())
            manifest_path = pack / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            index_path = pack / "artifacts.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            artifact = index["artifacts"][0]
            old_snapshot_rel = artifact["snapshot"]
            new_snapshot_rel = "ticket/custom/plan.md"
            new_snapshot = pack / new_snapshot_rel
            new_snapshot.parent.mkdir(parents=True)
            (pack / old_snapshot_rel).replace(new_snapshot)
            artifact["snapshot"] = new_snapshot_rel
            index_path.write_text(json.dumps(index), encoding="utf-8")
            package_entry = next(
                entry for entry in manifest["files"]
                if entry["path"] == old_snapshot_rel
            )
            package_entry["path"] = new_snapshot_rel
            package_entry["sha256"] = sha256_file(new_snapshot)
            package_entry["size"] = new_snapshot.stat().st_size
            index_entry = next(
                entry for entry in manifest["files"]
                if entry["path"] == "artifacts.json"
            )
            index_entry["sha256"] = sha256_file(index_path)
            index_entry["size"] = index_path.stat().st_size
            manifest["pack_digest"] = pack_digest(manifest["files"])
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            body_bytes = sum(
                (pack / item["snapshot"]).stat().st_size
                for item in index["artifacts"] if item["snapshot"]
            )

            with patch(
                "icode.pack_verify._MAX_PACKAGE_ARTIFACT_BYTES", body_bytes - 1,
                create=True,
            ):
                problems = verify_pack(pack)

            self.assertTrue(
                any("产物快照累计字节超过安全上限" in problem for problem in problems),
                problems,
            )

    def test_导出器单文件或总快照字节超限时清理前保留旧包(self) -> None:
        from unittest.mock import patch

        from icode.evidence import EvidenceError

        for limit_name in ("_MAX_PACKAGE_FILE_BYTES", "_MAX_PACKAGE_ARTIFACT_BYTES"):
            with self.subTest(limit=limit_name), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                events = [
                    json.loads(line)
                    for line in (out_dir / ".ico_events.jsonl").read_text(
                        encoding="utf-8",
                    ).splitlines()
                    if line.strip()
                ]
                artifact = next(
                    event for event in events if event.get("event_type") == "artifact_written"
                )
                artifact_size = Path(artifact["payload"]["path"]).stat().st_size
                dest = ws / "existing-pack"
                dest.mkdir()
                marker = dest / "keep.txt"
                marker.write_text("preserve previous evidence pack\n", encoding="utf-8")

                selected_limit = artifact_size - 1
                with patch(
                    f"icode.evidence.{limit_name}", selected_limit, create=True,
                ):
                    with self.assertRaisesRegex(EvidenceError, "产物快照.*安全上限"):
                        build_evidence_pack(
                            out_dir, dest=dest, gates_json=None,
                        )

                self.assertEqual(
                    marker.read_text(encoding="utf-8"),
                    "preserve previous evidence pack\n",
                )

    def test_正文复制对累计限额失败时只清理本次创建的部分文件(self) -> None:
        from icode.evidence import EvidenceError, _copy_file_bounded
        from icode.pack_verify import _HashReadBudget

        with temp_workspace() as ws:
            source = ws / "source.bin"
            source.write_bytes(b"0123456789")
            destination = ws / "snapshot.bin"
            with self.assertRaisesRegex(EvidenceError, "产物快照累计字节超过安全上限"):
                _copy_file_bounded(
                    source,
                    destination,
                    max_bytes=20,
                    read_budget=_HashReadBudget(20),
                    artifact_budget=_HashReadBudget(9),
                )
            self.assertFalse(destination.exists())

            destination.write_bytes(b"existing content")
            with self.assertRaises(FileExistsError):
                _copy_file_bounded(
                    source,
                    destination,
                    max_bytes=20,
                    read_budget=_HashReadBudget(20),
                    artifact_budget=_HashReadBudget(20),
                )
            self.assertEqual(destination.read_bytes(), b"existing content")

    def test_清单与正文索引条目数有上限(self) -> None:
        from unittest.mock import patch

        for relative, constant in (
            ("manifest.json", "_MAX_MANIFEST_FILE_ENTRIES"),
            ("artifacts.json", "_MAX_ARTIFACT_INDEX_ENTRIES"),
        ):
            with self.subTest(member=relative), temp_workspace() as ws:
                out_dir = make_finished_plan_ticket(self.settings, ws / "work")
                pack = ws / "pack"
                report = build_evidence_pack(
                    out_dir, dest=pack, gates_json=self.settings.gates_json,
                )
                self.assertTrue(report.ok, report.render())
                if relative == "manifest.json":
                    count = len(json.loads(
                        (pack / relative).read_text(encoding="utf-8"),
                    )["files"])
                else:
                    count = len(json.loads(
                        (pack / relative).read_text(encoding="utf-8"),
                    )["artifacts"])
                with patch(f"icode.pack_verify.{constant}", count):
                    self.assertEqual(verify_pack(pack), [])
                with patch(f"icode.pack_verify.{constant}", count - 1):
                    problems = verify_pack(pack)
                self.assertTrue(
                    any("条目数量超过安全上限" in problem for problem in problems),
                    problems,
                )

    def test_目录枚举在排序前执行条目数上限(self) -> None:
        from unittest.mock import patch

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            pack = ws / "pack"
            report = build_evidence_pack(
                out_dir, dest=pack, gates_json=self.settings.gates_json,
            )
            self.assertTrue(report.ok, report.render())
            count = sum(1 for _ in pack.rglob("*"))
            with patch("icode.pack_verify._MAX_PACKAGE_ENTRY_COUNT", count):
                self.assertEqual(verify_pack(pack), [])
            with patch("icode.pack_verify._MAX_PACKAGE_ENTRY_COUNT", count - 1):
                problems = verify_pack(pack)
            self.assertTrue(
                any("目录条目数量超过安全上限" in problem for problem in problems),
                problems,
            )

    def test_导出器拒绝超预算metadata且保留旧包(self) -> None:
        from unittest.mock import patch

        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_text("preserve previous evidence pack\n", encoding="utf-8")
            metadata_size = (out_dir / ".ico_metadata.json").stat().st_size

            with patch("icode.evidence._MAX_METADATA_JSON_BYTES", metadata_size - 1):
                with self.assertRaises(EvidenceError):
                    build_evidence_pack(
                        out_dir, dest=dest, gates_json=self.settings.gates_json,
                    )

            self.assertEqual(
                marker.read_text(encoding="utf-8"), "preserve previous evidence pack\n",
            )

    def test_导出器拒绝会超出产物索引预算的任务且保留旧包(self) -> None:
        from unittest.mock import patch

        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_text("preserve previous evidence pack\n", encoding="utf-8")

            with patch("icode.evidence._MAX_ARTIFACT_INDEX_ENTRIES", 0):
                with self.assertRaisesRegex(EvidenceError, "产物索引条目数量"):
                    build_evidence_pack(
                        out_dir, dest=dest, gates_json=self.settings.gates_json,
                    )

            self.assertEqual(
                marker.read_text(encoding="utf-8"), "preserve previous evidence pack\n",
            )

    def test_导出器在产物索引JSON超预算前保留旧包(self) -> None:
        from unittest.mock import patch

        from icode.evidence import EvidenceError

        with temp_workspace() as ws:
            out_dir = make_finished_plan_ticket(self.settings, ws / "work")
            dest = ws / "existing-pack"
            dest.mkdir()
            marker = dest / "keep.txt"
            marker.write_text("preserve previous evidence pack\n", encoding="utf-8")

            with patch("icode.evidence._MAX_ARTIFACT_INDEX_JSON_BYTES", 1):
                with self.assertRaisesRegex(EvidenceError, "产物索引 JSON 超过输入字节上限"):
                    build_evidence_pack(
                        out_dir, dest=dest, gates_json=self.settings.gates_json,
                    )

            self.assertEqual(
                marker.read_text(encoding="utf-8"), "preserve previous evidence pack\n",
            )


if __name__ == "__main__":
    unittest.main()
