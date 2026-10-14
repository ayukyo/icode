# Candidate Inspection CI Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 候选源码、provider TEST 和候选 workflow 的 main push 同时触发原 inspection 完整软件门，新增三方法防回归配置测试。

**Architecture:** 复用现有两个 workflow；原 inspection 仅追加四条精确 paths，candidate 仅追加一个严格运行新测试的 step。测试只读取当前固定缩进的 push paths 区间，直接检查字面条目，不实现 GitHub glob/YAML 框架。

**Tech Stack:** Python 3.10 标准库 unittest、pathlib、tempfile、re；现有 GitHub Actions。无新依赖或权限。

---

起草状态：PLAN ONLY，起草作者只新增本文，没有实施或触发 CI。后续执行状态见下节；原批准资产不变。
执行工作区 `/home/orbbec/projects/icode-skill`；本计划在 Agent `/home/orbbec/projects/icode/docs/nbl/plans/`。
用户既有 main-only、线上优先授权覆盖技能新分支/worktree和逐任务提交建议；本作者只计划，交 root 全文阅读及 fresh SPEC→不同 QUALITY 后才实施。
本计划采用 writing-plans/TDD；root 已记录实际 sequential-thinking 三步 `04cb4f`（覆盖缺口→复用 path fix→TDD 与不削弱门）。

## 2026-10-14 执行记录（非整体验收）

- 原批准计划 SHA256 `37e79750197baf28661fab315e7f29917fc842ba99efbe5a6a28ffa755edfea5` 已由 root 全文读取、fresh SPEC→不同 QUALITY 均 C0/I0/M0。以下为执行后追加，不冒称当前文档仍为原 hash；附录完整资产保持原样。
- 独立 TEST 作者仅新增附录A字节；root d1f0cf正式三方法运行得到3个缺路径 AssertionError、0ERROR/skip、exit1。不同 SOURCE 作者root才应用附录B两 workflow补丁。
- root 2fb47b实际三方法/.005s/OK，四次真实临时删除及外区注释负控执行；57895c原provider20/1.724s/OK、0skip。3ebc28逆消除新增四路径/两行step逐字节还原原workflow；SOURCE/provider TEST未变。实际fresh SPEC→不同QUALITY均C0/I0/M0，并各自定点运行三方法通过。
- 精确三个计划路径另加独立一行site fixture修正，形成 Skill待验候选 `02f419d449f3ba9ba87717a928f740b6ce17e327`，父96b89798。site仅补上游fixture已有两resources的unsafe预期，真实单项RED→完整23项GREEN，单独审查通过，checker不动。root精确索引/密钥模式检查后commit283b68、push6e2a2e/exit0，main-only，无新增branch/tag或固定pin变更。
- 同SHA自动触发 inspection38554148379、candidate38554148462、site38554148568，首次均in_progress/attempt1。此前96的Windows legacy16失败、父generic3失败尚未修，必须保留并诊断。线上全门、C1整体、R2/R3与最终pin验收仍未通过；Task3线上部分未勾选。

## 基线、三问和证据边界

观察日期 2026-10-14；实际 Skill HEAD `96b89798d4aa45f2fb03d6dd9c27982e26a625b7`。
root 提供该 main 已 push；parents 为 `8b3d678cfdd7b6a51bef127663c11340c6e5944a` 与 `b9696c6f49b4b09cf136bd9ce6c804576a23ae2a`，共同 base `5be`。
root 已独立逐字节/模式核 3+44=47 无重叠并集，独立整合审查 0 发现；这里不重复整合或赋予线上通过信用。
真实问题：原 inspection 的 push paths 缺少三个新候选资产路径；原 jobs 因而不会由这些变动自动触发。
已有实现：原 inspection 含软件 162 legacy/Windows 诊断及 generic-verification MCP；新 candidate 含 provider20、五组 related legacy、两 shell，不能互相替代。
调用链：main push→两个路径过滤器→各自 Ubuntu/Windows matrix；修复不触碰候选算法/provider API/host 绑定。

