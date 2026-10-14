# Mac vector FD8 reservation 与最小后代 ACK 传承 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 sandbox 内仅为 FD8 占位而新开 /dev/null 的拒绝，并精确保留 vector5/slot2 后代所需的既有 ACK24。

## 2026-10-15 正式实施进度（优先于下方起草状态）

输入账本620行／37785881经独立DOCSSPEC与不同QUALITY均零后，root仅落批准A：TEST568行／26927字节／f6e8cd6b。65012c正式12方法为3红父／16Assertion、其余9绿、零ERRORskip；完整补取日志SHA77cff6d20813b8b4786e965fe321c0ef343ae5cdac33700c68a690cc62539b2f。actual TEST独立SPEC与不同QUALITY均零，逐字正逆A及原方法/错误覆盖保持。

不同SOURCE作者先独立复RED／.353s，再仅落B/C：vectors741行／37292字节／b1d4b3f9，controller331行／17878字节／0ba85855。strict12／.599s、groups13／6.038s、snapshot12／.135s均零ERRORskip；vectors默认9P6skip，opt-in9P1既有cap2 APIAssertion／5native skip／零ERROR，明确保留。actualSOURCE独立SPEC与不同QUALITY均零，前者另37项／6.120s全绿，后者12／.587s全绿；root16ef76亲读实际diff、2f53f3独立12／.674s全绿。原profile／cap1／marker／清理及其它输入保持，controller只绑定来源。

本片仍未同SHA双Darwin原生验收，cap2既有检查未通过；Linux提取探针不授Seatbelt/NPROC/ledger/cleanup或R2/R3信用。当前基准main026932cfde58c2916501ac6cbb6d49ee00a85b01为已推WFP候选，线上未全终态；本Mac候选尚未提交，最终三源码、本文及两份进度文档须全片双审后才发布，且须等待上一批run/job全部终态。下方“仅PLAN／尚未授权”为起草时历史，不代表本段实施尚未发生。

发布前补充：原六路径global SPEC与不同QUALITY已零；随后026全部57job终态为49成功／5失败／3skip，新第五失败是Python3.11 full exit139无footer，3.12 full3369／99既有skip通过。最小collector软件用例未复现，不能归因Mac FD修复或采样位置。只给CI runner补一行显式fatal-handler enable及既有诊断TEST九行，先取得5方法中3条Assertion RED再5全绿；这仅补观测，不修复已知根因、不增超时或跳过。新增两路径后发布候选为八路径，三Mac代码／A/B/C不变；仍须最终八路径双审与新SHA双Darwin，Task3继续未完成。

**Architecture:** launch_child 使用 checked dup2(2,8)，保留原 CLOEXEC、marker pipe、fork/spawn 与 ACK 协议。一个私有 predicate 在 fork pre-exec、L/S post-exec 两处关闭循环中，仅保留当前 slot ACK 与 vector5/slot2 预定 slot4 的 ACK；不新增 ACK、权限或清理信用。

**Tech Stack:** C11/POSIX descriptor、Python unittest、Linux 提取式软件探针、双 Mac CI 原生验收。

---

## 1. 授权、三问与边界

本轮仅新增此 ignored PLAN，不实施资产。权威路径 /home/orbbec/projects/icode（Ubuntu-22.04），main-only；不建 worktree/branch/DESIGN，不 stage/commit/push/reset/rebase。root 后续独立发布，技能的自动执行/提交默认被本次指令覆盖。
主代理报告实际 sequential-thinking 三步 9b0ee2 accepted/exit0，本作者不冒称亲调。独立只读研究已于前轮完成，本轮复用固定 Apple 源码，不以研究替代验收。

三问：真实问题是两架构同 case0/open EPERM；已有 launch_failure 与 marker/ACK 协议可复用；实际调用方 payload、leaf、main L/S 与 root_child 已追踪。附带发现 vector5/slot2 在两次关闭循环丢失 ACK24，经 root 明确授权纳入本片最小生命周期修复。

禁止改变 profile、/dev/null 其它预 sandbox 用途、limit cap1、NPROC、case表、原接受门、data reader、成功输出、cleanup 范围、M0A2_SOURCE=0 或 CI。不得本机执行 Darwin/native binary、root/账号/实际 kill/系统配置或全量。
本机仅 j1 编译下面 extracted C 软件程序；真实 fork/exec/spawn 均为自建有界小软件子进程，不运行工程 native target。Linux 通过不授 Seatbelt/NPROC/Darwin 清理信用。

## 2. 失败基线与 claim ledger

| 项目 | 已有证据与来源 | 上限 |
|---|---|---|
| identity/repo | root/observer 原件 candidate 5bde45676dbedc7942c52993cd0bfffbe028e57c；作者当前只读 HEAD 相同 | 不代表新修复 |
| time/platform | run38620537823/attempt1；Intel B116047032764；mac15.7.9/build24G830/kernel24.6.0；ARM B116047032453 同 open/1 | 本轮没有新 runtime |
| artifact | root RAM核 Intel11922016931，37061B/26entries，ZIP SHA0d2e7952cdd093052031b13833a3a914319b316f313518b9bacf6665411fdc57；ARM11920859681 由独立observer核 | 作者未独立下载此 ZIP |
| raw completeness | red native stderr293B；native2、complete true、result ERROR；无 formal/audit/manifest | 完整失败记录≠完整验收 |
| first rejection | M0A2_LAUNCH case0/slot0/child_slot2/stage=open/saved_errno1/exit85 | /dev/null open EPERM，非 quota EAGAIN |
| following symptom | M0A2_DATA event_count2/read_result32/received0/last_kind1/last_slot0 | read==0 映射 EPIPE；不是已证明另一次内核 write 失败 |
| policy mechanism | deny default profile 无 /dev/null permit；sandbox 后 open O_RDWR | 与拒绝相符，不冒称闭源 Seatbelt 内部审计根因 |
| static ACK gap | root 预置20..27；fork与L/S循环只留 own ACK；leaf vector5/slot2随后 launch4 | 新静态发现，不冒称已线上走到该分支 |

