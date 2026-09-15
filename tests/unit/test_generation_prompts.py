from datetime import UTC, datetime

import pytest

from taxguide.context.builder import ContextBuilder
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.generation.prompts import build_grounded_messages
from taxguide.vectorstores.base import ScoredChunk


def test_grounded_prompt_requires_only_supplied_evidence_and_structured_citations() -> None:
    chunk = _chunk()
    context = ContextBuilder(max_tokens=3).build([ScoredChunk(chunk=chunk, score=1.0)])

    messages = build_grounded_messages("Can I claim this deduction?", context, tax_year=2026)

    assert messages[0]["role"] == "system"
    assert "Use only the retrieved evidence" in messages[0]["content"]
    assert "Do not assume tax residency" in messages[0]["content"]
    assert "If the evidence is insufficient" in messages[0]["content"]
    assert "Question:\nCan I claim this deduction?" in messages[1]["content"]
    assert "Requested tax year: 2026" in messages[1]["content"]
    assert f"[S1] chunk_id={chunk.id}" in messages[1]["content"]
    assert "Exact source evidence" in messages[1]["content"]
    assert '"citation_id"' in messages[1]["content"]


def test_grounded_prompt_explicitly_exposes_an_empty_context() -> None:
    context = ContextBuilder(max_tokens=1).build([])
    messages = build_grounded_messages("What is the deadline?", context)

    assert "Requested tax year: not specified" in messages[1]["content"]
    assert "Retrieved evidence:\n(No retrieved evidence.)" in messages[1]["content"]


def test_grounded_prompt_is_deterministic() -> None:
    context = ContextBuilder(max_tokens=3).build([ScoredChunk(chunk=_chunk(), score=1.0)])

    first = build_grounded_messages("Question", context)
    second = build_grounded_messages("Question", context)

    assert first == second


@pytest.mark.parametrize("question", ["", "   "])
def test_grounded_prompt_rejects_blank_question(question: str) -> None:
    with pytest.raises(ValueError, match="question"):
        build_grounded_messages(question, ContextBuilder(max_tokens=1).build([]))


def _chunk() -> Chunk:
    return Chunk(
        id="a" * 64,
        document_id="b" * 64,
        text="Exact source evidence",
        section_path=("Deductions",),
        chunk_index=0,
        token_count=3,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            title="Deductions",
            source_url="https://www.skatteetaten.no/en/deductions",
            source_domain="www.skatteetaten.no",
            tax_year=2026,
            retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )
