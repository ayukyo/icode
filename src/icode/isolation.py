"""隔离能力层（Phase 5）。

目的：把「门禁不可绕过」从**约定**变成**机制**——在能落地的平台上用真正的
内核/容器级隔离执行外部命令；落不了的平台**如实标注**，绝不宣称沙箱。

三条铁律（有测试锁住）：
1. **能力靠探测，不靠假设。** 每台机器上有什么后端由 `probe_capabilities()` 实测。
2. **没落地就不许宣称沙箱。** `is_real_isolation=False` 的实现，`describe()`
   必须明说"应用层限制，非沙箱"。
3. **默认更严格的一侧。** 无法确认时按"无隔离"处理，而不是假设有隔离。

当前各平台现状（R2.2 实施中）：
    Linux   → `bwrap` 需通过最小真实负向探测；随包 Landlock 助手仍在策略接入前
    macOS   → `sandbox-exec` 需通过最小真实负向探测
    容器    → `docker` / `podman` 可用则用容器
    Windows → **未实现内核级隔离**（Job Object 只限资源不限文件/网络；AppContainer
              需 Win32 组包，本运行时尚未做）→ 明确报告为「应用层限制」
"""

from __future__ import annotations

import ctypes
import errno
import http.server
import os
import select
import signal
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Protocol, Sequence, runtime_checkable

from .sandbox_policy import NetworkMode, SandboxPolicy

KIND_KERNEL = "kernel"
KIND_CONTAINER = "container"
KIND_NONE = "none"

# 各实现的能力声明用语，统一在此，避免各处口径漂移
BASELINE_CLAIM = "应用层限制，非内核级沙箱"
BASELINE_NOTE = "工作区限制 + 危险命令拦截由 guard 在应用层完成；模型若绕过运行时直接执行 shell，这些规则不构成保障"

# 进程执行/派生所需最小集合；信号与进程信息只针对同沙箱目标。
_MAC_PROCESS_RULES = (
    "(allow process-exec)",
    "(allow process-fork)",
    "(allow signal (target same-sandbox))",
    "(allow process-info* (target same-sandbox))",
)

_MACOS_SEATBELT_EXEC = "/usr/bin/sandbox-exec"


@dataclass(frozen=True)
class Capability:
    """一次探测结果。"""

    name: str
    available: bool
    kind: str
    detail: str

    @property
    def is_kernel_or_container(self) -> bool:
        return self.available and self.kind in (KIND_KERNEL, KIND_CONTAINER)


@dataclass(frozen=True)
class NativeProbeResult:
    """原生后端的实际启动和最小负向探测结果。"""

    ready: bool
    checks: dict[str, bool]
    detail: str


@dataclass(frozen=True)
class ProcessGroupProbeResult:
    """macOS 组级清理局部实测；不代表完整后代树回收或 R2 ready。"""

    executed: bool
    passed: bool
    checks: dict[str, bool]
    detail: str


@dataclass(frozen=True)
class MacProtectedPathProbeResult:
    """macOS 保护路径策略的独立实测；不代表生产策略合同已就绪。"""

    executed: bool
    passed: bool
    checks: dict[str, bool]
    detail: str


@dataclass(frozen=True)
class LinuxProtectedPathProbeResult:
    """Linux 分层工作区保护路径的真实实测；不代表完整 R2 就绪。"""

    executed: bool
    passed: bool
    checks: dict[str, bool]
    detail: str


@dataclass(frozen=True)
class LinuxProcessTreeCleanupProbeResult:
    """Linux PID namespace 宿主崩溃清理实测，不代表完整 R2 ready。"""

    executed: bool
    passed: bool
    checks: dict[str, bool]
    detail: str


@dataclass(frozen=True)
class MetadataReadRoot:
    """Trusted path plus creation-time identity for one read-only root."""

    path: Path
    device: int
    inode: int


@dataclass(frozen=True)
class ExecuteOnlyFile:
    """Trusted exact-file execute exception for a fixed internal payload."""

    path: Path
    device: int
    inode: int


_NATIVE_PROBE_CHECKS = (
    "workspace_write", "workspace_read", "outside_write_denied",
    "secret_read_denied", "child_inherits", "network_denied",
)


