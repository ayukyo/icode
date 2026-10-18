# Windows Reviewer 网络举证重定义与正控临时豁免实验 SPEC

日期：2026-10-17（北京时间）。状态：SPEC v2（已按独立 QUALITY 评审修订 M1-M6/m1-m2），待完整 PLAN 双审；不是 PLAN、已实现能力或原生验收。
权威工作区：WSL `/home/orbbec/projects/icode`；观察 HEAD `6ae841f3`（候选 de637ac 之后）。vendor 固定 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`，不原地改。
前置：2026-10-14 只读配置观察设计（已实现）、2026-10-15 正控临时豁免实验设计（未实现，含用户对临时正控 SID 增删验证的授权）；本文是该链的落地 SPEC。

## 1. 问题、用户授权与非目标

候选 de637ac（CI `39000099220`）实测：Windows 双快照 job 的 readonly admission 与 WFP observer 步骤首次全绿，仅 Reviewer 快照探针步双腿 `exit=78`。根因是零能力 AppContainer 双栈 loopback 实测 `connect_ex=10035` + `FD_CONNECT` 10 秒等待超时、`SO_ERROR=0`，而既有合同要求 `network_error==10013`（WSAEACCES）且 `connect_denied=True`；带 privateNetworkClientServer capability 的正控同样超时（exit 105、ipv4_connect_timeout）——capability 不等于 loopback exemption（2026-10-13 已记录）。该 10013 硬门自 2026-10-02 引入起从未在任何 CI 候选达成。

**用户已明确授权**重新定义网络举证：以三元证据替代零能力候选的“可审计双栈 10013”硬断言——(1) 只读配置证明相关 SID 未豁免；(2) 临时豁免的正控实测双栈 loopback 通路可用（canary 实际送达）；(3) 候选连接未建立且无 canary。

非目标：不给 Reviewer/候选 SID 添加豁免（任何时候都不）；不修改产品零 capability 的权限；不新增 MSIX/服务/驱动/安装步骤；不改防火墙策略、private range、网络分类；不停用、弱化任何文件系统隔离断言（写/删/改名/创建/写 DAC 拒绝、ACL 恢复、child 生命周期、job 清理全部保持原判据）；不把超时本身写成拒绝证据（候选无 canary 与正控实际连通才是证据）；非本 SPEC 授权的资产不改；不复制第三方源码。

## 2. 已读实际链与冻结观察

| 实际入口/依赖 | 当前事实 |
| --- | --- |
| `.github/workflows/ci.yml:926` 起 Reviewer 步 | admin PowerShell 创建临时标准用户、staged WFP helper 进 `$probeRoot`（SHA256 校验）、`Start-Process -Credential` 跑 unittest、netsh capture/observer 编排、try(1333)→finally(1676) 清理；另有 `$env:ICODE_DIAGNOSTIC_WFP_PROBE_BUILD` 受保护构建路径（admin 可读、标准用户不可写） |
| `tests/test_windows_appcontainer.py` Reviewer 测试 | 宿主双栈 listener 正控 → capability 正控（`_build_private_network_capability_probe_argv`、`_diagnostic_private_network_capability=True`、独立 capability profile）→ reviewer 零 cap 候选（staged runtime + snapshot 根）；负载末段 `raise SystemExit(78)` 自检；outer 断言 `exit==0` 且 `network_error==10013`、`connect_denied=True` |
| `native/windows/icode_positive_loopback_config.inc`（147 行，10-14 已实现） | helper 模式 `--observe-positive-loopback-config <icode-32hex>`：只读 `NetworkIsolationGetAppContainerConfig`，固定 receipt（status/api_stage/api_code/entry_count/target_match/target_attributes/release 账），公开输出不含 SID/profile；父侧包装 `_observe_positive_loopback_config` 2s 预算、stdout≤4096 单行 JSON |
| `scripts/windows_positive_loopback_admin_jobs.py:82` + `..._native.py` | positive loopback admin **serve** 流已实现豁免 add/delete（`CheckNetIsolation.exe LoopbackExempt -a/-d -p=<positive_sid>`，owned_intent、add_intent/cleanup_intent 相位、deadline、replay 防护、命令账本、admin-only store）；因 readonly 门此前未过，serve 从未在 CI 原生执行 |
| 双腿原始日志（本地 temp 归档） | 候选 exit=78、隔离事实全真；`positive exit=105 stage=ipv4_connect_timeout`；config 采样 pre/post 均 complete/target_match=false；WFP Subscribe2 以临时用户返回 5（ runner ACL 差异，与本实验无关） |

## 3. 三元证据合同（新零能力网络门）

候选（零 capability AppContainer，reviewer profile）同时满足以下三项才授网络隔离通过：

1. **未豁免证明（候选侧）**：对 reviewer profile 名的只读 config 采样 status=complete、`target_match=false`、且 full-list 指纹与预基线一致（others_preserved）；采样发生在候选启动前、且在豁免实验 delete 验证之后。
2. **通路证明（正控侧）**：对独立 capability profile（≠ reviewer profile）加临时 loopback 豁免后，带 privateNetworkClientServer capability 的正控双栈 connect 实际成功——宿主 listener `received_canaries` 双栈各收到精确 nonce canary（v4、v6 均 received=True，任一栈未达即失败）；随后豁免被删除且只读采样 `target_match=false`（恢复证明，full-list 指纹回到预基线）。
3. **未建立证明（候选侧）**：候选双栈 `network_connected=false` 且宿主双栈 `canary_received=false`；候选仍须 `executed=true`、`cleanup_ok=true`。

豁免生命周期账（admin state ledger，四项全 complete + cleanup confirmed）：capability profile 加前采样 `target_match=false`；add 后采样 `target_match=true`（attributes 有值记录）；delete 后采样 `target_match=false`；任一 unsupported/api_error/invalid_data/timed_out/协议错/helper 未回收 → 实验失败，不授任何一项通过。

原 `connect_denied=True` 与 `network_error==10013` 断言**删除**；`ipv4/ipv6_network_connect_denied/_error/_wait_expired/_terminal_error` 保留记录（facts/notices）但不再授信或要求特定值。负载自检（SystemExit 78）排除集加入上述四键；保留 `attempted=True`、`connected=False` 与全部文件系统隔离事实为必需。

**测试侧授信边界（M1）**：gate 断言只信本侧证据——本进程发起的 helper 采样（受保护构建路径调用）、宿主 listener 实测 canary、候选/正控自身 receipts；标准用户可写的 `state.json` 与握手工文件一律不作为授信输入，仅用于编排；`state.json` 的有界摘要（含四采样 status/target_match/entry_count、CheckNetIsolation 身份、cleanup 状态）由 admin 在删 `$probeRoot` 前写入 job 日志。

## 4. 信任模型与固定协议

执行者分工：**admin = 现有 workflow 父进程（提权）**；**standard user = Reviewer unittest 进程**。标准用户只提交两个预分配 profile 名（测试内随机生成、一次性、恰 `icode-`+32 小写 hex），不能提交 SID、命令、路径或端口；admin 自行从两个名字派生双 SID（`userenv!DeriveAppContainerSidFromAppContainerName` + `advapi32!ConvertSidToStringSidW` p/invoke，FreeSid 配对释放）并断言两 SID 不等，不相信任何来自测试文件的 SID。派生正确性由独立代码路径交叉验证：若派生 SID 错误，post-add 采样（受保护 native helper）对该 capability profile 名必然 `target_match≠true` → 实验失败，无假阳通路。

admin-only 状态目录（`$env:RUNNER_TEMP\icode-loopback-exemption-admin-<suffix>`，不授标准用户任何权限）：`state.json`（固定 schema 1，字段：phase、four sample 的 status/api_stage/api_code/entry_count/target_match/target_attributes/full-list 指纹、others_preserved、CheckNetIsolation.exe 完整路径/FileVersion/SHA256、add/delete 退出码、派生 SID 的前 8+后 4 字符摘要、cleanup、candidate SHA/run/job 身份、单调时刻）、预基线全列表指纹（add 前）、删除后指纹（delete 后）。协议开始 admin 断言四个握手工文件不存在（存在即陈旧 → 删除后重来判定为失败关闭）。

握手工文件（`$probeRoot`，标准用户可写、admin 可读写，仅编排用）：`loopback-exemption-profile.txt`（单行 ASCII profile 名，admin 有界读+整行+形状校验）、`loopback-exemption-ready.txt`（admin 写 `ready`，tmp+rename 原子写）、`loopback-exemption-done.txt`（测试写 `done`）、`loopback-exemption-removed.txt`（admin 写 `removed`）。相位单调：ready→done→removed，乱序/预置/超限/多行/非 ASCII → 失败。

时序（等待均有硬上限，超时即失败）：
```text
宿主 listener + 宿主正控（原顺序）
→ 测试写 capability/reviewer 两 profile 名；admin 校验形状、定位并核验 CheckNetIsolation.exe
  （$env:SystemRoot\System32 显式路径 + 存在性 + FileVersion + SHA256 记录 + 架构相符；
   SystemRoot 被篡改导致路径不符即拒绝）、派生双 SID 并断言不等
