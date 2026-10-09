# 工作台 Python 测试预设上游复核

观察日期：2026-10-09 09:26–09:28 Asia/Shanghai；root 分支复核时点 01:28:28 UTC。ICODE 基线 `6ded1d3c16c265fda16fa6506cb57c29067b5fbd`。这是独立只读研究和设计输入，不是 ICODE 实现、测试或原生验收证明。

## 来源与读取范围

- Aider main：`5dc9490bb35f9729ef2c95d00a19ccd30c26339c`，提交时间 2026-05-22T14:02:20Z，未归档。独立研究读取 args 510–580、main 1020–1090、commands 965–1045；root 定点回读 args 548–563，并完整读取 [Apache-2.0 许可证](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/LICENSE.txt)。没有声称全文阅读该仓库或三个源文件。
- Codex main：`0ada5d8806cdad498230d5b1b2924091e04c8feb`，提交时间 2026-10-09T01:22:30Z，未归档。独立研究读取 loader 75–145、1098–1285、1700–1795，exec_policy 210–238、337–465、660–719，config 3770–3810、4138–4205；root 定点回读 loader 85–102、1113–1180，并完整读取 [Apache-2.0 许可证](https://github.com/openai/codex/blob/0ada5d8806cdad498230d5b1b2924091e04c8feb/LICENSE)。没有声称全文阅读所有源文件。
- root 独立读取两仓库 branch 元数据，确认上述 SHA；研究时 Codex 已从先前 `b6e8a2e207e5591780061c62c50df417670f8d75` 前进。独立研究核 [固定比较](https://github.com/openai/codex/compare/b6e8a2e207e5591780061c62c50df417670f8d75...0ada5d8806cdad498230d5b1b2924091e04c8feb) 的 29 个文件名和相关 loader/许可证未变；不是 29 文件的全文代码审查。

## 结论与本项目映射

1. 采纳显式测试预配置。Aider [args 548–563](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/args.py#L548-L563) 的 test-cmd 默认空、auto-test 默认关闭；[main 1056–1063](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/main.py#L1056-L1063) 在显式测试但无命令时失败。ICODE 已有 plan provider 与验证执行链，本片由可信 CLI 启动者选择固定 unittest argv，不猜项目命令。收益是缩小配置步骤与信任歧义，成本是只覆盖可由宿主 Python 发现的测试；验收默认不变、未知预设拒绝、无自动模式前置拒绝与真实接线。
2. 暂缓任意测试命令。Aider [commands 993–1044](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/commands.py#L993-L1044) 接受字符串或 callable 并把失败输出回送模型；不能据此让项目或模型在 ICODE 中取得新的执行权限。当前无新 shell/callable/provider 注册、环境注入或依赖安装；通用预配置需独立设计。
3. 采纳项目配置与可信执行授权分离。Codex [loader 85–102](https://github.com/openai/codex/blob/0ada5d8806cdad498230d5b1b2924091e04c8feb/codex-rs/config/src/loader/mod.rs#L85-L102)、[1113–1180](https://github.com/openai/codex/blob/0ada5d8806cdad498230d5b1b2924091e04c8feb/codex-rs/config/src/loader/mod.rs#L1113-L1180) 中，不可信项目配置层被禁用；项目层 sanitizer 对受信项目也剔除端点、模型提供方、notify 等 denylist 项，不能简写为“只有不可信项目才过滤”。ICODE 本片不读取项目配置来选解释器/命令/模型端点。验收绝对 lexical sys.executable 原样、启动及构造窗口身份漂移拒绝、同次执行 code/deepcheck 复用原 Plan。
4. 采纳能力不足时拒绝，不借用上游批准规则。独立研究核 Codex [exec_policy 394–460](https://github.com/openai/codex/blob/0ada5d8806cdad498230d5b1b2924091e04c8feb/codex-rs/core/src/exec_policy.rs#L394-L460) 与 [config 4151–4202](https://github.com/openai/codex/blob/0ada5d8806cdad498230d5b1b2924091e04c8feb/codex-rs/core/src/config/mod.rs#L4151-L4202)。ICODE 继续依现有 resource/Reviewer/tree/CP 门拒绝；不引入 prefix allow 绕过、持久授权或原生 fallback。macOS/Windows 不因配置预设而取得工程准入。

以上只借鉴机制，不复制源码。两许可证为本次完整读取的 Apache-2.0；无新第三方代码、依赖或权限。旧[工作台预研](2026-10-09-r3-workbench-verification-research.md)的 args 537–547 链接指向 lint 区域，本次明确以 548–563 为测试选项证据，保留旧日期，不改写历史。

独立研究与 root 设计核对发现：既有 provider 每步构造会重新观察身份；新内置 provider 必须仅在同次 execute 内固定第一次工程 Plan，并保持任意第三方 provider 的原调用语义。此项仍需设计/计划双审、实际 TDD 与关联回归；源码观察不替代其验收。

研究全程不写源码、不运行测试、不访问 KEY/私有模型配置、不请求模型 HTTP；独立研究已停止。下一次主阶段开始/结束刷新相关条目，并按持续对照约定定期复核名单。
