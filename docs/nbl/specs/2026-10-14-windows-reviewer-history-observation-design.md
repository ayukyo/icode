# Windows Reviewer 实际 payload 历史事件观察设计

状态：DESIGN，待 root 独立 SPEC / QUALITY 审查；未实施、未运行原生探针、未授予 R2/R3 验收信用。

## 授权、基线与三问

本片仅新增此设计文档。权威工作区 `/home/orbbec/projects/icode`，2026-10-14 本片只读 `git rev-parse HEAD` 实得 `6e893f0170b74c32d7143680636d85f400ecc7c9`；不创建 worktree、分支或 tag，不改 SOURCE / TEST / CI / 系统 / 权限。持续开发授权允许把具体设计交 root 审查，不等待新的常规许可；brainstorming 的设计边界仍有效，本片不转实现。

三问均已确认：

1. 真实问题：root 提供的同 SHA Windows Reviewer x64 job `115385294904`、ARM64 job `115385295105` 候选为 `10035 / wait_expired / connect_denied=false`，私网能力正控 exit105（IPv4 timeout）。本片未重新取远端原日志，这些是继承的已绑定证据；均不构成 DENY，也不能归因系统策略。当前源另确认实际 payload 观察入口没有尝试历史查询，构成具体诊断覆盖缺口。
2. 已有实现：`native/windows/icode_wfp_event_probe.c` 已有 Enum3 单页历史查询、64 条预算、时间窗/SID/端点二次匹配、各 API 错误状态和独立 capability/classify 字段。复用这些机制，不另造 observer。
3. 调用链：CI `ci.yml:1486` 实际启动 `--collect-ipv6-loopback-wait-profile`，其 `wmain:1890` 传 `TRUE, TRUE, TRUE, FALSE`，最后一项 `enumerate_history=FALSE`。`run_runner_subscription_probe:1781` 的 `TRUE, TRUE, FALSE, TRUE` 有历史查询，但它创建另一个临时 profile，属于订阅权限探针，不是实际 payload scope。`hist_cap/hist_cls=not_attempted` 的零计数只是初始化值，不能写作查询获得零结果。

本片最小目标：使现有、实际 IPv6 loopback payload 观察入口执行有界历史查询；输出事件已有字段的脱敏摘要，明确未尝试、查询完成零匹配、截断和错误。不解决 private capability 正控，不改零能力生产 token、网络路径或 Reviewer 错误门。

## 源码事实与消费者

| 位置（基线行） | 已核事实 / 影响 |
|---|---|
| C:349–492 | `history_event_matches_target` 和 `run_historical_event_query`：每类型单次 Enum3；最多64条；满页 `limit_reached`；逐条时间/SID/type/TCP/remote tuple/isLoopback核验；释放数组和枚举句柄 |
| C:319–338、464 | 现有bool matcher先比较isLoopback再核header；正确scope但BOOL值2被视为普通不匹配，不能复用这个bool结果实现新invalid_data分支 |
| C:1606–1684 | ready前 UTC FILETIME 起点；stop后200ms drain、两路 unsubscribe后终点；collection unknown/disabled不查询；查询后才关闭engine、释放SID |
| C:815、888、964 | 当前 JSON buffer2048；IPv6 schema8，IPv4 schema6；`write_ascii_file` 硬上限4096、CREATE_NEW和同目录不覆盖rename |
| C:1733–1737 | 当前 helper exit0说明回执写出/观察进程收尾；history API错误不会自动使它非零，不能把 exit0称为历史查询通过 |
| CI:731–789 | 订阅权限正控消费者严格接受schema8；更新schema时必须同步，不能只改实际payload消费者 |
| CI:1676–1825 | 实际payload消费者校验history状态/阶段/计数和schema8；callback计数与history计数分开；当前history零计数不证明未drop |
| CI:1731–1738、1860、2088–2091 | 现原日志仅history状态/计数，随后删除临时observer目录与回执；新归因字段必须在删除前作固定脱敏投影进入原job日志，不能只存在临时JSON |
| `scripts/run_windows_appcontainer_read_probe.py:258–359` | `_classify_wfp_ipv6_loopback_receipt` 接受6/7/8，schema8有双订阅严格分支；只依callback分类 |
| 同脚本:362–489、1080–1134 | `_wfp_observer_diagnostic_summary` 固定投影；`_stop_wfp_event_probe` 上限4096且收集非零exit的回执 |
| 同脚本:974 | 独立read-handle观察仍用 `--collect-ipv6-loopback`；不能误认为它是Reviewer实际runner入口 |
| `tests/test_windows_wfp_capture.py:227–284` | 现测试核Enum3/64/顺序及runner probe history TRUE，却没有断言实际wmain入口的history参数；必须补真实入口行为oracle |
| `tests/test_ci_workflow_contracts.py:547、563` | 两个schema8消费者契约；一并迁移 |
| `tests/test_windows_appcontainer_read_probe.py:640–776` | 旧schema7/schema8分类及v8投影回归；保留旧wire兼容，增加schema9严格验证 |
| `tests/windows_wfp_abi_probe.py`、`tests/fixtures/native/wfp_sdk_layout_probe.c`、`tests/test_windows_wfp_abi.py` | 已核HEADER3/EVENT3/CAPABILITY_DROP0布局；目前SDK输出没有CLASSIFY_DROP2字段布局；新增ctypes定义/布局映射、native fixture的sizeof/offsetof输出、`_EXPECTED_64BIT_WINDOWS_LAYOUT`字典及SDK比较断言必须全同步 |

