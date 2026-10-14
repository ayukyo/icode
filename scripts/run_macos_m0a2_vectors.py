import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import unittest
from scripts.run_macos_m0_ci import checked_text,process_groups_binding,run_suite,write_json

def bounded_native(argv,deadline_ns):
    buffers=[bytearray(),bytearray()]
    process=subprocess.Popen(argv,cwd="/",stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    reason=None
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ,0)
            selector.register(process.stderr,selectors.EVENT_READ,1)
            while selector.get_map():
                remaining=(deadline_ns-time.clock_gettime_ns(time.CLOCK_MONOTONIC))/1_000_000_000
                if remaining<=0:
                    reason="timeout"
                    break
                for key,_ in selector.select(min(remaining,0.1)):
                    room=65536-len(buffers[0])-len(buffers[1])
                    chunk=os.read(key.fileobj.fileno(),min(4096,room+1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(chunk)>room:
                        buffers[key.data].extend(chunk[:room])
                        reason="output_exceeded"
                        break
                    else:
                        buffers[key.data].extend(chunk)
                if reason:
                    break
            if not reason:
                try:
                    process.wait(timeout=max(0.001,(deadline_ns-time.clock_gettime_ns(time.CLOCK_MONOTONIC))/1_000_000_000))
                except subprocess.TimeoutExpired:
                    reason="timeout"
    except (TimeoutError,OSError) as error:
        reason="interrupted:"+type(error).__name__
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except OSError:
                # Native root has its own bounded alarm. No cleanup credit here.
                pass
        try:
            process.wait(timeout=2)
        except (subprocess.TimeoutExpired,TimeoutError,OSError):
            reason=reason or "exit_unknown"
        for stream in (process.stdout,process.stderr):
            try:
                stream.close()
            except OSError:
                reason=reason or "pipe_close_unknown"
    return {"native_exit":process.returncode,"reason":reason,
            "stdout":bytes(buffers[0]),"stderr":bytes(buffers[1]),"complete":reason is None}

def prepare_build(repo,build,output,with_source,deadline_ns):
    executable=shutil.which("cmake")
    if executable is None:
        raise RuntimeError("CMake unavailable; not native RED")
    cmake=Path(executable).resolve(strict=True)
    if not cmake.is_file() or not os.access(cmake,os.X_OK):
        raise RuntimeError("actual CMake executable unavailable")
    configuration=[str(cmake),"-S",str(repo/"native/mac"),"-B",str(build),"-DM0_BUILD_SOURCE=ON"]
    commands=[
        ("configure-baseline",configuration+["-DM0_BUILD_VECTORS_SOURCE=OFF"]),
        ("build-baseline",[str(cmake),"--build",str(build),"--target","icode_m0a1_vectors_baseline","--parallel","1"]),
    ]
    if with_source:
        commands.extend([
            ("configure-source",configuration+["-DM0_BUILD_VECTORS_SOURCE=ON"]),
            ("build-source",[str(cmake),"--build",str(build),"--target","icode_m0a1_vectors_source","--parallel","1"]),
        ])
    build_deadline=min(deadline_ns,time.clock_gettime_ns(time.CLOCK_MONOTONIC)+90_000_000_000)
    for name,argv in commands:
        actual=bounded_native(argv,build_deadline)
        (output/(name+".stdout")).write_bytes(actual["stdout"])
        (output/(name+".stderr")).write_bytes(actual["stderr"])
        write_json(output/(name+".json"),{"argv":argv,"native_exit":actual["native_exit"],
            "reason":actual["reason"],"complete":actual["complete"],
            "stdout_sha256":hashlib.sha256(actual["stdout"]).hexdigest(),
            "stderr_sha256":hashlib.sha256(actual["stderr"]).hexdigest()})
        if type(actual["native_exit"]) is not int or actual["native_exit"]!=0 or actual["complete"] is not True or actual["reason"] is not None:
            raise RuntimeError("bounded build failed; not semantic RED: "+name)

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key]=value
    return result

def collect_ledger(manifest):
    path=Path(manifest["root_directory"])
    identity=path.lstat()
    if (not stat.S_ISDIR(identity.st_mode) or identity.st_uid!=0
            or stat.S_IMODE(identity.st_mode)!=0o755):
        raise RuntimeError("protected vectors directory invalid")
    fd=os.open(path/"vectors.jsonl",os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_nlink!=1
                or stat.S_IMODE(before.st_mode)!=0o444 or not 0<before.st_size<=2*1024*1024):
            raise RuntimeError("protected vectors ledger invalid")
        data=bytearray()
        while len(data)<=2*1024*1024:
            chunk=os.read(fd,min(4096,2*1024*1024+1-len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after=os.fstat(fd)
        def stamp(value):
            return tuple(getattr(value,key) for key in
                         ("st_dev","st_ino","st_mode","st_uid","st_nlink","st_size","st_mtime_ns","st_ctime_ns"))
        if len(data)>2*1024*1024 or len(data)!=before.st_size or stamp(before)!=stamp(after):
            raise RuntimeError("vectors ledger changed or exceeded")
    finally:
        os.close(fd)
    raw=bytes(data)
    if hashlib.sha256(raw).hexdigest()!=manifest["ledger_sha256"]:
        raise RuntimeError("vectors ledger digest differs")
    return raw

def run_vectors(repo,build,output,metadata):
    phase=metadata["phase"];variant=metadata["variant"]
    binary=build/("icode_m0a1_vectors_"+variant)
    if binary.is_symlink() or not binary.is_file() or not os.access(binary,os.X_OK):
        raise RuntimeError("native vectors binary missing; never semantic RED")
    binary=binary.resolve(strict=True)
    if binary.parent!=build or not 0<binary.stat().st_size<=16*1024*1024:
        raise RuntimeError("vectors binary escaped/bounds")
    image=binary.read_bytes()
    if len(image)!=binary.stat().st_size:
        raise RuntimeError("vectors binary changed")
    digest=hashlib.sha256(image).hexdigest()
    metadata["binary_sha256"]=digest
    (output/binary.name).write_bytes(image)
    binding=output/"binding";binding.mkdir(mode=0o700)
    metadata["binding_sha256"]=process_groups_binding(repo,build,binary,"vectors_"+variant,binding)
    argv=["/usr/bin/sudo","-n","--","/usr/bin/env","-i","PATH=/usr/bin:/bin",
          str(binary),metadata["candidate_sha"],digest,format(metadata["deadline_ns"],"016x")]
    if time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=metadata["deadline_ns"]:
        raise RuntimeError("shared vectors deadline expired before root launch")
    actual=bounded_native(argv,metadata["deadline_ns"])
    stdout=actual["stdout"];stderr=actual["stderr"]
    (output/"native.stdout.json").write_bytes(stdout)
    (output/"native.stderr.log").write_bytes(stderr)
    metadata.update({k:actual[k] for k in ("native_exit","reason","complete")})
    metadata.update({"stdout_sha256":hashlib.sha256(stdout).hexdigest(),
                     "stderr_sha256":hashlib.sha256(stderr).hexdigest()})
    write_json(output/"metadata.json",metadata)
    if (actual["native_exit"]!=0 or not actual["complete"] or actual["reason"] is not None
            or len(stdout)>512 or len(stderr)>65536 or len(stdout)+len(stderr)>65536 or stderr):
        raise RuntimeError("native vectors infrastructure failure/overflow; never quota RED")
    manifest=json.loads(stdout,object_pairs_hook=unique)
    if (type(manifest) is not dict or set(manifest)!={"version","root_directory","ledger_sha256","cases"}
            or type(manifest["version"]) is not int or manifest["version"]!=1
            or type(manifest["cases"]) is not int or manifest["cases"]!=(2 if phase=="red" else 24)
            or type(manifest["root_directory"]) is not str
            or not re.fullmatch(r"/private/var/icode-m0a1\.[A-Za-z0-9]+",manifest["root_directory"])
            or type(manifest["ledger_sha256"]) is not str
            or not re.fullmatch("[0-9a-f]{64}",manifest["ledger_sha256"])):
        raise RuntimeError("vectors manifest schema/identity invalid")
    raw=collect_ledger(manifest)
    (output/"vectors.audit.jsonl").write_bytes(raw)
    metadata["ledger_sha256"]=hashlib.sha256(raw).hexdigest()
    metadata["root_directory"]=manifest["root_directory"]
    previous=os.environ.get("ICODE_M0A2_EVIDENCE")
    try:
        os.environ["ICODE_M0A2_EVIDENCE"]=str(output)
        spec=importlib.util.spec_from_file_location("m0a2_frozen_observer",repo/"tests/test_macos_m0a2_vectors.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("vectors formal TEST unavailable")
        tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
        rows=tests.parse_vectors(raw,metadata)
        tests.TestVectorsNative.rows=rows;tests.TestVectorsNative.variant=variant
        formal=run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(tests.TestVectorsNative),
                         output/"native-tests.log")
    finally:
        if previous is None:
            os.environ.pop("ICODE_M0A2_EVIDENCE",None)
        else:
            os.environ["ICODE_M0A2_EVIDENCE"]=previous
    metadata["formal"]={"tests":formal.testsRun,"failures":len(formal.failures),
                        "errors":len(formal.errors),"skipped":len(formal.skipped)}
    write_json(output/"metadata.json",metadata)
    if formal.testsRun!=5 or formal.errors or formal.skipped:
        raise RuntimeError("vectors formal incomplete; never semantic RED")
    if phase=="red":
        observed=tests.operations(rows["baseline_third"])
        if (len(formal.failures)!=1 or formal.failures[0][0]._testMethodName!="test_cap2_quota_semantic"
                or "M0A2_CAP2_REJECTION" not in formal.failures[0][1]
                or len(observed)!=2 or any(e["rc"]<=0 or e["error"] or e["aux"]!=1 for e in observed)
                or any(e["current"]<3 for e in observed)):
            raise RuntimeError("RED must be actual first+third creation and sole quota assertion")
        result="vectors_semantic_RED_confirmed"
    elif not formal.wasSuccessful():
        raise RuntimeError("vectors SOURCE native GREEN failed")
    else:
        result="vectors_GREEN_only"
    total=0
    for path in output.parent.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("export symlink")
        if path.is_file():
            total+=path.stat().st_size
    if total+4096>16*1024*1024 or time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=metadata["deadline_ns"]:
        raise RuntimeError("vectors artifact budget exceeded")
    record={"version":1,"candidate_sha":metadata["candidate_sha"],"arch":metadata["arch"],
            "result":result,"cases":manifest["cases"],"binary_sha256":digest,
            "ledger_sha256":metadata["ledger_sha256"],"binding_sha256":metadata["binding_sha256"],
            "cleanup_scope":"owned_roots_and_observed_direct_parent_reaps","identities_retained":True,
            "M0a2_complete":False,"M0b_complete":False,"M1_enabled":False}
    write_json(output/"vectors-result.json",record)
    return record

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--build-dir",type=Path,required=True)
    parser.add_argument("--output-root",type=Path,required=True)
    parser.add_argument("--phase",choices=("red","both"),required=True)
    parser.add_argument("--expected-arch",choices=("arm64","x86_64"),required=True)
    args=parser.parse_args()
    if sys.platform!="darwin" or os.getuid()==0:
        raise RuntimeError("nonroot native macOS controller required")
    repo=Path(__file__).resolve().parents[1]
    temporary=Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    build=args.build_dir.absolute();root=args.output_root.absolute()
    if (build.parent.resolve()!=temporary or build.is_symlink() or build.exists() or root.is_symlink() or root.exists()
            or root.parent.resolve()!=temporary):
        raise RuntimeError("fresh bounded build/output required")
    root.mkdir(mode=0o700)
    deadline=time.clock_gettime_ns(time.CLOCK_MONOTONIC)+480_000_000_000
    if not 0<deadline<2**64:
        raise RuntimeError("deadline cannot fit fixed uint64 wire")
    def expired(signum,frame):
        raise TimeoutError("shared B480 deadline expired")
    previous_handler=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,480)
    job={"result":"ERROR_or_unaccepted_failure","deadline_ns":deadline,"cleanup":"unknown"}
    try:
        sha=checked_text(["git","rev-parse","HEAD"],repo)
        if not re.fullmatch("[0-9a-f]{40}",sha) or sha!=os.environ["GITHUB_SHA"]:
            raise RuntimeError("candidate differs")
        arch=platform.machine()
        if arch!=args.expected_arch:
            raise RuntimeError("native architecture differs")
        common={"candidate_sha":sha,"arch":arch,"kernel":platform.release(),"deadline_ns":deadline,
            "os_build":checked_text(["/usr/bin/sw_vers","-buildVersion"],repo),
            "os_version":checked_text(["/usr/bin/sw_vers","-productVersion"],repo),
            "run_id":os.environ["GITHUB_RUN_ID"],"job":os.environ["GITHUB_JOB"],
            "run_attempt":os.environ["GITHUB_RUN_ATTEMPT"]}
        if arch=="x86_64" and common["os_version"].split(".")[0]!="15":
            raise RuntimeError("Intel macOS15 required")
        sources=(
            "native/mac/tests/icode_m0a1_driver.c","native/mac/tests/icode_m0a1_fixed_helpers.inc",
            "native/mac/tests/icode_m0a1_unused_identity.inc","native/mac/tests/icode_m0a1_identity_lease.inc",
            "native/mac/tests/icode_m0a1_process_groups_native.c","native/mac/tests/icode_m0a2_vectors.c",
            "native/mac/icode_m0a1_limit.h","native/mac/tests/icode_m0a1_baseline.c",
            "native/mac/icode_m0a1_process_groups.h","native/mac/icode_m0a1_process_groups.c",
            "tests/test_macos_task_quota_probe.py","tests/test_macos_process_groups_native.py",
            "tests/test_macos_process_groups.py","tests/test_macos_m0a2_vectors.py",
            "tests/test_macos_m0a2_event_diagnostics.py",
            "tests/test_macos_identity_snapshot_diagnostics.py",
            "tests/test_macos_identity_zombie_native.py",
            "docs/nbl/plans/2026-10-15-macos-identity-zombie-snapshot.md",
            "docs/nbl/plans/2026-10-15-macos-vector-fd8-reservation.md",
            "docs/nbl/plans/2026-10-15-macos-identity-snapshot-diagnostics.md",
            "docs/nbl/plans/2026-10-14-macos-m0a2-event-diagnostics.md",
            "scripts/run_macos_m0_ci.py","scripts/run_macos_m0a2_vectors.py",
            "native/mac/CMakeLists.txt",".github/workflows/ci.yml",
            "docs/nbl/specs/2026-10-13-macos-task-identity-quota-design.md",
            "docs/nbl/plans/2026-10-13-macos-task-identity-quota-m0.md",
            "docs/nbl/specs/2026-10-14-macos-m0a2-quota-design.md",
            "docs/nbl/plans/2026-10-14-macos-m0a2-vectors.md")
        common["source_hashes"]={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in sources}
        prepare_build(repo,build,root,args.phase=="both",deadline)
        records=[]
        for phase in (("red","green") if args.phase=="both" else ("red",)):
            output=root/phase;output.mkdir(mode=0o700)
            metadata={**common,"phase":phase,"variant":"baseline" if phase=="red" else "source",
                      "result":"ERROR_or_unaccepted_failure","cleanup":"unknown"}
            if phase=="green":
                path="native/mac/icode_m0a1_limit.c"
                metadata["source_hashes"]={**common["source_hashes"],
                    path:hashlib.sha256((repo/path).read_bytes()).hexdigest()}
            write_json(output/"metadata.json",metadata)
            try:
                records.append(run_vectors(repo,build,output,metadata))
                metadata["result"]=records[-1]["result"]
                write_json(output/"metadata.json",metadata)
            except Exception as error:
                metadata.update({"result":"ERROR_or_unaccepted_failure","error":str(error)})
                write_json(output/"metadata.json",metadata)
                raise
        if time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=deadline:
            raise TimeoutError("B deadline expired before combined publication")
        expected=["vectors_semantic_RED_confirmed"]
        if args.phase=="both":
            expected.append("vectors_GREEN_only")
        if [r["result"] for r in records]!=expected:
            raise RuntimeError("combined phase result mismatch")
        job.update({"candidate_sha":sha,"arch":arch,"records":records,
                    "cases":sum(r["cases"] for r in records),
                    "result":"B_vectors_GREEN_only" if args.phase=="both" else "B_TESTOnly_RED_only",
                    "M0a2_complete":False,"M0b_complete":False,"M1_enabled":False})
        write_json(root/"vectors-combined-result.json",job)
        return 0
    except Exception as error:
        job.update({"result":"ERROR_or_unaccepted_failure","error":str(error)})
        write_json(root/"vectors-error.json",job)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous_handler)

if __name__=="__main__":
    raise SystemExit(main())
