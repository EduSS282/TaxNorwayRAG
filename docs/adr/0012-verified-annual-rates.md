# ADR 0012: Verify annual rate applicability against captured HTML

Status: accepted, 2026-09-27.

## Context

Strict retrieval requires a tax year, but ordinary guidance captures have no verified year.
Previously corpus building trusted `?year=` alone, even if the server ignored that parameter.
Capture dates and year mentions in mixed-year guidance cannot establish annual applicability.

## Decision

Reuse the crawler/parser/corpus boundaries. Expand only explicitly requested years advertised by
the official rate selector. Verify the selected option against the final annual URL both before
capture persistence and during parsing. Reject mismatches, including redirects dropping the year.
The shared Skatteetaten-specific helper lives with ingestion, not with retrieval or the UI.
The rate catalog's known JSON data supplies links but no JavaScript is evaluated. Existing
host/path/robots and total page limits still apply. Annual variants use the same link depth.

Capture manifests optionally record the verified year; older manifests remain readable. The parser
revalidates saved HTML rather than trusting manifest metadata. Documents and chunks use the existing
tax-year fields. Incremental Qdrant reuse also compares tax-year metadata so identical chunk text
cannot hide a metadata correction. No retrieval fallback to unknown or different years is added.

## Consequences

Unknown years remain unknown. URL-only annual fixtures/captures without a matching selector fail
closed. Other annual document formats require a separately verified extraction rule, not a generic
year regex. If markup changes, capture/build reports expose the failure. Previously indexed invalid
data is not deleted automatically; rebuild into a clean candidate and validate before promotion.
The UI does not gain a coverage guarantee, and source traceability does not prove LLM faithfulness.
