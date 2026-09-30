"""隔离能力层测试（Phase 5）。

核心不是"沙箱好不好用"，而是**能不能坚守诚实**：
没有可用后端时必须自我标注为「应用层限制」，且隔离失败时**拒绝执行**而不是降级执行。
"""

from __future__ import annotations

import ast
from dataclasses import replace
import errno
import hashlib
import ipaddress
import os
import plistlib
import re
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
    ExecuteOnlyFile,
    LandlockSandbox,
    MetadataReadRoot,
    ContainerSandbox,
    MacSeatbeltSandbox,
    NoIsolation,
    WindowsJobLimits,
    WslSandbox,
    capability_report,
    probe_capabilities,
    probe_linux_protected_paths,
    probe_linux_process_tree_cleanup,
    probe_macos_process_group_cleanup,
    probe_macos_protected_paths,
    probe_native_sandbox,
    select_sandbox,
)
from icode.tools import IsolationUnavailable, ToolContext, default_registry
from icode.tools.builtin import run_command
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.workspace import WorkspaceManager
from icode.execution_broker import execute_policy_command


def _metadata_read_root(path: Path) -> MetadataReadRoot:
    path = path.resolve(strict=True)
    status = os.lstat(path)
    return MetadataReadRoot(path, status.st_dev, status.st_ino)


