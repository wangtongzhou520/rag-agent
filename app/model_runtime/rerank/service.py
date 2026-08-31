"""Rerank 候选路由与 noop fallback。"""

from collections.abc import Mapping

from app.model_runtime.rerank.base import RerankClient
from app.model_runtime.routing import (
    ModelCandidate,
    ModelHealthStore,
    ModelRoutingExecutor,
    ModelSelector,
)
from app.rag.retrieval.models import RetrievedChunk


class RoutingRerankService:
    def __init__(
        self,
        selector: ModelSelector,
        health_store: ModelHealthStore,
        clients: Mapping[str, RerankClient],
        candidates: list[ModelCandidate],
        default_model: str | None = None,
    ) -> None:
        self._selector = selector
        self._clients = dict(clients)
        self._candidates = candidates
        self._default_model = default_model
        self._executor = ModelRoutingExecutor(health_store, self._clients)

    async def rerank(
        self, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        targets = await self._selector.select_candidates(
            self._candidates, default_model=self._default_model
        )
        return await self._executor.execute_with_fallback(
            targets,
            lambda client, target: client.rerank(
                query, candidates, top_n, target
            ),
            "Rerank",
        )
