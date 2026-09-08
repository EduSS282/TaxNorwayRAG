# Local ingestion

## Input

A UTF-8 HTML file (optional BOM) and its original HTTP(S) URL. The loader does not
use the file extension to determine content validity and makes no network requests.
`LocalHtmlSource(clock=...)` accepts a known capture timestamp through an injected
clock; by default, it records the local ingestion time in UTC.

## Extraction

`SkatteetatenHtmlParser` accepts `skatteetaten.no` and its subdomains with MIME type
`text/html`. It removes navigation, headers/footers, forms, scripts, styles, SVG,
buttons, templates, cookie notices, and hidden elements declared in HTML or inline
styles. It does not compute external CSS styles. Content is treated only as data.

It tries `.article-body`, `.article-content`, `[itemprop="articleBody"]`,
`[role="main"]`, `main`, and `article`, in that order. Empty candidates do not
prevent later fallbacks from being tried. The entire `body` is not extracted as
a last resort because that could turn navigation into apparently valid documentation.

The parser prefers h1 for the title, with `title` as a fallback. It reads the language
from `html[lang]` or `content-language` metadata; without a declaration, it returns
`None`. It preserves h1–h6, paragraphs, lists, blockquotes, pre elements, and simple
tables in order. Links within those blocks are resolved against the original URL;
HTTP(S) and mailto are allowed, while executable schemes are excluded.
`preserve_links` and `preserve_headings` control the output; when headings are
disabled, their text remains as paragraphs.

## Normalization

Normalization applies Unicode NFC, compacts whitespace, and removes empty blocks
and identical adjacent paragraphs within a section. Repetitions across sections
are preserved because they may have different meanings. Lists and tables retain
line breaks. Links are resolved, cleaned, and deduplicated by text and destination
within each section.

Plain text includes the title, headings with level markers, and paragraphs separated
by a blank line. It avoids repeating h1 when it matches the title. URLs are retained
in the JSON field `sections[].links`. Tax rules are not summarized, translated, or inferred.

## Errors and logging

- `DocumentLoadError`: unreadable file, invalid encoding, or invalid source identity.
- `UnsupportedDocumentError`: unsupported source or MIME type.
- `ParseError`: internal extraction failure, with file context.
- `EmptyDocumentError`: useful content is missing or disappears during normalization.
- `InvalidConfigurationError`: unreadable YAML or invalid configuration.

The CLI displays the error on stderr and exits with code 1. INFO logs record loading,
parser selection, extraction, and normalization without dumping the complete HTML.

## Extension and validation

Implement `DocumentSource` for another loading mechanism or `DocumentParser` for
another HTML structure; inject them into `IngestionPipeline` with a compatible
normalizer. Add saved fixtures and tests before extending the selectors.

The current fixtures are synthetic and cover basic structure, nested headings,
lists, tables, and noise. Before using a real corpus, manually review representative
official captures. Automatic downloading is not implemented in this phase.
