"""知识库、文档和 chunk 的 M2 业务服务。"""

import asyncio
import hashlib
import uuid
from pathlib import Path

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from uuid_utils import uuid7

from app.core.parser.detector import MimeTypeDetector
from app.core.parser.registry import ParserRegistry
from app.framework.async_task import AsyncTask
from app.framework.exceptions import ClientException
from app.framework.task_queue import TaskQueue
from app.knowledge.models import (
    VECTOR_DIMENSION,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentChunkLog,
    KnowledgeVector,
)
from app.knowledge.schemas import (
    ChunkVO,
    DocumentVO,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseVO,
    Page,
)
from app.model_runtime.embedding.service import EmbeddingService


class KnowledgeService:
    def __init__(
        self,
        engine: AsyncEngine,
        detector: MimeTypeDetector,
        registry: ParserRegistry,
        embedding: EmbeddingService,
        http: httpx.AsyncClient,
        upload_dir: Path,
    ) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._detector = detector
        self._registry = registry
        self._embedding = embedding
        self._http = http
        self._upload_dir = upload_dir

    async def create_base(self, body: KnowledgeBaseCreate, user_id: int) -> str:
        name = body.name.strip()
        collection = body.collection_name.strip()
        if not name or not collection or not body.embedding_model.strip():
            raise ClientException("知识库名称、集合名和模型不能为空")
        async with self._sessions.begin() as session:
            exists = await session.scalar(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.collection_name == collection,
                    KnowledgeBase.deleted == 0,
                )
            )
            if exists is not None:
                raise ClientException("集合名称已存在")
            model = KnowledgeBase(
                name=name,
                embedding_model=body.embedding_model.strip(),
                collection_name=collection,
                created_by=user_id,
            )
            session.add(model)
            await session.flush()
            return str(model.id)

    async def update_base(
        self, kb_id: int, body: KnowledgeBaseUpdate, user_id: int
    ) -> None:
        async with self._sessions.begin() as session:
            model = await self._require_base(session, kb_id)
            if model.embedding_model != body.embedding_model:
                count = await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeDocument)
                    .where(
                        KnowledgeDocument.kb_id == kb_id,
                        KnowledgeDocument.deleted == 0,
                        KnowledgeDocument.chunk_count > 0,
                    )
                )
                if count:
                    raise ClientException("知识库已有分块文档，不能修改 Embedding 模型")
            model.name = body.name.strip()
            model.embedding_model = body.embedding_model.strip()
            model.updated_by = user_id

    async def get_base(self, kb_id: int) -> KnowledgeBaseVO:
        async with self._sessions() as session:
            return self._base_vo(await self._require_base(session, kb_id))

    async def list_bases(
        self, current: int, size: int, name: str | None
    ) -> Page[KnowledgeBaseVO]:
        current, size = _page(current, size)
        filters = [KnowledgeBase.deleted == 0]
        if name and name.strip():
            filters.append(KnowledgeBase.name.ilike(f"%{name.strip()}%"))
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(KnowledgeBase).where(*filters)
            )
            rows = (
                await session.scalars(
                    select(KnowledgeBase)
                    .where(*filters)
                    .order_by(KnowledgeBase.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        return Page(
            records=[self._base_vo(row) for row in rows],
            total=int(total or 0),
            current=current,
            size=size,
        )

    async def delete_base(self, kb_id: int, user_id: int) -> None:
        async with self._sessions.begin() as session:
            model = await self._require_base(session, kb_id)
            docs = await session.scalar(
                select(func.count())
                .select_from(KnowledgeDocument)
                .where(
                    KnowledgeDocument.kb_id == kb_id,
                    KnowledgeDocument.deleted == 0,
                )
            )
            if docs:
                raise ClientException("知识库下存在文档，不能删除")
            model.deleted = 1
            await TaskQueue.enqueue(
                session,
                "kb-cleanup",
                f"kb-cleanup:{kb_id}",
                {
                    "kbId": kb_id,
                    "collectionName": model.collection_name,
                    "operator": user_id,
                },
            )

    async def create_document(
        self,
        kb_id: int,
        user_id: int,
        *,
        filename: str | None,
        data: bytes | None,
        source_type: str,
        source_location: str | None,
        ingestion_spec: dict | None,
    ) -> DocumentVO:
        source_type = source_type.lower().strip()
        if source_type not in {"file", "url"}:
            raise ClientException("sourceType 只支持 file 或 url")
        if source_type == "url":
            if not source_location:
                raise ClientException("链接地址不能为空")
            response = await self._http.get(source_location)
            response.raise_for_status()
            data = response.content
            filename = filename or Path(httpx.URL(source_location).path).name or "remote"
        if not data:
            raise ClientException("文件内容为空")
        filename = Path(filename or "document").name
        mime = self._detector.detect(data, filename)
        if not self._registry.can_parse(mime):
            raise ClientException(f"不支持的文件类型: {mime}")
        relative = Path(str(kb_id)) / f"{uuid7()}-{filename}"
        absolute = self._upload_dir / relative
        await asyncio.to_thread(absolute.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(absolute.write_bytes, data)
        async with self._sessions.begin() as session:
            await self._require_base(session, kb_id)
            document = KnowledgeDocument(
                kb_id=kb_id,
                doc_name=filename,
                file_url=str(absolute),
                file_type=Path(filename).suffix.lower().lstrip(".") or None,
                mime_type=mime,
                file_size=len(data),
                process_mode="chunk",
                status="pending",
                source_type=source_type,
                source_location=source_location,
                ingestion_spec=ingestion_spec,
                created_by=user_id,
            )
            session.add(document)
            await session.flush()
            return self._document_vo(document)

    async def trigger_chunk(self, doc_id: int, user_id: int) -> None:
        async with self._sessions.begin() as session:
            document = await self._require_document(session, doc_id)
            active = await session.scalar(
                select(AsyncTask.id).where(
                    AsyncTask.task_type == "chunk-document",
                    AsyncTask.biz_key == f"doc:{doc_id}",
                    AsyncTask.status.in_(("pending", "running")),
                )
            )
            if active is not None:
                raise ClientException("文档正在处理中")
            log = KnowledgeDocumentChunkLog(
                doc_id=doc_id,
                status="pending",
                process_mode=document.process_mode,
                parse_profile=(document.ingestion_spec or {}).get("parseProfile", "fast"),
            )
            session.add(log)
            await session.flush()
            document.status = "pending"
            await TaskQueue.enqueue(
                session,
                "chunk-document",
                f"doc:{doc_id}",
                {"docId": doc_id, "logId": log.id, "operator": user_id},
            )

    async def get_document(self, doc_id: int) -> DocumentVO:
        async with self._sessions() as session:
            return self._document_vo(await self._require_document(session, doc_id))

    async def update_document(
        self,
        doc_id: int,
        *,
        doc_name: str,
        ingestion_spec: dict | None,
        source_location: str | None,
    ) -> None:
        if not doc_name.strip():
            raise ClientException("文档名称不能为空")
        async with self._sessions.begin() as session:
            document = await self._require_document(session, doc_id)
            if document.status == "running":
                raise ClientException("文档正在处理中")
            document.doc_name = doc_name.strip()
            document.ingestion_spec = ingestion_spec
            document.source_location = source_location

    async def search_documents(self, keyword: str | None, limit: int) -> list[DocumentVO]:
        filters = [KnowledgeDocument.deleted == 0]
        if keyword and keyword.strip():
            filters.append(KnowledgeDocument.doc_name.ilike(f"%{keyword.strip()}%"))
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(KnowledgeDocument)
                    .where(*filters)
                    .order_by(KnowledgeDocument.update_time.desc())
                    .limit(min(20, max(1, limit)))
                )
            ).all()
        return [self._document_vo(row) for row in rows]

    async def preview_document(self, doc_id: int) -> str:
        async with self._sessions() as session:
            await self._require_document(session, doc_id)
            chunks = (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(
                        KnowledgeChunk.doc_id == doc_id,
                        KnowledgeChunk.deleted == 0,
                    )
                    .order_by(KnowledgeChunk.chunk_index)
                )
            ).all()
        return "\n\n".join(chunk.content for chunk in chunks)

    async def document_file(self, doc_id: int) -> tuple[Path, str]:
        async with self._sessions() as session:
            document = await self._require_document(session, doc_id)
            if not document.file_url:
                raise ClientException("文档文件不存在")
            return Path(document.file_url), document.doc_name

    async def list_documents(
        self,
        kb_id: int,
        current: int,
        size: int,
        status: str | None,
        keyword: str | None,
    ) -> Page[DocumentVO]:
        current, size = _page(current, size)
        filters = [
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.deleted == 0,
        ]
        if status:
            filters.append(KnowledgeDocument.status == status)
        if keyword and keyword.strip():
            filters.append(KnowledgeDocument.doc_name.ilike(f"%{keyword.strip()}%"))
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(KnowledgeDocument).where(*filters)
            )
            rows = (
                await session.scalars(
                    select(KnowledgeDocument)
                    .where(*filters)
                    .order_by(KnowledgeDocument.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        return Page(
            records=[self._document_vo(row) for row in rows],
            total=int(total or 0),
            current=current,
            size=size,
        )

    async def set_document_enabled(self, doc_id: int, value: bool) -> None:
        async with self._sessions.begin() as session:
            document = await self._require_document(session, doc_id)
            document.enabled = int(value)

    async def delete_document(self, doc_id: int) -> None:
        async with self._sessions.begin() as session:
            document = await self._require_document(session, doc_id)
            document.deleted = 1
            await TaskQueue.enqueue(
                session,
                "delete-document",
                f"doc-delete:{doc_id}",
                {"docId": doc_id, "fileUrl": document.file_url},
            )

    async def list_chunks(
        self, doc_id: int, current: int, size: int, enabled: bool | None
    ) -> Page[ChunkVO]:
        current, size = _page(current, size)
        filters = [KnowledgeChunk.doc_id == doc_id, KnowledgeChunk.deleted == 0]
        if enabled is not None:
            filters.append(KnowledgeChunk.enabled == int(enabled))
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(KnowledgeChunk).where(*filters)
            )
            rows = (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(*filters)
                    .order_by(KnowledgeChunk.chunk_index)
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        return Page(
            records=[self._chunk_vo(row) for row in rows],
            total=int(total or 0),
            current=current,
            size=size,
        )

    async def set_chunk_enabled(self, chunk_id: uuid.UUID, value: bool) -> None:
        async with self._sessions.begin() as session:
            chunk = await session.get(KnowledgeChunk, chunk_id)
            if chunk is None or chunk.deleted:
                raise ClientException("分块不存在")
            chunk.enabled = int(value)

    async def batch_set_chunks_enabled(
        self, chunk_ids: list[str], value: bool
    ) -> None:
        if not chunk_ids or len(chunk_ids) > 500:
            raise ClientException("chunkIds 必填且最多 500 个")
        try:
            ids = [uuid.UUID(item) for item in dict.fromkeys(chunk_ids)]
        except ValueError as exc:
            raise ClientException("chunkId 格式错误") from exc
        async with self._sessions.begin() as session:
            chunks = (
                await session.scalars(
                    select(KnowledgeChunk).where(
                        KnowledgeChunk.id.in_(ids), KnowledgeChunk.deleted == 0
                    )
                )
            ).all()
            if len(chunks) != len(ids):
                raise ClientException("部分分块不存在")
            for chunk in chunks:
                chunk.enabled = int(value)

    async def update_chunk(self, chunk_id: uuid.UUID, content: str) -> None:
        content = content.strip()
        if not content:
            raise ClientException("分块内容不能为空")
        async with self._sessions() as session:
            chunk = await session.get(KnowledgeChunk, chunk_id)
            if chunk is None or chunk.deleted:
                raise ClientException("分块不存在")
            document = await self._require_document(session, chunk.doc_id)
            kb = await self._require_base(session, document.kb_id)
            embedding_model = kb.embedding_model
        vector = await self._embedding.embed(content, model_id=embedding_model)
        if len(vector) != VECTOR_DIMENSION:
            raise ClientException(
                f"向量维度 {len(vector)} 与要求 {VECTOR_DIMENSION} 不符"
            )
        async with self._sessions.begin() as session:
            chunk = await session.get(KnowledgeChunk, chunk_id)
            stored = await session.get(KnowledgeVector, chunk_id)
            if chunk is None or stored is None:
                raise ClientException("分块不存在")
            chunk.content = content
            chunk.embedding_text = content
            chunk.content_hash = hashlib.sha256(content.encode()).hexdigest()
            chunk.char_count = len(content)
            stored.content = content
            stored.embedding = vector

    async def delete_chunk(self, chunk_id: uuid.UUID) -> None:
        async with self._sessions.begin() as session:
            chunk = await session.get(KnowledgeChunk, chunk_id)
            if chunk is None or chunk.deleted:
                raise ClientException("分块不存在")
            doc_id = chunk.doc_id
            await session.execute(
                delete(KnowledgeVector).where(KnowledgeVector.id == chunk_id)
            )
            chunk.deleted = 1
            document = await self._require_document(session, doc_id)
            document.chunk_count = max(0, document.chunk_count - 1)

    @staticmethod
    async def _require_base(session, kb_id: int) -> KnowledgeBase:
        model = await session.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id, KnowledgeBase.deleted == 0
            )
        )
        if model is None:
            raise ClientException("知识库不存在")
        return model

    @staticmethod
    async def _require_document(session, doc_id: int) -> KnowledgeDocument:
        model = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == doc_id, KnowledgeDocument.deleted == 0
            )
        )
        if model is None:
            raise ClientException("文档不存在")
        return model

    @staticmethod
    def _base_vo(model: KnowledgeBase) -> KnowledgeBaseVO:
        return KnowledgeBaseVO.model_validate(model)

    @staticmethod
    def _document_vo(model: KnowledgeDocument) -> DocumentVO:
        return DocumentVO(
            id=model.id,
            kb_id=model.kb_id,
            doc_name=model.doc_name,
            enabled=bool(model.enabled),
            chunk_count=model.chunk_count,
            file_type=model.file_type,
            mime_type=model.mime_type,
            file_size=model.file_size,
            status=model.status,
            source_type=model.source_type,
            source_location=model.source_location,
            ingestion_spec=model.ingestion_spec,
        )

    @staticmethod
    def _chunk_vo(model: KnowledgeChunk) -> ChunkVO:
        return ChunkVO(
            id=str(model.id),
            doc_id=model.doc_id,
            chunk_index=model.chunk_index,
            content=model.content,
            enabled=bool(model.enabled),
        )


def _page(current: int, size: int) -> tuple[int, int]:
    return max(1, current), min(100, max(1, size))
