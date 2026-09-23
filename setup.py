"""在构建 Linux wheel 时随包编译静态隔离助手。"""

from __future__ import annotations

import hashlib
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

from setuptools import Distribution, setup
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.build_py import build_py


class NativeDistribution(Distribution):
    def has_ext_modules(self) -> bool:
        # Linux wheel 包含 ELF 可执行文件，不能误标记为 py3-none-any。
        return sys.platform.startswith("linux") or super().has_ext_modules()


class NativeWheel(bdist_wheel):
    def get_tag(self) -> tuple[str, str, str]:
        python_tag, abi_tag, platform_tag = super().get_tag()
        if sys.platform.startswith("linux"):
            # 助手是独立静态 ELF，不链接 CPython ABI；一个 wheel 支持 3.11+。
            return "py3", "none", platform_tag
        return python_tag, abi_tag, platform_tag


class BuildWithLinuxHelper(build_py):
    def run(self) -> None:
        super().run()
        if not sys.platform.startswith("linux"):
            return
        if platform.machine().lower() not in {"x86_64", "aarch64", "arm64"}:
            raise RuntimeError("R2.2 Linux helper only supports x86_64 and arm64")

        source = Path(__file__).resolve().parent / "native" / "linux" / "icode_landlock.c"
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
        (destination / "icode-landlock.sha256").write_text(digest + "\n", encoding="ascii")


setup(
    cmdclass={"build_py": BuildWithLinuxHelper, "bdist_wheel": NativeWheel},
    distclass=NativeDistribution,
)
