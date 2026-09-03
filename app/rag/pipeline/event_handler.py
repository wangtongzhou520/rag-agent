"""流式问答事件处理器：StreamCallback 实现，累积内容并落库（docs/01 §5.1）。

处理器是管线与 SSE 推送之间的桥梁：回调累积 content/thinking，完成/取消时
经 ConversationMemoryService 落库 assistant 消息，再发 finish/cancel 序列。
"""

import asyncio
import time
from typing import Protocol

from app.framework.logging import get_logger
from app.framework.sse import (
    CompletionPayload,
    GuidancePayload,
    MessageDeltaType,
    MessageStatus,
    SourceRef,
    SseEventType,
    SseSender,
)
from app.framework.stream_tasks import StreamTaskManager
from app.model_runtime.chat.base import StreamCallback
from app.rag.memory.service import ConversationMemoryService

logger = get_logger(__name__)


class StreamEventCallback(StreamCallback, Protocol):
    """管线侧回调协议：LLM 流回调 + 记忆/取消扩展（docs/01 §5.1）。"""

    async def on_reply_to_message_id(self, message_id: str | None) -> None: ...
    async def on_cancelled(self) -> None: ...
    async def on_sources(self, sources: list[SourceRef]) -> None: ...
    async def on_grounding_chunks(self, chunks: list[dict]) -> None: ...
    async def on_guidance(self, payload: GuidancePayload) -> None: ...


class StreamChatEventHandler:
    """累积流式内容，完成/取消时落库并下发 SSE 终态事件。"""

    def __init__(
        self,
        sender: SseSender,
        memory: ConversationMemoryService,
        *,
        conversation_id: str,
        user_id: int,
        is_new_conversation: bool,
        chunk_size: int = 5,
        task_id: str | None = None,
        task_manager: StreamTaskManager | None = None,
    ) -> None:
        self._sender = sender
        self._memory = memory
        self._conversation_id = conversation_id
        self._user_id = user_id
        self._is_new_conversation = is_new_conversation
        self._chunk_size = chunk_size
        self._task_id = task_id
        self._task_manager = task_manager
        self._contents: list[str] = []
        self._thinkings: list[str] = []
        self._thinking_start: float | None = None
        self._reply_to_message_id: str | None = None
        self._sources: list[SourceRef] = []
        self._grounding_chunks: list[dict] = []
        self._terminal = False
        self._terminal_lock = asyncio.Lock()
        self._terminal_task: asyncio.Task[None] | None = None

    def _accepting(self) -> bool:
        return not self._terminal and not (
            self._task_id
            and self._task_manager
            and self._task_manager.is_cancelled(self._task_id)
        )

    async def on_content(self, content: str) -> None:
        if not self._accepting():
            return
        self._contents.append(content)
        await self._sender.send_message(
            MessageDeltaType.RESPONSE, content, self._chunk_size
        )

    async def on_thinking(self, content: str) -> None:
        if not self._accepting():
            return
        if not self._thinkings:
            self._thinking_start = time.monotonic()
        self._thinkings.append(content)
        await self._sender.send_message(MessageDeltaType.THINK, content, self._chunk_size)

    async def on_reply_to_message_id(self, message_id: str | None) -> None:
        if not self._accepting():
            return
        self._reply_to_message_id = message_id

    async def on_sources(self, sources: list[SourceRef]) -> None:
        if not self._accepting():
            return
        self._sources = list(sources)

    async def on_grounding_chunks(self, chunks: list[dict]) -> None:
        if not self._accepting():
            return
        self._grounding_chunks = list(chunks)

    async def on_guidance(self, payload: GuidancePayload) -> None:
        if not self._accepting():
            return
        await self._sender.send(SseEventType.GUIDANCE, payload)

    async def on_complete(self) -> None:
        """正常完成：assistant 消息 NORMAL 落库，发 finish + done。"""
        await self._finish(MessageStatus.NORMAL)

    async def on_error(self, error: Exception) -> None:
        """LLM 流异常：不补 finish，由上层 sender.fail 关闭连接（docs/01 §13）。"""
        logger.warning("llm 流异常", error=str(error))

    async def on_cancelled(self) -> None:
        """取消收尾：已累积内容非空则以 INTERRUPTED 落库（docs/01 §9.2）。"""
        await self._finish(MessageStatus.INTERRUPTED)

    async def _finish(self, status: MessageStatus) -> None:
        """创建唯一且 shield 的终态任务，消除完成与取消并发收尾竞态。"""
        async with self._terminal_lock:
            if self._terminal_task is None:
                if status is MessageStatus.NORMAL and not self._accepting():
                    return
                if self._terminal:
                    return
                self._terminal = True
                self._terminal_task = asyncio.create_task(
                    self._emit_terminal(status),
                    name=f"stream-terminal:{self._task_id or self._conversation_id}",
                )
            terminal_task = self._terminal_task
        await asyncio.shield(terminal_task)

    async def _emit_terminal(self, status: MessageStatus) -> None:
        message_id = (
            await self._persist(status)
            if status is MessageStatus.NORMAL or self._contents
            else None
        )
        await self._sender.send(
            SseEventType.FINISH
            if status is MessageStatus.NORMAL
            else SseEventType.CANCEL,
            CompletionPayload(
                message_id=message_id,
                title="新对话" if self._is_new_conversation else None,
                sources=self._sources or None,
                message_status=status,
            ),
        )
        await self._sender.done()

    def _thinking_duration(self) -> int | None:
        if self._thinking_start is None:
            return None
        return int(time.monotonic() - self._thinking_start)

    async def _persist(self, status: MessageStatus) -> str | None:
        return await self._memory.append_assistant_message(
            self._conversation_id,
            self._user_id,
            "".join(self._contents),
            thinking_content="".join(self._thinkings) or None,
            thinking_duration=self._thinking_duration(),
            sources=[
                source.model_dump(by_alias=True, exclude_none=True)
                for source in self._sources
            ]
            or None,
            retrieved_chunks=self._grounding_chunks or None,
            message_status=str(status),
            reply_to_message_id=self._reply_to_message_id,
        )
