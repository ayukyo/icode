# Windows 启动权限合同实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development task-by-task；真实 RED→GREEN，单写者，主代理最终提交。用户明确要求 main 开发，不建立分支/worktree，不重复询问已批准路线。

**Goal:** 建立 held HANDLE 权限查询将消费的有界描述符 parser 与 source/protected 防篡改政策；再接入原生查询，不提前开放启动。

**Architecture:** 纯 owned bytes 解析和政策集中于 `windows_startup_security.py`，不接触路径、句柄或系统权限。原生运输另片实现 GetSecurityInfo/LocalFree，再由 pin owner 消费；当前旧 provenance、snapshot 与 launch flags 不变。

**Tech Stack:** Python 3.11/3.12 标准库、unittest；编译 -j1，无新依赖或 token 特权。

基线 main `90370b1`、vendor `21566a5`。总设计为 [可信启动](../specs/2026-10-11-windows-trusted-startup-design.md)，本片只落实其第 2 项中的 bytes 与政策，不声称已实现 DLL、UAC、晋升或完整窗口。

## 设计边界及接口

新 `src/icode/windows_startup_security.py` 与 `tests/test_windows_startup_security.py`。异常 `StartupSecurityError` 继承现有 `StartupPinError`。冻结 `StartupAccessEntry(allowed: bool, flags: int, mask: int, sid: str)`；冻结 `StartupSecurityDescriptor(raw: bytes, owner_sid: str, group_sid: str | None, control: int, entries: tuple[StartupAccessEntry, ...])`。仅两个内部函数：

```python
def parse_startup_security(data: bytes) -> StartupSecurityDescriptor: ...
def check_startup_security(data: bytes, *, role: str,
                           host_sid: str, directory: bool) -> StartupSecurityDescriptor: ...
```

`check` 必须自己 parse 原 bytes，不能信任可人为构造的 dataclass 作为授权。返回值只是防篡改政策检查通过的快照，不是 OS AccessCheck、读取/执行许可或 launch grant。host SID 参数将由后续固定内部消费者取实际 token，当前不注册模型入口。

Parser 仅 exact bytes，20 至 128 KiB；revision=1、Sbz1=0，control 仅 OWNER/GROUP_DEFAULTED、DACL_PRESENT/DEFAULTED/AUTO_INHERIT_REQ/AUTO_INHERITED/PROTECTED、SELF_RELATIVE（允许掩码 0x950f），必须 SELF_RELATIVE+DACL_PRESENT，SACL offset=0。owner 和 DACL 必须非零；group 可无，但存在须同样校验。offset DWORD 对齐且不进入 header。SID revision=1、subauthority 0–15，authority 6 字节大端、subauthority DWORD 小端，先检查完整范围再解码为规范十进制 `S-1-A-N...`。owner/group 可复用完全相同 SID 范围，其余组件不允许重叠。

ACL revision 2 或 4、保留字段为 0、AclSize>=8 且 DWORD 对齐、完整范围有界；AceCount 对应逐条走完。只接受 basic allowed=0/denied=1、flags 0x1f 以内、AceSize>=16 且 DWORD 对齐、mask 仅文件 specific 0x1ff、标准 0x1f0000、generic 0xf0000000（合为 0xf01f01ff）。ACE SID 必须恰好占满 ACE，未知对象/callback/audit 类型或 bit 拒绝。ACL 可有合法未使用空间，只接受零 padding；不把 padding 当 ACE。descriptor 未引用空间也须为零，避免漏读组件或隐藏数据。空 DACL 可 parse，但不据此授执行信用。

