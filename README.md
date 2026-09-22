# icode — 过程可审计的 AI 编码 Agent

> 本项目的唯一切口：**不是给 Agent 装一道审计门，而是让 Agent 本身不可撒谎。**
> 现有治理类项目的 `fail-closed` + 哈希链审计几乎都是「套在不可审计的 Agent 外面的一道门」（sidecar）；
> 我们审的是**过程**，而不是**产物**。

- 状态：**Phase 1（离线契约内核）已完成**，尚未接入真模型
- 上游：[icode-skill](https://github.com/ayukyo/icode-skill) 以 git submodule 形式只读消费（**两仓完全独立，本仓永不修改子模块**）
- 设计文档：[方案与决策](./docs/design-decisions.md) · [开发路线图](./docs/roadmap.md) · [格局调研](./docs/agent-landscape.md) · [上游依赖面](./docs/upstream-contract.md)

---

## 快速开始

```bash
# 子模块（浅克隆，约数分钟）
git submodule update --init --depth 1

# 自检（离线）
PYTHONPATH=src python -m icode.cli doctor

# 契约握手：证明 Agent 与控制面对齐（不联网、不花钱）
PYTHONPATH=src python -m icode.cli handshake --workspace /tmp/handshake-ws

# 测试（离线，零依赖）
python -m unittest
```

安装为命令后可直接用 `icode`：

```bash
pipx install .          # 或 uv tool install .
icode doctor
```

---

## Phase 1 现状

Phase 1 的目标是**在接入真模型之前，先证明我们与控制面完全对齐**，
全程离线、零成本、可进 CI。

| 能力 | 状态 |
|---|---|
| 从 `gates.json` **动态读取**步骤契约（不写死步骤表） | ✅ |
| 契约与 `steps/*.md` 的交叉一致性校验 | ✅ |
| **渐进披露**：门禁规则强制注入 + 背景知识按需加载 | ✅ 强制层占全文 **9.3%**（335K → 31K 字符） |
| 控制面适配：`step start/check/finish` + `artifact` + `transition` + `trace` | ✅ |
| **确定性幂等键**（由逻辑坐标派生，重试安全） | ✅ |
| 应用层权限模型（默认拒绝；**明确声明不是沙箱**） | ✅ |
| 离线校验：核心模块无网络导入 + socket 打瘸后仍可跑通 | ✅ |
| 真模型 + Tool Loop | ⏳ Phase 2 |
| 证据包导出 | ⏳ Phase 3 |

### 命令

| 命令 | 说明 |
|---|---|
| `icode doctor` | 环境与能力自检（离线） |
| `icode handshake --workspace <dir>` | 契约握手：跑通完整步骤契约并校验事件链 |
| `icode steps` | 列出契约登记的步骤 |
| `icode brief <step>` | 打印门禁简报（强制注入层） |
| `icode outline <step>` | 打印步骤文档章节索引（懒加载入口） |

---

## 一个值得注意的设计：状态前移会被门禁拦下，这是对的

`icode handshake` 会跑完 `plan` 的完整契约（复检 → 产物 → 回执 → 事件链），
然后**尝试**状态前移。对一个只有产物、没有真实推理证据的探测件，
门禁会拒绝前移并列出缺口（`thinking_gate` / `workflow_contract`）。

**我们不伪造思考 trace 去凑前移** —— 这恰恰是「过程可审计」在起作用。
待补证据清单见 [上游依赖面 §4](./docs/upstream-contract.md)。

---

## 明确不做

- 通用 CLI 编码 Agent、IDE 插件、云自主 Agent、通用 Agent 框架（**四个坑已被填满**）
- 数百并行子代理、以"采纳率"为指标、用工具白名单冒充沙箱、用 LLM 投票做对抗验证
- 桌面安装包（UI 走本地 WebUI，Phase 5）

详见 [路线图 §2](./docs/roadmap.md)。

---

## 安全边界（必须如实声明）

当前权限模型是**应用层限制，不是内核级沙箱**。
只要 Agent 能执行任意 shell，`fail-closed` 就仍是约定而非机制。
真正的隔离计划在 Phase 5 落地，**在此之前对外不得宣称"安全沙箱"**。

- 密钥只存在于进程内存，绝不写入仓内任何文件；测试密钥存放于仓外
- 事件链与 trace 只存摘要，不存密钥/正文/大段日志

---

## 许可

MIT
