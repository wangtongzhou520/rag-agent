"""MCP 意图分发与失败隔离。"""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.framework.logging import get_logger
from app.rag.intent.node import IntentKind, SubQuestionIntent

logger = get_logger(__name__)


class McpToolExecutor(Protocol):
    async def call(self, tool_id: str, question: str) -> str: ...


@dataclass(frozen=True, slots=True)
class McpEvidence:
    tool_id: str
    content: str


class McpIntentDispatcher:
    def __init__(self, executor: McpToolExecutor) -> None:
        self._executor = executor

    async def dispatch(
        self, intents: list[SubQuestionIntent]
    ) -> list[McpEvidence]:
        requests: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item in intents:
            for score in item.node_scores:
                node = score.node
                if node.kind != IntentKind.MCP or not node.mcp_tool_id:
                    continue
                if node.mcp_tool_id in seen:
                    continue
                seen.add(node.mcp_tool_id)
                requests.append((node.mcp_tool_id, item.sub_question))

        async def invoke(tool_id: str, question: str) -> McpEvidence | None:
            try:
                content = (await self._executor.call(tool_id, question)).strip()
                return McpEvidence(tool_id, content) if content else None
            except Exception:
                logger.exception("MCP 工具调用失败，忽略该结果", tool_id=tool_id)
                return None

        results = await asyncio.gather(
            *(invoke(tool_id, question) for tool_id, question in requests)
        )
        return [result for result in results if result is not None]
