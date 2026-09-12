"""检索评测与批次报告接口契约。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvalResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    retrieved_doc_ids: list[str] = Field(alias="retrievedDocIds")
    retrieved_chunk_ids: list[str] = Field(alias="retrievedChunkIds")
    retrieved_contexts: list[str] = Field(alias="retrievedContexts")
    retrieved_scores: list[float] = Field(alias="retrievedScores")
    retrieved_context_doc_ids: list[str | None] = Field(
        alias="retrievedContextDocIds"
    )
    retrieval_collections: list[str] = Field(alias="retrievalCollections")
    answer: str | None = None
    answer_latency_ms: int | None = Field(default=None, alias="answerLatencyMs")
    mcp_context: str = Field(alias="mcpContext")
    has_mcp_success: bool = Field(alias="hasMcpSuccess")
    needs_clarification: bool = Field(alias="needsClarification")
    has_mcp_failure: bool = Field(alias="hasMcpFailure")
    has_kb: bool = Field(alias="hasKb")
    sub_intents: list[str] = Field(alias="subIntents")
    intent_leaf_ids: list[str | None] = Field(alias="intentLeafIds")
    latency_ms: int = Field(alias="latencyMs")


class EvalReportCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str | None = Field(default=None, max_length=128)
    dataset: str = Field(min_length=1, max_length=255)
    collections: list[str] = Field(min_length=1, max_length=32)
    include_answers: bool = Field(default=False, alias="includeAnswers")
    thresholds: dict[str, Any]
    summary: dict[str, Any]
    cases: list[dict[str, Any]] = Field(max_length=1000)
