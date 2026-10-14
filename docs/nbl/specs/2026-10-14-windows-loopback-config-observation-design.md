# Windows loopback 配置前提只读观测设计

观察日期：2026-10-14。状态：DESIGN ONLY，尚待 root 全文及 fresh SPEC → 不同 QUALITY；不是实现、TEST、完整资产 PLAN 或新增权限授权。

本轮只新增本文。源码、测试、CI、Git 与系统不改，不运行网络或原生探测。批准输入为 root 实际 sequential-thinking 三步 accepted 的 `7702ec`（exit 0）及本轮固定 Microsoft 官方 API 研究；本作者不把 root 的调用冒称自己的调用。下一阶段仍须独立批准完整资产。

## 真实问题、基线与结论上限

分析基线为 Agent `58bc31be4f4a235848cff3e36c482985db23e9ef`，与 CI `38581925165` attempt 1 两个失败 Reviewer job 的 checkout SHA 一致。云 runner 是逻辑平台身份，不是已核物理设备；本研究没有重新独立散列其已加载 Python、系统 DLL 或原生 helper 字节。

| 平台 | job | 原始观测与 footer（UTC） |
| --- | --- | --- |
| windows-latest / x64 | `115913759361` | exit 78；10035 后 wait timeout 10 次，event enum 未执行；positive exit 105 / ipv4_connect_timeout；cleanup footer `14:40:41.4028964Z` |
| windows-11-arm / ARM64 | `115913759450` | 同类字段，不能仅因字段相似认定同根因；cleanup footer `14:44:21.8131752Z` |

两 job 的宿主 IPv4/IPv6 listener 正控均成功；候选 connect_denied=false、SO_ERROR=0、TCP 信息不可用。privateNetwork 正控父侧 token 核验匹配，cleanup=true，但 readiness_credit=false。现有正控脚本按 IPv4 → IPv6 顺序，IPv4 失败即退出；不能把 IPv6 canary=false 写成 IPv6 正控实际连接失败。

10035 是非阻塞连接 pending；等待预算到期、没有事件、SO_ERROR=0 均不是本候选 DENY 证明。本片只补充当前未观测的配置前提，不确定唯一根因，不解决 timeout，也不改变 Reviewer 原失败。结论上限为 observation_only。

前置[公网网络对照设计](2026-10-11-windows-public-network-control-design.md)仍是待确认的新能力提案。本文不启用其中 internetClient、公网 TLS、external peer 或临时公网 token，也不以本片替代三方公网实验。

## 已有实现与推荐路线

当前 `src/icode/windows_job.py` 的固定 privateNetwork 正控使用恰一项 privateNetworkClientServer capability，连接既有本机双栈 listener。`tests/test_windows_appcontainer.py` 生成独立 positive profile，先派生预期 SID，调用 `run_windows_appcontainer`，再读取父侧 token 回执；candidate 是另一零 capability profile。

`src/icode/windows_appcontainer.py` 已限制正控入口、staged runtime、临时 profile、Job 和 ACL 生命周期。`native/windows/icode_wfp_event_probe.c` 已有严格 profile 名检查、SID 派生与若干固定 observer 模式；`scripts/run_windows_appcontainer_read_probe.py` 已有启动/停止及小回执解析。

项目当前没有 `NetworkIsolationGetAppContainerConfig` 接线。`native/windows/icode_appcontainer_read_probe.c` 的 `NetworkIsolationDiagnoseConnectFailureAndGetInfo` 是不同 API；它不是 GetConfig，也不能据此称 Reviewer 已观测 loopback 豁免配置。

| 路线 | 取舍 |
| --- | --- |
| 推荐：既有 fixed native helper 增独立只读配置模式，标准用户父侧驱动 | 复用构建/分发与内部 profile 约束；单独协议和退出，不依赖 WFP 订阅成功，不扩大网络入口 |
| 在长期运行的 Python 测试线程内直接 ctypes 调 API | 同步 API 无取消合同，线程 watchdog 不能保证回收；暂缓 |
| 改豁免、网络 capability、外部目标或防火墙 | 改变验收对象并超出授权；不适配 |

推荐只观察 positive profile。零 capability candidate 不查询、不修改，也不以 positive 配置为其授权限或拒绝信用；如以后确需 candidate 配置，另行设计。

## 调用入口与两采样顺序

