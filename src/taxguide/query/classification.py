"""Replaceable deterministic query-intent classification."""

import re
from collections.abc import Mapping, Sequence
from typing import Protocol

from taxguide.domain.taxonomy import ControlledTaxonomy
from taxguide.query.models import IntentClassification, QueryIntent


class IntentClassifier(Protocol):
    """Classify a query into the controlled intent vocabulary."""

    def classify(self, query: str) -> IntentClassification: ...


DEFAULT_INTENT_TERMS: Mapping[QueryIntent, tuple[str, ...]] = {
    QueryIntent.DEADLINE: (
        "deadline",
        "due date",
        "when is",
        "when do i file",
        "frist",
        "når må",
        "fecha límite",
        "plazo",
        "cuándo tengo que presentar",
    ),
    QueryIntent.DOCUMENT_REQUIRED: (
        "what documents",
        "which documents",
        "documentation required",
        "need a receipt",
        "need receipts",
        "supporting document",
        "hvilke dokumenter",
        "dokumentasjon",
        "kvittering",
        "qué documentos",
        "documentación necesaria",
        "necesito un recibo",
    ),
    QueryIntent.HOW_TO_REPORT: (
        "how do i report",
        "how should i report",
        "where do i report",
        "where should i report",
        "where do i enter",
        "which field",
        "hvordan fører",
        "hvor fører",
        "hvordan rapporterer",
        "cómo declaro",
        "cómo se declara",
        "dónde declaro",
        "en qué campo",
    ),
    QueryIntent.ELIGIBILITY: (
        "am i eligible",
        "can i claim",
        "can i deduct",
        "do i have to",
        "must i",
        "am i required",
        "does this apply",
        "må jeg",
        "kan jeg kreve",
        "har jeg rett",
        "tengo que",
        "debo",
        "puedo deducir",
        "tengo derecho",
        "me aplica",
    ),
    QueryIntent.FIELD_EXPLANATION: (
        "what does",
        "what is this field",
        "explain field",
        "meaning of field",
        "what is box",
        "hva betyr",
        "forklar felt",
        "hva er post",
        "qué significa",
        "explica el campo",
        "qué es la casilla",
    ),
    QueryIntent.GENERAL_EXPLANATION: (
        "what is",
        "explain",
        "how does",
        "overview",
        "hva er",
        "forklar",
        "hvordan fungerer",
        "qué es",
        "explica",
        "cómo funciona",
    ),
    QueryIntent.OUT_OF_SCOPE: (),
}

_EXPLICIT_TAX_SCOPE_TERMS = (
    "tax",
    "tax return",
    "taxable",
    "skatt",
    "skattemelding",
    "skattemeldingen",
    "skatteetaten",
    "impuesto",
    "fiscal",
    "declaración de la renta",
    "form rf-",
)


class RuleBasedIntentClassifier:
    """Classify common English, Norwegian and Spanish queries predictably."""

    def __init__(
        self,
        *,
        taxonomy: ControlledTaxonomy,
        terms: Mapping[QueryIntent, Sequence[str]] = DEFAULT_INTENT_TERMS,
    ) -> None:
        supplied = set(terms)
        expected = set(QueryIntent)
        if supplied != expected:
            missing = expected - supplied
            unexpected = supplied - expected
            raise ValueError(
                "terms must define every intent; "
                f"missing={sorted(intent.value for intent in missing)}, "
                f"unexpected={sorted(str(intent) for intent in unexpected)}"
            )
        self._taxonomy = taxonomy
        self._terms = {
            intent: tuple(dict.fromkeys(_normalize(term) for term in terms[intent]))
            for intent in QueryIntent
        }
        for intent, intent_terms in self._terms.items():
            if intent is QueryIntent.OUT_OF_SCOPE:
                continue
            if not intent_terms or any(not term for term in intent_terms):
                raise ValueError(f"terms for {intent.value} must contain non-blank values")

    def classify(self, query: str) -> IntentClassification:
        normalized = _normalize(query)
        if not normalized:
            raise ValueError("query must not be empty")

        if not self._is_tax_scope(normalized):
            return IntentClassification(intent=QueryIntent.OUT_OF_SCOPE)

        for intent in (
            QueryIntent.DEADLINE,
            QueryIntent.DOCUMENT_REQUIRED,
            QueryIntent.HOW_TO_REPORT,
            QueryIntent.ELIGIBILITY,
            QueryIntent.FIELD_EXPLANATION,
            QueryIntent.GENERAL_EXPLANATION,
        ):
            matches = tuple(
                term for term in self._terms[intent] if _contains_term(normalized, term)
            )
            if matches:
                return IntentClassification(intent=intent, matched_terms=matches)

        return IntentClassification(intent=QueryIntent.GENERAL_EXPLANATION)

    def _is_tax_scope(self, normalized_query: str) -> bool:
        if any(_contains_term(normalized_query, term) for term in _EXPLICIT_TAX_SCOPE_TERMS):
            return True
        return bool(self._taxonomy.match(normalized_query).topics)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.UNICODE) is not None
