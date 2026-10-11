# Windows PE目录实际消费 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement task-by-task. 用户已指定main直接阶段发布及自主继续，覆盖默认工作树/逐阶段等待；实现者不自行commit/push，主代理完整门禁后发布。

**Goal:** 在实际Windows签名前采集中完整检查ordinary、delay及所有manifest，产生绑定原bytes摘要的窄范围回执。

**Architecture:** 复用PeImage严格RVA映射，新目录层无I/O；capture读取同一raw快照并先核摘要，再调用目录层。三个生产验证标志保持false，任何目录/预算错误不生成成功回执。

**Tech Stack:** Python标准库struct/dataclasses/hashlib/ElementTree、unittest、现有Windows四格CI；编译j1。

---

基线main `e525cda9edebd03961b062f0f5c8b493309f4772`，vendor `21566a5`。完整目录与预算合同见 [已双审设计](../specs/2026-10-11-windows-pe-directories-design.md)，所有要求均为必需项，不用容错前缀替代。

## 文件与责任

- `scripts/windows_pe_directories.py`：纯bytes目录层及封闭固定错误，不改原PeImage/public machine API。
- `tests/test_windows_pe_directories.py`：完整合成PE bytes、双架构、资源及XML负控；不mock目录读取。
- `scripts/probe_windows_pe_capture.py`：同raw摘要绑定、schema2与窄scope计数/manifest摘要回执。
- `tests/test_windows_pe_capture.py`：helper改为完整有效PE夹具，外部Windows工具继续已有边界隔离；工具样本仍opaque。
- `scripts/run_workspace_ci.py`、`tests/test_run_workspace_ci.py`：目录模块在跨平台DEFAULT中恰一次，不隐含平台跳过。
- `tests/test_ci_workflow_contracts.py`：只在确有接线合同需要时修改，保留已有四格capture调用。

## Task1：纯目录层

**Dependencies:** None
**Parallelizable:** No（后续capture依赖返回记录；只有独立只读研究并行）

- [x] 完成任务及SPEC/QUALITY自审。
- [x] 先写真实完整PE字节测试；缺实现以接口存在断言失败，而非导入错误。

```python
module = importlib.util.find_spec('scripts.windows_pe_directories')
self.assertIsNotNone(module, 'PE directory interface is missing')
```

- [x] 执行RED：`./.venv/bin/python -m unittest tests.test_windows_pe_directories -v`；记录明确missing接口失败。
- [x] 实现固定接口及不可变记录，所有目录规范、预算、manifest语义严格按设计。基础PeFormatError原样传播，不catch成空结果。

```python
result = inspect_directories(image, expected_arch='x64')
self.assertEqual(result.architecture, 'x64')
self.assertTrue(result.manifests)
```

- [x] 对ordinary/OFT0/ordinal、delay resolver、全部资源、零payload、跨section、所有预算和全部XML安全边界逐项RED→GREEN；命令同上，须0失败0错误0跳过。
- [x] 回归：`./.venv/bin/python -m unittest tests.test_windows_pe_reader tests.test_windows_pe_directories -v`；头部层接口/错误与原bytes不变。
- [x] 独立SPEC源码审查通过后独立QUALITY；发现项修复重新跑真实bytes测试。

## Task2：真实capture消费及闭集schema

**Dependencies:** Task1
**Parallelizable:** No（只派一个写入者，不与Task1并行改源码）

- [x] 完成任务及双审。
- [x] 在capture测试先添加schema2/static_directory_check与A→B→A负控；先RED再改capture。helper夹具为真实完整manifest PE，工具PE仍原轻量machine合同。
- [x] capture在三个初始摘要后执行以下顺序，raw不再次读取替代：

```python
raw = _read_regular(helper, _IMAGE_LIMIT)
if hashlib.sha256(raw).hexdigest() != digests[0]:
    raise RuntimeError('PE bytes changed during capture')
static = inspect_directories(raw, expected_arch=architecture)
```

