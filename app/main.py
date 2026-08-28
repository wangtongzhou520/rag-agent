"""FastAPI 装配入口：lifespan 管理基础设施资源，全局异常映射为 Result JSON。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
import structlog.contextvars
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.framework.config import Settings, get_settings
from app.framework.db import init_schema
from app.framework.exceptions import BizException
from app.framework.ids import new_uuid7
from app.framework.logging import get_logger, init_logging
from app.framework.result import ErrorCode, Results
from app.framework.trace_ctx import reset_request_id, set_request_id
from app.model_runtime.factory import build_model_runtime

# 导入即注册 t_* 表元数据，供 init_schema 自动建表
import app.framework.async_task  # noqa: F401,E402
import app.knowledge.models  # noqa: F401,E402
import app.rag.models  # noqa: F401,E402
from app.rag.memory.service import ConversationMemoryService
from app.rag.memory.store import ConversationMemoryStore
from app.rag.pipeline.stream_chat import EmptyRetrievalEngine, StreamChatPipeline
from app.rag.router import router as rag_router
from app.rag.service import RAGChatService

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """管理应用级资源的启动与关闭生命周期。

    ``@asynccontextmanager`` 把 ``yield`` 前后的代码转换为异步上下文管理器：
    FastAPI 在开始接收请求前执行 ``yield`` 之前的初始化，在应用关闭后执行
    ``yield`` 之后的清理。这里集中持有数据库引擎、Redis 客户端和 HTTP 客户端，
    确保无论应用正常退出还是测试 lifespan 结束，连接池都会被释放。
    """
    settings: Settings = get_settings()
    init_logging(settings.logging.level)

    # 基础设施资源：只创建与关闭，连通性自检随各里程碑补
    engine: AsyncEngine = create_async_engine(settings.datasource.url, pool_pre_ping=True)
    if settings.datasource.auto_ddl:
        await init_schema(engine)
    redis_client = aioredis.Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.database,
        password=settings.redis.password or None,
        decode_responses=True,
    )
    http_client = httpx.AsyncClient()

    # 模型运行时与问答链路装配（docs/04 §2 三层结构、docs/01 §11 模块落点）
    model_runtime = build_model_runtime(settings)
    memory_service = ConversationMemoryService(
        ConversationMemoryStore(engine),
        history_keep_turns=settings.rag.memory.history_keep_turns,
    )
    pipeline = StreamChatPipeline(
        memory_service, model_runtime.llm, EmptyRetrievalEngine()
    )

    app.state.engine = engine
    app.state.redis = redis_client
    app.state.http = http_client
    app.state.model_runtime = model_runtime
    app.state.rag_chat_service = RAGChatService(memory_service, pipeline, settings)
    logger.info("app started", root_path=settings.server.root_path)

    try:
        yield
    finally:
        await engine.dispose()
        await redis_client.aclose()
        await http_client.aclose()
        await model_runtime.http.aclose()
        logger.info("app stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ragent", root_path=settings.server.root_path, lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "").strip()
        request_id = incoming if 0 < len(incoming) <= 128 else new_uuid7()
        token = set_request_id(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
            reset_request_id(token)

    @app.exception_handler(BizException)
    async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
        return JSONResponse(Results.error(exc.code, exc.message).model_dump(by_alias=True))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception")
        return JSONResponse(
            status_code=500,
            content=Results.error(ErrorCode.SERVICE_ERROR, "internal error").model_dump(
                by_alias=True
            ),
        )

    @app.get("/health")
    async def health() -> dict:
        return Results.success({"status": "UP"}).model_dump(by_alias=True)

    app.include_router(rag_router)

    # TODO: 挂载其余领域 router（system / knowledge / ingestion / admin），随里程碑接入

    return app


app = create_app()
