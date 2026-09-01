"""检索结果元数据批量回表富化。"""

from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.rag.retrieval.models import RetrievedChunk


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    doc_id: int
    doc_name: str
    source_type: str
    file_type: str | None = None
    url: str | None = None
    chunk_index: int | None = None


class MetadataResolver(Protocol):
    async def resolve_chunks(
        self, chunk_ids: tuple[UUID, ...]
    ) -> dict[UUID, DocumentMetadata]: ...

    async def resolve_documents(
        self, doc_ids: tuple[int, ...]
    ) -> dict[int, DocumentMetadata]: ...


class ChunkMetadataResolver:
    """以两次批量查询覆盖 chunk 主键与仅有 docId 的图谱证据。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def resolve_chunks(
        self, chunk_ids: tuple[UUID, ...]
    ) -> dict[UUID, DocumentMetadata]:
        if not chunk_ids:
            return {}
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(KnowledgeChunk, KnowledgeDocument)
                    .join(
                        KnowledgeDocument,
                        KnowledgeDocument.id == KnowledgeChunk.doc_id,
                    )
                    .where(KnowledgeChunk.id.in_(chunk_ids))
                )
            ).all()
        return {
            chunk.id: self._metadata(document, chunk.chunk_index)
            for chunk, document in rows
        }

    async def resolve_documents(
        self, doc_ids: tuple[int, ...]
    ) -> dict[int, DocumentMetadata]:
        if not doc_ids:
            return {}
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.id.in_(doc_ids)
                    )
                )
            ).all()
        return {document.id: self._metadata(document) for document in rows}

    @staticmethod
    def _metadata(
        document: KnowledgeDocument, chunk_index: int | None = None
    ) -> DocumentMetadata:
        return DocumentMetadata(
            doc_id=document.id,
            doc_name=document.doc_name,
            source_type=document.source_type,
            file_type=document.file_type,
            url=document.source_location,
            chunk_index=chunk_index,
        )


class MetadataEnrichmentPostProcessor:
    order = 20

    def __init__(self, resolver: MetadataResolver) -> None:
        self._resolver = resolver

    async def process(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []
        chunk_ids = tuple(dict.fromkeys(item.id for item in chunks))
        by_chunk = await self._resolver.resolve_chunks(chunk_ids)
        enriched = [self._replace(item, by_chunk.get(item.id)) for item in chunks]

        missing_doc_ids = tuple(
            dict.fromkeys(
                item.doc_id
                for item in enriched
                if item.doc_id is not None and not item.doc_name
            )
        )
        by_document = await self._resolver.resolve_documents(missing_doc_ids)
        return [
            self._replace(item, by_document.get(item.doc_id))
            if item.doc_id is not None and not item.doc_name
            else item
            for item in enriched
        ]

    @staticmethod
    def _replace(
        chunk: RetrievedChunk, metadata: DocumentMetadata | None
    ) -> RetrievedChunk:
        if metadata is None:
            return chunk
        return replace(
            chunk,
            doc_id=metadata.doc_id,
            doc_name=metadata.doc_name,
            source_type=metadata.source_type,
            chunk_index=metadata.chunk_index
            if metadata.chunk_index is not None
            else chunk.chunk_index,
            file_type=metadata.file_type,
            url=metadata.url,
        )
