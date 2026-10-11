# Windows 已安装来源整链权限：只读观察设计

2026-10-11。基线main `90704b41439c025d7f5ff9f8689db3b7b208cc91` 已推送且远端一致。本设计复用用户批准的固定路径/持有全祖先方案；例行技术选择自主执行。采用设计技能梳理真实问题与替代方案，不要求用户重复批准既定边界。新身份四Windows格是实现前置门，目前仍待；本文不是原生通过或生产准入。

## 问题、现有能力与选择

真实缺口是没有实际安装来源祖先ACL的分类证据。现有 `PinnedStartupFile`、`WindowsStartupPinBackend.query_security`、`parse_startup_security/check_startup_security` 和 `WindowsStartupHostIdentity.capture` 已覆盖所有权、运输、纯策略和原宿主身份，不能重复重写；当前没有生产整链消费者。系统根目录是否被保守策略拒绝尚未观察，不可先猜测或放宽。

推荐先做测试专用只读分类，接入既有 `scripts/run_windows_wheel_ci.py` 的独立安装venv及实际来源验证之后，再据真实数据设计消费者。直接先接消费者会把未知兼容问题混入生产合同；更改系统ACL或构造另一个安装位置掩盖拒绝，超出范围。workspace的PYTHONPATH=src只证明checkout，不是安装正控，不能回退到模块py文件替代helper。

## 范围与数据流

新 `scripts/probe_windows_installed_chain.py` 只观察当前解释器安装包内两项固定资源：`native/icode-sandbox-windows-{arch}.exe` 与 `native/icode-provenance-windows-{arch}.exe`，arch复用 `windows_arch_from_platform(sysconfig.get_platform())`。不接收外部path/role/SID/HANDLE，不执行这两镜像，不验证新publisher授权，不安装、提权、变ACL或创建protected目录。

入口只接可信CI的 `--source-sha`（精确40位小写hex），记录其来源是job候选标识，不独立证明它与安装包相同；同一调用链在此前已完成签名来源和安装包绑定，脚本输出的owned镜像SHA256只绑定本次实际观察bytes。不能把参数当publisher证明。

包位置用当前installed `icode.__file__` 与sysconfig purelib的词法绝对路径核包含，不调用resolve消去待检查的reparse祖先；路径不得经环境、CWD或PATH回退。脚本用 `-I -B -X utf8` 启动，无PYTHONPATH。只限Windows/x64或ARM64及Python3.11/3.12；不在Linux模拟原生。实际资源缺失、无法打开、预算超限均失败，不记unobserved冒充安装正控。protected目标尚未安装，本片固定 `protected_observed=false`，不探测用户目录或猜默认目标。

流程：一次真实primary TOKEN_QUERY捕获host SID并确认token关闭；每资源各建一个新的backend/owner，沿绝对本地卷root与全部祖先/最终镜像pin原对象。不能共用关闭后backend绕过其retired HANDLE规则。owner生命周期内固定单actor，按实际baseline.directory逐同HANDLE查询metadata和owned security bytes，复制后先parse，再按固定source角色判owner/mutation；重复同HANDLE读取security与metadata核观察一致性。正常最后逆序一次关闭全链并确认close_confirmed；任何主体失败/中断仍尝试全链一次关闭，保留主体异常。仅全部资源完成且所有close确认后输出一次JSON，不能在finally回收前报告成功。

诊断必须完整逐对象记录成功读取后的策略拒绝，不在第一个可分类拒绝时假装整链通过：owner不可信、非可信mutation、empty_dacl三个有限拒绝类别。仅捕获 `check_startup_security` 这一已成功读取/解析owned bytes后的独立调用中已知固定政策拒绝，未知异常或其它文案仍FAIL。现reader.read会在返回前parse，parse拒绝、native故障与LocalFree故障共享异常类，复合失败还能保留parser主体；因此任何query_security抛错一律观察失败，不按类型/文案/cleanup状态降成完整拒绝，不要求或臆造其未返回raw bytes的前后比较。额外parse失败、metadata漂移、descriptor前后不一致、回收未确认同样失败。读取和nativefixture失败在Windows上不得skip。

## 有界脱敏回执

schema_version=1；scope=`installed_source_chain_observation`；记录source_sha、architecture、Python major/minor、Windows版本数字（无平台名称/机器名）、protected_observed=false、launch_authorized=false、每资源固定role=source和resource=helper/verifier、owned image SHA256及有限chain记录；chain仅index与directory/file类别，不含名称、路径、卷号/fileID、HANDLE或地址。

