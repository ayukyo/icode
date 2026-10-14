# macOS M0a2 固定向量 V1–V11 实施计划

> For agent: REQUIRED SUB-SKILL nbl.superpowers:nbl.executing-plans，仅 root 全文及 fresh SPEC→不同 QUALITY 批准后使用。当前 PLAN ONLY，不执行任何代码/TEST/CI/Git/root操作。
> Goal: 同一候选 SHA 两 Mac 原生满足旧 A18 + 新 B26，仅关闭固定向量分片。
> Architecture: 独立固定 native TEST 链接真实 groups TU + baseline/source quota TU；最小机械 include，共用固定 root/lease 路径，不复制整 driver/predicate，不新增通用 root/path API。
> Stack: Darwin C11、公共 getgroups、固定 Seatbelt profile、libproc/sysctl/kqueue、Python3.11、GitHub CI。

## 1. 批准边界和真实问题

批准 DESIGN：docs/nbl/specs/2026-10-14-macos-m0a2-quota-design.md，152L，SHA256 39e4b5675e0864cd9daeef683f48b1e5e60b3f9138cb5fe0761d70314a62540e；root全文回读、fresh SPEC→不同QUALITY C0/I0/M0。root实际 sequential-thinking 17c5f5三步用于原DESIGN。本PLAN仍待双审；480秒共用绝对deadline是root允许纳入待审资产的唯一推荐，不是实施批准。

三问已确认：cap1不能证明cap2、继承/僵尸/UID隔离是真实缺口；已有fixed observer、lease、groups/profile可复用；新controller→新固定TEST→真实quotaTU，不改变旧A wire/classification。唯一方案：先可运行TEST-only no-quota baseline真实第三进程成功+首byte，再不同SOURCE作者仅扩cap2，最后同新SHA重跑A+B。cap2旧EINVAL、编译/import/缺文件错误、observer ERROR不是nativeRED。

不做cap4/race、C launchfault/faultprofile、M0b escape、M1/ready、账号/daemon、raw syscall/私有alias、目录补丁、产品canary allow、root正控代非root、放宽权限或profile。当前诊断候选仍在途，不因此push新候选。root单独发布；本作者仅写本文件。

## 2. 实例计数及预算（全部拟议，未执行）

|每架构 job|实例来源|实例|nominal UID|状态|
|---|---|---:|---:|---|
|A|原baseline7 + SOURCE7 + W1两binary各2|18|20|旧job原门全保留，不能借旧SHA|
|B baseline|V3 quota-labelled + control|2|2|真实第三fork成功首byte|
|B SOURCE|V1–V8各quota/control|16|16|8×2|
|B SOURCE|V9 quota/control/root calibration|3|2|root校准不消费任务UID|
|B SOURCE|V10 independent quota/control各两UID + shared反例一UID|3|5|实际3cases/6roots|
|B SOURCE|V11 guard + shared counterexample|2|2|1root+2roots|
|B小计|baseline2+SOURCE24|26|27|both共用480秒|
|本片|A18+B26|44|47|每架构2jobs；双架构4jobs/88实例|
|C|剩余launchfault及正控|22|独立冻结|未实现阻断|
|D|轮0..15每轮quota/control各1|32|32|未实现阻断|
|E|轮16..31每轮quota/control各1|32|32|未实现阻断|
|最终每架构|18+26+22+32+32|130|独立发放|拟议5jobs|
|最终两架构|2×130|260|不复用已发lease|未跑、不得称完成|

A实例来源沿批准DESIGN/既有controller；W1同PID exec是case内observation，不另计完整case。若实际A统计不匹配18/20，停止报告，不改oracle补数字。B固定SOURCE_NAMES/CONFIGS24与C表24必须机械一致。

每job≤48cases（最终各job最大32），单case≤15秒、job≤10分钟、导出总原件≤16MiB；JSON行≤4096、case≤64KiB、ledger≤2MiB、case≤64dataevents。固定数组容量为8个owned slot；本B实际任务峰值≤6、加observer≤7，遵守原任务上限8。总活跃线程≤4含main。V6先3个worker并发并join，再第4个并join：create4/join4、峰main+3=4，随后fork；不称4worker并发。UID/GID60000..61023仅1024、持久lease不回收、耗尽failclosed。

B build/binding/baseline/SOURCE/发布共用CLOCK_MONOTONIC绝对480秒；build子预算min(共同deadline,now+90秒)。case alarm=min(15,剩余向下取整秒)，剩余<1拒绝，不重置deadline。15秒是上限，不保证所有case都能耗满；超时失败不放宽预算。新observer CPU20 exactreadback；旧W1 CPU10不动；任务CPU2/FSIZE64KiB。root超时自终结不等于整树回收，未知保留隔离，不凭alarm报零残留。

## 3. 全向量映射

|向量|quota oracle|同代码正控/独立观察|收尾|
|---|---|---|---|
|V1 fork/exec|cap1 fork=-1/EAGAIN无首byte|noquota成功先byte再exec固定镜像START|barrier，父wait/reap|
|V2 spawn|返回EAGAIN，不以errno代返回值，不读失败PID|同fileactions成功首byte、固定S入口|仅成功且有byte的child登记|
|V3 rootchildthird|cap2第一child成功，第三fork EAGAIN|noquota第一和第三成功且各byte1/errno0|固定slots，ACK后reap|
|V4 refork|cap2实际reap后可再fork|无profile控制分离Seatbelt影响|先reap再试，不复用PID/slot|
|V5 grandchild|root+child cap2，child fork EAGAIN|noquota grandchild成功/byte|child亲自reap，root再reap|
|V6 pthread|create4/join4后cap1 fork EAGAIN|noquota同分波线程流程可fork|独立pti_threadnum峰4；join先于fork|
|V7 zombie|退出未reap仍占cap2；reap后可fork|noquota同waitid WNOWAIT流程|observer PID/start/SZOMB=5，真实wait|
|V8 softrestore|hard2，soft1阻fork，restore2后成功|noquota同fork成功及真实inherited pair，不执行降软/恢复|每次getrlimit；异常child仍登记|
|V9 hardraise|非root hard2→3 EPERM，pair不变|非root控制及独立root calibration设置3/3并读回|root不代非root，最后健康fork|
|V10 UID|两个不同UID各root+child；同UID双root阻fork|两root独立四ID/saved/组/PID/start/count|ownedroots各reap，共享反例不混|
|V11 migration|同attempt第二入口EPERM且未fork|TEST-only绕guard真实双root同UID cap1反例|不加产品canaryallow，实际root计数|

forkchild先异步信号安全write、再read/close/execve/_exit，不在线程活跃后unsafe fork；pthread全部join先于fork。spawn S先write首byte，不以exec名义代执行。FD3配置/FD4release在payload为EBADF；data5/ACK20..27固定。先占3..31防dup2互毁，普通pipe继承，明确关闭其它FD。
正常路径在READY后新建kqueue注册NOTE_EXEC/EXIT，再发R，不能信用T/G早期exec。root校准单独R入口注册不混普通payload信用。完整实现见资产。

## 4. 最小复用和原A保护

fixed_helpers.inc精确抽旧driver all_write至identity_lease include前原文，再加原canaries函数；原位置换include并删canaries。profile、镜像hash、路径/identity/errno原文不变。
unused_identity.inc精确抽旧W1 supplementary_free与reserve_unused_id；W1原位include，main/CPU10不抽取。新TEST同一lease_root/owner_text、同/private/var/icode-m0a1.固定前缀，不加通用root/path参数。

fixed_helpers依赖：Darwin/CommonCrypto/ACL/dyld/MachO/fcntl/unistd/stat/limits/errno/stdio/stdlib/string/inttypes头；MAX_IMAGE/PATH_MAX、image/directory/binary_hash/sandbox_hash、canary_errno/canary_allowed、die。unused_identity依赖：sysctl/user/NGROUPS/uid_t/errno、UID_FIRST/UID_COUNT/MAX_PIDS/unavailable/candidate、die、lease_directory/reserve_uid/process_count；先include原identity_lease再unused_identity。资产给完整前置声明和headers。

精确保留旧lease：pre-reservation已知busy未发lease直接跳过；O_EXCL成功后发出lease永久不复用；postreservation组/进程collision烧已发lease继续；unknown立即die不得被下一成功隐藏。不是“预碰撞也永久烧lease”。READY/START/结束独立count，unknown隔离。
软件exact-inverse把两projected文件反向恢复完整原hash，非textassert。旧A仅source_hashes新增2include：baseline15→17、source16→18，其wire72/96、gate/release/phase/exit、7cases、5正式TEST与classification不动。旧SHA结果不能替新SHA。

## 5. 输入冻结

|输入|SHA256|
|---|---|
|driver.c|944c9268461e522a01653b46bb3c18d038504af66910c66cf861901f8f28d25e|
|W1native.c|eb51b489cd07399414b98dc409fe08637c56d3b1e99636def493348d0d1aa636|
|run_macos_m0_ci.py|b44cea4e111eae1a69183db254093191e44f242bc353cdc2d9aa8cf555ab53af|
|native/mac/CMakeLists.txt|4812f7ea7b8e546a2e4412eb4a52be3bc6f40f7b769ff5435a79cf9a07be3d54|
|.github/workflows/ci.yml|0abad9d728f177a4094ff98ea563c6d07a171f44fb667c2d2f041545ee89d0d4|
|limit.c|507b26a2d2ff1cca663c4c52f8ead50b1a4991563f1942e0f7d2a8f39dcc208c|
|identity_lease.inc|3f8563da5c30d55469776a212b397e4515a33b090dae4d387d8439ffc0226e82|
|原formalTEST|d0438e66bd356aefdfd2ebdd8edaa12529a88f18fb8c5556d2404c672291dafd|
|W1TEST472L|1ed2b2d8d3f2606a9fdf07fa94a0809919f54e23c2f2d515921dfcef8d6f2ed1|
|groups.c|b0a75c2ca2ee28334821c085c4460ab130ba6e1a02acc488d992491d57984ce6|
|groups.h|e739bff808adda9a98158b78419cbfa0d99b99160d4c1987bea7e116d43d4bdd|
|baseline.c|b861c67ee46e4c21cc22c5cac7a86879fcf038156d6ca4f4d963aa4818e3b596|
|原DESIGN124L|774e33f4c2485da553f6b41572ef9641c4b30dea307a8e466c2bbdca7b2e5b23|
|原PLAN1664L|37e4852cb9c25dfa2154ec8356d5416859125271f14b27d8d45f46bc44168ee7|

路径全称见patch/新controller源码source_hashes。漂移先只读核验并重审patch，不覆盖root后续诊断/文档改动。baseline链接既有完整源码不改；actualvariant必须baseline。TEST独立作者先冻结，SOURCE不得改断言补绿。

## 6. 证据、异常与RED

历史冻结95114042eed4daafdebcade5f15f74391b54cabc031249057f0a0841fcfc0a0d保留为审查历史，不再作为当前候选计划。该版存在真实observer盲点：删除fork_exec_c全部创建/childSTART/reap、修正FINISH与events后仍可通过。此修订只改本文TEST资产与措辞，不宣称实际生产修复。

新增CREATION_CONTRACT逐case冻结真实C固定slots（父→子）：V1/V2/V6为0→2，q/c尝试均1、成功0/1；V3为0→2再0→4，尝试2、成功1/2；V4同slots且2成功、首reap先于第二fork；V5为0→2再2→4，成功1/2；V7为0→2、0→4、0→6，尝试3、成功2/3，SZOMB观察→中间尝试→首reap→末fork；V8q为0→2失败、0→4成功，另LOWER/RESTORE两op，c仅0→2成功且保留inherited pair；V9q/c各0→2成功，q另RAISE/EPERM；V10 independent两root分别0→2/4和1→3/5，共4尝试，q成功2/c成功4，shared仅0→2和1→3两次失败；V11/rootcal没有fork，必须有专用admission/两rootSTART/calibration op证据。baseline两V3均两次成功，不把baseline真实错误行为拒于parser外。

严格parser先核operation类型/父slot/子slot/每父尝试顺序和成功/拒绝结果，再核完整START/FINISH/DONE及亲父reap集合、fork→childSTART→reap、grandparent DONE→root reap、refork/zombie因果序。不同root之间不加虚假总序。所有缺证据通过need抛ValueError，不靠IndexError或非空循环。新增模型负控逐case删全部创建（同时清掉后代/亲父reap、将FINISH rc改0）、删一次尝试、逐个删childSTART或reap；无fork实例删专用证据。每次修正end.events，113场景全部语义拒绝。

manifest严格四键version/root_directory/ledger_sha256/cases；重复键、类型、非法path/version/digest/count、stderr非空、非零exit、不完整输出拒绝。protected目录/ledger核root owner/mode/nlink/size及读前后device/inode/mtime/ctime/hash。JSONL完整LF、有限行、无未知/缺键、PID/start/parent/UID/FD/group/limit/cleanup完整；失败不得发布vectors-result.json。真实run_vectors/bounded_native/prepare_build软件正负控仅替OS/工具边界，不授native信用。

新parser第三arg固定16小写hex，溢出/clock秒纳秒/乘法检查；0<remaining≤480e9ns，同公共CLOCK_MONOTONIC单位；启动/case取min，不续租。controller只对仍持有的Popen leader组发信号，非root杀root可能失败，native自alarm/unknown隔离，绝不声称自动整树清零。

正式nativeRED：baseline两个V3实际第一/第三child均成功、各byte1/errno0，inheritedpair足够3；formal5运行，仅test_cap2_quota_semantic含M0A2_CAP2_REJECTION的assert失败，4P/1F/0E/0skip。无首byte、limit不足、observer错误、cap2 EINVAL都非RED。软件opt-in真实旧quotaTU+OSstub的M0A2_CAP2_API assertionRED仅辅助，不代双Mac真实RED。

最终SOURCE两Mac同SHA：A18所有原门 + B baseline2真实RED/SOURCE24 formal5GREEN/0E/0skip；原W0 SDK/header/object/final普通_getgroups无DARWIN_EXTSN、W1双组EPERM/同PIDexec、原7case、实际raw/binary/sourcehash/ownedroot零残留全部重核。新controller baseline22/source23源hash、actualOS/SDK/arch/compiler/object/final/raw独立绑定；符号不代运行。B只局部GREEN，M0a2/M0b/M1保持false。

## 7. 串行任务（未来，当前STOP）

Task1 root全文/asset LF/hash→freshSPEC→不同QUALITY，冻结独立TEST作者、不同SOURCE作者、独立实际双审。
Task2 TEST作者落地5新文件、机械driver/W1/A摘要patch、CMake、CIenv0；limit.c不动。默认-j1仅针对性软件。第一命令15方法=9软件PASS/5native skip/1optin skip；第二命令10软件中唯一API assertionRED/0E，5native skip不计native信用。
```bash
python -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
ICODE_M0A2_LIMIT_SOFTWARE=1 python -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
```

软件9含44collector边界、6build场景、17clock C检查、严格模型及逐case113种创建证据删除负控、exactinverse。root独立审后main发布TEST-only候选，两MacB2真RED并同SHA旧A18；不把compile/import或missingtarget报RED，不改冻结TEST补绿。
Task3 两Mac正式RED/独立TEST审后，不同SOURCE作者仅cap2 patch+CIenv1；cap0/3/4仍EINVAL，disabled无OS调用，errno/readback/variant原样。optin第二命令应10软件PASS、5native skip。SOURCE实际freshSPEC→不同QUALITY后root单独发布。
Task4 两Mac同新SHA A18+B26，B单controller both共480秒；baseline唯一quotaassertRED，SOURCE5GREEN，所有raw/hash/cleanup独立核。线上优先，不本机full/native/root，不取消/重跑遮失败。
Task5 仅关闭V1–V11。C22/D32/E32、M0b/M1阻断；race后独立TEST真实RED→不同SOURCE才扩4，最终同SHA A–E260实例不可删。

## 8. 完整执行资产

每fence去围栏保留末LF为目标字节。patch交apply_patch，仅未来Task2/3依序执行。没有placeholder/TODO/可注入产品provider；stub仅TEST OS边界。当前只新增本PLAN。

### Asset: native/mac/tests/icode_m0a1_fixed_helpers.inc

```c
static int all_write(int fd,const void *buf,size_t n) {
    const unsigned char *p=buf;
    while(n) {
        ssize_t r=write(fd,p,n);
        if(r<0 && errno==EINTR) continue;
        if(r<=0) return errno ? errno : EIO;
        p+=r; n-=(size_t)r;
    }
    return 0;
}
static int all_read(int fd,void *buf,size_t n) {
    unsigned char *p=buf;
    while(n) {
        ssize_t r=read(fd,p,n);
        if(r<0 && errno==EINTR) continue;
        if(r<=0) return r==0 ? EPIPE : errno;
        p+=r; n-=(size_t)r;
    }
    return 0;
}
static int read_record(int fd,void *buf,size_t n) {
    struct pollfd p={.fd=fd,.events=POLLIN};
    int r;
    do { r=poll(&p,1,11000); } while(r<0 && errno==EINTR);
    if(r<=0) return r==0 ? ETIMEDOUT : errno;
    return all_read(fd,buf,n); /* Fixed writer plus child alarm bounds read. */
}
static int hex_string(const char *s,size_t n) {
    if(strlen(s)!=n) return 0;
    for(size_t i=0;i<n;i++)
        if(!((s[i]>='0' && s[i]<='9') || (s[i]>='a' && s[i]<='f'))) return 0;
    return 1;
}
static int numeric(const char *s,int low,int high) {
    char *end=NULL; errno=0; long v=strtol(s,&end,10);
    if(errno || end==s || *end || v<low || v>high) die("numeric");
    return (int)v;
}
static int acl_safe(const char *path,struct stat *st) {
    filesec_t sec=filesec_init();
    if(!sec) return errno ? errno : ENOMEM;
    int e=0,present=0;
    if(lstatx_np(path,st,sec)<0) e=errno;
    if(!e && filesec_query_property(sec,FILESEC_ACL,&present)<0) e=errno;
    acl_t acl=NULL;
    if(!e && present) {
        if(filesec_get_property(sec,FILESEC_ACL,&acl)<0) e=errno;
        if(!e && (!acl || acl==(acl_t)_FILESEC_REMOVE_ACL || acl_valid(acl)<0)) e=EINVAL;
        acl_permset_mask_t read_mask=ACL_READ_DATA|ACL_EXECUTE|ACL_READ_ATTRIBUTES|
            ACL_READ_EXTATTRIBUTES|ACL_READ_SECURITY|ACL_SYNCHRONIZE;
        for(unsigned i=0;!e && i<=ACL_MAX_ENTRIES;i++) {
            acl_entry_t entry; errno=0;
            int r=acl_get_entry(acl,i==0 ? ACL_FIRST_ENTRY : ACL_NEXT_ENTRY,&entry);
            if(r<0 && errno==EINVAL) break; /* Valid ACL, validated iterator exhausted. */
            if(r!=0 || i==ACL_MAX_ENTRIES) { e=EPROTO; break; }
            acl_tag_t tag; acl_permset_mask_t permissions=0;
            if(acl_get_tag_type(entry,&tag)<0 || acl_get_permset_mask_np(entry,&permissions)<0) {
                e=errno; break;
            }
            if(tag!=ACL_EXTENDED_ALLOW && tag!=ACL_EXTENDED_DENY) { e=EPROTO; break; }
            /* Conservative: no principal may gain mutation rights through an ALLOW ACE. */
            if(tag==ACL_EXTENDED_ALLOW && (permissions&~read_mask)) { e=EPERM; break; }
        }
    }
    if(acl && acl!=(acl_t)_FILESEC_REMOVE_ACL && acl_free(acl)<0 && !e) e=errno;
    filesec_free(sec);
    return e;
}
static int secure_chain(const char *path) {
    char copy[PATH_MAX];
    if(path[0]!='/' || strlen(path)>=sizeof(copy)) return EINVAL;
    struct stat root;
    int e=getuid()==0 ? acl_safe("/",&root) : (lstat("/",&root)<0 ? errno : 0);
    if(e) return e;
    if(root.st_uid!=0 || (root.st_mode&022) || !S_ISDIR(root.st_mode)) return EPERM;
    strcpy(copy,path);
    for(char *p=copy+1;;p++) {
        if(*p!='/' && *p) continue;
        char saved=*p; *p=0; struct stat st;
        e=getuid()==0 ? acl_safe(copy,&st) : (lstat(copy,&st)<0 ? errno : 0);
        if(e) return e;
        if(st.st_uid!=0 || (st.st_mode&022) || S_ISLNK(st.st_mode)) return EPERM;
        *p=saved; if(!saved) break;
    }
    return 0;
}
static void self_path(void) {
    char buf[PATH_MAX]; uint32_t n=sizeof(buf);
    if(_NSGetExecutablePath(buf,&n)!=0 || !realpath(buf,image)) die("self-path");
    strcpy(directory,image);
    char *slash=strrchr(directory,'/');
    if(!slash) die("self-directory");
    *slash=0;
}
static int hash_fd(int fd,char out[65],size_t bound) {
    CC_SHA256_CTX ctx; unsigned char buf[65536],digest[CC_SHA256_DIGEST_LENGTH];
    if(lseek(fd,0,SEEK_SET)<0 || CC_SHA256_Init(&ctx)!=1) return EIO;
    size_t total=0;
    for(;;) {
        ssize_t n=read(fd,buf,sizeof(buf));
        if(n<0 && errno==EINTR) continue;
        if(n<0) return errno;
        if(!n) break;
        if((size_t)n>bound-total) return EFBIG;
        total+=(size_t)n;
        if(CC_SHA256_Update(&ctx,buf,(CC_LONG)n)!=1) return EIO;
    }
    if(CC_SHA256_Final(digest,&ctx)!=1) return EIO;
    for(size_t i=0;i<sizeof(digest);i++) sprintf(out+2*i,"%02x",digest[i]);
    out[64]=0; return 0;
}
static int protected_image(const char *expected) {
    const char prefix[]="/private/var/icode-m0a1.";
    if(strncmp(directory,prefix,sizeof(prefix)-1)!=0) return EPERM;
    int e=secure_chain(image);
    if(e) return e;
    int fd=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0) return errno;
    struct stat st; char digest[65];
    e=fstat(fd,&st)<0 ? errno : (!S_ISREG(st.st_mode) ? EINVAL : 0);
    if(!e) e=hash_fd(fd,digest,MAX_IMAGE);
    if(close(fd)<0 && !e) e=errno;
    if(!e && strcmp(digest,expected)) e=EPERM;
    return e;
}
static void create_file(const char *name,const void *data,size_t n,mode_t mode) {
    char path[PATH_MAX];
    if(snprintf(path,sizeof(path),"%s/%s",directory,name)>=(int)sizeof(path)) die("path");
    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0 || all_write(fd,data,n) || fchmod(fd,mode)<0 || fsync(fd)<0) die("create-file");
    if(close(fd)<0) die("close-file");
}
static void prepare_image(const char *expected) {
    int in=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC); struct stat st;
    if(in<0 || fstat(in,&st)<0 || !S_ISREG(st.st_mode) || st.st_size<=0 || st.st_size>MAX_IMAGE)
        die("source-image");
    struct mach_header_64 mh;
    if(all_read(in,&mh,sizeof(mh)) || mh.magic!=MH_MAGIC_64) die("native-Mach-O");
#if defined(__arm64__)
    if(mh.cputype!=CPU_TYPE_ARM64) die("Mach-O-arm64");
#elif defined(__x86_64__)
    if(mh.cputype!=CPU_TYPE_X86_64) die("Mach-O-x86_64");
#else
#error Unsupported native macOS architecture
#endif
    char observed[65];
    if(hash_fd(in,observed,MAX_IMAGE) || strcmp(observed,expected)) die("source-hash");
    if(secure_chain("/private/var")) die("protected-parent");
    strcpy(directory,"/private/var/icode-m0a1.XXXXXX");
    if(!mkdtemp(directory) || chmod(directory,0755)<0 || secure_chain(directory)) die("fixture-directory");
    char target[PATH_MAX];
    if(snprintf(target,sizeof(target),"%s/probe",directory)>=(int)sizeof(target)) die("copy-path");
    int out=open(target,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(out<0 || lseek(in,0,SEEK_SET)<0) die("copy-open");
    unsigned char buf[65536]; size_t copied=0;
    for(;;) {
        ssize_t n=read(in,buf,sizeof(buf));
        if(n<0 && errno==EINTR) continue;
        if(n<0) die("copy-read");
        if(!n) break;
        if((size_t)n>MAX_IMAGE-copied || all_write(out,buf,(size_t)n)) die("copy-bound");
        copied+=(size_t)n;
    }
    if(hash_fd(out,observed,MAX_IMAGE) || strcmp(observed,expected) ||
       fchmod(out,0555)<0 || fsync(out)<0) die("protected-copy-hash");
    if(close(in)<0 || close(out)<0) die("copy-close");
    strcpy(image,target); strcpy(binary_hash,expected);
    create_file("allowed","A",1,0444); create_file("denied","D",1,0444);
    const char bad[]="(version 1)(";
    create_file("bad.sb",bad,sizeof(bad)-1,0444);
    char profile[4096];
    int n=snprintf(profile,sizeof(profile),
        "(version 1)\n(deny default)\n(allow process-exec)\n(allow process-fork)\n"
        "(allow signal (target same-sandbox))\n(allow process-info* (target same-sandbox))\n"
        "(allow sysctl-read)\n"
        "(allow file-read-metadata file-test-existence (path-ancestors \"%s\"))\n"
        "(allow file-read* file-test-existence (literal \"/\") "
        "(subpath \"/usr/lib\") (subpath \"/System/Library\") "
        "(literal \"%s\") (literal \"%s/profile.sb\") (literal \"%s/allowed\") "
        "(literal \"%s/not-created\"))\n",
        image,image,directory,directory,directory);
    if(n<=0 || n>=(int)sizeof(profile)) die("profile-bound");
    create_file("profile.sb",profile,(size_t)n,0444);
}
static int canaries(int sandbox) {
    char path[PATH_MAX]; snprintf(path,sizeof(path),"%s/allowed",directory);
    int f=open(path,O_RDONLY|O_NOFOLLOW);
    if(f<0) return errno;
    char value=0;
    int e=all_read(f,&value,1);
    if(close(f)<0 && !e) e=errno;
    if(e || value!='A') return e ? e : EPROTO;
    canary_allowed=1;
    snprintf(path,sizeof(path),"%s/denied",directory); errno=0;
    f=open(path,O_RDONLY|O_NOFOLLOW); canary_errno=f<0 ? errno : 0;
    if(f>=0) {
        e=all_read(f,&value,1);
        if(close(f)<0 && !e) e=errno;
        if(e || value!='D') return e ? e : EPROTO;
    }
    return (sandbox && canary_errno!=EPERM && canary_errno!=EACCES) ||
           (!sandbox && canary_errno) ? EPROTO : 0;
}
```

