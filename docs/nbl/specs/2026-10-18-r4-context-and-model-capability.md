# R4 规格：上下文与模型能力（2026-10-18）

**状态**：v1 验收通过。候选 `a58c81d`：CI run `39143696377` success（45 job / 42 成功 / 0 失败 / 3 跳过）、provenance `39143696572` 三 job success；本机全量 3660 项仅剩仓库既有环境项，真实模型冒烟（MiniMax-M3）通过。继承 `docs/icode-agent-product-architecture.md` §13.8 与主序规则（前一阶段通过退出门槛后才展开本阶段；R2/R3 八门与全链路 CI 全绿已于同日达成，见 `nbl/plans/2026-10-18-r2-r3-exit-gate-audit.md`）。

## 1. 目标与边界

在不牺牲契约完整性的前提下支持大仓库、长任务和多模型。**控制面契约（gates.json / ICODE-SKILL 状态机 / 事件链 / 证据绑定）不变**：R4 只增加“如何为当前步骤选择与准备上下文”和“如何选择模型”，不新增第二真源，不放宽任何门禁。

## 2. 范围（对应 §13.8 五项工作）

| # | 工作 | 落地物 |
|---|---|---|
| W1 | 仓库结构、符号、变更索引 | `src/icode/context_index.py`：目录/文件指纹、Python 符号大纲（函数/类，正则级）、git 变更文件集；**只出大纲不出正文**，token 预算感知的有界选取 |
| W2 | 分层上下文、摘要、压缩、重新水合 | `src/icode/compaction.py`：受保护前缀/后缀（system 门禁、用户约束）+ 中段有界摘要 + 未闭合副作用回执注入 + `compact/rehydrate` 纯函数；`loop.py` 超预算时启用 |
| W3 | 模型后端 | 新增 `AnthropicBackend`（Messages API）、`GeminiBackend`（generateContent）、`OllamaBackend`（本地模型 `/api/chat`）；与既有 `OpenAICompatibleBackend`（含本地 llama.cpp/Ollama 兼容端点）并列，共 4 真实后端 + `FakeBackend` |
| W4 | 按步骤和能力选择模型 | `src/icode/model_routing.py`：step/capability → (backend, model) 路由；路由只选后端，不写任何模型自有状态 |
| W5 | 质量与运营指标分离 | `Usage` 增加 `latency_ms` / `cost_usd`（有价格表才计价，否则 null）；预算闸门语义不变，运营指标永不参与质量判定 |

## 3. 影响面与安全边界

- **正面**：`backends/__init__.py` 新增导出与工厂分支；`build_backend` 支持 `anthropic` / `gemini` / `ollama`；`Usage` 增加两个字段（向后兼容：默认 0/None，`as_dict` 追加键，既有测试的值断言不受影响——已核验现有测试只断言 token 类键存在性）。
- **风险与控制**：新后端全部标准库实现，沿用既有安全姿态（凭据 `repr=False`、固定公开错误说明、拒绝重定向、4xx 不重试）；上下文压缩永不断系统提示与未闭合副作用回执；路由不得写控制面（只读 settings/env）。
- **不适配**：不引入第三方 SDK（core 零依赖不变）；不做模型侧 embedding/向量库（v1 用符号与变更索引）；不做跨机器索引共享；不改 ICODE-SKILL 契约或事件 schema。
- **暂缓**：真实计费对账（需要供应商账单接口；当前只做公开标价的静态估算，未知模型为 null）；Anthropic/Gemini/Ollama 的真实网络 canary 需要对应凭据或本地服务，已提供按后端独立门控的用例，缺凭据即跳过并说明原因。

## 4. 验收计划（逐条对应退出门槛）

| 门 | 判据 | 证据 |
|---|---|---|
| G1 至少三个模型后端通过**同一离线契约套件** | `tests/test_backend_contract_suite.py` 对 4 个真实后端 + fake 跑同一组用例：请求形状（model/messages/tools/max_tokens）、usage 映射、tool_calls 解析、重试分类（4xx 不重试 / 5xx 有界重试）、公开错误边界、usage 先于解析失败记录 | CI Python 3.12 job 全绿 |
| G2 压缩与恢复不丢失硬门禁、用户约束、未闭合副作用 | 压缩后 system 门禁与首条用户约束逐字保留；未闭合副作用以有界回执注入；`rehydrate` 还原后仍含全部受保护项；总字节下降且有界 | 新增测试 + 全量套件 |
| G3 大仓库任务不需要全量注入源码 | 索引只产大纲与指纹；选取器在 token 预算内命中相关符号/变更文件，不含无关文件正文 | 新增测试 |
| G4 模型切换不产生状态第二真源 | 路由为纯函数；同脚本两条路由产生**相同**工单终态与事件序列（除有界指标通道外无差异）；ticket metadata/agent extension 无模型自有键 | 新增测试 |
| W5 指标分离 | `Usage.latency_ms/cost_usd` 存在且合并正确；超预算停止等质量判定不读取二者 | 新增测试 |

