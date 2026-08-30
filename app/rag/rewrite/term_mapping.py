"""查询词映射和无模型规则拆分。"""

import re
from collections.abc import Iterable

from app.rag.rewrite.models import QueryTermMapping, RewriteResult


class QueryTermMappingUtil:
    @staticmethod
    def apply_mapping(text: str, mapping: QueryTermMapping) -> str:
        """按精确规则顺序替换；目标词已经存在时跳过，避免重复膨胀。"""
        source = mapping.source_term.strip()
        target = mapping.target_term.strip()
        if mapping.match_type != 1 or not source or not target or source == target:
            return text
        result = text
        offset = 0
        while True:
            index = result.find(source, offset)
            if index < 0:
                return result
            if not result.startswith(target, index):
                result = result[:index] + target + result[index + len(source) :]
                offset = index + len(target)
            else:
                offset = index + len(source)


class QueryTermMappingService:
    def __init__(self, mappings: Iterable[QueryTermMapping] = ()) -> None:
        self._mappings = tuple(mappings)

    def normalize(self, question: str) -> str:
        normalized = question.strip()
        for mapping in self._ordered_mappings():
            if mapping.enabled:
                normalized = QueryTermMappingUtil.apply_mapping(normalized, mapping)
        return normalized

    def _ordered_mappings(self) -> list[QueryTermMapping]:
        return sorted(
            self._mappings,
            key=lambda item: (
                item.priority is not None,
                -(item.priority or 0),
                -len(item.source_term),
            ),
        )


class RuleBasedRewriteService:
    """模型关闭或不可用时的确定性改写兜底。"""

    _SEPARATOR = re.compile(r"[?？。；;\n]+")

    def __init__(self, mappings: QueryTermMappingService | None = None) -> None:
        self._mappings = mappings or QueryTermMappingService()

    async def rewrite_with_split(
        self, question: str, history: Iterable[object] = ()
    ) -> RewriteResult:
        del history
        normalized = self._mappings.normalize(question)
        parts = [part.strip() for part in self._SEPARATOR.split(normalized) if part.strip()]
        sub_questions = tuple(
            part if part.endswith(("?", "？")) else f"{part}？" for part in parts
        ) or (normalized,)
        return RewriteResult(normalized, sub_questions)
