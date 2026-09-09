"""自研 PG 队列 worker（python -m app.worker）。"""

import asyncio
import os
import signal
import socket
from contextlib import suppress

import asyncpg
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.chunk.service import ChunkingService
from app.core.ingest.kernel import ChunkEmbeddingService, DefaultIngestionKernel
from app.core.ingest.writer import PgChunkIndexWriter
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.registry import build_default_registry
from app.framework.config import DatasourceSettings, get_settings
from app.framework.db import init_schema
from app.framework.idempotency import (
    ConsumeInProgressError,
    ConsumeMarkExecutor,
    ConsumeState,
)
from app.framework.logging import get_logger, init_logging
from app.framework.task_queue import ClaimedTask, TaskQueue
from app.knowledge.tasks import KnowledgeTaskHandler
from app.model_runtime.factory import build_model_runtime
from app.rag.feedback import FEEDBACK_TASK_TYPE, MessageFeedbackTaskHandler

logger = get_logger(__name__)

RENEW_SECONDS = 60.0


class WorkerTaskHandler:
    """按任务类型分发到领域 handler，保持 PG 队列只有一套消费循环。"""

    def __init__(
        self,
        knowledge: KnowledgeTaskHandler,
        feedback: MessageFeedbackTaskHandler,
        consume_marks: ConsumeMarkExecutor | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._feedback = feedback
        self._consume_marks = consume_marks

    async def handle(self, task: ClaimedTask) -> None:
        key = str(task.event_id)
        owns_mark = False
        if self._consume_marks is not None:
            try:
                state = await self._consume_marks.try_begin(key)
            except Exception:
                logger.exception(
                    "consume idempotency unavailable; using PostgreSQL guards",
                    task_id=task.id,
                )
            else:
                if state is ConsumeState.CONSUMED:
                    logger.info("consumed task skipped", task_id=task.id)
                    return
                if state is ConsumeState.CONSUMING:
                    raise ConsumeInProgressError("任务正在被其他实例消费")
                owns_mark = True
        try:
            if task.task_type == FEEDBACK_TASK_TYPE:
                await self._feedback.handle(task)
            else:
                await self._knowledge.handle(task)
        except BaseException:
            if owns_mark and self._consume_marks is not None:
                try:
                    await self._consume_marks.rollback(key)
                except Exception:
                    logger.exception(
                        "consume idempotency rollback failed", task_id=task.id
                    )
            raise
        if owns_mark and self._consume_marks is not None:
            try:
                marked = await self._consume_marks.mark_consumed(key)
                if not marked:
                    logger.warning(
                        "consume idempotency ownership lost before completion",
                        task_id=task.id,
                    )
            except Exception:
                logger.exception(
                    "consume idempotency completion failed; PostgreSQL remains authoritative",
                    task_id=task.id,
                )

    async def mark_claimed(
        self, session: AsyncSession, task: ClaimedTask
    ) -> None:
        await self._knowledge.mark_claimed(session, task)

    async def mark_retry_or_failed_in_session(
        self,
        session: AsyncSession,
        task: ClaimedTask,
        error: str,
        terminal: bool,
    ) -> None:
        await self._knowledge.mark_retry_or_failed_in_session(
            session, task, error, terminal
        )

async def _listen_notifications(
    datasource: DatasourceSettings,
    wakeup: asyncio.Event,
    stopped: asyncio.Event,
) -> None:
    """LISTEN 失败时重连；claim 循环始终保留短轮询兜底。"""
    loop = asyncio.get_running_loop()
    while not stopped.is_set():
        connection = None
        try:
            connection = await asyncpg.connect(
                host=datasource.host,
                port=datasource.port,
                database=datasource.database,
                user=datasource.username,
                password=datasource.password or None,
            )

            def on_notify(*_) -> None:
                loop.call_soon_threadsafe(wakeup.set)

            await connection.add_listener("ragent_task", on_notify)
            await stopped.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("task LISTEN connection failed; polling remains active")
            try:
                await asyncio.wait_for(stopped.wait(), timeout=5)
            except TimeoutError:
                continue
        finally:
            if connection is not None:
                with suppress(Exception):
                    await connection.close()


async def _renew_loop(
    queue: TaskQueue,
    task: ClaimedTask,
    owner: str,
    stopped: asyncio.Event,
    lease_lost: asyncio.Event,
    *,
    renew_seconds: float = RENEW_SECONDS,
    lease_seconds: float = 300,
) -> None:
    loop = asyncio.get_running_loop()
    last_success = loop.time()
    while not stopped.is_set():
        try:
            await asyncio.wait_for(stopped.wait(), timeout=renew_seconds)
        except TimeoutError:
            try:
                renewed = await queue.renew(task.id, owner)
            except Exception:
                logger.exception("task lease renewal failed", task_id=task.id)
                if loop.time() - last_success >= lease_seconds:
                    lease_lost.set()
                    return
                continue
            if not renewed:
                logger.warning("task lease lost", task_id=task.id)
                lease_lost.set()
                return
            last_success = loop.time()


async def _process(
    queue: TaskQueue,
    handler: WorkerTaskHandler,
    task: ClaimedTask,
    owner: str,
    *,
    renew_seconds: float = RENEW_SECONDS,
    lease_seconds: float = 300,
) -> None:
    renew_stopped = asyncio.Event()
    lease_lost = asyncio.Event()
    renew_task = asyncio.create_task(
        _renew_loop(
            queue,
            task,
            owner,
            renew_stopped,
            lease_lost,
            renew_seconds=renew_seconds,
            lease_seconds=lease_seconds,
        ),
        name=f"task-renew:{task.id}",
    )
    handler_task = asyncio.create_task(
        handler.handle(task), name=f"task-handler:{task.id}"
    )
    lease_waiter = asyncio.create_task(
        lease_lost.wait(), name=f"task-lease-lost:{task.id}"
    )
    try:
        done, _ = await asyncio.wait(
            (handler_task, lease_waiter), return_when=asyncio.FIRST_COMPLETED
        )
        if handler_task not in done:
            handler_task.cancel()
            with suppress(asyncio.CancelledError):
                await handler_task
            logger.error(
                "task execution cancelled after lease loss",
                task_id=task.id,
                owner=owner,
            )
            return
        await handler_task
        completed = await queue.succeed(task.id, owner, task.event_id)
        if completed:
            logger.info("task succeeded", task_id=task.id, task_type=task.task_type)
        else:
            logger.info(
                "task superseded and requeued",
                task_id=task.id,
                task_type=task.task_type,
            )
    except ConsumeInProgressError as exc:
        logger.info("task consumption deferred", task_id=task.id)
        await queue.defer(
            task.id,
            owner,
            str(exc),
            on_transition=handler.mark_retry_or_failed_in_session,
        )
    except Exception as exc:
        logger.exception(
            "task failed", task_id=task.id, task_type=task.task_type
        )
        await queue.fail(
            task.id,
            owner,
            str(exc),
            task.event_id,
            handler.mark_retry_or_failed_in_session,
        )
    finally:
        renew_stopped.set()
        lease_waiter.cancel()
        if not handler_task.done():
            handler_task.cancel()
        renew_task.cancel()
        await asyncio.gather(
            lease_waiter, handler_task, renew_task, return_exceptions=True
        )


async def run() -> None:
    settings = get_settings()
    init_logging(settings.logging.level)
    task_settings = settings.rag.task
    if task_settings.heartbeat_seconds >= task_settings.lease_seconds:
        raise ValueError("rag.task.heartbeat_seconds must be less than lease_seconds")
    if (
        settings.rag.idempotency.enabled
        and settings.rag.idempotency.consume_ttl_seconds
        <= task_settings.lease_seconds + task_settings.recovery_interval_seconds
    ):
        raise ValueError(
            "rag.idempotency.consume_ttl_seconds must exceed lease plus recovery interval"
        )
    engine = create_async_engine(settings.datasource.url, pool_pre_ping=True)
    if settings.datasource.auto_ddl:
        await init_schema(engine)
    runtime = build_model_runtime(settings)
    redis_client = aioredis.Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.database,
        password=settings.redis.password or None,
        decode_responses=True,
    )
    kernel = DefaultIngestionKernel(
        MimeTypeDetector(),
        build_default_registry(),
        ChunkingService(),
        ChunkEmbeddingService(runtime.embedding),
        PgChunkIndexWriter(engine),
    )
    queue = TaskQueue(engine, lease_seconds=int(task_settings.lease_seconds))
    handler = WorkerTaskHandler(
        KnowledgeTaskHandler(engine, kernel),
        MessageFeedbackTaskHandler(engine),
        ConsumeMarkExecutor(
            redis_client,
            settings.redis.key_prefix,
            ttl_seconds=settings.rag.idempotency.consume_ttl_seconds,
            consuming_ttl_seconds=(
                task_settings.lease_seconds
                + task_settings.recovery_interval_seconds
                + 30
            ),
        )
        if settings.rag.idempotency.enabled
        else None,
    )
    owner = f"{socket.gethostname()}:{os.getpid()}"

    stop_event = asyncio.Event()
    wakeup = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    logger.info("worker started", owner=owner)
    listener = asyncio.create_task(
        _listen_notifications(settings.datasource, wakeup, stop_event),
        name="task-listener",
    )
    last_recover = loop.time() - (
        task_settings.recovery_interval_seconds
        - task_settings.recovery_initial_delay_seconds
    )
    try:
        while not stop_event.is_set():
            if (
                loop.time() - last_recover
                >= task_settings.recovery_interval_seconds
            ):
                recovered = await queue.recover_stuck(
                    handler.mark_retry_or_failed_in_session
                )
                if recovered:
                    logger.warning("recovered stuck tasks", count=len(recovered))
                last_recover = loop.time()
            task = await queue.claim(owner, handler.mark_claimed)
            if task is None:
                wakeup.clear()
                stop_waiter = asyncio.create_task(stop_event.wait())
                notify_waiter = asyncio.create_task(wakeup.wait())
                done, pending = await asyncio.wait(
                    (stop_waiter, notify_waiter),
                    timeout=task_settings.poll_interval_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for waiter in pending:
                    waiter.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for waiter in done:
                    await waiter
            else:
                await _process(
                    queue,
                    handler,
                    task,
                    owner,
                    renew_seconds=task_settings.heartbeat_seconds,
                    lease_seconds=task_settings.lease_seconds,
                )
    finally:
        stop_event.set()
        listener.cancel()
        with suppress(asyncio.CancelledError):
            await listener
        await runtime.http.aclose()
        await redis_client.aclose()
        await engine.dispose()
        logger.info("worker stopped", owner=owner)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
