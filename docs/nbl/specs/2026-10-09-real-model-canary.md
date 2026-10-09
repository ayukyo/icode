# 真实模型靶场验证记录

日期：2026-10-09。密钥仅通过仓外路径传入，未读取、打印或提交；两次运行均使用临时 `pycalc` 副本和 bubblewrap 隔离。

## 结果

0. **修复后窄任务复验（2026-10-09）**：使用同一仓外密钥、MiniMax-M3、`https://api.minimaxi.com/v1` 与 bubblewrap 临时 `pycalc` 副本；需求明确要求通过 `edit_file`/`write_file` 修改，不把代码只写在回复中。主模型循环 12 回合/11 次工具调用，Reviewer 4 回合/4 次工具调用，共 16 次调用、69,484 tokens（prompt 63,306 / completion 6,178 / cached 52,094）。实际修改 `calc.py`、`test_calc.py`，独立 `python -B -m unittest` 执行 21 tests、退出码 0；Reviewer 精确读取两文件并提交结构化结果，最终通过。模型尝试的越界 `run_command` 仍被拒绝，未放宽工具或审批门。该样本证明当前窄 pycalc 任务的真模型→写入→独立测试→Reviewer 闭环可运行；不证明六阶段 1→6、跨平台原生隔离、90% 一致性或 R2/R3 总验收。临时工作区位于 `/tmp`，仓库无改动，密钥未打印、未复制、未进入产物。

1. 默认任务，6 回合、90,000 token 上限：13 次模型调用、54,224 tokens。模型修改了 `calc.py`、`test_calc.py`，但独立 `python -B -m unittest` 仍失败：`AssertionError: CalcError not raised`。两次有界修复后，独立 Reviewer 只读读取后未调用必需 `submit_review`，以 `required_tool_not_called` 失败关闭。
2. 显式 `calc_gcd/calc_lcm` 任务，12 回合、120,000 token 上限：3 次调用、8,039 tokens。模型尝试被拒绝的 `run_command`，随后只读取并未修改文件；基线测试虽 `12 tests / OK`，因无改动文件按合同失败关闭（`没有改动文件，不能把基线测试通过当作编码任务完成`）。
3. 同一显式任务但在需求中明确“不要调用 `run_command`，直接使用 `edit_file/write_file`”，12 回合、120,000 token 上限：16 次调用、88,482 tokens；模型修改 `calc.py`、`test_calc.py`，独立测试 `19 tests / OK`，Reviewer 完整读取并成功调用 `submit_review`，结果通过。

## 取舍与边界

采纳：把真实模型运行作为独立能力证据，保留调用量、token、隔离路径、测试退出码、Reviewer stop reason 和失败类别；任何基线全绿但无代码改动、必需工具未调用或独立测试失败均不授予完成信用。

暂缓：仅凭前两次失败调整生产提示、放宽 `run_command`、自动接受模型文本或提高模型/Reviewer 回合上限。第三次在需求中明确工具纪律后通过，说明模型具备完成该窄任务的能力，但三次样本远不足以宣称 90% 一致性；若要改善普通用户默认体验，必须先针对“工具选择/写入缺失”写独立 TDD，证明不削弱 write/approval/证据门，再以同一密钥路径做 A/B。

不适配：把模型自报、一次基线通过、签名 wheel、Pages 或 native bridge 结果合并为模型 90% 一致性；本记录不关闭 R2/R3、自动模式或真实工程总门。

## R3 计划→审查链复验（2026-10-09）

针对首次真实审查停步时发现的机器产物时序缺口，先在代码中补上最终登记前的幂等 `post_write` 重试，并让 `review_manifest.json` 引用模型提交的原始 `review_round_*.json` 字节，避免已经有 artifact 回执后再重写同一路径造成幂等冲突。新增回归覆盖“只缺机器清单”场景；相关链路/预算测试 44 项全绿。

随后用首次真实模型产生的 `01_plan.md` 作为计划正文，在新的真实控制面工单中重跑 review，仍使用仓外密钥路径和 bubblewrap。模型实际 23 次调用、135,095 tokens（含 108,928 cached），提交 `02_review.md`、`review_round_1.json`；控制面最终装配 `review_manifest.json`，三项边界检查通过，步骤 finish success。审查 JSON 含 5 条建议、4 条驳回、3 条待核实，manifest 的摘要计数与 detail SHA 一致。

