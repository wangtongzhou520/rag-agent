"""意图树管理服务。"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.rag.intent.cache import IntentTreeCacheManager
from app.rag.intent.classifier import DefaultIntentClassifier
from app.rag.intent.node import IntentNode
from app.rag.intent.orm import IntentNodeRecord


class IntentTreeService:
    def __init__(self, engine: AsyncEngine, cache: IntentTreeCacheManager) -> None:
        self._engine = engine
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._cache = cache

    async def list_tree(self) -> list[IntentNode]:
        return await DefaultIntentClassifier(
            None, engine=self._engine, cache=self._cache
        ).load_intent_tree(include_disabled=True)

    async def create(self, data: dict, user_id: int) -> int:
        self._validate(data)
        async with self._sessions.begin() as session:
            row = IntentNodeRecord(**self._record_data(data), created_by=user_id)
            session.add(row)
            await session.flush()
            result = int(row.id)
        await self._cache.evict()
        return result

    async def update(self, node_id: int, data: dict, user_id: int) -> None:
        self._validate(data)
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(IntentNodeRecord).where(
                    IntentNodeRecord.id == node_id, IntentNodeRecord.deleted == 0
                )
            )
            if row is None:
                raise ValueError("意图节点不存在")
            for key, value in self._record_data(data).items():
                setattr(row, key, value)
            row.updated_by = user_id
        await self._cache.evict()

    async def delete(self, node_id: int) -> None:
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(IntentNodeRecord).where(
                    IntentNodeRecord.id == node_id, IntentNodeRecord.deleted == 0
                )
            )
            if row is None:
                raise ValueError("意图节点不存在")
            row.deleted = 1
        await self._cache.evict()

    async def batch_enable(self, node_ids: list[int], enabled: bool) -> None:
        await self._batch_update(node_ids, {"enabled": int(enabled)})

    async def batch_delete(self, node_ids: list[int]) -> None:
        await self._batch_update(node_ids, {"deleted": 1})

    async def _batch_update(self, node_ids: list[int], values: dict) -> None:
        if not node_ids or len(node_ids) > 500:
            raise ValueError("ids 必填且最多 500 个")
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(IntentNodeRecord)
                .where(
                    IntentNodeRecord.id.in_(set(node_ids)),
                    IntentNodeRecord.deleted == 0,
                )
                .values(**values)
            )
            if result.rowcount != len(set(node_ids)):
                raise ValueError("部分意图节点不存在")
        await self._cache.evict()

    @staticmethod
    def _validate(data: dict) -> None:
        if not str(data.get("intent_code", "")).strip() or not str(data.get("name", "")).strip():
            raise ValueError("intentCode 和 name 不能为空")
        if data.get("level", 0) not in {0, 1, 2} or data.get("kind", 0) not in {0, 1, 2}:
            raise ValueError("level 或 kind 不合法")

    @staticmethod
    def _record_data(data: dict) -> dict:
        return {
            "kb_id": data.get("kb_id"),
            "intent_code": data["intent_code"].strip(),
            "name": data["name"].strip(),
            "level": data.get("level", 0),
            "parent_code": data.get("parent_code"),
            "description": data.get("description"),
            "examples": data.get("examples", []),
            "collection_name": data.get("collection_name"),
            "collection_names": data.get("collection_names", []),
            "kind": data.get("kind", 0),
            "mcp_tool_id": data.get("mcp_tool_id"),
            "top_k": data.get("top_k"),
            "enabled": int(data.get("enabled", True)),
        }
