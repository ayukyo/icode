# Python 3.12 Runtime Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development or nbl.executing-plans task-by-task. 用户已明确main-only，不建立分支/worktree；仅root提交推送。

**Goal:** 移除Agent的Python3.11支持与重复CI版本cell，不降低任何剩余平台/安全验收。

**Architecture:** 复用现有包和workflow，仅修改版本声明、当前观察版本校验及精确矩阵。旧事件/观察schema、job标识、测试命令和权限不变。

**Tech Stack:** Python stdlib unittest、TOML、GitHub Actions YAML、既有HTML与CMake。

---

### Task 1: 当前支持范围TEST

**Dependencies:** None
**Parallelizable:** No (唯一TEST writer；SOURCE尚不改)

- [x] TEST作者完整阅读相关文件，更新`test_full_suite_ci_budget.py`、`test_full_suite_ci_diagnostics.py`、`test_ci_delivery_job.py`当前full矩阵期望为`python-version: ["3.12"]`。
- [x] `test_packaged_skill_ci.py`期望精确五平台各3.12、无重复；`test_ci_workflow_contracts.py`workspace期望原四平台各3.12、计数4，原非版本断言保留。
- [x] 新`tests/test_python_runtime_policy.py`冻结元数据/双语当前要求/构建版本、所有setup版本、实际平台集合及不删job/权限/安全门。安装观察旧TEST将正常runtime改为3.12，保留3.11拒绝和3.13拒绝，不误把正常3.12继续列为负控。
- [x] `PYTHONPATH=src python -B -m unittest tests.test_python_runtime_policy tests.test_full_suite_ci_budget tests.test_ci_delivery_job tests.test_packaged_skill_ci tests.test_ci_workflow_contracts tests.test_windows_installed_source tests.test_windows_installed_chain -v`取得真实预期RED，保存完整原log；资源成本较高的已有临时clone方法仅在必要时单独选取，不运行全仓full/native。
- [x] 自审及独立审查，不以语法/导入错误当Assertion RED；实际测试源码是资产真源，未授权模型凭据或系统变更。

### Task 2: 最小SOURCE配置与运行边界

**Dependencies:** Task 1
**Parallelizable:** No (不同SOURCE作者，唯一代码writer)

- [x] `pyproject.toml`写`requires-python = ">=3.12"`；`native/windows/CMakeLists.txt`写`find_package(Python3 3.12 REQUIRED COMPONENTS Interpreter)`；`setup.py`仅将wheel支持说明改3.12+。
- [x] `.github/workflows/ci.yml`所有固定3.11 setup与名称改3.12，主矩阵写`python-version: ["3.12"]`。packaged include精确为ubuntu-latest、macos-latest、macos-15-intel、windows-latest、windows-11-arm各一条3.12；workspace为ubuntu-latest、macos-latest、windows-latest、windows-11-arm各一条3.12。禁止更改其它字段/步骤/job。
- [x] `.github/workflows/windows-helper-provenance.yml`validate设3.12；sign只保留原3.12两行cell（x64/ARM64各自架构字段原样），不得更改签名权限或证明门。
- [x] `scripts/probe_windows_installed_chain.py`的producer guard改为：

```python
    if (sys.version_info.major, sys.version_info.minor) != (3, 12):
        raise ValueError("invalid_installed_observation_input")
```

- [x] 同文件`_runtime`中仅将`_exact_int(value[1], 11, 12)`改为`_exact_int(value[1], 12, 12)`；`scripts/probe_windows_installed_source.py`中仅将`_integer(python[1], 11, 12)`改为`_integer(python[1], 12, 12)`。不改回执schema/owner策略/资源清理/权限。
- [x] 双语README、`site/index.html`/`site/en/index.html`当前要求改3.12+，徽章改`Python-3.12-blue.svg`。`scripts/check_governance.py`同步相同徽章及单元素full矩阵token；不更改其余治理门。
- [x] 重跑Task1软件selector及诊断9项、治理/站点；失败先定位原log，不跳测刷绿。原3.11技术事实、历史记录及Skill仓不做全局替换。

### Task 3: 审查、候选及线上证据

**Dependencies:** Task 2
**Parallelizable:** No (候选必须冻结后审查)

