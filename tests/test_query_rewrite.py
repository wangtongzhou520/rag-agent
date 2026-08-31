"""M3 查询词归一化与规则拆分。"""

from app.rag.rewrite.models import QueryTermMapping
from app.rag.rewrite.term_mapping import (
    ModelRewriteService,
    QueryTermMappingService,
    RuleBasedRewriteService,
)


def test_term_mapping_applies_priority_and_skips_existing_target() -> None:
    service = QueryTermMappingService(
        [
            QueryTermMapping("短名", "标准名称", priority=10),
            QueryTermMapping("标准名称", "标准名称（完整版）", priority=5),
            QueryTermMapping("不要替换", "ignored", match_type=2),
        ]
    )

    assert service.normalize("短名和标准名称；不要替换") == (
        "标准名称（完整版）和标准名称（完整版）；不要替换"
    )


async def test_rule_rewrite_splits_mixed_delimiters_and_adds_question_marks() -> None:
    service = RuleBasedRewriteService()

    result = await service.rewrite_with_split("第一问? 第二问；第三问\n")

    assert result.rewritten_question == "第一问? 第二问；第三问"
    assert result.sub_questions == ("第一问？", "第二问？", "第三问？")


async def test_rule_rewrite_empty_input_keeps_single_fallback() -> None:
    result = await RuleBasedRewriteService().rewrite_with_split("   ")

    assert result.sub_questions == ("",)


class FakeLLM:
    async def chat(self, request, tier=None) -> str:
        assert request.temperature == 0.1
        assert request.top_p == 0.3
        return '```json\n{"rewrite":"标准问题","sub_questions":["子问题一？","子问题二？"]}\n```'


async def test_model_rewrite_parses_json_fence_and_normalizes_first() -> None:
    service = ModelRewriteService(
        FakeLLM(),
        QueryTermMappingService([QueryTermMapping("简称", "标准名称")]),
    )
    result = await service.rewrite_with_split("请问简称？")
    assert result.rewritten_question == "标准问题"
    assert result.sub_questions == ("子问题一？", "子问题二？")


class FailingLLM:
    async def chat(self, request, tier=None) -> str:
        raise RuntimeError("offline")


async def test_model_rewrite_failure_falls_back_to_rules() -> None:
    result = await ModelRewriteService(FailingLLM()).rewrite_with_split("第一问；第二问")
    assert result.sub_questions == ("第一问？", "第二问？")
