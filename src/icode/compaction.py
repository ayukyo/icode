"""分层上下文压缩与重新水合（R4/G2）。

不变式（压缩前后必须逐字保持）：
1. 头部 system 消息（门禁要求、需求约束）全部逐字保留；
2. 首条 user 消息（用户原始要求）逐字保留；
3. 未闭合副作用以有界回执注入，绝不因压缩而消失；
4. 压缩后的中段只放有界摘要，不放工具正文。

压缩是纯函数：不改入参、不发请求、不写文件；`rehydrate` 只还原受保护项，
不臆造被丢弃内容。
"""

from __future__ import annotations

from dataclasses import dataclass

COMPACT_MARKER = "【历史压缩】"
UNCLOSED_MARKER = "【未闭合副作用】"
_SUMMARY_MAX_CHARS = 120
_UNCLOSED_MAX_CHARS = 200


def _content(message: dict) -> str:
    value = message.get("content")
    return value if isinstance(value, str) else ""


def history_chars(messages: list[dict]) -> int:
    """有界估算：正文长度 + 每条固定开销 + 工具调用名。"""
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        total += len(_content(message)) + 24
        for call in message.get("tool_calls") or []:
            if isinstance(call, dict):
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                total += len(str(fn.get("name") or "")) + len(str(fn.get("arguments") or ""))
    return total


@dataclass(frozen=True)
class CompactionResult:
    messages: list[dict]
    digest: dict
    dropped: int
    chars_before: int
    chars_after: int
    compacted: bool


def _summary_line(message: dict) -> str:
    role = str(message.get("role") or "?")
    text = " ".join(_content(message).split())
    names = []
    for call in message.get("tool_calls") or []:
        if isinstance(call, dict):
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            if fn.get("name"):
                names.append(str(fn["name"]))
    if names:
        text = (text + " " if text else "") + "调用:" + ",".join(names)
    return f"- {role}: {text[:_SUMMARY_MAX_CHARS]}"


def _unclosed_message(open_operations) -> dict:
    items = [str(item)[:_UNCLOSED_MAX_CHARS] for item in open_operations if str(item).strip()]
    body = "\n".join(f"- {item}" for item in items[:8])
    return {
        "role": "system",
        "content": (
            f"{UNCLOSED_MARKER}以下动作可能已生效但回执未知；"
            "继续前必须先核对真实状态，禁止直接重放。\n" + body
        ),
    }


def compact_history(
    messages: list[dict],
    *,
    budget_chars: int,
    open_operations=(),
    keep_tail: int = 2,
) -> CompactionResult:
    """超预算时压缩中段；不超预算时原样返回（compacted=False）。"""
    if not isinstance(budget_chars, int) or budget_chars <= 0:
        raise ValueError("budget_chars 必须为正整数")
    if not isinstance(keep_tail, int) or keep_tail < 1:
        raise ValueError("keep_tail 必须为正整数")
    source = [dict(message) for message in messages if isinstance(message, dict)]
    before = history_chars(source)
    protected_system: list[dict] = []
    index = 0
    while index < len(source) and source[index].get("role") == "system":
        protected_system.append(source[index])
        index += 1
    requirement: list[dict] = []
    if index < len(source) and source[index].get("role") == "user":
        requirement.append(source[index])
        index += 1
    tail = source[-keep_tail:] if len(source) - index > keep_tail else []
    middle = source[index:len(source) - len(tail)] if tail else source[index:]
    if before <= budget_chars or not middle:
        digest = {
            "compacted": False,
            "system": len(protected_system),
            "constraints": len(requirement),
            "tail": len(tail),
            "dropped": 0,
            "unclosed": 0,
            "chars_before": before,
            "chars_after": before,
        }
        return CompactionResult(source, digest, 0, before, before, False)

    # 已生成的压缩摘要与未闭合副作用回执是受保护项：不参与二次摘要。
    protected_extra = [
        message for message in middle
        if message.get("role") == "system"
        and (COMPACT_MARKER in _content(message) or UNCLOSED_MARKER in _content(message))
    ]
    if protected_extra:
        middle = [message for message in middle if message not in protected_extra]
    if not middle:
        digest = {
            "compacted": False,
            "system": len(protected_system),
            "constraints": len(requirement),
            "tail": len(tail),
            "dropped": 0,
            "unclosed": 0,
            "chars_before": before,
            "chars_after": before,
        }
        return CompactionResult(source, digest, 0, before, before, False)

    lines = [_summary_line(message) for message in middle][-8:]
    summary = {
        "role": "system",
        "content": (
            f"{COMPACT_MARKER}已省略 {len(middle)} 条中间消息（原始内容不注入）；"
            "中段事件摘要如下，仅用于定位，不作为门禁证据：\n" + "\n".join(lines)
        ),
    }
    rebuilt = [*protected_system, *requirement, *protected_extra, summary]
    unclosed = [item for item in open_operations if str(item).strip()]
    if unclosed:
        rebuilt.append(_unclosed_message(unclosed))
    rebuilt.extend(tail)
    after = history_chars(rebuilt)
    digest = {
        "compacted": True,
        "system": len(protected_system),
        "constraints": len(requirement),
        "tail": len(tail),
        "dropped": len(middle),
        "unclosed": len(unclosed),
        "chars_before": before,
        "chars_after": after,
    }
    return CompactionResult(rebuilt, digest, len(middle), before, after, True)


def rehydrate(result: CompactionResult) -> list[dict]:
    """还原受保护项（头部 system、用户约束、未闭合回执、尾部），不臆造内容。"""
    if not isinstance(result, CompactionResult):
        raise TypeError("rehydrate 需要 CompactionResult")
    messages = [dict(message) for message in result.messages]
    if not any(message.get("role") == "system" for message in messages):
        raise ValueError("压缩结果缺少受保护的 system 消息")
    return messages
