# Windows WFP CAB 固定类别观察 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: nbl.executing-plans 串行实施。仅 root 全文读、fresh SPEC → 不同 QUALITY 全零后，独立 TEST 作者先正式 RED，再不同 SOURCE 作者，最后 root 单独 CI 接线与同 SHA 观察。当前 PLAN ONLY；本轮用户/root 的唯一文档、只读产品、main-only 和不自动实施约束覆盖技能默认另建 SPEC、worktree、频繁提交和自动执行。

**Goal:** 在现有 CAB 元数据枚举链中加入脱敏固定类别计数，知道当前两个成员分别属于哪些词法类别，不把成员观察当网络拒绝或文件格式证明。

**Architecture:** 复用真实 SetupIterateCabinetW 回调和真实 main JSON 序列化。默认 v3 回执保持；仅真实 capture 成员请求显式 opt-in v4，五项整数计数或失败 null。PowerShell 严格校验新字段后只在既有普通 group 日志增加一行，不修改 exact-wfpdiag 提取/parser 准入、Actions notice、capture/policy 或 Reviewer 结论。

**Tech Stack:** Python stdlib、既有 ctypes/SetupAPI 边界、现有 GitHub Actions PowerShell。无新依赖、管理员操作、原生构建或本机系统改动。

---

## 1. 输入、三问与决策

观察日 2026-10-15；权威工作区 /home/orbbec/projects/icode，编写基线 main ce4a53098938af6767e6c33f4a756fb566b1731d，vendor 仍 21566a589cbe98bd35372a04bbb6ca1c51d8eed2。root 当前两进度 docs 与 Mac macro 小修 dirty 保留；B3d ignored PLAN 是另一作者资产，不属于本片/下一小修候选。

真实问题：ce4 x64 Reviewer job116029773658 不是未启动 capture。原日志176520字符、1860行绑定 checkout SHA，capture_preflight=inactive，最终 CAB member_count=2/xml_member_count=1/wfpdiag-prefixed=0，exact target zero，extract_exit_code=not_run，capture_status=archive_member_missing。现报告不能区分该 XML 的词法类别或另一个成员的后缀。它们的原始名称/路径没有保留，本 PLAN 不猜名字。

已有实现：scripts/inspect_windows_cabinet_members.py 267行已经有 exact basename、XML 和 prefix 分类，SetupAPI 只 FILEOP_SKIP、不提取，并由真实 main 序列化；CI 严格唯一 exact wfpdiag.xml 才提取并运行 XML parser。本片复用这一条链，绝不新增旁支“模拟最终结果”。

影响链：回调 → 内存计数 → v4 JSON → 既有 CI receipt 校验 → 固定普通日志。默认 v3 synthetic CAB 正/负控、旧7方法、原 Actions notice 和 Reviewer first failure 不变。旧 WFP TEST24中仅实际 receipt schema 的一条断言从3迁4，synthetic v3断言继续保留。

root 已实际完成本轮 sequential-thinking 三步 7aaef7（需求/方案/风险）；作者工具目录无该 MCP，不能冒称自己调用。上轮只读调查已有根因边界，不重新刷全20项目。

三种方案：采纳仅类别计数，成本最低且不扩大数据披露；暂缓 XML schema/ETL 转换，因为未取得目标真实样本和稳定格式合同；不适配启审计、豁免、外部 peer、任意 XML fallback 来强行提供 DENY。

## 2. 同 SHA 因果边界

ce4 x64 Windows Server2025、runner2.337.0、image windows-2025-vs2026/20260925.250.1；实际 Reviewer 1方法51.558s、1FAILURE、0ERROR/skip。positive 105/ipv4_connect_timeout、candidate78，均不是 DENY。

普通标准用户自身 IPv6 WFP helper Subscribe2 code5/handle=false、history not_attempted，是权限不可用，不是0事件。管理员 runner observer 另为 ready/collection enabled/cleanup passed；其 candidate IPv6目标/时间窗 capability/classify history complete/returned0/matched0，不能解释不同 profile 的正控 IPv4 timeout。不得把两种身份或两个端点合并。

CI1332–1364 status/start，1904–1921 stop/archive/枚举；1975–2008 exact basename分支；2044–2068才调用 XML parser。实际已到可枚举 CAB、缺精确成员分支，故不是 archive_missing/extract_failed/parser no_match。start/stop 原输出默认 drain 到 Null，2086–2094清理，无此job artifact上传，当前无法重建成员原件。本片只为下一同SHA观察增加类别，不补写历史。

## 3. 不可变合同

- 不改 capture status/start/stop 参数、超时、恢复所有权、清理、运行身份或新的 native API。
- 不改原 exact matcher、target_match_count、XML/prefix计数或 missing/multiple/unique 分支。
- 不改 expand 的 -F:wfpdiag.xml、目标路径、唯一匹配、XML大小/parser准入；未知/state/ETL/other类别均不触发提取。
- 不新增 Set/启审计/LoopbackExempt/网络capability/peer/policy/topology/ETL转换/rawCAB上传。
- 不打印任意成员名、路径、XML/ETL正文、SID、私有stdout/stderr、凭据或临时URL。
- 原500字节序列化预算、新日志普通 bounded group、原Actions九槽/标题与消息字节保持；不截断原证明字段。
- 不改原 Reviewer candidate、positive profile、token/firstfailure、cleanup、timeout≠DENY、双10013/零cap等门。
- XML parser完整文件不变；它没有真实schema观察信用。合法非事件XML可能返回no_match，本片不喂它任意新XML、不借此假补绿。
- C2/宿主权限/跨平台认证/R2R3仍未授；分类观察不提供数据包drop原因。

