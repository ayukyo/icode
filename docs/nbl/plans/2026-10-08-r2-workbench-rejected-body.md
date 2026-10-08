# R2 工作台早拒请求的有界丢弃

## 基线与结论上限

真实缺口：Workbench 在鉴权、路由或媒体类型拒绝 POST 时，尚未消费请求 body 就关闭默认 HTTP/1.0 连接。已有 `_drain_rejected_body` 用于 413，复用其 0.25 秒总期限、8KiB 分块和 timeout 恢复；不新增服务入口、客户端重试或吞掉网络错误。

| 证据 | 精确身份及边界 |
| --- | --- |
| 故障运行 | root `edbfbe83a97e1fc2a72beb6b024aa57632696708` / vendor b74，Windows x64，Python 3.11.9，job 113223664203 |
| 实际日志 | workspace 开始 08:38:20.011 UTC；错误汇总于 08:41:26.57 UTC 打印，不能推断单条发生时间；cross-origin POST 在 urllib→http.client→socket.recv_into 收到 WinError10053，无已解析的状态/header/body |
| 原运行源码 | workbench Git blob `6e544a69697cbfcb959d7748b551fec3ebbb9cfc`；与后续757相同 |
| 分析及本机修复 | 当前 root757/vendor169；冻结workbench SHA256 `8badbeb2a32de5ab54bc04f754d1772b77667c359d654a5a2f093e48e5699d49`；Ubuntu Python3.11.15，不是故障运行树 |
| 后续原代码运行 | 757 x64 job113226997633：226项/283.038秒、9skip、OK；未复现10053，不能证明候选根因成立或消失 |

没有服务端发送跟踪/抓包/原生Windows复现。已确认的是源码的未读body路径及新增本机实际HTTP验证；“本次10053由此引起”仍是候选。Microsoft将10053定义为本机软件abort，不与10054 peer reset混称。

## 范围及验收

- `_error` 只处理 POST、尚未读取、单一合法正 Content-Length、没有 Transfer-Encoding、长度不超过128KiB 的 body；GET、缺失/非法/重复CL、TE和超上限不读。
- `_read_json` 在开始读取或原413 drain之前标记；错误响应不会对已读、部分失败、中断或二次错误重复消费。body不解析/解码、不进入业务，原鉴权、403/404/415/413与服务副作用判据不变。
- 复用原 drain 的总期限和timeout恢复；普通OSError保持原响应，中断保持原对象。不是保证任意不完整/超大恶意请求都能可靠收到响应，也不是OS隔离或自动模式验收。

TDD原6方法中2方法产生6个断言FAIL、0ERROR：五种早拒没有消费38字节；慢body未调用有界read1。四个原兼容正控已GREEN，不把它们声称RED。最终扩到10方法，10/10、0skip、1.017秒；冻结后20轮200PASS、0skip、20.375秒。旧工作台33项PASS、0skip、4.358秒。CI接线覆盖先1RED，后8GREEN、0skip、0.056秒；新增10进入已有DEFAULT，CROSS50与权限不变。

独立SPEC：新10＋旧33＋CI8，51/51、0skip、5.340秒；四文件SHA、AST、diff一致。不同作者QUALITY：同51/51、0skip、5.273秒，另五实际控制覆盖精确128KiB非法UTF8全丢、128KiB+1不读、16×8192读取上界、空TE不读、drain OSError后403与原timeout恢复。两者完整核对所有 `_error` 调用方，无阻断发现。全仓preflight与新SHA远端矩阵在整体冻结后另验，未冒称已通过。

## 调研取舍（2026-10-08）

