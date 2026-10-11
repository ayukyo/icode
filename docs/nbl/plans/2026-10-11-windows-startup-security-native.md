# Windows held-HANDLE 安全描述符运输计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development task-by-task。用户授权 main 直接开发，无 worktree/新分支；单写者，真实 RED→GREEN，独立 SPEC 后不同 QUALITY，root 最终提交。

**Goal:** 让 startup backend 从本次 active HANDLE 查询有界安全描述符，并完整验证 native allocation 的一次回收。

**Architecture:** 新 reader 模块仅负责 Win32 查询、复制与 LocalFree；backend 懒加载 reader 并先核 HANDLE ownership。纯 parser/policy 已冻结，但本片不接 provenance/UAC，不授角色授权、AccessCheck 或完整窗口。

**Tech Stack:** Python 3.11/3.12 ctypes/unittest、GetSecurityInfo；标准库、编译 -j1，无 SACL/额外特权/系统服务。

依赖 [纯权限合同](./2026-10-11-windows-startup-security.md) 实际完成发布后执行；此前测试在冻结验收期间不得改动。总路线仍为 [可信启动](../specs/2026-10-11-windows-trusted-startup-design.md)。

启动基线已核main/远端 `6216c420104097a03073ebdfecd5f30f5062c882`；纯片完整preflight三道通过、独立双审C0/I0/M0，原始源/测试保持其冻结摘要。Task1软件合同已实现并冻结，Task2独立单写者已启动；全片尚未发布或授原生信用。

## 真实问题、复用与调用链

backend 当前开对象没有 READ_CONTROL，也无 query_security；旧路径 ACL 查询不满足同对象。复用其 active HANDLE 验证、share-read/relative-open、固定错误与中断优先级，不更换 snapshot/share 或 provenance。新调用链：backend.query_security(active HANDLE) → lazy reader.read(HANDLE) → GetSecurityInfo → owned raw bytes → strict parser → LocalFree 确认 → raw bytes 返回。后片再由 pin owner 对整链检查角色与来源，不能因这里返回 bytes 就授 startup grant。

## 确定合同

新 `src/icode/windows_startup_security_native.py`：`WindowsStartupSecurityReader`，构造时仅 Windows 可用，读取实例只在内部 backend 懒创建。`read(handle: int) -> bytes` exact 正整数、指针宽度上界，拒绝 NULL/INVALID_HANDLE_VALUE；数字检查不是 ownership，backend 另 `_require`。reader 单 actor，同步查询，无路径、shell、写文件或 ACL mutation。

单 actor 同样约束整个 backend/owner：从 `_require` 到本次读取结束，不允许另线程并发 close/open，或其它调用方关闭/复用这个数值 HANDLE。当前不是线程安全接口，不把一次 active 登记检查写成并发生命周期保护；后续消费者必须保持该所有权约束，不引入通用锁框架来掩盖未验证链路。

显式宽度与 ABI（U32=c_uint32，U16=c_uint16，I32=c_int32，VOID=c_void_p）：

```python
signatures = {
    'GetSecurityInfo': ([VOID, I32, U32, POINTER(VOID), POINTER(VOID),
                         POINTER(VOID), POINTER(VOID), POINTER(VOID)], U32),
    'IsValidSecurityDescriptor': ([VOID], I32),
    'GetSecurityDescriptorControl': ([VOID, POINTER(U16), POINTER(U32)], I32),
    'GetSecurityDescriptorLength': ([VOID], U32),
}
local_free_signature = ([VOID], VOID)
```

使用 `SE_FILE_OBJECT=1`、`OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION=5`；owner/group/DACL/SACL 借用输出一律传 NULL，只接 descriptor 单 owned 输出。成功为DWORD0且 descriptor非NULL；原调用必须在 BaseException 清理保护中。读取不修改对象，descriptor ownership 不等同文件 HANDLE ownership；文件句柄仍属 backend/owner，reader 绝不 CloseHandle它。

OS 生成有效 allocation 是 TCB，不模拟任意坏地址。IsValidSecurityDescriptor 必须真，control API成功、revision1和SELF_RELATIVE；随后长度 exact int、20..128 KiB，再有界复制 `ctypes.string_at(pointer,length)`，strict parser 验证本次 owned bytes，raw control/revision与native回执一致。没有 accessor 借用指针，也不盲调用 GetLengthSid/GetAce；不自动转换 absolute格式。无效状态、缺输出、结构失败和未知格式拒绝，不能因 IsValid 真跳过 parser。

