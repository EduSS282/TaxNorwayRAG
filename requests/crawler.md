You are working on the TaxGuide Norway project.

Implement a minimal, production-minded crawler for official Skatteetaten pages.

IMPORTANT:
- Implement ONLY the crawler/acquisition layer described below.
- Do NOT implement Playwright, browser automation, JavaScript execution, wizard traversal, embeddings, retrieval, generation, scheduling, or multi-domain crawling.
- Do NOT treat norway_tax_rag_architecture.md as a request to implement the whole architecture.
- Use it only as design guidance for this issue.
- Inspect the repository before changing anything.
- Read AGENTS.md and the relevant architecture documents first.
- Reuse existing domain models, hashing utilities, configuration patterns, logging, CLI conventions, and ingestion interfaces where appropriate.
- Do not duplicate abstractions that already exist.

The repository already contains the ingestion, parsing, normalization, chunking, embedding, indexing, retrieval, hybrid retrieval, reranking, and evaluation layers. This issue adds the missing remote document acquisition layer.

==================================================
GOAL
==================================================

Create a safe and modular Skatteetaten crawler that can:

1. download official Skatteetaten HTML pages;
2. optionally follow internal Skatteetaten links;
3. save raw HTML locally;
4. save metadata/manifests for every fetched page;
5. detect whether a page contains an interactive Skatteetaten wizard;
6. produce artifacts that can later be passed through the existing ingestion pipeline.

The intended pipeline is:

Skatteetaten URL
    ↓
Crawler
    ↓
Raw HTML + crawl metadata
    ↓
existing parser
    ↓
existing normalizer
    ↓
existing chunker
    ↓
existing embedding/indexing pipeline

The crawler must NOT contain parsing, chunking, embedding or indexing logic.

==================================================
1. CRAWLER ABSTRACTION
==================================================

Create an explicit crawler/source abstraction following the existing architecture.

Prefer something conceptually similar to:

class Crawler(Protocol):
    def crawl(self, request: CrawlRequest) -> CrawlResult:
        ...

Adapt this to the async/sync conventions already used by the repository.

Define typed domain models as appropriate, for example:

CrawlRequest
CrawledPage
CrawlResult
CrawlMetadata

Use Pydantic v2 if domain models in the repository already use Pydantic.

A CrawledPage should contain enough information to preserve provenance, including at least:

- original_url
- final_url
- canonical_url, if discoverable
- document_id
- retrieved_at
- HTTP status
- content_type
- content_sha256
- raw_html
- language hint, if explicitly available in HTML metadata
- page_type
- wizard metadata when present

Do not infer tax facts in the crawler.

==================================================
2. SKATTEETATEN DOMAIN RESTRICTION
==================================================

Implement a Skatteetaten-specific crawler.

Allowed hosts must be configurable but default to official Skatteetaten web pages only.

At minimum support:

www.skatteetaten.no
skatteetaten.no

Reject external URLs.

When following links:

- follow only HTTP/HTTPS links;
- reject mailto:, tel:, javascript:, fragments-only URLs, etc.;
- normalize relative URLs;
- remove URL fragments before deduplication;
- avoid crawling login/application areas unless explicitly allowed;
- never follow links to arbitrary external domains.

Do not crawl:

- social media
- unrelated external resources
- images
- CSS
- JavaScript bundles
- fonts
- downloadable binaries

For the MVP, only text/html pages are crawl targets.

==================================================
3. SAFE HTTP CLIENT
==================================================

Use a proper HTTP client already present in the repository if available.

Otherwise prefer httpx.

Implement:

- explicit User-Agent
- connection timeout
- read timeout
- retry policy for transient errors
- configurable delay between requests
- redirect handling
- maximum response size if practical
- meaningful exceptions

Do not retry indefinitely.

Reasonable defaults could be approximately:

timeout: 15–30 seconds
max retries: 2–3
delay: around 0.5–1 second

Make them configurable.

Retry only transient failures such as:

- network failures
- HTTP 429
- HTTP 500
- HTTP 502
- HTTP 503
- HTTP 504

Do not blindly retry permanent 4xx failures.

==================================================
4. ROBOTS.TXT
==================================================

Add basic robots.txt compliance.

Before crawling paths for a host, consult robots.txt and avoid fetching URLs disallowed for the crawler's User-Agent.

Cache robots rules per host during a crawl session.

If robots.txt cannot be retrieved because of a transient failure, handle the situation explicitly and conservatively.

Do not build a complex robots subsystem; basic standards-compliant support is sufficient.

==================================================
5. URL NORMALIZATION AND DEDUPLICATION
==================================================

Normalize URLs before queueing them.

At minimum:

