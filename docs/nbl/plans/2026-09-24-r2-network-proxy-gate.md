# R2.4 临时网络授权与代理门禁

- 日期：2026-09-24
- 状态：已新增 v2 host-only lease overlay（绑定默认 DENY 基线）、本机审批/HMAC/撤销 authority 契约、真实 socket 关闭测试适配器及 Linux native loopback-only namespace probe；没有生产代理或 OS 强制路由，自动模式保持默认断网
- 依据：[R2 正式设计](../specs/2026-09-23-r2-cross-platform-isolation-design.md) §8、§14；[持续竞品对照](../../agent-landscape-live.md)

## 2026-09-27 10:45 UTC 最新推进：Linux loopback-only namespace probe

- **并行只读研究：**Codex `openai/codex@67a709665ac7b50311b93e32612c9a8281684787`（Apache-2.0）的 Linux sandbox 有 netns loopback TCP listener、host bridge、SCM_RIGHTS FD handoff 与按 socket family 限制 seccomp；其直接相关测试仍不足以证明 managed-proxy 完整旁路防护。Codex README 对 AF_UNIX/socketpair 的概述与此 SHA 源码不同：源码保留 `socketpair()` 供本地 IPC。Gemini CLI `2fe7c2d3f065dc40ad573d50b2091116f8a4aa18`（Apache-2.0）通过 Docker/Podman 网络与代理容器，不适配本项目无额外容器运行时的 pip-only 约束。精确证据与链接见[持续竞品对照](../../agent-landscape-live.md)。
- **采纳 / 暂缓：**采纳 netns、loopback-only 和 seccomp socket family/type 约束作为后续 FD bridge 的基础；暂缓真实 bridge 与策略开放，未复制代码、未新增运行依赖。本地 `unshare --user --map-root-user --net true` 仅作主机能力预检，不代替原生子进程测试。
- **实现状态：**native helper 增加仅供原生探针调用、未接入 `LandlockSandbox`/`SandboxPolicy`/Agent 的 `--network-loopback-only` 模式。它创建 user/PID/network namespaces，在丢弃能力前仅启用新命名空间的 `lo`；子进程 seccomp 仅允许 IPv4/IPv6 TCP stream `socket()`（protocol 0 或 TCP），保持 `io_uring_setup` 拒绝；UDP、raw 及 AF_UNIX `socket()` 被拒。两个模式中的 `socketpair()` 都仅允许 AF_UNIX stream/datagram/seqpacket，protocol=0，作为本地 IPC；其他 family/type/protocol 由 seccomp 拒绝。默认生产 DENY 路径不传新 flag，拒绝全部 `socket()`，并施加同一 `socketpair()` 本地限定；`NetworkMode.PROXY_ALLOWLIST` 仍由策略入口拒绝。
- **先红后绿与本机证据：**真实进程测试先因 helper 不识别新选项失败，再通过。后来新增 `socketpair()` 限定回归，先因 seccomp 未检查 family/protocol、由内核返回 `EOPNOTSUPP` 而失败，再修复通过。验证 netns 标识与宿主不同、IPv4 loopback TCP（protocol 0 与显式 `IPPROTO_TCP`）可双向通信、宿主 127.0.0.1 服务不可达、IPv4 TEST-NET-3 以 `ENETUNREACH` 失败、IPv6 TEST-NET 返回网络不可达/不支持错误、UDP/协议错配/AF_UNIX `socket()` 以 `EPERM` 失败；AF_UNIX 三种本地 pair 可通信，而其他 family/type/protocol 以 `EPERM` 拒绝；重复开关在命令启动前返回错误。默认 DENY 原生 probe 另外验证 IPv4/IPv6 TCP、UDP、AF_UNIX `socket()` 均被拒，且 socketpair 只开放有效 AF_UNIX 本地 IPC。C `-Werror` 构建、PID namespace/mapless 15 项、定向 probe 3 项通过；完整 `scripts/preflight.py` 三道门通过，Linux wheel 构建、隔离安装及运行态探针全部通过。独立复核为 0 Critical / 0 Important，曾指出的显式 TCP 正向测试缺口已补入并复验。
- **当前验收结果：**`scripts/run_native_probe_ci.py` 的进程树清理、保护路径、默认网络 DENY 均实测通过，但 R2 conformance 只有 7/10，`critical_passed=false`、`ready=false`；临时网络 allowlist、资源限制、统一违规处理仍为未验证。因此这只是 loopback namespace 基础切片，不能宣称 R2 网络/自动模式通过。新提交后的跨架构 GitHub CI 仍待运行。
- **严格边界：**netns+本地 loopback 不提供 host bridge、listener FD handoff、CONNECT proxy、lease/域名授权、DNS/IP pinning、expiry/revoke 的双端关闭或 ToolContext 调用链。它只证明本机该 helper 模式没有外部路由且宿主 loopback 不可达；不能标为 OS“只到代理”通过，也不开放临时网络、工单自动模式或 R2/R3。Linux x86_64/ARM64 线上验证仍待推送后的 CI。

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

