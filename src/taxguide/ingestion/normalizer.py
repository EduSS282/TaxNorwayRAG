import logging
import re
import unicodedata
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from taxguide.domain.enums import ParagraphKind
from taxguide.domain.exceptions import EmptyDocumentError, ParseError
from taxguide.domain.models import Document, Link, Paragraph, ParsedDocument, Section

logger = logging.getLogger(__name__)
ALLOWED_LINK_SCHEMES = frozenset({"http", "https", "mailto"})


class DocumentNormalizer(Protocol):
    def normalize(self, document: ParsedDocument) -> Document: ...


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def normalize_paragraph(paragraph: Paragraph) -> Paragraph:
    if paragraph.kind == ParagraphKind.TEXT:
        text = normalize_text(paragraph.text)
    else:
        lines = []
        for raw_line in unicodedata.normalize("NFC", paragraph.text).splitlines():
            if raw_line.strip():
                # Tabs are presentation whitespace. Expand them before counting so the
                # normalized form has stable, space-only indentation.
                line = raw_line.expandtabs()
                indent = len(line) - len(line.lstrip())
                clean = normalize_text(line)
                if paragraph.kind == ParagraphKind.LIST:
                    clean = re.sub(r"^[•*]\s+", "- ", clean)
                    clean = " " * indent + clean
                lines.append(clean)
        text = "\n".join(lines)
    return Paragraph(text=text, kind=paragraph.kind)


def normalize_link(link: Link, source_url: str) -> Link | None:
    text = normalize_text(link.text)
    href = link.href.strip()
    if not text or not href:
        return None

    try:
        supplied_href = urlsplit(href)
        if supplied_href.scheme in {"http", "https"} and not supplied_href.hostname:
            return None
        if supplied_href.scheme == "mailto" and not supplied_href.path:
            return None
        resolved_href = urljoin(source_url, href)
        parsed_href = urlsplit(resolved_href)
    except ValueError as exc:
        raise ParseError(f"Invalid link URL while normalizing document: {source_url}") from exc

    if parsed_href.scheme not in ALLOWED_LINK_SCHEMES:
        return None
    if parsed_href.scheme in {"http", "https"} and not parsed_href.hostname:
        return None
    if parsed_href.scheme == "mailto" and not parsed_href.path:
        return None
    return Link(text=text, href=resolved_href)


class Normalizer:
    def normalize(self, document: ParsedDocument) -> Document:
        sections: list[Section] = []
        for section in document.sections:
            paragraphs: list[Paragraph] = []
            for paragraph in section.paragraphs:
                clean = normalize_paragraph(paragraph)
                if clean.text and (not paragraphs or paragraphs[-1] != clean):
                    paragraphs.append(clean)
            links: list[Link] = []
            for link in section.links:
                clean_link = normalize_link(link, document.source_url)
                if clean_link is not None and clean_link not in links:
                    links.append(clean_link)
            heading = normalize_text(section.heading) if section.heading else None
            if heading or paragraphs or links:
                sections.append(
                    Section(
                        heading=heading or None,
                        level=section.level if heading else None,
                        paragraphs=paragraphs,
                        links=links,
                    )
                )
        if not any(s.paragraphs for s in sections):
            raise EmptyDocumentError(f"No text after normalization: {document.source_url}")
        title = normalize_text(document.title) if document.title else None
        blocks = [title] if title else []
        for section in sections:
            if section.heading and not (section.level == 1 and section.heading == title):
                blocks.append(f"{'#' * (section.level or 1)} {section.heading}")
            blocks.extend(p.text for p in section.paragraphs)
        values = document.model_dump(exclude={"sections", "title", "plain_text"})
        result = Document(**values, title=title, sections=sections, plain_text="\n\n".join(blocks))
        logger.info("document normalized id=%s sections=%d", result.id, len(result.sections))
        return result
