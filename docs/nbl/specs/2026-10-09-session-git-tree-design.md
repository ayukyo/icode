# R3：可信会话的分离 Git 状态与树投影最小修复设计

日期：2026-10-09。状态：设计稿，未实施、未运行测试；待独立 SPEC 与不同 QUALITY 审查。基线 main `8d53670192e3e2cbfebaa0300d697fb3036308be`，固定 ICODE-SKILL `1693651c1bd7daad3272eb054f0f81d6f254d08d`。本片不是 R2/R3 整体验收，也不开放 Native 自动模式。

## 1. 真实问题、复用与边界

`WorkspaceManager(...isolate_git_metadata=True)` 已将整个仓库的原始 Git 内容物化到 `checkout/code`，`.git` 指针留在 `checkout`；`WorkspaceSession.workspace_root` 在仓库根需求下等于该 code 根。当前 runner 的树捕获要求 `workspace/.git`，而 Git 状态读取会发现父层仓库。于是状态非空但树状态是 `workspace_not_repository_root`，工程 gate 的 `source_stable` 必失败。这是生产接线缺陷，不是缺少测试或模型质量问题。

已有 `git_broker.verify_git_workspace_identity` 对 manager 捕获的设备/inode、所有路径组件 no-follow、`.git`/commondir/HEAD/ownership marker 做实际复核；已有 `workspace_snapshot.worktree_git_tree_oid` 对代码根做 bounded、no-follow 的纯文件树投影，不调用 Git，不写索引或对象库。两者可复用；不能重新发明仓库发现或无边界宿主 Git 通道。

关联问题：在 code 根注入 `.git` 会改变现有 `_read_task_git_state` 的仓库选择，而树 walker 默认跳过根 `.git`。因此修复必须将 session-aware state 与 tree 成对接线，并明确拒绝分离 code 根的 `.git`，不能只补正控树捕获。root 已确认这一最小同源范围。

本片只支持 `source_relative_path == Path(".")` 的可信分离会话。manager 已支持子目录需求，不代表当前工程证据授权读取代码根之外的兄弟目录；子目录 tree 不能称整仓 tree。该形态明确失败关闭，留待独立范围/证据设计，不自动扩根。

## 2. 方案比较与决策

| 方案 | 决策 | 原因与成本 |
| --- | --- | --- |
| A：复用 manager 身份，session-aware state/tree 成对核验 | 采纳 | 仅 runner 内部接口与必要测试；保留原布局、保护根和纯文件投影；增加有限的身份/状态只读复核成本 |
| B：缺 `.git` 就沿父层发现并允许投影 | 不适配 | 祖先发现不是授权，code/.git 注入或另一个父仓可混淆身份；不能证明树属于 session 基线 |
| C：移动 `.git` 到 code 根，或哈希整 checkout/兄弟目录 | 不适配 | 破坏元数据不可写拓扑或越过 workspace 范围；还会把 code 包装目录错误地等同 commit 根 tree |

无新包、Git helper、服务、UAC、权限、沙箱 backend、模型工具、CP schema 或证据 schema。`LandlockSandbox.policy_contract_ready` 继续 False。Windows Git pipe/Reviewer、macOS quota、模型 endpoint 与真实 1→6 门不在本片。

## 3. 内部 API 与来源合同

仅在 `runner.py` 中增加可选 keyword：

```python
_read_task_git_state(workspace, *, workspace_session=None) -> tuple[str, str]
_capture_task_git_tree_oid(workspace, base_commit_sha, *,
                           object_format=None, workspace_session=None) -> tuple[str, str]
```

建议共用一个私有 session layout 校验函数，复用现有 `VerifiedGitLayout`，不新增持久模型。其职责只验证可信输入，不运行 payload，不制造 resource/violation 证据。真正的分离路径从宿主已有 `WorkspaceSession.git_status_identity` 取得身份，不能从模型路径、仓库文件、父层发现或 receipt 反序列化创建授权。

分离路径的全部前置条件：

