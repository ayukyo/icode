"""本地工单工作台 HTTP 边界测试。"""

from __future__ import annotations

import json
import re
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from tests._support import require_skill, temp_workspace

from icode.autonomy import ExecutionResult
from icode.cli import _build_parser
from icode.workbench import ASSETS_DIR, MAX_BODY_BYTES, WorkbenchServer


class _ImmediateExecutor:
    def __init__(self) -> None:
        self.called = threading.Event()
        self.calls = 0

    def execute(self, context, control) -> ExecutionResult:
        self.calls += 1
        self.called.set()
        control.safe_point("plan")
        return ExecutionResult(state="succeeded", last_step="plan")


def _request(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    cookie: str | None = None,
    origin: str | None = None,
    content_type: str = "application/json",
):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        request.add_header("Content-Type", content_type)
    if cookie:
        request.add_header("Cookie", cookie)
    if origin:
        request.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return response.status, dict(response.headers), response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8")


class TestWorkbenchHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_ctx = temp_workspace()
        cls.workspace = cls.workspace_ctx.__enter__()
        cls.server = WorkbenchServer(
            settings=require_skill(),
            workspace=cls.workspace,
            index_path=cls.workspace / "index.json",
            port=0,
        )
        cls.url = cls.server.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()
        cls.workspace_ctx.__exit__(None, None, None)

    def _cookie(self) -> str:
        status, headers, _ = _request(self.url)
        self.assertEqual(status, 200)
        raw = headers.get("Set-Cookie", "")
        self.assertIn("icode_workbench_session=", raw)
        self.assertIn("SameSite=Strict", raw)
        return raw.split(";", 1)[0]

    def _payload(self, **extra) -> dict:
        payload = {
            "project_id": self.server.service.project_id,
            "title": "断线恢复",
            "description": "设备恢复在线后任务没有继续。",
            "expected_result": "恢复任务，或明确提示原因。",
            "priority": "normal",
            "locale": "zh-CN",
            "execution_mode": "interactive",
            "request_id": "http-create-1",
        }
        payload.update(extra)
        return payload

    def test_只监听_loopback(self) -> None:
        self.assertTrue(self.url.startswith("http://127.0.0.1:"))

    def test_健康检查无需会话且包含安全响应头(self) -> None:
        status, headers, body = _request(self.url + "api/v1/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'none'", headers.get("Content-Security-Policy", ""))

    def test_API_无_cookie_被拒(self) -> None:
        status, _, _ = _request(self.url + "api/v1/bootstrap")
        self.assertEqual(status, 403)

    def test_bootstrap_只返回不透明项目身份(self) -> None:
        status, _, body = _request(
            self.url + "api/v1/bootstrap", cookie=self._cookie())
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data["projects"]), 1)
        self.assertTrue(data["projects"][0]["project_id"].startswith("project-"))
        self.assertNotIn(str(self.workspace), body)
        self.assertNotIn("project_path", body)

    def test_bootstrap_返回安全的自主能力摘要(self) -> None:
        status, _, body = _request(
            self.url + "api/v1/bootstrap", cookie=self._cookie())
        self.assertEqual(status, 200)
        capability = json.loads(body)["capabilities"]["autonomous"]
        self.assertFalse(capability["enabled"])
        self.assertEqual(capability["pause_semantics"], "contract_step_boundary")
        self.assertEqual(
            capability["intents"], ["start", "pause", "resume", "cancel", "takeover"])
        for forbidden in (
            str(self.workspace), "key_file", "api_key", "base_url", "backend", "model",
        ):
            self.assertNotIn(forbidden, body)

    def test_跨源建单被拒(self) -> None:
        status, _, _ = _request(
            self.url + "api/v1/tickets",
            method="POST",
            payload=self._payload(request_id="cross-origin"),
            cookie=self._cookie(),
            origin="https://evil.example.com",
        )
        self.assertEqual(status, 403)

    def test_建单与详情闭环(self) -> None:
        cookie = self._cookie()
        status, _, body = _request(
            self.url + "api/v1/tickets",
            method="POST",
            payload=self._payload(),
            cookie=cookie,
        )
        self.assertIn(status, (200, 201))
        created = json.loads(body)["ticket"]
        ticket_id = created["ticket_id"]
        status, _, detail_body = _request(
            self.url + "api/v1/tickets/" + ticket_id,
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(detail_body)["ticket"]["title"], "断线恢复")
        self.assertNotIn(str(self.workspace), detail_body)

    def test_搜索真实工单(self) -> None:
        cookie = self._cookie()
        create_status, _, _ = _request(
            self.url + "api/v1/tickets",
            method="POST",
            payload=self._payload(
                title="可独立搜索的工单", request_id="search-independent-ticket"),
            cookie=cookie,
        )
        self.assertIn(create_status, (200, 201))
        status, _, body = _request(
            self.url + "api/v1/tickets?query=%E5%8F%AF%E7%8B%AC%E7%AB%8B%E6%90%9C%E7%B4%A2",
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        snapshot = json.loads(body)
        self.assertGreaterEqual(len(snapshot["tickets"]), 1)
        self.assertFalse(snapshot["capabilities"]["autonomous"]["enabled"])
        self.assertNotIn(str(self.workspace), body)

    def test_未知字段和路径命令被拒(self) -> None:
        cookie = self._cookie()
        for field, value in (
            ("path", "/etc/passwd"),
            ("argv", ["rm", "-rf", "/"]),
            ("shell", "bash -c x"),
        ):
            status, _, body = _request(
                self.url + "api/v1/tickets",
                method="POST",
                payload=self._payload(request_id=f"reject-{field}", **{field: value}),
                cookie=cookie,
            )
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)["code"], "invalid_request")
            self.assertNotIn(str(self.workspace), body)

    def test_错误_content_type_被拒(self) -> None:
        status, _, _ = _request(
            self.url + "api/v1/tickets",
            method="POST",
            payload=self._payload(request_id="wrong-content-type"),
            cookie=self._cookie(),
            content_type="text/plain",
        )
        self.assertEqual(status, 415)

    def test_超大请求体返回_413(self) -> None:
        status, _, body = _request(
            self.url + "api/v1/tickets",
            method="POST",
            payload=self._payload(
                request_id="too-large",
                description="x" * (MAX_BODY_BYTES + 1),
            ),
            cookie=self._cookie(),
        )
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body)["code"], "request_too_large")

    def test_未知路由_404(self) -> None:
        status, _, body = _request(self.url + "api/v1/unknown", cookie=self._cookie())
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["code"], "not_found")

    def test_intent_端点复用会话跨源与严格字段边界(self) -> None:
        cookie = self._cookie()
        created_status, _, created_body = _request(
            self.url + "api/v1/tickets",
            method="POST",
            payload=self._payload(
                request_id="intent-boundary-ticket", execution_mode="autonomous"),
            cookie=cookie,
        )
        self.assertIn(created_status, (200, 201))
        ticket_id = json.loads(created_body)["ticket"]["ticket_id"]
        endpoint = self.url + "api/v1/tickets/" + ticket_id + "/intents"

        cases = (
            ({"intent": "start", "request_id": "no-cookie"}, None, None, 403, "forbidden"),
            ({"intent": "start", "request_id": "cross-origin"}, cookie,
             "https://evil.example.com", 403, "forbidden"),
            ({"intent": "launch", "request_id": "bad-intent"}, cookie, None,
             400, "invalid_intent"),
            ({"intent": "start", "request_id": "extra", "path": "/tmp/x"},
             cookie, None, 400, "invalid_intent"),
            ({"intent": "start", "request_id": "disabled"}, cookie, None,
             409, "capability_disabled"),
        )
        for payload, case_cookie, origin, expected_status, expected_code in cases:
            with self.subTest(payload=payload):
                status, _, body = _request(
                    endpoint, method="POST", payload=payload,
                    cookie=case_cookie, origin=origin,
                )
                self.assertEqual(status, expected_status)
                self.assertEqual(json.loads(body)["code"], expected_code)
                self.assertNotIn(str(self.workspace), body)

        status, _, body = _request(
            self.url + "api/v1/tickets/bad%2Fid/intents",
            method="POST",
            payload={"intent": "start", "request_id": "bad-ticket"},
            cookie=cookie,
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["code"], "invalid_ticket_id")

    def test_真实_HTTP_通过_manager_启动且建单本身不自启(self) -> None:
        executor = _ImmediateExecutor()
        with temp_workspace() as workspace:
            server = WorkbenchServer(
                settings=require_skill(),
                workspace=workspace,
                index_path=workspace / "index.json",
                port=0,
                enable_autonomous=True,
                autonomy_executor=executor,
                autonomy_limits={
                    "max_turns": 7,
                    "budget_tokens": 1200,
                    "isolation_level": "application_only",
                },
            )
            url = server.start()
            try:
                status, headers, _ = _request(url)
                self.assertEqual(status, 200)
                cookie = headers["Set-Cookie"].split(";", 1)[0]
                project_id = server.service.project_id
                status, _, body = _request(
                    url + "api/v1/tickets",
                    method="POST",
                    payload={
                        "project_id": project_id,
                        "title": "HTTP autonomous",
                        "description": "Run through the manager.",
                        "expected_result": "A stable terminal state.",
                        "priority": "normal",
                        "locale": "en-US",
                        "execution_mode": "autonomous",
                        "request_id": "http-autonomous-create",
                    },
                    cookie=cookie,
                )
                self.assertIn(status, (200, 201))
                ticket = json.loads(body)["ticket"]
                self.assertEqual(ticket["autonomous_run"]["state"], "pending")
                self.assertEqual(executor.calls, 0)

                status, _, body = _request(
                    url + f"api/v1/tickets/{ticket['ticket_id']}/intents",
                    method="POST",
                    payload={"intent": "start", "request_id": "http-start-1"},
                    cookie=cookie,
                )
                self.assertEqual(status, 202)
                self.assertTrue(json.loads(body)["ok"])
                self.assertTrue(executor.called.wait(5))

                deadline = time.monotonic() + 5
                runtime_state = None
                while time.monotonic() < deadline:
                    _, _, detail_body = _request(
                        url + f"api/v1/tickets/{ticket['ticket_id']}", cookie=cookie)
                    runtime_state = json.loads(detail_body)["ticket"]["autonomous_run"]["state"]
                    if runtime_state == "succeeded":
                        break
                    time.sleep(0.02)
                self.assertEqual(runtime_state, "succeeded")
                self.assertEqual(executor.calls, 1)

                _, _, bootstrap_body = _request(
                    url + "api/v1/bootstrap", cookie=cookie)
                capability = json.loads(bootstrap_body)["capabilities"]["autonomous"]
                self.assertTrue(capability["enabled"])
                self.assertEqual(capability["limits"]["max_turns"], 7)
                self.assertEqual(capability["limits"]["budget_tokens"], 1200)
                self.assertNotIn("backend", bootstrap_body)
                self.assertNotIn("model", bootstrap_body)
            finally:
                server.stop()

    def test_stop即使自主manager异常也完成线程join与server_close(self) -> None:
        with temp_workspace() as workspace:
            server = WorkbenchServer(
                settings=require_skill(),
                workspace=workspace,
                index_path=workspace / "index.json",
                port=0,
            )
            server.start()
            thread = server.thread
            self.assertIsNotNone(thread)
            assert thread is not None
            with patch.object(
                server.autonomy,
                "shutdown",
                side_effect=RuntimeError("simulated manager shutdown failure"),
            ), patch.object(
                thread, "join", wraps=thread.join,
            ) as join_mock, patch.object(
                server.httpd, "server_close", wraps=server.httpd.server_close,
            ) as close_mock:
                with self.assertRaisesRegex(RuntimeError, "manager shutdown failure"):
                    server.stop()

            join_mock.assert_called_once()
            close_mock.assert_called_once()
            self.assertIsNone(server.thread)


