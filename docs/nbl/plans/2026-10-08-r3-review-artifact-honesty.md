# R3 审查产物真实性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development。main 原地开发；实施、SPEC、QUALITY独立。此片与Linux quota文件不重叠，测试与提交冻结仍串行。

**Goal:** 删除运行时伪造的审查正文与“无发现”轮记录，保留有来源的回复补落盘，并让机器manifest及时重新装配；修正首次进入review的事件顺序。

**Architecture:** 沿用ICODE-SKILL控制面、review契约及既有`post_write`。模型真实提交round才可装manifest；缺产物不finish成功、不前移。此片不移植`run_task`验证循环、不改预算/策略/attempt/operation/checkpoint所有权。

**Tech Stack:** Python3.11、unittest、现有FakeBackend与真实控制面离线夹具。

## 已确认的真实问题、复用和影响

基线main d65ecf8：`run_chain` review post生成占位`02_review.md`和默认空数组`review_round_1.json`，与模块“不编造”的约定冲突。`run_contract_step`真实回复补落盘之后没有重新调用post，可能遗漏manifest更新。已有`_persist_missing_from_response`支持来源标注、不覆盖现存文件、受控ArtifactBroker及无内容保持缺失，可直接复用。

固定上游review输出为`02_review.md`（ticket_file）、`review_manifest.json`（ticket_file）、`review_round_*.json`（ticket_glob）。当前回复补落盘不支持glob，此片不偷偷把自由JSON当成轮记录；已有测试的ticket_file JSON提取能力不等于上游glob能力。

