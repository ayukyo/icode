# R3 Provider Transport Privacy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留既有模型请求、代理映射、用量与有界重试合同的同时，拒绝凭据重定向转发，并把后端默认展示及公开失败文本收敛到固定安全信息。

**Architecture:** 复用标准库 urllib 和现有 Backend 协议，在当前后端加入私有拒绝重定向 handler、闭集错误类别与响应解析边界。完整 portable 离线测试用真实 OpenerDirector/HTTPErrorProcessor 验证重定向目的地零访问，用合成值验证默认 repr、公开 BackendError 和现有 LoopResult 传播。CI 仅在 DEFAULT 增加一个模块及完整选择配对守卫。

**Tech Stack:** Python 标准库 dataclasses、urllib、http.client、unittest；既有跨平台 workspace CI 与原三道 preflight；不新增依赖。

---

## 冻结输入、范围与执行授权

请求路径与实际 Git root 都是 `/home/orbbec/git/icode`。设计 `docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md` SHA256 `9edf53ff7cc4999e9f19837ef2a2b1819924ddd71e61c92a4d3f59b6972e892d`，已获 fresh SPEC→不同 QUALITY C0/I0/M0，仅 STATIC 信用。研究 `docs/nbl/specs/2026-10-09-provider-endpoint-and-secret-research.md` SHA256 `1ebeeda075935a0e2bf8edaa35ddd40655abbff55f10fd7354703f69fce31ab7`。起草时 main `d365e6f15d2d1a223ec60ba18310647c338f4eba`，vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`；当前构建诊断两源仍冻结且由 root 跑原完整 preflight。本计划不接触两源或共享测试进程，不抢其发布。它的正常发布可能推进 main；Task 1 必须重新绑定实际 main、后端及五文件原始 SHA，不能宣称 d365 是未来实施基线。

计划作者只读静态上下文、仅写本文件及 AST 解析样例，未执行样例、import 项目源码、测试、HTTP、后端 repr、读取 KEY/私有环境/本地配置，未提交/推送。正文中的命令与代码是未来实施内容；勾选必须由实际证据取得。用户“只 main、自主决定阶段、直接下一阶段不用等命令”既有授权覆盖技能默认 worktree、常规用户等待和逐任务提交惯例，但不覆盖安全门、测试、外发 KEY、新权限或平台准入。本作者冻结后 STOP；root 在 fresh 计划 SPEC→不同 QUALITY 后决定派发，禁止作者自动 handoff。

三问均有静态依据：dataclass 敏感 repr、HTTP body/exception 文本及默认 urllib redirect 是当前真实机制风险；已有 ProxyHandler、Usage、重试及 LoopResult 路径可复用；调用链 build_backend→complete→BackendError→LoopResult.error/render 或 CLI 捕获已核。不是实际凭据泄露事件或旧域名失效诊断。结构化需求→方案→风险记录沿设计118–120，文档计划不另改方案。

| 文件 | 任务/职责 | 允许变更 |
| --- | --- | --- |
| `src/icode/backends/openai_compatible.py` | Task 1，传输与错误展示边界 | 敏感字段 repr、拒绝 redirect、固定错误/提示、解析异常边界 |
| `tests/test_runner.py` | Task 1，既有三后端类回归 | 仅必要代理展示断言方法，其他方法保留 |
| `tests/test_backend_transport_privacy.py` | Task 1，完整 portable 正负控 | 新模块，全离线、无 skip |
| `scripts/run_workspace_ci.py` | Task 2，DEFAULT 选择 | 仅新增模块一次，不改 main 跳过策略 |
| `tests/test_run_workspace_ci.py` | Task 2，完整选择配对 | 一个完整选择/无 skip 标记断言方法 |

其余 config、base、loop、CLI、runner、native、vendor、workflow 不改。不迁默认域名/model，不增 provider/history 注册，不修改签名、工具参数、TLS、代理认证、超时/backoff/重试集合、权限或行为准入。成功内容和工具 arguments 不是通用脱敏对象；不声称 asdict、内存对象图、__context__、任意第三方后端全局安全。

独立研究沿固定 OpenCode `388406238bd5ca15564a762840a2362c3a45bd9c` MIT 和 Codex `99aa05341d1564cf4ca2b463c83b607ea5d1bb3e` Apache-2.0、CPython3.11.15 commit `2340a037f7450e70fccfe411e6531afb4d57a312`。采纳显式端点/敏感展示机制，成本为固定错误减少诊断细节与3xx失败；暂缓 provider 注册、同源例外、私有历史；不适配未知端点携 KEY 试错、正文 replace 式全链路安全声明。具体链接/日期/许可见冻结研究。root 阶段开始/结束刷新 `docs/agent-landscape-live.md` 相关条目；不假称完整20项目刚刷新，不复制上游代码。

## 公共合同与验收映射

| 冻结合同 | 完整实现/测试定位 |
| --- | --- |
| api_key/base_url/proxy repr=False，参数顺序/default 保留 | Task1字段块；`test_repr_and_constructor_contract` |
| 固定代理展示、_proxy_mapping不改，hint不碰异常属性 | Task1代理方法；`test_proxy_policy_and_mapping`、`test_proxy_hint_never_formats_exception` |
| 合法HTTP精确int100–599，unknown不重试，资源close一次 | Task1HTTP catch；`test_http_status_normalization`、`test_http_body_and_properties_are_not_read`、`test_http_close_boundaries` |
| 闭集类别/subclass优先级、MemoryError/KI/SE传播 | `_transport_label`/catch；`test_closed_transport_labels`、`test_transport_fatal_exceptions_propagate` |
| 已知响应输入异常固定错误、Usage顺序/_raw兼容 | 完整complete；`test_malformed_response_boundaries`、`test_usage_precedes_tool_parse_failure`、`test_success_tools_usage_and_raw_arguments` |
| 全代理真实opener拒绝5状态/5Location，origin1/destination0 | fixture+`test_real_opener_redirect_matrix`、`test_real_opener_success_control` |
| 401一次，429/503/Timeout成功与耗尽，URL不换 | `test_deterministic_http_no_retry`、`test_retry_success_contract`、`test_retry_exhaustion_contract` |
| decode错误固定文本，公开str/repr/traceback/JSON/loop无合成值 | `test_decode_failures`、`test_public_exception_boundary`、`test_loop_public_error_boundary` |
| DEFAULT仅增模块一次、完整加载、无skip标记，实际运行零skip另计 | Task2配对方法；Task3真实结果 |
| 五源freeze、双审、定点→20→DEFAULT→原三道、治理文档与发布观察 | Task1/2 STOP；Task3/4 root流程 |

## 固定运行环境

未来每个执行者在 `/home/orbbec/git/icode` 设置下列环境，再逐条串行命令；Python 实际版本为3.11.15，执行文件叫 `python`，不拼不存在的 `python3.11.15`。Go实际版本为1.27.1，执行文件叫 `go`，其父目录已列 PATH。不读取/打印其他环境变量。所有 build 并发1，低于用户上限6；源码写入时不得跑共享全量验证。

```bash
cd /home/orbbec/git/icode
export PATH=/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin:/tmp/icode-sigstore-go-gwCdn3/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONPATH=src:.
export PYTHONDONTWRITEBYTECODE=1
export GOMAXPROCS=1
export GOFLAGS=-p=1
export GOTOOLCHAIN=local
export CMAKE_BUILD_PARALLEL_LEVEL=1
```

### Task 1: fresh 单实现者完成后端边界与离线 TDD

**状态**
- [x] 任务完成（仅 Task1；独立 SPEC→不同 QUALITY 已通过，完整软件门另列）

**Dependencies:** None（root 当前构建诊断必须先退出并完成其源码冻结/发布；本计划fresh双审通过）
**Parallelizable:** No (生产修改、RED/GREEN、作者自审和三源冻结串行；禁止全量验证与写入并行)

- [x] **Step 1: root 绑定实际 main，并由 fresh writer 全文回读本次三个编辑文件及上下游。**

```bash
git branch --show-current
git rev-parse --show-toplevel
git rev-parse HEAD
git status --short
sha256sum docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md docs/nbl/specs/2026-10-09-provider-endpoint-and-secret-research.md
sha256sum src/icode/backends/openai_compatible.py tests/test_runner.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
git -C vendor/icode-skill rev-parse HEAD
git -C vendor/icode-skill status --porcelain
git ls-files -s vendor/icode-skill
sed -n '1,360p' src/icode/backends/openai_compatible.py
sed -n '1,90p' src/icode/backends/base.py
sed -n '1,35p' tests/test_runner.py
sed -n '1489,1727p' tests/test_runner.py
sed -n '1,186p' scripts/run_workspace_ci.py
sed -n '1,360p' tests/test_run_workspace_ci.py
sed -n '35,145p' src/icode/loop.py
sed -n '295,330p' src/icode/loop.py
rg -n 'active_proxy|BackendError|build_backend|def _build_runner' src/icode/cli.py
```

Expected：root=请求路径、branch=main；冻结设计/研究SHA精确匹配，vendor clean/head=gitlink；记录实际后端/选择文件SHA和main。行号是起草快照，若文件变长必须读到 EOF，三个类边界须用rg定位后全文回读，不能拿截断片段称全文。发现已有重叠改动先由root判断来源，不覆盖用户/上一片变化。原三后端类总体保留，只有Step2列出的方法变化。

- [x] **Step 2: 先用 apply_patch 创建完整 `tests/test_backend_transport_privacy.py`，并替换旧代理类下列五个完整方法。**

新模块完整内容如下。fixture只能创建合成值，不取私有env/local配置；getproxies 始终stub，proxy_bypass 固定False以隔离主机环境/系统代理绕过配置读取，getproxies_environment 毒化以拒绝任何漏出的主机代理环境读取。这些patch仅限测试，不改生产代理行为。真实redirect fixture拦截所有http/https地址，并毒化socket连接；支持问题必须FAIL，不能skip。普通transport mock仅用于错误/重试，不冒充真实redirect。

```python
"""Portable offline tests for backend transport and public error privacy."""