def _macos_non_loopback_ipv4() -> str | None:
    """Return an IPv4 address assigned to this macOS host, if one is usable."""

    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["/sbin/ifconfig", "-a"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    for raw_address in re.findall(r"(?m)^\s*inet\s+([0-9.]+)(?:\s|$)", result.stdout):
        try:
            address = ipaddress.IPv4Address(raw_address)
        except ipaddress.AddressValueError:
            continue
        if (
            address.is_loopback
            or address.is_link_local
            or address.is_unspecified
            or address.is_multicast
            or address.is_reserved
        ):
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((str(address), 0))
        except OSError:
            continue
        return str(address)
    return None


def _seatbelt_stderr_tags(stderr: str) -> str:
    """Expose fixed error categories without printing runner stderr contents."""

    lowered = stderr.lower()
    categories = (
        ("sandbox_exec", ("sandbox-exec",)),
        ("unsupported_host_predicate", ("host must be * or localhost",)),
        ("unbound_variable", ("unbound variable", "undefined variable")),
        ("profile", ("profile", "sbpl", "predicate")),
        ("syntax_or_invalid", ("syntax", "parse", "invalid")),
        ("permission", ("denied", "not permitted", "permission")),
        ("loader", ("dyld", "library not loaded")),
        ("launch", ("cannot execute", "exec failed", "spawn", "launch")),
        ("python_runtime", ("traceback", "fatal python error", "importerror")),
        ("python_import_error", ("importerror", "modulenotfounderror")),
        ("python_name_error", ("nameerror",)),
        ("python_attribute_error", ("attributeerror",)),
        ("python_type_error", ("typeerror",)),
        ("python_value_error", ("valueerror",)),
        ("python_os_error", (
            "oserror", "permissionerror", "filenotfounderror", "timeouterror",
        )),
        ("python_runtime_error", ("runtimeerror", "assertionerror")),
    )
    tags = [
        name for name, needles in categories
        if any(needle in lowered for needle in needles)
    ]
    return "+".join(tags) or ("other" if stderr else "empty")


class TestProbe(unittest.TestCase):
    def test_linux后代清理探针在非Linux平台明确不执行(self) -> None:
        with mock.patch("icode.isolation.sys.platform", "darwin"):
            result = probe_linux_process_tree_cleanup(
                LandlockSandbox(helper="/bin/true", manifest="/bin/true.sha256")
            )

        self.assertFalse(result.executed)
        self.assertFalse(result.passed)
        self.assertEqual(
            result.checks,
            {
                "descendant_started": False,
                "descendant_detached": False,
                "descendant_alive_before_host_kill": False,
                "host_killed": False,
                "descendant_exited": False,
                "no_delayed_write": False,
            },
        )
        self.assertIn("仅适用于 Linux", result.detail)

    def test_linux后代清理探针在helper完整性失败时关闭执行(self) -> None:
        with temp_workspace() as root:
            helper = root / "helper"
            helper.write_text("not an executable helper", encoding="ascii")
            helper.chmod(0o755)
            manifest = root / "helper.sha256"
            manifest.write_text("0" * 64 + "\n", encoding="ascii")
            sandbox = LandlockSandbox(helper=str(helper), manifest=str(manifest))

            with mock.patch("icode.isolation.sys.platform", "linux"):
                result = probe_linux_process_tree_cleanup(sandbox)

        self.assertFalse(result.executed)
        self.assertFalse(result.passed)
        self.assertIn("完整性校验失败", result.detail)

    def test_linux保护路径探针只在Linux上运行(self) -> None:
        sandbox = LandlockSandbox(helper="/bin/true")
        with mock.patch("icode.isolation.sys.platform", "darwin"):
            result = probe_linux_protected_paths(sandbox)

        self.assertFalse(result.executed)
        self.assertFalse(result.passed)
        self.assertEqual(
            result.checks,
            {
                "workspace_write_allowed": False,
                "protected_write_denied": False,
                "protected_rename_denied": False,
            },
        )

    def test_linux保护路径探针使用分层git元数据和正向控制(self) -> None:
        with temp_workspace() as root:
            helper = root / "helper"
            helper.write_bytes(b"probe helper")
            helper.chmod(0o755)
            manifest = root / "helper.sha256"
            manifest.write_text(
                hashlib.sha256(helper.read_bytes()).hexdigest() + "\n",
                encoding="ascii",
            )
            sandbox = LandlockSandbox(
                helper=str(helper), manifest=str(manifest),
            )
            executions = [
                mock.Mock(exit_code=0, error=None, cleanup_ok=True),
                mock.Mock(exit_code=1, error=None, cleanup_ok=True),
                mock.Mock(exit_code=1, error=None, cleanup_ok=True),
            ]

            def simulate_broker(argv, *, cwd, policy, timeout):
                if any("Path('allowed').write_text('ok')" in part for part in argv):
                    (policy.workspace_root / "allowed").write_text(
                        "ok", encoding="utf-8",
                    )
                return executions.pop(0)

            with mock.patch("icode.isolation.sys.platform", "linux"), \
                 mock.patch("icode.execution_broker.execute_policy_command",
                            side_effect=simulate_broker) as execute:
                result = probe_linux_protected_paths(sandbox)

        self.assertTrue(result.executed)
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(
            result.checks,
            {
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
        )
        self.assertEqual(execute.call_count, 3)
        for call in execute.call_args_list:
            argv = call.args[0]
            policy = call.kwargs["policy"]
            self.assertEqual(policy.write_roots, (policy.workspace_root,))
            self.assertEqual(policy.deny_write_roots, policy.protected_paths)
            self.assertEqual(policy.network_mode, NetworkMode.DENY)
            self.assertTrue(
                policy.protected_paths[0].is_relative_to(policy.workspace_root.parent)
            )

    def test_doctor把Linux保护路径实测并入同一份一致性回执(self) -> None:
        native = mock.Mock(
            ready=True,
            checks={"workspace_write": True},
            detail="native ok",
        )
        protected = mock.Mock(
            executed=True,
            passed=True,
            checks={
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
            detail="protected paths ok",
        )
        sandbox = LandlockSandbox(helper="/tmp/helper", manifest="/tmp/manifest")
        with mock.patch("icode.isolation.sys.platform", "linux"), \
             mock.patch("icode.isolation.probe_capabilities", return_value=()), \
             mock.patch("icode.isolation.select_sandbox", return_value=NoIsolation()), \
             mock.patch.object(LandlockSandbox, "from_bundle", return_value=sandbox), \
             mock.patch("icode.isolation.probe_native_sandbox", return_value=native), \
             mock.patch("icode.isolation.probe_linux_protected_paths",
                        return_value=protected):
            report = capability_report()

        self.assertTrue(report["bundled_linux_helper"]["protected_path_probe_passed"])
        self.assertTrue(
            report["conformance_contract"]["outcomes"]["protected_paths"]
        )
        self.assertTrue(
            report["conformance_contract"]["outcomes"]["doctor_self_test"]
        )

    def test_macos保护路径探针只在macOS上运行(self) -> None:
        sandbox = MacSeatbeltSandbox(sandbox_exec="/bin/true")
        with mock.patch("icode.isolation.sys.platform", "linux"):
            result = probe_macos_protected_paths(sandbox)

        self.assertFalse(result.executed)
        self.assertFalse(result.passed)
        self.assertEqual(
            result.checks,
            {
                "workspace_write_allowed": False,
                "protected_write_denied": False,
                "protected_rename_denied": False,
            },
        )

    def test_macos保护路径探针使用正向控制并核验写入和重命名拒绝(self) -> None:
        sandbox = MacSeatbeltSandbox(sandbox_exec="/bin/true")
        executions = [
            mock.Mock(exit_code=0, error=None, cleanup_ok=True),
            mock.Mock(exit_code=1, error=None, cleanup_ok=True),
            mock.Mock(exit_code=1, error=None, cleanup_ok=True),
        ]

        def simulate_broker(argv, *, cwd, policy, timeout):
            if "Path('allowed')" in argv[-1]:
                (policy.workspace_root / "allowed").write_text("ok", encoding="utf-8")
            return executions.pop(0)

        with mock.patch("icode.isolation.sys.platform", "darwin"), \
             mock.patch("icode.execution_broker.execute_policy_command",
                        side_effect=simulate_broker) as execute:
            result = probe_macos_protected_paths(sandbox)

        self.assertTrue(result.executed)
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(
            result.checks,
            {
                "workspace_write_allowed": True,
                "protected_write_denied": True,
                "protected_rename_denied": True,
            },
        )
        self.assertEqual(execute.call_count, 3)
        for call in execute.call_args_list:
            argv = call.args[0]
            policy = call.kwargs["policy"]
            self.assertEqual(argv[0], "/bin/true")
            self.assertEqual(policy.deny_write_roots, policy.protected_paths)
            self.assertEqual(policy.network_mode, NetworkMode.DENY)

    def test_macos保护路径探针正向控制失败时不能记保护路径通过(self) -> None:
        sandbox = MacSeatbeltSandbox(sandbox_exec="/bin/true")
        executions = [
            mock.Mock(exit_code=1, error=None, cleanup_ok=True),
            mock.Mock(exit_code=1, error=None, cleanup_ok=True),
            mock.Mock(exit_code=1, error=None, cleanup_ok=True),
        ]
        with mock.patch("icode.isolation.sys.platform", "darwin"), \
             mock.patch("icode.execution_broker.execute_policy_command",
                        side_effect=executions):
            result = probe_macos_protected_paths(sandbox)

        self.assertFalse(result.passed)
        self.assertFalse(result.checks["protected_write_denied"])
        self.assertFalse(result.checks["protected_rename_denied"])

    def test_报告区分mac同组清理与完整一致性(self) -> None:
        report = capability_report()
        group = report["macos_group_cleanup"]
        self.assertIsInstance(group["passed"], bool)
        self.assertEqual(set(group["checks"]), {"normal_exit", "timeout"}
                         if sys.platform == "darwin" else set())
        # 一致性合同现在按已采集证据保守评分（不冒充 ready）
        conformance = report["conformance_contract"]
        self.assertTrue(conformance["executed"])
        self.assertIn("score", conformance)
        self.assertIn("outcomes", conformance)
        self.assertEqual(conformance["score"]["total"], 10)
        self.assertFalse(conformance["score"]["ready"])
        if sys.platform != "darwin":
            self.assertFalse(group["executed"])
            self.assertFalse(group["passed"])

    def test_局部进程清理探针不计作完整后端自检(self) -> None:
        from types import SimpleNamespace

        cases = (
            ("win32", "icode.windows_job.probe_windows_job_cleanup", {
                "executed": True,
                "passed": True,
                "checks": {"normal_exit": True, "timeout": True},
                "detail": "ok",
            }),
            ("darwin", "icode.isolation.probe_macos_process_group_cleanup", {
                "executed": True,
                "passed": True,
                "checks": {"normal_exit": True, "timeout": True},
                "detail": "ok",
            }),
        )
        for platform, probe_path, probe_result in cases:
            with self.subTest(platform=platform), \
                 mock.patch("icode.isolation.sys.platform", platform), \
                 mock.patch("icode.isolation.probe_capabilities", return_value=()), \
                 mock.patch("icode.isolation.select_sandbox", return_value=NoIsolation()), \
                 mock.patch(probe_path, return_value=SimpleNamespace(**probe_result)):
                report = capability_report()

            contract = report["conformance_contract"]
            self.assertTrue(contract["executed"])
            self.assertEqual(len(contract["outcomes"]), 10)
            self.assertFalse(contract["outcomes"]["doctor_self_test"])
            self.assertFalse(contract["outcomes"]["process_tree_cleanup"])

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
            protected = probe_linux_protected_paths(sandbox)
            self.assertTrue(protected.executed)
            self.assertTrue(protected.passed, protected.detail)
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
                    [str(system_python), "-c",
                     "import socket;\n"
                     "for family, kind in ((socket.AF_INET, socket.SOCK_STREAM),\n"
                     "                     (socket.AF_INET6, socket.SOCK_STREAM),\n"
                     "                     (socket.AF_INET, socket.SOCK_DGRAM),\n"
                     "                     (socket.AF_UNIX, socket.SOCK_STREAM)):\n"
                     "    try: socket.socket(family, kind)\n"
                     "    except PermissionError: continue\n"
                     "    raise AssertionError('default-deny socket was allowed')\n"
                     "for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM,\n"
                     "             socket.SOCK_SEQPACKET):\n"
                     "    left, right = socket.socketpair(socket.AF_UNIX, kind)\n"
                     "    left.send(b'ipc'); assert right.recv(3) == b'ipc'\n"
                     "    left.close(); right.close()\n"
                     "try: socket.socketpair(socket.AF_INET)\n"
                     "except PermissionError: pass\n"
                     "else: raise AssertionError('non-local socketpair allowed')\n"
                     "for kind, protocol in ((socket.SOCK_RAW, 0),\n"
                     "                       (socket.SOCK_STREAM, 1)):\n"
                     "    try: socket.socketpair(socket.AF_UNIX, kind, protocol)\n"
                     "    except PermissionError: continue\n"
                     "    raise AssertionError('invalid local socketpair allowed')\n"
                     "print('socket-denied; AF_UNIX-socketpair-only')"],
                    workspace=checkout,
                ),
                capture_output=True, text=True, timeout=4, check=False,
            )
            self.assertEqual(denied.returncode, 0, denied.stderr)
            self.assertIn("socket-denied; AF_UNIX-socketpair-only", denied.stdout)
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
                '    return run_helper(argc, argv, getenv("ICODE_TEST_SETGROUPS_PATH"),\n'
                '                      "/proc/self/uid_map");\n'
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
        # 一致性合同按已采集证据保守评分：评分在但 ready 不得为真
        self.assertTrue(report["conformance_contract"]["executed"])
        self.assertEqual(report["conformance_contract"]["score"]["total"], 10)
        self.assertFalse(report["conformance_contract"]["score"]["ready"])
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
    def test_Seatbelt错误分类只暴露固定标签(self) -> None:
        self.assertEqual(
            _seatbelt_stderr_tags("sandbox-exec: unbound variable: TIOCSTI"),
            "sandbox_exec+unbound_variable",
        )
        self.assertEqual(_seatbelt_stderr_tags(""), "empty")

    def test_Seatbelt不支持的数值主机谓词暴露固定标签(self) -> None:
        self.assertEqual(
            _seatbelt_stderr_tags(
                "sandbox-exec: host must be * or localhost in network address"
            ),
            "sandbox_exec+unsupported_host_predicate",
        )

    def test_Seatbelt运行时异常类别保持固定且不包含原始内容(self) -> None:
        self.assertEqual(
            _seatbelt_stderr_tags(
                "Traceback (most recent call last):\nNameError: private value"
            ),
            "python_runtime+python_name_error",
        )

    def test_landlock_Reviewer包装显式传入工作区只读标记(self) -> None:
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            helper = root / "fake-landlock-helper"
            helper.write_text("probe", encoding="ascii")
            sandbox = LandlockSandbox(helper=str(helper))

            argv = sandbox.wrap_read_only(["/bin/true"], workspace=workspace)

        self.assertEqual(argv[0], str(helper))
        self.assertIn("--workspace-read-only", argv)
        self.assertNotIn("--metadata-read", argv)
        with self.assertRaisesRegex(RuntimeError, "network grants"):
            sandbox.wrap_read_only(["/bin/true"], workspace=workspace, network=True)

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

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux 临时 CONNECT 候选包装")
    def test_leased_connect_candidate_only_accepts_private_seqpacket_and_deny_policy(self) -> None:
        with temp_workspace() as root:
            workspace = (root / "code").resolve()
            workspace.mkdir()
            policy = SandboxPolicy(
                schema_version=1, run_id="proxy-candidate", ticket_id="proxy-candidate",
                step="code", workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
            )
            sandbox = LandlockSandbox(helper="/bin/true")
            host, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            stream_host, stream_sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                with mock.patch.object(sandbox, "prepare_policy"):
                    wrapped = sandbox.wrap_leased_connect_candidate(
                        ["/usr/bin/true"], policy=policy, sender_control=sender,
                    )
                    self.assertIn("--network-loopback-only", wrapped)
                    descriptor_index = wrapped.index("--proxy-control-fd")
                    self.assertEqual(wrapped[descriptor_index + 1], str(sender.fileno()))
                    self.assertEqual(wrapped[-2:], ["--", "/usr/bin/true"])
                    with self.assertRaises(ValueError):
                        sandbox.wrap_policy(["/usr/bin/true"], policy=policy, network=True)
                    with self.assertRaises(ValueError):
                        sandbox.wrap_leased_connect_candidate(
                            ["/usr/bin/true"],
                            policy=replace(
                                policy,
                                network_mode=NetworkMode.PROXY_ALLOWLIST,
                                allowed_domains=("packages.example",),
                            ),
                            sender_control=sender,
                        )
                    with self.assertRaises(ValueError):
                        sandbox.wrap_leased_connect_candidate(
                            ["/usr/bin/true"], policy=policy,
                            sender_control=stream_sender,
                        )
            finally:
                for endpoint in (host, sender, stream_host, stream_sender):
                    endpoint.close()

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux Landlock read-only policy")
    def test_landlock_Git只读工作区拒绝可执行授权重叠(self) -> None:
        sandbox = LandlockSandbox(helper="/not-needed-for-static-check")
        for root in (Path("/"), Path("/usr"), Path("/bin"), Path(sys.prefix)):
            with self.subTest(root=root):
                with self.assertRaises(ValueError):
                    sandbox._validate_non_executable_workspace(root)

    @unittest.skipUnless(
        sys.platform.startswith("linux") and shutil.which("cc"),
        "需要 Linux Landlock 和 C 编译器验证精确执行授权",
    )
    def test_landlock_execute_only_authorizes_the_fixed_payload_binary(self) -> None:
        python = Path(shutil.which("python3", path="/usr/bin:/bin") or "").resolve()
        self.assertTrue(python.is_file())
        source = Path(__file__).resolve().parents[1] / "native" / "linux" / "icode_landlock.c"

        with temp_workspace() as root:
            helper = root / "icode-landlock"
            subprocess.run(
                [
                    shutil.which("cc") or "cc", "-std=c11", "-O2", "-Wall", "-Wextra",
                    "-Werror", str(source), "-o", str(helper),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            manifest = root / "icode-landlock.sha256"
            manifest.write_text(
                hashlib.sha256(helper.read_bytes()).hexdigest() + "\n", encoding="ascii"
            )
            workspace = root / "code"
            workspace.mkdir()
            policy = SandboxPolicy(
                schema_version=1,
                run_id="execute-only-test",
                ticket_id="execute-only-test",
                step="review",
                workspace_root=workspace.resolve(),
                read_roots=(workspace.resolve(),),
                write_roots=(workspace.resolve(),),
                deny_read_roots=(),
                deny_write_roots=(),
                network_mode=NetworkMode.DENY,
                allowed_domains=(),
                process_limit=8,
                wall_timeout_seconds=10,
                output_limit_bytes=1024,
                protected_paths=(),
            )
            script = (
                "import subprocess, sys\n"
                "allowed = subprocess.run([sys.executable, '-c', \"print('allowed-child')\"], "
                "capture_output=True, text=True, check=False)\n"
                "assert allowed.returncode == 0, allowed.stderr\n"
                "assert 'allowed-child' in allowed.stdout\n"
                "try:\n"
                "    subprocess.run(['/bin/sh', '-c', 'exit 0'], check=False)\n"
                "except PermissionError:\n"
                "    pass\n"
                "else:\n"
                "    raise AssertionError('unlisted executable was allowed')\n"
                "print('execute-only-ok')\n"
            )
            sandbox = LandlockSandbox(helper=str(helper), manifest=str(manifest))
            result = subprocess.run(
                sandbox._wrap_policy_with_metadata_roots(
                    [str(python), "-c", script],
                    policy=policy,
                    metadata_roots=(),
                    execute_only=python,
                ),
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("execute-only-ok", result.stdout)

            claims = sandbox._validated_execute_only_files(python, [str(python)])
            stale_payload = ExecuteOnlyFile(
                claims[0].path, claims[0].device, claims[0].inode + 1,
            )
            identity_mismatch = subprocess.run(
                sandbox._wrap_with_metadata_roots(
                    [str(python), "-c", "print('must-not-start')"],
                    workspace=workspace,
                    metadata_roots=(),
                    workspace_read_only=False,
                    execute_only=(stale_payload, *claims[1:]),
                ),
                capture_output=True,
                text=True,
                timeout=6,
                check=False,
            )
            self.assertNotEqual(identity_mismatch.returncode, 0)
            self.assertIn("execute-only file identity changed", identity_mismatch.stderr)
            self.assertNotIn("must-not-start", identity_mismatch.stdout)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux Landlock read-only policy")
    def test_landlock_Git只读工作区允许缺失的可选系统路径(self) -> None:
        sandbox = LandlockSandbox(helper="/not-needed-for-static-check")
        with temp_workspace() as root:
            workspace = (root / "code").resolve()
            workspace.mkdir()
            original_resolve = Path.resolve

            def simulate_missing_lib64(path: Path, *, strict: bool = False) -> Path:
                if path == Path("/lib64"):
                    if strict:
                        raise FileNotFoundError("simulated optional root is absent")
                    return path
                return original_resolve(path, strict=strict)

            with mock.patch.object(Path, "resolve", simulate_missing_lib64):
                self.assertEqual(
                    sandbox._validate_non_executable_workspace(workspace), workspace,
                )

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux Git 元数据只读授权")
    def test_landlock_Git元数据根必须明确且与工作区隔离(self) -> None:
        with temp_workspace() as root:
            workspace = root / "code"
            workspace.mkdir()
            metadata = root / "gitdir"
            metadata.mkdir()
            sandbox = LandlockSandbox(helper="/not-needed-for-static-check")
            metadata_claim = _metadata_read_root(metadata)

            self.assertEqual(
                sandbox._validated_metadata_roots(workspace, (metadata_claim,)),
                (metadata_claim,),
            )
            for roots in (
                (_metadata_read_root(workspace),),
                (_metadata_read_root(root),),
                (_metadata_read_root(Path("/")),),
                (_metadata_read_root(Path("/usr")),),
                (_metadata_read_root(Path.home()),),
                (_metadata_read_root(Path(sys.prefix)),),
                (MetadataReadRoot(root / "missing", 0, 0),),
                ("not-a-path-sequence",),
            ):
                with self.subTest(roots=roots):
                    with self.assertRaises(ValueError):
                        sandbox._validated_metadata_roots(workspace, roots)

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("cc"),
                         "需要 Linux C 编译器验证只读 Git 元数据边界")
    def test_landlock_Git元数据根只读且不可执行(self) -> None:
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

            workspace = root / "code"
            workspace.mkdir()
            metadata = root / "gitdir"
            metadata.mkdir()
            metadata_claim = _metadata_read_root(metadata)
            index = metadata / "index"
            index.write_text("index-data\n", encoding="ascii")
            hook_marker = workspace / "hook-ran"
            hook = metadata / "hook"
            hook.write_text(f"#!/bin/sh\ntouch {hook_marker}\n", encoding="utf-8")
            hook.chmod(0o755)
            outside = root / "not-authorized"
            outside.write_text("secret\n", encoding="ascii")

            policy = SandboxPolicy(
                schema_version=1, run_id="git-ro-test", ticket_id="git-ro-test",
                step="code", workspace_root=workspace.resolve(),
                read_roots=(workspace.resolve(),), write_roots=(workspace.resolve(),),
                deny_read_roots=(), deny_write_roots=(),
                network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
            )
            sandbox = LandlockSandbox(helper=str(helper), manifest=str(manifest))
            script = """
from pathlib import Path
import subprocess
import sys

meta, work, outside = sys.argv[1:]
assert (Path(meta) / "index").read_text() == "index-data\\n"
(Path(work) / "allowed-write").write_text("ok")

def must_be_denied(action, label):
    try:
        action()
    except PermissionError:
        return
    raise AssertionError(f"unexpected permission: {label}")

must_be_denied(lambda: (Path(meta) / "index").write_text("changed"), "overwrite")
must_be_denied(lambda: (Path(meta) / "new-index").write_text("new"), "create")
must_be_denied(lambda: Path(outside).read_text(), "outside read")
try:
    run = subprocess.run([str(Path(meta) / "hook")], check=False)
except PermissionError:
    pass
else:
    assert run.returncode != 0, run.returncode
assert not (Path(work) / "hook-ran").exists()
print("metadata-read-only-ok")
"""
            result = subprocess.run(
                sandbox._wrap_policy_with_metadata_roots(
                    ["/usr/bin/python3", "-c", script,
                     str(metadata), str(workspace), str(outside)],
                    policy=policy, metadata_roots=(metadata_claim,),
                ),
                capture_output=True, text=True, timeout=6, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("metadata-read-only-ok", result.stdout)
            self.assertEqual(index.read_text(encoding="ascii"), "index-data\n")
            self.assertFalse((metadata / "new-index").exists())
            self.assertFalse(hook_marker.exists())

            noexec_script = workspace / "must-not-execute"
            noexec_marker = workspace / "noexec-marker"
            noexec_script.write_text(
                f"#!/bin/sh\ntouch {noexec_marker}\n", encoding="utf-8"
            )
            noexec_script.chmod(0o755)
            read_only_probe = subprocess.run(
                sandbox._wrap_policy_with_metadata_roots(
                    [
                        "/usr/bin/python3", "-c",
                        "from pathlib import Path; import subprocess, sys\n"
                        "script = Path(sys.argv[1]); marker = Path(sys.argv[2])\n"
                        "assert script.read_text().startswith('#!/bin/sh')\n"
                        "try: script.write_text('changed')\n"
                        "except PermissionError: pass\n"
                        "else: raise AssertionError('workspace is writable')\n"
                        "try: result = subprocess.run([str(script)], check=False)\n"
                        "except PermissionError: pass\n"
                        "else: assert result.returncode != 0, result.returncode\n"
                        "assert not marker.exists()\n",
                        str(noexec_script), str(noexec_marker),
                    ],
                    policy=policy,
                    metadata_roots=(),
                    workspace_read_only=True,
                ),
                capture_output=True, text=True, timeout=6, check=False,
            )
            self.assertEqual(read_only_probe.returncode, 0, read_only_probe.stderr)
            self.assertFalse(noexec_marker.exists())

            metadata_file = root / "git-pointer"
            metadata_file.write_text(
                f"#!/bin/sh\ntouch {workspace / 'metadata-file-executed'}\n",
                encoding="utf-8",
            )
            metadata_file.chmod(0o755)
            file_claim = _metadata_read_root(metadata_file)
            file_probe = subprocess.run(
                sandbox._wrap_policy_with_metadata_roots(
                    [
                        "/usr/bin/python3", "-c",
                        "from pathlib import Path; import subprocess, sys\n"
                        "path = Path(sys.argv[1])\n"
                        "assert path.read_text().startswith('#!/bin/sh')\n"
                        "try: path.write_text('changed')\n"
                        "except PermissionError: pass\n"
                        "else: raise AssertionError('metadata file writable')\n"
                        "try: result = subprocess.run([str(path)], check=False)\n"
                        "except PermissionError: pass\n"
                        "else: assert result.returncode != 0, result.returncode\n",
                        str(metadata_file),
                    ],
                    policy=policy,
                    metadata_roots=(file_claim,),
                ),
                capture_output=True, text=True, timeout=6, check=False,
            )
            self.assertEqual(file_probe.returncode, 0, file_probe.stderr)
            self.assertFalse((workspace / "metadata-file-executed").exists())

            moved_metadata = root / "gitdir-original"
            metadata.rename(moved_metadata)
            metadata.mkdir()
            for entry in moved_metadata.iterdir():
                shutil.copy2(entry, metadata / entry.name)
            stale_claim_marker = workspace / "stale-metadata-claim-ran"
            stale_claim = subprocess.run(
                [
                    str(helper), "--workspace", str(workspace),
                    "--parent-pid", str(os.getpid()),
                    "--metadata-read", str(metadata),
                    str(metadata_claim.device), str(metadata_claim.inode), "--",
                    "/usr/bin/python3", "-c",
                    "from pathlib import Path\n"
                    "Path('stale-metadata-claim-ran').write_text('ran')",
                ],
                capture_output=True, text=True, timeout=6, check=False,
            )
            self.assertNotEqual(stale_claim.returncode, 0, stale_claim.stdout)
            self.assertFalse(stale_claim_marker.exists())
            with self.assertRaises(ValueError):
                sandbox._validated_metadata_roots(workspace, (metadata_claim,))

            no_metadata_grant = subprocess.run(
                sandbox.wrap_policy(
                    ["/usr/bin/python3", "-c",
                     "from pathlib import Path; import sys; Path(sys.argv[1]).read_text()",
                     str(index)],
                    policy=policy,
                ),
                capture_output=True, text=True, timeout=6, check=False,
            )
            self.assertNotEqual(no_metadata_grant.returncode, 0)
            self.assertIn("PermissionError", no_metadata_grant.stderr)

            metadata_alias = root / "metadata-alias"
            metadata_alias.symlink_to(metadata, target_is_directory=True)
            parent_alias = root / "parent-alias"
            parent_alias.symlink_to(root, target_is_directory=True)
            escaped_parent_path = parent_alias / metadata.name
            marker = workspace / "symlink-root-payload-ran"
            for unsafe_root in (metadata_alias, escaped_parent_path):
                with self.subTest(unsafe_root=unsafe_root.name):
                    result = subprocess.run(
                        [
                            str(helper), "--workspace", str(workspace),
                            "--parent-pid", str(os.getpid()),
                            "--metadata-read", str(unsafe_root),
                            str(os.lstat(unsafe_root).st_dev),
                            str(os.lstat(unsafe_root).st_ino), "--",
                            "/usr/bin/python3", "-c",
                            "from pathlib import Path; Path('symlink-root-payload-ran').write_text('ran')",
                        ],
                        capture_output=True, text=True, timeout=6, check=False,
                    )
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertFalse(marker.exists())

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
        runtime_prefix = Path(sys.base_prefix).resolve()
        standard_roots = tuple(Path(path) for path in ("/usr", "/bin", "/lib", "/lib64"))
        if runtime_prefix.is_dir() and not any(
            runtime_prefix == root or root in runtime_prefix.parents
            for root in standard_roots
        ):
            mounts = [
                tuple(argv[index + 1:index + 3])
                for index, item in enumerate(argv[:-2]) if item == "--ro-bind"
            ]
            self.assertIn((str(runtime_prefix), str(runtime_prefix)), mounts)
            self.assertNotIn((str(runtime_prefix.parent), str(runtime_prefix.parent)), mounts)

    def test_bwrap_只读审查包装使用只读工作区绑定(self) -> None:
        with temp_workspace() as workspace:
            ctx = ToolContext(
                root=workspace, sandbox=BubblewrapSandbox(), read_only_workspace=True,
            )
            try:
                ctx.pin_read_only_workspace()
                argv = ctx.wrap_command(["python", "-m", "unittest"])
                self.assertIn("--ro-bind-fd", argv)
                bind = argv.index("--ro-bind-fd")
                self.assertEqual(argv[bind + 1], str(ctx.read_only_workspace_fd))
                self.assertEqual(argv[bind + 2], str(workspace.resolve()))
                self.assertNotIn("--bind", argv)
                self.assertIn("--unshare-net", argv)
            finally:
                ctx.close()

    def test_bwrap_只读审查将排除目录覆盖为空的只读挂载(self) -> None:
        with temp_workspace() as workspace:
            excluded = workspace / ".icode_output"
            nested = excluded / "ticket-1" / "out"
            nested.mkdir(parents=True)
            ctx = ToolContext(
                root=workspace, sandbox=BubblewrapSandbox(), read_only_workspace=True,
                deny_read_roots=(excluded, nested),
            )
            try:
                ctx.pin_read_only_workspace()
                argv = ctx.wrap_command(["python", "-m", "unittest"])
            finally:
                ctx.close()

        workspace_bind = next(
            index for index, item in enumerate(argv[:-2])
            if item == "--ro-bind-fd"
            and argv[index + 2] == str(workspace.resolve())
        )
        self.assertTrue(argv[workspace_bind + 1].isdigit())
        self.assertEqual(argv[workspace_bind + 2], str(workspace.resolve()))
        mounts = [
            tuple(argv[index + 1:index + 2])
            for index, item in enumerate(argv[:-2]) if item == "--tmpfs"
        ]
        self.assertEqual(mounts.count((str(excluded.resolve()),)), 1)
        self.assertIn("--remount-ro", argv)
        self.assertEqual(argv[argv.index("--remount-ro") + 1], str(excluded.resolve()))
        self.assertLess(workspace_bind, argv.index("--tmpfs", workspace_bind))
        self.assertIn("--unshare-net", argv)

    def test_bwrap_只读审查排除路径不存在或含符号链接时拒绝(self) -> None:
        with temp_workspace() as temporary_root:
            workspace = temporary_root / "workspace"
            workspace.mkdir()
            sandbox = BubblewrapSandbox()
            pinned = sandbox.pin_read_only_workspace(workspace)

            def wrap_excluding(deny_read_roots):
                return sandbox.wrap_read_only_excluding(
                    ["/bin/true"], workspace=pinned.path, workspace_fd=pinned.fd,
                    deny_read_roots=deny_read_roots,
                )

            try:
                missing = workspace / ".icode_output" / "missing"
                with self.assertRaises((OSError, ValueError)):
                    wrap_excluding((missing,))

                outside = workspace.parent / "outside-ledger"
                outside.mkdir()
                internal = workspace / "private-target"
                internal.mkdir()
                outside_link = workspace / "outside-alias"
                outside_link.symlink_to(outside, target_is_directory=True)
                inside_link = workspace / "inside-alias"
                inside_link.symlink_to(internal, target_is_directory=True)
                file_root = workspace / "ordinary-file"
                file_root.write_text("not a directory", encoding="utf-8")
                for invalid in (
                    workspace, workspace.parent, outside, workspace / ".." / "outside-ledger",
                    outside_link, inside_link, file_root,
                ):
                    with self.subTest(invalid=invalid), self.assertRaises((OSError, ValueError)):
                        wrap_excluding((invalid,))
            finally:
                os.close(pinned.fd)

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bwrap"),
                         "需要 Linux bubblewrap")
    def test_bwrap_只读审查包装实际阻断工作区写入(self) -> None:
        with temp_workspace() as workspace:
            target = workspace / "reviewed.py"
            target.write_text("original\n", encoding="utf-8")
            python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
            ctx = ToolContext(
                root=workspace, sandbox=BubblewrapSandbox(), read_only_workspace=True,
            )
            ctx.pin_read_only_workspace()
            wrapped = ctx.wrap_command(
                [python, "-c", "from pathlib import Path; Path('reviewed.py').write_text('changed')"],
            )
            try:
                result = subprocess.run(
                    wrapped, cwd=wrapped.cwd, pass_fds=wrapped.pass_fds,
                    capture_output=True, text=True, check=False,
                )
            finally:
                ctx.close()
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(target.read_text(encoding="utf-8"), "original\n")

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bwrap"),
                         "需要 Linux bubblewrap")
    def test_bwrap只读Reviewer在启动前根路径被替换仍绑定已固定目录(self) -> None:
        with temp_workspace() as temporary_root:
            workspace = temporary_root / "workspace"
            workspace.mkdir()
            original = temporary_root / "workspace-original"
            decoy = temporary_root / "workspace-decoy"
            decoy.mkdir()
            (workspace / "marker.txt").write_text("approved-root\n", encoding="utf-8")
            (decoy / "marker.txt").write_text("replacement-root\n", encoding="utf-8")
            ctx = ToolContext(
                root=workspace, sandbox=BubblewrapSandbox(), read_only_workspace=True,
            )
            ctx.pin_read_only_workspace()
            python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
            code = (
                "from pathlib import Path\n"
                "marker = Path('marker.txt')\n"
                "assert marker.read_text() == 'approved-root\\n'\n"
                "try: marker.write_text('tampered')\n"
                "except OSError: pass\n"
                "else: raise AssertionError('workspace root is writable')\n"
                "print(marker.read_text().strip())\n"
            )
            real_run = subprocess.run

            def replace_workspace_then_launch(*args, **kwargs):
                workspace.rename(original)
                workspace.symlink_to(decoy, target_is_directory=True)
                return real_run(*args, **kwargs)

            try:
                with mock.patch("subprocess.run", side_effect=replace_workspace_then_launch):
                    result = run_command(ctx, [python, "-c", code], timeout=15)
            finally:
                ctx.close()

            self.assertTrue(result.ok, result.content)
            self.assertEqual(result.meta["exit_code"], 0)
            self.assertIn("approved-root", result.content)
            self.assertNotIn("replacement-root", result.content)
            self.assertEqual(
                (original / "marker.txt").read_text(encoding="utf-8"),
                "approved-root\n",
            )
            self.assertEqual(
                (decoy / "marker.txt").read_text(encoding="utf-8"),
                "replacement-root\n",
            )

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bwrap"),
                         "需要 Linux bubblewrap")
    def test_bwrap_只读Reviewer实际隐藏工单账本且阻断所有写入(self) -> None:
        with temp_workspace() as temporary_root:
            workspace = temporary_root / "workspace"
            workspace.mkdir()
            source = workspace / "reviewed.py"
            source.write_text("source-original\n", encoding="utf-8")
            output_root = workspace / ".icode_output"
            ticket_dir = output_root / "ticket-1"
            out_dir = ticket_dir / "review"
            out_dir.mkdir(parents=True)
            ledger = ticket_dir / "ledger.json"
            ledger.write_text("private-ledger\n", encoding="utf-8")
            outside_secret = workspace.parent / "outside-secret.txt"
            outside_secret.write_text("outside-secret\n", encoding="utf-8")

            code = (
                "from pathlib import Path\n"
                "source = Path('reviewed.py')\n"
                "assert source.read_text() == 'source-original\\n'\n"
                "ledger = Path('.icode_output/ticket-1/ledger.json')\n"
                "assert not ledger.exists()\n"
                "try: ledger.read_text()\n"
                "except FileNotFoundError: pass\n"
                "else: raise AssertionError('ledger was readable')\n"
                "assert Path('.icode_output').is_dir()\n"
                "assert not any(Path('.icode_output').iterdir())\n"
                "for fd_path in Path('/proc/self/fd').iterdir():\n"
                "    try: (fd_path / '.icode_output/ticket-1/ledger.json').read_text()\n"
                "    except OSError: pass\n"
                "    else: raise AssertionError('ledger was readable through inherited fd')\n"
                "for path in (source, Path('.icode_output/new.json')):\n"
                "    try: path.write_text('tampered')\n"
                "    except OSError: pass\n"
                "    else: raise AssertionError(f'writable: {path}')\n"
                f"outside = Path({str(outside_secret)!r})\n"
                "try: outside.read_text()\n"
                "except (FileNotFoundError, PermissionError): pass\n"
                "else: raise AssertionError('outside workspace was readable')\n"
                "print('review-boundary-ok')\n"
            )
            ctx = ToolContext(
                root=workspace, sandbox=BubblewrapSandbox(), read_only_workspace=True,
                deny_read_roots=(output_root, out_dir),
            )
            try:
                ctx.pin_read_only_workspace()
                python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
                wrapped = ctx.wrap_command([python, "-c", code])
                result = subprocess.run(
                    wrapped, cwd=wrapped.cwd, pass_fds=wrapped.pass_fds,
                    capture_output=True, text=True, check=False,
                )
            except IsolationUnavailable as exc:
                self.fail(f"Bubblewrap 只读排除目录未能包装命令：{exc}")
            finally:
                ctx.close()
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(result.stdout.strip(), "review-boundary-ok")
            self.assertEqual(source.read_text(encoding="utf-8"), "source-original\n")
            self.assertEqual(ledger.read_text(encoding="utf-8"), "private-ledger\n")
            self.assertEqual(outside_secret.read_text(encoding="utf-8"), "outside-secret\n")

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
        runtime_prefix = str(Path(sys.base_prefix).resolve())
        self.assertIn(f'(subpath "{runtime_prefix}")', profile)
        self.assertNotIn(f'(subpath "{Path(runtime_prefix).parent}")', profile)
        self.assertNotIn('(subpath "/private/tmp")', profile)
        self.assertNotIn("(allow network*)", profile)
        self.assertNotIn("(allow process*)", profile)
        self.assertIn("(allow process-exec)", profile)
        self.assertIn("(allow process-fork)", profile)
        self.assertIn("(allow signal (target same-sandbox))", profile)

    def test_seatbelt_只读审查profile不给工作区写权限(self) -> None:
        workspace = Path("/tmp/review-ws").resolve()
        argv = MacSeatbeltSandbox().wrap_read_only(["python", "-m", "unittest"],
                                                   workspace=workspace)
        profile = argv[argv.index("-p") + 1]
        quoted_workspace = str(workspace).replace("\\", "\\\\").replace('"', '\\"')
        self.assertIn(f'(allow file-read* (subpath "{quoted_workspace}"))', profile)
        self.assertNotIn(f'(allow file-write* (subpath "{quoted_workspace}"))', profile)

    def test_seatbelt_只读Reviewer把排除目录从工作区读授权中精确剔除(self) -> None:
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            excluded = workspace / '.icode_output "private"'
            excluded.mkdir()
            wrap_excluding = getattr(
                MacSeatbeltSandbox(sandbox_exec="/usr/bin/sandbox-exec"),
                "wrap_read_only_excluding", None,
            )
            self.assertTrue(callable(wrap_excluding), "Seatbelt 缺少只读排除目录能力")
            argv = wrap_excluding(
                ["python", "-m", "unittest"], workspace=workspace,
                deny_read_roots=(excluded,),
            )

        profile = argv[argv.index("-p") + 1]
        quoted_workspace = str(workspace.resolve()).replace("\\", "\\\\").replace('"', '\\"')
        quoted_excluded = str(excluded.resolve()).replace("\\", "\\\\").replace('"', '\\"')
        self.assertIn(
            f'(allow file-read* (require-all (subpath "{quoted_workspace}") '
            f'(require-not (literal "{quoted_excluded}")) '
            f'(require-not (subpath "{quoted_excluded}"))))',
            profile,
        )
        self.assertNotIn(f'(allow file-read* (subpath "{quoted_workspace}"))', profile)
        self.assertNotIn("(allow network*)", profile)

    def test_seatbelt_只读Reviewer对不确定排除路径拒绝包装(self) -> None:
        with temp_workspace() as temporary_root:
            workspace = temporary_root / "workspace"
            workspace.mkdir()
            wrap_excluding = getattr(
                MacSeatbeltSandbox(sandbox_exec="/usr/bin/sandbox-exec"),
                "wrap_read_only_excluding", None,
            )
            self.assertTrue(callable(wrap_excluding), "Seatbelt 缺少只读排除目录能力")
            missing = workspace / ".icode_output" / "missing"
            with self.assertRaises((OSError, ValueError)):
                wrap_excluding(["/usr/bin/true"], workspace=workspace,
                               deny_read_roots=(missing,))
            outside = temporary_root / "outside"
            outside.mkdir()
            for invalid in (workspace, workspace.parent, outside):
                with self.subTest(invalid=invalid), self.assertRaises((OSError, ValueError)):
                    wrap_excluding(["/usr/bin/true"], workspace=workspace,
                                   deny_read_roots=(invalid,))
            real = workspace / "real"
            real.mkdir()
            alias = workspace / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises((OSError, ValueError)):
                wrap_excluding(["/usr/bin/true"], workspace=workspace,
                               deny_read_roots=(alias,))

    def test_seatbelt_只读Reviewer拒绝与额外Python读授权重叠的账本路径(self) -> None:
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            output_root = workspace / ".icode_output"
            output_root.mkdir()
            sandbox = MacSeatbeltSandbox(sandbox_exec="/usr/bin/sandbox-exec")
            wrap_excluding = getattr(sandbox, "wrap_read_only_excluding", None)
            self.assertTrue(callable(wrap_excluding), "Seatbelt 缺少只读排除目录能力")
            with mock.patch("icode.isolation.sys.base_prefix", str(output_root)):
                with self.assertRaises(ValueError):
                    wrap_excluding(
                        ["/usr/bin/true"], workspace=workspace,
                        deny_read_roots=(output_root,),
                    )

    def test_seatbelt_只读Reviewer在macOS拒绝PATH外部指定的沙箱程序(self) -> None:
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            output_root = workspace / ".icode_output"
            output_root.mkdir()
            sandbox = MacSeatbeltSandbox(sandbox_exec="/tmp/untrusted-sandbox-exec")
            wrap_excluding = getattr(sandbox, "wrap_read_only_excluding", None)
            self.assertTrue(callable(wrap_excluding), "Seatbelt 缺少只读排除目录能力")
            with mock.patch("icode.isolation.sys.platform", "darwin"):
                with self.assertRaises(ValueError):
                    wrap_excluding(
                        ["/usr/bin/true"], workspace=workspace,
                        deny_read_roots=(output_root,),
                    )

    def test_seatbelt_无账本排除根的只读Reviewer也固定系统沙箱程序(self) -> None:
        with temp_workspace() as workspace, mock.patch(
            "icode.isolation.sys.platform", "darwin",
        ):
            trusted = MacSeatbeltSandbox().wrap_read_only(
                ["/usr/bin/true"], workspace=workspace,
            )
            self.assertEqual(trusted[0], "/usr/bin/sandbox-exec")

            untrusted = MacSeatbeltSandbox(sandbox_exec="/tmp/untrusted-sandbox-exec")
            with self.assertRaises(ValueError):
                untrusted.wrap_read_only(["/usr/bin/true"], workspace=workspace)

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
                "identity = f'{os.getpid()}:{os.getsid(0)}:{os.getpgid(0)}'\n"
                "Path('seatbelt-grandchild-identity').write_text(identity)\n"
                "Path('seatbelt-grandchild-started').write_text('yes')\n"
                "deadline = time.monotonic() + 15\n"
                "while time.monotonic() < deadline and not Path('seatbelt-grandchild-release').exists():\n"
                "    time.sleep(0.02)\n"
                "if not Path('seatbelt-grandchild-release').exists():\n"
                "    Path('seatbelt-grandchild-release-missed').write_text('timeout')\n"
                "    raise SystemExit(2)\n"
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
            (workspace / "seatbelt-grandchild-release").write_text("release", encoding="utf-8")
            self.assertEqual(descendants.exit_code, 0, descendants)
            self.assertIsNone(descendants.error, descendants)
            self.assertIn("grandchild-started", descendants.output)
            # 现有 Seatbelt profile 不拦截 setsid；cleanup_ok 仅覆盖原进程组。
            # 把真实残留锁成已知负例，并要求自动策略入口继续不可用。
            self.assertFalse((workspace / "seatbelt-setsid-denied").exists(), descendants)
            identity = tuple(
                int(part) for part in
                (workspace / "seatbelt-grandchild-identity").read_text(encoding="utf-8").split(":")
            )
            self.assertEqual(len(identity), 3, identity)
            self.assertEqual(identity[1:], identity[:1] * 2, "孙进程未成为独立 session/process-group leader")
            self.assertFalse((workspace / "seatbelt-grandchild-release-missed").exists())
            survived = workspace / "seatbelt-grandchild-survived"
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not survived.exists():
                time.sleep(0.05)
            child_output = (workspace / "seatbelt-grandchild-output").read_text(
                encoding="utf-8", errors="replace",
            )
            self.assertTrue(
                survived.exists(),
                f"脱离进程组的孙进程未在有界等待内完成；输出={child_output!r}",
            )
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

    @unittest.skipUnless(sys.platform == "darwin", "需 macOS Seatbelt 实测")
    def test_seatbelt_localhost随机端口规则地址范围诊断(self) -> None:
        """仅作诊断：核验 localhost:<port> 规则，不放开产品网络。"""

        local_address = _macos_non_loopback_ipv4()
        sandbox_exec = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
        if not Path(sandbox_exec).is_file():
            self.skipTest("sandbox-exec 不可用")

        canary_payload = b"icode-seatbelt-probe"
        probe_code = (
            "import sys\n"
            "sock = None\n"
            "stage = 'socket-import'\n"
            "try:\n"
            "    import socket\n"
            "    print('probe:stage=socket-imported', flush=True)\n"
            "    stage = 'socket-create'\n"
            "    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    print('probe:stage=socket-created', flush=True)\n"
            "    stage = 'socket-timeout'\n"
            "    sock.settimeout(1.5)\n"
            "    print('probe:stage=timeout-set', flush=True)\n"
            "    stage = 'connect'\n"
            "    print('probe:stage=connect', flush=True)\n"
            "    sock.connect((sys.argv[1], int(sys.argv[2])))\n"
            "    if sys.argv[3] == 'send':\n"
            "        stage = 'send'\n"
            "        print('probe:stage=send', flush=True)\n"
            f"        sock.sendall({canary_payload!r})\n"
            "    print('probe:connected', flush=True)\n"
            "except OSError as exc:\n"
            "    print('probe:errno=' + str(exc.errno) + '@' + stage, flush=True)\n"
            "finally:\n"
            "    if sock is not None: sock.close()\n"
        )

        def run_probe(
            profile: str,
            address: str,
            port: int,
            *,
            stage: str,
            send: bool = False,
        ) -> str:
            result = subprocess.run(
                [sandbox_exec, "-p", profile, sys.executable, "-c", probe_code,
                 address, str(port), "send" if send else "no-send"],
                cwd=workspace, capture_output=True, text=True, timeout=6, check=False,
            )
            matches = re.findall(
                r"(?m)^probe:(connected|errno=\d+@(?:socket-import|socket-create|socket-timeout|connect|send))$",
                result.stdout,
            )
            child_stages = re.findall(
                r"(?m)^probe:stage=(socket-imported|socket-created|timeout-set|connect|send)$",
                result.stdout,
            )
            if result.returncode != 0 or len(matches) != 1:
                print(
                    "::error::macos-seatbelt-port-boundary "
                    f"stage={stage} subprocess_exit={result.returncode} "
                    f"marker_count={len(matches)} "
                    f"child_stages={'+'.join(child_stages) or 'none'} "
                    f"stderr_tags={_seatbelt_stderr_tags(result.stderr)}",
                    flush=True,
                )
                self.fail("Seatbelt probe did not return one safe result marker")
            marker = matches[0]
            print(
                "::notice::macos-seatbelt-port-boundary "
                f"stage={stage} probe_result={marker} "
                f"child_stages={'+'.join(child_stages) or 'none'}",
                flush=True,
            )
            return marker

        def assert_classification(stage: str, result: str, expected: str) -> None:
            actual = classify(result)
            if actual != expected:
                print(
                    "::error::macos-seatbelt-port-boundary "
                    f"stage={stage} expected={expected} observed={actual}",
                    flush=True,
                )
            self.assertEqual(actual, expected, result)

        def assert_profile_startup(
            profile: str, *, stage: str, command: list[str], marker: str | None,
        ) -> None:
            result = subprocess.run(
                [sandbox_exec, "-p", profile, *command],
                cwd=workspace, capture_output=True, text=True, timeout=6, check=False,
            )
            markers = (
                re.findall(r"(?m)^probe:profile-started$", result.stdout)
                if marker else []
            )
            if result.returncode != 0 or (marker is not None and len(markers) != 1):
                print(
                    "::error::macos-seatbelt-port-boundary "
                    f"stage={stage} subprocess_exit={result.returncode} "
                    f"marker_count={len(markers)} "
                    f"stderr_tags={_seatbelt_stderr_tags(result.stderr)}",
                    flush=True,
                )
                self.fail("Seatbelt startup control did not meet its bounded result")
            print(
                "::notice::macos-seatbelt-port-boundary "
                f"stage={stage} probe_result=started",
                flush=True,
            )

        def classify(result: str) -> str:
            if result == "connected":
                return "connected"
            errno_text, child_stage = result.removeprefix("errno=").split("@", 1)
            code = int(errno_text)
            if code in (errno.EPERM, errno.EACCES):
                return f"denied_{child_stage}"
            if code == errno.ECONNREFUSED:
                return f"allowed_no_listener_{child_stage}"
            return f"inconclusive_errno_{code}_{child_stage}"

        sandbox = MacSeatbeltSandbox(sandbox_exec=sandbox_exec)
        with temp_workspace() as workspace:
            base_profile = sandbox._profile(workspace, False)
            assert_profile_startup(
                base_profile, stage="base-executable", command=["/usr/bin/true"],
                marker=None,
            )
            assert_profile_startup(
                base_profile, stage="base-python-no-site",
                command=[sys.executable, "-S", "-c",
                         "print('probe:profile-started', flush=True)"],
                marker="probe:profile-started",
            )
            assert_profile_startup(
                base_profile, stage="base-python-site",
                command=[sys.executable, "-c",
                         "print('probe:profile-started', flush=True)"],
                marker="probe:profile-started",
            )
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as loopback_listener:
                loopback_listener.bind(("127.0.0.1", 0))
                loopback_listener.listen(2)
                loopback_port = loopback_listener.getsockname()[1]
                profile = base_profile + (
                    f'(allow network-outbound (remote ip "localhost:{loopback_port}"))'
                )
                assert_profile_startup(
                    profile, stage="port-rule-python-site",
                    command=[sys.executable, "-c",
                             "print('probe:profile-started', flush=True)"],
                    marker="probe:profile-started",
                )

                # Positive control: the exact localhost port rule reaches the loopback listener.
                loopback_result = run_probe(
                    profile, "127.0.0.1", loopback_port,
                    stage="loopback-allowed", send=True,
                )
                assert_classification("loopback-allowed", loopback_result, "connected")
                loopback_listener.settimeout(1)
                accepted, _ = loopback_listener.accept()
                with accepted:
                    self.assertEqual(accepted.recv(64), b"icode-seatbelt-probe")

                # Negative control: an otherwise live loopback listener on another port stays denied.
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as other_listener:
                    other_listener.bind(("127.0.0.1", 0))
                    other_listener.listen(1)
                    other_port = other_listener.getsockname()[1]
                    other_result = run_probe(
                        profile, "127.0.0.1", other_port,
                        stage="other-loopback-port",
                    )
                    other_class = classify(other_result)
                    assert_classification(
                        "other-loopback-port", other_result, "denied_connect",
                    )

                if local_address is None:
                    print(
                        "::warning::macos-seatbelt-port-boundary "
                        "same_host_address=unavailable"
                    )
                    self.skipTest("没有可绑定的宿主非 loopback IPv4 地址")

                # Keep a canary listener active on the host's assigned address
                # and the exact same port. This distinguishes Seatbelt denial
                # from ECONNREFUSED caused by a missing service without probing
                # any off-host address.
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as host_listener:
                    try:
                        host_listener.bind((local_address, loopback_port))
                        host_listener.listen(1)
                    except OSError as exc:
                        print(
                            "::warning::macos-seatbelt-port-boundary "
                            f"same_host_active_listener=unavailable errno={exc.errno}",
                            flush=True,
                        )
                        self.skipTest("无法在宿主非 loopback 地址绑定同一随机端口")

                    host_listener.settimeout(0.25)
                    host_result = run_probe(
                        profile, local_address, loopback_port,
                        stage="same-host-address-same-port-active-listener",
                        send=True,
                    )
                    host_class = classify(host_result)
                    listener_accepted = False
                    canary_received = False
                    try:
                        accepted, _ = host_listener.accept()
                    except socket.timeout:
                        pass
                    else:
                        listener_accepted = True
                        with accepted:
                            accepted.settimeout(0.5)
                            received = bytearray()
                            try:
                                while len(received) < len(canary_payload):
                                    chunk = accepted.recv(
                                        len(canary_payload) - len(received)
                                    )
                                    if not chunk:
                                        break
                                    received.extend(chunk)
                                canary_received = bytes(received) == canary_payload
                            except socket.timeout:
                                pass

                    # The native syscall result and the local listener must
                    # agree; otherwise report a broken/inconclusive probe.
                    if host_class == "connected":
                        self.assertTrue(
                            listener_accepted,
                            "connect reported success but the active local listener saw none",
                        )
                        self.assertTrue(
                            canary_received,
                            "connect reported success but the listener did not receive the canary",
                        )
                    elif host_class == "denied_connect":
                        self.assertFalse(
                            listener_accepted,
                            "connect was reported denied but the active local listener accepted it",
                        )
                    elif host_class == "denied_send":
                        host_class = (
                            "connected_but_send_denied"
                            if listener_accepted
                            else "inconclusive_send_denied_without_accept"
                        )

                    inconclusive = (
                        host_class.startswith("inconclusive_")
                        or host_class.startswith("allowed_no_listener_")
                        or host_class == "connected_but_send_denied"
                    )
                    level = "warning" if inconclusive else "notice"
                    print(
                        f"::{level}::macos-seatbelt-port-boundary "
                        f"loopback=connected other_loopback_port={other_class} "
                        f"same_host_active_listener={host_class} "
                        f"listener_accepted={'yes' if listener_accepted else 'no'} "
                        f"canary_received={'yes' if canary_received else 'no'} "
                        "external_network=not_probed",
                        flush=True,
                    )

                    # Test a numeric IPv4 loopback predicate separately. The
                    # localhost form above is known to reach the host address;
                    # this candidate must preserve loopback access while
                    # denying the active same-port host listener.
                    loopback_only_profile = base_profile + (
                        f'(allow network-outbound '
                        f'(remote ip "127.0.0.1:{loopback_port}"))'
                    )
                    numeric_startup = subprocess.run(
                        [
                            sandbox_exec, "-p", loopback_only_profile,
                            sys.executable, "-c",
                            "print('probe:profile-started', flush=True)",
                        ],
                        cwd=workspace, capture_output=True, text=True,
                        timeout=6, check=False,
                    )
                    numeric_startup_markers = re.findall(
                        r"(?m)^probe:profile-started$", numeric_startup.stdout,
                    )
                    numeric_startup_tags = _seatbelt_stderr_tags(
                        numeric_startup.stderr,
                    )
                    if numeric_startup.returncode != 0:
                        if "unsupported_host_predicate" in numeric_startup_tags.split("+"):
                            print(
                                "::warning::macos-seatbelt-port-boundary "
                                "numeric_ipv4_rule=unsupported_host_predicate "
                                "conformance_credit=none "
                                f"stderr_tags={numeric_startup_tags}",
                                flush=True,
                            )
                            return
                        print(
                            "::error::macos-seatbelt-port-boundary "
                            "numeric_ipv4_rule=startup_inconclusive "
                            f"subprocess_exit={numeric_startup.returncode} "
                            f"stderr_tags={numeric_startup_tags}",
                            flush=True,
                        )
                        self.fail("Numeric IPv4 profile startup failed inconclusively")
                    if len(numeric_startup_markers) != 1:
                        print(
                            "::error::macos-seatbelt-port-boundary "
                            "numeric_ipv4_rule=startup_marker_invalid "
                            f"marker_count={len(numeric_startup_markers)} "
                            f"stderr_tags={numeric_startup_tags}",
                            flush=True,
                        )
                        self.fail("Numeric IPv4 profile startup marker is invalid")
                    print(
                        "::notice::macos-seatbelt-port-boundary "
                        "numeric_ipv4_rule=profile_started",
                        flush=True,
                    )
                    strict_loopback_result = run_probe(
                        loopback_only_profile, "127.0.0.1", loopback_port,
                        stage="numeric-ipv4-loopback-allowed", send=True,
                    )
                    assert_classification(
                        "numeric-ipv4-loopback-allowed",
                        strict_loopback_result, "connected",
                    )
                    loopback_listener.settimeout(1)
                    accepted, _ = loopback_listener.accept()
                    with accepted:
                        self.assertEqual(accepted.recv(64), canary_payload)

                    host_listener.settimeout(0.25)
                    strict_host_result = run_probe(
                        loopback_only_profile, local_address, loopback_port,
                        stage="numeric-ipv4-rule-blocks-host-address", send=True,
                    )
                    assert_classification(
                        "numeric-ipv4-rule-blocks-host-address",
                        strict_host_result, "denied_connect",
                    )
                    with self.assertRaises(socket.timeout):
                        host_listener.accept()
                    print(
                        "::notice::macos-seatbelt-port-boundary "
                        "numeric_ipv4_loopback=connected "
                        "numeric_rule_same_host=denied_connect "
                        "same_host_listener_accepted=no canary_received=no "
                        "external_network=not_probed",
                        flush=True,
                    )

    @unittest.skipUnless(
        sys.platform == "linux" and shutil.which("bwrap"),
        "需 Linux Bubblewrap + Reviewer 联测",
    )
    def test_bwrap_只读Reviewer真实隐藏账本且阻断工作区内外写入(self) -> None:
        with temp_workspace() as temporary_root:
            workspace = temporary_root / "workspace"
            workspace.mkdir()
            source = workspace / "reviewed.py"
            source.write_text("source-original\n", encoding="utf-8")
            output_root = workspace / ".icode_output"
            ticket_dir = output_root / "ticket-1"
            out_dir = ticket_dir / "review"
            out_dir.mkdir(parents=True)
            ledger = ticket_dir / "ledger.json"
            ledger.write_text("private-ledger-marker\n", encoding="utf-8")
            alias = workspace / "ledger-alias"
            alias.symlink_to(ledger)
            outside_secret = temporary_root / "outside-secret.txt"
            outside_secret.write_text("outside-secret-marker\n", encoding="utf-8")

            code = (
                "from pathlib import Path\n"
                "source = Path('reviewed.py')\n"
                "assert source.read_text() == 'source-original\\n'\n"
                "for path in (Path('.icode_output/ticket-1/ledger.json'), Path('ledger-alias')):\n"
                "    try: path.read_text()\n"
                "    except OSError: pass\n"
                "    else: raise AssertionError(f'excluded content readable: {path}')\n"
                "for path in (source, Path('.icode_output/new.json')):\n"
                "    try: path.write_text('tampered')\n"
                "    except OSError: pass\n"
                "    else: raise AssertionError(f'writable: {path}')\n"
                f"outside = Path({str(outside_secret)!r})\n"
                "try: outside.read_text()\n"
                "except OSError: pass\n"
                "else: raise AssertionError('outside workspace was readable')\n"
                "print('bwrap-review-boundary-ok')\n"
            )
            ctx = ToolContext(
                root=workspace, sandbox=BubblewrapSandbox(), read_only_workspace=True,
                deny_read_roots=(output_root, out_dir),
            )
            try:
                ctx.pin_read_only_workspace()
                wrapped = ctx.wrap_command(
                    [str(Path(getattr(sys, "_base_executable", sys.executable)).resolve()),
                     "-c", code],
                )
                result = subprocess.run(
                    wrapped, cwd=wrapped.cwd, pass_fds=wrapped.pass_fds,
                    capture_output=True, text=True,
                    timeout=15, check=False,
                )
            finally:
                ctx.close()
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(result.stdout.strip(), "bwrap-review-boundary-ok")
            self.assertNotIn(
                "private-ledger-marker", result.stdout + result.stderr,
            )
            self.assertNotIn(
                "outside-secret-marker", result.stdout + result.stderr,
            )
            self.assertEqual(source.read_text(encoding="utf-8"), "source-original\n")
            self.assertEqual(ledger.read_text(encoding="utf-8"), "private-ledger-marker\n")
            self.assertEqual(
                outside_secret.read_text(encoding="utf-8"),
                "outside-secret-marker\n",
            )
            self.assertFalse((output_root / "new.json").exists())

    @unittest.skipUnless(sys.platform == "darwin", "需 macOS Seatbelt + Reviewer 联测")
    def test_seatbelt_只读Reviewer真实隐藏账本且阻断工作区内外写入(self) -> None:
        with temp_workspace() as temporary_root:
            workspace = temporary_root / "workspace"
            workspace.mkdir()
            source = workspace / "reviewed.py"
            source.write_text("source-original\n", encoding="utf-8")
            output_root = workspace / ".icode_output"
            ticket_dir = output_root / "ticket-1"
            out_dir = ticket_dir / "review"
            out_dir.mkdir(parents=True)
            ledger = ticket_dir / "ledger.json"
            ledger.write_text("private-ledger-marker\n", encoding="utf-8")
            alias = workspace / "ledger-alias"
            alias.symlink_to(ledger)
            outside_secret = temporary_root / "outside-secret.txt"
            outside_secret.write_text("outside-secret-marker\n", encoding="utf-8")

            code = (
                "from pathlib import Path\n"
                "source = Path('reviewed.py')\n"
                "assert source.read_text() == 'source-original\\n'\n"
                "for path in (Path('.icode_output/ticket-1/ledger.json'), Path('ledger-alias')):\n"
                "    try: path.read_text()\n"
                "    except OSError: pass\n"
                "    else: raise AssertionError(f'excluded content readable: {path}')\n"
                "for path in (source, Path('.icode_output/new.json')):\n"
                "    try: path.write_text('tampered')\n"
                "    except OSError: pass\n"
                "    else: raise AssertionError(f'writable: {path}')\n"
                f"outside = Path({str(outside_secret)!r})\n"
                "try: outside.read_text()\n"
                "except OSError: pass\n"
                "else: raise AssertionError('outside workspace was readable')\n"
                "print('seatbelt-review-boundary-ok')\n"
            )
            sandbox = MacSeatbeltSandbox(
                sandbox_exec="/usr/bin/sandbox-exec",
            )
            wrapped = sandbox.wrap_read_only_excluding(
                [str(Path(getattr(sys, "_base_executable", sys.executable)).resolve()),
                 "-c", code],
                workspace=workspace, deny_read_roots=(output_root, out_dir),
            )
            result = subprocess.run(
                wrapped, cwd=workspace, capture_output=True, text=True,
                timeout=8, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(result.stdout.strip(), "seatbelt-review-boundary-ok")
            self.assertNotIn("private-ledger-marker", result.stdout + result.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), "source-original\n")
            self.assertEqual(ledger.read_text(encoding="utf-8"), "private-ledger-marker\n")
            self.assertEqual(outside_secret.read_text(encoding="utf-8"), "outside-secret-marker\n")

    def test_容器_包装默认断网且只挂工作区(self) -> None:
        argv = ContainerSandbox(runtime="podman").wrap(["python", "-V"], workspace=Path("/tmp/ws"))
        self.assertEqual(argv[:3], ["podman", "run", "--rm"])
        self.assertIn("--network", argv)
        self.assertEqual(argv[argv.index("--network") + 1], "none")
        self.assertIn("-v", argv)

    def test_容器_Reviewer工作区挂载为只读(self) -> None:
        workspace = Path("/tmp/review-ws").resolve()
        argv = ContainerSandbox(runtime="podman").wrap_read_only(
            ["python", "-m", "unittest"], workspace=workspace,
        )
        self.assertEqual(argv[argv.index("-v") + 1], f"{workspace}:{workspace}:ro")
        self.assertEqual(argv[argv.index("--network") + 1], "none")

    def test_容器_Reviewer排除挂载按Docker和Podman合同只读遮蔽(self) -> None:
        with temp_workspace() as root:
            workspace = root / "review-workspace"
            workspace.mkdir()
            excluded = workspace / ".icode_output"
            (excluded / "ticket-1" / "review").mkdir(parents=True)

            cases = (
                (
                    "docker",
                    f"type=bind,src={workspace},dst={workspace},readonly,"
                    "bind-recursive=readonly,bind-propagation=rprivate",
                    f"{excluded}:ro,noexec,nosuid,nodev,size=1048576,mode=0555",
                ),
                (
                    "podman",
                    f"type=bind,src={workspace},dst={workspace},ro=true,"
                    "bind-nonrecursive,bind-propagation=rprivate",
                    f"{excluded}:ro,noexec,nosuid,nodev,size=1048576,"
                    "mode=0555,notmpcopyup",
                ),
            )
            with mock.patch("icode.isolation.sys.platform", "linux"):
                for runtime, expected_bind, expected_hidden in cases:
                    with self.subTest(runtime=runtime):
                        argv = ContainerSandbox(runtime=runtime).wrap_read_only_excluding(
                            ["python", "-c", "pass"],
                            workspace=workspace,
                            deny_read_roots=(excluded, excluded / "ticket-1" / "review"),
                        )
                        self.assertIn("--pull=never", argv)
                        self.assertEqual(argv[argv.index("--mount") + 1], expected_bind)
                        self.assertEqual(argv[argv.index("--tmpfs") + 1], expected_hidden)
                        self.assertEqual(argv[argv.index("--network") + 1], "none")
                        self.assertEqual(argv[-3:], ["python", "-c", "pass"])

    def test_容器_Reviewer排除路径拒绝注入分隔符及未知运行时(self) -> None:
        with temp_workspace() as root:
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".icode_output").mkdir()

            with mock.patch("icode.isolation.sys.platform", "linux"):
                with self.assertRaisesRegex(ValueError, "运行时"):
                    ContainerSandbox(runtime="unknown").wrap_read_only_excluding(
                        ["true"], workspace=workspace,
                        deny_read_roots=(workspace / ".icode_output",),
                    )

                comma_workspace = root / "workspace,comma"
                comma_workspace.mkdir()
                comma_excluded = comma_workspace / ".icode_output"
                comma_excluded.mkdir()
                with self.assertRaisesRegex(ValueError, "挂载路径"):
                    ContainerSandbox(runtime="docker").wrap_read_only_excluding(
                        ["true"], workspace=comma_workspace,
                        deny_read_roots=(comma_excluded,),
                    )

                colon_excluded = workspace / "private:ledger"
                colon_excluded.mkdir()
                with self.assertRaisesRegex(ValueError, "挂载路径"):
                    ContainerSandbox(runtime="podman").wrap_read_only_excluding(
                        ["true"], workspace=workspace,
                        deny_read_roots=(colon_excluded,),
                    )

            with mock.patch("icode.isolation.sys.platform", "darwin"):
                with self.assertRaisesRegex(ValueError, "Linux 宿主机"):
                    ContainerSandbox(runtime="docker").wrap_read_only_excluding(
                        ["true"], workspace=workspace,
                        deny_read_roots=(workspace / ".icode_output",),
                    )

    @unittest.skipUnless(
        os.environ.get("ICODE_RUN_CONTAINER_REVIEWER_PROBE") == "1",
        "原生容器 Reviewer 探针由必需 CI job 显式启用",
    )
    def test_容器_Reviewer原生只读与账本遮蔽边界(self) -> None:
        runtime = os.environ.get("ICODE_CONTAINER_REVIEWER_RUNTIME", "")
        if runtime not in {"docker", "podman"}:
            self.fail("原生容器探针必须显式选择 docker 或 podman")
        if not shutil.which(runtime):
            self.fail("原生容器探针要求所选运行时已安装")

        with temp_workspace() as temporary_root:
            workspace = temporary_root / "workspace"
            workspace.mkdir()
            source = workspace / "reviewed.py"
            source.write_text("source-original\n", encoding="utf-8")
            output_root = workspace / ".icode_output"
            ticket_dir = output_root / "ticket-1"
            out_dir = ticket_dir / "review"
            out_dir.mkdir(parents=True)
            ledger = ticket_dir / "ledger.json"
            ledger.write_text("private-ledger-marker\n", encoding="utf-8")
            (workspace / "ledger-alias").symlink_to(
                ".icode_output/ticket-1/ledger.json",
            )
            outside_secret = temporary_root / "outside-secret.txt"
            outside_secret.write_text("outside-secret-marker\n", encoding="utf-8")

            code = "\n".join((
                "from pathlib import Path",
                "source = Path('reviewed.py')",
                "assert source.read_text() == 'source-original\\n'",
                "for path in (Path('.icode_output/ticket-1/ledger.json'), Path('ledger-alias')):",
                "    try: path.read_text()",
                "    except OSError: pass",
                "    else: raise AssertionError('excluded content readable')",
                "for path in (source, Path('.icode_output/new.json')):",
                "    try: path.write_text('tampered')",
                "    except OSError: pass",
                "    else: raise AssertionError('reviewer write succeeded')",
                f"outside = Path({str(outside_secret)!r})",
                "try: outside.read_text()",
                "except OSError: pass",
                "else: raise AssertionError('outside workspace readable')",
                "print('container-review-boundary-ok')",
            ))
            ctx = ToolContext(
                root=workspace,
                sandbox=ContainerSandbox(runtime=runtime),
                read_only_workspace=True,
                deny_read_roots=(output_root, out_dir),
            )
            wrapped = ctx.wrap_command(["python", "-c", code])
            result = subprocess.run(
                wrapped, cwd=workspace, capture_output=True, text=True,
                timeout=45, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(result.stdout.strip(), "container-review-boundary-ok")
            self.assertNotIn("private-ledger-marker", result.stdout + result.stderr)
            self.assertNotIn("outside-secret-marker", result.stdout + result.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), "source-original\n")
            self.assertEqual(ledger.read_text(encoding="utf-8"), "private-ledger-marker\n")
            self.assertEqual(
                outside_secret.read_text(encoding="utf-8"),
                "outside-secret-marker\n",
            )
            self.assertFalse((output_root / "new.json").exists())


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

    def test_只读审查无真实只读沙箱时拒绝命令(self) -> None:
        ctx = ToolContext(root=self.ws, sandbox=NoIsolation(), read_only_workspace=True)
        with self.assertRaises(IsolationUnavailable):
            ctx.wrap_command(["python", "-m", "unittest"])

    def test_bwrap只读Reviewer保留工作区目录FD直到启动合同(self) -> None:
        ctx = ToolContext(
            root=self.ws, sandbox=BubblewrapSandbox(), read_only_workspace=True,
        )
        try:
            ctx.pin_read_only_workspace()
            prepared = ctx.wrap_command(["/usr/bin/true"])

            self.assertIn("--ro-bind-fd", prepared)
            self.assertEqual(prepared.pass_fds, (ctx.read_only_workspace_fd,))
            self.assertEqual(prepared.cwd, "/")
        finally:
            close = getattr(ctx, "close", None)
            if callable(close):
                close()

    def test_bwrap只读Reviewer未提前固定工作区时拒绝命令(self) -> None:
        ctx = ToolContext(
            root=self.ws, sandbox=BubblewrapSandbox(), read_only_workspace=True,
        )
        with self.assertRaises(IsolationUnavailable):
            ctx.wrap_command(["/usr/bin/true"])

    def test_Seatbelt工作流Reviewer命令绑定工单账本拒读根(self) -> None:
        output_root = self.ws / ".icode_output"
        out_dir = output_root / "ticket-1" / "review"
        out_dir.mkdir(parents=True)
        ctx = ToolContext(
            root=self.ws, sandbox=MacSeatbeltSandbox(sandbox_exec="/usr/bin/sandbox-exec"),
            read_only_workspace=True,
            deny_read_roots=(output_root, out_dir),
        )
        wrapped = ctx.wrap_command(["python", "-c", "print('review')"])
        profile = wrapped[wrapped.index("-p") + 1]
        quoted_output_root = str(output_root.resolve()).replace('"', '\\"')

        self.assertEqual(wrapped[0], "/usr/bin/sandbox-exec")
        self.assertIn(f'(require-not (subpath "{quoted_output_root}"))', profile)
        self.assertNotIn('(allow file-write* (subpath', profile)
        self.assertNotIn("(allow network*)", profile)

    def test_容器Reviewer命令走排除只读后端(self) -> None:
        output_root = self.ws / ".icode_output"
        (output_root / "ticket-1" / "review").mkdir(parents=True)
        ctx = ToolContext(
            root=self.ws,
            sandbox=ContainerSandbox(runtime="docker"),
            read_only_workspace=True,
            deny_read_roots=(output_root,),
        )

        if sys.platform != "linux":
            with self.assertRaises(IsolationUnavailable):
                ctx.wrap_command(["python", "-c", "print('review')"])
            return

        wrapped = ctx.wrap_command(["python", "-c", "print('review')"])

        self.assertEqual(wrapped[0:4], ["docker", "run", "--rm", "--pull=never"])
        self.assertEqual(wrapped[wrapped.index("--network") + 1], "none")
        self.assertIn("readonly", wrapped[wrapped.index("--mount") + 1])
        self.assertEqual(
            wrapped[wrapped.index("--tmpfs") + 1].split(":", 1)[0],
            str(output_root.resolve()),
        )

    def test_策略化Reviewer命令因缺少可证明的只读策略交集而拒绝(self) -> None:
        policy = SandboxPolicy(
            schema_version=1, run_id="review-policy", ticket_id="review-policy",
            step="review", workspace_root=self.ws,
            read_roots=(self.ws,), write_roots=(self.ws,),
            deny_read_roots=(), deny_write_roots=(),
            network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
            wall_timeout_seconds=10, output_limit_bytes=4096, protected_paths=(),
        )
        ctx = ToolContext(
            root=self.ws, sandbox=BubblewrapSandbox(), policy=policy,
            read_only_workspace=True,
        )
        with self.assertRaises(IsolationUnavailable):
            ctx.wrap_command(["python", "-m", "unittest"])

    def test_不支持排除目录的只读后端拒绝Reviewer命令(self) -> None:
        class _WouldExposeExcludedRoot:
            name = "test-read-only"
            is_real_isolation = True

            def __init__(self) -> None:
                self.called = False

            def wrap_read_only(self, argv, *, workspace, network=False):
                self.called = True
                return list(argv)

        sandbox = _WouldExposeExcludedRoot()
        ctx = ToolContext(
            root=self.ws, sandbox=sandbox, read_only_workspace=True,
            deny_read_roots=(self.ws / ".icode_output",),
        )
        with self.assertRaises(IsolationUnavailable):
            ctx.wrap_command(["cat", ".icode_output/private.txt"])
        self.assertFalse(sandbox.called)

    @unittest.skipUnless(os.name == "posix", "需要 POSIX 符号链接语义")
    def test_Reviewer命令对指向Python运行时的工单排除链接仍拒绝(self) -> None:
        class _WouldExposeExcludedRoot:
            name = "test-read-only"
            is_real_isolation = True

            def __init__(self) -> None:
                self.called = False

            def wrap_read_only(self, argv, *, workspace, network=False):
                self.called = True
                return list(argv)

        excluded = self.ws / ".icode_output"
        excluded.symlink_to(Path(sys.prefix).resolve(), target_is_directory=True)
        sandbox = _WouldExposeExcludedRoot()
        ctx = ToolContext(
            root=self.ws, sandbox=sandbox, read_only_workspace=True,
            deny_read_roots=(excluded,),
        )
        with self.assertRaisesRegex(IsolationUnavailable, "排除目录"):
            ctx.wrap_command(["cat", ".icode_output/should-not-read.txt"])
        self.assertFalse(sandbox.called)

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
