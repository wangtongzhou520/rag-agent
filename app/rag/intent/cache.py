"""意图树 Redis 读穿缓存。"""

import json

from redis.asyncio import Redis

from app.rag.intent.node import IntentNode


class IntentTreeCacheManager:
    TTL_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, redis: Redis, key_prefix: str = "ragent:") -> None:
        self._redis = redis
        self._key = f"{key_prefix}intent:tree"

    async def get(self) -> list[IntentNode] | None:
        raw = await self._redis.get(self._key)
        if raw is None:
            return None
        try:
            return self._decode(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            await self._redis.delete(self._key)
            return None

    async def put(self, roots: list[IntentNode]) -> None:
        await self._redis.set(self._key, json.dumps([self._encode(node) for node in roots], ensure_ascii=False), ex=self.TTL_SECONDS)

    async def evict(self) -> None:
        await self._redis.delete(self._key)

    @classmethod
    def _encode(cls, node: IntentNode) -> dict:
        return {"id": node.id, "intent_code": node.intent_code, "name": node.name, "level": node.level, "kind": node.kind, "description": node.description, "examples": list(node.examples), "parent_code": node.parent_code, "collection_name": node.collection_name, "collection_names": list(node.collection_names), "mcp_tool_id": node.mcp_tool_id, "top_k": node.top_k, "full_path": node.full_path, "children": [cls._encode(child) for child in node.children]}

    @classmethod
    def _decode(cls, value: list[dict]) -> list[IntentNode]:
        def build(item: dict) -> IntentNode:
            children = [build(child) for child in item.get("children", [])]
            return IntentNode(**{key: item.get(key) for key in ("id", "intent_code", "name", "level", "kind", "description", "parent_code", "collection_name", "mcp_tool_id", "top_k", "full_path")} , examples=tuple(item.get("examples") or ()), collection_names=tuple(item.get("collection_names") or ()), children=children)
        return [build(item) for item in value]
