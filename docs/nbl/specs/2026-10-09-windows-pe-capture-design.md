# Windows 最终 PE 检查样本采集设计

日期：2026-10-09 Asia/Shanghai。基线 main `3ef4ecd7b4854985202e39704c8efa9e2c1be22b`；设计待独立审查，未实施。

## 问题、复用与边界

当前四格真实 build-context、签名及安装均通过，但 `/MT`、架构字段与 C→Go 摘要关系不能证明 pre-main DLL 加载安全。现有 `windows_pe_architecture` 只读 DOS/PE machine，不解析导入或资源。下一步先采集当前最终 C 的真实工具报告，再独立设计完整性解析与原生加载负控，不能先用英文标题正则宣布安全。

备选：复用已选 VS/SDK 的 dumpbin/mt；扩展自写 PE 解析器；新增第三方解析包。采用第一种 CI-only 样本采集：成本最小，不增加用户依赖，不复制或分发微软工具。后两种暂缓，前者需新增完整 RVA/section/import/delay/resource 畸形边界，后者增加依赖与许可审查。用户已要求自主推进已授权阶段；此设计不增加产品权限或安装步骤，具体安全边界仍受独立审查约束。

可信构建宿主与已安装工具是本片 TCB，不对抗同权限恶意宿主。常规 lstat/原字节重读不是同对象锁、owner/DACL 验证、发布者认证或首次 UAC 证明。C 的 setup/spawn=78、产品 readiness、普通安装与旧诊断入口不变；不执行目标 PE。

## 接口与工具定位

新增 CI-only `scripts/probe_windows_pe_capture.py`，固定 CLI `--build-directory` 与 `--architecture {x64,arm64}`，禁止参数缩写。调用已验证的 `scripts.probe_windows_build_context.probe`，复用其项目/context/评估交叉校验，不另造 VS 实例 resolver；现有 workflow 的独立 context CLI 保留，因此新片额外进行一次有界 properties-only 查询。

