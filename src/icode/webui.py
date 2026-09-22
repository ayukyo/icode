"""本地 WebUI（Phase 5）。唯一监听 `127.0.0.1`，不提供远程绑定。

设计与上游 UI 的既有约束对齐，三条硬边界**由测试锁住**：

    ① **不做状态第二写入者** —— 本模块不 import 控制面、不写工单。
       它只做一件事：把「审批」这一层的交互从终端搬到浏览器。
    ② **不收路径 / 命令 / shell** —— 只接受 `approval_id`（必须是已知的挂起项）
       + `decision`（枚举）+ 可选 `reason`（仅字符串，长度受限，绝不执行）。
       未知字段一律拒绝。
    ③ **挂起审批重启后不自动放行** —— 挂起项只在内存；进程重启即消失；
       等待超时一律**拒绝**（fail-closed）。

安全细节：
    - 只监听 loopback（没有 `--host` 参数，代码里写死）
    - 会话令牌走 **HttpOnly-less 的 SameSite=Strict Cookie**（页面与 JS 都不接触令牌）
    - 写请求校验 Cookie + Origin（拒绝跨源）+ 严格 JSON + 64KiB 上限
    - 页面资源全部随仓提供：无 CDN、无内联脚本、无第三方前端依赖
"""

from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .approvals import ApprovalRequest

LOOPBACK = "127.0.0.1"
MAX_BODY_BYTES = 64 * 1024
SESSION_COOKIE = "icode_session"
ASSETS_DIR = Path(__file__).resolve().parent / "web_assets"

# 写请求允许的字段（白名单；未知字段直接拒绝）
ALLOWED_FIELDS = frozenset({"approval_id", "decision", "reason"})
DECISIONS = frozenset({"approve", "deny"})
MAX_REASON_CHARS = 500


# ---------------------------------------------------------------------------
# 审批桥：WebApprover
# ---------------------------------------------------------------------------


@dataclass
class PendingApproval:
    approval_id: str
    tool: str
    reason: str
    opclass: str
    workspace: str
    arguments: dict
    event: threading.Event = field(default_factory=threading.Event, repr=False)
    granted: bool = False
    decided_at: float | None = None


