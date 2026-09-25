# Skatteetaten crawler

The crawler acquires public HTML from `www.skatteetaten.no` and
`skatteetaten.no`. It validates every target and redirect, obeys cached
`robots.txt` rules before each content redirect hop, applies bounded retries and response sizes, and follows only
eligible internal HTML links. Conservative defaults limit a crawl to 50 pages
and depth 2; these and request delay are configurable.

It does not parse article content, execute JavaScript, submit forms, enter login
areas, traverse wizard branches, or perform downstream chunking/indexing.

## Commands

Acquire one page:

```console
uv run taxguide crawl "https://www.skatteetaten.no/en/person/taxes/tax-return/" --max-pages 1 --no-follow
```

Prefer a named, bounded source from `configs/sources.yaml`:

```console
uv run taxguide crawl --source skatteetaten-tax-return-en --max-pages 25 --max-depth 2
```

`--sources-file` selects another source-policy YAML. Each entry defines a unique ID, domain,
seed URL, allowed path prefixes, optional language list, and priority. The CLI uses that source's
hosts and paths for the seed, discovered links, and every content redirect. A page with a detected
language outside the source's list is skipped without saving. The source ID is stored in each
capture manifest. `priority` is recorded policy metadata; crawl scheduling by priority is not yet
implemented. URL-only crawls remain available and use the flat allowlists in `configs/base.yaml`.
The source-policy YAML is distinct from the output JSON crawl manifests.

Run a small recursive crawl:

```console
uv run taxguide crawl "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/" --max-pages 25 --max-depth 2
```

`--delay`, `--output-dir`, and `--json` control pacing, the artifact root, and
machine-readable output. `Retry-After` is honored for 429/5xx responses, bounded
by `crawler.max_retry_after_seconds` (60 seconds by default); malformed or
missing values use bounded exponential backoff. Configuration defaults live
under `crawler` in `configs/base.yaml`.

## Artifacts and ingestion handoff

For document ID `<id>`, the default repository atomically writes UTF-8 files:

```text
data/raw/skatteetaten/<id>.html
data/manifests/crawl/<id>.json
```

The manifest records original, final, and discovered canonical URLs, retrieval
time, HTTP status and content type, SHA-256, language hint, page classification,
wizard metadata, and content-duplicate provenance. Recrawls also record
`change_status` (`new`, `unchanged`, or `changed`) and the prior content hash
when one exists; the CLI summarizes all three categories. IDs are deterministic from
the normalized final URL; discovered canonical metadata is retained without
allowing two fetched aliases to overwrite one another. Recrawls replace the same
artifact paths while preserving the comparison result in the new manifest.

The crawler stays inside explicitly allowed hosts and path prefixes. Prefixes
are path-segment boundaries (`/en` allows `/en/...`, not `/english/...`), only
HTTP(S) and standard ports are accepted, and each redirect is checked again.

The saved HTML can be passed directly to the existing local ingestion command:

```console
uv run taxguide parse data/raw/skatteetaten/<id>.html --url "https://www.skatteetaten.no/..."
```

Wizard markup is classified as `interactive_wizard`, and the initially rendered
question, answers, step ID, wizard IDs, and language are captured when present.
The HTML remains available to the normal parser. This metadata never claims that
unrendered branches were captured; wizard traversal is not implemented.
