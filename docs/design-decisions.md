# ICODE Agent · 方案与决策记录

- 日期：2026-09-23
- 状态：**已拍板，尚未开始编码**（本文档为开工依据）
- 关联：[预研报告](./preresearch-2026-09-22.md) · [主流格局调研](./agent-landscape.md) · [开发路线图](./roadmap.md)
- 目标仓：`icode`（git@github.com:ayukyo/icode.git）

> 本文档回答「**做什么**」；**「按什么顺序做、哪些明确不做」见 [开发路线图](./roadmap.md)**。

---

## 1. 一句话定位

`icode` 是一个**独立的 AI Agent**：自带 Tool Loop，能脱离宿主（Claude Code / Codex / CodeBuddy）独立跑完 ICODE 的完整工作流。

它**单向只读消费** `icode-skill` 的流程真源与控制面，不修改上游、不复制上游逻辑。

```text
        ┌────────────────────────────┐
        │   icode-skill（子模块）     │  steps/ · gates.json · tools/
        └─────────────┬──────────────┘
                      │ 只读消费
        ┌─────────────▼──────────────┐
        │   icode  ├── core 库        │  编排 / Tool Loop / backend / 控制面适配
        │          ├── CLI 前端        │  ← 一期
        │          └── WebUI 前端      │  ← 二期（仅留接口）
        └────────────────────────────┘
```

---

## 2. 决策总表

| # | 决策项 | 结论 | 理由摘要 |
|---|---|---|---|
| D1 | 项目定位 | **独立 AI Agent 运行时**（非宿主编排器） | icode-skill 明确把 Tool Loop 留作后续；这是它唯一的架构缺口 |
| D2 | 与 icode-skill 耦合 | **git submodule**，ssh + `branch=main` + `--depth 1` | 可复现且不 fork；浅克隆因上游 `.git` 有 156MB。gitlink 记录的就是具体 commit，"跟随 main"实为**手动 bump**；**每次 bump 必须重跑上游契约冒烟测试** |
| D3 | 上游修改权 | **本仓永不修改 `vendor/icode-skill/**`，两个工程完全独立**；缺陷修复在上游仓库独立提交（如 fcntl 修复），再由本仓 bump gitlink 引用 | 保证子模块永不 dirty、依赖面可审计；提交前守护强制校验（见 roadmap §7.1） |
| D4 | UI 形态 | **CLI（一期）+ 本地 WebUI（二期）**，不做桌面安装包 | 见 §4 |
| D5 | 分发方式 | Python 包（`pipx` / `uv tool install`） | 跨平台零打包成本 |
| D6 | 实现语言 | **Python 3.11+**；**core 零第三方依赖，外围按需 extras**（`icode-agent[llm]` / `[web]`） | 与上游同栈，可直接复用 `gates.json` / 控制面；离线契约测试零依赖，LLM/网络/WebUI 按需装 |
| D7 | 代码布局 | `src/icode/`，console_script 入口 `icode` | 可安装、可进 CI |
| D8 | 跨平台 | **硬需求**，Windows / macOS / Linux 一致 | 见 §5 |
| D9 | E2E 靶场 | **双靶场**：`pycalc`（主，Python）+ `demo`（附加，C） | 主 E2E 必须能自己跑起来，见 §6 |
| D10 | 架构分层 | core 库与 UI 解耦，UI 可缺省 | 见 §3 |
| D11 | 证据包构成 | **正文快照 + 与事件链 hash 的对应表**，校验器验证 hash 匹配 | 事件链只存摘要（防泄密），审计方需正文才能核实——快照 + hash 兼顾"安全"与"可验证" |
| D12 | 交付节奏 | **每完成一个 Phase 立即自动 commit + push 一次**，提交前跑三道守护（密钥扫描 / 子模块完整性 / 测试全绿） | 自动提交没有人工把关机会，守护与 `.gitignore` 必须先行（见 roadmap §7） |

---

## 3. 架构：core 库 + 可插拔前端

**核心原则：UI 是消费者，不是灵魂。** 控制面适配、Tool Loop、backend、门禁全在 core 里，
CLI 与 WebUI 只是它的两个前端。

