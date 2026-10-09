# R3 模型传输与错误展示保护设计

日期2026-10-09。只作下一阶段设计，尚未实施或运行新测试；当前构建诊断片正在自己的软件守卫中。本设计不混入其两源提交。后端源码基线d365e6f，vendor1693651；实施前重新绑定实际main与两源冻结，正常完成构建诊断发布不会改变本文引用的后端现存合同。

## 真实问题、复用与调用链

依据[独立研究](2026-10-09-provider-endpoint-and-secret-research.md)，当前`OpenAICompatibleBackend`的api_key默认出现在dataclass repr；HTTP正文、异常str和响应结构截取进入BackendError；默认urllib redirect可能保留Authorization。`active_proxy()`另把包含用户信息、路径或查询的代理原URL展示给CLI。上述是源码机制风险，没有真实KEY泄露或网络复现证据。

root全文读当前299行后端、53行base及BackendFactory/ProxyStrategy/BackendRetry完整测试类，定点核CLI `_build_runner`、CLI BackendError捕获和loop306–308/83–84。调用链是build_backend→后端complete→BackendError→LoopResult.error/render或CLI错误展示；CLI另直接展示active_proxy。复用标准库urllib、现有代理映射、Usage、有界重试和Backend协议，不新增供应商、依赖、权限、服务或执行能力。

当前HTTP catch会读取错误body；`_proxy_hint`会str异常和插入代理地址。`_usage_from`的整数转换处于transport catch之外，畸形usage可在ValueError中带原值，因此响应解码后的结构/usage/tool-call解析也必须有明确安全错误边界，而不是只修HTTP正文。原成功回复、工具参数和用户消息不是本片通用内容脱敏对象。

## 候选与自主阶段决策

A（选择）：模型调用拒绝所有redirect；可公开的后端错误仅由固定类别、合法HTTP整数状态和固定提示组成；后端repr隐藏敏感配置，代理显示只给固定策略说明。它不猜测端点或改变原代理输运。

B（暂缓）：同源redirect白名单，加正文秘密字符串替换和代理URL部分展示。收益是保留部分诊断细节；成本是URL等价、降级、编码/重复header和未知凭据边界，不能用replace声明全链路安全。本片没有已证明依赖redirect的产品合同，先选A。大规模secret-wrapper/provider注册重构也不适配当前最小修复。

root依用户“你决定阶段”“直接下一阶段、不用等命令”既有授权选择A，不是新的许可答复；仅软件范围，仍须设计双审、计划、TDD、实施双审和完整守卫。真实KEY所属端点待明确，不能凭本设计外发、切域名或开放任何生产隔离准入。结构化118–120记录需求→方案→兼容风险。

## 范围与接口保护

预计五个源码路径：`src/icode/backends/openai_compatible.py`、现有`tests/test_runner.py`中三个后端测试类的必要断言、新`tests/test_backend_transport_privacy.py`、`scripts/run_workspace_ci.py`、`tests/test_run_workspace_ci.py`。新测试须portable完整选择一次并有配对no-skip守卫；DEFAULT原选择只新增该模块，不删已有项。其余runner/loop/CLI/config/base/native/vendor/workflow不改。后续计划须全文回读实际编辑上下文和两个选择文件。

保留constructor参数顺序/default、Backend.complete签名、build_backend名称与显式参数/环境优先级、旧默认域名/model、不读取KEY的配置行为、代理映射与优先级、max_retries/backoff/timeout、Usage计数及tools/tool_choice序列化。成功请求仍向已选URL POST一次并带原Authorization；不改TLS、代理认证、HTTP初始端点支持或新增URL猜测/fallback。

行为变更明确只有安全界限：3xx不再跟随；错误不公开原正文/URL/任意exception文本；active_proxy由地址变为策略；后端自身格式化repr不展示敏感配置；畸形响应解析拒绝为安全BackendError；MemoryError不再被普通transport catch吞成字符串。错误仍失败，不假成功，不更换端点。401等确定性错误不重试，既有传输重试集合与次数保持。

## 凭据展示与错误边界

dataclass中api_key、base_url、proxy使用repr=False，避免默认repr含KEY或URL中的凭据；不改变字段的实际值和请求使用。这里只保护默认repr/str，不承诺asdict、pickle、字段直接读取、调试器内存、第三方自定义记录器或任意反射安全。model/name等普通标识字段不是凭据存储支持项。

`active_proxy`保持no_proxy的旧“禁用（强制直连）”、无代理的旧“无”；显式代理固定“已配置（显式代理）”，环境代理固定“已配置（环境代理）”。不显示原URL、用户名/密码、路径、query或fragment，真实`_proxy_mapping`不变。自检仍告诉小白代理策略和`--no-proxy`，不公布地址。

`_proxy_hint`不调用str/repr或读取reason/URL。显式proxy/no_proxy时仍空；自动环境代理存在时只给固定策略提示和已有`--no-proxy`/`ICODE_LLM_NO_PROXY=1`，不带地址。可以对普通RuntimeError给同样通用提示，不根据任意错误字符串猜“代理根因”。

