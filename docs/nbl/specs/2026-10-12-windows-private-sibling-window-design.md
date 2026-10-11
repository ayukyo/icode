# 私有父目录的 sibling 创建窗口候选设计

2026-10-12；设计文档基线提交 `e72c229`，生产与基础 fixture 源码基线仍为 `8b1afd4`。状态：设计已冻结，Task1–4实际CODE及整片SPEC → 不同QUALITY均C0/I0/M0；root32项portable/guard通过、18项连续20轮通过、208项关联回归196通过/12平台跳过，完整preflight三道通过，阶段发布待执行。未执行本片Windows原生实验，未取得安全或兼容通过信用，见[实施记录](../plans/2026-10-12-windows-private-sibling-window.md)。

## 真实问题与决策边界

前片直接 DACL 实验已有四格、16 条回执、48 个窗口的原生观察：READ-only sharing pin 没有阻止同宿主已获 full-control actor 的直接 WRITE_DAC。这是已观察的能力边界，不能解释为安全通过，也不能推导新增 sibling 是否被阻止。下一片只回答：同一私有 parent 内，当前宿主在 unpinned、pinned、released 三个窗口能否实际创建一个文件或目录？

三问已确认：真实问题是 sibling 创建尚无独立原生证据；现有私有 DACL fixture、primary-token 身份、pin、metadata ABI 和 security reader 可复用；调用链仅限测试和现有 Windows 必需选择器，不改变产品入口、启动授权、祖先 policy 或 sharing。

选择 A：四变体、有限窗口、私有自有对象的观测。收益是分开验证 Win32 路径创建与 Nt RootDirectory 相对创建；成本是测试专用 ctypes ABI、ownership 故障测试和四格原生运行。选择 B：直接修改生产 ACL/UAC/默认 pip 安装策略不适配，本实验没有不可信 principal 或 deployed 系统祖先证据。选择 C：新增服务/MSIX/权限机制暂缓，超出目前缺口。本片不测继承传播，不启用 privilege，不新增服务、依赖、网络或 workflow 权限，不放宽现有安全门。

## 复用点与最小改动范围

实现时新增 `tests/windows_private_sibling_fixture.py` 与 `tests/test_windows_private_sibling_window.py`，只追加该片必需测试接线。既有 `tests/windows_private_dacl_fixture.py` 保持原状；新 fixture 内部构造其 `_Fixture('parent', 'new')`，直接复用 prepare、observer、pin 获取和基础收尾；不调用旧 `_windows`、reset、operate、旧 event 或旧 scope validator。其 prepare 已先保护 leaf 再保护 parent，保留真实宿主、SYSTEM、Administrators 的 FA 及 Everyone READ_ATTRIBUTES marker。

| 当前代码锚点 | 可复用事实 | 本片限制 |
| --- | --- | --- |
| `tests/windows_private_dacl_fixture.py:93–181` | Win32 ABI、full-share observer open、NTFS 确认、初始 DACL 设置 | ADD 旁证须新测试专用方法，不能复用 WRITE_DAC open 当 ADD |
| 同文件 `:202–235` | `_ConvertedDacl` 独立 allocation 与一次 LocalFree | `acquire()` 返回 DACL interior pointer；创建必须使用 `output.value` 完整 SD 指针 |
| 同文件 `:237–322,399–595` | observer、真实私有创建、基础对象 ownership、全链 pin/收尾 | 三窗控制器新写；基础 fixture 不知道新 children，由外层先收尾 |
| `src/icode/windows_startup_native.py:34–72,95–111` | `_INFO_CLASSES`、`_UNICODE_STRING`、`_OBJECT_ATTRIBUTES`、`_IO_STATUS_BLOCK` 与 NtCreateFile ABI | 导入实际结构，不复制另造；本片只绑定测试 API，不改 backend |
| 同文件 `:141–184,228–261` | 相对打开、防 reparse、实际 HANDLE metadata/security | 新 create 的注册独立，不能把外来 HANDLE 放进 backend `_active` |
| `src/icode/windows_startup_pin.py:74–100,136–138,227–264` | 非空 startup leaf 验证、真实整链 pin、owner 生命周期 | 新建零长度测试文件用测试专用 validator；生产 `_metadata` 非空门不改 |
| `src/icode/windows_startup_security_native.py:77–122` | 真实 SD readback、self-relative 解析、有界复制/释放 | 每次 reader 清理须确认；不以构造 SD 代替实际 child SD |

