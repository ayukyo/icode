"""Fixed positive loopback configuration observation; software only, no system API calls."""
from __future__ import annotations
import ast
import contextlib
import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "scripts/run_windows_appcontainer_read_probe.py"
REVIEWER = ROOT / "tests/test_windows_appcontainer.py"
NATIVE = ROOT / "native/windows/icode_wfp_event_probe.c"
CORE = ROOT / "native/windows/icode_positive_loopback_config.inc"
PROFILE = "icode-" + "0" * 32
OLD_POSITIVE = "                try:\n                    capability_control = run_windows_appcontainer(\n                        capability_argv, cwd=scratch, timeout_seconds=12,\n                        process_limit=2, _diagnostic_profile_name=capability_profile_name,\n                        _diagnostic_runtime_acl=True,\n                        _diagnostic_runtime_roots=(staged_runtime,),\n                        _diagnostic_private_network_capability=True,\n                    )\n                except Exception as exc:  # noqa: BLE001 - diagnostic failure is inconclusive\n                    capability_control = WindowsJobResult(\n                        False, None, \"diagnostic_exception\", False,\n                        type(exc).__name__,\n                    )\n                if not capability_control.cleanup_ok:\n                    self.fail(\n                        \"private-network positive-control Job/profile/ACL cleanup did not verify: \"\n                        f\"{capability_control.detail}\"\n                    )\n"
C_STUB = r'''#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <wchar.h>
#define WINAPI
#define TRUE 1
#define FALSE 0
typedef int BOOL;
#define MAX_PATH 260
#define MAX_PROFILE_NAME 38
#define LOAD_LIBRARY_SEARCH_SYSTEM32 0x800
#define ERROR_SUCCESS 0U
#define ERROR_INVALID_DATA 13U
#define ERROR_INSUFFICIENT_BUFFER 122U
#define S_OK 0
typedef uint32_t DWORD;
typedef unsigned UINT;
typedef int32_t HRESULT;
typedef void *PSID;
typedef void *HMODULE;
typedef void *HANDLE;
typedef struct { PSID Sid; DWORD Attributes; } SID_AND_ATTRIBUTES, *PSID_AND_ATTRIBUTES;
struct fake_sid { int valid, value; };
static struct fake_sid target = {1, 7}, sids[4097];
static SID_AND_ATTRIBUTES array[4097];
static unsigned mode, derives, queries, sid_frees, arrays, derived_frees, libraries;
static unsigned loads, exports, forbidden, connect_calls, profile_calls, duplicate_free;
static unsigned freed[4097], release_stage;
static char receipt[4096];
static DWORD last_error = 5;
static int receipt_printf(const char *format, ...) {
    va_list arguments; va_start(arguments, format);
    int n = vsnprintf(receipt, sizeof(receipt), format, arguments);
    va_end(arguments); if (n < 0 || n >= (int)sizeof(receipt)) abort();
    return n;
}
static UINT GetSystemDirectoryW(wchar_t *out, UINT capacity) {
    if (mode == 17) return 0;
    if (mode == 18) return capacity;
    const wchar_t text[] = L"C:\\Windows\\System32";
    if (capacity <= wcslen(text)) abort();
    wcscpy(out, text); return (UINT)wcslen(text);
}
static DWORD GetLastError(void) { return last_error; }
static HMODULE LoadLibraryExW(const wchar_t *path, void *file, DWORD flags) {
    loads++;
    if (file || flags != LOAD_LIBRARY_SEARCH_SYSTEM32 ||
        wcscmp(path, L"C:\\Windows\\System32\\FirewallAPI.dll")) abort();
    if (mode == 19) { last_error = 126; return NULL; }
    return (HMODULE)(uintptr_t)1;
}
static DWORD WINAPI fake_query(DWORD *count, PSID_AND_ATTRIBUTES *entries) {
    queries++;
    if (*count || *entries || derives != 1 || libraries) abort();
    if (mode == 4 || mode == 26) return 5;
    *count = mode == 11 ? 4096 : mode == 12 ? 4097 : 2;
    *entries = array;
    if (mode == 2) { *count = 0; *entries = NULL; }
    if (mode == 3) *count = 0;
    if (mode == 5) *entries = NULL;
    if (mode == 6) sids[1].valid = 0;
    if (mode == 7) sids[0].value = sids[1].value = 7;
    if (mode == 8) array[1].Sid = array[0].Sid;
    if (mode == 9) array[0].Sid = array;
    if (mode == 10) array[0].Sid = &target;
    if (mode == 22) return 5;
    if (mode == 23) { *count = 0; *entries = (PSID_AND_ATTRIBUTES)&target; }
    if (mode == 24) array[0].Sid = NULL;
    return 0;
}
static void *GetProcAddress(HMODULE library, const char *name) {
    exports++;
    if (library != (HMODULE)(uintptr_t)1) abort();
    if (strcmp(name, "NetworkIsolationGetAppContainerConfig")) { forbidden++; return NULL; }
    if (mode == 20) { last_error = 127; return NULL; }
    return (void *)fake_query;
}
static HRESULT DeriveAppContainerSidFromAppContainerName(const wchar_t *name, PSID *sid) {
    derives++;
    if (wcsncmp(name, L"icode-", 6) || *sid) abort();
    if (mode == 21) return (HRESULT)0x80004005U;
    if (mode == 25) return 0;
    *sid = &target; return 0;
}
static int IsValidSid(PSID sid) { return sid && ((struct fake_sid *)sid)->valid; }
static int EqualSid(PSID left, PSID right) {
    return ((struct fake_sid *)left)->value == ((struct fake_sid *)right)->value;
}
static HANDLE GetProcessHeap(void) { return (HANDLE)(uintptr_t)2; }
static int HeapFree(HANDLE heap, DWORD flags, void *pointer) {
    if (heap != (HANDLE)(uintptr_t)2 || flags) abort();
    if (pointer == array) { if (release_stage > 2) forbidden++; release_stage = 2; arrays++; return mode != 14; }
    for (unsigned i = 0; i < 4097; i++) if (pointer == &sids[i]) {
        if (release_stage > 1) forbidden++; release_stage = 1;
        if (freed[i]++) duplicate_free++;
        sid_frees++; return mode != 13 || i != 1;
    }
    forbidden++; return 0;
}
static PSID FreeSid(PSID sid) {
    if (release_stage > 3) forbidden++; release_stage = 3;
    if (sid != &target || derived_frees++) { forbidden++; return sid; }
    return mode == 15 ? sid : NULL;
}
static int FreeLibrary(HMODULE library) {
    if (library != (HMODULE)(uintptr_t)1 || libraries++) abort();
    release_stage = 4;
    return mode != 16 && mode != 26;
}
/* These counted TEST symbols are never OS calls or network/profile mutations. */
int NetworkIsolationSetAppContainerConfig(DWORD n, void *p) { (void)n; (void)p; forbidden++; return 5; }
int connect(int a, void *b, int c) { (void)a; (void)b; (void)c; connect_calls++; return -1; }
int CreateAppContainerProfile(void) { profile_calls++; return -1; }
ACTUAL_PROFILE_VALIDATOR
#define printf receipt_printf
ACTUAL_CONFIG_TU
#undef printf
static int actual_mode_dispatch(int argc, wchar_t **argv) {
ACTUAL_FIXED_MODE_BRANCH
    return 2;
}
int main(int argc, char **argv) {
    if (argc != 2) return 90;
    mode = (unsigned)strtoul(argv[1], NULL, 10);
    for (unsigned i = 0; i < 4097; i++) {
        sids[i] = (struct fake_sid){1, (int)i + 100};
        array[i] = (SID_AND_ATTRIBUTES){&sids[i], 0xFFFFFFFFU};
    }
    if (mode != 1) sids[1].value = 7;
    if (mode == 11) sids[4095].value = 7;
    if (mode == 11) sids[1].value = 8;
    wchar_t *arguments[] = {L"fixed-helper", L"--observe-positive-loopback-config",
        mode == 99 ? L"bad" : L"icode-00000000000000000000000000000000"};
    int result = actual_mode_dispatch(3, arguments);
    fputs(receipt, stdout);
    printf("COUNTS %d %u %u %u %u %u %u %u %u %u %u %u %u\n", result, derives, queries,
        sid_frees, arrays, derived_frees, libraries, loads, exports,
        forbidden, connect_calls, profile_calls, duplicate_free);
    return result;
}
'''

