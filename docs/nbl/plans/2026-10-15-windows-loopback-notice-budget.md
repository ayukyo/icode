# Windows positive loopback notice budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 批准实施后使用 nbl.subagent-driven-development 或 nbl.executing-plans，按独立 TEST → 不同 SOURCE → fresh actual SPEC → 不同 QUALITY 串行执行。
> 状态：PLAN ONLY；本轮只新增本文，不能执行实际 TEST/SOURCE/CI、Git 或原生操作。main-only、仅 root 提交与本轮 PLAN ONLY 覆盖技能默认 worktree、提交和自动执行建议。

**Goal:** 无损输出 loopback 完整诊断，同时满足原单 JSON 500 字符与每步九个诊断 Actions annotation 槽，恢复原 Reviewer 首错误与后续门，并补齐三个关联回归。

**Architecture:** 完整 pre/post/comparison 分成三个固定普通 stdout 日志；仍通过实际 JSON serializer 与500断言，再由上层固定三标题路由。原 _workflow_notice、八个原 Actions 标签、WFP和九槽断言不变；测试复用真实 serializer/路由/Actions函数和原正控block，只隔离 OS执行边界。

**Tech Stack:** Python stdlib/unittest、现有 GitHub CI；无新依赖、通用分片协议、API、capability 或权限。

## 1. 真实问题、证据与信用

