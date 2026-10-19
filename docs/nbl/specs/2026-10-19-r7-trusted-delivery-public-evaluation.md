# R7 规格：可信交付与公开评测（2026-10-19）

**状态**：v1（待独立评审）。继承 `docs/icode-agent-product-architecture.md` §13.11 与主序规则。前置阶段退出门槛均已验收：R4（`nbl/specs/2026-10-18-r4-context-and-model-capability.md`）、R5（`nbl/specs/2026-10-19-r5-open-ecosystem.md`）、R6（`nbl/specs/2026-10-19-r6-controlled-multi-agent.md`，HEAD `45c073c` CI `39201336710` 等三 run 全 success）。

## 1. 目标与边界

让 ICODE 的可靠性**能被外部复现**，而不是停留在产品声明。R7 做的是签名、外部锚定、provenance 与可复现评测口径，不是把验证推迟到最后——测试、事件留痕与基础证据自 R0/R1 起持续存在，本阶段只给它们加上"第三方可独立核实"的外壳。

**核心约束**：core 零第三方依赖（pyproject.toml `dependencies = []`）不变；签名用纯 Python Ed25519（RFC 8032）实现并以 RFC 官方测试向量交叉验证；第三方验证路径只依赖标准库。证据包、事件链、门禁与 `pack_verify.py` 既有校验全部保留且不被放宽。

## 2. 现状盘点（差异即工作）

- 证据包已有 `manifest.json`（逐文件 sha256 + `pack_digest`，`evidence.py:1282-1347`）与自校验；`evidence.py:8` 自述"pack_digest 需要外部渠道锚定才有抗抵赖力，否则可被整体重签"——**正是本阶段要收的口**。
- `pack_verify.py`（2751 行）只用标准库（hashlib/json/os/re/stat/sys/pathlib）、无包内导入、自带 `main`——已是潜在独立验证器，但**尚无签名与锚定校验**。
- GitHub Actions 已有 artifact attestation（windows-helper-provenance.yml）——CI 锚定有现成思想可沿用。
- R4 `Usage.as_metrics()` 已有 token/latency/cost 口径——benchmark 统计可直接消费。
- 缺失：非对称签名、外部锚定记录、包内 provenance 段、多 run 统计口径（成功率/首过率/恢复率/介入率）、防"单次成功冒充统计"的报告纪律。

## 3. 范围（四项工作）

| # | 工作 | 落地物 |
|---|---|---|
| W1 | 证据包非对称签名 | `src/icode/pack_signing.py`：纯 Python Ed25519（RFC 8032，签名+验证，RFC 8032 §7 测试向量驱动测试）；`sign_pack(manifest, sign_key)` 对 `pack_digest` 与 manifest 规范化字节签名，产出 `signature.json`（封闭字段：algorithm=ed25519、public_key、signature、signed_digest、key_fingerprint、signed_at；缺一或多余字段即无效）；密钥文件 0600/显式路径，私钥与明文密钥**绝不**进证据包、账本、日志或测试固定值（哨兵词表沿用 R4 教训）；验签失败/格式坏/密钥不符一律稳定错误码，不降级为"仅摘要比对" |
| W2 | 外部锚定记录与工作流 | `src/icode/pack_anchor.py`：锚定记录封闭类型词表（`git-tag` / `ci-run` / `rfc3161-file` / `transparency-log-entry`，未知类型拒绝）；每条记录必须携带 anchor_target=pack_digest、外部可核查凭据（tag 名/run URL/时间戳文件指纹）与 anchor 时间；`anchor bundle`（记录数组）整体纳入签名范围；新增 `.github/workflows/pack-anchor.yml`：workflow_dispatch 接收 pack_digest → 校验形态 → 写入 job summary 并创建 `anchor/<digest前16>` 公开 git tag——第三方用 `git ls-remote` + GitHub UI 即可独立核查，仓库公开历史即轻量透明日志 |
| W3 | 独立第三方验证器 | 扩展 `pack_verify.py`（保持零包内依赖、零第三方依赖）：`--verify-signature`（加载 `signature.json` 验签，manifest 任一字节改动即失败）、`--verify-anchor`（锚定记录类型/凭据/digest 一致性校验）；同时交付 `tools/verify_evidence_pack.py` **单文件分发副本**（同源生成，生成测试保证副本与模块校验逻辑一致），确保"无 ICODE 运行环境"下 `python tools/verify_evidence_pack.py <pack> --public-key <pk>` 可完成 manifest+签名+锚定校验 |
| W4 | 可复现评测口径与报告 | `src/icode/benchmark.py`：任务集与 run 记录封闭 schema（repo/commit/task/budget/model/backend/seed/结果态）；结果态封闭（success/failed/refused/human_intervention），`first_pass`（首过门禁布尔）、`recovered`（失败后恢复布尔）独立记录；RunLedger 只增有界、缺字段/伪造态拒绝入账；`aggregate()` 产出成功率、首次门禁通过率、恢复率、人工介入率 + token/耗时/成本汇总（cost 未知记 null 绝不冒充 0，沿用 Usage 纪律）；`render_report()` 输出 JSON+Markdown，**必须列出全部 run（含失败样本），无筛选参数**——结构性排除"单次成功演示冒充统计结论"；聚合对同输入字节级稳定（canonical json） |

