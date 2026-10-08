# Linux 任务与管理环境边界 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. 用户已要求直接在 main 开发、验收后提交推送，不建立分支或 worktree；单实施者写代码，研究与复审只读。

**Goal:** 在已有私有 resource 模式下，任务不继承 systemd 管理环境，任务 stderr 进入任务 stdout，管理 stderr 留在独立宿主通道。

**Architecture:** 复用 namespace PID1、原子 quota 创建和 pre-exec error pipe，只在根 payload 的 exec 边界处理环境与标准流。无 resource 的旧调用保持原行为；后续 broker 才负责有界排空并丢弃管理 stderr。本片不接产品入口、不开放评分或自动模式。

**Tech Stack:** C11、Linux Landlock/seccomp/cgroup v2、Python 3.11 unittest、已有 user systemd manager；不新增权限、服务或依赖。

---

## 文件与固定合同

- 修改 `native/linux/icode_landlock.c`：根 payload 分支去除管理变量，exec 前重定向 stderr；失败写已有专用 error pipe 并退出。
- 修改 `tests/test_linux_task_resource.py`：复用真实随机 scope、cap、resource/USER_NOTIF 双 FD 和 GC harness，增加环境/流边界正负控。
- 修改本计划及 `docs/nbl/specs/2026-10-08-linux-payload-quota-design.md`：只登记实际证据。
- 不改变 `icode_task_quota.h`、资源协议、模型 schema、score、其它平台或无 resource 的环境合同。

真实问题：未来可信 broker 必须给管理进程当前 UID 的 user bus 地址，但不能给任务该管理环境；现有 stderr 合流无法区分管理诊断与任务输出。已有实现：`error_writer >= 0` 精确标识私有 resource 模式，复用错误管道，不加新外部开关。调用链：`supervise_task → run_namespace_init → payload → execvp`；管理程序/launcher/PID1 的 stderr 不变。

独立研究发现 systemd scope 另注入 `INVOCATION_ID`；因此任务移除 `DBUS_SESSION_BUS_ADDRESS`、`XDG_RUNTIME_DIR`、`INVOCATION_ID` 三项，不恢复任意宿主环境。参考既有持续对照中的固定 systemd v249/v254 源码，借机制不复制实现。

### Task 1: resource 模式下的 payload 环境与标准流

**状态**
- [x] 任务完成（本机分片；新提交远端复验单独跟踪）

**Dependencies:** None（须先完成当前私有回执分片独立复审、安装验证和提交）
**Parallelizable:** No（修改冻结 native 文件，研究与复审可只读并行）

- [x] **Step 1: 写真实边界测试**

给现有 `run_resource` 增加内部测试参数 `management_boundary: bool = False`。启用时仅给本次 scope 的测试环境设置两条 bus 变量，使用 `_user_manager()` 提供的真实地址；其余代码不动。payload code 在现有 FD/argv/UID 断言后追加：

```python
assert 'DBUS_SESSION_BUS_ADDRESS' not in os.environ
assert 'XDG_RUNTIME_DIR' not in os.environ
assert 'INVOCATION_ID' not in os.environ
print('payload-stdout', flush=True)
print('payload-stderr', file=sys.stderr, flush=True)
```

本次 `communicate()` 的 `output` 必须含两个固定 marker；`error` 必须不含它们。测试原 scope 仍精确 GC，resource finished/complete、payload_started unknown。分别真实 default、forced mapless、与 USER_NOTIF 双端点运行，不用 argv mock 代替任务执行。default 允许既有 native 的 mapped UID0 或自动 mapless UID65534，不能把 default 标签当保证 mapped；forced mapless 仍严格要求65534。支持主机实际默认 mapped 的证据另行记录。新增测试方法调用上述参数并断言回执，不改旧方法含义。

