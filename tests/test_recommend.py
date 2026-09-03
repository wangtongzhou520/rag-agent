"""推荐追问生成器的模型参数、解析与边界测试。"""

from app.framework.sse import RecommendedQuestionStatus
from app.model_runtime.routing import Tier
from app.rag.recommend import RecommendedQuestionGenerator


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    async def chat(self, request, tier=None, preferred_model_id=None):
        self.calls.append((request, tier))
        return self.response


async def test_generator_uses_fast_tier_and_bounded_grounding() -> None:
    llm = FakeLLM('```json\n["继续问题一？", "继续问题二？"]\n```')
    generator = RecommendedQuestionGenerator(llm)

    result = await generator.generate(
        "原问题",
        "带引用的回答 [1](#cite-1)",
        [{"docName": "手册", "text": "依据" * 4000}],
    )

    request, tier = llm.calls[0]
    assert tier is Tier.FAST
    assert request.thinking is False
    assert request.temperature == 0.7
    assert request.top_p == 0.8
    assert request.max_tokens == 256
    assert "#cite-1" not in request.messages[-1].content
    assert len(request.messages[-1].content) < 14_000
    assert result.status is RecommendedQuestionStatus.SUCCESS
    assert result.questions == ["继续问题一？", "继续问题二？"]


def test_parser_deduplicates_truncates_and_negative_caches_empty_array() -> None:
    long_question = "问" * 220
    result = RecommendedQuestionGenerator.parse(
        f'["相同问题", "相同问题", "  ", "{long_question}", 42]', count=3
    )

    assert result.status is RecommendedQuestionStatus.SUCCESS
    assert result.questions == ["相同问题", "问" * 200]

    empty = RecommendedQuestionGenerator.parse("[]")
    invalid = RecommendedQuestionGenerator.parse('{"question": "不是数组"}')
    assert empty.status is RecommendedQuestionStatus.EMPTY
    assert invalid.status is RecommendedQuestionStatus.FAILED
