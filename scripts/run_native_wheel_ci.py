"""在干净 Linux CI 中构建、安装并实测随包原生助手。"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(stage: str, argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-1800:]
        escaped = detail.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        raise RuntimeError(f"{stage} exit={result.returncode}: {escaped}")
    print(f"{stage}: PASS")


def main() -> int:
    if not sys.platform.startswith("linux"):
        print("::error::Linux native wheel CI was invoked on a non-Linux platform")
        return 1
    repository = Path(__file__).resolve().parents[1]
    try:
        with tempfile.TemporaryDirectory(prefix="icode-native-wheel-") as raw:
            root = Path(raw)
            dist = root / "dist"
            _run("install build frontend", [sys.executable, "-m", "pip", "install", "build"], cwd=root)
            _run("build Linux wheel", [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist)], cwd=repository)
            wheels = list(dist.glob("*.whl"))
            if len(wheels) != 1:
                raise RuntimeError(f"expected one Linux wheel, found {len(wheels)}")
            _run("inspect Linux wheel", [sys.executable, str(repository / "scripts" / "check_native_wheel.py"), str(wheels[0])], cwd=root)
            venv = root / "venv"
            _run("create isolated venv", [sys.executable, "-m", "venv", str(venv)], cwd=root)
            python = venv / "bin" / "python"
            _run("install wheel", [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])], cwd=root)
            clean_env = os.environ.copy()
            clean_env.pop("PYTHONPATH", None)
            code = (
                "import subprocess, sys, tempfile; from pathlib import Path; "
                "from icode.artifact_broker import ArtifactBroker; "
                "from icode.execution_broker import execute_policy_command; "
                "from icode.native_helper import bundled_linux_helper; "
                "from icode.isolation import LandlockSandbox, capability_report, probe_native_sandbox; "
                "p = bundled_linux_helper(); assert p is not None, 'helper missing'; "
                "s = LandlockSandbox(helper=str(p)); "
                "r = probe_native_sandbox(s); assert r.ready, r.detail; "
                "cap = capability_report()['bundled_linux_helper']; "
                "assert cap['installed'] and cap['minimal_probe_passed']; "
                "assert not cap['policy_ready']; "
                "t = tempfile.TemporaryDirectory(); "
                "child = subprocess.run(s.wrap([sys.executable, '-c', "
                "'import icode; print(icode.__name__)'], workspace=Path(t.name)), "
                "capture_output=True, text=True, timeout=5); "
                "assert child.returncode == 0, child.stderr[-300:]; "
                "assert child.stdout.strip() == 'icode', child.stdout; "
                "t.cleanup(); print('native helper and installed Python: ready')"
            )
            _run("probe installed wheel", [str(python), "-c", code], cwd=root, env=clean_env)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(f"::error::{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