政策仅 source/protected，directory exact bool，host SID 必须规范且有界，不接受环境或模型派生信任。固定可信集合为 Admin `S-1-5-32-544`、SYSTEM `S-1-5-18`；source 另含 host，protected 不含 host。owner 必须在对应集合，不能用 OWNER RIGHTS ACE 把不可信 owner 变可信。空 entries 拒绝作为可用启动对象政策。禁止非可信 allowed ACE 的 WRITE_DATA/APPEND_DATA/WRITE_EA/WRITE_ATTRIBUTES、DELETE/WRITE_DAC/WRITE_OWNER、GENERIC_WRITE/ALL；目录额外 DELETE_CHILD。GENERIC_READ/EXECUTE 和普通 RX 可接受，未知掩码已由 parser 拒绝。deny ACE 不抵消危险 allow，不模拟用户组或 ACE 排序；OWNER RIGHTS `S-1-3-4` 仅在可信 owner 后对应 owner。inherit-only 的危险非可信 allow 亦保守拒绝（含未来子项风险）；CREATOR OWNER 不自动被列可信。此保守政策的真实系统目录兼容性另验，失败不能放宽成已安全。

## Task 1：有界纯 parser

状态：parser 已实现；独立 SPEC C0/I0/M0，随后不同 QUALITY C0/I0/M1（非阻断测试分支精度，Task2 一并补齐）。两者实跑23 PASS/0 skip；主代理完整回读121行源/203行测试，关联99项=93 PASS/6 Windows平台 skip，0 F/E；固定种子两万畸形输入未泄漏非 StartupSecurityError，不将变异接受数当政策安全证明。冻结源摘要 `f50684cda9d92ea3fdecaf1f2e5ef34e854671f38faf5b3befe680f7654a397d`、测试 `a6f13fd0b3de8cf6fef998ebb752d17b7bc6904181e3a4fb75b1ceb726a94fee`。阶段尚未完成 preflight/提交。

**Dependencies:** None
**Parallelizable:** No（单一实现写者）

- [x] 先写接口存在性 assertion RED，不以 ImportError 代替缺实现：

```python
def test_parser_interface_exists(self):
    self.assertIsNotNone(importlib.util.find_spec('icode.windows_startup_security'))
```

- [x] 运行 `.venv/bin/python -B -m unittest tests.test_windows_startup_security -v`，实际接口1断言RED、扩展23断言RED；随后实现 GREEN。
- [x] 按上述精确数据结构和 parser 合同实现；fixture 使用 `struct.pack('<BBHIIII', 1, 0, 0x8004, owner_offset, 0, 0, dacl_offset)` 加 binary SID 和 ACL，不依赖 Windows 或 mock native 调用。
- [x] 实测 owner/group 共享或非共享、合法不同组件顺序、空 DACL、ACL padding、零/15 subauthority 和完整 descriptor 冻结；畸形长度/offset/重叠、截断 SID/ACL/ACE、unknown 类型/flag/mask、保留/control/SACL、未引用非零字节、bytearray/memoryview 等全部拒绝。输入不得修改。
- [x] 自 SPEC→QUALITY 后停止写者，主代理完整回读、运行同命令；独立 SPEC 后不同 QUALITY。测试精度 Minor 将另补两项原本已正确拒绝的对齐 fixture，不伪装产品 Bug RED；任何产品修复仍须真实 RED。

## Task 2：source/protected 政策

**Dependencies:** Task 1
**Parallelizable:** No（同文件接口依赖已冻结 parser）

- [x] 先写实际缺政策 assertion RED：

```python
def test_policy_interface_exists(self):
    self.assertTrue(callable(getattr(security, 'check_startup_security', None)))
```

- [x] 补 actual bytes fixture：host-owned + host modify 在 source 可通过、protected 拒绝；Admin/SYSTEM owner 与 RX 可通过；不可信 owner 即使空/deny/OWNER RIGHTS 均拒绝；无 ACE 拒绝。
- [x] 逐一测试 write/append/EA/attributes/delete/DAC/owner/generic write/all、目录 delete-child、普通 file delete-child非修改语义、deny 后 allow、继承/IO dangerous allow、OWNER RIGHTS可信/不可信、角色/host_sid/bool 类型及规范格式负控。
- [x] 实现 `check_startup_security` 自 parse 返回 immutable 快照；其余调用者、权限、native backend、flags 一律不改。GREEN→自双审→主代理关联→独立双审。

