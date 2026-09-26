"""控制面适配：把 `tools/icode_control.py` 包装成可编程接口。

边界（不要越过）：
- 控制面是**唯一写入口**；本模块不直接读写 `.ico_metadata.json` / `.ico_events.jsonl`。
- 本模块只调用上游 CLI，**不修改子模块内任何文件**。
- 事件幂等使用**确定性 request 键**（由逻辑坐标派生），重试沿用同一键，避免盲重放。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .config import Settings


class ControlError(RuntimeError):
    """控制面调用失败。"""

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True)
class ControlResult:
    args: tuple[str, ...]
    returncode: int
    data: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and bool(self.data.get("ok", True))


def make_request(
    ticket_id: str,
    action: str,
    *,
    attempt: str | None = None,
    boundary: str | None = None,
    occurrence: int = 1,
) -> str:
    """派生**确定性** request 幂等键。

    同一个逻辑动作重复调用得到同一个键（重试安全）；
    同一动作的第 N 次真实发生用 occurrence 区分（避免 payload 冲突）。
    """
    parts = [ticket_id, action, attempt or "-", boundary or "-", str(occurrence)]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{action}-{digest}"


class ControlPlane:
    """`icode_control.py` 的受控包装。"""

    def __init__(self, settings: Settings, *, check: bool = True) -> None:
        self.settings = settings
        self.check = check

    # ---- 底层调用 ----

    def run(self, *args: str, check: bool | None = None) -> ControlResult:
        script = self.settings.control_script
        if not script.is_file():
            raise ControlError(f"控制面脚本不存在：{script}")
        cmd: Sequence[str] = [self.settings.python, str(script), *args]
        proc = subprocess.run(  # noqa: S603 - 参数列表且 shell=False
            list(cmd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.settings.skill_subcommand_timeout,
            shell=False,
        )
        data: dict[str, Any] = {}
        text = (proc.stdout or "").strip()
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    data = {"value": parsed}
            except json.JSONDecodeError:
                data = {"raw": text}
        result = ControlResult(args=tuple(args), returncode=proc.returncode, data=data)

        strict = self.check if check is None else check
        if strict and not result.ok:
            detail = data.get("error") or data.get("message") or (proc.stderr or "").strip()[:400]
            raise ControlError(
                f"控制面命令失败：{' '.join(args)} :: {detail}",
                returncode=proc.returncode,
                stderr=proc.stderr or "",
            )
        return result

    # ---- 工单 ----

    def create(
        self,
        out_dir: Path | str,
        *,
        ticket_id: str,
        requirement: str,
        birth: str = "plan",
        request: str | None = None,
        metadata_json: str | None = None,
    ) -> ControlResult:
        args = [
            "create",
            "--dir", str(out_dir),
            "--ticket-id", ticket_id,
            "--requirement", requirement,
            "--birth", birth,
        ]
        if metadata_json:
            args += ["--metadata-json", metadata_json]
        args += ["--request-id", request or make_request(ticket_id, "create")]
        return self.run(*args)

    def create_next(
        self,
        *,
        workspace: Path | str,
        requirement: str,
        request_id: str,
        index_path: Path | str | None = None,
    ) -> ControlResult:
        """通过控制面原子分配下一工单目录并写入索引。

        ``workspace`` 只能来自服务端可信配置；浏览器不得提交真实路径。
        """
        args = [
            "create-next",
            "--workspace", str(workspace),
            "--requirement", requirement,
            "--request-id", request_id,
        ]
        if index_path is not None:
            args += ["--index", str(index_path)]
        return self.run(*args)

    def resolve_ticket(
        self,
        *,
        out_dir: Path | str | None = None,
        ticket: str | None = None,
        latest: bool = False,
        workspace: Path | str | None = None,
    ) -> ControlResult:
        args = ["resolve-ticket"]
        if out_dir:
            args += ["--dir", str(out_dir)]
        elif ticket:
            args += ["--ticket", ticket]
        elif latest:
            args += ["--latest"]
        else:
            raise ControlError("resolve-ticket 需要 --dir / --ticket / --latest 之一")
        if workspace:
            args += ["--workspace", str(workspace)]
        return self.run(*args)

    # ---- 步骤端口 ----

    def step_start(self, out_dir: Path | str, step: str, *, ticket_id: str, request: str | None = None) -> str:
        result = self.run(
            "step", "--dir", str(out_dir), "--step", step, "--phase", "start",
            "--request", request or make_request(ticket_id, f"step-{step}-start"),
        )
        attempt = result.data.get("attempt")
        if not attempt:
            raise ControlError(f"step start 未返回 attempt：{result.data}")
        return str(attempt)

    def step_check(
        self,
        out_dir: Path | str,
        step: str,
        attempt: str,
        boundary: str,
        *,
        ticket_id: str,
        occurrence: int = 1,
        request: str | None = None,
    ) -> ControlResult:
        return self.run(
            "step", "--dir", str(out_dir), "--step", step, "--phase", "check",
            "--attempt", attempt, "--boundary", boundary,
            "--request", request or make_request(
                ticket_id, f"step-{step}-check", attempt=attempt,
                boundary=boundary, occurrence=occurrence,
            ),
        )

    def step_finish(
        self,
        out_dir: Path | str,
        step: str,
        attempt: str,
        outcome: str,
        *,
        ticket_id: str,
        evidence: Sequence[str] = (),
        request: str | None = None,
        check: bool = True,
    ) -> ControlResult:
        """终结回执。`check=False` 时**不抛异常**，由调用方如实上报门禁拒绝。"""
        args = [
            "step", "--dir", str(out_dir), "--step", step, "--phase", "finish",
            "--attempt", attempt, "--outcome", outcome,
        ]
        for item in evidence:
            args += ["--evidence", item]
        args += ["--request", request or make_request(
            ticket_id, f"step-{step}-finish", attempt=attempt)]
        return self.run(*args, check=check)

    def artifact(
        self,
        out_dir: Path | str,
        step: str,
        attempt: str,
        path: Path | str,
        *,
        ticket_id: str,
        scope: str = "ticket",
        occurrence: int = 1,
        request: str | None = None,
    ) -> ControlResult:
        return self.run(
            "artifact", "--dir", str(out_dir), "--step", step, "--attempt", attempt,
            "--path", str(path), "--scope", scope,
            "--request", request or make_request(
                ticket_id, f"artifact-{Path(path).name}", attempt=attempt, occurrence=occurrence,
            ),
        )

    # ---- 状态流转 ----

    def transition(
        self,
        out_dir: Path | str,
        to_status: str,
        *,
        ticket_id: str,
        delivery_verdict: str | None = None,
    ) -> ControlResult:
        """状态流转。**不抛异常**：门禁拦截是正常结果，由调用方判定。

        `to_status == "completed"` 时上游**强制**显式回填 `--delivery-verdict`
        （交付分层契约：宿主验证通过不得自动映射为 verified）。
        """
        args = [
            "transition", "--dir", str(out_dir), "--to", to_status,
            "--request-id", make_request(ticket_id, f"transition-{to_status}"),
        ]
        if delivery_verdict:
            args += ["--delivery-verdict", delivery_verdict]
        return self.run(*args, check=False)

    # ---- 长动作回执（副作用） ----

    def operation_start(
        self,
        out_dir: Path | str,
        *,
        ticket_id: str,
        name: str,
        opclass: str,
        input_desc: str,
        occurrence: int = 1,
        request: str | None = None,
    ) -> ControlResult:
        """开始一个长动作。**不抛异常**：`ambiguous_side_effect` 必须由调用方处理。"""
        return self.run(
            "operation", "--dir", str(out_dir), "--phase", "start",
            "--name", name, "--opclass", opclass, "--input", input_desc,
            "--request", request or make_request(
                ticket_id, f"op-{name}-start", occurrence=occurrence),
            check=False,
        )

    def operation_finish(
        self,
        out_dir: Path | str,
        *,
        attempt: str,
        outcome: str,
        evidence: str,
        check_ref: str,
        failure: str | None = None,
    ) -> ControlResult:
        args = [
            "operation", "--dir", str(out_dir), "--phase", "finish",
            "--attempt", attempt, "--outcome", outcome,
            "--evidence", evidence, "--check", check_ref,
        ]
        if failure:
            args += ["--failure", failure]
        return self.run(*args, check=False)

    # ---- 元数据 ----

    def metadata_update(
        self,
        out_dir: Path | str,
        *,
        ticket_id: str,
        set_json: dict | None = None,
        append_json: dict | None = None,
        request: str | None = None,
    ) -> ControlResult:
        args = ["metadata-update", "--dir", str(out_dir), "--request-id",
                request or make_request(ticket_id, "metadata-update")]
        if set_json is not None:
            args += ["--set-json", json.dumps(set_json, ensure_ascii=False)]
        if append_json is not None:
            args += ["--append-json", json.dumps(append_json, ensure_ascii=False)]
        return self.run(*args, check=False)

    # ---- 验证记录（R3：回归证据写入事件链） ----

    def record_verification(
        self,
        out_dir: Path | str,
        *,
        ticket_id: str,
        kind: str,
        outcome: str,
        evidence: str,
        baseline: str = "",
        layer: str | None = None,
        scenario: str | None = None,
        note: str = "",
    ) -> ControlResult:
        """原子记录一条验证 run 到事件链（`verification_recorded` 事件 + `verification_runs`）。

        这是控制面**唯一**允许写 `verification_runs` 的入口；幂等键由
        `ticket_id + kind + outcome + evidence + baseline` 派生，同一条验证
        重放不会重复记录。`evidence` 应为验证证据指纹（不含输出正文/密钥），
        `baseline` 为绑定的 diff 指纹（回归证据锚定到具体改动）。
        """
        args = [
            "record-verification",
            "--dir", str(out_dir),
            "--kind", kind,
            "--outcome", outcome,
            "--evidence", evidence,
            "--request-id", make_request(
                ticket_id, "record-verification",
                attempt="verify",
                boundary="|".join([kind, outcome, evidence, baseline]),
            ),
        ]
        if baseline:
            args += ["--baseline", baseline]
        if layer:
            args += ["--layer", layer]
        if scenario:
            args += ["--scenario", scenario]
        if note:
            args += ["--note", note]
        return self.run(*args, check=False)

    # ---- 只读查询 ----

    def trace(self, out_dir: Path | str, *, limit: int = 50) -> ControlResult:
        return self.run("trace", "--dir", str(out_dir), "--limit", str(limit))

    def validate(self, out_dir: Path | str) -> ControlResult:
        return self.run("validate", "--dir", str(out_dir), check=False)

    def check_outputs(self, out_dir: Path | str, step: str) -> ControlResult:
        return self.run("check-outputs", "--dir", str(out_dir), "--step", step, check=False)

    # ---- 副作用策略（只读） ----

    def policy(self, *, opclass: str, failure: str, attempts: int) -> ControlResult:
        return self.run(
            "policy", "--opclass", opclass, "--failure", failure, "--attempts", str(attempts)
        )
