# Linux 会话工作区对象传递（2026-10-11）

## 范围与真实缺口

普通可写命令此前仅使用路径；资源包装和 scope 的 list 转换会丢失 PreparedCommand 元数据。复用现有资源监督链，不改变配额口径、网络策略或 Native 准入。

Session 是唯一工作区 FD 所有者，ToolContext 借用；dataclasses.replace 共享幂等所有者，防止副本关闭后另一副本误关复用的数字。关闭仍释放原工单租约。

Linux native 新增 `--workspace-object-fd FD DEVICE INODE`：冻结身份由宿主生成，helper 独立验证 FD、目录和设备/inode；旧 Reviewer `--workspace-fd` 仍仅允许只读。cwd 与 Landlock 规则引用保留对象，payload exec 时关闭目录 FD。

scope 保留 PreparedCommand 的 pass_fds/cwd；broker 合并工作区与两个私人控制通道，拒绝重号，不静默去重。真实 run_chain 各步骤持有同一 Session；自定义 adapter 维持旧调用合同。

## 并行研究与取舍

2026-10-11 只读核对：Codex `cc7ba33601286a751477832b01de7b6f8de0dd9c`（Apache-2.0）[FD 挂载校验](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/linux-sandbox/src/fd_mount.rs)；systemd v249.11 `5d125aae0cc9be0ac5abb8ab8e5081d27e1377a4`（LGPL-2.1-or-later）[scope 本地 exec 路径](https://github.com/systemd/systemd/blob/5d125aae0cc9be0ac5abb8ab8e5081d27e1377a4/src/run/run.c#L1406-L1551)。本机 systemd 249.11，发行版行为由真实资源链验证。

- 采纳：固定身份、清晰 owner/borrower、逐层保留继承元数据、接收端复核与 payload 前关闭。收益是消除二次路径授权；成本是一个 Session FD、身份验证和退出回收。
- 暂缓：换成 service/全局 FD store、复制 Rust/Node 实现或新增运行依赖。
- 不适配：仅凭 argv、结构测试或数字 FD 更新身份授予完整隔离信用；不宣称 Codex 普通可写根全部固定 FD。

未复制上游代码，没有新增许可证、安装步骤或权限依赖。

## 验证记录

新增会话/可写 native 正控先失败后通过；scope 元数据测试先失败后通过；副本 owner 测试先失败后通过。夹具首次非 Git 根含受保护 `.git`，保持保护规则，改用真实拆分 Git 布局。资源夹具曾引用错误测试装饰器/方法名，修正后实跑；v1 回执不提供正向 payload_started，保持 None，由实际生成文件证明运行，不修改生产回执语义。

- 固定 FD 模块：17 项通过、0 skip，含真实 writable Session→scope→broker→helper、允许写、FD 不进 payload、违规回执完整、资源 configured/terminal 完整及 scope collected；错误工单、外部关闭/数字复用、宿主包装后路径与 FD 同时替换和 broker 通道重号均拒绝；真实资源超时后 scope 回收且 Session FD 仍有效。
- 关联模块：130 项通过（此前 13 项 FD 加 quota/autonomy/session Git），0 skip。
- 扩大关联：176 项执行、164 项通过、12 项平台/环境 skip、0 failure/error（FD、isolation、engineering verification、control、execution binding pack）；其运行已加载此前 17 项模块，但未包含随后在同一资源测试内补充的 timeout 子向量，timeout 已由上面的独立 17 项最新运行覆盖。
- 工作区模块：62 项通过、0 skip；串行 compileall -j1、git diff --check、治理、网站和竞品排期检查通过。
- 独立只读审查：8 个实现/测试文件及最后新增的实际超时/替换负控均无阻断；首轮失败后的最新冻结源码原始完整 preflight 三道守护于 2026-10-11 05:47 UTC 确认终态 rc0，全量测试通过。原脚本成功时不打印测试数量，不虚构这次的实际计数。

首轮完整 preflight 在夹具修订前已加载模块，终态 2542 项/60 skip/1 error，539.519 秒：旧夹具仍调用不存在的 `wrap_resource_observed_command`。该夹具已改用真实 `wrap_command_with_resource_receipt`，最新 17 项通过；随后冻结源码重跑原完整 preflight，三道全通过。首轮失败保留记录，没有先提交绕过门禁。

边界：不证明 Windows/macOS 新能力、Linux 全策略覆盖、安装包 ARM 复验、真实模型全链或 90% SKILL 一致性。Landlock policy_contract_ready 保持 false。上一提交 c615d87 主 CI 两 Windows Reviewer 失败已定位为网络证据不足，尚未修复。

## 宿主绑定授权核对

本轮授权允许最小子仓契约修复。当前绑定入口已在子仓 d935a52 实现并发布，父仓 43e7739 已接线，当前固定 vendor 21566a5 包含该入口。避免重复新增接口；后续实际契约复验若出现额外缺口，仅在本授权范围内最小修复。

## 下一阶段输入：Windows 网络证明（只读研究，不属于本片实现）

独立观察 c615d87：[CI 38114149650](https://github.com/ayukyo/icode/actions/runs/38114149650) 44 jobs＝39 success/2 Windows Reviewer failure/3 skip；[provenance 38114149648](https://github.com/ayukyo/icode/actions/runs/38114149648) 5/5 success。零 capability 的文件拒绝与 ACL 清理已通过，网络仍 10035 等待超时；宿主 WFP ready/collection enabled/receipt valid，但无目标事件，CAB 缺 wfpdiag.xml，不能授予明确网络拒绝信用。

Microsoft [UWP 网络排障](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/troubleshooting-uwp-firewall)与 [IPC](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication)区分 capability 和同机 loopback exemption。现有 privateNetworkClientServer canary 固定 localhost，因此“加 capability 应连接本机成功”的前提不能成立；这是官方机制与源码的对照推断，不是新增 Windows 实测。

下一片仅考虑固定 errno/阶段诊断、已有 runner 权限下有界只读 [netsh wfp show netevents](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netsh-wfp)，以及专用目录内固定 wfpdiag basename 的实验。不得新增 loopback exemption、修改 WFP ACL/全局采集或防火墙规则；任意 XML、无目标事件、权限拒绝及超时均不视为通过。CAB 缺成员原因尚未确认。

## 架构级自检报告（本片）

- ✅ 语法/编译：真实 C -Werror、串行 Python 编译及完整 preflight 通过。
- ✅ 依赖/调用链：Session→ToolContext→scope→broker→helper 真实执行，独立审查无阻断。
- ✅ 逻辑/边界：错工单、FD 重用、路径替换、旧调用与 owner 副本均有覆盖。
- ✅ 异常处理：真实超时回收、无效身份启动前拒绝、重复关闭与租约释放验证通过；不称未测异常全部覆盖。
- ✅ 关联模块：工作区、autonomy、Git projection、资源与隔离关联通过。
- ✅ 兼容安全：旧无 FD 返回合同、自定义 runner 签名、readonly 旧参数及 readiness 保留。
- ✅ 可运行性：本机实际内核/资源执行通过；安装包与 ARM 新 FD 子门仍须后续实证，不称 R2/R3 全部完成。
