# Windows CI positive loopback exemption — software core only Implementation Plan

> For agentic workers: 后续经 root 全文及 freshSPEC/不同 QUALITY 批准后，才按 nbl.subagent-driven-development 或 nbl.executing-plans 实施。本轮仅 PLAN，禁止自动实施/提交。main-only 覆盖 worktree/分支默认，apply_patch 是唯一编辑方式。

**Goal:** 验证临时正控专用的 typed 关联、完整 SID/Attributes 映射与 owned 状态机；本片不执行或启用任何系统豁免。
**Architecture:** 仅新增一个无 I/O 的 Python 模型模块和完整软件 TEST。全部输入都是调用者的模型断言，不是 core 采集的 OS 证据；现有正控、权限、CI配置和产品路径不接入。
**Tech Stack:** 目标Python3.12标准库 dataclasses/json/hashlib/re/struct/unittest；复用默认 full-suite 测试发现，无新依赖或安装。本机无3.12，允许沿用既有3.11.17解释器做本片纯软件TDD诊断；既不恢复产品3.11支持，也不授实际3.12运行信用。

---

实施账（2026-10-15，覆盖下方冻结前的“未来/不存在/PLAN-only”叙述）：原冻结PLAN SHA `96d7fc18bda4713e599ed6ef68cf75764d13731a387426dd95d15e8e72e0e260` 已经root全文及fresh SPEC/不同QUALITY零审后解冻。独立TEST作者正式落A并经actualTEST双审零；root亲跑20=19指定Assertion RED/discovery1P/0ERRORskip（d3d647，日志SHAc42da017dc2c07b6ddce571e654c52c759c94d09bae453331e783c4502a63582）。不同SOURCE作者只落B，A/B字节不变；root实际新20＋旧15合35P/0skip（b690d8，日志SHA2f210f127422303b3da59caecf3ac9c7fbe2f4f8806b92eab426cc0307097223）。下方输入表及不存在条件是实施前冻结快照，不伪称当前文件不存在；当前两实际文件已存在，仅纯模型，无OS接线或授权。实际全片双审、候选线上真实3.12仍待；后续admin组件和真实consumer必须继续闭合。

## 1. 权威与范围

已批准 DESIGN：docs/nbl/specs/2026-10-15-windows-ci-positive-loopback-exemption-design.md，109L/20640B，raw SHA256 62f1ffa91d51ea837371a392f807d7bd325cf64c0e7cb1fc277030413324606c，freshSPEC/不同 QUALITY 双0。root 本轮实际三步 MCP 1d62a1 明确 software-only；作者不冒称亲调。
本片拆分由 root 明确批准。原起草基线1ce4c2a4896b4b56f87a08dc6fe347425a93524b及上轮重绑定beb499b7380404bac515174821e738ebde760390保留为历史；当前权威为已推main候选e94f72004071188b1c69e838f6faa98bc58e9723，父ca41c78d6f57938f8dd9aa1fb912dad7e44efe9c；DESIGN的b341仍是历史观察。本轮root结构化思考receipt为2fd95d。§3十二输入均重新按实际文件核对，仅tests/test_windows_appcontainer.py相对上版表格漂移；CI与旧budget hash均与上版相同。两代码资产完整字节不变。vendor仍21566a589cbe98bd35372a04bbb6ca1c51d8eed2。不修改其它作者dirty或线上候选。
用户已明确去掉Python3.11；产品最低版本和当前hostCI/安装观察通道为3.12，本片不把旧双矩阵当不可改约束。本轮重绑定只允许PLAN完整双审与当前三run观察并行；正式落TEST/SOURCE仍须root另行解冻，不要求先有本机3.12、不安装解释器。当前候选观察对象为CI38680822889、provenance38680822937、Pages38680822882，三者全部终态前不得推新候选；本PLAN不将交接时live状态冒称持续确认。实际3.12运行由本片未来同新SHA线上full承担，不能用本机3.11软件诊断替代。
未来本片实际仅两个新文件：src/icode/windows_positive_loopback_policy.py 和 tests/test_windows_positive_loopback_policy.py；当前两者必须不存在。本轮唯一可写为本文 ignored PLAN，不落实际SOURCE/TEST/CI，不Git写，不本机运行系统API/CLI。
后续两片尚未冻结代码资产且未实现，不能按本文实施：其一完整Get原件、admin受保护ACL/durable账本、固定System32单SID执行/回收/finally/always；其二真实TEST→Create成功后/launch前session→删除前清理→双nonce/原Reviewer→同SHA两Windows门。须分别完整PLAN/双审/独立TEST与SOURCE，不把此说明当已批准实施资产。core只是实际单SID临时豁免链的依赖；下一protected ledger与实际OS consumer计划仍必须闭合，core GREEN不授native通过。
这两片闭合前，临时豁免未实现、真实恢复未验证，不授Reviewer DENY/readiness/产品隔离完成。Reviewer及foreign永不豁免/改动；不另建SID作原生负控，不授权任何本机系统动作。
原CI默认full门已经发现test*.py；按root最终收敛，本片不新增专属CI门、不迁移旧TEST、不改任何已有门/权限/预算。第20方法验证既有发现路径，不用静态CI检查替代前19业务模型测试。

## 2. 复用与消费者合同

已完整读windows_runner_protocol.py（246行，length-prefixed spawn协议）及windows_provenance.py（125行，安装资源校验）。其schema、认证与用途不同，不能把spawn协议或相邻哈希当created/release授权，也不改其私有helper/公开ABI。复用exact shape/type、重复键拒绝、有界序列化和“不授权限”的机制；新模块不是第二个通用runner框架。
未来唯一消费者是受保护的CI-only admin协调器与标准用户固定正控session，不是产品CLI/模型API。其原件/执行/ACL及真实链路径尚未落地；本片没有环境开关、自动import接线、transport、任意命令/路径/地址入口。
未来admin在真实workflow/job/candidate/临时非admin身份、专用runner和显式授权检查后，将已绑定事实构成AdmissionFacts/Manifest。core只验证shape及exact true，不能从这些可构造布尔值认证GitHub/admin。SID字符串形状不证明真实Derive关系；必须由后续原件adapter核对。
固定真实链的消费次序：真实完整Get→显式Snapshot→begin→真实hr0创建事实profile_created→add_intent→持久化intent→实际唯一SID操作及完整Get→add_observed→真实双listener/token/Job结果probe_observed→fresh Get/真实命令回收事实cleanup_plan→实际窄清理及完整Get→cleanup_complete。此顺序是后续接口消费合同，不代表本片执行上述OS动作。
Snapshot的api_code/complete/released/reaped无默认成功值，必须显式提供；core仍只处理断言。标准用户将来可用encode_request，admin确认受保护句柄/发送者后用validate_request；后者仅关联校验，不认证来源/ACL，nonce也不是秘密认证。
State和CleanupPlan不可变，但不是host epoch/凭证。add_intent只创建内存状态，不证明持久化；cleanup_plan.action的delete/absent/refuse只为模型建议，绝非执行授权。调用者保存旧对象可重放；后续durable one-shot账本/进程身份/ACL必须独立阻止，不让旧对象绕过。Asset A方法名中的one-shot仅指当前已推进phase的重复调用拒绝，不证明旧created对象不能重放。
modeled_restoration只表示传入的完整post映射满足当前map减owned target的等式；输出固定native_authorized=false、native_restoration_verified=null。即使status=modeled，也不能重命名为真实恢复receipt或进入产品准入判断。
Manifest冻结同一started_ms/deadline_ms，最长60000ms，所有工作及最后导出检查累计deadline。时间由未来同一受信admin单调时钟提供；此模块无clock/sleep。过期仍可计算owned清理并保留deadline首错，但不授成功，不宣称物理I/O hard deadline。
地址不作为输入，仅对应未来固定127.0.0.1/::1；端口exact int，matrix为现CMake架构x64/ARM64。payload保持原固定双栈JSON的nonce/SID/1cap形状，token真实性、真实收包、实际Job回收均由后续consumer提供证据。
若后续实际消费者无法安全复用这些接口，须重新冻结资产，不以增加通用query/执行器掩盖缺口。本片独立可交付物为受测试的专用纯软件核，不对完整DESIGN阶段验收。

