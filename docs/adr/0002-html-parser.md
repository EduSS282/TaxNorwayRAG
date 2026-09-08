# ADR 0002 — Source-specific parser with semantic fallbacks

## Context

Navigation and structural variations on an official website can contaminate
extracted text. Flattening content too early removes information needed for chunking.

## Decision

Use a Skatteetaten-specific parser backed by selectolax, with preferred selectors
and semantic HTML fallbacks, rather than relying solely on generic extraction.
Retain headings, paragraphs, lists, and links in explicit models.

## Alternatives

A single selector is brittle. Extracting all body text retains noise.
A generic article extraction library may discard lists or structure.
BeautifulSoup is not installed because a second parsing engine is not currently needed.

## Consequences

Extraction is fast and local, and fails explicitly when no content is found.
Selectors require maintenance using representative fixtures; synthetic tests
do not demonstrate coverage of every real page.
