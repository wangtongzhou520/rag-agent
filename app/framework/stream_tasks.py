"""流任务注册与幂等取消；Redis 协调器负责跨 API 实例路由。"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from app.framework.logging import get_logger

logger = get_logger(__name__)
CancelAction = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class _TaskEntry:
    user_id: int
    created_at: float
    finalizer: CancelAction
    cancel_action: CancelAction | None = None
    cancelled: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class StreamTaskManager:
    """维护当前进程中的流任务，所有取消副作用最多执行一次。"""

    def __init__(self, *, max_entries: int = 10_000, ttl_seconds: int = 30 * 60) -> None:
        self._entries: dict[str, _TaskEntry] = {}
        self._max_entries = max(1, max_entries)
        self._ttl_seconds = max(1, ttl_seconds)

    async def register(self, task_id: str, user_id: int, finalizer: CancelAction) -> None:
        self._prune()
        if len(self._entries) >= self._max_entries:
            oldest = min(self._entries, key=lambda key: self._entries[key].created_at)
            self._entries.pop(oldest, None)
        self._entries[task_id] = _TaskEntry(
            user_id=user_id,
            created_at=time.monotonic(),
            finalizer=finalizer,
        )

    async def bind_cancel(self, task_id: str, action: CancelAction) -> bool:
        entry = self._entries.get(task_id)
        if entry is None:
            return False
        async with entry.lock:
            entry.cancel_action = action
            run_immediately = entry.cancelled
        if run_immediately:
            await self._run(action, task_id, "late cancel action")
        return True

    async def cancel(self, task_id: str, user_id: int) -> bool:
        """取消本人任务；任务不存在、已完成或不属于本人时均幂等返回 False。"""
        self._prune()
        entry = self._entries.get(task_id)
        if entry is None or entry.user_id != user_id:
            return False
        async with entry.lock:
            if entry.cancelled:
                return False
            entry.cancelled = True
            action = entry.cancel_action
            finalizer = entry.finalizer
        if action is not None:
            await self._run(action, task_id, "cancel action")
        await self._run(finalizer, task_id, "cancel finalizer")
        return True

    def is_cancelled(self, task_id: str) -> bool:
        entry = self._entries.get(task_id)
        return bool(entry and entry.cancelled)

    async def unregister(self, task_id: str) -> None:
        self._entries.pop(task_id, None)

    def owner(self, task_id: str) -> int | None:
        entry = self._entries.get(task_id)
        return entry.user_id if entry is not None else None

    def _prune(self) -> None:
        deadline = time.monotonic() - self._ttl_seconds
        expired = [
            task_id
            for task_id, entry in self._entries.items()
            if entry.created_at < deadline
        ]
        for task_id in expired:
            self._entries.pop(task_id, None)

    @staticmethod
    async def _run(action: CancelAction, task_id: str, label: str) -> None:
        try:
            await action()
        except asyncio.CancelledError:
            logger.info("stream task callback cancelled", task_id=task_id, callback=label)
        except Exception:
            logger.exception("stream task callback failed", task_id=task_id, callback=label)


class RedisStreamTaskManager(StreamTaskManager):
    """在本地幂等语义之上增加 Redis 归属、取消标记与跨实例广播。"""

    def __init__(
        self,
        redis: Any,
        *,
        key_prefix: str = "ragent:",
        max_entries: int = 10_000,
        ttl_seconds: int = 30 * 60,
        redis_timeout_seconds: float = 0.5,
    ) -> None:
        super().__init__(max_entries=max_entries, ttl_seconds=ttl_seconds)
        self._redis = redis
        self._ttl_seconds = max(1, ttl_seconds)
        self._redis_timeout_seconds = max(0.05, redis_timeout_seconds)
        self._owner_prefix = f"{key_prefix}stream:owner:"
        self._cancel_prefix = f"{key_prefix}stream:cancel:"
        self._topic = f"{key_prefix}stream:cancel"
        self._listener: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()

    async def start(self) -> None:
        if self._listener is None or self._listener.done():
            self._closed.clear()
            self._listener = asyncio.create_task(
                self._listen(), name="stream-cancel-listener"
            )

    async def close(self) -> None:
        self._closed.set()
        if self._listener is None:
            return
        self._listener.cancel()
        with suppress(asyncio.CancelledError):
            await self._listener
        self._listener = None

    async def register(
        self, task_id: str, user_id: int, finalizer: CancelAction
    ) -> None:
        await super().register(task_id, user_id, finalizer)
        try:
            async with asyncio.timeout(self._redis_timeout_seconds):
                await self._redis.set(
                    self._owner_key(task_id), str(user_id), ex=self._ttl_seconds
                )
                cancelled_by = await self._redis.get(self._cancel_key(task_id))
        except Exception:
            logger.exception("stream task Redis register failed", task_id=task_id)
            return
        if cancelled_by == str(user_id):
            await super().cancel(task_id, user_id)

    async def cancel(self, task_id: str, user_id: int) -> bool:
        """校验 Redis 归属后写取消标记并广播；本机任务在广播前立即取消。"""
        local_owner = self.owner(task_id)
        if local_owner is not None and local_owner != user_id:
            return False
        if local_owner is None:
            try:
                async with asyncio.timeout(self._redis_timeout_seconds):
                    remote_owner = await self._redis.get(self._owner_key(task_id))
            except Exception:
                logger.exception("stream task Redis owner lookup failed", task_id=task_id)
                return False
            if remote_owner != str(user_id):
                return False

        cancelled_local = await super().cancel(task_id, user_id)
        try:
            async with asyncio.timeout(self._redis_timeout_seconds):
                await self._redis.set(
                    self._cancel_key(task_id), str(user_id), ex=self._ttl_seconds
                )
                await self._redis.publish(
                    self._topic,
                    json.dumps({"taskId": task_id, "userId": user_id}),
                )
        except Exception:
            logger.exception("stream task Redis cancel broadcast failed", task_id=task_id)
            return cancelled_local
        return True

    async def bind_cancel(self, task_id: str, action: CancelAction) -> bool:
        bound = await super().bind_cancel(task_id, action)
        if not bound:
            return False
        user_id = self.owner(task_id)
        if user_id is None:
            return True
        try:
            async with asyncio.timeout(self._redis_timeout_seconds):
                cancelled_by = await self._redis.get(self._cancel_key(task_id))
        except Exception:
            logger.exception("stream task Redis bind replay failed", task_id=task_id)
            return True
        if cancelled_by == str(user_id):
            await super().cancel(task_id, user_id)
        return True

    async def unregister(self, task_id: str) -> None:
        await super().unregister(task_id)
        try:
            async with asyncio.timeout(self._redis_timeout_seconds):
                await self._redis.delete(self._owner_key(task_id))
        except Exception:
            logger.exception("stream task Redis unregister failed", task_id=task_id)

    async def _listen(self) -> None:
        while not self._closed.is_set():
            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(self._topic)
                await self._replay_registered()
                async for message in pubsub.listen():
                    if self._closed.is_set():
                        return
                    if message.get("type") != "message":
                        continue
                    await self._handle_message(message.get("data"))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("stream cancel Redis subscription failed; reconnecting")
                try:
                    await asyncio.wait_for(self._closed.wait(), timeout=1)
                except TimeoutError:
                    pass
            finally:
                with suppress(Exception):
                    await pubsub.aclose()

    async def _handle_message(self, raw: object) -> None:
        try:
            payload = json.loads(str(raw))
            task_id = str(payload["taskId"])
            user_id = int(payload["userId"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("ignored invalid stream cancel message")
            return
        await super().cancel(task_id, user_id)

    async def _replay_registered(self) -> None:
        entries = list(self._entries.items())
        if not entries:
            return
        try:
            async with asyncio.timeout(self._redis_timeout_seconds):
                markers = await self._redis.mget(
                    [self._cancel_key(task_id) for task_id, _ in entries]
                )
        except Exception:
            logger.exception("stream task Redis reconnect replay failed")
            return
        for (task_id, entry), cancelled_by in zip(entries, markers, strict=True):
            if cancelled_by == str(entry.user_id):
                await super().cancel(task_id, entry.user_id)

    def _owner_key(self, task_id: str) -> str:
        return f"{self._owner_prefix}{task_id}"

    def _cancel_key(self, task_id: str) -> str:
        return f"{self._cancel_prefix}{task_id}"
