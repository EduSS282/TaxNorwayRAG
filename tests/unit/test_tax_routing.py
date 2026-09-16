from taxguide.domain.enums import TaxTopic
from taxguide.domain.taxonomy import ControlledTaxonomy
from taxguide.query.classification import RuleBasedIntentClassifier
from taxguide.query.models import QueryIntent, RiskLevel
from taxguide.query.risk import RuleBasedRiskClassifier
from taxguide.rules.routing import DeterministicTaxRouter, RouteAction


def test_router_requires_year_for_year_sensitive_intent() -> None:
    decision = _router().route("Where do I report a foreign bank account?")

    assert decision.action is RouteAction.CLARIFY
    assert decision.requires_tax_year is True
    assert decision.filters.tax_year is None
    assert decision.filters.topics == (TaxTopic.BANK, TaxTopic.FOREIGN_ASSETS)
    assert decision.filters.official_sources_only is True
    assert decision.clarification_questions == ("Which tax year does your question concern?",)


def test_router_retrieves_with_explicit_year_and_controlled_filters() -> None:
    decision = _router().route("Where do I report a foreign bank account?", tax_year=2025)

    assert decision.action is RouteAction.RETRIEVE
    assert decision.classification.intent is QueryIntent.HOW_TO_REPORT
    assert decision.risk.level is RiskLevel.MEDIUM
    assert decision.filters.tax_year == 2025
    assert decision.filters.audience == "individual"
    assert decision.clarification_questions == ()
    assert decision.minimum_evidence == 1


def test_router_raises_evidence_threshold_for_high_risk_query() -> None:
    decision = _router().route("Can I opt out of PAYE tax?", tax_year=2025)

    assert decision.action is RouteAction.RETRIEVE
    assert decision.risk.level is RiskLevel.HIGH
    assert decision.minimum_evidence == 2
    assert decision.filters.topics == (TaxTopic.PAYE,)


def test_high_risk_subject_requires_year_even_with_general_intent() -> None:
    decision = _router().route("Explain how PAYE opt out works for tax.")

    assert decision.action is RouteAction.CLARIFY
    assert decision.classification.intent is QueryIntent.GENERAL_EXPLANATION
    assert decision.risk.level is RiskLevel.HIGH
    assert decision.requires_tax_year is True


def test_router_abstains_from_out_of_scope_query_without_retrieval() -> None:
    decision = _router().route("Write a poem about the sea.")

    assert decision.action is RouteAction.ABSTAIN
    assert decision.classification.intent is QueryIntent.OUT_OF_SCOPE
    assert decision.requires_tax_year is False
    assert "outside" in decision.reason


def test_general_explanation_can_route_without_silently_assigning_a_year() -> None:
    decision = _router().route("Explain Norwegian wealth tax.")

    assert decision.action is RouteAction.RETRIEVE
    assert decision.requires_tax_year is False
    assert decision.filters.tax_year is None
    assert decision.filters.topics == (TaxTopic.WEALTH,)


def _router() -> DeterministicTaxRouter:
    taxonomy = ControlledTaxonomy()
    return DeterministicTaxRouter(
        intent_classifier=RuleBasedIntentClassifier(taxonomy=taxonomy),
        risk_classifier=RuleBasedRiskClassifier(),
        taxonomy=taxonomy,
    )
