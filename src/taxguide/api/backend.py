"""API composition over the existing retrieval, reranking, and answer services."""

from threading import Lock
from typing import Protocol

from taxguide.config.models import AppConfig
from taxguide.domain.models import Chunk
from taxguide.generation.composition import build_grounded_service
from taxguide.generation.service import GroundedRagResult, GroundedRagService
from taxguide.observability.request import timed_stage
from taxguide.reranking.base import Reranker
from taxguide.reranking.factory import create_reranker
from taxguide.retrieval.factory import RetrievalMode, create_retriever
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.hybrid import Retriever
from taxguide.retrieval.temporal import TaxYearAwareRetriever
from taxguide.vectorstores.base import ScoredChunk


class ApiBackend(Protocol):
    def retrieve(
        self,
        query: str,
        *,
        mode: RetrievalMode,
        limit: int,
        candidate_limit: int,
        tax_year: int | None,
    ) -> list[ScoredChunk]: ...

    def rerank(self, query: str, chunks: list[Chunk], *, limit: int) -> list[ScoredChunk]: ...

    def query(
        self,
        question: str,
        *,
        mode: RetrievalMode,
        retrieval_limit: int,
        candidate_limit: int,
        tax_year: int | None,
    ) -> GroundedRagResult: ...


class ConfiguredBackend:
    """Lazily cache configured adapters for one API process; no model loads at import."""

    def __init__(self, settings: AppConfig) -> None:
        self.settings = settings
        self._lock = Lock()
        self._retrievers: dict[tuple[RetrievalMode, int], Retriever] = {}
        self._answer_services: dict[tuple[RetrievalMode, int], GroundedRagService] = {}
        self._reranker: Reranker | None = None

    def _retriever(self, mode: RetrievalMode, candidate_limit: int) -> Retriever:
        key = (mode, candidate_limit)
        with self._lock:
            if key not in self._retrievers:
                self._retrievers[key] = create_retriever(
                    self.settings, mode=mode, candidate_limit=candidate_limit
                )
            return self._retrievers[key]

    def retrieve(
        self,
        query: str,
        *,
        mode: RetrievalMode,
        limit: int,
        candidate_limit: int,
        tax_year: int | None,
    ) -> list[ScoredChunk]:
        retriever = TaxYearAwareRetriever(self._retriever(mode, candidate_limit))
        filters = RetrievalFilter(tax_year=tax_year) if tax_year is not None else None
        if filters is None:
            return retriever.retrieve(query, limit=limit)
        return retriever.retrieve(query, limit=limit, filters=filters)

    def rerank(self, query: str, chunks: list[Chunk], *, limit: int) -> list[ScoredChunk]:
        with self._lock:
            if self._reranker is None:
                self._reranker = create_reranker(self.settings.retrieval)
            reranker = self._reranker
        return reranker.rank(query, chunks, limit=limit)

    def query(
        self,
        question: str,
        *,
        mode: RetrievalMode,
        retrieval_limit: int,
        candidate_limit: int,
        tax_year: int | None,
    ) -> GroundedRagResult:
        key = (mode, candidate_limit)
        with self._lock:
            if key not in self._answer_services:
                self._answer_services[key] = build_grounded_service(
                    self.settings,
                    mode=mode,
                    candidate_limit=candidate_limit,
                    stage_timer=timed_stage,
                )
            service = self._answer_services[key]
        return service.answer(question, tax_year=tax_year, retrieval_limit=retrieval_limit)
