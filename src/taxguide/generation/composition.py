"""Shared application composition for CLI and HTTP grounded answers."""

from collections.abc import Callable
from contextlib import AbstractContextManager

from taxguide.config.models import AppConfig
from taxguide.context.builder import ContextBuilder
from taxguide.generation.factory import create_generator
from taxguide.generation.service import GroundedRagService
from taxguide.retrieval.factory import RetrievalMode, create_retriever
from taxguide.retrieval.temporal import TaxYearAwareRetriever
from taxguide.rules.factory import create_tax_router


def build_grounded_service(
    settings: AppConfig,
    *,
    mode: RetrievalMode,
    qdrant_url: str | None = None,
    collection: str | None = None,
    candidate_limit: int | None = None,
    stage_timer: Callable[[str], AbstractContextManager[None]] | None = None,
) -> GroundedRagService:
    """Compose the default application service with replaceable inner contracts."""
    retriever = create_retriever(
        settings,
        mode=mode,
        qdrant_url=qdrant_url,
        collection=collection,
        candidate_limit=candidate_limit,
    )
    return GroundedRagService(
        router=create_tax_router(),
        retriever=TaxYearAwareRetriever(retriever),
        context_builder=ContextBuilder(
            max_tokens=settings.generation.evidence_max_tokens,
            max_chunks_per_document=settings.generation.max_chunks_per_document,
        ),
        generator=create_generator(settings.generation),
        temperature=settings.generation.temperature,
        max_tokens=settings.generation.max_tokens,
        stage_timer=stage_timer,
    )