独立研究及主代理回读vendor `b74c4c40f2246a6c4eea77e494dd57c642f3a9a3`（MIT）[合同](https://github.com/ayukyo/icode-skill/blob/b74c4c40f2246a6c4eea77e494dd57c642f3a9a3/mcp/workflow-gate/gates.json#L209-L221)与[校验实现](https://github.com/ayukyo/icode-skill/blob/b74c4c40f2246a6c4eea77e494dd57c642f3a9a3/tools/icode_control.py#L1562-L1670)：glob端口本身可选，但manifest必须非空，首轮即使零发现也必须有真实detail，并关联hash/数组计数/origin attempt及登记回执。缺round仍不能闭合manifest；这些关联也不证明模型理解或审查质量。

允许写：`src/icode/chain.py`、`src/icode/runner.py`、`tests/test_chain.py`、`tests/test_chain_offline.py`、必要的`tests/test_runner.py`。不修改Linux并行文件、vendor、控制面契约、模型KEY、CI权限、评分或自动模式。

## Task 1: 审查产物与补落盘顺序

**状态**
- [x] 任务完成

**Dependencies:** 上游契约与现有产物修复机制已读确认。
**Parallelizable:** Yes（仅与Linux片源码不交叠；最终门禁串行冻结）

- [x] **Step 1: 先测试RED**

真实调用`run_chain`的review post，缺正文/round时必须不创建占位正文、空round或manifest。真实`run_contract_step`离线链：缺正文与缺round分别不能成功前移。正例为模型已提交round，实质回复正文由既有来源通道补落盘后，post被再次调用，manifest和实际round/hash/attempt一致。保留已有正文不被回复补落盘覆盖。

至少覆盖：全部缺失、只有正文、只有真实round但回复不足、真实round＋可追溯正文补落盘、自由JSON但没有提交round、完整模型提交、已有正文保留、post异常固定失败。RED必须来自旧行为断言失败，不是缺import/API、主机条件或无效夹具。

- [x] **Step 2: 最小GREEN**

删除review post的两个默认写文件分支；仅调用既有`assemble_review_manifest`并记录其真实成功/缺失，缺round不能抛异常抢在合法正文补落盘前退出。保持现有manifest机器装配语义，不改round格式、命名、控制面规则。

`run_contract_step`在`persisted`非空后、重登记产物之前，再调用既有`post_write(out_dir,step,attempt)`。不调用额外模型、不伪造缺失内容、不绕过后续门禁。checkpoint不保存模型正文；operation recorder仍整步共用。post异常沿现有失败通道返回，不能finish成功。

- [x] **Step 3: 关联回归与20轮**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_chain tests.test_chain_offline tests.test_runner -v`。
新真实性矩阵冻结后20轮、0SKIP；记录测试方法数与真实失败/通过，不把FakeBackend离线语义称为真实模型质量验收。核对plan/merge/code/deepcheck/audit默认无post与有post行为，重放不覆盖既有正文、上游子模块不变。

- [x] **Step 4: 独立SPEC→QUALITY与提交**

两次独立只读复审，无遗留发现后，主代理冻结所有并行源码再运行完整preflight、governance/site/landscape及diff-check。单片精确文件commit/push main、核对remote；不依赖此前门禁或另一片的20轮。阶段报告保留R2/R3整体未验收。

## Task 2: 真实初入步骤的状态/attempt顺序

**状态**
- [x] 任务完成

**Dependencies:** Task1取得独立RED/GREEN；不把预进入review夹具的成功当初入生产链通过。
**Parallelizable:** No（同runner文件与实施者）

2026-10-08实施者实际离线正控发现`review_manifest:stale_review_run`，主代理回读固定vendor `cmd_transition`、`cmd_step`和`review_evidence_issues`确认：start没有要求尚未进入in_progress，review终结却要求origin start在最近review_in_progress事件之后。当前runner顺序反了。这是既有合同下的真实调用顺序缺陷，不是新需求。

- [x] **Step 1: 独立RED**

从真实合法review前一状态启动，不能预先转到review_in_progress，完整模型提交正文/round应finish成功。旧代码必须以真实`stale_review_run`拒绝；同时记录实际事件中错误的start→state_changed顺序。

- [x] **Step 2: 最小GREEN**

将现有`in_progress_status_for`与`cp.transition`块移到`cp.step_start`之前；显式确认transition返回ok，否则按固定步骤失败返回，不创建attempt/checkpoint/operation、不调用模型。其它身份/幂等键和所有契约复检保持原样。是否有中间状态只按真源派生：当前plan返回init_in_progress、merge/audit返回None；None才直接start，不按旧注释硬编码plan例外。不得改vendor或自行写metadata/events。

关联实际105方法首跑发现新建/复用plan已处于init_in_progress，真实同状态transition被state_machine拒绝，导致1FAIL/1ERROR（另5项原有平台SKIP）。最小兼容处理：新工单取成功create返回status，复用工单经控制面trace取得status；当前等于派生in_prog时记录已处于并直接start，否则必须先成功transition。trace失败/缺状态不能借假定绕过；不硬编码plan、不恢复忽略false。真实初入review依旧必须留下entry先于start事件。

- [x] **Step 3: 首入/拒绝/兼容验证**

真实初入review完整提交及round＋真实正文补落盘均成功，检查state_changed先于本次step_started与manifest origin/hash/回执。失败transition（抛异常及返回ok=false）均无step_start/模型调用；plan/init_in_progress、code/deepcheck及无中间状态merge/audit的关联调用顺序不退化；可另用明确None合同夹具检查通用边界，但不能称当前plan没有中间状态。两Task的新矩阵最终冻结统一20轮0SKIP、独立SPEC→QUALITY，最后整库门禁与推送。

另测真实新建/复用plan避免自流转的RED→GREEN，并重跑关联105方法。此前预进入review的Task1证明仅限真实性；首次关联兼容失败和中间GREEN不得充当最终冻结通过记录。

## 持续研究与下一片

2026-10-08独立只读核对Codex `1fbe15c962cc3d8eabec36d67987c83cfc4eeec9`（Apache-2.0）[exec事件](https://github.com/openai/codex/blob/1fbe15c962cc3d8eabec36d67987c83cfc4eeec9/codex-rs/exec/src/exec_events.rs#L23-L34)及[命令终态](https://github.com/openai/codex/blob/1fbe15c962cc3d8eabec36d67987c83cfc4eeec9/codex-rs/exec/src/exec_events.rs#L137-L154)。采纳消息/回合/命令完成与独立验证分离；收益是避免把模型停止或文件存在当质量证明，成本是缺真实证据必须停步。仅借机制，不复制代码；暂缓日志格式重构，不适配`item.completed`即通过。此片不改变工具/安装兼容合同。

后续才抽取共享验证执行核，保留实际step/CP attempt、policy、operation、checkpoint、artifact broker、共享预算，接入真实项目验证计划与只读Reviewer；再验真实模型1→6及不同非玩具工程。直接将`run_contract_step`替换为当前`run_task`会丢这些身份与治理，禁止这样接线。

## 冻结验证记录（2026-10-08；尚未提交）

Task1 旧行为真实 RED：12 方法中 10 失败、2 正控通过；Task2 初入 review 的失败来自真实控制面 `stale_review_run`。兼容修正后最终矩阵为 18 方法，固定四文件连续 20 轮，共 360 次通过、0 SKIP；关联链路/离线链/runner 为 107 方法通过、5 项既有平台 SKIP，不给跳过项通过信用。

主代理独立 SPEC 已完整回读修改上下文、实际控制面与来源校验调用链，并独立执行三个新测试类：18/18、28.964 秒、0 SKIP；另一名非实施者独立 QUALITY 同样实跑18/18、28.621秒、0 SKIP，两次审查无遗留阻断。冻结源码完整preflight三道门、compileall `-j6`、治理/官网/竞品/diff守护通过；源码包、重建wheel和干净安装八模块字节一致。待精确提交推送及新 SHA 在线验证后才关闭本片。

本记录绑定 `chain.py` SHA-256 `7e2f9dbb785e1318961e0e1060b09f0e9bb3bc8bdaa119d8ac4cc3e2a1217cc8`、`runner.py` `d673aadb7e8ba242edd94c940c33920261cf7e0e1a8e1f0f4df75040ad9d75e8`、`test_chain.py` `3531687c9ae96b69bb95841324e5c56682ea4db58b866ec1a079ee4ebd8d9289`、`test_chain_offline.py` `db72152ad1a8dbd07776d06d83a11acf1c4a657be4527709db84a8ff0ada4f12`。源码变化须重新验证，不能套用上述轮次。

真实 review 步骤 finish 成功不等于完整链 delivered；后续 `mcp_coverage` 门仍未闭合。这些离线测试不证明真实模型质量、完整1→6链或 R3 整体验收，也未更改 R2 隔离与自动模式 readiness。

两个无文件交叠分片共同冻结受测树后精确提交／推送main `be31b9895681e651737714f667d8ceb8e3a56f7d`，远端一致；不是两次独立单片提交。[主CI](https://github.com/ayukyo/icode/actions/runs/37736905277)Python3.11/3.12全仓各1959方法、OK/71 SKIP，主代理实读日志确认；整轮仍有两Windows Reviewer failure，不称整轮全绿。[provenance](https://github.com/ayukyo/icode/actions/runs/37736905233)四矩阵与[官网](https://github.com/ayukyo/icode/actions/runs/37736905248)成功仅关闭各自子门，不证明本片完整模型工作流。Task1/2仅在上述真实性与入口顺序范围关闭；下一片单循环预算门正在独立验收，共享验证核与全流程治理继续实施。

**Execution Mode:** parallel isolated files; acceptance serial
