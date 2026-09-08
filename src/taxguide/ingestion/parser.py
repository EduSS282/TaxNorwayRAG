from typing import Protocol

from taxguide.domain.models import ParsedDocument, RawDocument


class DocumentParser(Protocol):
    """Structural contract for parsers supplied to ingestion consumers.

    Implementations need no inheritance from this protocol. ``can_parse``
    reports source/format support, not whether the content is valid. ``parse``
    returns structured content with the original source identity, or raises
    ``UnsupportedDocumentError`` for an unsupported source/format and
    ``ParseError`` (including ``EmptyDocumentError``) for unusable content.
    """

    def can_parse(self, document: RawDocument) -> bool: ...

    def parse(self, document: RawDocument) -> ParsedDocument: ...
