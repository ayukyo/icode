"""CI / 工单 / 代码托管连接器（R5/W5）。

边界：

- v1 只做**出站调用 + 回执入账本**，不提供入站 webhook 服务端（不新增网络
  监听面，与既有仅回环 HTTP 基线一致）。
- 连接器必须是已注册扩展（manifest ``kind=connector``，声明权限/副作用/
  证据）且**被显式启用**才可执行；endpoint 主机必须被 manifest 的网络副作用
  声明覆盖——声明不是装饰，未声明即拒绝。
- 每次调用先过副作用回执（``start``/``finish``），证据经回执的
  ``evidence``/``check_ref`` 通道落账；没有回执通道（recorder）时调用一律
  拒绝（``evidence_channel_missing``），因为证据无处安放。
- 传输失败只给稳定错误码，不回传响应正文。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .backends.transport import post_json
from .extension_contract import (
    ContractError,
    ExtensionManifest,
    ExtensionRegistry,
    SIDE_EFFECT_NETWORK,
    SideEffect,
    attach_evidence,
)
from .tools.base import OPCLASS_EXTERNAL

CONNECTOR_KINDS = frozenset({"ci", "ticket", "vcs"})

_MAX_ENDPOINT = 256
_MAX_OPERATION = 64
_MAX_OUTPUT_CHARS = 8000

# 传输契约：(endpoint, payload) -> (data, status_code)。
# 默认实现只在 2xx 成功时返回；失败以 ConnectorError 呈现（不带正文）。
ConnectorTransport = Callable[[str, Mapping[str, Any]], "tuple[Mapping[str, Any], int]"]


class ConnectorError(RuntimeError):
    """连接器错误；``code`` 稳定。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _host_of(endpoint: str) -> str:
    parts = urlsplit(endpoint)
    return (parts.hostname or "").lower()


def _host_covered(host: str, targets: tuple[str, ...]) -> bool:
    for target in targets:
        if host == target or host.endswith("." + target):
            return True
    return False


@dataclass(frozen=True)
class Connector:
    """一个连接器：端点 + 已校验的扩展清单。"""

    name: str
    kind: str
    endpoint: str
    manifest: ExtensionManifest

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ConnectorError("connector_name", "name 必须为非空字符串")
        if self.kind not in CONNECTOR_KINDS:
            raise ConnectorError("connector_kind", f"未知连接器类型 {self.kind!r}")
        if not isinstance(self.endpoint, str) or not self.endpoint:
            raise ConnectorError("connector_endpoint", "endpoint 必须为非空字符串")
        if len(self.endpoint) > _MAX_ENDPOINT:
            raise ConnectorError("connector_endpoint", "endpoint 过长")
        scheme = urlsplit(self.endpoint).scheme.lower()
        if scheme not in ("http", "https"):
            raise ConnectorError("connector_endpoint", "endpoint 只接受 http/https")
        if not isinstance(self.manifest, ExtensionManifest):
            raise ConnectorError("connector_manifest", "manifest 必须是 ExtensionManifest")
        if self.manifest.kind != "connector":
            raise ConnectorError("connector_manifest_kind", "manifest 类型必须是 connector")
        if self.manifest.name != self.name:
            raise ConnectorError("connector_manifest_name", "manifest 与连接器不同名")
        host = _host_of(self.endpoint)
        if not host:
            raise ConnectorError("connector_endpoint", "endpoint 缺少主机")
        targets = tuple(
            effect.target.lower() for effect in self.manifest.side_effects
            if effect.kind == SIDE_EFFECT_NETWORK
        )
        if not _host_covered(host, targets):
            raise ConnectorError(
                "network_undeclared",
                f"endpoint 主机 {host} 未被 manifest 的网络副作用声明覆盖",
            )


@dataclass(frozen=True)
class ConnectorReceipt:
    """一次连接器调用的有界回执（不含响应正文）。"""

    connector: str
    operation: str
    ok: bool
    attempt: str | None = None
    exit_code: int | None = None
    output_chars: int = 0
    output_sha256: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)


class ConnectorRegistry:
    """注册 + 显式启用；未启用的连接器不可执行。"""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}
        self._manifests = ExtensionRegistry()
        self._enabled: set[str] = set()

    def register(self, connector: Connector) -> Connector:
        if not isinstance(connector, Connector):
            raise ConnectorError("connector_type", "需要 Connector")
        if connector.name in self._connectors:
            raise ConnectorError("connector_duplicate", connector.name)
        self._manifests.register(connector.manifest)
        self._connectors[connector.name] = connector
        return connector

    def enable(self, name: str) -> None:
        if name not in self._connectors:
            raise ConnectorError("connector_not_registered", name)
        self._enabled.add(name)

    def names(self) -> list[str]:
        return sorted(self._connectors)

    def manifest(self, name: str) -> ExtensionManifest | None:
        return self._manifests.get(name)

    def assert_executable(self, name: str) -> Connector:
        connector = self._connectors.get(name)
        if connector is None:
            raise ConnectorError("connector_not_registered", str(name))
        if name not in self._enabled:
            raise ConnectorError("connector_not_enabled", name)
        return connector


