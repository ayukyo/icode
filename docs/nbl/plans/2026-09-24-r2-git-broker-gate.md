# R2.4 分层工作区 Git 状态代理门禁

- 日期：2026-09-24
- 状态：调用链与风险已确认；只读状态端口尚未接入模型，完整 R2 仍阻断
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

## 先红后绿验收

- 恶意仓库配置包含 fsmonitor、外部 diff、filter、hook、credential helper；只读状态不得启动它们，不得读取或写入宿主敏感路径。
- 查询前后对工作树、Git 管理目录、index、锁文件及原仓做不跟随链接的身份与内容检查；正常、错误、超时路径均不产生越权写入或残留子进程。
- 分层 worktree、中途删除或替换 `.git` 指针、无效会话、跨任务路径、符号链接/重解析、空格和非 ASCII 文件名，以及模型注入 `-c`/`--git-dir` 均须 fail-closed。
- Linux x64/ARM64 与 macOS/Windows 对应架构在独立安装后验证；不具备等价隔离的系统不开放该端口。

本计划仅固定后续实施与验收门禁，不改变任何当前能力声明。
