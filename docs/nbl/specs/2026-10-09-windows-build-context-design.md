# Windows 构建工具选择诊断设计

## 范围与现状

基线main `58c93518117c117f0e37c8af33ef2a049ddfdbe6`；同日路径夹具一行修正独立验收中，不修改本设计的生产者。沿已批准WP0b启动前加载验收顺序，先获取实际构建工具链证据，再决定如何检查成品imports/manifest；本片不是加载防护、受保护安装或执行权限实现。用户已要求main自主持续推进，无额外审批等待；新增特权部署仍必须另获授权。

真实缺口：本仓signed四格已构建C，但没有记录本次MSVC/SDK工具目录。已有 `/MT` 不证明入口前无DLL。本仓 `native/windows/CMakeLists.txt` 的 `project(... C)` 已完成选工具；signed工作流只传 `-A`，不能从PATH、镜像清单或另一次vswhere latest推导本次选择。

三种方案：新PE完整解析器成本大且不能解决工具来源；解析instance再拼vswhere目录重复CMake选择且有多义；**采用现CMake选择结果与生成项目MSBuild评估**，依赖最小，先通过双架构实际输出再继续成品检查。

## 两个边界清晰的组件

1. CMake opt-in诊断：新增 `ICODE_WINDOWS_BUILD_CONTEXT_DIAGNOSTIC`，默认OFF。只有ON且bootstrap开启、MSVC及Visual Studio generator时才生成build目录内的 `icode-windows-build-context.json`。不修改默认目标、二进制常量、原metadata/拒绝接口或用户安装要求。
2. CI-only Python检查器：新 `scripts/probe_windows_build_context.py`，唯一输入 `--build-directory` 绝对目录及 `--architecture x64|arm64`。从该目录固定context和 `icode_windows_bootstrap.vcxproj` 取证，只执行context明确选择的MSBuild，不执行bootstrap、dumpbin/mt、不签名、不启动payload、不调用shell。

context为UTF-8封闭对象，固定字段：`schema_version`严格int1、`generator`、`platform`、`toolset`、`sdk_version`、`msbuild`。后三者分别来自 `CMAKE_VS_PLATFORM_TOOLSET`、`CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION`、`CMAKE_VS_MSBUILD_COMMAND`；generator/platform来自原CMake选择。字符串不允许空、NUL/控制字符，序列化转义引号和反斜线；不会无条件把cache值视为绝对路径。

检查器要求context最多4096原bytes、固定字段无重复、合法UTF-8/JSON，固定项目最多1MiB且是普通非链接文件；context同样普通非链接。build目录为本次可信CI私有生成根，不是敌对用户目录，前后读取不被称为原子锁或no-reparse祖先保证。msbuild必须是绝对现存普通文件，basename为MSBuild.exe，拒绝裸命令或PATH回退；工作流传来的架构与context的x64/ARM64精确映射，generator必须是Visual Studio名称，toolset/sdk必须非空。

## 评估与可观察结果

用上述明确MSBuild，以固定项目/cwd运行下列固定参数，不附加targets、restore、任意用户选项或build请求：

`-nologo -noAutoResponse -nodeReuse:false -maxCpuCount:1 -property:Configuration=Release -property:Platform=x64|ARM64 -getProperty:Configuration,Platform,PlatformToolset,WindowsTargetPlatformVersion,VCToolsInstallDir,WindowsSdkDir,MSBuildToolsPath`

复用 `icode.runner._run_unittest_with_bounded_output`；timeout30秒、stdout/stderr合计16384原bytes、继承本次CI的构建环境，不误用仅SystemRoot/WINDIR的产品环境。成功必须严格int0、stderr为空、stdout严格UTF-8且无重复成员；MSBuild封闭根为 `Properties` 对象，上述七属性均为非空字符串。Configuration/Platform精确匹配，toolset/sdk匹配context；其余三目录必须绝对、现存目录。生成vcxproj中的唯一WindowsTargetPlatformVersion及Release/本架构的唯一PlatformToolset必须与两边相符；XML禁DOCTYPE/ENTITY，缺失、重复或选择多义失败。不能把其它配置的toolset冒充当前配置。

