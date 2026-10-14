# Windows positive loopback config observation Implementation Plan

> 状态：PLAN ONLY，待 root 全文、fresh SPEC → 不同 QUALITY。不得据此执行 TEST/SOURCE/CI、Git 或系统操作。
> 后续实施使用已批准计划执行流程；本轮 writing-plans 仅组织完整资产与验收门，用户的 PLAN ONLY 覆盖自动执行建议。

**Goal:** 在既有 privateNetwork 正控的前后，增加独立 fixed helper 的 GetConfig 只读样本，关闭配置前提盲点；不修复或重新解释原 Reviewer 失败。

**Architecture:** 现有 native helper 独立 mode → 专用有界父侧采样 seam → 既有 positive-control 同 profile 两端样本。原 candidate、Job/profile/ACL、WFP observer、token 核验与最终 DENY gate 不变。

**Tech stack:** Windows SDK/C11、Python stdlib、既有 CMake/GitHub CI；无新增依赖、权限、capability、系统配置或公网目标。

## 1. 批准输入、真实问题与信用边界

唯一设计为 [Windows loopback 配置前提只读观测设计](../specs/2026-10-14-windows-loopback-config-observation-design.md)，172L，SHA256 `78723e957ac0258e8da342ce20fe1b00b45de2dde5fba4964ee7b24642d57fe6`；root 已全文及独立 SPEC → 不同 QUALITY 均 C0/I0/M0。root sequential-thinking `7702ec` 三步 accepted 是批准输入，不冒称本作者自己的调用。

观察日 2026-10-14，源码基线 Agent `58bc31be4f4a235848cff3e36c482985db23e9ef`。原 run `38581925165` attempt1：x64 job `115913759361`、ARM64 job `115913759450` 均 Reviewer exit78、positive exit105；各原 footer、pending10035、cleanup 与 token 事实以批准 DESIGN 为准。本轮未重新查询线上、不重新加载 Windows DLL，也不把云 runner 当已核物理设备。两平台相似失败不证明同根因；IPv4 正控先失败时不能称 IPv6 连接已实际失败。

三问已确认：确有当前未观测 GetConfig 前提；已有 fixed helper/标准用户 staging/正控可复用；本片触达正控前后诊断调用链但不改变产品接口。结论上限严格为 observation_only；配置匹配、未匹配、API 错误均不授 DENY、网络可用、WFP 有效策略或根因信用。原 Reviewer 若继续失败必须保留，不能以新增样本绿替代旧门。

仅本 PLAN 文件落盘。后续目标共六路径：新 TEST、新 C include、现有 helper、父脚本、Reviewer 测试中的诊断编排、CI。产品 `src/icode/windows_job.py` / `windows_appcontainer.py` 不改。起草时的 Mac 十目标、legacy 测试修订及 root 文档 dirty 未被覆盖；本轮同样不改其它作者当前变更。

## 2. 冻结、唯一投影与停止线

所有文件按 UTF-8/LF；资产 hash 包括末尾一个 LF、不含 Markdown 围栏。不得重排或格式化。四 diff 为 apply_patch 信封；逐 hunk 原上下文必须恰一处匹配，按列明输入应用；inverse 逐块恢复原字节。输入漂移先停交 root，不按行号强套，不借更新 hash 掩盖其它作者改动。

| 修改路径 | 输入 SHA256 | 输出 SHA256 / 行数 |
| --- | --- | --- |
| `native/windows/icode_wfp_event_probe.c` | `6d878e45a5b8f8938ab9a72040df2d1ec698d0e3e2953cc61d56a754d3b09dc5` | `1796d36ca0964d685a7d0aeedb8bbabd3d29a8eb7c209255310f1ee6769ad596` / 2124 |
| `scripts/run_windows_appcontainer_read_probe.py` | `d4f1e7c59af8d1d077d5fa2ec8dec46914f1e39b9e87ce82dba7952d88549b31` | `ca84b611053f8b3d9e92196dc71561bfa93c54f2a545e302500ec92b27699d92` / 1818 |
| `tests/test_windows_appcontainer.py` | `51de57ea545f03091c5154621037f22cd08355ba120c1c1705bd865840fdf562` | `5be4949f16dbf7a0607bdc5e24a1cf110c94c65e2b8b862b03a74c6c35ed61cc` / 9424 |
| `.github/workflows/ci.yml` | `25ce291318d265335d8ec0a1b54050dd49adcf70e8229dc96c8a49f8702f8fd1` | `92a19ba6fab8e5e5b1afdb1c5cf5caad7d9eff7992b84fb539c1bc27e9be5679` / 2503 |
| 新 `tests/test_windows_loopback_config_observation.py` | 必须不存在 | `45fa5f0734a551fbd043dce535420881936c2cc993be4b25ceb4fc484f2a8060` / 553 |
| 新 `native/windows/icode_positive_loopback_config.inc` | 必须不存在 | `194a6902cb828a71cac25c10b3bb66a1189355c888f7d51b724cc31c895de977` / 147 |

CI 输入 `25ce2913…` 起草时是已批准 Mac TESTONLY dirty 投影，不是 58bc 的 HEAD blob；现据 root 交接已随 `5ad08dd` 发布，本轮实际文件仍与该输入 hash 一致。本片仅追加下面三个 hunk，不将 Mac 变更冒领为本片资产或覆盖它。真正执行 Task3 时仍先核实际输入；字节漂移须重审，不因历史发布而强套补丁或覆盖其它作者变更。

不变边界：windows_job.py `ac2bfbe924a9b03b68ab0304f55cfcfde7b79615c3563c0db61ca099d335d640`；windows_appcontainer.py `307dc730bf28bc661ad99b8d02dc9093b51c1dcdf45f993b470e68a5562f1a1f`；native/windows/CMakeLists.txt `a617f5c0cd5c1e50065aad54469bba20f9c63c7065475b48176bff9c9f30105c`。现有 C11/SDK 与链接足够，不改 CMake/ABI pack。

| 冻结资产 | 围栏内容行数 | SHA256 |
| --- | ---: | --- |
| A 完整新 TEST | 553 | `45fa5f0734a551fbd043dce535420881936c2cc993be4b25ceb4fc484f2a8060` |
| B 完整新 include | 147 | `194a6902cb828a71cac25c10b3bb66a1189355c888f7d51b724cc31c895de977` |
| C helper patch / 2 hunks | 23 | `d1c2e79ac08d298efdce4c823af92e85d4afadef0a394abfa192662794c8b885` |
| D parent patch / 1 hunk | 242 | `d35b602663d1165133011184d355c74621903c9f1d4ab04d545add3eede5efd7` |
| E Reviewer 编排 patch / 3 hunks | 72 | `de6c695694ecc17cc93f5fa6216e3b7e810d3758326fec615c1e6701c1736f3a` |
| F CI patch / 3 hunks | 33 | `420b75a2b211e16eb4487a1e939708d4f71bf5c2b321be5f0d341c21fed8a523` |

停止线：需要产品返回类型/profile 生命周期扩修、新 API 权限/Job、派生子孙、任意 SID/命令入口、Set/豁免/防火墙变更、loader 全局设置或真正总墙钟硬限额时退回设计。禁止环境旁路、skip/unsupported 当通过、放宽 Reviewer 或取消/重跑隐藏失败。

## 3. 精确 seam、协议与生命周期

Native 签名是 `DWORD (WINAPI *)(DWORD *, PSID_AND_ATTRIBUTES *)`，用 SDK 原生结构与 DWORD32；新 mode 恰 `--observe-positive-loopback-config PROFILE`，内部 `icode-[0-9a-f]{32}`，argc3。非法参数 exit2 无回执；合法固定回执所有状态 exit0。旧 self-test/所有其它 mode 保持。独立分支不打开 WFP engine、不订阅事件、不连接，不创建删除 profile。

可信 SystemDirectory 绝对 FirewallAPI.dll + LoadLibraryExW SEARCH_SYSTEM32 + 精确 GetProcAddress，不重试/回退；一次派生、一次 GetConfig。查询前 count0/NULL，只有实际 ERROR_SUCCESS 完整验证可判空/未匹配。返回后最多4096项，不授 API 预分配上限；超过预算不部分判未匹配。先验证完整安全指针所有权图再比较/释放：SID 指针别名（含数组或 derived 指针）、坏 SID、重复目标值均 invalid_data；不做野地址解引用负控。

合法独立 SID 和数组各 HeapFree 一次，derived FreeSid，最后 FreeLibrary；记录尝试/确认与每资源状态，不重试；错误或无法安全遍历保持 unknown，进程退出 OS 回收不冒充显式释放。释放失败保留 query status/code，清除 target 字段。不用 LocalFree/FreeAppContainers/FwpmFreeMemory。API stage 的 HRESULT 保留 unsigned32，不读 last-error 代替查询 DWORD。

父侧 `_observe_positive_loopback_config(executable, profile_name, phase) -> (sample, unreaped_stop)`：仅确实创建且实际 wait 未确认回收的进程使私有 stop=true；未启动并非“已确认未回收”。monotonic 从 Popen 前计2s，剩余等待；超时/协议失败 terminate+wait2，仍失败 kill+wait2；仅实际 wait 成功授 process_reaped。Popen、kernel/close/terminate/kill 操作本身非硬墙钟保证，不能将2+2+2宣传为全路径6秒上限。

