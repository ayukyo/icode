# Windows 目录伪项身份校验顺序设计

状态：DESIGN ONLY，2026-10-13。基线 main `0a980e0130873020881a6892d88715948af909a7`。权威工作区 `/home/orbbec/projects/icode`；Windows 访问入口为 `\\wsl.localhost\Ubuntu-22.04\home\orbbec\projects\icode`。本设计不表示正式 TEST、SOURCE、原生或 CI 已通过。

## 问题与证据上限

三问均已确认：真实 Windows 空目录可被拒绝；现有 parser 已准确忽略 `.`/`..`，无需另建枚举器；调用链是 native backend → collector → parser → shared walker → workspace snapshot / Git tree OID。

[交接证据](../../development-handoff.md)记录 Windows 10 build 19045 / AMD64 / CPython 3.11.4：自有空 TemporaryDirectory 的 class 20 原生页包含有效 ID 的 `.` 与全零 16-byte ID 的 `..`，原 parser 在解码名称前以 `windows_directory_record_invalid` 拒绝。研究者与 root 分别复现并确认句柄/临时目录回收。root RAM 仅移动判据，原 34 项从 2 FAIL / 2 ERROR 变为 1 FAIL / 0 ERROR；三个快照相关失败消失，剩余 `test_control.py` POSIX 路径硬编码断言不属于本片。RAM 不是正式 RED/GREEN 或原生产品验收。

root 开工已完成真实 sequential-thinking 三步（9c225a）：需求分解为伪项兼容片与路径断言片；方案分析优先复用既有准确伪项识别和 collector；风险评估要求真实子项身份与所有记录边界保持严格。本文件不另扩功能。

## 方案决策

| 方案 | ICODE 当前机制及影响 | 决策 |
| --- | --- | --- |
| 准确识别 dot 后，仅对会输出的真实 child 校验 ID | 复用既有名称过滤，生产差分小于 10 行；正常伪项不产生 `_WindowsDirectoryEntry` 或子句柄，真实 child 保留拒绝 | 采纳 |
| 对所有记录一律先拒绝零 ID | 当前实现；严格记录身份但把不进入 walker 的 OS 伪项误拒，无法满足正常空目录 | 不适配 |
| 所有名称均允许零/FF ID | 会输出无可信身份的真实 child，削弱 enumeration/handle identity 契约 | 不适配 |

准确名称仅为解码后的 `.`、`..`，不 trim、不 casefold、不按前缀过滤。`. `、`.. `、`...` 均视为普通名称，零/FF ID 必须拒绝。FF 伪项仅被排除，不承认其身份有效；本机观察只证明零 ID，不声称 OS 实际返回 FF。

## 最小实现与不变契约

生产 parser 仅改 `src/icode/workspace_snapshot.py::_parse_windows_directory_entries`：从现有 structural `if` 移除 `file_id in (bytes(16), bytes([0xFF]) * 16)`，在既有 `if name:` 最前以同一表达式和同一 reason 拒绝；增加注释说明准确 dot 伪项不产生子句柄。

实际 native CI 通过 `scripts/run_windows_tree_ci.py` 的固定模块 tuple 收集，目前只有旧 tree 模块。必须给该 tuple 加唯一 `tests.test_windows_dot_entry_identity` 条目；`tests/test_run_windows_tree_ci.py` 的既有 loader.loaded 断言同步为有序两个模块。先改该唯一 TEST 断言并获得真实 RED，再改 runner tuple；日志防注入/错误分类/权限/workflow 均不变。不接线就不能声称新 SHA native 测试已 hit。

顺序为 buffer/header/length/time/EOF → UTF-16/name → 准确 dot 转空 → 真实 child ID/duplicate/append → trailing/offset。不得用 `continue` 跳过记录尾部检查。非 dot 无效名称与无效 ID 同时存在时，名称 reason 将优先；这是顺序调整的明确影响，未引入新公开 API 或新 reason。

函数签名、tuple/dataclass 字段、正常 child metadata、collector class20→class19/EOF18/no-progress、上限、重复名称判据均不变。`_require_windows_directory_handle`、`_require_windows_entry_identity`、`_require_windows_symlink_identity`、`_validate_windows_directory_listing` 及所有 root/child handle identity 校验完全不变。`windows_worktree.py`、权限/ACL/helper/isolation/retry、POSIX 流程、Git OID 与 workspace hash 合同不修改。

## 验收矩阵

正式新文件 `tests/test_windows_dot_entry_identity.py` 用真实生产 parser/collector；仅复用完整读过的 `tests.test_windows_worktree_tree_oid._directory_record`，它固定 88-byte header、UTF-16LE 名称和指定 offset 的零 padding。signed 负字段通过 pack `<q` 注入，避免 helper `<Q` 产生夹具错误。

