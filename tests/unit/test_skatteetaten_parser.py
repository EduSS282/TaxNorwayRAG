from pathlib import Path

import pytest

from taxguide.domain.exceptions import EmptyDocumentError, ParseError, UnsupportedDocumentError
from taxguide.ingestion.skatteetaten_parser import SkatteetatenHtmlParser
from taxguide.sources.local import LocalHtmlSource

PARSER = SkatteetatenHtmlParser()


def test_parser_extracts_title(raw):
    assert PARSER.parse(raw).title == "Tax return"


def test_parser_extracts_language(raw):
    assert PARSER.parse(raw).language == "en"
    assert (
        PARSER.parse(raw.model_copy(update={"content": "<main><p>Text</p></main>"})).language
        is None
    )


def test_parser_preserves_main_links(raw):
    doc = PARSER.parse(raw)
    assert doc.sections[1].links[0].href == "https://www.skatteetaten.no/en/help"
    assert doc.sections[1].paragraphs[0].text == "Read the guidance."


def test_parser_preserves_heading_levels_and_lists(raw):
    page = LocalHtmlSource().load(
        Path("tests/fixtures/html/skatteetaten_nested_headings.html"), raw.source_url
    )
    doc = PARSER.parse(page)
    assert [s.level for s in doc.sections] == [1, 2, 3, 2]
    assert doc.sections[2].paragraphs[0].text == "- Bank name\n- Balance\n  - Currency"
    assert doc.sections[3].paragraphs[0].text == "2. Review\n3. Confirm"
    assert doc.sections[3].paragraphs[1].text == "Field | Description\nBank | Name"


def test_parser_removes_navigation_scripts_footer_and_hidden_content(raw):
    page = LocalHtmlSource().load(
        Path("tests/fixtures/html/skatteetaten_noise.html"), raw.source_url
    )
    assert "NOISE" not in PARSER.parse(page).model_dump_json()


@pytest.mark.parametrize(
    "control",
    [
        "<select><option>CONTROL_NOISE</option></select>",
        "<textarea>CONTROL_NOISE</textarea>",
    ],
)
def test_parser_removes_form_controls_outside_a_form(raw, control):
    html = f"<main><p>Useful content.</p>{control}</main>"
    doc = PARSER.parse(raw.model_copy(update={"content": html}))
    assert [paragraph.text for paragraph in doc.sections[0].paragraphs] == ["Useful content."]


@pytest.mark.parametrize(
    "html", ["", "<main><nav>Only noise</nav></main>", "<main><h1>Title only</h1></main>"]
)
def test_parser_fails_on_empty_content(raw, html):
    with pytest.raises(EmptyDocumentError):
        PARSER.parse(raw.model_copy(update={"content": html}))


@pytest.mark.parametrize(
    "container",
    [
        "main",
        "article",
        'div role="main"',
        'div class="article-body"',
        'div itemprop="articleBody"',
    ],
)
def test_selector_fallbacks(raw, container):
    html = (
        f"<html><head><title>Fallback</title></head><body><{container}>"
        f"<p>Useful</p></{container.split()[0]}></body></html>"
    )
    doc = PARSER.parse(raw.model_copy(update={"content": html}))
    assert doc.title == "Fallback"
    assert doc.sections[0].paragraphs[0].text == "Useful"


def test_empty_preferred_selector_uses_main(raw):
    html = '<main><div class="article-body"></div><p>Useful</p></main>'
    assert (
        PARSER.parse(raw.model_copy(update={"content": html})).sections[0].paragraphs[0].text
        == "Useful"
    )


def test_options(raw):
    doc = SkatteetatenHtmlParser(preserve_headings=False, preserve_links=False).parse(raw)
    assert all(s.heading is None and not s.links for s in doc.sections)
    assert doc.sections[0].paragraphs[0].text == "Tax return"


def test_unsupported_source(raw):
    with pytest.raises(UnsupportedDocumentError):
        PARSER.parse(raw.model_copy(update={"source_domain": "skatteetaten.no.evil.test"}))


def test_parser_wraps_low_level_errors(raw, monkeypatch):
    def fail(*args):
        raise RuntimeError("parser failure")

    monkeypatch.setattr(PARSER, "_parse", fail)
    with pytest.raises(ParseError, match="Cannot parse"):
        PARSER.parse(raw)


def test_standalone_links_and_line_breaks(raw):
    html = '<main><p>First<br>second</p><a href="/help">Help</a></main>'
    doc = PARSER.parse(raw.model_copy(update={"content": html}))
    assert doc.sections[0].paragraphs[0].text == "First\nsecond"
    assert doc.sections[0].links[0].href == "https://www.skatteetaten.no/help"


def test_unsafe_links_are_excluded(raw):
    html = '<main><p><a href="javascript:alert(1)">Text</a></p></main>'
    doc = PARSER.parse(raw.model_copy(update={"content": html}))
    assert not doc.sections[0].links
    assert doc.sections[0].paragraphs[0].text == "Text"


def test_named_anchor_without_href_does_not_create_link(raw):
    html = '<main><a id="income">Income</a><p>Read <a name="details">details</a>.</p></main>'
    doc = PARSER.parse(raw.model_copy(update={"content": html}))
    assert not doc.sections[0].links
    assert [p.text for p in doc.sections[0].paragraphs] == ["Income", "Read details."]


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<ol start="invalid"><li>First</li><li>Second</li></ol>', "1. First\n2. Second"),
        (
            '<ol start="0"><li>First</li><li value="4">Second</li><li>Third</li></ol>',
            "0. First\n4. Second\n5. Third",
        ),
        ("<ol reversed><li>First</li><li>Second</li></ol>", "2. First\n1. Second"),
        (
            '<ol reversed start="7"><li>First</li><li value="3">Second</li><li>Third</li></ol>',
            "7. First\n3. Second\n2. Third",
        ),
        ('<ol><li value="invalid">First</li><li>Second</li></ol>', "1. First\n2. Second"),
    ],
)
def test_ordered_list_numbering_and_invalid_attributes(raw, html, expected):
    doc = PARSER.parse(raw.model_copy(update={"content": f"<main>{html}</main>"}))
    assert doc.sections[0].paragraphs[0].text == expected


def test_blockquote_preserves_paragraph_boundaries(raw):
    html = "<main><blockquote><p>First paragraph.</p><p>Second paragraph.</p></blockquote></main>"
    doc = PARSER.parse(raw.model_copy(update={"content": html}))
    assert doc.sections[0].paragraphs[0].text == "First paragraph.\nSecond paragraph."


def test_unwrapped_main_text_and_inline_markup_are_preserved(raw):
    html = (
        "<main>Intro <strong>words</strong>."
        '<div>Read <a href="/help">the guidance</a> carefully.</div>'
        "<div>Before.<p>Paragraph.</p>After <em>text</em>.</div></main>"
    )
    doc = PARSER.parse(raw.model_copy(update={"content": html}))
    assert [p.text for p in doc.sections[0].paragraphs] == [
        "Intro words.",
        "Read the guidance carefully.",
        "Before.",
        "Paragraph.",
        "After text.",
    ]
    assert [link.href for link in doc.sections[0].links] == ["https://www.skatteetaten.no/help"]