## 3. 精确输入与输出

任何输入漂移先停止报告，不改TEST补绿。原不改文件只核hash与必要精确引用，不复制其实现。本片除两个新文件外无未来代码改动。

| 输入路径 | raw SHA256 |
| --- | --- |
| DESIGN（§1） | 62f1ffa91d51ea837371a392f807d7bd325cf64c0e7cb1fc277030413324606c |
| .github/workflows/ci.yml（2541L/136918B） | b4e10208ee1c28ddc45d9bc81365791ec58af5ada34aba220182700fdd01cb18 |
| scripts/run_full_suite_ci.py（71L/2526B） | cfef3f0ed06661ffee7781ab66978b402dd897af085f885d5bb5c990f9284bd7 |
| tests/test_full_suite_ci_budget.py（42L/2514B） | 2c56b7ad877896bf76e1d84c07d9368d11cf488d57711c5de024067c46231a10 |
| src/icode/windows_runner_protocol.py（246L/8846B） | c29b163d0a3c67885e34dce0e3660dc21feaa186a06b1c6c35dcb7bf94de2ac1 |
| src/icode/windows_provenance.py（125L/5300B） | 244d32edfb229c340c66891f07e5bbae7412f01baf44f20945f8363aeeb72a28 |
| tests/test_windows_runner_protocol.py（236L/9242B） | 130a5eac707d14a0739d3a1f50e2fafd4d64d44b77e9f846be096f7b51a909bf |
| tests/test_windows_appcontainer.py（9719L/477980B） | 3fcb8ab511c99ad76e7e39bd17a0ce3acb1dae7a97d07300e485e58a52e3419e |
| src/icode/windows_appcontainer.py | 307dc730bf28bc661ad99b8d02dc9093b51c1dcdf45f993b470e68a5562f1a1f |
| src/icode/windows_job.py | ac2bfbe924a9b03b68ab0304f55cfcfde7b79615c3563c0db61ca099d335d640 |
| native/windows/icode_positive_loopback_config.inc | 194a6902cb828a71cac25c10b3bb66a1189355c888f7d51b724cc31c895de977 |
| native/windows/icode_wfp_event_probe.c | 1796d36ca0964d685a7d0aeedb8bbabd3d29a8eb7c209255310f1ee6769ad596 |
| 新SOURCE及TEST路径 | 两者不存在；不覆盖已有文件 |

| 资产=新文件完整输出 | LF行 | UTF-8字节 | raw SHA256 |
| --- | --- | --- | --- |
| A: tests/test_windows_positive_loopback_policy.py | 356 | 18847 | 49bf9718468002078cfc62eeccd877e3967a69c92b8b40fd9f2c15db3f9c2cf1 |
| B: src/icode/windows_positive_loopback_policy.py | 402 | 16686 | 0598a314200dd69258bd0e9c2db2d38eaecb5037580799890672047d26d0298c |

两资产均完整全文、末尾LF；围栏不计入hash。未来用apply_patch新增完整文件，每行加补丁前缀；不使用shell重定向写源码。正向为不存在→完整资产；逆向核去除本次新增文件后其它原文件raw不变，不授权执行删除/Git恢复。

## 4. TDD任务与依赖

### Task 1：正式TEST-only

**Dependencies:** None；**Parallelizable:** No（先正式RED与独立审查）。
- [x] 不同于未来SOURCE的作者，仅apply_patch新增Asset A。source/CI/旧TEST/DESIGN均不变。
- [x] 严格20方法应为19父Assertion（setUp明确新software core缺失）+发现机制1P，0ERROR/skip，exit1。不是19个旧产品bug；只为新设施缺失校准。若是ModuleNotFound/TypeError/loader ERROR，不计合格RED。
- [x] 保存完整日志、count/退出/耗时/hash，核资产及其余输入字节。fresh actualTEST SPEC→不同QUALITY后冻结TEST；不得SOURCE作者改TEST补绿。

### Task 2：正式SOURCE-only

**Dependencies:** Task1及其actual双审；**Parallelizable:** No（唯一SOURCE作者串行）。
- [x] 只apply_patch新增Asset B，不改Asset A/旧TEST/CI。无参数接入windows_appcontainer，无环境自动启用；不实现任何adapter/CLI/API/文件I/O。
- [x] 严格新20必须20P/0F/E/skip，旧相关15=预算3+协议12必须15P/0F/E/skip。AST/导入与全资产raw核对；其它代码/CI/native输入逐字不动。
- [x] selfSPEC→不同角度selfQUALITY/七维后停止；fresh actualSOURCE SPEC→不同QUALITY与全片双审由root安排。旧full/原生门原样保留，线上候选由root另行处理。本片通过不授后续两片或Windows原生通过。

精确命令均在WSL权威根/home/orbbec/projects/icode，使用既有DL2JQJ/bin/python（3.11.17）作纯软件TDD诊断，不装依赖或解释器，不跑full/native/网络/系统。以下两条固定定数、零skip命令不授产品3.11支持或实际3.12信用；正式执行仍须§1解冻，CI不添加这两步。

```bash
env PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_positive_loopback_policy.py'); assert s.countTestCases()==20, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
```

```bash
env PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.loadTestsFromNames(('tests.test_full_suite_ci_budget','tests.test_windows_runner_protocol')); assert s.countTestCases()==15, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
```

## 5. 覆盖与边界映射

| Asset A方法顺序 | 可证明的纯软件合同 | 不可声称 |
| --- | --- | --- |
| 1–2 | 每位admission exact bool、完整manifest/候选/身份/不等SID/窗口 | 不认证admin/GitHub、不实际Derive |
| 3–4 | 真实JSON编码/解析，exact键/type/关联、重复/NaN/UTF8/4096/截止 | 不认证文件ACL/发送进程/nonce秘密 |
| 5–7 | 规范SID二进制身份、完整Attributes、不重复、4096/4097、显式complete/released/reaped | 不读取或释放真实API内存 |
| 8–10 | 稳定双baseline、预有target拒绝、hr0创建、单轮phase、无intent不能清理 | 不创建profile/持久化intent/防旧对象重放 |
| 11–12 | 添加精确delta、foreign/Reviewer保留、失败/超时/不回收/晚结果 | 不执行CLI，不取得OS事实 |
| 13 | 原形双栈完整payload、nonce/token/Job/exit/截止模型 | 不连接listener/验证真实token |
| 14–17 | 当前map减owned、foreign差异保留并失败、属性冲突、absent幂等、首错/失败/晚清理 | 不删SID/回放旧快照、不证明原生恢复 |
| 18–19 | 真实≤500序列化、隐私、nativefalse/null、纯依赖/canonical类型 | 不输出Actions/产品准入 |
| 20 | 默认test*.py发现、旧full入口/argv、无mutation开关 | 不运行full，不能单靠静态断言证明业务 |

