# Windows 启动对象 pin 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking. 用户明确要求 main 开发、非必要不重复询问；不创建 worktree/分支。主代理控制提交，子代理不自行 commit/push。

**Goal:** 实现 WP0b 第一依赖：从直接卷逐段持有启动文件及祖先 HANDLE，读取该文件原字节并完整管理生命周期；随后连续进入权限、加载、晋升及首次 UAC 门，不把 pin 视为 WP0b 完成。

**Architecture:** 纯生命周期层与 Windows 原生适配器分开，后者只打开/查询/读取/关闭对象，不启动进程。现有 snapshot 和 provenance 消费者不改，本片完成后在后续接线片将固定包内资源绑定到该 owner。

**Tech Stack:** Python 3.11/3.12、标准库 ctypes/unittest、Windows NtCreateFile/QueryDosDeviceW/ReadFile；无新增依赖，编译 -j1。

设计：[可信启动与受保护晋升](../specs/2026-10-11-windows-trusted-startup-design.md)。基线 fb35f55/vendor21566a5。全部完成状态均以实际命令/审查为准。

## 当前状态刷新（提交 90370b1 后）

本片软件已提交并推送 main `90370b1dfc0b21df3b8e0e9970bd9ccedcfc391f`，主代理再次核远端同 SHA。下方早期“尚未提交/仍在运行”只描述各自历史窗口，不是当前状态。新 [权限合同计划](./2026-10-11-windows-startup-security.md)继续下一依赖，不等待重复批准。

