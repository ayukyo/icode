"""Bind bootstrap builds to actual verifier bytes in a private builder window.

This generator is not a publisher verifier, path lock, or launch authorization.
The header belongs only in the build directory, never in an sdist or checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from icode.native_helper import windows_pe_architecture  # noqa: E402

MAX_VERIFIER_BYTES = 64 * 1024 * 1024
_MACHINES = {"x64": 0x8664, "arm64": 0xAA64}


def _file_identity(info: os.stat_result) -> tuple[int, ...]:
    # Windows lstat adds executable permission hints for .exe suffixes while
    # fstat does not. Compare file kind, not these synthetic permission bits;
    # this private builder check is not an owner/DACL authorization proof.
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_verifier_image(verifier: Path, expected_arch: str) -> bytes:
    """Hash consumers use these same bounded bytes, not an adjacent manifest."""
    if expected_arch not in _MACHINES:
        raise ValueError("unsupported verifier architecture")
    verifier = Path(verifier)
    before = verifier.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or not 0 < before.st_size <= MAX_VERIFIER_BYTES):
        raise ValueError("verifier must be a bounded nonempty single-link regular file")
    with verifier.open("rb") as stream:
        if _file_identity(os.fstat(stream.fileno())) != _file_identity(before):
            raise ValueError("verifier changed before read")
        image = stream.read(MAX_VERIFIER_BYTES + 1)
        after_fd = os.fstat(stream.fileno())
    if (_file_identity(after_fd) != _file_identity(before)
            or _file_identity(verifier.lstat()) != _file_identity(before)
            or len(image) != before.st_size):
        raise ValueError("verifier changed during read")
    if windows_pe_architecture(image) != expected_arch:
        raise ValueError("verifier PE architecture mismatch")
    return image


def generate_binding_header(verifier: Path, architecture: str, output: Path) -> None:
    image = read_verifier_image(verifier, architecture)
    digest = hashlib.sha256(image).hexdigest()
    header = (
        "/* Generated from the current verifier bytes; build-directory only. */\n"
        "#define ICODE_VERIFIER_BINDING_SCHEMA 1\n"
        f"#define ICODE_VERIFIER_BINDING_MACHINE 0x{_MACHINES[architecture]:04X}\n"
        f'#define ICODE_VERIFIER_BINDING_SHA256 "{digest}"\n'
    )
    # Always write after successful validation. A build must run this generator
    # even if an input's size/mtime or a previous header appears unchanged.
    Path(output).write_text(header, encoding="ascii", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verifier", type=Path, required=True)
    parser.add_argument("--architecture", choices=tuple(_MACHINES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        generate_binding_header(args.verifier, args.architecture, args.output)
    except (OSError, ValueError):
        # Do not expose private build paths or input bytes in CI diagnostics.
        print("windows_bootstrap_binding: invalid_verifier_input_or_header_output", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
