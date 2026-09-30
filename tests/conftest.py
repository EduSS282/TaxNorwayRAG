from datetime import UTC, datetime
from pathlib import Path

import pytest

from taxguide.domain.models import RawDocument
from taxguide.sources.local import LocalHtmlSource

FIXTURES = Path(__file__).parent / "fixtures" / "html"
URL = "https://www.skatteetaten.no/en/example"


@pytest.fixture
def raw() -> RawDocument:
    return LocalHtmlSource(clock=lambda: datetime(2026, 9, 8, tzinfo=UTC)).load(
        FIXTURES / "skatteetaten_basic.html",
        URL,
    )