- [x] **Step 2: 观察 RED**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_linux_task_resource -v`。
Expected: 新方法在任务环境/标准流断言上失败（管理变量仍存在或 stderr marker 留在宿主 error），旧方法仍通过；保留准确 RED 原因。若只有 import/编译失败，先修测试而不是写实现。

- [x] **Step 3: 最小 native 实现**

在 `run_namespace_init` 的 `payload == 0` 分支、隔离及 violation FD 关闭完成后、`execvp` 前，增加：

```c
if (error_writer >= 0 &&
    (unsetenv("DBUS_SESSION_BUS_ADDRESS") != 0 ||
     unsetenv("XDG_RUNTIME_DIR") != 0 ||
     unsetenv("INVOCATION_ID") != 0)) {
    icode_resource_preexec_failure(error_writer);
    _exit(1);
}
```

接着增加：

```c
if (error_writer >= 0 && dup2(STDOUT_FILENO, STDERR_FILENO) < 0) {
    icode_resource_preexec_failure(error_writer);
    _exit(1);
}
```

当前 `execvp` 失败随后调用 `perror("execvp")`；重定向后会写入任务 stdout。即使正常 phase2 会使 broker 丢弃输出，通道同时失效时也不能泄露原生诊断。因此替换该处诊断为：

```c
if (error_writer < 0) perror("execvp");
```

加清楚注释：只改私有资源模式的载荷，管理进程标准流与旧无 resource 调用不变。重定向后的原生失败只写专用 F；不根据 stderr 文本判断启动状态。新增 missing_exec 回归断言 stdout 不含原生 execvp 错误，保留原退出码与可信 phase2。

- [x] **Step 4: GREEN 与故障负控**

Run: `PYTHONPATH=src .venv/bin/python -m unittest tests.test_linux_task_resource -v`；Expected: 全部通过、0 SKIP（当前支持主机）。单次本进程注入 `dup2(1,2) → EPERM`，先对旧路径观察 payload marker RED，再对新路径验证无 marker、preexec_failed/false、scope GC；不改变宿主 seccomp。只对无法安全真实触发的 unsetenv 分配失败使用局部 API 故障注入，验证同样失败关闭，不制造机器内存耗尽。

额外无 resource 真实旧 native 调用传入三个非敏感固定测试值；核对环境仍保留、stdout/stderr 分离，明确该兼容检查不计产品安全分。

- [x] **Step 5: 冻结验证与提交**

冻结后新组件全部方法重复 20 轮、0失败/跳过，原 quota/helper/mapless/PID namespace/USER_NOTIF 关联回归；C11 `-Wall -Wextra -Werror -fanalyzer`，独立 SPEC→QUALITY。实际 sdist→wheel→干净 pip 安装，使用安装包内 helper 复验两种 payload marker 和管理环境；不能只测 source driver。

Run: `PYTHONPATH=src .venv/bin/python scripts/preflight.py`、三个 governance/site/landscape 检查和 `git diff --check`；Expected: 全仓门禁通过。主代理按用户已有授权只提交本片精确文件并推送 main，核实 remote SHA，再开始真实 broker 接线；不由实施者提交未验收代码。

## 验收上限与自检

当前前置提交 e2bd25d 的远端全仓测试暴露夹具兼容错误，须先闭合：default 硬断言 UID0 与既有合法 mapless fallback 不一致；cleanup 优先级负控从本次 scope 外搬进程受 common-ancestor 权限拒绝。仅修测试，使用实际空 uid_map 的 default 回归及本 scope 内、真实 quota_fork 创建的有限寿命 charged 子进程；后者证明非空导致启动前失败＋cleanup_failed 优先，不宣称触发 clone3/EAGAIN。所有 management FD 副本关闭，最终 waitpid 自有子进程和 exact GC。不得 sudo、改全局 controller 或新增 SKIP 掩盖支持场景。最终冻结 hash 的重复轮数与关联测试必须重跑，不借旧轮数。

语法、依赖/调用链、逻辑/边界、异常、关联、兼容安全、可运行性逐项登记真实证据。管理 stderr 的宿主有界读取、完整 `_policy_environment`、ToolContext/run_command、并发、取消/timeout/output/host-crash 尚不在本片已验证范围，不报告 R2/R3 完成。

2026-10-08 最终冻结 C0700aa／tests87db9：43×20＝860，关联124，独立SPEC123、QUALITY57，均0 SKIP；sdist重建与干净安装 helper 六项通过，旧安装十阶段全通过。最终冻结后完整 preflight 密钥／子模块／全仓测试3/3、governance／site／landscape、严格C静态分析、compileall和diff-check通过。较早运行期间夹具曾改版的preflight不用于此最终验收。精确摘要／产物及远端e2bd25d失败证据见规范，本片不增加产品资源评分。

**Execution Mode:** serial