当前实际 context 共同为 VS18/v145、SDK10.0.26100.0、VCTools14.51.36231，但不硬编码这些版本。sdk_version 必须为四段十进制，防止作为路径组件穿越。Python 进程目标架构由现有 `windows_arch_from_platform(sysconfig.get_platform())` 解析，须与请求 architecture 相同；这不是 OS 原生架构证明，实际运行结论须结合四格 OS/image/Python 及工具执行回读，不自动尝试另一架构候选。根另核固定 [CPython3.12.10 get_platform](https://github.com/python/cpython/blob/0cc81280367df838c4b199f8f0378837165071c2/Lib/sysconfig.py#L782-L789)，Windows 返回值依据 sys.version 的编译架构；`f86fdcac` 是 annotated tag 对象，源码链接使用解引用后的 commit。

每架构只允许一个明确候选：`VCToolsInstallDir/bin/Hostx64/x64/dumpbin.exe` 或 `VCToolsInstallDir/bin/Hostarm64/arm64/dumpbin.exe`；`WindowsSdkDir/bin/<sdk_version>/x64/mt.exe` 或对应 `arm64/mt.exe`。原生存在性尚未验证，缺文件即明确失败，不走 PATH/vswhere/latest/扫盘/另一架构回退。所选根由真实 probe 给出；通过绝对路径、regular file、有界原字节及现有 PE machine 检查才调用工具。MSBuildToolsPath 不是 dumpbin/mt 所在目录，不从其字符串推导版本。

唯一目标是 build root 的 `Release/icode-sandbox-windows-<architecture>.exe`。目标与两个工具各限定非空 regular file、最多8MiB，并检查 machine 匹配；在调用前读出原字节 SHA256，调用后逐件重读比较原字节摘要。拒绝目录、链接、缺失、过大、错机器及前后变化；不额外要求 hardlink count=1，也不把该检查当作防重解析/竞态锁。

## 有界采集与收据

在已核 build root 内新建本次拥有的私有临时目录，作为两工具 cwd 和 manifest 输出位置；输出文件启动前必须不存在。工具 argv 仅为 `[dumpbin, /nopdb, /imports, target]` 与 `[mt, -nologo, -inputresource:<target>;#1, -out:<本次目录/manifest.xml>]`，list 调用、无 shell，不使用 outputresource/updateresource。DUMPBIN 用官方 `/NOPDB` 禁止默认的 PDB 加载/搜索，去掉未列入其官方选项表且采集不需要的 `/NOLOGO`；这不是所有文件/网络 I/O 均已禁止的证明。复用已有 binary bounded runner，每次 timeout=30秒、stdout+stderr 原字节合计上限16384。环境仅 SystemRoot、WINDIR 和指向本次临时目录的 TEMP/TMP；缺系统根值拒绝，不继承 PATH、INCLUDE、LIB、模型配置或凭据。官方建议正确的开发工具环境，尚未保证本最小环境可运行；须四格真实执行，失败保持失败，不自动扩大环境或工具候选。

两次返回须严格为三元组、真实 int0、bytes stdout/stderr；stderr 必须为空。dumpbin stdout 必须非空，mt stdout 可以为空；mt 成功后输出文件须为非空 regular file、最多4096字节，用 limit+1 读取并检查 stat 长度。仅捕获原字节，不假设其语言、UTF8、XML BOM 或文本语法；本片不解析 manifest，不声称覆盖其它 resource ID/language。异常、超时、输出超限、空报告、缺/旧输出及前后 bytes 变化都不得产生成功收据。临时目录仅清理本次拥有对象；清理失败也是失败，不继续签名。

成功只有固定 `windows-pe-capture status=CAPTURED production_authority=none` 与单行 ASCII canonical JSON（最大32768字节）。闭集 schema_version=1，含 architecture、完整九字段 build_context、helper_sha256、dumpbin/mt 各 path+sha256、dumpbin_stdout_base64、manifest_base64，以及 `parse_complete=false`、`runtime_load_verified=false`、`source_launch_verified=false`。成功报告里的两段 base64 可逆且会公开于 CI：仅来自本仓公开源码生成的固定 C 的导入表及 manifest，不是脱敏、加密或任意程序输出；不包含环境、错误诊断、模型数据或 KEY。错误只公开固定类别和非零退出，不转储 stdout/stderr、路径之外异常或凭据。长度验证在打印成功标记前完成；KeyboardInterrupt/SystemExit 不吞掉。不得截断后宣称完整采集。

该收据只证明可信 CI 窗口中工具返回及样本与目标摘要关联，不证明工具输出解析完整、DLL允许清单、全部资源不存在、传递/动态依赖来源或首次启动认证。

## 接线与测试

只有 sign job 在现 context CLI 成功后、attest 前调用采集器，返回非零立即 exit；原 matrix、权限/action SHA、Go/C 构建、签名/安装检查及 upload 顺序不改。普通包与用户 CLI 不调用此脚本，不改变 MANIFEST 或运行依赖。

新增 `tests/test_windows_pe_capture.py` 的 portable class，加到 DEFAULT 恰好一次；Host-only 测试不加入 DEFAULT。每项软件正控明确使用合成 PE 和 mocked Windows filesystem/runner，不需 symlink 管理员权限，也不算原生工具运行。定点覆盖：两架构准确候选/argv/环境/cwd、九字段 context 复用、machine/平台/sdk 拒绝、非regular/0/超限、变化 bytes、严格 runner 返回类型与bool拒绝、stderr/非零/空/超限、mt缺/旧/链接/超限输出、每阶段异常与 owned cleanup、base64无损与JSON闭集/总长度、固定错误/零后续执行、旧context及workflow/default选择兼容。多语言/坏PE/ordinary+delay已知清单与多resource的真实行为属于下一解析门，不能由 mock 给信用。

完成真实 RED→GREEN 后，全局独立 SPEC→不同 QUALITY、20轮零新增 skip、DEFAULT、完整 preflight、compileall-j1/治理/站点/对照/diff、固定 vendor 完整性通过，才 main commit/push。然后独立回读新 SHA 四格：实际 OS/image/Python/context、两个候选存在/原生工具执行、目标前后摘要、完整有界样本、采集在attest前、后续19安装PASS。任何缺候选/编码或工具行为失败保留，不预填PASS或降低门槛。

下一片根据真实报告设计解析，须 ordinary/delay 正控、缺资源及 #2/#3/multi-language 反例、完整输出/畸形和真实 pre-main DLL负控；不将本片 CAPTURED 当 production安全结论。Win10、标准用户、protected-root、UAC/DPAPI、配额、工作台验证提供者、真实模型1→6/90%仍独立未验。

## 证据与许可

独立只读研究及根复核：[Microsoft IMPORTS](https://learn.microsoft.com/en-us/cpp/build/reference/imports-dumpbin?view=msvc-170) 明确普通及 delay 导入，[mt](https://learn.microsoft.com/en-us/windows/win32/sbscs/mt-exe) 提供显式 inputresource/out，[resource ID](https://learn.microsoft.com/en-us/windows/win32/sbscs/using-side-by-side-assemblies-as-a-resource) 区分ID语义，[PE格式](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format) 说明自写完整解析的边界，[DLL搜索](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order) 说明静态清单不是加载来源证明。微软文档未保证文本编码/本地化格式或缺资源错误输出。前片固定 Codex9b738（Apache2）机制只复用分层约束，未复制源码或刷新HEAD；本片实现自写 CI胶水，新增用户依赖/权限/第三方源码数量均为零。

2026-10-09 修订证据：根及独立只读研究核对 [Microsoft NOPDB](https://learn.microsoft.com/en-us/cpp/build/reference/nopdb?view=msvc-170)、[DUMPBIN options](https://learn.microsoft.com/en-us/cpp/build/reference/dumpbin-options?view=msvc-170) 与 [DUMPBIN reference](https://learn.microsoft.com/en-us/cpp/build/reference/dumpbin-reference?view=msvc-170)。采纳 `/NOPDB`，避免默认查找大型或远端 PDB；去掉不需要的 DUMPBIN `/NOLOGO`，不据选项表缺项断言所有版本都不支持它。成本为一个 argv 替换及精确行为测试，无新增依赖、源码复制、许可分发或权限。暂缓扩大环境：现有绝对路径与最小环境须通过原生四格，不能将编译环境说明伪装成可运行证明；不适配“超时/输出上限等于零额外 I/O”的安全说法。验收项为精确 `/nopdb /imports` argv、无 DUMPBIN `/nologo`、失败停签与四格真实工具返回，仍不授予解析或生产安全信用。

自审：采集与解析/生产明确分离，公开base64的含义明确；输入、限额、TCB、缺工具失败及旧兼容有闭合合同。修订独立审查前暂停本任务实现。
