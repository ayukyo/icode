# Linux helper 启动对象绑定：只读研究

观察日期：2026-10-11。ICODE 源码基线 `2e8fe1c629e2724b91c5287095b3f9495b115122`，固定 ICODE-SKILL `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。本记录不是已批准设计、实现计划或运行证明；启动方案已另询问用户，答复前不修改执行行为。

## 三问结论

1. 真实问题：`verify_native_helper` 打开 helper 做摘要后关闭，包装器随后用路径启动。校验与执行不是同一持有对象，路径替换窗口仍存在。
2. 现有实现：已有 `PreparedCommand.pass_fds/cwd`、工作区根 FD、resource/violation 通道及原生 FD 白名单。可复用，不另造启动器或安装服务。
3. 调用链：修改不止 argv[0]。普通命令、Reviewer、资源限制、systemd scope 和 leased-connect 都涉及描述符透传与生命周期，必须同步验证，不能孤立修改校验器。

## 两种机制不是同一验收项

| 候选 | 能解决 | 不能证明 | 主要成本/风险 |
| --- | --- | --- | --- |
| A：持有原文件 FD，校验该 FD，经 `/proc/self/fd/N` 执行 | 校验后路径替换不改变启动对象 | 同 inode 后续改写被禁止、发布者身份可信、动态 loader/库可信 | 描述符 owner、启动前关闭/复用竞态、所有包装器透传 |
| B：复制到 sealed memfd，封印后摘要校验，经该 FD 执行 | 主 ELF 快照字节不可再写入/缩放，源路径和 inode 后续变化不改变快照 | 原路径全部 LSM 限制自动继承、动态 loader/库可信、发布者身份可信 | 有界内存/复制成本、新执行对象的安全身份、内核执行策略兼容 |

推荐 A 作为边界较小的首阶段，明确只授防路径替换信用；若用户选择 B，则必须接受下述新执行对象边界。不能为了较易通过而让 A 获得 B 的信用。

## 固定上游证据

- Codex 固定 `8c0f7011674145da7e10627769fb221c74fbf7a0`：[bundled_bwrap.rs](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/linux-sandbox/src/bundled_bwrap.rs#L65-L95)。持有 File、摘要后经其 FD 执行，属于 A，不是封印快照；预期摘要缺失或占位分支不能称为强制验证。Apache-2.0，借鉴机制，不复制源码。
- Linux v5.15 固定 `8bb7eca972ad531c9b149c0a51ab43a417385813`：[memfd UAPI](https://github.com/torvalds/linux/blob/8bb7eca972ad531c9b149c0a51ab43a417385813/include/uapi/linux/memfd.h)。有 CLOEXEC/ALLOW_SEALING，没有新 EXEC/NOEXEC_SEAL 位。UAPI 标记 GPL-2.0 WITH Linux-syscall-note；不复制内核实现。
- Linux v6.8 固定 `e8f897f4afef0031fe618a8e94127a0934896aba`：[memfd.c](https://github.com/torvalds/linux/blob/e8f897f4afef0031fe618a8e94127a0934896aba/mm/memfd.c)。支持新执行标志。Ubuntu 22/24 的实际内核可能有回移补丁，不能只靠发行版名称判能力。
- [内核 memfd_noexec 官方文档](https://docs.kernel.org/userspace-api/mfd_noexec.html)：设置 0 默认可执行，1 默认不可执行但允许显式 EXEC，2 禁止 executable memfd；祖先 namespace 的更严格设置也生效。文档明确警告 executable memfd 的 NoExec 绕过风险。
- [Linux man-pages：封印](https://www.man7.org/linux/man-pages/man2/F_GET_SEALS.2const.html)：WRITE 封印禁止写入及新的共享可写映射；FUTURE_WRITE 仍允许既有共享可写映射改内容，不能替代 WRITE。

以上为源码/官方文档证据，不是 ICODE 原生探针结果。研究代理独立只读核对，主代理另核源码调用链及官方来源。

## B 的必要安全边界

B 若获选，顺序必须是：有界复制 → WRITE/SHRINK/GROW/SEAL → GET_SEALS 确认 → 对封印对象重新计算摘要 → 执行该对象。只摘要源文件再复制不满足合同。

不得修改 sysctl、去掉封印、fchmod 绕过 NX，或在策略拒绝后无标志重试。旧内核兼容分支与策略拒绝必须严格区分，不能把任意 EINVAL/EACCES 当作允许降级。缺 `/proc` 不回退路径执行。

至少对已打开源 FD 检查原挂载 noexec，失败拒绝。该检查不是完整原路径执行授权：memfd 改变执行对象，AppArmor/其它 LSM 将按新对象判定，没有通用用户态原路径执行权限 dry-run。本候选不能承诺全部原路径限制继承。

## 当前调用链缺口

- `src/icode/native_helper.py`：当前 verifier 返回 bool，关闭摘要 FD；bundle 返回路径。
- `src/icode/isolation.py`：`PreparedCommand` 只有 argv/pass_fds/cwd，没有启动对象 owner；工作区/资源包装重建对象时必须保留未来 helper 元数据。
- `src/icode/linux_task_scope.py`：scope 重建 PreparedCommand，目前只保留上述三个字段。
- `src/icode/tools/base.py`：Reviewer 精确要求 pass_fds 只有工作区 FD。新增 helper FD 不能通过“允许任意额外 FD”解决，必须校验明确角色及 owner。
- `src/icode/execution_broker.py`：普通资源路径合并工作区和通道 FD；leased-connect 固定传一个控制 FD，不能丢失 helper 启动 FD。Popen 前失败、启动失败、超时/取消、正常退出均须关闭对应 owner。
- `src/icode/tools/builtin.py`：无 broker 的 subprocess.run 路径也要有生命周期合同。
- `native/linux/icode_landlock.c`：现有白名单只保留 violation/resource/workspace 三角色，其余继承 FD 关闭。启动 FD 不得加入 payload 保留白名单；仍须真实负控证明 payload 无法拿到它。

## 取舍与必需验收

采纳：明确对象 owner、精确角色白名单、校验与启动对象绑定、失败拒绝且无路径回退。复用现有准备命令和进程监督链，不增加 Python 包依赖或特权部署。

暂缓：用户未选定的启动机制；原路径 LSM 等价性；摘要发布者认证及动态依赖验证。它们不是本片完成后自动具备的能力。

不适配：只改 argv、提前关闭 FD、靠数字不变判对象、Reviewer 任意 FD 放行、封印失败后无封印启动，以及研究结果替代原生验收。

共同必需负控：路径替换后不启动 decoy；FD 提前关闭/数字复用拒绝；完整 scope/resource/Reviewer/broker 链透传；创建/包装/Popen 异常及取消无泄漏；payload 不继承启动 FD。A 额外明确同 inode 改写不授信用；B 额外验证 write/truncate/shared writable mmap 被封印拒绝、复制过程中产生不匹配快照时封印后摘要校验拒绝、封印后源变异不影响已校验快照，以及 noexec/memfd 禁止/无 proc/封印失败均拒绝且无回退。不能声称捕获所有源变异。Ubuntu 22/24 × x64/ARM64 分别原生通过才能授相应平台信用。

成本：A 为 FD 所有权和跨包装器接线；B 另加有界快照、封印与策略兼容。许可影响限于机制研究，无源码复制、新依赖或权限。收益分别对应表中有限范围，不提升 `policy_contract_ready` 或整体 R2/R3 状态。

【架构级自检报告】

- ✅ 语法/格式：纯 Markdown，未新增运行代码；新文件单独 no-index 格式检查无诊断（diff 返回 1 表示新文件存在，不是门禁失败）。
- ✅ 依赖/调用链：定位相关包装与启动入口，未改接口；当前控制面及执行绑定证据包 7 项回归通过、0 跳过。
- ✅ 逻辑/边界：区分路径替换与 inode 改写，两个候选不混用信用。
- ✅ 异常处理：记录必需负控与无回退原则；尚无新实现可声称异常全覆盖。
- ✅ 关联模块：标明 Reviewer、scope、resource、leased broker 与 native 清理关联。
- ✅ 兼容安全：不新增依赖/权限，不修改 sysctl，不降低 readiness。
- ✅ 可运行性：本轮只读研究，未执行候选；不报告候选或整体 100% 通过。

本地核验：governance、密钥扫描、子模块完整性、20 项观察排期均通过；排期通过不等于 20 项源码全刷新。研究文件是未获选的候选草稿，没有修改运行代码；文档发布不代表批准或实现候选，完整 preflight 的旧成功不能当作本草稿的新全仓测试。

独立只读复核：A/B、Codex 可选摘要、固定内核与 sysctl、许可及 LSM 边界与官方来源一致；指出不能承诺捕获所有复制期间源变异，已改为封印后摘要不匹配拒绝的可测合同。A 是有限首阶段，不是最终 same-bytes 目标完成。研究复核未重跑 root 的本地回归，不重复授运行信用。

随后本轮文档发布前新完整 preflight 已退出0、三道通过；四份关联文档一致性两轮无疑似项。只证明当前仓库门禁，不是候选启动机制运行证明。
