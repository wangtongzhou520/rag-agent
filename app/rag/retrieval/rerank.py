"""异步 Rerank 后处理与 noop 降级。"""

import asyncio
from typing import Protocol

from app.framework.logging import get_logger
from app.rag.retrieval.models import RetrievedChunk

logger = get_logger(__name__)


class Reranker(Protocol):
    async def rerank(
        self, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]: ...


class NoopReranker:
    async def rerank(
        self, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        del query
        return candidates[:top_n]


class RerankPostProcessor:
    order = 10

    def __init__(self, reranker: Reranker, *, timeout_ms: int = 10_000) -> None:
        if timeout_ms <= 0:
            raise ValueError("rerank timeout_ms 必须大于 0")
        self._reranker = reranker
        self._timeout_seconds = timeout_ms / 1000

    async def process(
        self, query: str, candidates: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        try:
            result = await asyncio.wait_for(
                self._reranker.rerank(query, candidates, top_n),
                timeout=self._timeout_seconds,
            )
            return result[:top_n]
        except TimeoutError:
            logger.warning("Rerank 超时，保留融合排序")
        except Exception:
            logger.exception("Rerank 失败，保留融合排序")
        return candidates[:top_n]
