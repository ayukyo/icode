"""单工程本地工单工作台。

该服务只监听 loopback。浏览器提交结构化业务意图；可信工作区路径在服务端启动时
绑定，所有工单写入仍由 :class:`icode.control.ControlPlane` 完成。
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .autonomy import AutonomyError, AutonomyManager, Executor
from .config import Settings
from .control import ControlError
from .tickets import TicketError, TicketService
from .workspace import WorkspaceManager, default_data_root

LOOPBACK_HOST = "127.0.0.1"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
SESSION_COOKIE = "icode_workbench_session"
MAX_BODY_BYTES = 64 * 1024
MAX_REJECTED_BODY_DRAIN_BYTES = MAX_BODY_BYTES * 2
REJECTED_BODY_DRAIN_TIMEOUT_SECONDS = 0.25
REJECTED_BODY_DRAIN_CHUNK_BYTES = 8 * 1024
ASSETS_DIR = Path(__file__).resolve().parent / "workbench_assets"
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
_TICKET_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,140}$")
_INTENT_PREFIX = "/api/v1/tickets/"
_INTENT_SUFFIX = "/intents"
_PUBLIC_INTENTS = ["start", "pause", "resume", "cancel", "takeover"]
_ISOLATION_LEVELS = frozenset({
    "enforced", "application_only", "not_configured", "policy_unavailable",
})


class WorkbenchHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        service: TicketService,
        autonomy: AutonomyManager,
        autonomy_capability: dict[str, Any],
    ) -> None:
        self.service = service
        self.autonomy = autonomy
        self.autonomy_capability = autonomy_capability
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

    def _drain_rejected_body(self, length: int) -> None:
        """有界丢弃小幅超限请求，避免未读数据导致 Windows 关闭连接时丢失 413。"""
        if length > MAX_REJECTED_BODY_DRAIN_BYTES:
            return
        original_timeout = self.connection.gettimeout()
        deadline = time.monotonic() + REJECTED_BODY_DRAIN_TIMEOUT_SECONDS
        try:
            remaining = length
            while remaining > 0:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                self.connection.settimeout(timeout)
                try:
                    chunk = self.rfile.read1(min(remaining, REJECTED_BODY_DRAIN_CHUNK_BYTES))
                except OSError:
                    break
                if not chunk:
                    break
                remaining -= len(chunk)
        finally:
            self.connection.settimeout(original_timeout)

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
            self._drain_rejected_body(length)
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
                self._send_json(HTTPStatus.OK, {
                    "ok": True,
                    **self.server.service.snapshot(),
                    "capabilities": {
                        "autonomous": self.server.autonomy_capability,
                    },
                })
                return
            if path == "/api/v1/tickets":
                query = parse_qs(parsed.query, keep_blank_values=False)
                result = self.server.service.snapshot(query=(query.get("query") or [None])[0])
                self._send_json(HTTPStatus.OK, {
                    "ok": True,
                    **result,
                    "capabilities": {
                        "autonomous": self.server.autonomy_capability,
                    },
                })
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
        is_create = path == "/api/v1/tickets"
        is_intent = path.startswith(_INTENT_PREFIX) and path.endswith(_INTENT_SUFFIX)
        if not is_create and not is_intent:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "路径不存在")
            return
        if not self._api_access(write=True):
            return
        try:
            payload = self._read_json()
            if is_create:
                result = self.server.service.create_ticket(payload)
            else:
                raw_ticket_id = path[len(_INTENT_PREFIX):-len(_INTENT_SUFFIX)]
                ticket_id = unquote(raw_ticket_id)
                if (
                    not ticket_id
                    or "/" in ticket_id
                    or "\\" in ticket_id
                    or _TICKET_ID_RE.fullmatch(ticket_id) is None
                ):
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid_ticket_id",
                        "ticket_id 非法",
                    )
                    return
                ticket = self.server.autonomy.handle_intent(ticket_id, payload)
                self._send_json(HTTPStatus.ACCEPTED, {"ok": True, "ticket": ticket})
                return
        except RequestTooLarge as exc:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large", str(exc))
            return
        except TicketError as exc:
            status = HTTPStatus.UNSUPPORTED_MEDIA_TYPE \
                if "Content-Type" in str(exc) else HTTPStatus.BAD_REQUEST
            self._error(status, "invalid_request", str(exc))
            return
        except AutonomyError as exc:
            status = {
                "invalid_intent": HTTPStatus.BAD_REQUEST,
                "ticket_not_found": HTTPStatus.NOT_FOUND,
                "manager_shutdown": HTTPStatus.SERVICE_UNAVAILABLE,
            }.get(exc.code, HTTPStatus.CONFLICT)
            self._error(status, exc.code, str(exc))
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
        enable_autonomous: bool = False,
        autonomy_executor: Executor | None = None,
        autonomy_limits: dict[str, Any] | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 0 <= port <= 65535
        ):
            raise ValueError("port 必须是 0..65535 的整数")
        self.service = TicketService(
            settings,
            workspace=workspace,
            index_path=index_path,
        )
        if (
            workspace_manager is None
            and enable_autonomous
            and autonomy_executor is not None
        ):
            protected_paths = [settings.skill_root]
            vendored_skill = self.service.workspace / "vendor" / "icode-skill"
            if vendored_skill.exists():
                protected_paths.append(vendored_skill)
            workspace_manager = WorkspaceManager(
                self.service.workspace,
                default_data_root(),
                self.service.project_id,
                extra_protected_paths=tuple(protected_paths),
            )
        self.autonomy = AutonomyManager(
            self.service,
            executor=autonomy_executor,
            enabled=enable_autonomous,
            workspace_manager=workspace_manager,
        )
        limits = self._safe_autonomy_limits(autonomy_limits)
        self.autonomy_capability = {
            "enabled": self.autonomy.enabled,
            "pause_semantics": "contract_step_boundary",
            "intents": list(_PUBLIC_INTENTS),
            "limits": limits,
        }
        self.httpd = WorkbenchHTTPServer(
            (LOOPBACK_HOST, port),
            self.service,
            self.autonomy,
            self.autonomy_capability,
        )
        self.thread: threading.Thread | None = None

    @staticmethod
    def _safe_autonomy_limits(raw: dict[str, Any] | None) -> dict[str, Any]:
        raw = raw if isinstance(raw, dict) else {}
        max_turns = raw.get("max_turns", 0)
        if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns < 0:
            max_turns = 0
        budget_tokens = raw.get("budget_tokens", 0)
        if (
            isinstance(budget_tokens, bool)
            or not isinstance(budget_tokens, int)
            or budget_tokens < 0
        ):
            budget_tokens = 0
        isolation_level = raw.get("isolation_level", "not_configured")
        if isolation_level not in _ISOLATION_LEVELS:
            isolation_level = "not_configured"
        return {
            "max_turns": max_turns,
            "budget_tokens": budget_tokens,
            "isolation_level": isolation_level,
        }

    @property
    def url(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.httpd.server_address[1]}/"

    def start(self) -> str:
        if self.thread is None:
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
        return self.url

    def stop(self) -> None:
        thread = self.thread
        try:
            if thread is not None:
                try:
                    self.httpd.shutdown()
                finally:
                    try:
                        self.autonomy.shutdown(timeout=2.0)
                    finally:
                        try:
                            thread.join(timeout=5)
                        finally:
                            self.thread = None
            else:
                self.autonomy.shutdown(timeout=2.0)
        finally:
            self.httpd.server_close()
