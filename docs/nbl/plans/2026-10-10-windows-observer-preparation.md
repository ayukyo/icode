# Windows Reviewer 观察器准备窗口

观察日期：2026-10-10。代码基线：`711e9fb`；待验收修改仅涉及 CI 配置和其合同测试。

## 实际问题和调用链

`06853da` 的 [Windows x64](https://github.com/ayukyo/icode/actions/runs/38051572829/job/114211656650) 与 [Windows ARM](https://github.com/ayukyo/icode/actions/runs/38051572829/job/114211656724) 返回 `target_context=wait_timeout`、`observer=target_unavailable`。因此宿主管理员 WFP 观察器没有接到本次目标，未启动；同一流水线的管理员订阅正控成功，不足以证明候选请求得到了观察。

父进程从标准用户 Python 启动开始等待目标 30 秒。子进程先创建 canary/listener，复制 Python runtime，再运行最长 15 秒的宿主解释器正控、最长 12 秒的 private-network capability 正控及最长 2 秒的接收核对，最后才发布目标。runtime 复制不包含在这些正控时间内；远端记录 staged_files=6722。30 秒准备预算不能覆盖这些阶段的预算之和。这是可确认的时序预算缺口；尚无分阶段时长记录证明本次超时具体发生在哪一阶段。

## 修改

将目标发布准备阶段设置为命名的、有限的 180 秒预算。目标字段校验、进程提前退出检测、25 毫秒轮询、15 秒观察器就绪等待和后续 65 秒 payload 等待保持原合同。准备预算只服务于 CI 诊断，不扩大产品权限或更改网络拒绝判定。准备超时仍返回未知，清理仍执行。

选择 180 秒是给文件复制和正控留出余量的诊断预算，不是已经测得的运行时上限；实际 Windows 复核若仍超时，应记录阶段时长并修正握手时序，不能无限延长窗口。

## 验收

- 配置合同先出现两项预期断言失败，再通过；工作流、WFP capture 和 read-probe 关联回归共 74 项通过。
- 提交前完整 preflight：密钥扫描、子模块完整性、全量 unittest 三道全部通过；YAML 使用系统 PyYAML 实际解析通过，job 总时限仍为 25 分钟。
- 待 Windows x64/ARM 真实复核：目标必须 `valid`；观察器启动、就绪、结果回收及清理逐项核对。无匹配事件、权限不足、网络等待超时继续保持 UNKNOWN。
- 即使观察器成功启动，也只有匹配具体 package SID、地址族、目的地址和端口的实际事件才能支持拒绝观察；本片不关闭 Windows 原生、生产 runner 或 R2/R3 总验收。

## 七维自检范围

本机可核对 YAML/合同语法、父子调用链、有限预算与早退、异常/清理分支、工作流关联和兼容性。Windows 动态可运行性等待远端，不以 Linux 合同测试替代。
