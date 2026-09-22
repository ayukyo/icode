# E2E 靶场：calc 演示工程

从 `vendor/icode-skill/demo/` 复制而来的**源码副本**，作为 Agent 端到端测试的被操作工程。

只保留 4 个源文件，**刻意排除**上游的 `.all_tests_final/` 与 `.ui_runtime_sim-final/`
（那是 icode-skill 自己的测试夹具快照，286+ 文件，与本仓 E2E 无关）。

## 为什么复制一份而不是直接用子模块里的

- 子模块保持干净：E2E 会在该工程下生成 `.icode_output/`（工单产物），
  直接写进子模块会让它变 dirty，也可能与上游的 `.gitignore` 规则互相干扰。
- 主仓自持后可以自由改造需求，不受上游 demo 演进影响。

## 当前状态

| 项 | 说明 |
|---|---|
| 语言 | C（`-std=c99`），`make` / `make test` |
| 已有能力 | `calc_basic`（+ - * / %）、`calc_power`、`calc_sqrt`、`calc_isqrt`、`calc_eval` |
| **已实现，不能再当新需求** | `calc_sqrt` / `calc_isqrt` 均已落地 —— 上游 README 的示例 `/icode fast "Add isqrt function to calc.c"` **已经跑过一轮** |
| 建议的 E2E 需求 | `calc_gcd` / `calc_lcm`（未实现、可断言、不依赖浮点） |

## 已知限制

本机**没有 gcc / make**，`make test` 无法执行。因此 E2E 目前只能验证到"产出代码"为止，
`verify` 阶段必须显式声明为 `unobserved` 降级，不能伪造验证结论。
需要完整跑通时请先安装 MinGW-w64 或 MSYS2。
