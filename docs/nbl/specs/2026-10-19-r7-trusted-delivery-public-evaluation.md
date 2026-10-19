# R7 规格：可信交付与公开评测（2026-10-19）

**状态**：v1.1（已独立评审并逐条处置）。继承 `docs/icode-agent-product-architecture.md` §13.11 与主序规则。前置阶段退出门槛均已验收：R4（`nbl/specs/2026-10-18-r4-context-and-model-capability.md`）、R5（`nbl/specs/2026-10-19-r5-open-ecosystem.md`）、R6（`nbl/specs/2026-10-19-r6-controlled-multi-agent.md`，HEAD `45c073c` CI `39201336710` 等三 run 全 success）。

## 1. 目标与边界

让 ICODE 的可靠性**能被外部复现**，而不是停留在产品声明。R7 做的是签名、外部锚定、provenance 与可复现评测口径，不是把验证推迟到最后——测试、事件留痕与基础证据自 R0/R1 起持续存在，本阶段只给它们加上"第三方可独立核实"的外壳。

**核心约束**：core 零第三方依赖（pyproject.toml `dependencies = []`）不变；签名用纯 Python Ed25519（RFC 8032）实现并以 RFC 官方测试向量交叉验证；第三方验证路径只依赖标准库。证据包、事件链、门禁与 `pack_verify.py` 既有校验全部保留且不被放宽。

## 2. 现状盘点（差异即工作）

- 证据包已有 `manifest.json`（逐文件 sha256 + `pack_digest`，`evidence.py:1281-1335`）与自校验；`evidence.py:16` 自述"pack_digest 需外部锚定才具抗抵赖力"——**正是本阶段要收的口**。
- `pack_verify.py`（2751 行）只用标准库（hashlib/json/os/re/stat/sys/pathlib）、无包内导入、自带 `main`（:2709）；且 `build_evidence_pack` 已把 pack_verify.py **原样复制**进包内为 `verify.py`（evidence.py "独立校验器"段）——包自带独立验证器已是既有机制，R7 在其上扩展即可让新包自动携带签名/锚定校验能力。
- GitHub Actions 已有 artifact attestation（windows-helper-provenance.yml）——CI 锚定有现成思想可沿用。
- R4 `Usage.as_metrics()`（backends/openai_compatible.py:100）已有 token/latency/cost 口径——benchmark 统计直接消费。
- 缺失：非对称签名、外部锚定记录、包内 provenance 段、多 run 统计口径（成功率/首过率/恢复率/介入率）、防"单次成功冒充统计"的报告纪律。

## 3. 范围（四项工作）

