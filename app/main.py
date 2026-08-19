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
from app.framework.exceptions import BizException
from app.framework.ids import new_uuid7
from app.framework.logging import get_logger, init_logging
from app.framework.result import ErrorCode, Results
from app.framework.trace_ctx import reset_request_id, set_request_id

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    init_logging(settings.logging.level)

    # 基础设施资源：只创建与关闭，连通性自检随各里程碑补
    engine: AsyncEngine = create_async_engine(settings.datasource.url, pool_pre_ping=True)
    redis_client = aioredis.Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.database,
        password=settings.redis.password or None,
        decode_responses=True,
    )
    http_client = httpx.AsyncClient()

    app.state.engine = engine
    app.state.redis = redis_client
    app.state.http = http_client
    logger.info("app started", root_path=settings.server.root_path)

    try:
        yield
    finally:
        await engine.dispose()
        await redis_client.aclose()
        await http_client.aclose()
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

    # TODO: 挂载各领域 router（system / knowledge / ingestion / rag / admin），随里程碑接入

    return app


app = create_app()
