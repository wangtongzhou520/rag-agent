"""行内引用标记处理。"""

import re

_CITATION = re.compile(r"\[[1-9]\d*]\(#cite-[1-9]\d*\)")


def strip_citations(content: str) -> str:
    return _CITATION.sub("", content)
