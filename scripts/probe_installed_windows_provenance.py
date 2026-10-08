"""CI-only real installed verifier positive/negative checks; never run a helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or re.fullmatch(r"[0-9a-f]{40}", args.source_sha) is None:
        print("::error::installed provenance probe input invalid")
        return 1
    try:
        import icode
        from icode.native_helper import bundled_windows_helper, windows_arch_from_platform
        from icode.windows_provenance import verify_bundled_windows_provenance

        # Source checkout imports do not satisfy pip-only installed acceptance.
        package = Path(icode.__file__).resolve().parent
        package.relative_to(Path(sysconfig.get_paths()["purelib"]).resolve())
        helper = bundled_windows_helper()
        assert helper is not None
        arch = windows_arch_from_platform(sysconfig.get_platform())
        receipt = verify_bundled_windows_provenance()
        assert receipt is not None and receipt["source_sha"] == args.source_sha
        assert receipt["launch_authorized"] is False
        verifier = package / "native" / f"icode-provenance-windows-{arch}.exe"
        proof = Path(str(helper) + ".sigstore.json")
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR")
                       if key in os.environ}

        def reject(artifact: Path, bundle: Path, source_sha: str) -> None:
            result = subprocess.run(
                [str(verifier), "--artifact", str(artifact), "--bundle", str(bundle),
                 "--source-sha", source_sha, "--arch", arch],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                check=False, shell=False, env=environment,
            )
            assert result.returncode == 78 and result.stdout == b""
            assert result.stderr == b"icode_provenance: verification_failed\n"

        reject(helper, proof, "0" * 40 if args.source_sha != "0" * 40 else "1" * 40)
        with tempfile.TemporaryDirectory(prefix="icode-installed-provenance-") as raw:
            root = Path(raw)
            artifact = root / helper.name
            image = helper.read_bytes()
            digest = hashlib.sha256(image).hexdigest()
            assert receipt["artifact_sha256"] == digest
            artifact.write_bytes(image[:-1] + bytes([image[-1] ^ 1]))
            reject(artifact, proof, args.source_sha)
            artifact.write_bytes(image)
            missing = root / "missing-proof.json"
            reject(artifact, missing, args.source_sha)
            malformed = root / "malformed-proof.json"
            malformed.write_bytes(b"{")
            reject(artifact, malformed, args.source_sha)
            original = json.loads(proof.read_bytes())
            entries = original["verificationMaterial"]["tlogEntries"]
            assert isinstance(entries, list) and entries
            for entry in entries:
                entry.pop("inclusionProof", None)
            promise_only = root / "promise-only.json"
            promise_only.write_text(json.dumps(original), encoding="utf-8")
            reject(artifact, promise_only, args.source_sha)
            wrong_name = root / "not-the-canonical-helper.exe"
            wrong_name.write_bytes(image)
            reject(wrong_name, proof, args.source_sha)
        print("installed-offline-provenance positive=PASS negatives=6 launch_authorized=false")
        return 0
    except (AssertionError, ImportError, OSError, ValueError, KeyError, TypeError, RuntimeError,
            subprocess.SubprocessError):
        print("::error::installed offline provenance verification failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
