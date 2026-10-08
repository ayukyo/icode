# Windows 快照拒绝：测试专用诊断设计

日期2026-10-09；基线main ccbe67。本设计沿用户连续开发授权自主推进，不扩权限、不修上游Git或产品快照判据。当前文案源码仍冻结跑完整守卫；本片实施必须在其发布之后。

## 三问与方案

真实问题是同SHA x64 contract fixture初始baseline出现`windows_directory_changed`，实际有listing与held-handle两个拒绝位置，当前日志无法区分。ARM该fixture为Git10093，不是相同根因证据。现walker和两次全新snapshot尝试已实现；现测试有walker别名hook先例，但旧ChangeTime探针多做查询且改写异常，不能整套复用。

采用A：仅测试中包原signature函数和walker，分类原调用已返回的签名；不代理native backend。B为生产增加异常reason，会影响retry/兼容，暂缓。C增加重试或忽略ChangeTime，不适配，因为没有根因。A收益是取得两个拒绝点及字段差异，成本测试helper/软件正负控制与后续原生复验；没有产品接口、依赖、特权或第三方代码复制。

## 文件、入口与调用保护

新增`tests/windows_snapshot_rejection_diagnostic.py`负责上下文管理器和闭集回执，新增`tests/test_windows_snapshot_rejection_diagnostic.py`软件测试。`tests/test_contract_engineering.py`只在git_workspace fixture的baseline snapshot调用上使用context；非Windows不装hook，调用原snapshot一次。为既有Windows workspace job消费软件测试，需要在`scripts/run_workspace_ci.py`现有DEFAULT新增该module并在`tests/test_run_workspace_ci.py`配对断言。不修改`src/`、vendor、CI权限、matrix或任何生产异常reason。

context只patch以下四个引用：workspace_snapshot中的两个signature函数、workspace_snapshot递归walker、windows_worktree已import的顶层walker别名。进入前保存原callables；退出用ExitStack/unittest.mock.patch恢复。每个wrapper只调用原callable一次，保持位置/关键字参数、原返回值对象和原异常对象；异常使用bare raise。不得再query/enumerate/open/read/重试/sleep或捕获原异常后返回success。只观察进入context的线程，其它线程直接透传；全进程仅一个context能安装hook，用本helper专有非阻塞Lock取得安装所有权，未取得的同线程嵌套/其它线程重叠context透明透传且不输出、不等待、不安装或恢复其它owner的hook。所有权持有至本owner退出恢复完成。hook安装失败须先恢复已经安装的部分并释放owner，再无hook执行原context body，不能阻断原snapshot。

scope frame在原walker执行前push，finally恢复进入前的栈；原kwargs的snapshot_parts仅分类，不输出或另保存路径。根frame（is_root=True/depth=0）给attempt1或2；递归不加attempt。生产允许depth0..128，故诊断最多129个frames；frame建立失败或第130个frame时，整个该子树暂停signature观察，不能借用父frame，实际拒绝仅记该有效attempt的diagnostic_unavailable。退出溢出子树后恢复父栈；不改变原调用或资源门。第三个root walker违反本context仅一个最多两次snapshot调用的观察合同：此时整个context停止观察并不输出，不增第三槽、不覆盖前两有效记录、不因第三次拒绝改写第二槽。push/pop/分类/记槽异常同样只能降级诊断，不能遮蔽原返回或错误。

## 比较与最深拒绝

listing wrapper先取得原生产signature tuple，再观察当前frame的两个返回值。frame只有一对listing签名；顺序先before后after。保留引用用于这次对比，退出立即释放，不保留全树历史。原tuple已排序且名称唯一，必须用两指针merge计算membership、字段及分类OR位图，不另建name字典/集合或重排序；除原返回tuple引用、有限frame及两record外，比较额外空间为常数级。若两签名相等，才允许观察随后该frame的两个held-directory signature返回值；此前文件或目录symlink的signature调用不计入。这样不会把文件hash检查混成最终目录handle检查。

只有原walker实际抛`WorktreeTreeUnavailable`且reason恰为`windows_directory_changed`，才记录拒绝。listing签名不同则stage=listing、handle=not_observed；listing相同且两个handle签名不同则stage=held_handle。其它组合stage=unavailable，不能猜测。每attempt用setdefault锁定第一个最深失败frame，父级异常冒泡不覆盖。listing相同只是这两次观察相同，不证明扫描期间namespace从未变化。

scope闭集为root/git_metadata/other_descendant/unavailable：空parts是root；非空且首组件恰为`.git`是git_metadata；其它parts均other_descendant，非法parts为unavailable。例如`.git/hooks`继承git_metadata，`subdir/.git`是other_descendant。ignored_control不进入walker，不能凭父listing中忽略entry变更虚构它是最深walker。

listing另附changed_entry_class：git_metadata/ignored_control/other/mixed/not_observed/unavailable。固定优先级：frame在根`.git`子树内则所有差异entry都git_metadata；否则root frame中entry名恰为`.git`归git_metadata；否则entry名为`.icode_output`或`__pycache__`归ignored_control；其它为other（包括嵌套`.git`）。类别内部用1/2/4 OR汇总，多个类别归mixed。只分类实际差异entry的既有name；不输出name、不输出数量或具体entry。文件不存在/新增只算membership位，不假造未同时观察的其它字段相同。非listing拒绝不归entry类，填not_observed；诊断失败填unavailable。

listing固定差异bit：membership=1、attributes=2、normalized_reparse_tag=4、file_id=8、change_time=16、end_of_file=32。共同name按原签名比较，新增/移除name只赋membership；不额外解析native records。handle固定bit：volume=1、file_id=2、type_attributes=4、normalized_reparse_tag=8、change_time=16、end_of_file=32、is_directory=64、delete_pending=128。这些bit表示字段差异，不能推断源码正文或Git/Defender根因。

