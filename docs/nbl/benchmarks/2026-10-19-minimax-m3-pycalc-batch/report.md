范围声明：单靶场任务（pycalc/DEFAULT_TASK）、单一模型、隔离工作区；这是 R7 benchmark 口径的端到端统计，不是多仓库公开评测。n=5 的样本量不足以支撑任何泛化结论。cost_usd 为 pricing 表静态估算价，不是账单。循环参数：max_turns=24、max_output_tokens=8192、max_repairs=2、预算硬停=120K tokens（hard_ratio=1.0）。已知失真：pricing 表 minimax 条目（0.30/1.20 per 1K）与 MiniMax M3 公开标价量级不符（约 0.30/1M 输入），cost 字段高估约两个数量级，仅作口径演示；pricing 表数据修正列为后续项。驱动只产出 success/failed 两态；refused/human_intervention 为保留态。

# icode benchmark 报告

- run 数：5
- 成功率：0.2000（分母=全部 run）
- 首次门禁通过率：0.0000（分母=全部 run（门禁一次通过，无重试后通过））
- 恢复率：0.2000（分母=经历过失败的 run（非 first_pass）；recovered 指其中最终成功者）
- 人工介入率：0.0000（分母=全部 run）
- token 合计：prompt=513375 completion=31514 total=544889
- 耗时合计：417557 ms
- 成本合计：$191.829300

## 全部 run（含失败样本，无筛选）

| run_id | task | repo@commit | backend/model | result | first_pass | recovered | total_tokens | cost_usd |
|---|---|---|---|---|---|---|---|---|
| minimax-m3-pycalc-01 | pycalc/default | ayukyo/icode@unknown | openai-compatible/MiniMax-M3 | failed | False | False | 109685 | 36.490200 |
| minimax-m3-pycalc-02 | pycalc/default | ayukyo/icode@unknown | openai-compatible/MiniMax-M3 | success | False | True | 59027 | 24.599400 |
| minimax-m3-pycalc-03 | pycalc/default | ayukyo/icode@unknown | openai-compatible/MiniMax-M3 | failed | False | False | 128085 | 47.511000 |
| minimax-m3-pycalc-04 | pycalc/default | ayukyo/icode@unknown | openai-compatible/MiniMax-M3 | failed | False | False | 121746 | 41.403600 |
| minimax-m3-pycalc-05 | pycalc/default | ayukyo/icode@unknown | openai-compatible/MiniMax-M3 | failed | False | False | 126346 | 41.825100 |
