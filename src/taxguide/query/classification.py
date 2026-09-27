"""Replaceable deterministic query-intent classification."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from taxguide.domain.taxonomy import ControlledTaxonomy
from taxguide.domain.text_matching import contains_term as _contains_term
from taxguide.domain.text_matching import normalize_query as _normalize
from taxguide.query.models import IntentClassification, QueryIntent


class IntentClassifier(Protocol):
    """Classify a query into the controlled intent vocabulary."""

    def classify(self, query: str) -> IntentClassification: ...


DEFAULT_INTENT_TERMS: Mapping[QueryIntent, tuple[str, ...]] = {
    QueryIntent.DEADLINE: (
        "deadline",
        "deadlines",
        "due date",
        "due",
        "forfaller",
        "vencimiento",
        "vence",
        "vencen",
        "when is",
        "when do i file",
        "when must i file",
        "when should i file",
        "last day",
        "by when",
        "frist",
        "fristen",
        "frister",
        "når må",
        "når må jeg levere",
        "når skal jeg levere",
        "når skal jeg betale",
        "fecha límite",
        "plazo",
        "hasta cuándo",
        "cuándo tengo que presentar",
    ),
    QueryIntent.DOCUMENT_REQUIRED: (
        "what documents",
        "which documents",
        "documentation required",
        "what paperwork",
        "which receipts",
        "what evidence",
        "proof required",
        "keep receipts",
        "documentation",
        "need a receipt",
        "need receipts",
        "supporting document",
        "hvilke dokumenter",
        "dokumentasjon",
        "kvittering",
        "qué documentos",
        "qué justificantes",
        "qué recibos",
        "guardar recibos",
        "documentación necesaria",
        "necesito un recibo",
    ),
    QueryIntent.HOW_TO_REPORT: (
        "how do i report",
        "how can i report",
        "how to report",
        "how do i declare",
        "where do i declare",
        "where can i enter",
        "where to enter",
        "how do i correct",
        "how do i amend",
        "how do i file",
        "how should i report",
        "where do i report",
        "where should i report",
        "where do i enter",
        "which field",
        "hvordan fører",
        "hvor fører",
        "hvor skal jeg føre",
        "hvordan endrer",
        "hvordan rapporterer",
        "cómo declaro",
        "cómo declarar",
        "cómo corrijo",
        "cómo se declara",
        "dónde declaro",
        "en qué campo",
    ),
    QueryIntent.ELIGIBILITY: (
        "am i eligible",
        "can i claim",
        "can i deduct",
        "can we deduct",
        "can i get a deduction",
        "eligible",
        "eligibility",
        "deductible",
        "deductable",
        "deducted",
        "deductibility",
        "taxable",
        "sujeto a impuestos",
        "sujeta a impuestos",
        "claim a deduction",
        "qualify for",
        "qualifies for",
        "tax exempt",
        "tax exemption",
        "tax free",
        "do i need to pay",
        "is it taxable",
        "are they taxable",
        "liable for tax",
        "do i have to",
        "must i",
        "am i required",
        "does this apply",
        "må jeg",
        "kan jeg kreve",
        "kan jeg trekke fra",
        "kan jeg få fradrag",
        "fradragsberettiget",
        "fradragsberettigede",
        "rett til fradrag",
        "skattepliktig",
        "skattepliktige",
        "skattefri",
        "har jeg rett",
        "tengo que",
        "debo",
        "puedo deducir",
        "podemos deducir",
        "deducible",
        "deducibles",
        "puedo desgravar",
        "está exento",
        "están exentos",
        "hay que declarar",
        "tengo que tributar",
        "tengo derecho",
        "me aplica",
    ),
    QueryIntent.FIELD_EXPLANATION: (
        "what does",
        "what do",
        "what is this field",
        "explain field",
        "meaning of field",
        "what is box",
        "tax return field",
        "field meaning",
        "hva betyr",
        "forklar felt",
        "hva er post",
        "qué significa",
        "qué significan",
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
    QueryIntent.UNCERTAIN: (),
}

_EXPLICIT_TAX_SCOPE_TERMS = (
    "tax",
    "taxes",
    "taxation",
    "tax return",
    "taxable",
    "deductible",
    "deductibility",
    "skatt",
    "skattepliktig",
    "skattepliktige",
    "skattefri",
    "skattefradrag",
    "skattekort",
    "skatteoppgjør",
    "skatteoppgjøret",
    "skattemelding",
    "skattemeldingen",
    "skatteetaten",
    "impuesto",
    "impuestos",
    "tributar",
    "tributación",
    "fiscal",
    "declaración de la renta",
    "form rf-",
)

# These topic aliases are ambiguous without a fiscal phrase. Topic matching is
# descriptive; it must not by itself authorize arbitrary questions about a home.
_AMBIGUOUS_SCOPE_TERMS = frozenset(
    _normalize(term)
    for term in (
        "home",
        "property",
        "properties",
        "real estate",
        "bolig",
        "eiendom",
        "inmueble",
        "vivienda",
        "viviendas",
        "bank",
        "banks",
        "family",
        "familie",
        "familia",
        "shares",
        "stocks",
        "acciones",
        "appeal",
        "appeals",
        "complaint",
        "klage",
        "klager",
        "recurso",
        "reclamación",
        "deadline",
        "deadlines",
        "due date",
        "filing date",
        "frist",
        "fristen",
        "frister",
        "fecha límite",
        "plazo",
        "employment",
        "arbeid",
        "empleo",
    )
)

_UNRELATED_REQUESTS = (
    "write a poem",
    "write a song",
    "tell me a joke",
    "bake sourdough",
    "bake bread",
    "weather forecast",
    "football score",
    "escribe un poema",
    "cuéntame un chiste",
    "receta de cocina",
    "pronóstico del tiempo",
    "skriv et dikt",
    "fortell en vits",
    "værmelding",
    "fotballresultat",
)
_WEAK_DEADLINE_TERMS = frozenset(_normalize(t) for t in ("when is", "når må"))
_FIELD_MARKERS = (
    "field",
    "fields",
    "box",
    "boxes",
    "felt",
    "feltet",
    "post",
    "posten",
    "campo",
    "campos",
    "casilla",
    "casillas",
)


def _matches(query: str, terms: Sequence[str]) -> tuple[str, ...]:
    return tuple(term for term in terms if _contains_term(query, _normalize(term)))


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
            if intent in {QueryIntent.OUT_OF_SCOPE, QueryIntent.UNCERTAIN}:
                continue
            if not intent_terms or any(not term for term in intent_terms):
                raise ValueError(f"terms for {intent.value} must contain non-blank values")

    def classify(self, query: str) -> IntentClassification:
        normalized = _normalize(query)
        if not normalized:
            raise ValueError("query must not be empty")

        scope_terms = self._scope_terms(normalized)
        unrelated = _matches(normalized, _UNRELATED_REQUESTS)
        task = normalized
        for prefix in ("please ", "can you ", "could you ", "por favor ", "puedes ", "kan du "):
            task = task.removeprefix(prefix)
        explicit_unrelated_task = any(
            task == _normalize(term) or task.startswith(_normalize(term) + " ")
            for term in unrelated
        )
        if unrelated and (not scope_terms or explicit_unrelated_task):
            return IntentClassification(intent=QueryIntent.OUT_OF_SCOPE, matched_terms=unrelated)
        if not scope_terms:
            return IntentClassification(intent=QueryIntent.UNCERTAIN)

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
            if intent is QueryIntent.DEADLINE and set(matches) <= _WEAK_DEADLINE_TERMS:
                continue
            if intent is QueryIntent.FIELD_EXPLANATION and not _matches(normalized, _FIELD_MARKERS):
                continue
            if matches:
                return IntentClassification(intent=intent, matched_terms=matches)

        return IntentClassification(
            intent=QueryIntent.GENERAL_EXPLANATION, matched_terms=scope_terms
        )

    def _scope_terms(self, normalized_query: str) -> tuple[str, ...]:
        explicit = _matches(normalized_query, _EXPLICIT_TAX_SCOPE_TERMS)
        if explicit:
            return explicit
        return tuple(
            term
            for term in self._taxonomy.match(normalized_query).matched_terms
            if term not in _AMBIGUOUS_SCOPE_TERMS
        )
