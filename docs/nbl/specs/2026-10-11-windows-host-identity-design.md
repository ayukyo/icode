# Windows startup：原宿主身份的只读捕获

日期：2026-10-11。基线 main `0d40c2577316bfa52e9c595dfcd4e388ecd8c28c`，vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。这是已批准 [WP0b 可信启动路线](./2026-10-11-windows-trusted-startup-design.md) 的内部身份子片，不新增服务、安装步骤或提权；普通技术取舍沿用户授权自主执行。本文件尚不是实现、原生通过或启动许可。

## 三问与范围

真实问题：纯权限政策接收 canonical `host_sid`，字符串校验不能证明它来自原宿主 token。来源对象允许 host 修改，protected 对象不允许把 host 加入可信主体；身份必须在首次 UAC 前取得，不能在另一管理员接受 UAC 后换绑。

现有实现：复用 `windows_startup_security._sid` 的 owned bytes 有界解析与固定安全错误。`windows_runner_pipe` 的 SID 查询是认证管道实现，未验证成功 returned window；`windows_job` 的回执针对挂起子进程 AppContainer，不是原宿主。两者保持不变，不顺带重构。

调用链：新内部 `WindowsStartupHostIdentity.capture() -> str` 固定读取 `GetCurrentProcess()` 的 primary token；取得 owned `TOKEN_USER` bytes、先检查 pointer 对应范围、用 `_sid` 解码、确认一次关闭后才返回 canonical SID。没有 PID/HANDLE/SID 参数，没有模型、环境、用户名、thread token、linked token 或 elevated token 输入。后续整链消费者使用该捕获结果，但本片不接入 launch/provenance，不把返回字符串直接升级为来源认证或授权对象。

## API 与生命周期

新模块 `src/icode/windows_startup_host_identity.py`；仅 Windows 构造可用，单 actor，不承诺并发 capture/close。只加载固定 kernel32/advapi32，标准库 ctypes，不新增依赖。固定宽度 U32=c_uint32、I32=c_int32、VOID=c_void_p。

```python
signatures = {
    'GetCurrentProcess': ([], VOID),
    'OpenProcessToken': ([VOID, U32, POINTER(VOID)], I32),
    'GetTokenInformation': ([VOID, I32, VOID, U32, POINTER(U32)], I32),
    'CloseHandle': ([VOID], I32),
}
```

`GetCurrentProcess()` 返回借用 pseudo HANDLE，不 CloseHandle、不以硬编码 -1 替代 API。`OpenProcessToken` 只申请 `TOKEN_QUERY=0x8`，信息类仅 `TokenUser=1`。无 duplicate/assign/adjust/all-access、权限启用或 token 修改。其输出为本次唯一 owned token HANDLE；acquisition 本身必须在 BaseException 清理边界内，以覆盖写 output 后失败/中断。NULL 与 INVALID_HANDLE_VALUE 不作为可关闭 owned 输出；成功必须有合法输出，否则拒绝。Windows API 的合法对象语义是 TCB，故障测试只使用测试自有 buffer 与合法形状输出，不解引用任意伪地址。

第一次 GetTokenInformation 传 NULL/0，要求失败回执、立即取得 ERROR_INSUFFICIENT_BUFFER=122，以及 required 至少 `sizeof(TOKEN_USER)+8` 且最多 4096。预算是 ICODE 内部限制，不称 Windows 通用最大值。分配一次 buffer，第二次必须成功且 `sizeof(TOKEN_USER)+8 <= returned <= capacity`；信息增长、零长度、超预算或错误一律拒绝，不重试、不使用首次 capacity 冒充成功 returned window。

TOKEN_USER 按 native ABI 的 SID_AND_ATTRIBUTES 定义：VOID Sid、U32 Attributes，并保留 native alignment。只从 owned raw header 用 `from_buffer_copy` 取 pointer 数值；SID pointer 不直接 dereference。将数值减去本次 allocation base，要求 SID offset 不落入 TOKEN_USER header，完整 SID 八字节头及 `8+4*count` 都位于成功 returned window 内；拒绝 NULL、低地址、头内、尾端、超窗和截断。通过已有 `_sid(raw, offset, returned)` 检查 revision1、最多15个 subauthority，并得到 canonical 字符串。Attributes 不授任何组/权限信用；Microsoft 未为 user SID 定义 attributes，本片不增加 attributes==0 的兼容限制。未引用 padding 不要求零，不借用 SD parser 的独立严格 padding 政策。

CloseHandle 对每个合法 acquired HANDLE 恰好尝试一次；调用前标记 `cleanup_unconfirmed=True`，只有非零 BOOL 回执确认后清除。零、普通异常或中断保持 unknown，实例拒绝后续 capture，绝不重试旧数值或调用新 acquisition。没有 HANDLE 不关闭；不关闭 process pseudo HANDLE。成功清理置于主体异常 handler 外，避免返回侧中断回到再次关闭路径。主体异常与清理失败同时存在时保原异常，只添加固定无 SID/地址/路径 note，note 本身失败也不得覆盖原异常。

普通加载/API/结构错误使用固定 StartupSecurityError 文案且 `from None`；KeyboardInterrupt/SystemExit 保留原实例。不能打印 SID、HANDLE、私有路径、原始异常或 token bytes。只在清理确认后返回 immutable canonical str。承诺限定到明确测试的 Python 行事件和 API 输出窗口，不声称任意异步字节码原子性。

## 验收和依赖

