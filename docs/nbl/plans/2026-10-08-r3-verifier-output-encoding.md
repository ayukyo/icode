# R3 独立验包诊断输出编码回归

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development、bug-investigation-baseline-checklist。单一源码写者；main开发，不新建分支。本文件区分已证实本机漏洞与尚未取得stderr的Windows原生原因。

## 基线与结论上限

| 项 | 当前证据与未决项 |
|---|---|
| identity | 软件CI无物理设备验收；绑定GitHub job113331994259 ARM及113331994380 x64，不臆造SN |
| time_window | 2026-10-08 UTC；精确push/main CI37783423412，观察当次原始job终态，不复用79e2旧日志；详细runner时钟偏移未观测 |
| repo_matrix | runtime/analysis＝main b5082d85b7bac881a4ff8086a52747c0862e9fc8；verification为后续冻结修复SHA待验；vendor1693651c1bd7daad3272eb054f0f81d6f254d08d未改 |
| artifact_identity | 原生Windows两架构workspace源码测试；离仓verify.py为b508 pack_verify.py实际复制，未提供Windows子进程stderr或独立PE部署事实 |
| evidence_sources | 新job各325 total、6failure、20skip；4方法/6断言在独立验包return1，内置verify_pack=[]；本机实际离仓包UTF8 exit0、cp1252/ASCII严格流UnicodeEncodeError exit1，保留异常栈 |
| unresolved | Windows实际child stderr缺失、对应根因未知；所有者root/CI observer，永久测试增加错误正文，新SHA原生复验 |
| conclusion_ceiling | 本机CLI输出编码漏洞root_cause_supported；Windows对应原因candidate_path。尚未修复验收，不得称跨平台通过 |

| Claim | Kind | Source | Boundary | Status |
|---|---|---|---|---|
| 本批Windows新增独立验包失败 | fact | 两精确job实际unittest栈 | 不证明JSON语义不兼容 | supported |
| 窄管道中文print改变合格包退出结果 | fact | 同包离仓-I实际UTF8/cp1252/ASCII三控制与异常栈 | 本机stdio控制不是Windows原生根因实测 | supported |
| Windows失败也是编码异常 | inference | 当前main中文print及-I环境规则 | 旧日志无stderr，不倒填 | open |
| 内置通过等于离仓或R3整体通过 | refuted | 同包独立子进程失败 | 不能跳过离仓正控 | refuted |

## 三问与最小方案

该精确CI后续已取得终态：44jobs＝37success/4failure/3整jobskip（13:31:13Z），停止旧窗口状态轮询。Python3.11/3.12全仓各2159 total＝2088PASS/71skip，566.139/573.955秒；Ubuntu与macOS ARM workspace各326PASS/0skip，七随包安装各18PASS/0skip。两个Windows新失败后的junction/lease没有执行，不计覆盖。官网同SHA两job成功；来源验证workflow另按精确终态回收，不以尚在运行的签名job预报通过。后续源码修复采用合法ASCII工单EV-1和Unicode路径/诊断；控制面拒绝Unicode工单ID的初始fixture ERROR不计功能RED，不改schema或造不合法成功fixture。

真实问题为诊断输出抛UnicodeEncodeError而改变验证退出码；已定位main打印调用且verify_pack可复用不改；生产/导出复制verify.py/离仓进程调用链已核对。仅按当前stream.encoding预转义不可编码字符，同一助手供main stdout/stderr所有诊断使用。UTF8/StringIO中文原样、窄流可审计转义，保留0通过/1校验失败/2用法错误；不修改全局stdio编码、不用-Xutf8/PYTHONIOENCODING绕测试、不捕获真正IO错误、不改schema/安全门/依赖。

根代理负责本文/roadmap/竞品；实现者仅pack_verify.py与test_engineering_evidence.py。按TDD先实际离仓脚本0/1/2×UTF8/cp1252/ASCII两个流strict控制RED，再最小GREEN；含Unicode路径/工单，禁止Traceback，旧independent helper在host端解码并输出诊断但不改变child编码。独立SPEC→不同QUALITY通过且两源码冻结后，再20轮新方法、工程/旧evidence/self_verify/CI关联、DEFAULT、干净pip、完整preflight、compileall-j1/治理/官网/竞品/diff/密钥/子模块门。阶段验收后按授权提交推送精确main，只取新SHA原生证据。

- [x] RED/GREEN与定点兼容回归
- [x] 独立SPEC及不同QUALITY
- [x] 根代理冻结守护与七维自检
- [x] 提交推送；官方main接口核对精确SHA
- [ ] 新SHA原生观察（独立回收，不由本机或推送代替）

## 第一冻结（2026-10-08）