- [x] schema2新增固定scope `imports_delay_manifest`、complete true、同helper_sha256、ordinary/delay模块与符号数、resource/manifest数、每manifest sha256及全部固定level语义通过标志；不得输出DLL/符号/XML/resource路径。parse_complete/runtime_load_verified/source_launch_verified仍false。
- [x] 端点摘要重读、私有输出目录清理、opaque工具samples和总32768B预算保留；schema1不与schema2混用。
- [x] RED与GREEN命令：`./.venv/bin/python -m unittest tests.test_windows_pe_capture tests.test_windows_pe_directories -v`。A→B→A是实际中间raw与原摘要不同导致固定拒绝，无成功回执，不mock解析器。
- [x] 接线先RED：DEFAULT新模块缺失；再新增恰一次模块和对应无skip合同。

```python
self.assertEqual(DEFAULT_MODULES.count('tests.test_windows_pe_directories'), 1)
```

- [x] 回归命令：`./.venv/bin/python -m unittest tests.test_run_workspace_ci tests.test_ci_workflow_contracts tests.test_windows_pe_reader tests.test_windows_pe_directories tests.test_windows_pe_capture -v`。

## Task3：成品证据与发布

**Dependencies:** Task1, Task2
**Parallelizable:** No（同SHA实跑在本地门禁/发布之后）

- [x] 两独立审查源码合并范围，分别SPEC与QUALITY，无Critical/Important残留。
- [x] `./.venv/bin/python scripts/preflight.py` 完整三道通过；新源码不能沿用旧文档阶段preflight。
- [x] governance/site/landscape检查及`git diff --check`通过；研究刷新只记录有日期/版本/许可/链接的真实核对，不把研究当运行证据。
- [x] 主代理精确stage文件，核cached diff/secrets/submodule，通过才commit/push main，核ls-remote完整SHA。
- [x] 同SHA x64/ARM64×Python3.11/3.12实际Windowscapture新schema/static_directory_check完整成功；只读观察每格实际日志，不用安装签名成功倒推目录解析。
- [x] 四格均未失败；保留全部检查门，不把旧样本或本地合成bytes叫Windows成品。
- [x] 更新阶段证据矩阵：本静态阶段可verified，整体验收继续partially_verified；可信启动/加载、网络、Reviewer和真实模型六步分别仍需闭合。

## 当前履历

Task1已实现、冻结且独立SPEC/QUALITY各C0/I0/M0。主代理完整核目录基础层、capture及跨平台选择器调用链；Task2交新独立实现者继续，源码写入串行。独立只读Agent对照研究已返回；没有上游源码复制或新权限。本文不是成品Windows完成证明。

实现者已报告首轮15项RED均为missing callable断言失败、无导入错误；后续初步GREEN含既有reader共53项。还在补精确预算及截断/终止负控并自审，独立SPEC预审进行中；这不是Task1最终门禁或Windows运行证据。宿主绑定授权范围另重跑4项控制面/证据包契约，通过，无重复vendor修改。

Task1终态：SPEC预审发现I1：逐项读允许跨相邻section拼ILT/INT/字符串；五实际bytes负控先RED后以整体单区域映射拒绝修复。另BOM-less UTF16被XML二次探测接受，真实bytes测试先RED、decode后拒绝NUL后GREEN。实现者与主代理reader+directories各62项通过0skip；SPEC独立目录29项，QUALITY独立62项，均0失败/错误/跳过。固定理由/原基础错误、所有预算精确边界、全部资源/manifest及冻结原bytes通过；不授capture/Windows/总门。

Task2终态：旧schema、A→B→A未拒绝、违规第二manifest/预算未拒绝及DEFAULT缺模块先RED；消费与接线后实现者137项通过0skip，主代理包含bootstrap工作流顺序共138项通过0skip。全片SPEC独立115项、QUALITY独立103项，均0失败/错误/跳过，C0/I0/M0。初次普通diff未覆盖尚未跟踪目录测试；精确stage后cached检查发现EOF多余空行，原实现者只修格式再跑29项通过，cached/worktree检查随后通过。完整preflight运行中，期间只有该EOF格式变化而无语义源码修改；结束后再核最终索引。官网/governance/观察排期通过，未声称20上游全刷新。尚未发布本代码片，Windows新scope待同SHA实跑。

## 验收矩阵与自检边界

acceptance_contract：Task1+Task2为真实bytes有限目录层与CI capture实际调用的本地实现片；静态成品还必需四Windows格同SHA schema2消费。它不包含生产加载/来源认证、网络拒绝或Reviewer权限，不替代整体R2/R3门。

