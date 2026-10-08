# R3 工作台验证计划接线：只读预研

观察日期：2026-10-09 Asia/Shanghai。本仓基线 `3ef4ecd7b4854985202e39704c8efa9e2c1be22b`。独立只读研究已回报，根另核下述本仓调用点及两份固定上游接口/许可；这是设计输入，不是实现、运行或 R3 验收结果。

## 已有实现与真实缺口

`cli.cmd_workbench` 在 `--enable-autonomous` 时构造 `NativeChainExecutor`，但没有传入 `verification_plan_provider`（`src/icode/cli.py:708-753`）。执行器在正式 `code/deepcheck` 步骤缺 provider 时返回 `verification_plan_required`，现有 provider 接口为 `(ExecutionContext, SandboxPolicy) -> VerificationPlan`，身份绑定仍核 run/ticket/root/step（`src/icode/autonomy.py:122-267`）。因此不用另造模型循环或测试执行框架，缺的是受信任宿主的计划工厂及入口接线。

现有 `VerificationPlan/VerificationCheck`、解释器身份和同策略工程检查可以复用；已有孤立 Python unittest 参数模板不需要增加 Python 包依赖（`src/icode/engineering_verification.py:48-78` 及 [软件模板计划](../plans/2026-10-08-r3-python-isolated-template.md)）。模板存在不等于默认工厂已接上，也不保证任意语言项目能用它测试。

正式工程前置门还有平台限制：`runner._contract_plan_error` 会检查资源通道，`tools.builtin._uses_resource_dispatch` 当前只接受 Linux + Landlock + 网络 DENY/空 domains；其它平台的 `require_resource` 会在命令启动前拒绝（`src/icode/runner.py:1450-1476`、`src/icode/tools/builtin.py:619-653`）。接上 provider 不会自动关闭 macOS/Windows 原生工程门。

## 必须保留的状态语义

“单个研发步骤在 CP/模型前拒绝坏计划”与“点击开始后没有任何状态写入”不是同一保证。当前 start 先打开工作区/租约，再持久化 starting；worker 会写 running，执行器每步先 `safe_point`，然后取得 policy/provider（`autonomy.py:578-674,703-760,172-227`）。这些状态用于审计；不能把现有单步前置检查宣传成整个 intent 零写入。若将来要求后者，必须单独设计 intent 前冻结和生命周期，不是加一个 closure 就完成。

当前 CLI 的 `isolation_level=enforced` 只看 real/policy-ready/wrap_policy；工作台 capability enabled 依 executor/WorkspaceManager，而不包含 provider 或工程资源就绪（`cli.py:733-761`、`workbench.py:337-398`）。普通用户可能把“已启用”误读成研发检查已准备好。后续设计需明确区分配置、可启动与实际执行就绪，兼容既有自定义 executor，不通过改标签授予执行权限。

## 固定上游与借鉴决策

这次只复核两个相关机制，不声称刷新其 HEAD 或完整20名单。

| 项目与固定源码 | 实际机制 | ICODE 决策 |
|---|---|---|
| Aider `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`：[测试配置参数](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/args.py#L537-L547)，[Apache-2.0](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/LICENSE.txt) | 存在 test-cmd 与 auto-test 的显式预配置入口 | 采纳“测试配置先于自动执行”的机制；不据参数存在证明测试质量或替代 ICODE 宿主授权 |
| Codex `fe50d010e203a9b8dda2c7737d7d8e4a80e6ab44`：[Windows 后端权限检查](https://github.com/openai/codex/blob/fe50d010e203a9b8dda2c7737d7d8e4a80e6ab44/codex-rs/sandboxing/src/windows.rs#L42-L115)，[Apache-2.0](https://github.com/openai/codex/blob/fe50d010e203a9b8dda2c7737d7d8e4a80e6ab44/LICENSE) | 后端不能兑现所请求权限时显式拒绝，不默默裸跑 | 采纳启动前能力匹配；这是邻近机制，不是宿主测试计划实现，不照搬特权后端 |

收益：复用既有计划和资源门，让小白不需要理解 argv，同时保留真实失败反馈。成本：宿主工厂、入口/显示配对接线、身份漂移与生命周期回归，以及真实 Linux 工程往返。只借机制，不复制上游源码，不新增许可分发、依赖或系统权限。

暂缓：非 Python 工程的宿主配置形态、自动安装依赖、任意自定义命令、其它平台原生通道、resume 原始基线恢复及真实模型六步/90%验收。它们需要各自明确合同，部分仍有用户选择/权限边界，不能从自然语言工单推断。

不适配：浏览器、项目文件、模型答复或工单 JSON 直接授权命令；用空测试或 FakeBackend 往返获得工程质量信用；把隔离名称、模板匹配或配置 enabled 等同原生执行通过。

## 下一设计的可验证项

- 受信任工厂复用内置模板，计划 root/run/ticket 来自真实 session/policy；浏览器不传 argv/env/root。
- 错身份、工具/环境漂移、缺资源通道在对应 CP step_start 和模型调用前拒绝；intent 层的工作区和审计写入另行如实计量。
- 默认 provider 接线与 CLI/UI 就绪显示相互一致，不误伤既有自定义 executor；非适用项目明确“需准备检查”，不猜命令或暗中安装依赖。
- 真实往返须实际宿主测试、结果 tree、新鲜独立 Reviewer、CP/evidence 保存和独立验包；软件模拟与目标原生/模型六步分开记录。

本次没有修改上述生产入口，没有运行测试、模型、原生探针或 CI。研究者指定搜索后端不可用时使用官方固定源码回读；没有更改系统配置，也不把工具缺失当作实现通过。