拟议 helper mode 名为 `--observe-positive-loopback-config`，不是当前可调用接口。参数恰为内部生成的 `icode-` 加 32 个小写十六进制字符 profile 名；不接受 SID 字符串、地址、端口、命令、任意路径或 JSON 目标。该模式不创建/删除 profile，不连接网络，不开 WFP engine，不订阅/枚举事件，不调用配置写 API。

可信测试父侧只在现有 CI opt-in、固定 staged runtime、既有 helper 解析路径及标准用户入口成立时调用。模型/普通工单不取得新入口；helper 参数合法也不代表任意调用者拥有产品授权。

固定顺序：

1. 现有测试生成 positive profile 名和预期 SID，listener 与宿主正控保持原顺序。
2. 在调用现有 privateNetwork 正控前，用独立 helper 实例取 pre 样本。helper 从固定 profile 名派生 SID，仅作一次派生，不使用现有 wait-profile 的 10 秒轮询。
3. 原正控完全照旧运行，保持 argv、capability、父 token 核验、connect 超时、profile/ACL/Job 清理及原判定。
4. 原正控返回后用第二个独立 helper 实例取 post 样本；即使正控失败也尝试取样，但已观察到回收 unknown 时不继续派生新工作。
5. 父侧确认两样本均来自自己的两次调用，且 positive 父 token 的 package SID 对该内部 profile 匹配。没有这层绑定时，只报告配置样本，聚合结论 unknown。
6. 在父侧 finally 路径回收 helper；新增诊断错误不得覆盖原 Reviewer 异常、退出或 cleanup 失败。

若 pre helper 已确认未回收，不再启动 positive 或 candidate，以诊断清理失败终止该测试，不把未执行的旧门标通过。若 post helper 未回收，保留已产生的原 Reviewer 首结果，另报诊断清理失败。其它已回收但 unsupported/API error 的样本不跳过原实验，只令配置观测 unknown。这里是清理停止线，不是修改原 DENY 判定。

post 采样发生在原 wrapper 返回之后，此时 profile 可已按旧合同删除。派生函数获得的是该内部 profile 名对应身份；样本不证明 profile 此刻存在，更不证明进程当前使用该 SID。此限制与父 token 的历史核验分账。

两采样只比较所观测的 target_match、target_attributes 和 entry_count。任一变化报告 observed_drift；均相同只叫 consistent_endpoints，不叫策略全程未变。未读取其它 SID 的可公开身份摘要，不声称检测到所有全局配置变化；采样间变化后恢复、无关项目替换且计数不变均是盲点。

## 精确 API、动态载入与 ABI

只调用官方函数：

```c
DWORD NetworkIsolationGetAppContainerConfig(
    DWORD *pdwNumPublicAppCs,
    PSID_AND_ATTRIBUTES *appContainerSids
);
```

`DWORD` 是 32 位，返回值是 Win32 状态码，不能用 BOOL/HRESULT 或环境 last-error 代替查询返回值。动态函数指针须使用官方示例的 WINAPI 调用约定及精确两指针形参。`SID_AND_ATTRIBUTES` 使用 Windows SDK 原生指针和 DWORD 布局，不手写 pack，不把 x64 的尺寸直接当 ARM64 已验证事实。SID 用 `IsValidSid` 检查后 `EqualSid` 比较，不转字符串；attributes 仅保留有界原始 DWORD，不推导 token enabled 或有效网络权限。重复目标 SID、返回 SID 指针别名或结构异常一律 invalid_data，避免同指针重复释放。

通过 `GetSystemDirectoryW` 取得系统目录，拒绝失败/截断，再以其绝对 FirewallAPI.dll 路径及 `LoadLibraryExW` 的 `LOAD_LIBRARY_SEARCH_SYSTEM32` 约束依赖搜索，精确 `GetProcAddress`。不能把官方示例的裸 `LoadLibraryW` 搜索直接复制进新模式；不更改全局 DLL 搜索目录，不用忽略签名/授权的 loader flag。系统 API 不支持或符号不存在时不回退到其它库、Set API、命令行工具或提权。

句柄/函数指针只在本 helper invocation 内持有；API 内存释放完成后 `FreeLibrary`，保存其成败。缺导出是 unsupported；一般 DLL 装载故障保留 load_failed，不把每个 loader 错误都解释成旧系统。Windows 8 / Server 2012 是官方最低桌面系统要求，当前 x64/ARM64 runner 是否可用须同新 SHA 实测。

## 分配与释放所有权

