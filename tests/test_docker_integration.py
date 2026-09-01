"""本地 Docker 集成验收：PG 队列、M2 入库、pgvector 检索与 Redis。"""

import uuid
from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path

import asyncpg
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.chunk.service import ChunkingService
from app.core.ingest.kernel import ChunkEmbeddingService, DefaultIngestionKernel
from app.core.ingest.writer import PgChunkIndexWriter
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.registry import build_default_registry
from app.framework.async_task import AsyncTask
from app.framework.config import AuthSettings, DatasourceSettings, get_settings
from app.framework.db import init_schema
from app.framework.exceptions import BizException
from app.framework.result import ErrorCode, Results
from app.framework.task_queue import TaskQueue
from app.knowledge.models import (
    VECTOR_DIMENSION,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentChunkLog,
    KnowledgeVector,
)
from app.knowledge.tasks import KnowledgeTaskHandler
from app.rag.retrieval.metadata import ChunkMetadataResolver
from app.rag.retrieval.pgvector import PgVectorRetrievalEngine
from app.rag.rewrite.cache import QueryTermMappingCacheManager
from app.rag.rewrite.models import QueryTermMapping
from app.rag.rewrite.term_mapping import QueryTermMappingService
from app.system.auth.jwt import decode_token
from app.system.auth.password import hash_password
from app.system.auth.router import router as auth_router
from app.system.auth.service import AuthService
from app.system.user.models import User

pytestmark = pytest.mark.integration


class DeterministicEmbedding:
    """用正交轴模拟语义空间，确保测试稳定且不访问模型供应商。"""

    dimension = VECTOR_DIMENSION

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * VECTOR_DIMENSION
        if "青竹" in text:
            vector[0] = 1.0
        elif "Silver Pine" in text:
            vector[1] = 1.0
        else:
            vector[2] = 1.0
        return vector

    async def embed_batch(
        self, texts: list[str], model_id: str | None = None
    ) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed(self, text: str, model_id: str | None = None) -> list[float]:
        return self._vector(text)


@pytest.fixture
async def integration_engine() -> AsyncIterator[AsyncEngine]:
    settings = get_settings()
    source = settings.datasource
    database = f"ragent_it_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(
        host=source.host,
        port=source.port,
        database="postgres",
        user=source.username,
        password=source.password or None,
    )
    await admin.execute(f'CREATE DATABASE "{database}"')
    await admin.close()

    test_source = DatasourceSettings(**{**source.model_dump(), "database": database})
    engine = create_async_engine(test_source.url, pool_pre_ping=True)
    try:
        await init_schema(engine)
        yield engine
    finally:
        await engine.dispose()
        admin = await asyncpg.connect(
            host=source.host,
            port=source.port,
            database="postgres",
            user=source.username,
            password=source.password or None,
        )
        try:
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database,
            )
            await admin.execute(f'DROP DATABASE "{database}"')
        finally:
            await admin.close()


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    settings = get_settings().redis
    client = Redis(
        host=settings.host,
        port=settings.port,
        db=settings.database,
        password=settings.password or None,
        decode_responses=True,
    )
    try:
        yield client
    finally:
        await client.aclose()


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(
        b"BT /F1 14 Tf 72 720 Td "
        b"(PDF M2 acceptance phrase: Silver Pine 5319.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


async def test_redis_container_is_reachable(redis_client: Redis) -> None:
    assert await redis_client.ping() is True


async def test_query_mapping_db_and_cache(
    integration_engine: AsyncEngine, redis_client: Redis
) -> None:
    prefix = f"ragent:integration:mapping:{uuid.uuid4().hex}:"
    service = QueryTermMappingService(
        engine=integration_engine,
        cache=QueryTermMappingCacheManager(redis_client, prefix),
    )
    mapping_id = await service.create_mapping(
        QueryTermMapping("简称", "标准名称", priority=10), user_id=1
    )
    records, total = await service.list_mappings(1, 20)
    assert total == 1 and records[0].id == mapping_id
    assert await service.normalize_async("请查询简称") == "请查询标准名称"
    assert await redis_client.exists(f"{prefix}query-term:mappings") == 1
    await service.update_mapping(
        mapping_id, QueryTermMapping("简称", "新标准名称", priority=10), user_id=1
    )
    assert await service.normalize_async("简称") == "新标准名称"
    await service.delete_mapping(mapping_id)
    assert await service.load_mappings() == []


async def test_jwt_login_redis_session_and_logout(
    integration_engine: AsyncEngine, redis_client: Redis
) -> None:
    username = f"integration-{uuid.uuid4().hex}"
    password = "M1-integration-password"
    sessions = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="ADMIN",
        )
        session.add(user)
        await session.flush()
        user_id = user.id

    prefix = f"ragent:integration:{uuid.uuid4().hex}:"
    redis_settings = get_settings().redis.model_copy(update={"key_prefix": prefix})
    auth_settings = AuthSettings(
        enabled=True,
        jwt_secret="integration-secret-at-least-32-bytes",
        token_ttl_seconds=60,
    )
    service = AuthService(
        integration_engine, redis_client, auth_settings, redis_settings
    )
    api = FastAPI()
    api.state.auth_service = service

    @api.exception_handler(BizException)
    async def handle_biz_exception(
        _request: Request, exc: BizException
    ) -> JSONResponse:
        return JSONResponse(Results.error(exc.code, exc.message).model_dump(by_alias=True))

    api.include_router(auth_router)
    transport = ASGITransport(app=api, raise_app_exceptions=True)
    try:
        async with AsyncClient(transport=transport, base_url="http://integration") as client:
            missing = await client.get("/user/me")
            assert missing.json()["code"] == str(ErrorCode.UNAUTHORIZED)

            rejected = await client.post(
                "/auth/login", json={"username": username, "password": "wrong"}
            )
            assert rejected.json()["code"] != str(ErrorCode.SUCCESS)

            login = await client.post(
                "/auth/login", json={"username": username, "password": password}
            )
            payload = login.json()
            assert payload["code"] == str(ErrorCode.SUCCESS)
            assert payload["data"]["userId"] == user_id
            token = payload["data"]["token"]
            token_user_id, jti = decode_token(token, auth_settings.jwt_secret)
            assert token_user_id == user_id

            session_key = f"{prefix}auth:session:{jti}"
            assert await redis_client.exists(session_key) == 1
            assert await redis_client.ttl(session_key) > 0

            me = await client.get("/user/me", headers={"Authorization": token})
            assert me.json()["data"] == {
                "userId": user_id,
                "username": username,
                "role": "ADMIN",
                "avatar": None,
            }

            logout = await client.post(
                "/auth/logout", headers={"Authorization": token}
            )
            assert logout.json()["code"] == str(ErrorCode.SUCCESS)
            assert await redis_client.exists(session_key) == 0

            expired = await client.get("/user/me", headers={"Authorization": token})
            assert expired.json()["code"] == str(ErrorCode.UNAUTHORIZED)
    finally:
        keys = [key async for key in redis_client.scan_iter(f"{prefix}*")]
        if keys:
            await redis_client.delete(*keys)


