"""文档级来源归并与稳定编号。"""

from dataclasses import dataclass

from app.framework.sse import SourceRef
from app.rag.retrieval.models import RetrievedChunk


@dataclass(frozen=True, slots=True)
class AssembledSources:
    sources: tuple[SourceRef, ...]
    indexes: dict[str, int]


class SourcesAssembler:
    def assemble(self, chunks: list[RetrievedChunk]) -> AssembledSources:
        by_doc: dict[int, RetrievedChunk] = {}
        for chunk in chunks:
            current = by_doc.get(chunk.doc_id)
            if current is None or chunk.score > current.score:
                by_doc[chunk.doc_id] = chunk
        ranked = sorted(by_doc.values(), key=lambda item: (-item.score, item.doc_id))
        indexes = {
            str(chunk.doc_id): index
            for index, chunk in enumerate(ranked, start=1)
        }
        return AssembledSources(
            tuple(chunk.to_source(indexes[str(chunk.doc_id)]) for chunk in ranked),
            indexes,
        )
