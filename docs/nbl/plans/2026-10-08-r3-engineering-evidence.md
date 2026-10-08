# R3 多检查证据与独立验包 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。用户已授权main串行实施、阶段验收后提交推送、自动继续；研究/审查只读，不另建分支。

**Goal:** 把已交付的宿主工程检查结果接入既有证据、修复账本、保存/导入/导出及离仓stdlib验证器，保持旧格式完全兼容。

**Architecture:** 新增默认None的深不可变工程事实，旧证据分支不改字段或指纹。新版闭合公开投影、检查结果和绑定事实；完整审计摘要与稳定修复键分离。语义校验仅放在不import仓库的pack_verify.py，供生产与随包verify.py共用；不新造状态机，不在本片接runner/合同/Reviewer。

**Tech Stack:** Python3.11/3.12、stdlib、既有VerificationEvidence/VerificationLedger、有界严格JSON与原子证据发布。基线main `eead3ad2702be44800ee8f3ec0a49e6fcd803082`，vendor169不变。

## 三问、依据与文件职责

真实缺口：EngineeringVerificationRun尚不能保存或由独立验包消费；旧fingerprint仅Go Elapsed变化即has_new_evidence=true已RAM复现。已有Evidence/Ledger/导入限额/原子保存/发布/独立verifier可复用，调用链为宿主run→工程事实→基础证据/账本→保存或直接导出→CLI导入→内置及离仓verifier。本片不提高隔离、自动模式或R2/R3 readiness。

- 新src/icode/engineering_evidence.py：冻结标量/tuple事实、宿主plan/run严格桥接与公开投影，不保存原输出、argv、环境正文或绝对路径。
- src/icode/self_verify.py：默认None事实、旧分支原样、新分支完整fingerprint及稳定repair键、账本显式保全事实，不改变任意旧子类行为。
- src/icode/pack_verify.py：仅stdlib的新kind语义与摘要重算；闭合结构、公开plan投影和结果一对一绑定；包装专用有界JSON消费。
- src/icode/evidence.py：保存与直接对象导出的前置预算、导入/导出语义验证，失败前不触碰已有目标。
- 新tests/test_engineering_evidence.py：实际工程观察桥接、golden、去重、真实保存/CLI/离仓往返及重算manifest后的负控。tests/test_self_verify.py、tests/test_evidence.py现有兼容回归保持原样，scripts/run_workspace_ci.py及test_run_workspace_ci.py按独立新类纳入无SDK默认矩阵。

## 冻结语义

1. VerificationEvidence新增engineering_facts=None；None时to_receipt字段和值、evidence_fingerprint算法、passed、ledger行为完全原样。预校验投影也省略这个None字段，避免旧边界预算增加。工程事实内部不得含可变dict/list或任意对象，投影生成新的有界JSON值。
2. 新kind为engineering_verification、schema_version严格int1。缺失、bool、浮点或未知版本拒绝，不能退opaque legacy；其它旧/未知kind或无kind行保留原语义，不授予工程信用。
3. 公开plan绑定run/ticket、workspace/environment摘要、适用step/platform、有序checks；每项包括唯一check_id、kind、adapter、required、执行工具观察摘要、argv/cwd参数摘要、timeout/output限额。原plan_digest仅宿主声明；public_projection_digest可由公开数据重算，不能声称恢复隐藏argv/env。
4. 结果必须与冻结checks按ID/数量/顺序一对一，各项严格记录status/exit/tests_passed/完整output_sha256及cleanup/scope/cache-owner/resource/observer事实、固定error。not_run无退出/输出/信用；test passed须exit0且正计数；build/lint不补测试信用。聚合passed须至少一个required test、全部实际checks合格、完整稳定源窗口和原执行器passed，不能取末尾exit0盖前败。未知清理、源/计划绑定、输出或通道不能伪装passed或允许自动重放。
5. 新audit/fingerprint覆盖公开观察全集与旧基础绑定，但排除attempt/captured_at等标签；原输出SHA必须是原完整bytes，不做任意regex删数值。repair_fingerprint另域分离/版本化，绑定源码/环境/工具/参数/失败检查状态，排除时间、耗时、通过检查输出和raw输出差异。无严格失败用例适配时采用保守固定失败状态键，不宣称任意新诊断能授予新重试许可。未知副作用仍human。
6. Ledger保全工程事实；旧None证据仍用旧fingerprint，新工程证据has_new_evidence消费稳定repair键。新摘要不能绕过attempt上限或未知副作用门；记录和决策返回的完整观察仍可审计。
7. 语义校验为新schema自洽，不认证执行来源/质量。删除新kind并重造合法旧包最多失去工程信用，没有外部锚定不能检测所有降级伪造。共享校验器必须由保存、load_verification_receipts、_verification_payload及verify_pack消费，不只校验manifest。
8. verifications.json总输入/条数/结构预算与生产端一致；包装层最多130，逐receipt本体仍128，其它JSON仍128，不全局放宽。保留旧无kind有限float与本体128层正控。新字段/超大对象在digest/to_receipt和任何目标修改前拒绝；save与直接导出对象都覆盖，旧None预算不能多出字段/null。