@pytest.mark.parametrize(
    ("filename", "data", "question", "expected"),
    [
        (
            "acceptance.md",
            "# M2 验收\n\n测试暗号是青竹计划 8246。".encode(),
            "青竹计划的测试暗号是什么？",
            "青竹计划 8246",
        ),
        (
            "acceptance.pdf",
            _pdf_bytes(),
            "What is the Silver Pine PDF acceptance phrase?",
            "Silver Pine 5319",
        ),
    ],
)
async def test_worker_ingestion_and_pgvector_retrieval(
    integration_engine: AsyncEngine,
    tmp_path: Path,
    filename: str,
    data: bytes,
    question: str,
    expected: str,
) -> None:
    sessions = async_sessionmaker(integration_engine, expire_on_commit=False)
    file_path = tmp_path / filename
    file_path.write_bytes(data)
    collection = f"it_{uuid.uuid4().hex}"

    async with sessions.begin() as session:
        kb = KnowledgeBase(
            name=f"integration-{filename}",
            embedding_model="deterministic-embedding",
            collection_name=collection,
            created_by=0,
        )
        session.add(kb)
        await session.flush()
        document = KnowledgeDocument(
            kb_id=kb.id,
            doc_name=filename,
            file_url=str(file_path),
            file_type=file_path.suffix.lstrip("."),
            source_type="file",
            ingestion_spec={
                "parseProfile": "fast",
                "budget": {"maxChars": 256, "overlapChars": 32},
            },
            created_by=0,
        )
        session.add(document)
        await session.flush()
        log = KnowledgeDocumentChunkLog(doc_id=document.id, status="pending")
        session.add(log)
        await session.flush()
        task = await TaskQueue.enqueue(
            session,
            "chunk-document",
            f"doc:{document.id}",
            {"docId": document.id, "logId": log.id},
        )
        task_id = task.id
        doc_id = document.id

    embedding = DeterministicEmbedding()
    kernel = DefaultIngestionKernel(
        MimeTypeDetector(),
        build_default_registry(),
        ChunkingService(),
        ChunkEmbeddingService(embedding),
        PgChunkIndexWriter(integration_engine),
    )
    queue = TaskQueue(integration_engine)
    handler = KnowledgeTaskHandler(integration_engine, kernel)
    claimed = await queue.claim("integration-worker")
    assert claimed is not None
    assert claimed.id == task_id
    await handler.handle(claimed)
    await queue.succeed(claimed.id, "integration-worker")

    async with sessions() as session:
        stored_document = await session.get(KnowledgeDocument, doc_id)
        stored_task = await session.get(AsyncTask, task_id)
        chunks = (
            await session.scalars(
                select(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id)
            )
        ).all()
        dimensions = await session.scalar(
            select(func.min(func.vector_dims(KnowledgeVector.embedding))).where(
                KnowledgeVector.collection_name == collection
            )
        )

    assert stored_document is not None
    assert stored_document.status == "success"
    assert stored_document.chunk_count == len(chunks) >= 1
    assert stored_task is not None and stored_task.status == "success"
    assert dimensions == VECTOR_DIMENSION
    assert all(isinstance(chunk.id, uuid.UUID) for chunk in chunks)

    results = await PgVectorRetrievalEngine(
        integration_engine, embedding, top_k=1
    ).retrieve(question)
    assert results
    assert results[0].doc_id == doc_id
    assert expected in results[0].text
    assert results[0].score == pytest.approx(1.0)

    metadata = await ChunkMetadataResolver(integration_engine).resolve_chunks(
        (results[0].id,)
    )
    assert metadata[results[0].id].doc_id == doc_id
    assert metadata[results[0].id].doc_name == stored_document.doc_name
    chunk_indexes = {chunk.id: chunk.chunk_index for chunk in chunks}
    assert metadata[results[0].id].chunk_index == chunk_indexes[results[0].id]

    fallback_results = await PgVectorRetrievalEngine(
        integration_engine, embedding, top_k=1
    ).retrieve(
        question,
        collections=("missing-collection",),
        supplement_ratio=0.25,
    )
    assert fallback_results
    assert fallback_results[0].doc_id == doc_id
    assert expected in fallback_results[0].text
