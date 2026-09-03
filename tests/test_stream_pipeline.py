"""StreamChatPipeline 最小链路测试：内存假记忆 + 假 LLM（docs/01 §14）。"""

import asyncio
import re

import pytest
from uuid_utils import uuid7

from app.framework.chat_types import ChatMessage, ChatRole
from app.framework.sse import SseSender
from app.rag.intent.node import IntentKind, IntentNode, NodeScore, SubQuestionIntent
from app.rag.mcp.service import McpIntentDispatcher
from app.rag.memory.store import normalize_history
from app.rag.pipeline.event_handler import StreamChatEventHandler
from app.rag.pipeline.stream_chat import (
    EMPTY_RETRIEVAL_TEXT,
    EmptyRetrievalEngine,
    StreamChatContext,
    StreamChatPipeline,
)
from app.rag.retrieval.models import RetrievedChunk
from app.rag.rewrite.models import RewriteResult


class FakeMemory:
    def __init__(self, history: list[ChatMessage] | None = None) -> None:
        self.history = history or []
        self.appended: list[tuple[str, str, str | None, str | None]] = []

    async def load(self, conversation_id: str, user_id: int) -> list[ChatMessage]:
        return list(self.history)

    async def append_user_message(self, conversation_id, user_id, content):
        self.appended.append(("user", content, None, None))
        return "user-msg-id"

    async def append_assistant_message(
        self,
        conversation_id,
        user_id,
        content,
        *,
        thinking_content=None,
        thinking_duration=None,
        sources=None,
        retrieved_chunks=None,
        message_status="NORMAL",
        reply_to_message_id=None,
    ):
        self.appended.append(("assistant", content, message_status, reply_to_message_id))
        return "assistant-msg-id"


class FakeLLM:
    def __init__(self, chunks: list[str] | None = None, cancel_after: int | None = None):
        self.chunks = chunks or []
        self.cancel_after = cancel_after
        self.requests = []

    async def stream_chat(self, request, callback):
        self.requests.append(request)
        for index, chunk in enumerate(self.chunks):
            if self.cancel_after is not None and index >= self.cancel_after:
                raise asyncio.CancelledError
            await callback.on_content(chunk)
        if self.cancel_after is None:
            await callback.on_complete()


def make_handler(sender: SseSender, memory: FakeMemory, is_new: bool = False):
    return StreamChatEventHandler(
        sender,
        memory,
        conversation_id="conv-1",
        user_id=0,
        is_new_conversation=is_new,
        chunk_size=5,
    )


def make_ctx(**overrides) -> StreamChatContext:
    defaults = {"question": "保险怎么赔", "conversation_id": "conv-1", "task_id": "task-1", "user_id": 0}
    return StreamChatContext(**(defaults | overrides))


async def drain(sender: SseSender) -> str:
    frames = []
    async for frame in sender.stream():
        frames.append(frame)
    return "".join(frames)


async def test_empty_retrieval_short_circuits_with_fixed_text() -> None:
    memory = FakeMemory()
    pipeline = StreamChatPipeline(memory, FakeLLM(), EmptyRetrievalEngine())
    sender = SseSender()

    await pipeline.execute(make_ctx(), make_handler(sender, memory, is_new=True))
    body = await drain(sender)

    deltas = re.findall(r'"delta":"(.*?)"', body)
    assert "".join(deltas) == EMPTY_RETRIEVAL_TEXT
    assert "finish" in body and '"title":"新对话"' in body
    # user 先落库，assistant 以 NORMAL 落库并回指 user 消息
    assert memory.appended[0] == ("user", "保险怎么赔", None, None)
    assert memory.appended[1] == (
        "assistant",
        EMPTY_RETRIEVAL_TEXT,
        "NORMAL",
        "user-msg-id",
    )


