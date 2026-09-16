"""Deterministic, inspectable risk classification for tax queries."""

import re
from collections.abc import Mapping, Sequence
from typing import Protocol

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
}

DEFAULT_HIGH_RISK_TERMS = (
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
    ) -> None:
        if set(intent_risk) != set(QueryIntent):
            raise ValueError("intent_risk must define every query intent")
        terms = tuple(dict.fromkeys(_normalize(term) for term in high_risk_terms))
        if not terms or any(not term for term in terms):
            raise ValueError("high_risk_terms must contain non-blank values")
        self._intent_risk = dict(intent_risk)
        self._high_risk_terms = terms

    def classify(self, query: str, classification: IntentClassification) -> RiskAssessment:
        normalized = _normalize(query)
        if not normalized:
            raise ValueError("query must not be empty")

        matched_overrides = tuple(
            term for term in self._high_risk_terms if _contains_term(normalized, term)
        )
        if matched_overrides:
            return RiskAssessment(
                level=RiskLevel.HIGH,
                reasons=tuple(f"high-risk subject: {term}" for term in matched_overrides),
            )

        level = self._intent_risk[classification.intent]
        return RiskAssessment(
            level=level,
            reasons=(f"{classification.intent.value} intent is classified as {level.value} risk",),
        )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.UNICODE) is not None
