"""查询词映射 Redis 读穿缓存。"""

import json

from redis.asyncio import Redis

from app.rag.rewrite.models import QueryTermMapping

CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


class QueryTermMappingCacheManager:
    def __init__(self, redis: Redis, key_prefix: str = "ragent:") -> None:
        self._redis = redis
        self._key = f"{key_prefix}query-term:mappings"

    async def get(self) -> list[QueryTermMapping] | None:
        raw = await self._redis.get(self._key)
        if raw is None:
            return None
        try:
            values = json.loads(raw)
            if not isinstance(values, list):
                return None
            return [QueryTermMapping(**value) for value in values]
        except (TypeError, ValueError, json.JSONDecodeError):
            await self._redis.delete(self._key)
            return None

    async def put(self, mappings: list[QueryTermMapping]) -> None:
        payload = [
            {
                "id": mapping.id,
                "source_term": mapping.source_term,
                "target_term": mapping.target_term,
                "match_type": mapping.match_type,
                "priority": mapping.priority,
                "enabled": mapping.enabled,
                "domain": mapping.domain,
                "remark": mapping.remark,
            }
            for mapping in mappings
        ]
        await self._redis.set(
            self._key,
            json.dumps(payload, ensure_ascii=False),
            ex=CACHE_TTL_SECONDS,
        )

    async def evict(self) -> None:
        await self._redis.delete(self._key)
