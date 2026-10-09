"""OpenAI 兼容后端（默认面向 MiniMax-M3）。

零第三方依赖：只用标准库 urllib —— core 保持零依赖（D6）。
需要 SDK 能力的场景再走 `icode-agent[llm]` extras。

安全边界：默认 repr 和公开模型调用错误隐藏敏感配置/原始失败详情；
请求凭据仍保存在实例字段中，只发往调用者选择的初始端点。
"""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .base import AssistantMessage, Backend, ToolCall, strip_think

DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M3"


class BackendError(RuntimeError):
    """模型调用失败；传输与响应解析路径使用固定公开说明。"""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """凭据只发往选定的初始端点；所有重定向均按 HTTP 错误失败。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport_error_label(exc: Exception) -> str:
    """只从固定类型集合生成展示标签，不检查或格式化原异常。"""
    for kind, label in (
        (TimeoutError, "TimeoutError"),
        (urllib.error.URLError, "URLError"),
        (ConnectionError, "ConnectionError"),
        (http.client.HTTPException, "HTTPException"),
        (UnicodeError, "UnicodeError"),
        (json.JSONDecodeError, "JSONDecodeError"),
        (ValueError, "ValueError"),
        (TypeError, "TypeError"),
        (OSError, "OSError"),
    ):
        if isinstance(exc, kind):
            return label
    return "unavailable"


@dataclass
class Usage:
    """一次调用的用量（运营指标，用于预算闸门，不作为质量指标）。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    calls: int = 1
    retries: int = 0

    def merge(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            calls=self.calls + other.calls,
            retries=self.retries + other.retries,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "retries": self.retries,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }


def _usage_from(raw: dict[str, Any]) -> Usage:
    u = raw.get("usage") or {}
    details = u.get("completion_tokens_details") or {}
    prompt_details = u.get("prompt_tokens_details") or {}
    return Usage(
        prompt_tokens=int(u.get("prompt_tokens") or 0),
        completion_tokens=int(u.get("completion_tokens") or 0),
        total_tokens=int(u.get("total_tokens") or 0),
        cached_tokens=int(prompt_details.get("cached_tokens") or 0),
        reasoning_tokens=int(details.get("reasoning_tokens") or 0),
    )


