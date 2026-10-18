# R5 规格：开放生态（2026-10-19）

**状态**：v1.1（已按独立评审修订）。评审代理误读了过期兄弟检出 `D:\Projects\icode`（HEAD 停在 `7aad12c`），故其 BLOCKER-1“规格不存在”不成立——本文件自提交 `e194149` 起在权威仓库（WSL `/home/orbbec/projects/icode`）。BLOCKER-2/3/4 与各 MAJOR 已逐条落入下文（消息分发层强制、batch 整体拒绝、MCP 工具必须走 ToolRegistry、ACP 不得成为第二 intent 入口、Guard 收紧词表边界、连接器证据通道）。继承 `docs/icode-agent-product-architecture.md` §13.9 与主序规则（前一阶段通过退出门槛后才展开本阶段；R4 四条门已验收通过，候选 `a58c81d`/HEAD `40b37e9` 三 run 全绿，规格见 `nbl/specs/2026-10-18-r4-context-and-model-capability.md`）。

## 1. 目标与边界

扩展工具、知识和使用入口，**但不转移核心控制权**。控制面契约（gates.json / ICODE-SKILL 状态机 / 事件链 / 证据绑定 / Guard-Sandbox-Approver 治理链）不变：R5 只新增“如何把外部能力接进既有治理链”，任何扩展都必须穿过与内建工具相同的裁决链，不存在旁路。**ICODE 创新落地**：扩展不是只有工具 schema，还必须携带可执行权限与证据契约（声明不全即不可执行）。

## 2. 范围（对应 §13.9 五项工作）

| # | 工作 | 落地物 |
|---|---|---|
| W1 | 扩展契约 schema（权限/输入/输出/副作用/证据） | `src/icode/extension_contract.py`：manifest 校验（缺 `opclass`/`side_effects`/`evidence` 任一即拒绝注册）、schema 中**不存在**控制面/账本写入授权位、证据需求复用 `engineering_evidence` 的 binding 字段集（`command_sha256`/`artifact_hashes`/`output_sha256`/`exit_code`） |
| W2 | 生命周期 Hooks（只收紧） | `src/icode/hooks.py`：hook 注册表（事件、声明式收紧、审计事件）；沙箱侧收紧经既有 `sandbox_policy.tighten_policy` 判定（对当前 `NetworkMode` 集合已证实结构化，新增模式必须同批补判定并加测试锁定）；Guard 侧收紧词表**只含 (deny 模式, 命令白名单) 一对**——`Scope` 的根字段（`readable_roots`/`allowed_read_*`/`deny_read_roots` 等，guard.py:173-187）在 v1 没有 hook 通道，故不存在 None↔tuple 序语义；hook 无法触及 gates.json/契约（未知事件注册即拒） |
| W3 | MCP 工具接入 | `src/icode/extensions/mcp_client.py`（标准库 stdio JSON-RPC 客户端：initialize/tools/list/tools/call，有界读、超时）。**白名单只是必要条件，强制执行点在消息分发层**：每个入站帧过同一白名单（服务端发起请求一律 `-32601`、通知忽略并留审计）；**JSON-RPC batch 整体拒绝**（稳定错误码 `batch_not_supported`，避免混合帧）。适配器把 MCP 工具包成 `Tool` 注册进 `ToolRegistry`（tools/base.py:400-456），经 `registry.invoke` 走 Guard→Approver→opclass 回执同一治理链 |
| W4 | ACP/IDE 前端 | `src/icode/acp.py`：stdio JSON-RPC 交互前端。**只承载交互，且不得成为第二 intent 入口**：意图提交必须映射到既有 `autonomy.normalize_intent_payload`（autonomy.py:426-446）的同一词表并由其解析（白名单外一律拒），会话本身只读控制面公开投影 + 订阅 `on_event`；方法白名单封闭，不可调用工具处理器、不可旁路 Guard/Approver、不可写账本 |
| W5 | CI/工单/代码托管连接器 | `src/icode/connectors.py`：连接器注册表（kind/endpoint/副作用类/证据需求）；每次调用先过 `OperationRecorder` 的 start/finish 回执（operations.py:91-108），证据经回执的 `evidence`/`check_ref` 通道落账，复用工程证据绑定的**字段词表与纪律**（有界、digest、不带正文）而非直接调用 `_public_binding`（其入参是 `VerificationEvidence`，类别不同）；未启用/未声明即不可执行；真实网络调用沿用“按连接器独立门控”的 canary 口径 |
| W6 | Skills/Recipes | Recipe 作为**声明式组合**（只引用既有 step/hook/tool，声明权限与证据）；Skill 侧沿用既有 vendor skill 资源暂存与白名单机制，不新增执行旁路 |

