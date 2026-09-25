"""Build-time staging helpers for architecture-specific Windows sandbox wheels."""

from __future__ import annotations

import stat
from pathlib import Path
import shutil

from icode.native_helper import verify_windows_helper, windows_arch_from_platform


def reject_stale_windows_helpers(build_lib: str | Path) -> None:
    """Do not let a helper left by an earlier build enter a pure wheel."""
    native_dir = Path(build_lib) / "icode" / "native"
    if native_dir.is_symlink():
        raise ValueError("build tree contains an unsafe native resource directory")
    if not native_dir.exists():
        return
    if not native_dir.is_dir():
        raise ValueError("build tree contains an unsafe native resource directory")
    if next(native_dir.glob("icode-sandbox-windows-*.exe*"), None) is not None:
        raise ValueError("build tree contains a stale Windows helper; clean the build tree")


def stage_windows_helper(
    source: str | Path,
    build_lib: str | Path,
    *,
    platform_name: str,
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

    native_dir = Path(build_lib) / "icode" / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    helper = native_dir / f"icode-sandbox-windows-{arch}.exe"
    manifest = Path(str(helper) + ".sha256")
    expected_names = {helper.name, manifest.name}

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
    if not verify_windows_helper(helper, manifest, expected_arch=arch):
        raise ValueError("staged Windows helper failed verification")
    return helper, manifest