观察日2026-10-15；analysis/main基线 `b233b66431984aed78266d294a88653586b8caec`，vendor/icode-skill `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。权威工作区 WSL Ubuntu-22.04 `/home/orbbec/projects/icode`；Windows `D:\\Projects\\icode` 保留不动。root sequential-thinking `964bed` 三步accepted及后续固定普通日志批准为输入，不冒称作者亲调。runtime=b233 CI云runner（不称物理设备）/analysis=b233/verification=未有修复后原生证据。

root交接：x64 Reviewer job115978478531原log19.465s，ARM64 job115978478714原log18.874s，均真实JSON865>500首断言失败；root已全文实读168510字符x64log，记录名 `b233-root-win-reviewer-x64`。本作者未重新下载/冒称亲核双平台原日志；helper build=staged hash只授文件时点一致，不授mapped字节或同对象启动。

root另交接b233 Python3.11 full footer：3344tests/624.227s/3failures/99skips。本作者已只读定位并定点实际复现 `04d401`：3tests/1.058s/3Assertion failures/0ERROR/skip/exit1。分别是：
1. Reviewer静态方法2603执行真实wrapped正控，由旧单条loopback JSON882>500失败。
2. private-connect `test_real_notice_budget_enumerates_actual_mapping` 调同一静态方法，第二次见证同882失败；不是第二个原生根因。
3. CIbudget `test_required_gates_run_once_in_order` 冻结五命令列表漏掉b233已有strict12；不是native失败。

旧loopback553L/12方法fixture使用假的紧凑comparison和参数收集notice，验证接线但绕过真实serializer/500/Actions消费门。本片如实补这个覆盖盲点，不能把旧12GREEN解释为输出可用。作者直接读实际两输出函数：上层compact ensure_ascii JSON→assert≤500→下层；下层先500截取再转义并仅CI输出。旧两端合并单条在截断前被拒绝。

进一步读到静态方法原 `len(captured_notices)+len(wfp_notice_lines)≤9`，为最终runner summary预留第十槽。原八Actions+一WFP已占九；三个新Actions会十二，不能只修字符限制。因此root明确批准三条loopback改普通日志，并保留原500及≤9门。所有八旧标签和原全部状态映射/最大字段断言均保留。

三问：真实问题有CI/本机证据；复用既有serializer/consumer/fixture/比较；调用链仅诊断及测试，无产品或隔离行为变更。研究为紧急小修不新增竞品研读、不刷新20榜；复用批准设计的固定Codex27065a91ccbf5ba8532844be3777fcf83b77820d（Apache2）执行/输出信用分离与本仓真实预算。采纳三条固定日志：无损低成本；暂缓通用分片；不适配扩预算/丢字段/Set/豁免/权限。未复制上游代码，无新许可或依赖影响；出处沿用[原设计研究](../specs/2026-10-14-windows-loopback-config-observation-design.md)，不声称刷新上游状态。

## 2. 最小输出与测试契约

上层 `_workflow_json_notice` 保留原编码及500断言；仅三个确切标题路由到 `positive_loopback_config_pre=` / `positive_loopback_config_post=` / `positive_loopback_config_comparison=` 普通stdout行，仍仅GITHUB_ACTIONS=true打印。其它任意标题仍走原Actions路径，无通用前缀旁路；原 `_workflow_notice` 整个函数逐字不变。每样本≤500，三个主体合计≤1500；这是日志，不是三个Actions annotations。既有post-unreaped first-result摘要仍原输出，不新占三槽。

正常/unknown输出完整pre、完整post、独立comparison；直接取两样本变量，comparison本体不变仅读返回comparison键。pre unreaped输出完整pre/not_attempted post/unknown comparison后原停止；post unreaped先三日志再原first-result摘要/原停止；旧cleanup/launcher异常保留原错误并输出已有pre/not_attempted post。普通unknown不跳过实验；same-profile/token/采样顺序/DENY门不变，comparison不授网络、WFP或根因信用。

A新3方法执行实际block/serializer/upper固定路由/lowerActions/父comparison/unknown，stub仅外部launch/sample；从实际stdout区分普通日志和Actions，JSON重构完整dict/字段与phase，无截断或drop。覆盖最大complete、实际合法unknown、pre/post未回收、旧cleanup/launch首错；fixed-route oversize仍被500拒绝、非CI不打印、相似任意标题仍走Actions、旧%/CR/LF转义实测。B只旧TEST fixture增加三个可选注入seam，默认旧12方法/断言/计数不减。

E迁移旧静态fixture：实际复用真实 `_workflow_json_notice`，补真实assertLessEqual，lower绑定实际 `_workflow_notice` 后收集原Actions；从实际stdout独立解析三条普通日志完整unknown/phase/comparison，而非mock按名字排除。原八标签/≤9/所有最大字段mapping不动。仅该软件fixture显式清空helper路径环境，防止环境遗留触发真helper；native Reviewer环境/staging不改。F仅关联测试增加三固定普通日志前缀源码映射断言，保留原退出码全mapping和真实static运行断言。G精确列表保留原五命令相对顺序/次数，加b233已有strict12及本片strict3，不能删gate/改count规则。

已完整读wrapped监听生命周期：只绑定127.0.0.1/::1端口0，host control只连这些地址；finally逐listener shutdown/join(timeout3)/server_close及home临时目录cleanup。静态fixture launcher为fake，脚本只compile，native API fake，helper路径为空。本作者获root明确授权仅两既有单方法的必要localhost软件回归；不外网、不真AppContainer/helper/DLL/firewall/system/full。

## 3. 字节冻结、阶段投影与停止线

资产UTF-8/LF，hash含末尾一个LF不含围栏；原文件末尾空行按bytes保留。所有hunk前/后块在对应中间状态恰一处匹配，inverse反序恢复原字节；漂移停止交root，不改hash强套。A必须不存在；root文档及其它作者dirty不动。

| 路径 | b233输入SHA256/行数 | TEST后或最终唯一输出SHA256/行数 |
| --- | --- | --- |
| 新tests/test_windows_loopback_notice_budget.py | 不存在 | 88cdbd9e03fea01c66c8a93254264cb482db6de4722bde210f669bae10595d35 /159 |
| tests/test_windows_loopback_config_observation.py | 45fa5f0734a551fbd043dce535420881936c2cc993be4b25ceb4fc484f2a8060 /553 | B:8461eda79c07f9fb6eeb7f14b36313347cb72f6d6e68aed8623be26fb7797a43 /557 |
| tests/test_windows_appcontainer.py | 5be4949f16dbf7a0607bdc5e24a1cf110c94c65e2b8b862b03a74c6c35ed61cc /9424 | E:7bc559b0f789dd34f2a595967fc8e84c2a8302cef2bf6a8ae21004de5488ca15 /9438；再C:e5b421b994c5866a60ff72feff6db68f8e037151c6f6b59331ce4c900513c81d /9459 |
| tests/test_windows_private_connect_diagnostic.py | 0199e7d9cb3e24e52f8ccddd7b528b7b2bccb97686c4001fc794a1f3f83a92d5 /313 | F:93501385bb724ee496b1f97a2e46c4f6da068afa8c393c8124b67e6c55885f7e /319 |
| tests/test_full_suite_ci_budget.py | a06eb8377715529feda124644b896573baff304ea338bb81b269fc963f3c90e1 /39 | G:98e16e2e00240c4f9237bced0c0e10b4bd4ca6f4f5671517425f802610649e2a /41 |
| .github/workflows/ci.yml | 29a7b8f8062c209388a7601126459f2aff4a3c23ecb777eac12f86760206fb68 /2506 | D:8045df800fde72f6ff2a94f1ea74cb039ed9a24abc1979c7189cb79e3b9307a6 /2508 |

| 资产 | 行数/hunks | SHA256 |
| --- | --- | --- |
| A完整新TEST |159|88cdbd9e03fea01c66c8a93254264cb482db6de4722bde210f669bae10595d35|
| B旧TEST seam |18/3|0d59a2a5f9ab540201c6d4c02a9717ccc1886fd73c570b1ae994955a896e0156|
| C SOURCE（仅在E投影后）|55/3|c795b8fd595d129adbab5549a58182f9d00d765c6a6ddab8c6dde87d37bf1799|
| D CI |10/1|a12d2dcb6f1198622413da67a1858cbf1dd3c285ae45ca71f7c8d38f68213b57|
| E静态TEST迁移 |48/3|1ac2b511fec2c1316ae6829015a6a073b0576bd4158c439e77a36134acd060ff|
| F关联TEST映射 |12/1|4756291b56cf806e16af8e2443d605211b03a44220f1a91c3b4be122a8d55f42|
| G gate TEST清单 |10/1|bb3716dbc9d8a283d526db2e6fe9f52e09c7512ebebdbaa3ac755f7978c30a8d|

六patch共12hunks，A完整新文件。B/E/F/G属于TEST，C属于SOURCE，D属于CI，不能混阶段落地。所有实际产品/native/父脚本/CMake/vendor不变：
windows_job.py ac2bfbe924a9b03b68ab0304f55cfcfde7b79615c3563c0db61ca099d335d640；
windows_appcontainer.py 307dc730bf28bc661ad99b8d02dc9093b51c1dcdf45f993b470e68a5562f1a1f；
CMakeLists.txt a617f5c0cd5c1e50065aad54469bba20f9c63c7065475b48176bff9c9f30105c；
icode_wfp_event_probe.c 1796d36ca0964d685a7d0aeedb8bbabd3d29a8eb7c209255310f1ee6769ad596；
icode_positive_loopback_config.inc 194a6902cb828a71cac25c10b3bb66a1189355c888f7d51b724cc31c895de977；
run_windows_appcontainer_read_probe.py ca84b611053f8b3d9e92196dc71561bfa93c54f2a545e302500ec92b27699d92。

停止线：需要扩500/九槽、drop字段/旧label、改变原DENY/首错误/退出码mapping、权限/配置/网络能力、真helper/native/外网或本机full时退回root。Agent禁止stage/commit/push；不取消/重跑在途CI隐藏失败。

## 4. 正式串行任务与命令

以下严格命令都在WSL根执行，exit反映实际测试成败，不以诊断驱动成功替测试RED。新/旧strict均不许skip。关联命令仅选原三方法，不全套：

~~~~bash
PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_config_observation.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_notice_budget.py'); assert s.countTestCases()==3, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -c "import unittest; from tests.test_windows_appcontainer import TestWindowsAppContainer as A; from tests.test_windows_private_connect_diagnostic import TestPrivateConnectDiagnostic as P; from tests.test_full_suite_ci_budget import TestFullSuiteCiBudget as G; s=unittest.TestSuite([A('test_Reviewer快照原生探针脚本在非Windows主机可静态解析'),P('test_real_notice_budget_enumerates_actual_mapping'),G('test_required_gates_run_once_in_order')]); assert s.countTestCases()==3; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~~

### Task1 — 独立TEST作者 A+B+E+F+G
**Dependencies:** None（先root全文/freshSPEC→不同QUALITY批准）
**Parallelizable:** No（实际测试先于SOURCE）
- [ ] 核主/pin/六实际输入/边界/缺A，完整读所有资产与实际监听清理上下文；用apply_patch仅落A/B/E/F/G，C/D不落。
- [ ] 旧strict12须12GREEN/0F/E/skip，证明默认seam无退化；新strict3须3方法、6子例Assertion RED/0Eskip，原因是实际500门而非缺函数/ERROR。
- [ ] 原关联三方法预期仍3Assertion RED：两次真实882预算、G因新strict3尚未进实际CI的清单差分。这是显式待C/D，不可吞失败称全绿；先记录原b233三回归与迁移后原因。
- [ ] A/B/E/F/G字节/AST/完整diff/inverse/七维及实际TEST独审通过后冻结。所有原12断言/8标签/500/≤9/完整mapping及五gate保留，不改测试补绿。

### Task2 — 不同SOURCE作者仅C
**Dependencies:** Task1与实际TEST审查通过
**Parallelizable:** No（冻结TEST之后）
- [ ] 重新核E后的Reviewer9438L/7bc559…及其它冻结输入；仅apply_patch C三hunks。
- [ ] strict3与strict12须3+12GREEN/0F/E/skip；关联三中前两须GREEN，G仍且仅因D未落而清单Assertion RED，不能称全部关联已通过。
- [ ] lower _workflow_notice函数逐字无差分；upper原编码/500断言不变；三确切label仅CI普通日志，任意相似label仍Actions；完整字段/原停序/首错误/DENY/同profile/token不变。
- [ ] 完整diff/AST/输出hash/inverse/自SPEC→自QUALITY/七维后，root fresh actual SPEC→不同QUALITY；原生与CI验收尚未完成。

### Task3 — 不同CI作者仅D
**Dependencies:** Task2及实际SPEC→不同QUALITY通过
**Parallelizable:** No（SOURCE验收之后）
- [ ] 核原CI2506L/29a7b8…，apply_patch D一个hunk；保留原strict12与其它所有job/matrix/25min/staging/helperhash/ACL/门。
- [ ] 新增strict3 count3；原五gate顺序/次数与strict12命令不改。重跑关联三须3GREEN/0F/E/skip（G由显式待D转GREEN）。
- [ ] 检查命令/YAML/唯一投影inverse/实际diff；原strict3/12已通过未变不无故重复。必要本机secrets/pin及root独审后才能发候选。

### Task4 — 仅root同新SHA双Windows在线门
**Dependencies:** Task3及实际审查/必要本机检查通过
**Parallelizable:** No（单候选后观察现有CI）
- [ ] root使用既有main-only待验候选授权，精确仅已批准路径，不混他人dirty、不新branch/tag；本文不扩大权限。
- [ ] 绑定candidate/run/job/attempt/platform/原始日志/退出。Linux strict3/12及full其它门保留实际结果；原full允许的平台skip如实计账，新strict3/12须0skip。
- [ ] x64/ARM64各记录三个完整普通日志、每条≤500及实际status/cleanup/reap/token绑定；原Actions8/WFP/runner槽位及原positive/candidate/footer/exit保持。helper两hash只文件观察。
- [ ] 预算修复成功但旧positive105/Reviewer78或其它门失败时，报告仍失败，不称R3/网络/发布通过；unknown/缺post不授原生观察成功。不取消/反复重跑刷绿，阶段充分通过后才继续后续阶段。

## 5. 匿名软件诊断与自审

本轮仅新PLAN落盘，无实际TEST/SOURCE/CI/Git变更。最终 `ae0840`（最终E清空helper前，其余最终资产）：新3旧语义3方法/6子例Assertion RED，0Eskip/.236s；投影3GREEN/.200s；原12GREEN/.651s；原关联3GREEN/5.214s，驱动exit0。E追加软件fixture清空helper后只重跑必要关联3：`1721ea` 3GREEN/0F/E/skip/5.187s/exit0；不重复未变的新3/旧12。所有这些是RAM投影，不替正式TDD或native。

实际b233三关联 `04d401` 3F/1.058s与根日志数字如§1。此前 `c0c9ca` 旧12仅TEST seam投影仍旧Reviewer为12GREEN/.962s；最大complete pre417/post418，实际protocol_error unknown pre422/post423。匿名新fixture旧组合最大887/unknown884，不混记线上865或旧static882。早期命令长度限制未启动；诊断驱动误要求fixture=线上865已纠正；`91a75c` 一次私有映射草稿仍查人类notice标题而非新普通前缀，单关联失败，已改F为实际三个prefix；这些不是产品新增故障或正式TDD。

`eed372`与最终E `409c2f`：所有资产/投影/inverse/AST通过，C后lower函数逐字相等；最终E两阶段Reviewer hash如表。六patch12hunks唯一正反；原输入/边界未写。普通loopback日志无Actions转义需求，旧Actions%/CR/LF路径实际测试保持，不把日志称annotations。

self SPEC已逐项映射完整A–G与Task1–4，原3关联待C/D的中间RED显式，不将未通过隐藏。self QUALITY在SPEC后核真实serializer/路由/静态fixture/完整mapping/唯一输出，原测试计数与500/≤9不弱化；这不替root独立双审。

## 6. 【架构级自检报告】

- ✅ 语法/编译：五Python资产AST与匿名定点投影通过；未作Windows SDK/PowerShell原生验证。
- ✅ 依赖/调用链：真实producer→JSON500→固定stdout或原Actions消费者完整；原监听finally清理已读且必要单方法实际软件通过。
- ✅ 逻辑/边界：最大完整字段/unknown/phase/stop/首错/500拒绝/非CI/任意标题/原转义及九槽断言保留。
- ✅ 异常处理：原首错误与停止恢复，无截断/drop/未知授成功；G中间待D失败明列。
- ✅ 关联模块：A–G、六实施路径、两阶段Reviewer输入与12hunks完整；产品/native/父脚本/CMake/vendor不改。
- ✅ 兼容安全：原12方法/断言、8标签、全部mapping、原五gate及strict12保留，无新权限/Set/豁免/connect。
- ✅ 可运行性：软件匿名3+12+原3通过；正式TDD/实际双审/同新SHA原生未验，不称100%或完整R3通过。

以下全部冻结资产，不能据此提前实施。

## Asset A: tests/test_windows_loopback_notice_budget.py

```python
"""Real loopback producer/Actions notice budget; software only, no OS APIs."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_windows_loopback_config_observation as original

ROOT = Path(__file__).resolve().parents[1]
REVIEWER = ROOT / "tests/test_windows_appcontainer.py"
PARENT = ROOT / "scripts/run_windows_appcontainer_read_probe.py"


def actual_functions(path, names, *, class_name=None):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = tree.body
    if class_name is not None:
        body = next(node.body for node in body if isinstance(node, ast.ClassDef)
                    and node.name == class_name)
    selected = [node for node in body if isinstance(node, ast.FunctionDef)
                and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("actual notice/comparison functions missing")
    future = ast.ImportFrom(module="__future__",
                            names=[ast.alias(name="annotations")], level=0)
    namespace = dict(json=json, os=os)
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[future, *selected], type_ignores=[])), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


class TestPositiveLoopbackNoticeBudget(unittest.TestCase):
    def setUp(self):
        methods = actual_functions(REVIEWER, {
            "_workflow_notice", "_workflow_json_notice",
        }, class_name="TestWindowsAppContainer")
        case = type("ActualNoticeCase", (unittest.TestCase,), methods)
        self.consumer = case()
        self.parent = actual_functions(PARENT, {
            "_positive_loopback_unknown", "_positive_loopback_comparison",
        })

    def unknown(self, phase):
        return self.parent["_positive_loopback_unknown"](phase, "protocol_error")

    def drive(self, factory, **options):
        harness = original.TestPositiveLoopbackConfig()
        output = io.StringIO()
        with patch.object(original, "sample", side_effect=factory), \
                patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                contextlib.redirect_stdout(output):
            outcome = harness.execute_positive(
                json_notice=self.consumer._workflow_json_notice,
                comparison=self.parent["_positive_loopback_comparison"],
                unknown=self.parent["_positive_loopback_unknown"],
                **options,
            )
        frames = []
        for line in output.getvalue().splitlines():
            if line.startswith("positive_loopback_config_"):
                prefix, decoded = line.split("=", 1)
                name = {
                    "positive_loopback_config_pre": "Windows positive loopback configuration pre",
                    "positive_loopback_config_post": "Windows positive loopback configuration post",
                    "positive_loopback_config_comparison": "Windows positive loopback configuration comparison",
                }[prefix]
            else:
                self.assertTrue(line.startswith("::notice title=R2.3 "))
                name, encoded = line[len("::notice title=R2.3 "):].split("::", 1)
                decoded = encoded.replace("%0A", "\n").replace("%0D", "\r").replace("%25", "%")
            self.assertLessEqual(len(decoded), 500)
            detail = json.loads(decoded)
            self.assertEqual(decoded, json.dumps(detail, ensure_ascii=True, separators=(",", ":")))
            frames.append((name, detail))
        return outcome, frames

    def assert_samples(self, frames, pre, post, comparison):
        expected = [
            ("Windows positive loopback configuration pre", pre),
            ("Windows positive loopback configuration post", post),
            ("Windows positive loopback configuration comparison", {"comparison": comparison}),
        ]
        self.assertEqual(frames[:3], expected)
        self.assertEqual(set(frames[0][1]), set(pre))
        self.assertEqual(set(frames[1][1]), set(post))

    def test_complete_and_unknown_use_actual_producer_consumer_without_loss(self):
        # Snapshot before patching original.sample to avoid recursive fixture calls.
        base = original.sample
        def maximum(phase):
            return dict(base(phase), entry_count=4096, target_match=True,
                        target_attributes=0xFFFFFFFF, sid_frees_attempted=4096,
                        sid_frees_confirmed=4096, array_release="confirmed")
        for factory, comparison in ((maximum, "consistent_endpoints"),
                                    (self.unknown, "unknown")):
            with self.subTest(comparison=comparison):
                expected_pre, expected_post = factory("pre"), factory("post")
                result, frames = self.drive(factory)
                self.assertIsNone(result.failure)
                self.assertEqual(result.events, ["pre", "launch", "post"])
                self.assertEqual(result.observed, [(original.PROFILE, "pre"),
                                                   (original.PROFILE, "post")])
                self.assertEqual(len(frames), 3)
                self.assert_samples(frames, expected_pre, expected_post, comparison)

    def test_unreaped_stops_and_original_errors_keep_full_samples(self):
        for options, events, failure in (
            ({"pre_stop": True}, ["pre"], "pre helper was not reaped"),
            ({"post_stop": True}, ["pre", "launch", "post"], "post helper was not reaped"),
            ({"clean": False}, ["pre", "launch"], "original-first"),
            ({"launch_error": True}, ["pre", "launch"], "OSError"),
        ):
            with self.subTest(options=options):
                result, frames = self.drive(self.unknown, **options)
                self.assertEqual(result.events, events)
                self.assertIsNotNone(result.failure)
                self.assertIn(failure, result.failure)
                post = self.unknown("post") if "post" in events else \
                    self.parent["_positive_loopback_unknown"]("post", "not_attempted")
                self.assert_samples(frames, self.unknown("pre"), post, "unknown")
                if options.get("post_stop"):
                    self.assertEqual(frames[3:], [
                        ("Windows private-network first result preserved",
                         {"executed": True, "exit": 105, "cleanup": True}),
                    ])
                else:
                    self.assertEqual(len(frames), 3)

    def test_actual_notice_guard_and_actions_escaping_remain_enforced(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                contextlib.redirect_stdout(output):
            self.consumer._workflow_json_notice("encoding", {"text": "%\r\n汉"})
            self.consumer._workflow_notice("raw encoding", "%\r\n")
            with self.assertRaisesRegex(AssertionError, "would be silently truncated"):
                self.consumer._workflow_json_notice(
                    "Windows positive loopback configuration pre", {"text": "X" * 500})
            self.consumer._workflow_json_notice(
                "Windows positive loopback configuration arbitrary", {"text": "%"})
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                contextlib.redirect_stdout(output):
            for phase in ("pre", "post", "comparison"):
                self.consumer._workflow_json_notice(
                    "Windows positive loopback configuration " + phase, {"value": 1})
        self.assertEqual(output.getvalue().splitlines(), [
            '::notice title=R2.3 encoding::{"text":"%25\\r\\n\\u6c49"}',
            "::notice title=R2.3 raw encoding::%25%0D%0A",
            '::notice title=R2.3 Windows positive loopback configuration arbitrary::{"text":"%25"}',
        ])


if __name__ == "__main__":
    unittest.main()
```

## Asset B: tests/test_windows_loopback_config_observation.py

```diff
*** Begin Patch
*** Update File: tests/test_windows_loopback_config_observation.py
@@
-    def execute_positive(self, *, pre_stop=False, post_stop=False, clean=True, launch_error=False):
+    def execute_positive(self, *, pre_stop=False, post_stop=False, clean=True, launch_error=False,
+                         json_notice=None, comparison=None, unknown=None):
@@
-            _positive_loopback_unknown=lambda phase,status:dict(sample(phase),status=status),
-            _positive_loopback_comparison=lambda pre,post,**kwargs:{"comparison":"unknown"},
+            _positive_loopback_unknown=(unknown if unknown is not None else
+                lambda phase,status:dict(sample(phase),status=status)),
+            _positive_loopback_comparison=(comparison if comparison is not None else
+                lambda pre,post,**kwargs:{"comparison":"unknown"}),
@@
-            self=N(_workflow_json_notice=lambda *args:notices.append(args),fail=self.fail))
+            self=N(_workflow_json_notice=(json_notice if json_notice is not None else
+                lambda *args:notices.append(args)),fail=self.fail))
*** End Patch
```

## Asset C: tests/test_windows_appcontainer.py — SOURCE

```diff
*** Begin Patch
*** Update File: tests/test_windows_appcontainer.py
@@
-        self._workflow_notice(name, encoded)
+        loopback_logs = {
+            "Windows positive loopback configuration pre": "positive_loopback_config_pre=",
+            "Windows positive loopback configuration post": "positive_loopback_config_post=",
+            "Windows positive loopback configuration comparison": "positive_loopback_config_comparison=",
+        }
+        if name in loopback_logs:
+            if os.environ.get("GITHUB_ACTIONS") == "true":
+                print(loopback_logs[name] + encoded, flush=True)
+            return
+        self._workflow_notice(name, encoded)
@@
-                    self._workflow_json_notice("Windows positive loopback configuration", {
-                        "pre": loopback_pre,
-                        "post": _positive_loopback_unknown("post", "not_attempted"),
-                        "comparison": "unknown",
-                    })
+                    self._workflow_json_notice(
+                        "Windows positive loopback configuration pre", loopback_pre,
+                    )
+                    self._workflow_json_notice(
+                        "Windows positive loopback configuration post",
+                        _positive_loopback_unknown("post", "not_attempted"),
+                    )
+                    self._workflow_json_notice(
+                        "Windows positive loopback configuration comparison",
+                        {"comparison": "unknown"},
+                    )
@@
-                self._workflow_json_notice(
-                    "Windows positive loopback configuration",
-                    _positive_loopback_comparison(
-                        loopback_pre, loopback_post,
-                        same_parent_profile=(loopback_profile == capability_profile_name),
-                        token_receipt=capability_control.child_token_receipt,
-                    ),
-                )
+                self._workflow_json_notice(
+                    "Windows positive loopback configuration pre", loopback_pre,
+                )
+                self._workflow_json_notice(
+                    "Windows positive loopback configuration post", loopback_post,
+                )
+                self._workflow_json_notice(
+                    "Windows positive loopback configuration comparison",
+                    {"comparison": _positive_loopback_comparison(
+                        loopback_pre, loopback_post,
+                        same_parent_profile=(loopback_profile == capability_profile_name),
+                        token_receipt=capability_control.child_token_receipt,
+                    )["comparison"]},
+                )
*** End Patch
```

## Asset D: .github/workflows/ci.yml

```diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@
-      - name: Compile Python sources
-        run: python -m compileall -q src tests scripts
+      - name: Strict positive loopback notice budget software contract
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_notice_budget.py'); assert s.countTestCases()==3, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
+      - name: Compile Python sources
+        run: python -m compileall -q src tests scripts
*** End Patch
```

## Asset E: tests/test_windows_appcontainer.py — TEST迁移

```diff
*** Begin Patch
*** Update File: tests/test_windows_appcontainer.py
@@
-            def _workflow_json_notice(
-                self, name: str, detail: dict[str, object],
-            ) -> None:
-                encoded = json.dumps(detail, ensure_ascii=True, separators=(",", ":"))
-                if len(encoded) > 500:
-                    raise AssertionError(
-                        f"native Reviewer probe notice exceeds GitHub limit: "
-                        f"{name} ({len(encoded)} bytes)",
-                    )
-                captured_notices.append((name, encoded))
+            def assertLessEqual(self, first: object, second: object, msg: str = "") -> None:
+                unittest.TestCase().assertLessEqual(first, second, msg)
+
+            def _workflow_notice(self, name: str, encoded: str) -> None:
+                TestWindowsAppContainer._workflow_notice(self, name, encoded)
+                captured_notices.append((name, encoded))
+
+            _workflow_json_notice = TestWindowsAppContainer._workflow_json_notice
@@
-                        "RUNNER_OS": "Windows",
-                        "RUNNER_TEMP": str(runner_temp_root),
+                        "RUNNER_OS": "Windows",
+                        "ICODE_DIAGNOSTIC_WFP_PROBE_PATH": "",
+                        "RUNNER_TEMP": str(runner_temp_root),
@@
-        self.assertIn("Windows Reviewer write canary fingerprints", notice_names)
-        self.assertTrue(all(len(encoded) <= 500 for _name, encoded in captured_notices))
+        self.assertIn("Windows Reviewer write canary fingerprints", notice_names)
+        loopback_lines = [
+            line for line in wfp_output.getvalue().splitlines()
+            if line.startswith("positive_loopback_config_")
+        ]
+        self.assertTrue(all(len(line.split("=", 1)[1]) <= 500 for line in loopback_lines))
+        self.assertEqual([
+            (line.split("=", 1)[0], json.loads(line.split("=", 1)[1]))
+            for line in loopback_lines
+        ], [
+            ("positive_loopback_config_pre",
+             _positive_loopback_unknown("pre", "not_attempted")),
+            ("positive_loopback_config_post",
+             _positive_loopback_unknown("post", "not_attempted")),
+            ("positive_loopback_config_comparison", {"comparison": "unknown"}),
+        ])
+        self.assertTrue(all(len(encoded) <= 500 for _name, encoded in captured_notices))
*** End Patch
```

## Asset F: tests/test_windows_private_connect_diagnostic.py

```diff
*** Begin Patch
*** Update File: tests/test_windows_private_connect_diagnostic.py
@@
-        self.assertIn("for code in windows_job_module._PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES", source)
+        self.assertIn("for code in windows_job_module._PRIVATE_NETWORK_CAPABILITY_EXIT_STAGES", source)
+        for label in (
+            "positive_loopback_config_pre",
+            "positive_loopback_config_post",
+            "positive_loopback_config_comparison",
+        ):
+            self.assertIn(label, source)
*** End Patch
```

## Asset G: tests/test_full_suite_ci_budget.py

```diff
*** Begin Patch
*** Update File: tests/test_full_suite_ci_budget.py
@@
-            'python -m pip install "setuptools>=80"',
-            "python -m compileall -q src tests scripts",
+            'python -m pip install "setuptools>=80"',
+            "python -B -c \"import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_config_observation.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))\"",
+            "python -B -c \"import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_notice_budget.py'); assert s.countTestCases()==3, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))\"",
+            "python -m compileall -q src tests scripts",
*** End Patch
```

---
**Execution Mode:** serial。PLAN ONLY覆盖技能自动执行；停止等待root全文与fresh SPEC→不同QUALITY，不落TEST/SOURCE/CI。