源锚点是当前基线的核对入口。没有新产品 API、CLI 或外部 path/SID/SDDL/HANDLE 输入。公开测试入口仅接受两个 exact str 枚举 `route ∈ {win32, nt_relative}`、`kind ∈ {file, directory}`；无效参数及非 Windows 在加载 native API、捕获 token、创建临时目录之前失败。

## 固定对象与创建参数

每变体独立私有 root → parent → 原 leaf；实际 NTFS 必须由持有的 parent observer HANDLE 确认。root 外只有原 pin 的只读祖先持有。每窗使用一个固定 basename：`sibling-unpinned`、`sibling-pinned`、`sibling-released`，均是单个 ASCII component，无路径分隔符、冒号、设备别名、尾点或尾空格，UTF-16LE 长度有界且包含终止符的 MaximumLength 不溢出 USHORT。每变体的新 children 最多三个；完成三窗之前不删除任何已创建 child，避免 FileId 回收后误判跨窗身份相同。

四变体是 win32/file、win32/directory、nt_relative/file、nt_relative/directory。每变体恰三窗，单原生 grid 共 12 个窗口；x64/ARM64 × Python 3.11/3.12 完整四格若全部完成，最多 16 个变体回执、48 个窗口。这是选择数量，当前未执行本片。

child 固定 SDDL 为 `D:P(A;;FA;;;{host})(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x80;;;WD)`：真实 primary-token host SID、protected DACL、四条 allow ACE、无继承 flags；不存在 absent/NULL DACL。用复用 `_ConvertedDacl.acquire(host, 0x80)` 取得并验证 allocation，然后向创建 API 传 **`owner.output.value` 完整自相对 SD**，绝不传其返回的 DACL interior pointer。此 allocation 每变体仅一个 owner，从三个 native create 调用之前一直活到最后一窗 create/output 注册完成；即使中途失败也按一次 LocalFree 收尾。它与每次实际 GetSecurityInfo 的 SD allocation 分开记账。

Win32 的测试专用 `_SECURITY_ATTRIBUTES` ABI：DWORD uint32 `nLength`、pointer-width `lpSecurityDescriptor`、BOOL int32 `bInheritHandle`；nLength=sizeof(struct)、lpSecurityDescriptor=完整 SD pointer、bInheritHandle=0。结构及 SD 在整个 native 调用中存活。不给新 HANDLE 继承标志。

| 创建变体 | 固定参数 |
| --- | --- |
| Win32 file | `CreateFileW(exact_owned_path, 0x120081, 7, &SA, CREATE_NEW=1, FILE_FLAG_OPEN_REPARSE_POINT=0x200000, NULL)`；全分享、只读观察访问，无 GENERIC_WRITE/DELETE |
| Win32 directory | `CreateDirectoryW(exact_owned_path, &SA)`；BOOL 非零确认新建后立即局部注册 owned path，再以 `CreateFileW(path,0x120081,7,NULL,OPEN_EXISTING=3,BACKUP_SEMANTICS\|OPEN_REPARSE_POINT,NULL)` 取得 witness HANDLE |
| Nt file/directory | `NtCreateFile(&output,0x120081,&OA,&IOSB,NULL,0,7,FILE_CREATE=2,options,NULL,0)`；不提供 allocation/EAs |

Nt ABI 原样复用 production structures，`ntdll.NtCreateFile.restype=ctypes.c_int32`，11 参数与现有 `_configure_apis` 相同。OA Length=实际 sizeof、ObjectName 指向有界 single-basename UNICODE_STRING、Attributes=`OBJ_CASE_INSENSITIVE=0x40 | OBJ_DONT_REPARSE=0x1000`，不加 OBJ_INHERIT；SecurityDescriptor=完整 SD pointer、SecurityQualityOfService=NULL。RootDirectory 在 unpinned/released 为实际已持有 parent observer HANDLE；pinned 为真实 pin owner 倒数第二 parent HANDLE，先 `_require_open`、检查位置和身份；只借用，不能关闭/转移或伪注册它。