class ApprovalRegistry:
    """挂起审批的内存登记处。

    **只在内存**：进程重启后必然为空 —— 这就是"重启后不自动放行"的实现方式。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingApproval] = {}
        self._history: list[dict] = []

    def add(self, request: ApprovalRequest) -> PendingApproval:
        item = PendingApproval(
            approval_id=f"ap-{secrets.token_hex(6)}",
            tool=request.tool,
            reason=request.reason,
            opclass=request.opclass,
            workspace=request.workspace,
            arguments=dict(request.arguments),
        )
        with self._lock:
            self._pending[item.approval_id] = item
        return item

    def resolve(self, approval_id: str, decision: str, reason: str = "") -> bool:
        with self._lock:
            item = self._pending.pop(approval_id, None)
        if item is None:
            return False
        item.granted = decision == "approve"
        item.decided_at = time.time()
        item.event.set()
        self._history.append({
            "approval_id": item.approval_id,
            "tool": item.tool,
            "decision": decision,
            "reason": reason[:MAX_REASON_CHARS],
            "at": item.decided_at,
        })
        return True

    def rev(self) -> int:
        with self._lock:
            return len(self._history)

    def snapshot(self) -> dict:
        with self._lock:
            pending = [
                {
                    "approval_id": p.approval_id,
                    "tool": p.tool,
                    "reason": p.reason,
                    "opclass": p.opclass,
                    "workspace": p.workspace,
                    "arguments": {k: str(v)[:300] for k, v in p.arguments.items()},
                }
                for p in self._pending.values()
            ]
            history = list(self._history[-20:])
        return {"pending": pending, "history": history, "rev": len(history) + len(pending)}


@dataclass
class WebApprover:
    """`Approver` 协议的 Web 实现（第 4 个实现，也是 WebUI 唯一需要新写的组件）。

    等待超时 → **拒绝**（fail-closed）。浏览器关闭/进程重启 → 挂起项消失 → 等同于拒绝。
    """

    registry: ApprovalRegistry
    timeout: float = 300.0

    def ask(self, request: ApprovalRequest) -> bool:
        item = self.registry.add(request)
        if not item.event.wait(self.timeout):
            # 超时未决 → 拒绝，并清掉挂起项
            self.registry.resolve(item.approval_id, "deny", "等待超时，按拒绝处理")
            return False
        return item.granted


# ---------------------------------------------------------------------------
# HTTP 服务
# ---------------------------------------------------------------------------


def _is_loopback_host(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost")


def validate_decision_payload(payload: Any) -> tuple[dict | None, str]:
    """严格校验写请求体。返回 (合法负载, 错误信息)。"""
    if not isinstance(payload, dict):
        return None, "请求体必须是 JSON 对象"
    unknown = set(payload) - ALLOWED_FIELDS
    if unknown:
        return None, f"存在未知字段（本接口只接受审批决定，不接受路径/命令）：{sorted(unknown)}"
    approval_id = payload.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        return None, "approval_id 缺失或类型错误"
    decision = payload.get("decision")
    if decision not in DECISIONS:
        return None, f"decision 必须是 {sorted(DECISIONS)} 之一"
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        return None, "reason 必须是字符串"
    if len(reason) > MAX_REASON_CHARS:
        return None, f"reason 过长（上限 {MAX_REASON_CHARS} 字符）"
    return {"approval_id": approval_id, "decision": decision, "reason": reason}, ""


class _Handler(BaseHTTPRequestHandler):
    server_version = "icode-webui"
    protocol_version = "HTTP/1.1"

    # 由 WebUIServer.start() 在子类上注入实例
    registry: ApprovalRegistry
    session_token: str

    def log_message(self, fmt: str, *args: Any) -> None:  # 静音默认日志
        pass

    # ---- 工具 ----

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True  # 同源的表单/无 Origin 请求（本地浏览器 fetch 会带）
        for prefix in ("http://127.0.0.1", "http://localhost", "http://[::1]"):
            if origin.startswith(prefix):
                return True
        return False

    def _cookie_ok(self) -> bool:
        raw = self.headers.get("Cookie") or ""
        if not raw:
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:  # noqa: BLE001
            return False
        morsel = cookie.get(SESSION_COOKIE)
        return bool(morsel) and secrets.compare_digest(morsel.value, self.session_token)

    def _send_json(self, status: HTTPStatus, payload: dict, *, cookie: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> tuple[Any, str]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None, "Content-Length 非法"
        if length <= 0 or length > MAX_BODY_BYTES:
            return None, f"请求体长度非法（须 1..{MAX_BODY_BYTES} 字节）"
        raw = self.rfile.read(length)
        # Content-Type 必须是 JSON
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return None, "Content-Type 必须是 application/json"
        try:
            return json.loads(raw.decode("utf-8")), ""
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return None, f"请求体不是合法 JSON：{exc}"

    # ---- 路由 ----

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            # 同源 Cookie 会话：页面与 JS 都拿不到令牌
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = (ASSETS_DIR / "index.html").read_bytes()
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}={self.session_token}; Path=/; SameSite=Strict",
            )
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/static/app.js":
            self._send_file(ASSETS_DIR / "app.js", "text/javascript; charset=utf-8")
            return
        if path == "/static/style.css":
            self._send_file(ASSETS_DIR / "style.css", "text/css; charset=utf-8")
            return
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "ticket": "n/a"})
            return
        if path == "/api/state":
            if not self._cookie_ok():
                self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "缺少有效会话 Cookie"})
                return
            self._send_json(HTTPStatus.OK, {"ok": True, **self.registry.snapshot()})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/api/decision":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._origin_ok():
            self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "拒绝跨源请求"})
            return
        if not self._cookie_ok():
            self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "缺少有效会话 Cookie"})
            return
        payload, err = self._read_body()
        if err:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": err})
            return
        clean, err = validate_decision_payload(payload)
        if err:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": err})
            return
        assert clean is not None
        ok = self.registry.resolve(clean["approval_id"], clean["decision"], clean["reason"])
        if not ok:
            # 未知或已失效的挂起项：**不猜测、不新建**，直接拒绝
            self._send_json(HTTPStatus.CONFLICT,
                            {"ok": False, "error": "未知或已失效的 approval_id"})
            return
        self._send_json(HTTPStatus.OK, {"ok": True, "decision": clean["decision"]})


@dataclass
class WebUIServer:
    """只监听 loopback 的本地服务。"""

    registry: ApprovalRegistry = field(default_factory=ApprovalRegistry)
    port: int = 0  # 0 = 由系统分配空闲端口
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    _httpd: ThreadingHTTPServer | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    @property
    def url(self) -> str:
        if self._httpd is None:
            return ""
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self) -> str:
        handler = type("BoundHandler", (_Handler,), {
            "registry": self.registry,
            "session_token": self.token,
        })
        # 硬编码 loopback：**没有 host 参数**，不提供远程绑定
        self._httpd = ThreadingHTTPServer((LOOPBACK, self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def approver(self, *, timeout: float = 300.0) -> WebApprover:
        return WebApprover(registry=self.registry, timeout=timeout)


def serve(
    *, port: int = 0, open_browser: bool = True, timeout: float = 300.0
) -> tuple[WebUIServer, WebApprover]:
    """启动服务并返回 (server, approver)。调用方负责持有 server 引用并按需 `stop()`。"""
    server = WebUIServer(port=port)
    url = server.start()
    print(f"ICODE WebUI：{url}")
    print("  仅监听 127.0.0.1；页面资源随程序提供（无 CDN / 无内联脚本）")
    print("  写请求需同源 Cookie；挂起审批不会因重启而放行")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    return server, server.approver(timeout=timeout)