1. 实际 session 是 `WorkspaceSession`，kind 为 `git_worktree`，身份是 `GitWorkspaceIdentity`；已有 admission 对 session run_id/ticket_id/policy/Plan 的绑定保持不变。
2. 参数 workspace 必须为绝对、lexically normalized Path；严格等于 session.workspace_root 与 identity.workspace_root，不先 resolve 不可信 identity 再宣称相等。
3. identity.source_relative_path 是 `Path(".")`；identity.code_root 严格等于 identity.checkout_root / "code"，并等于 workspace。不接受子目录、相邻路径、另一 session 的根或 checkout 本身。
4. `verify_git_workspace_identity(identity)` 返回的 worktree_root 与 pathspec_root 均严格等于 workspace；所有既有 metadata/inode/token/HEAD 条件真实通过。身份对象是当前调用从可信 session 抽取的对象，结束时重新确认 session 的 workspace/kind/身份引用未替换，再真实验证同一身份。
5. 分离 code 根的 `.git` 必须不存在：以 lstat 区分不存在与检查错误；任何文件、目录、链接（包括悬空链接）或其他类型均拒绝。权限/IO 异常不得当不存在。该检查在每次 state/tree 操作前后进行；nested `.git` 仍由原 walker 拒绝。

在 state 与 tree 入口先按可信宿主 session 的**既有固定布局与原保护拓扑**明确路由，再碰 Git 或执行投影；不是先发现根 `.git` 或保护成员资格再推断布局：

| 宿主输入 | 路由合同 |
| --- | --- |
| workspace_session 为 None | 完整原行为；tree 仍要求根 `.git` 是非链接普通文件或目录，父层发现不新增树授权 |
| 合法 snapshot session 且 git_status_identity 为 None | 保持原 state/tree 逻辑，不新增分离 Git 支持 |
| 合法 git_worktree session 且身份非 None | 仅走上述严格分离核验；错类型/失效身份拒绝，绝不 fallback |
| 合法 git_worktree session 且身份为 None | 必须先由下述可信固定同级字段证明workspace就是ticket_root/checkout，再要求 `workspace / ".git"` 严格列在原 protected_paths，才可沿既有普通非分层根逻辑；保护成员资格或.git存在均不能单独赋资格 |
| session/字段类型、kind、workspace 身份、保护清单或路径检查错误 | 失败关闭，不执行 Git、不投影，不猜测普通根资格 |

有 session 时，workspace/session.workspace_root 都须是绝对、lexically normalized Path 并严格相等；kind 仅接受 snapshot/git_worktree。protected_paths 须为 tuple，成员均为绝对、lexically normalized Path；错误字段或读取/检查异常均拒绝，不 resolve 不可信成员或用祖先/重叠代替严格成员相等。snapshot 带非空 Git 身份也是错配，拒绝。

无身份 git_worktree fallback 的固定布局证明：session.manifest_path、runtime_root、receipts_root 必须分别为绝对、lexically normalized Path；令 `ticket_root = session.manifest_path.parent`，要求 `manifest_path == ticket_root / "workspace.json"`、`runtime_root == ticket_root / "runtime"`、`receipts_root == ticket_root / "receipts"`，且 `workspace == session.workspace_root == ticket_root / "checkout"`。这些名称来自现有 manager schema 的固定布局（workspace.py:1654–1657），不是新魔法配置、Git发现或允许模型声明的目录。严格等式不允许checkout/code、checkout子目录、未知命名、相邻ticket或词法别名；错误字段/未知或不符布局拒绝。只读取可信session固定字段，不读manifest正文、仓库config、.git内容或receipt来构造布局，不新增持久flag或变manager。

固定布局资格与根 `.git` 在原protected_paths两项均必要：`extra_protected_paths`本来会合并清单（workspace.py:2118），故新增code/.git保护项**不能**升级其布局资格。真实普通非分层dot-root session满足workspace=ticket_root/checkout并保护checkout/.git；无关extra保护项不使该正控失效。真实分离session的workspace=ticket_root/checkout/code，身份置None后，即使宿主extra保护code/.git并注入指向原仓同HEAD的.git，仍先因固定布局不符拒绝，不执行Git查询或walker。

原非分层fallback仅保留现有完整仓库根资格，不授分离或子目录能力。前后重核同一session的kind/workspace/身份None、manifest_path/runtime_root/receipts_root固定字段与同一原protected_paths清单，变化则丢弃结果；不能在窗口内改字段以重新选route。无session完全原行为、合法snapshot且无身份原行为保持，不把fallback专用布局条件附加到这两个分支。

