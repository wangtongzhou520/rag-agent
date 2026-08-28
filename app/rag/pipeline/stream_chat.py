"""问答主链路七步编排（docs/01 §5）。

本期为最小骨架：记忆加载 → 检索 → 空检索短路 / 流式问答。
改写拆分（②）、意图树（③）、歧义追问（④）、闲聊短路（⑤）为 passthrough，
待 docs/02 对应增量接入；检索通道在知识库表（M2）就绪前恒为空。
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.framework.chat_types import ChatMessage, ChatRequest
from app.model_runtime.chat.service import LLMService
from app.rag.memory.service import ConversationMemoryService
from app.rag.pipeline.event_handler import StreamEventCallback

EMPTY_RETRIEVAL_TEXT = "未检索到与问题相关的文档内容。"


class RetrievalEngine(Protocol):
    """多通道检索引擎（docs/02）；本期由 EmptyRetrievalEngine 占位。"""

    async def retrieve(self, question: str) -> Sequence[Any]: ...


class EmptyRetrievalEngine:
    """知识库就绪前的空检索实现：恒返回空，触发短路文案。"""

    async def retrieve(self, question: str) -> Sequence[Any]:
        return []


@dataclass(slots=True)
class StreamChatContext:
    """主链路上下文：入参 + 管道中间态（docs/01 §2.5）。"""

    question: str
    conversation_id: str
    task_id: str
    user_id: int
    deep_thinking: bool = False
    is_new_conversation: bool = False
    history: list[ChatMessage] = field(default_factory=list)


class StreamChatPipeline:
    """确定性编排管线：私有阶段方法 + 短路返回，各 async 阶段按序 await。"""

    def __init__(
        self,
        memory: ConversationMemoryService,
        llm: LLMService,
        retrieval: RetrievalEngine,
    ) -> None:
        self._memory = memory
        self._llm = llm
        self._retrieval = retrieval

    async def execute(self, ctx: StreamChatContext, callback: StreamEventCallback) -> None:
        try:
            await self._load_memory(ctx, callback)
            # ② rewrite_query / ③ resolve_intents：passthrough，待 docs/02 接入
            # ④ handle_guidance / ⑤ handle_system_only：本期不触发
            chunks = await self._retrieval.retrieve(ctx.question)
            if not chunks:
                # ⑥ 空检索短路：固定文案 + 正常落库（无 sources）
                await callback.on_content(EMPTY_RETRIEVAL_TEXT)
                await callback.on_complete()
                return
            await self._stream_rag_response(ctx, chunks, callback)
        except asyncio.CancelledError:
            # 取消收尾：部分内容以 INTERRUPTED 落库（docs/01 §9.2）
            await callback.on_cancelled()
            raise

    async def _load_memory(
        self, ctx: StreamChatContext, callback: StreamEventCallback
    ) -> None:
        """① 记忆加载：历史加载在当前问题落库之前（历史不含本问）。"""
        ctx.history = await self._memory.load(ctx.conversation_id, ctx.user_id)
        question_message_id = await self._memory.append_user_message(
            ctx.conversation_id, ctx.user_id, ctx.question
        )
        await callback.on_reply_to_message_id(question_message_id)

    async def _stream_rag_response(
        self, ctx: StreamChatContext, chunks: Sequence[Any], callback: StreamEventCallback
    ) -> None:
        """⑦ Prompt 组装 + LLM 流式（本期不可达：检索恒空；M2 后接入溯源与编号）。

        TODO(M2/M3)：mergeIntentGroup → sources 编号 → citation 注入 → grounding 暂存。
        """
        messages = [*ctx.history, ChatMessage(role="user", content=ctx.question)]
        request = ChatRequest(messages=messages, thinking=ctx.deep_thinking)
        await self._llm.stream_chat(request, callback)
