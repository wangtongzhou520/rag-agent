"""进程内流任务注册与幂等取消。Redis 跨实例广播在 M5 接入。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

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