from __future__ import annotations

import http.client
import inspect
import io
import json
import socket
import tempfile
import traceback
import unittest
import urllib.error
import urllib.request
import urllib.response
from email.message import Message
from pathlib import Path
from unittest import mock

from icode.backends import BackendError, OpenAICompatibleBackend
from icode.backends.openai_compatible import DEFAULT_BASE_URL, DEFAULT_MODEL
from icode.guard import Guard, Scope
from icode.loop import AgentLoop, LoopConfig
from icode.tools import ToolContext, ToolRegistry


PRIVATE = "-".join(("fixture", "credential", "private"))
PROXY = "http://user:" + PRIVATE + "@proxy.invalid:8080/path?q=" + PRIVATE + "#fragment"
BASE = "https://origin.invalid/v1"
MESSAGES = [{"role": "user", "content": "hello"}]
OK = {
    "model": "fixture-model",
    "choices": [{"message": {"content": "<think>hidden</think>ok"}}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
              "prompt_tokens_details": {"cached_tokens": 1},
              "completion_tokens_details": {"reasoning_tokens": 1}},
}


class _Response:
    def __init__(self, value=OK, *, raw=None):
        self.raw = json.dumps(value).encode("utf-8") if raw is None else raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.raw


class _SequenceOpener:
    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append((req.full_url, req.get_header("Authorization"), timeout,
                              json.loads(req.data.decode("utf-8"))))
        value = self.sequence.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class _PoisonRuntimeError(RuntimeError):
    def __str__(self):
        raise AssertionError("exception str was accessed")

    def __repr__(self):
        raise AssertionError("exception repr was accessed")

    @property
    def reason(self):
        raise AssertionError("exception reason was accessed")


class _PoisonHTTPError(urllib.error.HTTPError):
    def __init__(self, code, *, close_error=None):
        super().__init__(BASE + "/" + PRIVATE, code, PRIVATE, Message(), None)
        self.close_count = 0
        self.close_error = close_error

    def __getattribute__(self, name):
        if name in {"url", "msg", "headers", "reason"}:
            raise AssertionError("HTTP private property was accessed")
        return super().__getattribute__(name)

    def __str__(self):
        raise AssertionError("HTTP exception str was accessed")

    def __repr__(self):
        raise AssertionError("HTTP exception repr was accessed")

    def read(self, *args):
        raise AssertionError("HTTP body was read")

    def close(self):
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


class _FixtureNetwork:
    """Capture every address inside real urllib dispatch, before any socket."""
    def __init__(self, origin, *, status=200, location=None, value=OK):
        self.origin = origin
        self.status = status
        self.location = location
        self.value = value
        self.origin_requests = []
        self.destination_requests = []

    def response(self, req):
        record = (req.full_url, req.get_header("Authorization"), req.get_method(), req.data)
        if req.full_url == self.origin:
            self.origin_requests.append(record)
            status = self.status
            headers = Message()
            if self.location is not None:
                headers["Location"] = self.location
            payload = json.dumps(self.value).encode("utf-8")
        else:
            self.destination_requests.append(record)
            status = 200
            headers = Message()
            payload = json.dumps(OK).encode("utf-8")
        response = urllib.response.addinfourl(io.BytesIO(payload), headers, req.full_url, status)
        response.msg = "fixture response"
        return response


class _FixtureHTTP(urllib.request.HTTPHandler):
    handler_order = 400

    def __init__(self, network):
        super().__init__()
        self.network = network

    def http_open(self, req):
        return self.network.response(req)


class _FixtureHTTPS(urllib.request.HTTPSHandler):
    handler_order = 400

    def __init__(self, network):
        super().__init__()
        self.network = network

    def https_open(self, req):
        return self.network.response(req)


