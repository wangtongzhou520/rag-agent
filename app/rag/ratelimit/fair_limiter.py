"""基于 Redis ZSet 与租约信号量的跨实例 FIFO 问答限流器。"""

import asyncio
from contextlib import suppress
from typing import Any

from app.framework.logging import get_logger
from app.rag.ratelimit.semaphore import Permit, PermitExpirableSemaphore

logger = get_logger(__name__)

_CLAIM_AND_ACQUIRE_SCRIPT = """
-- ragent:fair-limiter:claim-and-acquire
local head = redis.call('ZRANGE', KEYS[1], 0, 16)
local first_live = nil
for _, member in ipairs(head) do
  if redis.call('EXISTS', ARGV[1] .. member) == 1 then
    first_live = member
    break
  end
  redis.call('ZREM', KEYS[1], member)
end
if first_live ~= ARGV[2] then return nil end

local expired = redis.call('ZRANGEBYSCORE', KEYS[4], '-inf', ARGV[3])
if #expired > 0 then
  redis.call('ZREM', KEYS[4], unpack(expired))
  redis.call('INCRBY', KEYS[3], #expired)
end
local available = tonumber(redis.call('GET', KEYS[3]) or '0')
if available <= 0 then return nil end

redis.call('ZREM', KEYS[1], ARGV[2])
redis.call('DEL', ARGV[1] .. ARGV[2])
redis.call('DECR', KEYS[3])
redis.call('ZADD', KEYS[4], ARGV[4], ARGV[5])
redis.call('PUBLISH', KEYS[5], 'permit_changed')
return ARGV[5]
"""


class FairDistributedRateLimiter:
    """每次只从存活队头发放许可，确保跨实例严格 FIFO。"""

    ENTRY_TTL_BUFFER_MS = 5000

    def __init__(
        self,
        redis: Any,
        *,
        name: str,
        max_concurrent: int,
        max_wait_seconds: float,
        lease_seconds: float,
        poll_interval_ms: int,
    ) -> None:
        self._redis = redis
        self._name = name
        self._queue_key = f"{name}:queue"
        self._sequence_key = f"{name}:queue:seq"
        self._entry_prefix = f"{name}:entry:"
        self._notify_channel = f"{name}:queue:notify"
        self._max_concurrent = max_concurrent
        self._max_wait_seconds = max_wait_seconds
        self._lease_seconds = lease_seconds
        self._poll_seconds = max(50, poll_interval_ms) / 1000
        self._semaphore = PermitExpirableSemaphore(redis, f"{name}:semaphore")
        # redis-py 的默认连接池是有界的；突发入队/轮询先在实例内背压，
        # 避免尚未进入全局队列就因连接池耗尽而失败。
        self._redis_gate = asyncio.Semaphore(16)
        self._notify = asyncio.Event()
        self._subscriber_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._semaphore.try_set_permits(self._max_concurrent)
        if self._subscriber_task is None:
            self._subscriber_task = asyncio.create_task(
                self._subscribe(), name=f"rate-limit-notify:{self._name}"
            )

    async def close(self) -> None:
        task = self._subscriber_task
        self._subscriber_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def acquire(self, request_id: str) -> Permit | None:
        """入队并等待许可；超时返回 None，取消时必定清理队列。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._max_wait_seconds
        ttl_ms = int(self._max_wait_seconds * 1000) + self.ENTRY_TTL_BUFFER_MS
        entry_key = f"{self._entry_prefix}{request_id}"
        async with self._redis_gate:
            await self._redis.set(entry_key, "1", px=ttl_ms)
            score = await self._redis.incr(self._sequence_key)
            await self._redis.zadd(self._queue_key, {request_id: score})
            await self._redis.publish(self._notify_channel, "permit_changed")
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return None
                permit = await self._try_claim(request_id)
                if permit is not None:
                    if loop.time() >= deadline:
                        await self.release(permit)
                        return None
                    return permit
                self._notify.clear()
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._notify.wait(), min(remaining, self._poll_seconds)
                    )
        finally:
            await self._cleanup_waiter(request_id)

    async def release(self, permit: Permit) -> bool:
        async with self._redis_gate:
            released = await self._semaphore.try_release(permit)
            if released:
                await self._redis.publish(self._notify_channel, "permit_changed")
        return released

    async def _try_claim(self, request_id: str) -> Permit | None:
        async with self._redis_gate:
            seconds, microseconds = await self._redis.time()
            now_ms = int(seconds) * 1000 + int(microseconds) // 1000
            permit_id = f"{request_id}:permit"
            result = await self._redis.eval(
                _CLAIM_AND_ACQUIRE_SCRIPT,
                5,
                self._queue_key,
                self._sequence_key,
                self._semaphore.counter_key,
                self._semaphore.permits_key,
                self._notify_channel,
                self._entry_prefix,
                request_id,
                now_ms,
                now_ms + int(self._lease_seconds * 1000),
                permit_id,
            )
        if result is None:
            return None
        return Permit(result.decode() if isinstance(result, bytes) else str(result))

    async def _cleanup_waiter(self, request_id: str) -> None:
        async with self._redis_gate:
            removed = await self._redis.zrem(self._queue_key, request_id)
            deleted = await self._redis.delete(f"{self._entry_prefix}{request_id}")
            if removed or deleted:
                await self._redis.publish(self._notify_channel, "permit_changed")

    async def _subscribe(self) -> None:
        while True:
            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(self._notify_channel, self._semaphore.channel)
                async for message in pubsub.listen():
                    if message.get("type") == "message":
                        self._notify.set()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("rate limiter Redis subscription failed; reconnecting")
                await asyncio.sleep(1)
            finally:
                await pubsub.aclose()


class ChatQueueLimiter(FairDistributedRateLimiter):
    """语义化入口类型，供 RAGChatService 依赖注入。"""
