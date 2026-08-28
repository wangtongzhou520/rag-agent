"""RAG 问答入口编排：ID 分配、handler 构造、meta 首发、管线执行与终态。"""

import asyncio

from app.framework.config import Settings
from app.framework.ids import new_uuid7
from app.framework.logging import get_logger
from app.framework.sse import MetaPayload, SseEventType, SseSender
from app.rag.memory.service import ConversationMemoryService
from app.rag.pipeline.event_handler import StreamChatEventHandler
from app.rag.pipeline.stream_chat import StreamChatContext, StreamChatPipeline

logger = get_logger(__name__)


class RAGChatService:
    """stream_chat 在 producer 协程内运行：meta → pipeline → finish/done。"""

    def __init__(
        self,
        memory: ConversationMemoryService,
        pipeline: StreamChatPipeline,
        settings: Settings,
    ) -> None:
        self._memory = memory
        self._pipeline = pipeline
        self._settings = settings

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
            await sender.complete()
            raise
        except Exception as exc:
            logger.exception("stream chat producer failed", task_id=task_id)
            await sender.fail(exc)
