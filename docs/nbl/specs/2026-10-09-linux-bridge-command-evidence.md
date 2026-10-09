# Linux 工程桥接：命令层实际观察

观察日期：2026-10-09，结果回读03:45:35 UTC。这是 root 的 L1 运行记录，不是设计作者的执行结果，也不是完整工程连接或 R2/R3 准入证明。

基线 main `8d53670192e3e2cbfebaa0300d697fb3036308be`，vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d`。运行前后生产源码未修改；仅另有文档收尾变更。环境为 UID1000、Linux6.8.0-138-generic x86_64、systemd249、cgroupv2；本轮没有修改服务、权限或调用sudo。compiler实际为Ubuntu GCC11.4.0，原测试串行编译单一helper，没有并行构建。

## 实际命令与结果

使用此前绑定的 lexical venv Python3.11.15，不将它resolve成另一解释器；保留既有验证环境，设置PYTHONDONTWRITEBYTECODE=1、GOMAXPROCS=1、GOFLAGS=-p=1、CMAKE_BUILD_PARALLEL_LEVEL=1。实际命令的解释器前缀为 `/tmp/icode-packaged-skill-acceptance-fqxSO0bh/venv/bin/python -B`，附加参数：

```bash
-m unittest tests.test_linux_product_task_quota.TestLinuxProductTaskQuota tests.test_linux_violation_receipt.TestLinuxViolationReceipt -v
```

实际exit0，40方法全部PASS，0 FAIL/ERROR/skip，13.129s：quota class25方法，violation class15方法。root完整读取这两个被运行class及其初始化/共享fixture、保存并逐项核40条actual `... ok`与最终summary。该集合包含实际原生正控、观察包装、应用编排和故障注入负控，不能称40个独立纯原生正控。

| 观察层 | 实际覆盖 | 信用边界 |
| --- | --- | --- |
| 原生quota正控 | cap1 fork/pthread EAGAIN、payload计数和supervisor分离、cap2 setsid后不能第三task、双scope cap1/2独立、正常/timeout/outputlimit收束、host SIGKILL后本次scope与late marker检查 | 仅本机当前命令层；host-death测试允许已死zombie状态，不声称已被全局init回收 |
| 原生拒绝/允许正控 | AF_INET USER_NOTIF、两个拒绝汇总、AF_UNIX成功、普通exit13/Permission denied输出没有OS回执、Landlock越界写不误记seccomp回执 | 仅已覆盖类别；不由文本推断OS拒绝，正常finished的payload_started仍None |
| 应用连接 | 实际registry→AgentLoop事件→CLI固定提示，backend为FakeBackend；CLI构造使用明确double | 只给协议/展示连接，不授真实模型语义审查或自然成功率 |
| 注入故障及防误用 | 缺bus/tool/cap、manager/ack/observer/receiver异常、close/interrupt、owned collision、过期/未知清理拒绝、marker不出现 | 按测试原有fault injection单列；不将注入结果冒称独立现场故障或全部零副作用 |

scope观察包装调用原configured并检查owned路径、LoadState=not-found、ControlGroup为空及launcher回收；没有枚举或停止他人unit。collision负例仅创建和回收明确owned fixture。manager bus存在检查不等于委托成功，实际正控已运行且没有将manager配置失败降为skip。

## 来源与证据局限

两个class在自有临时目录实际编译helper、生成SHA256 manifest，再由生产LandlockSandbox消费；这些绑定断言是本次通过路径的一部分。临时helper随原class生命周期清理，**root没有另行保留本次binary/manifest摘要或完整原始resource回执**。因此这份记录不是独立可重放binary来源清单，也不能冒称installed wheel验收。保存的是完整unittest输出和决定性断言结果，不是native C全文安全审计。

| 当前文件 | 完整SHA256 |
| --- | --- |
| `native/linux/icode_landlock.c` | `0700aa0a9fb8f18d60d1fe2f8320d8a1a03d4c0be9e189d10922fc2ada0a1ea3` |
| `tests/test_linux_product_task_quota.py` | `b04d5996799c66bcc86709cc1e201fc0718d214a1af01ce34d758e70b1db9418` |
| `tests/test_linux_violation_receipt.py` | `02821aa85001dba014d7966114173b405c9bf5b187e0632e665f020b2ae5bda3` |
| `src/icode/execution_broker.py` | `ee1b60b5c922a72de23234069d83e603287b66f3f6bed70323944d1663aab6f3` |
| `src/icode/linux_task_scope.py` | `6ce8cc433395a2110ba636d7b6eae0af2a6614bcea62b23687e577432493f6f9` |
| `src/icode/linux_task_resource.py` | `2c7158a6b3d5ef67d42578ebe675a12aeb97a1896e3790c9bbdca22d42cf6217` |
| `src/icode/linux_seccomp_notify.py` | `740eaca978f67946a2cd6e7fa05e78b6694e06bf425fa8340919022132ade8dd` |

## 未完成门与结论

分离Git布局的可信session state/tree接线仍需独立生产修复；本次没有执行L2a/L2b完整CP、fresh Reviewer、工程receipt、partial pack与独立verify.py往返，也没有跑installed层或Native自动模式正控。已有真实命令层成功不解除policy_contract_ready=False。macOS quota、Windows工作区/Reviewer/PE/首次UAC、真实模型endpoint/1→6/≥90%及R2/R3整体仍未通过。

结论：L1现有40方法在上述本机/源码窗口通过；没有将命令层结果升级为完整工程、installed、模型或原生总体准入。下一步按[桥接设计](2026-10-09-linux-engineering-bridge-design.md)的前置依赖推进。

【架构级自检报告】

- ✅ 语法/编译：两个原class实际单helper编译与40测试通过；本文不新增代码。
- ✅ 依赖/调用链：现有registry/manager/helper/通道及应用展示按实际层分别记录。
- ✅ 逻辑/边界：正控、注入、普通失败、OS拒绝与None exec状态分开。
- ✅ 异常处理：运行集合含超时、截断、setup/ack/close/interrupt、未知清理负控。
- ✅ 关联模块：仅新增运行记录，未修改源码或平台准入。
- ✅ 兼容安全：无新依赖、权限、服务、KEY或模型HTTP。
- ✅ 可运行性：仅上述本机40方法已验；完整工程与其它平台未验，不写100%。
