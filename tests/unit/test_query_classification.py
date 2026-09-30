import pytest

from taxguide.domain.taxonomy import ControlledTaxonomy
from taxguide.query.classification import RuleBasedIntentClassifier
from taxguide.query.models import QueryIntent


@pytest.fixture
def classifier() -> RuleBasedIntentClassifier:
    return RuleBasedIntentClassifier(taxonomy=ControlledTaxonomy())


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("What is the tax return deadline?", QueryIntent.DEADLINE),
        ("What documents do I need for a commuting deduction?", QueryIntent.DOCUMENT_REQUIRED),
        ("Where do I report my foreign bank account?", QueryIntent.HOW_TO_REPORT),
        ("Can I deduct commuting costs on my tax return?", QueryIntent.ELIGIBILITY),
        ("What does this tax return field mean?", QueryIntent.FIELD_EXPLANATION),
        ("Explain Norwegian wealth tax.", QueryIntent.GENERAL_EXPLANATION),
        ("How do I bake sourdough bread?", QueryIntent.OUT_OF_SCOPE),
        ("¿Dónde declaro una cuenta bancaria extranjera?", QueryIntent.HOW_TO_REPORT),
        ("Når må jeg levere skattemeldingen?", QueryIntent.DEADLINE),
    ],
)
def test_classifier_assigns_controlled_intent(
    classifier: RuleBasedIntentClassifier, query: str, expected: QueryIntent
) -> None:
    assert classifier.classify(query).intent is expected


def test_classifier_priority_is_deterministic() -> None:
    classifier = RuleBasedIntentClassifier(taxonomy=ControlledTaxonomy())

    result = classifier.classify("When is the deadline and what documents does my tax return need?")

    assert result.intent is QueryIntent.DEADLINE
    assert result.matched_terms == ("deadline", "when is")


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_classifier_rejects_blank_queries(
    classifier: RuleBasedIntentClassifier, query: str
) -> None:
    with pytest.raises(ValueError, match="query must not be empty"):
        classifier.classify(query)
