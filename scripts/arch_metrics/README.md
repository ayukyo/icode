# 架构度量脚本

可复算 ICODE `src/icode` 的架构指标。基线 commit：`105fc27`（远端 main）。

## 前置

- Python >= 3.12（项目要求）
- 零第三方依赖，仅用标准库（`ast` / `os` / `re` / `collections`）

## 运行

在**仓库根目录**执行（脚本以 `parents[2]` 解析仓库根，必须从根目录跑）：

```bash
python scripts/arch_metrics/metrics.py           # 模块清单 / LOC / 扇入扇出 / 测试映射
python scripts/arch_metrics/cycles.py            # SCC 循环检测（含行号与 import 形态）
python scripts/arch_metrics/cycles_classified.py # 硬循环 vs 延迟导入循环分类
python scripts/arch_metrics/coupling.py          # 平台混用 / 重复函数 / 参数分布 / 全局状态
```

每个脚本会把结果同时打印到 stdout。`metrics.py` 另写一份 JSON 到 `scripts/arch_metrics/metrics_out.json`。

## 各脚本的口径

| 脚本 | 输出 | 口径说明 |
|---|---|---|
| `metrics.py` | 模块数 / LOC / 扇入扇出 / 无直接测试的模块 | 扇入扇出含**函数内延迟导入**，去重后统计 |
| `cycles.py` | 全部 SCC 循环组 + 每条边的行号与 import 形态 | 含 `rel-from` / `from` 等形态标注 |
| `cycles_classified.py` | **硬循环**（模块级双向 import）与**延迟循环**（一侧为函数内 import）分离 | 硬循环 = import 期即成环；延迟循环 = 运行时成环 |
| `coupling.py` | 平台混用模块 / 重复函数 / 参数数分布 / 模块级可变全局 | 重复检测按 AST 归一化（去函数名）后精确匹配 |

## 已知基线值（`105fc27`）

- 模块 **104** / LOC **48,516**（代码行 42,605）
- 函数总数 **1,653**
- 硬循环依赖 **0**；延迟循环 **14 组**，函数内延迟导入 **177 处**（28 个模块）
- 扇入 hub：`sandbox_policy` 21、`config` 10、`control` 10、`isolation` 10
- 扇出 hub：`runner` 36、`cli` 22、`autonomy` 14、`chain` 12
- 参数 ≥8 的函数 **51**；≥12 的 13 个；≥20 的 4 个
- 无直接测试 import 的模块 **6 个 / 926 行**

## 用途

用于 SPEC `docs/nbl/specs/2026-10-25-architecture-consolidation.md` 的验收度量，以及后续重构前后的前后对比。
