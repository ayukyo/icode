# 真实模型靶场验证记录

日期：2026-10-09。密钥仅通过仓外路径传入，未读取、打印或提交；两次运行均使用临时 `pycalc` 副本和 bubblewrap 隔离。

## 结果

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

该次状态前移仍被 `mcp_coverage` 门禁拒绝（工单保持 `review_in_progress`），因此只证明“真实模型 review 产物→机器清单→诚实停步”链路，不证明 merge/code/deepcheck/audit 或 R3 完成。模型期间额外执行了受控 `run_command` 探查，说明仅靠任务文本仍不能视为工具纪律稳定；不放宽门禁，也不把本次单样本外推为 90% 一致性。