本次搜索覆盖 native、scripts、tests、.github 的入口和schema引用；`src` 未发现本helper的schema消费者。CAB捕获解析及private-connect stage合同是不同证据路径，本片不改。

## 两种备选与唯一选择

方案A（采纳）：复用现有两路订阅及单页Enum3，只为实际wait-profile入口开启历史查询；在历史匹配项中聚合有限事件字段；把诊断schema和所有消费者成对更新。成本是一个C helper、一个Python诊断脚本及CI/合同/ABI测试同步；不加依赖、权限或网络动作。可验证actual scope与零结果/未尝试分离，改动范围最窄。

方案B（暂缓）：基于filterId继续调用 `FwpmFilterGetById0`、layer/provider查询和规则条件归因。收益是更完整的策略身份；成本是额外权限、filter生命周期竞态、对象释放与隐私过滤，还不能证明当前socket终态。当前事件字段足以填补观察覆盖缺口，本片不新增查询。

方案C（不适配）：扩大订阅/历史范围、全系统枚举、调整collection开关、增加timeout、添加loopback exemption或更换公网实验。它们改变诊断与系统边界，不能由当前未知结果授权，也不能直接修复实际入口FALSE。本片排除。

唯一选定A。event字段摘要不是完整策略归因；filterId指向事件中的过滤器，不能凭数字、层号或显示名断言AppContainer缺能力是当前失败根因。

## 架构和生命周期

只把 `--collect-ipv6-loopback-wait-profile` 的现有history参数置TRUE；不为普通IPv4 collector或独立 `--collect-ipv6-loopback` 增加历史操作。runner订阅正控已有TRUE保留。所有IPv6回执统一升级schema9，避免同一writer产生两种新合同；IPv4 schema6维持既有合同。

时间与资源顺序复用：derive指定profile SID → engine只读打开及GetOption → 两路精确IPv6/type订阅 → ready前记录起点 → 原payload执行 → stop/200ms drain → 两路unsubscribe → 记录终点 → capability及classify各一页64历史枚举 → 枚举数组释放/句柄销毁 → engine close → SID free → bounded回执。不在callback做额外WFP查询；历史摘要在unsubscribe后同线程计算，不引入共享状态竞争。

起点/终点保留UTC FILETIME闭区间；端点仍是固定 `::1` / TCP / 同remote port，事件类型分别精确。package SID不在模板中，由现有检查标志、`IsValidSid`、`EqualSid`逐条判定。历史时间不是进程身份的单独证明：scope由本次生成profile/SID、端点、时间共同绑定。

历史匹配需新增三阶段结果（outside_scope / valid_nonmatch / matched / invalid_data），不能直接沿用先比较loopback的现有bool matcher：第一阶段检查type、时间窗及header的flags/SID/族/TCP/端点；不属本次scope即outside_scope，不读取该项payload标量以污染本次结论。第二阶段只对正确scope检查对应payload存在及标量合法性；BOOL必须exact `{0,1}`，capability枚举必须0..2；NULL payload、BOOL2或其他非法值、capability越界均invalid_data，使本类型查询invalid_data、摘要unavailable。第三阶段才将合法BOOL与目标TRUE比较：合法FALSE是valid_nonmatch，合法TRUE才matched并加入聚合。其它SID/时间/端点中的BOOL2或capability越界不使本次scope invalid_data。枚举API层的空entry/空数组/异常count仍按全页结构损坏处理，不伪装scope匹配问题。callback既有bool matcher行为维持，不借此片扩大callback观察信用。