- [ ] 核diff精确范围；所有jobID集合、原非版本命令/权限/timeout不变；仅删除重复版本cell，四平台workspace/五平台安装/双架构签名仍在。
- [ ] fresh SPEC和不同QUALITY通过；root执行密钥/固定子仓/whitespace必要检查，保留其它作者独立PLAN草稿与原Windows链接。
- [ ] 先核上一Agent候选三run全终态，再将本候选main-only提交推送，不发标签；本机未做full/native，线上承担完整验证。
- [ ] 绑定新SHA/run/job/原log/退出，实际展开预计主CI45、provenance3、Pages2，不以预计代替实测。版本收敛成功也不授WP0b、Mac完整quota或R2/R3整体通过。

---

### Task 4: beb线上暴露的精确计数关联修复

**Dependencies:** Task 2；Task 3线上失败已观察，不要求失败候选变绿
**Parallelizable:** No (TEST与SOURCE作者分离；下一推送仍等原三run终态)

`beb499b`工作区995项/8 Assertion失败证实本片漏同步计数消费者；此前零审不是该缺口不存在的证明。原生/权限/运行版本政策不改，不动态放宽数量、不取消skip拒绝。root实际MCP三步回执`4bcbd1`。

| producer/consumer边界 | 旧值 | 当前真实值 |
| --- | --- | --- |
| InstalledProbe / InstalledWire | 7 / 11 | 8 / 12 |
| SourceReceipt / SourceConsumer | 6 / 21 | 7 / 22 |
| installed_chain / installed_source模块 | 46 / 33 | 48 / 35 |
| sign四selection与去重总量 | (46,6,3,14) / 69 | (48,6,3,14) / 71 |

- [x] root TEST-only在`test_python_runtime_policy.py`新增解析实际sign嵌入Python的回归：只load四selection以核数量，不执行Windows探针；command指纹仅按后两条计数assert的确切变更更新为`5dbce0bb10c4e9dc55a196a8ebf43b8aa423a3fa81ef7cdbc4ef70f20805570a`，policy指纹不变。
- [x] 正式RED为新两方法＋原StartupPinCiTests14合16，10 Assertion/0ERRORskip，完整11480B/SHA52fe925542e8dcc948d6cd1f9d0230d48fddec11baf6bd77725d72a201a6a630。既有WSL311仅软件诊断，driver显式模拟312版本标签以运行已不支持311的parent-bound回执fixture；不是实际312运行证据。此前未模拟标签的诊断额外触发unsupported311 fixture失败，不授产品缺陷；首次日志输出截断也不当完整原件。
- [ ] fresh TEST SPEC与不同QUALITY后，不同SOURCE作者只改`tests/test_windows_startup_pin_ci.py`的上述四类、两模块及对应skip计数常量；原32类/所有14方法/skip注入断言原样。
- [ ] SOURCE作者只将provenance嵌入门的tuple改`(48, 6, 3, 14)`、双去重总量改71；实际选择、执行命令、旧真实RED探针、权限/超时/架构不改，不修改root TEST补绿。
- [ ] 同一16方法必须零失败/错误/跳过；补全运行策略及132相关回归并纳入原skip-enforcement模块，软件版标签仿真明确分账。独立实际源码及整片审查、必要守护后才推后续main候选；原beb所有失败保留，不取消/重跑刷绿，真实312仍待新SHA线上核验。

**Execution Mode:** serial

Task 4关联补充：beb线上full的另两项失败来自`tests/test_provenance_validation_budget.py`冻结的旧版本workflow哈希。root在当前候选亲证3项中2个Assertion失败、0ERROR/skip后，仅更新该文件两个完整SHA256基线和说明；保留25分钟预算、完整prefix/sign字节冻结及命令/权限独立策略指纹，不增加归一化规则。此文件纳入本片审查与针对性回归，不能以更新哈希代替原workflow差异审查。

用户已批准该支持范围调整，按既有持续执行授权实施，不新增重复人工审批。计划自审：三项覆盖配置/回执/测试/双语描述与原生平台保留，零新通用框架/外部依赖；实际软件资产在Task1先落并验证，SOURCE严格限定以上机械改动。
