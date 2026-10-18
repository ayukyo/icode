# R5 规格：开放生态（2026-10-19）

**状态**：v1，实施中。继承 `docs/icode-agent-product-architecture.md` §13.9 与主序规则（前一阶段通过退出门槛后才展开本阶段；R4 四条门已验收通过，候选 `a58c81d`/HEAD `40b37e9` 三 run 全绿，规格见 `nbl/specs/2026-10-18-r4-context-and-model-capability.md`）。

## 1. 目标与边界

扩展工具、知识和使用入口，**但不转移核心控制权**。控制面契约（gates.json / ICODE-SKILL 状态机 / 事件链 / 证据绑定 / Guard-Sandbox-Approver 治理链）不变：R5 只新增“如何把外部能力接进既有治理链”，任何扩展都必须穿过与内建工具相同的裁决链，不存在旁路。**ICODE 创新落地**：扩展不是只有工具 schema，还必须携带可执行权限与证据契约（声明不全即不可执行）。

## 2. 范围（对应 §13.9 五项工作）

| # | 工作 | 落地物 |
|---|---|---|
| W1 | 扩展契约 schema（权限/输入/输出/副作用/证据） | `src/icode/extension_contract.py`：manifest 校验（缺 `opclass`/`side_effects`/`evidence` 任一即拒绝注册）、schema 中**不存在**控制面/账本写入授权位、证据需求复用 `engineering_evidence` 的 binding 字段集（`command_sha256`/`artifact_hashes`/`output_sha256`/`exit_code`） |
| W2 | 生命周期 Hooks（只收紧） | `src/icode/hooks.py`：hook 注册表（事件、声明式收紧、审计事件）；沙箱侧收紧经既有 `sandbox_policy.tighten_policy` 判定；Guard 侧收紧用同语义的**只减不增**判定（deny 模式只加不减、命令白名单只减不加）；hook 无法触及 gates.json/契约 |
| W3 | MCP 工具接入 | `src/icode/extensions/mcp_client.py`（标准库 stdio JSON-RPC 客户端：initialize/tools/list/tools/call，有界读、超时、拒绝服务端推送的非协议方法）+ 适配器把 MCP 工具包成 `Tool`，走 Guard→Approver→副作用回执→registry 同一治理链 |
| W4 | ACP/IDE 前端 | `src/icode/acp.py`：stdio JSON-RPC 交互前端。**只承载交互**：提交既有 intent、接收 `on_event` 子集与公开工单投影；方法白名单封闭，不可调用工具处理器、不可旁路 Guard/Approver、不可写账本 |
| W5 | CI/工单/代码托管连接器 | `src/icode/connectors.py`：连接器注册表（kind/endpoint/副作用类/证据需求）；每次调用作为 operation 记录并绑定证据；未启用/未声明即不可执行；真实网络调用沿用“按连接器独立门控”的 canary 口径 |
| W6 | Skills/Recipes | Recipe 作为**声明式组合**（只引用既有 step/hook/tool，声明权限与证据）；Skill 侧沿用既有 vendor skill 资源暂存与白名单机制，不新增执行旁路 |

## 3. 影响面与安全边界

- **正面**：新增 6 个模块与对应测试；`tools/base.py` 的 `Tool`/`ToolRegistry` 被扩展复用但**不加 permissions 字段**（权限继续由 Guard 裁决，保持单一裁决点）；hook 合并点位于 runner 构造 Guard/SandboxPolicy 处，复用 `tighten_policy`。
- **风险与控制**：MCP 客户端与 ACP 前端都是**独立进程/会话**边界——客户端只实现协议方法，不持有控制面路径句柄；ACP 方法白名单封闭，未知方法返回稳定错误码；hook 收紧先判定后应用，放宽一律拒绝并留审计事件；连接器证据缺失即拒绝落账。
- **不适配**：不引入第三方 MCP SDK（core 零依赖不变，客户端用标准库实现；vendor skill 的 MCP server 继续用其自有 SDK，两者是不同边界）；不做远程工单/CI 系统的双向同步（v1 只做“带证据的出站调用 + 回执入账本”）；不做 IDE 插件的图形侧（v1 只做协议前端）；不放宽任何 Guard/Sandbox/门禁语义。
- **暂缓**：真实连接器 canary（需要真实 CI/工单/托管平台凭据，与 R4 真实模型 canary 同口径——用例已备，缺凭据即跳过并说明原因，跳过不等于通过）；MCP 服务端发现与第三方扩展市场（v1 只接显式配置的本地进程）；ACP 的 IDE 侧 UI。

