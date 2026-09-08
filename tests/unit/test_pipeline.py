from pathlib import Path
from unittest.mock import Mock

import pytest

from taxguide.domain.exceptions import UnsupportedDocumentError
from taxguide.ingestion.pipeline import IngestionPipeline


def test_pipeline_orchestrates_injected_components_only(raw) -> None:
    source = Mock()
    parser = Mock()
    normalizer = Mock()
    expected = Mock()
    path = Path("document.html")

    source.load.return_value = raw
    parser.can_parse.return_value = True
    parser.parse.return_value = Mock()
    normalizer.normalize.return_value = expected

    result = IngestionPipeline(source, parser, normalizer).ingest(
        path=path,
        source_url=raw.source_url,
    )

    assert result is expected
    source.load.assert_called_once_with(path, raw.source_url)
    parser.can_parse.assert_called_once_with(raw)
    parser.parse.assert_called_once_with(raw)
    normalizer.normalize.assert_called_once_with(parser.parse.return_value)


def test_pipeline_stops_before_parsing_for_unsupported_documents(raw) -> None:
    source = Mock()
    parser = Mock()
    normalizer = Mock()
    source.load.return_value = raw
    parser.can_parse.return_value = False

    pipeline = IngestionPipeline(source, parser, normalizer)

    with pytest.raises(UnsupportedDocumentError, match="No parser"):
        pipeline.ingest(path=Path("document.html"), source_url=raw.source_url)
    parser.parse.assert_not_called()
    normalizer.normalize.assert_not_called()