def probe_native_sandbox(sandbox: Sandbox) -> NativeProbeResult:
    """用真实子进程验证本机后端；任何启动或探测故障均不可当作保护。"""
    checks = dict.fromkeys(_NATIVE_PROBE_CHECKS, False)
    if os.name != "posix":
        return NativeProbeResult(False, checks, "原生 POSIX 探测不适用于当前平台")
    binaries = {name: shutil.which(name) for name in ("touch", "cat", "sh", "curl")}
    missing = [name for name, path in binaries.items() if path is None]
    if missing:
        return NativeProbeResult(False, checks, "探测工具缺失：" + ", ".join(missing))

    with tempfile.TemporaryDirectory(prefix="icode-native-probe-") as raw:
        diagnostics: list[str] = []
        parent = Path(raw).resolve()
        workspace = parent / "workspace"
        outside = parent / "outside"
        workspace.mkdir()
        outside.mkdir()
        (workspace / "marker").write_text("workspace", encoding="utf-8")
        (outside / "secret").write_text("probe-secret", encoding="utf-8")

        def run(argv: list[str]) -> subprocess.CompletedProcess[str] | None:
            try:
                wrapped = sandbox.wrap(argv, workspace=workspace)
                return subprocess.run(
                    wrapped, cwd=workspace, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=4, check=False,
                )
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return None

        def success(argv: list[str], *, label: str = "") -> bool:
            result = run(argv)
            if label and (result is None or result.returncode != 0):
                reason = "启动失败或超时" if result is None else (
                    f"exit={result.returncode} " + (result.stderr or result.stdout).strip()[:300]
                )
                diagnostics.append(f"{label}: {reason or '退出码非零'}")
            return result is not None and result.returncode == 0

        checks["workspace_write"] = success([binaries["touch"], str(workspace / "written")], label="workspace_write") and (workspace / "written").is_file()
        checks["workspace_read"] = success([binaries["cat"], str(workspace / "marker")], label="workspace_read")
        checks["outside_write_denied"] = not success([binaries["touch"], str(outside / "written")]) and not (outside / "written").exists()
        checks["secret_read_denied"] = not success([binaries["cat"], str(outside / "secret")])
        child_allowed = success([binaries["sh"], "-c", 'printf child > "$1"', "sh", str(workspace / "child")], label="child_allowed") and (workspace / "child").is_file()
        child_denied = not success([binaries["sh"], "-c", 'printf child > "$1"', "sh", str(outside / "child")]) and not (outside / "child").exists()
        checks["child_inherits"] = child_allowed and child_denied

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"probe-ok")

            def log_message(self, format: str, *args: object) -> None:
                pass

        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/"
            curl = [binaries["curl"], "--noproxy", "*", "--max-time", "2", "--silent", "--fail", url]
            control = subprocess.run(curl, capture_output=True, timeout=4, check=False)
            checks["network_denied"] = (
                control.returncode == 0
                and success([binaries["curl"], "--version"], label="curl_launch")
                and not success(curl)
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            if "server" in locals():
                server.shutdown()
                server.server_close()

    failed = [name for name, ok in checks.items() if not ok]
    return NativeProbeResult(
        not failed, checks,
        "通过最小负向探测" if not failed else "未通过：" + ", ".join(failed)
        + ("；诊断：" + " | ".join(diagnostics) if diagnostics else ""),
    )


def probe_linux_protected_paths(
    sandbox: LandlockSandbox,
) -> LinuxProtectedPathProbeResult:
    """在 Linux 分层 checkout 中实测 `.git` 元数据写入/移动被拒。

    ICODE 的 POSIX 自主工作区将可写代码目录与 checkout 根的 `.git`
    元数据分开。Landlock 只授权工作区子树，因此该测试使用同样的兄弟布局；
    它不声称可排除工作区内部的任意受保护子目录。
    """
    checks = {
        "workspace_write_allowed": False,
        "protected_write_denied": False,
        "protected_rename_denied": False,
    }
    if not sys.platform.startswith("linux"):
        return LinuxProtectedPathProbeResult(
            False, False, checks, "仅适用于 Linux Landlock",
        )
    if not isinstance(sandbox, LandlockSandbox) or sandbox.manifest is None:
        return LinuxProtectedPathProbeResult(
            False, False, checks, "随包 Landlock 助手或摘要清单不可用",
        )

    from .execution_broker import execute_policy_command

    stage = "setup"
    try:
        with tempfile.TemporaryDirectory(prefix="icode-linux-protected-probe-") as raw:
            checkout = Path(raw).resolve() / "checkout"
            workspace = checkout / "code"
            workspace.mkdir(parents=True)
            protected = checkout / ".git"
            protected.write_text("gitdir: protected-metadata\n", encoding="utf-8")
            protected_before = protected.read_text(encoding="utf-8")
            moved = checkout / "git-moved"
            allowed_file = workspace / "allowed"
            policy = SandboxPolicy(
                schema_version=1,
                run_id="linux-protected-path-probe",
                ticket_id="linux-protected-path-probe",
                step="code",
                workspace_root=workspace,
                read_roots=(workspace,),
                write_roots=(workspace,),
                deny_read_roots=(),
                deny_write_roots=(protected,),
                network_mode=NetworkMode.DENY,
                allowed_domains=(),
                process_limit=8,
                wall_timeout_seconds=5,
                output_limit_bytes=2048,
                protected_paths=(protected,),
            )

            def execute(argv: list[str]):
                wrapped = sandbox.wrap_policy(argv, policy=policy)
                return execute_policy_command(
                    wrapped, cwd=workspace, policy=policy, timeout=5,
                )

            stage = "workspace_write_allowed"
            allowed = execute([
                sys.executable, "-c",
                "from pathlib import Path; Path('allowed').write_text('ok')",
            ])
            checks["workspace_write_allowed"] = (
                allowed.exit_code == 0 and allowed.error is None
                and allowed.cleanup_ok and allowed_file.is_file()
                and allowed_file.read_text(encoding="utf-8") == "ok"
            )

            stage = "protected_write_denied"
            write = execute([
                sys.executable, "-c",
                "from pathlib import Path; import sys; "
                "Path(sys.argv[1]).write_text('changed')",
                str(protected),
            ])
            checks["protected_write_denied"] = (
                checks["workspace_write_allowed"]
                and write.exit_code not in (None, 0)
                and write.error is None and write.cleanup_ok
                and protected.read_text(encoding="utf-8") == protected_before
            )

            stage = "protected_rename_denied"
            rename = execute([
                sys.executable, "-c",
                "from pathlib import Path; import sys; "
                "Path(sys.argv[1]).rename(sys.argv[2])",
                str(protected), str(moved),
            ])
            checks["protected_rename_denied"] = (
                checks["workspace_write_allowed"]
                and rename.exit_code not in (None, 0)
                and rename.error is None and rename.cleanup_ok
                and protected.is_file() and not moved.exists()
                and protected.read_text(encoding="utf-8") == protected_before
            )
    except Exception:  # noqa: BLE001 - 原生探针异常必须 fail-closed。
        return LinuxProtectedPathProbeResult(
            True, False, checks, f"Linux 保护路径探针异常：{stage}",
        )

    failed = [name for name, passed in checks.items() if not passed]
    return LinuxProtectedPathProbeResult(
        True, not failed, checks,
        "分层 checkout 保护路径探测通过" if not failed
        else "Linux 保护路径未通过：" + ", ".join(failed),
    )


def _open_verified_descendant_pidfd(namespace_pid: int, unique_path: Path) -> int:
    """按 NSpid、唯一命令参数和 start-time 锚定后代，不向数值 PID 发信号。"""
    token = os.fsencode(str(unique_path))
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            status = (process / "status").read_text(encoding="ascii")
            nspid_line = next(
                line for line in status.splitlines() if line.startswith("NSpid:")
            )
            if int(nspid_line.split()[-1]) != namespace_pid:
                continue
            if token not in (process / "cmdline").read_bytes():
                continue
            before = (process / "stat").read_text(encoding="ascii").rsplit(")", 1)[1]
            start_time = before.split()[19]  # /proc/<pid>/stat field 22
            if hasattr(os, "pidfd_open"):
                pidfd = os.pidfd_open(int(process.name))
            else:
                # pidfd_open 使用的系统调用号在本项目 Linux x64/ARM64 上均为 434。
                pidfd = ctypes.CDLL(None, use_errno=True).syscall(
                    434, int(process.name), 0,
                )
                if pidfd < 0:
                    raise OSError(ctypes.get_errno(), "pidfd_open failed")
            try:
                after = (process / "stat").read_text(encoding="ascii").rsplit(")", 1)[1]
                if (
                    after.split()[19] == start_time
                    and token in (process / "cmdline").read_bytes()
                ):
                    return pidfd
            except (OSError, ValueError, IndexError):
                pass
            os.close(pidfd)
        except (OSError, StopIteration, ValueError, IndexError):
            continue
    raise RuntimeError("descendant_identity_not_found")


def probe_linux_process_tree_cleanup(
    sandbox: LandlockSandbox,
) -> LinuxProcessTreeCleanupProbeResult:
    """实测宿主被 SIGKILL 后，主动 setsid 的 PID namespace 后代也会退出。

    这是 CI/显式诊断探针，不由 ``icode doctor`` 自动运行。它核对传入 helper
    的摘要，使用 pidfd 观察由 NSpid 与唯一命令参数确认的测试后代，并验证
    延迟写入哨兵没有出现；不会向扫描到的普通数值 PID 发送信号。
    """
    checks = {
        "descendant_started": False,
        "descendant_detached": False,
        "descendant_alive_before_host_kill": False,
        "host_killed": False,
        "descendant_exited": False,
        "no_delayed_write": False,
    }
    if not sys.platform.startswith("linux"):
        return LinuxProcessTreeCleanupProbeResult(
            False, False, checks, "仅适用于 Linux PID namespace",
        )
    if not isinstance(sandbox, LandlockSandbox) or sandbox.manifest is None:
        return LinuxProcessTreeCleanupProbeResult(
            False, False, checks, "Landlock helper 或完整性清单不可用",
        )

    from .native_helper import verify_native_helper

    helper = Path(sandbox.helper)
    manifest = Path(sandbox.manifest)
    try:
        helper_verified = verify_native_helper(helper, manifest)
    except Exception:  # noqa: BLE001 - 摘要校验异常一律失败关闭。
        helper_verified = False
    if not helper_verified:
        return LinuxProcessTreeCleanupProbeResult(
            False, False, checks, "Landlock helper 完整性校验失败",
        )
    system_python = Path("/usr/bin/python3")
    if not system_python.is_file():
        return LinuxProcessTreeCleanupProbeResult(
            False, False, checks, "系统 Python 3 不可用",
        )

    stage = "setup"
    pidfd: int | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="icode-linux-tree-cleanup-") as raw:
            root = Path(raw).resolve()
            workspace = root / "workspace"
            workspace.mkdir()
            started = workspace / "descendant-started"
            survived = workspace / "descendant-survived"
            grandchild = (
                "import os, time\nfrom pathlib import Path\n"
                "try:\n    os.setsid()\n    detached = os.getsid(0) == os.getpid()\n"
                "except PermissionError:\n    detached = False\n"
                f"Path({str(started)!r}).write_text(('detached:' if detached else "
                "'denied:') + str(os.getpid()))\n"
                "time.sleep(1.2)\n"
                f"Path({str(survived)!r}).write_text('escaped')\n"
            )
            child = (
                "import subprocess, sys, time\n"
                f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                "time.sleep(3)\n"
            )
            host = (
                "import os, subprocess, time\n"
                f"subprocess.Popen([{str(helper)!r}, '--workspace', {str(workspace)!r}, "
                f"'--parent-pid', str(os.getpid()), '--', {str(system_python)!r}, '-c', "
                f"{child!r}], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)\n"
                "time.sleep(10)\n"
            )
            parent: subprocess.Popen[bytes] | None = None
            try:
                parent = subprocess.Popen(
                    [sys.executable, "-c", host],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                stage = "descendant_started"
                for _ in range(400):
                    if started.exists() or parent.poll() is not None:
                        break
                    time.sleep(0.01)
                if not started.is_file():
                    return LinuxProcessTreeCleanupProbeResult(
                        True, False, checks, "descendant_did_not_start",
                    )
                checks["descendant_started"] = True
                marker = started.read_text(encoding="ascii")
                if not marker.startswith("detached:"):
                    return LinuxProcessTreeCleanupProbeResult(
                        True, False, checks, "descendant_did_not_detach",
                    )
                namespace_pid_text = marker.partition(":")[2]
                if not namespace_pid_text.isdecimal():
                    return LinuxProcessTreeCleanupProbeResult(
                        True, False, checks, "descendant_namespace_pid_invalid",
                    )
                checks["descendant_detached"] = True

                stage = "descendant_identity"
                pidfd = _open_verified_descendant_pidfd(
                    int(namespace_pid_text), survived,
                )
                if parent.poll() is not None:
                    return LinuxProcessTreeCleanupProbeResult(
                        True, False, checks, "host_parent_exited_before_kill",
                    )
                exit_events = select.poll()
                exit_events.register(pidfd, select.POLLIN)
                if exit_events.poll(0):
                    return LinuxProcessTreeCleanupProbeResult(
                        True, False, checks, "descendant_exited_before_host_kill",
                    )
                checks["descendant_alive_before_host_kill"] = True

                stage = "host_kill"
                os.kill(parent.pid, signal.SIGKILL)
                parent.wait(timeout=3)
                checks["host_killed"] = parent.returncode == -signal.SIGKILL
                if not checks["host_killed"]:
                    return LinuxProcessTreeCleanupProbeResult(
                        True, False, checks, "host_parent_not_killed_by_sigkill",
                    )

                stage = "descendant_exit"
                checks["descendant_exited"] = bool(exit_events.poll(2000))
                if not checks["descendant_exited"]:
                    return LinuxProcessTreeCleanupProbeResult(
                        True, False, checks, "detached_descendant_still_running",
                    )

                stage = "delayed_write"
                time.sleep(1.45)
                checks["no_delayed_write"] = not survived.exists()
                if not checks["no_delayed_write"]:
                    return LinuxProcessTreeCleanupProbeResult(
                        True, False, checks,
                        "detached_descendant_wrote_after_host_death",
                    )
            finally:
                if parent is not None and parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=3)
    except (OSError, RuntimeError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return LinuxProcessTreeCleanupProbeResult(
            True, False, checks, f"Linux process-tree cleanup probe failed: {stage}",
        )
    finally:
        if pidfd is not None:
            os.close(pidfd)

    failed = [name for name, passed in checks.items() if not passed]
    return LinuxProcessTreeCleanupProbeResult(
        True, not failed, checks,
        "宿主强杀后主动脱组后代已退出且无延迟写入"
        if not failed else "Linux process-tree cleanup probe failed: " + ", ".join(failed),
    )


def probe_macos_process_group_cleanup(
    sandbox: MacSeatbeltSandbox,
) -> ProcessGroupProbeResult:
    """在 Seatbelt 策略下实测正常退出和超时后的同组孙进程清理。"""
    checks = {"normal_exit": False, "timeout": False}
    if sys.platform != "darwin":
        return ProcessGroupProbeResult(False, False, {}, "仅适用于 macOS")
    if shutil.which(sandbox.sandbox_exec) is None:
        return ProcessGroupProbeResult(False, False, checks, "sandbox-exec 不可用")

    from .execution_broker import execute_policy_command

    stage = "setup"
    diagnostics: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="icode-mac-cleanup-probe-") as raw:
            workspace = Path(raw).resolve()
            policy = SandboxPolicy(
                schema_version=1, run_id="mac-cleanup-probe",
                ticket_id="mac-cleanup-probe", step="code",
                workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(),
                deny_write_roots=(), network_mode=NetworkMode.DENY,
                allowed_domains=(), process_limit=8,
                wall_timeout_seconds=5, output_limit_bytes=1024,
                protected_paths=(),
            )
            for mode, timeout, child_delay in (
                ("normal_exit", 5, 1.3),
                ("timeout", 2, 3.0),
            ):
                stage = mode
                started = workspace / f"{mode}-started"
                residue = workspace / f"{mode}-residue"
                output = workspace / f"{mode}-child-output"
                child_code = (
                    "import time\nfrom pathlib import Path\n"
                    f"Path({str(started)!r}).write_text('ready')\n"
                    f"time.sleep({child_delay!r})\n"
                    f"Path({str(residue)!r}).write_text('late')\n"
                )
                parent_code = (
                    "import subprocess, sys, time\nfrom pathlib import Path\n"
                    f"with open({str(output)!r}, 'wb') as sink:\n"
                    f"    subprocess.Popen([sys.executable, '-c', {child_code!r}], "
                    "stdout=sink, stderr=subprocess.STDOUT)\n"
                    f"for _ in range(200):\n    if Path({str(started)!r}).exists(): break\n"
                    "    time.sleep(0.01)\n"
                    "else: raise RuntimeError('child did not start')\n"
                    "print('started', flush=True)\n"
                    + ("time.sleep(8)\n" if mode == "timeout" else "")
                )
                result = execute_policy_command(
                    sandbox.experimental_wrap_policy(
                        [sys.executable, "-c", parent_code], policy=policy,
                    ),
                    cwd=workspace, policy=policy, timeout=timeout,
                )
                if started.is_file():
                    time.sleep(child_delay + 0.2)
                started_ok = started.is_file()
                residue_present = residue.exists()
                checks[mode] = (
                    started_ok and not residue_present
                    and result.cleanup_ok
                    and (result.error == "timeout" if mode == "timeout"
                         else result.error is None and result.exit_code == 0)
                )
                if not checks[mode]:
                    diagnostics.append(
                        f"{mode}: started={int(started_ok)}, "
                        f"residue={int(residue_present)}, exit={result.exit_code}, "
                        f"error={result.error or 'none'}, cleanup={int(result.cleanup_ok)}"
                    )
    except Exception:  # noqa: BLE001 - 自检意外失败必须按未通过处理
        return ProcessGroupProbeResult(True, False, checks, f"组级清理探测异常：{stage}")
    failed = [mode for mode, passed in checks.items() if not passed]
    return ProcessGroupProbeResult(
        True, not failed, checks,
        "同组清理局部探测通过；不覆盖主动脱组后代" if not failed
        else "同组清理未通过：" + " | ".join(diagnostics),
    )