本片实现前必须完成 `0d40c25` 的 held-HANDLE 运输原生门：新 SHA Windows x64/ARM64 × Python3.11/3.12 必需共享锁6+query2实际运行；工作区 job success 仍须核选中项及日志，不复用前 SHA。其余设计/只读研究可并行，运输兼容失败时先修根因，不开始消费不合格运输。

便携测试文件 `tests/test_windows_startup_host_identity.py`：接口存在性 assertion RED（不以 ImportError 充当产品失败）；显式 DLL signatures、固定当前进程/TOKEN_QUERY/TokenUser、两次 query receipt、4096预算、header/body所有边界、owned copy 后原 buffer 修改不改 SID、无 path/env/account/SID API。测试真实自有 ctypes buffer，不直接构造危险 pointer 供解引用。

清理故障覆盖 output 后 OSError/KeyboardInterrupt/SystemExit、open false/缺输出、sizing失败与 last-error错误、第二次失败/returned增长、parser拒绝、正常关闭/零/异常/关闭后中断、主体与清理复合错误和 hostile note；unknown 后重调必须零 acquisition/零 close，正常成功可再次独立捕获。pseudo HANDLE 零 close，owned HANDLE 一次 close；原 KI/SystemExit 身份保持，普通错误无测试私有字符串。构造不可用/缺 API 保持拒绝。成功样例明确包含非零 Attributes、非零未引用 padding、SID 不紧邻 header 和 SID body 恰好填满 returned；ABI 无 `_pack_`，x64/ARM64 原生核 Sid.offset=0、Attributes.offset=8、sizeof(TOKEN_USER)=16，便携测试按本机 native pointer 宽度核布局。

新增 Windows-only actual capture positive：固定当前进程，通过独立 Windows SID API 交叉比较 canonical SID，不依赖环境用户名；重复捕获与返回类型/清理状态实际核。负控仍以便携自有 buffer 故障注入表达，不修改宿主 token/ACL。CI 在同四格实际选择该原生类并拒绝 method、fixture、subTest skip；只授实际 runner 系统，Win10/普通 host 继续另列缺口。原有运输/共享锁必需门保持，CI 权限不变。

真实 TDD → 单写者实现自审 → root 全文回读与关联验证 → 独立 SPEC → 不同 QUALITY → 新完整 preflight → 七维报告 → 按授权 main 提交推送。新增原生 CI 再逐格追踪；仅身份片通过不代表整链角色 consumer、ACL 防变更、AccessCheck/RX、publisher/DLL/UAC、DPAPI、WP0b 或 R2/R3 已通过。

后续整链消费者另成片：从原 owner 保存的同一 HANDLE 逐个 query_security，核实际目录类型与 source/protected role，前后重核 metadata，任何失败关闭全链；不能接受外部提供 SID/snapshot 作为权限来源。本片不提前实现此依赖，更不新增 readiness/launch flag。

## 研究取舍和自审

独立只读观察 2026-10-11 11:38 UTC；沿 Codex `8c0f7011674145da7e10627769fb221c74fbf7a0` 与 SRT `5507fb0e639c00f845554336ece62e27af5b1bb7`，均 Apache-2.0，未刷新 HEAD/完整二十名单。主代理另取固定 raw 源全文或相关完整函数并核 Microsoft 原文，校准 SRT 行号，不声称上游版本变化。

采纳 Codex [`token_user.rs:18–69`](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/token_user.rs#L18-L69) 的预算、returned window、buffer 内 SID offset 与 owned copy机制；ICODE 复用已有 bytes SID parser，不复制 Rust 源或新增 SID allocation。Codex 的 sizing 返回值不是本片严格 sizing 错误合同，借用 token HANDLE 也不等于本片 token ownership。

不适配 SRT [`token.rs:79–86`](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/token.rs#L79-L86) 的 TOKEN_ALL_ACCESS、[`200–211`](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/token.rs#L200-L211) 的借用 pointer/GetLengthSid 路径及 [`236–253`](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/token.rs#L236-L253) 未显式消费成功 returned window；这不是上游实际漏洞结论。ICODE 的 unknown quarantine 是保守 ownership 政策，不是官方声称失败一定已关闭。

主证据：[GetCurrentProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getcurrentprocess)、[OpenProcessToken](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocesstoken)、[GetTokenInformation](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation)、[TOKEN_USER](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-token_user)、[CloseHandle](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle)。收益是补 host SID 的实际读取来源，成本是内部 owner/有界解析与保守拒绝；无新依赖、权限或许可交付变化。暂缓组 membership、AccessCheck、TrustedInstaller自动信任、系统祖先放宽与跨管理员身份交接。

自审：三问均有当前源码依据；接口零外部身份参数，清理与返回边界明确；不改管道/Job/运输/parser；原生证据门、整链和启动门分开。设计采用已批准路线，无新需用户决定的权限/安装扩展；下一实施计划仍须完整任务分解与独立审查。

独立只读设计审查 C0/I0/M2：两项均为成功样例/ABI验收细化，已补入，不新增产品限制。2026-10-11 11:45 UTC 后主代理核 `0d40c25` 新CI四Windows workspace 均 success，逐格日志实际775 tests/20 optional skips；当前 selector 将全部新纯/运输类及6+2原生方法选中并将其 method/fixture/subTest skip升为失败，因此关闭本片运输前置门。此证据仅适用于实际hosted runner，不替代Win10/普通host或新身份模块原生门。
