"""单工程本地工单工作台。

该服务只监听 loopback。浏览器提交结构化业务意图；可信工作区路径在服务端启动时
绑定，所有工单写入仍由 :class:`icode.control.ControlPlane` 完成。
"""

from __future__ import annotations

import json
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .config import Settings
from .control import ControlError
from .tickets import TicketError, TicketService

LOOPBACK_HOST = "127.0.0.1"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SESSION_COOKIE = "icode_workbench_session"
MAX_BODY_BYTES = 64 * 1024
ASSETS_DIR = Path(__file__).resolve().parent / "workbench_assets"
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


class WorkbenchHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], service: TicketService) -> None:
        self.service = service
        self.session_token = secrets.token_urlsafe(32)
        super().__init__(address, WorkbenchRequestHandler)


class RequestTooLarge(TicketError):
    """请求体超过工作台允许的固定上限。"""


class WorkbenchRequestHandler(BaseHTTPRequestHandler):
    server: WorkbenchHTTPServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"ok": False, "code": code, "message": message})

    def _host_ok(self) -> bool:
        raw = (self.headers.get("Host") or "").strip()
        if raw.startswith("["):
            host = raw[1:].split("]", 1)[0]
        else:
            host = raw.split(":", 1)[0]
        if host not in ALLOWED_HOSTS:
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "仅允许本机访问")
            return False
        return True

    def _cookie_ok(self) -> bool:
        cookies = self.headers.get("Cookie") or ""
        expected = f"{SESSION_COOKIE}={self.server.session_token}"
        return expected in {item.strip() for item in cookies.split(";")}

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        return parsed.scheme == "http" and parsed.hostname in ALLOWED_HOSTS

    def _api_access(self, *, write: bool = False) -> bool:
        if not self._cookie_ok():
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "会话无效，请刷新页面")
            return False
        if write and not self._origin_ok():
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "拒绝跨源写请求")
            return False
        return True

    def _read_json(self) -> object:
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise TicketError("Content-Type 必须是 application/json")
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError as exc:
            raise TicketError("Content-Length 非法") from exc
        if length <= 0:
            raise TicketError("请求体不能为空")
        if length > MAX_BODY_BYTES:
            raise RequestTooLarge(f"请求体不能超过 {MAX_BODY_BYTES} 字节")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TicketError("请求体不是合法 JSON") from exc

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            try:
                body = (ASSETS_DIR / "index.html").read_bytes()
            except OSError:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "asset_unavailable", "工作台资源不可用")
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}={self.server.session_token}; Path=/; HttpOnly; SameSite=Strict",
            )
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)
            return
        assets = {
            "/static/workbench.js": ("app.js", "text/javascript; charset=utf-8"),
            "/static/workbench.css": ("style.css", "text/css; charset=utf-8"),
        }
        if path in assets:
            name, content_type = assets[path]
            try:
                body = (ASSETS_DIR / name).read_bytes()
            except OSError:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "asset_unavailable", "工作台资源不可用")
                return
            self._send_bytes(HTTPStatus.OK, body, content_type)
            return
        if path == "/api/v1/health":
            self._send_json(HTTPStatus.OK, {
                "ok": True,
                "service": "icode-workbench",
                "schema_version": 1,
            })
            return
        if not path.startswith("/api/v1/"):
            self._error(HTTPStatus.NOT_FOUND, "not_found", "路径不存在")
            return
        if not self._api_access():
            return
        try:
            if path == "/api/v1/bootstrap":
                self._send_json(HTTPStatus.OK, {"ok": True, **self.server.service.snapshot()})
                return
            if path == "/api/v1/tickets":
                query = parse_qs(parsed.query, keep_blank_values=False)
                result = self.server.service.snapshot(query=(query.get("query") or [None])[0])
                self._send_json(HTTPStatus.OK, {"ok": True, **result})
                return
            if path.startswith("/api/v1/tickets/"):
                ticket_id = unquote(path.removeprefix("/api/v1/tickets/"))
                if not ticket_id or "/" in ticket_id:
                    raise TicketError("ticket_id 非法")
                ticket = self.server.service.ticket_detail(ticket_id)
                self._send_json(HTTPStatus.OK, {"ok": True, "ticket": ticket})
                return
        except TicketError:
            self._error(HTTPStatus.NOT_FOUND, "ticket_unavailable", "工单不存在或当前不可读取")
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "路径不存在")

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            return
        path = urlsplit(self.path).path
        if path != "/api/v1/tickets":
            self._error(HTTPStatus.NOT_FOUND, "not_found", "路径不存在")
            return
        if not self._api_access(write=True):
            return
        try:
            payload = self._read_json()
            result = self.server.service.create_ticket(payload)
        except RequestTooLarge as exc:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large", str(exc))
            return
        except TicketError as exc:
            status = HTTPStatus.UNSUPPORTED_MEDIA_TYPE \
                if "Content-Type" in str(exc) else HTTPStatus.BAD_REQUEST
            self._error(status, "invalid_request", str(exc))
            return
        except ControlError:
            self._error(HTTPStatus.CONFLICT, "control_rejected", "控制面拒绝创建或更新工单")
            return
        status = HTTPStatus.OK if result["already_applied"] else HTTPStatus.CREATED
        self._send_json(status, result)


class WorkbenchServer:
    """可测试的后台线程包装。"""

    def __init__(
        self,
        *,
        settings: Settings,
        workspace: Path | str,
        port: int = 0,
        index_path: Path | str | None = None,
    ) -> None:
        if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
            raise ValueError("port 必须是 0..65535 的整数")
        self.service = TicketService(
            settings,
            workspace=workspace,
            index_path=index_path,
        )
        self.httpd = WorkbenchHTTPServer((LOOPBACK_HOST, port), self.service)
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.httpd.server_address[1]}/"

    def start(self) -> str:
        if self.thread is None:
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
        return self.url

    def stop(self) -> None:
        if self.thread is not None:
            self.httpd.shutdown()
            self.thread.join(timeout=5)
            self.thread = None
        self.httpd.server_close()