### Asset: native/mac/tests/icode_m0a1_unused_identity.inc

```c
static int supplementary_free(gid_t gid) {
    pid_t pids[MAX_PIDS];int n=proc_listallpids(pids,sizeof(pids));
    if(n<=0 || n>=MAX_PIDS) return -1;
    for(int i=0;i<n;i++) {
        if(pids[i]<=0) continue;
        struct kinfo_proc info;memset(&info,0,sizeof(info));size_t size=sizeof(info);
        int mib[]={CTL_KERN,KERN_PROC,KERN_PROC_PID,pids[i]};
        if(sysctl(mib,4,&info,&size,NULL,0)<0 || size!=sizeof(info)) {
            errno=0;
            if(kill(pids[i],0)<0 && errno==ESRCH) continue;
            return -1;
        }
        int count=info.kp_eproc.e_ucred.cr_ngroups;
        if(count<0 || count>NGROUPS) return -1;
        for(int j=0;j<count;j++) if(info.kp_eproc.e_ucred.cr_groups[j]==gid) return 0;
    }
    return 1;
}
static uid_t reserve_unused_id(int leases) {
    for(unsigned attempt=0;attempt<UID_COUNT;attempt++) {
        uid_t uid=reserve_uid(leases,candidate);
        int empty=supplementary_free((gid_t)uid);
        if(empty<0) die("supplementary-snapshot");
        int active=process_count(uid);
        if(active<0) die("identity-process-snapshot");
        if(empty==1 && active==0) return uid;
        /* A collision burns its permanent lease; no identity is retried or cleaned. */
    }
    errno=ENOSPC;die("supplementary-exhausted");return 0;
}
```

### Asset: native/mac/tests/icode_m0a2_vectors.c

