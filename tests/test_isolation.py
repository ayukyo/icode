"""隔离能力层测试（Phase 5）。

核心不是"沙箱好不好用"，而是**能不能坚守诚实**：
没有可用后端时必须自我标注为「应用层限制」，且隔离失败时**拒绝执行**而不是降级执行。
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
import unittest
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from tests._support import temp_workspace

from icode.isolation import (
    BASELINE_CLAIM,
    PARTIAL_CLAIM,
    BubblewrapSandbox,
    LandlockSandbox,
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
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.workspace import WorkspaceManager
from icode.execution_broker import execute_policy_command


class TestProbe(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                         "需要 Linux C 编译器验证原生助手")
    def test_landlock_助手真实阻断文件与网络越权(self) -> None:
        from tests._support import temp_workspace

        source = Path(__file__).resolve().parents[1] / "native" / "linux" / "icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                 str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            manifest = root / "icode-landlock.sha256"
            manifest.write_text(hashlib.sha256(helper.read_bytes()).hexdigest() + "\n",
                                encoding="ascii")
            result = probe_native_sandbox(LandlockSandbox(helper=str(helper)))
            self.assertTrue(result.ready, result.detail)
            system_python = Path("/usr/bin/python3")
            self.assertTrue(system_python.is_file(), "Linux CI must have a system Python")
            checkout = root / "checkout"
            checkout.mkdir()
            sandbox = LandlockSandbox(helper=str(helper), manifest=str(manifest))
            positive = subprocess.run(
                sandbox.wrap([str(system_python), "-c", "print('ready')"], workspace=checkout),
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(positive.returncode, 0, positive.stderr)
            installed_python = subprocess.run(
                sandbox.wrap(
                    [sys.executable, "-c", "import sys; print(sys.prefix)"],
                    workspace=checkout,
                ),
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(installed_python.returncode, 0, installed_python.stderr)
            denied = subprocess.run(
                sandbox.wrap(
                    [str(system_python), "-c", "import socket; socket.socket(socket.AF_UNIX)"],
                    workspace=checkout,
                ),
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("PermissionError", denied.stderr)
            for syscall in ("setsid", "setpgid"):
                operation = (
                    "import os; os.setpgid(0, 0)"
                    if syscall == "setpgid" else "import os; os.setsid()"
                )
                escaped_group = subprocess.run(
                    sandbox.wrap(
                        [str(system_python), "-c", operation],
                        workspace=checkout,
                    ),
                    capture_output=True, text=True, timeout=4, check=False,
                )
                self.assertNotEqual(escaped_group.returncode, 0, syscall)
                self.assertIn("PermissionError", escaped_group.stderr, syscall)

            # Git 管理文件位于可写代码目录的兄弟位置时，Landlock 的路径
            # 白名单可直接拒绝写入；通过代码目录内的符号链接也不能绕过。
            checkout = root / "layered-checkout"
            checkout.mkdir()
            code = checkout / "code"
            code.mkdir()
            git_file = checkout / ".git"
            git_file.write_text("gitdir: protected\n", encoding="utf-8")
            (code / "git-alias").symlink_to(git_file)
            for target in ("../.git", "git-alias"):
                denied = subprocess.run(
                    sandbox.wrap(
                        [
                            str(system_python), "-c",
                            "from pathlib import Path; import sys; "
                            "Path(sys.argv[1]).write_text('changed')",
                            target,
                        ],
                        workspace=code,
                    ),
                    capture_output=True, text=True, timeout=4, check=False,
                )
                self.assertNotEqual(denied.returncode, 0, target)
                self.assertIn("PermissionError", denied.stderr, target)
            self.assertEqual(git_file.read_text(encoding="utf-8"), "gitdir: protected\n")

            repository = root / "source-repository"
            repository.mkdir()
            subprocess.run(["git", "-C", str(repository), "init", "-q"], check=True)
            (repository / "tracked.txt").write_text("source\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "-c", "user.name=ICODE Test",
                 "-c", "user.email=icode@example.invalid", "commit", "-qm", "initial"],
                check=True,
            )
            manager = WorkspaceManager(
                repository, root / "managed", "project-1", isolate_git_metadata=True,
            )
            with manager.open("real-layered", "run-1") as session:
                code_root = session.workspace_root
                policy = session.policy("plan")
                self.assertEqual(policy.write_roots, (code_root,))
                self.assertEqual(sandbox._checked_policy_workspace(policy), code_root)
                sandbox.prepare_policy(policy)
                result = default_registry().invoke(
                    "run_command",
                    ToolContext(root=code_root, sandbox=sandbox, policy=policy),
                    {"argv": [sys.executable, "-c", "print('policy-command-ready')"]},
                )
                self.assertTrue(result.ok, result.content)
                self.assertIn("policy-command-ready", result.content)
                allowed = subprocess.run(
                    sandbox.wrap(
                        [
                            str(system_python), "-c",
                            "from pathlib import Path; Path('new.txt').write_text('ok')",
                        ],
                        workspace=code_root,
                    ),
                    capture_output=True, text=True, timeout=4, check=False,
                )
                self.assertEqual(allowed.returncode, 0, allowed.stderr)
                denied = subprocess.run(
                    sandbox.wrap(
                        [
                            str(system_python), "-c",
                            "from pathlib import Path; Path('../.git').write_text('bad')",
                        ],
                        workspace=code_root,
                    ),
                    capture_output=True, text=True, timeout=4, check=False,
                )
                self.assertNotEqual(denied.returncode, 0)
                self.assertIn("PermissionError", denied.stderr)
                self.assertEqual(
                    (code_root / "new.txt").read_text(encoding="utf-8"), "ok",
                )
                child_code = (
                    "import time, pathlib; time.sleep(1.4); "
                    "pathlib.Path('late-child').write_text('escaped')"
                )
                parent_code = (
                    "import subprocess, sys, time; "
                    f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
                    "print('spawned', flush=True); time.sleep(5)"
                )
                outcome = execute_policy_command(
                    sandbox.wrap(
                        [sys.executable, "-c", parent_code], workspace=code_root,
                    ),
                    cwd=code_root, policy=policy, timeout=1,
                )
                self.assertEqual(outcome.error, "timeout")
                self.assertTrue(outcome.cleanup_ok)
                self.assertIn("spawned", outcome.output)
                time.sleep(1.5)
                self.assertFalse((code_root / "late-child").exists())

            started = checkout / "parent-exit-started"
            survived = checkout / "parent-exit-survived"
            child_code = (
                "from pathlib import Path; import time; "
                "Path('parent-exit-started').write_text('ready'); "
                "time.sleep(1); Path('parent-exit-survived').write_text('escaped')"
            )
            wrapped = sandbox.wrap(
                [sys.executable, "-c", child_code], workspace=checkout,
            )
            self.assertIn("--parent-pid", wrapped)
            wrong_parent = list(wrapped)
            wrong_parent[wrong_parent.index("--parent-pid") + 1] = str(os.getpid() + 1)
            rejected = subprocess.run(
                wrong_parent, capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse(started.exists())
            parent_code = (
                "import os, subprocess, time\n"
                "from pathlib import Path\n"
                f"wrapped = {wrapped!r}\n"
                "wrapped[wrapped.index('--parent-pid') + 1] = str(os.getpid())\n"
                "subprocess.Popen(wrapped, stdin=subprocess.DEVNULL, "
                "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                "for _ in range(400):\n"
                f"    if Path({str(started)!r}).exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('sandbox child did not start')\n"
            )
            parent = subprocess.run(
                [sys.executable, "-c", parent_code],
                capture_output=True, text=True, timeout=7, check=False,
            )
            self.assertEqual(parent.returncode, 0, parent.stderr)
            self.assertTrue(started.is_file())
            time.sleep(1.2)
            self.assertFalse(survived.exists(), "宿主退出后沙箱命令仍在执行")

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
        bundled = report["bundled_linux_helper"]
        self.assertFalse(bundled["policy_ready"])
        self.assertIsInstance(bundled["minimal_probe_passed"], bool)
        self.assertIsInstance(bundled["detail"], str)
        if not sys.platform.startswith("linux"):
            self.assertFalse(bundled["installed"])
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
    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux 策略助手完整性验证")
    def test_landlock_策略路径逐次校验助手摘要(self) -> None:
        with temp_workspace() as root:
            workspace = (root / "code").resolve()
            workspace.mkdir()
            helper = root / "icode-landlock"
            helper.write_bytes(b"#!/bin/sh\nexit 0\n")
            helper.chmod(0o755)
            manifest = root / "icode-landlock.sha256"
            manifest.write_text(hashlib.sha256(helper.read_bytes()).hexdigest() + "\n",
                                encoding="ascii")
            policy = SandboxPolicy(
                schema_version=1, run_id="hash-test", ticket_id="hash-test", step="code",
                workspace_root=workspace, read_roots=(workspace,), write_roots=(workspace,),
                deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
            )
            with self.assertRaises(RuntimeError):
                LandlockSandbox(helper=str(helper)).prepare_policy(policy)
            sandbox = LandlockSandbox(helper=str(helper), manifest=str(manifest))
            sandbox.prepare_policy(policy)
            self.assertEqual(sandbox.wrap_policy(["true"], policy=policy)[0], str(helper))
            helper.write_bytes(b"#!/bin/sh\nexit 1\n")
            with self.assertRaises(RuntimeError):
                sandbox.prepare_policy(policy)
            with self.assertRaises(RuntimeError):
                sandbox.wrap_policy(["true"], policy=policy)

    def test_landlock_实验性策略路径映射拒绝不可表达合同(self) -> None:
        with temp_workspace() as root:
            workspace = (root / "code").resolve()
            workspace.mkdir()
            protected = root / ".git"
            protected.write_text("gitdir: protected\n", encoding="utf-8")
            policy = SandboxPolicy(
                schema_version=1, run_id="map-test", ticket_id="map-test", step="code",
                workspace_root=workspace,
                read_roots=(workspace,), write_roots=(workspace,),
                deny_read_roots=(), deny_write_roots=(protected,),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=1024,
                protected_paths=(protected,),
            )
            sandbox = LandlockSandbox(helper="/not-needed-for-static-check")
            self.assertEqual(sandbox._checked_policy_workspace(policy), workspace)
            with self.assertRaises(ValueError):
                sandbox.wrap_policy(["true"], policy=policy, network=True)
            for broad_root in (Path("/"), Path("/tmp"), Path.home()):
                with self.assertRaises(RuntimeError):
                    sandbox._validated_runtime_roots((broad_root,))
            for changed in (
                replace(policy, write_roots=(workspace / "nested",)),
                replace(policy, read_roots=(workspace, root)),
                replace(policy, deny_read_roots=(workspace / "secret",)),
                replace(policy, deny_write_roots=(workspace / ".git",),
                        protected_paths=(workspace / ".git",)),
                replace(policy, deny_read_roots=(Path("/usr/bin"),)),
                replace(policy, deny_write_roots=(Path("/dev/null"),),
                        protected_paths=(Path("/dev/null"),)),
                replace(policy, network_mode=NetworkMode.PROXY_ALLOWLIST,
                        allowed_domains=("example.com",)),
            ):
                with self.subTest(changed=changed):
                    with self.assertRaises(ValueError):
                        sandbox._checked_policy_workspace(changed)

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
        self.assertIn('(subpath "/private/etc/ssl")', profile)
        self.assertNotIn("(allow network*)", profile)

    def test_seatbelt_工作区路径不能注入_profile(self) -> None:
        sb = MacSeatbeltSandbox()
        profile = sb._profile(Path('/tmp/work"space'), False)
        self.assertIn('work\\"space', profile)
        with self.assertRaises(ValueError):
            sb._profile(Path("/tmp/work\nspace"), False)

    def test_seatbelt_策略profile排除受保护路径(self) -> None:
        with temp_workspace() as root:
            workspace = (root / "workspace").resolve()
            workspace.mkdir()
            protected = workspace / ".git"
            secret = workspace / "secret"
            policy = SandboxPolicy(
                schema_version=1, run_id="profile-test", ticket_id="profile-test", step="code",
                workspace_root=workspace, read_roots=(workspace,), write_roots=(workspace,),
                deny_read_roots=(secret,), deny_write_roots=(protected,),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=1024,
                protected_paths=(protected,),
            )
            profile = MacSeatbeltSandbox()._policy_profile(policy)
            self.assertIn("(deny default)", profile)
            self.assertIn(f'(require-not (literal "{protected}"))', profile)
            self.assertIn(f'(require-not (subpath "{protected}"))', profile)
            self.assertIn(f'(require-not (literal "{secret}"))', profile)
            self.assertNotIn("(allow network*)", profile)

    @unittest.skipUnless(sys.platform == "darwin", "需 macOS Seatbelt 实测")
    def test_seatbelt_策略profile真实阻断受保护文件与外部路径(self) -> None:
        with temp_workspace() as root:
            workspace = (root / "workspace").resolve()
            outside = (root / "outside").resolve()
            workspace.mkdir()
            outside.mkdir()
            protected = workspace / ".git"
            protected.write_text("protected", encoding="utf-8")
            secret = workspace / "secret"
            secret.write_text("private", encoding="utf-8")
            policy = SandboxPolicy(
                schema_version=1, run_id="profile-probe", ticket_id="profile-probe", step="code",
                workspace_root=workspace, read_roots=(workspace,), write_roots=(workspace,),
                deny_read_roots=(secret,), deny_write_roots=(protected,),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=1024,
                protected_paths=(protected,),
            )
            sb = MacSeatbeltSandbox(sandbox_exec=shutil.which("sandbox-exec") or "sandbox-exec")
            profile = sb._policy_profile(policy)

            def run(command: list[str]) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sb.sandbox_exec, "-p", profile, *command],
                    cwd=workspace, capture_output=True, text=True, timeout=5, check=False,
                )

            touch = shutil.which("touch") or "/usr/bin/touch"
            cat = shutil.which("cat") or "/bin/cat"
            allowed = run([touch, str(workspace / "allowed")])
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            python = run([sys.executable, "-c", "print('policy-python-ready')"])
            self.assertEqual(python.returncode, 0, python.stderr)
            self.assertIn("policy-python-ready", python.stdout)
            self.assertNotEqual(run([touch, str(protected)]).returncode, 0)
            self.assertEqual(protected.read_text(encoding="utf-8"), "protected")
            self.assertNotEqual(run([touch, str(outside / "blocked")]).returncode, 0)
            self.assertFalse((outside / "blocked").exists())
            self.assertNotEqual(run([cat, str(secret)]).returncode, 0)

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

    def test_执行目录不能逃出工作区(self) -> None:
        import sys

        ctx = ToolContext(root=self.ws, sandbox=NoIsolation())
        with temp_workspace() as outside:
            command = [sys.executable, "-c", "from pathlib import Path; Path('escaped').touch()"]
            for cwd in (str(outside), str(self.ws / ".." / outside.name)):
                result = default_registry().invoke(
                    "run_command", ctx, {"argv": command, "cwd": cwd}
                )
                self.assertFalse(result.ok)
                self.assertEqual(result.meta.get("error"), "invalid_cwd")
                self.assertFalse((outside / "escaped").exists())

            link = self.ws / "outside-link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                return  # Windows 受限账户可能不允许创建符号链接。
            result = default_registry().invoke(
                "run_command", ctx, {"argv": command, "cwd": "outside-link"}
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.meta.get("error"), "invalid_cwd")
            self.assertFalse((outside / "escaped").exists())

    def test_策略未绑定原生后端时命令拒绝而不裸执行(self) -> None:
        policy = SandboxPolicy(
            schema_version=1, run_id="run-1", ticket_id="ticket-1", step="code",
            workspace_root=self.ws, read_roots=(self.ws,), write_roots=(self.ws,),
            deny_read_roots=(), deny_write_roots=(self.ws / ".git",),
            network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=16,
            wall_timeout_seconds=60, output_limit_bytes=1024,
            protected_paths=(self.ws / ".git",),
        )
        ctx = ToolContext(root=self.ws, sandbox=NoIsolation(), policy=policy)
        result = default_registry().invoke(
            "run_command", ctx,
            {"argv": [sys.executable, "-c", "from pathlib import Path; Path('unsafe').touch()"]},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.meta.get("error"), "isolation_unavailable")
        self.assertFalse((self.ws / "unsafe").exists())


if __name__ == "__main__":
    unittest.main()
