from typing import Protocol

from taxguide.domain.models import ParsedDocument, RawDocument


class DocumentParser(Protocol):
    def can_parse(self, document: RawDocument) -> bool: ...

    def parse(self, document: RawDocument) -> ParsedDocument: ...
