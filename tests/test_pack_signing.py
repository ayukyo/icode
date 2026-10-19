"""R7/W1：纯 Python Ed25519（RFC 8032）与证据包签名。

向量来源：RFC 8032 §7.1（Ed25519 三条 + SHA(abc) 已知答案）、§7.2（Ed25519ctx
"foo" 条）、§7.3（Ed25519ph "TEST abc" 条）。§7.2/§7.3 公式核对：r 与 k 均
拼接 dom4，r 额外拼接种子扩展前缀（sha512(seed)[32:]）。
"""

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from icode import pack_signing
from icode.pack_signing import (
    SigningError,
    generate_signing_key,
    key_fingerprint,
    public_key_hex,
    read_signing_key,
    sign_pack,
    write_signing_key,
)
from icode.pack_verify import (
    SIGNATURE_NAME,
    _signature_problems,
    ed25519_public_key,
    ed25519_sign,
    ed25519_verify,
    ed25519ctx_sign,
    ed25519ctx_verify,
    ed25519ph_sign,
    ed25519ph_verify,
)

# RFC 8032 §7.1 TEST 1-3 + SHA(abc)
PLAIN_VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    ("833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
     "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
     hashlib.sha512(b"abc").hexdigest(),
     "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
     "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704"),
]

# RFC 8032 §7.2 "foo"（Ed25519ctx）与 §7.3 "TEST abc"（Ed25519ph）
CTX_SK = "0305334e381af78f141cb666f6199f57bc3495335a256a95bd2a55bf546663f6"
CTX_PK = "dfc9425e4f968f7f0c29f0259cf5f9aed6851c2bb4ad8bfb860cfee0ab248292"
CTX_MSG = "f726936d19c800494e3fdaff20b276a8"
CTX_SIG = ("55a4cc2f70a54e04288c5f4cd1e45a7bb520b36292911876cada7323198dd87a"
           "8b36950b95130022907a7fb7c4e9b2d5f6cca685a587b4b21f4b888e4e7edb0d")
PH_SK = "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42"
PH_PK = "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf"
PH_SIG = ("98a70222f0b8121aa9d30f813d683f809e462b469c7ff87639499bb94e6dae41"
          "31f85042463c2a355a2003d062adf5aaa10b8c61e636062aaad11c2a26083406")

SENTINEL_SEED = "contract-secret-marker-not-a-key"