```c
#define _DARWIN_C_SOURCE 1
#include "icode_m0a1_limit.h"
#include "icode_m0a1_process_groups.h"
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <inttypes.h>
#include <libproc.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <poll.h>
#include <pthread.h>
#include <pwd.h>
#include <signal.h>
#include <spawn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/acl.h>
#include <sys/event.h>
#include <sys/param.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <sys/user.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
enum { UID_FIRST=60000,UID_COUNT=1024,MAX_PIDS=8192,MAX_IMAGE=16*1024*1024,
       VMAGIC=0x4d304132,CONFIG=100,READY=101,START=1,OP=2,FORKED=3,
       REAPED=4,THREADS=5,ZOMBIE=6,FINISH=7,DONE=8,
       FORK_OP=1,SPAWN_OP=2,LOWER=3,RESTORE=4,RAISE=5,DENY=6,CALIBRATE=7 };
struct definition { const char *name;int vector,quota,profile,cap,roots,shared; };
static const struct definition source_cases[]={
 {"fork_exec_q",1,1,1,1,1,0},{"fork_exec_c",1,0,1,1,1,0},
 {"spawn_q",2,1,1,1,1,0},{"spawn_c",2,0,1,1,1,0},
 {"third_q",3,1,1,2,1,0},{"third_c",3,0,1,2,1,0},
 {"refork_q",4,1,1,2,1,0},{"refork_c",4,1,0,2,1,0},
 {"grandchild_q",5,1,1,2,1,0},{"grandchild_c",5,0,1,2,1,0},
 {"pthread_q",6,1,1,1,1,0},{"pthread_c",6,0,1,1,1,0},
 {"zombie_q",7,1,1,2,1,0},{"zombie_c",7,0,1,2,1,0},
 {"soft_q",8,1,1,2,1,0},{"soft_c",8,0,1,2,1,0},
 {"hard_q",9,1,1,2,1,0},{"hard_c",9,0,1,2,1,0},
 {"hard_root_calibration",12,0,0,3,1,0},
 {"independent_q",10,1,1,2,2,0},{"independent_c",10,0,1,2,2,0},
 {"shared_counterexample",10,1,1,2,2,1},
 {"migration_guard",11,1,1,1,1,0},{"migration_counterexample",11,1,1,1,2,1}
};
static const struct definition baseline_cases[]={
 {"baseline_third",3,1,1,2,1,0},{"baseline_control",3,0,1,2,1,0}
};
struct event {
 uint32_t magic,version,length,kind,slot,other,op;
 int32_t pid,ppid,uid,euid,gid,egid,count,read,predicate,error,aux,fd3_errno,fd4_errno,canary_error,canary_allowed;
 int64_t rc;
 uint64_t group,current,maximum;
};
_Static_assert(sizeof(struct event)<=PIPE_BUF,"atomic event exceeds PIPE_BUF");
static const char lease_root[]="/private/var/icode-m0a1-leases";
static const char owner_text[]="ICODE-M0A1-v1\n";
static unsigned char unavailable[UID_COUNT];
static char image[PATH_MAX],directory[PATH_MAX],binary_hash[65],sandbox_hash[65];
static const char *candidate;
static int canary_errno=-1,canary_allowed;
static volatile sig_atomic_t owned[2];
static void expire(int sig) {
 (void)sig;
 for(unsigned i=0;i<2;i++) if(owned[i]>0) (void)kill((pid_t)owned[i],SIGKILL);
 _exit(124);
}
static void die(const char *stage) {
 int e=errno ? errno : EPROTO;
 fprintf(stderr,"M0A2 stage=%s errno=%d retained=%s cleanup=unknown\n",stage,e,directory);
 for(unsigned i=0;i<2;i++) if(owned[i]>0) (void)kill((pid_t)owned[i],SIGKILL);
 exit(2);
}
#include "icode_m0a1_fixed_helpers.inc"
#include "icode_m0a1_identity_lease.inc"
#include "icode_m0a1_unused_identity.inc"
static uint64_t experiment_deadline;
static uint64_t monotonic_ns(void) {
 struct timespec value;
 if(clock_gettime(CLOCK_MONOTONIC,&value)<0) die("monotonic-clock");
 if(value.tv_sec<0 || value.tv_nsec<0 || value.tv_nsec>=1000000000L ||
    (uint64_t)value.tv_sec>(UINT64_MAX-(uint64_t)value.tv_nsec)/1000000000ULL)
  die("monotonic-range");
 return (uint64_t)value.tv_sec*1000000000ULL+(uint64_t)value.tv_nsec;
}
static void parse_deadline(const char *text) {
 if(!hex_string(text,16)) die("deadline-hex16");
 char *end=NULL;errno=0;unsigned long long value=strtoull(text,&end,16);
 if(errno || end==text || *end || value>UINT64_MAX) die("deadline-overflow");
 uint64_t now=monotonic_ns();
 if((uint64_t)value<=now || (uint64_t)value-now>480000000000ULL) die("deadline-window");
 experiment_deadline=(uint64_t)value;
}
static unsigned remaining_seconds(void) {
 uint64_t now=monotonic_ns();
 if(now>=experiment_deadline || experiment_deadline-now<1000000000ULL) die("deadline-expired");
 return (unsigned)((experiment_deadline-now)/1000000000ULL);
}
static struct definition definition_at(int index) {
 if(!strcmp(m0_variant(),"baseline")) {
  if(index<0 || index>=2) die("baseline-index");
  return baseline_cases[index];
 }
 if(index<0 || index>=24) die("source-index");
 return source_cases[index];
}
static void sample(struct event *e,unsigned kind,unsigned slot,unsigned other,
                   unsigned op,int64_t rc,int error,int aux) {
 memset(e,0,sizeof(*e));
 e->magic=VMAGIC;e->version=1;e->length=sizeof(*e);e->kind=kind;e->slot=slot;
 e->other=other;e->op=op;e->rc=rc;e->error=error;e->aux=aux;
 e->pid=getpid();e->ppid=getppid();e->uid=getuid();e->euid=geteuid();
 e->gid=getgid();e->egid=getegid();gid_t g=UINT32_MAX;
 e->count=m0_process_getgroups(0,NULL);e->read=m0_process_getgroups(1,&g);e->group=g;
 e->predicate=m0_process_credentials((uid_t)e->uid);
 e->canary_error=canary_errno;e->canary_allowed=canary_allowed;
 errno=0;e->fd3_errno=fcntl(3,F_GETFD)<0 ? errno : 0;
 errno=0;e->fd4_errno=fcntl(4,F_GETFD)<0 ? errno : 0;
 struct rlimit actual;
 if(getrlimit(RLIMIT_NPROC,&actual)<0) _exit(80);
 e->current=actual.rlim_cur;e->maximum=actual.rlim_max;
}
static char send_event(unsigned kind,unsigned slot,unsigned other,unsigned op,
                       int64_t rc,int error,int aux) {
 struct event e;sample(&e,kind,slot,other,op,rc,error,aux);
 /* One bounded write: shared data writers cannot interleave a record. */
 ssize_t n;
 do { n=write(5,&e,sizeof(e)); } while(n<0 && errno==EINTR);
 char response=0;
 if(n!=(ssize_t)sizeof(e) || all_read(20+(int)slot,&response,1)) _exit(81);
 return response;
}
static void require_ack(char actual,char expected) { if(actual!=expected) _exit(82); }
static void status_event(unsigned kind,unsigned slot,int error) {
 struct event e;sample(&e,kind,slot,0,0,0,error,canary_errno);
 if(all_write(3,&e,sizeof(e))) _exit(83);
}
static void wait_child(pid_t child,unsigned slot,unsigned child_slot) {
 int status=0;pid_t result;
 do { result=waitpid(child,&status,0); } while(result<0 && errno==EINTR);
 if(result!=child || !WIFEXITED(status) || WEXITSTATUS(status)) _exit(84);
 require_ack(send_event(REAPED,slot,child_slot,0,child,0,status),'A');
}
static pid_t launch_child(int index,unsigned slot,unsigned child_slot,int spawning) {
 int marker[2];
 int reserved=open("/dev/null",O_RDWR|O_CLOEXEC);
 if(reserved<0 || (reserved!=8 && dup2(reserved,8)<0)) _exit(85);
 if(reserved!=8 && close(reserved)<0) _exit(85);
 if(fcntl(8,F_SETFD,FD_CLOEXEC)<0 || pipe(marker)<0 ||
    fcntl(marker[0],F_SETFD,FD_CLOEXEC)<0 || fcntl(marker[1],F_SETFD,FD_CLOEXEC)<0) _exit(85);
 char idx[16],target[16],parent[16];
 snprintf(idx,sizeof(idx),"%d",index);snprintf(target,sizeof(target),"%u",child_slot);
 snprintf(parent,sizeof(parent),"%u",slot);
 char *args[]={image,spawning ? "S" : "L",idx,target,parent,binary_hash,NULL};
 char *env[]={"PATH=/usr/bin:/bin",NULL};
 pid_t child=-1;int error=0,spawn_rc=0;
 if(spawning) {
  posix_spawn_file_actions_t actions;
  if(posix_spawn_file_actions_init(&actions)) _exit(86);
  /* Descriptor 8 is reserved explicitly before creating the marker pipe. */
  if(posix_spawn_file_actions_adddup2(&actions,marker[1],8) ||
     posix_spawn_file_actions_addclose(&actions,marker[0])) _exit(87);
  spawn_rc=posix_spawn(&child,image,&actions,NULL,args,env);
  if(posix_spawn_file_actions_destroy(&actions)) _exit(88);
  if(spawn_rc) { error=spawn_rc;child=-1; }
 } else {
  errno=0;child=fork();error=child<0 ? errno : 0;
  if(child==0) {
   if(write(marker[1],"C",1)!=1) _exit(89);
   alarm(10);
   char go=0;
   if(all_read(20+(int)child_slot,&go,1) || go!='C') _exit(90);
   if(close(marker[0])<0 || close(marker[1])<0) _exit(91);
   for(int fd=0;fd<65536;fd++)
    if(fd!=2 && fd!=5 && fd!=20+(int)child_slot && close(fd)<0 && errno!=EBADF) _exit(92);
   execve(image,args,env);_exit(93);
  }
 }
 if(close(marker[1])<0) _exit(94);
 char byte=0;ssize_t n;
 do { n=read(marker[0],&byte,1); } while(n<0 && errno==EINTR);
 if(close(marker[0])<0 || n<0 || (n==1 && byte!='C') ||
    (child>0 && n!=1) || (child<0 && n!=0)) _exit(95);
 require_ack(send_event(child>0 ? FORKED : OP,slot,child_slot,
             spawning ? SPAWN_OP : FORK_OP,child,error,(int)n),'A');
 return child;
}
static pthread_mutex_t thread_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t thread_cond=PTHREAD_COND_INITIALIZER;
static unsigned thread_arrived,thread_release;
static void *thread_worker(void *unused) {
 (void)unused;
 if(pthread_mutex_lock(&thread_lock)) _exit(96);
 thread_arrived++;
 if(pthread_cond_broadcast(&thread_cond)) _exit(97);
 while(!thread_release) if(pthread_cond_wait(&thread_cond,&thread_lock)) _exit(98);
 if(pthread_mutex_unlock(&thread_lock)) _exit(99);
 return NULL;
}
static void thread_wave(unsigned count,unsigned total,unsigned slot) {
 pthread_t workers[3];
 if(count>3 || pthread_mutex_lock(&thread_lock)) _exit(100);
 thread_arrived=thread_release=0;
 if(pthread_mutex_unlock(&thread_lock)) _exit(101);
 for(unsigned i=0;i<count;i++) if(pthread_create(&workers[i],NULL,thread_worker,NULL)) _exit(102);
 if(pthread_mutex_lock(&thread_lock)) _exit(103);
 while(thread_arrived!=count) if(pthread_cond_wait(&thread_cond,&thread_lock)) _exit(104);
 require_ack(send_event(THREADS,slot,total,0,count+1,0,(int)count),'A');
 thread_release=1;
 if(pthread_cond_broadcast(&thread_cond) || pthread_mutex_unlock(&thread_lock)) _exit(105);
 for(unsigned i=0;i<count;i++) if(pthread_join(workers[i],NULL)) _exit(106);
}
static void finished(unsigned slot,pid_t *children,unsigned *slots,unsigned count) {
 require_ack(send_event(FINISH,slot,0,0,count,0,0),'A');
 for(unsigned i=0;i<count;i++) if(children[i]>0) wait_child(children[i],slot,slots[i]);
 require_ack(send_event(DONE,slot,0,0,0,0,0),'A');
 _exit(0);
}
static void leaf(int index,unsigned slot,unsigned parent_slot) {
 struct definition c=definition_at(index);
 if(protected_image(binary_hash) || m0_process_credentials(getuid()) || canaries(c.profile)) _exit(107);
 char answer=send_event(START,slot,parent_slot,0,0,0,canary_errno);
 if(c.vector==5 && slot==2) {
  require_ack(answer,'A');
  pid_t children[1]={launch_child(index,slot,4,0)};unsigned slots[1]={4};
  finished(slot,children,slots,children[0]>0 ? 1 : 0);
 }
 if(answer!='X') {
  require_ack(answer,'H');char finish=0;
  if(all_read(20+(int)slot,&finish,1) || finish!='X') _exit(108);
 }
 _exit(0);
}
static void limit_change(unsigned slot,unsigned op,rlim_t current,rlim_t maximum) {
 struct rlimit desired={current,maximum};errno=0;
 int rc=setrlimit(RLIMIT_NPROC,&desired);int error=rc<0 ? errno : 0;
 require_ack(send_event(OP,slot,0,op,rc,error,0),'A');
}
static void payload(int index,unsigned slot) {
 struct definition c=definition_at(index);
 if(protected_image(binary_hash) || m0_process_credentials(getuid()) || canaries(c.profile)) _exit(109);
 require_ack(send_event(START,slot,0,0,0,0,canary_errno),'A');
 pid_t children[3]={0};unsigned slots[3]={0};unsigned count=0;
 if(c.vector==11) finished(slot,children,slots,0);
 if(c.vector==6) { thread_wave(3,3,slot);thread_wave(1,4,slot); }
 if(c.vector==8 && c.quota) {
  limit_change(slot,LOWER,1,2);
  pid_t unexpected=launch_child(index,slot,2,0);
  if(unexpected>0) { children[count]=unexpected;slots[count++]=2; }
  limit_change(slot,RESTORE,2,2);
 } else if(c.vector==9 && c.quota) limit_change(slot,RAISE,3,3);
 unsigned first=c.vector==8 && c.quota ? 4 : slot==0 ? 2 : 3;
 if(c.vector==1 || c.vector==2 || c.vector==6 || c.vector==8 || c.vector==9 ||
    (c.vector==10 && c.shared)) {
  pid_t p=launch_child(index,slot,first,c.vector==2);
  if(p>0) { children[count]=p;slots[count++]=first; }
 } else {
  pid_t first_pid=launch_child(index,slot,first,0);
  if(first_pid<=0) _exit(110);
  if(c.vector==4) {
   wait_child(first_pid,slot,first);
   unsigned next=slot==0 ? 4 : 5;
   pid_t p=launch_child(index,slot,next,0);
   if(p<=0) _exit(111);
   wait_child(p,slot,next);
  } else if(c.vector==7) {
   siginfo_t information;memset(&information,0,sizeof(information));errno=0;
   int rc=waitid(P_PID,(id_t)first_pid,&information,WEXITED|WNOWAIT);
   int error=rc<0 ? errno : 0;
   require_ack(send_event(ZOMBIE,slot,first,0,rc,error,information.si_pid),'A');
   unsigned next=4;
   pid_t p=launch_child(index,slot,next,0);
   if(p>0) { children[count]=p;slots[count++]=next; }
   wait_child(first_pid,slot,first);
   p=launch_child(index,slot,6,0);
   if(p<=0) _exit(112);
   children[count]=p;slots[count++]=6;
  } else {
   children[count]=first_pid;slots[count++]=first;
   if(c.vector==3 || c.vector==10) {
    unsigned next=slot==0 ? 4 : 5;
    pid_t p=launch_child(index,slot,next,0);
    if(p>0) { children[count]=p;slots[count++]=next; }
   }
  }
 }
 finished(slot,children,slots,count);
}
static void worker(int index,unsigned slot,uid_t uid,int gate_stage) {
 struct definition c=definition_at(index);
 if(protected_image(binary_hash)) _exit(113);
 if(!gate_stage) {
  struct rlimit cpu={2,2},files={65536,65536},actual;
  if(setrlimit(RLIMIT_CPU,&cpu)<0 || setrlimit(RLIMIT_FSIZE,&files)<0 ||
     getrlimit(RLIMIT_CPU,&actual)<0 || actual.rlim_cur!=2 || actual.rlim_max!=2 ||
     getrlimit(RLIMIT_FSIZE,&actual)<0 || actual.rlim_cur!=65536 || actual.rlim_max!=65536) _exit(114);
  gid_t gid=(gid_t)uid;
  if(m0_apply_limit((rlim_t)c.cap,c.quota) || setgroups(1,&gid)<0 ||
     setgid(gid)<0 || setuid(uid)<0 || m0_process_credentials(uid) ||
     m0_check_limit((rlim_t)c.cap,c.quota)) _exit(115);
  status_event(CONFIG,slot,0);
  char idx[16],position[16],identity[16],profile[PATH_MAX];
  snprintf(idx,sizeof(idx),"%d",index);snprintf(position,sizeof(position),"%u",slot);
  snprintf(identity,sizeof(identity),"%u",uid);
  char *env[]={"PATH=/usr/bin:/bin",NULL};
  char *args[]={image,"G",idx,position,identity,binary_hash,NULL};
  if(!c.profile) { execve(image,args,env);_exit(116); }
  if(snprintf(profile,sizeof(profile),"%s/profile.sb",directory)>=(int)sizeof(profile)) _exit(117);
  char *sandbox_args[]={"/usr/bin/sandbox-exec","-f",profile,image,"G",idx,position,identity,binary_hash,NULL};
  execve("/usr/bin/sandbox-exec",sandbox_args,env);_exit(118);
 }
 if(m0_process_credentials(uid) || m0_check_limit((rlim_t)c.cap,c.quota) || canaries(c.profile)) _exit(119);
 status_event(READY,slot,0);
 char release=0;
 if(all_read(4,&release,1) || release!='R' || close(4)<0 ||
    fcntl(3,F_SETFD,FD_CLOEXEC)<0) _exit(120);
 char idx[16],position[16],identity[16];
 snprintf(idx,sizeof(idx),"%d",index);snprintf(position,sizeof(position),"%u",slot);
 snprintf(identity,sizeof(identity),"%u",uid);
 char *args[]={image,"P",idx,position,identity,binary_hash,NULL};
 char *env[]={"PATH=/usr/bin:/bin",NULL};
 execve(image,args,env);_exit(121);
}
static int enter_attempt(unsigned *consumed) {
 if(*consumed) return EPERM;
 *consumed=1;return 0;
}
static int packet_valid(const struct event *e) {
 return e->magic==VMAGIC && e->version==1 && e->length==sizeof(*e) && e->slot<8;
}
struct member { pid_t pid;uint64_t sec,usec;uid_t uid;int parent,started,held,finished,reaped,completed; };
static void identify(struct member *m,pid_t pid,uid_t uid,int parent) {
 struct proc_bsdinfo b;
 if(proc_pidinfo(pid,PROC_PIDTBSDINFO,0,&b,sizeof(b))!=(int)sizeof(b) ||
    b.pbi_pid!=(uint32_t)pid) die("register-member-PID-start");
 *m=(struct member){.pid=pid,.sec=b.pbi_start_tvsec,.usec=b.pbi_start_tvusec,.uid=uid,.parent=parent};
}
static void acknowledgement(int ack[8][2],unsigned slot,char value) {
 if(slot>=8 || all_write(ack[slot][1],&value,1)) die("member-ack");
}
static void ledger_row(int fd,const char *row,int n) {
 if(n<=0 || n>=4096 || all_write(fd,row,(size_t)n) || fsync(fd)<0) die("bounded-ledger-row");
}
static void record_event(int ledger,const struct event *e,struct member members[8],
                         const struct definition *c,unsigned case_index) {
 struct member *m=&members[e->slot];struct proc_bsdinfo b;
 if(m->pid!=e->pid || proc_pidinfo(e->pid,PROC_PIDTBSDINFO,0,&b,sizeof(b))!=(int)sizeof(b) ||
    b.pbi_pid!=(uint32_t)e->pid || b.pbi_start_tvsec!=m->sec || b.pbi_start_tvusec!=m->usec ||
    b.pbi_ppid!=(uint32_t)m->parent) die("event-live-PID-start-parent");
 int credential=c->vector==12 ? b.pbi_ruid==0 && b.pbi_uid==0 && b.pbi_svuid==0 :
    b.pbi_ruid==m->uid && b.pbi_uid==m->uid && b.pbi_svuid==m->uid &&
    b.pbi_rgid==m->uid && b.pbi_gid==m->uid && b.pbi_svgid==m->uid;
 int count=c->vector==12 ? -1 : process_count(m->uid);
 if(!credential || (c->vector!=12 && (count<0 || count>8 || e->uid!=(int32_t)m->uid ||
    e->euid!=(int32_t)m->uid || e->gid!=(int32_t)m->uid || e->egid!=(int32_t)m->uid ||
    e->count!=1 || e->read!=1 || e->group!=m->uid || e->predicate))) die("independent-credential-snapshot");
 if(c->vector!=12 && (e->kind==CONFIG || e->kind==READY) &&
    count!=(c->shared ? (int)e->slot+1 : 1)) die("pre-release-UID-count");
 if(c->vector!=12 && e->kind==START && e->slot<(unsigned)c->roots &&
    count!=(c->shared ? c->roots : 1)) die("initial-UID-count");
 int threads=-1,zombie=-1;
 if(e->kind==THREADS) {
  struct proc_taskinfo task;
  if(proc_pidinfo(e->pid,PROC_PIDTASKINFO,0,&task,sizeof(task))!=(int)sizeof(task)) die("thread-snapshot");
  threads=task.pti_threadnum;
  if(threads<1 || threads>4) die("thread-budget");
 }
 if(e->kind==ZOMBIE) {
  if(e->other>=8 || !members[e->other].pid || e->aux!=members[e->other].pid) die("zombie-owned-PID");
  struct member *z=&members[e->other];struct kinfo_proc info;memset(&info,0,sizeof(info));
  size_t size=sizeof(info);int mib[]={CTL_KERN,KERN_PROC,KERN_PROC_PID,z->pid};
  if(sysctl(mib,4,&info,&size,NULL,0)<0 || size!=sizeof(info) ||
     info.kp_proc.p_pid!=z->pid || info.kp_proc.p_starttime.tv_sec!=(time_t)z->sec ||
     info.kp_proc.p_starttime.tv_usec!=(suseconds_t)z->usec) die("zombie-start-snapshot");
  zombie=info.kp_proc.p_stat;
 }
 char row[4096];
 int n=snprintf(row,sizeof(row),
  "{\"kind\":\"event\",\"version\":1,\"case_index\":%u,\"event\":%u,\"slot\":%u,\"other\":%u,"
  "\"op\":%u,\"pid\":%d,\"ppid\":%d,\"start_sec\":%" PRIu64 ",\"start_usec\":%" PRIu64 ","
  "\"uid\":%d,\"euid\":%d,\"gid\":%d,\"egid\":%d,\"saved_uid\":%u,\"saved_gid\":%u,"
  "\"count\":%d,\"read\":%d,\"group\":%" PRIu64 ",\"predicate\":%d,"
  "\"current\":%" PRIu64 ",\"maximum\":%" PRIu64 ",\"rc\":%" PRId64 ",\"error\":%d,\"aux\":%d,"
  "\"independent_credentials\":%d,\"live_count\":%d,\"threads\":%d,\"zombie_state\":%d,\"fd3_errno\":%d,\"fd4_errno\":%d,\"canary_error\":%d,\"canary_allowed\":%d}\n",
  case_index,e->kind,e->slot,e->other,e->op,e->pid,e->ppid,m->sec,m->usec,
  e->uid,e->euid,e->gid,e->egid,b.pbi_svuid,b.pbi_svgid,e->count,e->read,e->group,e->predicate,
  e->current,e->maximum,e->rc,e->error,e->aux,credential,count,threads,zombie,e->fd3_errno,e->fd4_errno,e->canary_error,e->canary_allowed);
 ledger_row(ledger,row,n);
}
static int register_exec(pid_t pid) {
 int kq=kqueue();struct kevent change,receipt;struct timespec zero={0,0};
 EV_SET(&change,pid,EVFILT_PROC,EV_ADD|EV_ENABLE|EV_CLEAR|EV_RECEIPT,NOTE_EXEC|NOTE_EXIT,0,NULL);
 if(kq<0 || kevent(kq,&change,1,&receipt,1,&zero)!=1 ||
    !(receipt.flags&EV_ERROR) || receipt.data!=0) die("new-exec-registration");
 return kq;
}
static void see_exec(int kq,pid_t pid) {
 struct kevent e;struct timespec timeout={1,0};int n;
 do { n=kevent(kq,NULL,0,&e,1,&timeout); } while(n<0 && errno==EINTR);
 if(n!=1 || (e.flags&EV_ERROR) || e.ident!=(uintptr_t)pid || !(e.fflags&NOTE_EXEC)) die("actual-payload-exec");
}
static int wait_root(unsigned slot,pid_t pid,int *status) {
 sigset_t mask,old;sigemptyset(&mask);sigaddset(&mask,SIGALRM);
 for(unsigned attempt=0;attempt<100;attempt++) {
  if(sigprocmask(SIG_BLOCK,&mask,&old)<0) return -1;
  pid_t result=waitpid(pid,status,WNOHANG);int saved=errno;
  if(result==pid || (result<0 && saved==ECHILD)) owned[slot]=0;
  if(sigprocmask(SIG_SETMASK,&old,NULL)<0) return -1;
  if(result==pid) return 0;
  if(result<0 && saved!=EINTR) { errno=saved;return -1; }
  (void)usleep(10000);
 }
 errno=ETIMEDOUT;return -1;
}
static void root_child(int index,unsigned slot,uid_t uid,int status[2],int release[2],
                       int data[2],int ack[8][2]) {
 owned[0]=owned[1]=0;alarm(10);
 if(dup2(status[1],3)<0 || dup2(release[0],4)<0 || dup2(data[1],5)<0) _exit(122);
 for(unsigned i=0;i<8;i++) if(dup2(ack[i][0],20+(int)i)<0) _exit(123);
 for(int fd=6;fd<65536;fd++)
  if((fd<20 || fd>27) && close(fd)<0 && errno!=EBADF) _exit(124);
 int null=open("/dev/null",O_RDWR);
 if(null<0 || dup2(null,0)<0 || dup2(null,1)<0) _exit(125);
 if(null>5 && close(null)<0) _exit(126);
 for(int sig=1;sig<NSIG;sig++) if(sig!=SIGKILL && sig!=SIGSTOP &&
    signal(sig,SIG_DFL)==SIG_ERR) _exit(127);
 sigset_t empty;sigemptyset(&empty);
 if(sigprocmask(SIG_SETMASK,&empty,NULL)<0) _exit(128);
 alarm(10);char start=0;
 if(all_read(4,&start,1) || start!='A') _exit(129);
 char idx[16],position[16],identity[16];
 snprintf(idx,sizeof(idx),"%d",index);snprintf(position,sizeof(position),"%u",slot);
 snprintf(identity,sizeof(identity),"%u",uid);
 struct definition c=definition_at(index);
 char *args[]={image,c.vector==12 ? "R" : "T",idx,position,identity,binary_hash,NULL};
 char *env[]={"PATH=/usr/bin:/bin",NULL};
 execve(image,args,env);_exit(130);
}
static void run_case(int index,int ledger,int leases,const char *os,const char *kernel,const char *arch) {
 struct definition c=definition_at(index);
 uid_t ids[2]={0,0};
 if(c.vector!=12) {
  ids[0]=reserve_unused_id(leases);
  if(c.roots==2) ids[1]=c.shared ? ids[0] : reserve_unused_id(leases);
 }
 int data[2],ack[8][2],status[2][2],release[2][2],kq[2]={-1,-1};
 if(pipe(data)<0) die("data-pipe");
 for(unsigned i=0;i<8;i++) if(pipe(ack[i])<0) die("ack-pipe");
 struct member members[8];memset(members,0,sizeof(members));
 char profile_path[PATH_MAX],profile_hash[65];
 if(snprintf(profile_path,sizeof(profile_path),"%s/profile.sb",directory)>=(int)sizeof(profile_path)) die("profile-path");
 int pf=open(profile_path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
 if(pf<0 || hash_fd(pf,profile_hash,4096) || close(pf)<0) die("profile-digest");
 struct proc_bsdinfo observer;
 if(proc_pidinfo(getpid(),PROC_PIDTBSDINFO,0,&observer,sizeof(observer))!=(int)sizeof(observer) ||
    observer.pbi_pid!=(uint32_t)getpid() || observer.pbi_ruid!=0 || observer.pbi_uid!=0 ||
    observer.pbi_svuid!=0) die("observer-PID-start");
 char row[4096];
 int n=snprintf(row,sizeof(row),
  "{\"kind\":\"begin\",\"version\":1,\"candidate_sha\":\"%s\",\"variant\":\"%s\","
  "\"binary_sha256\":\"%s\",\"profile_sha256\":\"%s\",\"sandbox_exec_sha256\":\"%s\","
  "\"case_index\":%d,\"case\":\"%s\",\"vector\":%d,\"quota\":%d,\"profile\":%d,\"cap\":%d,"
  "\"roots\":%d,\"shared\":%d,\"uid0\":%u,\"uid1\":%u,\"observer_pid\":%d,\"observer_uid\":%u,"
  "\"observer_start_sec\":%" PRIu64 ",\"observer_start_usec\":%" PRIu64 ",\"deadline_ns\":%" PRIu64 ","
  "\"arch\":\"%s\",\"os_build\":\"%s\",\"kernel\":\"%s\"}\n",
  candidate,m0_variant(),binary_hash,profile_hash,sandbox_hash,index,c.name,c.vector,c.quota,c.profile,
  c.cap,c.roots,c.shared,ids[0],ids[1],getpid(),getuid(),observer.pbi_start_tvsec,
  observer.pbi_start_tvusec,experiment_deadline,arch,os,kernel);
 ledger_row(ledger,row,n);
 unsigned consumed=0;
 for(unsigned root=0;root<(unsigned)c.roots;root++) {
  if(c.vector==11 && (root==0 || !c.shared) && enter_attempt(&consumed)) die("first-attempt-rejected");
  if(pipe(status[root])<0 || pipe(release[root])<0) die("root-pipes");
  pid_t pid=fork();
  if(pid<0) die("root-fork");
  if(pid==0) root_child(index,root,ids[root],status[root],release[root],data,ack);
  owned[root]=pid;identify(&members[root],pid,ids[root],getpid());
  close(status[root][1]);close(release[root][0]);
  if(c.vector==12) kq[root]=register_exec(pid);
  if(all_write(release[root][1],"A",1)) die("initial-A");
  if(c.vector==12) { close(status[root][0]);close(release[root][1]);continue; }
  struct event configured,ready;
  if(read_record(status[root][0],&configured,sizeof(configured)) ||
     read_record(status[root][0],&ready,sizeof(ready)) ||
     !packet_valid(&configured) || !packet_valid(&ready) ||
     configured.kind!=CONFIG || ready.kind!=READY || configured.slot!=root || ready.slot!=root ||
     configured.pid!=pid || ready.pid!=pid || configured.error || ready.error ||
     configured.uid!=(int32_t)ids[root] || ready.uid!=(int32_t)ids[root] ||
     configured.predicate || ready.predicate || configured.count!=1 || configured.read!=1 ||
     ready.count!=1 || ready.read!=1 || ready.group!=ids[root] || configured.group!=ids[root])
   die("configured-ready-contract");
  if(c.quota && strcmp(m0_variant(),"baseline") &&
     (configured.current!=(uint64_t)c.cap || configured.maximum!=(uint64_t)c.cap ||
      ready.current!=(uint64_t)c.cap || ready.maximum!=(uint64_t)c.cap)) die("exact-limits-before-release");
  record_event(ledger,&configured,members,&c,(unsigned)index);
  record_event(ledger,&ready,members,&c,(unsigned)index);
  kq[root]=register_exec(pid); /* Fresh after READY: cannot credit T/G exec. */
  if(all_write(release[root][1],"R",1) || close(release[root][1])<0) die("release-R");
  if(close(status[root][0])<0) die("status-reader-close");
 }
 if(c.vector==11 && !c.shared) {
  int error=enter_attempt(&consumed);
  if(error!=EPERM) die("replay-admission-was-not-rejected");
  n=snprintf(row,sizeof(row),"{\"kind\":\"admission\",\"version\":1,\"case_index\":%d,\"observer_uid\":%u,\"consumed\":%u,\"error\":%d,\"second_forked\":0}\n",index,getuid(),consumed,error);
  ledger_row(ledger,row,n);
 }
 close(data[1]);for(unsigned i=0;i<8;i++) close(ack[i][0]);
 unsigned root_started=0,finished_count=0,done=0;
 int all_finished=0;unsigned event_count=0;
 while(done<(unsigned)c.roots) {
  struct event e;
  if(++event_count>64 || read_record(data[0],&e,sizeof(e)) || !packet_valid(&e) ||
     e.kind<START || e.kind>DONE || !members[e.slot].pid) die("data-event-contract");
  record_event(ledger,&e,members,&c,(unsigned)index);
  if(e.kind==FORKED) {
   if(e.other>=8 || members[e.other].pid || e.rc<=0 || e.rc>INT_MAX || e.error || e.aux!=1) die("fork-registration");
   identify(&members[e.other],(pid_t)e.rc,members[e.slot].uid,e.pid);
   acknowledgement(ack,e.other,'C');acknowledgement(ack,e.slot,'A');
  } else if(e.kind==START) {
   if(members[e.slot].started) die("duplicate-start");
   members[e.slot].started=1;
   if(e.slot<(unsigned)c.roots) {
    see_exec(kq[e.slot],e.pid);root_started++;
    if(root_started==(unsigned)c.roots)
     for(unsigned root=0;root<(unsigned)c.roots;root++) acknowledgement(ack,root,'A');
   } else {
    int immediate=c.vector==4 || (c.vector==7 && e.slot==2) || all_finished;
    int grandparent=c.vector==5 && e.slot==2;
    acknowledgement(ack,e.slot,immediate ? 'X' : grandparent ? 'A' : 'H');
    members[e.slot].held=!immediate && !grandparent;
   }
  } else if(e.kind==FINISH) {
   if(members[e.slot].finished) die("duplicate-finish");
   members[e.slot].finished=1;finished_count++;
   unsigned required=(unsigned)c.roots+(c.vector==5 ? 1u : 0u);
   if(finished_count==required) {
    all_finished=1;
    for(unsigned i=0;i<8;i++) if(members[i].held) {
     acknowledgement(ack,i,'X');members[i].held=0;
    }
    for(unsigned i=0;i<8;i++) if(members[i].finished) acknowledgement(ack,i,'A');
   }
  } else if(e.kind==DONE) {
   if(!all_finished || !members[e.slot].finished || members[e.slot].completed) die("premature-done");
   members[e.slot].completed=1;
   if(e.slot<(unsigned)c.roots) done++;
   acknowledgement(ack,e.slot,'A');
  } else {
   if(e.kind==REAPED) {
    if(e.other>=8 || members[e.other].pid!=e.rc || members[e.other].parent!=e.pid ||
       members[e.other].reaped || e.error || e.aux) die("owned-reap-contract");
    members[e.other].reaped=1;
   }
   acknowledgement(ack,e.slot,'A');
  }
 }
 for(unsigned root=0;root<(unsigned)c.roots;root++) {
  int wait_status=0;
  if(wait_root(root,members[root].pid,&wait_status)<0 || !WIFEXITED(wait_status) ||
     WEXITSTATUS(wait_status)) die("owned-root-wait");
  members[root].reaped=1;
  if(close(kq[root])<0) die("kqueue-close");
 }
 for(unsigned i=0;i<8;i++) if(members[i].pid && !members[i].reaped) die("unreaped-member");
 if(c.vector!=12 && (process_count(ids[0])!=0 || supplementary_free(ids[0])!=1 ||
    (c.roots==2 && (process_count(ids[1])!=0 || supplementary_free(ids[1])!=1)))) die("retained-identity-unknown");
 char extra=0;
 if(read(data[0],&extra,1)!=0 || close(data[0])<0) die("data-tail");
 for(unsigned i=0;i<8;i++) if(close(ack[i][1])<0) die("ack-close");
 n=snprintf(row,sizeof(row),
  "{\"kind\":\"end\",\"version\":1,\"case_index\":%d,\"events\":%u,\"roots_reaped\":%d,"
  "\"remaining\":0,\"cleanup_scope\":\"owned_roots_and_observed_direct_parent_reaps\",\"retained\":true}\n",
  index,event_count+(c.vector==12 ? 0u : 2u*(unsigned)c.roots),c.roots);
 ledger_row(ledger,row,n);
}
static void root_calibration(unsigned slot) {
 if(protected_image(binary_hash) || getuid()!=0 || geteuid()!=0) _exit(131);
 struct rlimit cpu={2,2},files={65536,65536},actual;
 if(setrlimit(RLIMIT_CPU,&cpu)<0 || setrlimit(RLIMIT_FSIZE,&files)<0 ||
    getrlimit(RLIMIT_CPU,&actual)<0 || actual.rlim_cur!=2 || actual.rlim_max!=2 ||
    getrlimit(RLIMIT_FSIZE,&actual)<0 || actual.rlim_cur!=65536 || actual.rlim_max!=65536) _exit(132);
 require_ack(send_event(START,slot,0,0,0,0,0),'A');
 limit_change(slot,CALIBRATE,3,3);
 pid_t none[1]={0};unsigned slots[1]={0};finished(slot,none,slots,0);
}
int main(int argc,char **argv) {
 if(argc==6 && !strcmp(argv[1],"S")) {
  if(write(8,"C",1)!=1) _exit(137);
  alarm(10);
 }
 self_path();
 if(argc==6 && (!strcmp(argv[1],"T") || !strcmp(argv[1],"G") || !strcmp(argv[1],"P") || !strcmp(argv[1],"R"))) {
  int index=numeric(argv[2],0,!strcmp(m0_variant(),"baseline") ? 1 : 23);
  unsigned slot=(unsigned)numeric(argv[3],0,1);
  uid_t uid=(uid_t)numeric(argv[4],0,UID_FIRST+UID_COUNT-1);
  if(!hex_string(argv[5],64)) _exit(133);
  strcpy(binary_hash,argv[5]);struct definition c=definition_at(index);
  if(c.vector==12) {
   if(strcmp(argv[1],"R") || uid!=0) _exit(134);
   root_calibration(slot);
  }
  if(uid<UID_FIRST) _exit(135);
  if(!strcmp(argv[1],"T")) worker(index,slot,uid,0);
  if(!strcmp(argv[1],"G")) worker(index,slot,uid,1);
  if(strcmp(argv[1],"P") || getuid()!=uid) _exit(136);
  payload(index,slot);return 2;
 }
 if(argc==6 && (!strcmp(argv[1],"L") || !strcmp(argv[1],"S"))) {
  /* Spawn's first external action is the byte; fork already wrote it before exec. */
  /* Marker already written before self_path above. */
  int index=numeric(argv[2],0,!strcmp(m0_variant(),"baseline") ? 1 : 23);
  unsigned slot=(unsigned)numeric(argv[3],2,7),parent=(unsigned)numeric(argv[4],0,7);
  if(!hex_string(argv[5],64)) _exit(138);
  strcpy(binary_hash,argv[5]);
  if(argv[1][0]=='S') {
   alarm(10);char go=0;
   if(all_read(20+(int)slot,&go,1) || go!='C' || close(8)<0) _exit(139);
  }
  for(int fd=0;fd<65536;fd++)
   if(fd!=2 && fd!=5 && fd!=20+(int)slot && close(fd)<0 && errno!=EBADF) _exit(140);
  leaf(index,slot,parent);return 2;
 }
 if(argc!=4 || getuid()!=0 || geteuid()!=0 || !hex_string(argv[1],40) || !hex_string(argv[2],64)) die("root-fixed-arguments");
 candidate=argv[1];parse_deadline(argv[3]);umask(077);
 if(signal(SIGALRM,expire)==SIG_ERR || signal(SIGPIPE,SIG_IGN)==SIG_ERR) die("root-signals");
 alarm(remaining_seconds());
 struct rlimit cpu={20,20},actual;
 if(setrlimit(RLIMIT_CPU,&cpu)<0 || getrlimit(RLIMIT_CPU,&actual)<0 ||
    actual.rlim_cur!=20 || actual.rlim_max!=20) die("observer-cpu20-readback");
 for(int fd=3;fd<32;fd++) if(open("/dev/null",O_RDWR|O_CLOEXEC)!=fd) die("reserved-FD-layout");
 struct utsname u;char os[64];size_t os_size=sizeof(os);
 if(uname(&u)<0 || sysctlbyname("kern.osversion",os,&os_size,NULL,0)<0 ||
    os_size<2 || os_size>sizeof(os) || os[os_size-1]!=0 ||
    (strcmp(u.machine,"arm64") && strcmp(u.machine,"x86_64"))) die("native-OS");
 for(const char *s=os;*s;s++) if(!((*s>='0' && *s<='9') || (*s>='A' && *s<='Z') ||
    (*s>='a' && *s<='z'))) die("OS-build-format");
 for(const char *s=u.release;*s;s++) if(!((*s>='0' && *s<='9') || *s=='.')) die("kernel-format");
 int translated=-1;size_t translation_size=sizeof(translated);errno=0;
 int query=sysctlbyname("sysctl.proc_translated",&translated,&translation_size,NULL,0);
 if(!((query==0 && translation_size==sizeof(translated) && translated==0) ||
      (query<0 && errno==ENOENT))) die("translation-or-unknown");
 if(secure_chain("/usr/bin/sandbox-exec")) die("system-seatbelt-chain");
 int system=open("/usr/bin/sandbox-exec",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat st;
 if(system<0 || fstat(system,&st)<0 || !S_ISREG(st.st_mode) || !(st.st_mode&0111) ||
    (st.st_mode&(S_ISUID|S_ISGID)) || hash_fd(system,sandbox_hash,MAX_IMAGE) || close(system)<0) die("system-seatbelt-image");
 prepare_image(argv[2]);directory_accounts();int leases=lease_directory();
 char path[PATH_MAX];
 if(snprintf(path,sizeof(path),"%s/vectors.jsonl",directory)>=(int)sizeof(path)) die("ledger-path");
 int ledger=open(path,O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
 if(ledger<0) die("ledger-open");
 unsigned count=!strcmp(m0_variant(),"baseline") ? 2u : 24u;
 for(unsigned i=0;i<count;i++) {
  unsigned remaining=remaining_seconds();
  alarm(remaining<15 ? remaining : 15);
  off_t before=lseek(ledger,0,SEEK_CUR);
  if(before<0) die("case-position");
  run_case((int)i,ledger,leases,os,u.release,u.machine);
  off_t after=lseek(ledger,0,SEEK_CUR);
  if(after<before || after-before>65536) die("case-evidence-bound");
 }
 (void)remaining_seconds();
 char digest[65];
 if(hash_fd(ledger,digest,2*1024*1024) || fchmod(ledger,0444)<0 || fsync(ledger)<0 ||
    close(ledger)<0 || close(leases)<0) die("ledger-seal");
 printf("{\"version\":1,\"root_directory\":\"%s\",\"ledger_sha256\":\"%s\",\"cases\":%u}\n",directory,digest,count);
 if(fflush(stdout)==EOF) die("manifest-write");
 alarm(0);return 0;
}
```

