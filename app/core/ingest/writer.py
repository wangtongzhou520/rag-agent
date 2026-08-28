"""关系 chunk 与 pgvector 的同事务 replaceDocument 写入。"""

import hashlib

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.chunk.models import EmbeddedChunk
from app.core.ingest.models import DocumentRef, VectorTarget
from app.knowledge.models import KnowledgeChunk, KnowledgeVector


class PgChunkIndexWriter:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def replace_document(
        self,
        target: VectorTarget,
        document: DocumentRef,
        chunks: list[EmbeddedChunk],
    ) -> None:
        async with self._sessions.begin() as session:
            old_ids = (
                await session.scalars(
                    KnowledgeChunk.__table__.select()
                    .with_only_columns(KnowledgeChunk.id)
                    .where(KnowledgeChunk.doc_id == document.doc_id)
                )
            ).all()
            if old_ids:
                await session.execute(
                    delete(KnowledgeVector).where(KnowledgeVector.id.in_(old_ids))
                )
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == document.doc_id)
            )
            for item in chunks:
                chunk = item.chunk
                session.add(
                    KnowledgeChunk(
                        id=chunk.id,
                        kb_id=document.kb_id,
                        doc_id=document.doc_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        content_hash=hashlib.sha256(chunk.content.encode()).hexdigest(),
                        char_count=len(chunk.content),
                        embedding_text=chunk.embedding_text,
                    )
                )
                session.add(
                    KnowledgeVector(
                        id=chunk.id,
                        collection_name=target.partition,
                        content=chunk.content,
                        extra_metadata={
                            **chunk.metadata,
                            "doc_id": document.doc_id,
                            "chunk_index": chunk.chunk_index,
                            "outline_path": list(chunk.outline_path),
                        },
                        embedding=list(item.vector),
                    )
                )