## 4. v4 观察合同

默认 inspect_cabinet_members(archive) 与 main 无 opt-in 时保持原 v3字段/退出及 old7正控。新增 keyword-only observe_categories 和 CLI --observe-categories 只开启现有回调的附加计数。

五类别互斥，总数在成功时等 member_count：
1. target：复用原 is_target_cabinet_member 的精确 ASCII basename规则，不更改嵌套路径原合同；
2. state：非target、规范ASCII且无控制字符/长度超过4096时，仅 basename wfpstate.xml（不区分大小写）；
3. etl：同前提、basename以.etl结尾；仅后缀标签，不验证ETL格式；
4. other：其余有效ASCII名称，包括未知XML、wfpdiag_extra.xml；
5. unknown：None、空/非ASCII basename或非target名称超过4096/含非ASCII/控制字符。

类别不是路径安全/提取授权：原 exact target 规则优先且逐字不变，观察不把旧准入改宽或暗改窄。state whitelist来自官方 show state 的默认文件名字面，不证明本次CAB必有该成员，不宣称解析了state内容。

成功 v4保留原6个字段（schema_version改4）并附 member_categories={target,state,etl,other,unknown} 五个0..4096整数。任何 API、permission、member、budget、missing/archive/platform失败均附五个null；原status、退出码、member_count与原nullable字段继续原样。null不是完整零计数。

实际 CI 仅 opt-in真实 capture memberList请求。v4消费者额外要求 nested大小写精确五keys、整数而非bool/浮点/字符串、逐值0..4096、sum==member_count、target==原target_match_count；原top-level兼容行为/原数值关系仍保留。未知/坏schema不得把日志分类归零。

新普通日志 cab_categories=target:N,state:N,etl:N,other:N,unknown:N，默认 unavailable，只有全部receipt校验通过才赋值。固定标签+五个最多4位计数，不含名称/路径，Actions notice完全不加字段。原first-error、finally cleanup原样。

剩余盲点：other/unknown或一个state标签仍不告诉真实名字/格式/网络原因；需要更多信息另做有界设计。现没有真实目标event XML样本，不捆绑schema或ETL支持。

## 5. 主源和取舍

本轮只复用/实核Microsoft官方：
- [netsh wfp](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netsh-wfp)，页面2025-08-11：cab=on自动加.cab、traceonly=off包含诊断、stop finalize；不保证CAB必含wfpdiag.xml。show state默认wfpstate.xml仅是词法白名单依据。
- [Subscribe2](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmneteventsubscribe2)，2024-02-22：netevent container需要FWPM_ACTRL_SUBSCRIBE，不能拿标准用户code5当drop。
- [Enum3](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmneteventenum3)，2022-07-27：只枚举handle创建前已记录事件，小于请求页表示耗尽，不是所有未来流量证明。
- [Filter origin](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/filter-origin-documentation)：5157/5152、FilterOrigin/InterfaceIndex及管理员启审计是另一个明确授权的设计，不在此片执行。
Microsoft Learn为官方文档，本片不复制其实现或引入依赖；页面日期不是runner版本证明。

固定一个开源Agent：openai/codex 27065a91ccbf5ba8532844be3777fcf83b77820d，Apache-2.0；复用同日独立raw952adf/4ab3a9：registry.rs SHAfc37acd056a78779aeeff497d30bcbba759ea55f469ae2c9e7b8f37f3aeb2dae，701–725前置拒绝、790执行/819posthook/846结果拒绝不撤执行；[固定原件](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/tools/registry.rs)。不声称刷新HEAD或20名单，不复制代码。
采纳：前置准入、观察/结果分账、未知不归零；暂缓权限缓存/ETL/原生归因；不适配把posthook或分类成功等同事务回滚/网络DENY。收益是缩小归档盲点，成本仅现枚举的一次计数与有界字段，无新权限/新依赖。

## 6. 冻结输入与范围

本文自hash另报，避免自引用。输入任一漂移须停止核差异，不覆盖root并行小修或B3d PLAN。计划实现严格四路径：新增TEST、旧WFP TEST单断言迁移、CAB helper、CI；本轮实际只写本PLAN。

|输入|行数|SHA256|
|---|---:|---|
|scripts/inspect_windows_cabinet_members.py|267|b360f75133ce24358d55dc870d04db89b71ce5883992740048553f203087442c|
|tests/test_windows_wfp_capture.py|817|2c3e6e2690e02e563e4d4ccccec57521a938e42aee9a6be872d877dfc4e9a7b6|
|.github/workflows/ci.yml|2511|c331b43681964eae1d62543b15fe1c43d4f4c6bbab346a33c5184c2d573cb5ca|
|tests/test_windows_cabinet_members.py（不改）|224|155b723967f77b3dfcfb344d51290134cb34110b32209e7bb5bb1e0c7d67eab4|
|scripts/inspect_windows_wfp_capture.py（不改）|240|5cbe11167f15750a26e54d5b92676a7bc58f4bcecaf0bf82e7ae88a26a03dc52|
|tests/test_windows_appcontainer.py（不改）|9459|e5b421b994c5866a60ff72feff6db68f8e037151c6f6b59331ce4c900513c81d|

新 tests/test_windows_wfp_cab_observation.py 必须不存在。CI无paths过滤，四路径均触发原push；原jobs/矩阵/permissions/pins/timeouts/env/failfast/concurrency保留，无新job。双Linuxfull版本和双WindowsReviewer仅各增加同一严格10方法软件step，共两个模板位置；默认full discovery也自然包含新TEST，不额外运行full。

