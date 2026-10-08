# 118a Windows 构建上下文拒绝调查

日期2026-10-09，独立只读研究结束，root另取原日志并核实际源码。仅调查，不改变预算、失败门或生产runner；下一候选尚未实施。

## 证据基线

| Section | 实际证据与未知边界 |
| --- | --- |
| identity | GitHub hosted x64 runner，Server2025 10.0.26100，image20260925.250.1；serial/MAC unknown，不作现场设备声明 |
| time_window | 原decodedlog UTC22:12:03.5174418–22:16:51.0036593；关键拒绝22:16:48.3774969，宿主时钟偏差unknown |
| repo_matrix | runtime/analysis均118a2621cef92a5fcda510db295ea8c7658e5d4f，实际vendor1693651c1bd7daad3272eb054f0f81d6f254d08d；本调查只有root文档变更，verification未实现 |
| artifact_identity | actualCPython3.11.9、VS18 2026/MSBuild18.10.1-1.26427.6+3cd27c13e；22:15:57.739已输出exe构建路径，失败格helper摘要unknown，无签名/安装/upload artifact |
| evidence_sources | [provenance37850895825 job113566689296](https://github.com/ayukyo/icode/actions/runs/37850895825/job/113566689296)，独立研究一次完整分片读取62531字符/593行；root另取完整字符串，核末段原编译与失败行、终态jobs/artifacts API；源码probe及runner和workflow实际回读 |
| unresolved | 无stage、异常类别、query开始/结束、returncode/输出完整性或Job/reader状态；owner root，下一步最小CI专用闭集诊断设计 |
| conclusion_ceiling | observation_only：build-context CLI泛错误并exit1；不授PE采集、签名、安装、加载或R2/R3门，不推timeout根因 |

tools实际9PASS/0.173秒。原log的后续PE命令只是PowerShell预先回显，不是执行证据；API显示后续步骤skipped，全字符串没有context receipt/PE CAPTURED/attestation/19项安装成功或artifact。最后清理vctip没有父子/Job关联，不称probe后代泄漏。

## 调用链与结论上限

`probe`读取固定context与project，校验选择后，单次MSBuild property-only query经`_run_unittest_with_bounded_output`进入Windows threaded route。当前runner已经创建挂起进程、绑定Job后恢复，不能套较早“未接Job”的历史观察。

30秒用于`proc.wait`，不是从probe入口到返回的完整预算；Popen、reader启动、Job绑定/主线程恢复在它之前，失败之后另有Job/根退出/EOF/cancel/join清理预算。实际约50.638秒跨度只由编译产出到泛错误两日志相减，既不是query阶段实测，也不能认定timeout。`main`统一捕获文件/JSON/XML/选择、runner/返回输出、properties/工具目录等多种拒绝，现有成功receipt不能辨别本次失败。

| Claim | Kind | Boundary | Status |
| --- | --- | --- | --- |
| 构建已输出后context CLI exit1 | fact | 路径不证明bytes绑定或任一probe内部阶段通过 | supported |
| 30秒query timeout导致失败 | inference | 缺异常类别、query时点及清理状态 | open |
| MSBuild字段/JSON或Job/EOF导致失败 | inference | 泛错误不足以区分 | open |
| vctip是本query泄漏后代 | unobserved | 无父子或Job关联 | open |
| 本失败格已采集/签名/安装 | refuted | 无回执、后续步骤skipped、无artifact | refuted |

## 定点借鉴与下一片边界

独立研究及root复核固定CPython v3.11.9的[Windows wait](https://github.com/python/cpython/blob/v3.11.9/Lib/subprocess.py#L1573-L1594)与[创建阶段超时说明](https://github.com/python/cpython/blob/v3.11.9/Doc/library/subprocess.rst#L62-L68)，沿PSF许可历史固定版本，不称当前HEAD。[CancelSynchronousIo官方合同](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelsynchronousio)明确请求取消不等待完成；ERROR_NOT_FOUND也不能替线程收敛检查。Codex/SRT的挂起→Job→恢复仅复用持续对照历史固定Apache2机制，不重新查询HEAD或称有同款失败诊断。

采纳候选是CI probe及配套测试增加固定stage/failure_kind的失败专用ASCII回执，保留成功receipt逐字兼容、原泛错误/exit1、单次query和30秒/16KiB预算；具体异常类型先于基类，无文本解析/cause遍历/路径/argv/env/stdout/stderr输出。收益是缩小下一窗口拒绝位置，成本是阶段与类型具名正负控、诊断故障原结果保护及新SHA四格观察。query+output_capture仍不定位Job/EOF/timeout-cleanup，不提前授根因。

暂缓生产runner观察接口、重试/调预算、取消Job或换工具；不适配50秒定性timeout、cancel成功等完整EOF、诊断成功视产品隔离。没有复制上游代码、新依赖/权限/源码修改或任何测试；本片只是后续设计输入，R2/R3整体开放。

## 同日补充：固定 Codex 的错误类别与载荷分层

新独立只读研究定点核固定`2c3156adf4c9454f0e01c839669255c6a32b5416`，root另取三个raw源码的相关片段（web raw cache miss后只读curl，三次exit0）及全文[Apache-2.0许可](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/LICENSE)。[error.rs:83–89](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/protocol/src/error.rs#L83)生成payload-free的`CodexErrKind`，以snake_case序列化；[212–215](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/protocol/src/error.rs#L212)从typed details转换，不解析Display。**采纳机制候选**是ICODE闭集类型分类与原文本分离；本项目已有TimeoutExpired、VerificationOutputCaptureError/LimitError，可用类型优先级，不复制代码或新增库。

[exec.rs:822–835](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/core/src/exec.rs#L822)有typed Sandbox Timeout/Denied，但客户端[error.rs:509–522](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/protocol/src/error.rs#L509)统一映为SandboxError并同时to_string生成message；[ErrorEvent与StreamErrorEvent](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/protocol/src/protocol.rs#L2123)仍序列化message/additional_details。**不适配**照搬客户端分类粒度或把typed enum当无文本泄漏证明；[Windows spawn诊断](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/core/src/exec.rs#L546)解析错误字符串并记录exe/path_kind/实际error_code，也不符合本候选禁原文本/路径/实际值边界。

**采纳测试纪律候选**：[misalignment专属字段排除正负控](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/protocol/src/protocol.rs#L5911)核精确序列化/恢复及Debug不含其特定敏感字段；不推演为全部错误保密。ICODE后续需自己的异常str/repr poison、秘密marker缺席、闭集ASCII/固定字段及诊断故障保护。收益为下一原生拒绝可定位且不公开正文；成本为阶段与类型矩阵、旧成功逐字兼容及同SHA观察。**暂缓**生产runner细阶段遥测、重试或调整额度；固定源码而非全项目最新架构复核，没有运行Codex、模型或额外实验，不授118a根因或R2/R3信用。
