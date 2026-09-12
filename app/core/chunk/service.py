"""Block-aware 分块与滑窗切分。"""

import re
from collections.abc import Iterable

from app.core.chunk.models import Chunk, ChunkBudget
from app.core.parser.models import (
    Block,
    CodeBlock,
    HeadingBlock,
    ListBlock,
    ParagraphBlock,
    TableBlock,
)


def _render_table(block: TableBlock) -> str:
    rows = [block.headers, *block.rows]
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def render_block(block: Block) -> str:
    if isinstance(block, ParagraphBlock):
        return block.text
    if isinstance(block, TableBlock):
        return _render_table(block)
    if isinstance(block, CodeBlock):
        fence = chr(96) * 3
        language = block.language or ""
        return f"{fence}{language}\n{block.code.rstrip()}\n{fence}"
    if isinstance(block, ListBlock):
        return "\n".join(
            f"{index + 1}. {item}" if block.ordered else f"- {item}"
            for index, item in enumerate(block.items)
        )
    return ""


def split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + max_chars)
        end = hard_end
        if hard_end < len(text):
            window = text[start:hard_end]
            matches = list(re.finditer(r"[\n。！？.!?]\s*", window))
            if matches and matches[-1].end() >= max_chars // 2:
                end = start + matches[-1].end()
        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return parts


class ChunkingService:
    def chunk(self, blocks: Iterable[Block], budget: ChunkBudget) -> list[Chunk]:
        outline: list[str] = []
        sections: list[tuple[tuple[str, ...], dict, list[str]]] = []
        current: tuple[tuple[str, ...], dict, list[str]] | None = None
        for block in blocks:
            if isinstance(block, HeadingBlock):
                level = min(6, max(1, block.level))
                outline[level - 1 :] = [block.text.strip()]
                current = None
                continue
            text = render_block(block).strip()
            if not text:
                continue
            metadata = self._metadata(block)
            path = tuple(outline)
            # 同节同来源的相邻块才允许打包，避免跨章节/跨表把无关内容粘在一起
            if current is None or current[0] != path or current[1] != metadata:
                current = (path, metadata, [])
                sections.append(current)
            current[2].append(text)

        if budget.max_chars is None:
            content = "\n\n".join(
                text for _, _, texts in sections for text in texts
            )
            if not content:
                return []
            path = sections[0][0] if sections else ()
            metadata = sections[0][1] if sections else {}
            return [self._make_chunk(content, 0, path, metadata)]

        chunks: list[Chunk] = []
        for path, metadata, texts in sections:
            buffer = ""
            for text in texts:
                if len(text) > budget.max_chars:
                    if buffer:
                        chunks.append(
                            self._make_chunk(buffer, len(chunks), path, metadata)
                        )
                        buffer = ""
                    for part in split_text(
                        text, budget.max_chars, budget.overlap_chars
                    ):
                        chunks.append(
                            self._make_chunk(part, len(chunks), path, metadata)
                        )
                    continue
                if buffer and len(buffer) + 2 + len(text) > budget.max_chars:
                    chunks.append(self._make_chunk(buffer, len(chunks), path, metadata))
                    buffer = ""
                buffer = f"{buffer}\n\n{text}" if buffer else text
            if buffer:
                chunks.append(self._make_chunk(buffer, len(chunks), path, metadata))
        return chunks

    @staticmethod
    def _metadata(block: Block) -> dict:
        return {
            "source_file": block.provenance.source_file,
            "sheet_name": block.provenance.sheet_name,
        }

    @staticmethod
    def _make_chunk(
        content: str, index: int, outline: tuple[str, ...], metadata: dict
    ) -> Chunk:
        prefix = " > ".join(item for item in outline if item)
        embedding_text = f"{prefix}\n{content}" if prefix else content
        return Chunk(
            content=content,
            embedding_text=embedding_text,
            chunk_index=index,
            outline_path=outline,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
