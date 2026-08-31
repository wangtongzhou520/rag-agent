"""MCP 意图分发与降级。"""

from app.rag.intent.node import IntentKind, IntentNode, NodeScore, SubQuestionIntent
from app.rag.mcp.service import McpIntentDispatcher


def mcp_intent(tool_id: str, question: str = "天气") -> SubQuestionIntent:
    node = IntentNode(
        1,
        "tool.weather",
        "天气工具",
        2,
        kind=IntentKind.MCP,
        mcp_tool_id=tool_id,
    )
    return SubQuestionIntent(question, (NodeScore(node, 0.9),))


async def test_dispatcher_deduplicates_tools() -> None:
    class Executor:
        def __init__(self) -> None:
            self.calls = []

        async def call(self, tool_id: str, question: str) -> str:
            self.calls.append((tool_id, question))
            return "晴，25℃"

    executor = Executor()
    result = await McpIntentDispatcher(executor).dispatch(
        [mcp_intent("weather:query"), mcp_intent("weather:query")]
    )
    assert executor.calls == [("weather:query", "天气")]
    assert result[0].content == "晴，25℃"


async def test_dispatcher_ignores_failed_tools() -> None:
    class Executor:
        async def call(self, tool_id: str, question: str) -> str:
            raise RuntimeError("offline")

    assert await McpIntentDispatcher(Executor()).dispatch(
        [mcp_intent("weather:query")]
    ) == []
