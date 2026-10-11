# Windows WP0b：可信启动与受保护晋升

日期：2026-10-11（Asia/Shanghai）。基线 main `fb35f557a84b46f9816d807bf3545ca2cc1deed7`，vendor `21566a5`。用户已批准推荐路线并委托一般技术取舍；不再重复询问同一设计，不扩大权限或降低验收标准。本文件是批准路线的具体化，不是实现或原生通过声明。

## 真实问题、复用与调用链

当前 provenance 验证后关闭原文件，再用路径启动 verifier；bootstrap 的 setup/spawn 仍退出 78。PE 的 imports/delay/manifest 静态检查已通过实际四格安装，但生产 parse/load/launch 标志仍为 false。缺的是从校验对象到启动对象及安装状态的完整可信链，不是增加一次摘要查询。

复用现有 Windows handle-relative 打开、固定架构资源和离线来源验证、原始 bytes PE 分析、严格有界子进程机制及认证管道。工作区 snapshot 的 share7 和执行前关闭的直达卷 canary 不能作为 startup pin。不要全局修改 snapshot 分享模式，也不将旧诊断接口升级为授权。

完整链为包内固定资源 → no-reparse/直接卷及祖先 pin → 原 HANDLE 字节/来源/权限/加载检查 → 固定操作首次 UAC → 受保护 staging 的原字节复制及重新核验 → marker 最后提交 → 晋升后固定镜像启动。任务 token、WFP、Job 和正式 payload 属于后续 WP1/WP2；本片不能提前开放。

## 取舍

采用已批准的稳定路径路线。Windows ShellExecuteExW 的 lpFile 是路径、hProcess 是输出，不存在输入 image HANDLE；必须实际证明持锁期间路径消费仍指向已核验对象。不要声称调用固定字符串便已证明同对象。

不采用 SYSTEM 服务、MSIX、额外 token 特权或安装外部工具。单纯调用 runas 后再比 hash 不能关闭竞争窗口，也不作为兼容回退。

## 分片及完成边界

| 顺序 | 交付物 | 关闭的门 | 明确不能替代 |
| --- | --- | --- | --- |
| 1 | 启动文件及全祖先 pin、原 HANDLE 有界读取、owner 生命周期 | 对象持有与字节快照的基础合同 | ACL、publisher、DLL、UAC、安装授权 |
| 2 | 从 HANDLE 核 owner/DACL，系统来源加载检查及固定资源 provenance 接线 | 完整核验窗口 | 首次提权时实际启动绑定 |
| 3 | KnownFolder protected root、私有 stage、owned journal、marker 最后提交 | 受保护晋升与恢复 | host 在 UAC 等待中死亡仍安全 |
| 4 | 首次 UAC 及晋升后启动，锁接管/宿主死亡/跨管理员负控 | WP0b 原生启动合同 | WP1/WP2 隔离、配额及 R2/R3 总验收 |

分片按依赖连续实施，不把较易通过的第一片重新定义为 WP0b 完成。需要 Windows 才能验证的项在 Linux 软件测试中记为未验证，不以 mock、签名或 job success 补齐。

## 1. 对象 pin 合同

新内部启动对象模块与 snapshot 后端分开。只接受明确的本地绝对盘符路径；拒绝 UNC、远程、相对、ADS、dot 段、空组件及设备别名。用 QueryDosDeviceW 将盘符绑定到直接 HarddiskVolume，不先 resolve 文件系统组件；拒绝 SUBST、多跳别名或非直接卷，不回退旧路径。

从直接卷打开并持有根及每段目录，NtCreateFile 使用 RootDirectory 相对打开和 OBJ_DONT_REPARSE。目录使用实际参与删除共享检查的访问权，文件以读取数据权限打开；不允许 FILE_SHARE_WRITE/DELETE。保持所有 HANDLE 非继承。句柄取得后立即登记 ownership，再进行可能失败的查询或读取。

每个对象以 volume serial 和 128-bit file ID 绑定，拒绝 reparse、delete-pending、错误类型或跨卷。文件须单链接、非空并有固定上限（镜像 64 MiB，proof 2 MiB）；同一 HANDLE 有界读，读取前后身份/尺寸/变更时间一致，完整内容 SHA256 与返回 bytes 一致。拒绝超量、短读、读取故障；摘要不是来源认证。文件和目录分享锁不覆盖全部元数据或新增子对象，不授对应信用。

一个 owner 持有整个链；构造异常、读取中断、正常退出及显式 close 均逆序尝试关闭全部已取得 HANDLE。重复 close 不重关，close 后访问拒绝；构造/主体中断保留原异常，清理故障不能伪造完成或把 KeyboardInterrupt/SystemExit 改成普通错误。原生 close 失败保持失败记录，不把可能仍 live 的句柄计为已确认关闭。

基础模块无 shell、进程创建、文件写入、权限变更或 launch grant。明确的内部调用方将在第二片绑定 package-local 资源；不向模型暴露任意路径入口。

## 2. 独立权限与加载检查

