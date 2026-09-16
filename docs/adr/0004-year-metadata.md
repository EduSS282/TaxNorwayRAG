# ADR 0004: Treat tax year and document version as first-class metadata

## Context

Norwegian tax guidance changes over time. Content for one tax year must remain queryable without
competing with, overwriting, or leaking into results for another year. A retrieval score alone
cannot establish temporal applicability.

## Decision

- `TaxYearMetadata` stores the independently optional `tax_year`, `valid_from`, and `valid_to`.
- `DocumentVersion` records `document_id`, deterministic `version_id`, `content_hash`, retrieval
  time, and temporal applicability.
- `version_id` is SHA-256 of `document_id + ":" + content_hash`. Changed captures therefore create
  new chunk and Qdrant point identities; old versions are not overwritten.
- Chunk IDs derive from `version_id`, section path, and chunk index. Every chunker copies all
  temporal metadata into its chunk payload.
- `TaxYearResolver` applies explicit query year, conversation context, identified form, and current
  applicable year in that order. Multiple explicit years are ambiguous.
- `TaxYearAwareRetriever` applies the resolved year before ranking and rejects any adapter result
  whose year is missing or different.

## Alternatives

- Filtering results after similarity search was rejected because wrong-year chunks can consume the
  candidate limit and hide relevant evidence.
- Replacing an old document version in place was rejected because it prevents historical answers
  and reproducible investigations.
- Deriving validity dates from `tax_year` was rejected because sources may define a different legal
  applicability interval; missing knowledge remains explicit.

## Consequences

Year-aware callers obtain strict, auditable retrieval. Ambiguous or contradictory years fail
before retrieval. Existing Qdrant payloads remain readable because the copied chunk `version_id`
is optional on deserialization, while newly ingested documents always materialize one.