| 层 | 必需 | 当前证据 | 结果 |
| --- | --- | --- | --- |
| pure bytes / unit | 是 | 全目录、预算精确边界、跨section、全部manifest及XML正负控，62项 | pass |
| local capture consumption | 是 | 不mock parser、真实完整PE fixture、A→B→A、schema2及DEFAULT，root138项 | pass，外部Windows工具仍隔离夹具 |
| independent reviews | 是 | SPEC115项、QUALITY103项，各C0/I0/M0 | pass |
| full repository gates | 是 | 新片完整preflight于06:53 UTC终态0、三道通过；治理/官网/排期/cached格式通过 | pass |
| actual Windows artifact | 是 | `2e8fe1c` 四格实际 schema2/新scope日志完整核对，详见发布后窗口 | pass，仅有限静态消费 |
| whole PE / load / trusted launch | 另有总门 | 原三个false保留 | 不授信用 |

negative_evidence：首轮missing API、跨区域拼接及无BOM再探测、旧capture缺snapshot检查均经RED暴露，不能删历史；旧opaque工具样本不证明目录内容。gaps：生产加载/可信启动、其它R2/R3门。verdict：本片有限静态检查与成品消费 verified；整体 R2/R3 仍 partially_verified，不能扩大到完整 PE、动态加载或自动模式。

【架构级自检报告】

- ✅ 语法/编译：单进程Python编译及本地回归通过，未新增原生编译。
- ✅ 依赖/调用链：capture→同raw摘要→目录层→PeImage及DEFAULT接线通过，四格实际Windows消费已核。
- ✅ 逻辑/边界：所有预算/终止/全部manifest及中间替换负控已覆盖。
- ✅ 异常处理：受测固定目录理由、基础错误原样传播、cleanup与CLI固定错误通过，不称未知异常全覆盖。
- ✅ 关联模块：既有reader/machine与工具opaque样本合同保留，无workflow修改。
- ✅ 兼容安全：schema明确升2；无新增依赖/权限/生产准入，原三个false不变。
- ✅ 可运行性：本地138项、两独立验证及源码发布前完整全仓门通过；四格Windows有限静态检查通过，不报告整体100%。

2026-10-11 06:53 UTC完整preflight返回0，密钥扫描、子模块完整性、全量unittest全部通过；脚本不提供测试数量，不从远端旧SHA补造本机计数。上述“运行中”保留为早期窗口。提交前再跑最终138项、语法及精确索引/secret/submodule检查；本片九文件发布门通过后由主代理提交推送并核远端main，实际Windows仍必需后续同SHA消费。

### 实施阶段开源Agent复核

2026-10-11独立只读核Codex HEAD `8c0f7011674145da7e10627769fb221c74fbf7a0`（06:08:41 UTC、Apache-2.0），主代理另打开固定源码核对。[helper manifest测试](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/tests/helper_manifest.rs)用资源API读取setup成品ID1；[Windows音频DLL打包检查](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/third_party/voice/windows_runtime.py)有限制静态子集和拒绝机制，后者不是sandbox helper全目录证明。采纳成品与支持子集明确化，暂缓资源API交叉核验与动态加载，不适配ID1代全部、字符串匹配代XML或tool文本代raw完整性。ICODE复用现有PeImage，收益为少漏成品边界，成本仍本片原定纯标准库与四Windows格；无代码复制/新许可依赖/权限。验收为所有ID/语言恶意manifest负控、同raw摘要绑定、窄scope回执；不是ICODE运行证明。旧cc7ba条目保留历史时间，20观察名单不在本片全刷新。

---
**Execution Mode:** serial

## 发布后实际 Windows 消费窗口

