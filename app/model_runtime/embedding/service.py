"""EmbeddingService 协议与路由实现（docs/04 §7.1）。

候选顺序 = defaultModel 置顶 + (priority, id) 排序，无档位；通用 fallback + 熔断
复用 ModelRoutingExecutor。指定 model_id 的调用不做重试降级：候选列表只含该
target，id 不存在直接抛错。
"""

from collections.abc import Mapping
from typing import Protocol

from app.framework.exceptions import RemoteException
from app.framework.logging import get_logger
from app.model_runtime.embedding.base import EmbeddingClient
from app.model_runtime.routing import (
    ModelCandidate,
    ModelHealthStore,
    ModelRoutingExecutor,
    ModelSelector,
)

logger = get_logger(__name__)


class EmbeddingService(Protocol):
    async def embed(self, text: str, model_id: str | None = None) -> list[float]: ...
    async def embed_batch(
        self, texts: list[str], model_id: str | None = None
    ) -> list[list[float]]: ...


class RoutingEmbeddingService:
    def __init__(
        self,
        selector: ModelSelector,
        health_store: ModelHealthStore,
        clients: Mapping[str, EmbeddingClient],
        candidates: list[ModelCandidate],
        default_model: str | None = None,
    ) -> None:
        self._selector = selector
        self._clients = dict(clients)
        self._candidates = {candidate.id: candidate for candidate in candidates}
        self._candidate_list = list(candidates)
        self._default_model = default_model
        self._executor = ModelRoutingExecutor(health_store, self._clients)

    async def embed(self, text: str, model_id: str | None = None) -> list[float]:
        vectors = await self.embed_batch([text], model_id)
        return vectors[0]

    async def embed_batch(
        self, texts: list[str], model_id: str | None = None
    ) -> list[list[float]]:
        targets = await self._targets(model_id)
        return await self._executor.execute_with_fallback(
            targets,
            lambda client, target: client.embed(texts, target),
            "Embedding",
        )

    async def _targets(self, model_id: str | None) -> list:
        if model_id is not None:
            candidate = self._candidates.get(model_id)
            if candidate is None or not candidate.enabled:
                raise RemoteException(f"Embedding 模型不可用: {model_id}")
            # 指定 modelId：不做重试降级，候选列表只含该 target
            return await self._selector.select_candidates([candidate])
        return await self._selector.select_candidates(
            self._candidate_list, default_model=self._default_model
        )
