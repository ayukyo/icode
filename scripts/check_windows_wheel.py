"""Check Windows wheel tag, packaged helper PE, manifest, and wheel RECORD."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from icode.native_helper import windows_pe_architecture

_ARCHES = {"win_amd64": ("x64", 0x8664), "win_arm64": ("arm64", 0xAA64)}
_SHA256_LINE = re.compile(rb"[0-9a-f]{64}(?:\r?\n)?")


def _record_hash(content: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest())
    return "sha256=" + encoded.rstrip(b"=").decode("ascii")


def check(wheel: Path) -> list[str]:
    """Return path-free package contract violations; never executes the helper."""
    problems: list[str] = []
    name = Path(wheel).name
    platform_tag = next(
        (tag for tag in _ARCHES if name.endswith(f"-py3-none-{tag}.whl")), None,
    )
    if platform_tag is None:
        return ["wheel architecture tag mismatch or unsupported Windows tag"]
    arch, _machine = _ARCHES[platform_tag]
    helper_name = f"icode/native/icode-sandbox-windows-{arch}.exe"
    manifest_name = helper_name + ".sha256"

    try:
        with zipfile.ZipFile(wheel) as archive:
            archive_names = archive.namelist()
            names = set(archive_names)
            if len(names) != len(archive_names):
                problems.append("wheel archive contains duplicate member names")
                return problems
            wheel_metadata_names = [
                entry for entry in names if entry.endswith(".dist-info/WHEEL")
            ]
            record_names = [
                entry for entry in names if entry.endswith(".dist-info/RECORD")
            ]
            if helper_name not in names or manifest_name not in names:
                problems.append("wheel helper or SHA-256 manifest missing")
                return problems
            packaged_helpers = {
                entry for entry in names
                if entry.startswith("icode/native/icode-sandbox-windows-")
                and (entry.endswith(".exe") or entry.endswith(".exe.sha256"))
            }
            if packaged_helpers != {helper_name, manifest_name}:
                problems.append("wheel contains an unexpected Windows helper architecture")
            if len(wheel_metadata_names) != 1:
                problems.append("wheel must contain exactly one WHEEL metadata file")
                return problems
            metadata_name = wheel_metadata_names[0]
            metadata = archive.read(metadata_name).decode("utf-8")
            tags = [
                line.removeprefix("Tag: ") for line in metadata.splitlines()
                if line.startswith("Tag: ")
            ]
            expected_tag = f"py3-none-{platform_tag}"
            if tags != [expected_tag] or "Root-Is-Purelib: false" not in metadata.splitlines():
                problems.append("wheel architecture tag mismatch")

            helper = archive.read(helper_name)
            manifest = archive.read(manifest_name)
            if _SHA256_LINE.fullmatch(manifest) is None:
                problems.append("helper SHA-256 manifest invalid")
            elif hashlib.sha256(helper).hexdigest().encode("ascii") != manifest.strip():
                problems.append("helper SHA-256 mismatch")
            if windows_pe_architecture(helper) != arch:
                problems.append("helper PE architecture mismatch")

            if len(record_names) != 1:
                problems.append("wheel must contain exactly one RECORD")
                return problems
            record_name = record_names[0]
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
            record = {row[0]: row[1:] for row in rows if len(row) == 3}
            if (
                len(record) != len(rows)
                or record.get(helper_name) != [_record_hash(helper), str(len(helper))]
                or record.get(manifest_name) != [_record_hash(manifest), str(len(manifest))]
            ):
                problems.append("wheel RECORD mismatch")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, csv.Error):
        problems.append("wheel archive or metadata invalid")
    return problems


def main() -> int:
    import sys

    if len(sys.argv) != 2:
        print("usage: check_windows_wheel.py WHEEL", file=sys.stderr)
        return 2
    problems = check(Path(sys.argv[1]))
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        return 1
    print("Windows native wheel packaging contract OK (not a signature/provenance check)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