class ConnectorInvoker:
    """按治理链执行连接器调用：回执先行，证据缺项即拒。"""

    def __init__(
        self,
        registry: ConnectorRegistry,
        *,
        recorder: Any | None = None,
        transport: ConnectorTransport | None = None,
    ) -> None:
        self.registry = registry
        self.recorder = recorder
        self.transport = transport or http_transport()

    def invoke(
        self,
        name: str,
        operation: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> ConnectorReceipt:
        connector = self.registry.assert_executable(name)
        if self.recorder is None:
            raise ConnectorError("evidence_channel_missing", "未接回执通道，禁止调用")
        if not isinstance(operation, str) or not operation:
            raise ConnectorError("operation_invalid", "operation 必须为非空字符串")
        if len(operation) > _MAX_OPERATION:
            raise ConnectorError("operation_invalid", "operation 过长")
        payload_args = dict(arguments) if isinstance(arguments, Mapping) else {}
        manifest = connector.manifest

        started = self.recorder.start(
            name=f"connector:{connector.name}",
            opclass=manifest.opclass,
            input_desc=json.dumps(
                {"operation": operation, "arg_keys": sorted(payload_args)},
                ensure_ascii=False,
            ),
        )
        if not getattr(started, "can_execute", False):
            raise ConnectorError(
                "ambiguous_side_effect", str(getattr(started, "detail", ""))[:120],
            )
        attempt = getattr(started, "attempt", None)
        if not attempt:
            # 没有可寻址的执行身份就无法终结回执；此时调用不得发生，未闭合的
            # start 会让控制面把下一次同名动作判为 ambiguous_side_effect——
            # 失败保持可见，而不是静默放行。
            raise ConnectorError("receipt_attempt_missing", "回执缺少可寻址的执行身份")

        try:
            data, status_code = self.transport(
                connector.endpoint, {"operation": operation, "arguments": payload_args},
            )
        except Exception:  # noqa: BLE001 - 传输失败只给稳定码，不带正文
            if attempt:
                self.recorder.finish(
                    attempt, outcome="failure", evidence="",
                    check_ref=json.dumps({"connector": connector.name}),
                    failure="transport_error",
                )
            raise ConnectorError("transport_error", "连接器调用失败（详情已隐藏）") from None

        if type(status_code) is not int or not 100 <= status_code <= 599:
            if attempt:
                self.recorder.finish(
                    attempt, outcome="failure", evidence="",
                    check_ref=json.dumps({"connector": connector.name}),
                    failure="transport_status_invalid",
                )
            raise ConnectorError("transport_status_invalid", "传输未给出有效状态码")

        output_text = json.dumps(data, ensure_ascii=False, default=str)
        if len(output_text) > _MAX_OUTPUT_CHARS:
            output_text = output_text[:_MAX_OUTPUT_CHARS]
        binding = {
            "command_sha256": _canonical_sha256(
                {"endpoint": connector.endpoint, "operation": operation},
            ),
            "artifact_hashes_sha256": _canonical_sha256(payload_args),
            "output_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
            "exit_code": int(status_code),
            "execution_attempt": str(attempt or ""),
        }
        try:
            evidence = attach_evidence(manifest, binding)
        except ContractError:
            if attempt:
                self.recorder.finish(
                    attempt, outcome="failure", evidence="",
                    check_ref=json.dumps({"connector": connector.name}),
                    failure="evidence_incomplete",
                )
            raise ConnectorError(
                "evidence_incomplete", "证据绑定不满足 manifest 要求",
            ) from None

        closed = self.recorder.finish(
            attempt, outcome="success",
            evidence=json.dumps(evidence, ensure_ascii=False)[:120],
            check_ref=json.dumps({
                "connector": connector.name,
                "output_chars": len(output_text),
            })[:200],
            failure=None,
        )
        if closed is not True:
            raise ConnectorError("receipt_finish_failed", "回执终结失败")
        return ConnectorReceipt(
            connector=connector.name, operation=operation, ok=True,
            attempt=attempt, exit_code=int(status_code),
            output_chars=len(output_text),
            output_sha256=binding["output_sha256"], evidence=evidence,
        )


def http_transport(
    *,
    timeout: int = 60,
    proxy: str | None = None,
    no_proxy: bool = False,
) -> ConnectorTransport:
    """默认传输：复用既有 post_json（拒绝重定向、有界重试、公开错误边界）。

    成功路径即 2xx（失败以 ``ConnectorError("transport_error")`` 呈现），
    因此状态码固定为 200；非 2xx 与传输异常都在调用前收敛，不流入证据。
    """

    def transport(endpoint: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
        result = post_json(
            url=endpoint, payload=dict(payload), headers={},
            timeout=timeout, proxy=proxy, no_proxy=no_proxy,
        )
        return result.data, 200

    return transport


def build_connector(
    *,
    name: str,
    kind: str,
    endpoint: str,
    opclass: str = OPCLASS_EXTERNAL,
    evidence: frozenset[str] | set[str] | tuple[str, ...] = frozenset({
        "command_sha256", "artifact_hashes_sha256", "output_sha256", "exit_code",
    }),
) -> Connector:
    """按端点自动生成覆盖主机的网络副作用声明，组装 manifest 与连接器。"""
    host = _host_of(endpoint)
    if not host:
        raise ConnectorError("connector_endpoint", "endpoint 缺少主机")
    manifest = ExtensionManifest(
        name=name, version="1.0.0", kind="connector", source=endpoint[:_MAX_ENDPOINT],
        opclass=opclass,
        side_effects=(SideEffect(SIDE_EFFECT_NETWORK, host),),
        evidence=frozenset(evidence),
    )
    return Connector(name=name, kind=kind, endpoint=endpoint, manifest=manifest)
