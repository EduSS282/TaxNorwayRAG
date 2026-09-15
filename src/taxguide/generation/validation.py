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
        return answer


def _evidence_by_id(context: GenerationContext) -> dict[str, ContextEvidence]:
    evidence_by_id = {evidence.evidence_id: evidence for evidence in context.evidence}
    if len(evidence_by_id) != len(context.evidence):
        raise CitationValidationError("generation context contains duplicate evidence IDs")
    return evidence_by_id
