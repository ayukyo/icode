# Protected Git B3c record-verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.executing-plans after root review. Steps use checkbox syntax. 本轮 PLAN ONLY；先 root 全文回读＋fresh SPEC→不同 QUALITY，正式独立 TEST 作者先 RED、不同 SOURCE 作者后实施。main-only 授权覆盖默认 worktree/分支/自动执行建议；本文不自动实施、stage、commit、push。

**Goal:** 仅开放 record-verification 的显式程序内 canonical provider 传播和精确 dispatch，保留历史 receipt 重放、None 算法及原事务完成规则。

**Architecture:** 复用 C1a/B1/B2/B3a/B3b 与原 commit_metadata_and_event。handler 完整 verify/capture/reuse/provenance 同两 kwargs；fresh build 第二次比较复用 B2 proof adapter；局部 before_publish 绑定本次初始 live，而不是合法历史 candidate。step/inspection/final gate、C2 原生/原子性及 pin 不开放。

**Tech Stack:** Python>=3.10 stdlib、既有 Git 和两平台软件 CI；无新依赖、权限、私有通道或模型可见 API。

---

## 1. 真实问题、批准依据与当前输入

观察日 2026-10-15。Skill HEAD 为 970cd359944624a6403f757997bae6d0020a5473，作者只读核 clean；CP6542行、CI78行。该 SHA candidate38602476989、inspection38602476983、site38602477375 均 push/attempt1，动态 total_count=2+4+3，9 jobs success；作者此前已实际读取原日志。只授 B3b 软件小片，不授后续 B3/C1b整体、C2/C3/C4、Agent pin 或 R2/R3。

批准 [C1b DESIGN](../specs/2026-10-14-protected-git-c1b-propagation-design.md) 164行/raw5197c84cf851d6376f106c0c44c0df8e924ec440f1d6c0ad41434d8505d4821c；[B1](2026-10-14-protected-git-b1-context.md) 558行/1da45c07dd325ff5689ff101aa6cf95efa2a97c83540230b03b180b777fdb2d9；[B2最终修订](2026-10-14-protected-git-b2-history.md) 1383行/6e66e8d1a18b006f8ced9995b45f3eb68081aca7013bd960fce70cb9201a2066；[B3a](2026-10-14-protected-git-b3a-candidate.md) 773行/aaf385168cec3dc907624c2e4d155af04a37c66d7810deb042ef50c27a8f2feb；[B3b](2026-10-15-protected-git-b3b-build-start.md) 707行/43c3a0421a8bfe2b223204073c0d23449dc2b879ff4297281dcd97e2e472bc8e 均已核实际字节。原 C1a/d23e230、inspection95199、candidate/delivery5abe 合同不变。

三问已确认：970 main 仍拒 record-verification，而 handler 的 capture/reuse/provenance/末次 compare 漏两参数，是真实缺口；已有 canonical API、B2 adapter、B3b build receipt 与原事务可复用；完整调用链会受影响，不能只加 main allowlist。root 回报官方 sequential-thinking 799459 三步 accepted/exit0，记录其需求分解→最小方案→风险评估，不冒称作者重调。root已全文读实际 handler/main，并明确接受本最小片契约。

备选已按实际依赖比较：推荐本片；完整 step start/finish 会牵涉 workspace_git_head raw 读取、独立 InspectionGitProvider ABI、inspection/artifact writer，暂缓；全 final-linter/host 通道更大，暂缓。没有把 optional Git 端口失败折为空，也不修改 inspection ABI。当前实际 finish_gate_steps 仅 patch/verify/readme，不能说所有 review finish 都调用 final linter。

| 冻结输入（raw SHA256，不是 commit） | SHA256 |
| --- | --- |
| tools/icode_control.py | 5ce5a6d0ebec51b33689e58f79b276b57301f9c37237d8d5b23c4f10be736806 |
| tools/icode_candidate.py | 12542f3b2bdccb6964433c20ed9f8ac0142c392027b52c0b5924e1421d742481 |
| tools/verification_evidence.py | bbf583c1668438f4bc9120bf6fca6cac7251f2c8a130b7c15e0ef3147bad3ba1 |
| tools/verification_debt.py | b0d4450d7d1fded0df6da005c4764aa29a0aeae8abf934975132096b867ac441 |
| tests/test_candidate_history_unit.py | 41be1da83a0b1d91a004fdb7cf5f54d4429e1d4ce67eb67ff061c49f4a0c990a |
| tests/test_candidate_context_unit.py | 31d2576fc408d2171483e611485ac8c9291d5f9f92ed87caa9e11522f79e9ef5 |
| tests/test_candidate_dispatch_unit.py | 41aaa32202d25c4872085f94e3b908b9f2bb73019b76e65abe852abe94b7ec3e |
| tests/test_candidate_build_start_provider_unit.py | a358f9747d6a416db77b9cc4f790c593f2387d6355cfaede2760560e3719b4d6 |
| tests/test_candidate_verification.py | dc263fa5242d2bdf6bcbfbfbd31cbc5170fadbce4fcc61d8094448af1684eb92 |
| .github/workflows/candidate-provider-software.yml | d1cc87f88f3784bb240175915b3e545cf58d599037a2ceca871ee9508ecda062 |

新路径 tests/test_candidate_record_verification_provider_unit.py 当前不存在。未来仅三个实施路径：该 TEST、tools/icode_control.py、.github/workflows/candidate-provider-software.yml。旧四个软件 TEST、candidate/evidence/debt、原 verification TEST、Agent SOURCE/pin 全不改。Agent 当前其它 dirty 文档/Windows TEST 属 root/并行任务，禁止覆盖。输入漂移先回读差异重审；不能强套旧 patch 或改变 TEST 凑绿。

## 2. 唯一接口、调用顺序与信用边界

拟议唯一新增 handler 签名：
~~~python
def cmd_record_verification(args, *, git_provider=None, require_git_provider=False):
~~~

main 原同名程序内 kwargs 保留，仅将精确 allowlist 从两对增为三对：
- args.cmd=="candidate" 且 args.func is cmd_candidate；
- args.cmd=="build-start" 且 args.func is cmd_build_start；
- args.cmd=="record-verification" 且 args.func is cmd_record_verification。

未知/错配/同名伪函数、step、其它 writer、final gate 仍 candidate_business_propagation_pending。无 argparse provider 参数、Namespace/env/global/contextvar/model JSON 身份发现；不放宽 CandidateGitProvider ABC、严格 bool 或 CODE root 校验。

### 锁与完整验证