## 7. 串行任务

### Task1：独立TEST ONLY

**Dependencies:** root全文＋fresh SPEC→不同QUALITY全零。
**Parallelizable:** No（须正式RED先行）。

- [ ] 核HEAD/输入hash/新TEST不存在；仅apply_patch Asset A完整新TEST和Asset C旧TEST单断言迁移；不提前helper/CI。
- [ ] 正式strict10旧实现应10运行、9红父方法9Assertion记录、默认v3正控1绿、0ERROR/skip、exit1；真实callback/真实main序列化，功能不存在落到实际旧v3而不靠TypeError/loader RED。新kwargs不存在时测试只不加flag，仍要求v4观察断言RED。
- [ ] 旧7保持GREEN；迁移旧24在CI未落时允许且仅一条schema -eq4断言RED（其余23绿），记录这是CI接线未实施，不能吞或冒sourceRED。
- [ ] 留完整stdout/stderr/cwd/HEAD/hash/时间/exit，独立actual TEST双审清零，冻结两TEST。匿名预演不替正式RED。

### Task2：不同SOURCE作者

**Dependencies:** Task1正式RED＋独立actualTEST审全零。
**Parallelizable:** No（不得作者自审替不同审者）。

- [ ] 重新核输入，仅apply_patch Asset B到CAB helper；不改TEST、CI、原parser、Reviewer或native。
- [ ] 运行严格source8：排除明确两个CI-only方法后恰8方法、0failure/error/skip。此时strict10应source8绿＋CI2红；旧7绿，迁移旧24仍仅CI1红。分类失败/null、多target、4097超界及500预算均真实软件执行。
- [ ] 核B每hunk唯一匹配/正投影/inverse/AST/hash与默认v3兼容；作者selfSPEC→selfQUALITY，再freshactualSPEC→不同QUALITY。原old7/header/native不改。

### Task3：root实际CI接线及候选

**Dependencies:** Task2actualSOURCE双审全零，root当前候选所有线上job终态。
**Parallelizable:** No（root统一接线/发布）。

- [ ] root重新核当前CI输入；其它片已改CI时必须组合重审，不硬套本D。apply_patch Asset D，另freshactualCI SPEC→不同QUALITY。
- [ ] strict10、旧7、迁移旧24恰41软件方法全绿0skip；不本机full/native/系统调用。必要原notice3/old12预算回归另由root批准，不默认重复。
- [ ] 仅root安全检查/精确路径/主父/index/modes后main待验候选；本PLAN必须按明确scope单独审批纳入，不能提前混入当前Mac紧急小修。
- [ ] 同SHA双Windows观察新普通分类行及所有旧门。expected v4实时类别是什么只能原日志回答，不能预设state+ETL。exacttarget缺失仍archive_member_missing/extractnotrun；Reviewertimeout/candidate78仍fail，不授DENY。
- [ ] 若观察不足/分类other/unknown，诚实停止本片观察，不自动拓宽提取或启审计；后续schema/权限/peer另设计。保留失败、skip、unknown，不取消重跑掩盖。

## 8. 精确命令（实施阶段，不是本轮授权）

从WSL仓库根，用 /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B；PYTHONPATH=src。正式strict10：
~~~bash
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_wfp_cab_observation.py'); assert s.countTestCases()==10, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~
Task2仅source8：
~~~python
import unittest
from tests.test_windows_wfp_cab_observation import TestWfpCabObservation as C
excluded = {"test_workflow_observation_is_after_validation_and_does_not_expand_admission",
            "test_strict_count_and_existing_actions_notice_are_preserved"}
names = [name for name in unittest.defaultTestLoader.getTestCaseNames(C) if name not in excluded]
suite = unittest.TestSuite(C(name) for name in names)
assert suite.countTestCases() == 8
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful() or bool(result.skipped))
~~~
上述Python围栏通过解释器stdin执行，不写项目文件。旧7与旧24分别：
~~~bash
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_cabinet_members.py'); assert s.countTestCases()==7; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
/home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_wfp_capture.py'); assert s.countTestCases()==24; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~

## 9. 匿名预演、自SPEC及selfQUALITY

匿名RAM仅挂接模块源码与CI read_text，不落产品/TEST/CI；临时synthetic CAB文件由TemporaryDirectory清理。Fake SetupAPI只产生元数据回调并要求FILEOP_SKIP，没有调用真实WinDLL/SetupAPI、解包或Windows网络。ctypes.CFUNCTYPE代替软件调用约定不提供WinSDK ABI信用。

最终完整A冻结后实跑：旧10=9父红9Assertion＋1绿/0ERRORskip/.037s/strict exit1；投影10P/.047s、旧7P/.001s、迁移旧24P/.032s，全部0ERRORskip/exit0。测试保持真实分类/回调/序列化，不mock最终receipt。初次探索9方法、巨长assertIn源输出已淘汰，最终固定消息不输出整workflow；不计正式TDD信用。

窄mutation匿名10方法：删callback计数4Assertion；把失败也observed导致3Assertion；state误归ETL导致1Assertion；删CI total一致性导致1Assertion，均0ERRORskip。它们证明词法计数、unknown与消费者必要条件可见，不证明完整PowerShell工作流执行。除下述I1的纯receipt片段WinPS5.1预演外，CI消费者仍仅静态审查；完整工作流/SetupAPI仍需新同SHA双Windows验证。