采用：现有 stderr FD2 占位、精确合法 ACK 传承。暂缓：Darwin dup2 策略、真实 quota/后续 vectors 结果，待同 SHA 双平台。拒绝：放宽 sandbox、保留全部 ACK、绕过失败、重跑取消刷绿。

2026-10-15 复用 Apple 官方固定 tag xnu-12377.1.9：
[kern_descrip.c](https://raw.githubusercontent.com/apple-oss-distributions/xnu/xnu-12377.1.9/bsd/kern/kern_descrip.c) 的 dup2/finishdup 复用既有 fileglob、调用 mac_file_check_dup；因此不是路径 open，但也不能保证实际 runner 允许。
[kern_exec.c](https://raw.githubusercontent.com/apple-oss-distributions/xnu/xnu-12377.1.9/bsd/kern/kern_exec.c) 的 PSFA_DUP2 用既有描述符完成 spawn actions。
所读文件头 APSL2.0；只采纳机制、不复制实现；固定版本不是实际 kernel24.6.0 binary/最新 HEAD 的证明。

## 3. FD 生命周期与最小成本

| 位置 | 原行为 | 本片 |
|---|---|---|
| root_child | 保留2/5/20..27，FD0/1预 sandbox /dev/null；8被关闭 | 不改 |
| launch reservation | sandbox 内 open/dup/close，仅占8 | checked dup2(2,8)，无占位IO；原 fcntl8 |
| marker pipe | 8已占用，避免 writer 与8别名 | 不改；真实最低可用FD软件验证 |
| fork child | marker C→ACK child→关marker→关其它FD→exec L | 仅 vector5/child_slot2 多留20+4 |
| spawn child | action dup marker writer→8，S先写C→ACK→close8 | 不改；同一 L/S关闭 predicate |
| leaf | 唯一 vector5/slot2 launch4 | 不改；ACK24由root既有端传承，descendant不补管 |
| 终叶slot4 | 保留2/5/自己的ACK24，到原退出关闭 | 不多留slot2 ACK，不改wait/reap/cleanup |

FD0/1在后代关闭，不能用dup0/1。FD5/ACK是控制通道，不用作占位。FD2始终保留，dup2仅新增它的别名；占位FD8在fork显式关闭、spawn被marker替换且S关闭，不产生跨生命周期额外stderr引用。
两个关闭点必须一起改；只改一个，真实 nested 探针仍失败。predicate 重用既有20+slot协议，额外目的地写20+4并注释与leaf固定关系，不用孤立24魔法数，不保留其它未授权ACK。
相对只修open，成本是一个5行predicate、两处条件、测试提取闭包同步；仍仅vectors/TEST，controller仅增加本PLAN source binding一行。相比profile allow方案，无权限扩大、无共享helper/profile/hash逆向资产变更。

## 4. 冻结输入与预期输出

实际读取时 HEAD=5bde；root handoff、Windows WFP实际TEST属于其它作者，完全保留。任一授权输入不符先停，不拿本PLAN覆盖他人改动。

| 路径 | 输入 SHA256 |
|---|---|
| native/mac/tests/icode_m0a2_vectors.c | 2546c73e5e17511d9431401461df924a77a56aa59ae00f9e0affce6e6da99e1c |
| tests/test_macos_m0a2_event_diagnostics.py | 8cfbe010826115648e3b46a9e4284419ab70fe12ddcf9802644814b8a299c5ac |
| scripts/run_macos_m0a2_vectors.py | ff21e16cc166fb9298c78b1be28f7be0c428ad40ec9ae1272fbfaec0094de69b |
| native/mac/tests/icode_m0a1_fixed_helpers.inc | de74f6b77a9d91fd3d9fdf2801adfe4dc8685ff685480a7b09bb0e9c58f10546 |
| .github/workflows/ci.yml | 289b21930ff23ec4c15dd07303580f6d78a6e299bc2caec8758e310c9ac7f5d7 |
| native/mac/icode_m0a1_limit.c | 507b26a2d2ff1cca663c4c52f8ead50b1a4991563f1942e0f7d2a8f39dcc208c |

输出hash以§8实际匿名机器记录为准。Asset A为TEST，B为SOURCE，C为仅绑定PLAN的controller；三个patch全字节与逆向必须核。不要把C的一行绑定说成controller行为修复。

原controller sources元组26项全部逐字节读取并核SHA：按原顺序生成(name,sha256)数组，以json.dumps(rows,separators=(",",":"))的UTF-8字节取SHA，当前冻结总摘要为060d350b5f51003e8152fd9c47de093fcd03f2a289354efcb04fe89bb0d8ba34。§7脚本强制该摘要、三个输入单hash及额外limit.c hash；涵盖旧PLAN、其它TEST、helper、controller、CMake、CI、quota设计，不需扩大修改面。
本PLAN不改CI；若其它已授权候选先改变HEAD/CI，root必须解释漂移并重新核Mac输入/组合CI，不允许作者覆盖或伪称仍5bde。

执行输入漂移记录（2026-10-15）：本PLAN原612L/36852B批准版SHA2a65f403c0914fe3e015476eaf58e6a8b6c4546842ecbbf0283478509dd445ec对应CI2511L/c331b43681964eae1d62543b15fe1c43d4f4c6bbab346a33c5184c2d573cb5ca、原26摘要9cf0cbd7d1e1f366291d13cf9050381dd22fc1779cb47495aa6b87918150f715。批准WFP SOURCE实际双审后，root仅对共享CI落已审WFP D，CI变为2539L/c3e4276128567359d472c80af482a723d5fe131eed2bb7352e4485c8782140e8；root bbc906回报新26摘要，作者336417独立重算一致，其余原26输入字节不变。此次仅同步输入表/摘要断言，不改变A/B/C资产及投影，也不实施Mac文件；root回报同步时HEAD仍5bde，未来候选提交SHA尚未知，不预写。

第二次执行输入漂移记录（2026-10-15）：旧618L/38169B批准版SHAf82cb8d72901e170a1a76712af3a5490e7dcc82e4a28ace571d2e7eac7faf20a对应CI2539L/c3e4276128567359d472c80af482a723d5fe131eed2bb7352e4485c8782140e8、26摘要1e0e00937fec19c66fc6abac43ca972aa84339ea94719d6c7b98c2fb04abfdf6。WFP不同QUALITY发现类别赋值未先拒绝非listed状态；正式TEST单条Assertion RED后，不同SOURCE仅在既有赋值条件补精确status -ceq listed，当前CI仍2539L/SHA289b21930ff23ec4c15dd07303580f6d78a6e299bc2caec8758e310c9ac7f5d7。此次从原controller AST提取sources顺序，26项逐rawhash重算为060d350b5f51003e8152fd9c47de093fcd03f2a289354efcb04fe89bb0d8ba34；仅将CI项替回旧值即可恢复1e0e0093摘要，其余25项未变。只同步本PLAN输入表、总摘要及脚本断言并记录历史；A/B/C资产及投影不变，不重跑C程序、不实施Mac文件，正式TEST仍未授权。main仍5bde，未来WFP候选SHA未知，不预写；本次修订待root独立DOCSSPEC与不同QUALITY。

## 5. 执行次序（仅未来正式执行）

### Task 1: 不同 TEST 作者落实 Asset A

**Dependencies:** None
**Parallelizable:** No（先冻结RED，再SOURCE）

- [x] 核输入表、当前HEAD/dirty保护；完整读此PLAN，apply_patch仅落A，不落B/C。
- [x] 使用下面严格12命令记录真实RED：必须为语义 Assertion、0ERROR/skip；缺compiler、missing helper、编译失败属于基础设施，不算RED，先停报root。
- [x] TEST作者自SPEC→自QUALITY，独立实际SPEC→不同QUALITY全0后冻结TEST。
- [x] 原12方法仍12：迁移被删除open/临时close分支为checked dup2的EACCES/EMFILE/EBADF；原fcntl/pipe/读写/信号/计数/header/宏重定义断言保留。旧“reserved8”场景改为已有目标仍必须dup覆盖。
- [x] 原临时close EIO分支已不存在，迁移为dup2 EIO即时errno断言（stage8），没有删掉EIO错误保存覆盖；不伪造仍会close临时FD6。
- [x] 五个真实FD子场景放入既有launch方法：fork+exec、spawn+exec、重复、已占8、nested0/1closed。不是新增五个native case，也不是stub全部EAGAIN的假正控。

严格命令（WSL根）：
```bash
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_m0a2_event_diagnostics.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
```

### Task 2: 不同 SOURCE 作者落实 B/C

**Dependencies:** Task 1
**Parallelizable:** No（TEST冻结与实际双审后）

- [x] fresh核A冻结、其余输入、CI仍原；apply_patch仅B/C，不改TEST/PLAN/CI。
- [x] 同命令12PASS/0F/E/skip；针对groups13、snapshot12做软件回归；vectors默认原15=9P6skip、ICODE_M0A2_LIMIT_SOFTWARE=1原cap2 APIAssertion预期9P1F5native skip/0ERROR，不据此改cap。
- [x] 全文diff、三输出hash、语法AST、三个patch唯一逆回输入；未改helper/limit/CI与所有其它输入hash。
- [x] SOURCE自SPEC→不同角度自QUALITY及七维；fresh实际SPEC→不同QUALITY全0后停交root。不得自行stage/commit/push。

```bash
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_process_groups*.py'); assert s.countTestCases()==13; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_identity_snapshot_diagnostics.py'); assert s.countTestCases()==12; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
ICODE_M0A2_LIMIT_SOFTWARE=1 /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
```

### Task 3: root 同 SHA 双 Mac 线上验收

**Dependencies:** Task 2
**Parallelizable:** No（候选与所有必要审查绑定）

- [ ] root独立发布仅此已审候选；本PLAN source binding要求root跟踪此ignored文件，不由作者执行Git操作。
- [ ] Intel/ARM既有工作流同候选SHA，strict12原计数；CI/env/job/权限完全不变，M0A2_SOURCE仍0。
- [ ] 记录原log/artifact ZIP digest、sourcehashes、binary binding、native/stdout/stderr及formal状态；旧EPERM消失不是完整vectors验收。
- [ ] 原cap1源码与cap2接受门仍独立：后续quota/ACK/权限等新失败必须保留并另诊断，不取消/重跑覆盖，不声称R2/R3通过。无原ledger/end不得cleanup信用。
- [ ] 本片阶段结果以必要两平台实际原始证据为准；Linux extracted软件GREEN仅授机制信用。

## 6. 完整资产

### Asset A — TEST-only patch
```diff
--- a/tests/test_macos_m0a2_event_diagnostics.py
+++ b/tests/test_macos_m0a2_event_diagnostics.py
@@ -1,4 +1,4 @@
+"""M0a2 software contracts; extracted C probes only, no Darwin/root workload."""
-"""M0a2 diagnostic-only software contract; no Darwin/root/fork execution."""
 import errno
 import os
 from pathlib import Path
@@ -45,6 +45,12 @@
         actual+=function(source,"read_data_record")+function(source,"reject_data_event")+function(source,"next_data_event")
     if "static _Noreturn void launch_failure(" in source:
         actual+=function(source,"launch_failure")
+    if "static int leaf_ack_fd(" in source:
+        definitions=re.search(r"^struct definition .*?(?=^struct event )",source,re.M|re.S)
+        if definitions is None:
+            raise AssertionError("actual case definitions unavailable")
+        actual+='static const char *m0_variant(void) {return "source";}\n'
+        actual+=definitions[0]+function(source,"definition_at")+function(source,"leaf_ack_fd")
     actual+=function(source,"require_ack")+function(source,"launch_child")
     return PRELUDE+actual+TRAILER.replace("ACTUAL_GUARD",guard[1]).replace("ACTUAL_ACCEPTED_UPDATE",guard[2] or "")
 
@@ -84,22 +90,22 @@
 static int model_open(const char *path,int flags) {
  opens++;
  if(strcmp(path,"/dev/null") || flags!=(O_RDWR|O_CLOEXEC)) _exit(202);
+ errno=EPERM;return -1; /* New path opens are forbidden by this fixture. */
- if(fail_stage==1) {errno=EACCES;return -1;}
- if(reserved_eight) fd8_ready=1;
- return reserved_eight ? 8 : 6;
 }
 static int model_dup2(int oldfd,int newfd) {
  dups++;
+ if(oldfd!=2 || newfd!=8) _exit(203);
+ if(fail_stage==1) {errno=EACCES;return -1;}
- if(oldfd!=6 || newfd!=8) _exit(203);
  if(fail_stage==2) {errno=EMFILE;return -1;}
+ if(fail_stage==3) {errno=EBADF;return -1;}
+ if(fail_stage==8) {errno=EIO;return -1;}
  fd8_ready=1;return 8;
 }
 static int model_close(int fd) {
  closes++;
- if(fd==6 && fail_stage==3) {errno=EIO;return -1;}
  if(fd==10) marker_read_closed=1;
  if(fd==11) marker_write_closed=1;
+ if(fd!=10 && fd!=11) _exit(204);
- if(fd!=6 && fd!=10 && fd!=11) _exit(204);
  return 0;
 }
 static int model_fcntl(int fd,int command,int flags) {
@@ -231,8 +237,9 @@
  if(!strncmp(scenario,"launch",6)) {
   launch_mode=1;fail_stage=atoi(argv[2]);spawning_mode=!strcmp(scenario,"launch_spawn");
   reserved_eight=!strcmp(scenario,"launch_reserved8");
+  fd8_ready=reserved_eight; /* dup2 must replace an already occupied target too. */
   pid_t result=launch_child(7,0,2,spawning_mode);
+  if(result!=-1 || opens!=0 || dups!=1 || fcntls!=3 || pipes!=1 ||
-  if(result!=-1 || opens!=1 || dups!=(reserved_eight ? 0 : 1) || fcntls!=3 || pipes!=1 ||
      forks!=(spawning_mode ? 0 : 1) || spawns!=(spawning_mode ? 1 : 0) || acks!=1) return 218;
   printf("launch_ok fd8=1 marker_closed=2 ack=1 fork=%d spawn=%d\n",forks,spawns);
   return 0;
@@ -268,6 +275,27 @@
                              capture_output=True,timeout=30)
         if built.returncode or built.stdout or len(built.stderr)>65536:
             raise AssertionError("C diagnostic probe infrastructure: "+built.stderr.decode("utf-8","replace"))
+        cls.build_descriptor_probe()
+    @classmethod
+    def build_descriptor_probe(cls):
+        cc=shutil.which("cc")
+        if cc is None:
+            raise AssertionError("C compiler unavailable; infrastructure, not semantic RED")
+        cls.fdtemporary=tempfile.TemporaryDirectory(prefix="m0a2-fd8-software-")
+        cls.addClassCleanup(cls.fdtemporary.cleanup)
+        cls.fd_binary=Path(cls.fdtemporary.name)/"fd-probe"
+        program=descriptor_probe_source(CFILE.read_text(encoding="utf-8"))
+        built=subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror","-Wno-unused-function",
+                              "-x","c","-","-o",str(cls.fd_binary)],input=program.encode("ascii"),
+                             capture_output=True,timeout=30)
+        if built.returncode or built.stdout or built.stderr:
+            raise AssertionError("C FD probe infrastructure: "+built.stderr.decode("utf-8","replace"))
+    def descriptor_case(self,mode,launches=1):
+        result=subprocess.run([str(self.fd_binary),str(mode)],capture_output=True,timeout=10)
+        self.assertLessEqual(len(result.stdout)+len(result.stderr),4096)
+        self.assertEqual(result.returncode,0,result.stderr)
+        self.assertEqual(result.stderr,b"")
+        self.assertEqual(result.stdout,f"fd8_ok mode={mode} launches={launches}\n".encode())
     def run_probe(self,scenario,stage=0):
         result=subprocess.run([str(self.binary),scenario,str(stage)],capture_output=True,timeout=5)
         self.assertLessEqual(len(result.stdout)+len(result.stderr),4096)
@@ -280,16 +308,16 @@
               f"received={received} last_kind={last[0]} last_slot={last[1]} cleanup=unknown\n").encode()
         self.assertIn(line,actual.stderr,"M0A2_DIAGNOSTIC_DATA_REQUIRED")
         self.assertIn(b"M0A2 stage=data-event-contract",actual.stderr)
+    def test_launch_reservation_refusal_has_saved_errno_without_creation(self):
-    def test_launch_open_refusal_has_saved_errno_without_creation(self):
         actual=self.run_probe("launch",1)
         self.assertEqual(actual.returncode,85)
         self.assertEqual(actual.stdout,b"")
         self.assertEqual(actual.stderr,
+            f"M0A2_LAUNCH case=7 slot=0 child_slot=2 stage=dup2 saved_errno={errno.EACCES} exit=85 cleanup=unknown\n".encode(),
-            f"M0A2_LAUNCH case=7 slot=0 child_slot=2 stage=open saved_errno={errno.EACCES} exit=85 cleanup=unknown\n".encode(),
             "M0A2_DIAGNOSTIC_LAUNCH_REQUIRED")
     def test_launch_other_setup_failures_are_exact_stages(self):
+        for stage,name,error in ((2,"dup2",errno.EMFILE),(3,"dup2",errno.EBADF),(4,"fcntl8",errno.EBADF),
+                                 (5,"pipe",errno.ENFILE),(6,"fcntl_read",errno.EBADF),(7,"fcntl_write",errno.EBADF),(8,"dup2",errno.EIO)):
-        for stage,name,error in ((2,"dup2",errno.EMFILE),(3,"close",errno.EIO),(4,"fcntl8",errno.EBADF),
-                                 (5,"pipe",errno.ENFILE),(6,"fcntl_read",errno.EBADF),(7,"fcntl_write",errno.EBADF)):
             with self.subTest(stage=stage):
                 actual=self.run_probe("launch",stage)
                 self.assertEqual(actual.returncode,85)
@@ -319,6 +347,9 @@
                 self.assertEqual(actual.stderr,b"")
                 self.assertEqual(actual.stdout,
                     f"launch_ok fd8=1 marker_closed=2 ack=1 fork={forks} spawn={spawns}\n".encode())
+        for mode,launches in ((0,1),(1,1),(2,2),(3,1),(4,1)):
+            with self.subTest(real_descriptor_mode=mode):
+                self.descriptor_case(mode,launches)
     def test_eof_reports_read_result_not_stale_errno(self):
         self.data_rejection("eof","read",errno.EPIPE,0)
     def test_partial_read_reports_actual_byte_count(self):
@@ -376,5 +407,162 @@
     def test_second_failure_retains_last_accepted_header(self):
         self.data_rejection("after","read",errno.EPIPE,0,last=(1,0),count=2)
 
+
+# This is a Linux/POSIX descriptor mechanism probe, not the Darwin vectors binary.
+# Source launch_child and the L/S entry branch are extracted unchanged at build time.
+FD_PRELUDE=r'''
+#define _POSIX_C_SOURCE 200809L
+#include <errno.h>
+#include <fcntl.h>
+#include <signal.h>
+#include <spawn.h>
+#include <stdint.h>
+#include <stdio.h>
+#include <stdlib.h>
+#include <string.h>
+#include <sys/stat.h>
+#include <sys/types.h>
+#include <sys/wait.h>
+#include <unistd.h>
+static char *image,binary_hash[65];
+enum { FORKED=3,OP=2,SPAWN_OP=2,FORK_OP=1 };
+static int reservations,marker_pipes,events;
+static int all_read(int fd,void *buffer,size_t amount) {
+ unsigned char *p=buffer;
+ while(amount) {
+  ssize_t n=read(fd,p,amount);
+  if(n<0 && errno==EINTR) continue;
+  if(n<=0) return 1;
+  p+=n;amount-=(size_t)n;
+ }
+ return 0;
+}
+static int forbidden_open(const char *path,int flags) {
+ (void)path;(void)flags;errno=EPERM;return -1;
+}
+static int reserve_dup(int from,int to) {
+ if(from!=2 || to!=8) _exit(201);
+ int result=dup2(from,to);
+ if(result==8) reservations++;
+ return result;
+}
+static int marker_pipe(int pair[2]) {
+ struct stat a,b;
+ if(fstat(2,&a)<0 || fstat(8,&b)<0 || a.st_dev!=b.st_dev || a.st_ino!=b.st_ino ||
+    fcntl(8,F_GETFD)!=FD_CLOEXEC) _exit(202);
+ int expected[2],found=0;
+ for(int fd=0;fd<64 && found<2;fd++)
+  if(fcntl(fd,F_GETFD)<0 && errno==EBADF) expected[found++]=fd;
+ if(found!=2 || pipe(pair)<0) _exit(203);
+ if(pair[0]!=expected[0] || pair[1]!=expected[1] || pair[0]==8 || pair[1]==8) _exit(204);
+ marker_pipes++;return 0;
+}
+static char send_event(unsigned kind,unsigned slot,unsigned other,unsigned op,
+                       int64_t rc,int error,int aux) {
+ if(kind!=FORKED || (slot!=0 && slot!=2) || (other!=2 && other!=4) ||
+    (op!=FORK_OP && op!=SPAWN_OP) || rc<=0 || error || aux!=1) _exit(205);
+ events++;return 'A'; /* Isolated observer: actual marker and ACK pipes are real. */
+}
+static _Noreturn void die(const char *stage) {(void)stage;_exit(227);}
+static int numeric(const char *value,int low,int high) {
+ char *end=NULL;long n=strtol(value,&end,10);
+ if(!end || *end || n<low || n>high) _exit(206);
+ return (int)n;
+}
+static const char *m0_variant(void) {return "source";}
+static int hex_string(const char *value,size_t n) {
+ return strlen(value)==n && strspn(value,"0123456789abcdef")==n;
+}
+static void finished(unsigned slot,pid_t *children,unsigned *slots,unsigned count);
+static void leaf(int index,unsigned slot,unsigned parent);
+#define open(path,flags) forbidden_open(path,flags)
+#define dup2(from,to) reserve_dup(from,to)
+#define pipe(pair) marker_pipe(pair)
+'''
+FD_TRAILER=r'''
+#undef open
+#undef dup2
+#undef pipe
+static void wait_success(pid_t pid) {
+ int status=0;pid_t got;
+ do {got=waitpid(pid,&status,0);} while(got<0 && errno==EINTR);
+ if(got!=pid || !WIFEXITED(status) || WEXITSTATUS(status)) _exit(207);
+}
+static void prepare_ack(int fd,int copies) {
+ int p[2];if(pipe(p)<0) _exit(208);
+ if(dup2(p[0],fd)!=fd) _exit(209);
+ if(close(p[0])<0) _exit(210);
+ for(int i=0;i<copies;i++) if(write(p[1],"C",1)!=1) _exit(211);
+ if(close(p[1])<0) _exit(212);
+}
+static void finished(unsigned slot,pid_t *children,unsigned *slots,unsigned count) {
+ if(slot!=2 || count!=1 || slots[0]!=4) _exit(217);
+ wait_success(children[0]);
+ if(write(5,"L",1)!=1) _exit(218);
+ _exit(0);
+}
+static void leaf(int index,unsigned slot,unsigned parent) {
+ if(parent!=(slot==2 ? 0u : 2u)) _exit(213);
+ for(int fd=0;fd<=8;fd++) {
+  int flags=fcntl(fd,F_GETFD);
+  if(fd==2 || fd==5) {if(flags<0) _exit(214);}
+  else if(flags>=0 || errno!=EBADF) _exit(215);
+ }
+ for(int fd=20;fd<28;fd++) {
+  int keep=fd==20+(int)slot || (fd==24 && slot==2 && definition_at(index).vector==5);
+  int flags=fcntl(fd,F_GETFD);
+  if(keep ? flags<0 : flags>=0 || errno!=EBADF) _exit(216);
+ }
+ struct definition c=definition_at(index);char answer='A';
+ACTUAL_NESTED_BRANCH
+ if(write(5,slot==4 ? "N" : "L",1)!=1) _exit(218);
+ _exit(0);
+}
+int main(int argc,char **argv) {
+ image=argv[0];memset(binary_hash,'a',64);binary_hash[64]=0;
+ACTUAL_S_FIRST
+ACTUAL_LS_BRANCH
+ if(argc!=2) return 219;
+ alarm(8);
+ for(int fd=3;fd<64;fd++) if(close(fd)<0 && errno!=EBADF) return 228;
+ int mode=numeric(argv[1],0,4),data[2];
+ if(pipe(data)<0 || dup2(data[1],5)!=5 || close(data[1])<0) return 220;
+ for(int fd=20;fd<28;fd++) prepare_ack(fd,mode==2 ? 2 : 1);
+ if(dup2(2,6)!=6 || dup2(2,7)!=7) return 221;
+ if(mode==3) {if(dup2(5,8)!=8) return 222;}
+ else if(close(8)<0 && errno!=EBADF) return 223;
+ int times=mode==2 ? 2 : 1;
+ for(int i=0;i<times;i++) {
+  int index=mode==4 ? 9 : mode==1 ? 2 : 0;
+  pid_t child=launch_child(index,0,2,mode==1);
+  wait_success(child);
+ }
+ if(reservations!=times || marker_pipes!=times || events!=times) return 224;
+ char bytes[3]={0};int wanted=mode==4 ? 2 : times;
+ if(all_read(data[0],bytes,(size_t)wanted) || memcmp(bytes,mode==4 ? "NL" : "LL",(size_t)wanted)) return 225;
+ if(close(5)<0 || close(data[0])<0) return 226;
+ printf("fd8_ok mode=%d launches=%d\n",mode,times);return 0;
+}
+'''
+
+def descriptor_probe_source(source):
+    main=source.index("int main(int argc,char **argv) {")
+    tail=source[main:]
+    first=re.search(r' if\(argc==6 && !strcmp\(argv\[1\],"S"\)\) \{.*?\n \}',tail,re.S)
+    branch=re.search(r' if\(argc==6 && \(!strcmp\(argv\[1\],"L"\).*?\n \}',tail,re.S)
+    if first is None or branch is None:
+        raise AssertionError("actual S-first/L-S branch unavailable")
+    definitions=re.search(r"^struct definition .*?(?=^struct event )",source,re.M|re.S)
+    nested=re.search(r" if\(c\.vector==5 && slot==2\) \{.*?\n \}",function(source,"leaf"),re.S)
+    if definitions is None or nested is None:
+        raise AssertionError("actual case definitions/nested launch unavailable")
+    actual=definitions[0]+function(source,"definition_at")
+    if "static int leaf_ack_fd(" in source:
+        actual+=function(source,"leaf_ack_fd")
+    actual+="".join(function(source,name) for name in
+                    ("require_ack","block_diagnostic_sigpipe","launch_failure","launch_child"))
+    return FD_PRELUDE+actual+FD_TRAILER.replace("ACTUAL_S_FIRST",first[0]).replace(
+        "ACTUAL_LS_BRANCH",branch[0]).replace("ACTUAL_NESTED_BRANCH",nested[0])
+
 if __name__=="__main__":
     unittest.main()
```

### Asset B — SOURCE patch
```diff
--- a/native/mac/tests/icode_m0a2_vectors.c
+++ b/native/mac/tests/icode_m0a2_vectors.c
@@ -163,12 +163,15 @@
  if(n>0 && n<(int)sizeof(line)) (void)write(2,line,(size_t)n);
  _exit(85);
 }
+static int leaf_ack_fd(int fd,int index,unsigned slot) {
+ /* leaf(vector 5,slot 2) alone launches the fixed descendant slot 4. */
+ return fd==20+(int)slot ||
+        (slot==2 && fd==20+4 && definition_at(index).vector==5);
+}
 static pid_t launch_child(int index,unsigned slot,unsigned child_slot,int spawning) {
  int marker[2];
+ /* Occupy 8 before pipe allocation without opening a new sandbox path. */
+ if(dup2(2,8)<0) launch_failure(index,slot,child_slot,"dup2",errno);
- int reserved=open("/dev/null",O_RDWR|O_CLOEXEC);
- if(reserved<0) launch_failure(index,slot,child_slot,"open",errno);
- if(reserved!=8 && dup2(reserved,8)<0) launch_failure(index,slot,child_slot,"dup2",errno);
- if(reserved!=8 && close(reserved)<0) launch_failure(index,slot,child_slot,"close",errno);
  if(fcntl(8,F_SETFD,FD_CLOEXEC)<0) launch_failure(index,slot,child_slot,"fcntl8",errno);
  if(pipe(marker)<0) launch_failure(index,slot,child_slot,"pipe",errno);
  if(fcntl(marker[0],F_SETFD,FD_CLOEXEC)<0) launch_failure(index,slot,child_slot,"fcntl_read",errno);
@@ -197,7 +200,8 @@
    if(all_read(20+(int)child_slot,&go,1) || go!='C') _exit(90);
    if(close(marker[0])<0 || close(marker[1])<0) _exit(91);
    for(int fd=0;fd<65536;fd++)
+    if(fd!=2 && fd!=5 && !leaf_ack_fd(fd,index,child_slot) &&
+       close(fd)<0 && errno!=EBADF) _exit(92);
-    if(fd!=2 && fd!=5 && fd!=20+(int)child_slot && close(fd)<0 && errno!=EBADF) _exit(92);
    execve(image,args,env);_exit(93);
   }
  }
@@ -685,7 +689,8 @@
    if(all_read(20+(int)slot,&go,1) || go!='C' || close(8)<0) _exit(139);
   }
   for(int fd=0;fd<65536;fd++)
+   if(fd!=2 && fd!=5 && !leaf_ack_fd(fd,index,slot) &&
+      close(fd)<0 && errno!=EBADF) _exit(140);
-   if(fd!=2 && fd!=5 && fd!=20+(int)slot && close(fd)<0 && errno!=EBADF) _exit(140);
   leaf(index,slot,parent);return 2;
  }
  if(argc!=4 || getuid()!=0 || geteuid()!=0 || !hex_string(argv[1],40) || !hex_string(argv[2],64)) die("root-fixed-arguments");
```

### Asset C — controller source binding only
```diff
--- a/scripts/run_macos_m0a2_vectors.py
+++ b/scripts/run_macos_m0a2_vectors.py
@@ -277,6 +277,7 @@
             "tests/test_macos_process_groups.py","tests/test_macos_m0a2_vectors.py",
             "tests/test_macos_m0a2_event_diagnostics.py",
             "tests/test_macos_identity_snapshot_diagnostics.py",
+            "docs/nbl/plans/2026-10-15-macos-vector-fd8-reservation.md",
             "docs/nbl/plans/2026-10-15-macos-identity-snapshot-diagnostics.md",
             "docs/nbl/plans/2026-10-14-macos-m0a2-event-diagnostics.md",
             "scripts/run_macos_m0_ci.py","scripts/run_macos_m0a2_vectors.py",
```

## 7. 匿名可执行预演与预算

下面脚本只读取本PLAN及冻结三个输入，在RAM正逆投影并exec测试模块；仅编译临时extracted软件，不写actual TEST/SOURCE/CI。正式TEST仍须不同作者真实落盘RED，不能用本预演代替。
运行方式：从WSL根将本节唯一python fence内容经stdin交给同一env的python -B -。不要把本节写入repo脚本。单个cc超时30s、单个小探针10s、输出上限4096；成功子进程waitpid，后代alarm10，重复最多2launch，nested最多2层。禁止外部PID/kill/账户/API native。
负控依次恢复任一旧关闭循环、扩大保留ACK；必须恰好触发真实FD断言，而非编译ERROR。保持实际新12数量，不虚构case通过数。

```python
import ast, hashlib, io, json, re, time, types, unittest
from pathlib import Path
PLAN=Path("docs/nbl/plans/2026-10-15-macos-vector-fd8-reservation.md")
text=PLAN.read_text(encoding="utf-8")
patches=re.findall(r"^```diff\n(.*?)^```$",text,re.M|re.S)
assert len(patches)==3,len(patches)
def digest(data):
    return hashlib.sha256(data.encode()).hexdigest()
def apply(data,patch,reverse=False):
    rows=patch.splitlines(keepends=True)
    old=data.splitlines(keepends=True);out=[];cursor=0
    headers=[i for i,row in enumerate(rows) if row.startswith("@@ ")]
    for pos,h in enumerate(headers):
        m=re.fullmatch(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n",rows[h])
        assert m,rows[h]
        line,count,newline,newcount=map(int,m.groups())
        if reverse:line,count,newline,newcount=newline,newcount,line,count
        target=line-1
        assert cursor<=target,(cursor,target)
        out+=old[cursor:target];cursor=target
        consumed=produced=0
        for row in rows[h+1:headers[pos+1] if pos+1<len(headers) else len(rows)]:
            kind,body=row[0],row[1:]
            if reverse and kind in "+-":kind="+" if kind=="-" else "-"
            assert kind in " +-",row
            if kind in " -":
                assert cursor<len(old) and old[cursor]==body,(cursor,row)
                cursor+=1;consumed+=1
            if kind in " +":out.append(body);produced+=1
        assert (consumed,produced)==(count,newcount)
    return "".join(out+old[cursor:])
paths=[Path("tests/test_macos_m0a2_event_diagnostics.py"),
       Path("native/mac/tests/icode_m0a2_vectors.c"),
       Path("scripts/run_macos_m0a2_vectors.py")]
old=[p.read_text(encoding="utf-8") for p in paths]
assert [digest(a) for a in old]==[
    "8cfbe010826115648e3b46a9e4284419ab70fe12ddcf9802644814b8a299c5ac",
    "2546c73e5e17511d9431401461df924a77a56aa59ae00f9e0affce6e6da99e1c",
    "ff21e16cc166fb9298c78b1be28f7be0c428ad40ec9ae1272fbfaec0094de69b"]
for n in ast.walk(ast.parse(old[2])):
    if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=="sources" for x in n.targets):
        names=ast.literal_eval(n.value)
rows=[(name,hashlib.sha256(Path(name).read_bytes()).hexdigest()) for name in names]
assert len(rows)==26
assert digest(json.dumps(rows,separators=(",",":")))=="060d350b5f51003e8152fd9c47de093fcd03f2a289354efcb04fe89bb0d8ba34"
assert hashlib.sha256(Path("native/mac/icode_m0a1_limit.c").read_bytes()).hexdigest()=="507b26a2d2ff1cca663c4c52f8ead50b1a4991563f1942e0f7d2a8f39dcc208c"
new=[apply(a,p) for a,p in zip(old,patches)]
for p,a,b,patch in zip(paths,old,new,patches):
    assert apply(b,patch,True)==a
    print("projection",p,len(b.splitlines()),len(b.encode()),digest(b),
          "patch",len(patch.splitlines()),len(patch.encode()),digest(patch))
ast.parse(new[0]);ast.parse(new[2])
class MemoryC:
    def __init__(self,value):self.value=value
    def read_text(self,**kwargs):return self.value
def run(label,source):
    module=types.ModuleType("fd8_anonymous_"+label)
    module.__file__=str(paths[0].resolve())
    exec(compile(new[0],module.__file__,"exec"),module.__dict__)
    module.CFILE=MemoryC(source)
    suite=unittest.defaultTestLoader.loadTestsFromModule(module)
    assert suite.countTestCases()==12,suite.countTestCases()
    stream=io.StringIO();start=time.monotonic()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    print(label,"methods",result.testsRun,"failures",len(result.failures),
          "errors",len(result.errors),"skips",len(result.skipped),
          "seconds",round(time.monotonic()-start,3))
    if result.errors:print(stream.getvalue())
    assert not result.errors and not result.skipped,stream.getvalue()
    if label=="green":assert result.wasSuccessful(),stream.getvalue()
    else:
        assert result.failures,stream.getvalue()
        assert all("AssertionError" in trace for _,trace in result.failures)
    return result
run("red",old[1])
run("green",new[1])
# Positive source minus each necessary closure fix: true nested path must fail.
for which,suffix in (("pre","child_slot"),("post","slot")):
    condition="!leaf_ack_fd(fd,index,"+suffix+")"
    assert new[1].count(condition)==1
    mutant=new[1].replace(condition,"fd!=20+(int)"+suffix,1)
    result=run(which,mutant)
    assert len(result.failures)==1 and "real_descriptor_mode=4" in str(result.failures[0][0])
# An overbroad ACK grant must fail in non-grandchild descendants.
mutant=new[1].replace("(slot==2 && fd==20+4 && definition_at(index).vector==5)",
                     "(fd==20+4 && definition_at(index).vector>=0)",1)
assert mutant!=new[1]
run("broad",mutant)
print("inverse AST strict12 semanticRED/GREEN and three lifecycle negatives: OK")
```

## 8. 匿名证据与自审

此节在作者定点预演后记录精确结果，不把匿名投影说成实际落盘或原生通过。

### 8.1 冻结资产/投影机器记录

2026-10-15，作者实际工具e73010，§7完整脚本stdin执行，wall3.325s/exit0；计数都是12个unittest方法，failures包含subTest条目，不把16条Assertion当16个父方法。

| 资产 | patch行/字节/SHA256 | 投影行/字节/SHA256 |
|---|---|---|
| A TEST | 283 / 13467 / 7d14c190038df957008aab75079a55f8951ad56d92622b08556da7cde3577389 | 568 / 26927 / f6e8cd6b2bab1518d43923311a39ce7e7772e2c1b7dd45dafc3d8e5630d3b70a |
| B vectors | 42 / 2155 / f5b6fee027a36272203bed26fb9295fe18014f7de86904ac84b0e384698c84e8 | 741 / 37292 / b1d4b3f97b038304dac76939db2bf25db485d21fc76ec57615fa54fa61328b0b |
| C binding | 10 / 619 / cf4f4c20fe76dadd4b2caf781e0d9f65c0c63934abc352d60c3bfb6469f9d456 | 331 / 17878 / 0ba8585518263c1cd488a52d84c6fbc31a76f81a3965a05b0d2e0198204eea7e |

| 匿名运行 | 方法 | Assertion条目 | ERROR/skip | 秒 |
|---|---:|---:|---|---:|
| A + 旧SOURCE | 12 | 16 | 0/0 | .367 |
| A + 完整B | 12 | 0 | 0/0 | .653 |
| 恢复fork pre-exec原关闭条件 | 12 | 1（nested mode4） | 0/0 | .632 |
| 恢复L/S post-exec原关闭条件 | 12 | 1（nested mode4） | 0/0 | .623 |
| 过宽保留ACK24 | 12 | 4（非nested的四模式） | 0/0 | .575 |

三个patch严格正逆字节一致，AST两个Python投影均通过。真实FD五子场景均取实际C launch、原S先写marker、实际L/S关闭分支；nested branch与definition表也从实际SOURCE抽取。observer/sample/credentials/Seatbelt没有被软件替代验证，send_event仅隔离固定字段与返回A；因此不授完整事件账本/配额信用。
计划形成期间第一次过宽负控因unused index编译ERROR（2b0767/exit1）被明确拒收；修改负控表达式使其仍消费index后，1808c8及最终e73010得到真实Assertion。该错误不是RED信用，也未据此修改实际文件。

### 8.2 selfSPEC → selfQUALITY

selfSPEC C0/I0/M0：两根实际拒绝/生命周期缺口都有对应最小资产；原12与所有其它旧诊断断言保留或明确迁移；两处关闭正负控、已占8、真实spawn/fork/重复/nested闭包齐全；不扩大profile、cap、case、协议或CI。
selfQUALITY C0/I0/M0：从依赖/资源/权限角度复查，predicate只调用已定义definition_at且仅fd20+4/slot2时查询；root原有ACK传承，不新增后代管道；父子marker/ACK原关闭顺序不变；临时软件最多两代且wait/alarm有界；SOURCE只B/C，TEST独立。自审不能替代fresh实际审者。

【架构级自检报告】

- ✅ 语法/编译：两个Python投影AST与严格C匿名编译通过。
- ✅ 依赖/调用链：实际definition/launch/S-first/L-S/nested提取闭包完整，source binding补此PLAN。
- ✅ 逻辑/边界：12GREEN与三类真实生命周期负控；未放宽其它ACK。
- ✅ 异常处理：dup2即时errno/exit85、原fcntl/pipe故障、SIGPIPE/断stderr断言保留。
- ✅ 关联模块：仅列明三条未来路径；helper/limit/CI及原26输入摘要保持。
- ✅ 兼容安全：原profile、NPROC、cap1、M0A2_SOURCE0、cleanup准入不动；软件≠Darwin。
- ✅ 可运行性：计划匿名软件资产100%通过；正式落盘TDD及双Mac native仍待验收。

### 8.3 批准WFP输入同步复核

作者ab2205重跑§7完整匿名driver，wall3.668s/exit0：RED仍12方法/16Assertion；GREEN12P；pre/post各1Assertion、broad4Assertion，全程0ERROR/skip。A/B/C patch及三个投影hash与§8.1逐字节相同，严格逆向与Python AST仍通过。本次selfSPEC→selfQUALITY均C0/I0/M0：只改输入账本及摘要断言，保留旧批准SHA与CI/摘要历史，不新增设计、实际TEST/SOURCE/CI或原生信用；七维自检结论与上节相同且仅限匿名软件层。当前修订等待独立DOCS双审，正式TEST尚未授权。

**Execution Mode:** serial。当前只交PLAN等待root全文/fresh双审，明确不自动执行技能的实施默认。

