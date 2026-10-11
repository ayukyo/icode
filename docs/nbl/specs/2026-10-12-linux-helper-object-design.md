# LA-2b2：Linux 助手打开对象与独立所有权

状态：设计历史窗口为下一片候选；现已完成内部对象软件实现及独立代码双审，完整门/发布尚待执行，不授执行信用。root设计实际sequential-thinking116–118、实施119–121，回读现有Landlock包装、PreparedCommand、普通/observed broker、task scope与原生close_range。用户已要求常规推荐方案自主推进；本片无新权限、依赖或安装步骤。

## 1. 真实问题与最小选择

LA-2b1补了包内候选的有限ELF机器核验，但当前prepare、wrap和Popen分别按路径取对象，尚无助手执行FD的持有/回收合同。现有workspace FD是借用资源，不能通过关闭所有pass_fds来补助手回收。

| 选择 | 收益与代价 | 结论 |
| --- | --- | --- |
| A：先建立独立的同FD核验对象，再接真实dispatch | 职责和失败清理可单独证明；此片不启动助手 | 采纳 |
| B：全局sandbox缓存一个FD | 易跨工单复用，prepare与任务生命周期错位 | 不适配 |
| C：一次加入密封、发布者认证及全部入口 | 范围超出当前对象所有权缺口 | 暂缓 |

本片只新增内部`src/icode/linux_helper_object.py`及专用测试；LA-2b1函数、resolver、PreparedCommand、生产broker、selector、CLI/MCP、原生C和vendor不改。不生成产品ready或执行授权。

## 2. 内部接口与流程

`open_linux_helper_object(binary: Path, manifest: Path) -> LinuxHelperObject`只供可信宿主代码调用，不暴露模型工具。实际Linux平台及`platform.machine()`有限映射必须先通过；不接受调用方自行选择架构、摘要或PATH fallback。错误类型为输入无关的`LinuxHelperObjectError`，KI/SE保留原对象。

打开binary/manifest使用`O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK`，缺机制时拒绝，不使用flag=0降级；NONBLOCK避免无writer的FIFO在fstat前阻塞，regular读取语义不因此改变。按打开FD的fstat核regular、单link，binary需mode具有至少一个execute位。该mode检查不是ACL执行能力证明。只阻止末段链接，不承诺祖先可信、root拥有或同UID抗修改。

manifest从其FD最多读取66字节，严格接受现有64个小写hex及可选单LF合同，额外字节拒绝；manifest FD核验后关闭。binary FD从offset0读取有限64字节头并复用LA-2b1解析及真实宿主映射；同一个FD以有界块读取全部摘要，文件大小上限64 MiB、单块64 KiB，短读继续、EOF完成、超限拒绝。用fstat前后核dev/ino、size及mtime_ns/ctime_ns一致，检测已观察到的漂移；不把前后相同解释成内容不可变或ABA防御。

```mermaid
flowchart LR
    A[真实宿主前拒] --> B[no-follow打开两对象]
    B --> C[manifest有限读取]
    C --> D[同binary FD有限头与全摘要]
    D --> E[返回独立owner 非执行授权]
    E --> F[显式close或context退出]
```

owner只持有binary FD、已观察身份/架构/摘要，不能从路径重开或转让close责任。`fileno()`只核仍打开、regular及dev/ino相同；失败不得重新查路径。单link与时间/大小稳定是取得对象时的检查，不在fileno中冒充持续内容核验。取得后pathname删除可使nlink为0、rename/unlink可改ctime，不因此把同一held regular对象认成另一个对象。返回FD不代表当前字节不可变、同身份FD复用可完全检测、prepare已固定或可直接Popen。可信调用方禁止外部close/dup2覆盖owned FD；不同对象复用应识别并拒绝，不能声称同对象复用检测完全。

`close()`及context协议负责独立回收，不依赖析构器；已完成关闭可重复调用。对close失败或已识别外部替换不盲重试，报告固定错误，避免关闭被复用的无关FD；不能把未知关闭写确认成功。工厂失败遍历自己取得的资源，普通错误不输出路径/异常正文，信号不被普通错误覆盖。参考现有`_select_cleanup_error`的优先级而不复制整套监督链。

