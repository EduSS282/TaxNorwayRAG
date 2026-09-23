"""Validation of generated citations against bounded source evidence."""

from taxguide.context.builder import ContextEvidence, GenerationContext
from taxguide.generation.models import RagAnswer


class CitationValidationError(ValueError):
    """A generated answer cites evidence that was not supplied to the model."""


class CitationValidator:
    """Reject citations that do not exactly match the generation context."""

    def validate(
        self,
        answer: RagAnswer,
        context: GenerationContext,
        *,
        is_abstention: bool = False,
        expected_tax_year: int | None = None,
    ) -> RagAnswer:
        """Return ``answer`` only when every citation is traceable to ``context``.

        An empty citation list is permitted only for an explicitly abstained answer.
        Callers provide that decision because abstention policy belongs to its own
        layer rather than being inferred from generated prose.
        """
        if not is_abstention and not answer.citations:
            raise CitationValidationError(
                "non-abstained answers must include at least one citation"
            )

        if expected_tax_year is not None and answer.tax_year != expected_tax_year:
            raise CitationValidationError(
                "answer tax_year does not match the resolved request tax year"
            )

        evidence_by_id = _evidence_by_id(context)
        cited_chunk_ids: set[str] = set()
        for citation in answer.citations:
            evidence = evidence_by_id.get(citation.citation_id)
            if evidence is None:
                raise CitationValidationError(
                    f"citation {citation.citation_id} does not reference context evidence"
                )
            if citation.chunk_id in cited_chunk_ids:
                raise CitationValidationError("answer contains duplicate cited chunks")
            cited_chunk_ids.add(citation.chunk_id)
            if citation.chunk_id != evidence.chunk.id:
                raise CitationValidationError(
                    f"citation {citation.citation_id} chunk_id does not match context evidence"
                )
            if citation.source_url != evidence.chunk.metadata.source_url:
                raise CitationValidationError(
                    f"citation {citation.citation_id} source_url does not match context evidence"
                )
            if citation.source_title != evidence.chunk.metadata.title:
                raise CitationValidationError(
                    f"citation {citation.citation_id} source_title does not match context evidence"
                )
            if citation.quote_span is not None:
                start, end = citation.quote_span
                if end > len(evidence.chunk.text):
                    raise CitationValidationError(
                        f"citation {citation.citation_id} quote_span is outside context evidence"
                    )
                if not evidence.chunk.text[start:end].strip():
                    raise CitationValidationError(
                        f"citation {citation.citation_id} quote_span selects no source text"
                    )
            if answer.tax_year is not None and evidence.chunk.metadata.tax_year != answer.tax_year:
                raise CitationValidationError(
                    f"citation {citation.citation_id} tax year does not match the answer"
                )
        return answer


def _evidence_by_id(context: GenerationContext) -> dict[str, ContextEvidence]:
    evidence_by_id = {evidence.evidence_id: evidence for evidence in context.evidence}
    if len(evidence_by_id) != len(context.evidence):
        raise CitationValidationError("generation context contains duplicate evidence IDs")
    return evidence_by_id
