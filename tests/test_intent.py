"""M3 意图树分类与多问题封顶。"""

from app.rag.intent.classifier import DefaultIntentClassifier
from app.rag.intent.node import IntentNode
from app.rag.intent.resolver import IntentResolver
from app.rag.rewrite.models import RewriteResult


def tree() -> list[IntentNode]:
    root = IntentNode(1, "product", "产品", 0)
    root.children = [IntentNode(2, "product.a", "A", 2), IntentNode(3, "product.b", "B", 2)]
    root.full_path = "产品"
    for child in root.children:
        child.full_path = f"产品 > {child.name}"
    return [root]


class FakeLLM:
    async def chat(self, request, tier=None) -> str:
        return '```json\n[{"id":2,"score":0.9},{"id":3,"score":0.8}]\n```'


async def test_classifier_parses_and_filters_scores() -> None:
    result = await DefaultIntentClassifier(FakeLLM(), min_score=0.85).classify("问题", tree())
    assert [item.node.id for item in result] == [2]


class FakeClassifier:
    async def classify(self, question):
        return [
            type("S", (), {"score": 0.9, "node": IntentNode(1, question, question, 2)})(),
            type("S", (), {"score": 0.8, "node": IntentNode(2, question + "2", question, 2)})(),
        ]


async def test_resolver_caps_total_and_keeps_each_question_head() -> None:
    result = await IntentResolver(FakeClassifier()).resolve(RewriteResult("x", ("一", "二")))
    assert [len(item.node_scores) for item in result] == [2, 1]
