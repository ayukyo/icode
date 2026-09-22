"""结构化顺序思考（推理门禁要求的 L2 机制）。

上游 `mcp/reasoning-gate/gates.json` 规定：L2 步骤必须由 `sequential-thinking`
机制承担，且 `attempted=true`。上游通过注册一个 npm MCP 服务器提供该机制。

**本模块是本仓自实现的同机制实现**（不依赖 Node、不联网、core 零依赖）：
    以有界轮次逐步推演，每轮在前一轮结论上继续，直到模型认为可以收敛
    或触达上限。

诚实标注（重要）：
    我们**不声称**调用了上游的 npm MCP 服务器。trace 行里按上游词表填
    `mechanism=sequential-thinking`（这是**机制名**，词表硬约束），
    同时用一个额外字段 `provider` 如实写明实现来源；`REQUIRED_FIELDS` 只检缺失、
    不拒绝额外键，因此这是允许的。

不落盘原则：推演正文只在内存里参与后续决策，**不进 trace、不进事件链**；
trace 只记步数与摘要。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# 上游 constants：l2_min_steps=3 / l2_max_steps=5 / l3_min_steps=4
PROVIDER_NAME = "icode-in-repo-sequential-thinking"
PROVIDER_KIND = "in_repo"

MIN_STEPS = {"L2": 3, "L3": 4}
MAX_STEPS = {"L2": 5, "L3": 8}

_SYSTEM = (
    "你正在进行一次**结构化的分步推演**（sequential thinking）。\n"
    "规则：\n"
    "  1. 每次只推进**一步**，内容简短（不超过 120 字），聚焦一个明确结论或一个待验证问题；\n"
    "  2. 后续步骤必须建立在前面的结论之上，不得重复；\n"
    "  3. 已能收敛时，把 next_thought_needed 置为 false；\n"
    "  4. **只输出 JSON**，不要输出其它文字。\n"
    '格式：{"step": "<本步内容>", "next_thought_needed": true|false}'
)


@dataclass
class Deliberation:
    """一次推演的结果。正文只用于当次决策，**不落盘**。"""

    tier: str
    steps: list[str] = field(default_factory=list)
    converged: bool = False
    truncated: bool = False
    empty_responses: int = 0
    error: str = ""

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def digest(self) -> str:
        material = "\n".join(self.steps)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def summary(self) -> str:
        tail = "（已收敛）" if self.converged else "（到上限）"
        if self.empty_responses:
            tail += f"，其中 {self.empty_responses} 次空响应"
        if self.error:
            tail += f"，中断：{self.error}"
        return f"{self.tier} 推演 {self.step_count} 步{tail}"


class SequentialThinking:
    """有界的分步推演机制。

    只用后端的一次回合接口；每轮调用都很短（max_tokens 很小），
    因此成本可控，且失败不会污染主流程（返回带 error 的结果，由调用方决定降级）。
    """

    def __init__(self, backend, *, max_tokens: int = 1200) -> None:
        # 注意：推理模型（如 MiniMax-M3）会先在 <think> 里花 token，
        # max_tokens 给小了会导致剥离思考后正文为空 —— 实测曾因此 4 步全空。
        self.backend = backend
        self.max_tokens = max_tokens

    def run(self, question: str, *, tier: str = "L2") -> Deliberation:
        lo = MIN_STEPS.get(tier, 3)
        hi = MAX_STEPS.get(tier, 5)
        result = Deliberation(tier=tier)
        history: list[str] = []

        for index in range(1, hi + 1):
            user = self._prompt(question, history, index, lo, hi)
            try:
                message = self.backend.complete(
                    [{"role": "system", "content": _SYSTEM},
                     {"role": "user", "content": user}],
                    tools=None,
                    max_tokens=self.max_tokens,
                )
            except Exception as exc:  # noqa: BLE001 - 推演失败不应中断主流程
                result.error = f"{type(exc).__name__}: {exc}"
                break

            step_text, more = self._parse(message.content)
            if not step_text:
                # 空响应（思考吃满 token / 模型没按格式回）——记下来并停下，
                # 不要用剩余的调用额度继续空转
                result.empty_responses += 1
                result.error = "模型返回空内容（可能是 max_tokens 不足或未按 JSON 格式回复）"
                break
            result.steps.append(step_text)
            history.append(step_text)
            # 未达下限时不允许提前收敛
            if index >= lo and not more:
                result.converged = True
                break
        else:
            result.truncated = True

        return result

    # ---- 内部 ----

    @staticmethod
    def _prompt(question: str, history: list[str], index: int, lo: int, hi: int) -> str:
        lines = [
            f"【推演目标】{question}",
            f"【进度】第 {index} 步（本等级最少 {lo} 步、最多 {hi} 步）",
        ]
        if history:
            lines.append("【已完成步骤】")
            lines.extend(f"  {i}. {s}" for i, s in enumerate(history, 1))
            lines.append("请在此基础上前进一步（不要重复上面的内容）。")
        else:
            lines.append("请给出第一步。")
        return "\n".join(lines)

    @staticmethod
    def _parse(text: str) -> tuple[str, bool]:
        """从回复里取出本步内容与是否继续。解析失败时按"内容即步骤、继续"处理。"""
        import json
        import re

        raw = (text or "").strip()
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            try:
                data = json.loads(match.group(0))
                step = str(data.get("step") or "").strip()
                more = bool(data.get("next_thought_needed", True))
                return step, more
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return raw[:200].replace("\n", " "), True
