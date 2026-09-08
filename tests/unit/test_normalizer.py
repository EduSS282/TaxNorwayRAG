from datetime import UTC, datetime
from pathlib import Path

import pytest

from taxguide.domain.enums import ParagraphKind
from taxguide.domain.exceptions import EmptyDocumentError, ParseError
from taxguide.domain.models import Link, Paragraph, ParsedDocument, Section
from taxguide.ingestion.normalizer import Normalizer
from taxguide.ingestion.skatteetaten_parser import SkatteetatenHtmlParser


def test_normalizer_whitespace_and_unicode(raw):
    parsed = SkatteetatenHtmlParser().parse(raw)
    parsed = parsed.model_copy(
        update={"sections": [Section(paragraphs=[Paragraph(text="  cafe\u0301\u00a0 \n text  ")])]}
    )
    doc = Normalizer().normalize(parsed)
    assert doc.sections[0].paragraphs[0].text == "café text"


def test_normalizer_removes_empty_sections_and_adjacent_duplicates(raw):
    parsed = (
        SkatteetatenHtmlParser()
        .parse(raw)
        .model_copy(
            update={
                "sections": [
                    Section(),
                    Section(
                        paragraphs=[
                            Paragraph(text=" A "),
                            Paragraph(text="A"),
                            Paragraph(text="B"),
                            Paragraph(text="A"),
                        ]
                    ),
                ]
            }
        )
    )
    doc = Normalizer().normalize(parsed)
    assert len(doc.sections) == 1
    assert [p.text for p in doc.sections[0].paragraphs] == ["A", "B", "A"]


def test_normalizer_preserves_semantics_and_identity(raw):
    parsed = SkatteetatenHtmlParser().parse(raw)
    doc = Normalizer().normalize(parsed)
    assert (
        doc.plain_text
        == "Tax return\n\nCheck your information.\n\n## Bank and loans\n\nRead the guidance."
    )
    assert doc.id == raw.id and doc.content_hash == raw.content_hash
    assert doc.retrieved_at == raw.retrieved_at and doc.local_path == raw.local_path
    assert Normalizer().normalize(doc) == doc
    assert parsed.sections[1].paragraphs[0].text == "Read the guidance."


def test_normalizer_links_and_empty_failure(raw):
    parsed = (
        SkatteetatenHtmlParser()
        .parse(raw)
        .model_copy(
            update={
                "sections": [
                    Section(
                        paragraphs=[Paragraph(text="Keep")],
                        links=[
                            Link(text=" Help ", href="/help"),
                            Link(text="Bad", href="javascript:bad"),
                        ],
                    ),
                ]
            }
        )
    )
    assert Normalizer().normalize(parsed).sections[0].links == [
        Link(text="Help", href="https://www.skatteetaten.no/help")
    ]
    with pytest.raises(EmptyDocumentError):
        Normalizer().normalize(parsed.model_copy(update={"sections": []}))


def test_lists_and_tables_keep_structure(raw):
    parsed = (
        SkatteetatenHtmlParser()
        .parse(raw)
        .model_copy(
            update={
                "sections": [
                    Section(
                        paragraphs=[
                            Paragraph(
                                kind=ParagraphKind.LIST,
                                text="* Bank  name\n\n  - Account   currency\n",
                            ),
                            Paragraph(
                                kind=ParagraphKind.TABLE, text="Name  | Balance\n\nBank |  100"
                            ),
                        ]
                    ),
                ]
            }
        )
    )
    doc = Normalizer().normalize(parsed)
    assert doc.sections[0].paragraphs[0].text == "- Bank name\n  - Account currency"
    assert doc.sections[0].paragraphs[1].text == "Name | Balance\nBank | 100"


def test_list_indentation_uses_deterministic_spaces(independent_parsed):
    parsed = independent_parsed.model_copy(
        update={
            "sections": [
                Section(
                    paragraphs=[Paragraph(kind=ParagraphKind.LIST, text="\t* First\n\t\t* Second")]
                )
            ]
        }
    )

    document = Normalizer().normalize(parsed)

    assert document.sections[0].paragraphs[0].text == "        - First\n                - Second"
    assert "\t" not in document.plain_text


@pytest.fixture
def independent_parsed():
    return ParsedDocument(
        id="a" * 64,
        source_url="https://example.com/tax/page",
        source_domain="example.com",
        source_path="/tax/page",
        local_path=Path("page.html"),
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash="b" * 64,
        title="  Tax  guide ",
        sections=[Section(paragraphs=[Paragraph(text="Keep this text.")])],
    )


def test_relative_fragment_mail_links_are_normalized_and_deduplicated(independent_parsed):
    section = independent_parsed.sections[0].model_copy(
        update={
            "links": [
                Link(text=" Help ", href=" ../help "),
                Link(text="Help", href="https://example.com/help"),
                Link(text="Section", href="#section"),
                Link(text="Email", href="mailto:help@example.com"),
                Link(text="Unsafe", href="data:text/html,hello"),
            ]
        }
    )
    parsed = independent_parsed.model_copy(update={"sections": [section]})

    document = Normalizer().normalize(parsed)

    assert document.sections[0].links == [
        Link(text="Help", href="https://example.com/help"),
        Link(text="Section", href="https://example.com/tax/page#section"),
        Link(text="Email", href="mailto:help@example.com"),
    ]
    assert len(parsed.sections[0].links) == 5
    assert Normalizer().normalize(document) == document


def test_empty_or_invalid_link_targets_are_removed(independent_parsed):
    section = independent_parsed.sections[0].model_copy(
        update={
            "links": [
                Link(text=" ", href="/help"),
                Link(text="Empty target", href=" \t "),
                Link(text="No host", href="https:///help"),
                Link(text="No address", href="mailto:"),
                Link(text="Useful", href="/help"),
            ]
        }
    )
    parsed = independent_parsed.model_copy(update={"sections": [section]})

    document = Normalizer().normalize(parsed)

    assert document.sections[0].links == [Link(text="Useful", href="https://example.com/help")]


def test_malformed_link_reports_domain_error(independent_parsed):
    section = independent_parsed.sections[0].model_copy(
        update={"links": [Link(text="Broken", href="https://[invalid")]}
    )
    parsed = independent_parsed.model_copy(update={"sections": [section]})

    with pytest.raises(ParseError, match="Invalid link URL") as caught:
        Normalizer().normalize(parsed)

    assert isinstance(caught.value.__cause__, ValueError)


def test_heading_only_content_cannot_become_document(independent_parsed):
    parsed = independent_parsed.model_copy(
        update={"sections": [Section(heading="Heading", level=2)]}
    )

    with pytest.raises(EmptyDocumentError, match="No text after normalization"):
        Normalizer().normalize(parsed)


def test_blank_heading_is_removed_without_discarding_paragraph(independent_parsed):
    parsed = independent_parsed.model_copy(
        update={
            "sections": [
                Section(heading=" \t ", level=2, paragraphs=[Paragraph(text="Keep this text.")])
            ]
        }
    )

    document = Normalizer().normalize(parsed)

    assert document.sections[0].heading is None
    assert document.sections[0].level is None
    assert document.plain_text == "Tax guide\n\nKeep this text."
