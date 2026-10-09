# 外置控制面与隔离执行根绑定

日期：2026-10-09。状态：子仓库最小契约已验证并发布；主工程接入与真实 Linux 工程验收进行中，未授予 R2/R3 整体验收信用。

## 真实问题与授权

main 020acebf51b61179bf401181ac703cb3d71446b6，ICODE-SKILL 1693651c1bd7daad3272eb054f0f81d6f254d08d。Linux bridge 两个真实正控在 create 阶段拒绝 project_path seed；没有 dispatch。现有 create 从工单目录推导 project_path，active_checkout 又要求独立 Git 根。WorkspaceManager 的隔离代码根无 .git，且控制数据必须外置。root与独立作者均复核，没有合法既有绑定入口。

用户已明确允许新增最小受校验、事件化宿主绑定入口和测试，验收后推送子仓库 main，再更新本工程固定版本。此前三个Python校验器已完成，不重复修改。G2 inspection源范围、Windows Git管道、模型端点不在本授权内。

## 方案选择

采用专用 `bind-execution-root`：新建工单仍使用原 create；可信宿主在第一次隔离执行前绑定现有代码目录。project_path、out_dir、ticket_id 的索引身份不变。WorkspaceManager 每个ticket的checkout路径稳定，run变更不要求重绑；run/attempt身份继续由现有执行合同维护。

不采用普通metadata-update开放project_path：这会混淆存储与执行身份、允许业务字段改授权。不采用active_checkout伪装：无.git代码树不是现存Git拓扑合同承认的checkout。不自动迁移/重新绑定旧目录，目录替换应拒绝并保留证据，不静默修复身份。

## 跨层合同

| 边界 | 生产者 | 消费者 | 要求 |
|---|---|---|---|
| 宿主会话→CP | WorkspaceSession的实际workspace_root | 新专用命令 | 显式ticket、绝对目录；不从模型正文解析、不祖先发现Git |
| CP→持久化 | 锁内校验后绑定 | metadata与事件链 | 复用原事务；新字段execution_binding受保护；失败不能宣告成功 |
| CP→执行 | execution_workspace / trusted_execution_workspace | 所有源文件端口、inspection、action-policy | 统一选绑定根并重新核对象身份；旧无绑定工单完全保留旧逻辑 |
| CP→独立包 | metadata_updated绑定事件 | 离线pack验证 | 绑定与metadata一致；不要求离线机器存在原目录；不因此宣称Native |

问题分类为身份契约缺口（supported），不是Linux内核执行故障。修复owner为ICODE-SKILL和主仓库CP适配；inspection的独立Git语义仍unresolved。

## 最小接口与生命周期

`bind-execution-root --dir TICKET --ticket-id ID --execution-root ABS --request-id KEY`。request-id必需；只接受v3、可信事件链和匹配ticket。当前close_state、active_checkout或活动checkout_history存在则拒绝；任何未结step/operation/agent拒绝新绑定。已绑定不可替换；同请求/同对象只返回already_applied，不产生执行授权或重复事件。不同请求不得用旧绑定偷偷改根。

execution_binding版本1包含规范绝对path和路径对象身份。字段结构严格封闭；device/inode必须是真整数（不含bool），inode必须非零；对象必须目录。记录根及需要保护的祖先身份，拒绝任一路径段符号链接/Windows junction、缺失、非目录、身份漂移及路径解析不一致。绑定执行根与control workspace必须互不包含。不添加依赖/权限；不能取得合格身份的平台拒绝绑定，而非仅相信路径文本。

使用原metadata_updated事件，payload含固定专用绑定标记和set.execution_binding，append为空。普通create seed/metadata-update不能写该字段；统一metadata结构校验禁止绑定与活动checkout并存，覆盖metadata-update、reopen和其它写入口，不只补一个调用方。此结构校验不访问在线执行目录。事件语义确认只存在一次合法绑定，与当前metadata完全一致，且事件流可观察到的绑定时刻无未结执行、无关闭流程；不能用缺少专用标记的普通事件替代绑定。旧无绑定事件链保持兼容。绑定根失效只阻止在线执行，不能让trace/离线取证依赖已经消失的目录。

旧ticket_created/migration_applied没有保存完整起始checkout种子，离线不能重建这些未记录的历史。在线绑定在原锁内检查当时实际metadata拓扑；离线只核记录结构、绑定/metadata一致性及已记录执行生命周期，不宣称证明历史OS对象或原始checkout种子真实。哈希链也不是抵御可信宿主整体伪造的签名。此片不为了新增绑定改写旧birth或补造历史证明。

