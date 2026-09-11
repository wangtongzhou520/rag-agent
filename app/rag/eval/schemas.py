"""纯检索评测接口契约。"""

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
    mcp_context: str = Field(alias="mcpContext")
    has_mcp_success: bool = Field(alias="hasMcpSuccess")
    needs_clarification: bool = Field(alias="needsClarification")
    has_mcp_failure: bool = Field(alias="hasMcpFailure")
    has_kb: bool = Field(alias="hasKb")
    sub_intents: list[str] = Field(alias="subIntents")
    intent_leaf_ids: list[str | None] = Field(alias="intentLeafIds")
    latency_ms: int = Field(alias="latencyMs")
