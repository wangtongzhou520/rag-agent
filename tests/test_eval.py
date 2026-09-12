"""M5 纯检索评测接口与证据口径。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.routing import NoMatchFound

from app.framework.config import get_settings
from app.main import create_app
from app.rag.eval.answer import EvalAnswerGenerator
from app.rag.eval.router import router
from app.rag.eval.schemas import EvalReportCreate, EvalResponse
from app.rag.eval.service import EvalService
from app.rag.intent.node import IntentKind, IntentNode, NodeScore, SubQuestionIntent
from app.rag.mcp.service import McpEvidence
from app.rag.retrieval.models import RetrievalScope, RetrievedChunk
from app.rag.retrieval.scope import RetrievalScopeResolver
from app.rag.rewrite.models import RewriteResult
from app.system.auth.deps import require_admin
from app.system.auth.models import LoginUser


class FakeRewriter:
    async def rewrite_with_split(
        self, question: str, history: tuple[object, ...] = ()
    ) -> RewriteResult:
        assert history == ()
        return RewriteResult(f"改写：{question}", (question,))


class FakeIntentResolver:
    def __init__(self, intents: list[SubQuestionIntent]) -> None:
        self._intents = intents

    async def resolve(self, rewrite: RewriteResult) -> list[SubQuestionIntent]:
        assert rewrite.sub_questions
        return self._intents


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls = 0
        self.kwargs: dict[str, object] = {}

    async def retrieve(self, *args: object, **kwargs: object) -> list[RetrievedChunk]:
        self.calls += 1
        self.kwargs = kwargs
        return self.chunks


class FakeMcpDispatcher:
    def __init__(self, evidence: list[McpEvidence] | None = None) -> None:
        self.evidence = evidence or []

    async def dispatch(self, intents: list[SubQuestionIntent]) -> list[McpEvidence]:
        return self.evidence


class FakeAnswerGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[RetrievedChunk]]] = []

    async def generate(self, question: str, chunks: list[RetrievedChunk]) -> str:
        self.calls.append((question, chunks))
        return "基于评测上下文的答案"


def _intent(kind: IntentKind, *, node_id: int = 7) -> SubQuestionIntent:
    node = IntentNode(
        id=node_id,
        intent_code=f"intent-{node_id}",
        name="评测意图",
        level=2,
        kind=kind,
    )
    return SubQuestionIntent("子问题", (NodeScore(node, 0.91),))


async def test_eval_answer_generator_reuses_grounded_prompt_without_memory() -> None:
    llm = SimpleNamespace(chat=AsyncMock(return_value="  标准答案  "))
    prompt_resolver = SimpleNamespace(resolve=AsyncMock(return_value="仅根据资料回答"))
    generator = EvalAnswerGenerator(llm, prompt_resolver)  # type: ignore[arg-type]
    chunk = RetrievedChunk(uuid4(), "年假为 10 天。", 0.9, doc_id=11)

    answer = await generator.generate("年假几天？", [chunk])

    assert answer == "标准答案"
    request = llm.chat.await_args.args[0]
    assert request.messages[-1].content == "年假几天？"
    assert "仅根据资料回答" in request.messages[0].content
    assert '<content ref="1">' in request.messages[0].content


async def test_eval_service_deduplicates_chunks_and_preserves_context_doc_slots() -> None:
    chunk = RetrievedChunk(uuid4(), "上下文", 0.9)
    retriever = FakeRetriever([chunk, chunk])
    service = EvalService(
        SimpleNamespace(),  # type: ignore[arg-type]
        FakeRewriter(),
        FakeIntentResolver([_intent(IntentKind.KB)]),  # type: ignore[arg-type]
        retriever,
        RetrievalScopeResolver(),
        FakeMcpDispatcher(),  # type: ignore[arg-type]
    )
    service._resolve_context_doc_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=["FAQ_VAC_001"]
    )

    result = await service.evaluate(
        "  如何办理？  ", collections=("quality-baseline", "quality-baseline")
    )

    assert result.retrieved_chunk_ids == [str(chunk.id)]
    assert result.retrieved_contexts == ["上下文"]
    assert result.retrieved_scores == [0.9]
    assert result.retrieved_context_doc_ids == ["FAQ_VAC_001"]
    assert result.retrieved_doc_ids == ["FAQ_VAC_001"]
    assert result.intent_leaf_ids == ["7"]
    assert result.has_kb is True
    assert result.retrieval_collections == ["quality-baseline"]
    scope = retriever.kwargs["scope"]
    assert isinstance(scope, RetrievalScope)
    assert scope.collections == ("quality-baseline",)
    assert scope.allow_supplement is False
    assert retriever.calls == 1


async def test_eval_service_classifies_mcp_clarification_without_kb_retrieval() -> None:
    retriever = FakeRetriever([])
    service = EvalService(
        SimpleNamespace(),  # type: ignore[arg-type]
        FakeRewriter(),
        FakeIntentResolver([_intent(IntentKind.MCP)]),  # type: ignore[arg-type]
        retriever,
        RetrievalScopeResolver(),
        FakeMcpDispatcher(  # type: ignore[arg-type]
            [McpEvidence("internal/weather", "需要参数：city，请主动向用户询问。")]
        ),
    )

    result = await service.evaluate("天气")

    assert result.needs_clarification is True
    assert result.has_mcp_success is False
    assert result.has_mcp_failure is False
    assert result.has_kb is False
    assert "internal/weather" in result.mcp_context
    assert retriever.calls == 0


async def test_eval_service_generates_answer_without_conversation_side_effects() -> None:
    chunk = RetrievedChunk(uuid4(), "上下文", 0.9)
    generator = FakeAnswerGenerator()
    service = EvalService(
        SimpleNamespace(),  # type: ignore[arg-type]
        FakeRewriter(),
        FakeIntentResolver([_intent(IntentKind.KB)]),  # type: ignore[arg-type]
        FakeRetriever([chunk]),
        RetrievalScopeResolver(),
        FakeMcpDispatcher(),  # type: ignore[arg-type]
        generator,  # type: ignore[arg-type]
    )
    service._resolve_context_doc_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=["doc"]
    )

    result = await service.evaluate("问题", include_answer=True)

    assert result.answer == "基于评测上下文的答案"
    assert result.answer_latency_ms is not None
    assert generator.calls == [("问题", [chunk])]


async def test_eval_router_returns_camel_case_contract() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: LoginUser(
        userId=1, username="admin", role="ADMIN"
    )
    app.state.eval_service = SimpleNamespace(
        evaluate=AsyncMock(
            return_value=EvalResponse(
                retrievedDocIds=[],
                retrievedChunkIds=[],
                retrievedContexts=[],
                retrievedScores=[],
                retrievedContextDocIds=[],
                retrievalCollections=["quality-baseline"],
                mcpContext="",
                hasMcpSuccess=False,
                needsClarification=False,
                hasMcpFailure=False,
                hasKb=False,
                subIntents=["问题"],
                intentLeafIds=[None],
                latencyMs=12,
            )
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/rag/eval",
            params=[
                ("question", "问题"),
                ("collection", " quality-baseline "),
                ("collection", "quality-baseline"),
                ("includeAnswer", "true"),
            ],
        )

    assert response.status_code == 200
    assert response.json()["data"]["latencyMs"] == 12
    assert response.json()["data"]["retrievedContextDocIds"] == []
    app.state.eval_service.evaluate.assert_awaited_once_with(  # type: ignore[union-attr]
        "问题", collections=("quality-baseline",), include_answer=True
    )


async def test_eval_report_router_uses_admin_identity_and_camel_case() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: LoginUser(
        userId=9, username="admin", role="ADMIN"
    )
    app.state.eval_report_service = SimpleNamespace(
        create=AsyncMock(return_value={"reportId": "report-1"}),
        page=AsyncMock(
            return_value={"records": [], "total": 0, "current": 1, "size": 10}
        ),
    )
    payload = {
        "label": "release-candidate",
        "dataset": "evals/datasets/rag_quality.v2.jsonl",
        "collections": ["m5_quality_baseline"],
        "includeAnswers": True,
        "thresholds": {"minHitRate": 0.8},
        "summary": {"docHitRate": 1.0, "thresholdsPassed": True},
        "cases": [],
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/rag/eval/reports", json=payload)
        listed = await client.get("/rag/eval/reports", params={"size": 10})

    assert created.status_code == 200
    assert created.json()["data"]["reportId"] == "report-1"
    assert listed.json()["data"]["records"] == []
    command = app.state.eval_report_service.create.await_args.args[0]
    assert isinstance(command, EvalReportCreate)
    assert command.include_answers is True
    assert app.state.eval_report_service.create.await_args.args[1] == 9


def test_eval_route_is_conditionally_registered(monkeypatch) -> None:
    monkeypatch.setenv("RAGENT_EVAL__ENABLED", "false")
    get_settings.cache_clear()
    disabled = create_app()
    try:
        disabled.url_path_for("evaluate")
    except NoMatchFound:
        pass
    else:
        raise AssertionError("disabled eval route must not be registered")

    monkeypatch.setenv("RAGENT_EVAL__ENABLED", "true")
    get_settings.cache_clear()
    enabled = create_app()
    assert str(enabled.url_path_for("evaluate")) == "/rag/eval"
    get_settings.cache_clear()


def test_eval_doc_name_strips_only_a_real_final_extension() -> None:
    assert EvalService._strip_extension("FAQ_VAC_001.pdf") == "FAQ_VAC_001"
    assert EvalService._strip_extension("FAQ.VAC.001.md") == "FAQ.VAC.001"
    assert EvalService._strip_extension("README") == "README"
    assert EvalService._strip_extension(".env") == ".env"