每个非NULL native descriptor 只尝试一次 LocalFree，包括 API 输出后抛异常的测试窗口。成功NULL才确认释放；非NULL/调用抛异常为 cleanup unknown，实例记录 cleanup_unconfirmed 并拒绝后续 read，绝不重试旧地址。无 descriptor 不调用释放。无主体异常时清理失败不给 bytes；有主体异常时保原异常，清理失败只加固定无地址 note，note自身故障也不覆盖原 KI/SystemExit。普通 DLL/调用错误固定消息，不泄露测试中的私有路径；KI/SystemExit身份保持。返回前必须释放已确认，只返回 owned immutable bytes，不能返回pointer或view。承诺限定到已测Python行事件，不宣称任意异步字节码原子性。

backend `_open` 增加 `_READ_CONTROL=0x20000`，不增加写/删除/系统安全权限，share仍1。`query_security` 先 `_require(handle)` 再懒创建 reader；closed/unknown/非法句柄不得触发 DLL 查询。constructor 原 kernel32/ntdll 两次加载及旧 mock fixture不变；lazy import失败或reader不可用保持拒绝，不走路径重开/旧查询兼容。

## Task 1：reader 与生命周期

**Dependencies:** 纯权限片发布
**Parallelizable:** No（单写者）

- [x] 新 `tests/test_windows_startup_security_native.py`，接口存在性先真实 assertion RED：`assertIsNotNone(importlib.util.find_spec('icode.windows_startup_security_native'))`；随后 class/read callable 缺失断言，不以 ImportError 作产品失败。
- [x] 真实 ctypes 测试自有合法 buffer构造 descriptor；fake DLL仅验证 ABI/生命周期，不授 Windows OS信用。按照以上 signatures 与 read合同实现新reader，不复制未知pointer，不改其它源。
- [x] 原生调用参数精确、success有界ownedbytes及释放1次；缺API/加载异常/非Windows；handle bool/零/INVALID/超指针；错误状态/NULL输出；IsValid/control/revision/absolute/length所有门；parser拒绝；API输出后OSError/KI/SystemExit；复制后中断；LocalFree非NULL/普通异常/KI/释放后抛异常；主体+清理复合异常和hostile note；unknown后重调零API/零重free。故障 buffer必须测试实际自有内存，不给任意伪地址解引用。
- [x] 运行 `.venv/bin/python -B -m unittest tests.test_windows_startup_security_native -v`，真实 RED→GREEN；自 SPEC/QUALITY 后冻结；主代理全文回读和实际验证，独立 SPEC→不同 QUALITY。

Task1 实际履历：接口缺模块 assertion RED，扩展13项 RED→GREEN；复制 OSError 固定消息回归真实 RED→GREEN。最终 reader115行、测试313行/20方法；独立SPEC初 C0/I0/M1（class/read callable少显式断言），仅补测试，patch模拟缺接口各1 FAIL/0 ERROR后恢复20 PASS，不虚构既有正确产品的RED。SPEC复核与不同QUALITY均 C0/I0/M0。root全文回读、新suite20/20 PASS，六模块关联144 run=138 PASS/6 Windows OS skip，0 F/E。冻结源 SHA256 `6e05d73c62d7b48918b3bcf75fefd3b5b47fe2b3fd679ebae5f5284752fb22e9`，测试 `335adc0c1bef6bac1140ba4733f2f731e6b70306db700f93841bb852acfda50a`。这是便携运输合同，不是 Windows allocator/padding、backend接线或整个阶段发布证明。

root随后对冻结reader串行20轮×20方法=400 PASS/0 skip/F/E；compileall -q -j1新源/测试通过。Task2修改后及全片发布前仍须按当前候选重新关联和完整preflight，不复用这里作全片信用。

## Task 2：backend 接线及实际对象负控

**Dependencies:** Task 1
**Parallelizable:** No（接口依赖）