所有权限检查消费 held HANDLE 的 GetSecurityInfo，拒绝 NULL DACL、未知 ACE、错误 owner 或允许非可信主体修改/删除/WRITE_DAC/WRITE_OWNER 的 ACL；目录新增子项亦独立检查。初始包内来源处于已安装包/可信 host TCB，不承诺抵御同权限可信 host 或管理员篡改；受保护目标仅 Admin/SYSTEM 拥有、普通 host/payload 只读执行。不能为了通过 pip 用户目录而声称它已是机器 protected root。

C 镜像、proof、release 和匹配 Go verifier 都保持 pin，来源结果须绑定该次原字节、固定工作流/身份/架构和完整 receipt。不采用相邻 sha 认证出版者、不允许 C↔Go 循环自认证。首次 C 的安装/发布 TCB 与 C 内 Go digest 的信用分开记录。

静态普通/delay imports、全部 manifest 之外，实际验证 pre-main DLL、SxS/redirection、cwd/邻接恶意 DLL。系统 DLL 来源与 SYSTEM32 动态加载约束独立成立；/MT 或 main 中设置 DLL 搜索参数不能证明入口前安全。未知依赖拒绝，不能因 static complete=true 授 runtime_load_verified。

## 3. 晋升及恢复

受保护根只由系统 KnownFolder 获得，不信任 ProgramData 环境、cwd/PATH 或模型路径。先核全部祖先 owner/DACL 与 no-reparse；只以创建新对象语义取得 private stage，已有同名对象拒绝、不接管。

从核验后的 held 原字节复制 C/Go/proof；目标 HANDLE 再核身份、架构、来源及内嵌 Go digest。journal 记录本次确实创建的对象；marker 最后写并核回读。失败只回收本次 owned 对象，遇到身份替换或未知清理保留证据，不盲删旧安装。重复初始化以合格安装合同判断，不用名字、长度/mtime 或 marker 存在判断。

## 4. 启动与宿主死亡

首次 UAC 只接受固定初始化操作，不接受用户命令；由用户操作系统授权，不自动点击。宿主持锁须覆盖完整核验、UAC 等待及子进程接管/原生确认窗口。SEE_MASK_NOASYNC 不是锁托管或父死取消证明。

特别测试 host 在 UAC 等待时被杀，之后用户仍确认的情况；锁随 host 死亡释放时必须独立证明不会越过安全边界。没有回执只能判 unknown，不能写 payload_started=false。锁交接失败不得继续，不能假定标准用户能给另一管理员 elevated process DuplicateHandle。若稳定路径方案在此门失败，保持阻断并依据实际证据重新设计，不自动新增服务或降低同对象指标。

原 host SID 保持宿主身份，不因另一管理员接受 UAC 改绑 DPAPI；凭据创建/存储仍在 WP1 验收。UAC 取消、初始化异常和 API 不支持保持结构化失败，禁止退回用户可写镜像或裸执行。

## 验收矩阵

软件：路径边界、原 HANDLE bytes、短读/超量/metadata 漂移、链接数、跨卷、早期关闭、全部构造失败点与复合异常、重复 close、对象 owner 被错用或复用拒绝。

原生：镜像/硬链写入、预有 WRITE/DELETE opener、每个祖先 rename/junction/reparse、盘符 alias、ACL/owner/新增 DLL、pre-main SxS、UAC 取消/宿主死亡/跨管理员、stage 碰撞/部分写/目标摘要失败/marker 前中断及 owned-only 回滚。测试不得修改宿主全局防火墙、权限或系统配置来掩盖失败。

平台：Windows 10 22H2 与 Windows 11，x64/ARM64，普通 host；实际支持的 Python 3.11/3.12 安装矩阵。Windows Server CI 只授该实际系统的证据，不能替代 Windows 10。未具备运行环境的格保留缺口。

独立 SPEC 后不同 QUALITY、关联回归、完整 preflight、语法/依赖/逻辑/异常/关联/兼容/可运行七维检查通过后，按用户授权提交推送 main；编译 -j1。PE 静态、pin 软件、签名、UAC 与完整 WP0b 分别记账；launch_authorized、isolation_ready 和自动模式只在对应完整合同实际成立时才变更。

## 并行研究与自审

2026-10-11 独立只读刷新 Codex `8c0f7011674145da7e10627769fb221c74fbf7a0` 与 SRT `5507fb0e639c00f845554336ece62e27af5b1bb7`，均 Apache-2.0。采纳 Codex [no-reparse/relative open](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs)机制；guard 维持非空的条件另验，本片不写 guard。暂缓将 [runas 分支](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/setup.rs)作为完成证明；不适配 SRT [锁失败继续](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/self_protect.rs)。借鉴机制，不复制源码、不加外部运行依赖或权限；成本为内部 ctypes 和负控，收益只对应实际通过的合同。

主代理另核 [CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew) 和 [SHELLEXECUTEINFOW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-shellexecuteinfow)。研究不是原生实验，未刷新完整二十项名单。

自审：无新增授权、无 snapshot 分享模式变更；每项安全检查与实际消费者对应；基础 pin 不冒充完整启动。用户已批准路线并要求非必要不再询问，因此不设置重复文档批准停点；实现仍按上述实测门逐项推进。
