"""pgvector cosine 单通道检索（M1）。"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.logging import get_logger
from app.knowledge.models import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVector,
)
from app.model_runtime.embedding.service import EmbeddingService
from app.rag.retrieval.models import RetrievedChunk

logger = get_logger(__name__)


class PgVectorRetrievalEngine:
    """按知识库 embedding 模型分组查询，避免混用不同语义空间。"""

    def __init__(
        self,
        engine: AsyncEngine,
        embedding: EmbeddingService,
        *,
        top_k: int = 10,
    ) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._embedding = embedding
        self._top_k = max(1, top_k)

    async def retrieve(self, question: str) -> list[RetrievedChunk]:
        try:
            groups = await self._collection_groups()
            if not groups:
                return []
            collected: list[RetrievedChunk] = []
            for model_id, collections in groups.items():
                vector = await self._embedding.embed(question, model_id=model_id)
                collected.extend(await self._search(vector, collections))
            collected.sort(key=lambda item: (-item.score, item.doc_id, str(item.id)))
            return collected[: self._top_k]
        except Exception:
            logger.exception("pgvector 检索失败，按空通道降级")
            return []

    async def _collection_groups(self) -> dict[str, list[str]]:
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        KnowledgeBase.embedding_model,
                        KnowledgeBase.collection_name,
                    ).where(KnowledgeBase.deleted == 0)
                )
            ).all()
        grouped: dict[str, list[str]] = defaultdict(list)
        for model_id, collection in rows:
            grouped[str(model_id)].append(str(collection))
        return dict(grouped)

    async def _search(
        self, query_vector: list[float], collections: list[str]
    ) -> list[RetrievedChunk]:
        distance = KnowledgeVector.embedding.cosine_distance(query_vector).label(
            "distance"
        )
        statement = (
            select(KnowledgeChunk, KnowledgeDocument, distance)
            .join(KnowledgeVector, KnowledgeVector.id == KnowledgeChunk.id)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.doc_id)
            .where(
                KnowledgeVector.collection_name.in_(collections),
                KnowledgeChunk.deleted == 0,
                KnowledgeChunk.enabled == 1,
                KnowledgeDocument.deleted == 0,
                KnowledgeDocument.enabled == 1,
                KnowledgeDocument.status == "success",
            )
            .order_by(distance)
            .limit(self._top_k)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            RetrievedChunk(
                id=chunk.id,
                text=chunk.content,
                score=max(0.0, 1.0 - float(raw_distance)),
                doc_id=document.id,
                doc_name=document.doc_name,
                source_type=document.source_type,
                file_type=document.file_type,
                url=document.source_location,
            )
            for chunk, document, raw_distance in rows
        ]