fresh SPEC I1（mac_m0a2_event_diagnostic_source，C0/I1/M0）证实新增nested键集合比较误用大小写不敏感 -notcontains。继任作者按writing-plans与receiving-code-review先核实际资产，再在本机Windows PowerShell 5.1.19041.6456的RAM执行直接从D抽取的nested验证语句，不调用helper/网络/系统API：规范五键原/修订均接受；分别将target/state/etl/other/unknown改为大写，原消费者5/5接受，修订后5/5拒绝，预演exit0。仅新增nested比较改-cnotcontains；旧top-level -notcontains兼容保持。最初探索驱动用子作用域读取了未更新的valid，已改为同作用域dot-source再得上述结果；该初次驱动结果不计验证信用。

I1最小修订：A既有CI-only方法只加一条大小写精确比较断言，仍10方法、全部旧断言保留；D只增加比较符号中的c，原top-level循环不变；B/C逐字相同。匿名新A：旧产品10项9父Assertion/1绿/0ERRORskip/.038s（strict语义exit1）；新A+B+C+D投影10GREEN/.047s、旧7GREEN/.001s、迁移旧24GREEN/.032s，均0ERRORskip；RAM驱动exit0。仅将投影D恢复原不敏感比较，新A10项恰1Assertion/0ERRORskip/.054s，失败消息nested category keys must be case-sensitive，预期突变驱动exit0。此处Python oracle仍是静态workflow断言，真实大小写拒绝依据是上面的WinPS片段实跑，不混作完整CI验收。

自SPEC：三问、四实现路径、默认v3/v4显式准入、旧exactgate/firstfailure/cleanup、nil失败、分类隐私与预算闭合；所有改动有完整资产，无替代schema承诺。
selfQUALITY：state/ETL标签不能当格式或drop原因；无任意XMLfallback；最多4096回调既有预算、8MiB parser/64MiB CAB不变；JSON实际序列化≤500不截断；source8/CI2阶段分账，旧24仅单断言迁移，未删旧门。保持原函数类型注释兼容，附加state dict仅私有计数、不对外序列化路径。
原始patch空白上下文按unified diff字节保留；若raw whitespace检查命中围栏单空格空上下文应明确分类，不修改冻结patch或冒raw全零。

【架构级自检报告】
- 语法/编译：Python资产AST与匿名软件执行通过；WinPS5.1仅执行nested receipt验证片段，完整工作流/Windows SDK未执行。
- 依赖/调用链：真实callback→main→v4消费者→普通日志成对；默认v3正控完整。
- 逻辑/边界：exact/state/ETL/other/unknown、多目标、4096/4097及null失败覆盖。
- 异常处理：API权限/member/预算失败不输出完整零计数，不扩大提取。
- 关联模块：旧7/迁移24通过；Reviewer/parser/native/Actions消息冻结。
- 兼容安全：无新权限/依赖/系统设置、rawCAB或私密名称输出。
- 可运行性：匿名软件41通过信用；正式TDD/双Windows/线上验收仍待，不能写100%。

## 10. 完整冻结资产

所有资产正文保留末LF；以下为计划，不在此轮实施。

### Asset A：tests/test_windows_wfp_cab_observation.py（完整新增）

~~~python
"""CAB category observations exercise the real callback and JSON serializer only."""
from __future__ import annotations

import contextlib
import ctypes
import inspect
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import inspect_windows_cabinet_members as probe

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("target", "state", "etl", "other", "unknown")