```text
core（纯库）
├── config         icode-skill 路径解析 / 密钥安全加载
├── control        控制面适配：step / artifact / operation / trace 回执
├── backends       模型后端抽象：fake / openai 兼容 /（后续 anthropic、本地）
├── tools          Tool Loop 的工具集：read / write / edit / grep / glob / bash
├── loop           有界 Agent 回合循环 + 副作用审批
└── steps          步骤编排：读 steps/*.md，按 gates.json 契约推进

frontends
├── cli            一期：自测、CI、无人值守
└── webui          二期：loopback HTTP + SSE，仅留接口
```

这样一期只做 CLI 就能自测并进 CI；UI 延后不阻塞任何东西，
将来想换形态（TUI / IDE 插件 / 其他宿主）也不用动核心。

---

## 4. UI 决策（已认可）

### 结论

**做「CLI + 本地 WebUI」，不做桌面安装包，UI 放在二期。**

### 理由

1. **跨平台成本**
   WebUI 天然三平台一致：本地起 loopback 服务，浏览器打开即可。
   桌面安装包要 ×3 套打包 + 签名：Windows 需代码签名证书、macOS 需 Apple 公证（开发者账号 + 年费）、
   Linux 需 deb/AppImage/rpm，还要自建更新通道。成本高一个数量级，且与 Agent 能力无关。

2. **与上游一致**
   `icode-skill` 的可选 UI 就是本地 WebUI（ICODE Manager 2.0，`127.0.0.1:8765`，明确不提供 `--host`、不开放远程）。
   理念对齐，用户认知一致，成本最低。

3. **场景适配**
   Tool Loop 要展示流式输出、工具调用、diff、审批确认——浏览器最自然。
   反过来 TUI 在 diff 与审批上体验很差。

4. **UI 必须可缺省**（见 §3）

5. **安装包有更轻的替代**
   `pipx install icode-agent` / `uv tool install` 就是跨平台"安装"。
   将来真要单文件，PyInstaller 也比 Electron 轻得多——但那是以后的事。

### WebUI 安全边界（照抄上游已被验证的约定）

- 仅监听 `127.0.0.1`，**不提供 `--host`**，不开放远程访问
- 写请求必须携带页面会话令牌
- 请求体为严格 JSON 并拒绝跨源 Origin 与未知字段
- 页面资源全部随仓提供：**无 CDN、无内联脚本、无第三方前端依赖**
- 动态内容只用 `textContent` 渲染
- 浏览器只提交「工单 ID + 动作枚举 + revision」，**不接收任意文件路径或 shell 命令**
- 不自动 commit / push / deploy / 删除工程

### 分期

| 期 | 内容 |
|---|---|
| 一期 | CLI + core；用 fake backend 跑通控制面契约握手（离线、不花钱） |
| 二期 | WebUI（loopback + SSE），复用 core，不改动核心逻辑 |

---

## 5. 跨平台硬约束

Windows / macOS / Linux 三平台一致是**硬需求**，不是加分项。以下为强制规则：