成功只输出 `windows-build-context status=PASS production_authority=none`，再输出一条固定前缀的canonical JSON（schema1、architecture、generator、toolset、sdk_version、msbuild、上述三目录），作为公开CI工具路径证据；路径只来自固定CI build工具属性，禁止任意异常正文或环境转储。明确来源是可信builder，不是由未认证输出创建运行时信任。预期输入/文件/XML/JSON/超时/进程失败输出固定 `::error::windows_build_context_probe_failed` 并返回1，编程错误与中断不吞；成功返回0。

## 唯一接点与兼容

仅 `.github/workflows/windows-helper-provenance.yml` 的四格signed构建启用开关，在final bootstrap构建成功后、attestation前运行检查器；失败不进入attest、安装或导出，不复用旧context宣告成功。旧unsigned、probe-only、synthetic packaging、产品locator与provenance、vendor、权限均不改。CMake新生成context不改变最终C编译；不新增runner action、OIDC写权、用户Go/MSVC/Node依赖。检查器复用现源码路径加载约定，不作为随包用户入口。

## 验收与证据边界

- TDD先复现旧源码缺诊断接口的assertion FAIL而非ImportError；覆盖JSON重复/extra/bool、编码/大小、裸msbuild、架构不符、工具集/SDK不符、路径不存在、项目多义/DOCTYPE、属性缺失/错误退出/输出超限/超时及零后续签名接点。
- host CMake夹具实际生成context并验证默认OFF与开启条件；只是CMake序列化/选择逻辑信用，不冒充真实MSVC。
- 检查实际argv/order/timeout/bytes上限及固定错误隐私；保留原接口及权限合同。独立SPEC→不同QUALITY、20轮、DEFAULT选择对应portable class、完整preflight和仓库治理检查后才提交。
- 新SHA四格Windows原生日志必须记录OS/image、实际Python、选择结果和固定成功标记。只有四格实际通过才称此CI诊断verified；其后可设计有限候选dumpbin/mt定位。本片不要求或授予Win10、标准用户、UAC、DLL负控、DPAPI、配额或R2/R3总验信用。

## 一手研究与采用决定

2026-10-09独立只读研究及根回读固定CMake4.4.3 `af7ecc8c294d153b0120813776e1fa11c5bfe4a1`：[对应VS命令官方合同](https://cmake.org/cmake/help/latest/variable/CMAKE_VS_MSBUILD_COMMAND.html)、[当前定义域设置](https://github.com/Kitware/CMake/blob/af7ecc8c294d153b0120813776e1fa11c5bfe4a1/Source/cmGlobalVisualStudio10Generator.cxx#L843-L849)、[选择及裸命令回退](https://github.com/Kitware/CMake/blob/af7ecc8c294d153b0120813776e1fa11c5bfe4a1/Source/cmGlobalVisualStudioVersionedGenerator.cxx#L999-L1049)。Microsoft [getProperty官方语义](https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-command-line-reference?view=visualstudio)保证不带targets/getTargetResult时评估而不build，不保证评估毫无副作用。**采纳**实际选择、绝对路径拒绝回退、独立生成项目交叉校验；**暂缓**具体dumpbin/mt路径及加载防护，属性缺失先原生诊断失败；**不适配**PATH/latest/镜像清单代替选择，/MT代替安全。无上游源码复制或新增运行依赖。相关Codex机制沿持续对照中的历史固定证据，不伪称刷新HEAD。

## 当前状态

设计待独立静态审查；未实现、未生成context、未运行Windows诊断。`verdict=unverified`，缺口owner为实现者与独立原生观察者，下一步仅静态审查和完整实施计划，不授予任何新执行权限。