## 4. 状态与树的核验时序

### 4.1 session-aware state

`校验 session/layout 与无 code/.git → read_git_repository_state(identity.checkout_root, require_root=True) → 真实重核同一 session/layout 与无 code/.git → 核格式、revision → 返回`

状态读只复用既有受控、只读、有界 Git 接口及其 no-replace/no-lazy-fetch/环境限制。不能执行模型 argv、配置-selected helper，不能从 code 根或普通祖先搜索决定来源。实际 storage format 必须为 sha1/sha256，HEAD 必须等于固定 identity.revision，长度必须分别为 40/64 且为规范小写十六进制。不能只由调用者的 object_format 或 revision 长度推断实际 storage format。

`verify_git_workspace_identity` 已校验固定 detached HEAD；再读实际 format/HEAD是两项独立职责。前后验证不冻结全部 Git metadata，不宣称点时原子快照；观察到身份/HEAD/格式漂移都拒绝。返回保留 `(format, revision)`，身份失效只报路径无关错误，不泄漏本地 token、源路径或 Git stderr。

### 4.2 session-aware tree capture

`可信 session/layout 前核 → session-aware actual state 前核 → base/format 对比 → 原 bounded tree walker(workspace) → session-aware actual state 后核 → 可信 session/layout 后核 → captured`

base_commit_sha 必须非空且精确等于 identity.revision；传入 format 若非 None 必须等于实际前后 format，省略时使用真实前读 format。前后 actual HEAD 均固定为 identity.revision；format 前后相同、与 revision 长度一致。捕获失败返回空 OID 与明确失败状态，不返回部分 tree、不补空 Git 身份、不复测取绿。实际文件内容在测试前后不同依然由原 `_resolve_tested_git_tree` 与 snapshot 指纹拒绝。

纯树投影的 250000 项、128 深度、256 MiB 原上限及链接/特殊文件/类型/执行位/原字节语义不变；root .git 注入不再因 walker 的忽略规则漏掉。before/after verifier 不是原子 namespace 锁，不能声称杜绝共享宿主所有 ABA 攻击；现有 fd/no-follow 和 identity 两端检查保留，观察不确定时不授 captured。该片不更改 walker 根打开机制或额外扩大其原始保证。

### 4.3 失败合同

| 条件 | state 行为 | tree 行为 | 后续信用 |
| --- | --- | --- | --- |
| 无 session，非仓库 | 原行为空 tuple | 原 not_git_workspace | 不新增 Git 绑定 |
| 无 session，workspace 是父仓子目录 | 原 state 行为不变 | 原 workspace_not_repository_root | 不新增祖先授权 |
| 非空分离身份无效/失效/路径不符/替换/注入 | `ValueError("workspace_git_identity_unavailable")`，无路径正文 | `("", "session_git_identity_unavailable")` | 不签发 captured；原 gate/Reviewer/finalCP 阻断 |
| git_worktree 身份None但固定checkout同级布局不符/未知、没有受保护根.git，或session/字段错误 | 同样 identity 错误；任何Git查询前拒绝 | `("", "session_git_identity_unavailable")`，不调用walker | extra保护、注入与否或相同HEAD均不能授fallback |
| 分离 source_relative_path 非 dot | 同样失败关闭 | `("", "workspace_shape_unsupported")` | 不称子树为整仓 |
| base 或 actual format 与固定 revision 不符 | 原 Git identity 错误边界 | `("", "session_git_identity_unavailable")` | 不拿 caller 字段替代真实状态 |
| walker 不稳定、超限、特殊类型等 | 不替代其既有结果 | 保留原 WorktreeTreeUnavailable.reason | 不返回部分 OID |

state 读的既有调用者捕获/报告 ValueError 流程保持；不吞 OSError 等既有非 session 失败改变 legacy 故障分类。生产实现需避免 blanket except BaseException：KeyboardInterrupt/SystemExit 不转成功或伪清理；GitStatusUnavailable 与可预期身份错误仅在本片的分离边界归一化。

## 5. 全调用链接线与兼容

下表位置均以基线 8d 为准；实现后由符号而非旧行号核查。

