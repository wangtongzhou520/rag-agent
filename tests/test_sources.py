"""M3 来源编号与引用上下文。"""

from uuid import uuid4

from app.rag.retrieval.models import RetrievedChunk
from app.rag.source.assembler import SourcesAssembler
from app.rag.source.citation import CitationContextEnricher, sanitize_attribute


def chunk(doc_id: int, score: float, name: str) -> RetrievedChunk:
    return RetrievedChunk(uuid4(), "内容", score, doc_id, name, "file")


def test_sources_merge_by_doc_and_assign_stable_indexes() -> None:
    assembled = SourcesAssembler().assemble(
        [chunk(2, 0.7, "二"), chunk(1, 0.8, "一"), chunk(2, 0.9, "二")]
    )
    assert [(source.index, source.doc_id) for source in assembled.sources] == [
        (1, "2"),
        (2, "1"),
    ]
    assert assembled.indexes == {"2": 1, "1": 2}


def test_citation_enricher_replaces_or_removes_internal_doc_ids() -> None:
    context = (
        '<content class="kb" data-ragent-doc-id="12">\na\n</content>\n'
        '<content data-ragent-doc-id="missing">\nb\n</content>'
    )
    enriched = CitationContextEnricher().enrich(context, {"12": 3})
    assert '<content class="kb" ref="3">' in enriched
    assert "data-ragent-doc-id" not in enriched
    assert '<content>\nb' in enriched


def test_citation_disabled_removes_all_internal_anchors() -> None:
    value = '<content data-ragent-doc-id="12">'
    assert CitationContextEnricher().enrich(value, {"12": 1}, enabled=False) == "<content>"
    assert sanitize_attribute('12"><script>') == "12script"
