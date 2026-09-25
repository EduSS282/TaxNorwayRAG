# Corpus batch workflow

The corpus command selects crawler artifacts from JSON crawl manifests, never from
HTML filenames. Its flow is:

```text
Crawl manifests → CorpusSelector → LocalHtmlSource → parser → normalizer → chunker
                                                                      ↓
                                                        optional embedder → vector store
```

By default it accepts only HTTP 200 `text/html` manifests and excludes content
duplicates. It does not index unless `--index` is supplied. Processing is one
raw HTML artifact at a time; a failed document is recorded and does not stop the
remaining batch.

Inspect an English personal-tax corpus without parsing or writing anything:

```console
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --dry-run
```

Other useful selections:

```console
uv run taxguide corpus build --url-prefix "/person/skatt/" --language nb --dry-run
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --url-prefix "/person/skatt/" --url-prefix "/nn/person/skatt/" --dry-run
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --limit 50
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --exclude-wizards --index
```

Indexing requires the configured embedding service and Qdrant. The command creates a missing
single-vector cosine collection using the embedder's reported dimension and validates an existing
collection before upsert; see [local Qdrant](qdrant-local.md). Repeated indexed builds parse and
chunk the source, then check that the selected collection contains the expected number of chunks
for `document_id + version_id` before embedding. This avoids re-embedding a complete indexed
version, detects partial earlier writes, and does not reuse vectors across collections or provide a
persistent embedding cache.

To build a separate physical candidate without replacing the configured production collection:

```console
uv run taxguide corpus build --url-prefix "/en/person/taxes/" --language en --index --collection taxguide_candidate_2026_09
```

Use a new candidate collection name for each evaluation cycle. Indexing is incremental within that
collection; a changed source version is indexed as a new version, while old points are retained.
Candidate cleanup and garbage collection are intentionally not automated.

`--list` shows document ID, language, page type, and effective URL. `--json`
provides the same selection data without HTML. Effective URL priority is an
allowed Skatteetaten canonical URL, then final URL, then original URL.

Non-dry runs write an immutable-per-execution report to
`data/manifests/corpus/<run_id>.json`. It records filters, selected IDs, counts,
timestamps, indexing configuration, and structured per-document failures.

Wizard pages can be excluded with `--exclude-wizards`; otherwise only their
already-rendered static HTML enters the existing parser. The command does not
execute JavaScript or traverse wizard branches.
