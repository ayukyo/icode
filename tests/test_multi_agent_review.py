"""评审补充测试：写区域收敛、身份强制写入、边界约束（R6 评审 M1/M2/M3/M7）。"""

import tempfile
import unittest
from pathlib import Path

from icode.agent_conclusion import (
    AgentConclusion,
    ConclusionError,
    ConclusionLedger,
)
from icode.guard import Scope
from icode.multi_agent import AgentTeam
from icode.roles import RoleError
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.write_lease import LeaseError


def _policy() -> SandboxPolicy:
    workspace = Path("/tmp/icode-r6-ws")
    return SandboxPolicy(
        schema_version=1, run_id="run-001", ticket_id="ICODE-31", step="code",
        workspace_root=workspace, read_roots=(workspace,), write_roots=(workspace,),
        deny_read_roots=(workspace / ".git",),
        deny_write_roots=(workspace / ".git",),
        network_mode=NetworkMode.DENY, allowed_domains=(),
        process_limit=32, wall_timeout_seconds=600, output_limit_bytes=4 * 1024 * 1024,
        protected_paths=(workspace / ".git",),
    )


def _scope() -> Scope:
    return Scope(workspace_root=Path("/tmp/icode-r6-ws"),
                 allowed_write_roots=(Path("/tmp/icode-r6-ws"),))


class TeamTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.team = AgentTeam(
            "ICODE-31",
            lease_dir=Path(self._tmp.name) / "leases",
            policy=_policy(),
            scope=_scope(),
        )


class TestExecutorRegionConvergence(TeamTestCase):
    def test_executor不申报写区域即拒(self) -> None:
        executor = self.team.spawn("executor")
        with self.assertRaises(RoleError) as caught:
            self.team.run(executor, lambda handle: {"ok": True}, step="code")
        self.assertEqual(caught.exception.code, "write_region_required")

    def test_非法区域形态被拒(self) -> None:
        executor = self.team.spawn("executor")
        from icode.write_lease import LeaseError
        with self.assertRaises(LeaseError) as caught:
            self.team.run(executor, lambda handle: {"ok": True},
                          step="code", write_region=("..", "escape"))
        self.assertEqual(caught.exception.code, "invalid_region")

    def test_区域在写根外拒绝(self) -> None:
        from dataclasses import replace
        base = replace(_policy(), write_roots=(_policy().workspace_root / "src",))
        team = AgentTeam("ICODE-31", lease_dir=self._leases_dir(),
                         policy=base, scope=_scope())
        executor = team.spawn("executor")
        with self.assertRaises(RoleError) as caught:
            team.run(executor, lambda handle: {"ok": True},
                     step="code", write_region=("tests",))
        self.assertEqual(caught.exception.code, "region_outside_write_scope")

    def _leases_dir(self) -> Path:
        return Path(self._tmp.name) / "leases"

    def test_收敛策略即本次运行真实边界(self) -> None:
        executor = self.team.spawn("executor")
        seen: list = []

        def work(handle):
            seen.append(handle)
            return {"ok": True}

        conclusion = self.team.run(executor, work, step="code",
                                   write_region=("src", "core"))
        self.assertEqual(conclusion.outcome, "completed")
        narrowed = seen[0].policy
        self.assertEqual(narrowed.write_roots,
                         (_policy().workspace_root / "src" / "core",))
        # 结论的边界摘要 = 收敛后策略的 policy_hash（不是 spawn 时的粗边界）
        self.assertEqual(conclusion.context_digest, narrowed.policy_hash)
        self.assertNotEqual(conclusion.context_digest, executor.context_digest)

    def test_伪造身份与边界被编排器覆盖(self) -> None:
        executor = self.team.spawn("executor")

        def work(handle):
            return {"ok": True, "agent_id": "ghost", "context_digest": "b" * 64}

        conclusion = self.team.run(executor, work, step="code",
                                   write_region=("src",))
        self.assertEqual(conclusion.evidence["agent_id"], executor.agent_id)
        self.assertNotEqual(conclusion.evidence["context_digest"], "b" * 64)

    def test_证据构造非法记failed不外泄(self) -> None:
        executor = self.team.spawn("executor")
        conclusion = self.team.run(
            executor, lambda handle: {"bad": ["nested"]}, step="code",
            write_region=("src",),
        )
        self.assertEqual(conclusion.outcome, "failed")
        self.assertEqual(conclusion.detail, "evidence_invalid")


