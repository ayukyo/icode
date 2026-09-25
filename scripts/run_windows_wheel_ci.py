"""Build and install a Windows architecture wheel using a synthetic, never-run PE."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

_REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY / "src"))

from icode.native_helper import windows_arch_from_platform  # noqa: E402

_HELPER_ENV = "ICODE_WINDOWS_SANDBOX_HELPER"


def _run(stage: str, argv: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    result = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=240, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-1600:]
        raise RuntimeError(f"{stage} exit={result.returncode}: {detail}")
    print(f"{stage}: PASS")


def _synthetic_pe(machine: int) -> bytes:
    image = bytearray(0x80 + 6)
    image[:2] = b"MZ"
    image[0x3C:0x40] = (0x80).to_bytes(4, "little")
    image[0x80:0x84] = b"PE\0\0"
    image[0x84:0x86] = machine.to_bytes(2, "little")
    return bytes(image)


def main() -> int:
    if sys.platform != "win32":
        print("::error::Windows wheel packaging probe was invoked on another platform")
        return 1
    try:
        platform_name = sysconfig.get_platform()
        arch = windows_arch_from_platform(platform_name)
        machine = {"x64": 0x8664, "arm64": 0xAA64}[arch]
        with tempfile.TemporaryDirectory(prefix="icode-windows-wheel-") as raw:
            root = Path(raw)
            helper_dir = root / "synthetic helper artifact"
            helper_dir.mkdir()
            helper = helper_dir / "sandbox-helper.exe"
            image = _synthetic_pe(machine)
            helper.write_bytes(image)
            Path(str(helper) + ".sha256").write_text(
                hashlib.sha256(image).hexdigest() + "\n", encoding="ascii",
            )

            dist = root / "dist"
            env = os.environ.copy()
            env[_HELPER_ENV] = str(helper)
            _run(
                "install build frontend",
                [sys.executable, "-m", "pip", "install", "build"],
                cwd=root, env=env,
            )

            pure_env = env.copy()
            pure_env.pop(_HELPER_ENV, None)
            pure_dist = root / "dist-pure-python"
            _run(
                "build pure Python wheel without native helper",
                [sys.executable, "-m", "build", "--wheel", "--outdir", str(pure_dist)],
                cwd=_REPOSITORY, env=pure_env,
            )
            pure_wheels = list(pure_dist.glob("*.whl"))
            if len(pure_wheels) != 1 or not pure_wheels[0].name.endswith("-py3-none-any.whl"):
                raise RuntimeError("build without helper must remain a universal pure-Python wheel")
            with zipfile.ZipFile(pure_wheels[0]) as archive:
                names = archive.namelist()
                if any("icode-sandbox-windows-" in name for name in names):
                    raise RuntimeError("pure-Python wheel unexpectedly contains a Windows helper")

            pure_venv = root / "pure-venv"
            _run("create pure-wheel venv", [sys.executable, "-m", "venv", str(pure_venv)],
                 cwd=root, env=pure_env)
            pure_python = pure_venv / "Scripts" / "python.exe"
            clean_pure_env = pure_env.copy()
            clean_pure_env.pop("PYTHONPATH", None)
            clean_pure_env.pop(_HELPER_ENV, None)
            _run("install pure-Python wheel", [str(pure_python), "-m", "pip", "install",
                 "--no-deps", str(pure_wheels[0])], cwd=root, env=clean_pure_env)
            _run(
                "pure-Python install reports helper unavailable",
                [str(pure_python), "-c",
                 "from icode.native_helper import bundled_windows_helper; "
                 "assert bundled_windows_helper() is None"],
                cwd=root, env=clean_pure_env,
            )

            _run(
                "build architecture-tagged Windows wheel",
                [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist)],
                cwd=_REPOSITORY, env=env,
            )
            wheels = list(dist.glob("*.whl"))
            if len(wheels) != 1:
                raise RuntimeError(f"expected one wheel, found {len(wheels)}")
            _run(
                "inspect Windows wheel metadata and integrity",
                [sys.executable, str(_REPOSITORY / "scripts" / "check_windows_wheel.py"),
                 str(wheels[0])],
                cwd=root, env=env,
            )

            venv = root / "venv"
            _run("create isolated venv", [sys.executable, "-m", "venv", str(venv)],
                 cwd=root, env=env)
            python = venv / "Scripts" / "python.exe"
            clean_env = env.copy()
            clean_env.pop("PYTHONPATH", None)
            clean_env.pop(_HELPER_ENV, None)
            _run("install Windows wheel", [str(python), "-m", "pip", "install",
                 "--no-deps", str(wheels[0])], cwd=root, env=clean_env)
            code = (
                "from pathlib import Path; import sysconfig; "
                "from icode.native_helper import bundled_windows_helper, "
                "windows_arch_from_platform; "
                "helper=bundled_windows_helper(); "
                "assert helper is not None and helper.is_file(); "
                "assert helper.name.endswith(windows_arch_from_platform(sysconfig.get_platform()) + '.exe'); "
                "print('installed helper resolved from package')"
            )
            _run("resolve installed helper without source checkout", [str(python), "-c", code],
                 cwd=root, env=clean_env)

            installed_code = (
                "from pathlib import Path; import icode.native_helper as nh; "
                "helper=nh.bundled_windows_helper(); assert helper is not None; "
                "helper.rename(helper.with_suffix('.exe.disabled')); "
                "assert nh.bundled_windows_helper() is None; "
                "print('missing installed helper fails closed')"
            )
            _run("fail closed when bundled helper is missing", [str(python), "-c", installed_code],
                 cwd=root, env=clean_env)
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
        print(f"::error::windows_wheel_probe_failed ({type(exc).__name__}: {exc})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