已完整读取两个实际 workflow；并核批准 C1 计划 Task4 与附录C 必要 CI 段：
`/home/orbbec/icode-frozen-c1-d23e230/approved-plan.md` SHA256 `d23e2302c1e61ea05cd8ab8a5f40d71f44cc5cc0bf87417660cd5ffc5a51944b`。
本片补足原计划要求的原兼容门，不修改其生产 SOURCE 或已冻结 provider TEST。

| 资产 | 当前 SHA256；实施前必须重核 |
|---|---|
| `tools/icode_candidate.py` | `12542f3b2bdccb6964433c20ed9f8ac0142c392027b52c0b5924e1421d742481` |
| `tests/test_candidate_git_provider_unit.py` | `ab598698e245dcaa3b0c61c877debe156863ef4a53492a8e1c82ab63c5b77173` |
| `.github/workflows/inspection-software.yml` | `1f0d60edeb97057d883cf7c5946663526f066f13cc98df14d111fefd4254501f` |
| `.github/workflows/candidate-provider-software.yml` | `d9792f352bdf06762477142a76028cd755cbaad55f296b66c9568764485ec5b5` |

Agent vendor pin `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` 不动。96 的自动 CI 继续观察；不取消、重跑或借旧 SHA 结果。
两个 workflow 都保持 `${{ github.sha }}` concurrency 与 `cancel-in-progress: false`，新候选不会抢停旧证据。

研究：这是已确认的 CI 配置小修，不启动新竞品 Agent 研究；复用 GitHub 官方现有机制。
2026-10-14 核对 [GitHub workflow syntax / paths](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)：branch 与 path 过滤均需满足，paths 中存在匹配变更才启动。
采纳：main 分支与四条字面路径，收益为原完整门恢复自动覆盖，成本为相关变更多跑原既有 jobs；无复制代码/许可新增/权限扩大。
暂缓：通用 glob/YAML 解析器、全仓触发；不适配：manual dispatch 代自动覆盖、缩减旧门、凭旧 SHA 宣称通过。
验收：旧配置真实 3 AssertionError RED，新配置真实 3 GREEN，两个 workflow 同一新 SHA 完整线上门均通过。

## Task 1: 独立 TEST 作者先取得真实 RED

**Dependencies:** None
**Parallelizable:** No（先计划双审；TEST 作者不同于 Task2 workflow 作者）

- [ ] 核 main/HEAD/上表 hashes 与工作树；漂移只读比较后重新冻结，不 reset/清理用户状态。
- [ ] 通过 apply_patch 仅创建 `tests/test_candidate_workflow_triggers.py`，完整内容见附录A；原两个 workflow 原样。
- [ ] 在 Skill 根运行以下命令，保存 cwd、HEAD、TEST/CI hashes、完整 stdout/stderr、退出状态。

```bash
python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_workflow_triggers.py'); assert s.countTestCases()==3; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
```

- [ ] 预期旧真实配置 `Ran 3 tests`、`FAILED (failures=3)`、exit1、errors=0/skipped=0；每个失败是缺对应 exact path 的 AssertionError。缺文件/import/区间标识错误不算 RED，先修 fixture 再双审。
- [ ] 正控必须保留既有 `tools/inspection_worklist.py`；新测试自身触发归入 source 方法，仍只有三方法。GREEN 时各方法真实临时副本删除其目标行、在区间外追加同名注释，必须仍拒绝该路径；不能全文 grep 通过。
- [ ] 冻结 TEST 字节，交不同 Task2 作者；不改 provider20、不做本机旧全集或 Windows20。

## Task 2: 不同 workflow 作者应用两处最小补丁

**Dependencies:** Task 1
**Parallelizable:** No（真实 RED 与冻结 TEST 后才应用）

- [ ] 确认附录B两个 hunk 的原文上下文各唯一匹配，完整阅读两个 workflow，apply_patch 仅改这两文件。
- [ ] 再执行 Task1 严格 runner，预期三方法 GREEN、0 failures/errors/skips、exit0；再定点 provider20：

