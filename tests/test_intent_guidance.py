"""M3 意图歧义引导。"""

from app.rag.intent.guidance import IntentGuidanceService
from app.rag.intent.node import IntentNode, NodeScore, SubQuestionIntent


def score(node_id: int, name: str, value: float) -> NodeScore:
    node = IntentNode(node_id, f"topic.{node_id}", name, 2, full_path=f"产品 > {name}")
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
