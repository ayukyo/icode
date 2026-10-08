# R3 模型计费后预算终态门 Implementation Plan

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development；独立只读研究、SPEC、QUALITY。按用户授权直接 main，不新建分支；先完成正在冻结的 Linux 产品 quota / R3 真实性提交，不能让本片源码变化污染此前门禁。

**Goal:** 使用已有 BudgetTracker 在本次模型用量计入后阻止成功返回与后续工具副作用，不改变既有预算阈值或将成本当质量指标。

**Architecture:** 保留 AgentLoop、同一个 tracker、模型消息与回合记录、事件/检查点接口，新增 charge 后硬门。此片不解决 contract repair 重建预算或 SequentialThinking 未计费；它们属于下一片共享预算治理，不借本片宣布全工作流预算强制。

**Tech Stack:** Python3.11 stdlib、unittest、实际 AgentLoop 与明确 last_usage 的离线 backend。

## 三问与真实基线

1. 真实问题：独立研究者与主代理均实际复现。expected_tokens=100、默认 hard_ratio=3、本次 total_tokens=301 后，纯文本终态 `ok=True/no_tool_calls`，tracker 已 over_budget；写工具回复虽最终 budget_exceeded，仍已产生一次 operation start 与真实文件写入。
2. 已有实现：Budget.verdict 使用严格 `>`，expected_tokens<=0 是 observe_only；复用现有判断，不能复制新阈值或追加另一账本。
3. 调用链：AgentLoop 目前仅在模型调用之前检查，随后记录 last_usage，再返回纯文本成功或执行工具。影响实际工具副作用、required-tool 重试和末轮成功；runner/Reviewer 消费 loop 结果需关联回归。

模型调用已产生的费用无法追回，本片承诺仅为观测到超限后停止，不是预测性计费或绝不超支。无 last_usage 不补造用量，不据此宣称硬门覆盖。

## Task 1: 单循环计费后的拒绝与兼容

**状态**

- [ ] 任务完成

**Dependencies:** 当前冻结分片已精确提交推送；独立研究记录采纳/暂缓/不适配。
**Parallelizable:** No（单实施者，仅 loop 与关联测试；研究/审查只读）

允许编辑 `src/icode/loop.py`、`tests/test_loop.py` 与必要的既有 runner 关联测试。不得在此片改 runner/shared tracker API、budget阈值、backend usage协议、模型KEY、policy/score/自动模式或vendor。

- [x] **Step 1: 先做真实 RED**

使用真实 AgentLoop 与 FakeBackend 子类在每次 complete 设置明确 last_usage；断言首个纯文本超限回复不能成功；首个超限工具回复不能调用审批、operation start/finish、registry.invoke或写出 marker；最后允许回合也必须拒绝。失败来自旧行为放行，不是缺 API 或夹具异常。

补正负边界：300 在默认3倍阈值上仍允许、301拒绝；expected=0和负数保留 observe_only；累计99+202超限停止，同一个tracker不重置；required-tool模式不能在已超限后再重试模型。完整保留实际charged usage，不把预算失败伪装成backend错误或工具成功。

- [x] **Step 2: 最小 GREEN**

在记录本次 last_usage 后、成功返回/工具/required-tool 重试之前复检已有 verdict。真实 assistant 和未执行事实必须可追踪；工具跳过不是已执行或已完成，不能创建副作用回执。保持 turn/on_turn 历史可恢复性，不留下会被恢复流程当作已执行成功的悬空调用；沿既有明确未执行回执语义处理，不建立新协议。

返回固定 `budget_exceeded`、ok=false，保留原用量；不修改strict>与observe_only，也不改变调用前已经超限的拒绝。异常、max_turns、单回合工具上限、required-tool保留其它已有语义。

- [x] **Step 3: 冻结20轮及关联回归**

新矩阵最终摘要冻结后连续20轮、0SKIP，测试次数按方法实数记录。完整 `tests.test_loop`、预算/后端/runner/Reviewer关联；真实副作用 marker 和 operation/approval调用数量必须实证，不以 mock 包装命令代替实际 AgentLoop 调用。

- [ ] **Step 4: 独立审查与交付**

实施者不得自审代替独立 SPEC→QUALITY。无遗留发现后完整 preflight三门、compileall≤j6、治理/官网/竞品/diff检查。精确 commit/push main并核对远端；新SHA线上结果独立记录，不借上一SHA门禁。阶段后继续共享验证/预算核及 R2 未闭合项。