```bash
python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_git_provider_unit.py'); assert s.countTestCases()==20; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
git diff --check
git diff -- .github/workflows/inspection-software.yml .github/workflows/candidate-provider-software.yml tests/test_candidate_workflow_triggers.py
```

- [ ] 差分保护：inspection 删除恰好四个新增 literal 行后必须逐字节等于表中原文件；candidate 删除恰好新增 name/run 两行后必须逐字节等于原文件。逆向各一次并核原 SHA，任何额外改动拒绝。
- [ ] 旧 paths 全保留；两文件 `permissions: contents: read`、checkout/setup pin、所有 jobs/矩阵/env/timeout/命令/步骤均原样。原 generic10/software15/candidate20 分钟及 Windows诊断1分钟不变。
- [ ] 只做必要定点、静态 AST/三方法计数、密钥规则扫描、固定 pin/manifest 完整性和 diff；不默认本机 full/原生/模型，不读凭据内容或 root secret store。

## Task 3: fresh 双审、main 候选及同 SHA 线上闭环

**Dependencies:** Task 2
**Parallelizable:** No（实际实现经 SPEC→不同 QUALITY，root 精确索引后推送）

- [ ] fresh SPEC 审实际新TEST与两个 workflow；不同 QUALITY 重核 Task2 差分冻结、真实 RED/GREEN、完整不削弱原门；发现先修再刷新 hashes/审查。
- [ ] root 按用户既有授权在 main 精确 stage 这三个路径；核暂存 bytes=已审资产，不用 add .、额外分支/tag、force/reset/rebase，也不纳入无关 dirty 文件。提交新的待验收候选并 push main。
- [ ] 绑定新完整 SHA、push 事件、workflow/run/job ID、平台、完整原始日志与 exit；两个 workflow 均须自动触发，不用 dispatch 补假覆盖。
- [ ] inspection Ubuntu/Windows 的 software 与 generic-verification 全必要步骤通过，包括原 provider/兼容 unittest、原162完整收集与执行、Windows诊断、MCP/路径/报告回归、route校验、Linux distribution/shell。
- [ ] candidate Ubuntu/Windows 新配置3、既有 provider20、语法、五组 related legacy 完整收集与执行及 Linux shell 全通过。记录实际 collection/count，失败/skip/0收集/缺 job 不折绿，不以新门替旧门。
- [ ] 原96与新候选证据分开保存；旧失败按原日志诊断，不取消/反复重跑隐去。仅新候选上述全部必要门通过才关闭本片软件覆盖；不授 C1整体、真实host/native、R2/R3或 Agentpin 升级信用。

## 附录 A: 完整新 TEST 资产

目标 Skill `tests/test_candidate_workflow_triggers.py`（本作者只嵌入文本，不创建该文件）：

```python
"""Keep candidate changes covered by the existing inspection workflow."""
from pathlib import Path
import re
import tempfile
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/inspection-software.yml"
START = "on:\n  push:\n    branches: [main]\n    paths:\n"
END = "  workflow_dispatch:\n"


def push_paths(text):
    # Deliberately bounded to this workflow's current literal-list layout.
    if text.count(START) != 1 or text.count(END) != 1:
        raise AssertionError("inspection push paths boundaries changed")
    before, body = text.split(START)
    paths, after = body.split(END)
    values = []
    for line in paths.splitlines():
        match = re.fullmatch(r"      - (['\"])(.+)\1", line)
        if match is None:
            raise AssertionError("unexpected push paths item: " + repr(line))
        values.append(match.group(2))
    if not values or len(values) != len(set(values)):
        raise AssertionError("empty or duplicate push paths")
    return values


class CandidateWorkflowTriggers(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def assert_trigger(self, target):
        paths = push_paths(self.text)
        self.assertIn("tools/inspection_worklist.py", paths)
        self.assertIn(target, paths)
        # A real temporary copy must reject a removed item, even with its comment.
        item = "      - '" + target + "'\n"
        self.assertEqual(self.text.count(item), 1)
        changed = self.text.replace(item, "", 1) + "\n# " + target + "\n"
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "inspection-software.yml"
            copy.write_text(changed, encoding="utf-8")
            self.assertNotIn(target, push_paths(copy.read_text(encoding="utf-8")))

    def test_candidate_source_triggers_inspection(self):
        self.assert_trigger("tools/icode_candidate.py")
        self.assert_trigger("tests/test_candidate_workflow_triggers.py")

    def test_candidate_provider_test_triggers_inspection(self):
        self.assert_trigger("tests/test_candidate_git_provider_unit.py")

    def test_candidate_workflow_triggers_inspection(self):
        self.assert_trigger(".github/workflows/candidate-provider-software.yml")


if __name__ == "__main__":
    unittest.main()
```

