"""固定入库内核的输入输出类型。"""

from dataclasses import dataclass, field

from app.core.chunk.models import Chunk, ChunkBudget
from app.framework.exceptions import ClientException


@dataclass(frozen=True, slots=True)
class DocumentRef:
    doc_id: int
    kb_id: int
    filename: str | None = None


@dataclass(frozen=True, slots=True)
class VectorTarget:
    partition: str
    embedding_model: str
    dimension: int

    def __post_init__(self) -> None:
        if not self.partition.strip():
            raise ClientException("向量分区不能为空")
        if not self.embedding_model.strip():
            raise ClientException("Embedding 模型不能为空")
        if self.dimension <= 0:
            raise ClientException("向量维度必须大于 0")


@dataclass(frozen=True, slots=True)
class IngestionSpec:
    version: int = 2
    parse_profile: str = "fast"
    budget: ChunkBudget = field(default_factory=ChunkBudget)

    @classmethod
    def from_dict(cls, raw: dict | None) -> "IngestionSpec":
        raw = raw or {}
        budget_raw = raw.get("budget") or {}
        max_chars = budget_raw.get("maxChars", budget_raw.get("max_chars", 1024))
        return cls(
            version=int(raw.get("version", 2)),
            parse_profile=str(raw.get("parseProfile", raw.get("parse_profile", "fast"))),
            budget=ChunkBudget(
                max_chars=None if max_chars == -1 else int(max_chars),
                overlap_chars=int(
                    budget_raw.get("overlapChars", budget_raw.get("overlap_chars", 128))
                ),
                rows_per_chunk=int(
                    budget_raw.get("rowsPerChunk", budget_raw.get("rows_per_chunk", 50))
                ),
                tolerance_factor=int(
                    budget_raw.get(
                        "toleranceFactor", budget_raw.get("tolerance_factor", 3)
                    )
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class IngestionTimings:
    parse_ms: int
    chunk_ms: int
    embed_ms: int
    persist_ms: int

    @property
    def total_ms(self) -> int:
        return self.parse_ms + self.chunk_ms + self.embed_ms + self.persist_ms


@dataclass(frozen=True, slots=True)
class IngestionOutcome:
    mime_type: str
    parser_type: str
    block_count: int
    chunks: tuple[Chunk, ...]
    timings: IngestionTimings
