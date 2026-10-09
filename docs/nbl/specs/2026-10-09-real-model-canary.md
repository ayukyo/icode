# 真实模型靶场验证记录

日期：2026-10-09。密钥仅通过仓外路径传入，未读取、打印或提交；两次运行均使用临时 `pycalc` 副本和 bubblewrap 隔离。

## 结果

0. **修复后窄任务复验（2026-10-09）**：使用同一仓外密钥、MiniMax-M3、`https://api.minimaxi.com/v1` 与 bubblewrap 临时 `pycalc` 副本；需求明确要求通过 `edit_file`/`write_file` 修改，不把代码只写在回复中。主模型循环 12 回合/11 次工具调用，Reviewer 4 回合/4 次工具调用，共 16 次调用、69,484 tokens（prompt 63,306 / completion 6,178 / cached 52,094）。实际修改 `calc.py`、`test_calc.py`，独立 `python -B -m unittest` 执行 21 tests、退出码 0；Reviewer 精确读取两文件并提交结构化结果，最终通过。模型尝试的越界 `run_command` 仍被拒绝，未放宽工具或审批门。该样本证明当前窄 pycalc 任务的真模型→写入→独立测试→Reviewer 闭环可运行；不证明六阶段 1→6、跨平台原生隔离、90% 一致性或 R2/R3 总验收。临时工作区位于 `/tmp`，仓库无改动，密钥未打印、未复制、未进入产物。

0.1. **R3 计划→审查复验（2026-10-09，提交 `120e94d` 后）**：新建临时 `pycalc` 工程，以 `chain --only plan,review,merge`、MiniMax-M3 和 bubblewrap 运行。plan 12 回合/20 次工具调用后通过并前移；review 5 回合/8 次工具调用后未生成 `02_review.md`，也没有合法 `review_round_*.json`，宿主无法装配 `review_manifest.json`，按 fail-closed 终止；merge 未运行。全链路共 48 次调用、304,057 tokens（prompt 287,743 / completion 16,314 / cached 246,831）。模型尝试的越界读取/命令仍被拒绝，未人工补产物。该结果证明修复后宿主仍能诚实停步，但不能授予 review、merge、code→deepcheck→audit、1→6 或 90% 一致性信用。

0.2. **审查提交动作提示收窄（2026-10-09，`9c0ec26`）**：针对 0.1 中“读完输入后无工具收尾”的真实行为，review 步骤额外要求读完计划后立即调用 `submit_artifact`，明确禁止只在最终回复中描述审查或无工具结束；不改变工具白名单、ArtifactBroker、控制面事件或 fail-closed 逻辑。`test_chain_offline` 25 项、compileall-j1 和 diff check 通过。尚未取得该提示修复后的新真实 review 证据，不能将本地回归计作 R3 信用。

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

## 结构化 review round 与完整三步链复验（2026-10-10，`c90825b`）

使用同一仓外 key、MiniMax-M3、bubblewrap 与临时 `pycalc` 副本，新建工单
`R3-REAL-CHAIN-FINAL`，执行 `chain --only plan,review,merge`，预算上限 700,000 tokens。
运行器为真实提供方保留交付回合；review 使用 typed `submit_review_round` 生成
`review_round_1.json`，控制面再装配 `review_manifest.json`。结果如下：

- plan：14 回合 / 22 次工具调用，`01_plan.md` 登记、finish success、状态前移；
- review：11 回合 / 14 次工具调用，`02_review.md`、合法 `review_round_1.json`、宿主
  `review_manifest.json` 均登记，三项边界检查、事件链和 finish success 通过；
- merge：14 回合 / 21 次工具调用，`03_plan_final.md` 登记、finish success、状态前移；
- 全链路：64 次调用、438,817 tokens（prompt 406,347 / completion 32,470 / cached
  353,826），最终 `链路走完（completed）`。

这是当前真实模型 plan→review→merge 的完整闭环证据，证明结构化 round 工具和回合边界修复
有效；仍不证明 code→deepcheck→audit、跨平台原生隔离、任意项目成功率、90% 一致性或 R2/R3
总验收。密钥未打印、未复制、未进入工单与提交。

## 后续真实后半段复验与失败边界（2026-10-10，`e3e1022`）

两次后续尝试均如实保留失败：

1. 在已通过三步的 `R3-REAL-CHAIN-FINAL` 工单继续执行 `code→deepcheck→audit` 时，模型提交了
   `04_code_review_fix.md` 与 `code_worklist.json`，但 `calc.py`、`test_calc.py` 没有任何工作区改动；
   inspection `prepare` 返回失败，code step fail-closed，未进入 deepcheck/audit。该样本证明
   “产物齐全”不会冒充“真实代码完成”。
2. 新建 `R3-REAL-FULL` 与 `R3-REAL-FULL-FINAL` 尝试完整六步时，plan 通过，但 review 未产生
   合法 round，均停在 review；没有把未验证的后半段写成成功。

随后主线 `e3e1022` 让真实 code 步骤接近回合上限时优先获得一次 `edit_file` 机会；离线 144
项回归通过，尚未取得该修复后的真实 code→deepcheck→audit 成功证据。因此 R3 仍只对
plan→review→merge 三步闭环有真实信用，R2、90% 一致性和总验收继续关闭。

## 强制交付回合与真实 code 改动复验（2026-10-10，`e94a86b`）

