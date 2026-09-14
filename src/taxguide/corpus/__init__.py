"""Manifest-driven corpus selection and batch processing."""

from taxguide.corpus.models import CorpusFilters, CrawlManifest
from taxguide.corpus.selector import ManifestCorpusSelector

__all__ = ["CorpusFilters", "CrawlManifest", "ManifestCorpusSelector"]