单页恰好64不能证明枚举穷尽，因此始终 `limit_reached`；不继续分页、不盲目增加等待预算。历史API调用数量有界，但同步Windows API不承诺绝对时间上界；沿用父进程有界等待/回收，超时仍不可用，不把kill后缺回执当零结果。stop缺失、ready失败、订阅失败、无有效时间窗、collection状态未知/关闭均不尝试查询，保留对应状态及null摘要。

## schema9与脱敏摘要合同

保留schema8全部callback、history计数/状态字段的含义。新增 `history_requested` exact bool；实际wait-profile必须true，独立non-history模式false；正控已有history模式true。新增两个对象 `history_capability_attribution`、`history_classify_attribution`，只聚合本页全部精确匹配事件，不输出逐条列表。

每个对象固定字段：`status`、`filter_id`、`layer_id`、`is_loopback`、`network_capability_id`。status只允许 `not_attempted / no_match / consistent / mixed / unavailable`；其余字段按下表。对象键完整、类型精确，不把 bool 当整数，不允许未知键/任意文本进入公开摘要。

| 摘要状态 | 字段规则与解释 |
|---|---|
| not_attempted | 仅history_requested=false；所有值null；不代表空历史 |
| unavailable | 请求了history但任一查询前提/有效数据/清理未满足，或本类型query状态不是complete；所有值null；limit_reached也属于此类，保留已有returned/matched计数但不授完整归因 |
| no_match | 本类型complete且matched_count=0；所有值null；仅表示该页该窗口未匹配，不能推断网络允许或无drop |
| consistent | 本类型complete且matched_count>0；所有匹配项的可用字段一致；filter_id为1–20位规范十进制字符串，数值0..UINT64_MAX；is_loopback=true；capability对象layer_id=null、network_capability_id为0..2；classify对象layer_id为0..65535 exact int、network_capability_id=null |
| mixed | 本类型complete、matched_count>0、至少一字段不一致；所有值null，不任取第一项冒充唯一归因 |

filterId使用十进制字符串避免JSON消费者/JavaScript精度截断；允许原生0值但不把0解读为有效策略身份。capability payload没有layerId，必须null，禁止臆造。classify读取SDK声明的 `FWPM_NET_EVENT_CLASSIFY_DROP2` 字段，不自定义packing，不把旧事件结构强转为新结构。只有上述第一阶段正确scope内的payload才做标量合法性检查；其非法值使该类型 `invalid_data/unavailable`，合法且非目标loopback只是nonmatch，不写consistent。

仅公开固定状态、计数、booleans、numeric IDs及规范ID字符串；不输出SID/profile、用户/路径、appId、地址、端口、时间值、provider/displayName、filter条件、vSwitch/blob或原始event。数字ID只用于本次证据关联，不当作跨runner稳定身份。摘要不是新增网络权限，也不是规则readback。

C固定buffer可扩到4096，仍维持writer/两个消费者现有4096硬上限；格式化返回负值、截断、写入/flush/close/rename失败均非零且无valid回执。必须以所有字段的最坏合法值测完整长度≤4096，不擅自提高外层限额。

## 失败关闭和兼容迁移

`history_requested=true`时，任一history不是complete（包括limit_reached、api_error、invalid_data、invalid_window、collection_disabled、unavailable）不能称为历史观察完成；原始stage/code保留。建议helper该请求模式返回现有通用非零1并尽力写完整诊断回执，不新增冲突exit-code表。历史complete/no_match允许观察transport成功，但不能授DENY。mixed属于有效、非唯一事件集合，可返回transport成功；归因不可完成、不授完整归因信用。

历史requested=false保留现有helper退出语义，严格无历史API调用。unsubscribe失败仍沿原helper立即终止且不释放callback状态，父进程标 unavailable；engine/enum destroy/收尾失败不得由回执写成功覆盖。这里的非零仅诊断failure，不改candidate的网络终态解释。

schema9由以下所有消费者同步承接：