## 4. 验收计划（逐条对应退出门槛）

| 门 | 判据 | 证据 |
|---|---|---|
| G1 MCP 工具不能直接写控制面或账本 | ① 契约校验拒绝任何声明控制面/账本路径授权的 manifest；② MCP 客户端协议面只有 initialize/tools/list/tools/call，恶意服务端推送文件/控制面请求 → 稳定拒绝；③ MCP 工具经适配器后与内建工具同链裁决（Guard/Approver/回执），测试用假服务端验证拒绝与回执 | 新增 `tests/test_extension_contract.py`、`tests/test_mcp_client.py`（假服务器子进程，离线） |
| G2 ACP 只承载交互，不接管 Agent 循环 | ① 方法白名单封闭：未知/畸形方法返回错误且不触达工具处理器；② ACP 会话只能提交既有 intent 并读公开投影；③ ACP 无法启动/停止/注入循环内部；④ 事件流为 `on_event` 子集且不含未公开字段 | 新增 `tests/test_acp_frontend.py`（假控制器，离线） |
| G3 Hooks 只能收紧，不能放宽 | ① 沙箱侧：放宽候选被 `tighten_policy` 拒绝，收紧候选被接受（roots/deny/protected/limits/network 逐维）；② Guard 侧：增加 deny 或收缩白名单被接受，移除 deny/扩张白名单被拒绝；③ 试图改 gates.json/契约的 hook 无路径可达；④ 拒绝产生审计事件 | 新增 `tests/test_hooks.py` + 复用 `test_sandbox_policy` 既有 tighten 用例 |
| G4 未声明副作用和证据要求的扩展默认不可执行 | ① manifest 缺 `opclass`/`side_effects`/`evidence` 任一 → 注册拒绝（ fail-closed）；② 证据需求字段复用绑定集，缺字段的调用拒绝落账；③ 违规尝试产生稳定错误码与审计事件，不静默放行 | `tests/test_extension_contract.py` + `tests/test_connectors.py` |
| 连接器证据链 | 连接器每次调用记 operation + 证据绑定（复用 `_public_binding` 字段集），未启用/未声明 → 不可执行 | `tests/test_connectors.py` |

**阶段完成判据**：四条门全部绿 + 新增模块单测全绿 + 全量套件零新增失败 + CI 全绿（双腿 Windows 快照、provenance、Linux native probe 等既有项不回退）。失败/跳过不得计为通过。

## 5. 显式偏离

- MCP 客户端用标准库实现而非官方 SDK：core 零依赖是比“协议一致性”更高的约束；协议面收敛到三个方法，覆盖度以测试声明为准，不宣称完整 MCP 兼容。
- Hook v1 定义为**声明式收紧 + 有界观察**：hook 可以提出策略收紧（经只紧判定）或产出自持有界观察，不提供任意代码写路径；“只收紧”以 `tighten_policy` 的同一语义为判定基准，而非信任 hook 自觉。
- ACP v1 是 stdio JSON-RPC 交互前端而非 Zed ACP 完整实现：方法集按“只承载交互”最小原则自定义，命名为 ACP 兼容前端而非 ACP 协议实现。
- 连接器 v1 只做出站调用与回执，不做入站 webhook 服务端（避免新增网络监听面，与既有仅回环 HTTP 基线一致）。

## 6. 实施记录

（实施后填写：逐工作项落地、测试锚点、CI/真实 canary 结果。）
