"""隔离能力层测试（Phase 5）。

核心不是"沙箱好不好用"，而是**能不能坚守诚实**：
没有可用后端时必须自我标注为「应用层限制」，且隔离失败时**拒绝执行**而不是降级执行。
"""

from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import os
import plistlib
import socket
import unittest
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
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
    probe_macos_process_group_cleanup,
    probe_native_sandbox,
    select_sandbox,
)
from icode.tools import IsolationUnavailable, ToolContext, default_registry
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.workspace import WorkspaceManager
from icode.execution_broker import execute_policy_command


class TestProbe(unittest.TestCase):
    def test_报告区分mac同组清理与完整一致性(self) -> None:
        report = capability_report()
        group = report["macos_group_cleanup"]
        self.assertIsInstance(group["passed"], bool)
        self.assertEqual(set(group["checks"]), {"normal_exit", "timeout"}
                         if sys.platform == "darwin" else set())
        self.assertFalse(report["conformance_contract"]["executed"])
        if sys.platform != "darwin":
            self.assertFalse(group["executed"])
            self.assertFalse(group["passed"])

    def test_macos_同组清理启动异常按失败报告(self) -> None:
        with mock.patch("icode.isolation.sys.platform", "darwin"), \
             mock.patch("icode.isolation.shutil.which", return_value="/fake/sandbox-exec"), \
             mock.patch("icode.execution_broker.execute_policy_command",
                        side_effect=RuntimeError("probe failed")) as broker:
            result = probe_macos_process_group_cleanup(MacSeatbeltSandbox())
        ast.parse(broker.call_args.args[0][-1])
        self.assertNotIn("subprocess.DEVNULL", broker.call_args.args[0][-1])
        self.assertTrue(result.executed)
        self.assertFalse(result.passed)
        self.assertEqual(result.checks, {"normal_exit": False, "timeout": False})
        self.assertIn("normal_exit", result.detail)
        self.assertNotIn("probe failed", result.detail)

    @unittest.skipUnless(os.name == "posix", "需 POSIX 进程组验证探针编排")
    def test_macos_同组探针编排在无沙箱假后端可运行(self) -> None:
        class NoopWrapper:
            sandbox_exec = "/bin/true"

            def experimental_wrap_policy(self, argv, *, policy):
                return list(argv)

        with mock.patch("icode.isolation.sys.platform", "darwin"):
            result = probe_macos_process_group_cleanup(NoopWrapper())
        self.assertEqual(result.checks, {"normal_exit": True, "timeout": True},
                         result.detail)

    @unittest.skipUnless(sys.platform == "darwin", "需 macOS Seatbelt 与真实进程组")
    def test_macos_同组清理真实自检不冒充整树(self) -> None:
        result = probe_macos_process_group_cleanup(MacSeatbeltSandbox())
        self.assertTrue(result.executed)
        self.assertEqual(result.checks, {"normal_exit": True, "timeout": True})
        self.assertTrue(result.passed, result.detail)
        self.assertFalse(MacSeatbeltSandbox().policy_contract_ready)

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
                changed_group = subprocess.run(
                    sandbox.wrap(
                        [str(system_python), "-c", operation],
                        workspace=checkout,
                    ),
                    capture_output=True, text=True, timeout=4, check=False,
                )
                self.assertEqual(changed_group.returncode, 0, changed_group.stderr)

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

                # 主进程正常结束时也必须清掉仍存活的孙进程；否则单靠
                # 主进程 returncode 会把后台残留误判为已完成。
                grandchild_code = (
                    "import os, time\nfrom pathlib import Path\n"
                    "try:\n    os.setsid()\nexcept PermissionError:\n    pass\n"
                    "Path('deep-started').write_text('ready')\n"
                    "time.sleep(1.4)\n"
                    "Path('deep-survived').write_text('escaped')\n"
                )
                child_code = (
                    "import subprocess, sys, time\nfrom pathlib import Path\n"
                    f"subprocess.Popen([sys.executable, '-c', {grandchild_code!r}], "
                    "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                    "stderr=subprocess.DEVNULL)\n"
                    "for _ in range(200):\n"
                    "    if Path('deep-started').exists(): break\n"
                    "    time.sleep(0.01)\n"
                    "else: raise RuntimeError('grandchild did not start')\n"
                )
                parent_code = (
                    "import subprocess, sys\n"
                    f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                    "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                    "stderr=subprocess.DEVNULL)\n"
                    "assert child.wait(timeout=4) == 0\n"
                    "print('deep-started', flush=True)\n"
                )
                finished = execute_policy_command(
                    sandbox.wrap([sys.executable, "-c", parent_code], workspace=code_root),
                    cwd=code_root, policy=policy, timeout=5,
                )
                self.assertEqual(finished.exit_code, 0, finished.output)
                self.assertIsNone(finished.error, finished.output)
                self.assertTrue(finished.cleanup_ok)
                self.assertTrue((code_root / "deep-started").exists())
                time.sleep(1.5)
                self.assertFalse((code_root / "deep-survived").exists())

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

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc")
                         and shutil.which("unshare"), "需要 Linux user namespace 测试工具")
    def test_landlock_嵌套userns继承deny仍通过原生负向探测(self) -> None:
        # CI 的外层 user namespace 可能已将 setgroups 置为 deny；该状态
        # 会继承到新 namespace，不能再次写入 deny。
        prefix = ["unshare", "--user", "--map-root-user"]
        preflight = subprocess.run(
            [*prefix, "sh", "-c", "cat /proc/self/setgroups"],
            capture_output=True, text=True, timeout=4, check=False,
        )
        if preflight.returncode != 0:
            self.skipTest(f"本机禁止创建测试用 user namespace: {preflight.stderr.strip()}")
        self.assertEqual(preflight.stdout.strip(), "deny")

        source = Path(__file__).resolve().parents[1] / "native" / "linux" / "icode_landlock.c"
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(source), "-o", str(helper)],
                check=True, capture_output=True, text=True,
            )
            # 调用助手的真实映射函数；util-linux 已在外层 namespace 写过
            # deny，再写同一个 proc 文件会失败。仅靠完整 probe 在部分
            # 内核上不能稳定复现这个时序。
            driver = root / "setgroups-driver.c"
            driver.write_text(
                f'#define main icode_helper_main\n#include "{source}"\n#undef main\n'
                'int main(int argc, char **argv) {\n'
                '    if (argc == 2 && strcmp(argv[1], "--verify-uid-only") == 0)\n'
                '        return verify_uid_only_mapping();\n'
                '    if (argc <= 2) {\n'
                '        int result = ensure_setgroups_denied(argc > 1 ? argv[1] : "/proc/self/setgroups");\n'
                '        return argc > 1 ? (result == 1 ? 0 : 1) : result;\n'
                '    }\n'
                '    return run_helper(argc, argv, getenv("ICODE_TEST_SETGROUPS_PATH"));\n'
                '}\n',
                encoding="ascii",
            )
            driver_bin = root / "setgroups-driver"
            driver_build = subprocess.run(
                [shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                 "-Werror", str(driver), "-o", str(driver_bin)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(driver_build.returncode, 0, driver_build.stderr)
            denied = subprocess.run(
                [*prefix, str(driver_bin)], capture_output=True, text=True,
                timeout=4, check=False,
            )
            self.assertEqual(denied.returncode, 0, denied.stdout + denied.stderr)
            if Path("/proc/self/gid_map").read_text(encoding="ascii").strip():
                mapped_gid = subprocess.run(
                    [str(driver_bin), "--verify-uid-only"],
                    capture_output=True, text=True, timeout=4, check=False,
                )
                self.assertNotEqual(mapped_gid.returncode, 0)
                self.assertIn("empty gid_map", mapped_gid.stderr)
            unreadable = subprocess.run(
                [str(driver_bin), str(root / "missing-setgroups")],
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertNotEqual(unreadable.returncode, 0)
            self.assertIn("missing-setgroups", unreadable.stderr)
            # allow 状态但写入受系统策略拒绝时，只能转 UID-only 映射。
            blocked = root / "setgroups-allow-readonly"
            blocked.write_text("allow\n", encoding="ascii")
            blocked.chmod(0o444)
            if os.geteuid() != 0:
                fallback = subprocess.run(
                    [str(driver_bin), str(blocked)], capture_output=True, text=True,
                    timeout=4, check=False,
                )
                self.assertEqual(fallback.returncode, 0, fallback.stdout + fallback.stderr)
                self.assertEqual(fallback.stderr, "")
            with mock.patch.dict(os.environ, {"ICODE_TEST_SETGROUPS_PATH": str(blocked)}):
                restricted = probe_native_sandbox(LandlockSandbox(helper=str(driver_bin)))
                positive = subprocess.run(
                    LandlockSandbox(helper=str(driver_bin)).wrap(
                        ["/bin/true"], workspace=root,
                    ), capture_output=True, text=True, timeout=4, check=False,
                )
                started = root / "uid-only-child-started"
                survived = root / "uid-only-child-survived"
                child_code = (
                    "import os, time\nfrom pathlib import Path\n"
                    "os.setsid()\n"
                    f"Path({str(started)!r}).write_text('ready')\n"
                    "time.sleep(1.2)\n"
                    f"Path({str(survived)!r}).write_text('escaped')\n"
                )
                parent_code = (
                    "import subprocess, sys, time\nfrom pathlib import Path\n"
                    f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                    "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                    "stderr=subprocess.DEVNULL)\n"
                    "for _ in range(200):\n"
                    f"    if Path({str(started)!r}).exists(): break\n"
                    "    time.sleep(0.01)\n"
                    "else: raise RuntimeError('detached child did not start')\n"
                )
                cleaned = subprocess.run(
                    LandlockSandbox(helper=str(driver_bin)).wrap(
                        [sys.executable, "-c", parent_code], workspace=root,
                    ), capture_output=True, text=True, timeout=5, check=False,
                )
            self.assertTrue(restricted.ready, restricted.detail)
            self.assertEqual(positive.returncode, 0, positive.stderr)
            self.assertEqual(positive.stderr, "")
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
            self.assertTrue(started.exists(), cleaned.stderr)
            time.sleep(1.4)
            self.assertFalse(survived.exists(), "UID-only 路径遗留了脱组后代")
            blocked.chmod(0o644)
            blocked.write_text("unknown\n", encoding="ascii")
            malformed = subprocess.run(
                [str(driver_bin), str(blocked)], capture_output=True, text=True,
                timeout=4, check=False,
            )
            self.assertNotEqual(malformed.returncode, 0)
            self.assertIn("unexpected setgroups state", malformed.stderr)
            script = (
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, sys.argv[2])\n"
                "from icode.isolation import LandlockSandbox, probe_native_sandbox\n"
                "assert Path('/proc/self/setgroups').read_text().strip() == 'deny'\n"
                "result = probe_native_sandbox(LandlockSandbox(helper=sys.argv[1]))\n"
                "print(result.detail)\n"
                "raise SystemExit(0 if result.ready else 1)\n"
            )
            result = subprocess.run(
                [*prefix, sys.executable, "-c", script, str(helper),
                 str(Path(__file__).resolve().parents[1] / "src")],
                capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_landlock_描述明确未强制进程数上限(self) -> None:
        sandbox = LandlockSandbox(helper="/not-needed-for-description")
        self.assertFalse(sandbox.policy_contract_ready)
        self.assertIn("进程数上限", sandbox.describe()["not_enforced"])

    def test_seatbelt_描述不把实验策略当完整合同(self) -> None:
        sandbox = MacSeatbeltSandbox()
        self.assertFalse(hasattr(sandbox, "wrap_policy"))
        self.assertIn("进程树清理", sandbox.describe()["not_enforced"])
        self.assertIn("进程数上限", sandbox.describe()["not_enforced"])

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
    @unittest.skipUnless(sys.platform == "darwin", "需 macOS launchd 真实作业")
    def test_launchd_独立作业仍未回收脱组后代(self) -> None:
        # 锁定双架构实测缺口：bootout 不能证明整树清理，生产入口必须保持关闭。
        with temp_workspace() as root:
            label = f"org.icode.test.cleanup.{uuid.uuid4().hex}"
            domain = f"gui/{os.getuid()}"
            service_target = f"{domain}/{label}"
            started = root / "launchd-child-started"
            survived = root / "launchd-child-survived"
            grandchild_code = (
                "import os, time\nfrom pathlib import Path\n"
                "os.setsid()\n"
                f"Path({str(started)!r}).write_text('ready')\n"
                "time.sleep(1.4)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            parent_code = (
                "import subprocess, sys, time\nfrom pathlib import Path\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild_code!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('detached child did not start')\n"
                "print('job-ready', flush=True)\n"
                "time.sleep(5)\n"
            )
            plist_path = root / f"{label}.plist"
            with plist_path.open("wb") as stream:
                plistlib.dump({
                    "Label": label,
                    "ProgramArguments": [sys.executable, "-c", parent_code],
                    "RunAtLoad": True,
                    "KeepAlive": False,
                    "AbandonProcessGroup": False,
                    "WorkingDirectory": str(root),
                    "StandardOutPath": str(root / "launchd-stdout"),
                    "StandardErrorPath": str(root / "launchd-stderr"),
                }, stream)
            try:
                bootstrapped = subprocess.run(
                    ["launchctl", "bootstrap", domain, str(plist_path)],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                self.assertEqual(bootstrapped.returncode, 0, bootstrapped.stderr)
                for _ in range(200):
                    if started.exists():
                        break
                    time.sleep(0.01)
                stderr_path = root / "launchd-stderr"
                self.assertTrue(started.exists(),
                                stderr_path.read_text(encoding="utf-8", errors="replace")
                                if stderr_path.exists() else bootstrapped.stderr)
                booted_out = subprocess.run(
                    ["launchctl", "bootout", service_target],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                self.assertEqual(booted_out.returncode, 0, booted_out.stderr)
                time.sleep(1.6)
                self.assertTrue(survived.exists(), "当前 launchd bootout 负例发生变化，需复核")
                sandbox = MacSeatbeltSandbox()
                self.assertFalse(hasattr(sandbox, "wrap_policy"))
                self.assertIn("进程树清理", sandbox.describe()["not_enforced"])
            finally:
                subprocess.run(
                    ["launchctl", "bootout", service_target],
                    capture_output=True, text=True, timeout=5, check=False,
                )

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
            self.assertFalse(sandbox.policy_contract_ready)
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
        self.assertNotIn('(subpath "/private/tmp")', profile)
        self.assertNotIn("(allow network*)", profile)
        self.assertNotIn("(allow process*)", profile)
        self.assertIn("(allow process-exec)", profile)
        self.assertIn("(allow process-fork)", profile)
        self.assertIn("(allow signal (target same-sandbox))", profile)

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
            self.assertNotIn("(allow process*)", profile)
            self.assertIn("(allow process-exec)", profile)
            self.assertIn("(allow process-fork)", profile)
            self.assertIn("(allow signal (target same-sandbox))", profile)

    def test_seatbelt_实验策略包装不开放完整_policy_接口(self) -> None:
        with temp_workspace() as root:
            workspace = (root / "workspace").resolve()
            workspace.mkdir()
            policy = SandboxPolicy(
                schema_version=1, run_id="mac-experiment", ticket_id="mac-experiment",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
            )
            sandbox = MacSeatbeltSandbox()
            self.assertFalse(hasattr(sandbox, "wrap_policy"))
            self.assertFalse(sandbox.policy_contract_ready)
            wrapped = sandbox.experimental_wrap_policy(["true"], policy=policy)
            self.assertEqual(wrapped[0], "sandbox-exec")
            self.assertIn("(deny default)", wrapped[wrapped.index("-p") + 1])
            with self.assertRaises(ValueError):
                sandbox.experimental_wrap_policy(["true"], policy=policy, network=True)

    @unittest.skipUnless(sys.platform == "darwin", "需 macOS Seatbelt + broker 联测")
    def test_seatbelt_实验策略经命令broker执行(self) -> None:
        with temp_workspace() as root:
            workspace = (root / "workspace").resolve()
            workspace.mkdir()
            protected = workspace / ".git"
            protected.write_text("protected", encoding="utf-8")
            policy = SandboxPolicy(
                schema_version=1, run_id="mac-broker", ticket_id="mac-broker",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(),
                deny_write_roots=(protected,), network_mode=NetworkMode.DENY,
                allowed_domains=(), process_limit=8, wall_timeout_seconds=10,
                output_limit_bytes=2048, protected_paths=(protected,),
            )
            sandbox = MacSeatbeltSandbox(
                sandbox_exec=shutil.which("sandbox-exec") or "sandbox-exec"
            )
            allowed = execute_policy_command(
                sandbox.experimental_wrap_policy(
                    [sys.executable, "-c", "from pathlib import Path; "
                     "Path('allowed').write_text('ok'); print('ready')"], policy=policy,
                ),
                cwd=workspace, policy=policy, timeout=5,
            )
            self.assertEqual(allowed.exit_code, 0, allowed)
            self.assertIsNone(allowed.error, allowed)
            self.assertEqual((workspace / "allowed").read_text(encoding="utf-8"), "ok")
            denied = execute_policy_command(
                sandbox.experimental_wrap_policy(
                    [sys.executable, "-c", "from pathlib import Path; "
                     "Path('.git').write_text('changed')"], policy=policy,
                ),
                cwd=workspace, policy=policy, timeout=5,
            )
            self.assertNotEqual(denied.exit_code, 0, denied)
            self.assertEqual(protected.read_text(encoding="utf-8"), "protected")
            child_ready = execute_policy_command(
                sandbox.experimental_wrap_policy(
                    [sys.executable, "-c", "import subprocess, sys; "
                     "subprocess.run([sys.executable, '-c', \"print('child-ready')\"], "
                     "check=True)"],
                    policy=policy,
                ),
                cwd=workspace, policy=policy, timeout=5,
            )
            self.assertEqual(child_ready.exit_code, 0, child_ready)
            self.assertIn("child-ready", child_ready.output)
            child = execute_policy_command(
                sandbox.experimental_wrap_policy(
                    [sys.executable, "-c", "import subprocess, sys; "
                     "subprocess.run([sys.executable, '-c', "
                     "\"from pathlib import Path; Path('.git').write_text('child-change')\"], "
                     "check=True)"],
                    policy=policy,
                ),
                cwd=workspace, policy=policy, timeout=5,
            )
            self.assertNotEqual(child.exit_code, 0, child)
            self.assertEqual(protected.read_text(encoding="utf-8"), "protected")
            grandchild_code = (
                "import os, time\nfrom pathlib import Path\n"
                "try:\n    os.setsid()\n"
                "except PermissionError:\n    Path('seatbelt-setsid-denied').write_text('yes')\n"
                "Path('seatbelt-grandchild-started').write_text('yes')\n"
                "time.sleep(1.4)\n"
                "Path('seatbelt-grandchild-survived').write_text('escaped')\n"
            )
            parent_code = (
                "import subprocess, sys, time\nfrom pathlib import Path\n"
                "with open('seatbelt-grandchild-output', 'wb') as sink:\n"
                f"    subprocess.Popen([sys.executable, '-c', {grandchild_code!r}], "
                "stdout=sink, stderr=subprocess.STDOUT)\n"
                "for _ in range(200):\n"
                "    if Path('seatbelt-grandchild-started').exists(): break\n"
                "    time.sleep(0.01)\n"
                "else: raise RuntimeError('grandchild did not start')\n"
                "print('grandchild-started', flush=True)\n"
            )
            descendants = execute_policy_command(
                sandbox.experimental_wrap_policy(
                    [sys.executable, "-c", parent_code], policy=policy,
                ),
                cwd=workspace, policy=policy, timeout=5,
            )
            self.assertEqual(descendants.exit_code, 0, descendants)
            self.assertIsNone(descendants.error, descendants)
            self.assertIn("grandchild-started", descendants.output)
            # 现有 Seatbelt profile 不拦截 setsid；cleanup_ok 仅覆盖原进程组。
            # 把真实残留锁成已知负例，并要求自动策略入口继续不可用。
            self.assertFalse((workspace / "seatbelt-setsid-denied").exists(), descendants)
            time.sleep(1.5)
            self.assertTrue((workspace / "seatbelt-grandchild-survived").exists())
            self.assertFalse(hasattr(sandbox, "wrap_policy"))
            self.assertIn("进程树清理", sandbox.describe()["not_enforced"])
            socket_ready = execute_policy_command(
                sandbox.experimental_wrap_policy(
                    [sys.executable, "-c", "import socket; print('socket-ready')"],
                    policy=policy,
                ),
                cwd=workspace, policy=policy, timeout=5,
            )
            self.assertEqual(socket_ready.exit_code, 0, socket_ready)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(2)
                with socket.create_connection(listener.getsockname(), timeout=1):
                    accepted, _ = listener.accept()
                    accepted.close()  # 阳性对照后清空队列，避免连接积压造成假拒绝。
                network = execute_policy_command(
                    sandbox.experimental_wrap_policy(
                        [sys.executable, "-c", "import socket, sys; "
                         "socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=1)",
                         str(listener.getsockname()[1])],
                        policy=policy,
                    ),
                    cwd=workspace, policy=policy, timeout=5,
                )
                self.assertNotEqual(network.exit_code, 0, network)

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

    @unittest.skipUnless(sys.platform == "darwin", "需 macOS Seatbelt 实测")
    def test_seatbelt_最小profile不读取private_tmp外部秘密(self) -> None:
        with temp_workspace() as workspace, tempfile.TemporaryDirectory(
            prefix="icode-seatbelt-secret-", dir="/private/tmp",
        ) as raw_secret:
            secret = Path(raw_secret) / "secret"
            secret.write_text("outside-private-tmp-secret", encoding="utf-8")
            sandbox = MacSeatbeltSandbox(
                sandbox_exec=shutil.which("sandbox-exec") or "sandbox-exec"
            )
            result = subprocess.run(
                sandbox.wrap([shutil.which("cat") or "/bin/cat", str(secret)],
                             workspace=workspace),
                cwd=workspace, capture_output=True, text=True,
                timeout=5, check=False,
            )
            self.assertNotEqual(result.returncode, 0, result)
            self.assertNotIn("outside-private-tmp-secret", result.stdout)

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