class TestWfpCabObservation(unittest.TestCase):
    def receipt(self, names=(), *, error=None, default=False, member_error=0):
        class NativeFunction:
            def __call__(self, _path, _reserved, callback, context):
                if callback(context, 0x10, 0, 0) != 0:
                    raise AssertionError("CAB metadata must not extract")
                for name in names:
                    info = probe._FileInCabinetInfoW()
                    info.NameInCabinet = name
                    info.Win32Error = member_error
                    if callback(context, 0x11, ctypes.addressof(info), 0) != 2:
                        return False
                return True
        api = SimpleNamespace(SetupIterateCabinetW=NativeFunction())
        supports = "observe_categories" in inspect.signature(probe.inspect_cabinet_members).parameters
        arguments = []
        with tempfile.TemporaryDirectory(prefix="cab-observation-software-") as tmp:
            archive = Path(tmp) / "private-source-identity.cab"
            archive.write_bytes(b"MSCF synthetic API-boundary fixture")
            arguments = ["--archive", str(archive)]
            if not default and supports:
                arguments.append("--observe-categories")
            output = io.StringIO()
            with mock.patch.object(probe, "os", SimpleNamespace(name="nt")), \
                 mock.patch.object(probe.ctypes, "WinDLL", create=True,
                                   side_effect=error, return_value=api), \
                 mock.patch.object(probe.ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, create=True), \
                 contextlib.redirect_stdout(output):
                code = probe.main(arguments)
            wire = output.getvalue()
        self.assertLessEqual(len(wire.encode("utf-8")), 500)
        self.assertEqual(wire.count("\n"), 1)
        self.assertNotIn("private-source-identity", wire)
        return code, json.loads(wire), wire

    def categories(self, result):
        self.assertEqual(result.get("schema_version"), 4, "CAB_CATEGORY_SCHEMA_REQUIRED")
        value = result.get("member_categories")
        self.assertIsInstance(value, dict, "CAB_CATEGORY_OBSERVATION_REQUIRED")
        self.assertEqual(set(value), set(KEYS))
        return value

    def test_real_callback_and_cli_classify_fixed_members(self):
        code, result, wire = self.receipt(
            ("nested/WFPDIAG.XML", "wfpstate.xml", "nested/trace.etl", "notes.txt"))
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "listed")
        self.assertEqual(self.categories(result),
                         dict(target=1, state=1, etl=1, other=1, unknown=0))
        self.assertEqual(result["target_match_count"], 1)
        self.assertEqual(result["xml_member_count"], 2)
        for private in ("nested", "notes.txt", "trace.etl"):
            self.assertNotIn(private, wire)

    def test_unknown_and_noncanonical_names_are_counted_not_extracted(self):
        code, result, wire = self.receipt(
            ("secret/user.xml", "trace.\u03bc.xml", "bad\nname.etl", "", None))
        self.assertEqual(code, 0)
        self.assertEqual(result["target_match_count"], 0)
        self.assertEqual(self.categories(result),
                         dict(target=0, state=0, etl=0, other=1, unknown=4))
        self.assertEqual(sum(self.categories(result).values()), 5)
        self.assertNotIn("secret", wire)
        self.assertNotIn("user.xml", wire)

    def test_multiple_exact_targets_keep_original_ambiguity(self):
        _, result, _ = self.receipt(("wfpdiag.xml", "nested/wfpdiag.xml"))
        self.assertEqual(result["target_match_count"], 2)
        self.assertEqual(self.categories(result)["target"], 2)
        self.assertEqual(result["member_count"], 2)

    def test_api_permission_failure_is_unavailable_not_zero_categories(self):
        code, result, wire = self.receipt(error=PermissionError("private path token"))
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "api_unavailable")
        self.assertEqual(self.categories(result), dict.fromkeys(KEYS))
        self.assertNotIn("private path token", wire)

    def test_member_permission_error_never_becomes_a_complete_observation(self):
        code, result, wire = self.receipt(("wfpdiag.xml",), member_error=5)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "member_error")
        self.assertEqual(self.categories(result), dict.fromkeys(KEYS))
        self.assertIsNone(result["target_match_count"])
        self.assertNotIn("wfpdiag.xml", wire)

    def test_member_limit_failure_does_not_publish_partial_zero_counts(self):
        code, result, _ = self.receipt(("wfpstate.xml",) * 4097)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "member_limit_exceeded")
        self.assertEqual(result["member_count"], 4097)
        self.assertEqual(self.categories(result), dict.fromkeys(KEYS))

    def test_largest_success_counts_serialize_under_budget(self):
        code, result, _ = self.receipt(("capture.etl",) * 4096)
        self.assertEqual(code, 0)
        counts = self.categories(result)
        self.assertEqual(counts["etl"], 4096)
        self.assertEqual(sum(counts.values()), result["member_count"])

    def test_default_v3_receipt_and_exact_matcher_are_unchanged(self):
        code, result, _ = self.receipt(("wfpdiag_extra.xml",), default=True)
        self.assertEqual(code, 0)
        self.assertEqual(result["schema_version"], 3)
        self.assertNotIn("member_categories", result)
        self.assertEqual(result["target_match_count"], 0)
        self.assertTrue(probe.is_target_cabinet_member("nested/WFPDIAG.XML"))
        self.assertFalse(probe.is_target_cabinet_member("wfpdiag_extra.xml"))

    def test_workflow_observation_is_after_validation_and_does_not_expand_admission(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        start = workflow.index("  windows-reviewer-snapshot-probe:")
        end = workflow.index("  windows-appcontainer-read-handle-probe:", start)
        job = workflow[start:end]
        self.assertTrue("'--archive', $wfpCaptureArchive, '--observe-categories'" in job, "fixed workflow contract missing")
        self.assertTrue("$cabinetMemberSummary.schema_version -eq 4" in job, "fixed workflow contract missing")
        self.assertTrue("$categoryTotal -eq $cabinetMemberSummary.member_count" in job, "fixed workflow contract missing")
        self.assertTrue("$categoryNames -cnotcontains $key" in job, "nested category keys must be case-sensitive")
        self.assertTrue("$categories.target -eq $cabinetMemberSummary.target_match_count" in job, "fixed workflow contract missing")
        self.assertLess(job.index("$categoryTotal -eq"),
                        job.index("$wfpArchiveCategoryCounts = (\'target:"))
        self.assertTrue("cab_categories=$wfpArchiveCategoryCounts" in job, "fixed workflow contract missing")
        self.assertTrue("if ($matchDisposition -eq 'missing')" in job, "fixed workflow contract missing")
        self.assertTrue("$wfpCaptureStatus = 'archive_member_missing'" in job, "fixed workflow contract missing")
        self.assertTrue("@($wfpCaptureArchive, '-F:wfpdiag.xml', $wfpExtractExplicitFile)" in job, "fixed workflow contract missing")
        self.assertTrue("$wfpCaptureArchive, '-F:*'" not in job, "fixed workflow contract missing")
        self.assertTrue("Write-Output $memberListResult.Stdout" not in job, "fixed workflow contract missing")
        self.assertTrue("'set', 'options'" not in job, "fixed workflow contract missing")

    def test_strict_count_and_existing_actions_notice_are_preserved(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("pattern='test_windows_wfp_cab_observation.py'"), 2)
        for command in (line for line in workflow.splitlines()
                        if "pattern='test_windows_wfp_cab_observation.py'" in line):
            self.assertTrue("countTestCases()==10" in command, "fixed workflow contract missing")
            self.assertTrue("not r.wasSuccessful() or bool(r.skipped)" in command, "fixed workflow contract missing")
        notice = next(line for line in workflow.splitlines()
                      if '::notice title=Windows WFP capture and runner observer::' in line)
        self.assertTrue("cab_categories" not in notice, "fixed workflow contract missing")
        self.assertTrue("capture=$wfpCaptureStatus" in notice, "fixed workflow contract missing")


if __name__ == "__main__":
    unittest.main()
~~~

### Asset B：scripts/inspect_windows_cabinet_members.py

~~~diff
*** Begin Patch
*** Update File: scripts/inspect_windows_cabinet_members.py
@@ -16,6 +16,7 @@
 _TARGET_BASENAME = "wfpdiag.xml"
 _WFPDIAG_BASENAME_PREFIX = "wfpdiag"
 _XML_SUFFIX = ".xml"
+_CATEGORY_KEYS = ("target", "state", "etl", "other", "unknown")
 
 _SPFILENOTIFY_CABINETINFO = 0x10
 _SPFILENOTIFY_FILEINCABINET = 0x11
@@ -85,6 +86,25 @@
     if not basename.isascii() or not basename:
         return None
     return basename
+
+
+def _member_category(member_name: object) -> str:
+    """Metadata labels only; never authorize extraction or retain member names."""
+    basename = _cabinet_member_basename(member_name)
+    if basename is None:
+        return "unknown"
+    # Preserve the original exact-target contract, including nested CAB paths.
+    if is_target_cabinet_member(member_name):
+        return "target"
+    if len(member_name) > 4096 or not member_name.isascii() or any(
+        ord(char) < 32 or ord(char) == 127 for char in member_name
+    ):
+        return "unknown"
+    if basename.lower() == "wfpstate.xml":
+        return "state"
+    if basename.lower().endswith(".etl"):
+        return "etl"
+    return "other"
 
 
 def _safe_summary(
@@ -160,6 +180,11 @@
                 int(state["wfpdiag_prefixed_xml_member_count"]) + 1
             )
 
+        categories = state.get("_category_counts")
+        if isinstance(categories, dict):
+            category = _member_category(info.NameInCabinet)
+            categories[category] += 1
+
         # Enumeration is intentionally non-extracting for every member.
         return _FILEOP_SKIP
 
@@ -173,7 +198,7 @@
     return _ERROR_NOT_SUPPORTED
 
 
-def _enumerate_windows_cabinet(archive_path: Path) -> dict[str, int | str | None]:
+def _enumerate_windows_cabinet(archive_path: Path, *, category_counts=None) -> dict[str, int | str | None]:
     try:
         setupapi = ctypes.WinDLL("setupapi.dll", use_last_error=True)
         setup_iterate_cabinet = setupapi.SetupIterateCabinetW
@@ -186,6 +211,9 @@
         "xml_member_count": 0,
         "wfpdiag_prefixed_xml_member_count": 0,
     }
