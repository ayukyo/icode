"""证据包外部锚定（R7/W2）。

时序纪律（回应规格评审 B2）：
- 包内 ``anchors.json`` 只承载**签名前**已确定的预声明锚定意图
  （例如"将打 git-tag anchor/<digest前16>"），整体被签名覆盖；
- 签名**之后**实际完成的外部锚定（tag 真已打出去、CI 真已跑完）存在于
  包外世界（公开仓库历史 / CI job summary / 时间戳服务），第三方经外部
  渠道核查，**不回写进包**——回写会破坏签名，两头落空。

记录校验规则（类型词表、必填凭据、anchor_target == pack_digest 绑定）
的唯一真源在 ``pack_verify.validate_anchor_bundle``（第三方验证器内嵌
同一套规则），本模块只负责构造与落盘。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .pack_verify import validate_anchor_bundle

__all__ = [
    "AnchorError",
    "ANCHOR_TYPES",
    "build_git_tag_record",
    "build_ci_run_record",
    "build_rfc3161_record",
    "build_transparency_log_record",
    "validate_records",
    "attach_anchor_records",
]

ANCHOR_TYPES = ("git-tag", "ci-run", "rfc3161-file", "transparency-log-entry")
ANCHORS_SCHEMA_VERSION = 1

_HEX64_RE = re.compile(r"[0-9a-f]{64}")


class AnchorError(RuntimeError):
    """锚定流程失败（稳定消息前缀 ``pack-anchor/``）。"""


def _fail(message: str) -> AnchorError:
    return AnchorError(f"pack-anchor/{message}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_digest(pack_digest: object) -> str:
    if not isinstance(pack_digest, str) or not _HEX64_RE.fullmatch(pack_digest):
        raise _fail("pack_digest 必须是 64 位小写 hex")
    return pack_digest


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"{label} 必须是非空字符串")
    return value


def build_git_tag_record(
    pack_digest: str, repository: str, *, tag: str | None = None,
) -> dict:
    """预声明 git-tag 锚定：tag 名默认 anchor/<digest 前 16 hex>。"""
    _require_digest(pack_digest)
    _require_text(repository, "repository")
    tag = tag or f"anchor/{pack_digest[:16]}"
    if not tag.startswith("anchor/"):
        raise _fail("git-tag 锚定的 tag 必须以 anchor/ 前缀命名")
    return {
        "type": "git-tag",
        "anchor_target": pack_digest,
        "anchor_time": _now(),
        "evidence": {"tag": tag, "repository": repository},
    }


def build_ci_run_record(
    pack_digest: str, run_url: str, run_id: str, conclusion: str,
) -> dict:
    """预声明 ci-run 锚定（run URL 必须是 https）。"""
    _require_digest(pack_digest)
    _require_text(run_url, "run_url")
    if not run_url.startswith("https://"):
        raise _fail("run_url 必须是 https URL")
    _require_text(run_id, "run_id")
    _require_text(conclusion, "conclusion")
    return {
        "type": "ci-run",
        "anchor_target": pack_digest,
        "anchor_time": _now(),
        "evidence": {"run_url": run_url, "run_id": run_id, "conclusion": conclusion},
    }


def build_rfc3161_record(
    pack_digest: str, file_fingerprint: str, hash_algorithm: str = "sha256",
) -> dict:
    """预声明 RFC 3161 时间戳文件锚定（真实服务端接入属后续增量）。"""
    _require_digest(pack_digest)
    _require_text(file_fingerprint, "file_fingerprint")
    if not re.fullmatch(r"[0-9a-f]+", file_fingerprint) or len(file_fingerprint) < 16:
        raise _fail("file_fingerprint 必须是至少 16 位的 hex 指纹")
    _require_text(hash_algorithm, "hash_algorithm")
    return {
        "type": "rfc3161-file",
        "anchor_target": pack_digest,
        "anchor_time": _now(),
        "evidence": {
            "file_fingerprint": file_fingerprint,
            "hash_algorithm": hash_algorithm,
        },
    }


def build_transparency_log_record(
    pack_digest: str, log_id: str, entry_url: str,
) -> dict:
    """预声明透明日志条目锚定（如 Rekor；真实客户端属后续增量）。"""
    _require_digest(pack_digest)
    _require_text(log_id, "log_id")
    _require_text(entry_url, "entry_url")
    if not entry_url.startswith("https://"):
        raise _fail("entry_url 必须是 https URL")
    return {
        "type": "transparency-log-entry",
        "anchor_target": pack_digest,
        "anchor_time": _now(),
        "evidence": {"log_id": log_id, "entry_url": entry_url},
    }


def validate_records(records: list, pack_digest: str) -> list[str]:
    """按验证器同一规则校验记录列表（返回问题列表，空即通过）。"""
    bundle = {"schema_version": ANCHORS_SCHEMA_VERSION, "records": list(records)}
    return validate_anchor_bundle(bundle, pack_digest)


def attach_anchor_records(pack_dir: Path | str, records: list) -> Path:
    """把预声明锚定记录写为包内 anchors.json（签名前调用；拒绝覆盖）。

    必须在 ``build_evidence_pack`` 之后、``sign_pack`` 之前调用；写出的
    anchors.json 字节会进入签名消息。
    """
    pack = Path(pack_dir)
    manifest_path = pack / "manifest.json"
    if not manifest_path.is_file():
        raise _fail("证据包缺少 manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise _fail(f"manifest.json 不可解析：{type(exc).__name__}") from None
    pack_digest = manifest.get("pack_digest")
    _require_digest(pack_digest)
    target = pack / "anchors.json"
    if target.exists():
        raise _fail("anchors.json 已存在，拒绝覆盖（锚定意图不可改写）")
    bundle = {"schema_version": ANCHORS_SCHEMA_VERSION, "records": list(records)}
    problems = validate_anchor_bundle(bundle, pack_digest)
    if problems:
        raise _fail("锚定记录校验失败：" + "；".join(problems))
    target.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return target
