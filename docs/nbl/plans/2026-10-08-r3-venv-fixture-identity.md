# R3 venv 测试的目录身份与新增 macOS 失败

本片仅修正受控测试的目录身份比较并增加固定状态诊断，不修改production、默认环境、隔离策略或平台验收门；证据片计划已形成，源码尚未启动。独立只读调研与SPEC→不同QUALITY继续，阶段门通过后按已授权main提交推送。

## 故障基线（2026-10-08）

| Section | 当前证据与边界 |
|---|---|
| identity | GitHub hosted job113298583352、macos-26-arm64 image20260907.0351.1；物理SN未知，不以job或镜像名称证明物理设备身份。 |
| time_window | 原始UTC日志11:58:58.958实际workspace命令→12:01:28.225唯一FAIL；同一job时钟，不跨设备推测偏移。 |
| repo_matrix | runtime/analysis均main eead3ad2702be44800ee8f3ec0a49e6fcd803082，子模块日志明确1693651c1bd7daad3272eb054f0f81d6f254d08d；verification为相同production加本片单测试文件WIP。 |
| artifact_identity | 实际setup CPython3.11.9、macOS26.6.2/25G83；fixture现场临时venv未保存哈希/路径对象，不能追认其精确运行前缀。 |
| evidence_sources | [原始job](https://github.com/ayukyo/icode/actions/runs/37773507699/job/113298583352)由独立观察者及主代理分别读回；291项/148.419秒/1FAIL/0skip，唯一原test_selected_venv_launch_path_and_actual_prefix_are_preserved的run.passedFalse。无child状态/输出，不能凭此认定root cause。 |
| unresolved | 原生子进程实际prefix与run.status未知；本片添加固定状态/退出/错误类型/清理字段，原生新SHA验证另验。 |
| conclusion_ceiling | 当前observation_only加官方源码支持的candidate_path；Linux真实alias fixture只证明字符串校验误拒同目录，不证明macOS本次launcher根因或修复已原生通过。 |

| Claim | Kind | Source | Boundary | Status |
|---|---|---|---|---|
| eead新增macOS workspace失败 | fact | 精确job原始trace | 不与两个旧Windows Reviewer失败混合 | supported |
| launcher规范化父目录可使prefix拼写不同 | fact | CPython固定v3.11.9 pythonw/site原文 | 不是该job缺失的实际prefix观察 | supported |
| 本次失败可能是父目录别名 | inference | 上述路径机制及非resolve临时fixture | 缺原生child事实 | open |
| Linux修正通过等于macOS原生通过 | refuted | 平台边界不同 | 必须新SHA原生运行 | refuted |

## 最小修正与动态证据

fixture比较Path(sys.prefix).resolve(strict=True)与预期临时runtime的resolve值，同时拒绝与base_prefix相同；仍严格检查argv[0]保持选择的词法python路径。不修改传给production的路径、不继承PYTHONHOME/launcher变量、不skip原失败测试，也不输出原始stream/argv/env/路径。

新增POSIX父目录实际symlink alias fixture：选择alias/bin/python而预期同一runtime。旧字符串断言真实1FAIL/0ERROR（宿主观察status=failed、exit1）；修正目录身份后两个实际venv方法PASS/0skip/0.178秒。此RED是测试合同误拒，不冒称production隔离漏洞或macOS动态复现。最终host39+CI10=49PASS/0skip/6.169秒；测试文件冻结SHA256 f7fff7a4be55dd27afd048d0b654582509d14d13feb3a36a5bbb23f4ced308b2，全部production与eead相同。20轮、DEFAULT、双独立审查与新完整preflight正在验收。

官方依据：[CPython v3.11.9 macOS launcher](https://github.com/python/cpython/blob/v3.11.9/Mac/Tools/pythonw.c)、[site venv](https://github.com/python/cpython/blob/v3.11.9/Lib/site.py)、[getpath](https://github.com/python/cpython/blob/v3.11.9/Modules/getpath.py)。采纳目录身份而非字符串拼写，收益是正确接受同目录别名，成本为测试补强；暂缓原生根因确认，不适配继承任意用户环境或以Linux替代macOS验收。仅核对机制，没有复制源码、新依赖或新权限。

## 最终本机验收与远端旧窗口收尾

冻结测试摘要不变；两个真实venv方法连续20轮共40PASS/0skip/3.305秒，DEFAULT292PASS/0skip/111.909秒。独立SPEC两方法PASS/0skip/0.183秒，并实际验证基础解释器被新断言拒绝、旧字符串断言误拒同目录alias；不同QUALITY两方法PASS/0skip/0.171秒，无遗留发现。新完整preflight句柄58468已捕获退出0、密钥/子模块/全量测试三道通过；守护不打印全量计数，不宣称全量零skip。全部production与eead相同，本机编译-j1及差异检查通过，文档更新后再做密钥/治理/官网/竞品守护后提交main。

独立观察者回收eead精确远端终态并STOP：[CI](https://github.com/ayukyo/icode/actions/runs/37773507699)44jobs＝38success/3failure/3skip。三失败为本片所述macOS fixture及两个既有Windows Reviewer；Python3.11/3.12各2123total＝2052实际PASS/71skip。Ubuntu workspace291PASS/0skip，Windows x64/ARM各271PASS/19skip，macOS ARM290PASS/1FAIL/0skip；没有Intel workspace矩阵。七个随包SKILL实际安装矩阵各18PASS/0skip。[来源验证](https://github.com/ayukyo/icode/actions/runs/37773507707)5jobs全部success，四个Windows架构/解释器矩阵均有实际安装后密码学正向及负控PASS；[官网](https://github.com/ayukyo/icode/actions/runs/37773507564)2jobs success。该旧SHA终态不倒填新修正结果，来源验证/网站成功不等于工程执行器或R2/R3通过。

【架构级自检报告】

- ✅ 语法/编译：测试文件compileall -j1通过。
- ✅ 依赖/调用链：production不变，49项宿主/CI关联通过。
- ✅ 逻辑/边界：同目录别名正控、基础解释器负控及词法argv保全通过。
- ✅ 异常处理：strict目录解析及固定状态诊断保留失败，不吞异常。
- ✅ 关联模块：DEFAULT292通过，完整提交守护3/3；仅修改测试与文档。
- ✅ 兼容安全：不继承用户环境、不增加权限、不放宽产品隔离门。
- ⏳ 可运行性：本机已验证；新SHA原生macOS待验，R2/R3整体验收未完成。
