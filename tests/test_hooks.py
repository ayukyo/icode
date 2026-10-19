"""生命周期 Hooks：只收紧、不放宽；未注册不可执行（R5/W2）。"""

import unittest
from dataclasses import replace
from pathlib import Path

from icode.extension_contract import (
    ExtensionManifest,
    ExtensionRegistry,
    SideEffect,
)
from icode.hooks import (
    HOOK_OBSERVE,
    HOOK_PRE_STEP,
    HOOK_PRE_TOOL,
    Hook,
    HookError,
    HookRegistry,
    apply_guard_tightenings,
    apply_policy_tightenings,
    run_observers,
)
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.tools.base import OPCLASS_READ_ONLY


def _hook_manifest(name: str) -> ExtensionManifest:
    return ExtensionManifest(
        name=name,
        version="1.0.0",
        kind="hook",
        source="vendor/icode-skill/extensions/hooks",
        opclass=OPCLASS_READ_ONLY,
        side_effects=(),
        evidence=frozenset({"output_sha256"}),
    )


class _HookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.manifests = ExtensionRegistry()
        self.registry = HookRegistry(self.manifests)

    def _register(self, name: str) -> None:
        self.manifests.register(_hook_manifest(name))


class TestGuardTighteningOnly(_HookTestCase):
    def test_deny只加白名单只减被接受且单调(self) -> None:
        self._register("deny-more")
        self.registry.register(Hook(
            name="deny-more", event=HOOK_PRE_TOOL,
            tighten=lambda deny, allow: (deny | {"git clean -fdx"}, allow - {"make"}),
        ))
        deny, allow, audit = apply_guard_tightenings(
            self.registry.hooks_for(HOOK_PRE_TOOL), {"rm -rf /"}, {"make", "python"},
        )
        self.assertEqual(allow, {"python"})
        self.assertIn("git clean -fdx", deny)
        self.assertEqual(audit, [{"hook": "deny-more", "event": HOOK_PRE_TOOL, "applied": True}])

    def test_移除既有拒绝被拒绝并留审计(self) -> None:
        self._register("drop-deny")
        self.registry.register(Hook(
            name="drop-deny", event=HOOK_PRE_TOOL,
            tighten=lambda deny, allow: (deny - {"rm -rf /"}, allow),
        ))
        deny, allow, audit = apply_guard_tightenings(
            self.registry.hooks_for(HOOK_PRE_TOOL), {"rm -rf /"}, {"python"},
        )
        self.assertEqual(deny, {"rm -rf /"})
        self.assertEqual(allow, {"python"})
        self.assertFalse(audit[0]["applied"])
        self.assertEqual(audit[0]["code"], "guard_tightening_removes_deny")

    def test_扩张白名单被拒绝(self) -> None:
        self._register("add-allow")
        self.registry.register(Hook(
            name="add-allow", event=HOOK_PRE_TOOL,
            tighten=lambda deny, allow: (deny, allow | {"curl"}),
        ))
        _, allow, audit = apply_guard_tightenings(
            self.registry.hooks_for(HOOK_PRE_TOOL), set(), {"python"},
        )
        self.assertEqual(allow, {"python"})
        self.assertEqual(audit[0]["code"], "guard_tightening_expands_allowlist")

    def test_候选形状非法被拒绝且不影响其他hook(self) -> None:
        self._register("bad-shape")
        self._register("good-shape")
        self.registry.register(Hook(
            name="bad-shape", event=HOOK_PRE_TOOL, tighten=lambda deny, allow: "nope",
        ))
        self.registry.register(Hook(
            name="good-shape", event=HOOK_PRE_TOOL,
            tighten=lambda deny, allow: (deny | {"dd if=/dev/zero"}, allow),
        ))
        _, _, audit = apply_guard_tightenings(
            self.registry.hooks_for(HOOK_PRE_TOOL), set(), {"python"},
        )
        self.assertFalse(audit[0]["applied"])
        self.assertTrue(audit[1]["applied"])


