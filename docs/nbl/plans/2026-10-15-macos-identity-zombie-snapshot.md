# Mac identity zombie snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅使现有身份聚合快照在已列举PID为zombie时请求完整BSD身份，保留所有不完整观察的unknown拒绝，并用独立Darwin自有child正控验证实际查询兼容性。

**Architecture:** identity_lease聚合算法唯一proc_pidinfo调用的既有arg由0改为1；六UID/GID计数、kill ESRCH规则、lease前后复核及诊断不变。软件TEST仍12方法，新增native-only一方法在自有child列表投影下运行实际helper算法与真实Darwin查询，和全机枚举信用分账；两个controller补齐来源，原MacA加独立零skip门及证据目录。

**Tech Stack:** 既有C/libproc、Python stdlib unittest、已有cc；未来双Mac CI实际SDK/header/kernel/binary绑定，无新依赖、私有syscall、符号别名、root或lease授权。

---

## 1. 授权、真实问题与证据上限

本轮仅可apply_patch写唯一ignored文档 docs/nbl/plans/2026-10-15-macos-identity-zombie-snapshot.md。实际SOURCE/TEST/CI均不落地，不Git写、不full/native/root/系统配置/安装/KEY，不触root两DOCS或其它PLAN。main-only；writing-plans技能的额外DESIGN/worktree/提交/自动实施默认被本次PLAN-only明确覆盖。root已实际完成e25744三步思考，作者不冒称亲调。

本次读取HEAD436751cf590c3d49b9506cf9b538e6419ddd7c0f，根工作区/home/orbbec/projects/icode。root两DOCS dirty保留。root提供436751 Intel A原件11928305869、ZIP112053B/SHA前缀fb10c11…尾4e9d及unknown诊断：这是实际失败，但没有证据证明PID2045就是zombie，不把机制研究倒写成现场根因。起草时436751全部CI仍动态；root现核三run/56unique job全部终态49成功/3失败/4skip，等待条件解除，但不授本修复任何新验收。B受needs占位skip不是cap2nativeGREEN。此前6dbc/436已取得正式quotaRED，并不消除本次A身份快照盲点，不授M0/R2/R3。

三问有实际源码依据：真实问题为全PID列举可包含退出未reap成员，而聚合查询arg0可能不返回该成员的BSD记录；已有proc_pidinfo、process_count_snapshot/emit/reserve算法及12项软件探针可复用；调用链为root reserve_uid与unused-identity/后续计数，现有driver/groups/vectors的其它arg0是受控活子/self，V7另用sysctl，不统一修改。本片仅收窄一次聚合查询的可观察语义，不跳过unknown、不重试、不补零，不变quota/cap/8192边界或持久身份。

使用writing-plans、TDD与testing-anti-patterns；已完整读取相应指引。正式实施必须独立TEST作者先落盘RED，不同SOURCE作者实施；匿名软件成功不能替正式TDD。当前停于root全文→freshSPEC→不同QUALITY，尚未授权执行。

## 2. 固定主源与取舍