| 调用方 | 当前位置 | 必须保持的接线 |
| --- | --- | --- |
| run_contract_step 工程 admission baseline | 1208 | 实际 workspace_session 传入 state；在 CP/model 实质动作前核可信来源；原 admission/错误处理不放宽 |
| resume_contract_step 工程恢复 baseline | 2703 | 同样 session-aware state；不重建 baseline、不重放已完成动作、不复用旧 receipt |
| _contract_engineering_gate 测试前/后 | 1756–1761 | 两端 state 与 tree 均传同一 session，保持原 before_head/base 与 snapshot 稳定断言 |
| _run_task_reviewer 内部末尾 tree | 3456 | 传已有 workspace_session；不能遗漏这个额外的 tree 重核 |
| _contract_engineering_gate Reviewer 后 | 1835–1836 | state/tree 同 session；保持 plan、snapshot、HEAD/OID 对比 |
| _contract_engineering_binding_error 最后 CP 边界 | 1879、1885 | state/tree 同 session，CP/body/deepcheck scope/Plan 重核原样保留 |
| _measure_task_verification 的 before/after 与 run_task baseline | 2797–2809、2858 | 无 session，完全保留原参数形状/原根限制/故障分类 |
| bind_task_result_commit → read_git_commit_tree_oid | 3717–3789、workspace 964 | 本片不改；仍只普通仓库根的显式 commit 内容比对，未支持分离 session 的 result-commit binding |

兼容不是仅新增默认参数：无 session 时各 caller **不要新增 `workspace_session=None` keyword**。已有 `test_r3_regression.py:1419` 的旧 tree wrapper 只有 object_format keyword，`test_verification_measurement.py:125` 的 state double 只接受 workspace；保持这些旧形状，不通过宽化所有测试 double 隐藏调用链回归。实际 session 分支才传新 keyword。可以采用局部条件 kwargs；不得为了省行引入全局重构或让 `_measure_task_verification` 获得 session 授权。

`tested_git_tree_oid` 始终只是完整 code 根的原始文件投影；稳定不等于 result commit 已匹配，不等于真实模型成功、独立 OS Reviewer sandbox、installed wheel 或 Native 准入。code/deepcheck 的所有普通门与开始后源码冻结条件不变。

## 6. 实现文件范围与真实测试矩阵

预期生产只改 `src/icode/runner.py`；不改 git_broker、workspace、workspace_snapshot、Native flag、ICODE-SKILL、CP/schema、package 权限。必要测试可新增 `tests/test_session_git_projection.py` 并在 `tests/test_contract_engineering.py` 增加最小接线回归；现有 r3/measurement/git_broker/walker 测试只运行，不默认重写。测试选择若需新模块加入已有总集合，由实施计划核 actual loader/守卫，不猜脚本、不漏选、不重复收集。

矩阵是计划要求，**本轮未运行**；所有真实文件/Git/manager 由明确 owned 临时 source/data 根创建，不操作主工程 checkout、不新增主工程 Git 分支。单测隔离 double 只可观察 caller 参数或模拟漂移时刻，不可把该 double 层报真实 OS/CP 产品链。

