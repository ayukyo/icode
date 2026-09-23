"""隔离能力层测试（Phase 5）。

核心不是"沙箱好不好用"，而是**能不能坚守诚实**：
没有可用后端时必须自我标注为「应用层限制」，且隔离失败时**拒绝执行**而不是降级执行。
"""

from __future__ import annotations

import unittest
import shutil
import sys
from pathlib import Path
from unittest import mock

from tests._support import temp_workspace

from icode.isolation import (
    BASELINE_CLAIM,
    PARTIAL_CLAIM,
    BubblewrapSandbox,
    ContainerSandbox,
    MacSeatbeltSandbox,
    NoIsolation,
    WindowsJobLimits,
    WslSandbox,
    capability_report,
    probe_capabilities,
    probe_native_sandbox,
    select_sandbox,
)
from icode.tools import IsolationUnavailable, ToolContext, default_registry


class TestProbe(unittest.TestCase):
    def test_恒等包装不能通过原生负向探测(self) -> None:
        result = probe_native_sandbox(NoIsolation())
        self.assertFalse(result.ready)
        self.assertIn("outside_write_denied", result.checks)
        self.assertFalse(result.checks["outside_write_denied"])

    def test_无法启动的候选后端不能报告可用(self) -> None:
        result = probe_native_sandbox(BubblewrapSandbox(bwrap="/no/such/bwrap"))
        self.assertFalse(result.ready)
        self.assertFalse(result.checks["workspace_write"])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux 原生后端测试")
    def test_探测异常不能自动选择候选程序(self) -> None:
        def which(name: str) -> str | None:
            return "/usr/bin/bwrap" if name == "bwrap" else None

        with mock.patch("icode.isolation.shutil.which", side_effect=which), mock.patch(
            "icode.isolation.probe_native_sandbox", side_effect=RuntimeError("probe failed")
        ):
            cap = next(item for item in probe_capabilities() if item.name == "bwrap")
            self.assertFalse(cap.available)
            self.assertIsInstance(select_sandbox(), NoIsolation)

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bwrap"),
                         "当前主机没有 Linux bwrap")
    def test_bwrap_在临时工作区真实阻断越权(self) -> None:
        result = probe_native_sandbox(BubblewrapSandbox(bwrap=shutil.which("bwrap") or "bwrap"))
        if not result.checks["workspace_write"]:
            self.skipTest("本机内核策略不允许启动 bwrap")
        self.assertTrue(result.ready, result.detail)

    def test_探测不抛异常且覆盖四类后端(self) -> None:
        caps = probe_capabilities()
        names = {c.name for c in caps}
        self.assertEqual(names, {"bwrap", "sandbox-exec", "wsl", "docker", "podman"})
        for c in caps:
            self.assertIn(c.kind, ("kernel", "container", "none"))
            self.assertIn("可执行文件", c.detail)

    def test_探测只报实测结果(self) -> None:
        for c in probe_capabilities():
            if not c.available:
                self.assertTrue(
                    "未找到" in c.detail or "真实探测：未通过" in c.detail
                    or "当前平台不适用" in c.detail,
                    c.detail,
                )


class TestHonesty(unittest.TestCase):
    """没有后端时不许宣称沙箱——本文件最重要的两条断言。"""

    def test_无可用后端时明确标注为应用层限制(self) -> None:
        sandbox = select_sandbox(preference="none")
        self.assertFalse(sandbox.is_real_isolation)
        desc = sandbox.describe()
        self.assertEqual(desc["claim"], BASELINE_CLAIM)
        self.assertIn("不是", desc["claim"].replace("非", "不是"))
        self.assertIn("文件系统", desc["not_enforced"])

    def test_请求不可用后端时退回基线且说明原因(self) -> None:
        sandbox = select_sandbox(preference="bwrap")
        if sandbox.is_real_isolation:
            self.skipTest("本机确实有 bwrap，跳过")
        self.assertFalse(sandbox.is_real_isolation)
        self.assertIn("不可用", sandbox.describe()["reason"])

    def test_能力报告口径与所选后端一致(self) -> None:
        report = capability_report()
        selected = report["selected"]
        self.assertEqual(report["policy_schema_version"], 1)
        self.assertEqual(report["conformance_contract"]["id"], "icode-sandbox-v1")
        self.assertEqual(report["conformance_contract"]["total"], 10)
        self.assertEqual(report["conformance_contract"]["critical"], 8)
        self.assertEqual(report["conformance_contract"]["minimum_passed"], 9)
        self.assertFalse(report["conformance_contract"]["executed"])
        self.assertEqual(report["honest_label"], selected["claim"])
        if not selected["is_real_isolation"]:
            self.assertEqual(report["honest_label"], BASELINE_CLAIM)

    def test_本机无自动可选后端时退回基线(self) -> None:
        """判据是**自动选择结果**，而不是"探测到可执行文件"。

        否则只要机器上装了 wsl.exe 就会误判为"有隔离"。
        """
        sandbox = select_sandbox()
        if sandbox.is_real_isolation:
            self.skipTest(f"本机确实自动选中了可用后端：{sandbox.name}")
        self.assertFalse(sandbox.is_real_isolation)
        self.assertEqual(sandbox.describe()["claim"], BASELINE_CLAIM)


