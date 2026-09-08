"""M5 问答限流入口的无 Redis 单元测试。"""

import json
from typing import cast

from app.framework.config import Settings
from app.framework.sse import SseSender
from app.rag.pipeline.stream_chat import StreamChatPipeline
from app.rag.ratelimit import ChatQueueLimiter
from app.rag.service import RAGChatService


def _event_names(body: str) -> list[str]:
    return [frame.splitlines()[0].removeprefix("event: ") for frame in body.strip().split("\n\n")]


async def test_queue_timeout_emits_reject_finish_done_and_persists() -> None:
    class RejectingLimiter:
        async def acquire(self, request_id: str):
            return None

        async def release(self, permit) -> bool:
            raise AssertionError("timeout must not release a permit")

    class FakeMemory:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str | None]] = []

        async def append_user_message(self, conversation_id, user_id, content):
            self.calls.append(("user", content, None))
            return "user-message-1"

        async def append_assistant_message(
            self, conversation_id, user_id, content, *, message_status, reply_to_message_id
        ):
            self.calls.append((message_status, content, reply_to_message_id))
            return "assistant-message-1"

    class NeverPipeline:
        async def execute(self, ctx, callback) -> None:
            raise AssertionError("rejected request must not execute the pipeline")

    memory = FakeMemory()
    service = RAGChatService(
        cast(object, memory),
        cast(StreamChatPipeline, NeverPipeline()),
        Settings(),
        chat_limiter=cast(ChatQueueLimiter, RejectingLimiter()),
    )
    sender = SseSender()

    await service.stream_chat(
        question="排队问题",
        conversation_id=None,
        deep_thinking=False,
        user_id=7,
        sender=sender,
        task_id="task-rejected",
    )
    body = "".join([frame async for frame in sender.stream()])
    frames = body.strip().split("\n\n")

    assert _event_names(body) == ["meta", "reject", "finish", "done"]
    assert json.loads(frames[1].splitlines()[1].removeprefix("data: ")) == {
        "type": "response",
        "content": "系统繁忙，请稍后再试",
    }
    assert json.loads(frames[2].splitlines()[1].removeprefix("data: ")) == {
        "messageId": "assistant-message-1",
        "title": "新对话",
        "messageStatus": "REJECTED",
    }
    assert memory.calls == [
        ("user", "排队问题", None),
        ("REJECTED", "系统繁忙，请稍后再试", "user-message-1"),
    ]


async def test_queue_timeout_still_finishes_when_persistence_fails() -> None:
    class RejectingLimiter:
        async def acquire(self, request_id: str):
            return None

    class FailingMemory:
        async def append_user_message(self, conversation_id, user_id, content):
            raise RuntimeError("database unavailable")

    class NeverPipeline:
        async def execute(self, ctx, callback) -> None:
            raise AssertionError("rejected request must not execute the pipeline")

    service = RAGChatService(
        cast(object, FailingMemory()),
        cast(StreamChatPipeline, NeverPipeline()),
        Settings(),
        chat_limiter=cast(ChatQueueLimiter, RejectingLimiter()),
    )
    sender = SseSender()

    await service.stream_chat(
        question="排队问题",
        conversation_id="conversation-1",
        deep_thinking=False,
        user_id=7,
        sender=sender,
        task_id="task-rejected",
    )
    body = "".join([frame async for frame in sender.stream()])

    assert _event_names(body) == ["meta", "reject", "finish", "done"]
    assert '"messageStatus":"REJECTED"' in body