### 2026-09-27 UTC：host-owned nonblocking numeric CONNECT connector

- **范围与调用顺序：**新增 `open_authorized_https_connection()`，只作为可信宿主侧单目标连接原语：严格解析 CONNECT head → lease 校验 → 复用既有公网上游地址校验/解析 → DNS 后重新校验 → 对每个已校验数值 sockaddr 创建 TCP socket → 在 authority 锁保护下登记 pending close/wakeup callback → `connect_ex()` → selector 等待并用 `SO_ERROR` 判定 → 再次校验租约并原子 promotion → 才返回连接对象。未新增 listener、CONNECT 成功响应、TLS、双向 relay、worker/Agent/ToolContext 或任务网络工具调用链。
- **TDD 与本机验收：**连接器测试先于实现落地并按预期失败，随后通过。13 项 connector tests 覆盖未授权域名在 DNS 前拒绝、私网 DNS 结果不建 socket、DNS 后撤销不拨号、过期清理回调跨越租约期限后 `connect_ex` 完全不调用、同一 numeric sockaddr 原样拨号、pending 先于 `connect_ex` 且 promotion 先于发布、selector 可写必须检查 `SO_ERROR`、authority revoke 唤醒 pending selector owner 并由 owner 关闭 socket、已连接 loopback upstream 在 revoke 后关闭、连接失败关闭候选/清理登记，以及 `KeyboardInterrupt` 传播前关闭目标 socket 和 wakeup pair。两个失败路径分别先红后绿：promotion 后清理关闭全部临时 descriptor；中断异常不会绕过 pending cleanup。
- **独立复审发现与修复（2026-09-27）：**复审确认 `register_active_connection()` 在同步 `close_expired_connections()` 执行回调后继续使用调用方传入的旧 `now_monotonic_ns`，可能在新 lease 已到期后仍发起 outbound dial。新增回归先按旧注册行为失败，直接记录 socket `connect_ex()` 是否被调用；修复为 pending 注册必须提供受信任的单调时钟回调，并在清理回调完成后、authority 锁内重新采样与验证，缺少回调/回调异常/无效值都 fail-closed。CONNECT connector 传入 `time.monotonic_ns`；已连接 socket 注册入口也可透传同一回调。补齐时钟回调异常与 bool/负数/浮点返回值回归；`scripts/run_network_lease_ci.py` 在 Python 3.11.15/3.12.13 各 71/71 通过；13 项 connector 单测连续 20 轮通过；两解释器下 `scripts/preflight.py` 的密钥、子模块与全量 unittest 三道门均通过。此为本机 Linux 验收，新提交的跨平台 CI 尚待执行。
- Python 3.11 从 tracked snapshot 与本地 connector source 构建 wheel、无依赖隔离安装并在仓库外成功导入。所有 connector loopback 仅连本机，不访问公网。
- **撤销并发模型：**单个拨号调用线程拥有候选 socket 和 selector；其他线程不调用 `close()` 或 `unregister()`，仅置持久 cancel flag 并写入非阻塞 socketpair，selector owner 唤醒后自行退出 selector、关闭候选并确认。成功路径在 authority 锁内原子更换 pending callback 为已连接 socket callback；未 promotion 的连接绝不返回。同步系统 DNS 本身仍不可物理取消；DNS 返回后重验只保证迟到目标不进入拨号。close 未确认时 lease authority 保留 revoking/active 条目并 fail-closed，清理失败可能阻断该 scope 的后续授权。
- **只读上游研究（观测 2026-09-27 07:35:54 UTC）：**Codex [`8f195c93d7e7acfef95acf273f0e49cce917e291`](https://github.com/openai/codex/commit/8f195c93d7e7acfef95acf273f0e49cce917e291)，Apache-2.0，连接器消费已解析 `SocketAddr`，使用 Tokio `TcpStream::connect`；RAII future-drop 对连接中断的解释是从 Tokio/源码结构作出的机制推断，不能当作 OS 连接中断保证。公开 lifecycle 测试使用真实 TCP 检查代理停止后的双侧 EOF/reset，但建立这些连接后才触发 shutdown，没有直接覆盖 pending dial 的 lease revoke。[connector](https://raw.githubusercontent.com/openai/codex/8f195c93d7e7acfef95acf273f0e49cce917e291/codex-rs/network-proxy/src/connect_policy.rs) · [lifecycle tests](https://raw.githubusercontent.com/openai/codex/8f195c93d7e7acfef95acf273f0e49cce917e291/codex-rs/network-proxy/src/connection_lifecycle/lifecycle_tests.rs)。Gemini CLI [`2fe7c2d3f065dc40ad573d50b2091116f8a4aa18`](https://github.com/google-gemini/gemini-cli/commit/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18)，Apache-2.0，代理退出路径会终止 sandbox 进程组，但所查生命周期测试使用 mock，未证明宿主 pending TCP 拨号撤销。[sandbox lifecycle](https://raw.githubusercontent.com/google-gemini/gemini-cli/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18/packages/cli/src/utils/sandbox.ts)。Qwen Code [`76c3dc5be6b3e22c8827dd1f72d7998e9a752678`](https://github.com/QwenLM/qwen-code/commit/76c3dc5be6b3e22c8827dd1f72d7998e9a752678)，Apache-2.0，该固定版本 bwrap contract 只接受 `open/closed`，未展示 CONNECT pending cancellation。[bwrap backend](https://raw.githubusercontent.com/QwenLM/qwen-code/76c3dc5be6b3e22c8827dd1f72d7998e9a752678/packages/core/src/sandbox/bwrap-execution.ts)。ICODE 采纳 numeric address 复用、真实连接/关闭验收纪律与不支持时拒绝；不复制代码，不增加运行依赖。
- **平台机制与代价：**Python `connect_ex()` 配合 `DefaultSelector` 的可写事件及 `SO_ERROR` 查询可区分完成/失败；Windows selector 只支持 socket，因此 wakeup 使用跨平台 `socketpair()` 而不是 pipe。Linux 文档明确被另一线程关闭的 watched fd 行为未定义/可能不唤醒；故撤销线程不跨线程关闭目标 socket。见 [Python connect_ex](https://docs.python.org/3.11/library/socket.html#socket.socket.connect_ex)、[selectors](https://docs.python.org/3.11/library/selectors.html)、[socketpair](https://docs.python.org/3.11/library/socket.html#socket.socketpair)、[CPython selector connect completion](https://github.com/python/cpython/blob/3.11/Lib/asyncio/selector_events.py#L594-L636)、[Linux select(2)](https://man7.org/linux/man-pages/man2/select.2.html) 与 [Winsock closesocket](https://learn.microsoft.com/en-us/windows/win32/api/winsock/nf-winsock-closesocket)。每个并发 pending dial 使用当前调用方 owner thread（本连接器不另建线程）及一对临时 socket；调用方在同步拨号期间保持阻塞。单个地址的拨号最多等待 10 秒、selector 最多每 100 ms 轮询一次、revoke 等待 owner 确认最多 4 秒；超时仍按 authority 失败关闭处理。
- **严格验收边界：**本地集成连接只使用 loopback；不得访问公网。即使本连接器测试全绿，也不能证明跨平台 runner、生产代理 listener/relay、DNS 物理取消、自动 TTL lifecycle 接线、OS “worker 只能访问代理”路由、TLS 内只读语义或 R2 `network_temporary_allowlist` 通过。自动模式和 Agent/worker 网络保持关闭，直到 Linux/macOS/Windows 的操作系统负例分别通过并完成上层代理生命周期集成。

### 2026-09-27 host CONNECT scope 与租约生命周期

- **实现范围：**新增 host-only `HostConnectRuntime` / `HostHttpsConnectScope`，把现有签名 lease、numeric CONNECT connector 与 expiry monitor 组合起来。每个 runtime 仅持有一个 authority-wide monitor；scope 在 DNS 前登记被信任宿主接收的 client socket，复用 connector 对已校验 numeric sockaddr 的拨号，并只关闭本 scope 的连接，不撤销同一 policy 下的兄弟 scope。expiry sweep 逐连接关闭过期/代次失效项，不误关仍有效的 sibling lease。同步 DNS 不能物理取消；scope close 会关闭 client、设置取消标志、拒绝迟到 DNS 结果及后续拨号，存在未结束操作时 shutdown 返回未完成并保持 monitor 运行，调用方必须在操作返回后重试。
- **TDD 与本机验收：**实现前缺失 scope 测试先红；新增真实 loopback 两侧关闭、revoke/expiry 后拒绝后续 DNS、兄弟 scope 隔离、pending numeric connect 唤醒并由 owner 关闭等行为测试。authority 到期 sweep 的 sibling 保活与到期期间 sibling 正常 release 各自先红后绿；release 竞争用事件屏障确定性阻塞过期连接的 close callback。20 轮重复测试曾揭示原 backlog 测试中 `connect_ex` 可能在撤销断言前完成；现增加屏障固定在真实 pending 状态，并确认相关 scope/release 用例连续 20/20 轮通过。Python 3.11.15 定向网络三套测试 63/63 通过；CPython 3.11.15 与 3.12.13 的 `scripts/run_network_lease_ci.py` 均为 74/74 通过；Linux native wheel CI 与新 scope 模块隔离安装导入通过；当前 Python 3.11.15 全仓 preflight 正在复验。`ruff` 未安装，未记为通过。
- **审查修复：**独立复审发现 expiry sweep 为一条过期 lease 设置 policy revoking 标记时，也阻断同 policy 活跃 sibling 的 `release_active_connection()`；正常 scope 会丢弃已关闭 sibling 的本地所有权，导致 authority entry/duplicate FD 残留。现仅由该 entry 自身的 `closing` 状态阻止 release；policy revoking 继续拒绝新审批、校验及注册，但不阻止已经关闭的 owner handle 释放。新增屏障测试确认 live peer 正常 EOF、该 handle 被删除、过期条目仍按 sweep 关闭且 authority 无残留。runtime 遇同步 DNS 时 `close() == False` 的重试责任已写入 API docstring；没有自动重试/完成通知。
- **上游只读研究（观察 2026-09-27 09:46:51 UTC，固定快照）：**Codex `main` `67a709665ac7b50311b93e32612c9a8281684787`、Gemini CLI `main` `2fe7c2d3f065dc40ad573d50b2091116f8a4aa18`，均 Apache-2.0。Codex execution-scope drop 会使策略 token 失效并拒绝尚未授权的决策，但所查代码/测试未证明既有 CONNECT 在 scope drop 时关闭；runtime shutdown 生命周期测试另有活动 CONNECT 双端 EOF/reset 证据，不能外推成逐 scope revoke 或 TTL。[scope token](https://github.com/openai/codex/blob/67a709665ac7b50311b93e32612c9a8281684787/codex-rs/network-proxy/src/proxy/execution_scope.rs#L3-L51) · [pending decision](https://github.com/openai/codex/blob/67a709665ac7b50311b93e32612c9a8281684787/codex-rs/network-proxy/src/proxy.rs#L1017-L1069) · [runtime shutdown lifecycle test](https://github.com/openai/codex/blob/67a709665ac7b50311b93e32612c9a8281684787/codex-rs/network-proxy/src/connection_lifecycle/lifecycle_tests.rs#L57-L172)。Gemini 管理 sandbox/proxy 进程生命周期；所查测试使用 mock handler，不证明活动 socket 双端关闭、DNS/connect 取消或 per-lease TTL。[sandbox lifecycle](https://github.com/google-gemini/gemini-cli/blob/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18/packages/cli/src/utils/sandbox.ts#L314-L395) · [proxy cleanup](https://github.com/google-gemini/gemini-cli/blob/2fe7c2d3f065dc40ad573d50b2091116f8a4aa18/packages/cli/src/utils/sandbox.ts#L928-L1029)。
- **采纳 / 暂缓与硬边界：**采纳 Codex runtime-owned cancellation 和真实 peer EOF 的验证方式；逐 lease expiry/generation、同 policy sibling 隔离是 ICODE 自有合同。Gemini 仅采纳 owner 生命周期思路，不视作 socket revoke 方案。未复制源码、无新增依赖。scope 仍无生产 listener、CONNECT response、TLS 或双向 relay，也未接 Agent/ToolContext、自动模式或 OS 网络后端；测试中手动传送数据仅作活跃 socket 控制，不是产品转发。Linux/macOS/Windows OS 级“只能到可信代理”仍是开放门槛，worker 网络默认 `DENY`。

### 2026-09-27 12:46 UTC：Linux loopback listener FD receiver

- **实现切片：**新增标准库-only `linux_proxy_handoff`，建立带 `SO_PASSCRED` 的私有 AF_UNIX/SOCK_SEQPACKET 控制通道；host receiver 限时接收并核验直接子进程 PID、固定消息、唯一 SCM_RIGHTS descriptor、IPv4 TCP listening socket、非零端口和 loopback 地址。通过 `MSG_CMSG_CLOEXEC` 接收，返回 socket wrapper 不可继承；selector 支持高于 1023 的 fd，recv 使用 DONTWAIT 处理多 reader 竞争，所有拒绝/中断路径关闭收到的 descriptor。
- **中断窗口复现与修复：**独立复审指出 `recvmsg()` 成功返回 raw ancillary bytes 到 FD 所有权登记之间可被 SIGINT 打断。新增真实 listener + `os.kill(SIGINT)` 回归：旧实现 FD alias 从 1 增为 2；修复在短暂非阻塞接收及 ancillary 解析/登记区间屏蔽该线程可屏蔽信号，恢复原 mask 后由外层 finally 清理；新回归通过。Python 官方 3.11 文档说明 `recvmsg()` 只有在自身抛异常时才尝试关闭 SCM_RIGHTS descriptor，`pthread_sigmask()` 可暂存当前线程信号，不能据“recvmsg 有异常清理”覆盖成功返回后的 Python 所有权窗口：[recvmsg](https://docs.python.org/3.11/library/socket.html#socket.socket.recvmsg) · [pthread_sigmask](https://docs.python.org/3.11/library/signal.html#signal.pthread_sigmask)。
- **研究取舍：**沿用此前固定 Codex 源码观察 [`41f9084b`](https://github.com/openai/codex/commit/41f9084b30812db321a0b592def4f500d1e79cf4) 的“netns loopback listener 经私有 Unix channel 交到 host bridge”机制；采纳 FD 类型/地址/来源与生命周期校验，不复制 Rust 实现或加依赖。12:46 UTC 阶段末在线复核 GitHub main 未能取回（GitHub 页面受限、`git ls-remote` TLS 握手失败），故该 SHA 仅作已固定参考，不标成当前最新。
- **本机验收与状态：**receiver 与 native probe CI 单元测试 20/20、compileall、diff check、`preflight.py --only tests` 及 `--only submodule` 通过；本次三份 Python 文件的限定密钥形态扫描无命中。CI #248 workflow overall Success，但其 4 条 Python `::error` 注解来自刻意验证失败分支的 mock 测试输出；现已在测试中捕获 stdout 并保留负例断言，新 CI 仍待提交后确认。独立复审第三轮待回报。
- **严格边界：**本切片没有建立 netns sender/listener、host bridge/relay、lease CONNECT 调用、授权或 Agent/ToolContext 网络入口；仅是 FD receiver 原语。新跨平台 CI、Linux x64/ARM64 runner receiver 测试、端到端受控流量和 OS“只能到代理”仍未验收，网络基础策略保持 `DENY`，自动模式关闭；不得作为 R2 完成证据。

### 2026-09-27 13:45 UTC：SIGINT 所有权窗口修订

- **撤回上一版方案：**12:46 UTC 记录的“短临界区屏蔽/延迟主线程信号”并未覆盖主线程上的 `os.dup()` 返回交接窗口；独立复审以真实 handoff + 同步 SIGINT 注入复现 FD alias 从 1 增至 2。基于该证据，上一版实现不再作为可提交候选。
- **当前实现：**主线程只负责等待专用 daemon worker；worker 独占 `recvmsg()`、ancillary 解析、FD 登记、`os.dup()`、socket 包装和 loopback/TCP 校验。等待期间若调用方 signal handler 抛异常，主线程记录首个异常并发出取消；worker 的 selector 最多每 50ms 检查取消，收齐并关闭本地 FD/socket 后结束，主线程 join 完再传播原异常。所有 Python signal handler 保持调用方原状；非主线程调用直接执行原语。
- **平台依据：**Python 3.11.16 官方文档说明 Python signal handler 总在主解释器线程执行，即使信号由其他线程收到；handler 抛出的异常也在主线程异步引发。故把拥有 SCM_RIGHTS 和 dup 生命周期的代码移出主线程，比逐一替换并恢复进程级 handler 更易审计。[signal：handler 执行线程与异常语义](https://docs.python.org/3.11/library/signal.html#signals-and-threads)。文档另说明 `recvmsg()` 仅在自身抛异常时尝试关闭收到的 SCM_RIGHTS descriptor，成功返回后的所有权仍由应用负责：[socket.recvmsg](https://docs.python.org/3.11/library/socket.html#socket.socket.recvmsg)。
- **回归证据：**真实 `os.dup()` 之后同步发送 SIGINT、并等待主线程 handler 确认再放行 worker，30 次独立运行均通过；recvmsg 返回后 SIGINT、跨线程 SIGINT、自定义抛异常 handler 均验证取消/join 后没有 descriptor alias 残留。receiver/native-probe 两模块 24/24 通过；`preflight.py --only tests`、`--only submodule`，治理/站点/竞品文档校验、`compileall`、`git diff --check` 和限定六个变更文件的密钥形态扫描通过。独立复审及远端 CI 尚未完成；不可报告该 slice Ready。
- **竞品采纳修订：**Codex 固定源码观察仍仅作架构机制参考；其私有 Unix FD handoff 机制采纳，不复制代码。本次 worker/cancel/join 是针对 Python 信号语义及 ICODE FD 所有权合同的本地实现选择，不宣称 Codex 使用相同内部策略。该修订不实现 sender、bridge/relay、lease 接线或 Agent 网络权限，R2 网络 `DENY` 与自动模式关闭。

### 2026-09-27 14:10 UTC：worker cleanup signal 修订

- **复审问题与 TDD 修复：**精确树复审指出 finalizer 中 `cancellation.set()` 位于保护区外，第二个 signal 可能跳过 join/FD 关闭；另一个异常也可能在 cleanup 的 `except BaseException` 中被吞。新增两条确定性回归，先在旧实现上分别复现未交付 socket 泄漏及 `KeyboardInterrupt` 被吞，再将取消设置、join、socket 关闭纳入重试清理循环，并在正常返回的 cleanup signal 下保留首个异常；两条均转绿。
- **当前测试证据：**receiver/native-probe 定向套件 26/26；真实 `os.dup()` 后 SIGINT 回归连续 30 次通过；仓库 `.venv` Python 3.11.15 的完整 `preflight.py --only tests` 和子模块完整性门禁通过，治理/站点/竞品校验、compileall、diff check 与限定六个变更文件的密钥形态扫描通过。首次误用系统 Python 3.10.12 得到失败；该版本不满足 `pyproject.toml` 的 `requires-python >=3.11`，不将其作为项目测试结果。最终精确树独立复审、commit 后 CI 仍待完成。
- **安全边界不变：**该修订只加强本地 FD owner 的信号清理；不能证明 worker 子进程隔离、sender/bridge/relay、CONNECT 策略接线、跨平台兼容或 OS 级“只能到可信代理”。网络 `DENY` 与自动模式关闭。

### 2026-09-27 14:25 UTC：调用方上下文与 worker startup 中断

- **TDD 复审修复：**独立复审发现 `sys.exc_info()` 可能看到 caller 的外层 `except`，不是 receiver 自己的失败；新增实际 SCM_RIGHTS+loopback 回归，旧实现返回 `None`，改为显式追踪本函数异常后通过。另模拟 `Thread.start()` 已抛出但 `ident` 尚未发布，再放行其 target；旧实现会访问控制 socket，新增早期 cancellation 检查后 getsockopt/recvmsg 均不再调用，来源 listener alias 不增长。
- **线程清理合同：**工作线程身份已发布时，cleanup 设置取消后执行 bounded join 轮询；若调用 signal 恰在 `Thread.start()`、身份未发布的窄窗口到达，线程 target 尚不能运行 receiver，此时先设置取消并重抛，延迟启动的 target 在任何控制 socket 操作前退出。该分支不声称 join 一个尚未发布 ident 的线程；以取消屏障保证它不接触 handoff 通道或 descriptor。
- **本地验收：**handoff/native-probe 定向 28/28、`.venv` Python 3.11.15 完整 unittest 门禁通过；本节证据不变更 sender、bridge/relay、策略或跨平台 OS 强制状态。最终精确树审查及远端 CI 待完成，R2 网络和自动模式仍关闭。

### 2026-09-27 14:40 UTC：wrapper close 异常下 raw FD 回收

- **TDD 复审修复：**精确树复审发现 adopted wrapper 在取消后 `close()` 若抛异常，会跳过随后 `_close_received_descriptors()`。新增真实 SCM_RIGHTS 接收、取消屏障和注入 close 异常的回归，旧实现 FD alias 从 1 增为 2；改为 `try/finally`，无论 wrapper close 结果如何都关闭原始 rights descriptors，回归转绿。
- **局部验收：**handoff/native-probe 当前 29/29；wrapper-close 异常回归单独先红后绿。完整 `.venv` 测试、精确树独立复审、远端 CI 需在本改动后重新完成。
- **安全边界不变：**仅增加 receiver cleanup 的资源回收保证，不是 sender/bridge/relay 或端到端网络安全证据；网络和自动模式保持关闭。

### 2026-09-27 14:45 UTC：最终本机门禁状态

- wrapper-close 修复后的 `.venv` Python 3.11.15 完整测试通过；handoff/native-probe 29/29，dup/SIGINT 30/30、子模块门禁、竞品/治理/站点检查、限定文件扫描、compileall 和 diff check 通过。
- 精确树独立复审与 commit/push 后远端 CI 仍为硬门槛；当前不开放 R2 网络或自动模式。

## 2026-09-27 下一片设计：Linux trusted sender → receiver → loopback accept

- **固定源码研究：**Codex `openai/codex` SHA [`41f9084b30812db321a0b592def4f500d1e79cf4`](https://github.com/openai/codex/commit/41f9084b30812db321a0b592def4f500d1e79cf4)，Apache-2.0。`proxy_lifecycle.rs` 通过私有 Unix 通道交接单个 loopback TCP listener FD；host 校验后 ACK，sandbox command 在 ACK 后才运行。该 SHA 的 README 称 `socketpair()` 会被阻止，但可执行 `managed_proxy.rs` 测试明确允许 AF_UNIX `socketpair()` 并只拒绝 AF_UNIX `socket()`；ICODE 以可执行源码/测试为准，不把文档表述提升为已证明能力。[handoff 源码](https://github.com/openai/codex/blob/41f9084b30812db321a0b592def4f500d1e79cf4/codex-rs/linux-sandbox/src/proxy_lifecycle.rs) · [managed proxy 测试](https://github.com/openai/codex/blob/41f9084b30812db321a0b592def4f500d1e79cf4/codex-rs/linux-sandbox/tests/suite/managed_proxy.rs#L806-L845)
- **采纳 / 暂缓：**采纳单 listener FD、独占控制通道、host 收到并验证后 ACK、ACK 后才启动 payload 的顺序；暂缓 CONNECT 解析/lease/relay、真实上游代理、Agent/ToolContext 接线和网络策略开放，不复制实现代码、不加运行依赖。对跨 netns socket 语义以 ICODE 自身真实回环测试验收。
- **本片验收：**Linux native helper 内建立 `127.0.0.1:0` TCP listener，经现有 credential-bound receiver 交给 host；host 发送严格 ACK 后 payload 才启动，并通过该 listener 与 host 收发 marker。验证 worker 新建 AF_UNIX `socket()` 被 seccomp 拒绝、错误 ACK/控制 fd 缺失时 payload 不启动、失败路径关闭 FD/子进程；namespace 受限的 runner 只能记为 skip/degraded，不能计通过。所有流量限于本机 loopback，不访问公网。
- **边界：**这是受控原生 helper 的 handoff 与 host accept 证明，不是 CONNECT proxy、代理目标授权或“worker 只能访问获批代理”的完整旁路证明。worker/Agent 网络与自动模式保持关闭；Linux 双架构 CI 和 OS 级 bypass 验收仍未满足。

### 2026-09-27 UTC 阶段末：nonce-bound listener ACK

- **实现：**native helper 在 loopback-only netns 中创建仅绑定 `127.0.0.1` 的 TCP listener，用 `getrandom(GRND_NONBLOCK)` 生成每次 handoff 独立的 16-byte challenge，与单个 listener FD 同包发送；host ACK 必须回显完整 challenge，native 才继续 fork/exec payload。随机源不可用、通道异常、超时、错误 ACK 一律关闭 listener/control 并不启动 payload。Python receiver 继续验证直接子进程 PID、消息长度、唯一 FD 与 listener 类型/地址；成功返回后才将 nonce 一次性绑定到 listener 对象和原 control socket，ACK 需匹配二者且只能使用一次。
- **TDD 与独立复审：**独立复审先发现固定 ACK 可在 listener 到达前排队，真实 native 回归在旧实现上观察到 payload 错误启动（RED）；改用随机 nonce 后，预排队旧 ACK、正确前缀+正确长度但错误 nonce、错误控制通道、重复 ACK 均拒绝且 marker 不产生。相关失败接收测试改为 4 秒有界等待。独立只读复审未发现 Critical/Important，Ready to merge 仅针对此 handoff slice；该结论不代表生产代理接线或完整 R2 网络门通过。
- **本机验收：**本阶段完整相关 handoff/native-probe 套件 48 项通过；4 条关键真实 namespace/native 边界连续 20 轮（80 次运行）通过且无平台 skip。Python 3.11.15 Linux x86_64 安装式 wheel 构建、检查、隔离安装、安装后 probe、宿主崩溃清理和 Git status broker probe 全通过；preflight 全量 unittest 与 submodule 门通过；`-Werror` 原生构建由真实集成测试覆盖。推送后的 Linux ARM64 / macOS / Windows CI 尚待回收。
- **上游对照与范围：**沿用 Codex 固定源码 SHA [`41f9084b30812db321a0b592def4f500d1e79cf4`](https://github.com/openai/codex/commit/41f9084b30812db321a0b592def4f500d1e79cf4)（Apache-2.0）的私有 Unix listener FD handoff / host ACK 机制作为架构参考；本阶段新增 nonce 是针对 ICODE 审查问题的本地强化，不归因于上游，也未复制上游实现或增加依赖。尝试刷新 Codex 当前源码页时 GitHub 未给出可核验的最新 commit SHA，因此不把 unpinned `main` 当成新固定观察，后续可访问时再复核。
- **严格边界与下一步：**真实测试只在本机 loopback 完成 marker 往返，不访问公网。此片未实现 host bridge 到授权上游、CONNECT listener/TLS/双向 relay、production proxy lifecycle、worker/Agent/ToolContext 接线、跨平台“只能到代理”路由或完整原生 conformance；netns helper 仍为不接产品执行路径的受控候选。网络默认 `DENY`，自动模式、Git 工具入口继续关闭；R2/R3 均未完成。下一阶段先把可信 host listener 生命周期与既有 lease/数值地址连接器按 scope 接成 loopback-only 验收闭环，同时维持 worker 网络拒绝，跨平台 OS 强制另列门禁。
