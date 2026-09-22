"""隔离能力层测试（Phase 5）。

核心不是"沙箱好不好用"，而是**能不能坚守诚实**：
没有可用后端时必须自我标注为「应用层限制」，且隔离失败时**拒绝执行**而不是降级执行。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests._support import temp_workspace

from icode.isolation import (
    BASELINE_CLAIM,
    BubblewrapSandbox,
    ContainerSandbox,
    MacSeatbeltSandbox,
    NoIsolation,
    capability_report,
    probe_capabilities,
    select_sandbox,
)
from icode.tools import IsolationUnavailable, ToolContext, default_registry


class TestProbe(unittest.TestCase):
    def test_探测不抛异常且覆盖四类后端(self) -> None:
        caps = probe_capabilities()
        names = {c.name for c in caps}
        self.assertEqual(names, {"bwrap", "sandbox-exec", "docker", "podman"})
        for c in caps:
            self.assertIn(c.kind, ("kernel", "container", "none"))
            self.assertIn("可执行文件", c.detail)

    def test_探测只报实测结果(self) -> None:
        for c in probe_capabilities():
            if not c.available:
                self.assertIn("未找到", c.detail)


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
        self.assertEqual(report["honest_label"], selected["claim"])
        if not selected["is_real_isolation"]:
            self.assertEqual(report["honest_label"], BASELINE_CLAIM)

    def test_本机若无后端则选中基线(self) -> None:
        if any(c.is_kernel_or_container for c in probe_capabilities()):
            self.skipTest("本机有可用隔离后端")
        self.assertFalse(select_sandbox().is_real_isolation)


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
        self.assertNotIn("(allow network*)", profile)

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
