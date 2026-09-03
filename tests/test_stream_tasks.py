"""F3 流任务注册、权限隔离与服务取消终态测试。"""

import asyncio
from contextlib import suppress
from typing import cast

from app.framework.config import Settings
from app.framework.sse import SseSender
from app.framework.stream_tasks import StreamTaskManager
from app.rag.pipeline.stream_chat import StreamChatPipeline
from app.rag.service import RAGChatService


async def test_task_manager_cancels_owned_task_once_in_order() -> None:
    manager = StreamTaskManager()
    calls: list[str] = []

    async def action() -> None:
        calls.append("action")

    async def finalizer() -> None:
        calls.append("finalizer")

    await manager.register("task-1", 7, finalizer)
    await manager.bind_cancel("task-1", action)

    assert await manager.cancel("task-1", 8) is False
    assert await manager.cancel("task-1", 7) is True
    assert await manager.cancel("task-1", 7) is False
    assert calls == ["action", "finalizer"]
    assert manager.is_cancelled("task-1") is True


async def test_task_manager_runs_late_bound_cancel_after_early_stop() -> None:
    manager = StreamTaskManager()
    calls: list[str] = []

    async def action() -> None:
        calls.append("action")

    async def finalizer() -> None:
        calls.append("finalizer")

    await manager.register("task-1", 7, finalizer)

    assert await manager.cancel("task-1", 7) is True
    assert await manager.bind_cancel("task-1", action) is True
    assert calls == ["finalizer", "action"]


async def test_rag_service_stop_emits_cancel_done_and_persists_partial_answer() -> None:
    started = asyncio.Event()

    class FakeMemory:
        def __init__(self) -> None:
            self.assistant: list[tuple[str, str]] = []

        async def append_assistant_message(
            self,
            conversation_id,
            user_id,
            content,
            *,
            message_status,
            **kwargs,
        ):
            self.assistant.append((content, message_status))
            return "assistant-1"

    class BlockingPipeline:
        async def execute(self, ctx, callback) -> None:
            await callback.on_content("部分回答")
            started.set()
            await asyncio.Event().wait()

    memory = FakeMemory()
    manager = StreamTaskManager()
    service = RAGChatService(
        cast(object, memory),
        cast(StreamChatPipeline, BlockingPipeline()),
        Settings(),
        task_manager=manager,
    )
    sender = SseSender()
    producer = asyncio.create_task(
        service.stream_chat(
            question="测试停止",
            conversation_id="conversation-1",
            deep_thinking=False,
            user_id=7,
            sender=sender,
            task_id="task-1",
        )
    )

    await started.wait()
    assert await manager.cancel("task-1", 7) is True
    with suppress(asyncio.CancelledError):
        await producer
    body = "".join([frame async for frame in sender.stream()])

    assert "event: meta" in body
    assert '"taskId":"task-1"' in body
    assert "event: cancel" in body
    assert '"messageId":"assistant-1"' in body
    assert '"messageStatus":"INTERRUPTED"' in body
    assert body.rstrip().endswith("event: done\ndata: [DONE]")
    assert memory.assistant == [("部分回答", "INTERRUPTED")]
