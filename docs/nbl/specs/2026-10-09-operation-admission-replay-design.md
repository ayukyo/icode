# G1：动作 admission 与旧回执重放的最小修复设计

日期：2026-10-09，Asia/Shanghai。状态：设计候选，作者静态自审后交 root 独立审；尚未实施或运行验收。

本设计仅修主工程的执行许可包装：旧 operation start 回执可以证明记录已存在，不能授权再次执行载荷。它不证明此前载荷已执行、完成或结果未知。
本片只新增本文；不写实施计划，不改 production、tests、vendor、permissions 或 Native readiness，不运行 CP、runtime import、测试、模型、编译或 Git 写操作。
本文被 `docs/` ignore，且不属于当前 session-Git 的 Git14 路径发布范围；root 另行决定后续阶段。

## 1. 问题、现有实现与证据边界

三问已确认：真实缺口在共用包装；已有 `OperationRecorder` 与 `can_execute` 可复用；实际调用链涉及普通工具和工程 gate 两个生产消费者。
基线 main 为 `8d53670192e3e2cbfebaa0300d697fb3036308be`，固定 vendor 为 `1693651c1bd7daad3272eb054f0f81d6f254d08d`。
本设计读的是 session-Git 修复中的当前源码，runner 摘要见末节；这不是把尚未发布源当作已发布 main。

[root 实际诊断](2026-10-09-linux-bridge-blockers.md)记录：首次真实 CP admission 允许执行；新 recorder 重置计数后，同 request 返回 `already_applied=True`、同一仍 open 的 attempt，但包装的 `can_execute=True`。
原 recorder 下一 occurrence 实际返回 returncode=1、中文 error 和 `gate_id=ambiguous_side_effect`，执行已被拒绝，但包装的 `ambiguous=False`。
该诊断载荷、工程 gate、模型与 Native 执行均为 0；临时工单已清，没有保留原始事件包。它证明 admission 缺口，不能声称已真实重复执行载荷。

本作者重新实读决定性源码：vendor 精确 matcher 比较 request/event type/payload；`cmd_operation` 的精确 prior 分支返回旧回执，先于同名 open 动作拒绝。
首次 start 成功输出没有 `already_applied`；因此把该字段改成必填会拒绝固定 vendor 的合法首次响应。
工程 gate 当前另查 `open_operations`，已完成回执会被旧二次门拒绝；仍 open 的同身份回执则不能靠该投影证明是新 admission。
公共 `resume_contract_step` 已在模型前拒绝 open operations / 已有工程动作；其信用不能代替内部 gate 或普通 `_invoke` 的许可检查。

## 2. 方案比较与上游复用

| 方案 | 决定 | 现有实现、收益与成本 | 许可、安全、兼容及验收 |
| --- | --- | --- | --- |
| 共用 wrapper 传递 marker，`can_execute` 拒绝旧回执 | 采纳 | 复用 recorder 和两个许可消费点；一个边界适配，少量字段与分支 | 无上游代码复制、新依赖或权限；保留旧构造；真实 CP 与两消费点零新增载荷验证 |
| 两消费者分别查 trace / metadata 决定是否执行 | 不适配本片 | 重复接线、存在观察竞态；open 身份不能证明新 admission | trace 只保留已有工程身份重核，不能反授许可；不新增账本读取旁路 |
| 业务 reconcile、缓存结果或重编号后执行 | 暂缓 | 需要载荷结果合同、外部核对和更广恢复设计 | 任意工程命令没有统一幂等保证；换 request/scope/class 不能绕过 open 动作；另立设计验收 |

