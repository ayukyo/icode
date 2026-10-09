# Windows 构建上下文失败分类设计

日期2026-10-09；源码基线main `d365e6f15d2d1a223ec60ba18310647c338f4eba`，parent118a262，vendor1693651。本稿未实施、未运行新增测试。上一PE基础片已通过本机软件守卫并推送；新SHA原生观察仍并行进行，不把上一片或研究当本片验收。

## 真实问题、现有实现与调用链

118a x64/Python3.11在构建产出后只出现`windows_build_context_probe_failed`，无法区分文件/JSON/XML/选择、单次MSBuild查询、返回输出或工具目录拒绝。约50.638秒是两条外部日志的跨度，不是query实测，也不证明timeout。原日志与固定源码、研究取舍见[调查](2026-10-09-windows-build-context-rejection-research.md)。新d365窗口的成功或失败须另记。

已存在严格metadata校验、一次property-only query、30秒/16KiB预算及Windows挂起→Job→恢复/有界清理，不重写。调用链是CI workflow→本脚本`main`→`probe`→现有bounded runner。只有`scripts/probe_windows_build_context.py`、`tests/test_windows_build_context.py`允许源码改动；不改src/runner/native/capture/工作流/DEFAULT/vendor/依赖/权限或生产准入。已有DEFAULT选择完整portable class及配对no-skip守卫继续复用，host CMake class不扩大选择。

## 两种方案与阶段决策

A：main每次新建私有诊断对象，probe增加默认None的私有keyword-only参数；固定阶段只写该对象，分类只看异常类型。收益是显式每次调用隔离，旧两参数调用兼容；成本是内部可选参数和具名正负控。

B：ContextVar保存观察状态以维持main的两参数调用形状，但增加隐式状态、上下文清理与并发/嵌套合同；本片没有需要维持替换main中probe自定义lambda ABI的消费者，暂缓。包装/重建异常不适配，会改变原类或identity。

root按用户已委托的阶段决策和持续开发权限选择A；不是新增A/B答复、不要求用户重发常规阶段命令。设计先自审→新鲜独立SPEC→不同QUALITY，再明确计划→TDD→实施双审→root完整守卫；不因自治跳过安全或验证门。用户如提出不同约束即调整，本设计不扩新的执行/特权权限。

## 私有观察接口与故障边界

`probe(build_directory, architecture, *, _diagnostic=None)`保留原两个位置参数和返回dict/异常合同。旧两参数调用不创建观察对象、不输出日志；新增参数只由main使用，不是CLI flag或生产API。每次main单独创建`_ProbeDiagnostic`，只持有当前stage字符串，不保存路径、原文本、异常、结果、历史或全局可变状态。

`_ProbeDiagnostic`初始stage为unavailable。`_set_diagnostic_stage`在对应操作前尽力写入固定标签；None或非本类对象不读取/调用其属性。类型必须精确str并属闭集；未知标签变unavailable。观察写入的普通异常使该次标签不可用而不阻止原操作，不能残留前一个阶段冒称当前；正常后续阶段可重新标记当前位置。取最终stage失败或非法值只用unavailable。

诊断factory、标记、分类/序列化/输出中的普通故障不把原probe成功变失败、也不把原失败变成功；保护仅围绕诊断代码，不catch整个业务流程后返回假结果。MemoryError明确不吞；KeyboardInterrupt/SystemExit自然传播。原probe的TypeError/AssertionError等编程错误仍按原main合同传播，不输出成功或失败诊断。

main调用probe即使诊断factory普通失败也执行一次（以None继续）；observer故障不得触发第二次probe/query。marker不得增加文件lstat/open、runner调用、时钟/线程/进程查询、重试、等待或预算。输入校验、求值与现有副作用顺序保持；原嵌套读/解析表达式仅拆为同顺序各一次临时值，以在两操作间标记。

## 十二项stage闭集

| Stage | 开始标记位置及包含的操作 |
| --- | --- |
| input | 原平台/arch与绝对且存在的目录校验前 |
| context_read | 固定context的原_read_regular前，仅读原文件一次 |
| context_validate | 读完context后，原_json解码/解析及schema/字符串/generator/platform校验前 |
| msbuild_identity | 原显式MSBuild basename及绝对regular路径校验前 |
| project_read | 固定vcxproj原_read_regular前，仅读原文件一次 |
| project_validate | 原UTF-8/XML/选择解析及SDK/toolset与context比较前 |
| query | 已构造原argv后、原environment快照及唯一bounded runner调用前；不证明子进程已启动 |
| query_result | 原tuple长度、code/stdout/stderr类型/限额/非空/退出校验前 |
| output_json | 原stdout严格_json解码/解析前 |
| properties_validate | 原输出root/Properties字段/字符串/配置平台SDK工具链匹配校验前 |
| tool_directory | 原三个绝对工具目录逐项校验前，保持原顺序与次数 |
| unavailable | 初始或观察失败/非法时点，没有细阶段信用 |

无completed、重试序号、PID、实际值或时间字段。成功不输出观察状态。query+output_capture只定位最外层捕获拒绝，不区分Job绑定、EOF、超时清理或root退出；不遍历cause推根因。