查询前 count=0、array=NULL；仅 ERROR_SUCCESS 且完整结构验证后解释内容。count=0/NULL 可表示成功空集合；count=0/非 NULL 时数组仍须释放。count>0/NULL 不是空集合。API 非零时初始化值不能当有效返回数据，原错误须保留。

官方 GetConfig 示例的释放规则为：逐项 `HeapFree(GetProcessHeap(), 0, array[i].Sid)`，再同样 `HeapFree` 数组。每项与数组的尝试/确认分开计数，固定唯一 owner，不重试已释放指针；派生目标 SID 的分配则仍用其原配对 `FreeSid`，不能混用 allocator。

禁止 LocalFree、CoTaskMemFree、FwpmFreeMemory，尤其禁止 `NetworkIsolationFreeAppContainers`：它的参数是另一种 `PINET_FIREWALL_APP_CONTAINER`，不是本返回结构。HeapFree 或 FreeLibrary 失败使 cleanup=failed；异常/不可信返回结构无法安全遍历使 cleanup=unknown，不能把部分释放当全部释放。

正常且受限的所有成功/比较失败出口必须显式释放所有已取得且可安全访问的资源。超过条数预算或异常结构时不为“清理完成”无界追遍历、不解引用已判不安全的数据；helper 退出后 OS 回收与显式清理确认分账，仍不授 cleanup=confirmed。故障注入不以任意野地址在宿主进程解引用来伪造有意义的软件负控，helper crash 则由父侧报告 unknown。

## 预算与生命周期

当前 Reviewer job timeout 为 25 分钟，原 full job 的 25 分钟不是本模式独有预算。当前 WFP 旧模式使用 ready 最多 5 秒、停止 wait 5 秒，再 terminate/wait 2 秒、kill/wait 2 秒，且回执文件至多 4096 字节；这些不是已有 GetConfig 的 2 秒硬时限。旧模式不在本片顺便重构。

本新模式冻结以下独立上限，未来完整 PLAN 须用真实实现与负控证明，不能只改常量：

| 边界 | 本设计约束 |
| --- | --- |
| 单样本工作预算 | 父侧 monotonic 从启动尝试前计 2 秒；拿到进程 HANDLE 后以剩余时间等待，无重试 |
| 回收预算 | 超时/溢出后 terminate，最多等 2 秒；未退出再 kill，最多等 2 秒；之后 process_reaped=false，停止后续新样本 |
| 输出 | stdout 恰一条 ASCII JSON，总计不超过 4096 字节；stderr 必须空；父侧读取需有界，禁止无界 capture 后才检查大小 |
| 项目 | 完整验证/比较至多 4096 项；超过即 limit_reached，不用前 4096 项得出未匹配 |
| 样本数量 | pre/post 各一次，至多两个 helper；无自动重跑、无循环等待 API 恢复 |

现有只读模式不创建子孙进程；如 helper 产生派生进程或需要新 Job/权限才能回收，停止并退回设计，不默默扩大能力。本进程必须由父侧保有实际 Popen/HANDLE 与 wait 结果；pid 消失、退出请求成功或超时异常不等于回收确认。

API 是同步调用，没有 timeout/cancel 参数，内部可能先分配大数组；4096 项只约束返回后的处理，不是 API 预分配上限或 memory hardquota。2 秒为父侧观察/等待预算，不宣称 Windows 进程创建或 terminate/kill 本身具有严格墙钟上界；当前 Popen/CreateProcess 阻塞、内核调用阻塞和外层 CI timeout 都仍是边界。不能加线程 watchdog 后声称 API 已取消。若独立验收要求真正总墙钟硬限额，当前设计不满足，必须停下另审监督边界。

## 安全协议与错误分账

拟议独立 schema 1，不改现有 WFP receipt，也不复用其 ready/stop/result 文件以免串样本。helper 只向 stdout 返回固定 JSON；父侧确定 phase、调用归属和最终 SHA/job/platform，不让 child 自报这些字段取得信用。父侧严格拒绝重复 JSON key、额外字段、缺字段、类型错（整数不接受 bool）、尾随内容、超长和非 ASCII。所有有合法固定回执的 status 均退出 0；非法 CLI 退出 2 且无回执，crash/其它非零由父侧归 protocol_error。退出 0 仅表示协议完成，不表示配置匹配、网络可用或隔离成功。

