"""受控编排：三段保护、并行租约、角色分离门禁、失败不绕门禁（R6/W5）。"""

import tempfile
import threading
import unittest
from pathlib import Path

from icode.agent_conclusion import ConclusionError
from icode.guard import Scope
from icode.multi_agent import AgentTeam
from icode.roles import RoleError
from icode.sandbox_policy import NetworkMode, SandboxPolicy
from icode.write_lease import LeaseBusy, LeaseError


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


class TestSpawnAndContext(TeamTestCase):
    def test_spawn派生只读上下文且边界可算(self) -> None:
        reviewer = self.team.spawn("reviewer")
        executor = self.team.spawn("executor")
        self.assertEqual(reviewer.policy.write_roots, ())
        self.assertEqual(executor.policy.write_roots, (_policy().workspace_root,))
        self.assertEqual(reviewer.scope.allowed_write_roots, ())
        self.assertNotEqual(reviewer.context_digest, executor.context_digest)
        self.assertEqual(len(reviewer.context_digest), 64)

    def test_重复spawn同角色得到递增身份(self) -> None:
        first = self.team.spawn("executor")
        second = self.team.spawn("executor")
        self.assertEqual(first.identity.ordinal, 1)
        self.assertEqual(second.identity.ordinal, 2)

    def test_未知角色拒绝(self) -> None:
        with self.assertRaises(RoleError) as caught:
            self.team.spawn("boss")
        self.assertEqual(caught.exception.code, "unknown_role")


class TestRun(TeamTestCase):
    def test_正常完成结论带身份边界与证据(self) -> None:
        reviewer = self.team.spawn("reviewer")
        conclusion = self.team.run(
            reviewer, lambda handle: {"reviewed_files": 2, "ok": True}, step="review",
        )
        self.assertEqual(conclusion.outcome, "completed")
        self.assertEqual(conclusion.step, "review")
        self.assertEqual(conclusion.evidence["agent_id"], reviewer.agent_id)
        self.assertEqual(conclusion.evidence["context_digest"],
                         reviewer.context_digest)

    def test_只读角色申请写区域是编程错误(self) -> None:
        reviewer = self.team.spawn("reviewer")
        with self.assertRaises(RoleError) as caught:
            self.team.run(reviewer, lambda handle: {"ok": True},
                          step="review", write_region=("src",))
        self.assertEqual(caught.exception.code, "role_write_denied")

    def test_工作异常记failed结论且正文不外泄(self) -> None:
        executor = self.team.spawn("executor")

        def work(handle):
            raise RuntimeError("内部敏感细节 /etc/passwd")

        conclusion = self.team.run(executor, work, step="code",
                                   write_region=("src",))
        self.assertEqual(conclusion.outcome, "failed")
        self.assertEqual(conclusion.detail, "agent_work_failed")
        self.assertNotIn("passwd", conclusion.detail)
        self.assertNotIn("passwd", str(self.team.conclusions()))

    def test_空证据记refused(self) -> None:
        planner = self.team.spawn("planner")
        conclusion = self.team.run(planner, lambda handle: None, step="plan")
        self.assertEqual(conclusion.outcome, "refused")
        self.assertEqual(conclusion.detail, "evidence_missing")

    def test_无边界上下文的团队连spawn都拒绝(self) -> None:
        bare = AgentTeam("ICODE-31")
        with self.assertRaises(RoleError) as caught:
            bare.spawn("executor")
        self.assertEqual(caught.exception.code, "context_boundary_missing")

    def test_写租约期间重叠获取被拒且释放后可复用(self) -> None:
        executor = self.team.spawn("executor")
        started = threading.Event()
        release = threading.Event()

        def work(handle):
            started.set()
            release.wait(timeout=5)
            return {"ok": True}

        result: list = []

        def runner():
            result.append(self.team.run(executor, work, step="code",
                                        write_region=("src",)))

        thread = threading.Thread(target=runner)
        thread.start()
        started.wait(timeout=5)
        with self.assertRaises(LeaseBusy):
            self.team._leases.acquire(("src",), "executor#ICODE-31#2")
        release.set()
        thread.join(timeout=5)
        self.assertEqual(result[0].outcome, "completed")
        again = self.team._leases.acquire(("src",), "executor#ICODE-31#2")
        again.release()


