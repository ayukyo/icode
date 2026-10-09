# R3 端点选择与凭据保护只读研究

观察2026-10-09，源码基线main d365e6f/vendor1693651。独立研究已STOP，root另读公开源码及官方文档；没有读取KEY、私有配置或环境token，没有模型HTTP、API旧域名探测、源码修改或测试。本文是后续设计输入，不扩当前构建诊断两源码范围，也不代表授权外发或真实六步验收。

## 当前事实与未知

root全文读取`src/icode/config.py`与`src/icode/backends/openai_compatible.py`。显式model/base_url优先于ICODE环境与默认；技术默认仍为`https://api.minimaxi.com/v1`和`MiniMax-M3`。key_file只控制凭据来源，解析器不解析provider/URL/地区。实际凭据顺序是显式key_file→环境KEY_FILE→本地key_file→环境API_KEY；“环境优先于本地”的宽泛注释不能代替实际路径。代理另按no_proxy→显式proxy→环境处理。

[中国官方OpenAI文档](https://platform.minimax.cn/docs/api-reference/text-openai-api)当前示例为`https://api.minimax.cn/v1`，[全球官方文档](https://platform.minimax.io/docs/api-reference/text-openai-api)为`https://api.minimax.io/v1`，两者列有MiniMax-M3。root另读当前官方页面。旧默认API是否仍可用、用户KEY地区/计费/适用端点及是否应更换默认未知；官方文档变化不是旧API失效证明。不得携KEY在多个域名试错或从文件字样猜地区。

源码确认三项潜在凭据保护缺口，不称已发生泄露：

- 后端dataclass的api_key字段未排除repr，默认对象repr会包含原值。
- HTTP错误正文截取、通用异常str及响应结构JSON进入BackendError；模块安全注释不是脱敏实现。root另核`loop.py:306–308`会将异常str放入LoopResult的error字段，证明有下游传播路径而非实际泄露事件。
- `_opener`只配置代理，沿标准库默认redirect。固定CPython3.11.15的[build_opener](https://github.com/python/cpython/blob/2340a037f7450e70fccfe411e6531afb4d57a312/Lib/urllib/request.py#L569)包含HTTPRedirectHandler；[POST301/302/303](https://github.com/python/cpython/blob/2340a037f7450e70fccfe411e6531afb4d57a312/Lib/urllib/request.py#L653)重建GET仅删content headers，保留其它headers、无host比较；[允许scheme](https://github.com/python/cpython/blob/2340a037f7450e70fccfe411e6531afb4d57a312/Lib/urllib/request.py#L704)包括http/https/ftp。ICODE把Bearer放在Request headers，因此此机制可能跨host或降级转发Authorization；本次没有网络复现。POST307/308在此固定实现不自动跟随，不能泛化所有redirect行为。

## 固定开源机制对照

| 项目与固定提交 | 已核机制 | 取舍与边界 |
| --- | --- | --- |
| OpenCode `388406238bd5ca15564a762840a2362c3a45bd9c`，MIT | [provider.ts](https://github.com/anomalyco/opencode/blob/388406238bd5ca15564a762840a2362c3a45bd9c/packages/opencode/src/provider/provider.ts#L1810)显式options.baseURL优先于model.api.url，并按provider加载凭据；root另读1533/1633/1698/1810片段与完整MIT许可 | 采纳显式provider/端点分离机制；暂缓注册架构，不从key猜域名，不复制auth落盘 |
| Codex `99aa05341d1564cf4ca2b463c83b607ea5d1bb3e`，独立研究核根Apache-2.0 | [RedactedString](https://github.com/openai/codex/blob/99aa05341d1564cf4ca2b463c83b607ea5d1bb3e/codex-rs/utils/redacted-string/src/lib.rs)隐藏Debug但serde透明序列化，root另读完整50行 | 采纳显式敏感字段展示保护；不能视serde安全或全链路脱敏证明；不复制Responses接口 |

独立研究还核Codex的[显式provider](https://github.com/openai/codex/blob/99aa05341d1564cf4ca2b463c83b607ea5d1bb3e/codex-rs/model-provider-info/src/lib.rs#L139)和[without_redirects](https://github.com/openai/codex/blob/99aa05341d1564cf4ca2b463c83b607ea5d1bb3e/codex-rs/http-client/src/client_builder.rs#L376)；后者只是可配置能力，默认follow_redirects=true，不证明所有模型调用关闭redirect。root没有另行全文复核上述两个大文件，结论明确限于研究输入，实施前需定点再核。

## 模型协议补充：公开显示不等于私有对话历史

中国官方同页“特别注意”要求多轮function-call保留完整assistant返回，列明MiniMax-M3的content包含think标签。root核当前后端`complete`在265行调用strip_think，`loop.py:315`把`_assistant_message(assistant)`加入history，484行只复用msg.content和工具字段，未复用原完整content/reasoning_content；公开消息清理和供应商私有历史没有分离。这是当前源码与该官方协议的差异，不证明旧Reviewer不提交或旧任务失败的根因；没有模型A/B或自然成功率证据。后续需独立设计私有协议历史与公开事件/显示的边界，不能直接把思考正文写日志或凭本页说明改全部模型。

## 开发决策与验收输入

采纳为下一R3设计依据：复用现有显式参数，先固定provider/完整端点/model/代理策略；合成秘密离线负控覆盖repr、HTTP正文、异常/响应结构及重定向，不读真实KEY；固定输出类别与原payload分离可复用当前诊断研究机制。禁止未知端点自动切换及携凭据redirect，保留确定性错误与既有有界重试的失败语义，不吞错假成功。

暂缓：修改默认域名、provider注册表、同源redirect例外、完整私有模型历史实现；需单独设计、接口兼容和真实验收。模型协议差异、隐私缺口与endpoint选择不是一个已修复阶段。

成本/风险：拒绝redirect及删原错误正文会改变诊断行为，须正负控与现有代理/重试回归；端点选择需明确，供应商支持列表不能代替用户账户资格或授权。收益是避免隐式地址与敏感正文外发/展示，让真实验收可审查。未复制上游实现、引入依赖/权限/部署；完整20名单未在此刷新。

实施后验收：显式URL胜过环境，生效配置可在不读取KEY时审查；跨host/降级redirect不外发Authorization；repr/异常/响应结构无合成秘密；确定性失败不换端点；私有历史与公开显示各有正负控且不泄露；再独立实际模型1→6与额度/平台门，不用离线成功宣称≥90%或R2/R3完成。

方法：firecrawl/exa未暴露，用官方GitHub只读connector与官方网页；root另核上述指定固定片段/小文件，而非所有上游全文。结构化115–117记录需求→机制→兼容风险；当前构建诊断继续按自己的冻结设计/计划/源码验收。
