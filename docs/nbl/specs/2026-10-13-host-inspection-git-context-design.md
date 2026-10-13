# 宿主固定 Git 身份的 inspection 最小跨仓设计

状态：DESIGN / 候选；不代表 SOURCE 已实施或 S2c 已验收。文档日期沿用任务名；实际观察日期 2026-10-14。用户已授权最小跨仓实现和候选验收流程；本独立任务仍仅新增本设计文件，先交独立评审，不修改源码、固定子仓、系统、Git 状态或远端。

## 结论与三问

真实问题已确认：Linux 隔离工作区的代码根不包含 `.git`，而 inspection 的仓库发现依赖代码根以内的 `.git`。现有 implementation 已确认：宿主有 `WorkspaceSession.git_status_identity`、安全 Git identity verifier、固定 inspection runner 及 Skill 的完整工作清单重建器。调用链已确认：prepare/read/check 与最终 step gate 都必须使用同一宿主 Git 身份；只补脚本调用不能修复发现失败。

采用方案 A：“宿主绑定、Skill 私有 FD 消费窄 provider、每次独立重建”。代码读取继续指向 `checkout/code`，Git 对象与 index 来自该会话注册的受保护 worktree；只固定必要 metadata 输入，绝不复制 CODE。禁止把 `checkout` 当作代码树，禁止启用 `allow_incomplete` 来通过 normal 门禁。

决策历史：首版候选 SHA256 `714e64ba3776e1d43e292a0376fc64904a3e1d823259e8c3de8ff7e2c89c0764` 把载体/ABA/ledger 留给实施决定；第二候选 `d41ca0b95afe24ef469ec5698ff0b3b2547a0f02beb1378e46215c667f656f3f` 有 assessment/sharedobjects/baseline digest/整体pin四项问题；第三候选 `e92a0f9492489d304033deffa0ef10f04b2961481cf49c7729a0e8513f7b31f4` fresh SPEC C0/I0/M0、QUALITY C0/I1/M1，要求补 attributes 输入与成功发布/资源清理信用。本次保留这些历史并收束下述规则，不启动 SOURCE。

## 来源与边界

权威工作区 `/home/orbbec/projects/icode`；读取时 HEAD `6e893f0170b74c32d7143680636d85f400ecc7c9`，固定 Skill HEAD `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`，均已本机只读 `rev-parse` 核对。源文件通过 WSL UNC 读取；同任务其他成员可正在修改工作树，下面以符号为主、观察时行号为辅，实施前须对最终候选重新定位。