| # | 工作 | 落地物 |
|---|---|---|
| W1 | 证据包非对称签名 | `src/icode/pack_signing.py`：纯 Python Ed25519 放在 `pack_verify.py` 内部（保持"单文件验证器"性质，pack_signing 从其导入）；`sign_pack(pack_dir, signing_key)` 对 **manifest.json 的完整文件字节**签名，产出 `signature.json`（封闭字段：schema_version、algorithm="ed25519"、public_key、signature、key_fingerprint、signed_object="manifest.json"、signed_digest=manifest.pack_digest、signed_at；缺一或多一字段即无效）；`signature.json` **不列入** manifest.files（与 manifest.json 同为清单外豁免，防循环哈希）；签名消息 = `b"icode-pack-signature-v1\n" + manifest 字节`；私钥文件显式路径，私钥与明文密钥**绝不**进证据包、账本、日志或测试固定值（哨兵词表沿用 R4 教训）；验签失败/格式坏/密钥不符一律稳定错误码，不降级为"仅摘要比对" |
| W2 | 外部锚定记录与工作流 | `src/icode/pack_anchor.py`：锚定记录封闭类型词表（`git-tag` / `ci-run` / `rfc3161-file` / `transparency-log-entry`，未知类型拒绝）；每条记录必须携带 `anchor_target`（必须等于包 manifest.pack_digest，即绑定靠摘要相等而非靠入签）、外部可核查凭据（tag 名/run URL/时间戳文件指纹）与 anchor 时间。**时序澄清（回应 B2）**：包内 `anchors.json` 只承载**签名前已确定的预声明锚定意图**（如"将打 git-tag anchor/<digest前16>"），正常列入 manifest.files、随 pack_digest 入签；签名**之后**实际完成的外部锚定（tag 真已打出去、CI 真已跑完）存在于包外世界，第三方经外部渠道核查，不回写进包——两条通路都不破坏签名。新增 `.github/workflows/pack-anchor.yml`：workflow_dispatch 接收 pack_digest → 先校验 64 hex 形态（不合即 fail，无任何 git 操作）→ 写入 job summary 并创建 `anchor/<digest前16>` 公开 annotated git tag；顶层 `permissions: contents: read`，仅 tag job 最低需要 `contents: write`（参照 windows-helper-provenance.yml 的最小权限模式）；第三方用 `git ls-remote` + GitHub UI 即可独立核查，仓库公开历史即轻量透明日志 |
| W3 | 独立第三方验证器 | 扩展 `pack_verify.py`（保持零包内依赖、零第三方依赖）：Ed25519 验证 + `signature.json` 校验（对 manifest 字节重算验签）+ 锚定记录校验（类型/凭据/digest 一致性）；CLI 增加可选开关 `--verify-signature` 与 `--require-signature`（前者有签名必验、无签名报"未签名"，后者无签名直接失败——回应 G2④"报告未签名而非通过"的口径）；**公钥来源（回应 M1）**：验签时公钥必须由使用者经命令行 `--public-key <hex>` 显式提供，signature.json 内嵌的 public_key 与命令行公钥**逐字节不等即稳定错误**（防换公钥重签绕过）；key_fingerprint 仅作人读提示，不作为信任依据；公钥的分发与信任建立属包外带外渠道（§4 边界）。同时交付 `tools/verify_evidence_pack.py`：与 `src/icode/pack_verify.py` **逐字节相同**的提交入库副本（回应 M2：同字节、无 BOM——包内 verify.py 的 BOM 是既有发布细节，不适用于 tools 副本），测试断言两文件 sha256 相等防漂移；pack_verify 的模块 docstring 改写为同时描述"包内 verify.py"与"tools 独立分发"两种角色，保持字节同源；确保"无 ICODE 运行环境"下 `python tools/verify_evidence_pack.py <pack> --public-key <hex>` 完成清单+签名+锚定校验 |
| W4 | 可复现评测口径与报告 | `src/icode/benchmark.py`：任务集与 run 记录封闭 schema（task_id/repo/commit/backend/model/budget/task_digest/run_id/结果字段）；结果态封闭（success/failed/refused/human_intervention），`first_pass`（首过门禁，bool）、`recovered`（失败后恢复，bool）独立必填；RunLedger 只增有界、缺字段/未知字段/伪造态拒绝入账、run_id 重复拒绝；`aggregate()` 产出成功率、首次门禁通过率、恢复率、人工介入率（口径在报告中显式写出分母定义）+ token/耗时/成本汇总（cost 未知记 null 绝不冒充 0，沿用 Usage 纪律）；`render_report()` 输出 JSON+Markdown，**必须列出全部 run（含失败样本），无筛选参数**——结构性排除"单次成功演示冒充统计结论"；聚合对同输入字节级稳定（canonical json） |

## 4. 影响面与安全边界

