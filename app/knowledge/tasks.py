"""知识域 PG 队列任务处理器。"""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.ingest.kernel import DefaultIngestionKernel
from app.core.ingest.models import DocumentRef, IngestionSpec, VectorTarget
from app.framework.exceptions import ServiceException
from app.framework.task_queue import ClaimedTask
from app.knowledge.models import (
    VECTOR_DIMENSION,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentChunkLog,
    KnowledgeVector,
)


class KnowledgeTaskHandler:
    def __init__(self, engine: AsyncEngine, kernel: DefaultIngestionKernel) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._kernel = kernel

    async def handle(self, task: ClaimedTask) -> None:
        handlers = {
            "chunk-document": self._chunk_document,
            "delete-document": self._delete_document,
            "kb-cleanup": self._cleanup_base,
        }
        handler = handlers.get(task.task_type)
        if handler is None:
            raise ServiceException(f"未知任务类型: {task.task_type}")
        await handler(task.payload)

    async def mark_retry_or_failed(
        self, task: ClaimedTask, error: str, terminal: bool
    ) -> None:
        if task.task_type != "chunk-document":
            return
        doc_id = int(task.payload["docId"])
        log_id = int(task.payload["logId"])
        async with self._sessions.begin() as session:
            document = await session.get(KnowledgeDocument, doc_id)
            log = await session.get(KnowledgeDocumentChunkLog, log_id)
            status = "failed" if terminal else "pending"
            if document is not None:
                document.status = status
            if log is not None:
                log.status = status
                log.error_message = error[:4000]
                if terminal:
                    log.end_time = _now()

    async def _chunk_document(self, payload: dict) -> None:
        doc_id = int(payload["docId"])
        log_id = int(payload["logId"])
        async with self._sessions.begin() as session:
            document = await session.scalar(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.id == doc_id,
                    KnowledgeDocument.deleted == 0,
                )
                .with_for_update()
            )
            if document is None:
                raise ServiceException("文档不存在")
            kb = await session.get(KnowledgeBase, document.kb_id)
            if kb is None or kb.deleted:
                raise ServiceException("知识库不存在")
            log = await session.get(KnowledgeDocumentChunkLog, log_id)
            if log is None:
                raise ServiceException("分块日志不存在")
            document.status = "running"
            log.status = "running"
            log.start_time = _now()
            file_url = document.file_url
            filename = document.doc_name
            kb_id = document.kb_id
            target = VectorTarget(
                kb.collection_name, kb.embedding_model, VECTOR_DIMENSION
            )
            spec = IngestionSpec.from_dict(document.ingestion_spec)
        if not file_url:
            raise ServiceException("文档文件不存在")
        data = Path(file_url).read_bytes()
        outcome = await self._kernel.run(
            DocumentRef(doc_id=doc_id, kb_id=kb_id, filename=filename),
            data,
            spec,
            target,
        )
        async with self._sessions.begin() as session:
            document = await session.get(KnowledgeDocument, doc_id)
            log = await session.get(KnowledgeDocumentChunkLog, log_id)
            if document is not None:
                document.status = "success"
                document.mime_type = outcome.mime_type
                document.chunk_count = len(outcome.chunks)
            if log is not None:
                log.status = "success"
                log.extract_duration = outcome.timings.parse_ms
                log.chunk_duration = outcome.timings.chunk_ms
                log.embed_duration = outcome.timings.embed_ms
                log.persist_duration = outcome.timings.persist_ms
                log.total_duration = outcome.timings.total_ms
                log.chunk_count = len(outcome.chunks)
                log.end_time = _now()
                log.error_message = None

    async def _delete_document(self, payload: dict) -> None:
        doc_id = int(payload["docId"])
        async with self._sessions.begin() as session:
            ids = (
                await session.scalars(
                    select(KnowledgeChunk.id).where(KnowledgeChunk.doc_id == doc_id)
                )
            ).all()
            if ids:
                await session.execute(
                    delete(KnowledgeVector).where(KnowledgeVector.id.in_(ids))
                )
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id)
            )
        file_url = payload.get("fileUrl")
        if file_url:
            Path(file_url).unlink(missing_ok=True)

    async def _cleanup_base(self, payload: dict) -> None:
        collection = str(payload["collectionName"])
        async with self._sessions.begin() as session:
            await session.execute(
                delete(KnowledgeVector).where(
                    KnowledgeVector.collection_name == collection
                )
            )


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
