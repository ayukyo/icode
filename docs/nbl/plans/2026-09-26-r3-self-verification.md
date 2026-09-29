# R3 自验证与有界修复

- 日期：2026-09-27
- **CI #354 双架构原生验收（commit `f709296`）：**Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36584911096/job/109462523692) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36584911096/job/109462523937) 各运行 25 项并全部通过，其中新增 `test_held_directory_restart_list_detects_add_remove_and_same_name_replacement` 成功。该用例只在已知小型临时目录中以同一目录 HANDLE 重启枚举，对比两次完整已知 fixture 名称集合、对象 FileId；结果只证明对应 runner 上的受控序列可观测，不是分页/递归/任意并发或 point-in-time 快照。CI #354 整体失败仅因 R2 AppContainer x64/ARM64 诊断 job 均为 `18/20`：`process_exit_zero`、`network_isolation_denied` 未通过，live/control 均 Winsock `10060`，故网络拒绝归因仍 inconclusive。Windows `worktree_git_tree_oid()` 仍 `unsupported_platform`。
- **R3 test-only 分页枚举候选（2026-09-29，本机纯测试通过、Windows native 待验）：**新增 `collect_extd_directory_entries()`，用 restart 信息类启动、续页类继续；限制 buffer/page/entry 数，拒绝未知 WinError、重复名、非零空解析页与无进展。当前候选接受明确 `ERROR_NO_MORE_FILES`，或已有条目后精确全零的成功 buffer。CI #355 双架构用例均在旧 no-progress 门失败，确切终止 buffer 形态待新 `page_signals` 断言确认。native fixture 以 512-byte buffers 枚举 96 个文件、重启复扫并验证空目录。Microsoft [`GetFileInformationByHandleEx`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex) / [`FILE_INFO_BY_HANDLE_CLASS`](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ne-minwinbase-file_info_by_handle_class) 支持 restart 与续页语义，但没有规定精确 EOF 形态；该零缓冲规则是待 x64/ARM64 验证的窄实验假设。即使 native 通过，也只证实受控 NTFS runner 的有界枚举，不构成并发稳定或快照保证。**暂缓**接入生产快照、递归 walker 和 tree OID。
- **CI #355 原生失败与修正边界（2026-09-29）：**Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36587999696/job/109473369837) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36587999696/job/109473369967) 各运行 30 项；唯有新分页用例在 `directory_enumeration_no_progress` 失败。此结果还不能区分“成功但全零的 EOF buffer”与“非零但仅含过滤项的响应”，故不把空页宽松计作终止。本地候选仅接受精确零填充成功页，native test 已加有界 `page_signals` 断言记录并验证终止形态；非零解析空页仍失败关闭。须新 x64/ARM64 CI 原生通过后才关闭此测试子门。其余 R3 比较逻辑未改变，仍不做生产快照/tree OID，也不对 CI #355 整体 failure 给 R2 网络门计成功。
- CI #353（commit `9ffeed4`）的 Windows x64 job `109451391664` 与 ARM64 job `109451391948` 各通过既有 23 项目录/相对打开用例，证明本轮代码之前的原生基线仍绿；本机随后新增的两次观察比较和新增 native mutation 用例不在该 commit，仍待下一轮双架构 CI。主 [CI #353](https://github.com/ayukyo/icode/actions/runs/36581740106) 因 AppContainer R2 硬门失败，不影响 R3 的上述 job 单独结论；官网 [#248](https://github.com/ayukyo/icode/actions/runs/36581740118) 成功。
- **CI #352 Windows namespace share-mode matrix（2026-09-29）：**x64 [job](https://github.com/ayukyo/icode/actions/runs/36579957568/job/109445204521) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36579957568/job/109445204558) 均在 NTFS 跑过 23 项。无句柄基线全允许；父目录仅 `FILE_SHARE_READ` 时 create/delete 与 junction remove/create 仍允许，file rename/replace 收到 `ERROR_SHARING_VIOLATION`；`READ|WRITE` 与 ALL share mask 下本矩阵操作全允许。仅记录受测 runner 上的结果，不推断 rename/replace 的普遍根因，尤其不声称父目录句柄冻结子树。**采纳**该窄实验作为目录行为回归；**暂缓**生产 walker、Windows tree OID 与目录锁承诺。下一片评估 test-only 持柄递归身份/内容协议及可检测漂移；任何普通双遍遍历都不能宣称捕获任意临时 ABA 或 point-in-time tree。Windows `worktree_git_tree_oid()` 保持 `unsupported_platform`，直到 tree 序列化、SHA-1/SHA-256、用户 index/ODB 不变及原生漂移门另行成立。
- **R3 同目录句柄双观察漂移分类（本机切片，2026-09-29；Windows CI 待验）：**为 `tests/windows_tree_snapshot_probe.py` 增加 test-only comparator，仅比较两份 `FILE_ID_EXTD_DIR_INFO` observation 中的精确名称、属性、reparse 标记（仅该字段有效时）和 128-bit FileId；拒绝异常类型、重复名称与无效 FileId。原生测试会在小型临时 NTFS 目录、同一 held directory HANDLE 上重读 restart listing，分别观察新增、删除及保持名称集合不变的两个普通文件身份互换。单测先 RED/GREEN，目标模块 25 项（本机 20 通过、5 项 Windows-native 跳过）。Microsoft [`FILE_INFO_BY_HANDLE_CLASS`](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ne-minwinbase-file_info_by_handle_class) 区分 restart 与 continuation；本片刻意只验证已知小 fixture，不实现多 buffer/递归扫描。**采纳**为 test-only 两次观察漂移分类；**暂缓**生产 `snapshot_workspace` 改造和 Windows tree OID。`same_observation` 只说明两份输入记录字段一致，不能证明枚举完整、文件内容不变或扫描期间无 transient ABA；R3 与 readiness 不提前开放。研究来源、Codex/OpenCode 借鉴边界见[持续竞品对照](../../agent-landscape-live.md)。
- CI #350 的 R3 单文件探针在 Windows x64 job `109425810185` 与 ARM64 job `109425810483` 继续成功；仍仅是 directory-record/relative-open/bounded-reader/share-mode 单文件合同。它不证明递归 namespace 稳定或 Git tree OID。下一测试片继续 test-only 比较不同 parent-handle share mask 下的 create/delete/rename/replace/junction-replace 变化；在并发 namespace fail-closed 证据、SHA-1/SHA-256 对照及 index/ODB 不变条件成立前，Windows `worktree_git_tree_oid()` 保持 `unsupported_platform`。
- 最新增量（2026-09-29，CI #349）：test-only Windows bounded-reader identity/read suite 在 x64 [job](https://github.com/ayukyo/icode/actions/runs/36570938004/job/109414476480) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36570938004/job/109414476544) 各通过 21 项；只证明单文件相对打开、身份绑定、限额与 share-mode 用例，不证明递归 walker/整树一致性。另已按固定 Codex [`fbc1698`](https://github.com/openai/codex/blob/fbc169827e9789f9e7ba2ed97c15e2021c3312bb/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs)、OpenCode [`a42f393`](https://github.com/anomalyco/opencode/blob/a42f393c850bec0c0f395fb91bf19b1ee8b31666/packages/opencode/src/snapshot/index.ts) 与 Microsoft 文件身份/句柄文档完成定向研究：采纳 no-reparse handle-relative 原语和隔离 index 思路；暂缓生产 Windows 快照及 `worktree_git_tree_oid()`，下一片仅做 test-only 目录 namespace 并发变化矩阵（create/delete/rename/replace/reparse），以实测建立何种变化能 fail-closed。目录句柄不是树事务锁，FileId 不是原子时点证明；R3 gate 不变。研究来源及许可/成本取舍见[持续竞品对照](../../agent-landscape-live.md)。
- 状态（2026-09-29 最新）：R3 自验证/有界修复核心、独立只读 Reviewer、受控 MiniMax-M3 真模型修复闭环，以及一次**强制触发的真实短上下文终结器**均有证据。POSIX 仓库根的稳定 raw Git tree OID 与可选结果 commit/tree 校验已进入 `VerificationEvidence`、证据指纹及持久化回执；Reviewer 输入绑定该 OID，并在审查后重算工作树 tree，漂移即失败关闭。对象摘要重算、`--result-commit` 绑定及上述回归已有 [CI #263](https://github.com/ayukyo/icode/actions/runs/36361956421) / [CI #267](https://github.com/ayukyo/icode/actions/runs/36365615681) 验证。`icode task --receipt-out` 可显式持久化失败或成功回执并导入证据包；空测试集稳定判失败，内部 unittest 用 `-B` 防止 verifier 写入 pyc 污染受测 tree。Linux Bubblewrap 工作流 Reviewer 命令边界与 macOS Seatbelt 同类拒读/只读负例已通过；Windows、容器和策略化 Reviewer 尚未开放。工作区快照对 POSIX/Windows 未知特殊文件类型失败关闭。R2 隔离能力仍未达到跨平台开放门槛。受测 tree 投影仅支持 POSIX 仓库根，最多 250,000 项、128 层和 256 MiB 文件字节；Python SHA-1 OID 不作签名或抗碰撞安全证明，commit 对象读取上限 1 MiB；子模块/嵌套 `.git`、Windows、attributes clean 转换、ACL/xattr、宿主环境与执行轨迹不在其证明范围。真模型终结器证据仅覆盖合成靶场中的强制 fallback，不代表自然触发率或完整 Reviewer 能力。
- 最新增量（2026-09-29）：Reviewer 实际读工具现在也校验可选精确文件名单；独立 Reviewer 将其 `changed_files` 传入 `ToolContext`，未授权文件及目录级 grep 在 handler 层失败关闭。该机制是应用层纵深防御，不替代 Guard 或 OS 沙箱，不改变跨平台 ready 状态。提交 `1468dd1` 的 [CI #312](https://github.com/ayukyo/icode/actions/runs/36479949142) 已在 Windows x64/ARM64 通过真实硬链接与白名单专项步骤；工作流 [CI #313](https://github.com/ayukyo/icode/actions/runs/36481777383) 随后在 macOS Intel/Apple Silicon 通过同组步骤，Python 3.11/3.12 全量测试及守卫成功；官网 [#217](https://github.com/ayukyo/icode/actions/runs/36481777807) 成功。
- 最新增量（2026-09-29，CI #342 双架构通过）：test-only `tests/windows_tree_snapshot_probe.py` 解析 bounded `FILE_ID_EXTD_DIR_INFO` 目录项，并从 handle-relative `NtCreateFile` 后查询 `FILE_ID_INFO`；native 用例比较 volume serial + 128-bit ID，再删除旧子项、把已枚举的另一普通文件移到旧名字，验证 opened ID 与该源对象一致且不同于 stale ID。拒绝全零与全 `0xFF` FileId 哨兵；空目录零缓冲返回空集。TDD RED/GREEN、目标模块 18 项（本机 15 pass/3 Windows-native skip）；Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36545492409/job/109330767269) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36545492409/job/109330767667) 均原生运行并通过 18 项；compileall、diff-check、完整 preflight 三门和独立审查通过。CI #342 总体只因既有 R2 AppContainer 网络门双架构失败而 failure，官网 #238 success。该原语没有接入生产快照、没有签发 tree OID；目录句柄不提供原子命名空间快照，完整 ABA/并发树漂移仍未解决，因此 `worktree_git_tree_oid()` 继续在 Windows 返回 `unsupported_platform`，R3/R2 readiness 不变。详见[持续竞品对照](../../agent-landscape-live.md)。
- 最新增量（2026-09-29，CI #344 x64/ARM64 原生通过）：将替换用例扩展为保留对象 A，先移走名字并要求相对打开返回精确 `STATUS_OBJECT_NAME_NOT_FOUND` (`0xC0000034`)，再把预枚举对象 B 移到原名并核对其身份，最后恢复 A 并核对身份回到原值。Microsoft [NTSTATUS 表](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55)定义该状态码。提交 [`80e6b07`](https://github.com/ayukyo/icode/commit/80e6b0779abe053c765137b7d65e21558eef5b23) 的 Windows [x64](https://github.com/ayukyo/icode/actions/runs/36549176322/job/109342834763) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36549176322/job/109342834657) native jobs 均成功；目标模块 18 项，本机 15 pass/3 因非 Windows 跳过。完整 preflight 三门、独立审查通过。精确错误码只在本次 NTFS runner 上确认；不外推到网络文件系统或其它文件系统。该 A→缺失→B→A 控制序列仍不是任意并发攻击/原子快照证明；仅为 test-only 原语，Windows `worktree_git_tree_oid()` 仍 `unsupported_platform`，生产快照与 Reviewer 不变。
- 最新增量（2026-09-29，本机切片，Windows 原生 CI 待验）：新增 test-only `read_relative_file_if_identity_matches()`，只接受与目录枚举完全一致的单一子项名；以已持有父目录句柄和 no-reparse 相对打开文件，只在比较枚举与打开对象的卷序列号 + 完整 128-bit FileId、普通文件属性通过后读取，并在同一 handle 上读后复核；读上限 8 MiB、分块 64 KiB、超限用一个 sentinel 字节拒绝，所有路径均关闭句柄。native 用例覆盖空文件、精确限额、恰好多 1 字节、跨分块、超限清理、已有 writer 阻止读取、name 缺失、A→B 替换身份不匹配，以及重新枚举后按 B 身份读取。Microsoft [同步 EOF 契约](https://learn.microsoft.com/en-us/windows/win32/fileio/testing-for-the-end-of-a-file)说明同步 `ReadFile(..., lpOverlapped=NULL)` 到 EOF 成功返回 0 字节；本实现使用同步句柄，因此没有为误判引入额外文件长度查询。当前 Linux 聚焦模块 21 项（18 pass、3 native skip）、`compileall` 与 `git diff --check` 通过；Windows x64/ARM64 原生结果待记录。
- **竞品取舍与边界：**沿用 Codex 固定源码 [`fbc1698`](https://github.com/openai/codex/blob/fbc169827e9789f9e7ba2ed97c15e2021c3312bb/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs) 的句柄相对打开/no-reparse/句柄生命周期作为机制参照；该文件不是枚举 FileId 绑定内容读取、递归一致性快照或 tree OID 实现。ICODE 仅选择性采纳这一窄边界用于 test-only 探针，不复制上游代码、不增加 runtime 依赖；Codex 固定提交许可证为 Apache-2.0。收益是让 stale 名称不能把另一对象内容交给探针；代价是 Windows native API/文件系统差异要求双架构原生验证，不可用 FileId 必须失败关闭。此前已通过 CI 的用例覆盖 identity mismatch 拒绝、读取上限与已有 writer 阻止打开；本轮再补“读取原语零调用”和“实际 reader handle 活跃时写/删 access 被拒”两项，见下两条。单文件 FileId 不证明 hardlink 唯一或不连到工作区外；API 支持范围仅以本次仓库 CI runner/文件系统为准，不外推旧 Windows 或其它文件系统。无生产调用方或用户行为变化；仍不证明并发目录项稳定、hardlink 边界、ID 不重用或 point-in-time 整树快照，Windows `worktree_git_tree_oid()` 继续 `unsupported_platform`，R2/R3 ready 与自动模式不变。详见[持续竞品对照](../../agent-landscape-live.md)。
- **审查缺口补测（2026-09-29）：**独立只读复核确认原生 reader 的身份验证先于 `_read_open_file_contents()`，但此前没有实测断言零读取调用；亦没有在该 reader 的真实 `NtCreateFile` handle 仍打开时尝试写与 DELETE access。本轮只扩展 test-only native 用例：FileId mismatch 负例 spy 读取原语并要求零调用；成功读路径在原语入口对同一临时文件尝试 `GENERIC_WRITE` 与 `DELETE` 的 `CreateFileW`，均要求 `ERROR_SHARING_VIOLATION` 后再继续真实读取。微软 [CreateFile 共享规则](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilea) 与 [`DeleteFileW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-deletefilew) 支持该边界；没有触碰 production 或 runtime。当前聚焦模块 21 项（18 pass/3 Windows native skip），compileall 和 diff-check 通过；新增断言须待后续 Windows x64/ARM64 原生 job 再验证。通过后也只证明对应 CI runner 文件系统上的单文件读句柄共享语义，不代表硬链接、目录快照、旧 Windows 或其它文件系统保证。
- **CI #346 复验（提交 `1fd7251`）：**R3 原有 Windows relative-open/read probe 在 x64 [job](https://github.com/ayukyo/icode/actions/runs/36556408411/job/109366509523) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36556408411/job/109366509728) 原生通过；官网 [#241](https://github.com/ayukyo/icode/actions/runs/36556408477) 成功。该轮必需 AppContainer x64/ARM64 jobs 的构建成功，探针运行到 `native_stage=5`、均 `18/20`；只有 `process_exit_zero` 与 `network_isolation_denied` 失败。宿主 RFC1918 listener 控制通过，AppContainer socket 未连上（Winsock `10060`），NetIso 为 `INTERNET_CLIENT=2`；WFP observer 已订阅但没有 callback/drop evidence (`evidence_unavailable`)。匿名 job log REST API 为 403；已登录 CI 页面显示两边还出现通用路径语法消息，但继续完成 probe，不能据此认定它是失败原因。该状态与 #343/#344 相同，不暴露新根因；不得将 timeout 记为拒绝或归因 WFP。R2 gate、自动模式及 R3 Windows tree OID 状态不变。
- 依据：[产品总架构](../../icode-agent-product-architecture.md) §13.7；[R2 跨平台隔离设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §12.2

## 2026-09-26 UTC 当前联动状态

- **测试计数补记：**首轮聚焦批次为 126 项；随后纳入离线链路快照基准断言并加严回归，最新聚焦批次为 133 项通过；全量 preflight 为 861 项通过、23 项平台跳过。路线图与持续对照已按最新计数刷新。

- R3 真模型修复闭环已在受控 MiniMax-M3 靶场完成；本地 `run_task` 将真实 Git 基线 SHA 与初始/受测工作区指纹纳入回执，快照进一步区分文件类型与 POSIX 可执行位。133 项聚焦测试和全量 preflight（861 项测试、23 skipped）通过。Reviewer 跨平台只读命令边界、终结器真模型路径及结果 commit/tree 匹配仍未验收。
- R2 常规 [CI #212](https://github.com/ayukyo/icode/actions/runs/36252023822) 成功，但 Windows 标准用户探针在 push 运行中跳过；Linux/macOS conformance 仍 `5/10`、`critical_passed=false`、`ready=false`。手动 [CI #213](https://github.com/ayukyo/icode/actions/runs/36252440492) 同 SHA x64/ARM64 标准用户管道均在子进程 `CreateFileW` 返回 `access_denied`，自动模式保持关闭。
- R2.4 Linux x86_64 Git broker 有精确 helper 白名单和污染环境的已安装 wheel 负例；不是跨平台 broker，尚未接入模型工具入口。#212 常规 CI 通过不验证手动 Windows pipe、R2 全部 10 项隔离门或 R3 Reviewer OS 边界。

## 2026-09-27 UTC：稳定受测 Git tree 投影 OID

- **实现边界：**`run_task` 在每轮测试前后只读计算 POSIX 仓库根的 Git 原始文件树投影，并在前后 tree OID 与完整工作区指纹一致时，才把 `tested_git_tree_oid` / `tested_git_tree_status=stable` 写入验证证据、指纹、回执和 Reviewer 输入；测试修改工作区或 Reviewer 后发生漂移都会撤销/否决证据。非 Git 靶场继续留空；没有调用 Git、`git add`、用户 index、attributes、filter 或仓库 helper。
- **算法与限制：**以 Git 对象序列化规则计算 SHA-1/SHA-256 tree，路径排序、常规文件模式、符号链接目标及目录均有 Git CLI 交叉向量；不跟随链接。扫描上限为 250,000 项、128 层、256 MiB 普通文件内容。未知特殊文件、嵌套 `.git`/子模块、竞态、超限、非 POSIX 或非仓库根均不给 OID。所有 ignored/未跟踪文件纳入原始投影，不应用 clean filter；因而这不是等价于 Git index/tree 的“已提交内容”证明，投影不匹配时 fail-closed。
- **密码学边界：**Python 标准库 SHA-1 OID 与 Git 对象 ID 兼容，但没有复用 Git 的碰撞检测 SHA-1，因此 OID 不用作签名或抗碰撞安全根。Git 正在迁移/加固 SHA-1 的官方说明见 [hash-function transition](https://git-scm.com/docs/hash-function-transition/2.48.0) 与 [Git 2.48 highlights](https://github.blog/open-source/git/highlights-from-git-2-48/)；此处仅将 OID 用作本地相等性筛查，后续结果 commit 验证需保持这一风险边界，并结合已绑定证据，不得升级为安全认证声明。
- **验证：**R3 聚焦回归 43 项通过；全量 `scripts/preflight.py` 三项保护门通过，独立全量 unittest 为 871 项通过、23 项平台跳过。专用临时 Git 仓库覆盖 SHA-1/SHA-256、staged/unstaged、untracked/ignored、模式、类型、链接、特殊文件与属性 helper 不执行；还核验用户 index 字节及时间戳未改变、测试期间变化撤销 OID。
- **线上隔离状态：**push CI [#214](https://github.com/ayukyo/icode/actions/runs/36254293856) 总体成功；其中 Linux/macOS 原生隔离均 `5/10`、`critical_passed=false`、`ready=false`，Windows 标准用户管道 job 跳过。不得把常规 CI 成功写成 R2 通过；自动模式仍关闭。
- **结果 commit tree 比对（2026-09-27）：**新增只读 Git 对象读取：只接收完整 storage-format commit OID，禁用 replace refs 和 partial-clone lazy fetch，校验对象类型/大小/tree header 与 tree 对象，不读写用户 index；明确不接受 SHA-256 仓库的兼容格式 OID。`run_task(..., result_commit_sha=...)` 与 `icode task --result-commit <完整 SHA>` 可显式绑定；tree 不匹配或结果对象不可用时 `TaskReport.ok` 失败关闭，匹配结果进入 receipt/fingerprint。测试前后 HEAD SHA 分别记录；相同 tree 的非边界 HEAD commit 只标注“tree matched / not observed as HEAD”，不得声称 commit 当时存在。Git author/committer dates 不用于时序判断。
- **当时的后续验收清单：**此 tree-binding 切片结束时，CLI 仅在标准输出显示比对结论，task 持久化回执尚未实现；partial clone 缺失对象的无网络读取与对象损坏路径也仍待专项验证。task 回执后续状态见本计划的“持久化验证回执”记录。R2 原生隔离红门、跨平台只读 Reviewer 命令边界和 Reviewer 短上下文终结器真模型路径证据仍需继续解决，不能据单一切片声称 R2/R3 完成。

## 2026-09-26 UTC：CI #202 回执过滤根因与修正

- **原生复验：**手动 [CI #202](https://github.com/ayukyo/icode/actions/runs/36242053362) 的 Windows x64/ARM64 标准用户步骤都仍输出通用 `RuntimeError`；此前的新增 DACL/token 诊断标签没有泄漏，但也被外层错误过滤器隐藏。此次运行其他已完成的 Windows Job、wheel、workspace 和 native-probe 作业保持其各自结果；它们不把 R2 变为通过。
- **根因：**子进程报告 parser 返回由 `+` 连接的固定安全标签，父端再包成 `standard_user_restricted_child_failed:<detail>`；最外层只接受 `[a-z_]+` 阶段名，因此将合法标签折叠成异常类型。并且旧的 `"winerror=" in safe` 快速通道不够严格，可能放行未按格式校验的异常正文。
- **修正与回归：**提取纯函数 `_safe_standard_user_probe_error()`，只允许精确的已知状态、完整小写 `stage:winerror=N`、或总长不超 200 字符且满足固定语法的受限子进程标签。增加正例验证 child-token/DACL 标签完整保留，负例验证 Windows 路径与秘密文本仍折叠为 `RuntimeError`。新测试先 RED，修正后 `test_windows_standard_user_token_probe` 31 项通过；`compileall`、`git diff --check` 与全量 `scripts/preflight.py` 通过。
- **边界：**这修正回执可见性并收紧错误输出，不改变权限、不宣称 `AccessCheck` 等同 `CreateFileW`，也不代表管道连接成功。需以新提交重新跑双架构 `workflow_dispatch`，读取 DACL、ACE、child primary-token、logon SID 与 AccessCheck 标签；R2 Windows 自动模式继续关闭，R3 Git SHA 与 workflow Reviewer OS 边界仍待验收。

## 2026-09-26 UTC：CI #204 AccessCheck 状态与安全描述符修正

- **原生证据：**手动 [CI #204](https://github.com/ayukyo/icode/actions/runs/36242591553) 的 Windows x64/ARM64 都报告相同标签：`client_open_access_denied+dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_unavailable`。因此已看到真实 DACL 有预期 ACE，child primary token 的 logon SID enabled 且 token 非 restricted；真实 `CreateFileW` 仍拒绝。Linux/macOS `5/10`、`critical_passed=false`、`ready=false`，不能据此通过 R2。
- **API 合同与推断：**Microsoft [`AccessCheck`](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck) 说明其输入需为有效安全描述符，缺少 owner/group SID 时会以 `ERROR_INVALID_SECURITY_DESCR` 失败；[`GetSecurityInfo`](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo) 仅返回被 `SecurityInfo` flags 请求的组件。本地原代码只请求 `DACL_SECURITY_INFORMATION`，与 `access_unavailable` 一致；但 CI 没保留 API 错误码，所以这仍是待验证根因，不是已确认结论。
- **TDD 修正：**先增加安全信息 mask RED 测试，再令 `GetSecurityInfo` 同时请求 `OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION`；DACL 读取/ACE 匹配逻辑、访问掩码及 ACL 均不改变。`test_windows_standard_user_token_probe` 32 项通过；下一次双架构原生 probe 必须验证 `access_allow` 或 `access_deny`，且不把 AccessCheck 单独当作 CreateFile 实际结果。
- **未关闭边界：**管道 `CreateFileW` access denied、标准用户 runner probe、Windows 文件/网络隔离与自动模式仍未通过/开放。即便 AccessCheck 返回 allow，也要继续分析 AccessCheck 与内核 CreateFile 结果差异，不能扩大权限试探。

## 2026-09-26 UTC：CI #206 DACL 放行但管道连接仍拒绝

- **独立原生证据：**手动 [CI #206](https://github.com/ayukyo/icode/actions/runs/36243032179) 的 Windows x64 与 ARM64 都报告 `dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_allow`；同一目标子进程的真实 `CreateFileW` 仍 `access_denied`。Linux/macOS 原生 conformance 仍为 `passed=5/10`、`critical_passed=false`、`ready=false`。因此只确认 DACL `AccessCheck` 不是充分解释，不能将失败归咎于完整性控制。
- **只读诊断补充：**根据并行微软 API 核对，将下一轮诊断收窄到实际 pipe 对象的 `LABEL_SECURITY_INFORMATION` 中 `SYSTEM_MANDATORY_LABEL_ACE`/`NO_WRITE_UP` bit，以及真实目标 child token 的 `TokenIntegrityLevel` 和 `TokenMandatoryPolicy`；只输出固定标签，不输出 SID/RID，不回退到父 token。Label-only 查询不读取审计 SACL；token 查询只需 `TOKEN_QUERY`。没有权限变更、重试 open 或改变探针判定。
- **微软 API 依据与推断边界：**[`GetSecurityInfo`](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo) 对管道 handle 可按 [`SECURITY_INFORMATION`](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-information) 请求 `LABEL_SECURITY_INFORMATION`；微软分别说明完整 SACL 查询与 label-only 查询的权限边界。`GetTokenInformation` 的 [`TokenIntegrityLevel`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_mandatory_label) 与 [`TokenMandatoryPolicy`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_mandatory_policy) 均通过 `TOKEN_QUERY` 读取；[Mandatory Integrity Control](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control) 在 DACL 之外检查对象标签与 mandatory policy，[SYSTEM_MANDATORY_LABEL_ACE](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_mandatory_label_ace) 定义 `NO_WRITE_UP`。对象 label + 有效 client token + 读写请求三者匹配才能形成强 MIC 候选，仍不能宣称唯一根因。
- **本机验证：**新增固定 RID/authority 分类、mandatory-label ACE 结构、缺失 label 与查询失败区分、token policy bit、白名单及较长但有界回执测试；Windows 探针单测 37 项通过。该环境不能原生执行 Windows API；需在后续 x64/ARM64 CI 确认新标签，且结果仍不能替代真实 `CreateFileW` 结论。
- **未关闭边界：**`CreateFileW` 拒绝、Windows 文件/网络隔离、runner 自动模式、Linux/macOS 5/10 门槛以及 R3 SHA 锚定和跨平台 workflow Reviewer 均未关闭。

## 2026-09-26 UTC：CI #208 完整性诊断未支持 MIC 假设

- **双架构原生证据：**手动 [CI #208](https://github.com/ayukyo/icode/actions/runs/36244885627) 的 Windows x64 与 ARM64 均报告 `dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_allow+client_il_medium+pipe_il_absent+pipe_nwu_unavailable+token_nwu_yes`；两架构真实 `CreateFileW` 都仍 `access_denied`。Linux/macOS 原生 conformance 继续 `passed=5/10`、`critical_passed=false`、`ready=false`。
- **有限推断：**本探针测量的是失败目标进程的 primary token（`token_child_process`），其 IL 为 medium，`NO_WRITE_UP` 策略启用；实际 pipe 上未发现显式 mandatory-label ACE。微软 [MIC 文档](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control)规定无标签对象按 medium 处理，因此当前记录不符合“低 IL 客户端写高 IL 对象”的典型 MIC 解释。它不能排除线程 impersonation、对象/令牌快照差异或其他内核路径条件，也不能单凭回执确定根因。
- **下一只读观察：**在调用 `CreateFileW` 的同一 runner 线程记录 [`OpenThreadToken`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openthreadtoken) 有无 token；如存在，仅以该 token 记录固定类别 IL、mandatory policy 和相同 DACL `AccessCheck` 结果。Microsoft 说明通常用请求线程的 primary token，但 impersonation 时改用线程 token（[How AccessCheck Works](https://learn.microsoft.com/en-us/windows/win32/secauthz/how-dacls-control-access-to-an-object)）；目标进程退出后的父进程快照不能代替这一调用点观察。保留真实 `CreateFileW` 结果及错误阶段；不扩大 desired access、不更改 DACL/SACL、不重试 production open。named-pipe 文档把 `FILE_CREATE_PIPE_INSTANCE` 的额外检查限定在 server-side `CreateNamedPipe` 打开现有实例；客户端 `CreateFile` 有自己的访问检查（[Named Pipe Security and Access Rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)），不能误把该服务器端条件套到客户端。
- **本地诊断切片（待原生 CI）：**已在等待实例后、实际 `CreateFileW` 前通过私有 CI 观察入口采样当前线程；公开 pipe-open API 没有接收任意回调，内部实现仅在标准用户探针使用，具体观察闭包只查询、不调用任何 token mutation API。`OpenThreadToken(TOKEN_QUERY, OpenAsSelf=TRUE)` 仅在 `ERROR_NO_TOKEN` 时读取进程 primary token，否则标记 unavailable，不把查询失败伪装成 primary token。固定回执包括 token 来源、归一化 IL、受限状态、logon SID 启用状态，以及 `TOKEN_MANDATORY_POLICY_NO_WRITE_UP`/`NEW_PROCESS_MIN` 两位；pipe open 失败时追加该调用的 Win32 错误码。观察失败不会改变原 open，客户端 desired access、share、creation disposition、flags 和 ACL/SACL 保持原值。依据微软的 [OpenThreadToken](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openthreadtoken) 与 [`TOKEN_MANDATORY_POLICY`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_mandatory_policy) 文档；不复制上游实现或代码。诊断 API 会拉长 `WaitNamedPipeW` 成功到 `CreateFileW` 之间的时间窗；微软也说明等待后实例状态仍可能变化，所以原生复验需确认失败仍可复现，不能将单次标签当作拒绝根因。Linux 上两份定向单测共 55 项通过，但不等于 Windows API 实测；提交后须用 x64/ARM64 workflow_dispatch 验证标签长度、双架构回执及实际失败阶段。
- **研究取舍：采纳该观测机制，暂缓任何权限/ACL 调整。**现有 token/DACL 解析器可复用，收益是把实际线程 token 与退出后的 primary-token 快照分开；代价是多次 `TOKEN_QUERY` 调用会增加 open 窗口延迟，且 `ERROR_NO_TOKEN` 回退语义仍待目标 Windows 原生确认。微软列出的 `OpenThreadToken` 最低客户端版本为 Windows XP；使用标准系统 API，不引入依赖或复制上游代码，因此无第三方许可负担。验收条件为 x64/ARM64 报告均有合法固定标签/错误码、原 `CreateFileW` 请求参数不变、失败阶段仍可复现；诊断本身不作为根因或 R2 readiness 证据。
- **边界：**x64/ARM64 均重现拒绝，Windows 自动模式保持关闭；Linux/macOS 仍 5/10；R2 Git broker 接入与 R3 Git SHA 锚定、workflow Reviewer 跨平台只读边界仍待验收。

## 2026-09-26 UTC：CI #210 同线程令牌复验

- **双架构原生结果：**手动 [CI #210 x64](https://github.com/ayukyo/icode/actions/runs/36247565458/job/108419708823) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36247565458/job/108419708651) 都在标准用户 restricted-token probe 失败；固定回执包含 `client_open_access_denied+token_process+il_medium+restricted_no+logon_enabled+nwu_yes+npm_yes+dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_allow+client_il_medium+pipe_il_absent+pipe_nwu_unavailable+token_nwu_yes:winerror=5`。其他 Python、workspace、Linux/macOS native、Windows Job/wheel 与 presentation 作业按其自身结果通过；不能替代失败的 Windows pipe gate。Linux/macOS native score 仍 `5/10`、`critical_passed=false`、`ready=false`。
- **结论边界：**`token_process` 表明该次同线程采样按严格无 impersonation-token 分支使用目标子进程的 primary token；这降低了“线程模拟令牌不同”的解释可能，但不会把用户态 `AccessCheck=allow` 变成内核 `CreateFileW` 的通过，也不能排除观察窗口/pipe 实例竞争或其他访问检查差异。实际错误为 Win32 5。没有改 DACL/SACL、token、desired access 或 CreateFile flags；Windows 自动模式仍关闭。
- **研究取舍：**并行只读核对 Codex runner 的命名管道 DACL/PID 验证与 Microsoft `CreateFileW`/`WaitNamedPipeW` 文档，采纳“必须检查客户端真实请求权限、创建端 DACL 与 client handle 打开结果分别验证”的方法；将等待成功与打开之间的实例变化保留为待实验风险，不据此归因。暂缓任何 ACL 放宽、提权或安全描述符改动；下一片继续只读/可控的时序与调用参数证据采集。

## 目标与范围

从「能修改」升级到「能根据真实失败证据验证和修复」：

```text
修改 → 静态诊断 → 编译 → 单元测试 → 失败分类 → 有界修复 → 回归 → 独立 Reviewer
```

R3 核心能力（本切片）：

1. **失败分类**（`src/icode/self_verify.py::classify_failure`）
   把命令 / 测试 / 契约回执的失败分成六类：
   `environment` / `code` / `test` / `contract` / `model_capability` / `side_effect_unknown`。
   分类依据是可见证据（退出码、输出模式、错误类型、是否产物缺失）；
   无法归类时如实归入 `side_effect_unknown`（fail-safe）。

2. **证据绑定**（`VerificationEvidence` / `evidence_fingerprint`）
   每次验证绑定到 step、attempt、命令摘要、退出码、环境指纹、产物哈希、
   输出摘要与捕获时间。没有绑定的结果不能被当成「新证据」，
   也就不能支撑一次新的修复；指纹不包含输出正文或敏感参数。

3. **有界修复决策**（`VerificationLedger::decide_repair`）
   只有出现**新的失败证据**才允许重试 / 修复；相同指纹的重复失败在
   有界次数内被终止，避免「没有新证据就反复碰运气」；
   副作用状态不明一律按 fail-safe 拒绝自动重试（`human`）。

4. **runner 补救回合证据门**（`src/icode/runner.py::run_contract_step`）
   进入补救回合前先给「产物缺失」分类并绑定证据，`decide_repair` 返回非
   `allow` 时跳过并如实警告，不再无条件重试。

5. **任务级验证证据绑定**（`src/icode/runner.py::run_task`）
   独立跑 `python -m unittest` 后把退出码、输出摘要、环境指纹、改动文件哈希
   与失败分类绑定成一条 `VerificationEvidence` 挂到 `TaskReport.verification`；
   模型自述不算证据。

6. **证据回执序列化**（`VerificationEvidence.to_receipt`）
   可把一条验证证据序列化成 `verifications.json` 回执（含指纹、环境指纹、
   产物哈希与失败分类，不含输出正文/敏感参数）；`build_evidence_pack` 直接
   接受 `VerificationEvidence` 并序列化进证据包。

7. **独立 Reviewer 只读上下文**（`src/icode/reviewer.py`）
   `reviewer_guard` 构造无任何写授权的审查上下文，`verify_read_only` 用真实
   Guard 判定锁死；`IndependentReviewer.review` 针对改动文件与验证证据产出
   带严重级别、类别、文件/行号与证据指纹引用的结构化发现，且不能修改被审对象
   （符号链接被审对象直接拒绝）。`run_task` 使用独立模型对话执行语义审查，工具
   运行时通过 `Guard.allowed_read_files` 精确限制为本次改动文件，仅开放 `read_file`
   与只读上下文专用 `submit_review`；后者以 JSON Schema 承载结构化结果，局部校验
   失败最多反馈纠正一次；未经结构化工具提交或超过回合/纠正上限均失败关闭。需完整读取所有改动文件，finding 绑定验证证据，审查结束重核
   diff 指纹。任何越权、无效响应、文件快照漂移或 Reviewer 错误均失败关闭。

8. **回归证据绑定到具体 diff**（`workspace_snapshot.diff_fingerprint`）
   把一次改动（相对基线）绑定成确定性指纹：只依赖改动前后每条路径的 sha256，
   增删改状态区分、同结果不同基线指纹不同。`run_task` 的独立测试回执把
   `diff_fingerprint` 一并绑定进 `VerificationEvidence`（进指纹与回执），
   证据锚定到「具体这一份 diff」而非仅结果内容。

9. **修复证据写入事件链并随证据包取证**（`control.record_verification`）
   控制面 `record-verification` 是唯一允许写 `verification_runs` 的入口；
   `runner` 在补救回合（产物缺失）进入时把该条修复证据（指纹 + 缺失摘要 +
   分类）写入事件链（`verification_recorded` 事件，幂等）。`build_evidence_pack`
   自动把 `metadata.verification_runs` 一并纳入 `verifications.json`，回归证据
   随包可取证。控制面验证域只有 build/deploy/listen/device_test 四类，R3 验证
   按 `device_test + layer=unit` 如实记录，`evidence` 字段放指纹、`note` 注明
   实际类别，不冒充设备实测。

## 六类失败定义

| 类别 | 含义 | 证据信号（示例） |
|---|---|---|
| `environment` | 环境/系统问题，与代码改动无关 | 退出码 126/127、`command not found`、`ModuleNotFoundError`、`Permission denied`、OOM |
| `code` | 代码改动引入的回归 | 测试断言失败、非零退出且无环境/契约信号 |
| `test` | 测试架子本身的问题 | `failed to collect`、`no tests ran`、fixture 错误 |
| `contract` | 控制面/门禁未满足 | 产物缺失、边界复检失败、副作用回执失败 |
| `model_capability` | 模型没有按契约产出或产出不可解析 | JSON 提取失败、未知工具、未审批、max_turns |
| `side_effect_unknown` | 无法判断类别/副作用不明 | `ambiguous_side_effect`、未闭合 operation |

## 验收（离线，已通过）

- `classify_failure` 对六类代表性样本分类正确；无法归类按 fail-safe；
- `evidence_fingerprint` 对同一事实稳定、对输出/退出码/产物哈希变化敏感，
  且不泄露输出正文或敏感参数；
- `VerificationLedger`：首次新证据允许、同指纹拒绝、输出变化允许、
  超界停止、副作用不明转人工、attempt 递增；
- runner 补救回合在首次失败时仍会进入（兼容既有离线链），无新证据时跳过；
- `run_task` 把独立测试退出码/输出摘要/环境指纹/改动哈希绑进 `TaskReport.verification`；
- `to_receipt` 与 `build_evidence_pack` 把验证证据序列化进证据包且不含正文。

## 边界（不冒充）

- 本切片**不是**完整 R3：真实模型有界修复循环尚在验收，证据尚未绑定真实 commit SHA；
  工作流 `step=review` 的原生跨平台命令边界仍 fail-closed；
- 分类函数只消费已提供证据，不做无依据推断，也不代替控制面门禁；
- 有界修复仍受既有预算、回合数、审批与副作用回执约束。

## 并行开源研究取舍

- **采纳机制：** Aider 的 edit→lint/test 验证闭环、SWE-agent 的
  observation-feedback、OpenHands 的 stuck detection、Cline 的 checkpoint
  共同点都是「没有新证据就不允许继续碰运气」；本切片用证据指纹 + 有界
  次数实现同一目标，不复制任何第三方实现。
- **不直接采纳：** 多 LLM 投票式对抗验证（arXiv 2512.03097 已证明共谋可破）；
  保持规则绑定 + 禁止自我委派。
- 以上为机制层面结论，不代表已集成任何上游运行时依赖。

## 已完成（回归切片，2026-09-26）

1. `workspace_changes` / 测试回执绑定到具体 commit/diff 与 artifact hash：
   `diff_fingerprint` 进 `VerificationEvidence`（指纹 + 回执）；
   工作区快照排除 `__pycache__` 编译产物（不是模型改动，不进 diff 证据）；
2. 独立 Reviewer 接线：`run_task` 用只读上下文复核改动与证据，不能修改被审对象；
3. 修复证据写入事件链与证据包：`record-verification` 记录 `verification_recorded`
   + `verification_runs`，`build_evidence_pack` 自动纳入 `verifications.json`；
4. **`run_task` 有界修复循环**：独立测试失败后，若类别可自动修复，在
   `max_repairs` 有界次数内重新让模型改动并复测；每次必须有**新的失败证据**
   （diff 或退出码/类别变化），同 diff 无新证据即停止，不碰运气；
   `TaskReport.repair_attempts` / `repair_decisions` 记录全部尝试与决策。
   指纹语义修正：`attempt` 是账本标签不进指纹（同一失败再次观测=无新证据），
   `record` 保留 `diff_fingerprint`；离线用 FakeBackend 覆盖修复成功、
   无新证据停止、次数有界三种路径。
5. **验证器继承执行隔离**：`run_task` 的独立 unittest 验证使用与 Executor 相同的
   sandbox，避免工作区测试代码经后置验证进程越过文件/网络边界。新增 Linux bwrap
   负例：测试代码尝试打开工作区外临时文件时被拒绝；密钥路径只验证 `open` 被拒，
   不读取内容。该修正已本地回归，跨平台 CI 与真模型调用待验证。
6. **独立模型 Reviewer 的精确读权限**：Reviewer 使用新对话、仅 `read_file` 工具与
   `allowed_read_files` 精确路径集，不获得 `glob`/`grep`/`workspace_changes`、写入或
   命令执行能力；必须读全本次变更、合法 findings 仅能指向改动文件，finding 保存行号
   并绑定 `evidence_fingerprint`。审查前后快照一致且任务确有改动才可能通过。
   Guard、工具越权、账本保密、无改动任务、非法响应及阻断 finding 的回归均先 RED 后 GREEN；
   本轮 57 项 Reviewer/Guard/runner 定向测试通过；真实模型单次执行 + 测试 + Reviewer 已通过，
   但 `max_repairs=0` 且没有出现失败，未覆盖真实模型修复重试；全量预检与跨平台 CI 待完成。

## 下一片（尚未闭合）

1. **已实现的基础锚点：**`base_commit_sha` 只表示任务开始时的提交；`initial_worktree_fingerprint` 与 `tested_worktree_fingerprint` 覆盖包括预存脏改动在内的快照，`diff_fingerprint` 保留本轮改动语义。回执与 Reviewer 终态校验均覆盖这些字段；快照摘要现包含文件类型、符号链接目标及 POSIX Git 可执行位，相关行为先 RED 后 GREEN。该快照仍不等于 Git tree。
2. **受测 tree 与结果 commit（POSIX 已实现；Windows 仍不签发）：**从 POSIX 仓库根以 no-follow 文件描述符只读扫描当前 Git 文件投影，用 Python 标准库按 Git object serialization 计算 tree OID；包含 staged/unstaged 当前工作树状态、未跟踪及 ignored 项，不触碰用户 index、不调用 `git add`/filters。以测试前后工作区 fingerprint 与 tree OID 一致作为可记录条件；`tested_git_tree_oid` 已进入 evidence fingerprint/receipt，送入独立 Reviewer 输入，且审查后会重算 tree，发现漂移即否决。显式 `--result-commit` 只读查询重算 commit/tree 规范对象 OID 并比对请求 OID，摘要也进入 receipt；不匹配令任务失败关闭。正文读取受预查大小硬上限约束。上述 POSIX 链路已有对象完整性、SHA-1/SHA-256、用户 index 不变、receipt/fingerprint 绑定与 Reviewer 漂移回归，并经 CI #263/#267 验证。匹配只证明 tree 层路径/字节/模式一致，不认证来源/时序，也不含 ACL、xattr 或执行环境。缺失 promisor 对象不得因查询而惰性取回；该行为按具体 Git binary 验收，不由版本号推断。Windows、子目录工作区、嵌套 `.git`/gitlink、特殊文件、路径竞态或不可读项一律不提供受测 tree OID。Attributes 不被读取或执行：转换最多造成安全的不匹配，不能把 raw-worktree 哈希解释为 Git clean-filter 结果。
3. **工作流 Reviewer 命令边界（Linux 与 macOS 已验收）：**Linux Bubblewrap 在同一 mount namespace 中以只读 bind 暴露工作区，再用只读空 tmpfs 覆盖 `.icode_output`；路径必须存在、是工作区内真实目录且每层无符号链接，否则不启动命令。已在本机真实执行验证源码可读、工单账本与工作区外秘密不可读、源码与账本路径均不可写。macOS Seatbelt 的同类负例已在 [CI #223](https://github.com/ayukyo/icode/actions/runs/36269281752) 的 ARM64 `macos-latest` 与 Intel `macos-15-intel` 原生 job 通过；Windows、容器及策略化 Reviewer 仍 fail-closed；
4. **短上下文终结器真模型路径（已补一条有限证据，2026-09-27）：**在合成临时靶场强制进入合法 fallback，再由真实 MiniMax-M3 执行终结器；记录见本计划末尾。此项不代表主 Reviewer 自然触发 fallback 的概率，也不替代 R2 或跨平台 OS 边界验收。

## 2026-09-27 UTC：受测 tree 证据方案复核

- **竞品研究：**OpenCode `a42f393c850bec0c0f395fb91bf19b1ee8b31666` 用独立 Git 目录/index/对象库构造可撤销会话快照，但会按 ignore 筛选且不代表测试认证；Codex `b334d5b3f2d9441b95286a8c2af8c2152737d977` 提供 HEAD→worktree diff/未跟踪清单，本次未见测试结果 tree 绑定。详细源码链接、采纳/暂缓判断见[持续竞品对照](../../agent-landscape-live.md)。
- **方案判断：**Git 官方对象是由类型、长度与正文寻址，Git tree 由路径、模式与子对象 ID 构成；`write-tree` 仅写 index。为避免临时索引过程继承配置并执行 clean/process filter，本实现不调用 Git 来生成投影，而在 Python 中只算规范 OID、不写对象。官方 `gitattributes` 可改写 check-in 字节，故只将 OID 等值解释成最终 Git tree 字节相同；不匹配不推断测试失败，未知条目则不给 OID。
- **验收切片状态：**canonical object hash 与 Git CLI tree 交叉测试、类型/模式/符号链接/字节路径排序、untracked+ignored 输入、SHA-1/SHA-256、测试前后净漂移、用户 index 不变、显式 `result_commit_sha`/`^{tree}` 比对及 receipt/Reviewer 绑定均已实现并有回归。Windows no-follow tree OID、不同 Git 实现下缺失 promisor 对象不触发惰性网络取回、路径竞态与 Git attributes 转换边界仍按本计划下方记录保持 unsupported/不作强保证。研究日期：2026-09-29 Asia/Shanghai。

## 2026-09-26 UTC：CI #188 跨平台证据接线回归

- [CI #188](https://github.com/ayukyo/icode/actions/runs/36222709957) 的 Python 3.11/3.12、Windows x64/ARM64 wheel、Linux 原生探针通过；Windows 两架构的 `test_局部自检不冒充完整沙箱` 失败，macOS Intel/ARM 因评分调用没有提供 `process_group_cleanup` 布尔证据而异常退出。
- **根因区分：**Windows `capability_report()` 把 Job 的正常退出/超时回收局部探针作为 `doctor_self_test`，并把 Windows Job 清理错传成 macOS 专用 `process_group_cleanup`；评分因此回退到空证据。macOS 原生 CI 的 `scripts/run_native_probe_ci.py` 评分前只运行六项文件/网络探针，没有运行真实同组清理探针，而 evaluator 按设计拒绝缺失证据。
- **修正与本地回归：**先新增跨平台 capability-report 与 macOS 原生 CI 编排测试并观测 RED，再修为：仅 Linux 已完成的内核沙箱最小探针可点亮 doctor `doctor_self_test`；Windows Job/macOS 同组清理只保留其局部证据；macOS 原生 CI 评分前运行真实组清理，把通过或失败的布尔值写入评分，失败仍令作业非零。额外发现 CI evidence 的来源字段可能是字符串或数组；补上输出格式回归，避免把字符串逐字符 join。当前 focused tests 与 Linux 原生探针通过；Windows、Intel macOS、Apple Silicon 的真实 runner 复验尚待后续 workflow。
- **状态边界：**CI #188 原始失败保留为历史证据。上述本地修正不等同原生复验，不关闭 R2；R3 的真模型端到端有界修复与 review 步骤接线仍是独立未闭门项。

## 2026-09-26 UTC：真实模型修复分支首次端到端试跑

- **靶场与实际分支：**使用一次性隔离 Python 计算器靶场，预置确定性除零缺陷。真实模型触发独立测试失败，分类结果进入可修复分支，`repair_decisions=["allow"]`；模型修改了计算逻辑及相关测试，第二次 unittest 从失败转为通过。此次证明有界修复分支确实执行，不是此前“只跑一次且没有触发修复”的成功用例。
- **最终任务结果：**首轮 Executor 与 repair Executor 都在 `max_turns=8` 到顶；Reviewer 虽读取本次改动文件，但返回值不符合严格 JSON findings schema。`TaskReport` 因回合耗尽和 Reviewer 合同错误正确 fail-closed，没有报告任务成功。整次调用为 18 次模型调用 / 68,929 tokens；因此这不是 R3 端到端验收通过，也不覆盖成功 Reviewer 后的最终闭环。
- **修正方向：**下一步先分析每一轮工具调用消耗与提示响应大小，确定合理且仍有限的 Executor / Reviewer 回合上限；压缩 Reviewer 输出合同、对格式错误保留失败证据并禁止修复器接管 Reviewer；以相同靶场再次验证“初始测试失败 → `allow` → 修复后测试通过 → Reviewer 合法 JSON → TaskReport 成功”。预算与最大回合仍为硬上限，不通过时保持失败关闭。
- **清理与边界：**临时缺陷靶场已移除；模型密钥只经既有本机配置读取，不写入仓库、命令记录或输出。该试跑不证明任意仓库的修复率、成本或生产环境成功率。

## 2026-09-26 UTC：Reviewer 短上下文终结回退

- **现象与改动：**MiniMax-M3 长 Reviewer 会话曾在完整读取改动后仍连续未调用被强制的 `submit_review`。新增只在 `required_tool_not_called`、所有改动文件已完整无截断读取、无此前无效提交且无权限拒绝时启用的全新终结上下文；最终上下文只暴露 `submit_review`，源码从已验证的 `read_file` 输出重建并受 64 KiB 上限约束，仍共用原 `BudgetTracker`。
- **回归与边界：**FakeBackend 正例验证读取阶段自由文本失败后短上下文提交可通过；负例验证终结器请求 `read_file` 会被拒绝。结构化结果仍走原本地合同校验，随后核验工作区快照与 diff fingerprint；fallback 本身不能形成成功，只有本地验证通过的工具提交可形成审查报告。
- **真模型复验：**MiniMax-M3 在 bubblewrap 临时靶场添加 `calc_clamp` 与测试，改动 `calc.py`、`test_calc.py`；独立 unittest 17 项通过，Reviewer 读取两个改动文件并提交有效 schema，TaskReport 通过（14 次调用 / 64,427 tokens）。本次没有进入 fallback 或 repair，因此只作为常规真模型链路证据；fallback 当前由离线回归验证。
- **验证状态：**Reviewer/loop/runner/Windows token probe 聚焦测试 104 项通过；`./.venv/bin/python -m unittest`：830 项通过、23 项跳过；`scripts/preflight.py` 密钥扫描、子模块完整性、全量测试门均通过。真实修复 TaskReport 成功、R2 Windows 双架构 probe 和 Git SHA 锚点仍待完成。
- **Windows 诊断边界：**父子握手都可能在 15 秒附近超时；父端失败后增加最多 2 秒退出宽限，再读取最多 512 字节的安全白名单报告。该改动只改善失败归因，不能让管道握手变成通过；当前 CI #196 使用旧 SHA，必须重跑双架构手动 probe。
- **CI #198 结果与异常映射修正：**使用 `8dd40eb` 的 x64/ARM64 标准用户探针均完成但返回 `unclassified`；普通测试、workspace、Linux/macOS 原生探针、Windows Job 与 wheel 作业完成。`_run_child_mode` 曾把 `TimeoutError` 等类名直接写入回执，违反仅小写标签的 parser 契约。新增固定小写 label 映射、对既有异常类标签的有限兼容，并只在报告路径经固定 TEMP/文件名合同校验后回写；聚焦测试通过，双架构原生复验仍未完成，Windows pipe 不视为已验收。

## 2026-09-26 UTC / 2026-09-27 Asia/Shanghai：task 验证回执持久化

- **实现：**`icode task --receipt-out <新 JSON 文件>` 仅在显式提供时写出 `VerificationEvidence.to_receipt()`；目标存在、父目录不存在、类型不受支持或文件系统无法安全发布时拒绝落盘，不覆盖、不自动建目录。使用同目录临时文件完成序列化后以无覆盖方式发布，失败时清理临时文件。回执可传给 `icode evidence --receipt <JSON>` 并进入现有独立证据包。
- **状态与隐私边界：**验证失败但证据对象可用时仍保存失败回执，`icode task` 保持失败退出码；收据写入失败用独立错误码 fail-closed。回执不含测试输出正文或 raw error，但保留既有 schema 中的命令/摘要与绑定字段。它是结果快照，不是 session/event 日志，不证明过程中没有未记录写入，也不代表完整测试证据或隔离能力。
- **竞品取舍：**固定 SHA 的 Codex RolloutRecorder 展示持久化屏障/写失败保留待重试后缀；OpenHands SDK 分离会话生命周期与持久事件 store；OpenCode 关联前后 Git 快照与差异。采纳明确持久化失败、证据与生命周期分离、快照便于审查等设计原则；暂缓完整 JSONL 事件流和可恢复会话 store，本片不重建 task 生命周期。源码/版本/许可与收益成本明细见[持续竞品对照](../../agent-landscape-live.md) 2026-09-27 记录；只借鉴机制，没有复制代码或新增依赖。
- **验证器一致性修正（由 CI #216 揭示）：**其两个 Python job 的 R3 单测失败都与测试夹具没有测试模块有关：零测试在不同 Python minor release 下出现 0/5 不同退出码，导致修复分支和 tree 捕获次数依赖版本。现在 `run_unittest` 将 `Ran 0 tests` 稳定规范为失败，并以 `-B` 禁止 verifier 自身写入 pyc；两个 tree 绑定回归均加入真实最小测试。此改动保留原始 tree 全量投影语义，不把 `__pycache__` 从树证据里排除。
- **验证：**新增测试覆盖 schema 输出与不覆盖、父目录边界、拒绝任意 duck-typed 回执、损坏证据序列化安全失败、文件发布失败临时清理、NUL 非法目标路径、证据包 CLI 导入、验证失败仍保存、回执保存失败返回独立退出码、零测试失败和 verifier 不污染 tree。完整 `.venv/bin/python -m unittest` 为 893 项通过、23 项跳过；`scripts/preflight.py` 三道守护、`compileall`、`git diff --check`、站点检查、治理检查和竞品对照检查通过。修正提交后的 Windows/macOS/Linux CI 尚待推送触发；`os.link` 对目标 runner/filesystem 的支持仍需在线 CI 结果确认。
- **未关闭项：**R2 原生隔离门、Windows 自动模式、工作流 Reviewer 跨平台 OS 只读边界仍继续 fail-closed；短上下文终结器仅通过本计划下方记录的强制触发真实模型路径，不据此宣称 R2/R3 全部完成。

## 2026-09-27 UTC：短上下文 Reviewer 终结器真实模型强制路径

- **测试构造与边界：**使用一次性 `pycalc` 副本及无秘密 README 变更；Bubblewrap 原生探针通过。Executor 与长上下文 Reviewer 由确定性测试后端驱动：Reviewer 确实调用 `read_file` 完整读取白名单文件，然后被刻意安排为连续未提交，从而只验证唯一合格的 fallback 分支。随后短上下文终结器调用真实 MiniMax-M3。没有把“强制进入”描述成真实模型自然触发，也未保留提示/响应正文或凭据。
- **结果：**生产默认 `LoopConfig.max_output_tokens=2048` 下，终结器首先以 `tool_choice=required`、唯一工具 `submit_review` 发起真实调用，并通过宿主结构合同；随后以 `tool_choice=auto` 自然结束。最终 `TaskReport.ok=True`、`review.model_reviewed=True`、独立测试退出码为 0；两次真实 provider 调用共 3,967 tokens（prompt 3,176、completion 791、cached 1,536、reasoning 0）。两项聚焦 FakeBackend 正负回归通过，非法读取仍 fail-closed。
- **失败探测的修正解释：**此前两次探测将每次输出上限设为 1,200 tokens，响应都用尽该限额；它们不能证明 `tool_choice=required` 或具名选择本身有缺陷。此次用生产默认 2,048 成功，但没有在同一上限下做 required/named A/B，因此不声称上限变化是唯一原因。保留唯一工具 `required` 作为执行策略，后续若调整还须重新做真实模型验证。
- **上游刷新与取舍：**Codex `openai/codex` `main` 固定 SHA `12de0e395d3313bc564190d983cb4f5acf0be713`（Apache-2.0）把 Reviewer 作为独立 one-shot 流程，并另有 managed read-only runtime profile；review prompt/approval 设置不能替代显式 OS 权限。OpenHands Extensions SHA `976f3c9cb61b137d113cd48d6b264e06aa4af54a`（MIT）的 review skill 强调当前改动与证据支撑，但 PR 插件的工具/JSON 提示不证明 OS 只读。ICODE 采纳显式只读权限模型与可操作证据 findings；暂缓自由文本兜底、自动评论/修复和把工具配置当作 OS 隔离。只借鉴机制，未复制代码、未增加依赖；详情及链接见[持续竞品对照](../../agent-landscape-live.md)。
- **退出边界：**这条真实模型路径不验证自然触发、任意任务成功率、敏感源代码发送风险上限之外的隐私承诺或跨平台权限。在当时记录点，工作流 `step=review` 命令及策略化命令继续禁用；后续 Linux-only Bubblewrap 只读目录切片和当前跨平台剩余项见下一节。

## 2026-09-27 UTC：Linux Bubblewrap 工作流 Reviewer 只读命令边界

- **上游只读研究：**Codex Linux sandbox 固定源码 `openai/codex` commit [`7f6c0f9387a0a60f396f61cc58f6b38bc98f2473`](https://github.com/openai/codex/commit/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473)，Apache-2.0。[设计文档](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/linux-sandbox/README.md)和 [bwrap 构造](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/linux-sandbox/src/bwrap.rs)展示只读基础挂载与更具体拒绝路径在同一 mount namespace 中组合、以及路径扩展失败时 fail-closed。ICODE 只采纳精确目录 carve-out 机制，不复制源码、不增加依赖，不引入通用 glob。
- **实现与取舍：**Reviewer 命令仅当后端显式提供 `wrap_read_only_excluding` 时才可包装；Bubblewrap 先只读绑定工作区，再为最浅层排除目录挂载空 tmpfs 并 remount-ro。工单账本通过既有 ArtifactBroker 由宿主按契约提供，不把工作区账本本身暴露给模型命令。工作区外、等于工作区根、路径不存在/非目录、符号链接（包含解析回工作区内的别名）全部拒绝；多个嵌套排除根归并到最浅共同根。策略化 Reviewer、macOS、Windows、WSL 和容器仍因缺少可证明的 OS 级只读/拒读组合而拒绝命令。
- **TDD 与本机验收：**新测试先 RED（缺少显式接口以及现有拒绝路径），实现后对隔离模块运行 66 项，59 项通过、7 项平台条件跳过。真实 bwrap 子进程证实源码可读、输出目录为空、账本不可见、workspace 外 sentinel 不可见、源码写与账本目录新建均失败且宿主数据不变；另覆盖根路径越界、缺失目录、普通文件、内外符号链接和嵌套排除归并。所有 bwrap/挂载启动异常经 ToolContext 映射为 `IsolationUnavailable`，不会降级裸执行。
- **先前切片线上复验：**推送 commit `9b198fc04d2c48a6e2d93fe82cfd0d774446dd78` 的 [CI #222](https://github.com/ayukyo/icode/actions/runs/36266613165) 已全部结束且所有 jobs 成功，包括当时的 macOS 原生基础隔离探针。该 workflow 尚未包含本节 Reviewer 账本拒读步骤，因此不作为当前 macOS carve-out 的证据。
- **边界：**这是 Linux Bubblewrap 的一条工作流 Reviewer 命令路径，不代表策略型自动工单、macOS/Windows、容器或整个 R2 就绪。当前真实挂载验收针对静态路径；对抗性的同用户外部进程在路径校验与 bwrap 启动之间并发替换工作区目录，不在此测试证明范围。跨平台只读 Reviewer 与 R2 自动模式保持关闭，后续需分别完成 native 验收。

## 2026-09-27 UTC：macOS Seatbelt 工作流 Reviewer 工单账本拒读（原生 CI 已验收）

- **上游只读研究：**Codex `openai/codex` 固定源码 SHA [`7f6c0f9387a0a60f396f61cc58f6b38bc98f2473`](https://github.com/openai/codex/commit/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473)，Apache-2.0；其 [Seatbelt profile](https://github.com/openai/codex/blob/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473/codex-rs/sandboxing/src/seatbelt.rs#L484-L588) 在 workspace 读取 allow 谓词内组合根匹配与排除路径的 `require-not literal` / `require-not subpath`。Apple [App Sandbox 文档](https://developer.apple.com/documentation/security/app_sandbox)没有给出 `sandbox-exec` SBPL 通用 deny/allow 优先级的证明；因此 ICODE 不依赖冲突规则顺序，而把 carve-out 写入授权谓词并以 macOS 原生运行作为验收。
- **实现与边界：**Seatbelt `wrap_read_only_excluding` 复用严格排除路径校验，只准工作区内已存在、真实目录，不接受根本身、越界、缺失、文件或符号链接。最浅排除根通过 `(require-all (subpath workspace) (require-not (literal excluded)) (require-not (subpath excluded)) ...)` 从工作区读授权中扣除；若任一排除根与 `/usr`、`/System`、`/Library`、`/bin`、`/sbin`、TLS 或 Python runtime 的独立读取授权重叠则拒绝包装。macOS Reviewer 只接受系统 `/usr/bin/sandbox-exec`，不信任 PATH 中的同名程序。策略化 Reviewer 不变，仍 fail-closed；未复制上游代码、未新增依赖。
- **本地验证与原生结果：**新增 profile、路径负例、独立读取根冲突、可信执行文件与 ToolContext 调用链测试；另修复了无排除根的只读入口可能绕过固定系统执行器的问题，并以新回归测试先 RED 后 GREEN。当前本地隔离模块 73 项通过、8 项平台条件跳过；全仓 preflight 三道守护、改动 Python 文件 AST 解析、站点/治理/竞品检查及 `git diff --check` 通过。GitHub [CI #223](https://github.com/ayukyo/icode/actions/runs/36269281752) 中 `Verify read-only Reviewer hides ticket ledger` 在 ARM64 `macos-latest` 与 Intel `macos-15-intel` 均成功，完成真实文件拒读、别名拒读、写入拒绝及宿主文件不变检查；runner 标签/架构映射见 [GitHub-hosted runners 官方文档](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。这只验收 macOS 普通工作流 Reviewer carve-out，不外推为 R2 隔离已就绪，也不开放 Windows、容器或策略化 Reviewer。

## 2026-09-27 UTC：Windows R3 workspace snapshot reparse-point fail-closed

- **根因与上游依据：**CPython 3.11 的 `Path.rglob("*")` 递归选择器会对 `entry.is_dir(follow_symlinks=False)` 为真的对象递归；CPython Windows stat 转换只把真实 symbolic link 标为 `S_IFLNK`，junction 可保留目录类型。配合 Python 官方 `os.stat(follow_symlinks=False)` 对 reparse point 的合同，静态安全扫描必须另查 `st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT`，不能依赖 `is_symlink()` 或 3.12 才有的 `Path.is_junction()`。固定源码版本、链接、采纳取舍及成本记录在[持续竞品对照](../../agent-landscape-live.md)。
- **实现范围：**Windows `snapshot_workspace` 使用显式递归 `os.scandir`，对 root 及每个子项先做 no-follow metadata check；symlink 按原有合同只记录 link target bytes；junction、mount point、以及未知 reparse point 一律在扫描/读取其目标前抛 `OSError`，禁止产生部分快照。普通文件/目录继续按相对 POSIX 路径散列，`.icode_output` 与 `__pycache__` 排除语义不变。POSIX Git tree OID 路径不改，Windows OID 仍不可用。
- **测试状态：**新回归模拟 workspace root reparse 属性与子目录 junction 属性，并断言 reparse 根未 `scandir`、子 junction 被发现后未递归目标。初次 [CI #241 Windows workspace job](https://github.com/ayukyo/icode/actions/runs/36299522452/job/108564474447) 仅在调用快照前因 `cmd.exe` 引号失败；修正为独立 argv 参数后，[CI #242 Windows workspace job](https://github.com/ayukyo/icode/actions/runs/36300286034/job/108566553505) 已原生建立 junction 并通过拒绝回归。该结果只验收静态 junction 检查，不覆盖未知 tag/mount point、句柄级抗竞态或 Windows tree OID。完整 R3 suite 应使用项目 Python 3.11，不使用系统 Python 3.10。
- **保留边界：**路径型 `lstat/resolve/scandir/read_bytes` 检查只能拒绝静态 reparse；同用户进程若在检查后替换祖先，仍可能存在 TOCTOU。此实现不声称 Windows 句柄级抗竞态、完整 Windows 快照认证、Reviewer 隔离或 R2 自动模式 readiness；若该威胁进入验收范围，须另做句柄级方案或保持相应自动路径关闭。

## 2026-09-28 Asia/Shanghai：工作区快照拒绝未知特殊文件类型

- **缺口：**POSIX fd 扫描与 Windows `scandir` 扫描只处理目录、符号链接和普通文件；其它类型（例如 FIFO）没有显式分支，会被静默遗漏。这样 R3 `changed_files`/diff 指纹可能把真实工作区条目误当作“无改动”。POSIX Git tree OID 对特殊文件已有独立拒绝，但非 Git 靶场和普通改动清单仍依赖 `snapshot_workspace`。
- **修改：**两平台快照在检查 `.icode_output` / `__pycache__` 排除名之后，遇到非目录、非链接、非普通文件时统一抛 `OSError("snapshot contains unsupported file type")`，不给特殊对象臆造快照编码；正常保留名继续排除。`workspace_changes` 将其映射为 `snapshot_unavailable`；`run_task` 初始或复核快照无法完整生成时中止，不产生成功报告。
- **TDD 与验证：**POSIX 普通路径 FIFO、两个快照保留名上的 FIFO，以及模拟 Windows 同类三种场景均先在旧实现上因“未抛错”失败，补充类型检查后通过。关键快照类连续 20 轮共 120 次测试无失败；R3 回归/workspace 定向套件 126 项通过、1 项平台条件跳过；全仓 unittest 1,098 项通过、25 项条件跳过。Windows 测试为分支模拟，未替代原生 Windows runner 验证。
- **独立复审：**首轮复审指出保留名在文件类型检查前 `continue` 的绕过；按意见增加 `.icode_output` / `__pycache__` 特殊对象负例并重排 no-follow 类型检查。复审复查最新 diff 后确认该 Important 项关闭、未发现新问题。
- **上游对照与取舍：**复用持续对照中 OpenCode 固定 SHA `a42f393c850bec0c0f395fb91bf19b1ee8b31666` 的会话快照研究及 Codex 固定 SHA `b334d5b3f2d9441b95286a8c2af8c2152737d977` 的 worktree-diff 研究；所查源码没有为 ICODE 的未知特殊文件定义可安全复用的哈希合同，因此只采纳“证据必须明确覆盖改动集合”的原则，不复制实现或增加依赖。许可均 Apache-2.0。
- **边界：**该改动使不可表示条目失败关闭，不解决 Windows 路径型快照的同用户并发祖先替换竞态；Windows Git tree OID、Windows/容器/策略化 Reviewer 的 OS 命令边界及 R2 隔离门仍未闭合。

## 2026-09-28 Asia/Shanghai：R3 结果 commit/tree 对象完整性

- **缺口与复现：**只读 `cat-file` 的类型、大小和可解析 commit header 不证明对象正文确实属于请求的 OID。在临时仓库中修改 loose commit 的消息正文、保留原 OID 文件名后，旧逻辑仍返回 tree OID；tree 对象也能以同样方式被伪造。本次只修改 disposable 测试仓库，未改用户仓库对象。
- **修复：**按 Git 规范对 `type + 空格 + size + NUL + payload` 重算 SHA-1 或 SHA-256，commit/tree OID 不一致即拒绝。元数据 stdout 上限为 128 字节，commit 正文上限 1 MiB，tree 正文上限 128 MiB；更重要的是，每次正文 `cat-file` 都把刚预查的具体对象大小作为流式硬上限，避免 size 查询与正文读取之间对象变化导致先无界分配。输出一旦超过上限即终止并回收 Git 子进程。读取设置 `GIT_NO_LAZY_FETCH=1`，不改用户 index、不写 Git 对象或引用。
- **测试与复审：**commit/tree 篡改、树预算、超限终止及 partial clone 缺树用例覆盖负例；两项“预查 size 与正文上限接线”测试先在旧实现中因实际参数为 `None` 失败，接线后通过。该回归边界组 7 项连续 20 轮共 140 次通过；结果 commit/tree 与 workspace 聚焦测试 80 项通过；全仓 unittest 1,105 项通过、25 项条件跳过。独立复审发现正文限额未接到 API 调用，修复后复审确认关闭。preflight 测试与子模块门分别通过；密钥形态扫描限定本次 5 个修改文件，避免遍历未跟踪用户目录；站点、治理、竞品排期、编译与 diff 检查通过。推送后 CI 状态见下方 #263 复验记录。
- **Git 运行时证据边界：**本机 `/usr/bin/git` 是 Ubuntu Jammy `1:2.34.1-1ubuntu1.17`，发行版回补 `GIT_NO_LAZY_FETCH`；同一 binary 的本地 `file://` partial clone/tree 正反对照确认：变量设置时 tree 保持缺失，清除变量后可取回。上游 vanilla Git v2.34.1 源码并无此环境变量处理，不应把本机发行版回补外推为同版本号二进制的普遍能力；已验证的新版本上游测试也以 blob 缺失为例，本地测试补充了 tree 场景。变量拒绝隐式 promisor 取回，不禁止显式 `git fetch`。来源及取舍见[持续竞品对照](../../agent-landscape-live.md)本节。
- **R3 边界：**对象 hash 一致只证明正文匹配该 OID，不证明作者来源、签名、任务时序或测试行为；现有 Windows Git tree OID、路径竞态及其它 R2/R3 门仍未关闭。Python 系统解释器 3.10 低于工程 `requires-python >=3.11`；本节测试使用项目 `.venv` Python 3.11。

## 2026-09-28 Asia/Shanghai：结果对象完整性推送后 CI #263

- **结果：**commit [`cfa90ac`](https://github.com/ayukyo/icode/commit/cfa90aca011d46740fa3e555b584d15c667e310f) 的 [CI #263](https://github.com/ayukyo/icode/actions/runs/36361956421) 已结束且总体成功；Python 3.11/3.12 测试、Windows Job/wheel 与 workspace/native workflow jobs 完成。该结果验证对象完整性切片的推送后 workflow，不等同 R2 隔离 ready。
- **R2 原生评分仍失败：**Ubuntu 22.04 x64/ARM64 为 `8/10`、`critical_passed=true`、`ready=false`；`ubuntu-latest` 与 Ubuntu 24.04 ARM 为 `7/10`、`critical_passed=false`、`ready=false`；macOS Apple Silicon/Intel 为 `6/10`、`critical_passed=false`、`ready=false`。普通 workflow 成功不能替代这些直接探针结果，自动模式继续关闭。
- **本次未覆盖：**Windows Git worktree tree OID、Windows/容器/策略化 Reviewer 的 OS 只读边界、R2 资源限制与原生违规回执仍未验收。Windows tree OID 的可行性研究与待确认边界见[持续竞品对照](../../agent-landscape-live.md) 2026-09-28 Windows 小节。

## 2026-09-28 Asia/Shanghai：跨平台 Git 对象矩阵 follow-up（CI #266 → #267）

- **CI #266 失败与根因：**commit [`197a846`](https://github.com/ayukyo/icode/commit/197a846cfb9e9366fd6dac706f4fc98aaad723f4) 将整个 `TestResultCommitTreeBinding` 类加入 workspace 矩阵，Windows 因 `test_run_task显式参数自动绑定结果commit` 期待 `run_task` 已能捕获 worktree tree OID 而失败。当前 Windows OID 功能明确未支持；失败来自测试选择过宽，不是对象读取器失败。Linux Python 3.11 job 也曾只有通用退出码失败 annotation；同一 SHA 的 Python 3.12 和其它 workspace/native jobs 通过。没有管理员权限，无法下载失败 job 原始日志；故不推断其具体失败测试。
- **修复与本机验证：**只选 17 个跨平台 Git commit/tree OID 读取、正文完整性、受测 tree 绑定与大小上限测试；排除依赖 `run_task` worktree tree OID 能力的集成用例，并将 GitHub annotation 标题改成通用 workspace regression。新增覆盖合同测试先红后绿；对象/合同定向 19 项通过、workspace runner 163 项通过、全仓 unittest 1,106 项通过/25 项条件跳过，`preflight.py --only tests`、compileall 与 diff check 通过。独立只读复审确认测试选择边界；其 Minor 注解命名意见已修正。
- **推送后复验：**commit [`bdcf906`](https://github.com/ayukyo/icode/commit/bdcf906f0e82e361943f363a194d90bfdbac7737) 的 [CI #267](https://github.com/ayukyo/icode/actions/runs/36365615681) 总体成功；Windows、macOS、Linux workspace jobs 和 Python 3.11/3.12 全量套件通过。可选 Windows 诊断 job 仍为 skipped，不作功能证据。R2 native probe 仍分别为 Ubuntu 22.04 x64/ARM64 8/10（critical=true）、ubuntu-latest/24.04 ARM 7/10（critical=false）、macOS Intel/Apple Silicon 6/10，全部 `ready=false`；因此该 CI 不表示 R2/R3 完成。

## 2026-09-28 Asia/Shanghai：Windows 目录句柄与文件 ID 原语实验

- **研究问题：**Windows 当前 `worktree_git_tree_oid()` 返回 `unsupported_platform`；本切片只验证 Win32 目录枚举、文件 ID 和共享打开原语，不改变产品路径，也不把实验提升为 R3 能力。
- **测试与实现：**`tests/windows_tree_snapshot_probe.py` 使用 `ctypes.LittleEndianStructure` 按本机 ABI 计算 `FILE_ID_BOTH_DIR_INFO` 固定头，解析有界字节缓冲区；回归覆盖 Unicode 名称、完整 64 位 ID、多记录对齐及截断/畸形偏移。原生测试在 `TemporaryDirectory` 内通过目录句柄枚举条目，再与文件句柄 ID 比对；观察父目录句柄打开时的 child create/rename/delete，并断言文件只读句柄的新写/DELETE 打开、目录只读句柄的新 DELETE 打开因共享冲突失败。输出只含文件系统类型与固定状态，不保存路径或数据。
- **本机门禁：**项目 Python 3.11 的 `preflight.py --only tests`、子模块门、定向 unittest、compileall 与 diff check 通过。当前 Linux 上 5 个纯解析/布局测试通过；原生 Win32 用例按 `os.name != "nt"` 条件跳过，本机结果不代表 Windows 句柄语义。
- **CI #291 / #292：**commit [`37e034b`](https://github.com/ayukyo/icode/commit/37e034bab61a7269ded90f386bde53db71830314) 的 [CI #291](https://github.com/ayukyo/icode/actions/runs/36408530343) 全量 workflow 成功，Windows x64 与 ARM64 探针任务都通过。commit [`ff4f2b2`](https://github.com/ayukyo/icode/commit/ff4f2b24034f4cb4eb8d5bb193e3a60f13fb173c) 的 [CI #292](https://github.com/ayukyo/icode/actions/runs/36409357853) 全量 workflow 最终成功；x64 [job](https://github.com/ayukyo/icode/actions/runs/36409357853/job/108885628104) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36409357853/job/108885627932) 均成功，notice 都报告 NTFS：父目录只读句柄期间创建/删除子项成功，改名报告 `ERROR_SHARING_VIOLATION`；文件只读句柄的新写/DELETE 打开均报告 `ERROR_SHARING_VIOLATION`，枚举与文件句柄 ID 相符。这是两个 NTFS runner 的实测，不外推为所有 Windows 文件系统保证，也不表示 R2 native readiness。
- **上游对照与决策：**依据 Microsoft [`CreateFileW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)、[`FILE_ID_BOTH_DIR_INFO`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_both_dir_info) 和 [`GetFileInformationByHandleEx`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex)。**采纳**test-only 实验来实测目录句柄与文件句柄的差异；**暂缓**把逐对象 FileId/handle 拼成生产快照；**不适配**“目录共享模式冻结了整层树”或“同一时点原子快照”的表述。保持 Windows tree OID `unsupported_platform`，直至 parent-relative 稳定遍历、reparse 验证、ABA/并发写入失败关闭、SHA-1/SHA-256 Git OID 及用户 index/ODB 不变均有可验收实现。该测试使用标准库，不复制第三方实现或引入依赖。

## 2026-09-29 Asia/Shanghai：Windows 相对句柄 no-reparse 原生探针（双架构已通过）

- **上游依据：**Codex 固定源码 [`openai/codex@fbc169827e9789f9e7ba2ed97c15e2021c3312bb`](https://github.com/openai/codex/commit/fbc169827e9789f9e7ba2ed97c15e2021c3312bb) 的 [`no_reparse_dir.rs`](https://github.com/openai/codex/blob/fbc169827e9789f9e7ba2ed97c15e2021c3312bb/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs) 与原生测试将 `OBJ_DONT_REPARSE` 和已固定目录句柄组合使用。Microsoft [`OBJECT_ATTRIBUTES`](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes) 明确 `RootDirectory` + 相对 `ObjectName` 的语义，`OBJ_DONT_REPARSE` 遇到 reparse 会返回 `STATUS_REPARSE_POINT_ENCOUNTERED`；[`GetFileInformationByHandleEx`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex) 将 `FileAttributeTagInfo` 定义为 class 9。ICODE 只用这些官方原语构建一次性 Python/ctypes 测试探针，不复制 Rust 实现。
- **探针范围：**新增 test-only `NtCreateFile` 相对 `RootDirectory` 打开，限制为单个临时靶场内的相对名字；组合 `OBJ_DONT_REPARSE` 和 `FILE_OPEN_REPARSE_POINT`，读取文件属性与 FileId 后立即关闭句柄，不读内容。正例覆盖普通文件/目录；负例覆盖终端 junction、`junction\\outside.txt` 祖先 reparse 路径，以及普通子目录名被 junction 替换后再次打开。对终端链接允许 native API 将它作为 reparse 对象本身打开，但分类器不得把有 reparse 属性的对象报告成普通 opened；祖先路径必须拿到明确 reparse 拒绝状态。拒绝绝对路径、盘符、ADS、点组件、NUL 与无效目录标志。
- **本机与原生验收：**Linux 项目解释器 `tests.test_windows_tree_snapshot_probe` 共 9 项，7 项通过、2 项原生 Windows 测试按平台 skip；compileall、全量 preflight 三道守护与 `git diff --check` 通过。提交 [`6cadedc`](https://github.com/ayukyo/icode/commit/6cadedc) 的 CI [#336 x64](https://github.com/ayukyo/icode/actions/runs/36527310079/job/109273079787) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36527310079/job/109273079792) 均在 Windows runner 上执行完整模块，9 项通过。测试明确观测普通打开成功、终端 reparse 不被分类为普通文件、祖先 junction 返回 `STATUS_REPARSE_POINT_ENCOUNTERED`，以及已打开为普通目录的名称被替换成 junction 后不再作为普通目录接受。
- **结论边界：**此探针证明的是 Windows runner 上一个打开请求对 junction 的处理，不是并发替换/ABA 的完整模型，也未把枚举得到的 FileId 与后续打开身份做一致性复核；它没有接入 `snapshot_workspace`，不产生 tree OID，也不提供递归原子快照。下一片仍须覆盖身份绑定、并发漂移失败关闭、Git SHA-1/SHA-256 序列化与 index/ODB 不变。Windows `worktree_git_tree_oid()` 继续 `unsupported_platform`，R3 readiness 与自动模式不变。

## 2026-09-29 Asia/Shanghai：Windows 目录共享模式后续复核（无新增代码）

- **现有证据足够：**复核确认原生探针父目录句柄使用 `FILE_SHARE_READ`，已同时省略 `FILE_SHARE_WRITE` 与 `FILE_SHARE_DELETE`；CI #292/#294 的 NTFS x64/ARM64 观察仍是子项 create/delete 成功、rename 报 sharing violation。另开目录 DELETE-access handle 被拒，不等于命名空间冻结。
- **官方合同：**Microsoft [`CreateFileW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew) 描述共享标志对同一 file/device 后续 open 请求的兼容要求；[`DeleteFileW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-deletefilew) 与 [`MoveFileW`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefilew) 没有将父目录 share mode 定义为递归子项 namespace lock。
- **取舍：**不再加只会重测已知差异的 A/B。仅当需要解释当前 runner 上 rename 为何被拦时，再做 test-only share-mode 组合诊断；它不改变安全结论。Windows `worktree_git_tree_oid()` 继续 `unsupported_platform`，路径 TOCTOU、Reviewer OS 边界与自动路径不变。

## 2026-09-29 Asia/Shanghai：Linux Reviewer Bubblewrap CI 门补齐

- **问题与现状：**Linux Reviewer 的工作流命令包装已通过本机真实 Bubblewrap 验证：审查源码可读，`.icode_output` 中账本及其工作区内符号链接别名不可读，工作区外 sentinel 不可读，源码与输出目录写入被拒，宿主内容保持不变。但既有全量 unittest 用例带 Linux+bwrap 条件 skip；若 CI runner 缺少 bwrap，仅靠常规测试不能证明原生边界运行过。
- **实现：**`.github/workflows/ci.yml` 的 Linux native-probe matrix 新增专项步骤，显式 `apt-get update/install bubblewrap`，然后运行 `ToolContext` 调用链集成用例和直接 Bubblewrap OS 探针。缺少包、安装失败、bwrap namespace 无法启动或测试失败都会使 job 失败，不把平台 skip 计为通过。新增 `tests/test_ci_workflow_contracts.py` 锁定这条 CI 契约；契约变更测试先 RED，加入依赖安装后 GREEN。
- **本地证据：**新 Reviewer OS 探针连续 20 次通过；隔离模块 84 项通过、9 项 macOS 专属测试按条件跳过；工作流契约测试通过；`preflight.py --only tests`、修改文件 compileall、`git diff --check` 通过。竞品取舍、许可及链接记录见[持续对照](../../agent-landscape-live.md) 2026-09-29 Linux Reviewer 小节。
- **CI #306 结果与边界：**Ubuntu 22.04 x64/ARM64 两腿的新合并步骤通过；Ubuntu 24.04 x64/ARM64 两腿在同一命名步骤失败。公开 job annotations 只给出退出码 1，且下载原始 job logs 返回 GitHub `403 Must have admin rights`，因此无法区分包安装、AppArmor 或具体 OS 探针故障。诊断 notice 显示 Ubuntu 22.04 的 `apparmor_restrict_unprivileged_userns=0`、24.04 为 `1`；Ubuntu 24.04 默认 user-namespace 限制与两腿差异相符，但不作为已证根因。
- **后续修正：**拆分 Bubblewrap 安装、AppArmor 前置、ToolContext 集成、直接 OS 探针四个步骤；当限制 sysctl 为 1 时只加载附带的 `/usr/bin/bwrap` AppArmor profile（授予该程序 `userns`），不写 sysctl、不关闭全局限制。Ubuntu 官方 24.04 说明支持在 `unconfined` profile 上添加 `userns` 权限；本机 Ubuntu 22.04 AppArmor parser 3.0.4 不识别该新规则，因此不把本机 parser 输出算作通过，须由 24.04 原生 CI 验证。此 CI-only 配置不会证明普通用户安装后无需 AppArmor 前置，也不改变生产代码或 capability score。
- **未验收：**CI #307 尚待推送后完成 Linux 四腿复验。此门只覆盖 Linux Reviewer 文件边界，不替代 macOS/Windows Reviewer、R2 资源限额/违规回执验收，也不表示 R2 或 R3 ready；自动模式状态不变。

## 2026-09-29 Asia/Shanghai：Reviewer 精确读文件拒绝硬链接别名

- **问题与 RED 证据：**`read_file` 先按规范路径做工作区/白名单判断，再经锚定目录句柄读取；但 hard link 的工作区目录项仍解析到工作区内名称，POSIX 打开句柄的原有检查只确认普通文件。新增外部私密标记文件硬链接到工作区白名单路径的回归后，旧实现确实返回了内容（测试先 RED）。
- **最小实现：**仅当 `ToolContext.read_only_workspace=True` 时，`_read_anchored_text` 对实际打开的文件句柄读取 `fstat().st_nlink`，只允许链接数为 1 的普通文件；不支持读取的 hard link 返回既有 `read_unavailable`。普通会话不加此限制，保留其原有硬链接读取兼容性。POSIX 继续沿锚定目录 fd + `O_NOFOLLOW` 读取；Windows 改用打开句柄读取并在同一句柄上检查链接数。未增加依赖或复制上游代码。
- **上游证据与取舍：**Codex `openai/codex` 固定 SHA `1bf73324cadc72a53ed467edc7d3fd2b145a6166` 的 [file-system API](https://github.com/openai/codex/blob/1bf73324cadc72a53ed467edc7d3fd2b145a6166/codex-rs/file-system/src/lib.rs) 与 [local file system](https://github.com/openai/codex/blob/1bf73324cadc72a53ed467edc7d3fd2b145a6166/codex-rs/exec-server/src/local_file_system.rs)，以及 Gemini CLI `2fe7c2d3f065dc40ad573d50b2091116f8a4aa18` 的 [fileUtils.ts](https://github.com/google-gemini/gemini-cli/blob/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18/packages/core/src/utils/fileUtils.ts)，在所查路径中均未发现硬链接计数拒绝。Gemini 会在读取前后比较 `dev`/`ino`，能帮助发现路径对象替换，但不识别同一 inode 的其他链接。Microsoft [硬链接说明](https://learn.microsoft.com/en-us/windows/win32/fileio/hard-links-and-junctions)说明多个名称引用同一文件；[`BY_HANDLE_FILE_INFORMATION.nNumberOfLinks`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information)提供句柄链接数。**采纳**在 Reviewer 白名单路径上补充同一句柄链接数门槛；不把 `nlink==1` 解释成来源证明，也不把 Gemini 的路径身份检查外推成硬链接防护。
- **本机验收与剩余门：**硬链接回归先 RED 后 GREEN，断言 Reviewer context 不泄露标记且普通 context 兼容读取；完整 `scripts/preflight.py` 三道门通过。提交 `e02cf81` 的 CI [#311](https://github.com/ayukyo/icode/actions/runs/36476737521) 所有必需作业成功，但 workflow 的 Windows 作业没有执行 `tests.test_tools` 硬链接用例，故不作为 Windows 句柄链接计数证据。新增双架构 focused step 见下节，等待新 CI。此 slice 不解决 Windows symlink/reparse TOCTOU、文件树快照竞态、策略化 Reviewer 或 OS 沙箱，也不改变 R2/R3 readiness。观察日期：2026-09-29。

## 2026-09-29 Asia/Shanghai：Reviewer ToolContext 精确读取纵深防御

- **问题与 RED 证据：**独立 Reviewer 的 `Guard` 已限制 `changed_files`，但它所持 `ToolContext` 未携带相同名单；单独调用 builtin handler 时，未授权 sibling 仍可由 `read_file` 读取，目录 `grep` 也可扫描。两条 direct ToolRegistry 回归在旧实现上分别得到成功结果，按预期 RED。
- **实现与兼容：**新增可选 `ToolContext.allowed_read_files`，构造时将条目规范化一次；无效名单收敛为空集合以 fail-closed，`None` 保留普通上下文既有语义。`_policy_allows_read` 同时要求精确路径匹配；独立 Reviewer 与其终结上下文都接收 `changed_files` 名单，grep 的扫描上下文继承该限制。未改变 Guard 判断、普通会话授权或 OS 沙箱状态。
- **上游对照与取舍：**Gemini CLI 固定 SHA [`2fe7c2d3f065dc40ad573d50b2091116f8a4aa18`](https://github.com/google-gemini/gemini-cli/commit/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18) 的 [ReadFileTool](https://github.com/google-gemini/gemini-cli/blob/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18/packages/core/src/tools/read-file.ts#L123-L161) 在 handler 内执行路径授权，但其范围是 workspace/temp 子树而非 Reviewer 变更文件名单；Codex 固定 SHA [`5a5a4aa79696a4c8a46dea1c9c04066b22559332`](https://github.com/openai/codex/commit/5a5a4aa79696a4c8a46dea1c9c04066b22559332) 采用权限策略与平台 sandbox filesystem 分层。本次采纳“在实际文件内容读取入口执行授权”的控制点，保留 ICODE exact-file 语义并继续区分 OS 层；不复制代码、不新增依赖。两仓均 Apache-2.0，概念借鉴无代码许可负担。成本是每个未来内容读取 handler 必须复用该合同；Gemini `dev+ino` 检查可发现部分路径替换，但不识别 hardlink，不能取代现有同句柄 `st_nlink==1` 门槛。
- **本机与远端验收：**两条回归先 RED 后 GREEN；`tests.test_tools`、`tests.test_runner`、`tests.test_reviewer` 合计 93 项通过，compileall/diff 检查通过；随后全量 `scripts/preflight.py` 的密钥、子模块和 unittest 三道守护全部通过。GitHub [CI #312](https://github.com/ayukyo/icode/actions/runs/36479949142) 的 Windows Job cleanup probe x64/ARM64 三项精确名单与真实硬链接测试成功；[CI #313](https://github.com/ayukyo/icode/actions/runs/36481777383) 的 macOS Intel/Apple Silicon 同组测试成功，Python 3.11/3.12 全量测试与守卫也成功。两次 workflow 的必需 jobs 均成功，默认关闭的两个可选诊断 jobs 跳过；官网 [#217](https://github.com/ayukyo/icode/actions/runs/36481777807) 成功。硬链接创建失败在 Windows/macOS 原生 runner 都不能以 skip 计过。
- **剩余边界：**这只在 ICODE builtin application layer 建立拒绝，不是系统级访问控制证明；R3 Windows tree OID、Windows Reviewer OS 只读/拒读、策略化 Reviewer 与其它平台原生 read boundary 仍未完成。R2/R3 ready 状态不变。

## 2026-09-29 Asia/Shanghai：Reviewer CI AppArmor profile 安全复核

- **历史 CI 结果：**commit `63c0f49` 的 [CI #307](https://github.com/ayukyo/icode/actions/runs/36462913484) 四个 Ubuntu runner 的 Bubblewrap 检查成功。但该版本使用 `flags=(unconfined)` + `userns` profile；Canonical [明确说明](https://discourse.ubuntu.com/t/understanding-apparmor-user-namespace-restriction/58007)这类 profile 会为 unconfined 应用提供绕过 userns 限制的路径。因此 #307 是测试配置下的成功运行记录，不是可接受的安全隔离证据，覆盖旧的“CI #307 尚待复验”状态说明。
- **当前实现候选：**工作流已移除仓库内宽权限 profile，改为从 AppArmor 固定提交 [`b0eb95457bc2de401920308869d016e696c73664`](https://gitlab.com/apparmor/apparmor/-/blob/b0eb95457bc2de401920308869d016e696c73664/profiles/apparmor/profiles/extras/bwrap-userns-restrict)临时下载专用 profile，固定 SHA-256 为 `11d39094f044f0cda0febb3ad517b830301da6b2ce929664af09ee9e4dd264f9`，校验后才由 runner 管理员加载；再检查 `bwrap (enforce)` 和实际 child label 含 `unpriv_bwrap`。上游根 LICENSE 为 GPLv2，ICODE 不 vendoring；profile 仍赋予 bwrap 较广初始化权限，父/子 profile 都允许 userns，子进程 `audit deny capability`，所以不宣称禁止嵌套 user namespace，也不把它本身当作文件只读边界。这一例外只在一次性 CI runner 生效，不是产品用户的安装指引。
- **#308 结果与修正：**commit `018ed54` 的 [CI #308](https://github.com/ayukyo/icode/actions/runs/36469108401) 中 Ubuntu 22.04 x64/ARM64 通过，Ubuntu 24.04 x64/ARM64 在 profile 清单核验时失败。原始 job log 显示下载与 SHA-256 校验成功、`apparmor_parser --replace` 返回成功；其后普通 runner 用户读取 `/sys/kernel/security/apparmor/profiles` 得到 `Permission denied`，错误分支再次读取时同样受拒。没有证据表明该次已运行 bwrap child-transition 探针。
- **#309 推送后验收：**修复 commit `2750a1e` 的 GitHub [CI #309](https://github.com/ayukyo/icode/actions/runs/36471224474) 总体 success：18 个必需 job 成功，两个默认关闭的诊断 job skipped；Ubuntu 22.04/24.04 x64/ARM64 四个原生探针、Python 3.11/3.12 全量测试、Windows x64/ARM64、macOS Intel/Apple Silicon 与 presentation jobs 均通过。官网 workflow [#213](https://github.com/ayukyo/icode/actions/runs/36471224530) success。四个 Ubuntu 原生 job 现确认 enforce profile 清单可读且 bwrap child 进入 `unpriv_bwrap`，并继续通过 Reviewer ToolContext 与 OS 负例探针。
- **剩余验收：**上述 CI 关闭的仅为 Linux Reviewer profile 门；不等同 Windows/macOS Reviewer OS 边界、R2 资源限制/统一违规回执或完整 R2/R3 ready。平台评分及自动模式状态不变。

## 2026-09-29 Asia/Shanghai：CI #334 Windows directory-handle 原语重复验收与上游刷新

- **CI #334 原生结果：**Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36522598887/job/109258542811) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36522598887/job/109258542579) 均通过 `tests.test_windows_tree_snapshot_probe` 六项用例，NTFS notice 相同：`directory_create=allowed`、`directory_rename=blocked_sharing_violation`、`directory_delete=allowed`、文件 handle 的写入/删除 open 被 sharing violation 阻止。它复验已知句柄差异，不意味着文件夹命名空间冻结、R3 Windows 快照安全或 tree OID 可用。
- **上游复核：**Codex 固定提交 [`fbc169827e9789f9e7ba2ed97c15e2021c3312bb`](https://github.com/openai/codex/commit/fbc169827e9789f9e7ba2ed97c15e2021c3312bb) 的 turn diff tracker 记录 apply-patch 变更而不重扫工作区，不能替代执行前后快照；其 Windows [`no_reparse_dir.rs`](https://github.com/openai/codex/blob/fbc169827e9789f9e7ba2ed97c15e2021c3312bb/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs) 使用 no-reparse handle-relative 打开原语，可作为未来候选但不是递归 snapshot。Cline 固定提交 [`3ba8dd8fa7b30420d03bf208b7d35b0f7f535cf5`](https://github.com/cline/cline/commit/3ba8dd8fa7b30420d03bf208b7d35b0f7f535cf5) 的 checkpoint hooks 含 session/cwd/run 元数据并可捕获 untracked 文件，但 checkpoint ref 未与 ICODE 所需的测试结果/tree OID 证明合同等价。固定源链接、许可、取舍及实现差异见[持续竞品对照](../../agent-landscape-live.md)。本轮没有改 Windows 快照生产路径。
- **下一片 R3 边界：**优先拆出可测试的 parent-relative no-reparse 元数据/文件打开协议与身份复核，拒绝路径组件在扫描期间替换；先用一次性 Windows 原生靶场验证正常树、终端/祖先 junction、rename/replace ABA、读失败及句柄清理，再评估是否能用于递归读取。直到 SHA-1/SHA-256 tree 构造、全树并发失效关闭、用户 index/ODB 不变和 x64/ARM64 原生证据闭合，Windows `worktree_git_tree_oid()` 保持 `unsupported_platform`。Reviewer OS 边界、R2/R3 ready 及自动模式不变。