### Asset: tests/test_macos_m0a2_vectors.py

```python
import errno
import json
import os
import re
import unittest

SOURCE_NAMES=(
 "fork_exec_q","fork_exec_c","spawn_q","spawn_c","third_q","third_c",
 "refork_q","refork_c","grandchild_q","grandchild_c","pthread_q","pthread_c",
 "zombie_q","zombie_c","soft_q","soft_c","hard_q","hard_c",
 "hard_root_calibration","independent_q","independent_c","shared_counterexample",
 "migration_guard","migration_counterexample",
)
BASELINE_NAMES=("baseline_third","baseline_control")
SOURCE_CONFIGS=(
 (1,1,1,1,1,0),(1,0,1,1,1,0),(2,1,1,1,1,0),(2,0,1,1,1,0),
 (3,1,1,2,1,0),(3,0,1,2,1,0),(4,1,1,2,1,0),(4,1,0,2,1,0),
 (5,1,1,2,1,0),(5,0,1,2,1,0),(6,1,1,1,1,0),(6,0,1,1,1,0),
 (7,1,1,2,1,0),(7,0,1,2,1,0),(8,1,1,2,1,0),(8,0,1,2,1,0),
 (9,1,1,2,1,0),(9,0,1,2,1,0),(12,0,0,3,1,0),
 (10,1,1,2,2,0),(10,0,1,2,2,0),(10,1,1,2,2,1),
 (11,1,1,1,1,0),(11,1,1,1,2,1),
)
BASELINE_CONFIGS=((3,1,1,2,1,0),(3,0,1,2,1,0))
BEGIN=set("""kind version candidate_sha variant binary_sha256 profile_sha256 sandbox_exec_sha256
case_index case vector quota profile cap roots shared uid0 uid1 observer_pid observer_uid
arch os_build kernel observer_start_sec observer_start_usec deadline_ns""".split())
EVENT=set("""kind version case_index event slot other op pid ppid start_sec start_usec
uid euid gid egid saved_uid saved_gid count read group predicate current maximum rc error aux
independent_credentials live_count threads zombie_state fd3_errno fd4_errno canary_error canary_allowed""".split())
END=set("kind version case_index events roots_reaped remaining cleanup_scope retained".split())
ADMISSION=set("kind version case_index observer_uid consumed error second_forked".split())

def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key]=item
    return value

def need(condition,message):
    if not condition:
        raise ValueError(message)

def parse_vectors(raw,metadata):
    need(type(raw) is bytes and 0<len(raw)<=2*1024*1024 and raw.endswith(b"\n"),"raw bounds/LF")
    names=BASELINE_NAMES if metadata["variant"]=="baseline" else SOURCE_NAMES
    records=[]
    for line in raw.splitlines():
        need(0<len(line)<=4096,"line bound")
        row=json.loads(line,object_pairs_hook=unique)
        need(type(row) is dict,"row object")
        kind=row.get("kind")
        if kind=="begin":
            need(set(row)==BEGIN and type(row["version"]) is int and row["version"]==1,"begin schema")
            need(len(records)<len(names) and (not records or records[-1]["end"] is not None),"case nesting")
            need(type(row["case_index"]) is int and row["case_index"]==len(records)
                 and row["case"]==names[len(records)],"case order/count")
            for key in ("candidate_sha","variant","binary_sha256","arch","os_build","kernel","deadline_ns"):
                need(row[key]==metadata[key],"candidate/binary/OS mismatch")
            for key in ("binary_sha256","profile_sha256","sandbox_exec_sha256"):
                need(type(row[key]) is str and re.fullmatch("[0-9a-f]{64}",row[key]),"digest")
            need(type(row["observer_uid"]) is int and row["observer_uid"]==0
                 and type(row["observer_pid"]) is int and row["observer_pid"]>0,"observer")
            need(type(row["observer_start_sec"]) is int and row["observer_start_sec"]>0
                 and type(row["observer_start_usec"]) is int and row["observer_start_usec"]>=0
                 and type(row["deadline_ns"]) is int and 0<row["deadline_ns"]<2**64,"observer start/deadline")
            for key in ("vector","quota","profile","cap","roots","shared","uid0","uid1"):
                need(type(row[key]) is int,"begin integer")
            configs=BASELINE_CONFIGS if metadata["variant"]=="baseline" else SOURCE_CONFIGS
            need(tuple(row[k] for k in ("vector","quota","profile","cap","roots","shared"))==configs[len(records)],"fixed case configuration")
            need(row["quota"] in (0,1) and row["profile"] in (0,1) and row["shared"] in (0,1)
                 and row["roots"] in (1,2) and 1<=row["cap"]<=3,"case configuration")
            if row["vector"]!=12:
                need(60000<=row["uid0"]<61024,"UID range")
                if row["roots"]==2:
                    need(60000<=row["uid1"]<61024,"second UID")
                    need((row["uid0"]==row["uid1"])==bool(row["shared"]),"UID independence")
            records.append({"begin":row,"events":[],"admission":[],"end":None})
            continue
        need(records and records[-1]["end"] is None,"row outside case")
        record=records[-1]
        need(type(row.get("version")) is int and row["version"]==1
             and type(row.get("case_index")) is int
             and row["case_index"]==record["begin"]["case_index"],"row identity")
        if kind=="event":
            need(set(row)==EVENT,"event schema")
            need(all(type(row[k]) is int for k in EVENT-{"kind"}),"event integer")
            need(row["event"] in (1,2,3,4,5,6,7,8,100,101) and 0<=row["slot"]<8
                 and row["pid"]>0 and row["ppid"]>0 and row["start_sec"]>0
                 and row["start_usec"]>=0 and row["independent_credentials"]==1,"event identity")
            if record["begin"]["vector"]!=12:
                need(all(row[k]==row["uid"] for k in ("euid","gid","egid","saved_uid","saved_gid","group"))
                     and row["count"]==row["read"]==1 and row["predicate"]==0
                     and 60000<=row["uid"]<61024 and 1<=row["live_count"]<=8,"credential vector")
                if row["event"]!=100:
                    need(row["canary_allowed"]==1 and row["canary_error"] in ((errno.EPERM,errno.EACCES) if record["begin"]["profile"] else (0,)),"canary")
                if row["event"] not in (100,101):
                    need(row["fd3_errno"]==row["fd4_errno"]==errno.EBADF,"control FD closure")
            need(len(record["events"])<68,"event count")
            record["events"].append(row)
        elif kind=="admission":
            need(set(row)==ADMISSION and all(type(row[k]) is int for k in ADMISSION-{"kind"}),"admission schema")
            record["admission"].append(row)
        elif kind=="end":
            need(set(row)==END and all(type(row[k]) is int for k in ("version","case_index","events","roots_reaped","remaining"))
                 and type(row["events"]) is int
                 and row["events"]==len(record["events"]) and type(row["remaining"]) is int
                 and row["remaining"]==0 and row["roots_reaped"]==record["begin"]["roots"]
                 and row["cleanup_scope"]=="owned_roots_and_observed_direct_parent_reaps"
                 and row["retained"] is True,"end contract")
            record["end"]=row
        else:
            raise ValueError("unknown row")
    need(tuple(r["begin"]["case"] for r in records)==names
         and all(r["end"] is not None for r in records),"incomplete ledger")
    identities=[]
    for record in records:
        begin=record["begin"];events=record["events"]
        need(len(json.dumps(record).encode())<=65536,"case evidence bound")
        members={}
        for e in events:
            slot=e["slot"]
            if slot not in members:
                need(slot<begin["roots"] and e["event"] in (1,100),"unregistered member")
                members[slot]=(e["pid"],e["start_sec"],e["start_usec"])
            need(members[slot]==(e["pid"],e["start_sec"],e["start_usec"]),"member PID/start changed")
            if e["event"]==3:
                need(e["other"] not in members and e["rc"]>0 and e["error"]==0 and e["aux"]==1,"fork registration")
                # START supplies the already independently registered child's start tuple.
                children=[x for x in events if x["slot"]==e["other"] and x["event"]==1]
                need(len(children)==1 and children[0]["pid"]==e["rc"]
                     and children[0]["ppid"]==e["pid"],"child start/parent")
                child=children[0]
                members[e["other"]]=(child["pid"],child["start_sec"],child["start_usec"])
        starts=[e for e in events if e["event"]==1]
        need(len(starts)==len(members) and len({e["slot"] for e in starts})==len(starts),"start cardinality")
        done=[e for e in events if e["event"]==8]
        need(len({e["slot"] for e in done if e["slot"]<begin["roots"]})==begin["roots"],"roots done")
        reaped=[e["other"] for e in events if e["event"]==4]
        need(sorted(reaped)==sorted(set(members)-set(range(begin["roots"]))),"each descendant reaped once")
        if begin["vector"]!=12:
            identities.append(begin["uid0"])
            if begin["roots"]==2 and not begin["shared"]:
                identities.append(begin["uid1"])
        if begin["vector"]!=11 or begin["shared"]:
            need(not record["admission"],"unexpected admission")
        validate_creation_contract(record)
    need(len(identities)==len(set(identities)),"identity reused across cases")
    return {r["begin"]["case"]:r for r in records}

# Exact native creation contract: (parent slot, child slot, API op, succeeds).
# Per-parent order is fixed; independent root schedules may interleave.
CREATION_CONTRACT={
 "fork_exec_q":((0,2,1,False),),"fork_exec_c":((0,2,1,True),),
 "spawn_q":((0,2,2,False),),"spawn_c":((0,2,2,True),),
 "third_q":((0,2,1,True),(0,4,1,False)),
 "third_c":((0,2,1,True),(0,4,1,True)),
 "refork_q":((0,2,1,True),(0,4,1,True)),
 "refork_c":((0,2,1,True),(0,4,1,True)),
 "grandchild_q":((0,2,1,True),(2,4,1,False)),
 "grandchild_c":((0,2,1,True),(2,4,1,True)),
 "pthread_q":((0,2,1,False),),"pthread_c":((0,2,1,True),),
 "zombie_q":((0,2,1,True),(0,4,1,False),(0,6,1,True)),
 "zombie_c":((0,2,1,True),(0,4,1,True),(0,6,1,True)),
 "soft_q":((0,2,1,False),(0,4,1,True)),"soft_c":((0,2,1,True),),
 "hard_q":((0,2,1,True),),"hard_c":((0,2,1,True),),
 "hard_root_calibration":(),
 "independent_q":((0,2,1,True),(0,4,1,False),(1,3,1,True),(1,5,1,False)),
 "independent_c":((0,2,1,True),(0,4,1,True),(1,3,1,True),(1,5,1,True)),
 "shared_counterexample":((0,2,1,False),(1,3,1,False)),
 "migration_guard":(),"migration_counterexample":(),
 "baseline_third":((0,2,1,True),(0,4,1,True)),
 "baseline_control":((0,2,1,True),(0,4,1,True)),
}

def validate_creation_contract(record):
    b=record["begin"];events=record["events"];name=b["case"]
    need(name in CREATION_CONTRACT,"creation contract case")
    if name=="migration_guard":
        need(len(record["admission"])==1 and
             tuple(record["admission"][0][k] for k in ("observer_uid","consumed","error","second_forked"))
             ==(0,1,errno.EPERM,0),"creation migration admission evidence")
    attempts=CREATION_CONTRACT[name]
    expected_ops={}
    for parent,child,api,success in attempts:
        expected_ops.setdefault(parent,[]).append((3 if success else 2,child,api,success))
    if name=="soft_q":
        expected_ops[0]=[(2,0,3,None),(2,2,1,False),(2,0,4,None),(3,4,1,True)]
    elif name=="hard_q":
        expected_ops[0]=[(2,0,5,None),(3,2,1,True)]
    elif name=="hard_root_calibration":
        expected_ops[0]=[(2,0,7,None)]
    actual_ops=[e for e in events if e["event"] in (2,3)]
    need(len(actual_ops)==sum(map(len,expected_ops.values())),"creation operation cardinality")
    for parent in set(expected_ops)|{e["slot"] for e in actual_ops}:
        expected=expected_ops.get(parent,[])
        actual=[e for e in actual_ops if e["slot"]==parent]
        need(len(actual)==len(expected),"creation parent cardinality")
        for e,(kind,child,api,success) in zip(actual,expected):
            need((e["event"],e["other"],e["op"])==(kind,child,api),"creation operation sequence")
            if success is True:
                need(e["rc"]>0 and e["error"]==0 and e["aux"]==1,"creation success/first byte")
            elif success is False:
                need((e["rc"],e["error"],e["aux"])==(-1,errno.EAGAIN,0),"creation rejection")
            else:
                wanted=(-1,errno.EPERM) if api==5 else (0,0)
                need((e["rc"],e["error"],e["aux"])==(*wanted,0),"limit mutation result")
    successful={(parent,child) for parent,child,api,success in attempts if success}
    roots=set(range(b["roots"]))
    expected_members=roots|{child for parent,child in successful}
    started=[e for e in events if e["event"]==1]
    need(len(started)==len(expected_members) and {e["slot"] for e in started}==expected_members,
         "creation START set")
    positions={(kind,slot):[i for i,e in enumerate(events) if e["event"]==kind and e["slot"]==slot]
               for kind in (1,7,8,100,101) for slot in expected_members}
    for slot in expected_members:
        need(len(positions[1,slot])==1,"creation unique START")
        if slot in roots and b["vector"]!=12:
            need(len(positions[100,slot])==len(positions[101,slot])==1
                 and positions[100,slot][0]<positions[101,slot][0]<positions[1,slot][0],
                 "creation root phases")
        else:
            need(not positions[100,slot] and not positions[101,slot],"creation unexpected root phase")
    finishers=roots|({2} if b["vector"]==5 else set())
    for slot in expected_members:
        need(len(positions[7,slot])==len(positions[8,slot])==(1 if slot in finishers else 0),
             "creation FINISH/DONE set")
        if slot in finishers:
            finish,done=positions[7,slot][0],positions[8,slot][0]
            need(positions[1,slot][0]<finish<done,"creation FINISH/DONE order")
            own=[(i,e) for i,e in enumerate(events) if e["slot"]==slot and e["event"] in (2,3,5,6)]
            need(all(positions[1,slot][0]<i<finish for i,e in own),"creation operation lifetime")
            pending=sum(1 for parent,child in successful if parent==slot and
                        not any(e["event"]==4 and e["other"]==child and i<finish for i,e in enumerate(events)))
            need((events[finish]["rc"],events[finish]["error"],events[done]["rc"],events[done]["error"])
                 ==(pending,0,0,0),"creation FINISH pending count")
    reaps=[(i,e) for i,e in enumerate(events) if e["event"]==4]
    need(len(reaps)==len(successful) and {(e["slot"],e["other"]) for i,e in reaps}==successful,
         "creation reap set")
    for parent,child in successful:
        forks=[(i,e) for i,e in enumerate(events) if e["event"]==3 and e["slot"]==parent and e["other"]==child]
        waits=[(i,e) for i,e in reaps if e["slot"]==parent and e["other"]==child]
        need(len(forks)==len(waits)==1,"creation unique fork/reap")
        fi,fork=forks[0];ri,reap=waits[0];ci=positions[1,child][0]
        need(positions[1,parent][0]<fi<ci<ri<positions[8,parent][0]
             and (reap["rc"],reap["error"],reap["aux"])==(fork["rc"],0,0),
             "creation parent/child/reap causality")
        need(events[ci]["other"]==parent,"creation child parent slot")
        if child in finishers:
            need(positions[8,child][0]<ri,"creation grandchild parent DONE before reap")
    def event_index(kind,slot,other=None):
        found=[i for i,e in enumerate(events) if e["event"]==kind and e["slot"]==slot
               and (other is None or e["other"]==other)]
        need(len(found)==1,"creation causal marker cardinality")
        return found[0]
    if b["vector"]==4:
        need(event_index(4,0,2)<event_index(3,0,4),"creation refork after reap")
    if b["vector"]==7:
        need(event_index(1,2)<event_index(6,0,2)
             <event_index(2 if b["quota"] else 3,0,4)<event_index(4,0,2)
             <event_index(3,0,6),"creation zombie/reap/refork order")
    thread_events=[e for e in events if e["event"]==5]
    zombie_events=[e for e in events if e["event"]==6]
    need(len(thread_events)==(2 if b["vector"]==6 else 0),"creation thread event cardinality")
    need(len(zombie_events)==(1 if b["vector"]==7 else 0),"creation zombie event cardinality")
    if b["vector"]==6:
        need(max(i for i,e in enumerate(events) if e["event"]==5)
             <min(i for i,e in enumerate(events) if e["event"] in (2,3)),"creation joins before fork")

def operations(record,slot=None,op=None):
    return [e for e in record["events"] if e["event"] in (2,3)
            and (slot is None or e["slot"]==slot) and (op is None or e["op"]==op)]

def starts(record):
    return [e for e in record["events"] if e["event"]==1]

@unittest.skipUnless(os.environ.get("ICODE_M0A2_EVIDENCE"),"native M0a2 evidence not requested")
class TestVectorsNative(unittest.TestCase):
    rows=None
    variant=None

    def test_complete_identity_protocol(self):
        expected=BASELINE_NAMES if self.variant=="baseline" else SOURCE_NAMES
        self.assertEqual(tuple(self.rows),expected)
        for record in self.rows.values():
            b=record["begin"]
            if b["vector"]!=12:
                for root in range(b["roots"]):
                    phases=[e["event"] for e in record["events"] if e["slot"]==root and e["event"] in (100,101,1)]
                    self.assertEqual(phases,[100,101,1])
                    root_start=next(e for e in starts(record) if e["slot"]==root)
                    self.assertEqual(root_start["live_count"],b["roots"] if b["shared"] else 1)

    def test_creation_positive_controls(self):
        controls=BASELINE_NAMES[1:] if self.variant=="baseline" else (
            "fork_exec_c","spawn_c","third_c","refork_q","refork_c","grandchild_c",
            "pthread_c","zombie_c","soft_c","hard_c","independent_c")
        for name in controls:
            for e in operations(self.rows[name]):
                self.assertGreater(e["rc"],0,name)
                self.assertEqual((e["error"],e["aux"]),(0,1),name)
        if self.variant!="baseline":
            calibration=operations(self.rows["hard_root_calibration"],op=7)
            self.assertEqual(len(calibration),1)
            self.assertEqual((calibration[0]["rc"],calibration[0]["error"],
                              calibration[0]["current"],calibration[0]["maximum"]),(0,0,3,3))

    def test_cap2_quota_semantic(self):
        if self.variant=="baseline":
            third=operations(self.rows["baseline_third"])[1]
            self.assertEqual(third["rc"],-1,"M0A2_CAP2_REJECTION")
            self.assertEqual((third["error"],third["aux"]),(errno.EAGAIN,0))
            return
        expected={
            "fork_exec_q":[0],"spawn_q":[0],"third_q":[1],"grandchild_q":[1],
            "pthread_q":[0],"zombie_q":[1],"soft_q":[1],"independent_q":[1,3],
            "shared_counterexample":[0,1],
        }
        for name,indices in expected.items():
            record=self.rows[name]
            ops=operations(record)
            if name=="independent_q":
                # Cross-root scheduling is deliberately unordered.
                rejected=[e for e in ops if e["rc"]<0]
                self.assertEqual(len(rejected),2)
            elif name=="soft_q":
                rejected=[e for e in ops if e["op"]==1 and e["other"]==2]
            else:
                rejected=[ops[i] for i in indices]
            for e in rejected:
                self.assertEqual((e["rc"],e["error"],e["aux"]),(-1,errno.EAGAIN,0),name)

    def test_inheritance_and_limit_mutations(self):
        for record in self.rows.values():
            b=record["begin"]
            if b["vector"]==12:
                continue
            soft_current=b["cap"]
            initial=next(e for e in starts(record) if e["slot"]==0)
            for e in record["events"]:
                if e["op"]==3: soft_current=1
                if e["op"]==4: soft_current=2
                if self.variant=="baseline" or not b["quota"]:
                    self.assertGreaterEqual(e["current"],3 if b["vector"]==3 else 2)
                    self.assertEqual((e["current"],e["maximum"]),(initial["current"],initial["maximum"]))
                    continue
                expected=(soft_current,2) if b["vector"]==8 and e["slot"]==0 else (b["cap"],b["cap"])
                self.assertEqual((e["current"],e["maximum"]),expected,b["case"])
        if self.variant!="baseline":
            soft=operations(self.rows["soft_q"],op=3)+operations(self.rows["soft_q"],op=4)
            self.assertEqual([(e["rc"],e["error"]) for e in soft],[(0,0),(0,0)])
            hard=operations(self.rows["hard_q"],op=5)
            self.assertEqual([(e["rc"],e["error"],e["current"],e["maximum"]) for e in hard],
                             [(-1,errno.EPERM,2,2)])

    def test_threads_zombie_and_identity_boundaries(self):
        if self.variant=="baseline":
            self.assertGreater(operations(self.rows["baseline_third"])[0]["rc"],0)
            return
        for name in ("pthread_q","pthread_c"):
            waves=[e for e in self.rows[name]["events"] if e["event"]==5]
            self.assertEqual([(e["rc"],e["aux"],e["other"],e["threads"],e["live_count"]) for e in waves],
                             [(4,3,3,4,1),(2,1,4,2,1)])
        for name in ("zombie_q","zombie_c"):
            record=self.rows[name]
            z=[e for e in record["events"] if e["event"]==6]
            self.assertEqual(len(z),1)
            self.assertEqual((z[0]["rc"],z[0]["error"],z[0]["zombie_state"]),(0,0,5))
            ordered=[(e["event"],e["other"]) for e in record["events"]]
            self.assertLess(ordered.index((6,2)),next(i for i,e in enumerate(record["events"])
                if e["event"] in (2,3) and e["other"]==4))
            self.assertLess(ordered.index((4,2)),ordered.index((3,6)))
        guard=self.rows["migration_guard"]
        self.assertEqual([(r["observer_uid"],r["consumed"],r["error"],r["second_forked"])
                          for r in guard["admission"]],[(0,1,errno.EPERM,0)])
        self.assertEqual(len(starts(guard)),1)
        for name in ("migration_counterexample","shared_counterexample"):
            roots=[e for e in starts(self.rows[name]) if e["slot"]<2]
            self.assertEqual(len(roots),2)
            self.assertEqual({e["uid"] for e in roots},{self.rows[name]["begin"]["uid0"]})
            self.assertTrue(all(e["live_count"]==2 for e in roots))
        q=self.rows["independent_q"]
        self.assertNotEqual(q["begin"]["uid0"],q["begin"]["uid1"])
        self.assertEqual(len([e for e in operations(q) if e["rc"]>0]),2)
        self.assertEqual(len([e for e in operations(self.rows["independent_c"]) if e["rc"]>0]),4)

# Portable observer/collector tests; synthetic rows never grant native credit.
import copy
import hashlib
import importlib.util
from pathlib import Path
import stat
import subprocess
import time
from types import SimpleNamespace
from unittest import mock

def software_fixture(variant="source"):
    names=BASELINE_NAMES if variant=="baseline" else SOURCE_NAMES
    configs=BASELINE_CONFIGS if variant=="baseline" else SOURCE_CONFIGS
    meta={"phase":"red" if variant=="baseline" else "green","variant":variant,
          "candidate_sha":"a"*40,"binary_sha256":hashlib.sha256(b"binary").hexdigest(),
          "arch":"arm64","os_build":"26A1","kernel":"26.0.0","deadline_ns":500_000_000_000}
    rows=[]
    for index,(name,config) in enumerate(zip(names,configs)):
        vector,quota,profile,cap,roots,shared=config
        uid=0 if vector==12 else 60000+index*3
        uids=[uid,uid if shared else uid+1]
        begin={"kind":"begin","version":1,**{k:meta[k] for k in
            ("candidate_sha","variant","binary_sha256","arch","os_build","kernel")},
            "profile_sha256":"b"*64,"sandbox_exec_sha256":"c"*64,"case_index":index,"case":name,
            "vector":vector,"quota":quota,"profile":profile,"cap":cap,"roots":roots,"shared":shared,
            "uid0":uids[0],"uid1":uids[1] if roots==2 else 0,"observer_pid":400,"observer_uid":0,
            "observer_start_sec":800,"observer_start_usec":0,"deadline_ns":meta["deadline_ns"]}
        rows.append(begin);events=[];alive={s for s in range(roots)}
        pids={s:1000+index*10+s for s in alive};parents={s:400 for s in alive}
        identities={s:uids[s] for s in alive};limits={s:cap if quota and variant=="source" else 20 for s in alive}
        def emit(kind,slot,other=0,op=0,rc=0,error=0,aux=0,threads=-1,zombie=-1):
            identity=identities[slot]
            current=limits[slot]
            hard=2 if vector==8 and quota and variant=="source" else current
            row={"kind":"event","version":1,"case_index":index,"event":kind,"slot":slot,
                 "other":other,"op":op,"pid":pids[slot],"ppid":parents[slot],"start_sec":900+index,
                 "start_usec":slot,"uid":identity,"euid":identity,"gid":identity,"egid":identity,
                 "saved_uid":identity,"saved_gid":identity,"count":1,"read":1,"group":identity,
                 "predicate":0,"current":current,"maximum":hard,"rc":rc,"error":error,"aux":aux,
                 "independent_credentials":1,"live_count":sum(identities[s]==identity for s in alive),
                 "threads":threads,"zombie_state":zombie,
                 "fd3_errno":0 if kind in (100,101) else errno.EBADF,
                 "fd4_errno":0 if kind in (100,101) else errno.EBADF,
                 "canary_error":-1 if kind==100 else errno.EPERM if profile else 0,
                 "canary_allowed":0 if kind==100 else 1}
            events.append(row)
            return row
        def fork(parent,child,success=True,spawn=False):
            if not success:
                emit(2,parent,child,2 if spawn else 1,-1,errno.EAGAIN)
                return False
            pids[child]=1000+index*10+child;parents[child]=pids[parent]
            identities[child]=identities[parent];limits[child]=limits[parent];alive.add(child)
            emit(3,parent,child,2 if spawn else 1,pids[child],0,1)
            emit(1,child,parent,aux=errno.EPERM if profile else 0)
            return True
        def reap(parent,child):
            alive.remove(child)
            emit(4,parent,child,rc=pids[child])
        if vector!=12:
            for root in range(roots):
                emit(100,root);emit(101,root)
        for root in range(roots):
            emit(1,root,aux=errno.EPERM if profile else 0)
        held={root:[] for root in range(roots)}
        if vector==12:
            limits[0]=3;emit(2,0,op=7)
        elif vector==11:
            if not shared:
                rows.append({"kind":"admission","version":1,"case_index":index,"observer_uid":0,
                             "consumed":1,"error":errno.EPERM,"second_forked":0})
        elif vector==6:
            emit(5,0,3,rc=4,aux=3,threads=4)
            emit(5,0,4,rc=2,aux=1,threads=2)
            if fork(0,2,not quota or variant=="baseline"):
                held[0].append(2)
        elif vector in (1,2):
            if fork(0,2,not quota or variant=="baseline",vector==2):
                held[0].append(2)
        elif vector==4:
            fork(0,2);reap(0,2);fork(0,4);reap(0,4)
        elif vector==5:
            fork(0,2);held[0].append(2)
            if fork(2,4,not quota or variant=="baseline"):
                held[2]=[4]
            else:
                held[2]=[]
        elif vector==7:
            fork(0,2)
            emit(6,0,2,rc=0,aux=pids[2],zombie=5)
            if fork(0,4,not quota or variant=="baseline"):
                held[0].append(4)
            reap(0,2)
            fork(0,6);held[0].append(6)
        elif vector==8:
            if quota:
                limits[0]=1;emit(2,0,op=3)
                fork(0,2,False)
                limits[0]=2;emit(2,0,op=4)
                fork(0,4);held[0].append(4)
            else:
                fork(0,2);held[0].append(2)
        elif vector==9:
            if quota:
                emit(2,0,op=5,rc=-1,error=errno.EPERM)
            fork(0,2);held[0].append(2)
        else:
            for root in range(roots):
                first=2+root
                if vector==10 and shared:
                    fork(root,first,False)
                    continue
                fork(root,first);held[root].append(first)
                if fork(root,4+root,not quota or variant=="baseline"):
                    held[root].append(4+root)
        if vector==5:
            emit(7,2,rc=len(held[2]))
        for root in range(roots):
            emit(7,root,rc=len(held[root]))
        if vector==5:
            for child in held[2]:
                reap(2,child)
            emit(8,2)
        for root in range(roots):
            for child in held[root]:
                reap(root,child)
            emit(8,root)
        rows.extend(events)
        rows.append({"kind":"end","version":1,"case_index":index,"events":len(events),
            "roots_reaped":roots,"remaining":0,
            "cleanup_scope":"owned_roots_and_observed_direct_parent_reaps","retained":True})
    return meta,rows

def encoded(rows):
    return ("\n".join(json.dumps(row,separators=(",",":")) for row in rows)+"\n").encode()

def exercise_assertions(raw,meta):
    rows=parse_vectors(raw,meta)
    target=unittest.TestCase()
    target.rows=rows;target.variant=meta["variant"]
    for name in sorted(name for name in TestVectorsNative.__dict__ if name.startswith("test_")):
        getattr(TestVectorsNative,name)(target)
    return rows

class TestVectorsPortable(unittest.TestCase):
    def test_source_oracle_all_twenty_four(self):
        meta,rows=software_fixture()
        self.assertEqual(len(exercise_assertions(encoded(rows),meta)),24)

    def test_baseline_only_real_quota_assertion_would_fail(self):
        meta,rows=software_fixture("baseline")
        parsed=parse_vectors(encoded(rows),meta)
        target=unittest.TestCase();target.rows=parsed;target.variant="baseline"
        methods=[name for name in TestVectorsNative.__dict__ if name.startswith("test_")]
        failures=[]
        for name in methods:
            try:
                getattr(TestVectorsNative,name)(target)
            except AssertionError as error:
                failures.append((name,str(error)))
        self.assertEqual(len(failures),1)
        self.assertEqual(failures[0][0],"test_cap2_quota_semantic")
        self.assertIn("M0A2_CAP2_REJECTION",failures[0][1])
        # This is synthetic observer self-calibration, not a native RED claim.

    def test_schema_identity_and_completeness_negative_controls(self):
        meta,rows=software_fixture()
        mutations=[
            lambda r:r.pop(),
            lambda r:r.insert(0,copy.deepcopy(r[0])),
            lambda r:r[0].update(candidate_sha="f"*40),
            lambda r:r[0].update(binary_sha256="f"*64),
            lambda r:r[0].update(cap=2),
            lambda r:r[1].update(uid=True),
            lambda r:r[1].update(group=1),
            lambda r:r[1].update(saved_uid=0),
            lambda r:r[1].update(start_sec=0),
            lambda r:r[3].update(fd3_errno=0),
            lambda r:r[2].update(canary_allowed=0),
            lambda r:r[1].update(extra=1),
            lambda r:r[-1].update(events=0),
            lambda r:r[-1].update(roots_reaped=True),
        ]
        for change in mutations:
            with self.subTest(change=mutations.index(change)):
                bad=copy.deepcopy(rows);change(bad)
                with self.assertRaises((ValueError,AssertionError)):
                    exercise_assertions(encoded(bad),meta)
        with self.assertRaises(ValueError):
            parse_vectors(encoded(rows).replace(b'"version":1',b'"version":1,"version":1',1),meta)

    def test_semantic_mutation_negative_controls(self):
        meta,rows=software_fixture()
        predicates=[
            lambda r:r["kind"]=="event" and r["event"]==2 and r["error"]==errno.EAGAIN,
            lambda r:r["kind"]=="event" and r["event"]==5,
            lambda r:r["kind"]=="event" and r["event"]==6,
            lambda r:r["kind"]=="event" and r["op"]==5,
            lambda r:r["kind"]=="admission",
        ]
        edits=[{"error":errno.EPERM},{"threads":5},{"zombie_state":0},
               {"error":0},{"error":0}]
        for select,edit in zip(predicates,edits):
            bad=copy.deepcopy(rows)
            next(row for row in bad if select(row)).update(edit)
            with self.assertRaises((ValueError,AssertionError)):
                exercise_assertions(encoded(bad),meta)

    def test_every_case_requires_exact_creation_and_reap_evidence(self):
        checked=0
        for variant in ("source","baseline"):
            meta,rows=software_fixture(variant)
            names=SOURCE_NAMES if variant=="source" else BASELINE_NAMES
            for index,name in enumerate(names):
                attempts=CREATION_CONTRACT[name]
                successful=[child for parent,child,api,success in attempts if success]
                modes=["all_creation","one_attempt"] if attempts else ["dedicated"]
                modes += [("child_START",child) for child in successful]
                modes += [("reap",child) for child in successful]
                for mode in modes:
                    with self.subTest(variant=variant,case=name,mutation=mode):
                        bad=copy.deepcopy(rows)
                        def selected(row):
                            return row.get("case_index")==index
                        if mode=="all_creation":
                            children=set(successful)
                            bad=[r for r in bad if not (selected(r) and r["kind"]=="event" and
                                 ((r["event"] in (2,3) and r["op"] in (1,2)) or
                                  r["slot"] in children or (r["event"]==4 and r["other"] in children)))]
                            for r in bad:
                                if selected(r) and r["kind"]=="event" and r["event"]==7:
                                    r["rc"]=0
                        elif mode=="one_attempt":
                            found=next(i for i,r in enumerate(bad) if selected(r) and r["kind"]=="event"
                                       and r["event"] in (2,3) and r["op"] in (1,2))
                            del bad[found]
                        elif mode=="dedicated":
                            found=next(i for i,r in enumerate(bad) if selected(r) and
                                       ((name=="hard_root_calibration" and r["kind"]=="event" and r["op"]==7)
                                        or (name=="migration_guard" and r["kind"]=="admission")
                                        or (name=="migration_counterexample" and r["kind"]=="event"
                                            and r["event"]==1 and r["slot"]==1)))
                            del bad[found]
                        else:
                            kind,child=mode
                            found=next(i for i,r in enumerate(bad) if selected(r) and r["kind"]=="event" and
                                       ((kind=="child_START" and r["event"]==1 and r["slot"]==child)
                                        or (kind=="reap" and r["event"]==4 and r["other"]==child)))
                            del bad[found]
                        # Repair factual accounting: refusal must not rely on stale end.events.
                        for r in bad:
                            if selected(r) and r["kind"]=="end":
                                r["events"]=sum(selected(e) and e["kind"]=="event" for e in bad)
                        with self.assertRaises(ValueError):
                            exercise_assertions(encoded(bad),meta)
                        checked+=1
        self.assertEqual(checked,113)

class TestVectorsCollectorPortable(unittest.TestCase):
    def test_actual_collector_success_and_rejection_boundaries(self):
        import tempfile
        import selectors
        from scripts import run_macos_m0a2_vectors as collector
        modes=(
            "success","native_nonzero","native_timeout","native_wait_timeout","native_select_timeout",
            "native_stdout_overflow","native_stderr_overflow","native_stderr","manifest_513","manifest_empty",
            "manifest_duplicate","manifest_bool_version","manifest_version","manifest_extra","manifest_bool_cases",
            "manifest_cases","manifest_path","manifest_digest_format","manifest_digest",
            "directory_owner","directory_mode","directory_type","ledger_owner","ledger_mode","ledger_nlink",
            "ledger_zero","ledger_large","ledger_type","changed_dev","changed_ino","changed_size",
            "changed_mtime","changed_ctime","changed_owner","changed_mode","changed_nlink",
            "ledger_short","ledger_overflow","ledger_bad_json","ledger_incomplete","observer_quota",
            "binary_missing","binary_symlink","binary_zero",
        )
        self.assertEqual(len(modes),44)
        for mode in modes:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix="m0a2-software-") as temporary:
                root=Path(temporary);build=root/"build";build.mkdir();output=root/"green";output.mkdir()
                binary=build/"icode_m0a1_vectors_source";binary.write_bytes(b"binary");binary.chmod(0o700)
                meta,rows=software_fixture()
                meta["deadline_ns"]=500_000_000_000
                if mode=="observer_quota":
                    next(r for r in rows if r["kind"]=="event" and r["error"]==errno.EAGAIN)["error"]=errno.EPERM
                raw=encoded(rows)
                if mode=="ledger_bad_json":raw=b"not JSON\n"
                if mode=="ledger_incomplete":raw=encoded(rows[:-1])
                if mode=="ledger_overflow":raw=b"X"*(2*1024*1024+1)
                digest=hashlib.sha256(raw).hexdigest()
                manifest={"version":1,"root_directory":"/private/var/icode-m0a1.Model",
                          "ledger_sha256":digest,"cases":24}
                changes={
                    "manifest_bool_version":{"version":True},"manifest_version":{"version":2},
                    "manifest_extra":{"extra":1},"manifest_bool_cases":{"cases":True},
                    "manifest_cases":{"cases":23},"manifest_path":{"root_directory":"/private/var/../tmp"},
                    "manifest_digest_format":{"ledger_sha256":"z"*64},
                    "manifest_digest":{"ledger_sha256":"f"*64},
                }
                manifest.update(changes.get(mode,{}))
                stdout=json.dumps(manifest).encode()
                if mode=="manifest_513":stdout=b" "*513
                if mode=="manifest_empty":stdout=b""
                if mode=="manifest_duplicate":stdout=stdout.replace(b'"version": 1',b'"version": 1, "version": 1')
                if mode=="native_stdout_overflow":stdout=b"X"*65537
                stderr=b"X"*65537 if mode=="native_stderr_overflow" else b"diagnostic" if mode=="native_stderr" else b""
                if mode=="binary_missing":binary.unlink()
                if mode=="binary_symlink":
                    binary.unlink();binary.symlink_to("/dev/null")
                if mode=="binary_zero":binary.write_bytes(b"")
                streams={1001:bytearray(stdout),1002:bytearray(stderr),700:bytearray(raw)}
                original_lstat=Path.lstat;original_open=os.open;original_read=os.read;original_fstat=os.fstat
                directory=SimpleNamespace(st_mode=stat.S_IFDIR|0o755,st_uid=0)
                if mode=="directory_owner":directory.st_uid=1
                if mode=="directory_mode":directory.st_mode=stat.S_IFDIR|0o777
                if mode=="directory_type":directory.st_mode=stat.S_IFREG|0o755
                file_fields=dict(st_mode=stat.S_IFREG|0o444,st_uid=0,st_nlink=1,
                    st_size=len(raw),st_dev=1,st_ino=2,st_mtime_ns=3,st_ctime_ns=4)
                for key,value in {
                    "ledger_owner":("st_uid",1),"ledger_mode":("st_mode",stat.S_IFREG|0o644),
                    "ledger_nlink":("st_nlink",2),"ledger_zero":("st_size",0),
                    "ledger_large":("st_size",2*1024*1024+1),
                    "ledger_type":("st_mode",stat.S_IFDIR|0o444),
                    "ledger_short":("st_size",len(raw)+1),
                }.items():
                    if mode==key:file_fields[value[0]]=value[1]
                # Overflow is detected by actual read loop, not the initial stat guard.
                if mode=="ledger_overflow":file_fields["st_size"]=2*1024*1024
                stat_calls=[0]
                def fstat(fd):
                    if fd!=700:return original_fstat(fd)
                    stat_calls[0]+=1;fields=dict(file_fields)
                    changed={
                        "changed_dev":"st_dev","changed_ino":"st_ino","changed_size":"st_size",
                        "changed_mtime":"st_mtime_ns","changed_ctime":"st_ctime_ns","changed_owner":"st_uid",
                        "changed_mode":"st_mode","changed_nlink":"st_nlink",
                    }
                    if stat_calls[0]>1 and mode in changed:fields[changed[mode]]+=1
                    return SimpleNamespace(**fields)
                def lstat(path,*args,**kwargs):
                    if str(path)=="/private/var/icode-m0a1.Model":return directory
                    return original_lstat(path,*args,**kwargs)
                def opened(path,*args,**kwargs):
                    if str(path)=="/private/var/icode-m0a1.Model/vectors.jsonl":return 700
                    return original_open(path,*args,**kwargs)
                def read(fd,size):
                    if fd not in streams:return original_read(fd,size)
                    value=bytes(streams[fd][:size]);del streams[fd][:size];return value
                class Pipe:
                    def __init__(self,fd):self.fd=fd;self.closed=False
                    def fileno(self):return self.fd
                    def close(self):self.closed=True
                class Process:
                    pid=987
                    def __init__(self):
                        self.stdout=Pipe(1001);self.stderr=Pipe(1002);self.returncode=None
                    def poll(self):return self.returncode
                    def wait(self,timeout):
                        if mode=="native_wait_timeout":raise subprocess.TimeoutExpired("model",timeout)
                        self.returncode=9 if mode=="native_nonzero" else 0
                        return self.returncode
                process=Process()
                class Selector:
                    def __init__(self):self.mapping={}
                    def __enter__(self):return self
                    def __exit__(self,*args):return False
                    def register(self,obj,event,data):
                        self.mapping[obj.fileno()]=SimpleNamespace(fileobj=obj,data=data)
                    def unregister(self,obj):self.mapping.pop(obj.fileno())
                    def get_map(self):return self.mapping
                    def select(self,timeout):
                        if mode=="native_select_timeout":raise TimeoutError("model deadline")
                        return [(value,None) for value in list(self.mapping.values())]
                clock_calls=[0]
                def clock(which):
                    self.assertEqual(which,time.CLOCK_MONOTONIC)
                    clock_calls[0]+=1
                    return 501_000_000_000 if mode=="native_timeout" and clock_calls[0]>1 else 100_000_000_000
                original_close=os.close
                def close(fd):
                    if fd!=700:return original_close(fd)
                with mock.patch.object(collector,"process_groups_binding",return_value="d"*64), \
                     mock.patch.object(collector.subprocess,"Popen",return_value=process) as popen, \
                     mock.patch.object(collector.selectors,"DefaultSelector",Selector), \
                     mock.patch.object(collector.time,"clock_gettime_ns",side_effect=clock), \
                     mock.patch.object(collector.os,"killpg") as killed, \
                     mock.patch.object(Path,"lstat",lstat), \
                     mock.patch.object(collector.os,"open",side_effect=opened), \
                     mock.patch.object(collector.os,"read",side_effect=read), \
                     mock.patch.object(collector.os,"fstat",side_effect=fstat), \
                     mock.patch.object(collector.os,"close",side_effect=close):
                    if mode=="success":
                        result=collector.run_vectors(Path(__file__).resolve().parents[1],build,output,dict(meta))
                        self.assertEqual(result["result"],"vectors_GREEN_only")
                        self.assertEqual(result["cases"],24)
                        self.assertTrue((output/"vectors-result.json").is_file())
                        self.assertEqual(popen.call_args.args[0][-1],format(meta["deadline_ns"],"016x"))
                    else:
                        with self.assertRaises((RuntimeError,ValueError,FileNotFoundError,TimeoutError)):
                            collector.run_vectors(Path(__file__).resolve().parents[1],build,output,dict(meta))
                        self.assertFalse((output/"vectors-result.json").exists())
                        if mode in ("native_timeout","native_wait_timeout","native_select_timeout",
                                    "native_stdout_overflow","native_stderr_overflow"):
                            self.assertTrue(killed.called)

class TestVectorsDeadlinePortable(unittest.TestCase):
    def test_actual_native_deadline_functions_with_clock_boundary_stub(self):
        import shutil
        import subprocess
        import tempfile
        if os.name!="posix":
            self.skipTest("software C probe requires POSIX host; not native credit")
        compiler=shutil.which("cc")
        self.assertIsNotNone(compiler)
        repo=Path(__file__).resolve().parents[1]
        source=(repo/"native/mac/tests/icode_m0a2_vectors.c").read_text()
        common=(repo/"native/mac/tests/icode_m0a1_fixed_helpers.inc").read_text()
        fragment=source[source.index("static uint64_t experiment_deadline;"):
                        source.index("static struct definition definition_at(")]
        hex_function=common[common.index("static int hex_string("):common.index("static int numeric(")]
        probe=r"""
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static jmp_buf failure;
static const char *last_stage;
static struct timespec fake_now={100,0};
static int clock_error;
static unsigned checks;
static void die(const char *stage) { last_stage=stage;longjmp(failure,1); }
static int fake_clock(clockid_t which,struct timespec *out) {
 if(which!=CLOCK_MONOTONIC) abort();
 if(clock_error) { errno=EIO;return -1; }
 *out=fake_now;return 0;
}
#define clock_gettime fake_clock
""" + hex_function + fragment + r"""
#define CHECK(statement,reject,prefix) do { \
 checks++;last_stage=NULL; \
 if(setjmp(failure)) { if(!(reject) || strncmp(last_stage,prefix,strlen(prefix))) return 3; } \
 else { statement; if(reject) return 4; } \
} while(0)
int main(void) {
 char text[17];
 snprintf(text,sizeof(text),"%016" PRIx64,(uint64_t)101000000000ULL);
 CHECK(parse_deadline(text),0,"");
 CHECK((void)remaining_seconds(),0,"");
 snprintf(text,sizeof(text),"%016" PRIx64,(uint64_t)580000000000ULL);
 CHECK(parse_deadline(text),0,"");
 snprintf(text,sizeof(text),"%016" PRIx64,(uint64_t)580000000001ULL);
 CHECK(parse_deadline(text),1,"deadline-window");
 CHECK(parse_deadline("000000174876e800"),1,"deadline-window");
 CHECK(parse_deadline("0000000000000000"),1,"deadline-window");
 CHECK(parse_deadline("ffffffffffffffff"),1,"deadline-window");
 CHECK(parse_deadline("000000000000000"),1,"deadline-hex16");
 CHECK(parse_deadline("00000000000000000"),1,"deadline-hex16");
 CHECK(parse_deadline("000000000000000G"),1,"deadline-hex16");
 CHECK(parse_deadline("+000000000000000"),1,"deadline-hex16");
 clock_error=1;CHECK(parse_deadline(text),1,"monotonic-clock");clock_error=0;
 fake_now.tv_sec=-1;CHECK(parse_deadline(text),1,"monotonic-range");fake_now.tv_sec=100;
 fake_now.tv_nsec=1000000000L;CHECK(parse_deadline(text),1,"monotonic-range");fake_now.tv_nsec=0;
 fake_now.tv_sec=(time_t)INT64_MAX;CHECK(parse_deadline(text),1,"monotonic-range");fake_now.tv_sec=100;
 experiment_deadline=101000000000ULL;fake_now.tv_nsec=1;
 CHECK((void)remaining_seconds(),1,"deadline-expired");
 fake_now.tv_sec=101;fake_now.tv_nsec=0;CHECK((void)remaining_seconds(),1,"deadline-expired");
 fake_now.tv_sec=100;experiment_deadline=115000000000ULL;
 if(remaining_seconds()!=15) return 5;
 if(checks!=17) return 6;
 puts("deadline software boundary: 17 checks");
 return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="m0a2-clock-software-") as temporary:
            executable=Path(temporary)/"probe"
            compiled=subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror","-x","c","-",
                "-o",str(executable)],input=probe,text=True,capture_output=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,"deadline software boundary: 17 checks\n")

class TestVectorsMechanicalPortable(unittest.TestCase):
    def test_exact_inverse_keeps_original_driver_and_w1(self):
        repo=Path(__file__).resolve().parents[1]
        common=(repo/"native/mac/tests/icode_m0a1_fixed_helpers.inc").read_bytes()
        split=common.index(b"static int canaries(")
        driver=(repo/"native/mac/tests/icode_m0a1_driver.c").read_bytes()
        marker=b'#include "icode_m0a1_fixed_helpers.inc"\n'
        self.assertEqual(driver.count(marker),1)
        restored=driver.replace(marker,common[:split]).replace(b"static void gate(",common[split:]+b"static void gate(")
        self.assertEqual(hashlib.sha256(restored).hexdigest(),
            "944c9268461e522a01653b46bb3c18d038504af66910c66cf861901f8f28d25e")
        identity=(repo/"native/mac/tests/icode_m0a1_unused_identity.inc").read_bytes()
        w1=(repo/"native/mac/tests/icode_m0a1_process_groups_native.c").read_bytes()
        marker=b'#include "icode_m0a1_unused_identity.inc"\n'
        self.assertEqual(w1.count(marker),1)
        self.assertEqual(hashlib.sha256(w1.replace(marker,identity)).hexdigest(),
            "eb51b489cd07399414b98dc409fe08637c56d3b1e99636def493348d0d1aa636")

@unittest.skipUnless(os.environ.get("ICODE_M0A2_LIMIT_SOFTWARE"),"explicit cap2 software gate not requested")
class TestVectorsLimitPortable(unittest.TestCase):
    def test_actual_quota_source_cap2_and_exact_readback(self):
        import shutil
        import subprocess
        import tempfile
        compiler=shutil.which("cc")
        self.assertIsNotNone(compiler)
        repo=Path(__file__).resolve().parents[1]
        source=(repo/"native/mac/icode_m0a1_limit.c").read_text()
        probe=r"""
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
static unsigned sets,gets,checks;
static int set_error,get_error,read_mode;
static struct rlimit stored;
static int fake_set(int resource,const struct rlimit *value) {
 if(resource!=RLIMIT_NPROC) abort();
 sets++;if(set_error) { errno=set_error;return -1; }
 stored=*value;return 0;
}
static int fake_get(int resource,struct rlimit *value) {
 if(resource!=RLIMIT_NPROC) abort();
 gets++;if(get_error) { errno=get_error;return -1; }
 *value=stored;
 if(read_mode==1) value->rlim_cur--;
 if(read_mode==2) value->rlim_max++;
 return 0;
}
#define setrlimit fake_set
#define getrlimit fake_get
""" + source + r"""
#define RESET() do { sets=gets=0;set_error=get_error=read_mode=0;stored=(struct rlimit){2,2}; } while(0)
#define EXPECT(condition) do { checks++;if(!(condition)) { printf("failed software check=%u sets=%u gets=%u\n",checks,sets,gets);return 42; } } while(0)
int main(void) {
 RESET();int cap2=m0_apply_limit(2,1);
 EXPECT(cap2==0 && sets==1 && gets==1 && stored.rlim_cur==2 && stored.rlim_max==2);
 RESET();errno=EBUSY;EXPECT(m0_apply_limit(0,0)==0 && !sets && !gets && errno==EBUSY);
 RESET();errno=EBUSY;EXPECT(m0_check_limit(2,0)==0 && !sets && !gets && errno==EBUSY);
 RESET();EXPECT(m0_apply_limit(1,1)==0 && sets==1 && gets==1 && stored.rlim_cur==1 && stored.rlim_max==1);
 const rlim_t invalid[]={0,3,4,8};
 for(unsigned i=0;i<4;i++) { RESET();EXPECT(m0_apply_limit(invalid[i],1)==EINVAL && !sets && !gets); }
 RESET();set_error=EACCES;EXPECT(m0_apply_limit(2,1)==EACCES && sets==1 && !gets);
 RESET();get_error=EIO;EXPECT(m0_apply_limit(2,1)==EIO && sets==1 && gets==1);
 RESET();read_mode=1;EXPECT(m0_apply_limit(2,1)==ERANGE && sets==1 && gets==1);
 RESET();read_mode=2;EXPECT(m0_apply_limit(2,1)==ERANGE && sets==1 && gets==1);
 RESET();EXPECT(m0_check_limit(2,1)==0 && !sets && gets==1);
 RESET();read_mode=1;EXPECT(m0_check_limit(2,1)==ERANGE && !sets && gets==1);
 RESET();read_mode=2;EXPECT(m0_check_limit(2,1)==ERANGE && !sets && gets==1);
 RESET();get_error=EIO;EXPECT(m0_check_limit(2,1)==EIO && !sets && gets==1);
 EXPECT(!strcmp(m0_variant(),"source"));
 if(checks!=17) return 43;
 puts("quota software boundary: 17 checks");return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="m0a2-limit-software-") as temporary:
            executable=Path(temporary)/"probe"
            compiled=subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror","-I",str(repo/"native/mac"),
                "-x","c","-","-o",str(executable)],input=probe,text=True,capture_output=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,"M0A2_CAP2_API "+result.stdout+result.stderr)
            self.assertEqual(result.stdout,"quota software boundary: 17 checks\n")

class TestVectorsBuildPortable(unittest.TestCase):
    def test_actual_build_sequence_and_tool_failures(self):
        import tempfile
        import sys
        from scripts import run_macos_m0a2_vectors as collector
        scenarios=((False,None),(True,None),(True,0),(True,1),(True,2),(True,3))
        for with_source,failure in scenarios:
            with self.subTest(source=with_source,failure=failure),tempfile.TemporaryDirectory(prefix="m0a2-build-model-") as temporary:
                root=Path(temporary);output=root/"logs";output.mkdir();calls=[]
                def tool(argv,deadline):
                    calls.append((argv,deadline))
                    return {"native_exit":9 if failure==len(calls)-1 else 0,"reason":None,"complete":True,
                            "stdout":b"bounded tool model\n","stderr":b""}
                with mock.patch.object(collector.shutil,"which",return_value=sys.executable), \
                     mock.patch.object(collector,"bounded_native",side_effect=tool), \
                     mock.patch.object(collector.time,"clock_gettime_ns",return_value=100_000_000_000):
                    if failure is None:
                        collector.prepare_build(root,root/"build",output,with_source,500_000_000_000)
                    else:
                        with self.assertRaises(RuntimeError):
                            collector.prepare_build(root,root/"build",output,with_source,500_000_000_000)
                self.assertEqual(len(calls),(4 if with_source else 2) if failure is None else failure+1)
                self.assertTrue(all(deadline==190_000_000_000 for _,deadline in calls))
                self.assertIn("-DM0_BUILD_VECTORS_SOURCE=OFF",calls[0][0])
                if len(calls)>1:
                    self.assertEqual(calls[1][0][-4:],["--target","icode_m0a1_vectors_baseline","--parallel","1"])
                if with_source and len(calls)>2:
                    self.assertIn("-DM0_BUILD_VECTORS_SOURCE=ON",calls[2][0])
                self.assertEqual(len(tuple(output.glob("*.json"))),len(calls))
                self.assertFalse((output/"vectors-result.json").exists())
```

