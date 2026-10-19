"""角色上下文派生：只读角色只紧不松、边界指纹可算不可自报（R6/W3）。"""

import unittest
from dataclasses import replace
from pathlib import Path

from icode.agent_scope import (
    derive_agent_guard_scope,
    derive_agent_policy,
    scope_fingerprint,
)
from icode.guard import Scope
from icode.roles import RoleError
from icode.sandbox_policy import NetworkMode, SandboxPolicy


def _policy(**overrides: object) -> SandboxPolicy:
    workspace = Path("/tmp/icode-r6-ws")
    values: dict[str, object] = dict(
        schema_version=1, run_id="run-001", ticket_id="ICODE-31", step="code",
        workspace_root=workspace, read_roots=(workspace,), write_roots=(workspace,),
        deny_read_roots=(workspace / ".git",),
        deny_write_roots=(workspace / ".git",),
        network_mode=NetworkMode.DENY, allowed_domains=(),
        process_limit=32, wall_timeout_seconds=600, output_limit_bytes=4 * 1024 * 1024,
        protected_paths=(workspace / ".git",),
    )
    values.update(overrides)
    return SandboxPolicy(**values)


def _scope() -> Scope:
    workspace = Path("/tmp/icode-r6-ws")
    return Scope(workspace_root=workspace, allowed_write_roots=(workspace,))


class TestPolicyDerivation(unittest.TestCase):
    def test_只读角色写根清空且网络拒绝(self) -> None:
        base = _policy(
            network_mode=NetworkMode.PROXY_ALLOWLIST,
            allowed_domains=("pypi.org",),
        )
        for role_name in ("reviewer", "verifier", "auditor", "planner"):
            with self.subTest(role=role_name):
                derived = derive_agent_policy(base, role_name,
                                              deny_read_roots=(base.workspace_root / "out",))
                self.assertEqual(derived.write_roots, ())
                self.assertEqual(derived.network_mode, NetworkMode.DENY)
                self.assertEqual(derived.allowed_domains, ())
                self.assertIn(base.workspace_root / "out", derived.deny_read_roots)
                # 只紧不松：派生结果必须仍是基座的合法收紧
                from icode.sandbox_policy import tighten_policy
                self.assertEqual(tighten_policy(base, derived), derived)

    def test_executor保留基座写范围(self) -> None:
        base = _policy()
        self.assertIs(derive_agent_policy(base, "executor"), base)

    def test_未知角色fail_closed(self) -> None:
        with self.assertRaises(RoleError) as caught:
            derive_agent_policy(_policy(), "boss")
        self.assertEqual(caught.exception.code, "unknown_role")

    def test_基座非法拒绝派生(self) -> None:
        with self.assertRaises(RoleError):
            derive_agent_policy("not-a-policy", "reviewer")  # type: ignore[arg-type]


class TestGuardScopeDerivation(unittest.TestCase):
    def test_只读角色无写根(self) -> None:
        base = _scope()
        for role_name in ("reviewer", "verifier", "auditor", "planner"):
            with self.subTest(role=role_name):
                derived = derive_agent_guard_scope(base, role_name)
                self.assertEqual(derived.allowed_write_roots, ())
                self.assertEqual(derived.workspace_root, base.workspace_root)

    def test_executor保留原作用域(self) -> None:
        base = _scope()
        self.assertIs(derive_agent_guard_scope(base, "executor"), base)


class TestContextFingerprint(unittest.TestCase):
    def test_边界变化即指纹变化且稳定可复算(self) -> None:
        first = scope_fingerprint(_scope())
        again = scope_fingerprint(_scope())
        self.assertEqual(first, again)
        narrowed = derive_agent_guard_scope(_scope(), "reviewer")
        self.assertNotEqual(scope_fingerprint(narrowed), first)

    def test_策略指纹与作用域指纹不同源不混用(self) -> None:
        policy_digest = _policy().policy_hash
        scope_digest = scope_fingerprint(_scope())
        self.assertEqual(len(policy_digest), 64)
        self.assertEqual(len(scope_digest), 64)
        self.assertNotEqual(policy_digest, scope_digest)


if __name__ == "__main__":
    unittest.main()
