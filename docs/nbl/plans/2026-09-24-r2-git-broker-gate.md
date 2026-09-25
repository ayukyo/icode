# R2.4 分层工作区 Git 状态代理门禁

- 日期：2026-09-24
- 状态：Linux 固定参数 Git status 内部原型已在本机真实 Landlock 下通过定向验证；不注册工具、不接模型调用链。macOS/Windows 等价边界、干净 wheel 和完整 R2 仍阻断
- 依据：[R2 正式设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §4.2、§7；[持续竞品对照](../../agent-landscape-live.md)

## 三问与现状

1. 真实问题：分层工作区的代码根是 `checkout/code/`，Git 管理入口位于只读的 `checkout/.git`；在代码根直接运行普通 `git status` 会以错误工作树解释路径。将 Git 改由宿主执行，又可能读取仓库配置并启动可执行扩展，或写入原仓。
2. 已有实现：`workspace_changes` 仅比较本次任务开始与现在的文件快照，不调用 Git，且明确不冒充暂存/提交状态；分层策略会话中的直接 Git 命令返回 `git_broker_unavailable`。保留这条安全降级路径。
3. 影响链：工具注册与提示 → 当前 `WorkspaceSession` 身份 → 只读 Git 代理 → 受限子进程 → 结构化回执。模型不能提交任意 `--git-dir`、工作树、配置文件、环境变量或可执行文件路径。

## 分阶段出口

1. 第一阶段只做只读状态：从可信会话取得注册路径，不接受模型给出的仓库路径；输出限定为相对代码根的已跟踪改动和未跟踪项，区分文件快照与 Git 暂存区。
2. Git 查询必须在独立的无网络、无外部秘密读取、无原仓或 Git 管理目录写入的执行边界中运行。清除继承的 `GIT_*` 变量；固定可执行文件、子命令和参数；禁止可选锁与 fsmonitor、hook、外部 diff、filter 等可执行扩展。仅靠参数或命令名推断“只读”不足以验收，需真实负例证明。
3. 暂存、提交、切换、fetch/push 都是独立能力与明确授权；只读状态端口不得隐式开放它们。远端认证材料不进入模型命令沙箱，联网能力交给独立代理验收。
4. 上述边界和对应平台的干净 wheel 负例未通过前，保持 `git_broker_unavailable`；`workspace_changes` 也不计为 Git broker 完成。

## 并行开源研究取舍（2026-09-24）

- **采纳机制，不复制实现：**[Codex 当前 Linux 沙箱](https://github.com/openai/codex/blob/61e23bc6a1e9e5fc8ed6aefb3575c9d1fd077c22/codex-rs/linux-sandbox/README.md)把 `.git` 和解析后的 `gitdir:` 在可写代码根下重新设为只读；[内部 Git 查询](https://github.com/openai/codex/blob/61e23bc6a1e9e5fc8ed6aefb3575c9d1fd077c22/codex-rs/git-utils/src/info.rs)使用 `GIT_OPTIONAL_LOCKS=0`、禁用 hook、控制 fsmonitor 并设时限。ICODE 已有分层工作区和拒绝直通 Git，后续只读代理应复用可信会话身份，并以 OS 边界证明只读，而非仅照搬这些参数。
- **采纳失配即关闭：**[Qwen Code 当前沙箱说明](https://github.com/QwenLM/qwen-code/blob/d33cd4ddcb5ce4c8f98df42210ca967707b3b9cd/docs/users/features/sandbox.md)明确禁用未移植的宿主 Git 预览/工作树管理，后端启动失败不在宿主重跑。ICODE 当前 `git_broker_unavailable` 保留到实测通过。
- **不直接采纳：**[Gemini CLI 沙箱与逐命令授权说明](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/docs/cli/sandbox.md)可参考用户审批呈现，但其策略不能替代 ICODE 自动模式的默认断网、固定 Git 端口和平台负例。

以上是指定提交的源码/官方文档观察，不是这些上游工具的运行时实测；若上游提交变化，按[持续对照约定](../../agent-landscape-live.md)复核。

## 2026-09-24 UTC 并行复核与决定

- Codex commit `e4b68615f06621c43b365d66823ed01b8f8e8416` 的 [`fsmonitor.rs`](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/git-utils/src/fsmonitor.rs) 实际检查有效 `core.fsmonitor`，只在确认内置 daemon 且 Git 支持时启用，否则覆盖成 `core.fsmonitor=false`，避免仓库配置选择外部 helper；[core README](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/core/README.md) 描述 macOS `.git`、解析后的 gitdir 与 `.codex` 在 workspace-write 下只读。[Git Doctor](https://github.com/openai/codex/blob/e4b68615f06621c43b365d66823ed01b8f8e8416/codex-rs/cli/src/doctor/git.rs) 是不启动 Git 的文件系统诊断；没有发现 Codex 专用 Git 状态 broker。
- Qwen Code v0.24.4 的[沙箱文档](https://github.com/QwenLM/qwen-code/blob/v0.24.4/docs/users/features/sandbox.md)和[设置解析实现](https://github.com/QwenLM/qwen-code/blob/v0.24.4/packages/cli/src/config/execution-sandbox-settings.ts)验证系统/用户级执行策略优先、项目设置不可降低边界、配置无效时拒绝启动；文档同时明确 network closed 不等于隐藏宿主文件/本地服务隔离，并拒绝宿主 Git 预览等未移植操作。没有发现独立 Git 状态代理。
- **采纳：** 固定 Git 可执行文件和参数，结构化 NUL 输出；对外部 helper 禁止优先于提速。OS 沙箱必须让代码与 Git 元数据只读、默认断网，并覆盖链接 worktree 解析后的 gitdir/common-dir。可信会话必须绑定路径身份，失败保持 unavailable。
- **暂缓接线：** ICODE 尚无可以让 Git 读取元数据但禁止写入的三平台统一执行合同；当前 Linux Landlock helper 仅表达单代码根读写，macOS/Windows 相关策略也未完整验收。因此先完善执行边界与恶意仓库负例，不开放工具入口；仅清理 `GIT_*`、设置 `GIT_OPTIONAL_LOCKS=0` 或过滤命令行均不构成安全证明。

## 先红后绿验收

- 恶意仓库配置包含 fsmonitor、外部 diff、filter、hook、credential helper；只读状态不得启动它们，不得读取或写入宿主敏感路径。
- 查询前后对工作树、Git 管理目录、index、锁文件及原仓做不跟随链接的身份与内容检查；正常、错误、超时路径均不产生越权写入或残留子进程。
- 分层 worktree、中途删除或替换 `.git` 指针、无效会话、跨任务路径、符号链接/重解析、空格和非 ASCII 文件名，以及模型注入 `-c`/`--git-dir` 均须 fail-closed。
- Linux x64/ARM64 与 macOS/Windows 对应架构在独立安装后验证；不具备等价隔离的系统不开放该端口。

本计划仅固定后续实施与验收门禁，不改变任何当前能力声明。

## 2026-09-25 独立源码复核：Git 状态 broker 的调用链缺口

- 核对 ICODE `main` SHA `e6fceca8f8ee5b0d9b32fc6c7656c62b8a65bcaf`：`git_status.py` 只有严格 porcelain v2 解析器，尚无生产调用；`run_command` 对分层 workspace 的 Git 调用保持 `git_broker_unavailable`。`WorkspaceSession` 没有可信 Git-dir 字段，manifest 虽记录顶层/common-dir/worktree-dir/identity，`NativeChainExecutor → runner → ToolContext` 尚未传入 session 身份；Landlock 也未提供为 Git 元数据加独立只读根的接口。故不能只把解析器接到宿主 `git status`。
- 下一实现片应是 Linux-only 内部 broker：可信 grant 由 `WorkspaceSession(kind=git_worktree)` 派生、启动前重核身份；扩展随包 Landlock helper 对 gitdir/common-dir 提供只读授权，继承既有默认断网；固定 Git 和 porcelain v2 参数，屏蔽 `GIT_*`、hooks/fsmonitor/helper；snapshot、错 run/ticket、身份漂移和其他平台继续拒绝。含无法安全解析的子模块/外部 gitdir 时完整拒绝，不给部分状态冒充成功。
- 上游刷新（2026-09-25）：Codex `aa380897f67b91e1a47d530d7286d497b6726d3f` 把 `.git` 与解析后 `gitdir:` 纳入只读沙箱，内部 Git helper 使用 `GIT_OPTIONAL_LOCKS=0`、禁 hooks、控制 fsmonitor 并设时限；Qwen Code `2686cad25fe8ffc24f582d8cb50f49743a884e3b` 文档要求后端启动失败不回宿主重试；Gemini CLI `bedef96ef42905bd84a86dbec021c706168e7e2f` 跟踪实际 worktree/common gitdir，但其权限转换不宜照搬。采纳“OS 只读边界 + 固定 helper 参数 + 失败关闭”机制，不复制实现。见[持续竞品对照](../../agent-landscape-live.md)。

## 2026-09-25 porcelain v2 解析器前置模块

- 对照 [Git 官方 `git status` 格式文档](https://git-scm.com/docs/git-status)，实现 `src/icode/git_status.py` 的纯字节解析：要求完整 NUL 终止；保留任意路径字节；重命名/复制记录按格式消费紧随其后的旧路径字段；忽略可扩展的 `#` 头；损坏或未知状态记录整体拒绝，不返回部分结果。
- 测试覆盖实际 Git CLI 输出、空格/换行/非 UTF-8 路径、重命名双路径、未合并/未跟踪/忽略类型、已文档化状态组合，以及错误字段和截断数据。此模块自身从不执行 Git。
- **阶段结论：前置解析可用，Git broker 未实现。** 模块没有 OS 权限、网络、helper、仓库路径或会话控制能力，因此不是安全边界；它没有注册成工具，`git_broker_unavailable` 必须保留。接线前仍须完成上面的会话身份、固定参数、helper 禁止、只读 gitdir、无网络、原仓不变、恶意仓库和三平台 wheel 验收。

## 2026-09-25 Linux 只读元数据授权基座

- Landlock helper 增加独立 `--metadata-read PATH` 白名单，只授予 `READ_FILE | READ_DIR`，不授予执行或写入权限；它与可读写的代码根、Python 运行时只读根分开表达。Python 内部包装先解析真实路径，再拒绝已知宽泛根、失效路径、非普通文件/目录、与任务代码根重叠，以及与既有可执行系统/runtime 只读根重叠的授权。后一项是因为 Landlock 同一层中路径规则权限叠加，窄只读规则不能撤销较宽祖先规则已授予的执行位。
- C helper 在真正安装规则时从 `/` 开始逐个 `openat` 路径组件，持有已打开的父目录 fd、对每段使用 `O_NOFOLLOW`，仅接受最终普通文件/目录；因此 Python 校验与 helper 打开之间若路径组件被改成符号链接，会在 payload 启动前失败关闭。
- Linux 本机真实内核测试验证：获准 Git 元数据可读，既有 index 不可覆写、不能新建文件、可执行 hook 无法启动；代码工作区仍可写，未获授权的邻近文件不可读，省略元数据授权时 Git 元数据默认不可读。静态校验也拒绝 `/usr` 与 Python runtime 根，防止与已有执行白名单叠权。helper 以 `-Wall -Wextra -Werror` 编译；隔离测试 47 项通过、7 项按平台跳过。
- 另外用真实 helper 验证最终目录符号链接和中间父目录符号链接均导致 payload 不启动。该检查防止 symlink redirection，但还不绑定已打开目录的 device/inode 与 session 快照；非符号链接路径替换及逐次 session 身份复核仍须由 Git broker 层负责。
- 这是**执行基座，不是 Git broker**：尚无 `WorkspaceSession` 可信 Git-dir grant、身份漂移复核、固定 Git 子命令/参数与环境、恶意仓库配置/扩展负例，也没有 x64/ARM64 wheel 和 macOS/Windows 等价证明。该接口目前只供内部将来接线使用，未注册模型工具，`git_broker_unavailable` 必须保持。
- 下一片先从可信 `git_worktree` 会话构造并重核 worktree/gitdir/common-dir 身份，再以固定 `git status --porcelain=v2 -z` 子命令做 Linux-only 实验；遇到子模块、外部 gitdir、身份变化或任何策略无法表达都整体拒绝。现阶段不得将普通宿主 `git status` 当作回退。

## 2026-09-25 WorkspaceSession Git 身份快照

- `WorkspaceManager` 仅对启用 Git 元数据分离的 `git_worktree` 会话附带冻结的 `GitWorkspaceIdentity`：checkout/code/task 根、顶层、common-dir、worktree gitdir、起始 revision、随机身份标记和源码相对路径。首次创建从内部构造元数据派生；复用前须先通过现有 manifest 精确匹配、`.git` 管理文件检查、Git rev-parse 与 worktree 注册校验。snapshot 与普通未分层 worktree 的字段保持 `None`。
- 新增工作区回归验证创建与复用 session 身份一致，非分层和 snapshot 不会获得 Git 身份。全量工作区与自治 executor 定向测试 112 项通过。
- **仍不是可执行 grant**：身份快照尚未传给 `ToolContext`，也没有每次调用前复核 `.git`/`commondir`/`HEAD`/身份标记；未启动 Git、未开放工具，`git_broker_unavailable` 保持。下一片为只读会话 recheck 与固定参数 Linux status 实验，失败时只返回 unavailable，不执行普通 Git。

## 2026-09-25 Linux 会话身份重核原语

- 新增内部 `git_broker.verify_git_workspace_identity()`，不执行 Git、不注册工具。它仅接受 `WorkspaceManager` 生成的 `GitWorkspaceIdentity`，校验所有路径为绝对规范路径、source 相对路径不逃逸、worktree gitdir 位于 common-dir 内，并用逐组件 `openat`/`O_NOFOLLOW` 检查 checkout、代码根、源码根、原仓顶层、gitdir、common-dir。`.git`、`commondir`、`HEAD` 与随机 marker 通过已打开目录 fd 安全读取并逐项匹配冻结 identity。
- 正常布局返回 checkout code root、worktree gitdir/common-dir、源子目录与三个最小 metadata 候选根（`.git` 指针文件、gitdir、common-dir）。身份缺失、指针/HEAD/token 替换、symlink、路径逃逸和不支持的平台均 fail-closed；错误不包含真实路径或 marker。
- TDD 验收先因新模块缺失而失败，补实现后 7 个 broker 测试通过；另与分层 workspace 回归联合执行 68 项通过，`compileall` 与 `git diff --check` 通过。当前环境未安装 Ruff，未声称通过 Ruff。
- **阶段边界：仍不是 broker/grant。**结果尚未传入 `ToolContext`，未启动 Git、未对 directory device/inode 与 helper 打开动作作原子绑定，也未扩展 Landlock 接口校验这些预期身份。不能消除真实目录被并发替换的竞态；broker 接线、写入负例和模型入口均继续关闭。
- 下一片需补目录/metadata 文件身份快照和 helper 侧 inode 对照，再实现有界的固定参数 Git status；对 submodule / 未支持的 common-dir 布局保持 unavailable。任何平台合同未通过前，不接自动执行路径。

## 2026-09-25 Linux metadata 对象身份固定

- `GitWorkspaceIdentity` 现在随 manager 创建/复用流程捕获 checkout/code/source/origin/gitdir/common-dir 目录，以及 `.git`、`commondir`、`HEAD`、随机 marker 文件的 `(st_dev, st_ino, kind)`。每次纯 Python recheck 都通过 nofollow fd 对照原快照，既拒绝 symlink，也拒绝“同路径换成内容完全相同的新目录/文件”。这组 stat 值只留在 session 内存快照，不写入 manifest 或模型上下文。
- `MetadataReadRoot` 要求可信路径携带预期 device/inode；Python 包装器复核后将三元组传给 helper。原生 Landlock helper 重新逐组件 `openat(O_NOFOLLOW)`，`fstat` 对照声明，再用**同一个 O_PATH fd**安装 `LANDLOCK_RULE_PATH_BENEATH`，消除了校验与规则安装之间通过目录替换绕过的窗口。坏数字、重复根、路径错配、symlink 和 inode 漂移都在 payload 启动前拒绝。
- 官方 [Linux Landlock 文档](https://docs.kernel.org/userspace-api/landlock.html)说明 `parent_fd` 标识规则作用的文件/目录层级；`READ_FILE` 与 `READ_DIR` 的适用对象不同。因此普通 `.git` 指针文件只授 `READ_FILE`，Git 元数据目录才授 `READ_FILE | READ_DIR`。该约束已加入 C helper。
- 真实 helper 回归：普通 metadata 目录仍可读但不可写/新建/执行；普通 metadata 文件可读但不可改写/执行；把原 metadata 目录换成同路径、同文件内容的新 inode，旧 claim 会在 payload 启动前拒绝；Git identity 同路径目录和 HEAD 文件替换也 fail-closed。针对上述四条定向套件共 11 项通过，C 用 `-Wall -Wextra -Werror` 编译。
- **剩余边界：**本片尚未将 recheck/layout 传给 `ToolContext`，也没有启动固定 Git 子命令；未证明 Git config/helper/子模块/超时与输出上限。此特定 Linux metadata grant 不能外推到 macOS/Windows，也不能宣称 R2 broker 或自动模式已完成。下一片才实现内部、有限时/有界输出的 status 执行函数，并维持模型入口关闭。

### 独立格式审查修正（2026-09-25）

- 上游 Git 回归用例确认 `git add --intent-to-add` 会产生合法 `.A` 状态；解析器现接受该组合，并以真实 Git CLI 输出回归。[Git 上游用例](https://github.com/git/git/blob/master/t/t7064-wtstatus-pv2.sh#L1934-L1953)
- mode 字段由“任意六位八进制”收紧为已知类型集合 `000000`、`040000`、`100644`、`100755`、`120000`、`160000`，保留删除与 sparse-index 目录模式并拒绝 `777777`；依据 [Git 数据模型](https://git-scm.com/docs/gitdatamodel)与[索引格式](https://git-scm.com/docs/index-format)。
- 仍忽略格式有效但未知的 `# ` 扩展头；拒绝空头、`#` 后无分隔符或重复空白的畸形头。测试同时验证合法模式集合、`.A`、畸形头及损坏记录 fail-closed。

## 2026-09-25 policy 执行器原始字节回执

- porcelain v2 `-z` 的路径字段是 NUL 分隔原始字节，不能先做 UTF-8 替换再交给解析器。`ExecutionResult` 增加受 `output_limit` 约束的 `raw_output`，原有 `output` 仍以 UTF-8 replacement 解码，保持既有工具调用兼容。
- 先加 subprocess 回归，确认二进制输出 `00 ff 41` 原样保留且兼容文本为 `\x00�A`；执行器定向测试 6 项通过，完整 preflight 的密钥扫描、子模块完整性和测试全绿通过。
- 这是字节协议传输前置能力，不执行 Git、不改变权限、不连接模型工具；输出超限仍为错误，不能把截断流交给状态解析器或当作 clean。

## 2026-09-25 Git status 执行策略复核

- 固定复核 Codex `main` commit `4b1c0c30dabd08fed7d6523844f9156d982eb297`：其状态提示 helper 执行 porcelain v1，仅判断是否有输出；Git 子进程管理还包含 timeout、`GIT_OPTIONAL_LOCKS=0`、hooks 限制与仓库级 fsmonitor 处理。这是轻量 UI dirty-check，不是可直接复用的安全 Git broker。Codex Linux sandbox 的主要边界是 bubblewrap 对 `.git` 与解析后 gitdir 做只读 carveout，不能把 ICODE 的 Landlock 入口视为等价。
- **采纳：**固定关闭 `core.fsmonitor`（Codex 在检测安全后可能允许内置 daemon；对只读原型更保守，避免 daemon 与 `.git` IPC 副作用）；同时设 `GIT_OPTIONAL_LOCKS=0`、固定 hooks 路径、清除全部继承 `GIT_*`，并依靠 OS 写隔离，不把参数当作证明。Git `status` 官方文档提示后台刷新可能写 index；全量未跟踪扫描需要有界超时和输出，超限整体失败。
- **暂缓：**不采纳动态 fsmonitor daemon、不接受外部 helper/用户参数；不承诺 submodule 完整状态。Porcelain v2 的 `S<c><m><u>` 子模块状态需要额外读取子模块元数据，当前 broker 不具备安全 grant；在识别出 submodule 或 linked-worktree common-dir 关系未覆盖时必须整体 unavailable，不能给部分结果冠以完整状态。
- 阶段方向仍为内部 Linux 原型：可信 identity 重核、固定 Git 可执行文件/argv/environment、NUL bytes + 严格解析、超时/字节上限、metadata-only Landlock；自动执行和模型工具入口继续关闭，直到恶意仓库、零写入与目标平台负例通过。

## 2026-09-25 Linux 固定参数 Git status 内部原型

- `execute_git_status()` 仅接受 WorkspaceManager 捕获的 `GitWorkspaceIdentity`、实际 `LandlockSandbox` 与断网策略；调用前复核 `.git`、`commondir`、`HEAD`、ownership marker 及 device/inode。它不接收模型 argv/path，不注册工具，不进入执行器或 ToolContext 路由。
- 所有 Git 子命令均经原生 helper 启动：系统 Git 固定在 `/usr/bin:/bin`，环境不继承 `GIT_*`/宿主 PATH，设置 `GIT_OPTIONAL_LOCKS=0`、禁用 fsmonitor、untracked cache、hook、外部 attributes/excludes 与 pager。固定命令只有 `config`、`ls-files`、`status`，不传无关的空 `diff.external` 值。Git 元数据按 identity inode 只读授权；该查询额外把代码工作区限制为 `READ_FILE | READ_DIR`，不授执行或写入，并拒绝与可执行系统/runtime 白名单重叠的工作区（Landlock 规则权限为叠加，窄规则不能撤销祖先权限）。普通任务策略包装仍保持原权限。
- 安全预检拒绝仓库级与启用时的 worktree 级 `filter.*.clean/process` 配置；先以固定 `ls-files --stage -z` 查明索引是否含 mode `160000`，存在 gitlink 即 unavailable，状态查询固定 `--ignore-submodules=all`，不递归进入另一仓库。任一执行错误、清理异常、超时、输出截断、未知/畸形 porcelain、非 N... 子模块状态都不给部分结果。
- 官方 [Git Attributes 文档](https://git-scm.com/docs/gitattributes)将 `filter.<driver>.clean` / `process` 定义为外部命令，并说明配置了 `process` 时优先于单文件 filter；[Git status 文档](https://git-scm.com/docs/git-status)定义 porcelain v2 与 `-z` 路径约束。宿主 Git 2.34.1 的受控临时仓库正向探针进一步实测：普通 status 会启动恶意 clean 脚本；ICODE 固定代理在执行 status 前拒绝该配置，marker 未生成。假的 fsmonitor/external diff 也未启动，gitlink 在任何子模块查询前拒绝。
- `scripts/run_native_wheel_ci.py` 已在本机 x86_64 构建并检查 Linux wheel、安装至隔离 venv；随包 helper 的原有最小探针和新增 `--workspace-read-only` 写入/执行负例均通过。C 编译单进程执行，没有超出 `-j6`。
- **采纳：**OS 只读/不可执行边界、固定 Git 参数、外部 filter 与 gitlink 整体 fail-closed、有界原始字节输出。**代价：**配置 clean/process filter 或含 submodule 的仓库当前不给状态；仅 Linux Landlock、顶层源码布局受支持。
- **阶段边界：原型已实现，R2 未完成。**Linux x86_64 当前 wheel 通过不等于 Linux ARM64、macOS/Windows 等价边界；仍需并发身份/配置变化审计、超时与超量清理压力负例及后续完整工单调用链验收。自动模式及模型工具入口继续关闭，原有 `git_broker_unavailable` 外部行为不变。

## 2026-09-25 UTC 上游 Git/沙箱调用链复核

- **Codex：**固定复核 [`60713126ee0dbc483fba83fc032dfaa5998521ec`](https://github.com/openai/codex/commit/60713126ee0dbc483fba83fc032dfaa5998521ec)。当前状态辅助是面向 UI 的轻量 dirty-check，Linux 沙箱将 `.git` 与解析后的 gitdir 设为只读；这支持“元数据 OS 只读”的方向，但不是 ICODE 可直接复用的跨平台、完整状态 broker。其普通 Git status 结果不得作为 ICODE 安全合同。
- **Qwen Code：**固定复核 [`790bd83c2b1e3b242e0487d92183b053ceb44ed8`](https://github.com/QwenLM/qwen-code/commit/790bd83c2b1e3b242e0487d92183b053ceb44ed8)。当前 sandbox 文档/测试继续要求后端 admission 或验证失败不退回宿主执行；采纳该 fail-closed 行为，不复制其容器配置实现。
- **Gemini CLI：**固定复核 [`bedef96ef42905bd84a86dbec021c706168e7e2f`](https://github.com/google-gemini/gemini-cli/commit/bedef96ef42905bd84a86dbec021c706168e7e2f)。会话跟踪 private worktree 与实际 gitdir 的关系值得参考；其 grant 可按用户授权覆盖读或写，不是固定只读 Git 状态合同，因此不接入 ICODE 只读状态端口。
- **采纳/成本/验收：**采纳 OS 强制只读的元数据根、可信会话身份重核、固定 Git 参数、失败不回宿主；暂缓任何跨平台工具接线。ICODE Linux status 原型仍未进入 `ToolContext`，ARM64、恶意仓库、并发身份漂移、超时/超量清理及 macOS/Windows 等价负例仍是门槛；在通过前，所有 unsupported layout/platform 均保持 `git_broker_unavailable`。本轮只借鉴机制，不复制上游代码或新增第三方依赖。

## 2026-09-25 UTC 干净安装 wheel Git broker 闭环

- `scripts/run_native_wheel_ci.py` 现不只确认 wheel 内原生 helper 存在、可运行；完成隔离 venv 安装后，还用该 interpreter 执行 `scripts/probe_installed_git_broker.py`。探针只导入已安装 wheel 的 broker 与随包 Landlock helper，不从源码树导入实现、不在测试中重新编译 helper。
- 临时 fixture 创建私有源仓与 `WorkspaceManager` 分层 worktree，验证 modified/untracked 状态；为同一仓库配置 hostile fsmonitor/external-diff 脚本并确认未产生 marker。随后用普通 Git status 正向确认 hostile clean filter 在受控 fixture 中会运行，再确认 broker 在执行 status 前 fail-closed 拒绝配置且不触发 filter。
- 每次 broker 调用前后对 checkout、gitdir、common-dir 做不跟随链接的路径/类型/内容摘要对比，同时核对 index 与源仓 tracked file 未变；不会发布临时路径或仓库内容。断网策略必须为 DENY。
- 新测试本机 Linux x86_64：wheel 构建/检查、隔离 venv 安装、原 native-helper 负例、已安装 broker hostile-repo probe 全部 PASS；Git broker 定向模块 14 项 PASS。Linux ARM64 由新提交触发的原生 wheel matrix 待验证，macOS/Windows 不适用此 Landlock 原型。
- **TDD 上游修正：**Gemini CLI commit [`562f0361fe63952fcf2db793e3e9fc0ae69ec506`](https://github.com/google-gemini/gemini-cli/commit/562f0361fe63952fcf2db793e3e9fc0ae69ec506) 移除 `diff.external=''`，其回归测试说明空值会被 Git 当成执行空名称程序。ICODE 新增命令捕获测试先失败，再移除固定 status 参数中无关的 `-c diff.external=`；本机只读命令 `git -c diff.external= diff` 复现 exit 128。原恶意 external-diff status 回归保留；固定查询仍不执行 `git diff`。
- **采纳/暂缓与影响：**采纳“交付 wheel 必须真实调用状态 broker”和上述负例；没有复制任何上游代码、无新增运行依赖，新增 CI 时间仅包括临时仓库/wheel 内 helper 操作。暂缓模型工具接线：ToolContext 身份传递、并发 config/身份替换、超时/超量输出、ARM64 wheel 与所有非 Linux 等价边界尚未清零；`git_broker_unavailable`、automatic mode 和网络 DENY 不变。