### Asset: scripts/run_macos_m0a2_vectors.py

```python
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import unittest
from scripts.run_macos_m0_ci import checked_text,process_groups_binding,run_suite,write_json

def bounded_native(argv,deadline_ns):
    buffers=[bytearray(),bytearray()]
    process=subprocess.Popen(argv,cwd="/",stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    reason=None
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ,0)
            selector.register(process.stderr,selectors.EVENT_READ,1)
            while selector.get_map():
                remaining=(deadline_ns-time.clock_gettime_ns(time.CLOCK_MONOTONIC))/1_000_000_000
                if remaining<=0:
                    reason="timeout"
                    break
                for key,_ in selector.select(min(remaining,0.1)):
                    room=65536-len(buffers[0])-len(buffers[1])
                    chunk=os.read(key.fileobj.fileno(),min(4096,room+1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(chunk)>room:
                        buffers[key.data].extend(chunk[:room])
                        reason="output_exceeded"
                        break
                    else:
                        buffers[key.data].extend(chunk)
                if reason:
                    break
            if not reason:
                try:
                    process.wait(timeout=max(0.001,(deadline_ns-time.clock_gettime_ns(time.CLOCK_MONOTONIC))/1_000_000_000))
                except subprocess.TimeoutExpired:
                    reason="timeout"
    except (TimeoutError,OSError) as error:
        reason="interrupted:"+type(error).__name__
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except OSError:
                # Native root has its own bounded alarm. No cleanup credit here.
                pass
        try:
            process.wait(timeout=2)
        except (subprocess.TimeoutExpired,TimeoutError,OSError):
            reason=reason or "exit_unknown"
        for stream in (process.stdout,process.stderr):
            try:
                stream.close()
            except OSError:
                reason=reason or "pipe_close_unknown"
    return {"native_exit":process.returncode,"reason":reason,
            "stdout":bytes(buffers[0]),"stderr":bytes(buffers[1]),"complete":reason is None}

def prepare_build(repo,build,output,with_source,deadline_ns):
    executable=shutil.which("cmake")
    if executable is None:
        raise RuntimeError("CMake unavailable; not native RED")
    cmake=Path(executable).resolve(strict=True)
    if not cmake.is_file() or not os.access(cmake,os.X_OK):
        raise RuntimeError("actual CMake executable unavailable")
    configuration=[str(cmake),"-S",str(repo/"native/mac"),"-B",str(build),"-DM0_BUILD_SOURCE=ON"]
    commands=[
        ("configure-baseline",configuration+["-DM0_BUILD_VECTORS_SOURCE=OFF"]),
        ("build-baseline",[str(cmake),"--build",str(build),"--target","icode_m0a1_vectors_baseline","--parallel","1"]),
    ]
    if with_source:
        commands.extend([
            ("configure-source",configuration+["-DM0_BUILD_VECTORS_SOURCE=ON"]),
            ("build-source",[str(cmake),"--build",str(build),"--target","icode_m0a1_vectors_source","--parallel","1"]),
        ])
    build_deadline=min(deadline_ns,time.clock_gettime_ns(time.CLOCK_MONOTONIC)+90_000_000_000)
    for name,argv in commands:
        actual=bounded_native(argv,build_deadline)
        (output/(name+".stdout")).write_bytes(actual["stdout"])
        (output/(name+".stderr")).write_bytes(actual["stderr"])
        write_json(output/(name+".json"),{"argv":argv,"native_exit":actual["native_exit"],
            "reason":actual["reason"],"complete":actual["complete"],
            "stdout_sha256":hashlib.sha256(actual["stdout"]).hexdigest(),
            "stderr_sha256":hashlib.sha256(actual["stderr"]).hexdigest()})
        if type(actual["native_exit"]) is not int or actual["native_exit"]!=0 or actual["complete"] is not True or actual["reason"] is not None:
            raise RuntimeError("bounded build failed; not semantic RED: "+name)

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key]=value
    return result

def collect_ledger(manifest):
    path=Path(manifest["root_directory"])
    identity=path.lstat()
    if (not stat.S_ISDIR(identity.st_mode) or identity.st_uid!=0
            or stat.S_IMODE(identity.st_mode)!=0o755):
        raise RuntimeError("protected vectors directory invalid")
    fd=os.open(path/"vectors.jsonl",os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_nlink!=1
                or stat.S_IMODE(before.st_mode)!=0o444 or not 0<before.st_size<=2*1024*1024):
            raise RuntimeError("protected vectors ledger invalid")
        data=bytearray()
        while len(data)<=2*1024*1024:
            chunk=os.read(fd,min(4096,2*1024*1024+1-len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after=os.fstat(fd)
        def stamp(value):
            return tuple(getattr(value,key) for key in
                         ("st_dev","st_ino","st_mode","st_uid","st_nlink","st_size","st_mtime_ns","st_ctime_ns"))
        if len(data)>2*1024*1024 or len(data)!=before.st_size or stamp(before)!=stamp(after):
            raise RuntimeError("vectors ledger changed or exceeded")
    finally:
        os.close(fd)
    raw=bytes(data)
    if hashlib.sha256(raw).hexdigest()!=manifest["ledger_sha256"]:
        raise RuntimeError("vectors ledger digest differs")
    return raw

def run_vectors(repo,build,output,metadata):
    phase=metadata["phase"];variant=metadata["variant"]
    binary=build/("icode_m0a1_vectors_"+variant)
    if binary.is_symlink() or not binary.is_file() or not os.access(binary,os.X_OK):
        raise RuntimeError("native vectors binary missing; never semantic RED")
    binary=binary.resolve(strict=True)
    if binary.parent!=build or not 0<binary.stat().st_size<=16*1024*1024:
        raise RuntimeError("vectors binary escaped/bounds")
    image=binary.read_bytes()
    if len(image)!=binary.stat().st_size:
        raise RuntimeError("vectors binary changed")
    digest=hashlib.sha256(image).hexdigest()
    metadata["binary_sha256"]=digest
    (output/binary.name).write_bytes(image)
    binding=output/"binding";binding.mkdir(mode=0o700)
    metadata["binding_sha256"]=process_groups_binding(repo,build,binary,"vectors_"+variant,binding)
    argv=["/usr/bin/sudo","-n","--","/usr/bin/env","-i","PATH=/usr/bin:/bin",
          str(binary),metadata["candidate_sha"],digest,format(metadata["deadline_ns"],"016x")]
    if time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=metadata["deadline_ns"]:
        raise RuntimeError("shared vectors deadline expired before root launch")
    actual=bounded_native(argv,metadata["deadline_ns"])
    stdout=actual["stdout"];stderr=actual["stderr"]
    (output/"native.stdout.json").write_bytes(stdout)
    (output/"native.stderr.log").write_bytes(stderr)
    metadata.update({k:actual[k] for k in ("native_exit","reason","complete")})
    metadata.update({"stdout_sha256":hashlib.sha256(stdout).hexdigest(),
                     "stderr_sha256":hashlib.sha256(stderr).hexdigest()})
    write_json(output/"metadata.json",metadata)
    if (actual["native_exit"]!=0 or not actual["complete"] or actual["reason"] is not None
            or len(stdout)>512 or len(stderr)>65536 or len(stdout)+len(stderr)>65536 or stderr):
        raise RuntimeError("native vectors infrastructure failure/overflow; never quota RED")
    manifest=json.loads(stdout,object_pairs_hook=unique)
    if (type(manifest) is not dict or set(manifest)!={"version","root_directory","ledger_sha256","cases"}
            or type(manifest["version"]) is not int or manifest["version"]!=1
            or type(manifest["cases"]) is not int or manifest["cases"]!=(2 if phase=="red" else 24)
            or type(manifest["root_directory"]) is not str
            or not re.fullmatch(r"/private/var/icode-m0a1\.[A-Za-z0-9]+",manifest["root_directory"])
            or type(manifest["ledger_sha256"]) is not str
            or not re.fullmatch("[0-9a-f]{64}",manifest["ledger_sha256"])):
        raise RuntimeError("vectors manifest schema/identity invalid")
    raw=collect_ledger(manifest)
    (output/"vectors.audit.jsonl").write_bytes(raw)
    metadata["ledger_sha256"]=hashlib.sha256(raw).hexdigest()
    metadata["root_directory"]=manifest["root_directory"]
    previous=os.environ.get("ICODE_M0A2_EVIDENCE")
    try:
        os.environ["ICODE_M0A2_EVIDENCE"]=str(output)
        spec=importlib.util.spec_from_file_location("m0a2_frozen_observer",repo/"tests/test_macos_m0a2_vectors.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("vectors formal TEST unavailable")
        tests=importlib.util.module_from_spec(spec);spec.loader.exec_module(tests)
        rows=tests.parse_vectors(raw,metadata)
        tests.TestVectorsNative.rows=rows;tests.TestVectorsNative.variant=variant
        formal=run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(tests.TestVectorsNative),
                         output/"native-tests.log")
    finally:
        if previous is None:
            os.environ.pop("ICODE_M0A2_EVIDENCE",None)
        else:
            os.environ["ICODE_M0A2_EVIDENCE"]=previous
    metadata["formal"]={"tests":formal.testsRun,"failures":len(formal.failures),
                        "errors":len(formal.errors),"skipped":len(formal.skipped)}
    write_json(output/"metadata.json",metadata)
    if formal.testsRun!=5 or formal.errors or formal.skipped:
        raise RuntimeError("vectors formal incomplete; never semantic RED")
    if phase=="red":
        observed=tests.operations(rows["baseline_third"])
        if (len(formal.failures)!=1 or formal.failures[0][0]._testMethodName!="test_cap2_quota_semantic"
                or "M0A2_CAP2_REJECTION" not in formal.failures[0][1]
                or len(observed)!=2 or any(e["rc"]<=0 or e["error"] or e["aux"]!=1 for e in observed)
                or any(e["current"]<3 for e in observed)):
            raise RuntimeError("RED must be actual first+third creation and sole quota assertion")
        result="vectors_semantic_RED_confirmed"
    elif not formal.wasSuccessful():
        raise RuntimeError("vectors SOURCE native GREEN failed")
    else:
        result="vectors_GREEN_only"
    total=0
    for path in output.parent.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("export symlink")
        if path.is_file():
            total+=path.stat().st_size
    if total+4096>16*1024*1024 or time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=metadata["deadline_ns"]:
        raise RuntimeError("vectors artifact budget exceeded")
    record={"version":1,"candidate_sha":metadata["candidate_sha"],"arch":metadata["arch"],
            "result":result,"cases":manifest["cases"],"binary_sha256":digest,
            "ledger_sha256":metadata["ledger_sha256"],"binding_sha256":metadata["binding_sha256"],
            "cleanup_scope":"owned_roots_and_observed_direct_parent_reaps","identities_retained":True,
            "M0a2_complete":False,"M0b_complete":False,"M1_enabled":False}
    write_json(output/"vectors-result.json",record)
    return record

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--build-dir",type=Path,required=True)
    parser.add_argument("--output-root",type=Path,required=True)
    parser.add_argument("--phase",choices=("red","both"),required=True)
    parser.add_argument("--expected-arch",choices=("arm64","x86_64"),required=True)
    args=parser.parse_args()
    if sys.platform!="darwin" or os.getuid()==0:
        raise RuntimeError("nonroot native macOS controller required")
    repo=Path(__file__).resolve().parents[1]
    temporary=Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    build=args.build_dir.absolute();root=args.output_root.absolute()
    if (build.parent.resolve()!=temporary or build.is_symlink() or build.exists() or root.is_symlink() or root.exists()
            or root.parent.resolve()!=temporary):
        raise RuntimeError("fresh bounded build/output required")
    root.mkdir(mode=0o700)
    deadline=time.clock_gettime_ns(time.CLOCK_MONOTONIC)+480_000_000_000
    if not 0<deadline<2**64:
        raise RuntimeError("deadline cannot fit fixed uint64 wire")
    def expired(signum,frame):
        raise TimeoutError("shared B480 deadline expired")
    previous_handler=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,480)
    job={"result":"ERROR_or_unaccepted_failure","deadline_ns":deadline,"cleanup":"unknown"}
    try:
        sha=checked_text(["git","rev-parse","HEAD"],repo)
        if not re.fullmatch("[0-9a-f]{40}",sha) or sha!=os.environ["GITHUB_SHA"]:
            raise RuntimeError("candidate differs")
        arch=platform.machine()
        if arch!=args.expected_arch:
            raise RuntimeError("native architecture differs")
        common={"candidate_sha":sha,"arch":arch,"kernel":platform.release(),"deadline_ns":deadline,
            "os_build":checked_text(["/usr/bin/sw_vers","-buildVersion"],repo),
            "os_version":checked_text(["/usr/bin/sw_vers","-productVersion"],repo),
            "run_id":os.environ["GITHUB_RUN_ID"],"job":os.environ["GITHUB_JOB"],
            "run_attempt":os.environ["GITHUB_RUN_ATTEMPT"]}
        if arch=="x86_64" and common["os_version"].split(".")[0]!="15":
            raise RuntimeError("Intel macOS15 required")
        sources=(
            "native/mac/tests/icode_m0a1_driver.c","native/mac/tests/icode_m0a1_fixed_helpers.inc",
            "native/mac/tests/icode_m0a1_unused_identity.inc","native/mac/tests/icode_m0a1_identity_lease.inc",
            "native/mac/tests/icode_m0a1_process_groups_native.c","native/mac/tests/icode_m0a2_vectors.c",
            "native/mac/icode_m0a1_limit.h","native/mac/tests/icode_m0a1_baseline.c",
            "native/mac/icode_m0a1_process_groups.h","native/mac/icode_m0a1_process_groups.c",
            "tests/test_macos_task_quota_probe.py","tests/test_macos_process_groups_native.py",
            "tests/test_macos_process_groups.py","tests/test_macos_m0a2_vectors.py",
            "scripts/run_macos_m0_ci.py","scripts/run_macos_m0a2_vectors.py",
            "native/mac/CMakeLists.txt",".github/workflows/ci.yml",
            "docs/nbl/specs/2026-10-13-macos-task-identity-quota-design.md",
            "docs/nbl/plans/2026-10-13-macos-task-identity-quota-m0.md",
            "docs/nbl/specs/2026-10-14-macos-m0a2-quota-design.md",
            "docs/nbl/plans/2026-10-14-macos-m0a2-vectors.md")
        common["source_hashes"]={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in sources}
        prepare_build(repo,build,root,args.phase=="both",deadline)
        records=[]
        for phase in (("red","green") if args.phase=="both" else ("red",)):
            output=root/phase;output.mkdir(mode=0o700)
            metadata={**common,"phase":phase,"variant":"baseline" if phase=="red" else "source",
                      "result":"ERROR_or_unaccepted_failure","cleanup":"unknown"}
            if phase=="green":
                path="native/mac/icode_m0a1_limit.c"
                metadata["source_hashes"]={**common["source_hashes"],
                    path:hashlib.sha256((repo/path).read_bytes()).hexdigest()}
            write_json(output/"metadata.json",metadata)
            try:
                records.append(run_vectors(repo,build,output,metadata))
                metadata["result"]=records[-1]["result"]
                write_json(output/"metadata.json",metadata)
            except Exception as error:
                metadata.update({"result":"ERROR_or_unaccepted_failure","error":str(error)})
                write_json(output/"metadata.json",metadata)
                raise
        if time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=deadline:
            raise TimeoutError("B deadline expired before combined publication")
        expected=["vectors_semantic_RED_confirmed"]
        if args.phase=="both":
            expected.append("vectors_GREEN_only")
        if [r["result"] for r in records]!=expected:
            raise RuntimeError("combined phase result mismatch")
        job.update({"candidate_sha":sha,"arch":arch,"records":records,
                    "cases":sum(r["cases"] for r in records),
                    "result":"B_vectors_GREEN_only" if args.phase=="both" else "B_TESTOnly_RED_only",
                    "M0a2_complete":False,"M0b_complete":False,"M1_enabled":False})
        write_json(root/"vectors-combined-result.json",job)
        return 0
    except Exception as error:
        job.update({"result":"ERROR_or_unaccepted_failure","error":str(error)})
        write_json(root/"vectors-error.json",job)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous_handler)

if __name__=="__main__":
    raise SystemExit(main())
```

