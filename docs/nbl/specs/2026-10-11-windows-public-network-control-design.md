# Windows 公网网络对照设计（待确认）

观察日期：2026-10-11。基线：main `532dae19099eec79772015ff6052175650da3d35`，vendor `21566a5`。

状态：设计提案，不是已实现能力。临时 internetClient 诊断入口已向用户异步询问，确认前不实施该新能力；已有安装包 CI 继续独立观察。

## 真实问题与已有实现

`9cb3809` 的 CI `38115964037` 终态为 39 成功、2 Windows Reviewer 失败、3 跳过。x64 job `114400792792`、ARM64 job `114400792841` 的前置10项通过，候选一项失败、退出78；零能力候选连接本机 listener 返回10035后等待到期，privateNetwork capability 正控也失败。宿主观察器 ready、回执格式有效，但没有匹配事件。不能把无事件或等待到期判为拒绝。

既有调用链：

```text
ci.yml 标准用户与 staged runtime
  → test_Reviewer快照AppContainer只读边界与Job清理
  → run_windows_appcontainer
  → windows_job 创建 AppContainer + Job、启动暂停的 child、核 token
  → runner WFP observer 精确订阅、候选执行、终态/清理
```

当前 loopback canary、主机实际收包、能力令牌身份、ACL恢复、Job回收均保留。`windows_appcontainer.py` 的 capability 诊断只接受固定 privateNetwork 双栈 loopback 脚本，不能换任意 argv；`windows_job.py` 只实现该私有能力。原生 `icode_wfp_event_probe.c` 的非 loopback 地址解析仅 RFC1918 IPv4；IPv6 模板固定 `::1`。公网实验不能靠放宽这些旧入口完成。

复用 `network_destination.resolve_public_tcp_targets` 的公共地址校验、绝对 DNS 名、固定 sockaddr 与旧版 IANA 分类拒绝；复用 WFP 生命周期、profile 身份核验、Job 和 ACL 清理。不能复用其结果冒充本机地址枚举或真实 TLS 成功。

## 选择与取舍

推荐：另设明确命名、仅 CI 的公网 HTTPS 三方对照，补充既有 loopback 测试，不替代它。

另两种路线：

- 继续调本机 listener：不新增能力，但 privateNetwork 正控也失败，仍难区分回环限制与测试环境；保留作诊断，不作为公网拒绝证据。
- 加回环豁免或修改 WFP/防火墙：会改变验收对象和宿主安全设置，不符合本次边界，不采用。

不选择“把本机 NIC IP 当公网”：同机非127地址不能仅按地址文字判为非 loopback，必须核实际事件的 `isLoopback=false`。

## 实验合同

### 1. 宿主固定目标

固定官方公开 HTTPS 域名，TCP443；无自由 URL、无凭据、无 HTTP 请求或重定向。宿主调用既有公共目标解析器一次，拒绝混合私网答案、保留地址、mapped IPv6、scope/flow 非零，以及本机接口实际持有的地址。地址族独立选取一个已验证数字 sockaddr，冻结 hostname、地址族、地址、443 和本轮不可猜 ID。

解析必须有有限预算；同步系统解析器没有期限保证时，放在受控子进程，超时回收。连接仅使用冻结数字 sockaddr；hostname 只用于 TLS SNI 和主机名校验，不得传入二次 DNS、代理、HTTP 客户端或连接池。

目标确认和协议解析为跨平台纯函数；实际宿主 TCP/TLS 是单独的有界探针。Python 标准库 TLS 开启证书验证和 hostname 验证，禁止关闭验证、自动代理、TLS fallback。公网目标不可用不是策略拒绝。

### 2. 三方对照

同一冻结目标、同一 staged runtime、相同连接与 TLS 脚本：

1. 宿主标准用户正控：实际 TCP + TLS 成功，读取经验证 peer 证书即可，不发送业务数据。
2. 临时 internetClient AppContainer 正控：独立 profile、启用恰一项 internetClient；child 自报身份只作辅助，父进程独立核 token 的 package SID、capability数量、确切 SID 和 enabled 属性。实际 TCP + TLS 必须成功。
3. 零能力 AppContainer 负控：父进程核恰零 capability；目标字段与前两方严格相同。先等待宿主 observer ready 再连接，记录初始错误、终态 SO_ERROR、期限与状态。10035/超时仍未知。

internetClient 入口只能用于新固定脚本和经过固定协议校验的目标，仅 GitHub Windows runner、临时 runtime/profile/cwd、显式诊断 opt-in；与 privateNetwork、Reviewer snapshot/read-handle/其它启动差分互斥。实际 token 必须恰含 `S-1-15-3-1`，enabled 位为 `SE_GROUP_ENABLED`（`0x00000004`）。普通工单不可调用，不存在通用“授网络能力”参数。生产默认仍零能力；旧私有能力模式不变。

每个地址族独立处理：host 或 capability 正控失败则该族 inconclusive，不借另一族的正控授信用。正控成功也不证明零能力拒绝。

### 3. WFP 独立事件

新增独立 public 模式，不放宽旧 private/loopback CLI。分别校验规范数字 public v4/v6、443、profile、临时回执路径；不能接受任意地址/端口或自由目标 JSON。

