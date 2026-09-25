"""Windows helper wheel contract tests; all PE images are synthetic and never executed."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from icode.native_helper import windows_arch_from_platform
from scripts.check_windows_wheel import check as check_windows_wheel
from scripts.windows_wheel import reject_stale_windows_helpers, stage_windows_helper


def _pe_image(machine: int) -> bytes:
    image = bytearray(0x80 + 6)
    image[:2] = b"MZ"
    image[0x3C:0x40] = (0x80).to_bytes(4, "little")
    image[0x80:0x84] = b"PE\0\0"
    image[0x84:0x86] = machine.to_bytes(2, "little")
    return bytes(image)


def _record_line(name: str, content: bytes) -> tuple[str, str, str]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest())
    return name, "sha256=" + digest.rstrip(b"=").decode("ascii"), str(len(content))


def _write_wheel(path: Path, *, arch: str, helper: bytes, manifest: bytes,
                 tag: str | None = None, bad_record: bool = False) -> None:
    platform_tag = {"x64": "win_amd64", "arm64": "win_arm64"}[arch]
    wheel_tag = tag or f"py3-none-{platform_tag}"
    dist_info = "icode_agent-0.1.0.dist-info"
    helper_name = f"icode/native/icode-sandbox-windows-{arch}.exe"
    manifest_name = helper_name + ".sha256"
    wheel_metadata = f"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: false\nTag: {wheel_tag}\n"
    record = [
        _record_line(helper_name, helper),
        _record_line(manifest_name, manifest),
        _record_line(f"{dist_info}/WHEEL", wheel_metadata.encode("utf-8")),
        (f"{dist_info}/RECORD", "", ""),
    ]
    if bad_record:
        record[0] = (record[0][0], "sha256=invalid", record[0][2])
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(record)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(helper_name, helper)
        archive.writestr(manifest_name, manifest)
        archive.writestr(f"{dist_info}/WHEEL", wheel_metadata)
        archive.writestr(f"{dist_info}/RECORD", stream.getvalue())


class TestWindowsWheelPackaging(unittest.TestCase):
    def test_platform_name_maps_only_supported_windows_architectures(self) -> None:
        self.assertEqual(windows_arch_from_platform("win-amd64"), "x64")
        self.assertEqual(windows_arch_from_platform("win_amd64"), "x64")
        self.assertEqual(windows_arch_from_platform("win-arm64"), "arm64")
        self.assertEqual(windows_arch_from_platform("win_arm64"), "arm64")
        for unsupported in ("win32", "win-ia64", "linux-x86_64"):
            with self.subTest(platform=unsupported):
                with self.assertRaises(ValueError):
                    windows_arch_from_platform(unsupported)

    def test_stage_copies_only_matching_PE_and_manifest_into_build_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "helper.exe"
            image = _pe_image(0x8664)
            source.write_bytes(image)
            Path(str(source) + ".sha256").write_text(
                hashlib.sha256(image).hexdigest() + "\n", encoding="ascii",
            )

            helper, manifest = stage_windows_helper(
                source, root / "build", platform_name="win-amd64",
            )

            self.assertEqual(helper.relative_to(root / "build").as_posix(),
                             "icode/native/icode-sandbox-windows-x64.exe")
            self.assertEqual(manifest, Path(str(helper) + ".sha256"))
            self.assertEqual(helper.read_bytes(), image)
            self.assertEqual(manifest.read_text(encoding="ascii"),
                             hashlib.sha256(image).hexdigest() + "\n")

    def test_stage_refuses_wrong_architecture_and_missing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "helper.exe"
            source.write_bytes(_pe_image(0x8664))
            Path(str(source) + ".sha256").write_text(
                hashlib.sha256(source.read_bytes()).hexdigest() + "\n", encoding="ascii",
            )
            with self.assertRaises(ValueError):
                stage_windows_helper(source, root / "wrong", platform_name="win-arm64")

            Path(str(source) + ".sha256").unlink()
            with self.assertRaises((FileNotFoundError, ValueError)):
                stage_windows_helper(source, root / "missing", platform_name="win-amd64")

    def test_stage_refuses_a_stale_artifact_from_another_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "helper.exe"
            image = _pe_image(0x8664)
            source.write_bytes(image)
            Path(str(source) + ".sha256").write_text(
                hashlib.sha256(image).hexdigest() + "\n", encoding="ascii",
            )
            build_lib = root / "build"
            stale = build_lib / "icode" / "native" / "icode-sandbox-windows-arm64.exe"
            stale.parent.mkdir(parents=True)
            stale.write_bytes(_pe_image(0xAA64))

            with self.assertRaisesRegex(ValueError, "another architecture"):
                stage_windows_helper(source, build_lib, platform_name="win-amd64")

    def test_pure_wheel_build_refuses_a_stale_helper_from_a_previous_build(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            native = root / "build" / "icode" / "native"
            native.mkdir(parents=True)
            (native / "icode-sandbox-windows-x64.exe").write_bytes(_pe_image(0x8664))

            with self.assertRaisesRegex(ValueError, "stale Windows helper"):
                reject_stale_windows_helpers(root / "build")

    def test_wheel_checker_accepts_matching_tag_PE_manifest_and_RECORD(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            wheel = root / "icode_agent-0.1.0-py3-none-win_amd64.whl"
            image = _pe_image(0x8664)
            manifest = (hashlib.sha256(image).hexdigest() + "\n").encode("ascii")
            _write_wheel(wheel, arch="x64", helper=image, manifest=manifest)
            self.assertEqual(check_windows_wheel(wheel), [])

    def test_wheel_checker_rejects_wrong_tag_PE_digest_and_RECORD(self) -> None:
        cases = (
            ("wrong_tag", _pe_image(0x8664), "py3-none-win_arm64", False,
             "wheel architecture tag mismatch"),
            ("pure_tag", _pe_image(0x8664), "py3-none-any", False,
             "wheel architecture tag mismatch"),
            ("wrong_pe", _pe_image(0xAA64), None, False,
             "helper PE architecture mismatch"),
            ("wrong_digest", _pe_image(0x8664), None, False, "helper SHA-256 mismatch"),
            ("wrong_record", _pe_image(0x8664), None, True, "wheel RECORD mismatch"),
        )
        for label, image, tag, bad_record, expected in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                wheel = root / "icode_agent-0.1.0-py3-none-win_amd64.whl"
                digest = hashlib.sha256(image).hexdigest()
                if label == "wrong_digest":
                    digest = "0" * 64
                _write_wheel(
                    wheel, arch="x64", helper=image,
                    manifest=(digest + "\n").encode("ascii"),
                    tag=tag, bad_record=bad_record,
                )
                problems = check_windows_wheel(wheel)
                self.assertTrue(any(expected in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
