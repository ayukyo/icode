"""运行器测试（离线）：靶场隔离、快照比对、独立验证、真模型后端构造。"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import sys
import unittest

from tests._support import REPO_ROOT, require_skill, temp_workspace

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

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_快照只记录链接文本不读取外部目标(self) -> None:
        with temp_workspace() as parent:
            workspace = parent / "workspace"
            workspace.mkdir()
            secret = parent / "secret"
            secret.write_text("outside-secret", encoding="utf-8")
            link = workspace / "alias"
            link.symlink_to(secret)
            expected = hashlib.sha256(os.fsencode(str(secret))).hexdigest()

            before = _snapshot(workspace)
            self.assertEqual(before, {"alias": expected})
            secret.write_text("changed-outside-secret", encoding="utf-8")
            self.assertEqual(_snapshot(workspace), before)

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_快照不递归外部目录且拒绝链接根(self) -> None:
        with temp_workspace() as parent:
            workspace = parent / "workspace"
            workspace.mkdir()
            outside = parent / "outside"
            outside.mkdir()
            (outside / "secret").write_text("outside-secret", encoding="utf-8")
            (workspace / "directory-link").symlink_to(outside, target_is_directory=True)
            self.assertEqual(list(_snapshot(workspace)), ["directory-link"])
            root_alias = parent / "root-alias"
            root_alias.symlink_to(workspace, target_is_directory=True)
            with self.assertRaises(OSError):
                _snapshot(root_alias)


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

    def test_指定沙箱会包裹独立测试命令(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        class _RecordingSandbox:
            name = "recording"
            is_real_isolation = True

            def __init__(self):
                self.calls = []

            def wrap(self, argv, *, workspace, network=False):
                self.calls.append((list(argv), workspace, network))
                return ["sandbox-wrapper", *argv]

        sandbox = _RecordingSandbox()
        with temp_workspace() as ws:
            with mock.patch(
                "icode.runner.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="OK", stderr=""),
            ) as run:
                code, output = run_unittest(ws, sandbox=sandbox)

        self.assertEqual((code, output), (0, "OK"))
        self.assertEqual(len(sandbox.calls), 1)
        argv, workspace, network = sandbox.calls[0]
        self.assertEqual(argv, [sys.executable, "-m", "unittest"])
        self.assertEqual(workspace, ws)
        self.assertFalse(network)
        self.assertEqual(run.call_args.args[0], ["sandbox-wrapper", *argv])

    @unittest.skipUnless(
        sys.platform.startswith("linux") and shutil.which("bwrap"),
        "需要 Linux bubblewrap 原生隔离",
    )
    def test_bwrap验证器不能读取工作区外文件(self) -> None:
        from icode.isolation import BubblewrapSandbox

        with temp_workspace() as parent:
            workspace = parent / "workspace"
            workspace.mkdir()
            private_file = parent / "private.txt"
            private_file.write_text("outside-workspace-sentinel", encoding="utf-8")
            (workspace / "test_boundary.py").write_text(
                "import unittest\n"
                "class BoundaryTest(unittest.TestCase):\n"
                "    def test_private_file_is_unavailable(self):\n"
                f"        with self.assertRaises(OSError): open({str(private_file)!r}, 'rb')\n",
                encoding="utf-8",
            )

            code, output = run_unittest(workspace, sandbox=BubblewrapSandbox())

        self.assertEqual(code, 0, output[-800:])
        self.assertIn("OK", output)
        self.assertNotIn("outside-workspace-sentinel", output)


class TestAutoPersist(unittest.TestCase):
    """"模型文本产出 → 运行时落盘"通道：内容必须来自模型，且诚实标注来源。"""

    def test_提取JSON并落盘(self) -> None:
        from icode.runner import _extract_json, _persist_missing_from_response

        text = (
            "审查结论如下：\n"
            '```json\n{"round": 1, "new_issues": ["计划缺测试计划"],'
            ' "refuted_issues": [], "pending_verification": []}\n```\n'
        )
        data = _extract_json(text)
        self.assertEqual(data["round"], 1)
        self.assertEqual(data["new_issues"], ["计划缺测试计划"])

        with temp_workspace() as ws:
            out = ws / "t"
            out.mkdir()
            report = _FakeReport()
            from icode.contracts import _to_contract

            contract = _to_contract("review", {"outputs": [
                {"id": "review", "kind": "ticket_file", "value": "review_round_1.json",
                 "required": True}]})
            persisted = _persist_missing_from_response(out, contract, report, text)
            self.assertEqual(len(persisted), 1)
            self.assertIn("JSON 提取", persisted[0])
            got = json.loads((out / "review_round_1.json").read_text(encoding="utf-8"))
            self.assertEqual(got["round"], 1)

    def test_Markdown产物带来源标注(self) -> None:
        from icode.runner import AUTOPERSIST_HEADER, _persist_missing_from_response
        from icode.contracts import _to_contract

        with temp_workspace() as ws:
            out = ws / "t"
            out.mkdir()
            report = _FakeReport()
            contract = _to_contract("plan", {"outputs": [
                {"id": "plan", "kind": "ticket_file", "value": "01_plan.md",
                 "required": True}]})
            text = "# 计划\n\n内容足够长。" * 10
            persisted = _persist_missing_from_response(out, contract, report, text)
            self.assertEqual(len(persisted), 1)
            body = (out / "01_plan.md").read_text(encoding="utf-8")
            self.assertTrue(body.startswith(AUTOPERSIST_HEADER.split("\n")[0][:20]))
            self.assertIn("# 计划", body)

    def test_策略会话的文本补落盘也经过合同端口(self) -> None:
        from icode.artifact_broker import ArtifactBroker
        from icode.contracts import _to_contract
        from icode.runner import _persist_missing_from_response

        with temp_workspace() as ws:
            out = ws / "ticket"
            out.mkdir()
            contract = _to_contract("plan", {"outputs": [
                {"id": "plan", "kind": "ticket_file", "value": "01_plan.md",
                 "required": True},
            ]})
            broker = ArtifactBroker(out, contract, max_bytes=1024)
            persisted = _persist_missing_from_response(
                out, contract, _FakeReport(), "# 计划\n" * 4,
                artifact_broker=broker,
            )
            self.assertEqual(len(persisted), 1)
            self.assertTrue((out / "01_plan.md").is_file())

    def test_符号链接不能冒充已登记的工单产物(self) -> None:
        from icode.contracts import _to_contract
        from icode.runner import StepReport, _register_outputs

        class RejectArtifactCall:
            def artifact(self, *args, **kwargs):
                raise AssertionError("符号链接不可登记")

        with temp_workspace() as ws:
            out = ws / "ticket"
            out.mkdir()
            outside = ws / "outside.md"
            outside.write_text("untrusted", encoding="utf-8")
            try:
                (out / "01_plan.md").symlink_to(outside)
            except OSError:
                self.skipTest("当前账户无法创建符号链接")
            contract = _to_contract("plan", {"outputs": [
                {"id": "plan", "kind": "ticket_file", "value": "01_plan.md",
                 "required": True},
            ]})
            report = StepReport(step="plan", ok=False, out_dir=str(out))
            missing = _register_outputs(
                RejectArtifactCall(), out, "plan", "attempt", "ticket", contract, report,
            )
            self.assertEqual(missing, ["01_plan.md"])

    def test_提取不到JSON时诚实保持缺失(self) -> None:
        from icode.runner import _persist_missing_from_response
        from icode.contracts import _to_contract

        with temp_workspace() as ws:
            out = ws / "t"
            out.mkdir()
            report = _FakeReport()
            contract = _to_contract("review", {"outputs": [
                {"id": "r", "kind": "ticket_file", "value": "review_round_1.json",
                 "required": True}]})
            persisted = _persist_missing_from_response(
                out, contract, report, "没有 JSON 对象的纯文本回复，" + "这段回复足够长以通过最短长度检查。" * 6)
            self.assertEqual(persisted, [], "提取不到 JSON 不得伪造")
            self.assertTrue(any("未提取到" in w for w in report.warnings))

    def test_已有产物不覆盖(self) -> None:
        from icode.runner import _persist_missing_from_response
        from icode.contracts import _to_contract

        with temp_workspace() as ws:
            out = ws / "t"
            out.mkdir()
            (out / "01_plan.md").write_text("模型自己写的", encoding="utf-8")
            report = _FakeReport()
            contract = _to_contract("plan", {"outputs": [
                {"id": "plan", "kind": "ticket_file", "value": "01_plan.md",
                 "required": True}]})
            persisted = _persist_missing_from_response(out, contract, report, "长文本" * 100)
            self.assertEqual(persisted, [], "已有产物不得覆盖")
            self.assertEqual((out / "01_plan.md").read_text(encoding="utf-8"), "模型自己写的")


class _FakeReport:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def warn(self, text: str) -> None:
        self.warnings.append(text)


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


class TestTaskVerificationEvidence(unittest.TestCase):
    """R3：run_task 的独立测试回执必须绑定到证据，模型自述不算。"""

    def test_独立测试回执绑定到证据(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import run_task

        settings = require_skill()
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            # 不改动文件：基线测试通过 → exit_code=0
            report = run_task(
                settings, backend=FakeBackend(["完成"]), workspace=dst,
            )
            self.assertIsNotNone(report.verification)
            evidence = report.verification
            self.assertEqual(evidence.step, "task")
            self.assertEqual(evidence.kind, "test")
            self.assertEqual(evidence.command, ("python", "-m", "unittest"))
            self.assertEqual(evidence.exit_code, 0)
            self.assertTrue(evidence.passed)
            self.assertTrue(evidence.environment_fingerprint)
            self.assertTrue(evidence.output_sha256)
            # 改动为空 → 无产物哈希，但仍绑定环境指纹
            self.assertEqual(dict(evidence.artifact_hashes), {})

    def test_run_task把同一沙箱交给独立验证器(self) -> None:
        from unittest import mock

        from icode.backends import FakeBackend
        from icode.isolation import NoIsolation
        from icode.runner import run_task

        settings = require_skill()
        sandbox = NoIsolation(reason="测试显式沙箱传递")
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            with mock.patch("icode.runner.run_unittest", return_value=(0, "OK")) as verify:
                run_task(
                    settings, backend=FakeBackend(["完成"]), workspace=dst,
                    sandbox=sandbox,
                )

        self.assertIs(verify.call_args.kwargs["sandbox"], sandbox)

    def test_破坏性改动产生带哈希与分类的证据(self) -> None:
        from icode.backends import FakeBackend
        from icode.runner import run_task

        settings = require_skill()
        with temp_workspace() as ws:
            dst = prepare_workspace("pycalc", ws / "work", repo_root=REPO_ROOT)
            # 模拟模型在工作区内把 calc.py 改坏（通过工具，而非直接改文件）
            calc_path = str(dst / "calc.py")
            script = [
                {"content": "", "tool_calls": [
                    {"id": "break-calc", "name": "write_file",
                     "arguments": {"path": calc_path,
                                   "content": "raise RuntimeError('boom')\n"}}
                ]},
                "完成",
            ]
            report = run_task(
                settings, backend=FakeBackend(script), workspace=dst,
            )
            evidence = report.verification
            self.assertIsNotNone(evidence)
            self.assertNotEqual(evidence.exit_code, 0)
            self.assertFalse(evidence.passed)
            from icode.self_verify import FAILURE_CODE

            self.assertEqual(evidence.category, FAILURE_CODE)
            self.assertIn("calc.py", evidence.artifact_hashes)
            self.assertEqual(len(evidence.artifact_hashes["calc.py"]), 64)
            self.assertTrue(evidence.environment_fingerprint)


if __name__ == "__main__":
    unittest.main()
