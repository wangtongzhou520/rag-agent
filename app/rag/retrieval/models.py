"""M3 多通道检索领域类型。"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.framework.sse import SourceRef


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: UUID
    text: str
    score: float
    doc_id: int
    doc_name: str
    source_type: str
    file_type: str | None = None
    url: str | None = None

    @property
    def key(self) -> str:
        """跨通道稳定去重键；当前各存储统一使用 chunk UUID。"""
        return str(self.id)

    def to_source(self, index: int) -> SourceRef:
        return SourceRef(
            index=index,
            doc_id=str(self.doc_id),
            doc_name=self.doc_name,
            source_type=self.source_type,
            file_type=self.file_type,
            url=self.url if self.source_type in {"url", "feishu"} else None,
            excerpt=self.text[:100],
        )


class SearchChannelType(StrEnum):
    VECTOR = "vector"
    KEYWORD = "keyword"
    GRAPH = "graph"
    WEB = "web"


@dataclass(frozen=True, slots=True)
class RetrievalBudget:
    recall_budget: int = 20
    candidate_limit: int = 40
    context_top_k: int = 10

    def __post_init__(self) -> None:
        if self.recall_budget <= 0:
            raise ValueError("recall_budget 必须大于 0")
        if self.candidate_limit < self.recall_budget:
            raise ValueError("candidate_limit 不能小于 recall_budget")
        if not 0 < self.context_top_k <= self.candidate_limit:
            raise ValueError("context_top_k 必须在 1 到 candidate_limit 之间")


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    collections: tuple[str, ...] = ()
    top_k: int | None = None

    @property
    def restricted(self) -> bool:
        return bool(self.collections)


@dataclass(frozen=True, slots=True)
class SearchContext:
    original_question: str
    rewritten_question: str
    budget: RetrievalBudget
    sub_questions: tuple[str, ...] = ()
    scope: RetrievalScope = RetrievalScope()

    @property
    def main_question(self) -> str:
        return self.rewritten_question.strip() or self.original_question


@dataclass(frozen=True, slots=True)
class SearchChannelResult:
    channel_type: SearchChannelType
    channel_name: str
    chunks: tuple[RetrievedChunk, ...] = ()
    latency_ms: int = 0
    metadata: dict | None = None
