# Linux 工程桥接：新增阻塞与真实诊断边界

观察日期：2026-10-09 04:11 UTC 起；下列补充诊断同日在初稿之后运行。基线 main `8d53670192e3e2cbfebaa0300d697fb3036308be`，ICODE-SKILL `1693651c1bd7daad3272eb054f0f81d6f254d08d`。仅记录当前源码、巡检生成/验证与 admission-only 诊断，不修改生产、测试、vendor、权限或 Native readiness；不是 R2/R3 完成报告。

本记录补充[桥接设计](2026-10-09-linux-engineering-bridge-design.md)的 CP-02、L2b、STEP-01，不能以原设计审查通过外推这些实现门已闭合。此前[命令层 40 项证据](2026-10-09-linux-bridge-command-evidence.md)保持其原信用范围。

## 1. 分离布局的巡检清单阻塞

独立计划作者发现，root 随后完整阅读 `vendor/icode-skill/tools/inspection_worklist.py` 471 行，并核控制面 `icode_control.py:4489–4504` 的严格 step finish：

- `_repo`（114–120）仅在 workspace 内寻找 `.git`，不查父层。真实分离 workspace 为 `checkout/code`，元数据在 `checkout`，故无法识别受影响仓库。
- `build_worklist`（274–286）为相应 seed 加入 `no affected Git repository; diff/association coverage unavailable` 债务，311–314 将覆盖状态设为 `partial`。
- `validate_worklist` 不接受这些债务作为成功验收；真实 step finish 也不绕过它。因此仅修主工程的 session-aware state/tree，不能使完整 code/deepcheck 正控通过。

初稿时这里只是实际源码分析，尚未运行分离巡检复现。随后 root 使用已有 `TestGitWorkspaceIdentityVerification.setUp` 的 owned 临时真实 Git/manager fixture，直接导入固定 vendor 的原 helper，实际运行 build/validate（非完整 CP 步骤），命令 exit 0。实际结果如下：

| 观察 | 真实结果 |
| --- | --- |
| 真实 workspace 与元数据 | workspace==checkout/code；父 checkout/.git 为文件 |
| `_repo(root, "tracked.txt")` | 未发现仓库 |
| build 覆盖率 | partial |
| unobserved | tracked.txt：no affected Git repository; diff/association coverage unavailable |
| 独立原 validate | inspection incomplete without accepted explicit debt；missing Read: tracked.txt:code_review |
| 模型、完整步骤 | 均为 0 次 |

这证明巡检生成与严格验证的实际拒绝条件，不等于已执行 CP step finish 或捕获其运行错误码。未填 reads、未清债务、未改 coverage；fixture 由其原 registered cleanup 清理，无持久报告包。完整步骤拒绝仍需后续真实负控。

2026-10-09 04:12 UTC 后已向用户另行请求最小修改巡检清单、必要调用处及测试的授权，当前待回复。之前授权只涵盖三个 Python 校验器的解释器/UTF-8 修复；不能推定授权扩大。拟议方向是明确、严格验证宿主提供的仓库身份与源码范围，**不是自动沿父目录发现，也不是清债务或伪造 complete**。具体设计与独立审查仍未完成。

L2b/STEP-01 完整成功门继续 blocked；Git 修复与可安全实施的 L2a 工作不被此授权问题阻塞。

## 2. 未决动作的记录幂等不等于执行幂等

root 实读 `src/icode/operations.py` 全文、vendor `cmd_operation` 4823–4950、runner 工程 gate 与公共 resume 的对应路径：

- vendor 同 request 的匹配事件先返回 `already_applied=True` 与旧 attempt，再处理同名未决动作拒绝。
- `OperationRecorder.start` 丢弃 already-applied 标记；`StartedOperation.can_execute` 仅检查 ok、ambiguous 与 attempt。
- 新 recorder 的计数重置，内部工程 gate 因而可能重新接受仍 open 的旧动作。公共 resume 有额外 open-operations 检查，不能把其拒绝信用移给内部 gate。

root 使用现有 Python 3.11 测试解释器、真实 CP 与 recorder，在独立 `TemporaryDirectory` 中创建合法 `.icode_output` 工单，只调用动作 admission 与 trace，**载荷执行数为 0**。最终命令 exit 0，wall 0.324261776 秒；实际结果：

| 观察 | 真实结果 |
| --- | --- |
| 首次 recorder admission | can_execute=True |
| 新 recorder 同 request | already_applied=True；同 attempt；仍在 open_operations；can_execute=True |
| 原 recorder 下一 occurrence | returncode=1；gate_id=ambiguous_side_effect；can_execute=False |
| 原 recorder 的 ambiguous 字段 | False；error 正文为中文，现有包装未据 gate_id 识别该字段 |
| 载荷、工程 gate、模型、Native | 均未执行 |

诊断历史不省略：第一次错误使用非 `.icode_output` 工单路径，被 CP 拒绝；改用现有 `next_out_dir` 后，第二次把 ambiguous 预期为 True 导致断言失败。最终按实际字段核实，并回读原始 returncode/gate_id/error，命令 exit 0。这些不是源码修复的 RED/GREEN，也不是完整 gate 已真实重执行载荷的证明。

临时工单已由 scoped TemporaryDirectory 清理；没有保存原始事件包供第三方重放，因此只授本次实际 admission 观察。没有触碰主工程工单或补 finish 来伪闭合未知动作。

CP-02 须分别记录公共 resume 未决拒绝、同 recorder 新 occurrence 拒绝、内部 fresh-recorder 同 request 缺口。第三项需另立最小 production 修复及真实负控，**不能把前两项通过写成 CP-02 整体通过**；不修改 vendor 或替换资源/CP 结果来取绿。

## 3. 自检与剩余门

【架构级自检报告】仅文档与 admission 诊断层：

- ✅ 语法/结构：Markdown、表格、相对链接与两类诊断命令解析已核；无生产编译声明。
- ✅ 依赖/调用链：巡检生成→独立重建验证→step finish、CP start→recorder→gate/resume 分别核对。
- ✅ 逻辑/边界：分析/实测、幂等记录/执行、公共/内部路径明确区分。
- ✅ 异常处理：保留两次诊断失败历史与未知载荷状态，不补造终结或覆盖率。
- ✅ 关联模块：Git 修复可继续；桥接对应完整正控与重放门明确未通过。
- ✅ 兼容安全：无源码、权限或 Native 改动；新增 vendor 授权待回复。
- ⚠️ 可运行性：上述巡检生成/原验证与 admission-only 诊断已实际运行；完整步骤、源码修复、整链及 R2/R3 尚未验收。