| 字段 | 类型与含义 |
| --- | --- |
| schema_version / scope | 整数 1；固定 positive_loopback_config_sample |
| status | complete、unsupported、load_failed、api_error、invalid_data、limit_reached 之一；父侧另合成 launch_failed、timed_out、protocol_error、not_attempted |
| api_stage / api_code | none、load、export、derive、query、validate、release；原阶段码 0..2^32-1 或 null；derive 的 HRESULT 保留 unsigned32 位形且不按 Win32 解读；不输出错误自由文本 |
| entry_count | null 或 0..4096 整数；超预算不泄漏无界计数，使用 limit_reached |
| target_match / target_attributes | target_match 为 bool 或 null；target_attributes 为 DWORD 或 null，匹配恰一项才有值；坏结构/不完整/清理失败时两者必须 null |
| sid_frees_attempted / sid_frees_confirmed | 0..4096 整数；只是显式释放账，不能代替数组/派生SID/DLL释放 |
| array_release / derived_sid_release / library_release | not_acquired、confirmed、failed、unknown；可表达零分配与失败，不能缺省 true |

父侧聚合添加 phase=pre/post、process_reaped 布尔、cleanup=confirmed/failed/unknown、observation_complete 布尔，以及 comparison=consistent_endpoints/observed_drift/unknown。这些固定字段不接收模型输入；helper schema 不含父侧字段。只有两个样本都 complete、所有取得资源释放确认、进程回收、同内部 profile 绑定与父 token 验证成立时，comparison 才可非 unknown。

release 故障保留原 query status/api_code，不覆盖首错误；cleanup 另记。即使 API/结构原本完整，cleanup 非 confirmed 时 target_match 归 null、observation_complete=false。没有取得任何资源的 not_acquired 可以构成对应资源已无回收责任，但不能把未调用 query 的整个观测算 complete。

公开输出不含 SID/profile、命令行、环境、路径、地址/端口、全局名单、全局名单指纹、原始 WFP 事件或原 API 内存。只有上表固定字段和父侧固定摘要；既有 Reviewer 原日志及失败继续独立保留。

## 未来修改责任与禁止扩散

| 关联资产 | 未来最小责任；不是本轮改动 |
| --- | --- |
| `native/windows/icode_wfp_event_probe.c` | 独立固定 mode、可信 loader、一次 derive/query、SDK ABI、内存释放、固定 receipt；不依赖 WFP 订阅权限 |
| `scripts/run_windows_appcontainer_read_probe.py` | 新模式专用启动/有界读取/回收及严格 schema seam；不修改旧 observer 启停合同 |
| `tests/test_windows_appcontainer.py` | 仅 existing positive-control 前后两样本与聚合；原 candidate、listener、token 与异常优先级保持 |
| 独立 portable/native 协议测试 | 固定状态、所有权、预算和 no-write/no-connect 负控；与原 Windows ABI/正控回归分账 |
| `.github/workflows/ci.yml` | 优先复用既有双 Reviewer job 的构建/helper staging；如需改动，完整 PLAN 必须列精确差分，保留 25min/matrix/guards，不新增权限 |

`src/icode/windows_job.py` 与 `src/icode/windows_appcontainer.py` 的产品/私有正控语义不改；若实现者发现必须改变其返回类型、profile 生命周期或正控启动 seam，应退回设计审查，不能自由扩修。

## 正负控、验收与停止线

正式 TEST 先于 SOURCE；旧源码的缺 mode/签名错误、ImportError 或编译失败不是有效 semantic RED。应以现有真实软件 seam 或匿名微型投影证明断言语义，再将批准完整资产落盘得到真实 RED，不能把设计研究当 TDD。

必要软件正控：恰一目标匹配、完整未匹配、合法空集合、普通 non-target 项、前后 consistent_endpoints；查询错误不改变原 Reviewer gate；正常所有资源一次释放且父侧回收确认。

必要负控：DLL/符号缺失与一般装载失败分开；API 非零且 count 初始化为零仍 unknown；count/NULL 矛盾、坏 SID、重复目标、预算上界/超过上界、attributes 仅数据不授权；数组/单 SID/目标 SID/DLL 各释放失败；启动失败、卡住 API、输出溢出/重复key/尾随/类型错/非零退出、回收失败；pre/post 目标或计数漂移、未取 post、父 token 绑定失效。source-level no-Set/no-socket/import 边界与实际调用计数需成对核对，不单靠字符串扫描授信用。