- [x] 先在现 `tests/test_windows_startup_native.py` 补 RED：`self.assertTrue(access & 0x20000)`，新增 query_security callable 与 active/closed/unknown拒绝测试；实际命令 `.venv/bin/python -B -m unittest tests.test_windows_startup_native -v`。
- [x] 最小实现 READ_CONTROL 与 query_security lazy接口，原metadata/读取/ownership路径不变；真实 backend open的相同数值HANDLE交给reader，禁止替换或按路径重开。
- [x] 新 Windows-only class直接 backend开本次临时目录与文件，用 query_security拿bytes并parse，文件身份重核一致；返回后descriptor副本可用、fileHANDLE仍可读、close后query拒绝。测试重复查询及文件/目录；只处理自己创建对象，不修改宿主ACL/配置。非Windows明确平台skip，Windows夹具/API失败不得skip。此勾选指实现，实际Windows运行仍待Task3发布后。
- [x] 默认创建对象及不同继承状态的 native 描述符可解析性必须实际验证：官方 API 不承诺所有空闲/未引用字节为零，冻结 parser 的严格子集可能拒绝有效 OS 描述符。此时记录具体格式与兼容缺口，不以假 DLL零 padding通过冒充原生兼容，不自动放宽冻结 parser；128 KiB仅内部预算，不称 Windows所有描述符通用上限。本勾选仅授下面四台实际runner的默认fixture子集。
- [x] 自审、主代理关联、独立双审；共享锁六项保留，本机按平台明确skip，Task3另做新SHA实机回归，本片实际原生新增门单独计数，不复用前SHA作通过。