## 附录 B: 完整两 workflow 最小 patch

```diff
diff --git a/.github/workflows/inspection-software.yml b/.github/workflows/inspection-software.yml
--- a/.github/workflows/inspection-software.yml
+++ b/.github/workflows/inspection-software.yml
@@ -34,3 +34,7 @@
       - 'tests/inspection_windows_diagnostic.py'
       - '.github/workflows/inspection-software.yml'
+      - 'tools/icode_candidate.py'
+      - 'tests/test_candidate_git_provider_unit.py'
+      - '.github/workflows/candidate-provider-software.yml'
+      - 'tests/test_candidate_workflow_triggers.py'
   workflow_dispatch:
diff --git a/.github/workflows/candidate-provider-software.yml b/.github/workflows/candidate-provider-software.yml
--- a/.github/workflows/candidate-provider-software.yml
+++ b/.github/workflows/candidate-provider-software.yml
@@ -46,3 +46,5 @@
           sudo apt-get update
           sudo apt-get install --no-install-recommends -y ripgrep
+      - name: Candidate inspection trigger contract
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_workflow_triggers.py'); assert s.countTestCases()==3; r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Typed candidate stdlib contract
```

## 静态自审与交付界限

计划作者只对本文嵌入资产做 AST/三方法、hunk唯一匹配与逆差分冻结检查，不执行 TEST，不把静态检查写作真实 RED/GREEN。
静态冻结：附录A 为59行/3方法，SHA256 `79cb54114e63de4e773d413dfb6d47b4775bf847b53679d1fd2fa87d54f9ef2e`；附录B 两块原文各唯一匹配，逆差分逐字节保持原文件。
内存重建 inspection SHA256 `20ba94d78ba71df79fa73b2f58231d9fac6d3dd37f06befa963161f5be660247`，candidate SHA256 `78dc0f5763469b56bb72635fb09b8327dd9e9b73c1bccf93f7b27ebb73d373e8`；未写回仓库。
实施时 Task1/2 的真实运行和 Task3 线上同 SHA 日志不可省略；三方法配置测试只保护触发边界，原门完整性由精确 diff/独立审查及真实线上共同保护。

【架构级自检报告】

- 语法/编译：嵌入 Python AST 与 patch 结构静态核；未运行或编译生产代码。
- 依赖/调用链：三个变更路径与自触发路径关联原 workflow，现 candidate glob 已覆盖新TEST。
- 逻辑/边界：固定 push 区间、exact item、已有path正控与临时副本删除/区间外注释负控；不模拟一般 glob。
- 异常处理：缺配置/标识变化不折绿，真实 RED 只认三 AssertionError，runner 拒绝失败/错误/skip/计数漂移。
- 关联模块：仅本文落地；未来精确三路径，生产SOURCE/provider20/Agentpin均冻结。
- 兼容安全：保留原 paths/jobs/权限/预算/命令/actions/env，差分逆消除须等于原 bytes。
- 可运行性：只完成可执行资产静态自审，真实3/20与线上全门仍待实施；不宣称100%运行验收。

---
**Execution Mode:** serial

起草作者交付时按 PLAN ONLY 停止；随后 root 完成全文阅读、独立双审及不同 TEST/workflow 作者串行实施，实际执行和待验收状态以上方执行记录为准。保留原复选框作为起草任务清单，不将其未勾选状态解释为尚未落地。
