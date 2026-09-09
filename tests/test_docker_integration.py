"""本地 Docker 集成验收：PG 队列、M2 入库、pgvector 检索与 Redis。"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.admin.agents.schemas import AgentProfileWrite
from app.admin.agents.service import AgentAdminService
from app.admin.dashboard import NO_DOCUMENT_ANSWER, DashboardService
from app.admin.mcp.service import McpAdminService
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
from app.framework.stream_tasks import RedisStreamTaskManager
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
from app.rag.intent.cache import IntentTreeCacheManager
from app.rag.intent.orm import IntentNodeRecord
from app.rag.intent.service import IntentTreeService
from app.rag.mcp.executor import McpClientToolExecutor
from app.rag.mcp.models import McpServerSnapshot, ToolDefinition
from app.rag.mcp.registry import McpToolRegistry
from app.rag.memory.store import ConversationMemoryStore
from app.rag.models import (
    Conversation,
    ConversationSummary,
    Message,
    MessageFeedback,
    RagTraceRun,
)
from app.rag.prompt.cache import AgentPromptCache
from app.rag.prompt.resolver import AgentPromptResolver
from app.rag.prompt.slots import AgentPromptSlot
from app.rag.ratelimit import FairDistributedRateLimiter, PermitExpirableSemaphore
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


async def test_redis_stream_cancel_broadcasts_between_instances(
    redis_client: Redis,
) -> None:
    prefix = f"ragent:test:stream:{uuid.uuid4()}:"
    source = RedisStreamTaskManager(redis_client, key_prefix=prefix)
    target = RedisStreamTaskManager(redis_client, key_prefix=prefix)
    cancelled = asyncio.Event()
    calls: list[str] = []

    async def action() -> None:
        calls.append("action")

    async def finalizer() -> None:
        calls.append("finalizer")
        cancelled.set()

    await source.start()
    await target.start()
    try:
        await asyncio.sleep(0.05)
        await target.register("task-remote", 7, finalizer)
        await target.bind_cancel("task-remote", action)

        assert await source.cancel("task-remote", 8) is False
        assert await source.cancel("task-remote", 7) is True
        await asyncio.wait_for(cancelled.wait(), timeout=2)

        assert calls == ["action", "finalizer"]
        assert target.is_cancelled("task-remote") is True
        assert await redis_client.get(f"{prefix}stream:cancel:task-remote") == "7"
    finally:
        await source.close()
        await target.close()
        await redis_client.delete(
            f"{prefix}stream:owner:task-remote",
            f"{prefix}stream:cancel:task-remote",
        )


async def test_redis_expirable_semaphore_recovers_and_releases_idempotently(
    redis_client: Redis,
) -> None:
    name = f"ragent:test:semaphore:{uuid.uuid4()}"
    semaphore = PermitExpirableSemaphore(redis_client, name)
    try:
        assert await semaphore.try_set_permits(1) is True
        assert await semaphore.try_set_permits(9) is False
        first = await semaphore.try_acquire(0.05)
        assert first is not None
        assert await semaphore.available_permits() == 0
        assert await semaphore.try_release(first) is True
        assert await semaphore.try_release(first) is False
        assert await semaphore.available_permits() == 1

        expired = await semaphore.try_acquire(0.05)
        assert expired is not None
        await asyncio.sleep(0.07)
        assert await semaphore.available_permits() == 1
        assert await semaphore.try_release(expired) is False
    finally:
        keys = [key async for key in redis_client.scan_iter(f"{name}*")]
        if keys:
            await redis_client.delete(*keys)


async def test_two_rate_limiter_instances_preserve_fifo_and_global_capacity(
    redis_client: Redis,
) -> None:
    name = f"ragent:test:fair:{uuid.uuid4()}"
    first = FairDistributedRateLimiter(
        redis_client,
        name=name,
        max_concurrent=1,
        max_wait_seconds=3,
        lease_seconds=5,
        poll_interval_ms=10,
    )
    second = FairDistributedRateLimiter(
        redis_client,
        name=name,
        max_concurrent=1,
        max_wait_seconds=3,
        lease_seconds=5,
        poll_interval_ms=10,
    )
    await first.start()
    await second.start()
    holder = await first.acquire("holder")
    assert holder is not None
    grant_order: list[int] = []

    async def wait_for_permit(index: int) -> None:
        limiter = first if index % 2 == 0 else second
        permit = await limiter.acquire(f"request-{index}")
        assert permit is not None
        grant_order.append(index)
        await asyncio.sleep(0.002)
        assert await limiter.release(permit) is True

    tasks: list[asyncio.Task[None]] = []
    try:
        for index in range(40):
            tasks.append(asyncio.create_task(wait_for_permit(index)))
            expected = index + 1
            for _ in range(100):
                if await redis_client.zcard(f"{name}:queue") == expected:
                    break
                await asyncio.sleep(0.002)
            else:
                pytest.fail(f"request {index} did not enter the distributed queue")

        assert await first.release(holder) is True
        await asyncio.gather(*tasks)
        assert grant_order == list(range(40))
        assert await redis_client.get(f"{name}:semaphore") == "1"
        assert await redis_client.zcard(f"{name}:semaphore:permits") == 0
        assert await redis_client.zcard(f"{name}:queue") == 0
    finally:
        for task in tasks:
            task.cancel()
        await first.close()
        await second.close()
        keys = [key async for key in redis_client.scan_iter(f"{name}*")]
        if keys:
            await redis_client.delete(*keys)


async def test_two_rate_limiter_instances_never_exceed_global_capacity(
    redis_client: Redis,
) -> None:
    name = f"ragent:test:capacity:{uuid.uuid4()}"
    limiters = [
        FairDistributedRateLimiter(
            redis_client,
            name=name,
            max_concurrent=5,
            max_wait_seconds=3,
            lease_seconds=5,
            poll_interval_ms=10,
        )
        for _ in range(2)
    ]
    for limiter in limiters:
        await limiter.start()
    active = 0
    peak = 0
    state_lock = asyncio.Lock()

    async def execute(index: int) -> None:
        nonlocal active, peak
        limiter = limiters[index % len(limiters)]
        permit = await limiter.acquire(f"request-{index}")
        assert permit is not None
        async with state_lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.005)
        async with state_lock:
            active -= 1
        assert await limiter.release(permit) is True

    try:
        await asyncio.gather(*(execute(index) for index in range(200)))
        assert peak == 5
        assert active == 0
        assert await redis_client.get(f"{name}:semaphore") == "5"
        assert await redis_client.zcard(f"{name}:semaphore:permits") == 0
    finally:
        for limiter in limiters:
            await limiter.close()
        keys = [key async for key in redis_client.scan_iter(f"{name}*")]
        if keys:
            await redis_client.delete(*keys)


async def test_pg_queue_multiple_workers_claim_each_task_once(
    integration_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        for index in range(60):
            await TaskQueue.enqueue(
                session,
                "capacity-probe",
                f"probe:{index}",
                {"index": index},
            )

    queues = [TaskQueue(integration_engine) for _ in range(8)]

    async def drain(worker_index: int) -> list[int]:
        claimed_ids: list[int] = []
        while task := await queues[worker_index].claim(f"worker-{worker_index}"):
            claimed_ids.append(task.id)
            await asyncio.sleep(0)
        return claimed_ids

    claimed_by_worker = await asyncio.gather(*(drain(index) for index in range(8)))
    claimed_ids = [task_id for group in claimed_by_worker for task_id in group]

    assert len(claimed_ids) == 60
    assert len(set(claimed_ids)) == 60
    assert sum(bool(group) for group in claimed_by_worker) > 1
    async with sessions() as session:
        owners = (
            await session.scalars(
                select(AsyncTask.owner).where(AsyncTask.status == "running")
            )
        ).all()
    assert len(owners) == 60
    assert len(set(owners)) > 1


async def test_pg_queue_recovery_updates_task_document_and_log_atomically(
    integration_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        kb = KnowledgeBase(
            name="recovery-test",
            embedding_model="deterministic-embedding",
            collection_name=f"recovery_{uuid.uuid4().hex}",
            created_by=0,
        )
        session.add(kb)
        await session.flush()
        document = KnowledgeDocument(
            kb_id=kb.id,
            doc_name="recover.md",
            file_type="md",
            source_type="file",
            status="pending",
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
            max_retries=1,
        )
        task_id, doc_id, log_id = task.id, document.id, log.id

    handler = KnowledgeTaskHandler(integration_engine, object())  # type: ignore[arg-type]
    first_queue = TaskQueue(integration_engine)
    second_queue = TaskQueue(integration_engine)

    async def failing_claim_transition(session, claimed) -> None:
        await handler.mark_claimed(session, claimed)
        raise RuntimeError("simulated crash before claim commit")

    with pytest.raises(RuntimeError, match="simulated crash"):
        await first_queue.claim("failed-owner", failing_claim_transition)
    async with sessions() as session:
        rolled_back_task = await session.get(AsyncTask, task_id)
        rolled_back_document = await session.get(KnowledgeDocument, doc_id)
        rolled_back_log = await session.get(KnowledgeDocumentChunkLog, log_id)
    assert rolled_back_task is not None and rolled_back_task.status == "pending"
    assert rolled_back_document is not None and rolled_back_document.status == "pending"
    assert rolled_back_log is not None and rolled_back_log.status == "pending"

    claimed = await first_queue.claim("dead-worker", handler.mark_claimed)
    assert claimed is not None and claimed.id == task_id
    async with sessions.begin() as session:
        await session.execute(
            update(AsyncTask)
            .where(AsyncTask.id == task_id)
            .values(lease_until=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1))
        )

    recovered = await asyncio.gather(
        first_queue.recover_stuck(handler.mark_retry_or_failed_in_session),
        second_queue.recover_stuck(handler.mark_retry_or_failed_in_session),
    )
    assert sum(len(group) for group in recovered) == 1
    assert [terminal for group in recovered for _, terminal in group] == [False]
    async with sessions() as session:
        pending_task = await session.get(AsyncTask, task_id)
        pending_document = await session.get(KnowledgeDocument, doc_id)
        pending_log = await session.get(KnowledgeDocumentChunkLog, log_id)
    assert pending_task is not None and pending_task.status == "pending"
    assert pending_task.retry_count == 1 and pending_task.owner is None
    assert pending_document is not None and pending_document.status == "pending"
    assert pending_log is not None and pending_log.status == "pending"

    reclaimed = await second_queue.claim("replacement-worker", handler.mark_claimed)
    assert reclaimed is not None and reclaimed.id == task_id
    async with sessions.begin() as session:
        await session.execute(
            update(AsyncTask)
            .where(AsyncTask.id == task_id)
            .values(lease_until=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1))
        )
    terminal_recovery = await asyncio.gather(
        first_queue.recover_stuck(handler.mark_retry_or_failed_in_session),
        second_queue.recover_stuck(handler.mark_retry_or_failed_in_session),
    )
    assert sum(len(group) for group in terminal_recovery) == 1
    assert [terminal for group in terminal_recovery for _, terminal in group] == [True]
    async with sessions() as session:
        failed_task = await session.get(AsyncTask, task_id)
        failed_document = await session.get(KnowledgeDocument, doc_id)
        failed_log = await session.get(KnowledgeDocumentChunkLog, log_id)
    assert failed_task is not None and failed_task.status == "failed"
    assert failed_task.retry_count == 2 and failed_task.owner is None
    assert failed_document is not None and failed_document.status == "failed"
    assert failed_log is not None and failed_log.status == "failed"
    assert failed_log.end_time is not None


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


async def test_agent_profiles_prompt_fallback_and_cache_invalidation(
    integration_engine: AsyncEngine, redis_client: Redis
) -> None:
    prefix = f"ragent:integration:agents:{uuid.uuid4().hex}:"
    cache = AgentPromptCache(redis_client, prefix)
    service = AgentAdminService(integration_engine, cache, "workflow")
    resolver = AgentPromptResolver(integration_engine, cache)
    try:
        await service.ensure_builtin()
        listing = await service.list_profiles()
        builtin = listing["agents"][0]
        assert builtin["builtin"] is True
        assert builtin["active"] is True
        assert listing["effectiveSlotTotal"] == 6

        agent_id = int(
            await service.create(
                AgentProfileWrite(
                    name="集成测试支持",
                    description="验证槽位覆盖和回落",
                    avatar="briefcase",
                ),
                user_id=1,
            )
        )
        custom_prompt = "仅回答集成测试范围内的问题。"
        await service.save_prompt(
            agent_id,
            AgentPromptSlot.SYSTEM_CHAT,
            custom_prompt,
            user_id=1,
        )
        await service.activate(agent_id, user_id=1)
        assert await resolver.resolve(AgentPromptSlot.SYSTEM_CHAT) == custom_prompt
        assert await redis_client.exists(f"{prefix}agent:resolved-prompts") == 1

        await service.save_prompt(
            agent_id, AgentPromptSlot.SYSTEM_CHAT, "  ", user_id=1
        )
        assert await redis_client.exists(f"{prefix}agent:resolved-prompts") == 0
        assert "友好、简洁" in await resolver.resolve(AgentPromptSlot.SYSTEM_CHAT)

        config = await service.prompts(agent_id)
        system_slot = next(
            item for item in config["slots"] if item["slotKey"] == "SYSTEM_CHAT"
        )
        assert system_slot["content"] == ""
        assert system_slot["effective"] is True

        await service.activate(int(builtin["id"]), user_id=1)
        await service.delete(agent_id)
        assert len((await service.list_profiles())["agents"]) == 1
    finally:
        keys = [key async for key in redis_client.scan_iter(f"{prefix}*")]
        if keys:
            await redis_client.delete(*keys)


async def test_mcp_switches_and_debug_state_persist(
    integration_engine: AsyncEngine,
) -> None:
    class FakeMcpClient:
        async def call_tool(self, name, parameters, **kwargs):
            assert name == "weather_query"
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="weather result")],
                structured_content={"city": parameters["city"], "weather": "晴"},
                is_error=False,
            )

    class FakeMcpManager:
        def __init__(self) -> None:
            self.snapshot = McpServerSnapshot(
                name="internal",
                url="http://127.0.0.1:9099",
                status="online",
                server_name="ragent-mcp-server",
                server_version="1.0.0",
                tool_count=1,
                discovered_at=1,
            )

        def snapshots(self) -> list[McpServerSnapshot]:
            return [self.snapshot]

        async def refresh(self, server_name: str) -> McpServerSnapshot:
            assert server_name == "internal"
            return self.snapshot

    definition = ToolDefinition(
        qualified_key="internal:weather_query",
        server_name="internal",
        name="weather_query",
        description="天气查询",
        input_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    executor = McpClientToolExecutor(FakeMcpClient(), definition, 5)
    manager = FakeMcpManager()
    registry = McpToolRegistry()
    registry.replace_server("internal", [executor])
    service = McpAdminService(integration_engine, manager, registry)

    await service.set_server_enabled("internal", False, user_id=7)
    assert registry.get_executor(definition.qualified_key) is None
    await service.set_server_enabled("internal", True, user_id=7)
    await service.set_tool_enabled(definition.qualified_key, False, user_id=7)
    assert registry.get_executor(definition.qualified_key) is None
    await service.set_tool_enabled(definition.qualified_key, True, user_id=7)
    debug = await service.debug(definition.qualified_key, {"city": "北京"})
    assert debug["success"] is True
    assert debug["structuredContent"] == {"city": "北京", "weather": "晴"}

    await service.set_server_enabled("internal", False, user_id=7)
    await service.set_tool_enabled(definition.qualified_key, False, user_id=7)
    restarted_registry = McpToolRegistry()
    restarted_registry.replace_server("internal", [executor])
    restarted_service = McpAdminService(
        integration_engine, manager, restarted_registry
    )
    await restarted_service.apply_persisted_states()
    assert restarted_registry.server_enabled("internal") is False
    assert restarted_registry.get_executor(definition.qualified_key) is None


async def test_intent_tree_crud_persists_audit_fields(
    integration_engine: AsyncEngine, redis_client: Redis
) -> None:
    prefix = f"ragent:integration:intent:{uuid.uuid4().hex}:"
    service = IntentTreeService(
        integration_engine, IntentTreeCacheManager(redis_client, prefix)
    )
    node_id = await service.create(
        {
            "intent_code": "integration-intent",
            "name": "集成意图",
            "level": 0,
            "kind": 0,
            "examples": ["集成测试问题"],
            "collection_names": ["integration_collection"],
            "enabled": True,
        },
        user_id=7,
    )
    await service.update(
        node_id,
        {
            "intent_code": "integration-intent",
            "name": "更新后的集成意图",
            "level": 0,
            "kind": 0,
            "examples": ["更新后的问题"],
            "collection_names": ["integration_collection"],
            "enabled": True,
        },
        user_id=8,
    )

    sessions = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with sessions() as session:
        row = await session.get(IntentNodeRecord, node_id)
        assert row is not None
        assert row.name == "更新后的集成意图"
        assert row.create_by == 7
        assert row.update_by == 8

    await service.delete(node_id)
    assert await service.list_tree() == []
    keys = [key async for key in redis_client.scan_iter(f"{prefix}*")]
    if keys:
        await redis_client.delete(*keys)


async def test_redis_container_is_reachable(redis_client: Redis) -> None:
    assert await redis_client.ping() is True


async def test_dashboard_aggregates_real_postgres_data(
    integration_engine: AsyncEngine,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    trace_bucket = (now - timedelta(hours=2)).replace(
        minute=30, second=0, microsecond=0
    )
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
                    start_time=trace_bucket + timedelta(seconds=offset),
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
