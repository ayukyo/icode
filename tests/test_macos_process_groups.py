import errno
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAC = ROOT / "native/mac"
HELPER = MAC / "icode_m0a1_process_groups.c"
DRIVER = MAC / "tests/icode_m0a1_driver.c"

HARNESS = r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
int m0_process_credentials(uid_t);
int m0_process_getgroups(int,gid_t[]);
static int mode,identity_calls,group_calls;
static unsigned trace;
static uid_t identity(unsigned stage) {
    identity_calls++;
    trace=trace*10+stage;
    return mode==(int)stage ? 60001 : 60000;
}
uid_t test_getuid(void) { return identity(1); }
uid_t test_geteuid(void) { return identity(2); }
gid_t test_getgid(void) { return (gid_t)identity(3); }
gid_t test_getegid(void) { return (gid_t)identity(4); }
int test_process_getgroups(int capacity,gid_t groups[]) {
    group_calls++;
    trace=trace*10+(capacity==0 ? 5 : 6);
    if(mode==5 && capacity==0) { errno=EIO; return -1; }
    if(mode==6 && capacity==0) return 0;
    if(mode==7 && capacity==0) return 2;
    if(mode==8 && capacity==1) { errno=EINVAL; return -1; }
    if(mode==9 && capacity==1) return 0;
    if(mode==10 && capacity==1) return 2;
    if(capacity==0) return 1;
    if(capacity==1 && groups) {
        groups[0]=mode==11 ? 60001 : 60000;
        return 1;
    }
    errno=EINVAL;
    return -1;
}
/* Models the documented no-directory-account error boundary, not Darwin execution. */
int test_directory_getgroups(int capacity,gid_t groups[]) {
    (void)capacity; (void)groups;
    group_calls++; trace=trace*10+5;
    errno=EIO; return -1;
}
int main(int argc,char **argv) {
    if(argc!=2) return 2;
    mode=atoi(argv[1]); errno=EAGAIN;
    int result=m0_process_credentials(60000);
    int saved=errno;
    printf("%d %d %d %u %d\n",result,identity_calls,group_calls,trace,saved);
    return 0;
}
'''

REAL = r'''
#define _POSIX_C_SOURCE 200809L
#include "icode_m0a1_process_groups.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
int main(void) {
    errno=0;
    int direct=getgroups(0,NULL), direct_errno=errno;
    errno=0;
    int wrapped=m0_process_getgroups(0,NULL), wrapped_errno=errno;
    if(direct<0 || direct!=wrapped || direct_errno!=wrapped_errno) return 2;
    gid_t *a=calloc((size_t)(direct ? direct : 1),sizeof(*a));
    gid_t *b=calloc((size_t)(direct ? direct : 1),sizeof(*b));
    if(!a || !b) return 3;
    int ar=getgroups(direct,a), br=m0_process_getgroups(direct,b);
    if(ar!=direct || br!=ar) return 4;
    for(int i=0;i<ar;i++) if(a[i]!=b[i]) return 5;
    free(a); free(b);
    errno=0;
    volatile int bad_capacity=-1;
    int bad=getgroups(bad_capacity,NULL), bad_errno=errno;
    errno=0;
    int actual=m0_process_getgroups(bad_capacity,NULL), actual_errno=errno;
    if(bad!=-1 || actual!=bad || actual_errno!=bad_errno || bad_errno!=EINVAL) return 6;
    printf("real count=%d errno=%d\n",direct,actual_errno);
    return 0;
}
'''

@unittest.skipUnless(sys.platform == "linux", "Linux software only; no native groups credit")
class TestMacProcessGroups(unittest.TestCase):
    def setUp(self):
        self.cc=shutil.which("cc")
        self.assertIsNotNone(self.cc, "required Linux cc unavailable; not a skip")

    def command(self, argv, cwd):
        p=subprocess.run(argv,cwd=cwd,capture_output=True,timeout=30,check=False)
        self.assertLessEqual(len(p.stdout)+len(p.stderr),65536,"software output exceeded")
        return p

    def actual_predicate(self):
        source=DRIVER.read_text(encoding="utf-8")
        found=re.search(r"static int credentials\(uid_t uid\) \{.*?\n\}",source,re.S)
        self.assertIsNotNone(found,"baseline predicate extraction is infrastructure, not RED")
        self.assertTrue(source.startswith("#define _DARWIN_C_SOURCE 1\n"))
        return found.group(0).replace("static int credentials(","int m0_process_credentials(",1)

    def probe(self, mode):
        with tempfile.TemporaryDirectory(prefix="icode-process-groups-") as tmp:
            d=Path(tmp)
            harness=d/"probe.c"; harness.write_text(HARNESS,encoding="ascii")
            production=HELPER
            macros=["-Dgetuid=test_getuid","-Dgeteuid=test_geteuid",
                    "-Dgetgid=test_getgid","-Dgetegid=test_getegid"]
            if not HELPER.exists():
                # Compile the real old predicate, with only external OS boundary substituted.
                production=d/"legacy.c"
                production.write_text("#define _POSIX_C_SOURCE 200809L\n"
                    "#include <errno.h>\n#include <unistd.h>\n"+self.actual_predicate()+"\n",
                    encoding="ascii")
                macros.append("-Dgetgroups=test_directory_getgroups")
            else:
                macros.append("-Dgetgroups=test_process_getgroups")
            obj=d/"groups.o"; binary=d/"probe"
            built=self.command([self.cc,"-std=c11","-Wall","-Wextra","-Werror",
                "-I",str(MAC),*macros,"-c",str(production),"-o",str(obj)],d)
            self.assertEqual(built.returncode,0,built.stderr.decode("utf-8","replace"))
            linked=self.command([self.cc,"-std=c11","-Wall","-Wextra","-Werror",
                str(harness),str(obj),"-o",str(binary)],d)
            self.assertEqual(linked.returncode,0,linked.stderr.decode("utf-8","replace"))
            actual=self.command([str(binary),str(mode)],d)
            self.assertEqual(actual.returncode,0,actual.stderr)
            self.assertEqual(actual.stderr,b"")
            return tuple(int(x) for x in actual.stdout.decode("ascii").split())

    def test_no_directory_account_reads_actual_process_vector(self):
        result,ids,groups,trace,saved=self.probe(0)
        self.assertEqual(result,0,"PROCESS_VECTOR_REJECTED_BY_DIRECTORY_READER")
        self.assertEqual((ids,groups,trace,saved),(4,2,123456,errno.EAGAIN))

    def test_strict_identity_order_and_short_circuit(self):
        for stage in range(1,5):
            with self.subTest(stage=stage):
                result,ids,groups,trace,saved=self.probe(stage)
                self.assertEqual((result,ids,groups,trace,saved),
                    (errno.EPERM,stage,0,int("1234"[:stage]),errno.EAGAIN))

    def test_count_type_number_read_type_number_and_value(self):
        for mode in range(5,12):
            with self.subTest(mode=mode):
                result,ids,groups,trace,saved=self.probe(mode)
                self.assertEqual(result,errno.EPERM)
                self.assertEqual((ids,groups,trace),(4,1,12345) if mode<=7 else (4,2,123456))
                self.assertEqual(saved,errno.EIO if mode==5 else errno.EINVAL if mode==8 else errno.EAGAIN)

    def test_real_public_wrapper_return_and_errno(self):
        self.assertTrue(HELPER.is_file(),"missing TU is infrastructure, not valid RED")
        with tempfile.TemporaryDirectory(prefix="icode-groups-real-") as tmp:
            d=Path(tmp); c=d/"real.c"; binary=d/"real"
            c.write_text(REAL,encoding="ascii")
            p=self.command([self.cc,"-std=c11","-Wall","-Wextra","-Werror","-I",str(MAC),
                str(c),str(HELPER),"-o",str(binary)],d)
            self.assertEqual(p.returncode,0,p.stderr)
            actual=self.command([str(binary)],d)
            self.assertEqual(actual.returncode,0,actual.stderr)
            self.assertEqual(actual.stderr,b"")
            self.assertRegex(actual.stdout.decode("ascii"),r"^real count=\d+ errno=22\n$")

    def test_macro_pollution_is_explicit_compile_negative_control(self):
        self.assertTrue(HELPER.is_file(),"missing TU is infrastructure, not valid RED")
        for definition in ("_DARWIN_C_SOURCE=1","_DARWIN_UNLIMITED_GETGROUPS=1",
                           "_POSIX_C_SOURCE=199309L"):
            with self.subTest(definition=definition), tempfile.TemporaryDirectory(prefix="icode-groups-macro-") as tmp:
                d=Path(tmp)
                p=self.command([self.cc,"-std=c11","-Wall","-Wextra","-Werror","-I",str(MAC),
                    "-D"+definition,"-c",str(HELPER),"-o",str(d/"bad.o")],d)
                self.assertNotEqual(p.returncode,0)
                self.assertIn(b"M0_PROCESS_GROUPS_FEATURE_MACRO",p.stderr)
                self.assertFalse((d/"bad.o").exists())

class TestProcessGroupsController(unittest.TestCase):
    def test_controller_preserves_formal_classification_and_calls_binding_gate(self):
        source=(ROOT/"scripts/run_macos_m0_ci.py").read_text(encoding="utf-8")
        self.assertIn('metadata["process_groups_binding_sha256"] = process_groups_binding(',source)
        self.assertLess(source.index('metadata["process_groups_binding_sha256"]'),
                        source.index('native = subprocess.run(argv'))
        self.assertIn('groups != ["_getgroups"]',source)
        self.assertIn('"-isysroot"',source)
        self.assertIn('"DARWIN_EXTSN" in declarations[0]',source)
        self.assertIn('failures[0][0]._testMethodName != "test_cap1_quota_semantic"',source)
        self.assertIn('"M0A1_QUOTA_REJECTION" not in failures[0][1]',source)

    @unittest.skipUnless(sys.platform in ("linux", "darwin"), "POSIX collector only")
    def test_real_collector_and_binding_rejections(self):
        import importlib.util
        import json
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location("groups_controller",ROOT/"scripts/run_macos_m0_ci.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(getattr(module,"process_groups_binding",None)),
                        "BINDING_OBSERVER_REQUIRED")
        original_popen=subprocess.Popen
        for mode in ("normal","extension","header_alias","wrong_sdk","overflow","exit","timeout"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="icode-binding-") as tmp:
                d=Path(tmp).resolve(strict=True); build=d/"build"; build.mkdir(); output=d/"output"; output.mkdir()
                sdk=d/"SDK"; sdk.mkdir(); other=d/"otherSDK"; other.mkdir()
                obj=build/"CMakeFiles/icode_m0a1_baseline.dir/icode_m0a1_process_groups.c.o"
                obj.parent.mkdir(parents=True); obj.write_bytes(b"software-object")
                binary=build/"icode_m0a1_baseline"; binary.write_bytes(b"software-image")
                argv=[sys.executable,"-c",str(HELPER),"-o",str(obj)]
                (build/"compile_commands.json").write_text(json.dumps([
                    {"directory":str(build),"file":str(HELPER),"arguments":argv}]),encoding="utf-8")
                def tool_boundary(command,**kwargs):
                    stdout=""; stderr=""; code=0
                    if "--version" in command:
                        stdout="software clang version\n"
                    elif "--show-sdk-path" in command:
                        stdout=str(sdk)+"\n"
                    elif "--show-sdk-version" in command:
                        stdout="software-sdk\n"
                    elif "-###" in command:
                        stderr='clang\n"-isysroot" '+json.dumps(str(other if mode=="wrong_sdk" else sdk))+"\n"
                    elif "-E" in command:
                        stdout='int getgroups(int, gid_t [])'+(' __asm("_getgroups$DARWIN_EXTSN")' if mode=="header_alias" else '')+';\n'
                    elif command[0]=="/usr/bin/nm":
                        stdout=" U _getgroups"+("$DARWIN_EXTSN" if mode=="extension" else "")+"\n"
                    else:
                        raise AssertionError("unexpected tool boundary: "+repr(command))
                    if mode=="overflow":
                        program="import sys;sys.stdout.write('x'*100000);sys.stdout.flush()"
                    elif mode=="timeout":
                        program="import time;time.sleep(60)"
                    else:
                        if mode=="exit": code=7
                        program="import sys;sys.stdout.write("+repr(stdout)+");sys.stderr.write("+repr(stderr)+");sys.exit("+str(code)+")"
                    return original_popen([sys.executable,"-c",program],**kwargs)
                with patch.object(module.subprocess,"Popen",side_effect=tool_boundary):
                    if mode=="normal":
                        digest=module.process_groups_binding(ROOT,build,binary,"baseline",output)
                        self.assertRegex(digest,r"^[0-9a-f]{64}$")
                        record=json.loads((output/"process-groups-binding.json").read_text())
                        self.assertEqual(record["symbols"]["groups-final-nm"],["_getgroups"])
                    elif mode=="timeout":
                        with patch.object(module.time,"monotonic",side_effect=[0,16]):
                            with self.assertRaisesRegex(RuntimeError,"timeout"):
                                module.process_groups_binding(ROOT,build,binary,"baseline",output)
                    else:
                        expected={"extension":"ordinary public", "header_alias":"declaration",
                                  "wrong_sdk":"actual compiler SDK", "overflow":"output exceeded",
                                  "exit":"command failed"}[mode]
                        with self.assertRaisesRegex(RuntimeError,expected):
                            module.process_groups_binding(ROOT,build,binary,"baseline",output)
                    if mode!="normal":
                        self.assertFalse((output/"process-groups-binding.json").exists())
                    if mode=="overflow":
                        self.assertLessEqual(sum(p.stat().st_size for p in output.iterdir()),65536)
