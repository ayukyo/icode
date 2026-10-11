# 固定来源消费者原生安装观测实施

基线main34c8bc6，按[设计](../specs/2026-10-11-windows-source-owner-native-design.md)继续；用户main-only/推荐方案自主执行覆盖重复批准和worktree步骤，TDD及独立审查保留。生产源码与vendor不改，编译-j1。

## Task1：真实委托probe与严格回执

单writer仅新增 `scripts/probe_windows_installed_source.py` / `tests/test_windows_installed_source.py`。

- [x] 先写真实assertion RED/0ERROR，接口probe(source_sha)、validate_wire(wire,source_sha,arch,*,expected_python,expected_windows)、main(argv=None)；非Windows/坏输入零原生调用。
- [x] 实现无包装基线、真实委托backend/reader/纯policy观测、绑定恢复、实际HANDLE/SD代次回收与前缀校验；不让原生异常伪装政策拒绝。
- [x] 规范finite JSON与严格validator、固定失败输出；未知关闭/释放、中断/原身份、重复/遗漏/倒序、地址复用、第二资源失败、非法wire/类型/budget覆盖。
- [x] 便携测试及20轮0skip/F/E；compileall-j1/diff，自SPEC→自QUALITY；冻结两文件摘要。便携fake仅验证账本契约，无原生信用。

### Task1最终软件冻结

writer有效assertion RED九组failure为1、2、1、1、2、2、1、1、3，每组有效RED均0ERROR；前期两次测试试跑各2ERROR经纠正后重取assertion RED，不计信用。此为writer历史，root未重演RED。最终probe436行/test680行，实际Interface1/Receipt6/Consumer21/Ledger5共33方法。writer33 PASS、20轮660 PASS/0skip/F/E、九关联285run=275 PASS/10既有native环境skip；compileall-j1/diff。最终SPEC复核与不同QUALITY均C0/I0/M0，I1与取得/释放记账中断窗口皆经负控关闭；旧30候选摘要及审查不用。

root已全文回读probe/tests及增补窗口，另实际33 PASS与20轮660 PASS/0skip/F/E，循环前后SHA相同。probe SHA256 `6d25ae9335ea5e87cee085dfcb5ad11efd2798d81efae38430d56a5312ab4050`；test `94953a0c500299a378a92c8864c88421a48e58373ab486400d261f61a7e6e849`。固定设计澄清note后的SHA `174c98949af5458fd99ff41fd60f1c04a6cc3bc12ecc09a8ebeadbc4f135ba3a`。仅两新文件，未改生产/vendor，没有Windows/UAC执行、主CI接线或发布信用；Task2新单writer已自主开始。

## Task2：既有安装监督与必需CI接线

Task1冻结后另一单writer，只改 `scripts/run_windows_wheel_ci.py`、现有父侧测试文件 `tests/test_windows_bootstrap_binding.py`、`scripts/run_workspace_ci.py`、`tests/test_windows_startup_pin_ci.py`。父侧旧整链监督测试实际位于bootstrap_binding，不在installed_chain；新独立便携class只选该class，不把旧bootstrap可选测试升级为必需。

- [x] 父侧用既有有界raw子进程、新probe固定路径、-I/-B/-Xutf8、30s/32KiB，signed安装整链后执行；先RED坏捕获/超量/timeout/pipeunknown/stderr/坏wire/隐私，后GREEN；仅validator认可schema输出，不走宽松_run。
- [x] 新测试模块一次进入DEFAULT/startup必需选择；实际loader同步counts，真实fixture/class/method/subTest skip均拒绝；旧ID/可选/native语义不变。
- [x] 全关联及20轮真实便携选择，自SPEC→自QUALITY，四功能接线文件摘要冻结。

### Task2最终软件冻结

