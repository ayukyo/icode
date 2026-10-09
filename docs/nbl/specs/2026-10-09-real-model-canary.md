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
