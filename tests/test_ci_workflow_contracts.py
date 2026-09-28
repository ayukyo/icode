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
            """      - name: Allow Bubblewrap user namespaces under Ubuntu AppArmor
        if: runner.os == 'Linux'
        shell: bash
        run: |
          if [[ -r /proc/sys/kernel/apparmor_restrict_unprivileged_userns ]] \\
            && [[ "$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns)" == "1" ]]; then
            sudo apparmor_parser -r .github/apparmor/bwrap-userns.profile
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

        apparmor_profile = (
            repository_root / ".github/apparmor/bwrap-userns.profile"
        ).read_text(encoding="utf-8")
        self.assertIn("profile /usr/bin/bwrap flags=(unconfined)", apparmor_profile)
        self.assertIn("userns,", apparmor_profile)
        self.assertEqual(
            apparmor_profile,
            "include <tunables/global>\n\n"
            "profile /usr/bin/bwrap flags=(unconfined) {\n"
            "    userns,\n"
            "}\n",
        )
        self.assertNotIn("sysctl -w", workflow)


if __name__ == "__main__":
    unittest.main()
