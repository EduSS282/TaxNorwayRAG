"""Composition for configured reranker backends."""

from taxguide.config.models import RetrievalConfig
from taxguide.reranking.base import Reranker
from taxguide.reranking.http import HttpReranker
from taxguide.reranking.llamacpp import LlamaCppReranker
from taxguide.reranking.qwen import QwenReranker


def create_reranker(settings: RetrievalConfig) -> Reranker:
    """Create the configured reranker without exposing backend details to callers."""
    if settings.reranker_provider == "local":
        return QwenReranker(settings.reranker_model)
    if settings.reranker_provider == "http":
        return HttpReranker(
            settings.reranker_model,
            settings.reranker_base_url,
            timeout=settings.reranker_timeout,
        )
    if settings.reranker_provider == "llamacpp":
        return LlamaCppReranker(
            settings.reranker_base_url,
            timeout=settings.reranker_timeout,
        )
    raise ValueError(f"Unsupported reranker provider: {settings.reranker_provider}")