| 向量 | 正/负控与验收 | 信用边界 |
| --- | --- | --- |
| S-01 | 真实 manager 分离 dot session：actual state==fixed revision、tree captured；与同一 Git fixture commit 原始根 tree 相等 | 真实 host 文件/Git/session；不运行 native/model |
| S-02 | sha1 与 Git 支持时 sha256 各核 actual格式、OID长度、base一致；caller错误format/base拒绝 | Git不支持sha256须明确环境skip，不能冒充已通过 |
| S-03 | 相邻/子目录/checkout/root路径混用、另一session、relative/..、source_relative非dot | 明确拒绝；绝不读兄弟目录求整仓tree |
| S-04 | 缺失/错类型/非空失效identity、身份集合缺失或重复、inode/dev/token变更；真实分离manager身份置None且无注入拒绝；session固定布局/保护清单错字段、未知布局、前后字段漂移或检查错误拒绝 | 复用真实 verifier与现有固定同级布局；任何Git查询/walker前拒绝失去资格，不用保护成员或缺身份升级普通根 |
| S-05 | `.git`/commondir/HEAD/ownership真实改写、同内容替换、目录替换或symlink | 前后实际身份门拒绝，不能只mock verifier失败 |
| S-06 | code/.git 为文件、目录、链接/悬空链接及lstat检查错误；组合负控分别有无extra保护code/.git：真实分离manager保持其原固定字段，身份置None，注入指向原仓同HEAD的.git；extra项由真实manager构造而非测试手改清单 | 强断言state/tree均拒绝，任何Git查询/walker均未执行，尤其不使用注入Git库；不能靠extra保护、相同HEAD或.git存在取绿 |
| S-07 | 捕获中更换session身份/根、改HEAD/metadata、改actualformat | 后核拒绝；故障注入时刻层与真实文件变化分别记录 |
| S-08 | 测试期间源码/类型/模式/链接目标变化、nested.git/特殊文件/超限 | 原 walker/稳定窗口拒绝；symlink只hash目标文本不读目标正文 |
| S-09 | 无session普通root正控、父仓子目录负控、非Git保持原结果；真实非分层manager dot-root身份None、固定同级布局成立且workspace/.git在原protected_paths时state/tree保持正控，另含无关extra保护正控；合法snapshot无Git身份原行为保留 | 原root限制与调用形状兼容，不为拓扑新增配置/持久flag，不把fallback条件附加到无session/snapshot |
| W-01 | contract admission/gate前后/Reviewer内部与外层后核/finalCP/resume每一位置同一session | caller参数观察；不得计真实wholechain |
| W-02 | 真实dot manager+真实state/tree，经现有工程 gate fixture 的 transport double 验证 stable 接线；另用 Reviewer真实读/submit控制double | 明确 transport/model_double，只授接线，不授native/语义质量 |
| W-03 | Reviewer后/finalCP真实源码或身份漂移、deepcheck开始后源码/范围变更 | 原阻断与CP不可推进保留，不能重捕获取绿 |
| C-01 | 原 measurement/r3/task IO/timeout、旧精准签名double、普通result-commit比对 | 全部回归；分离result-commit仍明确未支持 |

本片批准后实施须 RED→GREEN、author自SPEC/自QUALITY、独立SPEC→不同QUALITY、root全局审查、点测/20轮/DEFAULT/同冻结源原full一次、compile j1、非测试守卫、文档连续两轮clean、exact main提交推送及绑定SHA的CI观察。不能从此设计自检推出这些已完成。随后的 Linux engineering bridge 还须真实资源通道、CP/operation/receipt/pack/Reviewer与普通code/deepcheck门、source/installed层矩阵；此片成功只解除其中Git接线阻塞。

## 7. 上游借鉴与许可

只读并行研究由 git_projection_arch_research 独立提供；2026-10-09 03:41–03:43 UTC 观察窗口的固定证据（Codex 固定旧输入，未新查 HEAD；Aider 官方 main 本次重核）：

- Codex `82883da25e3be5883e905afa02c3a639d02a97aa`（commit 02:59:21Z），[worktree.rs](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/git-utils/src/worktree.rs) 的 repository_identity 34–87 区分 common_dir/relative_cwd/primary_root，核 linked metadata/backlink。采纳身份、相对cwd、行政目录分层机制；不把其 canonicalize/父层发现当ICODE授权。
- 同提交 [baseline.rs](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/git-utils/src/baseline.rs) 的内部reset写对象、索引并删除/重建.git（研究所读65–159、173–258）。不适配用户工作区，不借此修复布局。
- Aider `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`（commit 2026-05-22 14:02:20Z；本次官方HEAD仍该SHA），[repo.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repo.py) 的父层发现是普通UX，root与subtree_only分别处理。仅借鉴范围分开命名，拒绝子树OID充整仓；不移植其父层发现授权。

研究代理全文读两根 Apache-2.0 LICENSE，无复制、依赖、运行实验或完整上游产品验收。本文作者未重新读取上游源码；引用是独立研究输入，不伪装成作者实际全文审查。后续 root 纳入持续对照时记录研究窗口/实际阅读范围，不覆盖旧日期。分离权限、no-follow、稳定性断言以 ICODE 当前实现为准，不由竞品行为替代验收。

## 8. 已核范围、自检与未通过门