## 输出与失败处理

context body只包一个原snapshot调用。若至少一次actual目录拒绝被观察，退出context时输出一次`ICODE_WINDOWS_SNAPSHOT_REJECTION=`前缀的ASCII JSON行；第一次拒绝而第二次成功也必须输出，call_outcome仅表示最终调用returned或raised，不代表readiness。完全没有目录拒绝的干净成功/其它错误不输出。

JSON顶层固定且仅有`schema_version`（整数1）、`call_outcome`（returned/raised）、`attempts`（按1/2固定两个objects）。每record固定且仅有`attempt`（整数1或2）、`status`（directory_rejected/completed/other_error/not_observed/diagnostic_unavailable）、`scope`、`reject_stage`（listing/held_handle/none/not_observed/unavailable）、`changed_entry_class`、`listing_difference_mask`、`handle_observation`（not_observed/same/different/unavailable）、`handle_difference_mask`。槽只描述第1/2次root walker的观察退出，不描述外围完整snapshot attempt：completed仅表示该root walker返回，不证明close_root或最终调用成功；other_error是该root walker观察到其它异常；not_observed仅表示未观察到该root walker，不推断外围attempt没开始。open_root/close_root均不新增hook，最终原snapshot结果另由call_outcome表达。

directory_rejected/listing的listing mask为1..63，handle为not_observed/null；directory_rejected/held_handle的listing mask=0，handle=different且mask1..255。该二种scope按上文，stage/class与比较所得一致。非拒绝的completed/other_error及未运行not_observed槽均scope=unavailable、class=not_observed、两mask=null、handle=not_observed，stage分别none/none/not_observed。diagnostic_unavailable槽scope/class/stage/handle均unavailable，mask=null；必须实际拒绝已观察且诊断不可用才采用该status。不把0与null混用或把没有比较写same。

典型第一拒绝第二成功：`{"schema_version":1,"call_outcome":"returned","attempts":[{"attempt":1,"status":"directory_rejected","scope":"root","reject_stage":"listing","changed_entry_class":"ignored_control","listing_difference_mask":1,"handle_observation":"not_observed","handle_difference_mask":null},{"attempt":2,"status":"completed","scope":"unavailable","reject_stage":"none","changed_entry_class":"not_observed","listing_difference_mask":null,"handle_observation":"not_observed","handle_difference_mask":null}]}`。两次held_handle ChangeTime拒绝则call_outcome=raised、两个status=directory_rejected、stage=held_handle、class=not_observed、listing mask=0、handle=different/16，scope按各frame。第一拒绝后第二open_root失败：call_outcome=raised，第二root walker槽not_observed；第一拒绝后第二root walker返回而close_root失败：call_outcome=raised，第二槽仍completed。不得据这两个槽推断外围attempt未开始、cleanup成功或任务readiness。

不得输出raw错误、traceback、路径/名字、volume/FileId/时间/大小/内容或原签名repr。由测试正常保留原异常traceback，helper不重复格式化它。

观察器自己的比较/分类/序列化或sink失败必须降为诊断unavailable或不输出，不能覆盖原snapshot结果/错误；不捕获KeyboardInterrupt/SystemExit。不得修改原records或异常reason/args。输出sink失败时允许丢失诊断，但原结果不变。不存在actual拒绝就不生成拒绝回执；未执行的attempt/handle明确not_observed，不赋pass。

## 软件与原生验收

独立设计SPEC→不同QUALITY通过后才写计划。TDD需实际RED后GREEN，覆盖：稳定返回对象/无输出；listing membership、各字段和mixed分类；handle分类器直接向量的8bit（不授实际walker可达信用）；真实walker中volume/type/directory/delete_pending等先被原身份validator拒绝，必须同对象透传windows_directory_identity_invalid且没有目录拒绝回执；普通目录合法raw tag差异被signature归零，原行为接受/无回执，非法raw tag或带REPARSE属性的normalized tag负例保原身份拒绝；实际held_handle FileId/ChangeTime/EOF差异；listing拒绝不查询handle；最深.git frame/父不覆盖，根.git及嵌套.git/忽略entry分类；第一拒绝第二成功、两次拒绝、第二open_root失败、第二root walker返回而close_root失败的固定槽及call_outcome；非目录错误同对象透传且不增retry；两个alias实际覆盖、退出恢复、其它线程/同线程嵌套/不同线程重叠context的非阻塞owner透传；129/130 frame及bookkeeping/部分安装/observer/sink故障保原结果；无敏感字段输出；对比有/无hook的backend query/enumerate/open/read/close序列完全相等。旧probe不用于完整生产signature分类器，不新增平台skip。

原fixture调用和DEFAULT接线配对回归保留；作者自审后全局SPEC→不同QUALITY，root定点、20轮、DEFAULT、完整preflight串行，compileall-j1及治理/site/landscape/diff通过后按已授权main提交推送。再取新SHA x64/ARM实际workspace日志；未复现没有拒绝回执只表示本窗口未观察，不能称根因修好。R2/R3、Windows网络/Git、macOSquota、PE/pre-main和模型六步门都保持独立。

## 当前状态

首轮独立SPEC针对c8dd47设计发现Important2/Minor3；第二轮对d2752e发现Important1/Minor2：外围open/close错误与root walker槽、raw/normalized tag和进程全局patch owner。以上已明确整改，等待重新SPEC→不同QUALITY。尚未实施。研究来源沿[只读记录](2026-10-09-windows-directory-change-research.md)及同日landscape，独立研究确认两alias与listing gate成立；不以设计或mock关闭实际失败。
