# R2.4 分层工作区 Git 状态代理门禁

- 日期：2026-09-24
- 状态：调用链与风险已确认；严格 porcelain v2 解析器及 Linux Landlock 独立只读元数据授权基座已通过本机测试，均未接入模型或启动 Git；broker 与完整 R2 仍阻断
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

### 独立格式审查修正（2026-09-25）

- 上游 Git 回归用例确认 `git add --intent-to-add` 会产生合法 `.A` 状态；解析器现接受该组合，并以真实 Git CLI 输出回归。[Git 上游用例](https://github.com/git/git/blob/master/t/t7064-wtstatus-pv2.sh#L1934-L1953)
- mode 字段由“任意六位八进制”收紧为已知类型集合 `000000`、`040000`、`100644`、`100755`、`120000`、`160000`，保留删除与 sparse-index 目录模式并拒绝 `777777`；依据 [Git 数据模型](https://git-scm.com/docs/gitdatamodel)与[索引格式](https://git-scm.com/docs/index-format)。
- 仍忽略格式有效但未知的 `# ` 扩展头；拒绝空头、`#` 后无分隔符或重复空白的畸形头。测试同时验证合法模式集合、`.A`、畸形头及损坏记录 fail-closed。