Task2 实际接口 RED：26 tests/1 assertion FAIL，随后全政策 RED：43 tests/18 assertion FAIL，均因缺接口而非 ImportError；最终43 PASS/0 skip。Task1 两个测试分支精度补强先单跑25 PASS，未假造产品 Bug RED。实现自 SPEC/QUALITY 后停止；独立全片 SPEC 和随后不同 QUALITY 均 C0/I0/M0，二者各实际43 PASS/0 skip，上轮 Minor 已关闭。

主代理完整回读最终源码180行、测试371行（任务传递中误写188行已纠正，不是内容漂移）；源 `c22fd35bb679a025ceff038f015b2ec83ad94c242bf2a5ddba5e08fe12680931`、测试 `5ee90d6466af316188753aa6a4c59cc4f805f6e940df88a0f5504d2e40892ede`，原前121行 parser 摘要仍冻结。独立审查仅授本片纯格式/防篡改政策，不授 native/DLL/UAC/RX/完整 WP0b。

## Task 3：关联、持续研究、发布

**Dependencies:** Task 1, Task 2
**Parallelizable:** No（冻结后验证）

- [x] `.venv/bin/python -B -m unittest tests.test_windows_startup_security tests.test_windows_startup_pin tests.test_windows_startup_native tests.test_windows_startup_pin_ci tests.test_windows_provenance`，实际124项=118 PASS/6 Windows skip/0 F/E；新纯 parser/policy 43项无 skip。
- [x] 新 suite 串行 20 轮，每轮43 run/0 skip/0 F/E，前后两文件摘要不变；compileall -q -j1 新源/测试通过，tracked及两新文件 no-index diff check 无格式诊断（后者exit1是新增差异本身，不是错误）。
- [x] `CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 .venv/bin/python -u scripts/preflight.py` 新完整三守卫全部通过、exit0；站点2HTML/6MD/3品牌资产/2预览/9未抓取外链检查通过，四文档契约连续两轮0疑似项，独立全片双审C0/I0/M0，七维报告见下。
- [x] 研究结论同步 `docs/agent-landscape-live.md`，保留具体版本/日期与阶段边界；精确暂存六文件，主代理提交推送main `6216c420104097a03073ebdfecd5f30f5062c882`，再次核远端同SHA及提交后工作树clean。

## 原生运输下一片接口（本计划不提前报实现）

同一 held HANDLE GetSecurityInfo，open 明确 READ_CONTROL；不重开路径，不查 SACL。输出 descriptor 单 ownership；原调用覆盖 BaseException；IsValidSecurityDescriptor、control/revision/self-relative、长度预算后复制 owned bytes，再由上述 parser消费。原生有效 allocation 属于 Windows API TCB，不能声称任意坏 pointer可恢复。LocalFree 一次，NULL才确认；未知释放不重试，保原 KI/SystemExit，附固定无地址 note。之后 pin owner 查询整链并检查角色/原 bytes，同时仍不承诺 sharing 锁住全部 ACL。

## 独立研究：2026-10-11

复用 Codex `8c0f7011674145da7e10627769fb221c74fbf7a0` 与 SRT `5507fb0e639c00f845554336ece62e27af5b1bb7`（Apache-2.0），未新刷新 HEAD。采纳 [Codex ACL 检查机制](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/acl.rs) 的保守修改 mask，区别 source/protected；不适配其未知 ACE 忽略或按路径重开。暂缓自动信任 TrustedInstaller、系统目录 profile 放宽，待原生证据。研究及 parser 不能替代 native 运输、预入口加载和 UAC。