def probe_macos_protected_paths(
    sandbox: MacSeatbeltSandbox,
) -> MacProtectedPathProbeResult:
    """用统一命令 broker 实测 Seatbelt 对策略保护路径的写入/重命名拒绝。

    本探针仅验证当前实验性策略 profile 的这项能力。Seatbelt 仍没有生产
    ``wrap_policy``，因此此结果不能把 ``policy_contract_ready`` 提升为真。
    """
    checks = {
        "workspace_write_allowed": False,
        "protected_write_denied": False,
        "protected_rename_denied": False,
    }
    if sys.platform != "darwin":
        return MacProtectedPathProbeResult(
            False, False, checks, "仅适用于 macOS Seatbelt",
        )
    if shutil.which(sandbox.sandbox_exec) is None:
        return MacProtectedPathProbeResult(
            False, False, checks, "sandbox-exec 不可用",
        )

    from .execution_broker import execute_policy_command

    stage = "setup"
    try:
        with tempfile.TemporaryDirectory(prefix="icode-mac-protected-probe-") as raw:
            workspace = (Path(raw) / "workspace").resolve()
            workspace.mkdir()
            protected = workspace / ".git"
            protected.mkdir()
            protected_file = protected / "probe"
            protected_file.write_text("protected", encoding="utf-8")
            allowed_file = workspace / "allowed"
            policy = SandboxPolicy(
                schema_version=1, run_id="mac-protected-path-probe",
                ticket_id="mac-protected-path-probe", step="code",
                workspace_root=workspace, read_roots=(workspace,),
                write_roots=(workspace,), deny_read_roots=(),
                deny_write_roots=(protected,), network_mode=NetworkMode.DENY,
                allowed_domains=(), process_limit=8, wall_timeout_seconds=5,
                output_limit_bytes=2048, protected_paths=(protected,),
            )

            def execute(code: str):
                return execute_policy_command(
                    sandbox.experimental_wrap_policy(
                        [sys.executable, "-c", code], policy=policy,
                    ),
                    cwd=workspace, policy=policy, timeout=5,
                )

            stage = "workspace_write_allowed"
            allowed = execute(
                "from pathlib import Path; Path('allowed').write_text('ok')"
            )
            checks["workspace_write_allowed"] = (
                allowed.exit_code == 0 and allowed.error is None
                and allowed.cleanup_ok
                and allowed_file.is_file()
                and allowed_file.read_text(encoding="utf-8") == "ok"
            )

            stage = "protected_write_denied"
            write = execute(
                "from pathlib import Path; Path('.git/probe').write_text('changed')"
            )
            checks["protected_write_denied"] = (
                checks["workspace_write_allowed"]
                and write.exit_code not in (None, 0)
                and write.error is None and write.cleanup_ok
                and protected_file.read_text(encoding="utf-8") == "protected"
            )

            stage = "protected_rename_denied"
            rename = execute(
                "from pathlib import Path; Path('.git').rename('git-moved')"
            )
            checks["protected_rename_denied"] = (
                checks["workspace_write_allowed"]
                and rename.exit_code not in (None, 0)
                and rename.error is None and rename.cleanup_ok
                and protected.is_dir() and not (workspace / "git-moved").exists()
                and protected_file.read_text(encoding="utf-8") == "protected"
            )
    except Exception:  # noqa: BLE001 - 原生探针异常必须 fail-closed。
        return MacProtectedPathProbeResult(
            True, False, checks, f"保护路径探测异常：{stage}",
        )

    failed = [name for name, passed in checks.items() if not passed]
    return MacProtectedPathProbeResult(
        True, not failed, checks,
        "保护路径策略探测通过" if not failed
        else "保护路径策略未通过：" + ", ".join(failed),
    )


def probe_capabilities() -> tuple[Capability, ...]:
    """Linux/macOS 原生后端实际探测；旧容器/WSL 仍仅作候选发现。"""
    probes: list[Capability] = []
    for name, kind, detail in (
        ("bwrap", KIND_KERNEL, "bubblewrap：可 unshare 文件系统与网络命名空间"),
        ("sandbox-exec", KIND_KERNEL, "macOS Seatbelt：按 profile 限制文件与网络"),
        ("wsl", KIND_KERNEL, "WSL：Linux 内核隔离（文件系统 + 可 unshare 网络）"),
        ("docker", KIND_CONTAINER, "容器：可限制挂载与网络"),
        ("podman", KIND_CONTAINER, "容器：可限制挂载与网络"),
    ):
        found = shutil.which(name)
        verified = None
        try:
            if found and name == "bwrap" and sys.platform.startswith("linux"):
                verified = probe_native_sandbox(BubblewrapSandbox(bwrap=found))
            elif found and name == "sandbox-exec" and sys.platform == "darwin":
                verified = probe_native_sandbox(MacSeatbeltSandbox(sandbox_exec=found))
        except Exception:  # noqa: BLE001 - 能力探测异常必须安全地视为不可用
            verified = NativeProbeResult(False, dict.fromkeys(_NATIVE_PROBE_CHECKS, False), "探测异常")
        platform_mismatch = found and name in ("bwrap", "sandbox-exec") and verified is None
        probes.append(Capability(
            name=name,
            available=verified.ready if verified is not None else bool(found and not platform_mismatch),
            kind=kind,
            detail=f"{detail}；可执行文件：{found or '未找到'}"
                   + (f"；真实探测：{verified.detail}" if verified is not None else "")
                   + ("；当前平台不适用" if platform_mismatch else ""),
        ))
    return tuple(probes)


@runtime_checkable
class Sandbox(Protocol):
    name: str

    @property
    def is_real_isolation(self) -> bool:
        """是否具备内核/容器级强制隔离。**不得虚报。**"""
        ...

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        """把命令包进沙箱执行，返回实际要执行的 argv。"""
        ...

    def describe(self) -> dict:
        ...


@dataclass(frozen=True)
class PinnedWorkspaceRoot:
    """A trusted directory handle and its stable mount destination."""

    path: Path
    fd: int


class PreparedCommand(list[str]):
    """Command metadata required to preserve a sandbox's launch contract."""

    def __init__(self, argv: Sequence[str], *, pass_fds: Sequence[int], cwd: str):
        super().__init__(argv)
        self.pass_fds = tuple(pass_fds)
        self.cwd = cwd


