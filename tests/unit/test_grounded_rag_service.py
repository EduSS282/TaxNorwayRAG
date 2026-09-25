"""End-to-end tests for deterministic grounded-generation orchestration."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from taxguide.context.builder import ContextBuilder
from taxguide.domain.exceptions import TemporalResolutionError
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.generation.base import ChatMessage
from taxguide.generation.models import Citation, ConfidenceLevel, RagAnswer
from taxguide.generation.service import GroundedRagService, GroundedRagStatus
from taxguide.query.tax_year import TaxYearResolutionContext
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.rules.factory import create_tax_router
from taxguide.vectorstores.base import ScoredChunk


class RecordingRetriever:
    def __init__(self, results: list[ScoredChunk], *, failure: RuntimeError | None = None) -> None:
        self.results = results
        self.failure = failure
        self.calls: list[tuple[str, int, RetrievalFilter | None]] = []

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: RetrievalFilter | None = None,
    ) -> list[ScoredChunk]:
        self.calls.append((query, limit, filters))
        if self.failure is not None:
            raise self.failure
        return self.results[:limit]


class StubGenerator:
    model_id = "stub-generator"

    def __init__(self, output: str, *, failure: RuntimeError | None = None) -> None:
        self.output = output
        self.failure = failure
        self.calls: list[list[ChatMessage]] = []

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        assert temperature == 0.1
        assert max_tokens == 100
        self.calls.append(messages)
        if self.failure is not None:
            raise self.failure
        return self.output


def test_service_returns_a_validated_grounded_answer() -> None:
    chunk = _chunk("a", tax_year=2026)
    retriever = RecordingRetriever([ScoredChunk(chunk=chunk, score=0.9)])
    generator = StubGenerator(_answer(chunk, tax_year=2026).model_dump_json())

    result = _service(retriever, generator).answer(
        "Explain Norwegian wealth tax for 2026.", retrieval_limit=3
    )

    assert result.status is GroundedRagStatus.ANSWERED
    assert result.answer == _answer(chunk, tax_year=2026)
    assert result.evidence_count == 1
    assert result.generator_model == "stub-generator"
    assert retriever.calls == [
        (
            "Explain Norwegian wealth tax for 2026.",
            3,
            RetrievalFilter(tax_year=2026),
        )
    ]
    assert "untrusted quoted data" in generator.calls[0][0]["content"]


def test_service_requests_clarification_before_runtime_calls() -> None:
    retriever = RecordingRetriever([])
    generator = StubGenerator("unused")

    result = _service(retriever, generator).answer(
        "Where do I report foreign income on my tax return?"
    )

    assert result.status is GroundedRagStatus.CLARIFICATION_REQUIRED
    assert result.clarification_questions == ("Which tax year does your question concern?",)
    assert retriever.calls == []
    assert generator.calls == []


def test_service_uses_injected_conversation_tax_year_before_retrieval() -> None:
    chunk = _chunk("a", tax_year=2025)
    retriever = RecordingRetriever([ScoredChunk(chunk=chunk, score=0.9)])
    generator = StubGenerator(_answer(chunk, tax_year=2025).model_dump_json())
    service = _service(
        retriever,
        generator,
        tax_year_context_provider=lambda question: (
            TaxYearResolutionContext(conversation_tax_year=2025)
            if "deduction" in question
            else TaxYearResolutionContext()
        ),
    )

    result = service.answer("Explain the standard deduction.")

    assert result.status is GroundedRagStatus.ANSWERED
    assert result.answer is not None and result.answer.tax_year == 2025
    assert retriever.calls[0][2] == RetrievalFilter(tax_year=2025)


def test_service_clarifies_when_context_requires_an_unresolved_year() -> None:
    retriever = RecordingRetriever([])
    generator = StubGenerator("unused")
    service = _service(
        retriever,
        generator,
        tax_year_context_provider=lambda _question: TaxYearResolutionContext(require_tax_year=True),
    )

    result = service.answer("Explain this tax form field.")

    assert result.status is GroundedRagStatus.CLARIFICATION_REQUIRED
    assert result.clarification_questions == ("Which tax year does your question concern?",)
    assert retriever.calls == []
    assert generator.calls == []


def test_service_clarifies_multiple_query_years() -> None:
    result = _service(RecordingRetriever([]), StubGenerator("unused")).answer(
        "Explain Norwegian wealth tax for 2025 and 2026."
    )

    assert result.status is GroundedRagStatus.CLARIFICATION_REQUIRED
    assert "2025, 2026" in result.clarification_questions[0]
    assert result.routing is None


def test_service_rejects_a_conflicting_explicit_tax_year() -> None:
    with pytest.raises(TemporalResolutionError, match="conflicts"):
        _service(RecordingRetriever([]), StubGenerator("unused")).answer(
            "Explain Norwegian wealth tax for 2026.", tax_year=2025
        )


def test_service_abstains_out_of_scope_without_runtime_calls() -> None:
    retriever = RecordingRetriever([])
    generator = StubGenerator("unused")

    result = _service(retriever, generator).answer("Write a poem about the sea.")

    assert result.status is GroundedRagStatus.ABSTAINED
    assert result.answer is not None
    assert result.answer.citations == []
    assert "outside" in result.answer.missing_information[0]
    assert retriever.calls == []
    assert generator.calls == []


def test_service_abstains_before_generation_when_evidence_is_insufficient() -> None:
    generator = StubGenerator("unused")

    result = _service(RecordingRetriever([]), generator).answer(
        "Explain Norwegian wealth tax for 2026."
    )

    assert result.status is GroundedRagStatus.ABSTAINED
    assert result.answer is not None
    assert result.answer.missing_information == ["Retrieved evidence was insufficient."]
    assert generator.calls == []


def test_high_risk_route_requires_two_evidence_chunks() -> None:
    chunk = _chunk("a", tax_year=2026)
    generator = StubGenerator("unused")

    result = _service(RecordingRetriever([ScoredChunk(chunk=chunk, score=1.0)]), generator).answer(
        "Can I opt out of PAYE tax for 2026?"
    )

    assert result.status is GroundedRagStatus.ABSTAINED
    assert result.evidence_count == 1
    assert generator.calls == []


def test_service_returns_failed_for_retrieval_and_generation_failures() -> None:
    retrieval_failure = _service(
        RecordingRetriever([], failure=RuntimeError("qdrant unavailable")),
        StubGenerator("unused"),
    ).answer("Explain Norwegian wealth tax for 2026.")

    chunk = _chunk("a", tax_year=2026)
    generation_failure = _service(
        RecordingRetriever([ScoredChunk(chunk=chunk, score=1.0)]),
        StubGenerator("", failure=RuntimeError("model unavailable")),
    ).answer("Explain Norwegian wealth tax for 2026.")

    assert retrieval_failure.status is GroundedRagStatus.FAILED
    assert retrieval_failure.error == "retrieval failed: qdrant unavailable"
    assert generation_failure.status is GroundedRagStatus.FAILED
    assert generation_failure.error == "generation failed: model unavailable"


def test_service_returns_failed_for_malformed_structured_output() -> None:
    chunk = _chunk("a", tax_year=2026)

    result = _service(
        RecordingRetriever([ScoredChunk(chunk=chunk, score=1.0)]),
        StubGenerator("not-json"),
    ).answer("Explain Norwegian wealth tax for 2026.")

    assert result.status is GroundedRagStatus.FAILED
    assert result.error == "generator returned invalid structured output"


@pytest.mark.parametrize("invalid_kind", ["citation", "quote_span", "tax_year"])
def test_service_abstains_when_generated_grounding_is_invalid(invalid_kind: str) -> None:
    chunk = _chunk("a", tax_year=2026)
    answer = _answer(chunk, tax_year=2026)
    if invalid_kind == "citation":
        citation = answer.citations[0].model_copy(update={"chunk_id": "b" * 64})
        answer = answer.model_copy(update={"citations": [citation]})
    elif invalid_kind == "quote_span":
        citation = answer.citations[0].model_copy(update={"quote_span": (0, 999)})
        answer = answer.model_copy(update={"citations": [citation]})
    else:
        answer = answer.model_copy(update={"tax_year": 2025})

    result = _service(
        RecordingRetriever([ScoredChunk(chunk=chunk, score=1.0)]),
        StubGenerator(answer.model_dump_json()),
    ).answer("Explain Norwegian wealth tax for 2026.")

    assert result.status is GroundedRagStatus.ABSTAINED
    assert result.answer is not None
    assert result.answer.citations == []
    assert result.answer.confidence is ConfidenceLevel.LOW
    assert result.answer.missing_information == ["Generated citations could not be validated."]


def _service(
    retriever: RecordingRetriever,
    generator: StubGenerator,
    *,
    tax_year_context_provider: Callable[[str], TaxYearResolutionContext] | None = None,
) -> GroundedRagService:
    return GroundedRagService(
        router=create_tax_router(),
        retriever=retriever,
        context_builder=ContextBuilder(max_tokens=100, max_chunks_per_document=2),
        generator=generator,
        temperature=0.1,
        max_tokens=100,
        tax_year_context_provider=tax_year_context_provider,
    )


def _answer(chunk: Chunk, *, tax_year: int) -> RagAnswer:
    return RagAnswer(
        answer="The evidence explains the applicable wealth tax rule.",
        tax_year=tax_year,
        citations=[
            Citation(
                citation_id="S1",
                chunk_id=chunk.id,
                source_title=chunk.metadata.title,
                source_url=chunk.metadata.source_url,
                quote_span=(0, len(chunk.text)),
            )
        ],
        confidence=ConfidenceLevel.HIGH,
        missing_information=[],
        warnings=[],
    )


def _chunk(identity: str, *, tax_year: int) -> Chunk:
    text = "Tax evidence for the selected year."
    return Chunk(
        id=identity * 64,
        document_id=identity * 64,
        text=text,
        section_path=("Wealth tax",),
        chunk_index=0,
        token_count=6,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            title="Official wealth tax guidance",
            source_url="https://www.skatteetaten.no/en/wealth-tax/",
            source_domain="www.skatteetaten.no",
            tax_year=tax_year,
            retrieved_at=datetime(2026, 9, 23, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )
