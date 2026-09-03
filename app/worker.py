"""自研 PG 队列 worker（python -m app.worker）。"""

import asyncio
import os
import signal
import socket
from contextlib import suppress

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.chunk.service import ChunkingService
from app.core.ingest.kernel import ChunkEmbeddingService, DefaultIngestionKernel
from app.core.ingest.writer import PgChunkIndexWriter
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.registry import build_default_registry
from app.framework.config import DatasourceSettings, get_settings
from app.framework.db import init_schema
from app.framework.logging import get_logger, init_logging
from app.framework.task_queue import ClaimedTask, TaskQueue
from app.knowledge.tasks import KnowledgeTaskHandler
from app.model_runtime.factory import build_model_runtime
from app.rag.feedback import FEEDBACK_TASK_TYPE, MessageFeedbackTaskHandler

logger = get_logger(__name__)

POLL_SECONDS = 1.0
RECOVER_SECONDS = 60.0
RENEW_SECONDS = 60.0


class WorkerTaskHandler:
    """按任务类型分发到领域 handler，保持 PG 队列只有一套消费循环。"""

    def __init__(
        self,
        knowledge: KnowledgeTaskHandler,
        feedback: MessageFeedbackTaskHandler,
    ) -> None:
        self._knowledge = knowledge
        self._feedback = feedback

    async def handle(self, task: ClaimedTask) -> None:
        if task.task_type == FEEDBACK_TASK_TYPE:
            await self._feedback.handle(task)
            return
        await self._knowledge.handle(task)

    async def mark_retry_or_failed(
        self, task: ClaimedTask, error: str, terminal: bool
    ) -> None:
        await self._knowledge.mark_retry_or_failed(task, error, terminal)


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
    queue: TaskQueue, task: ClaimedTask, owner: str, stopped: asyncio.Event
) -> None:
    while not stopped.is_set():
        try:
            await asyncio.wait_for(stopped.wait(), timeout=RENEW_SECONDS)
        except TimeoutError:
            if not await queue.renew(task.id, owner):
                logger.warning("task lease lost", task_id=task.id)
                return


async def _process(
    queue: TaskQueue,
    handler: WorkerTaskHandler,
    task: ClaimedTask,
    owner: str,
) -> None:
    renew_stopped = asyncio.Event()
    renew_task = asyncio.create_task(
        _renew_loop(queue, task, owner, renew_stopped),
        name=f"task-renew:{task.id}",
    )
    try:
        await handler.handle(task)
        completed = await queue.succeed(task.id, owner, task.event_id)
        if completed:
            logger.info("task succeeded", task_id=task.id, task_type=task.task_type)
        else:
            logger.info(
                "task superseded and requeued",
                task_id=task.id,
                task_type=task.task_type,
            )
    except Exception as exc:
        logger.exception(
            "task failed", task_id=task.id, task_type=task.task_type
        )
        terminal = await queue.fail(task.id, owner, str(exc), task.event_id)
        await handler.mark_retry_or_failed(task, str(exc), terminal)
    finally:
        renew_stopped.set()
        renew_task.cancel()
        with suppress(asyncio.CancelledError):
            await renew_task


async def run() -> None:
    settings = get_settings()
    init_logging(settings.logging.level)
    engine = create_async_engine(settings.datasource.url, pool_pre_ping=True)
    if settings.datasource.auto_ddl:
        await init_schema(engine)
    runtime = build_model_runtime(settings)
    kernel = DefaultIngestionKernel(
        MimeTypeDetector(),
        build_default_registry(),
        ChunkingService(),
        ChunkEmbeddingService(runtime.embedding),
        PgChunkIndexWriter(engine),
    )
    queue = TaskQueue(engine)
    handler = WorkerTaskHandler(
        KnowledgeTaskHandler(engine, kernel),
        MessageFeedbackTaskHandler(engine),
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
    last_recover = loop.time()
    try:
        while not stop_event.is_set():
            if loop.time() - last_recover >= RECOVER_SECONDS:
                recovered = await queue.recover_stuck()
                if recovered:
                    for recovered_task, terminal in recovered:
                        await handler.mark_retry_or_failed(
                            recovered_task, "任务租约超时", terminal
                        )
                    logger.warning("recovered stuck tasks", count=len(recovered))
                last_recover = loop.time()
            task = await queue.claim(owner)
            if task is None:
                wakeup.clear()
                stop_waiter = asyncio.create_task(stop_event.wait())
                notify_waiter = asyncio.create_task(wakeup.wait())
                done, pending = await asyncio.wait(
                    (stop_waiter, notify_waiter),
                    timeout=POLL_SECONDS,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for waiter in pending:
                    waiter.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for waiter in done:
                    await waiter
            else:
                await _process(queue, handler, task, owner)
    finally:
        stop_event.set()
        listener.cancel()
        with suppress(asyncio.CancelledError):
            await listener
        await runtime.http.aclose()
        await engine.dispose()
        logger.info("worker stopped", owner=owner)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
