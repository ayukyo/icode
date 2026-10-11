# Windows held-HANDLE 安全描述符运输计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development task-by-task。用户授权 main 直接开发，无 worktree/新分支；单写者，真实 RED→GREEN，独立 SPEC 后不同 QUALITY，root 最终提交。

**Goal:** 让 startup backend 从本次 active HANDLE 查询有界安全描述符，并完整验证 native allocation 的一次回收。

**Architecture:** 新 reader 模块仅负责 Win32 查询、复制与 LocalFree；backend 懒加载 reader 并先核 HANDLE ownership。纯 parser/policy 已冻结，但本片不接 provenance/UAC，不授角色授权、AccessCheck 或完整窗口。

**Tech Stack:** Python 3.11/3.12 ctypes/unittest、GetSecurityInfo；标准库、编译 -j1，无 SACL/额外特权/系统服务。

依赖 [纯权限合同](./2026-10-11-windows-startup-security.md) 实际完成发布后执行；此前测试在冻结验收期间不得改动。总路线仍为 [可信启动](../specs/2026-10-11-windows-trusted-startup-design.md)。

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

- [ ] 新 `tests/test_windows_startup_security_native.py`，接口存在性先真实 assertion RED：`assertIsNotNone(importlib.util.find_spec('icode.windows_startup_security_native'))`；随后 class/read callable 缺失断言，不以 ImportError 作产品失败。
- [ ] 真实 ctypes 测试自有合法 buffer构造 descriptor；fake DLL仅验证 ABI/生命周期，不授 Windows OS信用。按照以上 signatures 与 read合同实现新reader，不复制未知pointer，不改其它源。
- [ ] 原生调用参数精确、success有界ownedbytes及释放1次；缺API/加载异常/非Windows；handle bool/零/INVALID/超指针；错误状态/NULL输出；IsValid/control/revision/absolute/length所有门；parser拒绝；API输出后OSError/KI/SystemExit；复制后中断；LocalFree非NULL/普通异常/KI/释放后抛异常；主体+清理复合异常和hostile note；unknown后重调零API/零重free。故障 buffer必须测试实际自有内存，不给任意伪地址解引用。
- [ ] 运行 `.venv/bin/python -B -m unittest tests.test_windows_startup_security_native -v`，真实 RED→GREEN；自 SPEC/QUALITY 后冻结；主代理全文回读和实际验证，独立 SPEC→不同 QUALITY。

## Task 2：backend 接线及实际对象负控

**Dependencies:** Task 1
**Parallelizable:** No（接口依赖）

- [ ] 先在现 `tests/test_windows_startup_native.py` 补 RED：`self.assertTrue(access & 0x20000)`，新增 query_security callable 与 active/closed/unknown拒绝测试；实际命令 `.venv/bin/python -B -m unittest tests.test_windows_startup_native -v`。
- [ ] 最小实现 READ_CONTROL 与 query_security lazy接口，原metadata/读取/ownership路径不变；真实 backend open的相同数值HANDLE交给reader，禁止替换或按路径重开。
- [ ] 新 Windows-only class直接 backend开本次临时目录与文件，用 query_security拿bytes并parse，文件身份重核一致；返回后descriptor副本可用、fileHANDLE仍可读、close后query拒绝。测试重复查询及文件/目录；只处理自己创建对象，不修改宿主ACL/配置。非Windows明确平台skip，Windows夹具/API失败不得skip。
- [ ] 默认创建对象及不同继承状态的 native 描述符可解析性必须实际验证：官方 API 不承诺所有空闲/未引用字节为零，冻结 parser 的严格子集可能拒绝有效 OS 描述符。此时记录具体格式与兼容缺口，不以假 DLL零 padding通过冒充原生兼容，不自动放宽冻结 parser；128 KiB仅内部预算，不称 Windows所有描述符通用上限。
- [ ] 自审、主代理关联、独立双审；共享锁六项全部回归，本片实际原生新增门单独计数，不复用前SHA作通过。

## Task 3：必需 CI 与发布

**Dependencies:** Task 1, Task 2
**Parallelizable:** No（全部冻结后）

- [ ] 完整回读 `scripts/run_workspace_ci.py`、`tests/test_windows_startup_pin_ci.py` 与新 reader classes；给新安全parser/policy/reader便携类恰好一次选择、Windows native类仅nt，扩展 selected_pin_ids 前缀与对应 body/fixture/subTest拒绝门。旧可选skip语义保持；新选择器和必需skip测试必须实际 RED→GREEN。
- [ ] `.github/workflows/ci.yml` 的 workspace 可最小加入 Windows Python3.12 两格，先核实际matrix及关联workflow测试；不新增CI权限、特权或用签名安装job代native query信用。Windows10/普通host仍另记缺口，不能用hostedWindowsServer替代。
- [ ] 主代理运行 `.venv/bin/python -B -m unittest tests.test_windows_startup_security tests.test_windows_startup_security_native tests.test_windows_startup_pin tests.test_windows_startup_native tests.test_windows_startup_pin_ci tests.test_windows_provenance tests.test_run_workspace_ci`；方法数/skip取实际输出。新便携类20轮无skip/F/E，冻结摘要不变。
- [ ] compileall -q -j1 touched源/测试/selector、diff check、站点/文档两轮、全片独立SPEC→不同QUALITY、完整preflight三道均通过；据实七维报告，root精确暂存commit/push main及远端核SHA。
- [ ] 新SHA Windows x64/ARM64×3.11/3.12 对实际选中原生query/共享锁方法逐格核作业与日志；失败继续阻断不回退。本片通过仍不闭合 owner权限窗口、publisher/DLL/UAC、WP0b/WP1/2或R2/R3。

## 研究取舍

独立研究沿2026-10-11固定Codex/SRT版本及Apache2许可，见上片完整链接；主代理另核 [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo)、[IsValid](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-isvalidsecuritydescriptor)、[Control](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptorcontrol)、[Length](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getsecuritydescriptorlength)、[LocalFree](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-localfree)。采纳HANDLE查询/单owned副本/一次free；不适配unchecked free、长度当allocation证明或path重开；暂缓AccessCheck/RX和整窗授权。无代码复制、新依赖或特权，收益/信用仅针对本片实际测过的运输合同。

独立只读计划复核未发现必须重设计项；另指出单 actor须覆盖整个backend生命周期、OS padding不保证零两项边界，主代理已补入。此为设计研究，不是新原生通过证据，也未重新刷新上游HEAD。

**Execution Mode:** serial