未来流程是：批准完整 TEST/SOURCE/必要CI资产 PLAN → fresh SPEC/不同 QUALITY → 正式 TEST 原语义 RED → 最小 SOURCE 与定点 GREEN → 实际 SOURCE fresh SPEC/不同 QUALITY → 同新 SHA 两 Windows native job。本文仅描述门，不授权现在进入任何一步。

两 native job 必须分别记录 SHA/run/job/platform/attempt、实际 helper/构建身份、调用 phase、返回状态/有界原 JSON、query 和释放账、回收、positive token 绑定及原 Reviewer footer。API 返回匹配或未匹配均可构成观测成功，但不授网络正控通过；原 Reviewer 若仍 exit78/positive105，整体失败如实保留。

停止线：要求新 capability/外部目标/豁免写入/权限、修改宿主防火墙或全局 loader；需要任意SID/命令入口；清理无法有界确认却要授完成；以部分集合判未匹配；以配置名单判有效 WFP 或根因；以 skip/unsupported/timeout 替代实际观测；以取消/重跑隐藏失败。任一出现均退回，不放宽现门。

## 固定官方证据与决策

研究观察日 2026-10-14，MicrosoftDocs/sdk-api 固定 commit `656e9656bfaef34dd29cd7ee9e1146aec17e924c`（提交日期 2026-10-09）。GetConfig 源文 ms.date 为 2022-08-03；Learn 展示更新日另为 2026-03-27，不混称 API 新版本。下列源码和根 LICENSE/LICENSE-CODE 均已实际读取；文档 CC-BY-4.0、示例代码 MIT，只借合同不复制实现，无新增第三方依赖。

- [GetConfig 官方固定文档与完整释放示例](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/networkisolation/nf-networkisolation-networkisolationgetappcontainerconfig.md)：返回允许发送 loopback 的配置集合及 HeapFree 配对，不承诺同步时限或实际连接结果。
- [FreeAppContainers 的不同类型合同](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/networkisolation/nf-networkisolation-networkisolationfreeappcontainers.md)：不能混为本数组释放器。
- [LoadLibraryExW 固定文档](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/libloaderapi/nf-libloaderapi-loadlibraryexw.md)：可信系统目录与依赖搜索，缺符号不能静默回退。
- [Winsock connect 固定文档](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/winsock2/nf-winsock2-connect.md)：10035 pending 与后续完成通知分开。
- [文档许可](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/LICENSE)及[示例代码许可](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/LICENSE-CODE)。

持续对照复用固定 Codex `27065a91ccbf5ba8532844be3777fcf83b77820d` / Apache-2.0 的 [token 有界读取/所有权](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/windows-sandbox-rs/src/token.rs#L194-L270)机制，不刷新 HEAD 或 20 项名单，不把上游管理员持久策略复制到本片。采纳：只读配置、错误/空集合/清理分账；收益是关闭正控前提盲点，成本为专用小协议和双原生验收。暂缓：WFP filter 因果、公网实验、完整隔离和产品化。不可适配：改豁免/权限、10035或配置未匹配冒充DENY/根因。

## 自审与【架构级自检报告】

本作者进行两轮不同视角的自审：第一轮按入口/协议/异常/所有权核完整闭环；第二轮按前置设计、现有源码、官方配对及信用边界反向核对。自审不是独立 SPEC/QUALITY，通过前不实施。文档结构/相对链接/字符另用 doc-contract-consistency-audit 只读检查，两轮结果交 root，不把检查脚本当运行测试。

- ✅ 语法/编译：Markdown、围栏、表格与字段约束核对；本文无源码，未编译，不冒称编译通过。
- ✅ 依赖/调用链：fixed helper → 专用父侧 seam → positive 两采样；原 candidate/observer/Job/ACL 分账，未实现入口明确。
- ✅ 逻辑/边界：空集合须真成功；partial/漂移/坏绑定不判未匹配；两个端点一致不证明全程稳定。
- ✅ 异常处理：首 query 错误、释放、超时与实际回收分别保留；unknown/unsupported 不授完成。
- ✅ 关联模块：仅新 DESIGN；未来关联表不等于授权修改，无Git/CI/系统/探测副作用。
- ✅ 兼容安全：原 Reviewer 原门、标准用户、两 job25min 与正控模式保持；无新网络权限、豁免或外部目标。
- ✅ 可运行性：设计可供独立资产审查；尚无 TEST/SOURCE/native 运行信用，不声明100%可运行或问题已修复。
