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
        by_doc: dict[str, RetrievedChunk] = {}
        for chunk in chunks:
            key = chunk.document_key
            current = by_doc.get(key)
            if current is None or chunk.score > current.score:
                by_doc[key] = chunk
        ranked = sorted(
            by_doc.values(),
            key=lambda item: (
                -item.score,
                item.doc_id is None,
                item.doc_id if item.doc_id is not None else item.document_key,
            ),
        )
        indexes = {
            chunk.document_key: index
            for index, chunk in enumerate(ranked, start=1)
        }
        return AssembledSources(
            tuple(chunk.to_source(indexes[chunk.document_key]) for chunk in ranked),
            indexes,
        )