async def test_history_loaded_before_question_persisted() -> None:
    history = [
        ChatMessage(role=ChatRole.USER, content="上一问"),
        ChatMessage(role=ChatRole.ASSISTANT, content="上一答"),
    ]
    memory = FakeMemory(history)
    pipeline = StreamChatPipeline(memory, FakeLLM(), EmptyRetrievalEngine())
    ctx = make_ctx()

    await pipeline.execute(ctx, make_handler(SseSender(), memory))

    assert ctx.history == history


async def test_system_intent_streams_without_retrieval() -> None:
    class SystemResolver:
        async def resolve(self, rewrite_result):
            node = IntentNode(1, "system.chat", "闲聊", 2, kind=IntentKind.SYSTEM)
            return [SubQuestionIntent(rewrite_result.rewritten_question, (NodeScore(node, 0.99),))]

    class MustNotRetrieve:
        async def retrieve(self, question: str, **kwargs):
            raise AssertionError("SYSTEM 意图不应进入检索")

    memory = FakeMemory()
    llm = FakeLLM(chunks=["你好！"])
    pipeline = StreamChatPipeline(memory, llm, MustNotRetrieve(), SystemResolver())
    sender = SseSender()

    await pipeline.execute(make_ctx(question="你好"), make_handler(sender, memory))
    body = await drain(sender)

    assert "你好！" in body
    assert "不要编造知识库来源" in llm.requests[0].messages[0].content


async def test_mcp_intent_uses_tool_context_without_retrieval() -> None:
    class McpResolver:
        async def resolve(self, rewrite_result):
            node = IntentNode(
                2,
                "tool.weather",
                "天气",
                2,
                kind=IntentKind.MCP,
                mcp_tool_id="weather:query",
            )
            return [SubQuestionIntent("北京天气", (NodeScore(node, 0.95),))]

    class Executor:
        async def call(self, tool_id: str, question: str) -> str:
            return "北京晴，25℃"

    class MustNotRetrieve:
        async def retrieve(self, question: str, **kwargs):
            raise AssertionError("MCP 成功后不应进入 KB 检索")

    llm = FakeLLM(chunks=["今天适合出行"])
    memory = FakeMemory()
    pipeline = StreamChatPipeline(
        memory,
        llm,
        MustNotRetrieve(),
        McpResolver(),
        McpIntentDispatcher(Executor()),
    )
    sender = SseSender()
    await pipeline.execute(make_ctx(question="北京天气"), make_handler(sender, memory))
    body = await drain(sender)

    assert "".join(re.findall(r'"delta":"(.*?)"', body)) == "今天适合出行"
    assert "北京晴，25℃" in llm.requests[0].messages[0].content
    assert "不得把工具结果标成知识库引用" in llm.requests[0].messages[0].content


async def test_rag_response_streams_llm_and_persists_normal() -> None:
    class NonEmptyRetrieval:
        async def retrieve(self, question: str, **kwargs):
            return [
                RetrievedChunk(
                    id=uuid7(),
                    text="命中片段",
                    score=0.9,
                    doc_id=7,
                    doc_name="理赔条款",
                    source_type="file",
                    file_type="pdf",
                )
            ]

    memory = FakeMemory()
    llm = FakeLLM(chunks=["按条款", "赔付"])
    pipeline = StreamChatPipeline(memory, llm, NonEmptyRetrieval())
    sender = SseSender()
    ctx = make_ctx(deep_thinking=True)

    await pipeline.execute(ctx, make_handler(sender, memory))
    body = await drain(sender)

    assert "按条款" in body and "赔付" in body
    request = llm.requests[0]
    assert request.thinking is True
    assert request.messages[-1].content == "保险怎么赔"
    assert '<content ref="1">' in request.messages[0].content
    assert '"docName":"理赔条款"' in body
    assert memory.appended[-1][1] == "按条款赔付"
    assert memory.appended[-1][2] == "NORMAL"


