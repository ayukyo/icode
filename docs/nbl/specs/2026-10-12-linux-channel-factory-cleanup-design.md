# Linux B1：channel 工厂已取得端点的失败收尾

## 当前基线与三问

S1c 已实际提交推送 main `d52ebcc011f4bb9a37627a38d8eb4af18f4f7d25`，四源码/测试冻结经不同 SOURCE 双审、root 新33/旧163及原完整 preflight 三门通过。它只撤销不透明构造失败后的消费资格，不授工厂内部清理信用；远端同 SHA CI 正在独立观察。

真实问题：seccomp 工厂初始化抛原 KI/SE，sender.close 抛 RuntimeError，会跳过 host 并覆盖原信号。作者/root 实际四有效assertionFAIL/0error/skip、均0.002s；两个真实 socket FD仍活。task 工厂有继续 host 与保留原信号的现有机制。调用链：两 channel 工厂→既有 broker 创建窗口与旧直接调用；成功返回端点仍由 caller owning。

## 推荐的有限方案

复用 task 工厂已有逐项 BaseException 清理与 `_select_cleanup_error`，令 seccomp 工厂也独立尝试 sender、host，不因一个关闭失败跳过另一个。初始化已收到 KI/SE 时保留原对象；普通初始化异常遇到清理中的 KI/SE 使用现有选择规则，不新增自定义 BaseException 排行。其余原普通错误转换及固定消息保持；seccomp 原先吞掉的普通关闭异常仍不替代原普通初始化错误，但必须完成剩余清理。

两个工厂均在某个 socket.close 抛 BaseException 后调用 `socket.socket.detach(endpoint)` 解除对象的自动 FD owning，不能调用可能覆写的 detach。detach 不关闭 FD、不是 cleanup confirmation，返回的未知数字 FD不得重试。即使 close 已实际关闭后再报错，也不能因已复用的 FD 数字误关新资源。detach 自身异常也独立参加原首信号保护，不能跳过另一个端点或冒称解除 owning 成功。

此防御不意味着标准 CPython 底层 close 的 OSError 必然留下自动 owning：固定v3.11.15的C实现先使sock_fd无效再系统close，通常已经disarm。额外detach针对真正关闭前的Python中断/替换故障；已无效对象的detach不供应释放确认。所有负控必须分别记录before-close与after-close，不能混为标准内核关闭行为。

推荐局部修复而非通用资源管理框架。两个工厂签名不变、不新增 callback/结果协议/公开错误字段，正常 tuple、socket flags、caller所有权和旧 None 调用形状不变。创建未返回仍由 S1c construction_failed 门永久结束消费；不把这一事实升级为内部回收确认。

## 明确不处理

只处理两个工厂已经取得的端点；socketpair 自身未正常返回时无法由外层追回的内部对象、scope临时FD、monitor parser/start/listener以及receiver opaque selector仍是 B 独立债务。不复制第三方代码，不加依赖、权限、服务、native更改。不改变 deadline、配额、CP/runner/ToolContext或 readiness，不授 R2/R3 整体验收。

## 测试与执行

不同测试作者先新增 `tests/test_linux_channel_factory_cleanup.py`，正式实际 RED后不同源码作者才修复。真实 socket/FD 前置必需；mock 仅初始化、close及detach故障边界。覆盖：seccomp两端点独立继续、原KI/SE对象、清理KI/SE、两工厂未知close后对象解除 owning而真实FD仍活、各端点只一次尝试、close实际完成后报错且原数字复用仍活、普通创建失败/成功返回及nonLinux固定拒绝、detach失败时剩余端点继续且原信号保留。测试自行释放只为卫生，不算生产清理。

精确允许既有 `tests/test_linux_prepared_broker.py` 的 `test_construction_seccomp_real_unreturned_socket_target` 配对调整：创建取得host时保存原真实FD，不在工厂失败后依靠对象fileno反取；原留存、close一次、attachment faulted/下一borrow拒绝断言不变。测试finally先用基类detach解除host的测试owning，再仅释放保存且由before-close注入保证仍活的host FD；sender仍基类对象close。此为真实FD观察与卫生适配，不授detach释放信用。配对调整先在旧SOURCE下独立GREEN；新的对象已解除owning目标放新测试中，仍必须实际RED先于SOURCE修复。

复用broker既有消费失效测试，确认无签名/kwargs破坏；root新目标、原新33与旧163，fresh独立SOURCE SPEC→不同QUALITY，原完整 preflight、最终文档两轮原scanner及secret/submodule单门后才提交推送main。当前 S1c 同 SHA 三工作流必须收齐终态再下一push，避免取消未取得证据的工作流。

精确七路径：`src/icode/linux_task_resource.py`、`src/icode/linux_seccomp_notify.py`、新测试、上述S1c测试的唯一配对方法、本 DESIGN、配套 B1 PLAN、`docs/agent-landscape-live.md`。broker、S1c测试其余方法、vendor、native、CI、母设计均只读；main-only，不新增分支/worktree。DESIGN 经独立 SPEC→不同QUALITY 后才实施。

## 研究取舍

B1 开始独立只读核 CPython 固定版本的 socket.close/detach/自动终结与 socketpair 包装。现阶段仅采用动作与确认分账、一次关闭和解除自动 owning机制；实际观察日期/源码锚/许可证与取舍随后记入持续对照。研究不能代替真实负控，也不把 detach 或异常传播当成资源回收成功。

实际独立观察窗口2026-10-12 05:18:57–05:19:51 UTC，固定CPython v3.11.15（PSF-2.0）：Lib/socket.py 495–513的Python包装、650–660的socketpair包装；Modules/socketmodule.c 3179–3201 close、3210–3214 detach、5067–5097自动终结、6175–6192 socketpair收尾均实际GET并按raw核锚。未刷新HEAD/二十名单，无复制/依赖/权限新增。采纳已取得对象解除拥有和动作/确认分账，暂缓opaque内部构造，不适配GC/fileno==-1/返回整数授OS回收。
