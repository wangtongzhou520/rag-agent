"""M3 多通道并行检索编排。"""

import asyncio
from time import perf_counter
from typing import Protocol

from app.framework.logging import get_logger
from app.framework.trace_ctx import get_trace_id
from app.rag.retrieval.metadata import MetadataEnrichmentPostProcessor
from app.rag.retrieval.models import (
    RetrievalBudget,
    RetrievalScope,
    RetrievedChunk,
    SearchChannelResult,
    SearchChannelType,
    SearchContext,
)
from app.rag.retrieval.postprocessors import (
    DeduplicationPostProcessor,
    WeightedRrfFusion,
)
from app.rag.retrieval.rerank import Reranker, RerankPostProcessor
from app.rag.rewrite.models import RewriteResult
from app.rag.trace.record import RagTraceRecordService

logger = get_logger(__name__)


class SearchChannel(Protocol):
    channel_type: SearchChannelType
    channel_name: str

    async def search(self, context: SearchContext) -> SearchChannelResult: ...


class QueryRewriter(Protocol):
    async def rewrite_with_split(self, question: str) -> RewriteResult: ...


class MultiChannelRetrievalEngine:
    def __init__(
        self,
        channels: list[SearchChannel],
        budget: RetrievalBudget,
        fusion: WeightedRrfFusion,
        *,
        timeout_ms: int = 15_000,
        rewriter: QueryRewriter | None = None,
        reranker: Reranker | None = None,
        rerank_timeout_ms: int = 10_000,
        metadata_enricher: MetadataEnrichmentPostProcessor | None = None,
        trace: RagTraceRecordService | None = None,
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError("timeout_ms 必须大于 0")
        self._channels = list(channels)
        self._budget = budget
        self._fusion = fusion
        self._deduplication = DeduplicationPostProcessor()
        self._timeout_seconds = timeout_ms / 1000
        self._rewriter = rewriter
        self._rerank = (
            RerankPostProcessor(reranker, timeout_ms=rerank_timeout_ms)
            if reranker is not None
            else None
        )
        self._metadata_enricher = metadata_enricher
        self._trace = trace

    async def retrieve(
        self,
        question: str,
        *,
        scope: RetrievalScope | None = None,
        rewrite_result: RewriteResult | None = None,
    ) -> list[RetrievedChunk]:
        started = perf_counter()
        rewritten = rewrite_result.rewritten_question if rewrite_result else question
        sub_questions = rewrite_result.sub_questions if rewrite_result else ()
        if rewrite_result is None and self._rewriter is not None:
            try:
                result = await self._rewriter.rewrite_with_split(question)
                rewritten = result.rewritten_question or question
                sub_questions = result.sub_questions
            except Exception:
                logger.exception("问题改写失败，使用原问题检索")
        context = SearchContext(
            question, rewritten, self._budget, sub_questions, scope or RetrievalScope()
        )
        results = await asyncio.gather(
            *(self._run_channel(channel, context) for channel in self._channels)
        )
        deduplicated = self._deduplication.process(results)
        candidates = self._fusion.process(deduplicated)
        if self._rerank is not None:
            final = await self._rerank.process(
                context.main_question, candidates, self._budget.context_top_k
            )
        else:
            final = candidates[: self._budget.context_top_k]
        if self._metadata_enricher is not None:
            try:
                final = await self._metadata_enricher.process(final)
            except Exception:
                logger.exception("检索元数据富化失败，保留原结果")
        trace_id = get_trace_id()
        if self._trace is not None and trace_id:
            await self._trace.record_retrieval(
                trace_id,
                int((perf_counter() - started) * 1000),
                {
                    "originalQuestion": question,
                    "rewrittenQuestion": context.main_question,
                    "channels": [
                        {
                            "name": result.channel_name,
                            "type": str(result.channel_type),
                            "latencyMs": result.latency_ms,
                            "count": len(result.chunks),
                            "metadata": result.metadata,
                        }
                        for result in results
                    ],
                    "fusionCandidateCount": len(candidates),
                    "finalCount": len(final),
                    "candidateIds": [item.key for item in candidates],
                    "finalIds": [item.key for item in final],
                },
            )
        return final

    async def _run_channel(
        self, channel: SearchChannel, context: SearchContext
    ) -> SearchChannelResult:
        try:
            return await asyncio.wait_for(
                channel.search(context), timeout=self._timeout_seconds
            )
        except TimeoutError:
            logger.warning(
                "检索通道超时，按空结果降级",
                channel=channel.channel_name,
                timeout_ms=int(self._timeout_seconds * 1000),
            )
            error = "timeout"
        except Exception:
            logger.exception(
                "检索通道失败，按空结果降级", channel=channel.channel_name
            )
            error = "error"
        return SearchChannelResult(
            channel_type=channel.channel_type,
            channel_name=channel.channel_name,
            metadata={"degraded": error},
        )