class TestWorkbenchAssets(unittest.TestCase):
    def test_无外链与内联脚本(self) -> None:
        for name in ("index.html", "app.js", "style.css"):
            text = (ASSETS_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn("https://", text, name)
            self.assertNotIn("http://", text, name)
            self.assertNotIn("cdn.", text, name)
        html = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
        for body in re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S):
            self.assertEqual(body.strip(), "")
        self.assertIn('src="/static/workbench.js"', html)

    def test_中英文资源与环境语言解析存在(self) -> None:
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn('"zh-CN"', js)
        self.assertIn('"en-US"', js)
        self.assertIn("navigator.languages", js)
        self.assertIn("navigator.language", js)
        self.assertIn("localStorage", js)

    def test_切换语言时同步刷新已选工单详情(self) -> None:
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn("selectedTicket: null", js)
        self.assertIn("if (state.selectedTicket) { renderDetail(state.selectedTicket); }", js)

    def test_动态内容不用_innerHTML(self) -> None:
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        code = "\n".join(
            line for line in js.splitlines() if not line.strip().startswith("//"))
        self.assertNotIn(".innerHTML", code)
        self.assertIn("textContent", code)

    def test_建单只提交结构化字段(self) -> None:
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        for field in (
            "project_id", "title", "description", "expected_result",
            "priority", "locale", "execution_mode", "request_id",
        ):
            self.assertIn(field, js)
        for forbidden in ("argv", "shell", "path:"):
            self.assertNotIn(forbidden, js)

    def test_工作台关键入口齐备(self) -> None:
        html = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "language-select", "ticket-search", "ticket-list", "new-ticket-button",
            "new-ticket-dialog", "execution-mode", "technical-details",
        ):
            self.assertIn(f'id="{element_id}"', html)

    def test_自主运行中英文案控件与只读配置摘要齐备(self) -> None:
        html = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        for element_id in (
            "autonomy-panel", "autonomy-state", "autonomy-last-step",
            "autonomy-capability", "autonomy-limits", "intent-start", "intent-pause",
            "intent-resume", "intent-cancel", "intent-takeover",
        ):
            self.assertIn(f'id="{element_id}"', html)
        for phrase in (
            "仅在当前契约步骤完成后暂停",
            "Pauses only after the current contract step finishes",
            "启动自动处理", "Start autonomous work",
            "接管为会话模式", "Take over interactively",
        ):
            self.assertIn(phrase, js)
        self.assertIn('var payload = { intent: intent, request_id: requestId() };', js)
        self.assertIn('"/intents"', js)
        intent_source = js[js.index("function submitIntent"):js.index("function bootstrap")]
        for forbidden in ("path:", "key_file", "api_key", "base_url", "backend", "model:"):
            self.assertNotIn(forbidden, intent_source)

    def test_失败阻断与中断状态均允许显式恢复(self) -> None:
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn(
            'var RESUMABLE_AUTONOMY_STATES = ["paused", "failed", "blocked", "interrupted"]',
            js,
        )
        self.assertIn(
            'resume: RESUMABLE_AUTONOMY_STATES.indexOf(current) !== -1',
            js,
        )
        self.assertIn(
            'start: ["pending", "cancelled", "succeeded"].indexOf(current) !== -1',
            js,
        )
        self.assertIn("ACTIVE_AUTONOMY_STATES", js)
        self.assertIn("scheduleActivePoll", js)


