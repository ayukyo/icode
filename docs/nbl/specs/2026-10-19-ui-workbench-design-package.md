# UI 工作台设计包规格（2026-10-19）

**状态**：v1（§14 UI 产品设计的第一包落地物）。继承 `docs/icode-agent-product-architecture.md` §14（14.1–14.16 全部条款）；与既有 R0/R1 资产（`src/icode/web_assets`、`src/icode/workbench_assets`，无 CDN/无内联脚本纪律）方向一致，但本包为**设计规格 + 静态原型**，不改动运行时资产。

## 1. 落地物

| # | 交付 | 位置 |
|---|---|---|
| D1 | 设计规格（本文档）：信息架构落地、组件清单、状态翻译词表 v1、i18n 键约定、接口边界对应、无障碍清单 | `docs/nbl/specs/2026-10-19-ui-workbench-design-package.md` |
| D2 | 静态原型：单工程工单工作台（工单列表 + 当前工单 + 用户行动区），零 JS、零 CDN、纯 HTML+CSS，`<details>` 承载双层信息架构 | `docs/ui/workbench-prototype.html` |

## 2. 信息架构落地（§14.2/14.5/14.10）

- **工单工作台优先**，聊天只是工单内沟通入口：原型以"列表 + 当前工单 + 行动区"三栏布局为主干。
- **双层信息架构**：默认层用业务语言；"技术详情"用 `<details>`（原生折叠，无 JS）承载同一份底层数据（原始步骤、diff、命令与退出码、模型与工具、事件链与证据包入口）——事实只能折叠，不能删除或改写。
- 四个布局问题（现在什么状态 / 是否需要我处理 / 为什么阻塞 / 下一步是什么）在状态卡与行动区逐一落位。

## 3. 状态翻译词表 v1（§14.11，后端输出、前端只渲染）

| 控制面状态 | zh-CN | en-US | 辅助状态（示例） |
|---|---|---|---|
| create/init | 已提交 | Submitted | — |
| plan | 正在理解需求 | Understanding request | — |
| review | 正在检查方案 | Reviewing plan | 等待用户确认 / Awaiting your confirmation |
| merge | 方案准备完成 | Plan ready | — |
| code | 正在处理 | Working | — |
| deepcheck | 正在全面检查 | Running full checks | — |
| audit | 正在整理交付结果 | Preparing delivery | — |
| completed | 已完成 | Completed | — |
| blocked | 需要补充信息 | Information needed | 缺少：… / Missing: … |
| approval required | 需要你确认 | Confirmation required | — |
| failed | 处理未完成 | Not completed | — |

规则：展示模型 = 控制面原始状态 + 用户可见阶段 + 辅助状态三段；状态不得仅靠颜色表达（图标 + 文字 + 行动提示）；映射由后端版本化输出，前端不做字符串猜测。

## 4. i18n 键约定（§14.4）

- locale：`zh-CN` / `en-US`；键名 `workbench.<area>.<element>`，例：`workbench.ticket.status.review`。
- 回退：当前语言 → 英文 → 简体中文；缺失键记录可观测告警，不显示资源键名。
- 工单正文/代码/日志保持原文不翻译；界面语言与工单沟通语言是两个字段。
- 原型用 CSS 双语言区块演示切换；实现期由后端映射契约驱动。

## 5. 接口边界对应（§14.14）

原型标注四类接口的落点（仅示意，不实现）：

- Ticket Query：列表/详情只读；
- Ticket Intent：`＋新建工单`、审批按钮（`approval_id + decision + reason`）、暂停/继续/切换执行方式（只提交枚举意图 + 幂等 request ID）；
- Event Stream：当前进展/状态变化；
- Evidence：验收记录（R7 后含签名与锚定状态行）与技术详情导出入口。

浏览器禁止事项（§14.14）全部适用于实现；原型不含任何网络调用。

## 6. R7 对齐点

完成页"验收记录"区新增三行事实（来自证据包 manifest/signature）：

- 包摘要 `pack_digest`（前 16 位展示，点击展开完整值）；
- 签名状态：已验签（Ed25519）/ 未签名（证据力受限）——照实展示，不冒充；
- 外部锚定：`anchor/<digest前16>` git tag（外部可核查）。

未验证边界与成功项同等可见（§14.13）：自动检查通过 ≠ 生产环境已验证。

## 7. 无障碍与视觉（§14.15）

- 浅色中性企业风格；大状态清晰；不用终端风；
- 状态用图标+文字+阶段，不依赖颜色单通道；
- 全部交互元素有可见焦点与语义标签（原型用原生元素：button/details/summary/label）；
- 错误信息 = 发生了什么 + 下一步怎么做。

## 8. 验收判据

- 原型为单文件、零 JS、零 CDN、零网络调用（源码无 `<script`、无 `http://`/`https://` 资源引用——文本内容中的 URL 除外）；
- §14.5 布局四问题、§14.11 状态三段模型、§14.12 审批文案（允许本次执行/暂不允许）、§14.13 完成页与未验证边界、R7 三行事实全部可见；
- 双层信息架构完整：默认层无内部步骤名/退出码等术语裸露（都在 `<details>` 内）。
