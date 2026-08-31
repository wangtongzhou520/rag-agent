"""RAG 问答入口编排：ID 分配、handler 构造、meta 首发、管线执行与终态。"""

import asyncio

from app.framework.config import Settings
from app.framework.ids import new_uuid7
from app.framework.logging import get_logger
from app.framework.sse import MetaPayload, SseEventType, SseSender
from app.framework.trace_ctx import reset_trace_id, set_trace_id
from app.rag.memory.service import ConversationMemoryService
from app.rag.pipeline.event_handler import StreamChatEventHandler
from app.rag.pipeline.stream_chat import StreamChatContext, StreamChatPipeline
from app.rag.trace.record import RagTraceRecordService

logger = get_logger(__name__)


class RAGChatService:
    """stream_chat 在 producer 协程内运行：meta → pipeline → finish/done。"""

    def __init__(
        self,
        memory: ConversationMemoryService,
        pipeline: StreamChatPipeline,
        settings: Settings,
        trace: RagTraceRecordService | None = None,
    ) -> None:
        self._memory = memory
        self._pipeline = pipeline
        self._settings = settings
        self._trace = trace

    async def stream_chat(
        self,
        *,
        question: str,
        conversation_id: str | None,
        deep_thinking: bool,
        user_id: int,
        sender: SseSender,
    ) -> None:
        is_new_conversation = conversation_id is None
        resolved_conversation_id = conversation_id or new_uuid7()
        task_id = new_uuid7()
        trace_data = (
            await self._trace.start_run(
                resolved_conversation_id, task_id, user_id, question
            )
            if self._trace is not None
            else None
        )
        trace_token = set_trace_id(trace_data[0]) if trace_data else None
        trace_status = "SUCCESS"
        trace_error: str | None = None
        handler = StreamChatEventHandler(
            sender,
            self._memory,
            conversation_id=resolved_conversation_id,
            user_id=user_id,
            is_new_conversation=is_new_conversation,
            chunk_size=self._settings.ai.stream.message_chunk_size,
        )
        ctx = StreamChatContext(
            question=question,
            conversation_id=resolved_conversation_id,
            task_id=task_id,
            user_id=user_id,
            deep_thinking=deep_thinking,
            is_new_conversation=is_new_conversation,
        )
        try:
            async with asyncio.timeout(
                self._settings.rag.default.sse_timeout_ms / 1000
            ):
                await sender.send(
                    SseEventType.META,
                    MetaPayload(
                        conversation_id=resolved_conversation_id, task_id=task_id
                    ),
                )
                await self._pipeline.execute(ctx, handler)
        except asyncio.CancelledError:
            trace_status = "ERROR"
            trace_error = "cancelled"
            await sender.complete()
            raise
        except Exception as exc:
            trace_status = "ERROR"
            trace_error = f"{type(exc).__name__}: {exc}"
            logger.exception("stream chat producer failed", task_id=task_id)
            await sender.fail(exc)
        finally:
            if trace_data and self._trace is not None:
                await self._trace.finish_run(
                    trace_data[0], trace_data[1], trace_status, trace_error
                )
            if trace_token is not None:
                reset_trace_id(trace_token)