class TestBackendTransportPrivacy(unittest.TestCase):
    def setUp(self):
        self.proxies = mock.patch("urllib.request.getproxies", return_value={})
        self.proxies.start()
        self.addCleanup(self.proxies.stop)
        self.proxy_bypass = mock.patch("urllib.request.proxy_bypass", return_value=False)
        self.proxy_bypass.start()
        self.addCleanup(self.proxy_bypass.stop)
        self.proxy_environment = mock.patch(
            "urllib.request.getproxies_environment",
            side_effect=AssertionError("host proxy environment forbidden"),
        )
        self.proxy_environment.start()
        self.addCleanup(self.proxy_environment.stop)

    def backend(self, **kwargs):
        defaults = dict(api_key=PRIVATE, model="fixture-model", base_url=BASE,
                        max_retries=0, timeout=23, retry_backoff=0.25)
        defaults.update(kwargs)
        return OpenAICompatibleBackend(**defaults)

    def failure(self, backend, opener):
        with mock.patch.object(backend, "_opener", return_value=opener):
            try:
                backend.complete(MESSAGES)
            except Exception as exc:
                self.assertIsInstance(exc, BackendError,
                                      "ordinary failure must become public BackendError")
                return exc
        self.fail("backend unexpectedly succeeded")

    def success(self, backend, opener, **kwargs):
        with mock.patch.object(backend, "_opener", return_value=opener):
            try:
                return backend.complete(MESSAGES, **kwargs)
            except Exception:
                self.fail("positive control unexpectedly raised an ordinary exception")

    def public(self, error):
        formatted = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        public_json = json.dumps({"error": str(error), "repr": repr(error)}, ensure_ascii=False)
        for value in (str(error), repr(error), formatted, public_json):
            self.assertNotIn(PRIVATE, value)
            self.assertNotIn("origin.invalid", value)
            self.assertNotIn("proxy.invalid", value)
        return str(error)

    def real_call(self, backend, network, *, tools=None, tool_choice="auto"):
        original_build = urllib.request.build_opener
        built = []

        def fixture_build(*handlers):
            opener = original_build(*handlers, _FixtureHTTP(network), _FixtureHTTPS(network))
            self.assertIsInstance(opener, urllib.request.OpenerDirector)
            self.assertTrue(any(isinstance(handler, urllib.request.HTTPErrorProcessor)
                                for handler in opener.handlers))
            built.append(opener)
            return opener

        with mock.patch("urllib.request.build_opener", side_effect=fixture_build), \
                mock.patch.object(socket, "create_connection", side_effect=AssertionError("socket forbidden")), \
                mock.patch.object(socket.socket, "connect", side_effect=AssertionError("socket forbidden")), \
                mock.patch.object(socket.socket, "connect_ex", side_effect=AssertionError("socket forbidden")), \
                mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
            try:
                message = backend.complete(MESSAGES, tools=tools, tool_choice=tool_choice)
                error = None
            except Exception as exc:
                self.assertIsInstance(exc, BackendError,
                                      "fixture/protocol failure must not be counted as ERROR RED")
                message = None
                error = exc
        return message, error, built, sleep

    def test_repr_and_constructor_contract(self):
        backend = self.backend(base_url=BASE + "/" + PRIVATE, proxy=PROXY)
        self.assertNotIn(PRIVATE, repr(backend))
        self.assertNotIn(BASE, repr(backend))
        self.assertNotIn(PROXY, str(backend))
        parameters = list(inspect.signature(OpenAICompatibleBackend).parameters.values())
        self.assertEqual([parameter.name for parameter in parameters],
                         ["api_key", "model", "base_url", "timeout", "temperature", "proxy",
                          "no_proxy", "max_retries", "retry_backoff", "name", "usage", "last_usage"])
        self.assertIs(parameters[0].default, inspect.Parameter.empty)
        self.assertEqual([parameter.default for parameter in parameters[1:10]],
                         ["", "", 180, None, None, False, 2, 1.5, "openai-compatible"])
        self.assertEqual(DEFAULT_BASE_URL, "https://api.minimaxi.com/v1")
        self.assertEqual(DEFAULT_MODEL, "MiniMax-M3")
        self.assertEqual(backend.api_key, PRIVATE)
        self.assertEqual(backend.proxy, PROXY)

    def test_proxy_policy_and_mapping(self):
        with mock.patch("urllib.request.getproxies", return_value={"https": PROXY}):
            for kwargs, expected, mapping in (
                ({"no_proxy": True, "proxy": PROXY}, "禁用（强制直连）", {}),
                ({"proxy": PROXY}, "已配置（显式代理）", {"http": PROXY, "https": PROXY}),
                ({}, "已配置（环境代理）", {"https": PROXY}),
            ):
                with self.subTest(kwargs=sorted(kwargs)):
                    backend = self.backend(**kwargs)
                    self.assertEqual(backend.active_proxy(), expected)
                    self.assertEqual(backend._proxy_mapping(), mapping)
                    self.assertNotIn(PRIVATE, backend.active_proxy())
        self.assertEqual(self.backend().active_proxy(), "无")

    def test_proxy_hint_never_formats_exception(self):
        error = _PoisonRuntimeError(PRIVATE)
        with mock.patch("urllib.request.getproxies", return_value={"https": PROXY}):
            for kwargs in ({"no_proxy": True}, {"proxy": PROXY}, {}):
                backend = self.backend(**kwargs)
                try:
                    hint = backend._proxy_hint(error)
                except Exception:
                    self.fail("proxy hint accessed a private exception property")
                if kwargs:
                    self.assertEqual(hint, "")
                else:
                    self.assertIn("--no-proxy", hint)
                    self.assertIn("ICODE_LLM_NO_PROXY=1", hint)
                    self.assertIn("环境代理", hint)
                self.assertNotIn(PRIVATE, hint)
                self.assertNotIn(PROXY, hint)
        self.assertEqual(self.backend()._proxy_hint(error), "")

    def test_real_opener_redirect_matrix(self):
        locations = (BASE + "/same", "https://foreign.invalid/next",
                     "https://origin.invalid:444/next", "/relative", "http://origin.invalid/down")
        for kwargs in ({"no_proxy": True}, {"proxy": PROXY}, {}):
            for code in (301, 302, 303, 307, 308):
                for location in locations:
                    with self.subTest(strategy=sorted(kwargs), code=code, location=location):
                        with mock.patch("urllib.request.getproxies", return_value={"https": PROXY}):
                            backend = self.backend(max_retries=3, **kwargs)
                            network = _FixtureNetwork(BASE + "/chat/completions", status=code,
                                                      location=location)
                            message, error, built, sleep = self.real_call(backend, network)
                        self.assertEqual(len(network.origin_requests), 1)
                        self.assertEqual(network.destination_requests, [], "Authorization must never forward")
                        self.assertIsNone(message)
                        self.assertIsInstance(error, BackendError)
                        self.assertIn("HTTP " + str(code), self.public(error))
                        self.assertEqual(backend.usage.retries, 0)
                        sleep.assert_not_called()
                        self.assertEqual(len(built), 1)
                        handlers = [handler for handler in built[0].handlers
                                    if isinstance(handler, urllib.request.HTTPRedirectHandler)]
                        self.assertEqual(len(handlers), 1)
                        self.assertIsNot(type(handlers[0]), urllib.request.HTTPRedirectHandler)
                        self.assertEqual(network.origin_requests[0][1], "Bearer " + PRIVATE)

    def test_real_opener_success_control(self):
        tools = [{"type": "function", "function": {"name": "inspect"}}]
        for kwargs in ({"no_proxy": True}, {"proxy": PROXY}, {}):
            for base_url in (BASE, "http://origin.invalid/v1"):
                with self.subTest(strategy=sorted(kwargs), base_url=base_url):
                    with mock.patch("urllib.request.getproxies", return_value={"https": PROXY, "http": PROXY}):
                        backend = self.backend(base_url=base_url, **kwargs)
                        network = _FixtureNetwork(base_url + "/chat/completions")
                        message, error, built, sleep = self.real_call(backend, network, tools=tools,
                                                                     tool_choice="required")
                    self.assertIsNone(error)
                    self.assertEqual(message.content, "ok")
                    self.assertEqual(len(built), 1)
                    self.assertEqual(len(network.origin_requests), 1)
                    self.assertEqual(network.destination_requests, [])
                    url, authorization, method, body = network.origin_requests[0]
                    self.assertEqual((url, authorization, method),
                                     (base_url + "/chat/completions", "Bearer " + PRIVATE, "POST"))
                    payload = json.loads(body.decode("utf-8"))
                    self.assertEqual(payload["messages"], MESSAGES)
                    self.assertEqual(payload["tools"], tools)
                    self.assertEqual(payload["tool_choice"], "required")
                    self.assertEqual(backend.usage.calls, 1)
                    self.assertEqual(backend.usage.total_tokens, 5)
                    self.assertEqual(backend.usage.retries, 0)
                    sleep.assert_not_called()

    def test_http_body_and_properties_are_not_read(self):
        error = _PoisonHTTPError(401)
        backend = self.backend(max_retries=3)
        opener = _SequenceOpener([error])
        with mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
            public = self.failure(backend, opener)
        self.assertEqual(self.public(public), "HTTP 401：模型调用失败（详情已隐藏）")
        self.assertEqual(error.close_count, 1)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(backend.usage.retries, 0)
        sleep.assert_not_called()

    def test_http_status_normalization(self):
        class StatusSubclass(int):
            pass

        for code in (100, 599, 99, 600, True, 429.0, "429", None, StatusSubclass(429)):
            with self.subTest(code=code):
                error = _PoisonHTTPError(code)
                backend = self.backend(max_retries=3)
                opener = _SequenceOpener([error])
                with mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    public = self.failure(backend, opener)
                expected = str(code) if type(code) is int and 100 <= code <= 599 else "unknown"
                self.assertEqual(self.public(public), "HTTP " + expected + "：模型调用失败（详情已隐藏）")
                self.assertEqual(error.close_count, 1)
                self.assertEqual(len(opener.requests), 1)
                self.assertEqual(backend.usage.retries, 0)
                sleep.assert_not_called()

    def test_http_close_boundaries(self):
        for close_error in (None, RuntimeError(PRIVATE)):
            with self.subTest(close_kind=type(close_error).__name__):
                error = _PoisonHTTPError(401, close_error=close_error)
                backend = self.backend(max_retries=3)
                opener = _SequenceOpener([error])
                with mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    public = self.failure(backend, opener)
                self.assertIn("HTTP 401", self.public(public))
                self.assertEqual(error.close_count, 1)
                self.assertEqual(len(opener.requests), 1)
                sleep.assert_not_called()
        for kind in (MemoryError, KeyboardInterrupt, SystemExit):
            with self.subTest(fatal=kind.__name__):
                fatal = kind(PRIVATE)
                error = _PoisonHTTPError(401, close_error=fatal)
                backend = self.backend(max_retries=3)
                opener = _SequenceOpener([error])
                with mock.patch.object(backend, "_opener", return_value=opener), \
                        mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    try:
                        backend.complete(MESSAGES)
                    except kind as received:
                        self.assertIs(received, fatal)
                    except Exception:
                        self.fail("HTTP close fatal exception was replaced")
                    else:
                        self.fail("HTTP close fatal exception was swallowed")
                self.assertEqual(error.close_count, 1)
                self.assertEqual(len(opener.requests), 1)
                sleep.assert_not_called()

    def test_closed_transport_labels(self):
        class ForeignError(Exception):
            pass

        cases = ((TimeoutError(PRIVATE), "TimeoutError"),
                 (urllib.error.URLError(PRIVATE), "URLError"),
                 (ConnectionRefusedError(PRIVATE), "ConnectionError"),
                 (http.client.RemoteDisconnected(PRIVATE), "ConnectionError"),
                 (http.client.BadStatusLine(PRIVATE), "HTTPException"),
                 (UnicodeDecodeError("utf-8", b"x", 0, 1, PRIVATE), "UnicodeError"),
                 (json.JSONDecodeError(PRIVATE, PRIVATE, 0), "JSONDecodeError"),
                 (ValueError(PRIVATE), "ValueError"), (TypeError(PRIVATE), "TypeError"),
                 (OSError(PRIVATE), "OSError"), (_PoisonRuntimeError(PRIVATE), "unavailable"),
                 (ForeignError(PRIVATE), "unavailable"))
        for error, label in cases:
            with self.subTest(label=label, type_name=type(error).__name__):
                public = self.failure(self.backend(), _SequenceOpener([error]))
                self.assertEqual(self.public(public), "模型传输失败（" + label + "；详情已隐藏）")

    def test_transport_fatal_exceptions_propagate(self):
        for kind in (MemoryError, KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__):
                error = kind(PRIVATE)
                backend = self.backend(max_retries=3)
                opener = _SequenceOpener([error])
                with mock.patch.object(backend, "_opener", return_value=opener), \
                        mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    try:
                        backend.complete(MESSAGES)
                    except kind as received:
                        self.assertIs(received, error)
                    except Exception:
                        self.fail("transport fatal exception was replaced")
                    else:
                        self.fail("transport fatal exception was swallowed")
                self.assertEqual(len(opener.requests), 1)
                self.assertEqual(backend.usage.retries, 0)
                sleep.assert_not_called()

    def test_deterministic_http_no_retry(self):
        for code in (400, 401, 403, 404, 422):
            with self.subTest(code=code):
                error = _PoisonHTTPError(code)
                backend = self.backend(max_retries=3)
                opener = _SequenceOpener([error])
                with mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    public = self.failure(backend, opener)
                self.assertIn("HTTP " + str(code), self.public(public))
                self.assertEqual(len(opener.requests), 1)
                self.assertEqual(backend.usage.retries, 0)
                self.assertEqual(error.close_count, 1)
                sleep.assert_not_called()

    def test_retry_success_contract(self):
        for first in (_PoisonHTTPError(429), _PoisonHTTPError(503), TimeoutError(PRIVATE),
                      _PoisonHTTPError(429, close_error=RuntimeError(PRIVATE))):
            with self.subTest(kind=type(first).__name__):
                backend = self.backend(max_retries=2)
                opener = _SequenceOpener([first, _Response()])
                with mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    message = self.success(backend, opener)
                self.assertEqual(message.content, "ok")
                self.assertEqual(backend.usage.retries, 1)
                self.assertEqual(backend.usage.calls, 1)
                self.assertEqual(backend.last_usage.total_tokens, 5)
                self.assertEqual(len(opener.requests), 2)
                self.assertEqual({record[0] for record in opener.requests}, {BASE + "/chat/completions"})
                self.assertEqual({record[1] for record in opener.requests}, {"Bearer " + PRIVATE})
                self.assertEqual({record[2] for record in opener.requests}, {23})
                self.assertEqual(opener.requests[0][3], opener.requests[1][3])
                sleep.assert_called_once_with(0.25)
                if isinstance(first, _PoisonHTTPError):
                    self.assertEqual(first.close_count, 1)

    def test_retry_exhaustion_contract(self):
        for kind in ("http429", "http503", "timeout"):
            with self.subTest(kind=kind):
                errors = [TimeoutError(PRIVATE) if kind == "timeout"
                          else _PoisonHTTPError(429 if kind == "http429" else 503) for _ in range(3)]
                backend = self.backend(max_retries=2)
                opener = _SequenceOpener(errors)
                with mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    public = self.failure(backend, opener)
                self.public(public)
                self.assertEqual(len(opener.requests), 3)
                self.assertEqual({record[0] for record in opener.requests}, {BASE + "/chat/completions"})
                self.assertEqual(backend.usage.retries, 2)
                self.assertEqual(backend.usage.calls, 0)
                self.assertEqual(sleep.call_args_list, [mock.call(0.25), mock.call(0.5)])
                for error in errors:
                    if isinstance(error, _PoisonHTTPError):
                        self.assertEqual(error.close_count, 1)

    def test_decode_failures(self):
        for raw, label in ((b"\xff", "UnicodeError"), (PRIVATE.encode("utf-8"), "JSONDecodeError")):
            with self.subTest(label=label):
                backend = self.backend(max_retries=3)
                opener = _SequenceOpener([_Response(raw=raw)])
                with mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    public = self.failure(backend, opener)
                self.assertEqual(self.public(public), "模型传输失败（" + label + "；详情已隐藏）")
                self.assertEqual(len(opener.requests), 1)
                self.assertEqual(backend.usage.retries, 0)
                sleep.assert_not_called()

    def test_malformed_response_boundaries(self):
        values = ({"private": PRIVATE}, {"choices": []}, {"choices": None},
                  {"choices": [{"message": PRIVATE}]},
                  {"choices": [{"message": {"content": PRIVATE}}], "usage": PRIVATE},
                  {"choices": [{"message": {"content": PRIVATE}}],
                   "usage": {"prompt_tokens": PRIVATE}},
                  {"choices": [{"message": {"content": PRIVATE}}],
                   "usage": {"completion_tokens_details": PRIVATE}},
                  {"choices": [{"message": {"content": PRIVATE}}],
                   "usage": {"prompt_tokens": float("inf")}},
                  {"choices": [{"message": {"tool_calls": [PRIVATE]}}]},
                  {"choices": [{"message": {"tool_calls": [{"function": PRIVATE}]}}]},
                  {"choices": [{"message": {"content": {"private": PRIVATE}}}]},
                  [{"private": PRIVATE}])
        for index, value in enumerate(values):
            with self.subTest(vector=index):
                backend = self.backend(max_retries=3)
                opener = _SequenceOpener([_Response(value)])
                with mock.patch("icode.backends.openai_compatible.time.sleep") as sleep:
                    public = self.failure(backend, opener)
                self.assertEqual(self.public(public), "响应结构异常（详情已隐藏）")
                self.assertEqual(len(opener.requests), 1)
                self.assertEqual(backend.usage.retries, 0)
                sleep.assert_not_called()

    def test_usage_precedes_tool_parse_failure(self):
        value = dict(OK, choices=[{"message": {"tool_calls": [PRIVATE]}}])
        backend = self.backend()
        public = self.failure(backend, _SequenceOpener([_Response(value)]))
        self.assertEqual(self.public(public), "响应结构异常（详情已隐藏）")
        self.assertEqual(backend.usage.calls, 1)
        self.assertEqual(backend.last_usage.total_tokens, 5)
        self.assertEqual(backend.usage.total_tokens, 5)

    def test_success_tools_usage_and_raw_arguments(self):
        value = dict(OK, choices=[{"message": {
            "content": "<think>hidden</think>ok", "tool_calls": [
                {"id": "one", "function": {"name": "inspect", "arguments": '{"x": 1}'}},
                {"function": {"name": "fallback", "arguments": "invalid arguments"}},
            ]}}])
        backend = self.backend(temperature=0.3)
        opener = _SequenceOpener([_Response(value)])
        tools = [{"type": "function", "function": {"name": "inspect"}}]
        message = self.success(backend, opener, tools=tools, max_tokens=17, tool_choice="inspect")
        self.assertEqual(message.content, "ok")
        self.assertEqual([(call.id, call.name, call.arguments) for call in message.tool_calls],
                         [("one", "inspect", {"x": 1}),
                          ("call_1", "fallback", {"_raw": "invalid arguments"})])
        self.assertEqual(message.raw, {"model": "fixture-model", "usage": OK["usage"]})
        self.assertEqual(backend.last_usage.as_dict(),
                         {"calls": 1, "retries": 0, "prompt_tokens": 3, "completion_tokens": 2,
                          "total_tokens": 5, "cached_tokens": 1, "reasoning_tokens": 1})
        self.assertEqual(backend.usage.as_dict(), backend.last_usage.as_dict())
        self.assertEqual(opener.requests[0][3],
                         {"model": "fixture-model", "messages": MESSAGES, "max_tokens": 17,
                          "temperature": 0.3, "tools": tools,
                          "tool_choice": {"type": "function", "function": {"name": "inspect"}}})

    def test_public_exception_boundary(self):
        for raw_error in (RuntimeError(PRIVATE), _PoisonRuntimeError(PRIVATE), _PoisonHTTPError(401)):
            with self.subTest(kind=type(raw_error).__name__):
                error = self.failure(self.backend(), _SequenceOpener([raw_error]))
                self.public(error)
                self.assertTrue(error.__suppress_context__)
        # Suppressed context can retain private objects; this is display-only credit.

    def test_loop_public_error_boundary(self):
        backend = self.backend()
        opener = _SequenceOpener([_PoisonHTTPError(401)])
        with tempfile.TemporaryDirectory(prefix="icode-backend-loop-") as directory:
            root = Path(directory)
            loop = AgentLoop(backend=backend, registry=ToolRegistry(),
                             guard=Guard(Scope(workspace_root=root)), ctx=ToolContext(root=root),
                             config=LoopConfig(max_turns=1))
            with mock.patch.object(backend, "_opener", return_value=opener):
                result = loop.run(MESSAGES)
        self.assertFalse(result.ok)
        self.assertEqual(result.stop_reason, "backend_error")
        self.assertEqual(result.turns, [])
        self.assertIn("BackendError: HTTP 401", result.error)
        for text in (result.error, result.render(), json.dumps({"ok": result.ok,
                     "stop_reason": result.stop_reason, "error": result.error}, ensure_ascii=False)):
            self.assertNotIn(PRIVATE, text)
            self.assertNotIn("origin.invalid", text)


