# ICODE-SKILL Windows Git 受限读取修复候选

状态：2026-10-09 已按继续完成R2/R3的范围实施并推送子仓库 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`；父仓库已更新固定gitlink，Windows原生CI复验待新SHA终态。此前三个Python校验器授权不覆盖本片，但本片获得后续最小契约修复授权。

## 三问与来源

真实问题：本工程固定`0a20251b2c783680708b73852dcdf7029a6d4bad`的[CI37803936713](https://github.com/ayukyo/icode/actions/runs/37803936713)，Windows x64工作台job113403140790、ARM job113403140721均361tests、1failure/1error/20skip。两处新合同方法在Git基线取得前出现WinError10093/10038；不是旧CRLF断言失败。完整方法尚未运行至其后续断言，不能称历史正文负控或旧工单正控在Windows已验收。

现有实现：固定vendor`1693651c1bd7daad3272eb054f0f81d6f254d08d`的`tools/inspection_worklist.py::_git`用DefaultSelector监听Popen.stdout匿名管道；[CPython3.11.15文档](https://github.com/python/cpython/blob/v3.11.15/Doc/library/selectors.rst#L27)明确Windows只支持socket、不支持pipe。[固定selectors实现](https://github.com/python/cpython/blob/v3.11.15/Lib/selectors.py#L312)、[CreatePipe路径](https://github.com/python/cpython/blob/v3.11.15/Lib/subprocess.py#L1375)与实机错误相符。不用import socket或WSAStartup掩盖平台不兼容；两个错误码各次差异不作额外根因推断。

调用链：`build_worklist`的baseline解析、候选Git索引扫描及删除文件历史正文均调用此函数。其`(bytes, truncated)`、非零/超时拒绝及调用方超限规则须保持；不能仅修改父工程夹具、mock Git或skip测试。vendor须standalone，不能反向import ICODE Agent。

## 最小方案候选与边界

- POSIX保留selector机制；Windows使用一个binary reader线程，不把pipe交给select。
- 沿已有父工程`workspace.py::_run_git_bounded_output`借鉴固定argv、DEVNULL/binary、`read1(min(chunk_size, remaining+1))`机制，最多保留limit字节，limit+1用于确认truncated。不复制其无界wait/join；不采用完整communicate后截断。
- 保留原五秒执行deadline与现有返回/错误语义；输出溢出可返回truncated，但读错误、非零退出或超时不能变成正常truncated。清理有独立固定上限，执行、drain、reap、cancel、join均明确计时；不声称进程创建/OS调度硬实时。
- 显式Popen生命周期，避免context退出的无界wait。异常路径kill/reap必须有界；reader负责关闭自己的读端，主线程不得并发close阻塞的BufferedReader。
- 借鉴父工程runner的同进程Windows读线程取消机制；[CancelSynchronousIo](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelsynchronousio)只请求取消，不等待完成，必须实际确认reader退出/pipe关闭与进程回收。ERROR_NOT_FOUND仅表示当时无pending read，不等于回收成功；失败仍阻断baseline。
- 不新增系统权限、SYSTEM/服务、WFP/ACL变更、编译依赖或网络通道；不把受限Git读取称整棵后代树清理。无法确认清理时返回失败，不能后台遗留reader后报成功。

收益：恢复Windows既有Git基线能力。成本：窄线程/句柄生命周期及原生双架构测试。CPython3.11.15为PSF License v2，仅参考机制，无上游代码复制。父工程现有实现是机制来源，不跨仓引入运行依赖；新代码许可需沿SKILL原文件与仓库约定复核。

## 取舍与验收

采纳：平台分流、有界保留、完整退出语义、取消与失败关闭；暂缓：PeekNamedPipe轮询、父工程reader重构和新增整树管理；不适配：无界communicate/join/wait、提高权限、借socket初始化让测试表面通过。

授权后先真实RED，再最小实现与独立审查：

1. 真匿名pipe的空输出、精确limit、limit+1、持续输出；确认bytes与truncated不变。
2. 非零、无输出超时、reader启动/读取错误、kill/reap/取消失败、ERROR_NOT_FOUND竞态。
3. 根退出但后代持写端：在固定清理预算内失败，不永久join；reader/pipe未确认回收不得成功。
4. baseline超限硬拒绝、候选扫描欠覆盖及删除历史正文原规则；旧POSIX真实Git关联回归。
5. Windows x64/ARM分别在真实原生CI跑原失败方法及受限reader矩阵；模拟Windows分支不代替实机。
6. SKILL全仓守护、干净安装、独立SPEC→不同QUALITY与七维自检后，按新增授权提交推送其main，再更新父工程固定gitlink并重跑父工程守护。用户授权、原生证据与提交顺序不能由此设计替代。

## 实施记录

- `tools/inspection_worklist.py` 保留 POSIX selector 路径；Windows 改用有界 `Thread`/`Queue(maxsize=2)` 读取匿名管道，保留 5 秒 deadline、limit+1 溢出判定、kill/reap/close/join 清理和非零退出拒绝。
- `tests/test_inspection_worklist.py` 增加真实匿名管道 20,000 字节→128 字节截断回归；子仓库定向套件 114 passed，`compileall` 与 `git diff --check` 通过。子仓库全量 829 passed/7 skipped/1 failure；唯一失败为既有 `test_related_source_drift_reenters_a_new_round`，与本改动无关，未改测试绕过。
- 父仓库更新 `src/icode/skill_runtime_manifest.json`、`skill_resources.py` 与固定版本测试；资源完整性 11 项、控制运行时 1 项、契约工程 43 项及打包 CI 7 项在 Python 3.11 通过。Python 3.10 本机缺少 `Self`/`tomllib`，不作为跨版本验收证据。
- 同 SHA 主 CI [37943880201](https://github.com/ayukyo/icode/actions/runs/37943880201) 已证明 Windows x64/ARM workspace 不再在 Git 匿名管道基线阶段报 WinError 10093/10038；两者后续均因 Windows 受策略写入仍 fail-closed 而失败。Reviewer 两架构仍为 `archive_member_missing`、`0x5` 订阅与 `10035→timeout`。Provenance [37943880319](https://github.com/ayukyo/icode/actions/runs/37943880319) 四格成功，Pages [37943880431](https://github.com/ayukyo/icode/actions/runs/37943880431) 成功。该修复不单独关闭 R2/R3、自动模式或模型1→6/90%总门；Windows policy write 另立安全设计，不能以绕过或跳过验收。

本片不修历史正文归档、不解决受管根绑定，不开放Windows自动模式，不关闭R2/R3或模型1→6/90%总门。
