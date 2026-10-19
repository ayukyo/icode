"""ACP/IDE 交互前端：只承载交互，不接管 Agent 循环（R5/W4）。

边界（对应 §13.9 退出门槛第 2 条）：

- 方法白名单封闭：只有 ``submit_intent`` / ``read_ticket`` /
  ``subscribe_events`` / ``unsubscribe_events`` / ``list_methods``。
  没有启动/停止/暂停循环的方法，也没有调用工具处理器的方法。
- **不得成为第二 intent 入口**：``submit_intent`` 原样转发给控制面既有入口
  （``AutonomyManager.handle_intent``，其内部经 ``normalize_intent_payload``
  同一词表校验）。本模块不定义、不解析任何 intent 语义。
- 会话只读控制面公开投影（``TicketService.ticket_detail``），不写账本、
  不碰文件系统；事件流只转发订阅白名单内的公开事件名。
- 有界：单帧字节上限、事件外发箱上限；超限即失败封闭。
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, IO, Mapping

ACP_METHODS = (
    "submit_intent", "read_ticket", "subscribe_events",
    "unsubscribe_events", "list_methods",
)

# 可订阅事件白名单：AgentLoop on_event 的公开子集。
SUBSCRIBABLE_EVENTS = frozenset({
    "tool_denied", "approval_requested", "approval_denied", "tool_start",
    "tool_result", "assistant", "tool_skipped_budget", "operation_ambiguous",
    "operation_finish_failed", "context_compacted",
})

_MAX_FRAME_BYTES = 262_144
_MAX_EVENT_PAYLOAD = 65_536
_OUTBOX_LIMIT = 64
_MAX_TICKET_TEXT = 256


class AcpError(RuntimeError):
    """ACP 会话错误；``code`` 稳定。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass
class AcpController:
    """既有控制面入口的适配面（方法名即契约，不含任何新能力）。"""

    handle_intent: Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
    read_ticket: Callable[[str], Mapping[str, Any]]


def controller_from_autonomy(manager: Any, service: Any) -> AcpController:
    """生产接线：ACP 只包住既有 autonomy 入口与公开投影，不新增路径。"""
    if not callable(getattr(manager, "handle_intent", None)):
        raise AcpError("acp_controller_shape", "manager 缺少 handle_intent")
    if not callable(getattr(service, "ticket_detail", None)):
        raise AcpError("acp_controller_shape", "service 缺少 ticket_detail")
    return AcpController(
        handle_intent=lambda ticket_id, payload: manager.handle_intent(ticket_id, payload),
        read_ticket=lambda ticket_id: service.ticket_detail(ticket_id),
    )


def _error_frame(frame_id: Any, code: int, message: str, data_code: str) -> dict:
    return {
        "jsonrpc": "2.0", "id": frame_id,
        "error": {"code": code, "message": message, "data": {"code": data_code}},
    }