PeekNamedPipe 后有界 os.read；stdout最多4097字节以检测超过4096、stderr只需1字节即拒绝，无 communicate/reader thread/先无限抓取后截断。恰一 ASCII JSON 行（LF/CRLF）、无重复/额外/缺字段、无尾随内容，bool不得充整数。固定 helper 字段与父 phase/process_reaped/cleanup/observation_complete 分开，详见 B/D 完整 schema；公开不含 profile/SID、argv、路径、env、全名单/指纹。退出0不是成功匹配；unsupported/load_failed/api_error/invalid_data/limit_reached 与父 launch_failed/timed_out/protocol_error/not_attempted 分账。

Reviewer 在原正控 try 前冻结同一个 `capability_profile_name`；两 helper 参数和原 `_diagnostic_profile_name` 来自该值。旧父 token 的 verified/package_sid_match 必须实际为 True；不扩大 token receipt、不声称读回 SID。post 在原 wrapper 返回清理后，profile 可能已删除，派生仅身份算法不证明此刻 profile 存在。两端都完整/释放确认/回收/父绑定时仅比较 match、attributes、count；一致为 consistent_endpoints，变化为 observed_drift，其余 unknown。不能证明采样之间稳定或同计数的无关项目替换。

pre unreaped：打印固定结构后终止，不启动 positive/candidate。旧 positive 异常及 cleanup 失败保持原首错误，cleanup 未确认不派生 post。post unreaped：先保留原 positive executed/exit/cleanup 摘要，再停止 candidate；不谎称 candidate 已运行。普通已回收 unknown 样本不跳过旧实验。无新 config gate 替代旧 DENY gate。

## 4. 正式串行任务与验收

### Task1 — 不同 TEST 作者：仅 Asset A，正式旧语义 RED

先核上述输入/缺新文件，完整回读资产。只落 A，不落 B–F，不改旧门。运行下列严格命令，必须 count12、0 ERROR/skip，失败必须是 AssertionError。旧前置断言取现有真实 Reviewer positive block，stub 仅外部 launcher/sample 边界；事件只有 launch，要求 pre→launch→post 因而失败。在访问缺 mode/include/新函数或编译前已断言，故不以编译/导入/签名错作 RED。

~~~~text
PYTHONPATH=src python3 -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_config_observation.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
~~~~

预计旧12方法均共享 `POSITIVE_LOOPBACK_OBSERVATION_MISSING` 前置 Assertion RED；这是一项缺接线的12记录，不是12独立原生失败。记录实际 failuremethods/records、ERROR/skip、退出与时长；非该语义失败先修计划资产，不吞掉错误。由 fresh 实际 TEST 审查后才准 Task2；匿名 RAM 不替正式 RED。

### Task2 — 不同 SOURCE 作者：B+C+D+E，定点 GREEN

仅新 include 与三个既有文件，apply_patch 精确9总hunk中的前6（C2+D1+E3），TEST A 冻结不改，CI F 暂不改。AST 新 TEST/父脚本/Reviewer，核全部原/投影 SHA及唯一 inverse，不改变产品/CMake hash；运行同 strict12，须12GREEN、0F/E/skip。C TU 使用实际 include、实际 profile validator/新 wmain 分支，只有 OS 边界假实现；编译/执行是 portable software fixture，不启动 native helper或系统网络 API。

逐方法覆盖以 A 全文为准：成功匹配/未匹配/emptyNULL/empty-array/max4096；query error 与 HRESULT；NULL/别名/重复/坏SID；四资源释放失败；loader/export/上限；真实固定 CLI；严格协议；有界 pipe/actual wait；launch/slowPopen/timeout/terminate/kill/动作失败/未回收；三字段漂移及父绑定；真实正控首错误/停止顺序；真实 Peek ABI seam + no-write/no-connect 实际计数。no-Set/no-connect 不是仅字符串证明；计数与源码边界成对。软件 TU 不授 Windows ABI/SDK/API 可用信用。

Task2 作者 self SPEC/QUALITY及7维完成后，root fresh actual SPEC → 不同 QUALITY；不由同一作者代替正式独立审查。

### Task3 — 审查后 CI 三 hunk 与同新 SHA 双平台

批准后另作者仅 F 三 hunk（strict12、build helper SHA日志、既有 Copy-Item 后 staged helper SHA校验与日志），精确 CI baseline/projection/inverse。Copy-Item 完成后分别对原 build source 与 `$wfpProbeForUser` 文件计算 SHA256；不相同以固定 `positive_loopback_staged_helper_hash_mismatch` 拒绝，成功才输出白名单标签 `positive-loopback-staged-helper-sha256=` 加小写hash，不输出路径。原 build 标签 `positive-loopback-helper-sha256=` 继续保留。复制、ACL、路径、env与权限不改；此仅观察该时点 staged 文件并与 source 内容相同，不证明 kernel mapped 字节或受保护同对象启动，后续替换/TOCTOU 不由此消除。

保留 matrix、25min、标准用户、staging、ABI检查、原全套与 Reviewer gates、原失败日志。strict12 在既有 Ubuntu Python3.11/3.12执行，cc由现有 runner提供；不新增依赖。不要仅 collect，不接受 skip。不能仅因 strict12通过跳过其它既有 CI 门。

仅由 root 按主仓 main-only 发布待验候选，不能把本 PLAN 当提交/推送授权。Mac 输入已随5ad08dd发布；仍不覆盖/顺带发布其它未授权路径。线上为同一个新 candidate SHA，现有 x64 windows-latest 与 ARM64 windows-11-arm Reviewer job attempt分别记录：

- run/job/SHA/platform/attempt、build 与 staged helper SHA256且校验相等、构建/SDK/ABI结果及标准用户/staging；staged hash仅为文件观察，不冒充 kernel mapped/受保护同对象启动证明。
- pre/post 固定 JSON、status/api_stage/code、目标/条数、全部释放/进程回收账、same-profile父token绑定、comparison；必须实际 GetConfig 与完整 cleanup/reap 才授该次观察成功。unsupported/error/timeout/缺post仅 unknown，不能记本片原生验收通过。
- 原 positive、candidate、WFP及 Reviewer footer和退出保留。配置匹配或未匹配均可为有效观测；即便 observation成功，若仍 exit78/positive105，Reviewer/完整R3仍失败，不称修复或发布通过。

若原实验无法前进至 post，报告观察不足/停止线，不重试刷绿。CI没有新网络能力、capability、豁免或权限。原 Linux full/Windows其它既有门由线上一次候选执行，本机不 full/native。两 native job 与 actual reviews完成前本片仅“资产实现/软件检查”而非跨平台完成。

## 5. 本轮匿名诊断与研究决策

仅设计诊断，未落 TEST/SOURCE/CI。最后匿名 RAM实测：旧12方法/12Assertion failures、0ERROR/skip、0.029s；投影12GREEN、0F/E/skip、0.746s；驱动退出0表示诊断按期完成，旧测试自身仍失败。两轮使用 TemporaryDirectory 的 C compiler/stub TU，未调用 Windows网络API/未启动 Windows helper/未运行原生或全套。测试源码来自 A，代码来自四唯一投影及 B。早期 fixture 格式/驱动错误已修正，不计生产 RED、不作为产品缺陷。

2026-10-15 修订账：初版1205L/`56401dfc540a048ff8b7ad32c5012066a534d02c34f18ea93d1c7ef642e8cddb` fresh SPEC为 C0/I0/M1；M1为起草时dirty被误写为当前状态，现明确5ad08dd已发布，不回写初版已通过。root另核build与Copy-Item目标不同，故F最小新增staged校验hunk，不扩观察权限。A–E资产字节不变；F变33L/3hunks，CI投影2503L。修订后匿名RAM（`eaf0d8`）旧12Assertion/0Eskip/0.021s，投影12GREEN/0Eskip/0.949s、驱动exit0；全部9hunks唯一投影与inverse精确，Python AST通过。该12方法不执行PowerShell或校验真实Windows staged文件；F仅静态核对既有Copy-Item之后、原source与实际staged两字节散列、固定标签/固定拒绝、复制/ACL/path/env无差分，实际双平台CI仍待。诊断驱动首次恢复RAM变量不存在而退出1，未运行测试，不算产品或语义RED。

固定研究复用批准 DESIGN，观察2026-10-14，不刷新HEAD或20榜。MicrosoftDocs/sdk-api `656e9656bfaef34dd29cd7ee9e1146aec17e924c`（2026-10-09；GetConfig文档ms.date2022-08-03），文档CC-BY4.0、示例MIT；Codex `27065a91ccbf5ba8532844be3777fcf83b77820d` Apache2。采纳 GetConfig正确类型/HeapFree配对、可信loader、有界读取与所有权分账：收益是关闭前提盲点，成本为147L专用C协议、父侧232L seam与两平台验收；不复制上游代码、无新依赖。暂缓 WFP因果/公网实验/真实硬隔离；不适配改配置/提权/全局策略、把10035/未匹配当DENY。

