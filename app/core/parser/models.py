"""解析阶段的 Block 中间表示。"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Provenance:
    source_file: str | None = None
    sheet_name: str | None = None


@dataclass(frozen=True, slots=True)
class HeadingBlock:
    level: int
    text: str
    provenance: Provenance = field(default_factory=Provenance)


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    text: str
    provenance: Provenance = field(default_factory=Provenance)


@dataclass(frozen=True, slots=True)
class TableBlock:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    provenance: Provenance = field(default_factory=Provenance)


@dataclass(frozen=True, slots=True)
class CodeBlock:
    code: str
    language: str | None = None
    provenance: Provenance = field(default_factory=Provenance)


@dataclass(frozen=True, slots=True)
class ListBlock:
    items: tuple[str, ...]
    ordered: bool = False
    provenance: Provenance = field(default_factory=Provenance)


type Block = HeadingBlock | ParagraphBlock | TableBlock | CodeBlock | ListBlock


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    blocks: tuple[Block, ...]
    metadata: dict = field(default_factory=dict)
