from datetime import UTC, datetime

import pytest

from taxguide.api.backend import ConfiguredBackend
from taxguide.config.models import AppConfig
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.generation.service import GroundedRagResult, GroundedRagStatus
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.vectorstores.base import ScoredChunk


def _chunk() -> Chunk:
    return Chunk(
        id="a" * 64,
        document_id="b" * 64,
        text="Tax evidence",
        chunk_index=0,
        token_count=2,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/taxes/",
            source_domain="www.skatteetaten.no",
            tax_year=2025,
            retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )


def test_backend_caches_retriever_and_applies_temporal_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[object] = []
    calls: list[RetrievalFilter | None] = []

    class FakeRetriever:
        def retrieve(
            self, query: str, *, limit: int = 5, filters: RetrievalFilter | None = None
        ) -> list[ScoredChunk]:
            calls.append(filters)
            return [ScoredChunk(chunk=_chunk(), score=0.9)]

    def factory(*_args: object, **_kwargs: object) -> FakeRetriever:
        result = FakeRetriever()
        constructed.append(result)
        return result

    monkeypatch.setattr("taxguide.api.backend.create_retriever", factory)
    backend = ConfiguredBackend(AppConfig())
    for _ in range(2):
        assert (
            backend.retrieve(
                "Tax in 2025", mode="dense", limit=1, candidate_limit=10, tax_year=2025
            )[0].chunk
            == _chunk()
        )
    assert len(constructed) == 1
    assert calls == [RetrievalFilter(tax_year=2025), RetrievalFilter(tax_year=2025)]


def test_backend_reuses_reranker_and_answer_service(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []

    class FakeReranker:
        def rank(self, query: str, chunks: list[Chunk], *, limit: int = 10) -> list[ScoredChunk]:
            return [ScoredChunk(chunk=chunks[0], score=0.8)]

    class FakeAnswerService:
        def answer(
            self, question: str, *, tax_year: int | None, retrieval_limit: int
        ) -> GroundedRagResult:
            return GroundedRagResult(
                status=GroundedRagStatus.CLARIFICATION_REQUIRED,
                clarification_questions=("Which tax year?",),
            )

    monkeypatch.setattr(
        "taxguide.api.backend.create_reranker", lambda _: built.append("rerank") or FakeReranker()
    )
    monkeypatch.setattr(
        "taxguide.api.backend.build_grounded_service",
        lambda *_args, **_kwargs: built.append("answer") or FakeAnswerService(),
    )
    backend = ConfiguredBackend(AppConfig())
    for _ in range(2):
        assert backend.rerank("tax", [_chunk()], limit=1)[0].score == 0.8
        assert (
            backend.query(
                "tax", mode="dense", retrieval_limit=1, candidate_limit=10, tax_year=2025
            ).status
            is GroundedRagStatus.CLARIFICATION_REQUIRED
        )
    assert built == ["rerank", "answer"]