实际RED三个方法、8FAIL/0ERROR/0skip/2.033秒；UTF8控制正常，cp1252/ascii的成功提示/失败诊断/用法与不存在目录均捕获窄流异常或错误退出。随后仅11行私有诊断助手及main十处打印接入，真实GREEN工程37+CI11＝48PASS/0skip/14.497秒；初始不合法工单3fixtureERROR另计。独立SPEC实际48PASS/0skip/15.131秒并批准，另RAM确认三个strict编码、StringIO、encoding/errors保持与BrokenPipeError透传。不同QUALITY及根代理完整守护未取得终态，不预报通过。

```text
src/icode/pack_verify.py 30dcdc6dcaf1fc49f0b8081997b1424c2d060c1f76b378357035446bc956fde3
tests/test_engineering_evidence.py 838c3c7057f94389264ab2a8b3ae9fa82d8be9cc11831b2c67edfc23f58d73c7
```

精确b508来源验证37783423396已终态5/5success（13:35:44Z），四签名安装各9tests/0skip及17实际PASS，均有密码学/离线/负控；Pages37783423415已终态2/2success（13:20:07Z）。旧三run观察全部STOP。签名仅现有main签名job写权、产物不是启动授权；上述成绩不抵消新Windows workspace失败或Reviewer安全硬门。

## 研究边界

根代理后续实际取得旧self_verify/evidence/CI关联226PASS/0skip/134.621秒，DEFAULT329PASS/0skip/125.599秒，干净离仓wheel/sdist及临时HOME安装19PASS/0skip/15.574秒。安装版producer/verifier实际SHA匹配，额外在安装版导出脚本上执行UTF8/cp1252/ASCII strict三编码×合格0/篡改1/用法2/不存在目录2共12控制，无Traceback；fixture普通组仍human，没有转换成OS隔离信用。compileall-j1、治理、官网、竞品排期、diff通过，两源码摘要仍匹配。完整preflight正在运行，Go仅本次PATH且GOMAXPROCS/编译并发固定1，不读模型KEY或修改全局环境；未取得终态不填全仓计数、不提交。

后续不同QUALITY已批准，无Critical/Important/Minor：工程37PASS/0skip/15.734秒、旧clean_export筛选11PASS/0skip/7.172秒、既有独立无仓依赖/通过/篡改3PASS/0skip/1.300秒、4RAM控制0skip/0.001秒；不是把clean_export的11项误作CI模块。两源码摘要前后匹配。根代理新3方法20轮＝60PASS/0skip/42.070秒；旧关联、DEFAULT、干净包和完整preflight尚在串行验收，不预报完成。

