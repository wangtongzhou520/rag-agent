"""M3 多通道并行检索编排。"""

import asyncio
from typing import Protocol

from app.framework.logging import get_logger
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
from app.rag.rewrite.models import RewriteResult

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
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError("timeout_ms 必须大于 0")
        self._channels = list(channels)
        self._budget = budget
        self._fusion = fusion
        self._deduplication = DeduplicationPostProcessor()
        self._timeout_seconds = timeout_ms / 1000
        self._rewriter = rewriter

    async def retrieve(
        self, question: str, *, scope: RetrievalScope | None = None
    ) -> list[RetrievedChunk]:
        rewritten = question
        sub_questions: tuple[str, ...] = ()
        if self._rewriter is not None:
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
        return candidates[: self._budget.context_top_k]

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