固定版本链接：[WorkspaceSession](https://github.com/ayukyo/icode/blob/6e893f0170b74c32d7143680636d85f400ecc7c9/src/icode/workspace.py)、[Git broker](https://github.com/ayukyo/icode/blob/6e893f0170b74c32d7143680636d85f400ecc7c9/src/icode/git_broker.py)、[inspection helper](https://github.com/ayukyo/icode-skill/blob/21566a589cbe98bd35372a04bbb6ca1c51d8eed2/tools/inspection_worklist.py)、[控制面](https://github.com/ayukyo/icode-skill/blob/21566a589cbe98bd35372a04bbb6ca1c51d8eed2/tools/icode_control.py)。这是固定运行时源码证据。

来源复核：UNC 原始读取曾出现 `_run_agent` 行号 2504，与随后读取不一致，该行号已撤回，不能据此推断源码发生变化或误用了旧 D 根。当前实际 UNC runner SHA256 `91e5e6cc6fb0c1c12f9c769bd30aea5b9e95d7dcd3dc01bea6027d6d6074869b`，workspace SHA256 `c8692242d1392e6170e075d208c042e7c6b33cc65eaeaa93d7fa9d0bcc12e368`；`_bound_inspection_runner` 2503、`_run_agent` 2568，与主代理独立真根证明一致。

另外已实际浏览 GitHub [52cb6b3 helper](https://github.com/ayukyo/icode-skill/blob/52cb6b3f0229bfc16e6faf00ce5dd2506e252a22/tools/inspection_worklist.py) 与 [52cb6b3 CP](https://github.com/ayukyo/icode-skill/blob/52cb6b3f0229bfc16e6faf00ce5dd2506e252a22/tools/icode_control.py)，并只读核对 canonical native `/home/orbbec/projects/icode-skill` HEAD 为该 SHA、status 空。该 clone 来自主代理说明的本地 Git 对象，不等于重新验证远端 main。候选源码 `_repo` 219 仍依赖 `.git`；build_worklist 309、_rebuild 470、validate_worklist 624 与 CP cmd_inspection 5290 无 git_context/trusted_git 入口。该候选新增 `_trigger_content` 的 unified diff，用于已移除代码的特殊规则触发；它也必须走同一 provider，不能只适配固定版本旧查询集合。主仓 vendor 仍是 21566a5，不能把 52cb6b3 新逻辑宣称为当前运行能力。

Git 官方文档于 2026-10-14 实际浏览：[git 全局选项与环境](https://git-scm.com/docs/git)、[diff](https://git-scm.com/docs/git-diff)。采纳显式 `--git-dir` / `--work-tree` 的仓库与代码分离机制；保留 `--no-ext-diff` / `--no-textconv`；这些参数本身不保证只读权限或会话身份。本机和 CI 的实际 Git 版本仍须记录，不以网站最新手册代替运行版本。

主仓与固定 Skill 的本地 LICENSE 均为 MIT；复用自己的现有 verifier 与工作清单机制，不引入新第三方实现。许可义务保持原版权/许可文本；主要成本来自安全查询与跨层验证，非许可转换。

## 调用链和契约矩阵

| 边界 | 当前行为与观察证据 | 期望契约 | 判定 |
|---|---|---|---|
| WorkspaceManager → session | `workspace.py:_materialize_git_tree` 1484–1509 将 blobs 写入 code_root，`read-tree revision` 初始化 worktree index；`_session` 2140–2217 构造受保护身份 | 当前代码来自 code_root，baseline/index 属于同一注册 worktree | supported |
| session → Git broker | `git_broker.py:verify_git_workspace_identity` 282–404 验证目录 dev/ino、pointer、commondir、HEAD、token | 可复用基础布局校验；inspection 另外绑定查询所用 index/config | 基础 supported；新扩展 candidate |
| Git broker → native runner | `managed_git_status` 102–149 固定 root repo、git executable、metadata read roots、只读 workspace | 只运行固定允许查询，网络关闭，metadata 不写 | supported；当前仅 status，不能冒充 diff ABI |
| host → inspection tool | `runner.py:_bound_inspection_runner` 2503–2565 固定 out_dir/ticket/step/attempt；tool schema 不给模型目录控制 | 在同一闭包增加宿主 Git context，模型参数不扩大 | candidate |
| ControlPlane → Skill prepare | `icode_control.py:cmd_inspection` 4803+ 使用 execution_workspace，现无 Git context | execution root 与 Git context 双绑定，不能从报告反向信任 | mismatch supported |
| helper repo discovery | `_repo` 198–205 只搜索 root 内祖先 `.git`；`build_worklist` 349–351 产生 no-Git debt，395–396 改为 partial | 宿主 context 显式声明单一受保护 repo；源码目录仍是 code_root | mismatch supported |
| read/check/rebuild | `_rebuild` 400–419、`validate_worklist` 435+ 与 `validate_findings` 499 重派生；CP `inspection_worklist_issues` 1722/1730；check 4823+ | 每条重建路径重新取得可信 context；保留相同范围、hash、baseline 门禁 | candidate；漏传一条仍会失败 |
| final step output gate | CP `step_output_issues` 1709–1710 调用工作清单验证 | 实际 check 与 step finish 均 strict；失败不写成功事件 | 必须验收，尚未验证 |

根因允许的表述：固定 helper 的仓库发现协议与 Linux 分层 session 不兼容。禁止扩大为“Git 丢失”“metadata 未创建”或“所有 S2c 失败均由此造成”。缺 `code_worklist` 的脚本入口与 no-Git partial 是两个先后独立障碍；后者通过此设计解决，前者仍需真实调用既有工具。

## 方案比较与决策

| 方案 | 收益 | 成本/风险 | 决策 |
|---|---|---|---|
| A：宿主保护 context + Skill 私有 FD 窄 provider | 复用现有 helper 全部派生逻辑；不增加代码副本；所有门禁重建一致 | 主仓与 Skill 最小双边 ABI、每调用必要 metadata snapshot、native 只读查询 | 采纳，本文唯一实施方案 |
| B：宿主生成限定 Git 查询结果包，Skill 重建消费 | Skill 不直接接触真实 metadata，可固定查询输出与来源 | 需预知 helper 的动态 query 集合，最新触发 diff 使结果包覆盖与来源验证成本超过窄 provider；跨调用复用会过期 | 暂缓，不在本次实施 |
| C：代码树内建立 `.git` pointer / shadow checkout / 扩大祖先搜索 | 改动表面较少 | 绕过隔离合同或读到旧代码；扩大自动发现、混合不同 Git 对象；模型可伪造仓库边界 | 不适配 |

不为本修复新增通用 Git executor、常驻 RPC 服务、多仓自动映射或写入 capability。IPC 仅是本次 CP 子进程的短生命周期 transport，没有监听地址、端口和外部发现入口。单层 root repo 以现 `managed_git_status` 的 `source_relative_path == '.'` 约束为第一版范围；snapshot、子目录项目、nested repo/gitlinks 显式拒绝，不能用父仓吸收。将来支持须另做契约和验收，不借此次扩大。

## A 的最小 ABI 与身份合同

新增内容均为拟议，当前不存在该 API。

1. 宿主从已准入 session 构造 `inspection_git_context_v1`，通过本次 CP 调用临时继承的双向 `socketpair` FD 传入窄 provider。只有 host CP 子进程继承客户端 FD，host 端保留服务 FD；模型 subprocess、普通 tools 和 Git 子进程均 `close_fds`，不继承该 capability。没有环境路径发现、端口和 JSON CLI 身份载荷。FD 号是 transport 标识，不是授权凭据；host 校验本次 peer/session/nonce，不能凭猜到 FD 号绑定身份。
2. host 内存 context 包含版本、project/ticket/run/step/attempt、workspace/code/checkout 根、git_dir/common_dir、固定 revision、source_relative_path、token、filesystem identities、snapshot index/config digest；Skill 只收到 repo label `'.'`、schema、binding digest、调用 nonce、输入 snapshot digest 和允许 query 能力，不收到原目录 dump。宿主 context 不来自模型、report、环境 `GIT_*` 或任意 JSON CLI 参数。
3. Skill helper 增加 keyword-only `git_provider=None`，贯穿 build_worklist/_rebuild/validate_worklist/validate_findings/实际登记 Read、apply_assessment/_checks_issues/_assessment_issues/_content；provider 为 CP 根据本次继承 FD 构造的对象。省略时保持普通本地 repo 路径的旧行为；ledger 声明 host-bound 执行时 provider 缺失、版本不匹配、peer/nonce 不符必须失败，不能退回 `.git` 搜索。
4. 显式 repo label 为 `'.'`，逻辑 repo root 为 code_root。baseline、diff、ls-files、历史 deleted content 通过同一 provider 使用受保护 git_dir/common_dir/index 与 code_root worktree；相对路径算法保持原语义。禁止把受保护 git_dir 误作 repo label。
5. provider 固定五类 query：`resolve_commit(ref)`、`diff_names(oid, relative_scopes)`、`list_files(kind, relative_scopes)`（kind 仅 tracked/others/association）、`historical_blob(oid, relative_path)`、`trigger_diff(oid, relative_path)`（统一 `--unified=0`）。query 参数只有严格范围内相对路径、受 host 认可的 commit、上述枚举；内部构造 argv，不接受任意命令列表。host 执行原生隔离 Git，Skill host-bound 路径不得调用旧 `_git` subprocess。返回 raw bytes、truncated、exit status、snapshot digest；任何失败均不可成为成功/空列表。全部消息有长度上限、query 数上限与本次总 deadline；未知 opcode、超限、EOF、重复序号、错误 nonce 均结束调用并失败，不保留后台服务。
6. Git 查询复用 native metadata 只读根、可信 `/usr/bin:/bin` Git、无网络、固定 cwd/code_root 对象；清理环境中的全部 `GIT_*`，设置固定 index，禁止 alternate index/object 路由污染。保持 fsmonitor/hook overrides 与 filter/worktree filter、gitlink 拒绝；diff 另外固定无 ext-diff/textconv、无 rename、literal pathspec。不能只复用 unsafe helper `_git` subprocess 后宣称 native 隔离有效。
7. prepare/read/check 与 final validator 每次重新取得 provider/context，不能根据报告内容创建 context。worklist schema v1 保持结构不变，context binding digest 放在新增 host ledger 事件和工作清单 receipt，不新增目录字段；现声明 hash、scope/bytes/hash/pinned baseline 验证保留。新的 FD provider schema 固定 v1，未知版 fail closed。

## 时间、索引与文件同步

`read-tree` 把会话 revision 写入本 worktree index，code_root 是 materialization 的目的地。后续模型 edit 直接改 code_root；不需要将代码复制回 checkout 根。查询必须 `--work-tree code_root`、cwd 同一已验证 code_root。deleted file 的历史内容用同一 Git 对象库和已解析 commit 获取，不能从 source_root 或 shadow 副本读取。

现有 verifier 没有 index 身份。现 managed_git_status 的源码注释（245–248）明确后检不冻结 config/index/refs，因此不能把其现有保证包装为更强的 inspection 保证。

唯一输入固定方案是“受管会话 writer 串行锁 + 必要 metadata 和查询对象闭包的不可变 snapshot”，不是仅前后 digest。host 在本次 CP 调用开始取得会话 inspection epoch 锁，锁顺序固定为会话 epoch 锁→CP DirLock，整个 helper 派生及 CP 成功事务发布期间持有。所有受管会话 code/index/metadata writer，包括 tool edit/write/exec、host workspace materialization/reset/index 更新均接同一锁；后台 payload 没有 cleanup 完成证明即拒绝开始 inspection。既有 ticket lease不能未经证明等同于 epoch 锁。

`workspace.py` Git identity 来源（932–938）及 `_create_git`（1835+）证明 common_dir 是用户源仓对象库；用户普通 git gc/repack/prune/自动 maintenance 是合法活动，不服从 ICODE 内部锁。本设计不要求用户普通 Git 接锁，也不把这些活动列为攻击。原共享对象库只用来有界抽取内容；所有正式 helper query 都改在已完成的独立 immutable object snapshot 上执行。

锁内先校验布局和 source 对象 FD，再将必要 metadata 用已打开 `O_NOFOLLOW` 普通文件 FD 复制至宿主保护的 invocation 临时目录。固定集合：本 worktree index、detached HEAD、有效 local/worktree config、info/exclude；对象闭包不遍历父历史，无需复制 shallow/完整 refs。拒绝 config include/includeIf、filters/helpers、fsmonitor 可执行设置、worktree extensions 不支持项、split index（sharedindex）、sparse index、object alternates、gitlinks、外部 exclude 文件与缺 index。首版仅支持已核验的 repository format 0 / SHA1；其他格式显式拒绝，不猜测转换。每项带源 dev/ino/字节 hash，copy 后从源 FD 再读核对；所有 snapshot 文件封为只读并属于 policy deny-write roots，host 服务也不再修改它们。

snapshot 是 host 内的最小查询 metadata 目录，不在 CODE 内创建 `.git`，也不建立第二份代码树。HEAD 是经认可的 detached commit；config 由采集到的允许配置字节解析并生成不可变有效配置，保留 core.filemode/ignorecase/autocrlf/eol/symlinks 等会影响结果的安全语义，不复制未知执行配置。索引字节来自相同 session 的 worktree index。用户源仓 config/info/exclude 不受会话锁控制；capture 到的字节须完整解析、来源身份核对，已采集值就是本次明确输入，不声称其永久当前或前后 digest 能证明 ABA。后续不再读取可变源配置；下次 invocation 重采集值变化即 invalidates 原 receipt。

snapshot 的 `objects` 是独立 host 私有目录，禁止 symlink/alternates/任何源库路由。对象闭包确定为本次 pinned baseline commit 的完整 tree/blob 闭包，加固定 index 所引用的全部 blob OID；不递归 commit parent，不包含其他 refs、历史版本、reflog、完整源仓。helper 有全仓范围 outside-diff/exclusion 扫描，Git 可能比较 index 的工作区字节，因此不能仅抽 code_files blobs 后声称 query 完整；全部已选 baseline 树及 index blob 是这组查询的保守完整闭包。多个 baseline commit 的对象按 OID 去重；tree 中 gitlinks 拒绝。被删除 source evidence 与 trigger diff 使用同一闭包。

抽取只用固定 `cat-file` 类型/内容查询，不开放任意 argv。先建立 host 私有 extraction metadata：配置使用已经复制/消毒的有效值，禁用 system/global/GIT_* 环境，HEAD 固定候选 OID，禁止 replace/graft/alternates/promisor 路由；只有 extraction 阶段的 host 创建 objects 链接指向已准入 source objects，并由 source readonly native 闭包限制。绝不拿原可变 config/env 执行 bootstrap。这个临时来源链接只用于构建 snapshot，不是正式 query 输入；封存前移除链接，切换为独立只读 object store，不能向任务暴露它。

host 解析 commit 的 root tree、原始 tree entries 与已固定 index OID，逐对象取得 type/size/bytes，验证 SHA1(`type + ' ' + decimal_size + NUL + bytes`) 精确等于请求 OID。commit/tree 结构不合法、长度不匹配、缺失对象、Git 截断/退出失败、对象总数/总字节/单对象/总 deadline 超限均拒绝本次调用，不退到原对象库、不自动网络抓取。写为 stdlib zlib 压缩 loose object，所有目录和文件封只读；写入能力仅是 host 私有 snapshot builder，不给 Git 子进程通用 write 权限，没有新依赖，也没有第二份检出代码。抽取时合法 repack/prune 可导致成功取得并验证完整 bytes 或明确失败，两者都正确。成功对象内容已由 OID 验证，原库后续移除/替换无需追踪，也不能污染 snapshot。原共享 object FD/dev+ino 不再被宣传为闭包冻结证明。

对象抽取预算新增为明确 host admission 参数 `inspection_snapshot_max_objects`、`inspection_snapshot_max_bytes`、`inspection_snapshot_max_object_bytes`，首版默认 100000 / 256 MiB / 64 MiB，同时受现 invocation 总 timeout/output policy 约束；任何调高必须由 host 配置，不由模型 scope 提升。这些是有界失败阈值，不保证任意大小项目通过。独立验收必须包含触发每个预算上限的拒绝测试。final 与 prepare 使用同一预算配置并将其纳入 input digest。

正式 query 的 native metadata read roots 只绑定 snapshot root 的身份，不再允许读原 common_dir/objects；cwd 仍固定 code_root。Git argv `--git-dir snapshot_root --work-tree code_root`，固定 index snapshot，禁用 global/system config；snapshot 不放 refs/replace/info/grafts/alternates/promisor 路由。native policy 无法表达该最小只读根时拒绝调用，不退到 raw subprocess。

attributes 是明确输入：[Git 官方优先级与 index fallback](https://git-scm.com/docs/gitattributes)（主代理2026-10-14实际核对，L280–283）指出 metadata info/attributes、CODE 祖先 .gitattributes 与 index fallback 都影响匹配。首版 host-bound 检查 source `info/attributes` 的缺失/空文件身份与内容摘要，非空明确 unsupported/reject；这是窄 metadata unsupported，不拒常见 CODE `* text=auto`。固定 `core.attributesFile=/dev/null`、`GIT_ATTR_NOSYSTEM=1` 并禁 system attrs；不得默默使用用户额外 attributes 文件。

CODE .gitattributes 不复制影子树：从真实 CODE 捕获所有可能参与全仓 diff/list/association/trigger/history 路径的祖先 .gitattributes（含 code root 和scope外目录），记录缺失状态、路径/dev/ino/bytes hash，纳入 input digest并在 epoch 前后核对。文件缺失时对应 index fallback blob 已在独立固定 index/object闭包中，fallback OID与bytes摘要也纳入 attributes 输入；不能仅检查种子/scopes目录。正式 query 保持读取真实 CODE attrs，受管 writer 在epoch内不得改变。普通安全 text/eol/binary-source byte语义保留；effective attrs 若指定 filter/textconv/custom diff driver、`-diff`/binary 隐藏文本触发、working-tree-encoding 或其他未经本次支持验证的执行/内容变换，host-bound 明确类别unsupported而不宣称 complete。必须用消毒 snapshot Git 的固定只读 `check-attr --all -z --stdin` 私有预检验证effective attrs（不是开放第六模型query），覆盖所有枚举路径；任何未知 attr/宏展开不能安全证明时失败。该预检同无network/helpers，不触发 filter 执行。legacy None路径原样。

符号 baseline 只在首次 prepare 的 bootstrap 阶段解析一次：HEAD 使用会话已验证 detached revision；声明 local refs 的 loose/packed refs 由 host 以 bounded `O_NOFOLLOW` FD 捕获至私有 metadata，解析得到候选 OID，再通过消毒 extraction metadata 的固定 cat-file 验证为 commit。annotated tag 仅沿已捕获 tag OID 有界校验 tag→commit 链，不开放任意 rev expression。解析能力首版仅 HEAD/完整 commit OID/合法 local ref 名，其他表达式明确拒绝，legacy 路径不改变。prepare receipt 在宿主受控字段持久化 baseline declaration（包括缺省 HEAD 的展开值）和对应 resolved OID；工作清单仍保留原 baselines/resolved_baselines，host 独立核对 receipt 与它们。后续 read/assess/check/final 读取真实宿主 receipt 的 declaration→pinned OID，不再从当前 HEAD/local ref 解析；provider 对原声明和对应 OID 都返回同一已固定 commit，仅检查 pinned commit 在本次 snapshot 有有效对象。receipt 缺失、report 改 declaration/pinned、无法抽取 pinned commit 均拒绝，不能切换到新 HEAD。用户 source branch 更新不是会话 detached HEAD 变化，不能据此失效整个 receipt。

`_rebuild` 470–486 当前传 resolved_baselines OID，再把报告原 baselines 复位，这条语义必须保留。snapshot digest 中 baseline 部分统一按 repo label 排序的 `{declaration, resolved_oid}` canonical pair 计算，来源是宿主 prepare receipt，不是本次 helper 实际用了 HEAD 字符串还是 OID 字符串。对象部分是上述确定闭包的排序 OID/type/size/hash 集合；不含随机目录/nonce、源 pack 文件 inode、source refs 当前 bytes、无关 refs/history，也不因 repack 变动。配置/index/当前 CODE/预算/binding 的摘要独立纳入。故 source HEAD/分支变化而 pinned commit 仍能抽取时，后续检查继续原 baseline；若同时有其他明确输入变化则按相应漂移规则失败。不能将当前 source ref 变化误算成旧 baseline 漂移。

不是整体复制对象库：仅复制明确查询闭包；合法外部维护可以在抽取中并发。完整验证并封存前不允许正式 query；抽取未完成或失败不产生成功 receipt。query 输出绑定独立 snapshot digest；会话 pointer/HEAD/token/index 与 CODE 前后校验失败仍丢弃结果，作用是受管来源漂移检测，不宣传检测全部 ABA，也不依赖源 pack inode 永远不变。

CODE 从同一已准入 workspace FD 读取真实当前字节，scope 范围内枚举清单与必要文件 hash 在 epoch 前后验证；禁止从 snapshot/source_root 取当前文件。枚举/字节预算不足则失败，不用抽样说明全覆盖。prepare 与后续 read/check/final 是不同 epoch，每次重新固定输入；prepare 后任何来源状态/代码变化必须重新 prepare/read，旧 receipt 不通过。

威胁边界明确：scope 内 payload 无 metadata 写权限、无 IPC capability、无法伪造 host binding；合法受管会话 writer 全部遵守 epoch 锁，epoch 内没有受管 writer ABA。用户源仓普通 Git maintenance/config/ref 活动仍是合法并发，由独立固定输入和 OID 校验处理，不依赖接锁。恶意 root、同 UID 宿主程序替换解释器/绕过访问控制直接修改 host 私有 snapshot 属于完整宿主失陷，本文不声称抵御；不得豁免任何有合法受管入口但未接锁的 writer。发现未覆盖受管 writer 即阻止交付。

baseline 的 symbolic ref 在 prepare 解析为 commit，重建继续用 pinned OID。不可自动跟随更新的 HEAD；所有 object 输出核对同一 context。index/config、timeout、预算、非 UTF8/binary 与历史文件缺失失败沿原 helper 语义，不改为覆盖完成。

## Ledger、权限与静态传播

ledger 选择新增受控 `bind-host-git-context` host CP 入口和 `host_git_context_bound` 事件，版本 `host_git_context_v1`。它沿现 bind-execution-root 准入/事务路径实施，不属于 model schema，不接受模型或报告 JSON。host 只经私有 FD handshake 提供 project/ticket/run、execution-root digest、session token digest、base revision、context schema、binding digest；事件不记录真实目录 dump。binding digest 固定 canonical JSON 算法与 v1 字段集合，不能把 invocation nonce/index snapshot digest 混入长期 binding identity。

每次 inspection/最终验证 receipt 另绑定 step/attempt/phase、binding digest、本次 input snapshot digest、声明 hash、完整派生范围 hash、工具退出状态；使用现有工作清单 artifact_written/receipt 事务追加这些受控字段，保持已有事件不变。check 不写 artifact，最终 gate 从本次 provider 独立重建核对 receipt 的来源摘要；query 结束前不发布成功。绑定失败、缺 binding 事件、同请求跨 context 重放、上下文 schema 不同均明确 blocked。resume 必须由 host 重新准入同一 session 并校验事件 binding，不能从事件原样反序列化目录获得能力。

context 不能由 artifact writer、submit_artifact、write_file、普通 shell、Reviewer 或模型额外参数替换。caller 可以要求合法 scope/baseline，但不能改变身份目录、index、executable、env、控制面目录或 writer role。请求 id boundary 应绑定 phase/relative scopes 与宿主 context digest，防止同一 id 跨 context 重放。

52cb special-check 合同的最小 Agent 入口适配纳入本次授权范围：当前 builtin.inspection 635–688、registry schema 1215–1235、runner adapter 2503–2568 均仅 prepare/read/check，真实整体升级必须成对增加 `phase=assess`、`check_id`、`assessment_json`。assessment 严格解析为现 Skill assessment schema，只允许已派生 check_id、当前 required read_phase、有限字节/条目数、合法相对 evidence path；不接受绝对目录、context、argv、writer role。这仅补齐既有上游 inspection 契约，不扩模型宿主身份权限。保留原 read-only Reviewer 只能 read 的限制；prepare/assess/check 均不能让 Reviewer 写清单。

runner request 的幂等 boundary 增加 check_id、read_phase、canonical assessment digest、host binding digest；不把原 payload、真实 context 路径或源码 excerpt dump 到宿主操作日志。工具响应给模型当前实际 check_id、required_items、合法 phase 和合同批准的相对 source evidence，提示模型每项独立给出处理/结论/理由/证据，不能默认填 not_applicable。loop/prompt 的既有 inspection 顺序同步为 prepare→所需各 phase 真实 read→已派生每 check/phase 真实 assess→check；只有 checklist 确实为空才跳过 assess，工具失败/编辑漂移重置后续状态。loop 不能凭模型说“已评估”或空 assessment 推进，也不能工具 schema 支持但 forced 阶段仍禁止 assess。

主仓采用一个 host-bound ControlPlane invocation wrapper：负责 epoch 锁、snapshot、私有 FD、child 启动/有界响应、全部 cleanup；runner/chain/resume/final gate 都调用它，不只 `_bound_inspection_runner` 给工具注入。只有不触发 inspection 的纯 CP 操作无需 provider。Skill 的本次调用入口统一解 FD→provider，再显式传入下面消费者；无法证明覆盖某消费路径时 fail closed。

资源信用固定为两层，不要求CP证明自身退出后再发布。publish之前，CP调用私有 provider `finish_epoch()`：host关闭后续query能力，确认全部native Git/payload子进程已reap且cleanup_ok、无活动query、所有query/native辅助FD和worker thread完成有界终止、snapshot保持不可变、CODE guards仍匹配，返回绑定invocation nonce/input digest的completion证明。仅保留发送这条completion的可信transport control端点，发送后host关闭；CP接收证明后关闭客户端query FD，才允许写工作清单receipt或step_finished success。这个端点不再接受query，不携带任何payload执行能力；最终transport关闭证明属于wrapper收尾，避免要求发送端在发送前证明自己已关闭。任何query/resource失败在成功发布前直接失败，不能在finally只attempt cleanup仍写success。必要provider资源没有证明不返回completion。

trusted CP子进程自身退出/reap、宿主wrapper输出收尾、snapshot删除是publish后的host收尾，不是让CP递归证明自身退出。wrapper调用开始即在host receipts_root原子写 `inspection_invocation_state_v1` 记录，字段固定为invocation_id、binding_digest、input_digest、state=active、必要cleanup证明摘要；该路径在任务deny-write范围，非模型入口。成功发布后wrapper只有取得CPexit0/完整结果、FD/thread终止、snapshot已清理证明才原子改state=closed并返回成功信用。超时/崩溃/删除失败改state=quarantined，或保留active（宿主重启没能完成落盘时）；保留已实际写出的ledger success事件，用户taskstatus/ready/下一admission/resume必须先查host记录并拒绝任何active/quarantined，不因ledger success越门。不能覆盖/删除历史success伪装未发生。

snapshot删除失败保留原封只读目录并记录quarantine路径/identity，不换大目录递归删除、不忽略失败；wrapper返回cleanup_failed且不clear=1。唯一恢复流程由host recovery入口对同一invocation检查无存活process/FD/thread、snapshot仍受保护，完成精确目标清理后原子写state=recovered并追加受控`host_invocation_cleanup_recovered`事件；随后重新host准入/实际final check，不能直接恢复成功信用。没有回收证明则保持blocked。P1 helper纯软件子片没有这些host记录API，不能称已完成此规则；P2完整计划须定义上述finish_epoch、状态文件/恢复与restart-negative资产后才实施。

| 消费者 | provider 传播与成功条件 |
|---|---|
| cmd_inspection prepare / resumed prepare | build_worklist、重建已存 report 都用本次 provider；完整 snapshot 成功才 publish receipt |
| cmd_inspection read | `_rebuild`、current source Read hash、phase 登记均用本次 epoch；不是模型声明读过即通过 |
| cmd_inspection assess（52cb CP 5405） | apply_assessment 599 → validate_worklist 和 _assessment_issues 均显式带 provider；缺 provider 不可改结果/发布 assessment receipt |
| Agent builtin/registry/runner/loop/prompt assess | 严格枚举 check_id/read_phase/assessment schema，同 host-bound CP；幂等绑定 canonical payload digest；真实每项证据齐备才进入check |
| cmd_inspection check | inspection_worklist_issues → validate_worklist → _rebuild 使用本次 provider，strict coverage |
| validate_findings / special rule trigger | `_trigger_content` fixed unified diff 同 provider；发现证据重建不得调用 raw `_git` |
| _checks_issues → _assessment_issues → _repo/_content | source evidence 当前文件来自真实 CODE；deleted source 使用 pinned snapshot historical_blob；核对 excerpt/line/hash，不能在 deleted 分支绕回旧 _git；artifact evidence 保留既有 artifact 边界 |
| step_output_issues / before_finish / step finish / final check | invocation wrapper 注入 provider，独立重派生，actual success event 只在同 epoch 内验真后写入 |
| chain 原生调用和 resume | 同一 wrapper，绑定需当前 host session；host-bound 模式缺 FD 失败 |
| crosscheck helper | 本次不扩 runtime 支持；发现 host binding 时明确 unsupported/reject，普通 legacy 工作区原行为保持 |

实施前静态扫描上述全部入口与所有 `_git` 调用点；负向测试逐路径去掉 provider，确认 host-bound 全部失败。普通旧工单不补写可信 context，新 attempt 经宿主重新绑定。宿主输入 schema/ledger 验证器、pack/evidence 检查中新增字段的计数/枚举/摘要规则须同步，不以 artifact 有 hash 代替 provenance。

## 验收 oracle 与 strict rollout

| 类别 | 实际执行输入 | 必须观察的输出 |
|---|---|---|
| 正向代码来源 | code_root 修改 A，checkout/source/shadow 保留旧 A | diff 候选包含 A，Read hash 对应 code_root 当前字节；普通 workspace 内无 `.git` |
| 正向关联来源 | modified/added/deleted 文件、同 stem test、明确 related/scopes | prepare 完整派生；历史 deleted 内容来自 pinned OID；read 每阶段绑定正确 hash |
| 正向闭环 | normal code attempt 完整 before_write → prepare → read → check → submit → finish | 实际 ledger step_finished success；clear=1；无 allow_incomplete/degraded/no-Git debt；finish 再独立重建 |
| 身份负向 | 替换 checkout/code/cwd/git_dir/common/HEAD/pointer/token 的 inode、symlink、路径或内容 | 显式失败，不能返回空 diff/成功 check；不写 success 事件 |
| 输入污染负向 | 更换 index/config、GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE/alternates、恶意 fsmonitor/filter/textconv/ext-diff | 被忽略或拒绝；无 helper 执行，无 metadata 写入、网络、越界读取 |
| 来源负向 | context 来自模型/report、跨 ticket/run/attempt 重放、修改 receipt digest | 权限/身份拒绝；旧 receipt 不通过 |
| 漂移负向 | prepare 后改代码或 index；query 期间替换身份锚点；timeout/overflow | check/final gate 拒绝；失败保留真实日志 |
| writer/ABA 正负向 | 两个受管会话 writer 竞争 epoch；锁内尝试 code/index/受管metadata A→B→A；调用结束后再写 | 受管 writer 在锁外等待，epoch 中没有写入；结束后修改导致下一重建拒旧 receipt；未接锁受管 writer 的测试必须失败并阻止交付 |
| 合法源仓维护 | 抽取前/中/后并发 gc/repack/prune/自动 maintenance，源 pack 路径替换 | 完整 OID 校验成功后正式 query 仅读独立 snapshot；缺失/损坏/截断抽取严格失败；不要求用户普通 Git 接内部锁 |
| assess 删除证据 | source evidence 指向 deleted baseline file，实际 excerpt/line/hash 正确；逐层移除 provider、改 excerpt/OID、删 snapshot blob | 真正 assess→check→final 成功；各负控严格失败，不改 assessment、不写成功 receipt；无 raw _git fallback |
| Agent 特殊检查实际闭环 | timestamp/shared-variant 至少一个真实触发场景，由模型调用 tool prepare/read/assess/check，逐项提供实际 source evidence | 特殊规则与当前源码/diff相符，真实每项 assessment 通过并 finish success；无自动NA；缺assess、非法check_id、错误phase、改payload重放、Reviewer assess全部拒绝 |
| baseline 稳定性 | prepare 默认 HEAD，重建只传 pinned OID；source HEAD 改为新 commit但旧 pinned object仍在 | declaration→OID 摘要相同，baseline 保持原 commit；改原声明/receipt/pinned 或 prune到不可抽取则严格失败 |
| IPC 负向 | 模型子进程枚举 FD、猜测 nonce/opcode、重放上一调用响应、截断帧、CP crash | 无 provider capability 泄漏，无常驻端口；本次 gate 失败，FD/thread/子进程/snapshot 全部清理 |
| attributes 正负向 | CODE `* text=auto`、scope外祖先attrs、缺失后indexfallback；非空metadata info/attrs、customdriver/-diff/filter/textconv、attrs漂移 | 安全text/eol场景实际trigger和hash正确；不支持配置明确拒绝；scope外/缺失/fallback输入均绑定，不能静默隐藏特殊规则 |
| cleanup信用 | nativequery cleanup失败；CP写success后wrapper reap失败；snapshot删除失败；写active后宿主重启 | 前者不发布success；后者保留真实历史但quarantine/active使taskstatus/ready/clear=1/admission/resume拒绝；只host recovery证明加fresh finalcheck能恢复 |
| 兼容性 | 普通非隔离本地 Git、旧 report、snapshot/nested/gitlink | 原合法本地行为不变；不支持的隔离形态显式拒绝，不能伪装 complete |

跨仓 SOURCE 授权已取得；先完成设计独立双审，再在 canonical native Skill main 的 52cb6b3 基线上做本次最小增量和针对性回归。主代理只读 `ls-remote` 8dfb2d 观察远端 main 为 52cb6b3；本任务只引用该独立 freshness 证据，不把 clone 视为远端证明。D 用户活跃 dirty 工作树不暂存、不覆盖。子仓候选只提交本次变更并推 main，不建分支、不回退上游；主仓随后将 gitlink 从固定 21566a5 更新到该实际新 commit，并更新 runtime manifest 的真实内容。

这必然是完整 Git commit 升级，不是“pin 只带批准文件”：21566a5→52cb6b3 的既有上游差异为主代理报告的 66 files / +8636 / -251，之后再加本次修复。提交前生成固定旧 pin→实际新 pin 的逐文件差异清单，逐项标明既有上游增量/本次修复、runtime/source/docs/tests、采用理由、合同/API/ledger/权限影响、对应验收；不能通过 manifest 排除或 hide 未审查变化后宣称整体兼容。若任一运行时增量尚未评估或其必要 CI 未通过，不推进主仓阶段验收；有冲突必须在 52cb main 后续兼容修复解决，不改历史回退。清单是后续 PLAN 实施必须产物，本设计只定协议不另写交付文件。

至少覆盖上游 special checks/assessment 新合同、旧 v1 只读兼容、actual current writer/schema/ledger/receipt gates、跨平台普通 legacy 路径、native Linux host-bound 正负权限、本次实际机器 worklist normal finish闭环；所有 upstream changed runtime 项的检查映射必须有证据。密钥扫描和子仓/manifest完整性、本次针对性回归、独立审查通过后依已授权顺序推 main 触发 GitHub CI，不在本机重复全量。所有结论绑定主仓 SHA + 新 Skill 整体 pin + workflow/job/platform/log/exit；阶段必需项全部通过才宣布 S2c normal 通过。失败保留、不取消或重跑隐藏。

## SPEC / QUALITY 自审与固定决策

SPEC：真实问题、复用点、双边 ABI、所有重建消费者、来源/权限、index/config 时间边界、兼容范围与正负 oracle 已明确。QUALITY：没有用脚本通过替代产品链路，没有 fake `.git`、allow_incomplete、shadow 代码、任意 Git executor，也没有未经授权实现源码。

架构选择已固定：每次 CP 私有有界 socketpair FD、五类 query provider、受管会话 writer 锁、必要 metadata 和查询 commit/tree/blob 闭包独立不可变 snapshot、持久 declaration→pinned OID 稳定摘要、host_git_context_v1 binding/receipt、包含 assess/deleted source evidence 的全部 final 消费者统一 wrapper，以及 main-only 真实整体 pin 升级治理。没有待实施任选的载体/对象/ABA/ledger方案。实现中发现现 native policy 无法表达 snapshot、对象抽取预算无法满足实际项目、合法受管 writer 无法接入锁时，应报告具体证据，不静默缩减保证。当前新 API 未实现，设计双审与实际 S2c 行为仍需候选证据。本任务只交付设计。

【架构级自检报告】

- 语法/编译：Markdown 结构可检查；本任务未修改源码，不适用编译通过声明。
- 依赖/调用链：已记录 producer、CP adapter、helper、Read/check 和 final gate；实施仍须重新扫描全部入口。
- 逻辑/边界：明确 code tree 与 metadata 对象分离、baseline 固定和 strict failure；新实现尚未验证。
- 异常处理：设计要求超时/截断/漂移/身份缺失拒绝；不宣称已有实现全覆盖。
- 关联模块：仅新增本设计；跨仓实现已获用户授权，尚待独立评审。
- 兼容安全：设计保留旧本地行为，受管隔离缺 context 失败；待负向权限 oracle 验证。
- 可运行性：设计文档可读；SOURCE 未实施，不报告 100% 运行通过。
