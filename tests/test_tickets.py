"""单工程工单目录与受控建单服务测试。"""

from __future__ import annotations

import json
import unittest

from tests._support import require_skill, temp_workspace

from icode.tickets import (
    TicketError,
    TicketService,
    normalize_create_ticket_payload,
)


def _payload(project_id: str, **overrides) -> dict:
    payload = {
        "project_id": project_id,
        "title": "Reconnect recovery",
        "description": "The task does not continue after reconnect.",
        "expected_result": "Resume or explain why it cannot resume.",
        "priority": "normal",
        "locale": "en-US",
        "execution_mode": "autonomous",
        "request_id": "ui-123",
    }
    payload.update(overrides)
    return payload


class TestCreateTicketPayload(unittest.TestCase):
    def test_接受中英文与两种执行方式(self) -> None:
        for locale in ("zh-CN", "en-US"):
            for mode in ("interactive", "autonomous"):
                clean = normalize_create_ticket_payload(
                    _payload("project-abc", locale=locale, execution_mode=mode))
                self.assertEqual(clean["locale"], locale)
                self.assertEqual(clean["execution_mode"], mode)

    def test_拒绝路径命令及未知字段(self) -> None:
        for key, value in (
            ("path", "/etc/passwd"),
            ("argv", ["rm", "-rf", "/"]),
            ("shell", "bash -c x"),
            ("unexpected", True),
        ):
            with self.subTest(key=key), self.assertRaises(TicketError):
                normalize_create_ticket_payload(_payload("project-abc", **{key: value}))

    def test_拒绝非法枚举与空文本(self) -> None:
        for field, value in (
            ("locale", "fr-FR"),
            ("execution_mode", "magic"),
            ("priority", "now"),
            ("title", " "),
            ("description", ""),
            ("expected_result", ""),
        ):
            with self.subTest(field=field), self.assertRaises(TicketError):
                normalize_create_ticket_payload(_payload("project-abc", **{field: value}))


class TestTicketService(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = require_skill()
        self.workspace_ctx = temp_workspace()
        self.workspace = self.workspace_ctx.__enter__()
        self.index_path = self.workspace / "global-index.json"
        self.service = TicketService(
            self.settings,
            workspace=self.workspace,
            index_path=self.index_path,
        )

    def tearDown(self) -> None:
        self.workspace_ctx.__exit__(None, None, None)

    def test_建单经控制面并投影自动模式待激活(self) -> None:
        created = self.service.create_ticket(_payload(self.service.project_id))

        self.assertTrue(created["ok"])
        ticket = created["ticket"]
        self.assertEqual(ticket["title"], "Reconnect recovery")
        self.assertEqual(ticket["requested_execution_mode"], "autonomous")
        self.assertEqual(ticket["effective_execution_mode"], "interactive")
        self.assertEqual(ticket["mode_status"], "pending_activation")
        self.assertEqual(ticket["locale"], "en-US")
        self.assertNotIn(str(self.workspace), json.dumps(ticket))

        out_dirs = list((self.workspace / ".icode_output").glob(".icode_output_*"))
        self.assertEqual(len(out_dirs), 1)
        metadata = json.loads((out_dirs[0] / ".ico_metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(
            metadata["extensions"]["icode_agent"]["requested_execution_mode"],
            "autonomous",
        )
        event_types = [
            json.loads(line)["event_type"]
            for line in (out_dirs[0] / ".ico_events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertIn("metadata_updated", event_types)

    def test_会话模式立即生效(self) -> None:
        created = self.service.create_ticket(_payload(
            self.service.project_id,
            request_id="ui-interactive",
            execution_mode="interactive",
        ))
        ticket = created["ticket"]
        self.assertEqual(ticket["effective_execution_mode"], "interactive")
        self.assertEqual(ticket["mode_status"], "active")

    def test_幂等重试不重复建单(self) -> None:
        payload = _payload(self.service.project_id)
        first = self.service.create_ticket(payload)
        second = self.service.create_ticket(payload)
        self.assertFalse(first["already_applied"])
        self.assertTrue(second["already_applied"])
        self.assertEqual(first["ticket"]["ticket_id"], second["ticket"]["ticket_id"])
        self.assertEqual(
            len(list((self.workspace / ".icode_output").glob(".icode_output_*"))), 1)

    def test_列表搜索不暴露路径(self) -> None:
        self.service.create_ticket(_payload(self.service.project_id))
        snapshot = self.service.snapshot(query="RECONNECT")
        self.assertEqual(len(snapshot["tickets"]), 1)
        raw = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn(str(self.workspace), raw)
        self.assertNotIn("out_dir", raw)
        self.assertNotIn("project_path", raw)

    def test_错误项目身份被拒绝(self) -> None:
        with self.assertRaises(TicketError):
            self.service.create_ticket(_payload("project-not-this-one"))

    def test_损坏工单降级为错误卡片而不泄露路径(self) -> None:
        root = self.workspace / ".icode_output" / ".icode_output_9"
        root.mkdir(parents=True)
        (root / ".ico_metadata.json").write_text("{bad json", encoding="utf-8")
        snapshot = self.service.snapshot()
        self.assertEqual(snapshot["errors"], [{"code": "ticket_metadata_unreadable", "slot": 9}])
        self.assertNotIn(str(self.workspace), json.dumps(snapshot))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
