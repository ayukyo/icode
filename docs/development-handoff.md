# R2 / R3 开发接力

更新：2026-10-12 17:50（北京时间）。按用户要求，本次收齐在途检查后保存进度，不再启动新的开发任务。

## 当前结论

**R2 / R3 尚未整体验收。** 最近一次生产代码提交为 `1754ccafcd568f5771c342ec9223c307513cee2c`，已推送 `main`，本地与远端一致。接力文档的后续提交不是新的生产代码验收候选。

| 阶段 | 当前状态 | 下一步 |
| --- | --- | --- |
| Linux S2a 上下文薄适配 | 已发布 `01e22a4` | 不重复实施 |
| Linux receiver 截止原因分账 | 已发布 `667c92a` | 不外推历史 ARM 根因或原生因果证明 |
| Linux S2b1 控制面适配 | 已发布 `1754cca` | 不重复实施 |
| Linux S2b2 Runner 生命周期 | DESIGN 双审通过；完整 PLAN 的独立 SPEC 通过，QUALITY 未启动 | 先做不同审查者的 PLAN QUALITY，再正式 TEST → SOURCE |

S2b2 的生产 `runner.py`、`chain.py` 尚未修改；`tests/test_linux_prepared_runner_lifecycle.py` 尚不存在。计划中的内存诊断不是正式 TDD，不代表功能已实现。

## 已发布 S2b1 的证据

仅六文件：控制面原始回执入口、新私有观察适配、新测试、DESIGN、PLAN、持续竞品对照。

- 正式原基线：作者与 root 各 16 方法、15 个有效断言失败、0 ERROR / skip，exit1。
- 实施后：作者与 root 各新 16 项通过；相关八模块 196 项通过，5 项原平台跳过。
- 实际 SOURCE 独立 SPEC → 不同 QUALITY 均 C0 / I0 / M0。
- 唯一原完整预检：`/tmp/icode-cp-prepared-preflight.dOMmDP/typescript`，09:10:18–09:20:00 UTC，三门 PASS、exit0；不猜未输出的全量数量。
- 最终两轮原文档检查各 raw0，密钥扫描、子模块完整性、精确六文件暂存字节及 cached whitespace 检查通过，再提交推送。
- 发布前补丁围栏尾随空格曾实际阻断；仅裁掉未修改的外缘上下文，严格投影源码不变，独立复核后重新过门。失败历史保留在原 PLAN 和持续对照中。