+
+    if category_counts is not None:
+        state["_category_counts"] = category_counts
 
     callback_type = ctypes.WINFUNCTYPE(
         wintypes.UINT,
@@ -233,7 +261,7 @@
     )
 
 
-def inspect_cabinet_members(archive: str | Path) -> dict[str, int | str | None]:
+def _inspect_cabinet_members(archive: str | Path, *, category_counts=None) -> dict[str, int | str | None]:
     """Enumerate a bounded cabinet and return only a fixed, privacy-safe receipt."""
     try:
         archive_path = Path(archive)
@@ -248,17 +276,31 @@
     if os.name != "nt":
         return _safe_summary("unsupported_platform")
     try:
-        return _enumerate_windows_cabinet(archive_path)
+        return _enumerate_windows_cabinet(archive_path, category_counts=category_counts)
     except Exception:
         # Native errors remain a fixed category; do not echo exception text or paths.
         return _safe_summary("api_failed")
 
 
+def inspect_cabinet_members(archive: str | Path, *, observe_categories=False) -> dict:
+    counts = dict.fromkeys(_CATEGORY_KEYS, 0) if observe_categories else None
+    result = _inspect_cabinet_members(archive, category_counts=counts)
+    if not observe_categories:
+        return result
+    # An API/member/budget failure is unavailable, never a complete zero count.
+    observed = result["status"] == "listed"
+    return dict(result, schema_version=4, member_categories={
+        key: counts[key] if observed else None for key in _CATEGORY_KEYS
+    })
+
+
 def main(argv: list[str] | None = None) -> int:
     parser = argparse.ArgumentParser(description=__doc__)
     parser.add_argument("--archive", required=True, help="local CAB file to enumerate")
+    parser.add_argument("--observe-categories", action="store_true",
+                        help="emit fixed metadata category counts, never member names")
     args = parser.parse_args(argv)
-    result = inspect_cabinet_members(args.archive)
+    result = inspect_cabinet_members(args.archive, observe_categories=args.observe_categories)
     print(json.dumps(result, sort_keys=True, separators=(",", ":")))
     return 0 if result["status"] == "listed" else 1
 
*** End Patch
~~~

### Asset C：tests/test_windows_wfp_capture.py（旧24仅单断言迁移）

~~~diff
*** Begin Patch
*** Update File: tests/test_windows_wfp_capture.py
@@ -626,7 +626,7 @@
             prefix_count_receipt,
             job.index("wfpdiag_xml_members=$wfpArchiveWfpdiagXmlMemberCount"),
         )
-        self.assertIn("$cabinetMemberSummary.schema_version -eq 3", job)
+        self.assertIn("$cabinetMemberSummary.schema_version -eq 4", job)
 
     def test_workflow_rejects_malformed_or_unbounded_cabinet_probe_receipts(self) -> None:
         repository_root = Path(__file__).resolve().parents[1]
