"""Build-time staging helpers for architecture-specific Windows sandbox wheels."""

from __future__ import annotations

import stat
import hashlib
import json
import re
from pathlib import Path
import shutil

from icode.native_helper import verify_windows_helper, windows_arch_from_platform

MAX_PROVENANCE_BYTES = 2 * 1024 * 1024
MAX_VERIFIER_BYTES = 64 * 1024 * 1024
MAX_NOTICES_BYTES = 2 * 1024 * 1024


def read_provenance_bundle(path: str | Path) -> bytes:
    """Read opaque proof bytes for transport only, not as a trust decision."""
    source = Path(path)
    info = source.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("provenance bundle must be a regular, unlinked file")
    with source.open("rb") as stream:
        content = stream.read(MAX_PROVENANCE_BYTES + 1)
    if not content or len(content) > MAX_PROVENANCE_BYTES:
        raise ValueError("provenance bundle is empty or exceeds transport limit")
    return content


def reject_stale_windows_helpers(build_lib: str | Path) -> None:
    """Do not let a helper left by an earlier build enter a pure wheel."""
    native_dir = Path(build_lib) / "icode" / "native"
    if native_dir.is_symlink():
        raise ValueError("build tree contains an unsafe native resource directory")
    if not native_dir.exists():
        return
    if not native_dir.is_dir():
        raise ValueError("build tree contains an unsafe native resource directory")
    if (next(native_dir.glob("icode-sandbox-windows-*.exe*"), None) is not None
            or next(native_dir.glob("icode-provenance-*"), None) is not None):
        raise ValueError("build tree contains a stale Windows helper; clean the build tree")


def stage_windows_helper(
    source: str | Path,
    build_lib: str | Path,
    *,
    platform_name: str,
    provenance_bundle: str | Path | None = None,
) -> tuple[Path, Path]:
    """Stage a prebuilt helper after its PE architecture and adjacent hash match.

    This is a packaging consistency check only. It does not verify Authenticode,
    build provenance, or authorize the helper to be executed.
    """
    arch = windows_arch_from_platform(platform_name)
    source_path = Path(source)
    manifest_source = Path(str(source_path) + ".sha256")
    if not verify_windows_helper(source_path, manifest_source, expected_arch=arch):
        raise ValueError("Windows helper architecture or SHA-256 manifest is invalid")
    # Validate the optional input before touching the build tree. No JSON field
    # or self-reported signer here can make these bytes trustworthy.
    proof = (None if provenance_bundle is None
             else read_provenance_bundle(provenance_bundle))

    native_dir = Path(build_lib) / "icode" / "native"
    if native_dir.is_symlink():
        raise ValueError("build tree contains an unsafe native resource directory")
    native_dir.mkdir(parents=True, exist_ok=True)
    helper = native_dir / f"icode-sandbox-windows-{arch}.exe"
    manifest = Path(str(helper) + ".sha256")
    bundle = Path(str(helper) + ".sigstore.json")
    expected_names = {helper.name, manifest.name}
    if proof is not None:
        expected_names.add(bundle.name)

    # Never silently carry an artifact from a previous architecture build into
    # this wheel. A reused build tree must be cleaned by the caller.
    for candidate in native_dir.glob("icode-sandbox-windows-*.exe*"):
        if candidate.name not in expected_names:
            raise ValueError("build tree contains a helper for another architecture")
        try:
            status = candidate.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise ValueError("build tree contains an unsafe Windows helper artifact")

    shutil.copyfile(source_path, helper)
    shutil.copyfile(manifest_source, manifest)
    if proof is not None:
        bundle.write_bytes(proof)
    if not verify_windows_helper(helper, manifest, expected_arch=arch):
        raise ValueError("staged Windows helper failed verification")
    return helper, manifest


def stage_windows_provenance(
    source: str | Path, build_lib: str | Path, *, platform_name: str,
    source_sha: str, notices: str | Path,
) -> tuple[Path, Path, Path, Path]:
    """Stage an explicitly built verifier beside a proof-carrying helper.

    These are bounded packaging checks, not authentication of the verifier or
    wheel. Its embedded trust material is part of the installed package TCB.
    """
    arch = windows_arch_from_platform(platform_name)
    if type(source_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("provenance requires an exact source commit")
    source_path = Path(source)
    source_manifest = Path(str(source_path) + ".sha256")
    for path, limit in ((source_path, MAX_VERIFIER_BYTES), (source_manifest, 66),
                        (Path(notices), MAX_NOTICES_BYTES)):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= limit:
            raise ValueError("invalid verifier resource shape or size")
    if not verify_windows_helper(source_path, source_manifest, expected_arch=arch):
        raise ValueError("verifier architecture or SHA-256 manifest is invalid")
    with source_path.open("rb") as stream:
        image = stream.read(MAX_VERIFIER_BYTES + 1)
    with Path(notices).open("rb") as stream:
        notice_bytes = stream.read(MAX_NOTICES_BYTES + 1)
    if not image or len(image) > MAX_VERIFIER_BYTES or not notice_bytes or len(notice_bytes) > MAX_NOTICES_BYTES:
        raise ValueError("verifier resource exceeds transport limit")
    notice_bytes.decode("utf-8", errors="strict")
    # Snapshot bytes must still match the explicit input manifest. A reused
    # build directory is trusted builder state, not a concurrent-host sandbox.
    digest = hashlib.sha256(image).hexdigest()
    if digest != source_manifest.read_text(encoding="ascii").strip():
        raise ValueError("verifier changed during staging")
    native_dir = Path(build_lib) / "icode" / "native"
    if native_dir.is_symlink() or not native_dir.is_dir():
        raise ValueError("build tree contains an unsafe native resource directory")
    helper = native_dir / f"icode-sandbox-windows-{arch}.exe"
    if not verify_windows_helper(helper, Path(str(helper) + ".sha256"), expected_arch=arch):
        raise ValueError("verifier requires a matching staged helper")
    read_provenance_bundle(Path(str(helper) + ".sigstore.json"))
    binary = native_dir / f"icode-provenance-windows-{arch}.exe"
    manifest = Path(str(binary) + ".sha256")
    release = native_dir / "icode-provenance-release.json"
    notice_target = native_dir / "icode-provenance-NOTICES.txt"
    destinations = (binary, manifest, release, notice_target)
    expected_names = {path.name for path in destinations}
    for candidate in native_dir.glob("icode-provenance-*"):
        info = candidate.lstat()
        if (candidate.name not in expected_names or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1):
            raise ValueError("build tree contains an unsafe or stale verifier resource")
    binary.write_bytes(image)
    manifest.write_text(digest + "\n", encoding="ascii")
    release.write_text(json.dumps({"schema_version": 1, "source_sha": source_sha,
                                   "architecture": arch}, separators=(",", ":")) + "\n",
                       encoding="ascii")
    notice_target.write_bytes(notice_bytes)
    return destinations
