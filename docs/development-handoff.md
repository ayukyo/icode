# R2 / R3 开发接力

更新：2026-10-14（北京时间）。已在 Windows / WSL2 接力续跑；下列历史发布及线上结果只授其实际候选证据，不作为本轮新增能力验收。

当前权威工作区：`/home/orbbec/projects/icode`（Windows可读 `\\wsl.localhost\Ubuntu-22.04\home\orbbec\projects\icode`）。用户已授权将开发工作区迁到此WSL原生目录，原 `D:\Projects\icode` 及其67个Junction保留不清理。以下旧日志只授其实际结果；当前交付顺序以本节线上优先约定为准，不借旧诊断副本的clean替代检查。

## 当前交付顺序：线上优先（2026-10-13 用户明确确认）

### 2026-10-14 最新终态与接续（优先于下方在途历史）

- 下一Agent待验收候选仅九路径：诊断driver/新TEST、provenance预算workflow/新TEST、三份最小计划及live/handoff。两实现片实际freshSPEC→不同QUALITY均C0/I0/M0；root已独立API重核b8所有55 job终态（48主CI/5签装/2Pages）、无active，秘密与固定子仓原单门通过58ec67，五文档链接扫描raw0。未混入C1a尚未过审草稿、未创建limit.c；stage/新SHA线上结果待收，不称阶段完成。

- 最新Skill已推送 `29634bc70cf0bcf6837bb0bbf5997641c73e6e71`：五路径11+/1-，root实际native Windows1个rooted测试RED→新8 GREEN、Linux新8及安装1 GREEN，freshSPEC→不同QUALITY各C0/I0/M0，五文件AST/秘密/精确索引及100644通过，无branch/tag/force。线上software `38498758288` Linux `115640454159` 已通过provider9/new8/旧162（99.26s）及两shell；Windows `115640453739`旧162在途；site `38498758246` 安装23项/3.774s已通过，整体部署终态待收，不预报完整兼容通过。
- 最新Agent诊断实际driver `01814ba4…`、TEST `d27d3ad2…`已实施，正式原测试/CI/controller等六资产逐字不变，limit.c仍不存在。root fa2303实际Linux9/.328s/0F/Eskip；SOURCE freshSPEC C0/I0/M0，不同QUALITY在途。原生两格只用于补第一失败点观察；不授quota。预算workflow25分钟片已独立双审0，软件6项通过，不改签装权限与命令。b8三主工作流全部终态（CI失败、provenance实际5/5成功、Pages成功），后续候选不会抢停旧证据。
- C1a修订45c385旧JSON/deadline缺陷在计划层关闭，freshSPEC另发现Windows typed manifest可接受drive-relative/rooted/ADS三种路径；作者继续仅修PLAN，生产candidate仍c3a15e。该本机草稿尚未进入提交，不提供线上悬空链接，也不因计划投影测试通过解冻。合法HEAD刷新/LFS/host/C1b–C4和最终90%门继续开放。

- Mac诊断修订PLAN `ad54f89…` freshSPEC→不同QUALITY已C0/I0/M0，root全文9d5365；实际新TEST作者及root各运行4方法/5条DIAGNOSTIC_EMITTER_ABSENT AssertionError/零ERROR或skip（末方法2个subTest），不虚报4条failure。root5fc5ab实际/.002s，TEST `d27d3ad2…`逐字等批准fence，driver仍32089c；作者原日志`/home/orbbec/macos-m0a1-task1-red.cg4NY9/unittest.log` SHA`e6076cf3d8042a062b7d0a219fe3ad22b1bf56142992744f444ea76df401382a`。仅Task1 TEST完成，可交不同SOURCE作者应用诊断patch；不是quota或nativeRED，limit.c仍不存在。

- 新计划审查没有绕过：Mac诊断PLAN旧 `0e3e7d…` SPEC零问题后，不同QUALITY发现I1，恢复默认SIGPIPE后的stderr brokenpipe可能改变原_exit路径；root已核Apple官方pipe(2)，作者仅修PLAN加入真实断管负控及必终止失败路径的最小保护，不改已发布driver。C1a旧 `abebb0…` freshSPEC C0/I2/M0：FACTS JSON重复字段会后值覆盖；LINEAR和最后TREE可消耗超出30秒仍等价。作者仅修PLAN资产递归拒重复与固定deadline/前后检查、真实负控；实施仍禁止，待修订重新双审。审查的RAM运行不是正式产品实施或native信用。

- b8cc 主 CI 已 48/48 终态：41 success、4 failure（两 Mac M0a1 基础设施、两 Windows Reviewer）、3 退役 skip；Python3.11 `115631154603` 3274/752.799s/OK(skip93)，3.12 3274/865.042s/OK(skip93)。provenance validate `115631154968` 在旧15分钟预算下成功，四真实签装 consumer 尚在途；因此25分钟改动只能称韧性余量，不能宣称修好了本候选超时。Pages 已成功，仍不算整体通过。新 Agent push 必须等四签装终态，避免旧 cancel-in-progress 抢停。
- Skill1bc Linux `115633567798` success：provider9/.131s、新compat7/1.222s、旧162/97.21s 均通过，crosscheck shell17passed0failed；Windows旧回归当时在途，后续失败见上节。单平台成功不授完整兼容验收。macOS 仅诊断[完整计划](nbl/plans/2026-10-14-macos-m0a1-harness-diagnostics.md)0e3e7d当时已 root全文阅读+freshSPEC零问题，不同QUALITY在途；本机C1a草稿abebb0当时已root全文阅读+freshSPEC在途，源码未实施。当前状态以上方后续审查为准。

- Skill 新候选软件 run `38496567720` / site `38496567735` 已触发，双平台旧回归待线上，不将本机专项当兼容片完成。Agent 签装 validate 原15分钟取消现已核实际15m04s，预算耗尽为强解释而非API确认；新独立[有限预算计划](nbl/plans/2026-10-14-provenance-validation-budget.md) 已TDD RED3/1assert→GREEN6/0F/Eskip，唯一workflow差分validate15→25，完整预检/权限/签装均不变。实际独立审查与新SHA线上验收待，不在b8全终态前push以免触发旧并发取消。

- Skill 兼容片已推送候选 `1bc464ca69cbcaac10ec0514c20aa7a66ebc6cd9`。本片先精确 13 路径提交 `d497b4547b94daaf2c48b41b312cd8a18af99f9f`（双审零问题，root Linux 16 项和 Windows 7 / 9.768s 全通过），首次推送被远端新增提交拒绝。只读核远端 `217ae04facbac9ea6e50fb09bc12e71682ca7976` 的 19 路径无重叠，随后常规非快进 merge 保留两父历史；实际 32 路径并集逐字等于双方原提交，clean，合并后新 7 / 1.226s 与 provider 9 / .116s 全通过，再推送成功。没有 force/reset/rebase、新分支或标签；远端新增 doc_snapshot/MCP 内容不因合并自动授整 pin 验收，最终升级清单须重算，vendor 仍 21566a5。
- b8cc 原生 M0a1 两格编译链接成功，但 driver exit2，不是 RED。Intel job `115631154807` / artifact `11862864535`：macOS15.7.9/24G830/kernel24.6.0，binary SHA `33b022091cacb7e84417085021ad7568f566fee88df75f2242017a4bd4ce5c37`；ARM job `115631154655` / artifact `11862819665`：26.6.2/25G83/kernel25.6.0，binary SHA `e3b54c2e652f5f67d6dfc2305fffa4acbc5635f8673e60c77df19d5822246c3b`。root 独立纯内存读取两 ZIP 原始 metadata/stdout/stderr：七 case 均 released0，末个 receipt_loss 无确认，`receipt-loss-requires-real-exec errno60 / cleanup=unknown`。stdout 两格相同 SHA `5475848ccb56d45c0c11971d9cb6d0db561f264175a3f02e16ac424d1ccb1814`；stderr Intel `b72430269686a25bd7ab9a2a355a93b0ced5414fad1ce2eaf920cf32eb5a96e2`、ARM `d4685618a7193bd094d8126f94831d7eb6b4264090a8405ff3a3f79862124123`。不把末尾 ambient errno 当最早故障原因；待最小 stderr 边界诊断，SOURCE limit.c 继续禁止。
- 故障基线（bug-investigation-baseline-checklist）：identity 为上述 GitHub 虚拟 runner，物理序号/MAC unknown，不冒称设备验收；time_window 为 run38495800553/attempt1 对应两 job，精确起止待原 job metadata，时钟偏移 unknown；runtime/analysis 均 b8cc 冻结七资产，verification 新诊断尚无；artifact_identity 为上列架构/OS/二进制摘要，临时 root fixture 保留、非产品安装；evidence_sources 为官方 artifact ZIP 内原始 bounded raw、truncatedfalse，支持未放行事实；unresolved 为首 configured/ready/read/wait 分支未导出，由下一诊断候选补齐。conclusion_ceiling=observation_only：任务未放行为 fact，getdtablesize/signal/Seatbelt 等仅候选路径，quota 原语及修复均 unobserved。root 实际 sequential-thinking 三步 e9e8eb 已完成需求分解、方案与风险，不冒称 MCP 配置存在就是调用成功。

- macOS TESTOnly 已提交推送 `b8cc1e737587fc4b40b3ed2bc167b045d51bc03f`（父 53dc），精确 9 路径与 100644 模式、索引字节/cached whitespace/秘密/pin/site/governance 均通过；首次 add 返回 ignored docs 的非零，随后显式 tracked docs add -u 和完整 9 路径索引核验通过，未使用 force。线上 CI `38495800553`、provenance `38495800566`、Pages `38495800547` 已触发 queued，尚无原生终态；不创建 branch/tag、未实施 limit.c。
- Skill 兼容片当前实际 fresh SPEC C0/I0/M0（3 SOURCE RAM 重构、7 fixture 61 hunk逐字相等、原断言/test IDs 保留、2新 TEST 等于 PLAN），不同 QUALITY 在途。CI 摘要 `fd0d50eb32ad9ad2c3c0b58f4e4965ccad0497977b9f0ac45e6c804ed77fc294`：Windows诊断一分钟、旧 162 项完整 collect-only与原回归不删减。root 13 路径秘密规则、12 Python AST、diff-check通过，不授线上旧回归终态。
- candidate/delivery 补充 DESIGN `5abe4a4…` fresh SPEC→不同 QUALITY 已 C0/I0/M0；前置 `95199a0…` 不变，仅放行后续完整实施计划设计，不提前实现或更新 pin。标准 LFS 与合法 HEAD 刷新仍是整体阻塞项。