async def test_cancel_persists_partial_content_as_interrupted() -> None:
    class NonEmptyRetrieval:
        async def retrieve(self, question: str, **kwargs):
            return [{"text": "x"}]

    memory = FakeMemory()
    llm = FakeLLM(chunks=["已写", "一半"], cancel_after=1)
    pipeline = StreamChatPipeline(memory, llm, NonEmptyRetrieval())
    sender = SseSender()

    with pytest.raises(asyncio.CancelledError):
        await pipeline.execute(make_ctx(), make_handler(sender, memory))

    body = await drain(sender)

    assert memory.appended[-1][0] == "assistant"
    assert memory.appended[-1][1] == "已写"
    assert memory.appended[-1][2] == "INTERRUPTED"
    assert "event: cancel" in body
    assert '"messageStatus":"INTERRUPTED"' in body
    assert body.rstrip().endswith("event: done\ndata: [DONE]")


async def test_normal_terminal_survives_concurrent_reader_cancellation() -> None:
    class BlockingMemory(FakeMemory):
        def __init__(self) -> None:
            super().__init__()
            self.persisting = asyncio.Event()
            self.release = asyncio.Event()

        async def append_assistant_message(self, *args, **kwargs):
            self.persisting.set()
            await self.release.wait()
            return await super().append_assistant_message(*args, **kwargs)

    memory = BlockingMemory()
    sender = SseSender()
    handler = make_handler(sender, memory)
    await handler.on_content("完整回答")
    completing = asyncio.create_task(handler.on_complete())

    await memory.persisting.wait()
    completing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await completing
    cancelled = asyncio.create_task(handler.on_cancelled())
    memory.release.set()
    await cancelled
    body = await drain(sender)

    assert body.count("event: finish") == 1
    assert "event: cancel" not in body
    assert body.rstrip().endswith("event: done\ndata: [DONE]")
    assert memory.appended == [("assistant", "完整回答", "NORMAL", None)]


async def test_rewrite_is_shared_by_intent_and_retrieval_without_duplicate_call() -> None:
    class Rewriter:
        def __init__(self) -> None:
            self.calls = 0

        async def rewrite_with_split(self, question, history=()):
            self.calls += 1
            assert question == "原问题"
            return RewriteResult("改写问题", ("子问题一", "子问题二"))

    class Resolver:
        async def resolve(self, rewrite_result):
            assert rewrite_result == RewriteResult(
                "改写问题", ("子问题一", "子问题二")
            )
            return []

    class Retrieval:
        async def retrieve(self, question, **kwargs):
            assert question == "原问题"
            assert kwargs["rewrite_result"] == RewriteResult(
                "改写问题", ("子问题一", "子问题二")
            )
            return []

    rewriter = Rewriter()
    memory = FakeMemory()
    pipeline = StreamChatPipeline(
        memory,
        FakeLLM(),
        Retrieval(),
        Resolver(),
        rewriter=rewriter,
    )

    await pipeline.execute(
        make_ctx(question="原问题"), make_handler(SseSender(), memory)
    )

    assert rewriter.calls == 1


def test_normalize_history_crops_head_assistant_and_keeps_recent_turns() -> None:
    messages = [
        ChatMessage(role=ChatRole.ASSISTANT, content="孤儿回答"),
        ChatMessage(role=ChatRole.USER, content="q1"),
        ChatMessage(role=ChatRole.ASSISTANT, content="a1"),
        ChatMessage(role=ChatRole.USER, content="q2"),
        ChatMessage(role=ChatRole.ASSISTANT, content="a2"),
    ]

    normalized = normalize_history(messages, keep_turns=1)

    assert [m.content for m in normalized] == ["q2", "a2"]

    full = normalize_history(messages, keep_turns=10)
    assert [m.content for m in full] == ["q1", "a1", "q2", "a2"]


def test_normalize_history_strips_assistant_citations() -> None:
    messages = [
        ChatMessage(role=ChatRole.USER, content="q"),
        ChatMessage(role=ChatRole.ASSISTANT, content="答案[1](#cite-1)"),
    ]
    assert normalize_history(messages, 8)[1].content == "答案"
