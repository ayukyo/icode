# Linux 工程验收桥接的定点上游研究

日期：2026-10-09；ICODE基线 main `8d53670192e3e2cbfebaa0300d697fb3036308be`、vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`。本记录只读、不执行上游或ICODE软件、不安装/下载artifact、不访问私有KEY、模型HTTP、提权或服务配置；没有源码复制、新运行依赖或权限。只复核相关Codex项目，不刷新完整20名单。实施与测试仍须[本片设计](2026-10-09-linux-engineering-bridge-design.md)的独立验收。

## 观察来源与固定版本

独立研究者窗口为 `2026-10-09 03:10:45–03:13:44 UTC`，现已STOP；root转交事实作为独立输入。固定Codex提交 `82883da25e3be5883e905afa02c3a639d02a97aa`，GitHub commit committer `2026-10-09T02:59:21Z`，观察时未归档、根许可证Apache-2.0。没有将workspace `0.0.0`一类版本占位当发布版本。

设计作者在本轮通过官方GitHub/raw另作定点回读：landlock.rs全部115行（独立研究记录116行计数差异属于末尾行计数，不扩大内容）；manager.rs273–470、478–578；linux_run_main.rs166–346；linux-sandbox README与根LICENSE全文；GitHub commit与repository元数据再次确认固定SHA/committer/archive/license。该补核只说明这些文件/范围，不是整个仓库或上游runtime审查。Firecrawl/Exa在独立研究环境不可用，使用官方GitHub fallback，没有安装替代工具。

| 材料及精确链接 | 实际读取 | 证据类型与允许观察 |
|---|---|---|
| [landlock.rs](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/sandboxing/src/landlock.rs) | 独立全文；作者全文 | 实际代码：将effective PermissionProfile、command cwd、sandbox policy cwd、managed网络与显式legacy选择编译为helper argv；参数编译不等强制执行 |
| [manager.rs273–470](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/sandboxing/src/manager.rs#L273-L470)及[478–578](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/sandboxing/src/manager.rs#L478-L578) | 独立、作者同范围 | 实际代码：effective权限与native cwd分层；缺Linux helper报MissingLinuxSandboxExecutable；trusted startup PID namespace选择独立于repo/command配置 |
| [linux_run_main.rs166–346](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/linux-sandbox/src/linux_run_main.rs#L166-L346) | 独立、作者同范围 | 实际代码：默认outer bubblewrap后re-exec inner；inner核capabilities、应用seccomp/no_new_privs并fork/exec/reap；outer失败不转legacy。full-disk-write另有分支，不能把默认描述外推所有profile |
| [linux-sandbox README](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/linux-sandbox/README.md) | 独立、作者全文 | 官方文档：bubblewrap默认、nested保护、系统/随包helper选择与trusted startup例外；不是本机enforcement结果 |
| [根LICENSE](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/LICENSE) | 独立、作者全文 | Apache-2.0根许可观察，不外推所有vendor子目录 |
| [vendor/bubblewrap/LICENSE](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/vendor/bubblewrap/LICENSE)及[COPYING](https://github.com/openai/codex/blob/82883da25e3be5883e905afa02c3a639d02a97aa/codex-rs/vendor/bubblewrap/COPYING) | 独立connector仅LICENSE响应1–7许可头；作者raw LICENSE为指针COPYING，另读COPYING前22行 | 许可局部证据：GNU Library GPL v2（1991）；LICENSE在tree为symlink mode120000/7bytes、blob`d24842f3cdcf2e447f9a7a26fa387ad63f5c4b91`，COPYING blob`5bc8fb2c8f757e34a0d8f4644f589d57609e213f`/25383bytes由独立研究元数据提供。未全文审COPYING或分发义务，不称“全仓Apache”或“已完成bwrap许可审计” |

作者最初尝试错误路径`codex-rs/linux-sandbox/vendor/bubblewrap/LICENSE`得到404，随后官方tree确认正确路径`codex-rs/vendor/bubblewrap/LICENSE`；该404不是上游缺LICENSE或归档证据。independent connector可能解symlink而raw返回目标名，两种读取对象明确分开。

## 机制观察与ICODE映射

这里的上游观察均是固定源码/官方文档。没有运行上游sandbox，不声称其在本机Linux6.8/systemd249、某版本Python或ICODE CP上实际通过。ICODE自身source/helper/host/CP/模型层仍独立验证。

| 任务/阶段 | 上游机制 | ICODE现状 | 决策与理由 | 成本/许可/安全/兼容影响 | 可验证验收项 |
|---|---|---|---|---|---|
| 工程控制面接线 | profile/cwd→helper argv与实际helper执行分层 | frozen VerificationPlan、ToolContext、broker/双私有通道已有；完整正控mock dispatch；分离Git tree投影存在已知生产阻塞 | 采纳：配置/编译/执行/消费分别记证据；root先独立设计并验收session-aware Git投影修复 | 本文仅验收设计/研究，不实施生产修复；不复制源码，无新许可义务 | 前置修复后再核真实session的dispatch→工程gate/CP/pack同run连接；仅新增测试不能关闭L2 |
| 缺能力失败关闭 | manager缺helper拒绝；outer失败不回legacy | LandlockreadyFalse、unsupported工程资源不fallback、helper完整性核对 | 采纳：保留原Native拒绝，并观察直接runner有限窗口的实际失败 | 不开Linux/mac/Windows准入，不绕guard，不把环境存在当PASS | NATIVE-01；missing/badhelper、资源/observer不完整、无普通subprocessfallback |
| 可信启动与repo输入分离 | manager296–300的trusted startup PIDnamespace选择 | CLI显式预设、真实session.policy/run_id，项目源码是非可信测试输入 | 采纳：Plan/解释器和session取可信host；不把模型/项目配置授权成新policy | 复用现有接口，不增配置解析/批准/权限 | frozen环境/工具/root漂移拒绝；CP执行根匹配；model_double明确 |
| nested readonly/deny | 默认bwrap overlays与保护carveout | Landlock当前拒绝workspace内deny交叠；POSIX manager虽已有checkout/code分离，但该根无.git，tree捕获返回workspace_not_repository_root，父层Git身份非空导致工程gate1802–1805必拒绝 | 暂缓新后端；先由root另立独立session-aware Git tree投影生产修复设计，保留分离保护布局 | 不能仅补测试达成L2a/L2b/ENG-06；不移.git、不清空身份、不mock或降断言，不设native readyTrue；bwrap部署/许可成本未承担 | ENG-01的policy.prepare不等工程成功；前置投影修复验收后才核ENG-06与L2正控；deepcheck最终源码/范围在step_start前固定 |
| 任意语言/依赖生态 | 上游通用命令路径 | ICODE已有限unittest/go adapter、固定预算与模板 | 暂缓任意语言、安装依赖、通用provider扩权 | 避免新增依赖和宿主副作用；缺依赖保持真实失败 | 零测试/全skip/缺依赖不计正控，实际测试报告非质量认证 |
| 准入或分发移植 | 上游独立sandbox与vendor资源 | ICODE完整准入尚未过、当前wheel/helper独立合同 | 不适配：readyTrue测试覆盖、复制bundled bwrap、根Apache外推vendor许可 | 不复制/分发，不改policy ready；不制造许可证合规声明 | 新SHA实际组件/CP/pack逐层；源码/README不授native/model信用 |

采纳的是机制与验收结构，未发现或声称Codex具有ICODE相同CP attempt、engineering operation/receipt、独立pack合同。上游PIDnamespace trusted startup例外允许同UID信号的风险由其README描述，不是本片应引入的默认设置，也不能替代ICODE单工单资源或完整policy要求。

## 本仓读取、独立性与未运行边界

独立研究者本仓core身份：isolation`3ee49c12efce8002a32e5b86fd8acc1edf221042df8d7177fff18e9fcec0816d`、execution_broker`ee1b60b5c922a72de23234069d83e603287b66f3f6bed70323944d1663aab6f3`、linux_task_scope`6ce8cc433395a2110ba636d7b6eae0af2a6614bcea62b23687e577432493f6f9`、engineering_verification`0d98080f9ad5aec567b23073048eca8bd584924f26ee927f17a49e582c901027`、runner`2b145db41b3ebbd0f90f3e9d8b19e73b9ca6a08c97e1ba5fbe59d6d777ea671b`、test_contract_engineering`f4845043d0ad2d4b5f39c54cf3143b8c09479f31f49c06114c589e8efa2bb6a9`。作者另独立计算，六项一致；作者实际阅读范围与完整文件SHA清单见设计，不冒称root重复全文审查。该一致性是源码身份，不是实际执行证据。

根此前只读环境快照与8d完整软件门是root证据，不属研究者/作者实际resource、模型或installed验收。作者本轮运行生产/测试/helper/编译/安装/模型HTTP数均0。实际操作仅文本/元数据读取、官方源码HTTP读取与apply_patch写指定两份Markdown；没有GitHub写、commit/push、plan/landscape或其他文件修改。

## 静态自审与结论

修订历史与设计同步：原作者自审C0/I0/M0后，fresh独立SPEC发现C0/I2/M0；I1为checkout/code无.git的tree投影生产阻塞，I2为原稿混用code/deepcheck开始后改源码时间线。原始两文档SHA与具体纠正见设计的修订历史，不能覆盖原I2结论。本次作者另只读核runner1788–1810、3558–3598、3620–3675、3838–3857（1525–1608与原读范围重叠），SHA仍`2b145db41b3ebbd0f90f3e9d8b19e73b9ca6a08c97e1ba5fbe59d6d777ea671b`；未运行/修改源码或测试。

修订后先selfSPEC再selfQUALITY：上游观察不代替本仓已知阻塞；nested映射、前置生产修复依赖、deepcheck捕获前固定与after-start mutation负例已同步；日期/路径/许可对象/信用边界仍明确。修订后作者自审C0/I0/M0，非重新独立SPEC结论。

静态研究完成；实际连接有已知Git投影前置阻塞且未运行，verdict为`partially_verified`（固定官方材料与本仓身份已核、运行层未验）。允许称“有固定源码支持的分层验收设计输入及明确前置阻塞”，禁止称“仅新增测试即可接通”“上游机制已在ICODE部署生效”“Linuxready”“R2/R3整体通过”。root另立最小Git投影生产修复设计；本研究/设计作者STOP，等待重新fresh独立SPEC，不进入计划/实现。

## 实施启动前独立刷新

2026-10-09 08:02:07–08:05:59 UTC，独立 `/root/linux_bridge_stage_start_research` 两次官方远端核main：Codex `2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4`，Aider `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`。两commit API各一次403后改官方git ls-remote与固定raw，无连续重试；本轮未取得committer/archive元数据。两根LICENSE全文均Apache-2.0，未审全依赖或重读bubblewrap许可。无本工程runtime、模型、文件写入或源码复制。

| 固定来源 | 实际阅读范围 | 完整raw Git blob |
| --- | --- | --- |
| [Codex landlock](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/sandboxing/src/landlock.rs) | 全115行 | dad16e238c081a36d01914e2847ba16cf67b220b |
| [manager](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/sandboxing/src/manager.rs) | 273–578 | f6c281a061d0af01ddf0ee9d56646ea5c0943ad9 |
| [linux_run_main](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/linux-sandbox/src/linux_run_main.rs) | 166–346 | 5c08c8c39ace69d95fcd5a22fa49c4b6b00eb36c |
| [Linux README](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/linux-sandbox/README.md) | 全113行 | 95865ded7462b92c49da4f56c405a3eea7993156 |
| [exec](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/core/src/exec.rs) | 85–130、258–293、784–856、947–1193 | f72396e38320e838e21b6a9ceaaa433ada62f0c0 |
| [exec_output](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/protocol/src/exec_output.rs) | 全169行 | 63675fe1d1046e74b6fa60b2c9de1196dabf49c3 |
| [process_group](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/utils/pty/src/process_group.rs) | 全309行 | f403b7e647dbf697b88d14e8f5468dc277da648e |
| [Codex LICENSE](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/LICENSE) | 全10926bytes | 4606e72e042564097e8780d66c1d4dcb611869bd |
| [Aider repo](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repo.py) | 20–140、510–570 | 92b5e3bf5b81ec1bcee62feaf64c9c09fc607f54 |
| [Aider commands](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/commands.py) | 970–1060 | 3881403c5c10212119e77a3ab0d3e092830054e6 |
| [Aider LICENSE](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/LICENSE.txt) | 全11358bytes | d645695673349e3947e8e5ae42332d0ac3164cd7 |

Codex所列8文件与原82883固定提交完整raw blob均相同，仅证明选中文件身份。上述blob由实际raw字节按Git算法计算，非API tree结果；读取范围仍以上表为限，不把完整摘要当全文审计。

采纳：权限/参数编译、helper执行、命令结果和业务终结分层；FullBufferWithExpiration的leader退出后drain期限与清理错误传播；Aider整仓/subtree显式范围。ICODE复用既有Plan/session/私有通道/CP/pack，收益为清楚定位不完整证据，成本为观察和身份负控；验收对应ENG-01/02/03/04/05/06、CMD-04/06及NATIVE-01，核真实测试、scope终态、CP与pack，不凭exit0或组信号授成功。

暂缓bwrap迁移、任意provider、reconciliation、缓存和业务补偿，需独立部署/许可/恢复合同。不适配ShellTool drain超时abort后空stream、无expiration的FullBuffer及启发式sandbox denial来替代本仓完整证据；不适配用killpg成功/leader reaped证明全部后代收束，或默认exit0对象/空test返回None证明运行。没有sudo/service/系统权限或Native准入变化。root已发布G0/G1，旧8d阻塞保留历史；实际Linux桥接、installed、模型与R2/R3仍逐层待验，完整20名单本轮未重查。

## Task2 失败、未知与再次执行许可复核

2026-10-09 09:48:31–09:49:19 UTC，独立只读研究再次由官方git ls-remote核对Codex2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4、Aider5dc9490bb35f9729ef2c95d00a19ccd30c26339c未变；两根许可证全文重读仍Apache-2.0，未审全依赖、不复制实现、不运行上游或本工程。

本轮实读Codex exec.rs 85–130、258–293、784–856、947–1193，process_group.rs 1–200，新增 [orchestrator.rs](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/core/src/tools/orchestrator.rs#L394) 1–330、360–626；Aider commands.py 970–1110。exec_output.rs本轮明确核到1–108，其后合并输出截断，不称全文重审。一次错误tools/src/orchestrator路径404后改正确core/src/tools路径成功，不认作上游缺实现。

Codex普通非零、Timeout、Denied分层；FullBufferWithExpiration的drain/cleanup错误传播，而ShellTool超时drain可能返回空输出。orchestrator只有特定Denied分支才按策略/工具/授权重试，strict auto-review第二次需fresh review；这是同次调用重试，不是崩溃恢复后旧回执可再次执行的证明。Aider/test多种路径可返回None，适合交互反馈，不提供本工程验收凭证。

采纳：结果分层、清理未知不被exit0覆盖、恢复读取与新执行许可分离；复用ICODE当前CP/receipt/scope和16个新增负控，验收确定失败关闭失败、timeout/截断保留未决、原始收束事实与注入副本分开、未知恢复不再次dispatch。暂缓自动重试/补偿/审批缓存扩展；不适配空输出或None作通过、killpg成功作后代收束证明、降沙箱重试作fallback。成本为测试和身份断言，无新依赖/权限；仅源码研究，不授Native或R2/R3通过。

阶段结束独立刷新窗口2026-10-09 10:10:52–10:11:15 UTC：官方远端HEAD及refs/heads/main仍为上述两固定提交。重新读取Codex exec.rs 85–130、258–293、784–856、947–1193，process_group.rs 1–200，orchestrator.rs 360–626，以及Aider commands.py 970–1110；对应失败/清理/受约束重试语义与取舍未变。本次未重新审许可证、全依赖或完整仓库；不运行上游或本工程、不复制源码、不授ICODE运行信用。此前09:48根许可证观察保留原日期，不伪装本次重审。
