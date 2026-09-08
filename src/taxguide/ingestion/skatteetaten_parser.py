import logging
import re
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser, Node

from taxguide.domain.enums import ParagraphKind
from taxguide.domain.exceptions import EmptyDocumentError, ParseError, UnsupportedDocumentError
from taxguide.domain.models import Link, Paragraph, ParsedDocument, RawDocument, Section

logger = logging.getLogger(__name__)
NOISE = (
    "nav, header, footer, script, style, svg, noscript, template, form, button, input, "
    "select, textarea, option, "
    '[hidden], [aria-hidden="true"], [role="navigation"], [role="search"], '
    ".breadcrumb, .breadcrumbs, .cookie-banner, #cookie-banner, .cookie-consent"
)


def _text(node: Node) -> str:
    # Preserve inline word boundaries as authored, including punctuation around links.
    tree = HTMLParser(node.html or "")
    for br in tree.css("br"):
        br.replace_with("\n")
    for block in tree.css("p, div, blockquote, pre"):
        block.insert_after("\n")
    return tree.body.text(separator="", strip=False).strip() if tree.body else ""


def _list(node: Node, depth: int = 0) -> str:
    lines: list[str] = []
    step = -1 if "reversed" in node.attributes else 1
    default_start = 1
    if step == -1:
        default_start = 0
        child = node.child
        while child is not None:
            default_start += child.tag == "li"
            child = child.next

    def integer(value: str | None, default: int) -> int:
        try:
            return int(value) if value is not None else default
        except ValueError:
            return default

    number = integer(node.attributes.get("start"), default_start)
    child = node.child
    while child is not None:
        if child.tag == "li":
            item = HTMLParser(child.html or "").css_first("li")
            if item is None:
                raise ParseError("Cannot read list item")
            nested = item.css("ul, ol")
            for nested_node in reversed(nested):
                nested_node.decompose()
            if node.tag == "ol":
                number = integer(child.attributes.get("value"), number)
            marker = f"{number}." if node.tag == "ol" else "-"
            lines.append(f"{'  ' * depth}{marker} {_text(item)}")
            sub = child.child
            while sub is not None:
                if sub.tag in {"ul", "ol"}:
                    lines.append(_list(sub, depth + 1))
                sub = sub.next
            number += step
        child = child.next
    return "\n".join(lines)


class SkatteetatenHtmlParser:
    def __init__(self, *, preserve_links: bool = True, preserve_headings: bool = True) -> None:
        self.preserve_links = preserve_links
        self.preserve_headings = preserve_headings

    def can_parse(self, document: RawDocument) -> bool:
        domain = document.source_domain
        return (
            domain == "skatteetaten.no" or domain.endswith(".skatteetaten.no")
        ) and document.content_type.split(";")[0].strip().lower() == "text/html"

    def parse(self, document: RawDocument) -> ParsedDocument:
        if not self.can_parse(document):
            raise UnsupportedDocumentError(f"Unsupported source: {document.source_url}")
        try:
            return self._parse(document)
        except EmptyDocumentError:
            raise
        except Exception as exc:
            raise ParseError(f"Cannot parse {document.local_path}: {exc}") from exc

    def _parse(self, document: RawDocument) -> ParsedDocument:
        tree = HTMLParser(document.content)
        html = tree.css_first("html")
        language = html.attributes.get("lang") if html else None
        if not language:
            meta = tree.css_first('meta[http-equiv="content-language"]')
            language = meta.attributes.get("content") if meta else None
        title_node = tree.css_first("title")
        fallback_title = title_node.text(strip=True) if title_node else None
        for node in tree.css(NOISE):
            if node.parent is not None:
                node.decompose()
        for node in tree.css("[style]"):
            style = re.sub(r"\s+", "", (node.attributes.get("style") or "")).lower()
            if "display:none" in style or "visibility:hidden" in style:
                node.decompose()

        for selector in (
            ".article-body",
            ".article-content",
            '[itemprop="articleBody"]',
            '[role="main"]',
            "main",
            "article",
        ):
            for root in tree.css(selector):
                sections = self._sections(root, document.source_url)
                if not any(p.text.strip() for s in sections for p in s.paragraphs):
                    continue
                h1 = root.css_first("h1") or tree.css_first("h1")
                title = _text(h1) if h1 else fallback_title
                identity = document.model_dump(exclude={"content", "content_type"})
                parsed = ParsedDocument(
                    **identity, title=title, language=language, sections=sections
                )
                logger.info("document parsed id=%s sections=%d", document.id, len(sections))
                return parsed
        raise EmptyDocumentError(f"No useful main content in {document.local_path}")

    def _sections(self, root: Node, source_url: str) -> list[Section]:
        sections: list[Section] = []
        heading: str | None = None
        level: int | None = None
        paragraphs: list[Paragraph] = []
        links: list[Link] = []

        def collect_links(node: Node) -> None:
            if not self.preserve_links:
                return
            anchors = [node] if node.tag == "a" else node.css("a[href]")
            for anchor in anchors:
                target = anchor.attributes.get("href")
                if target is None:
                    continue
                href = urljoin(source_url, target.strip())
                if urlsplit(href).scheme in {"http", "https", "mailto"}:
                    links.append(Link(text=_text(anchor), href=href))

        def flush() -> None:
            if heading or paragraphs or links:
                sections.append(
                    Section(
                        heading=heading, level=level, paragraphs=list(paragraphs), links=list(links)
                    )
                )
            paragraphs.clear()
            links.clear()

        def visit(node: Node) -> None:
            nonlocal heading, level
            tag = node.tag
            if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                if self.preserve_headings:
                    flush()
                    heading, level = _text(node), int(tag[1])
                else:
                    paragraphs.append(Paragraph(text=_text(node)))
            elif tag in {"p", "ul", "ol", "table", "blockquote", "pre", "a"}:
                kind = ParagraphKind.TEXT
                text = _text(node)
                if tag in {"ul", "ol"}:
                    text, kind = _list(node), ParagraphKind.LIST
                elif tag == "table":
                    text = "\n".join(
                        " | ".join(_text(c) for c in row.css("th, td")) for row in node.css("tr")
                    )
                    kind = ParagraphKind.TABLE
                paragraphs.append(Paragraph(text=text, kind=kind))
            else:
                inline: list[str] = []

                def flush_inline() -> None:
                    text = "".join(inline).strip()
                    if text:
                        paragraphs.append(Paragraph(text=text))
                    inline.clear()

                child = node.child
                while child is not None:
                    if child.tag in {
                        "-text",
                        "a",
                        "span",
                        "strong",
                        "em",
                        "b",
                        "i",
                        "u",
                        "small",
                        "sup",
                        "sub",
                        "code",
                        "br",
                    }:
                        if child.tag == "-text":
                            inline.append(child.text())
                        elif child.tag == "br":
                            inline.append("\n")
                        else:
                            # Keep surrounding whitespace until the complete inline run is joined.
                            inline.append(child.text(separator="", strip=False))
                            collect_links(child)
                    else:
                        flush_inline()
                        visit(child)
                    child = child.next
                flush_inline()
                return
            collect_links(node)

        visit(root)
        flush()
        return sections