**阶段完成判据**：四条门全部绿 + 全量套件零新增失败 + CI 全绿（双腿 Windows 快照、provenance、Linux native probe 等既有项不回退）。失败/跳过不得计为通过。

## 5. 显式偏离

- 不把“模型输出”当作文本侧的状态载体：压缩产物的 digest 只含结构化字段与有界摘要，供人审计，不参与门禁判定（门禁判定只认事件链与回执）。
- 本地模型以 Ollama 原生 `/api/chat` 为基准后端；OpenAI 兼容端点（llama.cpp/Ollama/vLLM）继续走既有后端，不因“本地模型”新增第二协议实现。

## 6. 实施记录（2026-10-18）

| 工作 | 落地 | 测试证据 |
|---|---|---|
| W1 索引 | `src/icode/context_index.py`：文件指纹/大小、Python 大纲符号、变更集；`select_context` 预算感知选取，**只渲染大纲不含正文** | `tests/test_context_index.py`（4 项：忽略目录、符号、预算、正文标记不泄露） |
| W2 压缩 | `src/icode/compaction.py`：保护头部 system/首条 user/压缩摘要/未闭合回执/尾部；`rehydrate` 只还原受保护项；`loop.py` 以 `compact_budget_chars` 启用并在超预算时发 `context_compacted` 事件，未闭合动作标签随压缩保留 | `tests/test_context_compaction.py`（5 项）+ `tests/test_loop.py::TestContextCompactionInLoop`（循环内压缩，门禁/约束逐字保留，中段正文不再注入） |
| W3 后端 | `anthropic.py`（Messages API）、`gemini.py`（generateContent）、`ollama.py`（本地 `/api/chat`）+ 既有 `openai_compatible.py`；共享 `transport.py`（代理、拒绝重定向、有界重试、延迟计量） | `tests/test_backend_contract_suite.py`：同一套 6 项契约 × 4 后端（请求形状/鉴权头、响应解析与用量、503 有界重试、4xx 不重试且不泄露正文、结构异常统一隐藏、畸形 JSON 不泄露） |
| W4 路由 | `src/icode/model_routing.py`：`ICODE_MODEL_ROUTE_<STEP>=backend[:model]`，显式 > 只读默认 > 全局默认；纯函数、不可变 | `tests/test_model_routing.py`（含“同脚本两条路由产物逐字节一致”的 G4 证据） |
| W5 指标 | `Usage.latency_ms/cost_usd`（成本未知为 null）、`as_metrics()` 运营视图；`as_dict()` 与预算闸门语义不变 | 契约套件中断言用量与延迟；既有 `test_backend_transport_privacy` 的 `as_dict` 精确断言保持通过 |

**真实模型冒烟（用户授权使用 `models.json`）**：MiniMax-M3（`https://api.minimaxi.com/v1`）单回合成功，1.5s，用量与延迟已记账；测试以 `ICODE_RUN_REAL_MODEL_SMOKE=1` 显式开启，CI 默认跳过。Anthropic/Gemini/Ollama 无凭据，仅离线契约覆盖（与“真实网络 canary 需单独授权”的既定口径一致）。

**补项（2026-10-19，用户“先补”）**：

- **W4 路由接入**：`run_contract_step` 增加 `routes`/`route_builder`，在入口按步骤选后端；`run_chain` 透传；CLI 从 `ICODE_MODEL_ROUTE_<STEP>` 读取并打印生效路由。**配置了路由但构造失败会抛 `RouteError` 失败封闭，绝不悄悄回落主后端**；未配置路由时行为与之前完全一致。测试：`test_model_routing.TestStepBackendSelection` 四项。
- **W5 价格表**：新增 `backends/pricing.py`，按模型前缀查公开标价并估算 `cost_usd`（未知模型为 null、本地模型为 0），四个后端在用量记账后写入；`as_dict`/预算闸门语义不变。真实账单对账仍需供应商账单接口，明确保留为暂缓。
- **真实 canary**：`TestRealModelCanary` 拆成四个独立门控用例（OpenAI 兼容 / Anthropic / Gemini / Ollama）。本机以 `models.json` 的 MiniMax-M3 跑通 OpenAI 兼容路径（用量、延迟、`cost_usd` 均记账），其余三项因缺凭据/本地服务跳过并给出原因——**跳过不等于通过**。
