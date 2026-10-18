"""共享的零依赖 HTTP 传输：代理策略、拒绝重定向、有界重试与延迟计量。

与 `openai_compatible` 保持同一安全姿态（凭据只发初始端点、4xx 不重试、
错误只给固定公开说明），但作为新后端共用的一条实现，避免三份复制。
测试通过替换 `_default_open` 在无网络下完整走请求构造与响应解析。
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .openai_compatible import BackendError, _RejectRedirects, _transport_error_label

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class HttpResult:
    data: dict[str, Any]
    latency_ms: int


def _proxy_mapping(proxy: str | None, no_proxy: bool) -> dict[str, str]:
    if no_proxy:
        return {}
    if proxy:
        return {"http": proxy, "https": proxy}
    return dict(urllib.request.getproxies())


def _default_open(request: urllib.request.Request, timeout: int,
                  proxy: str | None, no_proxy: bool):
    mapping = _proxy_mapping(proxy, no_proxy)
    handler = urllib.request.ProxyHandler(mapping if mapping else {})
    return urllib.request.build_opener(handler, _RejectRedirects()).open(
        request, timeout=timeout
    )


def post_json(
    *,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 180,
    max_retries: int = 2,
    retry_backoff: float = 1.5,
    proxy: str | None = None,
    no_proxy: bool = False,
    on_retry=None,
) -> HttpResult:
    """POST JSON 并按传输类/限流类状态做有界重试；返回解析结果与总延迟。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    started = time.monotonic()
    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            response = _default_open(request, timeout, proxy, no_proxy)
            with response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, dict):
                raise BackendError("响应结构异常（详情已隐藏）")
            return HttpResult(
                data=data,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        except urllib.error.HTTPError as exc:
            code = exc.code
            status = code if type(code) is int and 100 <= code <= 599 else None
            try:
                exc.close()
            except MemoryError:
                raise
            except Exception:  # noqa: BLE001 - 关闭失败不得覆盖原状态
                pass
            last_error = f"HTTP {status if status is not None else 'unknown'}（详情已隐藏）"
            if status is None or status not in RETRYABLE_STATUS or attempt >= max_retries:
                raise BackendError(last_error) from None
        except MemoryError:
            raise
        except BackendError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = f"模型传输失败（{_transport_error_label(exc)}；详情已隐藏）"
            retryable = isinstance(
                exc, (TimeoutError, urllib.error.URLError, ConnectionError,
                      http.client.HTTPException)
            )
            if not retryable or attempt >= max_retries:
                raise BackendError(last_error) from None
        if on_retry is not None:
            on_retry()
        time.sleep(retry_backoff * (attempt + 1))
    raise BackendError(f"重试耗尽：{last_error}")


def tool_specs_openai(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """规范化 OpenAI 风格工具 schema（loop 使用的规范格式）。"""
    specs: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        spec: dict[str, Any] = {"name": name}
        if isinstance(fn.get("description"), str):
            spec["description"] = fn["description"]
        spec["parameters"] = fn.get("parameters") or {"type": "object", "properties": {}}
        specs.append(spec)
    return specs


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {"_raw": raw}
        return parsed if isinstance(parsed, dict) else {"_raw": raw}
    return {}
