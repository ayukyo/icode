import errno
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "native/mac/tests/icode_m0a1_driver.c"

@unittest.skipUnless(sys.platform == "linux", "Linux-only emitter software test; no native credit")
class TestM0a1Diagnostics(unittest.TestCase):
    def run_emitter(self, mode):
        source = DRIVER.read_text(encoding="utf-8")
        found = re.search(
            r"/\* M0A1_DIAGNOSTIC_EMITTER_BEGIN \*/\n(.*?)"
            r"/\* M0A1_DIAGNOSTIC_EMITTER_END \*/", source, re.S)
        self.assertIsNotNone(found, "DIAGNOSTIC_EMITTER_ABSENT")
        self.assertEqual(sys.platform, "linux", "portable emitter proof is Linux only")
        cc = shutil.which("cc")
        self.assertIsNotNone(cc, "Linux C compiler required; not a skip")
        harness = r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
EMITTER
int main(int argc,char **argv) {
    if(argc!=2) return 2;
    int mode=atoi(argv[1]);
    if(mode==3 || mode==4) {
        sigset_t unblocked;
        if(signal(SIGPIPE,SIG_DFL)==SIG_ERR || sigemptyset(&unblocked)<0 ||
           sigaddset(&unblocked,SIGPIPE)<0 ||
           sigprocmask(SIG_UNBLOCK,&unblocked,NULL)<0) return 7;
        if(mode==3) {
            int endpoints[2];
            if(pipe(endpoints)<0 || close(endpoints[0])<0 ||
               dup2(endpoints[1],STDERR_FILENO)<0 || close(endpoints[1])<0) return 8;
        }
        if(setvbuf(stderr,NULL,_IONBF,0)) return 9;
        setup_fail(0,15,EPIPE,0,111);
        return 10;
    }
    if(mode==2) {
        if(!freopen("/dev/full","w",stderr)) return 3;
        if(setvbuf(stderr,NULL,_IONBF,0)) return 4;
    }
    errno=EAGAIN;
    if(mode==1) emit_diagnostic(UINT_MAX,UINT_MAX,INT_MIN,INT_MAX,INT_MIN);
    else emit_diagnostic(0,101,EPIPE,-1,-1);
    if(errno!=EAGAIN) return 5;
    if(mode==2 && !ferror(stderr)) return 6;
    return 0;
}
'''.replace("EMITTER", found.group(1))
        with tempfile.TemporaryDirectory(prefix="icode-m0a1-emit-") as tmp:
            directory = Path(tmp)
            cpath, binary = directory / "probe.c", directory / "probe"
            cpath.write_text(harness, encoding="ascii", newline="\n")
            built = subprocess.run(
                [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(cpath), "-o", str(binary)],
                capture_output=True, timeout=30, check=False)
            self.assertEqual(built.returncode, 0, built.stderr.decode("utf-8", "replace"))
            self.assertEqual(built.stdout, b"")
            actual = subprocess.run([str(binary), str(mode)], capture_output=True,
                                    timeout=5, check=False)
            self.assertEqual(actual.returncode, 111 if mode in (3, 4) else 0, actual.stderr)
            self.assertEqual(actual.stdout, b"")
            return actual.stderr

    def test_actual_diagnostic_fields_and_errno_preserved(self):
        expected = ("M0A1_DIAG version=1 case_index=0 stage=101 error="
                    + str(errno.EPIPE) + " detail=-1 result=-1\n").encode("ascii")
        self.assertEqual(self.run_emitter(0), expected)

    def test_integer_extremes_are_ascii_single_bounded_record(self):
        raw = self.run_emitter(1)
        self.assertLess(len(raw), 192)
        self.assertEqual(raw.count(b"\n"), 1)
        self.assertRegex(raw.decode("ascii"),
                         r"^M0A1_DIAG version=1 case_index=4294967295 stage=4294967295 "
                         r"error=-2147483648 detail=2147483647 result=-2147483648\n$")

    def test_write_failure_does_not_replace_callers_errno(self):
        self.assertEqual(self.run_emitter(2), b"")

    def test_setup_failure_preserves_exit_with_real_broken_pipe(self):
        with self.subTest(stderr="closed_read_end"):
            self.assertEqual(self.run_emitter(3), b"")
        with self.subTest(stderr="healthy_pipe_positive_control"):
            expected = ("M0A1_DIAG version=1 case_index=0 stage=15 error="
                        + str(errno.EPIPE) + " detail=0 result=111\n").encode("ascii")
            self.assertEqual(self.run_emitter(4), expected)
@unittest.skipUnless(sys.platform == "linux", "Linux gate observer software only; no native credit")
class TestM0a1GateObservation(unittest.TestCase):
    def run_gate(self, mode):
        source = DRIVER.read_text(encoding="utf-8")
        found = re.search(
            r"/\* M0A1_GATE_OBSERVER_BEGIN \*/\n(.*?)"
            r"/\* M0A1_GATE_OBSERVER_END \*/", source, re.S)
        self.assertIsNotNone(found, "GATE_OBSERVER_ABSENT")
        record = re.search(r"struct gate_record \{.*?\n\};", source, re.S)
        self.assertIsNotNone(record, "actual gate struct required")
        cc = shutil.which("cc")
        self.assertIsNotNone(cc, "Linux cc required; not a skip")
        harness = r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
RECORD
HELPER
int main(int argc,char **argv) {
    if(argc!=2) return 9;
    int mode=atoi(argv[1]);
    struct gate_record r={.magic=123,.version=7,.length=99,.phase=3,
        .error=EPERM,.pid=42,.uid=0,.euid=60001,.gid=0,.egid=60002,
        .groups=1,.group=UINT32_MAX};
    if(mode==1) {
        r.magic=r.version=r.length=r.phase=UINT32_MAX;
        r.error=r.pid=INT32_MIN;
        r.uid=r.euid=r.gid=r.egid=r.groups=r.group=UINT32_MAX;
    }
    if(mode==6) r.groups=0;
    if(mode==7) r.groups=2;
    if(mode==3) {
        if(!freopen("/dev/full","w",stderr) || setvbuf(stderr,NULL,_IONBF,0)) return 8;
    }
    if(mode==4) {
        int fds[2];
        if(signal(SIGPIPE,SIG_IGN)==SIG_ERR || pipe(fds)<0 ||
           close(fds[0])<0 || dup2(fds[1],2)<0 || close(fds[1])<0 ||
           setvbuf(stderr,NULL,_IONBF,0)) return 7;
    }
    struct gate_record before=r;
    errno=EAGAIN;
    if(mode==2) emit_gate_observation(0,1,60000,0,NULL);
    else if(mode==5) {
        for(unsigned i=0;i<7;i++) {
            emit_gate_observation(i,1,60000,1,&r);
            emit_gate_observation(i,2,60000,0,NULL);
        }
    } else emit_gate_observation(UINT_MAX,2,UINT32_MAX,1,&r);
    if(errno!=EAGAIN || memcmp(&r,&before,sizeof(r))) return 6;
    if((mode==3 || mode==4) && !ferror(stderr)) return 5;
    return mode==5 ? 2 : 0;
}
'''.replace("RECORD", record.group(0)).replace("HELPER", found.group(1))
        with tempfile.TemporaryDirectory(prefix="icode-m0a1-gate-") as tmp:
            directory = Path(tmp)
            cpath, binary = directory / "probe.c", directory / "probe"
            cpath.write_text(harness, encoding="ascii", newline="\n")
            built = subprocess.run(
                [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(cpath), "-o", str(binary)],
                capture_output=True, timeout=30, check=False)
            self.assertEqual(built.returncode, 0, built.stderr.decode("utf-8", "replace"))
            self.assertEqual(built.stdout, b"")
            actual = subprocess.run([str(binary), str(mode)], capture_output=True,
                                    timeout=5, check=False)
            self.assertEqual(actual.returncode, 2 if mode==5 else 0, actual.stderr)
            self.assertEqual(actual.stdout, b"")
            return actual.stderr

    def test_actual_fields_and_unsigned_group_positive_control(self):
        raw = self.run_gate(0)
        expected = (
            "M0A1_GATE_DIAG format_version=1 case_index=4294967295 slot=2 received=1 "
            "raw_magic=123 wire_version=7 length=99 pid=42 phase=3 error=" + str(errno.EPERM) +
            " expected_uid=4294967295 uid=0 euid=60001 gid=0 egid=60002 "
            "groups=1 group_observed=1 group=4294967295\n")
        self.assertEqual(raw, expected.encode("ascii"))

    def test_unsigned_extremes_and_group_failure_unknown(self):
        raw = self.run_gate(1).decode("ascii")
        expected = (
            "M0A1_GATE_DIAG format_version=1 case_index=4294967295 slot=2 received=1 "
            "raw_magic=4294967295 wire_version=4294967295 length=4294967295 "
            "pid=-2147483648 phase=4294967295 error=-2147483648 "
            "expected_uid=4294967295 uid=4294967295 euid=4294967295 "
            "gid=4294967295 egid=4294967295 groups=4294967295 group_observed=0 group=unknown\n")
        self.assertEqual(raw, expected)
        self.assertLess(len(raw.encode("ascii")), 512)

    def test_unreceived_record_has_no_fabricated_values(self):
        expected = (
            "M0A1_GATE_DIAG format_version=1 case_index=0 slot=1 received=0 "
            "raw_magic=unknown wire_version=unknown length=unknown pid=unknown "
            "phase=unknown error=unknown expected_uid=60000 uid=unknown euid=unknown "
            "gid=unknown egid=unknown groups=unknown group_observed=0 group=unknown\n")
        self.assertEqual(self.run_gate(2), expected.encode("ascii"))

    def test_non_single_group_is_not_observed(self):
        for mode, count in ((6, 0), (7, 2)):
            with self.subTest(groups=count):
                raw = self.run_gate(mode).decode("ascii")
                self.assertIn(" groups=" + str(count) + " group_observed=0 group=unknown\n", raw)
                self.assertNotIn("group=4294967295", raw)

    def test_failed_outputs_preserve_errno_and_exit(self):
        for mode in (3, 4):
            with self.subTest(mode=mode):
                self.assertEqual(self.run_gate(mode), b"")
        # Healthy output is required by the first test, so a silent helper cannot pass.

    def test_fixed_call_bound_and_root_only_integration(self):
        raw = self.run_gate(5)
        self.assertEqual(raw.count(b"\n"), 14)
        self.assertLess(len(raw), 14 * 512)
        self.assertTrue(all(len(line)+1 < 512 for line in raw.splitlines()))
        source = DRIVER.read_text(encoding="utf-8")
        self.assertEqual(source.count("emit_gate_observation("), 3)
        root = source[source.index("    if(wait_owned(pid,&status)<0)"):
                      source.index("    if(kq>=0) close(kq);")]
        self.assertIn("emit_gate_observation(index,1,(uint32_t)uid,configured_read_errno==0,&configured);", root)
        self.assertIn("emit_gate_observation(index,2,(uint32_t)uid,ready_attempted && ready_read_errno==0,&ready);", root)
        worker = source[source.index("static void trampoline("):source.index("static int valid_gate(")]
        self.assertNotIn("emit_gate_observation(", worker)
