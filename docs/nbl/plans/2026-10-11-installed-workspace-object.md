# 随包 Session 工作区对象验证（2026-10-11）

基线：main `9cb380932e8591d334e7a1cafd0f30a82ac7792b`，vendor `21566a5`。前置 Linux Session FD 阶段已提交推送并核对远端 main；它的完整 preflight 三道通过，17 项源码测试不等于安装包/ARM 的证据。本片验证实际 wheel。

## 缺口与实现

现有四 Linux wheel CI 已有真实资源、违规回执、网络租约与清理探针，但未给包装器传入 Session 工作区 FD。新增 `probe_installed_linux_workspace_object.py`，接入原 `run_native_wheel_ci.py` 的安装后阶段；不修改 workflow 权限、评分、环境跳过或产品准入。

入口用 `-I`、包外 cwd、去除 PYTHONPATH；核 icode 模块来自 site-packages 且不在 checkout，helper/manifest 也位于同一已安装包。复用 from_bundle 原始摘要校验，不把临时包来源检查称作发布者签名或抗 TOCTOU 启动绑定。

真实临时 Git 工程使用拆分元数据 WorkspaceManager Session：ToolContext 只借用目录对象；先验证 PreparedCommand 的 FD/cwd，再通过产品 default_registry/run_command 跑资源链。有效源码读取、实际写入、limit=1 的真实 fork EAGAIN、configured/terminal/观测/清理回执均检查；fstat 原目录 FD 必须 EBADF。此项检查原 FD，不夸大为任意 duplicate FD 全覆盖。

真实 timeout 先生成 started 文件，核 timeout、进程组/scope 回收与 Session FD 存活。最后冻结 PreparedCommand 后同时替换路径与 FD，接收端必须给出固定身份不匹配诊断，新旧目录均无负载写入；退出关闭 Session owner，finally 释放工单 lease。

## 研究与取舍

