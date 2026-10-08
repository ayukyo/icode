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
- [ ] 独立规范/质量复审通过，提交推送 main；记录具体 SHA 与 x64/ARM64 真实 job/步骤结论，失败不调整判据。
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