1. 原参数/metrics/JSON、meta_probe 及 kind/build 校验顺序保留。access 只在原合法 None/False 时为空，不将 0/[] 误作 None。
2. 原 DirLock 内、recover_pending_transaction 前，以真实 metadata 调 _candidate_context_guard；provider+disabled 明确 candidate_provider_context / "candidate tracking required"，不会自动启用契约。健康 context 有 TXN_NAME 则 candidate_transaction_pending，不做 provider 恢复。None 原恢复顺序不变。
3. 原 vNext/schema/close_state/close_repair 条件保持；verify_event_chain 显式同 kwargs，保原 hash/schema/B2 历史语义，不 semantic=False 跳验。
4. enabled 路径 capture 当前 live，同 canonical/两 kwargs/已验证 events；resolve_candidate 保留原当前/历史选择。validate_supersedes/direct/test_summary 原唯一逻辑；validate_reuse、validate_provenance 显式传播，不 fallback 动态模块。
5. fresh build/pass 的原第二次 snapshot 显式传播；仅 provider 分支复用 evidence._compare_candidates，None 仍原 canonical compare。unknown/head_history_changed/不可用证明→EvidenceError(candidate_proof_unavailable)→原 ControlError(verification_evidence)；普通 source_or_contract_drift→原 source candidate changed。不能把 proof failure 吞成普通 mismatch，也不能复制第二份普通 reason 白名单。

### 幂等、publication 与历史 candidate

原 JUnit stored summary 与 prior receipt 重放仍不重读已移动报告/本地产物；事件回放原 check_files=False 仍完整验证 proof，不能 mock 成跳过历史语义。prior 成功返回前执行局部 before_publish：再次 capture 本次 live、核 candidate_id 未在本 invocation 内改变、最后 guard。query/expiry/capture返回后expiry均不能借 prior 早返回成功。

这个重放仍是历史 receipt，不因返回成功授“该历史 run 就是当前源码的 fresh pass”。合法历史 candidate 与本次 live 可以不同；新 fixture 以真实 same-content commit 两代和旧 runtime/build/reuse 证明这点。publication 必须比较本次最初 live 与末次 current，不能比较 args.candidate_id 或 input_payload["candidate"]。

新记录仍原 UUID/run/meta/event/schema。局部 callback 使用同 out_dir/meta 对象、已验证 events 和两 kwargs；metadata 中候选策略字段不另取源，verification_runs 的原追加不赋 Git 权限。provider 已被 enabled gate 限定，live 在进入 callback 前已初始化；None/disabled 原路径不执行 callback，不以捕获 UnboundLocalError 兜底。

commit_metadata_and_event 完整字节不变。其原 guard/full before verify/纯 prepare envelope、txn前guard、metadata前guard、metadata替换后 callback+guard、append 顺序复用。append前失败回滚 control metadata/events、保留真实 CODE；已append后 fsync/返回失败仍依事件存在完成 metadata。不能 append 后加 guard 再谎称回滚。

C1b只授可注入的软件检查点。最后检查至 append 仍非原子；无 C2 epoch/snapshot/attrs/finish_epoch/cleanup、真实 private transport、宿主/root authority、生产执行、C3 delivery 或 C4 pin 信用。

## 3. 完整 TEST oracle

附录A为独立15方法，不继承 HistoryTests，避免重复收集原12。复用其真实 None create→bind→enable/build-start/record 端口、separate-git-dir 导出、非Git CODE实际字节和 canonical raw _git AssertionError tripwire；匿名 Git仅在 TemporaryDirectory，不碰用户项目 Git。None 正控是真实端口，不手造成功 event/hash/provenance。

disabled fixture 只不调用原初始 candidate enable，真实 None create→bind 保留；canonical head/base导出仅用于匿名 provider 准备，不写 candidate_tracking。两例 candidate_id=None/非法64零都要求 candidate_provider_context、control冻结、不自动启用。这不是 load_metadata mock 或未初始化变量 ERROR 充 RED。

| 方法（test_前缀省略） | 正控/负控 |
| --- | --- |
| none_cli_real_record_and_immutable_report_replay | None main 真实记录；移除JUnit后原receipt幂等、字节不变 |
| provider_real_code_callbacks_and_exact_canonical_kwargs | 非Git CODE manifest实际SHA；verify/reuse/provenance/commit/capture同canonical与kwargs，纯prepare单列 |
| main_exact_three_pairs_and_unconnected_step_reject | 新record真实正控；原candidate/build dispatch spy；未知/错配/step拒绝不执行 |
| missing_wrong_root_foreign_class_and_falsey_reject | 缺provider/object/异dynamic类/错根/0/[]不写 |
| real_disabled_contract_rejects_missing_and_invalid_candidate_without_live | 真实disabled两例精确context gate，无live读取/自动enable |
| pending_never_recovers_even_with_invalid_context | invalid先拒，healthy pending拒，recover tripwire和pending bytes保留 |
| fresh_build_keeps_real_provenance_and_second_capture | 真build-start目录/真实binary bytes与SHA、3次同参数capture，不执行编译器 |
| second_compare_proof_unavailable_is_not_ordinary_mismatch | 只末比较注入unknown/head_history_changed/ordinary；前二proof_unavailable，第三原mismatch，确认真实调用命中 |
| historical_reused_candidate_is_not_publication_live_binding | 真实两代same-content/旧source candidate复用，callback不能错误绑定历史id |
| provider_report_replay_does_not_reread_or_duplicate | None先产生真实JUnit receipt，provider重放不重读summary/本地产物；历史check_files=False仍跑 |
| replay_query_failure_and_late_expiry_cannot_return_success | query/postquery/初capture返回/末capture返回失效，冻结control |
| expiry_at_verify_transaction_and_metadata_checkpoints | 完整verify后/txn写后/metadata写后expiry均拒且还原 |
| live_code_drift_before_append_rolls_back_only_control | metadata替换后改真实CODE bytes，拒发布且只回滚control |
| append_failures_keep_original_rollback_and_completion | append前OSError rollback；已append抛错仍完成一次，重放不重复 |
| bad_chain_and_original_parameter_close_repair_controls | hash/schema各可见，原evidence/metrics/close_repair/非法candidate拒绝保持 |

替身只用于固定 provider 回应、末比较坏reason、时间点/I/O故障/spy及禁止执行的错配handler；完整 candidate/verify/业务/provenance/事务判定不 mock 结果。fresh fixture 的 binary 是明确软件字节，不是实际构建/设备证据；direct/physical字段不授native。

## 4. 串行正式实施任务

### Task 1：独立 TEST ONLY 与正式旧 RED

