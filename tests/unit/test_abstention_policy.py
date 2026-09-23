from datetime import UTC, datetime

import pytest

from taxguide.context.builder import ContextBuilder, GenerationContext
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.generation.abstention import AbstentionPolicy
from taxguide.generation.models import ConfidenceLevel, RagAnswer
from taxguide.vectorstores.base import ScoredChunk


def test_abstention_policy_abstains_without_sufficient_evidence() -> None:
    answer = _answer()

    result = AbstentionPolicy().enforce(answer, GenerationContext(), citations_valid=True)

    assert result.tax_year == 2026
    assert result.citations == []
    assert result.confidence == ConfidenceLevel.LOW
    assert "enough retrieved official evidence" in result.answer
    assert result.missing_information == ["Retrieved evidence was insufficient."]


def test_abstention_policy_abstains_when_citations_are_invalid() -> None:
    result = AbstentionPolicy().enforce(_answer(), _context(), citations_valid=False)

    assert result.citations == []
    assert result.missing_information == ["Generated citations could not be validated."]


def test_abstention_policy_preserves_answer_with_sufficient_valid_evidence() -> None:
    answer = _answer()

    assert AbstentionPolicy().enforce(answer, _context(), citations_valid=True) is answer


def test_abstention_policy_respects_configured_evidence_threshold() -> None:
    assert AbstentionPolicy(minimum_evidence=2).should_abstain(_context(), citations_valid=True)


@pytest.mark.parametrize("minimum_evidence", [0, -1])
def test_abstention_policy_rejects_invalid_threshold(minimum_evidence: int) -> None:
    with pytest.raises(ValueError, match="minimum_evidence"):
        AbstentionPolicy(minimum_evidence=minimum_evidence)


def _answer() -> RagAnswer:
    return RagAnswer(
        answer="A grounded answer.",
        tax_year=2026,
        citations=[],
        confidence=ConfidenceLevel.MEDIUM,
        missing_information=[],
        warnings=[],
    )


def _context() -> GenerationContext:
    chunk = Chunk(
        id="a" * 64,
        document_id="b" * 64,
        text="Evidence",
        chunk_index=0,
        token_count=1,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )
    return ContextBuilder(max_tokens=1).build([ScoredChunk(chunk=chunk, score=1.0)])
