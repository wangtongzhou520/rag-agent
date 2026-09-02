"""M3 意图树分类与多问题封顶。"""

from app.rag.intent.cache import IntentTreeCacheManager
from app.rag.intent.classifier import DefaultIntentClassifier
from app.rag.intent.node import IntentNode, NodeScore, SubQuestionIntent
from app.rag.intent.resolver import IntentResolver
from app.rag.intent.schemas import IntentNodeVO
from app.rag.intent.service import IntentTreeService
from app.rag.retrieval.scope import RetrievalScopeResolver, ScopeQuota
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


def test_scope_resolver_merges_kb_collections_and_top_k() -> None:
    first = IntentNode(
        10,
        "a",
        "A",
        2,
        collection_names=("kb-a", "kb-b"),
        top_k=12,
    )
    second = IntentNode(
        11,
        "b",
        "B",
        2,
        collection_names=("kb-b", "kb-c"),
        top_k=20,
    )
    scope = RetrievalScopeResolver().resolve(
        [SubQuestionIntent("问题", (NodeScore(first, 0.9), NodeScore(second, 0.8)))]
    )
    assert scope.collections == ("kb-a", "kb-b", "kb-c")
    assert scope.top_k == 20


def test_scope_quota_keeps_primary_and_supplement_budget() -> None:
    assert ScopeQuota.split(20, 0.25, directed=True, has_supplement=True) == ScopeQuota(15, 5)
    assert ScopeQuota.split(1, 0.25, directed=True, has_supplement=True) == ScopeQuota(1, 0)
    assert ScopeQuota.split(20, 0.25, directed=False, has_supplement=True) == ScopeQuota(20, 0)


def test_intent_cache_preserves_management_fields() -> None:
    node = IntentNode(
        1,
        "product",
        "产品",
        0,
        kb_id=12,
        enabled=False,
    )
    decoded = IntentTreeCacheManager._decode([IntentTreeCacheManager._encode(node)])
    assert decoded[0].kb_id == 12
    assert decoded[0].enabled is False
    payload = IntentNodeVO.model_validate(decoded[0], from_attributes=True).model_dump(
        by_alias=True
    )
    assert payload["kbId"] == 12
    assert payload["enabled"] is False


async def test_management_tree_requests_disabled_nodes(monkeypatch) -> None:
    requested: list[bool] = []

    async def load_tree(self, *, include_disabled: bool = False):
        requested.append(include_disabled)
        return []

    monkeypatch.setattr(DefaultIntentClassifier, "load_intent_tree", load_tree)
    service = IntentTreeService.__new__(IntentTreeService)
    service._engine = None
    service._cache = None
    assert await service.list_tree() == []
    assert requested == [True]