**Dependencies:** root全文读本文＋fresh SPEC→不同QUALITY零遗留。
**Parallelizable:** No（独立TEST作者；SOURCE尚不得落地）。

- [ ] 核970输入hash/实际HEAD和新路径不存在，保护并行dirty；仅用apply_patch将附录A新增为100644、唯一末LF，不动SOURCE/CI/旧TEST。
- [ ] AST/15方法/资产hash吻合后做独立actual TEST ONLY审查；对未改SOURCE运行精确命令：
~~~bash
python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_record_verification_provider_unit.py'); assert s.countTestCases()==15, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~

- [ ] 应见15方法：14红方法＋None1绿、28条Assertion records、0ERROR/skip、exit1。计时可异，ImportError/TypeError/fixture/loader/属性读取ERROR均不算RED；失败形状不符先停，不松断言或先改SOURCE。
- [ ] 原B1九/B2十二/B3a十二/B3b十二仍应GREEN，45方法0F/E/skip；不删除unsupported-step原负控，不迁移旧TEST。
~~~bash
python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_context_unit.py'); assert s.countTestCases()==9, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_history_unit.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_dispatch_unit.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_build_start_provider_unit.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~

- [ ] 保留完整方法/record/exit/rawlog；TEST ONLY独立审查和root复验后才Task2。本文匿名RED不是正式TDD信用。

### Task 2：不同 SOURCE 作者，仅 CP 八hunks

**Dependencies:** Task1正式语义RED＋actual TEST ONLY独立审查。
**Parallelizable:** No（SOURCE作者不同于TEST作者）。

- [ ] 完整回读handler/main、原事务helper及B2 adapter，核冻结输入；仅apply_patch附录B，不改TEST/evidence/candidate/debt/其它writer/CI。
- [ ] 全CP AST；仅 cmd_record_verification/main 变更，8hunks、helper字节不动、正向投影/唯一逆向还原原完整CP；实际hash应等§5。
- [ ] 执行Task1新15及原45全部strict命令，均0F/E/skip/exit0。再执行原 verification 7个必要节点，不运行本机完整107/full/native：
~~~bash
python -B -c "import sys,unittest; sys.path.insert(0,'tests'); names=['test_enabled_record_requires_explicit_candidate','test_device_kind_cannot_close_enabled_build_cell_with_fresh_label','test_same_request_different_candidate_conflicts_and_old_pass_cannot_hide_failure','test_cookie_candidate_paths_are_metadata_and_free_evidence_is_checked','test_event_mirror_rejects_provenance_source_forgery_and_missing_snapshot','test_direct_failure_not_overridden_by_runner_pass','test_reuse_cannot_change_device_identity']; s=unittest.defaultTestLoader.loadTestsFromNames(['test_candidate_verification.VerificationTests.'+name for name in names]); assert s.countTestCases()==7, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~

- [ ] self SPEC/QUALITY及七维检查，actualdiff/error/None/disabled/历史live绑定/末compare/事务边界全核；root fresh actualSPEC→不同actualQUALITY零遗留后才Task3。不得把匿名软件或None可运行称host已启。

### Task 3：CI一个hunk与同SHA待验候选

**Dependencies:** Task2实际双审＋必要安全/固定子仓检查。
**Parallelizable:** No（root另行精确接线与发布）。

- [ ] 仅apply_patch附录C：B3b strict12后加B3c strict15拒skip，已有tests/test_candidate*触发覆盖新文件；matrix/20min/permissions/env/依赖/触发/并发/旧门完整保留。
- [ ] 原typed20、trigger3、wire3、portable2、B1九/B2十二/B3a十二/B3b十二、legacy107及Linux shell17不减。Windows旧107=103P+4明确POSIXskip，新15必须实际15运行且零skip；subtests另账。
- [ ] root按现main-only授权精确3路径待验候选，不新branch/tag、不更新Agentpin；先必要安全检查与actual CI双审，不因本文允许提前push。
- [ ] 绑定新SHA/run/job/platform/Python/Git/collection/rawlog/footer/exit/attempt，candidate两平台及相关inspection/site必要门同SHA通过后，只闭B3c软件片。旧970九S不拼新SHAGREEN。step/inspection/final gate、C1b整体/C2/C3/C4/pin/≥90%和R2/R3继续未完成。

## 5. 冻结资产、正反投影与匿名结果

每fence正文保留唯一末LF。附录B/C为标准 unified diff，apply_patch若需要可仅规范数字hunk头为@@，增删/context字节不得自由修改。diff围栏内单空格的空context是patch语法，不是实际source尾空格；若提交守护raw diff--check报告，需逐行分类并保留原退出码，不冒称raw0。

| 资产/完整输出 | 行数 | raw SHA256 |
| --- | ---: | --- |
| A 新TEST | 432 | c6f3f59a39941b5ef6bd64cba26070d8848b5cd2b5b3a7d98cfafc67bc096e05 |
| B CP patch（8hunks） | 113 | 8484d089fa7c8de6d710a86b8c12bb3f89c47e9efd5b1b0451e15219336bc1ee |
| C CI patch（1hunk） | 11 | 15031aa5e712005e9f5e527dc519395d1e03e0fae5a19395885bdce44af414f8 |
| 完整CP投影 | 6570 | 50dcf826283ddd4a6160911babdc3e3255255024e35775b60a5629abf486b0b6 |
| 完整CI投影 | 80 | 546397d4d3a2bbaa9b6268fbd01eedaff5373e2d45f48a1918893b529f502f9d |

匿名驱动通过 SourceFileLoader.get_code 仅替换CP在RAM compile的完整投影；新TEST以准确__file__在RAM exec。finally停止loader patch，fixture清理仅TemporaryDirectory；没有实际新增Skill TEST、修改源码/CI或用户项目Git。Windows32KiB命令长度两次拒绝不是测试执行；后用RAM gzip/base64分块压缩传输，无长期log或新系统依赖。

