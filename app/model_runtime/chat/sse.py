"""OpenAI 兼容 SSE 流式行解析（docs/04 §6.4）。

规则：空行跳过；去 ``data:`` 前缀；``[DONE]``（忽略大小写）→ completed；
JSON 解析失败告警跳过、不中断流；choices 缺失/为空 → 空事件；文本字段
``delta.<field>`` 优先、回落 ``message.<field>``（非 null 才取）；
``finish_reason`` 非 null → completed。
"""

import json
from dataclasses import dataclass

from app.framework.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ParsedEvent:
    content: str | None = None
    reasoning: str | None = None
    completed: bool = False


def _pick(choice: dict, field: str) -> str | None:
    """文本字段优先 delta.<field>，回落 message.<field>（非 null 才取）。"""
    for block in ("delta", "message"):
        value = choice.get(block)
        if isinstance(value, dict) and value.get(field) is not None:
            return value[field]
    return None


def parse_line(line: str, reasoning_enabled: bool = False) -> ParsedEvent | None:
    """解析单行 SSE；空行与坏行返回 None，无内容返回空事件。"""
    payload = line.strip()
    if payload.startswith("data:"):
        payload = payload[len("data:") :].strip()
    if not payload:
        return None
    if payload.lower() == "[done]":
        return ParsedEvent(completed=True)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("skip malformed sse line", line=payload[:200])
        return None
    if not isinstance(data, dict):
        logger.warning("skip non-object sse payload", line=payload[:200])
        return None

    choices = data.get("choices")
    if not choices or not isinstance(choices[0], dict):
        return ParsedEvent()

    choice = choices[0]
    content = _pick(choice, "content")
    if content is not None and not content.strip():
        content = None  # content 非空白才算内容
    reasoning = _pick(choice, "reasoning_content") if reasoning_enabled else None
    if reasoning is not None and not reasoning:
        reasoning = None
    completed = choice.get("finish_reason") is not None
    return ParsedEvent(content=content, reasoning=reasoning, completed=completed)
