import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import unittest

def checked_text(argv, cwd):
    p = subprocess.run(argv, cwd=cwd, check=True, capture_output=True, timeout=15)
    if len(p.stdout) > 4096 or p.stderr:
        raise RuntimeError("unexpected identity command output")
    return p.stdout.decode("utf-8").strip()

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

def run_suite(suite, path):
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = stream.getvalue()
    if len(report.encode("utf-8")) > 65536:
        raise RuntimeError("test output exceeded")
    path.write_text(report, encoding="utf-8")
    print(report, end="")
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("red", "green"), required=True)
    parser.add_argument("--expected-arch", choices=("arm64", "x86_64"), required=True)
    args = parser.parse_args()
    if sys.platform != "darwin" or os.getuid() == 0:
        raise RuntimeError("controller requires nonroot native macOS")
    repo = Path(__file__).resolve().parents[1]
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    output = args.output.absolute()
    build = args.build_dir.resolve(strict=True)
    if output.is_symlink() or output.exists() or output.parent.resolve() != temporary:
        raise RuntimeError("output must be a fresh direct child of RUNNER_TEMP")
    if build.parent != temporary or not build.is_dir():
        raise RuntimeError("build must be a direct child of RUNNER_TEMP")
    output.mkdir(mode=0o700)
    metadata = {"phase": args.phase, "native_exit": None, "cleanup": "unknown"}
    try:
        sha = checked_text(["git", "rev-parse", "HEAD"], repo)
        if not re.fullmatch("[0-9a-f]{40}", sha) or sha != os.environ["GITHUB_SHA"]:
            raise RuntimeError("actual candidate SHA differs from GitHub candidate")
        arch = platform.machine()
        if arch != args.expected_arch:
            raise RuntimeError("runner label did not deliver expected native architecture")
        variant = "baseline" if args.phase == "red" else "source"
        binary = build / ("icode_m0a1_" + variant)
        if binary.is_symlink() or not binary.is_file() or not os.access(binary, os.X_OK):
            raise RuntimeError("native binary missing; not semantic RED")
        binary = binary.resolve(strict=True)
        if binary.parent != build:
            raise RuntimeError("native binary escaped build directory")
        image = binary.read_bytes()
        if not 0 < len(image) <= 16 * 1024 * 1024:
            raise RuntimeError("native binary size invalid")
        digest = hashlib.sha256(image).hexdigest()
        artifact_sources = (
            "native/mac/icode_m0a1_limit.h",
            "native/mac/tests/icode_m0a1_baseline.c",
            "native/mac/tests/icode_m0a1_driver.c",
            "tests/test_macos_task_quota_probe.py",
            "native/mac/CMakeLists.txt",
            "scripts/run_macos_m0_ci.py",
            ".github/workflows/ci.yml",
            "docs/nbl/specs/2026-10-13-macos-task-identity-quota-design.md",
            "docs/nbl/plans/2026-10-13-macos-task-identity-quota-m0.md",
        )
        source_hashes = {p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in artifact_sources}
        if variant == "source":
            p = "native/mac/icode_m0a1_limit.c"
            source_hashes[p] = hashlib.sha256((repo / p).read_bytes()).hexdigest()
        metadata.update({
            "candidate_sha": sha, "variant": variant, "binary_sha256": digest,
            "arch": arch, "kernel": platform.release(),
            "os_build": checked_text(["/usr/bin/sw_vers", "-buildVersion"], repo),
            "os_version": checked_text(["/usr/bin/sw_vers", "-productVersion"], repo),
            "run_id": os.environ["GITHUB_RUN_ID"], "job": os.environ["GITHUB_JOB"],
            "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "source_hashes": source_hashes,
        })
        if arch == "x86_64" and metadata["os_version"].split(".")[0] != "15":
            raise RuntimeError("Intel target is explicitly macOS 15")
        write_json(output / "metadata.json", metadata)
        argv = ["/usr/bin/sudo", "-n", "--", "/usr/bin/env", "-i",
                "PATH=/usr/bin:/bin", str(binary), sha, digest]
        try:
            native = subprocess.run(argv, cwd="/", capture_output=True, timeout=135, check=False)
        except subprocess.TimeoutExpired as exc:
            (output / "native.stdout.jsonl").write_bytes((exc.stdout or b"")[:65536])
            (output / "native.stderr.log").write_bytes((exc.stderr or b"")[:65536])
            metadata.update({"native_exit": "timeout", "cleanup": "unknown", "truncated": True})
            raise RuntimeError("native timeout; retained targets unknown, never RED")
        (output / "native.stdout.jsonl").write_bytes(native.stdout[:65536])
        (output / "native.stderr.log").write_bytes(native.stderr[:65536])
        metadata.update({
            "native_exit": native.returncode,
            "native_stdout_sha256": hashlib.sha256(native.stdout).hexdigest(),
            "native_stderr_sha256": hashlib.sha256(native.stderr).hexdigest(),
            "truncated": len(native.stdout) > 65536 or len(native.stderr) > 65536,
        })
        write_json(output / "metadata.json", metadata)
        if native.returncode or metadata["truncated"]:
            raise RuntimeError("native infrastructure failure; preserve raw evidence, not RED")
        os.environ["ICODE_M0A1_EVIDENCE"] = str(output)
        test_path = repo / "tests/test_macos_task_quota_probe.py"
        spec = importlib.util.spec_from_file_location("m0a1_frozen_tests", test_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("formal TEST module unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        protocol = run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(module.TestM0a1Protocol),
                             output / "protocol-tests.log")
        if not protocol.wasSuccessful() or protocol.skipped or protocol.testsRun != 5:
            raise RuntimeError("portable protocol gate failed")
        # Freeze the actual delivery interpretation BEFORE opening any audit
        # file. No case name or unseen root exec fact supplies a receipt.
        views, manifest = module.parse_delivery(native.stdout)
        write_json(output / "delivery-view.json", views)
        root_directory = Path(manifest["root_directory"])
        root_stat = root_directory.lstat()
        if (not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != 0
                or stat.S_IMODE(root_stat.st_mode) != 0o755):
            raise RuntimeError("protected audit directory identity invalid")
        fd = os.open(root_directory / "native.jsonl", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                    or stat.S_IMODE(before.st_mode) != 0o444 or before.st_nlink != 1
                    or not 0 < before.st_size <= 65536):
                raise RuntimeError("protected audit file identity invalid")
            chunks = []
            total = 0
            while total <= 65536:
                chunk = os.read(fd, min(4096, 65537 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            after = os.fstat(fd)
            if (total > 65536 or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise RuntimeError("audit changed or exceeded size bound")
            audit_raw = b"".join(chunks)
        finally:
            os.close(fd)
        if hashlib.sha256(audit_raw).hexdigest() != manifest["ledger_sha256"]:
            raise RuntimeError("independent root audit export digest differs")
        (output / "native.audit.jsonl").write_bytes(audit_raw)
        metadata["native_audit_sha256"] = hashlib.sha256(audit_raw).hexdigest()
        write_json(output / "metadata.json", metadata)
        meta, rows, audit, frozen_views = module.load_evidence(output)
        formal = run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(module.TestNativeM0a1),
                           output / "native-tests.log")
        metadata["protocol_ledger"] = {"passed": protocol.testsRun, "errors": 0, "skipped": 0}
        metadata["native_ledger"] = {
            "tests": formal.testsRun, "failures": len(formal.failures),
            "errors": len(formal.errors), "skipped": len(formal.skipped),
            "root_ledger_sha256": audit["ledger_sha256"], "root_directory": audit["root_directory"],
        }
        if formal.errors or formal.skipped or formal.testsRun != 5:
            raise RuntimeError("formal native suite incomplete; not RED")
        if args.phase == "red":
            failures = formal.failures
            observed = rows["cap1_fork"]
            if (len(failures) != 1 or failures[0][0]._testMethodName != "test_cap1_quota_semantic"
                    or "M0A1_QUOTA_REJECTION" not in failures[0][1]
                    or observed["fork_pid"] <= 0 or observed["fork_errno"] != 0
                    or observed["child_byte"] != 1 or observed["payload_cur"] < 2):
                raise RuntimeError("RED must be the genuine fork-success quota assertion")
            metadata["result"] = "semantic_RED_confirmed"
        elif not formal.wasSuccessful():
            raise RuntimeError("SOURCE native GREEN failed")
        else:
            metadata["result"] = "M0a1_GREEN_only"
        metadata["cleanup"] = "owned_root_reaped; targets_and_UIDs_retained; no_full_tree_credit"
        write_json(output / "metadata.json", metadata)
        return 0
    except Exception as exc:
        metadata["result"] = "ERROR_or_unaccepted_failure"
        metadata["error"] = str(exc)
        write_json(output / "metadata.json", metadata)
        raise

if __name__ == "__main__":
    raise SystemExit(main())
