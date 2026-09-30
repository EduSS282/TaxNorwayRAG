# ADR 0007: Promote evaluated Qdrant candidate indexes through aliases

## Status

Accepted.

## Context

Corpus builds previously wrote directly to the configured collection. That made an index refresh
hard to validate before readers observed it and provided no quick recovery path after a bad update.
Incremental builds also need a stable version identity so repeat runs do not re-embed unchanged
source content.

## Decision

- Index candidate corpora into a separate physical collection selected by the corpus CLI.
- Identify an indexed source version by `document_id` and deterministic `version_id`; parse and
  chunk deterministically, then skip embedding only when exact chunk IDs, content hashes, and
  the index-settings signature match. Partial earlier writes are therefore retried.
- Record source changes in crawl manifests by comparing the content hash with the previously saved
  manifest for that document.
- Persist live retrieval metrics as an artifact bound to candidate collection and dataset version.
- Require all four retrieval modes in the report and an explicit operator `--evaluation-passed`
  flag before promoting.
- Use Qdrant's atomic alias operations to point the stable current alias to a candidate while
  retaining one prior collection for rollback. The first promotion adopts the configured existing
  physical collection as the previous target when no current alias exists.
- Never delete collections automatically during promotion or rollback.

## Consequences

Indexing and promotion can be separated, checked and rolled back without changing physical
collection contents. Repeat corpus builds avoid embedding versions already in their target. The
system still depends on operators to curate a representative gold dataset, define acceptance
thresholds, review reports, configure readers to use the alias and manage collection retention.
Evaluation artifacts do not yet capture all model, runtime, and hardware provenance.
