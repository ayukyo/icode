"""在构建 Linux wheel 时随包编译静态隔离助手。"""

from __future__ import annotations

import hashlib
import os
import platform
import shlex
import subprocess
import sys
import sysconfig
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.build_py import build_py

_SETUP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_SETUP_ROOT / "src"))
sys.path.insert(0, str(_SETUP_ROOT / "scripts"))

from icode.native_helper import windows_arch_from_platform  # noqa: E402
from windows_wheel import (  # noqa: E402
    reject_stale_windows_helpers, stage_windows_helper, stage_windows_provenance,
)


_WINDOWS_HELPER_ENV = "ICODE_WINDOWS_SANDBOX_HELPER"
_WINDOWS_BUNDLE_ENV = "ICODE_WINDOWS_SANDBOX_BUNDLE"
_WINDOWS_VERIFIER_ENV = "ICODE_WINDOWS_PROVENANCE_VERIFIER"
_WINDOWS_SOURCE_ENV = "ICODE_WINDOWS_PROVENANCE_SOURCE_SHA"
_WINDOWS_NOTICES_ENV = "ICODE_WINDOWS_PROVENANCE_NOTICES"


class NativeDistribution(Distribution):
    def has_ext_modules(self) -> bool:
        # Linux wheel 包含 ELF 可执行文件，不能误标记为 py3-none-any。
        # Windows wheels become platform-specific only when an architecture-
        # verified native helper is explicitly supplied to the build.
        return (
            sys.platform.startswith("linux")
            or (sys.platform == "win32" and bool(os.environ.get(_WINDOWS_HELPER_ENV)))
            or super().has_ext_modules()
        )


class NativeWheel(bdist_wheel):
    def get_tag(self) -> tuple[str, str, str]:
        python_tag, abi_tag, platform_tag = super().get_tag()
        if sys.platform.startswith("linux"):
            # 助手是独立静态 ELF，不链接 CPython ABI；一个 wheel 支持 3.11+。
            return "py3", "none", platform_tag
        if sys.platform == "win32" and os.environ.get(_WINDOWS_HELPER_ENV):
            arch = windows_arch_from_platform(sysconfig.get_platform())
            windows_tag = {"x64": "win_amd64", "arm64": "win_arm64"}[arch]
            # The package ships an independent executable, not a CPython module.
            return "py3", "none", windows_tag
        return python_tag, abi_tag, platform_tag


class BuildWithNativeHelper(build_py):
    def run(self) -> None:
        super().run()
        windows_helper = os.environ.get(_WINDOWS_HELPER_ENV)
        windows_bundle = os.environ.get(_WINDOWS_BUNDLE_ENV)
        windows_verifier = os.environ.get(_WINDOWS_VERIFIER_ENV)
        windows_source_sha = os.environ.get(_WINDOWS_SOURCE_ENV)
        windows_notices = os.environ.get(_WINDOWS_NOTICES_ENV)
        offline_inputs = (windows_verifier, windows_source_sha, windows_notices)
        if any(offline_inputs) and not all(offline_inputs):
            raise RuntimeError("Windows offline verifier requires all explicit build inputs")
        if any(offline_inputs) and not (windows_helper and windows_bundle):
            raise RuntimeError("Windows offline verifier requires a proof-carrying Windows helper")
        if windows_bundle and not windows_helper:
            raise RuntimeError("Windows provenance bundle requires an explicit native helper")
        if windows_helper and sys.platform != "win32":
            raise RuntimeError("Windows helper wheels must be built on a native Windows runner")
        if sys.platform.startswith("linux"):
            if platform.machine().lower() not in {"x86_64", "aarch64", "arm64"}:
                raise RuntimeError("R2.2 Linux helper only supports x86_64 and arm64")

            source = _SETUP_ROOT / "native" / "linux" / "icode_landlock.c"
            destination = Path(self.build_lib) / "icode" / "native"
            destination.mkdir(parents=True, exist_ok=True)
            binary = destination / "icode-landlock"
            compiler = shlex.split(os.environ.get("CC", "cc"))
            if not compiler:
                raise RuntimeError("C compiler is not configured")
            subprocess.run(
                [*compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-static",
                 str(source), "-o", str(binary)],
                check=True,
            )
            binary.chmod(0o755)
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            (destination / "icode-landlock.sha256").write_text(
                digest + "\n", encoding="ascii",
            )
            return
        if windows_helper:
            stage_windows_helper(
                windows_helper, self.build_lib, platform_name=sysconfig.get_platform(),
                provenance_bundle=windows_bundle,
            )
            if windows_verifier:
                stage_windows_provenance(
                    windows_verifier, self.build_lib, platform_name=sysconfig.get_platform(),
                    source_sha=windows_source_sha, notices=windows_notices,
                )
        elif sys.platform == "win32":
            reject_stale_windows_helpers(self.build_lib)


setup(
    cmdclass={"build_py": BuildWithNativeHelper, "bdist_wheel": NativeWheel},
    distclass=NativeDistribution,
)
