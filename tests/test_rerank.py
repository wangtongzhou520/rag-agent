"""百炼 Rerank Client 与 noop fallback。"""

import json
from uuid import uuid4

import httpx

from app.model_runtime.http import HttpClientFactory
from app.model_runtime.rerank.base import BaiLianRerankClient, NoopRerankClient
from app.model_runtime.rerank.service import RoutingRerankService
from app.model_runtime.routing import (
    ModelCandidate,
    ModelHealthStore,
    ModelSelector,
    ModelTarget,
)
from app.rag.retrieval.models import RetrievedChunk


def chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(uuid4(), "文档一", 0.9, 1, "一", "file"),
        RetrievedChunk(uuid4(), "文档二", 0.8, 2, "二", "file"),
    ]


class MockHttpFactory(HttpClientFactory):
    def __init__(self, handler) -> None:
        super().__init__()
        self._mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def derive(self, timeout_ms: int | None) -> httpx.AsyncClient:
        return self._mock


async def test_bailian_client_sends_documents_and_uses_result_indexes() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.5},
                ]
            },
        )

    client = BaiLianRerankClient(
        MockHttpFactory(handler), "https://unused.example", "sk-test"
    )
    target = ModelTarget(
        ModelCandidate(
            "rerank",
            "bailian",
            "qwen3-rerank",
            url="https://example.com/reranks",
        )
    )
    values = chunks()
    result = await client.rerank("查询", values, 2, target)
    assert result == [values[1], values[0]]
    assert seen == {
        "model": "qwen3-rerank",
        "query": "查询",
        "documents": ["文档一", "文档二"],
        "top_n": 2,
    }


async def test_routing_falls_back_to_noop() -> None:
    class FailingClient:
        async def rerank(self, query, candidates, top_n, target):
            raise RuntimeError("offline")

    candidates = [
        ModelCandidate("real", "bailian", "qwen3-rerank", priority=1),
        ModelCandidate("noop", "noop", "noop", priority=100),
    ]
    service = RoutingRerankService(
        ModelSelector({}, {}),
        ModelHealthStore(),
        {"bailian": FailingClient(), "noop": NoopRerankClient()},
        candidates,
        "real",
    )
    values = chunks()
    assert await service.rerank("查询", values, 1) == values[:1]