@dataclass
class AcpSession:
    """一个 IDE 会话：封闭方法集 + 有界事件外发。"""

    controller: AcpController
    subscriptions: set[str] = field(default_factory=set)
    outbox: deque = field(default_factory=deque)
    refusals: list[dict[str, Any]] = field(default_factory=list)

    # ---- 事件（公开子集，只出不进） ----

    def on_event(self, name: str, payload: Mapping[str, Any]) -> None:
        if name not in self.subscriptions:
            return
        try:
            encoded = json.dumps(dict(payload), ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return
        if len(encoded) > _MAX_EVENT_PAYLOAD:
            self.refusals.append({"event": name[:64], "code": "event_oversize"})
            return
        if len(self.outbox) >= _OUTBOX_LIMIT:
            self.refusals.append({"event": name[:64], "code": "outbox_full"})
            return
        self.outbox.append({"jsonrpc": "2.0", "method": "event",
                            "params": {"event": name, "payload": json.loads(encoded)}})

    # ---- 方法处理 ----

    def _submit_intent(self, params: Mapping[str, Any]) -> dict[str, Any]:
        ticket_id = params.get("ticket_id")
        payload = params.get("payload")
        if not isinstance(ticket_id, str) or not ticket_id:
            raise AcpError("ticket_id_invalid", "ticket_id 必须为非空字符串")
        if not isinstance(payload, dict):
            raise AcpError("payload_invalid", "payload 必须是对象")
        # 语义校验完全交给既有入口（normalize_intent_payload 的同一词表）。
        ticket = self.controller.handle_intent(ticket_id, payload)
        return {"accepted": True, "ticket": _bounded_ticket(ticket)}

    def _read_ticket(self, params: Mapping[str, Any]) -> dict[str, Any]:
        ticket_id = params.get("ticket_id")
        if not isinstance(ticket_id, str) or not ticket_id:
            raise AcpError("ticket_id_invalid", "ticket_id 必须为非空字符串")
        return {"ticket": _bounded_ticket(self.controller.read_ticket(ticket_id))}

    def _subscribe_events(self, params: Mapping[str, Any]) -> dict[str, Any]:
        events = params.get("events")
        if not isinstance(events, list):
            raise AcpError("events_invalid", "events 必须是数组")
        accepted, refused = [], []
        for name in events:
            if not isinstance(name, str):
                refused.append(str(name)[:64])
                continue
            if name in SUBSCRIBABLE_EVENTS:
                self.subscriptions.add(name)
                accepted.append(name)
            else:
                refused.append(name[:64])
        return {"subscribed": sorted(self.subscriptions), "refused": refused}

    def _unsubscribe_events(self, params: Mapping[str, Any]) -> dict[str, Any]:
        events = params.get("events")
        if not isinstance(events, list):
            raise AcpError("events_invalid", "events 必须是数组")
        for name in events:
            if isinstance(name, str):
                self.subscriptions.discard(name)
        return {"subscribed": sorted(self.subscriptions)}

    def _list_methods(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "methods": sorted(ACP_METHODS),
            "events": sorted(SUBSCRIBABLE_EVENTS),
        }

    _HANDLERS = {
        "submit_intent": _submit_intent,
        "read_ticket": _read_ticket,
        "subscribe_events": _subscribe_events,
        "unsubscribe_events": _unsubscribe_events,
        "list_methods": _list_methods,
    }

    # ---- 帧分发 ----

    def dispatch(self, frame: bytes) -> bytes | None:
        """处理一帧；请求返回响应字节；通知只处理不响应。"""
        try:
            message = json.loads(frame.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return json.dumps(
                _error_frame(None, -32700, "Parse error", "parse_error"),
                ensure_ascii=False,
            ).encode("utf-8")
        if isinstance(message, list):
            self.refusals.append({"method": "batch", "code": "batch_not_supported"})
            return json.dumps(
                _error_frame(None, -32600, "Invalid Request", "batch_not_supported"),
                ensure_ascii=False,
            ).encode("utf-8")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return json.dumps(
                _error_frame(None, -32600, "Invalid Request", "invalid_frame"),
                ensure_ascii=False,
            ).encode("utf-8")
        method = message.get("method")
        frame_id = message.get("id")
        handler = self._HANDLERS.get(method) if isinstance(method, str) else None
        if handler is None:
            self.refusals.append({"method": str(method)[:64], "code": "method_not_supported"})
            if "id" not in message:
                return None
            return json.dumps(
                _error_frame(frame_id, -32601, "Method not found", "method_not_supported"),
                ensure_ascii=False,
            ).encode("utf-8")
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            if "id" not in message:
                return None
            return json.dumps(
                _error_frame(frame_id, -32600, "Invalid Request", "params_invalid"),
                ensure_ascii=False,
            ).encode("utf-8")
        try:
            result = handler(self, params)
        except AcpError as error:
            code = error.code
            if "id" not in message:
                return None
            return json.dumps(
                _error_frame(frame_id, -32602, "Invalid params", code),
                ensure_ascii=False,
            ).encode("utf-8")
        except Exception as error:  # noqa: BLE001 - 控制面异常不外泄正文
            # AutonomyError 等既有错误携带稳定 code；其余归一为 controller_error。
            code = str(getattr(error, "code", "") or "controller_error")[:64]
            if "id" not in message:
                return None
            return json.dumps(
                _error_frame(frame_id, -32603, "Controller error", code),
                ensure_ascii=False,
            ).encode("utf-8")
        if "id" not in message:
            return None
        return json.dumps(
            {"jsonrpc": "2.0", "id": frame_id, "result": result},
            ensure_ascii=False, default=str,
        ).encode("utf-8")

    # ---- 服务循环 ----

    def serve(self, stdin: IO[bytes], stdout: IO[bytes]) -> None:
        buffer = b""
        while True:
            reader = getattr(stdin, "read1", None)
            chunk = reader(65536) if reader is not None else stdin.read(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                if len(line) > _MAX_FRAME_BYTES:
                    stdout.write(json.dumps(_error_frame(
                        None, -32600, "Invalid Request", "frame_oversize"),
                        ensure_ascii=False,
                    ).encode("utf-8") + b"\n")
                    stdout.flush()
                    continue
                response = self.dispatch(line)
                if response is not None:
                    stdout.write(response + b"\n")
                    stdout.flush()
                while self.outbox:
                    stdout.write(json.dumps(self.outbox.popleft(),
                                            ensure_ascii=False).encode("utf-8") + b"\n")
                    stdout.flush()


def _bounded_ticket(ticket: Mapping[str, Any]) -> dict[str, Any]:
    """公开投影有界化：只保留既有投影字段，超长文本截断。"""
    if not isinstance(ticket, Mapping):
        raise AcpError("ticket_projection", "投影不是对象")
    bounded: dict[str, Any] = {}
    for key, value in ticket.items():
        if isinstance(value, str) and len(value) > _MAX_TICKET_TEXT:
            bounded[str(key)] = value[:_MAX_TICKET_TEXT] + "…"
        else:
            bounded[str(key)] = value
    return bounded
