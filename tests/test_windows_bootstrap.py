"""Bootstrap logic tests; host compilation is not Windows isolation evidence."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts import run_windows_wheel_ci as wheel_ci


SOURCE = Path(__file__).resolve().parents[1] / "native/windows/icode_windows_bootstrap.c"


class TestWindowsBootstrap(unittest.TestCase):
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