| 方面 | 规则 |
|---|---|
| 路径 | 一律 `pathlib.Path`；禁止硬编码 `/` 或 `\`；不依赖文件名大小写（Windows/macOS 不敏感） |
| 子进程 | 参数列表 + `shell=False` + `sys.executable`；**必须显式 `encoding="utf-8"`** |
| 工具链 | 禁止用 `bash` / `grep` / `sed` / `rm` / `make` 实现功能逻辑；入口用 console_script，不提供 `.sh` |
| 文件锁 | 自带锁须 `fcntl` ↔ `msvcrt` 双路，或改用单写者设计规避 |
| 换行 | 由 `.gitattributes` 统一下来，见下 |
| 临时目录 | `tempfile`，不写死 `/tmp` |
| 终端输出 | 颜色按 `isatty()` 决定；中文输出前显式设置 UTF-8 |

### 换行符处置（本机实测问题）

本机全局 `core.autocrlf=true`（`C:/Users/36584/.gitconfig`），导致：

- `git submodule add` 告警 `.gitmodules` 的 LF 将被替换为 CRLF
- **从上游复制来的 C 靶场文件在磁盘上实际就是 CRLF**（`Makefile` / `calc.c` / `calc.h` / `main.c`）

`demo/Makefile` 一旦是 CRLF，Unix 侧 `make` 会直接报错。因此：

1. 新增根级 `.gitattributes`，用 `* text=auto eol=lf` 覆盖 `core.autocrlf`
   （`core.autocrlf` 只对未声明 `text` 属性的文件生效，显式声明后即被旁路）
2. 已把 4 个 C 文件规范化回 LF（Makefile 1394 → 1360 字节）
3. 校验通过：`git ls-files --eol` 显示 `.gitmodules` 为 `i/lf w/lf attr/text eol=lf`

---

## 6. E2E 靶场

| 靶场 | 路径 | 角色 | 依赖 |
|---|---|---|---|
| **pycalc** | `tests/fixtures/pycalc/` | **主 E2E** | Python 标准库 |
| demo | `tests/fixtures/demo/` | 附加靶场（有 C 工具链才跑） | gcc + make |

**为什么双靶场**：主 E2E 必须能在任意平台自己跑起来。
`demo` 是 C 工程，跑它需要 gcc + make（Windows 装 MinGW、macOS 装 Xcode CLT、Linux 装 build-essential），
跨平台下这是最脆的一环，本机现在就装不了。

`pycalc` 用标准库 `unittest`（12 用例，已实测全绿），与 C 版能力及错误码语义一一对应，
`python -m unittest` 的**退出码**就是 Agent「验证通过」的客观证据来源。

**注意**：`demo` 里 `calc_sqrt` / `calc_isqrt` **已经实现**（上游 README 的示例需求已跑过一轮），
不能再当新需求。建议用 `calc_gcd` / `calc_lcm` 或 `calc_eval` 这类未实现且可断言的需求。

---

## 7. 密钥与安全约定

- 测试密钥存放于**仓外**：`D:\AI_CODING\ICODE测试KEY-禁止上传GIT.txt`（厂商 MiniMax，模型 MiniMax-M3）
- **密钥绝不入库**。处理方式：
  1. 只读进进程内存，不写入任何仓内文件
  2. 加载优先级：`--key-file` > `ICODE_LLM_KEY_FILE` > `ICODE_LLM_API_KEY` > 仓内 gitignore 的 `icode.local.toml`
  3. 日志与异常一律脱敏（仅前缀 + 长度），不回显完整密钥
- `.gitignore` 已兜底屏蔽 `.env` / `*.key` / `*KEY*.txt` / `*密钥*.txt` 等形态
- 模型能力已实测：MiniMax-M3 支持 OpenAI 风格 function calling（`finish_reason=tool_calls`），Tool Loop 可行；
  其 `content` 含 `<think>` 标签，需剥离后再作为正文

---

## 8. 待办（开工后）

1. 立骨架：`pyproject.toml` + `src/icode/{config,control,backends,cli}`
2. **契约握手里程碑**：用 fake backend 跑通 `step start → check → artifact → finish`，
   并用 `icode_control.py trace` 校验事件链（离线、零成本）
3. 真模型接入（MiniMax-M3）+ Tool Loop 最小工具集
4. 在 `pycalc` 上跑一条完整 E2E（如"新增 `calc_gcd`"），以 `unittest` 退出码验收
5. 二期：WebUI

---

## 9. 未决 / 风险

| 项 | 说明 |
|---|---|
| 上游仍在演进 | `icode-skill` 以 `main` 分支跟随，契约可能变动；需关注 `gates.json` 与 `steps/` 的变化 |
| 步骤 prompt 体积大 | `01_plan.md` 67KB、`log.md` 146KB，须做懒加载/裁剪，否则单步 token 成本失控 |
| 门禁 fail-closed | 缺产物 / 缺 Read / 源码漂移一律拒绝 success，Agent 需真正收集证据而非生成文本 |
| 无 C 工具链 | `demo` 靶场的验证只能降级为 `unobserved`，不得伪造结论 |
