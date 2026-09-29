"""R2.2 开发期原生后端负向探测；未通过则 CI 失败。"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from icode.conformance_evidence import score_probe_evidence
from icode.isolation import (
    LandlockSandbox,
    MacSeatbeltSandbox,
    probe_macos_process_group_cleanup,
    probe_macos_protected_paths,
    probe_linux_protected_paths,
    probe_linux_process_tree_cleanup,
    probe_native_sandbox,
)

MACOS_PROTECTED_PATH_CHECKS = (
    "workspace_write_allowed",
    "protected_write_denied",
    "protected_rename_denied",
)
LINUX_PROTECTED_PATH_CHECKS = (
    "workspace_write_allowed",
    "protected_write_denied",
    "protected_rename_denied",
)

ProbeStatus = Literal["passed", "skipped", "failed"]


@dataclass(frozen=True)
class ProbeExecution:
    """单个 unittest 行为探针的三态结果；skip 不代表能力通过。"""

    status: ProbeStatus
    detail: str


def _run_unittest_probe(test_case: unittest.TestCase) -> ProbeExecution:
    """执行一个行为用例并保留 unittest 的显式 skip/failure 语义。"""
    result = unittest.TestResult()
    unittest.TestSuite((test_case,)).run(result)
    if result.testsRun != 1:
        return ProbeExecution("failed", f"expected one test, ran {result.testsRun}")
    if result.skipped:
        return ProbeExecution("skipped", result.skipped[0][1])
    if result.wasSuccessful():
        return ProbeExecution("passed", "")
    failures = result.failures + result.errors
    detail = failures[0][1] if failures else "unittest did not report success"
    return ProbeExecution("failed", " ".join(detail.split())[-500:])


def _probe_linux_network_lease_expiry() -> ProbeExecution:
    """复用真实 Linux PID namespace/SCM_RIGHTS/CONNECT TTL 端到端用例。"""
    repository_root = str(Path(__file__).resolve().parents[1])
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    try:
        from tests.test_linux_pidns_cleanup import TestLinuxPidNamespaceCleanup

        test_case = TestLinuxPidNamespaceCleanup(
            "test可信helper交接后授权隧道随租约到期关闭",
        )
    except Exception as exc:
        return ProbeExecution("failed", f"could not load Linux lease expiry test: {exc}")
    return _run_unittest_probe(test_case)


def _probe_linux_seccomp_receipt() -> ProbeExecution:
    """Run a diagnostic for bounded Linux seccomp receipt categories.

    This does not satisfy the platform-wide uniform-violation capability:
    Landlock file denials and other platform enforcement sources are not
    currently captured by this USER_NOTIF observer.
    """
    if not sys.platform.startswith("linux"):
        return ProbeExecution("skipped", "linux_only")
    repository_root = str(Path(__file__).resolve().parents[1])
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    try:
        from tests.test_linux_violation_receipt import TestLinuxViolationReceipt

        test_case = TestLinuxViolationReceipt(
            "test_multiple_os_denials_share_minimized_receipt_without_raw_syscall_data",
        )
    except Exception:  # noqa: BLE001 - CI receipt probe must not leak import details.
        return ProbeExecution("failed", "native_receipt_probe_unavailable")
    execution = _run_unittest_probe(test_case)
    if execution.status == "passed":
        return ProbeExecution("passed", "multiple_categories_observed")
    if execution.status == "skipped":
        return ProbeExecution("skipped", "native_receipt_environment_unavailable")
    return ProbeExecution("failed", "native_violation_receipt_mismatch")


def _probe_linux_observed_command_bounds() -> ProbeExecution:
    """Verify timeout/output bounds on the actual deny-only run_command path."""
    if not sys.platform.startswith("linux"):
        return ProbeExecution("skipped", "linux_only")
    repository_root = str(Path(__file__).resolve().parents[1])
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    try:
        from tests.test_linux_violation_receipt import TestLinuxViolationReceipt

        test_case = TestLinuxViolationReceipt(
            "test_deny_only_run_command_enforces_output_and_timeout_without_os_denial_receipt",
        )
    except Exception:  # noqa: BLE001 - Do not expose import paths or diagnostics.
        return ProbeExecution("failed", "native_command_bounds_probe_unavailable")
    execution = _run_unittest_probe(test_case)
    if execution.status == "passed":
        return ProbeExecution("passed", "timeout_and_output_bounds_observed")
    if execution.status == "skipped":
        return ProbeExecution("skipped", "native_command_bounds_environment_unavailable")
    return ProbeExecution("failed", "native_command_bounds_mismatch")


def _emit_conformance_score(
    checks: dict[str, bool],
    *,
    platform: str,
    doctor_self_test: bool,
    process_tree_cleanup: bool | None = None,
    process_group_cleanup: bool | None = None,
) -> None:
    """把本次原生探针证据映射到十项一致性合同并打印评分。

    只把**本次探针实际采集的证据**计入；未验证能力保守为 False，
    因此该分数反映「当前探针矩阵已直接证明的能力」，不冒充完整验收。
    """
    report = score_probe_evidence(
        checks,
        platform=platform,
        process_tree_cleanup=process_tree_cleanup,
        doctor_self_test=doctor_self_test,
        process_group_cleanup=process_group_cleanup,
    )
    score = report["score"]
    group_cleanup = score["process_group_cleanup"]
    process_group_status = (
        "not_applicable"
        if group_cleanup is None
        else str(group_cleanup).lower()
    )
    print(
        f"::notice::conformance {platform} "
        f"passed={score['passed']}/{score['total']} "
        f"critical_passed={str(score['critical_passed']).lower()} "
        f"platform_critical_passed={str(score['platform_critical_passed']).lower()} "
        f"process_group_cleanup={process_group_status} "
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
            manifest = Path(str(helper) + ".sha256")
            manifest.write_text(
                hashlib.sha256(helper.read_bytes()).hexdigest() + "\n",
                encoding="ascii",
            )
            return _check(
                LandlockSandbox(helper=str(helper), manifest=str(manifest)),
                str(helper),
            )
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
    platform = "linux" if sys.platform.startswith("linux") else "macos"
    group_result = None
    protected_result = None
    process_tree_result = None
    lease_expiry_result = None
    seccomp_receipt_result = None
    observed_command_bounds_result = None
    if platform == "macos":
        protected_result = probe_macos_protected_paths(backend)
        group_result = probe_macos_process_group_cleanup(backend)
        protected_checks = MACOS_PROTECTED_PATH_CHECKS
    elif platform == "linux":
        protected_result = probe_linux_protected_paths(backend)
        process_tree_result = probe_linux_process_tree_cleanup(backend)
        lease_expiry_result = _probe_linux_network_lease_expiry()
        seccomp_receipt_result = _probe_linux_seccomp_receipt()
        observed_command_bounds_result = _probe_linux_observed_command_bounds()
        protected_checks = LINUX_PROTECTED_PATH_CHECKS
    else:
        protected_checks = ()
    if protected_result is not None:
        for name in protected_checks:
            passed = protected_result.checks.get(name) is True
            print(
                f"::notice::{platform}-protected-path {name}="
                f"{str(passed).lower()}"
            )
            print(f"{backend.name} {name}: {'PASS' if passed else 'FAIL'}")
    if group_result is not None:
        for name, passed in group_result.checks.items():
            print(f"{backend.name} process_group_{name}: {'PASS' if passed else 'FAIL'}")
    if process_tree_result is not None:
        for name, passed in process_tree_result.checks.items():
            print(f"{backend.name} process_tree_{name}: {'PASS' if passed else 'FAIL'}")
        print(
            "::notice::linux-process-tree-cleanup "
            f"executed={str(process_tree_result.executed).lower()} "
            f"passed={str(process_tree_result.passed).lower()} "
            f"detail={process_tree_result.detail}"
        )
    checks = dict(result.checks)
    if protected_result is not None:
        checks.update(protected_result.checks)
    lease_expiry_failed = False
    violation_receipt_failed = False
    observed_command_bounds_failed = False
    if lease_expiry_result is not None:
        lease_status = lease_expiry_result.status
        if lease_status not in {"passed", "skipped", "failed"}:
            lease_status = "failed"
        checks["network_allowlist_expiry"] = lease_status == "passed"
        lease_expiry_failed = lease_status == "failed"
        print(f"::notice::linux-network-allowlist-expiry status={lease_status}")
        safe_detail = " ".join(lease_expiry_result.detail.split())[:500] or "-"
        print(f"{backend.name} network_allowlist_expiry: {lease_status.upper()} ({safe_detail})")
    if seccomp_receipt_result is not None:
        violation_status = seccomp_receipt_result.status
        if violation_status not in {"passed", "skipped", "failed"}:
            violation_status = "failed"
        violation_receipt_failed = violation_status == "failed"
        print(f"::notice::linux-seccomp-receipt-probe status={violation_status}")
        safe_detail = (
            "multiple_categories_observed"
            if violation_status == "passed"
            else "native_receipt_environment_unavailable"
            if violation_status == "skipped"
            else "native_violation_receipt_mismatch"
        )
        print(
            f"{backend.name} seccomp_receipt_probe: {violation_status.upper()} "
            f"({safe_detail})"
        )
    if observed_command_bounds_result is not None:
        bounds_status = observed_command_bounds_result.status
        if bounds_status not in {"passed", "skipped", "failed"}:
            bounds_status = "failed"
        observed_command_bounds_failed = bounds_status == "failed"
        print(f"::notice::linux-observed-command-bounds status={bounds_status}")
        safe_detail = (
            "timeout_and_output_bounds_observed"
            if bounds_status == "passed"
            else "native_command_bounds_environment_unavailable"
            if bounds_status == "skipped"
            else "native_command_bounds_mismatch"
        )
        print(
            f"{backend.name} observed_command_bounds: {bounds_status.upper()} "
            f"({safe_detail})"
        )
    for name, passed in result.checks.items():
        print(f"{backend.name} {name}: {'PASS' if passed else 'FAIL'}")
    _emit_conformance_score(checks, platform=platform,
                            doctor_self_test=(
                                result.ready
                                and (protected_result is None or protected_result.passed)
                                and (process_tree_result is None or process_tree_result.passed)
                                and (group_result is None or group_result.passed)
                            ),
                            process_tree_cleanup=(
                                process_tree_result.passed
                                if process_tree_result is not None
                                and process_tree_result.executed else None
                            ),
                            process_group_cleanup=(
                                group_result.passed if group_result is not None else None
                            ))
    group_failed = group_result is not None and not group_result.passed
    protected_failed = protected_result is not None and not protected_result.passed
    process_tree_failed = (
        process_tree_result is not None
        and (not process_tree_result.executed or not process_tree_result.passed)
    )
    native_ready = result.ready and not protected_failed and not process_tree_failed
    if (
        not native_ready or group_failed or lease_expiry_failed
        or violation_receipt_failed or observed_command_bounds_failed
    ):
        if not native_ready and isinstance(backend, MacSeatbeltSandbox):
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
        if protected_failed:
            failures.append(f"protected paths: {protected_result.detail}")
        if process_tree_failed:
            failures.append(f"process-tree cleanup: {process_tree_result.detail}")
        if group_failed:
            failures.append(f"process-group cleanup: {group_result.detail}")
        if lease_expiry_failed:
            safe_detail = " ".join(lease_expiry_result.detail.split())[:500]
            failures.append(f"network allowlist expiry: {safe_detail}")
        if violation_receipt_failed:
            failures.append("native seccomp receipt probe: failed")
        if observed_command_bounds_failed:
            failures.append("native observed command bounds probe: failed")
        print(f"::error::{backend.name} native probe failed: {'; '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