独立只读联网核 Codex HEAD `cc7ba33601286a751477832b01de7b6f8de0dd9c`（2026-10-10，Apache-2.0）。[bundled launcher](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/linux-sandbox/src/bundled_bwrap.rs#L65-L95)用同一 File 校验与 FD 启动；其 expected digest 缺失分支不做摘要验证，不能泛称全部 helper 已认证。[FD 测试](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/linux-sandbox/src/fd_mount_tests.rs)属于上游源码单测，不能替代 ICODE 成品运行。

- 采纳：成品模块/二进制/manifest 同源检查、原生身份负控、真实资源链与清理。
- 暂缓：本片实现 helper FD-exec；需另评生命周期与兼容链。
- 不适配：文件存在、manifest 非空、源码测试或原 FD 号缺失冒充全面运行/泄漏证明。

收益为关闭源码测试到发布成品的证据缺口；成本是安装后有界探针及一次真实临时 Git 工程。不复制上游代码，不新增运行依赖、权限或安装步骤；本探针需要 CI 已有 Git，不证明无 Git 新工程的 Native 完整支持。

## 验证履历与边界

CI 接线测试先 RED：安装后 stage 缺失；接入后 GREEN。首次实际 wheel 流程在新探针 `timeout_not_enforced` 失败，原因是探针误断言 timeout 的 error_code，而生产协议只记录 error；只修探针，不改产品错误协议。修正后完整 wheel 流程通过；加入包内 helper/manifest 归属与 fstat 原 FD 负控后再跑完整流程，所有阶段 PASS，包括新 Session 对象、既有资源、违规回执、宿主强杀清理、租约到期及 Git broker。租约仍输出 conformance_credit=none，不能授总门信用。

独立只读审查三文件无阻断，核对实际 error 字段、故障注入 finally 与 lease 释放。源码注入负控将导入强制定位 checkout，必须只输出 package_not_installed 并退出1。最终专项执行 `tests.test_ci_workflow_contracts tests.test_linux_workspace_fd`：38 项通过、0 跳过；单进程语法编译和 diff 检查通过。2026-10-11 06:03 UTC 完整提交前 preflight 返回0，密钥扫描、子模块完整性与全量 unittest 三道全部通过；治理、官网和20项观察名单排期检查通过。preflight 不输出测试数量，不补造数量。

本机 x64 已验证实际安装包链；ARM64 必须等待本片新 SHA 的四平台 wheel 实跑。Windows/macOS、完整 Reviewer、uniform_violation 全类别、策略完整度、真实模型六步与≥90%一致性均未关闭；policy_contract_ready 保持 false。

### 发布后实际四 Linux 安装包证据

上述“ARM64待跑”是提交前窗口。已提交推送 `532dae19099eec79772015ff6052175650da3d35`，远端main完整SHA一致。其 CI `38116851881` 的四个 Linux native jobs 均终态 success，主代理读取各自实际日志，新stage如下；不是打包SKILL测试或Windows签名任务推断。

| 平台 | job | 新Session安装stage（UTC） | 租约安装探针 |
| --- | --- | --- | --- |
| Ubuntu22.04 x64 | [114403333467](https://github.com/ayukyo/icode/actions/runs/38116851881/job/114403333467) | PASS，06:06:12.7438830 | PASS，conformance_credit=none |
| Ubuntu22.04 ARM64 | [114403333621](https://github.com/ayukyo/icode/actions/runs/38116851881/job/114403333621) | PASS，06:06:13.4863045 | PASS，conformance_credit=none |
| Ubuntu latest x64 | [114403333616](https://github.com/ayukyo/icode/actions/runs/38116851881/job/114403333616) | PASS，06:05:59.7689986 | SKIP，namespace/loopback unavailable，conformance_credit=none |
| Ubuntu24.04 ARM64 | [114403333560](https://github.com/ayukyo/icode/actions/runs/38116851881/job/114403333560) | PASS，06:05:55.1576700 | SKIP，同上，conformance_credit=none |

四者实际输出 `probe installed wheel session workspace object: PASS`，资源安装探针亦PASS。源级conformance的22.04双架构为9/10、ready=true，其余两个8/10、ready=false；这不改变Landlock `policy_contract_ready=false`，也不授完整Reviewer或总门信用。产品自主准入还检查该独立策略标志。

观察纠正：最初把新stage待观察目标指向Windows provenance四安装矩阵不正确；此stage在 `ci.yml` 的 `Build and verify installed Linux wheel`（`run_native_wheel_ci.py`），不是Windows workflow。已按真实调用链改正并获得四Linux实证。旧 `9cb3809` provenance被工作流并发规则取消，不能算通过；新 `532dae1` provenance此时仍运行，独立保留，不用来证明本stage。

`532dae1` 主CI随后终态 failure：39成功、2 Windows Reviewer失败、3跳过。双Linux全量各2547项，2476通过/71跳过/0失败/0错误；失败窗口不由四wheel专项通过抵消。

### 验收边界矩阵

acceptance_contract：本片要求安装包真实 Session FD 保留、资源配额、超时清理及冻结身份替换拒绝；消费者为产品run_command/native接收端，环境为本机x64及上述四Linux runner。完整Reviewer/模型六步不是本片通过声明，但仍是总目标的必需项。

| verification_matrix 层 | 必需 | 场景/消费者 | 基线与证据 | 结果 |
| --- | --- | --- | --- | --- |
| static/unit | 是 | 安装入口、防checkout误导入、相关FD链 | 38专项及三道preflight，提交前履历 | pass |
| build/deploy | 是 | 构建wheel、干净venv、包内helper/manifest | 532dae1四Linux实际安装日志 | pass |
| host/consumption | 是 | Session→产品run_command→原生对象、配额/timeout/替换拒绝 | 同一安装stage PASS；对应脚本逐项强制断言 | pass |
| policy admission | 总目标必需 | 自动工单完整策略、Reviewer隐藏账本 | isolation.py策略标志false；autonomy.py模型调用前独立检查 | 未通过；仍拒绝 |
| Windows/macOS/model | 总目标必需 | 平台隔离、配额、实际六步/90% | 各自待验或失败，不由上述相邻层代授 | 未通过 |

negative_evidence：latest/24ARM租约安装探针SKIP；双Windows Reviewer F；源码9/10并非完整policy。gaps：Reviewer排除与资源链、统一违规全类别、可信启动绑定、其它平台和真实模型总门仍缺；由后续各自实现/实测闭合，禁止用安装片替代。

verdict：本安装片 required 四Linux环境 verified；整体 R2/R3 为 partially_verified，未完成。允许声明四Linux实际安装Session对象专项通过；禁止声明完整策略、自动模式或整体通过。本文无工单完成状态变更。

后续终态：`532dae1` Windows provenance `38116851941` 返回success（validate+四矩阵）。主代理读取 `114405392808/817/849/854` 实际日志，均有安装包密码学来源、包内verifier绑定、offline验证、真实密码学负控、direct-volume、bootstrap拒绝setup/commands及signed wheel export PASS；各9项测试通过。PE采集仍production_authority=none，三个解析/加载/来源标志false。此为独立Windows签名安装层，不是Linux对象或生产启动证据；已终态窗口停止重复观察。

本轮证据/待确认设计文档的完整preflight于2026-10-11 06:27 UTC再次返回0、三道通过；没有生产代码变化。governance/site/landscape/diff通过。新Windows公网与Linux只读视图是待确认提案；PE目录设计已通过独立SPEC及QUALITY审查，实际实施尚未开始。这些提案不能被本文已通过的安装验证代授。

## 架构级自检报告（本切片）

- ✅ 语法/编译：单进程 Python 编译、完整 wheel 构建及安装通过。
- ✅ 依赖/调用链：已安装包→Session→ToolContext→产品资源 broker→原生 helper 实跑通过。
- ✅ 逻辑/边界：源码误导入拒绝、真实配额、冻结身份替换拒绝通过。
- ✅ 异常处理：已覆盖 timeout、负载未启动、替换 FD 回收与 Session lease 释放；不宣称未知异常全覆盖。
- ✅ 关联模块：既有安装后探针保留，相关38项及全量 preflight 通过。
- ✅ 兼容安全：不改产品协议、权限、准入或 vendor 固定版本；其它平台结论不由本机代授。
- ✅ 可运行性：本机 x64 及发布后四Linux wheel专项通过；R2/R3总门仍未通过。