独立只读核对 CPython [v3.11.15 http/server.py](https://github.com/python/cpython/blob/v3.11.15/Lib/http/server.py) 与 [v3.12.10 socketserver.py](https://github.com/python/cpython/blob/v3.12.10/Lib/socketserver.py)：默认HTTP/1.0，handler/finish/SHUT_WR没有自动丢弃应用尚未读的完整body。PSF许可；复用机制，不复制代码。

[RFC9112 §9.6](https://datatracker.ietf.org/doc/html/rfc9112#section-9.6)说明提前关闭且后续入站数据可能导致客户端丢掉最后HTTP响应；[Microsoft Winsock错误](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2)及[优雅关闭说明](https://learn.microsoft.com/en-us/windows/win32/winsock/graceful-shutdown-linger-options-and-socket-closure-2)支持审查此边界，不证明该次10053具体成因。采纳已有有界drain与严格framing guard；不适配无限读完、全局读取不明确framing、client重试或降低断言。收益是完整小POST早拒的连接处理，成本是最多既有0.25秒等待；无新依赖/许可证变化。

【架构级自检报告】

- ✅ 语法/编译：四文件AST与本片解析通过，整体compile另验。
- ✅ 依赖/调用链：所有错误入口与既有drain/响应链完整。
- ✅ 逻辑/边界：framing、额度、防重复与实际HTTP通过。
- ✅ 异常处理：本片OSError/timeout及同一KI/SystemExit负控通过。
- ✅ 关联模块：原33项及CI8项，两次独立51项通过。
- ✅ 兼容安全：鉴权、业务、状态码、CROSS和CI权限不变。
- ✅ 可运行性：本机本片通过；Windows修复与整体R2/R3未据此宣称完成。

**Execution Mode:** serial implementation, independent read-only research/reviews

### 最终ASCII framing补充（2026-10-08）

上面的10/200/51结果为同日先前版本。后续自检发现int()会接受`+38`、`3_8`、全角/阿拉伯数字及非HTTP外围空白，虽有既定读取上限且无业务调用，不符合“合法单一长度”的说明。新增一方法含六负控/四正控先复现6FAIL、0ERROR；只在早拒drain路径使用SP/HTAB trim与ASCII 0–9，保持正常_read_json原兼容路径。038及外围SP/HTAB是合法正控；0是合法长度但没有需丢弃body，不能与畸形长度混称。

最终workbench SHA256 `690ba045dd30b4c06bbf619ecb29386c6c5e0edfaf45f345d7a3664e47ca9848`，新测试 `fe2a85f9c84b30437938eab8f4d00a7ff64dacccd42935a08a251a811d845b3f`；CI接线两文件仍 `4d57d0cac1a0e52167d62d6629fc28d4ebb76d71016b70a489d068662518fe01` / `295bac65f6e01c2700546fa62dbee32cc7468db182a6af5ee16c87972239d77f`。11方法20轮220 PASS、0SKIP、20.484秒，关联52 PASS、0SKIP、5.277秒。独立SPEC52 PASS、0SKIP、5.181秒，四SHA保持；另RAM恢复旧guard独立复得6FAIL、0ERROR，不写源码。

一手依据[RFC9110 §8.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6)的1*DIGIT、[§5.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.5)的外围空白及CTL边界、[§5.6.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6.3)的OWS=SP/HTAB。Unicode负控在RAM header fixture执行，不冒充实际网络可发送该字符。不同作者QUALITY及重新冻结全仓门禁另记，先前2066发现项/preflight通过不替代本次最终树。

不同作者最终QUALITY52 PASS、0SKIP、5.251秒，四SHA一致/AST4/diff通过；另RAM26控制覆盖13种非法长度/4500位转换保护不IO、五合法decimal/leadingzero/OWS精确读38并恢复原4.75秒timeout、三合法零长度无discard、128KiB及+1、三旧正常_read_json兼容。CROSS50与HEAD相同。完整DEFAULT238 PASS、0SKIP、97.310秒；compileall-j6、governance/site/严格竞品与diff通过。最终完整preflight发现2067项，运行结果待另记，不称2067全部无skip。

最终完整preflight于2026-10-08 09:52 UTC三道全部PASS，冻结源码未变。上句“待另记”为运行中历史；没有新增Windows实测，不改变10053候选或R2/R3结论。
