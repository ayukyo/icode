# WP0b：持有来源对象的内部权限消费者

日期：2026-10-11。基线 main `37f100a0566e9225630e409b8077a1c06789b649`，vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`。这是已批准[可信启动路线](./2026-10-11-windows-trusted-startup-design.md)第二片的权限接线，不是 UAC、publisher 或 Windows 兼容通过声明。用户委托推荐技术选择，不设重复批准停点；部署、权限与安全硬门不变。

## 问题、现有实现与调用链

已存在 pin owner、原 HANDLE security reader、原宿主 primary token 身份与纯 source/protected policy，生产代码尚没有将四者组合成持有窗口的内部消费者。CI 观察在退出前关闭对象，输出 JSON；该回执不能交给生产消费者取得权限，也不能用先行路径 provenance 认证后来 held bytes。

新 SHA 四格安装结果在[整链观察记录](../plans/2026-10-11-windows-installed-chain-observation.md)逐格保存。四格均为每资源13节点/全部关闭，两个卷根 owner_untrusted、其余节点 pass。根目录还有非可信 ADD_SUBDIRECTORY 与 inherit-only 修改项，不能因为首先报 owner 拒绝就认为只补一个可信 owner 即可解决。本片仍执行原政策；不猜 TrustedInstaller、不跳过卷根、不改根 ACL。

选择窄内部 owner，而非把诊断 JSON 升为权限票据（没有 live 对象），也不现在重定义卷根政策（缺少操作/加载/全窗口证明）。收益是把已核政策绑定实际持有链，成本是生命周期与负控；默认安装根被拒绝的兼容缺口保留，而不是把拒绝包装为成功。

## 接口与对象归属

新增 `src/icode/windows_startup_source.py` 和配套测试。无参数入口 `pin_installed_startup_sources()` 只定位当前包的 helper/verifier 两个固定架构镜像，不接受任意 path、SID、role、期望 digest、HANDLE 或诊断 JSON。包位置从本模块 `__file__` 词法取得，要求固定 `icode/windows_startup_source.py` 形状及本地绝对安全组件；不 resolve、不走 PATH/CWD/env 或源码原生构建目录回退。不同于 CI-only purelib 校验，不把 venv purelib 强加给正常 pip 用户安装。资源名与架构复用既有固定映射；资源缺失或源码缺镜像保持失败。

入口仅 Windows；一次捕获真实 primary token SID并确认 token 关闭，调用原 SID 验证后才打开镜像。每个资源各创建新的 backend/pin owner，两组全祖先与镜像 HANDLE 同时持有，完成所有节点的 source 政策之后才返回 `PinnedStartupSources`。角色固定 source；protected 在另一入口将来实现，不允许调用者切换。

返回对象仅供可信宿主单 actor 使用。`content(resource)`、`sha256(resource)` 仅在 ready 且未 closed 时返回既有 owned bytes/摘要；resource 必须 exact str helper/verifier。不公开 HANDLE/SID/path/security raw，不提供启动路径、授权标志或序列化回执。禁止 copy/deepcopy/pickle；对象名称不代表安全能力，Python 私有成员也不是对不可信 Python 调用者的隔离边界。

## 政策、重验与预算

构造和 `revalidate()` 对两个资源逐节点使用同 HANDLE：metadata前 → SD前 → SD后 → metadata后，metadata必须等于原baseline，SD为exact bytes且两次相等；两份各按既有 parser 解析，再执行原 `check_startup_security(role='source', host_sid=实际身份, directory=实际对象)`。任何 owner/mutation/empty/未知拒绝、reader/native/parser故障均抛错，不分类降级。初次保存每节点 owned SD；重验还要求与初次 bytes 一致，即使变后的政策仍通过也拒绝。前后各进行全链 metadata 重验：由 composite 直接使用各子backend.query、既有 `_metadata` 和baseline，不能调用会在失败时提前自闭的子owner.revalidate；统一交 composite 全局逆资源收尾，既有单文件owner行为不改。

每资源含卷根最多32节点，打开前词法核预算；现有每镜像64MiB。每次构造/重验的两个资源所有节点两份成功SD的 `len(entries)` 总和最多512；reader/policy内部重复执行parser不额外计次数，不截断或跳过。每次重新计数，不把反复调用次数当累计终身预算；任何超量清理并失败。重验成功只证明调用点的快照一致，不证明两点之间 SD 不变、RX/AccessCheck、publisher、DLL 搜索或 ShellExecuteEx 实际镜像一致。

新对象提供 `closed`、`close_confirmed`、`close_errors`，正常 `close()` / context exit 逆资源、逆链各关闭一次，确认所有子 owner；重复 close 不重试。构造/重验/主体任何 BaseException 都清理已取得的所有资源，保留原异常（含 KI/SE），复合清理只加固定 note，不泄漏原异常值。正常关闭收集全部错误，优先保留非 Exception 中断，否则以既有 `StartupPinCloseError` 报告；所有 ambiguous close 永不重试，closed不代表confirmed。关闭后 content/sha/revalidate 拒绝；不以 `__del__` / GC 或异常吞掉冒充交付。

## 调用边界和验收

本片是可信启动内部基础设施，暂不接现有路径式 provenance 或 native setup/spawn，避免把不完整 owner 当 launch grant。后一片来源/PE/加载消费者必须显式在此 context 中消费原 bytes；现有 setup/spawn退出78与自动模式关闭不变。这里只完成权限绑定门，不宣称已消除当前卷根兼容问题。

便携真实 TDD 覆盖：定位用户安装/源码缺镜像、非法路径/架构/身份0open、两资源各全部失败点、政策 source/protected差异继承旧回归、同HANDLE调用顺序、32/33节点、512/514ACE、两次及跨调用漂移、allowed-change拒绝、query/parser/metadata错误、第二资源失败回收第一、normalclose复合错误/KI/SE/hostile异常note、逆序一次、数值回收独立backend、copy/pickle、关闭及参数精确类型。不得用 unknown policy 作为正常拒绝回执。

后续 CI 选择必须把新便携模块一次加入 DEFAULT 与 startup 必需选择，method/class/fixture/subTest skip 均拒绝；旧可选/平台 native skip 含义不变。实际 loader 计数取得后同步，不猜数。本片软件验收仅授便携消费者与既有运输回归；新SHA安装观察仍独立，不能当新consumer已在Windows执行。接下来的原生消费者验收须区分固定installed入口root拒绝/回收与测试私有组装缝的临时叶故障；不得向生产开放path/SID注入，叶负控必须核实际拒绝节点匹配目标，若先被卷根拒绝只给root信用，叶格未过。不得改系统卷根ACL或把mock正控当普通host兼容；Win10、普通host、完整窗口与首UAC另验。

独立SPEC后不同QUALITY、关联/20轮、完整preflight、文档/站点和七维自检后按授权提交推送main，编译-j1。真实Windows日志、default根拒绝、publisher/加载/UAC和R2/R3各单独记账。

## 并行研究与取舍

独立只读研究实际13:32–13:35及追加13:37–13:41 UTC，固定 Codex `8c0f7011674145da7e10627769fb221c74fbf7a0` / SRT `5507fb0e639c00f845554336ece62e27af5b1bb7`、Apache-2.0；没有完整二十项/HEAD刷新或原生实验。**采纳：**同owner权限检查、caller锁窗口、权限/稳定性/publisher/启动分门。**暂缓：**guard写对象、卷根角色特化、publisher/加载/UAC/protected晋升。**不适配：**service/MSIX权限来源、warn-and-continue、host DACL重写、default ACL/TrustedInstaller假设。

Codex [home.rs:80–169](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-service/src/ipc/home.rs#L80-L169)位于service调用链，原文保留leaf/path race边界，不能当纯pip首UAC证明。SRT [exec锁](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/cli.rs#L1428-L1521)不等于其独立[runas](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/cli.rs#L1638-L1748)路径的整链认证。root另核[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)/[GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo)：sharing不冻结WRITE_DAC，二次快照不处理并发变更。没有复制上游代码、依赖或权限新增；若以后复制vendor需另核子目录许可。

自审：内部固定来源、实际身份、两live owners、全部原policy、有限预算与失败回收对应；兼容与启动均不由本片授权。独立SPEC首轮I2/M1已明确composite无自闭metadata检查、root与目标叶原生信用拆分、两份SD的ACE计数；复核C0/I0/M0后不同QUALITY亦C0/I0/M0。未放宽旧政策或追加部署，没有模糊占位接口。