### Asset: Task 2 mechanical driver patch

```diff
*** Begin Patch
*** Update File: native/mac/tests/icode_m0a1_driver.c
@@
     if(owned_child>0) (void)kill((pid_t)owned_child,SIGKILL);
     exit(2);
 }
-static int all_write(int fd,const void *buf,size_t n) {
-    const unsigned char *p=buf;
-    while(n) {
-        ssize_t r=write(fd,p,n);
-        if(r<0 && errno==EINTR) continue;
-        if(r<=0) return errno ? errno : EIO;
-        p+=r; n-=(size_t)r;
-    }
-    return 0;
-}
-static int all_read(int fd,void *buf,size_t n) {
-    unsigned char *p=buf;
-    while(n) {
-        ssize_t r=read(fd,p,n);
-        if(r<0 && errno==EINTR) continue;
-        if(r<=0) return r==0 ? EPIPE : errno;
-        p+=r; n-=(size_t)r;
-    }
-    return 0;
-}
-static int read_record(int fd,void *buf,size_t n) {
-    struct pollfd p={.fd=fd,.events=POLLIN};
-    int r;
-    do { r=poll(&p,1,11000); } while(r<0 && errno==EINTR);
-    if(r<=0) return r==0 ? ETIMEDOUT : errno;
-    return all_read(fd,buf,n); /* Fixed writer plus child alarm bounds read. */
-}
-static int hex_string(const char *s,size_t n) {
-    if(strlen(s)!=n) return 0;
-    for(size_t i=0;i<n;i++)
-        if(!((s[i]>='0' && s[i]<='9') || (s[i]>='a' && s[i]<='f'))) return 0;
-    return 1;
-}
-static int numeric(const char *s,int low,int high) {
-    char *end=NULL; errno=0; long v=strtol(s,&end,10);
-    if(errno || end==s || *end || v<low || v>high) die("numeric");
-    return (int)v;
-}
-static int acl_safe(const char *path,struct stat *st) {
-    filesec_t sec=filesec_init();
-    if(!sec) return errno ? errno : ENOMEM;
-    int e=0,present=0;
-    if(lstatx_np(path,st,sec)<0) e=errno;
-    if(!e && filesec_query_property(sec,FILESEC_ACL,&present)<0) e=errno;
-    acl_t acl=NULL;
-    if(!e && present) {
-        if(filesec_get_property(sec,FILESEC_ACL,&acl)<0) e=errno;
-        if(!e && (!acl || acl==(acl_t)_FILESEC_REMOVE_ACL || acl_valid(acl)<0)) e=EINVAL;
-        acl_permset_mask_t read_mask=ACL_READ_DATA|ACL_EXECUTE|ACL_READ_ATTRIBUTES|
-            ACL_READ_EXTATTRIBUTES|ACL_READ_SECURITY|ACL_SYNCHRONIZE;
-        for(unsigned i=0;!e && i<=ACL_MAX_ENTRIES;i++) {
-            acl_entry_t entry; errno=0;
-            int r=acl_get_entry(acl,i==0 ? ACL_FIRST_ENTRY : ACL_NEXT_ENTRY,&entry);
-            if(r<0 && errno==EINVAL) break; /* Valid ACL, validated iterator exhausted. */
-            if(r!=0 || i==ACL_MAX_ENTRIES) { e=EPROTO; break; }
-            acl_tag_t tag; acl_permset_mask_t permissions=0;
-            if(acl_get_tag_type(entry,&tag)<0 || acl_get_permset_mask_np(entry,&permissions)<0) {
-                e=errno; break;
-            }
-            if(tag!=ACL_EXTENDED_ALLOW && tag!=ACL_EXTENDED_DENY) { e=EPROTO; break; }
-            /* Conservative: no principal may gain mutation rights through an ALLOW ACE. */
-            if(tag==ACL_EXTENDED_ALLOW && (permissions&~read_mask)) { e=EPERM; break; }
-        }
-    }
-    if(acl && acl!=(acl_t)_FILESEC_REMOVE_ACL && acl_free(acl)<0 && !e) e=errno;
-    filesec_free(sec);
-    return e;
-}
-static int secure_chain(const char *path) {
-    char copy[PATH_MAX];
-    if(path[0]!='/' || strlen(path)>=sizeof(copy)) return EINVAL;
-    struct stat root;
-    int e=getuid()==0 ? acl_safe("/",&root) : (lstat("/",&root)<0 ? errno : 0);
-    if(e) return e;
-    if(root.st_uid!=0 || (root.st_mode&022) || !S_ISDIR(root.st_mode)) return EPERM;
-    strcpy(copy,path);
-    for(char *p=copy+1;;p++) {
-        if(*p!='/' && *p) continue;
-        char saved=*p; *p=0; struct stat st;
-        e=getuid()==0 ? acl_safe(copy,&st) : (lstat(copy,&st)<0 ? errno : 0);
-        if(e) return e;
-        if(st.st_uid!=0 || (st.st_mode&022) || S_ISLNK(st.st_mode)) return EPERM;
-        *p=saved; if(!saved) break;
-    }
-    return 0;
-}
-static void self_path(void) {
-    char buf[PATH_MAX]; uint32_t n=sizeof(buf);
-    if(_NSGetExecutablePath(buf,&n)!=0 || !realpath(buf,image)) die("self-path");
-    strcpy(directory,image);
-    char *slash=strrchr(directory,'/');
-    if(!slash) die("self-directory");
-    *slash=0;
-}
-static int hash_fd(int fd,char out[65],size_t bound) {
-    CC_SHA256_CTX ctx; unsigned char buf[65536],digest[CC_SHA256_DIGEST_LENGTH];
-    if(lseek(fd,0,SEEK_SET)<0 || CC_SHA256_Init(&ctx)!=1) return EIO;
-    size_t total=0;
-    for(;;) {
-        ssize_t n=read(fd,buf,sizeof(buf));
-        if(n<0 && errno==EINTR) continue;
-        if(n<0) return errno;
-        if(!n) break;
-        if((size_t)n>bound-total) return EFBIG;
-        total+=(size_t)n;
-        if(CC_SHA256_Update(&ctx,buf,(CC_LONG)n)!=1) return EIO;
-    }
-    if(CC_SHA256_Final(digest,&ctx)!=1) return EIO;
-    for(size_t i=0;i<sizeof(digest);i++) sprintf(out+2*i,"%02x",digest[i]);
-    out[64]=0; return 0;
-}
-static int protected_image(const char *expected) {
-    const char prefix[]="/private/var/icode-m0a1.";
-    if(strncmp(directory,prefix,sizeof(prefix)-1)!=0) return EPERM;
-    int e=secure_chain(image);
-    if(e) return e;
-    int fd=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
-    if(fd<0) return errno;
-    struct stat st; char digest[65];
-    e=fstat(fd,&st)<0 ? errno : (!S_ISREG(st.st_mode) ? EINVAL : 0);
-    if(!e) e=hash_fd(fd,digest,MAX_IMAGE);
-    if(close(fd)<0 && !e) e=errno;
-    if(!e && strcmp(digest,expected)) e=EPERM;
-    return e;
-}
-static void create_file(const char *name,const void *data,size_t n,mode_t mode) {
-    char path[PATH_MAX];
-    if(snprintf(path,sizeof(path),"%s/%s",directory,name)>=(int)sizeof(path)) die("path");
-    int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
-    if(fd<0 || all_write(fd,data,n) || fchmod(fd,mode)<0 || fsync(fd)<0) die("create-file");
-    if(close(fd)<0) die("close-file");
-}
-static void prepare_image(const char *expected) {
-    int in=open(image,O_RDONLY|O_NOFOLLOW|O_CLOEXEC); struct stat st;
-    if(in<0 || fstat(in,&st)<0 || !S_ISREG(st.st_mode) || st.st_size<=0 || st.st_size>MAX_IMAGE)
-        die("source-image");
-    struct mach_header_64 mh;
-    if(all_read(in,&mh,sizeof(mh)) || mh.magic!=MH_MAGIC_64) die("native-Mach-O");
-#if defined(__arm64__)
-    if(mh.cputype!=CPU_TYPE_ARM64) die("Mach-O-arm64");
-#elif defined(__x86_64__)
-    if(mh.cputype!=CPU_TYPE_X86_64) die("Mach-O-x86_64");
-#else
-#error Unsupported native macOS architecture
-#endif
-    char observed[65];
-    if(hash_fd(in,observed,MAX_IMAGE) || strcmp(observed,expected)) die("source-hash");
-    if(secure_chain("/private/var")) die("protected-parent");
-    strcpy(directory,"/private/var/icode-m0a1.XXXXXX");
-    if(!mkdtemp(directory) || chmod(directory,0755)<0 || secure_chain(directory)) die("fixture-directory");
-    char target[PATH_MAX];
-    if(snprintf(target,sizeof(target),"%s/probe",directory)>=(int)sizeof(target)) die("copy-path");
-    int out=open(target,O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
-    if(out<0 || lseek(in,0,SEEK_SET)<0) die("copy-open");
-    unsigned char buf[65536]; size_t copied=0;
-    for(;;) {
-        ssize_t n=read(in,buf,sizeof(buf));
-        if(n<0 && errno==EINTR) continue;
-        if(n<0) die("copy-read");
-        if(!n) break;
-        if((size_t)n>MAX_IMAGE-copied || all_write(out,buf,(size_t)n)) die("copy-bound");
-        copied+=(size_t)n;
-    }
-    if(hash_fd(out,observed,MAX_IMAGE) || strcmp(observed,expected) ||
-       fchmod(out,0555)<0 || fsync(out)<0) die("protected-copy-hash");
-    if(close(in)<0 || close(out)<0) die("copy-close");
-    strcpy(image,target); strcpy(binary_hash,expected);
-    create_file("allowed","A",1,0444); create_file("denied","D",1,0444);
-    const char bad[]="(version 1)(";
-    create_file("bad.sb",bad,sizeof(bad)-1,0444);
-    char profile[4096];
-    int n=snprintf(profile,sizeof(profile),
-        "(version 1)\n(deny default)\n(allow process-exec)\n(allow process-fork)\n"
-        "(allow signal (target same-sandbox))\n(allow process-info* (target same-sandbox))\n"
-        "(allow sysctl-read)\n"
-        "(allow file-read-metadata file-test-existence (path-ancestors \"%s\"))\n"
-        "(allow file-read* file-test-existence (literal \"/\") "
-        "(subpath \"/usr/lib\") (subpath \"/System/Library\") "
-        "(literal \"%s\") (literal \"%s/profile.sb\") (literal \"%s/allowed\") "
-        "(literal \"%s/not-created\"))\n",
-        image,image,directory,directory,directory);
-    if(n<=0 || n>=(int)sizeof(profile)) die("profile-bound");
-    create_file("profile.sb",profile,(size_t)n,0444);
-}
-#include "icode_m0a1_identity_lease.inc"
-static void send_gate(unsigned phase,int error) {
-    struct gate_record r; memset(&r,0,sizeof(r));
-    r.magic=MAGIC; r.version=1; r.length=sizeof(r); r.phase=phase;
-    r.error=error; r.pid=getpid(); r.uid=getuid(); r.euid=geteuid();
-    r.gid=getgid(); r.egid=getegid(); gid_t g=0; int n=m0_process_getgroups(1,&g);
-    r.groups=n<0 ? UINT32_MAX : (uint32_t)n; r.group=g;
-    struct rlimit l;
-    if(getrlimit(RLIMIT_NPROC,&l)<0) { r.phase=FAILED; r.error=errno; }
-    else { r.current=l.rlim_cur; r.maximum=l.rlim_max; }
-    r.canary_errno=canary_errno; r.canary_allowed=canary_allowed;
-    if(all_write(3,&r,sizeof(r))) _exit(93);
-}
-/* M0A1_DIAGNOSTIC_EMITTER_BEGIN */
-static void emit_diagnostic(unsigned index,unsigned stage,int error,int detail,int result) {
-    int saved=errno;
-    char row[192];
-    int n=snprintf(row,sizeof(row),
-        "M0A1_DIAG version=1 case_index=%u stage=%u error=%d detail=%d result=%d\n",
-        index,stage,error,detail,result);
-    if(n>0 && (size_t)n<sizeof(row)) (void)fwrite(row,1,(size_t)n,stderr);
-    errno=saved;
-}
-static void setup_fail(unsigned index,unsigned stage,int error,int detail,int code) {
-    sigset_t blocked;
-    /* This path must exit: never restore a mask that could deliver pending SIGPIPE. */
-    if(sigemptyset(&blocked)==0 && sigaddset(&blocked,SIGPIPE)==0 &&
-       sigprocmask(SIG_BLOCK,&blocked,NULL)==0)
-        emit_diagnostic(index,stage,error,detail,code);
-    _exit(code);
-}
-/* M0A1_DIAGNOSTIC_EMITTER_END */
-/* M0A1_GATE_OBSERVER_BEGIN */
-static void emit_gate_observation(unsigned index,unsigned slot,uint32_t expected_uid,
-                                  int received,const struct gate_record *r) {
-    int saved=errno;
-    char row[512],group[11];
-    int n;
-    if(!received) {
-        n=snprintf(row,sizeof(row),
-            "M0A1_GATE_DIAG format_version=1 case_index=%u slot=%u received=0 "
-            "raw_magic=unknown wire_version=unknown length=unknown pid=unknown "
-            "phase=unknown error=unknown expected_uid=%" PRIu32 " uid=unknown euid=unknown "
-            "gid=unknown egid=unknown groups=unknown group_observed=0 group=unknown\n",
-            index,slot,expected_uid);
-    } else {
-        /* group is meaningful only when the existing wire reports one group. */
-        const char *observed_group="unknown";
-        if(r->groups==1) {
-            int g=snprintf(group,sizeof(group),"%" PRIu32,r->group);
-            if(g>0 && (size_t)g<sizeof(group)) observed_group=group;
-        }
-        n=snprintf(row,sizeof(row),
-            "M0A1_GATE_DIAG format_version=1 case_index=%u slot=%u received=1 "
-            "raw_magic=%" PRIu32 " wire_version=%" PRIu32 " length=%" PRIu32
-            " pid=%" PRId32 " phase=%" PRIu32 " error=%" PRId32
-            " expected_uid=%" PRIu32 " uid=%" PRIu32 " euid=%" PRIu32
-            " gid=%" PRIu32 " egid=%" PRIu32 " groups=%" PRIu32
-            " group_observed=%d group=%s\n",
-            index,slot,r->magic,r->version,r->length,r->pid,r->phase,r->error,
-            expected_uid,r->uid,r->euid,r->gid,r->egid,r->groups,
-            r->groups==1,observed_group);
-    }
-    if(n>0 && (size_t)n<sizeof(row)) (void)fwrite(row,1,(size_t)n,stderr);
-    errno=saved;
-}
-/* M0A1_GATE_OBSERVER_END */
-static void worker_fail(int error) { send_gate(FAILED,error); _exit(94); }
-static void trampoline(unsigned index,uid_t uid,const char *hash) {
-    if(getuid()!=0 || protected_image(hash)) worker_fail(EPERM);
-    const struct case_def *c=&cases[index]; gid_t gid=uid;
-    int e=m0_apply_limit(1,c->quota);
-    if(e) worker_fail(e);
-    if(setgroups(1,&gid)<0 || setgid(gid)<0 || setuid(uid)<0) worker_fail(errno);
-    e=m0_process_credentials(uid);
-    if(e) worker_fail(e);
-    e=m0_check_limit(1,c->quota);
-    if(e) worker_fail(e);
-    send_gate(CONFIGURED,0);
-    char idx[16],id[16],profile[PATH_MAX];
-    snprintf(idx,sizeof(idx),"%u",index); snprintf(id,sizeof(id),"%u",uid);
-    char *env[]={"PATH=/usr/bin:/bin",NULL};
-    char *args[]={image,"G",idx,id,(char *)hash,NULL};
-    if(!c->sandbox) { execve(image,args,env); worker_fail(errno); }
-    if(snprintf(profile,sizeof(profile),"%s/%s",directory,c->fault==1 ? "bad.sb" : "profile.sb")
-       >=(int)sizeof(profile)) worker_fail(ENAMETOOLONG);
-    char *sandbox_args[]={"/usr/bin/sandbox-exec","-f",profile,image,"G",idx,id,(char *)hash,NULL};
-    execve("/usr/bin/sandbox-exec",sandbox_args,env); worker_fail(errno);
-}
-static int canaries(int sandbox) {
-    char path[PATH_MAX]; snprintf(path,sizeof(path),"%s/allowed",directory);
-    int f=open(path,O_RDONLY|O_NOFOLLOW);
-    if(f<0) return errno;
-    char value=0;
-    int e=all_read(f,&value,1);
-    if(close(f)<0 && !e) e=errno;
-    if(e || value!='A') return e ? e : EPROTO;
-    canary_allowed=1;
-    snprintf(path,sizeof(path),"%s/denied",directory); errno=0;
-    f=open(path,O_RDONLY|O_NOFOLLOW); canary_errno=f<0 ? errno : 0;
-    if(f>=0) {
-        e=all_read(f,&value,1);
-        if(close(f)<0 && !e) e=errno;
-        if(e || value!='D') return e ? e : EPROTO;
-    }
-    return (sandbox && canary_errno!=EPERM && canary_errno!=EACCES) ||
-           (!sandbox && canary_errno) ? EPROTO : 0;
+#include "icode_m0a1_fixed_helpers.inc"
+#include "icode_m0a1_identity_lease.inc"
+static void send_gate(unsigned phase,int error) {
+    struct gate_record r; memset(&r,0,sizeof(r));
+    r.magic=MAGIC; r.version=1; r.length=sizeof(r); r.phase=phase;
+    r.error=error; r.pid=getpid(); r.uid=getuid(); r.euid=geteuid();
+    r.gid=getgid(); r.egid=getegid(); gid_t g=0; int n=m0_process_getgroups(1,&g);
+    r.groups=n<0 ? UINT32_MAX : (uint32_t)n; r.group=g;
+    struct rlimit l;
+    if(getrlimit(RLIMIT_NPROC,&l)<0) { r.phase=FAILED; r.error=errno; }
+    else { r.current=l.rlim_cur; r.maximum=l.rlim_max; }
+    r.canary_errno=canary_errno; r.canary_allowed=canary_allowed;
+    if(all_write(3,&r,sizeof(r))) _exit(93);
+}
+/* M0A1_DIAGNOSTIC_EMITTER_BEGIN */
+static void emit_diagnostic(unsigned index,unsigned stage,int error,int detail,int result) {
+    int saved=errno;
+    char row[192];
+    int n=snprintf(row,sizeof(row),
+        "M0A1_DIAG version=1 case_index=%u stage=%u error=%d detail=%d result=%d\n",
+        index,stage,error,detail,result);
+    if(n>0 && (size_t)n<sizeof(row)) (void)fwrite(row,1,(size_t)n,stderr);
+    errno=saved;
+}
+static void setup_fail(unsigned index,unsigned stage,int error,int detail,int code) {
+    sigset_t blocked;
+    /* This path must exit: never restore a mask that could deliver pending SIGPIPE. */
+    if(sigemptyset(&blocked)==0 && sigaddset(&blocked,SIGPIPE)==0 &&
+       sigprocmask(SIG_BLOCK,&blocked,NULL)==0)
+        emit_diagnostic(index,stage,error,detail,code);
+    _exit(code);
+}
+/* M0A1_DIAGNOSTIC_EMITTER_END */
+/* M0A1_GATE_OBSERVER_BEGIN */
+static void emit_gate_observation(unsigned index,unsigned slot,uint32_t expected_uid,
+                                  int received,const struct gate_record *r) {
+    int saved=errno;
+    char row[512],group[11];
+    int n;
+    if(!received) {
+        n=snprintf(row,sizeof(row),
+            "M0A1_GATE_DIAG format_version=1 case_index=%u slot=%u received=0 "
+            "raw_magic=unknown wire_version=unknown length=unknown pid=unknown "
+            "phase=unknown error=unknown expected_uid=%" PRIu32 " uid=unknown euid=unknown "
+            "gid=unknown egid=unknown groups=unknown group_observed=0 group=unknown\n",
+            index,slot,expected_uid);
+    } else {
+        /* group is meaningful only when the existing wire reports one group. */
+        const char *observed_group="unknown";
+        if(r->groups==1) {
+            int g=snprintf(group,sizeof(group),"%" PRIu32,r->group);
+            if(g>0 && (size_t)g<sizeof(group)) observed_group=group;
+        }
+        n=snprintf(row,sizeof(row),
+            "M0A1_GATE_DIAG format_version=1 case_index=%u slot=%u received=1 "
+            "raw_magic=%" PRIu32 " wire_version=%" PRIu32 " length=%" PRIu32
+            " pid=%" PRId32 " phase=%" PRIu32 " error=%" PRId32
+            " expected_uid=%" PRIu32 " uid=%" PRIu32 " euid=%" PRIu32
+            " gid=%" PRIu32 " egid=%" PRIu32 " groups=%" PRIu32
+            " group_observed=%d group=%s\n",
+            index,slot,r->magic,r->version,r->length,r->pid,r->phase,r->error,
+            expected_uid,r->uid,r->euid,r->gid,r->egid,r->groups,
+            r->groups==1,observed_group);
+    }
+    if(n>0 && (size_t)n<sizeof(row)) (void)fwrite(row,1,(size_t)n,stderr);
+    errno=saved;
+}
+/* M0A1_GATE_OBSERVER_END */
+static void worker_fail(int error) { send_gate(FAILED,error); _exit(94); }
+static void trampoline(unsigned index,uid_t uid,const char *hash) {
+    if(getuid()!=0 || protected_image(hash)) worker_fail(EPERM);
+    const struct case_def *c=&cases[index]; gid_t gid=uid;
+    int e=m0_apply_limit(1,c->quota);
+    if(e) worker_fail(e);
+    if(setgroups(1,&gid)<0 || setgid(gid)<0 || setuid(uid)<0) worker_fail(errno);
+    e=m0_process_credentials(uid);
+    if(e) worker_fail(e);
+    e=m0_check_limit(1,c->quota);
+    if(e) worker_fail(e);
+    send_gate(CONFIGURED,0);
+    char idx[16],id[16],profile[PATH_MAX];
+    snprintf(idx,sizeof(idx),"%u",index); snprintf(id,sizeof(id),"%u",uid);
+    char *env[]={"PATH=/usr/bin:/bin",NULL};
+    char *args[]={image,"G",idx,id,(char *)hash,NULL};
+    if(!c->sandbox) { execve(image,args,env); worker_fail(errno); }
+    if(snprintf(profile,sizeof(profile),"%s/%s",directory,c->fault==1 ? "bad.sb" : "profile.sb")
+       >=(int)sizeof(profile)) worker_fail(ENAMETOOLONG);
+    char *sandbox_args[]={"/usr/bin/sandbox-exec","-f",profile,image,"G",idx,id,(char *)hash,NULL};
+    execve("/usr/bin/sandbox-exec",sandbox_args,env); worker_fail(errno);
 }
 static void gate(unsigned index,uid_t uid,const char *hash) {
     const struct case_def *c=&cases[index]; int e=protected_image(hash);
*** End Patch
```

