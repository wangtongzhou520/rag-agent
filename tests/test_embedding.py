"""Embedding 运行时测试：路由顺序、指定 modelId 不降级、OpenAI 兼容客户端（docs/04 §7.1/§14）。"""

import json

import httpx
import pytest

from app.framework.exceptions import RemoteException
from app.model_runtime.embedding.base import AbstractOpenAIStyleEmbeddingClient
from app.model_runtime.embedding.service import RoutingEmbeddingService
from app.model_runtime.http import HttpClientFactory, ModelClientException
from app.model_runtime.routing import (
    ModelCandidate,
    ModelHealthStore,
    ModelSelector,
)

CANDIDATES = [
    ModelCandidate("emb-default", "siliconflow", "m-default", dimension=1536, priority=99),
    ModelCandidate("emb-a", "siliconflow", "m-a", dimension=1536, priority=1),
    ModelCandidate("emb-b", "ollama", "m-b", dimension=1536, priority=2),
]


class FakeEmbeddingClient:
    """记录调用并按候选 id 脚本化失败。"""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.calls: list[str] = []

    async def embed(self, texts: list[str], target) -> list[list[float]]:
        self.calls.append(target.id)
        if target.id in self.fail:
            raise RuntimeError(f"{target.id} boom")
        return [[1.0, 0.0] for _ in texts]


def make_service(fail: set[str] | None = None) -> tuple[RoutingEmbeddingService, dict]:
    clients = {"siliconflow": FakeEmbeddingClient(fail), "ollama": FakeEmbeddingClient(fail)}
    selector = ModelSelector({}, {})
    service = RoutingEmbeddingService(
        selector, ModelHealthStore(), clients, CANDIDATES, default_model="emb-default"
    )
    return service, clients


async def test_default_model_first_then_priority() -> None:
    service, clients = make_service()

    await service.embed_batch(["x", "y"])

    assert clients["siliconflow"].calls == ["emb-default"]


async def test_fallback_to_next_candidate_on_failure() -> None:
    service, clients = make_service(fail={"emb-default", "emb-a"})

    vectors = await service.embed_batch(["x"])

    assert vectors == [[1.0, 0.0]]
    assert clients["siliconflow"].calls == ["emb-default", "emb-a"]
    assert clients["ollama"].calls == ["emb-b"]


async def test_explicit_model_id_disables_fallback() -> None:
    service, clients = make_service(fail={"emb-a"})

    with pytest.raises(RemoteException, match="All Embedding model candidates failed"):
        await service.embed("x", model_id="emb-a")
    # 指定 modelId：候选只含该 target，失败即结束
    assert clients["siliconflow"].calls == ["emb-a"]
    assert clients["ollama"].calls == []

    with pytest.raises(RemoteException, match="Embedding 模型不可用: missing"):
        await service.embed("x", model_id="missing")


class MockHttpFactory(HttpClientFactory):
    def __init__(self, handler) -> None:
        super().__init__()
        self._mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    @property
    def base(self) -> httpx.AsyncClient:
        return self._mock

    def derive(self, timeout_ms: int | None) -> httpx.AsyncClient:
        return self._mock


def make_target(model: str = "m", dimension: int | None = 1536):
    from app.model_runtime.routing import ModelTarget

    return ModelTarget(ModelCandidate("id-1", "siliconflow", model, dimension=dimension))


async def test_client_request_body_and_index_ordering() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2]},
                    {"index": 0, "embedding": [0.1]},
                ]
            },
        )

    client = AbstractOpenAIStyleEmbeddingClient(
        MockHttpFactory(handler), "https://api.example.com", "sk-x", {"embedding": "/v1/embeddings"}
    )

    vectors = await client.embed(["a", "b"], make_target())

    assert vectors == [[0.1], [0.2]]
    assert seen[0]["model"] == "m"
    assert seen[0]["dimensions"] == 1536
    assert seen[0]["encoding_format"] == "float"
    assert seen[0]["input"] == ["a", "b"]


async def test_client_batch_splitting_preserves_order() -> None:
    class BatchLimitedClient(AbstractOpenAIStyleEmbeddingClient):
        def max_batch_size(self) -> int:
            return 2

    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches.append(body["input"])
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [float(len(text))]}
                    for i, text in enumerate(body["input"])
                ]
            },
        )

    client = BatchLimitedClient(
        MockHttpFactory(handler), "https://api.example.com", "sk-x", {"embedding": "/v1/embeddings"}
    )

    vectors = await client.embed(["a", "bb", "ccc", "dddd", "eeeee"], make_target())

    assert batches == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert vectors == [[1.0], [2.0], [3.0], [4.0], [5.0]]


async def test_client_count_mismatch_raises_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1]}]})

    client = AbstractOpenAIStyleEmbeddingClient(
        MockHttpFactory(handler), "https://api.example.com", "sk-x", {"embedding": "/v1/embeddings"}
    )

    with pytest.raises(ModelClientException, match="条数"):
        await client.embed(["a", "b"], make_target())


async def test_client_http_error_mapped_by_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow down"})

    client = AbstractOpenAIStyleEmbeddingClient(
        MockHttpFactory(handler), "https://api.example.com", "sk-x", {"embedding": "/v1/embeddings"}
    )

    with pytest.raises(ModelClientException) as exc_info:
        await client.embed(["a"], make_target())
    assert exc_info.value.http_status == 429