复用今天[持续对照首条](../../agent-landscape-live.md)的独立研究：LangGraph `bfcfea554ed5c7f7be562cebf8825e911b493ab1`、官方 docs `be3028f3b446d7cfc63b434faf4e594689129251`，两根许可由研究者全文核为 MIT。
来源为实际固定源码与官方文档：[已有结果复用](https://github.com/langchain-ai/langgraph/blob/bfcfea554ed5c7f7be562cebf8825e911b493ab1/libs/langgraph/langgraph/pregel/_runner.py#L747-L764)、[Functional API](https://github.com/langchain-ai/docs/blob/be3028f3b446d7cfc63b434faf4e594689129251/src/oss/langgraph/functional-api.mdx#L790-L810)。
采纳机制是区分新 admission、旧 receipt、未知结果；收益是避免把持久记录的幂等误当载荷的执行幂等，成本是包装兼容与负控。
未完成 task 可自动重跑的上游规则不适配任意工程载荷；不承诺 exactly-once，不复制实现。本作者仅复核本地来源记录，未在本片联网或全文重读上游 LICENSE，未重查完整 20 项名单。

## 3. boundary 与 contract_matrix

生产者：固定 vendor `cmd_operation`；传输：`ControlPlane.operation_start` 的原 `ControlResult`；适配：`OperationRecorder.start`；消费者：`AgentLoop._invoke`、`runner._contract_engineering_gate`。
持久真源仍是 CP 事件链；request 由 ticket/action/occurrence 派生，operation attempt 与 step attempt 是不同身份。
`already_applied` 为 JSON bool 或合法首次缺字段，无单位；表示该 start 记录已存在，既不是 payload completion，也不是 payload 可重跑标志。
本片不改 CP schema/ABI、finish 的结果合同或 `ControlResult.ok`。

| 维度 | 生产者合同 | 消费者合同 | 当前适配 / 拟适配 | 证据 | 匹配状态 |
| --- | --- | --- | --- | --- | --- |
| 首次成功 / 默认 | returncode=0、ok=True、attempt；marker 缺失 | 新 admission 才可进入载荷 | 缺字段归一 False，保留现有 ok/attempt 判断 | vendor 4896–4901 | 保持兼容，待验 |
| 精确重放 / 时间意义 | ok=True、already_applied=True、旧 attempt/event | 旧回执不能再执行 | 当前丢字段；拟保留 True，ok 不改，can_execute=False | vendor 4879–4885；operations 75–87 | 缺口 supported |
| 显式 False | bool False | 满足其余门才可执行 | 保留 False；不增必填 phase/class/event_id | 协议兼容向量，非固定 vendor 实吐观察 | 待验 |
| 非 bool marker | 0、1、字符串、null、数组或对象 | 非法协议不能授执行许可 | type(value) 必须是 bool；非法令 ok=False，marker 归一 False | 拟协议 double | 未观察，待验 |
| 同名未决 / 错误 | 中文 error + gate_id=ambiguous_side_effect，非零退出 | 拒绝且保留未知动作 | 补 gate_id 精确识别，保留原布尔及英文 error fallback | root 真实诊断；vendor 4889–4895 | 字段缺口 supported |
| request / scope / occurrence | 精确身份与 payload matcher | 不换键绕过未决 | 原两次 `_next_occurrence`、scope/action/name 派生全部保留 | operations 63–74；matcher 1866–1893 | 本片无变更 |
| finish / recovery | 显式终结与 CP 真源恢复 | 未知必须先核对 | 不自动 finish/cache/reconcile；原 public resume 门保留 | recovery 全文；runner 2655–2689 | 源合同已核，运行未验 |

### classification、skill_routes、gaps 与 verdict

| 问题 | 主分类 / 竞争分类 | 原因、严重度与状态 | 修复 owner / 独立证据 |
| --- | --- | --- | --- |
| 旧 start 记录被当新许可 | 跨层协议时间语义 / 业务执行幂等 | marker 在 wrapper 丢失；高，supported；未证明重复 payload | operations；真实两消费点计数和持久事件 |
| 中文未决错误未标 ambiguous | 结构化错误适配 / 文本翻译 | 只查布尔和英文正文；中，supported；当前仍拒绝 | operations；真实 gate_id 与兼容 fallback |
| 重启后旧 receipt 的行为 | 状态生命周期 / 新 admission | 内存计数消失、事件持久；高，unobserved | 同 wrapper；真实子进程 restart 负控 |

| 问题 | Skill | 触发输入 | 输出与 fallback | 路由状态 |
| --- | --- | --- | --- | --- |
| marker 与 gate_id 跨边界 | cross-layer-contract-audit | raw CP、wrapper、两个实际消费者 | 本节契约矩阵；文本核对不足即保持未验 | 已全文读，设计适用 |
| fresh recorder / restart / 未知恢复 | state-lifecycle-replay-audit | request/attempt、事件、载荷 marker | 下述六维与 owner 矩阵；不可注入项标 unobserved | 已全文读，未执行生命周期 |
| 两入口的载荷前门 | agent-workflow-step-gate | 原 start 结果与实际入口顺序 | 在载荷前判断原 marker；不从执行后状态反授许可 | 已全文读，设计适用 |

没有传感器、总线、MCU 或闭源 SDK 参与本片，硬件 fault adapter 不适用；不引入对应窄技能或 Java/MySQL controller/DDL 框架。
缺口是原始 admission 事件包、真实 consumer marker、真 process restart 与故障注入结果；影响是尚不能授修复通过或全生命周期信用。
跨层结论：两个已确认缺口可由主工程 wrapper 修复；非法值和重启仅为待验合同，不称固定 vendor 曾返回 malformed 值；其余 CP 与恢复机制保留各自证据边界。

## 4. 最小接口与执行入口设计

在 `StartedOperation` 原全部字段之后（包括 `detail`）追加 `already_applied: bool = False`。
旧 positional 参数位置、旧 keyword 构造及省略新字段的用法不变；不重新设计 attempt 类型。
`can_execute` 保持原 ok、非 ambiguous、非空 attempt 条件，并追加 `self.already_applied is False`；直接构造时的 0、None 等非 bool 同样不能授许可。

`OperationRecorder.start` 按字段是否存在分支：缺失使用 False；存在时仅接受 `type(value) is bool`，不用 truthiness 或 `isinstance(value, int)`。
exact True 保留 CP 的 ok=True、旧 attempt 与 replay 事实，can_execute=False；不伪造 ambiguous=True。
非法值归一 marker=False 且 ok=False；detail 使用固定说明 `operation_start_protocol_invalid: already_applied 必须是 bool`，不回显非法正文。
原 `ControlResult` 在测试 fixture 和断言中保留，分别核原值与归一值；不为 StartedOperation 增加 raw 字段或重写 CP 原响应。
attempt 现有转换、detail 原上限及 transport/ok 失败条件继续生效，不因 marker=True 掩盖其它失败。

ambiguous 判断加入 `res.data.get("gate_id") == "ambiguous_side_effect"`，与既有布尔字段及 error 英文 fallback 取或；不改变其它 gate_id 类别。
两次 `_next_occurrence` 递增、request/scope/operation name、输入摘要、账本和 finish 请求保持原样；本片不是修计数语义。

工程入口在现有 `not started.can_execute` 早门内，用 `getattr(started, "already_applied", False) is True` 分类：精确 True 使用旧 `engineering_operation_replay_refused`；其余用旧 `engineering_operation_start_unconfirmed`。
这保持 completed replay 既有错误合同，同时在 open replay 上更早拒绝；后续 CP open identity 重核继续保留。
成功路径 double 只需原有 can_execute/attempt/detail，不新增 mandatory 属性；缺 marker 的旧成功 double 不被强制升级。

普通 `_invoke` 继续共用 can_execute 拒绝并在 `registry.invoke` 前返回。
精确 True 的中文前缀 / note 明确为“此前动作的回执不能用于再次执行”；旧 metadata error 和事件名可以保持兼容，但不能把该拒绝写成已完成动作的结果未知。
原 ambiguous 与普通失败分支保持原文案和逻辑；拒绝不调用 finish，不发 tool_start 或执行 handler，不缓存/复用 payload 结果。

### 多入口的载荷前检查

| 入口 | 原事实读取 | 初始化后的状态 | 门位置与预期 | 证明边界 |
| --- | --- | --- | --- | --- |
| 普通非 read_only 工具 | 此次 CP start 的 marker | inv 尚未 approved，handler 未调用 | can_execute 后才 registry.invoke；旧回执拒绝 | 实际 handler 计数待验 |
| read_only 工具 | 原来不创建 operation | 保留原只读流程 | 无本门新增 | 兼容回归待验 |
| code/deepcheck 工程 gate | 同次 StartedOperation | 尚未 snapshot/host plan | 早门拒绝；原 open trace 再核 | controlled_dispatch 不调用待验 |
| 公共 resume | CP trace / checkpoint 原身份 | 尚未 `_run_agent` | 原未知 / completed 工程动作拒绝保持 | 不能外推内部 gate 已安全 |
| fresh recorder / completed rerun | 新内存计数，旧 CP 回执 True | 不视为 fresh admission | 两消费者拒绝，原错误类别保持 | 不靠改变 request 取成功 |

## 5. scope、state_inventory 与 transition_matrix

scope：operation.start → 载荷 → 显式 finish；成功终态为原 attempt 已明确 finish，未知失败终态仍 open 并阻断恢复。
可复用基线是旧动作经原授权路径核对终结后，新 occurrence 的新 admission；同 request 的旧 receipt 永远不是该基线。
进程内 recorder 计数短寿命，CP 事件与外部文件效果可持久；载荷 marker 只用于 owned 测试，不外推任意工程效果可回滚。

| 状态 / 产物 | 生命周期 | Owner | 写 / 读 | 清除 / 恢复来源 | 不变量 |
| --- | --- | --- | --- | --- | --- |
| `_counters` / scope | recorder 实例 | OperationRecorder | 原 start 递增 / request 派生 | 新实例重置；不从账本恢复 | 重置不授予旧 attempt 再执行权 |
| request / operation attempt | 逻辑轮次、CP 持久 | CP | 原派生 / matcher、finish、trace | 不删；从事件链读取 | step attempt 与 operation attempt 不混用 |
| already_applied / can_execute | 单次返回 | wrapper | start 归一 / 两消费者 | 返回对象自然释放 | 仅严格 False 能通过新增条件 |
| open operation | 直到明确终结 | CP | start / gate、Recoverer | 仅原显式 finish；trace 恢复 | 异常、旧 replay 拒绝不伪闭合 |
| payload marker / 外部效果 | 测试 fixture / 业务持久 | handler / 实际业务 | 真实 handler / 验收计数 | fixture 清理 / 不自动业务回滚 | 拒绝后计数不增长 |
| checkpoint / 审核证据 | 原步骤合同 | 原 runner | 原路径 / public resume | 原 clear 条件 / CP 优先 | marker 不替代质量、身份或恢复门 |

| From | 事件 / guard | 轮次校验 | 副作用 | 补偿 | To | 证据 / 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 无 start | 合法首次、marker 缺失/False | 原 request/attempt | 可执行一次 payload | 原 finish | 明确结果或 open | 源合同；修后待验 |
| open / completed | 同 request 精确 replay=True | matcher 返回旧 attempt | 新 payload 0 次 | 无自动补偿/finish | 原状态保留 | admission 诊断；consumer 待验 |
| open | 新 occurrence 同名副作用 | 原 CP 同名检查 | 无 payload | 保留原动作待核对 | ambiguous 拒绝 | root 已观察；字段修后待验 |
| confirmed start | 载荷前后异常或 finish 失败 | 原 operation attempt | 可能 0 或 1，不能猜 | 原显式核对路径 | open / 恢复拒绝 | 既有测试源码；本片未跑 |
| 明确 finished | 新 occurrence 合法 start | 原派生新身份 | 可执行新业务轮次 | 原 finish | 新轮结果 | 与 replay 分开验收 |
| 任意响应 | marker 存在但类型非法 | 保留 raw fixture | 无 payload | 无自动 finish | ok=False / 不许可 | 协议 double 待验 |

## 6. replay_matrix：六维逐项验收边界

| 维度 | 初始状态 / 刺激 | 预期状态与效果 | 现观察 | 清理 | 状态 |
| --- | --- | --- | --- | --- | --- |
| immediate | first start 后；fresh recorder 同 key | first 许可；replay 旧 attempt、零新增 payload，open 不变 | root admission-only 当前 replay 错误许可；payload0，consumer 未跑 | owned fixture，不补未知 finish | 缺口 fail；修后 unobserved |
| converged | replay 拒绝后，不发新业务请求，读 durable trace | 无后台重执行、无自动 finish；原 open 持续，marker 不增长 | 未观察等待窗口；源码无本片自动收束 | 观察结束才 fixture 清理 | unobserved |
| restart | 新真实 Python 子进程重启应用并访问同一 durable CP | 内存计数重置仍拒绝旧 key；外部 marker 和 open 保留 | 未运行；新 recorder 对象不是 process restart | 子进程退出、owned 根清理 | unobserved |
| replay | 原 open 分别 marker0/已执行未finish marker1；completed 同 key | 两 consumer 均不增 marker；completed 工程旧 replay_refused | 仅 admission-only；旧 completed test 源码已读，未运行 | completed 必须原明确 finish；open 不伪闭合 | consumer unobserved |
| rollback | start 后中断、拒绝或取消，含 finish 拒绝 | 本修复不承诺撤销外部效果；不盲重跑或自动 finish，保留需核对状态 | 没有强制 rollback / cancellation 运行证据 | 测试 marker 仅 owned fixture 清理 | unobserved，业务补偿暂缓 |
| failure | malformed marker、start 异常、handler 异常、finish False | 非法不许可；已 start 的异常仍 open；public resume 在 model/payload 前拒绝 | root 中文 gate_id 真实拒绝；其余仅源码合同 | 禁止以补 finish 取绿 | 部分观察；修后 unobserved |

leaks_and_conflicts：第一轮 open attempt 的旧回执可污染 fresh recorder 第二轮许可；最小 reproducer 是同 ticket/scope/name/input、fresh recorder、计数重置。
影响是可能重复任意副作用；修复责任在共用 wrapper 和载荷前门。当前仅证明许可泄漏，不宣称实际重复效果或恢复泄漏已全面证实。
生命周期 verdict 为 `unobserved`：没有修后六维通过证据；下一判别测试是两消费者真实 marker 负控，其后单独做 durable CP 的真实 process restart。

## 7. 验收合同与最小职责边界

验收均留给后续唯一 writer / root 串行执行；本作者未运行。测试必须使用 owned `.icode_output`、固定真实 SKILL、真实 `OperationRecorder` 与 CP，不把协议 double 当 CP 运行观察。

| 验收组 | 必须观察的输出 / 调用数 | 信用范围 |
| --- | --- | --- |
| 基础构造与协议 | missing/False/default/旧 positional+keyword 可用；True 禁止；直接非 bool 不许可；raw malformed `[0, 1, 'false', None, [], {}]` 各 type fail、ok=False | 包装协议，不声称 vendor 实吐非法值 |
| 真实 CP first / open replay | first 原响应无 marker且许可；fresh 同 key 原 True、同 attempt；marker0 和 marker1 两情形重放后均不增长、open 仍存在 | 新 admission 与旧 receipt，不是 exactly-once |
| 普通 loop | 实际本地 handler marker 或 wrapped real handler 计数；旧回执在 invoke 前拒绝，finish 不调用；中文表述准确；只读与旧 ambiguous 回归 | offline backend，非模型/Native |
| 工程 gate | replay 时 `_controlled_dispatch` 入口不调用；completed 原明确 finish 后同 key 仍旧 replay_refused；新 occurrence 在 finish 后合法 | 真实 CP + broker double，非原生执行 |
| occurrence / scope | 原 open 同名下一 occurrence 原中文error/gate_id，包装 ambiguous=True；scope 派生与两次计数原样 | 不换键绕过；原精准 double 调用回归 |
| failure / public resume | start 后异常、finish False 保留 open且无自动 finish；真实 public resume 在模型/载荷前拒绝 unknown；既有 completed/stale 拒绝不退化 | 原恢复前置；非全生命周期通过 |
| restart / CI | 同 durable CP 的真实子进程重启负控；选择新 test module和必要契约方法恰好一次，无 loader error或新增 skip 掩盖 | process restart独立验；CI选择不是平台隔离证明 |

后续实现最小职责建议约七源：`src/icode/operations.py`（字段/归一/许可）、`src/icode/loop.py`（旧回执拒绝文案）、`src/icode/runner.py`（早门错误分类）、新增 `tests/test_operation_admission.py`（协议、真实 CP、loop、restart）、`tests/test_contract_engineering.py`（工程/open/completed/failure 回归）、`scripts/run_workspace_ci.py`（有界选择）、`tests/test_run_workspace_ci.py`（恰好一次/无静态 skip 守护）。
这是职责与验收依赖说明，不是实施计划；不添加框架或预先固定最终测试方法数量。原 loop/recovery/CLI 精准测试作为关联回归，只有必要时才由实施阶段说明额外测试源改动。
阶段依赖为：本文独立 SPEC→不同 QUALITY 通过 → root 决定实施计划/串行 writer → 修复与上述负控 → 冻结与独立审 → root 软件/发布/实际平台门。
session-Git 当前冻结验证与本片设计互不改写；vendor worklist 与 Gitpipe 新授权仍 pending，不属于 G1 wrapper 修复，也不据此阻断已授权主工程最小片。
OS / installed 包、真实模型、Native 资源通道与 R2/R3 全体验收分别保留；不改 Native false、Git identity、baseline 或 CP protected input。

## 8. 作者静态审查与来源冻结

已实际全文读：根 AGENTS；brainstorming147、doc-contract62、执行门233、跨层111、生命周期113；本机 checker 全文193行（父任务称210，本次以实际文件为准）。
决定性读边界：operations1–106全文，recovery1–297全文；control1–82/272–309；loop164–266完整调用路径；runner1714–1848完整工程 gate/2570–2767完整公共resume。
另实读 vendor1866–1893 matcher、4812–4986 operation；工程 tests1–118/440–509/659–688，loop1–125、recovery327–396，CI选择137–175及相关 selection guard；只文本读，没有导入运行。
当前 SHA-256：operations `2e72103a85e24b940f6a3147f0a92f186cf2e8580e15abd07951b984437687a0`；loop `1b3d9ddb17deabfe460c0ef0fa03a3d3f10a6307e4a3dd2b9d15a1af5cac3746`。
runner `0bc0d5e0711e88e9aee35f3a693430eb529a6d597388a32c3ff0f2defe596a83`；vendor control `0b7e2577844f135269bdcc78bee195ad974a350f20792af7de46b2bdae76564c`。后续实施前重核实际冻结源，不用这些摘要声称运行 provenance。

作者 selfSPEC 检查：字段顺序/严格 bool/缺失兼容、两个消费者、旧错误合同、六维未验状态、授权及当前 Git 发布范围一致；C0/I0/M0，仅作者自审，不代替独立 SPEC。
作者 selfQUALITY 检查：复用点明确、错误不误称 completion unknown、raw/normalized 分开、替代方案与成本明确、无多余框架或虚构 API；C0/I0/M0，仅作者自审，不代替不同独立 QUALITY。
文档 checker 两轮只选本文；链接/字符/表格/围栏由实际静态检查记录，不授生产测试信用。

【架构级自检报告】范围仅本文静态设计：

- ✅ 语法/结构：Markdown 与链接结构检查；没有生产编译声明。
- ✅ 依赖/调用链：CP→wrapper→两个载荷前门、公共恢复前置实读完整。
- ✅ 逻辑/边界：strict bool、缺字段、旧构造、open/completed/new occurrence 区分清楚。
- ✅ 异常处理：设计覆盖非法字段、异常、finish失败；运行全覆盖尚未验证。
- ✅ 关联模块：七源职责与原契约回归明确；未改其它文件。
- ✅ 兼容安全：原构造/精确double/错误分类保留，无权限/Native/账本改动。
- ⚠️ 可运行性：本文可检查；实现、测试、生命周期及平台门均未运行，不能报告生产100%。

作者完成文档自审后 DONE STOP；root 独立审查与后续阶段另行负责。

## root实施状态（2026-10-09）

以上为原作者186行设计快照，其SHA为 `1b2c718d1288c142f46c49fef0537b87a9791f5bbceec4ce1d0671a2af6106a8`；当前新增此实施记录后不再是整文件摘要。获准设计、计划、四任务及全局独立双审均通过，七源最小修复已经实施。

root定点141项、20轮320次、DEFAULT609项均零失败/错误/跳过；原完整入口一次运行2469项，2410通过、59跳过、零失败/错误，三道守卫通过。单进程编译及治理/site/排期检查通过。真实CP、两消费者、持久CP的两个child、有限观察和失败路径详见[实际实施履历](../plans/2026-10-09-operation-admission-replay.md)。旧构造、错误分类和恢复合同保持，未改变vendor或原生准入。

当前已通过的是本机G1软件验收，文档收尾与main发布待。原作者“尚未实施”等是历史状态；工程host/backend double、59skip、业务回滚、installed、真实模型及各平台原生门保持各自未验边界，R2/R3整体未完成。