发布提交为 `2e8fe1c629e2724b91c5287095b3f9495b115122`，主代理核远端 main 一致。签名前采集工作流 [38119598986](https://github.com/ayukyo/icode/actions/runs/38119598986) 的 validate 已成功；不能由此推导四格成功。

首个独立核验成品：[x64 / Python 3.11 job 114412922340](https://github.com/ayukyo/icode/actions/runs/38119598986/job/114412922340) 已终态 success。root 直接读取该 job 完整日志，从实际 capture JSON 提取公开摘要与计数，不输出原样工具样本：schema_version=2，scope=`imports_delay_manifest`，complete=true，ordinary=1 module/71 symbols，delay=0/0，resource=1，manifest=1。helper SHA256=`d3723b5001ad8de97536a7e8952da0bb8a46c57ee7bd0f32ad51b49afae2b93f`，与 static_directory_check.helper_sha256 相同；manifest SHA256=`4bb79dcea0a901f7d9eac5aa05728ae92acb42e0cb22e5dd14134f4421a3d8df`，两个全部 manifest 语义标志 true。parse_complete/runtime_load_verified/source_launch_verified 三项仍 false。

该格是实际成品静态有限范围消费证据，不是安装签名成功的推断；其余三格仍待实际回执，不授四格或总阶段通过。并行主 CI 两 Windows Reviewer 已失败，观察到等待超时且无匹配拒绝事件，不能拿本片静态目录成功抵消网络硬门。

随后另两格已终态 success 且 root 直接核 capture JSON。共同字段为 schema2、同 scope/complete、delay0/0、resource1/manifest1、manifest SHA256 与首格相同、两个 manifest 语义标志 true、三个生产标志 false；每格 helper 摘要与其 static_directory_check 摘要相同：

| 实际 job | 架构/Python | ordinary 模块/符号 | helper SHA256 |
| --- | --- | --- | --- |
| [114412922345](https://github.com/ayukyo/icode/actions/runs/38119598986/job/114412922345) | ARM64/3.12 | 1/68 | `2d592dd25791bebc998e3adeb5458a3a35a1904ad6a4a8b2632b405c35a9e0a3` |
| [114412922359](https://github.com/ayukyo/icode/actions/runs/38119598986/job/114412922359) | x64/3.12 | 1/71 | `319843bc8c815bc79e868eec90abe7cc24ad368fa11e9997335b6f2c37db184e` |

当前已核 3/4，ARM64/3.11 job114412922381 仍在 build-only verifier 阶段；保持四格 checkbox 未完成，不将三格扩大为完成。上述“其余三格待”是首格观察时的历史窗口。

主 CI [38119599021](https://github.com/ayukyo/icode/actions/runs/38119599021) 已终态 failure，44 jobs 为39成功/2 Windows Reviewer失败/3条件跳过，不再轮询该终态。root 直接核两个全量 job [114411407406](https://github.com/ayukyo/icode/actions/runs/38119599021/job/114411407406)、[114411407430](https://github.com/ayukyo/icode/actions/runs/38119599021/job/114411407430) 日志：各2580 tests，OK，71 skipped；跳过不记通过，实际执行2509项。此全量结果不抵消独立 Reviewer job 失败，也不能替代本地文档发布前的完整门禁。

最后 [ARM64 / Python 3.11 job114412922381](https://github.com/ayukyo/icode/actions/runs/38119598986/job/114412922381) 已全步骤终态 success，root 直接核实际 capture JSON：schema2、同 scope/complete、ordinary1/68、delay0/0、resource1/manifest1，helper SHA256=`e5a675e5ba5fe7f2edf55f5c4c2597bc84cad5072dbed216a5f6c118fdf9e20a` 与 static check 相同；manifest SHA256 同上，两 manifest 语义 true，三个生产标志 false。至此同源码 SHA 四格实际成品消费全部核验，静态检查子阶段闭合。前述 pending 为历史观察窗口，不删除或当作当前结论。文档发布前本地完整 preflight 已启动，尚需该进程终态通过，不能拿远端全量或源码发布前旧门禁代替。

文档发布终检：同一本地完整 preflight 进程已退出0，密钥扫描、子模块完整性、全量unittest三道全部通过；脚本未提供数量，不编造本机测试数。四格实际JSON另自动核12字段闭集、同helper摘要、manifest计数及三个false。四文件文档一致性连续两轮0疑似项，治理/站点/观察排期/精确索引格式检查通过；新研究稿独立只读复核后收紧“捕获所有源变异”的过强表述。完整门禁后仅追加本结果记录，无运行代码变化。本片仅记录既有源码成品验收与未获选研究，不新增权限、依赖或生产准入，主代理按既定main流程发布。
