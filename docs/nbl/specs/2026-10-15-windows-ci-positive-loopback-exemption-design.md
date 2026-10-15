# Windows CI 正控 loopback 临时豁免设计

日期：2026-10-15。状态：待完整评审的 DESIGN，不是 PLAN、已实现能力或原生验收。
权威工作区：WSL `/home/orbbec/projects/icode`；观察 HEAD `b341cb1f010942d99f56861f9eff0ff60f84fc57`，vendor 固定 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。
本次只新增本文；已有 GIL 诊断/进度文档 dirty 属其它作者，保留。root 已记录新用户授权和实际三步思考 `4b41e4`，本文作者不冒称亲调。

## 1. 问题、授权与非目标

现有固定 privateNetworkClientServer 正控在标准用户下运行，完整 GetConfig 样本可以显示 target 不在豁免中，却不能证明实际 WFP 允许或失败根因。新增实验只为在同候选 GitHub 临时 Windows runner 上，以独立正控 SID 临时豁免，证明固定双栈 loopback 通路；不修改产品零 capability Reviewer 的权限或判据。
用户新授权仅覆盖该临时正控 SID 的添加、删除及验证。正控 SID 与 Reviewer SID 必须不同，二者均不得预有豁免；不因预有条目而先删除再创建。产品/Reviewer SID 任何时候都不添加豁免。
不增加 capability、MSIX、服务、外部目标、云端 peer、token 权限或本机操作授权；不改防火墙 policy、private range、网络分类，不授通用提权入口。非 CI、self-hosted/shared runner、非固定探针、普通 CLI/模型请求一律不进入此实验。
本设计存在系统非原子边界：仅在专用、临时、无其它豁免写者的 runner 窗口可实施；若要求在未知并发写者下无条件保证其它 SID/Attributes 从未被覆盖，下面 API/CLI 均无足够官方合同，必须停止，不能降格为“最终看起来相同”。

## 2. 已读实际链与冻结观察

| 实际入口/依赖 | 当前事实 | raw SHA256 |
| --- | --- | --- |
| `tests/test_windows_appcontainer.py:8245` 起正控链 | host 双栈 listener → staged Python → 独立 capability profile/nonce → run → 精确 payload 比较；不是 parent 脚本 main | `e5b421b994c5866a60ff72feff6db68f8e037151c6f6b59331ce4c900513c81d` |
| `src/icode/windows_appcontainer.py:1280` 附近包装器 | 固定 CI argv/单 capability guard；1592 CreateProfile，1781 finally DeleteProfile | `307dc730bf28bc661ad99b8d02dc9093b51c1dcdf45f993b470e68a5562f1a1f` |
| `src/icode/windows_job.py:509` | 固定 `-I -c` payload、nonce/SID/端口白名单；不接受通用命令 | `ac2bfbe924a9b03b68ab0304f55cfcfde7b79615c3563c0db61ca099d335d640` |
| `native/windows/icode_positive_loopback_config.inc` | 147 行，只 Get，不 Set；只输出目标采样，不输出完整列表 | `194a6902cb828a71cac25c10b3bb66a1189355c888f7d51b724cc31c895de977` |
| `native/windows/icode_wfp_event_probe.c` | 现有观察 helper，不授任意变更 | `1796d36ca0964d685a7d0aeedb8bbabd3d29a8eb7c209255310f1ee6769ad596` |
| `.github/workflows/ci.yml:560` 起 Reviewer job | x64/ARM64、25min；admin parent 创建标准用户、固定 observer、现有 finally | `9825850137f1b244940bd7fc412af8f1e72d81c052384e93c75fe702243cefc6` |

现有 probeRoot 授标准用户 Modify，不能放 admin 将执行的脚本、可信账本或权限回执。现 WFP target/ready 协议是观察协议，不能原样当作授权。现只读 Get include 不能证明其它条目及 Attributes 未变；必须另有 admin 完整列表验证边界。
外层 `try: run_windows_appcontainer(...)` 前加、返回后删不足：尚未证明 profile 创建成功，返回时 profile 已删除。必须增加仅正控的内部生命周期检查点；不改其它启动路径或已有通用 result/错误首因语义。

## 3. 官方合同、选项与选择

观察日 2026-10-15；以下为 Microsoft 官方文档，不是本机执行或裸 profile 成因证明。