主源：[GetConfig及释放](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/networkisolation/nf-networkisolation-networkisolationgetappcontainerconfig.md)、[不同FreeAppContainers类型](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/networkisolation/nf-networkisolation-networkisolationfreeappcontainers.md)、[LoadLibraryExW](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/libloaderapi/nf-libloaderapi-loadlibraryexw.md)、[Codex token所有权](https://github.com/openai/codex/blob/27065a91ccbf5ba8532844be3777fcf83b77820d/codex-rs/windows-sandbox-rs/src/token.rs#L194-L270)。许可链接与完整研究在批准 DESIGN，不将上游机制授本项目 authority。

## 6. 自审与【架构级自检报告】

self SPEC：逐项核唯一 DESIGN、三seam、12方法 oracle、所有权/预算、None/unknown与旧首错误；self QUALITY：反向核公开输出、真实计数、projection/inverse、并行dirty隔离。自审完成不代 fresh 独立双审；当前禁止实施。

- ✅ 语法/编译：资产 Python AST与实际 portable C TU定点通过；未作 Windows SDK编译，不授原生通过。
- ✅ 依赖/调用链：fixed mode→专用父 seam→原正控两端，原mode/CMake/product无变化；CI依赖Mac基线显式。
- ✅ 逻辑/边界：0/NULL、4096/超限、别名、重复目标、实际wait与父token绑定均有可执行断言；端点不等全程。
- ✅ 异常处理：原query/旧Reviewer首错误、release/timeout/reap分账；未知不判空，不吞EOF或授成功。
- ✅ 关联模块：完整A–F与六目标，原门/25min/matrix未改；并发dirty保留，无SOURCE/TEST/CI落盘。
- ✅ 兼容安全：无Set/connect/新权限/任意SID，产品接口/profile生命周期与普通CLI不改。
- ✅ 可运行性：12软件定点投影GREEN；正式TDD、实际双审、同SHA双原生均待，不能声称100%或R3修复。

以下为全部冻结资产，实施者不得另造省略片段。

## Asset A: tests/test_windows_loopback_config_observation.py

```python
"""Fixed positive loopback configuration observation; software only, no system API calls."""
from __future__ import annotations
import ast
import contextlib
import ctypes
from ctypes import wintypes
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "scripts/run_windows_appcontainer_read_probe.py"
REVIEWER = ROOT / "tests/test_windows_appcontainer.py"
NATIVE = ROOT / "native/windows/icode_wfp_event_probe.c"
CORE = ROOT / "native/windows/icode_positive_loopback_config.inc"
PROFILE = "icode-" + "0" * 32
OLD_POSITIVE = "                try:\n                    capability_control = run_windows_appcontainer(\n                        capability_argv, cwd=scratch, timeout_seconds=12,\n                        process_limit=2, _diagnostic_profile_name=capability_profile_name,\n                        _diagnostic_runtime_acl=True,\n                        _diagnostic_runtime_roots=(staged_runtime,),\n                        _diagnostic_private_network_capability=True,\n                    )\n                except Exception as exc:  # noqa: BLE001 - diagnostic failure is inconclusive\n                    capability_control = WindowsJobResult(\n                        False, None, \"diagnostic_exception\", False,\n                        type(exc).__name__,\n                    )\n                if not capability_control.cleanup_ok:\n                    self.fail(\n                        \"private-network positive-control Job/profile/ACL cleanup did not verify: \"\n                        f\"{capability_control.detail}\"\n                    )\n"
C_STUB = r'''#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <wchar.h>
#define WINAPI
#define TRUE 1
#define FALSE 0
typedef int BOOL;
#define MAX_PATH 260
#define MAX_PROFILE_NAME 38
#define LOAD_LIBRARY_SEARCH_SYSTEM32 0x800
#define ERROR_SUCCESS 0U
#define ERROR_INVALID_DATA 13U
#define ERROR_INSUFFICIENT_BUFFER 122U
#define S_OK 0
typedef uint32_t DWORD;
typedef unsigned UINT;
typedef int32_t HRESULT;
typedef void *PSID;
typedef void *HMODULE;
typedef void *HANDLE;
typedef struct { PSID Sid; DWORD Attributes; } SID_AND_ATTRIBUTES, *PSID_AND_ATTRIBUTES;
struct fake_sid { int valid, value; };
static struct fake_sid target = {1, 7}, sids[4097];
static SID_AND_ATTRIBUTES array[4097];
static unsigned mode, derives, queries, sid_frees, arrays, derived_frees, libraries;
static unsigned loads, exports, forbidden, connect_calls, profile_calls, duplicate_free;
static unsigned freed[4097], release_stage;
static char receipt[4096];
static DWORD last_error = 5;
static int receipt_printf(const char *format, ...) {
    va_list arguments; va_start(arguments, format);
    int n = vsnprintf(receipt, sizeof(receipt), format, arguments);
    va_end(arguments); if (n < 0 || n >= (int)sizeof(receipt)) abort();
    return n;
}
static UINT GetSystemDirectoryW(wchar_t *out, UINT capacity) {
    if (mode == 17) return 0;
    if (mode == 18) return capacity;
    const wchar_t text[] = L"C:\\Windows\\System32";
    if (capacity <= wcslen(text)) abort();
    wcscpy(out, text); return (UINT)wcslen(text);
}
static DWORD GetLastError(void) { return last_error; }
static HMODULE LoadLibraryExW(const wchar_t *path, void *file, DWORD flags) {
    loads++;
    if (file || flags != LOAD_LIBRARY_SEARCH_SYSTEM32 ||
        wcscmp(path, L"C:\\Windows\\System32\\FirewallAPI.dll")) abort();
    if (mode == 19) { last_error = 126; return NULL; }
    return (HMODULE)(uintptr_t)1;
}
static DWORD WINAPI fake_query(DWORD *count, PSID_AND_ATTRIBUTES *entries) {
    queries++;
    if (*count || *entries || derives != 1 || libraries) abort();
    if (mode == 4 || mode == 26) return 5;
    *count = mode == 11 ? 4096 : mode == 12 ? 4097 : 2;
    *entries = array;
    if (mode == 2) { *count = 0; *entries = NULL; }
    if (mode == 3) *count = 0;
    if (mode == 5) *entries = NULL;
    if (mode == 6) sids[1].valid = 0;
    if (mode == 7) sids[0].value = sids[1].value = 7;
    if (mode == 8) array[1].Sid = array[0].Sid;
    if (mode == 9) array[0].Sid = array;
    if (mode == 10) array[0].Sid = &target;
    if (mode == 22) return 5;
    if (mode == 23) { *count = 0; *entries = (PSID_AND_ATTRIBUTES)&target; }
    if (mode == 24) array[0].Sid = NULL;
    return 0;
}
static void *GetProcAddress(HMODULE library, const char *name) {
    exports++;
    if (library != (HMODULE)(uintptr_t)1) abort();
    if (strcmp(name, "NetworkIsolationGetAppContainerConfig")) { forbidden++; return NULL; }
    if (mode == 20) { last_error = 127; return NULL; }
    return (void *)fake_query;
}
static HRESULT DeriveAppContainerSidFromAppContainerName(const wchar_t *name, PSID *sid) {
    derives++;
    if (wcsncmp(name, L"icode-", 6) || *sid) abort();
    if (mode == 21) return (HRESULT)0x80004005U;
    if (mode == 25) return 0;
    *sid = &target; return 0;
}
static int IsValidSid(PSID sid) { return sid && ((struct fake_sid *)sid)->valid; }
static int EqualSid(PSID left, PSID right) {
    return ((struct fake_sid *)left)->value == ((struct fake_sid *)right)->value;
}
static HANDLE GetProcessHeap(void) { return (HANDLE)(uintptr_t)2; }
static int HeapFree(HANDLE heap, DWORD flags, void *pointer) {
    if (heap != (HANDLE)(uintptr_t)2 || flags) abort();
    if (pointer == array) { if (release_stage > 2) forbidden++; release_stage = 2; arrays++; return mode != 14; }
    for (unsigned i = 0; i < 4097; i++) if (pointer == &sids[i]) {
        if (release_stage > 1) forbidden++; release_stage = 1;
        if (freed[i]++) duplicate_free++;
        sid_frees++; return mode != 13 || i != 1;
    }
    forbidden++; return 0;
}
static PSID FreeSid(PSID sid) {
    if (release_stage > 3) forbidden++; release_stage = 3;
    if (sid != &target || derived_frees++) { forbidden++; return sid; }
    return mode == 15 ? sid : NULL;
}
static int FreeLibrary(HMODULE library) {
    if (library != (HMODULE)(uintptr_t)1 || libraries++) abort();
    release_stage = 4;
    return mode != 16 && mode != 26;
}
/* These counted TEST symbols are never OS calls or network/profile mutations. */
int NetworkIsolationSetAppContainerConfig(DWORD n, void *p) { (void)n; (void)p; forbidden++; return 5; }
int connect(int a, void *b, int c) { (void)a; (void)b; (void)c; connect_calls++; return -1; }
int CreateAppContainerProfile(void) { profile_calls++; return -1; }
ACTUAL_PROFILE_VALIDATOR
#define printf receipt_printf
ACTUAL_CONFIG_TU
#undef printf
static int actual_mode_dispatch(int argc, wchar_t **argv) {
ACTUAL_FIXED_MODE_BRANCH
    return 2;
}
int main(int argc, char **argv) {
    if (argc != 2) return 90;
    mode = (unsigned)strtoul(argv[1], NULL, 10);
    for (unsigned i = 0; i < 4097; i++) {
        sids[i] = (struct fake_sid){1, (int)i + 100};
        array[i] = (SID_AND_ATTRIBUTES){&sids[i], 0xFFFFFFFFU};
    }
    if (mode != 1) sids[1].value = 7;
    if (mode == 11) sids[4095].value = 7;
    if (mode == 11) sids[1].value = 8;
    wchar_t *arguments[] = {L"fixed-helper", L"--observe-positive-loopback-config",
        mode == 99 ? L"bad" : L"icode-00000000000000000000000000000000"};
    int result = actual_mode_dispatch(3, arguments);
    fputs(receipt, stdout);
    printf("COUNTS %d %u %u %u %u %u %u %u %u %u %u %u %u\n", result, derives, queries,
        sid_frees, arrays, derived_frees, libraries, loads, exports,
        forbidden, connect_calls, profile_calls, duplicate_free);
    return result;
}
'''

def sample(phase="pre"):
    return {"schema_version":1,"scope":"positive_loopback_config_sample","status":"complete",
        "api_stage":"query","api_code":0,"entry_count":0,"target_match":False,"target_attributes":None,
        "sid_frees_attempted":0,"sid_frees_confirmed":0,"array_release":"not_acquired",
        "derived_sid_release":"confirmed","library_release":"confirmed","phase":phase,
        "process_reaped":True,"cleanup":"confirmed","observation_complete":True}


def c_body(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 1
    for index in range(opening + 1, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError("actual C function infrastructure truncated")


class TestPositiveLoopbackConfig(unittest.TestCase):
    def execute_positive(self, *, pre_stop=False, post_stop=False, clean=True, launch_error=False):
        source = REVIEWER.read_text(encoding="utf-8")
        start_marker = "                loopback_profile = capability_profile_name"
        if start_marker not in source:
            start_marker = "                try:\n                    capability_control = run_windows_appcontainer("
        start = source.index(start_marker)
        end = source.index("                expected_capability_payload = json.dumps(", start)
        block = textwrap.dedent(source[start:end])
        events, observed, notices, launches = [], [], [], []
        token = N(verified=True, package_sid_match=True)
        result = N(cleanup_ok=clean, child_token_receipt=token, detail="original-first",
                   executed=True, exit_code=105)
        def observe(executable, profile, phase):
            events.append(phase);observed.append((profile, phase))
            return sample(phase), pre_stop if phase == "pre" else post_stop
        def launch(*args, **kwargs):
            events.append("launch");launches.append((args, kwargs))
            if launch_error:
                raise OSError("original failure")
            return result
        def failed_result(*args):
            return N(cleanup_ok=args[3], child_token_receipt=None, detail=args[4],
                     executed=args[0], exit_code=args[1])
        namespace = dict(Path=Path, os=N(environ={"GITHUB_ACTIONS":"true","RUNNER_OS":"Windows",
            "ICODE_DIAGNOSTIC_WFP_PROBE_PATH":"fixed-helper"}),
            capability_profile_name=PROFILE, capability_argv=("fixed-positive-argv",),
            scratch=Path("fixed-scratch"),staged_runtime=Path("fixed-runtime"),
            _observe_positive_loopback_config=observe,
            _positive_loopback_unknown=lambda phase,status:dict(sample(phase),status=status),
            _positive_loopback_comparison=lambda pre,post,**kwargs:{"comparison":"unknown"},
            run_windows_appcontainer=launch,WindowsJobResult=failed_result,
            self=N(_workflow_json_notice=lambda *args:notices.append(args),fail=self.fail))
        failure = None
        try:
            exec(compile(block, str(REVIEWER), "exec"), namespace)
        except AssertionError as error:
            failure = str(error)
        return N(events=events,observed=observed,notices=notices,launches=launches,failure=failure)

    def setUp(self):
        # Old real Reviewer code executes its positive launch, but samples zero
        # times. That is semantic RED BEFORE accessing a missing mode/file/API.
        actual = self.execute_positive()
        self.assertEqual(actual.events, ["pre", "launch", "post"],
                         "POSITIVE_LOOPBACK_OBSERVATION_MISSING: actual positive flow must sample pre/post")
        self.assertIsNone(actual.failure)
        self.assertEqual(actual.observed, [(PROFILE,"pre"),(PROFILE,"post")])
        args, kwargs = actual.launches[0]
        self.assertEqual(args, (("fixed-positive-argv",),))
        self.assertEqual(kwargs["_diagnostic_profile_name"], PROFILE)
        self.assertEqual(kwargs["timeout_seconds"], 12)
        self.assertEqual(kwargs["process_limit"], 2)
        self.assertIs(kwargs["_diagnostic_private_network_capability"], True)
        self.assertIs(kwargs["_diagnostic_runtime_acl"], True)
        tree = ast.parse(PARENT.read_text(encoding="utf-8"))
        nodes = [ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0)]
        nodes += [node for node in tree.body if isinstance(node,ast.FunctionDef) and
                  (node.name.startswith("_positive_loopback_") or
                   node.name == "_observe_positive_loopback_config")]
        self.api = dict(json=json,re=re,Path=Path,subprocess=subprocess,time=time,os=os,
                        ctypes=ctypes,wintypes=wintypes)
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),
                     str(PARENT),"exec"),self.api)

    @contextlib.contextmanager
    def c_probe(self):
        compiler = shutil.which("cc")
        self.assertIsNotNone(compiler, "Linux software compiler infrastructure required")
        source = NATIVE.read_text(encoding="utf-8")
        validator = c_body(source, "static BOOL is_generated_profile_name(")
        branch = c_body(source, 'if (argc >= 2 && wcscmp(argv[1], L"--observe-positive-loopback-config")')
        probe = C_STUB.replace("ACTUAL_PROFILE_VALIDATOR",validator).replace(
            "ACTUAL_CONFIG_TU",CORE.read_text(encoding="utf-8")).replace("ACTUAL_FIXED_MODE_BRANCH",branch)
        with tempfile.TemporaryDirectory(prefix="loopback-config-software-") as temporary:
            binary = Path(temporary) / "stub"
            built = subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror",
                "-x","c","-","-o",str(binary)],input=probe.encode(),capture_output=True,timeout=20)
            self.assertEqual(built.returncode,0,built.stderr.decode("utf-8","replace"))
            def run(mode):
                actual = subprocess.run([str(binary),str(mode)],capture_output=True,timeout=2)
                self.assertLessEqual(len(actual.stdout)+len(actual.stderr),8192)
                self.assertFalse(actual.stderr)
                lines = actual.stdout.splitlines()
                counts = [int(x) for x in lines[-1].decode("ascii").split()[1:]]
                self.assertEqual(len(counts),13)
                self.assertEqual(actual.returncode,counts[0])
                self.assertEqual(counts[-4:],[0,0,0,0], "write/connect/profile/double-free")
                if mode == 99:
                    self.assertEqual(len(lines),1)
                    return None, counts
                self.assertEqual(len(lines),2)
                receipt = self.api["_positive_loopback_parse"](lines[0]+b"\n")
                return receipt, counts
            yield run

    def test_c_success_empty_and_maximum_ownership(self):
        with self.c_probe() as run:
            for mode,count,matched in ((0,2,True),(1,2,False),(2,0,False),(3,0,False),(11,4096,True)):
                with self.subTest(mode=mode):
                    result,calls=run(mode)
                    self.assertEqual((result["status"],result["entry_count"],result["target_match"]),
                                     ("complete",count,matched))
                    self.assertEqual(result["target_attributes"],0xFFFFFFFF if matched else None)
                    self.assertEqual(result["sid_frees_attempted"],count)
                    self.assertEqual(result["sid_frees_confirmed"],count)
                    self.assertEqual(calls[1:3],[1,1])
                    self.assertEqual(calls[3],count)
                    self.assertEqual(calls[4],0 if mode==2 else 1)
                    self.assertEqual(calls[5:9],[1,1,1,1])

    def test_c_query_error_is_not_empty_and_derive_hresult(self):
        with self.c_probe() as run:
            for mode in (4,21,22,26):
                result,calls=run(mode)
                self.assertEqual(result["status"],"api_error")
                self.assertIsNone(result["entry_count"])
                self.assertIsNone(result["target_match"])
                self.assertIsNone(result["target_attributes"])
                if mode==21:
                    self.assertEqual((result["api_stage"],result["api_code"]),("derive",0x80004005))
                    self.assertEqual(calls[2],0)
                    self.assertEqual(calls[5],0)
                else:
                    self.assertEqual((result["api_stage"],result["api_code"]),("query",5))
                    self.assertEqual(calls[2],1)
                self.assertEqual(calls[3:5],[0,0])

    def test_c_aliases_null_sid_and_duplicate_target_are_invalid(self):
        with self.c_probe() as run:
            for mode in (5,6,7,8,9,10,23,24,25):
                with self.subTest(mode=mode):
                    result,calls=run(mode)
                    self.assertEqual(result["status"],"invalid_data")
                    self.assertIsNone(result["target_match"])
                    self.assertIsNone(result["target_attributes"])
                    if mode==7:
                        self.assertEqual(calls[3:7],[2,1,1,1])
                    else:
                        self.assertEqual(calls[3:5],[0,0])
                    if mode in (10,23):
                        self.assertEqual(result["derived_sid_release"],"unknown")
                        self.assertEqual(calls[5],0)

    def test_c_all_release_failures_keep_original_query_result(self):
        with self.c_probe() as run:
            for mode in (13,14,15,16):
                with self.subTest(mode=mode):
                    result,calls=run(mode)
                    self.assertEqual((result["status"],result["api_stage"],result["api_code"]),
                                     ("complete","query",0))
                    self.assertEqual(self.api["_positive_loopback_cleanup"](result),"failed")
                    self.assertIsNone(result["target_match"])
                    self.assertIsNone(result["target_attributes"])
                    self.assertEqual(calls[3:7],[2,1,1,1])

    def test_c_loader_failures_and_returned_item_limit(self):
        with self.c_probe() as run:
            for mode,status in ((12,"limit_reached"),(17,"load_failed"),(18,"load_failed"),
                                (19,"load_failed"),(20,"unsupported")):
                result,calls=run(mode)
                self.assertEqual(result["status"],status)
                self.assertIsNone(result["target_match"])
                if mode==12:
                    self.assertIsNone(result["entry_count"])
                    self.assertEqual(calls[2:5],[1,0,0])
                    self.assertEqual(result["array_release"],"unknown")
                else:
                    self.assertEqual(calls[1:3],[0,0])
                if mode in (17,18):
                    self.assertEqual(calls[7:9],[0,0])

    def test_c_fixed_mode_cli_and_sdk_type_contract(self):
        with self.c_probe() as run:
            result,calls=run(99)
            self.assertIsNone(result)
            self.assertEqual(calls,[2]+[0]*12)
            result,calls=run(0)
            self.assertEqual(calls[1:3],[1,1])
        core = CORE.read_text(encoding="utf-8")
        self.assertIn("DWORD (WINAPI *PositiveLoopbackGetConfigFn)(DWORD *, PSID_AND_ATTRIBUTES *)",core)
        self.assertNotIn("NetworkIsolationFreeAppContainers",core)
        self.assertNotIn("LocalFree",core)
        self.assertNotIn("CoTaskMemFree",core)
        self.assertNotIn("FwpmFreeMemory",core)

    def test_parent_receipt_strict_schema_and_release_accounting(self):
        parse = self.api["_positive_loopback_parse"]
        wire = {k:v for k,v in sample().items() if k not in {
            "phase","process_reaped","cleanup","observation_complete"}}
        self.assertEqual(parse(json.dumps(wire).encode()+b"\n"),wire)
        changes = ({"schema_version":True},{"entry_count":True},{"api_code":-1},
                   {"target_attributes":True},{"status":[]},{"api_stage":{}},
                   {"array_release":[]},{"sid_frees_confirmed":1},
                   {"target_match":True,"target_attributes":0},{"extra":"hidden SID"},
                   {"status":"api_error"},{"api_code":None})
        for change in changes:
            with self.subTest(change=str(change)):
                value=dict(wire,**change)
                with self.assertRaises((ValueError,UnicodeError)):
                    parse(json.dumps(value).encode()+b"\n")
        raw=json.dumps(wire).encode()
        for bad in (raw,raw+b"\n\n",json.dumps(wire,indent=2).encode()+b"\n",
                    raw+b"\n{}",raw+b"\n"+raw+b"\n",b"X"*4097,
                    raw.replace(b'"schema_version": 1',b'"schema_version": 1,"schema_version": 1')+b"\n",
                    b"\xff\n"):
            with self.assertRaises((ValueError,UnicodeError)):
                parse(bad)

    def drive_parent(self, mode="normal"):
        with tempfile.TemporaryDirectory(prefix="loopback-parent-software-") as temporary:
            binary=Path(temporary)/"icode-wfp-event-probe.exe"
            binary.write_bytes(b"not executed")
            receipt={k:v for k,v in sample().items() if k not in {
                "phase","process_reaped","cleanup","observation_complete"}}
            streams={0:bytearray(json.dumps(receipt).encode()+b"\n"),1:bytearray()}
            if mode=="overflow":streams[0]=bytearray(b"X"*4097)
            if mode=="stderr":streams[1]=bytearray(b"X"*9000)
            if mode=="duplicate":streams[0]=bytearray(b'{"a":1,"a":2}\n')
            clock=[0.0];reads=[];actions=[];waits=[];launches=[]
            class Stream:
                def __init__(self,index):self.index=index
                def close(self):
                    if mode=="close_error":raise OSError("close failed")
            class Process:
                stdout=Stream(0);stderr=Stream(1);returncode=0
                def wait(self,timeout):
                    waits.append(timeout)
                    if mode=="unreaped" or mode=="kill_reap" and not actions or \
                            mode=="kill_reap" and actions[-1]=="terminate":
                        raise subprocess.TimeoutExpired("fixed",timeout)
                    self.returncode=9 if mode=="nonzero" else 0
                    return self.returncode
                def terminate(self):
                    actions.append("terminate")
                    if mode=="action_error":raise RuntimeError("termination request unavailable")
                def kill(self):actions.append("kill")
            process=Process()
            def launch(*args,**kwargs):
                launches.append((args,kwargs))
                if mode=="launch_failure":raise OSError("creation unavailable")
                if mode=="slow_creation":clock[0]+=3
                return process
            def chunk(stream,capacity):
                reads.append((stream.index,capacity))
                if mode in ("timeout","kill_reap","unreaped","action_error"):return b"",False
                data=bytes(streams[stream.index][:capacity]);del streams[stream.index][:capacity]
                return data,not streams[stream.index]
            namespace=self.api
            with patch.dict(namespace,_positive_loopback_pipe_chunk=chunk), \
                    patch.object(subprocess,"Popen",side_effect=launch), \
                    patch.object(time,"monotonic",side_effect=lambda:clock[0]), \
                    patch.object(time,"sleep",side_effect=lambda value:clock.__setitem__(0,clock[0]+value)):
                result,stop=namespace["_observe_positive_loopback_config"](binary,PROFILE,"pre")
            self.assertEqual(len(launches),1)
            args,kwargs=launches[0]
            self.assertEqual(args[0],[str(binary.resolve()),"--observe-positive-loopback-config",PROFILE])
            self.assertIs(kwargs["shell"],False)
            self.assertNotIn("capture_output",kwargs)
            self.assertTrue(all(1<=capacity<=4097 if index==0 else capacity==1 for index,capacity in reads))
            if mode=="slow_creation":self.assertFalse(reads)
            return result,stop,actions,waits

    def test_parent_bounded_pipe_and_actual_wait_receipt(self):
        result,stop,actions,waits=self.drive_parent()
        self.assertTrue(result["observation_complete"])
        self.assertTrue(result["process_reaped"])
        self.assertFalse(stop)
        self.assertEqual(actions,[])
        self.assertEqual(len(waits),1)
        self.assertLessEqual(waits[0],2.0)
        for mode in ("overflow","stderr","duplicate","nonzero","close_error"):
            with self.subTest(mode=mode):
                result,stop,actions,waits=self.drive_parent(mode)
                self.assertFalse(result["observation_complete"])
                self.assertIsNone(result["target_match"])
                self.assertTrue(result["process_reaped"])
                self.assertFalse(stop)

    def test_parent_launch_timeout_terminate_kill_and_unreaped_stop(self):
        for mode in ("launch_failure","slow_creation","timeout","kill_reap","unreaped","action_error"):
            with self.subTest(mode=mode):
                result,stop,actions,waits=self.drive_parent(mode)
                self.assertFalse(result["observation_complete"])
                self.assertIsNone(result["target_match"])
                if mode=="launch_failure":
                    self.assertEqual(result["status"],"launch_failed")
                    self.assertFalse(result["process_reaped"])
                    self.assertFalse(stop)
                    self.assertFalse(waits)
                elif mode=="unreaped":
                    self.assertEqual(actions,["terminate","kill"])
                    self.assertEqual(waits,[2.0,2.0])
                    self.assertTrue(stop)
                    self.assertFalse(result["process_reaped"])
                else:
                    self.assertEqual(result["status"],"timed_out")
                    self.assertTrue(result["process_reaped"])
                    self.assertFalse(stop)
                    self.assertEqual(actions,["terminate","kill"] if mode=="kill_reap" else ["terminate"])
                    self.assertEqual(waits,[2.0,2.0] if mode=="kill_reap" else [2.0])

    def test_two_endpoints_drift_and_parent_token_binding(self):
        compare=self.api["_positive_loopback_comparison"]
        token=N(verified=True,package_sid_match=True)
        pre,post=sample(),sample("post")
        self.assertEqual(compare(pre,post,same_parent_profile=True,token_receipt=token)["comparison"],
                         "consistent_endpoints")
        for key,value in (("target_match",True),("target_attributes",4),("entry_count",1)):
            changed=dict(post,**{key:value})
            self.assertEqual(compare(pre,changed,same_parent_profile=True,token_receipt=token)["comparison"],
                             "observed_drift")
        for changed in (dict(post,status="api_error"),dict(post,process_reaped=False),
                        dict(post,cleanup="unknown"),dict(post,observation_complete=False),
                        dict(post,phase="pre")):
            self.assertEqual(compare(pre,changed,same_parent_profile=True,token_receipt=token)["comparison"],"unknown")
        for binding,receipt in ((False,token),(True,None),(True,N(verified=False,package_sid_match=True)),
                                (True,N(verified=True,package_sid_match=False))):
            self.assertEqual(compare(pre,post,same_parent_profile=binding,token_receipt=receipt)["comparison"],"unknown")

    def test_real_positive_flow_stop_and_first_error_priority(self):
        self.assertEqual(self.execute_positive().events,["pre","launch","post"])
        pre=self.execute_positive(pre_stop=True)
        self.assertEqual(pre.events,["pre"])
        self.assertIn("pre helper was not reaped",pre.failure)
        self.assertFalse(pre.launches)
        post=self.execute_positive(post_stop=True)
        self.assertEqual(post.events,["pre","launch","post"])
        self.assertIn("post helper was not reaped",post.failure)
        self.assertTrue(any("first result preserved" in name for name,data in post.notices))
        failure=self.execute_positive(clean=False)
        self.assertEqual(failure.events,["pre","launch"])
        self.assertIn("original-first",failure.failure)
        raised=self.execute_positive(launch_error=True)
        self.assertEqual(raised.events,["pre","launch"])
        self.assertIn("OSError",raised.failure)

    def test_actual_peek_boundary_is_bounded_without_reader_thread(self):
        function=self.api["_positive_loopback_pipe_chunk"]
        available=N(value=20)
        reads=[]
        def peek(*args):
            args[4].value=available.value
            return True
        class Api:
            def __init__(self):self.PeekNamedPipe=peek
        fake=N(WinDLL=lambda *args,**kwargs:Api(),c_void_p=object,
               POINTER=lambda value:object,byref=lambda value:value)
        types=N(HANDLE=object,DWORD=lambda:N(value=0),BOOL=object)
        with patch.dict(sys.modules,msvcrt=N(get_osfhandle=lambda fd:fd)), \
                patch.dict(self.api,ctypes=fake,wintypes=types), \
                patch.object(os,"read",side_effect=lambda fd,size:reads.append(size) or b"X"*size):
            data,eof=function(N(fileno=lambda:8),3)
        self.assertEqual((data,eof),(b"XXX",False))
        self.assertEqual(reads,[3])
        core=CORE.read_text(encoding="utf-8")
        self.assertNotRegex(core,r"\b(?:NetworkIsolationSetAppContainerConfig|connect|socket|CreateAppContainerProfile)\s*\(")


if __name__=="__main__":
    unittest.main()
```

## Asset B: native/windows/icode_positive_loopback_config.inc

```c
/* Fixed positive-profile diagnostic only; no profile/network/config mutation. */
typedef DWORD (WINAPI *PositiveLoopbackGetConfigFn)(DWORD *, PSID_AND_ATTRIBUTES *);
_Static_assert(sizeof(DWORD) == 4, "Win32 DWORD width");
_Static_assert(sizeof(((SID_AND_ATTRIBUTES *)0)->Attributes) == 4, "SDK attributes width");

static int observe_positive_loopback_config(const wchar_t *profile) {
    HMODULE library = NULL;
    PositiveLoopbackGetConfigFn query = NULL;
    PSID target = NULL;
    PSID_AND_ATTRIBUTES entries = NULL;
    PSID pointers[4096];
    DWORD count = 0, code = 0, attributes = 0;
    unsigned attempted = 0, confirmed = 0, index, previous;
    int code_present = 0, count_present = 0, match = -1, target_alias = 0;
    int ownership_safe = 1, targets = 0;
    const char *status = "complete", *stage = "none";
    const char *array_release = "not_acquired", *target_release = "not_acquired";
    const char *library_release = "not_acquired";
    wchar_t path[MAX_PATH + 32];
    UINT length;
    HRESULT derived;
    if (!is_generated_profile_name(profile)) return 2;

    length = GetSystemDirectoryW(path, (UINT)(sizeof(path) / sizeof(path[0])));
    if (!length || length >= sizeof(path) / sizeof(path[0]) ||
        length + wcslen(L"\\FirewallAPI.dll") >= sizeof(path) / sizeof(path[0])) {
        status = "load_failed"; stage = "load";
        code = length ? ERROR_INSUFFICIENT_BUFFER : GetLastError(); code_present = 1;
        goto cleanup;
    }
    if (length < 3 || path[1] != L':' || path[2] != L'\\') {
        status = "load_failed"; stage = "load"; code = ERROR_INVALID_DATA; code_present = 1;
        goto cleanup;
    }
    wcscat(path, L"\\FirewallAPI.dll");
    library = LoadLibraryExW(path, NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!library) {
        status = "load_failed"; stage = "load"; code = GetLastError(); code_present = 1;
        goto cleanup;
    }
    library_release = "unknown";
    query = (PositiveLoopbackGetConfigFn)GetProcAddress(library, "NetworkIsolationGetAppContainerConfig");
    if (!query) {
        status = "unsupported"; stage = "export"; code = GetLastError(); code_present = 1;
        goto cleanup;
    }
    derived = DeriveAppContainerSidFromAppContainerName(profile, &target);
    stage = "derive"; code = (DWORD)derived; code_present = 1;
    if (target) target_release = "unknown";
    if (derived != S_OK) {
        status = "api_error";
        /* Failed derivation does not establish a safe owned SID. */
        goto cleanup;
    }
    if (!target || !IsValidSid(target)) {
        status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
        goto cleanup;
    }
    target_release = "confirmed"; /* Acquired and validated; actually freed below. */
    stage = "query"; code = query(&count, &entries); code_present = 1;
    if (entries) array_release = "unknown";
    if (code != ERROR_SUCCESS) {
        status = "api_error"; ownership_safe = 0;
        goto cleanup;
    }
    if (count > 4096) {
        status = "limit_reached"; ownership_safe = 0;
        goto cleanup;
    }
    count_present = 1;
    if (count && !entries) {
        status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
        goto cleanup;
    }
    if ((void *)entries == (void *)target && entries) {
        status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
        ownership_safe = 0; target_alias = 1;
        goto cleanup;
    }
    /* Validate the complete bounded ownership graph before comparisons/frees. */
    for (index = 0; index < count; ++index) {
        pointers[index] = entries[index].Sid;
        if (!pointers[index] || (void *)pointers[index] == (void *)entries ||
            pointers[index] == target) {
            if (pointers[index] == target) target_alias = 1;
            status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
            ownership_safe = 0;
            goto cleanup;
        }
        for (previous = 0; previous < index; ++previous) {
            if (pointers[index] == pointers[previous]) {
                status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
                ownership_safe = 0;
                goto cleanup;
            }
        }
        if (!IsValidSid(pointers[index])) {
            status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
            ownership_safe = 0;
            goto cleanup;
        }
    }
    for (index = 0; index < count; ++index) {
        if (EqualSid(target, pointers[index])) {
            targets++;
            attributes = entries[index].Attributes;
        }
    }
    if (targets > 1) {
        status = "invalid_data"; stage = "validate"; code = ERROR_INVALID_DATA;
    } else match = targets == 1;

cleanup:
    if (entries && ownership_safe) {
        for (index = 0; index < count; ++index) {
            attempted++;
            if (HeapFree(GetProcessHeap(), 0, pointers[index])) confirmed++;
        }
        array_release = HeapFree(GetProcessHeap(), 0, entries) ? "confirmed" : "failed";
    }
    if (target_alias) target_release = "unknown";
    if (target && !target_alias && strcmp(target_release, "confirmed") == 0)
        target_release = FreeSid(target) == NULL ? "confirmed" : "failed";
    if (library) library_release = FreeLibrary(library) ? "confirmed" : "failed";
    if (strcmp(status, "complete") || attempted != confirmed ||
        strcmp(array_release, "failed") == 0 || strcmp(array_release, "unknown") == 0 ||
        strcmp(target_release, "confirmed") ||
        strcmp(library_release, "confirmed"))
        match = -1;
    {
        char code_text[16], count_text[16], attributes_text[16];
        if (code_present) (void)snprintf(code_text, sizeof(code_text), "%lu", (unsigned long)code);
        else strcpy(code_text, "null");
        if (count_present) (void)snprintf(count_text, sizeof(count_text), "%lu", (unsigned long)count);
        else strcpy(count_text, "null");
        if (match == 1) (void)snprintf(attributes_text, sizeof(attributes_text), "%lu", (unsigned long)attributes);
        else strcpy(attributes_text, "null");
        printf("{\"schema_version\":1,\"scope\":\"positive_loopback_config_sample\","
            "\"status\":\"%s\",\"api_stage\":\"%s\",\"api_code\":%s,\"entry_count\":%s,"
            "\"target_match\":%s,\"target_attributes\":%s,"
            "\"sid_frees_attempted\":%u,\"sid_frees_confirmed\":%u,"
            "\"array_release\":\"%s\",\"derived_sid_release\":\"%s\",\"library_release\":\"%s\"}\n",
            status, stage, code_text, count_text, match < 0 ? "null" : match ? "true" : "false",
            attributes_text, attempted, confirmed, array_release, target_release, library_release);
    }
    return 0;
}
```

## Source patch: native/windows/icode_wfp_event_probe.c

```diff
*** Begin Patch
*** Update File: native/windows/icode_wfp_event_probe.c
@@ -138,6 +138,8 @@
     }
     return TRUE;
 }
+
+#include "icode_positive_loopback_config.inc"
 
 static BOOL parse_port(const wchar_t *value, UINT16 *port_out) {
     wchar_t *end = NULL;
@@ -2005,6 +2007,10 @@
     UINT16 remote_port;
     enum ProbePathValidation path_status;
 
+    if (argc >= 2 && wcscmp(argv[1], L"--observe-positive-loopback-config") == 0) {
+        if (argc != 3 || !is_generated_profile_name(argv[2])) return 2;
+        return observe_positive_loopback_config(argv[2]);
+    }
     if (argc == 2 && wcscmp(argv[1], L"--self-test") == 0) {
         return classifier_self_test() && history_scalar_self_test() ? 0 : 1;
     }
*** End Patch
```

## Source patch: scripts/run_windows_appcontainer_read_probe.py

```diff
*** Begin Patch
*** Update File: scripts/run_windows_appcontainer_read_probe.py
@@ -56,6 +56,238 @@
 _EXPECTED_SOURCE_CONTENTS = b"ICODE-READ-HANDLE-PROBE-v1\n"
 _DISPOSABLE_WORKSPACE_PREFIX = "icode-appcontainer-read-handle-"
 _SID_PATTERN = re.compile(r"(?i)(?<![A-Z0-9])S-\d+(?:-\d+)+(?![A-Z0-9])")
+
+
+# Positive-only diagnostic seam; never used as a Reviewer acceptance gate.
+def _positive_loopback_unknown(phase: str, status: str) -> dict[str, object]:
+    return {"schema_version": 1, "scope": "positive_loopback_config_sample",
+            "status": status, "api_stage": "none", "api_code": None, "entry_count": None,
+            "target_match": None, "target_attributes": None,
+            "sid_frees_attempted": 0, "sid_frees_confirmed": 0,
+            "array_release": "not_acquired", "derived_sid_release": "not_acquired",
+            "library_release": "not_acquired", "phase": phase, "process_reaped": False,
+            "cleanup": "unknown", "observation_complete": False}
+
+
+def _positive_loopback_cleanup(receipt: dict[str, object]) -> str:
+    releases = [receipt[key] for key in
+                ("array_release", "derived_sid_release", "library_release")]
+    if "failed" in releases or receipt["sid_frees_confirmed"] < receipt["sid_frees_attempted"]:
+        return "failed"
+    if "unknown" in releases:
+        return "unknown"
+    if receipt["entry_count"] is not None and receipt["sid_frees_attempted"] != receipt["entry_count"]:
+        return "unknown"
+    return "confirmed"
+
+
+def _positive_loopback_parse(raw: bytes) -> dict[str, object]:
+    if type(raw) is not bytes or not 0 < len(raw) <= 4096 or not raw.endswith(b"\n"):
+        raise ValueError("loopback receipt bounds")
+    line = raw[:-2] if raw.endswith(b"\r\n") else raw[:-1]
+    if b"\n" in line or b"\r" in line:
+        raise ValueError("loopback receipt must be one line")
+    text = raw.decode("ascii", "strict")
+    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
+        result = {}
+        for key, value in pairs:
+            if key in result:
+                raise ValueError("loopback duplicate key")
+            result[key] = value
+        return result
+    value = json.loads(text, object_pairs_hook=unique)
+    expected = set(_positive_loopback_unknown("pre", "not_attempted")) - {
+        "phase", "process_reaped", "cleanup", "observation_complete"}
+    if type(value) is not dict or set(value) != expected:
+        raise ValueError("loopback receipt shape")
+    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or \
+            value["scope"] != "positive_loopback_config_sample":
+        raise ValueError("loopback receipt version")
+    if type(value["status"]) is not str or value["status"] not in {
+            "complete", "unsupported", "load_failed", "api_error", "invalid_data", "limit_reached"}:
+        raise ValueError("loopback receipt status")
+    if type(value["api_stage"]) is not str or value["api_stage"] not in {"none", "load", "export", "derive", "query", "validate", "release"}:
+        raise ValueError("loopback receipt stage")
+    for key, maximum in (("api_code", 0xFFFFFFFF), ("entry_count", 4096),
+                         ("target_attributes", 0xFFFFFFFF)):
+        if value[key] is not None and (type(value[key]) is not int or not 0 <= value[key] <= maximum):
+            raise ValueError("loopback receipt integer")
+    for key in ("sid_frees_attempted", "sid_frees_confirmed"):
+        if type(value[key]) is not int or not 0 <= value[key] <= 4096:
+            raise ValueError("loopback release count")
+    if value["sid_frees_confirmed"] > value["sid_frees_attempted"]:
+        raise ValueError("loopback release accounting")
+    for key in ("array_release", "derived_sid_release", "library_release"):
+        if type(value[key]) is not str or value[key] not in {"not_acquired", "confirmed", "failed", "unknown"}:
+            raise ValueError("loopback release state")
+    if value["target_match"] is not None and type(value["target_match"]) is not bool:
+        raise ValueError("loopback match type")
+    if value["status"] == "complete" and (value["api_stage"] != "query" or value["api_code"] != 0 or
+            type(value["entry_count"]) is not int or value["target_match"] is True and value["entry_count"] == 0):
+        raise ValueError("loopback query completion")
+    clean = _positive_loopback_cleanup(value)
+    if value["status"] != "complete" or clean != "confirmed":
+        if value["target_match"] is not None or value["target_attributes"] is not None:
+            raise ValueError("loopback incomplete match")
+    else:
+        if type(value["entry_count"]) is not int or type(value["target_match"]) is not bool or \
+                value["derived_sid_release"] != "confirmed" or value["library_release"] != "confirmed":
+            raise ValueError("loopback complete ownership")
+        if value["entry_count"] and value["array_release"] != "confirmed":
+            raise ValueError("loopback array ownership")
+        if value["target_match"] and type(value["target_attributes"]) is not int or \
+                not value["target_match"] and value["target_attributes"] is not None:
+            raise ValueError("loopback attributes")
+    return value
+
+
+def _positive_loopback_pipe_chunk(stream: object, capacity: int) -> tuple[bytes, bool]:
+    """Peek before a bounded read; no reader thread or communicate/capture buffer."""
+    import msvcrt
+    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
+    kernel.PeekNamedPipe.argtypes = [
+        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
+        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
+    ]
+    kernel.PeekNamedPipe.restype = wintypes.BOOL
+    available = wintypes.DWORD()
+    handle = msvcrt.get_osfhandle(stream.fileno())
+    if not kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
+        if ctypes.get_last_error() in (109, 232):
+            return b"", True
+        raise OSError("loopback pipe peek failed")
+    if not available.value:
+        return b"", False
+    return os.read(stream.fileno(), min(capacity, int(available.value))), False
+
+
+def _positive_loopback_reap(process: subprocess.Popen[bytes]) -> bool:
+    """Only actual wait completion grants reaped; terminate/kill requests do not."""
+    for action in ("terminate", "kill"):
+        try:
+            getattr(process, action)()
+        except Exception:
+            pass
+        try:
+            process.wait(timeout=2.0)
+            return True
+        except Exception:
+            pass
+    return False
+
+
+def _observe_positive_loopback_config(
+    executable: Path | None, profile_name: str, phase: str,
+) -> tuple[dict[str, object], bool]:
+    """Return a public sample plus private stop flag for an actually unreaped child."""
+    sample = _positive_loopback_unknown(phase, "not_attempted")
+    if phase not in ("pre", "post") or type(profile_name) is not str or re.fullmatch(r"icode-[0-9a-f]{32}", profile_name) is None:
+        return sample, False
+    if executable is None:
+        return sample, False
+    try:
+        executable = executable.resolve(strict=True)
+        if not executable.is_file() or executable.name.casefold() != "icode-wfp-event-probe.exe":
+            return sample, False
+    except OSError:
+        return sample, False
+    process = None
+    reaped = False
+    reason = None
+    stdout = bytearray()
+    stderr_seen = False
+    eof = [False, False]
+    start = time.monotonic()
+    try:
+        process = subprocess.Popen(
+            [str(executable), "--observe-positive-loopback-config", profile_name],
+            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
+            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), shell=False,
+        )
+        while not all(eof):
+            remaining = 2.0 - (time.monotonic() - start)
+            if remaining <= 0:
+                reason = "timed_out"
+                break
+            for index, stream in enumerate((process.stdout, process.stderr)):
+                if eof[index]:
+                    continue
+                chunk, eof[index] = _positive_loopback_pipe_chunk(
+                    stream, max(1, 4097 - len(stdout)) if index == 0 else 1)
+                if index == 0:
+                    stdout.extend(chunk)
+                    if len(stdout) > 4096:
+                        reason = "protocol_error"
+                elif chunk:
+                    stderr_seen = True
+                    reason = "protocol_error"
+                if reason:
+                    break
+            if reason:
+                break
+            if not all(eof):
+                time.sleep(min(0.01, max(0.0, remaining)))
+        if reason is None:
+            try:
+                process.wait(timeout=max(0.0, 2.0 - (time.monotonic() - start)))
+                reaped = True
+            except (subprocess.TimeoutExpired, OSError):
+                reason = "timed_out"
+        if reason is None and time.monotonic() - start > 2.0:
+            reason = "timed_out"
+        if reason is None and (process.returncode != 0 or stderr_seen):
+            reason = "protocol_error"
+        if reason is None:
+            receipt = _positive_loopback_parse(bytes(stdout))
+            sample.update(receipt)
+            sample["cleanup"] = _positive_loopback_cleanup(receipt)
+            sample["observation_complete"] = (
+                receipt["status"] == "complete" and sample["cleanup"] == "confirmed")
+    except OSError:
+        reason = "launch_failed" if process is None else "protocol_error"
+    except Exception:
+        reason = "protocol_error"
+    finally:
+        if process is not None:
+            if not reaped:
+                reaped = _positive_loopback_reap(process)
+            for stream in (process.stdout, process.stderr):
+                try:
+                    stream.close()
+                except Exception:
+                    sample["cleanup"] = "unknown"
+                    sample["observation_complete"] = False
+            sample["process_reaped"] = reaped
+            if not reaped:
+                sample["cleanup"] = "unknown"
+                sample["observation_complete"] = False
+        if sample["cleanup"] != "confirmed" or sample["process_reaped"] is not True:
+            sample.update(target_match=None, target_attributes=None, observation_complete=False)
+        if reason is not None:
+            sample.update(status=reason, target_match=None, target_attributes=None,
+                          observation_complete=False)
+    return sample, process is not None and not reaped
+
+
+def _positive_loopback_comparison(
+    pre: dict[str, object], post: dict[str, object], *,
+    same_parent_profile: bool, token_receipt: object,
+) -> dict[str, object]:
+    comparison = "unknown"
+    try:
+        bound = same_parent_profile is True and token_receipt is not None and \
+            getattr(token_receipt, "verified", None) is True and \
+            getattr(token_receipt, "package_sid_match", None) is True
+    except Exception:
+        bound = False
+    if bound and all(sample.get("phase") == phase and sample.get("status") == "complete" and
+                     sample.get("process_reaped") is True and
+                     sample.get("cleanup") == "confirmed" and
+                     sample.get("observation_complete") is True
+                     for sample, phase in ((pre, "pre"), (post, "post"))):
+        keys = ("target_match", "target_attributes", "entry_count")
+        comparison = "consistent_endpoints" if all(pre[k] == post[k] for k in keys) else "observed_drift"
+    return {"pre": pre, "post": post, "comparison": comparison}
 
 
 def _file_digest(path: Path) -> str:
*** End Patch
```

## Source patch: tests/test_windows_appcontainer.py

```diff
*** Begin Patch
*** Update File: tests/test_windows_appcontainer.py
@@ -32,6 +32,9 @@
 import icode.windows_appcontainer as windows_appcontainer
 import icode.windows_job as windows_job_module
 from scripts.run_windows_appcontainer_read_probe import (
+    _observe_positive_loopback_config,
+    _positive_loopback_comparison,
+    _positive_loopback_unknown,
     _classify_wfp_ipv6_loopback_receipt,
     _print_wfp_observer_diagnostics,
     _publish_wfp_ipv6_loopback_target,
@@ -8248,6 +8251,25 @@
                     str(staged_executable), ipv4_loopback_port, ipv6_loopback_port,
                     capability_nonce, capability_package_sid,
                 )
+                loopback_profile = capability_profile_name
+                loopback_helper = None
+                loopback_helper_value = os.environ.get("ICODE_DIAGNOSTIC_WFP_PROBE_PATH", "")
+                if (
+                    os.environ.get("GITHUB_ACTIONS") == "true"
+                    and os.environ.get("RUNNER_OS") == "Windows"
+                    and loopback_helper_value
+                ):
+                    loopback_helper = Path(loopback_helper_value)
+                loopback_pre, loopback_pre_unreaped = _observe_positive_loopback_config(
+                    loopback_helper, loopback_profile, "pre",
+                )
+                if loopback_pre_unreaped:
+                    self._workflow_json_notice("Windows positive loopback configuration", {
+                        "pre": loopback_pre,
+                        "post": _positive_loopback_unknown("post", "not_attempted"),
+                        "comparison": "unknown",
+                    })
+                    self.fail("positive loopback pre helper was not reaped; original experiment not run")
                 try:
                     capability_control = run_windows_appcontainer(
                         capability_argv, cwd=scratch, timeout_seconds=12,
@@ -8261,11 +8283,32 @@
                         False, None, "diagnostic_exception", False,
                         type(exc).__name__,
                     )
+                loopback_post = _positive_loopback_unknown("post", "not_attempted")
+                loopback_post_unreaped = False
+                if capability_control.cleanup_ok:
+                    loopback_post, loopback_post_unreaped = _observe_positive_loopback_config(
+                        loopback_helper, loopback_profile, "post",
+                    )
+                self._workflow_json_notice(
+                    "Windows positive loopback configuration",
+                    _positive_loopback_comparison(
+                        loopback_pre, loopback_post,
+                        same_parent_profile=(loopback_profile == capability_profile_name),
+                        token_receipt=capability_control.child_token_receipt,
+                    ),
+                )
                 if not capability_control.cleanup_ok:
                     self.fail(
                         "private-network positive-control Job/profile/ACL cleanup did not verify: "
                         f"{capability_control.detail}"
                     )
+                if loopback_post_unreaped:
+                    self._workflow_json_notice("Windows private-network first result preserved", {
+                        "executed": capability_control.executed,
+                        "exit": capability_control.exit_code,
+                        "cleanup": capability_control.cleanup_ok,
+                    })
+                    self.fail("positive loopback post helper was not reaped; candidate not run")
                 expected_capability_payload = json.dumps(
                     {
                         "nonce": capability_nonce,
*** End Patch
```

## Source patch: .github/workflows/ci.yml

```diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@ -60,6 +60,8 @@
           python-version: ${{ matrix.python-version }}
       - name: Install the declared build backend for package tests
         run: python -m pip install "setuptools>=80"
+      - name: Strict positive loopback configuration software contract
+        run: python -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_windows_loopback_config_observation.py'); assert s.countTestCases()==12, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
       - name: Compile Python sources
         run: python -m compileall -q src tests scripts
       - name: Run the full unit test suite
@@ -595,6 +597,7 @@
           $wfpProbe = Join-Path $buildDirectory 'Release/icode-wfp-event-probe.exe'
           & $wfpProbe --self-test
           if ($LASTEXITCODE -ne 0) { throw "IPv6 WFP observer self-test failed: $LASTEXITCODE" }
+          Write-Host ("positive-loopback-helper-sha256=" + (Get-FileHash -LiteralPath $wfpProbe -Algorithm SHA256).Hash.ToLowerInvariant())
           Add-Content -Path $env:GITHUB_ENV `
             -Value "ICODE_DIAGNOSTIC_WFP_PROBE_BUILD=$wfpProbe" -Encoding utf8
       - name: Cross-check Windows SDK WFP ABI (x64/ARM64)
@@ -1267,8 +1270,12 @@
             New-Item -ItemType Directory -Path $probeRoot | Out-Null
             & icacls.exe $probeRoot /grant "*${sid}:(OI)(CI)M" /Q
             if ($LASTEXITCODE -ne 0) { throw "reviewer_probe_root_acl_failed exit=$LASTEXITCODE" }
             Copy-Item -LiteralPath $env:ICODE_DIAGNOSTIC_WFP_PROBE_BUILD `
               -Destination $wfpProbeForUser -ErrorAction Stop
+            $positiveLoopbackBuildHash = (Get-FileHash -LiteralPath $env:ICODE_DIAGNOSTIC_WFP_PROBE_BUILD -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
+            $positiveLoopbackStagedHash = (Get-FileHash -LiteralPath $wfpProbeForUser -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
+            if ($positiveLoopbackStagedHash -cne $positiveLoopbackBuildHash) { throw 'positive_loopback_staged_helper_hash_mismatch' }
+            Write-Host ("positive-loopback-staged-helper-sha256=" + $positiveLoopbackStagedHash)
 
             $profileBootstrap = Start-Process `
               -FilePath (Join-Path $env:SystemRoot 'System32/cmd.exe') `
*** End Patch
```
