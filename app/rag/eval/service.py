"""改写、意图与检索的离线评测编排；不调用回答模型。"""

import asyncio
from collections.abc import Sequence
from time import perf_counter
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.rag.eval.answer import EvalAnswerGenerator
from app.rag.eval.schemas import EvalResponse
from app.rag.intent.node import IntentKind, SubQuestionIntent
from app.rag.intent.resolver import IntentResolver
from app.rag.mcp.service import McpEvidence, McpIntentDispatcher
from app.rag.retrieval.models import RetrievalScope, RetrievedChunk
from app.rag.retrieval.scope import RetrievalScopeResolver
from app.rag.rewrite.models import RewriteResult


class EvalRewriter(Protocol):
    async def rewrite_with_split(
        self, question: str, history: Sequence[object] = ()
    ) -> RewriteResult: ...


class EvalRetriever(Protocol):
    async def retrieve(
        self,
        question: str,
        *,
        scope: RetrievalScope | None = None,
        rewrite_result: RewriteResult | None = None,
    ) -> list[RetrievedChunk]: ...


class EvalService:
    """提供与在线链路同源、但不生成答案的确定性检索证据。"""

    def __init__(
        self,
        engine: AsyncEngine,
        rewriter: EvalRewriter,
        intent_resolver: IntentResolver,
        retrieval: EvalRetriever,
        scope_resolver: RetrievalScopeResolver,
        mcp_dispatcher: McpIntentDispatcher,
        answer_generator: EvalAnswerGenerator | None = None,
    ) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._rewriter = rewriter
        self._intent_resolver = intent_resolver
        self._retrieval = retrieval
        self._scope_resolver = scope_resolver
        self._mcp_dispatcher = mcp_dispatcher
        self._answer_generator = answer_generator

    async def evaluate(
        self,
        question: str,
        *,
        collections: Sequence[str] = (),
        include_answer: bool = False,
    ) -> EvalResponse:
        started = perf_counter()
        rewrite = await self._rewriter.rewrite_with_split(question.strip(), ())
        intents = await self._intent_resolver.resolve(rewrite)
        scores = [score for item in intents for score in item.node_scores]
        has_mcp_intent = any(score.node.kind == IntentKind.MCP for score in scores)
        should_retrieve = not IntentResolver.is_system_only(intents) and (
            not scores or any(score.node.kind == IntentKind.KB for score in scores)
        )

        intent_scope = self._scope_resolver.resolve(intents)
        normalized_collections = tuple(
            dict.fromkeys(value.strip() for value in collections if value.strip())
        )
        scope = RetrievalScope(
            collections=normalized_collections or intent_scope.collections,
            top_k=intent_scope.top_k,
            allow_supplement=not normalized_collections,
        )

        async def retrieve() -> list[RetrievedChunk]:
            if not should_retrieve:
                return []
            return await self._retrieval.retrieve(
                question,
                scope=scope if scope.restricted else None,
                rewrite_result=rewrite,
            )

        evidence, chunks = await asyncio.gather(
            self._mcp_dispatcher.dispatch(intents), retrieve()
        )
        chunks = self._deduplicate(chunks)
        context_doc_ids = await self._resolve_context_doc_ids(chunks)
        doc_ids = list(dict.fromkeys(value for value in context_doc_ids if value))
        mcp_context = "\n\n".join(
            f"[{item.tool_id}]\n{item.content}" for item in evidence
        )
        clarification = any(self._is_clarification(item) for item in evidence)
        failure = any(self._is_failure(item) for item in evidence)
        success = any(
            not self._is_clarification(item) and not self._is_failure(item)
            for item in evidence
        )
        if has_mcp_intent and not evidence:
            failure = True

        retrieval_latency_ms = max(0, int((perf_counter() - started) * 1000))
        answer: str | None = None
        answer_latency_ms: int | None = None
        if include_answer:
            answer_started = perf_counter()
            if self._answer_generator is not None:
                answer = await self._answer_generator.generate(question, chunks)
            else:
                answer = ""
            answer_latency_ms = max(0, int((perf_counter() - answer_started) * 1000))

        return EvalResponse(
            retrievedDocIds=doc_ids,
            retrievedChunkIds=[chunk.key for chunk in chunks],
            retrievedContexts=[chunk.text for chunk in chunks],
            retrievedScores=[chunk.score for chunk in chunks],
            retrievedContextDocIds=context_doc_ids,
            retrievalCollections=list(scope.collections),
            answer=answer,
            answerLatencyMs=answer_latency_ms,
            mcpContext=mcp_context,
            hasMcpSuccess=success,
            needsClarification=clarification,
            hasMcpFailure=failure,
            hasKb=bool(chunks),
            subIntents=[item.sub_question for item in intents],
            intentLeafIds=[self._top_leaf_id(item) for item in intents],
            latencyMs=retrieval_latency_ms,
        )

    async def _resolve_context_doc_ids(
        self, chunks: list[RetrievedChunk]
    ) -> list[str | None]:
        if not chunks:
            return []
        chunk_ids = tuple(dict.fromkeys(chunk.id for chunk in chunks))
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(KnowledgeChunk.id, KnowledgeDocument.doc_name)
                    .join(
                        KnowledgeDocument,
                        KnowledgeDocument.id == KnowledgeChunk.doc_id,
                    )
                    .where(KnowledgeChunk.id.in_(chunk_ids))
                )
            ).all()
        by_chunk = {chunk_id: self._strip_extension(name) for chunk_id, name in rows}
        return [by_chunk.get(chunk.id) for chunk in chunks]

    @staticmethod
    def _deduplicate(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        seen: set[str] = set()
        unique: list[RetrievedChunk] = []
        for chunk in chunks:
            if chunk.key not in seen:
                seen.add(chunk.key)
                unique.append(chunk)
        return unique

    @staticmethod
    def _strip_extension(name: str) -> str:
        dot = name.rfind(".")
        return name[:dot] if 0 < dot < len(name) - 1 else name

    @staticmethod
    def _top_leaf_id(intent: SubQuestionIntent) -> str | None:
        return str(intent.node_scores[0].node.id) if intent.node_scores else None

    @staticmethod
    def _is_clarification(evidence: McpEvidence) -> bool:
        return "需要参数" in evidence.content and "询问" in evidence.content

    @staticmethod
    def _is_failure(evidence: McpEvidence) -> bool:
        return evidence.content.startswith(("工具调用失败", "未能为工具")) or (
            evidence.content.startswith("工具【")
            and evidence.content.endswith("当前不可用。")
        )
