# WP0b 前置：Windows 固定卷路径兼容性探针

> 2026-10-09实施状态：下文设计正文固定SHA `20eaff207ee73a5bbbeff8a534cab3a171d2183f824e637fda74d694f3cc565f`已由独立SPEC与不同QUALITY批准。源码现已实现，根新增负控后组合50PASS/0skip；完整独立软件审查、阶段守护及新SHA原生四格尚未完成。9ed旧四格两Py3.12生成头失败已单列修复，不能覆盖为成功。正文末尾“源码未实施”保留其历史设计窗口，不是当前结论。

后续软件验收：最终SPEC51PASS/QUALITY87PASS、20轮1740PASS、DEFAULT418PASS均无skip；全仓2261 total/59既有skip、无失败、3道通过。最终ctime兼容修复保持3.11与POSIX旧cross，只有win32且有birthtime时跨接口改用birthtime；两侧各自ctime前后仍完整。源码聚合ca04e90c，尚待main提交及新SHA四格原生验证；此设计不变为生产锁/UAC/隔离证明。

## 1. 背景、基线与范围

基线为已推送 main `9ed070010f934fb6fee69d8b8b000e63cfdc2b47`，固定 SKILL `1693651c1bd7daad3272eb054f0f81d6f254d08d`。WP0a本机软件门通过；其精确SHA签名安装矩阵另行观察，本设计不是该矩阵结果。用户已要求在原授权内自主继续R2/R3及阶段提交；本片不扩大Windows权限、部署方式或SKILL源码授权。

真实缺口：现 `windows_provenance.verify_bundled_windows_provenance()` 按路径运行包内Go并重新读取artifact/proof；现测试探针持句柄只在读取期间有效。单独加来源对象锁后仍用原盘符路径，不能锁住DOS设备映射，因此不应声称“核验后消费同一对象”。主代理已完整读取现provenance、相关适配测试、NT探针及安装消费者；结构化思考205–207记为：先核调用链、禁止认证循环、区分共享锁/ACL/启动身份。

三方案取舍：

1. **采纳：先做CI专用固定卷路径兼容性探针。**复用本次已完成gh验C及C→Go绑定的安装材料，运行已有离线Go，只确定真实路径兼容性。成本是小型Python脚本、软件负控及四签名安装格，无新编译目标/运行依赖。
2. **暂缓：生产held-HANDLE guard及消费接线。**仅在原生路径正控成立后设计；还需DOS映射漂移、逐祖先重解析、共享冲突和关闭生命周期，不能用本片代替。
3. **不适配：直接包裹旧盘符路径、前后readback充当原子锁、直接UAC setup。**前两者没有关掉命名空间窗口；后者同时引入ACL、事务、pre-main DLL和DPAPI等尚未闭合的独立硬门。

## 2. 调用链与文件职责

固定顺序：安装wheel → 既有gh验C → 既有C绑定/Go原bytes匹配 → 既有离线Go正负控 → **新固定卷兼容性探针** → 原bootstrap v1/78 → wheel导出。仅 `proof != None` 且有真实Go的分支调用新探针；unsigned、synthetic、无Go proof-only行为不变。新探针失败不得导出wheel，但不得改写为隔离DENY。

新增 `scripts/probe_windows_direct_volume.py`：CI-only入口，仅参数 `--source-sha`，由当前已安装 `icode` 与固定sysconfig架构定位C、Go、proof和native目录。无任意路径/argv/root选项。仅Windows允许；使用当前安装解释器，不新增用户工具或公共产品CLI。

新增 `tests/test_windows_direct_volume.py`：纯软件路径/Win32 ABI与错误清理/固定argv及输出合同；host fake API不获得Windows原生信用。修改 `scripts/run_windows_wheel_ci.py` 的上述唯一调用点及配对顺序/失败测试。若加入DEFAULT，只有明确portable class，不能把平台skip当必需软件覆盖。既有workflow无需新权限、job或runner，signed四格沿现调用链实际执行探针。

## 3. 路径与资源合同

内部 `direct_volume_path(path: Path) -> str` 只用于本次CI固定资源。使用 `CreateFileW` 打开存在的文件/目录以查询元数据，文件 `FILE_READ_ATTRIBUTES`，目录另带 `FILE_FLAG_BACKUP_SEMANTICS`；只读、不创建、不删除、不提权。此兼容性探针允许已有共享读/写/删，并**明确不建立生产锁或no-reparse保证**。用 `GetFinalPathNameByHandleW` 的 `VOLUME_NAME_NT | FILE_NAME_NORMALIZED` 获取原句柄路径，再关闭该句柄；关闭失败也必须使探针失败，不能继续报PASS。

查询缓冲区有固定32768 wchar上限，零/越界/缺少终止/错误类型拒绝；不循环无界增长。只接受直达 `\Device\HarddiskVolume` 加非空十进制卷号、分隔符及非空文件系统路径，不能接受其它设备/卷子路径作为卷本身、UNC、ADS、点段、空组件或歧义末尾点/空格。转换结果由程序拼 `\\?\GLOBALROOT` 加该NT路径，绝不把用户输入设备路径加入命令。这里为实际路径展示，不是Python字符串转义文本。Unicode组件不ASCII折损；固定C/Go/proofbasename必须保留。

