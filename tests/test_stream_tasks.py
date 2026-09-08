"""F3 流任务注册、权限隔离与服务取消终态测试。"""

import asyncio
from contextlib import suppress
from typing import cast

from app.framework.config import Settings
from app.framework.sse import SseSender
from app.framework.stream_tasks import RedisStreamTaskManager, StreamTaskManager
from app.rag.pipeline.stream_chat import StreamChatPipeline
from app.rag.service import RAGChatService


class MemoryPubSub:
    def __init__(self, redis: "MemoryRedis") -> None:
        self.redis = redis
        self.channel = ""
        self.queue: asyncio.Queue[dict] = asyncio.Queue()

    async def subscribe(self, channel: str) -> None:
        self.channel = channel
        self.redis.subscribers.add(self)

    async def listen(self):
        while True:
            yield await self.queue.get()

    async def aclose(self) -> None:
        self.redis.subscribers.discard(self)


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.subscribers: set[MemoryPubSub] = set()

    async def set(self, key: str, value: str, **_kwargs) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    async def publish(self, channel: str, value: str) -> None:
        for subscriber in tuple(self.subscribers):
            if subscriber.channel == channel:
                await subscriber.queue.put({"type": "message", "data": value})

    def pubsub(self) -> MemoryPubSub:
        return MemoryPubSub(self)


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


async def test_redis_manager_routes_owned_cancel_to_remote_instance() -> None:
    redis = MemoryRedis()
    source = RedisStreamTaskManager(redis)
    target = RedisStreamTaskManager(redis)
    calls: list[str] = []
    cancelled = asyncio.Event()

    async def action() -> None:
        calls.append("action")

    async def finalizer() -> None:
        calls.append("finalizer")
        cancelled.set()

    await source.start()
    await target.start()
    try:
        for _ in range(20):
            if len(redis.subscribers) == 2:
                break
            await asyncio.sleep(0)
        await target.register("task-remote", 7, finalizer)
        await target.bind_cancel("task-remote", action)

        assert await source.cancel("task-remote", 8) is False
        assert await source.cancel("task-remote", 7) is True
        await asyncio.wait_for(cancelled.wait(), timeout=1)

        assert calls == ["action", "finalizer"]
        assert target.is_cancelled("task-remote") is True
        assert redis.values["ragent:stream:cancel:task-remote"] == "7"
    finally:
        await source.close()
        await target.close()


async def test_redis_manager_replays_cancel_marker_during_registration() -> None:
    redis = MemoryRedis()
    redis.values["ragent:stream:cancel:task-early"] = "7"
    manager = RedisStreamTaskManager(redis)
    calls: list[str] = []

    async def action() -> None:
        calls.append("action")

    async def finalizer() -> None:
        calls.append("finalizer")

    await manager.register("task-early", 7, finalizer)
    await manager.bind_cancel("task-early", action)

    assert manager.is_cancelled("task-early") is True
    assert calls == ["finalizer", "action"]


async def test_redis_manager_replays_missed_broadcast_when_binding() -> None:
    redis = MemoryRedis()
    manager = RedisStreamTaskManager(redis)
    calls: list[str] = []

    async def action() -> None:
        calls.append("action")

    async def finalizer() -> None:
        calls.append("finalizer")

    await manager.register("task-bind", 7, finalizer)
    redis.values["ragent:stream:cancel:task-bind"] = "7"

    await manager.bind_cancel("task-bind", action)

    assert manager.is_cancelled("task-bind") is True
    assert calls == ["action", "finalizer"]


async def test_redis_timeout_keeps_local_cancellation_available() -> None:
    class HangingRedis(MemoryRedis):
        async def get(self, key: str) -> str | None:
            await asyncio.Event().wait()
            return await super().get(key)

    manager = RedisStreamTaskManager(
        HangingRedis(), redis_timeout_seconds=0.05
    )
    calls: list[str] = []

    async def finalizer() -> None:
        calls.append("finalizer")

    await asyncio.wait_for(manager.register("task-local", 7, finalizer), timeout=0.2)

    assert await manager.cancel("task-local", 7) is True
    assert calls == ["finalizer"]


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