if __name__ == "__main__":
    unittest.main()
```

`tests/test_runner.py` 仅 `TestProxyStrategy` 下这五个方法替换，类其他方法与 `TestBackendFactory`/`TestBackendRetry` 全部保留。无需改顶层import，已有mock；每个完整方法如下，不直接访问真实主机代理env。

```python
    def test_默认跟随环境(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        self.assertFalse(b.no_proxy)
        self.assertIsNone(b.proxy)
        with mock.patch("urllib.request.getproxies", return_value={"https": "http://proxy.invalid:1"}):
            self.assertEqual(b.active_proxy(), "已配置（环境代理）")
        with mock.patch("urllib.request.getproxies", return_value={}):
            self.assertEqual(b.active_proxy(), "无")

    def test_显式代理优先于环境(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", proxy="http://127.0.0.1:1")
        with mock.patch("urllib.request.getproxies", return_value={"https": "http://proxy.invalid:1"}):
            self.assertEqual(b.active_proxy(), "已配置（显式代理）")
        self.assertEqual(b._proxy_mapping(),
                         {"http": "http://127.0.0.1:1", "https": "http://127.0.0.1:1"})

    def test_默认跟随环境代理(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        proxies = {"http": "http://proxy.invalid:1", "https": "http://proxy.invalid:2"}
        with mock.patch("urllib.request.getproxies", return_value=proxies):
            self.assertEqual(b._proxy_mapping(), proxies)

    def test_opener_可构造且不改状态(self) -> None:
        with mock.patch("urllib.request.getproxies", return_value={}):
            for kwargs in ({}, {"no_proxy": True}, {"proxy": "http://127.0.0.1:1"}):
                b = OpenAICompatibleBackend(api_key="k", **kwargs)
                opener = b._opener()
                self.assertTrue(hasattr(opener, "open"))
                self.assertEqual((b.no_proxy, b.proxy),
                                 (kwargs.get("no_proxy", False), kwargs.get("proxy")))

    def test_代理失败时给出可执行提示(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        with mock.patch("urllib.request.getproxies", return_value={"https": "http://proxy.invalid:1"}):
            hint = b._proxy_hint(RuntimeError("Tunnel connection failed: 502 Bad Gateway"))
        self.assertIn("--no-proxy", hint)
        self.assertIn("ICODE_LLM_NO_PROXY=1", hint)
        self.assertNotIn("proxy.invalid", hint)
```

- [x] **Step 3: 对生产修改前的具名断言取得有效 RED，随后检查完整新模块的错误归类。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_backend_transport_privacy.TestBackendTransportPrivacy.test_repr_and_constructor_contract tests.test_backend_transport_privacy.TestBackendTransportPrivacy.test_proxy_policy_and_mapping tests.test_backend_transport_privacy.TestBackendTransportPrivacy.test_real_opener_redirect_matrix tests.test_backend_transport_privacy.TestBackendTransportPrivacy.test_malformed_response_boundaries -v
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_backend_transport_privacy tests.test_runner.TestBackendFactory tests.test_runner.TestProxyStrategy tests.test_runner.TestBackendRetry -v
```

Expected：第一命令明确assertion FAIL，分别为repr含合成值、代理策略原地址、redirect目的地访问/默认handler、畸形usage未变安全BackendError；第二命令记录实际FAIL/ERROR/skip，不预填数量。poison的普通意外异常由failure/real_call包装为assertion FAIL，不能把加载/fixture ERROR当RED。有ERROR先修测试夹具并重新跑命名RED，禁止先改生产绕过RED。301/302/303旧标准handler可能访问destination，307/308旧默认POST本就失败，不能把后二者旧失败当新增redirect拒绝信用；完整矩阵另断言私有handler实例。新测试不得skip。

- [x] **Step 4: apply_patch 修改后端完整代码块，保留未列代码原样。**

顶层import增加 `http.client`，完整import段为：

```python
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
```

BackendError 本身的名字、继承与接口不变，完整声明仅校准说明边界：

```python
class BackendError(RuntimeError):
    """模型调用失败；传输与响应解析路径使用固定公开说明。"""
```

在 BackendError 与 Usage 之间加入唯一私有redirect handler；保留标准HTTPErrorProcessor，由urllib按现有标准错误路径抛HTTPError，不调用第二目标。

```python
class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """模型凭据只发往已选择端点，所有 redirect 均按原状态失败。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
```

dataclass完整字段段如下（顺序/default不变）；`__post_init__` 和 `_proxy_mapping` 原样保留：

```python
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
```

完整替换三个代理展示/opener方法；`exc` 参数保留但不读/格式化其属性。

```python
    def _opener(self) -> urllib.request.OpenerDirector:
        mapping = self._proxy_mapping()
        return urllib.request.build_opener(
            urllib.request.ProxyHandler(mapping), _RejectRedirects(),
        )

    def active_proxy(self) -> str:
        """只描述代理策略，不公开包含凭据的代理地址。"""
        if self.no_proxy:
            return "禁用（强制直连）"
        if self.proxy:
            return "已配置（显式代理）"
        env = urllib.request.getproxies()
        if env.get("https") or env.get("http"):
            return "已配置（环境代理）"
        return "无"

    def _proxy_hint(self, exc: Exception) -> str:
        """自动代理模式提供固定策略提示，不推断错误文本中的根因。"""
        if self.no_proxy or self.proxy:
            return ""
        env = urllib.request.getproxies()
        if env.get("https") or env.get("http"):
            return (
                "\n  提示：当前请求使用环境代理。"
                "若该代理不适用于此端点，可用 `--no-proxy` 或环境变量 `ICODE_LLM_NO_PROXY=1` 强制直连。"
            )
        return ""
```

在原 `_retryable_exc` 后加入私有闭集展示方法，原重试两个方法及状态集合完全不变。RemoteDisconnected同时继承ConnectionResetError/BadStatusLine，按顺序映射ConnectionError，恢复资格仍由原 `_retryable_exc` 决定。

```python
    @staticmethod
    def _transport_label(exc: Exception) -> str:
        """具体类别先于基类；未知异常不能把动态类名或文本公开。"""
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
```

完整替换 `complete`（不改其签名、请求构造、Usage顺序与_raw兼容），所有实际代码如下：

```python
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

        data: dict[str, Any] = {}
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                with self._opener().open(req, timeout=self.timeout) as resp:  # noqa: S310
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                code = exc.code
                status = code if type(code) is int and 100 <= code <= 599 else None
                # 不读取正文/URL/msg/headers/reason；普通close故障不覆盖原失败。
                try:
                    exc.close()
                except MemoryError:
                    raise
                except Exception:  # noqa: BLE001
                    pass
                label = str(status) if status is not None else "unknown"
                last_error = f"HTTP {label}：模型调用失败（详情已隐藏）"
                if status is None or not self._retryable_http(status) or attempt >= self.max_retries:
                    raise BackendError(last_error + self._proxy_hint(exc)) from None
            except MemoryError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = f"模型传输失败（{self._transport_label(exc)}；详情已隐藏）"
                if not self._retryable_exc(exc) or attempt >= self.max_retries:
                    raise BackendError(last_error + self._proxy_hint(exc)) from None
            self.usage.retries += 1
            time.sleep(self.retry_backoff * (attempt + 1))
        else:  # pragma: no cover - 合法重试预算下必然break或raise
            raise BackendError(f"重试耗尽：{last_error}{self._proxy_hint(RuntimeError())}")

        try:
            msg = data["choices"][0]["message"]
            # 保留旧记账顺序：usage成功转换后、工具/content解析前合并。
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
```

`Usage`/`_usage_from`、`_protocol_selfcheck`、`build_backend` 全部原样；后端模块开头原安全注释应精确改为下面完整docstring，不承诺所有序列化/内存无凭据。

```python
"""OpenAI 兼容后端（默认面向 MiniMax-M3）。

零第三方依赖：只用标准库 urllib —— core 保持零依赖（D6）。
需要 SDK 能力的场景再走 `icode-agent[llm]` extras。

安全边界：默认 repr 和公开模型调用错误隐藏敏感配置/原始失败详情；
请求凭据仍保存在实例字段中，只发往调用者选择的初始端点。
"""
```

- [x] **Step 5: GREEN、仅三源语法检查、自审与freeze，然后 writer STOP。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_backend_transport_privacy tests.test_runner.TestBackendFactory tests.test_runner.TestProxyStrategy tests.test_runner.TestBackendRetry -v
privacy_task1_pyc_dir=$(mktemp -d /tmp/icode-privacy-task1-pyc-XXXXXX)
PYTHONPYCACHEPREFIX="$privacy_task1_pyc_dir" /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m compileall -q -j 1 src/icode/backends/openai_compatible.py tests/test_backend_transport_privacy.py tests/test_runner.py
git diff --check
sha256sum src/icode/backends/openai_compatible.py tests/test_runner.py tests/test_backend_transport_privacy.py
sha256sum docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md
git diff -- src/icode/backends/openai_compatible.py tests/test_runner.py
```

Expected：指定suite实际exit0/0F/E/skip，原三类方法全部在；compile-j1/diff退出0；记录真实RED/GREEN、方法与子向量区别，三源SHA保持。writer先自己逐条SPEC再QUALITY自审，报告七维实际证据和任何风险，然后STOP。没有作者commit/push、20轮、DEFAULT/full、native/model；源后续变化使freeze与GREEN失效。

- [x] **Step 6: root派fresh独立SPEC，再派另一fresh QUALITY，均只读三源并STOP。**

两审都全文回读冻结设计/计划、实际三源及上下游，不用作者自审替代。SPEC检查missing/extra/mismatch和合同；QUALITY在SPEC通过后核毒化、真实opener矩阵、异常关闭/排序/Usage顺序与边界。各自可在writer停止后按Step5准确定点命令复验，并前后核SHA，禁止同时写源码。root汇总各C/I/M计数与真实结果；有问题派writer按具体证据修复并重冻结重审，不能越Task2。此步只授三源实现信用，不授CI覆盖/整片交付。

### Task 2: fresh writer仅两文件接入DEFAULT与配对选择

**状态**
- [x] 任务完成（全局 SPEC→不同 QUALITY 通过；完整软件验收与发布另列）

**Dependencies:** Task 1
**Parallelizable:** No (Task1三源已冻结且独立双审；Task2改两源后五源整体双审)

- [x] **Step 1: 全文回读两个选择文件；先增加完整配对方法。**

```bash
sed -n '1,240p' scripts/run_workspace_ci.py
sed -n '1,400p' tests/test_run_workspace_ci.py
sha256sum src/icode/backends/openai_compatible.py tests/test_runner.py tests/test_backend_transport_privacy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

在 `TestWorkspaceCiCoverage` 中加入下列完整方法，现有顶层import已经提供importlib和unittest，不增加import。此守卫核完整选择及静态skip标记；运行结果零skip须另核，不声称main新增动态skip拦截。

```python
    def test_backend_transport_privacy_selected_once_without_skips(self):
        name = "tests.test_backend_transport_privacy"
        self.assertEqual(DEFAULT_MODULES.count(name), 1)
        module = importlib.import_module(name)
        test_class = getattr(module, "TestBackendTransportPrivacy", None)
        self.assertTrue(isinstance(test_class, type))
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        self.assertTrue(methods)
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        expected = {name + ".TestBackendTransportPrivacy." + method for method in methods}
        actual = [test for selection in DEFAULT_MODULES
                  if selection == name or selection.startswith(name + ".")
                  for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual({test.id() for test in actual}, expected)
        self.assertEqual(len(actual), len(expected))
        for test in actual:
            self.assertIs(type(test), test_class)
            self.assertFalse(getattr(type(test), "__unittest_skip__", False))
            self.assertFalse(getattr(getattr(test, test._testMethodName), "__unittest_skip__", False))
```

- [x] **Step 2: 对选择次数取得具名有效 RED。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_backend_transport_privacy_selected_once_without_skips -v
```

Expected：一方法assertion FAIL，`DEFAULT_MODULES.count(name)`实际0≠1；import/fixture ERROR不能当RED。

- [x] **Step 3: apply_patch仅DEFAULT新增一项，完整tuple如下。**

```python
DEFAULT_MODULES = (
    "tests.test_workspace",
    "tests.test_workspace_hook_contract",
    "tests.test_windows_snapshot_rejection_diagnostic",
    "tests.test_backend_transport_privacy",
    "tests.test_autonomy",
    "tests.test_workbench",
    "tests.test_workbench_rejected_body",
    "tests.test_cli_resume_sandbox",
    "tests.test_shared_runtime_budget",
    "tests.test_contract_finalization",
    # Portable build/transport contracts only; host C fixtures are not native
    # Windows proof and are intentionally not selected as required coverage.
    "tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding",
    "tests.test_windows_direct_volume.TestWindowsDirectVolume",
    "tests.test_windows_build_context.TestWindowsBuildContext",
    "tests.test_windows_pe_capture.TestWindowsPeCapture",
    "tests.test_windows_pe_reader",
    *CONTRACT_ENGINEERING_TESTS,
    # Host/framework contracts are bounded; optional Go SDK diagnostics are
    # separate and do not stand in for native resource-scope acceptance.
    "tests.test_engineering_verification.TestEngineeringVerification",
    "tests.test_engineering_verification.TestEngineeringAdapters",
    "tests.test_engineering_verification.TestEngineeringResourceDispatch",
    "tests.test_engineering_verification.TestPythonIsolatedTemplate",
    "tests.test_engineering_evidence.TestEngineeringEvidence",
    "tests.test_engineering_evidence.TestEngineeringReceiptValidation",
    "tests.test_engineering_evidence.TestEngineeringEvidencePack",
    # Keep the integration matrix bounded while exercising task-tree capture,
    # result-commit binding, and receipt export/import on each workspace platform.
    *CROSS_PLATFORM_R3_TESTS,
    # The no-follow POSIX tree walker is shared by Linux and macOS; don't add
    # this POSIX-only Git differential to the Windows workspace test selection.
    *(POSIX_R3_TESTS if os.name == "posix" else ()),
)
```

这是完整tuple替换，除新增模块外逐字保留起草时全部旧选择。实施前按实际main核旧tuple，若前一片确有合法新增项必须保留并同步完整样例；不能删除/复制任何旧选择。`main`、CROSS_PLATFORM_R3_TESTS、POSIX策略和workflow原样。

- [x] **Step 4: 两文件GREEN、五源freeze、自SPEC→QUALITY，然后writer STOP。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_run_workspace_ci.TestWorkspaceCiCoverage tests.test_backend_transport_privacy tests.test_runner.TestBackendFactory tests.test_runner.TestProxyStrategy tests.test_runner.TestBackendRetry -v
privacy_task2_pyc_dir=$(mktemp -d /tmp/icode-privacy-task2-pyc-XXXXXX)
PYTHONPYCACHEPREFIX="$privacy_task2_pyc_dir" /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m compileall -q -j 1 scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
git diff --check
sha256sum src/icode/backends/openai_compatible.py tests/test_runner.py tests/test_backend_transport_privacy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
sha256sum docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md
git diff -- scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：实际exit0/0F/E/skip，前三源与Task1相同；五源SHA/顺序汇总冻结。writer仅改两个选择路径，自审后STOP，没有commit/push/full。执行者先记录七维结果，不用测试方法数量代替向量覆盖。

- [x] **Step 5: root fresh全局SPEC→另一fresh全局QUALITY，绑定同五源并STOP。**

两审全文回读设计、计划、五源和public下游，各前后核五SHA。SPEC先过且C/I/M0，再不同QUALITY核全片与原选择保留；各可复验Step4相同定点命令。需要修复则root限定writer路径，重新TDD/冻结/双审；不能用Task1双审抵整片审查。最终root复核source diff五路径，无不明extra/mismatch，才入Task3。

### Task 3: root软件验收、原完整守卫与文档冻结

**状态**
- [x] 任务完成（本机软件门；新SHA线上观察和平台/模型门另列）

**Dependencies:** Task 2
**Parallelizable:** No (所有writer STOP、同五源SHA；定点→20轮→DEFAULT→ORIGINAL完整preflight必须串行)

- [x] **Step 1: root独立定点核原三类、新模块、loop和CI选择。**

```bash
sha256sum src/icode/backends/openai_compatible.py tests/test_runner.py tests/test_backend_transport_privacy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_runner.TestBackendFactory tests.test_runner.TestProxyStrategy tests.test_runner.TestBackendRetry tests.test_backend_transport_privacy tests.test_run_workspace_ci.TestWorkspaceCiCoverage tests.test_loop -v
```

Expected：实际exit0，新增portable零skip；既有loop环境skip如实单列，不预填“全部native”。root另静态核CLI `_build_runner`/active_proxy和BackendError捕获未改变、loop原error传播未改变、构造/默认/model/tool_choice调用参数相同。不运行模型HTTP或访问KEY。

- [x] **Step 2: 定点结束后串行20轮，每轮新suite，失败/skip阻断。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -c 'import sys, unittest
names = ("tests.test_backend_transport_privacy", "tests.test_runner.TestBackendFactory", "tests.test_runner.TestProxyStrategy", "tests.test_runner.TestBackendRetry", "tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_backend_transport_privacy_selected_once_without_skips")
total = 0
for round_number in range(1, 21):
    print("backend transport privacy round", round_number, flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    total += result.testsRun
    print("actual", result.testsRun, "failures", len(result.failures), "errors", len(result.errors), "skips", len(result.skipped), flush=True)
    if not result.wasSuccessful() or result.skipped:
        sys.exit(1)
print("actual aggregate", total, flush=True)'
```

Expected：20轮各实际0F/E/skip，累计实际执行次数单列，不称新增方法。任何源变动使20轮信用失效并回五源双审/定点，不先猜结果数。

- [x] **Step 3: 20轮结束后DEFAULT，再原三道完整preflight。**

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/run_workspace_ci.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py
```

Expected：两命令先后实际exit0，原secrets/submodule/tests三道通过。原tests唯一内部调用必须保持 `[sys.executable, "-m", "unittest"]`，cwd=str(REPO)、capture_output=True、text=True、encoding="utf-8"、errors="replace"、shell=False；与父当前诊断使用的ORIGINAL合同相同。不能筛模块、修改sys.executable/kwargs/环境、重复执行原子调用再择优。可沿root既有只读wrapper截获这次原subprocess的完整summary，每调用实际仅执行一次，保留返回码与argv/kwargs；preflight尾部不能代替完整total/F/E/skip。每60秒内报进度，不同时启动第二套全量。

- [x] **Step 4: compile-j1仅仓外缓存，治理/site/landscape/diff。**

```bash
privacy_pyc_dir=$(mktemp -d /tmp/icode-privacy-pyc-XXXXXX)
PYTHONPYCACHEPREFIX="$privacy_pyc_dir" /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m compileall -q -j 1 src scripts tests
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_governance.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_site.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
sha256sum src/icode/backends/openai_compatible.py tests/test_runner.py tests/test_backend_transport_privacy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：各实际exit0，五源同freeze。缓存路径由mktemp实际绑定，不递归删除。landscape只证结构/日期，root阶段记录需区分固定源码/官方文档与设计提案，实际已核相关条目，不授20上游全刷新信用。

- [x] **Step 5: root按实测更新本计划/landscape，再连续两轮相关文档clean。**

root全文读 `/home/orbbec/.agents/skills/doc-contract-consistency-audit/SKILL.md` 后使用，apply_patch精确更新本计划验收履历与 `docs/agent-landscape-live.md` 相关条目；冻结设计/研究不改，相关事实不回写为旧观察时间的实测。记录实际main/五SHA、RED/GREEN、两轮独立审查、每轮测试total/F/E/skip、软件门和仍未通过原生/模型门。文档写入内容必须来自已实际取得证据，不能预置完成模板。两命令第一次完成后审查每项，才第二次。

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-r3-provider-transport-privacy.md docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md docs/nbl/specs/2026-10-09-provider-endpoint-and-secret-research.md docs/agent-landscape-live.md
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B /home/orbbec/.agents/skills/doc-contract-consistency-audit/scripts/check_consistency.py docs/nbl/plans/2026-10-09-r3-provider-transport-privacy.md docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md docs/nbl/specs/2026-10-09-provider-endpoint-and-secret-research.md docs/agent-landscape-live.md
```

Expected：两轮各0疑似项，人工再核错误闭集/subclass顺序、响应usage记账、repr与memory边界、5×5×3redirect矩阵、静态无skip标记和真实零skip信用分开、旧默认domain不变与未来main绑定。若新root相关证据文档确有必要，先说明精确路径/内容，在两轮清单中逐一补入；不做目录扫全替代精确范围。

- [x] **Step 6: 最终文档/五源freeze，重验secrets/vendor/治理。**

```bash
sha256sum src/icode/backends/openai_compatible.py tests/test_runner.py tests/test_backend_transport_privacy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
sha256sum docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md docs/nbl/specs/2026-10-09-provider-endpoint-and-secret-research.md docs/nbl/plans/2026-10-09-r3-provider-transport-privacy.md
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_governance.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_site.py
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/check_agent_landscape.py --today 2026-10-09
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py --only secrets
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B scripts/preflight.py --only submodule
git diff --check
git -C vendor/icode-skill status --porcelain
git -C vendor/icode-skill rev-parse HEAD
git ls-files -s vendor/icode-skill
```

Expected：各actual0，五源与独立审查和software相同，设计/研究输入SHA保持，vendorclean/head=gitlink。源变化回Task1/2并双审/软件重验；文档变化回Step5两轮，禁止在finalguard后悄改source。

### Task 4: root精确main发布与fresh源SHA跨平台观察

**状态**
- [x] 任务完成（仅 provider transport/privacy 切片；R2/R3 总门、真实模型和原生整体门仍独立）

**Dependencies:** Task 3
**Parallelizable:** No (只有完整软件门通过后发布，fresh观察必须绑定实际发布SHA)

- [x] **Step 1: root全文核实际diff和index范围，精确暂存。**

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
git diff -- src/icode/backends/openai_compatible.py tests/test_runner.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
git add -- src/icode/backends/openai_compatible.py tests/test_runner.py tests/test_backend_transport_privacy.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
git add -- docs/agent-landscape-live.md
git add -f -- docs/nbl/plans/2026-10-09-r3-provider-transport-privacy.md docs/nbl/specs/2026-10-09-r3-provider-transport-privacy-design.md
git diff --cached --name-only
git diff --cached --check
git diff --cached --stat
```

研究若已由构建诊断发布则原SHA保持，不重复纳提交；若尚未入库且确是本片必要记录，root先核既有owner/来源与最终文档门后才精确暂存该路径。上述候选不授权未知dirty、其它ticket或先前未验证修改入库；不使用git add . / -A、不创建分支、不改vendor。root逐一核index bytes等于已验工作树、五源SHA匹配、main父为Task1实际绑定；force-add仅上述已审新plan/spec路径。范围不匹配必须停发布定位，不能混入。

- [x] **Step 2: root依既有授权commit/push main，验证远端精确SHA。**

```bash
git commit -m "fix(backend): protect transport credentials and public failures"
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short
```

Expected：actual成功，新HEAD与remote main相同，记录父SHA/sourceSHA/精确路径；剩余无关dirty如实说明。push失败先定位实际权限/检查，不forcepush，不创建新rights、release、PyPI/vendor提交。发布前SOURCE不能变化；用户既有授权无需再次例行等待，不绕任何自动审批或测试拒绝。

- [x] **Step 3: fresh独立只读观察者绑定新SHA的现有CI，root另核。**

```bash
privacy_commit=$(git rev-parse HEAD)
gh run list --commit "$privacy_commit" --limit 30 --json databaseId,headSha,workflowName,status,conclusion,url
```

用返回的实际run ID逐一执行只读命令，不能预填旧run或job。以下完整Python程序从gh的JSON读取实际ID并输出绑定元数据/decoded日志；只选择本SHA已有 `CI` workflow，其他workflow先由root读实际名称再准确观察，不调用dispatch/rerun/cancel。

```bash
/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -c 'import json, subprocess, sys
commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
runs = json.loads(subprocess.run(["gh", "run", "list", "--commit", commit, "--limit", "30", "--json", "databaseId,headSha,workflowName,status,conclusion,url"], check=True, capture_output=True, text=True).stdout)
matching = [run for run in runs if run["headSha"] == commit and run["workflowName"] == "CI"]
if not matching:
    raise SystemExit("No exact-source CI run observed; retain pending observation")
for run in matching:
    run_id = str(run["databaseId"])
    detail = json.loads(subprocess.run(["gh", "run", "view", run_id, "--json", "headSha,status,conclusion,jobs,url"], check=True, capture_output=True, text=True).stdout)
    if detail["headSha"] != commit:
        raise SystemExit("Source binding mismatch")
    print(json.dumps(detail, ensure_ascii=False), flush=True)
    if detail["status"] != "completed":
        print("Exact-source run remains pending", flush=True)
        continue
    log = subprocess.run(["gh", "run", "view", run_id, "--log"], check=True, capture_output=True, text=True)
    print(log.stdout, flush=True)'
```

Expected：真实新SHA/checkouts/vendor、workflow/run/job/image/Python均绑定，Linux/macOS/Windows workspace日志分别读取完整summary，新模块实际零skip、完整选择且不漏关键向量；其它既有failed/skipped格如实分列，不用旧成功抵本窗口失败。观察者与root独立读取，长run使用产品等待机制/≤60秒更新，不重复提交或自动重跑。CI全文日志不是凭据遍历，不读取secret环境/KEY。若实际workflow名称不是CI，先read-only列表确认后精确替换该常量并记录，不因无匹配新触发任务。新SHA软件协议边界不证明模型1→6、≥90%能力一致性、KEY地区/端点资格、R2资源/隔离或原生整体门；未取得结果保持未勾选。

## 交付自检与信用限制

【架构级自检报告】须由root填实际证据，不用模板冒称“异常全覆盖/可运行100%”。

- [x] 语法/编译：实际指定/全仓compile-j1，缓存仓外。
- [x] 依赖/调用链：Backend/build_backend/constructor签名及CLI/loop原调用相同，DEFAULT旧项保持。
- [x] 逻辑/边界：真实redirect矩阵和200正控、状态精确int/unknown、Usage顺序与工具_raw正控实际通过。
- [x] 异常处理：poison不读原详情、普通close不覆盖，ME/KI/SE传播、decode/已知响应异常安全失败，重试次数/backoff/URL实际保持。
- [x] 关联模块：五源独立全局SPEC→不同QUALITY C0/I0/M0，其他runner/config/base/native/vendor/workflow未改。
- [x] 兼容安全：成功payload/auth/tools/choice/usage与旧参数/default保持，明列3xx拒绝/公开错误变更；内存/任意序列化不授安全信用。
- [x] 可运行性（本机）：实际RED→GREEN、root定点/20/DEFAULT/ORIGINAL三道同freeze；发布/新SHA各平台软件观察已取得本片 CI/provenance/Pages 证据，实际模型与R2/R3总门仍独立。

计划作者静态自审：逐条覆盖映射齐全；所有代码步骤给完整代码块或准确完整替换方法，Task2完整tuple保留原余项；helper/classes/import均定义，public签名/default和Usage顺序一致；RED为具名assertion而非fixture ERROR；仅作者计划文件可写。AST检查只解析去共同缩进的Python代码块，不执行它们；不把静态解析算实施或测试。root后续计划双审绑定最终本文件SHA。

---
## root实施窗口（2026-10-09）

上一单方法JSON测试兼容片已经独立双审、软件门、精确三路径提交推送：main `cad0eb17b206ce276b325f3209ff601480be06d8`，parent ef43，tree a17e4f865eba846a9bafa8a376a5f9f5081d62ab；root远端only-main/官方main与commit各独立核相等。修后DEFAULT539P零skip、原完整2394total/2335P/59环境skip/0F/E/484.328s，原tests子调用一次/argv及kwargs保持、三道通过；不混用ef43旧修前记录。CI37865969420 已终态37success/4failure/3停用workflow job skip；provenance37865969446 已5/5success；Pages37865969489 已2/2success，fresh观察者全部STOP。root另核终态run/jobs/artifacts、双Python全文日志及决定性summary、四失败决定性日志和四签名日志，后述证据不替原生门。Pages部署job113612691285/source cad0/artifact11587913198/313410B/ZIP sha256 ca5defef3def8b11268adb4fe83a17a7004bfe4d91db5e886b222e2767e4a75f，00:41:44.925Z Reported success（日志split计67行、physical66行）。不重复查询旧终态窗口。

cad0 root 独立日志：Python3.11.17/3.12.15 完整套件各2394total/2323P/71环境skip/0F/E，分别563.313/494.515s，bootstrap字节绑定PASS。Windows workspace x64/ARM64 各533total/511P/1F/1E/20skip，343.551/352.608s，仍Git10093与10038；快照诊断均只证.git listing差异mask16与第二次root完成，不推写入者/Defender/根因。两Reviewer各先10P再native1F，exit78/cleanuptrue/token null；双栈10035/wait_expired而非connect_denied，WFP subscribe5不可用。x64 runner target_unavailable/inconclusive，ARM64 target valid/observer ready但no_matching_event，二者均无DENY信用。root未另读本窗口Linux/macOS workspace/native日志，只保留独立观察者报告；不能把签名通过称R2/R3整体通过。

cad0四签名格 root 独立回读各完整capture JSON、19阶段脚本PASS和实际attestation/upload行，解析capture均parse_complete/runtime_load_verified/source_launch_verified=false；CAPTURED状态authority none，JSON没有production_authority字段。root在已取得日志与API metadata之间另作精确相等比较：capture helper SHA等attestation subject；artifact ID/ZIP digest/大小均相等、source均cad0。x64py3.11 job113615716206/helper69af1f2d5ebfce7310f6474fcdd0593c2c5b49e544a7414fe2c81494e736452d/artifact11588363797；x64py3.12 job113615716230/helper41a3561d4ff476a3cb7d92444ae50693980b304bb383ce5eb5320d9d7d613fa8/artifact11588931192；ARM64py3.11 job113615716247/helper1df60b3e25bae9cb897c0b914f6c22c1064a75d97277152d25432014a71abb16/artifact11589135712；ARM64py3.12 job113615716254/helperf27926313623bcd8eed80a07f5b3f6043b06ce05672f1eafb6deb2ac815b3cab/artifact11588149673。没有下载/解码/独立执行成品，不给完整PE或生产加载准入信用。签名validate静默完整guard不提供套件总数，保持unknown，不借root本机或别job数字补齐。

Task1 fresh唯一作者已重绑上述main与vendor1693651 clean；原backend/test_runner/两CI源SHA仍与本计划起草一致，冻结设计9edf53ff、计划实施前54d26cee、旧研究1ebeeda0。结构化需求/方案/风险root127–129：问题真实、旧代理/重试/Usage可复用，保护公开错误链而不授私有对象安全；单writer TDD→fresh SPEC→不同QUALITY→CI接线→完整守卫，禁止源码写入与全量测试并行。用户main-only、自主阶段及不例行等待覆盖skill默认worktree/逐任务提交要求；其余门不覆盖。

并行定点研究已经独立证据复核C0/I0/M0 STOP，[阶段刷新](../specs/2026-10-09-provider-transport-upstream-refresh.md) SHA0e8042260e94239b1aabdce31a31976e770c2631990ea62b4fea9d59e9a15ddc，必须纳入本片精确文档清单/后续两轮clean。它明确22ebb0f固定源码与00:44 UTC发现main前进b6e8a2e的时间区分，七文件same由独立研究/复核核，root只认两文件；不修改本片冻结全部3xx拒绝策略、不增加依赖/权限/模型端点或上游代码复制。下一工作台provider只读预研另行并行，不混入当前五源。

Task1 作者 RED：生产源仍ee042时四命名断言实际4tests/61F/0E/skip/0.053s/exit1；全19在修复框架poison fixture后119F/0E/skip/0.094s，仍原生产SHA；另在内存加载cad0原源码复验119F/0E/skip/0.097s。307/308共30redirect子向量原本已拒绝，无新增RED信用；301/302/303才为新拒绝边界。首GREEN旧三class23+新19=42P/0F/E/skip/0.077s，收紧fixture后0.081s，实际CLI出口正控加强后0.084s、最终0.087s。poison不作栈/调用范围豁免，私有cause/context访问仅记录并返回以兼容unittest，touched仍核空；str/repr/args/reason/url/headers/msg/body/read保持记录并抛。RED 是作者实际执行证据，不冒充 root 独立重跑。

Task1 fresh SPEC 首次42P/0F/E/skip/0.085s，C0/I0/M1：两处 docstring 超出限定公开展示边界。唯一作者只修为计划精确文本，逆替换可还原原审源码，去该两说明的 AST SHA742b5e1f9aa78e6993bd12c8356898a72108da5d33f94abbe274c9244fa2806c 不变；作者修后42P/0.088s、自审SPEC FIXED→PASS及QUALITY PASS/STOP。原独立 SPEC 修后42P/0.095s C0/I0/M0/STOP；不同 fresh QUALITY 全文三源/设计/计划及公开链，42P/0.084s C0/I0/M0/STOP。每次 exit0、0F/E/skip；不把说明修正授新功能 RED。root 全文回读 backend/newtests、旧三类及 diff，三源 compile-j1 exit0，缓存 /tmp/icode-privacy-task1-root-pyc-WuEYot，diff-check0；未以定点替代完整软件门。

Task2 fresh 作者仅两 CI 文件：具名 guard 在原 runner e3cb0c27 上取得1test/1F/0E/skip/0.000s/exit1；增加唯一 DEFAULT 后指定五组63P/0F/E/skip/0.145s/exit0，作者自 SPEC→QUALITY C0/I0/M0 后复跑63P/0.128s/exit0，两源 compile-j1/diff-check0，缓存 /tmp/icode-privacy-task2-pyc-AkrvX3，STOP。root 派发提示曾误写不存在的 tests.test_runner 插入锚点，作者在生产选择编辑前提出，root 按冻结计划纠正为 snapshot_rejection_diagnostic 后/autonomy 前；不是规格变更。逆删除唯一新增行/完整 guard 可逐字还原原两个文件；未新增 runner 整模块或动态 skip 门。root 全文核两源及 diff；fresh 全局 SPEC→不同 QUALITY 和 Task3 软件验收仍待实际结果。

五源冻结：backend332行 SHA8f69083a07c33127fd6993ff5f8e3d1b4ff861895a9cd64bbfee11ce39ebe541；test_runner2186行 SHA75dbf49d196dfc822e14c29436635cfaa56bacc4c57476321e522d9218b91d3e；privacy621行 SHA8958a848bf28f1fbf1d7ce9941c5394347104c59e32dae7d34e65344ae6d7282；CI runner187行 SHA2c76012c1de3f0283f8721ff577a5f9c9bac2012d8c73a0a86507488ec689279；coverage346行 SHA6a0444a9f8fd2960b4444dc4225a44ac3baa8bd06572b063737ae4bb7d2b439d。root再次逐一SHA匹配，main cad0/vendor1693651不变。设计冻结9edf53ff不变；本文勾选仅实际完成步骤，不预填整片或平台/模型准入。

全局 fresh SPEC 实际全文设计63/当时计划1287/五源及公开 base/loop/CLI，唯一授权组合63total/63P/0F/E/skip/0.128s/exit0，C0/I0/M0/STOP，计划当时SHA12a2da4c。随后不同 fresh QUALITY 全文设计63/根实际步骤更新后计划1293/同五源和调用链，63total/63P/0F/E/skip/0.131s/exit0，C0/I0/M0/STOP。五源及设计前后均匹配上述冻结，main cad0/vendor1693651 clean；仅计划勾选和实际履历元数据变化，无规格或源码改变。两审不是 Task1 双审替身，也未运行完整软件门。

root 同 freeze 关联组合实测100total/100P/0F/E/skip/0.187s/exit0；verbose输出有中段截断，只认实际完整summary，不宣称全文日志回读。串行20轮每轮新suite，实际各43total/43P/0F/E/skip，unittest耗时按轮为0.091、0.079、0.085、0.081、0.088、0.087、0.078、0.086、0.083、0.101、0.080、0.088、0.094、0.077、0.089、0.079、0.085、0.090、0.080、0.089秒，累计860次，exit0。75重定向和6正控为每方法子向量，不重复计为方法。

root 本窗口软件门：DEFAULT实际558total/558P/0F/E/skip/162.812s/exit0，安装bootstrap verifier字节绑定PASS。随后原完整preflight实际2414total/2355P/59既有环境skip/0F/E/490.568s/exit0；原tests子调用恰好一次，argv/kwargs精确原样、原result对象原样返回并finally还原观察wrapper；child实测wall490.821486768s，整preflight492.151501238s，三道全部通过及bootstrap字节绑定PASS。不是筛模块或重复full择绿。全仓compileall src/scripts/tests -j1 actual0，wall0.800425152s，缓存仅 /tmp/icode-privacy-root-pyc-Mbxp91；治理/site/landscape排期/diff-check各actual0，五源仍匹配冻结。landscape结构/20项排期通过不等于20上游源码已重查。文档两轮、最终守卫和精确main发布尚待；未读取真实KEY或调用模型，不授模型/原生/R2R3总门信用。

**Execution Mode:** serial

提交前本机收尾：五份精确相关文档（本计划、冻结设计、旧研究、上游阶段刷新、landscape）连续两轮各0疑似项/exit0；人工复核闭类别顺序/Usage/75子向量、静态skip与实际零skip、默认端点不变、memory与公开文本边界。最终secrets/submodule、治理/site/landscape和diff-check各actual0，vendor1693651 clean/head=gitlink，设计及两研究SHA保持、五source freeze不变。以上 Task3 勾选仅此软件范围；元数据收尾后重跑文档两轮和最终守卫，不重跑原完整测试。本文正文及设计中的早期“尚未实施/待双审/待完整守卫”是起草/作者STOP时点，实际后续记录以本履历为准。下一步按用户既有授权精确9路径发布：五源、landscape、本计划、冻结设计、上游阶段刷新；旧研究已在ef43发布，保持原SHA且不重复暂存。root没有对真实模型、90%或未通过的原生门勾选。

四任务为纯链：fresh Task1 writer→作者自审STOP→fresh SPEC→不同QUALITY→fresh Task2 writer→作者自审STOP→fresh全局SPEC→不同全局QUALITY→root完整软件守卫→root发布/新SHA观察。复杂业务边界、多文件、真实urllib负控，不满足inline；没有可并行写入/全量测试阶段。用户与root明确要求本计划作者freeze后STOP，覆盖writing-plans默认自动调用执行技能；计划作者不自行派发、实施或阶段handoff。

### Task 4 实际发布与新 SHA 观察（2026-10-10）

本片生产实现已由 `6ded1d3c16c265fda16fa6506cb57c29067b5fbd`（parent `cad0eb17b206ce276b325f3209ff601480be06d8`）发布到 `main`；随后 `f0d06c8167cc148c6dcdea3f1a566bf4ffc7a7a8` 仅修正文档中的上一轮 CI 统计，未改动五源生产代码。工作树及 `origin/main` 均精确绑定 f0d06c8，vendor gitlink 保持 `1693651c1bd7daad3272eb054f0f81d6f254d08d`。

fresh 只读观察者绑定 f0d06c8 取得以下终态（没有 dispatch、rerun、cancel，也未下载签名制品）：

- CI [38009094454](https://github.com/ayukyo/icode/actions/runs/38009094454)：`failure`，39 success / 2 failure / 3 skipped。唯一失败是 Windows Reviewer snapshot candidate：x64 job `114084780908` 与 ARM job `114084781092`，均为临时标准用户候选步骤 exit 78，双栈 `10035` / `wait_expired`，`cleanup_ok=true`；没有 DENY 事件信用。Python 3.11 与 3.12 完整套件均为 2527 tests、71 skipped、成功；双 Windows workspace 成功。该失败保持为观察边界，不通过放宽断言或解析 stderr 记为成功。
- Windows helper provenance [38009094416](https://github.com/ayukyo/icode/actions/runs/38009094416)：`success`，5 jobs success（validate 加 x64/ARM × Python 3.11/3.12 四矩阵）。四矩阵日志均确认安装制品密码学 provenance、离线验证器、密码学负控拒绝和 signed-mode wheel 导出通过；日志明确不是产品启动授权，未授予完整 PE/生产加载准入信用。
- Pages [38009094547](https://github.com/ayukyo/icode/actions/runs/38009094547)：`success`，2 jobs success。

本切片因此完成“代码→本机软件门→main→新 SHA 跨平台观察”的证据链，但不把 CI/provenance/Pages 结果升级成 R2/R3 总验收、模型 1→6 或 ≥90% 能力一致性、原生隔离/资源门、Windows Reviewer DENY 或真实 KEY 可用性证明。
