# Windows 随包离线来源验证

用户已授权随包验签依赖、受限 main 签名 job 权限及持续开发；本片采用此前提出的原生验签器路线，解决 Python Sigstore SDK 的 Windows ARM64 二进制依赖缺口。开发机与 CI 可以使用 Go，安装者仍只需 pip，不要求 Go、Rust、GitHub CLI 或在线验签。

## 信任边界与复用

复用 sigstore-go v1.3.0（Apache-2.0）进行证书链、DSSE、认证时间、SCT 和透明日志验证，不自行实现密码学。发布器及其内嵌可信根属于已安装 Python 包的信任基；相邻哈希仅用于检测损坏，不能证明 wheel 发布者，也不能解决整个 wheel 被替换。沿用已有 proof transport 和 gh CI 独立验证，不修改 bootstrap 的三个 false 或开放自动模式。

原生 CLI 只验证、不启动 helper。只接受明确 artifact、bundle、架构与源码 SHA；不接受用户指定证书身份、可信根、在线回退、当前时间替代签名时间或跳过验证。对辅助输入有长度上限；所有失败只输出固定错误码，不输出路径、证书、证明正文或底层错误。

## 验证合同

- 内嵌经过来源审核的 Sigstore public-good trusted root；固定根原始字节摘要、来源提交和依赖版本，更新须重新审查并重跑正反例。测试专用根只能通过内部函数注入，不成为 CLI 参数或环境开关。
- 使用完整、单一的 certificate identity：精确 OIDC issuer、ICODE main 签名 workflow SAN、source/signer SHA、source URI/ref、repository/owner ID、github-hosted runner。多个身份是 OR，不能拆成多个身份误当 AND。
- 要求至少一个经过验证的 observer 时间、SCT 和透明日志条目；另明确要求 inclusion proof/checkpoint。公有仓库默认 Rekor SET 可提供认证时间，不强制所有合法 bundle 都带 RFC3161；绝不相信裸 integratedTime。
- 验证成功后检查已验证 statement：in-toto Statement/v1、SLSA provenance/v1、恰好一个 subject、对应架构 canonical helper basename、唯一 SHA-256 摘要与实际读入的 helper 字节匹配。
- 成功回执只表达 provenance_verified=true、launch_authorized=false，并绑定摘要、架构和 source SHA；它不是可信启动对象或隔离就绪证明。

## 实施与验收

先开发和独立审查原生验证引擎，使用上游固定真实签名 fixture/root 做正例与摘要、身份、证明、签名负例；生产 identity 策略另外严格测试。随后将匹配 x64/ARM64 的 CGO-disabled 可执行文件、内嵌根、许可证及 source SHA 元数据接入现有 wheel staging/check/安装测试。干净安装后的验证必须调用包内原生程序，不能用宿主 Go/gh 或 crypto mock 代替。

CI 保留 gh 作为独立 oracle，并在实际 main attestation 上验证包内引擎正例及篡改摘要、身份/source SHA、缺失证明等负例。双架构原生行为、Python 3.11/3.12 安装、完整 preflight、20 轮聚焦回归与独立审查通过后才能关闭本子门。R2/R3 总门、生产 setup/runner 和固定启动对象单独验收。
