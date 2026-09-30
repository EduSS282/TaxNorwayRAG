import pytest
from pydantic import ValidationError

from taxguide.generation.models import Citation, ConfidenceLevel, RagAnswer

VALID_CITATION = {
    "citation_id": "S1",
    "chunk_id": "a" * 64,
    "source_title": "Travel deductions",
    "source_url": "https://www.skatteetaten.no/en/travel/",
    "quote_span": [0, 37],
}


def test_rag_answer_round_trips_all_structured_fields() -> None:
    answer = RagAnswer(
        answer="You may deduct documented travel expenses.",
        tax_year=2026,
        citations=[_citation()],
        confidence=ConfidenceLevel.HIGH,
        missing_information=["Your number of travel days."],
        warnings=["Keep receipts for the claimed expenses."],
    )

    assert answer.model_dump(mode="json") == {
        "answer": "You may deduct documented travel expenses.",
        "tax_year": 2026,
        "citations": [
            {
                "citation_id": "S1",
                "chunk_id": "a" * 64,
                "source_title": "Travel deductions",
                "source_url": "https://www.skatteetaten.no/en/travel/",
                "quote_span": [0, 37],
            }
        ],
        "confidence": "high",
        "missing_information": ["Your number of travel days."],
        "warnings": ["Keep receipts for the claimed expenses."],
    }
    assert RagAnswer.model_validate_json(answer.model_dump_json()) == answer


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"answer": "   "}, "answer must not be blank"),
        ({"tax_year": 1899}, "greater than or equal"),
        ({"confidence": "certain"}, "confidence"),
        ({"citations": [{**VALID_CITATION, "citation_id": "source-1"}]}, "citation_id"),
        ({"citations": [{**VALID_CITATION, "chunk_id": "not-a-digest"}]}, "chunk_id"),
        ({"citations": [{**VALID_CITATION, "source_url": "/relative"}]}, "absolute HTTP"),
        ({"citations": [{**VALID_CITATION, "quote_span": [3, 3]}]}, "start must be before"),
        ({"unexpected": "field"}, "unexpected"),
    ],
)
def test_rag_answer_rejects_invalid_structured_values(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        RagAnswer.model_validate(_answer_payload() | payload)


def test_rag_answer_requires_each_issue_field() -> None:
    for field in (
        "answer",
        "tax_year",
        "citations",
        "confidence",
        "missing_information",
        "warnings",
    ):
        payload = _answer_payload()
        payload.pop(field)

        with pytest.raises(ValidationError, match="Field required"):
            RagAnswer.model_validate(payload)


def test_citations_need_unique_stable_identifiers() -> None:
    duplicate = _citation()

    with pytest.raises(ValidationError, match="citation IDs must be unique"):
        RagAnswer.model_validate(_answer_payload() | {"citations": [_citation(), duplicate]})


def test_models_are_immutable() -> None:
    answer = RagAnswer.model_validate(_answer_payload())

    with pytest.raises(ValidationError, match="frozen"):
        answer.answer = "Different answer"


def _citation() -> Citation:
    return Citation(
        citation_id="S1",
        chunk_id="a" * 64,
        source_title="Travel deductions",
        source_url="https://www.skatteetaten.no/en/travel/",
        quote_span=(0, 37),
    )


def _answer_payload() -> dict[str, object]:
    return {
        "answer": "You may deduct documented travel expenses.",
        "tax_year": 2026,
        "citations": [VALID_CITATION],
        "confidence": "high",
        "missing_information": [],
        "warnings": [],
    }
