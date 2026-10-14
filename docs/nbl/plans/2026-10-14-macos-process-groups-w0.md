# macOS POSIX process groups W0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 独立 POSIX TU 读取实际进程组，机械共享现有严格 credentials predicate，取得针对性软件证据与双架构实际绑定证据；W0 不解除 quota SOURCE 禁令。

**Architecture:** driver 保留 Darwin API 环境；新增私有 TU/头承载公共 getgroups 薄 wrapper 与原 predicate。baseline/未来 source 的共同 CMake target 使用同一 TU；controller 在原生运行前记录并拒绝错误 SDK/最终绑定，原七 case 及正式 classification 完全保留。W1 独立原生双组负控及同 PID exec 单组正控是后续单独完整 PLAN 的不可跳过 hard 门。

**Tech Stack:** C11、POSIX.1-2008、Apple SDK/Clang、CMake、Python 3.11 unittest、既有 GitHub 双原生架构 CI。

---

## 冻结、授权与证据边界

本轮只新建本文；没有执行 TEST/SOURCE、编译、CI、Git 或系统变更。技能的 worktree、自动执行与频繁 commit 建议服从用户本轮 PLAN ONLY、权威 WSL/main-only、root 独立发布要求；作者不调用执行技能。

工作区 `/home/orbbec/projects/icode`；起点 HEAD `2c593046e5a9aa4d0c36e04ae7b6bbb26c6625a5`；vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。权威 DESIGN 为 `docs/nbl/specs/2026-10-14-macos-process-groups-interface-design.md`，99 行，SHA-256 `8fb4484dce9c11f673fdbed623951b36f344ce62d5931f53b5260f92c4141367`，root 已全文阅读并取得 fresh SPEC → 不同 QUALITY 的 C0/I0/M0。root 三步真实 sequential-thinking 记录 `fe4453`：需求分解→公共 POSIX TU 方案→宏/绑定/错误信用风险；本作者不冒称另调 MCP。

三问已确认：真实缺陷为两个旧 Mach-O 都导入 `_getgroups$DARWIN_EXTSN`；现有实现为 driver 四处查询和七行 predicate；调用链为 trampoline→gate→payload，三处身份判定，wire 两处采样。旧两次 predicate 调用各自 errno 未直接观察，不能把目录解释说成唯一失败 syscall。Apple 固定主源、许可和采纳/暂缓/不适配已见批准 DESIGN §2；只借公共机制，不复制 APSL 代码。W0 不重开全部竞品研究。

| 基线文件 | SHA-256 |
| --- | --- |
| `native/mac/tests/icode_m0a1_driver.c` | `1fe2b712636ed31d51e9192783e977fd1e35657fcc434bf5960a7030e4fcfd43` |
| `native/mac/CMakeLists.txt` | `0480d7268b8baa6ff2935731d9430dcfe85362c4dd4ef97aa5cc23ac1d27be96` |
| `scripts/run_macos_m0_ci.py` | `770669a24e8aa9437b5c586a0d57c65d90aaf833a785eec70bdb575f346058ad` |
| `tests/test_macos_task_quota_probe.py` | `d0438e66bd356aefdfd2ebdd8edaa12529a88f18fb8c5556d2404c672291dafd` |

开始执行时先只读核对这些内容；漂移时 root 阅读实际 diff 再重审受影响资产，不覆盖用户变化。设计原文不修改。不得新建 `native/mac/icode_m0a1_limit.c`；不得改 wire72/96、setgroups→setgid→setuid、valid_gate、release、phase、exit、原七 case、正式 TEST、分类 oracle 或 quota SOURCE 构建门。

## 文件职责与顺序

