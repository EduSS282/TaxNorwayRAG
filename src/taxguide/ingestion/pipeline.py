import logging
from pathlib import Path

from taxguide.domain.exceptions import UnsupportedDocumentError
from taxguide.domain.models import Document
from taxguide.ingestion.normalizer import DocumentNormalizer
from taxguide.ingestion.parser import DocumentParser
from taxguide.sources.base import DocumentSource

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self, source: DocumentSource, parser: DocumentParser, normalizer: DocumentNormalizer
    ) -> None:
        self.source = source
        self.parser = parser
        self.normalizer = normalizer

    def ingest(self, *, path: Path, source_url: str) -> Document:
        raw = self.source.load(path, source_url)
        if not self.parser.can_parse(raw):
            raise UnsupportedDocumentError(f"No parser for {source_url}")
        logger.info("parser selected id=%s parser=%s", raw.id, type(self.parser).__name__)
        return self.normalizer.normalize(self.parser.parse(raw))
