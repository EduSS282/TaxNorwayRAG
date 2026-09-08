from pathlib import Path
from typing import Protocol

from taxguide.domain.models import RawDocument


class DocumentSource(Protocol):
    def load(self, path: Path, source_url: str) -> RawDocument: ...