### Asset: Task 2 mechanical W1 patch

```diff
*** Begin Patch
*** Update File: native/mac/tests/icode_m0a1_process_groups_native.c
@@
 }
 #include "icode_m0a1_identity_lease.inc"
 /* Include dependencies are fixed above; same finite lease namespace as original TEST. */
-static int supplementary_free(gid_t gid) {
-    pid_t pids[MAX_PIDS];int n=proc_listallpids(pids,sizeof(pids));
-    if(n<=0 || n>=MAX_PIDS) return -1;
-    for(int i=0;i<n;i++) {
-        if(pids[i]<=0) continue;
-        struct kinfo_proc info;memset(&info,0,sizeof(info));size_t size=sizeof(info);
-        int mib[]={CTL_KERN,KERN_PROC,KERN_PROC_PID,pids[i]};
-        if(sysctl(mib,4,&info,&size,NULL,0)<0 || size!=sizeof(info)) {
-            errno=0;
-            if(kill(pids[i],0)<0 && errno==ESRCH) continue;
-            return -1;
-        }
-        int count=info.kp_eproc.e_ucred.cr_ngroups;
-        if(count<0 || count>NGROUPS) return -1;
-        for(int j=0;j<count;j++) if(info.kp_eproc.e_ucred.cr_groups[j]==gid) return 0;
-    }
-    return 1;
-}
-static uid_t reserve_unused_id(int leases) {
-    for(unsigned attempt=0;attempt<UID_COUNT;attempt++) {
-        uid_t uid=reserve_uid(leases,candidate);
-        int empty=supplementary_free((gid_t)uid);
-        if(empty<0) die("supplementary-snapshot");
-        int active=process_count(uid);
-        if(active<0) die("identity-process-snapshot");
-        if(empty==1 && active==0) return uid;
-        /* A collision burns its permanent lease; no identity is retried or cleaned. */
-    }
-    errno=ENOSPC;die("supplementary-exhausted");return 0;
-}
+#include "icode_m0a1_unused_identity.inc"
 struct observation {
     uint32_t uid,euid,gid,egid,group0,group1;
     int32_t pid,count,count_errno,capacity,read,read_errno,predicate_attempted,predicate,image_stage;
*** End Patch
```

