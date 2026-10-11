"""Linux 包内助手的有限 ELF 头、真实文件与拒绝边界。"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock, patch

from tests._support import temp_workspace
import icode.native_helper as h


def image(machine: int = 62, kind: int = 2) -> bytes:
    buf = bytearray(64)
    buf[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", buf, 16, kind, machine, 1)
    struct.pack_into("<H", buf, 52, 64)
    return bytes(buf)


def write_helper(root: Path, content: bytes) -> tuple[Path, Path]:
    native = root / "native"
    native.mkdir(exist_ok=True)
    binary = native / "icode-landlock"
    manifest = native / "icode-landlock.sha256"
    binary.write_bytes(content)
    binary.chmod(0o755)
    manifest.write_text(hashlib.sha256(content).hexdigest() + "\n", encoding="ascii")
    return binary, manifest


class FaultStream:
    """只在指定读取阶段注入故障；不暴露绕过 readinto 的 getbuffer。"""

    def __init__(self, content: bytes, phase: str, failure: BaseException | None):
        self.inner = io.BytesIO(content)
        self.phase = phase
        self.failure = failure
        self.requests: list[int] = []

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        if self.phase == "digest" and self.failure is not None:
            raise self.failure
        return self.inner.readinto(buffer)

    def read(self, size: int = -1) -> bytes:
        self.requests.append(size)
        if self.phase == "header" and self.failure is not None:
            raise self.failure
        return self.inner.read(size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.inner.close()

    @property
    def closed(self) -> bool:
        return self.inner.closed


class LinuxHelperElfTests(unittest.TestCase):
    def test_bundle_rejects_digest_matching_non_elf(self) -> None:
        with temp_workspace() as root:
            binary, _ = write_helper(root, b"not-an-ELF-helper")
            with (
                patch.object(h, "__file__", str(root / "native_helper.py")),
                patch.object(h.sys, "platform", "linux"),
                patch("platform.machine", return_value="x86_64"),
            ):
                self.assertIsNone(h.bundled_linux_helper())
            self.assertTrue(binary.is_file())

    def test_parser_supported_machines_and_object_types(self) -> None:
        for machine, arch in ((62, "x86_64"), (183, "arm64")):
            for kind in (2, 3):
                with self.subTest(machine=machine, kind=kind):
                    content = image(machine, kind)
                    self.assertEqual(h.linux_elf_architecture(content), arch)
                    unused = bytearray(content)
                    unused[7:16] = b"\xff" * 9
                    unused[24:52] = b"\xff" * 28
                    unused[54:64] = b"\xff" * 10
                    self.assertEqual(h.linux_elf_architecture(bytes(unused) + b"tail"), arch)

    def test_parser_rejects_types_lengths_and_bad_fields(self) -> None:
        class BytesSubclass(bytes):
            pass

        for value in (None, False, "ELF", bytearray(image()), memoryview(image()),
                      BytesSubclass(image())):
            with self.subTest(value_type=type(value)):
                self.assertIsNone(h.linux_elf_architecture(value))
        for length in range(64):
            with self.subTest(length=length):
                self.assertIsNone(h.linux_elf_architecture(image()[:length]))
        for offset, replacement in (
            (0, b"bad!"), (4, b"\x01"), (5, b"\x02"), (6, b"\x00"),
            (16, b"\x01\0"), (16, b"\x04\0"), (18, b"\x03\0"),
            (20, b"\0\0\0\0"), (52, b"\x3f\0"), (52, b"\x41\0"),
        ):
            with self.subTest(offset=offset, replacement=replacement):
                content = bytearray(image())
                content[offset:offset + len(replacement)] = replacement
                self.assertIsNone(h.linux_elf_architecture(bytes(content)))

    def test_machine_mapping_is_finite_and_exact(self) -> None:
        class StrSubclass(str):
            pass

        for machine, arch in (("x86_64", "x86_64"), ("X86_64", "x86_64"),
                              ("aarch64", "arm64"), ("ARM64", "arm64")):
            with self.subTest(machine=machine):
                self.assertEqual(h.linux_arch_from_machine(machine), arch)
        for machine in (None, True, [], "", "amd64", "x86", "x86_64-extra",
                        " arm64", StrSubclass("arm64")):
            with self.subTest(machine=machine):
                with self.assertRaisesRegex(ValueError, "^unsupported Linux architecture$"):
                    h.linux_arch_from_machine(machine)

    def test_real_file_digest_and_architecture(self) -> None:
        for machine, arch, wrong in ((62, "x86_64", "arm64"), (183, "arm64", "x86_64")):
            for kind in (2, 3):
                with self.subTest(machine=machine, kind=kind), temp_workspace() as root:
                    content = image(machine, kind)
                    binary, manifest = write_helper(root, content)
                    self.assertTrue(h.verify_linux_helper(binary, manifest, expected_arch=arch))
                    self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch=wrong))
                    binary.write_bytes(content + b"changed")
                    self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch=arch))

    def test_manifest_shapes_and_execute_permission(self) -> None:
        with temp_workspace() as root:
            content = image()
            binary, manifest = write_helper(root, content)
            for malformed in ("0" * 64 + "\n", "invalid", "é", ""):
                with self.subTest(manifest=malformed):
                    manifest.write_text(malformed, encoding="utf-8")
                    self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch="x86_64"))
            write_helper(root, content)
            with patch.object(h.os, "access", return_value=False):
                self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch="x86_64"))
            manifest.unlink()
            self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch="x86_64"))
            write_helper(root, content)
            binary.unlink()
            self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch="x86_64"))
            binary.mkdir()
            self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch="x86_64"))

    @unittest.skipUnless(os.name == "posix", "POSIX link creation; no Windows credit")
    def test_real_links_are_rejected(self) -> None:
        for target in ("binary", "manifest"):
            for link_kind in ("hard", "symbolic"):
                with self.subTest(target=target, link_kind=link_kind), temp_workspace() as root:
                    binary, manifest = write_helper(root, image())
                    path = binary if target == "binary" else manifest
                    other = root / "other"
                    if link_kind == "hard":
                        os.link(path, other)
                    else:
                        path.rename(other)
                        path.symlink_to(other)
                    self.assertFalse(h.verify_linux_helper(binary, manifest, expected_arch="x86_64"))

    def test_invalid_expected_arch_refuses_before_open(self) -> None:
        class StrSubclass(str):
            pass

        for arch in (None, True, [], "x64", StrSubclass("x86_64")):
            with (
                self.subTest(arch=arch),
                patch.object(h, "verify_native_helper") as generic,
                patch.object(Path, "open") as opened,
            ):
                self.assertFalse(h.verify_linux_helper(
                    Path("unused"), Path("unused"), expected_arch=arch,
                ))
                generic.assert_not_called()
                opened.assert_not_called()

    def test_bundle_matches_actual_host_without_path_fallback(self) -> None:
        for machine, elf_machine in (("x86_64", 62), ("aarch64", 183), ("arm64", 183)):
            with self.subTest(machine=machine), temp_workspace() as root:
                content = image(elf_machine)
                binary, manifest = write_helper(root, content)
                outsider = root / "outsider"
                outsider.mkdir()
                outside_binary = outsider / binary.name
                outside_binary.write_bytes(content)
                outside_binary.chmod(0o755)
                (outsider / manifest.name).write_text(
                    hashlib.sha256(content).hexdigest() + "\n", encoding="ascii",
                )
                with (
                    patch.object(h, "__file__", str(root / "native_helper.py")),
                    patch.object(h.sys, "platform", "linux"),
                    patch("platform.machine", return_value=machine),
                    patch.dict(os.environ, {"PATH": str(outsider)}),
                ):
                    self.assertEqual(h.bundled_linux_helper(), binary)
                    write_helper(root, image(183 if elf_machine == 62 else 62))
                    self.assertIsNone(h.bundled_linux_helper())
                    binary.unlink()
                    manifest.unlink()
                    self.assertTrue(outside_binary.is_file())
                    self.assertIsNone(h.bundled_linux_helper())

    def test_host_failure_and_non_linux_refuse_before_file_checks(self) -> None:
        for machine in ("unknown", None, [], True):
            with (
                self.subTest(machine=machine),
                patch.object(h.sys, "platform", "linux"),
                patch("platform.machine", return_value=machine),
                patch.object(h, "verify_linux_helper", new=Mock()) as verifier,
            ):
                self.assertIsNone(h.bundled_linux_helper())
                verifier.assert_not_called()
        for failure in (OSError("private"), RuntimeError("private"), ValueError("private")):
            with (
                self.subTest(failure=type(failure)),
                patch.object(h.sys, "platform", "linux"),
                patch("platform.machine", side_effect=failure),
                patch.object(h, "verify_linux_helper", new=Mock()) as verifier,
            ):
                self.assertIsNone(h.bundled_linux_helper())
                verifier.assert_not_called()
        with (
            patch.object(h.sys, "platform", "win32"),
            patch("platform.machine") as machine,
            patch.object(h, "verify_linux_helper", new=Mock()) as verifier,
        ):
            self.assertIsNone(h.bundled_linux_helper())
            machine.assert_not_called()
            verifier.assert_not_called()

    def test_digest_and_header_streams_close_on_faults(self) -> None:
        original_open = Path.open
        for phase in ("digest", "header"):
            for failure in (None, OSError("private"), ValueError("private"),
                            KeyboardInterrupt("private"), SystemExit("private")):
                with self.subTest(phase=phase, failure=type(failure)), temp_workspace() as root:
                    content = image()
                    binary, manifest = write_helper(root, content)
                    streams: list[FaultStream] = []

                    def opened(path, mode="r", *args, **kwargs):
                        if path == binary and mode == "rb":
                            fault_ordinal = 0 if phase == "digest" else 1
                            injected = failure if len(streams) == fault_ordinal else None
                            stream = FaultStream(content, phase, injected)
                            streams.append(stream)
                            return stream
                        return original_open(path, mode, *args, **kwargs)

                    with patch.object(Path, "open", new=opened):
                        if isinstance(failure, (KeyboardInterrupt, SystemExit)):
                            with self.assertRaises(type(failure)) as caught:
                                h.verify_linux_helper(binary, manifest, expected_arch="x86_64")
                            self.assertIs(caught.exception, failure)
                        else:
                            self.assertIs(
                                h.verify_linux_helper(binary, manifest, expected_arch="x86_64"),
                                failure is None,
                            )
                    self.assertTrue(all(stream.closed for stream in streams))
                    expected_count = 1 if phase == "digest" and failure is not None else 2
                    self.assertEqual(len(streams), expected_count)
                    if len(streams) == 2:
                        self.assertEqual(streams[1].requests, [64])

    def test_host_interrupts_preserve_original_object(self) -> None:
        for failure in (KeyboardInterrupt("private"), SystemExit("private")):
            with (
                self.subTest(failure=type(failure)),
                patch.object(h.sys, "platform", "linux"),
                patch("platform.machine", side_effect=failure),
            ):
                with self.assertRaises(type(failure)) as caught:
                    h.bundled_linux_helper()
                self.assertIs(caught.exception, failure)


if __name__ == "__main__":
    unittest.main()