该次状态前移仍被 `mcp_coverage` 门禁拒绝（工单保持 `review_in_progress`）：严格校验报告明确缺少 `review.dedup` 与 `review.result_summary` 两条 `.mcp_gate_trace.jsonl` 最终记录。当前 ICODE runner 尚未接入 cheap-research 的确定性 eligibility/trace 适配器，不能把“模型已提交审查正文”冒充这两条 gate 的履行；下一步应补宿主适配或记录可验证的 unavailable/degraded 证据，不得手写成功 trace 绕过门禁。因此本次只证明“真实模型 review 产物→机器清单→诚实停步”链路，不证明 merge/code/deepcheck/audit 或 R3 完成。模型期间额外执行了受控 `run_command` 探查，说明仅靠任务文本仍不能视为工具纪律稳定；不放宽门禁，也不把本次单样本外推为 90% 一致性。

在临时工单中按 cheap-research 契约写入了可验证的 host trace（dedup：0 个受影响函数，合法 `skipped_not_eligible`；summary：工具未暴露，`unavailable_before_call` 且带回退证据），校验器通过后 review 状态可前移。随后真实模型继续 merge，17 次调用、85,537 tokens，成功提交 `03_plan_final.md`；但 `merge.cross_round_summary` 仍缺最终 trace，状态前移再次被门禁拦截。该实验说明下一阶段应实现宿主 gate 适配/trace 生成，而不是让每个模型自行伪造隐藏账本。

## 宿主 gate 适配（2026-10-09，本机已验证）

新增 `src/icode/mcp_gates.py`，由链路步骤产物落盘后的宿主回调确定性写入 review/merge 的最终 trace；模型不能写隐藏账本。当前默认 runner 的 cheap-research MCP 未暴露，因此 `review.dedup` 按真实 Python Git 文件计数并合法记录 `skipped_not_eligible`，`review.result_summary` 与达到两轮时的 `merge.cross_round_summary` 记录 `unavailable_before_call` 及回退来源；少于两轮的 merge gate 记录 `skipped_not_eligible`。写入按 `(step, gate_id)` 替换，重试不会重复累积旧结论。新增适配器合同测试，并用固定子仓校验器验证 `missing_gate=0/schema_errors=0/sensitive_data=0`。这只关闭“宿主能生成诚实 trace”的本机软件子门；尚未用真实模型重跑 review→merge，也不授予 R3 或 90% 一致性信用。

## 真实模型 plan→review→merge 复验（2026-10-09）

在提交 `fe27a94` 后用仓外 key 文件、bubblewrap 和临时 `pycalc` 工作区重跑三步链路。第一次 12 回合、78,258 tokens 因模型把 plan 产物写成相对路径而由门禁失败关闭；第二次把绝对产物路径和工具白名单写入需求后，plan 18 回合、review 11 回合、merge 9 回合均完成，链路共 60 次模型调用、417,505 tokens（含 318,271 cached）。宿主自动生成 `.mcp_gate_trace.jsonl`：review 两条 gate 与 merge 一条 gate 均有最终记录，固定校验器两步均为 `missing_gate=0/schema_errors=0/sensitive_data=0/coverage=1.0`；review dedup 因临时 workspace 非 Git 合同地 `skipped_not_eligible`，summary 因默认 registry 未暴露 cheap-research 合同地 `unavailable_before_call`，merge 只有一轮 review 合同地 `skipped_not_eligible`。这证明真实模型→机器产物→宿主 gate trace→状态前移闭环，但只覆盖 plan/review/merge，尚未证明 code/deepcheck/audit、90% 一致性或 R2/R3 总验收。

随后在同一工单继续真实 `code→deepcheck→audit`。code 步骤 12 回合、20 次工具调用后，模型确实编辑了临时工作区的 `calc.py`、`test_calc.py`，但没有提交合同要求的 `04_code_review_fix.md` 与 `code_worklist.json`；宿主检测到 `code_files` 变更但控制面元数据写入未通过，按 fail-closed 停在 code，未进入 deepcheck/audit。独立 diff 还显示模型删除了原有 gcd/lcm 实现，说明“有代码改动”不等于实现正确，不能人工补齐产物或把这次运行计入 R3 完成。

