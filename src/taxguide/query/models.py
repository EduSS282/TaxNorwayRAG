"""Typed outputs from deterministic query classifiers."""

from enum import StrEnum

from pydantic import field_validator

from taxguide.domain.models import DomainModel


class QueryIntent(StrEnum):
    DEADLINE = "deadline"
    FIELD_EXPLANATION = "field_explanation"
    ELIGIBILITY = "eligibility"
    HOW_TO_REPORT = "how_to_report"
    DOCUMENT_REQUIRED = "document_required"
    GENERAL_EXPLANATION = "general_explanation"
    OUT_OF_SCOPE = "out_of_scope"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IntentClassification(DomainModel):
    intent: QueryIntent
    matched_terms: tuple[str, ...] = ()

    @field_validator("matched_terms")
    @classmethod
    def non_blank_terms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not term.strip() for term in value):
            raise ValueError("matched_terms must not contain blank values")
        return value


class RiskAssessment(DomainModel):
    level: RiskLevel
    reasons: tuple[str, ...]

    @field_validator("reasons")
    @classmethod
    def reasons_are_present(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not reason.strip() for reason in value):
            raise ValueError("risk assessment must contain non-blank reasons")
        return value