主代理定点核 [self-relative 描述符](https://learn.microsoft.com/en-us/windows/win32/secauthz/absolute-and-self-relative-security-descriptors)、[ACL](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-acl)、[ACE header](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-ace_header)、[SID](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-sid)、[文件权利](https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants)。这里消费不可变序列，不创建/修改 OS ACL；真实 OS 格式有效性仍单独在 native 层验证。成本为严格格式及兼容负控，收益限于消除未知格式默认允许；未复制上游源码、新增依赖或权限。

## 前片原生状态刷新

main `90370b1` 的 CI run `38132136078` 已终止为 failure：39 success/2 failure/3 skipped；Windows x64 job `114448479543` 与 ARM64 job `114448479619` workspace 均 success，实际各 704 tests / 20 skip；pin 类及 fixture/subTest skip 已是失败门，六个原生 pin 方法因此有这两台 Python3.11主机证据。不替代 Win10 或 Python3.12。Reviewer jobs `114448479661`/`114448479597` 均 failure，实际 ipv4/ipv6 error10035、wait_expired=true、connect_denied=false，仍未隔离通过。Python3.11/3.12 jobs `114448479608`/`114448479639` 均 success，各实际2656 tests /77 skip。官网独立 run `38132136023` 两 job success。来源run38132136038的validate及四签名安装格共5/5 success（x64/ARM64×3.11/3.12），job114450959534/584/595/603；其旧成品检查不是新权限片/native pin3.12或完整可信启动证据，不以此片掩盖 CI 整体失败。

## 当前软件发布窗口

全片独立双审、定点关联、20轮、语法/格式及站点检查已通过。新完整 preflight 于2026-10-11 11:03 UTC确认全部三道通过、exit0，源码/测试摘要仍一致；不是复用先前90370b1结果。密钥文件摘要与前窗口一致，仅查摘要不输出内容；固定vendor21566a5无改动。此观察窗口发布门已通过，root接续精确提交推送；最终SHA在实际发布后核验，不提前猜测。下一片 [原生运输计划](./2026-10-11-windows-startup-security-native.md) 已完成独立只读研究复核，尚无实现信用。

【架构级自检报告】（本片纯 parser/policy）

- ✅ 语法/编译：导入、compileall -j1、tracked及新文件格式检查通过。
- ✅ 依赖/调用链：复用StartupPinError，纯parser→policy自解析完整；旧consumer/native/launch flags未改。
- ✅ 逻辑/边界：43项角色、范围、未知格式、伪快照、继承/OWNER RIGHTS和修改权限合同通过，20轮冻结候选稳定。
- ✅ 异常处理：所测畸形输入统一拒绝；不把便携输入检查当任意资源耗尽或native异常保证。
- ✅ 关联模块：124项关联=118 PASS/6 Windows平台skip/0 F/E；新完整preflight三道通过，skip不授信用。
- ✅ 兼容安全：parser原121行不变，source/protected独立，无新依赖、权限、工具入口或执行授权。
- ✅ 可运行性：本片43 PASS/0 skip；未接实际token/HANDLE查询、DLL/UAC，不报告完整WP0b或R2/R3/100%总验收。

**Execution Mode:** serial

发布后刷新：软件片已发布6216c42；上述“发布动作待”是11:03UTC提交前观察窗口。root立即开始下一片原生reader，独立单写者负责新运输源/测试；旧纯parser/policy继续冻结，R2/R3整体验收未通过。

6216c42后续CI实证（11:19 UTC观察）：run38134223455已completed/failure，39 success/2 failure/3 skipped；Windows workspace x64 job114454674725、ARM64 job114454674761均success，各704 tests/20 skip（Python3.11），保持旧六项必需pin方法的这两台主机证据。新权限parser/policy尚未进入workspace选择器，不冒充其Windows原生查询已验；后片会补选。完整Python3.11/3.12 jobs114454674445/565均success，各2699 tests/77 skip。Reviewer job114454674700/600仍实际v4/v6 error10035、wait_expired=true、connect_denied=false且failure，整体仍阻断。来源run38134223407此时还在进行，不提前记为安装成功。

随后来源作业刷新：run38134223407的validate及Windows x64/ARM64×3.11/3.12安装五个jobs全部success（114454674308、114456951077/126/149/169）。只有旧成品来源/安装检查信用，不代尚未发布的新reader、原生query或完整可信启动；原11:19“进行中”保留其历史窗口。