*** End Patch
~~~

### Asset D：.github/workflows/ci.yml

~~~diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@ -64,6 +64,8 @@
         run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_config_observation.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Strict positive loopback notice budget software contract
         run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_notice_budget.py'); assert s.countTestCases()==3, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
+      - name: Strict WFP CAB metadata observation software contract
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_wfp_cab_observation.py'); assert s.countTestCases()==10, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Compile Python sources
         run: python -m compileall -q src tests scripts
       - name: Run the full unit test suite
@@ -845,6 +847,8 @@
             }
           }
           Write-Output "::notice title=WFP observer identity control::runner_admin_token=$runnerAdminToken runner_wfp_observer_permission_probe=$observerPermissionState runner_wfp_observer_setup=$observerSetupStage runner_wfp_observer_helper_exit_code=$observerHelperExitCode runner_wfp_network_events_collected=$observerNetworkEventsState subscription_return_code=$observerReturnCode"
+      - name: Strict WFP CAB metadata observation software contract
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_wfp_cab_observation.py'); assert s.countTestCases()==10, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Run Reviewer snapshot probe as temporary standard user
         shell: pwsh
         run: |
@@ -881,6 +885,7 @@
           $wfpArchiveMemberMatchCount = 'not_checked'
           $wfpArchiveXmlMemberCount = 'not_checked'
           $wfpArchiveWfpdiagXmlMemberCount = 'not_checked'
+          $wfpArchiveCategoryCounts = 'unavailable'
           $wfpExactDropCount = 0
           $wfpExtractExitCode = 'not_run'
           $wfpMemberSelfTestStage = 'prepare'