class TestWslAndJobLimits(unittest.TestCase):
    """WSL 沙箱与 Windows Job Object。

    注意：这些测试**只校验 argv 构造与声明**，不实际启动任何后端
    （受限环境会按安全策略拦截 wsl.exe，且不应反复尝试）。
    """

    def test_wsl_路径映射(self) -> None:
        sb = WslSandbox()
        self.assertEqual(sb.to_wsl_path(Path("C:/a/b")), "/mnt/c/a/b")

    def test_wsl_包装含工作目录与断网(self) -> None:
        sb = WslSandbox()
        argv = sb.wrap(["python", "-V"], workspace=Path("C:/ws"))
        self.assertEqual(argv[0], "wsl")
        self.assertIn("--cd", argv)
        self.assertEqual(argv[argv.index("--cd") + 1], "/mnt/c/ws")
        self.assertIn("unshare", argv)
        self.assertIn("-n", argv)
        self.assertEqual(argv[-2:], ["python", "-V"])
        self.assertTrue(sb.is_real_isolation)

    def test_wsl_允许网络时不加_unshare(self) -> None:
        argv = WslSandbox().wrap(["curl"], workspace=Path("C:/ws"), network=True)
        self.assertNotIn("unshare", argv)

    def test_仅存在_wsl_可执行文件时不自动选中(self) -> None:
        """回归：曾因"存在 wsl.exe"就自动选中 WSL，导致每条命令都被包进 wsl 而失败。

        存在 ≠ 可用；自动选择不得包含 WSL。
        """
        sandbox = select_sandbox()
        if any(c.name == "wsl" and c.available for c in probe_capabilities()):
            self.assertNotIsInstance(sandbox, WslSandbox,
                                     "WSL 不得进入自动选择列表")
            self.assertFalse(sandbox.is_real_isolation,
                             "本机只有 wsl.exe 时，自动选择应退回基线而非假装有隔离")

    def test_JobObject_是部分强制且明确表态(self) -> None:
        jl = WindowsJobLimits()
        desc = jl.describe()
        self.assertFalse(desc["is_real_isolation"])
        self.assertEqual(desc["claim"], PARTIAL_CLAIM)
        self.assertIn("文件系统", desc["not_enforced"])
        self.assertIn("网络", desc["not_enforced"])
        self.assertIn("活动进程数上限", desc["enforced"])
        self.assertIn("不得据此宣称沙箱", desc["note"])

    def test_JobObject_wrap_不改写命令(self) -> None:
        jl = WindowsJobLimits()
        self.assertEqual(jl.wrap(["python", "-V"], workspace=Path("C:/ws")),
                         ["python", "-V"])

    def test_JobObject_apply_不抛异常(self) -> None:
        """apply 是尽力而为：成功与否都要返回可读说明，绝不抛。"""
        ok, detail = WindowsJobLimits(active_process_limit=32, memory_mb=1024).apply()
        self.assertIsInstance(ok, bool)
        self.assertTrue(detail)


