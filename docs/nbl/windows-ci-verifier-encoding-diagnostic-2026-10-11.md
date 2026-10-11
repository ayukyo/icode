# Windows CI 独立校验器输出诊断

2026-10-11，以下保留只读诊断初始窗口（当时尚未修复）；软件修复观察见末。独立研究与root另核源码/原始日志，不把Ubuntu复现作Windows新运行。

| 基线 | 已确认与边界 |
| --- | --- |
| identity | job114460308565，Windows x64/CPython3.12.10；hosted runner无物理设备身份信用 |
| time_window | 11:40:30–11:40:40 UTC两次readerthread异常 |
| repo_matrix | runtime/analysis均main `0d40c2577316bfa52e9c595dfcd4e388ecd8c28c`，固定vendor21566a5；verification尚无修复SHA |
| artifact_identity | 当前pack_verify.py原样生成verify.py；异常包摘要未记录，不能授特定包重新验证 |
| evidence_sources | 完整job日志、实际775项选择顺序、两个完整夹具调用、CPython固定源码；root另核decisive原文 |
| unresolved | 子进程实际stream.encoding未直接打印；Windows修复后四格日志补新证据，root负责 |
| conclusion_ceiling | 两个夹具输出编码不一致路径得到支持；没有修复或新Windows实测，不能称所有输出链完整 |

两次异常按完整选择顺序与成功点计数位于第612项 `TestContractEngineering.test_native_legacy_code_actual_cp_to_independent_pack`（tests/test_contract_engineering.py:1256）和第630项 `BindingPackTests.test_real_bound_partial_pack_is_portable_after_code_disappears`（tests/test_execution_binding_pack.py:41）。必需startup native8位于563–570，先前成功，且method/fixture/subTest skip均阻断；当前运输门不被这两个后置输出夹具异常直接污染，但不授总体R2/R3信用。

两夹具均用 `python -I -B verify.py`，子进程不带 `-X utf8`；-I忽略PYTHONUTF8/PYTHONIOENCODING。parent严格UTF8读管道，而Windows非控制台默认stream可为系统ANSI。真实 `_print_diagnostic`保留流编码，只对不能编码的中文backslashreplace；可编码的中点在cp1252写成0xb7。独立诊断用自有cp1252/CRLF/同路径形状复现异常字节offset214/210与日志精确相符；这支持机制解释，不把未直接读取的实际encoding写成日志事实。

root另用实际 `_print_diagnostic`和自有cp1252流确认严格UTF8拒绝byte0xb7，子进程实际-I flags为ignore_environment1/utf8_mode0，增加-X utf8后为1/1。Ubuntu不执行Windows `_communicate`；[CPython v3.12.10:1598–1651](https://github.com/python/cpython/blob/v3.12.10/Lib/subprocess.py#L1598-L1651) 原文显示readerthread内 `fh.read()`异常未向调用线程重抛，空capture list成为None，两fixture只断言exit0因此未检出正文丢失。control.py/builtin.py已有errors=replace，不是这两个异常源，不改其政策。

| 声明 | 类别 | 来源与边界 |
| --- | --- | --- |
| 两次UnicodeDecodeError且主套件775/20skip成功 | fact | 同SHA完整job日志，不等于异常全部消失 |
| 两个独立verify调用是对应失败位置 | supported inference | 775选择顺序/点计数、调用形态、两个byteoffset精确吻合 |
| 当前Windows子流实际cp1252 | inference | 机制精确匹配，但未直接打印encoding |
| 新startup native8通过 | fact with scope | 此job对应选择及成功点/必需skip拒绝，不代表WP0b/R2/R3 |
| 修复已通过Windows | unobserved | 尚无修复SHA/新日志，不授信用 |

独立小修建议：两调用显式-X utf8，第一处parent也显式encoding=utf-8，保持strict，不用errors=replace吞掉输出；断言stdout非空并含成功/工单/已核验完整语义。受控stdout=None必须失败；在两个既有test实际运行，再核新SHA四Windows日志无该readerthread异常。身份片冻结后由独立单写者执行，必要纳入该轮候选完整审查，绝不在身份模块中修测试夹具或顺带修改产品输出政策。

后续软件修复已冻结但未发布：单写者仅两tests11+/3-实现上述调用与正文断言，旧loststdout负控误放行2→新2assertionFAIL/0ERROR，恢复2PASS及deepcheck1PASS；root又独立跑负控确认2FAIL/0ERROR。产品诊断/校验器均无修改，原生新SHA无readerthread异常待四Windows日志，不把宿主测试当Windows闭合。完整候选审查/preflight/发布随[身份片](./plans/2026-10-11-windows-host-identity.md)独立记账，本文上表“verification尚无修复SHA”仍为实际事实。
