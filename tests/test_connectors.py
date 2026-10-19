"""连接器：显式启用、证据缺项即拒、回环传输契约（R5/W5）。"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from pathlib import Path

from icode.connectors import (
    Connector,
    ConnectorError,
    ConnectorInvoker,
    ConnectorRegistry,
    build_connector,
    http_transport,
)
from icode.extension_contract import ExtensionManifest, SideEffect
from icode.tools.base import OPCLASS_EXTERNAL


class _Recorder:
    """记录 start/finish 的假回执通道（与 OperationRecorder 同形）。"""

    def __init__(self, *, can_execute: bool = True, closes: bool = True) -> None:
        self.started: list[tuple[str, str]] = []
        self.finished: list[tuple[str, str, str | None]] = []
        self._can_execute = can_execute
        self._closes = closes

    def start(self, name, opclass, input_desc):
        self.started.append((name, opclass))
        return SimpleNamespace(
            can_execute=self._can_execute, attempt="att-1",
            already_applied=False, detail="ambiguous" if not self._can_execute else "",
        )

    def finish(self, attempt, *, outcome, evidence, check_ref, failure):
        self.finished.append((attempt, outcome, failure))
        return self._closes


def _registry(name: str = "jira", endpoint: str = "https://jira.example.com/rest") -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(build_connector(name=name, kind="ticket", endpoint=endpoint))
    return registry


class TestConnectorRegistration(unittest.TestCase):
    def test_端点主机必须被声明覆盖(self) -> None:
        manifest = ExtensionManifest(
            name="jira", version="1.0.0", kind="connector",
            source="local", opclass=OPCLASS_EXTERNAL,
            side_effects=(SideEffect("network", "other.example.com"),),
            evidence=frozenset({"output_sha256"}),
        )
        with self.assertRaises(ConnectorError) as caught:
            Connector(name="jira", kind="ticket",
                      endpoint="https://jira.example.com/rest", manifest=manifest)
        self.assertEqual(caught.exception.code, "network_undeclared")

    def test_子域视为已覆盖(self) -> None:
        registry = ConnectorRegistry()
        registry.register(build_connector(
            name="jira", kind="ticket", endpoint="https://api.jira.example.com/rest",
        ))
        self.assertEqual(registry.names(), ["jira"])

    def test_类型与端点形态受限(self) -> None:
        for kind, endpoint in (("plugin", "https://x.example.com"),
                               ("ticket", "ftp://x.example.com")):
            with self.subTest(kind=kind, endpoint=endpoint):
                with self.assertRaises(ConnectorError):
                    build_connector(name="x", kind=kind, endpoint=endpoint)

    def test_未启用不可执行(self) -> None:
        registry = _registry()
        invoker = ConnectorInvoker(registry, recorder=_Recorder())
        with self.assertRaises(ConnectorError) as caught:
            invoker.invoke("jira", "create_issue")
        self.assertEqual(caught.exception.code, "connector_not_enabled")


class TestConnectorInvocation(unittest.TestCase):
    def test_正常路径留回执与证据(self) -> None:
        registry = _registry()
        registry.enable("jira")
        recorder = _Recorder()
        invoker = ConnectorInvoker(
            registry, recorder=recorder,
            transport=lambda endpoint, payload: ({"issue": "ICODE-1"}, 200),
        )
        receipt = invoker.invoke("jira", "create_issue", {"summary": "x"})
        self.assertTrue(receipt.ok)
        self.assertEqual(receipt.exit_code, 200)
        self.assertEqual(recorder.started, [("connector:jira", OPCLASS_EXTERNAL)])
        self.assertEqual(recorder.finished, [("att-1", "success", None)])
        self.assertEqual(sorted(receipt.evidence),
                         ["artifact_hashes_sha256", "command_sha256",
                          "exit_code", "output_sha256"])

    def test_没有回执通道即拒绝(self) -> None:
        registry = _registry()
        registry.enable("jira")
        invoker = ConnectorInvoker(registry, recorder=None,
                                   transport=lambda endpoint, payload: ({}, 200))
        with self.assertRaises(ConnectorError) as caught:
            invoker.invoke("jira", "create_issue")
        self.assertEqual(caught.exception.code, "evidence_channel_missing")

    def test_回执不明确时传输不发生(self) -> None:
        registry = _registry()
        registry.enable("jira")
        calls: list[tuple[str, dict]] = []

        def transport(endpoint, payload):
            calls.append((endpoint, dict(payload)))
            return ({}, 200)

        invoker = ConnectorInvoker(
            registry, recorder=_Recorder(can_execute=False), transport=transport,
        )
        with self.assertRaises(ConnectorError) as caught:
            invoker.invoke("jira", "create_issue")
        self.assertEqual(caught.exception.code, "ambiguous_side_effect")
        self.assertEqual(calls, [])

    def test_传输失败留下失败回执(self) -> None:
        registry = _registry()
        registry.enable("jira")
        recorder = _Recorder()

        def transport(endpoint, payload):
            raise OSError("connection refused")

        invoker = ConnectorInvoker(registry, recorder=recorder, transport=transport)
        with self.assertRaises(ConnectorError) as caught:
            invoker.invoke("jira", "create_issue")
        self.assertEqual(caught.exception.code, "transport_error")
        self.assertEqual(recorder.finished, [("att-1", "failure", "transport_error")])

    def test_回执缺少可寻址身份即拒且不发生传输(self) -> None:
        registry = ConnectorRegistry()
        registry.register(build_connector(
            name="jira", kind="ticket", endpoint="https://jira.example.com/rest",
            evidence=frozenset({"execution_attempt"}),
        ))
        registry.enable("jira")
        recorder = _Recorder()
        original_start = recorder.start
        calls: list[str] = []

        def start_without_attempt(name, opclass, input_desc):
            original_start(name, opclass, input_desc)
            return SimpleNamespace(
                can_execute=True, attempt="", already_applied=False, detail="",
            )

        def transport(endpoint, payload):
            calls.append(endpoint)
            return ({"ok": True}, 200)

        recorder.start = start_without_attempt  # type: ignore[method-assign]
        invoker = ConnectorInvoker(registry, recorder=recorder, transport=transport)
        with self.assertRaises(ConnectorError) as caught:
            invoker.invoke("jira", "create_issue")
        self.assertEqual(caught.exception.code, "receipt_attempt_missing")
        self.assertEqual(calls, [])
        self.assertEqual(recorder.finished, [])

    def test_传输未给出有效状态码即拒(self) -> None:
        registry = _registry()
        registry.enable("jira")
        recorder = _Recorder()
        invoker = ConnectorInvoker(
            registry, recorder=recorder,
            transport=lambda endpoint, payload: ({"ok": True}, None),
        )
        with self.assertRaises(ConnectorError) as caught:
            invoker.invoke("jira", "create_issue")
        self.assertEqual(caught.exception.code, "transport_status_invalid")
        self.assertEqual(recorder.finished,
                         [("att-1", "failure", "transport_status_invalid")])

    def test_回执终结失败可见(self) -> None:
        registry = _registry()
        registry.enable("jira")
        invoker = ConnectorInvoker(
            registry, recorder=_Recorder(closes=False),
            transport=lambda endpoint, payload: ({"ok": True}, 200),
        )
        with self.assertRaises(ConnectorError) as caught:
            invoker.invoke("jira", "create_issue")
        self.assertEqual(caught.exception.code, "receipt_finish_failed")


class _LoopbackHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - http.server 回调名
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/fail":
            self.send_response(500)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"echo": body.get("operation")}).encode("utf-8"))

    def log_message(self, *args) -> None:  # 静默
        return


class TestLoopbackTransport(unittest.TestCase):
    def test_回环HTTP默认传输成功与失败路径(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _LoopbackHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_address[1]}/rest"
            registry = ConnectorRegistry()
            registry.register(build_connector(name="local", kind="ci", endpoint=endpoint))
            registry.enable("local")
            recorder = _Recorder()
            invoker = ConnectorInvoker(
                registry, recorder=recorder,
                transport=http_transport(timeout=10, no_proxy=True),
            )
            receipt = invoker.invoke("local", "list_runs", {"repo": "icode"})
            self.assertTrue(receipt.ok)
            self.assertEqual(receipt.output_chars, len('{"echo": "list_runs"}'))
            self.assertEqual(recorder.finished, [("att-1", "success", None)])

            registry.register(build_connector(
                name="broken", kind="ci",
                endpoint=f"http://127.0.0.1:{server.server_address[1]}/fail",
            ))
            registry.enable("broken")
            failing = ConnectorInvoker(
                registry, recorder=_Recorder(),
                transport=http_transport(timeout=10, no_proxy=True),
            )
            with self.assertRaises(ConnectorError) as caught:
                failing.invoke("broken", "list_runs")
            self.assertEqual(caught.exception.code, "transport_error")
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
