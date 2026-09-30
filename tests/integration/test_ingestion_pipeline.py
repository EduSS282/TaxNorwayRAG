from datetime import UTC, datetime
from pathlib import Path

from taxguide.ingestion.normalizer import Normalizer
from taxguide.ingestion.pipeline import IngestionPipeline
from taxguide.ingestion.skatteetaten_parser import SkatteetatenHtmlParser
from taxguide.sources.local import LocalHtmlSource

URL = "https://www.skatteetaten.no/en/example"
FIXTURE = Path("tests/fixtures/html/skatteetaten_noise.html")


def test_full_ingestion_pipeline():
    pipeline = IngestionPipeline(
        LocalHtmlSource(clock=lambda: datetime(2026, 9, 8, tzinfo=UTC)),
        SkatteetatenHtmlParser(),
        Normalizer(),
    )
    doc = pipeline.ingest(path=FIXTURE, source_url=URL)
    assert doc == pipeline.ingest(path=FIXTURE, source_url=URL)
    assert len(doc.id) == 64 and len(doc.content_hash) == 64
    assert doc.source_url == URL and doc.language == "en" and doc.title == "Tax return"
    assert len(doc.sections) == 2 and "NOISE" not in doc.plain_text
    assert (
        doc.plain_text
        == "Tax return\n\nCheck your information.\n\n## Details\n\nKeep your documents."
    )
