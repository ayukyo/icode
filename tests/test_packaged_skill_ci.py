"""Require installed SKILL tests to use the declared build backend and pins."""

from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD_STEP = 'run: python -m pip install "setuptools>=80"'
CHECKOUT_ENV = {
    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.autocrlf",
    "GIT_CONFIG_VALUE_0": "false",
}


def _job(workflow: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow, re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing CI job: {name}")
    return match.group(1)


class TestPackagedSkillCi(unittest.TestCase):
    def setUp(self) -> None:
        self.ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.provenance = (
            ROOT / ".github/workflows/windows-helper-provenance.yml"
        ).read_text(encoding="utf-8")

    def test_full_suite_installs_declared_build_backend_before_tests(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["build-system"]["requires"], ["setuptools>=80"])
        job = _job(self.ci, "test")
        self.assertIn(BUILD_STEP, job)
        self.assertLess(job.index(BUILD_STEP), job.index("run: python -m unittest\n"))

    def test_readonly_validate_installs_backend_before_preflight(self) -> None:
        job = _job(self.provenance, "validate")
        self.assertIn(BUILD_STEP, job)
        self.assertLess(job.index(BUILD_STEP), job.index("python scripts/preflight.py"))
        self.assertNotIn("id-token:", job)
        self.assertNotIn("attestations:", job)

    def test_native_install_matrix_covers_five_platforms_and_windows312(self) -> None:
        job = _job(self.ci, "packaged-skill-install")
        pairs = re.findall(
            r'- os: ([a-zA-Z0-9.-]+)\n\s+python-version: "([0-9.]+)"', job,
        )
        self.assertEqual(set(pairs), {
            (os_name, "3.11") for os_name in (
                "ubuntu-latest", "macos-latest", "macos-15-intel",
                "windows-latest", "windows-11-arm",
            )
        } | {("windows-latest", "3.12"), ("windows-11-arm", "3.12")})
        self.assertEqual(len(pairs), 7)
        self.assertIn("runs-on: ${{ matrix.os }}", job)
        self.assertIn("fail-fast: false", job)

    def test_installed_suite_requires_backend_and_fixed_source_without_soft_fail(self) -> None:
        job = _job(self.ci, "packaged-skill-install")
        self.assertIn("submodules: recursive", job)
        self.assertIn("persist-credentials: false", job)
        self.assertIn(BUILD_STEP, job)
        command = "run: python -m unittest tests.test_packaged_skill -v"
        self.assertIn(command, job)
        self.assertLess(job.index(BUILD_STEP), job.index(command))
        self.assertNotIn("continue-on-error:", job)
        self.assertNotIn("permissions:", job)
        self.assertNotIn("sudo ", job)

    def test_all_wheel_build_jobs_checkout_pinned_skill(self) -> None:
        for workflow, name in (
            (self.ci, "native-probe"),
            (self.ci, "windows-native-wheel"),
            (self.ci, "windows-bootstrap-wheel"),
            (self.provenance, "sign"),
        ):
            with self.subTest(job=name):
                job = _job(workflow, name)
                first_step = job.split("      - name:")[1]
                self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", first_step)
                self.assertIn("submodules: recursive", first_step)
                self.assertIn("persist-credentials: false", first_step)

    def test_resource_consumers_disable_checkout_conversion_in_command_scope(self) -> None:
        for workflow, name in (
            (self.ci, "test"), (self.ci, "packaged-skill-install"),
            (self.ci, "native-probe"), (self.ci, "windows-native-wheel"),
            (self.ci, "windows-bootstrap-wheel"),
            (self.provenance, "validate"), (self.provenance, "sign"),
        ):
            with self.subTest(job=name):
                first_step = _job(workflow, name).split("      - name:")[1]
                for key, value in CHECKOUT_ENV.items():
                    self.assertIn(f'{key}: "{value}"', first_step)
                self.assertIn("submodules: recursive", first_step)

    def test_real_recursive_checkout_retains_pin_bytes_under_autocrlf_override(self) -> None:
        from icode.skill_resources import SOURCE_COMMIT, SkillResourceError, verify_resources

        def git(*argv: str, env: dict[str, str]) -> None:
            result = subprocess.run(
                ["git", *argv], cwd=ROOT, env=env, capture_output=True,
                encoding="utf-8", timeout=60, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr[-1200:])

        # Preflight runs before commit: exercise the prospective gitlink, not
        # the previous HEAD. CI's clean index yields the committed tree too.
        tree = subprocess.run(
            ["git", "write-tree"], cwd=ROOT, capture_output=True,
            encoding="utf-8", timeout=10, check=False,
        )
        self.assertEqual(tree.returncode, 0, tree.stderr[-1200:])
        index_tree = tree.stdout.strip()

        with tempfile.TemporaryDirectory(prefix="icode-checkout-bytes-") as temporary:
            base = Path(temporary).resolve()
            for conversion in ("true", "false"):
                with self.subTest(autocrlf=conversion):
                    checkout = base / conversion
                    env = {**os.environ, **CHECKOUT_ENV, "GIT_CONFIG_VALUE_0": conversion}
                    git("clone", "--shared", "--no-checkout", "--", str(ROOT),
                        str(checkout), env=env)
                    git("-C", str(checkout), "config", "core.autocrlf", "true", env=env)
                    git("-C", str(checkout), "config", "submodule.vendor/icode-skill.url",
                        str(ROOT / "vendor/icode-skill"), env=env)
                    git("-C", str(checkout), "checkout", "--detach", "HEAD", env=env)
                    git("-C", str(checkout), "read-tree", "--reset", "-u",
                        index_tree, env=env)
                    # Local-only temporary clone; file transport is not enabled
                    # in product, CI checkout, user/global config, or the source.
                    git("-c", "protocol.file.allow=always", "-C", str(checkout),
                        "submodule", "update", "--init", "--recursive", env=env)
                    vendor = checkout / "vendor/icode-skill"
                    pin = subprocess.run(
                        ["git", "-C", str(vendor), "rev-parse", "HEAD"],
                        env=env, capture_output=True, encoding="utf-8", timeout=10,
                        check=False,
                    )
                    self.assertEqual(pin.returncode, 0)
                    self.assertEqual(pin.stdout.strip(), SOURCE_COMMIT)
                    raw = (vendor / "tools/icode_control.py").read_bytes()
                    if conversion == "true":
                        self.assertIn(b"\r\n", raw)
                        with self.assertRaises(SkillResourceError):
                            verify_resources(vendor)
                    else:
                        self.assertEqual(raw, (ROOT / "vendor/icode-skill/tools/icode_control.py").read_bytes())
                        self.assertEqual(verify_resources(vendor), vendor)


if __name__ == "__main__":
    unittest.main()
