"""将 KB 意图合并为检索集合范围。"""

from dataclasses import dataclass

from app.rag.intent.node import IntentKind, SubQuestionIntent
from app.rag.retrieval.models import RetrievalScope


class RetrievalScopeResolver:
    def __init__(self, *, min_score: float = 0.4, confidence_threshold: float = 0.6) -> None:
        self._min_score = min_score
        self._confidence_threshold = confidence_threshold

    def resolve(self, intents: list[SubQuestionIntent]) -> RetrievalScope:
        collections: list[str] = []
        top_ks: list[int] = []
        for sub_intent in intents:
            for score in sub_intent.node_scores:
                node = score.node
                if node.kind != IntentKind.KB or score.score < self._min_score:
                    continue
                collections.extend(node.effective_collection_names())
                if node.top_k and node.top_k > 0:
                    top_ks.append(node.top_k)
        if not collections or not any(
            score.score >= self._confidence_threshold
            for item in intents
            for score in item.node_scores
            if score.node.kind == IntentKind.KB
        ):
            return RetrievalScope()
        return RetrievalScope(
            collections=tuple(dict.fromkeys(collections)),
            top_k=max(top_ks) if top_ks else None,
        )


@dataclass(frozen=True, slots=True)
class ScopeQuota:
    primary: int
    supplement: int

    @classmethod
    def split(
        cls,
        budget: int,
        ratio: float,
        *,
        directed: bool,
        has_supplement: bool,
    ) -> "ScopeQuota":
        if not directed or not has_supplement or ratio <= 0 or budget <= 1:
            return cls(max(0, budget), 0)
        supplement = min(budget - 1, max(1, round(budget * ratio)))
        return cls(budget - supplement, supplement)
