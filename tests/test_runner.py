"""运行器测试（离线）：靶场隔离、快照比对、独立验证、真模型后端构造。"""

from __future__ import annotations

import unittest

from tests._support import REPO_ROOT, temp_workspace

from icode.backends import BackendError, OpenAICompatibleBackend, Usage, build_backend
from icode.runner import _changed, _snapshot, prepare_workspace, run_unittest


class TestFixtureIsolation(unittest.TestCase):
    def test_靶场复制到隔离目录(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            self.assertTrue((dst / "calc.py").is_file())
            self.assertTrue((dst / "test_calc.py").is_file())
            # 是副本，不是软链/原目录
            self.assertNotEqual(dst.resolve(), (REPO_ROOT / "tests" / "fixtures" / "pycalc").resolve())

    def test_改副本不影响仓库基线(self) -> None:
        origin = REPO_ROOT / "tests" / "fixtures" / "pycalc" / "calc.py"
        before = origin.read_text(encoding="utf-8")
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            (dst / "calc.py").write_text("# 被污染的副本\n", encoding="utf-8")
        self.assertEqual(origin.read_text(encoding="utf-8"), before,
                         "靶场基线被污染：E2E 必须在副本上跑")

    def test_未知靶场报错(self) -> None:
        with temp_workspace() as ws:
            with self.assertRaises(FileNotFoundError):
                prepare_workspace("no_such_fixture", ws / "work", repo_root=REPO_ROOT)

    def test_重复准备会重建(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            (dst / "junk.tmp").write_text("x", encoding="utf-8")
            dst2 = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            self.assertFalse((dst2 / "junk.tmp").exists())


class TestSnapshot(unittest.TestCase):
    def test_改动检测(self) -> None:
        with temp_workspace() as ws:
            (ws / "a.py").write_text("1\n", encoding="utf-8")
            before = _snapshot(ws)
            (ws / "a.py").write_text("2\n", encoding="utf-8")
            (ws / "b.py").write_text("3\n", encoding="utf-8")
            after = _snapshot(ws)
            self.assertEqual(_changed(before, after), ["a.py", "b.py"])

    def test_快照忽略工单产物(self) -> None:
        with temp_workspace() as ws:
            (ws / ".icode_output").mkdir()
            (ws / ".icode_output" / "x.md").write_text("x", encoding="utf-8")
            (ws / "a.py").write_text("1\n", encoding="utf-8")
            self.assertEqual(list(_snapshot(ws)), ["a.py"])


class TestIndependentVerification(unittest.TestCase):
    def test_靶场基线独立跑测试通过(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            code, output = run_unittest(dst)
            self.assertEqual(code, 0, output[-800:])
            self.assertIn("OK", output)

    def test_改动导致失败时退出码非零(self) -> None:
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            (dst / "calc.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
            code, _ = run_unittest(dst)
            self.assertNotEqual(code, 0, "独立验证必须能识别破坏性改动")


class TestBackendFactory(unittest.TestCase):
    def test_fake_后端无需密钥(self) -> None:
        b = build_backend("fake")
        self.assertEqual(getattr(b, "name", ""), "fake")
        msg = b.complete([{"role": "user", "content": "hi"}])
        self.assertTrue(msg.content)

    def test_真模型后端缺密钥时报可读错误(self) -> None:
        import os
        from unittest import mock

        from icode import config as cfg
        from icode.config import ConfigError

        saved = {k: os.environ.pop(k, None) for k in ("ICODE_LLM_API_KEY", "ICODE_LLM_KEY_FILE")}
        try:
            # 同时屏蔽本地 icode.local.toml，确保"无任何密钥来源"这一前提成立
            with mock.patch.object(cfg, "_load_local_config", return_value={}):
                with self.assertRaises(ConfigError):
                    build_backend("openai-compatible")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_未知后端名报错(self) -> None:
        with self.assertRaises(BackendError):
            build_backend("gpt-from-mars")

    def test_剥离思考标签(self) -> None:
        from icode.backends import strip_think

        self.assertEqual(strip_think("<think>内部推理</think>\n结果"), "结果")

    def test_usage_合并(self) -> None:
        a = Usage(total_tokens=10, prompt_tokens=6, completion_tokens=4)
        b = Usage(total_tokens=5, prompt_tokens=3, completion_tokens=2, calls=2)
        m = a.merge(b)
        self.assertEqual(m.total_tokens, 15)
        self.assertEqual(m.calls, 3)

    def test_空密钥直接拒绝(self) -> None:
        with self.assertRaises(BackendError):
            OpenAICompatibleBackend(api_key="")


class TestProxyStrategy(unittest.TestCase):
    """代理策略：默认跟随环境，但必须能显式绕过（托管环境的隧道代理会 502）。"""

    def test_默认跟随环境(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        self.assertFalse(b.no_proxy)
        self.assertIsNone(b.proxy)
        # 环境相关：要么是某个代理 URL，要么是"无"——只要求可描述、不抛异常
        desc = b.active_proxy()
        self.assertTrue(desc == "无" or "//" in desc, f"代理描述异常：{desc}")

    def test_强制直连时描述明确(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", no_proxy=True)
        self.assertEqual(b.active_proxy(), "禁用（强制直连）")

    def test_显式代理优先于环境(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", proxy="http://127.0.0.1:1")
        self.assertEqual(b.active_proxy(), "http://127.0.0.1:1")

    def test_直连时代理映射为空(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", no_proxy=True)
        self.assertEqual(b._proxy_mapping(), {}, "强制直连必须得到空代理映射")

    def test_显式代理映射只含该代理(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", proxy="http://127.0.0.1:1")
        self.assertEqual(b._proxy_mapping(),
                         {"http": "http://127.0.0.1:1", "https": "http://127.0.0.1:1"})

    def test_默认跟随环境代理(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        import urllib.request

        self.assertEqual(b._proxy_mapping(), dict(urllib.request.getproxies()))

    def test_opener_可构造且不改状态(self) -> None:
        for kwargs in ({}, {"no_proxy": True}, {"proxy": "http://127.0.0.1:1"}):
            opener = OpenAICompatibleBackend(api_key="k", **kwargs)._opener()  # type: ignore[arg-type]
            self.assertTrue(hasattr(opener, "open"))

    def test_代理失败时给出可执行提示(self) -> None:
        b = OpenAICompatibleBackend(api_key="k")
        hint = b._proxy_hint(RuntimeError("Tunnel connection failed: 502 Bad Gateway"))
        self.assertIn("--no-proxy", hint)
        self.assertIn("ICODE_LLM_NO_PROXY=1", hint)

    def test_已显式配置时不再提示(self) -> None:
        b = OpenAICompatibleBackend(api_key="k", no_proxy=True)
        self.assertEqual(b._proxy_hint(RuntimeError("502 Bad Gateway")), "")

    def test_环境变量可强制直连(self) -> None:
        import os

        from icode.config import llm_no_proxy

        saved = os.environ.get("ICODE_LLM_NO_PROXY")
        try:
            os.environ["ICODE_LLM_NO_PROXY"] = "1"
            self.assertTrue(llm_no_proxy())
            os.environ["ICODE_LLM_NO_PROXY"] = "0"
            self.assertFalse(llm_no_proxy())
        finally:
            if saved is None:
                os.environ.pop("ICODE_LLM_NO_PROXY", None)
            else:
                os.environ["ICODE_LLM_NO_PROXY"] = saved


class TestBackendRetry(unittest.TestCase):
    """模型调用是只读动作：传输类失败可自动重试；4xx 属确定性失败，绝不重试。"""

    def test_可重试状态码(self) -> None:
        for code in (408, 425, 429, 500, 502, 503, 504):
            self.assertTrue(OpenAICompatibleBackend._retryable_http(code), code)
        for code in (400, 401, 403, 404, 422):
            self.assertFalse(OpenAICompatibleBackend._retryable_http(code), code)

    def test_超时与连接错误可重试(self) -> None:
        self.assertTrue(OpenAICompatibleBackend._retryable_exc(TimeoutError("read timed out")))
        self.assertTrue(OpenAICompatibleBackend._retryable_exc(
            __import__("urllib.error", fromlist=["URLError"]).URLError("boom")))
        self.assertFalse(OpenAICompatibleBackend._retryable_exc(ValueError("逻辑错误")))

    def _ok_response(self):
        import json as _json

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return _json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        return _Resp()

    def test_首次超时后重试成功(self) -> None:
        from unittest import mock

        calls: list[int] = []

        class _Opener:
            def open(self, req, timeout=None):
                calls.append(1)
                if len(calls) == 1:
                    raise TimeoutError("The read operation timed out")
                return NONE_RESP

        NONE_RESP = self._ok_response()
        b = OpenAICompatibleBackend(api_key="k", max_retries=2, retry_backoff=0)
        with mock.patch.object(b, "_opener", return_value=_Opener()):
            msg = b.complete([{"role": "user", "content": "x"}])
        self.assertEqual(msg.content, "ok")
        self.assertEqual(b.usage.retries, 1)
        self.assertEqual(len(calls), 2, "应当重试一次")

    def test_重试耗尽报可读错误(self) -> None:
        from unittest import mock

        class _Opener:
            def open(self, req, timeout=None):
                raise TimeoutError("The read operation timed out")

        b = OpenAICompatibleBackend(api_key="k", max_retries=1, retry_backoff=0)
        with mock.patch.object(b, "_opener", return_value=_Opener()):
            with self.assertRaises(BackendError) as ctx:
                b.complete([{"role": "user", "content": "x"}])
        self.assertIn("TimeoutError", str(ctx.exception))
        self.assertEqual(b.usage.retries, 1)

    def test_401_不重试(self) -> None:
        import urllib.error
        from unittest import mock

        calls: list[int] = []

        class _Opener:
            def open(self, req, timeout=None):
                calls.append(1)
                raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

        b = OpenAICompatibleBackend(api_key="k", max_retries=3, retry_backoff=0)
        with mock.patch.object(b, "_opener", return_value=_Opener()):
            with self.assertRaises(BackendError) as ctx:
                b.complete([{"role": "user", "content": "x"}])
        self.assertIn("401", str(ctx.exception))
        self.assertEqual(len(calls), 1, "401 是确定性失败，不得重试")
        self.assertEqual(b.usage.retries, 0)


if __name__ == "__main__":
    unittest.main()
