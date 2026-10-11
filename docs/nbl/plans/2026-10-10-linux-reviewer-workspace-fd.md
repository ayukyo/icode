# Linux Reviewer 固定目录对象

开始日期：2026-10-10；验收日期：2026-10-11。基线：`1b53bc1`，vendor `21566a5`。状态：本机阶段验收通过，待提交与远端验证。

## 缺口与最小实现

`ToolContext` 已有固定 Reviewer 目录句柄生命周期，但 Landlock 后端没有对应入口；原生助手按路径重新打开授权根。固定对象是后续完整只读 Reviewer 接线的前置能力，不可用路径字符串或模型声明替代。

复用 `PinnedWorkspaceRoot`、`PreparedCommand` 和原进程监督。提取 Bubblewrap 现有目录固定函数供两个后端使用；Landlock 的只读 wrapper 接受可选 `workspace_fd`，在宿主侧核对目录对象与路径，保留精确 FD 启动合同。旧无 FD 调用仍返回原列表。

原生助手新增只读专用 `--workspace-fd`：拒绝重复参数、非目录、失效或错根句柄、与控制通道的别名及可写模式；只保留固定目录与原可信通道，设置目录 FD 的 CLOEXEC。初次路径/对象核验后，cwd 使用 `fchdir`，Landlock 授权使用该 FD 的 `/proc/self/fd` 引用，避免授权与 cwd 二次解析到不同对象。PID 监督、资源协议、网络策略不变。

目录替换发生在初次核验前时拒绝；在核验与 cwd/规则安装之间替换时仍授权原固定对象，新对象不可读。这不是阻止宿主修改或冻结目录内容，后续 snapshot/tree 校验仍不可省略。

## 验证记录

- 两项正控先真实 RED：宿主固定入口不存在，原生参数未知；之后 GREEN。
- 当前模块八项通过，含真实原生读取、exec 后目录 FD 不可见、写入/外部读取拒绝、替换对象拒绝、错误 FD 与重复/可写参数拒绝、旧 API 返回合同。
- 竞态负控在独立编译驱动中仅替换 `fchdir` 调用点，在原生对象核验后更换路径对象；原授权、cwd、Landlock 与 payload 均真实运行，证明原对象可读而替换对象不可列举。不把故障注入称为自然发生的竞态。
- 新驱动首次编译失败：系统头先于 `_GNU_SOURCE`；仅修正测试驱动头顺序后八项通过。该失败不改写为生产源码 RED。
- 新模块与旧 mapless/resource 通道合计 53 项通过；更广隔离/监督回归 127 项、11 环境跳过、0 失败。完整原始 preflight 的密钥、子模块和全量 unittest 三道全部通过；治理检查通过。
- 独立只读审查 `/root/review_observer_preparation` 核对模型前 pin、FD 启动、原生复验、cwd/授权一致、exec 关闭和 finally 关闭的调用链，无阻断发现。本片尚未取得已安装 wheel 或 Linux ARM64 的新源码运行证据。

## 并行研究与边界

独立只读研究及 Linux 调用链审计已返回。官方依据沿用持续对照已记录的 Codex `36650394`（Apache-2.0）[Linux helper](https://github.com/openai/codex/blob/36650394c5b38c2990ccf2a3457165ca3e9d9726/codex-rs/linux-sandbox/src/landlock.rs)、[denial 分类](https://github.com/openai/codex/blob/36650394c5b38c2990ccf2a3457165ca3e9d9726/codex-rs/sandboxing/src/denial.rs)及 [Landlock audit](https://docs.kernel.org/admin-guide/LSM/landlock.html) 原记录；网络失败，本轮没有新的上游 HEAD 核验，不称最新源码。采纳：固定对象并统一 exec 前准备与后续清理；暂缓：不具备逐任务直接来源的文件拒绝观察；不适配：把文本推断或特权审计服务当无特权内核回执。没有源码复制、新许可义务或依赖变化。收益是消除本片路径二次解析，成本为一项原生参数及明确 FD 生命周期；真实正负控见上节。

审计确认现有资源/违规双通道已经接入真实工具链，不能重复实现。下一片需贯通普通可写上下文的固定根；同时覆盖 `ToolContext` 各策略 wrapper 的 `list(...)`、scope 包装和 resource executor 的 pass_fds 合并，否则未来的 PreparedCommand 元数据会丢失。这些分支不用于本片只读启动，必须在扩展前补独立负控。

本片不增加子目录排除、Reviewer 配额通道或网络租约能力，不提供 `wrap_read_only_policy_excluding`，不把 `policy_contract_ready` 改为 true。策略化 Reviewer/Native 自动模式仍拒绝。完整 Reviewer、统一违规回执、Windows/macOS、真实模型六步与 R2/R3 总验收继续未通过。未改子仓库，不触碰其中用户文档工具改动；未增加权限、依赖或安装步骤。

## 架构级自检报告（本片）

- ✅ 语法/编译：真实 C `-Werror` 编译、八项定点和完整 preflight 通过。
- ✅ 依赖/调用链：宿主 pin、PreparedCommand、原生参数、cwd/规则及关闭逐层核对，独立审查无阻断。
- ✅ 逻辑/边界：错根、替换、核验后竞态、错误/重复 FD 与旧无 FD 调用通过。
- ✅ 异常处理：无效输入拒绝且负载未启动；pin 失败关闭句柄，宿主 finally 保留关闭所有权。未覆盖范围不称全覆盖。
- ✅ 关联模块：mapless/resource 回归和隔离/监督关联回归通过；普通策略 FD 接线留待下一片。
- ✅ 兼容安全：旧返回合同、Bubblewrap 固定函数语义及 readiness 保留；无新权限或依赖。
- ✅ 可运行性：本机 x64 真实内核路径通过；随包、ARM64 与完整 Reviewer 尚未证明，不称跨平台 100%。
