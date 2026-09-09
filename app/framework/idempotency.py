"""Redis 提交锁与消费三态标记，供 API 和 Worker 跨实例协调。"""

from enum import StrEnum
from typing import Any

from app.framework.exceptions import ServiceException
from app.framework.ids import new_uuid7

_UNLOCK_SCRIPT = """
-- ragent:idempotency:unlock
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""

_TRY_BEGIN_SCRIPT = """
-- ragent:idempotency:try-begin
local current = redis.call('GET', KEYS[1])
if current then return current end
redis.call('SET', KEYS[1], '0:' .. ARGV[2], 'PX', ARGV[1])
return '-1'
"""

_MARK_CONSUMED_SCRIPT = """
-- ragent:idempotency:mark-consumed
if redis.call('GET', KEYS[1]) ~= '0:' .. ARGV[1] then return 0 end
redis.call('SET', KEYS[1], '1', 'EX', ARGV[2])
return 1
"""

_ROLLBACK_CONSUME_SCRIPT = """
-- ragent:idempotency:rollback-consume
if redis.call('GET', KEYS[1]) ~= '0:' .. ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""


class ConsumeState(StrEnum):
    FIRST_RUN = "FIRST_RUN"
    CONSUMING = "CONSUMING"
    CONSUMED = "CONSUMED"


class ConsumeInProgressError(ServiceException):
    """另一执行者仍持有 CONSUMING 标记；应延迟归还而非计入失败重试。"""


class SubmitLockExecutor:
    """唯一 token 的 SET NX 锁；释放时 Lua 校验 token，避免误删新锁。"""

    def __init__(
        self, redis: Any, key_prefix: str, *, ttl_seconds: float = 330
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        self._redis = redis
        self._prefix = f"{key_prefix}idempotent-submit:key:"
        self._ttl_ms = int(ttl_seconds * 1000)

    async def try_lock(self, value: str) -> str | None:
        token = new_uuid7()
        acquired = await self._redis.set(
            f"{self._prefix}{value}", token, nx=True, px=self._ttl_ms
        )
        return token if acquired else None

    async def unlock(self, value: str, token: str) -> bool:
        return bool(
            await self._redis.eval(
                _UNLOCK_SCRIPT, 1, f"{self._prefix}{value}", token
            )
        )


class ConsumeMarkExecutor:
    """nil/0/1 三态消费标记；相同 event_id 跨 Worker 共享。"""

    def __init__(
        self,
        redis: Any,
        key_prefix: str,
        *,
        ttl_seconds: float = 3600,
        consuming_ttl_seconds: float | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        if consuming_ttl_seconds is not None and consuming_ttl_seconds <= 0:
            raise ValueError("consuming_ttl_seconds must be greater than zero")
        self._redis = redis
        self._prefix = f"{key_prefix}idempotent-consume:"
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._ttl_ms = int((consuming_ttl_seconds or ttl_seconds) * 1000)
        self._tokens: dict[str, str] = {}

    async def try_begin(self, business_key: str) -> ConsumeState:
        token = new_uuid7()
        result = await self._redis.eval(
            _TRY_BEGIN_SCRIPT,
            1,
            f"{self._prefix}{business_key}",
            self._ttl_ms,
            token,
        )
        value = result.decode() if isinstance(result, bytes) else str(result)
        if value == "-1":
            self._tokens[business_key] = token
            return ConsumeState.FIRST_RUN
        if value == "0" or value.startswith("0:"):
            return ConsumeState.CONSUMING
        if value == "1":
            return ConsumeState.CONSUMED
        raise RuntimeError(f"unknown consume idempotency state: {value}")

    async def mark_consumed(self, business_key: str) -> bool:
        token = self._tokens.pop(business_key, None)
        if token is None:
            return False
        return bool(
            await self._redis.eval(
                _MARK_CONSUMED_SCRIPT,
                1,
                f"{self._prefix}{business_key}",
                token,
                self._ttl_seconds,
            )
        )

    async def rollback(self, business_key: str) -> bool:
        token = self._tokens.pop(business_key, None)
        if token is None:
            return False
        return bool(
            await self._redis.eval(
                _ROLLBACK_CONSUME_SCRIPT,
                1,
                f"{self._prefix}{business_key}",
                token,
            )
        )