| 方案 | 合同/收益 | 成本与限制 | 决策 |
| --- | --- | --- | --- |
| 固定系统 `CheckNetIsolation.exe LoopbackExempt -a/-d -p=<SID>` | 官方归档明确单 SID 添加/删除；不由 ICODE 提交完整替换列表，SID 不依赖 admin/标准用户 HKCU 名称映射 | 文档未承诺原子单项更新或无并发丢失；工具退出码不替代 Get/实际 nonce/恢复验证 | 采纳，唯一 mutation 路径 |
| `NetworkIsolationGetAppContainerConfig` + `NetworkIsolationSetAppContainerConfig` | desktop API；Set 要求调用者先 Get 并保留原条目 | Set 是全列表输入；自行 merge/read-modify-write 存在竞争；旧快照恢复会覆盖他人，连空列表也不允许 | 本片不采用 Set，不加载/调用其 export |
| 仅原 Get 观察、不豁免 | 无系统写，保留现未知事实 | 不能满足新增正控前提实验；不允许用 timeout 充 DENY | 保留为观察，不替代实验 |

官方依据：[GetConfig](https://learn.microsoft.com/en-us/windows/win32/api/netfw/nf-netfw-networkisolationgetappcontainerconfig)、[SetConfig](https://learn.microsoft.com/en-us/windows/win32/api/netfw/nf-netfw-networkisolationsetappcontainerconfig)（均页面更新 2026-03-27）；[官方旧版 CLI 合同](https://learn.microsoft.com/en-us/previous-versions/windows/apps/hh780593(v=win.10))（2015-08-31，含 SID `-p` 添加/删除）；[当前 UWP 排障](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/troubleshooting-uwp-firewall)（客户端出站 `-a`，与服务器入站 `-is` 不同）。旧文档的 Unicode 横杠示例不能逐字当 argv，实际只用 ASCII `-a`、`-d`、`-p=`。
适用性界限：UWP 文档说明 loopback 调试前提，不单独证明本仓 CreateAppContainerProfile 的具体 packet 失败原因；本设计必须由未来同 SHA 原生实验验证。无需复制 Microsoft 示例代码，不引入第三方实现/依赖；系统工具/SDK 使用遵循 runner Windows 许可，文档仅机制链接与转述，无许可不明代码拷贝。

## 4. 信任模型与固定 one-shot 协议

执行者仅现有 admin workflow parent；它自己生成 positive profile 名称、Reviewer profile 名称和 128-bit 随机 nonce，分别 Derive SID 并确认不等。标准用户改为使用这两个预分配名称，不能自行提交待提权 SID。所有输入均 exact schema/type/大小写、长度上限及无重复 JSON keys，未知字段拒绝。
admin manifest 固定 schema 1、repository、候选完整 SHA、run_id/run_attempt、job/matrix 身份、临时标准用户 SID、PID+creation time、两个 profile/SID、nonce、允许地址仅 `127.0.0.1`/`::1`、本次冻结端口、单调 deadline 和 session id。GitHub 身份来自受信 workflow 上下文，不接受请求覆盖；nonce 只防串单/重放，不被说成对恶意标准用户的秘密认证。
admin 自有独立目录由 Administrators/SYSTEM 持有，标准用户仅可读固定配置/只读回执，不能改账本、替换工具或删除父目录。独立请求槽才准许该临时用户写；固定文件名、父目录 ACL、无 reparse/hardlink、持有句柄读取、一次性消费，路径从不来自请求。fallback 只用受信 job 记录的精确目录，不扫描 user 目录选目标。
请求最多 4096 UTF-8 bytes；只含绑定值与枚举 `profile_created`/`probe_finished`，不含 executable、脚本、命令、路径或自由操作码。端口由本次真实 listener 分配并冻结一次，必须 int 非 bool、1..65535；请求不得更换端点/nonce/身份。端口是匹配证据，不成为提权命令参数。
只有同时满足 GitHub Actions、Windows、github-hosted 临时 runner、明确新增授权开关、固定 workflow/job/candidate、现有 staging/capability 固定 argv guards 和 admin manifest，才能启用私有 session；伪造环境变量本身不足。admin 从 manifest 派生唯一 SID，不相信请求 SID；请求不匹配、重复、过期、进程已退出均拒绝，禁止自动重新添加。
admin 通过 `GetSystemDirectoryW` 固定定位系统 `System32/CheckNetIsolation.exe`，显式完整路径、核系统文件身份及当前架构/版本、无 shell/PATH/cmd 拼接；不信用户可改的SystemRoot环境变量。只允许三个固定 argv 元素 `LoopbackExempt`、`-a` 或 `-d`、`-p=` 加 admin 预绑定 SID；禁止 `-c`、`-is`、自由 `-n`、其它模块/目标。admin 完整 Get 读取器也必须来自本候选受保护构建位置，不能执行标准用户可写 staged helper。
这是现 workflow 内的一次短生命周期协调，不安装服务、计划任务或监听网络的 broker，不开放新的产品/模型提权入口。

## 5. 生命周期与精确恢复

```text
admin 固定 manifest/完整 baseline → 标准用户 CreateProfile 成功
 → 内部 created 握手 → admin 精确 add + Get 验证 → 只读授权回执
 → 标准用户固定双栈 payload → Job 实际回收
 → admin 精确 delete + Get 验证 → 内部 finally/原 ACL 与 profile 清理
 → 测试核两个 nonce payload、恢复回执 → Reviewer 零 cap 原实验
独立 workflow always fallback：仅按 admin 账本接管未完成的同一 owned SID 清理
```

完整 baseline `B` 是按 SID 二进制值比较的无重复映射 `SID → uint32 Attributes`，不按名称/格式化工具 stdout 比较，不以数量相等冒相同。Get 必须验证 API code、count≤4096、有效指针/SID/Attributes、完整释放和进程回收；错误或超限为 unknown，不能截断后使用。所有 SID 及数组按官方 HeapFree 配对，派生 SID 按 FreeSid；reader 无 Set 权限入口。
添加前两次完整读取必须一致，positive/Reviewer 均不在 `B`，证明当前没有预有豁免；已有 positive 条目即拒绝且永不删除它。两次读取稳定不是全局锁或独占证明。workflow 必须声明同 runner 无其它 exemption writer，串行协调自己的所有操作；合作 mutex 只能防本项目并发，不能防未知系统写者。若 runner 不满足专用前提，添加前拒绝。
标准用户包装器新增私有可选 session（默认 None 完全旧行为），只在既有 capability 固定正控路径接受。必须在本次 `CreateAppContainerProfile` hr==0、有效 SID 与 admin 预分配 SID 相等之后，在任何子进程 launch 前同步 created；非零/已存在 hr 不能接管。session 固定协议，不接受任意 callback/命令；传入错误类型/其它诊断路径均拒绝。
admin 验证创建握手、身份/窗口，先持久化自己的 `add_intent`（baseline 摘要、原始 manifest、精确 SID、操作实例），再只调用一次 add。创建成功事实由真实标准用户包装器采集；admin 授权范围始终是自己预分配的独立随机 profile，不由该声明扩展到任意 SID。
add 后 Get 的 `A` 必须恰是 `B` 加唯一 positive SID；其 Attributes 原值记录为 `a`，其余所有 SID/Attributes 逐一不变，Reviewer 仍不存在。退出码非零、超时、缺回执不能启动 payload；即使工具失败也必须检查实际配置，不能假定未添加。仅“add 已尝试、原来不存在”的账本授予窄清理资格，不授成功信用。
标准用户只有接收匹配的 admin 只读回执后才能执行原固定 argv；仍是原标准用户、原 profile/token 验证、单 private capability、原12s Job预算/真实回收。callback/session 失败不折成普通观察 unknown 后继续。listener 本次 host canary 验证清空后，双栈必须各恰收一个原有完整 JSON payload，含同 nonce/SID/1cap；错误 nonce、重复、只有一栈均不通过。
正常 finally 必须在 profile 删除前请求精确删除并等待验证；无论 payload/断言/Job 是否失败都尝试 owned 清理。不能用 `capability_control.cleanup_ok` 为 true 才清理豁免。未确认 Job 回收时先停止本次进程树，清理状态保持失败；豁免移除仍由 admin own SID 执行，不被标准用户的结果字典阻断。
删除前重新 Get 当前 `C`：目标不存在时只确认幂等 absent，不再调用 delete；目标存在且与本次已记录 `a` 相等（或 add 结果未确定、但有原 absent+add_intent 的唯一所有权）才执行单 SID delete。若目标被其它写者接管/Attributes 冲突，所有权不明，不能擅删，保留故障账本并 failunknown。
清理只移除 owned target；永不 Set(B)、清空列表、逐项重建或删除 foreign 条目。delete 后 `D` 必须等于本次删除前 `C` 减去 positive；所有其它 SID/Attributes 逐一相同、Reviewer absent。正常无并发成功还要求 `D == B`。若 `C` 出现 foreign 变动，保留该变动并可窄删仍 owned target，但本次完整恢复不通过；不“修复” foreign 差异。
若发生未观测到的并发丢失/ABA，Get 前后对比不能证明中间没有覆盖；CLI 内部无公开 CAS 保证。此项是独占 runner 前提的残余限制，不可以收据掩盖。用户若不接受该限制，必须停用本方案，而非默认换 Set。
独立 `if: always()` 清理 step 使用 admin 原账本、相同 session，先确认原 add/delete 进程已实际退出，防止晚 add 与 delete 竞争，再 fresh Get/必要的唯一 SID delete/验证。已确认 absent 则幂等完成；损坏/缺失账本、不明所有权或无法回收时禁止猜 SID。parent finally 失败后不能删掉该账本或用临时账号/profile 删除抵销错误。
建议上限：沿用既有180s准备等待；从 add_intent 起单调60s窗口，原12s payload不变；Get和CLI每次工作≤5s，超时终止后最多2s+2s等待实际回收。窗口耗尽禁止启动/授成功但不取消清理义务；fallback独立≤30s。不增加25min job预算，不宣传这些工作/回收预算是所有OS路径hard deadline。
workflow always 在 runner 丢失/强制终止时也不保证执行；此时恢复是 unknown、候选失败，保留外部可得证据，不声称 runner销毁/profile删除就是验证恢复。未满足恢复证据不得启动后续 Reviewer 或报告该候选通过；first error保留，cleanup失败另列，不覆盖原错误为成功。

## 6. 输出、隐私与验收分账

admin 账本保存完整 baseline/add/predelete/postdelete 原始读取结果、来源hash/时刻/完整性/释放及命令PID、退出码、回收事实和状态转换。位于admin-only目录，不放user可写probeRoot；原件留到独立fallback验证完成，随后按既有临时证据生命周期处理，不上传完整机器SID名单或命令输出中的其它应用信息。
导出固定 schema 1 紧凑收据：candidate/run/job/session绑定摘要、pre_absent、created_owned、add_verified、both_nonce_received、delete_verified、others_preserved、reviewer_unexempt、cleanup状态、原错误/清理错误阶段及原始证据摘要。unknown用null/明确状态，禁止构造true补齐。普通 stdout 有界行，每条JSON仍≤500bytes，不新增 Actions annotation 槽；完整schema分固定语义记录，不截断、不自由分片。原3条只读采样日志及其含义保留，不能硬改其比较为allow证据。
成功必要条件为：授权/身份/所有权有效 + 原固定token/profile/capability校验 + 双栈精确nonce收包 + add/delete/其它SID及Attributes验证 + Job/ACL/profile各自清理确认。loopback正控为“带显式临时豁免的本机通路可达”；不是 privateNetwork 单独充分、真正外部private网络可达或原35e timeout唯一根因的证明。
零 cap Reviewer 的 profile、token、原错误/DENY证据规则保持不变：其SID从未豁免；正控清理后重读完整配置确认才继续。没有相关WFP精确drop/capability证据时timeout/no-match仍inconclusive，不能把正控成功直接授Reviewer DENY/readiness/product隔离完成。候选所有旧必需门仍保留，同一SHA x64与ARM64原生均须验收。

## 7. 软件、原生与恢复矩阵

以下是未来实施验收要求，本次未运行测试、CLI、Windows API或本机网络。软件用真实producer/serializer/parser及假OS边界，不把mock调用次数当系统恢复证明；新协议设施可先自校验，不虚构旧产品bug RED。

| 场景 | 软件判据 | 同SHA GitHub Windows原生判据 |
| --- | --- | --- |
| 正常baseline含非空foreign条目/非零Attributes | 完整映射与顺序无关；添加仅目标，删除仅目标，实际回执全链 | 读取runner原有条目而非为测试修改别人；前/加后/删前/删后原件、x64/ARM64双nonce及owned清理 |
| 非CI/未授权/伪环境/self-hosted/错workflow或candidate | mutation零次、fixture不变 | 未授权负控不改系统列表 |
| positive==Reviewer/错SID/name/nonce/端口/过期/重复/未知keys | 入口及admin双拒绝；不执行任意path/argv | 固定拒绝回执，Get证明未变 |
| Create失败/已存在profile/无效SID | 无add、保留首错误，不删除不owned profile | 独立固定fixture制造创建拒绝；无接管旧profile |
| positive或Reviewer预有豁免 | 拒绝且不删；非空baseline/Attributes保留 | 原生fixture仅可用本次manifest同一admin预分配positive SID，先记自有setup intent/receipt，再建立条目；拒绝路径不得接管，仅对应setup账本授权其teardown并验证恢复。Reviewer预有豁免仅软件模型/被动实际观察，绝不原生主动添加；不得另建SID或改foreign。修订历史：原版freshSPEC C0/I1/M0，指出另建SID及setup归属未限，本行收紧，待fresh复审 |
| Get失败/重复SID/无效内存/4097/释放或回收失败 | unknown、不截断；无add或转owned清理 | 合法错误边界可注入，不伪称真实内核坏指针测试 |
| add非零/超时/已写后丢回执/standard进程退出 | intent在先；不启payload；实际配置决定窄清理；fallback一次接管 | 有界故障点、工具实际回收与Get原件；晚add未回收不得并发delete |
| wrong/重复nonce、仅IPv4或仅IPv6、原105timeout | 正控失败，finally仍清理；不授DENY | 真实listener收包/退出码与原错误保留，所有owned资源回收 |
| delete失败/超时/读后未确认/正常finally被中止 | cleanup failunknown，不因profile消失变通过 | 独立always重新Get，仅owned目标可删；末次absence与其它条目逐一验证 |
| foreign新增/删改Attributes、目标ownership冲突 | 不快照回滚、不删foreign；即使target清掉本片仍失败 | 不为负控改runner他人条目；软件覆盖并发分类，原生只观察实际异常，不声称穷尽race |
| 重放旧run/job/session、账本损坏或普通用户改receipt | exact绑定/ACL拒绝、无猜测清理 | 真实NTFS ACL/路径替换拒绝，标准用户不能修改admin账本或运行任意admin程序 |
| runner取消/损失、always未执行 | 模型明确unknown非通过 | 只报告实际可得清理证据；缺证据门失败，不能拿再次rerun覆盖旧失败 |

## 8. 实施范围与审查停点

未来最小关联面为：上述真实TEST正控链、windows_appcontainer仅正控session检查点、admin受保护完整Get/固定CLI协调及Reviewer workflow finally/always接线、严格软件TEST与CI依赖门。不得把修改落到parent脚本main假装覆盖本链；不得把原Get include改通用写配置helper。具体文件/patch/count/hash须后续独立PLAN冻结，本设计不提供自动实施授权。
顺序为 root全文与freshSPEC/不同QUALITY → 未来完整PLAN双审 → 不同TEST/SOURCE作者TDD与窄软件回归 → 同新SHA两Windows原生门；任何阶段失败保留原始退出和unknown。现有Actions预算、旧CI门、parser权限与vendorpin不变。
作者selfSPEC：范围、非原子限制、None兼容、实际Create/launch/delete接点、两种清理与证据分账已逐项核对；无TODO/占位、无系统操作声称。
作者selfQUALITY：独立反向检查预有条目误删、晚add、foreign属性丢失、user可写路径提权、profile消失冒恢复及unknown补true；均有拒绝/清理归属要求。不是fresh独立审查零结论。
【架构级自检报告】
语法/编译：Markdown结构与路径静态检查；本片无代码编译。依赖/调用链：已定位真实TEST→包装器→固定payload→admin/fallback边界。逻辑/边界：单SID、双栈、非原子/晚结果限制明确。异常处理：矩阵含授权/创建/读取/添加/回收/删除/恢复unknown。关联模块：只设计未来必要关联面，本片仅新本文。兼容安全：None及旧Reviewer/权限/CI门不变为未来硬约束。可运行性：设计静态通过，软件/Windows原生尚未实施验证，不能声称100%运行通过。
