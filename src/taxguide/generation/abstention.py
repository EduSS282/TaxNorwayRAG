"""Safe abstention decisions for evidence-bound tax answers."""

from taxguide.context.builder import GenerationContext
from taxguide.generation.models import ConfidenceLevel, RagAnswer

_ABSTENTION_ANSWER = (
    "I do not have enough retrieved official evidence to answer this tax question safely."
)


class AbstentionPolicy:
    """Return a canonical non-claiming response when grounding guarantees fail."""

    def __init__(self, *, minimum_evidence: int = 1) -> None:
        if minimum_evidence <= 0:
            raise ValueError("minimum_evidence must be positive")
        self._minimum_evidence = minimum_evidence

    def should_abstain(self, context: GenerationContext, *, citations_valid: bool = True) -> bool:
        """Decide from the evidence threshold and an injected citation-validation result."""
        return len(context.evidence) < self._minimum_evidence or not citations_valid

    def enforce(
        self,
        answer: RagAnswer,
        context: GenerationContext,
        *,
        citations_valid: bool = True,
    ) -> RagAnswer:
        """Keep a safely grounded answer or replace it with a canonical abstention."""
        if not self.should_abstain(context, citations_valid=citations_valid):
            return answer
        reason = (
            "Retrieved evidence was insufficient."
            if len(context.evidence) < self._minimum_evidence
            else "Generated citations could not be validated."
        )
        return self.abstain(tax_year=answer.tax_year, missing_information=[reason])

    def abstain(self, *, tax_year: int | None, missing_information: list[str]) -> RagAnswer:
        """Create a transparent response with no tax claim or unverified citation."""
        return RagAnswer(
            answer=_ABSTENTION_ANSWER,
            tax_year=tax_year,
            citations=[],
            confidence=ConfidenceLevel.LOW,
            missing_information=missing_information,
            warnings=["Consult Skatteetaten's official guidance for a definitive answer."],
        )
