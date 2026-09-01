"""M3 多通道编排、去重与加权 RRF。"""

import asyncio
from uuid import UUID, uuid4

import pytest

from app.rag.retrieval.channels import VectorSearchChannel
from app.rag.retrieval.engine import MultiChannelRetrievalEngine
from app.rag.retrieval.metadata import (
    DocumentMetadata,
    MetadataEnrichmentPostProcessor,
)
from app.rag.retrieval.models import (
    RetrievalBudget,
    RetrievalScope,
    RetrievedChunk,
    SearchChannelResult,
    SearchChannelType,
    SearchContext,
)
from app.rag.retrieval.postprocessors import WeightedRrfFusion
from app.rag.rewrite.models import RewriteResult


def chunk(chunk_id: UUID, score: float, doc_id: int) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        text=f"chunk-{doc_id}",
        score=score,
        doc_id=doc_id,
        doc_name=f"doc-{doc_id}",
        source_type="file",
    )


class FakeChannel:
    def __init__(
        self,
        channel_type: SearchChannelType,
        chunks: list[RetrievedChunk] | None = None,
        *,
        delay: float = 0,
        fails: bool = False,
    ) -> None:
        self.channel_type = channel_type
        self.channel_name = str(channel_type)
        self.chunks = chunks or []
        self.delay = delay
        self.fails = fails

    async def search(self, context: SearchContext) -> SearchChannelResult:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fails:
            raise RuntimeError("channel failed")
        return SearchChannelResult(
            self.channel_type,
            self.channel_name,
            tuple(self.chunks),
        )


@pytest.mark.parametrize(
    "budget",
    [
        (0, 40, 10),
        (20, 10, 10),
        (20, 40, 0),
        (20, 40, 41),
    ],
)
def test_retrieval_budget_rejects_invalid_values(budget: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError):
        RetrievalBudget(*budget)


async def test_single_channel_preserves_native_scores_and_context_limit() -> None:
    chunks = [chunk(uuid4(), 0.9, 1), chunk(uuid4(), 0.8, 2)]
    budget = RetrievalBudget(2, 2, 1)
    engine = MultiChannelRetrievalEngine(
        [FakeChannel(SearchChannelType.VECTOR, chunks)],
        budget,
        WeightedRrfFusion(candidate_limit=2),
    )

    results = await engine.retrieve("question")

    assert [(item.doc_id, item.score) for item in results] == [(1, 0.9)]


async def test_weighted_rrf_deduplicates_and_rewards_cross_channel_hits() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    vector = FakeChannel(
        SearchChannelType.VECTOR,
        [chunk(a, 0.9, 1), chunk(a, 0.8, 1), chunk(b, 0.7, 2)],
    )
    keyword = FakeChannel(
        SearchChannelType.KEYWORD,
        [chunk(b, 10.0, 2), chunk(c, 9.0, 3)],
    )
    budget = RetrievalBudget(3, 3, 3)
    engine = MultiChannelRetrievalEngine(
        [vector, keyword],
        budget,
        WeightedRrfFusion(
            rrf_k=20,
            candidate_limit=3,
            weights={
                SearchChannelType.VECTOR: 1.0,
                SearchChannelType.KEYWORD: 1.0,
            },
        ),
    )

    results = await engine.retrieve("question")

    assert [item.id for item in results] == [b, a, c]
    assert results[0].score == pytest.approx(1 / 22 + 1 / 21)
    assert results[1].score == pytest.approx(1 / 21)
    assert results[2].score == pytest.approx(1 / 22)


async def test_channel_timeout_and_failure_degrade_without_losing_success() -> None:
    expected = chunk(uuid4(), 0.95, 7)
    budget = RetrievalBudget(1, 1, 1)
    engine = MultiChannelRetrievalEngine(
        [
            FakeChannel(SearchChannelType.VECTOR, [expected]),
            FakeChannel(SearchChannelType.KEYWORD, fails=True),
            FakeChannel(SearchChannelType.GRAPH, delay=0.1),
        ],
        budget,
        WeightedRrfFusion(candidate_limit=1),
        timeout_ms=10,
    )

    results = await engine.retrieve("question")

    assert results == [expected]


async def test_vector_channel_passes_recall_budget_to_retriever() -> None:
    expected = chunk(uuid4(), 0.8, 9)

    class FakeRetriever:
        def __init__(self) -> None:
            self.call: tuple[str, int | None] | None = None

        async def retrieve(
            self, question: str, *, limit: int | None = None
        ) -> list[RetrievedChunk]:
            self.call = (question, limit)
            return [expected]

    retriever = FakeRetriever()
    channel = VectorSearchChannel(retriever)
    context = SearchContext("original", "rewritten", RetrievalBudget(20, 40, 10))

    result = await channel.search(context)

    assert retriever.call == ("rewritten", 20)
    assert result.channel_type is SearchChannelType.VECTOR
    assert result.chunks == (expected,)


