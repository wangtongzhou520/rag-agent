"""M3 意图歧义引导。"""

from app.model_runtime.routing import Tier
from app.rag.intent.guidance import IntentGuidanceService, ModelAmbiguityChecker
from app.rag.intent.node import IntentNode, NodeScore, SubQuestionIntent


def score(node_id: int, name: str, value: float) -> NodeScore:
    node = IntentNode(node_id, f"topic.{node_id}", name, 2, full_path=f"产品 > {name}")
    return NodeScore(node, value)


def path_score(node_id: int, path: str, value: float) -> NodeScore:
    node = IntentNode(
        node_id,
        f"topic.{node_id}",
        path.rsplit(" > ", 1)[-1],
        2,
        full_path=path,
    )
    return NodeScore(node, value)


async def test_close_kb_scores_trigger_guidance() -> None:
    intents = [
        SubQuestionIntent(
            "怎么配置",
            (score(1, "标准版", 0.9), score(2, "企业版", 0.82)),
        )
    ]
    decision = await IntentGuidanceService().detect("怎么配置", intents)
    assert decision.required is True
    assert "1) 产品 > 标准版" in decision.message
    assert "2) 产品 > 企业版" in decision.message


async def test_clear_winner_or_explicit_name_skips_guidance() -> None:
    service = IntentGuidanceService()
    clear = [SubQuestionIntent("怎么配置", (score(1, "标准版", 0.9), score(2, "企业版", 0.4)))]
    explicit = [SubQuestionIntent("企业版怎么配置", (score(1, "标准版", 0.9), score(2, "企业版", 0.85)))]
    assert (await service.detect("怎么配置", clear)).required is False
    assert (await service.detect("企业版怎么配置", explicit)).required is False


async def test_topics_in_same_category_do_not_trigger_false_ambiguity() -> None:
    intents = [
        SubQuestionIntent(
            "怎么操作",
            (
                path_score(1, "产品 > 标准版 > 安装", 0.9),
                path_score(2, "产品 > 标准版 > 升级", 0.85),
            ),
        )
    ]

    assert (await IntentGuidanceService().detect("怎么操作", intents)).required is False


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.requests = []

    async def chat(self, request, tier=None) -> str:
        self.requests.append((request, tier))
        return self.response


async def test_middle_ratio_uses_fast_model_second_check() -> None:
    llm = FakeLLM('{"ambiguous": false, "category_ids": [1], "reason": "明确"}')
    service = IntentGuidanceService(checker=ModelAmbiguityChecker(llm))
    intents = [
        SubQuestionIntent(
            "怎么配置",
            (score(1, "标准版", 0.9), score(2, "企业版", 0.7)),
        )
    ]

    decision = await service.detect("怎么配置", intents)

    assert decision.required is False
    assert len(llm.requests) == 1
    request, tier = llm.requests[0]
    assert tier is Tier.FAST
    assert request.temperature == 0.1
    assert request.top_p == 0.3


async def test_second_check_invalid_output_conservatively_requests_guidance() -> None:
    checker = ModelAmbiguityChecker(FakeLLM("not-json"))
    service = IntentGuidanceService(checker=checker)
    intents = [
        SubQuestionIntent(
            "怎么配置",
            (score(1, "标准版", 0.9), score(2, "企业版", 0.7)),
        )
    ]

    assert (await service.detect("怎么配置", intents)).required is True