Nt options 固定为 `FILE_SYNCHRONOUS_IO_NONALERT=0x20 | FILE_OPEN_REPARSE_POINT=0x200000 | (FILE_DIRECTORY_FILE=0x1 或 FILE_NON_DIRECTORY_FILE=0x40)`，与 SYNCHRONIZE access 配对。Microsoft 的目录 options 列表与 OPEN_REPARSE_POINT 的一般说明尚不足以完整证明本组合在所有目标平台合法；这是明确的原生兼容验收项。若目录正控返回 INVALID_PARAMETER 等未知码，整变体 FAIL；不得移除 OPEN_REPARSE_POINT、改成路径 fallback、扩大 sharing 或 skip 来取得通过。

目录 desired access 的 `0x1` 依对象类型表示 LIST_DIRECTORY，与文件 READ_DATA 共用 bit；现有目录 observer 的 `0x120081` 已有前片实际目录读取证据，但这不能证明本片 Nt FILE_CREATE 目录组合已兼容。此创建组合保留为待原生正控证明的另一项，不因文字称为“read”而推导成功，也不自行删除 bit 获取通过。

Win32 创建失败仅实际 GetLastError 5/32/33 可记录有限 blocked；CreateFileW 成功须 pointer-width 整数、非 NULL/INVALID_HANDLE_VALUE、非当前 active/关闭未知 owner 数值碰撞。CreateDirectoryW 成功确认 owned path 与 witness 获取分开：后续 witness open/metadata/SD 失败属于已创建对象的证据失败，必须清理，不能归类 blocked。

Nt 成功须 **actual function return=0 AND IOSB.Status=0 AND IOSB.Information=FILE_CREATED=2 AND valid new HANDLE**。warning、STATUS_PENDING、非 FILE_CREATED、碰撞或部分输出一律 FAIL。Nt 非成功仅将实际 int32 return 转 unsigned32；有限 blocked 仅 `0xC0000022 / 0xC0000043 / 0xC0000054`。非 pending 的失败根据官方约定依赖函数 return，不要求失败 IOSB 与 return 相等，不把初始化的 IOSB=0 当成功；失败回执没有 IOSB 字段。其它码、reparse、collision、partial/unknown 均无回执。有限拒绝不推断 DACL 或 share 的根因。

## 每窗 ADD 旁证与真实效果

每个窗口只对 parent 做 **一个同 kind** 的直接 ADD open：file 请求 FILE_ADD_FILE=2；directory 请求 FILE_ADD_SUBDIRECTORY=4；`CreateFileW(parent, desired_add, share=7, NULL, OPEN_EXISTING=3, BACKUP_SEMANTICS|OPEN_REPARSE_POINT, NULL)`。不混入 GENERIC_WRITE/DELETE/WRITE_DAC，也不每窗同时打开两个 ADD 权限。成功 handle 立即一次 CloseHandle 确认，之后实际调用该窗 native create；有限拒绝码同为 5/32/33。

旁证不是 create 的先决门：ADD open 失败仍必须实际尝试本窗 create，不能用 direct-open code 合成 create result。若旁证是未知码或 close 不确认，本窗仍在 cleanup 可控的局部 try 内实际尝试 create，然后本变体 FAIL、无 wire、不进入后续窗口；保留第一次异常及 KI/SE 优先规则。这样不会把 RootDirectory 创建能力等同于额外 ADD HANDLE 的 sharing 结果。旁证调用本身被 KI/SE 打断则停止，不为补信用继续创建。

unpinned 和 released 必须实际创建成功且完成 witness、metadata、实际 child SD 验证，是两个正控；缺任何正控整变体 FAIL。pinned 允许实际 created 或有限 blocked，均如实记录，不预设“pin 应阻止 sibling”。同一变体 pinned created 只表示同宿主当前访问下发生新增对象；pinned blocked 只表示该 API 在本窗口有限拒绝。有且只有三窗都完成、所有稳定性及清理确认通过才可输出。

