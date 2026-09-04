"""本地 Docker 集成验收：PG 队列、M2 入库、pgvector 检索与 Redis。"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import asyncpg
import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.admin.dashboard import NO_DOCUMENT_ANSWER, DashboardService
from app.core.chunk.service import ChunkingService
from app.core.ingest.kernel import ChunkEmbeddingService, DefaultIngestionKernel
from app.core.ingest.writer import PgChunkIndexWriter
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.registry import build_default_registry
from app.framework.async_task import AsyncTask
from app.framework.chat_types import ChatRole
from app.framework.config import AuthSettings, DatasourceSettings, get_settings
from app.framework.db import init_schema
from app.framework.exceptions import BizException
from app.framework.result import ErrorCode, Results
from app.framework.sse import RecommendedQuestionsPayload, RecommendedQuestionStatus
from app.framework.task_queue import TaskQueue
from app.ingestion.engine.engine import IngestionEngine
from app.ingestion.schemas import DocumentSource, NodeConfig, PipelineCreate, TaskCreate
from app.ingestion.service import IngestionService
from app.knowledge.models import (
    VECTOR_DIMENSION,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentChunkLog,
    KnowledgeVector,
)
from app.knowledge.tasks import KnowledgeTaskHandler
from app.rag.conversation import ConversationService
from app.rag.feedback import MessageFeedbackService, MessageFeedbackTaskHandler
from app.rag.memory.store import ConversationMemoryStore
from app.rag.models import (
    Conversation,
    ConversationSummary,
    Message,
    MessageFeedback,
    RagTraceRun,
)
from app.rag.recommend import RecommendedQuestionService
from app.rag.retrieval.metadata import ChunkMetadataResolver
from app.rag.retrieval.pgvector import PgVectorRetrievalEngine
from app.rag.rewrite.cache import QueryTermMappingCacheManager
from app.rag.rewrite.models import QueryTermMapping
from app.rag.rewrite.term_mapping import QueryTermMappingService
from app.system.audit.router import router as audit_router
from app.system.audit.service import AuditQueryService, AuditRecordService
from app.system.auth.deps import require_admin, require_user
from app.system.auth.jwt import decode_token
from app.system.auth.models import LoginUser
from app.system.auth.password import hash_password
from app.system.auth.router import router as auth_router
from app.system.auth.service import AuthService
from app.system.user.models import User
from app.system.user.router import router as user_router
from app.system.user.service import UserService

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


class UnusedPipelineLLM:
    async def chat(self, *args, **kwargs) -> str:
        raise AssertionError("this pipeline does not include an LLM node")


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


async def test_pipeline_crud_and_synchronous_file_run(
    integration_engine: AsyncEngine,
) -> None:
    http = httpx.AsyncClient()

    async def unused_writer(_context) -> None:
        raise AssertionError("this pipeline does not include an indexer node")

    runner = IngestionEngine(
        MimeTypeDetector(),
        build_default_registry(),
        ChunkingService(),
        ChunkEmbeddingService(DeterministicEmbedding()),
        UnusedPipelineLLM(),
        http,
        unused_writer,
    )
    service = IngestionService(
        integration_engine,
        runner,
        embedding_model="deterministic-embedding",
        dimension=VECTOR_DIMENSION,
    )
    try:
        pipeline_id = int(
            await service.create_pipeline(
                PipelineCreate(
                    name="Markdown parser acceptance",
                    description="integration",
                    nodes=[
                        NodeConfig(
                            nodeId="fetch",
                            nodeType="fetcher",
                            nextNodeId="parse",
                        ),
                        NodeConfig(nodeId="parse", nodeType="parser"),
                    ],
                ),
                user_id=7,
            )
        )
        result = await service.run_task(
            TaskCreate(
                pipelineId=pipeline_id,
                source=DocumentSource(type="file", fileName="acceptance.md"),
            ),
            user_id=7,
            raw_bytes="# Pipeline 验收\n\n内容已进入解析节点。".encode(),
        )
        assert result["status"] == "completed"
        task = await service.get_task(int(result["taskId"]))
        nodes = await service.task_nodes(task["id"])
        assert task["status"] == "completed"
        assert [node["nodeType"] for node in nodes] == ["fetcher", "parser"]
        assert nodes[1]["output"]["blockCount"] == 2
        assert all(isinstance(node["createTime"], int) for node in nodes)
        page = await service.page_pipelines(1, 20, "Markdown")
        assert page["total"] == 1
        assert page["records"][0]["nodes"][0]["nextNodeId"] == "parse"
    finally:
        await http.aclose()


async def test_redis_container_is_reachable(redis_client: Redis) -> None:
    assert await redis_client.ping() is True


async def test_dashboard_aggregates_real_postgres_data(
    integration_engine: AsyncEngine,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    conversation_id = uuid.uuid4()
    sessions = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add(
            User(
                username=f"dashboard-{uuid.uuid4().hex}",
                password_hash="not-used",
                role="USER",
                create_time=now - timedelta(hours=1),
            )
        )
        session.add(
            Conversation(
                conversation_id=conversation_id,
                user_id=71,
                create_time=now - timedelta(hours=1),
            )
        )
        session.add_all(
            [
                Message(
                    conversation_id=conversation_id,
                    user_id=71,
                    role="user",
                    content="测试 Dashboard",
                    create_time=now - timedelta(minutes=50),
                ),
                Message(
                    conversation_id=conversation_id,
                    user_id=71,
                    role="assistant",
                    content=NO_DOCUMENT_ANSWER,
                    create_time=now - timedelta(minutes=49),
                ),
            ]
        )
        for status, duration, offset in (
            ("SUCCESS", 1_000, 40),
            ("SUCCESS", 3_000, 30),
            ("ERROR", 500, 20),
            ("RUNNING", None, 10),
        ):
            session.add(
                RagTraceRun(
                    trace_id=uuid.uuid4(),
                    trace_name="dashboard-integration",
                    entry_point="integration",
                    conversation_id=conversation_id,
                    task_id=uuid.uuid4(),
                    user_id=71,
                    status=status,
                    start_time=now - timedelta(minutes=offset),
                    duration_ms=duration,
                )
            )

    dashboard = DashboardService(integration_engine)
    overview = await dashboard.overview("24h")
    performance = await dashboard.performance("24h")
    trends = await dashboard.trends("quality", "24h", "hour")

    assert overview["window"] == "24h"
    assert overview["kpis"]["totalUsers"]["value"] == 1
    assert overview["kpis"]["activeUsers"]["value"] == 1
    assert overview["kpis"]["sessions24h"]["value"] == 1
    assert overview["kpis"]["messages24h"]["value"] == 2
    assert performance == {
        "window": "24h",
        "avgLatencyMs": 2_000,
        "p95LatencyMs": 3_000,
        "successRate": 66.7,
        "errorRate": 33.3,
        "noDocRate": 100.0,
        "slowRate": 0.0,
    }
    assert trends["metric"] == "quality"
    assert [series["name"] for series in trends["series"]] == ["错误率", "无知识率"]
    assert max(point["value"] for point in trends["series"][0]["points"]) == 33.3
    assert max(point["value"] for point in trends["series"][1]["points"]) == 100.0


async def test_conversation_crud_isolated_by_user_and_soft_deletes_children(
    integration_engine: AsyncEngine,
) -> None:
    conversation_id = uuid.uuid4()
    other_conversation_id = uuid.uuid4()
    memory = ConversationMemoryStore(integration_engine)
    service = ConversationService(integration_engine)

    await memory.get_or_create_conversation(conversation_id, user_id=11)
    user_message_id = await memory.append_message(
        conversation_id=conversation_id,
        user_id=11,
        role=ChatRole.USER,
        content="如何配置本地检索？",
    )
    assistant_message_id = await memory.append_message(
        conversation_id=conversation_id,
        user_id=11,
        role=ChatRole.ASSISTANT,
        content="请参考配置文档 [1](#cite-1)。",
        thinking_content="检索配置材料",
        thinking_duration=2,
        sources=[{"index": 1, "docId": "7", "docName": "配置文档.md"}],
        reply_to_message_id=user_message_id,
    )
    await memory.get_or_create_conversation(other_conversation_id, user_id=22)
    await memory.append_message(
        conversation_id=other_conversation_id,
        user_id=22,
        role=ChatRole.USER,
        content="其他用户的问题",
    )

    sessions = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add_all(
            [
                ConversationSummary(
                    conversation_id=conversation_id,
                    user_id=11,
                    last_message_id=assistant_message_id,
                    content="用户正在配置本地检索。",
                ),
                MessageFeedback(
                    message_id=assistant_message_id,
                    user_id=11,
                    conversation_id=conversation_id,
                    vote=1,
                ),
            ]
        )

    conversations = await service.list_conversations(user_id=11)
    assert len(conversations) == 1
    assert conversations[0]["title"] == "如何配置本地检索？"
    assert isinstance(conversations[0]["lastTime"], int)
    other_conversations = await service.list_conversations(user_id=22)
    assert len(other_conversations) == 1
    assert other_conversations[0]["title"] == "其他用户的问题"

    messages = await service.list_messages(str(conversation_id), user_id=11)
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["vote"] is None
    assert messages[1]["vote"] == 1
    assert messages[1]["content"] == "请参考配置文档 [1](#cite-1)。"
    assert await service.list_messages(str(conversation_id), user_id=22) == []

    await service.rename(str(conversation_id), user_id=11, title="本地检索配置")
    assert (await service.list_conversations(user_id=11))[0]["title"] == "本地检索配置"

    await service.delete(str(conversation_id), user_id=11)
    assert await service.list_conversations(user_id=11) == []
    assert await service.list_messages(str(conversation_id), user_id=11) == []
    async with sessions() as session:
        conversation_deleted = await session.scalar(
            select(Conversation.deleted).where(Conversation.conversation_id == conversation_id)
        )
        child_deleted = (
            await session.scalars(
                select(Message.deleted).where(Message.conversation_id == conversation_id)
            )
        ).all()
        summary_deleted = await session.scalar(
            select(ConversationSummary.deleted).where(
                ConversationSummary.conversation_id == conversation_id
            )
        )
        feedback_deleted = await session.scalar(
            select(MessageFeedback.deleted).where(
                MessageFeedback.conversation_id == conversation_id
            )
        )
    assert conversation_deleted == 1
    assert child_deleted == [1, 1]
    assert summary_deleted == 1
    assert feedback_deleted == 1

    with pytest.raises(ValueError, match="deleted"):
        await memory.append_message(
            conversation_id=conversation_id,
            user_id=11,
            role=ChatRole.USER,
            content="删除后不可继续写入",
        )


async def test_feedback_queue_latest_event_and_recommendation_cache(
    integration_engine: AsyncEngine,
) -> None:
    conversation_id = uuid.uuid4()
    memory = ConversationMemoryStore(integration_engine)
    await memory.get_or_create_conversation(conversation_id, user_id=11)
    user_message_id = await memory.append_message(
        conversation_id=conversation_id,
        user_id=11,
        role=ChatRole.USER,
        content="如何继续配置？",
    )
    assistant_message_id = await memory.append_message(
        conversation_id=conversation_id,
        user_id=11,
        role=ChatRole.ASSISTANT,
        content="先完成基础配置 [1](#cite-1)。",
        retrieved_chunks=[{"docName": "配置手册", "text": "基础配置步骤"}],
        reply_to_message_id=user_message_id,
    )
    feedback = MessageFeedbackService(integration_engine)
    feedback_handler = MessageFeedbackTaskHandler(integration_engine)
    queue = TaskQueue(integration_engine)

    await feedback.submit(str(assistant_message_id), 11, 1)
    first = await queue.claim("feedback-worker")
    assert first is not None
    await feedback.remove(str(assistant_message_id), 11)
    await feedback_handler.handle(first)
    assert await queue.succeed(first.id, "feedback-worker", first.event_id) is False

    latest = await queue.claim("feedback-worker")
    assert latest is not None and latest.event_id != first.event_id
    await feedback_handler.handle(latest)
    assert await queue.succeed(latest.id, "feedback-worker", latest.event_id) is True
    messages = await ConversationService(integration_engine).list_messages(
        str(conversation_id), 11
    )
    assert messages[-1]["vote"] is None

    class Generator:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, question, answer, grounding_chunks):
            self.calls += 1
            assert question == "如何继续配置？"
            assert "#cite-1" in answer
            assert grounding_chunks == [
                {"docName": "配置手册", "text": "基础配置步骤"}
            ]
            return RecommendedQuestionsPayload(
                status=RecommendedQuestionStatus.SUCCESS,
                questions=["下一项配置是什么？"],
            )

    generator = Generator()
    recommendations = RecommendedQuestionService(integration_engine, generator)
    generated = await recommendations.generate(str(assistant_message_id), 11)
    cached = await recommendations.generate(str(assistant_message_id), 11)

    assert generated.questions == ["下一项配置是什么？"]
    assert cached.questions == generated.questions
    assert generator.calls == 1


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


async def test_user_management_writes_audit_and_invalidates_sessions(
    integration_engine: AsyncEngine, redis_client: Redis
) -> None:
    prefix = f"ragent:integration:user:{uuid.uuid4().hex}:"
    settings = get_settings()
    redis_settings = settings.redis.model_copy(update={"key_prefix": prefix})
    auth = AuthService(integration_engine, redis_client, settings.auth, redis_settings)
    users = UserService(integration_engine, auth)
    api = FastAPI()
    api.state.user_service = users
    api.state.audit_record_service = AuditRecordService(integration_engine)
    api.state.audit_query_service = AuditQueryService(integration_engine)

    async def admin_user(request: Request) -> LoginUser:
        user = LoginUser(userId=999, username="integration-admin", role="ADMIN")
        request.state.current_user = user
        return user

    current_user_id = 0

    async def current_user(request: Request) -> LoginUser:
        user = LoginUser(userId=current_user_id, username="managed-user", role="USER")
        request.state.current_user = user
        return user

    api.dependency_overrides[require_admin] = admin_user
    api.dependency_overrides[require_user] = current_user
    api.include_router(user_router)
    api.include_router(audit_router)
    transport = ASGITransport(app=api, raise_app_exceptions=True)
    try:
        async with AsyncClient(transport=transport, base_url="http://integration") as client:
            created = await client.post(
                "/users",
                json={"username": "managed-user", "password": "initial-secret", "role": "user"},
            )
            assert created.json()["code"] == str(ErrorCode.SUCCESS)
            current_user_id = int(created.json()["data"])

            session_key = f"{prefix}auth:session:test-jti"
            index_key = f"{prefix}auth:user-sessions:{current_user_id}"
            await redis_client.set(session_key, "active")
            await redis_client.sadd(index_key, "test-jti")
            updated = await client.put(
                f"/users/{current_user_id}",
                json={"password": "updated-secret", "role": "admin"},
            )
            assert updated.json()["code"] == str(ErrorCode.SUCCESS)
            assert await redis_client.exists(session_key) == 0
            assert await redis_client.exists(index_key) == 0

            changed = await client.put(
                "/user/password",
                json={"currentPassword": "updated-secret", "newPassword": "final-secret"},
            )
            assert changed.json()["code"] == str(ErrorCode.SUCCESS)

            listing = await client.get("/users", params={"keyword": "managed"})
            record = listing.json()["data"]["records"][0]
            assert record["role"] == "admin"
            assert isinstance(record["createTime"], int)

            logs = await client.get("/biz-change-logs", params={"bizType": "USER"})
            payload = logs.json()["data"]
            assert payload["total"] == 3
            assert {item["actionDesc"] for item in payload["records"]} == {
                "创建用户：managed-user",
                "更新用户",
                "修改本人密码",
            }
            assert "passwordHash" not in str(payload["records"])

            deleted = await client.delete(f"/users/{current_user_id}")
            assert deleted.json()["code"] == str(ErrorCode.SUCCESS)
            assert (await users.page(1, 20))["total"] == 0
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
