"""行内引用标记处理。"""

import re

_CITATION = re.compile(r"\[[1-9]\d*]\(#cite-[1-9]\d*\)")
_DOC_ANCHOR = re.compile(
    r'(?m)^<content([^>]*) data-ragent-doc-id="([^"]*)">$'
)


def strip_citations(content: str) -> str:
    return _CITATION.sub("", content)


class CitationContextEnricher:
    def enrich(
        self, context: str, indexes: dict[str, int], *, enabled: bool = True
    ) -> str:
        def replace(match: re.Match) -> str:
            attributes, doc_id = match.groups()
            index = indexes.get(doc_id) if enabled else None
            reference = f' ref="{index}"' if index is not None else ""
            return f"<content{attributes}{reference}>"

        return _DOC_ANCHOR.sub(replace, context)


def sanitize_attribute(value: object) -> str:
    return re.sub(r'["<>]', "", str(value))