## 三窗生命周期与真实采样

```text
base.prepare(parent,new) → initial 身份/bytes 基线与双 SD 模板核验
  → 单 child SD owner 转换
  → unpinned: observer before → ADD旁证 → create/register → observer after → child witness
  → 真 pin_startup_file(leaf,max_bytes=4096)，核对 parent/leaf 基线身份
  → pinned: 借原 pin before → ADD旁证 → create/register → 借原 pin after → child witness
  → pin 全链逆序一次关闭，close_confirmed=true
  → released: observer before → ADD旁证 → create/register → observer after → child witness
  → child SD owner 一次 LocalFree
  → children 逆序 HANDLE close + 精确 unlink/rmdir
  → base.close(原 leaf/parent/root)
  → strict wire validate → 单行输出
```

每窗 before/after 都采实际 parent 和原 leaf：GetFileType=DISK；复用 `_INFO_CLASSES` 读取 basic/standard/tag/FileId；检验 volume/FileId/type/目录角色、无 reparse、非 DeletePending；叶用同一持有 HANDLE 的 SetFilePointerEx/ReadFile 实际读取 `len(_CONTENT)` bytes。parent、leaf 的实际 SD 都必须前后 raw bytes 相等，且符合 protected 固定 marker；二者身份始终等于初始 observer 基线，叶 bytes 始终等于 `_CONTENT`。pinned 使用 pin 原 backend query/query_security/read；unpinned/released 使用完整分享 observer，两者不能用 owner.content 缓存充当实时读取。

双 SD 的跨窗原字节基线明确取自 unpinned-before 的这两次真实读取，此后所有 before/after 均与之逐字节比较，不额外读取。base.prepare 已核验两份模板，但只保留最后 leaf raw，不能声称保留了 prepare 时 parent raw；首窗 leaf raw 还须与 base.initial 的已保留 leaf raw 相同。prepare 到首窗之间的 parent raw 不授连续观测信用，身份/bytes 仍与 base.initial 核对。这样既证明三窗口贯穿稳定性，又不靠未保存的初始 SD 或新增调用补预算。

prepare 已实际读 parent/leaf SD 各一次；之后每窗 before/after 各读二者 SD。pinned 新增的身份绑定检查合并在其 before sample，不增加额外 SD 读；不沿用旧 DACL `_windows` 的 reset/prepin_sample。整片无后续 SetSecurityInfo，不传播继承。parent ChangeTime 因目录项增加可能变化；每窗 parent/leaf metadata_changed 仅记录 exact bool，不要求整份 metadata 相等，不调用会自关闭的 production revalidate；volume/FileId/type 与 bytes/SD 稳定性仍硬门。

每个 created child 由其真正 witness HANDLE 查询，不以路径存在、native success 或传入模板自证。测试专用 metadata validator复用生产结构，exact types/ranges、disk、volume 同 parent、16-byte FileId、目录角色匹配、无 reparse/no DeletePending。file 要单 link、EOF=0；directory EOF 必须非负而不要求空文件语义，link 不套用生产 file 门。所有 child `(volume,FileId)` 与 parent/leaf 及此前保留 children 互异。真实 child SD 经现有 reader 读取/解析，要求 protected、无继承 ACE、四条固定 SID/mask；不要求 OS 填入 owner/group 等同于输入中未设置的字段。child SD 实际证明是模板 DACL，不将输入 SD 作为结果。

## ownership 与异常收尾

获取 native create 返回值、输出 HANDLE、已创建路径 registration 全部位于 **同一直接局部 try/except BaseException**；调用实际 native function，不能用 `_at_stage`、generic `_call` 或另一个 return wrapper 包住创建获取，制造 resource 已生成而调用方未见返回的 ownership 窗口。普通失败的有限诊断在 owner 收尾后由外层生成。SD 转换输出同样在 owner 范围内；所有返出 owner 的注册在 cleanup 边界之内。

