import pytest
from pydantic import ValidationError

from taxguide.domain.enums import TaxTopic
from taxguide.domain.taxonomy import ControlledTaxonomy, TopicMatch


def test_taxonomy_exposes_exact_controlled_vocabulary() -> None:
    assert ControlledTaxonomy().topics == tuple(TaxTopic)
    assert {topic.value for topic in TaxTopic} == {
        "income",
        "employment",
        "pension",
        "bank",
        "loan",
        "wealth",
        "property",
        "foreign_income",
        "foreign_assets",
        "deductions",
        "commuting",
        "family",
        "shares",
        "crypto",
        "self_employed",
        "paye",
        "tax_residency",
        "deadlines",
        "appeals",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Where do I declare a foreign bank account?", (TaxTopic.BANK, TaxTopic.FOREIGN_ASSETS)),
        ("Hvordan behandles kildeskatt på lønn?", (TaxTopic.EMPLOYMENT, TaxTopic.PAYE)),
        ("¿Puedo deducir el desplazamiento al trabajo?", (TaxTopic.DEDUCTIONS, TaxTopic.COMMUTING)),
    ],
)
def test_taxonomy_matches_multilingual_aliases_in_stable_order(
    text: str, expected: tuple[TaxTopic, ...]
) -> None:
    assert ControlledTaxonomy().match(text).topics == expected


def test_taxonomy_does_not_match_inside_larger_words() -> None:
    assert ControlledTaxonomy().match("The syntax is explained here.").topics == ()


def test_taxonomy_rejects_blank_text_and_unknown_topic_values() -> None:
    with pytest.raises(ValueError, match="text must not be empty"):
        ControlledTaxonomy().match("  ")
    with pytest.raises(ValidationError, match="topics"):
        TopicMatch.model_validate({"topics": ["not_controlled"]})


def test_custom_taxonomy_must_define_every_topic() -> None:
    with pytest.raises(ValueError, match="every controlled topic"):
        ControlledTaxonomy({TaxTopic.INCOME: ("income",)})
