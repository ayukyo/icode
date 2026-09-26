"""R2.2 开发期原生后端负向探测；未通过则 CI 失败。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from icode.conformance_evidence import score_probe_evidence
from icode.isolation import (
    LandlockSandbox,
    MacSeatbeltSandbox,
    probe_macos_process_group_cleanup,
    probe_native_sandbox,
)


def _emit_conformance_score(
    checks: dict[str, bool],
    *,
    platform: str,
    doctor_self_test: bool,
    process_group_cleanup: bool | None = None,
) -> None:
    """把本次原生探针证据映射到十项一致性合同并打印评分。

    只把**本次探针实际采集的证据**计入；未验证能力保守为 False，
    因此该分数反映「当前探针矩阵已直接证明的能力」，不冒充完整验收。
    """
    report = score_probe_evidence(
        checks,
        platform=platform,
        doctor_self_test=doctor_self_test,
        process_group_cleanup=process_group_cleanup,
    )
    score = report["score"]
    print(
        f"::notice::conformance {platform} "
        f"passed={score['passed']}/{score['total']} "
        f"critical_passed={str(score['critical_passed']).lower()} "
        f"ready={str(score['ready']).lower()}"
    )
    for capability_id, passed in sorted(report["outcomes"].items()):
        mark = "PASS" if passed else "UNVERIFIED"
        raw_source = report["evidence"][capability_id]
        source = ",".join(raw_source) if isinstance(raw_source, list) else str(raw_source)
        source = source or "-"
        print(f"conformance {platform} {capability_id}: {mark} ({source})")


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
    platform = "linux" if sys.platform.startswith("linux") else "macos"
    group_result = None
    if platform == "macos":
        group_result = probe_macos_process_group_cleanup(backend)
        for name, passed in group_result.checks.items():
            print(f"{backend.name} process_group_{name}: {'PASS' if passed else 'FAIL'}")
    _emit_conformance_score(result.checks, platform=platform,
                            doctor_self_test=(
                                result.ready
                                and (group_result is None or group_result.passed)
                            ),
                            process_group_cleanup=(
                                group_result.passed if group_result is not None else None
                            ))
    group_failed = group_result is not None and not group_result.passed
    if not result.ready or group_failed:
        if not result.ready and isinstance(backend, MacSeatbeltSandbox):
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
        failures = []
        if not result.ready:
            failures.append(f"native probe: {result.detail}")
        if group_failed:
            failures.append(f"process-group cleanup: {group_result.detail}")
        print(f"::error::{backend.name} native probe failed: {'; '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