常量复用DESIGN的4096条/4096请求字节/500日志字节/60000ms；uint32 Attributes及SID规范化仅软件表示，不制造传OS的SID指针。后续仍用SDK验证原件。SID结构参考Microsoft官方SID文档（2026-10-15观察，页面2024-02-22）：https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-sid；不复制示例代码。
沿用root已记live的固定Codex27065a91 smoke正控/finally机制研究（Apache-2.0，仅机制，不是单SID豁免先例）；OpenHands3934349 completion先于cleanup不适配恢复信用。采纳显式前置、结果/恢复分账；暂缓执行器/重试/宿主，不适配posthook冒回滚。不引新依赖/许可不明拷贝，不重刷20名单。完整Get/Set/CLI非原子限制和同一SIDauthority沿用DESIGN，不重复或改写。

## 6. 实际匿名证据与自审

下表为原1ce基线上的作者RAM资产自校验，历史日志/耗时/hash保持原件，不重标为beb、e94或实际3.12结果；未写正式TEST/SOURCE/CI。本轮e94重绑定重新核对§3文件hash与A/B资产字节，不将旧RAM测试结果当当前候选执行证据。仅将新SOURCE的read_text精确映射到内存以供AST检查，测试函数及末结果不mock；原budget3/协议12真实执行。没有Windows API/CLI/网络。新设施RED不虚构旧产品bug。
初版曾含CI专门门/预算迁移投影；root进一步收敛后全部撤销，未曾落盘，不属本片资产或范围。最终A/B、严格20与原15均如下。早期nativefalse/null字段收紧、无owned intent负控和二次失败保首错均在冻结前补入，不减方法数或旧oracle。
“覆盖first_error”突变初次逃逸20P，暴露fixture只含一次错误；新增同方法的第二错误断言后最终该突变1Assertion。此历史保留，不冒覆盖完整。os206命令过长与一次PLAN字符串组装SyntaxError均未启动产品代码，属于工具/文档组装失败，绝不计TDD RED；最终短压缩RAM重放成功，无安全拒绝绕过或临时源码写入。

| 匿名场景 | count | F/E/skip | suite exit | 秒 | 完整日志SHA256 |
| --- | --- | --- | --- | --- | --- |
| test-only-red | 20 | 19/0/0 | 1 | 0.003179 | e4c861bf6d21a91ac4c5f134f39828ded3401648dbebb5f7e4e9a899a909b42d |
| core-only | 20 | 0/0/0 | 0 | 0.040094 | 940127eb67150a1525dd693ead5c8bfa696e50d7dd82c42a908c87334ad6ab03 |
| related-consumers | 35 | 0/0/0 | 0 | 0.047822 | 385c20555ff61bba5b542b0d98f1b5af7e66c8e3a6012baea9d3ef228ee509dc |
| mutant-native-authority | 20 | 1/0/0 | 1 | 0.039422 | 64afba5fcb6c9f18eb21c1892c42424417e07d5a376e94a3932b8acf1e65f275 |
| mutant-late-result | 20 | 1/0/0 | 1 | 0.046733 | ebb8e988376da16958c37801672f47c83d089d197367911219cbd7a0fc2249bc |
| mutant-lost-first-error | 20 | 1/0/0 | 1 | 0.040362 | ba47d0809d48a4887e008ff2a3d7489bf64e17202db2b529a55a3c3cba60a1f0 |

当前候选e94另账：root在e94f72004071188b1c69e838f6faa98bc58e9723、actual311亲自运行本文最后完整RAM重放器，receipt `9097ac`，不是本次PLAN编辑者的执行记录。以下为root交接的完整日志hash；本地3.11仅软件诊断，不是正式TDD、实际3.12或native信用。三突变各1 Assertion、0 ERROR/skip；未收到其各自hash与精确耗时，不补造或覆盖上表历史记录。

| root e94 RAM场景 | count | F/E/skip | suite exit | 完整日志SHA256 |
| --- | --- | --- | --- | --- |
| test-only-red | 20 | 19/0/0 | 1 | 7f3bd542e695878aa116fa0987009528d70cdf49489251a5fe0896fca6970df3 |
| core-only | 20 | 0/0/0 | 0 | 5e66f706f1df265aaf5b56d63439c2a3ce510f461371f0a944b339d1d96f95d6 |
| related-consumers | 35 | 0/0/0 | 0 | 4142cdedac3c6177c6f1b8a15e666a6b48858434231a20b9de5cb2456a367844 |

外层驱动exit0仅指预期全部符合，RED/mutant各自suite仍exit1。最终日志完整压缩留作者RAM wlpolicy_core_parsed.results[*].log_z；不承诺跨isolate可访问，后附完整重放器可由root独立重取。
selfSPEC：§1范围/硬依赖、§2未来实际消费界面、§3十二输入与两输出、§4严格阶段、§5每项模型/原生分账逐一核对，无未定义的实际可执行adapter。
selfQUALITY：反向核权限误授、无intent清理、属性覆盖、串单/重复、晚结果、二次失败首错及原生true伪造；三突变均Assertion，非ERROR。没有把软件对象当host authority，未改双0DESIGN。
【架构级自检报告】
语法/编译：完整A/B RAM compile/AST和unittest已过；无原生编译声称。
依赖/调用链：当前仅软件TEST消费；未来CI-only真实边界明确且硬阻断；旧协议12/预算3保持。
逻辑/边界：typed关联/完整映射/owned phase/固定payload/累计deadline/foreign保留覆盖。
异常处理：坏schema/type/UTF8/超限/晚结果/模型失败/清理冲突均拒绝或unknown保首错；不称系统异常已全实测。
关联模块：默认full发现保留，不加CI/旧TEST修改；真实正控旧输入不变。
兼容安全：无环境/I/O/adapter/产品入口，旧None路径原字节保持，无权限/依赖变化。
可运行性：匿名纯软件新20及相关35P；正式文件、线上、Windows原生均未实施，不称100%产品通过。

## Asset A