## Task 1：工程事实、账本及所有证据入口闭环

**状态**
- [ ] 任务完成

**Dependencies:** None（已交付执行器基线）
**Parallelizable:** No（五模块共享schema与序列化合同，串行修改）

- [ ] **Step 1: 写RED**。新测试先以find_spec/assert检测新桥接入口缺失，避免ImportError冒充功能RED；随后 actual Python failing/nonzero/zero工程fixture→工程证据。新增旧golden、事实冻结/账本保全、elapsed/attempt/capture/通过输出变化不补修复信用、源码变化变键、未知清理human及check缺失/重复/额外/错序/伪passed测试。

```python
legacy = VerificationEvidence(step="code", attempt="1", kind="test",
    command=("python", "-m", "unittest"), exit_code=1, output="AssertionError",
    environment_fingerprint="env-1", artifact_hashes={"calc.py": "abc"},
    category="code", captured_at="2026-10-08T00:00:00+00:00")
assert evidence_fingerprint(legacy) == "c36a606190f236e92d3a586b92c78faf0e4df9e9eb575f438fe76181176a669c"
raw = json.dumps(legacy.to_receipt(), ensure_ascii=False, sort_keys=True,
                 separators=(",", ":")).encode()
assert hashlib.sha256(raw).hexdigest() == "6fa92e309d7819b3056508149ad51ea7585b620a8e087d68be883f16b81a9a9d"
```

上述两摘要在修改前基线实际捕获；期望值不得调用当前实现生成。新桥接API为build_engineering_evidence(plan, run, *, binding: VerificationEvidence)，要求plan/run/step/attempt及结果身份一致，不从模型或文件重载宿主计划。完整往返采用现有make_finished_plan_ticket/CLI fixture；独立verify.py以-I、空PYTHONPATH、仓库外cwd运行。

- [ ] **Step 2: 实跑RED并记录**：`env PYTHONPATH=/home/orbbec/git/icode/src /tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B -m unittest tests.test_engineering_evidence`。结构缺口与真实旧漏洞FAIL分开，fixture ERROR先修，不伪报。
- [ ] **Step 3: 最小实现**：按冻结语义定义深不可变事实与build_engineering_evidence，新增stdlib语义校验器及canonical摘要；旧函数仅显式None/非None分支，ledger重建保字段。所有入口共用同一语义校验器和前置有界投影；包装专用解析只增加两层，再逐row原128校验。保留现有保存/发布事务，未校验不得写目标。
- [ ] **Step 4: 实跑GREEN/兼容**：新类、tests.test_self_verify、tests.test_evidence、test_run_workspace_ci通过；新增包内wrapper重复键/坏UTF8/孤立代理项/非有限数值/版本类型负控、上限及上限+1、旧最大深度与其它128门不变。篡改新receipt再更新manifest文件SHA/pack_digest，内置与离仓verifier仍拒绝；自洽伪造仅自洽，不授予质量信用。
- [ ] **Step 5: 冻结验收后提交**：新方法20轮、完整DEFAULT及关联、独立SPEC→不同QUALITY、七维报告、完整preflight、compileall-j1、治理/官网/竞品/diff与干净包运行；通过后精确文件提交推送main并核对远端。源码漂移须重跑，旧守护不倒填。阶段提交由根代理执行，不由实现子代理自行提交。

## 后续依赖（不在本片冒称具备）

下一片run_task可选宿主计划及现有Git/tree窗口消费新版结果，随后真实code/deepcheck/chain/独立Reviewer和控制面终结；这些按工程总设计另验。Windows生产runner、macOS单任务额度及真实模型1→6/90%SKILL矩阵仍须总门，不由证据自洽替代。

独立只读研究固定PydanticAI f55bb8a和Aider5dc9490，主代理已实际回读核心原文和许可证；取舍/成本/许可/负控见持续对照“多检查证据绑定与稳定修复键”。研究额外发现旧本体128/包装130与vars新增None预算兼容陷阱，已列为硬门，不以研究替代测试。

---
**Execution Mode:** serial