→ 预基线 full-list 采样；capability profile pre 采样（要求 complete/target_match=false；
  预存豁免即停）；reviewer profile pre 采样（要求 target_match=false，预豁免即失败）
→ add（LoopbackExempt -a -p=<派生SID>，固定 argv，禁 -c/-is/-n/其它模块）
→ post-add 采样（要求 complete/target_match=true）→ 写 ready
→ 测试：capability 正控（原 argv/capability/profile/token 核验/超时/清理不变）→ 写 done
→ admin：delete（-d -p=）→ post-delete 采样（要求 complete/target_match=false 且
  full-list 指纹与预基线一致）→ 写 removed
→ 测试：reviewer profile 配置采样（complete/target_match=false/fingerprint 一致）
  → candidate 原实验 → 汇总断言
finally：任何失败路径 admin 仍尝试 delete+post-delete 采样；cleanup 未确认即步骤失败
```

预算（分步，均在 10-14/10-15 冻结既有值内）：admin 派生 5s；每次 helper 采样沿用父侧包装既有 2s；add/delete 各 10s；ready/done/removed 等待各 120s。happy path 新增约 15-30s，落在既有 180s staging-prep 窗内且候选 payload 的 runner-target 发布其后；ARM64 staging 已占该窗主体，本协议不改变 staging/copy 预算，观测者 target 等待仍以既有 180s 为界（不因本协议放宽）。job 总窗 25min 不变。

失败封闭（M4）：`ICODE_DIAGNOSTIC_LOOPBACK_EXEMPTION` 缺失/空/非 `true`（或四文件不齐）→ 三元证据不可建立 → Reviewer 测试失败；禁止 skipTest、禁止条件跳过整个网络断言组、禁止把 env 缺失写成 unsupported/unknown 了事。

独立清理步（M3，与 10-15 §5 对齐）：workflow 增加 `if: always()` 的 admin-only 清理步，读 admin-only state 目录；若存在“add 已验证但 delete 未确认”的未完成 owned SID，尝试 delete + post-delete 采样并记结果；无未完成项即 no-op。runner 强制取消/重启导致的残缺只记 unknown，不授通过。与 positive serve 流的关系：本实验不复用 serve 的 store/账本（topology 不同：unittest 标准用户进程 vs serve admin 入口），此偏离显式记录，其安全属性由 admin 派生 SID、受保护 helper 交叉验证、full-list 指纹与独立 always() 清理补足。

## 5. 资产改动清单（最小集）

| 资产 | 改动 | 责任边界 |
| --- | --- | --- |
| `tests/test_windows_appcontainer.py` | 豁免握手读写（有界、形状校验、失败封闭）；capability 正控改 ready 后跑、done 前不结束；reviewer profile 预采样；正控双栈 canary 必达断言；候选未建立断言；删 10013/connect_denied 断言；负载自检排除集调整；`windows_appcontainer_private_network_positive_control` 通知语义随三元证据更新；`_reviewer_network_evidence` 纯函数（canary 三态判定）+ 模块级可测 | 不改 capability 探针 argv、profile 生命周期、token 核验、Job/ACL 语义 |
| `.github/workflows/ci.yml` Reviewer 步 | env `ICODE_DIAGNOSTIC_LOOPBACK_EXEMPTION=true` + 四握手工文件 + admin-only 状态目录 + state.json；admin 派生/预采样/add/delete/恢复协议；try/finally 清理（未确认清理即 throw）；新增独立 `if: always()` 清理步；删 probeRoot 前把 state 有界摘要写 job 日志 | 保留 25min/matrix/既有 guards/staging/hash 校验；不加权限 |
| 契约测试 | source-contract（Reviewer 测试源与 workflow 源的新结构断言，沿用既有 `reviewer_source.index(...)`、`test_ci_workflow_contracts.py` 模式）；纯函数单测（canary 三态、握手形状、state.json schema 严格解析、env 失败封闭） | 字符串断言的边界在验收节明示 |
| mock 回归 | 负载自检排除集（注入 facts 编译执行，既有先例）；握手相位负例；state.json 负例 | 不联网、不建 profile |
| `docs/agent-landscape-live.md` | 追加决策条目（采纳/暂缓/不适配 + 官方链接 + 用户授权引述 + 偏离记录） | 只追加 |

不改：`src/icode/windows_job.py` 正控 argv 与 capability 注入、`src/icode/windows_appcontainer.py` 包装器、`native/windows/*.c/.inc`（无新原生模式）、positive loopback admin serve 流、其它测试门。

## 6. 正负控、验收与停止线

必要软件正控：握手 happy path（mock 文件序列驱动前后断言）；state.json 固定 schema 全字段解析；capability 双栈 canary 必达对“单栈到达/双栈未达/双栈到达”三态分别 RED/GREEN（`_reviewer_network_evidence` 纯函数，Linux 可跑）；候选采样 target_match=false 必需；负载自检对 `connect_denied=False`/`error=10035` 不退 78，对 `connected=True`/隔离事实为假仍退 78。

必要负控（全列）：env 缺失/空/非 true → 失败；预置/陈旧 ready/done/removed/profile 文件与相位乱序（done 早于 ready、removed 早于 done）→ 拒绝；profile 文件非原子/部分写/超限/多行/非 ASCII → admin 拒绝；admin 侧使用用户可写 staged helper（含被替换）→ 契约测试拒绝（必须受保护构建路径+每次 SHA256）；CheckNetIsolation 路径/FileVersion/SHA256 不符或 SystemRoot 篡改 → 拒绝；reviewer profile 预豁免（target_match=true）→ 失败；add 后 target_match≠true 或 post-delete target_match≠false → 失败；foreign 条目变动/others_preserved=false/delete 后指纹≠预基线 → 失败；任一 admin 侧 helper 未回收 → 按 10-14 不再启动 capability/candidate；canary 任一栈未达 → leg2 失败；state.json 重复 key/额外字段/非 ASCII/超限 → 拒绝；reviewer 与 capability profile 名相同（测试侧断言 + admin 双 SID 不等断言）→ 拒；finally delete 失败或 post-delete 未确认 → 步骤失败。

验收：正式 TEST 先 RED（当前源必红：10013 断言存在、无握手、env 失败封闭未实现）；最小实现后 GREEN；本地家族基线 237 项 + 新增 mock/纯函数回归 N 项零差异（2 个 Linux `SO_EXCLUSIVEADDRUSE` 环境错误不变）；CI 同 SHA 双 Windows native job 双腿：readonly admission 与 WFP observer 保持全绿，Reviewer 快照步首次全绿，且原始日志含四采样 receipt、双栈 canary、账户与恢复证据、state 有界摘要。**未双架构原生通过前不记 R3 网络门通过。** source-contract 字符串断言只作结构辅助，语义信用以前述正负控与原生收据为准（不单靠字符串扫描授信用）。

停止线：给 reviewer/candidate SID 加豁免或删任何文件系统隔离断言；把超时/`SO_ERROR=0`/采样 unsupported 当作证据；候选或正控任一侧无 canary 却判通过；删 10013 却不建三元证据；helper 输出引入 SID 全文或改写 10-14 receipt；测试消费用户可写 state.json 作授信；无独立评审即合入；任一出现均退回。

## 7. 自审（v2 修订对照）

- M1：state/账本入 admin-only 目录；测试授信边界明文；摘要入 job 日志。✅
- M2：admin 采样只用受保护构建路径 + 每次 SHA256；契约负控“用户可写 staged helper 不得进 admin 侧”。✅
- M3：显式记录不复用 serve 的偏离；admin-only 持久 intent（state.json）；独立 always() 清理步；取消只记 unknown。✅
- M4：env 缺失 → 失败封闭，禁 skip。✅
- M5：分步预算表；不调整既有 180s/65s；采样沿用冻结 2s。✅
- M6：full-list 指纹 + others_preserved + reviewer 预豁免负控。✅
- m1 四文件不存在前置 + 原子写 + 相位单调；m2 admin 双 SID 派生断言；m3 SystemRoot 篡改负控；m4 派生经 post-add 采样交叉验证；m5 纯函数 seam；m6 字符串断言边界；m7 基线 237+N。✅
- 仍待独立二次确认：p/invoke 清理配对、budget 总和分析、workflow 结构断言充分性（进入 PLAN 双审）。
