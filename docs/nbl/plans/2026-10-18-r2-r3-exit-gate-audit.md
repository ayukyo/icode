# R2 / R3 退出门槛逐条核对（2026-10-18）

**口径**：以 `docs/icode-agent-product-architecture.md` §13.6（R2）与 §13.7（R3）的退出门槛原文为准，逐条映射到“代码落点 / 测试 / CI 收据”，结论只取三档：**通过**（有 OS 层或契约层直接证据）、**部分**（有实现但存在明确缺口）、**待补**（无实现或无证据）。不以“相关测试绿了”代替门本身。

**证据基线**：HEAD `8687002`；CI run `39115536392`（45 job / 42 成功 / 0 失败 / 3 跳过，conclusion=success）、provenance `39115536372`（validate + 双架构 attest/install 全绿）、官网 `39115536367`；本地全量 3641 项 failures=0（仅本地 uv Python 缺 setuptools 的环境性 setUpClass 不计）。

---

## R2 真正隔离：四条门

| # | 门（原文） | 关键证据 | 结论 |
|---|---|---|---|
| R2-1 | 原始工作树、工作区外文件、受保护目录和网络的负向测试全部通过 | 见下 | **通过（OS 层）** |
| R2-2 | 危险命令即使被模型构造为变体也不能绕过策略 | 见下 | **通过（G1 已收口）** |
| R2-3 | 沙箱不可用时无裸执行降级 | 见下 | **通过** |
| R2-4 | 审批只承担业务风险确认，不被当作隔离替代品 | 见下 | **通过** |

### R2-1 负向测试（三平台 + 双层）

- **Windows（OS 强制，双架构 CI 实收据）**：`R3 Windows Reviewer snapshot candidate` 以临时标准用户在 AppContainer 内运行，收据字段全部为真——`outside_snapshot_denied / workspace_denied / home_denied / ledger_denied / write_denied / delete_denied / rename_denied / create_denied / dacl_write_dac_denied / write_canary_unchanged`（job `117624491590`，run `39110200656`，x64；ARM64 同构）。配套 `R2.3 Windows Job cleanup probe`、`R2.3 Windows wheel packaging`、`R2 authenticated runner pipe` 四类 job 在 x64/ARM 双腿 success。
- **Linux**：`tests/test_linux_workspace_fd.py::test_native_read_only_and_outside_boundaries_remain_enforced`（只读与越界边界）、`tests/test_linux_violation_receipt.py::test_caught_network_socket_denial_returns_os_enforced_receipt`（网络拒绝返回 OS 收据）、`tests/test_network_lease.py::test_expiry_generation_and_network_denial_fail_closed` 等三条（网络 fail-closed）；受保护路径（`.git`、`identity.common_dir`）在 `test_autonomy.py:301/330/395`、`test_chain.py:85/130`、`test_execution_broker.py:43` 中作为 `protected_paths` 注入并断言拒绝。
- **macOS**：`tests/test_macos_unix_socket_probe.py::test_path_scoped_unix_proxy_works_while_other_sockets_remain_denied`（点路径放行、其余 socket 仍拒）等；CI `R2.2 native probe` 在 macos-latest 与 macos-15-intel 均 success。
- **网络负向**：零能力 AppContainer 双栈实测 `10035` + `FD_CONNECT` 超时且无 canary（de637ac 起记录，1fdfa41 起以三元证据固化）；Linux 侧 network lease 拒绝路径见上。

### R2-2 危险命令变体（缺口 G1）

- **已覆盖**：`tests/test_guard.py::test_危险命令拒绝` 覆盖 9 种变体（`rm -rf /`、`rm -fr .`、`git push --force`、`git reset --hard`、`curl | bash`、`mkfs`、`shutdown`、fork 炸弹、`del /s /q C:\`）；`test_工作区外写入即使穿越也拒绝`、`test_工作区内受保护路径优先拒绝且符号链接不能绕过`。
- **实测缺口（本地 stdlib 直接调用 Guard）**：
  - `python -c "__import__(chr(115)...).rmtree('/')"` → **allow**（`python` 在白名单且载荷无 shell 元字符）
  - `find / -delete` → **allow**（`find` 在白名单，`-delete` 不在危险模式表）
  - `git clean -fdx` → **allow**
  - `rm -r -f /`、`rm --recursive --force /` → `require_approval`（未被模式表命中，退化为审批而非拒绝）
- **性质判定**：`src/icode/guard.py` 首行自述“应用层权限模型（**不是沙箱**）”，与架构 §15“不用命令白名单冒充 OS 沙箱”一致；真正的边界在 OS 层（写边界、受保护路径、网络），上述变体在 OS 层仍被兜底（工作区外写入/受保护路径/网络均拒绝）。但 `git clean -fdx` 的破坏发生在允许写入的工作区内，OS 层不会拦，属于“任务边界内可破坏”，且 `destructive_risk` 分类未触发审批。
- **结论**：应用层变体可绕过，OS 层不可绕过 → 判 **部分**，记 **G1**。

### R2-3 无裸执行降级

- `src/icode/autonomy.py:180/193/207/215`：无 session、取策略异常、策略身份不符、`prepare_policy` 异常 → `state="blocked", error_code="isolation_unavailable"`，不进入执行。
- `src/icode/execution_broker.py:310/332/549`：`isolation_unavailable` 直接失败返回，不回落裸执行。
- `src/icode/engineering_verification.py:528`：`execution_unavailable`。
- 测试：`tests/test_autonomy.py:476/512/539/892/1389/1422/1452`、`tests/test_isolation.py:3102` 断言 blocked/错误码。
- 结论：**通过**。

### R2-4 审批与隔离分离

- 架构 §13.6 原文：“审批只承担业务风险确认，不被当作隔离替代品”。
- 机制证据：网络能力必须经 `network_lease`（`test_network_lease.py:385/476/511`，lease 必须绑定 denied 基础策略，审批不能替代 lease）；Git 外部写经 `git_broker` 的 policy 校验；安装/引导走独立 `R2 bundled SKILL install`、`R2.3 Real Windows bootstrap wheel` job（独立授权路径，不因审批放行）。
- 结论：**通过**（审批决策不创建 lease/broker 策略/安装授权，结构上分离；能力授权与审批是两条独立路径，且有对应 job 证据）。

---

## R3 自验证与有界修复：四条门

| # | 门（原文） | 关键证据 | 结论 |
|---|---|---|---|
| R3-1 | 失败分类可以稳定决定 retry、fallback、人工介入或停止 | 见下 | **通过（G2 已收口）** |
| R3-2 | 重复无进展尝试能被检测并终止 | 见下 | **通过（G3 已收口）** |
| R3-3 | 代码变更后验证证据不会错误复用旧结果 | 见下 | **通过** |
| R3-4 | Reviewer 与 Executor 使用隔离上下文，Reviewer 不能修改被审对象 | 见下 | **通过** |

### R3-1 失败分类（G2）

- **契约真源**：`vendor/icode-skill/references/execution_model.md` §4 定义六类（`retryable_transport` / `capability_unavailable` / `deterministic_failure` / `policy_schema_security` / `ambiguous_side_effect` / `destructive_risk`）与 `policy --opclass --failure --attempts` 查询，返回 `action / max_attempts / backoff_seconds / conclusion_ceiling / auto_retry`。
- **ICODE 桥**：`src/icode/control.py:404 control.policy(opclass, failure, attempts)` 已实现。
- **缺口**：全仓（`src/`、`tests/`、`scripts/`）**零调用点**——`autonomy.py` 只调用 `session.policy(step)`（沙箱策略，同名不同义）；失败后是否 retry/fallback/停止未由分类驱动，实际由外层循环与人工编排。
- **结论**：契约与通道齐备，运行时未接线 → **部分**，记 **G2**。

### R3-2 无进展检测（G3）

- 全仓无 `stuck` / `no_progress`（针对重复尝试）实现或测试；`loop.py` 只有 `max_turns=12` 的粗上限；上游 `conclusion_repeatedly_overturned` 是“结论被新证据连续推翻”的升级触发器，不等于“重复无进展尝试检测并终止”。
- **结论**：**待补**，记 **G3**。

### R3-3 证据绑定与旧结果不复用

- `src/icode/engineering_evidence.py:104-113 build_engineering_evidence`：拒绝非 host-owned 的 plan/run/binding；`binding.step/attempt != run.step/attempt` 拒绝；`tested_worktree_fingerprint != run.source_after` 直接拒绝（`:113`，代码变更后旧测试证据无法挂到新源码）；`:60 _public_binding` 绑定 `command_sha256 / artifact_hashes_sha256 / output_sha256 / exit_code / execution_attempt`。
- 测试：`tests/test_engineering_evidence.py:149`（精确 plan 顺序与 binding）、`:193`（unknown source 不得臆造）、`:239`（真实源码/环境/工具/参数/失败事实刷新修复键）、`:216`（基础观测标签不得刷新修复键）。
- 结论：**通过**。

### R3-4 Reviewer 隔离

- `src/icode/reviewer.py`：只读审查上下文（`reviewer_guard:98` / `is_review_read_only:121`）、只读自检（`verify_read_only:141`），自检失败拒绝结论（`:175`）。
- 测试：`tests/test_reviewer.py` 的 `test_只读上下文拒绝写但允许读`、`test_可写作用域不是审查只读`、`test_符号链接被审对象拒绝`、`test_只读自检失败时拒绝结论`、`test_无证据不算自验证结论`、`test_失败证据产生blocking且引用指纹`。
- Windows 端 OS 强制：Reviewer 以临时标准用户 + AppContainer 运行，`dacl_write_dac_denied / write_denied / delete_denied` 全真，双腿 CI success（同 R2-1 收据）。
- 结论：**通过**。

---

## 汇总

- **R2**：4/4 通过。
- **R3**：4/4 通过。
- **R1 发布门**：六阶段非玩具任务验收仍为独立发布门槛，本核对不涉及。

## 收口记录（2026-10-18，用户授权“都做”）

- **G1（guard 参数级否决）**：`src/icode/guard.py` 增加 `_argument_verdict`。`find -delete/-exec/-execdir/-ok/-okdir` → DENY；`git clean` 含 `f`（`-fdx`/`--force`）→ REQUIRE_APPROVAL（`git clean -n` 仍 ALLOW）；`python -c` → REQUIRE_APPROVAL（`python -m` 仍 ALLOW）；`rm` 的分离写法（`rm -r -f /`、`rm --recursive --force /`）→ DENY。测试：`tests/test_guard.py::test_白名单命令的破坏型参数不能借白名单放行`。
- **G2（失败分类接线）**：新增 `src/icode/failure_policy.py`（六类映射、`decide_failure` 四态收敛、策略载荷严格解析 fail-closed）；`NativeChainExecutor.failure_decision` 先查 `control.policy` 再决策（无策略通道时降级人工介入）；worker 在失败边界记录有界 `failure_decision`，并仅在策略明确 `retry` 时做一次有界重跑（`_WORKER_RETRY_LIMIT=1`，写入步骤由上游策略改写成先核对回执）。测试：`tests/test_failure_policy.py`（分类/策略/畸形载荷/四态）、`tests/test_autonomy.py::test_策略允许的重试只重跑一次且成功后不留失败决策`。
- **G3（无进展检测）**：失败指纹 = `step:error_code`，跨 run 有界历史（`HISTORY_LIMIT=8`，新 run 继承，成功后清空）；最近一次与本次相同即判无进展，决策强制 `stop`、`error_code=no_progress_stuck`。测试：`tests/test_failure_policy.py::TestNoProgress`、`tests/test_autonomy.py::test_失败决策有界记录且相同失败证据第二次即判无进展`。
- 失败决策对外只投影三个稳定字段（`class`/`action`/`stuck`），不含命令、路径、异常正文。

## 后续

三项已收口，R2/R3 八条退出门槛全部有实现与测试证据。下一步可按架构要求为 R4（上下文与多模型）单独出 SPEC + 影响面 + 验收计划（R4 四条退出门槛见 §13.8）。
