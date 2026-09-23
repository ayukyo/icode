"""本地工单工作台 HTTP 边界测试。"""

from __future__ import annotations

import json
import re
import unittest
import urllib.error
import urllib.request

from tests._support import require_skill, temp_workspace

from icode.cli import _build_parser
from icode.workbench import ASSETS_DIR, MAX_BODY_BYTES, WorkbenchServer


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
        status, _, body = _request(
            self.url + "api/v1/tickets?query=%E6%96%AD%E7%BA%BF",
            cookie=self._cookie(),
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(json.loads(body)["tickets"]), 1)

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
        self.assertFalse(hasattr(args, "host"))

    def test_旧_webui_审批台入口仍存在(self) -> None:
        args = _build_parser().parse_args(["webui", "--no-browser"])
        self.assertEqual(args.command, "webui")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
