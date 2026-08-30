"""分块领域类型。"""

from dataclasses import dataclass, field
from uuid import UUID

from app.framework.exceptions import ClientException
from app.framework.ids import new_native_uuid7


@dataclass(frozen=True, slots=True)
class ChunkBudget:
    max_chars: int | None = 1024
    overlap_chars: int = 128
    rows_per_chunk: int = 50
    tolerance_factor: int = 3

    def __post_init__(self) -> None:
        if self.max_chars is not None and not 128 <= self.max_chars <= 50_000:
            raise ClientException("maxChars 必须在 128 到 50000 之间")
        if self.overlap_chars < 0:
            raise ClientException("overlapChars 不能小于 0")
        if self.max_chars is not None and self.overlap_chars >= self.max_chars:
            raise ClientException("overlapChars 必须小于 maxChars")
        if not 1 <= self.rows_per_chunk <= 1000:
            raise ClientException("rowsPerChunk 必须在 1 到 1000 之间")


@dataclass(frozen=True, slots=True)
class Chunk:
    content: str
    embedding_text: str
    chunk_index: int
    outline_path: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)
    id: UUID = field(default_factory=new_native_uuid7)


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    chunk: Chunk
    vector: tuple[float, ...]