### Asset: Task 2 old A source hashes patch

```diff
*** Begin Patch
*** Update File: scripts/run_macos_m0_ci.py
@@
             "native/mac/icode_m0a1_process_groups.h",
             "native/mac/icode_m0a1_process_groups.c",
             "native/mac/tests/icode_m0a1_identity_lease.inc",
+            "native/mac/tests/icode_m0a1_fixed_helpers.inc",
+            "native/mac/tests/icode_m0a1_unused_identity.inc",
             "native/mac/tests/icode_m0a1_process_groups_native.c",
             "tests/test_macos_process_groups_native.py",
             "tests/test_macos_process_groups.py",
*** End Patch
```

### Asset: Task 2 CMake patch

```diff
*** Begin Patch
*** Update File: native/mac/CMakeLists.txt
@@
   endif()
   m0_target(icode_m0a1_source icode_m0a1_limit.c)
 endif()
+
+option(M0_BUILD_VECTORS_SOURCE "Build cap2 SOURCE only after genuine native RED" OFF)
+function(m0_vectors_target name implementation)
+  add_executable(${name} tests/icode_m0a2_vectors.c icode_m0a1_process_groups.c ${implementation})
+  target_include_directories(${name} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
+  set_target_properties(${name} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED YES C_EXTENSIONS NO)
+  target_compile_options(${name} PRIVATE -Wall -Wextra -Werror -Wno-deprecated-declarations)
+endfunction()
+m0_vectors_target(icode_m0a1_vectors_baseline tests/icode_m0a1_baseline.c)
+if(M0_BUILD_VECTORS_SOURCE)
+  if(NOT M0_BUILD_SOURCE OR NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/icode_m0a1_limit.c")
+    message(FATAL_ERROR "M0a2 SOURCE unavailable; not semantic RED")
+  endif()
+  m0_vectors_target(icode_m0a1_vectors_source icode_m0a1_limit.c)
+endif()
*** End Patch
```

### Asset: Task 2 CI TEST-only patch

```diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@
             ${{ runner.temp }}/icode-m0a1-source-build.log
             ${{ runner.temp }}/icode-m0a1-build/icode_m0a1_baseline
             ${{ runner.temp }}/icode-m0a1-build/icode_m0a1_source
+
+  macos-m0a2-vectors:
+    name: M0a2 fixed vectors and genuine cap2 RED (${{ matrix.os }})
+    needs: macos-m0a1-finite
+    if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')
+    runs-on: ${{ matrix.os }}
+    timeout-minutes: 10
+    permissions:
+      contents: read
+    env:
+      M0A2_SOURCE: "0"
+    strategy:
+      fail-fast: false
+      matrix:
+        include:
+          - os: macos-latest
+            arch: arm64
+          - os: macos-15-intel
+            arch: x86_64
+    steps:
+      - name: Check out exact candidate
+        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
+        with:
+          persist-credentials: false
+          submodules: recursive
+      - name: Set up nonroot Python
+        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
+        with:
+          python-version: "3.11"
+      - name: Targeted SOURCE software contract
+        if: env.M0A2_SOURCE == '1'
+        shell: bash
+        run: ICODE_M0A2_LIMIT_SOFTWARE=1 python -m unittest discover -s tests -p test_macos_m0a2_vectors.py -v
+      - name: Shared B deadline and strict native oracle
+        shell: bash
+        run: >-
+          python -m scripts.run_macos_m0a2_vectors
+          --build-dir "$RUNNER_TEMP/icode-m0a2-build"
+          --output-root "$RUNNER_TEMP/icode-m0a2-vectors"
+          --phase "${{ env.M0A2_SOURCE == '1' && 'both' || 'red' }}"
+          --expected-arch "${{ matrix.arch }}"
+      - name: Preserve bounded candidate evidence
+        if: always()
+        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
+        with:
+          name: m0a2-vectors-${{ github.sha }}-${{ matrix.arch }}-${{ github.run_attempt }}
+          if-no-files-found: error
+          retention-days: 14
+          path: |
+            ${{ runner.temp }}/icode-m0a2-vectors/
*** End Patch
```

### Asset: Task 3 cap2 SOURCE patch

```diff
*** Begin Patch
*** Update File: native/mac/icode_m0a1_limit.c
@@
 }
 int m0_apply_limit(rlim_t cap,int enabled) {
     if(!enabled) return 0;
-    if(cap!=1) return EINVAL; /* Explicitly a cap1-only slice. */
+    if(cap!=1 && cap!=2) return EINVAL; /* cap1/cap2 only; cap4 awaits race RED. */
     struct rlimit target={.rlim_cur=cap,.rlim_max=cap};
     if(setrlimit(RLIMIT_NPROC,&target)<0) return errno;
     return m0_check_limit(cap,1);
*** End Patch
```

### Asset: Task 3 CI candidate phase patch

```diff
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@
     permissions:
       contents: read
     env:
-      M0A2_SOURCE: "0"
+      M0A2_SOURCE: "1"
     strategy:
       fail-fast: false
       matrix:
*** End Patch
```

## 9. 冻结资产和投影摘要

摘要算法为 SHA256，fence正文保留末LF。以下为实际本文资产重新提取所得，不是已落地源码的摘要。projection patch已在RAM针对当前完整输入逐一精确匹配并投影，不执行写入。

|资产|行数|SHA256|
|---|---:|---|
|fixed_helpers.inc|203|de74f6b77a9d91fd3d9fdf2801adfe4dc8685ff685480a7b09bb0e9c58f10546|
|unused_identity.inc|30|a6916f73f63275ea43e1653a0d9ced53b4daceb594846a795cedd24b13035619|
|icode_m0a2_vectors.c|675|c65a88c3f416948ed4df14639870885784c64832975dfe333a620329eea530c2|
|test_macos_m0a2_vectors.py|990|f924880a575c6e11aebac1fdbaa1d114691e1fe88c59fb1093a22e18b510285e|
|run_macos_m0a2_vectors.py|326|9aed0af65ef16a69d8f55f929238593038a190b0cbf9f863173af57e8fae648e|
|Task2 driver patch|390|2dff4bbb3a68ca7aff0b8cbc27eee148da92730a9aa23f7953fe48b8af0c0e2c|
|Task2 W1 patch|41|2e9a002e6cefedac3ef2dd3b92a8f0325a447fadebab542054daa35fad0f9b8c|
|Task2 A摘要patch|12|5f6616323336a4e4eb7e38159f7853c052db0bb1db5091b5b7a42b5ebaaf8777|
|Task2 CMake patch|22|b02c3fb0beb2bd2503041445504b4299038dc8917c6699ad0c3394121c6c2d3c|
|Task2 CI patch|57|ea5abe399d4c515d61c01d258c00b1f20e6ba9a928befb577ff08c0c85be1db7|
|Task3 limit patch|12|ac8533c71cf9772491650b48cc17d87c31e612415854a2953aed7c1113427786|
|Task3 CI patch|12|74e3c5d059c580ebcd456425d825c101473adb75bfe4b3554edab14dfddd5f3e|

|完整投影文件|行数|SHA256|
|---|---:|---|
|driver.c|511|141bedc63deadad332eb1d46a474d24d68c837248fd89247d04bea4819f1bf9a|
|W1native.c|389|ebe6071bd7b9e26c4948d1bbc87f496a149766e352231a5c0a5675d9f45194aa|
|run_macos_m0_ci.py|429|823c8b219ed72040cab2f1029c37c181b7ded81529ac14f338d4c1e8f7359814|
|CMakeLists.txt|42|dac5e951d417733f4de6350591c42c02ba5534e2a3d770b4f04ccaffc1cb39fa|
|CI TEST-only|2496|25ce291318d265335d8ec0a1b54050dd49adcf70e8229dc96c8a49f8702f8fd1|
|limit.c SOURCE cap2|16|a5fb47b059c9a877089d46284fe938ae6131198e9b5b3c24e8522b6e43daf001|
|CI SOURCE candidate|2496|5e432dd879c4e4fb78e3fa57cc7f627bf7d8b9525c575041e6b46edab8eb34c5|

静态诊断：本文实际提取的两Python资产AST通过，15 TEST方法分类为native5、portable5、collector1、deadline1、mechanical1、limit1、build1。此次匿名stdin执行实际本文TEST资产的portable5方法，Ran 5 tests in 1.624s / OK，包含113删除负控。历史匿名C clock实际函数17边界检查通过仍仅软件信用；真实collector44/build6/quota17及完整Darwin源码尚未执行，不将资产覆盖数量冒称运行结果。其它11fence字节及7完整投影摘要不变。

## 10. 研究、自检及停止线

采纳：批准DESIGN§8固定Apple XNU fork1/realUID/RLIMIT_NPROC、reap释放/公共groups，以及固定Codex提交leader退出与descendant pipe/timeout分离机制；借机制不复制APSL实现。暂缓C/D/E/cap4/M0b；不适配目录账号、root代非root、产品canaryallow、polling代hardquota。固定主源URL/版本/许可沿批准DESIGN，不伪装新运行。研究不代测试。

【架构级自检报告】
✅ 语法/编译：Python资产AST与最小匿名C clock软件诊断通过；完整Darwin编译待未来TEST/线上，未冒称通过。
✅ 依赖/调用链：两个include全变量/header依赖、同namespace、旧A/W1 exactinverse明确。
✅ 逻辑/边界：24+2计数、首byte、cap2唯一assertRED、READY后freshNOTE_EXEC、480秒不续租。
✅ 异常处理：timeout/output/manifest/ledger/unknown隔离，失败不发布成功；不虚称整树回收。
✅ 关联模块：controller/TEST/CMake/CI全资产成对，旧wire/profile/formal/classification不改。
✅ 兼容安全：旧W1 CPU10保留；仅cap2待不同SOURCE，cap4/C/D/E/M0b/M1阻断。
✅ 可运行性：完整可执行资产/命令；未运行native/CI，不授100%原生信用。

执行模式：串行独立TEST→真实RED→不同SOURCE→实际双审→root线上待验候选。当前STOP等待root全文及freshSPEC→不同QUALITY；不调用执行技能、不stage/commit/push、不建worktree分支。

## 附录 E：Task2 旧 groups TEST 契约最小兼容修订（PLAN ONLY）

此附录仅修订计划，不修改实际 TEST/SOURCE/CI/Git。历史主体为2998行 SHA256 4ee5d9f0fc77f82545547c2c921e992730904638a8b490859d6487d1c555d1f9；它仅比21cbb历史少EOF空行，原12资产字节不变。本附录可按此标题分割并删除，严格恢复4ee5完整原文及其EOF单LF。原12资产及7patch均不改，不能以本附录授权quota SOURCE/cap2/CIenv1。

root实际回报：独立TEST作者已经精确落地原Task2十路径，新15默认9PASS/6skip；opt-in9PASS/1个M0A2_CAP2_API assertionFAIL/5native skip，root46c017/5f98af独立一致。这是软件结果，不是双Mac cap2第三fork真实RED，原Task3仍阻断。新增关联回归f52fd8与独立actualTEST review复现：旧 groups TEST13方法11PASS/2FAIL/0ERROR/0skip。两失败均为旧软件提取合同未认识已批准机械include，不是quota产品语义回归。root实际 sequential-thinking db72e9三步accepted用于本最小修订；仅记录回报，不冒称本作者再次调用。

### E.1 根因、最小复用和不变边界

1. TestW1MechanicalLeaseExtraction.test_driver_inverse_is_exact_original，原182行：旧测试只展开identity_lease，此时摘要为eeb7d00820b0ca946cd1a763733a7af4b864adabfe467e4a86b1c73b0cb8fcba，不等于原a65f067ec9c6b32eb3bb7cc7afd803fe465d02273b5484561b237db59c31f673。driver实际只有fixed_helpers及lease，无unused_identity。fixed_helpers含原前缀加尾部canaries，整段原位展开会改变顺序，不能恢复原hash。
2. TestW1LeaseSnapshotSoftware.test_actual_reservation_unknown_collision_and_success，原192行：W1当前仅include unused_identity，直接regex inline函数found=0，不等于原len(found)==1。真实函数仍存在于固定新include，不能删该断言、跳过或换假算法。

唯一修订复用原新TEST test_exact_inverse_keeps_original_driver_and_w1 的机械算法，不跨测试import、不新增生产算法：
- driver inverse在原lease展开前，只认固定fixed_helpers marker且最多一次；将helper在唯一canaries定义处分开，前缀回原include位置，canaries回插唯一gate定义前；然后原lease展开与原a65f完整hash断言逐字不变。
- reservation在regex前只认固定unused_identity marker且最多一次，读同目录固定文件，展开一次；原regex唯一性、实际函数编译、全部7个mode、1024耗尽/unknown即时拒绝/碰撞永久烧已发lease、stdout/stderr/timeout计数均不变。
- 两个已知marker不存在时保留旧inline形态兼容；不是任意include解析器，不递归、不接收root/path参数、不从任意文本发现文件、不改生产driver或W1文件。

修改仅未来一个文件两个方法，新增13行；不改imports、expectedhash、skip、13方法数、原7case/W0W1原生门、wire/profile/正式classification。原新15仍须保持默认9PASS6skip/optin9PASS1APIassertFAIL5skip；不得将skip当native通过。

### E.2 冻结输入与完整投影

|路径/资产|行数|SHA256|
|---|---:|---|
|tests/test_macos_process_groups_native.py 输入|472|1ed2b2d8d3f2606a9fdf07fa94a0809919f54e23c2f2d515921dfcef8d6f2ed1|
|tests/test_macos_process_groups.py 只读旧W0 TEST|267|632c251af3fe9c190397db2b69e3bb6fd1c664433c1f5fec2a9e8af33381f235|
|同文件最终投影|485|78e30df5c19ab97feb9eabcdf6f314602b7df96399b5ba6a7fbe8d6fdaf21927|
|附录E唯一apply_patch fence|30|a41bc0392b25f0b01ab8d26e18844382d3d9743f784037269d24746a2b961999|
|native/mac/tests/icode_m0a1_driver.c 实际Task2投影|511|141bedc63deadad332eb1d46a474d24d68c837248fd89247d04bea4819f1bf9a|
|native/mac/tests/icode_m0a1_fixed_helpers.inc|203|de74f6b77a9d91fd3d9fdf2801adfe4dc8685ff685480a7b09bb0e9c58f10546|
|native/mac/tests/icode_m0a1_process_groups_native.c 实际Task2投影|389|ebe6071bd7b9e26c4948d1bbc87f496a149766e352231a5c0a5675d9f45194aa|
|native/mac/tests/icode_m0a1_unused_identity.inc|30|a6916f73f63275ea43e1653a0d9ced53b4daceb594846a795cedd24b13035619|
|native/mac/tests/icode_m0a1_identity_lease.inc|81|3f8563da5c30d55469776a212b397e4515a33b090dae4d387d8439ffc0226e82|

以下唯一完整patch仅在本附录freshSPEC→不同QUALITY全0后，由root或另人实施。数字坐标若apply_patch不接，可仅规范化@@头，增删正文/hash不可改。

### Asset E: 旧TEST固定include兼容patch

```diff
*** Begin Patch
*** Update File: tests/test_macos_process_groups_native.py
@@ -174,6 +174,15 @@
     def test_driver_inverse_is_exact_original(self):
         driver=ROOT/"native/mac/tests/icode_m0a1_driver.c"
         content=driver.read_bytes()
+        marker=b'#include "icode_m0a1_fixed_helpers.inc"\n'
+        if marker in content:
+            self.assertEqual(content.count(marker),1)
+            common=(driver.parent/"icode_m0a1_fixed_helpers.inc").read_bytes()
+            self.assertEqual(common.count(b"static int canaries("),1)
+            self.assertEqual(content.count(b"static void gate("),1)
+            split=common.index(b"static int canaries(")
+            content=content.replace(marker,common[:split],1)
+            content=content.replace(b"static void gate(",common[split:]+b"static void gate(",1)
         marker=b'#include "icode_m0a1_identity_lease.inc"\n'
         if marker in content:
             self.assertEqual(content.count(marker),1)
@@ -188,6 +197,10 @@
         native=ROOT/"native/mac/tests/icode_m0a1_process_groups_native.c"
         self.assertTrue(native.is_file(),"native TEST asset absent is infrastructure, not RED")
         source=native.read_text(encoding="utf-8")
+        marker='#include "icode_m0a1_unused_identity.inc"\n'
+        if marker in source:
+            self.assertEqual(source.count(marker),1)
+            source=source.replace(marker,(native.parent/"icode_m0a1_unused_identity.inc").read_text(encoding="utf-8"),1)
         found=re.findall(r"static uid_t reserve_unused_id\(int leases\) \{.*?\n\}",source,re.S)
         self.assertEqual(len(found),1,"actual reservation function must be extracted unambiguously")
         cc=shutil.which("cc")
*** End Patch
```

### E.3 未来独立实施及定点命令

Dependencies：本附录root全文＋fresh SPEC→不同QUALITY均0，实际TEST review修复项明确批准；Parallelizable：No。当前作者不落实TEST、不调用执行技能。
- 核输入与原12fence/hash，apply_patch仅E资产；AST与最终投影hash485L匹配；源文件driver/W1/groups/limit/controller/CMake/CI与冻结新TEST均不改。
- 仅运行下列旧13定点，必须13PASS/0FAIL/0ERROR/0skip。它们仍是软件TU/runner/observer回归，不授native信用。
```bash
python3 -B -c "import unittest; s=unittest.defaultTestLoader.discover('tests', pattern='test_macos_process_groups*.py'); assert s.countTestCases()==13, s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(not r.wasSuccessful() or bool(r.skipped))"
```
- 保留并复跑原Task2新15同命令，默认9PASS/6skip；optin9PASS/唯一API assertionFAIL/5skip。此API故意仍RED，不扩cap2补绿。未来需新15/旧13全部约定结果及actualTEST fresh双审才可root发布TEST-only候选。
- 之后仍须两Mac可运行noquota V3首byte及唯一第三fork quotaassert真实RED。没有此信用，Task3 quotaSOURCE/cap2/CIenv1继续禁止；本附录不改变A18+B26/finalA–E门，不消减C/D/E/M0b/M1阻断。

### E.4 七维自检与停止线

本作者有界匿名stdin诊断：从本文E fence逐hunk唯一匹配构造485L投影并核78e30d完整hash，compile后仅在RAM执行该模块，同时加载未改旧W0 TEST，严格count==13；Ran 13 tests in 7.174s / OK，0FAIL/0ERROR/0skip、退出0。包含真实Linux TU编译/7 reservation modes及50 runner软件边界，未运行Mac/root/native或全量。两方法输入真实文件仍472L原1ed2摘要，没有落地修订。实际4ee5主体可由raw[:raw.rfind(b"\n## ")]逐字节恢复，独立hash4ee5已核；原12fence摘要全部不变。此诊断不是正式TEST修改或quotaRED信用。

语法：新13行和完整投影AST可解析；依赖：仅同目录固定include、无跨测试import；逻辑：前缀/canaries回正确gate位置再展开lease；异常：重复marker/歧义canaries或gate以断言拒绝，原真实TU错误不被隐藏；关联：仅两个旧提取方法适配；兼容：原a65f/len(found)==1/7modes/13计数不变，None/native契约不变；可运行：完整唯一patch与strict命令已提供，原生未跑。当前STOP等待root全文＋freshSPEC→不同QUALITY，不自行实施或发布。