| 文件 | 责任 |
| --- | --- |
| 新 `tests/test_macos_process_groups.py` | Linux 真实 TU 编译运行、旧实际 predicate 的可控语义 RED、错误/短路/errno、宏污染负控；不授 native 信用 |
| 新 `native/mac/icode_m0a1_process_groups.h`、`.c` | 两个固定私有函数，无 provider/测试开关 |
| `native/mac/tests/icode_m0a1_driver.c` | 删除旧 predicate；三个调用及两个 wire 采样迁移 |
| `native/mac/CMakeLists.txt` | 同一 TU 加入共同 target，导出实际编译命令 |
| `scripts/run_macos_m0_ci.py` | 新源码摘要、独立实际 SDK/头/object/final 绑定证据及拒绝门 |

不改 `.github/workflows/ci.yml`：现有 Ubuntu unittest 会发现新 TEST；现有 native job 构建 baseline、调用 controller 并上传 output，已能承载 W0 证据。无新增 native target、无 root lease/helper 重构。W1 原生资产不在 W0 留空实现。

### Task 1: 独立 TEST 作者冻结软件 TEST 与语义 RED

**Dependencies:** None
**Parallelizable:** No (TEST 冻结和有效 RED 先于不同作者 SOURCE)

- [ ] TEST 作者完整阅读 DESIGN、本文和当前 driver/CMake/controller/formal/diagnostic TEST，确认 baseline 哈希，记录 TEST 资产摘要。仅新增下列完整文件；SOURCE 作者此时不得动生产源码。

`tests/test_macos_process_groups.py` 完整资产：

```python
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
```

- [ ] 在改生产源码前只跑语义 RED 一项：

```bash
cd /home/orbbec/projects/icode
python3 -m unittest tests.test_macos_process_groups.TestMacProcessGroups.test_no_directory_account_reads_actual_process_vector -v
```

预期：编译/链接/运行全部成功，Python assertion 因 `result==EPERM` 而失败，含 `PROCESS_VECTOR_REJECTED_BY_DIRECTORY_READER`。记录真实命令、退出码、stdout/stderr、TEST hash、实际 legacy predicate hash 和 baseline driver hash。此模型只证明“真实旧 predicate 在已知目录错误边界拒绝有效进程组”，不声称 Linux 产生 Darwin alias，不授 quota/native RED。旧 Mach-O 的真实 alias 和所有组 unknown 是独立二进制/运行观察，不捏造原 errno。若只有 missing/import/compile/link 错误，或语义项意外通过，STOP NEEDS_CONTEXT，禁止移交 SOURCE。

- [ ] 原始 TEST 冻结并由 root 阅读；独立审查确认真实代码被编译、替身只在 OS 调用边界、没有测试专用生产接口。不同 SOURCE 作者收到有效 RED 后才能做 Task 2。

### Task 2: 不同 SOURCE 作者最小 TU 与调用迁移

**Dependencies:** Task 1
**Parallelizable:** No (必须先有效软件 RED，不能与 TEST 同作者)

- [ ] 新增 `native/mac/icode_m0a1_process_groups.h`，完整内容：

```c
#ifndef ICODE_M0A1_PROCESS_GROUPS_H
#define ICODE_M0A1_PROCESS_GROUPS_H
#include <sys/types.h>
int m0_process_getgroups(int capacity, gid_t groups[]);
int m0_process_credentials(uid_t uid);
#endif
```

- [ ] 新增 `native/mac/icode_m0a1_process_groups.c`，完整内容：

```c
#if defined(_DARWIN_C_SOURCE) || defined(_DARWIN_UNLIMITED_GETGROUPS)
#error M0_PROCESS_GROUPS_FEATURE_MACRO_DARWIN_BEFORE_HEADERS
#endif
#if defined(_POSIX_C_SOURCE) && _POSIX_C_SOURCE != 200809L
#error M0_PROCESS_GROUPS_FEATURE_MACRO_POSIX_CONFLICT
#endif
#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#include "icode_m0a1_process_groups.h"
#include <errno.h>
#include <unistd.h>
#if defined(_DARWIN_C_SOURCE) || defined(_DARWIN_UNLIMITED_GETGROUPS)
#error M0_PROCESS_GROUPS_FEATURE_MACRO_DARWIN_AFTER_HEADERS
#endif
int m0_process_getgroups(int capacity, gid_t groups[]) {
    return getgroups(capacity,groups);
}
int m0_process_credentials(uid_t uid) {
    gid_t g=0;
    if(getuid()!=uid || geteuid()!=uid || getgid()!=uid || getegid()!=uid ||
       m0_process_getgroups(0,NULL)!=1 || m0_process_getgroups(1,&g)!=1 || g!=uid) return EPERM;
    return 0;
}
```