分别转换 verifier、helper、proof、native cwd，不能只转换exe而保留其它盘符路径。本轮CI私有builder窗口假设保持；查询后句柄不再持有，因此该路径不应作为启动权/原对象锁回执。它不证明命名空间原子性、目录ACL或已加载Python模块真实性。

## 4. 实际执行与错误合同

由已安装 `icode.runner._run_unittest_with_bounded_output` 复用既有原bytes捕获、timeout和清理；不走replace decode或无界capture。固定30秒、stdout+stderr合计512 bytes；传完整GLOBALROOT exe/artifact/bundle/cwd，shell关闭、stdin禁用，仅保留现有SystemRoot/WINDIR环境。错误、超时、输出限额、捕获失败或清理未知均不返回成功。

正例调用现Go的四固定参数 `--artifact/--bundle/--source-sha/--arch`。只接受rc0、空stderr、严格UTF-8闭集JSON及全部类型/值正确：schema_version严格int1，provenance_verified true，launch_authorized false，artifact_sha256为安装C实际SHA256，source_sha精确本次40hex，architecture为实际x64/arm64。不以Python字典中bool等于int作为类型验证。输出不能有额外内容或重复成员。

同一固定卷路径再做错误source_sha负例（正常非全零SHA用40个0，否则40个1）：必须rc78、stdout空、stderr严格既有 `icode_provenance: verification_failed` 单LF。负例仅证明真实Go拒绝该identity；不证明网络/文件隔离或quota。异常对外仅固定英文失败标记，不打印路径、proof、进程输出或异常详情；成功只输出固定兼容性PASS标记及 `launch_authorized=false`，不输出“同对象启动verified”。

现 `subprocess.run`/旧产品provenance API不在本片改变；真实Go解析/信任根/协议、C、vendor、UAC、DACL、WFP和资源门全部不改。不会从Linux运行Windows二进制；host mocks不是密码学正例。

## 5. TDD、验收与信用边界

先在原9ed版复现真实软件断言RED：安装顺序缺少新探针调用；新增脚本/固定接口存在性以断言失败记录，不把ImportError或坏fixture当RED。GREEN后冻结文件，独立SPEC→不同QUALITY、20轮、DEFAULT和全仓preflight三道、编译1与治理/官网/竞品/diff通过才提交推送main。断言每种失败都阻止wheel导出，unsigned/no-Go分支零探针，原v1/78不变。

软件场景：合法Unicode固定卷路径；错设备/卷号/UNC/ADS/点段/空组件/末尾歧义；query失败/越界/close失败；文件与目录打开flags；全部四路径消费；严格receipt类型/字段/重复/非法UTF8/尾随/非零/stderr；真实负例错误类型；timeout/limit/capture错误不转换为成功；仅固定七项既有资源，不从PATH或cwd选择程序。

原生必需格：本次新SHA Windows x64/ARM64 × Python3.11/3.12，实际签名wheel安装后执行正负例，记录原job/log与OS版本。若runner是管理员，只记该上下文的兼容性，**不称标准用户通过**；现hosted Windows亦不代替Windows10 22H2/Windows11专用验收。任何格失败保留真实错误分类，不回退原盘符路径。无需新privilege或安装步骤。

本片正例全部成立时，最多称“在四个实际CI环境中，现Go可通过固定卷路径读取签名材料并返回正确回执”。后续held-HANDLE API必须另证：句柄全生命周期、卷序列号+128-bit FileId、原bytes、逐祖先no-reparse、write/delete冲突、DOS映射漂移负控、实际消费对象与held HANDLE一致、清理无遗漏。该负控尚未运行；本片不创建/修改DOS alias，不清理任何外部系统对象。

整体结论在原生结果返回前为 `unverified`；不得授首次UAC C认证、保护晋升、pre-main DLL、DPAPI、标准用户restricted payload、WFP/Job配额、Windows自动模式或R2/R3总门信用。macOS单任务quota与R3模型1→6/90%保持独立缺口。

## 6. 一手证据、许可与自检

2026-10-09独立研究固定Codex [`9b73858` no-reparse](https://github.com/openai/codex/blob/9b738582b13c2cdbeff54af0afd04c50c3e7ba09/codex-rs/windows-sandbox-rs/src/no_reparse_dir.rs#L112-L178)，根代理独立回读正文：直达卷仅用于NT打开，不是GLOBALROOT进程执行先例；复用2026-10-08的固定Apache-2.0许可证据，不伪装刷新HEAD、不复制代码。Microsoft [`QueryDosDeviceW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-querydosdevicew)只报告当时mapping；[`GLOBALROOT说明`](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)支持真实对象根但非全部API；[`GetFinalPathNameByHandleW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew)提供NT卷路径；[`CreateProcessW`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)是路径API，文档不替代本轮原生canary。仅采用机制，无第三方代码或runtime依赖。

设计自检：现有消费者与唯一新调用点明确；不新增公开启动入口、数据表、MQ或持久状态；错误阻断与兼容分支均有配对验收。技术设计技能的Java/MySQL专属规则不适用于本Python/Win32仓库，仅复用需求/架构/接口/验收结构，不引入Java分层或SQL。该文档尚须独立静态审查，源码未实施。
