"""M2 固定入库内核的数据库无关测试。"""

from uuid import UUID

from app.core.chunk.models import ChunkBudget
from app.core.chunk.service import ChunkingService
from app.core.ingest.kernel import ChunkEmbeddingService, DefaultIngestionKernel
from app.core.ingest.models import DocumentRef, IngestionSpec, VectorTarget
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.models import HeadingBlock, ParagraphBlock
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
