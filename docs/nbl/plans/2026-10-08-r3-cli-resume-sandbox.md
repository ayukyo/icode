# R3 CLI恢复的隔离参数断链修复

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。先提交契约硬停止片，再改runner；随后自动实施同次工单共享预算片。

## 三问与已确认根因

2026-10-08主代理回读cmd_recover与resume_contract_step，独立只读审查实际调用CLI恢复入口：仅替换无关前置以阻断KEY/模型，真实resume函数未替换，得到 `TypeError: resume_contract_step() got an unexpected keyword argument 'sandbox'`，模型0次、恢复体内CP0调用。唯一定义和直接import无别名或fallback，旧CLI/recovery测试没有该边界用例。

真实问题是已选择隔离对象的参数签名与调用方不一致，不是模型或恢复事件链错误。已有_run_agent接受sandbox，可复用。影响CLI cmd_recover → resume_contract_step → _run_agent → ToolContext；不得通过删除CLI参数退回自动选择来掩盖断链。

主代理随后在真实临时CP create/start/before_write及有效checkpoint下调用实际main recover --resume，只有backend构建和sandbox选择为无KEY离线替身，CLI/Recoverer/resume均未替换：同一TypeError精确复现，模型0次、事件链字节完全不变、checkpoint仍在。该真实旧版负控可复用为专片TDD基线，不代表修复已完成。

## 实施及验收

- [ ] RED：临时真实CP工单、未闭合plan attempt、实际main recover --resume及离线backend，不mock resume函数。确认旧版因sandbox参数拒绝；不读KEY、不调用真实模型或生产命令。
- [ ] 最小修复：resume_contract_step新增可选关键字sandbox默认None，并原样传_run_agent，默认直接调用兼容。仅2行生产变化，不调整事件/恢复/预算/沙箱策略。
- [ ] 测试显式sandbox同一对象传递至实际上下文；CLI0/1退出按真实StepReport，不能伪造成功恢复。None旧调用、budget301硬停止、未决副作用入口拒绝及KI/SystemExit透传保持。显式NoIsolation只测参数链，不算隔离能力证据。
- [ ] 冻结矩阵20轮、关联CLI/recovery/hard-stop/runner；独立SPEC→QUALITY、7维自检、完整preflight三门及compileall≤j6、治理/官网/竞品/diff。干净pip安装实际CLI恢复接口；main提交推送、核对远端并观察新SHA。

本片不接新增policy/workspace_session，不放宽恢复门、R2/R3评分或自动模式，不宣称跨进程budget连续。复用持续对照固定Codex的执行事实与终态分层机制，不复制源码、增加依赖或权限。调用链诊断与本片动态回归才是验收依据。

**Execution Mode:** serial implementation, independent read-only research/reviews
