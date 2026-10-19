# R6 规格：受控多 Agent（2026-10-19）

**状态**：v1，实施中。继承 `docs/icode-agent-product-architecture.md` §13.10 与主序规则（前一阶段通过退出门槛后才展开本阶段；R4 四条门已验收通过，R5 六项工作与四条门已实施并通过 CI，规格见 `nbl/specs/2026-10-18-r4-context-and-model-capability.md` 与 `nbl/specs/2026-10-19-r5-open-ecosystem.md`）。

## 1. 目标与边界

在单 Agent 稳定后引入**职责明确、权限受限、过程可审计**的协作。控制面契约（gates.json / ICODE-SKILL 状态机 / 事件链 / 证据绑定）不变：R6 只新增“角色如何被分配身份、上下文边界、写范围与证据责任”，不新增第二真源，不放宽任何门禁。

**初始角色（封闭词表，§13.10）**：Planner / Executor / Reviewer / Verification Agent / Evidence Auditor。每个 Agent 必须拥有独立上下文、明确读写范围、独立 operation 身份、独立 worktree 或只读视图。**子代理不得自行扩大权限或把写能力继续委派给未知 Agent**——本规格以“无扩权/委派 API + 冻结角色 + fail-closed 能力校验”结构性保证，不依赖自觉。

## 2. 范围（六项工作）

| # | 工作 | 落地物 |
|---|---|---|
| W1 | 角色契约与身份 | `src/icode/roles.py`：封闭角色词表（planner/executor/reviewer/verifier/auditor）；`AgentRole` 冻结数据（may_write 仅 executor 为真、may_delegate 恒为 false、证据责任字段）；`spawn` 分配稳定身份 `role#ticket#ordinal`；能力校验 fail-closed（未知角色、身份重复、越权书写一律稳定错误码） |
| W2 | 区域写租约（防未检测写冲突） | `src/icode/write_lease.py`：区域（工作区相对路径前缀）→ 持有者租约；进程内区域表 + 跨进程文件锁（POSIX `flock` / Windows `_locking`，与既有 `TicketLease` 同一纪律）；重叠区域（相等或前缀相关）冲突、相异区域并行；`LeaseBusy` 稳定码，绝不静默放行 |
| W3 | 角色上下文派生 | `agent_scope.py`（或并入 W1）：按角色派生沙箱策略与 Guard 作用域——reviewer/verifier/auditor 走 `write_roots=()` + deny 追加 + 网络 DENY，并过 `tighten_policy` 只紧判定（复用 `derive_read_only_reviewer_policy` 的纪律，不限于 review 步）；executor 写范围收敛到其分配区域 |
| W4 | 结论账本（可追溯） | `src/icode/agent_conclusion.py`：`AgentConclusion` 冻结记录（agent_id/role/ticket_id/step/context_digest/evidence/outcome/detail + 自描述 digest）；缺身份、缺上下文边界或空证据一律拒绝入账；账本有界、只增；公开投影只含稳定字段 |
| W5 | 编排器与门禁 | `src/icode/multi_agent.py`：`AgentTeam`（spawn/run/run_parallel/step_gate）；run 在身份校验、（executor 必须申报区域且策略收敛到该区域）、（按需）写租约、结论入账多段保护下执行调用方注入的角色逻辑——executor 的结论边界摘要即收敛后策略指纹；`step_gate(required_roles)` 只有全部所需角色都有 `completed` 结论才放行——任一代理失败/拒绝即 blocked（G4）；角色分离：executor 结论不能满足 reviewer 要求（不自审） |
| W6 | 证据接入 | 结论 digest 与 agent 身份经既有 `attach_evidence`（R5）进入证据绑定；控制面侧沿用既有 `record_verification`/`step_finish`/回执通道。**不修改 vendor/icode-skill**：gates.json 角色契约键与 `record-agent-spawn/result` 包装列为暂缓（需用户对 ICODE-SKILL 的明确授权，见 §5） |

## 3. 影响面与安全边界

