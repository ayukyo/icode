"""Python 3.12 support policy without reducing platform or security coverage."""

from pathlib import Path
import ast
import hashlib
import re
import textwrap
import tomllib
import unittest

from tests.test_packaged_skill_ci import _job


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


class PythonRuntimePolicyTests(unittest.TestCase):
    def test_package_minimum_is_python312(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["requires-python"], ">=3.12")

    def test_current_installation_guidance_uses_python312(self):
        for name in ("README.md", "README.zh-CN.md", "site/index.html", "site/en/index.html"):
            with self.subTest(path=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn("Python 3.12+", text)
                self.assertNotIn("Python 3.11", text)
                self.assertNotIn("Python-3.11", text)

    def test_windows_binding_build_requires_python312(self):
        text = (ROOT / "native/windows/CMakeLists.txt").read_text(encoding="utf-8")
        versions = re.findall(r"find_package\(Python3\s+([0-9.]+)\s+REQUIRED COMPONENTS Interpreter\)", text)
        self.assertEqual(versions, ["3.12"])

    def test_every_host_workflow_python_declaration_is_312_or_its_matrix(self):
        paths = sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")))
        self.assertTrue(paths)
        declarations = 0
        for path in paths:
            values = re.findall(r"^\s+python-version:\s*(.*?)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
            declarations += len(values)
            for value in values:
                with self.subTest(workflow=path.name, value=value):
                    self.assertIn(value, ('"3.12"', '["3.12"]', '${{ matrix.python-version }}'))
        self.assertGreater(declarations, 0)

    def test_install_workspace_and_provenance_keep_exact_platforms_without_duplicates(self):
        ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        provenance = (WORKFLOWS / "windows-helper-provenance.yml").read_text(encoding="utf-8")
        expected = (
            (ci, "packaged-skill-install", {"ubuntu-latest", "macos-latest", "macos-15-intel", "windows-latest", "windows-11-arm"}),
            (ci, "workspace-platforms", {"ubuntu-latest", "macos-latest", "windows-latest", "windows-11-arm"}),
            (provenance, "sign", {"windows-latest", "windows-11-arm"}),
        )
        for workflow, name, platforms in expected:
            with self.subTest(job=name):
                entries = re.findall(r"^          - os: ([\w.-]+)\n((?:            .*\n)*)", _job(workflow, name), re.MULTILINE)
                actual = []
                for platform, body in entries:
                    versions = re.findall(r'^            python-version: "([0-9.]+)"$', body, re.MULTILINE)
                    self.assertEqual(versions, ["3.12"])
                    actual.append((platform, versions[0]))
                self.assertEqual(set(actual), {(platform, "3.12") for platform in platforms})
                self.assertEqual(len(actual), len(platforms))
        for name in ("macos-m0a1-finite", "macos-m0a2-vectors"):
            with self.subTest(job=name):
                pairs = re.findall(r"- os: ([\w.-]+)\n            arch: ([\w_]+)", _job(ci, name))
                self.assertEqual(set(pairs), {("macos-latest", "arm64"), ("macos-15-intel", "x86_64")})
                self.assertEqual(len(pairs), 2)
        sign = _job(provenance, "sign")
        for platform, cmake, helper in (("windows-latest", "x64", "x64"), ("windows-11-arm", "ARM64", "arm64")):
            self.assertIn(f"- os: {platform}\n            cmake-architecture: {cmake}\n            helper-architecture: {helper}\n            python-version: \"3.12\"", sign)

    def test_existing_ci_and_provenance_job_identities_are_preserved(self):
        expected = {
            "ci.yml": {
                "test", "packaged-skill-install", "verification-output-lifecycle",
                "windows-verification-lifecycle-python312", "container-reviewer",
                "workspace-platforms", "windows-runner-pipe", "windows-tree-snapshot-probe",
                "native-probe", "windows-job-probe", "windows-reviewer-snapshot-probe",
                "windows-appcontainer-read-handle-probe", "windows-standard-user-token-probe",
                "windows-appcontainer-diagnostics", "windows-native-wheel", "windows-bootstrap-wheel",
                "presentation", "macos-m0a1-finite", "macos-m0a2-vectors",
            },
            "windows-helper-provenance.yml": {"validate", "sign"},
        }
        for name, jobs in expected.items():
            with self.subTest(workflow=name):
                text = (WORKFLOWS / name).read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
                found = re.findall(r"^  ([\w-]+):$", text, re.MULTILINE)
                self.assertEqual(set(found), jobs)
                self.assertEqual(len(found), len(jobs))

    def test_version_migration_preserves_commands_and_security_policies(self):
        # Freeze reviewed workflow behavior, excluding version/matrix declarations
        # and setup labels. The CI digest includes the three readonly-admin steps
        # added in 4fff535; removing their reviewed block exactly restores d954840.
        # Security policies and the provenance command contract stay unchanged.
        # No native command runs in this test.
        expected = {
            "ci.yml": (
                "87e5bedb30438cd74741713bded58e51107da0f443bc245875d95cef7ad99e47",
                "47953a7c8cdb502d0ced29e9875ecb0964d5a25a3c033dde9b5f93e39c2660bc",
            ),
            "windows-helper-provenance.yml": (
                "5dbce0bb10c4e9dc55a196a8ebf43b8aa423a3fa81ef7cdbc4ef70f20805570a",
                "06fb33eb4b3a7fb42101f5b95a24abb2ca48eff2347d21faaad0fcf1de17eeaa",
            ),
        }
        for name, digests in expected.items():
            text = (WORKFLOWS / name).read_text(encoding="utf-8")
            commands = re.findall(r"^        run:.*(?:\n(?:          .*|[ \t]*$))*", text, re.MULTILINE)
            policies = re.findall(r"^(?:[ ]{0,8}(?:permissions|contents|id-token|attestations|timeout-minutes|if|needs|fail-fast|runs-on):.*)$", text, re.MULTILINE)
            for label, values, expected_digest in zip(("commands", "policies"), (commands, policies), digests):
                with self.subTest(workflow=name, contract=label):
                    self.assertEqual(hashlib.sha256("\n".join(values).encode()).hexdigest(), expected_digest)

    def test_signer_required_counts_match_actual_test_selections(self):
        # Parse the real embedded gate, but never execute its Windows API probe.
        job = _job((WORKFLOWS / "windows-helper-provenance.yml").read_text(
            encoding="utf-8"), "sign")
        block = job.split("          @'\n", 1)[1].split(
            "          '@ | python -B -\n", 1)[0]
        tree = ast.parse(textwrap.dedent(block))
        selections = [ast.literal_eval(node.value) for node in tree.body
                      if isinstance(node, ast.Assign) and any(
                          isinstance(target, ast.Name) and target.id == "selections"
                          for target in node.targets)]
        self.assertEqual(len(selections), 1)
        suites = [unittest.defaultTestLoader.loadTestsFromName(name)
                  for name in selections[0]]
        counts = tuple(suite.countTestCases() for suite in suites)
        declared = [ast.literal_eval(node.args[0].comparators[0])
                    for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == "require"
                    and len(node.args) == 1 and isinstance(node.args[0], ast.Compare)
                    and isinstance(node.args[0].left, ast.Call)
                    and isinstance(node.args[0].left.func, ast.Name)
                    and node.args[0].left.func.id == "tuple"]
        self.assertEqual(declared, [counts])
        total = sum(counts)
        self.assertEqual(block.count(
            f"require(len(ids) == {total} and len(set(ids)) == {total})"), 1)


if __name__ == "__main__":
    unittest.main()
