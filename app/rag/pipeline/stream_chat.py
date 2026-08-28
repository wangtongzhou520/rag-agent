"""问答主链路七步编排（docs/01 §5）。

本期为最小骨架：记忆加载 → 检索 → 空检索短路 / 流式问答。
改写拆分（②）、意图树（③）、歧义追问（④）、闲聊短路（⑤）为 passthrough，
待 docs/02 对应增量接入；检索通道在知识库表（M2）就绪前恒为空。
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.framework.chat_types import ChatMessage, ChatRequest, ChatRole
from app.model_runtime.chat.service import LLMService
from app.rag.memory.service import ConversationMemoryService
from app.rag.pipeline.event_handler import StreamEventCallback
from app.rag.retrieval.models import RetrievedChunk

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
        """⑦ 来源编号、上下文组装与 LLM 流式。"""
        typed_chunks = [chunk for chunk in chunks if isinstance(chunk, RetrievedChunk)]
        sources_by_doc: dict[int, RetrievedChunk] = {}
        for chunk in typed_chunks:
            current = sources_by_doc.get(chunk.doc_id)
            if current is None or chunk.score > current.score:
                sources_by_doc[chunk.doc_id] = chunk
        ranked = sorted(
            sources_by_doc.values(), key=lambda item: (-item.score, item.doc_id)
        )
        source_indexes = {
            chunk.doc_id: index for index, chunk in enumerate(ranked, start=1)
        }
        await callback.on_sources(
            [chunk.to_source(source_indexes[chunk.doc_id]) for chunk in ranked]
        )
        context = "\n\n".join(
            (
                f'<content ref="{source_indexes[chunk.doc_id]}">'
                f"\n{chunk.text}\n</content>"
            )
            for chunk in typed_chunks
        )
        system = (
            "你是严谨的知识库问答助手。仅依据 <knowledge-context> 中的资料回答；"
            "资料不足时明确说明。引用事实时在句末使用 [N](#cite-N)，N 必须来自 ref。"
            f"\n<knowledge-context>\n{context}\n</knowledge-context>"
        )
        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=system),
            *ctx.history,
            ChatMessage(role=ChatRole.USER, content=ctx.question),
        ]
        request = ChatRequest(messages=messages, thinking=ctx.deep_thinking)
        await self._llm.stream_chat(request, callback)
