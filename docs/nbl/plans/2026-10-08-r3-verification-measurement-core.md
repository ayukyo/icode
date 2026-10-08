# R3 独立验证测量统一 Implementation Plan

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development；独立只读研究和 SPEC→QUALITY。按已授权 main 开发，不新建分支。

**Goal:** 初次验证与有界修复复测共享同一观察窗口，保留现有 API、证据和错误语义，为后续契约验收接入提供可复用入口。

**Architecture:** 只抽取 runner 内私有单次验证函数及最小结果结构；调用现有 run_unittest、Git状态/原始tree投影、工作区快照和 _bind_task_evidence。模型循环、异常报告、修复账本和 Reviewer 仍由 run_task 拥有。不得以 run_task 替换 run_contract_step。

## 三问与边界

1. 真实问题：run_task 初次与修复分支重复相同的测试前后文件/Git/输出绑定窗口，后续适配容易改漏。
2. 已有实现：已有有界输出执行器、快照/树解析和证据绑定，全部复用；不创建另一命令执行框架。
3. 调用链：只影响上述两个调用方及私有测量函数，run_unittest/TaskReport/VerificationEvidence/CLI/控制面接口不变。

本片不是契约工程验收接入、共享全流程预算、可信工程命令计划或真实模型1→6的完成证明。保持当前 readiness 与自动模式限制。

## Task 1: 提取并锁住原观察语义

- [ ] 完成

允许编辑 src/icode/runner.py 和新 tests/test_verification_measurement.py；必要的现有相关测试只能补兼容断言，不重写旧断言降低门槛。不改 vendor、平台实现、CI权限、预算规则或模型配置。

- [x] Step 1: 特征测试与 RED

先以真实临时工作区/实际 FakeBackend 调用锁住初次与修复行为。新增私有入口测试缺失导致的结构性 RED 必须与行为负控分开记录，不宣称旧逻辑存在本片未修复的行为缺陷。覆盖稳定与测试写文件、HEAD变化、object format变化、Git投影不可用、原始命令/上限/sandbox传递、失败分类和实际attempt。

- [x] Step 2: 最小抽取

由调用方先保留模型结束后的 after 快照（失败报告仍需要）；私有函数接收该快照和原基线，捕获Git前态/树，执行同一个有界run_unittest，再捕获Git后态/树/文件快照并绑定证据。只返回 changed_files 和 VerificationEvidence，不新建 ready bool，不改变现有快照与绑定顺序。

VerificationOutputError、TimeoutExpired、OSError仍由原调用方转换私密不完整报告，修复失败保留先前证据；程序错误和 KeyboardInterrupt/SystemExit原样透传。不能扩大catch范围吞掉Git或绑定错误。两个调用方不保留重复观察窗口。

实施前实际核对确认：不能直接把整个helper放进原三异常catch，否则会新吞Git/绑定OSError。采用唯一必要的私有output-failure wrapper：仅围住helper内run_unittest，携带原异常对象；调用方仅catch该wrapper，传原error至原报告构造函数。公开run_unittest直接调用仍抛原异常，Git/快照/绑定异常完全透传。测试必须独立证明这些异常来源不被混淆，不新增公共错误协议。

- [x] Step 3: 最终冻结与回归

新测试最终摘要连续20轮，记录方法数与SKIP；关联 runner/self_verify/task_timeout/task_verification_io/reviewer/workspace tree测试，旧错误隐私、输出上限和真实子进程清理断言保留。实现者7维自检，独立SPEC→QUALITY，完整preflight三门及compileall≤j6、治理/官网/竞品/diff。

- [ ] Step 4: 交付

精确提交推送main并核对远端。下一片先解决契约循环预算硬拒绝被产物齐备软化、共享预算所有权，再设计实际政策绑定的契约验证接入；不据纯抽取宣称全链闭合。

## 研究与采纳上限

2026-10-08主代理实际回读 Codex 固定源码 `1fbe15c962cc3d8eabec36d67987c83cfc4eeec9`（Apache-2.0）：[独立审查入口](https://github.com/openai/codex/blob/1fbe15c962cc3d8eabec36d67987c83cfc4eeec9/codex-rs/core/src/tasks/review.rs#L90-L132)使用新上下文和显式工具限制，[终态](https://github.com/openai/codex/blob/1fbe15c962cc3d8eabec36d67987c83cfc4eeec9/codex-rs/core/src/tasks/review.rs#L133-L195)区分完成、取消和通道关闭，但保留纯文本解析fallback。

采纳：维持 ICODE 已有独立 Reviewer 与测量职责分离，不把模型自述当测试；代价是私有小函数和兼容测试，无SDK/源码复制/许可证依赖。不适配：不引入纯文本fallback，保留现有严格submit_review及实际读取证据。暂缓：跨契约工程计划和全链budget接入，需另有政策/控制面验收。该源码不证明上游存在与本片相同的Git测量抽取，也不代替ICODE测试。

**Execution Mode:** serial implementation, independent read-only research/reviews

## 冻结证据（2026-10-08；待实际提交推送）

runner SHA256 `f64c5cec05f1b637bb59ae950f35d7431c3f1cb56d8c5d0fa7ead3f8087cc33a`，新测试 `cd00e040b1c4eb193bd541c6c4d9c544557396daeea24beecf9d386c56be0d29`。旧版3项真实特征GREEN；新增9项缺私有入口的结构RED单列，不能冒称旧行为错误。实际测试空commit改变HEAD并改变包含.git的完整快照，旧RAM对照已确认必须保留unstable_during_test，不按最初错误夹具预期改生产。

最终12方法×20轮=240/240、0SKIP，25.585秒，轮前后两摘要不变。实施关联八模块265方法、253通过与12既有平台SKIP、25.404秒；SKIP不计跨平台通过。Windows/macOS本次未原生执行，虽复用既有对应tree投影，也不外推原生验收。

主代理实际隔离构建（setuptools84满足声明>=80）及干净pip --no-deps安装wheel，已安装runner字节精确一致；-I、临时cwd、无checkout imports下，实际稳定测试、测试新增文件导致unstable、真实缺interpreter保持公开原异常且私有包装、Git观测OSError原对象透传四类全部通过。初次--no-isolation因本地setuptools79不满足>=80被正确拒绝，不跳依赖检查且不计成功。原生wheel检查通过。

独立SPEC新增12/12、1.198秒、0SKIP；关联选择249方法，238通过/11既有SKIP、12.590秒；另实际9步测量顺序通过。独立QUALITY新增12/12、1.087秒、0SKIP；其六模块选择175方法，164通过/11既有SKIP、7.387秒；另实际9步顺序及修复回合binder OSError、测试KI/SystemExit原对象透传三负控通过，Reviewer不调用。各审查者模块选择不同，不混合方法总数；两者均无遗留发现。

主代理最终完整preflight于2026-10-08 07:01:23 UTC退出0、三门PASS；本树load的完整测试集为1983方法（preflight不单列SKIP数，不能补造全项实测）。compileall -j6、治理/官网/竞品/diff通过。冻结生产/测试三摘要未变，联合当前Linux procstatus测试竞态修复交付，不能称作两个各自独立提交；提交推送及新SHA线上结果待实际记录。
