"""Portable, offline contracts for model transport and public error privacy."""

from __future__ import annotations

import http.client
import inspect
import io
import json
import socket
import traceback
import unittest
import urllib.error
import urllib.request
import urllib.response
from contextlib import contextmanager, redirect_stderr
from dataclasses import MISSING, fields
from email.message import Message
from pathlib import Path
from unittest import mock

from icode.backends import BackendError, OpenAICompatibleBackend
from icode.backends.base import Backend
from icode.backends.openai_compatible import DEFAULT_BASE_URL, DEFAULT_MODEL
from icode.guard import Guard, Scope
from icode.loop import AgentLoop
from icode.tools import ToolContext, ToolRegistry


# These credentials and domains are synthetic. No fixture accesses a real key.
SECRET = "SYNTHETIC-凭据-\u202ePRIVATE\nsecond-line"
MARKERS = ("SYNTHETIC", "凭据", "PRIVATE", "second-line", "proxy-user", "proxy-pass")
BASE_URL = "https://origin.invalid/v1"
PROXY = "http://proxy-user:proxy-pass@proxy.invalid:8123"
MESSAGES = [{"role": "user", "content": "offline request"}]
OK_DATA = {"choices": [{"message": {"content": "ok"}}]}


def _response(data=OK_DATA, *, url=BASE_URL + "/chat/completions", code=200,
              location=None, body=None):
    headers = Message()
    headers["Content-Type"] = "application/json"
    if location is not None:
        headers["Location"] = location
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8") if body is None else body
    response = urllib.response.addinfourl(io.BytesIO(raw), headers, url, code)
    response.msg = "offline response"
    return response


def _request_record(req, timeout):
    return {
        "url": req.full_url, "method": req.get_method(), "body": req.data,
        "authorization": req.get_header("Authorization"), "timeout": timeout,
        "selector": req.selector, "host": req.host,
        "tunnel_host": req._tunnel_host,
    }


class _OfflineTransport:
    """Catch every HTTP(S) URL below real urllib request/error processing."""

    def __init__(self, initial_url, *, code=200, location=None):
        self.initial_url = initial_url
        self.code = code
        self.location = location
        self.records = []

    def open(self, req):
        self.records.append(_request_record(req, req.timeout))
        if req.full_url == self.initial_url:
            return _response(url=req.full_url, code=self.code, location=self.location)
        # A followed redirect is recorded, including forwarded Authorization.
        # Unknown URLs also fail locally rather than falling through to a socket.
        return _response(url=req.full_url, code=404)


class _OfflineHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, transport):
        super().__init__()
        self.transport = transport

    def http_open(self, req):
        return self.transport.open(req)


class _OfflineHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, transport):
        super().__init__()
        self.transport = transport

    def https_open(self, req):
        return self.transport.open(req)


