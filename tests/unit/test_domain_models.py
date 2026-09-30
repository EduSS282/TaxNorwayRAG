from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from taxguide.domain.enums import ParagraphKind
from taxguide.domain.models import Document, Link, Paragraph, ParsedDocument, RawDocument, Section


@pytest.fixture
def source_identity():
    return {
        "id": "a" * 64,
        "content_hash": "b" * 64,
        "source_url": "https://www.skatteetaten.no:443/en/tax/?year=2026#income",
        "source_domain": "www.skatteetaten.no",
        "source_path": "/en/tax/",
        "local_path": Path("capture.html"),
        "retrieved_at": datetime(2026, 9, 8, tzinfo=timezone(timedelta(hours=2))),
    }


@pytest.mark.parametrize("model", [RawDocument, ParsedDocument, Document])
def test_documents_preserve_source_identity_and_round_trip_json(model, source_identity):
    payload = dict(source_identity)
    if model is RawDocument:
        payload["content"] = "<main>Income</main>"
    else:
        payload["sections"] = [Section(paragraphs=[Paragraph(text="Income")])]
        if model is Document:
            payload["plain_text"] = "Income"

    document = model.model_validate(payload)

    for field, expected in source_identity.items():
        assert getattr(document, field) == expected
    assert model.model_validate_json(document.model_dump_json()) == document


@pytest.mark.parametrize(
    "invalid",
    [
        {"retrieved_at": datetime(2026, 9, 8)},
        {"id": "g" * 64},
        {"content_hash": "a" * 63},
        {"source_url": "ftp://www.skatteetaten.no/en/tax/"},
        {"source_url": "/en/tax/"},
        {"source_domain": "example.org"},
        {"source_path": "/other/"},
        {"unexpected": "field"},
    ],
)
def test_raw_document_rejects_invalid_source_identity(source_identity, invalid):
    with pytest.raises(ValidationError):
        RawDocument.model_validate(source_identity | {"content": "<main/>"} | invalid)


def test_sections_keep_structured_content_and_independent_defaults():
    section = Section(
        heading="Income",
        level=2,
        paragraphs=[Paragraph(text="Salary"), Paragraph(text="- Allowance", kind="list")],
        links=[Link(text="Read more", href="../income/")],
    )
    assert section.paragraphs[0].kind is ParagraphKind.TEXT
    assert section.paragraphs[1].kind is ParagraphKind.LIST
    assert section.links[0].href == "../income/"
    first, second = Section(), Section()
    first.paragraphs.append(Paragraph(text="Independent content"))
    first.links.append(Link(text="More", href="/more"))
    assert second.paragraphs == []
    assert second.links == []


@pytest.mark.parametrize(
    "values",
    [
        {"heading": "Income"},
        {"level": 2},
        {"heading": "Income", "level": 0},
        {"heading": "Income", "level": 7},
    ],
)
def test_section_rejects_invalid_heading_pair(values):
    with pytest.raises(ValidationError):
        Section.model_validate(values)


def test_paragraph_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        Paragraph.model_validate({"text": "Income", "kind": "unknown"})


def test_final_document_requires_nonempty_plain_text(source_identity):
    with pytest.raises(ValidationError):
        Document.model_validate(source_identity | {"sections": [], "plain_text": ""})


def test_source_identity_cannot_be_reassigned(source_identity):
    document = RawDocument.model_validate(source_identity | {"content": "<main/>"})
    with pytest.raises(ValidationError, match="frozen"):
        document.source_url = "https://example.org/"
