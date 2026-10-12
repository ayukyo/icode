# Linux prepared broker：未返回资源的构造失败边界

## 状态与依据

这是 S1c 的有限设计补充，尚未实施或完成验收。母设计 `2026-10-12-linux-prepared-step-scope-design.md` 保持不变。本补充不授真实 CP、安装包、自动模式或 R2/R3 整体信用。用户已授权常规选择按推荐推进；不新增依赖、权限、服务或系统扩展。

真实问题：资源工厂或构造器在返回对象前失败，外层变量仍为空，已有 finally 无法观察其内部清理结果。已有实现：S1b 消费状态与 helper owner 分账，以及 broker 对已返回资源的逐项清理。影响链：两个 observed public → 唯一 observed core → 工厂/构造器；旧 None owning 路径不新增通知或行为。

独立 QUALITY 与 root 均在当前 PLAN 的内存投影上复现两项真实资源反例：seccomp socketpair 初始化失败后 close 抛错且 socket FD 仍活；LinuxTaskScope 构造器的 trusted-tool 临时 FD close 抛错且 FD 仍活。root 两项均在 attached_bound≠faulted 断言失败，2 FAIL/0 errors/0 skips，0.147s。测试最后自行释放已保存的真实资源，不给 broker 清理信用；这是诊断，不是正式落盘 TDD RED。

## 方案选择

采用 A：有效借用成功后，资源创建未正常返回，记录独立 `construction_failed` 事实并终止该 attachment 的后续消费。收益是阻断当前可复现的不安全复用，成本是保守拒绝部分内部已清理但无法证明的构造失败。

暂缓 B：逐工厂修复未返回对象的所有权、清理结果传递与未知 close 后的安全处置。需要多个组件的新设计和真实 FD 故障矩阵，不能混入当前 broker 最小改动。B 是 R2/R3 整体验收前的明确债务，而不是被 A 解决的风险。

不适配：把所有普通业务异常猜成 cleanup unknown；无条件恢复失效附件；重试未知数字 FD；通过下一命令补救上一命令资源；把 faulted 当成已经清理。

## 状态与调用边界

`construction_failed` 与现有 `cleanup_unknown` 独立，前者只表示不透明创建操作未正常返回，不证明真实泄漏或 cleanup unknown。有效借用期间任一事实成立，归还前令消费状态 sticky faulted；helper owner 仍 active，由原创建者最后唯一关闭。

覆盖 observed core 中的 LinuxTaskScope、task resource channel、seccomp handoff channel、resource receiver、seccomp monitor 的创建调用。仅围绕实际创建操作记录 BaseException 后重抛；不包住整个业务 body，也不借此跳过已有独立清理。构造器内部普通 manager 查询失败也保守失效，因为外层没有取得对象；成功创建后的普通 wrapper/body 错误不因此失效，独立 cleanup unknown 仍按既有规则处理。

借用前 session/attempt/policy/类型检查拒绝不标记 faulted。未成功进入 borrow 的失败不供应 construction_failed 信用。旧 None owning 路径保持原异常、返回值、kwargs 与清理行为。

broker 实际收到的首个 KeyboardInterrupt/SystemExit 保留原对象；之后的清理错误不得覆盖它，所有独立已返回资源仍尽力收尾。不宣称修复工厂/构造器内部既有信号选择器：内部未返回前可能覆盖信号的路径无法由 A 追回，内部首信号与 unknown 安全处置并入 B 整体验收债务。消费失效通知不关闭共享 helper/session/lease，不改变 deadline、进程计数、native helper 或认证规则。

## 验收与实施顺序

先修订精确 PLAN 并独立 SPEC → 不同 QUALITY。保留现有 17-hunk 接线阶段及 manager-query 修复阶段作为可达中间状态；先在实际磁盘代码上证明对应有效 assertion RED。新增两项真实资源构造反例及普通构造失败、首信号、成功构造后普通 body 失败、借用前拒绝与旧 None 矩阵，然后由不同作者实施最小构造失败门。不得先写完整修复再删除门制造 RED。

新测试应验证失败后借用被拒绝、inflight 已归还、helper owner 未被冒记关闭，以及实际资源仍活的前置事实。测试自身释放仅供测试卫生；不得把该动作计为 broker cleanup_ok。

最终实际 SOURCE 双审、root 独立目标与回归、原完整 preflight、语法/调用链/逻辑边界/异常/关联/兼容/可运行七维检查后，才发布 main。阶段精确路径扩为五个：broker、新测试、S1c PLAN、本补充 DESIGN、持续竞品对照；其他路径禁止修改。

## 研究与剩余债务

复用本轮独立只读研究固定 Codex `27065a91ccbf5ba8532844be3777fcf83b77820d` 的 terminate/terminate_confirmed 分账及 OpenHands SDK `3934349da2db0433238621542173a00a8af7439c` 的默认 exit 行为，来源与观察时间见持续竞品对照；不是最新 HEAD 刷新。仅借鉴动作与确认分离机制，不复制代码，不增加许可证或依赖负担。

A 完成只证明消费资格 fail-closed。工厂内部潜在 FD 残留、析构重复关闭风险及其原生边界仍待 B 独立修复/验收，不允许整体验收删除此债务。另有 Linux 原生 timeout 间歇故障、S2 真实 CP 接线与 S3 installed 验收，均不由本片抵消。