## 4. 影响面与安全边界

- **正面**：新增 3 个模块 + 1 个工作流 + 1 个分发副本；复用而不改动：`pack_digest`/`sha256_file`（pack_verify.py）、`Usage.as_metrics`（backends/openai_compatible.py:58）、证据包原子发布（evidence.py:1006）；`signature.json`/`provenance`/锚定记录经 manifest 纳入哈希与签名范围。
- **风险与控制**：Ed25519 纯实现是最大风险——以 RFC 8032 §7.1/§7.2 全部测试向量 + 已知答案文件（A.3）驱动测试，验证侧另用固定向量交叉验证；规范哈希复用 pack_verify 既有 canonical sha256 纪律；签名覆盖 `pack_digest` 本身（防 manifest 与签名拼接错位）；锚定记录防重放靠"记录含 pack_digest 且 bundle 入签"——换包重贴旧锚定即验签失败；benchmark 记录禁网络、禁模型调用（纯口径层），真实评测执行不进 v1。
- **不适配**：不自建 CA/PKI；不引入 cryptography/pynacl 等第三方；不修改既有证据包格式兼容性（旧包无 signature.json → 明确报告"未签名"，不冒充通过）；不动 vendor/icode-skill。
- **暂缓（§5）**：多仓库真实任务集的采集与执行、真实模型 benchmark 跑批、与主流 Agent 同任务公开对比——三者都需要模型预算与外部环境授权；RFC 3161 可信时间戳与 Rekor 透明日志的真实服务端接入（v1 只交付记录格式与校验，外部服务调用需网络授权）。

## 5. 显式偏离与暂缓

- §13.11 工作项 4-7（多仓库真实任务集、四率统计的**实际测量**、token/成本**实测**、公开对比）：v1 交付**口径与工具**（schema、账本、聚合、报告），不执行真实评测跑批。真实跑批需要：用户授权模型预算与目标仓库清单；主流 Agent 对比需要对方运行环境。**报告生成器在 run 数为 0 时明确输出"无样本，不构成统计结论"**。
- §13.11 工作项 3 的"依赖 provenance"：core 零依赖使 v1 provenance 段记录 python 版本 + 零依赖声明 + 代码 commit；llm extra（httpx）版本在有模型调用时由 runtime 记录，未实测不虚构。
- 透明日志（Rekor）接入暂缓：锚定 v1 用公开仓库 git tag + CI job summary 作为可独立核查的外部锚点，满足"第三方可验证"；真实 Rekor 客户端列为后续增量。

## 6. 验收计划（逐条对应退出门槛）

| 门 | 判据 | 证据 |
|---|---|---|
| G1 第三方无 ICODE 环境可验证 | ① `tools/verify_evidence_pack.py` 单文件仅标准库（源码结构断言：无 `import icode`/包内导入/第三方 import）；② 对构建出的样例包（含签名+锚定 bundle）独立 python 进程验证通过；③ RFC 8032 测试向量全过（签名+验证+篡改拒绝） | 新增 `tests/test_pack_signing.py`、`tests/test_pack_verify_extensions.py` |
| G2 签名不可绕过 | ① manifest 任一字节翻转 → 验签失败（稳定码）；② 换公钥 → 失败；③ signature.json 缺字段/多字段/坏格式 → 失败；④ 无签名包 → 报告"未签名"而非通过；⑤ 私钥明文不进任何包/日志/测试值（哨兵扫描） | 同上 |
| G3 锚定可核且不可重贴 | ① 锚定记录未知类型拒绝、缺凭据拒绝、digest 与包不一致拒绝；② bundle 整体在签名范围内——换包重贴旧 bundle 验签失败；③ pack-anchor.yml 的 digest 形态校验（64 hex，否则 fail） | `tests/test_pack_anchor.py` + workflow YAML 自检 |
| G4 评测口径可复现、无 cherry-pick | ① run 记录缺封闭字段/未知结果态 → 拒绝入账；② 同输入 ledger → aggregate → 报告字节级稳定；③ 报告必须含全部 run（构造含 failed/human_intervention 样本断言逐条出现，且聚合器无过滤参数——源码结构断言）；④ cost 未知显式 null；⑤ run 数为 0 → 报告明确"无样本，不构成统计结论" | 新增 `tests/test_benchmark.py` |
| 阶段完成判据 | 四门全绿 + 新增单测全绿 + 全量套件零新增失败 + CI 三 run（ci/pages/windows-helper-provenance）全 success。失败/跳过不计为通过 |

## 7. 实施记录

（实施后回填）
