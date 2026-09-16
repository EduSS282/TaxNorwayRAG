import pytest

from taxguide.query.models import IntentClassification, QueryIntent, RiskLevel
from taxguide.query.risk import RuleBasedRiskClassifier


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        (QueryIntent.GENERAL_EXPLANATION, RiskLevel.LOW),
        (QueryIntent.FIELD_EXPLANATION, RiskLevel.MEDIUM),
        (QueryIntent.DEADLINE, RiskLevel.MEDIUM),
        (QueryIntent.HOW_TO_REPORT, RiskLevel.MEDIUM),
        (QueryIntent.ELIGIBILITY, RiskLevel.HIGH),
        (QueryIntent.OUT_OF_SCOPE, RiskLevel.HIGH),
    ],
)
def test_risk_classifier_uses_explicit_intent_mapping(
    intent: QueryIntent, expected: RiskLevel
) -> None:
    result = RuleBasedRiskClassifier().classify(
        "A Norwegian tax question", IntentClassification(intent=intent)
    )

    assert result.level is expected
    assert result.reasons


@pytest.mark.parametrize(
    "query",
    [
        "How do I opt out of PAYE?",
        "Explain whether I am tax resident in Norway.",
        "Hvordan sender jeg en klage?",
        "¿Cómo presento un recurso fiscal?",
    ],
)
def test_high_consequence_subjects_override_lower_intent_risk(query: str) -> None:
    result = RuleBasedRiskClassifier().classify(
        query, IntentClassification(intent=QueryIntent.GENERAL_EXPLANATION)
    )

    assert result.level is RiskLevel.HIGH
    assert result.reasons[0].startswith("high-risk subject:")


def test_risk_classifier_rejects_blank_query() -> None:
    with pytest.raises(ValueError, match="query must not be empty"):
        RuleBasedRiskClassifier().classify(
            " ", IntentClassification(intent=QueryIntent.GENERAL_EXPLANATION)
        )
