# R2.4 临时网络授权与代理门禁

- 日期：2026-09-24
- 状态：已新增 lease 范围模型与本机审批/HMAC/撤销 authority 契约；代理和 OS 强制路由仍未实现，自动模式保持默认断网
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
