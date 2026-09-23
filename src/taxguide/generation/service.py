"""End-to-end orchestration for evidence-bound tax answers."""

from enum import StrEnum
from typing import Self

from pydantic import Field, ValidationError, model_validator

from taxguide.context.builder import ContextBuilder, GenerationContext
from taxguide.domain.exceptions import TaxguideError, TemporalResolutionError
from taxguide.domain.models import DomainModel
from taxguide.generation.abstention import AbstentionPolicy
from taxguide.generation.base import Generator
from taxguide.generation.models import RagAnswer
from taxguide.generation.prompts import build_grounded_messages
from taxguide.generation.validation import CitationValidationError, CitationValidator
from taxguide.query.tax_year import TaxYearResolutionSource, TaxYearResolver
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.retrieval.hybrid import Retriever
from taxguide.rules.base import TaxRouter
from taxguide.rules.routing import RouteAction, RoutingDecision


class GroundedRagStatus(StrEnum):
    """Application-level outcome independent of generated answer prose."""

    ANSWERED = "answered"
    CLARIFICATION_REQUIRED = "clarification_required"
    ABSTAINED = "abstained"
    FAILED = "failed"


class GroundedRagResult(DomainModel):
    """Auditable outcome of one complete grounded-generation attempt."""

    status: GroundedRagStatus
    answer: RagAnswer | None = None
    routing: RoutingDecision | None = None
    clarification_questions: tuple[str, ...] = ()
    evidence_count: int = Field(default=0, ge=0)
    generator_model: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def status_fields_are_consistent(self) -> Self:
        if self.status in {GroundedRagStatus.ANSWERED, GroundedRagStatus.ABSTAINED}:
            if self.answer is None:
                raise ValueError("answered and abstained results require an answer")
            if self.clarification_questions or self.error is not None:
                raise ValueError("answer results cannot contain clarification or error fields")
            if self.status is GroundedRagStatus.ANSWERED and not self.answer.citations:
                raise ValueError("answered results require citations")
            if self.status is GroundedRagStatus.ABSTAINED and self.answer.citations:
                raise ValueError("abstained results cannot contain citations")
        elif self.status is GroundedRagStatus.CLARIFICATION_REQUIRED:
            if (
                not self.clarification_questions
                or self.answer is not None
                or self.error is not None
            ):
                raise ValueError("clarification results require only clarification questions")
        elif self.status is GroundedRagStatus.FAILED:
            if self.error is None or self.answer is not None or self.clarification_questions:
                raise ValueError("failed results require only an error")
        return self


