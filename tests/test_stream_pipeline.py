"""StreamChatPipeline 最小链路测试：内存假记忆 + 假 LLM（docs/01 §14）。"""

import asyncio
import re

import pytest

from app.framework.chat_types import ChatMessage, ChatRole
from app.framework.sse import SseSender
from app.rag.memory.store import normalize_history
from app.rag.pipeline.event_handler import StreamChatEventHandler
from app.rag.pipeline.stream_chat import (
    EMPTY_RETRIEVAL_TEXT,
    EmptyRetrievalEngine,
    StreamChatContext,
    StreamChatPipeline,
)


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


async def test_rag_response_streams_llm_and_persists_normal() -> None:
    class NonEmptyRetrieval:
        async def retrieve(self, question: str):
            return [{"text": "命中片段"}]

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
    assert memory.appended[-1][1] == "按条款赔付"
    assert memory.appended[-1][2] == "NORMAL"


async def test_cancel_persists_partial_content_as_interrupted() -> None:
    class NonEmptyRetrieval:
        async def retrieve(self, question: str):
            return [{"text": "x"}]

    memory = FakeMemory()
    llm = FakeLLM(chunks=["已写", "一半"], cancel_after=1)
    pipeline = StreamChatPipeline(memory, llm, NonEmptyRetrieval())

    with pytest.raises(asyncio.CancelledError):
        await pipeline.execute(make_ctx(), make_handler(SseSender(), memory))

    assert memory.appended[-1][0] == "assistant"
    assert memory.appended[-1][1] == "已写"
    assert memory.appended[-1][2] == "INTERRUPTED"


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