```python
"""Pure software loopback policy; no Windows APIs or mutation adapters."""
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
import importlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = "icode.windows_positive_loopback_policy"
try:
    core = importlib.import_module(MODULE)
except ModuleNotFoundError as exc:
    if exc.name != MODULE:
        raise
    core = None


def fields():
    return dict(admission=core.AdmissionFacts(True, True, True, True, True),
                repository="ayukyo/icode", source_sha="a" * 40, run_id="123",
                run_attempt=1, job="windows-reviewer-snapshot-probe", matrix="x64",
                account_sid="S-1-5-21-1-2-3-1001", pid=1234, process_created=5678,
                positive_profile="icode-" + "1" * 32,
                reviewer_profile="icode-" + "2" * 32,
                positive_sid="S-1-15-2-1-2-3-4-5-6-7",
                reviewer_sid="S-1-15-2-8-9-10-11-12-13-14",
                nonce="3" * 32, ipv4_port=12345, ipv6_port=23456,
                started_ms=1000, deadline_ms=61000)



def full_snapshot(entries, **options):
    # Explicit complete model facts; these are not OS observations.
    return core.Snapshot(entries, **{
        **dict(api_code=0, complete=True, released=True, reaped=True), **options})


class TestPositiveLoopbackPolicy(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(core, "new software policy core is absent; not an OS bug")
        self.m = core.Manifest(**fields())
        self.foreign = ("S-1-15-2-99", 0x80000004)
        self.b = full_snapshot((self.foreign,))
        self.a = full_snapshot((self.foreign, (self.m.positive_sid, 4)))
        self.ok = core.CommandResult(0, False, True)

    def begin(self):
        return core.begin(self.m, self.b, self.b, 1000)

    def intent(self):
        state = core.profile_created(self.begin(), self.m.positive_profile,
                                     self.m.positive_sid, 0, 1001)
        return core.add_intent(state, 1002)

    def added(self):
        return core.add_observed(self.intent(), self.a, self.ok, 1003)

    def successful(self):
        payload = json.dumps(dict(nonce=self.m.nonce, appcontainer=True,
            package_sid=self.m.positive_sid, capability_count=1,
            capability_sid="S-1-15-3-3"), sort_keys=True,
            separators=(",", ":")).encode("ascii")
        state = core.probe_observed(self.added(), (payload,), (payload,),
                                    True, True, 0, 1004)
        plan = core.cleanup_plan(state, self.a, True, 1005)
        self.assertEqual(plan.action, "delete")
        return core.cleanup_complete(plan, self.b, self.ok, 1006)

    def test_manifest_complete_binding_and_immutability(self):
        self.assertEqual(self.m.source_sha, "a" * 40)
        for index in range(5):
            for invalid in (False, 1, None):
                flags = [True] * 5
                flags[index] = invalid
                with self.subTest(index=index, value=invalid), self.assertRaises(core.PolicyError):
                    core.AdmissionFacts(*flags)
        with self.assertRaises(FrozenInstanceError):
            self.m.pid = 1
        for key in fields():
            changed = fields()
            changed[key] = None
            with self.subTest(key=key), self.assertRaises(core.PolicyError):
                core.Manifest(**changed)

    def test_manifest_rejects_cross_identity_and_invalid_scalars(self):
        cases = (("positive_sid", self.m.reviewer_sid),
                 ("positive_profile", self.m.reviewer_profile),
                 ("run_attempt", True), ("pid", False), ("process_created", -1),
                 ("ipv4_port", True), ("ipv6_port", 65536),
                 ("source_sha", "A" * 40), ("nonce", "x" * 32),
                 ("matrix", "arm"), ("deadline_ms", 61001),
                 ("started_ms", 61000), ("repository", "../other"))
        for key, value in cases:
            with self.subTest(key=key), self.assertRaises(core.PolicyError):
                core.Manifest(**dict(fields(), **{key: value}))

    def test_request_real_roundtrip_and_exact_correlation(self):
        wire = core.encode_request(self.m, "profile_created")
        self.assertLessEqual(len(wire), 4096)
        self.assertEqual(core.validate_request(wire, self.m, "profile_created", 1001),
                         "profile_created")
        body = json.loads(wire)
        for key in body:
            other = dict(body)
            other[key] = None
            with self.subTest(key=key), self.assertRaises(core.PolicyError):
                core.validate_request(json.dumps(other).encode(), self.m,
                                      "profile_created", 1001)
        for kind in ("probe_finished", "arbitrary_command"):
            with self.assertRaises(core.PolicyError):
                core.validate_request(wire, self.m, kind, 1001)

    def test_request_duplicates_limits_types_utf8_and_deadline(self):
        wire = core.encode_request(self.m, "probe_finished")
        for bad in (wire[:-1] + b',"version":1}', b"[]", b"\xff",
                    b" " * 4097, b'{"version":NaN}', wire + b"{}"):
            with self.subTest(bad=bad[:30]), self.assertRaises(core.PolicyError):
                core.validate_request(bad, self.m, "probe_finished", 1001)
        body = json.loads(wire)
        body["pid"] = True
        with self.assertRaises(core.PolicyError):
            core.validate_request(json.dumps(body).encode(), self.m,
                                  "probe_finished", 1001)
        for now in (True, 999, 61000, 61001):
            with self.assertRaises(core.PolicyError):
                core.validate_request(wire, self.m, "probe_finished", now)

    def test_snapshot_binary_identity_attributes_and_order(self):
        other = ("S-1-5-18", 0xFFFFFFFF)
        left = full_snapshot((self.foreign, other))
        right = full_snapshot((other, self.foreign))
        self.assertEqual(left, right)
        self.assertEqual(left.digest, right.digest)
        self.assertNotEqual(left, full_snapshot((other, (self.foreign[0], 0))))
        self.assertEqual(core.sid_bytes("S-1-5-18"),
                         b"\x01\x01\x00\x00\x00\x00\x00\x05\x12\x00\x00\x00")

    def test_snapshot_invalid_sids_duplicates_and_attribute_types(self):
        cases = ((("S-1-15-2-01", 0),), (("S-2-5-18", 0),),
                 (("S-1-281474976710656-1", 0),), (("S-1-5-4294967296", 0),),
                 (("S-1-5", 0),), ((self.foreign[0], True),),
                 ((self.foreign[0], -1),), ((self.foreign[0], 1 << 32),),
                 (self.foreign, self.foreign), [self.foreign],
                 ((self.foreign[0], 0, 1),))
        for entries in cases:
            with self.subTest(entries=entries), self.assertRaises(core.PolicyError):
                full_snapshot(entries)

    def test_snapshot_complete_limit_and_api_release_reap_are_required(self):
        entries = tuple((f"S-1-15-2-{i}", i) for i in range(4096))
        self.assertEqual(len(full_snapshot(entries).entries), 4096)
        with self.assertRaises(core.PolicyError):
            full_snapshot(entries + (("S-1-15-2-5000", 0),))
        for options in (dict(api_code=5), dict(api_code=False),
                        dict(complete=False), dict(released=False),
                        dict(reaped=False), dict(complete=1)):
            with self.subTest(options=options), self.assertRaises(core.PolicyError):
                full_snapshot((self.foreign,), **options)

    def test_begin_requires_stable_absent_two_target_snapshot(self):
        self.assertEqual(self.begin().phase, "baseline")
        for other in (self.a, full_snapshot((self.foreign, (self.m.reviewer_sid, 0))),
                      full_snapshot(())):
            with self.subTest(other=other), self.assertRaises(core.PolicyError):
                core.begin(self.m, other, other if other == self.a else self.b, 1000)
        with self.assertRaises(core.PolicyError):
            core.begin(self.m, self.b, self.b, 61000)

    def test_profile_creation_requires_exact_owned_success(self):
        for args in ((self.m.reviewer_profile, self.m.positive_sid, 0),
                     (self.m.positive_profile, self.m.reviewer_sid, 0),
                     (self.m.positive_profile, self.m.positive_sid, 1),
                     (self.m.positive_profile, self.m.positive_sid, False)):
            with self.subTest(args=args), self.assertRaises(core.PolicyError):
                core.profile_created(self.begin(), *args, 1001)
        with self.assertRaises(core.PolicyError):
            core.add_intent(self.begin(), 1001)

    def test_intent_one_shot_and_deadline_cannot_be_replayed(self):
        intent = self.intent()
        self.assertEqual(intent.phase, "add_intent")
        with self.assertRaises(core.PolicyError):
            core.add_intent(intent, 1003)
        with self.assertRaises(core.PolicyError):
            core.profile_created(intent, self.m.positive_profile,
                                 self.m.positive_sid, 0, 1003)
        with self.assertRaises(core.PolicyError):
            core.add_intent(core.profile_created(self.begin(), self.m.positive_profile,
                            self.m.positive_sid, 0, 1001), 61000)
        with self.assertRaises(core.PolicyError):
            core.cleanup_plan(self.begin(), self.b, True, 1002)
        with self.assertRaises(core.PolicyError):
            core.cleanup_plan(core.fail(self.begin(), "observation_failed"),
                              self.a, True, 1003)

    def test_add_exact_delta_no_foreign_or_reviewer_change(self):
        state = self.added()
        self.assertEqual((state.phase, state.target_attributes), ("added", 4))
        for snapshot in (self.b, full_snapshot(((self.foreign[0], 0),
                             (self.m.positive_sid, 4))),
                         full_snapshot(self.a.entries + ((self.m.reviewer_sid, 0),))):
            result = core.add_observed(self.intent(), snapshot, self.ok, 1003)
            self.assertEqual(result.phase, "unknown")
            self.assertIsNotNone(result.first_error)

    def test_add_error_timeout_late_and_unreaped_do_not_grant_success(self):
        for command in (core.CommandResult(5, False, True),
                        core.CommandResult(None, True, True),
                        core.CommandResult(None, True, False)):
            state = core.add_observed(self.intent(), self.a, command, 1003)
            self.assertEqual(state.phase, "unknown")
            self.assertEqual(state.target_attributes, 4)
        late = core.add_observed(self.intent(), self.a, self.ok, 61000)
        self.assertEqual((late.phase, late.first_error), ("unknown", "deadline"))
        for args in ((False, False, True), (0, 0, True), (None, False, True)):
            with self.assertRaises(core.PolicyError):
                core.CommandResult(*args)

    def test_probe_requires_actual_complete_dual_payload_and_verified_token(self):
        payload = core.probe_payload(self.m)
        for args in (((payload,), (), True, True, 0),
                     ((payload, payload), (payload,), True, True, 0),
                     ((b"wrong",), (payload,), True, True, 0),
                     ((payload,), (payload,), False, True, 0),
                     ((payload,), (payload,), True, False, 0),
                     ((payload,), (payload,), True, True, 105)):
            state = core.probe_observed(self.added(), *args, 1004)
            self.assertEqual(state.phase, "unknown")
            self.assertFalse(state.both_nonce_received)
        self.assertEqual(self.successful().phase, "restored")
        late = core.probe_observed(self.added(), (payload,), (payload,),
                                   True, True, 0, 61000)
        self.assertEqual((late.phase, late.first_error), ("unknown", "deadline"))

    def test_cleanup_current_map_preserves_foreign_deltas_without_rollback(self):
        foreign_delta = ("S-1-5-19", 128)
        changed = full_snapshot(self.a.entries + (foreign_delta,))
        plan = core.cleanup_plan(self.added(), changed, True, 1005)
        self.assertEqual(plan.action, "delete")
        post = full_snapshot(self.b.entries + (foreign_delta,))
        result = core.cleanup_complete(plan, post, self.ok, 1006)
        self.assertTrue(result.modeled_restoration)
        self.assertEqual(result.first_error, "foreign_delta")
        receipt = json.loads(core.encode_receipt(result, 1007))
        self.assertEqual(receipt["status"], "unknown")

    def test_cleanup_absence_is_idempotent_and_ambiguous_owner_refuses(self):
        absent = core.cleanup_plan(self.added(), self.b, True, 1005)
        self.assertEqual(absent.action, "absent")
        done = core.cleanup_complete(absent, self.b, None, 1006)
        self.assertTrue(done.modeled_restoration)
        for current, reaped in ((full_snapshot((self.foreign,
                             (self.m.positive_sid, 8))), True), (self.a, False)):
            plan = core.cleanup_plan(self.added(), current, reaped, 1005)
            self.assertEqual(plan.action, "refuse")
            result = core.cleanup_complete(plan, self.b, self.ok, 1006)
            self.assertFalse(result.modeled_restoration)

    def test_cleanup_unknown_add_intent_and_error_keep_first_result(self):
        failed = core.fail(self.intent(), "add_failed")
        repeated = core.fail(failed, "cleanup_failed")
        self.assertEqual(repeated.first_error, "add_failed")
        plan = core.cleanup_plan(failed, self.a, True, 1005)
        self.assertEqual(plan.action, "delete")
        done = core.cleanup_complete(plan, self.b, self.ok, 1006)
        self.assertEqual(done.first_error, "add_failed")
        self.assertTrue(done.modeled_restoration)
        self.assertEqual(json.loads(core.encode_receipt(done, 1007))["status"], "unknown")
        with self.assertRaises(core.PolicyError):
            core.fail(self.intent(), "arbitrary stage/private contents")

    def test_cleanup_failure_or_bad_post_never_claims_restore(self):
        plan = core.cleanup_plan(self.added(), self.a, True, 1005)
        for post, command in ((self.a, self.ok),
                              (full_snapshot(()), self.ok),
                              (self.b, core.CommandResult(5, False, True)),
                              (self.b, core.CommandResult(None, True, False))):
            done = core.cleanup_complete(plan, post, command, 1006)
            self.assertFalse(done.modeled_restoration)
            self.assertEqual(json.loads(core.encode_receipt(done, 1007))["status"],
                             "unknown")
        late_plan = core.cleanup_plan(self.added(), self.a, True, 61000)
        late = core.cleanup_complete(late_plan, self.b, self.ok, 61001)
        self.assertTrue(late.modeled_restoration)
        self.assertEqual(late.first_error, "deadline")
        self.assertEqual(json.loads(core.encode_receipt(late, 61002))["status"], "unknown")
        with self.assertRaises(core.PolicyError):
            core.cleanup_plan(self.successful(), self.b, True, 1008)

    def test_receipt_budget_privacy_native_false_and_late_result(self):
        done = self.successful()
        for state, now, status in ((done, 1007, "modeled"),
                                  (done, 61000, "unknown"),
                                  (self.intent(), 1007, "unknown")):
            wire = core.encode_receipt(state, now)
            self.assertLessEqual(len(wire), 500)
            receipt = json.loads(wire)
            self.assertEqual(receipt["status"], status)
            self.assertIs(receipt["native_authorized"], False)
            self.assertIsNone(receipt["native_restoration_verified"])
            self.assertNotIn(self.m.positive_sid.encode(), wire)
            self.assertNotIn(self.foreign[0].encode(), wire)
            self.assertEqual(wire, json.dumps(receipt, sort_keys=True,
                separators=(",", ":"), ensure_ascii=True).encode("ascii"))

    def test_core_is_pure_and_canonical_types_are_not_duck_typed(self):
        tree = ast.parse(Path(core.__file__).read_text(encoding="utf-8"))
        forbidden = {"os", "sys", "ctypes", "subprocess", "socket", "pathlib", "time"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse({item.name.split(".")[0] for item in node.names}
                                 & forbidden)
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)
        class ForeignManifest:
            pass
        for bad in (ForeignManifest(), dict(fields())):
            with self.assertRaises(core.PolicyError):
                core.begin(bad, self.b, self.b, 1000)
        with self.assertRaises(core.PolicyError):
            core.begin(self.m, self.b.entries, self.b, 1000)
        self.assertEqual(replace(self.m, matrix="ARM64").matrix, "ARM64")


class TestPositiveLoopbackPolicyDiscovery(unittest.TestCase):
    def test_existing_default_discovery_without_native_activation(self):
        import fnmatch
        self.assertTrue(fnmatch.fnmatch(Path(__file__).name, "test*.py"))
        business = unittest.defaultTestLoader.loadTestsFromTestCase(TestPositiveLoopbackPolicy)
        own = unittest.defaultTestLoader.loadTestsFromTestCase(type(self))
        self.assertEqual((business.countTestCases(), own.countTestCases()), (19, 1))
        text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        test_job = text.split("\n  test:\n", 1)[1].split(
            "\n  packaged-skill-install:\n", 1)[0]
        self.assertEqual(test_job.count(
            "        run: python -u scripts/run_full_suite_ci.py\n"), 1)
        runner = (ROOT / "scripts/run_full_suite_ci.py").read_text(encoding="utf-8")
        tree = ast.parse(runner)
        argv = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Attribute) and target.attr == "argv"
                        for target in node.targets)
                and isinstance(node.value, ast.List)]
        self.assertEqual([ast.literal_eval(node.value) for node in argv], [["unittest", "-v"]])
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "run_module"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(ast.literal_eval(calls[0].args[0]), "unittest")
        self.assertNotIn("ICODE_DIAGNOSTIC_POSITIVE_LOOPBACK_EXEMPTION:", text)
        self.assertNotIn("CheckNetIsolation.exe LoopbackExempt -a", text)


if __name__ == "__main__":
    unittest.main()
```