每对象包含metadata_observed_equal/descriptor_observed_equal、parser_result固定supported、policy_result有限pass/owner_untrusted/mutation_untrusted/empty_dacl；owner类别admin/system/host/other，admin/system优先于host以保证稳定。每ACE仅allowed、flags、既有目录/文件mutation mask交集与trustee类别admin/system/host/everyone/authenticated_users/builtin_users/creator_owner/owner_rights/other，类别优先级固定，不携带实际SID或其hash；owner_rights仍仅按既有policy处理，不额外信任。无raw SD、host SID、group SID、原异常正文、任意未过滤对象repr。source_policy_all_passed必须由所有policy_result是否pass重算，不接受自述。

预算：每资源root/祖先/file总计最多32，两个资源前后两轮成功解析的ACE累计最多512（相同snapshot也计两次），最终UTF8 JSON最多256KiB；严格上限不截断，不压缩成假完整。无法parse的snapshot一律FAIL，不启用宽松备用parser/新raw读取接口，仍受既有128KiB运输预算；本片不提供unsupported descriptor的完整分类，若原生遇到则另查根因。镜像用现有64MiB pin预算。每记录都是owned普通数据，无pointer或owner泄露。只有全部遍历与close成功才 `observation_complete=true`；任一policy拒绝使 `source_policy_all_passed=false`。诊断退出0仅代表完整、安全回收的观察，即使策略拒绝；固定compatibility_accepted=false，不打印compatibility=PASS或更新readiness。每资源回执须包含owned句柄总数、close确认数/未确认数（只由实际owner关闭状态核得，不猜测API调用次数）。

## 测试与接线

新增便携测试只核测试脚本数据脱敏/预算/分类/失败与回收合同；真实构造的SD测试既有parser/policy交叉核验，并保持其它模块不变。缺模块/入口应明确assertion RED，不能以ImportError冒充。覆盖每链位置native query故障、unsupported descriptor及与清理失败复合时均FAIL、owner/mutation/empty_dacl拒绝、directory DELETE_CHILD差异、重复snapshot漂移、private字段/hostile异常不泄露、任一close失败/KI/SE、输出预算与多资源backend隔离。正常观察有已识别policy拒绝也必须完整记录，既有policy本身不放宽。

`run_windows_wheel_ci.py` 只在实际installed provenance绑定成功后，用该venv Python `-I -B -X utf8` 调用新脚本，复用已有有界raw-byte subprocess监督，不使用_run的errors=replace解码来验证回执。父侧核精确schema、重复成员/类型/有限枚举/预算、完整观察/关闭确认及不授launch，再打印已验证的有限JSON；必须保留policy拒绝供核查。先行path式provenance成功不自动绑定随后pin的bytes，本片也不宣称这种绑定。已有direct-volume、缺失资源负控、签名与其它安装步骤不变。配套CI合同测试证明必需调用及失败阻断，不改workflow/权限、不创建服务。新SHA四格实际日志分别验；Win10/普通host仍另账。

## 非目标与验收边界

不实现生产consumer、protected迁移/安装、AccessCheck/组/TrustedInstaller放宽、加载/DLL白名单、首次UAC或启动身份交接；现有三个生产标志与R2/R3不变。GetSecurityInfo不保证竞争安全；分享锁不冻结WRITE_DAC/owner；二次snapshot相同仅表示观察一致，旧已授HANDLE/加载全窗口必须另验。策略拒绝不是发现漏洞，也不是兼容成功。

自审：真实问题、复用与调用链已确认；文件/数据流/失败/预算/平台和信用边界完整。实施须先核90704身份四格，通过后单写者TDD、独立SPEC后不同QUALITY、root全回读、关联与新完整preflight、两轮文档/站点及七维实际报告，提交推送main后核新安装四格。独立研究取舍见[实现前研究](../windows-startup-chain-permissions-research-2026-10-11.md)，本阶段补充研究另记，不以研究代验证。

阶段开始独立只读研究12:25–12:27 UTC复核本地90704与固定Codex8c0f701/SRT5507fb0两raw/Apache-2.0（未刷HEAD/二十名单）。采纳持有同HANDLE与分享/权限分开核查，暂缓Codex guard写对象与生产consumer，不适配SRT warn-and-continue/进程DACL重写；来源固定链接见上述研究。明确当前workspace不是installed、两个资源各新backend、词法路径不resolve、两轮ACE均计预算与先行provenance不替新held-bytes绑定。收益是识别真实兼容拒绝，成本是测试专用预算/脱敏/逐格证据；不复制源、新增依赖/权限。无新Windows原生/审查信用。

独立SPEC首轮C0/I2/M0：reader预parse导致unsupported异常无raw且不能与复合释放故障分类区分；policy另有empty_dacl拒绝。root全文核reader.read及policy实际调用，已将所有query_security异常保守FAIL并补有限empty_dacl枚举，不改产品运输接口/异常类型。修订后需同SPEC复核，再由不同QUALITY审设计；未预授通过。