def _write_manifest(root: Path, pack_digest: str) -> Path:
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps({"pack_digest": pack_digest, "ticket": {"ticket_id": "r7"}},
                   ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


class Ed25519VectorTests(unittest.TestCase):
    def test_rfc8032_plain_vectors(self):
        for index, (sk, pk, msg, sig) in enumerate(PLAIN_VECTORS, 1):
            seed = bytes.fromhex(sk)
            with self.subTest(vector=index):
                self.assertEqual(ed25519_public_key(seed).hex(), pk)
                self.assertEqual(ed25519_sign(seed, bytes.fromhex(msg)).hex(), sig)
                self.assertTrue(
                    ed25519_verify(bytes.fromhex(pk), bytes.fromhex(msg),
                                   bytes.fromhex(sig)))
                tampered = bytearray(bytes.fromhex(sig))
                tampered[10] ^= 1
                self.assertFalse(
                    ed25519_verify(bytes.fromhex(pk), bytes.fromhex(msg),
                                   bytes(tampered)))

    def test_rfc8032_ctx_vector_and_separation(self):
        seed, pk, msg = bytes.fromhex(CTX_SK), bytes.fromhex(CTX_PK), bytes.fromhex(CTX_MSG)
        self.assertEqual(ed25519ctx_sign(seed, b"foo", msg).hex(), CTX_SIG)
        self.assertTrue(ed25519ctx_verify(pk, b"foo", msg, bytes.fromhex(CTX_SIG)))
        other = ed25519ctx_sign(seed, b"bar", msg)
        self.assertNotEqual(other.hex(), CTX_SIG)
        self.assertTrue(ed25519ctx_verify(pk, b"bar", msg, other))
        self.assertFalse(ed25519ctx_verify(pk, b"bar", msg, bytes.fromhex(CTX_SIG)))
        self.assertFalse(ed25519_verify(pk, msg, bytes.fromhex(CTX_SIG)))

    def test_rfc8032_ph_vector(self):
        seed, pk = bytes.fromhex(PH_SK), bytes.fromhex(PH_PK)
        self.assertEqual(ed25519ph_sign(seed, b"", b"abc").hex(), PH_SIG)
        self.assertTrue(ed25519ph_verify(pk, b"", b"abc", bytes.fromhex(PH_SIG)))

    def test_non_canonical_s_rejected(self):
        _, pk, msg, sig = PLAIN_VECTORS[0]
        bad = bytearray(bytes.fromhex(sig))
        bad[32] |= 0x80  # s >= L
        self.assertFalse(ed25519_verify(bytes.fromhex(pk), b"", bytes(bad)))

    def test_garbage_public_key_rejected(self):
        self.assertFalse(ed25519_verify(b"\x00" * 32, b"", bytes(64)))
        self.assertFalse(ed25519_verify(b"short", b"", bytes(64)))
        self.assertFalse(ed25519_verify(bytes(32), b"", b"short"))


class KeyFileTests(unittest.TestCase):
    def test_write_read_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-key-") as raw:
            root = Path(raw)
            seed = generate_signing_key()
            key_path = root / "sub" / "signing.key"
            write_signing_key(seed, key_path)
            self.assertEqual(read_signing_key(key_path), seed)
            with self.assertRaises(SigningError):
                write_signing_key(generate_signing_key(), key_path)

    def test_generated_seed_is_32_bytes(self):
        self.assertEqual(len(generate_signing_key()), 32)

    def test_bad_key_file_rejected(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-key-") as raw:
            path = Path(raw) / "bad.key"
            path.write_text(SENTINEL_SEED + "\n", encoding="ascii")
            with self.assertRaises(SigningError):
                read_signing_key(path)

    @unittest.skipUnless(os.name == "posix", "POSIX 权限位断言")
    def test_key_file_mode_restricted(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-key-") as raw:
            path = Path(raw) / "signing.key"
            write_signing_key(generate_signing_key(), path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0)
            path.chmod(0o644)
            with self.assertRaises(SigningError):
                read_signing_key(path)


class SignPackTests(unittest.TestCase):
    def test_sign_and_verify_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-pack-") as raw:
            root = Path(raw)
            digest = "ab" * 32
            manifest_path = _write_manifest(root, digest)
            key_path = root / "signing.key"
            write_signing_key(generate_signing_key(), key_path)
            record = sign_pack(root, key_path)
            self.assertEqual(
                set(record),
                {"schema_version", "algorithm", "public_key", "signature",
                 "key_fingerprint", "signed_object", "signed_digest",
                 "anchors_included", "signed_at"},
            )
            self.assertEqual(record["signed_digest"], digest)
            self.assertEqual(record["algorithm"], "ed25519")
            self.assertEqual(record["key_fingerprint"],
                             key_fingerprint(record["public_key"]))
            # 私钥材料绝不出现
            sig_file = json.loads((root / SIGNATURE_NAME).read_text(encoding="utf-8"))
            seed_hex = read_signing_key(key_path).hex()
            self.assertNotIn(seed_hex, json.dumps(sig_file))
            # 验证：完整字节验签通过
            problems = _signature_problems(
                json.loads(manifest_path.read_text(encoding="utf-8")),
                root / SIGNATURE_NAME, manifest_path, None,
                record["public_key"],
            )
            self.assertEqual(problems, [])

    def test_tampered_manifest_fails_verification(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-pack-") as raw:
            root = Path(raw)
            manifest_path = _write_manifest(root, "ab" * 32)
            key_path = root / "signing.key"
            write_signing_key(generate_signing_key(), key_path)
            record = sign_pack(root, key_path)
            tampered = manifest_path.read_bytes() + b" "  # JSON 仍可解析，字节已变
            manifest_path.write_bytes(tampered)
            manifest = json.loads(tampered.decode("utf-8"))
            problems = _signature_problems(
                manifest, root / SIGNATURE_NAME, manifest_path, None,
                record["public_key"],
            )
            self.assertTrue(any("签名验证失败" in p for p in problems), problems)

    def test_wrong_public_key_fails(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-pack-") as raw:
            root = Path(raw)
            manifest_path = _write_manifest(root, "cd" * 32)
            key_path = root / "signing.key"
            write_signing_key(generate_signing_key(), key_path)
            record = sign_pack(root, key_path)
            other = ed25519_public_key(generate_signing_key()).hex()
            problems = _signature_problems(
                json.loads(manifest_path.read_text(encoding="utf-8")),
                root / SIGNATURE_NAME, manifest_path, None, other,
            )
            self.assertTrue(any("公钥不一致" in p for p in problems), problems)

    def test_closed_field_set_enforced(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-pack-") as raw:
            root = Path(raw)
            manifest_path = _write_manifest(root, "ef" * 32)
            key_path = root / "signing.key"
            write_signing_key(generate_signing_key(), key_path)
            sign_pack(root, key_path)
            record = json.loads((root / SIGNATURE_NAME).read_text(encoding="utf-8"))
            public_key = record["public_key"]
            for mutate, label in (
                (lambda r: r.pop("signed_at"), "缺字段"),
                (lambda r: r.update({"extra": 1}), "多字段"),
                (lambda r: r.update({"schema_version": 99}), "坏版本"),
                (lambda r: r.update({"signature": "zz" * 64}), "坏签名"),
            ):
                with self.subTest(label=label):
                    mutated = json.loads(json.dumps(record))
                    mutate(mutated)
                    (root / SIGNATURE_NAME).write_text(
                        json.dumps(mutated), encoding="utf-8")
                    problems = _signature_problems(
                        json.loads(manifest_path.read_text(encoding="utf-8")),
                        root / SIGNATURE_NAME, manifest_path, None, public_key,
                    )
                    self.assertTrue(problems, label)

    def test_missing_public_key_refuses_verification(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-pack-") as raw:
            root = Path(raw)
            manifest_path = _write_manifest(root, "12" * 32)
            key_path = root / "signing.key"
            write_signing_key(generate_signing_key(), key_path)
            sign_pack(root, key_path)
            problems = _signature_problems(
                json.loads(manifest_path.read_text(encoding="utf-8")),
                root / SIGNATURE_NAME, manifest_path, None, None,
            )
            self.assertTrue(any("未提供" in p for p in problems), problems)

    def test_sign_requires_manifest_with_digest(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-pack-") as raw:
            root = Path(raw)
            key_path = root / "signing.key"
            write_signing_key(generate_signing_key(), key_path)
            with self.assertRaises(SigningError):
                sign_pack(root, key_path)
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(SigningError):
                sign_pack(root, key_path)

    def test_anchors_binding_into_signature(self):
        with tempfile.TemporaryDirectory(prefix="icode-r7-pack-") as raw:
            root = Path(raw)
            digest = "34" * 32
            manifest_path = _write_manifest(root, digest)
            key_path = root / "signing.key"
            write_signing_key(generate_signing_key(), key_path)
            anchors_path = root / "anchors.json"
            anchors_path.write_text(
                json.dumps({"schema_version": 1, "records": []}), encoding="utf-8")
            record = sign_pack(root, key_path)
            self.assertTrue(record["anchors_included"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(_signature_problems(
                manifest, root / SIGNATURE_NAME, manifest_path, anchors_path,
                record["public_key"]), [])
            # 换包重贴：把另一包的 anchors 字节贴进来 → 验签失败
            anchors_path.write_text(
                json.dumps({"schema_version": 1, "records": [{"x": 1}]}),
                encoding="utf-8")
            problems = _signature_problems(
                manifest, root / SIGNATURE_NAME, manifest_path, anchors_path,
                record["public_key"])
            self.assertTrue(any("签名验证失败" in p for p in problems), problems)
            # 签名声明不含 anchors 但包内出现 → 覆盖不完整
            (root / "anchors.json").rename(root / "anchors.bak")
            record2 = sign_pack(root, key_path)
            self.assertFalse(record2["anchors_included"])
            (root / "anchors.bak").rename(root / "anchors.json")
            problems = _signature_problems(
                manifest, root / SIGNATURE_NAME, manifest_path,
                root / "anchors.json", record2["public_key"])
            self.assertTrue(any("覆盖不完整" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