分别订阅 CLASSIFY_DROP 与 CAPABILITY_DROP，不把重复事件类型条件塞入同一 AND 模板；历史枚举保持有限页数与本轮时间窗。IPv4 精确地址为 UINT32，IPv6 为 FWP_V6_ADDR_AND_MASK 的16字节地址和 `/128`。回调再次检查 header 字段有效位；实际事件必须匹配零能力候选的 package SID、数字地址、TCP、443、时间窗和 OUT，且 `isLoopback=false`；计数一致性、observer句柄关闭和回收均核验。

CAPABILITY_DROP 应核 network capability 分类符合公网；CLASSIFY_DROP 的 `filterId` 必须进一步读取过滤器元数据或有其它独立证据证明是 AppContainer 能力规则。普通防火墙 drop 不能算 AppContainer 拒绝。禁止新启用全局 netevent collection、改 ACL 或新防火墙规则；采集不足仍 inconclusive。

保留现有终态10013门。这次实验不能因“微软案例通常有 drop”而改变错误协议或降低准入。若真实事件与现有门产生矛盾，先记录并提出单独的验收调整，不自动通过。

## 文件边界与依赖顺序

1. 新的诊断目标/脚本模块与独立测试：固定协议、host预算、TCP/TLS脚本、严格 argv识别；复用既有公共解析器，不修改产品代理/租约。
2. `windows_job.py`、`windows_appcontainer.py` 与对应测试：仅新诊断 capability 模式、父 token 核验与互斥；原模式回归。
3. `native/windows/icode_wfp_event_probe.c` 及原生/协议测试：新 public IPv4/IPv6 模式、精确模板、事件分类归因、固定回执版本和清理。
4. 独立 Windows 测试及 `ci.yml`：同一目标三方运行、先订阅后负控、地址族独立终态、诊断固定摘要；不得上传证书、路径、SID、地址或原始 WFP 日志。

三方实验尚未接线之前，单个解析器或 argv 测试不能称作本阶段完成。新文件必须与实际 CI 调用相接；不提交未调用的“安全能力”冒充交付。

## 失败、隐私与验收

固定错误分类：目标不合法、解析期限、宿主正控失败、能力正控失败、token身份失败、observer不可用、负控期限、无匹配事件、事件不可归因、清理失败。正控失败同时保留固定子阶段 `ssl_init`、`trust_init`、`tcp_connect`、`tls_handshake`、`certificate_verify`，不能只报笼统能力正控失败；TLS失败或TCP已通不自动授拒绝信用。公开日志仅固定分类和有界计数/布尔，不输出 argv、证书、profile/SID、用户路径、DNS答案或回执原文。

每个动作均须 RED→GREEN：恶意目标/混合DNS/本机IP/代理注入/二次DNS/错误cap/互斥/无opt-in/错误身份/时间窗或SID目标不匹配/普通防火墙drop/通道损坏不能通过。平台纯测试不能代替 Windows 动态检查。资源和控制句柄故障注入、超时、profile/ACL/Job回收必须实际覆盖。

本机相关和完整 preflight通过、独立审查无阻断后才提交推送 main；Windows x64/ARM64新SHA实际三方与WFP事件通过，才能结论这个实验完成。`policy_contract_ready` 和R2/R3总门仍不由单个诊断改变。

## 官方证据与持续研究

- [Microsoft AppContainer/UWP 排障](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/troubleshooting-uwp-firewall)：Internet有internetClient允许、零能力CLASSIFY_DROP及非loopback事件案例。是官方案例，不保证当前runner同样结果。
- [Microsoft TCP loopback](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2012-r2-and-2012/hh997026%28v%3Dws.11%29)：同机通信概念，不能仅据NIC地址断言非loopback。
- [AppContainer 创建](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)和 [SE_GROUP_ENABLED](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-samr/9e093bd2-e451-4dd5-9700-97b977d7ebb2)：请求 capability 与 enabled 属性；实际 token 仍必须独立核验。
- [WFP 枚举模板](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_net_event_enum_template0)及 [IPv6 精确地址](https://learn.microsoft.com/en-us/windows/win32/api/fwptypes/ns-fwptypes-fwp_v6_addr_and_mask)：AND 模板和 `/128`；不推断实际事件存在。
- [CLASSIFY_DROP2](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_net_event_classify_drop2)与 [FwpmFilterGetById0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmfiltergetbyid0)：filterId 只指向过滤器，按名称猜因果无效。
- [Certificate Stores](https://learn.microsoft.com/en-us/windows/win32/secauthn/certificate-stores)：证书存储访问是独立兼容性门，不保证 Python ssl 在任意 AppContainer 中完整可用。诊断分别记录 ssl/trust 初始化、TCP、TLS握手与证书/hostname验证，失败不算网络拒绝。

独立只读研究已在本阶段核确切 capability SID/属性、公网IPv6模板和 CLASSIFY_DROP 归因所需接口；TLS/AppContainer默认信任存储兼容仍须实测。采纳实际正控和精确事件绑定；暂缓改变验收错误门或产品网络路由；不适配无callback、10035或文档案例作为当前拒绝证据。不复制上游源码；不新增特权安装/宿主配置；新增能力仅限待确认的临时诊断token。

## 设计自检

真实故障、现有实现及调用链已核对；新入口不放宽旧入口；目标、正控、负控和事件必须绑定同一冻结对象；环境失败不授策略信用。已明确网络权限、TLS验证、协议版本、失败和清理边界。此文是设计，不具有语法编译或Windows动态通过证明。

独立只读审查无设计阻断，提出正控固定TLS子阶段要求，已纳入失败协议；不把设计审查结论当作授权或实际运行结果。