观察日2026-10-15。root研究已覆盖xnu-11215.1.10和xnu-12377.1.9的allproc/zombproc及libproc转换，作者本轮定点亲核：
- [11215 proc_info](https://github.com/apple-oss-distributions/xnu/blob/xnu-11215.1.10/bsd/kern/proc_info.c)与[12377 proc_info](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/kern/proc_info.c)：指定BSD flavor的非零arg开启findzomb，仍经安全策略检查。
- [12377 libproc wrapper](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/libsyscall/wrappers/libproc/libproc.c)：底层失败映射0，调用者必须保存errno。
- [libproc header](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/libsyscall/wrappers/libproc/libproc.h)明确属于可变的private interfaces；[proc_info.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/sys/proc_info.h)和[proc.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/sys/proc.h)给出BSD字段及SZOMB。

这不是公开稳定SDK保证，也未与runner kernel24.6逐字绑定。未来native门记录实际SDK/version、三个SDK header raw SHA、clang、kernel/build、动态符号及source/generated-C/binary SHA，再观察实际系统。只借APSL2.0机制，未复制上游实现或新增底层syscall/别名。

采纳：仅聚合query arg1与真实自有child兼容正控；收益是能计入完整可读zombie身份，成本为一行算法和TEST/来源/CI配套。暂缓：全机unknown的其它权限/并发根因、cap4/race、身份逃逸或安装。拒绝：把0/ESRCH+kill0当已消失、用root解决普通child测试、跳unknown、遍改其它arg0、以固定开源tag等同SDK/runtime认证。研究与测试独立，不重刷20项目。

## 3. 不变量与原生设计

生产仅Asset D一行；满长返回后仍按pbi_ruid/uid/svuid/rgid/gid/svgid任一匹配计一个PID。外UID/GID zombie不计。包括arg1仍0/ESRCH+kill0、short/negative/其它errno时，原unknown拒绝不变；只有原kill<0且ESRCH允许继续。8192界、两次lease扫描、目录lookup优先顺序、碰撞扫描次数、SIGPIPE前提、诊断字段/errno保存/持久租约保持。

软件Asset A不增加方法：fake_info允许0或1避免旧源_exit201假RED；仅zombie场景在arg0模拟0/ESRCH+kill0，arg1返回真实六字段模型。原source对zombie_six_fields/foreign/collision得到3条语义Assertion、两父失败；原其它断言不删除。新增zombie_unknown在arg1也返回0/ESRCH+kill0，必须仍拒绝。原short/error、list界、post-lease、namespace、真实SIGPIPE路径全部保留。

Asset B在机械TEST内仅将唯一新query语义逆回旧query，再核原完整lease SHA3c8e74…；随后原诊断逆向与原driver哈希a65f067…证明继续执行。不是换一个期望hash来补绿；其它字节改变仍会失败。旧source下该迁移TEST也通过，正式RED来自真实计数缺口。

### Darwin native门边界

Asset C完整新TEST，一方法仅在Darwin且ICODE_RUN_IDENTITY_ZOMBIE_NATIVE=1时显式启用；Linux full新增一个明确native-only skip，普通Mac未显式启用也skip，不要求本地默认discovery具备GitHub环境。该flag只准入测试夹具，不授模型或产品环境权限，不能混入严格软件12门。MacA新step明确设置flag=1，先严格软件12零skip，再严格native1零skip，之后才原A基线/SOURCE流程，B原needs不改。native拒绝root/euid0，既有普通runner运行，无账户/lease/quota/沙箱新权限。

唯一枚举替身是proc_listallpids→已知自有child一个PID；不是全系统列举证明。process_count_snapshot从实际lease源码原样提取，proc_pidinfo仅观察并调用真实原符号，arg由当前helper决定，kill/waitid/waitpid都真实；不独立硬编码arg1冒SOURCE验收。

父子ready/release管道确保live观察，然后waitid(WEXITED|WNOWAIT)证明正常退出未reap，再实际聚合计数1；PID/parent/start身份必须与live相同、六字段一致、status==SDK SZOMB，foreign目标计数0。父waitpid回收后，再用旧PID查询；只有真实不存在且原ESRCH规则给0才接受。完整不同start的PID复用记观察不足失败，不当旧child、不对其发signal。清理只对尚未reap的自有child SIGKILL+waitpid；reap后立即撤销child句柄，绝不信号复用PID。

C父alarm10、子alarm8，SIGALRM/SIGTERM触发受控收尾，Python15秒沟通超时后仅终止仍持有Popen再给3秒收尾，最后必要强杀仅该Popen；任何超时/清理不足保持unknown并失败。成功必须显式reaped=true与旧identity拒绝。无native原件就不授清理信用。软件不验证这些Darwin路径，本轮仅AST/静态审查，不编译运行native。

native在RUNNER_TEMP下全新精确子目录保留probe.c/编译binary、每条命令stdout/stderr、binding.json；collect遇TimeoutExpired先保存已有exc.stdout/stderr bytes（缺失为b空串）和timed_out=true/exit_code=null命令记录，再原异常重抛；不重试或延长timeout，result未接受且cleanup仍unknown。原always artifact增加该目录。记录同GITHUB_SHA/实际git HEAD、run/attempt、arch、SDK头hash、nm真实_proc_pidinfo/_kill/_waitid/_waitpid且无_proc_listallpids、raw digests。A/B两个controller原来源元组各添加nativeTEST和本PLAN，其余来源/解析/接受门不变。全机枚举和root A/W1/B原链仍须同候选另验，不以自有child正控覆盖整机unknown。

## 4. 冻结输入与输出

必须逐raw核对；其它作者推进HEAD/CI时先停止核差异，经root授权解释组合，不覆盖变化或伪称仍436751。当前未来实现共七路径（六改一新），加本PLAN来源共八；root两进度DOCS当前不在实施范围，若后来获准修改须扩实际全片审查。其它PLAN、vendor、TEST及受控arg0不改。

### 原始输入

| 路径 | 行数 | 字节 | SHA256 |
|---|---:|---:|---|
| native/mac/tests/icode_m0a1_identity_lease.inc | 117 | 5497 | 3c8e74cffa0dfda2fc8e7cf91e67cd6db99c7a5c88167ab9c95925887356ada5 |
| tests/test_macos_identity_snapshot_diagnostics.py | 303 | 15631 | cb122e84187ca669daf7918280b72719baa3f95bb1f3491b6458d5739e64425f |
| tests/test_macos_process_groups_native.py | 528 | 31897 | c87354483a29ffaa412c83f623af1d0f8f73b03aff4d44975bc36ab47aa60475 |
| scripts/run_macos_m0_ci.py | 431 | 24193 | d6bceacd396b95580c3abfe281b9a2d8a80d3d219a52e18944c05abd03723938 |
| scripts/run_macos_m0a2_vectors.py | 331 | 17878 | 0ba8585518263c1cd488a52d84c6fbc31a76f81a3965a05b0d2e0198204eea7e |
| .github/workflows/ci.yml | 2539 | 136233 | c154dbb7a1b0625a8a2b869f4e58bcae82cceb136fd303f03fbce922178a2030 |
| native/mac/tests/icode_m0a1_driver.c | 511 | 26164 | 141bedc63deadad332eb1d46a474d24d68c837248fd89247d04bea4819f1bf9a |
| native/mac/tests/icode_m0a1_process_groups_native.c | 389 | 19112 | ebe6071bd7b9e26c4948d1bbc87f496a149766e352231a5c0a5675d9f45194aa |
| native/mac/tests/icode_m0a2_vectors.c | 741 | 37292 | b1d4b3f97b038304dac76939db2bf25db485d21fc76ec57615fa54fa61328b0b |
| native/mac/icode_m0a1_limit.c | 16 | 629 | a5fb47b059c9a877089d46284fe938ae6131198e9b5b3c24e8522b6e43daf001 |
| native/mac/icode_m0a1_limit.h | 7 | 207 | caa37e7f999ddefe5550726275d242c93155af9e62a4d23e22f21cb018f1ecd2 |

### 输出与资产

| 资产/路径 | 行数 | 字节 | SHA256 |
|---|---:|---:|---|
| A tests/test_macos_identity_snapshot_diagnostics.py | 313 | 16388 | 51843b0dd22666b9436f5ffa9d374d7c5f3fb2aec3c679ac99678eecb0b78587 |
| B tests/test_macos_process_groups_native.py | 535 | 32450 | 0a32b0c9371c1863304e20f93628905fa48e122678aa98ec236acdeedfe957f2 |
| C tests/test_macos_identity_zombie_native.py | 309 | 14912 | 254c6d54b1111d68a9a895606d869cd2e2c12aa1e8d527d8dfdca76131b54fd8 |
| D native/mac/tests/icode_m0a1_identity_lease.inc | 117 | 5551 | 524b43b60e0d035581427b19511e05245aa0e59f22ca1caa5d1433a7dbdca980 |
| E scripts/run_macos_m0_ci.py | 433 | 24326 | bd2aba735d643ab4315f5a7a8cc38866a22ff18eb2a35d457b4a2271f148855b |
| F scripts/run_macos_m0a2_vectors.py | 333 | 18011 | cb3aa7b402e022ceda382bd9f4d567de838a82da8a7c9f8a82dccc86edaa62a9 |
| G .github/workflows/ci.yml | 2546 | 136798 | 24bd6e5c203f56d1de4e16c0ab4c17f20ff8a4424b67309ba8467222b6689e2a |

| patch | 行数 | hunks | SHA256 |
|---|---:|---:|---|
| A | 62 | 4 | 04624a3096d241c0e5e00d1639eb15690542f5120f7f7426076665f8ddd4debe |
| B | 16 | 1 | 3bb5d5fa21b3be514c69e5447ba8d63b8e208c5b6481c051ce3e1f75abc5e184 |
| D | 11 | 1 | 5f21193cad631cde409a3c5ece87dbfb1ffbf24b16f548e2cdac4422fe8a4591 |
| E | 11 | 1 | 318e412cd54d65fc3c705b15e5c81e640f770a9651cb53a471a50e4e4ddbec5b |
| F | 11 | 1 | 38f7907693d49e8e8f50d098e9f1865755712fe5f89f342fce3a9369f04f18ae |
| G | 23 | 2 | 912d6c3262434f26098fc40ce40aa633cf70a7ba3ca1c08609963f2740e3a2c7 |

所有资产UTF-8/LF、保留末LF；统一patch中单空格空context合法，不冒原始文档whitespace全零。Asset C不是native已通过记录。

## 5. 串行实施（未来，不自动执行）

### Task 1：独立TEST作者落A/B/C

**Dependencies:** None（root全文、freshSPEC、不同QUALITY全零之后）。
**Parallelizable:** No（先冻结正式RED）。
**状态**
- [ ] 任务完成

- [ ] 核11输入、main/index/pin、native新文件不存在与root脏文件保护。
- [ ] 仅apply_patch Asset A/B和完整C，不改helper/controller/CI/PLAN；完整保留原12和机械断言。
- [ ] 在WSL仓库根正式运行下面strict12：预期12方法、两红父/3Assertion、0ERROR/skip、exit1；机械单方法预期1P/exit0。编译失败/_exit201/import错误不是RED，停报root而非放宽oracle。
- [ ] native新文件只AST及一方法计数，不本机Darwin/native/root；Linux skip不冒成功。
- [ ] 自SPEC→selfQUALITY/七维，再actualTEST freshSPEC→不同QUALITY；零后冻结三TEST，交不同SOURCE作者。

```bash
PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests',pattern='test_macos_identity_snapshot_diagnostics.py'); assert s.countTestCases()==12; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -m unittest tests.test_macos_process_groups_native.TestW1MechanicalLeaseExtraction.test_driver_inverse_is_exact_original -v
```

### Task 2：不同SOURCE作者落D/E/F

**Dependencies:** Task 1正式RED及实际双审全零。
**Parallelizable:** No（三TEST冻结）。
**状态**
- [ ] 任务完成

- [ ] 重新核原输入，仅apply_patch Asset D一行query及E/F来源绑定，不改TEST/CI或其它arg0。
- [ ] 运行相同strict12，预期12P/0F/E/skip；机械单方法1P。只有当前helper原样进入真实OS边界，不把wrapper或假结果当修复。
- [ ] 核D/E/F输出SHA、统一patch每hunk唯一正向/逆向回原输入；cap2/driver/groups/vectors及CI不变。
- [ ] 自SPEC→不同角度selfQUALITY及七维；actualSOURCE freshSPEC→不同QUALITY，零后停等root。无Git写入。

### Task 3：root落G、全片与候选

**Dependencies:** Task 2实际双审零；上一436751全部run/job终态之后才允许推新候选。
**Parallelizable:** No（root独占CI/候选）。
**状态**
- [ ] 任务完成

- [ ] 核共享CI当前输入，apply_patch仅G两个hunks；保留strict软件12、原A/B预算/权限/架构/后续命令及M0A2_SOURCE=1。
- [ ] 软件12及机械1各自计数/零skip；full-suite-budget3必要软件回归，现有零skip软件门不掺native skip；不本机full/native/root。
- [ ] 核七实现+本PLAN来源实际scope、source counts、原字段/接受门；全片freshSPEC→不同QUALITY。新native1命令和artifact path必须实际接线，不能仅把文件纳discovery。
- [ ] 只有root可按既有main候选授权做索引/密钥/pin/提交推送；本PLAN不授权作者Git操作，vendor不升级。新增DOCS需明确纳scope再审。

### Task 4：同SHA双Mac观察

**Dependencies:** Task 3实际新SHA候选。
**Parallelizable:** No（按真实job及原证据终态分账）。
**状态**
- [ ] 任务完成

- [ ] Intel/ARM实际软件12零skip、native1零skip；检查native raw/JSON、source/headers/generated-C/binary/hash/SDK/kernel/arch/candidate/attempt及自有child回收。
- [ ] native失败不得改用root/跳unknown/硬编码arg1/移除gate或取消重跑刷绿；不完整query、PID复用、SDK不兼容按失败保留。native门失败导致后续A/B未运行只记skip。
- [ ] 同候选原A/W1/B全机枚举、quota/manifest/lease等仍单独验；自有child门GREEN不授全机可观测或M0/R2/R3，也不证明原PID2045的身份。
- [ ] 保留原failure、skip及unknown，报告实际源码/SDK/API兼容边界；不借固定XNU版本或Linux软件GREEN升级原生信用。

## 6. 本轮匿名证据、自SPEC→selfQUALITY

实际仅RAM投影+现有临时C软件夹具（工具225e14）：
- 新A+旧helper：12方法、两父失败/3Assertion、0ERROR/skip，.233s；失败恰zombie_six_fields、zombie_foreign、zombie_collision，不是_exit201或编译ERROR。
- 新A+D投影：12P/0F/E/skip，.118s；zombie_unknown及原short/errors仍拒绝，原12门保留。
- 新B+D投影：机械1P/.001s；保留原lease完整hash与更早driver inverse hash。
- C Python AST通过；没有Darwin编译或运行，没有任何nativeGREEN证据。E/F/G仅RAM资产生成/正逆/AST，§7供root复核。
- 初次传输把payload重复base64，Windows命令长度限制在启动前拒绝；改为单层编码后执行成功。不把传输失败算产品RED；未为绕过限制写脚本到仓库。

selfSPEC C0/I0/M0：query只一点、真实六字段/foreign与unknown约束、机械语义逆向、独立原生门、两来源与CI/artifact成对；七完整实现资产给定，不留占位代码。所有正式与原生阶段仍未执行。
selfQUALITY C0/I0/M0：不完整读取不归零，原lease/scans/diagnostic保持；PID复用不变旧身份且reap后不signal；nativechild列表投影不冒全机，实际private libproc/SDK与核验上限清楚；A/W1/B旧链及quota不改。自审不能替root不同双审。

【架构级自检报告】
- ✅ 语法/编译：软件实际严格C编译/RAM执行通过，Python投影AST通过；Darwin源码仅静态，不冒编译成功。
- ✅ 依赖/调用链：实际聚合helper→六字段→lease前后检查；两个controller来源和新原生门完整。
- ✅ 逻辑/边界：旧两父3Assertion→12P，foreign/unknown、8192和旧扫描顺序保持。
- ✅ 异常处理：short/error/0ESRCH+kill0仍unknown；子进程超时/回收不足不授成功。
- ✅ 关联模块：机械原hash证明保留；CI软件12与native1分开；其它arg0/header/limit不改。
- ✅ 兼容安全：无新root/lease/API别名/syscall/权限依赖；private模式不承诺稳定SDK。
- ✅ 可运行性：匿名软件层通过；正式TEST/SOURCE/CI及同SHA双Darwin/全机验收均待。

### 6.1 本次PLAN-only增量复核

root已全文读旧761行/45703B/SHA8895fe73f618ac9d5c16fe750066b372035c3f97ceff0d5381a8120a717e1db7后指出兼容I1与超时原件缺口，本次仅修本PLAN。C新增Darwin+显式flag准入及类说明；G新step设置flag=1，仍严格1项零skip。C.collect仅新增TimeoutExpired分支，保存已有两路bytes和timed_out/exitunknown记录后裸raise，不改已有成功路径、timeout、重试、原生生命周期或生产query资产。A/B/D/E/F原patch及输出逐字节不变，11实际输入保持；C/G及摘要同步。

匿名工具e155a0：准入矩阵3项通过（Darwin无flag拒、Darwin flag1启、Linux flag1拒）；提取实际C.collect做TimeoutExpired mock两项，通过partial bytes/无输出bytes保存、exit_code=null/timed_out=true、仅调用一次及抛同一异常对象。此mock不授SDK/原生或真实超时信用。§7重放所有输入/六patch正逆与七输出摘要/AST通过；旧source仍12方法两父3Assertion、0ERROR/skip/.166s，投影12P/0F/E/skip/.109s，机械1P/.001s。没有编译或运行Darwin。默认普通Mac未opt-in也不运行依赖GitHub绑定的夹具；Linux full新增1skip边界保持。

本次selfSPEC→selfQUALITY C0/I0/M0：测试准入不是产品authority；严格CI不以skip放行；失败原件与unknown状态保持。七维增量自检：Python/patch语法通过，来源/CI依赖完整，准入矩阵与未知退出边界通过，原异常不吞，资产关联摘要同步，默认Mac兼容且生产不变，软件匿名可运行而Darwin仍待同SHA双平台。反向撤销本次精确增量应完整回旧761行/45703B/8895fe73…，不得把前761行当旧全文；自审不替root增量回读或freshSPEC→不同QUALITY。

## 7. 可重放的RAM核查

在WSL仓库根将下面唯一驱动经stdin交现有python -B；不将驱动写入项目文件。它只编译既有软件stub，C native仅AST，不运行。每软件cc/探针使用原timeout，串行/j1；失败停报，不改冻结资产补绿。

```python
import ast,hashlib,io,re,time,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path.cwd()
PLAN=ROOT/"docs/nbl/plans/2026-10-15-macos-identity-zombie-snapshot.md"
text=PLAN.read_bytes().decode("utf-8")
def sha(value):
    return hashlib.sha256(value).hexdigest()
def asset(letter,language):
    part=text.split("### Asset "+letter+" —",1)[1]
    fence=chr(96)*3
    return part.split(fence+language+"\n",1)[1].split("\n"+fence,1)[0]+"\n"
def project(before,patchtext):
    groups=re.split(r"^@@[^\n]*\n",patchtext,flags=re.M)[1:]
    pairs=[]
    for group in groups:
        rows=group.splitlines(keepends=True)
        assert all(row[:1] in (" ","+","-") for row in rows)
        a="".join(row[1:] for row in rows if row[0]!="+")
        b="".join(row[1:] for row in rows if row[0]!="-")
        pairs.append((a,b))
    after=before
    for a,b in pairs:
        assert after.count(a)==1,(a[:80],after.count(a))
        after=after.replace(a,b,1)
    reverse=after
    for a,b in reversed(pairs):
        assert reverse.count(b)==1
        reverse=reverse.replace(b,a,1)
    assert reverse==before
    return after
input_part=text.split("### 原始输入",1)[1].split("### 输出与资产",1)[0]
inputs=re.findall(r"^\| ([^|]+) \| (\d+) \| (\d+) \| ([0-9a-f]{64}) \|$",input_part,re.M)
assert len(inputs)==11,len(inputs)
for name,lines,size,expected in inputs:
    raw=(ROOT/name).read_bytes()
    assert (len(raw.splitlines()),len(raw),sha(raw))==(int(lines),int(size),expected),name
mapping={
 "A":"tests/test_macos_identity_snapshot_diagnostics.py",
 "B":"tests/test_macos_process_groups_native.py",
 "D":"native/mac/tests/icode_m0a1_identity_lease.inc",
 "E":"scripts/run_macos_m0_ci.py",
 "F":"scripts/run_macos_m0a2_vectors.py",
 "G":".github/workflows/ci.yml",
}
new={}
for letter,name in mapping.items():
    patchtext=asset(letter,"diff")
    new[name]=project((ROOT/name).read_bytes().decode("utf-8"),patchtext)
    print(letter,name,len(new[name].splitlines()),len(new[name].encode()),sha(new[name].encode()),
          "patchsha",sha(patchtext.encode()))
    if name.endswith(".py"):ast.parse(new[name])
native=asset("C","python")
assert not (ROOT/"tests/test_macos_identity_zombie_native.py").exists()
ast.parse(native)
assert sum(isinstance(n,ast.FunctionDef) and n.name.startswith("test_")
           for n in ast.walk(ast.parse(native)))==1
print("C native AST-only",len(native.splitlines()),len(native.encode()),sha(native.encode()))
outputs=re.findall(r"^\| ([A-G]) ([^|]+) \| (\d+) \| (\d+) \| ([0-9a-f]{64}) \|$",text,re.M)
assert len(outputs)==7
for letter,name,lines,size,expected in outputs:
    value=native if letter=="C" else new[name]
    assert (len(value.splitlines()),len(value.encode()),sha(value.encode()))==(int(lines),int(size),expected),name
# No importing or running C/native code: only Python AST above.
lease=ROOT/"native/mac/tests/icode_m0a1_identity_lease.inc"
def software(label,source):
    module=types.ModuleType("zombie_ram_"+label)
    module.__file__=str(ROOT/"tests/test_macos_identity_snapshot_diagnostics.py")
    exec(compile(new["tests/test_macos_identity_snapshot_diagnostics.py"],module.__file__,"exec"),module.__dict__)
    module.LEASE_SOURCE=source
    suite=unittest.defaultTestLoader.loadTestsFromModule(module)
    assert suite.countTestCases()==12
    stream=io.StringIO();start=time.monotonic()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    parents={getattr(case,"test_case",case).id() for case,_ in result.failures}
    print(label,result.testsRun,"parents",len(parents),"assertions",len(result.failures),
          "errors",len(result.errors),"skip",len(result.skipped),"seconds",round(time.monotonic()-start,3))
    assert not result.errors and not result.skipped,stream.getvalue()
    if label=="old":
        assert len(parents)==2 and len(result.failures)==3,stream.getvalue()
        assert all("AssertionError" in detail for _,detail in result.failures)
    else:assert result.wasSuccessful(),stream.getvalue()
software("old",lease.read_text(encoding="utf-8"))
software("projected",new[str(lease.relative_to(ROOT))])
module=types.ModuleType("zombie_mechanical_ram")
module.__file__=str(ROOT/"tests/test_macos_process_groups_native.py")
exec(compile(new["tests/test_macos_process_groups_native.py"],module.__file__,"exec"),module.__dict__)
actual_read=Path.read_bytes
def read_bytes(path):
    if path==lease:return new[str(lease.relative_to(ROOT))].encode()
    return actual_read(path)
suite=unittest.TestSuite([module.TestW1MechanicalLeaseExtraction("test_driver_inverse_is_exact_original")])
with patch.object(Path,"read_bytes",read_bytes):
    result=unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful() and not result.skipped
print("source/TEST/controller/CI RAM inverse+AST; old2parents3Assertion/project12P/mechanical1P; native not run")
```

## 8. 完整冻结资产

### Asset A — 软件TEST，保留12方法

目标：tests/test_macos_identity_snapshot_diagnostics.py。

```diff
--- a/tests/test_macos_identity_snapshot_diagnostics.py
+++ b/tests/test_macos_identity_snapshot_diagnostics.py
@@ -72,22 +72,23 @@
  if(is("near_cap")) {
   memset(buffer,0,(size_t)bytes);p[MAX_PIDS-2]=101;return MAX_PIDS-1;
  }
- if(is("six_fields")) {for(int i=0;i<6;i++)p[i]=101+i;return 6;}
+ if(is("six_fields") || is("zombie_six_fields")) {for(int i=0;i<6;i++)p[i]=101+i;return 6;}
  p[0]=101;return 1;
 }
 static int fake_info(int pid,int flavor,unsigned long long arg,void *buffer,int bytes) {
- if(pid<101 || pid>106 || flavor!=PROC_PIDTBSDINFO || arg ||
+ if(pid<101 || pid>106 || flavor!=PROC_PIDTBSDINFO || arg>1 ||
     bytes!=(int)sizeof(struct proc_bsdinfo)) _exit(201);
  infos++;errno=EACCES;
+ if(is("zombie_unknown") || (!arg && (!strncmp(scenario,"zombie_",7)))) {errno=ESRCH;return 0;}
  if(is("info_zero") || is("info_chain") || is("info_esrch")) return 0;
  if(is("info_short")) {errno=EIO;return bytes-1;}
  if(is("info_negative")) {errno=EBADF;return -1;}
  struct proc_bsdinfo *p=buffer;memset(p,0,sizeof(*p));
- if(is("six_fields")) {
+ if(is("six_fields") || is("zombie_six_fields")) {
   uid_t *fields[]={&p->pbi_ruid,&p->pbi_uid,&p->pbi_svuid,&p->pbi_rgid,&p->pbi_gid,&p->pbi_svgid};
   *fields[pid-101]=UID_FIRST;
  }
- if((is("collision") && scans==1) || (is("post_positive") && scans==2)) p->pbi_svuid=UID_FIRST;
+ if((is("collision") && scans==1) || (is("post_positive") && scans==2) || is("zombie_collision")) p->pbi_svuid=UID_FIRST;
  return bytes;
 }
 static int fake_kill(pid_t pid,int sig) {
@@ -199,7 +200,8 @@
                 self.assertIn(b"scans=1 infos=0 kills=0 lookups=2 leases=0 errno=100",actual.stderr)
     def test_info_result_and_independent_kill_result_are_retained(self):
         for case,result,info_error,kill_result,kill_error in (
-            ("info_zero",0,errno.EACCES,0,0),("info_short",23,errno.EIO,-1,errno.EPERM),
+            ("info_zero",0,errno.EACCES,0,0),("zombie_unknown",0,errno.ESRCH,0,0),
+            ("info_short",23,errno.EIO,-1,errno.EPERM),
             ("info_negative",-1,errno.EBADF,-1,errno.EINVAL)):
             with self.subTest(case=case):
                 fields,actual=self.rejection(case)
@@ -233,6 +235,7 @@
         self.assertIn(b"REFUSAL stage=uid-directory-lookup",actual.stderr)
     def test_normal_collision_and_full_positive_count_stay_silent(self):
         for case,uid,scans,infos in (("valid",60000,2,2),("collision",60001,3,3),
+                                    ("zombie_collision",60001,3,3),
                                     ("lease_collision",60001,3,3),("near_cap",60000,2,2),
                                     ("nonpositive",60000,2,2)):
             with self.subTest(case=case):
@@ -250,6 +253,13 @@
         self.assertEqual(actual.returncode,0,actual.stderr)
         self.assertEqual(actual.stderr,b"")
         self.assertEqual(actual.stdout,b"uid=60000 scans=2 infos=2 kills=2 lookups=2 leases=1\n")
+        for case,count,infos in (("zombie_six_fields",6,6),("zombie_foreign",0,1)):
+            with self.subTest(zombie_case=case):
+                observed=self.probe("direct_"+case)
+                self.assertEqual(observed.returncode,0,observed.stderr)
+                self.assertEqual(observed.stderr,b"")
+                self.assertEqual(observed.stdout,
+                    f"count={count} scans=1 infos={infos} kills=0 errno={errno.EACCES}\n".encode())
         actual=self.probe("direct_six_fields")
         self.assertEqual(actual.returncode,0,actual.stderr)
         self.assertEqual(actual.stderr,b"")
```

### Asset B — 机械逆向TEST

目标：tests/test_macos_process_groups_native.py。

```diff
--- a/tests/test_macos_process_groups_native.py
+++ b/tests/test_macos_process_groups_native.py
@@ -187,6 +187,13 @@
         if marker in content:
             self.assertEqual(content.count(marker),1)
             lease=(driver.parent/"icode_m0a1_identity_lease.inc").read_bytes()
+            # Reverse only the reviewed zombie-query semantic projection, then prove the old full hash.
+            zombie_query=b"proc_pidinfo(pids[i],PROC_PIDTBSDINFO,1,&b,sizeof(b)); /* Include listed zombies in this identity census. */"
+            original_query=b"proc_pidinfo(pids[i],PROC_PIDTBSDINFO,0,&b,sizeof(b));"
+            if zombie_query in lease:
+                self.assertEqual(lease.count(zombie_query),1)
+                lease=lease.replace(zombie_query,original_query,1)
+            self.assertEqual(lease.count(original_query),1)
             if b"/* IDENTITY_SNAPSHOT_DIAGNOSTIC_BEGIN */\n" in lease:
                 self.assertEqual(hashlib.sha256(lease).hexdigest(),
                     "3c8e74cffa0dfda2fc8e7cf91e67cd6db99c7a5c88167ab9c95925887356ada5")
```

### Asset C — 完整新增Darwin-only TEST

目标：tests/test_macos_identity_zombie_native.py。

```python
"""Explicit opt-in Darwin owned-child CI fixture, not all-host enumeration proof."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import unittest

from tests.test_macos_identity_snapshot_diagnostics import function

ROOT = Path(__file__).resolve().parents[1]
LEASE = ROOT / "native/mac/tests/icode_m0a1_identity_lease.inc"

PRELUDE = r'''
#define _DARWIN_C_SOURCE 1
#include <errno.h>
#include <inttypes.h>
#include <libproc.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/proc.h>
#include <sys/proc_info.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
enum { MAX_PIDS=8192 };
static pid_t selected;
static volatile sig_atomic_t interrupted;
static struct proc_bsdinfo observed;
static int query_result,query_errno;
static uint64_t query_arg;
static void interrupt_handler(int value) { interrupted=value; }
static int owned_list(void *buffer,int size) {
 if(selected<=0 || size!=(int)(MAX_PIDS*sizeof(pid_t))) abort();
 ((pid_t *)buffer)[0]=selected;return 1;
}
static int observed_query(int pid,int flavor,uint64_t arg,void *buffer,int size) {
 int result=proc_pidinfo(pid,flavor,arg,buffer,size);
 int saved=errno;query_arg=arg;query_result=result;query_errno=saved;
 memset(&observed,0,sizeof(observed));
 if(result==(int)sizeof(observed)) memcpy(&observed,buffer,sizeof(observed));
 errno=saved;return result;
}
#define proc_listallpids owned_list
#define proc_pidinfo observed_query
'''
TRAILER = r'''
#undef proc_listallpids
#undef proc_pidinfo
static int one_byte(int fd,char *value,int writing) {
 ssize_t n;
 do {n=writing ? write(fd,value,1) : read(fd,value,1);}
 while(n<0 && errno==EINTR && !interrupted);
 return n==1 ? 0 : -1;
}
static int same_identity(const struct proc_bsdinfo *a,const struct proc_bsdinfo *b) {
 return a->pbi_pid==b->pbi_pid && a->pbi_ppid==b->pbi_ppid &&
        a->pbi_start_tvsec==b->pbi_start_tvsec && a->pbi_start_tvusec==b->pbi_start_tvusec;
}
static int same_six(const struct proc_bsdinfo *a,const struct proc_bsdinfo *b) {
 return a->pbi_ruid==b->pbi_ruid && a->pbi_uid==b->pbi_uid && a->pbi_svuid==b->pbi_svuid &&
        a->pbi_rgid==b->pbi_rgid && a->pbi_gid==b->pbi_gid && a->pbi_svgid==b->pbi_svgid;
}
static int matches(uid_t uid,const struct proc_bsdinfo *b) {
 return b->pbi_ruid==uid || b->pbi_uid==uid || b->pbi_svuid==uid ||
        b->pbi_rgid==uid || b->pbi_gid==uid || b->pbi_svgid==uid;
}
int main(void) {
 int ready[2]={-1,-1},release[2]={-1,-1},rc=2,reaped=0,status=0;
 pid_t child=-1;const char *stage="setup";
 struct proc_bsdinfo live,zombie;
 memset(&live,0,sizeof(live));memset(&zombie,0,sizeof(zombie));
 struct sigaction action;memset(&action,0,sizeof(action));
 action.sa_handler=interrupt_handler;
 if(sigemptyset(&action.sa_mask)<0 || sigaction(SIGALRM,&action,NULL)<0 ||
    sigaction(SIGTERM,&action,NULL)<0) goto done;
 if(signal(SIGPIPE,SIG_IGN)==SIG_ERR || signal(SIGCHLD,SIG_DFL)==SIG_ERR) goto done;
 alarm(10);
 if(pipe(ready)<0 || pipe(release)<0) goto done;
 child=fork();
 if(child<0) goto done;
 if(child==0) {
  if(signal(SIGALRM,SIG_DFL)==SIG_ERR) _exit(21);
  alarm(8);
  close(ready[0]);close(release[1]);
  char byte='R';
  if(one_byte(ready[1],&byte,1)<0) _exit(22);
  if(one_byte(release[0],&byte,0)<0 || byte!='X') _exit(23);
  close(ready[1]);close(release[0]);_exit(0);
 }
 selected=child;
 close(ready[1]);ready[1]=-1;close(release[0]);release[0]=-1;
 char byte=0;
 stage="live-ready";
 if(one_byte(ready[0],&byte,0)<0 || byte!='R') goto done;
 struct process_snapshot snapshot;
 stage="live-count";
 if(process_count_snapshot(getuid(),&snapshot)!=1 || query_result!=(int)sizeof(live)) goto done;
 live=observed;
 if(live.pbi_pid!=(uint32_t)child || live.pbi_ppid!=(uint32_t)getpid() ||
    live.pbi_status==SZOMB || live.pbi_start_tvsec==0 || live.pbi_start_tvusec>=1000000 ||
    !matches(getuid(),&live)) goto done;
 stage="release";
 byte='X';if(one_byte(release[1],&byte,1)<0) goto done;
 close(release[1]);release[1]=-1;
 stage="waitid-wnowait";
 siginfo_t info;int waited;
 do {memset(&info,0,sizeof(info));waited=waitid(P_PID,(id_t)child,&info,WEXITED|WNOWAIT);}
 while(waited<0 && errno==EINTR && !interrupted);
 if(waited<0 || interrupted || info.si_pid!=child || info.si_code!=CLD_EXITED || info.si_status!=0) goto done;
 stage="zombie-count";
 if(process_count_snapshot(getuid(),&snapshot)!=1 || query_result!=(int)sizeof(zombie)) goto done;
 zombie=observed;
 if(query_arg!=1 || zombie.pbi_status!=SZOMB || !same_identity(&live,&zombie) ||
    !same_six(&live,&zombie)) goto done;
 uid_t foreign=0;
 while(matches(foreign,&zombie)) foreign++;
 stage="foreign-zombie";
 if(process_count_snapshot(foreign,&snapshot)!=0 || query_result!=(int)sizeof(zombie) ||
    !same_identity(&zombie,&observed) || !same_six(&zombie,&observed)) goto done;
 stage="reap";
 pid_t got;
 do {got=waitpid(child,&status,0);} while(got<0 && errno==EINTR && !interrupted);
 if(got!=child) goto done;
 reaped=1;child=-1;
 if(!WIFEXITED(status) || WEXITSTATUS(status)!=0) goto done;
 stage="old-identity-after-reap";
 /* A reused PID must never be accepted as the old child or signalled below.
    A complete different-start query is observation interference, not success. */
 int count=process_count_snapshot(getuid(),&snapshot);
 if(query_result==(int)sizeof(observed)) {
  if(same_identity(&live,&observed)) stage="reaped-old-identity-still-visible";
  else stage="pid-reuse-observation-inconclusive";
  goto done;
 }
 if(count!=0 || query_result!=0 || query_errno!=ESRCH) goto done;
 rc=0;
done:
 {
  int saved=errno;
  for(unsigned i=0;i<2;i++) {
   if(ready[i]>=0) close(ready[i]);
   if(release[i]>=0) close(release[i]);
  }
  if(child>0) {
   /* child is unreaped: PID ownership is retained, so it cannot be reused. */
   if(kill(child,SIGKILL)<0 && errno!=ESRCH) rc=2;
   pid_t got;
   do {got=waitpid(child,&status,0);} while(got<0 && errno==EINTR);
   if(got==child) reaped=1;
   else rc=2;
  }
  alarm(0);
  if(interrupted) rc=2;
  if(rc || !reaped) {
   fprintf(stderr,"ZOMBIE_NATIVE_FAILURE stage=%s errno=%d query_arg=%" PRIu64
           " query_result=%d query_errno=%d cleanup=%s\n",
           stage,saved,query_arg,query_result,query_errno,reaped ? "owned_child_reaped" : "unknown");
   return 2;
  }
  printf("{\"version\":1,\"pid\":%u,\"parent\":%u,\"start\":[%" PRIu64 ",%" PRIu64
         "],\"live_status\":%u,\"zombie_status\":%u,\"query_arg\":1,"
         "\"counts\":[1,1,0,0],\"six_fields\":[%u,%u,%u,%u,%u,%u],"
         "\"waited_exit\":0,\"reaped\":true,\"identity_rejected\":true,"
         "\"cleanup\":\"owned_child_reaped\"}\n",
         live.pbi_pid,live.pbi_ppid,(uint64_t)live.pbi_start_tvsec,(uint64_t)live.pbi_start_tvusec,
         live.pbi_status,zombie.pbi_status,(unsigned)live.pbi_ruid,(unsigned)live.pbi_uid,
         (unsigned)live.pbi_svuid,(unsigned)live.pbi_rgid,(unsigned)live.pbi_gid,(unsigned)live.pbi_svgid);
  return 0;
 }
}
'''


def native_program(source):
    declarations = re.findall(r"^struct process_snapshot \{.*?^\};\n", source, re.M | re.S)
    if len(declarations) != 1:
        raise AssertionError("actual snapshot declaration unavailable")
    return PRELUDE + declarations[0] + function(source, "process_count_snapshot") + TRAILER


@unittest.skipUnless(
    sys.platform == "darwin" and os.environ.get("ICODE_RUN_IDENTITY_ZOMBIE_NATIVE") == "1",
    "explicit Darwin owned-child compatibility gate only")
class TestIdentityZombieNative(unittest.TestCase):
    """CI fixture is opt-in; default local discovery needs no GitHub environment."""
    def test_owned_child_live_zombie_and_reap_use_actual_snapshot_query(self):
        self.assertNotEqual(os.getuid(), 0, "native compatibility fixture must remain nonroot")
        self.assertNotEqual(os.geteuid(), 0, "native compatibility fixture must remain nonroot")
        expected_arch = os.environ.get("ICODE_ZOMBIE_EXPECTED_ARCH")
        self.assertIn(expected_arch, ("arm64", "x86_64"))
        self.assertEqual(platform.machine(), expected_arch)
        candidate = os.environ.get("GITHUB_SHA", "")
        self.assertRegex(candidate, r"^[0-9a-f]{40}$")
        runtime = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
        output = runtime / "icode-identity-zombie-native"
        self.assertFalse(output.exists() or output.is_symlink())
        output.mkdir(mode=0o700)
        binding = dict(version=1, candidate_sha=candidate, arch=platform.machine(),
                       kernel=platform.release(), result="unaccepted", cleanup="unknown",
                       enumeration="projected_owned_child_only", run_id=os.environ["GITHUB_RUN_ID"],
                       run_attempt=os.environ["GITHUB_RUN_ATTEMPT"])
        records = []

        def collect(label, command, *, timeout=15, input_bytes=None):
            try:
                result = subprocess.run(command, cwd=ROOT, input=input_bytes,
                                        capture_output=True, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                (output / (label + ".stdout")).write_bytes(exc.stdout or b"")
                (output / (label + ".stderr")).write_bytes(exc.stderr or b"")
                records.append(dict(label=label, argv=list(map(str, command)),
                                    exit_code=None, timed_out=True))
                raise
            self.assertLessEqual(len(result.stdout) + len(result.stderr), 131072)
            (output / (label + ".stdout")).write_bytes(result.stdout)
            (output / (label + ".stderr")).write_bytes(result.stderr)
            records.append(dict(label=label, argv=list(map(str, command)), exit_code=result.returncode))
            self.assertEqual(result.returncode, 0, result.stderr[:4096])
            return result.stdout.decode("utf-8", "strict").strip()

        try:
            self.assertEqual(collect("candidate", ["git", "rev-parse", "HEAD"]), candidate)
            binding["os_version"] = collect("os-version", ["/usr/bin/sw_vers", "-productVersion"])
            binding["os_build"] = collect("os-build", ["/usr/bin/sw_vers", "-buildVersion"])
            compiler = collect("compiler", ["/usr/bin/xcrun", "--find", "clang"])
            sdk = collect("sdk", ["/usr/bin/xcrun", "--show-sdk-path"])
            binding["sdk_version"] = collect("sdk-version", ["/usr/bin/xcrun", "--show-sdk-version"])
            binding["compiler_version"] = collect("compiler-version", [compiler, "--version"])
            headers = ("libproc.h", "sys/proc_info.h", "sys/proc.h")
            binding["sdk_header_sha256"] = {
                name: hashlib.sha256((Path(sdk) / "usr/include" / name).read_bytes()).hexdigest()
                for name in headers
            }
            source = LEASE.read_bytes()
            code = native_program(source.decode("utf-8")).encode("ascii")
            (output / "probe.c").write_bytes(code)
            binding.update(source_sha256=hashlib.sha256(source).hexdigest(),
                           test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           probe_sha256=hashlib.sha256(code).hexdigest(), sdk=sdk)
            executable = output / "probe"
            command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-Wno-unused-function", "-isysroot", sdk, "-x", "c", "-", "-o", str(executable)]
            collect("compile", command, timeout=30, input_bytes=code)
            binding["binary_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
            binding["binary_arch"] = collect("binary-arch", ["/usr/bin/lipo", "-archs", str(executable)])
            self.assertEqual(binding["binary_arch"], expected_arch)
            symbols = collect("symbols", ["/usr/bin/nm", "-u", str(executable)])
            imported = {line.split()[-1] for line in symbols.splitlines() if line.strip()}
            self.assertTrue({"_proc_pidinfo", "_kill", "_waitid", "_waitpid"} <= imported)
            self.assertNotIn("_proc_listallpids", imported)
            child = subprocess.Popen([str(executable)], cwd=ROOT,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            timed_out = False
            try:
                stdout, stderr = child.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                timed_out = True
                child.terminate()
                try:
                    stdout, stderr = child.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    stdout, stderr = child.communicate(timeout=3)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=3)
            self.assertLessEqual(len(stdout) + len(stderr), 8192)
            (output / "native.stdout").write_bytes(stdout)
            (output / "native.stderr").write_bytes(stderr)
            records.append(dict(label="native", argv=[str(executable)], exit_code=child.returncode,
                                timed_out=timed_out))
            self.assertFalse(timed_out, "owned-child timeout; cleanup remains unknown")
            self.assertEqual(child.returncode, 0, stderr.decode("utf-8", "replace"))
            self.assertEqual(stderr, b"")
            receipt = json.loads(stdout)
            self.assertEqual(set(receipt), {"version", "pid", "parent", "start", "live_status",
                                           "zombie_status", "query_arg", "counts", "six_fields",
                                           "waited_exit", "reaped", "identity_rejected", "cleanup"})
            self.assertEqual(receipt["version"], 1)
            self.assertEqual(receipt["query_arg"], 1)
            self.assertEqual(receipt["counts"], [1, 1, 0, 0])
            self.assertEqual(len(receipt["six_fields"]), 6)
            self.assertEqual(len(receipt["start"]), 2)
            self.assertTrue(receipt["reaped"] and receipt["identity_rejected"])
            self.assertEqual(receipt["cleanup"], "owned_child_reaped")
            binding.update(result="owned_child_query_verified", cleanup=receipt["cleanup"], receipt=receipt)
        finally:
            binding["commands"] = records
            binding["raw_sha256"] = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(output.glob("*.stdout")) + sorted(output.glob("*.stderr"))
            }
            (output / "binding.json").write_text(
                json.dumps(binding, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print("IDENTITY_ZOMBIE_NATIVE:" + json.dumps(binding, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
```

### Asset D — 唯一算法语义修改

目标：native/mac/tests/icode_m0a1_identity_lease.inc。

```diff
--- a/native/mac/tests/icode_m0a1_identity_lease.inc
+++ b/native/mac/tests/icode_m0a1_identity_lease.inc
@@ -43,7 +43,7 @@
     for(int i=0;i<n;i++) {
         if(pids[i]<=0) continue;
         struct proc_bsdinfo b;
-        int r=proc_pidinfo(pids[i],PROC_PIDTBSDINFO,0,&b,sizeof(b));
+        int r=proc_pidinfo(pids[i],PROC_PIDTBSDINFO,1,&b,sizeof(b)); /* Include listed zombies in this identity census. */
         int info_errno=errno;
         if(r!=(int)sizeof(b)) {
             errno=0;
```

### Asset E — A来源绑定

目标：scripts/run_macos_m0_ci.py。

```diff
--- a/scripts/run_macos_m0_ci.py
+++ b/scripts/run_macos_m0_ci.py
@@ -298,6 +298,8 @@
             "native/mac/tests/icode_m0a1_process_groups_native.c",
             "tests/test_macos_process_groups_native.py",
             "tests/test_macos_identity_snapshot_diagnostics.py",
+            "tests/test_macos_identity_zombie_native.py",
+            "docs/nbl/plans/2026-10-15-macos-identity-zombie-snapshot.md",
             "docs/nbl/plans/2026-10-15-macos-identity-snapshot-diagnostics.md",
             "tests/test_macos_process_groups.py",
             "tests/test_macos_task_quota_probe.py",
```

### Asset F — B来源绑定

目标：scripts/run_macos_m0a2_vectors.py。

```diff
--- a/scripts/run_macos_m0a2_vectors.py
+++ b/scripts/run_macos_m0a2_vectors.py
@@ -277,6 +277,8 @@
             "tests/test_macos_process_groups.py","tests/test_macos_m0a2_vectors.py",
             "tests/test_macos_m0a2_event_diagnostics.py",
             "tests/test_macos_identity_snapshot_diagnostics.py",
+            "tests/test_macos_identity_zombie_native.py",
+            "docs/nbl/plans/2026-10-15-macos-identity-zombie-snapshot.md",
             "docs/nbl/plans/2026-10-15-macos-vector-fd8-reservation.md",
             "docs/nbl/plans/2026-10-15-macos-identity-snapshot-diagnostics.md",
             "docs/nbl/plans/2026-10-14-macos-m0a2-event-diagnostics.md",
```

### Asset G — 原生门及原artifact接线

目标：.github/workflows/ci.yml。

```diff
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -2439,6 +2439,12 @@
       - name: Identity snapshot diagnostic software contract
         shell: bash
         run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_identity_snapshot_diagnostics.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
+      - name: Native owned-child identity zombie query compatibility
+        shell: bash
+        env:
+          ICODE_RUN_IDENTITY_ZOMBIE_NATIVE: "1"
+          ICODE_ZOMBIE_EXPECTED_ARCH: ${{ matrix.arch }}
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_identity_zombie_native.py'); assert s.countTestCases()==1, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Build the TESTOnly wrong baseline without SOURCE
         shell: bash
         run: |
@@ -2476,6 +2482,7 @@
           if-no-files-found: error
           retention-days: 14
           path: |
+            ${{ runner.temp }}/icode-identity-zombie-native/
             ${{ runner.temp }}/icode-m0a1-red/
             ${{ runner.temp }}/icode-m0a1-green/
             ${{ runner.temp }}/icode-m0a1-configure.log
```

---
**Execution Mode:** serial。PLAN-only：root全文→freshSPEC→不同QUALITY之后另行授权；当前不自动执行技能、不落实际TEST/SOURCE/CI、不提交。
