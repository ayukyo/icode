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