最终A15（本节表hash）、B完整CP投影实际结果：
- 3c085d：原970，Ran15/3.562s，14红方法＋None1绿、28 Assertion records、0ERROR/skip；源码投影Ran15/4.246s，OK/0F/E/skip。驱动exit0仅表示诊断完成，正式旧strict命令应exit1。
- 659bcf/ed4baf：同一冻结SOURCE投影的原B1九/1.292s、B2十二/6.951s、B3a十二/2.646s、B3b十二/4.099s以及上述7个legacy节点/4.448s全OK/零F/E/skip。该组运行时新TEST尚为14；SOURCE投影字节未变，因此原45/7的SOURCE回归结果仍对应最终相同B资产，不冒称此组运行了最终15。
- b4ea88，从实际本文最终A15围栏回读的独立窄mutation：仅把末比较B2adapter换回直接canonical compare，单方法2条Assertion/0ERRORskip（unknown/head_history_changed精确错误文本不符，ordinary负控仍保持）；0.257s。
- 同次仅将callback绑定从初live改成input historical candidate，历史复用方法1Assertion/0ERRORskip，0.606s；仅删prior前末capture，重放方法仅replay_return1Assertion/0ERRORskip，0.236s。均RAM反例，不是生产修改/正式RED。
- 0f4cf2为inverse全部通过后发现环境无yaml模块的诊断停止，未安装。3bd5f7从实际本文围栏完成CP/CI每hunk唯一正向与逆向逐字恢复5ce5/d1cc、CP/完整TEST AST、仅两函数AST变化、事务helper完整byteequal；CI删除新增两个原缩进字段后逐字等原CI，strict15内嵌Python AST通过。签名展示围栏仅是拟议接口、非完整源码资产，AST诊断时补pass验证签名，不将它冒称可独立执行代码。没有宣称运行了缺失的YAML parser或CI。

初稿未冻结TEST曾误读ControlError.gate_id、subTest外读取未形成的assertRaises exception、build-start parser缺parameters，导致ERROR；另历史provenance tripwire一度错误拦check_files=False，已改为只拒真实重读，末compare spy只定位handler末比较。上述都属fixture错误，未计最终RED。此前14版26Assertion/0ERRORskip及14GREEN保留历史，不覆盖最终15/28记录。

最终静态结果的详细输出见作者本轮工具记录；CP/CI正反校验无需写文件。正式作者仍须按Task1/2自己保留原始日志和fresh actual双审，不用RAM结果代替。

## 6. 固定主源复用、决策与边界

