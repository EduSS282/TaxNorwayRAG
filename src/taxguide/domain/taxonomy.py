"""Controlled vocabulary for Norwegian individual-tax topics."""

from collections.abc import Mapping, Sequence

from pydantic import field_validator

from taxguide.domain.enums import TaxTopic
from taxguide.domain.models import DomainModel
from taxguide.domain.text_matching import contains_term as _contains_term
from taxguide.domain.text_matching import normalize_query as _normalize


class TopicMatch(DomainModel):
    """Controlled topics found in text, in taxonomy order."""

    topics: tuple[TaxTopic, ...] = ()
    matched_terms: tuple[str, ...] = ()

    @field_validator("topics")
    @classmethod
    def unique_topics(cls, value: tuple[TaxTopic, ...]) -> tuple[TaxTopic, ...]:
        if len(value) != len(set(value)):
            raise ValueError("topics must be unique")
        return value


DEFAULT_TOPIC_ALIASES: Mapping[TaxTopic, tuple[str, ...]] = {
    TaxTopic.INCOME: (
        "income",
        "taxable income",
        "inntekt",
        "inntekter",
        "ingreso",
        "ingresos",
        "renta",
    ),
    TaxTopic.EMPLOYMENT: (
        "employment",
        "salary",
        "salaries",
        "wages",
        "arbeid",
        "lønn",
        "empleo",
        "salario",
        "salarios",
    ),
    TaxTopic.PENSION: ("pension", "pensions", "pensjon", "pensjoner", "pensión", "pensiones"),
    TaxTopic.BANK: (
        "bank",
        "banks",
        "bank account",
        "bank accounts",
        "bankkonto",
        "bankkontoer",
        "cuenta bancaria",
        "cuentas bancarias",
    ),
    TaxTopic.LOAN: (
        "loan",
        "loans",
        "mortgage",
        "mortgages",
        "interest expense",
        "loan interest",
        "lån",
        "gjeld",
        "gjeldsrenter",
        "préstamo",
        "préstamos",
        "hipoteca",
        "hipotecas",
    ),
    TaxTopic.WEALTH: ("wealth", "net wealth", "formue", "patrimonio"),
    TaxTopic.PROPERTY: (
        "property",
        "properties",
        "real estate",
        "home",
        "bolig",
        "eiendom",
        "inmueble",
        "vivienda",
        "viviendas",
        "rental income",
        "leieinntekter",
    ),
    TaxTopic.FOREIGN_INCOME: (
        "foreign income",
        "income abroad",
        "utenlandsk inntekt",
        "inntekt i utlandet",
        "ingresos extranjeros",
        "ingresos en el extranjero",
    ),
    TaxTopic.FOREIGN_ASSETS: (
        "foreign assets",
        "assets abroad",
        "foreign bank account",
        "foreign bank accounts",
        "utenlandske eiendeler",
        "formue i utlandet",
        "utenlandsk bankkonto",
        "activos extranjeros",
        "bienes en el extranjero",
        "cuenta bancaria extranjera",
        "cuentas bancarias extranjeras",
    ),
    TaxTopic.DEDUCTIONS: (
        "deduction",
        "deductions",
        "deduct",
        "deductible",
        "deductable",
        "deducted",
        "deductibility",
        "tax relief",
        "tax credit",
        "tax credits",
        "personal allowance",
        "standard deduction",
        "personfradrag",
        "personfradraget",
        "minstefradraget",
        "fradrag",
        "fradraget",
        "fradragene",
        "fradragsberettiget",
        "fradragsberettigede",
        "fradragsrett",
        "minstefradrag",
        "deducción",
        "deducciones",
        "deducir",
        "deducible",
        "deducibles",
        "desgravar",
        "desgravación",
        "desgravaciones",
    ),
    TaxTopic.COMMUTING: (
        "commuting",
        "commuter",
        "commuters",
        "travel to work",
        "pendler",
        "arbeidsreise",
        "desplazamiento al trabajo",
    ),
    TaxTopic.FAMILY: (
        "family",
        "childcare",
        "child care",
        "parental deduction",
        "familie",
        "foreldrefradrag",
        "familia",
        "guardería",
        "guarderías",
    ),
    TaxTopic.SHARES: (
        "shares",
        "stocks",
        "dividend",
        "dividends",
        "capital gains",
        "aksjer",
        "utbytte",
        "acciones",
        "dividendos",
        "ganancias patrimoniales",
    ),
    TaxTopic.CRYPTO: (
        "crypto",
        "cryptocurrency",
        "cryptocurrencies",
        "bitcoin",
        "kryptovaluta",
        "criptomoneda",
        "criptomonedas",
    ),
    TaxTopic.SELF_EMPLOYED: (
        "self-employed",
        "self employed",
        "sole proprietor",
        "næringsdrivende",
        "enkeltpersonforetak",
        "autónomo",
        "autónomos",
        "trabajador por cuenta propia",
    ),
    TaxTopic.PAYE: ("paye", "pay as you earn", "kildeskatt på lønn", "retención paye"),
    TaxTopic.TAX_RESIDENCY: (
        "tax residency",
        "tax resident",
        "fiscal residence",
        "skattemessig bosted",
        "skattemessig bosatt",
        "residencia fiscal",
        "residente fiscal",
    ),
    TaxTopic.DEADLINES: (
        "deadline",
        "deadlines",
        "due date",
        "filing date",
        "frist",
        "fristen",
        "frister",
        "fecha límite",
        "plazo",
    ),
    TaxTopic.APPEALS: (
        "appeal",
        "appeals",
        "complaint",
        "challenge a decision",
        "klage",
        "klager",
        "recurso",
        "reclamación",
    ),
}


class ControlledTaxonomy:
    """Match text to a closed set of topics without statistical inference."""

    def __init__(
        self,
        aliases: Mapping[TaxTopic, Sequence[str]] = DEFAULT_TOPIC_ALIASES,
    ) -> None:
        supplied = set(aliases)
        expected = set(TaxTopic)
        if supplied != expected:
            missing = sorted(topic.value for topic in expected - supplied)
            unexpected = sorted(str(topic) for topic in supplied - expected)
            raise ValueError(
                f"aliases must define every controlled topic; missing={missing}, "
                f"unexpected={unexpected}"
            )

        normalized: dict[TaxTopic, tuple[str, ...]] = {}
        for topic in TaxTopic:
            terms = tuple(dict.fromkeys(_normalize(term) for term in aliases[topic]))
            if not terms or any(not term for term in terms):
                raise ValueError(f"aliases for {topic.value} must contain non-blank terms")
            normalized[topic] = terms
        self._aliases = normalized

    @property
    def topics(self) -> tuple[TaxTopic, ...]:
        """Return the complete controlled vocabulary in stable order."""
        return tuple(TaxTopic)

    def match(self, text: str) -> TopicMatch:
        """Return all topics with aliases present as complete words or phrases."""
        normalized_text = _normalize(text)
        if not normalized_text:
            raise ValueError("text must not be empty")

        topics: list[TaxTopic] = []
        matched_terms: list[str] = []
        for topic in TaxTopic:
            matches = [
                term for term in self._aliases[topic] if _contains_term(normalized_text, term)
            ]
            if matches:
                topics.append(topic)
                matched_terms.extend(matches)
        return TopicMatch(topics=tuple(topics), matched_terms=tuple(matched_terms))
