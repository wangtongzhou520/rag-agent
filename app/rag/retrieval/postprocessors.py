"""M3 检索后处理：通道内去重与加权 RRF。"""

from dataclasses import replace

from app.rag.retrieval.models import (
    RetrievedChunk,
    SearchChannelResult,
    SearchChannelType,
)


class DeduplicationPostProcessor:
    order = 1

    def process(self, results: list[SearchChannelResult]) -> list[SearchChannelResult]:
        processed = []
        for result in results:
            seen: set[str] = set()
            chunks = []
            for chunk in result.chunks:
                if chunk.key in seen:
                    continue
                seen.add(chunk.key)
                chunks.append(chunk)
            processed.append(replace(result, chunks=tuple(chunks)))
        return processed


class WeightedRrfFusion:
    order = 5

    def __init__(
        self,
        *,
        rrf_k: int = 20,
        weights: dict[SearchChannelType, float] | None = None,
        candidate_limit: int = 40,
    ) -> None:
        if rrf_k < 0:
            raise ValueError("rrf_k 不能小于 0")
        if candidate_limit <= 0:
            raise ValueError("candidate_limit 必须大于 0")
        self._rrf_k = rrf_k
        self._weights = weights or {}
        self._candidate_limit = candidate_limit

    def process(self, results: list[SearchChannelResult]) -> list[RetrievedChunk]:
        active = [result for result in results if result.chunks]
        if not active:
            return []
        if len(active) == 1:
            return list(active[0].chunks[: self._candidate_limit])

        scores: dict[str, float] = {}
        representatives: dict[str, RetrievedChunk] = {}
        first_seen: dict[str, int] = {}
        sequence = 0
        for result in active:
            weight = self._weights.get(result.channel_type, 1.0)
            for rank, chunk in enumerate(result.chunks):
                representatives.setdefault(chunk.key, chunk)
                first_seen.setdefault(chunk.key, sequence)
                sequence += 1
                scores[chunk.key] = scores.get(chunk.key, 0.0) + weight / (
                    self._rrf_k + rank + 1
                )

        ordered = sorted(scores, key=lambda key: (-scores[key], first_seen[key]))
        return [
            replace(representatives[key], score=scores[key])
            for key in ordered[: self._candidate_limit]
        ]
