"""MCP 工具接入客户端（R5/W3）。

标准库实现的 stdio JSON-RPC 客户端。安全姿态：

- 客户端→服务端只发三个方法：``initialize`` / ``tools/list`` / ``tools/call``
  （外加紧随 initialize 的 ``notifications/initialized`` 通知）。
- **白名单只是必要条件；强制执行在消息分发层**：每个入站帧过同一判定——
  服务端发起的请求（带 ``method``）一律以 ``-32601`` 回绝并留审计；普通通知
  忽略并留审计；JSON-RPC batch 帧整体拒绝（``batch_not_supported``），会话
  视为不可信；响应 id 不匹配即协议错误。
- 有界：单帧字节上限、读超时、结果文本上限、工具清单条数上限；超限即失败封闭。
- 客户端没有任何文件读写能力；服务端借 ``content`` 回灌的"指令文本"只是数据，
  不构成执行——要行动必须另经 Tool 治理链（Guard→Approver→副作用回执）。
"""

from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..extension_contract import OPCLASSES
from ..tools.base import (
    DEFAULT_OUTPUT_LIMIT,
    OPCLASS_EXTERNAL,
    Tool,
    ToolResult,
)

_CLIENT_METHODS = frozenset({"initialize", "tools/list", "tools/call"})
_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "icode", "version": "1"}
_MAX_LINE_BYTES = 1 << 20
_MAX_TOOLS = 256
_MAX_REFUSALS = 16
_DEFAULT_TIMEOUT = 30.0
_CLOSE_GRACE = 2.0
_READ_BLOCK = 65536