@dataclass
class OpenAICompatibleBackend:
    """POST /chat/completions 的最小实现（支持 function calling）。

    代理策略（三种，按优先级）：
      - `no_proxy=True`  → 强制直连（`ProxyHandler({})`）
      - `proxy="..."`    → 只走指定代理
      - 都不给            → 跟随环境变量（HTTP(S)_PROXY），这是最不意外的默认

    为什么要有前两种：托管环境常注入内部隧道代理（如 `127.0.0.1:xxxx`），
    它对外部模型端点可能直接 502。此时必须能显式绕过，而不是让人猜。
    """

    api_key: str = field(repr=False)
    model: str = ""
    base_url: str = field(default="", repr=False)
    timeout: int = 180
    temperature: float | None = None
    proxy: str | None = field(default=None, repr=False)
    no_proxy: bool = False
    max_retries: int = 2
    retry_backoff: float = 1.5
    name: str = "openai-compatible"
    usage: Usage = field(default_factory=lambda: Usage(calls=0))
    last_usage: Usage = field(default_factory=Usage, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise BackendError("api_key 为空")
        if not self.model:
            self.model = os.environ.get("ICODE_LLM_MODEL") or DEFAULT_MODEL
        if not self.base_url:
            self.base_url = (os.environ.get("ICODE_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

    # ---- 代理 ----

    def _proxy_mapping(self) -> dict[str, str]:
        """本次请求实际使用的代理映射（空 dict = 直连）。

        这是可测试的契约：`{}` 明确表示"不走代理"，
        而 `getproxies()` 的结果表示"跟随环境"。
        """
        if self.no_proxy:
            return {}
        if self.proxy:
            return {"http": self.proxy, "https": self.proxy}
        return dict(urllib.request.getproxies())

    def _opener(self) -> urllib.request.OpenerDirector:
        mapping = self._proxy_mapping()
        if not mapping:
            # 显式传空映射：禁用代理（注意空 ProxyHandler 不注册为 handler，
            # 因此不能用 opener.handlers 断言，见 _proxy_mapping）
            return urllib.request.build_opener(urllib.request.ProxyHandler({}), _RejectRedirects())
        return urllib.request.build_opener(urllib.request.ProxyHandler(mapping), _RejectRedirects())

    def active_proxy(self) -> str:
        """当前生效的代理描述（用于自检与错误提示）。"""
        if self.no_proxy:
            return "禁用（强制直连）"
        if self.proxy:
            return "已配置（显式代理）"
        env = urllib.request.getproxies()
        got = env.get("https") or env.get("http")
        return "已配置（环境代理）" if got else "无"

    def _proxy_hint(self, exc: Exception) -> str:
        """仅按配置给出固定提示，不从异常文字猜测代理根因。"""
        if self.no_proxy or self.proxy:
            return ""
        env = urllib.request.getproxies()
        if env.get("https") or env.get("http"):
            return (
                "\n  提示：当前请求使用环境代理。"
                "若该代理不适用于此端点，可用 `--no-proxy` 或环境变量 `ICODE_LLM_NO_PROXY=1` 强制直连。"
            )
        return ""

    # ---- 重试策略 ----

    _RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

    @classmethod
    def _retryable_http(cls, status: int) -> bool:
        """只重试传输类/限流类状态；4xx 业务错误属确定性失败，不重试。"""
        return status in cls._RETRYABLE_STATUS

    @staticmethod
    def _retryable_exc(exc: Exception) -> bool:
        import http.client

        if isinstance(exc, (TimeoutError, urllib.error.URLError, ConnectionError,
                            http.client.HTTPException)):
            return True
        return False

    # ---- 调用 ----

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
        tool_choice: str = "auto",
    ) -> AssistantMessage:
        if not isinstance(tool_choice, str) or not tool_choice:
            raise ValueError("tool_choice 必须为非空模式或工具名")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if tools:
            payload["tools"] = tools
            if tool_choice in ("auto", "required"):
                payload["tool_choice"] = tool_choice
            else:
                payload["tool_choice"] = {
                    "type": "function",
                    "function": {"name": tool_choice},
                }

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        # 模型调用是**只读动作**：传输类失败可按执行模型策略自动重试
        # （retryable_transport），但 4xx 属确定性失败，绝不重试。
        data: dict[str, Any] = {}
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                with self._opener().open(req, timeout=self.timeout) as resp:  # noqa: S310
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                # 状态是唯一可展示的原错误字段；拒绝 bool/int 子类等动态值。
                code = exc.code
                status = code if type(code) is int and 100 <= code <= 599 else None
                try:
                    exc.close()
                except MemoryError:
                    raise
                except Exception:  # noqa: BLE001
                    # 普通关闭失败不能覆盖原 HTTP 状态或改变其重试策略。
                    pass
                last_error = f"HTTP {status if status is not None else 'unknown'}（详情已隐藏）"
                if status is None or not self._retryable_http(status) or attempt >= self.max_retries:
                    raise BackendError(last_error + self._proxy_hint(exc)) from None
            except MemoryError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = f"模型传输失败（{_transport_error_label(exc)}；详情已隐藏）"
                if not self._retryable_exc(exc) or attempt >= self.max_retries:
                    raise BackendError(last_error + self._proxy_hint(exc)) from None
            self.usage.retries += 1
            time.sleep(self.retry_backoff * (attempt + 1))
        else:  # pragma: no cover - 循环必然 break 或 raise
            raise BackendError(f"重试耗尽：{last_error}{self._proxy_hint(RuntimeError(last_error))}")

        try:
            msg = data["choices"][0]["message"]

            self.last_usage = _usage_from(data)
            self.usage = self.usage.merge(self.last_usage)

            calls: list[ToolCall] = []
            for idx, raw in enumerate(msg.get("tool_calls") or []):
                fn = raw.get("function") or {}
                raw_args = fn.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {"_raw": raw_args}
                calls.append(
                    ToolCall(
                        id=str(raw.get("id") or f"call_{idx}"),
                        name=str(fn.get("name") or ""),
                        arguments=args or {},
                    )
                )

            return AssistantMessage(
                content=strip_think(msg.get("content")),
                tool_calls=calls,
                raw={"model": data.get("model"), "usage": data.get("usage")},
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, OverflowError):
            raise BackendError("响应结构异常（详情已隐藏）") from None


def _protocol_selfcheck() -> None:
    _: Backend = OpenAICompatibleBackend(api_key="x")  # type: ignore[assignment]


def build_backend(
    kind: str,
    *,
    key_file: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    proxy: str | None = None,
    no_proxy: bool = False,
) -> Backend:
    """按名称构造后端。`fake` 离线；其余需要密钥。"""
    if kind == "fake":
        from .fake import FakeBackend

        return FakeBackend()
    if kind in ("openai-compatible", "openai", "minimax"):
        from ..config import llm_no_proxy, llm_proxy, resolve_api_key

        return OpenAICompatibleBackend(
            api_key=resolve_api_key(key_file),
            model=model or os.environ.get("ICODE_LLM_MODEL") or "",
            base_url=base_url or os.environ.get("ICODE_LLM_BASE_URL") or "",
            proxy=proxy or llm_proxy(),
            no_proxy=no_proxy or llm_no_proxy(),
        )
    raise BackendError(f"未知后端：{kind}（可用：fake / openai-compatible）")