## Asset B

```python
"""CI positive-loopback software policy only: no OS authorization or restoration.

Inputs are caller assertions, not authenticated OS evidence. No result from this
module permits mutation. The future admin adapter must authenticate context,
persist intents, observe actual operations and independently verify restoration.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re
import struct

MAX_ENTRIES = 4096
MAX_REQUEST_BYTES = 4096
MAX_RECEIPT_BYTES = 500
WINDOW_MS = 60000
UINT32_MAX = (1 << 32) - 1
_ERRORS = frozenset({"add_failed", "deadline", "add_delta", "probe_failed",
                     "foreign_delta", "owner_conflict", "unreaped",
                     "cleanup_failed", "observation_failed"})
_PHASES = frozenset({"baseline", "created", "add_intent", "added", "probe",
                     "cleanup", "restored", "unknown"})


class PolicyError(ValueError):
    """Invalid software policy input; never a Windows DENY observation."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise PolicyError(code)


def _uint(value: object, maximum: int = UINT32_MAX, minimum: int = 0) -> bool:
    return type(value) is int and minimum <= value <= maximum


def sid_bytes(text: str) -> bytes:
    """Validate canonical decimal SID text and return Windows binary SID bytes."""
    _require(type(text) is str and len(text) <= 184, "invalid_sid")
    parts = text.split("-")
    _require(len(parts) >= 4 and parts[:2] == ["S", "1"]
             and len(parts) <= 18, "invalid_sid")
    _require(all(re.fullmatch(r"0|[1-9][0-9]*", part) for part in parts[2:]),
             "invalid_sid")
    values = [int(part) for part in parts[2:]]
    _require(values[0] < (1 << 48)
             and all(value <= UINT32_MAX for value in values[1:]), "invalid_sid")
    return bytes((1, len(values) - 1)) + values[0].to_bytes(6, "big") + b"".join(
        struct.pack("<I", value) for value in values[1:])


@dataclass(frozen=True)
class AdmissionFacts:
    """Caller assertions only, not proof of GitHub identity or administrator rights."""
    github_actions: bool
    windows: bool
    github_hosted: bool
    explicitly_authorized: bool
    dedicated_runner: bool

    def __post_init__(self):
        _require(all(type(value) is bool and value for value in (
            self.github_actions, self.windows, self.github_hosted,
            self.explicitly_authorized, self.dedicated_runner)), "admission")


@dataclass(frozen=True)
class Manifest:
    admission: AdmissionFacts
    repository: str
    source_sha: str
    run_id: str
    run_attempt: int
    job: str
    matrix: str
    account_sid: str
    pid: int
    process_created: int
    positive_profile: str
    reviewer_profile: str
    positive_sid: str
    reviewer_sid: str
    nonce: str
    ipv4_port: int
    ipv6_port: int
    started_ms: int
    deadline_ms: int

    def __post_init__(self):
        _require(type(self.admission) is AdmissionFacts, "admission_type")
        _require(self.repository == "ayukyo/icode"
                 and type(self.repository) is str, "repository")
        for value, pattern in ((self.source_sha, r"[0-9a-f]{40}"),
                               (self.run_id, r"[1-9][0-9]{0,19}"),
                               (self.nonce, r"[0-9a-f]{32}"),
                               (self.positive_profile, r"icode-[0-9a-f]{32}"),
                               (self.reviewer_profile, r"icode-[0-9a-f]{32}")):
            _require(type(value) is str and re.fullmatch(pattern, value) is not None,
                     "manifest_text")
        _require(type(self.job) is str and self.job == "windows-reviewer-snapshot-probe"
                 and type(self.matrix) is str and self.matrix in ("x64", "ARM64"),
                 "job_identity")
        for value in (self.account_sid, self.positive_sid, self.reviewer_sid):
            sid_bytes(value)
        _require(self.account_sid.startswith("S-1-5-21-")
                 and self.positive_sid.startswith("S-1-15-2-")
                 and self.reviewer_sid.startswith("S-1-15-2-")
                 and self.positive_sid != self.reviewer_sid
                 and self.positive_profile != self.reviewer_profile, "profile_identity")
        _require(_uint(self.run_attempt, minimum=1) and _uint(self.pid, minimum=1)
                 and _uint(self.process_created, (1 << 64) - 1, 1), "process_identity")
        _require(_uint(self.ipv4_port, 65535, 1)
                 and _uint(self.ipv6_port, 65535, 1), "endpoint")
        _require(_uint(self.started_ms, (1 << 63) - 1)
                 and _uint(self.deadline_ms, (1 << 63) - 1)
                 and 0 < self.deadline_ms - self.started_ms <= WINDOW_MS, "window")

    @property
    def digest(self) -> str:
        return hashlib.sha256(_json(asdict(self))).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _clock(manifest: Manifest, now_ms: int) -> bool:
    _require(type(manifest) is Manifest, "manifest_type")
    _require(_uint(now_ms, (1 << 63) - 1) and now_ms >= manifest.started_ms, "clock")
    return now_ms < manifest.deadline_ms


def _live(manifest: Manifest, now_ms: int) -> None:
    _require(_clock(manifest, now_ms), "deadline")


def _request(manifest: Manifest, kind: str) -> dict:
    _require(type(manifest) is Manifest, "manifest_type")
    _require(type(kind) is str and kind in ("profile_created", "probe_finished"), "kind")
    return dict(version=1, kind=kind, binding=manifest.digest,
                positive_profile=manifest.positive_profile,
                positive_sid=manifest.positive_sid, reviewer_sid=manifest.reviewer_sid,
                nonce=manifest.nonce, ipv4_port=manifest.ipv4_port,
                ipv6_port=manifest.ipv6_port, pid=manifest.pid,
                process_created=manifest.process_created)


def encode_request(manifest: Manifest, kind: str) -> bytes:
    wire = _json(_request(manifest, kind))
    _require(len(wire) <= MAX_REQUEST_BYTES, "request_size")
    return wire


def _unique(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate_key")
        value[key] = item
    return value


def validate_request(wire: bytes, manifest: Manifest, kind: str, now_ms: int) -> str:
    """Correlation only: this does not authenticate the sender or filesystem."""
    _live(manifest, now_ms)
    _require(type(wire) is bytes and 0 < len(wire) <= MAX_REQUEST_BYTES, "request_size")
    expected = _request(manifest, kind)
    try:
        body = json.loads(wire.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              PolicyError("json_constant")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PolicyError("request_json") from exc
    _require(type(body) is dict and set(body) == set(expected), "request_fields")
    _require(all(type(body[key]) is type(value) and body[key] == value
                 for key, value in expected.items()), "request_binding")
    return kind


@dataclass(frozen=True)
class Snapshot:
    entries: tuple[tuple[str, int], ...]
    api_code: int
    complete: bool
    released: bool
    reaped: bool

    def __post_init__(self):
        _require(type(self.entries) is tuple and len(self.entries) <= MAX_ENTRIES,
                 "snapshot_entries")
        _require(type(self.api_code) is int and self.api_code == 0
                 and all(type(flag) is bool and flag
                         for flag in (self.complete, self.released, self.reaped)),
                 "snapshot_unverified")
        binary = set()
        for entry in self.entries:
            _require(type(entry) is tuple and len(entry) == 2, "snapshot_entry")
            sid, attributes = entry
            value = sid_bytes(sid)
            _require(value not in binary and _uint(attributes), "snapshot_identity")
            binary.add(value)
        object.__setattr__(self, "entries", tuple(sorted(
            self.entries, key=lambda entry: sid_bytes(entry[0]))))

    @property
    def digest(self) -> str:
        return hashlib.sha256(_json(self.entries)).hexdigest()


@dataclass(frozen=True)
class CommandResult:
    exit_code: int | None
    timed_out: bool
    reaped: bool

    def __post_init__(self):
        _require((self.exit_code is None or _uint(self.exit_code))
                 and type(self.timed_out) is bool and type(self.reaped) is bool
                 and (self.exit_code is not None or self.timed_out), "command_result")

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.reaped


@dataclass(frozen=True)
class State:
    manifest: Manifest
    baseline: Snapshot
    phase: str
    target_attributes: int | None = None
    both_nonce_received: bool = False
    first_error: str | None = None
    modeled_restoration: bool = False
    owned_intent: bool = False

    def __post_init__(self):
        _require(type(self.manifest) is Manifest and type(self.baseline) is Snapshot
                 and type(self.phase) is str and self.phase in _PHASES, "state")
        _require(self.target_attributes is None or _uint(self.target_attributes), "state_attr")
        _require(type(self.both_nonce_received) is bool
                 and type(self.modeled_restoration) is bool
                 and (self.first_error is None or (type(self.first_error) is str
                      and self.first_error in _ERRORS))
                 and type(self.owned_intent) is bool, "state_flags")
        _require(self.manifest.positive_sid not in dict(self.baseline.entries)
                 and self.manifest.reviewer_sid not in dict(self.baseline.entries), "state_baseline")
        _require((self.phase not in ("baseline", "created") or not self.owned_intent)
                 and (self.phase not in ("add_intent", "added", "probe", "cleanup", "restored")
                      or self.owned_intent)
                 and (not self.modeled_restoration or self.phase == "restored"), "state_ownership")


def _state(state: State, phases: tuple[str, ...]) -> None:
    _require(type(state) is State and state.phase in phases, "phase")


def _map(snapshot: Snapshot) -> dict:
    _require(type(snapshot) is Snapshot, "snapshot_type")
    return dict(snapshot.entries)


def begin(manifest: Manifest, first: Snapshot, second: Snapshot, now_ms: int) -> State:
    _live(manifest, now_ms)
    before, after = _map(first), _map(second)
    _require(before == after and manifest.positive_sid not in before
             and manifest.reviewer_sid not in before, "baseline")
    return State(manifest, first, "baseline")


def profile_created(state: State, profile: str, sid: str,
                    hresult: int, now_ms: int) -> State:
    _state(state, ("baseline",))
    _live(state.manifest, now_ms)
    _require(type(profile) is str and profile == state.manifest.positive_profile
             and type(sid) is str and sid == state.manifest.positive_sid
             and type(hresult) is int and hresult == 0, "creation")
    return replace(state, phase="created")


def add_intent(state: State, now_ms: int) -> State:
    """In-memory intent only; future adapter must durably persist before add."""
    _state(state, ("created",))
    _live(state.manifest, now_ms)
    return replace(state, phase="add_intent", owned_intent=True)


def fail(state: State, error: str) -> State:
    _require(type(state) is State and type(error) is str and error in _ERRORS, "error")
    return replace(state, phase="unknown", first_error=state.first_error or error,
                   modeled_restoration=False)


def add_observed(state: State, snapshot: Snapshot,
                 command: CommandResult, now_ms: int) -> State:
    _state(state, ("add_intent",))
    _require(type(command) is CommandResult, "command_type")
    current = _map(snapshot)
    sid = state.manifest.positive_sid
    target = current.pop(sid, None)
    result = replace(state, target_attributes=target)
    if not _clock(state.manifest, now_ms):
        return fail(result, "deadline")
    if not command.ok:
        return fail(result, "add_failed")
    if target is None or current != _map(state.baseline):
        return fail(result, "add_delta")
    return replace(result, phase="added")


def probe_payload(manifest: Manifest) -> bytes:
    _require(type(manifest) is Manifest, "manifest_type")
    return _json(dict(nonce=manifest.nonce, appcontainer=True,
                      package_sid=manifest.positive_sid, capability_count=1,
                      capability_sid="S-1-15-3-3"))


def probe_observed(state: State, ipv4: tuple[bytes, ...], ipv6: tuple[bytes, ...],
                   token_verified: bool, job_reaped: bool, exit_code: int,
                   now_ms: int) -> State:
    _state(state, ("added",))
    _require(type(ipv4) is tuple and type(ipv6) is tuple
             and all(type(value) is bytes for value in (*ipv4, *ipv6))
             and type(token_verified) is bool and type(job_reaped) is bool
             and _uint(exit_code), "probe_type")
    if not _clock(state.manifest, now_ms):
        return fail(state, "deadline")
    expected = (probe_payload(state.manifest),)
    if not (ipv4 == ipv6 == expected and token_verified and job_reaped and exit_code == 0):
        return fail(state, "probe_failed")
    return replace(state, phase="probe", both_nonce_received=True)


@dataclass(frozen=True)
class CleanupPlan:
    state: State
    before: Snapshot
    action: str

    def __post_init__(self):
        _require(type(self.state) is State and self.state.phase == "cleanup"
                 and type(self.before) is Snapshot
                 and type(self.action) is str
                 and self.action in ("delete", "absent", "refuse"), "cleanup_plan")


def cleanup_plan(state: State, current: Snapshot, last_command_reaped: bool,
                 now_ms: int) -> CleanupPlan:
    """Model a narrow cleanup decision, never an executable deletion grant."""
    _state(state, ("add_intent", "added", "probe", "unknown"))
    _require(state.owned_intent, "no_owned_intent")
    _require(type(last_command_reaped) is bool, "reaped_type")
    if not _clock(state.manifest, now_ms):
        state = fail(state, "deadline")
    observed = _map(current)
    target = observed.pop(state.manifest.positive_sid, None)
    if observed != _map(state.baseline):
        state = fail(state, "foreign_delta")
    if not last_command_reaped:
        state, action = fail(state, "unreaped"), "refuse"
    elif target is None:
        action = "absent"
    elif state.target_attributes is not None and target != state.target_attributes:
        state, action = fail(state, "owner_conflict"), "refuse"
    else:
        action = "delete"
    return CleanupPlan(replace(state, phase="cleanup"), current, action)


def cleanup_complete(plan: CleanupPlan, post: Snapshot,
                     command: CommandResult | None, now_ms: int) -> State:
    _require(type(plan) is CleanupPlan, "cleanup_type")
    state = plan.state
    if not _clock(state.manifest, now_ms):
        state = fail(state, "deadline")
    expected = _map(plan.before)
    expected.pop(state.manifest.positive_sid, None)
    actual = _map(post)
    command_ok = ((plan.action == "absent" and command is None)
                  or (plan.action == "delete" and type(command) is CommandResult
                      and command.ok))
    if plan.action == "refuse" or not command_ok or actual != expected:
        return fail(state, "cleanup_failed")
    return replace(state, phase="restored", modeled_restoration=True)


def encode_receipt(state: State, now_ms: int) -> bytes:
    """Export only model outcomes. Native authority is false; restoration null."""
    _require(type(state) is State, "state_type")
    live = _clock(state.manifest, now_ms)
    passed = (live and state.phase == "restored" and state.modeled_restoration
              and state.both_nonce_received and state.first_error is None)
    wire = _json(dict(schema_version=1, scope="positive_loopback_software_policy",
                      binding=state.manifest.digest, status="modeled" if passed else "unknown",
                      modeled_restoration=state.modeled_restoration,
                      native_authorized=False, native_restoration_verified=None,
                      first_error=state.first_error or (None if live else "deadline")))
    _require(len(wire) <= MAX_RECEIPT_BYTES, "receipt_size")
    return wire
```