| 测试 | 必须结果 |
| --- | --- |
| 两个准确 dot × zero/FF/valid ID | 输出空 tuple；FF 不输出身份 |
| 对齐 dot+dotdot+真实 child 页 | 仅 child，全部六字段完全相等 |
| 普通/近似 dot × zero/FF ID | `windows_directory_record_invalid` |
| dot header/name 长度 0/奇数/超界/超长、负 ChangeTime/EOF | `windows_directory_record_invalid` |
| 孤立代理项、NUL/分隔符/冒号名称 | `windows_directory_name_invalid` |
| dot offset 不对齐/不足/越界、trailing 非零、截断 header | 对应固定 offset/trailing/truncated reason |
| 首个 dot-only 页后 child 页与 EOF18 | 实际 parser，调用 class `[20,19,19]`，仅 child |
| 首个 dot-only 页后 EOF18 | class `[20,19]`，空结果，不把首成功页当 EOF |
| 第二个 dot-only 成功页 | class `[20,19]`，`windows_directory_enumeration_no_progress` |
| 原 CI loader 合同 | 固定有序两模块被同一安全 runner 收集，原防注入用例保留 |
| Windows 自有空临时目录 | 实际 `snapshot_workspace(root) == {}`，empty tree SHA1 正确 |
| Windows 文件及 nested empty 目录 | 实际 snapshot 精确 SHA256、OID 精确独立 hashlib SHA1；empty directories 不入 tree |

便携字节测试无平台 skip，不能冒称 native。两条 native 仅 `os.name != 'nt'` 显式 skip；Windows 遇权限、unsupported、身份或清理错误必须失败。无需 shell Git、管理员权限、symlink 或额外依赖。

## 调研与安全影响

复用交接中 2026-10-13 官方 [FILE_ID_EXTD_DIR_INFO 布局](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_extd_dir_info)和 [FILE_INFO_BY_HANDLE_CLASS](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ne-minwinbase-file_info_by_handle_class)观察，属于官方文档而非开源实现。文档布局支持字段位置与 class 的现有用法；不承诺伪项 ID 非零，零 ID 的事实来源是原生实测。主代理独立只读研究补充现有 live 条目；本作者不重复全名单或改 live。

主代理独立研究者在 2026-10-13 12:43:54–12:44:22 UTC 取回并核 Codex 固定提交 `8c0f7011674145da7e10627769fb221c74fbf7a0` 的 [no_reparse_dir.rs](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs#L118-L140)、[relative guard](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs#L205-L245)、[Apache-2.0 LICENSE](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/LICENSE)及 Microsoft [Naming](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)，本作者复用其只读报告：借鉴持有目录句柄、不遍历 reparse 的边界原则，ICODE 已有相应 backend/walker。该 Codex 文件没有 EXTD parser，不能证明 dot 零 ID 或替本片原生实测；不复制源码。

采纳现有过滤机制的校验顺序修复，收益为合法空目录兼容，成本为新定点正负控及同 SHA 原生 CI；无复制第三方代码，无新增许可、依赖或权限。暂缓剩余路径断言、整套 Windows 兼容结论、installed/native isolation、R2/R3 总体验收；不适配放宽所有 ID、增加 retry、扩大忽略集合、隐藏失败。

## 交付门与白名单

顺序：两份文档 fresh SPEC→不同 QUALITY 全部 C0/I0/M0 → TEST ONLY 作者正式 RED → root 独立确认有效 assertion RED → 不同 SOURCE 作者小差分 → 定点 GREEN → 实际 SOURCE 两审 → 密钥/固定子仓检查 → main 候选线上验收。旧 RAM 不授 SOURCE GO。本机不默认全量，构建若必须默认 -j1、最多 -j6。

必须等待 `0a980e0130873020881a6892d88715948af909a7` 的对应 CI 终态，再由 root 推下一候选；新候选绑定实际 SHA/workflow/job/platform/raw log/exit，失败与 skip 原样保留，不能替代阶段通过。

精确发布白名单：`src/icode/workspace_snapshot.py`、`scripts/run_windows_tree_ci.py`、`tests/test_windows_dot_entry_identity.py`、`tests/test_run_windows_tree_ci.py`、本 DESIGN、`docs/nbl/plans/2026-10-13-windows-dot-entry-identity.md`、`docs/agent-landscape-live.md`、`docs/development-handoff.md`，共八路径。其余文件、vendor、配置、workflow、Windows 旧链接全部受保护。不建 branch/worktree/tag。本次作者仅写两个文档，不能提交/推送或改 SOURCE/TEST。

## 自审（仅文档门）

SPEC C0/I0/M0：上述矩阵逐项对应 PLAN 的新 TEST fence、唯一既有 TEST diff 与两个生产 diff；无遗漏范围、失配接口或越权步骤。QUALITY C0/I0/M0：夹具边界、assertion RED、collector progression、独立 hash oracle、原生 CI 收集接线、平台信用及发布门均明确；不是不同审查者的独立批准。

【架构级自检报告】
- ✅ 语法/编译：TEST fence 已 ast.parse/compile（10 方法）通过，diff whitespace 检查 exit 0；正式源码未改。
- ✅ 依赖/调用链：既有 parser/helper/collector/public 入口已核。
- ✅ 逻辑/边界：准确 dot、普通 sentinel 和完整记录边界覆盖。
- ✅ 异常处理：固定 reason 与失败关闭保留。
- ✅ 关联模块：拟 parser 判据顺序与固定 CI 模块收集接线；上游/下游契约已标明。
- ✅ 兼容安全：身份/权限/隔离规则不放宽。
- ✅ 可运行性：PLAN 给出完整测试资产、diff 与命令；实现尚未授权执行。