class TestWorkbenchCLI(unittest.TestCase):
    def test_workbench_命令绑定可信工作区且不提供_host(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "workbench", "--workspace", "/srv/project", "--port", "0", "--no-browser",
        ])
        self.assertEqual(args.command, "workbench")
        self.assertEqual(args.workspace, "/srv/project")
        self.assertEqual(args.port, 0)
        self.assertTrue(args.no_browser)
        self.assertFalse(args.enable_autonomous)
        self.assertFalse(hasattr(args, "host"))

    def test_workbench_自主执行必须显式启用且配置仅在服务端(self) -> None:
        args = _build_parser().parse_args([
            "workbench", "--workspace", "/srv/project", "--enable-autonomous",
            "--backend", "openai-compatible", "--model", "private-model",
            "--base-url", "https://models.internal/v1", "--key-file", "/safe/key.txt",
            "--max-turns", "9", "--budget-tokens", "2400", "--isolation", "bwrap",
            "--no-browser",
        ])
        self.assertTrue(args.enable_autonomous)
        self.assertEqual(args.backend, "openai-compatible")
        self.assertEqual(args.model, "private-model")
        self.assertEqual(args.base_url, "https://models.internal/v1")
        self.assertEqual(args.key_file, "/safe/key.txt")
        self.assertEqual(args.max_turns, 9)
        self.assertEqual(args.budget_tokens, 2400)
        self.assertEqual(args.isolation, "bwrap")

    def test_旧_webui_审批台入口仍存在(self) -> None:
        args = _build_parser().parse_args(["webui", "--no-browser"])
        self.assertEqual(args.command, "webui")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
