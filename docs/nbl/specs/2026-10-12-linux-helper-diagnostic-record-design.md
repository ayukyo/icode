# Linux 安装包故障记录的有限补充

状态：六字段软件实现、定向回归、独立 SOURCE 双审与原完整守护已通过；精确发布及新 SHA 原生安装包观察仍待。用户已委托常规方案选择和持续开发；本片不增加权限、依赖、安装步骤或安全准入能力。root sequential-thinking 182–184 已核需求、复用和风险，185–187在SOURCE开始时再次核对。

## 问题与证据边界

main `74163aa59affa406bed230679ac29ec638c0c979` 的 ubuntu22.04-arm job114634914991安装probe exit1。原84记录中context/scope/timeout返回resource_channel_failed，固定脚本要求timeout。stderr只发布2659bytes；现记录缺exit_code、payload_started、ready和resource receipt，不能区分启动早退、实际超时或资源通道终态。原身份/回收成功不替代失败负控。

## 选择

直接打印stderr可能公开路径/命令，不采纳；原样重跑无法补证据，不作为修复；推荐在现有有限JSON投影增加字段。复用原result、固定测试ready文件及resource_receipt，不读取新敏感内容，不改执行逻辑、超时、quota、错误优先级或任何断言。

## 合同

只增加故障record的六个flat字段：

| 字段 | producer事实 | publisher允许值 |
| --- | --- | --- |
| exit_code | result.exit_code，result不存在为None | exact int，-255至255；或None，bool不算int |
| payload_started | result.payload_started或None | exact bool或None |
| payload_ready | 已有workspace固定ready文件exists() | exact bool |
| resource_configured | resource_receipt configured或None | exact bool或None |
| resource_channel_status | resource_receipt channel_status或None | complete/incomplete/None |
| resource_terminal | resource_receipt terminal或None | preexec_failed/finished/cleanup_failed/None |

publisher继续仅输出白名单，未知类型/值字段删除，不改值或推导成功；缺字段旧record仍兼容。None明确未观察，不是false或通过。未知exit不得公开原数值。record投影不能认证payload、资源回收或timeout根因。

只改 `scripts/probe_installed_linux_helper_object.py` 的原故障record生产处与 `scripts/run_native_wheel_ci.py` 原发布器；新增便携测试精确执行实际producer AST与发布器，不能只检查源码字符串或复制待测表达式。生产broker、native helper、workflow、原测试断言和vendor保持不变。

## 验收及次序

新测试先行：旧producer实际AST缺字段与旧publisher丢字段必须出现目标assertFAIL，而非缺API错误。随后最小配对GREEN；边界含bool-as-int、数值范围、None、缺receipt/缺result、非法enum及隐私sentinel。既有publisher/helper相关测试兼容，独立双审、原完整preflight、两次文档扫描和精确stage通过再main发布。

本片SOURCE必须在当前Windowsfinite阶段实际发布后串行开始，不与其冻结源码交叠。新SHA四Linux安装包原日志另验，不靠重跑覆盖原失败。若有限字段仍无法定位，保留unknown并继续只读分析，不放宽timeout预期或宣布修复。

研究复用02:14–02:17独立Windows/Codex有限错误研究及本工程现有白名单投影模式，仅采纳诊断/准入分账；不复制上游代码、扩大授权或声称20项目/HEAD刷新。开始该SOURCE阶段还须开启相关独立只读研究。

2026-10-12 02:45 SOURCE开始时已开启独立只读研究；02:45:54–02:46:29实际核固定Codex `27065a91ccbf5ba8532844be3777fcf83b77820d` error.rs/exec.rs及Apache-2.0 LICENSE。采纳payload-free类别与wait/expiry分账，复用现有白名单；不适配含stdout/stderr的Display或timeout重写exit124解释本地故障，暂缓新遥测与策略调整。无源码复制、新依赖/权限。对应具体链接与取舍记录见[持续对照](../../agent-landscape-live.md)。作者/root实际两有效目标RED后由不同fresh作者实现GREEN；root新8与旧41均0F/E/skip，两脚本各+9行，原断言/执行/收尾保持。不宣称原生故障已修复。

【架构级自检报告】（设计，非运行）

- 语法/编译：字段与现有接口静态核对；未执行实现。
- 依赖/调用链：producer/publisher配对，不新增生产执行入口。
- 逻辑/边界：类型、None、有限枚举与兼容明确。
- 异常处理：保持原执行/错误合同，不公开stderr。
- 关联模块：实际AST测试和既有发布器回归必须同步。
- 兼容安全：旧记录兼容，无新权限/依赖，未知不授通过。
- 可运行性：待实施与实际安装包验收，不报告运行通过。

以上为计划时静态历史记录。SOURCE实际已由作者/root有效RED→GREEN，fresh SPEC→不同QUALITY均C0/I0/M0；root新8与旧41无skip通过。原完整preflight唯一session60796于2026-10-12 03:06:46 UTC完成exit0/三门OK，SOURCE摘要保持；compileall-j1/site/governance通过。软件阶段七维报告、摘要与命令在[PLAN](../plans/2026-10-12-linux-helper-diagnostic-record.md)留存。未知字段删除、None未观察、原执行/断言/收尾及旧记录兼容合同不变；新SHA原生结果另验，不撤销741失败或授根因修复。
