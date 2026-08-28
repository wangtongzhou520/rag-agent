"""二维解析器路由。"""

from enum import StrEnum

from app.core.parser.parsers import (
    CsvDocumentParser,
    DocumentParser,
    ExcelDocumentParser,
    MarkdownDocumentParser,
    PdfDocumentParser,
    TextDocumentParser,
)
from app.framework.exceptions import ClientException


class ParseProfile(StrEnum):
    FAST = "fast"
    FIDELITY = "fidelity"


class ParserRegistry:
    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], DocumentParser] = {}

    def register(
        self, parser: DocumentParser, mimes: tuple[str, ...], profiles: tuple[str, ...]
    ) -> None:
        for mime in mimes:
            for profile in profiles:
                key = (mime.lower(), str(profile))
                if key in self._routes:
                    raise ValueError(f"解析器路由冲突: {mime}/{profile}")
                self._routes[key] = parser

    def find(self, mime: str, profile: str) -> DocumentParser | None:
        mime = mime.lower().split(";", 1)[0].strip()
        wildcard = "text/*" if mime.startswith("text/") else "*/*"
        candidates = (
            (mime, str(profile)),
            (wildcard, str(profile)),
            (mime, str(ParseProfile.FAST)),
            (wildcard, str(ParseProfile.FAST)),
        )
        return next((self._routes[key] for key in candidates if key in self._routes), None)

    def require(self, mime: str, profile: str) -> DocumentParser:
        parser = self.find(mime, profile)
        if parser is None:
            raise ClientException(f"不支持的文件类型: {mime}")
        return parser

    def can_parse(self, mime: str) -> bool:
        return self.find(mime, str(ParseProfile.FAST)) is not None


def build_default_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(
        MarkdownDocumentParser(),
        ("text/markdown", "text/x-markdown", "text/x-web-markdown", "text/plain"),
        (str(ParseProfile.FAST),),
    )
    registry.register(
        CsvDocumentParser(),
        ("text/csv", "application/csv", "text/comma-separated-values"),
        (str(ParseProfile.FAST),),
    )
    registry.register(
        ExcelDocumentParser(),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
        (str(ParseProfile.FAST),),
    )
    registry.register(
        PdfDocumentParser(),
        ("application/pdf", "application/x-pdf"),
        (str(ParseProfile.FAST), str(ParseProfile.FIDELITY)),
    )
    registry.register(
        TextDocumentParser(),
        ("text/*", "application/json", "application/xml", "text/html"),
        (str(ParseProfile.FAST),),
    )
    return registry
