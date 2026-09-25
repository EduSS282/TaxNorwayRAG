"""Stable identity for the settings that produce an indexed chunk vector."""

import json
from hashlib import sha256

from taxguide.config.models import AppConfig


def index_signature(settings: AppConfig, embedding_model_id: str) -> str:
    """Invalidate incremental reuse when parsing, chunking, or embedding settings change."""
    identity = {
        "schema_version": 1,
        "parser": settings.ingestion.parser,
        "preserve_links": settings.ingestion.preserve_links,
        "preserve_headings": settings.ingestion.preserve_headings,
        "chunk_strategy": settings.corpus.chunk_strategy,
        "max_tokens": settings.corpus.max_tokens,
        "overlap_tokens": settings.corpus.overlap_tokens,
        "embedding_provider": settings.corpus.embedding_provider,
        "embedding_model": embedding_model_id,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()
