"""Deterministic routing rules for safe, source-first tax answers."""

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from taxguide.domain.enums import TaxTopic
from taxguide.domain.models import DomainModel
from taxguide.domain.taxonomy import ControlledTaxonomy
from taxguide.query.classification import IntentClassifier
from taxguide.query.models import IntentClassification, QueryIntent, RiskAssessment, RiskLevel
from taxguide.query.risk import RiskClassifier


class RouteAction(StrEnum):
    RETRIEVE = "retrieve"
    CLARIFY = "clarify"
    ABSTAIN = "abstain"


class RoutingFilters(DomainModel):
    """Provider-neutral retrieval constraints chosen by the rule engine."""

    tax_year: int | None = Field(default=None, ge=1900, le=2100)
    topics: tuple[TaxTopic, ...] = ()
    audience: str = "individual"
    official_sources_only: bool = True

    @field_validator("topics")
    @classmethod
    def topics_are_unique(cls, value: tuple[TaxTopic, ...]) -> tuple[TaxTopic, ...]:
        if len(value) != len(set(value)):
            raise ValueError("routing topics must be unique")
        return value


class RoutingDecision(DomainModel):
    """Auditable instructions for later retrieval and generation stages."""

    action: RouteAction
    classification: IntentClassification
    risk: RiskAssessment
    filters: RoutingFilters
    requires_tax_year: bool
    minimum_evidence: int = Field(ge=1)
    clarification_questions: tuple[str, ...] = ()
    reason: str = Field(min_length=1)

    @field_validator("clarification_questions")
    @classmethod
    def questions_are_non_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not question.strip() for question in value):
            raise ValueError("clarification questions must not be blank")
        return value

    @model_validator(mode="after")
    def action_is_consistent(self) -> "RoutingDecision":
        if self.action is RouteAction.CLARIFY and not self.clarification_questions:
            raise ValueError("clarify routes must include a clarification question")
        if self.action is not RouteAction.CLARIFY and self.clarification_questions:
            raise ValueError("only clarify routes may include clarification questions")
        if (
            self.action is RouteAction.RETRIEVE
            and self.requires_tax_year
            and self.filters.tax_year is None
        ):
            raise ValueError("retrieval cannot omit a required tax year")
        return self


_INTENTS_REQUIRING_TAX_YEAR = frozenset(
    {
        QueryIntent.DEADLINE,
        QueryIntent.ELIGIBILITY,
        QueryIntent.HOW_TO_REPORT,
        QueryIntent.DOCUMENT_REQUIRED,
        QueryIntent.FIELD_EXPLANATION,
    }
)


class DeterministicTaxRouter:
    """Compose injected classifiers into a side-effect-free routing decision."""

    def __init__(
        self,
        *,
        intent_classifier: IntentClassifier,
        risk_classifier: RiskClassifier,
        taxonomy: ControlledTaxonomy,
    ) -> None:
        self._intent_classifier = intent_classifier
        self._risk_classifier = risk_classifier
        self._taxonomy = taxonomy

    def route(self, query: str, *, tax_year: int | None = None) -> RoutingDecision:
        """Decide whether to retrieve, clarify or abstain; never generate tax advice."""
        classification = self._intent_classifier.classify(query)
        risk = self._risk_classifier.classify(query, classification)
        topics = self._taxonomy.match(query).topics
        filters = RoutingFilters(tax_year=tax_year, topics=topics)
        requires_tax_year = (
            classification.intent in _INTENTS_REQUIRING_TAX_YEAR or risk.level is RiskLevel.HIGH
        )
        minimum_evidence = 2 if risk.level is RiskLevel.HIGH else 1

        if classification.intent is QueryIntent.OUT_OF_SCOPE:
            return RoutingDecision(
                action=RouteAction.ABSTAIN,
                classification=classification,
                risk=risk,
                filters=filters,
                requires_tax_year=False,
                minimum_evidence=minimum_evidence,
                reason="The query is outside the supported Norwegian individual-tax scope.",
            )

        if requires_tax_year and tax_year is None:
            return RoutingDecision(
                action=RouteAction.CLARIFY,
                classification=classification,
                risk=risk,
                filters=filters,
                requires_tax_year=True,
                minimum_evidence=minimum_evidence,
                clarification_questions=("Which tax year does your question concern?",),
                reason="This intent can change between tax years; a year must be explicit.",
            )

        return RoutingDecision(
            action=RouteAction.RETRIEVE,
            classification=classification,
            risk=risk,
            filters=filters,
            requires_tax_year=requires_tax_year,
            minimum_evidence=minimum_evidence,
            reason="Retrieve official evidence using the selected controlled filters.",
        )
