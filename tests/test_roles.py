"""角色契约与身份：封闭词表、只读默认、无扩权无委派（R6/W1）。"""

import unittest

from icode.roles import (
    ROLES,
    AgentIdentity,
    RoleError,
    RoleRegistry,
    is_valid_ticket_id,
    parse_agent_id,
    read_only_roles,
    role,
    roles,
)


class TestRoleVocabulary(unittest.TestCase):
    def test_五角色封闭词表(self) -> None:
        self.assertEqual(ROLES, {"planner", "executor", "reviewer",
                                 "verifier", "auditor"})
        self.assertEqual(len(roles()), 5)

    def test_只有executor可写其余只读(self) -> None:
        for item in roles():
            with self.subTest(role=item.name):
                self.assertEqual(item.may_write, item.name == "executor")
        self.assertEqual(read_only_roles(),
                         ("auditor", "planner", "reviewer", "verifier"))

    def test_未知角色fail_closed(self) -> None:
        for name in ("boss", "root", "", None, "Reviewer"):
            with self.subTest(name=name):
                with self.assertRaises(RoleError) as caught:
                    role(name)
                self.assertEqual(caught.exception.code, "unknown_role")

    def test_角色数据冻结且无委派能力(self) -> None:
        item = role("executor")
        with self.assertRaises(Exception):
            item.may_write = False  # type: ignore[misc]
        for entry in roles():
            self.assertFalse(entry.may_delegate)


class TestAgentIdentity(unittest.TestCase):
    def test_spawn分配稳定且可解析的身份(self) -> None:
        registry = RoleRegistry()
        first = registry.spawn("executor", "ICODE-31")
        second = registry.spawn("executor", "ICODE-31")
        other = registry.spawn("executor", "ICODE-32")
        self.assertEqual(first.agent_id, "executor#ICODE-31#1")
        self.assertEqual(second.agent_id, "executor#ICODE-31#2")
        self.assertEqual(other.agent_id, "executor#ICODE-32#1")
        self.assertEqual(parse_agent_id(first.agent_id), ("executor", "ICODE-31", 1))
        self.assertIs(registry.identity(first.agent_id), first)

    def test_未知角色与非法工单拒绝spawn(self) -> None:
        registry = RoleRegistry()
        with self.assertRaises(RoleError) as caught:
            registry.spawn("boss", "ICODE-31")
        self.assertEqual(caught.exception.code, "unknown_role")
        with self.assertRaises(RoleError) as caught:
            registry.spawn("executor", "ICODE 31")
        self.assertEqual(caught.exception.code, "invalid_ticket")

    def test_身份字段一致性校验(self) -> None:
        valid = AgentIdentity(agent_id="executor#ICODE-31#1", role="executor",
                              ticket_id="ICODE-31", ordinal=1)
        self.assertEqual(parse_agent_id(valid.agent_id), ("executor", "ICODE-31", 1))
        for agent_id in ("reviewer#X#0", "ghost#X#1",
                         "executor#ICODE-31", ""):
            with self.subTest(agent_id=agent_id):
                with self.assertRaises(RoleError):
                    AgentIdentity(agent_id=agent_id, role="executor",
                                  ticket_id="ICODE-31", ordinal=1)
        self.assertTrue(is_valid_ticket_id("ICODE-31"))
        self.assertFalse(is_valid_ticket_id("ICODE 31"))

    def test_未发放身份不可用(self) -> None:
        registry = RoleRegistry()
        forged = AgentIdentity(agent_id="executor#ICODE-31#1", role="executor",
                               ticket_id="ICODE-31", ordinal=1)
        with self.assertRaises(RoleError) as caught:
            registry.assert_may_write(forged)
        self.assertEqual(caught.exception.code, "unknown_agent")
        self.assertIsNone(registry.identity(forged.agent_id))


class TestCapabilityChecks(unittest.TestCase):
    def test_只读角色申请写能力被拒(self) -> None:
        registry = RoleRegistry()
        reviewer = registry.spawn("reviewer", "ICODE-31")
        with self.assertRaises(RoleError) as caught:
            registry.assert_may_write(reviewer)
        self.assertEqual(caught.exception.code, "role_write_denied")

    def test_executor可写且结论类型受职责约束(self) -> None:
        registry = RoleRegistry()
        executor = registry.spawn("executor", "ICODE-31")
        registry.assert_may_write(executor)
        registry.assert_conclusion_kind(executor, "execution")
        with self.assertRaises(RoleError) as caught:
            registry.assert_conclusion_kind(executor, "review")
        self.assertEqual(caught.exception.code, "conclusion_out_of_role")


if __name__ == "__main__":
    unittest.main()