在 `86cdc14`、`8d1f5f3`、`e562624`、`2fe8169`、`e94a86b` 的连续窄修复中，运行器为真实提供方
增加了有界交付回合、非目标工具拒绝和 code 产物提交切换；149 项定向回归、5 项跳过，compileall
通过，所有提交均推送 `main`。真实工单 `R3-REAL-FINAL-2FE8169` 的 plan、review、merge 全部成功，
code 步骤实际用 `edit_file` 修改了临时 `calc.py` 和 `test_calc.py`，并登记了
`04_code_review_fix.md`；但 `code_worklist.json` 未形成合法 JSON 产物，按 fail-closed 停在 code，
没有进入 deepcheck/audit。该样本首次证明“两个工程文件真实变更”与“code 产物完整”被分别核验，
不能把部分成功折算为 R3 六步成功。

随后 `R3-REAL-FINAL-E94A86B` 在 plan 阶段收到兼容端点 HTTP 400，未形成 `01_plan.md`，也不作
能力信用。当前仍没有 code→deepcheck→audit 的完整真实成功样本，不提高 R3/90% 一致性或 R2 总验收。

## inspection 状态机修复与真实边界（2026-10-10，`8fabe36`、`fee0353`、`695a381`）

针对真实 code 回合中“同一模型回复包含多次编辑时提前切换工具”、源码编辑后继续沿用旧
worklist、以及恢复时旧 worklist 未重新绑定的问题，运行器现在会在一条 assistant 回复的所有工具
结果配对后再切换；编辑后强制 `prepare → read(code_review) → check`，按 worklist 逐文件读取；恢复
检测到既有 worklist 时先重新 prepare。新增恢复/多调用顺序测试；定向套件最终为 **151 passed、5
skipped、32 subtests passed**，compileall 与 diff check 通过，三个提交均已推送 `main`。

真实证据：`R3-REAL-FINAL-8FABE36` 的 plan、review、merge 成功；code 真实修改了临时
`calc.py`、`test_calc.py`，并由宿主 inspection 生成了 `code_worklist.json` 与 `04_code_review_fix.md`。
但模型在源码变更后未完成有效的 `read/check` 顺序，code finish 被控制面拒绝，未进入
deepcheck/audit。随后对该失败 attempt 的 recovery 也如实停在 `required_tool_not_called`，旧 attempt
被控制面标记 failure，未重放或冒充成功。新的完整链路尝试 `R3-REAL-FINAL-FEE0353` 在 merge 阶段
缺少 `03_plan_final.md` 停步，未取得后半段证据。以上结果证明状态机与 fail-closed 行为可观察，
不证明 code→deepcheck→audit、R3 六步、跨平台原生隔离、90% 一致性或 R2 总验收。

## Review round 提供方兼容复验（2026-10-10，`a5fbf56` 工作树后）

新工单 `R3-REAL-FINAL-15` 使用同一仓外 key、MiniMax-M3、bubblewrap 和临时 `pycalc` 副本执行
`chain --only plan,review,merge`。plan 在 26 回合上限内成功；review 只提交了 `02_review.md`，
没有合法的 `review_round_*.json`，宿主没有装配 `review_manifest.json`，按 fail-closed 停在 review；
merge、code、deepcheck、audit 均未运行。全程 46 次调用、557,849 tokens（prompt 526,222 /
completion 31,627 / cached 475,525）。

该行为显示兼容 OpenAI 端点仍可能忽略 typed `submit_review_round`，改用通用 `submit_artifact`。
主线随后增加窄兼容：仅当当前强制交付为 review round 且 ArtifactBroker 合同明确允许
`review_round_*.json` 时，通用调用仍必须经过同一文件名、JSON schema、大小、路径和事件校验；
其它强制工具调用仍拒绝。本次真实运行发生在修改前，不能计作新兼容命中或 R3 信用。修改后
全量本机回归（2,518 项，60 项平台条件跳过）通过；Windows 原生 CI 仍有独立失败项，R2/R3、
六步链和 90% 一致性继续未通过。

## Review round 兼容命中与 merge 副作用边界（2026-10-10，`028fd7a`）

新工单 `R3-REAL-FINAL-16` 在 `028fd7a` 工作树后使用同一仓外 key、MiniMax-M3、bubblewrap
和临时 `pycalc` 副本执行 `chain --only plan,review,merge`。plan 32 回合后成功；review
只用 6 回合/4 次工具调用即完成，真实目录同时登记 `02_review.md`、合法
`review_round_1.json` 和宿主装配的 `review_manifest.json`。其中模型先发通用
`submit_artifact`，随后调用 typed `submit_review_round`；两者都经过同一合同和事件校验，
证明窄兼容路径在真实模型上可命中，不是离线假设。

merge 阶段模型确实生成了 `03_plan_final.md`，但连续重复写入触发宿主“副作用回执不完整”的
保护，事件链不完整，控制面拒绝登记该产物并 fail-closed；没有人工重放或把文件存在当作成功。
全工单共 132 次调用、1,610,565 tokens（prompt 1,524,629 / completion 85,936 /
cached 1,395,820），最终停在 merge。该样本授予 plan→review（含真实 round/manifest）信用，
不授予 merge、code→deepcheck→audit、R3 六步、90% 一致性或 R2 总验收信用；同时暴露长产物
提交的事件链收尾仍需独立修复和新工单复验。
