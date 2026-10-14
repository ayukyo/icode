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
