"""Curated routing regressions, not evidence of tax-answer accuracy."""

import unicodedata

import pytest

from taxguide.domain.taxonomy import ControlledTaxonomy
from taxguide.query.classification import RuleBasedIntentClassifier
from taxguide.query.models import QueryIntent, RiskLevel
from taxguide.rules.factory import create_tax_router
from taxguide.rules.routing import RouteAction

ELIGIBILITY = [
    "Can donations to NGOs deductible?",  # Original user report; imperfect grammar.
    "Are donations to NGOs deductible?",
    "Are charitable gifts tax-deductible?",
    "Are charitable gifts tax‑deductible?",
    "Can I deduct donations to charities?",
    "Can we deduct gifts to voluntary organisations?",
    "Can donations be deducted?",
    "Are donations deductable?",  # Explicitly supported common spelling variant.
    "Are donations not deductible?",
    "Which donations qualify for tax deductions?",
    "Am I eligible for the personal allowance?",
    "Can I claim a deduction for mortgage interest?",
    "Do I have to pay tax for my home?",
    "Is it taxable if I sell shares?",
    "Are gifts tax exempt?",
    "¿Son deducibles las donaciones a ONGs?",
    "Son deducibles las donaciones a una ONG?",
    "¿Puedo desgravar donaciones?",
    "¿Podemos deducir los intereses de la hipoteca?",
    "¿Está exento de impuestos este ingreso?",
    "¿Hay que declarar ingresos extranjeros?",
    "Er gaver til frivillige organisasjoner fradragsberettiget?",
    "Er donasjoner fradragsberettigede?",
    "Kan jeg trekke fra gjeldsrenter?",
    "Kan jeg få fradrag for gaver?",
    "Har jeg rett til fradrag for arbeidsreise?",
    "Er utbytte skattepliktig?",
    "Når må jeg betale skatt på skattepliktig utbytte?",
    "When is a donation deductible?",  # 'When is' alone is not a deadline.
    "Can I deduct a course to bake bread?",
    "Can I deduct a course to write a poem?",
    "¿Puedo deducir un libro con una receta de cocina?",
]

REPORTING = [
    "Can I deduct loan interest and where do I enter it?",
    "How do I report dividends?",
    "How can I report cryptocurrencies?",
    "Where do I declare foreign bank accounts?",
    "Where can I enter mortgage interest?",
    "How do I amend my tax return?",
    "How to report foreign income?",
    "¿Dónde declaro cuentas bancarias extranjeras?",
    "Donde declaro cuentas bancarias extranjeras?",
    "¿Cómo declarar dividendos?",
    "Como corrijo mi declaracion de la renta?",
    "Hvor skal jeg føre gjeldsrenter?",
    "Hvordan endrer jeg skattemeldingen?",
]

DOCUMENTS = [
    "What paperwork do I need for tax deductions?",
    "Which receipts support my commuting deduction?",
    "What evidence is needed for a tax deduction?",
    "Should I keep receipts for deductions?",
    "What documents show my donation is deductible?",
    "Qué justificantes necesito para una deducción?",
    "Que recibos debo guardar para deducir gastos?",
    "Hvilke dokumenter trenger jeg for fradrag?",
    "Trenger jeg kvittering for fradraget?",
]

DEADLINES = [
    "What are the tax return deadlines?",
    "By when should I submit my tax return?",
    "What is the last day to file taxes?",
    "When must I file my tax return?",
    "¿Hasta cuándo puedo presentar mi declaración de la renta?",
    "Hasta cuando puedo presentar mi declaracion de la renta?",
    "Når må jeg levere skattemeldingen?",
    "Når skal jeg levere skattemeldingen?",
    "Hva er fristen for skattemeldingen?",
]

GENERAL = [
    "Explain Norwegian wealth tax.",
    "What does PAYE mean?",  # Not a form field.
    "Hva betyr skattekort?",
    "Qué significa impuesto sobre el patrimonio?",
    "What should I check before making a deduction?",
    "Explain deductions for donations to NGOs.",
    "What is personal allowance?",
    "Explain pensions and salaries.",
    "Explain capital gains.",
    "Explain self‑employed income tax.",
    "Explain taxation of foreign assets.",
]

FIELDS = [
    "What does this tax return field mean?",
    "What is this field on my tax return?",
    "Explain field 3 in the tax return.",
    "Hva betyr dette felt i skattemeldingen?",
    "Que significa esta casilla de la declaracion de la renta?",
]

UNCERTAIN = [
    "Which NGO should I support?",
    "Can I donate to a charity?",
    "Which charity is best?",
    "Donations to NGOs?",
    "¿Qué ONG recomiendas?",
    "Hvilken organisasjon bør jeg støtte?",
    "How do I paint my home?",
    "What is the bank opening time?",
    "Tell me about my family.",
    "Where can I buy stocks?",
    "What is the project deadline?",
    "How do I appeal a parking ticket?",
    "Can I claim this?",
    "What about it?",
    "syntax taxi taxonomy deductedness",
    "Nonsense asdfgh",
    "¿Cómo arreglo mi vivienda?",
    "Når åpner banken?",
]

