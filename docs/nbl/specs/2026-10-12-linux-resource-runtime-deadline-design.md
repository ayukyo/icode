# Linux resource receiver 运行截止原因分账

状态：本片已完成有限源码实施、正式双RED/GREEN、独立双审与唯一完整软件门，尚待最终文档/index和发布；不授原生因果或 R2/R3 整体验收。下文设计时基线与非目标保留。

## 真实问题、复用与调用链

当前 main `60325a4` 的原 job114693852884 有84条旧 installed dispatch记录；唯一异常为 context/scope/timeout 返回 resource_channel_failed、exit=-9、ready/configured=true、channel incomplete、terminal null且回收true。两 resource_close/exit0 是预期负控。日志没有 kill来源或单调时间，不证明本设计就是该原生失败的根因。

真实问题是已有 `LinuxTaskResourceReceiver._receive` 在运行 deadline 到期时调用 `_fail`，后者清空 transcript 并 kill 绑定进程，却没有保存到期原因。已有 process core 在输出EOF与进程退出竞争中可跳过下一循环体截止采样、返回 error=None；outer 随后只见 incomplete而归为 resource_channel_failed。历史人工delay/__new__ RAM仅为可达性输入，不替本片正式TDD。

复用现有 receiver 锁、运行deadline、stop/done、kill与独立清理，以及 `execution_broker._execute_linux_observed_command` 的收尾/错误选择。没有第二等待器或新执行通道。调用链是公共 resource entry → observer start → 真实 receiver worker与process core → 独立组件收尾 → outer错误分类；scope/helper/session消费与清理所有权保持原合同。

## 最小方案与明确非目标

receiver增加私有、锁保护的运行截止事实，初始false且一旦确认不清除。仅真实 `_receive` 主循环采样运行deadline已到期、并重新确认stop未设置时，在 `_fail` kill之前记为true；不是根据退出码、EOF、异常字符串或事后wall-time推断。读取接口是私有只读属性，返回精确bool。

所有既有stop设置（start失败与close）及“重查stop＋写到期事实”使用同一 `_lock` 作为共同线性化点；join、kill及 `_fail` 调用在锁外。stop先持锁设置则不得新增到期事实；到期先持锁确认则后续stop不能清除已经发生的事实。不能仅锁保护属性、却保留stop写入在锁外。

配置截止 (`launch_start+2s`)、配置callback失败、协议/凭据错误、peer EOF缺terminal、显式close/stop、selector/FD清理unknown都不写这个事实。即使配置截止与运行截止数值相同，只有上述明确运行到期分支可授事实，不能猜其他分支。完整terminal/EOF成功后的清理不能改写结束原因；清理确认仍独立。

outer在既有组件收尾之后、violation observer分类之前读取事实：仅 core `result.error is None` 且事实 `is True` 时补记 timeout。新增补记不得覆盖任何已有非None core错误，随后完全沿用原observer及terminal分类；不扩 `preserved_errors` 集合。因此manager_output_limit/read_failed/proxy_setup_failed仍可能按原合同被失败observer覆盖，不能声称这些错误在最终outcome必然保持。既有cleanup/terminal优先级、输出处理、scope_cleanup字段及消费faulted逻辑不变。真实生产receiver提供属性；旧内部测试double没有属性按false处理，不以truthy对象自证到期。

本片不改公开resource receipt schema、不新增模型工具字段、不改时限或配置截止、不改变process core的“何时算观察完成”语义、不把所有晚收割/exit=-9判为timeout。不扩到 monitor deadline原因、opaque factory或其它清理债务；这些保留独立整体验收项。本片只恢复已经被真实worker确认的运行截止，不承诺涵盖worker未采样即提前结束的所有竞争。

## 精确实施范围与兼容

拟定五路径：`src/icode/linux_task_resource.py`、`src/icode/execution_broker.py`、新 `tests/test_linux_resource_runtime_deadline.py`、本设计及对应独立PLAN；root同时在 `docs/agent-landscape-live.md` 更新研究/实际证据，因此发布集合为六路径。旧tests、process core、scope/attachment、runner/ToolContext、native、vendor、CI与S2a设计/计划只读。实施前冻结实际基线摘要；当前S2a源码作者不得混入本片。

成功流程、旧None调用、公开receipt全部保持。属性是host内部观测，不是payload可提交的授权字段，不授ready/执行成功/OS释放。无新增依赖、权限、服务或系统安装步骤。main-only，正式TEST作者与不同SOURCE作者依序，root唯一完整预检及发布，独立SPEC后不同QUALITY；当前S2a已完成并发布前仅允许本片DOCS准备。