## 3. 影响面与安全边界

- **正面**：新增 6 个模块与对应测试；`tools/base.py` 的 `Tool`/`ToolRegistry` 被扩展复用但**不加 permissions 字段**（tools/base.py:373-393 无该字段，`schema()`:381-390 亦无——扩展的权限声明只存在于 `extension_contract` 的 schema 层，裁定仍只有 Guard 一个裁决点；调用方需收紧 Guard 必须改 `Guard`/`Scope` 代码，无法靠工具 schema 达成）；hook 合并点位于 runner 构造 Guard/SandboxPolicy 处，复用 `tighten_policy`。另注意口径：Guard 对 allowlist 外命令的默认裁决是 `REQUIRE_APPROVAL` 而非 DENY（guard.py:150），收紧语义只针对白名单集合本身。
- **风险与控制**：MCP 客户端与 ACP 前端都是**独立进程/会话**边界——客户端只实现协议方法，不持有控制面路径句柄；ACP 方法白名单封闭，未知方法返回稳定错误码；hook 收紧先判定后应用，放宽一律拒绝并留审计事件；连接器证据缺失即拒绝落账。
- **不适配**：不引入第三方 MCP SDK（core 零依赖不变，客户端用标准库实现；vendor skill 的 MCP server 继续用其自有 SDK，两者是不同边界）；不做远程工单/CI 系统的双向同步（v1 只做“带证据的出站调用 + 回执入账本”）；不做 IDE 插件的图形侧（v1 只做协议前端）；不放宽任何 Guard/Sandbox/门禁语义。
- **暂缓**：真实连接器 canary（需要真实 CI/工单/托管平台凭据，与 R4 真实模型 canary 同口径——用例已备，缺凭据即跳过并说明原因，跳过不等于通过）；MCP 服务端发现与第三方扩展市场（v1 只接显式配置的本地进程）；ACP 的 IDE 侧 UI。

## 4. 验收计划（逐条对应退出门槛）

| 门 | 判据 | 证据 |
|---|---|---|
| G1 MCP 工具不能直接写控制面或账本 | ① 契约校验拒绝任何声明控制面/账本路径授权的 manifest；② **消息分发层**强制：每个入站帧过同一白名单，恶意服务端推送文件/控制面请求（含普通通知、带 id 请求、batch 帧）→ 稳定拒绝并留审计；③ MCP 工具经适配器注册进 `ToolRegistry`，`registry.invoke` 与内建工具同链裁决（Guard/Approver/opclass 回执）；④ 客户端全程不产生任何文件写入（会话后 cwd 零新文件）；⑤ 服务端借 content 回灌的“指令文本”只是数据，不构成执行 | 新增 `tests/test_extension_contract.py`、`tests/test_mcp_client.py`（假服务器子进程，离线） |
| G2 ACP 只承载交互，不接管 Agent 循环 | ① 方法白名单封闭：未知/畸形方法返回错误且不触达工具处理器；② 意图提交经同一 `normalize_intent_payload` 词表解析，白名单外拒——**不存在第二 intent 入口**；③ ACP 无法启动/停止/注入循环内部，不可调 `Loop.run` 或工具 handler；④ 事件流为 `on_event` 子集且只含公开投影字段 | 新增 `tests/test_acp_frontend.py`（假控制器，离线） |
| G3 Hooks 只能收紧，不能放宽 | ① 沙箱侧：放宽候选被 `tighten_policy` 拒绝，收紧候选被接受（roots/deny/protected/limits/network 逐维）；② Guard 侧：收紧词表只有 (deny, 白名单) 一对，增加 deny 或收缩白名单被接受，移除 deny/扩张白名单/返回其他形状一律拒绝；③ Scope 根字段无 hook 通道，hook 无法触碰；④ 试图改 gates.json/契约的 hook 无事件词表可达；⑤ 拒绝产生审计事件；⑥ 网络模式集合锁定测试 | 新增 `tests/test_hooks.py` + 复用 `test_sandbox_policy` 既有 tighten 用例 |
| G4 未声明副作用和证据要求的扩展默认不可执行 | ① manifest 缺 `opclass`/`side_effects`/`evidence` 任一 → 注册拒绝（fail-closed）；② hook 未绑定 `kind=hook` 的已注册 manifest → 不可注册；③ 证据需求字段复用绑定词表，调用侧缺字段 → 拒绝落账；④ 违规尝试产生稳定错误码与审计事件，不静默放行 | `tests/test_extension_contract.py` + `tests/test_connectors.py` |
| 连接器证据链 | 连接器每次调用记 operation + 证据绑定（复用 `_public_binding` 字段集），未启用/未声明 → 不可执行 | `tests/test_connectors.py` |

