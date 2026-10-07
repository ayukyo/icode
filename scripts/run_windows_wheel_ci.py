"""Exercise synthetic packaging or an explicit, CI-built native bootstrap.

Only the explicit native mode runs metadata/rejection checks. Optional proof
mode uses GitHub CLI to verify the installed artifact in CI. Neither mode
authorizes product launch, setup, or isolation acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

_REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY))
sys.path.insert(0, str(_REPOSITORY / "src"))

from icode.native_helper import windows_arch_from_platform, windows_pe_architecture  # noqa: E402
from scripts.check_windows_wheel import check as check_windows_wheel  # noqa: E402
from scripts.windows_wheel import read_provenance_bundle  # noqa: E402

_HELPER_ENV = "ICODE_WINDOWS_SANDBOX_HELPER"
_BUNDLE_ENV = "ICODE_WINDOWS_SANDBOX_BUNDLE"


def _provenance_verify_argv(helper: Path, bundle: Path, source_sha: str) -> list[str]:
    """Fixed policy for CI only. This does not add a product verifier dependency."""
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("provenance CI requires the exact source commit")
    return [
        "gh", "attestation", "verify", str(helper), "--bundle", str(bundle),
        "--repo", "ayukyo/icode",
        "--cert-identity", "https://github.com/ayukyo/icode/.github/workflows/"
        "windows-helper-provenance.yml@refs/heads/main",
        "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
        "--source-ref", "refs/heads/main", "--source-digest", source_sha,
        "--signer-digest", source_sha, "--deny-self-hosted-runners",
        "--predicate-type", "https://slsa.dev/provenance/v1",
    ]


def _run(stage: str, argv: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=240, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-1600:]
        raise RuntimeError(f"{stage} exit={result.returncode}: {detail}")
    print(f"{stage}: PASS")
    return result.stdout


def _synthetic_pe(machine: int) -> bytes:
    image = bytearray(0x80 + 6)
    image[:2] = b"MZ"
    image[0x3C:0x40] = (0x80).to_bytes(4, "little")
    image[0x80:0x84] = b"PE\0\0"
    image[0x84:0x86] = machine.to_bytes(2, "little")
    return bytes(image)


def _read_native_image(helper: Path, arch: str) -> bytes:
    """Accept an explicit CI artifact, not a trusted product executable."""
    info = helper.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise RuntimeError("native CI artifact must be a regular, unlinked file")
    with helper.open("rb") as stream:
        image = stream.read(32 * 1024 * 1024 + 1)
    if len(image) > 32 * 1024 * 1024 or windows_pe_architecture(image) != arch:
        raise RuntimeError("native CI artifact size or PE architecture mismatch")
    return image


def _validate_bootstrap_output(output: str, arch: str) -> None:
    expected = {
        "helper": "icode-windows-bootstrap", "bootstrap_version": 1,
        "runner_protocol_version": 1, "architecture": arch,
        "setup_complete": False, "command_execution": False,
        "isolation_ready": False,
    }
    # Fixed serialization also rejects duplicates, extra fields, bool/int aliases
    # and trailing output without parsing arbitrary JSON from a candidate image.
    if output != json.dumps(expected, separators=(",", ":")) + "\n":
        raise RuntimeError("native bootstrap metadata contract mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-helper", type=Path,
                        help="explicit artifact built from this checkout; CI use only")
    parser.add_argument("--provenance-bundle", type=Path,
                        help="CI proof to package exactly and verify using GitHub CLI")
    parser.add_argument("--wheel-output", type=Path,
                        help="CI directory for a wheel after all signed-mode checks pass")
    args = parser.parse_args()
    if sys.platform != "win32":
        print("::error::Windows wheel packaging probe was invoked on another platform")
        return 1
    try:
        if args.provenance_bundle is not None and args.native_helper is None:
            raise ValueError("provenance mode requires a real native CI artifact")
        if args.wheel_output is not None and args.provenance_bundle is None:
            raise ValueError("wheel publication requires provenance mode")
        proof = (None if args.provenance_bundle is None
                 else read_provenance_bundle(args.provenance_bundle))
        if proof is not None:
            _provenance_verify_argv(Path("unused"), Path("unused"),
                                    os.environ.get("GITHUB_SHA", ""))
        platform_name = sysconfig.get_platform()
        arch = windows_arch_from_platform(platform_name)
        machine = {"x64": 0x8664, "arm64": 0xAA64}[arch]
        with tempfile.TemporaryDirectory(prefix="icode-windows-wheel-") as raw:
            root = Path(raw)
            helper_dir = root / "helper artifact"
            helper_dir.mkdir()
            helper = helper_dir / "sandbox-helper.exe"
            image = (_synthetic_pe(machine) if args.native_helper is None
                     else _read_native_image(args.native_helper, arch))
            helper.write_bytes(image)
            Path(str(helper) + ".sha256").write_text(
                hashlib.sha256(image).hexdigest() + "\n", encoding="ascii",
            )

            dist = root / "dist"
            env = os.environ.copy()
            env[_HELPER_ENV] = str(helper)
            env.pop(_BUNDLE_ENV, None)
            if proof is not None:
                staged_bundle = helper_dir / "proof.json"
                staged_bundle.write_bytes(proof)
                env[_BUNDLE_ENV] = str(staged_bundle)
            _run(
                "install build frontend",
                [sys.executable, "-m", "pip", "install", "build"],
                cwd=root, env=env,
            )

            pure_env = env.copy()
            pure_env.pop(_HELPER_ENV, None)
            pure_env.pop(_BUNDLE_ENV, None)
            pure_dist = root / "dist-pure-python"
            _run(
                "build pure Python wheel without native helper",
                [sys.executable, "-m", "build", "--wheel", "--outdir", str(pure_dist)],
                cwd=_REPOSITORY, env=pure_env,
            )
            pure_wheels = list(pure_dist.glob("*.whl"))
            if len(pure_wheels) != 1 or not pure_wheels[0].name.endswith("-py3-none-any.whl"):
                raise RuntimeError("build without helper must remain a universal pure-Python wheel")
            with zipfile.ZipFile(pure_wheels[0]) as archive:
                names = archive.namelist()
                if any("icode-sandbox-windows-" in name for name in names):
                    raise RuntimeError("pure-Python wheel unexpectedly contains a Windows helper")

            pure_venv = root / "pure-venv"
            _run("create pure-wheel venv", [sys.executable, "-m", "venv", str(pure_venv)],
                 cwd=root, env=pure_env)
            pure_python = pure_venv / "Scripts" / "python.exe"
            clean_pure_env = pure_env.copy()
            clean_pure_env.pop("PYTHONPATH", None)
            clean_pure_env.pop(_HELPER_ENV, None)
            _run("install pure-Python wheel", [str(pure_python), "-m", "pip", "install",
                 "--no-deps", str(pure_wheels[0])], cwd=root, env=clean_pure_env)
            _run(
                "pure-Python install reports helper unavailable",
                [str(pure_python), "-c",
                 "from icode.native_helper import bundled_windows_helper; "
                 "assert bundled_windows_helper() is None"],
                cwd=root, env=clean_pure_env,
            )

            _run(
                "build architecture-tagged Windows wheel",
                [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist)],
                cwd=_REPOSITORY, env=env,
            )
            wheels = list(dist.glob("*.whl"))
            if len(wheels) != 1:
                raise RuntimeError(f"expected one wheel, found {len(wheels)}")
            if check_windows_wheel(wheels[0], expected_bundle=proof):
                raise RuntimeError("final wheel provenance transport contract failed")
            _run(
                "inspect Windows wheel metadata and integrity",
                [sys.executable, str(_REPOSITORY / "scripts" / "check_windows_wheel.py"),
                 str(wheels[0])],
                cwd=root, env=env,
            )

            venv = root / "venv"
            _run("create isolated venv", [sys.executable, "-m", "venv", str(venv)],
                 cwd=root, env=env)
            python = venv / "Scripts" / "python.exe"
            clean_env = env.copy()
            clean_env.pop("PYTHONPATH", None)
            clean_env.pop(_HELPER_ENV, None)
            clean_env.pop(_BUNDLE_ENV, None)
            _run("install Windows wheel", [str(python), "-m", "pip", "install",
                 "--no-deps", str(wheels[0])], cwd=root, env=clean_env)
            code = (
                "from pathlib import Path; import sysconfig; "
                "from icode.native_helper import bundled_windows_helper, "
                "windows_arch_from_platform; "
                "helper=bundled_windows_helper(); "
                "assert helper is not None and helper.is_file(); "
                "assert helper.name.endswith(windows_arch_from_platform(sysconfig.get_platform()) + '.exe'); "
                "assert helper.is_absolute(); "
                "print(str(helper))"
            )
            installed_path = _run("resolve installed helper without source checkout",
                                  [str(python), "-c", code], cwd=root, env=clean_env).strip()
            if proof is not None:
                installed_helper = Path(installed_path)
                installed_bundle = Path(str(installed_helper) + ".sigstore.json")
                if read_provenance_bundle(installed_bundle) != proof:
                    raise RuntimeError("installed proof differs from the signing action output")
                _run("cryptographically verify installed CI artifact provenance",
                     _provenance_verify_argv(installed_helper, installed_bundle,
                                             env.get("GITHUB_SHA", "")),
                     cwd=root, env=clean_env)

            if args.native_helper is not None:
                # CI executes only the artifact explicitly built from this job's
                # checkout. Runtime helper discovery remains non-authorizing.
                metadata_code = (
                    "import subprocess,sys; "
                    "from icode.native_helper import bundled_windows_helper; "
                    "helper=bundled_windows_helper(); assert helper is not None; "
                    "result=subprocess.run([str(helper),'--version-json'],"
                    "capture_output=True,text=True,encoding='utf-8',timeout=5); "
                    "assert result.returncode == 0 and not result.stderr; "
                    "sys.stdout.write(result.stdout)"
                )
                output = _run("run installed native bootstrap metadata", [str(python), "-c", metadata_code],
                              cwd=root, env=clean_env)
                _validate_bootstrap_output(output, arch)
                refusal_code = (
                    "import subprocess; "
                    "from icode.native_helper import bundled_windows_helper; "
                    "helper=bundled_windows_helper(); assert helper is not None; "
                    "args_list=[[],['setup'],['spawn','PRIVATE_COMMAND'],"
                    "['--version-json','PRIVATE_ARGUMENT']]; "
                    "results=[subprocess.run([str(helper),*args],capture_output=True,"
                    "text=True,encoding='utf-8',timeout=5) for args in args_list]; "
                    "assert all(r.returncode == 78 and not r.stdout and r.stderr == "
                    "'icode_windows_bootstrap: unsupported_operation\\n' for r in results)"
                )
                _run("installed bootstrap refuses setup and commands", [str(python), "-c", refusal_code],
                     cwd=root, env=clean_env)

            installed_code = (
                "from pathlib import Path; import icode.native_helper as nh; "
                "helper=nh.bundled_windows_helper(); assert helper is not None; "
                "helper.rename(helper.with_suffix('.exe.disabled')); "
                "assert nh.bundled_windows_helper() is None; "
                "print('missing installed helper fails closed')"
            )
            _run("fail closed when bundled helper is missing", [str(python), "-c", installed_code],
                 cwd=root, env=clean_env)
            if args.wheel_output is not None:
                args.wheel_output.mkdir(parents=True, exist_ok=True)
                # Never replace an earlier artifact under a superficially equal
                # name; publication only follows all installed-wheel checks.
                with (args.wheel_output / wheels[0].name).open("xb") as target:
                    target.write(wheels[0].read_bytes())
                print("signed-mode CI wheel exported (not product launch authorization): PASS")
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
        print(f"::error::windows_wheel_probe_failed ({type(exc).__name__}: {exc})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
