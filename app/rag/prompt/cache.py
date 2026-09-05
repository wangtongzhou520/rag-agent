"""解析后 Prompt 的 Redis 缓存，故障时透明回源。"""

import json

from redis.asyncio import Redis

from app.framework.logging import get_logger

logger = get_logger(__name__)


class AgentPromptCache:
    def __init__(self, redis: Redis, key_prefix: str, ttl_seconds: int = 3600) -> None:
        self._redis = redis
        self._key = f"{key_prefix}agent:resolved-prompts"
        self._ttl = ttl_seconds

    async def get(self) -> dict[str, str] | None:
        try:
            raw = await self._redis.get(self._key)
            if not raw:
                return None
            value = json.loads(raw)
            if not isinstance(value, dict):
                return None
            return {str(key): str(content) for key, content in value.items()}
        except Exception:
            logger.exception("agent prompt cache read failed")
            return None

    async def set(self, value: dict[str, str]) -> None:
        try:
            await self._redis.set(
                self._key,
                json.dumps(value, ensure_ascii=False),
                ex=self._ttl,
            )
        except Exception:
            logger.exception("agent prompt cache write failed")

    async def clear(self) -> None:
        try:
            await self._redis.delete(self._key)
        except Exception:
            logger.exception("agent prompt cache clear failed")
