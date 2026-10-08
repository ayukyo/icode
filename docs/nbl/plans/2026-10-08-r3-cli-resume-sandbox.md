# R3 CLI恢复的隔离参数断链修复

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。先提交契约硬停止片，再改runner；随后自动实施同次工单共享预算片。

## 三问与已确认根因

2026-10-08主代理回读cmd_recover与resume_contract_step，独立只读审查实际调用CLI恢复入口：仅替换无关前置以阻断KEY/模型，真实resume函数未替换，得到 `TypeError: resume_contract_step() got an unexpected keyword argument 'sandbox'`，模型0次、恢复体内CP0调用。唯一定义和直接import无别名或fallback，旧CLI/recovery测试没有该边界用例。

真实问题是已选择隔离对象的参数签名与调用方不一致，不是模型或恢复事件链错误。已有_run_agent接受sandbox，可复用。影响CLI cmd_recover → resume_contract_step → _run_agent → ToolContext；不得通过删除CLI参数退回自动选择来掩盖断链。

主代理随后在真实临时CP create/start/before_write及有效checkpoint下调用实际main recover --resume，只有backend构建和sandbox选择为无KEY离线替身，CLI/Recoverer/resume均未替换：同一TypeError精确复现，模型0次、事件链字节完全不变、checkpoint仍在。该真实旧版负控可复用为专片TDD基线，不代表修复已完成。

## 实施及验收

- [ ] RED：临时真实CP工单、未闭合plan attempt、实际main recover --resume及离线backend，不mock resume函数。确认旧版因sandbox参数拒绝；不读KEY、不调用真实模型或生产命令。
- [ ] 最小修复：resume_contract_step新增可选关键字sandbox默认None，并原样传_run_agent，默认直接调用兼容；按后段实体安装追加，显式复用当前cp的OperationRecorder，原scope保持。合计3行生产变化，不调整事件/恢复/预算/沙箱策略。
- [ ] 测试显式sandbox同一对象传递至实际上下文；CLI0/1退出按真实StepReport，不能伪造成功恢复。None旧调用、budget301硬停止、未决副作用入口拒绝及KI/SystemExit透传保持。显式NoIsolation只测参数链，不算隔离能力证据。
- [ ] 冻结矩阵20轮、关联CLI/recovery/hard-stop/runner；独立SPEC→QUALITY、7维自检、完整preflight三门及compileall≤j6、治理/官网/竞品/diff。干净pip安装实际CLI恢复接口；main提交推送、核对远端并观察新SHA。

本片不接新增policy/workspace_session，不放宽恢复门、R2/R3评分或自动模式，不宣称跨进程budget连续。复用持续对照固定Codex的执行事实与终态分层机制，不复制源码、增加依赖或权限。调用链诊断与本片动态回归才是验收依据。

**Execution Mode:** serial implementation, independent read-only research/reviews

## 实体安装审查追加（2026-10-08）

首个两行实现8方法/11场景通过，20轮160通过/0SKIP仅为历史：主代理随后实际干净安装wheel/-I/临时cwd/无ICODE_SKILL_ROOT，传显式Settings及真实有效CP checkpoint，调用原resume（省略sandbox也复现）仍ConfigError/0模型/事件字节未变。根因是_run_agent默认OperationRecorder使用load_settings_for重建全局CP，丢调用者的Settings，而不是没有在CLI指定--skill-root。

本片最小追加第三行：resume显式传OperationRecorder(cp,out_dir,ticket_id)，保留原默认scope及恢复操作合同；复用本次cp，避免新全局source。需追加禁止load_settings_for的真实Settings/API/CLI负控RED→GREEN、独立installed路径；修改后重新20轮，不用旧160计最终冻结。包内SKILL资源另片不能掩盖显式配置丢失。

主代理另在现有跨平台workspace默认矩阵新增本模块，不扩大现CROSS50列表；覆盖合同先旧版1/1FAIL，再6/6PASS。scripts/run_workspace_ci.py SHA256 `9835a0752c5fa559c510f1b3c3ffd8aafd117c2e400176af194c69c8320568e0`、tests/test_run_workspace_ci.py `23edc22b5fdf90e4ca3e3a0a61e6a02bf8ffd65d54a4e88e61e6cd0ac606b17d`；最终全守护/独立审查必须包括这两个关联文件，不仅两行runner改动。

## 最终冻结及独立验收

最终第三行Settings负控三场景先3 FAIL/0 ERROR/0 SKIP，失败前模型0次、events/checkpoint字节不变；GREEN后9方法/14场景×20轮共180 PASS/0 SKIP（226.415秒）。关联135为130 PASS/5既有平台SKIP（37.997秒）。runner摘要 `d4dc65ef3480667835831998620059428bd9b4a2c5842bd9b0f52ad772d97471`，新测试 `6660ee855b1e52f03cc274d37ce9337efb5bf3ec417803ec327a475f856e84df`，每轮不变；旧160不计最终验收。

独立SPEC：新9+CI6共15/15、11.657秒、0 SKIP；关联141为136 PASS/5旧SKIP、39.721秒。不同代理QUALITY：15/15、11.394秒、0 SKIP；其另选关联126为121 PASS/5旧SKIP、27.598秒。额外实际写入操作确认当前CP/空scope，真实start/finish回执各1；缺检查继续保留checkpoint/openstep。CROSS50逐项与HEAD一致，四冻结摘要、AST及diff通过；没有新审查发现。

主代理完整preflight三门退出0，当前实际收集2010项，守护不打印通过SKIP数，因此不称全部原生/零SKIP。compileall -j6、治理、官网、竞品排期及diff通过。PyPI TLS EOF阻止首次隔离构建；随后uv --offline按声明依赖及本机缓存隔离构建成功，不关闭TLS或降低构建依赖。干净venv pip --no-deps安装、临时cwd/-I/无ICODE_SKILL_ROOT/PYTHONPATH，已安装runner原字节摘要匹配；默认API、显式sandbox API、显式Skill CLI成功，实际write_file缺检查CLI失败保留checkpoint，expected100/301响应CLI预算failure，五场景全部通过。

安装测试两个首版夹具错误已修正重跑：缺检查场景须真实写产物才到边界门；budget-tokens是expected而非硬上限（默认倍率3），须100而非300。修正仅仓外验收夹具，没有生产改动，不将首版失败算通过。验收显式只读消费固定外部SKILL，仍不证明pip-only包内资源、真实模型质量或跨平台原生隔离。

【架构级自检报告】

- 语法/编译：AST、compileall -j6、diff通过。
- 依赖/调用链：真实CLI→resume→AgentLoop→Context/同次CP通过。
- 逻辑/边界：最终20轮及五安装场景通过。
- 异常处理：预算、未决副作用、检查缺失与原对象中断负控通过。
- 关联模块：独立关联回归、操作回执与CI选择合同通过。
- 兼容安全：默认None、原scope和CROSS50保持；未读KEY或修改子模块。
- 可运行性：本机已安装离线执行通过，Windows/mac原生及新SHA线上待实测；不称R2/R3整体通过。