- **正面**：新增 5-6 个模块与测试；复用而不改动：`tighten_policy`/`derive_read_only_reviewer_policy`（sandbox_policy.py:470/534）、`reviewer_guard` 只读构造（reviewer.py:98）、`OperationRecorder` 身份与幂等键纪律（operations.py:38-102，含跨步骤 occurrence 撞键教训）、`TicketLease` 锁文件纪律（workspace.py:169-220）、R5 `attach_evidence`。
- **风险与控制**：租约锁文件落在显式 lease 目录（不进工作区、不进账本目录）；锁先于任何写入获取，零长 inode 先锁再写；结论账本只增有界；编排器无网络、无文件旁路（写范围只经租约+策略表达）；并行执行上限有界（默认 4，可配置但封闭）。
- **不适配**：不引入 agent 间自由消息/投票/聊天；不做跨机器协调；不把“多数结论”当门禁（门禁只认角色完成的契约）；不动 vendor/icode-skill 任何文件；不用第三方并发框架（标准库 threading）。
- **暂缓**：每个 Executor 真实 git worktree 分配（v1 经注入的 session 工厂 + 区域租约表达边界，真实 worktree 执行属下一增量）；gates.json 角色契约键与 `record-agent-spawn/result` 的 ControlPlane 包装（需 ICODE-SKILL 授权）；跨进程编排（v1 为进程内并行：线程 + 跨进程区域锁已备）。

## 4. 验收计划（逐条对应退出门槛）

| 门 | 判据 | 证据 |
|---|---|---|
| G1 并行 Agent 不发生未检测的工作区写冲突 | ① 重叠区域（相等/前缀相关）第二个获取者被 `LeaseBusy` 拒绝且不留锁；② 相异区域可并行（线程实测两写者互不阻塞）；③ 持锁者异常退出后租约可回收（上下文管理器/finally）；④ 只读角色连租约都申请不到（稳定码） | 新增 `tests/test_write_lease.py` + `tests/test_multi_agent.py` |
| G2 Reviewer/Verifier/Auditor 默认只读 | ① 三角色派生策略 `write_roots=()`、deny 追加、网络 DENY，且过 `tighten_policy` 只紧判定；② Guard 作用域 `allowed_write_roots=()`；③ 只读角色调用写工具/申请写租约/携带写区域运行均被拒（稳定码），不降级 | 新增 `tests/test_roles.py`（或 agent_scope 测试） |
| G3 每项代理结论都能追溯到身份、上下文边界和证据 | ① 结论缺 agent_id/role/ticket_id/step/context_digest/evidence 任一 → 拒绝入账；② 同输入 digest 稳定、可复算；③ 公开投影有界且不含正文；④ 上下文边界用策略/作用域指纹（canonical_json sha256）而非自报 | 新增 `tests/test_agent_conclusion.py` |
| G4 任一代理失败不会绕过当前步骤门禁 | ① 所需角色缺结论/结论非 completed → `step_gate` blocked（稳定码列出缺口）；② executor 结论不能满足 reviewer 角色要求（角色分离，不自审）；③ 代理调用抛异常 → 记 failed 结论且门禁仍 blocked，异常正文不外泄；④ 门禁无任何放宽路径（无 override/force 参数） | 新增 `tests/test_multi_agent.py` |
| 子代理不扩权/不委派 | ① 角色数据冻结，无 grant/escalate/delegate API（源码结构断言）；② 以只读身份申请写能力 → 稳定码拒绝；③ spawn 出的未知 role 名 → 拒绝 | `tests/test_roles.py` + `tests/test_multi_agent.py` |

**阶段完成判据**：四条门全部绿 + 新增模块单测全绿 + 全量套件零新增失败 + CI 全绿（双腿 Windows 快照、provenance、Linux native probe 等既有项不回退）。失败/跳过不得计为通过。

## 5. 显式偏离与暂缓

