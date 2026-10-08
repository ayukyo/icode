# R3 历史产物正文保存（候选独立片）

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。设计候选，未实现、未验收。对 ICODE-SKILL 进一步修改及推送已单独询问，尚未收到授权；不能用此前解释器/UTF-8 最小修复的授权代替。本工程其它已授权开发继续。

## 已确认的真实问题与复用

2026-10-08根代理读取固定169的`cmd_inspection`、`cmd_artifact`及本工程`ArtifactBroker.submit`、`evidence._snapshot_artifacts`和`pack_verify._verify_artifact_binding`：inspection逐次更新同一清单、登记不同sha；broker只原子替换，export对每条事件只复制当前正文。实际合同code通过工程/Reviewer/精确finish后，增量清单的历史正文仍缺失，pack自验失败。既有ticket snapshot仅状态/事件尾，不保存历史产物。

三问均确认：这是产品链问题，存在可复用的控制面锁/原子写/事件登记与有界export，影响producer→保存→export→内置/离仓verify。不能只在broker保存，否则CP自身的inspection写入仍遗漏；不能只改export，因为已被覆盖的旧正文无法重建。

## 候选最小边界（授权及设计审查前不实施）

- 控制面的inspection与artifact登记复用一个保存入口，在追加事件前保存本次实际原字节正文；按实际sha内容寻址，保持既有事件/metadata/request/回包schema及所有历史记录。不得由模型任意路径或自报sha提供保存权限。
- 在现有控制面锁内完成读取/摘要/大小事实一致核对与原子发布，使用no-follow普通文件和目录身份检查，拒链接/reparse、异常源变化、超限与陌生冲突；不能覆盖坏历史对象或把缺失旧正文伪造为当前正文。
- 保存的目录与正文只有宿主写，模型仍只能访问原合同的精确单文件端口。单文件、累计字节/对象数、单次读取和故障残留须明确有界；不用递归无限扫描或每次全量hash旧目录。具体限额/目录布局须冻结后TDD，不能把“内容寻址”当完整性认证。
- export先按事件确切sha选择并验证已保存正文，旧工单没有历史存储时保留当前正文确实匹配的兼容路径。旧sha无匹配正文继续拒绝，不能降低独立verifier或忽略历史mismatch。产物索引的source_path仍是真实原路径，snapshot仍为包内普通文件；不改包schema或共享离仓verifier。
- 故障发生在保存之后、事件追加之前可能留下未引用对象；明确保留/诊断，不因下次请求删除未知对象。保存失败不追加本次新事件，幂等冲突不覆盖已存在事实；KI/SystemExit及真正IO错误不能吞成成功。
- 历史正文保存不隐藏当前末版漂移：按每个真实source_path核对该路径最后登记版本的当前普通文件；缺失、链接/reparse、不可读、sha或size不一致均成为export problems，report.ok=false，不能退化成warning。正常历史版本从保存正文解析，不以它们与当前末版不同触发此门；归档完好不覆盖末版门的失败。inspection保存失败须保留上一份有效清单；现metadata+event事务恢复不包含artifact，不宣称三者已经原子提交。
- 旧工单已丢失的正文不能追溯恢复。历史存储不是sandbox、测试质量认证、模型语义审查或R2/R3 readiness。

## TDD与阶段验收

1. 真实CP prepare→read每phase→完成同一清单，旧hash与新hash不同；所有版本的真实原字节均能导出并由内置/离仓-I verify核对。另覆盖普通artifact同一路径的多次登记。
2. 不同event同digest、同request重放、不同request新版本，事件数量和原回包语义不变；输入冲突保持拒绝。修改当前正文不改变保存的已登记版本。
3. 保存对象缺失、坏内容、同尺寸篡改、命名sha不符、超限、链接/祖先替换、源变化与partial-write拒绝；不得从工作区、邻接sha或任意缓存回填。历史归档全部正确但末版当前正文缺失/链接/不可读/同尺寸篡改也须export失败，不能仅warning；正常已登记多版本仍通过。
4. 旧无存储工单的当前匹配正控、历史正文已丢失负控；不能将合法新保存路径当旧失败窗口已修复。
5. 实际注入保存/发布/fsync/事件追加异常与中断；无假success、无删除陌生对象、无盲重放副作用。已写事件和旧正文仍可验证。
6. 子仓先完整独立SPEC→不同QUALITY与自身门，验收后main提交推送；本工程更新固定gitlink再验真实默认增量链、合同接线、干净pip和独立验包、20轮、完整preflight及七维自检。两仓不混写、不用脏vendor通过守护。

一次提交最终清单的宿主alternate正控仅证明该支持路径，不能关闭默认逐次CP read的缺边。持续并行只读上游研究记录在竞品对照；机制可借鉴，不能替代这些实际验收。

只读对照沿固定OpenHands SDK `69e26889401fe69157fff536e6a69049e6644cb3`/1.53.0的[EventLog.append](https://github.com/OpenHands/software-agent-sdk/blob/69e26889401fe69157fff536e6a69049e6644cb3/openhands-sdk/openhands/sdk/conversation/event_store.py#L169)（MIT）及Codex `9b738582b13c2cdbeff54af0afd04c50c3e7ba09`的[rollout recorder](https://github.com/openai/codex/blob/9b738582b13c2cdbeff54af0afd04c50c3e7ba09/codex-rs/rollout/src/recorder.rs#L1785)（Apache-2.0），采纳当时结构化正文持久化及失败不推进的机制；不移植框架/分支缓存，不称它们保存任意工程文件历史或认证执行。固定源码观察不等于当日全项目复核或动态试跑；仅借机制，无源码复制、新运行依赖或许可成本。

**Execution Mode:** serial implementation after explicit upstream authority, independent read-only research/reviews