- lowercase host
- remove fragments
- resolve relative URLs
- normalize obvious duplicate trailing-slash cases according to the project's URL policy
- use canonical URL metadata when available
- keep deterministic document IDs using the project's existing hashing/ID utilities

Avoid crawling the same normalized URL twice in one crawl.

Also detect duplicate content using SHA-256.

Two different URLs with identical HTML/content should be identifiable as duplicate content in crawl metadata.

Do not silently discard provenance.

==================================================
6. RAW ARTIFACT STORAGE
==================================================

Persist downloaded pages.

Reuse an existing repository/storage abstraction if one already exists.

Otherwise introduce a small explicit storage abstraction, for example:

RawDocumentRepository / CrawlArtifactRepository

Do NOT write files directly from low-level HTTP code.

Suggested output layout:

data/raw/skatteetaten/<document_id>.html

and metadata such as:

data/manifests/crawl/<document_id>.json

or an equivalent structure consistent with the repository.

Metadata should include at least:

{
  "document_id": "...",
  "original_url": "...",
  "final_url": "...",
  "canonical_url": "...",
  "retrieved_at": "...",
  "http_status": 200,
  "content_type": "text/html",
  "content_sha256": "...",
  "language": "en",
  "page_type": "static_article",
  "wizard_ids": [],
  "duplicate_of": null
}

Use UTF-8.

Writes should be deterministic and atomic where reasonable.

Running the crawler twice for unchanged pages must not create arbitrary duplicate filenames.

==================================================
7. INTERACTIVE PAGE / WIZARD DETECTION
==================================================

Add detection of Skatteetaten interactive wizard pages.

DO NOT traverse the wizard yet.

DO NOT use Playwright.

DO NOT execute JavaScript.

Only classify and capture metadata.

The project has already encountered pages where the raw HTML contains structures such as:

- class="wizardstartpage"
- class="wizards"
- id="vue-advanced-wizard"
- data-wizard-step-type="question"
- data-stepid="..."
- JavaScript such as:
    var id = 560397;
    var language = "en";

The crawler should detect this kind of page and classify it.

Use a typed page classification, for example:

STATIC_ARTICLE
INTERACTIVE_WIZARD
UNKNOWN_DYNAMIC

Avoid stringly-typed values if the project already uses enums.

For wizard pages, extract safe structural metadata when available:

- wizard ID
- first visible step ID
- initial question
- available initial answer labels
- language
- whether only the initial rendered step appears to be present

Do NOT claim that all wizard branches have been captured.

A page with a wizard should remain available to the normal HTML parser for its static content.

==================================================
8. LINK EXTRACTION FOR CRAWLING
==================================================

Implement link discovery separately from article parsing.

The crawler may inspect anchor href attributes only for navigation purposes.

Do not reuse article paragraphs as the crawler graph.

For every page:

- extract candidate links;
- normalize them;
- filter according to allowlist;
- ignore fragments and non-HTML resources;
- enqueue unseen URLs subject to limits.

Crawler link discovery must be its own small component/function that can be unit tested.

==================================================
9. CRAWL LIMITS
==================================================

Prevent runaway crawls.

Support configurable:

- max_pages
- max_depth
- request_delay
- allowed_hosts
- allowed_path_prefixes if practical

Defaults must be conservative.

For example:

max_pages = 50
max_depth = 2

A crawl must terminate deterministically when limits are reached.

==================================================
10. CLI
==================================================

Add CLI commands consistent with the existing TaxGuide CLI.

The exact naming should follow current CLI conventions after inspecting the repository.

Conceptually support:

Single-page acquisition:

uv run taxguide crawl \
  "https://www.skatteetaten.no/en/person/taxes/tax-return/" \
  --max-pages 1

Small recursive crawl:

uv run taxguide crawl \
  "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/" \
  --max-pages 25 \
  --max-depth 2

Useful options:

--max-pages
--max-depth
--delay
--output-dir
--json
--no-follow

Do not expose unnecessary implementation details.

The CLI output should summarize something like:

Crawl complete

Fetched:            18
Skipped:             4
Duplicates:          2
Failed:              1
Interactive wizards: 3

Artifacts:
data/raw/...
data/manifests/...

When --json is used, output machine-readable JSON without human formatting mixed into stdout.

Logs can go to stderr according to the repository's existing logging conventions.

==================================================
11. FAILURE HANDLING
==================================================

Add explicit domain exceptions as appropriate, such as:

CrawlerError
DisallowedDomainError
RobotsDisallowedError
UnsupportedContentTypeError
FetchError
ResponseTooLargeError

Reuse existing exception hierarchy if present.

One failed page should not necessarily abort an entire multi-page crawl.

CrawlResult should report failures with:

- URL
- error category
- useful message

Do not silently swallow exceptions.

