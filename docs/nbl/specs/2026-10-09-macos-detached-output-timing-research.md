# macOS Intel 脱组持管道测试：耗时边界调查

日期2026-10-09。只读调查，不放宽4秒断言、缩短生产预算、改变测试选择或授平台门。用户允许macOS同组清理/继承沙箱而不承诺主动脱组后代零残留，该边界不等于放弃有界输出捕获。

## 证据基线

| Section | 实际字段与边界 |
| --- | --- |
| identity | GitHub云runner，CI37850895865 job113563238539，logical macos-15-intel；物理serial/MAC unknown，不作真实设备部署声明 |
| time_window | job完整decoded日志2026-10-08 22:02:45.2837000–22:03:11.7194710 UTC；测试命令记录22:02:56.5415480，汇总22:03:10.6075250；日志由pwsh批量尾部转发，不提供每个method起止 |
| repo_matrix | runtime checkout与analysis main均118a2621cef92a5fcda510db295ea8c7658e5d4f，vendor固定1693651c1bd7daad3272eb054f0f81d6f254d08d；analysis当前仅root文档dirty，runner/test未改；verification候选未实现 |
| artifact_identity | actualCPython3.11.9/x64，macOS15.7.9/build24G830，runner image20260824.0482.1；源码unittest从checkout运行，无产品wheel/首次UAC/模型artifact绑定，Python/OS原始hash unknown |
| evidence_sources | [原生job日志](https://github.com/ayukyo/icode/actions/runs/37850895865/job/113563238539)；独立观察者及root分别取完整decodedlog，root保留完整字符串后分段读；actual checkout与vendor SHA、安装Python、31方法及失败traceback可见，CI原命令仅转发末80行/12000字符，未恢复不存在的原始子进程全stdout |
| unresolved | 无Popen完成、child.pid出现、root exit、group cleanup、reap、drain到期逐阶段时间；本机Linux不能填macOS耗时。owner root，下一步有界测试专用观察或明确测量分层，再同SHA原生验证 |
| conclusion_ceiling | observation_only：该窗口端到端4秒断言失败且原不完整输出拒绝已满足。不得声称rootcause、稳定性修复、零残留、Mac配额或R2/R3整体通过 |

actual31 total/26PASS/1FAIL/4既有skip、9.373秒。唯一FAIL为`tests/test_runner.py:1109`，`4.037273346999996 < 4.0`不满足；此前assertRaisesRegex(RuntimeError,"输出管道未在")已经完成。其它method摘要ok不能填此失败为通过。job终态STOP，不dispatch/rerun/cancel。

## 当前源码调用链与预算

`run_unittest(output_limit_bytes=1024, timeout=5)`使用同sys.executable、`-B -m unittest`，路由`_run_unittest_with_bounded_output`→`_run_posix_bounded_output`，不走无限阻塞pipe reader。直接子进程使用新session；退出监视不先reap数字PGID，killpg后reap，随后排空到期拒绝不完整输出。两流总预算仍共享，未返回部分输出。

该fixture的后代先setsid、写pid marker、sleep3秒；直接父测试最多200次检查pid marker，每次未见sleep0.01秒。外层`started`在整个run_unittest之前，故实际断言包括Popen/Python与unittest启动、后代就绪等待、退出/清理/reap及排空，不仅是排空2秒。源码允许约2秒就绪等待，加生产`_VERIFICATION_OUTPUT_DRAIN_TIMEOUT_SECONDS=2.0`及启动/调度开销，不能仅凭4.037秒判断是哪一阶段耗尽。

Darwin EPERM审计单独预算1秒；退出分支的drain_deadline使用cleanup/reap之前的now，不是给审计以后再额外加2秒。process cleanup预算2秒、process timeout5秒同样不能被写成该单次已实际耗时。缺阶段时间时这些是源码上限/路径事实，不是本格计时结果。

| Claim | Kind | Source | Boundary | Status |
| --- | --- | --- | --- | --- |
| 4秒端到端断言失败，原不完整输出拒绝满足 | fact | 原生method及traceback | 不给阶段根因/修复信用 | supported |
| 两个等待阶段及启动开销可能耗尽4秒余量 | inference | fixture与runner预算/计时位置 | 本格没有分阶段时间 | open |
| POSIX原读取是非阻塞并有退出后排空截止 | fact | runner实际selectors/monitor/deadline | 不证明native截止未被调度拖延 | supported |
| Windows Git/网络失败或Mac quota导致本method失败 | unobserved | 本日志没有该路径证据 | 不跨job/模块归因 | open |
| 本机Linux指定method通过 | fact | root实测1PASS/0skip、2.177秒/exit0 | 仅Linux当前源码，不抵消Mac失败 | supported |

## 下一步与禁止替代

独立只读研究核相关CPython/Codex机制；实施前先确定是否加测试专用、有界、脱敏的逐阶段时间观察，还是重构独立的“就绪/排空”验收。任何测量分层都要保留原端到端4秒失败，不能通过挪计时点把失败变PASS，也不修改2秒生产期限。现在不直接实现、称flaky、调整阈值、重跑赌通过或加平台skip。

## 固定上游核对与取舍

2026-10-09独立只读研究及root分别核对CPython实际runner版本v3.11.9，不把该版本称当前HEAD。原生CI没有升级Python的改动。root读取[POSIX启动条件](https://github.com/python/cpython/blob/v3.11.9/Lib/subprocess.py#L1825-L1844)、[communicate排空](https://github.com/python/cpython/blob/v3.11.9/Lib/subprocess.py#L2097-L2141)、[超时文档](https://github.com/python/cpython/blob/v3.11.9/Doc/library/subprocess.rst#L62-L68)及[PSF许可](https://github.com/python/cpython/blob/v3.11.9/LICENSE#L54-L105)：posix_spawn快路径要求cwd为空且不创建新session，ICODE本路径不满足；创建过程不能保证受communicate超时打断。两者不证明本次启动慢。CPython对EOF/endtime的处理也不是ICODE退出后2秒排空合同。

| 选择 | ICODE现状与借鉴机制 | 收益、成本及可验证边界 |
| --- | --- | --- |
| 采纳（设计输入，尚未实现） | 保留独立的启动与排空阶段，拟增加测试专用单调时钟观察；原process/drain预算、调用参数、返回/异常与端到端计时不动 | 能定位耗时组成；成本是固定少量阶段字段和配对负控。验收需原call恰好一次、原结果/异常对象不变、有界字段、无敏感输出、两种Mac同SHA观察；没有原生结果前不授修复信用 |
| 暂缓 | 改启动方式、移动计时起点、独立就绪/排空重构 | 当前无阶段证据，可能影响新session与清理依赖；另行设计并确认验收含义，不能在诊断中顺带实现 |
| 不适配 | 用普通communicate或扩大阈值代替ICODE的有界共享输出与退出后排空 | 会改变合同或隐藏本次失败，不能提供完整输出、同组清理或quota证明 |

只借鉴机制，没有复制CPython代码、增加库或权限，PSF许可观察不代替后续代码复用审查。研究作者只读STOP；本文件只有调查与候选设计输入，无实施、RED/GREEN或Mac重新验收。