- **正面**：新增 3 个模块 + 1 个工作流 + 1 个分发副本；复用而不改动：`pack_digest`/`sha256_file`（pack_verify.py）、`Usage.as_metrics`、证据包原子发布（evidence.py:1006）；evidence.py 仅最小改动——manifest 构建增加 `signature.json` 清单外豁免、anchors.json 正常入清单、README 补签名/锚定说明。
- **风险与控制**：Ed25519 纯实现是最大风险——以 RFC 8032 §7.1 全部测试向量（TEST 1–3 与 SHA(abc) 向量，回应 m5）+ 已知答案文件（A.3）驱动测试，并测非规范 s/R 拒绝；**诚实边界（回应 m4）**：纯 Python 实现非常量时间，理论上存在侧信道——v1 声明此边界，签名环境要求受控/离线，硬件密钥与常量时间实现列为后续增量；规范哈希复用 pack_verify 既有 canonical sha256 纪律；锚定防重放靠 `anchor_target == manifest.pack_digest` 摘要绑定（换包重贴旧锚定即校验失败）；防"整体重签"靠 M1 的带外公钥核对——**签名证明的是"私钥持有者在 signed_at 时刻认可此包"，不证明私钥归属；公钥身份锚定走带外渠道并在文档明示**；benchmark 记录禁网络、禁模型调用（纯口径层），真实评测执行不进 v1；pack-anchor.yml 是仓库首个 contents:write 工作流（回应 M3）：顶层 contents:read、仅 tag job contents:write、digest 形态校验先于任何 git 操作、无 secrets 使用、无其他写路径。
- **不适配**：不自建 CA/PKI；不引入 cryptography/pynacl 等第三方；不修改既有证据包格式兼容性（旧包无 signature.json → 明确报告"未签名"，不冒充通过）；不动 vendor/icode-skill；包内"未登记额外文件"既有防线不放宽——豁免名单仅 {manifest.json, signature.json}（回应 B1）。
- **暂缓（§5）**：多仓库真实任务集的采集与执行、真实模型 benchmark 跑批、与主流 Agent 同任务公开对比——三者都需要模型预算与外部环境授权；RFC 3161 可信时间戳与 Rekor 透明日志的真实服务端接入（v1 只交付记录格式与校验，外部服务调用需网络授权）。

## 5. 显式偏离与暂缓

- §13.11 工作项 4-7（多仓库真实任务集、四率统计的**实际测量**、token/成本**实测**、公开对比）：v1 交付**口径与工具**（schema、账本、聚合、报告），不执行真实评测跑批。真实跑批需要：用户授权模型预算与目标仓库清单；主流 Agent 对比需要对方运行环境。**报告生成器在 run 数为 0 时明确输出"无样本，不构成统计结论"**。
- §13.11 工作项 3 的"依赖 provenance"：core 零依赖使 v1 provenance 段记录 python 版本 + 零依赖声明 + 代码 commit；llm extra（httpx）版本在有模型调用时由 runtime 记录，未实测不虚构。
- 透明日志（Rekor）接入暂缓：锚定 v1 用公开仓库 git tag + CI job summary 作为可独立核查的外部锚点，满足"第三方可验证"；真实 Rekor 客户端列为后续增量。

## 6. 验收计划（逐条对应退出门槛）