每次 create 预先准备精确 path、输出容器、slot，成功回执与 registration 之间被打断时，本地 handler 根据实际保留的成功 result/IOSB 与输出作收尾。Win32 directory native BOOL 非零就登记 owned path，无需等 witness；Nt 只有 return=0、IOSB.Status=0、Information=2 确认 FILE_CREATED 才授权登记新路径，其他状态即使输出非 NULL 也不授权删除 pathname。Win32 file 只凭有效 CREATE_NEW 成功回执登记新路径。unknown result/输出写入后 native 抛错，不能猜测创建成功或删除既存对象。

valid、确认属此 acquisition、未与当前 active 或关闭未知 owner 数值碰撞的新 HANDLE 即使路径所有权未知也必须一次 close；当前仍持有的 owner 数值碰撞绝不关闭。出错后一个 close/free 尝试，无确认就 unknown，不重试旧数值/地址。不把非 NULL HANDLE 当 owned pathname；未知 path 不 unlink/rmdir，不递归清扫 root。任何未知 ownership/清理失败都无 wire，可能残留私有对象的失败必须报告固定 stage，不能伪造 cleanup=true。

测试 owner 以 acquisition 代次而非裸 HANDLE 数值标识生命周期：已确认关闭的 owner 保持 retired、绝不再次关闭；后续真实 native acquisition 可以合法复用其数值并建立新 owner 代次，不能为取得通过伪造输出。active/unknown ledger 包含本片已获取 child/ADD，以及当前借用的 base observer 和 pin 实际值；不冒充保存了 base.prepare 已关闭配置 HANDLE 的历史。pin 放行结束须确认整个 owner.close_confirmed 后才解除其 active 阻断；任意未确认关闭使整变体失败，不进入 released，不拿潜在新获取重试未知旧值。便携负控同时覆盖当前 active 碰撞、未知关闭拒绝及确认关闭后合法数值复用；生产 backend 的退役集合与规则不改。

正常 children 一直保留到全部三窗结束；外层首先逆序尝试每个 child HANDLE close，再对其确认 owned 的 exact path 做一次 file unlink 或 directory rmdir；没有递归、重试、通配符或外部目标。即使一个 close/remove 失败也尝试其它明确 owned children，再调用 base.close；失败不能获得回执。child 创建成功但 SD、metadata、registration 或 witness open 失败也按此收尾。pin release失败禁止 released窗口；中途失败停止后续窗口，仍收尾 pin、SD、children、base。基础 fixture 的收尾不能先删 parent 再由外层尝试 child。

保留主体 KeyboardInterrupt/SystemExit **原对象**；收尾异常不得替换。没有主体异常时，收尾中的 KI/SE 优先于普通错误，其余保留第一失败；继续一次尝试剩余明确 owned 资源。仅固定有限 stage 值的 sanitized diagnostic 输出，禁止私有 path/SID/raw SD/SDDL/HANDLE/address/native exception text 或 traceback。KI/SE 不输出“成功回执”，测试最外层沿用已有抑制私密 traceback 的边界。

## 回执协议：scope/schema 与合法组合

新增 scope=`private_sibling_window_observation`，schema_version=1，不复用 DACL scope。wire 必须 exact bytes、长度1至8192，每完整变体一个 ASCII JSON + 单 LF；canonical 为 `json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii') + b'\n'`。validator 拒绝重复 key、非 ASCII、额外空白/行、重排为非 canonical、缺失/额外 key、bool 冒充整数、str/int/bool subclasses。反序列化后重编码逐 byte 等于 wire。类型须 `type(x) is ...`，恒定 true/false/null 使用 `is`。

top exact keys：`scope, schema_version, route, kind, windows, cleanup_confirmed, consumer_ready, compatibility_accepted, launch_authorized`。route/kind 使用上述枚举；windows exact list 长3、按 unpinned/pinned/released；cleanup_confirmed=true；三个 authority 字段始终 false。无 acquisition、target、opener 或其它 scope 的字段。

每个 window exact keys：`window, direct_add, create, effect, parent_metadata_changed, leaf_metadata_changed, identity_stable, bytes_stable, parent_sd_stable, leaf_sd_stable, child`。window 为固定顺序 exact str；两个 metadata_changed 为 exact bool；四个 stable 恒 true；effect exact str，仅 created/blocked。