## 验收上限与研究

2026-10-08独立只读研究及主代理实际回读固定一手源码：PydanticAI `f55bb8a6fd6cdb34405e5f523d67cf8f366df4aa`（MIT）[计费后检查](https://github.com/pydantic/pydantic-ai/blob/f55bb8a6fd6cdb34405e5f523d67cf8f366df4aa/pydantic_ai_slim/pydantic_ai/_agent_graph.py#L1667-L1715)与[处理结果/工具入口](https://github.com/pydantic/pydantic-ai/blob/f55bb8a6fd6cdb34405e5f523d67cf8f366df4aa/pydantic_ai_slim/pydantic_ai/_agent_graph.py#L2041-L2117)，先记录实际usage、再限制检查、随后才形成工具节点；[token阈值](https://github.com/pydantic/pydantic-ai/blob/f55bb8a6fd6cdb34405e5f523d67cf8f366df4aa/pydantic_ai_slim/pydantic_ai/usage.py#L591-L605)使用严格`>`。采纳检查顺序、复用本仓tracker；代价仅额外一次verdict及未执行回执，不依赖SDK、不复制代码。

OpenHands SDK `69e26889401fe69157fff536e6a69049e6644cb3`（MIT）的[预算实现](https://github.com/OpenHands/software-agent-sdk/blob/69e26889401fe69157fff536e6a69049e6644cb3/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L720-L734)聚合多个LLM美元成本，但[step后检查](https://github.com/OpenHands/software-agent-sdk/blob/69e26889401fe69157fff536e6a69049e6644cb3/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L1993-L2022)对FINISHED有豁免。暂缓多LLM聚合机制至共享预算阶段，不适配照搬>=阈值或完成状态豁免。源码观察不是上游SDK动态测试，不构成ICODE验证证据。

此片不证明 contract step/repair/reasoning/Reviewer 的全流程共用账本，不证明模型质量或真实1→6链，不消除已经发生的费用。已有 contract step 对 loop失败的软提示可能仍让产物齐备的步骤前移；下一片必须明确区分可软化的回合上限与不可软化的预算硬拒绝，不在本片偷换完整工作流承诺。R2/R3 readiness维持未通过。

## 最终冻结证据（2026-10-08；待提交）

原8方法真实旧行为RED为7方法失败、8条断言失败及1兼容正控通过；最小修改后8/8转GREEN。独立SPEC又复现实际JSON非对象参数7、字符串及数组在预算拒绝分支转换时抛异常，破坏固定失败与配对历史。补新方法，在有效夹具上RAM恢复旧转换语句时三实际TypeError/ValueError仍RED；仅拒绝分支对dict保留副本、其它保留空参数，原JSON仍留真实assistant历史。正常执行路径与backend解析未改。

过程中误选不存在的`tests.test_budget`、新增夹具漏json导入以及中途被主动中断的旧完整守护，都不充当源码RED或最终通过。修正后绑定loop SHA-256 `1b3d9ddb17deabfe460c0ef0fa03a3d3f10a6307e4a3dd2b9d15a1af5cac3746`、test_loop `aa5e327178d478d6603a17ecddf3f11399f6108eefb4fddc2896fc1d18b34880`，最终9方法×20轮=180/180、0 SKIP、轮前后摘要相同。旧8×20=160和旧wheel不作最终证据。

正确关联为loop/reasoning_budget/runner/reviewer四模块：143方法，138通过、5既有平台SKIP，主代理7.143秒；独立SPEC9/9（.048秒）、关联143（7.091秒）与独立QUALITY9/9（.014秒）、关联143（7.051秒）均通过且摘要固定，无遗留发现。两审查者另独立接真实Checkpointer保存/加载非对象参数负控，摘要、计数及未执行配对正确，正文不落checkpoint；不借此证明跨进程budget恢复。

最终wheel干净venv仅pip安装，已安装loop字节匹配上述摘要；真实安装API完成末轮301拒绝、300边界正控、超限写工具无marker、非对象JSON固定失败及配对回执四类验收，不导入checkout模块。compileall `-j6`、治理/官网/竞品/diff守护通过；最终完整preflight于2026-10-08 06:36:49 UTC退出0，三门全部通过。提交/推送及远端核对仍待实际完成后记录，不提前关闭Step4。

**Execution Mode:** serial
