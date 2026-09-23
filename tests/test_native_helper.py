"""R2.2 随包 Linux 助手的完整性检查。"""

from __future__ import annotations

import hashlib
import os
import unittest

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


if __name__ == "__main__":
    unittest.main()