- CI两个PowerShell消费者均严格验证新字段及状态关系；实际payload还须要求history_requested=true。先验证并在删除临时observer目录前作固定脱敏日志投影，再依据helper exit判定观察是否完成；不能因为非零而丢弃已取得的API stage/code，不能因回执有效而覆写非零为成功。两个消费者的既有job原日志分别标记固定scope `subscription_probe` / `reviewer_payload`，不新增artifact或查询范围。
- Python `_classify_wfp_ipv6_loopback_receipt` 明确把schema9进入同schema8的双订阅分支，并先验证schema9额外合同。历史字段不加入callback计数，不用于生成connect_denied；schema6/7/8历史fixture继续按原分支解释，不能按schema9补默认值。
- Python固定summary/notice增加有界history状态投影，禁原对象repr/原JSON；callback原分类继续独立。schema9收到history/API失败、缺字段或错误类型时 `evidence_unavailable`，旧wire不能声称已提供新历史观测。
- C self-test、workflow schema合同、Python历史wire与字段负控同步；不能只把8替换为9然后跳过错误条件。schema6私网分类及read-handle入口原合同保留。

两个PowerShell日志投影采用相同白名单：`history_requested`、`history_time_window_valid`、每类型的query status / api_stage / api_code / returned_count / matched_count，以及该类型attribution的status / filter_id / layer_id / is_loopback / network_capability_id。API code保留验证后的DWORD十进制或固定null；filter_id全过程保持规范十进制字符串，禁止cast为double/浮点数/中间JSON数值；其余字段按schema9精确类型校验再输出固定scalar键值。未知/无效输入只输出固定 `receipt_invalid` 标识及无法确认项null，不把原输入插到错误文本中；有效但helper非零仍打印已验证的有限stage/code和状态，再打印真实非零exit。两个scope各最多两行（每drop类型一行），每行≤1024 ASCII bytes，无逐事件列表；超过输出限额记固定投影失败，不能截断filter_id后声称完整。沿现有job原始日志持久保留这些字段即可复核新SHA/平台/任务对应关系；临时回执清理仍照原生命周期执行。严禁输出原JSON/对象repr、原异常、SID/profile/path/address/port/time值、appId/provider/displayName/filter条件/vSwitch/blob，新增字段不能被宽泛插值带入notice。

## 正负oracle与后续验收

本设计不运行测试；以下是下一计划必须具体实现和绑定新SHA的验收项。

1. actual入口oracle：测试真实argv分支/注入API行为，证明wait-profile请求TRUE且每drop类型只Enum3一次，正控与payload的profile身份分账；旧假设只测试runner-probe不能通过。
2. 生命周期oracle：固定ready前起点、stop后两路unsubscribe再history、history结束再close/free；ready/stop/订阅失败、collection未知/disabled不调用Enum3；不新增SetOption/SetLoopbackConfig/策略写入。
3. 正向历史oracle：0、1、63、64项，含恰好边界时间；complete/0与not_attempted必须不同；匹配项字段一致生成consistent；不一致生成mixed；64项无论匹配多少均limit_reached且摘要unavailable。
4. 负向匹配oracle：错SID/缺flag/空SID、错族/地址/port/TCP/type、窗前窗后均outside_scope、不计匹配；正确scope+合法loopbackFALSE为valid_nonmatch、不生成归因；正确scope+NULL payload/BOOL2/BOOL-1/capability越界为invalid_data/unavailable，不能变no_match；其他SID或窗外事件即使BOOL2/capability越界也不污染本次scope。反转查询时间是invalid_window；API错误、count>64、非零count+NULL数组/空entry和清理失败分别保留错误。
5. wire oracle：schema9缺字段/键重复/额外键、错误类型、bool-as-int、负值/越界计数、非规范filter字符串/UINT64溢出、错误null关系、complete/64、limit/63、stage/code矛盾、requested=false却有历史结果均拒绝；schema6/7/8合法旧fixture继续原行为，不得提升新观察信用。
6. 精度/隐私oracle：UINT64_MAX filterId全文保留字符串；最坏合法回执≤4096；C格式化截断不通过；两PowerShell消费者在删除临时回执前分别输出固定scope的白名单scalar，实际日志有query stage/code和attribution字段；非法字段不透传，每类型行≤1024 ASCII bytes。summary/notice不包含原始SID/path/profile/address/event或原JSON。callback和history同时匹配不相加、不设置connect_denied。
7. ABI oracle：`tests/windows_wfp_abi_probe.py` 新增CLASSIFY_DROP2 ctypes结构及布局映射，`tests/fixtures/native/wfp_sdk_layout_probe.c` 新增其sizeof/offsetof（filterId/layerId/isLoopback）输出，`tests/test_windows_wfp_abi.py` 的 `_EXPECTED_64BIT_WINDOWS_LAYOUT`字典及SDK比较断言全同步，并用Windows SDK在x64/ARM64对照；native字段是SDK定义，不假设两平台布局等同。C helper编译/self-test和消费者实跑分别绑定job/log/exit。
8. CI oracle：沿现有Windows x64/ARM64 Reviewer实际入口，同新候选SHA/平台/实际job原日志记录history_requested、窗口状态、两路query状态/阶段/API code/计数、归因白名单字段及helper/候选exit；回执清理后仍可用原日志独立核对，无新artifact。成功观测no_match也不能宣称隔离验证完成；若private正控仍exit105或候选仍10035/timeout，Reviewer/R2/R3保持失败/未知。

