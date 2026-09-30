"""Embedding composition for configured application entry points."""

from taxguide.config.models import CorpusConfig
from taxguide.embeddings.base import Embedder
from taxguide.embeddings.ollama import OllamaEmbedder
from taxguide.embeddings.qwen import QwenEmbedder


def create_embedder(settings: CorpusConfig) -> Embedder:
    """Create the configured embedding provider without exposing it to callers."""
    if settings.embedding_provider == "ollama":
        return OllamaEmbedder(
            settings.embedding_base_url,
            settings.embedding_model,
            timeout=settings.embedding_timeout,
        )
    if settings.embedding_provider == "local":
        return QwenEmbedder(settings.embedding_model)
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