本轮复用受审C1b/B3a/B3b独立研究，不再抓上游HEAD或重刷20项。固定Codex27065a91ccbf5ba8532844be3777fcf83b77820d，[LICENSE](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/LICENSE) Apache-2.0：
- 采纳 [ToolInvocation显式归属](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/tools/context.rs#L47-L80)：复用ICODE canonical/API两kwargs，不从call_id/身份字符串推导authority；验项为同对象/类/根/required逐入口spy及错配拒绝。
- 采纳 [Git结果错误分层](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/app-server/src/request_processors/git_processor.rs#L11-L34)：proof unavailable不能吞成普通diff；成本是末比较adapter和明确故障oracle，不引入第二套validator。
- 采纳 [接纳/posthook边界](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/core/src/tools/registry.rs#L783-L888)：复用原事务检查点，已执行/已append副作用不能凭事后拒绝宣称撤销。暂缓C2原生epoch/cleanup、step/inspection桥、finalgate/C3/C4。不同产品机制不直接复制源码，无新依赖、许可或权限扩张。

本文采用brainstorming的范围/替代方案收敛，已有受审C1b设计及root明确B3c批准覆盖另写DESIGN/反复询问；writing-plans提供完整资产/串行依赖/TDD门；step-gate要求检查幂等早返回与多入口精确配对。用户PLAN ONLY优先于默认worktree、frequent commit和自动执行handoff。

## 附录 A：完整新增 tests/test_candidate_record_verification_provider_unit.py

~~~python
"""B3c record-verification: real ports and bytes, software authority only."""
import contextlib
import copy
import hashlib
import inspect
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_candidate_history_unit as history

ctl, api, ev = history.ctl, history.api, history.ev


def invoke(function, *args, provider=None, required=False, **kwargs):
    # Old implementations must reach behavior, not fail on missing kwargs.
    names = inspect.signature(function).parameters
    if "git_provider" in names:
        kwargs["git_provider"] = provider
    if "require_git_provider" in names:
        kwargs["require_git_provider"] = required
    return function(*args, **kwargs)


class RecordVerificationProviderTests(unittest.TestCase):
    def fixture(self, *, enabled=True):
        f = history.HistoryTests(methodName="runTest")
        self.addCleanup(f.doCleanups)
        command = f.command
        def bootstrap(*args, **kwargs):
            return {} if args[0] == "candidate" else command(*args, **kwargs)
        with contextlib.nullcontext() if enabled else patch.object(f, "command", side_effect=bootstrap):
            f.setUp()
        return f

    def seal(self, f):
        with patch.object(f, "snapshot", side_effect=lambda: ctl.candidate_snapshot(
                f.ticket, f.meta(), base=f.base)):
            return f.seal()

    def args(self, f, candidate, request="b3c", **options):
        argv = ["record-verification", "--dir", str(f.ticket), "--kind", "device_test",
                "--outcome", "pass", "--environment", "physical",
                "--candidate-id", candidate["candidate_id"], "--device", "SN=B3c-fixture",
                "--layer", "physical", "--consumer", "camera", "--scenario", "steady",
                "--baseline", "fixture source", "--evidence", "fixture.log",
                "--request-id", request]
        args = ctl.build_parser().parse_args(argv)
        for key, value in options.items():
            setattr(args, key, json.dumps(value) if key.endswith("_json") else value)
        return args

    def call(self, args, provider=None, *, required=False, main=False):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            if main:
                with patch.object(ctl, "build_parser") as parser:
                    parser.return_value.parse_args.return_value = args
                    code = invoke(ctl.main, provider=provider, required=required)
            else:
                code = invoke(ctl.cmd_record_verification, args, provider=provider, required=required)
        return code, json.loads(output.getvalue())

    def success(self, args, provider=None, *, required=False, main=False):
        try:
            code, result = self.call(args, provider, required=required, main=main)
        except ctl.ControlError as exc:
            self.fail("protected verification must complete: " + str(exc))
        self.assertEqual(code, 0, result)
        self.assertTrue(result["ok"], result)
        return result

    def frozen(self, f, before):
        self.assertEqual(f.frozen(), before)
        self.assertFalse((f.ticket / ctl.TXN_NAME).exists())

    def build_args(self, f, request="b3c-build"):
        directory = f.code / "build"
        directory.mkdir()
        candidate = f.snapshot()
        start = f.command("build-start", "--dir", f.ticket, "--build-dir", directory,
            "--candidate-id", candidate["candidate_id"], "--parameters-json",
            json.dumps({"configure_command": ["cmake", "-S", ".", "-B", "build"],
                        "build_command": ["cmake", "--build", "build"]}),
            "--request-id", request + ":start")
        artifact = directory / "app"
        artifact.write_bytes(b"binary")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        provenance = {"start_event_id": start["event_id"], "source_candidate_id": candidate["candidate_id"],
            "configure_command": ["cmake", "-S", ".", "-B", "build"],
            "build_command": ["cmake", "--build", "build"], "compiler": "fixture",
            "architecture": "host", "artifacts": [{"path": "build/app", "sha256": digest}],
            "evidence_refs": ["build.log"]}
        args = self.args(f, candidate, request, kind="build", layer="build", device=None,
            environment="host", build_source="fresh", artifact_identity="sha256:" + digest,
            build_provenance_json=provenance)
        return args, artifact

    def test_none_cli_real_record_and_immutable_report_replay(self):
        f = self.fixture()
        directory = f.code / "build"
        directory.mkdir()
        report = directory / "junit.xml"
        report.write_bytes(b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite>')
        args = self.args(f, f.snapshot(), test_report="build/junit.xml")
        first = self.success(args, main=True)
        before = f.frozen()
        report.unlink()
        again = self.success(args, main=True)
        self.assertTrue(again["already_applied"])
        self.assertEqual(first["event_id"], again["event_id"])
        self.frozen(f, before)

    def test_provider_real_code_callbacks_and_exact_canonical_kwargs(self):
        f = self.fixture()
        candidate = f.snapshot()
        args, provider = self.args(f, candidate), self.seal(f)
        self.assertFalse((f.code / ".git").exists())
        with patch.object(ctl, "candidate_snapshot", wraps=ctl.candidate_snapshot) as capture, \
                patch.object(ctl, "verify_event_chain", wraps=ctl.verify_event_chain) as verify, \
                patch.object(ev, "validate_reuse", wraps=ev.validate_reuse) as reuse, \
                patch.object(ev, "validate_provenance", wraps=ev.validate_provenance) as provenance, \
                patch.object(ctl, "commit_metadata_and_event", wraps=ctl.commit_metadata_and_event) as publish:
            result = self.success(args, provider, required=True)
        self.assertEqual(capture.call_count, 2)
        self.assertEqual(capture.call_args_list[0], capture.call_args_list[1])
        self.assertIs(capture.call_args.kwargs["git_provider"], provider)
        self.assertIs(capture.call_args.kwargs["require_git_provider"], True)
        self.assertIs(publish.call_args.kwargs["git_provider"], provider)
        self.assertTrue(callable(publish.call_args.kwargs["before_publish"]))
        for spy in (reuse, provenance):
            self.assertTrue(spy.call_count)
            for call in spy.call_args_list:
                self.assertIs(call.kwargs["git_provider"], provider)
                self.assertIs(call.kwargs["require_git_provider"], True)
                self.assertIs(call.args[2] if spy is reuse else call.args[4], api)
        for call in verify.call_args_list:
            if call.kwargs.get("semantic") is False:
                self.assertNotIn("git_provider", call.kwargs)
            else:
                self.assertIs(call.kwargs["git_provider"], provider)
                self.assertIs(call.kwargs["require_git_provider"], True)
        run = f.meta()["verification_runs"][-1]
        self.assertEqual(run["run_id"], result["run"]["run_id"])
        row = next(x for x in run["candidate"]["manifest"] if x["path"] == "source.py")
        self.assertEqual(row["sha256"], hashlib.sha256((f.code / "source.py").read_bytes()).hexdigest())
        events, issues = invoke(ctl.verify_event_chain, f.ticket, f.meta(), provider=provider, required=True)
        self.assertFalse(issues, issues)
        self.assertEqual(events[-1]["payload"]["run_id"], run["run_id"])

    def test_main_exact_three_pairs_and_unconnected_step_reject(self):
        f = self.fixture()
        args, provider = self.args(f, f.snapshot()), self.seal(f)
        self.success(args, provider, required=True, main=True)
        for command, function in (("step", ctl.cmd_step), ("candidate", ctl.cmd_record_verification),
                                  ("record-verification", ctl.cmd_candidate), ("record-verification", lambda args, **kw: self.fail("unknown handler executed"))):
            before = f.frozen()
            forged = SimpleNamespace(cmd=command, func=function)
            code, report = self.call(forged, provider, required=True, main=True)
            self.assertEqual(code, 1, report)
            self.assertEqual(report["gate_id"], "candidate_business_propagation_pending")
            self.frozen(f, before)
        for command, function in (("candidate", ctl.cmd_candidate), ("build-start", ctl.cmd_build_start)):
            real = ctl.build_parser().parse_args(
                ["candidate", "--dir", str(f.ticket), "--phase", "inspect"] if command == "candidate" else
                ["build-start", "--dir", str(f.ticket), "--build-dir", str(f.code / "later"),
                 "--candidate-id", f.meta()["candidate_tracking"]["current"]["candidate_id"],
                 "--parameters-json", "{}", "--request-id", "still-build"])
            with patch.object(ctl, "build_parser") as parser, patch.object(ctl, function.__name__, return_value=0) as allowed:
                real.func = allowed
                parser.return_value.parse_args.return_value = real
                invoke(ctl.main, provider=provider, required=True)
                self.assertIs(allowed.call_args.kwargs["git_provider"], provider)

    def test_missing_wrong_root_foreign_class_and_falsey_reject(self):
        f = self.fixture()
        args, provider = self.args(f, f.snapshot()), self.seal(f)
        foreign_api = history.load("b3c_foreign", "icode_control.py").candidate_module()
        class Foreign(foreign_api.CandidateGitProvider):
            workspace = f.code
            def assert_context(self): return None
            def query(self, request, *, limit): raise AssertionError("foreign query")
        for supplied, required in ((None, True), (object(), True), (Foreign(), True), (provider, 0), (provider, [])):
            before = f.frozen()
            with self.subTest(provider_type=type(supplied).__name__, required=required):
                with self.assertRaises(ctl.ControlError) as caught:
                    self.call(args, supplied, required=required)
                self.assertEqual(caught.exception.report()["gate_id"], "candidate_provider_context")
                self.frozen(f, before)
        provider.workspace = f.control
        with self.assertRaises(ctl.ControlError) as caught:
            self.call(args, provider, required=True)
        self.assertEqual(caught.exception.report()["gate_id"], "candidate_provider_context")
        provider.workspace = f.code

    def test_real_disabled_contract_rejects_missing_and_invalid_candidate_without_live(self):
        for candidate_id in (None, "0" * 64):
            f = self.fixture(enabled=False)
            candidate = ctl.candidate_snapshot(f.ticket, f.meta(), base=f.base)
            args = self.args(f, candidate)
            args.candidate_id = candidate_id
            self.assertNotIn("candidate_tracking", f.meta())
            provider, before = self.seal(f), f.frozen()
            with self.subTest(candidate_id=candidate_id):
                with self.assertRaises(ctl.ControlError) as caught:
                    self.call(args, provider, required=True)
                self.assertEqual(caught.exception.report()["gate_id"], "candidate_provider_context")
                self.assertIn("candidate tracking required", str(caught.exception))
                self.frozen(f, before)
                self.assertNotIn("candidate_tracking", f.meta())
            f.doCleanups()

    def test_pending_never_recovers_even_with_invalid_context(self):
        f = self.fixture()
        args, provider = self.args(f, f.snapshot()), self.seal(f)
        pending = f.ticket / ctl.TXN_NAME
        pending.write_bytes(b"pending must survive\n")
        before = f.frozen()
        with patch.object(ctl, "recover_pending_transaction", side_effect=AssertionError("recovery called")):
            for expired, gate in ((True, "candidate_provider_context"), (False, "candidate_transaction_pending")):
                provider.expired = expired
                with self.subTest(expired=expired):
                    with self.assertRaises(ctl.ControlError) as caught:
                        self.call(args, provider, required=True)
                    self.assertEqual(caught.exception.report()["gate_id"], gate)
        self.assertEqual(pending.read_bytes(), b"pending must survive\n")
        self.assertEqual(before, f.frozen())

    def test_fresh_build_keeps_real_provenance_and_second_capture(self):
        f = self.fixture()
        args, artifact = self.build_args(f)
        provider = self.seal(f)
        with patch.object(ctl, "candidate_snapshot", wraps=ctl.candidate_snapshot) as capture:
            self.success(args, provider, required=True)
        self.assertEqual(capture.call_count, 3)
        self.assertEqual(capture.call_args_list[0], capture.call_args_list[1])
        self.assertEqual(capture.call_args_list[0], capture.call_args_list[2])
        run = f.meta()["verification_runs"][-1]
        self.assertEqual(run["build_provenance"]["artifacts"][0]["sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
        self.assertEqual(run["build_provenance"]["source_candidate_id"], args.candidate_id)

    def test_second_compare_proof_unavailable_is_not_ordinary_mismatch(self):
        f = self.fixture()
        args, artifact = self.build_args(f)
        provider, before = self.seal(f), f.frozen()
        original = api.compare_candidates
        for reason in ("unknown_future_reason", "head_history_changed", "source_or_contract_drift"):
            hits = []
            def compare(*pos, **kw):
                frame = inspect.currentframe().f_back
                while frame is not None:
                    if frame.f_code.co_name in ("validate_provenance", "validate_reuse", "event_issues"):
                        break
                    if frame.f_code.co_name == "cmd_record_verification":
                        hits.append(reason)
                        return {"equivalent": False, "reason": reason}
                    frame = frame.f_back
                return original(*pos, **kw)
            with self.subTest(reason=reason), patch.object(api, "compare_candidates", side_effect=compare):
                with self.assertRaises(ctl.ControlError) as caught:
                    self.call(args, provider, required=True)
                expected = "source candidate changed" if reason == "source_or_contract_drift" else "candidate_proof_unavailable"
                self.assertIn(expected, str(caught.exception))
                self.assertEqual(caught.exception.report()["gate_id"], "verification_evidence")
                self.assertEqual(hits, [reason])
                self.assertIsNone(provider.assert_context())
                self.frozen(f, before)

    def test_historical_reused_candidate_is_not_publication_live_binding(self):
        f = self.fixture()
        old, current, build, second, origin, later = f.linear_history()
        args = self.args(f, old, "old-origin-new-record", device=origin["device"],
            build_source="fresh", artifact_identity=build["artifact_identity"],
            reuse_json=later["reuse"], runtime_provenance_json=later["runtime_provenance"])
        provider = self.seal(f)
        self.assertNotEqual(old["candidate_id"], current["candidate_id"])
        self.success(args, provider, required=True)
        run = f.meta()["verification_runs"][-1]
        self.assertEqual(run["candidate"]["candidate_id"], old["candidate_id"])
        self.assertEqual(run["reuse"]["origin_run_id"], origin["run_id"])
        self.assertTrue(invoke(ctl.verification_applicability, f.ticket, provider=provider, required=True)["ok"])

    def test_provider_report_replay_does_not_reread_or_duplicate(self):
        f = self.fixture()
        directory = f.code / "build"
        directory.mkdir()
        report = directory / "junit.xml"
        report.write_bytes(b'<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite>')
        args = self.args(f, f.snapshot(), test_report="build/junit.xml")
        first = self.success(args)
        report.unlink()
        provider, before = self.seal(f), f.frozen()
        original = ev.validate_provenance
        def historical(*pos, **kw):
            self.assertIs(kw.get("check_files"), False, "historical artifacts reread")
            return original(*pos, **kw)
        with patch.object(ev.test_result_module(), "summarize_report", side_effect=AssertionError("historical report reread")), \
                patch.object(ev, "validate_provenance", side_effect=historical):
            again = self.success(args, provider, required=True)
        self.assertTrue(again["already_applied"])
        self.assertEqual(again["event_id"], first["event_id"])
        self.assertEqual(again["run_id"], first["run"]["run_id"])
        self.frozen(f, before)

    def test_replay_query_failure_and_late_expiry_cannot_return_success(self):
        f = self.fixture()
        args = self.args(f, f.snapshot())
        self.success(args)
        provider, before = self.seal(f), f.frozen()
        original = provider.query
        for failure in ("query", "post_query", "capture_return", "replay_return"):
            calls = []
            def query(request, *, limit):
                result = original(request, limit=limit)
                if failure == "query":
                    return api.CandidateReadResult(b"", 1, False)
                if failure == "post_query":
                    provider.expired = True
                return result
            original_capture = ctl.candidate_snapshot
            def capture(*pos, **kw):
                result = original_capture(*pos, **kw)
                calls.append(1)
                if failure == "capture_return" or (failure == "replay_return" and len(calls) == 2):
                    provider.expired = True
                return result
            with self.subTest(failure=failure), patch.object(provider, "query", side_effect=query), \
                    patch.object(ctl, "candidate_snapshot", side_effect=capture):
                with self.assertRaises(ctl.ControlError):
                    self.call(args, provider, required=True)
            provider.expired = False
            self.frozen(f, before)

    def test_expiry_at_verify_transaction_and_metadata_checkpoints(self):
        for checkpoint in ("verify", "txn", "metadata"):
            f = self.fixture()
            args, provider = self.args(f, f.snapshot()), self.seal(f)
            before, original_write, original_verify = f.frozen(), ctl.atomic_write_json, ctl.verify_event_chain
            def write(path, data):
                result = original_write(path, data)
                if (checkpoint == "txn" and Path(path).name == ctl.TXN_NAME) or \
                        (checkpoint == "metadata" and Path(path).name == ctl.METADATA_NAME):
                    provider.expired = True
                return result
            def verify(*pos, **kw):
                result = original_verify(*pos, **kw)
                if checkpoint == "verify" and kw.get("semantic") is not False:
                    provider.expired = True
                return result
            with self.subTest(checkpoint=checkpoint), patch.object(ctl, "atomic_write_json", side_effect=write), \
                    patch.object(ctl, "verify_event_chain", side_effect=verify):
                with self.assertRaises(ctl.ControlError):
                    self.call(args, provider, required=True)
            provider.expired = False
            self.frozen(f, before)
            f.doCleanups()

    def test_live_code_drift_before_append_rolls_back_only_control(self):
        f = self.fixture()
        args, provider = self.args(f, f.snapshot()), self.seal(f)
        before, original = f.frozen(), ctl.atomic_write_json
        changed = b"value = 72\n"
        def write(path, data):
            result = original(path, data)
            if Path(path).name == ctl.METADATA_NAME:
                (f.code / "source.py").write_bytes(changed)
            return result
        with patch.object(ctl, "atomic_write_json", side_effect=write):
            with self.assertRaises(ctl.ControlError) as caught:
                self.call(args, provider, required=True)
        self.assertIn("source candidate changed", str(caught.exception))
        self.frozen(f, before)
        self.assertEqual((f.code / "source.py").read_bytes(), changed)

    def test_append_failures_keep_original_rollback_and_completion(self):
        f = self.fixture()
        args, provider = self.args(f, f.snapshot()), self.seal(f)
        before, original = f.frozen(), ctl.append_prepared_event
        with patch.object(ctl, "append_prepared_event", side_effect=OSError("before append")):
            with self.assertRaises(OSError):
                self.call(args, provider, required=True)
        self.frozen(f, before)
        def append_then_raise(*pos, **kw):
            original(*pos, **kw)
            raise OSError("after append")
        with patch.object(ctl, "append_prepared_event", side_effect=append_then_raise):
            first = self.success(args, provider, required=True)
        after = f.frozen()
        again = self.success(args, provider, required=True)
        self.assertEqual(first["event_id"], again["event_id"])
        self.assertEqual(len(f.meta()["verification_runs"]), 1)
        self.frozen(f, after)

    def test_bad_chain_and_original_parameter_close_repair_controls(self):
        f = self.fixture()
        args, provider = self.args(f, f.snapshot()), self.seal(f)
        original = ctl.read_events
        for corruption in ("hash", "schema"):
            before = f.frozen()
            def read(*pos, **kw):
                events, detail = original(*pos, **kw)
                events = copy.deepcopy(events)
                if corruption == "hash":
                    events[0]["event_hash"] = "0" * 64
                else:
                    events[0]["schema_version"] = 99
                return events, detail
            with self.subTest(corruption=corruption), patch.object(ctl, "read_events", side_effect=read):
                with self.assertRaises(ctl.ControlError) as caught:
                    self.call(args, provider, required=True)
                self.assertEqual(caught.exception.report()["gate_id"], "event_chain")
                self.frozen(f, before)
        for updates, gate in (({"evidence": ""}, "verification_evidence"),
                              ({"metrics_json": '{"fps":true}'}, "verification_metrics"),
                              ({"close_repair": True}, "close_repair_state"),
                              ({"candidate_id": "0" * 64}, "verification_evidence")):
            before = f.frozen()
            altered = copy.copy(args)
            for key, value in updates.items():
                setattr(altered, key, value)
            with self.subTest(updates=updates):
                with self.assertRaises(ctl.ControlError) as caught:
                    self.call(altered, provider, required=True)
                self.assertEqual(caught.exception.report()["gate_id"], gate)
                self.frozen(f, before)


if __name__ == "__main__":
    unittest.main()
~~~

## 附录 B：不同SOURCE作者未来实施CP patch

~~~diff
--- a/tools/icode_control.py
+++ b/tools/icode_control.py
@@ -4438,8 +4438,10 @@
     return 0
 
 
-def cmd_record_verification(args):
+def cmd_record_verification(args, *, git_provider=None, require_git_provider=False):
     out_dir = Path(args.dir).resolve()
+    access = ({"git_provider": git_provider, "require_git_provider": require_git_provider}
+              if _candidate_access_requested(git_provider, require_git_provider) else {})
     if args.close_repair and not args.request_id:
         raise ControlError(
             "--close-repair 必须提供 --request-id，避免关闭恢复记录被重复追加",
@@ -4509,6 +4511,14 @@
         optional_fields[field] = verification_json(getattr(args, field + "_json"), "--" + field.replace("_", "-") + "-json")
     input_payload.update({key: value for key, value in optional_fields.items() if value is not None})
     with DirLock(out_dir):
+        if access:
+            probe = load_metadata(out_dir)
+            _candidate_context_guard(out_dir, probe, git_provider, require_git_provider)
+            if not verification_evidence_module().enabled(probe):
+                raise ControlError("candidate tracking required", gate_id="candidate_provider_context")
+            if (out_dir / TXN_NAME).exists():
+                raise ControlError("provider transaction recovery is not enabled",
+                                   gate_id="candidate_transaction_pending")
         recover_pending_transaction(out_dir)
         meta = load_metadata(out_dir)
         require_vnext(meta, out_dir)
@@ -4525,7 +4535,7 @@
             raise ControlError(
                 "--close-repair 仅用于 close_state=close_planned 的归档前证据恢复",
                 exit_code=1, gate_id="close_repair_state")
-        events, problems = verify_event_chain(out_dir, meta)
+        events, problems = verify_event_chain(out_dir, meta, **access)
         if problems:
             raise ControlError("现有事件链不完整，拒绝记录验证", exit_code=1,
                                gate_id="event_chain", violations=problems)
@@ -4534,7 +4544,7 @@
             if evidence_api.enabled(meta):
                 if args.environment is None:
                     raise evidence_api.EvidenceError("enabled verification requires explicit --environment")
-                live = candidate_snapshot(out_dir, meta, events=events)
+                live = candidate_snapshot(out_dir, meta, events=events, **access)
                 input_payload["candidate"] = evidence_api.resolve_candidate(args.candidate_id, meta, events, live, candidate_module())
             elif args.candidate_id is not None:
                 raise evidence_api.EvidenceError("candidate-id requires an explicitly enabled candidate contract")
@@ -4553,7 +4563,7 @@
                     input_payload["test_summary"] = report_api.summarize_report(report, workspace)
             prior_runs = evidence_api.event_runs(events)
             evidence_api.validate_supersedes(input_payload, prior_runs)
-            evidence_api.validate_reuse(input_payload, prior_runs, candidate_module())
+            evidence_api.validate_reuse(input_payload, prior_runs, candidate_module(), **access)
             evidence_api.validate_direct(input_payload)
             evidence_api.validate_test_summary(input_payload)
             # Idempotent replay checks stored inputs before re-reading outputs:
@@ -4564,16 +4574,32 @@
                 # Exact replay is a historical receipt, not a new observation.
                 evidence_api.validate_direct(input_payload, strict_outcome=True)
                 evidence_api.validate_provenance(input_payload, meta, events, execution_workspace(out_dir, meta), candidate_module(),
-                                                live_candidate=live if evidence_api.enabled(meta) else None)
-                if evidence_api.enabled(meta) and args.kind == "build" and args.build_source == "fresh" and args.outcome == "pass" \
-                        and not candidate_module().compare_candidates(input_payload["candidate"], candidate_snapshot(out_dir, meta, events=events))["equivalent"]:
-                    raise evidence_api.EvidenceError("source candidate changed while verifying build artifacts")
+                                                live_candidate=live if evidence_api.enabled(meta) else None, **access)
+                if evidence_api.enabled(meta) and args.kind == "build" and args.build_source == "fresh" and args.outcome == "pass":
+                    if access:
+                        proof = evidence_api._compare_candidates(
+                            input_payload["candidate"], candidate_snapshot(out_dir, meta, events=events, **access),
+                            candidate_module(), **access)
+                    else:
+                        proof = candidate_module().compare_candidates(
+                            input_payload["candidate"], candidate_snapshot(out_dir, meta, events=events))
+                    if not proof["equivalent"]:
+                        raise evidence_api.EvidenceError("source candidate changed while verifying build artifacts")
         except (evidence_api.EvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
             raise ControlError(str(exc), exit_code=1, gate_id="verification_evidence") from exc
         prior = find_idempotent_event(
             events, args.request_id, "verification_recorded", input_payload,
             payload_keys=(*input_payload, "test_summary"))
+        def before_publish():
+            # Bind this invocation's live source, not a permitted historical origin.
+            current = candidate_snapshot(out_dir, meta, events=events, **access)
+            if current["candidate_id"] != live["candidate_id"]:
+                raise ControlError("source candidate changed before verification publication",
+                                   gate_id="verification_evidence")
+            _candidate_context_guard(out_dir, meta, git_provider, require_git_provider)
         if prior:
+            if access:
+                before_publish()
             print(json.dumps({"ok": True, "already_applied": True,
                               "request_id": args.request_id,
                               "run_id": prior["payload"].get("run_id"),
@@ -4587,7 +4613,8 @@
         meta["verification_runs"] = runs
         event = commit_metadata_and_event(
             out_dir, before_meta, meta, "verification_recorded", run,
-            request_id=args.request_id)
+            request_id=args.request_id,
+            **(dict(access, before_publish=before_publish) if access else {}))
     print(json.dumps({"ok": True, "run": {key: value for key, value in run.items() if key != "candidate"}, "event_id": event["event_id"]},
                      ensure_ascii=False, indent=2))
     return 0
@@ -6508,7 +6535,8 @@
         access = ({"git_provider": git_provider, "require_git_provider": require_git_provider}
                   if _candidate_access_requested(git_provider, require_git_provider) else {})
         if access and not ((args.cmd == "candidate" and args.func is cmd_candidate) or
-                           (args.cmd == "build-start" and args.func is cmd_build_start)):
+                           (args.cmd == "build-start" and args.func is cmd_build_start) or
+                           (args.cmd == "record-verification" and args.func is cmd_record_verification)):
             raise ControlError("B1 command dispatch is not enabled", gate_id="candidate_business_propagation_pending")
         # 捕获子命令输出：业务失败（ok=false）时子命令仍可能返回 0，
         # 会让 shell 的 `&&` / `set -e` 误判为成功。此处统一纠正为退出码 1。
~~~

## 附录 C：root未来实施CI patch

~~~diff
--- a/.github/workflows/candidate-provider-software.yml
+++ b/.github/workflows/candidate-provider-software.yml
@@ -64,6 +64,8 @@
         run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_dispatch_unit.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Candidate B3b build-start software contract
         run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_build_start_provider_unit.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
+      - name: Candidate B3c record-verification software contract
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_candidate_record_verification_provider_unit.py'); assert s.countTestCases()==15, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Syntax
         run: python -B -m py_compile tools/icode_candidate.py tests/test_candidate_git_provider_unit.py
       - name: Collect complete related legacy contract
~~~

## 【架构级自检报告】

- ✅ 语法/编译：完整TEST/CP投影AST、strict命令AST通过；CI仅原层级两字段插入/精确逆向，不冒称未安装YAML parser或native编译。
- ✅ 依赖/调用链：精确第三配对→同canonical verify/capture/reuse/provenance→B2末比较→原commit/before_publish，纯prepare不跳业务验证。
- ✅ 逻辑/边界：真实disabled两例、None、历史candidate与本次live分离、重放/初末capture/expiry、proof与ordinary错误均有oracle。
- ✅ 异常处理：pending不恢复；hash/schema/参数/close_repair原拒绝保留，append前rollback与已append完成分账；最终旧RED零ERROR。
- ✅ 关联模块：未来仅三路径，旧45/7及线上107门保留，其它writer/step/inspection/finalgate仍pending；并行dirty和Agentpin不动。
- ✅ 兼容安全：None原端口/报告receipt语义及helper字节不变；无模型/env/CLI身份、raw Git fallback/新权限/依赖/宿主假授权。
- ✅ 可运行性：完整冻结资产、正反唯一投影和匿名15/45/7及窄mutation均已记录；正式TEST→不同SOURCE、实际双审/同新SHA线上仍待，不授100%/native/C1b整体/C2/R2/R3。

---

**Execution Mode:** serial。PLAN ONLY；本轮唯一写入本文。root全文回读、fresh SPEC→不同QUALITY零遗留前，不调用执行技能、不派正式TEST、不stage/commit/push。
