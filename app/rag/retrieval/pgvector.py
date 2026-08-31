"""pgvector cosine 单通道检索（M1）。"""

import asyncio
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
from app.rag.retrieval.scope import ScopeQuota

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

    async def retrieve(
        self,
        question: str,
        *,
        limit: int | None = None,
        collections: tuple[str, ...] = (),
        supplement_ratio: float = 0.0,
    ) -> list[RetrievedChunk]:
        try:
            resolved_limit = max(1, limit or self._top_k)
            groups = await self._collection_groups()
            if not groups:
                return []
            targets = set(collections)
            all_collections = {
                collection for values in groups.values() for collection in values
            }
            quota = ScopeQuota.split(
                resolved_limit,
                supplement_ratio,
                directed=bool(targets),
                has_supplement=bool(all_collections - targets),
            )
            collected: list[RetrievedChunk] = []
            for model_id, model_collections in groups.items():
                primary = (
                    [value for value in model_collections if value in targets]
                    if targets
                    else model_collections
                )
                supplement = (
                    [value for value in model_collections if value not in targets]
                    if targets and quota.supplement
                    else []
                )
                if not primary and not supplement:
                    continue
                vector = await self._embedding.embed(question, model_id=model_id)
                branches = await asyncio.gather(
                    *(
                        [self._search(vector, primary, quota.primary)]
                        if primary and quota.primary
                        else []
                    ),
                    *(
                        [self._search(vector, supplement, quota.supplement)]
                        if supplement and quota.supplement
                        else []
                    ),
                    return_exceptions=True,
                )
                for branch in branches:
                    if isinstance(branch, list):
                        collected.extend(branch)
            collected.sort(key=lambda item: (-item.score, item.doc_id, str(item.id)))
            unique = {item.key: item for item in collected}
            return sorted(
                unique.values(), key=lambda item: (-item.score, item.doc_id, str(item.id))
            )[:resolved_limit]
        except Exception:
            logger.exception("pgvector 检索失败，按空通道降级")
            return []

    async def _collection_groups(
        self, collections: tuple[str, ...] = ()
    ) -> dict[str, list[str]]:
        filters = [KnowledgeBase.deleted == 0]
        if collections:
            filters.append(KnowledgeBase.collection_name.in_(collections))
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        KnowledgeBase.embedding_model,
                        KnowledgeBase.collection_name,
                    ).where(*filters)
                )
            ).all()
        grouped: dict[str, list[str]] = defaultdict(list)
        for model_id, collection in rows:
            grouped[str(model_id)].append(str(collection))
        return dict(grouped)

    async def _search(
        self, query_vector: list[float], collections: list[str], limit: int
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
            .limit(limit)
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