## 7. 完整仅RAM重放器

下列代码可在已有WSL解释器通过stdin执行，仅读本文/原旧文件；不落临时源码。内存注册的是本次canonical模块名称，非跨module class alias或产品singleton。它运行严格20、相关35和三突变并保留完整log_z、每suite真实exit/hash。仅适于实际SOURCE落盘之前的新进程；实际实施后使用§4正式命令，不冒重放旧RED。

```python
import sys,types,unittest,io,time,json,hashlib,zlib,base64,pathlib
from unittest.mock import patch
ROOT=pathlib.Path("/home/orbbec/projects/icode")
sys.path[:0]=[str(ROOT/"src"),str(ROOT)]
plan=(ROOT/"docs/nbl/plans/2026-10-15-windows-ci-positive-loopback-exemption.md").read_text(encoding="utf-8")
def asset(name):
    marker="## Asset "+name+"\n\n"+chr(96)*3+"python\n"
    assert plan.count(marker)==1,name
    return plan.split(marker,1)[1].split("\n"+chr(96)*3+"\n",1)[0]+"\n"
assets={"source":asset("B"),"test":asset("A")}
source,test=assets["source"],assets["test"]
original_read=pathlib.Path.read_text
source_path=ROOT/"src/icode/windows_positive_loopback_policy.py"
results=[]
def run(label,source_text=None,old=False):
    sys.modules.pop("icode.windows_positive_loopback_policy",None)
    if source_text is not None:
        mod=types.ModuleType("icode.windows_positive_loopback_policy")
        mod.__file__=str(source_path)
        sys.modules[mod.__name__]=mod
        exec(compile(source_text,str(source_path),"exec"),mod.__dict__)
    module=types.ModuleType("tests._ram_positive_policy_"+label)
    module.__file__=str(ROOT/"tests/test_windows_positive_loopback_policy.py")
    exec(compile(test,module.__file__,"exec"),module.__dict__)
    suite=unittest.defaultTestLoader.loadTestsFromModule(module)
    assert suite.countTestCases()==20
    def read(path,*args,**kwargs):
        if path==source_path and source_text is not None:
            return source_text
        return original_read(path,*args,**kwargs)
    if old:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromNames((
            "tests.test_full_suite_ci_budget","tests.test_windows_runner_protocol")))
        assert suite.countTestCases()==35
    stream=io.StringIO(); start=time.monotonic()
    with patch.object(pathlib.Path,"read_text",read):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    log=stream.getvalue().encode()
    results.append(dict(label=label,count=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),
        seconds=time.monotonic()-start,exit=int(not result.wasSuccessful() or bool(result.skipped)),
        log_sha=hashlib.sha256(log).hexdigest(),
        log_z=base64.b64encode(zlib.compress(log)).decode()))
run("test-only-red")
run("core-only",source)
run("related-consumers",source,True)
for name,old,new in (
    ("native-authority","native_authorized=False","native_authorized=True"),
    ("late-result","live = _clock(state.manifest, now_ms)","live = True"),
    ("lost-first-error","first_error=state.first_error or error","first_error=error")):
    assert source.count(old)==1
    run("mutant-"+name,source.replace(old,new))
meta={name:dict(lines=text.count("\n"),bytes=len(text.encode()),
              sha=hashlib.sha256(text.encode()).hexdigest()) for name,text in assets.items()}
print(json.dumps(dict(meta=meta,results=results)))
assert results[0]["failures"]==19 and results[0]["errors"]==results[0]["skips"]==0
assert all(r["failures"]==r["errors"]==r["skips"]==0 for r in results[1:3])
assert all(r["failures"]>0 and r["errors"]==r["skips"]==0 for r in results[3:])
```

---
**Execution Mode:** serial。本轮PLAN-only覆盖技能自动实施/worktree/commit默认；停止待root全文与freshSPEC→不同QUALITY。后续实际TEST/SOURCE各需新授权。

执行后审结：actualSOURCE及GLOBAL fresh SPEC、不同fresh QUALITY均C0/I0/M0，二者分别亲跑同新20＋旧15合35P/0跳过。以上勾选只关闭本片软件实施/审查步骤，root正式解冻及执行事实见顶部；线上真实3.12、受保护admin组件、真实OSconsumer和完整R2/R3仍待，禁止将“模型restored”当系统恢复。
