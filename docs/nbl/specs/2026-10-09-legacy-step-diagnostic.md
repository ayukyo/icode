# 旧入口测试的缺报告诊断修正

日期：2026-10-09。基线main `9b22490b6feb55be8aa2ab459b1f00b1d898b41f`，vendor `d935a5218ca2970bce8157814bfda1f03aa6c9c4`。仅测试诊断，不修Windows Git或生产执行链，不授R2/R3整体通过。

## 问题与范围

此前43e7739 Windows x64 DEFAULT在legacy code测试中出现IndexError。当前源码可确定：`observed`仅在原run_contract_step正常返回后追加，Native executor已将异常转为稳定chain_error，但断言消息无条件求值observed[0].render()，使二次IndexError掩盖无报告的原故障。不能从该日志推断原错误一定是Win10038或Git10093。

按用户连续开发要求，先完成Linux片发布，再独立修此明确单点缺陷。方案为先断言恰好一份报告，再render；测试包装记录异常类型及纯整数errno/winerror后原样raise，保留生产转换路径。相比使用空字符串隐藏诊断，此方案明确无报告仍失败；相比修改生产异常API，此方案不扩大接口、权限或兼容面。唯一源码变更为tests/test_contract_engineering.py；既有dispatch=1、唯一receipt、成功finish及独立验包断言保持。

## TDD与边界

先添加一个守卫方法，内部新建真实unittest用例及TestResult，注入无报告异常，检查最终是带稳定诊断的AssertionError而非IndexError。两个场景仅令既有传输double计数为0或1，不是两次真实命令，不能从计数宣称载荷启动。实际Native executor的异常转换、用例失败收集及cleanup仍执行。异常含私有正文marker，最终失败诊断不得包含它。

RED：1方法、2个subTest失败、0.467s，均因原observed[0]产生IndexError而不是预期AssertionError。随后最小修正；新守卫与原legacy code/deepcheck方法3P/0F/E/skip、8.349s。原始源码SHA256 `2406b0a2d92bd1eb5d174fe674b78680ec6afe33ab9eefec72a467b1398db1cc`；独立SPEC正在进行。sequential-thinking205–207记录修正边界与风险。

作者自检：新诊断不输出异常正文或非整数错误码，原异常裸raise，正常报告只render一次，生产/vendor均零修改；新负控、旧两个完整测试正控通过。尚不以作者自检替代独立审查或全局发布门。

## 独立上游机制核对

