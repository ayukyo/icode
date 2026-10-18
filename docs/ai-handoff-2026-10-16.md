# ICODE Agent：交给另一 AI 的开发接力

核对日期：2026-10-18（北京时间）。这是当前接力入口；旧 `development-handoff.md` 是按时间追加的历史账，不要把其中“当前、尚未实施、正在运行”脱离日期当作最新事实。**2026-10-18 最新进展：候选 `1fdfa41` 已推送 main，两个 Windows Reviewer 快照 job（windows-latest x64 + windows-11-arm）CI 双腿首绿——readonly admission（无豁免）、WFP observer 四步、Reviewer 快照探针步（三元网络证据：只读配置证实候选零豁免 + 正控临时豁免实测双栈 canary + 候选无连接无 canary）全部通过；R2/R3 既定验收目标达成。余下红项原为预存在（`commands` 陈旧钉锁 + 2 个 Linux 专有 `SO_EXCLUSIVEADDRUSE` 环境错误），已按用户授权“按你推荐的来”同口径刷新钉锁并加平台守卫（Windows 腿保留真实覆盖），R2/R3 既定目标已在决策日志与 development-handoff.md 正式结案。证据链、三轮 CI 诊断与结案记录见 development-handoff.md “候选 1fdfa41”节。**

## 1. 目标和产品定位

继续完成既定 **R2 跨平台隔离及独立安装**、**R3 自验证和真实研发闭环**的全部必要验收，不能把局部通过、skip、设计文档或签名安装成功当整体验收。

ICODE Agent 是独立 Agent，不是 ICODE-SKILL 的别名。底层复用 Skill 的流程和逻辑，Agent 负责运行、隔离、权限、工单/会话、验证及用户界面。面向不懂代码术语的普通用户，采用易懂的工单界面，但主要处理软件研发任务；支持按环境中英双语、会话/自动模式。目标能力至少与既定 Skill 对照矩阵 90% 一致，不能靠删减矩阵达标。

安装方向是 Python 包入口，借鉴 uv 管理独立 Python 环境，不要求用户处理系统解释器。产品最低 Python **3.12**；本地历史 3.11.17 仅用于定向软件诊断，不代表恢复 3.11 支持。

## 2. 首先核对现场

