# Windows Offline Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 在 Windows x64/ARM64 wheel 中提供无需用户编译器或在线服务的只读来源验证。

**Architecture:** 固定 sigstore-go 的薄原生程序内嵌可信根，Python 包内适配器只解析固定回执。已有 transport/check 和 gh CI oracle 保留；来源验证不授予执行权限。

**Tech Stack:** Go 1.27.1 / CGO disabled、sigstore-go v1.3.0、Python 3.11+、现有 Windows provenance CI。

## Task 1: 离线原生验证内核

**Dependencies:** None
**Parallelizable:** No (单一写入者，密码学与语义合同紧密关联)

- [x] 在 `native/provenance` 建立独立 Go module、内部验签函数与固定 CLI，测试文件先行。
- [x] 观察真实签名 fixture 正例在尚未实现的内核上 FAIL，不接受导入错误或下载失败作 RED。
- [x] 实现设计中的身份、认证时间、SCT、proof 和 statement 验证；固定输出，不执行 helper，不在线获取根。
- [x] 真实签名正例与错摘要/身份/签名/缺 proof 负例通过；严格生产 identity、输入上限、畸形/trailing JSON 和错误脱敏回归通过。
- [x] `GOMAXPROCS=6 CGO_ENABLED=0 go test -p 6 ./...`、`go vet -p 6 ./...`、x64/ARM64 交叉构建均通过；交叉构建不冒充原生运行。
- [x] 逐项规范自审、独立规范审查和质量审查无遗留阻断；根来源、许可证和依赖闭包记录可复核。

## Task 2: 随包 staging 与只读 API

**Dependencies:** Task 1
**Parallelizable:** No (依赖内核稳定 wire 合同)

- [x] 先补 `tests/test_windows_wheel_packaging.py` 与包内 API 的失败测试，覆盖架构、缺失/损坏/链接资源、source SHA、RECORD 和纯 wheel 无残留。
- [x] 将明确 CI 构建的 verifier 及许可/source 元数据接入 `scripts/windows_wheel.py`、`setup.py`、`MANIFEST.in` 和 `scripts/check_windows_wheel.py`；unsigned synthetic 旧测试保持兼容。
- [x] 在独立 `src/icode/windows_provenance.py` 提供只读固定结果 API，定位只允许包内 matching architecture，无 PATH、cwd、用户根或 identity 回退。
- [x] `.venv/bin/python -m unittest tests.test_windows_bootstrap tests.test_windows_wheel_packaging tests.test_windows_provenance` 全部通过；不改变现有 helper locator 的授权语义。

## Task 3: 实际安装 CI 与交付

**Dependencies:** Task 2
**Parallelizable:** No (依赖最终 wheel 合同)

- [x] 在 `.github/workflows/windows-helper-provenance.yml` 使用固定 setup-go action SHA，原生构建纯 Go verifier，编译并发不超过 6。
- [x] `scripts/run_windows_wheel_ci.py` 在干净 pip 安装后调用包内 verifier 验证实际 action bundle，并运行实际负例；保留 gh 独立验证。
- [x] 聚焦回归连续 20 轮、冻结源码完整 `.venv/bin/python scripts/preflight.py`、`compileall -j 6`、governance/site/landscape/diff 守护通过。
- [x] 独立规范/质量复审通过，提交推送 main；记录具体 SHA 与 x64/ARM64 真实 job/步骤结论，失败不调整判据。
- [ ] 回收真实结果后继续 R2 生产 runner、资源/lease 接线与 R3 工作流绑定，不把本子门当整体验收。

---
**Execution Mode:** serial

## 2026-10-08 本机记录（不是原生 Windows 验收）

Python 33 个关联方法连续 20 轮（660 次），Go 16 个函数连续 20 轮（320 次）、vet、module checksum verification 通过。许可证 6 个方法连续 20 轮（120 次）；独立规范审查复现并关闭“已审核 NOTICE/PATENTS 缺失仍接受”问题，质量审查随后复现 Windows 临时夹具 CRLF 问题，仅将四处夹具改为固定 bytes，不规范化生产许可字节或摘要。独立质量复审用同一 CRLF 模拟转为 GREEN，无遗留阻断；修复后的冻结源码完整 preflight 三道门通过，语法、治理、官网、竞品排期与 diff 守护通过。

