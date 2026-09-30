"""CI 工作流必须显式运行安全边界原生回归。"""

from __future__ import annotations

from pathlib import Path
import unittest


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
