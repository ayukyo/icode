"""ACP 前端：只承载交互、意图走同一词表、方法白名单封闭（R5/W4）。"""

import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from icode.acp import (
    ACP_METHODS,
    SUBSCRIBABLE_EVENTS,
    AcpController,
    AcpError,
    AcpSession,
    controller_from_autonomy,
)
from icode.autonomy import INTENTS, normalize_intent_payload


def _controller() -> AcpController:
    intents: list[tuple[str, dict]] = []
    reads: list[str] = []

    def handle_intent(ticket_id: str, payload) -> dict:
        # 与生产一致：先过同一词表校验，再应用
        clean = normalize_intent_payload(payload)
        intents.append((ticket_id, clean))
        if clean["intent"] not in INTENTS:
            raise AcpError("invalid_intent", "intent 不是受支持的稳定动作")
        return {"ticket_id": ticket_id, "status": "idle",
                "autonomous_run": {"state": clean["intent"]}}

    def read_ticket(ticket_id: str) -> dict:
        reads.append(ticket_id)
        return {"ticket_id": ticket_id, "status": "idle",
                "requirement": "保持门禁完整"}

    return AcpController(handle_intent=handle_intent, read_ticket=read_ticket)


class TestAcpMethodWhitelist(unittest.TestCase):
    def setUp(self) -> None:
        self.session = AcpSession(controller=_controller())

    def _request(self, method: str, params: dict | None = None, rid: int = 1) -> dict:
        frame = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            frame["params"] = params
        raw = self.session.dispatch(json.dumps(frame).encode("utf-8"))
        assert raw is not None
        return json.loads(raw.decode("utf-8"))

    def test_白名单方法可用(self) -> None:
        listed = self._request("list_methods")
        self.assertEqual(listed["result"]["methods"], sorted(ACP_METHODS))
        self.assertTrue(set(listed["result"]["events"]) <= SUBSCRIBABLE_EVENTS)

    def test_循环控制类方法一律拒绝(self) -> None:
        for method in ("run_tool", "start_run", "stop_run", "pause", "resume",
                       "Loop.run", "execute_command", "write_ledger"):
            with self.subTest(method=method):
                response = self._request(method, {"argv": ["rm", "-rf", "/"]})
                self.assertEqual(response["error"]["data"]["code"], "method_not_supported")

    def test_未知方法拒绝且不留审计外通道(self) -> None:
        self._request("fs/write_file", {"path": ".ico_events.jsonl"})
        self.assertIn("fs/write_file",
                      [item["method"] for item in self.session.refusals])

    def test_畸形帧与batch帧失败封闭(self) -> None:
        parsed = json.loads(self.session.dispatch(b"not json").decode("utf-8"))
        self.assertEqual(parsed["error"]["data"]["code"], "parse_error")
        batch = json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "list_methods"}])
        parsed = json.loads(self.session.dispatch(batch.encode("utf-8")).decode("utf-8"))
        self.assertEqual(parsed["error"]["data"]["code"], "batch_not_supported")

    def test_通知不产生响应(self) -> None:
        frame = {"jsonrpc": "2.0", "method": "list_methods"}
        self.assertIsNone(self.session.dispatch(json.dumps(frame).encode("utf-8")))