_SERVER_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_TOOL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class McpClientError(RuntimeError):
    """MCP 会话错误；``code`` 稳定，供测试与审计断言。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class McpToolDescription:
    """服务端声明的一个工具（已经过有界校验）。"""

    name: str
    description: str = ""
    input_schema: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class McpToolResult:
    """一次 tools/call 的有界结果。"""

    ok: bool
    text: str
    truncated: bool


class _FrameReader(threading.Thread):
    """跨平台有界读帧：后台线程按字节上限切行，主线程按超时取帧。"""

    def __init__(self, stream: Any, max_line_bytes: int) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._max_line_bytes = max_line_bytes
        self.frames: queue.Queue = queue.Queue()
        self.error: McpClientError | None = None

    def run(self) -> None:
        buffer = b""
        try:
            while True:
                chunk = self._read_block()
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if line:
                        self.frames.put(line)
                if len(buffer) > self._max_line_bytes:
                    raise McpClientError("oversize_response", "单帧超过字节上限")
        except McpClientError as error:
            self.error = error
        except Exception as error:  # noqa: BLE001 - 传输异常统一收敛为稳定码
            self.error = McpClientError("transport_error", type(error).__name__)
        finally:
            self.frames.put(None)

    def _read_block(self) -> bytes:
        # read(n) 会阻塞到凑满 n 字节；read1 最多一次底层读、立即返回。
        reader = getattr(self._stream, "read1", None)
        if reader is not None:
            return reader(_READ_BLOCK)
        return self._stream.read(_READ_BLOCK)


class McpClient:
    """一个 MCP 服务端进程的标准库客户端；生命周期即会话边界。"""

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
        max_line_bytes: int = _MAX_LINE_BYTES,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        if not isinstance(command, (list, tuple)) or not command:
            raise McpClientError("bad_command", "command 必须为非空参数序列")
        if any(not isinstance(item, str) or not item for item in command):
            raise McpClientError("bad_command", "command 只接受非空字符串参数")
        if timeout_seconds <= 0 or max_line_bytes <= 0:
            raise McpClientError("bad_command", "超时与字节上限必须为正")
        self.command = list(command)
        self._timeout = float(timeout_seconds)
        self._max_line_bytes = int(max_line_bytes)
        self._env = dict(env) if env is not None else None
        self._cwd = cwd
        self._proc: subprocess.Popen | None = None
        self._reader: _FrameReader | None = None
        self._next_id = 0
        self._server_info: dict[str, Any] = {}
        self.refusals: list[dict[str, Any]] = []

    # ---- 生命周期 ----

    def start(self) -> "McpClient":
        if self._proc is not None:
            raise McpClientError("already_started", "会话已启动")
        try:
            self._proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                env=self._env,
            )
        except Exception as error:  # noqa: BLE001 - 启动失败只给稳定码
            raise McpClientError("spawn_failed", type(error).__name__) from error
        self._reader = _FrameReader(self._proc.stdout, self._max_line_bytes)
        self._reader.start()
        return self

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def close(self) -> None:
        proc, self._proc = self._proc, None
        reader, self._reader = self._reader, None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except Exception:  # noqa: BLE001 - 关闭失败不影响后续回收
            pass
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            proc.wait(timeout=_CLOSE_GRACE)
        except Exception:  # noqa: BLE001
            try:
                proc.terminate()
                proc.wait(timeout=_CLOSE_GRACE)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if reader is not None:
            reader.join(timeout=1.0)

    def __enter__(self) -> "McpClient":
        if self._proc is None:
            self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ---- 出站 ----

    def _send_raw(self, frame: Mapping[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise McpClientError("transport_closed", "会话未启动")
        if self._proc.poll() is not None:
            raise McpClientError("transport_closed", "服务端进程已退出")
        line = json.dumps(frame, ensure_ascii=False) + "\n"
        try:
            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()
        except Exception as error:  # noqa: BLE001
            raise McpClientError("transport_closed", "写入失败") from error

    def _send(self, method: str, params: Mapping[str, Any]) -> int:
        if method not in _CLIENT_METHODS:
            raise McpClientError("client_method_refused", f"客户端不发送 {method}")
        self._next_id += 1
        self._send_raw({"jsonrpc": "2.0", "id": self._next_id, "method": method,
                        "params": params})
        return self._next_id

    # ---- 入站分发（强制点） ----

    def _record_refusal(self, method: str, *, had_id: bool) -> None:
        if len(self.refusals) < _MAX_REFUSALS:
            self.refusals.append({"method": method[:64], "had_id": had_id})

    def _dispatch(self, line: bytes) -> Mapping[str, Any] | None:
        """返回待匹配的响应帧；服务端推送一律拒付或忽略（返回 None）。"""
        try:
            frame = json.loads(line.decode("utf-8"))
        except Exception as error:  # noqa: BLE001
            raise McpClientError("protocol_error", "帧不是合法 JSON") from error
        if isinstance(frame, list):
            self._record_refusal("batch", had_id=False)
            raise McpClientError("batch_not_supported", "拒绝 JSON-RPC batch 帧")
        if not isinstance(frame, dict) or frame.get("jsonrpc") != "2.0":
            raise McpClientError("protocol_error", "帧不是 JSON-RPC 2.0 对象")
        if "method" in frame:
            method = frame.get("method")
            self._record_refusal(str(method)[:64], had_id=isinstance(frame.get("id"), int))
            if isinstance(frame.get("id"), int):
                self._send_raw({
                    "jsonrpc": "2.0", "id": frame["id"],
                    "error": {"code": -32601,
                              "message": "method not supported by this client"},
                })
            return None
        if "id" not in frame:
            raise McpClientError("protocol_error", "帧既无 method 也无 id")
        return frame

    def _request(self, method: str, params: Mapping[str, Any],
                 timeout: float | None) -> dict[str, Any]:
        if self._proc is None or self._reader is None:
            raise McpClientError("not_started", "会话未启动")
        limit = self._timeout if timeout is None else float(timeout)
        request_id = self._send(method, params)
        deadline = time.monotonic() + limit
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpClientError("timeout", f"{method} 响应超时")
            try:
                line = self._reader.frames.get(timeout=remaining)
            except queue.Empty:
                raise McpClientError("timeout", f"{method} 响应超时") from None
            if line is None:
                if self._reader.error is not None:
                    raise self._reader.error
                raise McpClientError("transport_closed", "服务端关闭了输出")
            frame = self._dispatch(line)
            if frame is None:
                continue
            if frame.get("id") != request_id:
                raise McpClientError("protocol_error", "响应 id 不匹配")
            error = frame.get("error")
            if error is not None:
                code = error.get("code") if isinstance(error, dict) else None
                message = str(error.get("message") if isinstance(error, dict) else error)
                raise McpClientError("remote_error", f"{code} {message[:200]}")
            result = frame.get("result")
            if not isinstance(result, dict):
                raise McpClientError("protocol_error", "result 必须是对象")
            return result

    # ---- 协议方法 ----

    def initialize(self, *, timeout: float | None = None) -> dict[str, Any]:
        result = self._request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": dict(_CLIENT_INFO),
        }, timeout)
        self._send_raw({"jsonrpc": "2.0", "method": "notifications/initialized"})
        server_info = result.get("serverInfo")
        if isinstance(server_info, dict):
            self._server_info = {
                "name": str(server_info.get("name") or "")[:64],
                "version": str(server_info.get("version") or "")[:32],
            }
        return result

    @property
    def server_info(self) -> dict[str, str]:
        return dict(self._server_info)

    def list_tools(self, *, timeout: float | None = None) -> tuple[McpToolDescription, ...]:
        result = self._request("tools/list", {}, timeout)
        tools = result.get("tools")
        if not isinstance(tools, list) or len(tools) > _MAX_TOOLS:
            raise McpClientError("protocol_error", "tools 清单非法或超限")
        described: list[McpToolDescription] = []
        for entry in tools:
            if not isinstance(entry, dict):
                raise McpClientError("protocol_error", "工具条目必须是对象")
            name = entry.get("name")
            if not isinstance(name, str) or _SERVER_TOOL_NAME_RE.match(name) is None:
                raise McpClientError("protocol_error", "服务端工具名非法")
            schema = entry.get("inputSchema")
            if schema is not None and not isinstance(schema, dict):
                raise McpClientError("protocol_error", "inputSchema 必须是对象")
            described.append(McpToolDescription(
                name=name,
                description=str(entry.get("description") or "")[:2000],
                input_schema=schema,
            ))
        return tuple(described)

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
        max_result_chars: int = DEFAULT_OUTPUT_LIMIT,
    ) -> McpToolResult:
        if not isinstance(name, str) or not name:
            raise McpClientError("bad_arguments", "工具名必须为非空字符串")
        payload = dict(arguments) if isinstance(arguments, Mapping) else {}
        result = self._request("tools/call", {"name": name, "arguments": payload}, timeout)
        texts: list[str] = []
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        texts.append(text)
        joined = "\n".join(texts)
        truncated = len(joined) > max_result_chars
        return McpToolResult(
            ok=result.get("isError") is not True,
            text=joined[:max_result_chars],
            truncated=truncated,
        )


def mcp_tool_to_tool(
    description: McpToolDescription,
    client: McpClient,
    *,
    opclass: str = OPCLASS_EXTERNAL,
    name_prefix: str = "mcp_",
    max_result_chars: int = DEFAULT_OUTPUT_LIMIT,
) -> Tool:
    """把 MCP 工具包装为内建同型的 ``Tool``，经 ToolRegistry 进入同一治理链。

    handler 只做一次远程调用并返回**有界文本**；会话不可用或参数不匹配时
    失败封闭，绝不本地降级执行。远程工具的真实副作用由 manifest 的 opclass
    驱动回执链，本地 Guard 裁决对包装后的 Tool 一视同仁。
    """
    if not isinstance(description, McpToolDescription):
        raise ValueError("mcp_tool_adapter: 需要 McpToolDescription")
    if not isinstance(client, McpClient):
        raise ValueError("mcp_tool_adapter: 需要 McpClient")
    if opclass not in OPCLASSES:
        raise ValueError(f"mcp_tool_adapter: 未知 opclass {opclass!r}")
    tool_name = f"{name_prefix}{description.name}"
    if _TOOL_NAME_RE.match(tool_name) is None:
        raise ValueError("mcp_tool_adapter: 包装后的工具名非法")

    def handler(ctx: Any, **arguments: Any) -> ToolResult:
        if not client.alive:
            return ToolResult(False, "MCP 会话不可用，已拒绝执行",
                              {"error": "mcp_session_unavailable"}, opclass=opclass)
        try:
            result = client.call_tool(
                description.name, arguments, max_result_chars=max_result_chars,
            )
        except TypeError:
            return ToolResult(False, "MCP 工具参数不匹配",
                              {"error": "mcp_bad_arguments"}, opclass=opclass)
        except McpClientError as error:
            return ToolResult(False, "MCP 调用失败，未执行任何本地动作",
                              {"error": "mcp_call_failed", "code": error.code},
                              opclass=opclass)
        meta: dict[str, Any] = {"tool": description.name, "truncated": result.truncated}
        if not result.ok:
            meta["error"] = "mcp_tool_error"
        content = result.text if result.text else ("（空结果）" if result.ok else "MCP 工具报错")
        return ToolResult(result.ok, content, meta, opclass=opclass)

    schema = dict(description.input_schema) if description.input_schema else {
        "type": "object", "properties": {},
    }
    return Tool(
        name=tool_name,
        description=f"[MCP] {description.description}".strip()[:500],
        parameters=schema,
        handler=handler,
        opclass=opclass,
    )
