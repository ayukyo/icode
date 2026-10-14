import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shlex
import signal
import time
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

def process_groups_binding(repo, build, binary, variant, output):
    def collect(name, argv, cwd, bound):
        buffers = [bytearray(), bytearray()]
        p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True)
        failure = None
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(p.stdout, selectors.EVENT_READ, 0)
                selector.register(p.stderr, selectors.EVENT_READ, 1)
                deadline = time.monotonic() + 15
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        failure = "timeout"
                        break
                    for key, _ in selector.select(min(remaining, 0.1)):
                        room = bound - len(buffers[0]) - len(buffers[1])
                        chunk = os.read(key.fileobj.fileno(), min(4096, room + 1))
                        if not chunk:
                            selector.unregister(key.fileobj)
                        elif len(chunk) > room:
                            buffers[key.data].extend(chunk[:room])
                            failure = "output exceeded"
                            break
                        else:
                            buffers[key.data].extend(chunk)
                    if failure:
                        break
                if not failure:
                    try:
                        p.wait(timeout=max(0.001, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        failure = "timeout"
        finally:
            if failure or p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            p.wait(timeout=2)
            p.stdout.close()
            p.stderr.close()
            for suffix, data in zip(("stdout", "stderr"), buffers):
                (output / (name + "." + suffix)).write_bytes(data)
        if failure or p.returncode:
            raise RuntimeError("process groups binding " + (failure or "command failed") + ": " + name)
        return (buffers[0].decode("utf-8", "strict"),
                buffers[1].decode("utf-8", "strict"))

    commands_path = build / "compile_commands.json"
    raw = commands_path.read_bytes()
    if not 0 < len(raw) <= 1048576:
        raise RuntimeError("compile commands size invalid")
    commands = json.loads(raw)
    helper = (repo / "native/mac/icode_m0a1_process_groups.c").resolve(strict=True)
    selected = []
    for entry in commands:
        cwd = Path(entry["directory"]).resolve(strict=True)
        source = Path(entry["file"])
        source = source if source.is_absolute() else cwd / source
        argv = entry.get("arguments") or shlex.split(entry["command"])
        if source.resolve(strict=True) == helper and "-o" in argv:
            target_object = Path(argv[argv.index("-o") + 1])
            target_object = target_object if target_object.is_absolute() else cwd / target_object
            if "CMakeFiles/icode_m0a1_" + variant + ".dir/" in target_object.as_posix():
                selected.append((cwd, argv, target_object.resolve(strict=True)))
    if len(selected) != 1:
        raise RuntimeError("helper compile command identity ambiguous")
    cwd, argv, obj = selected[0]
    if cwd != build or build not in obj.parents or argv.count("-o") != 1 or argv.count("-c") != 1:
        raise RuntimeError("helper compiler/object escaped expected build")
    compiler = Path(argv[0]).resolve(strict=True)
    if not compiler.is_file() or not os.access(compiler, os.X_OK):
        raise RuntimeError("actual compiler unavailable")
    version, version_err = collect("groups-compiler", [str(compiler), "--version"], cwd, 65536)
    sdk_text, sdk_err = collect("groups-sdk-path", ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"], cwd, 65536)
    sdk_version, sdk_version_err = collect("groups-sdk-version", ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-version"], cwd, 65536)
    sdk = Path(sdk_text.strip()).resolve(strict=True)
    if not sdk.is_dir() or sdk_err or sdk_version_err or version_err:
        raise RuntimeError("unexpected SDK/compiler metadata")
    _, trace = collect("groups-compiler-trace", argv + ["-###"], cwd, 65536)
    trace_args = shlex.split(trace)
    roots = [trace_args[i + 1] for i, value in enumerate(trace_args[:-1]) if value == "-isysroot"]
    if len(roots) != 1 or Path(roots[0]).resolve(strict=True) != sdk:
        raise RuntimeError("actual compiler SDK differs or is unknown")
    expanded = list(argv)
    expanded[expanded.index("-c")] = "-E"
    expanded[expanded.index("-o") + 1] = "-"
    headers, header_err = collect("groups-expanded", expanded, cwd, 2097152)
    declarations = re.findall(r"(?m)^[ \t]*(?:extern[ \t]+)?int[ \t]+getgroups\s*\([^;]+;", headers)
    if header_err or len(declarations) != 1 or "DARWIN_EXTSN" in declarations[0]:
        raise RuntimeError("actual SDK getgroups declaration is unknown or extended")
    symbols = {}
    for name, image in (("groups-object-nm", obj), ("groups-final-nm", binary)):
        text, diagnostic = collect(name, ["/usr/bin/nm", "-u", str(image)], cwd, 262144)
        groups = [line.split()[-1] for line in text.splitlines() if "getgroups" in line]
        if diagnostic or groups != ["_getgroups"]:
            raise RuntimeError("ordinary public getgroups binding required: " + name)
        symbols[name] = groups
    record = {
        "version": 1, "compiler": str(compiler), "compiler_version": version,
        "sdk": str(sdk), "sdk_version": sdk_version.strip(), "directory": str(cwd),
        "compile_argv": argv, "helper_object": str(obj),
        "helper_object_sha256": hashlib.sha256(obj.read_bytes()).hexdigest(),
        "final_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "compile_commands_sha256": hashlib.sha256(raw).hexdigest(),
        "getgroups_declaration": declarations[0], "symbols": symbols,
        "raw_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(output.glob("groups-*.stdout")) + sorted(output.glob("groups-*.stderr"))},
    }
    write_json(output / "process-groups-binding.json", record)
    return hashlib.sha256((output / "process-groups-binding.json").read_bytes()).hexdigest()

def require_w1_groups(metadata):
    record=metadata.get("groups_native")
    keys={"result","candidate_sha","arch","binary_sha256","ledger_sha256","binding_sha256","native_exit","cleanup_scope"}
    if (not isinstance(record,dict) or set(record)!=keys
            or record.get("result")!="native_groups_verified"
            or record.get("candidate_sha")!=metadata.get("candidate_sha")
            or record.get("arch")!=metadata.get("arch")
            or type(record.get("native_exit")) is not int or record["native_exit"]!=0
            or record.get("cleanup_scope")!="owned_root_only_identities_retained"
            or any(not isinstance(record.get(k),str) or not re.fullmatch("[0-9a-f]{64}",record[k])
                   for k in ("binary_sha256","ledger_sha256","binding_sha256"))):
        raise RuntimeError("W1_GROUPS same-candidate native evidence required")

def run_w1_groups(repo,build,output,sha,arch):
    binary=build/"icode_m0a1_groups_native"
    if binary.is_symlink() or not binary.is_file() or not os.access(binary,os.X_OK):
        raise RuntimeError("W1_GROUPS native TEST binary unavailable; not semantic RED")
    binary=binary.resolve(strict=True)
    if binary.parent!=build:
        raise RuntimeError("W1_GROUPS binary escaped build")
    size=binary.stat().st_size
    if not 0<size<=16*1024*1024:
        raise RuntimeError("W1_GROUPS binary size invalid")
    image=binary.read_bytes();digest=hashlib.sha256(image).hexdigest()
    (output/"icode_m0a1_groups_native").write_bytes(image)
    binding=output/"w1-binding";binding.mkdir(mode=0o700)
    binding_sha=process_groups_binding(repo,build,binary,"groups_native",binding)
    argv=["/usr/bin/sudo","-n","--","/usr/bin/env","-i","PATH=/usr/bin:/bin",str(binary),sha,digest]
    try:
        actual=subprocess.run(argv,cwd="/",capture_output=True,timeout=50,check=False)
    except subprocess.TimeoutExpired as exc:
        (output/"w1-native.stdout.json").write_bytes((exc.stdout or b"")[:512])
        (output/"w1-native.stderr.log").write_bytes((exc.stderr or b"")[:256])
        write_json(output/"w1-execution.json",{"candidate_sha":sha,"arch":arch,"binary_sha256":digest,
            "native_exit":"timeout","cleanup":"unknown","raw_complete":False})
        raise RuntimeError("W1_GROUPS timeout; identities retained cleanup unknown") from exc
    (output/"w1-native.stdout.json").write_bytes(actual.stdout[:512])
    (output/"w1-native.stderr.log").write_bytes(actual.stderr[:256])
    write_json(output/"w1-execution.json",{"candidate_sha":sha,"arch":arch,"binary_sha256":digest,
        "native_exit":actual.returncode,"stdout_bytes":len(actual.stdout),"stderr_bytes":len(actual.stderr),
        "stdout_sha256":hashlib.sha256(actual.stdout).hexdigest(),
        "stderr_sha256":hashlib.sha256(actual.stderr).hexdigest(),
        "raw_complete":len(actual.stdout)<=512 and len(actual.stderr)<=256})
    if actual.returncode or len(actual.stdout)>512 or len(actual.stderr)>256 or actual.stderr:
        raise RuntimeError("W1_GROUPS infrastructure failure/overflow; never quota RED")
    testpath=repo/"tests/test_macos_process_groups_native.py"
    spec=importlib.util.spec_from_file_location("w1_frozen_observer",testpath)
    if spec is None or spec.loader is None:
        raise RuntimeError("W1_GROUPS independent TEST unavailable")
    tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError("W1_GROUPS duplicate JSON key")
            value[key]=item
        return value
    manifest=json.loads(actual.stdout,object_pairs_hook=unique)
    if (not isinstance(manifest,dict) or set(manifest)!={"version","root_directory","ledger_sha256"}
            or type(manifest["version"]) is not int or manifest["version"]!=1
            or not isinstance(manifest["root_directory"],str)
            or not re.fullmatch(r"/private/var/icode-m0a1-groups\.[A-Za-z0-9]+",manifest["root_directory"])
            or not isinstance(manifest["ledger_sha256"],str)
            or not re.fullmatch("[0-9a-f]{64}",manifest["ledger_sha256"])):
        raise RuntimeError("W1_GROUPS root manifest invalid")
    directory=Path(manifest["root_directory"])
    st=directory.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or stat.S_IMODE(st.st_mode)!=0o755:
        raise RuntimeError("W1_GROUPS protected directory invalid")
    fd=os.open(directory/"groups.jsonl",os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_nlink!=1
                or stat.S_IMODE(before.st_mode)!=0o444 or not 0<before.st_size<=16384):
            raise RuntimeError("W1_GROUPS protected ledger invalid")
        raw=bytearray()
        while len(raw)<=16384:
            chunk=os.read(fd,min(4096,16385-len(raw)))
            if not chunk:break
            raw.extend(chunk)
        after=os.fstat(fd)
        if (len(raw)>16384 or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
                !=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):
            raise RuntimeError("W1_GROUPS ledger changed/exceeded")
    finally:
        os.close(fd)
    raw=bytes(raw)
    if hashlib.sha256(raw).hexdigest()!=manifest["ledger_sha256"]:
        raise RuntimeError("W1_GROUPS root ledger digest differs")
    (output/"w1-native.audit.jsonl").write_bytes(raw)
    if not raw.endswith(b"\n") or len(raw.splitlines())!=5:
        raise RuntimeError("W1_GROUPS complete fixed ledger required")
    rows=[json.loads(line,object_pairs_hook=unique) for line in raw.splitlines()]
    if not tests.verify_groups(rows,sha,digest,arch):
        raise RuntimeError("W1_GROUPS independent TEST failed")
    record={"result":"native_groups_verified","candidate_sha":sha,"arch":arch,
            "binary_sha256":digest,"ledger_sha256":manifest["ledger_sha256"],"binding_sha256":binding_sha,
            "native_exit":0,"cleanup_scope":"owned_root_only_identities_retained"}
    write_json(output/"w1-result.json",record)
    return record

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
            "native/mac/icode_m0a1_process_groups.h",
            "native/mac/icode_m0a1_process_groups.c",
            "native/mac/tests/icode_m0a1_identity_lease.inc",
            "native/mac/tests/icode_m0a1_fixed_helpers.inc",
            "native/mac/tests/icode_m0a1_unused_identity.inc",
            "native/mac/tests/icode_m0a1_process_groups_native.c",
            "tests/test_macos_process_groups_native.py",
            "tests/test_macos_identity_snapshot_diagnostics.py",
            "tests/test_macos_identity_zombie_native.py",
            "docs/nbl/plans/2026-10-15-macos-identity-zombie-snapshot.md",
            "docs/nbl/plans/2026-10-15-macos-identity-snapshot-diagnostics.md",
            "tests/test_macos_process_groups.py",
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
        metadata["process_groups_binding_sha256"] = process_groups_binding(
            repo, build, binary, variant, output)
        metadata["groups_native"] = run_w1_groups(repo,build,output,sha,arch)
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
        require_w1_groups(metadata)
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