- 仓库：`ayukyo/icode`，分支 `main`，本地及远端 HEAD 为 `de637acdd8ab79dbb58ce3e78e79c47ee0abb827f`（d6a7a3a 为上一交接核对点，结果已被 de637ac 候选推进）。
- 权威代码在已确认的 WSL 原生工作区，**不是旧 Windows 副本**。机器位置及诊断解释器见该权威仓库的 `.git/AI-HANDOFF.local.md`；该文件只在本机，不上传。
- 整理前，Agent 唯一 tracked dirty 是 `docs/development-handoff.md` 的两行最新候选记录，index 空。本次又新增本文、更新旧接力入口；它们是交接文档，不是未提交产品修复。
- 固定子仓 `vendor/icode-skill`：`21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。不要直接指向独立 Skill 的最新 main。
- 独立 ICODE-SKILL 本地 HEAD：`cd9889f2ae4cb1090963338ad72412f526342ea5`，留有下文五个 TEST-only 文件；不得清理或提交猜测性修复。
- 文档目录存在 ignored 的本地计划；只 clone Git 不会带走它们和 Skill 的未提交测试。切换机器前应单独、经用户同意转移，不能声称都在远端。

开始时只读运行 `git status --short`、`git diff --cached --name-only`、`git log -5 --oneline`、`git submodule status` 并重新查询 GitHub。上述是交接快照，不是永远有效的锁。

## 3. 最新线上结果：d6a7a3a，attempt 1（已被 de637ac 推进，见 development-handoff.md 同节新记录）

**当前远端及本地 HEAD：`de637acdd8ab79dbb58ce3e78e79c47ee0abb827f`（52ce9b4 盘根迁移 + 本文档更新）。** 候选 de637ac 的 CI `39000099220`：45 job 39 成功 / 3 失败 / 3 跳过；Windows 双快照 job 的 readonly admission（无豁免）与 WFP observer 步骤首次全绿，仅 Reviewer 快照探针步因零能力 AppContainer 网络双栈实测 `10035` 超时而非 `10013` 失败（双腿 exit 78），与 2026-10-05 记录的 OS 机制边界一致；Python 3.12 与 provenance 失败集同上一候选逐项一致，无回归。详细收据、已知“不适配”清单与待用户决策选项见 `development-handoff.md` 的 de637ac 节；未获用户授权前不放宽任何网络门。

以下在本次交接中从 GitHub API 和关键完整原日志重新核对，**全部已终态**。

| 工作流 | 结果 | 证据 |
| --- | --- | --- |
| CI | 45 jobs：40 success、2 failure、3 skipped | [38706002261](https://github.com/ayukyo/icode/actions/runs/38706002261) |
| Windows helper provenance | 3/3 success | [38706002204](https://github.com/ayukyo/icode/actions/runs/38706002204) |
| 官网 | 2/2 success | [38706002225](https://github.com/ayukyo/icode/actions/runs/38706002225) |

关键 job：

- 全量 `116325467105`：3624 tests / 721.560s，`OK (skipped=100)`。100 skip 不授对应平台能力信用。
- Windows x64 `116325467953`：202 项软件测试通过（21.531s），SDK oracle 构建 step 成功；**实际 readonly admission 失败**，输出 `{"schema":1,"stage":"readonly_failed","state":"unknown"}`。
- Windows ARM64 `116325468334`：202 项软件测试通过（18.255s），SDK oracle 构建 step 成功；**相同 readonly admission 失败**。
- 两个失败 job 后续 WFP、实际标准用户 Reviewer 均 skipped。不要报告本候选执行了网络 DENY、旧正控 105 或 Reviewer 78；这些是更早候选的历史事实。
- provenance validate `116325467187`、签名安装 x64 `116332122545`、ARM64 `116332122712` 均 success；签装成功不证明可信启动、首次 UAC、受保护晋升或 WP0b 整体通过。
- 三 run 均已终态，旧候选等待门已解除；不需重新运行旧候选来抹去失败。

关键完整日志本轮实际获取：x64 71852 字符、ARM64 74317 字符、full 866521 字符。工具会话内存不是长期证据存储；按上面的 workflow/job 重新下载原日志，不依赖旧 agent、RAM key 或临时签名 URL。

## 4. 第一优先任务：定位实际 readonly admission 失败

不要继续修已经线上通过的 202 项模型路径，也不要重复更新已通过的 CI 摘要。

1. 读取上述两个失败 job 的完整日志和当前实际实现，确定失败发生于 Gate 构造、freeze、账号创建、suspended parent、private readonly entry、原件重开验证还是 finally。
2. 当前 helper 的顶层异常路径只导出 `readonly_failed/unknown`，未给出足够阶段信息。**根因尚未证实**。如需补诊断，只提供有界阶段/错误类别；不输出密码、完整 SID 列表、任意 traceback 路径或开放任意 root/command。
3. 按真实调用链补测试、复现失败，再最小修复。不能删隔离断言、降低 ACL/加载边界、换成功假对象、把 unknown 改 true 或加 skip。
4. 保持本机定向诊断，完整及原生验证走同候选 GitHub x64/ARM64。
5. 两架构真正通过 readonly gate 后，再推进原 Task 4 consumer。SDK 构建成功不等于全部 ABI 比较和系统生命周期已通过。

主要实现与测试：

- `scripts/windows_positive_admin_readonly_gate.py`
- `scripts/windows_positive_loopback_admin_entry.py`
- `scripts/windows_positive_loopback_admin_native.py`
- `scripts/windows_positive_loopback_admin_store.py`
- `scripts/windows_positive_loopback_admin_win32.py`
- `scripts/windows_positive_loopback_admin_jobs.py`
- `scripts/windows_positive_loopback_admin.py`
- `tests/test_windows_positive_admin_readonly_gate.py` 及 `tests/test_windows_positive_loopback_admin*.py`
- `.github/workflows/ci.yml` 中 `windows-reviewer-snapshot-probe`
- `native/windows/icode_positive_loopback_admin_abi.c`、对应 CMake target。

原只读门计划：[SOURCE](nbl/plans/2026-10-15-windows-positive-admin-readonly-gate.md)、[TEST](nbl/plans/2026-10-15-windows-positive-admin-readonly-gate-tests.md)。计划用于理解合同，当前实际源码及同 SHA 日志优先；计划的旧字节不能覆盖后来已提交的测试修复。

## 5. 最近已完成的修复，不要重做

| 提交 | 已做事项 | 仍不能外推 |
| --- | --- | --- |
| `39030d2` | CI-only admin/完整 Get/受保护账本/Job 与软件测试 | 当时没有实际 readonly 接线验收 |
| `d954840` | Host CMake 测试夹具只截取标记区间，不误带新增 SDK target | 不证明 Windows SDK/native |
| `4fff535` | 新 readonly orchestrator、30 测试、CI 三个前置步骤 | 原候选被旧模型路径和摘要契约挡住 |
| `b6dba5e` | 三个旧 TEST 的 host-absolute/canonical 路径；生产 guard 未改 | 现在已在双 Windows 202 项软件门通过，但 native 仍失败 |
| `d6a7a3a` | CI 命令由89增为92后更新已审核摘要；权限及 provenance 摘要不变 | 全量已通过，不是 R2/R3 全通过 |

## 6. 后续 Task 4 的正确合同

本节只是接点提示，**consumer 尚未实现，不能直接凭摘要跳过完整方案审查**。

- freeze privileged runtime 必须早于临时标准用户创建。受保护账本不放标准用户可修改的 probeRoot。
- 真正标准用户 parent 必须 suspended 创建、持原始句柄、校验 PID+creation+SID、绑定 outer Job 并持久化后才 Resume。
- 不能复用 readonly gate 已被终止的 parent。
- 顺序是：实际 `CreateProfile` 成功且 SID 等于预分配正控 SID → `created` 握手 → admin 单 SID add 并核原件 → 原固定双栈 payload。
- **不是 profile 创建前 add。** `finished`/cleanup 必须在 wrapper 的 payload finally 内、profile delete 前；wrapper 返回后补调用太晚。
- 正常 finally 与独立 workflow `always` 恢复分开；先确认 add 命令实际退出，避免 late add/delete 竞争。不能以删账号、删 profile 或 runner 销毁冒充配置恢复。
- 仅 CI 临时 runner 的一个预分配 positive SID 可豁免；永不豁免 Reviewer/foreign SID，不 Set 全列表，不回放旧快照，不增加本机权限、服务或自由提权入口。
- bootstrap 180s 与 operation ≤60s 为不同不可变域；异常恢复保留独立预算及原 first error。
- 正控双栈可达不自动证明零 capability Reviewer 的 DENY；超时或 WFP 无匹配仍不确定。

依据：[临时豁免设计](nbl/specs/2026-10-15-windows-ci-positive-loopback-exemption-design.md)、[admin binding 补充](nbl/specs/2026-10-15-windows-ci-positive-loopback-admin-binding-design.md)。

## 7. ICODE-SKILL：当前不得继续修改

用户要求**每一批**跨仓修改先明确同意，范围包含源码、测试、配置及所有副本；普通“继续”、本次交接或旧批授权不等于新批准。下一批 business-consumer/worker SOURCE/CI 尚无新批准。不要默认推送或升级 Agent pin。

独立 Skill 留下的五个 TEST-only 文件：

- `tests/test_candidate_code_inspection_provider_unit.py`（modified）
- `tests/test_candidate_business_consumers_unit.py`（untracked）
- `tests/test_candidate_consumer_closure_unit.py`（untracked）
- `tests/test_candidate_derived_consumers_unit.py`（untracked）
- `tests/test_candidate_workflow_worker_unit.py`（untracked）

这些是先前阶段保留的工作，不是垃圾或新实现完成。相关本地计划 `docs/nbl/plans/2026-10-15-protected-git-business-consumers.md` 可能被 ignore，不能假定已在远端。获批后按真实 RED、最小 SOURCE、独立审查和必要验收收尾，推 Skill main 后再精确更新 Agent gitlink。

旧 `generic-skill-hardening` 临时工作区此前已核无独有差异并移除；不要重建或把旧实现覆盖较新的 main。任何新清理先核现场，不凭历史记录删目录。

## 8. R2/R3 原范围仍开放

下列来自原阶段接力的未闭合清单，交接本轮未逐项重新跑验收；接手者须回原设计/矩阵核实，不能缩减目标：

- Windows：当前 readonly admission；真实正控 consumer/恢复/Reviewer 网络证据；WP0b 来源、proof、加载边界、首次 UAC、受保护晋升、跨管理员及 parent-death。
- Linux：受保护 Git 上下文到实际业务 consumer/worker 的传播；外置工单/隔离代码根合法契约；S2c/S3 实际安装矩阵；自动准入及 policy-ready 合同。
- R3：真实模型 plan→review→merge→code→deepcheck→audit 六步链、code worklist、候选新鲜度、最终交付及≥90%能力对照。
- macOS：单任务进程配额及必要身份/安装/生命周期原生矩阵未整体验收。用户已接受 Codex 式沙箱继承+同组清理，不承诺主动脱组后代零残留；不能以用户级限额/轮询终止替代硬配额。已有高权限初始化方案的授权不等于验收通过；此前工具拒绝不能通过换工具、改措辞重试绕过。
- 安装/UX：uv 独立运行环境、纯 Python 包入口及平台实际能力要分别验证；不能用官网“最终效果”描述当当前产品证据。

R2/R3 未全部必要验收通过前，不开放不合格平台自动模式、不发布整体完成声明、不用绿色软件测试替代隔离实证。

## 9. 执行约束与交接验收

1. 阅读当前 `AGENTS.md`，其优先于旧文档中的历史协作约定。复杂修改先实际 sequential-thinking MCP 至少三步；无该工具时不能伪造调用记录。
2. main-only，不创建分支/worktree/tag；阶段候选可按用户既有授权提交推送，不等于发布或阶段通过。本次整理没有新增提交、推送或产品变更。
3. 线上优先；本机只做必要定向回归、密钥及固定子仓检查。本机编译默认 `-j1`，最大 `-j6`；不默认本机 full、安装软件或提权。
4. 新候选提交前核 scope、index 白名单、密钥、vendor pin 和独立审查；每轮线上记录完整 SHA、run/job、架构、原日志、退出、skip 范围。前一候选全部工作流终态后再下一 push。
5. 诊断、TDD、独立规格/质量审查不可被计划围栏或旧 RAM 投影替代；错误/skip 不当通过，缺组件断言不当行为根因 RED。
6. 开发并行只读研究，优先 [持续竞品对照](agent-landscape-live.md) 的固定源码证据；选择性借鉴机制，标采纳/暂缓/不适配，保留日期与许可边界。文档交接无需另启动竞品研究。
7. 凭据只在确需模型验收时从用户指定的本地文件读取；不要打印、放文档、复制到仓库或上传。本文不包含密钥。
8. 原有未提交文件归用户/既有工作；禁止 reset/clean/猜测恢复。切换 AI 不代表批准清理工作树。

建议给新 AI 的第一条指令：

> 请先读取本接力文档、权威仓库 `.git/AI-HANDOFF.local.md` 和当前 AGENTS.md，核对 HEAD/status/pin 及 d6a7a3a 的同 SHA CI。不要修改 ICODE-SKILL，不重做已过的路径和摘要修复。先定位双 Windows readonly admission 的真实失败阶段，按测试先行最小修复并线上验收，再继续原 R2/R3 全部必要项；不得靠 skip 或缩减指标完成。

## 本次交接的架构级自检报告

- 语法/格式：新接力入口和本地环境文件连续两轮一致性检查均零疑似项；diff whitespace通过。没有新增代码编译结论。
- 依赖/调用链：新入口指向现存设计、测试、实现及准确job，旧入口已链接新入口。
- 逻辑/边界：当前终态与历史状态分开，软件、构建、原生准入和整体验收不混算。
- 异常处理：readonly失败阶段仍unknown，明确列为下一步诊断，不虚称已定位/修复。
- 关联模块：没有修改产品、CI、SDK、Skill或固定gitlink；保留既有未提交记录和五个Skill测试。
- 兼容安全：无系统操作、无凭据读取、无commit/push；机器定位放Git元数据本地文件，不写协作规范。
- 可运行性：本次只验证文档及读取现有线上结果；R2/R3尚未整体通过，不报告产品100%可运行。
