"""定位并校验随 Linux wheel 发布的原生隔离助手。"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
from pathlib import Path

_SHA256_LINE = re.compile(r"[0-9a-f]{64}\n?")


def verify_native_helper(binary: Path, manifest: Path) -> bool:
    """缺失、链接、权限或摘要不符均视为不可用，绝不执行。"""
    try:
        binary_stat = binary.lstat()
        manifest_stat = manifest.lstat()
        if not stat.S_ISREG(binary_stat.st_mode) or binary_stat.st_nlink != 1:
            return False
        if not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_nlink != 1:
            return False
        if not os.access(binary, os.X_OK):
            return False
        expected = manifest.read_text(encoding="ascii")
        if _SHA256_LINE.fullmatch(expected) is None:
            return False
        with binary.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        return actual == expected.strip()
    except (OSError, UnicodeError):
        return False


def bundled_linux_helper() -> Path | None:
    """返回经过本地摘要检查的包内助手；其他平台或不完整 wheel 返回 None。"""
    if not sys.platform.startswith("linux"):
        return None
    directory = Path(__file__).resolve().parent / "native"
    binary = directory / "icode-landlock"
    manifest = directory / "icode-landlock.sha256"
    return binary if verify_native_helper(binary, manifest) else None
