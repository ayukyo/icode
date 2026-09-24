"""在干净 Linux CI 中构建、安装并实测随包原生助手。"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
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
            code = textwrap.dedent("""\
                import os
                import subprocess
                import sys
                import tempfile
                import time
                from pathlib import Path

                from icode.execution_broker import execute_policy_command
                from icode.native_helper import bundled_linux_helper
                from icode.isolation import LandlockSandbox, capability_report, probe_native_sandbox
                from icode.sandbox_policy import NetworkMode, SandboxPolicy

                helper = bundled_linux_helper()
                assert helper is not None, 'wheel helper missing'
                sandbox = LandlockSandbox.from_bundle()
                assert sandbox is not None and sandbox.helper == str(helper)
                assert sandbox.manifest is not None
                probe = probe_native_sandbox(sandbox)
                assert probe.ready, probe.detail
                cap = capability_report()['bundled_linux_helper']
                assert cap['installed'] and cap['minimal_probe_passed']
                assert not cap['policy_ready']
                with tempfile.TemporaryDirectory() as raw:
                    workspace = Path(raw).resolve()
                    policy = SandboxPolicy(
                        schema_version=1, run_id='wheel', ticket_id='wheel', step='code',
                        workspace_root=workspace, read_roots=(workspace,),
                        write_roots=(workspace,), deny_read_roots=(), deny_write_roots=(),
                        network_mode=NetworkMode.DENY, allowed_domains=(), process_limit=8,
                        wall_timeout_seconds=10, output_limit_bytes=1024, protected_paths=(),
                    )
                    sandbox.prepare_policy(policy)
                    smoke = execute_policy_command(
                        sandbox.wrap_policy([
                            sys.executable, '-c',
                            'import icode, os; assert os.getpid() == 2 and os.getppid() == 1; '
                            'print(icode.__name__)',
                        ], policy=policy), cwd=workspace, policy=policy, timeout=5,
                    )
                    assert smoke.error is None and smoke.exit_code == 0, smoke
                    assert smoke.output.strip() == 'icode', smoke.output
                    started = workspace / 'wheel-detached-started'
                    late = workspace / 'wheel-detached-survived'
                    grandchild = (
                        'import os, time; from pathlib import Path; '
                        f'os.setsid(); Path({str(started)!r}).write_text("detached"); '
                        'time.sleep(1.2); '
                        f'Path({str(late)!r}).write_text("escaped")'
                    )
                    parent = (
                        'import subprocess, sys, time\\nfrom pathlib import Path\\n'
                        f'subprocess.Popen([sys.executable, "-c", {grandchild!r}], '
                        'stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, '
                        'stderr=subprocess.DEVNULL)\\n'
                        f'for _ in range(200):\\n    if Path({str(started)!r}).exists(): break\\n'
                        '    time.sleep(0.01)\\n'
                        'else: raise RuntimeError("detached grandchild did not start")\\n'
                        'print("spawned-detached", flush=True)\\n'
                    )
                    cleanup = execute_policy_command(
                        sandbox.wrap_policy([sys.executable, '-c', parent], policy=policy),
                        cwd=workspace, policy=policy, timeout=5,
                    )
                    assert cleanup.error is None and cleanup.exit_code == 0, cleanup
                    assert 'spawned-detached' in cleanup.output, cleanup.output
                    assert started.read_text(encoding='ascii') == 'detached'
                    time.sleep(1.4)
                    assert not late.exists(), 'installed wheel left a detached descendant'
                print('installed wheel helper: namespace, Python and cleanup PASS')
            """)
            _run("probe installed wheel", [str(python), "-c", code], cwd=root, env=clean_env)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(f"::error::{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
