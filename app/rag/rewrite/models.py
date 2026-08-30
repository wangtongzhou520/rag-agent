"""问题改写与术语映射的领域类型。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueryTermMapping:
    source_term: str
    target_term: str
    match_type: int = 1
    priority: int | None = 100
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class RewriteResult:
    rewritten_question: str
    sub_questions: tuple[str, ...]