HTTPError可公开信息只为type(code)精确int且100–599的HTTP状态，否则unknown；不读取msg、headers、url、body、reason或格式化原异常。不读body；对HTTPError的响应资源只关闭一次，关闭普通故障不盖住原确定性失败或额外重试，MemoryError/KI/SE仍传播。HTTP状态仍按原retryable集合决定是否重试，未知状态不重试。

普通transport错误使用闭集标签：TimeoutError、URLError、ConnectionError、HTTPException、UnicodeError、JSONDecodeError、ValueError、TypeError、OSError、unavailable，具体类先于基类；不输出动态类名或str/repr/args/cause/context。默认消息仅固定失败说明，TimeoutError标签保留旧测试可识别性。真实重试仍按原类型判定，不从展示类别推新恢复策略。MemoryError明确传播，KeyboardInterrupt/SystemExit自然传播。

响应结构/usage/tool-call/content解析的已知输入异常（KeyError/IndexError/TypeError/ValueError/AttributeError/OverflowError）统一为固定“响应结构异常（详情已隐藏）”BackendError，保留已有from None。不得序列化data/原message/usage/tool参数作为错误说明。保留现有解析成功结果与usage记账顺序；现有工具arguments非JSON时_raw兼容行为不变，不新增结构“修复”或无限重试。公开成功模型内容/工具参数不是本片秘密过滤器。

保护信用只覆盖BackendError公开str/repr/格式化traceback以及它进入现有LoopResult.error/render/CLI后的文本。Python内部被抑制的__context__仍可能留原异常，本片不承诺内存对象图无原值；不得用from None冒称清除了所有上下文或数据。对任意custom Backend/输入构造失败的全局脱敏另需设计。

## 重定向边界与真实离线负控

用一个私有HTTPRedirectHandler子类拒绝redirect_request，并同时用于所有代理策略的build_opener。保留标准HTTPErrorProcessor；不禁用TLS、不变更初始Request头、不自动GET/fallback。301/302/303/307/308均确定性失败且不跟随，包括同源、跨host、跨port、HTTPS→HTTP、相对Location；不只测试直接调用拒绝helper。

离线测试使用真实`OpenerDirector`/HTTPErrorProcessor/redirect handler，加测试内HTTP/HTTPS响应handler：第一目标返回实际带Location的响应对象，第二目标若被调用记录凭据。代理映射由fixture固定，不读取私有环境；在handler拦截所有地址，并用socket连接毒化证明没有外部网络。每个3xx确认origin一次、destination零次、零sleep/retry、Authorization没有被转发。另200正控确认同一实际opener能发送一次合法原请求、解析回复。测试不能直接mock opener.open抛HTTPError来冒充真实redirect信用。

普通错误/重试测试可使用输运fixture：401/403/404等一次、429/503和TimeoutError规定次数、失败后成功只增加实际retries、每次同一URL且无fallback；核APIKEY仅出现在起始授权Request，不在公开异常/代理描述/repr/loop render/记录的公开JSON。合成秘密只在测试内创建，不读真实KEY或发送模型HTTP。

## 验收与阶段分离

具名正负控覆盖三种代理策略repr/展示、HTTP正文和异常属性poison、闭错误类别优先级、HTTP状态精确int/unknown、关闭响应ordinary/fatal边界、decode/畸形choice/message/usage/tools/content固定错误、正常tools与usage不变、重试耗尽/重试成功/401不重试、真实opener3xx目的地零访问和200正控、LoopResult.error/render的合成秘密缺席。测试失败必须是有效assertion RED，fixture ERROR不能当RED；新增portable不能skip。

实施规格/质量双审绑定实际源码SHA；root定点涵盖原三个后端类、新测试、loop错误传播及CI选择，20轮关键路径、DEFAULT、原三道preflight、compile-j1、治理/site/持续对照、文档连续两轮clean、secrets/vendor和精确main发布都按实际执行记数。新SHA跨平台CI仅授软件协议边界，不能代替实际模型1→6、≥90%能力一致性、账户适用端点或R2资源/隔离门。构建诊断片必须先结束源码测试冻结，再实施本片；可并行做本设计审查，不并行改生产代码。

采纳固定OpenCode的显式provider/端点分离原则与Codex的敏感展示保护原则；不复制上游实现、auth落盘或Responses API，也不把Codex可配置禁redirect称其全部调用默认行为。固定源码/许可与观察日期见独立研究；完整20观察名单未在此重新刷新。

暂缓默认域名迁移、provider选择UI/注册表、供应商私有完整历史与公开think分离、同源redirect例外、生产资源准入。收益是消除本次可审查的凭据展示/默认转发路径；成本是少量诊断详情与代理地址不再公开及3xx显式配置要求，正负控保护普通白领仍可按固定提示配置。

root静态自审：范围五路径、旧成功输运与重试保持、安全行为变更明列；敏感字段默认展示与任意序列化/内存边界区分；响应解析和HTTP资源关闭没有留未定义异常处理。本文无实现/测试/发布完成信用；下一门为fresh设计SPEC→不同QUALITY，然后writing-plans。
