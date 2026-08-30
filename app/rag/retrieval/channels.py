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
        self, question: str, *, limit: int | None = None
    ) -> list[RetrievedChunk]: ...


class VectorSearchChannel:
    channel_type = SearchChannelType.VECTOR
    channel_name = "pgvector"

    def __init__(self, retriever: VectorRetriever) -> None:
        self._retriever = retriever

    async def search(self, context: SearchContext) -> SearchChannelResult:
        started = perf_counter()
        chunks = await self._retriever.retrieve(
            context.main_question,
            limit=context.budget.recall_budget,
        )
        return SearchChannelResult(
            channel_type=self.channel_type,
            channel_name=self.channel_name,
            chunks=tuple(chunks),
            latency_ms=int((perf_counter() - started) * 1000),
        )