本机只做允许的针对性回归及静态/密钥/子仓检查；全量、Windows SDK/native与跨平台以GitHub CI为主。阶段必要证据未齐、skip、日志缺失或观察超时不能当通过。没有真实新SHA原生结果，本设计不预写“可运行性100%”。

## 官方研究与采纳记录

2026-10-14 只读复用 `docs/agent-landscape-live.md:320–328`（2026-10-04历史Enum3机制/覆盖边界）及 `2026-10-11-windows-public-network-control-design.md:87–91`。旧研究日期保留，不当今天重新验证全部来源或20项名单。此片只实读两份Microsoft官方页面；页面均标注更新2024-02-22，接口代际是CAPABILITY_DROP0 / CLASSIFY_DROP2，没有仓库commit可声称。

- [Microsoft CAPABILITY_DROP0](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_net_event_capability_drop0)：仅借鉴network capability/filter/isLoopback字段合同；layerId不存在，null是必要边界。
- [Microsoft CLASSIFY_DROP2](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_net_event_classify_drop2)：filterId为LUID、layerId为层标识、isLoopback为loopback事实；这些字段不能单独证明socket/API因果。

采纳：既有严格scope、单页budget、API状态、SDK字段类型及脱敏摘要；收益是填补真实payload观测缺口。暂缓：filter/layer/provider对象查询和完整规则归因、仅查询现有loopback exemption；当前history观测不依赖后者，新增它不能解决query未尝试，故本片不设计必要调用也不执行。不适配：增加网络能力/权限、SetLoopbackConfig/豁免写入、改变collection策略、扩大范围、增加timeout或拿无事件证明DENY。

仅引用官方API机制，不复制官方或第三方代码/示例，不引入新依赖；因此无新增第三方源码许可负担。后续实现仍遵循本仓库许可；官方文档非开源Agent代码许可的替代证明。成本限定C/脚本/CI/合同/ABI同步及双架构CI观察，不新增系统安装、服务或权限。研究不是实际Windows结果，主阶段结束须在此记录实际采纳变化及新SHA证据；本片结束记录就是此DESIGN，不将拟实现写为具备。

## SPEC / QUALITY 自审

SPEC：无占位项；只有一片目标和唯一方案A；真实入口/正控scope明确；schema9所有已发现消费者列出；新字段类型、状态/null关系、ABI、计数与时间界限、错误与清理顺序均具体。no_match、not_attempted、limit/error分离，源码事实与继承CI事实分离。

2026-10-14 修订自审：按fresh SPEC对首版 `e16e051e…` 的C0/I1/M1反馈，明确history三阶段scope→scalar合法性→合法loopback比较，避免BOOL2被旧bool matcher吞为no_match或其他SID非法值污染scope；同时补两个PowerShell消费者删除临时回执前的固定日志投影/精度/隐私/限长合同及ABI三文件全同步。仅此DESIGN修订，未实施新matcher/日志/ABI或运行测试，不冒称问题已经修复到产品。

QUALITY：新增只此文档；源码/测试/CI/系统未改，无native/联网探针执行；两次官方文档读取仅为primary contract复核；没有隐藏权限增加、额外网络路径或实现信用。许可/成本/兼容及未来正负oracle均明确。独立SPEC与不同QUALITY审查尚由root安排，本段仅作者自审，不冒称独立通过。

【架构级自检报告】

✅ 语法/编译：Markdown结构自审；无代码修改，不声称编译通过。

✅ 依赖/调用链：实际argv→collector→history→writer及两类CI/Python消费者已核并列迁移点。

✅ 逻辑/边界：未尝试/零匹配/截断/错误分离，单页与字段上限具体。

✅ 异常处理：设计覆盖API/数据/时间/写入/清理故障；实际实现和故障测试未执行。

✅ 关联模块：仅文档落盘；未来C/脚本/CI/ABI/合同成对修改范围明确。

✅ 兼容安全：旧wire分支保留，禁止权限/豁免/collection写入；DENY门不变。

✅ 可运行性：本片为可审阅设计；原生与新实现未验证，R2/R3尚未通过。
