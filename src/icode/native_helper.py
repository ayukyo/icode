"""定位并校验随 Linux wheel 发布的原生隔离助手。"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import struct
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


def _windows_pe_architecture(binary: Path) -> str | None:
    """Read the PE COFF machine field without loading or executing the image."""
    try:
        with Path(binary).open("rb") as stream:
            dos_header = stream.read(64)
            if len(dos_header) != 64 or dos_header[:2] != b"MZ":
                return None
            pe_offset = struct.unpack_from("<I", dos_header, 0x3C)[0]
            # A PE header is conventionally near the start. Bound seeks so malformed
            # images cannot induce unbounded sparse-file scans or integer surprises.
            if pe_offset < 64 or pe_offset > 16 * 1024 * 1024:
                return None
            stream.seek(pe_offset)
            header = stream.read(6)
    except (OSError, ValueError, struct.error):
        return None

    if len(header) != 6 or header[:4] != b"PE\0\0":
        return None
    machine = struct.unpack_from("<H", header, 4)[0]
    return {0x8664: "x64", 0xAA64: "arm64"}.get(machine)


def verify_windows_helper(
    binary: Path, manifest: Path, *, expected_arch: str,
) -> bool:
    """Check a packaged helper's file shape, PE machine and adjacent SHA-256.

    The adjacent digest detects package-internal corruption or mismatch. It is not
    a signature, publisher identity, provenance proof, or race-free launch grant.
    Callers must not execute the returned path based on this check alone.
    """
    if expected_arch not in {"x64", "arm64"}:
        return False
    try:
        binary_stat = Path(binary).lstat()
        manifest_stat = Path(manifest).lstat()
        if not stat.S_ISREG(binary_stat.st_mode) or binary_stat.st_nlink != 1:
            return False
        if not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_nlink != 1:
            return False
        expected = Path(manifest).read_text(encoding="ascii")
        if _SHA256_LINE.fullmatch(expected) is None:
            return False
        if _windows_pe_architecture(binary) != expected_arch:
            return False
        digest = hashlib.sha256()
        with Path(binary).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected.strip()
    except (OSError, UnicodeError, ValueError):
        return False