## 验收与暂停线

正式RED必须在未经修改的SOURCE上，由作者与root分别执行实际落盘测试：使用真实receiver `_receive` 线程、真实进程/管道及socket凭据；同步屏障控制EOF、运行到期记录及kill/退出的顺序。不得手动设置到期属性、用 `__new__`/直接 `_fail` 代替运行到期、先改SOURCE再回放RED，也不得靠脆弱sleep猜竞争。测试卫生只释放测试自有资源，不供应生产清理信用。

最小矩阵：

| 场景 | 需要证明 |
| --- | --- |
| worker真实运行到期，core EOF/已退出竞争 | kill前记录；收尾后事实仍true；实际公共broker保留timeout |
| 截止内CONFIGURED+terminal+EOF | receipt完整、事实false、原成功/explicit失败语义不变 |
| 提前自然退出、外部kill、非到期协议错误 | 事实false，不按exit/EOF猜timeout |
| 配置截止或callback失败 | 原协议/启动错误，不冒充运行到期 |
| close诱发stop与到期竞争 | 已设置stop不能新授运行到期；独立收尾继续 |
| output_limit/cleanup_failed等已有core错误 | 即使事实true也不覆盖；既有cleanup/terminal优先级保持 |
| EOF但进程仍活 | 现有core等待路径仍正确timeout，不归因EOF本身 |
| 完整transcript后清理unknown | 结束与释放确认分账、消费失效保持 |

同步屏障若必须新增生产测试hook或改process core/公开接口，先返回设计，不偷偷扩范围。正式计划需要可运行完整测试资产、冻结基线、明确负控与实际错误顺序；通过软件矩阵、限定回归、源码双审及原完整preflight后才发布。新同SHA四Linux安装原生格仍需验证；绿色不能证明历史ARM根因，旧探针记录不替新矩阵，失败不放宽预期。

## 持续研究取舍

独立研究实际GET源码窗口2026-10-12 06:56:37–06:56:40 UTC、LICENSE窗口06:57:35–06:57:39 UTC。固定 [Codex27065a91等待/expiration分账](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/exec.rs#L1017-L1075)（Apache-2.0）及 [CPython v3.11.15 select-return截止检查](https://github.com/python/cpython/blob/v3.11.15/Lib/subprocess.py#L2105-L2116)（PSF-2.0）；旧live错误行锚已另记纠正，未刷新HEAD/二十名单。

采纳独立结束原因机制，收益是保留已经发生的到期事实，成本为私有状态和真实线程/进程负控；暂缓core完成观察合同及原生因果结论；不适配EOF、-9或晚观察自证到期。仅借机制，不复制代码或引入许可不明依赖。设计时尚未实施，审查或研究本身不供应运行/安装/整体信用。

## 正式有限验收记录（2026-10-12 UTC）

批准DESIGN d31876bf/最终PLAN c8f9fe25与407行13方法TEST9c8c3a52先独立双审零遗留。正式TEST作者/root在原两SOURCE分别13方法25有效assertFAIL/0E/skip（7.685s、7.743s）；不同SOURCE作者仅六hunk，receiver3dcff102/broker9de4f953与批准投影逐字吻合，TEST不变。作者/root新13GREEN（7.798s、7.817s），七模块148GREEN（13.414s、13.444s），均0F/E/skip；compileall-j1/diff通过。

fresh SOURCE SPEC及随后不同QUALITY各C0/I0/M0，各自独立新13（7.775s、7.788s）和148（13.667s、13.606s）全部0F/E/skip。root唯一原完整guard session80104、j1，08:18:05 UTC启动，08:27:41 UTC原footer exit0，root08:27:42取得完整三门PASS；原日志 `/tmp/icode-runtime-deadline-preflight.VpUpXl/typescript`。三SOURCE/TEST freeze不变，原门没有全量数量就不猜。批准设计摘要和本次追加事实后的摘要分开，不继承旧S2a守护为本片门。

【架构级自检报告】（本片已执行的软件范围）

- 语法/编译：compileall-j1与完整软件门通过。
- 依赖/调用链：严格六hunk，既有receiver/core/outer链及借用所有权保持。
- 逻辑/边界：真实worker/ACK/EOF/kill前事实、stop共锁、sticky与严格bool负控通过。
- 异常处理：原错误优先级、协议/配置/非到期及独立清理负控通过。
- 关联模块：仅六路径；runner/vendor/CI/原core及其它平台不改。
- 兼容安全：限定148回归通过，无schema/权限/新依赖。
- 可运行性：唯一完整软件门exit0；新同SHA安装/原生因果及R2/R3整体仍未授信用。