class TestPolicyTighteningOnly(_HookTestCase):
    def _policy(self, **overrides: object) -> SandboxPolicy:
        workspace = Path("/tmp/icode-hook-ws")
        values: dict[str, object] = {
            "schema_version": 1,
            "run_id": "run-001",
            "ticket_id": "ICODE-25",
            "step": "code",
            "workspace_root": workspace,
            "read_roots": (workspace,),
            "write_roots": (workspace,),
            "deny_read_roots": (workspace / ".git",),
            "deny_write_roots": (workspace / ".git",),
            "network_mode": NetworkMode.DENY,
            "allowed_domains": (),
            "process_limit": 32,
            "wall_timeout_seconds": 600,
            "output_limit_bytes": 4 * 1024 * 1024,
            "protected_paths": (workspace / ".git",),
        }
        values.update(overrides)
        return SandboxPolicy(**values)

    def test_收窄写根与降低限额被接受(self) -> None:
        self._register("narrow")
        base = self._policy()
        self.registry.register(Hook(
            name="narrow", event=HOOK_PRE_STEP,
            tighten=lambda policy: replace(
                policy, write_roots=(policy.workspace_root / "src",), process_limit=8,
            ),
        ))
        tightened, audit = apply_policy_tightenings(
            self.registry.hooks_for(HOOK_PRE_STEP), base,
        )
        self.assertEqual(tightened.write_roots, (base.workspace_root / "src",))
        self.assertEqual(tightened.process_limit, 8)
        self.assertTrue(audit[0]["applied"])

    def test_放宽网络被拒绝(self) -> None:
        self._register("open-net")
        base = self._policy()
        self.registry.register(Hook(
            name="open-net", event=HOOK_PRE_STEP,
            tighten=lambda policy: replace(
                policy, network_mode=NetworkMode.PROXY_ALLOWLIST,
                allowed_domains=("pypi.org",),
            ),
        ))
        tightened, audit = apply_policy_tightenings(
            self.registry.hooks_for(HOOK_PRE_STEP), base,
        )
        self.assertEqual(tightened.network_mode, NetworkMode.DENY)
        self.assertFalse(audit[0]["applied"])

    def test_扩大写根被拒绝(self) -> None:
        self._register("widen")
        base = replace(
            self._policy(), write_roots=(self._policy().workspace_root / "src",),
        )
        self.registry.register(Hook(
            name="widen", event=HOOK_PRE_STEP,
            tighten=lambda policy: replace(policy, write_roots=(policy.workspace_root,)),
        ))
        _, audit = apply_policy_tightenings(
            self.registry.hooks_for(HOOK_PRE_STEP), base,
        )
        self.assertFalse(audit[0]["applied"])

    def test_收紧不得改身份字段(self) -> None:
        self._register("rename")
        base = self._policy()
        self.registry.register(Hook(
            name="rename", event=HOOK_PRE_STEP,
            tighten=lambda policy: replace(policy, run_id="run-002"),
        ))
        _, audit = apply_policy_tightenings(
            self.registry.hooks_for(HOOK_PRE_STEP), base,
        )
        self.assertFalse(audit[0]["applied"])


class TestHookBindingGate(_HookTestCase):
    def test_未注册manifest的hook不可注册(self) -> None:
        with self.assertRaises(HookError) as caught:
            self.registry.register(Hook(name="ghost", event=HOOK_PRE_TOOL,
                                        tighten=lambda d, a: (d, a)))
        self.assertIn("hook_not_registered", str(caught.exception))

    def test_manifest类型不是hook被拒绝(self) -> None:
        self.manifests.register(ExtensionManifest(
            name="tool-like", version="1.0.0", kind="tool",
            source="vendor/icode-skill/extensions/x", opclass=OPCLASS_READ_ONLY,
            evidence=frozenset({"output_sha256"}),
        ))
        with self.assertRaises(HookError) as caught:
            self.registry.register(Hook(name="tool-like", event=HOOK_PRE_TOOL,
                                        tighten=lambda d, a: (d, a)))
        self.assertIn("hook_manifest_kind_mismatch", str(caught.exception))

    def test_未知事件不在词表内(self) -> None:
        with self.assertRaises(HookError) as caught:
            Hook(name="x", event="gates", tighten=lambda d, a: (d, a))
        self.assertIn("hook_event_unknown", str(caught.exception))

    def test_收紧型hook缺少构造器被拒绝(self) -> None:
        with self.assertRaises(HookError) as caught:
            Hook(name="x", event=HOOK_PRE_TOOL)
        self.assertIn("hook_tighten_missing", str(caught.exception))


class TestObservers(_HookTestCase):
    def test_观察者收到事件且异常不中断(self) -> None:
        seen: list[tuple[str, dict]] = []
        self._register("watch")
        self._register("broken")
        self.registry.register(Hook(
            name="watch", event=HOOK_OBSERVE,
            observe=lambda name, payload: seen.append((name, dict(payload))),
        ))
        self.registry.register(Hook(
            name="broken", event=HOOK_OBSERVE,
            observe=lambda name, payload: 1 / 0,
        ))
        audit = run_observers(
            self.registry.hooks_for(HOOK_OBSERVE), "tool_result", {"tool": "read_file"},
        )
        self.assertEqual(seen, [("tool_result", {"tool": "read_file"})])
        self.assertEqual([item["hook"] for item in audit], ["broken", "watch"])
        self.assertTrue(audit[1]["applied"])
        self.assertFalse(audit[0]["applied"])

    def test_观察载荷超限被拒绝(self) -> None:
        self._register("watch")
        self.registry.register(Hook(
            name="watch", event=HOOK_OBSERVE, observe=lambda name, payload: None,
        ))
        with self.assertRaises(HookError) as caught:
            run_observers(
                self.registry.hooks_for(HOOK_OBSERVE), "tool_result",
                {"blob": "x" * 5000},
            )
        self.assertIn("hook_observe_payload", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