@@ -1917,7 +1922,7 @@
                       $wfpXmlCandidates = @()
                       $memberListResult = Invoke-BoundedDiagnosticCommand `
                         -Path $python -Arguments @(
-                          $cabinetMemberProbe, '--archive', $wfpCaptureArchive
+                          $cabinetMemberProbe, '--archive', $wfpCaptureArchive, '--observe-categories'
                         ) -TimeoutMilliseconds 5000 -CaptureStdout
                       if ($memberListResult.TimedOut) {
                         $wfpArchiveMemberStatus = 'list_timeout'
@@ -1934,7 +1939,7 @@
                           )
                           $expectedSummaryPropertyNames = @(
                             'member_count', 'schema_version', 'status', 'target_match_count',
-                            'xml_member_count', 'wfpdiag_prefixed_xml_member_count'
+                            'xml_member_count', 'wfpdiag_prefixed_xml_member_count', 'member_categories'
                           )
                           $cabinetSummaryValid = (
                             $summaryPropertyNames.Count -eq $expectedSummaryPropertyNames.Count
@@ -1946,7 +1951,7 @@
                           }
                           if ($cabinetSummaryValid) {
                             $cabinetSummaryValid = (
-                              $cabinetMemberSummary.schema_version -eq 3 -and
+                              $cabinetMemberSummary.schema_version -eq 4 -and
                               ($cabinetMemberSummary.member_count -is [int] -or
                                $cabinetMemberSummary.member_count -is [long]) -and
                               $cabinetMemberSummary.member_count -ge 0 -and
@@ -1973,6 +1978,28 @@
                           $cabinetSummaryValid = $false
                         }
                         if ($cabinetSummaryValid) {
+                          $categoryKeys = @('target', 'state', 'etl', 'other', 'unknown')
+                          $categories = $cabinetMemberSummary.member_categories
+                          $categoryNames = @($categories.PSObject.Properties.Name)
+                          $categoryTotal = 0
+                          $cabinetSummaryValid = $categoryNames.Count -eq $categoryKeys.Count
+                          foreach ($key in $categoryKeys) {
+                            $value = $categories.$key
+                            if ($categoryNames -cnotcontains $key -or
+                                ($value -isnot [int] -and $value -isnot [long]) -or
+                                $value -lt 0 -or $value -gt 4096) {
+                              $cabinetSummaryValid = $false
+                            } else {
+                              $categoryTotal += $value
+                            }
+                          }
+                          $cabinetSummaryValid = $cabinetSummaryValid -and
+                            ($categoryTotal -eq $cabinetMemberSummary.member_count) -and
+                            ($categories.target -eq $cabinetMemberSummary.target_match_count)
+                        }
+                        if ($cabinetSummaryValid) {
+                          $wfpArchiveCategoryCounts = ('target:{0},state:{1},etl:{2},other:{3},unknown:{4}' -f
+                            $categories.target, $categories.state, $categories.etl, $categories.other, $categories.unknown)
                           $wfpArchiveMemberCount = [string]$cabinetMemberSummary.member_count
                           $wfpArchiveXmlMemberCount = [string]$cabinetMemberSummary.xml_member_count
                           $wfpArchiveWfpdiagXmlMemberCount = [string]$cabinetMemberSummary.wfpdiag_prefixed_xml_member_count
@@ -2096,6 +2123,7 @@
             }
             Write-Output '::group::Windows WFP supplemental capture states'
             Write-Output "observer_preflight=$runnerWfpObserverPreflightState capture_preflight=$wfpCapturePreflight archive_member_match_count=$wfpArchiveMemberMatchCount"
+            Write-Output "cab_categories=$wfpArchiveCategoryCounts"
             Write-Output "observer_matched_classify_drops=$runnerWfpMatchedClassifyDropCount matched_capability_drops=$runnerWfpMatchedCapabilityDropCount history_capability=$runnerWfpHistoryCapability history_classify=$runnerWfpHistoryClassify"
             Write-Output "capture_status=$wfpCaptureStatus exact_classify_drop_count=$wfpExactDropCount extract_exit_code=$wfpExtractExitCode cab_status=$wfpArchiveMemberStatus cab_members=$wfpArchiveMemberCount xml_members=$wfpArchiveXmlMemberCount wfpdiag_xml_members=$wfpArchiveWfpdiagXmlMemberCount"
             Write-Output '::endgroup::'
*** End Patch
~~~

## 11. 资产与投影摘要

|资产|行数|SHA256|hunks|
|---|---:|---|---:|
|A完整新TEST|164|864f450da603cdb85528236599327700378187bb7008a0928e65acf9aba657ac|新增|
|B helper patch|111|df872dbecabdb6d52541ae2bf1acaf9ccd0724cc2353001021d365c1661c9aa4|7|
|C旧TEST patch|12|5b368a8ef54535c880a9099395985646e2887031dc4f341a184ce729b12eb2a6|1|
|D CI patch|93|dae336968e4e5db2937c675418f6be8da1c7101ca66c29603a7ce089d32d1c78|8|

|未来输出|行数|SHA256|
|---|---:|---|
|scripts/inspect_windows_cabinet_members.py|309|e68d7048a344a6b50c9080cc0b309bc8a7465dc6eba8c958f07c812504dc7152|
|tests/test_windows_wfp_capture.py|817|6ebbc90a1cafe9a302eddf1a89469ae9940035a7febdfb1294a6d8ddccf823dc|
|.github/workflows/ci.yml|2539|c3e4276128567359d472c80af482a723d5fe131eed2bb7352e4485c8782140e8|

---

## 追加执行记录：CI精确总门清单同步

原596行批准版SHA148425c7bbe62a30ce4e9f195f19d34e78cb6f63e8ffa4793af33396f2202dac及A/B/C/D资产保持原字节。root发布前扩查发现现有test_full_suite_ci_budget的精确命令清单消费者漏同步，原七路径双审与56定点未覆盖此旧关联；暂缓发布，不把原审查当完整关联通过。

4296b0对实际已接D的工作树运行原3方法，2绿、精确命令清单1条Assertion、0ERROR/skip、exit1；随后仅补清单中本次新增strict10命令。3caea4实际3方法全绿、0ERROR/skip、exit0。保持assertEqual整列、每门一次/固定顺序、原25分钟、矩阵及失败语义，不删除断言或弱化为子串包含。

仅新增第五个实现路径tests/test_full_suite_ci_budget.py的一行TEST迁移；原四实现不变，候选因此为五实现＋本文＋两进度文档共八路径。输入41行SHA98e16e2e00240c4f9237bced0c0e10b4bd4ca6f4f5671517425f802610649e2a；输出42行SHA24b971867ba890eac238366f7ce6297322527b404956757c08403eb31bc67287。新范围须独立全片SPEC补审及不同QUALITY后才发布，不预授线上结果。

### Asset E：既有CI总门精确清单单行迁移

~~~diff
*** Begin Patch
*** Update File: tests/test_full_suite_ci_budget.py
@@ -27,2 +27,3 @@
             "python -B -c \"import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_notice_budget.py'); assert s.countTestCases()==3, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))\"",
+            "python -B -c \"import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_wfp_cab_observation.py'); assert s.countTestCases()==10, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))\"",
             "python -m compileall -q src tests scripts",
*** End Patch
~~~
## 追加执行记录：失败状态不发布类别计数

八路径fresh QUALITY实际在Windows PowerShell 5.1运行真实消费者片段，发现exit0但status为api_failed、member_error或LISTED且数字字段合法时，类别日志仍显示有效计数；下游提取虽拒绝，观测仍违反失败应为unavailable的合同，记录为I1并阻断发布。原59项绿不能证明这一缺口已覆盖。

不同TEST作者仅在原10方法之一新增四行相邻精确listed门断言，168行／9401字节／SHA90c7d8ab48c17d8aedf6b3cda9df23d1d2910f010f1eacb028add058420f2dc4；删除该块精确恢复原Asset A。正式197850为9绿／新断言唯一Assertion、零ERRORskip，actual TEST SPEC与不同QUALITY均零。不同SOURCE root仅修改下列CI条件，保留summary_invalid／list_failed与旧提取拒绝分支；420e90关联59项／1.527s全绿、零ERRORskip。实际SOURCE双审及新候选线上仍待，不授原生或R2/R3通过。

### Asset F：仅收紧类别日志成功状态

~~~diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@
-                        if ($cabinetSummaryValid) {
+                        if ($cabinetSummaryValid -and $cabinetMemberSummary.status -ceq 'listed') {
                           $wfpArchiveCategoryCounts = ('target:{0},state:{1},etl:{2},other:{3},unknown:{4}' -f
*** End Patch
~~~

当前CI2539行／SHA289b21930ff23ec4c15dd07303580f6d78a6e299bc2caec8758e310c9ac7f5d7，逆此唯一条件精确恢复批准D投影c3e42761。原596行批准资产及Asset E原字节保留，本记录仍插在原Execution Mode页脚前；原围栏投影是历史基线，最终TEST／CI以上述执行修订为准。Mac输入账本原冻结CI随之再次漂移，正式实施前必须重核，不覆盖或伪称仍c3e。

**Execution Mode:** serial。STOP：只交唯一PLAN，等root全文与fresh SPEC→不同QUALITY全零；不同TEST作者正式RED后不同SOURCE，不自动写产品/TEST/CI或stage/commit/push。