[CPython3.11命令行](https://docs.python.org/3.11/using/cmdline.html#cmdoption-I)的-I忽略PYTHON*环境；[stdio定义](https://docs.python.org/3.11/library/sys.html#sys.stdout)区分Windows控制台与重定向管道编码；[backslashreplace](https://docs.python.org/3.11/library/codecs.html#error-handlers)可保留不可编码字符的转义。采纳当前输出编码下的诊断转义机制；暂缓整个CLI双语/输出协议重构；不适配全局UTF8覆盖或删除中文。只依赖stdlib，不复制上游代码、无新许可/权限，研究不能替代本机和新Windows控制。

## 最终本机门（2026-10-08）

完整preflight实际3/3通过：2162 total＝2103PASS/59skip，440.172秒，不是2162全过或零跳过。根代理只为完整unittest回包打印最后统计，未改守护/测试行为；Go仅进程PATH，GOMAXPROCS=1、GOFLAGS=-p=1。相比先前60skip未取得逐项差异，不推定某原生门变为通过。两源码冻结仍匹配；最终文档之后密钥/子模块/diff再核对，通过后按授权提交推送main，精确新SHA与原生结果后记。本机CLI漏洞修复验收关闭；旧Windows远端根因、新SHA原生兼容、R2/R3总门仍各自独立。

## 发布与新原生窗口（2026-10-08，终态已回收）

本片已提交推送`aaaa448c3cfd7d859e894e87c627be156c77a65d`，官方GitHub commits/main接口独立确认同SHA；固定vendor169未变。精确新[CI37788328985](https://github.com/ayukyo/icode/actions/runs/37788328985)、[来源验证37788329060](https://github.com/ayukyo/icode/actions/runs/37788329060)、[官网37788329189](https://github.com/ayukyo/icode/actions/runs/37788329189)各自取当次日志，不借旧窗口填通过。

14:04:50 UTC只读观察：Linux workspace113348767925与macOS workspace113348768198各实际329tests/OK及75lease tests/OK；七随包安装日志各实际18tests/OK。Python3.11 full113348768130实际2162tests/OK、71skip；Python3.12及两个Windows workspace尚未终态，不计期望328项或Windows兼容关闭。来源验证validate113348767411实际9tests/OK，四签名安装job仍在运行；官网两job已success，部署状态观察停止，详细构建日志另回收。

新Reviewer候选ARM113348767879/x64113348767897均终态failure：实际1test/1failure，exit78、cleanup=true；private-network正控exit91/ipv4_connect、WFP订阅return5、双栈10035后等待超时且无canary。ARM观察门ready，x64观察门unavailable/wait_timeout；均缺补充capture精确成员。两job终态后停止轮询，以上不是网络DENY，不能由安装、签名或本次编码修复抵消。Windows新workspace结果将另记；不倒填b508 child stderr或根因。

### 新Windows测试夹具换行回归（本机门通过，随合同片提交推送中）

随后实际取得两个Windows workspace终态：ARM113348768466/x64113348768560各328total、6failure、20skip。新success/tamper两个方法三编码均已通过退出0/1前置断言，但文本期望`\n  工单`与真实`\r\n  工单`不匹配；旧四方法六returncode断言未再出现在新FAIL汇总。不倒填旧child异常栈，也不能把整job failure误称校验器仍返回错误退出。junction3与lease75后续步骤未执行，仍不计覆盖。

按TDD与独立复审流程，根代理先暂停合同唯一写者，再用真实离仓子进程强制CRLF复现2methods/6FAIL/0ERROR/0skip、1.310秒；仅两文本断言在比较时规范精确CRLF、保留原stdout/stderr、编码/0/1/2/篡改/Traceback门。测试helper新增可选newline（默认None为平台原行为），新方法实际执行退出0/1×三编码的CRLF控制，并断言原stdout确有CRLF；生产pack_verify.py没有修改。根代理4methods/0skip/2.834秒及整个工程证据38tests/0skip/15.522秒通过；独立SPEC4methods（18真实子进程场景）/0skip/2.733秒批准。不同QUALITY、20轮及下一合同冻结完整守护尚在进行，不把本机修正写成已推送或Windows原生再验通过。完成小修后恢复同一合同唯一写者。

```text
tests/test_engineering_evidence.py e1974a1e663de068ee250f54df7a808c6f1e6f5d6bf572c2e354193dea4e8ac6
src/icode/pack_verify.py 30dcdc6dcaf1fc49f0b8081997b1424c2d060c1f76b378357035446bc956fde3
```

根代理同一冻结4methods20轮实际80PASS/0skip、56.341秒，包含默认平台流与强制CRLF且退出0/1/2控制没有降门。之后CI37788328985已终态failure，44jobs＝37success/4failure/3整jobskip，停止该run状态轮询；Python3.11/3.12各实际2162tests、71skip、无failure，即各2091PASS。四失败精确为两个CRLF fixture与两个Reviewer候选；不用失败job掩盖已观测退出控制，也不把未执行后续junction/lease填通过。来源验证唯一尚运行ARM Python3.11与已成功官网各另取证。

不同QUALITY最终批准，Critical/Important/Minor均无：4methods/18真实child场景、0skip、3.330秒；RAM负控确认孤CR保留及非法newline真实ValueError/exit1/stderr Traceback不吞、repr参数不执行插入内容。辅助runner误发现其全局导入的既有测试类，实际另跑14tests（2负控加12原方法）/0skip/8.549秒，如实计范围偏差，不称新14项、全模块或CI。两SHA前后仍相符。根代理语法-j1、diff、密钥及子模块分别通过；第三全仓测试门须等合同唯一写者冻结后一起验，两个only守护的通用“可以commit”提示不授权跳过完整门或提交WIP。

精确aaaa448来源验证37788329060最终5/5success；四签名job实际每个9tests/0skip及17PASS（安装后密码学、离线与负控、setup拒绝），分别x64/3.12 job113352154954 attestation53961786、ARM/3.12 job113352154976 attestation53962014、x64/3.11 job113352155111 attestation53962036、ARM/3.11 job113352155043 attestation53963370。官网37788329189最终2/2success。三个run全部STOP，不重跑、不给启动或Reviewer网络信用；前述在运行条目保留其历史时点而非伪装最终状态。签名写权仍仅现有main签名job，本片未新增权限/依赖/vendor修改。

合同唯一写者冻结后，本CRLF夹具同SHA纳入根代理关联、DEFAULT367PASS/0skip与完整preflight2201 total/2142PASS/59skip/0FAIL（466.044秒、3/3）通过；干净安装20外层及新合同37子测0skip通过。生产verifier SHA仍30dcdc6...，夹具仍e1974a1...；全部新SHA真实Windows结果另验，不能用本机或推送抵消两个Reviewer原生失败。此前“完整门待验”保留其历史窗口。

【架构级自检报告】
✅ 语法/编译：compileall-j1、2162全仓执行无失败
✅ 依赖/调用链：导出复制与独立stdlib main消费一致
✅ 逻辑/边界：0/1/2、三编码、Unicode路径正负控通过
✅ 异常处理：窄流转义，BrokenPipeError/OSError仍透传
✅ 关联模块：226关联、329DEFAULT和19干净安装零skip
✅ 兼容安全：旧golden/schema/退出/权限不变
✅ 可运行性：本片已测本机与安装路径全部通过；新原生及总门另验