任何 header 之前固定 POSIX，include 前后拒污染。wrapper 直接 return、不碰 errno。predicate 仅函数名/查询入口变化，原顺序/短路/EPERM/成功0机械保留。

- [ ] 对 driver 应用精确 patch：

```diff
--- a/native/mac/tests/icode_m0a1_driver.c
+++ b/native/mac/tests/icode_m0a1_driver.c
@@
 #define _DARWIN_C_SOURCE 1
 #include "icode_m0a1_limit.h"
+#include "icode_m0a1_process_groups.h"
@@
-static int credentials(uid_t uid) {
-    gid_t g=0;
-    if(getuid()!=uid || geteuid()!=uid || getgid()!=uid || getegid()!=uid ||
-       getgroups(0,NULL)!=1 || getgroups(1,&g)!=1 || g!=uid) return EPERM;
-    return 0;
-}
 static void send_gate(unsigned phase,int error) {
@@
-    r.gid=getgid(); r.egid=getegid(); gid_t g=0; int n=getgroups(1,&g);
+    r.gid=getgid(); r.egid=getegid(); gid_t g=0; int n=m0_process_getgroups(1,&g);
@@
-    e=credentials(uid);
+    e=m0_process_credentials(uid);
@@
-    e=credentials(uid);
+    e=m0_process_credentials(uid);
@@
-    if(protected_image(hash) || credentials(uid)) _exit(95);
+    if(protected_image(hash) || m0_process_credentials(uid)) _exit(95);
@@
-    gid_t g=0; r.groups=getgroups(1,&g); r.group=(int32_t)g;
+    gid_t g=0; r.groups=m0_process_getgroups(1,&g); r.group=(int32_t)g;
```

- [ ] CMake 精确 patch，原 source 存在性门不动：

```diff
--- a/native/mac/CMakeLists.txt
+++ b/native/mac/CMakeLists.txt
@@
 cmake_minimum_required(VERSION 3.20)
+set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
 project(icode_m0a1_experiment C)
@@
-  add_executable(${name} tests/icode_m0a1_driver.c ${implementation})
+  add_executable(${name} tests/icode_m0a1_driver.c icode_m0a1_process_groups.c ${implementation})
```

- [ ] 仅针对性软件 GREEN 和原 diagnostic/protocol 回归：

```bash
python3 -m unittest tests.test_macos_process_groups.TestMacProcessGroups tests.test_macos_m0a1_diagnostics tests.test_macos_task_quota_probe.TestM0a1Protocol -v
```

所有请求项必须实际执行、无 ERROR/SKIP；新 helper TEST 五项、原诊断十项、协议五项。Task3 的 controller TEST 先由 TEST 作者冻结，Task3 SOURCE 前单独观察其 assertion RED；它不进入上述 Task2 GREEN 命令。不启动原生 TestNativeM0a1，不在本机跑全量。宏污染项是预期编译失败的负控，不能数作语义 RED。记录实际计数而非依本文预填 PASS。

### Task 3: controller 实际绑定观察与拒绝门

**Dependencies:** Task 2
**Parallelizable:** No (绑定检查针对同一个真实 helper/最终候选)

- [ ] 在 `scripts/run_macos_m0_ci.py` 的 `import re` 后新增 `import selectors`、`import shlex`、`import signal`、`import time`。在 `def main():` 前新增以下完整函数；不改 checked_text/run_suite/classification。命令均 `shell=False`，15 秒 deadline；额外 compiler 输出最多 2 MiB、nm 256 KiB、其它64 KiB，逐块collector超界立即停止自有命令组，不进入原生运行。

```python
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
```

