# Linux Reviewer 只读视图设计（待方案确认）

基线：main `532dae1`，观察日期2026-10-11。设计提案；namespace/遮罩与独立源码复制视图的选择已异步询问，尚未实施。

## 已确认缺口

产品 Reviewer 调用 `wrap_read_only_policy_excluding`；当前 Landlock 不提供该接口，资源 dispatch 也不能把只读策略交给普通读写 wrapper。旧 `wrap_read_only` 与安装包工作区 FD 测试不能替代完整 Reviewer：Landlock 授权是叠加，不能从已授权工作区减去内部工单账本目录。

`code` 与 `deepcheck` 阶段派生的 Reviewer 策略保留原步骤身份，不能照搬 Bubblewrap 的 `step == review` 限制。复用已有 Session owner、PreparedCommand、资源 scope、两条可信回执通道、ArtifactBroker 和 tighten_policy；不绕开配额或把普通命令当只读运行。

## 方案比较

推荐：随原 Python 包的 native helper，在已有 user/PID namespace 内建立 private mount namespace、只读工作区与账本遮罩。不依赖宿主 bwrap 或额外特权安装；内核不支持即拒绝。

替代：宿主构建独立只读源码副本，完整记录原工程身份、每个文件hash、允许清单、映射和Reviewer事件，资源链只授权该副本。实现与拷贝成本较高，必须证明审查的是最终候选tree，不能用随机副本绕开原工单/政策身份。

不采用：只读工具提示、application-level禁止写、放宽策略、把账本搬到外部后宣称内置排除已支持、用户级process限额冒充单任务限额。

## 内核前置实证与边界

本机 Ubuntu 已实际执行：

```bash
unshare --user --map-root-user --mount /bin/true
unshare --user --map-root-user --mount /bin/sh -ec 'mount --make-rprivate /
mount -t tmpfs -o size=64k,nosuid,nodev,noexec tmpfs /mnt
test "$(stat -f -c %T /mnt)" = tmpfs'
```

两次返回0；挂载只存在临时 private namespace，进程退出后消失，没有宿主挂载或文件修改。这只证明本机这些内核操作可用，不证明 helper、完整只读排除、其它发行版/架构或安装包可用。生产不得要求用户执行这些命令。

## namespace 路线的必要顺序

1. 宿主固定原workspace目录FD、dev/inode与规范路径；排除清单固定为相对路径，拒绝根、穿越、链接组件和不明重叠。源码清单拒绝异常硬链接/未批准子挂载，避免账本通过内容别名泄露。
2. user/PID namespace 的既有生命周期内新增 private mount namespace，必须成功 UID映射并设置 private propagation；既有 mapless 降级不足以挂载，失败须拒绝，不能继续无mask。
3. 以固定对象而非再次授权路径建立非递归bind工作区视图；排除目录覆盖为空只读、nosuid/nodev/noexec tmpfs，工作区设为只读。挂载目标同样固定对象并防race，不能先检查后按可替换路径mount。
4. 重新打开挂载后的根并核身份，chdir新view，关闭原rootFD/旧cwd路径。现有native提前 `fchdir(old FD)` 与 `/proc/self/fd/old FD` Landlock grant 必须改变，否则旧mount视图可绕过mask；Landlock只授权新视图。
5. 新PID namespace 的PID1建立private proc，或完整屏蔽宿主proc别名。实际测试 `/proc/<宿主PID>/root`、cwd、fd，不凭“不继承原FD”推断全部别名关闭。保留runtime必需接口须明确最小范围。
6. 完成挂载后清空payload能力，安装Landlock/seccomp；配额、父死亡监督、PID1清理和可信resource/violation通道保持原合同。pre-exec挂载失败必须产生可信失败回执，负载不得启动。

不能先以路径grant原inode再单独mask其中目录并假设Landlock自动减权。原始绝对路径、旧FD、硬链接、别的bind视图与宿主proc是同一个泄漏边界的不同入口，必须一起验证。

## 实际验收

- 正控：相对/绝对允许源码读取；同一候选tree/hash、原步骤及工单/run身份匹配。
- 负控：源码写/创建/删除/rename、执行与网络被拒绝；内部与外部账本、旧cwd/旧rootFD、宿主proc、软硬链接和子挂载别名不可读。
- 竞态：构造后替换根/FD/排除路径，可信原生接收端必须拒绝或始终绑定正确对象；新旧目录无未授权payload副作用。
- 生命周期：配额、timeout/output上限、通道中断、挂载故障、宿主死亡、payload脱组后的既有整树回收；resource configured与terminal、独立违规/清理回执都检查。
- 宿主不变：只读/mask不传播到宿主，退出可再次正常使用原工程；Session借用者不关闭owner，异常仍释放工单lease。
- 成品：源码x64实测、安装包x64/ARM64及平台差异明确，未知内核不静默降级。

专项通过后仍不自动提高 policy_contract_ready、其它平台或R2/R3总门；完整 Reviewer 应通过产品工程入口，而不止裸helper argv。

## 研究与自检

独立只读研究核 Codex `cc7ba33601286a751477832b01de7b6f8de0dd9c` 的 [bwrap](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/linux-sandbox/src/bwrap.rs)及 [FD身份](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/linux-sandbox/src/fd_mount.rs)，Apache-2.0。采纳内核视图隔离、固定对象、失败关闭；暂缓引入bwrap依赖/Rust实现；不适配只grant原FD而忽略mount视图变化。只借鉴机制，不复制源码。

独立调用链审查已识别现有namespace入口、PID1/配额fork、capdrop可复用，同时指出旧FD/cwd、宿主proc和硬链接风险，已全部纳入。此文及内核前置检查没有授完整Reviewer可运行性；实际实现、测试及用户方案确认仍缺失。
