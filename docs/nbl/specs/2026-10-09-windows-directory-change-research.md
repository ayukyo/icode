# Windows 初始快照目录变化：只读诊断记录

观察日期：2026-10-09；基线 main `ccbe67bb65d5246a61fb3078b85c83fba5aa7c42`。独立研究与 root 分别回读同一公开决定性日志、fixture 与实际 walker。仅记录新失败和诊断候选，不实施修复、不宣称根因已确认。

## 当前实际证据

[CI37840482757 x64 workspace job113528293532](https://github.com/ayukyo/icode/actions/runs/37840482757/job/113528293532) 在2026-10-08 20:40:38UTC记录 ERROR：`TestContractEngineering.test_incremental_cp_worklist_history_without_old_bodies_blocks_export` → `gate_fixture(git_workspace=True)` → `baseline = runner._snapshot(root)` → `OSError: snapshot unavailable (windows_directory_changed)`。455 total、1FAIL、1ERROR、20SKIP；另一个legacy code FAIL是Git10038，与这个ERROR分开。

同SHA ARM workspace job113528293556也有455 total、1FAIL、1ERROR、20SKIP，但该incremental ERROR是inspection基线Git10093；legacy code FAIL是Git10038。未观察到ARM同样的目录变化错误，不以一格结论覆盖另一格。root后续独立核CI整体终态：44个jobs中36成功、4失败、3跳过、1取消；上述数字仅为两个workspace job结果。

公开日志没有该x64 fixture的root或最深失败目录、拒绝分支、差异字段。邻近legacy失败的临时目录与venv诊断路径属于其它调用，不能拿来定位本ERROR。

fixture顺序已核：创建临时目录，写`changed.py=value 0`，同步Git init/add/commit返回，然后立即读取baseline。后续`value 1`、`next_out_dir`、CP create及inspection尚未发生，所以不能归因于本测试后续控制面写入。Git已经存在不证明它的后台活动导致变化。

## 两个同名拒绝点

| 实际代码位置 | 比较对象 | 目前缺的证据 |
|---|---|---|
| workspace_snapshot.py:533–536 | 同目录before/after listing签名：name/attributes/tag/FileId/ChangeTime/EndOfFile | 哪个scope、membership/identity/metadata哪类差异 |
| workspace_snapshot.py:544–545 | 同一held目录handle前后签名：volume/ID/type属性/tag/ChangeTime/EndOfFile/directory/delete_pending | 哪个scope、哪个固定字段变化 |

listing拒绝时final-handle查询尚未执行，不能把后者标为相同。snapshot投影包含根`.git`；只有Git-tree投影排除它。忽略`.icode_output`/`__pycache__`的内容不等于忽略其父目录entry签名。

现`windows_worktree.snapshot_windows_workspace_windows`已有最多两次全新尝试，第一次目录变化会先关闭全部handles再重开root；最终同reason表示两次都拒绝。不得增加重试、sleep、skip或扩大忽略集合制造通过。held相对no-reparse handles不等于全树namespace锁；既有跨entry/handle差异兼容不授权放宽同一对象before/after检查。

## 官方原文与决策

root另读[Microsoft FILE_BASIC_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_basic_info)：ChangeTime指metadata变化，LastWriteTime涉及数据流；所以ChangeTime差异不等于源码正文变动。[FILE_ID_EXTD_DIR_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_id_extd_dir_info)列出listing各字段。这些说明没有为本事件确认缓存、非原子观察、Git或Defender根因。

**采纳候选：**仅测试专用观察wrapper，用原调用已经取得的records分辨两拒绝点，固定attempt1/2、最深scope分类root/git_metadata/ignored_control/other_descendant/unavailable、固定字段差异位图。listing先失败时handle结果明确not_observed。原函数调用一次、原异常/返回/retry/cleanup顺序完全保留，不能新enumerate/query或输出真实path/name/ID/volume/timestamp/正文/raw异常；深层失败冒泡不能覆盖初始scope。

收益是可区分现有同reason，成本为测试诊断与mock正负控、后续同SHA双架构原生重验；不新增运行依赖、产品接口、系统权限或上游源码复制。**暂缓：**任何稳定性修复，必须先取得对应证据；**不适配：**称flaky、凭同格其它路径定位、宽松字段过滤或第三次重试。开源借鉴机制沿本阶段独立Aider/Codex配置与执行证据分离，不声称上游有同款Windows目录诊断。

## 验收边界

此研究未改源码、未运行测试/native/model或变更CI。root已独立核日志和上述两个抛点，不能定位最终拒绝的具体scope；当前`unverified`。后续独立诊断设计/TDD/双审/完整软件门与Windows真实receipt是前置，不以本机软件或文字片通过关闭Windows/R2/R3门。