def _validated_read_only_exclusions(
    workspace: Path, deny_read_roots: Sequence[Path], *,
    workspace_fd: int | None = None,
) -> tuple[Path, ...]:
    """Validate existing exclusions, using the pinned root when one is supplied."""
    workspace_input = Path(workspace)
    workspace_lexical = Path(os.path.abspath(workspace_input))
    if workspace_fd is None:
        workspace_resolved = workspace_input.resolve(strict=True)
        if not workspace_resolved.is_dir():
            raise ValueError("Reviewer 工作区必须是已存在的目录")
    else:
        if not stat.S_ISDIR(os.fstat(workspace_fd).st_mode):
            raise ValueError("Reviewer 工作区句柄必须指向目录")
        # The root handle, not a fresh path lookup, anchors all component opens.
        workspace_resolved = workspace_lexical

    validated: list[Path] = []
    for denied in deny_read_roots:
        denied_input = Path(denied)
        candidate = (
            denied_input if denied_input.is_absolute()
            else workspace_lexical / denied_input
        )
        lexical = Path(os.path.abspath(candidate))
        try:
            relative = lexical.relative_to(workspace_lexical)
        except ValueError as exc:
            raise ValueError("Reviewer 排除目录必须严格位于工作区内") from exc
        if not relative.parts:
            raise ValueError("Reviewer 排除目录不能等于工作区根目录")

        if workspace_fd is None:
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(workspace_resolved):
                raise ValueError("Reviewer 排除目录解析后逃出工作区")

            # Reject every symlink component, including aliases that resolve back
            # inside the workspace; otherwise the mount target could be ambiguous.
            current = workspace_resolved
            for component in relative.parts:
                current = current / component
                info = os.lstat(current)
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError("Reviewer 排除目录不能包含符号链接")
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError("Reviewer 排除路径必须是已存在的目录")
            if current.resolve(strict=True) != resolved:
                raise ValueError("Reviewer 排除目录的规范路径不匹配")
            validated.append(current)
            continue

        # Walk from the pinned root without following symlinks. A path-based
        # resolve here would silently switch the exclusion check to a replacement
        # workspace if its original pathname had been swapped.
        flags = (
            getattr(os, "O_PATH", os.O_RDONLY)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        current_fd = os.dup(workspace_fd)
        try:
            for component in relative.parts:
                next_fd = os.open(component, flags, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
                if not stat.S_ISDIR(os.fstat(current_fd).st_mode):
                    raise ValueError("Reviewer 排除路径必须是已存在的目录")
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ValueError("Reviewer 排除目录不能包含符号链接") from exc
            raise
        finally:
            os.close(current_fd)
        validated.append(workspace_lexical.joinpath(*relative.parts))

    # An ancestor carve-out already hides every nested exclusion. Keeping only
    # the shallowest roots also avoids overlaying below a hidden mount.
    minimal: list[Path] = []
    for path in sorted(set(validated), key=lambda item: (len(item.parts), str(item))):
        if not any(path.is_relative_to(parent) for parent in minimal):
            minimal.append(path)
    return tuple(minimal)


@dataclass
class NoIsolation:
    """基线实现：不做任何强制隔离（当前 Windows 的实际情况）。"""

    name: str = "none"
    reason: str = "本机未探测到可用的内核/容器级隔离后端"

    @property
    def is_real_isolation(self) -> bool:
        return False

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        return list(argv)

    def describe(self) -> dict:
        return {
            "backend": self.name,
            "is_real_isolation": False,
            "claim": BASELINE_CLAIM,
            "reason": self.reason,
            "note": BASELINE_NOTE,
            "enforced": [],
            "not_enforced": ["文件系统", "网络", "资源"],
        }


@dataclass
class LandlockSandbox:
    """R2.2 开发期 Linux 原生助手；已打包，但完整策略绑定前不参与自动选择。"""

    helper: str
    name: str = "landlock"
    manifest: str | None = None

    @property
    def is_real_isolation(self) -> bool:
        return True

    @property
    def policy_contract_ready(self) -> bool:
        """实验后端尚未落实进程数等完整策略，不能启动自动工单。"""
        return False

    @classmethod
    def from_bundle(cls) -> LandlockSandbox | None:
        """只从摘要已核对的随包文件构造策略候选，仍不自动启用。"""
        from .native_helper import bundled_linux_helper

        helper = bundled_linux_helper()
        if helper is None:
            return None
        return cls(helper=str(helper), manifest=str(helper.parent / "icode-landlock.sha256"))

    @staticmethod
    def _validated_runtime_roots(prefixes: Sequence[Path]) -> tuple[Path, ...]:
        """仅授权 Python 安装前缀，不把用户主目录当作运行时。"""
        home = Path.home().resolve()
        roots = tuple(sorted({path.resolve() for path in prefixes}, key=str))
        broad = {Path("/"), Path("/tmp"), Path("/var"), Path("/home")}
        for root in roots:
            if (
                root in broad or home.is_relative_to(root)
                or not root.is_dir()
            ):
                raise RuntimeError("Python 运行时前缀过宽或不可用")
        return roots

    def _runtime_read_roots(self) -> tuple[Path, ...]:
        return self._validated_runtime_roots(
            (Path(sys.prefix), Path(sys.base_prefix))
        )

    def _checked_policy_workspace(self, policy: SandboxPolicy) -> Path:
        """仅核对当前助手能表达的文件/网络子集；不是完整策略绑定。"""
        workspace = policy.workspace_root

        def intersects(left: Path, right: Path) -> bool:
            return left.is_relative_to(right) or right.is_relative_to(left)

        if policy.network_mode is not NetworkMode.DENY or policy.allowed_domains:
            raise ValueError("Landlock helper 尚不支持网络临时授权")
        if policy.read_roots != (workspace,) or policy.write_roots != (workspace,):
            raise ValueError("Landlock helper 仅支持单一代码读写根")
        if any(
            intersects(path, workspace)
            for path in (*policy.deny_read_roots, *policy.deny_write_roots)
        ):
            raise ValueError("Landlock 无法从可写根中排除受保护子路径")

        # 助手有 Python/动态链接器所需的固定系统只读白名单，以及 /dev/null
        # 这一写入例外。拒绝规则若与这些路径重叠，不能宣称已完整执行策略。
        runtime_read = (
            "/usr", "/bin", "/lib", "/lib64", "/sbin",
            "/etc/ld.so.cache", "/etc/passwd", "/etc/nsswitch.conf",
            "/dev/urandom", "/dev/null",
        )
        runtime_paths = tuple(map(Path, runtime_read)) + self._runtime_read_roots()
        if any(
            intersects(denied, allowed)
            for denied in policy.deny_read_roots
            for allowed in runtime_paths
        ):
            raise ValueError("Landlock 系统运行时读取白名单与拒读路径冲突")
        if any(
            intersects(denied, Path("/dev/null"))
            for denied in policy.deny_write_roots
        ):
            raise ValueError("Landlock /dev/null 写入例外与拒写路径冲突")
        return workspace

    def _validated_metadata_roots(
        self, workspace: Path, roots: Sequence[MetadataReadRoot],
    ) -> tuple[MetadataReadRoot, ...]:
        """Validate narrow trusted read-only roots for an internal status broker.

        These roots are intentionally not taken from ``SandboxPolicy`` or model
        arguments. They grant read access only, never execute/write access.
        """
        if isinstance(roots, (str, bytes)) or not isinstance(roots, Sequence):
            raise ValueError("Git metadata roots must be trusted identity claims")
        workspace = workspace.resolve(strict=True)
        home = Path.home().resolve()
        broad_roots = {Path("/"), Path("/tmp"), Path("/var"), Path("/home")}
        executable_roots = tuple(
            Path(path) for path in ("/usr", "/bin", "/lib", "/lib64", "/sbin")
        )
        executable_roots += self._runtime_read_roots()

        def intersects(left: Path, right: Path) -> bool:
            return left.is_relative_to(right) or right.is_relative_to(left)

        validated: list[MetadataReadRoot] = []
        for claim in roots:
            if (
                not isinstance(claim, MetadataReadRoot)
                or not isinstance(claim.path, Path)
                or type(claim.device) is not int
                or type(claim.inode) is not int
                or claim.device < 0
                or claim.inode < 0
            ):
                raise ValueError("Git metadata root identity claim is invalid")
            try:
                root = claim.path.resolve(strict=True)
                status = os.lstat(claim.path)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise ValueError("Git metadata root cannot be resolved") from exc
            if (
                root != claim.path
                or stat.S_ISLNK(status.st_mode)
                or (status.st_dev, status.st_ino) != (claim.device, claim.inode)
                or not (stat.S_ISREG(status.st_mode) or stat.S_ISDIR(status.st_mode))
            ):
                raise ValueError("Git metadata root must be a file or directory")
            if (
                root in broad_roots
                or home.is_relative_to(root)
                or root.is_relative_to(workspace)
                or workspace.is_relative_to(root)
            ):
                raise ValueError("Git metadata root is broad or overlaps the task workspace")
            if any(intersects(root, allowed) for allowed in executable_roots):
                raise ValueError("Git metadata root overlaps an executable runtime allowlist")
            if not any(existing.path == root for existing in validated):
                validated.append(claim)
        return tuple(sorted(validated, key=lambda claim: str(claim.path)))

    def _execute_only_file_claim(
        self, executable: Path, *, allowed_roots: Sequence[str],
    ) -> ExecuteOnlyFile:
        if not isinstance(executable, Path) or not executable.is_absolute():
            raise ValueError("execute-only file must be an absolute trusted path")
        try:
            path = executable.resolve(strict=True)
            status = os.lstat(path)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ValueError("execute-only file cannot be resolved") from exc
        if (
            path != executable
            or not stat.S_ISREG(status.st_mode)
            or not os.access(path, os.X_OK)
            or not any(path.is_relative_to(Path(root)) for root in allowed_roots)
        ):
            raise ValueError("execute-only file must match a fixed system executable")
        return ExecuteOnlyFile(path, status.st_dev, status.st_ino)

    @staticmethod
    def _elf_interpreter(executable: Path) -> Path | None:
        """Return a validated ELF PT_INTERP path without running the binary."""
        with executable.open("rb") as stream:
            header = stream.read(64)
            if len(header) < 52 or header[:4] != b"\x7fELF":
                raise ValueError("execute-only payload is not a supported ELF file")
            elf_class, elf_data = header[4], header[5]
            if elf_class not in (1, 2) or elf_data not in (1, 2):
                raise ValueError("execute-only ELF header is unsupported")
            endian = "<" if elf_data == 1 else ">"
            if elf_class == 2:
                if len(header) < 64:
                    raise ValueError("execute-only ELF header is truncated")
                phoff = struct.unpack_from(endian + "Q", header, 32)[0]
                phentsize, phnum = struct.unpack_from(endian + "HH", header, 54)
                ph_format = endian + "IIQQQQQQ"
                p_offset_index, p_filesz_index = 2, 5
            else:
                phoff = struct.unpack_from(endian + "I", header, 28)[0]
                phentsize, phnum = struct.unpack_from(endian + "HH", header, 42)
                ph_format = endian + "IIIIIIII"
                p_offset_index, p_filesz_index = 1, 4
            minimum_entry_size = struct.calcsize(ph_format)
            if phentsize < minimum_entry_size or phnum > 1024:
                raise ValueError("execute-only ELF program-header table is invalid")
            executable_size = os.fstat(stream.fileno()).st_size
            for index in range(phnum):
                entry_offset = phoff + index * phentsize
                if entry_offset + minimum_entry_size > executable_size:
                    raise ValueError("execute-only ELF program-header table is truncated")
                stream.seek(entry_offset)
                entry_bytes = stream.read(minimum_entry_size)
                if len(entry_bytes) != minimum_entry_size:
                    raise ValueError("execute-only ELF program-header table is truncated")
                entry = struct.unpack(ph_format, entry_bytes)
                if entry[0] != 3:  # PT_INTERP
                    continue
                interpreter_offset = entry[p_offset_index]
                interpreter_size = entry[p_filesz_index]
                if (
                    interpreter_size < 2
                    or interpreter_size > 4096
                    or interpreter_offset + interpreter_size > executable_size
                ):
                    raise ValueError("execute-only ELF interpreter is invalid")
                stream.seek(interpreter_offset)
                raw_path = stream.read(interpreter_size)
                if (
                    len(raw_path) != interpreter_size
                    or raw_path[-1:] != b"\0"
                    or b"\0" in raw_path[:-1]
                ):
                    raise ValueError("execute-only ELF interpreter is malformed")
                try:
                    interpreter = Path(raw_path[:-1].decode("ascii"))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise ValueError("execute-only ELF interpreter is malformed") from exc
                if not interpreter.is_absolute():
                    raise ValueError("execute-only ELF interpreter must be absolute")
                return interpreter
            return None

    def _validated_execute_only_files(
        self, executable: Path, command: Sequence[str],
    ) -> tuple[ExecuteOnlyFile, ...]:
        """Bind payload and dynamic loader to exact system-file identities."""
        payload = self._execute_only_file_claim(
            executable, allowed_roots=("/usr/bin", "/bin"),
        )
        if not command or command[0] != str(payload.path):
            raise ValueError("execute-only payload must match the fixed command")
        claims = [payload]
        interpreter = self._elf_interpreter(payload.path)
        if interpreter is not None:
            loader = interpreter.resolve(strict=True)
            loader_claim = self._execute_only_file_claim(
                loader, allowed_roots=("/lib", "/lib64", "/usr/lib", "/usr/lib64"),
            )
            if loader_claim.path not in {claim.path for claim in claims}:
                claims.append(loader_claim)
        return tuple(claims)

    def prepare_policy(self, policy: SandboxPolicy) -> None:
        """模型调用前的静态阻断；仅覆盖当前助手已实现的策略子集。"""
        self._checked_policy_workspace(policy)
        from .native_helper import verify_native_helper

        if self.manifest is None or not verify_native_helper(
            Path(self.helper), Path(self.manifest)
        ):
            raise RuntimeError("Landlock helper integrity check failed")

    def wrap_policy(
        self, argv: Sequence[str], *, policy: SandboxPolicy, network: bool = False,
    ) -> list[str]:
        return self._wrap_policy_with_metadata_roots(
            argv, policy=policy, metadata_roots=(), network=network,
        )

    def wrap_policy_with_violation_receipt(
        self, argv: Sequence[str], *, policy: SandboxPolicy,
        control_socket: socket.socket,
    ) -> list[str]:
        """Wrap one deny-only command with a private native receipt channel."""
        if (
            not sys.platform.startswith("linux")
            or not isinstance(policy, SandboxPolicy)
            or type(control_socket) is not socket.socket
            or control_socket.fileno() < 3
            or control_socket.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN)
            != socket.AF_UNIX
            or control_socket.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            != socket.SOCK_SEQPACKET
            or policy.network_mode is not NetworkMode.DENY
            or policy.allowed_domains
        ):
            raise ValueError("native violation receipt channel is unavailable")
        return self._wrap_policy_with_metadata_roots(
            argv,
            policy=policy,
            metadata_roots=(),
            violation_control_descriptor=control_socket.fileno(),
        )

    def _wrap_policy_with_metadata_roots(
        self, argv: Sequence[str], *, policy: SandboxPolicy,
        metadata_roots: Sequence[MetadataReadRoot], network: bool = False,
        workspace_read_only: bool = False, execute_only: Path | None = None,
        network_loopback_only: bool = False,
        proxy_control_descriptor: int | None = None,
        violation_control_descriptor: int | None = None,
    ) -> list[str]:
        """Wrap a trusted internal read-only query with extra file/directory roots.

        Git-status callers provide server-derived roots after rechecking the
        worktree identity; model-supplied paths are never accepted here.
        """
        if network:
            raise ValueError("Landlock helper does not support network grants")
        if (
            type(network_loopback_only) is not bool
            or (network_loopback_only and (
                proxy_control_descriptor is None
                or type(proxy_control_descriptor) is not int
                or proxy_control_descriptor < 3
            ))
            or (not network_loopback_only and proxy_control_descriptor is not None)
            or (violation_control_descriptor is not None and (
                type(violation_control_descriptor) is not int
                or violation_control_descriptor < 3
                or network_loopback_only
                or proxy_control_descriptor is not None
            ))
        ):
            raise ValueError("invalid trusted proxy handoff configuration")
        if workspace_read_only:
            self._validate_non_executable_workspace(policy.workspace_root)
        self.prepare_policy(policy)
        validated_roots = self._validated_metadata_roots(
            policy.workspace_root, metadata_roots,
        )
        execute_claims = (
            self._validated_execute_only_files(execute_only, argv)
            if execute_only is not None else None
        )
        return self._wrap_with_metadata_roots(
            argv, workspace=policy.workspace_root, metadata_roots=validated_roots,
            workspace_read_only=workspace_read_only, execute_only=execute_claims,
            network_loopback_only=network_loopback_only,
            proxy_control_descriptor=proxy_control_descriptor,
            violation_control_descriptor=violation_control_descriptor,
        )

    def wrap_leased_connect_candidate(
        self, argv: Sequence[str], *, policy: SandboxPolicy,
        sender_control: socket.socket,
    ) -> list[str]:
        """Build a non-product Linux loopback-proxy candidate command.

        The caller must supply a live host-owned lease scope and retain control
        of the resulting helper process. This method is deliberately separate
        from ``wrap_policy`` and is not exposed through ToolContext or Agent
        tools; ordinary policy execution remains network-deny.
        """
        if (
            not sys.platform.startswith("linux")
            or not isinstance(policy, SandboxPolicy)
            or type(sender_control) is not socket.socket
            or sender_control.fileno() < 3
            or sender_control.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN)
            != socket.AF_UNIX
            or sender_control.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            != socket.SOCK_SEQPACKET
            or policy.network_mode is not NetworkMode.DENY
            or policy.allowed_domains
        ):
            raise ValueError("leased CONNECT candidate is unavailable")
        return self._wrap_policy_with_metadata_roots(
            argv,
            policy=policy,
            metadata_roots=(),
            network_loopback_only=True,
            proxy_control_descriptor=sender_control.fileno(),
        )

    def _validate_non_executable_workspace(self, workspace: Path) -> Path:
        """Reject read-only roots whose paths overlap a separately executable grant.

        Landlock rules at one layer add rights; a read-only child rule cannot
        revoke EXECUTE already granted by an overlapping system/runtime root.
        """
        workspace = Path(workspace).resolve(strict=True)
        # Some supported distributions (notably arm64) omit optional roots
        # such as /lib64; the native helper also treats those as absent.
        executable_roots = tuple(
            Path(path).resolve(strict=False)
            for path in ("/usr", "/bin", "/lib", "/lib64", "/sbin")
        ) + self._runtime_read_roots()

        def intersects(left: Path, right: Path) -> bool:
            return left.is_relative_to(right) or right.is_relative_to(left)

        if any(intersects(workspace, root) for root in executable_roots):
            raise ValueError(
                "read-only workspace overlaps an executable system/runtime root"
            )
        return workspace

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        if network:
            raise RuntimeError("Landlock helper does not support network grants")
        return self._wrap_with_metadata_roots(
            argv, workspace=workspace, metadata_roots=(), workspace_read_only=False,
        )

    def wrap_read_only(
        self, argv: Sequence[str], *, workspace: Path, network: bool = False,
    ) -> list[str]:
        """Wrap Reviewer commands with an OS-enforced read-only workspace."""
        if network:
            raise RuntimeError("Landlock helper does not support network grants")
        workspace = self._validate_non_executable_workspace(workspace)
        helper = Path(self.helper)
        if not helper.is_file():
            raise RuntimeError("Landlock helper is unavailable")
        if self.manifest is not None:
            from .native_helper import verify_native_helper

            if not verify_native_helper(helper, Path(self.manifest)):
                raise RuntimeError("Landlock helper integrity check failed")
        return self._wrap_with_metadata_roots(
            argv, workspace=workspace, metadata_roots=(), workspace_read_only=True,
        )

    def _wrap_with_metadata_roots(
        self, argv: Sequence[str], *, workspace: Path,
        metadata_roots: Sequence[MetadataReadRoot], workspace_read_only: bool,
        execute_only: Sequence[ExecuteOnlyFile] | None = None,
        network_loopback_only: bool = False,
        proxy_control_descriptor: int | None = None,
        violation_control_descriptor: int | None = None,
    ) -> list[str]:
        helper = Path(self.helper)
        if not helper.is_file():
            raise RuntimeError("Landlock helper is unavailable")
        if self.manifest is not None:
            from .native_helper import verify_native_helper

            if not verify_native_helper(helper, Path(self.manifest)):
                raise RuntimeError("Landlock helper integrity check failed")
        wrapped = [
            str(helper), "--workspace", str(Path(workspace).resolve()),
            "--parent-pid", str(os.getpid()),
        ]
        if workspace_read_only:
            wrapped.append("--workspace-read-only")
        if network_loopback_only:
            wrapped.extend(("--network-loopback-only", "--proxy-control-fd",
                            str(proxy_control_descriptor)))
        if violation_control_descriptor is not None:
            wrapped.extend(("--violation-control-fd", str(violation_control_descriptor)))
        for root in self._runtime_read_roots():
            wrapped.extend(("--runtime-read", str(root)))
        for root in metadata_roots:
            wrapped.extend((
                "--metadata-read",
                str(root.path), str(root.device), str(root.inode),
            ))
        if execute_only is not None:
            for executable in execute_only:
                wrapped.extend((
                    "--execute-only",
                    str(executable.path), str(executable.device), str(executable.inode),
                ))
        return [*wrapped, "--", *argv]

    def describe(self) -> dict:
        return {
            "backend": self.name,
            "is_real_isolation": True,
            "claim": "开发期 Landlock/seccomp 原生边界，尚未达到 R2 完整合同",
            "enforced": ["工作区读写", "默认断网", "子进程继承"],
            "not_enforced": ["受保护子路径", "R2 完整策略映射", "进程树清理", "进程数上限"],
        }


