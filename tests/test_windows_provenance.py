"""Python resource/wire adapter tests, not cryptographic verification evidence.

Synthetic PE files are never executed. Real signature tests live in the Go
module and the installed native Windows CI; mocking transport is not a crypto
positive or a product launch grant.
"""

from __future__ import annotations

from contextlib import ExitStack
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from icode import native_helper
from tests.test_windows_wheel_packaging import _pe_image


class TestWindowsProvenanceAdapter(unittest.TestCase):
    def _api(self):
        self.assertIsNotNone(importlib.util.find_spec("icode.windows_provenance"),
                             "packaged provenance adapter is missing")
        return importlib.import_module("icode.windows_provenance")

    def _resources(self, root: Path, arch: str = "x64") -> tuple[Path, Path, dict]:
        native = root / "native"
        native.mkdir()
        image = _pe_image({"x64": 0x8664, "arm64": 0xAA64}[arch])
        helper = native / f"icode-sandbox-windows-{arch}.exe"
        verifier = native / f"icode-provenance-windows-{arch}.exe"
        for binary in (helper, verifier):
            binary.write_bytes(image)
            Path(str(binary) + ".sha256").write_text(
                hashlib.sha256(image).hexdigest() + "\n", encoding="ascii")
        Path(str(helper) + ".sigstore.json").write_bytes(b"unsigned transport fixture")
        release = {"schema_version": 1, "source_sha": "a" * 40, "architecture": arch}
        (native / "icode-provenance-release.json").write_text(json.dumps(release), encoding="utf-8")
        (native / "icode-provenance-NOTICES.txt").write_text("License transport fixture\n", encoding="utf-8")
        receipt = dict(release, provenance_verified=True, launch_authorized=False,
                       artifact_sha256=hashlib.sha256(image).hexdigest())
        return helper, verifier, receipt

    def _context(self, api, root: Path, arch: str = "x64") -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch.object(api, "__file__", str(root / "windows_provenance.py")))
        stack.enter_context(patch.object(native_helper, "__file__", str(root / "native_helper.py")))
        stack.enter_context(patch.object(api.sys, "platform", "win32"))
        stack.enter_context(patch.object(api.sysconfig, "get_platform", return_value={
            "x64": "win-amd64", "arm64": "win-arm64"}[arch]))
        return stack

    def test_matching_resource_wire_never_executes_helper_or_grants_launch(self) -> None:
        api = self._api()
        for arch in ("x64", "arm64"):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                helper, verifier, receipt = self._resources(root, arch)
                result = subprocess.CompletedProcess([], 0, json.dumps(receipt).encode() + b"\n", b"")
                with self._context(api, root, arch), patch.object(api.subprocess, "run", return_value=result) as run:
                    self.assertEqual(api.verify_bundled_windows_provenance(), receipt)
                argv = run.call_args.args[0]
                self.assertEqual(Path(argv[0]), verifier)
                self.assertEqual(Path(argv[argv.index("--artifact") + 1]), helper)
                self.assertEqual(argv[argv.index("--source-sha") + 1], "a" * 40)
                self.assertEqual(argv[argv.index("--arch") + 1], arch)
                self.assertFalse(receipt["launch_authorized"])

    def test_wrong_platform_or_architecture_has_no_execution_fallback(self) -> None:
        api = self._api()
        for platform, tag in (("linux", "linux-x86_64"), ("win32", "win32")):
            with self.subTest(platform=platform), patch.object(api.sys, "platform", platform), \
                    patch.object(api.sysconfig, "get_platform", return_value=tag), \
                    patch.object(api.subprocess, "run") as run:
                self.assertIsNone(api.verify_bundled_windows_provenance())
                run.assert_not_called()

    def test_missing_corrupt_mismatched_and_linked_resources_fail_before_subprocess(self) -> None:
        api = self._api()
        for label in ("verifier", "bundle", "release", "notices", "sha", "arch", "empty_proof", "large_proof", "link"):
            with self.subTest(case=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                helper, verifier, _ = self._resources(root)
                if label in ("verifier", "bundle", "release", "notices"):
                    target = {"verifier": verifier, "bundle": Path(str(helper) + ".sigstore.json"),
                              "release": verifier.parent / "icode-provenance-release.json",
                              "notices": verifier.parent / "icode-provenance-NOTICES.txt"}[label]
                    target.unlink()
                elif label == "sha":
                    Path(str(verifier) + ".sha256").write_text("0" * 64)
                elif label == "arch":
                    verifier.write_bytes(_pe_image(0xAA64))
                    Path(str(verifier) + ".sha256").write_text(hashlib.sha256(verifier.read_bytes()).hexdigest())
                elif label in ("empty_proof", "large_proof"):
                    Path(str(helper) + ".sigstore.json").write_bytes(b"" if label == "empty_proof" else b"x" * (2 * 1024 * 1024 + 1))
                else:
                    original = verifier.with_suffix(".original")
                    verifier.rename(original)
                    try:
                        verifier.symlink_to(original)
                    except OSError:
                        continue
                with self._context(api, root), patch.object(api.subprocess, "run") as run:
                    self.assertIsNone(api.verify_bundled_windows_provenance())
                    run.assert_not_called()

    def test_release_metadata_is_bounded_exact_and_not_caller_controlled(self) -> None:
        api = self._api()
        for bad in (b"", b"x" * 1025, b'{"schema_version":1,"source_sha":"main","architecture":"x64"}',
                    b'{"schema_version":true,"source_sha":"' + b"a" * 40 + b'","architecture":"x64"}',
                    b'{"schema_version":1,"source_sha":"' + b"a" * 40 + b'","architecture":"arm64"}',
                    b'{"schema_version":1,"schema_version":1,"source_sha":"' + b"a" * 40 + b'","architecture":"x64"}'):
            with self.subTest(length=len(bad)), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                _, verifier, _ = self._resources(root)
                (verifier.parent / "icode-provenance-release.json").write_bytes(bad)
                with self._context(api, root), patch.object(api.subprocess, "run") as run:
                    self.assertIsNone(api.verify_bundled_windows_provenance())
                    run.assert_not_called()

    def test_malformed_or_failed_wire_does_not_become_verified(self) -> None:
        api = self._api()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, _, receipt = self._resources(root)
            payloads = [b"", b"x" * 513, json.dumps(receipt).encode() + b"\nPRIVATE_TRAILING",
                        json.dumps(dict(receipt, launch_authorized=True)).encode(),
                        json.dumps(dict(receipt, provenance_verified=1)).encode(),
                        json.dumps(dict(receipt, artifact_sha256="0" * 64)).encode(),
                        json.dumps(dict(receipt, source_sha="b" * 40)).encode(),
                        json.dumps(dict(receipt, extra="PRIVATE_EXTRA")).encode(),
                        json.dumps(receipt).encode().replace(b'"schema_version": 1', b'"schema_version": 1,"schema_version": 1')]
            for stdout in payloads:
                with self.subTest(stdout_length=len(stdout)), self._context(api, root), \
                        patch.object(api.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout, b"")):
                    self.assertIsNone(api.verify_bundled_windows_provenance())
            for outcome in (subprocess.CompletedProcess([], 78, b"PRIVATE_OUTPUT", b"PRIVATE_ERROR"),
                            subprocess.CompletedProcess([], 0, json.dumps(receipt).encode(), b"PRIVATE_ERROR"),
                            OSError("PRIVATE_PATH"), subprocess.TimeoutExpired("PRIVATE_COMMAND", 30)):
                with self.subTest(outcome=type(outcome).__name__), self._context(api, root):
                    args = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                    with patch.object(api.subprocess, "run", **args):
                        self.assertIsNone(api.verify_bundled_windows_provenance())