OUTSIDE = [
    "Write a poem about the sea.",
    "Write a poem about Norwegian tax.",
    "Please write a poem about Norwegian tax.",
    "Could you write a song about taxes?",
    "How do I bake sourdough bread?",
    "Tell me a joke about tax.",
    "What is the weather forecast?",
    "Escribe un poema sobre impuestos.",
    "Dame una receta de cocina.",
    "Skriv et dikt om skatt.",
    "Fortell en vits.",
]

CASES = [
    *[(query, QueryIntent.ELIGIBILITY) for query in ELIGIBILITY],
    *[(query, QueryIntent.HOW_TO_REPORT) for query in REPORTING],
    *[(query, QueryIntent.DOCUMENT_REQUIRED) for query in DOCUMENTS],
    *[(query, QueryIntent.DEADLINE) for query in DEADLINES],
    *[(query, QueryIntent.GENERAL_EXPLANATION) for query in GENERAL],
    *[(query, QueryIntent.FIELD_EXPLANATION) for query in FIELDS],
    *[(query, QueryIntent.UNCERTAIN) for query in UNCERTAIN],
    *[(query, QueryIntent.OUT_OF_SCOPE) for query in OUTSIDE],
]


@pytest.mark.parametrize("query,intent", CASES)
def test_curated_multilingual_intents(query: str, intent: QueryIntent) -> None:
    result = RuleBasedIntentClassifier(taxonomy=ControlledTaxonomy()).classify(query)
    assert result.intent is intent
    if intent not in {QueryIntent.UNCERTAIN}:
        assert result.matched_terms


@pytest.mark.parametrize("query,intent", CASES)
@pytest.mark.parametrize("year", [None, 2026])
def test_routing_invariants_with_and_without_year(
    query: str, intent: QueryIntent, year: int | None
) -> None:
    route = create_tax_router().route(query, tax_year=year)
    assert route.filters.tax_year == year
    assert route.filters.official_sources_only
    if intent is QueryIntent.OUT_OF_SCOPE:
        assert route.action is RouteAction.ABSTAIN
    elif intent is QueryIntent.UNCERTAIN:
        assert route.action is RouteAction.CLARIFY
        assert not route.requires_tax_year
        assert "issue" in route.clarification_questions[0]
    elif route.requires_tax_year and year is None:
        assert route.action is RouteAction.CLARIFY
        assert "year" in route.clarification_questions[0]
    else:
        assert route.action is RouteAction.RETRIEVE
    if intent is QueryIntent.ELIGIBILITY:
        assert route.risk.level is RiskLevel.HIGH
        assert route.requires_tax_year
        assert route.minimum_evidence == 2


@pytest.mark.parametrize(
    "query",
    [
        "What is the maximum deduction for donations?",
        "What tax rate applies to salary?",
        "What is the deduction limit?",
        "Is rental income taxable?",
        "How much tax do I pay?",
        "¿Cuál es el límite de la deducción?",
        "Cuanto impuesto tengo que pagar?",
        "Hva er satsen for skatt?",
        "Hva er beløpet for minstefradraget?",
        "What documents show I am eligible for a deduction?",
        "Can I deduct loan interest and where do I enter it?",
        "When is the tax deadline and can I deduct donations?",
    ],
)
def test_numeric_and_mixed_intents_cannot_bypass_high_risk(query: str) -> None:
    without_year = create_tax_router().route(query)
    with_year = create_tax_router().route(query, tax_year=2026)
    assert without_year.action is RouteAction.CLARIFY
    assert with_year.action is RouteAction.RETRIEVE
    assert with_year.risk.level is RiskLevel.HIGH
    assert with_year.minimum_evidence == 2


@pytest.mark.parametrize(
    "transform",
    [str.upper, lambda s: unicodedata.normalize("NFD", s), lambda s: s.replace(" ", "  \t")],
)
@pytest.mark.parametrize("query", [ELIGIBILITY[0], ELIGIBILITY[16], ELIGIBILITY[22]])
def test_typographic_variants_do_not_change_intent(query, transform) -> None:
    router = create_tax_router()
    assert router.route(transform(query)).classification.intent is QueryIntent.ELIGIBILITY


def test_shared_normalization_preserves_norwegian_and_word_boundaries() -> None:
    taxonomy = ControlledTaxonomy()
    assert taxonomy.match("LÅN og lønn").topics == taxonomy.match("lån og lønn").topics
    assert taxonomy.match("deductedness taxing syntaxes").topics == ()
    assert (
        create_tax_router().route("What does PAYE mean?").classification.intent
        is QueryIntent.GENERAL_EXPLANATION
    )


def test_risk_eligibility_terms_remain_injectable() -> None:
    from taxguide.query.models import IntentClassification
    from taxguide.query.risk import RuleBasedRiskClassifier

    low = IntentClassification(intent=QueryIntent.GENERAL_EXPLANATION)
    custom = RuleBasedRiskClassifier(eligibility_terms=("special case",))
    assert custom.classify("tax special case", low).level is RiskLevel.HIGH
    assert custom.classify("tax eligible", low).level is RiskLevel.LOW
    with pytest.raises(ValueError, match="eligibility_terms"):
        RuleBasedRiskClassifier(eligibility_terms=(" ",))
