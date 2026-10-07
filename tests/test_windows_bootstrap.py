"""Bootstrap logic tests; host compilation is not Windows isolation evidence."""

from __future__ import annotations

import json
import inspect
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts import run_windows_wheel_ci as wheel_ci


SOURCE = Path(__file__).resolve().parents[1] / "native/windows/icode_windows_bootstrap.c"


class TestWindowsBootstrap(unittest.TestCase):
    def test_provenance_ci_binds_exact_workflow_ref_commit_and_hosted_runner(self) -> None:
        builder = getattr(wheel_ci, "_provenance_verify_argv", None)
        self.assertIsNotNone(builder, "CI cryptographic verification policy is missing")
        sha = "a" * 40
        argv = builder(Path("helper.exe"), Path("proof.json"), sha)
        self.assertEqual(argv[:3], ["gh", "attestation", "verify"])
        expected = {
            "--bundle": "proof.json", "--repo": "ayukyo/icode",
            "--cert-identity": "https://github.com/ayukyo/icode/.github/workflows/windows-helper-provenance.yml@refs/heads/main",
            "--cert-oidc-issuer": "https://token.actions.githubusercontent.com",
            "--source-ref": "refs/heads/main", "--source-digest": sha,
            "--signer-digest": sha, "--predicate-type": "https://slsa.dev/provenance/v1",
        }
        for option, value in expected.items():
            self.assertEqual(argv[argv.index(option) + 1], value)
        self.assertIn("--deny-self-hosted-runners", argv)
        for invalid in ("", "main", "b" * 39, "B" * 40, "b" * 40 + "\n"):
            with self.subTest(sha=invalid), self.assertRaises(ValueError):
                builder(Path("helper.exe"), Path("proof.json"), invalid)

    def test_provenance_workflow_privileges_and_artifact_publication_are_scoped(self) -> None:
        path = SOURCE.parents[2] / ".github/workflows/windows-helper-provenance.yml"
        self.assertTrue(path.is_file(), "dedicated provenance workflow is missing")
        text = path.read_text(encoding="utf-8")
        header, _, jobs = text.partition("\njobs:\n")
        self.assertIn("branches: [main]", header)
        self.assertNotIn("pull_request", header)
        self.assertNotIn("workflow_dispatch", header)
        self.assertNotIn("id-token: write", header)
        self.assertNotIn("attestations: write", header)
        guard, _, signing = jobs.partition("\n  sign:\n")
        self.assertIn("python scripts/preflight.py", guard)
        self.assertNotIn("id-token: write", guard)
        self.assertIn("needs: validate", signing)
        for token in ("github.repository == 'ayukyo/icode'", "github.ref == 'refs/heads/main'",
                      "github.event_name == 'push'", "id-token: write", "attestations: write",
                      "push-to-registry: false", "create-storage-record: false",
                      "--provenance-bundle", "--wheel-output", "--parallel 1",
                      "if-no-files-found: error"):
            self.assertIn(token, signing)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("artifact-metadata: write", text)
        self.assertEqual(text.count("id-token: write"), 1)
        self.assertEqual(text.count("attestations: write"), 1)
        self.assertLess(signing.index("uses: actions/attest@"),
                        signing.index("--provenance-bundle"))

    def test_signed_runner_clears_bundle_from_pure_build_and_checks_before_execution(self) -> None:
        source = inspect.getsource(wheel_ci.main)
        self.assertIn("pure_env.pop(_BUNDLE_ENV, None)", source)
        self.assertIn("expected_bundle=proof", source)
        self.assertIn("--provenance-bundle", source)
        self.assertIn("--wheel-output", source)
        self.assertLess(source.index("cryptographically verify installed CI artifact provenance"),
                        source.index("run installed native bootstrap metadata"))
        setup_source = (SOURCE.parents[2] / "setup.py").read_text(encoding="utf-8")
        self.assertIn("provenance_bundle=windows_bundle", setup_source)

    def test_source_distribution_declares_windows_build_sources(self) -> None:
        manifest = SOURCE.parents[2] / "MANIFEST.in"
        self.assertIn("recursive-include native/windows *.c CMakeLists.txt",
                      manifest.read_text(encoding="utf-8"))

    def test_ci_metadata_rejects_wrong_versions_architecture_and_readiness(self) -> None:
        validator = getattr(wheel_ci, "_validate_bootstrap_output", None)
        self.assertIsNotNone(validator, "native CI must verify bounded metadata")
        valid = {
            "helper": "icode-windows-bootstrap", "bootstrap_version": 1,
            "runner_protocol_version": 1, "architecture": "x64",
            "setup_complete": False, "command_execution": False,
            "isolation_ready": False,
        }
        output = json.dumps(valid, separators=(",", ":")) + "\n"
        validator(output, "x64")
        for field, value in (("architecture", "arm64"), ("bootstrap_version", True),
                             ("runner_protocol_version", 2), ("setup_complete", True),
                             ("command_execution", True), ("isolation_ready", True)):
            changed = dict(valid, **{field: value})
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                validator(json.dumps(changed, separators=(",", ":")) + "\n", "x64")
        for bad in ("", output * 2, output + "PRIVATE_EXTRA", "x" * 513,
                    output.replace('"bootstrap_version":1', '"bootstrap_version":1,"bootstrap_version":1')):
            with self.subTest(output_length=len(bad)), self.assertRaises(RuntimeError):
                validator(bad, "x64")

    def test_ci_native_input_cannot_fall_back_to_a_synthetic_fixture(self) -> None:
        reader = getattr(wheel_ci, "_read_native_image", None)
        self.assertIsNotNone(reader, "native CI must require explicit artifact")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            helper = root / "native.exe"
            image = wheel_ci._synthetic_pe(0x8664)
            helper.write_bytes(image)
            self.assertEqual(reader(helper, "x64"), image)
            with self.assertRaises(RuntimeError):
                reader(helper, "arm64")
            with self.assertRaises(OSError):
                reader(root / "missing.exe", "x64")
            helper.write_bytes(b"not PE")
            with self.assertRaises(RuntimeError):
                reader(helper, "x64")
            helper.write_bytes(image)
            alias = root / "alias.exe"
            try:
                alias.symlink_to(helper)
            except OSError:
                return  # Windows standard users may not have symlink permission.
            with self.assertRaises(RuntimeError):
                reader(alias, "x64")

    def test_bootstrap_source_exists(self) -> None:
        self.assertTrue(SOURCE.is_file(), "real native bootstrap source is missing")

    @unittest.skipUnless(shutil.which("cc"), "host C compiler unavailable")
    def test_fixed_metadata_and_unsupported_commands(self) -> None:
        self.assertTrue(SOURCE.is_file(), "real native bootstrap source is missing")
        for arch, define in (("x64", "_M_X64"), ("arm64", "_M_ARM64")):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as raw:
                binary = Path(raw) / "bootstrap-logic-test"
                compiled = subprocess.run(
                    [shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                     "-D_WIN32", f"-D{define}", str(SOURCE), "-o", str(binary)],
                    capture_output=True, timeout=30, check=False,
                )
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                result = subprocess.run([str(binary), "--version-json"],
                                        capture_output=True, timeout=5, check=False)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                self.assertLess(len(result.stdout), 512)
                self.assertEqual(json.loads(result.stdout), {
                    "helper": "icode-windows-bootstrap", "bootstrap_version": 1,
                    "runner_protocol_version": 1, "architecture": arch,
                    "setup_complete": False, "command_execution": False,
                    "isolation_ready": False,
                })
                for args in ([], ["setup"], ["spawn", "PRIVATE_COMMAND"],
                             ["--version-json", "PRIVATE_ARGUMENT"], ["--help"]):
                    rejected = subprocess.run([str(binary), *args],
                                              capture_output=True, timeout=5, check=False)
                    self.assertEqual(rejected.returncode, 78, args)
                    self.assertEqual(rejected.stdout, b"")
                    self.assertEqual(rejected.stderr,
                                     b"icode_windows_bootstrap: unsupported_operation\n")

    @unittest.skipUnless(shutil.which("cc"), "host C compiler unavailable")
    def test_unsupported_architecture_is_a_build_error(self) -> None:
        self.assertTrue(SOURCE.is_file(), "real native bootstrap source is missing")
        with tempfile.TemporaryDirectory() as raw:
            result = subprocess.run(
                [shutil.which("cc"), "-std=c11", "-D_WIN32", "-U__x86_64__", "-U__aarch64__",
                 "-c", str(SOURCE), "-o", str(Path(raw) / "unsupported.o")],
                capture_output=True, timeout=30, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"unsupported_windows_architecture", result.stderr)
