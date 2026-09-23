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

Indexing requires the configured embedding service and an existing Qdrant collection with the
matching vector dimension. The command does not create or validate the collection; see
[local Qdrant](qdrant-local.md). The configured embedder is called directly: the available
`CachingBatchingEmbedder` is not currently composed into this workflow, so repeated builds do not
use a persistent embedding cache.

`--list` shows document ID, language, page type, and effective URL. `--json`
provides the same selection data without HTML. Effective URL priority is an
allowed Skatteetaten canonical URL, then final URL, then original URL.

Non-dry runs write an immutable-per-execution report to
`data/manifests/corpus/<run_id>.json`. It records filters, selected IDs, counts,
timestamps, indexing configuration, and structured per-document failures.

Wizard pages can be excluded with `--exclude-wizards`; otherwise only their
already-rendered static HTML enters the existing parser. The command does not
execute JavaScript or traverse wizard branches.
