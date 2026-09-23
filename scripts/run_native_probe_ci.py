"""R2.2 开发期原生后端负向探测；未通过则 CI 失败。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from icode.isolation import LandlockSandbox, MacSeatbeltSandbox, probe_native_sandbox


def main() -> int:
    if sys.platform.startswith("linux"):
        compiler = shutil.which("cc")
        if compiler is None:
            print("::error::Linux C compiler is missing from the development runner")
            return 1
        source = Path(__file__).resolve().parents[1] / "native" / "linux" / "icode_landlock.c"
        with tempfile.TemporaryDirectory(prefix="icode-native-ci-") as raw:
            helper = Path(raw) / "icode-landlock"
            build = subprocess.run(
                [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                 str(source), "-o", str(helper)],
                capture_output=True, text=True, check=False,
            )
            if build.returncode != 0:
                print(f"::error::Linux helper build failed: {build.stderr[-1500:]}")
                return 1
            return _check(LandlockSandbox(helper=str(helper)), str(helper))
    elif sys.platform == "darwin":
        executable = shutil.which("sandbox-exec")
        if executable is None:
            print("::error::sandbox-exec executable is missing")
            return 1
        return _check(MacSeatbeltSandbox(sandbox_exec=executable), executable)
    else:
        print("::error::R2.2 native probe CI only supports Linux and macOS")
        return 1


def _check(backend: LandlockSandbox | MacSeatbeltSandbox, executable: str) -> int:
    result = probe_native_sandbox(backend)
    for name, passed in result.checks.items():
        print(f"{backend.name} {name}: {'PASS' if passed else 'FAIL'}")
    if not result.ready:
        if isinstance(backend, MacSeatbeltSandbox):
            true_path = shutil.which("true")
            if true_path is not None:
                for name, profile in (
                    ("allow_default", "(version 1)(allow default)"),
                    ("deny_with_process_read", "(version 1)(deny default)(allow process*)(allow file-read*)"),
                    ("deny_with_process_read_sysctl", "(version 1)(deny default)(allow process*)(allow sysctl-read)(allow file-read*)"),
                    ("current_with_read_all", backend._profile(Path.cwd(), False) + "(allow file-read*)"),
                    ("current_profile", backend._profile(Path.cwd(), False)),
                ):
                    try:
                        control = subprocess.run(
                            [executable, "-p", profile, true_path],
                            capture_output=True, text=True, timeout=4, check=False,
                        )
                        print(
                            f"::warning::macOS diagnostic {name}: exit={control.returncode} "
                            f"stderr={control.stderr.strip()[:300]!r}"
                        )
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        print(f"::warning::macOS diagnostic {name}: {type(exc).__name__}")
        print(f"::error::{backend.name} native probe failed: {result.detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
