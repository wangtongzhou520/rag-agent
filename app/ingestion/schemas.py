"""Pipeline REST 契约与引擎领域对象。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.chunk.models import Chunk, EmbeddedChunk
from app.core.ingest.models import VectorTarget
from app.core.parser.models import ParsedDocument


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class IngestionNodeType(StrEnum):
    FETCHER = "fetcher"
    PARSER = "parser"
    ENHANCER = "enhancer"
    CHUNKER = "chunker"
    ENRICHER = "enricher"
    INDEXER = "indexer"


class SourceType(StrEnum):
    FILE = "file"
    URL = "url"
    FEISHU = "feishu"


class NodeConfig(CamelModel):
    id: int | None = None
    node_id: str = Field(alias="nodeId", min_length=1, max_length=64)
    node_type: IngestionNodeType = Field(alias="nodeType")
    settings: dict[str, Any] = Field(default_factory=dict)
    condition: dict | str | bool | None = None
    next_node_id: str | None = Field(default=None, alias="nextNodeId", max_length=64)

    @field_validator("node_id", "next_node_id")
    @classmethod
    def normalize_id(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class PipelineCreate(CamelModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    nodes: list[NodeConfig] = Field(min_length=1)


class PipelineUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    nodes: list[NodeConfig] | None = None


class DocumentSource(CamelModel):
    type: SourceType
    location: str | None = Field(default=None, max_length=1024)
    file_name: str | None = Field(default=None, alias="fileName", max_length=256)
    credentials: dict[str, str] = Field(default_factory=dict)


class TaskCreate(CamelModel):
    pipeline_id: int = Field(alias="pipelineId")
    source: DocumentSource
    metadata: dict[str, Any] = Field(default_factory=dict)
    vector_space_id: str | None = Field(default=None, alias="vectorSpaceId", max_length=64)


@dataclass(slots=True)
class NodeLog:
    node_id: str
    node_type: str
    status: str
    duration_ms: int
    message: str
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IngestionContext:
    task_id: int
    pipeline_id: int
    source: DocumentSource
    metadata: dict[str, Any]
    vector_target: VectorTarget | None
    raw_bytes: bytes | None = None
    mime_type: str | None = None
    parsed: ParsedDocument | None = None
    raw_text: str = ""
    enhanced_text: str = ""
    keywords: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    embedded_chunks: list[EmbeddedChunk] = field(default_factory=list)
    logs: list[NodeLog] = field(default_factory=list)
    error: str | None = None

