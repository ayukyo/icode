# WP0b：固定来源消费者的原生安装观测

日期2026-10-11，软件基线main `34c8bc66b4f91d2d3bc063d35fe22c634bd6a621`；固定vendor不变。用户委托推荐技术选择，继续现有路线，无服务、MSIX、新token权限或UAC。真实问题：新消费者已通过便携测试，但尚未在真实安装解释器执行；既有整链JSON不能替代其实际调用和失败回收。

## 最小方案与调用链

复用真实 `pin_installed_startup_sources()`、原生backend/reader、固定安装轮子CI及有界raw监督。新CI-only `scripts/probe_windows_installed_source.py`、便携契约测试；父侧signed安装阶段在现有整链观察后调用。生产模块、policy、setup/spawn不改。

先无包装调用无参生产入口，记录ready或既有政策拒绝的有限结果；随后独立调用，临时将入口模块的backend绑定换成真实委托子类，纯policy绑定换成参数/返回/异常完全保留的观测函数，退出后必恢复。两轮结果需一致；第二轮的原生回收信用不借给第一轮。第一次未知异常、第二次原生/reader/parser/漂移异常或不一致全部FAIL，不记录任意异常文本。

两轮都可能ready，也可能拒绝；拒绝仅在第二轮成功读取raw后的纯 `check_startup_security` 调用处认定三个既有固定错误：owner_untrusted、mutation_untrusted、empty_dacl。第一轮异常必须为同类同固定args；不能把reader返回同名异常自动当作政策拒绝。正常ready只证明本消费者调用成功，正常关闭后才输出；不额外revalidate，避免跨两轮漂移假定与翻倍预算。无包装轮仅记录其自身close_confirmed（若返回owner），不声称已观察拒绝轮全部原生回收。

无包装拒绝的null信用不是吞掉可见故障：生产若在政策异常上附加cleanup-unconfirmed备注，必须原异常失败并停止第二轮。纯policy正常无notes，观测可保守拒绝任何非空备注、非exact-list备注或不能安全读取的备注；读取失败不能替换原异常，不解析/输出未知文本。无备注仅表示未看到该标记，不证明第一轮原生回收，因此close_confirmed仍null。不得重试未知资源或用第二轮正常回收补第一轮可见故障。

## 真正原生回收账本

观测backend/reader必须委托原实现及实际ctypes函数；不制造HANDLE、SD、身份、path或policy pass。每资源新backend，按取得先后识别helper/verifier；`_open`成功返回记录acquisition ordinal，最多两资源各32节点。实际CloseHandle返回非零才记confirmed，任何零、调用异常、未知/重复关闭、顺序不符FAIL。全局关闭ordinal必须恰为全部成功取得ordinal逆序；资源/节点仅输出有限索引，HANDLE数值不输出。open中失败的额外清理也不得被隐去；其轮必须FAIL，不产完整回执。

GetSecurityInfo每次非NULL输出产生新的allocation ordinal，最多128；同一地址释放后可再次取得，不以全局地址去重。LocalFree必须实际收到对应非NULL输入并返回NULL才confirmed。GetSecurityInfo失败/中断后若非NULL输出也归账；释放未知、未配对、重复、顺序错误全部FAIL，永不重试旧地址。账本只保留当前active地址用于内部关联，输出不含指针/SD/SID。实际successful descriptor reads、allocations、confirmed frees严格一致；先发生原生故障不能包装为policy reject。

各节点policy事件记录resource、index、固定结果；必须是helper全链再verifier全链的无重复前缀。政策拒绝只能为最后事件，ready时必须全节点pass。当前预期helper/root首拒绝时，两组链已取得并全部关闭，但只执行该root的两次SD读取和一次政策判断；不给verifier或其它节点SD信用，不硬编码13节点。

成功回执必须满足security_reads=allocations=confirmed_frees=2×policy_events长度；每事件两次读取及释放须在内部账本绑定同一个resource/index，纯policy调用只能消费刚完成的该节点两份raw，拒绝终点后无更多SD读取。每事件也输出security_reads=2、confirmed_frees=2供严格关联校验。零SD而有policy事件、数量相等但节点错配均必须RED→拒绝。

## 输出、父侧及验收边界

单行规范ASCII JSON加LF/CRLF，严格duplicate-free、exact keys/types、source_sha/arch/python/windows匹配，最大32KiB。`validate_wire(wire, source_sha, arch, *, expected_python, expected_windows)` 两个必需keyword为实际版本整数列表；child传自身版本，父侧传当前实际版本（目标venv明确由该sys.executable创建、同一Windows宿主）。Python为[3,11或12]，Windows为实际major/minor/build；不能仅范围校验称匹配。compatibility_accepted、launch_authorized、protected_observed必须false；observation_complete及reverse_close_confirmed必须true。不要输出路径、SID、HANDLE、地址、SD、原异常、traceback；父侧严格校验后才打印，raw失败只固定错误。

有限schema冻结：top exact keys为schema_version(1)、scope(installed_source_consumer_observation)、source_sha、architecture(x64/arm64)、python、windows、observation_complete、baseline、consumer、resources、policy_events、security_reads、allocations、confirmed_frees、unconfirmed_frees(0)、close_order、reverse_close_confirmed、compatibility_accepted、launch_authorized、protected_observed。baseline exact keys outcome(ready/rejected)、close_confirmed：ready为true，rejected为null（该轮拒绝回收未观测，不借第二轮）；consumer exact keys outcome(同baseline)、reason：ready为pass，rejected为三种固定拒绝之一。resources恰helper/verifier两项，各exact keys resource、nodes(2..32)、opened、confirmed_closes、unconfirmed_closes(0)，opened/confirmed_closes均等nodes。policy_events各exact keys resource、index、result、security_reads(2)、confirmed_frees(2)，前缀及终点如上；SD三个成功计数等2×事件数且<=128。close_order每项exact keys resource/index，必须恰为取得顺序(helper全部后verifier全部)的逆序，无重复遗漏。整数拒绝bool；全部文字为exact str和固定枚举，无额外key或内容。

超时30s与raw32KiB由既有监督机制执行；未知pipe清理、超时、超量、非零exit、stderr、坏JSON都FAIL、不重试、不skip。旧整链观察及安装stages不变。新便携模块加入必需CI selector一次，fixture/class/method/subTest skip失败；计数取实际loader。四Windows格实际安装执行后才授原生观测信用；普通host、Win10、默认根兼容、目标叶负控、publisher/加载及首UAC仍独立未过。临时叶运输实验另片，不改系统卷根ACL或mock根使消费者ready。

## 研究取舍与成本

独立只读研究2026-10-11 14:15–14:17 UTC复核固定Codex8c0f701、SRT5507fb0及Apache2，无HEAD/全部20项刷新，root另核Microsoft主源。采纳显式生命周期、actual-return确认、allocation代次；暂缓guard/protected/publisher/UAC；不适配service身份、warn-and-continue、SDDL日志和host DACL重写。收益为证明固定入口真实调用及拒绝回收；成本为有限观测账本、严格schema和四格安装CI，无源码复制/新依赖/权限。

来源：[Codex home](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-service/src/ipc/home.rs#L80-L169)、[SRT self_protect](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/self_protect.rs)、[CloseHandle](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle)、[GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo)、[LocalFree](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-localfree)。两次快照与sharing仍不冻结ACL；以上只证明观测，不签发启动权限。

独立设计SPEC首轮I2已修复：SD与policy事件数量/节点关联、精确schema及版本预期来源；复核C0/I0/M0，不同独立QUALITY亦C0/I0/M0。没有使用研究替代实现/原生验收，Task1进入TDD。