事后从事件链确认，`code_files` 写入失败的直接原因是宿主复用了 plan 阶段的通用 metadata request，触发控制面 `idempotency_conflict`；`24e58dd` 已按 code attempt 与文件集合生成独立 request 并加入回归。该失败工单的 step attempt 已终结，不能重放覆盖原证据；修复后的真实 code→deepcheck→audit 需新工单重新验证。

## inspection 工具接线（2026-10-09，本机实现待新工单真实复验）

失败样本还暴露了一个独立的运行器能力缺口：模型原先只能使用普通 `write_file`/`submit_artifact`，没有办法调用固定工单身份的 ICODE-SKILL 原生 `inspection --phase prepare/read/check`。仅让模型手写 `code_worklist.json` 会缺少控制面 `artifact_written` 回执，不能作为真实审查证据。

本轮实现了宿主绑定的 `inspection` 工具。运行器把当前 `out_dir`、ticket、step、attempt 和控制面实例闭包绑定，模型只能提交阶段、工程内相对路径、关联范围和基线 JSON；路径越界、非法阶段和超过有界数量的范围在工具层拒绝。控制面仍负责冻结输入、哈希、事件回执和最终 check，失败结果原样返回模型，不绕过门禁。`code_worklist.json`、`deepcheck_worklist.json`、`audit_worklist.json` 已加入“已由 inspection 生成后不可被模型覆盖”的保护；兼容夹具仍允许在尚未生成时通过合同提交，避免破坏旧离线回归。

本机针对工具边界、机器工作清单保护、`code_files` 幂等键修复及相关链路共 15 项定向测试通过，compileall 与 diff check 通过。下一步必须用新 ticket、同一仓外模型 key 和真实隔离环境重新跑 code→deepcheck→audit，并分别核对源码正确性、独立测试、inspection 回执、Reviewer 只读与状态前移；在该证据取得前，R3 和“≥90% 一致性”仍未通过。

## 新工单真实复验（2026-10-09，6ac32e5 运行器）

使用同一仓外 key、bubblewrap 和临时 `pycalc` 副本启动 `R3-REAL-6AC32E5`，真实链路共 63 次调用、417,756 tokens。plan 成功并前移；review 在 18 回合后 fail-closed：模型提交了 `02_review.md`，但没有形成合法的 `review_round_*.json`，多次 `submit_artifact` 事件均以 `bad_arguments` 失败，因此宿主不能装配 `review_manifest.json`。没有进入 merge/code/deepcheck/audit，不能把这次运行当作 inspection 工具的真实 code 证据，也不把失败归因于门禁放宽。该工单保留在临时目录供审计；后续若要重新取得 code 信用，必须新建工单并先让模型完成合法 review round。

## Review 参数兼容修复（2026-10-09，eb42ab9）

针对上述 `bad_arguments`，主工程提示明确要求 `submit_artifact` 的 `name`、`content` 均为字符串，
JSON 文件的正文必须是合法 JSON 文本，`review_manifest.json` 由宿主装配而非模型提交。运行器还增加窄
兼容：当提供方把 dict/list 作为 `.json` 正文传入时，仅将其序列化为 UTF-8 文本；Markdown 或其它文本
仍拒绝非字符串，ArtifactBroker 的路径、大小、机器所有权和事件登记合同不变。回归测试覆盖结构化
JSON 接受、普通文本拒绝、旧 artifact 合同及 review 提示，共 10 项通过，compileall 通过。该修改尚
未取得新的真实 review 成功证据；新工单 `R3-REAL-REVIEW-PROMPT` 的进程在修复前启动，结果必须
单独记录，不能与 `eb42ab9` 的新行为混写。

该工单随后结束：plan 通过；review 的最终有效阶段为 5 回合/9 次工具调用，模型只提交了
`02_review.md`，没有形成合法 `review_round_*.json`，宿主无法装配 `review_manifest.json`，按
fail-closed 停步。总计 56 次调用、483,922 tokens（prompt 440,950 / completion 42,972 / cached
380,889）。新的 dict/list 兼容没有获得真实命中样本；因此这次不证明 review、inspection 或
code→deepcheck→audit 能力，也不提高 R3 或 90% 一致性信用。
