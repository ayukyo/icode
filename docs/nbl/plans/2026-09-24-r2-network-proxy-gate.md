# R2.4 临时网络授权与代理门禁

- 日期：2026-09-24
- 状态：设计边界与负例已确认；尚未实现代理，自动模式保持默认断网
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

这些是固定版本源码/官方文档观察，不是上游运行时实测；`HTTP_PROXY` 仅为合作式客户端提供路由信息，不构成安全边界。

## 必须先红后绿的负例

- raw IPv4/IPv6、localhost/loopback、RFC1918、链路本地、保留地址、DNS 重绑定、跨域重定向与非法 CONNECT/SOCKS 目标；HTTP、HTTPS、DNS、UDP、UDS 和直接 `connect()` 均不能绕过。
- 代理宕机、授权撤销/到期时，已有隧道和新连接都关闭；不同 run/工单不能借用同一个授权；子孙进程不能比父进程有更大网络能力。
- 代理进程、环境变量、回执和沙箱文件均不泄露模型 API key、SSH key、浏览器凭据；启动失败绝不裸执行。
- Linux x64/ARM64、macOS Intel/Apple Silicon、Windows x64/ARM64 的原生负例和干净 wheel 安装复测分别通过。

本计划只固定安全门禁，不把 `PROXY_ALLOWLIST` 数据结构误报为已经支持临时联网。
