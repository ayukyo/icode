"""证据包 Ed25519 签名（R7/W1）。

签名消息 = ``SIGNATURE_MESSAGE_PREFIX + manifest.json 完整文件字节``
（当包内存在 ``anchors.json`` 时再追加 ``b"\\nanchors.json\\n" + 其字节``）。

``signature.json`` / ``anchors.json`` 是清单外豁免文件（与 ``manifest.json``
同等待遇，见 pack_verify ⑤），不参与 manifest.files 哈希，但被本签名覆盖。

私钥文件是 64 位小写 hex 的 32 字节 Ed25519 种子（RFC 8032），POSIX 下强制
0600 权限。私钥与明文种子绝不进入证据包、日志或返回值。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from .pack_verify import (
    SIGNATURE_MESSAGE_PREFIX,
    ed25519_public_key,
    ed25519_sign,
    ed25519_verify,
)

__all__ = [
    "SigningError",
    "generate_signing_key",
    "public_key_hex",
    "key_fingerprint",
    "write_signing_key",
    "read_signing_key",
    "sign_pack",
]

_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_MAX_ANCHORS_BYTES = 256 * 1024
_KEY_FILE_MODE = 0o600


class SigningError(RuntimeError):
    """签名流程失败（稳定消息前缀 ``pack-signing/``）。"""


def _fail(message: str) -> SigningError:
    return SigningError(f"pack-signing/{message}")


def generate_signing_key() -> bytes:
    """生成 32 字节 Ed25519 种子（os.urandom，不经任何派生）。"""
    return os.urandom(32)


def public_key_hex(seed: bytes) -> str:
    return ed25519_public_key(seed).hex()


def key_fingerprint(public_key: str) -> str:
    """人读提示（sha256 前 16 hex）；不是信任依据（信任走带外公钥核对）。"""
    return hashlib.sha256(bytes.fromhex(public_key)).hexdigest()[:16]


def write_signing_key(seed: bytes, path: Path | str) -> Path:
    """把种子写成 hex 私钥文件：O_EXCL 拒绝覆盖，POSIX 0600。"""
    if len(seed) != 32:
        raise _fail("私钥种子必须是 32 字节")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _KEY_FILE_MODE)
    except FileExistsError:
        raise _fail("私钥文件已存在，拒绝覆盖") from None
    try:
        os.write(fd, seed.hex().encode("ascii") + b"\n")
    finally:
        os.close(fd)
    if os.name == "posix":
        os.chmod(path, _KEY_FILE_MODE)
    return path


def read_signing_key(path: Path | str) -> bytes:
    """读取并校验私钥文件（64 位 hex；POSIX 下拒绝权限过宽）。"""
    path = Path(path)
    try:
        text = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail(f"私钥文件不可读：{type(exc).__name__}") from None
    if not _HEX64_RE.fullmatch(text):
        raise _fail("私钥文件必须是 64 位小写 hex 的 32 字节种子")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise _fail("私钥文件权限过宽（要求 0600）")
    return bytes.fromhex(text)


def sign_pack(pack_dir: Path | str, signing_key_path: Path | str) -> dict:
    """对证据包 manifest（及声明纳入的 anchors.json）签名，写 signature.json。

    返回写入的签名记录（不含任何私钥材料）。重复签名会覆盖旧 signature.json
    （签名只覆盖 manifest/anchors 字节，重签不改变证据内容）。
    """
    pack = Path(pack_dir)
    manifest_path = pack / "manifest.json"
    if not manifest_path.is_file():
        raise _fail("证据包缺少 manifest.json")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise _fail(f"manifest.json 不可解析：{type(exc).__name__}") from None
    if len(manifest_bytes) > _MAX_MANIFEST_BYTES:
        raise _fail("manifest.json 超过安全上限")
    pack_digest = manifest.get("pack_digest")
    if not isinstance(pack_digest, str) or not _HEX64_RE.fullmatch(pack_digest):
        raise _fail("manifest.json 缺少有效 pack_digest")

    anchors_path = pack / "anchors.json"
    anchors_included = anchors_path.is_file()
    message = SIGNATURE_MESSAGE_PREFIX + manifest_bytes
    if anchors_included:
        try:
            anchors_bytes = anchors_path.read_bytes()
        except OSError as exc:
            raise _fail(f"anchors.json 不可读：{type(exc).__name__}") from None
        if len(anchors_bytes) > _MAX_ANCHORS_BYTES:
            raise _fail("anchors.json 超过安全上限")
        message += b"\nanchors.json\n" + anchors_bytes

    seed = read_signing_key(signing_key_path)
    public = ed25519_public_key(seed)
    public_hex = public.hex()
    signature = ed25519_sign(seed, message)
    if not ed25519_verify(public, message, signature):
        raise _fail("签名后自校验失败（实现缺陷，拒绝发布）")
    record = {
        "schema_version": 1,
        "algorithm": "ed25519",
        "public_key": public_hex,
        "signature": signature.hex(),
        "key_fingerprint": key_fingerprint(public_hex),
        "signed_object": "manifest.json",
        "signed_digest": pack_digest,
        "anchors_included": anchors_included,
        "signed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (pack / "signature.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return record