direct_add exact keys `{access, result}`。access exact int：file=2、directory=4；result exact int∈{0,5,32,33}，0 必须来自实际 valid HANDLE open 且一次关闭确认，非零来自实际失败的即时 GetLastError。任何 result 与 create 均无因果合法性约束，允许 ADD 拒绝而 create 成功或相反；该窗 create 必须实际调用。未知旁证不进入回执。

| route 与 effect | create exact object | child |
| --- | --- | --- |
| win32 + created | `{result:0}` | 下述 created child object |
| win32 + blocked | `{result:5或32或33}` | null |
| nt_relative + created | `{return_u32:0, iosb:{status_u32:0, information:2}}` | 下述 created child object |
| nt_relative + blocked | `{return_u32:3221225506或3221225539或3221225556}` | null，且 create 不含 iosb |

以上三个 decimal NTSTATUS 分别为 C0000022/C0000043/C0000054。所有 return/result/status/information 必须 exact int；合法对象的 key set 随组合精确校验。Win32 directory 的 result=0 表示已确认 native BOOL 非零并取得/验证 witness，不泄露任意 BOOL 原值；file 的 result=0表示已确认 CREATE_NEW HANDLE。Nt return_u32/status_u32 是各自实际 int32 值的 unsigned32 规范化，Information 是实际 pointer-width 输出，不合成 success。

created child exact keys：`identity_distinct, volume_matches, kind_matches, nonreparse, not_delete_pending, protected, template_verified, empty_file`。前七个恒 true，均须由上述 metadata/SD 实测；file 的 empty_file=true，directory 的 empty_file=null。blocked 必须 child=null。unpinned/released 必须 effect=created；pinned 可 created/blocked 且 create/child 严格对应。禁止 raw identity/SD/bytes/hash/path 或任意 exception 字段；跨 child identity 比较在进程内完成，不输出标识。没有部分变体、未清理、只有旁证或没有正控的合法回执。

有限失败前缀固定 `private_sibling_window_failed`，允许追加一个内部白名单 stage；白名单冻结为 `fixture,prepare,child_sd,initial,unpinned_before,unpinned_direct_add,unpinned_create,unpinned_after,unpinned_child,start_pin,pinned_before,pinned_direct_add,pinned_create,pinned_after,pinned_child,release_pin,released_before,released_direct_add,released_create,released_after,released_child,cleanup,wire`。不读取任意 exception 的自定义属性；stage 不接受外部字符串。route/kind 仅已验证固定枚举时可在最外层附带。没有原生数值/路径/私密文本的 failure wire。

## 固定预算与验收门

静态上限按四变体全部 created 算，不是 actual loader/native 计数；blocked 路径可少但不能授 credit。每变体 SD read=initial parent+leaf 2 + 三窗 before/after × parent+leaf 12 + children 3 =17；四变体68次 GetSecurityInfo allocation/free。基础配置转换每变体2，共8；child转换每变体1，共4。总 SD allocation/free 上限 **80**，不遗漏 setup，不新增 prepin SD sample。

HANDLE 上限：基础配置2+observer2，每变体4、合16；created child3×4=12（Win32 directory witness只计一个）；同kind ADD旁证3×4=12；pin每变体≤32，合≤128；primary-token capture每变体一个、合4。总计 **≤172** 次 native HANDLE acquisition/once close；base Python leaf stream四次 close另账。基础 prepare 以已验证局部 drive component chain≤32；所有循环固定有限。不得每窗两种 ADD（那会额外12至184），不得追加 observer/reopen或重试悄然突破预算。SD最大128KiB、原 leaf≤4096 bytes、新 file零bytes、三children、四variants。实际实现按真实调用图核算，超出须先修订设计并复核。

便携测试首先验证参数前置拒绝、SA/Nt 真实ABI及完整SD指针、OA root随窗口切换、basename/flags/disposition/share/access、direct ADD失败仍实际create、成功/有限blocked组合、nonpending failure IOSB不必等return、pending/warning/collision/partial拒绝。覆盖完整实际控制器而非 mock控制器，核验三窗及pin释放顺序、SD/identity/bytes双对象稳定、Child EOF专用validator不改生产门、三child ID互异、actualSD不符/缺效果、目录已创建后witness失败、取得后/注册前/return边界KI/SE、数值碰撞、不确认CloseHandle/LocalFree、未知pathname不删、全部owned逆序一次收尾、主体原对象优先、严格协议和预算。fake只能授软件 transport 信用。