class TestSandboxWrapping(unittest.TestCase):
    def test_基线包装是恒等变换(self) -> None:
        sb = NoIsolation()
        argv = ["python", "-m", "unittest"]
        self.assertEqual(sb.wrap(argv, workspace=Path("/tmp/w")), argv)

    def test_bwrap_包装含工作区绑定与默认断网(self) -> None:
        sb = BubblewrapSandbox()
        argv = sb.wrap(["ls", "-la"], workspace=Path("/tmp/ws"))
        self.assertEqual(argv[0], "bwrap")
        self.assertIn("--unshare-net", argv)
        self.assertIn("--bind", argv)
        self.assertEqual(argv[argv.index("--bind") + 1], str(Path("/tmp/ws").resolve()))
        self.assertEqual(argv[-2:], ["ls", "-la"])
        self.assertLess(argv.index("--tmpfs"), argv.index("--bind"))

    def test_bwrap_显式允许网络时不加_unshare_net(self) -> None:
        argv = BubblewrapSandbox().wrap(["curl"], workspace=Path("/tmp/ws"), network=True)
        self.assertNotIn("--unshare-net", argv)

    def test_seatbelt_包装含最小_profile(self) -> None:
        sb = MacSeatbeltSandbox()
        argv = sb.wrap(["ls"], workspace=Path("/tmp/ws"))
        self.assertEqual(argv[0], "sandbox-exec")
        profile = argv[argv.index("-p") + 1]
        self.assertIn("(deny default)", profile)
        self.assertIn(str(Path("/tmp/ws").resolve()), profile)
        self.assertIn('(path-ancestors "', profile)
        self.assertIn('(literal "/")', profile)
        self.assertNotIn("(allow network*)", profile)

    def test_seatbelt_工作区路径不能注入_profile(self) -> None:
        sb = MacSeatbeltSandbox()
        profile = sb._profile(Path('/tmp/work"space'), False)
        self.assertIn('work\\"space', profile)
        with self.assertRaises(ValueError):
            sb._profile(Path("/tmp/work\nspace"), False)

    def test_容器_包装默认断网且只挂工作区(self) -> None:
        argv = ContainerSandbox(runtime="podman").wrap(["python", "-V"], workspace=Path("/tmp/ws"))
        self.assertEqual(argv[:3], ["podman", "run", "--rm"])
        self.assertIn("--network", argv)
        self.assertEqual(argv[argv.index("--network") + 1], "none")
        self.assertIn("-v", argv)


class TestContextIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self._ws = temp_workspace()
        self.ws: Path = self._ws.__enter__()

    def tearDown(self) -> None:
        self._ws.__exit__(None, None, None)

    def test_无沙箱时包装为恒等且标注诚实(self) -> None:
        ctx = ToolContext(root=self.ws)
        self.assertEqual(ctx.wrap_command(["ls"]), ["ls"])
        self.assertFalse(ctx.needs_real_isolation())
        self.assertIn("应用层限制", ctx.isolation_label())

    def test_有沙箱时按后端包装并标注(self) -> None:
        ctx = ToolContext(root=self.ws, sandbox=NoIsolation())
        self.assertFalse(ctx.needs_real_isolation())
        self.assertIn("应用层限制", ctx.isolation_label())

        ctx2 = ToolContext(root=self.ws, sandbox=BubblewrapSandbox())
        self.assertTrue(ctx2.needs_real_isolation())
        self.assertEqual(ctx2.wrap_command(["ls"])[0], "bwrap")

    def test_隔离包装失败时拒绝执行而非降级(self) -> None:
        class _Broken:
            name = "broken"

            @property
            def is_real_isolation(self) -> bool:
                return True

            def wrap(self, *a, **kw):
                raise OSError("bwrap 启动失败")

            def describe(self) -> dict:
                return {"claim": "损坏的后端"}

        ctx = ToolContext(root=self.ws, sandbox=_Broken())
        with self.assertRaises(IsolationUnavailable):
            ctx.wrap_command(["ls"])

        # 工具层要把它变成"拒绝执行"
        result = default_registry().invoke("run_command", ctx, {"argv": ["ls"]})
        self.assertFalse(result.ok)
        self.assertEqual(result.meta.get("error"), "isolation_unavailable")

    def test_执行结果如实标注隔离情况(self) -> None:
        import sys

        ctx = ToolContext(root=self.ws, sandbox=NoIsolation())
        r = default_registry().invoke("run_command", ctx,
                                      {"argv": [sys.executable, "-c", "print(1)"]})
        self.assertTrue(r.ok)
        self.assertFalse(r.meta["real_isolation"])
        self.assertIn("应用层限制", r.meta["isolation"])


if __name__ == "__main__":
    unittest.main()