**阶段完成判据**：四条门全部绿 + 新增模块单测全绿 + 全量套件零新增失败 + CI 全绿（双腿 Windows 快照、provenance、Linux native probe 等既有项不回退）。失败/跳过不得计为通过。

## 5. 显式偏离

- MCP 客户端用标准库实现而非官方 SDK：core 零依赖是比“协议一致性”更高的约束；协议面收敛到三个方法，覆盖度以测试声明为准，不宣称完整 MCP 兼容。**JSON-RPC batch 整体拒绝**：逐元素放行需要额外的帧内一致性证明，v1 选择失败封闭并在规格中显式记录。
- Hook v1 定义为**声明式收紧 + 有界观察**：hook 可以提出策略收紧（经只紧判定）或产出自持有界观察，不提供任意代码写路径；“只收紧”以 `tighten_policy` 的同一语义为判定基准，而非信任 hook 自觉。
- ACP v1 是 stdio JSON-RPC 交互前端而非 Zed ACP 完整实现：方法集按“只承载交互”最小原则自定义，命名为 ACP 兼容前端而非 ACP 协议实现。
- 连接器 v1 只做出站调用与回执，不做入站 webhook 服务端（避免新增网络监听面，与既有仅回环 HTTP 基线一致）。

## 6. 实施记录

### 6.0 评审回应（独立 QUALITY 评审）

- BLOCKER-1（规格不存在）：评审代理读取的是过期兄弟检出 `D:\Projects\icode`（HEAD `7aad12c`）。权威仓库为 WSL `/home/orbbec/projects/icode`，本规格自 `e194149` 起存在；两个检出的分工已向用户说明，后续评审以 WSL 路径为准。
- BLOCKER-2/3/4 与 MAJOR-1/3/4/5/6 已逐条落入 v1.1：消息分发层强制与 batch 整体拒绝（W3/G1）、MCP 工具必须经 ToolRegistry（W3/G1）、ACP 意图必须过 `normalize_intent_payload` 同一词表（W4/G2）、Guard 收紧词表边界与根字段无通道（W2/G3）、连接器证据经 operation 回执通道而非 `_public_binding`（W5）、Tool 不加 permissions 的代码依据（§3）。
- MINOR-2（`tighten_policy` 的 `elif` 对未来网络模式静默放行）：以测试锁定当前模式集合，新增模式必须同批补判定。

### 6.1 已落地

- **W1 扩展契约**：`src/icode/extension_contract.py`（manifest 五段声明 + 控制面/账本目标结构性不可声明 + `attach_evidence` 证据缺项拒落账 + `tighten_guard_scope` Guard 侧只紧判定）。测试 `tests/test_extension_contract.py` 17 项全绿。
- **W2 Hooks**：`src/icode/hooks.py`（三类事件、注册即绑定 manifest、Guard/沙箱双通道只紧、观察者有界、审计记录）。测试 `tests/test_hooks.py` 14 项全绿。