class TestParallelAndGate(TeamTestCase):
    def test_并行作业相异区域互不阻塞(self) -> None:
        first = self.team.spawn("executor")
        second = self.team.spawn("executor")
        conclusions = self.team.run_parallel([
            (first, lambda handle: {"side": "a"}, ("src",), "code"),
            (second, lambda handle: {"side": "b"}, ("tests",), "code"),
        ])
        self.assertEqual([item.outcome for item in conclusions],
                         ["completed", "completed"])

    def test_并行作业重叠区域恰有一个被拒(self) -> None:
        first = self.team.spawn("executor")
        second = self.team.spawn("executor")
        conclusions = self.team.run_parallel([
            (first, lambda handle: {"side": "a"}, ("src",), "code"),
            (second, lambda handle: {"side": "b"}, ("src", "core"), "code"),
        ])
        outcomes = sorted(item.outcome for item in conclusions)
        self.assertEqual(outcomes, ["completed", "refused"])
        refused = [item for item in conclusions if item.outcome == "refused"][0]
        self.assertEqual(refused.detail, "lease_busy")

    def test_门禁要求全部角色完成(self) -> None:
        reviewer = self.team.spawn("reviewer")
        executor = self.team.spawn("executor")
        blocked = self.team.step_gate("review", {"reviewer": "review",
                                                 "executor": "execution"})
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.missing, ("reviewer:review", "executor:execution"))
        self.team.run(reviewer, lambda handle: {"ok": True}, step="review")
        self.team.run(executor, lambda handle: {"ok": True}, step="review",
                      write_region=("src",))
        passed = self.team.step_gate("review", {"reviewer": "review",
                                                "executor": "execution"})
        self.assertTrue(passed.ok)
        self.assertEqual(passed.missing, ())

    def test_代理失败不绕过门禁(self) -> None:
        reviewer = self.team.spawn("reviewer")

        def work(handle):
            raise RuntimeError("审查中途崩溃")

        self.team.run(reviewer, work, step="review")
        blocked = self.team.step_gate("review", {"reviewer": "review"})
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.missing, ("reviewer:review",))
        failed = [item for item in self.team.conclusions()
                  if item["outcome"] == "failed"]
        self.assertEqual(failed[0]["detail"], "agent_work_failed")

    def test_executor结论不能顶替reviewer门禁(self) -> None:
        executor = self.team.spawn("executor")
        self.team.run(executor, lambda handle: {"ok": True}, step="review",
                      write_region=("src",))
        blocked = self.team.step_gate("review", {"reviewer": "review"})
        self.assertFalse(blocked.ok)

    def test_跨步骤结论不串门(self) -> None:
        reviewer = self.team.spawn("reviewer")
        self.team.run(reviewer, lambda handle: {"ok": True}, step="deepcheck")
        blocked = self.team.step_gate("review", {"reviewer": "review"})
        self.assertFalse(blocked.ok)

    def test_门禁无放宽路径(self) -> None:
        source = Path(__file__).resolve().parent.parent.joinpath(
            "src/icode/multi_agent.py").read_text(encoding="utf-8")
        for literal in ("force=True", "override=True", "skip_gate",
                        "allow_incomplete"):
            self.assertNotIn(literal, source,
                             f"multi_agent.py 不得存在门禁放宽参数：{literal}")

    def test_门禁要求错误结论类型被拒(self) -> None:
        with self.assertRaises(RoleError) as caught:
            self.team.step_gate("review", {"reviewer": "execution"})
        self.assertEqual(caught.exception.code, "conclusion_out_of_role")


if __name__ == "__main__":
    unittest.main()