重新生成的 x64/ARM64 notice 各 625239 bytes，SHA-256 均为 `f6c4772fb032b893dc74e99df4bec4e9a0926f1fbd80219c8b5007e09fb3b6e4`。sdist 构建并核对原生源码、根、fixture、许可证和 staging 源文件均在归档中；Linux wheel 的十阶段干净安装、真实 namespace/cleanup/receipt/lease/Git broker 回归全通过。Go 是构建依赖，不加入 Python core dependency，以上不是 Windows 原生安装正例。

待 main 新 SHA 的四个原生矩阵（x64/ARM64 × Python 3.11/3.12）验证同次 action attestation、包内验签正例及六类实际负例后再关闭本子门；不改变 helper 三个 false、只读回执或 R2/R3 readiness。

## ae18bbf 原生复验：构建步骤失败，本子门仍未通过

提交 `ae18bbf62739094abdbb6e643125ff97ca8800fe` 已推送并核对远端 main。
[provenance run 37717792299](https://github.com/ayukyo/icode/actions/runs/37717792299) 的 validate 成功；四组原生 job 均在合并的 build/test/notices step 失败：x64 Python 3.11 `113120005052`、x64 Python 3.12 `113120005033`、ARM64 Python 3.11 `113120004956`、ARM64 Python 3.12 `113120004975`。attest、安装验签和上传全部跳过，真实包内正例及六类负例确认数均为零。

公开 x64/ARM64 check annotations 只给 `Process completed with exit code 1`，没有 raw details；不能断言是 go test、vet、build、license tests 或 closure 中的某一项，也不能因为四格同一步失败就认定内部根因相同。下一次只加入各原生命令固定 stage/exit，Go JSON fail 只投影严格白名单形状、数量有界的顶层测试名，许可输出只匹配固定错误类别，不输出证明、路径或异常正文；失败仍返回原退出码且不进入签名/上传。实际原因待下一 SHA，严禁猜测修改密码学或规范化许可证字节来放宽判据。

同 SHA 的 [主 CI](https://github.com/ayukyo/icode/actions/runs/37717792363) 为 32 success、2 Windows Reviewer snapshot candidate failure、3 skipped；两个 Python 全仓、Windows 旧 bootstrap wheel、workspace 和 R3 lifecycle 子门通过，不替代本 provenance 或 R2/R3 总门。[官网](https://github.com/ayukyo/icode/actions/runs/37717792362) success。

## ffc3792 阶段定位与严格 UTF-8 修复候选

[run 37720691064](https://github.com/ayukyo/icode/actions/runs/37720691064) 的四组原生 job（`113128677034`、`113128677135`、`113128677172`、`113128677027`）均失败；分别读取的公开注解均为 `stage=license_closure exit=1 reason=unclassified`。前置 validate 成功，四组签名/安装正例/六类负例/上传全部跳过。主代理也直接重读 x64 Python 3.12 原始公开注解；仍未取得异常类型或 runner locale，不以共同阶段推断底层原因。

| 基线 | 本次证据与未观测边界 |
|---|---|
| identity | 以上四个 GitHub hosted matrix job；物理 serial/MAC 不适用，实际 ANSI code page unknown |
| time_window | 该 run 2026-10-08 03:01–03:12 UTC，按 job 时间定位；无原始异常文本 |
| repo_matrix | runtime/main `ffc3792401dca0edde0570e53e0d3711a53f02ef`；analysis/verification 为其上的两处编码工作树补丁，子模块未改 |
| artifact_identity | 本机 Go 1.27.1；远端编译器产物未取得/hash unknown，签名 wheel 未生成；本机 notice 双架构均 625239 bytes、SHA-256 `f6c4772fb032b893dc74e99df4bec4e9a0926f1fbd80219c8b5007e09fb3b6e4` |
| evidence_sources | 公开固定阶段注解、当前源码、真实 go list 元数据与 child-pipe 回归；没有完整远端日志 |
| unresolved | Windows 实际解码页/异常类型及修复后原生行为；主代理以新 SHA 四组 CI 验收，不放宽失败条件 |
| conclusion_ceiling | `fix_verified_host`：修复真实平台编码缺陷；禁止称旧 CI 确定根因或 Windows 验签通过 |

Go 1.27.1 的 [list JSON 输出](https://github.com/golang/go/blob/go1.27.1/src/cmd/go/internal/list/list.go#L470)与 [JSON 编码](https://github.com/golang/go/blob/go1.27.1/src/encoding/json/encode.go#L82)采用 UTF-8；CPython 3.12.10 的 [subprocess 默认文本编码](https://github.com/python/cpython/blob/v3.12.10/Lib/subprocess.py)和 [Windows ANSI code page 路径](https://github.com/python/cpython/blob/v3.12.10/Python/fileutils.c)说明未指定编码会受 locale/UTF-8 mode 影响。真实本机 go list 输出 2141305 bytes 严格 UTF-8 通过，CP1252 在位置 145465、字节 157 拒绝；独立复现一致。两次 Go subprocess 现显式严格 UTF-8，未改 read_notice、原文 bytes、哈希、模块审核、密码学或权限。

| 断言 | 类别 / 状态 |
|---|---|
| locale 默认解码存在真实缺陷 | 当前源码＋真实输出，已复现 |
| 它导致 ffc3792 原生失败 | 候选解释，未确认，不作根因结论 |
| 严格 UTF-8 不改变 notice 原文/摘要 | 两架构生成器与完整许可审核通过，本机证据 |

新增正常 UTF-8 JSON/Unicode GOROOT 与坏 UTF-8 两例先 RED 后 GREEN；8 项许可测试、最终 20 轮 160 次通过。独立 SPEC/QUALITY 通过；QUALITY 发现 Unicode 临时父路径可能让 GOROOT 的无关解码异常冒充坏 JSON 拒绝，现负例绑定异常编码及原始坏 JSON bytes。独立旧版变体明确 RED、新版 Unicode 父路径变体 GREEN，Minor 关闭。生产文件冻结后的完整 preflight 3/3、补强测试后的许可回归与密钥/子模块守护、编译/治理/官网/竞品/diff 均通过。整体 R2/R3 与自动模式门不变，待新 SHA 原生复验。

## 0268506 原生测试失败与 Windows reader 边界修正

[run 37722539792](https://github.com/ayukyo/icode/actions/runs/37722539792) 的 validate 成功；四组原生 job `113134743567`、`113134743611`、`113134743674`、`113134743652` 的公开注解分别确认 `stage=license_tests exit=1`。这是新的失败阶段，不能继续沿用上一 SHA 的 license_closure 结论，也不能宣称许可生成或安装验签通过。公开注解没有具体测试名/异常类型，当前未确认远端断言。

独立核对固定 CPython [v3.11.15](https://github.com/python/cpython/blob/v3.11.15/Lib/subprocess.py)与 [v3.12.10](https://github.com/python/cpython/blob/v3.12.10/Lib/subprocess.py) 的 Windows `_readerthread/_communicate`：text pipe 在后台线程 read；坏 UTF-8 引发线程异常，空 buffer 在 caller 变为 None，继而 Go package stream 解析 TypeError。独立代理仅在内存运行抽取的官方 reader 方法、真实 TextIOWrapper，两个版本均复现；这确认平台机制，但没有证明它是以上四格的实际失败测试。

新增 Windows reader 语义回归保留实际 child-pipe bytes，旧 generator 明确 RED（caller 为 TypeError 而非绑定原坏 JSON bytes 的 UnicodeDecodeError）。现在 Go subprocess 收取 binary bytes，在主调用方立即严格 UTF-8 解码后才进入下一输入；check/timeouts、原文许可、哈希与模块审核不变，不接受 ignore/replace 或任意异常冒充拒绝。9 方法 20 轮 180 次、0 SKIP；两架构真实 Go linked metadata 生成 notice 仍为 625239 bytes、SHA-256 `f6c4772fb032b893dc74e99df4bec4e9a0926f1fbd80219c8b5007e09fb3b6e4`。独立复审和新 SHA 原生四矩阵另记，不把机制模拟当 Windows 实际安装验收。

四组后续步骤 6–9 最终均 skipped，license_closure、签名、gh oracle、实际安装正例与六类负例、上传的已确认执行数均为 0/4，停止旧 SHA 轮询。本修正独立 SPEC 后 QUALITY 均通过；QUALITY 分别以旧代码 RAM 变体在 ASCII/Unicode 临时父目录复现 RED，新版 GREEN，并检查真实 child-pipe CRLF 协议、Unicode＋空格 GOROOT、许可混合换行原字节/hash及拒绝输出覆盖。主代理也直接运行本机 CPython 3.11.15 的 Windows reader AST 方法重核 empty buffer→None。生产文件冻结后完整 preflight 3/3 通过，仍为本机修正，下一 SHA 四矩阵另验。

## 6fda570 原生四矩阵通过：离线验签子门闭合

2026-10-08 04:07 UTC，已推送并核对远端 main 的 `6fda57075e4eee0dc1fed399c6f317d0bc43e3e1` 对应 [provenance run 37724953112](https://github.com/ayukyo/icode/actions/runs/37724953112) 全部成功。独立观察后，主代理再次直接读取公开 jobs API：validate `113140899613` 成功，四组原生 job 的步骤 5–9 均 success。

| 矩阵 | job | 原生许可闭包 / helper / 签名 / 安装验签 / 上传 |
|---|---|---|
| x64 Python 3.11 | `113142724257` | 全部通过 |
| x64 Python 3.12 | `113142724231` | 全部通过 |
| ARM64 Python 3.11 | `113142724303` | 全部通过 |
| ARM64 Python 3.12 | `113142724330` | 全部通过 |

安装步骤的结论来自该 SHA 固定脚本的强制执行顺序与整个步骤成功：gh 独立 oracle、干净安装的包内离线正例、六类实际篡改负例、bootstrap setup/spawn 拒绝及 TemporaryDirectory 清理均未被跳过或吞掉错误。因此支持正例 4/4、六类负例各 4/4；没有获取逐项原始 stdout，不把推导证据写成逐行日志证明。此前旧 SHA 的具体失败测试仍未知，本次成功不追溯伪造其根因。

本子门 verdict 为 `verified_native_matrix`。验签结果仍是只读回执，`launch_authorized=false`；bootstrap 的 setup、execution、ready 三项仍 false。下一步继续受保护启动对象、Windows sandbox identity/WFP/ACL/Job 与真实工作流接线；签名通过不授予启动权限，不关闭 R2/R3，不改变自动模式。[官网 run 37724952996](https://github.com/ayukyo/icode/actions/runs/37724952996) 已成功；主 CI 与隔离子门另行记录。

同 SHA 的 [主 CI 37724953038](https://github.com/ayukyo/icode/actions/runs/37724953038) 最终 32 success、2 failure、3 skipped。独立观察分别读取 x64 `113140899976`、ARM64 `113140899987` 的公开注解：两个 Windows Reviewer snapshot candidate 在 temporary standard user 步骤失败，snapshot 执行 exit78、cleanup=true；双栈均 connect_denied=false、10035 后 wait_expired=true，runner observer ready 但 no_matching_event，capture archive_member_missing。这些是本轮未过硬门的直接公开证据，不推断 WFP/系统根因，不把等待超时算拒绝，也不继续扩展已被生产方案替代的诊断后端。provenance 子门与整体主 CI verdict 独立；后续仍按已选专用身份＋WFP＋Job 生产方案开发和验收。

## d65ecf8 原生四矩阵复验（2026-10-08）

main `d65ecf8e210d273984f2b0bf12fe163eb695e2ad` 的 [provenance run 37731144892](https://github.com/ayukyo/icode/actions/runs/37731144892) 最终 success。独立只读观察者取得四组真实解码日志；主代理通过授权 jobs API 再核对 validate 与四组步骤5–9全部 success。

| 矩阵 | job | 许可证9项耗时 | 已上传 artifact |
|---|---:|---:|---:|
| x64 / Python3.11 | 113162160040 | .102s | 11530631100 |
| x64 / Python3.12 | 113162159971 | .172s | 11529901887 |
| ARM64 / Python3.11 | 113162159963 | .159s | 11529882082 |
| ARM64 / Python3.12 | 113162160032 | .188s | 11530501584 |

各组真实日志确认 gh oracle、包内离线 API、实际密码学负控集合、metadata、拒绝 setup/commands 均 PASS；六类负控来自该 SHA 脚本强制集合验收，不伪装六条独立输出。临时目录清理依据正常退出包含清理推导，不声称额外显式 GC 日志。主代理实读 validate 日志另确认签名fixture9/9、完整preflight3/3与governance通过。

同 SHA [主 CI 37731144778](https://github.com/ayukyo/icode/actions/runs/37731144778) 32 success／2 failure／3 skipped；Python3.11/3.12各1899项，OK、71 skips。两失败仍是旧Windows Reviewer硬门，不能由此开放自动模式。该复验仅闭合离线签名验证：`launch_authorized=false`、bootstrap setup/execution/ready=false及R2/R3未整体验收均保持。
