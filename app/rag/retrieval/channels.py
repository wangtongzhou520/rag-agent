"""检索通道适配器；外部通道后续按同一契约接入。"""

from time import perf_counter
from typing import Protocol

from app.rag.retrieval.models import (
    RetrievedChunk,
    SearchChannelResult,
    SearchChannelType,
    SearchContext,
)


class VectorRetriever(Protocol):
    async def retrieve(
        self,
        question: str,
        *,
        limit: int | None = None,
        collections: tuple[str, ...] = (),
        supplement_ratio: float = 0.0,
    ) -> list[RetrievedChunk]: ...


class VectorSearchChannel:
    channel_type = SearchChannelType.VECTOR
    channel_name = "pgvector"

    def __init__(
        self, retriever: VectorRetriever, *, supplement_ratio: float = 0.25
    ) -> None:
        self._retriever = retriever
        self._supplement_ratio = max(0.0, min(1.0, supplement_ratio))

    async def search(self, context: SearchContext) -> SearchChannelResult:
        started = perf_counter()
        options = {"limit": context.scope.top_k or context.budget.recall_budget}
        if context.scope.collections:
            options["collections"] = context.scope.collections
            options["supplement_ratio"] = self._supplement_ratio
        chunks = await self._retriever.retrieve(context.main_question, **options)
        return SearchChannelResult(
            channel_type=self.channel_type,
            channel_name=self.channel_name,
            chunks=tuple(chunks),
            latency_ms=int((perf_counter() - started) * 1000),
        )
