"""M2 固定入库内核的数据库无关测试。"""

from uuid import UUID

from app.core.chunk.models import ChunkBudget
from app.core.chunk.service import ChunkingService
from app.core.ingest.kernel import ChunkEmbeddingService, DefaultIngestionKernel
from app.core.ingest.models import DocumentRef, IngestionSpec, VectorTarget
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.models import HeadingBlock, ParagraphBlock, Provenance
from app.core.parser.registry import build_default_registry
from app.framework.exceptions import ServiceException


class FakeEmbedding:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.calls = []

    async def embed_batch(self, texts, model_id=None):
        self.calls.append((list(texts), model_id))
        return [[0.1] * self.dimension for _ in texts]


class FakeWriter:
    def __init__(self) -> None:
        self.calls = []

    async def replace_document(self, target, document, chunks):
        self.calls.append((target, document, chunks))


def test_mime_detector_uses_filename_for_markdown() -> None:
    detector = MimeTypeDetector()
    assert detector.detect(b"# title", "readme.md") == "text/markdown"


def test_markdown_parser_and_outline_aware_chunking() -> None:
    registry = build_default_registry()
    parsed = registry.require("text/markdown", "fast").parse_structured(
        "# 标题\n\n正文内容".encode(), "text/markdown", {"sourceFile": "a.md"}
    )
    assert isinstance(parsed.blocks[0], HeadingBlock)
    assert isinstance(parsed.blocks[1], ParagraphBlock)

    chunks = ChunkingService().chunk(
        parsed.blocks, ChunkBudget(max_chars=128, overlap_chars=16)
    )
    assert len(chunks) == 1
    assert chunks[0].content == "正文内容"
    assert chunks[0].embedding_text == "标题\n正文内容"
    assert type(chunks[0].id) is UUID
    assert chunks[0].id.version == 7


def test_chunker_packs_adjacent_blocks_of_the_same_section() -> None:
    blocks = [
        HeadingBlock(1, "第一章"),
        ParagraphBlock("短段落 A。", Provenance("a.md")),
        ParagraphBlock("短段落 B。", Provenance("a.md")),
        ParagraphBlock("短段落 C。", Provenance("a.md")),
    ]

    chunks = ChunkingService().chunk(
        blocks, ChunkBudget(max_chars=128, overlap_chars=0)
    )

    assert len(chunks) == 1
    assert chunks[0].content == "短段落 A。\n\n短段落 B。\n\n短段落 C。"
    assert chunks[0].embedding_text.startswith("第一章\n")
    assert chunks[0].metadata == {"source_file": "a.md"}


def test_chunker_flushes_on_heading_change_and_splits_oversized_block() -> None:
    long_text = "句子。" * 60  # 180 字，超过 128 字预算
    blocks = [
        HeadingBlock(1, "第一章"),
        ParagraphBlock("第一节内容。", Provenance("a.md")),
        HeadingBlock(1, "第二章"),
        ParagraphBlock(long_text, Provenance("a.md")),
    ]

    chunks = ChunkingService().chunk(
        blocks, ChunkBudget(max_chars=128, overlap_chars=16)
    )

    assert next(chunk.outline_path for chunk in chunks) == ("第一章",)
    assert all(chunk.outline_path == ("第二章",) for chunk in chunks[1:])
    assert len(chunks) >= 2
    assert all(len(chunk.content) <= 128 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunker_does_not_pack_across_sheets() -> None:
    blocks = [
        ParagraphBlock("Sheet1 内容", Provenance("book.xlsx", "Sheet1")),
        ParagraphBlock("Sheet2 内容", Provenance("book.xlsx", "Sheet2")),
    ]

    chunks = ChunkingService().chunk(
        blocks, ChunkBudget(max_chars=512, overlap_chars=0)
    )

    assert len(chunks) == 2
    assert chunks[0].metadata == {"source_file": "book.xlsx", "sheet_name": "Sheet1"}
    assert chunks[1].metadata == {"source_file": "book.xlsx", "sheet_name": "Sheet2"}


async def test_kernel_runs_all_steps_and_persists() -> None:
    embedding = FakeEmbedding(3)
    writer = FakeWriter()
    kernel = DefaultIngestionKernel(
        MimeTypeDetector(),
        build_default_registry(),
        ChunkingService(),
        ChunkEmbeddingService(embedding),
        writer,
    )
    target = VectorTarget("kb-1", "emb-1", 3)
    outcome = await kernel.run(
        DocumentRef(1, 2, "a.md"),
        "# 标题\n\n正文".encode(),
        IngestionSpec(budget=ChunkBudget(max_chars=128, overlap_chars=16)),
        target,
    )

    assert outcome.mime_type == "text/markdown"
    assert len(outcome.chunks) == 1
    assert embedding.calls[0][1] == "emb-1"
    assert writer.calls[0][0] == target
    assert writer.calls[0][1].kb_id == 2


async def test_kernel_rejects_wrong_embedding_dimension() -> None:
    kernel = DefaultIngestionKernel(
        MimeTypeDetector(),
        build_default_registry(),
        ChunkingService(),
        ChunkEmbeddingService(FakeEmbedding(2)),
        FakeWriter(),
    )
    try:
        await kernel.run(
            DocumentRef(1, 2, "a.txt"),
            b"plain text",
            IngestionSpec(budget=ChunkBudget(max_chars=128, overlap_chars=16)),
            VectorTarget("kb", "emb", 3),
        )
    except ServiceException as exc:
        assert "返回维度 2" in exc.message
    else:
        raise AssertionError("expected ServiceException")
