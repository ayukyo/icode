"""R2.2 随包 Linux 助手的完整性检查。"""

from __future__ import annotations

import hashlib
import os
import unittest
import icode.native_helper as native_helper

from tests._support import temp_workspace

from icode.native_helper import bundled_linux_helper, verify_native_helper


class TestNativeHelper(unittest.TestCase):
    def test_摘要匹配才能使用助手(self) -> None:
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            manifest = root / "icode-landlock.sha256"
            helper.write_bytes(b"helper-v1")
            os.chmod(helper, 0o755)
            manifest.write_text(hashlib.sha256(b"helper-v1").hexdigest() + "\n", encoding="ascii")
            self.assertTrue(verify_native_helper(helper, manifest))
            helper.write_bytes(b"tampered")
            self.assertFalse(verify_native_helper(helper, manifest))

    def test_缺失或软链接不能充当随包助手(self) -> None:
        with temp_workspace() as root:
            helper = root / "icode-landlock"
            manifest = root / "icode-landlock.sha256"
            self.assertFalse(verify_native_helper(helper, manifest))
            target = root / "target"
            target.write_bytes(b"target")
            helper.symlink_to(target)
            manifest.write_text(hashlib.sha256(b"target").hexdigest() + "\n", encoding="ascii")
            self.assertFalse(verify_native_helper(helper, manifest))

    def test_包内查询安全地报告缺失(self) -> None:
        result = bundled_linux_helper()
        self.assertTrue(result is None or result.is_file())


class TestWindowsNativeHelper(unittest.TestCase):
    @staticmethod
    def _synthetic_pe(machine: int) -> bytes:
        image = bytearray(0x80 + 6)
        image[:2] = b"MZ"
        image[0x3C:0x40] = (0x80).to_bytes(4, "little")
        image[0x80:0x84] = b"PE\0\0"
        image[0x84:0x86] = machine.to_bytes(2, "little")
        return bytes(image)

    def test_仅匹配目标PE架构且摘要正确的helper可用(self) -> None:
        verifier = getattr(native_helper, "verify_windows_helper", None)
        self.assertIsNotNone(verifier, "缺少 Windows PE helper 校验器")
        with temp_workspace() as root:
            helper = root / "icode-sandbox-x64.exe"
            manifest = root / "icode-sandbox-x64.exe.sha256"
            image = self._synthetic_pe(0x8664)
            helper.write_bytes(image)
            manifest.write_text(hashlib.sha256(image).hexdigest() + "\n", encoding="ascii")

            self.assertTrue(verifier(helper, manifest, expected_arch="x64"))
            self.assertFalse(verifier(helper, manifest, expected_arch="arm64"))

    def test_损坏或非PE镜像不能通过校验(self) -> None:
        verifier = getattr(native_helper, "verify_windows_helper", None)
        self.assertIsNotNone(verifier, "缺少 Windows PE helper 校验器")
        for label, image in (("truncated", b"MZ"), ("wrong_signature", b"not a PE")):
            with self.subTest(label=label), temp_workspace() as root:
                helper = root / "icode-sandbox-x64.exe"
                manifest = root / "icode-sandbox-x64.exe.sha256"
                helper.write_bytes(image)
                manifest.write_text(
                    hashlib.sha256(image).hexdigest() + "\n", encoding="ascii",
                )
                self.assertFalse(verifier(helper, manifest, expected_arch="x64"))

    def test_摘要不匹配和硬链接helper一律拒绝(self) -> None:
        verifier = getattr(native_helper, "verify_windows_helper", None)
        self.assertIsNotNone(verifier, "缺少 Windows PE helper 校验器")
        with temp_workspace() as root:
            image = self._synthetic_pe(0x8664)
            helper = root / "icode-sandbox-x64.exe"
            manifest = root / "icode-sandbox-x64.exe.sha256"
            helper.write_bytes(image)
            manifest.write_text("0" * 64 + "\n", encoding="ascii")
            self.assertFalse(verifier(helper, manifest, expected_arch="x64"))

            manifest.write_text(hashlib.sha256(image).hexdigest() + "\n", encoding="ascii")
            second_link = root / "hardlink.exe"
            os.link(helper, second_link)
            self.assertFalse(verifier(helper, manifest, expected_arch="x64"))


if __name__ == "__main__":
    unittest.main()
