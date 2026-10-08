# R3 自动模式配置提示：最小设计

日期：2026-10-09；基线 main `ccbe67bb65d5246a61fb3078b85c83fba5aa7c42`。本文件只设计 CLI/UI 提示文字，不接验证计划工厂，不改变任何执行或授权合同。用户已要求自主连续开发 R2/R3；按该授权选择下述最小方案，覆盖技能默认逐次等待，但不扩大权限、模型请求或默认测试命令范围。

## 三问与选择

真实问题：`cmd_workbench` 在隔离后端满足当前配置判据时打印“自主执行：已启用”，但该入口构造的 `NativeChainExecutor` 没有验证计划 provider，正式 code/deepcheck 仍可能因缺计划阻断。CLI 文案不能代表工程检查就绪。

已有实现：UI 的 `capabilityEnabled` 已注明“仅服务端配置”，保护卡片也仍显示检查未完成；复用这两个翻译项及 CLI 三分支。`capabilities.autonomous.enabled` 继续表示现有意图入口可用，不是整个任务执行成功或各步骤条件就绪。

调用影响：CLI 仅改 enforced 分支字符串；UI 仅改中英文 `capabilityEnabled` 的值。按钮状态、意图 payload、HTTP API、executor、隔离、资源、provider、状态机及配置均不变。既有自定义 executor 不新增属性要求。

方案 A（采用）：文字层明确“已配置；任务仍需通过执行检查”。收益是小白不会把服务端配置理解为研发检查已通过；无新增探测或接口成本。

方案 B（暂缓）：增加 configured/execution_ready 能力字段。需要定义跨平台、步骤、工厂和自定义 executor 的真实就绪协议；本片没有足够证据，不凭静态属性给出肯定结论。

方案 C（不适配本片）：启动工作台时试跑工程检查或禁用启动按钮。会新增副作用或改变现有启用语义，且不能替代每任务实际策略和身份检查。

## 精确实现合同

1. `src/icode/cli.py` 中 enforced 分支从“已启用”改为“已配置；任务仍需通过执行检查”。未启用与 policy_unavailable 分支保持原文；不改变隔离判据或传给 server 的 limits。
2. `src/icode/workbench_assets/app.js` 两个既有翻译值改为：中文“已配置；任务仍需通过执行检查”，英文“Configured; execution checks are still required for each task”。既有 key 名保留。`renderAutonomy` 的映射与按钮逻辑保持逐字不变。
3. `tests/test_workbench.py` 先新增行为 RED：真实调用 cmd_workbench 的软件 fixture 覆盖 enforced/disabled/policy_unavailable 三状态，捕获输出并核传给 server 的配置不变；两语言精确文案存在、旧肯定提示缺失。保留现有 HTTP enabled/custom-executor/按钮/安全 payload 与保护卡片断言，不以删断言制造 GREEN。
4. 不增加依赖、路径/模型配置、DOM、API字段、自动检查或后台任务；不修改官网、其余静态资源、vendor 或 CI。
5. 提示不宣称零写入、自动检查已通过或任意项目可运行；实际任务遇缺计划/资源仍按原流程阻断。软件 mock 不授任何原生执行信用。

## 验收与风险

冻结设计后先独立 SPEC，再不同 QUALITY；实现采用新鲜唯一三文件写者，TDD 后全局两审。root 全读实际差异与调用点，定点工作台/自主执行回归，20轮定点、DEFAULT、全仓 preflight 严格串行，已有 skip 保留；语法与治理/站点/对照守护通过后按已授权 main 提交推送。并行 PE 原生观察与本片独立，不取消 run 或把本片提交当作原生结果。

主要风险是文案或测试暗中改变 enabled 语义。通过精确三文件允许清单、逐字按钮/API不变、旧 HTTP 和 custom executor 测试及限额断言验证。CLI 仍是现有中文输出，本片的双语要求针对工作台 UI，不新增全 CLI 国际化。

研究输入：[工作台验证计划接线只读预研](2026-10-09-r3-workbench-verification-research.md)；本片独立并行研究另核固定官方来源，采纳“配置不等于执行通过”，不复制上游实现。许可、固定链接和新增观察结果在实现前或阶段验收前由 root 汇入持续对照。

当前状态：设计自检完成，尚未独立双审或写源码。范围、精确文字、旧兼容及验收项无占位；不报告 R3 或总体完成。
