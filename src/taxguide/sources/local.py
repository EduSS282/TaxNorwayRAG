import logging
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from taxguide.domain.exceptions import DocumentLoadError
from taxguide.domain.models import RawDocument
from taxguide.ingestion.hashing import document_id_from_url

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class LocalHtmlSource:
    """Load UTF-8 HTML; clock records ingestion time unless supplied from a capture manifest."""

    def __init__(self, clock: Callable[[], datetime] = utc_now) -> None:
        self.clock = clock

    def load(self, path: Path, source_url: str) -> RawDocument:
        try:
            data = path.read_bytes()
            parts = urlsplit(source_url)
            document = RawDocument(
                id=document_id_from_url(source_url),
                source_url=source_url,
                source_domain=parts.hostname or "",
                source_path=parts.path,
                local_path=path.resolve(),
                content=data.decode("utf-8-sig"),
                retrieved_at=self.clock(),
                content_hash=sha256(data).hexdigest(),
            )
        except (OSError, ValueError) as exc:
            raise DocumentLoadError(f"Cannot load HTML {path}: {exc}") from exc
        logger.info("document loaded id=%s path=%s", document.id, path)
        return document
