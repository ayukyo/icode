# Windows startup 整链权限：实现前研究

2026-10-11，ICODE分析基线main `0d40c2577316bfa52e9c595dfcd4e388ecd8c28c`。身份候选软件已冻结并完成双审，但完整守护/发布/新身份原生门仍待；本文仅只读研究和设计输入，不实施消费者、不授完整权限窗口或WP0b/R2/R3。

## 现有实现与最小缺口

| 当前对象 | 已有机制 | 缺口/不能代替 |
| --- | --- | --- |
| PinnedStartupFile | 保存root/全部祖先/file HANDLE与metadata baseline，失败逆序一次close全链 | 未逐对象消费权限，不冻结ACL |
| WindowsStartupPinBackend | active HANDLE的query_security与owned bytes运输 | 不判source/protected，不证明加载/启动 |
| check_startup_security | owned bytes重parse，分source/protected与实际directory检查 | 外部canonical SID不是来源凭证，不是AccessCheck |
| WindowsStartupHostIdentity候选 | 原宿主primary TOKEN_QUERY/returned window/确认close后canonical SID | 新SHA实际原生门未跑，不是UAC交接/DPAPI身份绑定 |

三问：真实问题是现有三层尚无同owner内部角色消费者；应复用现有HANDLE、bytes parser和生命周期而非重开路径；调用链仅增加窄内部检查，旧pin仅持有字节与读取行为保持。生产操作先在首次UAC前捕获实际原host身份，owner同actor保持root及祖先，前核metadata→逐同HANDLE按真实directory与固定role查询/检查→后核metadata。失败或中断复用全链一次关闭/主体异常优先；正常继续持有原owner，不能检查后关闭再重开。

这是建议的内部连接边界，尚不是批准/实施的消费者API；模型入口不得接受caller SID、外部snapshot、裸HANDLE或自述role当授权。pure policy从source信任Admin/SYSTEM/原host TCB，protected仅Admin/SYSTEM；不自动信任TrustedInstaller，不在这片做组、deny/ACE顺序模拟或RX grant。两个源权限/身份组件的实机门须先按新SHA独立关闭，再开始消费者实现。

## 两个必须先明确的风险

1. 系统祖先兼容：代码将目录allow ACE的0x2/0x4/0x40作mutation，即[ADD_FILE/ADD_SUBDIRECTORY/DELETE_CHILD](https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants)；普通群体若有这些位则保守拒绝，即使inherit-only/另有deny也不抵消。本轮没有root C盘或其它系统祖先实际descriptor日志，因此不能声称默认ACL必然存在这些项，亦不能为了假设的pip兼容自动放宽或修改host ACL。
2. 时间窗口：[GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo)不处理同时更改descriptor的竞争，可能失败。分享模式阻止所测写/删除open，不等于WRITE_DAC/owner/ACL恒定；metadata前后相等、两次descriptor bytes相同也只证明观察一致。完整核验/加载/UAC窗口与旧已授访问句柄仍须单独分析，逐对象快照不升级为全窗不变量。

## 原生最小鉴别，不靠改环境过门

对实际固定包内来源资源和已存在的受保护候选，只读全祖先同HANDLE metadata/security前后查询，消费当前纯策略并记录其真实分类。没有protected安装候选时明确未观察，不创建/接管同名目录以假装已安装。实际来源从可信包定位，不从模型或用户环境路径代入。

有限回执包括实际OS/build、architecture/Python、候选SHA、固定role、链index/type、owner可信类别、公共well-known trustee类别、ACE flags与mutation位、parser/policy拒绝类别、metadata/descriptor观察一致性、各owned close确认。禁止私有路径/host SID/裸地址/raw descriptor；预期拒绝或诊断job exit0不算生产兼容通过。不修改祖先ACL、创建系统root子项或执行安装/提权。

便携消费者负控再覆盖每个位置query/parse/policy失败、role混用、实际directory错配、metadata漂移、constructor/主体KI或SE与复合close故障；新增方法/fixture/subTest不允许skip骗过门。hosted四格、Win10/普通host分别计账；没有合格native正控时继续未通过，不用synthetic ACL覆盖实际祖先问题。

## 开源取舍

独立只读研究于root收到时12:14 UTC前完成，沿固定Codex `8c0f7011674145da7e10627769fb221c74fbf7a0` / SRT `5507fb0e639c00f845554336ece62e27af5b1bb7`，Apache-2.0；未刷新HEAD或完整二十名单。root另取固定raw与Microsoft原文校准行号，不把行号调整称版本变化。

- 采纳Codex [`no_reparse_dir.rs:112–137`](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs#L112-L137)的操作期间保留HANDLE及分享访问权单独约束；ICODE复用owner/active HANDLE运输，收益为不混权限对象和字节对象，成本为内部窄消费者及负控。
- 暂缓Codex [`198–220`](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs#L198-L220)的新对象guard：它会写对象，不属于只读鉴别；不能默认为已部署。暂缓系统祖先兼容调整/TrustedInstaller、组AccessCheck、安装/加载/UAC。
- 不适配SRT [`self_protect.rs:55–78`](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/self_protect.rs#L55-L78)的锁失败warn-and-continue，及[`92–104`](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/self_protect.rs#L92-L104)另属进程DACL重写的机制；本片不可用宿主权限变更掩盖拒绝。

无源码复制、新依赖或新增权限；许可交付不变，收益仅限该实际连接与观察合同。以上不是上游漏洞结论、CODEX式启动授权、SPEC/QUALITY或任何新Windows验证。