## 3. 关联与下一片边界

本片对象尚未传给任何执行器；没有workspace或channel FD，也不调用subprocess/systemd。后续接线必须覆盖`_with_workspace_object_fd`、resource wrapper、`LinuxTaskScope.wrap`元数据传播，以及普通/observed broker的明确finally责任。scope包装失败不能丢失已取得owner。原生close_range应关闭启动FD、防止payload继承，但需分别真实验证无scope/有scope及x64/ARM64。

如果以后在dispatch创建owner，只能报告每次dispatch同FD核验/启动；模型前prepare固定同对象是另一个生命周期合同。无全局缓存、自动回退或网络candidate合流。现有借用workspace、Reviewer pin、socket及quota owner各自保持责任。

## 4. 验收与许可

先实际RED再实现：新模块缺失/AttributeError只作脚手架，不算有效RED；针对已有同路径多次读取的真实缺口建立可执行负控，或先完成完整导入骨架后用行为断言取得RED，独立记录两者。正控必须真实临时regular文件及摘要，验证header和digest使用相同FD，取owner后删除/替换pathname不改变held对象读取；这不是执行证明。

负控覆盖错误平台/host前拒；缺失/坏/超长manifest、目录/socket/软硬链接、binary与manifest各真实FIFO且无writer（测试用独立子进程超时/kill/reap保护）、错ELF/hash、mode、超限/持续增长、短读、可见漂移；各open/fstat/read/close阶段普通故障与KI/SE、实际FD回收、重复close、不同对象FD复用不误关、两个owner独立。generic/Windows及显式脚本保持原回归。完整preflight、compileall-j1、独立SPEC→不同QUALITY、精确main发布按原门执行。未完成源码前不写测试通过或可运行性100%。

独立只读研究2026-10-11 19:35 UTC与root调用链回读：固定Codex `27065a91ccbf5ba8532844be3777fcf83b77820d`的[bundled_bwrap](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/linux-sandbox/src/bundled_bwrap.rs)提供同打开对象摘要/exec分层输入，Apache-2.0已核。采纳对象及所有权分账，暂缓exec与密封，不适配可选摘要、链接打开或关闭全部pass_fds；无代码复制、新依赖或许可成本。此次man-pages取文超时，不能据未获取内容授procfd加载保证；未刷新HEAD或全部20名单。

2026-10-11 20:14 UTC实际软件记录：冻结设计SHA=`39447b7e8483d464f401606cd47ebdcf1637374f6a4e2dbcbe8104fe134e2e3f`经独立SPEC修FIFO前阻塞缺口后、不同QUALITY各零遗留；同设计计划经不同双审零遗留。磁盘骨架单例1 assertion FAIL/0ERROR→不同writer完成204行源码，测试563行保持冻结；root42相关方法PASS/0skip，fresh全局CODE SPEC→不同QUALITY各42方法PASS/0skip、C0/I0/M0。实际hash及完整流程见[实施记录](../plans/2026-10-12-linux-helper-object.md)。尚未接生产或启动helper；完整守护/发布另账。

【架构级自检报告】（内部对象软件候选）

后续完整门：2026-10-11 20:20:01 UTC root实际完整preflight三道exit0，全仓compileall-j1/site/governance/排期及文档检查完成；source/test保持冻结。软件门通过，main发布下一操作；上方“完整门待执行”为此前时点记录，不授原生exec或产品ready。

- 语法/文档：接口与当前源符号已回读；设计及代码不同双审零遗留，compileall-j1通过。
- 依赖/调用链：只复用有限ELF解析，无生产接线。
- 逻辑/边界：同FD读取与执行/不可变/祖先信任明确分开。
- 异常处理：规定OS故障、双角色FIFO、关闭未知和信号优先级已实际测试通过；未知关闭不冒充确认。
- 关联模块：现有wrapper/broker/quota及借用FD不修改。
- 兼容安全：无权限、系统服务、安装步骤或自动授权扩大。
- 可运行性：内部对象及42相关软件方法通过，完整门/发布待完成；不授安装包、原生启动或R2/R3通过。