- **不修改 ICODE-SKILL**：§13.10 说“由 ICODE-SKILL 契约分配职责、权限和证据责任”，但按仓库约定修改 ICODE-SKILL 需用户对该批改动的明确同意。v1 角色契约放在 ICODE 侧封闭词表，gates.json 角色键/`record-agent-spawn/result` 包装待授权后增量接入；控制面入账仍走既有事件与回执通道。
- v1 并行范围为**进程内**（线程 + 跨进程文件锁已备但编排器不跨进程）：跨进程编排需要控制面 spawn 协议授权后增量。
- worktree 分配经注入工厂表达，不新建第二套 worktree 机制（复用 `workspace.py` 既有会话）。

## 6. 实施记录

- **W1 角色契约**：`src/icode/roles.py`。封闭五角色词表（`AgentRole` 冻结，`may_delegate` 恒 False 属性）；`spawn` 分配 `role#ticket#ordinal` 稳定身份（`parse_agent_id` 可独立校验形态）；`assert_may_write`（未发放身份/只读角色 → 稳定码）、`assert_conclusion_kind`（跨角色顶替拒绝）。测试 `tests/test_roles.py` 12 项。
- **W2 区域写租约**：`src/icode/write_lease.py`。`normalize_region` 接受字符串或段元组（拒绝绝对路径/父目录逃逸/控制面目标，与 R5 同一黑名单）；`regions_overlap` 前缀相关即重叠；`WriteLeaseBoard` 进程内区域表（线程互斥）+ 跨进程文件锁（POSIX flock / Windows msvcrt，先锁后写零长 inode，TicketLease 同纪律）；**租约释放自动从区域表除名**（`WriteLease` 回连所属板，with 块/直接 release 均安全）。测试 `tests/test_write_lease.py` 10 项（含子进程跨进程竞争实测）。踩坑修复：`BufferedReader.read(n)` 类似问题未犯，但 `read1` 教训沿用为有界读；释放不除名曾导致幽灵占用（已修）。
- **W3 上下文派生**：`src/icode/agent_scope.py`。`derive_agent_policy`（只读角色 `write_roots=()` + deny 追加 + 网络 DENY，过 `tighten_policy` 只紧判定，不绑定 review 步）；`derive_agent_guard_scope`（只读角色 `allowed_write_roots=()`）；`scope_fingerprint` 用解析后绝对路径+白名单计算边界摘要（边界算出来，不自报）；策略侧直接用既有 `policy_hash`。测试 `tests/test_agent_scope.py` 8 项。
- **W4 结论账本**：`src/icode/agent_conclusion.py`。`AgentConclusion` 冻结（身份形态/角色-结论类型一致/`context_digest` 必须 sha256/`outcome` 封闭/`completed` 必须带非空标量证据且 ≤4KB、`failed`/`refused` 以稳定码为内容——不伪造不存在的工作产物证据）；自描述 digest（canonical sha256，幂等重录）；`ConclusionLedger` 只增有界（写满 fail-closed）、线程安全、按 role+kind+step 查询。测试 `tests/test_agent_conclusion.py` 10 项。
- **W5 编排器**：`src/icode/multi_agent.py`。`AgentTeam.spawn`（无策略/作用域即拒——没有边界就没有独立上下文）；`run` 三段保护：身份核对 →（executor 且给定区域）租约 → 结论入账；**run 不抛执行异常**——工作异常/空证据/区域竞争都记 `failed`/`refused` 结论（稳定码，正文不外泄），只有编程错误（未知身份、只读角色申请写区域）抛 RoleError；`run_parallel` 线程有界、线程内异常必须浮出（曾修复静默丢结果的缺陷：LeaseBusy 处理时 `kind` 未赋值的 UnboundLocalError 被线程吞掉）；`step_gate` 只认本步骤内所需角色的 completed 结论，无 force/override 参数（源码结构断言）。测试 `tests/test_multi_agent.py` 17 项。
- **W6 证据接入**：结论 digest/agent_id 进入证据载荷（`run` 把 `agent_id`/`context_digest` 注入 completed 证据）；控制面入账沿用既有事件与回执通道；gates.json 角色键与 `record-agent-spawn/result` 包装按 §5 暂缓（待 ICODE-SKILL 授权）。

**本机测试台账**：新增 57 项（12/10/8/10/17）全绿；密钥扫描通过；全量套件结果见 CI 验收记录。