def sample(phase="pre"):
    return {"schema_version":1,"scope":"positive_loopback_config_sample","status":"complete",
        "api_stage":"query","api_code":0,"entry_count":0,"target_match":False,"target_attributes":None,
        "sid_frees_attempted":0,"sid_frees_confirmed":0,"array_release":"not_acquired",
        "derived_sid_release":"confirmed","library_release":"confirmed","phase":phase,
        "process_reaped":True,"cleanup":"confirmed","observation_complete":True}


def c_body(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 1
    for index in range(opening + 1, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError("actual C function infrastructure truncated")


class TestPositiveLoopbackConfig(unittest.TestCase):
    def execute_positive(self, *, pre_stop=False, post_stop=False, clean=True, launch_error=False,
                         json_notice=None, comparison=None, unknown=None):
        source = REVIEWER.read_text(encoding="utf-8")
        start_marker = "                loopback_profile = capability_profile_name"
        if start_marker not in source:
            start_marker = "                try:\n                    capability_control = run_windows_appcontainer("
        start = source.index(start_marker)
        end = source.index("                expected_capability_payload = json.dumps(", start)
        block = textwrap.dedent(source[start:end])
        events, observed, notices, launches = [], [], [], []
        token = N(verified=True, package_sid_match=True)
        result = N(cleanup_ok=clean, child_token_receipt=token, detail="original-first",
                   executed=True, exit_code=105)
        def observe(executable, profile, phase):
            events.append(phase);observed.append((profile, phase))
            return sample(phase), pre_stop if phase == "pre" else post_stop
        def launch(*args, **kwargs):
            events.append("launch");launches.append((args, kwargs))
            if launch_error:
                raise OSError("original failure")
            return result
        def failed_result(*args):
            return N(cleanup_ok=args[3], child_token_receipt=None, detail=args[4],
                     executed=args[0], exit_code=args[1])
        namespace = dict(Path=Path, os=N(environ={"GITHUB_ACTIONS":"true","RUNNER_OS":"Windows",
            "ICODE_DIAGNOSTIC_WFP_PROBE_PATH":"fixed-helper"}),
            capability_profile_name=PROFILE, capability_argv=("fixed-positive-argv",),
            scratch=Path("fixed-scratch"),staged_runtime=Path("fixed-runtime"),
            _observe_positive_loopback_config=observe,
            _positive_loopback_unknown=(unknown if unknown is not None else
                lambda phase,status:dict(sample(phase),status=status)),
            _positive_loopback_comparison=(comparison if comparison is not None else
                lambda pre,post,**kwargs:{"comparison":"unknown"}),
            run_windows_appcontainer=launch,WindowsJobResult=failed_result,
            self=N(_workflow_json_notice=(json_notice if json_notice is not None else
                lambda *args:notices.append(args)),fail=self.fail))
        failure = None
        try:
            exec(compile(block, str(REVIEWER), "exec"), namespace)
        except AssertionError as error:
            failure = str(error)
        return N(events=events,observed=observed,notices=notices,launches=launches,failure=failure)

    def setUp(self):
        # Old real Reviewer code executes its positive launch, but samples zero
        # times. That is semantic RED BEFORE accessing a missing mode/file/API.
        actual = self.execute_positive()
        self.assertEqual(actual.events, ["pre", "launch", "post"],
                         "POSITIVE_LOOPBACK_OBSERVATION_MISSING: actual positive flow must sample pre/post")
        self.assertIsNone(actual.failure)
        self.assertEqual(actual.observed, [(PROFILE,"pre"),(PROFILE,"post")])
        args, kwargs = actual.launches[0]
        self.assertEqual(args, (("fixed-positive-argv",),))
        self.assertEqual(kwargs["_diagnostic_profile_name"], PROFILE)
        self.assertEqual(kwargs["timeout_seconds"], 12)
        self.assertEqual(kwargs["process_limit"], 2)
        self.assertIs(kwargs["_diagnostic_private_network_capability"], True)
        self.assertIs(kwargs["_diagnostic_runtime_acl"], True)
        tree = ast.parse(PARENT.read_text(encoding="utf-8"))
        nodes = [ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0)]
        nodes += [node for node in tree.body if isinstance(node,ast.FunctionDef) and
                  (node.name.startswith("_positive_loopback_") or
                   node.name == "_observe_positive_loopback_config")]
        self.api = dict(json=json,re=re,Path=Path,subprocess=subprocess,time=time,os=os,
                        ctypes=ctypes,wintypes=wintypes)
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),
                     str(PARENT),"exec"),self.api)

    @contextlib.contextmanager
    def c_probe(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "Linux software compiler infrastructure required")
        source = NATIVE.read_text(encoding="utf-8")
        validator = c_body(source, "static BOOL is_generated_profile_name(")
        branch = c_body(source, 'if (argc >= 2 && wcscmp(argv[1], L"--observe-positive-loopback-config")')
        probe = C_STUB.replace("ACTUAL_PROFILE_VALIDATOR",validator).replace(
            "ACTUAL_CONFIG_TU",CORE.read_text(encoding="utf-8")).replace("ACTUAL_FIXED_MODE_BRANCH",branch)
        with tempfile.TemporaryDirectory(prefix="loopback-config-software-") as temporary:
            binary = Path(temporary) / "stub"
            built = subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror",
                "-x","c","-","-o",str(binary)],input=probe.encode(),capture_output=True,timeout=20)
            self.assertEqual(built.returncode,0,built.stderr.decode("utf-8","replace"))
            def run(mode):
                actual = subprocess.run([str(binary),str(mode)],capture_output=True,timeout=2)
                self.assertLessEqual(len(actual.stdout)+len(actual.stderr),8192)
                self.assertFalse(actual.stderr)
                lines = actual.stdout.splitlines()
                counts = [int(x) for x in lines[-1].decode("ascii").split()[1:]]
                self.assertEqual(len(counts),13)
                self.assertEqual(actual.returncode,counts[0])
                self.assertEqual(counts[-4:],[0,0,0,0], "write/connect/profile/double-free")
                if mode == 99:
                    self.assertEqual(len(lines),1)
                    return None, counts
                self.assertEqual(len(lines),2)
                receipt = self.api["_positive_loopback_parse"](lines[0]+b"\n")
                return receipt, counts
            yield run

    def test_c_success_empty_and_maximum_ownership(self):
        with self.c_probe() as run:
            for mode,count,matched in ((0,2,True),(1,2,False),(2,0,False),(3,0,False),(11,4096,True)):
                with self.subTest(mode=mode):
                    result,calls=run(mode)
                    self.assertEqual((result["status"],result["entry_count"],result["target_match"]),
                                     ("complete",count,matched))
                    self.assertEqual(result["target_attributes"],0xFFFFFFFF if matched else None)
                    self.assertEqual(result["sid_frees_attempted"],count)
                    self.assertEqual(result["sid_frees_confirmed"],count)
                    self.assertEqual(calls[1:3],[1,1])
                    self.assertEqual(calls[3],count)
                    self.assertEqual(calls[4],0 if mode==2 else 1)
                    self.assertEqual(calls[5:9],[1,1,1,1])

    def test_c_query_error_is_not_empty_and_derive_hresult(self):
        with self.c_probe() as run:
            for mode in (4,21,22,26):
                result,calls=run(mode)
                self.assertEqual(result["status"],"api_error")
                self.assertIsNone(result["entry_count"])
                self.assertIsNone(result["target_match"])
                self.assertIsNone(result["target_attributes"])
                if mode==21:
                    self.assertEqual((result["api_stage"],result["api_code"]),("derive",0x80004005))
                    self.assertEqual(calls[2],0)
                    self.assertEqual(calls[5],0)
                else:
                    self.assertEqual((result["api_stage"],result["api_code"]),("query",5))
                    self.assertEqual(calls[2],1)
                self.assertEqual(calls[3:5],[0,0])

    def test_c_aliases_null_sid_and_duplicate_target_are_invalid(self):
        with self.c_probe() as run:
            for mode in (5,6,7,8,9,10,23,24,25):
                with self.subTest(mode=mode):
                    result,calls=run(mode)
                    self.assertEqual(result["status"],"invalid_data")
                    self.assertIsNone(result["target_match"])
                    self.assertIsNone(result["target_attributes"])
                    if mode==7:
                        self.assertEqual(calls[3:7],[2,1,1,1])
                    else:
                        self.assertEqual(calls[3:5],[0,0])
                    if mode in (10,23):
                        self.assertEqual(result["derived_sid_release"],"unknown")
                        self.assertEqual(calls[5],0)

    def test_c_all_release_failures_keep_original_query_result(self):
        with self.c_probe() as run:
            for mode in (13,14,15,16):
                with self.subTest(mode=mode):
                    result,calls=run(mode)
                    self.assertEqual((result["status"],result["api_stage"],result["api_code"]),
                                     ("complete","query",0))
                    self.assertEqual(self.api["_positive_loopback_cleanup"](result),"failed")
                    self.assertIsNone(result["target_match"])
                    self.assertIsNone(result["target_attributes"])
                    self.assertEqual(calls[3:7],[2,1,1,1])

    def test_c_loader_failures_and_returned_item_limit(self):
        with self.c_probe() as run:
            for mode,status in ((12,"limit_reached"),(17,"load_failed"),(18,"load_failed"),
                                (19,"load_failed"),(20,"unsupported")):
                result,calls=run(mode)
                self.assertEqual(result["status"],status)
                self.assertIsNone(result["target_match"])
                if mode==12:
                    self.assertIsNone(result["entry_count"])
                    self.assertEqual(calls[2:5],[1,0,0])
                    self.assertEqual(result["array_release"],"unknown")
                else:
                    self.assertEqual(calls[1:3],[0,0])
                if mode in (17,18):
                    self.assertEqual(calls[7:9],[0,0])

    def test_c_fixed_mode_cli_and_sdk_type_contract(self):
        with self.c_probe() as run:
            result,calls=run(99)
            self.assertIsNone(result)
            self.assertEqual(calls,[2]+[0]*12)
            result,calls=run(0)
            self.assertEqual(calls[1:3],[1,1])
        core = CORE.read_text(encoding="utf-8")
        self.assertIn("DWORD (WINAPI *PositiveLoopbackGetConfigFn)(DWORD *, PSID_AND_ATTRIBUTES *)",core)
        self.assertNotIn("NetworkIsolationFreeAppContainers",core)
        self.assertNotIn("LocalFree",core)
        self.assertNotIn("CoTaskMemFree",core)
        self.assertNotIn("FwpmFreeMemory",core)

    def test_parent_receipt_strict_schema_and_release_accounting(self):
        parse = self.api["_positive_loopback_parse"]
        wire = {k:v for k,v in sample().items() if k not in {
            "phase","process_reaped","cleanup","observation_complete"}}
        self.assertEqual(parse(json.dumps(wire).encode()+b"\n"),wire)
        changes = ({"schema_version":True},{"entry_count":True},{"api_code":-1},
                   {"target_attributes":True},{"status":[]},{"api_stage":{}},
                   {"array_release":[]},{"sid_frees_confirmed":1},
                   {"target_match":True,"target_attributes":0},{"extra":"hidden SID"},
                   {"status":"api_error"},{"api_code":None})
        for change in changes:
            with self.subTest(change=str(change)):
                value=dict(wire,**change)
                with self.assertRaises((ValueError,UnicodeError)):
                    parse(json.dumps(value).encode()+b"\n")
        raw=json.dumps(wire).encode()
        for bad in (raw,raw+b"\n\n",json.dumps(wire,indent=2).encode()+b"\n",
                    raw+b"\n{}",raw+b"\n"+raw+b"\n",b"X"*4097,
                    raw.replace(b'"schema_version": 1',b'"schema_version": 1,"schema_version": 1')+b"\n",
                    b"\xff\n"):
            with self.assertRaises((ValueError,UnicodeError)):
                parse(bad)

    def drive_parent(self, mode="normal"):
        with tempfile.TemporaryDirectory(prefix="loopback-parent-software-") as temporary:
            binary=Path(temporary)/"icode-wfp-event-probe.exe"
            binary.write_bytes(b"not executed")
            receipt={k:v for k,v in sample().items() if k not in {
                "phase","process_reaped","cleanup","observation_complete"}}
            streams={0:bytearray(json.dumps(receipt).encode()+b"\n"),1:bytearray()}
            if mode=="overflow":streams[0]=bytearray(b"X"*4097)
            if mode=="stderr":streams[1]=bytearray(b"X"*9000)
            if mode=="duplicate":streams[0]=bytearray(b'{"a":1,"a":2}\n')
            clock=[0.0];reads=[];actions=[];waits=[];launches=[]
            class Stream:
                def __init__(self,index):self.index=index
                def close(self):
                    if mode=="close_error":raise OSError("close failed")
            class Process:
                stdout=Stream(0);stderr=Stream(1);returncode=0
                def wait(self,timeout):
                    waits.append(timeout)
                    if mode=="unreaped" or mode=="kill_reap" and not actions or \
                            mode=="kill_reap" and actions[-1]=="terminate":
                        raise subprocess.TimeoutExpired("fixed",timeout)
                    self.returncode=9 if mode=="nonzero" else 0
                    return self.returncode
                def terminate(self):
                    actions.append("terminate")
                    if mode=="action_error":raise RuntimeError("termination request unavailable")
                def kill(self):actions.append("kill")
            process=Process()
            def launch(*args,**kwargs):
                launches.append((args,kwargs))
                if mode=="launch_failure":raise OSError("creation unavailable")
                if mode=="slow_creation":clock[0]+=3
                return process
            def chunk(stream,capacity):
                reads.append((stream.index,capacity))
                if mode in ("timeout","kill_reap","unreaped","action_error"):return b"",False
                data=bytes(streams[stream.index][:capacity]);del streams[stream.index][:capacity]
                return data,not streams[stream.index]
            namespace=self.api
            with patch.dict(namespace,_positive_loopback_pipe_chunk=chunk), \
                    patch.object(subprocess,"Popen",side_effect=launch), \
                    patch.object(time,"monotonic",side_effect=lambda:clock[0]), \
                    patch.object(time,"sleep",side_effect=lambda value:clock.__setitem__(0,clock[0]+value)):
                result,stop=namespace["_observe_positive_loopback_config"](binary,PROFILE,"pre")
            self.assertEqual(len(launches),1)
            args,kwargs=launches[0]
            self.assertEqual(args[0],[str(binary.resolve()),"--observe-positive-loopback-config",PROFILE])
            self.assertIs(kwargs["shell"],False)
            self.assertNotIn("capture_output",kwargs)
            self.assertTrue(all(1<=capacity<=4097 if index==0 else capacity==1 for index,capacity in reads))
            if mode=="slow_creation":self.assertFalse(reads)
            return result,stop,actions,waits

    def test_parent_bounded_pipe_and_actual_wait_receipt(self):
        result,stop,actions,waits=self.drive_parent()
        self.assertTrue(result["observation_complete"])
        self.assertTrue(result["process_reaped"])
        self.assertFalse(stop)
        self.assertEqual(actions,[])
        self.assertEqual(len(waits),1)
        self.assertLessEqual(waits[0],2.0)
        for mode in ("overflow","stderr","duplicate","nonzero","close_error"):
            with self.subTest(mode=mode):
                result,stop,actions,waits=self.drive_parent(mode)
                self.assertFalse(result["observation_complete"])
                self.assertIsNone(result["target_match"])
                self.assertTrue(result["process_reaped"])
                self.assertFalse(stop)

    def test_parent_launch_timeout_terminate_kill_and_unreaped_stop(self):
        for mode in ("launch_failure","slow_creation","timeout","kill_reap","unreaped","action_error"):
            with self.subTest(mode=mode):
                result,stop,actions,waits=self.drive_parent(mode)
                self.assertFalse(result["observation_complete"])
                self.assertIsNone(result["target_match"])
                if mode=="launch_failure":
                    self.assertEqual(result["status"],"launch_failed")
                    self.assertFalse(result["process_reaped"])
                    self.assertFalse(stop)
                    self.assertFalse(waits)
                elif mode=="unreaped":
                    self.assertEqual(actions,["terminate","kill"])
                    self.assertEqual(waits,[2.0,2.0])
                    self.assertTrue(stop)
                    self.assertFalse(result["process_reaped"])
                else:
                    self.assertEqual(result["status"],"timed_out")
                    self.assertTrue(result["process_reaped"])
                    self.assertFalse(stop)
                    self.assertEqual(actions,["terminate","kill"] if mode=="kill_reap" else ["terminate"])
                    self.assertEqual(waits,[2.0,2.0] if mode=="kill_reap" else [2.0])

    def test_two_endpoints_drift_and_parent_token_binding(self):
        compare=self.api["_positive_loopback_comparison"]
        token=N(verified=True,package_sid_match=True)
        pre,post=sample(),sample("post")
        self.assertEqual(compare(pre,post,same_parent_profile=True,token_receipt=token)["comparison"],
                         "consistent_endpoints")
        for key,value in (("target_match",True),("target_attributes",4),("entry_count",1)):
            changed=dict(post,**{key:value})
            self.assertEqual(compare(pre,changed,same_parent_profile=True,token_receipt=token)["comparison"],
                             "observed_drift")
        for changed in (dict(post,status="api_error"),dict(post,process_reaped=False),
                        dict(post,cleanup="unknown"),dict(post,observation_complete=False),
                        dict(post,phase="pre")):
            self.assertEqual(compare(pre,changed,same_parent_profile=True,token_receipt=token)["comparison"],"unknown")
        for binding,receipt in ((False,token),(True,None),(True,N(verified=False,package_sid_match=True)),
                                (True,N(verified=True,package_sid_match=False))):
            self.assertEqual(compare(pre,post,same_parent_profile=binding,token_receipt=receipt)["comparison"],"unknown")

    def test_real_positive_flow_stop_and_first_error_priority(self):
        self.assertEqual(self.execute_positive().events,["pre","launch","post"])
        pre=self.execute_positive(pre_stop=True)
        self.assertEqual(pre.events,["pre"])
        self.assertIn("pre helper was not reaped",pre.failure)
        self.assertFalse(pre.launches)
        post=self.execute_positive(post_stop=True)
        self.assertEqual(post.events,["pre","launch","post"])
        self.assertIn("post helper was not reaped",post.failure)
        self.assertTrue(any("first result preserved" in name for name,data in post.notices))
        failure=self.execute_positive(clean=False)
        self.assertEqual(failure.events,["pre","launch"])
        self.assertIn("original-first",failure.failure)
        raised=self.execute_positive(launch_error=True)
        self.assertEqual(raised.events,["pre","launch"])
        self.assertIn("OSError",raised.failure)

    def test_actual_peek_boundary_is_bounded_without_reader_thread(self):
        function=self.api["_positive_loopback_pipe_chunk"]
        available=N(value=20)
        reads=[]
        def peek(*args):
            args[4].value=available.value
            return True
        class Api:
            def __init__(self):self.PeekNamedPipe=peek
        fake=N(WinDLL=lambda *args,**kwargs:Api(),c_void_p=object,
               POINTER=lambda value:object,byref=lambda value:value)
        types=N(HANDLE=object,DWORD=lambda:N(value=0),BOOL=object)
        with patch.dict(sys.modules,msvcrt=N(get_osfhandle=lambda fd:fd)), \
                patch.dict(self.api,ctypes=fake,wintypes=types), \
                patch.object(os,"read",side_effect=lambda fd,size:reads.append(size) or b"X"*size):
            data,eof=function(N(fileno=lambda:8),3)
        self.assertEqual((data,eof),(b"XXX",False))
        self.assertEqual(reads,[3])
        core=CORE.read_text(encoding="utf-8")
        self.assertNotRegex(core,r"\b(?:NetworkIsolationSetAppContainerConfig|connect|socket|CreateAppContainerProfile)\s*\(")


if __name__=="__main__":
    unittest.main()
