"""Controlled vocabulary for Norwegian individual-tax topics."""

import re
from collections.abc import Mapping, Sequence

from pydantic import field_validator

from taxguide.domain.enums import TaxTopic
from taxguide.domain.models import DomainModel


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
    TaxTopic.INCOME: ("income", "taxable income", "inntekt", "ingresos", "renta"),
    TaxTopic.EMPLOYMENT: (
        "employment",
        "salary",
        "wages",
        "arbeid",
        "lønn",
        "empleo",
        "salario",
    ),
    TaxTopic.PENSION: ("pension", "pensjon", "pensión"),
    TaxTopic.BANK: ("bank", "bank account", "bankkonto", "cuenta bancaria"),
    TaxTopic.LOAN: ("loan", "interest expense", "lån", "gjeld", "préstamo", "hipoteca"),
    TaxTopic.WEALTH: ("wealth", "net wealth", "formue", "patrimonio"),
    TaxTopic.PROPERTY: (
        "property",
        "real estate",
        "home",
        "bolig",
        "eiendom",
        "inmueble",
        "vivienda",
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
        "utenlandske eiendeler",
        "formue i utlandet",
        "utenlandsk bankkonto",
        "activos extranjeros",
        "bienes en el extranjero",
        "cuenta bancaria extranjera",
    ),
    TaxTopic.DEDUCTIONS: (
        "deduction",
        "deductions",
        "deduct",
        "fradrag",
        "deducción",
        "deducciones",
        "deducir",
    ),
    TaxTopic.COMMUTING: (
        "commuting",
        "commuter",
        "travel to work",
        "pendler",
        "arbeidsreise",
        "desplazamiento al trabajo",
    ),
    TaxTopic.FAMILY: (
        "family",
        "childcare",
        "parental deduction",
        "familie",
        "foreldrefradrag",
        "familia",
        "guardería",
    ),
    TaxTopic.SHARES: ("shares", "stocks", "dividend", "aksjer", "utbytte", "acciones"),
    TaxTopic.CRYPTO: (
        "crypto",
        "cryptocurrency",
        "bitcoin",
        "kryptovaluta",
        "criptomoneda",
    ),
    TaxTopic.SELF_EMPLOYED: (
        "self-employed",
        "self employed",
        "sole proprietor",
        "næringsdrivende",
        "enkeltpersonforetak",
        "autónomo",
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
        "due date",
        "filing date",
        "frist",
        "fecha límite",
        "plazo",
    ),
    TaxTopic.APPEALS: (
        "appeal",
        "complaint",
        "challenge a decision",
        "klage",
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


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.UNICODE) is not None
