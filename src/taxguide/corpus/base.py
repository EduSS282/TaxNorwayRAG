from collections.abc import Iterable
from typing import Protocol

from taxguide.corpus.models import CorpusFilters, CorpusSelection, CrawlManifest


class CorpusSelector(Protocol):
    def select(
        self, manifests: Iterable[CrawlManifest], filters: CorpusFilters
    ) -> CorpusSelection: ...
