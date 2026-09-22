"""隔离能力层（Phase 5）。

目的：把「门禁不可绕过」从**约定**变成**机制**——在能落地的平台上用真正的
内核/容器级隔离执行外部命令；落不了的平台**如实标注**，绝不宣称沙箱。

三条铁律（有测试锁住）：
1. **能力靠探测，不靠假设。** 每台机器上有什么后端由 `probe_capabilities()` 实测。
2. **没落地就不许宣称沙箱。** `is_real_isolation=False` 的实现，`describe()`
   必须明说"应用层限制，非沙箱"。
3. **默认更严格的一侧。** 无法确认时按"无隔离"处理，而不是假设有隔离。

当前各平台现状（2026-09-23 实测于 Windows）：
    Linux   → `bwrap` 可用则给文件系统 + 网络隔离（需自行安装 bubblewrap）
    macOS   → `sandbox-exec` + 自写 profile
    容器    → `docker` / `podman` 可用则用容器
    Windows → **未实现内核级隔离**（Job Object 只限资源不限文件/网络；AppContainer
              需 Win32 组包，本运行时尚未做）→ 明确报告为「应用层限制」
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
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


def probe_capabilities() -> tuple[Capability, ...]:
    """探测本机可用的隔离后端。**只报告实测结果，不推断。**"""
    probes: list[Capability] = []
    for name, kind, detail in (
        ("bwrap", KIND_KERNEL, "bubblewrap：可 unshare 文件系统与网络命名空间"),
        ("sandbox-exec", KIND_KERNEL, "macOS Seatbelt：按 profile 限制文件与网络"),
        ("docker", KIND_CONTAINER, "容器：可限制挂载与网络"),
        ("podman", KIND_CONTAINER, "容器：可限制挂载与网络"),
    ):
        found = shutil.which(name)
        probes.append(Capability(
            name=name,
            available=bool(found),
            kind=kind,
            detail=f"{detail}；可执行文件：{found or '未找到'}",
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
            "--bind", ws, ws,          # 工作区可写
            "--chdir", ws,
            "--tmpfs", "/tmp",
        ]
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
        net = "(allow network*)" if network else ""
        return (
            "(version 1)"
            "(deny default)"
            "(allow process*)"
            "(allow sysctl-read)"
            f'(allow file-read* file-write* (subpath "{ws}"))'
            "(allow file-read* (subpath \"/usr\") (subpath \"/System\") (subpath \"/Library\")"
            ' (subpath \"/bin\") (subpath \"/sbin\") (subpath \"/private/tmp\"))'
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
            return BubblewrapSandbox()
        if pref in ("seatbelt", "sandbox-exec") and _ok("sandbox-exec"):
            return MacSeatbeltSandbox()
        if pref in ("docker", "podman", "container"):
            for rt in ("docker", "podman"):
                if _ok(rt):
                    return ContainerSandbox(runtime=rt)
        return NoIsolation(reason=f"请求的隔离后端 {preference!r} 在本机不可用")

    for name, factory in (
        ("bwrap", BubblewrapSandbox),
        ("sandbox-exec", MacSeatbeltSandbox),
        ("docker", lambda: ContainerSandbox(runtime="docker")),
        ("podman", lambda: ContainerSandbox(runtime="podman")),
    ):
        if _ok(name):
            return factory()
    return NoIsolation()


def capability_report() -> dict:
    """给 `icode doctor` 用的隔离能力报告（措辞必须能追溯到实测）。"""
    caps = probe_capabilities()
    sandbox = select_sandbox()
    return {
        "probes": [
            {"name": c.name, "available": c.available, "kind": c.kind, "detail": c.detail}
            for c in caps
        ],
        "selected": sandbox.describe(),
        "honest_label": (
            sandbox.describe()["claim"] if sandbox.is_real_isolation else BASELINE_CLAIM
        ),
    }
