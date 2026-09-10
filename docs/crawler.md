# Skatteetaten crawler

The crawler acquires public HTML from `www.skatteetaten.no` and
`skatteetaten.no`. It validates every target and redirect, obeys cached
`robots.txt` rules, applies bounded retries and response sizes, and follows only
eligible internal HTML links. Conservative defaults limit a crawl to 50 pages
and depth 2; these and request delay are configurable.

It does not parse article content, execute JavaScript, submit forms, enter login
areas, traverse wizard branches, or perform downstream chunking/indexing.

## Commands

Acquire one page:

```console
uv run taxguide crawl "https://www.skatteetaten.no/en/person/taxes/tax-return/" --max-pages 1 --no-follow
```

Run a small recursive crawl:

```console
uv run taxguide crawl "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/" --max-pages 25 --max-depth 2
```

`--delay`, `--output-dir`, and `--json` control pacing, the artifact root, and
machine-readable output. Configuration defaults live under `crawler` in
`configs/base.yaml`.

## Artifacts and ingestion handoff

For document ID `<id>`, the default repository atomically writes UTF-8 files:

```text
data/raw/skatteetaten/<id>.html
data/manifests/crawl/<id>.json
```

The manifest records original, final, and discovered canonical URLs, retrieval
time, HTTP status and content type, SHA-256, language hint, page classification,
wizard metadata, and content-duplicate provenance. IDs are deterministic from
the normalized final URL; discovered canonical metadata is retained without
allowing two fetched aliases to overwrite one another. Unchanged recrawls replace
the same artifact paths.

The saved HTML can be passed directly to the existing local ingestion command:

```console
uv run taxguide parse data/raw/skatteetaten/<id>.html --url "https://www.skatteetaten.no/..."
```

Wizard markup is classified as `interactive_wizard`, and the initially rendered
question, answers, step ID, wizard IDs, and language are captured when present.
The HTML remains available to the normal parser. This metadata never claims that
unrendered branches were captured; wizard traversal is not implemented.