@dataclass
class BubblewrapSandbox:
    """Linux：bwrap 绑定工作区 + 可选断网。"""

    bwrap: str = "bwrap"
    name: str = "bwrap"

    @property
    def is_real_isolation(self) -> bool:
        return True

    def pin_read_only_workspace(self, workspace: Path) -> PinnedWorkspaceRoot:
        """Pin a Reviewer root before model-controlled commands can run."""
        path = Path(workspace).resolve(strict=True)
        flags = (
            getattr(os, "O_PATH", os.O_RDONLY)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        fd = os.open(path, flags)
        try:
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise ValueError("Reviewer 工作区必须是目录")
        except BaseException:
            os.close(fd)
            raise
        return PinnedWorkspaceRoot(path=path, fd=fd)

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        return self._wrap(argv, workspace=workspace, network=network, read_only=False)

    def wrap_read_only(
        self, argv: Sequence[str], *, workspace: Path, workspace_fd: int,
        network: bool = False,
    ) -> PreparedCommand:
        """Wrap Reviewer commands with a read-only workspace bind."""
        return self._wrap(
            argv, workspace=workspace, workspace_fd=workspace_fd,
            network=network, read_only=True,
        )

    def wrap_read_only_excluding(
        self, argv: Sequence[str], *, workspace: Path, workspace_fd: int,
        network: bool = False,
        deny_read_roots: Sequence[Path],
    ) -> PreparedCommand:
        """Wrap a read-only Reviewer and hide validated workspace subdirectories.

        Each excluded directory is replaced by an empty tmpfs and remounted
        read-only inside the same mount namespace as the workspace bind.
        """
        exclusions = _validated_read_only_exclusions(
            workspace, deny_read_roots, workspace_fd=workspace_fd,
        )
        return self._wrap(
            argv, workspace=workspace, workspace_fd=workspace_fd,
            network=network, read_only=True,
            deny_read_roots=exclusions,
        )

    def _wrap(
        self, argv: Sequence[str], *, workspace: Path, network: bool, read_only: bool,
        workspace_fd: int | None = None,
        deny_read_roots: Sequence[Path] = (),
    ) -> list[str]:
        if deny_read_roots and not read_only:
            raise ValueError("排除只读目录只能用于 Reviewer 沙箱")
        if read_only:
            if workspace_fd is None or not stat.S_ISDIR(os.fstat(workspace_fd).st_mode):
                raise ValueError("Reviewer 只读绑定要求已固定的工作区目录句柄")
            ws = str(Path(os.path.abspath(workspace)))
        else:
            ws = str(Path(workspace).resolve())
        out = [
            self.bwrap,
            "--die-with-parent",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/lib", "/lib",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
        ]
        if read_only:
            out += ["--ro-bind-fd", str(workspace_fd), ws]
        else:
            out += ["--bind", ws, ws]
        for excluded in deny_read_roots:
            excluded_path = str(excluded)
            out += ["--tmpfs", excluded_path, "--remount-ro", excluded_path]
        if Path("/lib64").exists():
            out += ["--ro-bind", "/lib64", "/lib64"]
        # venv 中的 base interpreter 可能位于 /usr 之外（如 uv runtime）。
        # 只挂载该 Python 安装前缀为只读，不开放它的上级 home 目录。
        python_prefix = Path(sys.base_prefix).resolve()
        standard_roots = tuple(Path(path) for path in ("/usr", "/bin", "/lib", "/lib64"))
        if python_prefix.is_dir() and not any(
            python_prefix == root or root in python_prefix.parents
            for root in standard_roots
        ):
            out += ["--ro-bind", str(python_prefix), str(python_prefix)]
        out += ["--chdir", ws]
        if not network:
            out.append("--unshare-net")
        out += ["--", *argv]
        if read_only:
            return PreparedCommand(out, pass_fds=(workspace_fd,), cwd="/")
        return out

    def describe(self) -> dict:
        return {
            "backend": self.name,
            "is_real_isolation": True,
            "claim": "内核级隔离（bubblewrap 命名空间）",
            "enforced": [
                "文件系统（除工作区外只读；非系统 Python 运行时前缀只读）",
                "网络（默认断网）", "PID/IPC/UTS",
            ],
            "not_enforced": ["同用户下的内核漏洞逃逸"],
        }


@dataclass
class MacSeatbeltSandbox:
    """macOS：sandbox-exec + 最小 profile。"""

    sandbox_exec: str = "sandbox-exec"
    name: str = "sandbox-exec"

    @property
    def is_real_isolation(self) -> bool:
        return True

    @property
    def policy_contract_ready(self) -> bool:
        """组级清理探测不代表完整 R2 策略已可用于自动工单。"""
        return False

    def _profile(
        self, workspace: Path, network: bool, *, read_only: bool = False,
        deny_read_roots: Sequence[Path] = (),
    ) -> str:
        ws = str(Path(workspace).resolve())
        if any(ord(char) < 32 or ord(char) == 127 for char in ws):
            raise ValueError("Seatbelt workspace path contains control characters")
        escaped_ws = ws.replace("\\", "\\\\").replace('"', '\\"')
        python_prefix = str(Path(sys.base_prefix).resolve())
        if any(ord(char) < 32 or ord(char) == 127 for char in python_prefix):
            raise ValueError("Seatbelt Python runtime path contains control characters")
        escaped_python_prefix = python_prefix.replace("\\", "\\\\").replace('"', '\\"')

        if deny_read_roots and not read_only:
            raise ValueError("Seatbelt read exclusions require a read-only profile")
        exclusions = (
            _validated_read_only_exclusions(workspace, deny_read_roots)
            if deny_read_roots else ()
        )
        independently_allowed = tuple(
            Path(path).resolve()
            for path in (
                "/usr", "/System", "/Library", "/bin", "/sbin",
                "/private/etc/ssl", python_prefix,
            )
        )
        for excluded in exclusions:
            if any(
                excluded.is_relative_to(root) or root.is_relative_to(excluded)
                for root in independently_allowed
            ):
                raise ValueError(
                    "Reviewer 排除目录与 Seatbelt 系统/Python 读取授权重叠"
                )

        workspace_read = f'(allow file-read* (subpath "{escaped_ws}"))'
        if exclusions:
            filters: list[str] = []
            for excluded in exclusions:
                value = str(excluded)
                if any(ord(char) < 32 or ord(char) == 127 for char in value):
                    raise ValueError("Seatbelt Reviewer exclusion path contains control characters")
                quoted = value.replace("\\", "\\\\").replace('"', '\\"')
                filters.extend((
                    f'(require-not (literal "{quoted}"))',
                    f'(require-not (subpath "{quoted}"))',
                ))
            workspace_read = (
                f'(allow file-read* (require-all (subpath "{escaped_ws}") '
                + " ".join(filters) + "))"
            )

        net = "(allow network*)" if network else ""
        workspace_write = "" if read_only else f'(allow file-write* (subpath "{escaped_ws}"))'
        return (
            "(version 1)"
            "(deny default)"
            + "".join(_MAC_PROCESS_RULES)
            + "(allow sysctl-read)"
            f'(allow file-read-metadata file-test-existence (path-ancestors "{escaped_ws}"))'
            '(allow file-read* file-test-existence (literal "/"))'
            f"{workspace_read}"
            f"{workspace_write}"
            "(allow file-read* (subpath \"/usr\") (subpath \"/System\") (subpath \"/Library\")"
            ' (subpath \"/bin\") (subpath \"/sbin\")'
            ' (subpath \"/private/etc/ssl\"))'
            f'(allow file-read* (subpath "{escaped_python_prefix}"))'
            f"{net}"
        )

    def _policy_profile(self, policy: SandboxPolicy) -> str:
        """编译 R2 策略以供负向试验；完整验收前不开放 ``wrap_policy``。"""
        if policy.network_mode is not NetworkMode.DENY:
            raise ValueError("Seatbelt policy profile does not support network grants")

        def quoted(path: Path) -> str:
            value = str(path)
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError("Seatbelt policy path contains control characters")
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

        def access_rule(action: str, roots: Sequence[Path], denied: Sequence[Path]) -> str:
            filters = []
            for root in roots:
                parts = [f"(subpath {quoted(root)})"]
                for blocked in denied:
                    if blocked.is_relative_to(root):
                        parts.extend((
                            f"(require-not (literal {quoted(blocked)}))",
                            f"(require-not (subpath {quoted(blocked)}))",
                        ))
                filters.append("(require-all " + " ".join(parts) + ")")
            return f"(allow {action} " + " ".join(filters) + ")" if filters else ""

        system_roots = tuple(
            Path(path) for path in ("/usr", "/System", "/Library", "/bin", "/sbin", "/private/etc/ssl")
        )
        toolchain_roots = tuple(sorted(
            {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}, key=str,
        ))
        read_roots = tuple(dict.fromkeys((*policy.read_roots, *system_roots, *toolchain_roots)))
        rules = [
            "(version 1)",
            "(deny default)",
            *_MAC_PROCESS_RULES,
            "(allow sysctl-read)",
            f"(allow file-read-metadata file-test-existence (path-ancestors {quoted(policy.workspace_root)}))",
            '(allow file-read* file-test-existence (literal "/"))',
            access_rule("file-read*", read_roots, policy.deny_read_roots),
            access_rule("file-write*", policy.write_roots, policy.deny_write_roots),
        ]
        # 可写目录本身不可被移动；受保护条目若位于其子目录，祖先也不可移动。
        anchors = set(policy.write_roots)
        for blocked in policy.deny_write_roots:
            for parent in blocked.parents:
                if any(parent.is_relative_to(root) for root in policy.write_roots):
                    anchors.add(parent)
        rules.extend(
            f"(deny file-write-unlink (literal {quoted(path)}))"
            for path in sorted(anchors, key=str)
        )
        return "\n".join(filter(None, rules)) + "\n"

    def experimental_wrap_policy(
        self, argv: Sequence[str], *, policy: SandboxPolicy, network: bool = False,
    ) -> list[str]:
        """仅供真实联测；无 ``wrap_policy``，生产自动链仍保持阻断。"""
        if network:
            raise ValueError("Seatbelt experimental policy does not support network grants")
        if not argv:
            raise ValueError("empty command")
        return [self.sandbox_exec, "-p", self._policy_profile(policy), *argv]

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        return [self.sandbox_exec, "-p", self._profile(workspace, network), *argv]

    def _reviewer_sandbox_exec(self) -> str:
        """Use the fixed OS Seatbelt executable for read-only reviews on macOS."""
        if sys.platform != "darwin":
            return self.sandbox_exec
        if self.sandbox_exec not in ("sandbox-exec", _MACOS_SEATBELT_EXEC):
            raise ValueError("macOS Reviewer requires the trusted system sandbox-exec")
        return _MACOS_SEATBELT_EXEC

    def wrap_read_only(
        self, argv: Sequence[str], *, workspace: Path, network: bool = False,
    ) -> list[str]:
        """Wrap Reviewer commands with no workspace file-write grant."""
        return [
            self._reviewer_sandbox_exec(), "-p",
            self._profile(workspace, network, read_only=True), *argv,
        ]

    def wrap_read_only_excluding(
        self, argv: Sequence[str], *, workspace: Path, network: bool = False,
        deny_read_roots: Sequence[Path],
    ) -> list[str]:
        """Wrap Reviewer commands read-only, excluding ticket-ledger subtrees."""
        if not argv:
            raise ValueError("empty command")
        sandbox_exec = self._reviewer_sandbox_exec()
        profile = self._profile(
            workspace, network, read_only=True, deny_read_roots=deny_read_roots,
        )
        return [sandbox_exec, "-p", profile, *argv]

    def describe(self) -> dict:
        return {
            "backend": self.name,
            "is_real_isolation": True,
            "claim": "内核级隔离（macOS Seatbelt profile）",
            "enforced": ["文件系统（白名单外拒绝）", "网络（默认拒绝）"],
            "not_enforced": ["R2 完整策略映射", "进程树清理", "进程数上限", "同用户下的内核漏洞逃逸"],
        }


@dataclass
class WslSandbox:
    """Windows 上的真隔离路径：把命令放进 WSL（Linux 内核）。

    前提：本机装了 WSL 且可用。**注意**：部分受限环境会拦截 `wsl.exe`；
    那时 `wrap` 出来的命令会启动失败，运行时会如实报错（不会静默降级成无隔离执行）。
    """

    wsl: str = "wsl"
    distro: str = ""
    name: str = "wsl"

    @property
    def is_real_isolation(self) -> bool:
        return True

    def to_wsl_path(self, path: Path) -> str:
        """`C:\\a\\b` → `/mnt/c/a/b`（WSL 默认自动挂载格式）。"""
        raw = str(path)
        windows = PureWindowsPath(raw)
        if windows.drive:
            drive = windows.drive.rstrip(":").lower()
            rest = "/".join(windows.parts[1:])
            return f"/mnt/{drive}/{rest}".rstrip("/")
        return str(Path(path).resolve())

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        cwd = self.to_wsl_path(workspace)
        prefix = [self.wsl]
        if self.distro:
            prefix += ["-d", self.distro]
        prefix += ["--cd", cwd, "--"]
        if not network:
            # unshare 需要 root（WSL 默认用户有 sudo 但不一定免密）；
            # 因此这里只声明意图，失败会在运行时如实暴露。
            return prefix + ["unshare", "-n", "--", *argv]
        return prefix + list(argv)

    def describe(self) -> dict:
        return {
            "backend": self.name + (f":{self.distro}" if self.distro else ""),
            "is_real_isolation": True,
            "claim": "内核级隔离（WSL：Linux 命名空间）",
            "enforced": ["文件系统（Linux 视图，仅 /mnt/<盘> 映射）", "网络（依赖 unshare -n 是否可用）"],
            "not_enforced": ["WSL 不可用或被安全策略拦截时无法执行"],
        }


@dataclass
class ContainerSandbox:
    """容器：挂载工作区，默认断网。"""

    runtime: str = "docker"
    image: str = "python:3.13-slim"
    name: str = "container"

    @property
    def is_real_isolation(self) -> bool:
        return True

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        ws = str(Path(workspace).resolve())
        out = [
            self.runtime, "run", "--rm",
            "-v", f"{ws}:{ws}", "-w", ws,
        ]
        if not network:
            out += ["--network", "none"]
        out += [self.image, *argv]
        return out

    def wrap_read_only(
        self, argv: Sequence[str], *, workspace: Path, network: bool = False,
    ) -> list[str]:
        """Mount the reviewed workspace read-only inside the disposable container."""
        ws = str(Path(workspace).resolve())
        out = [
            self.runtime, "run", "--rm",
            "-v", f"{ws}:{ws}:ro", "-w", ws,
        ]
        if not network:
            out += ["--network", "none"]
        out += [self.image, *argv]
        return out

    def describe(self) -> dict:
        return {
            "backend": f"{self.name}:{self.runtime}",
            "is_real_isolation": True,
            "claim": "容器级隔离",
            "enforced": ["文件系统（仅挂载工作区）", "网络（默认 --network none）"],
            "not_enforced": ["容器逃逸类内核漏洞"],
        }


# ---------------------------------------------------------------------------
# Windows 资源限制（**部分强制**，不是隔离）
# ---------------------------------------------------------------------------


PARTIAL_CLAIM = "部分强制：仅资源上限，不含文件系统与网络"


@dataclass
class WindowsJobLimits:
    """Windows Job Object：限制**资源**，不限制文件系统与网络。

    这是**部分强制**，不是隔离，因此 `is_real_isolation` 恒为 False，
    描述里也明确区分「已强制」与「未强制」。

    实现要点（Windows 8+ 支持嵌套 Job，因此可以给当前进程再挂一个）：
    创建 Job → 设置限额 → 把当前进程加入 Job。子进程默认继承 Job，
    于是整棵进程树都受限额约束，并在 Job 关闭时被回收（防失控进程残留）。

    只能用 ctypes 标准库实现，不引入第三方依赖。
    """

    active_process_limit: int = 64
    memory_mb: int = 4096
    name: str = "windows-job-object"

    is_real_isolation = False  # 类属性，明确表态

    def available(self) -> bool:
        import sys

        return sys.platform == "win32"

    def apply(self) -> tuple[bool, str]:
        """把当前进程加入受限额的 Job。返回 (是否成功, 说明)。**失败不抛异常。**"""
        if not self.available():
            return False, "非 Windows 平台，Job Object 不可用"
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:  # pragma: no cover
            return False, "ctypes 不可用"

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_ulonglong),
                        ("WriteOperationCount", ctypes.c_ulonglong),
                        ("OtherOperationCount", ctypes.c_ulonglong),
                        ("ReadTransferCount", ctypes.c_ulonglong),
                        ("WriteTransferCount", ctypes.c_ulonglong),
                        ("OtherTransferCount", ctypes.c_ulonglong)]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return False, f"CreateJobObject 失败（err={ctypes.get_last_error()}）"

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | 0x0008        # JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | 0x0100        # JOB_OBJECT_LIMIT_JOB_MEMORY
        )
        info.BasicLimitInformation.ActiveProcessLimit = int(self.active_process_limit)
        info.JobMemoryLimit = int(self.memory_mb) * 1024 * 1024

        ok = kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            return False, f"SetInformationJobObject 失败（err={ctypes.get_last_error()}）"

        assigned = kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
        if not assigned:
            return False, (
                f"AssignProcessToJobObject 失败（err={ctypes.get_last_error()}）；"
                "当前进程可能已在不允许嵌套的 Job 中"
            )
        return True, (
            f"已生效：活动进程上限 {self.active_process_limit}、Job 内存上限 {self.memory_mb}MB、"
            "Job 关闭即回收全部子进程"
        )

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        # 限额作用于当前进程及其子进程，无需改写命令行
        return list(argv)

    def describe(self) -> dict:
        return {
            "backend": self.name,
            "is_real_isolation": False,
            "claim": PARTIAL_CLAIM,
            "enforced": ["活动进程数上限", "Job 内存上限", "Job 关闭时回收子进程"],
            "not_enforced": ["文件系统", "网络"],
            "note": "这是资源限制而非隔离；不得据此宣称沙箱",
        }


