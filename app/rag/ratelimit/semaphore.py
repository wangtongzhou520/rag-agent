"""Redis 带租约信号量：进程崩溃后许可可由后续操作自动回收。"""

from dataclasses import dataclass
from typing import Any

from app.framework.ids import new_uuid7

_INIT_SCRIPT = """
-- ragent:semaphore:init
if redis.call('EXISTS', KEYS[1]) == 0 then
  redis.call('SET', KEYS[1], ARGV[1])
  return 1
end
return 0
"""

_ACQUIRE_SCRIPT = """
-- ragent:semaphore:acquire
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
if #expired > 0 then
  redis.call('ZREM', KEYS[2], unpack(expired))
  redis.call('INCRBY', KEYS[1], #expired)
end
local available = tonumber(redis.call('GET', KEYS[1]) or '0')
if available <= 0 then return nil end
redis.call('DECR', KEYS[1])
redis.call('ZADD', KEYS[2], ARGV[2], ARGV[3])
return ARGV[3]
"""

_AVAILABLE_SCRIPT = """
-- ragent:semaphore:available
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', ARGV[1])
if #expired > 0 then
  redis.call('ZREM', KEYS[2], unpack(expired))
  redis.call('INCRBY', KEYS[1], #expired)
end
return tonumber(redis.call('GET', KEYS[1]) or '0')
"""

_RELEASE_SCRIPT = """
-- ragent:semaphore:release
if redis.call('ZREM', KEYS[2], ARGV[1]) == 0 then return 0 end
redis.call('INCR', KEYS[1])
redis.call('PUBLISH', KEYS[3], 'permit_changed')
return 1
"""


@dataclass(frozen=True, slots=True)
class Permit:
    id: str


class PermitExpirableSemaphore:
    def __init__(self, redis: Any, name: str) -> None:
        self._redis = redis
        self._counter_key = name
        self._permits_key = f"{name}:permits"
        self.channel = f"{name}:channel"

    @property
    def counter_key(self) -> str:
        return self._counter_key

    @property
    def permits_key(self) -> str:
        return self._permits_key

    async def try_set_permits(self, permits: int) -> bool:
        if permits <= 0:
            raise ValueError("permits must be greater than zero")
        result = await self._redis.eval(
            _INIT_SCRIPT, 1, self._counter_key, permits
        )
        return bool(result)

    async def try_acquire(self, lease_seconds: float) -> Permit | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be greater than zero")
        now_ms = await self._server_time_ms()
        permit_id = new_uuid7()
        result = await self._redis.eval(
            _ACQUIRE_SCRIPT,
            2,
            self._counter_key,
            self._permits_key,
            now_ms,
            now_ms + int(lease_seconds * 1000),
            permit_id,
        )
        if result is None:
            return None
        return Permit(self._decode(result))

    async def available_permits(self) -> int:
        now_ms = await self._server_time_ms()
        return int(
            await self._redis.eval(
                _AVAILABLE_SCRIPT,
                2,
                self._counter_key,
                self._permits_key,
                now_ms,
            )
        )

    async def try_release(self, permit: Permit | str) -> bool:
        permit_id = permit.id if isinstance(permit, Permit) else permit
        return bool(
            await self._redis.eval(
                _RELEASE_SCRIPT,
                3,
                self._counter_key,
                self._permits_key,
                self.channel,
                permit_id,
            )
        )

    async def _server_time_ms(self) -> int:
        seconds, microseconds = await self._redis.time()
        return int(seconds) * 1000 + int(microseconds) // 1000

    @staticmethod
    def _decode(value: Any) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)