精确 SHA 的 [CI run38132136078](https://github.com/ayukyo/icode/actions/runs/38132136078)：Windows x64 job114448479543 与 ARM64 job114448479619 workspace success，各实际 704 tests / 20 skip。该 SHA 的 DEFAULT 在 nt 显式选择六个 WindowsEnforcementTests，selected_pin_ids 将 body、fixture、subTest skip 提升为 exit1，因此这六项已获两台实际 Python3.11主机证据；不以整体 success 掩盖其余20个历史可选 skip。Win10、Python3.12及普通宿主矩阵未补齐。

同 run Reviewer x64/ARM64 两作业仍 failure，日志 ipv4/ipv6 error10035、wait_expired=true、connect_denied=false，不能算网络 DENY 或 R2/R3 通过。权限/DLL/UAC/晋升及完整 WP0b 尚未完成。官网 run38132136023 validate/deploy 两作业 success。

## 文件职责

- 新 `src/icode/windows_startup_pin.py`：内部 pin owner、严格路径/metadata 及有界 bytes 合同。
- 新 `src/icode/windows_startup_native.py`：直接卷、no-reparse/relative open、真实 HANDLE metadata 与读/关的 ctypes 后端。
- 新 `tests/test_windows_startup_pin.py`：portable owner 生命周期；新 `tests/test_windows_startup_native.py`：原生边界传输测试及 Windows-only 真正共享锁负控，分别计数，不将模拟接口当原生。
- 新 `tests/test_windows_startup_pin_ci.py`：如加入 CI 选择，验证 portable 与原生方法恰好出现且不退化为全 skip；只在实际选择器完整回读后最小接入。
- `scripts/run_workspace_ci.py`：实际 workspace workflow 的选择器，本片最小注册 pin 必需合同并拒绝 body/fixture/subTest skip。`scripts/run_windows_wheel_ci.py` 本片未修改；包内资源接线在后片进行，不提前更改初始化、签名或安装权限。

### Task 1：内部 owner 与原文件 bytes

**Dependencies:** None

**Parallelizable:** No（单一实现写者；研究可只读并行）

- [x] 写真实 RED：通过 importlib 查模块存在性，以 assertIsNotNone 失败而非 ImportError 作为缺实现证据。

```python
def test_startup_pin_interface_exists(self):
    spec = importlib.util.find_spec('icode.windows_startup_pin')
    self.assertIsNotNone(spec, 'missing Windows startup pin owner')
```

- [x] 执行 `./.venv/bin/python -B -m unittest tests.test_windows_startup_pin`，记录失败方法与原因；未出现预期失败不得写生产实现。
- [x] 实现内部 `PinnedStartupFile` owner：明确 immutable identity/content/digest、live/closed 状态；同一 native handle 有界读取，所有句柄立即登记 ownership。
- [x] 公共测试合同示意（具体私有构造参数随后端保持一致，不注册模型工具）：

```python
with pin_startup_file(absolute_local_path, max_bytes=64 * 1024 * 1024) as pinned:
    assert hashlib.sha256(pinned.content).hexdigest() == pinned.sha256
    pinned.revalidate()
# Close 后读取和 revalidate 必须拒绝，不能返回旧 snapshot 当 live。
```

- [x] 用精确 fake backend 测所有构造阶段故障、short/overflow/metadata 漂移、reparse/跨卷/多链接/非法类型、读取中断、close 失败与异常优先级；fake 仅验证生命周期，清楚标记不授 OS 信用。
- [x] 按相同命令跑 GREEN，完整 self SPEC→QUALITY；尚无 native backend 时本任务不标 native 实现完成。

Task1 实施者已停止写文件。首次 1 方法及扩展 14 方法均预期 assertion RED 后实现；自审新增未初始化 owner、中断、import 名称及安全清理 note 负控后最终 31 方法 GREEN、0 skip。主代理完整回读源码 257 行和测试 443 行，确认停止后的两文件摘要一致；当前关联实跑 118 tests / 12 Windows skip / 0 failure/error，即实际 106 PASS。该结果只关闭便携 owner 逻辑，不授 native 后端、完整 WP0b 或原生启动信用。

### Task 2：真实 Windows 后端

**Dependencies:** Task 1

**Parallelizable:** No（需要同一 owner 接口，单写者避免接口竞争）

- [x] 先补 RED：路径解析拒绝相对/UNC/ADS/dot/空组件、多跳盘符映射，原生调用参数必须是直接卷/RootDirectory/OBJ_DONT_REPARSE/share-read/non-inheritable；原生函数不可用时拒绝，不返回模拟成功。
- [x] 实现 `windows_startup_native.py`：QueryDosDeviceW 有界结果严格接收直接 HarddiskVolume；卷根与祖先持有，NtCreateFile 相对打开；通过 FILE_ID_INFO、FILE_STANDARD_INFO、FILE_BASIC_INFO、FILE_ATTRIBUTE_TAG_INFO 查询完整身份和链接数；ReadFile 有界，CloseHandle 状态如实返回。
- [x] 可复用 windows_worktree ctypes 布局，但不得复用 share7/open-root 路径，也不得修改该 snapshot 后端。复用私有布局时显式记录依赖并关联回归；不把仅 READ_ATTRIBUTES 的 open 误当能参与全部数据分享检查。
- [x] 每取得句柄即登记，API 查询异常也必须进入 cleanup；尚 live 的 handle 数字不能绕 owner 直接暴露给模型。目录保持非继承，文件身份再核验与原字节绑定。
- [x] 真 Windows 临时目录测试：正常读、held image 写/删除/rename 拒绝、原先 WRITE/DELETE opener 导致 pin 拒绝、祖先 rename/junction/多链接拒绝；关闭后合法写入恢复。已在上列 x64/ARM64 Python3.11 CI 两主机通过，未授其余平台格；只处理测试本次创建的对象，不改宿主 ACL/全局设置。
- [x] Linux 上跑 portable suite，Windows 测试按平台单列 skip；原生四格随后按精确提交实际执行，不能以 Linux 无失败授它们通过。

### Task 3：选择器、双独立审查与阶段发布

**Dependencies:** Task 1, Task 2

**Parallelizable:** No（冻结实现后审查，避免消费者随写者变化）

- [x] 完整回读实际 DEFAULT/Windows 安装选择器及配对测试，最小注册必要 suite；不复制不存在的 workflow 命令。
- [x] 执行 `./.venv/bin/python -B -m unittest tests.test_windows_startup_pin tests.test_windows_provenance tests.test_windows_worktree_tree_oid tests.test_windows_tree_snapshot_probe`；实际模块名已用 rg 定位，不以错误导入当产品 RED。
- [x] 独立 SPEC：按本设计逐项核实现/测试，修完再进行不同 QUALITY；两者只读、主代理完整回读所有实现后执行关联回归。
- [x] 冻结后定点 portable 方法连续串行 20 轮，逐轮记录实际通过数、skip 和失败；原生方法在 Linux 的 skip 不计入 portable 通过数量，不用单次测试重复报作新原生证据。
- [x] 新完整 `./.venv/bin/python scripts/preflight.py` 三道通过；`./.venv/bin/python -m compileall -q -j1 src/icode/windows_startup_pin.py src/icode/windows_startup_native.py`、diff、治理及密钥/子模块检查通过。测试数量与 skip 取实际输出，不能猜。
- [x] 执行 `./.venv/bin/python scripts/check_site.py`，确认本片不新增提前宣称启动或隔离已就绪的文案，不绕过站点守卫。
- [x] 七维自检据实记录；精确暂存路径（新 docs 需 `git add -f`）、cached diff check 后主代理提交推送 main 并核远端 SHA90370b1。精确 SHA 的完整 Windows 支持矩阵缺口单列。
- [x] 阶段结束更新持续竞品对照：采纳对象 pin、暂缓首 UAC 证明、不适配锁失败继续；记录当前源码/许可/观察日期，未伪装全二十项目刷新。新原生窗口见顶部刷新。

## WP0b 后续连续任务（不因第一片通过而关闭）

第一片审查完成后，按总设计进入 held-HANDLE owner/DACL 和原始 PE/来源接线，再实现 KnownFolder private stage/owned journal/marker；最后完成首次 UAC、跨管理员和 host-death 锁窗口的真实负控。这些具体实现计划根据第一片冻结接口展开，无需再询问已批准的推荐路线；新增权限或已批准路线实际不满足硬指标时才报告必要取舍。

总退出门仍含 Windows10/11 x64/ARM64 实测、首次与晋升后同对象启动、pre-main 加载边界；WP1/WP2、R3真实模型1→6/90%能力一致性独立保持未完成。当前凭据 401 只阻塞真实模型，不阻塞本片开发。

## 后续审查窗口：owner 复制与原生中断

首次 owner QUALITY 独立复现浅复制共享 HANDLE 而关闭状态独立，可重复关闭回收后重新分配的数字。新增两个方法、六个状态/复制子场景先出现 6 assertion FAIL / 0 ERROR，再以固定 `StartupPinError` 明确拒绝 `copy.copy` 与 `copy.deepcopy`。修复后独立 SPEC 和另一位原 QUALITY 均 C0/I0/M0；主代理实跑 33 PASS / 0 skip，并串行 20 轮，每轮 33 PASS / 0 skip / 0 failure/error，前后两文件摘要一致。此前 31 项和 118 项关联结果保留为历史窗口，不充当修复后关联验证。

Task2 实施者交付后停止写入，独立 SPEC 实跑 29 项：23 PASS / 6 Windows 平台 skip。审查仍有两个 Important：清理失败时添加 note 可覆盖原中断，以及原生成功打开后的提取/登记尚未处于异常保护范围。修复另以单一写者进行，必须先补真实 assertion RED；本窗口不标 Task2 合同通过，不把六项平台 skip 当原生信用，也不提前运行或宣称全阶段 preflight 完成。

上述两项修复随后完成并冻结：三个新增方法先实际 15 assertion FAIL / 0 ERROR，另增 API 中断与旧 ownership 碰撞负控。主代理修复后关联实跑 153 项，135 PASS / 18 Windows 平台 skip / 0 failure/error；四个新文件冻结摘要前后不变，portable owner 与后端传输共 60 方法串行 20 轮，每轮 60 PASS / 0 skip / 0 failure/error。仅有界验证成功输出提取、登记和 return 的 Python 行事件中断，不宣称任意异步字节码或跨函数返回原子性。原生独立复审和 CI 选择器接线仍在进行，完整 preflight 尚未执行。

随后原 SPEC 复审关闭两个 Important，另一位独立 QUALITY 核接口/ABI/ownership/原生夹具后亦 C0/I0/M0，两者冻结摘要一致。两位独立 native 实跑各 33 项：27 PASS / 6 Windows 平台 skip；QUALITY 另跑 owner 33 PASS，组合 66 项：60 PASS / 6 skip。Task2 软件合同通过，Windows 实际强制执行仍待；Task3 已开始，复用既有 `workspace-platforms` 调用的 `scripts/run_workspace_ci.py`，不新增 workflow/权限。包内 provenance 固定资源接线仍属第二片，未改变当前消费者。

Task3 首轮接线后，新旧选择器主代理实跑 35 PASS / 0 skip；portable 与 CI 共 68 方法串行 20 轮均 PASS / 0 skip，六个源/测试文件摘要不变。独立 SPEC C0/I0/M0，但不同 QUALITY 复现一个 Important：必需方法内部 `subTest` skip 的 ID 带子场景参数，runner 只匹配冻结父 leaf ID，因此错误返回 0。该问题修复前不能交付。主代理已对本次完整 preflight 的确切测试子进程发送 SIGINT 并确认该运行 exit1；其密钥/子模块两道通过不代表全三道通过，首次全仓运行不授信用，修复后须重新开始完整守护。

subTest 修复随后冻结：六类普通/嵌套子场景先实际 12 assertion FAIL / 0 ERROR，生产仅补真实 `_SubTest.test_case` 父对象归属，不解析带参数显示字符串，不改旧 OP/EXEC 或 optional 语义。主代理实跑新合同 10＋旧配对 27＝37 PASS / 0 skip，并把冻结的 70 个 portable/CI 方法串行 20 轮，每轮 70 PASS / 0 skip / 0 failure/error，六文件摘要不变。独立 SPEC 复审与原不同 QUALITY 均 C0/I0/M0；QUALITY 原复现实际返回 1，旧 optional 嵌套 skip 仍 0。新完整 preflight 和 DEFAULT CI 回归已启动，尚未取得终态；这两项通过前禁止提交。

最终本机窗口：新完整 `scripts/preflight.py` 实际 exit0，密钥、固定子模块及全仓测试三道全部通过；它不打印成功测试的详细计数，本记录不推算该总数。实际 DEFAULT runner 718 PASS / 0 skip / 0 failure/error，耗时 179.616 秒。编译并发通过环境及 compileall 限为 1；站点守卫通过，三份文档契约检查连续两轮 0 疑似项。上述旧“仍运行”是各自观察时刻，当前软件发布门已通过，提交/远端与真实 Windows 仍单独记录。

【架构级自检报告】（第一片软件阶段）

- ✅ 语法/编译：六个 Python 源/测试文件导入与 compileall -j1、格式检查通过。
- ✅ 依赖/调用链：内部 owner→native 后端、实际 workspace workflow→DEFAULT→必需测试完整；未更换旧来源消费者。
- ✅ 逻辑/边界：路径/身份/有界原 bytes/唯一 ownership、实例和各级 fixture/subTest skip 负控通过。
- ✅ 异常处理：已测构造、查询、读取、中断、note 故障、关闭不确定性及碰撞负控通过；不宣称任意异步字节码原子性。
- ✅ 关联模块：153 项关联、37 项新旧 CI 配对、718 项 DEFAULT 实跑无失败；关联中的 18 个 Windows skip 单列不授信用。
- ✅ 兼容安全：固定 SKILL 未变，无新权限、依赖、启动授权、readiness 或 snapshot 分享模式变更。
- ✅ 可运行性：本机软件合同与完整三道守护通过；真实 Windows/ACL/DLL/UAC、完整 WP0b 和 R2/R3 仍未通过，不报告整体 100%。

## 本片并行研究：2026-10-11 09:51–09:52 UTC

独立只读研究核验 Codex HEAD `8c0f7011674145da7e10627769fb221c74fbf7a0` 和 Anthropic Sandbox Runtime HEAD `5507fb0e639c00f845554336ece62e27af5b1bb7`，两者 Apache-2.0；主代理另打开固定源码复核。这是两个相关项目的定点刷新，不是完整二十项目重查。

- **采纳：**[Codex no-reparse 源码](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs#L107-L267)中的直接卷、参与 sharing 的访问权、相对 HANDLE 打开与对象 ownership。ICODE 已实现对应内部 owner 和后端候选；收益是减少二次路径解析和清理盲点，成本是 ctypes ABI 与异常负控维护。验收仍要求新取得对象只关闭一次、旧 active/unknown 不误关、真实 Windows sharing/reparse 负控。Rust 成功返回后的 RAII 不能替代 Python DLL 写出 HANDLE 后抛异常的验证。
- **暂缓：**Codex 写入 guard 文件保持目录非空的机制，本片仅只读 pin，尚未引入；受保护晋升阶段须另评估权限和事务影响。首 UAC 同对象及 pre-main DLL 加载证明仍未完成。
- **不适配：**[SRT self-protect 源码](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/self_protect.rs#L51-L74)的锁失败警告后继续，或为兼容放宽到 WRITE/DELETE sharing；ICODE 保持失败阻断。启动后的 `current_exe` 锁也不能证明首次提权启动对象一致。

仅借鉴机制，未复制上游实现、增加第三方依赖或权限；[Codex 许可](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/LICENSE)、[SRT 许可](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/LICENSE)按固定提交记录。研究不替代实际 Windows 或 R2/R3 验收。

### 后续权限片研究准备：2026-10-11 10:07–10:09 UTC

独立只读研究复用上述两个固定提交，未再次刷新 HEAD；主代理另核 Microsoft 原文和现有模块。**采纳（后续设计，尚未实现）：**[GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo)消费 held HANDLE，打开时需要明确 `READ_CONTROL`，当前 `_open` 尚无该权限；不得查询时再按路径重开。安全描述符由单一 owner 有界读取与 `LocalFree` 回收，NULL/absent DACL、未知或越界 ACE/SID、非可信 owner 和修改 allow 均拒绝；目录新增/删除子项权利独立检查。[NULL 与空 DACL](https://learn.microsoft.com/en-us/windows/win32/secauthz/null-dacls-and-empty-dacls)、[文件及目录权利](https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants)是不同合同，不能因无 ACE 或已有文件 pin 直接授运行/新增 DLL 安全信用。

**采纳机制、区别角色：**[Codex ACL 检查](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/acl.rs#L81-L329)的 generic mask 与保守修改权检查。初始 source 的实际 host SID 属于既定可信 host TCB；protected target 则仍仅 Admin/SYSTEM拥有和修改，普通 host/payload只读执行，不把用户 pip 目录当机器保护根。**暂缓：**将 TrustedInstaller 自动扩为 protected target owner，或移植 SRT 的写进程 DACL操作。**不适配：**Codex 查询按路径 share7 重开、忽略部分未知 ACE，以及现 `windows_appcontainer._read_dacl_state` 的路径查询/`_contains_sid` 包 SID成员检查直接充当启动授权。

收益是对象与权限结果绑定，成本为严格 ACL/SID parser、少量 advapi32 绑定和拒绝未知格式的兼容门；无上游代码复制、新依赖或 token 特权。负控须覆盖隐式 owner WRITE_DAC、OWNER RIGHTS、inherit-only/generic write/all、新增子项、查询输出后中断/回收失败、既有 WRITE_DAC/WRITE_OWNER opener及安全描述符漂移。分享锁不覆盖整个 ACL变化窗口，前后 descriptor 相同也不代表从未变化；研究仍不授 publisher、首 UAC、pre-main DLL 或完整 WP0b 信用。

**Execution Mode:** serial

## 当前核验窗口

设计与计划的独立只读 SPEC 首轮指出继承遗漏：冻结后 20 轮和站点检查未显式列出，及资源名称“源码”不准确。主代理已补齐并改为 C 镜像，独立复审 Critical/Important/Minor 均 0。文档契约检查连续两轮 0 疑似项；站点守卫通过（外链未抓取）。

Task1 主代理实跑关联 118 项，106 PASS/12 Windows 平台 skip/0 failure/error；compileall -j1、两个新文件 no-index 格式检查无诊断、密钥与子模块独立守卫通过。后两者只覆盖各自一道，不能据脚本“可以 commit/push”提示跳过完整 preflight。当前完整阶段、Task2 原生及双代码审查仍在实施，尚未提交推送。

【架构级自检报告】（仅文档与 Task1 已测边界）

- ✅ 语法/编译：文档结构/链接检查与 Task1 compileall -j1 通过。
- ✅ 依赖/调用链：native 接口冻结，保持既有 snapshot/provenance 消费者；Task2 接线继续。
- ✅ 逻辑/边界：严格路径、metadata、原 bytes 与关闭后访问测试通过。
- ✅ 异常处理：已测 acquisition/query/read/close 故障及中断、清理不确定性记录通过，不声称全部原生异常已覆盖。
- ✅ 关联模块：主代理 118 项关联实跑无失败，12 平台 skip 单列。
- ✅ 兼容安全：无新权限、依赖、启动授权、readiness 或 snapshot 分享模式变更。
- ✅ 可运行性：Task1 便携逻辑通过；Task2 和 Windows/UAC 原生仍未验证，不报告整体验收或 100%。
