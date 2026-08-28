"""字节与文件名联合 MIME 探测。"""

import mimetypes
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import filetype

from app.framework.exceptions import ClientException

_EXTENSION_MIMES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".text": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".rtf": "application/rtf",
    ".svg": "image/svg+xml",
}


class MimeTypeDetector:
    def detect(self, data: bytes, filename: str | None = None) -> str:
        if not data:
            raise ClientException("文件内容为空")
        suffix = Path(filename or "").suffix.lower()
        if suffix in {".docx", ".xlsx", ".pptx"} or data.startswith(b"PK"):
            detected = self._detect_ooxml(data)
            if detected:
                return detected
        kind = filetype.guess(data)
        if kind is not None:
            return kind.mime
        if suffix in _EXTENSION_MIMES:
            return _EXTENSION_MIMES[suffix]
        guessed, _ = mimetypes.guess_type(filename or "")
        if guessed:
            return guessed
        try:
            data[:4096].decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            return "application/octet-stream"

    @staticmethod
    def _detect_ooxml(data: bytes) -> str | None:
        try:
            with ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
        except (BadZipFile, OSError):
            return None
        if "word/document.xml" in names:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "xl/workbook.xml" in names:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if "ppt/presentation.xml" in names:
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        return None
