# R3 模型传输上游阶段复核

观察2026-10-09，独立只读研究已STOP；root另读指定公开源码。本文属于下一R3片，不混入当前单方法JSON测试兼容修复。没有模型HTTP、KEY/私有配置读取、源码导入、上游测试执行、代码复制或新增依赖/权限。原[端点与保护研究](2026-10-09-provider-endpoint-and-secret-research.md)的固定快照保留，不回写旧观察日期。

## 当前提交与读取范围

先前阶段GET中root与独立研究各只读观察[Codex main](https://api.github.com/repos/openai/codex/branches/main)为`22ebb0fb178fe369190123c256ba200585765725`；本片源码固定核该提交与原`99aa05341d1564cf4ca2b463c83b607ea5d1bb3e`。独立证据复核于2026-10-09 00:44 UTC另见main前进到`b6e8a2e207e5591780061c62c50df417670f8d75`（父提交22ebb0f）；只记录分支漂移，不扩大已冻结源码范围或把新HEAD算全文已核。[OpenCode dev](https://api.github.com/repos/anomalyco/opencode/branches/dev)该次仍为固定`388406238bd5ca15564a762840a2362c3a45bd9c`。这是按时点的阶段观察，不称完整20名单重查或持续轮询。

独立研究全文比对Codex的RedactedString、client_builder、builder_tests、route_aware_redirect、redirect_tests、pool_tests、LICENSE，本片固定22ebb0f与原固定99aa053快照相同；root只独立精确比对RedactedString和route_aware_redirect两文件，不冒领其它文件全文复核。独立研究全文核固定Codex Apache-2.0和OpenCode MIT许可；没有复制其实现。

## 源码与测试证据

- [Codex RedactedString](https://github.com/openai/codex/blob/99aa05341d1564cf4ca2b463c83b607ea5d1bb3e/codex-rs/utils/redacted-string/src/lib.rs#L8-L49)：root全文读；仅Debug固定隐藏，serde透明，仍有原值访问。默认展示保护不等于任意序列化或内存安全。该文件没有测试；全仓专项测试是否存在unknown，不以有限搜索冒称没有。
- [Codex builder](https://github.com/openai/codex/blob/99aa05341d1564cf4ca2b463c83b607ea5d1bb3e/codex-rs/http-client/src/client_builder.rs#L376-L402)：独立研究全文422行，without_redirects映射Policy::none，默认follow_redirects=true；root未另全文。不能称所有模型调用默认拒绝redirect；builder_tests仅CA回退保留header，不是redirect证明。
- [Codex pool测试](https://github.com/openai/codex/blob/99aa05341d1564cf4ca2b463c83b607ea5d1bb3e/codex-rs/http-client/src/route_aware_client_pool_tests.rs#L530-L640)：root读完整530–640选段。默认GET/302实际localhost测试跟随至200；禁redirect池分别ReqwestDefault/RespectSystemProxy返回302、起始GET一次。仅源码测试逻辑证据，未执行；没有POST、全部五状态、跨源/降级、Authorization或socket poison矩阵信用。
- [Codex route redirect](https://github.com/openai/codex/blob/99aa05341d1564cf4ca2b463c83b607ea5d1bb3e/codex-rs/http-client/src/route_aware_redirect.rs#L98-L137)：root全文读。按scheme/host/有效port判断同源，跨源移除敏感header，降级不置Referer；这是允许跟随时的保护，不是全部3xx拒绝。相关单测由独立研究读192–232，仅所见向量，不替ICODE验收。
- [OpenCode provider](https://github.com/anomalyco/opencode/blob/388406238bd5ca15564a762840a2362c3a45bd9c/packages/opencode/src/provider/provider.ts#L1810-L1837)：独立研究重核显式baseURL/已有apiKey优先；root原研究已读相关片段。配置对象测试不证明实际网络目的地或redirect安全。1172–1186的toPublicInfo为JSON兼容化/无效model过滤，保留可序列化key/options，不是脱敏器；未沿消费者穷尽追踪，不宣称公开UI或实际泄露。timeoutFetch未显式设置redirect，实际SDK/runtime全调用策略unknown。
- [OpenCode error](https://github.com/anomalyco/opencode/blob/388406238bd5ca15564a762840a2362c3a45bd9c/packages/opencode/src/provider/error.ts#L32-L70)与[测试](https://github.com/anomalyco/opencode/blob/388406238bd5ca15564a762840a2362c3a45bd9c/packages/opencode/test/provider/error.test.ts#L5-L22)：root分别全文195/24行。可以保留message/body；API错误172–191还保留responseBody/headers/URL metadata。HTML错误有固定提示分支，但不等于通用秘密过滤；测试正向期待保留正文。记录诊断取舍，不从这些代码断言已泄露凭据。

## ICODE取舍与验收

采纳：敏感字段值与默认展示分离、显式端点/凭据独立配置、真实输运正负控。ICODE已有标准库后端、原代理映射与有界重试可复用；收益是凭据外发/展示边界可审查，成本为错误详情与redirect兼容回归，无新增依赖、权限或许可代码复制。

暂缓：Codex同源redirect/路由池与OpenCode注册架构。可扩复杂路由，但成本超过本片，不能据此放宽已冻结全部3xx拒绝；同源等价、降级与代理重新解析需另设计。

不适配：透明serde、toPublicInfo命名、固定InitError message或少量上游单测冒称全面脱敏；不复用OpenCode原正文/URL错误对象保留策略，不推断未知SDK默认行为。

本片继续既有冻结设计：repr敏感字段/固定代理策略/闭类别错误、HTTPError一次close、所有3xx拒绝；构造参数、默认端点、成功payload/tools/Usage、原代理映射与重试不变。验收只据实际TDD及合成秘密、真实urllib/error processor、HTTP/HTTPS fixture、host proxy-bypass隔离和socket poison、75redirect子向量/200正控；上游测试未执行，更不是ICODE测试或live网络证明。私有内存/任意序列化、模型1→6/≥90%、Windows隔离和平台配额/R2/R3仍独立。

方法：firecrawl/exa未暴露，使用官方GitHub只读连接；只相关两个项目阶段复核，不安装/配置新工具。root完整软件preflight期间研究与源码/测试执行隔离；下一片履历与精确文档一致性清单再纳本文，当前测试修复不暂存它。
