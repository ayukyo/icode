"""CI 工作流必须显式运行安全边界原生回归。"""

from __future__ import annotations

from pathlib import Path
import unittest


class TestContainerReviewerBoundaryCi(unittest.TestCase):
    def test_docker和Podman必须运行原生Reviewer隔离探针(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        required_contracts = (
            "  container-reviewer:\n",
            "    name: R3 container Reviewer (${{ matrix.runtime }})\n",
            "        runtime: [docker, podman]\n",
            '      ICODE_RUN_CONTAINER_REVIEWER_PROBE: "1"\n',
            "      ICODE_CONTAINER_REVIEWER_RUNTIME: ${{ matrix.runtime }}\n",
            "          sudo apt-get install --yes podman\n",
            "          docker pull python:3.13-slim\n",
            "          podman pull docker.io/library/python:3.13-slim\n",
            "        run: python -m unittest tests.test_isolation.TestSandboxWrapping.test_容器_Reviewer原生只读与账本遮蔽边界 -v\n",
        )
        for contract in required_contracts:
            with self.subTest(contract=contract.splitlines()[0]):
                self.assertIn(contract, workflow)

        install = workflow.index("sudo apt-get install --yes podman")
        pull = workflow.index("docker pull python:3.13-slim")
        probe = workflow.index(
            "tests.test_isolation.TestSandboxWrapping.test_容器_Reviewer原生只读与账本遮蔽边界"
        )
        self.assertLess(install, pull)
        self.assertLess(pull, probe)


class TestLinuxReviewerBoundaryCi(unittest.TestCase):
    def test_linux_native_matrix_requires_real_bubblewrap_reviewer_probe(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        required_steps = (
            """      - name: Install Bubblewrap for Linux Reviewer probes
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install --yes bubblewrap
          command -v bwrap
""",
            """      - name: Load the pinned Bubblewrap AppArmor profile when required
        if: runner.os == 'Linux'
        shell: bash
        run: |
          if [[ ! -r /proc/sys/kernel/apparmor_restrict_unprivileged_userns ]] \\
            || [[ "$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns)" != "1" ]]; then
            echo "::notice::AppArmor user namespace restriction is not enabled"
            exit 0
          fi
          profile_revision='b0eb95457bc2de401920308869d016e696c73664'
          profile_sha256='11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9'
          profile_path="${RUNNER_TEMP}/bwrap-userns-restrict"
          profile_url="https://gitlab.com/apparmor/apparmor/-/raw/${profile_revision}/profiles/apparmor/profiles/extras/bwrap-userns-restrict"
          curl --fail --location --silent --show-error "${profile_url}" --output "${profile_path}"
          printf '%s  %s\\n' "${profile_sha256}" "${profile_path}" | sha256sum --check
          sudo apparmor_parser --replace "${profile_path}"
          active_profiles='/sys/kernel/security/apparmor/profiles'
          if ! sudo grep -Fq 'bwrap (enforce)' "${active_profiles}"; then
            sudo cat "${active_profiles}"
            echo "::error::Pinned bwrap AppArmor profile was not loaded"
            exit 1
          fi
          bwrap_args=(--die-with-parent --unshare-user --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --proc /proc --dev /dev)
          if [[ -e /lib64 ]]; then
            bwrap_args+=(--ro-bind /lib64 /lib64)
          fi
          child_profile="$(bwrap "${bwrap_args[@]}" -- /bin/cat /proc/self/attr/current)"
          if [[ "${child_profile}" != *unpriv_bwrap* ]]; then
            echo "::error::Bubblewrap child did not enter the restricted AppArmor profile: ${child_profile}"
            exit 1
          fi
""",
            """      - name: Verify Linux Reviewer ToolContext boundary
        if: runner.os == 'Linux'
        run: python -m unittest tests.test_isolation.TestSandboxWrapping.test_bwrap_只读Reviewer实际隐藏工单账本且阻断所有写入 -v
""",
            """      - name: Verify Linux read-only Reviewer OS boundary
        if: runner.os == 'Linux'
        run: python -m unittest tests.test_isolation.TestSandboxWrapping.test_bwrap_只读Reviewer真实隐藏账本且阻断工作区内外写入 -v
""",
        )

        for required_step in required_steps:
            with self.subTest(step=required_step.splitlines()[0].strip()):
                self.assertIn(
                    required_step,
                    workflow,
                    "Linux native-probe matrix must run each Bubblewrap Reviewer gate explicitly",
                )

        ordered_step_names = (
            "      - name: Install Bubblewrap for Linux Reviewer probes",
            "      - name: Load the pinned Bubblewrap AppArmor profile when required",
            "      - name: Verify Linux Reviewer ToolContext boundary",
            "      - name: Verify Linux read-only Reviewer OS boundary",
        )
        step_positions = tuple(workflow.index(name) for name in ordered_step_names)
        self.assertEqual(
            step_positions,
            tuple(sorted(step_positions)),
            "Bubblewrap must be installed and its active AppArmor child profile verified before Reviewer probes",
        )

        self.assertIn(
            "profile_revision='b0eb95457bc2de401920308869d016e696c73664'",
            workflow,
        )
        self.assertIn(
            "profile_sha256='11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9'",
            workflow,
        )
        self.assertIn("sha256sum --check", workflow)
        self.assertIn("sudo apparmor_parser --replace", workflow)
        self.assertIn("bwrap (enforce)", workflow)
        self.assertIn("*unpriv_bwrap*", workflow)
        self.assertNotIn("flags=(unconfined)", workflow)
        self.assertFalse(
            (repository_root / ".github/apparmor/bwrap-userns.profile").exists(),
            "Do not ship the broad unconfined profile with userns permission",
        )
        self.assertNotIn("sysctl -w", workflow)


class TestRetiredAppContainerProbeCi(unittest.TestCase):
    def test_retired_windows_appcontainer_probe_is_opt_in_only(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        expected_input = """      run_windows_appcontainer_read_handle_probe:
        description: Run the retired AppContainer read-handle experiment (diagnostic only)
        required: false
        default: false
        type: boolean
"""
        expected_job_gate = """  windows-appcontainer-read-handle-probe:
    if: github.event_name == 'workflow_dispatch' && inputs.run_windows_appcontainer_read_handle_probe
"""

        self.assertIn(expected_input, workflow)
        self.assertIn(expected_job_gate, workflow)


class TestWindowsReviewerSnapshotProbeCi(unittest.TestCase):
    def test_windows_x64_and_arm64_run_reviewer_snapshot_candidate_as_required_job(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        required_job = """  windows-reviewer-snapshot-probe:
    name: R3 Windows Reviewer snapshot candidate (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 25
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            python-architecture: x64
            cmake-architecture: x64
          - os: windows-11-arm
            python-architecture: arm64
            cmake-architecture: ARM64
    env:
      PYTHONPATH: src
      PYTHONIOENCODING: utf-8
      PYTHONUTF8: "1"
      ICODE_DIAGNOSTIC_RUNTIME_STAGING: "true"
      ICODE_DIAGNOSTIC_REVIEWER_SNAPSHOT: "true"
"""
        self.assertIn(required_job, workflow)
        self.assertIn(
            "              'tests.test_windows_appcontainer.TestWindowsAppContainer.test_Reviewer快照AppContainer只读边界与Job清理',\n",
            workflow,
        )
        self.assertNotIn(
            "  windows-reviewer-snapshot-probe:\n    if:", workflow,
            "the Windows Reviewer candidate must not silently skip on push CI",
        )
        self.assertIn(
            "      - name: Run Reviewer snapshot probe as temporary standard user\n",
            workflow,
        )
        candidate_job = workflow.split(
            "  windows-reviewer-snapshot-probe:\n", 1,
        )[1].split("\n  windows-appcontainer-read-handle-probe:", 1)[0]
        native_observer_contract = (
            "      - name: Build and self-test IPv6 loopback WFP observer\n"
            "        shell: pwsh\n"
        )
        self.assertIn(native_observer_contract, candidate_job)
        for native_requirement in (
            "cmake -S native/windows -B $buildDirectory -A '${{ matrix.cmake-architecture }}'",
            "cmake --build $buildDirectory --config Release --parallel 1",
            "icode-wfp-event-probe.exe",
            "--self-test",
            "$env:ICODE_DIAGNOSTIC_WFP_PROBE_PATH = $wfpProbeForUser",
            "Copy-Item -LiteralPath $env:ICODE_DIAGNOSTIC_WFP_PROBE_BUILD",
        ):
            with self.subTest(requirement=native_requirement):
                self.assertIn(native_requirement, candidate_job)
        abi_probe = (
            "      - name: Cross-check Windows SDK WFP ABI (x64/ARM64)\n"
            "        run: python -m unittest tests.test_windows_wfp_abi.TestWindowsWfpAbi -v\n"
        )
        self.assertIn(abi_probe, candidate_job)
        self.assertLess(
            candidate_job.index(abi_probe),
            candidate_job.index("      - name: Run Reviewer snapshot probe as temporary standard user\n"),
        )
        runner_observer_probe = (
            "      - name: Probe WFP Subscribe2 access as runner identity\n"
            "        shell: pwsh\n"
        )
        self.assertIn(runner_observer_probe, candidate_job)
        runner_observer_step = candidate_job.split(
            runner_observer_probe, 1,
        )[1].split("\n      - name:", 1)[0]
        for runner_observer_requirement in (
            "[IO.Path]::GetTempPath()",
            "--probe-runner-subscription",
            "$observerSetupStage = 'unavailable'",
            "runner_wfp_observer_setup=$observerSetupStage",
            "profile_create_failed",
            "profile_sid_invalid",
            "profile_cleanup_failed",
            "sid_derive_failed",
            "engine_open_failed",
            "subscribe_failed",
            "subscription_ready",
            "runner_wfp_observer_helper_exit_code=$observerHelperExitCode",
            "if ($observerProcess.ExitCode -eq 2)",
            "$observerSetupStage = 'profile_cleanup_failed'",
            "elseif ($observerProcess.ExitCode -eq 3)",
            "$observerSetupStage = 'invalid_arguments'",
            "elseif ($observerProcess.ExitCode -eq 4)",
            "$observerSetupStage = 'invalid_profile_name'",
            "elseif ($observerProcess.ExitCode -eq 5)",
            "$observerSetupStage = 'invalid_port'",
            "elseif ($observerProcess.ExitCode -eq 6)",
            "$observerSetupStage = 'invalid_paths'",
            "elseif ($observerProcess.ExitCode -eq 7)",
            "$observerSetupStage = 'probe_path_full_path_failed'",
            "elseif ($observerProcess.ExitCode -eq 8)",
            "$observerSetupStage = 'probe_path_leaf_name_mismatch'",
            "elseif ($observerProcess.ExitCode -eq 9)",
            "$observerSetupStage = 'probe_path_temp_root_rejected'",
            "elseif ($observerProcess.ExitCode -eq 10)",
            "$observerSetupStage = 'probe_path_parent_mismatch'",
            "elseif ($observerProcess.ExitCode -eq 11)",
            "$observerSetupStage = 'probe_path_destination_not_missing'",
            "Length -le 64",
            "switch -Exact -CaseSensitive",
            "$observerProcess.WaitForExit(5000)",
            "$observerStopPath",
            "subscription_return_code",
            "runner_wfp_observer_permission_probe=",
            "observer_permission_probe_cleanup_timeout",
        ):
            with self.subTest(requirement=runner_observer_requirement):
                self.assertIn(runner_observer_requirement, runner_observer_step)
        for forbidden_mutation in (
            "CreateAppContainerProfile",
            "DeleteAppContainerProfile",
            "FwpmEngineSetOption0",
            "FwpmFilterAdd0",
            "FwpmFilterDeleteByKey0",
            "Add-LocalGroupMember",
            "-Verb RunAs",
            "-Credential",
        ):
            with self.subTest(forbidden_mutation=forbidden_mutation):
                self.assertNotIn(forbidden_mutation, runner_observer_step)
        self.assertLess(
            candidate_job.index(runner_observer_probe),
            candidate_job.index(
                "      - name: Run Reviewer snapshot probe as temporary standard user\n",
            ),
        )
        for standard_user_contract in (
            "architecture: ${{ matrix.python-architecture }}",
            "New-LocalUser -Name $accountName",
            "Get-LocalGroupMember -Group 'Administrators'",
            "Start-Process -FilePath $python -ArgumentList $arguments `\n              -Credential $credential -LoadUserProfile",
            "Remove-LocalUser -Name $accountName",
        ):
            with self.subTest(contract=standard_user_contract.splitlines()[0]):
                self.assertIn(standard_user_contract, candidate_job)
        for profile_contract in (
            '$accountName = "icodeprobe_$suffix"',
            "if ($accountName.Length -gt 20)",
            "Get-CimInstance -ClassName Win32_UserProfile -Filter",
            "$env:USERPROFILE = $profilePath",
            "$env:HOME = $profilePath",
            "$env:RUNNER_TEMP = $probeRoot",
            "icacls.exe $probeRoot /grant",
        ):
            with self.subTest(contract=profile_contract):
                self.assertIn(profile_contract, candidate_job)
        self.assertNotIn("$env:USERPROFILE = $probeRoot", candidate_job)
        self.assertNotIn("-UseNewEnvironment", candidate_job)

    def test_required_native_probe_fails_closed_if_setup_python_uses_a_venv(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        test_source = (repository_root / "tests/test_windows_appcontainer.py").read_text(
            encoding="utf-8",
        )
        self.assertIn(
            'self.fail("CI Python must be a base interpreter for disposable runtime staging")',
            test_source,
        )
        self.assertNotIn(
            'self.skipTest("CI Python must be a base interpreter for disposable runtime staging")',
            test_source,
        )

    def test_native_dacl_probe_requests_write_dac_and_has_an_allowed_control(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        appcontainer_tests = (repository_root / "tests/test_windows_appcontainer.py").read_text(
            encoding="utf-8",
        )
        for required_probe in (
            "handle=kernel.CreateFileW(str(path),0x00060000,",
            "dacl_write_dac_denied",
            "dacl_control_verified",
            "SetSecurityInfo(",
        ):
            with self.subTest(probe=required_probe):
                self.assertIn(required_probe, appcontainer_tests)


class TestWindowsStandardUserSqosProbeCi(unittest.TestCase):
    def test_sqos_probe_is_a_separate_opt_in_on_the_existing_manual_job(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        expected_input = """      run_windows_standard_user_sqos_diagnostic:
        description: Compare default SQOS only after the temporary standard-user pipe open is denied
        required: false
        default: false
        type: boolean
"""
        expected_job = """  windows-standard-user-token-probe:
    if: github.event_name == 'workflow_dispatch' && inputs.run_windows_standard_user_token_probe
    name: Standard-user restricted token probe (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 10
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            python-architecture: x64
          - os: windows-11-arm
            python-architecture: arm64
    env:
      ICODE_R2_SQOS_DIAGNOSTIC: ${{ inputs.run_windows_standard_user_sqos_diagnostic }}
"""

        self.assertIn(expected_input, workflow)
        self.assertIn(expected_job, workflow)


class TestWindowsWorktreeTreeOidCi(unittest.TestCase):
    def test_native_windows_jobs_run_production_worktree_tree_oid_contract(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        required_step = """      - name: Verify production Windows snapshots and Git tree OID
        run: python scripts/run_windows_tree_ci.py
        env:
          ICODE_REQUIRE_WINDOWS_NATIVE_SYMLINKS: "1"
"""

        self.assertIn(required_step, workflow)


class TestCrossPlatformWorkspaceEvidenceCi(unittest.TestCase):
    def test_workspace_matrix_includes_windows_arm64_for_R3_receipt_roundtrip(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        required_matrix = """  workspace-platforms:
    name: R2.1 workspace (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest, windows-11-arm]
"""
        self.assertIn(required_matrix, workflow)


class TestWindowsRunnerPipeNativeCi(unittest.TestCase):
    def test_authenticated_pipe_round_trip_runs_on_x64_and_arm64(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        workflow = (repository_root / ".github/workflows/ci.yml").read_text(
            encoding="utf-8",
        )
        expected_job = """  windows-runner-pipe:
    name: R2 authenticated runner pipe (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 5
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, windows-11-arm]
"""
        self.assertIn(expected_job, workflow)
        self.assertIn(
            "run: python -m unittest tests.test_windows_runner_pipe.TestWindowsRunnerPipeNative -v",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
