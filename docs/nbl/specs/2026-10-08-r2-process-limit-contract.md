# R2 单命令进程上限合同（用户已确认）

确认日期：2026-10-08 Asia/Shanghai。用户选择“接受建议口径，继续实现”，解除资源计划 RL-0 的计数口径实施阻断，不改变验收分数或 macOS 例外。

每次 `run_command` 建立独立的 OS 配额边界。根 payload 计 1，全部后代计入；不同并发命令不得共享或相互消耗配额。任务外 broker、launcher、observer 不计入，必须实际位于边界外，不能通过事后扣减 helper 数伪造这一语义。

Linux 使用内核 task/TID 计数，线程也计入；Windows 使用 Job 活跃进程计数，线程不计入。这一差异必须在能力说明和策略回执中明示。macOS 没有合格的单任务限制机制时，启动前报告 unsupported、payload_started=false；不使用 UID 级 RLIMIT_NPROC 或进程组回收冒充配额。没有获得新增特权服务或额外安装步骤授权。

接线必须贯通 policy → ToolContext/Agent → broker → OS enforcer，复用已有 namespace/Job 清理，不另建无必要的清理系统。验收包括 cap=2 的根+一个后代正例、cap=1 的超限后代无 marker 负例、线程差异、并发命令独立计数、配置失败前没有 payload，以及正常/超时/取消/异常/主动脱组后代清理。须有实际 cgroup membership/pids.events 或 Job 配额证据；mock、未接线组件和环境 SKIP 不计分。

本确认不解除其他产品化门槛，也不开放自动模式。macOS 完整树清理仍是唯一已批准例外；资源限制和统一违规两项仍必须通过才能达到 9/10。