目录核验是宿主控制面的对象检查；不冒充持有整个执行期间的内核对象锁。代码树的父目录/控制面访问保护仍由WorkspaceManager、policy和原生隔离提供，实际消费前仍要原有session/Git身份检查。

## 主仓库接入

新增ControlPlane窄wrapper，使用原request命名与返回错误规则；Linux fixture先合法create再绑定，从metadata seed去掉project_path。绑定失败立即停止，dispatch为0。完整步骤fixture仍明确fixture_seed，不给模拟早期阶段信用；不得再通过legacy project_path伪装绑定。

绑定修复只解决CP代码根选择；inspection对外置Git元数据的处理不在此片修复。独立pack若需要新增绑定语义校验，同步最小实现并保留旧pack行为，不因复用事件名放任绑定被篡改。

## 验收

先RED再GREEN：真实CLI创建/绑定/投影/源端口消费；中文和空格路径；独立进程重放不新增事件；同key异根、错ticket、普通seed/update注入、缺失/文件/链接/junction、目录和祖先替换、控制目录重叠、活动step/operation/agent、close/checkout冲突、事务异常都拒绝且不改原身份。离线事件缺失/重复/伪造标记/metadata漂移负控；旧工单无绑定回归。

子仓库按原必要校验命令执行，不跳过现存门禁；作者自审后fresh SPEC与不同QUALITY。只有验收通过才推送main并核远端SHA，然后更新主仓库固定版本。主仓库CP适配与pack回归后恢复两例Linux真实正控；不把portable测试、编译或partial pack当R2/R3整体通过。

## 并行官方研究

独立只读研究窗口2026-10-09 08:30–08:31 UTC：Codex main2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4、Aider main5dc9490bb35f9729ef2c95d00a19ccd30c26339c，两官方HEAD核验，根Apache-2.0许可证全文读取（Codex LICENSE、Aider LICENSE.txt）；未审全依赖，不复制实现。阶段末09:17–09:18 UTC再次核HEAD与相关源码，版本及取舍不变；persist/flush写入任务确认不直接等于断电耐久性。

Codex [recorder.rs](https://github.com/openai/codex/blob/2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4/codex-rs/rollout/src/recorder.rs#L910) 实读910–1160、1740–1783、2201–2262：cwd/runtime_workspace_roots与codex_home/sessions分离，首SessionMeta及persist ACK维护记录身份。采纳分离存储与显式持久化确认；恢复路径筛选不是可信对象授权，不直接照搬。

Aider [repo.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repo.py#L86) 实读48–120：显式git_dname优先、拒绝零或多repo。采纳唯一明确目标；祖先Git发现不适配隔离代码树。自动跨宿主恢复/历史重绑暂缓。收益为消除存储根与执行根混淆，成本为一个窄接口、事件语义和真实负控。

## 设计审查

root自审已修订历史checkout证据边界，并核稳定ticket目录和现有事务/事件消费；三份相关文档连续两轮结构/链接检查0疑似项。独立只读SPEC `/root/execution_binding_design_review` 全文与关键实现核对，阻断问题0；未写文件、未运行测试。实现与实际验收仍未开始，不因设计审查通过授运行信用。

## 实施进展（设计审查之后）

子仓库新增一次性绑定入口、严格 schema、在线逐级对象身份复验及纯离线事件镜像。独立 SPEC 首轮发现绑定事件摘要字段不严格，已先 RED 再修复：新事件恰好四字段且摘要为规范 64 位小写十六进制字符串，后续合法摘要不能掩盖早先缺失/非法值。独立 SPEC 复核与不同 QUALITY 均无待修问题。

最终冻结新增模块 23 项经 root 20 轮串行复跑共 460P、零跳过；原五项控制面契约均通过，Python 修改 compileall -j1 通过。已发布子仓库 main `d935a5218ca2970bce8157814bfda1f03aa6c9c4` 并核远端，主工程 vendor 已精确更新。逐轮、环境差异与审查记录见[执行计划](../plans/2026-10-09-execution-root-binding.md)。

主工程 wrapper、独立验包及 fixture 接入通过独立 SPEC 和不同 QUALITY；临时 wheel / 独立 sdist 安装的18项测试通过，Linux两个实际 code/deepcheck 正控和三个 portable 方法通过。阶段20轮220P、DEFAULT614P均零跳过。首次全量2479项发现递归检出测试错误使用旧 HEAD 而非暂存 gitlink，已保留失败证据并最小修正测试输入；7项定点及其20轮140P通过，完整复验2479项、2420P/59skip/0F/E，j1编译和仓库守卫通过，母仓库正在发布收尾。真实完整步骤、跨平台原生、最终安装体验仍需各自验收，不把子仓库单片或 Linux partial pack 通过扩写为产品完成。
