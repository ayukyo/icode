# Linux prepared broker：已返回接收器的清理确认

## 真实问题与范围

这是 S1c 的第二项有限补充，不是整体完成声明。returned-receiver-I3 已由实际接收线程与真实文件描述符反例证明：收到禁止的 SCM_RIGHTS 时关闭异常被忽略；selector 的关闭异常被协议错误捕获。两种情况下 worker 已结束、receipt 为 incomplete，但 receiver.close() 返回 True，broker attachment 仍可继续借用。该对象已经返回，不能归入上一补充的未返回工厂 B 债务。

复用 receiver.close() → broker cleanup_unknown → attachment faulted 的现有链，不增加 callback、权限、依赖、服务、系统扩展或公开接口。线程停止与其自有资源清理确认分别记账。母设计及上项构造失败设计的其余边界不变。

## 推荐方案

增加不可恢复的接收器内部清理未知标记。每个原始 SCM_RIGHTS delivery 中完整整数 FD 独立尝试关闭一次；任一 BaseException 标为未知，继续其余独立 FD，不重试未知整数。这些 FD 永不被协议采用。使用已有 lock 保护事实读取与写入。

已成功返回的 selector 由接收线程显式 finally 关闭一次；关闭异常标为未知，协议错误仍按现有 _fail() 处理。selector 创建未正常返回单独保守标记未知，不声称已清理其内部未返回资源；该不透明构造安全处置仍是 B 债务。不能把任意 worker body 或协议异常都猜成清理未知。

close() 仍只负责停止线程，不关闭 caller 的 socket、process 或 scope。其 True 同时要求既有线程结束确认与自有资源无未知事实；worker 从未启动且无未知事实保持 True。线程终态不能冲掉未知标记。worker 内 BaseException 不扩展为 main-thread 信号传播承诺，broker 实际收到的首信号规则保持原样。

普通 malformed、timeout、EOF、incomplete 且已返回自有资源清理确认时，close() 仍为 True，不误标 attachment faulted。receipt schema 与错误分类不变；已有 broker 对 close=False 的通知在归还 borrow 前执行，不需要增加 broker 行为。

## 验收与发布路径

先独立设计 SPEC / 不同 QUALITY，再落盘新测试观察真实 assertion RED，然后最小源码修复。覆盖实际 worker / SCM_RIGHTS 与 selector 真实 FD 留存、attachment faulted、下一 borrow 拒绝、owner active 与 inflight 归还；多 FD 继续关闭且各一次；普通 malformed 的清理确认与可继续借用；selector 未返回保守拒绝。测试自行释放留存 FD 仅为卫生，不计生产清理信用。

新测试单独放在 tests/test_linux_resource_cleanup.py，不修改旧测试。根重新执行新目标、既有 S1c 26 项、receiver 回归和原 163 项；随后不同 SOURCE 双审、原完整 preflight、文档一致性、secret 与 submodule 门，才提交推送 main。

本补充明确取代上一补充的五路径发布上限，精确扩为八路径：src/icode/execution_broker.py、src/icode/linux_task_resource.py、tests/test_linux_prepared_broker.py、tests/test_linux_resource_cleanup.py、S1c PLAN、构造失败 DESIGN、本 DESIGN、docs/agent-landscape-live.md。其他源码、旧测试、vendor、native、CI 不变。根负责文档记录；测试与源码作者按顺序独立，不同时修改源码。

## 不供应的信用

不解决未返回工厂 B、Linux deadline 竞争、S2 真实 CP、S3 安装包或跨平台原生验收。不把 faulted 或 close=False 当成资源已清理；不复制第三方实现。研究复用既有动作/确认分账，并对 CPython selector 清理机制另做固定版本只读核对。
