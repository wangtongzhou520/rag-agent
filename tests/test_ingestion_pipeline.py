"""可编排 Pipeline 状态、条件和数据模型契约测试。"""

from typing import cast

import httpx
import pytest
from fastapi.routing import APIRoute

from app.core.chunk.service import ChunkingService
from app.core.ingest.kernel import ChunkEmbeddingService
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.registry import build_default_registry
from app.framework.db import Base
from app.framework.exceptions import ClientException
from app.ingestion.api import router
from app.ingestion.engine.condition import ConditionEvaluator
from app.ingestion.engine.engine import IngestionEngine
from app.ingestion.schemas import DocumentSource, IngestionContext, NodeConfig
from app.model_runtime.chat.service import LLMService
from app.model_runtime.embedding.service import EmbeddingService
from app.system.auth.deps import require_admin


class UnusedEmbedding:
    async def embed_batch(self, texts, model_id=None):
        raise AssertionError("embedding should not be called")


class UnusedLLM:
    async def chat(self, request, tier=None, preferred_model_id=None):
        raise AssertionError("llm should not be called")


def _engine() -> IngestionEngine:
    return IngestionEngine(
        MimeTypeDetector(),
        build_default_registry(),
        ChunkingService(),
        ChunkEmbeddingService(cast(EmbeddingService, UnusedEmbedding())),
        cast(LLMService, UnusedLLM()),
        httpx.AsyncClient(),
        lambda _: _noop(),
    )


async def _noop() -> None:
    return None


def test_pipeline_tables_and_route_guards_are_registered() -> None:
    assert {
        "t_ingestion_pipeline",
        "t_ingestion_pipeline_node",
        "t_ingestion_task",
        "t_ingestion_task_node",
    }.issubset(Base.metadata.tables)
    for route in router.routes:
        assert isinstance(route, APIRoute)
        assert require_admin in {dependency.call for dependency in route.dependant.dependencies}


def test_pipeline_orders_single_chain_and_rejects_invalid_graphs() -> None:
    engine = _engine()
    nodes = [
        NodeConfig(nodeId="parse", nodeType="parser"),
        NodeConfig(nodeId="fetch", nodeType="fetcher", nextNodeId="parse"),
    ]
    assert [item.node_id for item in engine.ordered_nodes(nodes)] == ["fetch", "parse"]
    with pytest.raises(ClientException, match="多个起始节点"):
        engine.ordered_nodes(
            [
                NodeConfig(nodeId="a", nodeType="fetcher"),
                NodeConfig(nodeId="b", nodeType="parser"),
            ]
        )
    with pytest.raises(ClientException, match="存在环|未找到起始节点"):
        engine.ordered_nodes(
            [
                NodeConfig(nodeId="a", nodeType="fetcher", nextNodeId="b"),
                NodeConfig(nodeId="b", nodeType="parser", nextNodeId="a"),
            ]
        )


def test_condition_json_dsl_reads_context_fields() -> None:
    context = IngestionContext(
        task_id=1,
        pipeline_id=2,
        source=DocumentSource(type="url", location="https://example.com/a.md"),
        metadata={},
        vector_target=None,
        mime_type="text/markdown",
    )
    evaluator = ConditionEvaluator()
    assert evaluator.evaluate(
        {"field": "source.type", "operator": "eq", "value": "URL"}, context
    )
    assert evaluator.evaluate("mimeType == 'text/markdown'", context)
    assert not evaluator.evaluate({"not": True}, context)


async def test_engine_records_success_skip_and_failure_logs() -> None:
    engine = _engine()
    context = IngestionContext(
        task_id=1,
        pipeline_id=2,
        source=DocumentSource(type="file", fileName="readme.md"),
        metadata={},
        vector_target=None,
        raw_bytes=b"# title\n\ncontent",
    )
    status = await engine.execute(
        [
            NodeConfig(nodeId="fetch", nodeType="fetcher", nextNodeId="skip"),
            NodeConfig(
                nodeId="skip",
                nodeType="enhancer",
                condition=False,
                nextNodeId="parse",
            ),
            NodeConfig(nodeId="parse", nodeType="parser", nextNodeId="index"),
            NodeConfig(nodeId="index", nodeType="indexer"),
        ],
        context,
    )
    assert status == "failed"
    assert [item.status for item in context.logs] == ["success", "skipped", "success", "failed"]
    assert context.raw_text.startswith("# title")
    assert "没有可写入" in (context.error or "")
    await engine._http.aclose()
