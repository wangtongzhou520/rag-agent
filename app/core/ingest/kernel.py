"""不可换序的五步固定入库内核。"""

import time
from typing import Protocol

from app.core.chunk.models import Chunk, EmbeddedChunk
from app.core.chunk.service import ChunkingService
from app.core.ingest.models import (
    DocumentRef,
    IngestionOutcome,
    IngestionSpec,
    IngestionTimings,
    VectorTarget,
)
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.registry import ParserRegistry
from app.framework.exceptions import ClientException, ServiceException
from app.model_runtime.embedding.service import EmbeddingService


class ChunkIndexWriter(Protocol):
    async def replace_document(
        self,
        target: VectorTarget,
        document: DocumentRef,
        chunks: list[EmbeddedChunk],
    ) -> None: ...


class ChunkEmbeddingService:
    def __init__(self, embedding: EmbeddingService) -> None:
        self._embedding = embedding

    async def embed(
        self, chunks: list[Chunk], target: VectorTarget
    ) -> list[EmbeddedChunk]:
        vectors = await self._embedding.embed_batch(
            [chunk.embedding_text for chunk in chunks],
            model_id=target.embedding_model,
        )
        if len(vectors) != len(chunks):
            raise ServiceException("向量结果条数与分块不符")
        embedded = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if not vector or len(vector) != target.dimension:
                raise ServiceException(
                    f"Embedding 模型 {target.embedding_model} 返回维度 {len(vector)}，"
                    f"要求 {target.dimension}，分区 {target.partition}"
                )
            embedded.append(EmbeddedChunk(chunk, tuple(float(item) for item in vector)))
        return embedded


class DefaultIngestionKernel:
    def __init__(
        self,
        detector: MimeTypeDetector,
        registry: ParserRegistry,
        chunking: ChunkingService,
        embedding: ChunkEmbeddingService,
        writer: ChunkIndexWriter,
    ) -> None:
        self._detector = detector
        self._registry = registry
        self._chunking = chunking
        self._embedding = embedding
        self._writer = writer

    async def run(
        self,
        document: DocumentRef,
        data: bytes,
        spec: IngestionSpec,
        target: VectorTarget,
    ) -> IngestionOutcome:
        mime = self._detector.detect(data, document.filename)

        started = time.perf_counter()
        parser = self._registry.require(mime, spec.parse_profile)
        parsed = parser.parse_structured(
            data,
            mime,
            {"sourceFile": document.filename, "documentId": document.doc_id},
        )
        parse_ms = _elapsed_ms(started)

        started = time.perf_counter()
        chunks = self._chunking.chunk(parsed.blocks, spec.budget)
        if not chunks:
            raise ClientException("分块结果为空")
        chunk_ms = _elapsed_ms(started)

        started = time.perf_counter()
        embedded = await self._embedding.embed(chunks, target)
        embed_ms = _elapsed_ms(started)

        started = time.perf_counter()
        await self._writer.replace_document(target, document, embedded)
        persist_ms = _elapsed_ms(started)

        return IngestionOutcome(
            mime_type=mime,
            parser_type=parser.name,
            block_count=len(parsed.blocks),
            chunks=tuple(chunks),
            timings=IngestionTimings(parse_ms, chunk_ms, embed_ms, persist_ms),
        )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
