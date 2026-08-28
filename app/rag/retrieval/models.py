"""M1 单通道检索领域类型。"""

from dataclasses import dataclass
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
