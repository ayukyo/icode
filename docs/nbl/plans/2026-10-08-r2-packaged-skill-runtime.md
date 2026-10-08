# R2 pip安装的固定SKILL运行资源闭包

> REQUIRED SUB-SKILL: nbl.test-driven-development、nbl.subagent-driven-development。当前为正式调查/实施前设计；候选资源清单不算已证明完整闭包。先完成正在实施的CLI恢复及共享预算片，再执行包内资源接线；不得并发改同一调用链。

**Goal:** 干净Python包安装后，无源码checkout、外部SKILL配置、用户Skill或运行时下载也能进入doctor及工单工作台，并消费同一固定ICODE-SKILL控制面。

**Architecture:** 构建时从固定gitlink只读提取必要运行资源，保留原布局、原字节和许可，wheel内解包为稳定只读资源目录；运行时定位包内默认来源。不复制实现逻辑、不另造CP或自动clone最新源码，不用PPT模板授权不明资源补充功能。

## 三问及实体基线

2026-10-08主代理隔离构建wheel、干净venv pip --no-deps安装，在临时cwd/-I/无ICODE_SKILL_ROOT下实际find_skill_root返回ConfigError。独立只读审查确认config只查外部显式/env/local/vendor/sibling/home、setup/MANIFEST无SKILL运行资源，doctor/workbench先load_settings，README仍clone子模块+editable；Skill独立install.sh不是Agent的pip fallback。已有安装API验收显式消费开发仓SKILL，不能称新机独立安装。

现有运行依赖通过Settings.control_script/gates_json/steps_dir、ControlPlane、ReasoningGate及CP动态inspection/linter加载；全部复用。构建与运行入口变化影响setup.py、MANIFEST/包数据、config.py、资源清单和安装/源码归属测试，不改vendor子模块或契约源。

## Task 1: 固定资源与许可闭包

- [ ] 完成
- [ ] 固定gitlink `b74c4c40f2246a6c4eea77e494dd57c642f3a9a3`、工作树/文件身份、原LICENSE及每个member hash；显式allowlist，不用全仓递归打包，也不从model/project输入路径选择资源。
- [ ] 审核候选：SKILL/LICENSE、schemas/steps/references、tools/icode_control.py与inspection_worklist.py/3lint脚本、workflow/reasoning/cheap-research gates。独立初步候选72tracked regular、1,922,179字节、0symlink只是候选；还须实际核对动态导入、lint数据、工作台和各catalog索引所需资源，不能先声称90%能力一致。
- [ ] 原字节/布局保留，不在打包时悄改gates或source。缺失、symlink/路径逃逸、摘要失配拒绝构建/定位；构建来源/成员/版本manifest与许可清单一并入包。sdist必须含同样闭包，脱离git构建也能验证，不能只在源码wheel成立。
- [ ] 禁止分发第三方PPT template.pptx/preview.png与无许可资产；MIT代码/元数据与受限素材分别处理，保留作者声明。包内无需runtime联网提取最新Skill，也不把zip解压到用户全局skills目录。

## Task 2: 默认来源及解释器边界

- [ ] 完成
- [ ] config新增明确包内来源，开发子模块/显式外部配置保持兼容；默认安装不靠当前工作目录补足资源。包内缺失/验证失败不得静默降成不完整源或裸运行，错误稳定且给普通用户可执行说明。
- [ ] 真实核对catalog中的python3命令和CP linter执行：Windows/非PATH pipx venv不能依赖系统同名解释器。先查已有可信接口；没有兼容接口时另定最小源码/上游契约变更，不生成不安全shell shim或篡改固定字节。Settings.python与资源root必须贯穿实际子进程。
- [ ] 资源只读，工单及checkpoint仍只写任务目录；并发实例不修改包数据，不制造全局安装状态。显式外部Skill是原高级能力，不将它冒称包内来源。

## Task 3: 真正安装验收

- [ ] 完成
- [ ] RED→GREEN：无外部源码/环境/用户Skill、-I、临时cwd、实际installed module字节归属；不只运行--help或mock load_settings。
- [ ] 直接wheel及脱离checkout的sdist重建wheel，独立比对manifest/成员字节/许可排除，pip --no-deps安装后实际doctor、步骤索引、handshake、CP三linters和状态转换、workbench真实建单/查找/列表/中英入口。doctor隔离分仍如实展示未通过，不用readonly UI等于auto ready。
- [ ] 新矩阵20轮、本机关联config/control/workbench/契约/evidence、独立SPEC→QUALITY、7维自检、完整preflight及compileall≤j6、治理/官网/竞品/diff；然后main提交推送、跨平台原生安装CI。Windows x64/ARM64与mac Intel/Apple Silicon都必须实际无外部Skill，不以Linux安装或skip替代。

## 取舍与未覆盖

本片只闭合现有工作流资源的分发和定位，不解决Windows正式启动/UAC/WFP或macOS单任务配额；不发布未测完整R2/自动模式。Git/构建工具链、可选Office素材与安装脚本不是被打包即可宣称所有能力已覆盖，相关前置及缺项需实测和另片处理。

观察2026-10-08：ICODE-SKILL固定gitlink根LICENSE为MIT；主代理完整读tools/ppt/NOTICE及[第三方素材当前NOTICE](https://github.com/lmori1301/Agent-PPTSkill/blob/main/NOTICE.md)，模板仅学习研究/非商业限制明确，不套用根MIT。采纳固定资源与许可边界；不适配无筛选vendor打包/移除署名/运行时拉main。独立研究不改变素材授权，也不替代实际安装测试。

**Execution Mode:** serial implementation, independent read-only research/reviews

## 独立实施前审查与已授权前置

独立审查复算72候选的组成为2根文件、3catalog、28references、7schemas、27steps、5tools，数量/字节/普通文件性一致；动态inspection与三lint源在内，但steps仍引用未含Office/TB/study工具，因此不得称整个SKILL能力闭包。无写实体负控：绝对Python启动CP、仅该子进程PATH为空，三gate均fail_closed且实际尝试python3；无现成解释器参数/环境接口。进程局部C locale且关闭UTF8模式时，action-policy缺路径失败产生UnicodeEncodeError/stdout空；-X utf8同命令返回合法ok:false JSON。

主代理已核对本机上游最新 `74473e5`（工作树干净）仍同一python3执行机制，不能假设新版本已修复。2026-10-08用户已明确授权最小ICODE-SKILL三lint当前解释器/UTF8及对应测试修改，验收后上游main提交推送，再更新本工程固定gitlink。上游在独立目录实施、独立审查；当前CLI冻结验收仍使用原gitlink，不并发改vendor。其它已授权CLI/shared预算工作继续，不能用PATH shim/运行时monkeypatch绕过这个前置。
