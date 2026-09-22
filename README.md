# icode — 过程可审计的 AI 编码 Agent

> 本项目的唯一切口：**不是给 Agent 装一道审计门，而是让 Agent 本身不可撒谎。**
> 现有治理类项目（Conduct AI / MakerChecker / sofagent 等）几乎都是「套在不可审计的 Agent 外面的一道门」；
> 我们审的是**过程**，而不是**产物**。

- 上游：[icode-skill](https://github.com/ayukyo/icode-skill) 以 git submodule 形式只读消费（**两仓完全独立，本仓永不修改子模块**）
- 设计文档：[方案与决策](./docs/design-decisions.md) · [开发路线图](./docs/roadmap.md) · [格局调研](./docs/agent-landscape.md) · [上游依赖面](./docs/upstream-contract.md)

---

## 我们和 icode-skill 是什么关系（重要）

**icode-skill 是「车管所」，我们是「司机」。**
它规定"什么算对"（流程、门禁、账本），我们负责"怎么做到"（执行）。

因此**存在三种"入口"，我们只用第三种**：

| 入口 | 给谁用 | 我们用吗 |
|---|---|---|
| `/icode plan`、`/icode code` 等 slash 命令 | **宿主 LLM**（Claude Code / Codex 读 SKILL.md 后由模型执行） | ❌ **不用**——我们就是执行者，不需要叫别的司机 |
| `install.sh`、`integrations/codebuddy/commands/icode.md` 命令桥 | 把 skill 装进宿主机 | ❌ 不用 |
| `tools/icode_control.py` **子命令**（step / artifact / operation / transition / trace） | 任何想合法推进工单的执行者 | ✅ **必须**——它是唯一写入口 |

```text
浏览器 UI（Phase 5）  ← 只发：意图 · 动作枚举 · revision
        ↓  POST + SSE（仅 loopback，带会话令牌）
本地后端 / core        ← Tool Loop · Guard 权限 · Approver 审批 · 回执 · 预算
        ↓  子进程调用（参数列表 / shell=False，只读消费）
icode-skill            ← icode_control.py 是唯一写入口，门禁与事件链在此判定
```

**WebUI 只换「审批」这一层的实现**（终端问答 → 网页弹框），core 其余部分一行不改。

---

## 怎么用

### 例子一：让 Agent 真去改代码（隔离靶场）

```bash
PYTHONPATH=src python -m icode.cli task --fixture pycalc --backend openai-compatible
```

背后依次发生：

1. 把 `tests/fixtures/pycalc` **复制**到临时目录（绝不污染仓库基线）
2. 模型自己读 `calc.py` / `test_calc.py`
3. 模型决定新增 `calc_gcd` / `calc_lcm`，调用 `edit_file` —— 每次写都过权限判定，只能是工作区内文件
4. 模型调用 `run_command` 跑 `python -m unittest` —— 白名单命令才放行
5. **跑完我们自己独立再跑一次测试** —— 不信模型的自我声明，只认退出码
6. 打印报告：退出码 / 改了哪些文件 / 花了多少 token

> 第 5 步是与普通 Agent 最本质的区别：**模型说"改好了"不算，退出码才算。**

### 例子二：产出「工单产物」

```bash
PYTHONPATH=src python -m icode.cli step-run --workspace /tmp/myws --step plan --backend openai-compatible
```

建单 → `step start` → 门禁复检 → 模型写 `01_plan.md` → `artifact` 登记哈希 → 复检 → `step finish` → 写推理 trace → 尝试状态前移（**可能被门禁拦下**）。

整条链路留下的是一串**带哈希的记录**，而不是"模型说它做了"。

### 例子三：不花钱验证流程通不通

```bash
PYTHONPATH=src python -m icode.cli handshake --workspace /tmp/hs   # 离线、零成本
python -m unittest                                                  # 全部测试
python scripts/preflight.py                                         # 提交前三道守护
```

---

## 命令一览

| 命令 | 说明 | 联网 |
|---|---|---|
| `icode doctor` | 环境与能力自检 | 否 |
| `icode steps` | 列出 `gates.json` 登记的步骤契约 | 否 |
| `icode brief <step>` | 打印该步骤的门禁简报（渐进披露的强制层） | 否 |
| `icode outline <step>` | 打印步骤文档章节索引（懒加载入口） | 否 |
| `icode handshake --workspace <dir>` | 契约握手：跑通完整步骤契约并校验事件链 | 否 |
| `icode step-run --workspace <dir> --step plan` | 用真模型按契约执行一个步骤 | 是 |
| `icode task --fixture pycalc` | 在隔离靶场副本上做能力验证（独立跑测试取退出码） | 是 |
| `icode evidence --ticket <dir> --dest <dir>` | 把工单导出为可独立校验的证据包 | 否 |
| `icode verify-pack <包目录>` | 校验证据包（与包内 verify.py 同一套逻辑） | 否 |
| `icode recover --ticket <dir> --step plan` | 分析被中断的工单该怎么继续（默认只分析） | 否 / `--resume` 时是 |
| `icode chain --workspace <dir> --requirement "..."` | 串起完整链路（顺序由状态机派生） | 是 |
| `icode webui` | 启动本地审批台（仅 127.0.0.1） | 否 |

安装为命令后可直接用 `icode`：

```bash
pipx install .          # 或 uv tool install .
```

---

## 现状

### Phase 1 —— 离线契约内核（已完成）

| 能力 | 状态 |
|---|---|
| 从 `gates.json` **动态读取**步骤契约（不写死步骤表） | ✅ |
| 契约与 `steps/*.md` 的交叉一致性校验 | ✅ |
| **渐进披露**：门禁规则强制注入 + 背景知识按需加载 | ✅ 强制层占全文 **9.3%**（335K → 31K 字符） |
| 控制面适配 + **确定性幂等键** | ✅ |
| 应用层权限模型（默认拒绝；**明确声明不是沙箱**） | ✅ |
| 离线校验：核心模块无网络导入 + socket 打瘸后仍可跑通 | ✅ |

### Phase 2 —— 真模型 + Tool Loop（已完成）

| 能力 | 状态 |
|---|---|
| 真模型后端（MiniMax-M3，OpenAI 兼容，**标准库实现，零依赖**） | ✅ |
| 工具集：`read_file` / `glob` / `grep` / `write_file` / `edit_file` / `run_command` | ✅ |
| **人在环审批协议**（默认拒绝；终端问答；可插拔 `Approver`） | ✅ |
| **副作用回执**：写与执行动作留 start/finish，歧义即停止，禁止盲重放 | ✅ |
| 传输类失败自动重试（只读动作可重试；4xx 确定性失败不重试） | ✅ |
| 代理策略可控（跟随环境 / 显式代理 / `--no-proxy` 强制直连） | ✅ |
| 预算与成本（**运营指标**，与质量指标分离） | ✅ |
| E2E 靶场隔离（复制到临时目录，独立跑测试取退出码） | ✅ |
| 推理门禁 trace（能力不足**如实写 degraded**，不冒充） | ✅ 诚实降级 |
| 完整 1→6 链路 | ⏳ 后续（`code` 步骤依赖 merge 产物） |

#### 实测结果（2026-09-23，真实模型）

**能力验证**（`icode task --fixture pycalc`）：

```text
独立验证：python -m unittest 退出码 = 0
改动文件：calc.py、test_calc.py
回合循环：11 回合 / 10 次工具调用；停止原因=no_tool_calls
成本：11 次调用 / 41,343 tokens（cached 33,944）
结果：通过（独立验证退出码 0）
```

**契约步骤**（`icode step-run --step plan`）：

```text
OK   产物登记 01_plan.md :: port=plan
OK   step finish（outcome=success） :: 回执被控制面接受
OK   推理 trace 写入 :: result=degraded attempted=False
OK   事件链可读 :: event_count=24
OK   无未闭合步骤/动作
【状态前移】被门禁拦截（门禁：thinking_gate, workflow_contract）
结果：通过
```

> 状态前移仍被拦下（预期、且正确）：上游要求 `plan` 用 L2 的 `sequential-thinking`
> 机制并留下真实 trace，本运行时尚未接入该 MCP，因此**如实写 degraded 而非冒充**。
> 待补清单见 [上游依赖面 §4](./docs/upstream-contract.md)。

---

### Phase 3 —— 证据包导出（已完成）

**这是产品形态**：把「过程」导出成外部可独立校验的凭证。

```bash
PYTHONPATH=src python -m icode.cli evidence --ticket <工单目录> --dest <包目录> --receipt-from <工程目录>
```

包结构：

```text
manifest.json          包清单 + pack_digest（每个文件的 sha256）
ticket/events.jsonl    事件链（唯一执行账本，原样）
ticket/metadata.json   工单状态元数据
ticket/bodies/         产物正文快照
artifacts.json         正文快照 ↔ 链上 sha256 对应表   ← D11 的核心
contracts.json         本工单涉及步骤的契约快照
verifications.json     外部验证回执（含命令退出码）
verify.py              独立校验器（零依赖，不 import 本仓任何代码）
```

**审计方不需要安装任何东西**：

```bash
python verify.py <证据包目录>     # 0 通过 / 1 被篡改 / 2 用法错误
```

#### 实测（真实模型产出的工单，24 条事件）

```text
【审计方独立校验】cwd=/，无 PYTHONPATH
证据包校验通过：工单 E2E-1
  已核验：清单完整性 · 事件链哈希链 · 正文与链上哈希对应 · 包摘要    退出码=0

【偷偷改掉计划正文】
证据包校验失败：问题 4 处
  - 文件内容与清单不符（疑似篡改）：清单=8c421d8a721b 实际=3ac7e84552ff
  - 文件大小与清单不符
  - 正文快照与事件链记录不符（疑似篡改）
  - 事件链记录的产物缺少正文快照                             退出码=1
```

**四条诚实边界**（写在包内 README，不可省略）：

1. 本包证明「**过程记录自洽且未被篡改**」，**不是**「代码绝对正确」
2. `pack_digest` 需**外部渠道锚定**才具抗抵赖力，否则持有整包者可整体重签
3. 权限模型是**应用层限制，不是内核级沙箱**
4. 未接入 `sequential-thinking`，推理 trace 如实标 `degraded`，**不冒充已满足**

---

### Phase 4 —— 韧性与恢复（已完成）

**双轨分工**：事件链管「发生了什么」（审计），检查点管「走到哪了」（恢复）。

```bash
PYTHONPATH=src python -m icode.cli recover --ticket <工单目录> --step plan   # 只分析，不动业务
PYTHONPATH=src python -m icode.cli recover --ticket <dir> --step plan \
    --resolve-attempt <attempt> --evidence "..." --check "人工核对：..."     # 核对后补回执
PYTHONPATH=src python -m icode.cli recover --ticket <dir> --step plan --resume  # 判定可恢复后继续跑
```

恢复决策有四种结果：

| 决策 | 含义 | 会自动继续吗 |
|---|---|---|
| `start_fresh` | 无未闭合项 | 可 |
| `resume` | 有未闭合步骤 / 只有只读动作 | 可（从事件链水合上下文） |
| `verify_side_effect_first` | 有**未终结的副作用** | ❌ **必须先人工核对真实状态** |
| `blocked` | 事件链不可读或自相矛盾 | ❌ 停下，绝不猜 |

两条不可妥协的原则（都有测试锁住）：

1. **真源是事件链，不是检查点。** 两者冲突时事件链优先，检查点被丢弃。
2. **检查点不保存模型正文。** 只存回合数 / 工具调用数 / 历史摘要；恢复时**从事件链重新水合上下文**，不回放聊天记录 —— 既不把模型正文落盘（安全），也不把对话当证据（审计）。

#### 崩溃演练（roadmap 验收项）

**① 写到一半中断**

```text
第一回合写产物 → 第二回合后端崩溃 → 检查点留下进度（turn_index ≥ 1）
工单侧：step_finished=0、artifact_written=0（未误报完成）
恢复分析 → resume（checkpoint 有效，attempt 一致）
恢复后续跑 → 登记产物 → 复检 → 终结        outcome=success
关键不变量：artifact_written=1、step_finished=1（**不重复登记**）
```

**② 副作用已发出但回执未知**

```text
开始一个 external_side_effect 动作 → 进程死亡（无 finish）
恢复分析 → verify_side_effect_first，needs_human=True，拒绝自动继续
人工核对真实状态 → resolve_open_operation() 补 finish（上游规定的正确收尾）
再分析 → 不再阻断
```

---

### Phase 5 —— 隔离升级 · WebUI · 分发（已完成）

#### 隔离：能力靠探测，不靠假设

```bash
PYTHONPATH=src python -m icode.cli doctor        # 会打印本机隔离能力与诚实标注
--isolation auto|none|bwrap|docker|podman        # 各真模型命令均可指定
```

| 平台 | 后端 | 强制什么 |
|---|---|---|
| Linux | `bwrap` | 文件系统（除工作区只读）+ **默认断网** + PID/IPC/UTS |
| macOS | `sandbox-exec` | Seatbelt profile：白名单外文件拒绝 + 默认拒绝网络 |
| 容器 | `docker` / `podman` | 仅挂载工作区 + `--network none` |
| **Windows** | **未实现内核级隔离** | **如实报告为「应用层限制，非内核级沙箱」** |

三条铁律，都有测试锁住：

1. **能力靠探测**——`probe_capabilities()` 实测本机有哪些后端，不假设。
2. **没落地就不许宣称沙箱**——无后端时 `is_real_isolation=False`，且措辞固定为「应用层限制，非内核级沙箱」。
3. **默认更严格的一侧**——无法确认按"无隔离"处理；**隔离包装失败时拒绝执行，而不是降级执行**。

> 本机（Windows）实测输出：`[WARN] 隔离后端：应用层限制，非内核级沙箱 / 后端=none /
> 未探测到可用后端（bwrap / sandbox-exec / docker / podman 均不可用）`。
> Windows 的 Job Object 只限资源不限文件/网络，AppContainer 需 Win32 组包——**本项目尚未做，所以明说没做。**

#### WebUI：只把「审批」搬到浏览器

```bash
PYTHONPATH=src python -m icode.cli webui --demo     # 仅监听 127.0.0.1
```

**命名划线**：上游的 `/icode ui` 是宿主自己的工单浏览器；我们的是执行前端，
故本仓命令叫 **`webui`** 而不是 `ui`，避免混淆。

三条硬边界（实测 + 测试双重锁）：

| 边界 | 实现 | 实测 |
|---|---|---|
| ① 不做状态第二写入者 | 不 import 控制面/契约/证据（静态断言） | 只处理审批，不写工单 |
| ② 不收路径/命令/shell | 只接受 `approval_id`（须为已知挂起项）+ `decision` 枚举 + 可选 `reason`；未知字段拒绝 | 带 `argv` 字段 → **400** |
| ③ 重启后不自动放行 | 挂起项只在内存；等待超时即拒绝 | 新进程挂起项 = `[]` |

安全细节：loopback 硬编码（无 `--host`）、写请求需同源 Cookie（`SameSite=Strict`）、
拒绝跨源 Origin、严格 JSON + 64KiB 上限、无 CDN、无内联脚本、不用 `innerHTML`。

实测边界（真实 HTTP 状态码）：

```text
GET /  下发会话 Cookie            → 200
GET /api/state 无 Cookie          → 403
GET /api/state 有 Cookie          → 200
POST 带 argv 字段（路径/命令）     → 400
POST 跨源 Origin                  → 403
POST 未知 approval_id             → 409（不猜测、不新建）
POST 错误 Content-Type            → 400
真实审批闭环：网页点「放行」→ 200，approver 返回 True
重启后挂起项：[]                  → 不会自动放行
```

#### 分发

```bash
pipx install .        # 或 uv tool install .
icode --version
```

实测（`pip install --target` 到临时目录）：包发现正常、**`web_assets/` 随包分发**、
控制台脚本 `icode.exe` 生成、从仓库外可执行；11 个子命令齐全。
（本沙箱禁止创建新 venv，故 `pipx install` 的端到端未能在此验证 —— 如实记录。）

---

### Phase 6 —— 缺口收口（四个遗留项）

#### ① 推理门禁 —— ✅ 已闭环（可验证）

上游词表规定 L2 必须由 `sequential-thinking` 机制承担。上游用 npm MCP 提供该机制；
**本仓自实现了同一机制**（`sequential.py`：有界分步推演，最少 3 步、最多 5 步）。

诚实标注：我们**不声称**调用了上游 MCP。trace 行里按词表填 `mechanism`（机制名，硬约束），
并用额外字段 `provider` / `provider_kind` 写明实现来源（上游只检必需键，不拒绝额外键）。

更关键的一条：**没真跑推演就不许写成功行**——`build_row()` 只在拿到满足下限步数的推演结果时
才给 `success`，否则一律 `degraded`。

实测（`icode chain`，真模型）：

```text
OK   plan（finish=success，前移：已前移）
OK   结构化推演 :: L2 推演 5 步
OK   推理 trace 写入 :: result=success attempted=True 推演=5步
事件链 status = plan_done          ← 整项目第一次推进到完成态
```

#### ② 完整链路 —— ⚠️ 部分闭环，已如实定位阻塞点

```bash
PYTHONPATH=src python -m icode.cli chain --workspace <dir> --requirement "..." [--only plan,review]
```

**链路顺序从状态机派生**，不写死：`plan → review → merge → code → deepcheck → audit`。
`review_manifest.json` / `*_worklist.json` 等机器产物由本仓**装配**（数据来自模型产出的
round 文件或控制面计算），不让模型手写。

| 步骤 | 状态 |
|---|---|
| `plan` | ✅ 走通：产物登记、finish success、**状态前移成功（plan_done）** |
| `review` | ⚠️ 未走通：模型读了大量文件但**没落盘** `02_review.md` / `review_round_1.json`；补救回合已触发但同回合内又遇下面的副作用歧义 |
| `merge`/`code`/`deepcheck`/`audit` | ⏳ 未到达 |

**阻塞点已定位（两条，都可复现）**：

1. **模型不落盘**：`review` 步骤里模型倾向在回复文本里给出审查意见，而不是调用 `write_file`。
   已加**有界补救回合**（明确列出缺失产物的绝对路径并要求立即写），但本轮仍未成功。
2. **副作用回执终结失败留下未闭合动作**：`operation_finish` 失败时控制面残留 open operation，
   下一次同名 start 被判 `ambiguous_side_effect` → 我们（正确地）拒绝执行。
   以前这个失败是静默的，现在会在 `inv.note`、`tool_result.meta` 与事件里显式暴露。

#### ③ Windows 隔离 —— ✅ 已落地并诚实标注

新增两条 Windows 路径：

| 后端 | 强制什么 | 说明 |
|---|---|---|
| **WSL**（`--isolation wsl`） | Linux 内核命名空间：文件系统视图 + `unshare -n` 断网 | 真隔离；但**需显式指定** |
| **Job Object**（`WindowsJobLimits`） | **仅资源**：活动进程上限、Job 内存上限、Job 关闭即回收子进程 | **部分强制**，`is_real_isolation=False`，描述里明说"不含文件系统与网络，不得据此宣称沙箱" |

**踩坑并修正**：一度只因 `wsl.exe` 存在就自动选中 WSL 沙箱，结果本机安全策略拦截 wsl.exe，
每条命令都被包进 wsl 而失败。**"存在"不等于"可用"**——现在 WSL 不进自动选择列表，
只有显式 `--isolation wsl` 才用；`doctor` 也改为分别报告"探测到可执行文件"与"实际可用"。

#### ④ 分发 —— ✅ 已用 wheel 验证

```text
构建：icode_agent-0.1.0-py3-none-any.whl（115KB）
核验：entry_points → icode = icode.cli:main
      WebUI 资源 3 个（index.html / app.js / style.css）在包内，RECORD 覆盖
       29 个模块；METADATA 齐全
安装：pip install --target <dir> <whl> → icode.exe 生成
执行：从仓库外运行 → icode-agent 0.1.0
      12 个子命令齐全（含 chain / webui）
```

`pipx install <wheel>` / `uv tool install` 走的就是这套元数据。

---

## 一个刻意的设计：门禁会拦下我们，这是对的

`icode handshake` 跑完契约后尝试状态前移，但会被门禁拒绝并列出缺口
（`thinking_gate` / `workflow_contract`）。

**我们不伪造思考 trace 去凑前移。** 探测件确实没做 L2 推理，写一行"看起来做过"的 trace
就是在造假——那正好摧毁本项目的立身之本。待补证据清单见
[上游依赖面 §4](./docs/upstream-contract.md)。

---

## 明确不做

- 通用 CLI 编码 Agent、IDE 插件、云自主 Agent、通用 Agent 框架（**四个坑已被填满**）
- 数百并行子代理、以"采纳率"为指标、用工具白名单冒充沙箱、用 LLM 投票做对抗验证
- 桌面安装包（UI 走本地 WebUI，Phase 5）

详见 [路线图 §2](./docs/roadmap.md)。

---

## 安全边界（必须如实声明）

- 当前权限模型是**应用层限制，不是内核级沙箱**。只要 Agent 能执行任意 shell，
  `fail-closed` 就仍是约定而非机制。真正隔离计划在 Phase 5，**在此之前不得宣称"安全沙箱"**。
- 密钥只存在于进程内存，绝不写入仓内任何文件；测试密钥存放于仓外。
- 事件链与推理 trace 只存摘要，不存密钥 / 正文 / 大段日志。

---

## 许可

MIT