10:30:58–10:31:11 UTC，独立只读核Codex固定历史提交`2c3156adf4c9454f0e01c839669255c6a32b5416`的[protocol/src/error.rs](https://github.com/openai/codex/blob/2c3156adf4c9454f0e01c839669255c6a32b5416/codex-rs/protocol/src/error.rs)，不称当前HEAD或本轮许可证审查。采纳typed语义分类与原错误分开保留；不适配其可能输出正文的Debug/Display或Denied stdout/stderr字段作为本工程脱敏证据。只借鉴机制，无源码复制、新依赖或权限，成本仅一处测试修正及守卫；实际安全与兼容仍由本仓实测证明。完整20项目名单未刷新。

阶段结束10:39:25–10:39:42 UTC独立核官方main为`2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4`；[当前固定文件](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/protocol/src/error.rs)与上述历史文件均33722字节，SHA256均`6e3f1eedd6d70450ecf84b2654707c1107dac0c06b4ed65631bd3251bc59373c`。仅此文件无差异，取舍不变；未核本次许可，不从旧commit许可推断，未扩大到全仓研究。

## 后续验收

独立SPEC后不同QUALITY；冻结后定点整个契约模块、指定三方法20轮、原DEFAULT、原preflight完整一次，j1编译、原守卫及文档两轮，再精确main发布与新SHA观察。已有9b22490全量2502项属于上一源码版本，不转记为本次通过。

独立SPEC已3P/0F/E/skip、7.470s、C0/I0/M0；不同QUALITY已3P/0F/E/skip、7.450s、C0/I0/M0。两者源码摘要前后一致，均只跑指定三方法、零修改并STOP。唯一源码增量48增4删；进入冻结后全局验收，完整契约模块运行中。

root完整契约模块42P/0F/E/skip、48.455s、rc0。随后串行20轮固定新守卫与原code/deepcheck三方法，每轮要求3 actual、零外层skip；不能把两个注入子场景或重复次数计作不同产品能力。

20轮实际60P/0F/E/skip、156.367s；每轮3项、7.339–7.923s。源码未变，随后启动原DEFAULT回归。

原DEFAULT614P/0F/E/skip、201.693s、rc0，bootstrap verifier byte binding另输出PASS。随后同冻结源码启动原preflight完整一次；子进程原argv/kwargs/环境不变，外层仅汇总结果及stdout/stderr中原HEAD保留路径，不修改测试结果。

## 首次全量发现的选择遗漏

原preflight实际2503total/2443P/59skip/1F/0E，588.022s（子进程588.466s、preflight589.968s），拒绝发布。唯一失败为test_contract_engineering_selection_exists_once_without_native_readiness_claim：新guard未加入原要求全覆盖的显式默认集合。此前作者及两个独立审查没有发现这个关联遗漏，保留原审查历史，不将该失败归为环境问题。HEAD异常现场实际stdout登记`/tmp/icode-linux-bridge-bmfni5op`，此前八个根不动。

root完整核默认集合及原选择断言，仅在scripts/run_workspace_ci.py的CONTRACT_ENGINEERING_TESTS增加一个新guard名称；不修改选择断言、skip或成功条件。源码范围因此为测试诊断文件加CI清单一行，而不是上方最初单文件范围。选择守卫与新guard实际2P/0F/E/skip、0.428s；script冻结SHA256 `0a741778b1b53c3ec21e106ecad08abf1f8805922c1d171ae2a1b6610f9d2c76`，原测试文件摘要未变。

该关联修正重新独立SPEC→不同QUALITY，再20轮选择守卫与新guard、原DEFAULT及完整preflight。此前三方法20轮60P仅保留未变测试文件信用，不宣称新的CI清单已通过旧全量。

关联修正独立SPEC2P/0F/E/skip、0.431s、C0/I0/M0；不同QUALITY2P/0F/E/skip、0.454s、C0/I0/M0。两源码摘要均一致，原选择断言与成功条件不变，审查者均STOP；进入新冻结复验。

新冻结20轮选择守卫与新guard：40P/0F/E/skip、12.779s，每轮2项。随后重新运行原DEFAULT；首次614项结果不冒充已含新guard的默认回归。

登记修正后的原DEFAULT实际615P/0F/E/skip、285.275s、rc0，bootstrap verifier byte binding另PASS。随后新冻结原preflight完整复验启动，保留首次2503项失败历史，不绕过原选择守卫。

## 最终本机软件验收

新冻结原preflight复验2503total/2444P/59环境skip/0F/E，unittest571.468s、原子进程571.888s、preflight573.300s，三道守卫通过。实际stdout新增HEAD异常保留根`/tmp/icode-linux-bridge-pdi79rst`，此前九根不动；不清现场或unknown。src/scripts/tests全部compileall -j1通过，新临时缓存不入库；治理、站点及严格竞品排期检查rc0。

两个源码SHA仍为上述冻结值，vendor d935a52干净，main未切分支。拟提交仅五路径：两个源码、本文、持续竞品对照及上一Linux阶段发布/线上记录。新文档受docs忽略规则覆盖，须exact force单文件；不force目录。

【架构级自检报告】（本片范围）

- ✅ 语法/编译：完整复验与j1编译通过。
- ✅ 依赖/调用链：默认清单遗漏已由原守卫发现并补齐，独立双审复核恰好一次。
- ✅ 逻辑/边界：零报告明确失败，正常报告先验证后读取，原成功条件保留。
- ✅ 异常处理：真实异常转换加故障注入验证，类型/纯整数错误码与正文分开，原异常raise；不声明覆盖任意异常类的所有行为。
- ✅ 关联模块：仅测试诊断及CI选择一行，原默认615P与完整2503项通过。
- ✅ 兼容安全：不修改生产/vendor、平台skip或隔离准入；新测试不授实际载荷执行信用。
- ✅ 可运行性：42项模块、原三方法20轮60P、关联守卫20轮40P及新冻结615P/2444P分层记录；59项环境skip不算通过。

未完成的产品门：G2完整Git审查身份、Windows有界Git读取、跨平台原生准入、安装态工程链、真实模型1→6及≥90%一致性。已合并询问前两项新增子仓最小修复授权，当前未获答复；已有执行根绑定授权不自动扩展。macOS maintenance.lock仅为独立待确认候选，不由本片诊断修正宣布解决。

## macOS 夹具维护竞态候选（同日后续）

线上 cdf8123 的 macOS DEFAULT 已由 3 个错误收敛为 1 个错误，剩余现场仍是初始快照读取 `maintenance.lock` 时的 `FileNotFoundError`。该证据只说明短生命周期 Git 夹具可能与后台维护竞争，不能证明生产快照有普遍缺陷；因此没有放宽 `WorkspaceSnapshot` 对普通源文件消失的 fail-closed 语义，也没有修改生产执行链。

本轮采用最小测试层候选：短生命周期、由测试完全拥有的 Git 夹具统一使用 `git -c maintenance.auto=false -C <fixture> ...`，并新增命令形状守卫，避免依赖 POSIX 临时路径。先以缺少 helper 的真实 NameError 做 RED，再 GREEN；独立 SPEC 与不同 QUALITY 均为 3P/0F/E/skip、C0/I0/M0。当前冻结源码摘要：`tests/test_contract_engineering.py`=`a3d29a3e08a572449517ebdedaf43448b1b0dec3bc3d5f70ea9cc03bdae763db`，`scripts/run_workspace_ci.py`=`59dc03342ce22c1a7c0f1d226924b902a3c7b792a67bc1bbc8d5d8491b61bbcf`。新增 guard 已登记到默认选择集合，避免只测到未被 CI 选择的测试。

定点验收：选择完整性、候选 guard、两个 macOS 失败边界共 4 项连续 20 轮，`80P/0F/E/skip`，83.809s；该重复矩阵仅证明测试稳定性，不授予 macOS 原生隔离或整树清理信用。待本轮默认、完整 preflight 及新 SHA 线上矩阵完成后，才能判断 cdf8123 的剩余错误是否真正消失；若仍复现，继续沿生产调用链做独立 TDD，不吞掉快照异常。

## Windows 诊断断言兼容修正（线上反馈后）

cdf8123 的 x64 Windows job 暴露了同一测试的跨平台语义差异：POSIX 入口保留注入的 `OSError(errno=5, winerror=10038)`，Windows runner 在进入边界前将其规范化为 `chain_error`，因此原先无条件要求 `OSError` 会产生新的测试错误。该失败不是生产错误分类漂移，也不能回写成 Windows 原生已通过。

最小修正仅将异常类型/错误码断言改为“若诊断保留 `OSError` 则核对纯整数码；否则接受稳定 `chain_error`”，两条路径都继续强制 `missing_step_report`、`state=failed`、正确 dispatch 次数及私有正文不泄漏。定点 2 项（missing-report + legacy code）`2P/0F/E/skip`、3.438s；随后默认 `616P/0F/E/skip`、191.197s，完整 preflight `2498P/60skip/0F/E` 三道门通过；compileall-j1、治理、官网、竞品排期与 diff check 也通过。未修改生产代码、Windows 子仓或错误协议；该修正不解决仍存在的旧 Win10093/Win10038、双 reviewer timeout 或 macOS maintenance.lock。