==================================================
12. TESTS
==================================================

Tests must NOT require internet access.

Use fixtures and mocked HTTP responses.

Add unit tests for at least:

- allowed domain validation
- rejection of external domains
- relative URL resolution
- fragment removal
- URL deduplication
- redirect handling
- transient retry behavior
- permanent 404 behavior
- non-HTML rejection
- content hashing
- deterministic IDs
- storage
- max_pages
- max_depth
- duplicate content
- robots.txt allow
- robots.txt disallow
- wizard detection
- wizard ID extraction
- ordinary static page classification
- crawl link extraction

Add at least one integration-style test:

seed Skatteetaten page
    ↓
mock HTTP
    ↓
crawler
    ↓
linked page(s)
    ↓
raw files persisted
    ↓
manifest persisted

No real network calls.

Use realistic HTML fixtures.

Include a fixture modeled after the observed Skatteetaten wizard structure, including:

<div class="wizardstartpage">
...
<div id="vue-advanced-wizard">
...
data-wizard-step-type="question"
...
</div>

The test should verify that it is classified as INTERACTIVE_WIZARD and that the initial wizard metadata is extracted.

==================================================
13. EXISTING INGESTION INTEGRATION
==================================================

Do not redesign the ingestion pipeline.

Make crawler artifacts compatible with the existing RawDocument/local-document source abstraction.

There should be a clean handoff:

Crawler
    ↓
saved raw artifact
    ↓
existing local/raw document source
    ↓
existing parser

If a small adapter is required, implement only that adapter.

The parser must remain responsible for extracting article content.

The crawler must remain responsible for acquisition and crawl metadata.

==================================================
14. DOCUMENTATION
==================================================

Add/update documentation explaining:

- crawler responsibilities
- crawler non-responsibilities
- supported domain
- crawl limits
- raw artifact layout
- manifest format
- how to run a single-page crawl
- how to run a small recursive crawl
- how wizard pages are handled
- that wizard branches are NOT yet traversed
- how crawler output enters the existing ingestion pipeline

Add an ADR only if the repository's existing ADR policy makes one appropriate.

==================================================
15. NON-GOALS
==================================================

Explicitly DO NOT implement:

- Playwright
- Selenium
- JavaScript execution
- wizard branch traversal
- form submission
- login/authenticated Skatteetaten areas
- tax return submission
- PDF parsing
- sitemap crawling unless trivially required by existing architecture
- Lovdata crawling
- Altinn crawling
- Regjeringen crawling
- distributed crawling
- Celery/background workers
- recurring scheduling
- change detection across historical snapshots
- incremental re-indexing
- embeddings
- Qdrant indexing
- reranking
- LLMs
- FastAPI endpoints
- UI

These belong to later issues.

==================================================
16. QUALITY REQUIREMENTS
==================================================

Preserve the project's current engineering standards:

- Python 3.12+
- typed code
- Pydantic v2 where appropriate
- explicit interfaces
- dependency injection
- no LangChain
- no LlamaIndex
- no Haystack
- avoid unnecessary dependencies
- modular design
- deterministic behavior
- timezone-aware timestamps
- testable without network access

Before completing the issue, run:

uv run pytest
uv run ruff check .
uv run mypy src

Fix failures caused by the implementation.

==================================================
17. ACCEPTANCE CRITERIA
==================================================

The issue is complete only when all of the following work:

1. A Skatteetaten URL can be downloaded through the crawler.
2. External domains are rejected.
3. Raw HTML is persisted.
4. Crawl metadata is persisted.
5. Canonical/source URL provenance is preserved.
6. Content SHA-256 is calculated.
7. URLs are deduplicated.
8. Recursive crawling respects max_pages and max_depth.
9. robots.txt rules are respected.
10. Interactive Skatteetaten wizard pages are detected.
11. Wizard pages are NOT falsely treated as fully captured.
12. Ordinary static pages remain classified normally.
13. Crawler output can be consumed by the existing ingestion pipeline.
14. Tests make no external HTTP requests.
15. pytest passes.
16. Ruff passes.
17. mypy passes.

==================================================
WORKFLOW
==================================================

Before modifying code:

1. inspect the repository;
2. inspect current domain models and ingestion interfaces;
3. inspect CLI conventions;
4. inspect configuration conventions;
5. inspect existing hashing and deterministic-ID utilities;
6. inspect AGENTS.md;
7. read only the relevant parts of norway_tax_rag_architecture.md;
8. identify which existing components can be reused.

Then briefly state the implementation plan.

Implement the issue.

After implementation, report:

- files added
- files modified
- architecture decisions
- CLI commands added
- tests added
- commands executed
- pytest result
- Ruff result
- mypy result
- assumptions
- known limitations

Do not continue into another issue.