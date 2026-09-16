import pytest

from taxguide.query.tax_year import (
    TaxYearResolutionContext,
    TaxYearResolutionSource,
    TaxYearResolver,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("What was the rule in 2024?", 2024),
        ("Tax year 2025 standard deduction", 2025),
        ("Hva gjelder for inntektsåret 2026?", 2026),
        ("¿Qué declaraba en 2023?", 2023),
    ],
)
def test_explicit_year_is_extracted_multilingually(query: str, expected: int) -> None:
    result = TaxYearResolver().resolve(
        query,
        TaxYearResolutionContext(
            conversation_tax_year=2022,
            form_tax_year=2021,
            current_tax_year=2020,
        ),
    )

    assert result.tax_year == expected
    assert result.source is TaxYearResolutionSource.EXPLICIT


@pytest.mark.parametrize(
    ("context", "year", "source"),
    [
        (
            TaxYearResolutionContext(
                conversation_tax_year=2025, form_tax_year=2024, current_tax_year=2023
            ),
            2025,
            TaxYearResolutionSource.CONVERSATION,
        ),
        (
            TaxYearResolutionContext(form_tax_year=2024, current_tax_year=2023),
            2024,
            TaxYearResolutionSource.FORM,
        ),
        (
            TaxYearResolutionContext(current_tax_year=2023),
            2023,
            TaxYearResolutionSource.CURRENT,
        ),
    ],
)
def test_context_precedence_is_conversation_then_form_then_current(
    context: TaxYearResolutionContext, year: int, source: TaxYearResolutionSource
) -> None:
    result = TaxYearResolver().resolve("What applies?", context)

    assert (result.tax_year, result.source) == (year, source)


def test_multiple_explicit_years_require_clarification_instead_of_guessing() -> None:
    result = TaxYearResolver().resolve("Compare 2024 with 2025")

    assert result.tax_year is None
    assert result.mentioned_years == (2024, 2025)
    assert result.source is TaxYearResolutionSource.AMBIGUOUS
    assert result.needs_clarification


def test_missing_year_only_requires_clarification_when_caller_marks_it_essential() -> None:
    optional = TaxYearResolver().resolve("Explain this field")
    required = TaxYearResolver().resolve(
        "Explain this field", TaxYearResolutionContext(require_tax_year=True)
    )

    assert not optional.needs_clarification
    assert optional.source is TaxYearResolutionSource.UNRESOLVED
    assert required.needs_clarification
