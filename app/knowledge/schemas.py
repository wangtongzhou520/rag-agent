"""知识库、文档和 chunk 的 API 模型。"""

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class Page[T](ApiModel):
    records: list[T]
    total: int
    current: int
    size: int


class KnowledgeBaseCreate(ApiModel):
    name: str
    embedding_model: str = Field(alias="embeddingModel")
    collection_name: str = Field(alias="collectionName")


class KnowledgeBaseUpdate(ApiModel):
    name: str
    embedding_model: str = Field(alias="embeddingModel")


class KnowledgeBaseVO(ApiModel):
    id: int
    name: str
    embedding_model: str = Field(alias="embeddingModel")
    collection_name: str = Field(alias="collectionName")


class DocumentUpdate(ApiModel):
    doc_name: str = Field(alias="docName")
    ingestion_spec: dict | None = Field(default=None, alias="ingestionSpec")
    source_location: str | None = Field(default=None, alias="sourceLocation")


class DocumentVO(ApiModel):
    id: int
    kb_id: int = Field(alias="kbId")
    doc_name: str = Field(alias="docName")
    enabled: bool
    chunk_count: int = Field(alias="chunkCount")
    file_type: str | None = Field(alias="fileType")
    mime_type: str | None = Field(alias="mimeType")
    file_size: int | None = Field(alias="fileSize")
    status: str
    source_type: str = Field(alias="sourceType")
    source_location: str | None = Field(alias="sourceLocation")
    ingestion_spec: dict | None = Field(alias="ingestionSpec")


class ChunkUpdate(ApiModel):
    content: str


class BatchEnable(ApiModel):
    chunk_ids: list[str] = Field(alias="chunkIds")


class ChunkVO(ApiModel):
    id: str
    doc_id: int = Field(alias="docId")
    chunk_index: int = Field(alias="chunkIndex")
    content: str
    enabled: bool