Task2 未发布观察：初次backend缺READ_CONTROL/query接口，38 run/6 assertion FAIL/6平台skip的RED→GREEN；backend仅20+/1-，总访问0x120081、share仍1。独立SPEC初 C0/I1/M0：两个对象的名称与查询成功不能证明不同继承形态。仅补测试helper（存在性1 assertion RED→GREEN），真实parsed合成bytes证明不同形态通过、相同/缺目录传播/缺文件继承位均拒绝；native直接消费实际两对象snapshots、缺形态FAIL、不改ACL。SPEC复核C0/I0/M0，不同QUALITY仍待。root回读当前差异、五模块142 run=134 PASS/8 nt skip、compileall -j1/diff check通过；backend SHA256 `75573a42212daaedb3ca570e975305ec772ee67c428dc9df29ec32283e9cd862`，测试 `8a520682dcb5fe54bd6c2c24c4ca1b35e8e0c05243950dcc3f700a4f26b66310`。NativeTransport30、NativeModule3、旧原生共享锁6、新query2；冻结reader/parser不变。所依据[Microsoft ACE继承规则](https://learn.microsoft.com/en-us/windows/win32/secauthz/ace-inheritance-rules)与ACE_HEADER已经主代理独立回读，但官方语义及Linux合成负控不算Windows实测。

## Task 3：必需 CI 与发布

Task2双审最终刷新：随后不同QUALITY C0/I0/M0、独立实跑142=134 PASS/8平台skip，候选摘要与reader冻结摘要一致；上述“QUALITY待”仅是其前窗口。Task3单写者已启动，前两Task源/测试保持冻结，CI计数/选择/版本格未完成前不运行发布。

**Dependencies:** Task 1, Task 2
**Parallelizable:** No（全部冻结后）

接线后的未完成窗口：root单跑旧CI两项计数合同，实际2 FAIL/0 ERROR（NativeTransport 30 != 25），系新增五个方法而旧计数仍固定25；这是Task3待同步项，不绕过或把当前全片称为通过。Task2独立双审尚在进行，尚不发布。

Task3候选已冻结：12个合同方法188 assertion FAIL/0 ERROR→12 PASS，新增安全六便携类与两nt类实际选择posix129/nt137 unique leaves，方法/夹具/嵌套subTest的skip必须失败，旧optional仍通过。workspace仅转六格include和setup实际消费版本，权限/其它步骤不变。root全文回读四文件差异、七模块加完整workflow合同共201 run=193 PASS/8平台skip/0 F/E；portable startup加CI 139方法串行20轮=2780 PASS/0 skip/F/E，compileall -q -j1通过。tracked diff与两新增文件no-index检查无格式诊断；新文件exit1表示新增差异，不算格式失败。完整preflight session27653已启动，密钥与子模块两道通过，测试守护仍在运行，不提前授最终门通过。全片独立SPEC正在收束，随后不同QUALITY，不用Task1/2批准替代本次全片审查。

CI片冻结SHA256：selector `fd2ad550b8c5754548ca1a2fbbeebeb11ba175524a611b9381a94e88beb45b57`，pin CI tests `bc68706a7c5a18ceaefc209f2c920dcef91a448a8f86659c405ff5e375f349b1`，workflow `e672781afcd413d4ebb2a8699fef7c6f7af955703b12eca3e0396d7da3814dd9`，workflow合同 `254cbf8fddd9e2f52f578c80c5535b31360f47966046ad21289824435841c113`。Task1/2源/测试冻结摘要均保持。

- [x] 完整回读 `scripts/run_workspace_ci.py`、`tests/test_windows_startup_pin_ci.py` 与新 reader classes；给新安全parser/policy/reader便携类恰好一次选择、Windows native类仅nt，扩展 selected_pin_ids 前缀与对应 body/fixture/subTest拒绝门。旧可选skip语义保持；新选择器和必需skip测试实际 RED→GREEN。
- [x] `.github/workflows/ci.yml` 的 workspace 最小加入 Windows Python3.12 两格，同步 `tests/test_ci_workflow_contracts.py` 的 `TestCrossPlatformWorkspaceEvidenceCi` 六格和setup实际消费版本合同，不只是把3.12写进job名。不新增CI权限、特权或用签名安装job代native query信用。Windows10/普通host仍另记缺口，不能用hostedWindowsServer替代。
- [x] 主代理运行 `.venv/bin/python -B -m unittest tests.test_windows_startup_security tests.test_windows_startup_security_native tests.test_windows_startup_pin tests.test_windows_startup_native tests.test_windows_startup_pin_ci tests.test_windows_provenance tests.test_run_workspace_ci`；方法数/skip取实际输出。新便携类20轮无skip/F/E，冻结摘要不变。
- [x] compileall -q -j1 touched源/测试/selector、diff check、站点/文档两轮、全片独立SPEC→不同QUALITY、完整preflight三道均通过；据实七维报告，root精确暂存commit/push main及远端核SHA。
- [x] 新SHA Windows x64/ARM64×3.11/3.12 对实际选中原生query/共享锁方法逐格核作业与日志；失败继续阻断不回退。本片通过仍不闭合 owner权限窗口、publisher/DLL/UAC、WP0b/WP1/2或R2/R3。

## 研究取舍

全片独立审查最终刷新：SPEC与随后不同QUALITY均 C0/I0/M0，八个冻结摘要一致。SPEC七模块179=171 PASS/8 skip，workflow22 PASS；QUALITY合并八模块201=193 PASS/8 skip。QUALITY独立核posix129/129 unique、nt137/137 unique，原optional语义保持。此结论只关闭软件实现审查，完整preflight、提交和新SHA实机门继续分别记录。

独立研究沿2026-10-11固定Codex/SRT版本及Apache2许可，见上片完整链接；主代理另核 [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo)、[IsValid](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-isvalidsecuritydescriptor)、[Control](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptorcontrol)、[Length](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptorlength)、[LocalFree](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-localfree)。采纳HANDLE查询/单owned副本/一次free；不适配unchecked free、长度当allocation证明或path重开；暂缓AccessCheck/RX和整窗授权。无代码复制、新依赖或特权，收益/信用仅针对本片实际测过的运输合同。

独立只读计划复核未发现必须重设计项；另指出单 actor须覆盖整个backend生命周期、OS padding不保证零两项边界，主代理已补入。此为设计研究，不是新原生通过证据，也未重新刷新上游HEAD。

2026-10-11 11:06–11:07 UTC 独立运输研究结束，主代理随后独立取固定源码复核：Codex [`acl.rs:99–132`](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/acl.rs#L99-L132) 按 HANDLE 查询、返回借用 DACL 与 owned SD；[`283–285`](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/acl.rs#L283-L285) 和 `354–356` 手动释放但不核返回值。SRT [`self_protect.rs:173–207`](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/self_protect.rs#L173-L207) 的诊断路径先释放 SD，后释放独立 SDDL allocation；[`util.rs:87–94`](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/util.rs#L87-L94) 忽略 LocalFree 回执，`161–213` 的 OwnedSd guard 与该诊断路径不同。采纳单 owned 对象与清理职责分离；不适配 unchecked free、独立 allocation 混为一次 ownership 转移或上游正常路径当作 Python 中断覆盖证据。ICODE 增加 unknown 隔离、主体异常优先及一次释放故障测试；无源码复制、依赖/许可变化或额外特权，代价为保守拒绝与单 actor 约束。该观察不是上游实际泄漏、安全漏洞或 Windows 验收结论；原研究行号经固定 raw 源校准，未刷新 HEAD。

**Execution Mode:** serial

阶段结束研究观察（11:21–11:22 UTC，CI实施尚未结束）：独立只读回核冻结Task1/2，未出现新方案分歧，保持同HANDLE READ_CONTROL/ownership与once-free unknown隔离取舍。不同继承flags明确断言和相同/缺标志负控已对应实现；源码测试不代Windows成品运行。实际四格默认descriptor子集、身份稳定、继续读、关闭后拒绝及旧共享锁均仍待；Win10/普通host另记，无HEAD刷新、代码复制、依赖/许可/特权变化。

## 软件交付检查终态

2026-10-11 11:34 UTC，root新完整preflight session27653实际exit0，密钥、固定子模块和全仓测试三道全部通过；此前“测试仍在运行”是更早观察窗口。未从守护隐藏输出猜测总测试数。此结果与本片201关联、20轮2780 PASS、全片SPEC/不同QUALITY C0/I0/M0分开记账，未授Windows原生或R2/R3信用。vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`保持clean；main精确提交/推送待下一实际动作，不提前猜SHA。

【架构级自检报告】（本片软件合同）

- ✅ 语法/编译：导入、compileall -q -j1及格式检查通过，无新本机工具链。
- ✅ 依赖/调用链：active HANDLE→lazy reader→owned bytes→冻结parser完整；无路径重开或CloseHandle ownership转移。
- ✅ 逻辑/边界：ABI、范围、回执、唯一选择、继承形态正负控通过；20轮139方法无skip/F/E。
- ✅ 异常处理：所测output后错误/中断、一次LocalFree、unknown隔离、主体优先与必需skip拒绝合同通过；不声称任意字节码中断原子性。
- ✅ 关联模块：201 run=193 PASS/8平台skip；新完整preflight三道exit0；workflow/selector同步。
- ✅ 兼容安全：共享模式仍1，旧optional skip语义及其它CI步骤/权限保持；实际Windows默认描述符兼容待四格验证。
- ✅ 可运行性：Ubuntu软件合同可运行；原生共享锁6+query2未在本机执行，不报告Windows/Win10、完整WP0b或R2/R3通过。

实际发布刷新：root已提交推送main `0d40c2577316bfa52e9c595dfcd4e388ecd8c28c`（11文件838+/49-），git ls-remote再次核远端同SHA，发布后工作树clean；此前“发布待”保留提交前窗口。新CI38136150544与来源38136150536已触发，原生四格尚无结果；下一步只按新SHA日志验收，不复用6216的旧测试信用。

原生运输刷新（2026-10-11 11:45 UTC后）：同SHA [CI38136150544](https://github.com/ayukyo/icode/actions/runs/38136150544) 的 x64/3.11 job114460308562、x64/3.12 job114460308565、ARM64/3.11 job114460308547、ARM64/3.12 job114460308481 均completed/success，root逐份日志核 `python scripts/run_workspace_ci.py` 与实际775 tests/20 skips。当前selector实际加入新安全六便携类、旧共享锁6与新query2，全部必需method/fixture/subTest skip均阻断，因此这些skip仅为其它optional项目；默认对象及两种实际继承形态运输门关闭，不推广为任意Windows描述符兼容。随后junction3和leased lifecycle75均OK。四份日志另有既有 `_readerthread` UnicodeDecodeError（非本片query错误），保留为独立诊断待查，不据job success声称所有异常已消除。Linux/macOS workspace也success。完整CI仍在运行且Windows Reviewer另有失败，不能把本片四格success等同R2/R3总体通过；来源/安装及Win10/普通host信用分别追踪。下一身份只读子片可开始。

同SHA Reviewer 原生日志另核：x64 job114460308676、ARM64 job114460308662 均failure；两族host control真、network attempted真、connected假、connect_denied假，error10035且wait_expired真、canary假；cap诊断exit91/ipv4_connect/credit=false，最终assert78!=0。observer订阅成功不能改此因果边界，继续fail-closed，不报告网络DENY或R2/R3通过。软件运输片保持自身完成范围，后续身份设计见[原宿主身份](../specs/2026-10-11-windows-host-identity-design.md)。

11:53 UTC终态：CI38136150544 completed/failure，46 jobs=41success/2Reviewer failure/3skipped；Python3.11 job114460308507与3.12 job114460308529全仓各2728 tests/79 skips均OK。Public website38136150543 success，来源38136150536四install仍在跑。此前“完整CI仍在运行”保留早期窗口，最终状态不能以41success覆盖两个失败。

随后来源38136150536的validate及四attest/install jobs114462667791（x64/3.11）、114462667788（x64/3.12）、114462667805（ARM64/3.11）、114462667786（ARM64/3.12）均completed/success；只授同SHA实际签名安装/静态scope信用，不等于新身份/UAC/完整启动。解码诊断见[独立报告](../windows-ci-verifier-encoding-diagnostic-2026-10-11.md)，修复与新Windows验证尚未发生。