writer有效assertion RED分别为父侧新5方法40F/0E、旧集成1方法2F/0E、guard12方法141F/0E；早期测试编写错误已修后重取纯assertion RED，不计错误轮信用。最终新probe33+parent5+guard12共50PASS，完整11模块346run=336PASS/10既有native平台skip/F0/E0；便携selector269+guard12共281方法，最终20轮5620PASS/0skip/F/E。自独立SPEC后不同QUALITY均C0/I0/M0。真实模块fixture负控：新parent class/whole module返回1，旧binding class返回0；新parent class skip为run5/skip5/code1。旧binding22及hostcompiler6语义保持，POSIX合成编译不算Windows证据。

root独立重跑11模块346run=336PASS/10既有native平台skip/F0/E0，20轮真实selector+guard5620PASS/0skip/F/E；六文件循环前后摘要相同。startup selector实际posix269/nt279且unique，旧231/241 ID全保留。接线四SHA256：wheel `0f2d91fab193b25c7c906c3b990c2d416f88492ff8bb368694dbdaede1bf0417`；binding test `435389cb70d682fb2ea4addca54a89cb637cc316d83c20c111dd392331c2784d`；workspace `f3b83b6de71cc79c54b1c96178fd028bf4a8e2619b105af04aeae3c6229919ae`；guard `94209a2bd953272d493752284aa24ff023313aa23104d2940710f9968af3f856`。全片独立SPEC后不同QUALITY均C0/I0/M0，各实际72PASS/0skip/F/E并核六摘要。Windows DEFAULT实际词法loader为923 unique（排除20 POSIX-only选择），其中probe33/parent5各一次；不是Windows运行信用。完整preflight仍运行；未发布、未跑Windows安装观测。

## Task3：软件发布、四格原生分账、下一片

- [x] root全文回读全部源及上下游，独立全片SPEC→不同QUALITY零C/I/M；关联/20轮、完整preflight三道、文档/site/diff/秘密/固定vendor、七维真实范围报告。
- [x] exact add/commit/push main并核remote；不带用户无关改动。
- [ ] 新SHA Windows x64/ARM64×Python3.11/3.12读取完整安装原始回执，父validator再核；分别记录根拒绝和实际回收，不授默认兼容/叶负控/UAC/R2/R3。
- [ ] 继续临时叶真实运输负控与卷根/加载操作合同工作，不能以本观测代替完成。

### root最终软件守护

软件已实际exact10文件提交 `e7833509030392e88a6ce11e9b455064925c0e06`，推送main后git ls-remote同SHA、工作树clean。CI38150048884、provenance38150048901、Pages38150048904已新SHA启动，独立只读观察者并行跟踪；四格新原生回执仍未授信用。

### e783350实Windows失败与窄测试修复（进行中）

root取得x64/3.12 workspace job114501428931完整raw：actual923run/20 optional skip/3 assertion failure/0error。核心是 `test_input_rejected_before_native_or_consumer` 将合法SHA列为invalid且未固定nonWindows，Windows会实际进入已mock入口；另两个是guard真实运行该class/module时关联同一失败。不能以Linux933PASS/0skip（root另跑182.001s）替代Windows通过。独立观察者另核两旧Reviewer，仍10035/wait_expired/private control creditfalse，非DENY，非此测试回归。

rootWindows模拟（真实probe+固定实际版本/架构边界，消费者仅测试mock）重取1assertionF/0E，再仅修改该测试315–328：win32/linux均坏SHA0入口，合法SHA只nonwin0入口，合法win32正控仍由原两轮ready/rejected测试验证。修后50PASS及外层Windows1PASS，11关联346run=336PASS/10既有native skip/F0/E0、20轮5620PASS/0skip/F/E；测试新SHA256 `8d09f8dc1cbab92ecca799b496bec09c8ddb7fa59db82a1187e0eea6ef00e136`，probe及其余五功能摘要不变，不修改生产或权限。hotfix独立SPEC后不同QUALITY均C0/I0/M0，各50PASS及外层Windows2PASS；新完整preflight session6118仍运行。下一片两draft文件暂冻结10P，仅为全仓守护保持稳定，不纳hotfix提交或授实验实现。