作者完整阅读 git_broker.py 524行；workspace_snapshot.py实际选读1–300、830–1174（POSIX完整tree投影/快照及公共接口，未全文读Windows walker）；workspace.py选读363–470、895–1040、1440–1469、1609–1685、1740–1885、2030–2220；runner.py选读1–100、1180–1240、1320–1479、1713–1895、2567–2777、2778–2890、3017–3485、3640–3867。一次大输出中1790–1895曾截断，已单独完整重读该段；不以保存全日志冒充全文审查。tests实际选读git_broker1–210、contract_engineering1–220、r3_regression1190–1244/1400–1445、verification_measurement105–170，另按rg核全相关符号调用点；没有声称完整阅读这些大型测试模块。

冻结生产SHA256：

| 文件 | SHA256 |
| --- | --- |
| runner.py | 2b145db41b3ebbd0f90f3e9d8b19e73b9ca6a08c97e1ba5fbe59d6d777ea671b |
| git_broker.py | e174d3fa75abb19b2c82aff835a638ac29df82665029c7be47b8063dc3a2c14e |
| workspace.py | 4fe2dd726ef75f53175bd8e69408855174f5b84ce5fcebf76c7ed98bdf1c7753 |
| workspace_snapshot.py | 56cdd4442a91c081e8cf1b86963f9894a1a55b458ff57584340229f4895d3eaf |

sequential-thinking 已完成三步（需求分解→同源state/tree方案分析→身份/范围/兼容风险），结果记录本任务context。技能采用 brainstorming 与 tech-design 的需求/边界/API/流程/测试体例；Java/Spring/MySQL专有规则不适配此Python内部修复，无HTTP API、MQ或数据库迁移，不新增这些组件。用户连续自主授权覆盖routine等待，但不覆盖独立设计批准与验收门。

审查历史：首稿SHA256 `7647171d47ceec2751aaa9bf8eb8847adb28dae937b334d1081419da23310ae1` 的作者自SPEC/自QUALITY均为C0/I0/M0，随后 fresh SPEC 得到 **C0/I1/M0**：无分离身份时普通root fallback资格不明确，可能漏掉身份None+code/.git同HEAD注入组合。原自审不覆盖此缺陷，不是独立批准。此修订依据真实manager原protected_paths拓扑明确路由，增加S-04/S-06/S-09子向量；未实施也未执行负控。

第二次审查历史：保护成员资格修稿SHA256 `ea665a2f3f49d952977407d1765e4b910accc4d03d1f5cbd0d4dcb09565d7011` 的作者自SPEC/自QUALITY均为C0/I0/M0，fresh SPEC仍 **C0/I1/M0**：宿主extra_protected_paths可加入code/.git，保护成员并非布局来源，因此identityNone+extra保护+同HEAD注入组合仍缺资格区分。此稿补现有可信manifest/runtime/receipts/workspace同级固定等式，保护成员仅必要非充分；此前自审不覆盖该缺陷，不伪装独立批准。

本稿作者自SPEC：C0/I0/M0；固定checkout资格与根保护成对必要、额外保护不upgrade、前后字段重核和组合负控明确，其余scope/边界未改。本稿作者自QUALITY：C0/I0/M0；复用已有session schema固定布局，不读manifest/config重造授权，无新flag/权限，真正普通非分层root和无关extra保护兼容。两者不是独立复审，也不能授软件或native PASS；仍待 fresh SPEC 复审及不同 QUALITY。

【架构级自检报告】（仅文档设计层）

- ✅ 语法/结构：Markdown结构、字段与接口合同已检查；无生产代码编译声明。
- ✅ 依赖/调用链：全部state/tree及Reviewer/恢复/最后CP边界逐符号列出；legacy独立保留。
- ✅ 逻辑/边界：注入、身份漂移、子树/整树、实际format/基线与无session已明确。
- ✅ 异常处理：路径无关失败状态、禁止fallback/伪证据；原legacy异常分类保留。
- ✅ 关联模块：CP/operation/receipt/Plan/Native不改；result-commit未升级。
- ✅ 兼容安全：最小runner范围、旧参数形状与根限制、无新增权限/依赖。
- ⚠️ 可运行性：仅设计，未实施、未执行任何测试/编译/安装/模型；不得声称100%运行通过。

未通过门：独立SPEC/QUALITY、实施计划、RED/GREEN与完整本地软件验收、目标CI、真实Linux产品工程往返、installed与模型、Windows与macOS剩余指标。设计交付后STOP，批准前不写生产或测试。
