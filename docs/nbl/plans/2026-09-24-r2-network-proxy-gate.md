# R2.4 临时网络授权与代理门禁

- 日期：2026-09-24
- 状态：已新增 v2 host-only lease overlay（绑定默认 DENY 基线）、本机审批/HMAC/撤销 authority 契约及真实 socket 关闭测试适配器；没有生产代理或 OS 强制路由，自动模式保持默认断网
- 依据：[R2 正式设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §8、§14；[持续竞品对照](../../agent-landscape-live.md)

## 三问与现状

1. 真实问题：研发任务可能需要访问包源或指定服务，但模型命令不得获得宿主密钥、SSH 凭据或任意联网能力；到期与代理失效时必须立即停止授权。
2. 已有实现：`SandboxPolicy` 已定义精确 ASCII DNS 域名与 `PROXY_ALLOWLIST`，`tighten_policy()` 阻止默认 `DENY` 被普通候选策略拓宽。Linux 助手以 seccomp 拒绝新建 socket，macOS 实验策略只接受默认断网，Windows Job 不负责网络。模型 API 出网由宿主现有配置处理，**不等于**工具命令联网许可。
3. 影响链：用户确认 → 可信宿主签发当前会话的短时授权 → 平台强制工具命令只能到达代理 → 代理逐请求核对域名和期限 → 违规回执。模型、仓库配置与普通策略收紧接口均不能签发或延长授权。

## 分阶段出口

1. 先定义独立的 network lease：绑定 run/工单、精确域名、用途、单调时钟截止时间和代次；基础 `SandboxPolicy` 仍为默认断网。代理对每次新请求与存活隧道复核 lease；撤销、到期、宿主或代理重启后，旧连接必须关闭。
2. 先实现可验证的平台强制路由，再开放任何授权：Linux 使用隔离 netns 与可信桥接或等价的 OS 强制路径，不能仅移除现有 seccomp `socket` 拒绝；macOS Seatbelt 只能连精确的本机代理端点，不能调用旧 `wrap(network=True)` 的全网开放；Windows Job 本身不限制网络，须独立完成可验证的 Windows 网络边界。不支持时保持 `isolation_unavailable`，绝不回退直连。
3. 代理只接受固定协议与端口、精确域名；主机侧解析并拒绝 raw IP、loopback、私网、链路本地和保留地址，包括 DNS 变化与重绑定。跨域重定向、CONNECT/SOCKS 目标、UDS/宿主服务必须按同一授权边界处理；不得继承模型密钥或宿主认证材料。
4. 包安装、只读 Git fetch 与普通网页请求分别授权和验收；Git push 仍拒绝。仅在三平台真实负例和干净 wheel 路径通过后，才能把十项合同的 `network_temporary_allowlist` 标为通过。

## 并行开源研究取舍（2026-09-24）

- **选择性采纳：**[Codex 指定版本 Linux 沙箱](https://github.com/openai/codex/blob/282cd7b019378746cb87bd91a95d8b4bcae12aa3/codex-rs/linux-sandbox/README.md)在代理模式结合 netns、TCP→UDS→TCP 桥与 seccomp 阻断新 AF_UNIX/socketpair；[网络代理说明](https://github.com/openai/codex/blob/282cd7b019378746cb87bd91a95d8b4bcae12aa3/codex-rs/network-proxy/README.md)区分代理域名策略和本地/私网防护。ICODE 不复制其实现，先证明自身 Linux 助手可表达同等级 OS 强制边界。
- **选择性采纳：**[Gemini CLI 指定版本严格代理 Seatbelt profile](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/packages/cli/src/utils/sandbox-macos-strict-proxied.sb)仅允许特定本机代理端口出站，可作为 macOS profile 结构参考；端口与授权必须由 ICODE 可信宿主生成并双架构实测。
- **不直接采纳：**[Qwen Code 指定版本沙箱说明](https://github.com/QwenLM/qwen-code/blob/11c87ee7c27dbc98efd0f67bb82f19b027f3e610/docs/users/features/sandbox.md)的新 Linux 工具级模式不支持 `proxied`；其[示例代理脚本](https://github.com/QwenLM/qwen-code/blob/11c87ee7c27dbc98efd0f67bb82f19b027f3e610/docs/developers/examples/proxy-script.md)不能代替动态授权、私网 DNS 和到期清理的验收。

## 2026-09-25 源码复核与最小实施顺序

- 快照：ICODE `f6d95ea5680d3f4a78593b5a60ab699f2eb2fcba`；Codex `3e27195f2de00dc975b1db03440ade31b889d9b7`；Gemini CLI `87de0b6369f0466da37d9b3c0c9b77374bb59992`。Codex Linux 文档描述隔离 netns、TCP→UDS→TCP 代理桥、HTTP/SOCKS5 与域名/私网策略；它明确提示 DNS 重绑定不能仅靠初次解析时检查解决。[Codex netns/桥接](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/linux-sandbox/README.md) · [Codex 代理](https://github.com/openai/codex/blob/3e27195f2de00dc975b1db03440ade31b889d9b7/codex-rs/network-proxy/README.md)
- Gemini CLI 同一观察版本的 [macOS strict-proxied profile](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/packages/cli/src/utils/sandbox-macos-strict-proxied.sb) 默认拒绝出站，只允许连接本机代理端口；环境变量负责合作式路由，但 Seatbelt 才是“只能连代理”的 OS 门。[启动代码](https://github.com/google-gemini/gemini-cli/blob/87de0b6369f0466da37d9b3c0c9b77374bb59992/packages/cli/src/utils/sandbox.ts)
- ICODE 源码核对结论：`PROXY_ALLOWLIST`/域名列表此前没有 lease、审批或代理服务。现有 `NetworkLeaseAuthority` 会调用通用 `Approver`，以宿主进程随机 HMAC key 签发 lease，并按策略代次撤销；但没有执行接线、代理服务或 OS 路由。Linux seccomp 禁止 socket，不能由 syscall 层按 hostname 放行；macOS 新实验只实现 DENY，旧 `network=True` 是宽泛联网；Windows Job 无网络过滤，AppContainer 尚未通过创建进程门槛。因此静态策略、lease、authority 和 `HTTP_PROXY` 均不能标为联网能力已完成。Windows 未来的 WFP 路线需单独验证 [ALE 连接层](https://learn.microsoft.com/en-us/windows/win32/fwp/ale-layers)，而非假设 Job Object 管网。
- **阶段取舍：**先实现 Linux 单平台最小纵向切片：可信宿主签发短时、绑定 run/步骤/用途/精确域名/端口/单调期限与代次的 lease；工具网络命名空间仅可连接可信代理；代理按请求核对目标域名并绑定最终解析 IP；撤销/到期关闭既有隧道。仅支持 HTTP(S) 精确域名，不做通配符、SOCKS、UDP 或 raw IP。macOS/Windows 先继续 DENY，后续只有 seatbelt/WFP 等 OS 级“仅达代理”及失效关闭负例双架构通过后再开放。此为研发顺序而非缩减 R2 最终跨平台合同。
- **明确不可推断：**允许 Git HTTPS 域名不等于限制为只读 fetch；CONNECT 隧道内的 Git 方法不可见且凭据可能赋予写权限。未另行证明凭据隔离和协议层限制前，Git push 始终拒绝。

## 2026-09-25 NetworkLease 范围校验切片

- 新增 `src/icode/network_lease.py`：lease 是冻结的数据合同，匹配 run、工单、step 与 `SandboxPolicy.policy_hash`；只接受精确 ASCII DNS 名、当前仅开放 HTTPS 443；期限使用 monotonic ns，最长 15 分钟，并通过 generation 匹配支持撤销/替代代次检查。
- `NetworkLeaseAuthority` 调用通用 `Approver` 明示批准后，以本机进程随机 HMAC key 签名 lease；请求和签名均绑定完整 lease 字段。拒绝、审批错误、越权域名、待审批期间撤销、篡改、过期、重启和代次撤销均有标准库单测。key 不序列化且不传给 worker，但 Python 私有成员不防同进程恶意代码。
- `verify_request()` 是点时验证，不创建 socket、不运行代理、不修改 `SandboxPolicy`；它不能和未来连接建立形成原子事务，代理不得把这一方法单独当作连接许可。代理接入前仍须设计原子连接登记/撤销竞态，关闭到期与撤销时的活跃隧道，并完成 netns/桥接代理和真实内核负例。执行后端当前仍 fail-closed。

### 2026-09-25 NetworkLease authority 切片

- 本机 authority 只签发最长 15 分钟、最多 32 个精确域名、HTTPS 443 的范围租约；调用通用 `Approver` 前验证请求域名属于当前 policy，且只接受严格布尔 `True`。
- 撤销使用进程内策略代次；若审批等待期间发生撤销则拒绝签发。新建 authority 会有新 HMAC key，因此重启后不能验证旧租约。该实现是授权数据合同，不持久化审批、不创建 socket、不开放执行器网络。
- 同一进程内的 Python 代码访问边界不由 HMAC 私有成员保护；点时校验和真实连接也存在 TOCTOU 间隙。未来代理必须重新设计并测试连接登记与撤销的并发原子性，不能把本切片宣传为网络安全边界。

### 2026-09-25 活跃连接撤销生命周期切片

- `NetworkLeaseAuthority` 现提供内部 `register_active_connection()` / `release_active_connection()` 和 `close_expired_connections()`：注册在同一 authority 锁内完成租约、策略摘要、用途、目标及期限复核；撤销/到期将对应策略 scope 标为 revoking，可信 close callback 在锁外执行，只有返回严格的 `True` 才从登记表删除。清理失败时保持 fail-closed、拒绝新审批/连接，并允许后续 sweep 重试；新连接注册前也会先清扫已过期记录。
- 20 个 `tests.test_network_lease` 用例通过，覆盖撤销、自然到期、正常释放幂等、审批/清理并发、回调失败/非严格 True、重试和 scope 阻断。callback 不应包含或透出 socket 异常详情；等待并发 close 有 5 秒上限，避免未确认清理时误报成功。
- **边界：**registry 仅保存进程内可信代理提供的回调；本身不会建立 socket、验证 callback 是否真的关闭底层传输、运行定时线程、设置 OS 路由或接入模型/工具。未来代理仍必须周期性 sweep、在 connect 前原子登记其连接句柄，并实现 netns→TCP bridge、目的 IP pinning 与代理死亡处置；macOS/Windows 继续 DENY。故这只是消除 ICODE 授权状态模型中的部分并发缺口，不代表网络授权功能或 R2.4 通过。
- **上游采纳：**Codex `c98e263fb5365a512bb997a103d6ee8aa14c23e6` 的 netns/TCP bridge 与取消时关闭活动连接作为 Linux 架构/验收参考；Gemini CLI `bedef96ef42905bd84a86dbec021c706168e7e2f` 的 Seatbelt 仅放行本机代理及代理死亡停止进程组作为 macOS 候选；Qwen Code `790bd83c2b1e3b242e0487d92183b053ceb44ed8` 继续支持 backend 不可用时失败关闭。未复制代码，未增加依赖；观察与实现复核日期为 2026-09-25。来源详见[持续竞品对照](../../agent-landscape-live.md)。

### 2026-09-25 Linux pip-only 代理路线复核

- **Codex 架构快照：**固定于 `c98e263fb5365a512bb997a103d6ee8aa14c23e6`。代理命令运行在仅有 loopback 的 network namespace；可信 helper 把其中的 TCP listener FD 经 UDS 交给宿主 bridge，再连接宿主代理，不需要给工具建 veth/NAT。交接之后还要阻止不可信工具自行建立新 AF_UNIX/socketpair 通道。[设计说明](https://github.com/openai/codex/blob/c98e263fb5365a512bb997a103d6ee8/codex-rs/linux-sandbox/README.md#L81-L89) · [桥接实现](https://github.com/openai/codex/blob/c98e263fb5365a512bb997a103d6ee8/codex-rs/linux-sandbox/src/proxy_routing.rs#L75-L120) · [宿主 TCP bridge](https://github.com/openai/codex/blob/c98e263fb5365a512bb997a103d6ee8/codex-rs/linux-sandbox/src/proxy_routing.rs#L317-L389)。
- **ICODE 兼容性判断：**目标应是“仅 `pip install`，无需用户再装 bwrap/管理员改机”，而不是“纯 Python 且任意 Linux 主机必可运行”。ICODE 当前最低 Python 为 3.11；标准库 `os.unshare()` 从 3.12 才提供，内核命名空间能力仍可能受 host seccomp、AppArmor、配额等限制。[Python `os.unshare`](https://docs.python.org/3/library/os.html#os.unshare) · [Linux user namespaces](https://man7.org/linux/man-pages/man7/user_namespaces.7.html) · [namespace quotas](https://docs.kernel.org/admin-guide/sysctl/user.html)。建议复用 ICODE 随 wheel 分发、按架构构建的可信 native helper 路线；受支持主机建立 netns 失败时必须在目标命令启动前拒绝，不能关闭 seccomp、请求 privileged 或退回直连。Codex 随 CLI 携带 Bubblewrap，但 ICODE 不应因此额外要求用户安装它；若以后分发 bubblewrap 二进制，须另审 LGPL-2.0-or-later 义务。[Codex Linux sandbox](https://github.com/openai/codex/blob/c98e263fb5365a512bb997a103d6ee8/codex-rs/linux-sandbox/README.md) · [Bubblewrap license header](https://github.com/containers/bubblewrap/blob/f8e1e5077eb8613ca559bac0d422282a910015d6/bubblewrap.c)。
- **采纳 / 暂缓与验收：**选择性采纳 netns→UDS FD 交接→宿主 TCP bridge、代理逐请求核验精确 HTTP(S) 域名/端口并把解析 IP 绑定实际连接；暂缓 veth/NAT、通配符/SOCKS/UDP 和代码复制。验收必须覆盖授权域名可达、无代理/namespace 创建失败/代理死亡 fail-closed、清理代理环境变量或 `NO_PROXY=*` 后的 IPv4/IPv6/DNS/UDP/loopback/私网/未授权直连负例、DNS 变化与重绑定，以及撤销/到期关闭现存隧道。Codex 因宿主权限不足而 skip 的集成测试不能算 ICODE 通过；另需受限 CI 负例明确断言目标命令未启动。[Codex proxy tests](https://github.com/openai/codex/blob/c98e263fb5365a512bb997a103d6ee8/codex-rs/linux-sandbox/tests/suite/managed_proxy.rs#L90-L142) · [Docker seccomp 限制](https://docs.docker.com/engine/security/seccomp/)。Codex 为 Apache-2.0，未复制代码；当前 ICODE lease/connection registry 仍不实现上述桥接或 OS 网络边界。

这些是固定版本源码/官方文档观察，不是上游运行时实测；`HTTP_PROXY` 仅为合作式客户端提供路由信息，不构成安全边界。

## 必须先红后绿的负例

- raw IPv4/IPv6、localhost/loopback、RFC1918、链路本地、保留地址、DNS 重绑定、跨域重定向与非法 CONNECT/SOCKS 目标；HTTP、HTTPS、DNS、UDP、UDS 和直接 `connect()` 均不能绕过。
- 代理宕机、授权撤销/到期时，已有隧道和新连接都关闭；不同 run/工单不能借用同一个授权；子孙进程不能比父进程有更大网络能力。
- 代理进程、环境变量、回执和沙箱文件均不泄露模型 API key、SSH key、浏览器凭据；启动失败绝不裸执行。
- Linux x64/ARM64、macOS Intel/Apple Silicon、Windows x64/ARM64 的原生负例和干净 wheel 安装复测分别通过。

本计划只固定安全门禁，不把 `PROXY_ALLOWLIST` 数据结构误报为已经支持临时联网。

## 2026-09-27 上游网络到期路径复核

- **Codex 当前源码：**观察 `main` 固定 SHA [`7f6c0f9387a0a60f396f61cc58f6b38bc98f2473`](https://github.com/openai/codex/commit/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473)，Apache-2.0。Managed Seatbelt 可只放行本机代理端口；代理策略逐请求决策，scope shutdown 会关闭 HTTP keep-alive、CONNECT 与 SOCKS 活动连接。但这证明的是 scope 生命周期清理，不是租约 TTL 自动过期清理；缺少强制 managed 配置时也不能笼统声称缺代理必定断网。
- **Gemini CLI 当前源码：**观察 `main` 固定 SHA [`2fe7c2d3f065dc40ad573d50b2091116f8a4aa18`](https://github.com/google-gemini/gemini-cli/commit/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18)，Apache-2.0。严格代理 Seatbelt 默认 deny，仅开放本机代理端口，代理退出可停止 sandbox 进程组；未发现按单一租约期限关闭 keep-alive 隧道的证据。
- **ICODE 现状：**`NetworkLeaseAuthority` 仍只是授权数据与活跃连接登记接口；没有生产 socket caller、代理服务、周期 sweeper 或 OS “仅到代理”路由。macOS 不接受 `PROXY_ALLOWLIST`，Linux/Windows 也未形成租约到内核强制边界的生产路径。当前状态不得因上游机制或 lease 单测改变。
- **采纳 / 暂缓：**采纳 OS 强制只到可信固定代理端点、代理逐请求检查精确授权、代理退出终止进程组作为故障兜底；暂缓把静态本机代理端口当成到期授权，禁止依赖 `HTTP_PROXY`/`NO_PROXY`。真正开放前还须证明过期/撤销同时关闭已建立连接并取消进行中的连接、过期后复用与新连接均拒绝，以及代理死亡无直连回退；DNS 私网/重绑定、IPv4/IPv6/UDP/loopback 绕过与两架构原生验证仍是门槛。上游仅作架构参考，未复制实现、无新增许可或依赖。详情见[持续竞品对照](../../agent-landscape-live.md)。

## 2026-09-27 当前主线复核与下一垂直切片

- **基线：**ICODE `17c7b95b8b565643ab61da63ca103076c72632de`；刷新时间 2026-09-27。生产 `src` 中 `NetworkLeaseAuthority` 无调用方；点时 lease 校验与回调 registry 不创建代理/socket，也没有生产周期 sweeper。基础策略仍为 `DENY`，网络能力未向 Agent 开放。
- **上游刷新：**Codex `main` SHA [`7f6c0f9387a0a60f396f61cc58f6b38bc98f2473`](https://github.com/openai/codex/commit/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473)，Gemini CLI `main` SHA [`2fe7c2d3f065dc40ad573d50b2091116f8a4aa18`](https://github.com/google-gemini/gemini-cli/commit/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18)，均 Apache-2.0。Codex scope shutdown 测试可借鉴真实 keep-alive/CONNECT/SOCKS 双端 EOF/reset 验证，但没有据此推断租约 TTL；Gemini 的 fixed loopback Seatbelt 和代理退出后停进程组也不等于 lease 到期语义。
- **采纳 / 暂缓：**先实现 Agent 不可调用的本机真实 socket 生命周期垂直切片：用宿主 scope 绑定现有 lease authority，在真实双向连接上测试 revoke/自然到期的关断与后续请求拒绝；候选 policy 保持 `DENY`，本片不打开执行网络、不更改自动模式。待此语义稳定，再独立实现各平台 OS 强制“只到可信代理”与 bypass/native/wheel 验收。不采纳仅靠 `HTTP_PROXY`/`NO_PROXY` 的软限制，也不以 callback 的布尔返回充当 socket 已关闭证明；不复制代码、不引入依赖。
- **验收边界：**测试需用真实 client/upstream sockets 观察双方在约定期限内 EOF/reset，覆盖到期、显式 revoke、过期后连接复用/新请求拒绝，以及 revoke 与建立连接并发；失败清理必须保持 scope 阻断和 worker fail-closed。该垂直切片不等于 DNS 私网/重绑定、IPv4/IPv6/UDP/loopback 旁路防护，也不代表 Linux/macOS/Windows 网络边界已通过，R2 最终门槛保持原样。

### 2026-09-27 真实 TCP socket 生命周期切片

- **实现：**`NetworkLeaseAuthority.register_active_sockets()` 仅接受非空、精确类型的标准 socket tuple，且每个 socket 必须是已连接的 IPv4/IPv6 TCP stream；以 `SO_TYPE` 和 `getpeername()` 验证，拒绝监听、未连接和 UDP socket。注册前快照并校验底层 fd 均打开且唯一，拒绝以两个 Python wrapper 共用同一 fd 的输入，避免重复关闭和误伤复用后的描述符。authority 随后 `dup()` 并持有独立 descriptor 副本，撤销/过期回调对副本执行 shutdown/close，避免调用方 detach 原 wrapper 后令底层连接逃过关闭确认。注册失败时关闭已创建副本。
- **本地验收：**`tests.test_network_lease` 25 项通过。真实 loopback TCP 用例验证 revoke 与显式 expiry sweep 后 peer 收到 EOF；另外验证共享 fd wrapper 被拒绝、注册后 detach 原 wrapper 仍无法阻断 revoke，以及监听/未连接 TCP 和 UDP（含已连接 UDP）均被拒绝。新增负例均先按预期失败，再实施对应收紧。Python 3.11.15 下完整 `scripts/preflight.py` 的密钥扫描、子模块完整性与 unittest 三道守护通过；站点、治理、竞品对照校验、107 个 Python 文件 AST 解析和 `git diff --check` 通过。对应的平台 CI 步骤已加入，尚待远端矩阵运行。
- **严格边界：**这不是 HTTP/TCP relay 或生产代理，也不让 Agent/worker 获得网络权限；没有后台 sweeper，expiry 仍由显式调用触发。双 TCP 对只证明登记 socket 的关闭会传至 peer，不证明真实流量转发、DNS/IP 策略、expiry 后新请求拒绝、连接建立竞态或 OS 路由；调用方必须是可信宿主，且注册期间不得并发修改原 wrapper。网络基础策略保持 `DENY`，macOS/Windows 网络继续关闭。
- **下一步：**等待 Ubuntu/macOS/Windows（含现有 x64/ARM runner）模块 CI 与独立 socket 生命周期复审；之后把 lease registry 接入真实宿主代理 scope，测试过期后复用/新请求拒绝、连接进行中撤销与失败清理重试，再单独做 Linux netns→可信桥接和其他平台强制“只到代理”门禁。上述缺口未通过前不得开放联网或宣称 R2/R2.4 完成。

### 2026-09-27 默认 DENY 上的 host-only lease overlay

- **问题与设计：**原 schema v1 要求静态 `PROXY_ALLOWLIST` 并把 lease 域名约束到候选 `SandboxPolicy.allowed_domains`；普通工单基线为 `DENY`，而 `tighten_policy()` 正确拒绝普通候选扩大权限。改为 schema v2 的宿主授权 overlay：仍绑定原始 deny-only policy hash、run/ticket/step；租约自身持有经审批的精确 ASCII DNS 域名、用途、443、单调期限与代次，不写入或改写候选策略。仅允许 `network_mode=DENY` 且 `allowed_domains=()` 的策略签发/校验 overlay，其他 mode/静态域名组合 fail-closed。无效 IP literal/hostname 在审批 UI 调用之前拒绝。策略收紧逻辑未修改。
- **本机证据：**对“DENY 工单可申请指定域名租约”和“非法目标/非 DENY 策略拒绝”新增两项先红后绿测试；`tests.test_network_lease` 28 项在 Python 3.11.15 通过。还覆盖租约 schema v1 语义被拒绝、policy hash/身份绑定、撤销代次、真实双端关闭和已知负例。文档更新后 `scripts/preflight.py` 的密钥、子模块与全量 unittest 三道守护通过；`check_governance.py`、`check_site.py`、`check_agent_landscape.py` 与 `git diff --check` 均通过。
- **远端边界：**GitHub [CI #226](https://github.com/ayukyo/icode/actions/runs/36271940621) workspace-platforms 3 项 job 均完成成功，含 `tests.test_network_lease`；整轮 CI 的 macOS native-probe 步骤已先成功退出，之后 `Verify policy command broker` 步骤失败。conformance `6/10` 是评分、不是此处失败根因；详细日志受匿名访问限制，不能据摘要解释断言。新 overlay 尚需随主线下一轮 CI 验证。
- **严格边界与后续：**overlay 不是 sandbox permission，不会令 DENY 命令联网。还没有 HTTPS CONNECT handler、可信 DNS 解析和数值 IP pinning、pending DNS/connect 的原子撤销、周期 TTL timer、隧道 idle reuse 拒绝、worker 停止机制或任意 OS 网络强制；没有向 Agent 暴露 localhost listener。下一垂直切片只能先实现宿主拥有的本机 fake-upstream CONNECT scope，覆盖批准/拒绝、IP 分类/pinning、建立中撤销、TTL 与双端 EOF；OS “仅到代理”门独立验证后才可能接线，R2 网络合同和自动模式继续关闭。

### 2026-09-27 HTTPS 目标 DNS 校验原语

- **基线与目的：**基线 `f544187197798b6877fa8ab9e5890f4e350bb79a`；先实现本机 fake-upstream CONNECT scope 的安全前置条件，不把授权 overlay 暴露给 Agent。只处理 hostname 到数值 TCP sockaddr 的校验，不在本切片拨号或启动代理。
- **上游采纳：**复核 Codex `main` SHA `06f97622f8529feef0d230fc37519c36c6bb2eeb` 的 IP 检查后以同一数值地址连接机制；Gemini CLI `main` SHA `2fe7c2d3f065dc40ad573d50b2091116f8a4aa18` 作为严格代理 profile 参考，不采纳其示例代理为 IP 安全实现。两项目根许可证 Apache-2.0；只借鉴机制，不复制代码/引入依赖。
- **实现契约：**`src/icode/network_destination.py` 的 `resolve_public_tcp_targets()` 限定精确 ASCII DNS 名与 HTTPS 443；对原始域名先作 ASCII 检查再转小写，拒绝 Kelvin 等会折叠为 ASCII 的 Unicode 字符；先拒绝 raw IP/localhost/非法名/端口，再以 TCP 参数调用系统 `getaddrinfo`。仅 resolver 入参添加根尾点，避免本地 search suffix 改写获批目标。只要 A/AAAA 中一项不是全局可达 IPv4/IPv6、属于保留或特殊用途、IPv4-mapped、scoped、非 TCP 或 malformed，整批拒绝；返回可直接用于 `socket.connect()` 的规范化 numeric sockaddr，重复项去重。安全分类要求 Python ≥3.11.10、≥3.12.4 或 ≥3.13；官方 `ipaddress` 文档及 3.12.4 发布说明记录了较早版本的 `is_global`/`is_private` 误判修正。
- **本机验收：**11 项 helper 测试覆盖 IPv4/IPv6 数值 sockaddr、禁止字面 IP 和 Kelvin 变体在 DNS 前失败、绝对 resolver 名、任一非全局地址导致整批失败、HTTPS 端口、旧分类表版本门、作用域/mapped/多播/文档网段地址、坏 DNS 记录、默认 resolver 注入和错误脱敏；策略与租约模块一并定向测试共 92 项通过。所有测试均使用注入 resolver，不执行真实 DNS 或外网请求。独立只读复审及完整 preflight 仍须通过后才提交。
- **未实现 / 后续：**该 helper 不核验 lease、不建立 socket、不是网络 permission；没有 HTTP CONNECT 请求解析、真实 connector、地址 pinning 调用点、DNS resolve cancellation、pending connect 注册/撤销原子性、自动 TTL timer、既有隧道 revoke/expiry、listener 生命周期或 OS 限制。未来调用者必须在 DNS 前授权、连接时使用检查返回的同一 sockaddr，并在连接建立期间重新核验租约/撤销 generation。当前 R2 网络、自动模式与所有 worker 仍保持 fail-closed。

### 2026-09-27 HTTPS CONNECT request-head parser 切片

- **上游采纳与来源：**Codex `main` 固定 SHA [`7f6c0f9387a0a60f396f61cc58f6b38bc98f2473`](https://github.com/openai/codex/commit/7f6c0f9387a0a60f396f61cc58f6b38bc98f2473) 的 Rama CONNECT 路径可参考独立 handler 结构，但未见 CONNECT 上 443/Host/CL/TE 的本地严格限制；Gemini CLI `main` SHA [`2fe7c2d3f065dc40ad573d50b2091116f8a4aa18`](https://github.com/google-gemini/gemini-cli/commit/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18) 示例做 CONNECT/443 检查但未做 Host/framing/IP pinning。两者根许可证 Apache-2.0；只采纳独立入口的设计，不复制代码或引入依赖。[RFC 9110 §9.3.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.6) 与 [RFC 9112 §3.2.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-3.2.3) 作为 HTTP 语义参考。
- **实现合同：**`src/icode/connect_request.py` 只解析完整原始 bytes header block，不处理 socket。必须是 `CONNECT host:443 HTTP/1.1` 精确三段、CRLFCRLF 结束、总长 ≤16 KiB；ASCII DNS hostname 规范化后与唯一 Host 一致，Host 可省略默认端口或明确 `:443`。拒绝重复/缺失 Host、其他全部 header（包括 CL/TE、授权头、Connection 等）、userinfo、raw IPv4/IPv6、zone、Unicode、路径/查询/fragment、畸形行、尾随数据和非 443。拒绝错误为通用信息，不包含输入值。
- **本机验收：**8 项 `tests.test_connect_request` 覆盖大小写规范化、Host 默认/显式 443、authority/Host 混淆、ASCII/Unicode/IP/zone/userinfo/端口、HTTP method/version、重复/缺失 Host、CL/TE/额外头、CRLF/折叠/控制字符/尾随字节、超长 block、字节与头数上限边界以及拒绝信息不回显输入；新增测试先以缺少模块失败，再以未实现桩让两项正向合同按预期失败，随后实现后全绿。`tests.test_connect_request` 与 DNS/policy/lease 模块合计 100 项通过，无 DNS/TCP/公网请求。Python 3.11.15 下完整 `scripts/preflight.py` 的密钥扫描、子模块完整性与全量 unittest 三道守护通过；`check_agent_landscape.py`、`check_governance.py`、`check_site.py`、`git diff --check` 通过。独立静态复审无 Critical/Important，边界与拒绝文本的 Minor 覆盖项已补测，可提交。
- **边界与兼容性：**纯 parser 不证明连接层正确读满一块 header、不管理 asyncio 超时/分段/limit、delimiter 后缓冲区或提前到达的隧道数据；不核验 lease、做 DNS/拨号、创建 listener 或开放 worker 网络。当前只接受 Host 头，可能拒绝携带 User-Agent/Proxy-Connection 的客户端；后续只有在确有客户端兼容需求时，才经实测添加明确、不会转发给目标的安全头白名单。CI #228 总体失败与本切片无关的原生门结果见[持续竞品对照](../../agent-landscape-live.md)。

### 2026-09-27 host-side 到期租约自动回收组件

- **问题与范围：**`NetworkLeaseAuthority.close_expired_connections()` 原来只在可信调用方显式 sweep 或登记新连接时执行；如果宿主 scope 空闲且不再有新请求，已登记的到期连接可能一直保留。新增显式生命周期组件 `NetworkLeaseExpiryMonitor`：由可信 host owner 单次启动专用 daemon thread，使用单调时钟立即 sweep，之后默认每 100 ms（可配置 10 ms–1 s）重试；停止最多等待 5 秒并返回是否退出。Authority 自身仍不隐式创建线程。
- **失败语义：**close callback 未确认时 authority 原有的 `revoking` 保护保持生效；monitor 只保留活动登记并在下一轮重试。监视器只记录固定的 `connection_cleanup_failed` 健康类别，不记录异常文本。启动间隔拒绝 bool、非有限、超界与超大整数，monitor 实例不可重复启动。
- **本机验收：**5 项 `tests.test_network_lease_monitor` 覆盖真实 loopback peer 在 TTL 后读到 EOF、一次关闭失败后重试成功、敏感错误内容不进入健康状态、周期/单次生命周期边界与停止超时。平台 lease CI runner `scripts/run_network_lease_ci.py` 已包含 authority 与 monitor 两套测试；本机 runner 34 项通过，完整 `scripts/preflight.py` 的密钥扫描、子模块完整性和全量测试三道门通过；macOS/Windows CI 需新提交后验证。
- **研究与取舍：**Codex `main` [`985cf47a`](https://github.com/openai/codex/commit/985cf47a4eb6084b2ff6b30ebdb1216acda85bb4)、Qwen Code 0.24.6 [`e471cfe6`](https://github.com/QwenLM/qwen-code/commit/e471cfe6cdd1eb151d3bb870ffa8658f0e497033) 与 Gemini CLI [`2fe7c2d3`](https://github.com/google-gemini/gemini-cli/commit/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18) 固定源码均为 Apache-2.0。**采纳**Codex 的 scope 生命周期关闭真实连接思路和实 TCP 两端 EOF 作为验收形式；**暂缓**任何上游代理实现直抄，也不将 scope shutdown 等同 lease TTL timer。Qwen/Gemini 示例仍按 hostname 拨号或只提供静态 sidecar，未显示本项目所需的租约撤销和 IP pinning。无代码复制与新增依赖。
- **严格边界：**该组件尚未接入已提交的 CONNECT handler、生产 proxy lifecycle、任何 worker/Agent/ToolContext；本地测试连接只使用 loopback，未访问公网。100 ms 是轮询间隔，不是硬实时截止；最坏回收时间还包含 close callback 耗时。它不取消同步 DNS/阻塞 connect、不建立 listener/relay、不阻止子进程绕过代理，也不替代 Linux netns、macOS Seatbelt 或 Windows WFP “只能到代理”门。基础策略保持 `DENY`，R2 网络、自动模式与工具入口继续关闭。

### 2026-09-26 UTC：CI #230 lease 关闭断言跨平台修正候选

- **观测事实：**CI #230 的 Actions annotation 在 macOS workspace 与 Intel native job 都报告 `test_revoke_closes_socket_after_original_wrapper_detaches` assertion failure；ARM native lease job 未报失败。完整 traceback 需登录才能访问，故目前只确认失败用例，不确认失败断言位置和值。
- **候选与研究：**该测试在 `revoke()` 后仅进行一次 non-blocking `recv(1)`；Python 官方 socket 文档说明非阻塞操作无法立即完成时会得到平台相关错误，Apple `shutdown(2)` 只定义本地收发关闭，不保证远端 EOF 同步可见。单次读取时序竞态是候选原因，不是已证实根因。[Python socket timeout/non-blocking](https://docs.python.org/3.11/library/socket.html#notes-on-socket-timeouts) · [Apple shutdown(2)](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/shutdown.2.html)
- **处理与验收边界：**断言改为设置 5 秒 socket timeout 并等待 EOF，生产 socket lifecycle 未改。本机定向用例通过；必须等新的 macOS/Windows/Linux CI 再判断此候选是否成立。若仍失败，先取得完整 traceback，不放宽权限、不改变关闭失败处理。R2 网络能力仍保持关闭。

### 2026-09-27 host-only pending connect promotion 与取消

- **问题与方案：**已登记的连接条目此前只能维持单一 close callback，不能原子地从“连接尝试取消/唤醒”转换为“已连接 socket 关闭”。新增 `NetworkLeaseAuthority.promote_active_connection()` 与显式 `pending=True`：只有 pending entry 可升级，且在 authority 锁内确认 entry 仍存在、未 closing/revoking、租约未早发/过期、generation 未变化，然后替换为 connected-socket close callback 并一次性转为 connected。重复或并发二次 promotion、以及已登记的 connected socket 均拒绝；失败时必须由 connector owner 自行关闭候选 socket，且不能发布给调用方。它只管理连接生命周期，不创建或路由连接。
- **本机验收：**首次缺少 promotion API 的回归测试按预期失败后通过；重复 promotion 与并发双 promotion 负例证明仅一个 close owner 被保留；pre-issue clock 负例先红后绿。`tests.test_network_lease` 使用 backlog=1 的 loopback listener 构造真实仍 pending 的非阻塞 `connect_ex`，每次分别由 revoke 与 expiry callback 通过 `socketpair` 唤醒 owner；owner 自己关闭 socket并确认后，promotion 结果为 false、不能发布。另用真实已建立 loopback TCP pair 与屏障覆盖“连接已就绪、尚未升级/发布”时 revoke 获胜。测试不访问 DNS 或公网；本机 `scripts/run_network_lease_ci.py` 的 authority+monitor 44 项全过、0 skip。完整 preflight 及跨平台新 CI 待本轮提交后验证。
- **研究与取舍（2026-09-27，固定上游快照）：**Codex `985cf47a4eb6084b2ff6b30ebdb1216acda85bb4`（Apache-2.0）以 scope cancellation 传播停止并对真实 peer 检查 EOF/reset，但其公开 lifecycle tests 在撤销前已完成 connect，没有证明 pending connect 可被中断；采纳 scope 取消传播与真实 socket 验收纪律，不夸大上游证据。[Codex lifecycle](https://github.com/openai/codex/blob/985cf47a4eb6084b2ff6b30ebdb1216acda85bb4/codex-rs/network-proxy/src/connection_lifecycle/service.rs) · [测试](https://github.com/openai/codex/blob/985cf47a4eb6084b2ff6b30ebdb1216acda85bb4/codex-rs/network-proxy/src/connection_lifecycle/lifecycle_tests.rs)。Gemini CLI `2fe7c2d3f065dc40ad573d50b2091116f8a4aa18`（Apache-2.0）的 Seatbelt 只到 localhost proxy 是独立 OS 路由门，不代替连接生命周期。[profile](https://github.com/google-gemini/gemini-cli/blob/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18/packages/cli/src/utils/sandbox-macos-strict-proxied.sb)。Qwen Code `e471cfe6cdd1eb151d3bb870ffa8658f0e497033`（0.24.6，Apache-2.0）明确 Linux `proxied` 不支持，采纳其失败关闭语义，不复制示例代理。[sandbox](https://github.com/QwenLM/qwen-code/blob/e471cfe6cdd1eb151d3bb870ffa8658f0e497033/docs/users/features/sandbox.md)。
- **严格边界与下一步：**这组测试在 tests 内实现 owner/wakeup harness，不是 production connector，也没有把 lease hostname 与测试使用的 loopback sockaddr 做 DNS/IP 绑定；它验证真实 pending 的非阻塞连接生命周期，不声称另一线程 `close()` 能打断同步阻塞 `connect()`。无已接入 listener/relay、无 worker/Agent/ToolContext 网络调用；Linux/macOS/Windows OS 级“只能到代理”路由、DNS pinning 调用链、CONNECT 双向 relay 与平台新 CI 均未通过。下一步把该 promotion/cancel contract 接到可信 host-side CONNECT scope，并用已校验的数值 sockaddr 作为真实目标；全程保持 worker 网络默认 DENY。未复制上游代码、未加运行依赖。

### 2026-09-27 UTC：CONNECT 授权到 numeric DNS target 绑定

- **实现范围：**新增 `src/icode/leased_connect.py` 的 `resolve_leased_https_connect_targets()`。它先复用严格 request-head parser；在任何 resolver 调用前，以 host-side `NetworkLeaseAuthority.verify_request()` 检查签名、deny-only policy hash、run/ticket/step、purpose、精确 hostname/443、期限和 generation；随后调用现有 `resolve_public_tcp_targets()`；DNS 返回后再按当前单调时钟复核租约，撤销或到期即丢弃所有解析目标。成功只返回冻结结构，其中地址为既有 helper 已校验的 numeric sockaddr，未来 connector 不得再次按 hostname 解析。
- **TDD 与本机验收：**新增 11 项先红后绿测试，覆盖有效租约返回数字地址、签名错误/过期/撤销/无效请求/未授权域名/错误用途/策略身份不符均在 DNS 前拒绝，以及 DNS 期间撤销、过期和私网答案均不返回目标。`tests.test_leased_connect` 11/11 通过并连续 20 轮通过；平台 lease runner authority+monitor+CONNECT 共 55 项通过。Python 3.11.15 Linux x86_64 下无依赖 wheel 构建/隔离安装后成功导入此模块。本片没有打开公网连接或创建任何 socket。
- **CI #243 复核与测试 harness 校正：**[CI #243](https://github.com/ayukyo/icode/actions/runs/36302118672) 中 Linux lease job 与 Python 3.11/3.12 完整测试 job 通过；Windows 与 macOS lease job 的 3 个集成测试在 `resolve_public_tcp_targets()` 的安全 patch-floor 检查处返回 `Python runtime is too old for safe IANA special-range classification`，导致 mock resolver 尚未调用。这是测试直接沿用各 runner 的系统 patch 版本，而生产 helper 按安全表版本 fail-closed；不是目标地址分类不通过。phase13 将测试中 `_supports_safe_ipaddress_classification` mock 为 True，仅用于隔离 lease→DNS 编排语义；真实最低版本门由 `tests.test_network_destination.test_rejects_runtime_with_stale_ipaddress_special_range_tables` 独立覆盖。不得修改生产 floor 放宽支持；修正后跨平台 CI 尚待新 run。
- **只读上游研究：**Codex `main` SHA `8f195c93d7e7acfef95acf273f0e49cce917e291` 的 CONNECT policy 检查 numeric `SocketAddr` 并连接同一数值目标，可防检查后重新解析；其真实生命周期测试覆盖已建连接关闭，但没有本项目所需的 lease TTL/generation。Gemini CLI `2fe7c2d3f065dc40ad573d50b2091116f8a4aa18` 展示 strict macOS profile 只放行 loopback proxy；示例代理按 hostname 连接。Qwen Code `8a170d7e45c65deece8ffa66768ff9fad6c39c0f` 当前 sandbox 只开放/关闭网络，不支持 proxied mode。ICODE 采纳“授权/host policy 先于 DNS、检查并连接同一 numeric 地址”和不支持时拒绝；不复制 Rust/JS 代码，不增加依赖。精确链接、证据边界、成本及日期见[持续竞品对照](../../agent-landscape-live.md)。
- **严格限制与后续：**系统 `getaddrinfo` 是同步阻塞操作，本函数不能取消正在进行的 DNS；二次 lease 校验只确保解析后不把已撤销/到期结果交给调用者。校验完成与未来登记 pending connection 之间也不是原子许可，因此返回值不是网络 permission。此模块不拨号、不启动 CONNECT listener/TLS/双向 relay、不暴露给 Agent/ToolContext、不改变基础 `DENY`。下一片应实现 host-owned、非阻塞 numeric-sockaddr connector：先在 authority 登记 pending/wakeup，再 connect_ex 到相同数字地址，复核并 promotion 后才发布；同时覆盖撤销/到期与候选 socket 关闭。OS “只能到代理”仍独立阻断 R2 网络开放和自动模式。