def select_sandbox(preference: str | None = None) -> Sandbox:
    """按偏好或探测结果选择沙箱；**没有可用后端时返回 NoIsolation**，不假装。"""
    caps = {c.name: c for c in probe_capabilities()}

    def _ok(name: str) -> bool:
        cap = caps.get(name)
        return bool(cap and cap.available)

    if preference:
        pref = preference.lower()
        if pref in ("none", "off", "no"):
            return NoIsolation(reason="显式选择不使用隔离后端")
        if pref == "bwrap" and _ok("bwrap"):
            return BubblewrapSandbox(bwrap=shutil.which("bwrap") or "bwrap")
        if pref in ("seatbelt", "sandbox-exec") and _ok("sandbox-exec"):
            return MacSeatbeltSandbox(sandbox_exec=shutil.which("sandbox-exec") or "sandbox-exec")
        if pref in ("wsl",) and _ok("wsl"):
            return WslSandbox()
        if pref in ("docker", "podman", "container"):
            for rt in ("docker", "podman"):
                if _ok(rt):
                    return ContainerSandbox(runtime=rt)
        return NoIsolation(reason=f"请求的隔离后端 {preference!r} 在本机不可用")

    # 自动选择只考虑**可信可用**的后端。
    # 注意 WSL 不在自动列表里：`wsl.exe` 存在不代表可用（受限环境会按安全策略
    # 直接拦截它）。实测踩过：只因存在 wsl.exe 就自动选中，导致每条命令都被包进
    # wsl 而失败 —— "存在"不等于"可用"，必须显式指定 `--isolation wsl` 才用。
    for name, factory in (
        ("bwrap", lambda: BubblewrapSandbox(bwrap=shutil.which("bwrap") or "bwrap")),
        ("sandbox-exec", lambda: MacSeatbeltSandbox(sandbox_exec=shutil.which("sandbox-exec") or "sandbox-exec")),
        ("docker", lambda: ContainerSandbox(runtime="docker")),
        ("podman", lambda: ContainerSandbox(runtime="podman")),
    ):
        if _ok(name):
            return factory()
    return NoIsolation()