async def test_vector_channel_passes_intent_scope() -> None:
    class ScopedRetriever:
        def __init__(self) -> None:
            self.options = None

        async def retrieve(self, question: str, **options):
            self.options = options
            return []

    retriever = ScopedRetriever()
    context = SearchContext(
        "original",
        "rewritten",
        RetrievalBudget(20, 40, 10),
        scope=RetrievalScope(("kb-a", "kb-b"), 8),
    )
    await VectorSearchChannel(retriever).search(context)
    assert retriever.options == {
        "limit": 8,
        "collections": ("kb-a", "kb-b"),
        "supplement_ratio": 0.25,
    }


async def test_engine_passes_rewritten_question_to_channels() -> None:
    expected = chunk(uuid4(), 0.8, 11)

    class Rewriter:
        async def rewrite_with_split(self, question: str) -> RewriteResult:
            assert question == "原问题"
            return RewriteResult("归一化问题", ("归一化问题？",))

    class CapturingChannel(FakeChannel):
        def __init__(self) -> None:
            super().__init__(SearchChannelType.VECTOR)
            self.question = ""

        async def search(self, context: SearchContext) -> SearchChannelResult:
            self.question = context.main_question
            assert context.sub_questions == ("归一化问题？",)
            return SearchChannelResult(self.channel_type, self.channel_name, (expected,))

    channel = CapturingChannel()
    engine = MultiChannelRetrievalEngine(
        [channel],
        RetrievalBudget(1, 1, 1),
        WeightedRrfFusion(candidate_limit=1),
        rewriter=Rewriter(),
    )

    assert await engine.retrieve("原问题") == [expected]
    assert channel.question == "归一化问题"


async def test_reranker_runs_after_fusion_and_before_context_limit() -> None:
    first = chunk(uuid4(), 0.9, 1)
    second = chunk(uuid4(), 0.8, 2)

    class ReverseReranker:
        async def rerank(self, query, candidates, top_n):
            assert query == "question"
            assert candidates == [first, second]
            assert top_n == 1
            return list(reversed(candidates))

    engine = MultiChannelRetrievalEngine(
        [FakeChannel(SearchChannelType.VECTOR, [first, second])],
        RetrievalBudget(2, 2, 1),
        WeightedRrfFusion(candidate_limit=2),
        reranker=ReverseReranker(),
    )
    assert await engine.retrieve("question") == [second]


async def test_reranker_failure_preserves_fusion_order() -> None:
    first = chunk(uuid4(), 0.9, 1)
    second = chunk(uuid4(), 0.8, 2)

    class FailingReranker:
        async def rerank(self, query, candidates, top_n):
            raise RuntimeError("rerank offline")

    engine = MultiChannelRetrievalEngine(
        [FakeChannel(SearchChannelType.VECTOR, [first, second])],
        RetrievalBudget(2, 2, 1),
        WeightedRrfFusion(candidate_limit=2),
        reranker=FailingReranker(),
    )
    assert await engine.retrieve("question") == [first]


async def test_metadata_enrichment_runs_after_rerank_and_context_limit() -> None:
    first_id, second_id = uuid4(), uuid4()
    first = RetrievedChunk(first_id, "first", 0.9)
    second = RetrievedChunk(second_id, "second", 0.8)

    class ReverseReranker:
        async def rerank(self, query, candidates, top_n):
            return [second]

    class Resolver:
        def __init__(self) -> None:
            self.chunk_ids = ()

        async def resolve_chunks(self, chunk_ids):
            self.chunk_ids = chunk_ids
            return {
                second_id: DocumentMetadata(
                    22, "说明书", "file", "pdf", chunk_index=3
                )
            }

        async def resolve_documents(self, doc_ids):
            return {}

    resolver = Resolver()
    engine = MultiChannelRetrievalEngine(
        [FakeChannel(SearchChannelType.VECTOR, [first, second])],
        RetrievalBudget(2, 2, 1),
        WeightedRrfFusion(candidate_limit=2),
        reranker=ReverseReranker(),
        metadata_enricher=MetadataEnrichmentPostProcessor(resolver),
    )

    results = await engine.retrieve("question")

    assert resolver.chunk_ids == (second_id,)
    assert results == [
        RetrievedChunk(
            second_id,
            "second",
            0.8,
            22,
            "说明书",
            "file",
            3,
            "pdf",
        )
    ]


async def test_metadata_enrichment_failure_preserves_results() -> None:
    expected = RetrievedChunk(uuid4(), "web", 0.9, source_type="web")

    class FailingResolver:
        async def resolve_chunks(self, chunk_ids):
            raise RuntimeError("database unavailable")

        async def resolve_documents(self, doc_ids):
            raise AssertionError("not reached")

    engine = MultiChannelRetrievalEngine(
        [FakeChannel(SearchChannelType.WEB, [expected])],
        RetrievalBudget(1, 1, 1),
        WeightedRrfFusion(candidate_limit=1),
        metadata_enricher=MetadataEnrichmentPostProcessor(FailingResolver()),
    )

    assert await engine.retrieve("question") == [expected]