固定子模块仍为 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`，本次没有再次修改 ICODE-SKILL。

## 当前提交的线上终态

以下均绑定 `1754cca`、`main / push / attempt 1`。独立观察者 09:49:36 UTC 收齐；root 另实际读取全部 job 元数据及 12 个关键原日志，并于 09:50:18 UTC 重核最后 provenance 终态。

| 工作流 | 终态 | 边界 |
| --- | --- | --- |
| [CI 38230724875](https://github.com/ayukyo/icode/actions/runs/38230724875) | 41 成功、2 失败、3 跳过，共 46 job | 两个 Windows Reviewer 仍失败，不是总体全绿 |
| [Windows helper provenance 38230724868](https://github.com/ayukyo/icode/actions/runs/38230724868) | 5 / 5 成功 | 来源拒绝与回收测试成功，不是可信启动授权 |
| [Public website 38230724577](https://github.com/ayukyo/icode/actions/runs/38230724577) | 2 / 2 成功 | 同 SHA 已部署，不是 R2 / R3 能力验收 |

关键原日志可从以上工作流重新读取，不依赖新会话仍能访问旧工具内存：

- Python 3.11 job `114749249615`：3221 tests / 545.992s / 86 skips；Python 3.12 job `114749249750`：3221 / 546.456s / 86 skips，均通过。这些数量属于已发布 S2b1，不包含尚未落盘的 S2b2 测试。
- Windows Reviewer：x64 `114749249934`、ARM `114749249836`。候选双协议仍 `10035 / wait_expired=true / connect_denied=false`；正控 `105 / ipv4_connect_timeout / inconclusive`，WFP 无匹配 drop、补充 capture 缺失。**超时不能当网络 DENY。**
- 四 Linux job `114749249902 / 114749249907 / 114749249972 / 114749250145`：各 84 条旧 helper-dispatch 记录，通道、进程、线程回收通过；不是新 prepared 安装矩阵或 worker 截止采样因果证明。
- 四 provenance consumer `114752517458 / 114752517497 / 114752517492 / 114752517673`：`source_policy_all_passed=false / owner_untrusted`，compatibility、launch、protected 均 false；helper/verifier 各 13 opened / 13 confirmed closes / 0 unknown，逆序回收确认。不能外推 Windows 10 实机、叶 PE 消费、UAC 或受保护晋升。
- 观察者保留了全部 50 个执行 job 的完整原日志；另 3 个 skipped job 无执行日志。不要取消或重跑来掩盖未通过项。

## 下一会话从这里接

先全文阅读：

1. [S2b2 DESIGN](nbl/specs/2026-10-12-linux-prepared-runner-lifecycle-design.md)。批准 SHA256：`ff78553d7fa5ce74fdb955464b253a0bb9567763f87e92ea8d0d04669d0410bf`。
2. [S2b2 完整 PLAN](nbl/plans/2026-10-12-linux-prepared-runner-lifecycle.md)。保存时冻结 SHA256：`75b1776e84e7726305171a400b39e1747bab3dd39909cc7a258a4824b3576643`，1244 行，完整 TEST 与两个 SOURCE diff 资产均已包含。
3. [持续竞品对照与执行历史](agent-landscape-live.md)，保留原失败、日期、固定上游和信用边界。

### 待完成的第一道门

PLAN 独立 SPEC 已 C0 / I0 / M0，审查者 `prepared_runner_plan_spec_review` 已停止：严格 13 + 3 hunk 投影、独立 RAM 20 项 / 49.888s / 0 FAIL / ERROR / skip，六健康 terminal=1、六 unknown terminal=0；两轮原 scanner raw0。**不同审查者的 PLAN QUALITY 还没有开始，不能直接实施。**

上述完整 SPEC 对象为原 PLAN `4936fe31e2c2932814c2162ac2ce31c85b20928413a3c1e2a0948ffcdf0ec553`。保存前对未跟踪全文的 whitespace 检查 817ecc 实际拦截末尾多一个空行（exit3）；root 只删除最后一个额外 LF，得到上面的保存摘要，正文与所有可执行资产不变。原审查摘要保留，不伪装同一文件字节；另做文档等价复核，不替代下一会话尚待的 QUALITY。

该等价复核已完成 C0 / I0 / M0（7b6d23，exit0）：加回一个 LF 精确重建原摘要，Python/diff 围栏及 13 + 3 hunk 投影完全相同，新 TEST 仍不存在；未重跑任何测试。四文档首次 cached 检查 de03e7 已 exit0；记录补入后发布前再核最终字节。

通过 QUALITY 后，按原 PLAN 串行推进：

1. 不同 TEST 作者只创建批准的新测试，正式原 SOURCE RED；root 独立重复。不得用 ImportError、TypeError、内存诊断冒充有效断言失败。
2. 冻结 TEST 后，由不同 SOURCE 作者仅修改 `runner.py / chain.py`，作者与 root 各 GREEN 和限定回归。
3. 实际 SOURCE fresh SPEC → 不同 QUALITY 零遗留，再由 root 启动唯一原完整预检，最终文档与精确六文件门通过后一次提交推送 main。

本片目标：一次 prepare / attach、真实 CP attempt / fresh observer、普通 / 补救 / 工程同 view，六 terminal 前确认收尾，finally 仅兜底；unknown/faulted 不终结、不清 checkpoint。内部 owner 关闭与外部 owner 保持 active 分账；旧 None/custom、Reviewer、resume、readyfalse 合同不变。

冻结资产用于识别漂移，不是执行授权：

| 对象 | SHA256 |
| --- | --- |
| 实际旧 runner | `56abe98e31f02cc96327a364c52ace9aef5b7c60e6594025058e2de48f15a63d` |
| 实际旧 chain | `28244144023c85548ca0e9bcb68235a935d648d53b8367ae80cde67f746508de` |
| PLAN 内完整 TEST，42485 bytes | `772188d5fae95b2dcd3415fe97ef62a4659edc5f7552f58ef9424ded8534a334` |
| PLAN 投影 runner | `a0f3342473edc1c222188bf47a2aed7903b33783d6d6871a5848451262fb9d2f` |
| PLAN 投影 chain | `16c23c505724cb9a23f25eb27d77e21919146dd0dbc3adde752de2c863f10acd` |

作者相同最终 TEST 的私人 RAM 基线为 20 方法 / 37 有效断言失败 / 0 ERROR / skip；投影 20 项通过 / 51.053s。首轮投影的四项失败及夹具修复历史见 PLAN；无正式新 SOURCE/TEST，因此不得继承为正式 RED/GREEN。

## 仍开放的整体验收项

- Linux 后续 S2c / S3 的实际安装候选消费、四 Linux 新 prepared 矩阵；LA-2 自动准入、LA-3 网络、LA-4 持久回执 / doctor / UI。
- Windows WP0b 的实际来源 / proof / release / 加载边界、稳定路径首次 UAC、受保护晋升、跨管理员与父进程死亡证明；双 Reviewer 网络 DENY 仍未证明。
- macOS 单任务配额仍不合格。已按用户同意的 Codex 式边界验收文件 / 网络沙箱继承与同组清理，不承诺主动脱组后代零残留；不得用用户级限额替代。
- R3 真实模型六步链及至少 90% 能力一致性仍未验收。历史 plan → review → merge 三步成功不能替代 code → deepcheck → audit。当前阶段未读取或使用仓外模型凭据，不把凭据内容写入文档或 Git。

## 接力约束

- 直接 main、完成阶段后提交推送，不创建工作分支 / worktree；不 reset、force push 或清除用户改动。
- 编译最多 `-j6`，完整验证沿本轮低负载 `-j1`。使用 `.venv/bin/python`，不因系统 Python 3.10 的收集问题修改产品合同。
- 复杂实现前遵守 AGENTS 的三问和 sequential-thinking；使用适用技能，独立只读研究与开发并行，采纳机制而非盲抄代码。
- 根目录执行 `git status --short`、`git log -5 --oneline` 和上述 SHA 核对；文档提交后 HEAD 会变化，判断生产代码基线时检查文件字节，不机械要求 HEAD 仍为1754cca。
- 当前 writer、SPEC、研究及 CI 观察线程均已停止；没有遗留运行中的完整预检或已启动的正式 S2b2 测试。

可在新会话直接发送：

> 先阅读 docs/development-handoff.md 与其中链接的 DESIGN / PLAN，核当前 Git 和冻结字节；从 S2b2 PLAN 的独立 QUALITY 开始，继续按门实施 R2 / R3。一般按推荐方案推进，非必要不用询问；保持并行只读研究、main-only 和最多 -j6。

## 架构级自检报告（本次仅进度文档）

- 语法 / 格式：两轮原文档检查 raw0、密钥与子模块单门通过，四文档 cached whitespace 检查通过；记录追加后发布前再次核验。
- 依赖 / 调用链：关联 DESIGN、PLAN、持续对照和线上 run / job 均已核。
- 逻辑 / 边界：已发布、仅计划、待审和未验收分别标明。
- 异常处理：保留真实失败和不通过项，不以线上绿色洗白未知。
- 关联模块：仅保存文档，不新增生产 SOURCE/TEST 或权限。
- 兼容安全：冻结字节、子仓库版本、旧合同及接力停止线保留。
- 可运行性：生产运行证据继承已发布候选；本次不授新代码执行或 R2 / R3 完成信用。
