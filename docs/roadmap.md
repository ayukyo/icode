# 开发路线图与取舍原则

- 日期：2026-10-01 Asia/Shanghai
- **CI #444 Windows R3 测试归属复核（commit `d14b7b7`）：**官网 workflow [#322](https://github.com/ayukyo/icode/actions/runs/36809562932) success；主 CI #444 因 Windows x64 原生 tree job 中额外选入的 `run_task` 集成测试失败而未通过，ARM64 同测试通过。公开 check-run annotation 只给出脱敏测试 ID，原始日志需登录且 API 返回 403，具体失败断言/根因未知。当前已将该集成测试移入跨平台 workspace 精选矩阵、改用 `require_skill()`，原生 Windows tree wrapper 恢复只跑生产 snapshot/tree-OID 模块；本机 workspace runner 167 项、Windows wrapper 47 项均通过，新 SHA 的跨平台/原生 CI 待验。该调整不表示已证明 x64 集成通过，也不改 R2/R3 readiness。R2 原生评分仍按 #443：Ubuntu 22.04 x64/ARM64 `8/10`（critical 通过、`ready=false`），较新 Ubuntu x64/ARM64 `7/10`（critical 未通过），macOS Intel/Apple Silicon `6/10`（critical 未通过）；资源限制/统一违规回执仍未闭合，自动模式关闭。
- **CI #443 R2/R3 状态刷新（commit `15d7e54`）：**完整 [CI #443](https://github.com/ayukyo/icode/actions/runs/36808015508) 与官网 [#321](https://github.com/ayukyo/icode/actions/runs/36808015545) 均成功。Windows x64 workspace 的 `run_task→tested tree→result commit` 集成回归通过；Windows x64/ARM64 生产 snapshot/tree 子门、authenticated runner pipe、Job cleanup 与 wheel 子门通过；Python 3.11/3.12、Linux/macOS workspace、Docker/Podman Reviewer 也通过。**R2 readiness 仍未通过：**Ubuntu 22.04 x64/ARM64 为 `8/10`、critical 通过但 `ready=false`；ubuntu-latest x64 与 Ubuntu 24.04 ARM 为 `7/10`、critical 未通过，真实 network lease expiry 因 runner namespace/AppArmor 条件 skip；macOS Intel/Apple Silicon 为 `6/10`、critical 未通过，Seatbelt numeric IPv4 port predicate 不受该 runner 支持，sandbox violation observation 不计统一回执。所有平台的 `resource_limits` / `uniform_violation` 仍无完整直接证据。Windows ARM64 的 run_task 结果 commit 集成尚未纳入 workspace 矩阵；Windows Reviewer 隔离命令和 WSL/策略化跨平台 Reviewer 仍未开放。标准用户/AppContainer 可选诊断 skipped。R2/R3 overall readiness 与自动模式不变。CI 子门 success 不替代这些缺项。
- **CI #441 与 R3 Windows ChangeTime 窄修候选（commit `55efa5a`）：**Windows authenticated runner pipe x64/ARM64 success；R3 ARM64 snapshot/tree job success，x64 在 `test_native_worktree_oid_matches_git_symlink_entry` 的 workspace snapshot 阶段因 `windows_directory_entry_change_time_changed` 失败，脱敏回执为 `eh_el+hr_same+dr_same+rh_el`。该回执表示两次跨来源比较均为枚举时间低于句柄时间，而句柄复读和父目录重复枚举各自稳定；它不是并发变化不存在的证明。代码候选仅对真实目录取消 entry-vs-handle ChangeTime 精确相等要求，继续检查卷/FileId、类型/reparse/delete 状态、父目录前后 listing signature、同一目录句柄前后 signature；普通文件与 symlink 仍严格比较。workspace snapshot 对观测到的目录变化仍最多完整重建一次，第二次失败关闭。本地 R3 聚焦 72 项（6 项 Windows 原生跳过）与跨平台 workspace CI 166 项通过；新 SHA 的 Windows x64/ARM64 验证尚未完成。本轮还把 task-tree、SHA-256 tree capture、result-commit binding 三个集成用例加入 workspace CI 矩阵。R2 readiness、R3 overall 与自动模式仍关闭。[CI #441](https://github.com/ayukyo/icode/actions/runs/36804382269) · [R3 x64](https://github.com/ayukyo/icode/actions/runs/36804382269/job/110185396868) · [R3 ARM64](https://github.com/ayukyo/icode/actions/runs/36804382269/job/110185396761) · [pipe x64](https://github.com/ayukyo/icode/actions/runs/36804382269/job/110185396922) · [pipe ARM64](https://github.com/ayukyo/icode/actions/runs/36804382269/job/110185396899)
- **CI #440 当前 R2/R3 状态（commit `fdd01b7`）：**生产 Windows authenticated runner pipe 的真实 round-trip 在 [x64](https://github.com/ayukyo/icode/actions/runs/36802466209/job/110179622635) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36802466209/job/110179622426) 均通过。生产 DACL 仅对精确 Logon SID ACE 增加 `FILE_READ_ATTRIBUTES (0x80)`，客户端请求掩码仍为 `0x00100003`；既保留随机 pipe、单实例、远端拒绝及连接后 PID 校验。结果与 #439 的受控 A/B 相符，但不证明该位是 Windows API 的普遍必要条件或底层拒绝根因。完整主 CI [#440](https://github.com/ayukyo/icode/actions/runs/36802466209) 和官网 [#318](https://github.com/ayukyo/icode/actions/runs/36802466217) 均 success；R3 Windows tree/snapshot 双架构、Docker/Podman Reviewer、Job/wheel 子门通过。R2.2 仍为 Ubuntu 22.04 `8/10`、较新 Ubuntu `7/10`（network lease expiry 因 runner namespace/AppArmor 条件 skip）、macOS `6/10`，均 `ready=false`；标准用户/AppContainer 诊断 skipped。本地 Python 3.11.15 的完整 preflight 三门通过。R2/R3 overall 与自动模式仍未完成。
- **CI #439 当前 R2/R3 状态（commit `1ec5c7a`）：**Windows authenticated pipe 生产 `CreateFileW` 在 x64/ARM64 仍 `ERROR_ACCESS_DENIED (5)`；但新受控 DACL A/B 两架构都得到 `base_access_denied+with_attribute_opened+shape_mask_only`：保持 SID、server/client 参数与请求掩码不变，仅给第二个临时 ACE 加 `FILE_READ_ATTRIBUTES (0x80)` 后打开成功。该结果支持下一切片仅在生产 Logon-SID DACL 增加此位、客户端请求掩码保持 `0x00100003`，仍须新 SHA 的生产双架构 round-trip 验证。R2.1 workspace、R2.3 Windows Job/wheel、R3 Windows tree/snapshot、Docker/Podman Reviewer 及 Python 3.11/3.12 子门成功；R2.2 readiness 仍是 Ubuntu 22.04 `8/10`、其它 Ubuntu `7/10`、macOS `6/10`，全部 `ready=false`。macOS Intel 的本轮 Seatbelt AF_UNIX 候选步骤成功，#438 同步骤失败未重现；Intel 与 Apple Silicon 的 `SO_ACCEPTCONN` 注记仍为 `ENOPROTOOPT`，但不是此次失败依据。标准用户/AppContainer 可选诊断 skipped；R3 其它 OS/策略 Reviewer 尚未全覆盖。R2、R3 overall 和自动模式继续关闭。[整轮 CI #439](https://github.com/ayukyo/icode/actions/runs/36801218459) · [Windows x64 pipe](https://github.com/ayukyo/icode/actions/runs/36801218459/job/110175761466) · [Windows ARM64 pipe](https://github.com/ayukyo/icode/actions/runs/36801218459/job/110175761437) · [macOS Intel R2.2](https://github.com/ayukyo/icode/actions/runs/36801218459/job/110175762509)
- **CI #409 与 R3 Linux Reviewer 根目录 FD 门（commit `2c9766650c715b11e2a9937389eaf60504ca324`）：**Linux x64 [原生 job](https://github.com/ayukyo/icode/actions/runs/36715769899/job/109888179192) 与 ARM64 [原生 job](https://github.com/ayukyo/icode/actions/runs/36715769899/job/109888179163) 均实际运行根目录替换负例，测试通过；Windows R3 directory/relative-open x64、ARM64 jobs 与 R2.3 Job cleanup/wheel 双架构 jobs、Python 3.11/3.12、跨平台 workspace 及站点作业通过。整轮仍因 Windows authenticated runner pipe x64/ARM64 失败：两边真实 `CreateFileW` 都是 `ERROR_ACCESS_DENIED (5)`，固定回执 `runner_pipe_open_access_denied;self_pipe_denied:self_access_allow;temporary_dacl=doappn_udappm`；不据 AccessCheck 推断根因，也不扩生产 ACL。R2.2 job success 不等于平台 ready：Ubuntu 22.04 x64/ARM64 各 `8/10`、critical true、`ready=false`；ubuntu-latest x64 与 Ubuntu 24.04 ARM 各 `7/10`、critical false（网络 allowlist expiry skipped）；macOS Intel/Apple Silicon 各 `6/10`、critical false、`ready=false`。Windows AppContainer/标准用户可选作业 skipped。根目录 FD 固定对象身份，不冻结目录内容；R3 整体、R2 跨平台 ready 与自动模式仍未完成。[整轮 CI #409](https://github.com/ayukyo/icode/actions/runs/36715769899)
- **CI #408 历史基线（commit `30f84edc33ecb3ebe748c99793ae7c9bdcebfa1d`）：**Windows x64/ARM64 的生产快照与 Git tree OID job（[x64](https://github.com/ayukyo/icode/actions/runs/36709199744/job/109866657931)、[ARM64](https://github.com/ayukyo/icode/actions/runs/36709199744/job/109866657896)）及 R2.3 Job 清理作业双架构成功；authenticated runner pipe 双架构实际打开仍被拒绝。该轮为 #409 的历史前序，不代表新根目录 FD 门已验收。[CI #408](https://github.com/ayukyo/icode/actions/runs/36709199744)
- **CI #404（commit `b83083247a172e273bc901ec05663f8ed9e6476b`）R3 双架构复验：**主 CI 总体 success；Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36700817484/job/109839570477) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36700817484/job/109839570197) 均通过经安全 wrapper 调用的生产 `tests.test_windows_worktree_tree_oid`。该 SHA 未改 Windows walker/生产测试代码；CI #401 的 x64 失败此次未重现，但原失败测试与根因仍未知，不声称已修复。当前 Windows snapshot/tree 双架构子门有新成功证据，R3 其它 Reviewer OS/策略边界仍未关闭。R2 最新 notice 仍为 Ubuntu 22.04 x64/ARM64 `8/10, critical=true, ready=false`；ubuntu-latest/24.04 ARM `7/10, critical=false, ready=false`；macOS Intel/Apple Silicon `6/10, critical=false, ready=false`。部分 Linux network-expiry 探针 skipped，Windows AppContainer/标准用户诊断仍 skipped；macOS worker 网络 DENY、所有平台 R2 readiness 与自动模式不变。[CI #404](https://github.com/ayukyo/icode/actions/runs/36700817484)
- **CI #401 R3 Windows 生产快照复验（commit `555001c90f902f725119012c16f7d3996a264f75`）：**主 CI 中 Windows ARM64 `R3 Windows directory and relative-open probes` 成功，Windows x64 的 `Verify production Windows snapshots and Git tree OID` 单步失败；Windows 目录记录/相对打开前置 probe 成功。公开 annotations 只有步骤退出码，原始 unittest 日志当前需 GitHub 登录权限，无法确认具体断言或根因。其余 Python 3.11/3.12、Linux/macOS native、workspace、Windows Job/wheel 与站点作业成功；AppContainer/标准用户可选诊断仍 skipped。此前 CI #399 双架构成功不能覆盖这次 x64 失败；Windows R3 快照/tree 原生子门暂不关闭，须在可见具体失败信息并复验 x64/ARM64 后再判断。R2/R3 readiness 与自动模式状态不变。 [CI #401](https://github.com/ayukyo/icode/actions/runs/36696603232) · [x64 job](https://github.com/ayukyo/icode/actions/runs/36696603232/job/109825959048) · [ARM64 job](https://github.com/ayukyo/icode/actions/runs/36696603232/job/109825959054)
- **CI #401 R2 conformance 复核：**Ubuntu 22.04 x64/ARM64 各 `8/10`、critical 通过、`ready=false`；ubuntu-latest/Ubuntu 24.04 ARM 各 `7/10`、critical 未通过，network-allowlist-expiry 为 `skipped`，不计通过。macOS Intel/Apple Silicon 均 `6/10`、critical 未通过；production UDS/SOCKS 测试的获批域名正例与未批准域名拒绝均成功，但 notice 明确 `conformance_credit=none`；旧 localhost 同端口规则仍能连接宿主非 loopback active listener，不能作为授权网络路径。Windows AppContainer/standard-user 诊断仍 skipped。worker 网络继续 DENY、所有平台 `ready=false`。详见[持续竞品对照](./agent-landscape-live.md) 与 [CI #401](https://github.com/ayukyo/icode/actions/runs/36696603232)。
- **CI #382 双架构结果与 pipe 诊断回执补齐（观察 2026-09-29 UTC）：**手动 [CI #382](https://github.com/ayukyo/icode/actions/runs/36643898194) 在 Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36643898194/job/109662294368) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36643898194/job/109662294353) 得到一致结果：标准用户的真实 `CreateFileW` 为 `ERROR_ACCESS_DENIED`；self-pipe 与 parent pipe 的 `AccessCheck` 均为 allow；LogonSID ACE 匹配；八种 desired-access 均拒绝；实际令牌摘要为 process token、logon SID enabled、`restricted_no`（不是 OS restricted token）。独立 no-RX 对照仍 `DENIED` 且 marker/residual absent。并行复核发现同一次 child run 已执行 default-DACL、TokenUser-only、TokenUser+`FILE_CREATE_PIPE_INSTANCE` 三个临时 pipe 对照，但旧格式化器在矩阵存在时覆盖其标签。本地 TDD 修复把“八项全 `d5`”压缩为 `mask_all_d5`，同时优先保留三项 DACL 状态、token/logon 与 WinError，子回执仍不超过 120 字符；没有新增对照或扩大 ACL。下一步以新 SHA 重跑双架构，读取这些已做对照的结果；它们仍只是诊断证据，不是根因或 R2 通过。Linux/macOS readiness、Windows 自动模式和 R3 完整 tree OID 继续关闭。
- **CI #380 Windows pipe 矩阵回执丢失与解析器修复（观察 2026-09-29 UTC）：**手动 [CI #380](https://github.com/ayukyo/icode/actions/runs/36641829762) 在 Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36641829762/job/109655640035) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36641829762/job/109655640114) 都失败，注释仅显示 `standard_user_token_probe_failed RuntimeError`；两边独立 no-RX 对照仍是 `DENIED` 且无 marker/residual。源码路径显示 self-pipe denied 后会运行八掩码临时 pipe 矩阵，但实际矩阵取值未从该 run 的安全过滤回执中恢复，故不能把这次 run 当作任何 mask 结果或根因证据。定位到父错误过滤器只允许固定上下文中的字母/`_`/`+`，而安全矩阵标签含数字 `d5`；本地新增的回归测试先 RED，最小修复只允许 ASCII 数字进入同一有限字符白名单，路径/任意异常文本仍被拒绝，原路径隐私测试保留；探针模块 83/83 通过。并行上游研究：Codex 固定 commit [`9212b3e`](https://github.com/openai/codex/commit/9212b3eca86e6eca061b15fe9f8971ca57ebe3c9) 的 tool output 显式关联调用并标明失败；Gemini CLI [`38700b4`](https://github.com/google-gemini/gemini-cli/commit/38700b4b38bf387dafded6c97c3f190d084b49e9) 分离模型内容、UI 展示与执行失败类别。**采纳**结构化失败状态与展示隔离；**不采纳**原样透传错误正文，ICODE 继续只显示经过字符集、长度及字段边界校验的固定 receipt；无复制源码/运行时依赖/许可影响。下一步完整 preflight、提交后重跑双架构原生探针；Windows/R2/R3 readiness 与自动模式继续关闭。
- **Windows R2 权限位矩阵探针（2026-09-29 UTC；native 待验）：**基于 #378 x64/ARM64 同时出现的 `AccessCheck=allow` / 实际 `CreateFileW=ERROR_ACCESS_DENIED`，并行只读复核与 Microsoft API 文档支持把“requested access mask”作为下一项可区分变量，但不支持由 AccessCheck 推断 open 结果。新增 test-only 临时管道矩阵，保持 logon-SID DACL、`OPEN_EXISTING`、overlapped/SQOS flags 不变，仅遍历零、READ、WRITE、READ|WRITE、SYNCHRONIZE 及其组合共八种 `dwDesiredAccess`。成功的 client handle 当即关闭，不调用 connect/读写/发送；每项错误码进入 ≤120 字符安全回执。新边界测试先 RED 再 GREEN；探针模块 82/82、`compileall` 和 `git diff --check` 通过。完整 preflight 与新 SHA x64/ARM64 手动 native 验收待跑；#378 本身仍失败，不将其当成新实现证据。无生产 ACL、管道协议、ready 评分、运行模式或依赖更改；Windows 自动模式以及 R2/R3 readiness 保持关闭。下一步执行完整预检、推送后重跑双架构标准用户 gate，根据 mask 矩阵结果决定是否还需 token-statistics/descriptor 级跟踪。[Microsoft CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew) · [Named Pipe Security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)
- **CI #378 同进程与跨进程 pipe 诊断结果（观察 2026-09-29 UTC）：**[run #378](https://github.com/ayukyo/icode/actions/runs/36637329583) 运行提交 `dd6d084`，x64 [standard-user job](https://github.com/ayukyo/icode/actions/runs/36637329583/job/109641266292) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36637329583/job/109641266323) 回执一致：子进程真实 parent-pipe `CreateFileW` 得 `ERROR_ACCESS_DENIED`，子进程主 token `AccessCheck=allow`；新增 `self_access_allow` 表示同进程 self-pipe 的只读 AccessCheck 也允许（该标签只在 self-pipe 的实际 client-open denied 分支生成），故相同矛盾也发生在同进程临时 pipe。它仍不揭示拒绝原因，也不证明 AccessCheck/描述符/实际 open 的等价。两架构 no-RX 负例继续 `DENIED` 且 marker/residual absent；Python 3.11/3.12、Windows Job/wheel 与受控 NTFS directory/tree 子门通过。Linux native 为 7/10 或 8/10，四个 runner 均 `ready=false`；macOS 两架构 6/10 且 `ready=false`。Windows R3 通过项只覆盖受控 fixture，不能证明生产递归快照/tree OID。完整 run 因 Windows standard-user pipe jobs 失败而未通过；自动模式继续关闭、不扩大 ACL。CI 显示竞品页“最近观察日期在未来”提示；本地已将 [对照页](./agent-landscape-live.md) 的观察日按时钟修正为 `2026-09-29 UTC`，并把下次复核设为 10-29。
- **CI #376 双架构 pipe 诊断与回执下一步（观察 2026-09-29 UTC）：**手动 [CI #376](https://github.com/ayukyo/icode/actions/runs/36633503016) 指向 commit `484f099f86bcccdde9c83401c0efc47c6c8e4ba4`；Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36633503016/job/109628539474) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36633503016/job/109628539396) 的标准用户主 pipe 都在真实 `CreateFileW` 得 `ERROR_ACCESS_DENIED`。子进程侧记录 `token_process+logon_enabled`；父端对服务端 DACL 和子进程主 token 的独立 `AccessCheck=allow` 仍不能解释实际拒绝。临时 TokenUser DACL 的 `CreateFileW` 与 `FILE_CREATE_PIPE_INSTANCE` 单权位对照均拒绝；默认 DACL 对照成功；独立 no-RX 负例两架构通过且无 marker/residual。该轮其它 matrix jobs 通过，但这些子门不等于 R2/R3 readiness 或生产 tree OID，Windows 自动模式保持关闭。只读复核指出同进程 self-pipe 已算出 AccessCheck 结果，却未进入主失败 receipt；本地新增固定枚举 `self_access_allow/deny/unavailable`，在 ≤120 字符回执内保留真实 token/logon、self-pipe AccessCheck、关键后续 A/B 和父端可提取 WinError。78 项探针模块测试、compileall、diff-check 通过；全量 preflight 与该 SHA 双架构 native CI 待本次推送后验证。无 ACL、生产 pipe、评分或运行策略改动。[Microsoft AccessCheck](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck) · [Named Pipe Security](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights)
- **CI #374 最新验收状态与回执修正（观察 2026-09-30 UTC）：**Windows x64 [standard-user job](https://github.com/ayukyo/icode/actions/runs/36630197765/job/109617508161) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36630197765/job/109617508255) 的真实 `CreateFileW` 仍 `ERROR_ACCESS_DENIED`；临时 TokenUser ACE 从 `0x00100003` 加 `FILE_CREATE_PIPE_INSTANCE` 到 `0x00100007` 仍失败，默认 DACL 对照成功，独立 no-RX 负例通过且无 marker/residual。runner 诊断的 `AccessCheck=allow` 不是实际 open 证据；子进程 token 回执在超长压缩时错误退化为 `token_unavailable`，因此当次不能确定子进程真实 token 字段。本地 test-only 修复保留实测 token 来源与 logon SID 状态，目标模块 77 项通过，完整 preflight 三道门已通过，新 SHA 双架构手动 CI 待验。R3 Windows directory/relative-open、R2.3 cleanup 与 wheel jobs 通过，但只覆盖这些子门，不证明 Windows R2 或生产 tree OID。继续停止 ACL 扩权，R2/R3 readiness 不成立，Windows 自动模式关闭；下一步推送后重跑标准用户原生探针。[CI #374](https://github.com/ayukyo/icode/actions/runs/36630197765) · [Microsoft named-pipe rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights) · [AccessCheck](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-accesscheck)
- **此前 CI #371 的 Windows ACL 权限掩码假设已在 #374 收窄：**固定 Codex [`runner_pipe.rs`](https://github.com/openai/codex/blob/193632d2448f6b0e9860faab8d6495124e266772/codex-rs/windows-sandbox-rs/src/elevated/runner_pipe.rs) 仍仅作机制参考；本轮 test-only `0x4` 单权位对照失败，停止继续扩大 ACE，`FILE_ALL_ACCESS` 不再作为下一候选。官方文档将 `FILE_CREATE_PIPE_INSTANCE` 的额外要求限定为服务端 `CreateNamedPipe` 打开已有管道名的场景，不能据此解释客户端 `CreateFile` 被拒。产品 ACL、ready 评分和自动模式均未改。[官方 named-pipe rights](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights) · [file access constants](https://learn.microsoft.com/en-us/windows/win32/fileio/file-access-rights-constants)
- **本机清理与回执复核更新（2026-09-29 UTC）：**追加了安全描述符缺失/释放失败、服务端 handle 回收以及 parent receipt parser 透传回归；标准用户探针模块 76 项通过，compileall/diff-check 通过，完整 preflight 正复验，native 双架构待 CI。前述宽权限决策、产品 ACL 与自动模式保持不变。
- **macOS 研究边界（2026-09-29 UTC）：**固定版 Codex Seatbelt 的 localhost TCP proxy 和 AF_UNIX 规则只作机制对照；ICODE 当前 UDS 代理 canary 不计产品隔离证据。自定义 SBPL 支持边界及 EndpointSecurity entitlement/扩展依赖不符合 pip-only，因此继续拒绝 macOS 自动模式，优先做 test-only UDS 路径安全和 lease 撤销测试。详见[持续竞品对照](./agent-landscape-live.md)。
- **CI #369 原生结果与下一切片（ICODE commit `5df16ed740c5c52fed6481a530dee5fdc4a728b0`，2026-09-29 UTC）：**Windows x64/ARM64 的临时标准用户 pipe 均复现 logon-SID ACL、no-SYNCHRONIZE、no-OVERLAPPED 打开失败；仅诊断默认 DACL pipe 两架构 `default_dacl_ok`。该默认 descriptor 对 Everyone/anonymous 有 read，不作为产品权限方案。下一候选仅在随机、拒绝远端、不传数据的临时 pipe 上改用当前 TokenUser SID，保持 ICODE 最小 `0x00100003` ACE、client flags/SQOS、PID 校验和句柄回收；采用已有 TokenUser helper，用户 SID 跨同账户登录会话的范围较宽，故不触产品 ACL。此处借鉴 Codex [`runner_pipe.rs`](https://github.com/openai/codex/blob/8ffd91e42aa001b7e897bea812b02f89264f9fa0/codex-rs/windows-sandbox-rs/src/elevated/runner_pipe.rs) 的 sandbox-user 身份限定思路，不采纳源码中的 `GA` 宽权限。当前实现的 69 项探针模块测试通过；完整 `scripts/preflight.py` 三道门通过，新 SHA 双架构 native 结果待验。R3 Windows directory/relative-open 两 job 单独成功：[x64](https://github.com/ayukyo/icode/actions/runs/36619596191/job/109581484807)、[ARM64](https://github.com/ayukyo/icode/actions/runs/36619596191/job/109581484916)，但受控 NTFS probes 仍不保证递归原子快照/tree OID。整轮 [CI #369](https://github.com/ayukyo/icode/actions/runs/36619596191) 失败；Linux 7/10 或 8/10、macOS 两架构 6/10，所有平台 `ready=false`；Windows AppContainer 作业仅诊断且失败。R2/R3 均未完整验收，自动模式继续关闭。
- **CI #367 状态与下一切片（commit `980d099`，2026-09-29 UTC）：**[整轮](https://github.com/ayukyo/icode/actions/runs/36615581946)因 Windows 标准用户 pipe 与 AppContainer 诊断 jobs 失败；标准用户 x64/ARM64 都复现 `self_pipe_denied+nosync_noovl_denied`、`winerror=5`，独立 no-RX 负例仍通过。R3 directory/relative-open Windows x64/ARM64 jobs 均通过，但这只是受控 runner 原语，不证明递归原子工作区快照或 Windows tree OID。Linux Ubuntu 22.04 x64/ARM64 均 `8/10` 且 critical pass，仍 `ready=false`；其他 Linux jobs 为 `7/10`，macOS 两架构 `6/10`，无平台 ready。下一步在 test-only 临时 pipe 上仅对比默认 DACL 与显式 logon-SID DACL；Microsoft 文档揭示默认命名管道 descriptor 允许 Everyone/anonymous read，故不接入产品、不承载数据、不调整生产 ACL；待新 SHA 双架构 native CI。R2/R3 未完成、自动模式保持关闭。细节见[Windows R2 计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)与[持续竞品对照](./agent-landscape-live.md)。
- **CI #365 结果拆分（commit `88cd67e`，2026-09-29 UTC）：**Windows x64 [standard-user job](https://github.com/ayukyo/icode/actions/runs/36612391379/job/109557123554) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36612391379/job/109557124104) 的 no-RX 负例通过且无 marker/residual，但临时标准用户同令牌自建 pipe 与 parent pipe 都在 `CreateFileW` 被拒；no-SYNCHRONIZE A/B 两架构仍 denied。R3 directory/relative-open 两个独立 job 双架构成功：[x64](https://github.com/ayukyo/icode/actions/runs/36612391379/job/109557123673)、[ARM64](https://github.com/ayukyo/icode/actions/runs/36612391379/job/109557123614)，但只是受控 NTFS fixture，不等于生产递归快照/tree OID。Linux native 分别 7/10 与 8/10、macOS 两架构 6/10，均 `ready=false`；AppContainer 仍只是失败的诊断 job。本机新 no-OVERLAPPED 打开诊断的模块 61 项与完整 preflight 三道门通过，尚未进 CI；未触生产 pipe 或评分。完整 R2 未验收，Windows 自动模式关闭。
- **CI #363 结果拆分与后续门禁（2026-09-29 UTC）：**R3 Windows directory/relative-open 测试在 x64 与 ARM64 各 33 项全部通过，分页候选首次在双架构原生 job 验收；仍只算受控 NTFS fixture，不是生产 tree OID/原子快照。R2 Windows 临时普通用户主 pipe 与同令牌自建 pipe 在两架构均 `CreateFileW ERROR_ACCESS_DENIED`；下一切片仅诊断 A/B 删除请求掩码中的 `SYNCHRONIZE`，保留 DACL 与其余 flags，未改生产掩码。Linux R2 native 从 7/10 到部分 Ubuntu 22.04 的 8/10，`ready=false`；macOS 两架构 6/10，端口规则仍报 `unsupported_host_predicate`。R2 继续不验收，Windows 自动模式关闭；R3 仅分页子门通过。
- **CI #361 标准用户探针拆门（commit `08951f6`）：**Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36605871993/job/109535048719) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36605871993/job/109535048317) 均确认独立 no-RX 可执行文件负例为 `DENIED`、无 marker/残留；但父子 runner pipe 主握手仍在 `CreateFileW` 报 `ERROR_ACCESS_DENIED`，所以 Windows pipe/R2 门未通过。回执的 `AccessCheck=allow`、DACL ACE 匹配、medium token 与未标记 pipe 仍不能定位拒绝原因。历史 CI #168 使用 commit `7332a22`，早于 named-pipe 模块提交 `b1962cf`，不构成 pipe 正向证据。当前新增仅分类自建 pipe 负向探针结果的安全化标签，双架构 native CI 待复测；不改 ACL/desired access，不开放 Windows 自动模式。详见 [R2 Windows 计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md) 与 [持续竞品对照](./agent-landscape-live.md)。
- **R2 Windows 无 RX 负例修正（本机验证先于 #361）：**CI [#359](https://github.com/ayukyo/icode/actions/runs/36600896933) x64/ARM64 都在 runner pipe 客户端 `CreateFileW` 遇到 access denied，旧版 no-RX 检查未执行；候选因此移至父进程，在启动 pipe runner 前，以临时普通账户 `CreateProcessWithLogonW(CREATE_SUSPENDED)` 直接尝试启动 scratch 中只对该 SID 拒绝 RX 的 `cmd.exe` 副本。此本机切片的 5 个定向用例、Windows 探针模块 55 项及 Python 3.11.15 下完整 preflight 三道门均通过；后续 CI #361 已双架构确认此 no-RX 子门，但 pipe 仍失败（见上条），不解锁 R2 readiness 或自动模式。详见 [R2 Windows 计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)。
- **CI #357 R3 分页双架构复验（commit `04b0b90`）：**Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36596536428/job/109502781225) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36596536428/job/109502781415) 的有界目录 fixture probe 通过 96 文件精确枚举、同句柄 restart rescan 与空目录。该子门仅支持受控 fixture，不代表生产递归快照或 tree OID；CI 总体失败源于仍运行的仅诊断 AppContainer read-handle jobs，Winsock `10060` 仍不作网络拒绝证据。Windows 自动模式继续关闭，详见 [CI #357](https://github.com/ayukyo/icode/actions/runs/36596536428) 与 [R3 计划](./nbl/plans/2026-09-26-r3-self-verification.md)。
- **CI #356 分页诊断与下一候选（CI 观测 2026-09-29；本机修正 2026-09-30）：**Windows x64/ARM64 的 R3 分页用例记录 restart 调用成功且缓冲非零，但没有解析出可用目录项；由于 parser 过滤点目录项，这与首个 restart 页只含 `.` / `..` 相符，具体内容仍未由 CI 证实。本机候选只允许首个 restart 页一次过滤后为空并继续普通信息类；严格全零成功缓冲可作 EOF，后续非零无进展仍拒绝。R3 focused/regression 104 项通过（7 skipped），完整 `scripts/preflight.py` 三道门通过；候选仍待新双架构 native CI 验证。CI #356 的退役 AppContainer 诊断双架构仍各 `18/20`、live/control Winsock `10060`，不视作网络拒绝；自动模式继续关闭。见 [CI #356](https://github.com/ayukyo/icode/actions/runs/36590470289) 和 [R3 计划](./nbl/plans/2026-09-26-r3-self-verification.md)。
- Windows R2/R3 开发边界刷新（2026-09-29）：AppContainer 在正式设计中仅保留诊断用途；批准的 UAC + 专用身份 + WFP/ACL/Job 产品路线仍无产品 helper，必须先做 setup/凭据/runtime 可达性及 BFE/整机重启原生验证，自动模式继续关闭。R3 test-only 同目录句柄两次观察漂移分类在 CI #354 的 Windows x64/ARM64 各 25 项通过。新增分页/EOF helper 目前仅本机纯测试通过，Windows native 还待下一轮 CI；官方文档描述 restart/continuation 但未规定精确 EOF Win32 code，故不作原生完成声称。即使验收，也仅覆盖受控目录 fixture，不等于递归/原子快照或 tree OID。详见[R2 Windows 计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)、[R3 计划](./nbl/plans/2026-09-26-r3-self-verification.md)和[持续竞品对照](./agent-landscape-live.md)。
- **CI #354 总体结果（commit `f709296`）：**Python、跨平台原生 R2.1/R2.2、Windows wheel/Job、R3 x64/ARM64 等必需工作通过；整体唯一失败为 R2 Windows AppContainer 诊断 x64/ARM64 jobs 均 `18/20`，`process_exit_zero` 和 `network_isolation_denied` 失败，live/control Winsock `10060`。这不是网络拒绝因果证据；AppContainer 仅诊断，UAC 产品路线待实现。见 [CI #354](https://github.com/ayukyo/icode/actions/runs/36584911096)。
- **CI #355 分页原生回归（commit `7cd036e`）：**R3 Windows x64 与 ARM64 pagination job 各运行 30 项；新用例都在终止页以 `directory_enumeration_no_progress` 失败。CI #355 还因已退役为诊断的 AppContainer x64/ARM64 网络门各 `18/20` 而整体失败。本地窄修正增加页响应布尔摘要，候选只接受 `ERROR_NO_MORE_FILES` 或严格零填充成功页，并保留非零空解析页失败关闭；等待新双架构 CI 验证。Windows OID、自动模式未开放。见 [CI #355](https://github.com/ayukyo/icode/actions/runs/36587999696)。
- CI #353（commit `9ffeed4`）：R3 Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36581740106/job/109451391664) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36581740106/job/109451391948) 各通过现有 23 项原生用例；本地后续新增的双观察用例未包含于该 SHA。R2 AppContainer x64/ARM64 均重现 stage 5 `18/20`，两个连接超时、NetIso `INTERNET_CLIENT=2`，严格网络门继续关闭；主 CI [#353](https://github.com/ayukyo/icode/actions/runs/36581740106) 因此 failure，官网 [#248](https://github.com/ayukyo/icode/actions/runs/36581740118) success。
- CI #350（commit `7a4d957`）确认 macOS Intel 与 Apple Silicon 的 `SO_ACCEPTCONN` 整数和 4-byte buffer getter 均为 `errno=42/ENOPROTOOPT`，`SO_TYPE` buffer control 正常；这与固定 XNU 源码一致，说明不是 Python 返回值解码问题。当前 test-only 修复由 canary 自己创建、bind/listen 的同一个 loopback socket；仅在 Darwin 精确遇到 `ENOPROTOOPT` 时，对该 socket 的构造期查询临时使用已知 `listen()` 来源，不改生产 validator，也不把 getter 当作内核证据。Linux 本机 R2 聚焦回归 51 项通过、3 项 macOS 原生跳过，完整 preflight 与新双架构 CI 待验证。Windows AppContainer 双架构仍各 `18/20`，live/control 均 `10060`、NetIso `INTERNET_CLIENT=2`，网络门与自动模式继续关闭。主 CI [#350](https://github.com/ayukyo/icode/actions/runs/36574295287) 仍失败于四项原生网络门；官网 [#245](https://github.com/ayukyo/icode/actions/runs/36574295394) 成功。
- CI #351（`db2ffad`）：macOS Intel [job](https://github.com/ayukyo/icode/actions/runs/36577798714/job/109437809979) 与 Apple Silicon [job](https://github.com/ayukyo/icode/actions/runs/36577798714/job/109437809667) 均越过代理构造并完成 approved-domain HTTP tunnel；blocked-domain 仍 fail-closed，notice 明确记录 getter 仍为 ENOPROTOOPT、此路径没有 conformance credit。Windows AppContainer 两架构虽构建成功且执行到 stage 5，仍 `18/20`：`process_exit_zero` 与 `network_isolation_denied` 失败，活跃/控制连接均 10060，不能归因网络拒绝。R3 既有单文件探针双架构通过；本地新 share-mode × namespace mutation 矩阵 23 项中 19 通过、4 项 Windows 原生跳过，待 CI #352。主 [CI #351](https://github.com/ayukyo/icode/actions/runs/36577798714) 仍失败于 Windows AppContainer 门，R2/R3 未验收、Windows 自动模式与 worker 网络继续关闭。
- R3 Windows 目录共享矩阵（CI #352，提交 `145f62f`）：x64 [job](https://github.com/ayukyo/icode/actions/runs/36579957568/job/109445204521) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36579957568/job/109445204558) 均在 NTFS 跑过 23 项。两边观测一致：无句柄基线全允许；parent `FILE_SHARE_READ` 时 create/delete 与 junction remove/create 仍允许，rename/replace 报 sharing violation；`READ|WRITE` 或 ALL 时本矩阵操作全允许。它证明的是该 runner 上这些调用的结果，不把原因外推为父目录锁，也不证明快照。CI #352 整体仍因 AppContainer x64/ARM64 的两个网络断言失败（各 `18/20`，stage 5）；Windows tree OID 与自动模式仍关闭。
- CI #349（commit `d07b93f`）：Python 3.11/3.12、Linux/macOS 基础探针及 Windows R3 bounded-reader x64/ARM64 jobs 通过；Windows AppContainer x64/ARM64 仍各 `18/20`，活跃 listener 与同地址 bound-but-not-listening 控制端口均为 Winsock `10060`，因此端口比较 `inconclusive`，NetIso 仍为 `INTERNET_CLIENT=2`；macOS Intel/Apple Silicon 仅 listener `SO_ACCEPTCONN` 查询失败，其余已记录前置事实通过。新一轮只读 errno/buffer-form 诊断待 CI。R3 Windows 本轮 21 项双架构通过只覆盖单文件 identity/read 合同，不是递归快照。主 CI [#349](https://github.com/ayukyo/icode/actions/runs/36570938004) 失败原因仍为上述 4 个 R2 原生网络 jobs；官网 [#349](https://github.com/ayukyo/icode/actions/runs/36570938035) 成功。R2/R3 未验收，Windows 自动模式、worker 网络仍关闭。
- R3 Windows 枚举身份绑定的有界文件读取（2026-09-29）：提交 [`1fd7251`](https://github.com/ayukyo/icode/commit/1fd72513a3f08b17fe10d0e785f772fecbb2c6ee) 的原生基线在 CI #346 Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36556408411/job/109366509523) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36556408411/job/109366509728) 均通过；本轮追加两个 test-only 断言：FileId 不匹配时底层读取原语零调用，实际 reader handle 存续时写入与 DELETE 打开均收到 `ERROR_SHARING_VIOLATION`。本机聚焦模块 21 项（18 通过、3 Windows 原生用例跳过），新增断言仍待下一次 x64/ARM64 原生 CI。CI #346 整体失败仅因 R2 AppContainer job，详见下条。该探针不接入 `snapshot_workspace`、不签发 Windows tree OID，不证明原子整树快照；R2/R3 与自动模式状态不变。详见[R3计划](./nbl/plans/2026-09-26-r3-self-verification.md)与[持续竞品对照](./agent-landscape-live.md)。
- R3 Windows 文件名 ABA 原生验证（2026-09-29，CI #344 双架构通过）：提交 [`80e6b07`](https://github.com/ayukyo/icode/commit/80e6b0779abe053c765137b7d65e21558eef5b23) 在 test-only 探针中按 A→缺失→B→A 变换同一名字，使用 held directory handle 相对打开并比对 volume + 128-bit FileId；缺失叶节点还精确返回 `STATUS_OBJECT_NAME_NOT_FOUND` (`0xC0000034`)。Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36549176322/job/109342834763) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36549176322/job/109342834657) 均通过；目标模块 18 项（本机 15 pass/3 native skip），Python 3.11 完整 preflight 三门通过，独立审查无阻断。该实验只证明托管 NTFS 上受控顺序的名称解析，不证明任意并发 ABA 或原子树快照；不接入生产 snapshot，不签发 Windows tree OID，R3 Windows 仍未完成。
- R2 全平台门槛刷新（CI #346，提交 `1fd7251`）：两个必需 Windows AppContainer job 均构建并运行到 `native_stage=5`，各 `18/20`，失败项仍是 `process_exit_zero` / `network_isolation_denied`；x64/ARM64 均为 Winsock `10060`、NetIso `INTERNET_CLIENT=2`、WFP 没有回调，证据为 `evidence_unavailable`。连接超时仍不计 OS 拒绝，也不能归因到 WFP；其余句柄、路径、token、Job 清理和 DACL 恢复检查通过。匿名 job 日志 API 返回 403，已登录页面有脱敏摘要；两架构同 #343/#344 失败签名相同，未见新根因。R3 Windows 两个相对打开/文件读取 job 均通过，官网 [#241](https://github.com/ayukyo/icode/actions/runs/36556408477) 成功；CI [#346](https://github.com/ayukyo/icode/actions/runs/36556408411) 仍因上述 R2 门失败。R2/R3 readiness 不变，自动模式继续关闭。详见[持续竞品对照](./agent-landscape-live.md)。
- R2 macOS UDS → lease CONNECT 测试桥候选（2026-09-29，本地）：仅 `tests/` 增加 test-only SOCKS5/UDS adapter，严格限制 no-auth/domain CONNECT/443，转发到既有 loopback lease CONNECT scope；SOCKS 请求及内部 CONNECT 响应均有绝对 deadline 与期间租约轮询，EOF 时复核租约，覆盖 active revoke 关闭和代理失败 general-failure 回执。相关本机模块运行 50 项，47 pass、3 个 native macOS 测试 skip；CONNECT 响应撤销/慢滴两个回归各重复 20 轮均无失败，EOF 撤销映射另有回归覆盖。CI #348 两种 macOS 架构在新 canary 构造 `HostConnectProxyServer` 时抛出统一构造错误，尚未进入 SOCKS/lease 转发；当前诊断补丁仅输出不含地址/端口/FD 的 listener 合同布尔事实，等待下一轮原生 CI。该诊断不改生产验证器；测试 resolver 将 `packages.example` 固定映射到受控 loopback，既不是 TLS/公网 DNS验收，也不能计网络 allowlist conformance。现有 CONNECT listener 无客户端认证，桥接明确不可产品化；网络 DENY、自动模式关闭、R2/R3 ready=false。Anthropic sandbox-runtime 当前 main 于 2026-09-29 核对仍为固定 SHA `3ed97390547bdd3d5cec5097d123f3a5fb741c6b`、0.0.77、Apache-2.0；详见[网络门禁计划](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)与[持续竞品对照](./agent-landscape-live.md)。
- CI [#347](https://github.com/ayukyo/icode/actions/runs/36559479174)（提交 `0bbda8f`）验证 R3 Windows bounded-reader x64/ARM64 job 成功，但整轮仍由 R2 Windows AppContainer 双架构失败；两边 native helper 均成功构建并运行到 stage 5，`18/20`，仅 `process_exit_zero` / `network_isolation_denied` 失败，网络回执与 #346 同为 Winsock `10060`、NetIso `INTERNET_CLIENT=2`、WFP `evidence_unavailable`。没有新因果证据；Windows AppContainer 门与自动模式保持关闭。
- CI [#348](https://github.com/ayukyo/icode/actions/runs/36567080695)（`61e4d62`）验证 Python 3.11/3.12、R2.1 workspace、R2.2 Linux、R2.3 Windows Job cleanup、R3 Windows x64/ARM64 jobs 通过；Windows AppContainer x64/ARM64 仍各 `18/20`，只有进程聚合退出与网络隔离硬门失败（Winsock `10060`、NetIso `INTERNET_CLIENT=2`、WFP 无匹配回执）。macOS Intel [job](https://github.com/ayukyo/icode/actions/runs/36567080695/job/109401550054) 与 Apple Silicon [job](https://github.com/ayukyo/icode/actions/runs/36567080695/job/109401550127) 的 UDS canary 均在 `HostConnectProxyServer` listener 构造处失败，未进入 SOCKS bridge；此前 Seatbelt/UDS canary 仍通过。官网 [#243](https://github.com/ayukyo/icode/actions/runs/36567080728) 成功。下一提交添加只用于定位的 listener 合同 facts，不改验证器。故 R2/R3 readiness 未完成、macOS/Windows 自动模式与 worker 网络继续关闭。
- Windows AppContainer 端口对照诊断候选（2026-09-29，本地待原生 CI）：test-only helper 在同一 AppContainer 子进程内依次尝试活跃 RFC1918 listener 和宿主保留的同地址 bound-but-not-listening 控制端口；两条 TCP connect 都有 1 秒上限，控制路径不发送 payload。只在 listener `10060` timeout、控制端口 `10061` refused 且宿主两控制均有效时输出 `listener_path_narrowed`，不进入 hard-gate score；NetIso `PRIVATE_NETWORK=1` 门、AppContainer 权限和生产执行器均不变。新增分类反例通过、相关本机套件 74/74（3 macOS 原生 skip）；C/MSVC 构建和 Windows 双架构行为仍待新 CI。设计/上游依据见[Windows计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)及[持续竞品对照](./agent-landscape-live.md)。
- R3 Windows 128-bit FileId 枚举/句柄绑定诊断（2026-09-29，CI #342 双架构通过）：test-only Windows 探针加入 `FILE_ID_EXTD_DIR_INFO` 解析（0x14）与相对打开后 `FILE_ID_INFO` 身份查询（0x12），比较卷序列号和完整 128-bit ID；全零/全 `0xFF` 无效哨兵 fail-closed，并覆盖空目录缓冲、junction 既有负例及“旧名被另一预枚举普通文件替换”的身份正反对照。本机目标模块 18 项中 15 pass、3 native skip；Windows x64 [job](https://github.com/ayukyo/icode/actions/runs/36545492409/job/109330767269) 与 ARM64 [job](https://github.com/ayukyo/icode/actions/runs/36545492409/job/109330767667) 均原生通过完整 18 项，完整 preflight、独立审查与官网 workflow [#238](https://github.com/ayukyo/icode/actions/runs/36545492411) 成功。CI [#342](https://github.com/ayukyo/icode/actions/runs/36545492409) 总体失败仅因两个 R2 AppContainer 网络门仍失败（双架构 `18/20`、Winsock `10060`、NetIso `INTERNET_CLIENT=2`、WFP 精确匹配为 0）；其余 18 个必需 job 成功、2 个可选诊断 skip。此原语没有接入生产 `snapshot_workspace`、没有签发 Windows tree OID；双架构通过仅证明本次 runner/文件系统上的枚举与句柄 identity 语义，不证明原子目录树快照、ABA/并发稳定或 Windows R3 完成。Windows tree OID 保持 `unsupported_platform`，R2 网络门与总体 readiness 不变。取舍见[持续竞品对照](./agent-landscape-live.md)及[R3计划](./nbl/plans/2026-09-26-r3-self-verification.md)。
- R2 Windows WFP 精确目标 capability-drop 诊断（2026-09-29，CI #340 已结束）：x64/ARM64 原生构建与本地分类自检通过；两边 RFC1918 host listener 正向控制成功，AppContainer 连接超时 `10060`，NetIso 诊断为 `INTERNET_CLIENT=2`（严格私网门要求 `PRIVATE_NETWORK=1`），精确 endpoint WFP observer 均成功订阅/退订但 callback 为 0、无匹配 capability ID。两项必需 AppContainer job 因 `network_isolation_denied` / 依赖的 `process_exit_zero` 失败；Python 3.11/3.12 与其余 18 个必需 CI job 成功，2 个可选旧诊断 job skipped；官网 workflow [#236](https://github.com/ayukyo/icode/actions/runs/36539616851) 成功。该结果不证明 WFP 根因，停止扩大 observer 收集；不放宽网络门、不改系统策略。Windows 自动模式、R2.3 与整体 R2/R3 readiness 继续关闭。详见[Windows计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)、[CI #340](https://github.com/ayukyo/icode/actions/runs/36539616876)与[持续竞品对照](./agent-landscape-live.md)。
- R2 Windows RFC1918 AppContainer 目标分类复核（2026-09-29）：提交 [`a5cab30`](https://github.com/ayukyo/icode/commit/a5cab304c8b713e21d6efaaeaa7771a77998f949) 的 CI [#338 x64](https://github.com/ayukyo/icode/actions/runs/36530780207/job/109283765567)/[ARM64](https://github.com/ayukyo/icode/actions/runs/36530780207/job/109283765683) 均成功原生构建，选中 RFC1918 地址且宿主 listener 正向控制通过；AppContainer 未连接 (`10060`)，但 Microsoft capability 诊断给出 `INTERNET_CLIENT=2` 而非 `PRIVATE_NETWORK=1`，两腿 `18/20`。CI 总体 18 success、这 2 个必需 probe failure、2 skipped；官网 [#234](https://github.com/ayukyo/icode/actions/runs/36530780191) success。RFC1918 不足以证明 Windows home/work 私网分类；精确门不放宽。NLM adapter/category 只能作解释上下文，下一步优先只读精确 WFP capability-drop 关联；事件关闭、无权限或无匹配时不改系统状态并保持 gate 关闭。Windows 自动模式、R2.3 及整体 R2/R3 readiness 继续关闭；详见[Windows 实验计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)与[持续竞品对照](./agent-landscape-live.md)。
- R2 Linux deny-only `run_command` deadline/输出预算直连验收（2026-09-29，本机与 CI）：TDD 合同先 RED 后 GREEN；真实执行链验证 `output_limit_bytes=128` 时以 `output_limit` 终止、只返回 128 字节，验证 `wall_timeout_seconds=2` 会覆盖工具请求 8 秒并清理同组后代，延迟 marker 不落盘，二者均无 OS 拒绝回执。新增 Linux native runner 探针 PASS；runner/receipt 聚焦 32 项通过。提交 [`8eb9d2e`](https://github.com/ayukyo/icode/commit/8eb9d2e) 的 CI [#334](https://github.com/ayukyo/icode/actions/runs/36522598887) 六个平台 R2.2 native jobs、Python 3.11/3.12、Windows directory-handle probe 与 presentation 均通过；但两个 Windows AppContainer read-handle jobs 仍失败（双架构 `18/20`、Winsock `10060` timeout、WFP 精确匹配为 0，见[Windows计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)），故整体 CI 失败。该证据仅涵盖时间/输出限额切片，不证明 `process_limit`，因此 `resource_limits` 仍未验证，分数 `8/10`、`ready=false`，自动模式关闭。
- R2 Windows AppContainer 网络证据仍未闭合（2026-09-29）：提交 [`7741604`](https://github.com/ayukyo/icode/commit/7741604) 的 CI [#335 x64](https://github.com/ayukyo/icode/actions/runs/36525230211/job/109266689610)/[ARM64](https://github.com/ayukyo/icode/actions/runs/36525230211/job/109266689710) 均原生编译并运行，但仍 `18/20`；`127.0.0.1` 连接超时 `10060`，capability API 返回 success + `NETISO_ERROR_TYPE_NONE=0`，WFP 仅 1 个 callback 且无 drop 匹配。故 API 不支持把该 loopback 超时归因到缺失网络 capability，timeout 仍不算 OS 拒绝证据。网络 gate、R2.3、Windows 自动模式及整体 ready 继续关闭；详见[Windows 计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)。
- R3 Windows handle-relative no-reparse 诊断探针（2026-09-29）：提交 [`6cadedc`](https://github.com/ayukyo/icode/commit/6cadedc) 的 CI [#336 x64](https://github.com/ayukyo/icode/actions/runs/36527310079/job/109273079787) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36527310079/job/109273079792) 均原生通过 `tests.test_windows_tree_snapshot_probe` 9 项，含普通子项、终端/祖先 junction 与 stale 名称替换检查。只完成 test-only NT API 原语验证；尚未集成 `snapshot_workspace`、未做 enumerated/opened FileId 绑定或完整 ABA/并发失效关闭。Windows tree OID 仍 `unsupported_platform`，不计 R3 完成；R2 network gate 仍关闭。
- CI [#336](https://github.com/ayukyo/icode/actions/runs/36527310079) 总体 failure 的唯一必需失败类别仍是 Windows AppContainer x64/ARM64 两腿：两边 `18/20`、loopback `10060`、capability API `NONE=0`、WFP 无目标 drop；其余 18 个已完成作业成功、2 个可选诊断 skip。官网 [#230](https://github.com/ayukyo/icode/actions/runs/36527310141) success。Microsoft 官方资料说明 packaged-app loopback 默认阻断，但不构成本工程当前 WFP packet 的直接归因。下一次 Windows network candidate 改为安全受控的 runner-local RFC1918 listener；若无法稳定得到 capability-specific 拒绝证据，则不放宽门槛。
- R2 Linux seccomp 多类别拒绝回执诊断（2026-09-29）：原生 runner 执行真实双类别 `USER_NOTIF` 用例并校验 broker `EPERM` 回执；普通 `Permission denied` 输出/退出 13 和 Landlock 文件拒绝不会误报；测试类级资源由 `TestSuite` 正确 setup/teardown。聚焦 28 项通过。提交 [`d721d83`](https://github.com/ayukyo/icode/commit/d721d83) 的 CI [#333](https://github.com/ayukyo/icode/actions/runs/36520245581) 中 Ubuntu 22.04/24.04 x64/ARM64、macOS Intel/Apple Silicon native jobs 与 Python 3.11/3.12 success；Windows AppContainer read-handle x64/ARM64 jobs failure（只有通用 exit-code annotation，详见[Windows计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)），所以整体 CI #333 failure。官网 [#229](https://github.com/ayukyo/icode/actions/runs/36520245588) success。Linux评分仍为 `8/10`，`uniform_violation` 未验证（Landlock 文件拒绝与 macOS/Windows 来源尚未闭环），`ready=false`。不改变网络 DENY、R2/R3 或自动模式。
- R2 macOS 同组清理回执可见性（2026-09-29）：`_emit_conformance_score` notice 将既有 scorer 的 `platform_critical_passed` 和 `process_group_cleanup` 与严格 `critical_passed` 分开输出，`None` 明确为 `not_applicable`；分数、严格门槛及 `ready` 计算不变。新增回归先 RED 后 GREEN；Python 3.11 下原生探针 CI 模块 11 项通过，提交前完整 preflight 三门、Python 语法与 diff 检查通过。提交 [`00440f2`](https://github.com/ayukyo/icode/commit/00440f2) 的 [CI #315](https://github.com/ayukyo/icode/actions/runs/36486236204) 有 18 个必需 jobs 全部成功，Python 3.11/3.12、Ubuntu x64/ARM64、macOS `macos-latest`/`macos-15-intel`、Windows x64/ARM64 wheel/Job/Reviewer 探针和 presentation 均完成；两个可选 Restricted Token/AppContainer 诊断 jobs 跳过、不计证据。官网 [#219](https://github.com/ayukyo/icode/actions/runs/36486236336) 成功。CI #313 的两个 macOS 架构同组正常退出/超时探针成功，评分仍 `6/10`、`ready=false`；本次只新增结果字段，没有提高分数。Codex 对照确认本门只覆盖同 PGID，不承诺主动脱组后代。R2/R3 readiness 不变，自动模式关闭。上游边界见[持续竞品对照](./agent-landscape-live.md)。
- R3 Reviewer 精确文件读取与硬链接隔离（2026-09-29）：对实际打开句柄校验普通文件及 `st_nlink == 1`，并在 builtin `read_file`/`grep` 入口校验精确 `allowed_read_files`；只作用于只读 Reviewer，普通会话语义保持兼容。提交 `1468dd1` 的 GitHub [CI #312](https://github.com/ayukyo/icode/actions/runs/36479949142) 在 Windows x64/ARM64 通过三项精确白名单与真实硬链接测试；后续 workflow [CI #313](https://github.com/ayukyo/icode/actions/runs/36481777383) 在 macOS Intel/Apple Silicon 通过同组测试，Python 3.11/3.12 全量测试及守卫也通过。两个 run 的必需 jobs 均成功，可选诊断 jobs 跳过；官网 [#217](https://github.com/ayukyo/icode/actions/runs/36481777807) 成功。此应用层限制不证明文件来源或消除路径竞态，不改变 Windows Reviewer OS 沙箱、Windows tree OID 或 R2/R3 ready 状态。上游取舍见[持续竞品对照](./agent-landscape-live.md)和[R3计划](./nbl/plans/2026-09-26-r3-self-verification.md)。
- R3 Linux Reviewer OS 边界专项 CI（2026-09-29）：Bubblewrap Reviewer 负例覆盖源码可读、工单账本与工作区外 sentinel 不可读、源码/输出不可写及宿主数据不变，另覆盖 `ToolContext` 调用链。commit `0ef2fed` 的 [CI #306](https://github.com/ayukyo/icode/actions/runs/36460339767) 中 Ubuntu 22.04 x64/ARM64 新步骤通过，Ubuntu 24.04 x64/ARM64 在合并步骤失败，公开 annotation 只显示通用退出码；诊断值为 Ubuntu 22.04 `apparmor_restrict_unprivileged_userns=0`、24.04 `=1`。commit `63c0f49` 的 [CI #307](https://github.com/ayukyo/icode/actions/runs/36462913484) 四个 Ubuntu runner 虽通过，但当时加载的 `flags=(unconfined)` + `userns` profile 被 Canonical 明确警告可绕过 userns 限制，故该绿灯不作为安全边界验收。当前改为运行时获取 AppArmor 固定提交 [`b0eb95457bc2de401920308869d016e696c73664`](https://gitlab.com/apparmor/apparmor/-/blob/b0eb95457bc2de401920308869d016e696c73664/profiles/apparmor/profiles/extras/bwrap-userns-restrict) 的专用 profile，校验 SHA-256 后仅在限制开启的 runner 加载，并验证 bwrap 子进程进入 `unpriv_bwrap`；上游 profile 的 bwrap 初始化权限较宽、子进程拒绝 capabilities，profile 依上游根 LICENSE 为 GPLv2，本仓不 vendoring。commit `018ed54` 的 [CI #308](https://github.com/ayukyo/icode/actions/runs/36469108401) 中 Ubuntu 22.04 x64/ARM64 及其余必要 jobs 成功；Ubuntu 24.04 x64/ARM64 均在读取 `/sys/kernel/security/apparmor/profiles` 时因普通 runner 用户权限不足失败，日志显示 profile 下载、SHA-256 校验及 `apparmor_parser` 已通过。修复 commit `2750a1e` 的 [CI #309](https://github.com/ayukyo/icode/actions/runs/36471224474) 总体成功：18 个必需 job 全绿，Ubuntu 22.04/24.04 x64/ARM64 四个原生探针（含 enforce profile 与 child-label 检查）通过，Python 3.11/3.12 全量测试、Windows/macOS 与 presentation jobs 通过；两个可选诊断 job 按默认配置跳过，不计功能证据。官网 workflow [#213](https://github.com/ayukyo/icode/actions/runs/36471224530) 也成功。该结果只关闭本轮 Linux Reviewer CI profile 门，不改变 macOS/Windows Reviewer 产品边界、R2/R3 readiness 或自动模式。本机工作流合同测试针对该权限缺陷先 RED 后 GREEN；本机 Reviewer 探针 20/20 次通过、隔离模块 84 项通过/9 项平台跳过。
- R2 不支持平台的安全命令提示（2026-09-29，本机切片）：当策略执行 broker 在创建子进程前明确返回 `unsupported_platform`，工具结果带稳定 `error_code=unsupported_platform`、`payload_started=false`、`cleanup_scope=not_started`；CLI 仅在代码与状态严格匹配时显示固定“命令未启动”提示，不再只显示“失败”。两组旧行为回归先失败后通过，工具/CLI 定向 51 项通过，新路径 20/20 轮通过；`preflight.py --only tests`、compileall、diff check、治理/官网/竞品门禁通过，独立复审 APPROVE（无 Critical/Important/Minor）。提交 [`1f43463`](https://github.com/ayukyo/icode/commit/1f43463149e87fa24b64863f6e81f1b7df6477cb) 的 GitHub [CI #302](https://github.com/ayukyo/icode/actions/runs/36452558796) 及官网 [#206](https://github.com/ayukyo/icode/actions/runs/36452558685) 均 success；CI 中 Windows x64/ARM64、macOS Intel/Apple Silicon、Linux native-probe 与 Python 3.11/3.12 关键 jobs 通过，两个可选诊断 job skipped、不计作验证。同步该结果的文档提交 [`092786e`](https://github.com/ayukyo/icode/commit/092786e7bab77fc746aa312e004dcd7c9cc21c82) 的 [CI #303](https://github.com/ayukyo/icode/actions/runs/36454220001) 与官网 [#207](https://github.com/ayukyo/icode/actions/runs/36454219942) 也 success。未改变平台支持、隔离评分或自动模式。
- R2 原生观察不完整的 CLI 安全提示（2026-09-28，本机切片）：仅当失败的 `tool_result` 明确带 `violation_observer_status=incomplete` 时，CLI 显示固定“隔离结果未确认”提示；不回显动态消息、不称为 OS 拒绝，也不暗示命令必然未启动。新增回归在旧实现先失败，修正后 CLI+Linux receipt 14 项通过，新用例连续 100/100；`preflight.py --only tests`、compileall/diff check 通过，独立复审 APPROVE（无 Critical/Important/Minor）。提交 [`6b9eaa5`](https://github.com/ayukyo/icode/commit/6b9eaa5742f0c357befc142e6b3360593fcbdb36) 的 GitHub [CI #301](https://github.com/ayukyo/icode/actions/runs/36446951546) 与官网 [#205](https://github.com/ayukyo/icode/actions/runs/36446950906) 均 success；不改变 Linux 来源、能力评分、`uniform_violation`、网络 DENY 或自动模式。
- R2 Linux USER_NOTIF 提交远端验收（commit [`2cecb6c`](https://github.com/ayukyo/icode/commit/2cecb6ce5e0734e435aef5da870426b8e75c6f7b)，CI [#298](https://github.com/ayukyo/icode/actions/runs/36435491001)、官网 [#298](https://github.com/ayukyo/icode/actions/runs/36435490339) 均 success）：此前 Linux `run_command` 原生回执切片的 secrets、submodule、全量 unittest 本机 preflight 及 Linux x86_64/ARM64 native-probe 矩阵通过；此结果不扩展到 macOS/Windows、不提高 `uniform_violation` 分数。
- R2 原生回执到 CLI 的安全展示（2026-09-28，本机阶段）：AgentLoop 真实 `run_command` AF_INET DENY 事件保留 `policy_denied`、脱敏用户提示和 seccomp 回执；CLI 对符合固定 schema 的回执显示 `network_socket × count`，不回显 argv 或额外字段；普通 exit 13 仍显示普通失败。Linux 原生集成 10 项连续 20 轮通过，CLI/Loop/Linux receipt 定向 40 项通过；全量 preflight 的 secrets、submodule 与 1,156 项 unittest（30 项 skip）均通过；复审要求的关闭交错测试加强后又连续 100/100 通过，最终 `preflight.py --only tests` 再次通过。Python 编译、diff whitespace、竞品/治理/官网门禁通过，文档契约检查连续两次均为 0 项；提交 [`99a4849`](https://github.com/ayukyo/icode/commit/99a4849fbb16ce4b9e47c67a7fc4870b84868b79) 的 GitHub [CI #299](https://github.com/ayukyo/icode/actions/runs/36443592405) 和[官网 #203](https://github.com/ayukyo/icode/actions/runs/36443592413) 均 success。仅完成 Linux→AgentLoop→CLI 路径；本 Python runtime 尚无 MCP server/result adapter，ICODE-SKILL 子仓库中的 MCP 工具不承载这条 `ToolResult`，故 MCP parity 和 VR-1 仍未闭合，不计 `uniform_violation`，R2/R3 状态、网络 DENY 与自动模式不变。
- R2 Linux USER_NOTIF 真实命令回执本机切片（2026-09-28）：仅在实际 Linux `LandlockSandbox`、deny-only policy 的 `run_command` 路径启用 seccomp USER_NOTIF observer；通知通过 SCM_RIGHTS 在 payload 启动前交给 broker，broker 明确回复 `EPERM`。真实 AF_INET DENY 得到脱敏原生回执，AF_UNIX `socketpair()` 允许正例、普通 exit 13 无误报；observer 握手/初始化/线程启动失败、策略工作区根不匹配、只读上下文及 observer deadline 过期时 payload marker 均不产生，线程创建失败也验证 listener FD 已关闭。新增 9 项集成用例连续 20 轮共 180/180；broker/tools/CLI/loop 73 项、isolation 74 项通过。完整 `preflight.py` 首轮曾发现核心离线模块意外导入 socket，已移除并定向复测通过，最终全仓 preflight 待重跑。GitHub Linux native-probe 矩阵已增加该集成测试，远端结果待本阶段推送后复核。仅覆盖 Linux socket 类通知，不观测 Landlock 文件拒绝，不改变 `uniform_violation`/能力评分、`policy_contract_ready`、R2/R3 完成状态或自动模式；macOS/Windows parity 与 `process_limit` 口径仍未闭合。
- R2 macOS AF_UNIX 代理通道候选（[CI #294](https://github.com/ayukyo/icode/actions/runs/36414729151)，2026-09-28）：macOS Intel 与 Apple Silicon 原生 job 均验证宿主预监听的获准 UDS 可双向传递固定 canary、不能 unlink listener，workspace sibling UDS 与 loopback TCP 被拒；notice 明确 `conformance_credit=none`。只证明 test-only Seatbelt 路径原语在本轮 runner 生效。只读客户端兼容研究发现，Python `urllib`、HTTPX 与 Node 内置 proxy 均没有通用 UDS proxy 环境值；curl/libcurl 的 UDS proxy 支持仅为 SOCKS，不能直接连接 ICODE 当前 HTTP CONNECT proxy。该候选暂缓生产接入；macOS `6/10`、critical 未通过、`ready=false`，worker 网络仍 DENY、自动模式关闭。
- R2 curl SOCKS5-over-UDS 客户端复核（commit [`a69dc50`](https://github.com/ayukyo/icode/commit/a69dc50be6b5c1c4b5d239dec37ebd402be64c87)，[CI #296](https://github.com/ayukyo/icode/actions/runs/36419842949)，全矩阵成功）：macOS Intel 与 Apple Silicon 上的 curl 均满足版本/UnixSockets feature 门槛，并在 test-only Seatbelt profile 中经 `ALL_PROXY` 到达受控 SOCKS5 UDS canary；域名保留、允许样例返回固定内容、阻断样例被拒。Canary 不发起 TCP 或真实网络，notice 为 `conformance_credit=none`，不证明 ICODE 代理或产品兼容性。R2 macOS 仍 `6/10`、`ready=false`，生产网络 DENY 与自动模式关闭不变。
- R3 Windows 目录句柄 / FileId 原语研究（commits [`37e034b`](https://github.com/ayukyo/icode/commit/37e034bab61a7269ded90f386bde53db71830314)、[`ff4f2b2`](https://github.com/ayukyo/icode/commit/ff4f2b24034f4cb4eb8d5bb193e3a60f13fb173c)，[CI #291](https://github.com/ayukyo/icode/actions/runs/36408530343)、[#292](https://github.com/ayukyo/icode/actions/runs/36409357853) 与 [#294](https://github.com/ayukyo/icode/actions/runs/36414729151) 均成功）：Windows x64 与 ARM64 NTFS runner 上，目录只读句柄仍允许新建和删除子项，改名观测为 sharing violation；单文件只读句柄的新写/DELETE 打开得到 `ERROR_SHARING_VIOLATION`，目录与文件 ID 一致。#294 重复观察到同一结果。原生代码仅为 test-only 探针，不接入产品；该结果否定“目录 handle 冻结整层命名空间”的假设，不能证明原子快照。`worktree_git_tree_oid()` 继续为 `unsupported_platform`；Windows 竞态/路径威胁和自动模式边界不变。
- R2/R3 组合回归 [CI #294](https://github.com/ayukyo/icode/actions/runs/36414729151) 已全绿：Python 3.11/3.12、Linux/macOS workspace、Windows workspace/Job/wheel 与本轮原生探针 job 成功；可选 Windows restricted-token/AppContainer diagnostics 按默认配置跳过，不计验证。Linux conformance 在 Ubuntu 22.04 x64/ARM64 为 `8/10`、`critical_passed=true`，在 ubuntu-latest 与 Ubuntu 24.04 ARM 为 `7/10`、`critical_passed=false`；macOS 双架构均为 `6/10`、`critical_passed=false`；全部 `ready=false`。CI 通过不等于 R2/R3 完成，自动模式保持关闭。
- R2 macOS 原生拒绝日志探针（commit [`a2b54ee`](https://github.com/ayukyo/icode/commit/a2b54ee8c8ac51d9bfc3cfbbd32dd348b4533074)，CI [#289](https://github.com/ayukyo/icode/actions/runs/36402344430)，全量 workflow 最终 success）：Intel 与 Apple Silicon 原生 job 均观测到受控 Seatbelt 文件读取拒绝及精确 `file-read-data` 事件；事件仅由 test-only 探针匹配，`conformance_credit=none`，不计 `uniform_violation`。同轮两架构也均能连接宿主非 loopback 活跃同端口 listener 并送达 canary，故 `localhost:<port>` 不是严格 loopback 边界。macOS 仍 `6/10`、critical 未通过、`ready=false`；产品网络 DENY、自动模式关闭。
- R2/R3 handoff 修复远端验收（commit [`f22f6a4`](https://github.com/ayukyo/icode/commit/f22f6a4ed733d8f1844a921aa2d9ac0a5de4b301)，GitHub Actions workflow run [#279](https://github.com/ayukyo/icode/actions/runs/36381227465)）：Python 3.11/3.12、Windows workspace/Job/wheel、Linux/macOS workspace 与六个原生探针 job 全部成功；可选 Windows 诊断 jobs 按默认配置跳过。Linux Ubuntu 22.04 x64/ARM64 为 `8/10`（critical 通过、`ready=false`），ubuntu-latest 与 Ubuntu 24.04 ARM 为 `7/10`（critical 未通过、`ready=false`）；macOS Intel/Apple Silicon 为 `6/10`（critical 未通过、`ready=false`）。Linux allowlist expiry 在 22.04 x64/ARM64 通过，在另外两种 Linux runner 跳过。macOS 双架构再次观测到获准 loopback connect/send 成功、其它 loopback 端口 `EPERM`、宿主非 loopback 同端口无 listener 时 `ECONNREFUSED`；仍未证明活跃 LAN listener 的允许或拒绝。Public website workflow [run 36381227448](https://github.com/ayukyo/icode/actions/runs/36381227448) 成功。CI 全绿只验证本提交矩阵，不代表 R2/R3 ready；网络仍 DENY，自动模式关闭。
- R2 Linux SCM_RIGHTS 接收器 SIGINT/FD 收尾竞态（已推送，GitHub Actions workflow run #279 通过）：旧 CI [run 36376611960](https://github.com/ayukyo/icode/actions/runs/36376611960) 的 Python 3.12 全量套件出现 1 项失败：SIGINT 期间 dup listener 的 FD alias 暂时多出 2 个。根因定位到 `Thread.is_alive()/join()` 等待被信号打断时不能作为接收线程已完成 FD-finally 清理的屏障。现在以接收线程只在清理后追加的 `outcome` 作为完成标记，主线程在信号/取消路径等待该标记后再 join；回归同时断言接收线程已退出及 FD alias 恢复。回归先红后绿；该 SIGINT 用例最终实现连续 3,000 轮通过，handoff 模块 24/24、Python 3.12 全仓 1,109 项通过/26 项条件跳过，Python 3.11 `preflight.py --only tests` 通过。该修复关闭已复现的线程完成判定竞态，不声称证明所有调度时序无竞态；远端跨平台与原生探针结果见上方 workflow run #279 验收条目。
- R2 macOS localhost 原生诊断刷新（旧 CI [run 36376611960](https://github.com/ayukyo/icode/actions/runs/36376611960)）：Intel 与 Apple Silicon 的 Seatbelt 子进程均实测 loopback 同端口连接及发送成功、另一 loopback 端口在 connect 阶段以 `EPERM` 拒绝；宿主非 loopback 地址的同端口探测返回 `ECONNREFUSED`，因为当时没有 listener，且未发送数据。因此此向量既不是活跃 LAN 服务可达的证明，也不是其被拒绝的证明。macOS native conformance 仍 `6/10`、critical 未通过、`ready=false`；网络保持 DENY，自动模式关闭。
- R3 跨平台 Git 对象矩阵复验：commit [`197a846`](https://github.com/ayukyo/icode/commit/197a846cfb9e9366fd6dac706f4fc98aaad723f4) 的 [CI #266](https://github.com/ayukyo/icode/actions/runs/36364499440) 暴露矩阵过宽：Windows 执行了依赖“受测 worktree tree OID 已支持”的 `run_task` 集成用例；当前 Windows 明确 `unsupported_platform`，因此该用例必须排除，不能靠放宽 fail-closed 让它通过。`bdcf906` 将跨平台覆盖收窄为 17 个对象读取/绑定单测，保留原有 workspace 模块，并修正失败注解标题。项目 `.venv` Python 3.11 全仓 unittest 1,106 项通过、25 项条件跳过；`preflight.py --only tests`、compileall、diff check 与 workspace runner 163 项均通过。push CI [#267](https://github.com/ayukyo/icode/actions/runs/36365615681) 全部 workflow 成功，Windows/macOS/Linux workspace 与 Python 3.11/3.12 全量套件通过。另有可选 Windows 诊断 jobs 按默认配置跳过，未计作验证。native conformance 仍为 Ubuntu 22.04 x64/ARM64 `8/10` (`critical_passed=true`)、ubuntu-latest/24.04 ARM `7/10` (`critical_passed=false`)、macOS x64/ARM64 `6/10`，均 `ready=false`；R2/R3 未完成，自动模式关闭。
- R3 Windows tree OID 可行性再研究（2026-09-28，只读）：标准库无 Windows `dir_fd`/句柄相对目录遍历合同；Win32 `FileIdExtdDirectoryInfo` + `OpenFileById` 可按文件 ID 打开条目，但不是 parent-relative 原子树快照，无法单独抵御同用户并发改写、删除/复用与目录命名空间竞态。Git 私有 index/ODB 可避免写用户 index/对象库，但 `git add` 会触发 attributes/filter，且仍是路径读取；stdin hash + 私有 `update-index`/`write-tree` 只解决 Git 编码，不解决快照 TOCTOU。继续让 `worktree_git_tree_oid()` 在 Windows 返回 `unsupported_platform`；仅作为未接 runner 的实验原型候选。原生验收/威胁语义见[持续竞品对照](./agent-landscape-live.md) Windows R3 后续研究。
- R3 result commit/tree 对象完整性（CI #263 已成功）：临时 Git 仓库实证旧读取会接受保留旧 OID 路径但正文已变的 commit/tree；现重算 Git 规范 SHA-1/SHA-256，并让流式 `cat-file` 正文读取严格受独立 size 预查结果约束（commit 1 MiB、tree 128 MiB，超限终止子进程）。缺失 promisor tree 的本机 Ubuntu Git 1ubuntu1.17 正/反对照证明 `GIT_NO_LAZY_FETCH=1` 时不取回、无此变量时可取回；此为该发行版回补证据，不外推到 vanilla 同版本。新增入口预算测试先红后绿；关键 7 项回归 20 轮共 140 次、全仓 1,105 项通过/25 项条件跳过。独立复审确认接线修复关闭；preflight 测试/子模块门、限定本次修改文件的密钥形态扫描、站点/治理/竞品排期检查、compileall 与 diff check 均通过。push CI [#263](https://github.com/ayukyo/icode/actions/runs/36361956421) 总体成功，但 Linux 原生探针分别为 8/10（Ubuntu 22.04 x64/ARM64，critical 通过）、7/10（ubuntu-latest 与 24.04 ARM，critical 未通过），macOS x64/ARM64 为 6/10；均 `ready=false`。Windows Git tree OID、路径 TOCTOU 等未闭合，R2/R3 不视为完成。
- R3 工作区快照特殊文件失败关闭（本机切片）：审计发现 POSIX fd 与 Windows `scandir` 分支都会静默遗漏 FIFO 等未知特殊类型，可能令改动列表把真实条目漏作“无变化”。现在两平台快照均遇此类型抛 `OSError`，包括 `.icode_output` / `__pycache__` 名称本身；`workspace_changes` 返回 `snapshot_unavailable`，任务/Reviewer 快照路径不能据不完整快照通过。普通路径与保留名用例先在旧实现上失败，复审发现并修复保留名跳过顺序；R3/workspace 定向套件 126 项通过、1 项平台跳过，全仓 1,098 项通过、25 项条件跳过。Windows 为分支模拟，原生 CI 待推送后验证。未解决 Windows 路径快照 TOCTOU、Windows tree OID、策略化 Reviewer 边界；R2/R3 尚未完成。
- R2 拒绝回执上游复核（2026-09-28）：Codex `rust-v0.157.1` 有 Linux seccomp `EPERM` 强制，但其公开拒绝归类从输出/退出推断，未找到 syscall 级工具回执；OpenHands SDK 通用命令结果也未提供 OS-deny 机器码。Landlock 系统审计需特权，不符合默认无特权 pip-only 入口。详情与固定源码链接见[持续竞品对照](./agent-landscape-live.md)及[R2 阶段门](./nbl/plans/2026-09-28-r2-resource-limit-and-violation-receipt.md)；不降低原生回执标准、不改分，自动模式继续关闭。
- R2 macOS 网络授权边界（CI #281 与后续只读调研，2026-09-28）：双架构原生诊断证实 `localhost:<随机端口>` 在 loopback 正例成功、其它 loopback 端口 `EPERM` 的同时，也可连接到宿主非 loopback 地址上的同端口活跃 listener，并实际送达 canary（[Apple Silicon](https://github.com/ayukyo/icode/actions/runs/36384721402/job/108807601206) · [Intel](https://github.com/ayukyo/icode/actions/runs/36384721402/job/108807601437)）。独立上游记录显示 `remote ip` 的字面 host 值 `127.0.0.1` 会触发 `host must be * or localhost in network address`：cplt 固定版本记录了 loopback literal，MCP Discussion 的 macOS 26.5.2 实测记录了公网 literal；后者不是 loopback 的直接实测。ICODE 已加入双架构原生具体端口复核：匹配到固定 parser tag 时报告 `unsupported_host_predicate`、不给能力分；其它启动错误作为不确定结果失败，不会被记为隔离通过。真实 macOS CI 结果待验。当前不采纳数值谓词或 `localhost:<port>` 作为严格 loopback 地址边界，worker 网络继续 DENY，不改变 conformance 评分或自动模式；详情见[持续竞品对照](./agent-landscape-live.md)。
- R2 macOS 网络边界后续验收（CI #283，2026-09-28）：具体 `127.0.0.1:<port>` 规则在 macOS Intel 与 Apple Silicon runner 均命中 `unsupported_host_predicate`，并记录 `conformance_credit=none`（[Intel](https://github.com/ayukyo/icode/actions/runs/36387612812/job/108816238112) · [Apple Silicon](https://github.com/ayukyo/icode/actions/runs/36387612812/job/108816238121)）。同一轮再次确认 `localhost:<port>` 可连接宿主非 loopback 同端口活跃 listener 并送达 canary。故这两种 Seatbelt 主机表达都不满足当前严格 loopback 地址边界；生产 worker 网络保持 DENY，macOS 仍 `6/10`、critical 未通过、`ready=false`，自动模式不开放。详见[持续竞品对照](./agent-landscape-live.md)。
- R2 macOS localhost 诊断 CI follow-up（2026-09-28）：`a57a93e` 的 CI [run 36375272942](https://github.com/ayukyo/icode/actions/runs/36375272942) 中 Intel/Apple Silicon 均通过基础 `/usr/bin/true`、Python `-S`、普通 Python 与附加随机端口规则后的 Python 启动，随后 socket 探针仍 exit 1、stderr 为 `python_runtime`；`4359b64` 的 CI [run 36376053831](https://github.com/ayukyo/icode/actions/runs/36376053831) 进一步显示 `child_stages=none`、`python_runtime+python_os_error`，失败在首个 socket 阶段标记前。源码比对发现 startup control 使用授权的临时 workspace cwd，而 socket probe 继承 checkout cwd；这是待验证的测试上下文差异，不是已确认根因。现统一 probe cwd 并捕获 socket import 阶段错误，提交后等待双架构验证；不把结果归因为 Seatbelt DENY/ALLOW。macOS 仍 `6/10, critical_passed=false, ready=false`，产品网络 DENY 不变。
- R2 macOS localhost probe harness follow-up（2026-09-28，commit `fbf2960`）：双架构新 CI [run 36372163484](https://github.com/ayukyo/icode/actions/runs/36372163484) 将失败定位为 `loopback-allowed` 子进程退出 1、无结果标记；探针源码显示 socket 创建/超时设置在其 errno 捕获区外，但具体底层异常尚未被观察到，因此不把它归因为 Seatbelt 拒绝。现将这两个操作纳入受控 OSError 分类，下一轮原生执行是必要证据；不改变任何策略、评分或产品网络开关。
- R2 macOS localhost probe staged startup check（2026-09-28，commit `38c241a`）：把 `socket()`/`settimeout()` 移入 errno 捕获后，双架构 CI [run 36372816346](https://github.com/ayukyo/icode/actions/runs/36372816346) 仍在 loopback 子进程返回 1 且无标记；因此根因并未确认。现添加同 profile 的纯 Python 启动对照，再分别判断 Seatbelt profile/解释器能否运行与后续 socket 行为；不输出 stderr 正文或网络标识、不改变产品策略。当前不能把该探针计为 macOS 网络允许或拒绝证据。
- R2 macOS profile-startup follow-up（2026-09-28，commit `abe6ef5`）：双架构 CI [run 36373392322](https://github.com/ayukyo/icode/actions/runs/36373392322) 显示同一 Seatbelt profile 下纯 Python 标记也未出现（exit 1，stderr 非空）；问题早于 socket 创建，但具体 SBPL/执行错误仍不可见。现仅输出固定词表映射的 stderr 类别，不输出原文或路径，再复跑以区分 profile 解析、执行器启动与平台限制；不改变生产网络策略或评分。
- R2 `process_limit` 平台语义复核（2026-09-28，只读）：Linux cgroup `pids.max` 是按 TID/task 的硬限制；Windows Job 限制 active processes，现有组件尚未接入 Workbench spawn 链；macOS `RLIMIT_NPROC`/launchd 是 UID 级、不是单工单配额。Codex 的 64 项 tracked-session LRU 也不是 OS 硬限额。保留 RL-0，先确认计数口径及平台差异；macOS 无 per-task 硬限额时不得计分。详情见[资源限制实施门](./nbl/plans/2026-09-28-r2-resource-limit-and-violation-receipt.md)与[持续竞品对照](./agent-landscape-live.md)。
- R2.4 Linux 候选代理租约到期端到端回归与评分接线（2026-09-28，本机验证、远端 CI 待验）：真实 helper/SCM_RIGHTS/lease CONNECT 用例保持双向隧道直到短租约到期，验证 worker 与上游 peer 都收到 EOF；过期 scope 再启动命令时 marker 不产生。native runner 复用同一单项并区分 PASS/SKIP/FAIL；本机实际 PASS 后 Linux conformance 为 `8/10`、`critical_passed=true`、`ready=false`，尚缺资源限制和统一违规回执两项。测试只把测试域名解析到本机 loopback fixture，不访问公网；SKIP 不计分，失败使 native job 失败。该候选仍未接入 ToolContext/Agent，也未证明 OS 层 worker 只能访问代理或三平台一致；不改变 `policy_contract_ready`，R2/R3 继续未完成。
- R2.4 资源限制与违规回执缺口审计（2026-09-28，只读研究/本机机制实验）：`process_limit` 尚未进入真实 `run_command` 执行链；Windows Job 限额目前只有诊断组件路径。user-systemd 临时 scope 的 `TasksMax=1/2` 本机正反实验分别拒绝/允许子进程，且证实脱组后代需要显式 stop unit；这不是 ICODE 接线、跨发行版、三平台或产品能力证据。cgroup 任务数包含线程，语义选择仍待用户确认。`uniform_violation` 需覆盖真实 OS DENY 经执行 broker 的回执，应用层 `ToolRegistry` 测试不足。详细阶段门见[R2 资源限制与统一违规回执计划](./nbl/plans/2026-09-28-r2-resource-limit-and-violation-receipt.md)与[持续竞品对照](./agent-landscape-live.md)；当前评分保持 `8/10`，自动模式关闭。
- R2 host proxy shutdown 返回值竞态（2026-09-28）：全仓守护在 `server.close()` 取消仍发送请求头的客户端用例中偶发失败。根因是 proxy 在授权前的 socket/lease 错误分支未再检查已线性化的 `_closed` 状态，导致 shutdown 路径偶尔回报 `True`。现在仅当尚无授权 tunnel 且 server 已关闭时返回 `False`；已建立 tunnel 后 relay 错误仍保持既有 `True` 语义。修复前新断言 20 轮失败 16 次；修复后 20/20 通过，proxy server 28 项回归连续 20 轮通过，提交前 preflight 全量测试门通过。固定 Codex 源码对照显示 `Ok(())` 仅表明取消的服务 future 结束，不作为 ICODE 成功回执；具体采纳/暂缓见[竞品对照](./agent-landscape-live.md)。未改变 lease 校验、连接授权或 R2 评分；R2/R3 仍未完成。
- R2.4 应用策略拒绝回执统一（2026-09-28，本机切片）：Guard 与 `ToolRegistry` 拒绝统一 `policy_denied`、用户提示及结构化回执，并明确标记 `application_policy` / `os_enforced=false`；CLI 对两类拒绝路径显示同一提示，最终报告也不回显动态 Guard 原因。4 项新增回归覆盖拒绝提示、拒绝报告脱敏及成功结果边界；全仓 1,094 项通过、25 项条件跳过。该片只补齐应用层回执，不计 `uniform_violation`，不提高 Linux `8/10` 评分；真实 OS DENY 到 broker 的跨平台证据仍缺，自动模式关闭。
- R2.4 lease/proxy CI follow-up（2026-09-28，已提交推送）：commit [`9d7d2a0`](https://github.com/ayukyo/icode/commit/9d7d2a09817b87669c454470cb6259ebee5a392c) 已进入 `main`；CI [#256](https://github.com/ayukyo/icode/actions/runs/36349914123) 全部 workflow 成功，Pages [#166](https://github.com/ayukyo/icode/actions/runs/36349914269) 成功。该轮确认 namespace/loopback 初始化失败只在明确权限错误且 payload 未启动时记为环境 skip，并修复 lease 撤销与 relay I/O 错误竞态导致的 listener 泄漏；Python 3.11/3.12、Windows、wheel 与 Linux/macOS native jobs 均通过。**绿色 workflow 不等于隔离 ready：**Linux native conformance `7/10`、macOS `6/10`，两者仍 `critical_passed=false`、`ready=false`；macOS 临时代理网络规则还受 `localhost` 地址范围限制，等待明确验收边界。worker 网络保持 `DENY`，自动模式关闭，`policy_contract_ready=false`，R2/R3 未完成。
- R2.4 Linux 单命令 launcher/session 接线（2026-09-28 本机切片，提交前门禁通过）：把原来只在测试中手工拼接的 helper Popen、SCM_RIGHTS handoff、lease CONNECT session 与 helper/FD/scope 清理收敛到受信候选执行器；候选强制原始 `DENY` policy 与同一 live scope 绑定，不接 `ToolContext`/Workbench/Agent。相关定向 80 项与全仓 `preflight.py --only tests` 通过；密钥、子模块三道 preflight、竞品/治理/站点检查、`git diff --check` 通过。密钥扫描在仅含 Git 跟踪文件和本次差异的临时快照运行，未触碰未跟踪用户数据。该记录仅代表本机提交前证据，不代表远端 CI 或跨平台验收。它没有证明 worker 只能访问指定代理端点或跨平台 OS 网络边界；`policy_contract_ready=false`、自动模式关闭、R2/R3 未完成。
- R2.4 Linux handoff→lease CONNECT session 阶段（本机门禁通过，push CI 待验）：`LinuxHostConnectProxySession` 将 credential/nonce-bound SCM_RIGHTS listener handoff、host CONNECT relay 与既有 lease scope 串起；native listener 在交付前设 `SOCK_NONBLOCK`。payload ACK 仅在 session ready 且 scope/runtime/expiry monitor/租约有效时发送；发布期间按 scope→runtime→monitor→authority 锁序保护，并在 authority 锁内重新采样单调时钟，覆盖撤销和等待锁跨 TTL 两个竞态。定向 proxy/scope/lease/handoff 101 项、Linux PID namespace/helper 18 项及全仓 unittest 门禁通过；完整源码独立复审未发现遗留问题。此 session 仍未接入产品 `execute_policy_command`/Agent/ToolContext，未证明 sandbox 只能访问代理；worker 网络仍 `DENY`、自动模式关闭，R2/R3 未完成。
- R2.4 host CONNECT listener/relay（本机切片，本机门禁通过，push CI 待验）：新增只供可信宿主持有的 `HostConnectProxyServer`，限定 IPv4 `127.0.0.1` listener/peer；listener 创建/共享前必须设置 `O_NONBLOCK`，POSIX wrapper timeout 仅允许 `None/0.0`，Windows 要求 `0.0`；构造时只读验证且拒绝阻塞/正 timeout 模式，避免 Linux select-ready 后因异步错误而让 accept 等待；接收端不修改共享 FD flags，handoff 默认 wrapper 经真实 dup-FD 测试覆盖。stale readiness 的 transient accept error 回到 poll，持续 accept 系统错误有 100 ms 退避且可被 close 唤醒。接受连接后立即登记到 scope，在 16 KiB/5 秒界限内读取 CONNECT head，并于等待期间复验租约；调用既有 CONNECT scope/数值地址 connector，只有拨号与 lease 复核成功后才回 `200`；双向转发缓冲每方向上限 256 KiB，支持 half-close。19 项真实 loopback 用例覆盖正常往返、半关闭、畸形/不完整/过大请求无拨号无 200、blocking/timeout-mode listener 拒绝且不改状态、stale readiness、EMFILE 退避、scope close、revoke/expiry、响应前撤销及 listener close；Windows 跳过 1 项 POSIX fd-wrapper 测试。最终树 `preflight.py --only tests`、69 项 lease/scope/server 套件、关键竞态 20 轮、子模块/文档检查/编译及独立复审通过。测试 resolver 仅在测试中映射到本机 upstream，没有放宽生产地址过滤。此片不接 FD handoff、Agent/ToolContext 或 OS 网络路由，worker 网络保持 `DENY`，R2 network conformance 未通过；GitHub 跨平台 CI 待推送后验证。
- R2.4 Linux native listener handoff 阶段（2026-09-27 UTC，本机 Linux x86_64）：helper 经 SCM_RIGHTS 交付 loopback listener 与 16-byte 随机 nonce；host ACK 必须回显 nonce、绑定原控制通道及已验证 listener，才启动 payload。旧实现的预排队 ACK 回归先红后绿；正确长度错误 nonce、错误通道、重复 ACK 与关闭通道均失败关闭。相关套件 48 项、关键 native 边界 20 轮/80 次、Linux 安装式 wheel probe 及独立复审通过。推送 [CI #250](https://github.com/ayukyo/icode/actions/runs/36332012958) 暴露测试 harness 在 peer 关闭且 `SCM_RIGHTS` 消息未读时裸 `recvmsg()` 收到 `ECONNRESET`；根因与本机修正验证见下条。本片不接生产 CONNECT/relay 或 Agent 网络，R2 网络 `DENY`、自动模式关闭，R2/R3 均未完成，详见[R2.4 网络门禁计划](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)。
- R2.4 listener handoff CI follow-up（2026-09-28 Asia/Shanghai）：回归测试固定 helper 先拒绝过期 ACK 并退出、再由 host 接收，改走生产 `receive_loopback_listener()`，将“收到 listener”或“peer reset 归一化”都限定为失败关闭，并要求 helper 非零退出且 payload marker 不存在；生产实现和安全门槛未改。stale-ACK 用例 Python 3.11/3.12 各 30 轮通过，Linux PID cleanup 模块两版本各 18/18；Python 3.11 `preflight.py --only tests` 通过，Python 3.12 全量 1050 项通过（25 skip）。准确错误分别见 CI [Python 3.11](https://github.com/ayukyo/icode/actions/runs/36332012958/job/108655634638)、[Python 3.12](https://github.com/ayukyo/icode/actions/runs/36332012958/job/108655634215)、[Linux x64](https://github.com/ayukyo/icode/actions/runs/36332012958/job/108655634538)、[Linux ARM64](https://github.com/ayukyo/icode/actions/runs/36332012958/job/108655634550)。修正提交后的远端复验仍待完成；完整 R2/R3 与自动模式继续关闭。
- R2.4 Linux listener FD receiver 验收刷新（2026-09-27 14:45 UTC，本地未提交）：wrapper-close 异常修复后的 `.venv` Python 3.11.15 完整测试门禁通过；receiver/native-probe 29/29，dup/SIGINT 连续 30 次通过，子模块/文档校验、限定文件扫描、compileall/diff check 均通过。最新精确树独立复审与 push 后远端 CI 尚待完成，未提交。本切片仅接收并校验 listener FD，不接 sender/bridge/策略，R2 网络与自动模式继续关闭。
- R2.4 Linux listener FD receiver follow-up（2026-09-27 14:40 UTC，本地未提交）：独立复审发现未交付 wrapper 的 `close()` 抛异常会跳过 raw SCM_RIGHTS FD 清理；新增真实 handoff/取消/close 异常回归，先红后绿，并用嵌套 `finally` 保证原始 descriptors 始终回收。handoff/native-probe 定向测试 29/29 通过；最后改动后的全量测试门禁、精确树独立复审与提交后 CI 仍待完成。该修复不接 sender、bridge、relay 或 Agent 网络，R2 网络 `DENY` 与自动模式关闭。
- R2.4 Linux listener FD receiver（2026-09-27 14:25 UTC，本地未提交）：新增标准库-only 私有 AF_UNIX/SOCK_SEQPACKET handoff 接收原语，按直接子进程凭据、固定消息、唯一 descriptor、IPv4 TCP listener 与 loopback 地址验证。独立复审曾真实复现主线程 `os.dup()` 前后 SIGINT 的 FD 别名泄漏；现改为主线程等待专用 worker，worker 独占接收、校验及 socket 接管，主线程中断时取消并在身份发布后 join，避免全局替换 signal handler。后续复审发现 cleanup signal 可跳过 join/关闭、外层 `except` 会污染 `sys.exc_info()` 判断、`Thread.start()` 身份发布前中断会让延迟 worker访问控制 socket；现改为显式记录 receiver 自身异常、保护区内完成返回，并在控制 socket 校验前处理取消。4 条清理/所有权回归先红后绿；真实 dup/SIGINT 回归连续 30 轮通过，receiver/probe 定向 28 项通过。项目 `.venv` Python 3.11.15 的完整 `preflight.py --only tests` 通过（系统 Python 3.10.12 不满足 `requires-python >=3.11`，其失败不作项目测试结论）；子模块、治理/站点/竞品文档校验、compileall、diff check 和六个变更文件的限定密钥形态扫描也已通过。最新精确树独立复审与新远端 CI 仍待完成。此切片无 sandbox sender、host bridge/relay、lease/Agent 接线或跨平台“只能到代理”证据；R2 网络与自动模式保持关闭，详见[R2.4 网络门禁计划](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)。
- CI [#247](https://github.com/ayukyo/icode/actions/runs/36315810399)（commit `8938c25`）暴露 loopback probe 的 runner 能力差异：Linux x64/ARM64 可建立 user/network namespace，但在新 namespace 启用 `lo` 时 `SIOCSIFFLAGS` 返回 EPERM；helper 在 payload exec 前失败关闭，因此不是网络隔离放行。修正后的本地用例确定性注入该 ioctl EPERM 并确认 payload 未启动；正向 loopback 端到端用例仅在无权配置接口时、且确认 payload 未启动后标为 skip，不能计作正向隔离证据。Python 3.11.15 的相关模块 13/13 通过；修正代码、完整门禁与新 CI 仍待验收。R2 conformance 保持 7/10、`critical_passed=false`、`ready=false`，R2 网络/自动模式继续关闭。
- R2.4 Linux loopback-only namespace probe（本地基础切片，2026-09-27 UTC）：新增不接入策略/Agent 的 native helper 实验选项，建立独立 user/PID/network namespaces，仅启用新 netns 的 loopback；seccomp 限定为 IPv4/IPv6 TCP stream，拒绝 UDP/raw/AF_UNIX `socket()`，只允许 AF_UNIX stream/datagram/seqpacket、protocol=0 的本地 `socketpair()` IPC。真实子进程验证 loopback 内通信、宿主 `127.0.0.1` listener 不可达、IPv4 无路由、IPv6 网络不可达/不支持；默认 DENY 拒绝全部 `socket()` 并限定有效本地 `socketpair()`。C `-Werror`、PID namespace/mapless 与定向 probe 通过，`scripts/preflight.py` 三道门通过，Linux wheel 构建/隔离安装/运行态探针通过；独立复核 0 Critical / 0 Important。原生 conformance 仍 7/10、critical=false、ready=false（临时 allowlist、资源限制、统一违规处理未验证）；该切片无 FD handoff/host bridge/CONNECT listener/lease，不开放 R2 网络或自动模式，新跨架构 CI 待推送后验证。
- R2.4 CONNECT pending numeric connector（phase14，本机验收完成，跨平台 CI 待本阶段提交）：新增 host-owned `open_authorized_https_connection()`，由调用方线程独占 nonblocking socket/selector，撤销经 socketpair 唤醒；authority pending entry 在 connect 前登记，numeric target completion 经 `SO_ERROR`、租约复核和原子 promotion 后才发布。独立复审发现并促成修复“同步 expiry sweep 的 close callback 跨过新租约期限后仍使用旧时间戳注册”的窗口：pending registration 必须提供单调时钟回调，authority 在清理回调结束后、锁内重新采样并验证 lease；TDD 回归确认到期后不会调用 `connect_ex`，缺少时钟、回调异常和非法时钟值都 fail-closed。lease/connector 平台 runner 在 Python 3.11.15、3.12.13 均 71/71 通过，13 项 connector 单测连续 20 轮通过；两版本完整 `scripts/preflight.py` 三道门通过；Python 3.11 wheel 隔离安装并从仓库外成功导入。另有 `KeyboardInterrupt` 先红后绿回归确认所有 pending descriptors 在中断传播前关闭。仍不接 listener/relay/worker/ToolContext；DNS 同步不可取消、OS 只到代理门未通过，网络与自动模式保持关闭。详见[R2.4 网络门禁计划](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)与[持续竞品对照](./agent-landscape-live.md)。
- CI [#244](https://github.com/ayukyo/icode/actions/runs/36303491439)（phase13 `a7f54ee`）整体状态为 Success，但 Linux native conformance 仍 7/10、`critical_passed=false`、`ready=false`；Python 3.11/3.12 作业另有 detached-descendant 与 protected-path 探针错误注解。不得把 workflow 总绿或这两个额外探针注解合并成 R2 隔离通过结论；阶段14提交后的新 CI 才覆盖 connector 改动。
- CI [#242](https://github.com/ayukyo/icode/actions/runs/36300286034)（commit `80b6e9b`）整轮 workflow 成功；Windows 原生 workspace job 实际通过 `mklink /J` 建链并完成 `snapshot_workspace` junction 拒绝回归，修复了 #241 的 harness 引号问题。Linux native conformance 为 7/10、macOS 为 6/10，二者 `critical_passed=false`、`ready=false`；workflow 成功不等于 R2 就绪，自动模式继续关闭。
- R2.4 CONNECT→lease→DNS 绑定（phase12 `867656e`）：新增宿主侧编排函数，CONNECT 解析和签名 lease/scope 校验先于 DNS，复用公网上游数值地址过滤，并在 resolver 返回后再次验证撤销代次/期限；11 项回归、20 轮、本地 wheel smoke 均通过。这里只返回不可变 numeric sockaddr 目标，不创建 socket、listener 或 relay；同步系统 DNS 仍阻塞且不可取消，worker 网络保持 DENY。
- CI [#243](https://github.com/ayukyo/icode/actions/runs/36302118672) 整体失败：Linux lease jobs 与两项 Python 主测试 job 通过；Windows/macOS lease job 中 3 项集成测试在 DNS helper 的 Python `ipaddress` 安全 patch-floor gate 处提前失败（`Python runtime is too old for safe IANA special-range classification`），未进入注入 resolver。生产 fail-closed gate 正确且不应放宽；phase13 仅让 lease-to-target 集成测试显式模拟受支持 classifier，并保留 `tests.test_network_destination` 的真实版本门测试。修正后的跨平台 CI 待推送验证；R2 native 仍 Linux 7/10、macOS 6/10、均 `critical_passed=false/ready=false`，完整 R2 与自动模式继续关闭。详见[持续竞品对照](./agent-landscape-live.md)及[R2.4 计划](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)。
- R3 Windows 工作区快照 fail-closed：Windows `snapshot_workspace` 使用 `scandir` + `stat(follow_symlinks=False)` 在进入目录/读取内容前拒绝 junction、mount point 与未知 reparse point；符号链接只记录链接目标文本。#242 原生 junction 测试通过；Linux 本地只运行模拟分支。静态路径检查仍不防同用户并发祖先替换，Windows Git tree OID 仍不支持，不改变 R2/R3 自动模式开放状态。源码证据及竞品取舍见[持续竞品对照](./agent-landscape-live.md)。
- R2.4 受门控 Git status 工具接线（2026-09-27 UTC，本地未推送阶段）：自主链路只传递与 control、ticket、run、policy、workspace 绑定的完整当前 `WorkspaceSession`，不再接受裸 Git identity；Linux 真 Landlock 且 session/policy/workspace 匹配时注册无参数只读工具。源码测试与本机 Linux x86_64 安装 wheel 均覆盖真实状态回执；wheel 探针还确认 Reviewer 不注册、固定无参 schema 和相对路径输出。Linux ARM64、macOS/Windows 等价证据待后续验收。Landlock 完整策略合同仍未 ready，实际自动模式未开启；Reviewer/普通任务/无会话不开放。详见 [Git broker 门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)。
- 时区说明：本轮提交 `7ae4559` 与 CI #230 的运行时间为 2026-09-26 UTC；本次 UTC 状态记录以该时区日期为准。
- 当前 R2/R3 状态（2026-09-26 UTC / 2026-09-27 Asia/Shanghai）：R3 自验证/有界修复、受控 MiniMax 修复闭环、受测 Git tree/可选结果 commit tree 绑定及 task receipt 均有本地证据；本轮另在 Bubblewrap 合成靶场强制进入短上下文 fallback，由真实 MiniMax-M3 提交唯一 `submit_review`，宿主合同通过、测试退出码 0、TaskReport 成功（2 次调用 / 3,967 tokens），不代表自然触发率。Linux Bubblewrap Reviewer 已通过本机只读账本隐藏与源码/输出写入拒绝测试；macOS Seatbelt Reviewer 同类拒读/只读负例已在 [CI #223](https://github.com/ayukyo/icode/actions/runs/36269281752) 的 `macos-latest` ARM64 和 `macos-15-intel` 原生 job 通过。Windows、WSL、容器及策略化 Reviewer 仍未开放。R2 原生隔离仍未达到跨平台开放门槛；网络授权目前是 host-only overlay 与测试用真实 socket 关闭适配器，没有生产代理或 OS 强制路由。受测 tree OID 的平台、attributes、嵌套 `.git` 与宿主执行环境证明范围有限，SHA-1 OID 不是安全认证。详见 [R2/R3 计划](./nbl/plans/2026-09-26-r3-self-verification.md) 与 [持续竞品对照](./agent-landscape-live.md)。
- CI [#231](https://github.com/ayukyo/icode/actions/runs/36281528655)（2026-09-27 UTC，commit `a20edad`）整体成功；Linux 原生探针证据仍为 5/10，macOS 为 6/10，均 `ready=false`。两架构 macOS 的 protected write/rename 拒绝及 workspace 写入正向 notice 为 true；这些局部证据不等同十项合同就绪。R2 与自动模式继续关闭。
- 上一阶段提交 `60b322ad1474b3bf840c6f852b5778182a78b201` 的 [CI #236](https://github.com/ayukyo/icode/actions/runs/36288760611) 已完成且所有作业成功：Linux x64/ARM64、macOS Intel/Apple Silicon、Windows x64/ARM64、Python 3.11/3.12；官网 [#146](https://github.com/ayukyo/icode/actions/runs/36288760512) 也部署成功。它们只验证 `60b322a`，不覆盖此后本地代码。
- R2.2 Linux 进程树清理回执（commit `ab624ee`，2026-09-27）：新增独立运行时探针，复用经 SHA-256 清单核验的原生 helper；宿主被 `SIGKILL` 后，以 NSpid、唯一命令参数和进程 start-time 确认测试孙进程，再用 pidfd 观察退出并检查延迟写哨兵。结果并入 native conformance，未执行或失败即令 CI 失败。[CI #237](https://github.com/ayukyo/icode/actions/runs/36290433525) 整轮成功，4 个 Linux 原生 runner（Ubuntu 22.04/24.04，x64/ARM64）的清理回执均通过；Linux 仍为 7/10、macOS 6/10，`ready=false`。这不是 R2 完成或自动模式开放；`doctor` 不自动运行较重清理探针，macOS 仍按用户批准的同组边界验收。
- R2.2 安装式 wheel 宿主崩溃清理（本地阶段，2026-09-27）：在 wheel 独立 venv/no-`PYTHONPATH` 验证中新增宿主 Python 收到 `SIGKILL` 后回收 `setsid()` 脱组后代的实测；回执显式检查宿主退出码 `-SIGKILL`，后代使用 pidfd 等待并验证延迟写哨兵未出现。Python 3.11.15 x86_64 从 tracked snapshot 离线构建 wheel 后，wheel 检查、隔离安装、原有正常退出探针、新增宿主崩溃探针和 Git broker 探针全部通过。标准 `run_native_wheel_ci.py` 的本机构建步骤因 PyPI TLS EOF 未完成，因此此本机实跑重用了离线构建 wheel；下一次 GitHub CI 才能验证标准构建路径和 ARM64 安装 wheel。R2/自动模式保持关闭。
- R2.2 安装式 Linux wheel 清理因果门禁（本地复核，2026-09-27）：独立审查发现旧探针未确认后代在宿主被杀前仍存活，可能把目标先行退出错误归因给宿主崩溃。增加 pidfd `poll(0)` 杀前检查与 fail-closed 回执，并新增真实进程树场景下的“pipe HUP 就绪 FD 替身”负例；该用例证明探针对任何预先就绪事件拒绝归因，不冒称真实 pidfd 退出。TDD 先复现旧实现误通过，修复后 40 项定向回归通过（1 项仅 macOS 执行而跳过），全量 `preflight.py` 三道门通过。tracked snapshot 的离线 wheel 经隔离 venv 安装后，检查、普通 smoke、宿主崩溃清理与 Git broker 阶段全部通过；Linux 原生证据现明确报告杀前存活、宿主 `-SIGKILL`、目标退出及无延迟写入。新提交的标准构建和 ARM64 wheel 结果仍待 CI；native conformance 仍为 7/10、`ready=false`，R2/自动模式保持关闭。
- R2.4 Git status 身份锚点后复核（本地切片，2026-09-27）：status 子进程成功后重查 manager-issued `.git`/common-dir、`HEAD` 与 ownership marker；本机竞态测试证明查询期间 `HEAD` 原位变更会丢弃结果。37 项执行器/Git broker/PID namespace 定向测试、`scripts/preflight.py` 三道全量守护和 Linux x86_64 安装式 wheel probe 通过。它不构成原子元数据快照，不能检测短暂改写后恢复或 `config/index/refs` 内容变化；ToolContext/模型工具仍未接线，ARM64 wheel 与跨平台门槛待后续验证，R2/自动模式继续关闭。上游无直接同类快照可复用，详见[持续竞品对照](./agent-landscape-live.md)与[Git broker 门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)。
- R2 Windows named-pipe 探针时序（本地切片，2026-09-27 UTC）：移除错误 PID 负例探针的固定 25 ms 启动 sleep；微软合同允许客户端先连接，服务端 `ConnectNamedPipe` 返回 `ERROR_PIPE_CONNECTED` 仍是有效连接，现有处理分支新增回归。TDD 新测试先因检测到 sleep 失败，移除后 Windows pipe / 标准用户探针 57 项通过。Codex `985cf47a…` 也容忍此错误码并在连接后校验 PID、保留有界等待；采用机制、不复制实现。此主机 Linux 上的模拟测试不是 Windows 原生复测；手动 x64/ARM64 workflow 未运行，标准用户管道仍未验收，R2 与 Windows 自动模式继续关闭。上一代码提交 CI [#235](https://github.com/ayukyo/icode/actions/runs/36286075211) 已成功，但不会覆盖本地未推送变更。
- R2 POSIX 保护路径负例（本地切片，2026-09-27 UTC）：自动工单工作区在 POSIX 上启用已有 `isolate_git_metadata` 分层布局；新增 Landlock 原生探针，实测 `code/` 可写且兄弟 `.git` 元数据不可写、不可重命名，并把直接证据并入 `doctor` 与 CI 评分。188 项定向回归（8 项平台跳过）、`scripts/preflight.py` 三道门和已安装 Linux wheel / Git broker probe 均通过；本机 native probe 为 6/10、`critical_passed=false`、`ready=false`。这不验证可写根内部的受保护子目录，也没有 Linux ARM64、macOS 或 Windows 新代码原生 CI 证据；CI #235 对应前一提交 `b788ca1`，不能外推到本地改动。R2 和自动模式仍关闭。
- R2.4 host-only 自动到期 sweep（本地切片，2026-09-27）：新增显式启动、单次使用的 `NetworkLeaseExpiryMonitor`，默认每 100 ms 调用既有 authority sweep；清理失败仅暴露固定健康类别并继续重试，停止 join 有 5 秒上限。本机 5 项真实 loopback/重试/错误脱敏/参数/停止超时测试通过；平台 lease CI runner 已纳入该测试模块，新的跨平台结果待推送后验证。它尚无生产 proxy lifecycle owner，也不开放 listener、worker 或 Agent 网络；到期延迟最多约一个 sweep 间隔加关闭回调耗时，仍不叫“立即”。
- R2.4 授权契约更新（2026-09-27）：网络租约 schema v2 改为由可信宿主签发、绑定完整默认 `DENY` policy 的精确域名 overlay；普通候选策略和 `tighten_policy()` 不变。Python 3.11.15 下 `tests.test_network_lease` 28 项通过；`scripts/preflight.py` 密钥、子模块和全量 unittest 三道守护均通过，治理、站点和 20 项竞品排期校验也通过。CI [#226](https://github.com/ayukyo/icode/actions/runs/36271940621) 的 workspace-platforms 三项任务成功（含租约/socket 测试），整轮另在 macOS `Verify policy command broker` 失败；同 job 的 native-probe 脚本先成功退出，conformance 仍为 6/10、未 ready。不得把此评分当作 protected-path 失败定位。此 overlay 不建立代理或 OS 路由，网络仍不向 Agent 开放。
- R2.4 DNS 目标校验原语（2026-09-27）：新增宿主侧 `resolve_public_tcp_targets()`，原始输入先作 ASCII 校验，拒绝 Kelvin 等 Unicode 大小写折叠绕过；仅 resolver 参数添加 DNS 根尾点，避免本地域名搜索后缀改写目标；全量拒绝非公网 IPv4/IPv6 答案，并对过旧 Python `ipaddress` 分类表在查询 DNS 前 fail-closed。11 项 helper 测试及策略/租约相关共 92 项定向测试通过。它不验证 lease、不拨号、不接入 CONNECT/worker；DNS 取消、连接建立撤销和 OS“只到代理”门仍未完成。详见[持续竞品对照](./agent-landscape-live.md)与[R2.4 计划](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)。
- R2.4 CONNECT request-head parser（2026-09-27）：宿主侧纯字节解析器仅接受 `CONNECT ascii-host:443 HTTP/1.1` 与一个规范化后相符的 Host；拒绝其他头/CL/TE、凭据、歧义 authority、非 CRLF、尾随字节和超限输入。`tests.test_connect_request` 8 项、连同 DNS/policy/lease 定向共 100 项通过。它不读 socket、不验证 lease、不做 DNS/拨号、也不接 Agent；通用 HTTP 代理兼容性需后续实测确认，所有生产网络能力仍关闭。CI [#228](https://github.com/ayukyo/icode/actions/runs/36274941264) 整轮在 macOS `Verify leased TCP socket lifecycle` 失败；同 job 前置的 native-probe 步骤已成功退出，但 macOS conformance 6/10、Linux 5/10，均未达到 ready。公开摘要不能把评分缺项定位成 protected-path failure，也不代表 CONNECT parser 验收；详见[持续竞品对照](./agent-landscape-live.md)与[R2.4 计划](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)。
- R2.1/R2.2 macOS CI 失败项复核（CI #229，2026-09-27 UTC）：[最新 run](https://github.com/ayukyo/icode/actions/runs/36276572030) 的 ARM64 `macos-latest` 和 Intel `macos-15-intel` 均在 `Verify leased TCP socket lifecycle` 失败；此前的 `Run actual native negative probes` 已成功退出（由同 job 后续步骤运行、workflow 无 `always()` 推得），因此此 run 不支持“内嵌 protected-path 探针失败”的结论。conformance `6/10`、`ready=false` 是十项评分，不能单独定位 protected paths。排在 lease 步骤之后的独立 `Verify protected-path Seatbelt policy` 未运行；Python 3.11/3.12 全量测试 job 虽有 `protected paths failed` annotation，但它与真实 macOS native job 是不同执行链，单凭摘要不能认定为 macOS 原生失败。原始 Actions 日志需登录，lease 子测试名/错误仍未知。当前 CI 将以固定检查名/布尔值报告实际 native-probe 子项，并以安全化测试 ID 报告 lease suite 中失败用例；本地 native-probe 单测、lease reporter 两项测试及真实 lease 模块 29 项通过，远端 macOS 待复测。R2.1 lease 跨平台生命周期及 R2.2 独立 Seatbelt 测试仍未验收，自动模式保持关闭。
- R2.1/R2.2 macOS CI 失败项复核（CI #230，2026-09-26 UTC）：[run #230](https://github.com/ayukyo/icode/actions/runs/36279299022) 已输出精确用例 ID：`test_revoke_closes_socket_after_original_wrapper_detaches` 在 `macos-latest` workspace 与 `macos-15-intel` native job 失败，另一个 macOS native lease job 通过。Actions 注解确认是 assertion failure，但完整 traceback 需要登录才能查看。候选原因是测试在 revoke 后只做一次 non-blocking `recv()`；Python 文档说明此类立即不可读会产生平台相关错误，故先改为 5 秒有界等待 EOF，本地复验通过，待新跨平台 CI 验证。此为测试时序候选修正，不改变 socket close 实现，也不表示 R2.1 生命周期验收通过。
- R2.4 Git broker 生命周期修正（2026-09-27 UTC）：真实子进程测试发现并修复“stdout/stderr 提前 EOF 被误作命令退出”，现在在原墙钟 deadline 内继续等待直接子进程。执行器/Git broker 定向 24 项、全量 preflight 与 Linux x86_64 安装式 wheel probe 通过；Codex/Qwen/Gemini 上游机制与采纳边界见[持续竞品对照](./agent-landscape-live.md)和[Git broker 门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)。此项不证明脱组后代零残留或跨平台 broker 已就绪，R2 自动模式仍关闭。
- R2.4 Git broker 单次查询共享 deadline 与 metadata inode 竞态（2026-09-27 UTC）：一次 status 查询内的配置、index、status 子命令现共享 `min(timeout, policy.wall_timeout_seconds)` 单调执行 deadline；fractional 剩余时限不向上取整，任何阶段超时都拒绝整份状态。真实 Linux helper 测试确认 Python recheck 后将 `.git` 指针换成相同内容的新 inode 会在 payload 前被拒，随后恢复原对象。36 项执行器/Git broker/PID namespace 定向测试、全量 preflight 三道守护、Linux x86_64 安装式 wheel broker probe 通过；新推送 CI 与 Linux ARM64 wheel 待验证。cleanup 的有界等待可晚于命令 deadline；元数据目录 inode 校验不证明内部文件原位写入免竞态。Git 工具入口、自动模式和网络仍关闭，详见[Git broker 门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)及[持续竞品对照](./agent-landscape-live.md)。
- 最新 Windows 诊断（2026-09-26 UTC）：手动 [CI #213](https://github.com/ayukyo/icode/actions/runs/36252440492) 在 x64 与 ARM64 均以 `CreateFileW` `winerror=5` 失败；两端标签为 `token_process`、`il_medium`、`restricted_no`、`logon_enabled`、`nwu_yes`、DACL `ace_match+access_allow`、`pipe_il_absent`、`pipe_nwu_unavailable`、`token_nwu_yes`。相较 [CI #210](https://github.com/ayukyo/icode/actions/runs/36247565458)，标准用户 token 的观测新增 no-write-up/mandatory policy 标签，但 pipe 的 mandatory label 查询仍 unavailable；只读 `AccessCheck` 仍不能解释内核实际拒绝，不能推断根因。观察器不更改 token、请求权限、pipe DACL/SACL；额外采样的时序影响仍保留为限制。Windows 自动模式保持关闭；[CI #212](https://github.com/ayukyo/icode/actions/runs/36252023822) Linux/macOS conformance 仍 `5/10`、`critical_passed=false`、`ready=false`。
- **CI #213 源码级候选复核（observation-only）：**客户端和 pipe DACL 的显式请求/授权掩码均为 `0x00100003`，没有请求 GENERIC access；微软文档所述 `FILE_CREATE_PIPE_INSTANCE`/`FILE_GENERIC_WRITE` 陷阱目前不能解释这个客户端请求。DACL `AccessCheck=allow` 不是实际 `CreateFileW` 授权结果；当前标签也不能证明 `AccessCheck` 使用了 CreateFile 同一线程的有效 token。pipe 标签查询 unavailable 不足以判定 MIC；详见[持续竞品对照](./agent-landscape-live.md)的 2026-09-26 Windows 定向复核。下一步只增加同线程 token 与 pipe 描述符/连接状态的只读观察，不放宽 ACL 或请求掩码。
- 此前 Windows 诊断计划（CI #206，已由 #208 实施）：[CI #206](https://github.com/ayukyo/icode/actions/runs/36243032179) 在 Windows x64 与 ARM64 得到 `dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_allow`，但实际客户端 `CreateFileW` 仍为 access denied。随后按微软 API 合同只读增加真实 pipe `LABEL_SECURITY_INFORMATION` label 与目标 child token 的 `TokenIntegrityLevel`/`TokenMandatoryPolicy` 观察；不读取完整 SACL、不记录 SID/RID，观察结果仍不能代替内核调用结果。
- 此前 Windows 诊断（CI #204，2026-09-26 UTC）：手动 [CI #204](https://github.com/ayukyo/icode/actions/runs/36242591553) 的 x64/ARM64 诊断标签一致：`dacl_present+ace_match+token_child_process+logon_enabled+restricted_no+access_unavailable`，而 `CreateFileW` 仍为 access denied。对照 Microsoft API 合同发现诊断只请求 DACL 的部分安全描述符，`AccessCheck` 需要 owner/group SID；已按 TDD 加入 owner+group+DACL 查询并有回归覆盖。当前只是可验证根因候选，修正后双架构结果未出；不据此放宽 ACL 或宣布通过。
- 此前诊断补充（CI #202，2026-09-26 UTC）：手动 Windows [CI #202](https://github.com/ayukyo/icode/actions/runs/36242053362) 在 x64/ARM64 均仍报告通用 `RuntimeError`；复核源代码发现子进程诊断以 `+` 连接的固定标签被外层异常安全过滤器拒绝，导致原始权限诊断被遮蔽。已新增有界标签白名单和负例，保留合法的 DACL/token 标签，同时拒绝路径或任意异常正文；定向探针 31 项及全量 preflight 通过。该修正尚待新的双架构原生 workflow_dispatch；R2/R3 仍未完成。
- 历史状态快照（CI #200，2026-09-26 UTC）：手动 Windows CI [#200](https://github.com/ayukyo/icode/actions/runs/36240714328) 已确认标准用户探针 x64/ARM64 均在子进程 `CreateFileW` 打开管道时 `access_denied`；其他 Windows Job/wheel/workspace 作业通过，Linux/macOS conformance 仍为 `5/10` 且未 ready。当前本地改动加入仅在该失败阶段触发的只读诊断：以真实子进程 token 对照服务端管道 DACL，不改变 ACL 或访问掩码；Windows 代码路径尚待新 CI 原生验证。R3 真模型修复闭环仅在受控 MiniMax 靶场通过；工作流 Reviewer 跨平台边界与真实 Git SHA 锚点仍未闭合。因此 R2、R3 均继续进行，不宣称完成。
- CI #198 / R3 状态快照（2026-09-26 UTC）：当时 Windows x64/ARM64 探针仍报 `unclassified`，R3 的真实修复分支已触发但 Reviewer 合同未成功；后续的 CI #210 与受控 MiniMax 修复闭环已更新在上方及 [R3 计划](./nbl/plans/2026-09-26-r3-self-verification.md)。
- Windows 门禁刷新：手动 [CI #192](https://github.com/ayukyo/icode/actions/runs/36226116303) 的 x64/ARM64 普通构建、R2.1 工作区、Linux/macOS 原生探针、Windows Job/wheel 和仓库检查通过；Windows 标准用户 runner pipe PID 负例失败在宿主 Actions 令牌的 `CreateFile` ACL 拒绝，尚未到 PID 比对。本轮将负例测试移入临时标准用户 runner 上下文，并保持父子正向握手/失败回报；需下一次双架构 Windows CI 验证。该失败不证明 PID 校验失败，也不证明管道门通过；Windows 自动模式继续关闭。
- Windows runner pipe 最新证据（2026-09-26 UTC）：手动 [CI #184](https://github.com/ayukyo/icode/actions/runs/36197559399) x64/ARM64 均在 `CreateFileW` 得到 access denied。刚完成的只读诊断候选会在相同客户端线程读取真实 DACL、effective token 的 logon SID 状态，并对 `0x00100003` 运行 `AccessCheck`；本机 32 项定向测试通过，但尚无新 Windows 原生结果。一个 restricted child 的 restricting-SID 修改与失败调用不在同一调用链，已撤销；不扩大 ACL、Windows 自动模式保持关闭。常规 push CI [#194](https://github.com/ayukyo/icode/actions/runs/36232004437) 通过，但手动标准用户 probe 因仅 workflow_dispatch 而跳过，不能作为此门的复验。
- R3 真模型修复尝试：较早试跑触发 `repair_decisions=allow` 后仍因 Executor 回合耗尽与 Reviewer 合同失败而 fail-closed（18 次调用 / 68,929 tokens）。本轮 MiniMax-M3 TDD 靶场进一步验证真实修复回合后独立 20 项测试通过，Reviewer 合法审查并且 `TaskReport.ok=True`（25 次调用 / 109,087 tokens）；因此 R3 `run_task` 真实修复闭环已在受控靶场通过，但不能替代 Git SHA 绑定、workflow review 跨平台边界或通用项目成功率验收。
- 状态：**R2.1 工作区边界已验收；R2.2 Linux/macOS 原生隔离门、R2.3 Windows AppContainer 生产候选及 R2.4 Linux x86_64 内部 Git broker 的剩余边界详见各验收记录；Windows 自动模式、Git 工具入口和网络保持关闭。R3 自验证/有界修复、受控 MiniMax 修复闭环、稳定受测 Git tree/可选结果 commit tree 绑定及 task receipt 已有证据；短上下文终结器另有一条合成靶场的强制触发真实 MiniMax 证据，不代表自然触发。Linux Bubblewrap Reviewer 已验证只读工作区与 `.icode_output` 同 namespace 隐藏；macOS Seatbelt Reviewer carve-out 已在 CI #223 的 ARM64 `macos-latest` 与 Intel `macos-15-intel` 原生 job 通过。Windows、WSL、容器和策略化 Reviewer 仍 fail-closed，不能外推为跨平台边界通过。`VerificationEvidence` 绑定基线、快照、改动、测试和结果对象信息；空测试集失败，内部 unittest 用 `-B`。tree OID 仅表示受限的 Git 路径/字节/模式投影，SHA-1 非安全认证，不覆盖宿主环境、ACL/xattr、attributes clean filter、Windows 或嵌套 `.git` 等边界。R2 原生隔离和网络租约门仍未闭合，不据常规 CI 通过宣称 R2/R3 完成。**
- R2.3 后续切片（2026-09-26）：Windows 架构 wheel 打包合同已在 CPython 3.11 全量 preflight、Linux 安装式 wheel probe 及 Windows x64/ARM64 合成 PE 打包安装 CI 中通过。它不含可运行 Windows 隔离 helper，不代表 Windows 隔离实现，详见 [Windows 后端路线复核](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)。
- R2.3 Windows wheel/CI runner 复核（2026-09-26）：#161 x64 发现 SHA 清单 CRLF 字节匹配缺陷；#162 修复后两个架构 wheel job 均通过。#162 旧 AppContainer 综合步骤仍失败，已移为显式手动诊断并保留失败证据；随后 #163 常规 CI 整体通过，但不代表 Windows 文件/网络/身份隔离完成。
- R2.3 IPC 协议切片（2026-09-26）：`windows_runner_protocol.py` 实现纯解析/编码、64 KiB 帧上限及严格版本/字段/类型/关联校验；CI [#173](https://github.com/ayukyo/icode/actions/runs/36188277042) 全部通过。未实现具名管道、对端认证、权限授予或命令执行连接；安全传输与 Windows 自动模式仍关闭。
- 依据：[持续竞品对照](./agent-landscape-live.md) · [方案与决策记录](./design-decisions.md)

---

## 0. 一句话策略

调研结论收敛成两条：

1. **不做什么** —— 结合持续竞品对照，定期复核不学清单，避免把旧热度结论当成当前事实
2. **先做什么** —— 把「**过程可审计**」做成内核，而不是把功能做多

**战略主线**：功能广度上我们注定打不过 OpenCode / Codex / Claude Code，
唯一的赢面是**在"证据与门禁的严格性"这一个维度上做到无人能及**。

---

## 1. 三条原则（用于裁决所有后续争议）

| # | 原则 | 含义 | 冲突时的取舍 |
|---|---|---|---|
| P1 | **门禁不可绕过 > 功能多** | 只要 Agent 能绕开门禁，"可审计"就是谎言 | 为了保住不可绕过，宁可少做工具、降低自动化程度 |
| P2 | **过程可审计 > 产物可审计** | 这是与治理 sidecar 阵营的唯一切割点 | 不为兼容其他宿主而让证据链降级为旁路日志 |
| P3 | **成本可控 > 单次吞吐** | 我们的步骤文档 67–146KB，是全行业最大的 | 宁可慢、宁可多次交互，也不能全量注入 prompt |

---

## 2. 能力边界：对齐什么、不做不学什么

**重要澄清**：本路线图强调"别做广度"，指的是**不争形态渠道、不追功能数量**，
**不是**"功能少"。主流 Agent 的底层能力我们**基本都要对齐**——因为缺了它们，
"过程可审计"根本无从谈起（没有 Tool Loop 就没有过程，没有 MCP 就没有生态）。

### 2.1 主流能力对照（对齐清单）

| # | 能力 | 主流代表 | 我们的计划 | 阶段 |
|---|---|---|---|---|
| 1 | **Tool Loop**（读/写/改/检索/执行） | 全部 | ✅ 最小集 `read/grep/glob/write/edit`；`bash` P2 仅白名单命令，P5 随沙箱全开 | P2 起 |
| 2 | **多模型 backend** | Aider(100+)、OpenCode(75+) | ✅ backend 抽象 + MiniMax-M3 / OpenAI 兼容 / Anthropic / 本地 | P2 起 |
| 3 | **MCP 扩展** | 几乎全部 | ✅ 复用上游生态（`icode-skill` 已带 17 个 MCP 定义） | P2+ |
| 4 | **上下文管理** | Claude Code 压缩、Aider Repo Map | ✅ **渐进披露**（比"事后压缩"更前置） | P1 |
| 5 | **计划/执行分离** | Aider architect、OpenCode Plan | ✅ 工单制天然分段（Plan→Review→Merge→Code） | 已有 |
| 6 | **项目规则 / 红线** | `AGENTS.md`、`.clinerules` | ✅ `limit`（项目约束红线）+ `steps/` + `references/` | 已有 |
| 7 | **Skills 体系** | Claude Code、Gemini CLI | ✅ 复用 `icode-skill` 的共享技能包 | 已有 |
| 8 | **子代理 / 独立审查** | Claude Code、Kimi（300 并行） | ✅ **但用途不同**：只做**独立质疑者**，不追数量（见 2.3） | P3+ |
| 9 | **审批 / 权限** | Cline 每动作批准、Codex 沙箱+审批 | ✅ 应用层限制 + 审批门禁；**内核沙箱后置** | P1/P2 |
| 10 | **会话恢复 / 检查点** | LangGraph、Cline、OpenCode | ✅ checkpointer 与事件链**双轨** | P4 |
| 11 | **审计 / 证据留痕** | Cline、sofagent | ✅ **这是我们最强项**，且要导出为可独立校验的证据包 | 已有 + P3 |
| 12 | **本地 WebUI** | 上游已有、OpenCode | ✅ 二期（loopback + SSE） | P5 |
| 13 | **便利分发** | 各家安装方式 | ✅ Python 包（`pipx` / `uv tool install`） | P5 |

**结论**：以上 13 项，**没有一项是我们"不支持"的**。差别只在**顺序**和**实现方式**。

> ⚠️ **期待管理**：P1 结束时的 `icode` 是一个**几乎没有功能的契约测试壳**。
> 要等到 **P2 才是"能用的 Agent"**，P3 才有产品形态。不要指望一期就有完整体验。

### 2.2 四个已被填满的坑（形态渠道，不做）

| 不做什么 | 谁在做 | 为什么不做 |
|---|---|---|
| 通用 CLI 编码 Agent | OpenCode(~200k★)、Codex CLI、Gemini CLI、dsh(~203k★) | 四强混战，无差异化空间 |
| IDE 内 Agent / 插件 | Cursor、Cline、Continue、Kilo | 我们的卖点是可审计，不是编辑器体验 |
| 云自主 Agent（issue→PR） | Devin、OpenHands、Jules | 需要云基础设施与沙箱，重资产 |
| 通用 Agent 框架 | LangGraph、CrewAI、AutoGen、OpenAI SDK | 我们是应用，不是框架 |

### 2.3 七项"明确不学"（有意识地放弃）

| 不学 | 出处 | 为什么不学 |
|---|---|---|
| 数百并行子代理 | Kimi Code `/swarm`（最多 300） | 与 P1 冲突：并发放大门禁与审计难度，先要可控 |
| "采纳率 / 补全率"类指标 | 国产厂商常见口径（44%、68–82%） | 是营销指标不是可靠性证据，会诱导我们做假优化 |
| 工具白名单冒充"沙箱" | 多数产品的实际做法 | 会给我们虚假的安全感，必须诚实标注能力边界 |
| 多 LLM 投票式对抗验证 | 部分多代理框架 | arXiv 2512.03097 已证明共谋可攻破；坚持规则绑定 + 禁止自我委派 |
| 一次性实现内核级沙箱 | Codex（Seatbelt / bwrap+seccomp） | 三平台成本极高，且会拖死进度；改为分阶段 |
| 多形态入口同时铺开 | 腾讯 CodeBuddy 三形态 | 三形态是渠道打法，我们是单点深度打法 |
| 全量上下文注入 | 我们当前的默认做法 | 是成本生死线，必须改成渐进披露 |

---

## 3. 分阶段路线图

> **排序已按确认结论调整**：原计划的"证据包导出"从最后一期**提前到 Phase 3**。
> 理由见 §4 —— 它不是锦上添花，而是我们的**产品形态**。

### Phase 0 —— 预研与准备（**已完成**）

| 项 | 状态 |
|---|---|
| 预研报告 | ✅ `docs/preresearch-2026-09-22.md` |
| 方案与决策记录 D1–D10 | ✅ `docs/design-decisions.md` |
| 格局调研 | ✅ 历史快照 `docs/agent-landscape.md`；持续对照 `docs/agent-landscape-live.md` |
| 子模块（ssh + main + 浅克隆） | ✅ `vendor/icode-skill` @ `a4ddbce` |
| E2E 靶场 | ✅ `tests/fixtures/pycalc`（主）+ `tests/fixtures/demo`（附加） |
| 跨平台换行治理 | ✅ `.gitattributes` + 4 个 C 文件规范化回 LF |

---

### Phase 1 —— 契约内核（离线，零成本）

**目标**：证明我们与控制面完全对齐，全程不调真模型、不花钱、可进 CI。

| 项 | 内容 |
|---|---|
| 交付 | `pyproject.toml` + `src/icode/{config, control, backends, cli}` |
| backend | 只接 `fake`（离线回放） |
| 关键链路 | `step start → check(before_write) → artifact → check(before_transition) → finish` 全通，并用 `icode_control.py trace` 校验事件链 |
| **渐进披露（硬要求，分两层）** | **门禁规则每步强制注入（不可懒加载）**；背景知识才允许按需加载——先只读 frontmatter + 章节索引，按步骤再取正文。**禁止一次性注入整份文档** |
| 契约来源 | 从 `gates.json` 的 `step_contracts` 动态读取必需输入/输出/复检点，**不写死步骤表** |
| **上游契约防御** | 文档化依赖的控制面子命令与输出字段清单；**每次子模块 bump 必须重跑契约握手冒烟测试**。注：gitlink 记录的就是具体 commit，"跟随 main"实为**手动 bump**，不会自动漂移 |
| 权限模型（应用层） | 只读自动放行；工作区内写按策略判定；工作区外与危险命令**默认拒绝**。**措辞上不得宣称"沙箱"**，只称"应用层限制" |
| 验收 | ① `python -m unittest` 全绿 ② `trace` 显示事件链完整且 `open_steps` 为空 ③ 全流程无网络访问 ④ **子模块完整性：`vendor/icode-skill` 无任何本地修改**（`git -C vendor/icode-skill status --porcelain` 输出为空） |
| 成本 | 0 元 |
| 风险闸门 | 若发现控制面必须人工交互才能推进，立即停下来重新评估自动化边界 |

---

### Phase 2 —— 真模型 + Tool Loop（**已完成**，2026-09-23）

**目标**：在 `pycalc` 上真正跑完一条端到端流程，用退出码验收。

| 项 | 内容 |
|---|---|
| backend | MiniMax-M3（OpenAI 兼容，**标准库实现，零依赖**）；保留 anthropic / 本地扩展位 |
| 工具集 | `read / grep / glob / write / edit`（最小集）；**`bash` 默认禁用，仅开放白名单命令**（如 `python -m unittest`）——沙箱在 P5，执行类工具的开放程度必须与阶段绑定 |
| 副作用处理 | 所有写与执行动作包 `operation` 回执（start/finish），支持 `ambiguous_side_effect` 拒绝重放 |
| **人机交互协议** | CLI 形态：门禁要求人工决定时（destructive / `ambiguous_side_effect` / 工作区外写）**暂停并显式提示，用户确认后才继续**；非交互环境**一律拒绝** |
| **E2E 隔离** | 运行前**把靶场复制到临时工作区**再操作，跑完丢弃——避免污染 `tests/fixtures/` 基线 |
| **幂等键** | **确定性**幂等键（由稳定逻辑坐标派生，**不用随机 UUID**）；只读动作的传输类失败可自动重试 |
| **实测验收** | ① `icode task`：隔离靶场改 `calc.py`/`test_calc.py`，**独立跑 unittest 退出码 0**（11 回合 / 41,343 tokens）<br>② `icode step-run --step plan`：产物 `01_plan.md` 登记成功、`finish success`、事件链 24 条无未闭合 |
| 成本 | 实测 41K tokens / 任务（cached 33.9K）；预算闸门就绪 |
| 遗留 | 状态前移仍被 `thinking_gate` 拦下（未接 sequential-thinking，如实 degraded 不冒充）；完整 1→6 链路待后续 |

**Phase 2 实测中修掉的真问题**（都是真实运行才暴露的）：

| # | 问题 | 修法 |
|---|---|---|
| 1 | 模型习惯传 `"ls && -la"` 这类 shell 串，被当作"未知命令等审批"，提示词对模型毫无指导 | guard 增加**形态校验**：单参数含 shell 元字符 → DENY + 可纠正提示 |
| 2 | 简报里的上游相对链接 `../references/x.md` 诱导模型读工作区外文件，白烧整轮 | 简报**降级相对链接为纯文本** + 声明上游路径不可读 |
| 3 | 简报只列输入文件名不报存在性，模型满目录找 `00_init.md`，12 回合全耗尽在侦察 | 简报**逐项标注输入实际存在性** + 提示词禁止无目的侦察 |
| 4 | `ProxyHandler({})` 不注册为 handler，直连逻辑形同虚设；托管环境隧道代理 502 | 改为 `_proxy_mapping()` 显式契约；新增 `--no-proxy` / `ICODE_LLM_NO_PROXY` |
| 5 | 模型调用无重试，网络抖动即中断整步 | 只读动作的**传输类失败自动重试**（4xx 不重试），`Usage.retries` 可观测 |
| 6 | 触到 `max_turns` 时即使产物齐备也判失败 | **由证据判定成败**，不由循环停止原因判定；非自然结束降级为提示 |

---

### Phase 3 —— 证据包导出（**已完成**，2026-09-23）

**为什么提前**：这是唯一把 P2（过程可审计）变成**可交付物**的一步。
外部审计方消费的不是我们的日志，而是证据包——**它才是产品**。

| 项 | 内容 |
|---|---|
| **最小版证据包** | `manifest.json`（清单 + `pack_digest`）+ `ticket/events.jsonl`（账本原样）+ **`ticket/bodies/` 正文快照** + `artifacts.json`（正文↔链上 sha256 对应表）+ `contracts.json`（契约快照）+ `verifications.json`（含命令退出码）+ `verify.py` |
| **独立校验器** | `verify.py` **零依赖、不 import 本仓任何代码**（有静态测试断言），审计方只需 Python 标准库 |
| 校验覆盖 | ① 清单完整性 ② 事件链哈希链（复算 `canonical_event_hash` + `previous_event_hash` 链接 + event_id 唯一 + 首事件类型）③ 正文与链上哈希对应 ④ 包摘要 ⑤ **未登记额外文件** |
| **对外定位口径** | 明确切割治理 sidecar 阵营，主打"**审过程而非审产物**"；四条诚实边界写进包内 README |
| 验收 | 对一条真实工单导出包：**审计方在包外、无 PYTHONPATH 下独立校验通过（exit 0）**；篡改正文一处即被检出 4 处问题（exit 1） |

**实测结果**（用真模型产出的工单，24 条事件 / 1 个产物）：

```text
审计方独立校验（cwd=/，无 PYTHONPATH）→ 退出码 0
篡改正文后 → 检出 4 处：清单不符 / 大小不符 / 与链上哈希不符 / 链上产物缺正文快照 → 退出码 1
```

**四条诚实边界**（写在包内 README，不可省略）：
1. 证明「过程记录自洽且未被篡改」，**不是**「代码绝对正确」
2. `pack_digest` 需**外部锚定**才具抗抵赖力，否则可被整体重签
3. 权限模型是**应用层限制，非内核级沙箱**
4. 未接入 `sequential-thinking`，推理 trace 如实标 `degraded`

**Phase 3 顺带修掉的一个跨平台坑**：把 Git Bash 的 `/c/xxx` 路径传给 Windows Python
会抛 `NotADirectoryError` 堆栈；CLI 现在给出可操作的提示（"请用 `C:/...` 形式"）。

---

### Phase 4 —— 韧性与恢复（**已完成**，2026-09-23）

**双轨分工**：事件链管"发生了什么"（审计），检查点管"走到哪了"（恢复）。

| 项 | 内容 |
|---|---|
| **检查点** | `.agent_checkpoint.json`，**原子写**（临时文件 + `os.replace`）；只存回合数 / 工具调用数 / 历史摘要 / 未决审批计数 |
| **不保存模型正文** | 安全底线：模型对话内容绝不落盘；恢复时**从事件链重新水合上下文**，不回放聊天记录 |
| **真源优先级** | 检查点与事件链冲突时**事件链优先**，检查点被丢弃并告警 |
| **恢复决策** | `start_fresh` / `resume` / `verify_side_effect_first` / `blocked`；由 `trace` 的 `open_steps`·`open_operations`·`open_agents` 投影判定 |
| **副作用 fail-closed** | 有未终结副作用时**拒绝自动恢复**，要求先核对真实状态，再用 `resolve_open_operation()` 补 finish（上游规定的正确收尾） |
| **未决审批** | `pending_approvals > 0` 时明确提示"不会自动放行"，必须重新人工确认 |
| 类别未知时 | **按副作用处理**（fail-safe）——误判为只读会导致重放副作用 |
| 验收 | 两类崩溃演练均通过（见下） |

**崩溃演练实测**：

```text
① 写到一半中断
   第一回合写产物 → 第二回合后端崩溃 → 检查点留下进度
   工单侧：step_finished=0 / artifact_written=0（未误报完成）
   恢复分析 → resume → 续跑 → 登记产物 → 复检 → finish success
   不变量：artifact_written=1、step_finished=1（不重复登记）

② 副作用已发出但回执未知
   开一个 external_side_effect 动作 → 进程死亡（无 finish）
   恢复分析 → verify_side_effect_first（needs_human=True，拒绝自动继续）
   人工核对 → resolve_open_operation() 补 finish → 再分析不再阻断
```

---

### Phase 5 —— 隔离升级 · WebUI · 分发（**已完成**，2026-09-23）

| 项 | 内容 |
|---|---|
| **隔离能力层** | `isolation.py`：`probe_capabilities()` **实测**本机后端（bwrap / sandbox-exec / docker / podman），`select_sandbox()` 按结果选择 |
| 平台落地 | Linux → `bwrap`（文件系统 + 默认断网 + PID/IPC/UTS）；macOS → `sandbox-exec` Seatbelt profile；容器 → `docker`/`podman`（仅挂工作区 + `--network none`） |
| **Windows** | **未实现内核级隔离**（Job Object 只限资源不限文件/网络；AppContainer 需 Win32 组包）→ **如实报告「应用层限制，非内核级沙箱」** |
| 三条铁律 | ①能力靠探测不靠假设 ②没落地不许宣称沙箱 ③**隔离包装失败时拒绝执行，不降级执行** |
| 接入方式 | `--isolation auto|none|bwrap|docker|podman`；`doctor` 打印能力与诚实标注；执行结果 meta 带 `isolation` / `real_isolation` |
| **WebUI** | `webui.py` + `web_assets/`：唯一监听 `127.0.0.1`（无 `--host`）；`WebApprover` 是审批协议的第 4 个实现，core 不改 |
| **三条硬边界** | ①不做状态第二写入者（静态断言不 import 控制面）②不收路径/命令/shell（未知字段 400）③重启后不自动放行（挂起项只在内存） |
| **命名划线** | 上游 `/icode ui` 是宿主的工单浏览器；本仓叫 **`webui`** 而非 `ui`，避免混淆 |
| 安全细节 | 同源 Cookie（`SameSite=Strict`）、拒绝跨源 Origin、严格 JSON + 64KiB、无 CDN、无内联脚本、不用 `innerHTML` |
| 分发 | `console_scripts` 入口 `icode`；`package-data` 含 `web_assets/*`；`pipx` / `uv tool install` |

**实测**：

```text
隔离（本机 Windows）：[WARN] 应用层限制，非内核级沙箱 / 后端=none / 无可探测后端
WebUI 边界（真实 HTTP）：GET / →200（下发 Cookie）；无 Cookie 读 →403；带 argv 字段 →400；
                        跨源 Origin →403；未知 approval_id →409；错误 Content-Type →400
WebUI 闭环：网页放行 → 200，approver 返回 True
重启后挂起项：[]（不会自动放行）
分发：pip install --target → 包发现正常、web_assets 随包分发、bin/icode.exe 生成、
      从仓库外可执行、11 个子命令齐全
```

**顺带修**：`--skill-root` 原本只能写在子命令**之前**；现在通过 `parents` 让它在前后都能用
（用户和我自己都自然地写到了后面）。

**未验证项（如实记录）**：本沙箱禁止创建新 venv（`python -m venv` 返回 0 但目录不落盘），
因此 `pipx install` 的端到端未能在本环境验证；已用 `pip install --target` 覆盖到包发现、
资源分发与控制台脚本层面。

### Phase 6 —— 缺口收口（2026-09-23）

四个遗留缺口的处理结果：

| 缺口 | 状态 | 关键证据 |
|---|---|---|
| ① 推理门禁未满足 | ✅ **闭环** | L2 由本仓自实现的 `sequential` 承担；trace `result=success attempted=True 推演=5步`；**`plan` 步骤首次推进到 `plan_done`** |
| ② 完整 1→6 链路 | ⚠️ **部分**：编排器已建，`plan` 走通，`review` 阻塞 | 链路顺序由状态机派生；两个阻塞点已精确复现并定位（见下） |
| ③ Windows 内核级隔离 | ✅ **落地并诚实标注** | 新增 `WslSandbox`（真隔离，需显式指定）+ `WindowsJobLimits`（**部分强制：仅资源**，明说不是沙箱） |
| ④ pipx 端到端未验证 | ✅ **用 wheel 验证** | 构建 → 核验 entry_points/资源/RECORD → 安装 → 仓库外执行 → **12 子命令齐全** |

**诚实说明（缺口②）**：本轮**没有**让 1→6 全链路跑完。已经做到的是：
编排器可用、链路顺序不写死、`plan` 全绿并推进状态；`review` 及之后仍未通过。
阻塞点两条，均可复现：

1. **模型不落盘**：`review` 里模型倾向在文本里回答，不调用 `write_file` 写 `02_review.md`
   与 `review_round_1.json`。已加**有界补救回合**（列出缺失产物的绝对路径并要求立即写），
   本轮仍未救回，需要继续调优提示或改成"文本产出 → 本仓落盘"的显式通道。
2. **`operation_finish` 失败留下未闭合动作**：导致同名副作用再次 start 被判
   `ambiguous_side_effect`，运行时如实拒绝执行。已改为**显式暴露**（`inv.note` /
   `tool_result.meta.operation_finish_failed` / `operation_finish_failed` 事件），
   不再静默；但"为什么 finish 会失败"仍需下一轮定位。

**Phase 6 实测中修掉的真 bug**：

| # | 问题 | 修法 |
|---|---|---|
| 1 | **tool_call 与 tool 消息不配对**：单回合超上限时直接丢弃多余调用，assistant 仍列着它们 → OpenAI 兼容端点 **HTTP 400 invalid params**（整条链路曾因此走不动） | 未执行的调用也回一条**"未执行"**配对结果；单回合上限 4→8。加回归测试锁死一一对应 |
| 2 | 推演 `max_tokens=300` 对推理模型太小：思考吃满 token，剥离 `<think>` 后正文为空，5 步里 4 步空转 | 提到 1200；空响应立即停止并如实记录（不烧完额度） |
| 3 | `extra_instructions` 里写裸文件名（`01_plan.md`）与"必须写绝对路径"冲突，模型把产物写到工作区根目录 | 步骤说明**只描述内容、不写裸文件名**；提示词末尾再次钉住绝对路径并禁止写到工作区根目录 |
| 4 | 补救回合新建 `OperationRecorder` 导致 occurrence 计数重启、request 键重复 → 副作用歧义 | 回执器改为**整步共用** |
| 5 | WSL 只因 `wsl.exe` 存在就被自动选中（本机被安全策略拦截，命令全失败） | **存在 ≠ 可用**：WSL 不进自动选择列表，仅显式指定才用；`doctor` 区分"有可执行文件"与"可用" |
| 6 | `_ensure_gate_metadata` 用了 `json` 但 runner 未 import → `NameError` 中断整条链路 | 补 `import json` |

> 教训：本轮有**两次**用 `str.replace` 打补丁**静默未生效**（`run_contract_step` 的签名与 `sandbox` 参数），
> 之后改成"改完立刻 grep 核对"，才没有继续带着错往下跑。

### R2 —— 跨平台隔离策略（实施中）

R2.0 已发布版本化 policy schema、冲突规则与 contract vectors/score。
R2.1 已实现每工单 Git worktree 或非 Git 清单快照、跨进程租约、受保护路径策略，并接入自主运行生命周期。
Linux 本地回归验证了同工单两进程互斥、worker 退出后释放租约、原始 Git 工作树内容与状态不变、非 Git 快照清单和受保护路径合同。[三平台 CI 验收](https://github.com/ayukyo/icode/actions/runs/35880420396) 的 Linux、macOS、Windows 工作区专项、Python 3.11/3.12 全量测试与仓库展示检查均通过。
这些工作区边界和策略合同**不等于操作系统强制隔离**：模型执行尚未被原生内核机制限制。
R2.2 已合入 main 持续验证 Linux/macOS 原生后端。CI [#157](https://github.com/ayukyo/icode/actions/runs/36161303803) 的六个 Linux/macOS 原生探针 runner 全部通过；此前 #156 的 macos-latest policy-command-broker 失败未在 #157 重现，具体差异未知。仍需按最终十项合同核对资源限制与平台得分，不能只用原生探针矩阵宣称阶段结束。macOS 的进程组清理按用户批准的 Codex 式边界验收，主动脱组后代不承诺零残留。

R2.2 十项合同评分已接线（2026-09-26）：新增 `src/icode/conformance_evidence.py`，把真实探针证据（`probe_native_sandbox` 的逐项检查、macOS 同组清理、独立回收/资源/回执证据）映射到十项能力并评分；`capability_report()`（`icode doctor`）与 `scripts/run_native_probe_ci.py` 现在输出逐项证据来源与 `passed/total/critical_passed/ready`。评分是**保守**的：没有直接证据的能力一律记 False，因此 doctor 单靠最小探针不会误报 ready。这不等于平台验收闭合——完整十项仍需在干净 CI/VM 上跑全矩阵并核对资源限制与统一违规回执。

R2.3 的 AppContainer + Job Object 路线已降为诊断实验，不再作为产品执行后端。CI #158 的 Windows x64/ARM64 综合步骤仍失败；独立 disposable staged-Python 子项、临时 ACL 精确恢复与 loopback 未连接断言通过，但不能代表任意工具链闭包或生产接线。原 Python 子进程退出 `0xC0000135`、`LOCALAPPDATA` profile marker 缺失且综合步骤的具体失败断言不可读。结合开放式研发工具兼容性，R2.3 恢复原批准的一次 UAC native helper、专用 sandbox 身份、受限 token、ACL、WFP 与 Job 路线。手动 CI [#171](https://github.com/ayukyo/icode/actions/runs/36186027245) 的 Windows Server 2025 x64/ARM64 有效账户控制、缺失账户与错误密码 fail-closed 均通过；这是凭据/进程创建前置可行性门，不是生产 runner。固定 runner IPC envelope、受信本机 named-pipe 基元与纯 Python 协议合同测试现已存在；当前推进认证后的双向消息与会话状态约束，CI [#406](https://github.com/ayukyo/icode/actions/runs/36705924194) 的旧表象为 x64/ARM64 服务端 ConnectNamedPipe 超时；#407 [x64](https://github.com/ayukyo/icode/actions/runs/36707249149/job/109860307652) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36707249149/job/109860307701) 的新回执都确认 hosted-runner 当前进程对 production Logon-SID pipe 的 CreateFileW 返回 `ERROR_ACCESS_DENIED (5)`。仅证明本 CI 令牌/ACL 组合当前不可连通，不能外推到专用 sandbox 身份或认定 DACL 是唯一根因。下一轮调用现有无数据、随机本机 pipe 的 default-DACL/TokenUser A/B 并留固定回执；生产 DACL 与 client access mask 不变，结果待 #408。生产 helper、UAC setup/恢复、runner 收发接线、ACL、WFP 与工作负载接线仍未实现；详细拆分及验收要求见 [Windows 后端路线复核](./nbl/plans/2026-09-25-r2-windows-appcontainer.md)。Windows 自动模式继续关闭。

R2.4 Git 已有 Linux-only 内部固定状态查询：每次调用重核 `WorkspaceManager` 的 `GitWorkspaceIdentity`，固定 Git 可执行文件和 status/porcelain v2 参数，在 Landlock 下将工作区与 Git 元数据只读、断网；clean/process filter、gitlink 和不支持的布局失败关闭。新的内部执行白名单将执行权再收窄到固定 Git 与 ELF loader，并以对象身份绑定；迟到 filter 配置由真实 Linux 负例证明不能启动 helper。Linux 本机 x86_64 干净 wheel 探针现也注入 hostile `GIT_CONFIG_*`、`GIT_DIR`、`GIT_WORK_TREE`、`GIT_INDEX_FILE` 环境并验证 broker 仍读取可信工作区；ARM64 等待新 CI。此 API 尚未接入 `ToolContext` 或模型工具，macOS/Windows 无等价后端，`git_broker_unavailable` 保持。R2.4 网络租约已有范围/HMAC authority、进程内连接登记/关闭、**可选 host-side** `NetworkLeaseExpiryMonitor` 和一次性 pending→connected promotion：pending 必须显式登记，升级在 authority 锁内重核 issue/expiry/revoke generation 并只允许一次；revoke/expiry 测试使用本机真实 pending loopback `connect_ex`、socketpair 唤醒和 owner 线程关闭，另有已连接待发布的屏障负例。它仍只是 authority 原语与测试 harness，没有生产 proxy lifecycle owner、worker/Agent 调用链、listener、relay、DNS-to-lease sockaddr 绑定或 OS 强制“只到代理”路由；测试也不证明另一线程能中断同步阻塞 `connect()`。Linux 本机 authority+monitor lease lifecycle runner 44 项全过、0 skip；macOS/Windows pending-backlog 复现可能按测试契约 skip，必须核对新 CI 的实际 skip 数；跨平台新 CI 待回收。网络默认仍 DENY。下一片接入经过 DNS/IP 校验的 numeric sockaddr、可信 CONNECT scope/relay，并补真实跨平台验收；Linux netns + 可信桥接与 macOS/Windows OS 级门禁仍独立阻断网络开放。R2.5 负责安装引导和发布矩阵。开发期线上只保留 main，不以合入主线代替阶段验收。
完整 R2 的验收门槛仍是 Linux、macOS、Windows 每个平台均达到 ≥9/10，且 8 项 critical 全部通过。

### 2026-09-25 UTC：CI #120 交叉平台回执

CI [#120](https://github.com/ayukyo/icode/actions/runs/36081977910) 中 R2.1 工作区三平台、Python 3.11/3.12 与 R2.2 Linux/macOS 原生探针矩阵均通过，官网工作流 [#55](https://github.com/ayukyo/icode/actions/runs/36081977987) 通过。Windows x64 与 ARM64 AppContainer 作业仍失败：两架构均见 Python `0xC0000135`；actual `LOCALAPPDATA` 键唯一，CMD 对显式注入的 API 路径 alias 比较为不相等，宿主 `stat=not_found`，路径位于 API profile 下方但不是 API `Temp`，profile marker 缺失。具体子目录尚未分类，不能推断与 Python 加载失败有因果关系。工作区、网络和 Job 子项的通过 notice 仍只是组件证据。故 R2.2 的当前原生探针矩阵通过但完整阶段门槛未闭合；R2.3、R2 全阶段与 `policy_contract_ready` 均未通过，自动模式继续关闭。

### 2026-09-25 UTC：CI #121 子目录分类回执

CI [#121](https://github.com/ayukyo/icode/actions/runs/36083440360) 的 Windows x64 与 ARM64 AppContainer 探针均失败；新增脱敏关系分类显示 actual `LOCALAPPDATA` 属于 API profile 下的多层子路径（`api_child_nested`），两架构 Python 仍以 `0xC0000135` 退出，profile marker 缺失。工作区/网络负例、Job 进程限制对照和后代清理的组件 notice 通过，不构成完整 Windows 隔离验收。下一轮只再识别首层是否为 `Temp`、`Local`、`LocalState` 或其他类别，不输出路径、不改 ACL；R2.3、完整 R2 和自动模式仍未通过。

### 2026-09-25 UTC：CI #122 Windows profile 路径复核

CI [#122](https://github.com/ayukyo/icode/actions/runs/36083962877) 的 Windows x64 与 ARM64 均将 actual `LOCALAPPDATA` 归为 `api_child_other_nested`；宿主 `stat=not_found`、profile marker 缺失、Python 仍退出 `0xC0000135`。其它平台矩阵通过。profile 子目录进一步猜测的收益有限，下一轮改为每个 Python 运行时文件直读探针完成时立即输出脱敏 notice，避免末尾断言失败掩盖逐项证据；仍不放宽 ACL 或输出路径。Windows R2.3、完整 R2 与自动模式继续关闭。

### 2026-09-25 UTC：CI #123 直读诊断缺口

CI [#123](https://github.com/ayukyo/icode/actions/runs/36085435118) 的 Windows x64 与 ARM64 综合探针继续失败；两架构 Python 3.11 均退出 `0xC0000135`、profile marker 缺失，通用 Python 3.11/3.12、R2.1 三平台与 R2.2 Linux/macOS 子项通过。新增逐文件直读 notice 未出现；代码复核发现 `runtime_files` 四样本断言先于 notice，尚不能判断运行时文件候选是否足够。下一轮先输出固定标签与候选数，再保留四样本门槛并输出逐项结果，不输出路径、不扩大 ACL。Windows SDK 将该状态码定义为 [`STATUS_DLL_NOT_FOUND`](https://github.com/microsoft/win32metadata/blob/1bfb76db1c360653bdcb56512af0fdf987aceab8/generation/WinSDK/RecompiledIdlHeaders/shared/ntstatus.h#L4921-L4927)，这提示先验证 loader 依赖闭包，但还不能定位具体 DLL 或访问拒绝；Python `sys.path`、`._pth`、`PYTHONHOME` 等模块搜索配置也不能直接解释 Windows loader 状态码。Windows R2.3、完整 R2 与自动模式继续关闭。

### 2026-09-25 UTC：CI #124 仍无直读回执

CI [#124](https://github.com/ayukyo/icode/actions/runs/36086599173) 的 Windows x64 与 ARM64 仍在 Python 3.11 AppContainer `0xC0000135` 失败，profile marker 缺失；其余平台、Python 通用测试和 R2.2 子项通过。即使把 inventory notice 前移到候选数断言前，综合作业 annotations 仍未显示该探针结果，公开摘要不足以判断方法是否执行或实际失败位置。下一轮在综合步骤前独立运行直读单测，诊断步骤失败允许继续，综合测试仍作为正式门槛重跑全部用例。Windows R2.3、完整 R2 与自动模式继续关闭。

### 2026-09-25 UTC：CI #125 双架构 Python runtime 直读结果

CI [#125 x64](https://github.com/ayukyo/icode/actions/runs/36087232240/job/107921726078) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36087232240/job/107921726100) 的独立直读步骤均执行完成，候选清单为 6 项、可用 5 项。两架构 `system32_control` 均为 `read_ok`；`python_executable`、`python_shared_library`、`stdlib_pathlib`、`stdlib_encodings` 均为 `access_denied`，复制探针退出 1 且清理为真。综合 AppContainer Python 仍退出 `0xC0000135`，profile marker 缺失，因此 #125 整轮失败；其余平台阶段矩阵通过。该证据优先支持验证 Python runtime root 的读取边界，但不能确认具体 DLL、证明映射失败由 ACL 单独导致，也不是 Windows 文件/网络隔离验收。生产 ACL 未改；下一步仅做经校验 runtime roots 的读取/执行授权 A/B，并测试写拒绝、精确 DACL 恢复、SID 残留、Python 启动及既有工作区/网络门禁。任一失败即保留 fail-closed；Windows 自动模式与完整 R2 仍未验收。

### 2026-09-25 UTC：CI-only Python runtime ACL 差分已实现，待双架构

新增的私有诊断开关只允许 GitHub-hosted Windows runner 上的当前解释器，并限定 `sys.prefix` / `sys.base_prefix`；生产执行器、自动模式和 `policy_contract_ready` 未接入。变更前逐对象快照 DACL/control/身份，最多扫描 100,000 项、30 秒；只给临时 Package SID 可继承的读取/执行权限。恢复后必须逐对象核对全树原状态及 SID 残留。UNC、卷根、Windows 系统目录、用户目录覆盖、工作区重叠、reparse/hardlink 和不可快照 DACL 均 fail-closed。原生 ACL 修改只在临时托管 runner 上尝试，双架构 CI 尚未执行；在全树精确恢复与 Python/工作区/网络门禁共同通过前，不能判定此方案可行，Windows R2.3、完整 R2、自动模式继续关闭。

### 2026-09-25 UTC：CI #127 runtime ACL 预检结果

Windows x64 与 ARM64 的独立只读 ACL 步骤均在快照阶段拒绝候选（[x64](https://github.com/ayukyo/icode/actions/runs/36090932965/job/107933023862)、[ARM64](https://github.com/ayukyo/icode/actions/runs/36090932965/job/107933023845)），回执只表明“运行时树含不支持的文件系统项”，候选未启动且 cleanup 为真；因此两端均未实际写入 runtime DACL。现有完整 AppContainer Python 仍以 `0xC0000135` 退出。接下来只补充路径脱敏的预检拒绝类别，不放宽过滤；Windows R2.3、完整 R2 与自动模式继续关闭。

### 2026-09-25 UTC：CI #128 将拒绝项收窄为 reparse point

Windows [x64](https://github.com/ayukyo/icode/actions/runs/36091394407/job/107934399982) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36091394407/job/107934399966) runtime-root 差分均由 reparse-point 检查拒绝，候选未启动、DACL 未变；Python 原有失败状态不变。tag 当时未知。当前代码只将 Windows `st_reparse_tag` 映射为路径脱敏类别，并以测试覆盖链接、mount point 与未知 tag。

CI [#129 x64](https://github.com/ayukyo/icode/actions/runs/36092603966/job/107937999811) 与 [ARM64](https://github.com/ayukyo/icode/actions/runs/36092603966/job/107937999747) 均确认 runtime-tree 拒绝类别为 `symbolic_link`；候选未启动、清理为真、没有 runtime DACL 变更。完整 AppContainer Python 仍为 `0xC0000135`，抽样 EXE、共享库、标准库读取仍被拒。此分类不包含链接路径或 target，不能推断其位于 runtime 根内。下一轮只做不跟随链接的路径脱敏词法关系计数；根外/未知仍拒绝，根内也不能单独作为放行证据。Windows R2.3、完整 R2 与自动模式仍关闭。

设计与实施依据：[R2 跨平台隔离设计](./nbl/specs/2026-09-23-r2-cross-platform-isolation-design.md) ·
[R2.0 policy contract 实施计划](./nbl/plans/2026-09-23-r2-policy-contract.md) ·
[R2.1 工作区与租约实施计划](./nbl/plans/2026-09-23-r2-workspace-lease.md) ·
[R2.2 Linux/macOS 原生隔离实施计划](./nbl/plans/2026-09-23-r2-native-isolation.md) ·
[R2.3 Windows AppContainer 实验计划](./nbl/plans/2026-09-25-r2-windows-appcontainer.md) ·
[R2.4 Git 状态代理门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md) ·
[R2.4 临时网络授权门禁](./nbl/plans/2026-09-24-r2-network-proxy-gate.md)

R2.3 Windows AppContainer 原生探针已覆盖 CI #91–#151：#91–#105 的启动差分曾返回 `CreateProcessW` 错误 203，#105 固定 whoami A/B 发现加入 profile `LOCALAPPDATA` 后可启动；其后原宿主 Python 一直退出 `0xC0000135`。#112 的 `process_limit=2/1` 同载荷正反对照双架构通过组件断言。#125 x64/ARM64 直读样本显示 System32 控制可读，而宿主 Python EXE、共享库、`pathlib.py`、`encodings` 均被拒绝读取。#131 清点 6,721 项、1 个词法根内 symbolic link；这不证明最终对象身份。#136/#137 把 staging ACL 差异定位为根对象 `SE_DACL_AUTO_INHERITED`；#138 先规范化该位后，双架构 staging ACL 全树精确恢复、candidate cleanup 与 staging 删除均通过，源 runtime 未修改。#149 双架构候选脚本退出 0、清理和各阶段 checkpoint 出现，但 workflow 在路径诊断 notice 前失败；已将回执缩短至固定别名与白名单三元组。CI [#150](https://github.com/ayukyo/icode/actions/runs/36128698379) 显示 staged candidate 通过，但两架构综合门禁各有 5 failures、4 errors；短/长路径规范化测试修正由 #151 验证。CI [#151](https://github.com/ayukyo/icode/actions/runs/36135745573) 确认 Python 与 Win32 API 对 `LOCALAPPDATA`、`TEMP`、`TMP` 的环境值一致，但三项 `stat` 均为 `not_found`、profile marker 仍 `path_not_found`；直接宿主 Python 仍 `0xC0000135`，staged candidate 退出 0。组合门禁两架构仍失败；loopback timeout 仅表示连接未建立，不能推断具体策略拦截。Linux ARM64 wheel 与 macOS Intel/macOS-latest 原生 job（含 policy-command-broker）通过。Windows 自动模式继续关闭，R2.3 与完整 R2 未完成。

### 2026-09-25 UTC：R2.3 下一诊断片（待 Windows 双架构 CI）

在既有 disposable staged Python 探针中新增 `LOCALAPPDATA`、`TEMP`、`TMP` 的 Python `os.environ` 与 Win32 `GetEnvironmentVariableW` 对照，并按脱敏类别检查路径状态；Actions notice 只含布尔值/固定类别，不含路径，纯测试另守 500 字符上限。该诊断没有修改 profile、ACL、环境变量或生产执行器。本机语法与摘要测试通过，但 Windows x64/ARM64 尚未跑这版；且即使结果一致，也不能将它等同 `0xC0000135` 根因。R2.3、完整 R2 与自动模式保持未完成/关闭。

### 2026-09-25 UTC：CI #156 复核与 staged runtime image-mapping 探针

- CI [#156](https://github.com/ayukyo/icode/actions/runs/36155715717) 的 Windows x64/ARM64 `Verify AppContainer workspace, network denial, ACL revocation, and Job composition` 步骤均失败；macOS `macos-latest` 的 `Verify policy command broker` 步骤也失败。当前可读到的公开 job 状态只标记步骤失败，Actions 日志接口返回 403，故不猜具体断言或跨任务归因。其它平台 job 的通过不能替代这两项门禁。
- **只读诊断实现（待新双架构 CI）：**在一次性 staged Python 诊断内，以 `CreateFileW(GENERIC_READ)` + `ReadFile(1 byte)` + `CreateFileMappingW(PAGE_READONLY | SEC_IMAGE_NO_EXECUTE)` + `MapViewOfFile(FILE_MAP_READ)`，分别观察原始/staged `python.exe` 与对应 `pythonXY.dll`；由普通宿主与 AppContainer 对同一文件集合做正向/差分对照。视图和句柄逐项释放；回执只含固定阶段标签、Win32 数值错误码与清理布尔值，状态用 `read|image` 短码表示，不含文件路径。该探针能区分文件数据读取和 PE image-section 映射，但不解析依赖闭包、不执行 DLL 初始化，也不等于完整进程 loader；不能仅凭结果指认 `0xC0000135` 根因。
- **取舍：**采纳单字节读取与 `SEC_IMAGE_NO_EXECUTE` 只读映像映射作为低风险分层诊断；参照 [Microsoft ReadFile](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-readfile)，暂缓 `LoadLibraryExW`，因为正常加载会运行 DLL 初始化代码，若需要应由可信、短命且独立于已加载 `pythonXY.dll` 的原生 helper 另行验证。只复用 Python `ctypes`/Win32 API 文档，不复制第三方代码、不增加安装依赖。Linux 本机 `tests.test_windows_appcontainer` 71 项通过、12 项因平台/CI条件跳过；新 Windows 原生探针仍待 x64/ARM64 CI，R2.3、完整 R2 和自动模式保持未完成/关闭。[Microsoft `CreateFileMappingW`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw) · [Microsoft `MapViewOfFile`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile) · [Microsoft `LoadLibraryExW`](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryexw)

Linux Git 元数据基座的本机 Landlock 负例覆盖可读/不可写/不可新建/不可执行、默认拒绝、符号链接拒绝和对象身份绑定。当前内部 status broker 已有固定 Git 命令、元数据只读根、状态解析、配置预检，以及固定 payload/loader 执行例外；该切片仍只在 Linux x86_64 本机及干净 wheel 有证据，尚无 ARM64 wheel 复验，也没有跨平台后端和模型调用端口。直接 Git 仍返回 `git_broker_unavailable`；详见[R2.4 Git 状态代理门禁](./nbl/plans/2026-09-24-r2-git-broker-gate.md)。

### 2026-09-25 UTC：CI #151 与 R2.4 网络生命周期内部切片

- [CI #151](https://github.com/ayukyo/icode/actions/runs/36135745573) 已验证 #150 后的 Windows 短/长路径规范化测试修正及 staged Python 双架构环境探针：Python/Win32 环境值一致，但 `LOCALAPPDATA`、`TEMP`、`TMP` 对 `stat` 均为 `not_found`，profile API 路径不匹配；宿主 Python `0xC0000135` 与 profile marker `path_not_found` 仍未解决。staged candidate/ACL 恢复和多个组件 notice 通过，Windows 组合门禁仍失败，不推断 `tempfile` 消费能力或失败根因。下一诊断仅检查 `tempfile.gettempdir()` 和临时文件创建，不改变环境、profile 或权限。
- R2.4 `NetworkLeaseAuthority` 已有内部活跃连接登记、正常释放、撤销/到期触发关闭回调、失败保持 revoking 并可重试的状态契约；20 项网络租约单测通过。它不运行代理、不持有/关闭真实 socket、不产生后台 sweep、不设置 Linux netns/桥接路由，亦不接入工具执行器。基于 Codex netns+TCP bridge/取消关闭、Gemini macOS 代理故障时终止进程组、Qwen 后端不可用不回宿主的固定源码对照，先采纳架构与失败关闭原则；实际网络开放仍需真实代理、DNS/IP pinning、到期/撤销隧道清理和三平台系统级负例。
- 本提交范围只有网络租约模型/测试及对照/阶段记录文档；不改变 R2 平台通过状态，Windows/macOS 网络继续 DENY，R2.3、R2.4、完整 R2 与自动模式均未验收。

### 2026-09-25 UTC：CI #147 ARM64 与 Windows 探针复核

CI [#147](https://github.com/ayukyo/icode/actions/runs/36122289071) 的 Ubuntu 22.04/24.04 ARM64 wheel jobs 均因 `/lib64` 可选根缺失、Python 使用 `resolve(strict=True)` 而失败；本轮改为只对固定可选系统可执行根非严格解析，并新增缺失路径测试，待新 ARM64 CI 验证。Windows x64/ARM64 的 staging ACL 恢复、清理与宿主 Python positive control 通过，但候选在网络检查 marker 前退出、失败 marker 为 `invalid_marker`，原因尚未定位。探针现报告“连接未建立”的可观测事实，不声称 WFP/策略拒绝；仍待新双架构 CI。R2.3、R2.4、完整 R2 与 `policy_contract_ready` 继续未完成，自动模式保持关闭。

### 2026-09-25 UTC：CI #148 双架构超时与 macOS job 复核

CI [#148](https://github.com/ayukyo/icode/actions/runs/36125785293) 中 Ubuntu 22.04/24.04 ARM64 wheel jobs 通过。Windows x64/ARM64 都在 AppContainer loopback connect 阶段得到 `TimeoutError`；stage ACL 恢复、清理、Python 导入/路径、运行时写拒绝与 source-read 检查通过，但 network-completed marker 未写，后续 workspace/child 尚未执行。当前代码将超时记为连接尝试未建立并保留白名单错误类，不推断 WFP/策略根因，待新 CI。macOS Intel 原生 job 通过，macos-latest 的 `Verify policy command broker` 失败且公开 annotation 只有退出码、日志 API 403，具体失败断言未知；本轮未改 broker，下一轮复核是否重现。R2.3、完整 R2 与自动模式仍未验收。

### 2026-09-25 UTC：CI #149 Windows 诊断回执长度复核

CI [#149 Windows x64](https://github.com/ayukyo/icode/actions/runs/36126829375/job/108044773273) 与 [Windows ARM64](https://github.com/ayukyo/icode/actions/runs/36126829375/job/108044773248) 中，staging ACL 恢复、清理、宿主 Python 正向控制及候选脚本均通过（candidate exit 0，所有脚本 checkpoint 出现），但工作流步骤仍失败，且路径诊断和边界 notice 未生成。输出顺序显示失败发生在路径 notice 序列化/长度断言附近；旧九项完整嵌套样本本机编码为 671 字符，而 `_workflow_json_notice()` 上限为 500，因此将此判断记录为有证据支持的定位，非可见原始断言。当前代码只压缩脱敏 notice，不改变权限或执行行为，待下一轮 CI 验证。Ubuntu 22.04/24.04 ARM64 wheel、macOS Intel/`macos-latest` 原生 job 与 `Verify policy command broker` 均通过；#148 macOS-latest 失败未重现。Windows 完整 AppContainer 组合门禁、R2.3 与自动模式仍关闭。

### 2026-09-25 UTC：CI #133/#134 staged runtime 与 ACL 回执

CI [#133](https://github.com/ayukyo/icode/actions/runs/36100147033) 的 x64/ARM64 staged Python 3.11.9 宿主正向控制均通过，但 AppContainer 候选退出 1、清理失败；#134 的拆分脱敏回执进一步确认 `runtime_acl_snapshot` 与只读授权成功、ACL root 为 disposable staging、源 runtime DACL 未改，且精确恢复失败。候选错误 `cleanup_failed`，故 workspace/network/child 结果无效，不能声称 Windows 文件/网络沙箱通过。其它 R2.1、Python 3.11/3.12、R2.2 Linux/macOS 和普通 Job 作业通过。

恢复失败原因仍待路径脱敏分类：下轮仅比较对象集合、首次 root/descendant DACL/元数据/SID 残留类别；不输出对象名、路径、ACL 内容或 SID，不改动源 runtime。无论诊断结果如何，在双架构精确恢复与完整组合负例通过前，Windows 自动模式、R2.3 和完整 R2 均保持关闭；若无法安全精确恢复，则停止该继承 ACL 路线并改评替代执行边界，不做宽松回退。

### 2026-09-25 UTC：CI #135/#136 runtime ACL 恢复元数据分类

CI [#135](https://github.com/ayukyo/icode/actions/runs/36102565397) 已确认 staging 检测后删除成功。CI [#136](https://github.com/ayukyo/icode/actions/runs/36103288445) x64 与 ARM64 均确认恢复后根对象只有 security descriptor `control` 字段不匹配：DACL bytes 未变、revision/present/defaulted/file identity 均未变、无 Package SID 残留；ACL 授权仅作用于 staging，源 runtime 未碰。候选仍 `cleanup_failed`，Python 与 workspace/network/child 组合探针没有有效结果。Windows 自动模式及完整 R2 继续关闭。下一轮只透出无路径 `control_delta` 位掩码，确认具体控制位后再决定该 ACL 路线是否可安全恢复，不能用 staging 最终删除覆盖尚未通过的恢复门。

CI [#137](https://github.com/ayukyo/icode/actions/runs/36104010820) 双架构确认 `control_delta=1024`（`0x0400`），Microsoft 文档对应 `SE_DACL_AUTO_INHERITED`；DACL bytes/identity/其它 metadata 未变且没有 SID 残留。该发现解释了 SetNamedSecurityInfo DACL 恢复触发的系统继承规范化，但不等同通过。下一轮只在 disposable staging 中、Package SID 授权前重设原 DACL并验证仅出现该规范化位，再以此为 baseline 继续做全树精确恢复；其它变化仍 fail-closed，不动源 runtime、不开放自动模式。

CI [#138](https://github.com/ayukyo/icode/actions/runs/36105290309) x64/ARM64 均证明 staging 根规范化 `0x0400` 后，Package SID 临时 ACL 全树精确恢复 (`acl_restore_verified=true`)、候选清理及 staging 删除通过、源 runtime 未改。候选 Python 仍退出 1、结果 marker 缺失；runtime/workspace/network/child 尚无有效回执，Windows 自动模式与完整 R2 保持关闭。下一轮增加脚本启动、导入、路径及负例阶段检查点，只公开布尔值和白名单异常类别。

CI [#105 x64](https://github.com/ayukyo/icode/actions/runs/36059960206/job/107836254760) 与 [#105 ARM64](https://github.com/ayukyo/icode/actions/runs/36059960206/job/107836255639) 的固定 whoami 同-profile A/B 均显示：省略容器 `LOCALAPPDATA` 时 `CreateProcessW` 返回 203，加入系统 API 返回的 profile 路径后成功且清理通过；但当时完整 AppContainer 流程的常规命令尚未带该变量，整组作业仍失败。当前代码已将容器专属路径接入常规 AppContainer 命令及撤权探针，并新增路径查询失败不启动、准确报告清理状态、临时 profile 数据目录删除/残留核验的测试；这条常规路径尚待新的 Windows x64/ARM64 CI。Windows AppContainer 与完整 R2 仍未验收，自动模式保持关闭。

CI [#106 x64](https://github.com/ayukyo/icode/actions/runs/36063691161/job/107848355215) 与 [#106 ARM64](https://github.com/ayukyo/icode/actions/runs/36063691161/job/107848355043) 已证明固定 whoami 的同-profile `LOCALAPPDATA` A/B 两边均可成功；但两项环境块断言拦截的是追加变量前的基础块，属于探针捕获层错误，现改为核对最终传给 `CreateProcessW` 的块。原生 Python 子进程退出码 `0xC0000135`（`STATUS_DLL_NOT_FOUND`），只能确认当前宿主 Python 运行时还不能在此 AppContainer 路径运行，具体依赖/访问原因尚未定位；工作区/网络组合探针仍返回 1，待补齐逐阶段成功标记后复验。上述结果没有证明 Windows 文件/网络门禁通过，R2.3、完整 R2 与自动模式仍未验收。

### 2026-09-24 UTC CI #112：进程上限组件通过，profile 与 Python 仍失败

CI [#112](https://github.com/ayukyo/icode/actions/runs/36074365589) 的 x64 与 ARM64 同载荷进程上限正反对照通过组件断言；cap=1 时没有子 marker、启动状态为 1816。两架构 `LOCALAPPDATA` 均已定义、API 路径宿主侧预先存在，但容器目录检查为假、写入类别 `path_not_found`、删除前 marker 缺失；Python 仍退出 `0xC0000135`。最新测试增加了只显示路径相等布尔值的对照，不输出路径；在 token SID、实际环境值与逐段访问问题查清前，不做目录创建或 ACL 放宽。R2.3/完整 R2 未通过，`policy_contract_ready=false`。

---

### 2026-09-25 UTC CI #113：profile 环境路径比较需原生复验

CI [#113](https://github.com/ayukyo/icode/actions/runs/36075689060) 的 x64 与 ARM64 普通检查及 `process_limit=2/1` 正反对照通过组件断言；两架构 AppContainer 集成仍失败，Python 继续退出 `0xC0000135`。profile notice 均显示 `LOCALAPPDATA` 已定义、API 路径宿主侧存在、容器内目录不可见、写入错误 `path_not_found`、删除前 marker 缺失。`cmd.exe set LOCALAPPDATA` 重定向文本比较为 false，但输出编码未固定，不能据此断言传入环境值不同。当前测试仅在环境块加入同值临时 alias，由受限进程内 CMD 比较并只发布 match/mismatch，不改生产环境或 ACL；Windows 自动模式和完整 R2 继续关闭。

### 2026-09-25 UTC CI #114：同块 alias 比较仍为 false

CI [#114](https://github.com/ayukyo/icode/actions/runs/36077520320) x64/ARM64 的 AppContainer 集成均失败；Job `process_limit=2/1` 对照仍通过组件断言，Python 仍退出 `0xC0000135`。容器内 `LOCALAPPDATA` 与 API 路径 alias 的 CMD 比较在两架构均为 false，但 alias 是否到达 CMD 尚未单独测量。新一轮只增加 alias-defined 状态和 Unicode `cmd /u` 输出，在宿主内比较实际值与 API 路径、notice 只报布尔值；不输出路径、不改变 ACL。R2.3、完整 R2 与 Windows 自动模式仍未验收。

### 2026-09-25 UTC CI #115：alias 存在但 profile 值不匹配

CI [#115](https://github.com/ayukyo/icode/actions/runs/36078212333) x64/ARM64 的 AppContainer 集成仍失败；`expected_localappdata_defined=true`，profile 路径不可见、marker 缺失，Python 退出 `0xC0000135`。Unicode `set` 输出的解析比较为 false，但当轮未记录子命令退出码或输出是否存在，不能据此判断值不匹配。CI [#116](https://github.com/ayukyo/icode/actions/runs/36078821652) x64 的 API/宿主路径比较也均为 false，但沿用相同的未验证采集文件，仍不能判断实际值。下一版记录 Unicode 子命令退出码和输出非空状态，仅对有效采集做内存布尔比较；不传入宿主路径、不授权访问。R2.3 和自动模式继续关闭。

### 2026-09-25 UTC CI #116：Unicode 采集有效性尚未核验

CI [#116](https://github.com/ayukyo/icode/actions/runs/36078821652) x64 的 profile 路径比较（API 值和宿主值）都报告 false，但 Unicode `set` 子命令的退出码、输出文件是否非空尚未单独采集，因此这两个结果不足以认定路径与两者都不同。下一版仅补这两个采集状态，并在有效时保留 API/宿主两个内存比较；不记录路径、不将宿主 profile 用于容器。Windows 自动模式与 R2.3 继续关闭。

### 2026-09-25 UTC CI #117：有效 Unicode 输出与 API/宿主值均不匹配

CI [#117](https://github.com/ayukyo/icode/actions/runs/36079222456) x64/ARM64 的 `cmd /u` 子命令均退出 0、输出文件非空，expected alias 已定义；当前解析出的 `LOCALAPPDATA` 不等于 API profile 路径，也不等于宿主变量。该结果将问题进一步收窄到受限子进程观察到的值/解析项，但仍未证明实际字符串含义（下一步核实 exact 键唯一性、actual/API 父子同级关系与文件系统对象身份）。profile 不可写、Python `0xC0000135`，Windows 自动模式与 R2.3 继续关闭；不扩大 ACL。

### 2026-09-25 UTC CI #118：删除前 actual path 仍不等于 API 对象

CI [#118](https://github.com/ayukyo/icode/actions/runs/36079893851) x64/ARM64 在 profile 删除前都确认 Unicode 输出有效、actual `LOCALAPPDATA` 键唯一，但宿主 `Path.is_dir` 与 `samefile(API profile path)` 均为 false；此采样尚未记录 `stat` 错误码，不能区分路径不存在与 host-side access-denied。下一版记录只读 `stat` 分类及 actual/API 的父子同级关系；不输出路径、不改变权限。Windows 自动模式与 R2.3 继续关闭。

### 2026-09-24 UTC CI #107：Windows cwd-relative 探针

CI [#107 x64](https://github.com/ayukyo/icode/actions/runs/36066941127) 的最终环境块与 profile `LOCALAPPDATA` A/B 检查通过；Python 仍退出 `0xC0000135`。CMD 批处理脚本未落下任何工作区标记，运行时文件诊断也未复制文件，故不能推断源文件 ACL。当前探针改用任务工作目录相对路径并增加 inline 写入对照；x64 不通过，ARM64 当时仍运行。R2.3 与自动模式继续关闭。

### 2026-09-24 UTC CI #108：工作区访问与子进程验收仍未闭环

CI [#108 x64](https://github.com/ayukyo/icode/actions/runs/36067827628/job/107861602120) 与 [#108 ARM64](https://github.com/ayukyo/icode/actions/runs/36067827628/job/107861602149) 的公开 notice 支持 profile 环境、cwd-relative workspace 及 loopback 子项通过，Python 两架构仍退出 `0xC0000135`。独立只读复核发现公开 Actions 注释不足以恢复精确失败断言：x64 没有 timeout notice，ARM64 只报告清理状态，日志 API 无法读取，因此不再把旧 notice 解读为具体失败根因。该提交 `eabc4df` 的源测试对 3 秒子进程仅留 3.2 秒观察窗，且没有同一 payload 的无 Job 正向对照；故 #108 不作为可靠的进程清理通过证据。#109 加入 release handshake 并有两架构子项通过 notice，但仍缺同 payload 正向对照和充分观察窗。#110 增加了 host 同载荷后代正对照及五秒清理观察窗，双架构组件 notice 通过；但 profile 写入与进程上限控制仍未验证，Python runtime 仍退出 `0xC0000135`。Windows R2.3 与自动模式继续关闭。

### 2026-09-24 UTC CI #109–#111：Windows 子项与真实失败分开记录

CI [#109 x64](https://github.com/ayukyo/icode/actions/runs/36069030309/job/107865391485) 与 [#109 ARM64](https://github.com/ayukyo/icode/actions/runs/36069030309/job/107865391466) 的 Windows 测试均有 cwd 工作区、loopback 连接失败、后代回收与 timeout 回收通过 notice，但研究复核指出进程探针只有 0.2 秒宽限。CI [#110](https://github.com/ayukyo/icode/actions/runs/36071476528) 以同 payload host 正对照和五秒后代观察窗重验后，双架构正常/timeout 后代清理 notice 通过；x64/ARM64 profile marker 均未写入，进程数对照尚不可靠。CI [#111](https://github.com/ayukyo/icode/actions/runs/36073278352) 的同步进程正对照父/子 marker 均出现，但临时目录诊断读取太晚、CMD 裸数字状态行未写出，导致两架构都在 `process_limit=1` 负例前失败。Python 仍退出 `0xC0000135`，AppContainer 和自动模式继续关闭；下一轮修正探针本身并重跑原生对照。

### R3 —— 自验证与有界修复（实施中）

R3 核心切片已合入 main（2026-09-26）：`src/icode/self_verify.py` 实现六类失败分类、`VerificationEvidence` / `evidence_fingerprint` 及有界修复决策；`runner.run_contract_step` 的补救回合接入证据门；`run_task` 将独立测试结果写入 `TaskReport` 和证据包；`src/icode/reviewer.py` 提供只读独立 Reviewer。当前受控 MiniMax-M3 已实际走通真实失败 → 有界修复 → 回归 → Reviewer 合法提交，最终 `TaskReport.ok=True`；不外推到任意项目成功率。

`VerificationEvidence` 使用真实 `base_commit_sha`、初始/受测工作区快照指纹与稳定受测 Git 原始 tree 投影 OID，并保留本轮 `diff_fingerprint` 与产物哈希；这些字段进入证据指纹/回执/Reviewer 输入，Reviewer 结束时重新核对受测工作区/tree。非 Git 靶场的 SHA 留空；无 Git 可执行文件时非 Git 工作区保持可用，检测到 Git 元数据却无法取 SHA 则失败关闭；基线 SHA 不冒充结果 commit。结果 commit `^{tree}` 只读比较和显式 task 验证回执已实现；`--receipt-out` 不覆盖既有目标、不创建父目录，回执可导入现有证据包。Linux 与 Windows 的受测 tree 原始投影已有生产实现及 Linux/Windows x64/ARM64 子门；Windows `run_task→tested tree→result commit` 已在 x64 workspace CI 验收，ARM64 集成用例尚未覆盖。实现纳入 ignored/未跟踪原始文件，不执行 attributes/filter；资源上限 250,000 项、128 层、256 MiB。Python SHA-1 OID 仅作兼容性内容标识，不能单独作为安全认证。计划与边界见 [R3 自验证与有界修复](./nbl/plans/2026-09-26-r3-self-verification.md)。

**R3 仍未验收的部分（如实标注）**：Linux Bubblewrap 与 macOS Seatbelt 普通工作流 Reviewer 命令、Docker/Podman 容器 Reviewer 的只读源码/拒读账本/拒绝写入负例已有本机或 [CI #443](https://github.com/ayukyo/icode/actions/runs/36808015508) 原生/容器证据；Linux 策略化 Bubblewrap Reviewer 已有受限 canary，但不能外推到其它 backend。Windows Reviewer OS 命令边界、WSL Reviewer 与 macOS/Windows/容器上的策略化 Reviewer 仍未开放。Linux 挂载测试针对静态路径，不证明敌意同用户进程可在路径校验与 bwrap 启动之间并发替换目录。短上下文终结器的强制触发真实 MiniMax 路径不证明自然触发率或任意任务成功率。task receipt 是可显式落盘并导入证据包的验证快照，不等于完整任务/会话事件回放，也不证明过程无未记录写入。专项范围包括 staged/unstaged、ignored/untracked、可执行位、符号链接、attributes/clean filter 与测试期间漂移；当前明确把 ignored 项纳入 raw projection、拒绝嵌套 `.git`/特殊文件/竞态，attributes 不执行，因此不可把 OID 解释为 Git clean-filter 结果。投影不证明 ACL、xattr、所有权、运行环境或进程执行轨迹；SHA-1 标识不作安全认证。Windows x64/ARM64 的 `run_task→tested tree→result commit` 集成用例已移入跨平台 workspace 精选矩阵并绑定 ICODE-SKILL Settings；新 SHA 的 x64/ARM64 结果待验。基线 SHA、受测 tree 锚点和 task 回执均不等于 R3 全部退出条件通过。

## 4. 为什么是这个顺序

| 顺序 | 依据 |
|---|---|
| Phase 1 先离线 | 控制面门禁极严（fail-closed），**不确定"我们的 Agent 能否满足契约"之前，接真模型就是烧钱** |
| 渐进披露必须在 Phase 1 | 步骤文档 67–146KB，是全行业最大；这是**成本生死线**，晚做等于先烧光预算 |
| **证据包提前到 Phase 3** | 它是**产品形态**而非收尾工作。越早做出可交付的证据包，越早能验证"过程可审计"这个定位是否真的成立；若等到最后才发现定位不成立，前面的投入全部报废 |
| 幂等键在 Phase 2 | 工业界已有成熟做法（确定性幂等键 + 写前意图），直接对齐，不必自研 |
| 内核沙箱放在 Phase 5 | 它是唯一能真正保证 P1 的手段，但三平台成本最高 → **先想清楚、分阶段落，但绝不能假装已经具备** |
| 韧性在证据包之后 | 证据包定义"什么算完成"，恢复机制定义"没完成怎么办"——**先定义完成，再定义恢复** |

---

## 5. 度量体系（质量指标与运营指标分开）

### 5.1 质量指标（只认三个，用于验收）

| 指标 | 定义 | 为什么 |
|---|---|---|
| **门禁通过率** | 首个 attempt 即 `finish success` 的步骤占比 | 反映 Agent 是否真在收集证据，而非反复碰运气 |
| **回归退出码** | E2E 靶场 `python -m unittest` 的退出码 | 客观、不可伪造、跨平台一致 |
| **证据完整度** | 每个产物是否都有 `artifact` 登记 + 短证据引用 | 这是我们与 sidecar 阵营的差异点，必须可度量 |

**防博弈**：门禁通过率**不可单独使用**——Agent 若知道指标，可能靠降低标准（如隐瞒漂移）刷分；必须与任务难度、证据完整度**配对观察**。

### 5.2 运营指标（只管预算，不进验收）

| 指标 | 用途 |
|---|---|
| 单工单 token / 费用 | P2 预算闸门（"超预算 3 倍即回退"）的**数据来源** |
| 任务耗时 / 尝试次数 | 观测回归，不用于横向比较 |

**区分逻辑**：token 与耗时会随任务规模、模型波动剧烈变化，**当质量指标会被优化成偷工减料或刷分**；但当运营指标是预算闸门的必需输入——**两者混用就是自相矛盾**。

---

## 6. 已确认的取舍（2026-09-23）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | Phase 1 范围 | **只做离线契约内核，不接真模型** —— 最低成本的风险探针 |
| 2 | 渐进披露 | **提为 Phase 1 硬要求** |
| 3 | 沙箱措辞边界 | Phase 1–2 只做**应用层限制**，对外**绝不宣称"安全沙箱"** |
| 4 | 确定性幂等键 | **引入**，对齐工业界成熟做法 |
| 5 | 证据包导出 | **从最后一期提前到 Phase 3**，视为产品形态 |
| 6 | 交付节奏 | **逐 Phase 验收**，每阶段留明确验收点 |

---

### 6.1 自检修正（2026-09-23 第二轮，换模型交叉审查）

| # | 发现 | 修正 |
|---|---|---|
| A1 | "零第三方依赖"与 Tool Loop / SSE / token 计数 / MCP 客户端冲突 | 改为 **core 零依赖 + 可选 extras**（`icode-agent[llm]` / `[web]`） |
| A2 | 成本被排除出度量，但 P2 预算闸门需要它 | 成本 = **运营指标**（管预算），不进质量验收（见 §5.2） |
| A3 | 依赖上游 main，但上游无契约稳定性承诺 | P1 验收加**上游 bump 冒烟测试**；依赖面文档化；澄清 gitlink 即 pin |
| B1 | 事件链不存正文 vs 审计需正文的张力 | 证据包 = **正文快照 + hash 对应表**，校验器验 hash 匹配 |
| B2 | 渐进披露可能漏读门禁规则 | 分两层：**门禁规则强制注入**，背景知识才懒加载 |
| B3 | E2E 会污染靶场基线 | 运行前复制到临时工作区，跑完丢弃 |
| B4 | CLI 人在环交互未定义 | P2 初定义**暂停/确认协议**并文档化 |
| C1 | 文档 5 份、代码 0 行，规划过剩 | **立即启动 Phase 1**，停止继续膨胀文档 |
| C2 | P2 首次让真模型跑 bash，而沙箱在 P5 | **P2 的 bash 默认禁用，仅白名单命令** |

---

## 7. 阶段交付工作流（每阶段一次 commit + push）

**约定**：每开发完一个阶段（Phase 验收全部通过），**立即自动 commit 并 push 一次**，不攒批。

### 7.1 提交前守护（三条全过才允许 commit / push）

| # | 守护 | 命令 / 规则 | 不过怎么办 |
|---|---|---|---|
| ① | **密钥扫描** | 全仓扫描 `sk-`、`Bearer `、`apiKey` 等形态与密钥文件名；命中即中止 | 排查来源，删除或移出仓外 |
| ② | **子模块完整性** | `git -C vendor/icode-skill status --porcelain` 必须为空，且 HEAD == 记录的 gitlink | 本仓**永不修改** `vendor/icode-skill/**`；修复一律在上游仓库独立进行 |
| ③ | **测试全绿** | `python -m unittest` 退出码 0 | 修完再交付 |

### 7.2 提交规范

- commit message：`phase<N>: <一句话成果>`（如 `phase1: offline contract handshake green`）
- push 目标：`origin main`
- 一阶段一提交，**禁止把多个 Phase 混在一个 commit 里**

### 7.3 `.gitignore` 责任边界

自动提交意味着**没有人工把关的机会**，所以 `.gitignore` 必须先行兜底，已覆盖：

| 类别 | 模式 |
|---|---|
| 密钥与本地配置 | `.env`、`*.key`、`*KEY*.txt`、`*密钥*.txt`、`icode.local.toml` 等 |
| Agent 运行产物 | `.icode_output/`、`.ico_*/`、`.icontrol.lock` |
| 工作数据 | `.workbuddy/*`（**保留** `.workbuddy/skills/` 供项目技能共享） |
| Python 构建与缓存 | `__pycache__`、`*.egg-info`、`.venv`、`.pytest_cache`、`.coverage`、`htmlcov` |
| IDE / OS | `.idea`、`.vscode`、`.DS_Store`、`Thumbs.db` |
| 临时产物 | `*.tmp`、`.tmp/`、`*.log` |

---

## 8. 一句话总结

> 调研告诉我们**别做广度**。我们的开发决策只有一条主线：
> **把"证据与门禁"这一个维度做到无人能及，其余一切都可以晚做、少做、甚至不做。**
