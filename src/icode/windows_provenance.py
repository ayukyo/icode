"""Read-only, package-local Windows provenance verification.

The verifier and embedded roots are part of the installed package's trust base.
Adjacent hashes detect corruption, not publisher authenticity. A successful
receipt identifies verified bytes; it is never an executable-path/launch grant.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import sysconfig

from . import native_helper

_MAX_IMAGE_BYTES = 64 * 1024 * 1024
_MAX_PROOF_BYTES = 2 * 1024 * 1024
_MAX_NOTICES_BYTES = 2 * 1024 * 1024
_MAX_RELEASE_BYTES = 1024
_MAX_RECEIPT_BYTES = 512
_VERIFY_TIMEOUT_SECONDS = 30
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _regular_resource(path: Path, limit: int) -> bool:
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= limit


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _object(content: bytes, limit: int) -> dict[str, object]:
    if not content or len(content) > limit:
        raise ValueError("invalid resource length")
    value = json.loads(content, object_pairs_hook=_unique_object)
    if type(value) is not dict:
        raise ValueError("invalid resource object")
    return value


def verify_bundled_windows_provenance() -> dict[str, object] | None:
    """Verify only installed matching-architecture resources, fail closed.

    No caller-supplied identity, source SHA, trust root, executable, PATH or cwd
    fallback exists. This API does not initialize or launch the sandbox helper.
    None means unavailable/unverified, not an OS isolation failure observation.
    """
    if sys.platform != "win32":
        return None
    try:
        arch = native_helper.windows_arch_from_platform(sysconfig.get_platform())
        directory = Path(__file__).resolve().parent / "native"
        if directory.is_symlink() or not directory.is_dir():
            return None
        helper = directory / f"icode-sandbox-windows-{arch}.exe"
        verifier = directory / f"icode-provenance-windows-{arch}.exe"
        proof = Path(str(helper) + ".sigstore.json")
        release_path = directory / "icode-provenance-release.json"
        notices = directory / "icode-provenance-NOTICES.txt"
        resources = (
            (helper, _MAX_IMAGE_BYTES), (Path(str(helper) + ".sha256"), 66),
            (verifier, _MAX_IMAGE_BYTES), (Path(str(verifier) + ".sha256"), 66),
            (proof, _MAX_PROOF_BYTES), (release_path, _MAX_RELEASE_BYTES),
            (notices, _MAX_NOTICES_BYTES),
        )
        if not all(_regular_resource(path, limit) for path, limit in resources):
            return None
        for binary in (helper, verifier):
            if not native_helper.verify_windows_helper(
                binary, Path(str(binary) + ".sha256"), expected_arch=arch,
            ):
                return None
        with release_path.open("rb") as stream:
            release = _object(stream.read(_MAX_RELEASE_BYTES + 1), _MAX_RELEASE_BYTES)
        if (
            set(release) != {"schema_version", "source_sha", "architecture"}
            or type(release["schema_version"]) is not int or release["schema_version"] != 1
            or type(release["source_sha"]) is not str
            or _SOURCE_SHA.fullmatch(release["source_sha"]) is None
            or release["architecture"] != arch
        ):
            return None
        with helper.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        # Never inherit user debug hooks, root/proxy options, or project-specific
        # environment into the package's offline verifier. Windows loader paths
        # are the only host variables retained; no external program is invoked.
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR")
                       if key in os.environ}
        result = subprocess.run(
            [str(verifier), "--artifact", str(helper), "--bundle", str(proof),
             "--source-sha", release["source_sha"], "--arch", arch],
            stdin=subprocess.DEVNULL, capture_output=True, shell=False,
            timeout=_VERIFY_TIMEOUT_SECONDS, check=False, env=environment,
            cwd=str(directory),
        )
        if result.returncode != 0 or result.stderr or type(result.stdout) is not bytes:
            return None
        receipt = _object(result.stdout, _MAX_RECEIPT_BYTES)
        expected = dict(release, artifact_sha256=digest,
                        provenance_verified=True, launch_authorized=False)
        if (
            receipt != expected or type(receipt.get("schema_version")) is not int
            or receipt.get("provenance_verified") is not True
            or receipt.get("launch_authorized") is not False
        ):
            return None
        return receipt
    except (OSError, UnicodeError, ValueError, RuntimeError, RecursionError,
            subprocess.SubprocessError):
        # No input path, proof, certificate, stderr or exception reaches callers.
        return None
