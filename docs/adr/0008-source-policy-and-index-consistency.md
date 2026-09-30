# ADR 0008: Source policy and document-level index consistency

## Status

Accepted.

## Context

Flat crawler allowlists did not identify named sources, while redirects were checked for host
but not for content path and robots policy before the HTTP request. Index reuse counted points
instead of verifying their identity; changed source versions could leave old dense and sparse
evidence in the collection.

## Decision

- Keep a validated input source-policy YAML separate from per-page output capture manifests.
  A named source defines ID, domain, seed URL, allowed paths, languages, and priority. The CLI
  binds host/path scope to each request and records the source ID in capture manifests.
- Validate content paths and cached robots policy before every HTTP redirect hop. Reject an
  out-of-scope or disallowed target before fetching its body.
- Compare complete chunk identity/content and a deterministic parse/chunk/embed settings
  signature before skipping embedding. Wait for each Qdrant upsert to finish; only then delete
  obsolete points for the document. Retry cleanup on a subsequent unchanged run.
- Use candidate physical collections and alias promotion to keep in-progress index writes away
  from production readers.

## Consequences and limits

Changed document versions do not persist as searchable evidence after a successful build. A
failed or interrupted in-place build may temporarily expose both versions; candidate promotion
is the operational boundary for readers. Signature changes detect configured model IDs but not
silent changes to model weights or library code. The source language hint may be unknown; a
named source with language restrictions skips such pages. Source priority is not a scheduler.
