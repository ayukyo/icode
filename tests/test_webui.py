"""WebUI 测试（Phase 5）。

重点验证三条硬边界**真的成立**，以及"重启后不自动放行"这条最容易漏的规则：

    ① 不做状态第二写入者（不 import 控制面 / 不写工单）
    ② 不收路径 / 命令 / shell（未知字段一律拒绝）
    ③ 挂起审批重启后不自动放行（只在内存 + 超时即拒）

另有资源自足性检查：无 CDN、无内联脚本、不用 innerHTML。
"""

from __future__ import annotations

import ast
import json
import re
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests._support import REPO_ROOT

from icode.approvals import ApprovalRequest
from icode.webui import (
    ALLOWED_FIELDS,
    ASSETS_DIR,
    MAX_REASON_CHARS,
    ApprovalRegistry,
    WebApprover,
    WebUIServer,
    validate_decision_payload,
)


def _request(
    url: str, *, method: str = "GET", payload: dict | None = None,
    cookie: str | None = None, origin: str | None = None, content_type: str = "application/json",
):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", content_type)
    if cookie:
        req.add_header("Cookie", cookie)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8")


class TestPayloadValidation(unittest.TestCase):
    def test_合法负载通过(self) -> None:
        clean, err = validate_decision_payload(
            {"approval_id": "ap-1", "decision": "approve", "reason": "看过日志了"})
        self.assertEqual(err, "")
        assert clean is not None
        self.assertEqual(clean["decision"], "approve")

    def test_拒绝未知字段_不接受路径或命令(self) -> None:
        for extra in ({"path": "/etc/passwd"}, {"argv": ["rm", "-rf", "/"]}, {"shell": "bash -c x"}):
            payload = {"approval_id": "ap-1", "decision": "approve", **extra}
            clean, err = validate_decision_payload(payload)
            self.assertIsNone(clean, extra)
            self.assertIn("未知字段", err, extra)
            self.assertIn("路径/命令", err)

    def test_decision_必须枚举(self) -> None:
        _, err = validate_decision_payload({"approval_id": "a", "decision": "maybe"})
        self.assertIn("decision", err)

    def test_拒绝非对象与缺失字段(self) -> None:
        for bad in ([], "x", 1, None):
            clean, err = validate_decision_payload(bad)
            self.assertIsNone(clean)
            self.assertTrue(err)
        _, err = validate_decision_payload({"decision": "approve"})
        self.assertIn("approval_id", err)

    def test_reason_必须字符串且有长度上限(self) -> None:
        _, err = validate_decision_payload({"approval_id": "a", "decision": "deny", "reason": 5})
        self.assertIn("字符串", err)
        _, err2 = validate_decision_payload(
            {"approval_id": "a", "decision": "deny", "reason": "x" * (MAX_REASON_CHARS + 1)})
        self.assertIn("过长", err2)

    def test_白名单只含三个字段(self) -> None:
        self.assertEqual(ALLOWED_FIELDS, {"approval_id", "decision", "reason"})


class TestRegistryAndApprover(unittest.TestCase):
    def _req(self) -> ApprovalRequest:
        return ApprovalRequest(tool="run_command", arguments={"argv": ["x"]},
                               reason="不在白名单", opclass="managed_write", workspace="/tmp")

    def test_登记与放行(self) -> None:
        reg = ApprovalRegistry()
        item = reg.add(self._req())
        self.assertEqual(len(reg.snapshot()["pending"]), 1)
        self.assertTrue(reg.resolve(item.approval_id, "approve", "ok"))
        self.assertTrue(item.event.is_set())
        self.assertTrue(item.granted)
        self.assertEqual(reg.snapshot()["pending"], [])
        self.assertEqual(reg.snapshot()["history"][-1]["decision"], "approve")

    def test_拒绝生效(self) -> None:
        reg = ApprovalRegistry()
        item = reg.add(self._req())
        reg.resolve(item.approval_id, "deny", "不允许")
        self.assertTrue(item.event.is_set())
        self.assertFalse(item.granted)

    def test_未知_approval_id_不猜测(self) -> None:
        self.assertFalse(ApprovalRegistry().resolve("ap-nonexistent", "approve"))

    def test_超时按拒绝处理(self) -> None:
        approver = WebApprover(registry=ApprovalRegistry(), timeout=0.05)
        self.assertFalse(approver.ask(self._req()), "等待超时必须拒绝，不能默认放行")

    def test_放行路径可用(self) -> None:
        reg = ApprovalRegistry()
        approver = WebApprover(registry=reg, timeout=5.0)
        result: list[bool] = []

        def _worker() -> None:
            result.append(approver.ask(self._req()))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        for _ in range(50):
            pending = reg.snapshot()["pending"]
            if pending:
                reg.resolve(pending[0]["approval_id"], "approve", "同意")
                break
            time.sleep(0.02)
        t.join(timeout=5)
        self.assertEqual(result, [True])

    def test_新实例没有挂起项_重启即作废(self) -> None:
        """硬边界③：挂起项只在内存，进程重启后必然为空 → 不会自动放行。"""
        reg1 = ApprovalRegistry()
        reg1.add(self._req())
        self.assertEqual(len(reg1.snapshot()["pending"]), 1)

        reg2 = ApprovalRegistry()  # 模拟重启后的新进程
        self.assertEqual(reg2.snapshot()["pending"], [])
        self.assertEqual(reg2.snapshot()["history"], [])


class TestServerBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = WebUIServer(port=0)
        cls.url = cls.server.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def _cookie(self) -> str:
        status, headers, _ = _request(self.url)
        self.assertEqual(status, 200)
        raw = headers.get("Set-Cookie", "")
        self.assertIn("icode_session=", raw)
        return raw.split(";", 1)[0]

    def test_仅监听_loopback(self) -> None:
        self.assertTrue(self.url.startswith("http://127.0.0.1:"))

    def test_首页设置会话_cookie_且不含令牌明文给_JS(self) -> None:
        status, headers, body = _request(self.url)
        self.assertEqual(status, 200)
        self.assertIn("SameSite=Strict", headers.get("Set-Cookie", ""))
        self.assertNotIn(self.server.token, body, "页面不应把令牌写进 HTML")

    def test_无_cookie_读状态被拒(self) -> None:
        status, _, _ = _request(self.url + "api/state")
        self.assertEqual(status, 403)

    def test_带_cookie_可读状态(self) -> None:
        status, _, body = _request(self.url + "api/state", cookie=self._cookie())
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["pending"], [])

    def test_无_cookie_写请求被拒(self) -> None:
        status, _, _ = _request(self.url + "api/decision", method="POST",
                                payload={"approval_id": "ap-1", "decision": "approve"})
        self.assertEqual(status, 403)

    def test_跨源写请求被拒(self) -> None:
        status, _, _ = _request(
            self.url + "api/decision", method="POST",
            payload={"approval_id": "ap-1", "decision": "approve"},
            cookie=self._cookie(), origin="https://evil.example.com",
        )
        self.assertEqual(status, 403)

    def test_同源_loopback_origin_放行(self) -> None:
        status, _, body = _request(
            self.url + "api/decision", method="POST",
            payload={"approval_id": "ap-unknown", "decision": "approve"},
            cookie=self._cookie(), origin="http://127.0.0.1:1",
        )
        # 同源通过 → 但 approval_id 未知 → 409（不猜测，不新建）
        self.assertEqual(status, 409)

    def test_未知字段被拒_400(self) -> None:
        status, _, body = _request(
            self.url + "api/decision", method="POST",
            payload={"approval_id": "ap-1", "decision": "approve", "argv": ["rm", "-rf", "/"]},
            cookie=self._cookie(),
        )
        self.assertEqual(status, 400)
        self.assertIn("未知字段", json.loads(body)["error"])

    def test_错误_Content_Type_被拒(self) -> None:
        status, _, _ = _request(
            self.url + "api/decision", method="POST",
            payload={"approval_id": "ap-1", "decision": "approve"},
            cookie=self._cookie(), content_type="text/plain",
        )
        self.assertEqual(status, 400)

    def test_端到端放行(self) -> None:
        cookie = self._cookie()
        item = self.server.registry.add(ApprovalRequest(
            tool="run_command", arguments={"argv": ["x"]}, reason="不在白名单",
            opclass="managed_write", workspace=str(Path.cwd())))
        status, _, body = _request(
            self.url + "api/decision", method="POST",
            payload={"approval_id": item.approval_id, "decision": "approve"},
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["decision"], "approve")
        self.assertTrue(item.event.wait(1.0))
        self.assertTrue(item.granted)

    def test_静态资源可访问(self) -> None:
        for path, ctype in (("static/app.js", "text/javascript"), ("static/style.css", "text/css")):
            status, headers, body = _request(self.url + path)
            self.assertEqual(status, 200, path)
            self.assertIn(ctype, headers.get("Content-Type", ""))
            self.assertTrue(body.strip())


class TestStaticBoundaries(unittest.TestCase):
    """不需要起服务的静态约束。"""

    def test_不做状态第二写入者(self) -> None:
        """webui.py 不得 import 控制面/契约/证据等会写工单的模块。"""
        source = (REPO_ROOT / "src" / "icode" / "webui.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = {
            "icode.control", "icode.contracts", "icode.handshake",
            "icode.evidence", "icode.runner", "icode.recovery", "icode.checkpoint",
        }
        self.assertEqual(imported & forbidden, set(), f"WebUI 不得触碰工单状态：{imported & forbidden}")

    def test_资源无_CDN_无外部引用(self) -> None:
        for name in ("index.html", "app.js", "style.css"):
            text = (ASSETS_DIR / name).read_text(encoding="utf-8")
            self.assertNotIn("http://", text, name)
            self.assertNotIn("https://", text, name)
            self.assertNotIn("cdn.", text, name)

    def test_无内联脚本(self) -> None:
        html = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
        for tag in re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.S):
            self.assertEqual(tag.strip(), "", "不允许内联脚本")
        self.assertIn('src="/static/app.js"', html)

    def test_前端不使用_innerHTML(self) -> None:
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        # 检查真实用法（去掉注释后再查 `.innerHTML` 调用）
        code = "\n".join(
            line for line in js.splitlines() if not line.strip().startswith("//")
        )
        self.assertNotIn(".innerHTML", code, "不得使用 innerHTML（避免注入）")
        self.assertIn("textContent", code)

    def test_前端只提交审批字段(self) -> None:
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn("approval_id", js)
        self.assertIn("decision", js)
        for bad in ("argv", "shell", "path:"):
            self.assertNotIn(bad, js, f"前端不应涉及 {bad}")


if __name__ == "__main__":
    unittest.main()
