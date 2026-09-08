from typing import Protocol

from taxguide.domain.models import Chunk, Document


class Chunker(Protocol):
    """Turns one normalized document into ordered, traceable chunks."""

    def chunk(self, document: Document) -> list[Chunk]: ...
