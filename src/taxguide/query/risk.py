"""Deterministic, inspectable risk classification for tax queries."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from taxguide.domain.text_matching import contains_term as _contains_term
from taxguide.domain.text_matching import normalize_query as _normalize
from taxguide.query.classification import DEFAULT_INTENT_TERMS
from taxguide.query.models import IntentClassification, QueryIntent, RiskAssessment, RiskLevel


class RiskClassifier(Protocol):
    """Assess the consequence risk of answering a classified query."""

    def classify(self, query: str, classification: IntentClassification) -> RiskAssessment: ...


DEFAULT_INTENT_RISK: Mapping[QueryIntent, RiskLevel] = {
    QueryIntent.GENERAL_EXPLANATION: RiskLevel.LOW,
    QueryIntent.FIELD_EXPLANATION: RiskLevel.MEDIUM,
    QueryIntent.DEADLINE: RiskLevel.MEDIUM,
    QueryIntent.DOCUMENT_REQUIRED: RiskLevel.MEDIUM,
    QueryIntent.HOW_TO_REPORT: RiskLevel.MEDIUM,
    QueryIntent.ELIGIBILITY: RiskLevel.HIGH,
    QueryIntent.OUT_OF_SCOPE: RiskLevel.HIGH,
    QueryIntent.UNCERTAIN: RiskLevel.HIGH,
}

DEFAULT_HIGH_RISK_TERMS = (
    "how much",
    "amount",
    "amounts",
    "rate",
    "rates",
    "threshold",
    "thresholds",
    "upper limit",
    "limit",
    "limits",
    "maximum",
    "minimum",
    "percentage",
    "percent",
    "hvor mye",
    "beløp",
    "beløpet",
    "sats",
    "satser",
    "satsen",
    "satsene",
    "grense",
    "grensen",
    "prosent",
    "cuánto",
    "cuánta",
    "importe",
    "cuantía",
    "límite",
    "límites",
    "importes",
    "cuantías",
    "tarifa",
    "tarifas",
    "máximo",
    "mínimo",
    "porcentaje",
    "paye opt out",
    "opt out of paye",
    "leave paye",
    "melde meg ut av kildeskatt",
    "salir de paye",
    "tax residency",
    "tax resident",
    "skattemessig bosatt",
    "residencia fiscal",
    "appeal",
    "klage",
    "recurso",
)


class RuleBasedRiskClassifier:
    """Map intent to risk and apply conservative high-risk subject overrides."""

    def __init__(
        self,
        *,
        intent_risk: Mapping[QueryIntent, RiskLevel] = DEFAULT_INTENT_RISK,
        high_risk_terms: Sequence[str] = DEFAULT_HIGH_RISK_TERMS,
        eligibility_terms: Sequence[str] = DEFAULT_INTENT_TERMS[QueryIntent.ELIGIBILITY],
    ) -> None:
        if set(intent_risk) != set(QueryIntent):
            raise ValueError("intent_risk must define every query intent")
        terms = tuple(dict.fromkeys(_normalize(term) for term in high_risk_terms))
        if not terms or any(not term for term in terms):
            raise ValueError("high_risk_terms must contain non-blank values")
        self._intent_risk = dict(intent_risk)
        self._high_risk_terms = terms
        self._eligibility_terms = tuple(dict.fromkeys(_normalize(t) for t in eligibility_terms))
        if any(not term for term in self._eligibility_terms):
            raise ValueError("eligibility_terms must not contain blank values")

    def classify(self, query: str, classification: IntentClassification) -> RiskAssessment:
        normalized = _normalize(query)
        if not normalized:
            raise ValueError("query must not be empty")

        matched_overrides = tuple(
            term for term in self._high_risk_terms if _contains_term(normalized, term)
        )
        eligibility = tuple(
            term for term in self._eligibility_terms if _contains_term(normalized, term)
        )
        if matched_overrides or eligibility:
            return RiskAssessment(
                level=RiskLevel.HIGH,
                reasons=(
                    *(f"high-risk subject: {term}" for term in matched_overrides),
                    *(f"eligibility phrase: {term}" for term in eligibility),
                ),
            )

        level = self._intent_risk[classification.intent]
        return RiskAssessment(
            level=level,
            reasons=(f"{classification.intent.value} intent is classified as {level.value} risk",),
        )
