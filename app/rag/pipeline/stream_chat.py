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
from app.framework.logging import get_logger
from app.framework.stream_tasks import StreamTaskManager
from app.model_runtime.chat.service import LLMService
from app.rag.intent.guidance import IntentGuidanceService
from app.rag.intent.node import SubQuestionIntent
from app.rag.intent.resolver import IntentResolver
from app.rag.mcp.service import McpEvidence, McpIntentDispatcher
from app.rag.memory.service import ConversationMemoryService
from app.rag.pipeline.event_handler import StreamEventCallback
from app.rag.retrieval.models import RetrievalScope, RetrievedChunk
from app.rag.retrieval.scope import RetrievalScopeResolver
from app.rag.rewrite.models import RewriteResult
from app.rag.source.assembler import SourcesAssembler
from app.rag.source.citation import CitationContextEnricher, sanitize_attribute

EMPTY_RETRIEVAL_TEXT = "未检索到与问题相关的文档内容。"
logger = get_logger(__name__)


class RetrievalEngine(Protocol):
    """多通道检索引擎（docs/02）；本期由 EmptyRetrievalEngine 占位。"""

    async def retrieve(
        self,
        question: str,
        *,
        scope: RetrievalScope | None = None,
        rewrite_result: RewriteResult | None = None,
    ) -> Sequence[Any]: ...


class EmptyRetrievalEngine:
    """知识库就绪前的空检索实现：恒返回空，触发短路文案。"""

    async def retrieve(
        self,
        question: str,
        *,
        scope: RetrievalScope | None = None,
        rewrite_result: RewriteResult | None = None,
    ) -> Sequence[Any]:
        return []


class QueryRewriter(Protocol):
    async def rewrite_with_split(
        self, question: str, history: Sequence[ChatMessage] = ()
    ) -> RewriteResult: ...


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
    intents: list[SubQuestionIntent] = field(default_factory=list)


class StreamChatPipeline:
    """确定性编排管线：私有阶段方法 + 短路返回，各 async 阶段按序 await。"""

    def __init__(
        self,
        memory: ConversationMemoryService,
        llm: LLMService,
        retrieval: RetrievalEngine,
        intent_resolver: IntentResolver | None = None,
        mcp_dispatcher: McpIntentDispatcher | None = None,
        guidance: IntentGuidanceService | None = None,
        *,
        rewriter: QueryRewriter | None = None,
        scope_resolver: RetrievalScopeResolver | None = None,
        task_manager: StreamTaskManager | None = None,
    ) -> None:
        self._memory = memory
        self._llm = llm
        self._retrieval = retrieval
        self._intent_resolver = intent_resolver
        self._mcp_dispatcher = mcp_dispatcher
        self._guidance = guidance
        self._rewriter = rewriter
        self._scope_resolver = scope_resolver or RetrievalScopeResolver()
        self._task_manager = task_manager

    async def execute(self, ctx: StreamChatContext, callback: StreamEventCallback) -> None:
        try:
            await self._load_memory(ctx, callback)
            # ② 只改写一次；③ 意图分类与后续检索共享同一份结果
            rewrite_result = RewriteResult(ctx.question, (ctx.question,))
            if self._rewriter is not None:
                try:
                    rewrite_result = await self._rewriter.rewrite_with_split(
                        ctx.question, ctx.history
                    )
                except Exception:
                    logger.exception("问题改写失败，使用原问题继续")
            if self._intent_resolver is not None:
                try:
                    ctx.intents = await self._intent_resolver.resolve(rewrite_result)
                except Exception:  # noqa: BLE001
                    ctx.intents = []
            # ④ 歧义引导命中后直接返回追问；⑤ 纯 SYSTEM 意图不访问知识库
            if self._guidance is not None:
                decision = await self._guidance.detect(
                    rewrite_result.rewritten_question, ctx.intents
                )
                if decision.required:
                    await callback.on_content(decision.message)
                    await callback.on_complete()
                    return
            if IntentResolver.is_system_only(ctx.intents):
                await self._stream_system_response(ctx, callback)
                return
            if self._mcp_dispatcher is not None:
                evidence = await self._mcp_dispatcher.dispatch(ctx.intents)
                if evidence:
                    await self._stream_mcp_response(ctx, evidence, callback)
                    return
            scope = self._scope_resolver.resolve(ctx.intents)
            if scope.restricted:
                chunks = await self._retrieval.retrieve(
                    ctx.question, scope=scope, rewrite_result=rewrite_result
                )
            else:
                chunks = await self._retrieval.retrieve(
                    ctx.question, rewrite_result=rewrite_result
                )
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
        assembled = SourcesAssembler().assemble(typed_chunks)
        await callback.on_sources(list(assembled.sources))
        await callback.on_grounding_chunks(
            [
                {"docName": chunk.doc_name, "text": chunk.text}
                for chunk in typed_chunks
            ]
        )
        raw_context = "\n\n".join(
            (
                '<content data-ragent-doc-id="'
                f'{sanitize_attribute(chunk.doc_id)}">'
                f"\n{chunk.text}\n</content>"
            )
            for chunk in typed_chunks
        )
        context = CitationContextEnricher().enrich(raw_context, assembled.indexes)
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
        await self._run_model_stream(ctx.task_id, request, callback)

    async def _stream_system_response(
        self, ctx: StreamChatContext, callback: StreamEventCallback
    ) -> None:
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content="你是友好、简洁的智能助手。直接回答用户，不要编造知识库来源或引用。",
            ),
            *ctx.history,
            ChatMessage(role=ChatRole.USER, content=ctx.question),
        ]
        await self._run_model_stream(
            ctx.task_id,
            ChatRequest(messages=messages, thinking=ctx.deep_thinking),
            callback,
        )

    async def _stream_mcp_response(
        self,
        ctx: StreamChatContext,
        evidence: list[McpEvidence],
        callback: StreamEventCallback,
    ) -> None:
        context = "\n\n".join(
            f'<tool-result tool="{item.tool_id}">\n{item.content}\n</tool-result>'
            for item in evidence
        )
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=(
                    "依据 <tool-context> 中的实时工具结果回答用户。"
                    "不得把工具结果标成知识库引用。"
                    f"\n<tool-context>\n{context}\n</tool-context>"
                ),
            ),
            *ctx.history,
            ChatMessage(role=ChatRole.USER, content=ctx.question),
        ]
        await self._run_model_stream(
            ctx.task_id,
            ChatRequest(messages=messages, thinking=ctx.deep_thinking),
            callback,
        )

    async def _run_model_stream(
        self,
        task_id: str,
        request: ChatRequest,
        callback: StreamEventCallback,
    ) -> None:
        handle = await self._llm.stream_chat(request, callback)
        if handle is None:
            return
        if self._task_manager is not None:
            await self._task_manager.bind_cancel(task_id, handle.cancel)
        await handle.wait()