| 门 | 判据 | 证据 |
|---|---|---|
| G1 第三方无 ICODE 环境可验证 | ① `tools/verify_evidence_pack.py` 与 `src/icode/pack_verify.py` sha256 逐字节相等（测试断言），且仅标准库（结构断言：无 `import icode`/包内导入/第三方 import）；② 独立 python 进程（subprocess，仅标准库环境）对构建出的样例包（含签名+锚定记录）验证通过；③ RFC 8032 §7.1 全部向量 + §7.2 全部向量 + A.3 知名答案文件全过（签名+验证+篡改拒绝+非规范 s/R 拒绝） | 新增 `tests/test_pack_signing.py`、`tests/test_pack_verify_extensions.py` |
| G2 签名不可绕过 | ① manifest 任一字节翻转 → 验签失败（稳定码）；② 换公钥（命令行公钥 ≠ signature.json 内嵌公钥）→ 失败；③ signature.json 缺字段/多字段/坏格式 → 失败；④ 无签名包 → 默认报"未签名（证据力受限）"，`--require-signature` 下失败退出；⑤ 私钥明文不进任何包/日志/测试值（哨兵扫描） | 同上 |
| G3 锚定可核且不可重贴 | ① 锚定记录未知类型拒绝、缺凭据拒绝、`anchor_target` 与包 pack_digest 不等拒绝；② 预声明意图记录经 anchors.json 随 manifest 入签（换包重贴旧 anchors.json → manifest/签名双重不符）；③ 签名后完成的外部锚定不回写包内（测试断言 anchors.json 修改会使 manifest 摘要与签名同时失效）；④ pack-anchor.yml digest 形态校验（64 hex，否则 fail 且无 git 操作）、最小权限（顶层 read / tag job write） | `tests/test_pack_anchor.py` + workflow YAML 结构断言 |
| G4 评测口径可复现、无 cherry-pick | ① run 记录缺封闭字段/未知字段/未知结果态 → 拒绝入账；② 同输入 ledger → aggregate → 报告字节级稳定；③ 报告必须含全部 run（构造含 failed/human_intervention 样本断言逐条出现）；④ 结构断言覆盖 `aggregate`/`render_report`/CLI 入口无任何筛选/排除参数（回应 m3）；⑤ cost 未知显式 null；⑥ run 数为 0 → 报告明确"无样本，不构成统计结论" | 新增 `tests/test_benchmark.py` |
| 阶段完成判据 | 四门全绿 + 新增单测全绿 + 全量套件零新增失败 + 本次 push 触发的三个 workflow run（ci / pages / windows-helper-provenance，回应 m2）全 success。失败/跳过不计为通过 |

## 7. 评审回应（v1 → v1.1）

独立评审（QUALITY 代理，2026-10-19）结论：需修订（BLOCKER×2、MAJOR×3、MINOR×5）。处置：

| # | 问题 | 处置 |
|---|---|---|
| B1 | signature.json 纳入 manifest 哈希范围构成循环依赖，且逼迫放宽"未登记文件"防线 | **采纳**。signature.json 移出 manifest.files（与 manifest.json 同为清单外豁免，豁免名单封闭 {manifest.json, signature.json}）；签名对象改为 manifest.json 完整文件字节；anchors.json 正常入清单 |
| B2 | "anchor bundle 入签"与 ci-run 记录产生于签名之后的时序矛盾 | **采纳**。包内 anchors.json 只承载签名前的**预声明锚定意图**并随 manifest 入签；签名后实际完成的外部锚定存在于包外，经外部渠道核查，不回写包内 |
| M1 | 验签者期望公钥来源未定义，换公钥重签可绕过 | **采纳**。公钥必须经命令行显式提供且与 signature.json 内嵌值逐字节相等；fingerprint 仅人读提示；公钥信任建立明示为带外渠道，签名不证明私钥归属 |
| M2 | tools 副本"同源生成"方案含糊（BOM、字节同源） | **采纳**。tools 副本为 pack_verify.py 逐字节相同副本（无 BOM），测试断言 sha256 相等；docstring 改写为双角色 |
| M3 | pack-anchor.yml 为仓库首个 contents:write 工作流，安全边界零着墨 | **采纳**。顶层 contents:read、仅 tag job contents:write、64-hex 形态校验先于任何 git 操作、无 secrets、无其他写路径（§4） |
| m1 | 引用 evidence.py:8 行号过期 | **采纳**。改为 evidence.py:16 |
| m2 | "三 run 全 success"表述含糊 | **采纳**。明确为本次 push 触发的 ci / pages / windows-helper-provenance 三个 workflow run |
| m3 | 无筛选参数的结构断言应覆盖 render_report 与 CLI 入口 | **采纳**。断言范围扩为 aggregate/render_report/CLI 入口（G4④） |
| m4 | 纯 Python Ed25519 非常量时间的侧信道风险应诚实声明 | **采纳**。§4 加入诚实边界与签名环境要求，常量时间/硬件密钥列为后续增量 |
| m5 | RFC 向量范围应含 §7.2 全部向量与非规范 s/R 拒绝 | **采纳**。G1③ 与 §4 更新 |

## 8. 实施记录

（实施后回填）