- Agent `53dc58ec1241495f4701662d01a530a17336c898` 三个工作流均已终态。CI [38444724409](https://github.com/ayukyo/icode/actions/runs/38444724409) 为 41 成功、2 Windows Reviewer 失败、3 退役条件跳过；Pages [38444724198](https://github.com/ayukyo/icode/actions/runs/38444724198) 成功；provenance [38444724218](https://github.com/ayukyo/icode/actions/runs/38444724218) 为 validate 取消、签装模板跳过，取消原因未知。本轮未取消或重跑以掩盖失败。
- 同 SHA 全量 Python 3.11 job `115460007396`：3264 / 834.206s / OK(skip88)；3.12 job `115460007528`：3264 / 611.860s / OK(skip88)，compile/full/secrets/pin 均成功。macOS 既有 lifecycle Intel `115460007395`、ARM `115460007464` 成功；均不是新增 M0 配额或安装验收。
- Windows Reviewer x64 `115460007402`、ARM `115460007624`：SDK ABI 各 10 项通过；管理员实际 payload 的历史采集 `status=complete / returned=0 / matched=0 / attribution=no_match`，helper/进程退出与清理成功。普通用户独立订阅仍 API5。候选连接仍 `10035 / wait_expired=true / connect_denied=false`，正控 `105 / ipv4_connect_timeout / inconclusive`。只证明新增观察链运行，不能把无匹配事件或超时当 DENY。provenance `115460006093` 仅 signed fixtures 9 项通过，后续验证取消，四动态 consumer 未执行，不能借旧候选的签装结果。
- Skill `4d9b07616f3f8c7e3d39e73b6da3494b44799392` 软件 CI 已失败终态：Linux 旧 162 项通过、crosscheck shell 缺 rg；Windows 74 fail / 88 pass。当前最小兼容修复及 7 旧 fixture 保留在原生子仓工作树，root 实际新 7 项 / 1.955s 与 provider 9 项 / .123s 均零失败、错误、跳过；fresh 实际源码审查与线上回归未完成。CI 补 Linux ripgrep、7 项 stdlib、旧 162 收集清单及有界 Windows 启动/路径诊断，不先猜 SystemRoot 或放宽身份校验。固定 vendor 仍 `21566a5`，尚不更新。
- macOS TESTOnly 六资产及新增双架构 CI 已接线，root portable 5 项 / .001s / 零失败、错误、跳过；最终只读审查在途。`native/mac/icode_m0a1_limit.c` 仍不存在。下一候选先在线证明 Intel 与 ARM 正控及真正配额断言 RED，编译错误、ERROR 或 skip 不算 RED；双格 RED 前不实施 SOURCE，TESTOnly job 通过也不算配额通过。
- 受保护 Git 上下文最小契约修复已有用户明确授权。后续 candidate/delivery 补充 DESIGN 当前 `5abe4a463800be6f21c0d931035abb3adebd18c847dbfc86c746dd896bdf8550` 正在 fresh 审查：不开放 .git，不任意执行 Git 命令，不用 legacy/None 绕过，不擅改 host revision；不支持的过滤属性及待合法身份刷新链仍须在整体 90% 验收前解决。
- 本机一次进程启动异常后，轻量检查实际可用内存约 4.1 GiB、可用提交约 6.2 GiB，WSL 两仓可读且专项可运行；原因未确认。未重启、关闭用户应用或更改资源配置。继续线上优先，原 D 盘与链接保留。

【架构级自检报告】（本次接续，非 R2/R3 整体验收）

- 语法/编译：上述软件专项通过；新增 macOS C 编译须线上实证。
- 依赖/调用链：旧测试入口保留，固定子仓未升级，受保护上下文尚未接通。
- 逻辑/边界：区分 payload、管理员探针和普通订阅；无事件不等于 DENY。
- 异常处理：保留失败、取消和未知原因，不用跳过补绿。
- 关联模块：主仓 TESTOnly 与 Skill 兼容片分开交付；原 Windows 工作区不动。
- 兼容安全：不改配额硬门槛、身份校验或产品权限，不读取模型密钥。
- 可运行性：局部软件通过；原生双架构配额、Windows Reviewer、完整安装与 R3 六步仍开放，不报告 100%。

### 先前在途记录（状态已由上节更新，保留审计历史）

- **最新 Agent 已推送候选：** `53dc58ec1241495f4701662d01a530a17336c898` 已原生提交242e92、Win Git推送0c4f10 exit0；18路径索引字节/固定vendor/CI源摘要及cached diff-check逐项通过。实际触发 [CI38444724409](https://github.com/ayukyo/icode/actions/runs/38444724409)、[provenance38444724218](https://github.com/ayukyo/icode/actions/runs/38444724218)、[Pages38444724198](https://github.com/ayukyo/icode/actions/runs/38444724198)，首次queued/in_progress/in_progress，终态与原生footer待收。未创建branch/tag，不把push叫阶段完成；不取消旧运行。
- **下一 Mac TESTOnly片：** 六新文件已逐字匹配PLAN37e485，实际SPEC→不同QUALITY各C0/I0/M0；portable协议5PASS/0skip，native类5skip未credit，SOURCE limit.c不存在，CI尚未接Mac。证据`/home/orbbec/icode-m0a1-testonly.s9qq3b29/portable-protocol.log` SHA`a248b0b7ccc2b8558bfea6c6af309b09ea21f525c526f5057f9944687562ab08`；复杂实施前root真实sequential三步19c59d。六文件明确未进入53dc候选，待独立CI接线审查、53dc所有jobs终态后另一main候选双格真正RED；正式SOURCE须两格语义RED之后。
- **后续设计与兼容片：** Skill Windows完整PLAN初版`1a654583…`已root4块全文读1205行并交fresh SPEC，不提前SOURCE；原生Windows74失败分类、已证明产品/fixture及未证实startup/binding分账。whole-pin candidate/delivery新DESIGN独立作者正起草，父真实sequential三步797c92，接现95199私有typed context/对象快照，不使用任意argv、fake.git或legacy tracking绕过。固定vendor仍21566a5，53dc没有产品Gitcontext新接线。
- **下一 Agent 待发布候选：** Windows history 九实现路径已通过实际源码 fresh SPEC→不同 QUALITY零问题，root另95/.427s/0F/E/1Linux SDK skip、源三摘要与冻结资产一致。仅本片实现和已审设计/计划/进度文档入提交；新Mac TESTOnly六文件保留工作树不入本片，CI仍只含Windows变化。秘密/固定vendor原单门通过；文档5疑似已逐一确认为T0 Python调用语法（da5df5），不是实际断链。候选尚未提交推送，不授线上SDK/native或R2/R3验收。
- **索引文档守护：** 首次18路径cached diff-check拦截P1内嵌diff的26个单空格context行；root只改文档空行表示，独立DOC审查C0/I0/M0，恢复context prefix后26hunk实际RAM重建原helper`23a42a22…`、TEST/CI未变。新P1文档`3a56ef20…`，原038审批摘要保留历史，不冒称新bytes相同。root重新秘密/固定vendor原单门均通过（8b262d/c253f7），待最终索引守护再提交。
- **最新跨仓软件候选（2026-10-14）：** Skill `4d9b07616f3f8c7e3d39e73b6da3494b44799392` 已在原生权威目录 main 提交并推送（3b5303/d51938），父 `52cb6b3`，只涉及 helper/新 TEST/新软件 CI 三路径，索引逐字节及 100644 模式核过、定向秘密规则零命中、diff-check 通过。最终 helper `c7ad6c9a…` / TEST `1efaab01…` / CI `5fd95bcd…`；3 行类型检查的 28 边界 RED→GREEN 已实跑，Linux 9/.115s、Windows 9/1.796s、零失败错误跳过，实际源码 fresh SPEC→另一 QUALITY 均 C0/I0/M0。线上 [software38441664572](https://github.com/ayukyo/icode-skill/actions/runs/38441664572) 双平台正在旧 inspection 回归，新 provider 与 syntax 两步已 success；尚未收终态/raw footer，不授片完成。Agent main 仍 `6e893f0`、vendor `21566a5`，未升级固定版本或开放宿主绑定。
- **并行计划推进：** Windows history PLAN `d9e2b8f…` 已 fresh SPEC→不同 QUALITY 均零问题，root 四块读全943行并实际 sequential 三步（08617a），仅 TEST 作者开始冻结 T0/T0b/S4，先取得语义 RED，不提前改 SOURCE。macOS M0a1 PLAN `45b033…` fresh SPEC C0/I2/M2：组权限描述及 receipt_loss 常量自证需修；root 仅把 DESIGN 组语义改为清继承 host/root 组、唯一专用 GID 且读回1组，新 DESIGN `774e33f4…` fresh 双审零问题。PLAN 作者正在修真实受控回执丢失及两个名称/只读措辞，无 native、系统账户或 CI 写入；不授 quota/ready。旧审查摘要保留历史，不冒充当前批准。
- **Skill4d9线上失败保留：** Ubuntu job115449521529 新 provider/语法/162旧 Python回归（69.90s）通过，inspection shell通过；crosscheck shell明确缺`rg`，RESULT2pass/15fail、exit1。root仅为新软件workflow增加Linux条件安装ripgrep五行，尚未提交。Windows job115449521129 旧回归实际74fail/88pass（176.44s），含source excerpt字节漂移、cp1252编解码、清空env的Python随机数初始化、execution binding路径解析等，不能泛归因provider或单一环境。新provider与syntax通过不代旧链；下一候选仍需逐因审查/精确修复，不删旧测试或条件跳过，Agentpin保持旧版。
- **Windows TEST真实RED：** T0/T0b/S4六TEST文件已按冻结资产落地，生产C/Python/CI仍无diff。root426459逐字核T0 `6ff02880…`，实际8/.048s/8AssertionFail/0ERRORskip/exit1（作者8/.053s），覆盖真实argv FALSE、BOOL2误吞、API5丢失及schema9不可接受，不把missing helper/import/compile当RED。root日志 `/tmp/icode-windows-history-root-red.syn_c8kq/red.log` SHA`a77cdaecb45308262eb326dddaad356c81a93003ae95064bc6d75d487d598c6b`；独立TEST审查在途，通过后才交不同SOURCE作者。
- **Windows TEST审查后续：** 独立TEST SPEC实际C0/I0/M0，六文件精确重放、生产三文件仍等于HEAD，并独立8/.054s/8ASSERT/0Eskip/exit1。root e4af7c核原/tmp作者及root日志现已不存在，原因未知，不把当前文件SHA重验记成功；直接工具输出的真实RED记录仍在。不同SOURCE作者已接三生产文件冻结资产，不改TEST，新证据改存/home/orbbec，尚无GREEN或SDK/native信用。macOS修订PLAN `37e4852c…` root五块全文读完（0e5868/2afa4c/ef8447/b286b7/ef6e1f），已送fresh SPEC；13围栏摘要`3c6136cd…`，仍PLAN-only。
- **后续 whole-pin 审查纠正：** 独立只读审查已确认新 candidate和submission inventory均额外要求CODE是checkout根，P1五inspection ops不能自动满足。新create先在控制根尝试tracking，binding不启用candidate；disabled review返回legacy_untracked.ok=false，但delivery总门对disabled票未必纳入该review.ok，所以下文“legacy_untracked拒绝”仅是freshness局部返回、不是所有legacy delivery阻断。HEAD改变同content还需≤64commit祖先/tree证明，现无parenthistory对象闭包不能自动授same_content_commit；必须保留commit_equivalence_unproven或另冻结有限证明合同，不能按同字节跳过复检。
- 最新已推送候选`6e893f0170b74c32d7143680636d85f400ecc7c9`（509ebc提交、77bedb推送exit0）：精确五路径，唯一workflow变化为test job预算25分钟，产品源码/vendor/其它jobs逐字不变。三个同SHA工作流全部终态：[CI38423094598](https://github.com/ayukyo/icode/actions/runs/38423094598)46项=40成功、2 Windows Reviewer失败、1未启动macOS lifecycle取消、3退役条件skip；[provenance38423094591](https://github.com/ayukyo/icode/actions/runs/38423094591)动态5/5成功；[Pages38423094589](https://github.com/ayukyo/icode/actions/runs/38423094589)2/2成功。没有rerun/cancel/dispatch；下面具体结果不授整体验收。
- 新预算同SHA两条full suite已实际取原footer：Python3.11 job115385294569为3256 / 829.560s / OK(skip88)，3.12 job115385294614为3256 / 865.497s / OK(skip88)，compile/full/secrets/submodule全部成功。Win directory x64 job115385294850和ARM64 job115385295028各57 run/0失败错误。两个Reviewer job115385294904/115385295105仍10035+等待超时、connect_denied=false，private正控105/ipv4_connect_timeout，不算DENY。macOS lifecycle job115385294761从queued取消，runner_id=0、name空、steps=[]，无运行日志；取消原因未知，不算PASS。四签装115392510856/115392511069/115392511184/115392511280全部observation_complete=true，但owner_untrusted拒绝、launch/protected/compatibility=false、逆序回收确认，不授UAC。
- Linux S2c最终PLAN `ada70a2b5514ab9936cb64fa1a0f8156830810feaaacd405c22f9f05bf0ea5ae` fresh SPEC C0/I1/M0未通过：正常路径缺固定SKILL必需code_worklist，真实finish不能success/clear。进一步静态核发现隔离代码根没有.git，固定SKILL inspection._repo仅找根内.git，导致coverage partial，即使真实prepare/read/check也不能闭合。不能放弃clear正控、假造.git、allow_incomplete或patch CPsuccess。用户已明确授权最小宿主绑定受保护Git上下文契约修复、针对性验收后推送子仓main并更新固定版本；授权不是验收通过。
- 新跨仓DESIGN候选[d41方案](nbl/specs/2026-10-13-host-inspection-git-context-design.md)已提交独立SPEC审查，之后须由不同审查者做QUALITY。真实sequential-thinking三步已执行（1f623d）：区分当前代码与受保护元数据、限定provider及全消费者传播、审查漂移/重放/清理负控。当前仅设计，没有新增产品API或更新vendor。Skill开发源为干净原生`/home/orbbec/projects/icode-skill`、基线`52cb6b3f0229bfc16e6faf00ce5dd2506e252a22`，来自本地Git对象克隆；远端freshness及相对固定21566a5的升级范围尚须确认。原D子仓用户改动未复制、提交或清理。
- d41独立SPEC实际C0/I4/M0：遗漏assess内部重建/删除文件历史证据、共享源仓对象库不能由host锁冻结、HEAD初次解析与pinned重建的可比snapshot定义不清、gitlink整体升级与“仅批准文件”说法矛盾。作者正在统一修订，SOURCE仍未开始；不把方向合理记为审查通过。root实际8dfb2d核远端Skill main=52cb；本地094168/4581fd静态核对215→52cb为66文件、+8636/-251。正常固定新main必携带这些已存在差异，需单独来源清单及兼容验收，不能用runtime manifest过滤伪装仅同步本次修复。
- 修订DESIGN `e92a0f9492489d304033deffa0ef10f04b2961481cf49c7729a0e8513f7b31f4`已由root完整UTF8读取（016178）并交原独立SPEC复审：改为有界独立Git对象闭包、稳定declaration/pinned摘要、全assess传播及Agent既有工具phase/schema适配；没有复制CODE或开放Git路径。root一次旧Skill专项基线尝试626a9e因测试依赖pytest缺失而ImportError，未执行实际方法，不计TDD RED或产品失败；不因此安装新依赖或启动本机全量，后续按正式针对性/线上验收方案执行。
- e92独立SPEC复审C0/I0/M0，四项契约问题已在设计层收束；不同QUALITY尚在执行，不授SOURCE或权限信用。首实施子片PLAN正在独立起草：Skill helper窄typed provider及全部内部消费者，保持None legacy语义；先stdlib语义RED、后不同SOURCE作者、定点GREEN/旧路径回归，再独立双审。首片不开放host binding、不更新主仓pin、不称S2c完成；FD/ledger/snapshot/Agent assess/installed native与66上游变化映射属于后续必要实施门。
- e92不同QUALITY实际C0/I1/M1：metadata输入遗漏Git attributes，可能改变删除行diff及专项检查触发；成功事件与wrapper清理失败的后续信用需明确。root另实际核Git官方attributes优先级与index回退，作者正在统一修订；不能凭SPEC零问题提前SOURCE。首helper计划继续草拟但未放行。Windows独立历史事件观察DESIGN[e16方案](nbl/specs/2026-10-14-windows-reviewer-history-observation-design.md)已由root完整读取（3ca714）并交fresh SPEC；只扩大实际payload的既有有界只读观测，不增加豁免/权限，不授DENY。
- 最新Git context DESIGN `95199a0f31fb2d1ced7ff609e41acd5167d342f84dc8105086303014e81c82fe` 已fresh SPEC→不同QUALITY各C0/I0/M0；root29431e读取有attrs段截断，0657d4完整补读，不把截断当读全。attributes输入及成功发布/清理信用已在设计层收束，首helper计划须冻结完整SOURCE patch后再双审/TEST。Windows DESIGN修订`2378f25f3a6ca91eb2de9bd1659d074da8325f7f74c34c367ff6341f966701ac`同样独立双审零问题，正在PLAN-only冻结schema/真实入口/PS日志/SDK等资产。没有新SOURCE、固定版本更新或原生通过；macOS M0a1完整资产已入其PLAN、作者自审中，M0a2/M0b仍必要且开放。
- 首helper PLAN `2ac47f1a1712c0ef7c5afc8566f1502624e7a4df39b6c8312c0133df52840a8c`1093行已由root三块读全（0d7990/365349/0310d5），包含stdlib TEST、完整422行SOURCE补丁及新Skill软件workflow。fresh SPEC C0/I2/M0：association_scopes的related分支一处漏provider，Windows嵌套scope的os.path.relpath反斜杠违反typed路径合同；当前fixture未覆盖这两项。作者正在修完整补丁和新增关联/嵌套fixture，未写SOURCE/TEST/CI或执行RED/GREEN；26hunk内存匹配及AST有效只是静态证据，不授实现信用。
- 首helper PLAN修订`038931d3af0c4f1a3b4a795caf75b661260bb09a13e00ba4e398ac1b42a7040e`1145行已独立SPEC→不同QUALITY零问题，root完整读0ee794/5148bf/8c1f17。首次b2d444读取短暂PathNotFound，同路径二次恢复且WSL仍running/caps未改（222ae3）；原因未证实，不报告文件丢失。TEST作者与root各实际正式RED8methods/6AssertionError/0ERROR/skip/exit1；root c454e6按冻结fence核TEST`0386b96acbbb4ba1b1bbb298c6ac7847d6910e22e4044fdb29ef895ca3a7a71a`逐字匹配，原helper`c81d68f03c0d1cd49b2996212424f30ae845c074b368de20b5ea33c9ad2843ab`未改。root RED日志`/home/orbbec/icode-provider-root-red.i4qlncxt/root-red.log` SHA`53a161649ef3a1c71ba507ddb845e3ea8a6845acf32754ef0f91435174bc1dde`。
- 不同SOURCE作者落原批准helper/新software workflow，helper`23a42a226a062bca6ade2c73483db8c9078e6b2f387999e3a488ed9bcf31b5e7`、workflow`5fd95bcde20a7f34d0d2e8e1065a5cbfc126ea22d357ec94c24ccec158e4da14`，TEST未改。ROOT定点Linux8/.103s/0FAIL/ERROR/skip/exit0（9ed2ea），日志root-green.log SHA`025f691be679302f792fd873a26b63da876bcd0d095427cca154dd7fa7708ab4`；本机Windows同模块8/1.874s/0FAIL/ERROR/skip/exit0（f1e075）。仅软件新单模块，不是全量/native权限/阶段完成。
- SOURCE自审再发现I1：未使用的ref/oid/path/kind假值非字符串可被当空参数接受；ROOT7f6735实际复现，按原typed合同批准最小修复，不扩大workspace规则。不同TEST作者只新增14行/28边界子测试，ROOT2ba4e3移除此增量后精确恢复旧TEST摘要；新TEST`1efaab01c9870faf7b1faef6c3cc7ce4b0471273465254b701e6991b97737bc0`冻结。ROOT721293实际新增RED9/.129s/28AssertionError/0ERROR/skip，旧8全pass；root-request-types-red.log SHA`3acd92ab8837305e2b56bf0cc67dff99e36500228354a81956ea94506105f371`。随后仅授权SOURCE三行精确字符串类型检查，尚待新GREEN/独立SOURCE双审/候选必要检查及同SHA线上门，未提交推送或更新Agentpin。
- 整体旧215→新Skill升级另有静态观察（2bc4dd/9c30ee/76c315）：52cb的candidate_snapshot调用execution_workspace再直接Git capture；capture要求真实Git checkout root，无.git时newborn可能未enable tracking，delivery_freshness会legacy_untracked拒绝。此为后续P2/P3候选/验证/交付契约需独立审查的输入，不改P1范围，不允许绕freshness或假造.git；不能仅inspection软件门通过便报告整体兼容。
- macOS专用身份DESIGN已fresh SPEC→不同QUALITY C0/I0/M0，但M0原生PLAN仍需补完整native/controller/TEST资产，persona/线程身份/外部代启动有效正控未冻结；M0a前提验证不能代完整M0或ready。XNU setgroups会把零组请求转换group0，计划采用唯一专用GID并真实读回，而非照搬Linux零组假设；尚无mac原生运行通过。
- 上一已推送候选为`e54ec8de3d0fd2dd76d1aac7d765ab1d742e2f7d`：Windows准确dot误拒最小修复及新native CI收集，精确八路径提交862b14、推送4ae780实际exit0。[CI38404554032](https://github.com/ayukyo/icode/actions/runs/38404554032)已终态：46 job为40成功、2 Windows Reviewer失败、1 Python3.12取消、3退役条件skip；[provenance38404554151](https://github.com/ayukyo/icode/actions/runs/38404554151)5/5成功，[Pages38404553952](https://github.com/ayukyo/icode/actions/runs/38404553952)2/2成功。源码候选、签装拒绝/回收及网站部署分账，不能授整体验收。
- 同SHA Windows目录job115320642194（x64）和115320642635（ARM64）各实际57 tests / 0失败、错误，包含新模块10方法及两个native正控。Python3.11 job115320641465实际3253 / 761.039s / OK(skip88)，compile/full suite/secret/submodule全部成功；3.12 job115320641589在15m14s取消，无完成footer，后续secret/submodule跳过。全量作业时限不足是最强解释而非API确认原因；下一机械候选只将test job预算15→25分钟，测试/任务/安全预算不变，见[执行记录](nbl/plans/2026-10-13-full-suite-ci-budget.md)。本机新增合同测试有效RED3项1断言失败，GREEN25项无失败、错误或skip，不默认本机全量。
- WSL曾停止并报HCS/ERROR_NO_SYSTEM_RESOURCES，权威UNC不可访问。2026-10-13用户明确授权新增`C:\Users\orbbec\.wslconfig`：memory=4GB、processors=6、swap=2GB。启动exit0后实际3918 MiB内存、6核、2048 MiB swap；HEAD e54ec8d及固定vendor21566a5不变，原有两份文档改动保留。未重启Windows、关闭应用、清理数据或改用旧D副本。该限额是开发环境资源配置，不是产品任务配额或验收结果；线上优先不变。
- 当前e54所有工作流均已终态，下一候选可按原授权提交推送，不取消旧验收。并行S2c DESIGN已fresh SPEC→不同QUALITY C0/I0/M0，初版PLAN被fresh SPEC检出I4，正在修订，未获实施放行；不混入本次CI预算候选。自动准入、S3四installed矩阵与R2/R3仍开放。
- GitHub CI优先承担全量测试、跨平台及原生阶段验收，减少用户本机资源占用。Windows/WSL只做密钥、固定子仓完整性、针对性回归，以及线上无法完成的必要诊断；不默认重跑本机整套测试。
- 本机轻量门和独立审查通过后，允许将**待验收候选**提交推送main触发线上验证。推送不等于阶段完成，不创建其它分支或版本标签，不手动发布产品版本。
- 线上原日志绑定真实候选SHA/workflow/job/平台/退出状态；同SHA全量单测、secret/submodule和本片必要验收项通过后，才确认阶段完成并继续下一阶段。失败/skip/inconclusive不能当PASS，不取消或反复重跑隐藏失败。
- 此明确授权替换旧“本机全量通过后才推送”顺序。旧完整guard失败仍保留为历史；本轮不再启动新本机全量。当前两SOURCE/new TEST保持批准摘要，加入AGENTS及本接力两份流程文档后候选索引白名单为八路径。
- WSL环境包已按用户授权安装：仅dbus-user-session1.12.20-2ubuntu4.1，0升级/0删除（27bcdc）；仅reload用户unit定义并启动标准dbus.socket，原Windows及产品依赖不改。原 `TestProbe` 实际21 / 20.215s / 0 FAIL、ERROR / skip2 / exit0；原日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/native-probe-with-user-bus.log`，SHA256 `ddac53139cc8f175af6d4b37308233278d0b7e0b257f39df8bcb23cf72c836a9`。先前缺bus导致拒绝的用例现在实际通过，2skip为bwrap/mac平台条件；不授全部原生能力或R2/R3。
- 两原单门secret/submodule已在新根再次PASS（d15bdd、a3abfd）；包18项通过与源码双审/22项双份GREEN/254项回归仍有效。候选已推送，线上结果待收齐，不因这些局部结果宣称全量通过。

### 上一候选0a980e0线上观察（历史）

- 实际候选：`0a980e0130873020881a6892d88715948af909a7`，八路径索引及逐字节核对通过后提交（ac266a），已推送main（be25b8）；随后ls-remote确认线上main为同SHA（f7151d）。未新增分支、标签或产品发布。
- 同SHA的push工作流：[CI](https://github.com/ayukyo/icode/actions/runs/38398777877)、[Windows helper provenance](https://github.com/ayukyo/icode/actions/runs/38398777497)、[Public website](https://github.com/ayukyo/icode/actions/runs/38398777702)。首次实际API观察为queued / in_progress / queued，均无终态结论；不得据此勾选阶段完成。
- 五份相关文档的原一致性scanner最终两轮均0疑似项、exit0（d7d827）；首次在WSL引用不存在的skill脚本路径失败（698352），改用Windows已有原脚本复核，未修改scanner或忽略诊断。独立文档复审C0/I0/M0。
- 本节是候选推送后的接力记录，暂留本机；等待当前CI终态再随后续文档提交，避免新push取消正在运行的同SHA验收。
- 在途已确认失败：Windows Reviewer [x64 job115300703337](https://github.com/ayukyo/icode/actions/runs/38398777877/job/115300703337) 与 [ARM64 job115300703411](https://github.com/ayukyo/icode/actions/runs/38398777877/job/115300703411) 均在temporary standard-user probe断言exit78不等于0，1项测试分别45.824s、47.166s / F1。双栈Win10035等待超时不是DENY，WFP订阅error5且无matching event，privateNetwork正控exit105/ipv4_connect_timeout为inconclusive。7aad的同名两个job也存在相同机制失败（run38233104888），这是既有未通过门继续失败，不据此声称S2b2引入回归或已排除全部影响。
- x64原日志SHA256为`9eeee886167cf803b07274810769f3d43f566c4f0d30f7d21814e3ae662b7357`；完整日志含checkout认证header和机器路径，未直接写盘。安全原文失败摘录为仓外`/home/orbbec/icode-s2b2-evidence.Y3xrfh/ci-0a980e0-windows-x64-reviewer-failure-excerpt.md`，摘录SHA256 `6cf2aa4f403878488e0d229549bb1503a8edf1f06f9af4a8ab6d1ef8d7d6c5ca`，不把摘录哈希冒充完整原日志哈希。
- CI38398777877已终态failure，完整46/46为41 success、2 Reviewer failure、3 retired条件skip；两Python job的compile/full suite/secret/submodule全部success。root实际取回两原日志再次核footer：[3.11 job115300703101](https://github.com/ayukyo/icode/actions/runs/38398777877/job/115300703101)为3243 / 831.418s / OK(skip86)，[3.12 job115300702938](https://github.com/ayukyo/icode/actions/runs/38398777877/job/115300702938)为3243 / 659.383s / OK(skip86)。仅授S2b2同SHA软件门，不授skip项、新prepared installed矩阵或R2/R3整体；provenance动态新增四签装job仍待收齐，下一候选不提前push取消它们。
- ARM64安全失败摘录为仓外`/home/orbbec/icode-s2b2-evidence.Y3xrfh/ci-0a980e0-windows-arm64-reviewer-failure-excerpt.md`，摘录SHA256 `99eb2449d0539f4c5d830a840ce5fe57b2edab92df7705ec097c4581b588c96d`，原日志SHA256 `a2d6dc5905658cbef24f6d8369c3d20571ce6e540cb6ad7c9655be58b0fdcd80`，完整原日志与摘录分账。
- 该SHA所有工作流终态已收齐：provenance38398777497 success / 5 jobs（validate115300700744，签装ARM3.11 115307030947、x64/3.12 115307030999、x64/3.11 115307031099、ARM3.12 115307031282）；Pages38398777702 success / 2 jobs。四consumer原wire均observation_complete=true，helper/verifier根节点owner_untrusted导致consumer拒绝，source_policy_all_passed/compatibility_accepted/launch_authorized/protected_observed均false；两resource各13句柄确认关闭，unconfirmed0。不能以密码学/签装绿授首次UAC或受保护晋升；此条更新取代上条在途等待描述，不取消/重跑原失败。

### 下一片执行中：Windows 准确 dot 伪项

- 批准[DESIGN](nbl/specs/2026-10-13-windows-dot-entry-identity-design.md) SHA256 `e6a6ebfb734c02c6a87293140dba13a319fc38d9f1ae75e9fbaed7527df0c22b`；批准[PLAN](nbl/plans/2026-10-13-windows-dot-entry-identity.md) SHA256 `bcde3dcc144922404f555149fa5fbccaff3901e8ca5b39278cca02e7ee8d26da`。fresh SPEC与不同QUALITY均C0/I0/M0；root已完整读资产、实际调用链及真实sequentialthinking三步（9c225a）。随后已正式TEST→SOURCE实施，当前PLAN的进度和原日志追加改变文档摘要，五个代码/差分围栏逐字不变；仓外原批准bytes`windows-dotentry-plan-approved.md`已核同bcde摘要，不把原批准当当前同对象摘要。
- 新测试资产8494 bytes / SHA256 `68aacc4ebd38237ce809965c31b643d5ef690514649d7662bd5e32a1aa535c1e`，8 portable + 2 Windows native；正式RED要同时打中准确dot误拒与CI漏收集两个缺口，ROOT独立重复后才改两SOURCE。不放宽真实子项零/FF身份或任何结构/UTF16/offset/trailing边界。
- 当前候选发布白名单为本片两SOURCE、两个TEST、两新docs、live/handoff共八路径；S2c独立DESIGN仅并行技术准备，不混入此候选。原Windows链接/vendor、test_control的路径断言、ready/权限/workflow均不在本片修改范围。
- 正式TEST已由唯一作者落盘：新TEST保持批准68aacc摘要，既有safe runner TEST仅同步loader有序两模块期待，SHA256 `93c61cd3f21cfa8435dcfbe02b0f7e2282d580b0eac2da0d8724a62550215d1c`。作者与root各2方法 / 0.002s / 5有效AssertionError / 0 ERROR、skip / exit1，原日志分别`windows-dotentry-author-red.log`、`windows-dotentry-root-red.log`（仓外同证据目录），两次实际输出恰好同bytes，SHA256均`a426476f6c2fa13aef619a60cb5a228c9f4bcfc9eb5366dd2dfa5737921d71bc`。root首次捕获在exec返回运行session时误按完成解析，未保存其结果，不授RED信用；bed896实际重验与25d7cb日志才为root有效证据。
- RED时两SOURCE保持原56cdd444/04db3893，保护windows_worktree保持2fe8702b。独立确认后不同SOURCE作者仅实施两冻结差分：当前parser SHA256 `7d9826d66a5e4a045a8b304ff5eb3c09fba230fc7c5eaffa045f8826bc2cdcc3`，safe runner SHA256 `7cbe2f234362e96378a48e0feffc406e74d8cbd69784f440989a47ad54c92a5d`；两TEST和保护windows_worktree不变。作者25/0.010s、root25/0.004s定点GREEN均0 FAIL、ERROR、skip/exit0；rootWin10.0.19045/AMD64/CPython3.11.4实际新模块10/0.129s/0 FAIL、ERROR、skip/exit0，含两native API正控。仅授窄parser/walker兼容，不代Windows隔离或新SHA CI。
- 实际SOURCE fresh SPEC→不同QUALITY均C0/I0/M0：原27个非parser函数全文不变，safe runner仅tuple条目，真实TEST等完整批准fence；仅候选新SHA线上门仍待。仓外author/root GREEN日志SHA分别`8f9a5ba56970824404985487e6f17c94db772c4461c0ad9f692d6ef5361b550b`、`88a52ac490b914859dfc84601719894224a7e80dc732b4cfc1d7900cd189a49f`，root-native原日志SHA `fc06c95e3862c3d01579134c264b6bf3cf64425668155d13774968993a14f28d`；具体日志名及未授边界见PLAN执行记录。

## 原生工作区来源与执行基线

本节对应多仓库来源核验，仅记录源代码迁移和软件验证，不是产品包安装或部署验收。
以下矩阵保留迁移时7aad基线及当时工作树状态；当前候选提交和线上状态以本节之前的“当前候选与线上观察”为准。

### vendor_package_matrix

| Package/tool | Acquisition source | Archive hash | Checksum/signature | Version/date | License | Product family | Host/toolchain compatibility | Intake risks | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 固定ICODE-SKILL | 原D子仓本地Git对象克隆，origin恢复原GitHub | N/A，未引入新archive | Git pin21566a5及工作树clean，不冒称包签名 | 固定21566a5，本轮2026-10-13 | MIT，实际读取克隆LICENSE | 既有控制面 | 当前Python3.11.17软件测试，安装能力另验 | 原D链接状态不复制或清理 | proven，仅既有源身份 |

### toolchain_compatibility

| Component | Required IDE/compiler/debugger/programmer | Observed version/platform/ABI | Project-consumed files/config | Local modifications | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Python运行环境 | 项目最低3.11 | 独立venv3.11.17 / Linux x86_64 / uid1000 | PYTHONPATH=src，实际runner/chain来自新根 | 不换系统3.10；仅新Git根local author/origin配置 | 67e156实际sys.executable、cwd、module.__file__ | proven，仅执行来源；安装链另验 |
| WSL文件系统 | 原生Linux验证根 | findmnt：ext4、/dev/sdd、/；当前kernel6.18.54.1-microsoft-standard-WSL2 | `/home/orbbec/projects/icode` | 不改权限、总线服务或配额 | 67e156 | proven，仅当前环境；早期6.18.40查询不代当前 |

### build_identity

| Invocation | Product/target | Architecture | Toolchain | Build root | Time | Manifest revision | Cache policy | Expected modules |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 原生完整unittest -v | SOURCE软件候选，未构建发行包 | x86_64宿主 | 上述Python；fixture编译j1 | 新权威根 | 2026-10-13，原日志记录准确start/end | 主7aad+批准工作区候选、子21566a5 | -B、PYTHONDONTWRITEBYTECODE=1 | src/tests/fixed vendor，不授installed |

### repo_matrix

| Module | Git root | Manifest pin | Actual commit | Branch | Dirty | Remote | Baseline relation | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 主仓 | `/home/orbbec/projects/icode` | 主基线7aad12c | 7aad12c | main，未建其他工作分支 | 仅批准候选及本接力记录，尚未stage | 原ayukyo/icode GitHub origin | 同原D HEAD，新clone而非历史诊断副本 | proven，仅源迁移 |
| 子仓 | 新根vendor/icode-skill | 21566a5 | 21566a5 | 固定gitlink detached | clean | 原ayukyo/icode-skill GitHub origin | 同原D固定commit，不复制dirty链接 | proven，仅源身份 |
| 原Windows主/子仓 | D盘原路径 | 保留原pin | 保留原HEAD | 不改变 | 原主候选及67个Junction保留 | 不改原配置 | 历史失败基线，不洗白clean | 不作为新权威发布门 |

### artifact_matrix

| Module | Build input root | Output path | Local hash/build ID | Package/member | Member hash/build ID | Architecture | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 源文件迁移 | 原D同候选 | 新权威根对应路径 | 486个tracked主文件逐字节相等；新增TEST20a另核 | N/A，未构建包 | 初次移交清单SHA256 `4a239ad997eabfa665a5ca602f9c55fa7805b8cfb41486ee25cc4e959b55dee4` | 解释型源文件，不授PE/ELF身份 | 053d0a/575b2f；之后接力记录仅追加真实证据 | proven，仅移交快照 |

### deployment_matrix

| Module | Device identity | Deploy window | Install path/slot | Device hash/build ID | Process restart | Runtime-loaded object | Verification window | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 软件候选 | 本机WSL uid1000；非终端产品设备 | 2026-10-13源迁移，不是产品部署 | 新权威根，无产品安装slot | SOURCE/TEST冻结摘要见后文 | 新验证Python进程，不宣称产品服务重启 | runner/chain实际新根__file__ | 完整-v suite已结束3216/623.663s/1FAIL1ERROR/skip165/exit1 | unresolved，完整发布门未过 |

### mismatches / verdict

- 原D为既有链接表示差异，完整guard已exit1，不恢复、删除或隐藏；用户授权改变权威验证/发布工作区，不改变其历史结果。
- 原生SOURCE迁移身份proven；发布、产品包/installed、自动模式及R2/R3整体均unresolved。复制成功、子仓单门PASS或原生进程已启动均不代表这些层通过。
- 新原子模块单门实际exit0（f66ddc），未额外创建日志文件；源码/TEST继续冻结。原生-v完整输出采用script -f保存；之后用户明确将后续全量移到GitHub，不再重复本机完整preflight。不得用原D失败尾部遗失的ERROR栈补猜新结果。

### 原生全量历史与环境前置（后续进度以上方当前顺序为准）

- 新权威根首次全量原日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/native-full-tests.log`，SHA256 `a83538f3305ec39c3e898a57fb085d24720298b1cff1562f58813c29e59c8ae6`；2026-10-13 11:54:10–12:04:36 UTC，3216 tests / 623.663s / FAIL1、ERROR1、skip165 / exit1。完整原输出已保存，既有子仓污染断言在新根通过；不据此洗白原D或宣称全部环境差异仅来自文件系统。
- ERROR为packaged Skill的setUpClass调用既有构建后端时 `ModuleNotFoundError: setuptools`。项目build-system及dev明确要求>=80，root仅对既有独立venv用uv安装setuptools84.0.0（919793），未改产品dependencies。随后原 `tests.test_packaged_skill -v` 实际18 / 19.949s / 0 FAIL、ERROR、skip / exit0，日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/native-packaged-skill.log`，SHA256 `936e87f6469989a4432336a1b920fb82ad044df0f4c21134a6aa8a315d78da06`。包含真实临时wheel/venv安装与sdist重建，但不代三平台、签名发布、原生隔离或R2/R3整体。
- FAIL为原 `TestProbe` Landlock真实文件/网络探测用例。root对原 `LinuxTaskScope.__init__` 只做透明观测、重新调用原失败：94d0c6实际1 test / 2.184s / FAIL1 / exit1；原构造器149行 `os.stat('bus', dir_fd=parent)` 抛FileNotFoundError，filename实际为bus（missing_user_bus=True），对应 `/run/user/1000/bus` 不存在。该失败在资源建立/任务启动前，未改变原检查或执行失败后的payload。
- 当时systemd用户实例running而标准dbus.socket/service unit缺失（8bae33）。apt模拟767cb6仅拟新增dbus-user-session，0升级/0删除；随后用户明确授权，实际安装及原失败复跑结果见当前顺序。没有跳过或降低原断言；后续全量按用户新要求移到线上。
- 两次诊断包装错误保留：487637因PowerShell stdin把中文方法名变成问号而收集ERROR，ed4f56因ASCII前缀匹配到多项触发自检assert，两者均不算有效RED或资源分支证据。改用Unicode escape精确选择后，08263c/94d0c6才实际命中原失败。后续MCP输入采用ASCII高层决策摘要，实际3步07d44c完成，避免同类stdin编码损坏；不修改全局编码、MCP配置或权限。
- 新工作区静态迁移/执行记录等价复核C0/I0/M0：当前PLAN d38183去掉两Task状态及末节，精确恢复批准836b；严格13+3重放、TEST fence和五共享函数均相等。当前无运行中的测试或审查线程，尚未暂存、提交、推送；原始新根完整preflight尚未启动。

【架构级自检报告】（当前软件候选与接力状态，非整体验收）

- 语法/编译：两SOURCE/TEST静态检查、22项双份GREEN及已执行软件回归通过；全量失败如上保留。
- 依赖/调用链：SOURCE双审零遗留、五共享函数未变；构建依赖和标准用户总线仅补授权的开发验收环境。
- 逻辑/边界：六terminal、unknown、公开字段漂移负控通过；资源缺失正确拒绝，不授自动ready。
- 异常处理：原全量及诊断失败、未通过环境/平台项均明确记录，不伪造成功或重试未知资源。
- 关联模块：主/子仓分别核根、固定pin及源字节，原D及67链接保留；迁移不改源码资产。
- 兼容安全：Linux限定软件合同通过，Windows旧快照缺陷未修复；无产品权限/依赖变化，WSL标准用户总线已按授权启用。
- 可运行性：包软件测试18项通过；全量/原完整发布门尚未通过，R2/R3、installed、原生完整能力均未完成，不报告100%。

## 当前结论

**R2 / R3 尚未整体验收。** 最新候选`6e893f0170b74c32d7143680636d85f400ecc7c9`两Python全量及独立密钥/子仓门通过，三个工作流均终态；CI还有两个Reviewer失败与一个未启动macOS生命周期取消。Linux inspection/Git分层契约与macOS完整M0原生资产仍开放；仅文档记录不能替代生产代码验收。

| 阶段 | 当前状态 | 下一步 |
| --- | --- | --- |
| Linux S2a 上下文薄适配 | 已发布 `01e22a4` | 不重复实施 |
| Linux receiver 截止原因分账 | 已发布 `667c92a` | 不外推历史 ARM 根因或原生因果证明 |
| Linux S2b1 控制面适配 | 已发布 `1754cca` | 不重复实施 |
| Linux S2b2 Runner 生命周期 | 正式 RED/GREEN、254项回归、实际 SOURCE 双审及0a980e0同SHA软件门通过 | 继续S2c真实内部组合及S3 installed矩阵；不借旧dispatch或软件门授完整R2/R3 |

S2b2 的生产 `runner.py`、`chain.py` 和新测试已随0a980e0提交推送，线上必要门仍待，不是产品发布。当前冻结 runner `91e5e6cc6fb0c1c12f9c769bd30aea5b9e95d7dcd3dc01bea6027d6d6074869b`、chain `16c23c505724cb9a23f25eb27d77e21919146dd0dbc3adde752de2c863f10acd`、TEST `20a1339e369c56617738e8938e4965ec68efebf44dea7e160c3f717121191b73`；原批准 PLAN 为836b。下文“未落盘”等文字是早期诊断历史，不代表当前状态。

### 正式实施与迁移历史（2026-10-13，旧本机交付顺序已由当前线上优先约定替换）

- 作者和 root 在原源码分别取得22方法 / 44有效 AssertionError / 0 ERROR、skip / exit1，耗时45.119s、45.750s；不是收集失败或 RAM 投影。root 原日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-formal-red.log`，SHA256 `9fc96fb312a0db93878ad2dbc262bccdce1ad52fe4dce07539fb22fe351669e7`。
- 冻结新 TEST 后，不同 SOURCE 作者仅实施两处批准源码。作者 GREEN 为22 tests / 188.874s / OK / exit0；原日志 `/home/orbbec/icode-s2b2-source-green-20261013-1910.log`，SHA256 `b1688bfb4e24e3034510f67e18ec7c534eb4f4c31d13f7e15234685661618fb8`，root 已实际核对原 footer 与摘要。
- root 独立 GREEN 为22 tests / 183.293s / OK / exit0；原日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-formal-green.log`，SHA256 `adfd03c75d2ae9bb67c98dc7e8727ec2faa07a5734b94a17c55c6eb99f7867aa`。作者10模块限定回归254 tests / 403.696s / 0 FAIL、ERROR / skip6 / exit0，日志 `/home/orbbec/icode-s2b2-source-regression-20261013-1915.log`，SHA256 `f0fe39bcccdf66d0d36ef144e693e6bc5989499ff7a362e132719c6ba23df525`；root 独立相同回归254 / 394.392s / 0 FAIL、ERROR / skip6 / exit0，日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-regression.log`，SHA256 `ef5b2fc7c15bbd0d7167bc9934fec62c938df1a905fd44a6a44594a0d01e1cf2`。各原 footer 和摘要均已实际核对；skip为既有平台条件，不授原生信用。
- 源码与 TEST 保持冻结，未取得终态的检查不记为通过。
- fresh 实际 SOURCE SPEC → 不同 QUALITY 已分别完成 C0 / I0 / M0：严格13+3重放与实际字节相等、新 TEST 与批准 fence 相等、五共享函数全文不变；消费漂移、候选未知、外部unknown六出口及异常优先级分别核实。两位审查者均停止、未重复执行测试或修改文件，不以审查替代完整守护或原生验收。
- root 补充8模块调用链回归（tools、engineering_verification、engineering_evidence、artifact_broker、execution_broker、linux_contract_engineering、linux_workspace_fd、contract_budget_stop）：200 tests / 93.289s / 0 FAIL、ERROR / skip3 / exit0。原日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-callchain-regression.log`，SHA256 `e4427635c77e26d98e8b171186575e8bb782c58887309f70af714acc5e2e89b4`。跳过为缺Go工具链、工程桥类与目录对象资源链缺同用户总线；实际 uid1000，systemctl用户实例running，但 `/run/user/1000/bus` 不存在。不得将这些跳过记为原生资源链通过，未为该软件片安装或修改总线服务。
- root 本候选原D完整守护已结束，原命令 `env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -u -B scripts/preflight.py`；日志 `/home/orbbec/icode-s2b2-evidence.Y3xrfh/root-full-preflight.log`，session74792。实际3216 tests / 1323.887s / FAIL2、ERROR1、skip165 / exit1；密钥PASS，子仓完整性与测试两门FAIL，禁止提交推送。原脚本只输出失败尾15行，已见子仓污染断言和Landlock probe拒绝绑定，ERROR1详情未被该脚本保留，不能猜测；后续原生工作区须捕获完整测试输出并重新原完整门，不把skip授能力信用。
- 发布障碍为67个tracked mode120000链接，Windows现为指向另一D盘工作区的Junction，而Git原记录为旧Linux绝对符号链接。用户已明确选择“保留本机链接，迁到WSL原生工作区验收发布”；不改写原D链接、子仓或配置，不把原D工作树称为clean。新权威工作区为 `/home/orbbec/projects/icode`，由同本机HEAD main和固定子仓本地Git对象新克隆，不复用历史诊断副本、不新建线上分支/worktree；逐字节候选核验与新工作区全门通过前仍禁止发布。迁移前实际3步sequentialthinking已完成（a10f77）。

### 本机 Windows 旧问题诊断（并行只读，非已修复）

| Section | 当前证据及边界 |
| --- | --- |
| identity | 当前本机Windows10 build19045、AMD64；以实际解释器路径绑定主机执行，未采集物理序列号，不授硬件或线上设备验收 |
| time_window | 2026-10-13北京时间本轮，current→HEAD-RAM顺序执行；工具记录60eedc/345050与88b2be/d84115保留，未做设备时钟偏移校准 |
| repo_matrix | runtime/analysis为HEAD7aad工作区runner91e5/chain16c2；comparison只从同HEAD读旧runner56abe/chain282441并SHA断言后在RAM加载；vendor固定21566a5且既有67链接dirty；尚无修复verification候选 |
| artifact_identity | `C:\Users\orbbec\AppData\Local\Programs\Python\Python311\python.exe`，3.11.4 / MSCv1934 64bit；代码字节如上，未构建或安装新产品包 |
| evidence_sources | 当前34项16.288s与旧HEAD-RAM34项16.245s均2FAIL/2ERROR/0skip/exit1，四失败名相同；原失败及footer保留在工具记录，RAM首次输出被截断，不冒称完整日志文件；RAM traceback的linecache可能显示当前文件文本，不据此推断旧字节调用行，实际编译输入SHA已核 |
| unresolved | 自有空目录的实际原生拒绝分支已由研究者及root各独立复现；原34项的各原目录未逐一采样，Windows全量兼容性未通过，root负责另片修复设计，不降低拒绝门 |
| conclusion_ceiling | root_cause_supported仅限自有空目录：原生`..`返回全零FileId，被既有parser在识别伪项前拒绝；四现象旧/新均复现而非S2b2新增，不授四用例唯一根因、修复、Windows运行链或R2/R3通过 |

四项为：create_next的测试把Windows Path转换期待写成硬编码POSIX字符串；真实chain快照报目录记录invalid；两个NativeChainExecutor相关用例未走到review或后续列表为空。后两者是否完全由同一快照拒绝引起尚须实际链路核实。复杂诊断前root以已配置stdio服务实际完成3步sequentialthinking（8022b8），另启动独立只读源码/官方API研究，SOURCE/TEST/权限均未修改。

| Claim | Kind | Source | Boundary | Status |
| --- | --- | --- | --- | --- |
| 四失败现象不由本次两SOURCE变更新增 | fact | current与旧HEAD-RAM同34项原footer、四失败名及编译输入SHA | 不证明Windows产品已可运行或根因已确认 | supported |
| 自有空目录中伪项身份校验先于忽略，导致正常枚举被拒绝 | fact | 研究者9ca00d、root42a3c7两次真实API页、生产parser与snapshot原错误 | 尚未逐项绑定34项原失败目录，不授修复通过 | supported |

root42a3c7实际核源码两文件等于HEAD：workspace_snapshot `56cdd4442a91c081e8cf1b86963f9894a1a55b458ff57584340229f4895d3eaf`，windows_worktree `2fe8702b9abcb01b18e7959b4c201b7108dca4341f32e0fd9473e90df47bf03b`。自有空TemporaryDirectory、实际GetFileInformationByHandleEx class20返回True/error0，`.` next96/名2bytes/有效ID，`..` next0/名4bytes/全零ID，两者directory属性16；原parser和snapshot均报directory_record_invalid，句柄按原close_root回收、自有temp删除确认True。没有访问用户目录内容或修改候选。

2026-10-13研究及root均核[Microsoft EXTD布局与class](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_extd_dir_info) / [枚举类](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ne-minwinbase-file_info_by_handle_class)，未发现结构混用；该官方资料不保证伪项ID必须非零，零ID事实来自本机实测。下一片拟先补严格结构/UTF16/offset/trailing下的确切dot伪项正控、普通子项零/FF-ID负控，再考虑最小生产校验顺序修复；S2b2及完整守护在途期间不改源码。

root进一步做只读RAM因果实验（d6b400/cf6b7f/439d46）：仅把生产parser的零/FF-ID校验移至真实非dot子项分支，仍运行原34项、不改任何断言或物理文件。实际34 / 26.947s / FAIL1、ERROR0、skip0、exit1：三个快照相关用例全部通过，唯一剩余为Path硬编码POSIX断言。结束再次断言workspace_snapshot物理字节完全不变；该实验支持快照拒绝导致这三个用例失败的因果路径，但不授正式TDD、完整安全负控、修复落盘或原生整体验收信用。

## 2026-10-13 接力更新（以下保留实施前历史）

- 接力开始时 Windows HEAD 与远端 main 已核为 `7aad12cc877c2a53abe565eb34d08f590630ff74`，该提交只保存文档；最近生产候选仍为 `1754cca`。当时 runner、chain、DESIGN、PLAN 的原始 SHA256 与下文冻结值一致，没有发现换行漂移；此为修订前基线，正在修改的 PLAN 必须重新取摘要与审查。
- 独立 PLAN QUALITY `s2b2_plan_quality_windows_resume` 发现 I1：原 PLAN 的 `finish_prepared()` 只核内部 owner 的关闭状态，外部 owner 为 unknown 时可在 view.finish 后变成 spent，错误允许 terminal。生产 `LinuxPreparedStep.close()` 会先设 unknown，底层关闭失败不恢复 active；attachment.finish 不核 owner 健康。root 已核源码与 DESIGN 的 unknown 不终结要求，采纳该缺口；修订文档资产进行中，尚未重新批准或实施生产代码。
- 修订要求：收尾门分别要求内部 owner 为 closed、外部 owner 为 active；外部 unknown 必须阻断六 terminal、保留实际 checkpoint/open attempt，且不得由 runner 重试关闭外部 owner。补真实外部关闭失败负控与普通 body 错误优先级。保持六文件范围、一次收尾及首信号语义；修订后的资产及摘要须重新审查，旧批准摘要不能沿用。
- 本轮 QUALITY 只授 Windows 静态与局部 RAM 证据：严格重放 runner 13 / chain 3 hunks，AST/compile 通过，TEST 42485 bytes / 20 方法及投影摘要符合原资产；局部负控确认 spent / unknown 被放行。未执行 Linux 全模块、正式 RED/GREEN、原生或模型测试。
- 本机已实际确认 Ubuntu 22.04.5 / WSL2、x86_64 Linux `6.18.40.1-microsoft-standard-WSL2`，systemd 系统与用户实例均 running；Landlock VERSION 查询返回 ABI 7 / errno0，用户 cgroup controllers 含 memory / pids 且 subtree_control 可写。只授能力查询，不授隔离或配额实际强制执行。工程可从 `/mnt/d/Projects/icode` 读取，该盘是 9p / drvfs，不视为 Linux 原生权限、符号链接或隔离验收环境。uv 0.13.0 已以用户级 pip 安装，Python 3.11.17 下载及安装成功（4m08s）；新独立 venv 为 `/home/orbbec/icode-r2r3-env.DL2JQJ`，不复用搬迁的 `.venv`，不更换系统 Python，不修改 shell PATH。
- 本轮环境回归实际命令：`wsl -d Ubuntu-22.04 --cd /mnt/d/Projects/icode -- env PYTHONPATH=src /home/orbbec/icode-r2r3-env.DL2JQJ/bin/python -B -m unittest tests.test_linux_prepared_control_attempt -v`，16 tests / 21.514s / 0 FAIL / ERROR / skip，exit0。之前误写为不存在的 `tests.test_linux_prepared_control`，收集报 ModuleNotFoundError / exit1；该调用错误不算有效 RED，改用真实现有模块后通过。当前新 lifecycle TEST 仍不存在，不能据此授 S2b2 正式 TDD 信用。
- 同一新环境实际执行 `tests.test_linux_prepared_tool_context -v`，8 tests / 0.754s / 0 FAIL / ERROR / skip，exit0；两组共 24 项仅授既有软件回归，不授新 lifecycle、完整 guard 或 native/installed 信用。
- 已在 WSL 原生文件系统新建诊断基线 `/home/orbbec/icode-linux-validation.UV7vPA/repo`，从本机 Git 对象克隆 main / 固定 vendor，不新建分支或 worktree、不恢复原 Windows 改动。实际 HEAD 为7aad12c，runner / chain 与冻结字节精确相等，主仓及 vendor clean，原子模块单门 PASS（753c9b）。同一 Python 在此运行上述两组共24 tests / 9.654s / 0 FAIL / ERROR / skip，exit0；不以副本的 clean / PASS 代替原 Windows 工作树完整性或新候选发布门。RAM 资产仍须读原工作区当前 PLAN，不能读取副本旧 PLAN 后冒称修订已测试。
- WSL 自带 Python 3.10.12，实际导入 workspace 因 typing.Self 失败，config/cli 因缺 tomli 失败，BaseException.add_note 不存在。用户已同意借鉴 Aider / uv 独立解释器安装，保留最低 >=3.11，不替换系统 Python。安装方案仍待实现与干净机器验收；不把开发环境安装当正式用户安装链通过。
- 本轮已解除 sequential-thinking 调用阻断：会话工具列表未直接提供入口，但 `codex mcp get sequential-thinking --json` 证实已启用的本机 stdio 配置。实际启动配置中的服务，读取 tools/list 得到 sequentialthinking 定义，再以 JSON-RPC tools/call 完成需求分解、方案分析、风险评估三步（d03163，server sequential-thinking-server 1.0.0，historyLength=3、nextThoughtNeeded=false、exit0）。首次连接因子进程 node 不在 PATH 且诊断解码失败而关闭；仅为本次子进程补齐配置中 node 的目录后成功，未修改 MCP / 全局 PATH / 用户权限。不以配置存在代替调用成功。
- 当前推进顺序：独立文档作者已停止并冻结修订 PLAN `836b276a167d17d29b57a3ac30a89ec76325d13d62876e085eec983dd80be174` / 1358行，root 已核实际摘要和全文差分；不同 fresh SPEC / QUALITY 已均 C0 / I0 / M0，正式 TEST ONLY 放行，由不同正式 TEST / SOURCE 作者依序执行。旧批准记录仅作历史，修订不能继承旧审查或 RAM 信用。源码尚未修改；新 lifecycle TEST 正在建立，尚无正式 RED/GREEN 终态。
- 本轮 fresh SPEC 严格13+3重放/compile/旧五共享函数全文不变通过；其 RAM 捕获只有开始输出、未保存原footer，已核无遗留进程，不授运行 PASS。不同 QUALITY 独立新增两个外部方法 RAM 2 / 15.564s / 0 FAIL、ERROR、skip / exit0；旧owner门mutation 2 / 14.592s / 7有效assert FAIL / 0 ERROR、skip / exit1，六真实CP回执 returncode0 / okTrue，普通body错误优先级被检出。仅批准当前PLAN质量，不授正式TDD、全套运行、native/installed或R2/R3。
- 修订 TEST 资产为47065 bytes / 22方法 / `20a1339e369c56617738e8938e4965ec68efebf44dea7e160c3f717121191b73`；runner候选 `91e5e6cc6fb0c1c12f9c769bd30aea5b9e95d7dcd3dc01bea6027d6d6074869b`，chain候选16c23c保持不变。作者最终相同 fence RAM BASE22方法/44有效assert FAIL/0 ERROR、skip（20.717s / exit1），投影22/0 FAIL、ERROR、skip（94.814s / exit0）；旧owner门mutation六分支真实terminal_calls=1 / step_finished=1 / state_changed=0 / CP ok=True（数量1不是returncode1），新门零terminal / 事件且保留checkpoint。root静态核对及作者RAM不代正式RED/GREEN；诊断采集中断、注入点修正等历史保留在PLAN。
- vendor 固定 HEAD 仍为 `21566a5`；Windows 工作树已有若干测试缓存 current 符号链接路径显示删除，主仓仅显示 vendor dirty。保留现状，不 reset/restore、不伪称子模块完整性门通过；查明迁移差异并完成完整性门前不提交推送。
- 本轮固定 Codex / OpenHands 只读研究于 07:25:46–07:26:20 UTC 重核既有提交与许可证；采纳退出/收尾/同对象绑定分账，暂缓状态恢复，不适配 best-effort callback 当 CP success。未刷新全部 20 项、复制源码或新增产品依赖/权限。

uv 安装片验收要求：保留系统解释器；独立、受维护且版本明确的运行环境；中英文入口一致；可清楚报告下载/代理/离线失败；保留 pip/pipx；从干净 Windows/Linux/macOS 环境实际安装并运行 doctor。不预写发布包可用、签名可信或 R2/R3 整体通过。

本轮独立安装研究固定 [Aider 5dc9490 Unix](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/install.sh) / [Windows](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/website/install.ps1)、[uv f55ed82 工具安装](https://github.com/astral-sh/uv/blob/f55ed8241a6484d654965cf4768667e176e1a59a/docs/guides/tools.md) / [解释器管理](https://github.com/astral-sh/uv/blob/f55ed8241a6484d654965cf4768667e176e1a59a/docs/concepts/python-versions.md)。采纳显式选择已覆盖版本、独立环境和缺失解释器下载，复用包名 / CLI / bundled SKILL / wheel 验收；收益为减少用户处理系统版本，成本为安装合同及三平台实际验证。暂缓正式发行命令直至发行身份、可获得版本与平台 wheel 核验；不适配照搬 force/latest、源码安装冒充免 Git/编译器或 uv 环境隔离当 OS 沙箱。Aider Apache-2.0、uv MIT/Apache-2.0，仅机制借鉴，不复制代码或新增产品依赖。

以下下一会话步骤保留原批准计划的历史；当前工具与基础环境已可用，仍须完成 I1 资产修订与重新双审、正式 TDD 及发布完整性门。

## 已发布 S2b1 的证据

仅六文件：控制面原始回执入口、新私有观察适配、新测试、DESIGN、PLAN、持续竞品对照。

- 正式原基线：作者与 root 各 16 方法、15 个有效断言失败、0 ERROR / skip，exit1。
- 实施后：作者与 root 各新 16 项通过；相关八模块 196 项通过，5 项原平台跳过。
- 实际 SOURCE 独立 SPEC → 不同 QUALITY 均 C0 / I0 / M0。
- 唯一原完整预检：`/tmp/icode-cp-prepared-preflight.dOMmDP/typescript`，09:10:18–09:20:00 UTC，三门 PASS、exit0；不猜未输出的全量数量。
- 最终两轮原文档检查各 raw0，密钥扫描、子模块完整性、精确六文件暂存字节及 cached whitespace 检查通过，再提交推送。
- 发布前补丁围栏尾随空格曾实际阻断；仅裁掉未修改的外缘上下文，严格投影源码不变，独立复核后重新过门。失败历史保留在原 PLAN 和持续对照中。

固定子模块仍为 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`，本次没有再次修改 ICODE-SKILL。

## 当前提交的线上终态

以下均绑定 `1754cca`、`main / push / attempt 1`。独立观察者 09:49:36 UTC 收齐；root 另实际读取全部 job 元数据及 12 个关键原日志，并于 09:50:18 UTC 重核最后 provenance 终态。

| 工作流 | 终态 | 边界 |
| --- | --- | --- |
| [CI 38230724875](https://github.com/ayukyo/icode/actions/runs/38230724875) | 41 成功、2 失败、3 跳过，共 46 job | 两个 Windows Reviewer 仍失败，不是总体全绿 |
| [Windows helper provenance 38230724868](https://github.com/ayukyo/icode/actions/runs/38230724868) | 5 / 5 成功 | 来源拒绝与回收测试成功，不是可信启动授权 |
| [Public website 38230724577](https://github.com/ayukyo/icode/actions/runs/38230724577) | 2 / 2 成功 | 同 SHA 已部署，不是 R2 / R3 能力验收 |

关键原日志可从以上工作流重新读取，不依赖新会话仍能访问旧工具内存：

- Python 3.11 job `114749249615`：3221 tests / 545.992s / 86 skips；Python 3.12 job `114749249750`：3221 / 546.456s / 86 skips，均通过。这些数量属于已发布 S2b1，不包含尚未落盘的 S2b2 测试。
- Windows Reviewer：x64 `114749249934`、ARM `114749249836`。候选双协议仍 `10035 / wait_expired=true / connect_denied=false`；正控 `105 / ipv4_connect_timeout / inconclusive`，WFP 无匹配 drop、补充 capture 缺失。**超时不能当网络 DENY。**
- 四 Linux job `114749249902 / 114749249907 / 114749249972 / 114749250145`：各 84 条旧 helper-dispatch 记录，通道、进程、线程回收通过；不是新 prepared 安装矩阵或 worker 截止采样因果证明。
- 四 provenance consumer `114752517458 / 114752517497 / 114752517492 / 114752517673`：`source_policy_all_passed=false / owner_untrusted`，compatibility、launch、protected 均 false；helper/verifier 各 13 opened / 13 confirmed closes / 0 unknown，逆序回收确认。不能外推 Windows 10 实机、叶 PE 消费、UAC 或受保护晋升。
- 观察者保留了全部 50 个执行 job 的完整原日志；另 3 个 skipped job 无执行日志。不要取消或重跑来掩盖未通过项。

## 原接力计划与诊断历史

先全文阅读：

1. [S2b2 DESIGN](nbl/specs/2026-10-12-linux-prepared-runner-lifecycle-design.md)。批准 SHA256：`ff78553d7fa5ce74fdb955464b253a0bb9567763f87e92ea8d0d04669d0410bf`。
2. [S2b2 完整 PLAN](nbl/plans/2026-10-12-linux-prepared-runner-lifecycle.md)。保存时冻结 SHA256：`75b1776e84e7726305171a400b39e1747bab3dd39909cc7a258a4824b3576643`，1244 行，完整 TEST 与两个 SOURCE diff 资产均已包含。
3. [持续竞品对照与执行历史](agent-landscape-live.md)，保留原失败、日期、固定上游和信用边界。

### 待完成的第一道门

原 PLAN 独立 SPEC 已 C0 / I0 / M0，审查者 `prepared_runner_plan_spec_review` 已停止：严格 13 + 3 hunk 投影、独立 RAM 20 项 / 49.888s / 0 FAIL / ERROR / skip，六健康 terminal=1、六 unknown terminal=0；两轮原 scanner raw0。**该对象随后 QUALITY 发现 I1；当前修订836b必须重新 fresh 双审，尚不能直接实施。**

上述完整 SPEC 对象为原 PLAN `4936fe31e2c2932814c2162ac2ce31c85b20928413a3c1e2a0948ffcdf0ec553`。保存前对未跟踪全文的 whitespace 检查 817ecc 实际拦截末尾多一个空行（exit3）；root 只删除最后一个额外 LF，得到上面的保存摘要，正文与所有可执行资产不变。原审查摘要保留，不伪装同一文件字节；另做文档等价复核，不替代本轮有 I1 的 QUALITY 或修订后独立审查。

该等价复核已完成 C0 / I0 / M0（7b6d23，exit0）：加回一个 LF 精确重建原摘要，Python/diff 围栏及 13 + 3 hunk 投影完全相同，新 TEST 仍不存在；未重跑任何测试。四文档首次 cached 检查 de03e7 已 exit0；记录补入后发布前再核最终字节。

通过 QUALITY 后，按原 PLAN 串行推进：

1. 不同 TEST 作者只创建批准的新测试，正式原 SOURCE RED；root 独立重复。不得用 ImportError、TypeError、内存诊断冒充有效断言失败。
2. 冻结 TEST 后，由不同 SOURCE 作者仅修改 `runner.py / chain.py`，作者与 root 各 GREEN 和限定回归。
3. 实际 SOURCE fresh SPEC → 不同 QUALITY 零遗留，再由 root 启动唯一原完整预检，最终文档与精确六文件门通过后一次提交推送 main。

本片目标：一次 prepare / attach、真实 CP attempt / fresh observer、普通 / 补救 / 工程同 view，六 terminal 前确认收尾，finally 仅兜底；unknown/faulted 不终结、不清 checkpoint。内部 owner 关闭与外部 owner 保持 active 分账；旧 None/custom、Reviewer、resume、readyfalse 合同不变。

冻结资产用于识别漂移，不是执行授权：

| 对象 | SHA256 |
| --- | --- |
| 实际旧 runner | `56abe98e31f02cc96327a364c52ace9aef5b7c60e6594025058e2de48f15a63d` |
| 实际旧 chain | `28244144023c85548ca0e9bcb68235a935d648d53b8367ae80cde67f746508de` |
| PLAN 内完整 TEST，42485 bytes | `772188d5fae95b2dcd3415fe97ef62a4659edc5f7552f58ef9424ded8534a334` |
| PLAN 投影 runner | `a0f3342473edc1c222188bf47a2aed7903b33783d6d6871a5848451262fb9d2f` |
| PLAN 投影 chain | `16c23c505724cb9a23f25eb27d77e21919146dd0dbc3adde752de2c863f10acd` |

作者相同最终 TEST 的私人 RAM 基线为 20 方法 / 37 有效断言失败 / 0 ERROR / skip；投影 20 项通过 / 51.053s。首轮投影的四项失败及夹具修复历史见 PLAN；无正式新 SOURCE/TEST，因此不得继承为正式 RED/GREEN。

## 仍开放的整体验收项

- Linux 后续 S2c / S3 的实际安装候选消费、四 Linux 新 prepared 矩阵；LA-2 自动准入、LA-3 网络、LA-4 持久回执 / doctor / UI。
- Windows WP0b 的实际来源 / proof / release / 加载边界、稳定路径首次 UAC、受保护晋升、跨管理员与父进程死亡证明；双 Reviewer 网络 DENY 仍未证明。
- macOS 单任务配额仍不合格。已按用户同意的 Codex 式边界验收文件 / 网络沙箱继承与同组清理，不承诺主动脱组后代零残留；不得用用户级限额替代。
- 2026-10-13用户已明确允许设计与验证“一次管理员初始化＋任务专用隔离身份＋受控启动器”，保留mac配额硬指标；Python包提供入口，未验收不启用。此前授权等待已解除，但不代表可信安装、UID排他、继承硬限、残留身份隔离或原生兼容已证明。独立设计正在核实际XNU UID计数、不可提高的hard NPROC及权限/凭据/工作区边界；其它Linux/Windows/R3独立工作继续，mac hard gate和ready=false不放宽。
- R3 真实模型六步链及至少 90% 能力一致性仍未验收。历史 plan → review → merge 三步成功不能替代 code → deepcheck → audit。当前阶段未读取或使用仓外模型凭据，不把凭据内容写入文档或 Git。

## 原接力约束历史（不作为当前执行指令）

- 直接 main、完成阶段后提交推送，不创建工作分支 / worktree；不 reset、force push 或清除用户改动。
- 编译最多 `-j6`，完整验证沿本轮低负载 `-j1`。使用 `.venv/bin/python`，不因系统 Python 3.10 的收集问题修改产品合同。
- 复杂实现前遵守 AGENTS 的三问和 sequential-thinking；使用适用技能，独立只读研究与开发并行，采纳机制而非盲抄代码。
- 根目录执行 `git status --short`、`git log -5 --oneline` 和上述 SHA 核对；文档提交后 HEAD 会变化，判断生产代码基线时检查文件字节，不机械要求 HEAD 仍为1754cca。
- 当前 writer、SPEC、研究及 CI 观察线程均已停止；没有遗留运行中的完整预检或已启动的正式 S2b2 测试。

当时的新会话示例（已过时，不再执行）：

> 先阅读 docs/development-handoff.md 与其中链接的 DESIGN / PLAN，核当前 Git 和冻结字节；先处理外部 owner unknown 的 I1、sequential-thinking 工具与环境门，修订 PLAN 资产并重新独立审查，再正式 TEST → SOURCE。一般按推荐方案推进，非必要不用询问；保持并行只读研究、main-only 和最多 -j6。

## 架构级自检报告（2026-10-13，实施前文档及环境准备的历史快照）

- 语法 / 格式：本轮 diff whitespace 与原 site 检查通过；历史四文档 scanner/cached 结果仅属于 2026-10-12，不外推当前版本。
- 依赖 / 调用链：已核 scope.close / attachment.finish / PLAN 局部收尾与 DESIGN unknown 要求；原 CODE/TEST 资产未修改。
- 逻辑 / 边界：QUALITY I1 的修订资产 fresh 双审已收齐，正式 TEST ONLY 已放行，SOURCE 尚未放行；环境回归及旧 CI 历史分别标明。
- 异常处理：保留实际 I1 与子模块完整性失败，不用旧通过结果覆盖当前阻断。
- 关联模块：仅更新本接力文档及仓外开发环境，不新增生产 SOURCE/TEST 或权限。
- 兼容安全：本轮密钥扫描通过，冻结字节与固定子仓库 HEAD 不变；vendor 现存删除保留，子模块完整性门未通过，未暂存、提交或推送。
- 可运行性：WSL 能力查询、uv / Python / 独立 venv 及现有控制面 / 上下文 24 项环境回归有实际证据；不授新 SOURCE/TEST 实施、原生安装或 R2 / R3 完成信用。