Windows native使用两个方法按kind=file/directory，各实际执行route=win32/nt_relative，两方法全平台selector规则按现有方式：非Windows不选原生；Windows方法/fixture/subTest skip为失败；无NTFS、未知code、缺正控、未确认cleanup不skip。新 portable class 全平台必需一次，新增 native IDs 与 loader实际count同步，旧ID/可选语义保持。x64/ARM64 × Python3.11/3.12逐格读取完整原始日志，核对四variant/12windows及scope合法组合；任何格失败继续阻断，不能用Linux模拟或前片4grid代替。

流程门：设计先 SPEC、再不同 QUALITY，零C/I/M且冻结exact protocol/lifecycle后单writer TDD实现；实现复核、20轮、关联、完整preflight三道和文档/site、自检按既有工作流逐项完成。实际软件实施及已测项见顶部与实施记录，完整守护和原生结果另记，不写100%通过。部署/消费/加载/UAC/R2/R3无新增授权。

## 独立研究与取舍

2026-10-12只读研究固定版本：[Codex `8c0f7011674145da7e10627769fb221c74fbf7a0` 的 home.rs](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/codex-rs/windows-sandbox-service/src/ipc/home.rs)，[SRT `5507fb0e639c00f845554336ece62e27af5b1bb7` 的 vendor/srt-win-src/src/self_protect.rs](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/vendor/srt-win-src/src/self_protect.rs)；两个项目 LICENSE 均为 Apache-2.0（[Codex](https://github.com/openai/codex/blob/8c0f7011674145da7e10627769fb221c74fbf7a0/LICENSE)、[SRT](https://github.com/anthropics/sandbox-runtime/blob/5507fb0e639c00f845554336ece62e27af5b1bb7/LICENSE)）。本轮不刷新HEAD、不复制源码。Codex祖先/目标权限分门及SRT自身保护路径的观察仅作机制对照，不能借其实现授 ICODE security pass。

采纳：复用本地私有fixture、按API和窗口分账、actual创建及SD/identity回读、有限协议与清理后输出；收益可判别机制，成本已受固定预算约束，许可不增加依赖，安全门不变。暂缓：继承传播、多principal、系统安装祖先及持久保护；需要另片身份/权限与部署证据。 不适配：生产UAC/服务/MSIX策略、本host full-control代表不可信actor、READ-sharing等同目录创建封锁；没有相应证据或任务授权。

官方依据：[NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile)、[IO_STATUS_BLOCK](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ns-wdm-_io_status_block)、[OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes)、[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)、[CreateDirectoryW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectoryw)、[SDDL转换](https://learn.microsoft.com/en-us/windows/win32/api/sddl/nf-sddl-convertstringsecuritydescriptortosecuritydescriptorw)、[MS-ERREF NTSTATUS](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-erref/596a1078-e883-4972-9bbc-49e60bebca55)。这些原文支持ABI、FILE_CREATE/FILE_CREATED、非pending返回语义、显式SD与有限status；目录option组合仍以原生正控判定，不能从文档空隙授兼容。

【架构级自检报告（设计阶段）】

- 语法/文档：结构与参数、协议字段已逐项核对；SPEC → 不同 QUALITY 均 C0/I0/M0。
- 依赖/调用链：复用点与测试接线边界完整；新增测试fixture与必测接线已实现，生产源码未修改。
- 逻辑/边界：正控、旁证独立、实际create、success/failure IOSB、三窗顺序明确。
- 异常处理：native获取与注册同try、unknown ownership、一次收尾、KI/SE原对象优先明确。
- 关联模块：新scope与新fixture分开；生产validator与旧DACLfixture不变。
- 兼容安全：不新增authority；Nt directory options兼容性待原生证明。
- 可运行性：实际portable/guard及关联回归见实施记录；native及四格验收待执行，不授原生或100%信用。