- [ ] `artifact_sources` 在 driver 条目后增加以下三条；原条目不删：

```python
            "native/mac/icode_m0a1_process_groups.h",
            "native/mac/icode_m0a1_process_groups.c",
            "tests/test_macos_process_groups.py",
```

- [ ] 在现有 Intel OS 版本检查后、`write_json(output / "metadata.json", metadata)` 前插入以下两行；source_hashes 已先绑定，任何失败走原 except，正式 classification 段逐字不动：

```python
        metadata["process_groups_binding_sha256"] = process_groups_binding(
            repo, build, binary, variant, output)
```

实际 `-###` 追踪固定编译 argv，记录实际 `-isysroot` 与 xcrun SDK路径/版本交叉核验；未知/不一致拒绝，不能用公开 Apple 头版本填充。预处理同一命令仅换 `-c/-o`，保存完整有界展开，核唯一公共声明；同一 object 与最终 Mach-O 都要求唯一普通 `_getgroups`，严拒扩展。符号通过只授绑定证据，不能代替运行。metadata 只增加摘要，完整记录独立文件，原 formal 16 KiB metadata 门保持；实际超过则拒绝而非放宽。该检查运行于原 root native 之前，不新增特权工具。

- [ ] 同 TEST 作者冻结下列 controller 软件测试，追加到 Task 1 TEST 文件；该项在 Task 3 SOURCE 前先跑，确认缺少观察门会产生 assertion RED（辅助回归门，不替代 Task 1 语义 RED）。

```python
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
```

第一项仅结构性调用接线检查。第二项执行真实 controller、真实 selector/pipe/子进程 collector、真实 JSON/trace/声明/nm 解析；只在固定外部工具启动边界代以真实 Python 子进程，避免在 Linux 冒称执行 Apple 工具。正常、扩展符号、扩展声明、错误SDK、超界、非零退出和受控到期均有正负控；到期用模拟 monotonic 越过 deadline，真实 sleeper 必须被自有进程组终止/回收。测试字节标明software，不进入formal evidence。实际 SDK/最终 Mach-O信用只由下阶段两实际原生job授予。若真实 trace/展开格式不同，保留原始证据，STOP；最小修正计划和相应 TEST 经重新审查，不静默放宽绑定门。