class TestAcpIntentEntry(unittest.TestCase):
    def setUp(self) -> None:
        self.session = AcpSession(controller=_controller())

    def test_合法意图经同一词表转发给既有入口(self) -> None:
        response = self._submit("start")
        self.assertTrue(response["result"]["accepted"])
        self.assertEqual(response["result"]["ticket"]["ticket_id"], "ICODE-1")

    def test_词表外意图被拒绝且不进入控制面(self) -> None:
        for intent in ("armageddon", "start; rm -rf /", ""):
            with self.subTest(intent=intent):
                response = self._submit(intent)
                self.assertIn("error", response)
                self.assertEqual(response["error"]["data"]["code"], "invalid_intent")
                self.assertNotIn("result", response)

    def test_多余字段的意图载荷被拒绝(self) -> None:
        frame = {"jsonrpc": "2.0", "id": 7, "method": "submit_intent",
                 "params": {"ticket_id": "ICODE-1",
                            "payload": {"intent": "start", "request_id": "r-1",
                                        "sandbox": False}}}
        raw = self.session.dispatch(json.dumps(frame).encode("utf-8"))
        response = json.loads(raw.decode("utf-8"))
        self.assertIn("error", response)
        self.assertEqual(response["error"]["data"]["code"], "invalid_intent")

    def _submit(self, intent: str, rid: int = 1) -> dict:
        frame = {"jsonrpc": "2.0", "id": rid, "method": "submit_intent",
                 "params": {"ticket_id": "ICODE-1",
                            "payload": {"intent": intent, "request_id": "req-1"}}}
        raw = self.session.dispatch(json.dumps(frame).encode("utf-8"))
        return json.loads(raw.decode("utf-8"))


class TestAcpEvents(unittest.TestCase):
    def test_只转发订阅白名单内事件(self) -> None:
        session = AcpSession(controller=_controller())
        result = json.loads(session.dispatch(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "subscribe_events",
            "params": {"events": ["tool_result", "not_a_real_event"]},
        }).encode("utf-8")).decode("utf-8"))
        self.assertEqual(result["result"]["refused"], ["not_a_real_event"])

        session.on_event("tool_result", {"tool": "read_file"})
        session.on_event("secret_internal", {"token": "x"})
        self.assertEqual([item["params"]["event"] for item in session.outbox],
                         ["tool_result"])

    def test_外发箱有界(self) -> None:
        session = AcpSession(controller=_controller())
        session.subscriptions.add("assistant")
        for index in range(100):
            session.on_event("assistant", {"turn": index})
        self.assertLessEqual(len(session.outbox), 64)
        self.assertTrue(any(item["code"] == "outbox_full"
                            for item in session.refusals))

    def test_载荷超限被拒绝(self) -> None:
        session = AcpSession(controller=_controller())
        session.subscriptions.add("assistant")
        session.on_event("assistant", {"blob": "x" * 70_000})
        self.assertEqual(list(session.outbox), [])
        self.assertTrue(any(item["code"] == "event_oversize"
                            for item in session.refusals))


class TestAcpServeLoop(unittest.TestCase):
    def test_端到端会话且不产生任何文件(self) -> None:
        session = AcpSession(controller=_controller())
        stdin = io.BytesIO(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "list_methods"}).encode("utf-8")
            + b"\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "read_ticket",
                          "params": {"ticket_id": "ICODE-9"}}).encode("utf-8") + b"\n"
        )
        stdout = io.BytesIO()
        with TemporaryDirectory() as tmp:
            previous = Path.cwd()
            try:
                import os
                os.chdir(tmp)
                session.serve(stdin, stdout)
                self.assertEqual(list(Path(tmp).iterdir()), [])
            finally:
                os.chdir(previous)
        lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line]
        self.assertEqual([line["id"] for line in lines], [1, 2])
        self.assertEqual(lines[1]["result"]["ticket"]["ticket_id"], "ICODE-9")


class TestAcpControllerWiring(unittest.TestCase):
    def test_形状不符的接线失败封闭(self) -> None:
        with self.assertRaises(AcpError):
            controller_from_autonomy(object(), object())

    def test_模块不定义自己的意图词表(self) -> None:
        source = Path(__file__).resolve().parent.parent.joinpath(
            "src/icode/acp.py").read_text(encoding="utf-8")
        for literal in ('"start"', '"stop"', '"pause"', '"retry"', "INTENTS ="):
            self.assertNotIn(literal, source,
                             f"acp.py 不得自定义意图词表：{literal}")


if __name__ == "__main__":
    unittest.main()
