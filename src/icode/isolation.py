"""隔离能力层（Phase 5）。

目的：把「门禁不可绕过」从**约定**变成**机制**——在能落地的平台上用真正的
内核/容器级隔离执行外部命令；落不了的平台**如实标注**，绝不宣称沙箱。

三条铁律（有测试锁住）：
1. **能力靠探测，不靠假设。** 每台机器上有什么后端由 `probe_capabilities()` 实测。
2. **没落地就不许宣称沙箱。** `is_real_isolation=False` 的实现，`describe()`
   必须明说"应用层限制，非沙箱"。
3. **默认更严格的一侧。** 无法确认时按"无隔离"处理，而不是假设有隔离。

当前各平台现状（R2.2 实施中）：
    Linux   → `bwrap` 需通过最小真实负向探测（目前仍依赖系统安装）
    macOS   → `sandbox-exec` 需通过最小真实负向探测
    容器    → `docker` / `podman` 可用则用容器
    Windows → **未实现内核级隔离**（Job Object 只限资源不限文件/网络；AppContainer
              需 Win32 组包，本运行时尚未做）→ 明确报告为「应用层限制」
"""

from __future__ import annotations

import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Protocol, Sequence, runtime_checkable

KIND_KERNEL = "kernel"
KIND_CONTAINER = "container"
KIND_NONE = "none"

# 各实现的能力声明用语，统一在此，避免各处口径漂移
BASELINE_CLAIM = "应用层限制，非内核级沙箱"
BASELINE_NOTE = "工作区限制 + 危险命令拦截由 guard 在应用层完成；模型若绕过运行时直接执行 shell，这些规则不构成保障"


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
    """R2.2 开发期 Linux 原生助手；未打包/绑定策略前不参与自动选择。"""

    helper: str
    name: str = "landlock"

    @property
    def is_real_isolation(self) -> bool:
        return True

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        if network:
            raise RuntimeError("Landlock helper does not support network grants")
        helper = Path(self.helper).resolve()
        if not helper.is_file():
            raise RuntimeError("Landlock helper is unavailable")
        return [str(helper), "--workspace", str(Path(workspace).resolve()), "--", *argv]

    def describe(self) -> dict:
        return {
            "backend": self.name,
            "is_real_isolation": True,
            "claim": "开发期 Landlock/seccomp 原生边界，尚未达到 R2 完整合同",
            "enforced": ["工作区读写", "默认断网", "子进程继承"],
            "not_enforced": ["R2 完整策略映射与发布包校验"],
        }


@dataclass
class BubblewrapSandbox:
    """Linux：bwrap 绑定工作区 + 可选断网。"""

    bwrap: str = "bwrap"
    name: str = "bwrap"

    @property
    def is_real_isolation(self) -> bool:
        return True

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
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
            "--bind", ws, ws,          # 工作区可写
            "--chdir", ws,
        ]
        if Path("/lib64").exists():
            out += ["--ro-bind", "/lib64", "/lib64"]
        if not network:
            out.append("--unshare-net")
        out += ["--", *argv]
        return out

    def describe(self) -> dict:
        return {
            "backend": self.name,
            "is_real_isolation": True,
            "claim": "内核级隔离（bubblewrap 命名空间）",
            "enforced": ["文件系统（除工作区外只读）", "网络（默认断网）", "PID/IPC/UTS"],
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

    def _profile(self, workspace: Path, network: bool) -> str:
        ws = str(Path(workspace).resolve())
        if any(ord(char) < 32 or ord(char) == 127 for char in ws):
            raise ValueError("Seatbelt workspace path contains control characters")
        escaped_ws = ws.replace("\\", "\\\\").replace('"', '\\"')
        net = "(allow network*)" if network else ""
        return (
            "(version 1)"
            "(deny default)"
            "(allow process*)"
            "(allow sysctl-read)"
            f'(allow file-read-metadata file-test-existence (path-ancestors "{escaped_ws}"))'
            '(allow file-read* file-test-existence (literal "/"))'
            f'(allow file-read* file-write* (subpath "{escaped_ws}"))'
            "(allow file-read* (subpath \"/usr\") (subpath \"/System\") (subpath \"/Library\")"
            ' (subpath \"/bin\") (subpath \"/sbin\") (subpath \"/private/tmp\")'
            ' (subpath \"/private/etc/ssl\"))'
            f"{net}"
        )

    def wrap(self, argv: Sequence[str], *, workspace: Path, network: bool = False) -> list[str]:
        return [self.sandbox_exec, "-p", self._profile(workspace, network), *argv]

    def describe(self) -> dict:
        return {
            "backend": self.name,
            "is_real_isolation": True,
            "claim": "内核级隔离（macOS Seatbelt profile）",
            "enforced": ["文件系统（白名单外拒绝）", "网络（默认拒绝）"],
            "not_enforced": ["同用户下的内核漏洞逃逸"],
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


def capability_report() -> dict:
    """给 `icode doctor` 用的隔离能力报告（措辞必须能追溯到实测）。"""
    from .conformance import load_conformance_contract
    from .sandbox_policy import POLICY_SCHEMA_VERSION

    caps = probe_capabilities()
    sandbox = select_sandbox()
    contract = load_conformance_contract()
    return {
        "probes": [
            {"name": c.name, "available": c.available, "kind": c.kind, "detail": c.detail}
            for c in caps
        ],
        "selected": sandbox.describe(),
        "honest_label": (
            sandbox.describe()["claim"] if sandbox.is_real_isolation else BASELINE_CLAIM
        ),
        "policy_schema_version": POLICY_SCHEMA_VERSION,
        "conformance_contract": {
            "id": contract["contract_id"],
            "total": len(contract["capabilities"]),
            "critical": sum(item["critical"] for item in contract["capabilities"]),
            "minimum_passed": contract["minimum_passed"],
            "executed": False,
        },
    }