2026-10-11 15:27 UTC，hotfix新完整preflight6118三道OK/exit0；测试及两draft摘要从守护前后均不变。双独立复核、关联/20轮、compile-j1、docs0疑似/site/diff通过。守护包含稳定的10项下一片draft合同但它们不纳本提交，不授该实验功能；功能交付仍仅一个输入负控测试。七维自检语法/依赖/逻辑/异常/关联/兼容/便携运行通过，新的实际Windows四格待新SHA，不声称跨平台完成。

e783主CI窗口已终态37success/6failure/3conditional skip，四workspace均923run/20skip/同源3F，root实际读取四完整raw；fullPython3.11/3.12各2876run/81skip/2795PASS，root分别核原始日志658.671s/789.814s。Pages2/2success。e783签装目前三格新消费者raw经独立观察者真实validator核过；root另核x64/3.12原始wire且预期Windows版本取runnerOS 10.0.26100：baseline拒绝关闭信用null，实际观测两资源各13节点/26确认逆序close，仅helper/root一个owner_untrusted事件及2SD读/alloc/free，无未知。此为固定consumer拒绝与回收的组件证据，非e783全软件通过；最后格及hotfix新四格仍验，compatibility/launch/protected均false。

2026-10-11 15:06 UTC，完整preflight session59265三道均OK、exit0；工具不打印全仓成功方法数，不估算。额外密钥扫描亦exit0，固定vendor `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` 无改动。compileall-j1、git diff-check均通过；四文档一致性检查0疑似项，site两次通过HTML2/MD6/上游品牌3/social2，9个外部导航未fetch，不授可达性。六功能摘要与双审/20轮相同。下一片直接DACL临时实验仅草拟、未纳本片软件提交，不借实验信用。

【架构级自检报告】

- 语法/编译：compileall-j1及完整回归通过。
- 依赖/调用链：真实消费者/reader/父监督/签名安装/必需选择完整，双独立全片复核通过。
- 逻辑/边界：346关联及5620轮次方法通过，10既定native环境skip不计原生信用。
- 异常处理：取得/记账/释放/中断、未知回收、非法raw/schema/版本及privacy负控通过。
- 关联模块：六功能文件与四文档同步，生产/vendor无改动。
- 兼容安全：旧可选测试、setup/spawn退出78及三个false保持，无新权限或部署。
- 可运行性：便携软件与完整回归通过；Windows真实安装/默认兼容/加载/UAC/R2/R3未由本片通过。

每次功能改动重新冻结、审查与全守护；研究独立只读不能替代验收。以下保留设计/实现过程的历史窗口；当前Task1/2软件已冻结，Task3发布及原生仍待，未授原生或发布信用。

设计SPEC首轮C0/I2/M0：补SD账本与事件2×数量及同节点关联，冻结各级exact schema与baseline拒绝的null关闭信用；父侧版本预期来自创建目标venv的同一sys.executable和当前宿主，而不是仅版本范围。修复后仍须SPEC复核、不同QUALITY。

设计SPEC复核已C0/I0/M0，不同独立QUALITY亦C0/I0/M0；真实_open/_call/reader委派缝和lazy reader接线、64 HANDLE/128 SD预算、版本来源及有限schema均已核。进入Task1 TDD，设计通过不授实现或原生信用。

Task1实现阶段QUALITY另发现I1：baseline known policy异常附有可见cleanup-unconfirmed却被分类拒绝。root决定最小fail-closed修复：有非空/非法/不可安全读取备注保持原异常、第二轮不调用；正常无备注仍null、不当关闭确认。只改CI probe/tests，不改生产；原30候选审查不沿用，需真实RED、重冻/20轮及SPEC→不同QUALITY复核。
