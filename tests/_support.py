"""测试公共支撑：路径引导、子模块探测、临时工作区。

零第三方依赖：只用标准库 unittest。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from icode.config import ConfigError, Settings, load_settings  # noqa: E402


def load_settings_or_none() -> Settings | None:
    try:
        return load_settings()
    except ConfigError:
        return None


def require_skill() -> Settings:
    """需要 icode-skill 子模块的测试用；缺失则跳过而不是失败。"""
    settings = load_settings_or_none()
    if settings is None or not settings.exists():
        raise unittest.SkipTest("未找到 icode-skill 子模块（git submodule update --init）")
    return settings


@contextmanager
def temp_workspace() -> Iterator[Path]:
    """临时工作区：握手产物落在这里，绝不污染仓库。"""
    with tempfile.TemporaryDirectory(prefix="icode_test_") as tmp:
        yield Path(tmp)


def make_finished_plan_ticket(
    settings: Settings,
    workspace: Path,
    *,
    ticket_id: str = "EV-1",
    plan_text: str = "# 计划\n\n用于证据包测试的产物正文。\n",
) -> Path:
    """在临时工作区造一条"plan 步骤已完成"的真实工单，返回工单目录。

    走的是真控制面（create → step start → check → artifact → check → finish），
    因此事件链是**真实**的，可直接用于证据包测试。
    """
    from icode.control import ControlPlane
    from icode.handshake import next_out_dir

    cp = ControlPlane(settings)
    out_dir = next_out_dir(Path(workspace))
    cp.create(out_dir, ticket_id=ticket_id,
              requirement="证据包测试用需求", birth="plan")
    attempt = cp.step_start(out_dir, "plan", ticket_id=ticket_id)
    cp.step_check(out_dir, "plan", attempt, "before_write", ticket_id=ticket_id, occurrence=1)
    (out_dir / "01_plan.md").write_text(plan_text, encoding="utf-8")
    cp.artifact(out_dir, "plan", attempt, "01_plan.md", ticket_id=ticket_id)
    cp.step_check(out_dir, "plan", attempt, "before_transition",
                  ticket_id=ticket_id, occurrence=2)
    cp.step_finish(out_dir, "plan", attempt, "success",
                   ticket_id=ticket_id, evidence=["test"], check=False)
    return out_dir