def _conformance_from_evidence(
    *,
    checks: dict[str, bool],
    platform: str,
    process_tree_cleanup: bool | None = None,
    process_group_cleanup: bool | None = None,
    resource_limits: bool | None = None,
    uniform_violation: bool | None = None,
    doctor_self_test: bool | None = None,
) -> dict:
    """把 doctor 已采集的探针证据评分；无证据时保守全 False。"""
    from .conformance_evidence import score_probe_evidence

    try:
        return score_probe_evidence(
            checks,
            platform=platform,
            process_tree_cleanup=process_tree_cleanup,
            resource_limits=resource_limits,
            uniform_violation=uniform_violation,
            doctor_self_test=doctor_self_test,
            process_group_cleanup=process_group_cleanup,
        )
    except Exception:  # noqa: BLE001 - doctor 诊断失败不得误报可用
        return {
            "platform": platform,
            "outcomes": {},
            "evidence": {},
            "score": {
                "passed": 0, "total": 10, "critical_passed": False,
                "platform_critical_passed": False, "ready": False,
            },
            "contract": {"id": "icode-sandbox-v1", "total": 10,
                         "critical": 8, "minimum_passed": 9},
            "honest_note": "证据评分异常，按未验证处理",
        }


def capability_report() -> dict:
    """给 `icode doctor` 用的隔离能力报告（措辞必须能追溯到实测）。"""
    from .conformance import load_conformance_contract
    from .sandbox_policy import POLICY_SCHEMA_VERSION

    caps = probe_capabilities()
    sandbox = select_sandbox()
    contract = load_conformance_contract()
    bundled: dict[str, object] = {
        "installed": False,
        "minimal_probe_passed": False,
        "protected_path_probe_passed": False,
        "policy_ready": False,
        "detail": "当前平台不适用",
    }
    native_checks: dict[str, bool] = {}
    process_group_cleanup: bool | None = None
    if sys.platform.startswith("linux"):
        try:
            bundled_sandbox = LandlockSandbox.from_bundle()
            if bundled_sandbox is None:
                bundled["detail"] = "随包助手缺失或完整性校验失败"
            else:
                result = probe_native_sandbox(bundled_sandbox)
                native_checks = dict(result.checks)
                protected_result = probe_linux_protected_paths(bundled_sandbox)
                native_checks.update(protected_result.checks)
                bundled.update({
                    "installed": True,
                    "minimal_probe_passed": result.ready,
                    "protected_path_probe_passed": protected_result.passed,
                    "detail": (
                        result.detail if protected_result.passed
                        else protected_result.detail
                    ),
                })
        except Exception:  # noqa: BLE001 - doctor 诊断失败不得误报可用
            bundled["detail"] = "随包助手诊断异常"
    macos_group: dict[str, object] = {
        "executed": False, "passed": False, "checks": {}, "detail": "当前平台不适用",
    }
    if sys.platform == "darwin":
        group_result = probe_macos_process_group_cleanup(MacSeatbeltSandbox())
        process_group_cleanup = group_result.passed
        macos_group = {
            "executed": group_result.executed,
            "passed": group_result.passed,
            "checks": group_result.checks,
            "detail": group_result.detail,
        }
        native_checks = dict(group_result.checks) or native_checks
    windows_job: dict[str, object] = {
        "executed": False, "passed": False, "checks": {}, "detail": "当前平台不适用",
    }
    if sys.platform == "win32":
        from .windows_job import probe_windows_job_cleanup

        job_result = probe_windows_job_cleanup()
        windows_job = {
            "executed": job_result.executed,
            "passed": job_result.passed,
            "checks": job_result.checks,
            "detail": job_result.detail,
        }
        native_checks = dict(job_result.checks)

    platform = ("linux" if sys.platform.startswith("linux")
                else "macos" if sys.platform == "darwin"
                else "windows" if sys.platform == "win32"
                else "linux")
    conformance = _conformance_from_evidence(
        checks=native_checks,
        platform=platform,
        process_tree_cleanup=None,   # doctor 不跑完整回收探针，保守不计
        process_group_cleanup=process_group_cleanup,
        resource_limits=None,        # doctor 不跑独立资源限制探针，保守不计
        uniform_violation=None,      # doctor 不跑独立违规回执探针，保守不计
        # Only Linux currently runs a native sandbox self-test here. macOS
        # group cleanup and Windows Job cleanup are narrower probes; neither
        # proves the backend's complete filesystem/network contract.
        doctor_self_test=(
            bool(bundled.get("minimal_probe_passed"))
            and bool(bundled.get("protected_path_probe_passed"))
            if platform == "linux" else False
        ),
    )
    return {
        "probes": [
            {"name": c.name, "available": c.available, "kind": c.kind, "detail": c.detail}
            for c in caps
        ],
        "selected": sandbox.describe(),
        "honest_label": (
            sandbox.describe()["claim"] if sandbox.is_real_isolation else BASELINE_CLAIM
        ),
        "bundled_linux_helper": bundled,
        "macos_group_cleanup": macos_group,
        "windows_job_cleanup": windows_job,
        "policy_schema_version": POLICY_SCHEMA_VERSION,
        "conformance_contract": {
            "id": contract["contract_id"],
            "total": len(contract["capabilities"]),
            "critical": sum(item["critical"] for item in contract["capabilities"]),
            "minimum_passed": contract["minimum_passed"],
            "executed": True,
            "score": conformance["score"],
            "outcomes": conformance["outcomes"],
            "evidence": conformance["evidence"],
        },
    }