class GroundedRagService:
    """Compose routing, retrieval, generation, validation, and abstention."""

    def __init__(
        self,
        *,
        router: TaxRouter,
        retriever: Retriever,
        context_builder: ContextBuilder,
        generator: Generator,
        temperature: float,
        max_tokens: int,
        tax_year_resolver: TaxYearResolver | None = None,
        citation_validator: CitationValidator | None = None,
    ) -> None:
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        self._router = router
        self._retriever = retriever
        self._context_builder = context_builder
        self._generator = generator
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._tax_year_resolver = tax_year_resolver or TaxYearResolver()
        self._citation_validator = citation_validator or CitationValidator()

    def answer(
        self,
        question: str,
        *,
        tax_year: int | None = None,
        retrieval_limit: int = 5,
    ) -> GroundedRagResult:
        """Return a validated answer, clarification, abstention, or safe failure."""
        if not question.strip():
            raise ValueError("question must not be blank")
        if retrieval_limit <= 0:
            raise ValueError("retrieval_limit must be positive")

        resolution = self._tax_year_resolver.resolve(question)
        if resolution.source is TaxYearResolutionSource.AMBIGUOUS:
            years = ", ".join(str(year) for year in resolution.mentioned_years)
            return GroundedRagResult(
                status=GroundedRagStatus.CLARIFICATION_REQUIRED,
                clarification_questions=(
                    f"Your question mentions multiple tax years ({years}). Which one applies?",
                ),
            )
        if (
            tax_year is not None
            and resolution.tax_year is not None
            and tax_year != resolution.tax_year
        ):
            raise TemporalResolutionError(
                f"Requested tax year {tax_year} conflicts with query year {resolution.tax_year}"
            )
        resolved_year = tax_year if tax_year is not None else resolution.tax_year
        decision = self._router.route(question, tax_year=resolved_year)

        if decision.action is RouteAction.CLARIFY:
            return GroundedRagResult(
                status=GroundedRagStatus.CLARIFICATION_REQUIRED,
                routing=decision,
                clarification_questions=decision.clarification_questions,
            )
        if decision.action is RouteAction.ABSTAIN:
            answer = AbstentionPolicy(minimum_evidence=decision.minimum_evidence).abstain(
                tax_year=resolved_year,
                missing_information=[decision.reason],
            )
            return GroundedRagResult(
                status=GroundedRagStatus.ABSTAINED,
                answer=answer,
                routing=decision,
            )

        filters = RetrievalFilter(tax_year=resolved_year) if resolved_year is not None else None
        try:
            if filters is None:
                results = self._retriever.retrieve(question, limit=retrieval_limit)
            else:
                results = self._retriever.retrieve(
                    question,
                    limit=retrieval_limit,
                    filters=filters,
                )
        except (TaxguideError, RuntimeError) as error:
            return self._failed(decision, f"retrieval failed: {error}")

        context = self._context_builder.build(results)
        policy = AbstentionPolicy(minimum_evidence=decision.minimum_evidence)
        if policy.should_abstain(context, citations_valid=True):
            return GroundedRagResult(
                status=GroundedRagStatus.ABSTAINED,
                answer=policy.abstain(
                    tax_year=resolved_year,
                    missing_information=["Retrieved evidence was insufficient."],
                ),
                routing=decision,
                evidence_count=len(context.evidence),
            )

        generated = self._generate(question, context, resolved_year, decision)
        if isinstance(generated, GroundedRagResult):
            return generated
        try:
            answer = RagAnswer.model_validate_json(generated)
        except ValidationError:
            return self._failed(
                decision,
                "generator returned invalid structured output",
                evidence_count=len(context.evidence),
                generator_model=self._generator.model_id,
            )

        try:
            self._citation_validator.validate(
                answer,
                context,
                expected_tax_year=resolved_year,
            )
        except CitationValidationError:
            safe_answer = policy.enforce(answer, context, citations_valid=False)
            return GroundedRagResult(
                status=GroundedRagStatus.ABSTAINED,
                answer=safe_answer,
                routing=decision,
                evidence_count=len(context.evidence),
                generator_model=self._generator.model_id,
            )

        return GroundedRagResult(
            status=GroundedRagStatus.ANSWERED,
            answer=policy.enforce(answer, context, citations_valid=True),
            routing=decision,
            evidence_count=len(context.evidence),
            generator_model=self._generator.model_id,
        )

    def _generate(
        self,
        question: str,
        context: GenerationContext,
        tax_year: int | None,
        decision: RoutingDecision,
    ) -> str | GroundedRagResult:
        messages = build_grounded_messages(question, context, tax_year=tax_year)
        try:
            return self._generator.generate(
                messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except RuntimeError as error:
            return self._failed(
                decision,
                f"generation failed: {error}",
                evidence_count=len(context.evidence),
                generator_model=self._generator.model_id,
            )

    @staticmethod
    def _failed(
        decision: RoutingDecision,
        message: str,
        *,
        evidence_count: int = 0,
        generator_model: str | None = None,
    ) -> GroundedRagResult:
        return GroundedRagResult(
            status=GroundedRagStatus.FAILED,
            routing=decision,
            evidence_count=evidence_count,
            generator_model=generator_model,
            error=message,
        )