class TestLeaseDirConstraint(TeamTestCase):
    def test_租约目录在工作区内即拒(self) -> None:
        with self.assertRaises(LeaseError) as caught:
            AgentTeam("ICODE-31", lease_dir=Path("/tmp/icode-r6-ws/leases"),
                      policy=_policy(), scope=_scope())
        self.assertEqual(caught.exception.code, "invalid_lease_dir")

    def test_锁文件记录持有者身份(self) -> None:
        lease = self.team._leases.acquire(("src",), "executor#ICODE-31#1")
        content = lease.path.read_bytes().decode("utf-8")
        self.assertEqual(content, "executor#ICODE-31#1")
        lease.release()


class TestParallelErrorAccounting(TeamTestCase):
    def test_多个逃逸异常全部入账且聚合上抛(self) -> None:
        first = self.team.spawn("executor")
        second = self.team.spawn("executor")
        # executor 不申报写区域是编程错误：run 抛 RoleError → worker 记 failed
        # 结论后聚合上抛；账本里每个逃逸异常都留下 failed 记录。
        with self.assertRaises(RoleError):
            self.team.run_parallel([
                (first, lambda handle: {"ok": True}, None, "code"),
                (second, lambda handle: {"ok": True}, None, "code"),
            ])
        failed = [item for item in self.team.conclusions()
                  if item["outcome"] == "failed"]
        self.assertEqual(len(failed), 2)
        for item in failed:
            self.assertEqual(item["detail"], "agent_work_failed")


class TestConclusionLedgerValidation(unittest.TestCase):
    def test_非法step与kind直接拒绝(self) -> None:
        from icode.agent_conclusion import AgentConclusion
        for step in ("", "x" * 65, None):
            with self.subTest(step=step):
                with self.assertRaises(ConclusionError):
                    AgentConclusion(
                        agent_id="reviewer#ICODE-31#1", role="reviewer",
                        ticket_id="ICODE-31", step=step, kind="review",
                        context_digest="a" * 64, outcome="completed",
                        evidence={"ok": True},
                    )
        with self.assertRaises(ConclusionError):
            AgentConclusion(
                agent_id="reviewer#ICODE-31#1", role="reviewer",
                ticket_id="ICODE-31", step="review", kind="",
                context_digest="a" * 64, outcome="completed",
                evidence={"ok": True},
            )

    def test_证据超4096字节拒绝(self) -> None:
        with self.assertRaises(ConclusionError) as caught:
            AgentConclusion(
                agent_id="reviewer#ICODE-31#1", role="reviewer",
                ticket_id="ICODE-31", step="review", kind="review",
                context_digest="a" * 64, outcome="completed",
                evidence={"blob": "x" * 5000},
            )
        self.assertEqual(caught.exception.code, "evidence_invalid")

    def test_账本满后fail_closed不淘汰(self) -> None:
        ledger = ConclusionLedger(limit=1)
        ledger.record(AgentConclusion(
            agent_id="reviewer#ICODE-31#1", role="reviewer",
            ticket_id="ICODE-31", step="review", kind="review",
            context_digest="a" * 64, outcome="completed", evidence={"n": 1},
        ))
        with self.assertRaises(ConclusionError) as caught:
            ledger.record(AgentConclusion(
                agent_id="reviewer#ICODE-31#2", role="reviewer",
                ticket_id="ICODE-31", step="review", kind="review",
                context_digest="a" * 64, outcome="completed", evidence={"n": 2},
            ))
        self.assertEqual(caught.exception.code, "ledger_full")


if __name__ == "__main__":
    unittest.main()
