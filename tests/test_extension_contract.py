"""扩展契约：声明不全即不可执行；控制面/账本不可声明（R5/W1）。"""

import unittest

from icode.extension_contract import (
    ContractError,
    ExtensionManifest,
    ExtensionRegistry,
    SideEffect,
    attach_evidence,
    tighten_guard_scope,
)
from icode.tools.base import OPCLASS_EXTERNAL, OPCLASS_MANAGED_WRITE, OPCLASS_READ_ONLY


def _manifest(**overrides):
    base = {
        "name": "jira-connector",
        "version": "1.0.0",
        "kind": "connector",
        "source": "vendor/icode-skill/extensions/jira",
        "opclass": OPCLASS_EXTERNAL,
        "description": "工单连接器",
        "inputs": {"issue": {"type": "string"}},
        "outputs": {"receipt": {"type": "object"}},
        "side_effects": (SideEffect("network", "jira.example.com"),),
        "evidence": frozenset({"command_sha256", "output_sha256", "exit_code"}),
    }
    base.update(overrides)
    return ExtensionManifest(**base)


class TestManifestValidation(unittest.TestCase):
    def test_完整声明可注册且投影只含声明(self) -> None:
        registry = ExtensionRegistry()
        manifest = registry.register(_manifest())
        self.assertEqual(registry.names(), ["jira-connector"])
        self.assertIs(registry.assert_executable("jira-connector"), manifest)
        projection = manifest.as_dict()
        self.assertEqual(projection["opclass"], OPCLASS_EXTERNAL)
        self.assertEqual(projection["evidence"],
                         ["command_sha256", "exit_code", "output_sha256"])
        self.assertEqual(projection["side_effects"],
                         [{"kind": "network", "target": "jira.example.com"}])
        self.assertNotIn("token", projection)

    def test_未声明证据要求默认不可执行(self) -> None:
        with self.assertRaises(ContractError) as caught:
            _manifest(evidence=frozenset())
        self.assertIn("manifest_evidence_empty", str(caught.exception))

    def test_证据词表外字段被拒绝(self) -> None:
        with self.assertRaises(ContractError) as caught:
            _manifest(evidence=frozenset({"sha256"}))
        self.assertIn("manifest_unknown_evidence", str(caught.exception))

    def test_权限档位必须是四档之一(self) -> None:
        with self.assertRaises(ContractError) as caught:
            _manifest(opclass="root")
        self.assertIn("manifest_unknown_opclass", str(caught.exception))

    def test_扩展类型必须是已知四种(self) -> None:
        with self.assertRaises(ContractError) as caught:
            _manifest(kind="plugin")
        self.assertIn("manifest_unknown_kind", str(caught.exception))

    def test_名称形态受限(self) -> None:
        with self.assertRaises(ContractError) as caught:
            _manifest(name="Jira Connector")
        self.assertIn("manifest_invalid_name", str(caught.exception))

    def test_副作用指向账本即拒绝(self) -> None:
        for target in (".ico_events.jsonl", ".icode_output_x/.ico_metadata.json"):
            with self.subTest(target=target):
                with self.assertRaises(ContractError) as caught:
                    _manifest(side_effects=(SideEffect("file_write", target),))
                self.assertIn("控制面/账本不是可声明目标", str(caught.exception))

    def test_副作用拒绝绝对路径与父目录逃逸(self) -> None:
        for target in ("/etc/passwd", "../outside.txt", "~/secrets.txt", "C:/Windows/x"):
            with self.subTest(target=target):
                with self.assertRaises(ContractError):
                    _manifest(side_effects=(SideEffect("file_write", target),))

    def test_网络副作用只接受域名特征(self) -> None:
        with self.assertRaises(ContractError):
            _manifest(side_effects=(SideEffect("network", "https://jira.example.com/x"),))
        manifest = _manifest(
            side_effects=(SideEffect("network", "jira.example.com"),),
        )
        self.assertEqual(manifest.side_effects[0].target, "jira.example.com")

    def test_未知副作用类型不在词表内(self) -> None:
        with self.assertRaises(ContractError) as caught:
            _manifest(side_effects=(SideEffect("ledger_write", "x"),))
        self.assertIn("manifest_unknown_side_effect", str(caught.exception))

    def test_同名扩展重复注册被拒绝(self) -> None:
        registry = ExtensionRegistry()
        registry.register(_manifest())
        with self.assertRaises(ContractError) as caught:
            registry.register(_manifest())
        self.assertIn("manifest_duplicate", str(caught.exception))

    def test_未注册扩展不可执行(self) -> None:
        registry = ExtensionRegistry()
        with self.assertRaises(ContractError) as caught:
            registry.assert_executable("ghost")
        self.assertIn("extension_not_registered", str(caught.exception))


class TestEvidenceAttachment(unittest.TestCase):
    def test_证据缺项拒绝落账(self) -> None:
        manifest = _manifest()
        with self.assertRaises(ContractError) as caught:
            attach_evidence(manifest, {"command_sha256": "a" * 64})
        self.assertIn("evidence_incomplete", str(caught.exception))

    def test_证据齐全返回有界绑定(self) -> None:
        manifest = _manifest()
        binding = {
            "command_sha256": "a" * 64,
            "output_sha256": "b" * 64,
            "exit_code": 0,
            "unrelated": "忽略",
        }
        attached = attach_evidence(manifest, binding)
        self.assertEqual(sorted(attached), ["command_sha256", "exit_code", "output_sha256"])
        self.assertNotIn("unrelated", attached)


class TestGuardTighteningOnly(unittest.TestCase):
    def test_只收紧的候选被接受(self) -> None:
        deny, allow = tighten_guard_scope(
            {"rm -rf /"}, {"python", "make"}, {"rm -rf /", "git clean -fdx"}, {"python"},
        )
        self.assertEqual(deny, frozenset({"rm -rf /", "git clean -fdx"}))
        self.assertEqual(allow, frozenset({"python"}))

    def test_移除既有拒绝被拒绝(self) -> None:
        with self.assertRaises(ContractError) as caught:
            tighten_guard_scope({"rm -rf /"}, {"python"}, set(), {"python"})
        self.assertIn("guard_tightening_removes_deny", str(caught.exception))

    def test_扩张白名单被拒绝(self) -> None:
        with self.assertRaises(ContractError) as caught:
            tighten_guard_scope(set(), {"python"}, set(), {"python", "curl"})
        self.assertIn("guard_tightening_expands_allowlist", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