- [ ] 最小语法和既有回归：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_macos_process_groups tests.test_macos_m0a1_diagnostics tests.test_macos_task_quota_probe.TestM0a1Protocol -v
```

通过仅表示软件针对性验证；新 controller 定义由 Python parser 导入检查不执行 Mac 命令。非 Linux 项的 skip 不得记作 Linux helper 实际执行通过。

### Task 4: 双审、待验候选与 W0 线上观察

**Dependencies:** Task 3
**Parallelizable:** No (必须同一候选 SHA)

- [ ] SOURCE 作者七维自检；root 全文阅读实际 diff 与完整资产；fresh SPEC → 不同 QUALITY，两者均 C0/I0/M0 才发布待验候选。TEST/SOURCE 作者分离，审查者不得用本计划自审替代实际 SOURCE 审查。
- [ ] root 按现有授权进行必要本机 secret/submodule 检查及最小针对性回归；本作者不执行。root main-only 提交推送候选触发既有 CI，不创建额外分支/tag/worktree，不使用模型 KEY、不改系统。
- [ ] 两格 `macos-m0a1-finite`：ARM macos-latest 实际 arm64、Intel macos-15-intel 实际 x86_64；绑定 SHA、run/job/attempt、退出码和完整原 artifact。每格 `process-groups-binding.json`、编译 argv/实际 SDK展开、object/final 普通符号必须有效，原七 case 必须完整进入原 formal oracle；只允许指定 `test_cap1_quota_semantic` 中真实 baseline fork成功触发唯一 `M0A1_QUOTA_REJECTION` assertion failure，由 controller 确认为 `semantic_RED_confirmed`。ERROR/SKIP/超时/绑定未知/cleanup unknown 均拒绝。
- [ ] 保留 workflow configure/build 原日志与新 controller output；输出上界依上文，超界明确 ERROR，不截断后授通过。现有 native 捕获135秒/64KiB门、身份持久 lease/不重用/保留目录和 owned-root-only 清理信用原样保留。不得通过取消或反复重跑隐藏失败；原日志定位后最小复现。
- [ ] root 报告 W0 的精确信用：软件 GREEN、两实际 SDK/最终绑定、原七case正式RED各自列真实候选与状态。即使 W0 全过，也只能进入 W1 完整 PLAN/双审/独立 TEST→RED→不同 SOURCE；禁止派 quota SOURCE。

## W1 与 quota SOURCE 的不可跳过依赖

W1 另写完整独立计划，承担新原生 target 的有限身份租约/observer、真实双组负控、单组同 PID exec 前后正控、固定输出/超时及继承证据。W0 不提供这些实现，也不因此宣称批准 DESIGN 整体完成。

只有 W1 最终新候选 SHA 同时具备所有新增原生正负控、W0 的实际绑定证据及重新运行的原七 case 正式 RED，才可另派不同作者实施受审 quota SOURCE。不能拿旧 W0 SHA 的成功替代 W1 SHA 的运行。两独占非零 GID、目录/进程碰撞和有限持久租约、UID/GID四项前置、完整 count/read=2 集合、同一生产 predicate EPERM、同 PID exec 单组继承缺任何一项，quota SOURCE 继续禁止。该 gate 不授 M0a1 GREEN/M0a2/M0b/M1/R2/R3/ready 或90%信用。

## 双自审与交付边界

第一次自审（spec coverage）：DESIGN §3 TU/头/四消费点/三身份调用由 Task2覆盖；§4软件/SDK绑定/原七case由 Task1/3/4覆盖；独立原生正负控明确归 W1 hard 依赖且禁止提前 quota SOURCE。DESIGN §5 允许的额外失败点诊断本片不新增，避免改变 predicate 短路；既有观察和unknown门不动。

第二次自审（资产/边界）：wrapper保持真实返回值/errno；真实新 TU 编译与共享 predicate非复制生产条件；旧 predicate 从实际文件提取，目录reader替身只模拟已知错误边界，不伪称原errno；宏编译失败标负控；driver仍Darwin环境；两ABI和formal文件冻结；controller独立SDK/nm拒绝不改classification；实施命令仅列计划未执行。作者仅在 RAM 对五段 Python 资产作 AST 解析（缩进片段恢复所属语法容器），未 import/execute TEST/SOURCE；未生成pycache/临时源码或二进制。静态自审不授软件/原生通过信用。

【架构级自检报告】

- 语法/编译：完整 Markdown/C/Python 资产已静态阅读；本轮未编译或执行，软件/SDK通过待后续真实证据。
- 依赖/调用链：私有头/TU、共同 CMake target、四组查询和三 credentials 调用成对列齐；绑定在 native 前，W1 hard依赖独立。
- 逻辑/边界：四 UID/GID顺序、count1/read1、gid==uid、短路、EPERM保持；错误类型/数量/值、身份 mismatch、errno和正常真实读取均有完整 TEST。
- 异常处理：宏污染拒绝；编译失败不能授RED；实际SDK未知/扩展符号/命令失败/超时/输出超界拒绝；原生ERROR绝不算quotaRED。
- 关联模块：原formal、wire、phase/exit/release、lease、quota构建门不改；新增source_hashes及独立原始绑定资产与controller接线明确。
- 兼容安全：不创建账号/daemon/私有alias/rawsyscall，不加大predicate容量；W0不新增root native接口，不修改系统或用户既有变化。
- 可运行性：计划资产和执行/预期完整；本轮仅PLAN，不虚报100%运行通过；需root全文与fresh不同双审后才TEST，W1全部门仍未交付。

---
**Execution Mode:** serial

本作者停止于 PLAN；不自动实施、不提交、不推送。完整文档 hash/行数由 root 交接记录承载，避免自哈希循环。