class _SequenceOpener:
    """Ordinary transport failures are injected at the external I/O boundary."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.records = []

    def open(self, req, timeout=None):
        self.records.append(_request_record(req, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _PoisonFormatting:
    def __str__(self):
        self.touched.append("str")
        raise AssertionError("original exception must not be formatted")

    def __repr__(self):
        self.touched.append("repr")
        raise AssertionError("original exception must not be formatted")

    def __getattribute__(self, name):
        # Frameworks inspect private links while reporting a failing test.
        # Record these reads instead of throwing, so RED can be reported. This
        # also detects production reads; no caller or stack-based bypass exists.
        if name in {"__cause__", "__context__"}:
            object.__getattribute__(self, "touched").append(name)
            return super().__getattribute__(name)
        if name in {"args", "reason", "url", "headers", "msg", "body"}:
            object.__getattribute__(self, "touched").append(name)
            raise AssertionError("original exception properties must not be read")
        return super().__getattribute__(name)


class _PoisonHTTPError(_PoisonFormatting, urllib.error.HTTPError):
    def __init__(self, code, close_error=None):
        super().__init__(BASE_URL + "/" + SECRET, code, SECRET, {}, io.BytesIO(SECRET.encode()))
        self.touched = []
        self.code_reads = 0
        self.close_calls = 0
        self.close_error = close_error

    def __getattribute__(self, name):
        if name == "code":
            object.__setattr__(self, "code_reads", object.__getattribute__(self, "code_reads") + 1)
        return super().__getattribute__(name)

    def read(self, *args, **kwargs):
        self.touched.append("read")
        raise AssertionError("HTTP error response body must not be read")

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


def _poison_exception(kind):
    cls = type("SyntheticDynamicSecretException", (_PoisonFormatting, kind), {})
    if issubclass(kind, json.JSONDecodeError):
        exc = cls(SECRET, SECRET, 0)
    elif issubclass(kind, UnicodeDecodeError):
        exc = cls("utf-8", SECRET.encode(), 0, 1, SECRET)
    else:
        exc = cls(SECRET)
    exc.touched = []
    return exc


class TestBackendTransportPrivacy(unittest.TestCase):
    def setUp(self):
        for patcher in (
            mock.patch("urllib.request.getproxies", return_value={}),
            mock.patch("urllib.request.proxy_bypass", return_value=False),
            mock.patch("urllib.request.getproxies_environment",
                       side_effect=AssertionError("host proxy environment forbidden")),
            mock.patch("socket.create_connection", side_effect=AssertionError("network forbidden")),
            mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")),
            mock.patch.object(socket.socket, "connect_ex", side_effect=AssertionError("network forbidden")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def backend(self, **kwargs):
        options = dict(api_key=SECRET, model="offline-model", base_url=BASE_URL,
                       max_retries=0, timeout=23, retry_backoff=0.25)
        options.update(kwargs)
        return OpenAICompatibleBackend(**options)

    def assert_private(self, text):
        for marker in MARKERS:
            self.assertNotIn(marker, text)
        self.assertNotIn(BASE_URL, text)
        self.assertNotIn(PROXY, text)

    def capture_error(self, backend):
        try:
            backend.complete(MESSAGES)
        except BackendError as exc:
            self.assert_private(str(exc))
            return exc
        except Exception as exc:
            # A production exception leak is an assertion RED, not a fixture E.
            self.fail("expected safe BackendError, got " + type(exc).__name__)
        self.fail("expected transport/response failure")

    def assert_fatal(self, backend, fatal):
        try:
            backend.complete(MESSAGES)
        except BaseException as caught:
            self.assertIs(caught, fatal)
        else:
            self.fail("fatal transport exception must propagate")

    @contextmanager
    def sequence(self, backend, outcomes):
        opener = _SequenceOpener(outcomes)
        with (mock.patch.object(backend, "_opener", return_value=opener),
              mock.patch("icode.backends.openai_compatible.time.sleep") as sleep):
            yield opener, sleep

    @contextmanager
    def real_transport(self, backend, *, code=200, location=None):
        transport = _OfflineTransport(backend.base_url + "/chat/completions",
                                      code=code, location=location)
        build_opener = urllib.request.build_opener

        def offline_opener(*handlers):
            opener = build_opener(*handlers, _OfflineHTTPHandler(transport),
                                  _OfflineHTTPSHandler(transport))
            self.assertIsInstance(opener, urllib.request.OpenerDirector)
            self.assertTrue(any(isinstance(h, urllib.request.HTTPErrorProcessor)
                                for h in opener.handlers))
            return opener

        with (mock.patch("urllib.request.build_opener", side_effect=offline_opener),
              mock.patch("icode.backends.openai_compatible.time.sleep") as sleep):
            yield transport, sleep

    def assert_request(self, record, backend, *, proxied=False):
        url = backend.base_url + "/chat/completions"
        self.assertEqual(record["url"], url)
        self.assertEqual(record["method"], "POST")
        self.assertEqual(record["authorization"], "Bearer " + SECRET)
        self.assertEqual(record["timeout"], backend.timeout)
        self.assertEqual(json.loads(record["body"])["messages"], MESSAGES)
        if proxied and url.startswith("http:"):
            self.assertEqual(record["host"], "proxy.invalid:8123")
            self.assertEqual(record["selector"], url)
            self.assertIsNone(record["tunnel_host"])
        elif proxied:
            self.assertEqual(record["host"], "proxy.invalid:8123")
            self.assertEqual(record["selector"], "/v1/chat/completions")
            self.assertEqual(record["tunnel_host"], "origin.invalid")
        else:
            self.assertEqual(record["host"], "origin.invalid")
            self.assertEqual(record["selector"], "/v1/chat/completions")
            self.assertIsNone(record["tunnel_host"])

    def test_repr_and_constructor_contract(self):
        parameters = inspect.signature(OpenAICompatibleBackend).parameters
        self.assertEqual(tuple(parameters), (
            "api_key", "model", "base_url", "timeout", "temperature", "proxy", "no_proxy",
            "max_retries", "retry_backoff", "name", "usage", "last_usage",
        ))
        expected_defaults = {"model": "", "base_url": "", "timeout": 180,
                             "temperature": None, "proxy": None, "no_proxy": False,
                             "max_retries": 2, "retry_backoff": 1.5,
                             "name": "openai-compatible"}
        self.assertIs(parameters["api_key"].default, inspect.Parameter.empty)
        for name, value in expected_defaults.items():
            self.assertEqual(parameters[name].default, value)
        backend = self.backend(base_url=BASE_URL + "/" + SECRET, proxy=PROXY + "/" + SECRET)
        self.assertEqual(backend.api_key, SECRET)
        self.assertEqual(backend.base_url, BASE_URL + "/" + SECRET)
        self.assertEqual(backend.proxy, PROXY + "/" + SECRET)
        self.assertIsInstance(backend, Backend)
        self.assert_private(repr(backend))
        self.assert_private(str(backend))
        by_name = {item.name: item for item in fields(backend)}
        self.assertIs(by_name["api_key"].default, MISSING)
        for name in ("api_key", "base_url", "proxy"):
            self.assertFalse(by_name[name].repr)
        self.assertEqual(DEFAULT_BASE_URL, "https://api.minimaxi.com/v1")
        self.assertEqual(DEFAULT_MODEL, "MiniMax-M3")

    def test_proxy_policy_and_mapping(self):
        env = {"https": PROXY + "/path?token=" + SECRET + "#fragment", "http": "http://env.invalid"}
        with mock.patch("urllib.request.getproxies", return_value=env):
            for options, description, mapping in (
                ({"no_proxy": True, "proxy": PROXY}, "禁用（强制直连）", {}),
                ({"proxy": PROXY}, "已配置（显式代理）", {"http": PROXY, "https": PROXY}),
                ({}, "已配置（环境代理）", env),
            ):
                with self.subTest(policy=description):
                    backend = self.backend(**options)
                    self.assertEqual(backend.active_proxy(), description)
                    self.assertEqual(backend._proxy_mapping(), mapping)
                    self.assert_private(backend.active_proxy())
        self.assertEqual(self.backend().active_proxy(), "无")

    def test_proxy_hint_never_formats_exception(self):
        for options in ({}, {"proxy": PROXY}, {"no_proxy": True}):
            for env in ({}, {"https": PROXY}, {"http": PROXY}):
                with self.subTest(explicit=bool(options), environmental=bool(env)):
                    exc = _poison_exception(RuntimeError)
                    with mock.patch("urllib.request.getproxies", return_value=env):
                        hint = self.backend(**options)._proxy_hint(exc)
                    self.assertEqual(exc.touched, [])
                    self.assert_private(hint)
                    if not options and env:
                        self.assertIn("--no-proxy", hint)
                        self.assertIn("ICODE_LLM_NO_PROXY=1", hint)
                    else:
                        self.assertEqual(hint, "")

    def test_real_opener_redirect_matrix(self):
        locations = ("https://origin.invalid/elsewhere", "https://other.invalid/elsewhere",
                     "https://origin.invalid:444/elsewhere", "../relative", "http://origin.invalid/downgrade")
        total = 0
        for policy in ("direct", "explicit", "environment"):
            options = {"no_proxy": True} if policy == "direct" else {"proxy": PROXY} if policy == "explicit" else {}
            env = {"http": PROXY, "https": PROXY} if policy == "environment" else {}
            for code in (301, 302, 303, 307, 308):
                for location in locations:
                    with self.subTest(policy=policy, status=code, location=location):
                        backend = self.backend(max_retries=2, **options)
                        with mock.patch("urllib.request.getproxies", return_value=env):
                            with self.real_transport(backend, code=code, location=location) as (transport, sleep):
                                error = self.capture_error(backend)
                        self.assertIn("HTTP " + str(code), str(error))
                        self.assertEqual(len(transport.records), 1, "redirect destination must never be reached")
                        self.assert_request(transport.records[0], backend, proxied=policy != "direct")
                        self.assertEqual(backend.usage.retries, 0)
                        sleep.assert_not_called()
                        total += 1
        self.assertEqual(total, 75)

    def test_real_opener_success_control(self):
        for scheme in ("http", "https"):
            for policy in ("direct", "explicit", "environment"):
                with self.subTest(scheme=scheme, policy=policy):
                    options = {"no_proxy": True} if policy == "direct" else {"proxy": PROXY} if policy == "explicit" else {}
                    env = {"http": PROXY, "https": PROXY} if policy == "environment" else {}
                    backend = self.backend(base_url=scheme + "://origin.invalid/v1", **options)
                    with mock.patch("urllib.request.getproxies", return_value=env):
                        with self.real_transport(backend) as (transport, sleep):
                            result = backend.complete(MESSAGES)
                    self.assertEqual(result.content, "ok")
                    self.assertEqual(len(transport.records), 1)
                    self.assert_request(transport.records[0], backend, proxied=policy != "direct")
                    self.assertEqual(backend.usage.calls, 1)
                    sleep.assert_not_called()

    def test_http_body_and_properties_are_not_read(self):
        exc = _PoisonHTTPError(401)
        backend = self.backend()
        with self.sequence(backend, [exc]) as (opener, sleep):
            error = self.capture_error(backend)
        self.assertIn("HTTP 401", str(error))
        self.assertEqual(exc.touched, [])
        self.assertEqual(exc.code_reads, 1)
        self.assertEqual(exc.close_calls, 1)
        self.assertEqual(len(opener.records), 1)
        sleep.assert_not_called()

    def test_http_status_normalization(self):
        class IntSubclass(int):
            pass
        codes = (True, "429" + SECRET, IntSubclass(503), 99, 600, 100, 599)
        for index, code in enumerate(codes):
            with self.subTest(vector=index):
                exc = _PoisonHTTPError(code)
                backend = self.backend(max_retries=2)
                with self.sequence(backend, [exc]) as (opener, sleep):
                    error = self.capture_error(backend)
                expected = str(code) if type(code) is int and 100 <= code <= 599 else "unknown"
                self.assertIn("HTTP " + expected, str(error))
                self.assertEqual(exc.code_reads, 1)
                self.assertEqual(exc.touched, [])
                self.assertEqual(exc.close_calls, 1)
                self.assertEqual(len(opener.records), 1)
                self.assertEqual(backend.usage.retries, 0)
                sleep.assert_not_called()

    def test_http_close_boundaries(self):
        for code in (401, 429):
            close_error = _poison_exception(RuntimeError)
            exc = _PoisonHTTPError(code, close_error)
            backend = self.backend(max_retries=1)
            outcomes = [exc, _response()] if code == 429 else [exc]
            with self.sequence(backend, outcomes) as (opener, sleep):
                if code == 429:
                    self.assertEqual(backend.complete(MESSAGES).content, "ok")
                    self.assertEqual(len(opener.records), 2)
                    sleep.assert_called_once_with(0.25)
                else:
                    self.assertIn("HTTP 401", str(self.capture_error(backend)))
                    sleep.assert_not_called()
            self.assertEqual(exc.close_calls, 1)
            self.assertEqual(exc.touched, [])
            self.assertEqual(close_error.touched, [])
        for kind in (MemoryError, KeyboardInterrupt, SystemExit):
            with self.subTest(fatal=kind.__name__):
                fatal = kind(SECRET)
                exc = _PoisonHTTPError(429, fatal)
                backend = self.backend(max_retries=2)
                with self.sequence(backend, [exc]) as (opener, sleep):
                    self.assert_fatal(backend, fatal)
                self.assertEqual(exc.close_calls, 1)
                self.assertEqual(exc.code_reads, 1)
                self.assertEqual(len(opener.records), 1)
                sleep.assert_not_called()

    def test_closed_transport_labels(self):
        cases = ((TimeoutError, "TimeoutError"), (urllib.error.URLError, "URLError"),
                 (ConnectionError, "ConnectionError"), (http.client.HTTPException, "HTTPException"),
                 (http.client.RemoteDisconnected, "ConnectionError"), (UnicodeError, "UnicodeError"),
                 (UnicodeDecodeError, "UnicodeError"), (json.JSONDecodeError, "JSONDecodeError"),
                 (ValueError, "ValueError"), (TypeError, "TypeError"),
                 (OSError, "OSError"), (RuntimeError, "unavailable"))
        for kind, label in cases:
            for poisoned in (False, True):
                with self.subTest(kind=kind.__name__, subclass=poisoned):
                    if poisoned:
                        exc = _poison_exception(kind)
                    elif kind is json.JSONDecodeError:
                        exc = kind(SECRET, SECRET, 0)
                    elif kind is UnicodeDecodeError:
                        exc = kind("utf-8", SECRET.encode(), 0, 1, SECRET)
                    else:
                        exc = kind(SECRET)
                    backend = self.backend()
                    with self.sequence(backend, [exc]) as (opener, sleep):
                        error = self.capture_error(backend)
                    self.assertEqual(str(error), "模型传输失败（" + label + "；详情已隐藏）")
                    if poisoned:
                        self.assertEqual(exc.touched, [])
                    self.assertEqual(len(opener.records), 1)
                    sleep.assert_not_called()

    def test_transport_fatal_exceptions_propagate(self):
        for kind in (MemoryError, KeyboardInterrupt, SystemExit):
            with self.subTest(fatal=kind.__name__):
                fatal = kind(SECRET)
                backend = self.backend(max_retries=2)
                with self.sequence(backend, [fatal]) as (opener, sleep):
                    self.assert_fatal(backend, fatal)
                self.assertEqual(len(opener.records), 1)
                self.assertEqual(backend.usage.retries, 0)
                sleep.assert_not_called()

    def test_deterministic_http_no_retry(self):
        for code in (401, 403, 404):
            with self.subTest(status=code):
                exc = _PoisonHTTPError(code)
                backend = self.backend(max_retries=2)
                with self.sequence(backend, [exc]) as (opener, sleep):
                    self.assertIn("HTTP " + str(code), str(self.capture_error(backend)))
                self.assertEqual(len(opener.records), 1)
                self.assert_request(opener.records[0], backend)
                self.assertEqual(backend.usage.retries, 0)
                self.assertEqual(exc.close_calls, 1)
                sleep.assert_not_called()

    def test_retry_success_contract(self):
        for kind in (429, 503, "timeout"):
            with self.subTest(failure=kind):
                exc = _poison_exception(TimeoutError) if kind == "timeout" else _PoisonHTTPError(kind)
                backend = self.backend(max_retries=2)
                with self.sequence(backend, [exc, _response()]) as (opener, sleep):
                    self.assertEqual(backend.complete(MESSAGES).content, "ok")
                self.assertEqual(len(opener.records), 2)
                self.assertEqual(opener.records[0], opener.records[1])
                self.assert_request(opener.records[0], backend)
                self.assertEqual(backend.usage.retries, 1)
                self.assertEqual(backend.usage.calls, 1)
                self.assertEqual(exc.touched, [])
                if kind != "timeout":
                    self.assertEqual(exc.close_calls, 1)
                sleep.assert_called_once_with(0.25)

    def test_retry_exhaustion_contract(self):
        for kind in (429, 503, "timeout"):
            with self.subTest(failure=kind):
                errors = [_poison_exception(TimeoutError) if kind == "timeout" else _PoisonHTTPError(kind)
                          for _ in range(3)]
                backend = self.backend(max_retries=2)
                with self.sequence(backend, errors) as (opener, sleep):
                    error = self.capture_error(backend)
                self.assertIn("TimeoutError" if kind == "timeout" else "HTTP " + str(kind), str(error))
                self.assertEqual(len(opener.records), 3)
                for record in opener.records:
                    self.assert_request(record, backend)
                    self.assertEqual(record, opener.records[0])
                self.assertEqual(backend.usage.retries, 2)
                self.assertEqual(backend.usage.calls, 0)
                self.assertEqual(sleep.call_args_list, [mock.call(0.25), mock.call(0.5)])
                for exc in errors:
                    self.assertEqual(exc.touched, [])
                    if kind != "timeout":
                        self.assertEqual(exc.close_calls, 1)

    def test_decode_failures(self):
        for body, label in ((SECRET.encode() + b"\xff", "UnicodeError"),
                            (SECRET.encode(), "JSONDecodeError")):
            with self.subTest(category=label):
                backend = self.backend(max_retries=2)
                with self.sequence(backend, [_response(body=body)]) as (opener, sleep):
                    error = self.capture_error(backend)
                self.assertIn(label, str(error))
                self.assertEqual(len(opener.records), 1)
                self.assertEqual(backend.usage.retries, 0)
                sleep.assert_not_called()

    def test_malformed_response_boundaries(self):
        vectors = [
            {"secret": SECRET}, {"choices": []}, {"choices": SECRET},
            {"choices": [{"message": SECRET}]}, {"choices": [{}]},
            {"choices": [{"message": {"content": [SECRET]}}]},
            {**OK_DATA, "usage": {"prompt_tokens": SECRET}},
            {**OK_DATA, "usage": {"total_tokens": [SECRET]}},
            {**OK_DATA, "usage": {"completion_tokens": float("inf")}},
            {"choices": [{"message": {"tool_calls": [SECRET]}}]},
            {"choices": [{"message": {"tool_calls": [{"function": [SECRET]}]}}]},
            {**OK_DATA, "usage": {"completion_tokens_details": [SECRET]}},
        ]
        self.assertEqual(len(vectors), 12)
        for index, data in enumerate(vectors):
            with self.subTest(vector=index):
                backend = self.backend(max_retries=2)
                with self.sequence(backend, [_response(data)]) as (opener, sleep):
                    error = self.capture_error(backend)
                self.assertEqual(str(error), "响应结构异常（详情已隐藏）")
                self.assertEqual(len(opener.records), 1)
                self.assertEqual(backend.usage.retries, 0)
                sleep.assert_not_called()

    def test_usage_precedes_tool_parse_failure(self):
        data = {"usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
                "choices": [{"message": {"tool_calls": [{"function": SECRET}]}}]}
        backend = self.backend()
        with self.sequence(backend, [_response(data)]):
            error = self.capture_error(backend)
        self.assertEqual(str(error), "响应结构异常（详情已隐藏）")
        self.assertEqual(backend.last_usage.total_tokens, 9)
        self.assertEqual(backend.usage.total_tokens, 9)
        self.assertEqual(backend.usage.calls, 1)

    def test_success_tools_usage_and_raw_arguments(self):
        data = {"model": "offline-model", "usage": {
            "prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16,
            "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 2}},
            "choices": [{"message": {"content": "<think>internal</think>" + SECRET,
                "tool_calls": [
                    {"id": "a", "function": {"name": "one", "arguments": json.dumps({"value": SECRET})}},
                    {"function": {"name": "two", "arguments": SECRET}},
                    {"function": {"name": "three", "arguments": {"value": SECRET}}},
                ]}}]}
        backend = self.backend(temperature=0.5)
        tools = [{"type": "function", "function": {"name": "one"}}]
        with self.sequence(backend, [_response(data), _response(data)]) as (opener, sleep):
            result = backend.complete(MESSAGES, tools=tools, max_tokens=77, tool_choice="one")
            backend.complete(MESSAGES)
        self.assertEqual(result.content, SECRET)
        self.assertEqual([call.id for call in result.tool_calls], ["a", "call_1", "call_2"])
        self.assertEqual([call.name for call in result.tool_calls], ["one", "two", "three"])
        self.assertEqual([call.arguments for call in result.tool_calls],
                         [{"value": SECRET}, {"_raw": SECRET}, {"value": SECRET}])
        self.assertEqual(result.raw, {"model": "offline-model", "usage": data["usage"]})
        self.assertEqual(backend.last_usage.as_dict(), dict(calls=1, retries=0, prompt_tokens=11,
            completion_tokens=5, total_tokens=16, cached_tokens=3, reasoning_tokens=2))
        self.assertEqual(backend.usage.total_tokens, 32)
        self.assertEqual(backend.usage.calls, 2)
        payload = json.loads(opener.records[0]["body"])
        self.assertEqual(payload["tools"], tools)
        self.assertEqual(payload["tool_choice"], {"type": "function", "function": {"name": "one"}})
        self.assertEqual(payload["max_tokens"], 77)
        self.assertEqual(payload["temperature"], 0.5)
        sleep.assert_not_called()

    def test_public_exception_boundary(self):
        from icode import cli

        outcomes = [_PoisonHTTPError(401), _poison_exception(RuntimeError),
                    _response({**OK_DATA, "usage": {"total_tokens": SECRET}})]
        for index, outcome in enumerate(outcomes):
            with self.subTest(vector=index):
                backend = self.backend()
                with self.sequence(backend, [outcome]):
                    error = self.capture_error(backend)
                self.assert_private(str(error))
                self.assert_private(repr(error))
                self.assert_private("".join(traceback.format_exception(error)))
                self.assert_private(json.dumps({"error": str(error)}, ensure_ascii=False))
                stderr = io.StringIO()
                with (mock.patch.dict(cli._COMMANDS, {"doctor": mock.Mock(side_effect=error)}),
                      redirect_stderr(stderr)):
                    self.assertEqual(cli.main(["doctor"]), 3)
                self.assertIn("模型调用错误：", stderr.getvalue())
                self.assert_private(stderr.getvalue())
                self.assertTrue(error.__suppress_context__)

    def test_loop_public_error_boundary(self):
        backend = self.backend()
        self.assertIsInstance(backend, Backend)
        root = Path(__file__).resolve().parent
        loop = AgentLoop(backend=backend, registry=ToolRegistry(),
                         guard=Guard(Scope(root)), ctx=ToolContext(root))
        with self.sequence(backend, [_PoisonHTTPError(401)]) as (opener, sleep):
            result = loop.run(MESSAGES)
        self.assertFalse(result.ok)
        self.assertEqual(result.stop_reason, "backend_error")
        self.assertIn("BackendError: HTTP 401", result.error)
        self.assert_private(result.error)
        self.assert_private(result.render())
        self.assert_private(json.dumps({"ok": result.ok, "error": result.error}, ensure_ascii=False))
        self.assertEqual(len(opener.records), 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