## 十项failure_kind闭集及优先级

仅按已知异常类型依次匹配（具体类型先于其基类），不读取str/repr/args/cmd/output/stderr/returncode/cause/context或自定义详情：

1. subprocess.TimeoutExpired→timeout。
2. VerificationOutputCaptureError→output_capture。
3. VerificationOutputLimitError→output_limit。
4. UnicodeError→unicode_error。
5. ET.ParseError→xml_parse。
6. OSError→os_error。
7. ValueError→validation_value。
8. RuntimeError（含RecursionError）→validation_runtime。
9. subprocess.SubprocessError（含CalledProcessError，但不覆盖第1项）→subprocess_error。
10. 诊断分类不可用/非法→unavailable。

两个VerificationOutput专用类仅从已有runner导入以复用类型，不改其实现或读取payload。main原捕获tuple不增删；bare MemoryError、TypeError、AssertionError、KeyboardInterrupt、SystemExit仍不落入新业务捕获。分类器不作为独立异常恢复/重试策略。

## 输出与兼容

成功仍是原status和receipt两行，字符、字段、顺序、ensure_ascii和退出0逐字不变；不额外打印诊断。原两个CLI参数/choices/allow_abbrev=False保持；argparse错误在调用probe之前按原退出2，不创建执行或失败回执。

既有受捕获probe失败先按原方式打印`::error::windows_build_context_probe_failed`，仍退出1；随后尽力尝试至多一次输出`windows-build-context rejection=`前缀加compact ASCII JSON及一个LF。四个字段固定为schema_version整数1、stage、failure_kind、production_authority字面none；标签必须精确str且属上述闭集，无其它keys/路径/值/文本。整行含前缀和LF不超过256 ASCII bytes；非法/超限跳过诊断，不截断、不补空对象、不重试输出。

准备完整合法行后才调用输出；普通序列化/输出故障不遮蔽原泛错误与exit1。损坏输出流可能物理截断，不能承诺其无碎片，也不授此时回执信用；仅成功完整发出的行可被解析。原泛错误自身写失败仍按原行为传播，不把它包入新吞错范围。成功stdout原处理不改变。

## 可验证验收

- 旧两参数成功dict与原受捕获/未捕获异常行为、runner异常identity保持；实际runner调用argv/cwd/env/timeout30/output16384/一次/无fallback逐项核。
- 用现有真实临时context JSON/project XML/properties bytes构造各阶段合法前缀后的单个拒绝，metadata语义不mock为成功；Windows路径lstat/runner仍仅portable输运fixture，不称native。query前拒绝0次、query及之后1次。
- 十二标签（十一具名操作+unavailable）与十类别逐一精确断言；UnicodeError/ValueError、capture/limit与RuntimeError、TimeoutExpired/SubprocessError优先级，RecursionError明确归类。
- 两arch成功golden原两行逐字保持且无rejection；旧捕获tuple失败golden保留原首行/exit1再唯一闭JSON。两个CLI flag及错误退出2/noprobe保持。
- 异常str/repr poison、秘密marker缺席、未知/非精确标签、固定字段及256-byte完整ASCII/LF、诊断factory/marker/取值/序列化/输出普通故障、fatal异常传播、两实例无串扰、无额外query或原结果修改均具名正负控。
- 新方法在已有portable class内无skip，现有DEFAULT/配对守卫自动完整选择；定点含probe/capture/bootstrap/CI选择/runner相关合同，再20轮关键路径、DEFAULT、原完整三道preflight串行；compile-j1、治理/site/landscape、文档两轮、secrets/submodule与exact source/doc scope通过后按已授权main提交推送。
- 独立新SHA四格原日志/失败回执及签名安装artifact各绑定，成功/失败/skip/unknown分开。诊断有用不等于故障修复；若未重现仅记本窗口，不沿用118a或d365给新SHA信用。

## 借鉴、许可与边界

复用[固定Codex错误类别研究](2026-10-09-windows-build-context-rejection-research.md)：采纳payload-free语义类别与敏感哨兵正负控，暂缓生产runner细遥测；不适配其to_string公开message、Windows错误字符串/path/实际code指标。独立研究及root已核固定2c3156a源码与Apache2许可，不称当日HEAD或同款stage/kind实现。没有复制代码、新依赖或权限。

收益是下一CI拒绝可缩小层位且不公开正文；成本为阶段/类型矩阵、兼容与普通诊断故障保护、新SHA观察。原泛错误与限额不放宽，reader/capture三个false不改，不授完整PE/实际加载/UAC/标准用户网络/额度/模型或R2/R3整体通过。

root已全文读当前probe183行、tests403行及相关runner错误/Windows执行清理，完成结构化112–114需求分解→方案→风险记录。草稿自审核两源码范围、12stage/10kind/4fields、继承优先级、MemoryError界限、query0/1次与损坏流信用；无未定义enum/占位或整体完成声明。下一门为新鲜独立设计SPEC→不同QUALITY；没有本片新增代码/测试/发布结论。
